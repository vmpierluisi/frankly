import React, { forwardRef, useCallback, useImperativeHandle, useRef, useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO, candidateColor } from "../../design.js";
import PassedOverFlag from "./PassedOverFlag.jsx";

// Manager Shortlist V7 — Scenarios tab.
// One block per scenario: prompt + a response card per active candidate. The
// top active response gets a green border + badge. A PassedOverFlag surfaces
// below the row when an also-considered candidate beat every active response.
//
// Exposes flashCandidate(candidateId, scenarioId) via ref — called when the
// manager arrives here from an Overview cell's "See in scenario".
const ScenarioComparison = forwardRef(function ScenarioComparison(
  { report, onAddPassed },
  ref,
) {
  const { scenarios, candidates, available_candidates: available, position } = report;
  const [flash, setFlash] = useState(null); // {candidateId, scenarioId}
  const blockRefs = useRef({});

  useImperativeHandle(ref, () => ({
    flashCandidate(candidateId, scenarioId) {
      setFlash({ candidateId, scenarioId });
      const el = blockRefs.current[scenarioId];
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(() => setFlash(null), 1600);
    },
  }));

  const skillLabel = useCallback(
    (skillId) => position.skills.find((s) => s.id === skillId)?.label || skillId,
    [position.skills],
  );

  if (!scenarios.length) {
    return (
      <div style={{ padding: "48px 0", color: COLORS.muted, fontStyle: "italic" }}>
        No scenarios recorded for this position.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 40 }}>
      {scenarios.map((sc, i) => {
        const activeScores = candidates
          .map((c) => c.responses[sc.id]?.score ?? null)
          .filter((s) => s != null);
        const topActive = activeScores.length ? Math.max(...activeScores) : null;

        // Passed-over: any available candidate strictly beating every active one.
        const passedOver = available
          .map((c) => ({ c, score: c.responses[sc.id]?.score ?? null }))
          .filter((x) => x.score != null && topActive != null && x.score > topActive)
          .sort((a, b) => b.score - a.score)[0];

        return (
          <section
            key={sc.id}
            ref={(el) => (blockRefs.current[sc.id] = el)}
          >
            <div className="label-mono" style={{ fontFamily: FONT_MONO, fontSize: 10 }}>
              Scenario {String(i + 1).padStart(2, "0")}
              {sc.eyebrow ? ` · ${sc.eyebrow}` : ""}
            </div>
            <h3 style={{ fontFamily: FONT_DISPLAY, fontSize: 26, fontWeight: 500, margin: "4px 0 12px" }}>
              {sc.title}
            </h3>

            {sc.prompt && (
              <div
                style={{
                  background: COLORS.ink,
                  color: COLORS.paper,
                  padding: "16px 20px",
                  fontStyle: "italic",
                  fontSize: 16,
                  marginBottom: 18,
                }}
              >
                {sc.who && (
                  <div
                    style={{
                      fontFamily: FONT_MONO,
                      fontSize: 10,
                      letterSpacing: "0.16em",
                      textTransform: "uppercase",
                      opacity: 0.7,
                      marginBottom: 6,
                      fontStyle: "normal",
                    }}
                  >
                    {sc.who}
                  </div>
                )}
                {sc.prompt}
              </div>
            )}

            <div
              style={{
                display: "grid",
                gridTemplateColumns: `repeat(${candidates.length}, minmax(240px, 1fr))`,
                gap: 14,
                overflowX: "auto",
              }}
            >
              {candidates.map((c) => {
                const resp = c.responses[sc.id];
                const isTop = resp && resp.score === topActive && topActive != null;
                const isFlash =
                  flash && flash.candidateId === c.id && flash.scenarioId === sc.id;
                const color = candidateColor(c.palette_color_var);
                return (
                  <div
                    key={c.id}
                    style={{
                      border: isTop ? `2px solid #3f7a34` : `1px solid ${COLORS.rule}`,
                      background: isFlash ? COLORS.accentSoft : "#fff",
                      padding: "16px 18px",
                      transition: "background 0.4s ease",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                      <span style={{ fontFamily: FONT_DISPLAY, fontSize: 18, fontWeight: 500, color }}>
                        {c.anchor_short || c.name}
                      </span>
                      <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: COLORS.muted }}>
                        {resp?.score ?? "—"}/100
                      </span>
                    </div>
                    {isTop && (
                      <div
                        style={{
                          fontFamily: FONT_MONO,
                          fontSize: 9,
                          letterSpacing: "0.14em",
                          textTransform: "uppercase",
                          color: "#3f7a34",
                          margin: "4px 0 8px",
                        }}
                      >
                        Top of shortlist
                      </div>
                    )}
                    <p style={{ fontStyle: "italic", fontSize: 15, margin: "10px 0 0", lineHeight: 1.5 }}>
                      {resp?.text ? `“${resp.text}”` : "No recorded response."}
                    </p>
                    {resp?.skills_shown?.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
                        {resp.skills_shown.map((sid) => (
                          <span
                            key={sid}
                            style={{
                              fontFamily: FONT_MONO,
                              fontSize: 10,
                              border: `1px solid ${COLORS.rule}`,
                              padding: "2px 7px",
                              color: COLORS.muted,
                            }}
                          >
                            {skillLabel(sid)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {passedOver && (
              <PassedOverFlag
                candidate={passedOver.c}
                scenarioTitle={sc.title}
                score={passedOver.score}
                beatBy={topActive != null ? passedOver.score - topActive : null}
                onAdd={onAddPassed}
              />
            )}
          </section>
        );
      })}
    </div>
  );
});

export default ScenarioComparison;
