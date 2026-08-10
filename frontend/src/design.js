// Design tokens — ported verbatim from hiring-sim-demo.jsx.
// Editorial / refined: FT meets research lab.

export const COLORS = {
  ink: "#1a1814",
  paper: "#f7f3ec",
  rule: "#d9d1c2",
  muted: "#7a7265",
  accent: "#b8391a",
  accentSoft: "#e8d4ca",
  cardBg: "#ffffff",
};

// Manager Shortlist V7 — per-candidate colour rotation. The backend assigns
// slot1..slot5 in ranked order (see comparison_builder._PALETTE_VARS) and the
// frontend maps the returned `--c-slotN` var to these hues.
export const CANDIDATE_PALETTE = {
  "--c-slot1": "#2c5163", // slate teal
  "--c-slot2": "#6b8154", // sage
  "--c-slot3": "#7a4a64", // plum
  "--c-slot4": "#a67a2d", // ochre
  "--c-slot5": "#a65538", // terra-cotta
};

export function candidateColor(paletteVar) {
  return CANDIDATE_PALETTE[paletteVar] || CANDIDATE_PALETTE["--c-slot1"];
}

export const FONT_DISPLAY = `'EB Garamond', 'Libre Caslon Text', 'Times New Roman', serif`;
export const FONT_BODY = `'EB Garamond', Georgia, serif`;
export const FONT_MONO = `'JetBrains Mono', 'Courier New', monospace`;

// Shared CSS injected once in App.jsx. Keeps the rest of the components JSX-only.
export const GLOBAL_CSS = `
  * { box-sizing: border-box; }
  body { margin: 0; background: ${COLORS.paper}; color: ${COLORS.ink};
         font-family: ${FONT_BODY}; font-size: 17px; line-height: 1.55; }
  a { color: ${COLORS.ink}; }
  .rule { border: none; border-top: 1px solid ${COLORS.rule}; margin: 0; }
  .rule-thick { border: none; border-top: 2px solid ${COLORS.ink}; margin: 0; }
  .container { max-width: 960px; margin: 0 auto; padding: 48px 32px 80px; }

  button.primary {
    background: ${COLORS.ink}; color: ${COLORS.paper};
    border: none; padding: 14px 28px;
    font-family: ${FONT_MONO}; font-size: 12px;
    letter-spacing: 0.15em; text-transform: uppercase;
    cursor: pointer; transition: background 0.2s;
  }
  button.primary:hover:not(:disabled) { background: ${COLORS.accent}; }
  button.primary:disabled { background: ${COLORS.muted}; cursor: not-allowed; }
  button.ghost {
    background: transparent; color: ${COLORS.ink};
    border: 1px solid ${COLORS.ink}; padding: 14px 28px;
    font-family: ${FONT_MONO}; font-size: 12px;
    letter-spacing: 0.15em; text-transform: uppercase; cursor: pointer;
  }
  button.ghost:hover { background: ${COLORS.ink}; color: ${COLORS.paper}; }

  button.choice {
    width: 100%; text-align: left;
    background: transparent; color: ${COLORS.ink};
    border: 1px solid ${COLORS.rule};
    padding: 16px 20px; margin-bottom: 10px;
    font-family: ${FONT_BODY}; font-size: 16px; line-height: 1.5;
    cursor: pointer; transition: all 0.15s;
  }
  button.choice:hover { border-color: ${COLORS.ink}; background: #fff; }
  button.choice.selected {
    border-color: ${COLORS.ink}; background: ${COLORS.ink}; color: ${COLORS.paper};
  }

  .likert { display: flex; gap: 6px; }
  .likert button {
    flex: 1; padding: 10px 0;
    background: transparent; border: 1px solid ${COLORS.rule};
    font-family: ${FONT_MONO}; font-size: 13px; cursor: pointer;
    transition: all 0.15s; color: ${COLORS.ink};
  }
  .likert button:hover { border-color: ${COLORS.ink}; }
  .likert button.selected {
    background: ${COLORS.ink}; color: ${COLORS.paper}; border-color: ${COLORS.ink};
  }

  .label-mono {
    font-family: ${FONT_MONO}; font-size: 11px;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: ${COLORS.muted};
  }

  .drop-cap::first-letter {
    font-size: 3.2em; float: left; line-height: 0.9;
    padding: 4px 8px 0 0; font-weight: 500;
  }

  input.ed, textarea.ed {
    width: 100%; border: 1px solid ${COLORS.rule};
    background: #fff; color: ${COLORS.ink};
    font-family: ${FONT_BODY}; font-size: 16px; line-height: 1.5;
    padding: 12px 14px; outline: none;
  }
  input.ed:focus, textarea.ed:focus { border-color: ${COLORS.ink}; }
  textarea.ed { resize: vertical; min-height: 120px; }

  .card { background: ${COLORS.cardBg}; border: 1px solid ${COLORS.rule};
          padding: 24px 28px; }

  @keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
  .pulse-dot {
    display: inline-block; width: 8px; height: 8px;
    background: ${COLORS.accent}; border-radius: 50%;
    animation: pulse 1.4s ease-in-out infinite;
  }
  .pulse-dot:nth-child(2) { animation-delay: 0.2s; }
  .pulse-dot:nth-child(3) { animation-delay: 0.4s; }

  .nav-bar {
    display: flex; gap: 24px; align-items: center;
  }
  .nav-link {
    font-family: ${FONT_MONO}; font-size: 11px;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: ${COLORS.muted}; text-decoration: none; padding: 6px 0;
    border-bottom: 2px solid transparent;
  }
  .nav-link.active { color: ${COLORS.ink}; border-bottom-color: ${COLORS.ink}; }
  .nav-link:hover { color: ${COLORS.ink}; }
`;
