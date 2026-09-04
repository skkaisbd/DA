/**
 * Client Portal API helper — stores client-only token under different key
 * so it never collides with internal ERP token.
 */
const CLIENT_TOKEN_KEY = 'dewi_client_token';
const CLIENT_USER_KEY = 'dewi_client_user';

export const clientApi = {
  saveSession(token, user) {
    localStorage.setItem(CLIENT_TOKEN_KEY, token);
    localStorage.setItem(CLIENT_USER_KEY, JSON.stringify(user));
  },
  loadSession() {
    const token = localStorage.getItem(CLIENT_TOKEN_KEY);
    const user = localStorage.getItem(CLIENT_USER_KEY);
    if (!token || !user) return null;
    try {
      return { token, user: JSON.parse(user) };
    } catch (e) {
      return null;
    }
  },
  clearSession() {
    localStorage.removeItem(CLIENT_TOKEN_KEY);
    localStorage.removeItem(CLIENT_USER_KEY);
  },
  async request(path, { method = 'GET', body, token } = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`/api/dewi/client-portal${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.detail || data.message || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  },
};

export const fmtCurrency = (n) => {
  const v = Number(n || 0);
  return `Rp ${v.toLocaleString('id-ID', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
};

export const fmtDate = (d) => {
  if (!d) return '-';
  try {
    const dt = new Date(d);
    if (Number.isNaN(dt.getTime())) return d;
    return dt.toLocaleDateString('id-ID', { year: 'numeric', month: 'short', day: 'numeric' });
  } catch (e) {
    return d;
  }
};

export const ORDER_STAGE_LABEL = {
  draft: 'Draft',
  confirmed: 'Konfirmasi',
  material_ready: 'Material Siap',
  cutting: 'Cutting',
  sewing: 'Jahit',
  qc: 'QC',
  packing: 'Packing',
  completed: 'Selesai',
  invoiced: 'Diinvoice',
  cancelled: 'Dibatalkan',
};

export const SAMPLE_STATUS_LABEL = {
  draft: 'Draft',
  in_progress: 'Dikerjakan',
  submitted: 'Menunggu Approval',
  approved: 'Disetujui',
  rejected: 'Ditolak',
  revision_requested: 'Minta Revisi',
};

export const INVOICE_STATUS_LABEL = {
  draft: 'Draft',
  issued: 'Terbit',
  partial_paid: 'Bayar Sebagian',
  paid: 'Lunas',
  overdue: 'Lewat Jatuh Tempo',
  cancelled: 'Dibatalkan',
};
