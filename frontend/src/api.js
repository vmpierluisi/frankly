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
  create: (payload) => request("/candidates", { method: "POST", body: payload }),
  get: (id) => request(`/candidates/${id}`),
  update: (id, payload) =>
    request(`/candidates/${id}`, { method: "PATCH", body: payload }),
  list: () => request("/candidates", { auth: true }),
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
  search: (company_id, { refresh = false } = {}) =>
    request("/matches/search", {
      method: "POST",
      body: { company_id, refresh },
      auth: true,
    }),
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/matches${qs ? `?${qs}` : ""}`, { auth: true });
  },
  get: (id) => request(`/matches/${id}`, { auth: true }),
};

export const API_BASE = BASE;
