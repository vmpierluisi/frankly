// Tiny fetch wrapper with:
//  * VITE_API_BASE_URL injection (docker-compose or local dev)
//  * Optional basic-auth header for manager routes, read from sessionStorage
//  * JSON content-type handling + error surfacing

// In dev (no VITE_API_BASE_URL set) BASE is empty — requests go to the same
// origin and Vite's proxy forwards them to localhost:8000. In production /
// Docker, set VITE_API_BASE_URL to the real backend URL.
const BASE = import.meta.env?.VITE_API_BASE_URL || "";

// ---------- Manager credentials (sessionStorage-backed) ----------
const CREDS_KEY = "hiring-sim:manager-creds";

export function setManagerCreds(username, password) {
  const encoded = btoa(`${username}:${password}`);
  sessionStorage.setItem(CREDS_KEY, encoded);
}

export function clearManagerCreds() {
  sessionStorage.removeItem(CREDS_KEY);
}

export function hasManagerCreds() {
  return !!sessionStorage.getItem(CREDS_KEY);
}

function authHeader() {
  const enc = sessionStorage.getItem(CREDS_KEY);
  return enc ? { Authorization: `Basic ${enc}` } : {};
}

// ---------- Candidate ID (localStorage-backed) ----------
const CANDIDATE_KEY = "hiring-sim:candidate-id";

export function getCandidateId() {
  return localStorage.getItem(CANDIDATE_KEY);
}

export function setCandidateId(id) {
  if (id) localStorage.setItem(CANDIDATE_KEY, id);
}

export function clearCandidateId() {
  localStorage.removeItem(CANDIDATE_KEY);
}

// ---------- Core request helper ----------
async function request(
  path,
  { method = "GET", body, manager = false, headers = {}, raw = false } = {},
) {
  const init = {
    method,
    headers: {
      ...(body && !(body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(manager ? authHeader() : {}),
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
  list: () => request("/candidates", { manager: true }),
};

// ---------- Company endpoints ----------
export const companies = {
  list: () => request("/companies", { manager: true }),
  get: (id) => request(`/companies/${id}`, { manager: true }),
  create: (payload) =>
    request("/companies", { method: "POST", body: payload, manager: true }),
  update: (id, payload) =>
    request(`/companies/${id}`, { method: "PUT", body: payload, manager: true }),
  remove: (id) =>
    request(`/companies/${id}`, { method: "DELETE", manager: true, raw: true }),
};

// ---------- Templates (artifact parse + criteria extract) ----------
export const templates = {
  parseArtifact: async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request("/templates/parse-artifact", {
      method: "POST",
      body: fd,
      manager: true,
    });
  },
  extractCriteria: (artifacts, role) =>
    request(
      `/templates/extract-criteria${role ? `?role=${encodeURIComponent(role)}` : ""}`,
      { method: "POST", body: artifacts, manager: true },
    ),
};

// ---------- Matches ----------
export const matches = {
  trigger: (candidate_id, company_id) =>
    request("/matches/trigger", {
      method: "POST",
      body: { candidate_id, company_id },
      manager: true,
    }),
  search: (company_id, { refresh = false } = {}) =>
    request("/matches/search", {
      method: "POST",
      body: { company_id, refresh },
      manager: true,
    }),
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/matches${qs ? `?${qs}` : ""}`, { manager: true });
  },
  get: (id) => request(`/matches/${id}`, { manager: true }),
};

export const API_BASE = BASE;
