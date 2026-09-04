/**
 * procApi.js — helper HTTP tunggal untuk Portal Pengadaan.
 *
 * Semua modul pengadaan memakai helper ini supaya:
 *  · header Authorization tidak ditulis ulang di 5 tempat,
 *  · pesan error backend (FastAPI `detail`) SELALU sampai ke pengguna
 *    (dulu banyak modul menelan error dengan `catch → setData([])` sehingga
 *    layar tampak "tidak ada data" padahal ada kesalahan nyata),
 *  · endpoint terkumpul di satu tempat (mudah diaudit vs backend).
 */

const authHeaders = (token) => ({
  Authorization: `Bearer ${token}`,
  'Content-Type': 'application/json',
});

async function handle(res) {
  if (res.ok) {
    const text = await res.text();
    if (!text) return null;
    try { return JSON.parse(text); } catch { return text; }
  }
  let detail = `HTTP ${res.status}`;
  try {
    const j = await res.json();
    if (typeof j?.detail === 'string') detail = j.detail;
    else if (Array.isArray(j?.detail)) detail = j.detail.map((d) => d?.msg || JSON.stringify(d)).join('; ');
    else if (j?.detail) detail = JSON.stringify(j.detail);
    else if (j?.message) detail = j.message;
  } catch { /* body bukan JSON — pakai pesan default */ }
  throw new Error(detail);
}

export const apiGet = (token, path) =>
  fetch(path, { headers: authHeaders(token) }).then(handle);

export const apiPost = (token, path, body) =>
  fetch(path, { method: 'POST', headers: authHeaders(token), body: JSON.stringify(body || {}) }).then(handle);

export const apiPut = (token, path, body) =>
  fetch(path, { method: 'PUT', headers: authHeaders(token), body: JSON.stringify(body || {}) }).then(handle);

export const apiDelete = (token, path) =>
  fetch(path, { method: 'DELETE', headers: authHeaders(token) }).then(handle);

// ── Endpoint pengadaan (SSOT daftar path) ──────────────────────────────────
export const EP = {
  overview: '/api/procurement/overview',
  pipeline: '/api/procurement/pipeline',
  spend: (months) => `/api/procurement/spend-analysis?months=${months}`,
  suppliers: (qs = '') => `/api/procurement/suppliers${qs}`,
  supplierOptions: '/api/procurement/suppliers/options',
  supplierMeta: '/api/procurement/suppliers/meta',
  supplier: (id) => `/api/procurement/suppliers/${id}`,
  supplierActivate: (id) => `/api/procurement/suppliers/${id}/activate`,
  priceList: (id) => `/api/procurement/suppliers/${id}/price-list`,
  priceRow: (id, rowId) => `/api/procurement/suppliers/${id}/price-list/${rowId}`,
  priceLookup: (materialId, supplierId) =>
    `/api/procurement/price-lookup?material_id=${materialId}${supplierId ? `&supplier_id=${supplierId}` : ''}`,
  migratePreview: '/api/procurement/suppliers/migrate/preview',
  migrate: '/api/procurement/suppliers/migrate-from-legacy',
  scorecard: (days) => `/api/procurement/supplier-scorecard?period_days=${days}`,
  supplierScorecard: (id) => `/api/procurement/suppliers/${id}/scorecard`,
  materials: '/api/rahaza/materials',
  uomOptions: (ids) => `/api/rahaza/materials/uom-options?material_ids=${ids}`,
  purchaseOrders: (qs = '') => `/api/rahaza/purchase-orders${qs}`,
  grsForInvoice: '/api/rahaza/grs/available-for-invoice',
  apFromGr: '/api/rahaza/ap-invoices/from-gr',
  threeWay: '/api/rahaza/3way-match',
};

export const fmtRp = (n) =>
  `Rp ${Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 0 })}`;

export const fmtNum = (n, max = 4) =>
  Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: max });

export const fmtDate = (d) =>
  d ? new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : '-';

export const PAYMENT_TERM_LABEL = {
  cod: 'COD', cbd: 'Bayar di Muka', net7: 'NET 7', net14: 'NET 14',
  net30: 'NET 30', net45: 'NET 45', net60: 'NET 60', net90: 'NET 90',
};

export const CATEGORY_LABEL = {
  yarn: 'Benang', fabric: 'Kain', accessory: 'Aksesoris', packaging: 'Kemasan',
  chemical: 'Kimia / Pewarna', spare_part: 'Suku Cadang', office: 'ATK / Kantor',
  asset: 'Aset / Mesin', service: 'Jasa', other: 'Lainnya',
};
