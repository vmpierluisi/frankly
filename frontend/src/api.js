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
};

// ---------- Company endpoints ----------
export const companies = {
  list: () => request("/companies", { auth: true }),
  get: (id) => request(`/companies/${id}`, { auth: true }),
  create: (payload) =>
    request("/companies", { method: "POST", body: payload, auth: true }),
  update: (id, payload) =>
    request(`/companies/${id}`, { method: "PUT", body: payload, auth: true }),
  remove: (id) =>
    request(`/companies/${id}`, { method: "DELETE", auth: true, raw: true }),
  leaderboard: (id) => request(`/companies/${id}/leaderboard`, { auth: true }),
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
    request(`/companies/${companyId}/scenarios`, { auth: true }),
  draft: (companyId) =>
    request(`/companies/${companyId}/scenarios/draft`, { method: "POST", auth: true }),
  create: (companyId, payload) =>
    request(`/companies/${companyId}/scenarios`, { method: "POST", body: payload, auth: true }),
  update: (companyId, scenarioId, payload) =>
    request(`/companies/${companyId}/scenarios/${scenarioId}`, {
      method: "PATCH", body: payload, auth: true,
    }),
  remove: (companyId, scenarioId) =>
    request(`/companies/${companyId}/scenarios/${scenarioId}`, {
      method: "DELETE", auth: true, raw: true,
    }),
};

// ---------- Synthetic team ----------
export const team = {
  list: (companyId) =>
    request(`/companies/${companyId}/team`, { auth: true }),
  synthesize: (companyId) =>
    request(`/companies/${companyId}/team/synthesize`, { method: "POST", auth: true }),
  update: (companyId, teammateId, payload) =>
    request(`/companies/${companyId}/team/${teammateId}`, {
      method: "PATCH",
      body: payload,
      auth: true,
    }),
  remove: (companyId, teammateId) =>
    request(`/companies/${companyId}/team/${teammateId}`, {
      method: "DELETE",
      auth: true,
      raw: true,
    }),
};

export const API_BASE = BASE;
