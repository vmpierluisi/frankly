import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { candidates, companies, matches } from "../api.js";
import { GeneratingScreen, MiniBar, formatCriterion } from "../components/Widgets.jsx";
import FitReport from "../components/FitReport.jsx";

// Manager-only command surface. Three columns of work:
//   1. Companies — the template library; click to edit
//   2. Candidates — anonymized list with narrative summary
//   3. Match — pick a candidate × company, run the matcher, view the report

export default function ManagerDashboard() {
  const nav = useNavigate();
  const [companyList, setCompanyList] = useState([]);
  const [candidateList, setCandidateList] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [matching, setMatching] = useState(false);
  const [report, setReport] = useState(null);
  const [companyDetail, setCompanyDetail] = useState(null);
  const [candidatePersona, setCandidatePersona] = useState(null);

  useEffect(() => {
    Promise.all([companies.list(), candidates.list()])
      .then(([cs, ks]) => {
        setCompanyList(cs);
        setCandidateList(ks);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Whenever the selected candidate changes, fetch their persona so we can show
  // the manager what they're matching against.
  useEffect(() => {
    if (!selectedCandidate) {
      setCandidatePersona(null);
      return;
    }
    candidates.get(selectedCandidate).then((c) => setCandidatePersona(c.persona));
  }, [selectedCandidate]);

  // Cache full company detail (with criteria) so FitReport can show weight chips.
  useEffect(() => {
    if (!selectedCompany) {
      setCompanyDetail(null);
      return;
    }
    companies.get(selectedCompany).then(setCompanyDetail);
  }, [selectedCompany]);

  const criteriaIndex = useMemo(() => {
    if (!companyDetail) return {};
    return Object.fromEntries(
      companyDetail.criteria.map((c) => [c.key, { label: c.label, weight: c.weight }]),
    );
  }, [companyDetail]);

  async function runMatch() {
    if (!selectedCandidate || !selectedCompany) return;
    setError("");
    setMatching(true);
    setReport(null);
    try {
      const m = await matches.trigger(selectedCandidate, selectedCompany);
      setReport(m.report);
    } catch (e) {
      setError(`Match failed: ${e.message}`);
    } finally {
      setMatching(false);
    }
  }

  if (loading) return <GeneratingScreen note="Loading dashboard…" />;

  return (
    <main className="container" style={{ maxWidth: 1200 }}>
      <div className="label-mono" style={{ marginBottom: 12 }}>Manager · Dashboard</div>
      <h2
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 40,
          fontWeight: 500,
          letterSpacing: "-0.015em",
          lineHeight: 1.1,
          margin: "0 0 8px",
        }}
      >
        Pick a candidate. Pick an environment. See how they would behave inside it.
      </h2>
      <p style={{ color: COLORS.muted, fontStyle: "italic", marginBottom: 32, fontSize: 17 }}>
        This is screening — not a hiring decision. Use these scores as a prompt for
        interview, not a substitute for one.
      </p>
      <hr className="rule-thick" style={{ margin: "0 0 32px" }} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, marginBottom: 40 }}>
        {/* Companies column */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
            <div className="label-mono">Templates ({companyList.length})</div>
            <button className="ghost" onClick={() => nav("/manager/templates")} style={{ padding: "8px 14px" }}>
              + New
            </button>
          </div>
          {companyList.map((c) => (
            <Row
              key={c.id}
              selected={selectedCompany === c.id}
              onClick={() => setSelectedCompany(c.id)}
            >
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: FONT_DISPLAY, fontSize: 19, fontWeight: 500 }}>{c.name}</div>
                <div style={{ color: COLORS.muted, fontSize: 14 }}>{c.role}</div>
                {c.tagline && (
                  <div style={{ color: COLORS.muted, fontSize: 13, fontStyle: "italic", marginTop: 2 }}>
                    {c.tagline}
                  </div>
                )}
              </div>
              <button
                className="ghost"
                style={{ padding: "6px 12px" }}
                onClick={(e) => {
                  e.stopPropagation();
                  nav(`/manager/templates/${c.id}`);
                }}
              >
                Edit
              </button>
            </Row>
          ))}
          {companyList.length === 0 && (
            <p style={{ color: COLORS.muted, fontSize: 14 }}>No companies yet. Create one.</p>
          )}
        </div>

        {/* Candidates column */}
        <div>
          <div className="label-mono" style={{ marginBottom: 12 }}>Candidates ({candidateList.length})</div>
          {candidateList.map((c) => (
            <Row
              key={c.id}
              selected={selectedCandidate === c.id}
              onClick={() => setSelectedCandidate(c.id)}
            >
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: FONT_MONO, fontSize: 12, color: COLORS.muted }}>
                  {c.id.slice(0, 8)}
                </div>
                <div
                  style={{
                    fontFamily: FONT_DISPLAY,
                    fontSize: 16,
                    fontStyle: "italic",
                    color: COLORS.ink,
                    lineHeight: 1.4,
                    marginTop: 2,
                  }}
                >
                  {c.narrative || "(persona not synthesized)"}
                </div>
                <div style={{ color: COLORS.muted, fontSize: 12, marginTop: 4 }}>
                  Submitted {new Date(c.created_at).toLocaleDateString()}
                </div>
              </div>
            </Row>
          ))}
          {candidateList.length === 0 && (
            <p style={{ color: COLORS.muted, fontSize: 14 }}>
              No candidates yet. Have someone go through /intake first.
            </p>
          )}
        </div>
      </div>

      {/* Match action row */}
      <div
        className="card"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
          marginBottom: 32,
          flexWrap: "wrap",
        }}
      >
        <div style={{ flex: 1, minWidth: 280 }}>
          <div className="label-mono" style={{ marginBottom: 4 }}>Selection</div>
          <div style={{ fontSize: 15, color: COLORS.muted }}>
            <span style={{ color: COLORS.ink }}>
              {selectedCandidate ? selectedCandidate.slice(0, 8) : "— no candidate —"}
            </span>
            {"  ×  "}
            <span style={{ color: COLORS.ink }}>
              {selectedCompany || "— no company —"}
            </span>
          </div>
        </div>
        <button
          className="primary"
          onClick={runMatch}
          disabled={!selectedCandidate || !selectedCompany || matching}
        >
          {matching ? "Running matcher…" : "Run match →"}
        </button>
      </div>

      {/* Persona preview */}
      {candidatePersona && (
        <div className="card" style={{ marginBottom: 32 }}>
          <div className="label-mono" style={{ marginBottom: 10 }}>Selected candidate · persona</div>
          <div
            style={{
              fontFamily: FONT_DISPLAY,
              fontSize: 19,
              fontStyle: "italic",
              lineHeight: 1.5,
              marginBottom: 20,
            }}
          >
            {candidatePersona.narrative}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
            <div>
              <div className="label-mono" style={{ marginBottom: 8 }}>Big Five</div>
              {Object.entries(candidatePersona.big_five).map(([k, v]) => (
                <MiniBar key={k} label={k} value={v} />
              ))}
            </div>
            <div>
              <div className="label-mono" style={{ marginBottom: 8 }}>SJT signals</div>
              {Object.entries(candidatePersona.sjt_signals).map(([k, v]) => (
                <MiniBar key={k} label={formatCriterion(k)} value={v} />
              ))}
            </div>
          </div>
        </div>
      )}

      {error && (
        <div style={{ color: COLORS.accent, marginBottom: 24, fontStyle: "italic" }}>{error}</div>
      )}

      {matching && <GeneratingScreen note="Running persona against environment…" />}

      {report && !matching && (
        <div style={{ marginTop: 16 }}>
          <FitReport report={report} criteriaIndex={criteriaIndex} />

          {/* Notification stub */}
          <div
            style={{
              marginTop: 40,
              textAlign: "center",
              padding: "32px 0",
              borderTop: `2px solid ${COLORS.ink}`,
            }}
          >
            <div style={{ fontFamily: FONT_DISPLAY, fontSize: 22, fontStyle: "italic", marginBottom: 20 }}>
              In production, this is where the candidate and the manager would each receive a
              notification — and an interview happens only if both opt in.
            </div>
            <button
              className="primary"
              style={{ marginRight: 12 }}
              onClick={() => alert("Notification stub — wire SendGrid/Postmark in v1.")}
            >
              Notify both parties
            </button>
            <button className="ghost" onClick={() => setReport(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}
    </main>
  );
}

function Row({ selected, onClick, children }) {
  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "14px 16px",
        marginBottom: 8,
        border: `1px solid ${selected ? COLORS.ink : COLORS.rule}`,
        background: selected ? "#fff" : "transparent",
        cursor: "pointer",
        transition: "border 0.15s, background 0.15s",
      }}
    >
      {children}
    </div>
  );
}
