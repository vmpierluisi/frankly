import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { candidates, interviews as interviewsApi } from "../api.js";
import { supabase } from "../lib/supabase.js";
import { useAuth } from "../lib/auth.js";
import {
  ROLE_FAMILIES,
  SENIORITY_LEVELS,
  ROLE_FAMILY_BY_VALUE,
  SENIORITY_BY_VALUE,
} from "../lib/roleFamilies.js";
import { GeneratingScreen } from "../components/Widgets.jsx";
import Tabs from "../components/Tabs.jsx";
import NotificationBell from "../components/NotificationBell.jsx";
import ProfileAccuracyRing from "../components/ProfileAccuracyRing.jsx";
import VerifiedProfileView from "../components/VerifiedProfileView.jsx";
import VerifiedProfileEditor from "../components/VerifiedProfileEditor.jsx";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "matches", label: "Matches" },
  { id: "settings", label: "Settings" },
];

// Until PR #5 calibration sets a "real" profile_accuracy_score, derive a
// best-effort baseline from extraction completeness so the ring isn't
// stuck at 0% the moment a candidate adds a CV / GitHub / etc. The
// displayed value is the max of (server-stored calibration score,
// extraction-derived baseline) — once calibration data flows in, it
// dominates.
function deriveBaselineAccuracy(profile, verified) {
  let pts = 0;
  if (profile.cv_path) pts += 18;
  if (profile.github_url) pts += 18;
  if (profile.linkedin_url) pts += 12;
  if (profile.portfolio_url) pts += 12;
  if (profile.assessment_status === "completed") pts += 25;
  // Quality bonus: if extraction actually produced structured rows.
  if (verified) {
    const exp = (verified.experience || []).length;
    const edu = (verified.education || []).length;
    const skills = (verified.skills || []).length;
    if (exp + edu + skills > 0) pts += 10;
    if (exp + edu + skills > 8) pts += 5;
  }
  return Math.min(100, pts);
}

