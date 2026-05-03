import React from "react";
import { COLORS, FONT_MONO } from "../design.js";

/**
 * Minimal tab strip + panel switcher.
 *
 * Usage:
 *   <Tabs
 *     value={tab}
 *     onChange={setTab}
 *     items={[
 *       { id: "overview", label: "Overview" },
 *       { id: "matches",  label: "Matches", badge: 2 },
 *       { id: "settings", label: "Settings" },
 *     ]}
 *   />
 *   {tab === "overview" && <OverviewPanel />}
 *
 * Style intentionally aligns with the existing nav-link motif: monospace
 * label, uppercase, ink underline on active. Keeps the editorial tone.
 */
export default function Tabs({ value, onChange, items }) {
  return (
    <div
      role="tablist"
      style={{
        display: "flex",
        gap: 28,
        borderBottom: `1px solid ${COLORS.rule}`,
        marginBottom: 28,
      }}
    >
      {items.map((item) => {
        const active = item.id === value;
        return (
          <button
            key={item.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.id)}
            style={{
              background: "transparent",
              border: "none",
              padding: "12px 0",
              marginBottom: -1,
              cursor: "pointer",
              fontFamily: FONT_MONO,
              fontSize: 11,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: active ? COLORS.ink : COLORS.muted,
              borderBottom: `2px solid ${active ? COLORS.ink : "transparent"}`,
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            {item.label}
            {item.badge != null && item.badge !== 0 && (
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  minWidth: 18,
                  padding: "0 6px",
                  height: 18,
                  background: active ? COLORS.ink : COLORS.rule,
                  color: active ? COLORS.paper : COLORS.muted,
                  fontFamily: FONT_MONO,
                  fontSize: 10,
                  letterSpacing: 0,
                  borderRadius: 9,
                }}
              >
                {item.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
