import React, { useRef } from "react";
import { COLORS, FONT_MONO } from "../../design.js";

// Manager Shortlist V7 — segmented size selector (3 / 5 / 10 / All).
// "All" maps to a large top_n the backend clamps to the available pool.
const ALL_N = 50;

export default function ShortlistSizeSelector({ value, onChange, sizes = [3, 5, 10] }) {
  const options = [...sizes, "all"];
  const refs = useRef([]);

  const activeIndex = options.findIndex((o) =>
    o === "all" ? value >= ALL_N : o === value,
  );

  function selectAt(idx) {
    const o = options[idx];
    onChange(o === "all" ? ALL_N : o);
  }

  function onKeyDown(e, idx) {
    let next = idx;
    if (e.key === "ArrowRight") next = (idx + 1) % options.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + options.length) % options.length;
    else return;
    e.preventDefault();
    refs.current[next]?.focus();
    selectAt(next);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span
        className="label-mono"
        style={{ fontFamily: FONT_MONO, fontSize: 10, letterSpacing: "0.18em" }}
        title="Ranked by weighted average across the role's criteria + hard skills. Adjust N to compare more candidates."
      >
        Shortlist · Top N by simulation fit
      </span>
      <div
        role="group"
        aria-label="Shortlist size"
        style={{ display: "inline-flex", border: `1px solid ${COLORS.ink}`, width: "fit-content" }}
      >
        {options.map((o, idx) => {
          const active = idx === activeIndex;
          const label = o === "all" ? "All" : String(o);
          return (
            <button
              key={label}
              ref={(el) => (refs.current[idx] = el)}
              type="button"
              aria-pressed={active}
              onClick={() => selectAt(idx)}
              onKeyDown={(e) => onKeyDown(e, idx)}
              style={{
                border: "none",
                borderRight:
                  idx < options.length - 1 ? `1px solid ${COLORS.ink}` : "none",
                background: active ? COLORS.ink : "transparent",
                color: active ? COLORS.paper : COLORS.ink,
                fontFamily: FONT_MONO,
                fontSize: 12,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                padding: "8px 16px",
                cursor: "pointer",
                transition: "background 0.15s, color 0.15s",
              }}
            >
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