export default function CandidateDashboard() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [profile, setProfile] = useState(null);
  const [verified, setVerified] = useState(null);
  const [verifiedError, setVerifiedError] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState("overview");

  useEffect(() => {
    candidates
      .me()
      .then(setProfile)
      .catch((e) => setError(e.message));
  }, []);

  // Verified profile loads independently — 404 is expected before extraction.
  // If the candidate has at least one source attached but no verified profile
  // yet, kick off extraction automatically. Without this the ring sits at
  // baseline-only and Experience/Education never populate even though the
  // user uploaded a CV / linked their GitHub.
  const [autoExtracting, setAutoExtracting] = useState(false);
  const autoExtractedRef = useRef(false);

  useEffect(() => {
    if (!profile) return;
    candidates
      .getProfile()
      .then(setVerified)
      .catch(async (e) => {
        if (e.status === 404) {
          setVerified(null);
          const hasSources =
            !!profile.cv_path ||
            !!profile.github_url ||
            !!profile.portfolio_url ||
            !!profile.linkedin_url;
          if (hasSources && !autoExtractedRef.current) {
            autoExtractedRef.current = true;
            setAutoExtracting(true);
            try {
              const v = await candidates.extractProfile();
              setVerified(v);
            } catch (extractErr) {
              setVerifiedError(extractErr.message);
            } finally {
              setAutoExtracting(false);
            }
          }
        } else {
          setVerifiedError(e.message);
        }
      });
  }, [profile]);

  async function patchProfile(fields) {
    setSaving(true);
    try {
      const updated = await candidates.updateMe(fields);
      setProfile(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function reExtract() {
    setSaving(true);
    setVerifiedError("");
    try {
      const v = await candidates.extractProfile();
      setVerified(v);
    } catch (e) {
      setVerifiedError(e.message);
    } finally {
      setSaving(false);
    }
  }

  const [editing, setEditing] = useState(false);
  async function saveVerifiedEdits(payload) {
    setSaving(true);
    setVerifiedError("");
    try {
      const v = await candidates.patchProfile(payload);
      setVerified(v);
      setEditing(false);
    } catch (e) {
      setVerifiedError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (error && !profile) {
    return (
      <main className="container">
        <div className="label-mono" style={{ color: COLORS.accent }}>
          Error loading dashboard
        </div>
        <p>{error}</p>
      </main>
    );
  }

  if (!profile) return <GeneratingScreen note="Loading your profile…" />;

  return (
    <main className="container" style={{ maxWidth: 960 }}>
      <div className="label-mono" style={{ marginBottom: 12 }}>
        Candidate · Dashboard
      </div>
      <h1
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 44,
          fontWeight: 500,
          letterSpacing: "-0.015em",
          lineHeight: 1.1,
          margin: "0 0 8px",
        }}
      >
        {profile.display_name ? `Hi, ${profile.display_name.split(" ")[0]}.` : "Welcome."}
      </h1>
      <p style={{ color: COLORS.muted, marginBottom: 28, fontSize: 16 }}>
        Managers see only what the system synthesizes — never this raw view.
      </p>

      <div style={{ position: "relative" }}>
        <Tabs value={tab} onChange={setTab} items={TABS} />
        <div
          style={{
            position: "absolute",
            right: 0,
            top: 4,
          }}
        >
          <NotificationBell onItemClick={() => setTab("matches")} />
        </div>
      </div>

      {error && (
        <div style={{ color: COLORS.accent, fontSize: 14, fontStyle: "italic", marginBottom: 20 }}>
          {error}
        </div>
      )}

      {tab === "overview" && (
        <OverviewTab
          profile={profile}
          verified={verified}
          verifiedError={verifiedError}
          saving={saving}
          autoExtracting={autoExtracting}
          onReExtract={reExtract}
          onEdit={() => setEditing(true)}
          nav={nav}
        />
      )}
      {editing && (
        <VerifiedProfileEditor
          profile={verified}
          saving={saving}
          onSave={saveVerifiedEdits}
          onClose={() => setEditing(false)}
        />
      )}
      {tab === "matches" && <MatchesTab />}
      {tab === "settings" && (
        <SettingsTab
          user={user}
          profile={profile}
          saving={saving}
          onSave={(fields) => patchProfile(fields)}
        />
      )}
    </main>
  );
}

// ===========================================================================
// Overview tab — profile accuracy ring + extracted profile + assessment summary
// ===========================================================================
function OverviewTab({
  profile,
  verified,
  verifiedError,
  saving,
  autoExtracting,
  onReExtract,
  onEdit,
  nav,
}) {
  const sources = extractionSources(profile, verified);
  const baseline = deriveBaselineAccuracy(profile, verified);
  const displayedAccuracy = Math.max(profile.profile_accuracy_score ?? 0, baseline);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <section className="card">
        <ProfileAccuracyRing value={displayedAccuracy} />
        <div style={{ marginTop: 22 }}>
          <CompletenessChecklist profile={profile} />
        </div>
        <div
          style={{
            marginTop: 18,
            padding: "12px 14px",
            background: COLORS.paper,
            border: `1px solid ${COLORS.rule}`,
            color: COLORS.muted,
            fontSize: 13,
            lineHeight: 1.5,
          }}
        >
          <strong style={{ color: COLORS.ink, fontWeight: 500 }}>Extracted from:</strong>{" "}
          {sources.length === 0
            ? "nothing yet — add a CV or link your GitHub in Settings to get started."
            : sources.join(" · ")}
        </div>
      </section>

      <BehaviouralAssessmentCard profile={profile} nav={nav} />

      <section className="card">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 18,
          }}
        >
          <div className="label-mono">Verified profile</div>
          <div style={{ display: "flex", gap: 8 }}>
            {verified && (
              <button
                className="ghost"
                disabled={saving || autoExtracting}
                onClick={onEdit}
                style={{ padding: "8px 16px", fontSize: 11 }}
              >
                Edit →
              </button>
            )}
            <button
              className="ghost"
              disabled={saving || autoExtracting}
              onClick={onReExtract}
              style={{ padding: "8px 16px", fontSize: 11 }}
            >
              {autoExtracting
                ? "Extracting…"
                : verified
                ? saving
                  ? "Re-extracting…"
                  : "Re-extract →"
                : saving
                ? "Extracting…"
                : "Run extraction →"}
            </button>
          </div>
        </div>
        {autoExtracting && (
          <div style={{ color: COLORS.muted, fontSize: 13, marginBottom: 12 }}>
            Reading your CV, GitHub, and any linked sites — this takes ~10–30 seconds.
          </div>
        )}
        {verifiedError && (
          <div style={{ color: COLORS.accent, fontSize: 13, marginBottom: 12 }}>
            {verifiedError}
          </div>
        )}
        <VerifiedProfileView profile={verified} />
      </section>
    </div>
  );
}

