import React, { useEffect, useRef, useState } from "react";
import { COLORS, FONT_MONO } from "../design.js";

/**
 * Tiny vertical "⋮" menu. Anchors top-right of its container by default.
 * `items` = [{ label, onClick }].
 *
 * Click outside or hit Escape closes.
 */
export default function KebabMenu({ items, ariaLabel = "More actions" }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    function onKey(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={wrapRef} style={{ position: "relative" }}>
      <button
        aria-label={ariaLabel}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        style={{
          background: "transparent",
          border: "none",
          cursor: "pointer",
          padding: "4px 6px",
          fontSize: 18,
          lineHeight: 1,
          color: COLORS.muted,
          fontWeight: 600,
          letterSpacing: "0.05em",
        }}
      >
        ⋮
      </button>

      {open && (
        <ul
          role="menu"
          style={{
            position: "absolute",
            top: "100%",
            right: 0,
            margin: 0,
            padding: 0,
            listStyle: "none",
            background: COLORS.cardBg,
            border: `1px solid ${COLORS.ink}`,
            minWidth: 140,
            zIndex: 20,
            boxShadow: "0 4px 12px rgba(26,24,20,0.12)",
          }}
        >
          {items.map((it, i) => (
            <li key={i}>
              <button
                role="menuitem"
                onClick={(e) => {
                  e.stopPropagation();
                  setOpen(false);
                  it.onClick(e);
                }}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  background: "transparent",
                  border: "none",
                  padding: "10px 14px",
                  fontFamily: FONT_MONO,
                  fontSize: 11,
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                  color: COLORS.ink,
                  cursor: "pointer",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = COLORS.paper)}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                {it.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
