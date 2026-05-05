import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { candidates as candidatesApi } from "../api.js";
import { supabase } from "../lib/supabase.js";
import VarianceBar from "./VarianceBar.jsx";
import VerifiedProfileView from "./VerifiedProfileView.jsx";
import BaselineCompareStrip from "./BaselineCompareStrip.jsx";
import RolloutSummaryCard from "./RolloutSummaryCard.jsx";
import { ProfileAccuracyChip } from "./ProfileAccuracyRing.jsx";
import { formatCriterion } from "./Widgets.jsx";

/**
 * Roadmap 2 / PR #2c — Fit Profile v3.
 *
 * Wraps the v2 envelope with:
 *   * Profile-link buttons (CV / LinkedIn / GitHub / Portfolio) — hidden when missing
 *   * Resume section: extracted education / experience / skills (VerifiedProfileView)
 *   * Profile accuracy chip
 *   * Tappable score explanations: every dimension row opens a slide-up sheet
 *     with justification + (later) cited transcript turns
 */
export default function FitProfileV3({
  report,
  candidate, // { id, display_name, cv_path, linkedin_url, github_url, portfolio_url, profile_accuracy_score }
  criteriaIndex = {},
  onOpenRollout,
}) {
  const navigate = useNavigate();
  const {
    matchId,
    overallScore,
    band,
    bandNote,
    companyName,
    company_name,
    role,
    criterionScores = {},
    dimensionalFit = null,
    rolloutSummaries = [],
    baselineComparison = null,
    inconsistencyFlags = [],
    confidenceSignals = null,
    auditTrailV2 = {},
    // PR #2d.3 — dual scores. behaviourFit falls back to overallScore for
    // legacy reports computed before this PR. skillsFit is null when the
    // position has no required_skills configured.
    behaviourFit,
    skillsFit,
    skillsFitDetails = null,
  } = report;
  const displayName = companyName || company_name;
  const behaviourScore =
    typeof behaviourFit === "number" ? behaviourFit : overallScore;
  const skillsScore = typeof skillsFit === "number" ? skillsFit : null;

  const [explainKey, setExplainKey] = useState(null); // dimension key being explained
  const [verified, setVerified] = useState(null);

  useEffect(() => {
    if (!candidate?.id) return;
    candidatesApi
      .getCandidateProfile(candidate.id)
      .then(setVerified)
      .catch((e) => {
        if (e.status !== 404) console.warn("verified profile fetch", e);
      });
  }, [candidate?.id]);

  return (
    <div>
      {/* Headline */}
      <div className="label-mono" style={{ marginBottom: 12 }}>
        Fit Report v3 · Confidential · Screening Signal
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: 24,
          marginBottom: 8,
        }}
      >
        <div>
          <h2
            style={{
              fontFamily: FONT_DISPLAY,
              fontSize: 44,
              fontWeight: 500,
              letterSpacing: "-0.015em",
              margin: "0 0 8px",
              lineHeight: 1.1,
            }}
          >
            {band}.
          </h2>
          <p style={{ fontSize: 18, color: COLORS.muted, margin: 0, fontStyle: "italic" }}>
            {bandNote || band}
          </p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 12 }}>
          <DualScoreHeadline
            overall={overallScore}
            behaviour={behaviourScore}
            skills={skillsScore}
          />
          <BaselineCompareStrip
            baselineComparison={baselineComparison}
            simulationOverallScore={overallScore}
            criteriaIndex={criteriaIndex}
          />
        </div>
      </div>

      {/* Candidate strip — links + accuracy */}
      <CandidateStrip candidate={candidate} />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 40,
          margin: "24px 0",
        }}
      >
        <div>
          <div className="label-mono" style={{ marginBottom: 8 }}>Matched environment</div>
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 26, fontWeight: 500 }}>{displayName}</div>
          <div style={{ color: COLORS.muted, fontSize: 16 }}>{role}</div>
        </div>
        {confidenceSignals && (
          <div style={{ textAlign: "right" }}>
            <div className="label-mono" style={{ marginBottom: 8 }}>Confidence signals</div>
            <div style={{ fontFamily: FONT_MONO, fontSize: 13, color: COLORS.muted, lineHeight: 1.8 }}>
              <div>σ overall: {(confidenceSignals.overallStd ?? 0).toFixed(1)}</div>
              <div>judge agreement: {(confidenceSignals.judgeAgreementMean ?? 0).toFixed(2)}</div>
              <div>min rollouts: {confidenceSignals.minNRollouts ?? 0}</div>
            </div>
          </div>
        )}
      </div>

      <hr className="rule-thick" style={{ margin: "24px 0" }} />

      {/* Resume section — verified profile */}
      <div className="label-mono" style={{ marginBottom: 16 }}>Background</div>
      {verified ? (
        <VerifiedProfileView profile={verified} />
      ) : (
        <div style={{ color: COLORS.muted, fontSize: 14, fontStyle: "italic" }}>
          No verified profile extracted for this candidate yet.
        </div>
      )}

      <hr className="rule-thick" style={{ margin: "32px 0 24px" }} />

      {/* Dimensional fit chart — tappable rows */}
      <div className="label-mono" style={{ marginBottom: 16 }}>Scoring decomposition</div>
      <TappableDimensionalChart
        criterionScores={criterionScores}
        dimensionalFit={dimensionalFit}
        criteriaIndex={criteriaIndex}
        onTap={(key) => setExplainKey(key)}
      />

      {/* Rollout summaries */}
      {rolloutSummaries.length > 0 ? (
        <div style={{ marginTop: 40 }}>
          <div className="label-mono" style={{ marginBottom: 16 }}>Simulation rollouts</div>
          <div style={{ display: "flex", gap: 16, overflowX: "auto", paddingBottom: 8 }}>
            {rolloutSummaries.map((s) => (
              <RolloutSummaryCard
                key={s.rolloutId}
                summary={s}
                onClick={(rolloutId) => {
                  if (onOpenRollout) return onOpenRollout(rolloutId);
                  if (matchId) navigate(`/manager/matches/${matchId}/rollouts/${rolloutId}`);
                }}
              />
            ))}
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 40 }}>
          <span className="label-mono">no rollouts persisted for this match</span>
        </div>
      )}

      {/* Inconsistency flags */}
      {inconsistencyFlags.length > 0 && (
        <div
          style={{
            marginTop: 40,
            background: COLORS.accentSoft,
            padding: "24px 28px",
            borderLeft: `3px solid ${COLORS.accent}`,
          }}
        >
          <div className="label-mono" style={{ marginBottom: 10, color: COLORS.accent }}>
            Cross-validation flags
          </div>
          <div style={{ fontSize: 14, color: COLORS.muted, marginBottom: 16 }}>
            Signals that don't cleanly align between self-report and situational response.
          </div>
          {inconsistencyFlags.map((flag, i) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <div
                style={{
                  fontFamily: FONT_MONO,
                  fontSize: 12,
                  color: COLORS.accent,
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                  marginBottom: 4,
                }}
              >
                {flag.type}
              </div>
              <div style={{ fontSize: 15, lineHeight: 1.55 }}>{flag.note}</div>
            </div>
          ))}
        </div>
      )}

      {/* Methodology footer */}
      <div
        style={{
          marginTop: 40,
          paddingTop: 24,
          borderTop: `1px solid ${COLORS.rule}`,
          fontSize: 12,
          color: COLORS.muted,
          fontFamily: FONT_MONO,
          lineHeight: 1.8,
        }}
      >
        <div>
          {[
            auditTrailV2.kPerScenario != null && `K=${auditTrailV2.kPerScenario}`,
            auditTrailV2.scenariosRun != null &&
              `${auditTrailV2.scenariosRun} scenario${auditTrailV2.scenariosRun !== 1 ? "s" : ""}`,
            auditTrailV2.judgeModel && `judge=${auditTrailV2.judgeModel}`,
            auditTrailV2.judgeCount != null && `${auditTrailV2.judgeCount} judges/rollout`,
            auditTrailV2.proofLayer && `proof=${auditTrailV2.proofLayer}`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </div>
        {auditTrailV2.timestamp && <div>ts={auditTrailV2.timestamp}</div>}
      </div>

      {explainKey && (
        <ScoreExplainSheet
          dimensionKey={explainKey}
          criterionScores={criterionScores}
          dimensionalFit={dimensionalFit}
          criteriaIndex={criteriaIndex}
          onClose={() => setExplainKey(null)}
        />
      )}
    </div>
  );
}