function CompletenessChecklist({ profile }) {
  const items = [
    { label: "CV uploaded", done: !!profile.cv_path },
    { label: "GitHub linked", done: !!profile.github_url },
    { label: "LinkedIn linked", done: !!profile.linkedin_url },
    { label: "Portfolio linked", done: !!profile.portfolio_url },
    { label: "Behavioural assessment", done: profile.assessment_status === "completed" },
  ];
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {items.map((it) => (
        <span
          key={it.label}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "5px 10px",
            border: `1px solid ${it.done ? COLORS.ink : COLORS.rule}`,
            background: it.done ? COLORS.ink : "transparent",
            color: it.done ? COLORS.paper : COLORS.muted,
            fontFamily: FONT_MONO,
            fontSize: 10,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
          }}
        >
          <span>{it.done ? "✓" : "○"}</span>
          {it.label}
        </span>
      ))}
    </div>
  );
}

function extractionSources(profile, verified) {
  const out = [];
  if (profile.cv_path) out.push("CV");
  if (profile.github_url && verified?.github_repos?.length) {
    out.push(`${verified.github_repos.length} GitHub repos`);
  } else if (profile.github_url) {
    out.push("GitHub");
  }
  if (profile.portfolio_url) out.push("Portfolio");
  if (profile.linkedin_url) out.push("LinkedIn");
  return out;
}

function BehaviouralAssessmentCard({ profile, nav }) {
  const done = profile.assessment_status === "completed";
  return (
    <section className="card">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 18,
        }}
      >
        <div className="label-mono">Behavioural assessment</div>
        <StatusChip done={done} />
      </div>
      {done && profile.persona?.narrative ? (
        <>
          <p
            style={{
              fontFamily: FONT_DISPLAY,
              fontSize: 18,
              fontStyle: "italic",
              lineHeight: 1.55,
              margin: "0 0 18px",
              color: COLORS.ink,
            }}
          >
            “{profile.persona.narrative}”
          </p>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <button className="ghost" onClick={() => nav("/profile")}>
              View full persona report →
            </button>
            <button className="ghost" onClick={() => nav("/intake")}>
              Re-take assessment
            </button>
          </div>
        </>
      ) : (
        <>
          <p style={{ color: COLORS.muted, marginBottom: 18, fontSize: 16 }}>
            Complete the 12-minute assessment to be matched against available positions.
            You won't be told which companies are evaluating you — this keeps the signal clean.
          </p>
          <button className="primary" onClick={() => nav("/intake")}>
            Take the assessment →
          </button>
        </>
      )}
    </section>
  );
}

function StatusChip({ done }) {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 12px",
        border: `1px solid ${done ? COLORS.ink : COLORS.rule}`,
        background: done ? COLORS.ink : "transparent",
        color: done ? COLORS.paper : COLORS.muted,
        fontFamily: FONT_MONO,
        fontSize: 10,
        letterSpacing: "0.15em",
        textTransform: "uppercase",
      }}
    >
      {done ? "Complete" : "Not started"}
    </div>
  );
}

