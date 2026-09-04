/**
 * Workspace Portal — shared utilities, constants, and a tiny formula evaluator.
 *
 * No React imports here — only pure helpers plus a few lucide icons (for ACCESS_CONFIG).
 */
import { Crown, Pencil, Eye } from 'lucide-react';

export const API = process.env.REACT_APP_BACKEND_URL || '';

/** Authenticated fetch, throws on !ok, returns parsed JSON. */
export const apicall = async (method, path, token, body = null) => {
  const opts = {
    method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(`${API}${path}`, opts);
  let data;
  try { data = await r.json(); } catch { data = {}; }
  if (!r.ok) throw Object.assign(new Error(data?.detail || `HTTP ${r.status}`), { status: r.status });
  return data;
};

/** Friendly relative timestamp ("Baru saja", "5 mnt lalu", short date). */
export const fmtTime = (iso) => {
  if (!iso) return '-';
  const d = new Date(iso);
  const diffMins = Math.floor((Date.now() - d) / 60000);
  if (diffMins < 1) return 'Baru saja';
  if (diffMins < 60) return `${diffMins} mnt lalu`;
  const diffH = Math.floor(diffMins / 60);
  if (diffH < 24) return `${diffH} jam lalu`;
  return d.toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: '2-digit' });
};

/** Full locale timestamp (used in version history). */
export const fmtIso = (iso) => {
  if (!iso) return '';
  return new Date(iso).toLocaleString('id-ID', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
};

export const ACCESS_CONFIG = {
  owner: { label: 'Milik Saya', icon: Crown,  cls: 'bg-violet-100 text-violet-700 border-violet-200' },
  admin: { label: 'Admin',      icon: Crown,  cls: 'bg-blue-100 text-blue-700 border-blue-200' },
  edit:  { label: 'Bisa Edit',  icon: Pencil, cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  view:  { label: 'Lihat Saja', icon: Eye,    cls: 'bg-amber-100 text-amber-700 border-amber-200' },
};

export const canEdit = (lv) => ['owner', 'admin', 'edit'].includes(lv);
export const canShare = (lv) => ['owner', 'admin'].includes(lv);

/** Cell text colors used by FormattingToolbar. */
export const COLORS = [
  { label: 'Merah',   val: '#ef4444' }, { label: 'Oranye',  val: '#f97316' },
  { label: 'Kuning',  val: '#eab308' }, { label: 'Hijau',   val: '#22c55e' },
  { label: 'Biru',    val: '#3b82f6' }, { label: 'Ungu',    val: '#a855f7' },
  { label: 'Default', val: '' },
];

/** Cell background colors used by FormattingToolbar. */
export const BG_COLORS = [
  { label: 'Merah Muda',  val: '#fecaca' }, { label: 'Oranye Muda', val: '#fed7aa' },
  { label: 'Kuning Muda', val: '#fef08a' }, { label: 'Hijau Muda',  val: '#bbf7d0' },
  { label: 'Biru Muda',   val: '#bfdbfe' }, { label: 'Ungu Muda',   val: '#e9d5ff' },
  { label: 'Default',     val: '' },
];

/**
 * Minimal spreadsheet-style formula evaluator.
 * Supports: =SUM(col), =AVG(col), =COUNT(col), =MIN(col), =MAX(col).
 * Returns the formula string verbatim if unrecognized.
 */
export const evaluateFormula = (formula, rows, colKey) => {
  if (!formula.startsWith('=')) return formula;
  const expr = formula.slice(1).trim().toUpperCase();
  const m = expr.match(/^(SUM|AVG|COUNT|MIN|MAX)\(([\w]+)\)$/);
  if (!m) return formula;
  const [, func, col] = m;
  const vals = rows.map((r) => parseFloat(r[col])).filter((v) => !isNaN(v));
  if (vals.length === 0) return func === 'COUNT' ? 0 : '';
  switch (func) {
    case 'SUM':   return vals.reduce((a, b) => a + b, 0);
    case 'AVG':   return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2);
    case 'COUNT': return vals.length;
    case 'MIN':   return Math.min(...vals);
    case 'MAX':   return Math.max(...vals);
    default:      return formula;
  }
};

/** Field schemas used by ImportFromModuleDialog. */
export const ASSET_FIELDS = [
  { key: 'asset_number', label: 'Nomor Aset' }, { key: 'name', label: 'Nama' },
  { key: 'category_name', label: 'Kategori' }, { key: 'department', label: 'Departemen' },
  { key: 'location', label: 'Lokasi' }, { key: 'brand', label: 'Merek' },
  { key: 'model', label: 'Model' }, { key: 'serial_number', label: 'Serial Number' },
  { key: 'purchase_date', label: 'Tgl Perolehan' }, { key: 'purchase_cost', label: 'Harga Beli' },
  { key: 'residual_value', label: 'Nilai Sisa' }, { key: 'status', label: 'Status' },
  { key: 'assigned_to_name', label: 'Ditugaskan Ke' },
];

export const PROCUREMENT_FIELDS = [
  { key: 'request_number', label: 'Nomor PR' }, { key: 'title', label: 'Judul' },
  { key: 'department', label: 'Departemen' }, { key: 'requested_by_name', label: 'Peminta' },
  { key: 'priority', label: 'Prioritas' }, { key: 'total_estimated', label: 'Total Estimasi' },
  { key: 'status', label: 'Status' },
];

export const DEF_ASSET_FIELDS = [
  'asset_number', 'name', 'category_name', 'department', 'location', 'purchase_cost', 'status',
];

export const DEF_PR_FIELDS = [
  'request_number', 'title', 'department', 'requested_by_name', 'total_estimated', 'status',
];