// ===========================================================================
// Candidate strip — links + accuracy
// ===========================================================================
function CandidateStrip({ candidate }) {
  const [cvUrl, setCvUrl] = useState(null);

  useEffect(() => {
    if (!candidate?.cv_path) return;
    let cancelled = false;
    supabase.storage
      .from("cvs")
      .createSignedUrl(candidate.cv_path, 600)
      .then(({ data }) => {
        if (!cancelled && data?.signedUrl) setCvUrl(data.signedUrl);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [candidate?.cv_path]);

  if (!candidate) return null;

  const links = [
    { label: "CV", href: cvUrl, present: !!candidate.cv_path },
    { label: "LinkedIn", href: candidate.linkedin_url, present: !!candidate.linkedin_url },
    { label: "GitHub", href: candidate.github_url, present: !!candidate.github_url },
    { label: "Portfolio", href: candidate.portfolio_url, present: !!candidate.portfolio_url },
  ].filter((l) => l.present);

  if (links.length === 0 && !candidate.profile_accuracy_score) return null;

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 12,
        flexWrap: "wrap",
        padding: "12px 0",
        marginTop: 16,
        borderTop: `1px solid ${COLORS.rule}`,
        borderBottom: `1px solid ${COLORS.rule}`,
      }}
    >
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {links.map((l) =>
          l.href ? (
            <a
              key={l.label}
              href={l.href}
              target="_blank"
              rel="noreferrer"
              className="ghost"
              style={{
                padding: "6px 14px",
                fontSize: 11,
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              {l.label} <span aria-hidden>↗</span>
            </a>
          ) : (
            <span
              key={l.label}
              style={{
                padding: "6px 14px",
                fontSize: 11,
                fontFamily: FONT_MONO,
                letterSpacing: "0.15em",
                textTransform: "uppercase",
                color: COLORS.muted,
                border: `1px solid ${COLORS.rule}`,
              }}
            >
              {l.label}
            </span>
          )
        )}
      </div>
      <ProfileAccuracyChip value={candidate.profile_accuracy_score || 0} />
    </div>
  );
}

// ===========================================================================
// Tappable dimensional chart — clones DimensionalFitChart but rows are buttons
// ===========================================================================
function TappableDimensionalChart({ criterionScores, dimensionalFit, criteriaIndex, onTap }) {
  const keys =
    Object.keys(criteriaIndex).length > 0
      ? Object.keys(criteriaIndex)
      : Object.keys(criterionScores);

  return (
    <div>
      {keys.map((key) => {
        const val = criterionScores[key] || {};
        const dim = dimensionalFit?.[key];
        const meta = criteriaIndex[key];
        const mean = dim?.mean ?? val.score ?? 0;
        const std = dim?.std ?? 0;
        const score = val.score ?? mean;
        const agreement = dim?.judgeAgreement;

        return (
          <button
            key={key}
            onClick={() => onTap(key)}
            style={{
              display: "block",
              width: "100%",
              textAlign: "left",
              padding: "20px 0",
              border: "none",
              borderBottom: `1px solid ${COLORS.rule}`,
              background: "transparent",
              cursor: "pointer",
              color: "inherit",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                marginBottom: 6,
              }}
            >
              <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
                <div style={{ fontFamily: FONT_DISPLAY, fontSize: 20, fontWeight: 500 }}>
                  {meta?.label || formatCriterion(key)}
                </div>
                {meta && (
                  <span className="label-mono">weight {Math.round((meta.weight ?? 0) * 100)}%</span>
                )}
                {agreement != null && (
                  <span className="label-mono">agreement {agreement.toFixed(2)}</span>
                )}
                <span
                  className="label-mono"
                  style={{ color: COLORS.muted, opacity: 0.6 }}
                >
                  tap for why →
                </span>
              </div>
              <span
                style={{
                  fontFamily: FONT_MONO,
                  fontSize: 20,
                  fontWeight: 500,
                  minWidth: 48,
                  textAlign: "right",
                }}
              >
                {Math.round(score)}
              </span>
            </div>
            <VarianceBar mean={mean} std={std} height={8} showBand={dimensionalFit != null} />
          </button>
        );
      })}
    </div>
  );
}

// ===========================================================================
// Slide-up sheet explaining a single dimension's score
// ===========================================================================
function ScoreExplainSheet({
  dimensionKey,
  criterionScores,
  dimensionalFit,
  criteriaIndex,
  onClose,
}) {
  const val = criterionScores[dimensionKey] || {};
  const dim = dimensionalFit?.[dimensionKey];
  const meta = criteriaIndex[dimensionKey];
  const mean = dim?.mean ?? val.score ?? 0;
  const std = dim?.std ?? 0;
  const n = dim?.n;
  const justification = val.justification;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(26,24,20,0.55)",
        zIndex: 90,
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "center",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 680,
          background: COLORS.cardBg,
          padding: "24px 32px 32px",
          borderTop: `2px solid ${COLORS.ink}`,
          maxHeight: "70vh",
          overflowY: "auto",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <div>
            <div className="label-mono" style={{ marginBottom: 4 }}>
              Why this score
            </div>
            <div style={{ fontFamily: FONT_DISPLAY, fontSize: 26, fontWeight: 500 }}>
              {meta?.label || formatCriterion(dimensionKey)}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              fontSize: 28,
              color: COLORS.muted,
              lineHeight: 1,
            }}
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 16,
            marginBottom: 18,
          }}
        >
          <Metric label="Score" value={Math.round(mean)} />
          <Metric label="σ across rollouts" value={std.toFixed?.(1) ?? std} />
          <Metric label="Rollouts" value={n ?? "—"} />
        </div>

        {justification ? (
          <p
            style={{
              fontFamily: FONT_DISPLAY,
              fontSize: 17,
              lineHeight: 1.6,
              color: COLORS.ink,
              margin: "0 0 16px",
            }}
          >
            {justification}
          </p>
        ) : (
          <p style={{ color: COLORS.muted, fontStyle: "italic" }}>
            No justification recorded for this dimension.
          </p>
        )}

        {meta?.description && (
          <p style={{ color: COLORS.muted, fontSize: 14, lineHeight: 1.6, margin: 0 }}>
            <span className="label-mono">Rubric · </span>
            {meta.description}
          </p>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div
      style={{
        background: COLORS.paper,
        border: `1px solid ${COLORS.rule}`,
        padding: "10px 14px",
      }}
    >
      <div className="label-mono" style={{ marginBottom: 4 }}>
        {label}
      </div>
      <div
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 22,
          fontWeight: 500,
          color: COLORS.ink,
          lineHeight: 1,
        }}
      >
        {value}
      </div>
    </div>
  );
}