// ===========================================================================
// Matches tab — interview invites + vacancy reveal (Roadmap 2 / PR #4).
// ===========================================================================
function MatchesTab() {
  const [interviews, setInterviews] = useState(null);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  async function refresh() {
    try {
      setInterviews(await interviewsApi.listMine());
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function act(id, fn) {
    setBusyId(id);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  if (interviews === null && !error) {
    return (
      <section className="card" style={{ textAlign: "center", padding: 32, color: COLORS.muted }}>
        Loading invites…
      </section>
    );
  }

  if ((interviews || []).length === 0) {
    return (
      <section className="card" style={{ textAlign: "center", padding: "48px 28px" }}>
        <div className="label-mono" style={{ marginBottom: 14 }}>Interview invites</div>
        <p
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 22,
            margin: "0 0 12px",
            color: COLORS.ink,
          }}
        >
          No invites yet.
        </p>
        <p style={{ color: COLORS.muted, fontSize: 15, maxWidth: 480, margin: "0 auto" }}>
          When a recruiter wants to interview you, the role and proposed times will
          appear here — and only here. You won't be told who's evaluating you in the
          meantime, so the signal stays clean.
        </p>
        {error && (
          <div style={{ marginTop: 16, color: COLORS.accent, fontSize: 13 }}>{error}</div>
        )}
      </section>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {error && (
        <div style={{ color: COLORS.accent, fontSize: 13 }}>{error}</div>
      )}
      {interviews.map((iv) => (
        <InterviewCard
          key={iv.id}
          interview={iv}
          busy={busyId === iv.id}
          onAccept={(slot) => act(iv.id, () => interviewsApi.accept(iv.id, slot))}
          onDecline={(msg) => act(iv.id, () => interviewsApi.decline(iv.id, msg))}
          onCounter={(slots, msg) =>
            act(iv.id, () => interviewsApi.counter(iv.id, slots, msg))
          }
        />
      ))}
    </div>
  );
}

function InterviewCard({ interview, busy, onAccept, onDecline, onCounter }) {
  const [selected, setSelected] = useState(interview.proposed_slots?.[0] || "");
  const [counterMode, setCounterMode] = useState(false);
  const [counterSlots, setCounterSlots] = useState(["", "", ""]);
  const [counterMsg, setCounterMsg] = useState("");
  const status = interview.status;
  const isDone = status === "accepted" || status === "declined";

  function submitCounter() {
    const cleaned = counterSlots
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => new Date(s).toISOString());
    if (cleaned.length === 0) return;
    onCounter(cleaned, counterMsg || null);
  }

  return (
    <section className="card" style={{ padding: 24 }}>
      <div className="label-mono" style={{ marginBottom: 8 }}>
        {interview.organization_name || "Vacancy"} · Interview invite
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 12 }}>
        <h3
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 26,
            fontWeight: 500,
            margin: "0 0 4px",
            letterSpacing: "-0.01em",
          }}
        >
          {interview.position_name}
        </h3>
        <StatusPill status={status} />
      </div>
      <div style={{ color: COLORS.muted, fontSize: 15, marginBottom: 14 }}>
        {interview.position_role}
      </div>

      {status === "accepted" && interview.selected_slot && (
        <div style={{ fontSize: 15 }}>
          Confirmed for{" "}
          <strong>{new Date(interview.selected_slot).toLocaleString()}</strong>.
        </div>
      )}
      {status === "declined" && (
        <div style={{ color: COLORS.muted, fontSize: 14 }}>You declined this invite.</div>
      )}

      {!isDone && !counterMode && (
        <>
          <div className="label-mono" style={{ marginBottom: 8 }}>Pick a time</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
            {(interview.proposed_slots || []).map((slot) => (
              <label
                key={slot}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "10px 12px",
                  border: `1px solid ${selected === slot ? COLORS.ink : COLORS.rule}`,
                  cursor: "pointer",
                  background: selected === slot ? "#fffbf2" : "transparent",
                }}
              >
                <input
                  type="radio"
                  name={`slot-${interview.id}`}
                  value={slot}
                  checked={selected === slot}
                  onChange={() => setSelected(slot)}
                />
                <span style={{ fontFamily: FONT_MONO, fontSize: 13 }}>
                  {new Date(slot).toLocaleString()}
                </span>
              </label>
            ))}
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button
              type="button"
              className="primary"
              disabled={busy || !selected}
              onClick={() => onAccept(selected)}
              style={{ padding: "10px 18px" }}
            >
              Accept
            </button>
            <button
              type="button"
              className="ghost"
              disabled={busy}
              onClick={() => setCounterMode(true)}
              style={{ padding: "10px 18px" }}
            >
              Propose new time
            </button>
            <button
              type="button"
              className="ghost"
              disabled={busy}
              onClick={() => onDecline(null)}
              style={{ padding: "10px 18px" }}
            >
              Decline
            </button>
          </div>
        </>
      )}

      {!isDone && counterMode && (
        <>
          <div className="label-mono" style={{ marginBottom: 8 }}>Counter-propose</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
            {counterSlots.map((s, i) => (
              <input
                key={i}
                type="datetime-local"
                className="ed"
                value={s}
                onChange={(e) =>
                  setCounterSlots((prev) => prev.map((x, idx) => (idx === i ? e.target.value : x)))
                }
              />
            ))}
          </div>
          <textarea
            className="ed"
            placeholder="Optional note (e.g. timezone constraints)"
            value={counterMsg}
            onChange={(e) => setCounterMsg(e.target.value)}
            style={{ minHeight: 80, marginBottom: 12 }}
          />
          <div style={{ display: "flex", gap: 10 }}>
            <button
              type="button"
              className="primary"
              disabled={busy}
              onClick={submitCounter}
              style={{ padding: "10px 18px" }}
            >
              Send counter
            </button>
            <button
              type="button"
              className="ghost"
              disabled={busy}
              onClick={() => setCounterMode(false)}
              style={{ padding: "10px 18px" }}
            >
              Back
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function StatusPill({ status }) {
  const label = {
    proposed: "Awaiting your response",
    accepted: "Accepted",
    declined: "Declined",
    rescheduled: "Counter-proposed",
    completed: "Completed",
  }[status] || status;
  const color =
    status === "accepted" ? "#1f7a3b" :
    status === "declined" ? COLORS.accent :
    COLORS.muted;
  return (
    <span
      style={{
        fontFamily: FONT_MONO,
        fontSize: 11,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color,
        border: `1px solid ${color}`,
        padding: "3px 8px",
      }}
    >
      {label}
    </span>
  );
}

// ===========================================================================
// Settings tab — display name + profile artefacts (CV, LinkedIn, GitHub, Portfolio)
// ===========================================================================
function SettingsTab({ user, profile, saving, onSave }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <IdentityCard user={user} profile={profile} saving={saving} onSave={onSave} />
      <TargetsCard profile={profile} saving={saving} onSave={onSave} />
      <ArtefactsCard user={user} profile={profile} saving={saving} onSave={onSave} />
    </div>
  );
}

function TargetsCard({ profile, saving, onSave }) {
  const [roleFamily, setRoleFamily] = useState(profile.target_role_family || "");
  const [seniority, setSeniority] = useState(profile.target_seniority || "");
  const dirty =
    roleFamily !== (profile.target_role_family || "") ||
    seniority !== (profile.target_seniority || "");
  const summary =
    profile.target_role_family || profile.target_seniority
      ? [
          ROLE_FAMILY_BY_VALUE[profile.target_role_family] || profile.target_role_family,
          SENIORITY_BY_VALUE[profile.target_seniority] || profile.target_seniority,
        ]
          .filter(Boolean)
          .join(" · ")
      : null;

  return (
    <section className="card">
      <div className="label-mono" style={{ marginBottom: 8 }}>
        Job targets
      </div>
      <p style={{ color: COLORS.muted, fontSize: 14, margin: "0 0 18px" }}>
        We'll only consider you for vacancies that match these. Change them
        any time — your live matches will refresh accordingly.
      </p>
      {summary && (
        <div
          style={{
            marginBottom: 18,
            padding: "10px 14px",
            background: COLORS.paper,
            border: `1px solid ${COLORS.rule}`,
            fontFamily: FONT_MONO,
            fontSize: 12,
            color: COLORS.ink,
            letterSpacing: "0.04em",
          }}
        >
          Currently targeting · {summary}
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16,
          marginBottom: 16,
        }}
      >
        <div>
          <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>
            Role family
          </label>
          <select
            className="ed"
            value={roleFamily}
            onChange={(e) => setRoleFamily(e.target.value)}
            style={selectStyle}
          >
            <option value="">— Select —</option>
            {ROLE_FAMILIES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>
            Seniority
          </label>
          <select
            className="ed"
            value={seniority}
            onChange={(e) => setSeniority(e.target.value)}
            style={selectStyle}
          >
            <option value="">— Select —</option>
            {SENIORITY_LEVELS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {dirty && (
        <button
          className="primary"
          disabled={saving}
          onClick={() =>
            onSave({
              target_role_family: roleFamily || null,
              target_seniority: seniority || null,
            })
          }
        >
          {saving ? "Saving…" : "Save targets →"}
        </button>
      )}
    </section>
  );
}

const selectStyle = {
  appearance: "none",
  background: COLORS.cardBg,
  cursor: "pointer",
  paddingRight: 32,
};

function IdentityCard({ user, profile, saving, onSave }) {
  const [name, setName] = useState(profile.display_name ?? "");
  const [dirty, setDirty] = useState(false);

  return (
    <section className="card">
      <div className="label-mono" style={{ marginBottom: 16 }}>
        Identity
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 24 }}>
        {user?.user_metadata?.avatar_url && (
          <img
            src={user.user_metadata.avatar_url}
            alt="avatar"
            style={{ width: 56, height: 56, borderRadius: "50%", border: `1px solid ${COLORS.rule}` }}
          />
        )}
        <div>
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 20, fontWeight: 500 }}>
            {profile.display_name || user?.email}
          </div>
          <div style={{ color: COLORS.muted, fontSize: 14 }}>{user?.email}</div>
        </div>
      </div>

      <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>
        Display name
      </label>
      <input
        className="ed"
        value={name}
        placeholder="How you'd like to be referred to"
        onChange={(e) => {
          setName(e.target.value);
          setDirty(true);
        }}
        style={{ marginBottom: 16 }}
      />
      {dirty && (
        <button
          className="primary"
          disabled={saving}
          onClick={() => {
            onSave({ display_name: name });
            setDirty(false);
          }}
        >
          {saving ? "Saving…" : "Save name →"}
        </button>
      )}
    </section>
  );
}

