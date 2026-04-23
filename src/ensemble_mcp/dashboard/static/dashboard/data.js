/* ensemble-mcp — API fetch layer + language colors */

/**
 * Fetch helper: calls endpoint, parses JSON, unwraps {ok, data} envelope.
 * Throws on network errors or when ok === false.
 */
async function _apiFetch(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  const json = await res.json();
  if (!json.ok) {
    const msg = json.error?.message || `API error: ${res.status}`;
    const err = new Error(msg);
    err.code = json.error?.code;
    err.retryable = json.error?.retryable;
    throw err;
  }
  return json.data;
}

const API = {
  /** GET /api/summary — aggregate counts and recent activity. */
  async summary() { return _apiFetch("/api/summary"); },

  /** GET /api/health — server health, version, DB size, counts. */
  async health() { return _apiFetch("/api/health"); },

  /** GET /api/patterns — paginated pattern list. */
  async patterns(params = {}) {
    const q = new URLSearchParams();
    if (params.limit != null) q.set("limit", params.limit);
    if (params.offset != null) q.set("offset", params.offset);
    if (params.category && params.category !== "all") q.set("category", params.category);
    const qs = q.toString();
    return _apiFetch(`/api/patterns${qs ? "?" + qs : ""}`);
  },

  /** DELETE /api/patterns/{id} */
  async patternDelete(id) {
    return _apiFetch(`/api/patterns/${id}`, { method: "DELETE" });
  },

  /** PUT /api/patterns/{id} — edit pattern fields. */
  async patternUpdate(id, data) {
    return _apiFetch(`/api/patterns/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },

  /** POST /api/patterns/prune — prune stale patterns. */
  async patternsPrune(maxAgeDays = 90) {
    return _apiFetch("/api/patterns/prune", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_age_days: maxAgeDays }),
    });
  },

  /** GET /api/skills — suggestions + tracked skills. */
  async skills() { return _apiFetch("/api/skills"); },

  /** GET /api/skills/stale — stale skills. */
  async skillsStale() { return _apiFetch("/api/skills/stale"); },

  /** POST /api/skills/suggestions/{id}/action */
  async skillAction(id, action) {
    return _apiFetch(`/api/skills/suggestions/${id}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
  },

  /** DELETE /api/skills/tracked/{id} */
  async skillDelete(id) {
    return _apiFetch(`/api/skills/tracked/${id}`, { method: "DELETE" });
  },

  /** GET /api/projects — indexed projects. */
  async projects() { return _apiFetch("/api/projects"); },

  /** GET /api/projects/{encodedPath} — single project detail. */
  async projectDetail(path) {
    return _apiFetch(`/api/projects/${encodeURIComponent(path)}`);
  },

  /** GET /api/projects/{encodedPath}/health — project health. */
  async projectHealth(path) {
    return _apiFetch(`/api/projects/${encodeURIComponent(path)}/health`);
  },

  /** POST /api/projects/{encodedPath}/reindex */
  async projectReindex(path) {
    return _apiFetch(`/api/projects/${encodeURIComponent(path)}/reindex`, { method: "POST" });
  },

  /** DELETE /api/projects/{encodedPath} */
  async projectDelete(path) {
    return _apiFetch(`/api/projects/${encodeURIComponent(path)}`, { method: "DELETE" });
  },

  /** GET /api/drift — drift check history. */
  async drift(params = {}) {
    const q = new URLSearchParams();
    if (params.limit != null) q.set("limit", params.limit);
    const qs = q.toString();
    return _apiFetch(`/api/drift${qs ? "?" + qs : ""}`);
  },

  /** GET /api/sessions — paginated session list. */
  async sessions(params = {}) {
    const q = new URLSearchParams();
    if (params.limit != null) q.set("limit", params.limit);
    if (params.offset != null) q.set("offset", params.offset);
    const qs = q.toString();
    return _apiFetch(`/api/sessions${qs ? "?" + qs : ""}`);
  },

  /** GET /api/sessions/{id} — single session detail. */
  async sessionDetail(id) { return _apiFetch(`/api/sessions/${encodeURIComponent(id)}`); },

  /** GET /api/settings — current config. */
  async settings() { return _apiFetch("/api/settings"); },

  /** GET /api/settings/schema — field schema for form. */
  async settingsSchema() { return _apiFetch("/api/settings/schema"); },

  /** PUT /api/settings — update config. */
  async settingsUpdate(data) {
    return _apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },

  /** GET /api/reports/full — full bug report. */
  async reportsFull() { return _apiFetch("/api/reports/full"); },

  /** GET /api/reports/history — scan history. */
  async reportsHistory() { return _apiFetch("/api/reports/history"); },

  /** GET /api/reports/summary — overview summary. */
  async reportsSummary() { return _apiFetch("/api/reports/summary"); },

  /** POST /api/reset — reset all data. */
  async reset() {
    return _apiFetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: true }),
    });
  },
};

/* language colors */
const LANG_COLOR = {
  python: "#3572A5", typescript: "#3178C6", javascript: "#F7DF1E",
  go: "#00ADD8", rust: "#DEA584", php: "#4F5D95", ruby: "#701516",
  java: "#B07219", kotlin: "#A97BFF", swift: "#F05138",
  c: "#555555", "c++": "#F34B7D", "c#": "#178600",
  vue: "#41B883", svelte: "#FF3E00", html: "#E34C26",
  css: "#563D7C", scss: "#C6538C", less: "#1D365D",
  json: "#292929", yaml: "#CB171E", toml: "#9C4221", xml: "#0060AC",
  markdown: "#083FA1", sql: "#E38C00", shell: "#89E051",
  dockerfile: "#384D54", terraform: "#844FBA",
};
function langColor(name) { return LANG_COLOR[name?.toLowerCase?.()] || "#6366F1"; }

window.API = API;
window.langColor = langColor;
