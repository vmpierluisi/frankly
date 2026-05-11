// Thin fetch wrapper:
//  * VITE_API_BASE_URL injection (docker-compose or local dev)
//  * Bearer token from active Supabase session for auth-gated routes
//  * JSON content-type handling + error surfacing

const BASE = import.meta.env?.VITE_API_BASE_URL || "";

// Lazily imported to avoid circular deps; set via setSessionGetter() at app init.
let _getSession = () => null;

export function setSessionGetter(fn) {
  _getSession = fn;
}

async function authHeader() {
  const session = await _getSession();
  if (session?.access_token) {
    return { Authorization: `Bearer ${session.access_token}` };
  }
  return {};
}

// ---------- Core request helper ----------
async function request(
  path,
  { method = "GET", body, auth = false, headers = {}, raw = false } = {},
) {
  const authHdr = auth ? await authHeader() : {};
  const init = {
    method,
    headers: {
      ...(body && !(body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...authHdr,
      ...headers,
    },
  };
  if (body !== undefined) {
    init.body = body instanceof FormData ? body : JSON.stringify(body);
  }

  const resp = await fetch(`${BASE}${path}`, init);
  if (!resp.ok) {
    const text = await resp.text();
    const err = new Error(`${resp.status} ${resp.statusText}: ${text}`);
    err.status = resp.status;
    throw err;
  }
  if (raw || resp.status === 204) return resp;
  return resp.json();
}

// ---------- Candidate endpoints ----------
export const candidates = {
  getInstruments: () => request("/candidates/instruments"),
  // Legacy anonymous intake (kept for backwards compat)
  create: (payload) => request("/candidates", { method: "POST", body: payload }),
  get: (id) => request(`/candidates/${id}`),
  update: (id, payload) =>
    request(`/candidates/${id}`, { method: "PATCH", body: payload }),
  list: (params = {}) => {
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null))
    ).toString();
    return request(`/candidates${qs ? `?${qs}` : ""}`, { auth: true });
  },
  // Authenticated self-service
  me: () => request("/candidates/me", { auth: true }),
  updateMe: (payload) =>
    request("/candidates/me", { method: "PATCH", body: payload, auth: true }),
  submitAssessment: (payload) =>
    request("/candidates/me/assessment", { method: "POST", body: payload, auth: true }),
  aggregatePersona: () =>
    request("/candidates/me/persona/aggregate", { method: "POST", auth: true }),
  getPersona: () =>
    request("/candidates/me/persona", { auth: true }),
  // Verified-profile (CV/Github/portfolio extraction).
  getProfile: () => request("/candidates/me/profile", { auth: true }),
  patchProfile: (payload) =>
    request("/candidates/me/profile", { method: "PATCH", body: payload, auth: true }),
  extractProfile: () =>
    request("/candidates/me/profile/extract", { method: "POST", auth: true }),
  // Manager-side: any candidate's verified profile.
  getCandidateProfile: (id) =>
    request(`/candidates/${id}/profile`, { auth: true }),
};

// ---------- Organization endpoints (Roadmap 2 / PR #2d) ----------
export const organizations = {
  list: () => request("/organizations", { auth: true }),
  get: (id) => request(`/organizations/${id}`, { auth: true }),
  create: (payload) =>
    request("/organizations", { method: "POST", body: payload, auth: true }),
  update: (id, payload) =>
    request(`/organizations/${id}`, { method: "PATCH", body: payload, auth: true }),
  remove: (id) =>
    request(`/organizations/${id}`, { method: "DELETE", auth: true, raw: true }),
  listTeams: (id) => request(`/organizations/${id}/teams`, { auth: true }),
  createTeam: (id, payload) =>
    request(`/organizations/${id}/teams`, {
      method: "POST",
      body: payload,
      auth: true,
    }),
};

// ---------- Team endpoints ----------
export const teams = {
  get: (id) => request(`/teams/${id}`, { auth: true }),
  update: (id, payload) =>
    request(`/teams/${id}`, { method: "PATCH", body: payload, auth: true }),
  remove: (id) =>
    request(`/teams/${id}`, { method: "DELETE", auth: true, raw: true }),
  listPositions: (id) => request(`/teams/${id}/positions`, { auth: true }),
};

// ---------- Company endpoints (legacy: a Company is a Position) ----------
export const positions = {
  list: () => request("/positions", { auth: true }),
  get: (id) => request(`/positions/${id}`, { auth: true }),
  create: (payload) =>
    request("/positions", { method: "POST", body: payload, auth: true }),
  update: (id, payload) =>
    request(`/positions/${id}`, { method: "PUT", body: payload, auth: true }),
  remove: (id) =>
    request(`/positions/${id}`, { method: "DELETE", auth: true, raw: true }),
  leaderboard: (id) => request(`/positions/${id}/leaderboard`, { auth: true }),
};

// ---------- Templates (artifact parse + criteria extract) ----------
export const templates = {
  parseArtifact: async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request("/templates/parse-artifact", {
      method: "POST",
      body: fd,
      auth: true,
    });
  },
  extractCriteria: (artifacts, role) =>
    request(
      `/templates/extract-criteria${role ? `?role=${encodeURIComponent(role)}` : ""}`,
      { method: "POST", body: artifacts, auth: true },
    ),
};

