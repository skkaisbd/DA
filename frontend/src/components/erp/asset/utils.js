/**
 * Asset Management — Shared utilities
 * Extracted from AssetManagementPortal.jsx (Phase 1 refactor)
 */

const API = process.env.REACT_APP_BACKEND_URL || '';

export async function apicall(method, path, token, body) {
  const opts = {
    method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(`${API}${path}`, opts);
  // Always read body once, even on error responses
  let data;
  try {
    data = await r.json();
  } catch {
    data = {};
  }
  if (!r.ok) {
    const msg = data?.detail || data?.message || `HTTP ${r.status}`;
    throw Object.assign(new Error(msg), { status: r.status, data });
  }
  return data;
}

export function fmtCurrency(v) {
  if (!v && v !== 0) return '-';
  return 'Rp ' + Number(v).toLocaleString('id-ID');
}

export function fmtDate(s) {
  if (!s) return '-';
  return new Date(s).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });
}

// Re-export API base for components that need it directly (e.g., multipart/file uploads)
export { API };
