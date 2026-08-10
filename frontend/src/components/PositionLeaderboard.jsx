import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { positions, matches } from "../api.js";
import { GeneratingScreen } from "./Widgets.jsx";

const POLL_INTERVAL_MS = 5000;

const BAND_COLOR = {
  "Exceptional fit": "#0a6640",
  "Strong fit": "#0e7a4d",
  "Good fit": "#1d6fa4",
  "Moderate fit": "#7d5a00",
  "Weak fit": "#9e2a2a",
  "Poor fit": "#666",
};

function bandColor(band) {
  return BAND_COLOR[band] || COLORS.muted;
}

export default function PositionLeaderboard({ positionId }) {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(null);
  const pollRef = useRef(null);

  async function load() {
    try {
      const result = await positions.leaderboard(positionId);
      setData(result);
      setError("");

      // Keep polling while any row is still in-flight.
      const hasLive = result.results.some(
        (r) => r.status === "pending" || r.status === "running",
      );
      if (hasLive) {
        pollRef.current = setTimeout(load, POLL_INTERVAL_MS);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    setData(null);
    load();
    return () => clearTimeout(pollRef.current);
  }, [positionId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleRetry(matchId, candidateId) {
    if (!data) return;
    setRetrying(matchId);
    try {
      await matches.trigger(candidateId, positionId);
      await load();
    } catch (e) {
      setError(`Retry failed: ${e.message}`);
    } finally {
      setRetrying(null);
    }
  }

  if (loading) return <GeneratingScreen note="Loading leaderboard…" />;
  if (error) return (
    <div style={{ color: COLORS.accent, fontStyle: "italic", padding: "24px 0" }}>{error}</div>
  );
  if (!data) return null;

  const succeeded = data.results.filter((r) => r.status === "succeeded");
  const topFive = succeeded.slice(0, 5);
  const remaining = succeeded.slice(5);
  const inFlight = data.results.filter(
    (r) => r.status === "pending" || r.status === "running",
  );
  const failed = data.results.filter((r) => r.status === "failed");

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4 }}>
        <div className="label-mono">Candidate leaderboard</div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {succeeded.length > 0 && (
            <button
              onClick={() => nav(`/manager/positions/${positionId}/shortlist`)}
              style={{
                background: "transparent",
                border: `1px solid ${COLORS.ink}`,
                cursor: "pointer",
                fontFamily: FONT_MONO,
                fontSize: 10,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: COLORS.ink,
                padding: "6px 12px",
              }}
            >
              Open shortlist comparison →
            </button>
          )}
          <div style={{ fontFamily: FONT_MONO, fontSize: 10, color: COLORS.muted, letterSpacing: "0.1em" }}>
            {succeeded.length} evaluated · {inFlight.length} in progress · {failed.length} failed
          </div>
        </div>
      </div>
      <div style={{ fontFamily: FONT_DISPLAY, fontSize: 22, fontWeight: 500, marginBottom: 4 }}>
        {data.company_name}
      </div>
      <div style={{ color: COLORS.muted, fontSize: 14, marginBottom: 24 }}>
        {data.role}
        {data.role_family && (
          <span style={{ marginLeft: 12, fontFamily: FONT_MONO, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>
            {data.role_family.replace(/_/g, " ")}
          </span>
        )}
        {data.target_seniority && (
          <span style={{ marginLeft: 8, fontFamily: FONT_MONO, fontSize: 10, color: COLORS.muted, textTransform: "uppercase" }}>
            · {data.target_seniority}
          </span>
        )}
        {!data.is_open && (
          <span style={{ marginLeft: 12, fontFamily: FONT_MONO, fontSize: 10, color: COLORS.accent, textTransform: "uppercase" }}>
            · closed
          </span>
        )}
      </div>

      <hr className="rule" style={{ margin: "0 0 28px" }} />

      {succeeded.length === 0 && inFlight.length === 0 && failed.length === 0 && (
        <div style={{ color: COLORS.muted, fontStyle: "italic", padding: "40px 0", textAlign: "center" }}>
          No candidates evaluated yet. Simulations will appear here automatically
          as candidates complete intake and match this position.
        </div>
      )}

      {/* Top 5 — prominent cards */}
      {topFive.length > 0 && (
        <section style={{ marginBottom: 32 }}>
          <div className="label-mono" style={{ marginBottom: 14 }}>Ready to interview</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {topFive.map((row, idx) => (
              <LeaderboardRow
                key={row.match_id}
                row={row}
                rank={idx + 1}
                prominent
                positionId={positionId}
              />
            ))}
          </div>
        </section>
      )}

      {/* Remaining succeeded — compact */}
      {remaining.length > 0 && (
        <section style={{ marginBottom: 32 }}>
          <div className="label-mono" style={{ marginBottom: 14 }}>Also evaluated</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {remaining.map((row, idx) => (
              <LeaderboardRow
                key={row.match_id}
                row={row}
                rank={topFive.length + idx + 1}
                prominent={false}
                positionId={positionId}
              />
            ))}
          </div>
        </section>
      )}

      {/* In-flight */}
      {inFlight.length > 0 && (
        <section style={{ marginBottom: 32 }}>
          <div className="label-mono" style={{ marginBottom: 14 }}>In progress</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {inFlight.map((row) => (
              <InFlightRow key={row.match_id} row={row} />
            ))}
          </div>
        </section>
      )}

      {/* Failed */}
      {failed.length > 0 && (
        <section style={{ marginBottom: 32 }}>
          <div className="label-mono" style={{ marginBottom: 14, color: COLORS.accent }}>
            Failed
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {failed.map((row) => (
              <FailedRow
                key={row.match_id}
                row={row}
                retrying={retrying === row.match_id}
                onRetry={() => handleRetry(row.match_id, row.candidate_id)}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ─── Succeeded row ──────────────────────────────────────────────────────────

function LeaderboardRow({ row, rank, prominent, positionId }) {
  const nav = useNavigate();
  const scoreColor = bandColor(row.band);
  const openShortlist = () =>
    nav(`/manager/positions/${positionId}/shortlist?candidate_ids=${row.candidate_id}`);

  return (
    <div>
      <div
        onClick={openShortlist}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: prominent ? "16px 20px" : "10px 20px",
          border: `1px solid ${COLORS.rule}`,
          background: "transparent",
          cursor: "pointer",
          transition: "border 0.15s, background 0.15s",
        }}
      >
        {/* Rank */}
        <div
          style={{
            fontFamily: FONT_MONO,
            fontSize: 11,
            color: COLORS.muted,
            minWidth: 28,
            textAlign: "right",
          }}
        >
          {String(rank).padStart(2, "0")}
        </div>

        {/* Name + seniority */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontFamily: prominent ? FONT_DISPLAY : undefined,
              fontSize: prominent ? 18 : 15,
              fontWeight: prominent ? 500 : 400,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {row.display_name || "Anonymous candidate"}
          </div>
          {row.candidate_seniority && (
            <div
              style={{
                fontFamily: FONT_MONO,
                fontSize: 10,
                color: COLORS.muted,
                textTransform: "uppercase",
                letterSpacing: "0.1em",
              }}
            >
              {row.candidate_seniority}
            </div>
          )}
        </div>

        {/* Band */}
        <div
          style={{
            fontFamily: FONT_MONO,
            fontSize: 11,
            color: scoreColor,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            display: prominent ? "block" : "none",
          }}
        >
          {row.band}
        </div>

        {/* PR #2d.3 — dual-score columns. Skills column hides when null
            (position has no required_skills configured). */}
        {row.skills_fit != null && (
          <div
            style={{
              fontFamily: FONT_MONO,
              fontSize: 11,
              color: COLORS.muted,
              minWidth: 56,
              textAlign: "right",
            }}
            title="Skills fit"
          >
            <div style={{ fontSize: 9, letterSpacing: "0.1em" }}>SKILLS</div>
            <div style={{ fontSize: 14, color: COLORS.ink }}>{row.skills_fit}</div>
          </div>
        )}
        {row.behaviour_fit != null && (
          <div
            style={{
              fontFamily: FONT_MONO,
              fontSize: 11,
              color: COLORS.muted,
              minWidth: 64,
              textAlign: "right",
            }}
            title="Behaviour fit"
          >
            <div style={{ fontSize: 9, letterSpacing: "0.1em" }}>BEHAVIOUR</div>
            <div style={{ fontSize: 14, color: COLORS.ink }}>{row.behaviour_fit}</div>
          </div>
        )}

        {/* Overall score pill */}
        <div
          style={{
            fontFamily: FONT_MONO,
            fontSize: prominent ? 22 : 16,
            fontWeight: 500,
            color: scoreColor,
            minWidth: 44,
            textAlign: "right",
          }}
          title="Overall fit"
        >
          {row.overall_score}
        </div>

        {/* Open-shortlist affordance */}
        <div style={{ color: COLORS.muted, fontSize: 13 }} title="Compare in shortlist">→</div>
      </div>
    </div>
  );
}

// ─── In-flight row ──────────────────────────────────────────────────────────

function InFlightRow({ row }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "10px 20px",
        border: `1px solid ${COLORS.rule}`,
        color: COLORS.muted,
      }}
    >
      <div style={{ fontFamily: FONT_MONO, fontSize: 11, minWidth: 28, textAlign: "right" }}>
        —
      </div>
      <div style={{ flex: 1, fontSize: 15 }}>
        {row.display_name || "Anonymous candidate"}
      </div>
      <div
        style={{
          fontFamily: FONT_MONO,
          fontSize: 10,
          textTransform: "uppercase",
          letterSpacing: "0.1em",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span className="pulse-dot" />
        {row.status === "running" ? "Evaluating" : "Queued"}
      </div>
    </div>
  );
}

// ─── Failed row ─────────────────────────────────────────────────────────────

function FailedRow({ row, retrying, onRetry }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "10px 20px",
        border: `1px solid ${COLORS.rule}`,
      }}
    >
      <div style={{ fontFamily: FONT_MONO, fontSize: 11, color: COLORS.accent, minWidth: 28, textAlign: "right" }}>
        ✕
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 15 }}>{row.display_name || "Anonymous candidate"}</div>
        {row.error_message && (
          <div style={{ fontFamily: FONT_MONO, fontSize: 10, color: COLORS.muted, marginTop: 2 }}>
            {row.error_message}
          </div>
        )}
      </div>
      <button
        className="ghost"
        onClick={onRetry}
        disabled={retrying}
        style={{ padding: "4px 12px", fontSize: 11 }}
      >
        {retrying ? "Retrying…" : "Retry"}
      </button>
    </div>
  );
}
