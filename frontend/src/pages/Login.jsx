import React from "react";
import { useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY } from "../design.js";
import { useAuth } from "../lib/auth.js";

export default function Login() {
  const { signInWithGoogle, loading } = useAuth();
  const nav = useNavigate();

  async function handleGoogle() {
    await signInWithGoogle();
    // Redirect happens via OAuth callback → onAuthStateChange → App routing.
  }

  return (
    <div className="container" style={{ maxWidth: 460, paddingTop: 48 }}>
      <div className="label-mono" style={{ marginBottom: 12 }}>
        Authentication required
      </div>
      <h2
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 34,
          fontWeight: 500,
          margin: "0 0 12px",
        }}
      >
        Sign in to continue.
      </h2>
      <p style={{ color: COLORS.muted, fontSize: 15, margin: "0 0 32px" }}>
        Managers land on the hiring dashboard. Candidates land on their profile.
      </p>

      <button
        className="primary"
        onClick={handleGoogle}
        disabled={loading}
        style={{ display: "flex", alignItems: "center", gap: 10 }}
      >
        <GoogleIcon />
        Continue with Google
      </button>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path
        d="M17.64 9.2c0-.638-.057-1.252-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908C16.658 14.252 17.64 11.948 17.64 9.2z"
        fill="#4285F4"
      />
      <path
        d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z"
        fill="#34A853"
      />
      <path
        d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"
        fill="#FBBC05"
      />
      <path
        d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"
        fill="#EA4335"
      />
    </svg>
  );
}
