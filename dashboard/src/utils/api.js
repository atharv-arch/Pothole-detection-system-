// ═══════════════════════════════════════════════════════════
// APIS v5.0 — API Client Utilities
// ═══════════════════════════════════════════════════════════

const API_BASE = '/api';

export async function fetchApi(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  try {
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    });
    if (!response.ok) throw new Error(`API error: ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error(`API call failed: ${endpoint}`, error);
    return null;
  }
}

export const api = {
  // Potholes
  getPotholes: (params = '') => fetchApi(`/potholes${params ? '?' + params : ''}`),
  getPotholesGeoJSON: (highway) => fetchApi(`/potholes/geojson${highway ? '?highway=' + highway : ''}`),
  getPothole: (uuid) => fetchApi(`/potholes/${uuid}`),
  getPotholeTimeline: (uuid) => fetchApi(`/potholes/${uuid}/timeline`),
  getPotholeImages: (uuid) => fetchApi(`/potholes/${uuid}/images`),

  // Complaints
  getComplaints: (params = '') => fetchApi(`/complaints${params ? '?' + params : ''}`),
  getComplaint: (id) => fetchApi(`/complaints/${id}`),
  getEscalations: () => fetchApi('/complaints/escalations/all'),

  // Stretches
  getStretches: () => fetchApi('/stretches'),
  getStretchDetail: (hid) => fetchApi(`/stretches/${hid}`),

  // Analytics
  getAnalyticsSummary: () => fetchApi('/analytics/summary'),

  // Predictive
  getPredictions: () => fetchApi('/predict'),
};

// Severity color mapping
export const SEVERITY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
};

// Status label mapping
export const STATUS_LABELS = {
  detected: 'Detected',
  complaint_filed: 'Complaint Filed',
  filed: 'Filed',
  escalated_l2: 'Escalated T2',
  escalated_l3: 'Escalated T3',
  sla_breach_public: 'SLA Breach',
  verified_repaired: 'Repaired',
  repair_partial: 'Partial Repair',
  pred_unconfirmed: 'Predicted',
};

// Date formatter
export function formatDate(dateStr) {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  });
}

export function formatDateTime(dateStr) {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  return d.toLocaleString('en-IN', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

export function timeAgo(dateStr) {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}
