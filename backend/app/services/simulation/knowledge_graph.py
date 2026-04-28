"""Company knowledge graph extractor.

MiroFish lineage: corresponds to MiroFish's DocumentGraph primitive —
structured node/edge representation of values, behaviors, and decisions
extracted from company artifacts. Used by team synthesis (grounds centroid
inferences), scenario drafting (seeds scenario topics from decision nodes),
and judge scoring (anchors justifications to artifact passages).

v0 scope: simple node/edge JSON persisted on Company.knowledge_graph.
No Neo4j — Postgres + JSON is sufficient until the graph exceeds ~200 nodes.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from .cost_tracker import CostBudget, tracked_chat_json

if TYPE_CHECKING:
    from ...models import Company

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates (verbatim from brief Appendix A.4)
# ---------------------------------------------------------------------------

KNOWLEDGE_GRAPH_SYSTEM = """\
You build a lightweight knowledge graph over a company's sanctioned
artifacts. The graph is consumed downstream by team synthesis, scenario
drafting, and judge scoring — keep nodes specific and edges meaningful.

NODE TYPES (use these exactly, no others):
  * value          — an explicit company value or principle
  * behavior       — an observable behavior the company expects or rewards
  * anti_behavior  — a behavior the company explicitly does not reward
  * role           — a position, seniority level, or pod/team unit
  * decision       — a recurring decision the team makes
  * artifact_quote — a directly-quoted artifact passage that anchors other
                      nodes (max 240 chars)

EDGE TYPES (use these exactly):
  * demands        — value -> behavior, role -> behavior
  * forbids        — value -> anti_behavior
  * cites          — any node -> artifact_quote (provenance)
  * informs        — decision -> behavior
  * conflicts_with — value -> value, behavior -> behavior (surface tensions)

HARD RULES:
  1. Every value, behavior, anti_behavior, role, and decision node MUST
     have at least one cites edge to an artifact_quote.
  2. Surface conflicts via conflicts_with edges. Do not paper over
     contradictions inside the artifacts.
  3. Keep node count modest: 8-25 non-quote nodes plus their backing
     artifact_quote nodes.
  4. Strict JSON only. Never reference protected characteristics.\
"""

KNOWLEDGE_GRAPH_USER_TEMPLATE = """\
Build the knowledge graph for this company.

COMPANY: {company_name}
ROLE: {role}

ARTIFACTS
=========
VALUES:
\"\"\"
{artifact_values}
\"\"\"

ROLE SPEC:
\"\"\"
{artifact_role_spec}
\"\"\"

TEAM STRUCTURE:
\"\"\"
{artifact_team_structure}
\"\"\"

SAMPLE COMMS:
\"\"\"
{artifact_sample_comms}
\"\"\"

