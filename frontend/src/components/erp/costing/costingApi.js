/**
 * costingApi — pembungkus fetch untuk layar HPP per Potong (`/api/costing`).
 *
 * Semua angka HPP datang dari SSOT backend `core/product_costing`; layar tidak
 * pernah menghitung ulang sendiri supaya tidak ada dua versi kebenaran.
 */
const BASE = process.env.REACT_APP_BACKEND_URL || '';

export async function costingApi(method, path, token, body) {
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token || localStorage.getItem('erp_token')}`,
    },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE}/api/costing${path}`, opts);
  let data = null;
  try { data = await res.json(); } catch { data = null; }
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `HTTP ${res.status}`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return data;
}

export const fmtRp = (v) => {
  const n = Number(v || 0);
  return `Rp${n.toLocaleString('id-ID', { maximumFractionDigits: 0 })}`;
};

export const fmtNum = (v, d = 2) => {
  const n = Number(v || 0);
  return n.toLocaleString('id-ID', { maximumFractionDigits: d });
};

export const fmtPct = (v) => `${Number(v || 0).toLocaleString('id-ID', { maximumFractionDigits: 1 })}%`;

/** Label sumber angka — layar TIDAK BOLEH menampilkan angka tanpa asal. */
export const SOURCE_LABEL = {
  owner: { text: 'dikunci pemilik', cls: 'bg-primary/10 text-primary border-primary/25' },
  cmt_job_actual: { text: 'rata-rata job CMT', cls: 'bg-emerald-400/10 text-emerald-600 border-emerald-300/25' },
  wip_actual: { text: 'upah nyata produksi', cls: 'bg-emerald-400/10 text-emerald-600 border-emerald-300/25' },
  settings_process_rates: { text: 'tarif standar proses', cls: 'bg-sky-400/10 text-sky-600 border-sky-300/25' },
  settings_fallback: { text: 'tarif cadangan', cls: 'bg-amber-400/10 text-amber-600 border-amber-300/25' },
  none: { text: 'belum ada', cls: 'bg-red-400/10 text-red-500 border-red-300/25' },
};

export const COST_SOURCE_LABEL = {
  purchase: { text: 'dari pembelian', cls: 'text-emerald-600 dark:text-emerald-300' },
  opening: { text: 'harga awal', cls: 'text-sky-600 dark:text-sky-300' },
  master: { text: 'nilai lama', cls: 'text-amber-600 dark:text-amber-300' },
  none: { text: 'belum ada harga', cls: 'text-red-500' },
};

export const STATUS_META = {
  ready: { label: 'Siap', cls: 'bg-emerald-400/10 text-emerald-600 border-emerald-300/25' },
  partial: { label: 'Sebagian', cls: 'bg-amber-400/10 text-amber-600 border-amber-300/25' },
  no_bom: { label: 'Belum ada BOM', cls: 'bg-red-400/10 text-red-500 border-red-300/25' },
};

/** Layar tujuan perbaikan untuk tiap jenis kekurangan (dipakai tombol "Perbaiki"). */
export const GAP_LABEL = {
  bom_missing: 'BOM belum ada',
  bom_empty: 'BOM masih kosong',
  bom_line_unlinked: 'Baris BOM belum tertaut master',
  bom_line_uom: 'Satuan baris BOM belum jelas',
  material_unvalued: 'Bahan belum punya harga',
  cmt_rate_missing: 'Upah CMT belum ada',
  internal_labor_missing: 'Upah cutting/internal belum ada',
  selling_price_missing: 'Harga jual belum ada',
};
