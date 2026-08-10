import React, { useCallback, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { useShortlistState } from "../hooks/useShortlistState.js";
import ShortlistSizeSelector from "../components/v7/ShortlistSizeSelector.jsx";
import ChipBar from "../components/v7/ChipBar.jsx";
import OverviewTable from "../components/v7/OverviewTable.jsx";
import CellPopover from "../components/v7/CellPopover.jsx";
import FloatingDecideBar from "../components/v7/FloatingDecideBar.jsx";
import CVModal from "../components/v7/CVModal.jsx";
import ScenarioComparison from "../components/v7/ScenarioComparison.jsx";
import FitChart from "../components/v7/FitChart.jsx";
import ScheduleInterviewModal from "../components/ScheduleInterviewModal.jsx";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "scenarios", label: "Scenarios" },
  { id: "fit", label: "Fit chart" },
];

// Manager Shortlist V7 — primary landing page for a position.
// Auto-fetches top-N on mount (or an explicit candidate set from the URL),
// mirrors tab / sub-tab / N into the URL, and hosts the three inner tabs plus
// the floating decide bar.
export default function ShortlistComparePage() {
  const { positionId } = useParams();
  const nav = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const urlIds = searchParams.get("candidate_ids");
  const initialIds = urlIds ? urlIds.split(",").filter(Boolean) : null;
  const nParam = searchParams.get("n");
  const initialN = nParam === "all" ? 50 : Number(nParam) || 3;

  const {
    report,
    loading,
    error,
    changeTopN,
    addCandidate,
    removeCandidate,
  } = useShortlistState(positionId, { initialN, initialIds });

  const tab = searchParams.get("tab") || "overview";
  const fitView = searchParams.get("fit") || "role";
  const focusScenario = useRef(null);

  const scenarioRef = useRef(null);

  function patchParams(patch) {
    const p = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([k, v]) => {
      if (v == null) p.delete(k);
      else p.set(k, v);
    });
    setSearchParams(p, { replace: true });
  }

  function setTab(next) {
    patchParams({ tab: next === "overview" ? null : next });
  }

  function onChangeN(n) {
    changeTopN(n);
    patchParams({ n: n >= 50 ? "all" : String(n), candidate_ids: null });
  }

  // --- Cell popover ---
  const [popover, setPopover] = useState(null); // {rect, candidate, type, rowId, scenarioId}
  const [cvFor, setCvFor] = useState(null);
  const [inviteFor, setInviteFor] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const scenarioIdForRow = useCallback(
    (type, rowId) => {
      if (!report) return null;
      if (type === "behavior") {
        return report.position.criteria.find((c) => c.id === rowId)?.scenario_id || null;
      }
      if (type === "skill") {
        return report.position.skills.find((s) => s.id === rowId)?.scenario_id || null;
      }
      return null;
    },
    [report],
  );

  function onCellAction(type, candidateId, rowId, rect) {
    const candidate = report.candidates.find((c) => c.id === candidateId);
    setPopover({
      rect,
      candidate,
      type,
      rowId,
      scenarioId: scenarioIdForRow(type, rowId),
    });
  }

  function seeInScenario() {
    const sid = popover?.scenarioId;
    setPopover(null);
    setTab("scenarios");
    // Defer until the scenarios tab has mounted, then flash the candidate.
    focusScenario.current = { candidateId: popover?.candidate?.id, scenarioId: sid };
    setTimeout(() => {
      scenarioRef.current?.flashCandidate?.(
        popover?.candidate?.id,
        sid,
      );
    }, 60);
  }

  // --- Decide bar ---
  function invite(candidate) {
    setInviteFor(candidate);
  }
  function inviteAll() {
    if (report?.candidates?.length) setInviteFor(report.candidates[0]);
  }
  async function decline(candidate) {
    // Declining is a manager-side, candidate-blind action (no notification).
    setBusyId(candidate.id);
    try {
      removeCandidate(candidate.id);
    } finally {
      setBusyId(null);
    }
  }

  if (loading && !report) {
    return <Shell><p style={muted}>Loading shortlist…</p></Shell>;
  }
  if (error && !report) {
    return (
      <Shell>
        <p style={{ color: COLORS.accent, fontStyle: "italic" }}>{error}</p>
        <button className="ghost" onClick={() => nav("/manager")}>← Back to dashboard</button>
      </Shell>
    );
  }
  if (!report) return null;

  const { position } = report;
  const hasCandidates = report.candidates.length > 0;

  return (
    <Shell>
      {/* Header + breadcrumb + Open triage */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
        <div>
          <div className="label-mono" style={{ fontFamily: FONT_MONO, fontSize: 10 }}>
            Shortlist · {position.company_name} · {position.role_short}
          </div>
          <h2 style={{ fontFamily: FONT_DISPLAY, fontSize: 34, fontWeight: 500, margin: "6px 0 0" }}>
            Compare the shortlist.
          </h2>
        </div>
        <div style={{ display: "flex", gap: 12, flexShrink: 0 }}>
          <button
            className="ghost"
            style={{ padding: "8px 14px", fontSize: 11 }}
            onClick={() => nav(`/manager/positions/${positionId}/triage`)}
          >
            Open triage →
          </button>
        </div>
      </div>

      {!hasCandidates ? (
        <div style={{ padding: "64px 0", textAlign: "center", color: COLORS.muted, fontStyle: "italic" }}>
          No candidates have completed simulation yet.
          <div style={{ marginTop: 16 }}>
            <button className="ghost" onClick={() => nav("/manager")}>← Back to dashboard</button>
          </div>
        </div>
      ) : (
        <>
          {/* Size selector row */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16, marginTop: 24, flexWrap: "wrap" }}>
            <ShortlistSizeSelector
              value={report.top_n_applied ?? report.candidates.length}
              onChange={onChangeN}
              sizes={position.available_sizes}
            />
            <p style={{ ...muted, maxWidth: 340, textAlign: "right", margin: 0, fontSize: 13 }}>
              Ranked by overall fit score. Adjust to compare more candidates.
            </p>
          </div>

          <ChipBar
            activeCandidates={report.candidates}
            availableCandidates={report.available_candidates}
            onAdd={addCandidate}
            onRemove={removeCandidate}
          />

          {/* Inner tab bar */}
          <div className="nav-bar" style={{ borderBottom: `1px solid ${COLORS.rule}`, marginBottom: 20 }}>
            {TABS.map((t) => (
              <button
                key={t.id}
                className={`nav-link ${tab === t.id ? "active" : ""}`}
                style={{ background: "transparent", border: "none", cursor: "pointer" }}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div style={{ paddingBottom: 120 }}>
            {tab === "overview" && (
              <OverviewTable report={report} onCellAction={onCellAction} />
            )}
            {tab === "scenarios" && (
              <ScenarioComparison
                ref={scenarioRef}
                report={report}
                onAddPassed={addCandidate}
              />
            )}
            {tab === "fit" && (
              <FitChart
                report={report}
                view={fitView}
                onChangeView={(v) => patchParams({ fit: v === "role" ? null : v })}
              />
            )}
          </div>

          <FloatingDecideBar
            activeCandidates={report.candidates}
            onDecline={decline}
            onInvite={invite}
            onInviteAll={inviteAll}
            busyId={busyId}
          />
        </>
      )}

      {popover && (
        <CellPopover
          anchorRect={popover.rect}
          scenarioId={popover.scenarioId}
          linkedinUrl={popover.candidate?.linkedin_url}
          cvAvailable={popover.candidate?.cv_available}
          onSeeInScenario={popover.scenarioId ? seeInScenario : null}
          onOpenLinkedIn={(url) => window.open(url, "_blank", "noopener")}
          onOpenCV={() => {
            setCvFor(popover.candidate);
            setPopover(null);
          }}
          onClose={() => setPopover(null)}
        />
      )}

      {cvFor && (
        <CVModal candidateId={cvFor.id} name={cvFor.name} onClose={() => setCvFor(null)} />
      )}

      {inviteFor && (
        <ScheduleInterviewModal
          matchId={inviteFor.match_id}
          candidateName={inviteFor.name}
          onClose={() => setInviteFor(null)}
          onSubmitted={() => setInviteFor(null)}
        />
      )}
    </Shell>
  );
}

const muted = { color: COLORS.muted, fontStyle: "italic" };

function Shell({ children }) {
  return <main className="container" style={{ maxWidth: 1280 }}>{children}</main>;
}