Return a JSON object matching the KnowledgeGraph schema.\
"""

# ---------------------------------------------------------------------------
# JSON schema (verbatim from brief Appendix B.4)
# ---------------------------------------------------------------------------

KNOWLEDGE_GRAPH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id":    {"type": "string", "description": "Stable slug, e.g. 'value:patience'."},
                    "type":  {"type": "string", "description": "One of: value, behavior, anti_behavior, role, decision, artifact_quote."},
                    "label": {"type": "string"},
                    "body":  {"type": "string", "description": "1-3 sentences. For artifact_quote: the quoted text (max 240 chars)."},
                },
                "required": ["id", "type", "label", "body"],
                "additionalProperties": False,
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "type":   {"type": "string", "description": "One of: demands, forbids, cites, informs, conflicts_with."},
                    "note":   {"type": "string"},
                },
                "required": ["source", "target", "type", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["nodes", "edges"],
    "additionalProperties": False,
}

# Node types that must each have at least one cites edge to an artifact_quote.
_CITES_REQUIRED_TYPES = {"value", "behavior", "anti_behavior", "role", "decision"}
_VALID_NODE_TYPES = _CITES_REQUIRED_TYPES | {"artifact_quote"}
_VALID_EDGE_TYPES = {"demands", "forbids", "cites", "informs", "conflicts_with"}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_graph(graph: dict[str, Any]) -> list[str]:
    """Post-hoc validation of the graph beyond what the JSON schema enforces.

    Returns a list of warning strings.  Warnings are logged but do not raise —
    the LLM output is kept as-is so callers can decide whether to retry.
    """
    warnings: list[str] = []
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])

    # Build lookup: which non-quote nodes have a cites edge?
    has_cites: set[str] = set()
    for e in edges:
        if e.get("type") == "cites":
            has_cites.add(e["source"])

    for node in graph.get("nodes", []):
        ntype = node.get("type", "")
        if ntype not in _VALID_NODE_TYPES:
            warnings.append(f"Unknown node type {ntype!r} on node {node['id']!r}")
        if ntype in _CITES_REQUIRED_TYPES and node["id"] not in has_cites:
            warnings.append(
                f"Node {node['id']!r} (type={ntype}) has no cites edge to an artifact_quote"
            )

    for edge in edges:
        etype = edge.get("type", "")
        if etype not in _VALID_EDGE_TYPES:
            warnings.append(f"Unknown edge type {etype!r} on edge {edge['source']!r}->{edge['target']!r}")
        for endpoint in ("source", "target"):
            if edge[endpoint] not in nodes_by_id:
                warnings.append(
                    f"Edge references unknown node {edge[endpoint]!r} as {endpoint}"
                )

    non_quote_count = sum(
        1 for n in graph.get("nodes", []) if n.get("type") != "artifact_quote"
    )
    if non_quote_count < 8:
        warnings.append(f"Only {non_quote_count} non-quote nodes — expected at least 8")
    if non_quote_count > 25:
        warnings.append(f"{non_quote_count} non-quote nodes — brief asks for ≤25")

    return warnings


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def _render_user_prompt(company: "Company") -> str:
    return KNOWLEDGE_GRAPH_USER_TEMPLATE.format(
        company_name=company.name,
        role=company.role,
        artifact_values=company.artifact_values or "(none provided)",
        artifact_role_spec=company.artifact_role_spec or "(none provided)",
        artifact_team_structure=company.artifact_team_structure or "(none provided)",
        artifact_sample_comms=company.artifact_sample_comms or "(none provided)",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def extract(company: "Company", *, budget: CostBudget) -> dict[str, Any]:
    """Extract a knowledge graph from company artifacts.

    Returns the KnowledgeGraph dict (nodes + edges). Does not persist to DB —
    the caller is responsible for writing result to company.knowledge_graph.

    Post-hoc structural warnings are logged at WARNING level but do not raise.
    """
    user_prompt = _render_user_prompt(company)
    result = await tracked_chat_json(
        budget,
        system=KNOWLEDGE_GRAPH_SYSTEM,
        user=user_prompt,
        schema=KNOWLEDGE_GRAPH_SCHEMA,
        schema_name="knowledge_graph",
        temperature=0.2,
        max_tokens=3000,
    )

    warnings = validate_graph(result)
    for w in warnings:
        logger.warning("knowledge_graph[%s]: %s", company.id, w)

    return result


def summarize_for_prompt(graph: dict[str, Any] | None) -> str:
    """Render a compact text summary of the knowledge graph for embedding in
    downstream prompts (team centroid, scenario drafter).

    Returns '(none)' when the graph is absent.
    """
    if not graph:
        return "(none)"
    nodes = graph.get("nodes", [])
    if not nodes:
        return "(none)"
    lines: list[str] = []
    for node in nodes:
        if node.get("type") == "artifact_quote":
            continue
        lines.append(f"  [{node['type']}] {node['label']}: {node['body'][:120]}")
    edges = graph.get("edges", [])
    conflict_edges = [e for e in edges if e.get("type") == "conflicts_with"]
    if conflict_edges:
        lines.append("  TENSIONS:")
        for e in conflict_edges:
            lines.append(f"    {e['source']} conflicts_with {e['target']}: {e.get('note', '')[:80]}")
    return "\n".join(lines) if lines else "(none)"
