import React, { useEffect, useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../../design.js";
import { candidates as candidatesApi } from "../../api.js";

// Manager Shortlist V7 — floating-window CV viewer.
// Pulls the candidate's verified profile (experience / education / skills).
export default function CVModal({ candidateId, name, onClose }) {
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    candidatesApi
      .getCandidateProfile(candidateId)
      .then((p) => alive && setProfile(p))
      .catch((e) => alive && setError(e.message || String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [candidateId]);

  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1100,
        background: "rgba(26,24,20,0.35)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`${name || "Candidate"} CV`}
        style={{
          background: "#fff",
          border: `1px solid ${COLORS.ink}`,
          width: "min(680px, 100%)",
          maxHeight: "85vh",
          overflowY: "auto",
          boxShadow: "0 12px 48px rgba(0,0,0,0.25)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "18px 24px",
            borderBottom: `2px solid ${COLORS.ink}`,
            position: "sticky",
            top: 0,
            background: "#fff",
          }}
        >
          <div>
            <div className="label-mono" style={{ fontFamily: FONT_MONO, fontSize: 10 }}>
              Verified profile
            </div>
            <div style={{ fontFamily: FONT_DISPLAY, fontSize: 24, fontWeight: 500 }}>
              {name || "Candidate"}
            </div>
          </div>
          <button className="ghost" onClick={onClose} style={{ padding: "8px 14px" }}>
            Close
          </button>
        </div>

        <div style={{ padding: "20px 24px" }}>
          {loading && <p style={{ color: COLORS.muted, fontStyle: "italic" }}>Loading…</p>}
          {error && <p style={{ color: COLORS.accent, fontStyle: "italic" }}>{error}</p>}
          {profile && (
            <>
              <Section title="Experience">
                {(profile.experience || []).map((e, i) => (
                  <Entry
                    key={i}
                    head={[e.title, e.company].filter(Boolean).join(" · ")}
                    sub={[e.start, e.end].filter(Boolean).join(" – ")}
                    body={e.summary || e.description}
                  />
                ))}
              </Section>
              <Section title="Education">
                {(profile.education || []).map((e, i) => (
                  <Entry
                    key={i}
                    head={[e.degree, e.institution || e.school].filter(Boolean).join(" · ")}
                    sub={e.year || [e.start, e.end].filter(Boolean).join(" – ")}
                  />
                ))}
              </Section>
              <Section title="Skills">
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {(profile.skills || []).map((s, i) => (
                    <span
                      key={i}
                      style={{
                        fontFamily: FONT_MONO,
                        fontSize: 11,
                        border: `1px solid ${COLORS.rule}`,
                        padding: "3px 8px",
                      }}
                    >
                      {typeof s === "string" ? s : s.skill || s.name}
                    </span>
                  ))}
                </div>
              </Section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  const empty =
    !children ||
    (Array.isArray(children) && children.every((c) => !c)) ||
    (Array.isArray(children) && children.length === 0);
  return (
    <section style={{ marginBottom: 22 }}>
      <div
        className="label-mono"
        style={{ fontFamily: FONT_MONO, fontSize: 10, marginBottom: 10 }}
      >
        {title}
      </div>
      {empty ? (
        <p style={{ color: COLORS.muted, fontStyle: "italic", fontSize: 14 }}>Not provided.</p>
      ) : (
        children
      )}
    </section>
  );
}

function Entry({ head, sub, body }) {
  if (!head && !sub && !body) return null;
  return (
    <div style={{ marginBottom: 14, borderTop: `1px solid ${COLORS.rule}`, paddingTop: 10 }}>
      {head && <div style={{ fontFamily: FONT_DISPLAY, fontSize: 17, fontWeight: 500 }}>{head}</div>}
      {sub && <div style={{ fontFamily: FONT_MONO, fontSize: 11, color: COLORS.muted }}>{sub}</div>}
      {body && <p style={{ fontSize: 14, margin: "6px 0 0" }}>{body}</p>}
    </div>
  );
}
