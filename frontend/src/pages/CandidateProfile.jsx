import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { candidates } from "../api.js";

const _CID_KEY = "parallax:candidate-id";
const _getCandidateId = () => localStorage.getItem(_CID_KEY);
const _clearCandidateId = () => localStorage.removeItem(_CID_KEY);
import { GeneratingScreen, MiniBar, formatCriterion } from "../components/Widgets.jsx";

// Persistent, read-only view of the candidate's quiz results. Loaded by UUID
// from localStorage. No fit reports here — blind matching means the candidate
// never sees which companies they've been scored against unless and until the
// manager surfaces a match.

export default function CandidateProfile() {
  const nav = useNavigate();
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const id = _getCandidateId();
    if (!id) {
      nav("/intake", { replace: true });
      return;
    }
    candidates
      .get(id)
      .then(setProfile)
      .catch((e) => {
        if (e.status === 404) {
          // Stale localStorage pointing at a candidate the server no longer has.
          _clearCandidateId();
          nav("/intake", { replace: true });
        } else {
          setError(e.message);
        }
      });
  }, [nav]);

  if (error) {
    return (
      <main className="container">
        <div className="label-mono" style={{ color: COLORS.accent }}>Error loading profile</div>
        <p>{error}</p>
      </main>
    );
  }
  if (!profile) return <GeneratingScreen note="Loading your profile…" />;

  const persona = profile.persona;
  const created = new Date(profile.created_at);
  const updated = new Date(profile.updated_at);

  return (
    <main className="container">
      <div className="label-mono" style={{ marginBottom: 12 }}>Candidate · Persistent profile</div>
      <h2
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 44,
          fontWeight: 500,
          letterSpacing: "-0.015em",
          lineHeight: 1.1,
          margin: "0 0 8px",
        }}
      >
        Your behavioral persona.
      </h2>
      <p style={{ color: COLORS.muted, fontStyle: "italic", marginBottom: 8, fontSize: 17 }}>
        This is what we synthesized from your responses. It is not a score, and it is not a
        decision. Hiring managers see the simulation output, not this raw view.
      </p>
      <div className="label-mono" style={{ color: COLORS.muted, marginBottom: 24 }}>
        Submitted {created.toLocaleDateString()} · Last updated {updated.toLocaleDateString()}
      </div>
      <hr className="rule-thick" style={{ margin: "0 0 32px" }} />

      {persona ? (
        <>
          <div className="card" style={{ marginBottom: 32 }}>
            <div className="label-mono" style={{ marginBottom: 10 }}>Narrative summary</div>
            <div style={{ fontFamily: FONT_DISPLAY, fontSize: 22, fontStyle: "italic", lineHeight: 1.5 }}>
              {persona.narrative}
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, marginBottom: 32 }}>
            <div>
              <div className="label-mono" style={{ marginBottom: 10 }}>Big Five (BFI-10)</div>
              {Object.entries(persona.big_five).map(([k, v]) => (
                <MiniBar key={k} label={k} value={v} />
              ))}
              <div style={{ fontSize: 13, color: COLORS.muted, marginTop: 8 }}>
                Self-report. Reverse-scored where appropriate.
              </div>
            </div>
            <div>
              <div className="label-mono" style={{ marginBottom: 10 }}>SJT behavioral signals</div>
              {Object.entries(persona.sjt_signals).map(([k, v]) => (
                <MiniBar key={k} label={formatCriterion(k)} value={v} />
              ))}
              <div style={{ fontSize: 13, color: COLORS.muted, marginTop: 8 }}>
                Aggregated across the three scenarios.
              </div>
            </div>
          </div>

          {persona.inconsistencies?.length > 0 && (
            <div
              style={{
                background: COLORS.accentSoft,
                padding: "24px 28px",
                borderLeft: `3px solid ${COLORS.accent}`,
                marginBottom: 32,
              }}
            >
              <div className="label-mono" style={{ marginBottom: 10, color: COLORS.accent }}>
                Cross-validation notes
              </div>
              <div style={{ fontSize: 14, color: COLORS.muted, marginBottom: 16 }}>
                Signals that don't cleanly align between self-report and situational response.
                Neither good nor bad on their own — useful questions for a human interviewer.
              </div>
              {persona.inconsistencies.map((flag, i) => (
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
        </>
      ) : (
        <p>Persona not synthesized yet.</p>
      )}

      <div
        style={{
          marginTop: 40,
          paddingTop: 24,
          borderTop: `1px solid ${COLORS.rule}`,
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <button className="ghost" onClick={() => nav("/intake")}>Retake assessment</button>
        <button
          className="ghost"
          onClick={() => {
            if (confirm("Forget this profile on this browser?")) {
              _clearCandidateId();
              nav("/intake");
            }
          }}
        >
          Forget me on this browser
        </button>
      </div>

      <div
        style={{
          marginTop: 24,
          fontFamily: FONT_MONO,
          fontSize: 12,
          color: COLORS.muted,
        }}
      >
        candidate-id: {profile.id}
      </div>
    </main>
  );
}
