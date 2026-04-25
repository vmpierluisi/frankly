import React, { useEffect } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, GLOBAL_CSS } from "./design.js";
import { setSessionGetter } from "./api.js";
import { useAuth } from "./lib/auth.js";
import { supabase } from "./lib/supabase.js";
import CandidateDashboard from "./pages/CandidateDashboard.jsx";
import CandidateIntake from "./pages/CandidateIntake.jsx";
import CandidateProfile from "./pages/CandidateProfile.jsx";
import ManagerDashboard from "./pages/ManagerDashboard.jsx";
import TemplateSetup from "./pages/TemplateSetup.jsx";
import Login from "./pages/Login.jsx";

// Wire the session getter into the API module once at startup.
setSessionGetter(() => supabase.auth.getSession().then((r) => r.data.session));

export default function App() {
  const auth = useAuth();

  if (auth.loading) {
    return (
      <>
        <style>{GLOBAL_CSS}</style>
        <div style={{ padding: 48, color: COLORS.muted, fontFamily: FONT_DISPLAY }}>
          Loading…
        </div>
      </>
    );
  }

  return (
    <>
      <style>{GLOBAL_CSS}</style>
      <Masthead auth={auth} />

      <Routes>
        {/* Public */}
        <Route path="/login" element={<Login />} />

        {/* Root redirect */}
        <Route path="/" element={<RootRedirect auth={auth} />} />

        {/* Candidate-gated */}
        <Route
          path="/dashboard"
          element={
            <RequireAuth auth={auth} role="candidate">
              <CandidateDashboard />
            </RequireAuth>
          }
        />
        <Route
          path="/intake/*"
          element={
            <RequireAuth auth={auth} role="candidate">
              <CandidateIntake />
            </RequireAuth>
          }
        />
        <Route
          path="/profile"
          element={
            <RequireAuth auth={auth} role="candidate">
              <CandidateProfile />
            </RequireAuth>
          }
        />

        {/* Manager-gated */}
        <Route
          path="/manager"
          element={
            <RequireAuth auth={auth} role="manager">
              <ManagerDashboard />
            </RequireAuth>
          }
        />
        <Route
          path="/manager/templates/:companyId?"
          element={
            <RequireAuth auth={auth} role="manager">
              <TemplateSetup />
            </RequireAuth>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <Footer />
    </>
  );
}

function RootRedirect({ auth }) {
  const nav = useNavigate();
  useEffect(() => {
    if (!auth.user) {
      nav("/login", { replace: true });
    } else if (auth.role === "manager") {
      nav("/manager", { replace: true });
    } else {
      nav("/dashboard", { replace: true });
    }
  }, [auth.user, auth.role, nav]);
  return null;
}

function RequireAuth({ auth, role, children }) {
  if (!auth.user) return <Navigate to="/login" replace />;
  if (role && auth.role !== role) {
    return (
      <div className="container" style={{ maxWidth: 460, paddingTop: 48 }}>
        <div className="label-mono" style={{ marginBottom: 12 }}>Access denied</div>
        <h2
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 34,
            fontWeight: 500,
            margin: "0 0 12px",
          }}
        >
          Wrong role.
        </h2>
        <p style={{ color: COLORS.muted }}>
          You're signed in as{" "}
          <strong>{auth.user.email}</strong> ({auth.role}) but this page
          requires the <strong>{role}</strong> role.
        </p>
      </div>
    );
  }
  return children;
}

function Masthead({ auth }) {
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
        {auth.user && auth.role === "candidate" && (
          <>
            <NavLink to="/dashboard" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              Dashboard
            </NavLink>
            <NavLink to="/intake" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              Intake
            </NavLink>
          </>
        )}
        {auth.user && auth.role === "manager" && (
          <NavLink to="/manager" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            Manager
          </NavLink>
        )}
        {auth.user ? (
          <button
            className="ghost"
            onClick={auth.signOut}
            style={{ padding: "6px 14px" }}
          >
            Sign out
          </button>
        ) : (
          <NavLink to="/login" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            Sign in
          </NavLink>
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
