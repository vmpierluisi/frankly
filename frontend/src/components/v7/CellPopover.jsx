import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { COLORS, FONT_MONO } from "../../design.js";

// Manager Shortlist V7 — anchored cell popover.
// Three actions: See in scenario / Open LinkedIn / Open CV. Closes on Esc,
// click-outside, or action selection. Clamps to the viewport. Focus-traps.
export default function CellPopover({
  anchorRect,
  scenarioId,
  linkedinUrl,
  cvAvailable,
  onSeeInScenario,
  onOpenLinkedIn,
  onOpenCV,
  onClose,
}) {
  const ref = useRef(null);
  const [pos, setPos] = useState({ top: -9999, left: -9999 });

  useLayoutEffect(() => {
    if (!ref.current || !anchorRect) return;
    const el = ref.current.getBoundingClientRect();
    const margin = 8;
    let top = anchorRect.bottom + 6;
    let left = anchorRect.left;
    if (left + el.width > window.innerWidth - margin) {
      left = window.innerWidth - el.width - margin;
    }
    if (top + el.height > window.innerHeight - margin) {
      top = anchorRect.top - el.height - 6; // flip above
    }
    setPos({ top: Math.max(margin, top), left: Math.max(margin, left) });
  }, [anchorRect]);

  useEffect(() => {
    // Focus first action on open.
    const first = ref.current?.querySelector("button");
    first?.focus();

    function onKey(e) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      } else if (e.key === "Tab") {
        const items = ref.current?.querySelectorAll("button") || [];
        if (items.length === 0) return;
        const list = Array.from(items);
        const idx = list.indexOf(document.activeElement);
        e.preventDefault();
        const next = e.shiftKey
          ? (idx - 1 + list.length) % list.length
          : (idx + 1) % list.length;
        list[next].focus();
      }
    }
    function onDocClick(e) {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    }
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("mousedown", onDocClick);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("mousedown", onDocClick);
    };
  }, [onClose]);

  const actions = [];
  if (scenarioId && onSeeInScenario) {
    actions.push({ label: "See in scenario →", run: onSeeInScenario });
  }
  if (linkedinUrl) {
    actions.push({ label: "Open LinkedIn ↗", run: () => onOpenLinkedIn(linkedinUrl) });
  }
  if (cvAvailable && onOpenCV) {
    actions.push({ label: "Open CV", run: onOpenCV });
  }
  if (actions.length === 0) {
    actions.push({ label: "No evidence linked", run: onClose, disabled: true });
  }

  return (
    <div
      ref={ref}
      role="menu"
      style={{
        position: "fixed",
        top: pos.top,
        left: pos.left,
        zIndex: 1000,
        background: "#fff",
        border: `1px solid ${COLORS.ink}`,
        boxShadow: "0 6px 24px rgba(0,0,0,0.12)",
        minWidth: 200,
        display: "flex",
        flexDirection: "column",
      }}
    >
      {actions.map((a) => (
        <button
          key={a.label}
          type="button"
          role="menuitem"
          disabled={a.disabled}
          onClick={() => {
            a.run();
            if (!a.disabled) onClose();
          }}
          style={{
            textAlign: "left",
            background: "transparent",
            border: "none",
            borderBottom: `1px solid ${COLORS.rule}`,
            padding: "12px 16px",
            fontFamily: FONT_MONO,
            fontSize: 12,
            letterSpacing: "0.06em",
            color: a.disabled ? COLORS.muted : COLORS.ink,
            cursor: a.disabled ? "default" : "pointer",
          }}
          onMouseEnter={(e) => {
            if (!a.disabled) e.currentTarget.style.background = COLORS.paper;
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
          }}
        >
          {a.label}
        </button>
      ))}
    </div>
  );
}
