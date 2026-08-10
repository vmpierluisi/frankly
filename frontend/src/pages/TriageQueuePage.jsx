import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { triage as triageApi } from "../api.js";
import TriageStack from "../components/v7/TriageStack.jsx";

// Manager Shortlist V7 — optional manual triage (swipe) page.
// Swipe decisions persist to TriageDecision; "Compare shortlist →" navigates to
// the shortlist with the swiped-right set as an explicit candidate_ids list.
export default function TriageQueuePage() {
  const { positionId } = useParams();
  const nav = useNavigate();
  const [queue, setQueue] = useState(null);
  const [error, setError] = useState("");
  // Track this session's decisions so we can build the shortlist link.
  const decisions = useRef({});
  const [shortlisted, setShortlisted] = useState([]);

  useEffect(() => {
    triageApi
      .queue(positionId)
      .then((q) => {
        setQueue(q);
        decisions.current = { ...q.decided };
        setShortlisted(
          Object.entries(q.decided)
            .filter(([, d]) => d === "shortlist")
            .map(([id]) => id),
        );
      })
      .catch((e) => setError(e.message || String(e)));
  }, [positionId]);

  function onDecide(candidateId, decision) {
    decisions.current[candidateId] = decision;
    setShortlisted((prev) =>
      decision === "shortlist"
        ? [...new Set([...prev, candidateId])]
        : prev.filter((id) => id !== candidateId),
    );
    // Persist (blind — never notifies the candidate).
    triageApi.decide(positionId, { candidate_id: candidateId, decision }).catch(() => {});
  }

  function openShortlist() {
    const ids = shortlisted.length ? shortlisted : null;
    const qs = ids ? `?candidate_ids=${ids.join(",")}` : "";
    nav(`/manager/positions/${positionId}/shortlist${qs}`);
  }

  if (error) {
    return (
      <Shell>
        <p style={{ color: COLORS.accent, fontStyle: "italic" }}>{error}</p>
        <button className="ghost" onClick={() => nav(`/manager/positions/${positionId}/shortlist`)}>
          ← Back to shortlist
        </button>
      </Shell>
    );
  }
  if (!queue) {
    return <Shell><p style={{ color: COLORS.muted, fontStyle: "italic" }}>Loading queue…</p></Shell>;
  }

  const { position, candidates } = queue;

  return (
    <Shell>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 24 }}>
        <div>
          <div className="label-mono" style={{ fontFamily: FONT_MONO, fontSize: 10 }}>
            Triage queue · {position.company_name} · {position.role_short}
          </div>
          <h2 style={{ fontFamily: FONT_DISPLAY, fontSize: 34, fontWeight: 500, margin: "6px 0 0" }}>
            Swipe the queue.
          </h2>
        </div>
        <button
          className="ghost"
          style={{ padding: "8px 14px", fontSize: 11, flexShrink: 0 }}
          onClick={openShortlist}
        >
          Compare shortlist →
        </button>
      </div>

      {candidates.length === 0 ? (
        <div style={{ padding: "64px 0", textAlign: "center", color: COLORS.muted, fontStyle: "italic" }}>
          No candidates have completed simulation yet.
        </div>
      ) : (
        <TriageStack
          candidates={candidates}
          decided={decisions.current}
          onDecide={onDecide}
          onOpenShortlist={openShortlist}
        />
      )}
    </Shell>
  );
}

function Shell({ children }) {
  return <main className="container" style={{ maxWidth: 900 }}>{children}</main>;
}
