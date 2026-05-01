"""Fetch public GitHub profile data: repos, languages, README excerpts.

Uses the unauthenticated GitHub REST API. No OAuth required for public data.
Rate-limited to 60 req/hr by GitHub for unauthenticated callers — fine for
v0 since we only fetch on demand.
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
USER_AGENT = "Frankly-Profile-Extractor/0.1"
TOP_REPOS_LIMIT = 6
README_EXCERPT_CHARS = 1200
HTTP_TIMEOUT = 10.0


def _parse_username(github_url: str) -> str | None:
    """Extract username from various GitHub URL shapes.

    Accepts ``https://github.com/<user>``, ``github.com/<user>``, or just
    ``<user>``. Returns None when the URL is unparseable.
    """
    if not github_url:
        return None
    s = github_url.strip().rstrip("/")
    if not s:
        return None
    if "/" not in s and " " not in s:
        return s
    if not s.startswith("http"):
        s = "https://" + s
    try:
        parsed = urlparse(s)
    except ValueError:
        return None
    if "github.com" not in (parsed.netloc or "").lower():
        return None
    parts = [p for p in (parsed.path or "").split("/") if p]
    if not parts:
        return None
    return parts[0]


async def _get_json(client: httpx.AsyncClient, path: str) -> Any:
    resp = await client.get(path, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def _get_text(client: httpx.AsyncClient, path: str) -> str | None:
    resp = await client.get(
        path,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github.raw"},
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


def _strip_markdown(md: str) -> str:
    """Cheap markdown → plain prose. Removes code fences, headers, links."""
    out = md
    out = re.sub(r"```.*?```", " ", out, flags=re.DOTALL)
    out = re.sub(r"`[^`]*`", " ", out)
    out = re.sub(r"^#+\s*", "", out, flags=re.MULTILINE)
    out = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", out)
    out = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", out)
    out = re.sub(r"<[^>]+>", "", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


async def fetch_github_profile(github_url: str) -> dict[str, Any]:
    """Fetch repos + README excerpts for a public GitHub user.

    Returns a dict ``{repos: [...], readme_samples: [...], username: str | None}``.
    Returns empty defaults on any failure (network, 404, malformed URL) so the
    caller can keep working without GitHub data.
    """
    username = _parse_username(github_url)
    if not username:
        return {"repos": [], "readme_samples": [], "username": None}

    out_repos: list[dict[str, Any]] = []
    readme_samples: list[str] = []

    try:
        async with httpx.AsyncClient(base_url=GITHUB_API, timeout=HTTP_TIMEOUT) as client:
            repos = await _get_json(
                client,
                f"/users/{username}/repos?per_page=100&sort=updated&type=owner",
            )
            if not repos:
                return {"repos": [], "readme_samples": [], "username": username}

            repos = [r for r in repos if not r.get("fork")]
            repos.sort(key=lambda r: (r.get("stargazers_count", 0), r.get("updated_at", "")), reverse=True)
            top = repos[:TOP_REPOS_LIMIT]

            for repo in top:
                name = repo.get("name", "")
                readme_excerpt = ""
                try:
                    readme = await _get_text(client, f"/repos/{username}/{name}/readme")
                    if readme:
                        plain = _strip_markdown(readme)
                        readme_excerpt = plain[:README_EXCERPT_CHARS]
                        if len(plain) > 200:
                            readme_samples.append(plain[:600])
                except httpx.HTTPError as exc:
                    logger.info("README fetch failed for %s/%s: %s", username, name, exc)

                out_repos.append({
                    "name": name,
                    "description": repo.get("description") or "",
                    "language": repo.get("language") or "",
                    "stars": repo.get("stargazers_count", 0),
                    "last_commit_at": repo.get("pushed_at") or repo.get("updated_at"),
                    "readme_excerpt": readme_excerpt,
                })
    except httpx.HTTPError as exc:
        logger.warning("Github fetch failed for %s: %s", username, exc)
        return {"repos": [], "readme_samples": [], "username": username}

    return {"repos": out_repos, "readme_samples": readme_samples, "username": username}
