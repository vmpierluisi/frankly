import React from "react";
import { COLORS } from "../design.js";

export default function VarianceBar({
  mean = 0,
  std = 0,
  height = 8,
  showBand = true,
  accentColor = COLORS.accent,
}) {
  const clamp = (v) => Math.max(0, Math.min(100, v));
  const meanPct = clamp(mean);
  const lo = clamp(mean - std);
  const hi = clamp(mean + std);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height,
        background: COLORS.rule,
        overflow: "hidden",
      }}
    >
      {/* filled bar up to mean */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: `${meanPct}%`,
          height: "100%",
          background: accentColor,
        }}
      />
      {/* variance band */}
      {showBand && std > 0 && (
        <div
          style={{
            position: "absolute",
            left: `${lo}%`,
            top: 0,
            width: `${hi - lo}%`,
            height: "100%",
            background: COLORS.accentSoft,
            opacity: 0.6,
          }}
        />
      )}
      {/* centre tick */}
      <div
        style={{
          position: "absolute",
          left: `${meanPct}%`,
          top: 0,
          width: 2,
          height: "100%",
          background: accentColor,
          transform: "translateX(-1px)",
        }}
      />
    </div>
  );
}