// ---------- Matches ----------
export const matches = {
  trigger: (candidate_id, company_id) =>
    request("/matches/trigger", {
      method: "POST",
      body: { candidate_id, company_id },
      auth: true,
    }),
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/matches${qs ? `?${qs}` : ""}`, { auth: true });
  },
  get: (id) => request(`/matches/${id}`, { auth: true }),
  listRollouts: (matchId) =>
    request(`/matches/${matchId}/rollouts`, { auth: true }),
  getRollout: (matchId, rolloutId) =>
    request(`/matches/${matchId}/rollouts/${rolloutId}`, { auth: true }),
  getBaseline: (matchId) =>
    request(`/matches/${matchId}/baseline`, { auth: true }),
};

// ---------- Scenario library ----------
export const scenarios = {
  list: (companyId) =>
    request(`/positions/${companyId}/scenarios`, { auth: true }),
  draft: (companyId) =>
    request(`/positions/${companyId}/scenarios/draft`, { method: "POST", auth: true }),
  create: (companyId, payload) =>
    request(`/positions/${companyId}/scenarios`, { method: "POST", body: payload, auth: true }),
  update: (companyId, scenarioId, payload) =>
    request(`/positions/${companyId}/scenarios/${scenarioId}`, {
      method: "PATCH", body: payload, auth: true,
    }),
  remove: (companyId, scenarioId) =>
    request(`/positions/${companyId}/scenarios/${scenarioId}`, {
      method: "DELETE", auth: true, raw: true,
    }),
};

// ---------- Synthetic team ----------
export const team = {
  list: (companyId) =>
    request(`/positions/${companyId}/team`, { auth: true }),
  synthesize: (companyId) =>
    request(`/positions/${companyId}/team/synthesize`, { method: "POST", auth: true }),
  update: (companyId, teammateId, payload) =>
    request(`/positions/${companyId}/team/${teammateId}`, {
      method: "PATCH",
      body: payload,
      auth: true,
    }),
  remove: (companyId, teammateId) =>
    request(`/positions/${companyId}/team/${teammateId}`, {
      method: "DELETE",
      auth: true,
      raw: true,
    }),
};

// ---------- Interviews (Roadmap 2 / PR #4) ----------
export const interviews = {
  propose: (match_id, proposed_slots) =>
    request("/interviews", {
      method: "POST",
      body: { match_id, proposed_slots },
      auth: true,
    }),
  listForManager: (candidate_id) => {
    const qs = candidate_id ? `?candidate_id=${encodeURIComponent(candidate_id)}` : "";
    return request(`/interviews${qs}`, { auth: true });
  },
  listMine: () => request("/interviews/me", { auth: true }),
  accept: (id, selected_slot, message) =>
    request(`/interviews/${id}/accept`, {
      method: "POST",
      body: { selected_slot, message: message || null },
      auth: true,
    }),
  decline: (id, message) =>
    request(`/interviews/${id}/decline`, {
      method: "POST",
      body: { message: message || null },
      auth: true,
    }),
  counter: (id, counter_slots, message) =>
    request(`/interviews/${id}/counter`, {
      method: "POST",
      body: { counter_slots, message: message || null },
      auth: true,
    }),
};

// ---------- Notifications ----------
export const notifications = {
  list: () => request("/notifications", { auth: true }),
  markRead: (id) =>
    request(`/notifications/${id}/read`, { method: "POST", auth: true }),
  markAllRead: () =>
    request("/notifications/read-all", { method: "POST", auth: true }),
  dismiss: (id) =>
    request(`/notifications/${id}/dismiss`, { method: "POST", auth: true }),
};

// ---------- Audit panel (Roadmap 2 / PR #6) ----------
export const audit = {
  reliability: (positionId) =>
    request(`/audit/positions/${positionId}/reliability`, { auth: true }),
  fairness: (positionId) =>
    request(`/audit/positions/${positionId}/fairness`, { auth: true }),
  exportCsvUrl: (positionId) =>
    `${BASE}/audit/positions/${positionId}/export.csv`,
  // PR #6 follow-up — multi-position overview.
  reliabilityOverview: (scope = "all") =>
    request(`/audit/overview/reliability?scope=${encodeURIComponent(scope)}`, { auth: true }),
  fairnessOverview: (scope = "all") =>
    request(`/audit/overview/fairness?scope=${encodeURIComponent(scope)}`, { auth: true }),
  exportOverviewCsvUrl: (scope = "all") =>
    `${BASE}/audit/overview/export.csv?scope=${encodeURIComponent(scope)}`,
};

// ---------- Calibration (Roadmap 2 / PR #5) ----------
export const calibration = {
  list: () => request("/calibration", { auth: true }),
  get: (id) => request(`/calibration/${id}`, { auth: true }),
  submit: (id, { selection_index = null, free_text = null } = {}) =>
    request(`/calibration/${id}/submit`, {
      method: "POST",
      body: { selection_index, free_text },
      auth: true,
    }),
  timeline: () => request("/calibration/timeline", { auth: true }),
};

export const API_BASE = BASE;
