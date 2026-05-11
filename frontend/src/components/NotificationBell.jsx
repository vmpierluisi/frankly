import React, { useEffect, useRef, useState } from "react";
import { COLORS, FONT_MONO } from "../design.js";
import { notifications as notificationsApi } from "../api.js";

/**
 * Roadmap 2 / PR #4 — bell-icon notification center.
 *
 * Works for both candidate and manager: the backend filters by role
 * automatically. Polls every 30s while mounted. On click, opens a popover
 * with unread + read items; clicking an item marks it read and (when
 * possible) hands off to the parent via `onItemClick(notif)` so the page
 * can route to the relevant tab.
 */
export default function NotificationBell({ onItemClick }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState(null);
  const popoverRef = useRef(null);

  async function refresh() {
    try {
      const rows = await notificationsApi.list();
      setItems(rows);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 30000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e) {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const unreadCount = items.filter((n) => n.status === "unread").length;

  async function handleClick(notif) {
    if (notif.status !== "read") {
      try {
        await notificationsApi.markRead(notif.id);
      } catch (_) {
        /* swallow — UI updates optimistically below */
      }
    }
    setItems((prev) =>
      prev.map((n) => (n.id === notif.id ? { ...n, status: "read" } : n)),
    );
    if (onItemClick) onItemClick(notif);
    setOpen(false);
  }

  async function markAll() {
    try {
      await notificationsApi.markAllRead();
      setItems((prev) =>
        prev.map((n) => (n.status === "dismissed" ? n : { ...n, status: "read" })),
      );
    } catch (_) {
      /* ignore */
    }
  }

  return (
    <div style={{ position: "relative", display: "inline-block" }} ref={popoverRef}>
      <style>{`
        @keyframes bell-swing {
          0%, 100% { transform: rotate(0deg); }
          15% { transform: rotate(12deg); }
          30% { transform: rotate(-10deg); }
          45% { transform: rotate(6deg); }
          60% { transform: rotate(-3deg); }
          75% { transform: rotate(1deg); }
        }
        .bell-icon { transform-origin: 50% 4px; transition: color 0.15s; color: ${COLORS.muted}; }
        .bell-btn:hover .bell-icon { color: ${COLORS.ink}; }
        .bell-btn[data-unread="1"] .bell-icon { color: ${COLORS.ink}; animation: bell-swing 1.6s ease-in-out infinite; }
      `}</style>
      <button
        type="button"
        aria-label="Notifications"
        className="bell-btn"
        data-unread={unreadCount > 0 ? "1" : "0"}
        onClick={() => setOpen((o) => !o)}
        style={{
          background: "transparent",
          border: "none",
          padding: 6,
          cursor: "pointer",
          position: "relative",
          lineHeight: 0,
        }}
      >
        <svg
          className="bell-icon"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="M6 8a6 6 0 1 1 12 0c0 5 2 6 2 8H4c0-2 2-3 2-8Z" />
          <path d="M10 20a2 2 0 0 0 4 0" />
        </svg>
        {unreadCount > 0 && (
          <span
            style={{
              position: "absolute",
              top: 0,
              right: 0,
              background: COLORS.accent,
              color: "#fff",
              borderRadius: 999,
              fontFamily: FONT_MONO,
              fontSize: 9,
              fontWeight: 600,
              minWidth: 14,
              height: 14,
              padding: "0 4px",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 8px)",
            background: COLORS.cardBg,
            border: `1px solid ${COLORS.rule}`,
            width: 360,
            maxHeight: 480,
            overflowY: "auto",
            zIndex: 50,
            boxShadow: "0 10px 32px rgba(0,0,0,0.08)",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "12px 16px",
              borderBottom: `1px solid ${COLORS.rule}`,
            }}
          >
            <div className="label-mono">Notifications</div>
            {items.length > 0 && (
              <button
                type="button"
                onClick={markAll}
                style={{
                  background: "transparent",
                  border: "none",
                  color: COLORS.muted,
                  fontFamily: FONT_MONO,
                  fontSize: 10,
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  cursor: "pointer",
                }}
              >
                Mark all read
              </button>
            )}
          </div>
          {error && (
            <div style={{ padding: 16, color: COLORS.accent, fontSize: 13 }}>{error}</div>
          )}
          {items.length === 0 && !error && (
            <div style={{ padding: 24, color: COLORS.muted, fontSize: 14, textAlign: "center" }}>
              You're all caught up.
            </div>
          )}
          {items.map((n) => (
            <button
              key={n.id}
              type="button"
              onClick={() => handleClick(n)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                background: n.status === "unread" ? "#fffbf2" : "transparent",
                border: "none",
                borderBottom: `1px solid ${COLORS.rule}`,
                padding: "14px 16px",
                cursor: "pointer",
              }}
            >
              <div style={{ fontSize: 14, color: COLORS.ink, marginBottom: 4 }}>
                {formatTitle(n)}
              </div>
              <div style={{ fontSize: 12, color: COLORS.muted, lineHeight: 1.4 }}>
                {formatBody(n)}
              </div>
              <div
                style={{
                  fontFamily: FONT_MONO,
                  fontSize: 10,
                  color: COLORS.muted,
                  marginTop: 6,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                }}
              >
                {new Date(n.created_at).toLocaleString()}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function formatTitle(n) {
  switch (n.type) {
    case "interview_invite":
      return "Interview invite";
    case "interview_accepted":
      return "Interview accepted";
    case "interview_declined":
      return "Interview declined";
    case "interview_counter":
      return "Counter-proposal";
    case "calibration_request":
      return "Calibration request";
    default:
      return n.type.replace(/_/g, " ");
  }
}

function formatBody(n) {
  const p = n.payload || {};
  if (n.type === "interview_invite") {
    const slots = (p.proposed_slots || []).length;
    return `${p.position_name || "A vacancy"} · ${slots} proposed time${slots === 1 ? "" : "s"}`;
  }
  if (n.type === "interview_accepted") {
    return `${p.candidate_display_name || "Candidate"} accepted · ${p.position_name || ""}`;
  }
  if (n.type === "interview_declined") {
    return `${p.candidate_display_name || "Candidate"} declined · ${p.position_name || ""}`;
  }
  if (n.type === "interview_counter") {
    return `${p.candidate_display_name || "Candidate"} counter-proposed · ${p.position_name || ""}`;
  }
  if (n.type === "calibration_request") {
    return "60 seconds to sharpen your profile";
  }
  return "";
}
