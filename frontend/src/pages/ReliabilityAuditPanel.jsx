import React, { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";

/**
 * Roadmap 2 / PR #6 follow-up — the per-position audit page is now a
 * legacy entry-point that simply forwards to the consolidated Audit tab
 * on the manager dashboard. The dashboard renders the same charts via
 * the shared ``components/AuditCharts.jsx`` primitives.
 */
export default function ReliabilityAuditPanel() {
  const { companyId } = useParams();
  const nav = useNavigate();
  useEffect(() => {
    nav(
      `/manager?tab=audit&scope=position&positionId=${encodeURIComponent(companyId)}`,
      { replace: true },
    );
  }, [companyId, nav]);
  return null;
}
