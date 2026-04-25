import React, { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, GLOBAL_CSS } from "./design.js";
import {
  clearManagerCreds,
  getCandidateId,
  hasManagerCreds,
  setManagerCreds,
} from "./api.js";
import CandidateIntake from "./pages/CandidateIntake.jsx";
import CandidateProfile from "./pages/CandidateProfile.jsx";
import ManagerDashboard from "./pages/ManagerDashboard.jsx";
import TemplateSetup from "./pages/TemplateSetup.jsx";

export default function App() {
  const [managerOk, setManagerOk] = useState(hasManagerCreds());

  return (
    <>
      <style>{GLOBAL_CSS}</style>
      <Masthead
        managerOk={managerOk}
        onLogin={() => setManagerOk(true)}
        onLogout={() => {
          clearManagerCreds();
          setManagerOk(false);
        }}
      />

      <Routes>
        <Route path="/" element={<LandingRedirect />} />
        <Route path="/intake/*" element={<CandidateIntake />} />
        <Route path="/profile" element={<CandidateProfile />} />
        <Route
          path="/manager"
          element={
            managerOk ? (
              <ManagerDashboard />
            ) : (
              <ManagerLogin onLogin={() => setManagerOk(true)} />
            )
          }
        />
        <Route
          path="/manager/templates/:companyId?"
          element={
            managerOk ? (
              <TemplateSetup />
            ) : (
              <ManagerLogin onLogin={() => setManagerOk(true)} />
            )
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <Footer />
    </>
  );
}

function LandingRedirect() {
  const nav = useNavigate();
  useEffect(() => {
    // If the browser already has a candidate UUID, take them to their profile.
    // Otherwise start a fresh intake.
    nav(getCandidateId() ? "/profile" : "/intake", { replace: true });
  }, [nav]);
  return null;
}

function Masthead({ managerOk, onLogin, onLogout }) {
  return (
    <header
      style={{
        borderBottom: `2px solid ${COLORS.ink}`,
        padding: "24px 48px 18px",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-end",
        gap: 32,
        flexWrap: "wrap",
      }}
    >
      <div>
        <div className="label-mono">Screening Instrument · v0</div>
        <div
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 32,
            fontWeight: 500,
            marginTop: 4,
            letterSpacing: "-0.01em",
          }}
        >
          Parallax<span style={{ color: COLORS.accent }}>.</span>
        </div>
      </div>
      <div className="nav-bar">
        <NavLink to="/intake" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
          Intake
        </NavLink>
        <NavLink to="/profile" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
          My profile
        </NavLink>
        <NavLink to="/manager" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
          Manager
        </NavLink>
        {managerOk && (
          <button className="ghost" onClick={onLogout} style={{ padding: "6px 14px" }}>
            Sign out
          </button>
        )}
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer
      style={{
        borderTop: `1px solid ${COLORS.rule}`,
        padding: "24px 48px",
        color: COLORS.muted,
        fontSize: 13,
        display: "flex",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: 12,
      }}
    >
      <div className="label-mono">Screening signal · Not a decision</div>
      <div className="label-mono">Blind matching · Mutual opt-in required</div>
    </footer>
  );
}

function ManagerLogin({ onLogin }) {
  const [username, setUsername] = useState("manager");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const nav = useNavigate();

  async function submit(e) {
    e.preventDefault();
    setError("");
    setManagerCreds(username, password);
    try {
      // Validate by calling a manager-gated endpoint.
      const resp = await fetch(
        `${(import.meta.env.VITE_API_BASE_URL || "http://localhost:8000")}/companies`,
        { headers: { Authorization: `Basic ${btoa(`${username}:${password}`)}` } },
      );
      if (resp.status === 401) {
        setError("Incorrect credentials.");
        clearManagerCreds();
        return;
      }
      onLogin();
      nav("/manager");
    } catch (e) {
      setError(e.message);
      clearManagerCreds();
    }
  }

  return (
    <div className="container" style={{ maxWidth: 460 }}>
      <div className="label-mono" style={{ marginBottom: 12 }}>Manager · Restricted</div>
      <h2
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 34,
          fontWeight: 500,
          margin: "0 0 24px",
        }}
      >
        Sign in to review candidates.
      </h2>
      <form onSubmit={submit}>
        <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>
          Username
        </label>
        <input
          className="ed"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          style={{ marginBottom: 16 }}
        />
        <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>
          Password
        </label>
        <input
          className="ed"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{ marginBottom: 24 }}
        />
        {error && (
          <div
            style={{
              color: COLORS.accent,
              fontSize: 14,
              marginBottom: 16,
              fontFamily: FONT_DISPLAY,
              fontStyle: "italic",
            }}
          >
            {error}
          </div>
        )}
        <button className="primary" type="submit">Sign in →</button>
      </form>
    </div>
  );
}
