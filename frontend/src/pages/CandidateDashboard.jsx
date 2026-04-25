import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { candidates } from "../api.js";
import { supabase } from "../lib/supabase.js";
import { useAuth } from "../lib/auth.js";
import { GeneratingScreen } from "../components/Widgets.jsx";

export default function CandidateDashboard() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    candidates
      .me()
      .then(setProfile)
      .catch((e) => setError(e.message));
  }, []);

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
    <main className="container" style={{ maxWidth: 860 }}>
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
        Your profile.
      </h1>
      <p style={{ color: COLORS.muted, marginBottom: 32, fontSize: 16 }}>
        Managers see only what the system synthesizes — never this raw view.
      </p>
      <hr className="rule-thick" style={{ margin: "0 0 40px" }} />

      {error && (
        <div
          style={{
            color: COLORS.accent,
            fontSize: 14,
            fontStyle: "italic",
            marginBottom: 20,
          }}
        >
          {error}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
        <IdentityCard
          user={user}
          profile={profile}
          saving={saving}
          onSave={(fields) => patchProfile(fields)}
        />
        <AssessmentCard profile={profile} nav={nav} />
        <ArtefactsCard
          user={user}
          profile={profile}
          saving={saving}
          onSave={(fields) => patchProfile(fields)}
        />
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Card 1 — Identity
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Card 2 — Behavioural assessment
// ---------------------------------------------------------------------------
function AssessmentCard({ profile, nav }) {
  const done = profile.assessment_status === "completed";

  return (
    <section className="card">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 20,
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
              fontSize: 19,
              fontStyle: "italic",
              lineHeight: 1.55,
              margin: "0 0 20px",
              color: COLORS.ink,
            }}
          >
            "{profile.persona.narrative}"
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
          <p style={{ color: COLORS.muted, marginBottom: 20, fontSize: 16 }}>
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

// ---------------------------------------------------------------------------
// Card 3 — Profile artefacts (CV, LinkedIn, GitHub)
// ---------------------------------------------------------------------------
function ArtefactsCard({ user, profile, saving, onSave }) {
  const [linkedin, setLinkedin] = useState(profile.linkedin_url ?? "");
  const [github, setGithub] = useState(profile.github_url ?? "");
  const [linksDirty, setLinksDirty] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [cvError, setCvError] = useState("");
  const [signedUrl, setSignedUrl] = useState(null);
  const fileRef = useRef(null);

  // Generate a short-lived signed URL for viewing the existing CV
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
      // Refresh signed URL
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

      {/* CV */}
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

      {/* LinkedIn */}
      <div style={{ marginBottom: 20 }}>
        <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>
          LinkedIn URL
        </label>
        <input
          className="ed"
          value={linkedin}
          placeholder="https://linkedin.com/in/yourname"
          onChange={(e) => {
            setLinkedin(e.target.value);
            setLinksDirty(true);
          }}
        />
      </div>

      {/* GitHub */}
      <div style={{ marginBottom: 20 }}>
        <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>
          GitHub URL
        </label>
        <input
          className="ed"
          value={github}
          placeholder="https://github.com/yourname"
          onChange={(e) => {
            setGithub(e.target.value);
            setLinksDirty(true);
          }}
        />
      </div>

      {linksDirty && (
        <button
          className="primary"
          disabled={saving}
          onClick={() => {
            onSave({ linkedin_url: linkedin || null, github_url: github || null });
            setLinksDirty(false);
          }}
        >
          {saving ? "Saving…" : "Save links →"}
        </button>
      )}
    </section>
  );
}