// ===========================================================================
// Dual-score headline — Roadmap 2 / PR #2d.3.
// Big overall number + the two components (Skills · Behaviour) below it.
// When skills_fit is null (no required_skills configured), shows behaviour
// alone with a small note; the overall == behaviour in that case.
// ===========================================================================
function DualScoreHeadline({ overall, behaviour, skills }) {
  return (
    <div style={{ textAlign: "right" }}>
      <div className="label-mono" style={{ marginBottom: 4 }}>
        Overall fit
      </div>
      <div
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 72,
          fontWeight: 500,
          lineHeight: 1,
          color: COLORS.accent,
          letterSpacing: "-0.03em",
        }}
      >
        {overall}
      </div>
      <div className="label-mono" style={{ marginBottom: 10 }}>of 100</div>

      {skills == null ? (
        <div
          style={{
            fontFamily: FONT_MONO,
            fontSize: 11,
            color: COLORS.muted,
            letterSpacing: "0.05em",
            maxWidth: 220,
            textAlign: "right",
          }}
        >
          behaviour-only · no required skills configured
        </div>
      ) : (
        <div
          style={{
            display: "flex",
            gap: 14,
            justifyContent: "flex-end",
            alignItems: "baseline",
          }}
        >
          <SubScore label="Skills" value={skills} />
          <span style={{ color: COLORS.muted, fontFamily: FONT_MONO }}>·</span>
          <SubScore label="Behaviour" value={behaviour} />
        </div>
      )}
    </div>
  );
}

function SubScore({ label, value }) {
  return (
    <div style={{ textAlign: "right" }}>
      <div
        className="label-mono"
        style={{ fontSize: 10, marginBottom: 2 }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 26,
          fontWeight: 500,
          lineHeight: 1,
          color: COLORS.ink,
        }}
      >
        {value}
      </div>
    </div>
  );
}
