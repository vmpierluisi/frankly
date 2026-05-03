import React from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";

/**
 * Read-only render of the public VerifiedProfile shape:
 *   { education: [...], experience: [...], skills: [...], github_repos: [...] }
 *
 * Skills appear as small chips. Experience and education render as a list
 * with role/company/dates. Voice samples and ledger internals are NEVER
 * shown (per ROADMAP_2: gaming risk). Used by candidate Overview tab and
 * recruiter FitProfile v3.
 *
 * `compact` mode trims to a single column for the FitProfile expansion
 * sheet; default mode is comfortable, two-column on wider screens.
 */
export default function VerifiedProfileView({
  profile,
  compact = false,
  onEditSkills = null, // optional callback (compact mode hides the edit affordance)
}) {
  if (!profile) {
    return (
      <div style={{ color: COLORS.muted, fontStyle: "italic" }}>
        No verified profile yet — extraction not run.
      </div>
    );
  }

  const { skills = [], experience = [], education = [], github_repos = [] } = profile;

  // CSS multi-column packs sections tightly (masonry-ish) so a tall
  // Experience block doesn't leave dead space beside Skills. Each
  // <Section> stays intact via `break-inside: avoid`. Compact mode
  // (FitProfile expansion sheet) renders single-column.
  const containerStyle = compact
    ? { display: "flex", flexDirection: "column", gap: 28 }
    : { columnCount: 2, columnGap: 28 };
  const sectionStyle = compact
    ? undefined
    : {
        breakInside: "avoid",
        WebkitColumnBreakInside: "avoid",
        pageBreakInside: "avoid",
        marginBottom: 28,
        display: "block",
      };

  return (
    <div style={containerStyle}>
      <Section
        title="Skills"
        style={sectionStyle}
        actionLabel={onEditSkills ? "Edit" : null}
        onAction={onEditSkills}
      >
        {skills.length === 0 ? (
          <Empty>No skills extracted yet.</Empty>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {skills.map((s, i) => (
              <SkillChip key={i} skill={s} />
            ))}
          </div>
        )}
      </Section>

      <Section title="Experience" style={sectionStyle}>
        {experience.length === 0 ? (
          <Empty>No experience entries yet.</Empty>
        ) : (
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {experience.map((e, i) => (
              <li key={i} style={{ marginBottom: 14 }}>
                <div style={{ fontFamily: FONT_DISPLAY, fontSize: 17, fontWeight: 500 }}>
                  {e.role || "Role"}{" "}
                  {e.company && (
                    <span style={{ color: COLORS.muted, fontWeight: 400 }}>
                      @ {e.company}
                    </span>
                  )}
                </div>
                <div
                  style={{
                    fontFamily: FONT_MONO,
                    fontSize: 11,
                    color: COLORS.muted,
                    letterSpacing: "0.05em",
                  }}
                >
                  {[e.start, e.end].filter(Boolean).join(" – ") || ""}
                </div>
                {Array.isArray(e.bullets) && e.bullets.length > 0 && (
                  <ul
                    style={{
                      margin: "6px 0 0 18px",
                      padding: 0,
                      color: COLORS.ink,
                      fontSize: 14,
                      lineHeight: 1.5,
                    }}
                  >
                    {e.bullets.slice(0, 3).map((b, bi) => (
                      <li key={bi}>{b}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Education" style={sectionStyle}>
        {education.length === 0 ? (
          <Empty>No education entries yet.</Empty>
        ) : (
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {education.map((e, i) => (
              <li key={i} style={{ marginBottom: 12 }}>
                <div style={{ fontFamily: FONT_DISPLAY, fontSize: 17, fontWeight: 500 }}>
                  {e.institution || "Institution"}
                </div>
                <div style={{ color: COLORS.muted, fontSize: 14 }}>
                  {[e.degree, e.field].filter(Boolean).join(" · ")}
                </div>
                <div
                  style={{
                    fontFamily: FONT_MONO,
                    fontSize: 11,
                    color: COLORS.muted,
                    letterSpacing: "0.05em",
                  }}
                >
                  {[e.start, e.end].filter(Boolean).join(" – ")}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="GitHub repos" style={sectionStyle}>
        {github_repos.length === 0 ? (
          <Empty>No GitHub repos linked.</Empty>
        ) : (
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {github_repos.slice(0, 6).map((r, i) => (
              <li key={i} style={{ marginBottom: 10 }}>
                <div style={{ fontFamily: FONT_DISPLAY, fontSize: 16, fontWeight: 500 }}>
                  {r.name || "Repo"}
                  {r.language && (
                    <span style={{ color: COLORS.muted, fontWeight: 400, fontSize: 13 }}>
                      {" · "}
                      {r.language}
                    </span>
                  )}
                </div>
                {r.description && (
                  <div style={{ color: COLORS.muted, fontSize: 13, lineHeight: 1.4 }}>
                    {r.description}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

function Section({ title, children, actionLabel = null, onAction = null, style = null }) {
  return (
    <div style={style || undefined}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <div className="label-mono">{title}</div>
        {actionLabel && (
          <button
            onClick={onAction}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              fontFamily: FONT_MONO,
              fontSize: 10,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: COLORS.muted,
              padding: 0,
            }}
          >
            {actionLabel} →
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

function Empty({ children }) {
  return (
    <div style={{ color: COLORS.muted, fontSize: 14, fontStyle: "italic" }}>
      {children}
    </div>
  );
}

function SkillChip({ skill }) {
  // skill can be a string OR an object {name, source_count, ...}.
  const name = typeof skill === "string" ? skill : skill?.name || "";
  const sourceCount = typeof skill === "object" ? skill?.source_count : null;
  return (
    <span
      title={
        sourceCount != null
          ? `Documented in ${sourceCount} source${sourceCount === 1 ? "" : "s"}`
          : null
      }
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "5px 12px",
        border: `1px solid ${COLORS.rule}`,
        background: COLORS.cardBg,
        fontFamily: FONT_MONO,
        fontSize: 12,
        color: COLORS.ink,
      }}
    >
      {name}
      {sourceCount != null && sourceCount > 1 && (
        <span style={{ color: COLORS.muted, fontSize: 10 }}>
          ×{sourceCount}
        </span>
      )}
    </span>
  );
}
