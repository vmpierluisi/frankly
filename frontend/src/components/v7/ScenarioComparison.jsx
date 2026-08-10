import React, { forwardRef, useImperativeHandle } from "react";
import { COLORS } from "../../design.js";

// Placeholder — full implementation lands in Phase 3.
const ScenarioComparison = forwardRef(function ScenarioComparison(_props, ref) {
  useImperativeHandle(ref, () => ({ flashCandidate: () => {} }));
  return (
    <div style={{ padding: "48px 0", color: COLORS.muted, fontStyle: "italic" }}>
      Scenario comparison — coming in Phase 3.
    </div>
  );
});

export default ScenarioComparison;