function ArtefactsCard({ user, profile, saving, onSave }) {
  const [linkedin, setLinkedin] = useState(profile.linkedin_url ?? "");
  const [github, setGithub] = useState(profile.github_url ?? "");
  const [portfolio, setPortfolio] = useState(profile.portfolio_url ?? "");
  const [linksDirty, setLinksDirty] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [cvError, setCvError] = useState("");
  const [signedUrl, setSignedUrl] = useState(null);
  const fileRef = useRef(null);

  useEffect(() => {
    if (!profile.cv_path) return;
    supabase.storage
      .from("cvs")
      .createSignedUrl(profile.cv_path, 300)
      .then(({ data }) => data?.signedUrl && setSignedUrl(data.signedUrl));
  }, [profile.cv_path]);

  async function handleCvUpload(e) {
    const file = e.target.files?.[0];
    if (!file || !user) return;
    setCvError("");
    setUploading(true);

    const path = `${user.id}/cv.${file.name.split(".").pop()}`;
    const { error } = await supabase.storage.from("cvs").upload(path, file, {
      upsert: true,
      contentType: file.type,
    });

    if (error) {
      setCvError(error.message);
    } else {
      await onSave({ cv_path: path });
      const { data } = await supabase.storage.from("cvs").createSignedUrl(path, 300);
      if (data?.signedUrl) setSignedUrl(data.signedUrl);
    }
    setUploading(false);
    e.target.value = "";
  }

  return (
    <section className="card">
      <div className="label-mono" style={{ marginBottom: 20 }}>
        Profile artefacts
      </div>

      <div style={{ marginBottom: 28 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 10,
          }}
        >
          <label className="label-mono">CV / Résumé</label>
          {signedUrl && (
            <a
              href={signedUrl}
              target="_blank"
              rel="noreferrer"
              style={{
                fontFamily: FONT_MONO,
                fontSize: 10,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: COLORS.muted,
                textDecoration: "none",
              }}
            >
              View current →
            </a>
          )}
        </div>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.doc,.docx"
          style={{ display: "none" }}
          onChange={handleCvUpload}
        />
        <button
          className="ghost"
          disabled={uploading}
          onClick={() => fileRef.current?.click()}
          style={{ width: "100%" }}
        >
          {uploading
            ? "Uploading…"
            : profile.cv_path
            ? "Replace CV (PDF or Word)"
            : "Upload CV (PDF or Word)"}
        </button>
        {cvError && (
          <div style={{ color: COLORS.accent, fontSize: 13, marginTop: 8 }}>{cvError}</div>
        )}
        {profile.cv_path && !cvError && (
          <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 6, fontFamily: FONT_MONO }}>
            {profile.cv_path.split("/").pop()}
          </div>
        )}
      </div>

      <LinkInput label="LinkedIn URL" value={linkedin} placeholder="https://linkedin.com/in/yourname"
        onChange={(v) => { setLinkedin(v); setLinksDirty(true); }} />
      <LinkInput label="GitHub URL" value={github} placeholder="https://github.com/yourname"
        onChange={(v) => { setGithub(v); setLinksDirty(true); }} />
      <LinkInput label="Personal website / Portfolio" value={portfolio} placeholder="https://yourname.dev"
        onChange={(v) => { setPortfolio(v); setLinksDirty(true); }} />

      {linksDirty && (
        <button
          className="primary"
          disabled={saving}
          onClick={() => {
            onSave({
              linkedin_url: linkedin || null,
              github_url: github || null,
              portfolio_url: portfolio || null,
            });
            setLinksDirty(false);
          }}
        >
          {saving ? "Saving…" : "Save links →"}
        </button>
      )}
    </section>
  );
}

function LinkInput({ label, value, placeholder, onChange }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>
        {label}
      </label>
      <input
        className="ed"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
