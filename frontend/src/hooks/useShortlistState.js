import { useCallback, useEffect, useRef, useState } from "react";
import { positions as positionsApi } from "../api.js";

// Manager Shortlist V7 — data + selection state for ShortlistComparePage.
//
// Owns:
//   * the fetched ShortlistComparisonReport (source of truth for every tab)
//   * the top-N size (auto mode) and explicit candidate-id set
//   * chip toggling between the active set and "also considered"
//
// Chip toggles re-slice from the already-fetched report when possible (the
// backend returns full CandidateInReport objects for both groups) and only
// refetch when a needed candidate isn't present in the current payload.
export function useShortlistState(positionId, { initialN = 3, initialIds = null } = {}) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [topN, setTopN] = useState(initialN);
  // null → auto top-N mode; array → explicit set mode.
  const [explicitIds, setExplicitIds] = useState(initialIds);

  const reqId = useRef(0);

  const fetchReport = useCallback(
    async (args = {}) => {
      const n = args.topN ?? topN;
      // Distinguish "not provided" (use current explicit set) from an explicit
      // null (force auto top-N mode). A bare `??` would wrongly fall back to the
      // stale explicit set when the caller passes null on purpose.
      const candidateIds = "candidateIds" in args ? args.candidateIds : explicitIds;
      const id = ++reqId.current;
      setLoading(true);
      setError("");
      try {
        const data = await positionsApi.shortlist(positionId, {
          topN: n,
          candidateIds,
        });
        // Ignore stale responses (a newer request has since fired).
        if (id === reqId.current) setReport(data);
        return data;
      } catch (e) {
        if (id === reqId.current) setError(e.message || String(e));
        throw e;
      } finally {
        if (id === reqId.current) setLoading(false);
      }
    },
    [positionId, topN, explicitIds],
  );

  // Initial load + reload whenever the position changes.
  useEffect(() => {
    fetchReport({ topN: initialN, candidateIds: initialIds }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionId]);

  const changeTopN = useCallback(
    (n) => {
      setTopN(n);
      setExplicitIds(null); // widening N returns to auto mode
      fetchReport({ topN: n, candidateIds: null }).catch(() => {});
    },
    [fetchReport],
  );

  // Add an also-considered candidate to the active comparison set.
  const addCandidate = useCallback(
    (candidateId) => {
      if (!report) return;
      const current = report.candidates.map((c) => c.id);
      if (current.includes(candidateId)) return;
      const next = [...current, candidateId];
      const found = report.available_candidates.find((c) => c.id === candidateId);
      setExplicitIds(next);
      if (found) {
        // Optimistic client-side move for instant feedback…
        setReport({
          ...report,
          candidates: [...report.candidates, found],
          available_candidates: report.available_candidates.filter(
            (c) => c.id !== candidateId,
          ),
          selection_mode: "explicit",
          top_n_applied: null,
        });
      }
      // …then reconcile with the server so top/weak markers + deltas are
      // recomputed across the new active set.
      fetchReport({ candidateIds: next }).catch(() => {});
    },
    [report, fetchReport],
  );

  // Remove a candidate from the active set (moves to also-considered).
  const removeCandidate = useCallback(
    (candidateId) => {
      if (!report) return;
      const remaining = report.candidates.filter((c) => c.id !== candidateId);
      if (remaining.length === 0) return; // never empty the comparison
      const moved = report.candidates.find((c) => c.id === candidateId);
      const nextIds = remaining.map((c) => c.id);
      setReport({
        ...report,
        candidates: remaining,
        available_candidates: moved
          ? [moved, ...report.available_candidates]
          : report.available_candidates,
        selection_mode: "explicit",
        top_n_applied: null,
      });
      setExplicitIds(nextIds);
      // Reconcile markers/deltas across the shrunk active set.
      fetchReport({ candidateIds: nextIds }).catch(() => {});
    },
    [report, fetchReport],
  );

  return {
    report,
    loading,
    error,
    topN,
    explicitIds,
    selectionMode: report?.selection_mode ?? "auto_top_n",
    changeTopN,
    addCandidate,
    removeCandidate,
    refetch: fetchReport,
    setReport,
  };
}
