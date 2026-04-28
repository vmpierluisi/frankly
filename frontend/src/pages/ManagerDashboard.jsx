import React, { useEffect, useMemo, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { candidates, companies, matches } from "../api.js";
import { GeneratingScreen } from "../components/Widgets.jsx";
import SearchReport from "../components/SearchReport.jsx";
import FitMap3D from "../components/FitMap3D.jsx";

// Manager command surface — position-first batch matching.
//
// Flow:
//   1. Recruiter selects a position (company template) from the full-width list.
//   2. Clicks "Search candidates" → POST /matches/search scans the whole pool.
//   3. Results appear in two switchable views: Report | 3D map.
//   4. "Re-run all" forces fresh LLM calls (refresh=true) — useful after
//      criteria edits or when the pool has changed.

const VIEW_REPORT = "report";
const VIEW_MAP = "map";

export default function ManagerDashboard() {
  const nav = useNavigate();
  const [companyList, setCompanyList] = useState([]);
  const [seedCount, setSeedCount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selectedCompany, setSelectedCompany] = useState(null);
  const [companyDetail, setCompanyDetail] = useState(null);

  const [searching, setSearching] = useState(false);
  const [scanTick, setScanTick] = useState(0); // drives fake-scan animation
  const [searchResult, setSearchResult] = useState(null); // SearchMatchOut

  const [view, setView] = useState(VIEW_REPORT);

  const tickerRef = useRef(null);

  useEffect(() => {
    Promise.all([
      companies.list(),
      candidates.list({ is_seed: true }),
    ])
      .then(([cos, seeds]) => {
        setCompanyList(cos);
        setSeedCount(seeds.length);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Fetch full company detail (with criteria) whenever selection changes.
  useEffect(() => {
    if (!selectedCompany) { setCompanyDetail(null); return; }
    companies.get(selectedCompany).then(setCompanyDetail).catch(() => {});
  }, [selectedCompany]);

  // Reset results when a different company is selected.
  useEffect(() => {
    setSearchResult(null);
    setError("");
  }, [selectedCompany]);

  const criteriaIndex = useMemo(() => {
    if (!companyDetail) return {};
    return Object.fromEntries(
      companyDetail.criteria.map((c) => [c.key, { label: c.label, weight: c.weight }]),
    );
  }, [companyDetail]);

  // ---- Scan animation -------------------------------------------------------
  // While `searching` we tick a counter every 180ms so the scanning shimmer
  // feels live. The POST resolves in its own time; animation stops on result.
  function startTicker() {
    setScanTick(0);
    tickerRef.current = setInterval(() => setScanTick((n) => n + 1), 180);
  }
  function stopTicker() {
    clearInterval(tickerRef.current);
    tickerRef.current = null;
  }

  async function runSearch(refresh = false) {
    if (!selectedCompany) return;
    setError("");
    setSearchResult(null);
    setSearching(true);
    startTicker();
    try {
      const result = await matches.search(selectedCompany, { refresh });
      setSearchResult(result);
      setView(VIEW_REPORT);
    } catch (e) {
      setError(`Search failed: ${e.message}`);
    } finally {
      stopTicker();
      setSearching(false);
    }
  }

  if (loading) return <GeneratingScreen note="Loading dashboard…" />;

  const company = companyList.find((c) => c.id === selectedCompany);

  return (
    <main className="container" style={{ maxWidth: 1280 }}>
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
        Select a role. Search the candidate pool. Explore who fits and why.
      </h2>
      <p style={{ color: COLORS.muted, fontStyle: "italic", marginBottom: 32, fontSize: 17 }}>
        Screening signal only — not a hiring decision. Use the scores as a
        prompt for interview, not a substitute for one.
      </p>
      <hr className="rule-thick" style={{ margin: "0 0 32px" }} />

      {/* ── Positions list ─────────────────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div className="label-mono">Positions ({companyList.length})</div>
          {seedCount !== null && seedCount > 0 && (
            <div
              style={{
                fontFamily: FONT_MONO,
                fontSize: 10,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: COLORS.muted,
                border: `1px solid ${COLORS.rule}`,
                padding: "2px 8px",
              }}
            >
              Seeded: {seedCount}
            </div>
          )}
        </div>
        <button
          className="ghost"
          onClick={() => nav("/manager/templates")}
          style={{ padding: "8px 14px" }}
        >
          + New position
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 8, marginBottom: 28 }}>
        {companyList.map((c) => (
          <PositionCard
            key={c.id}
            company={c}
            selected={selectedCompany === c.id}
            onSelect={() => setSelectedCompany(c.id)}
            onEdit={(e) => { e.stopPropagation(); nav(`/manager/templates/${c.id}`); }}
            onViewTeam={(e) => { e.stopPropagation(); nav(`/manager/companies/${c.id}/team`); }}
          />
        ))}
        {companyList.length === 0 && (
          <p style={{ color: COLORS.muted, fontSize: 14, gridColumn: "1/-1" }}>
            No positions yet. Create one with "+ New position".
          </p>
        )}
      </div>

      {/* ── Action bar ─────────────────────────────────────────────────────── */}
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
        <div style={{ flex: 1, minWidth: 240 }}>
          {company ? (
            <>
              <div className="label-mono" style={{ marginBottom: 4 }}>Selected position</div>
              <div style={{ fontFamily: FONT_DISPLAY, fontSize: 20, fontWeight: 500 }}>
                {company.name}
              </div>
              <div style={{ color: COLORS.muted, fontSize: 14 }}>{company.role}</div>
            </>
          ) : (
            <div style={{ color: COLORS.muted, fontStyle: "italic" }}>
              — select a position above —
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {selectedCompany && (
            <button
              className="ghost"
              onClick={() => nav(`/manager/companies/${selectedCompany}/team`)}
              style={{ padding: "14px 20px" }}
            >
              View team
            </button>
          )}
          <button
            className="primary"
            onClick={() => runSearch(false)}
            disabled={!selectedCompany || searching}
          >
            {searching ? "Searching…" : "Search candidates →"}
          </button>
          {searchResult && (
            <button
              className="ghost"
              onClick={() => runSearch(true)}
              disabled={searching}
              style={{ padding: "14px 20px" }}
            >
              Re-run all
            </button>
          )}
        </div>
      </div>

      {error && (
        <div style={{ color: COLORS.accent, marginBottom: 24, fontStyle: "italic" }}>{error}</div>
      )}

      {/* ── Search simulation animation ─────────────────────────────────────── */}
      {searching && (
        <ScanAnimation tick={scanTick} />
      )}

      {/* ── Results ────────────────────────────────────────────────────────── */}
      {searchResult && !searching && (
        <>
          {/* View switcher */}
          <div
            style={{
              display: "flex",
              gap: 0,
              marginBottom: 24,
              borderBottom: `2px solid ${COLORS.ink}`,
              width: "fit-content",
            }}
          >
            {[
              { id: VIEW_REPORT, label: "Report" },
              { id: VIEW_MAP, label: "3D map" },
            ].map(({ id, label }) => (
              <button
                key={id}
                onClick={() => setView(id)}
                style={{
                  background: "transparent",
                  border: "none",
                  borderBottom: `3px solid ${view === id ? COLORS.ink : "transparent"}`,
                  marginBottom: -2,
                  padding: "10px 24px",
                  fontFamily: FONT_MONO,
                  fontSize: 11,
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                  color: view === id ? COLORS.ink : COLORS.muted,
                  cursor: "pointer",
                  transition: "color 0.15s, border-color 0.15s",
                }}
              >
                {label}
              </button>
            ))}
          </div>

          {view === VIEW_REPORT && (
            <SearchReport search={searchResult} criteriaIndex={criteriaIndex} />
          )}
          {view === VIEW_MAP && (
            <FitMap3D search={searchResult} criteriaIndex={criteriaIndex} />
          )}
        </>
      )}
    </main>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────────

function PositionCard({ company, selected, onSelect, onEdit, onViewTeam }) {
  return (
    <div
      onClick={onSelect}
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: 10,
        padding: "14px 16px",
        border: `1px solid ${selected ? COLORS.ink : COLORS.rule}`,
        background: selected ? "#fff" : "transparent",
        cursor: "pointer",
        transition: "border 0.15s, background 0.15s",
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: FONT_DISPLAY, fontSize: 18, fontWeight: 500 }}>
          {company.name}
        </div>
        <div style={{ color: COLORS.muted, fontSize: 13 }}>{company.role}</div>
        {company.tagline && (
          <div style={{ color: COLORS.muted, fontSize: 12, fontStyle: "italic", marginTop: 2 }}>
            {company.tagline}
          </div>
        )}
      </div>
      <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
        <button
          className="ghost"
          style={{ padding: "4px 10px", fontSize: 11, whiteSpace: "nowrap" }}
          onClick={onViewTeam}
        >
          Team
        </button>
        <button
          className="ghost"
          style={{ padding: "4px 10px", fontSize: 11, whiteSpace: "nowrap" }}
          onClick={onEdit}
        >
          Edit
        </button>
      </div>
    </div>
  );
}

// Animated scan that plays while the search POST is in flight.
// A ticker cycling through fake "scanning candidate…" lines gives the
// feeling of live progress — the real batch runs server-side in parallel.
const SCAN_LABELS = [
  "Synthesising personas…",
  "Running matcher against criteria…",
  "Projecting fit axes…",
  "Cross-validating signals…",
  "Ranking candidates…",
  "Resolving inconsistency flags…",
  "Comparing culture alignment…",
  "Weighting role-specific criteria…",
  "Computing absolute fit scores…",
  "Sorting by overall band…",
];

function ScanAnimation({ tick }) {
  const line = SCAN_LABELS[tick % SCAN_LABELS.length];
  return (
    <div
      style={{
        padding: "48px 0",
        textAlign: "center",
        borderTop: `1px solid ${COLORS.rule}`,
        borderBottom: `1px solid ${COLORS.rule}`,
        marginBottom: 32,
      }}
    >
      <div className="label-mono" style={{ marginBottom: 18 }}>
        <span className="pulse-dot" />
        &nbsp;
        <span className="pulse-dot" />
        &nbsp;
        <span className="pulse-dot" />
      </div>
      <div
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 26,
          fontStyle: "italic",
          color: COLORS.muted,
          transition: "opacity 0.2s",
        }}
      >
        {line}
      </div>
    </div>
  );
}
