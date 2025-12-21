const BASE_URL = '';

export async function fetchJSON(endpoint) {
  const res = await fetch(`${BASE_URL}${endpoint}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function postJSON(endpoint, data = {}) {
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function putJSON(endpoint, data = {}) {
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function deleteJSON(endpoint) {
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method: 'DELETE'
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// API endpoints
export const api = {
  // Dashboard - single call for all dashboard data
  getDashboard: () => fetchJSON('/api/dashboard'),

  // Status (legacy, use getDashboard instead)
  getStatus: () => fetchJSON('/api/status'),
  getStatsCards: () => fetchJSON('/api/stats/cards'),
  getDbSize: () => fetchJSON('/api/db-size'),

  // Jobs (sync runs)
  getActiveJob: () => fetchJSON('/api/jobs/active'),
  getJobs: (limit = 20) => fetchJSON(`/api/jobs?limit=${limit}`),
  startJob: () => postJSON('/api/jobs'),
  pauseJob: (id) => postJSON(`/api/jobs/${id}/pause`),
  resumeJob: (id) => postJSON(`/api/jobs/${id}/resume`),
  cancelJob: (id) => postJSON(`/api/jobs/${id}/cancel`),
  deleteJob: (id) => deleteJSON(`/api/jobs/${id}`),
  cleanupJobs: (days = 7, status = 'all') => deleteJSON(`/api/jobs/cleanup?days=${days}&status=${status}`),

  // Live worker metrics (poll every 1-2 seconds when job active)
  getLiveMetrics: () => fetchJSON('/api/workers/live'),

  // Legacy aliases (use jobs instead)
  getActiveBatch: () => fetchJSON('/api/jobs/active'),
  getBatches: (limit = 20) => fetchJSON(`/api/jobs?limit=${limit}`),
  startBatch: () => postJSON('/api/jobs'),
  pauseBatch: (id) => postJSON(`/api/jobs/${id}/pause`),
  resumeBatch: (id) => postJSON(`/api/jobs/${id}/resume`),
  cancelBatch: (id) => postJSON(`/api/jobs/${id}/cancel`),

  // Stats
  getStats: () => fetchJSON('/api/stats/cards'),
  getChartData: () => fetchJSON('/api/stats/chart'),
  getDailyStats: () => fetchJSON('/api/stats/daily'),
  getActivity: () => fetchJSON('/api/activity'),
  getRecentUploads: (minutes = 5, limit = 20) => fetchJSON(`/api/uploads/recent?minutes=${minutes}&limit=${limit}`),
  backfillStats: () => postJSON('/api/stats/backfill'),

  // Logs
  getLogs: (limit = 100, level = undefined) => {
    let url = `/api/logs?limit=${limit}`;
    if (level) url += `&level=${encodeURIComponent(level)}`;
    return fetchJSON(url);
  },

  // Files
  getFiles: (page = 1, limit = 50, search = '', status = '', sortBy = '', sortDir = '') => {
    let url = `/api/files?page=${page}&limit=${limit}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    if (status) url += `&status=${encodeURIComponent(status)}`;
    if (sortBy) url += `&sort_by=${encodeURIComponent(sortBy)}`;
    if (sortDir) url += `&sort_dir=${encodeURIComponent(sortDir)}`;
    return fetchJSON(url);
  },

  // Config
  getConfig: () => fetchJSON('/api/config'),
  updateConfig: (config) => putJSON('/api/config', config),
  updateSourceDirs: (dirs) => putJSON('/api/config/source-dirs', { dirs }),

  // Documentation
  getQuickstart: () => fetchJSON('/api/quickstart'),
};
