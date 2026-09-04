/**
 * format.js — Utilitas format ANGKA / RUPIAH / TANGGAL kanonik (locale id-ID).
 * =============================================================================
 * SATU SUMBER KEBENARAN untuk format Rupiah & angka di seluruh aplikasi.
 * Sebelumnya formatter Rupiah tersebar (fmtRp/fmtIDR/formatCurrency lokal) di
 * ~100+ file. Gunakan util ini untuk file baru & migrasi bertahap.
 *
 * Standar Rupiah: "Rp 1.500.000"  (spasi setelah "Rp", tanpa desimal,
 * pemisah ribuan titik ala Indonesia).
 *
 * Contoh:
 *   formatRupiah(1500000)                 -> "Rp 1.500.000"
 *   formatRupiah(null)                    -> "Rp 0"
 *   formatRupiah(null, { dash: true })    -> "—"
 *   formatRupiah(1500.5, { decimals: 2 }) -> "Rp 1.500,50"
 *   formatNumber(1234567)                 -> "1.234.567"
 *   formatNumber(1.2345, { maximumFractionDigits: 2 }) -> "1,23"
 *   formatRupiahShort(1500000)            -> "Rp 1,5 jt"
 *   formatDateID('2026-07-19')            -> "19 Jul 2026"
 *   formatDateTimeID('2026-07-19T08:30')  -> "19 Jul 2026, 08.30"
 */

export const LOCALE = 'id-ID';

/** Konversi nilai apa pun ke number berhingga, atau null bila tak valid. */
function toFiniteNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * Format angka murni (tanpa "Rp"). Default tanpa desimal, pemisah ribuan id-ID.
 * @param {number|string} value
 * @param {{ minimumFractionDigits?: number, maximumFractionDigits?: number, fallback?: string }} [opts]
 */
export function formatNumber(value, opts = {}) {
  const n = toFiniteNumber(value);
  if (n === null) return opts.fallback ?? '0';
  const {
    minimumFractionDigits = 0,
    maximumFractionDigits = Math.max(minimumFractionDigits, 0),
  } = opts;
  return n.toLocaleString(LOCALE, { minimumFractionDigits, maximumFractionDigits });
}

/**
 * Format Rupiah kanonik: "Rp 1.500.000".
 * @param {number|string} value
 * @param {{ decimals?: number, dash?: boolean, withSpace?: boolean }} [opts]
 *   - decimals: jumlah desimal (default 0)
 *   - dash: bila true, nilai kosong/tidak valid -> "—" (bukan "Rp 0")
 *   - withSpace: spasi setelah "Rp" (default true)
 */
export function formatRupiah(value, opts = {}) {
  const n = toFiniteNumber(value);
  const sep = opts.withSpace === false ? '' : ' ';
  if (n === null) return opts.dash ? '—' : `Rp${sep}0`;
  const decimals = opts.decimals ?? 0;
  const digits = formatNumber(n, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return `Rp${sep}${digits}`;
}

/** Alias eksplisit — sebagian modul lama memakai nama ini. */
export const formatCurrency = formatRupiah;
export const formatIDR = formatRupiah;

/**
 * Format Rupiah ringkas untuk kartu/dashboard: "Rp 1,5 jt", "Rp 2,3 rb", "Rp 4 M".
 * @param {number|string} value
 */
export function formatRupiahShort(value) {
  const n = toFiniteNumber(value);
  if (n === null) return 'Rp 0';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  const fmt = (x) => x.toLocaleString(LOCALE, { maximumFractionDigits: 1 });
  if (abs >= 1e12) return `${sign}Rp ${fmt(abs / 1e12)} T`;
  if (abs >= 1e9)  return `${sign}Rp ${fmt(abs / 1e9)} M`;
  if (abs >= 1e6)  return `${sign}Rp ${fmt(abs / 1e6)} jt`;
  if (abs >= 1e3)  return `${sign}Rp ${fmt(abs / 1e3)} rb`;
  return `${sign}Rp ${fmt(abs)}`;
}

/**
 * Format tanggal id-ID. Default: "19 Jul 2026".
 * @param {string|number|Date} value
 * @param {Intl.DateTimeFormatOptions & { fallback?: string }} [opts]
 */
export function formatDateID(value, opts = {}) {
  if (!value) return opts.fallback ?? '—';
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return opts.fallback ?? '—';
  const { fallback, ...rest } = opts;
  const options = Object.keys(rest).length ? rest : { day: '2-digit', month: 'short', year: 'numeric' };
  return d.toLocaleDateString(LOCALE, options);
}

/**
 * Format tanggal + jam id-ID. Default: "19 Jul 2026, 08.30".
 * @param {string|number|Date} value
 * @param {{ fallback?: string }} [opts]
 */
export function formatDateTimeID(value, opts = {}) {
  if (!value) return opts.fallback ?? '—';
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return opts.fallback ?? '—';
  return d.toLocaleString(LOCALE, {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

/**
 * Parse string angka locale-ID -> number (atau null bila tak valid).
 * Kebalikan dari formatRupiah/formatNumber; dipakai untuk membaca input user
 * atau data impor. Locale ID: '.' = ribuan, ',' = desimal. Toleran currency,
 * gaya US, dan negatif via kurung "(1.000)".
 *   parseIDNumber("Rp 1.500.000") -> 1500000
 *   parseIDNumber("1.234.567,89") -> 1234567.89
 *   parseIDNumber("150,5")        -> 150.5
 *   parseIDNumber("(1.000)")      -> -1000
 * @param {string|number} value
 * @param {{ fallback?: number|null }} [opts]
 * @returns {number|null}
 */
export function parseIDNumber(value, opts = {}) {
  const fallback = opts.fallback ?? null;
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'number') return Number.isFinite(value) ? value : fallback;
  let s = String(value).trim();
  if (s === '' || s.toLowerCase() === 'nan' || s.toLowerCase() === 'none') return fallback;

  let neg = false;
  if (s.startsWith('(') && s.endsWith(')')) { neg = true; s = s.slice(1, -1).trim(); }
  s = s.replace(/rp|idr/gi, '').replace(/\u00a0/g, ' ').trim();
  if (s.startsWith('-')) { neg = true; s = s.slice(1).trim(); }
  else if (s.startsWith('+')) { s = s.slice(1).trim(); }

  s = s.replace(/[^0-9.,]/g, '');
  if (s === '') return fallback;

  const hasDot = s.includes('.');
  const hasCom = s.includes(',');
  if (hasDot && hasCom) {
    if (s.lastIndexOf(',') > s.lastIndexOf('.')) s = s.replace(/\./g, '').replace(',', '.');
    else s = s.replace(/,/g, '');
  } else if (hasCom) {
    s = (s.split(',').length - 1) > 1 ? s.replace(/,/g, '') : s.replace(',', '.');
  } else if (hasDot) {
    if ((s.split('.').length - 1) > 1) s = s.replace(/\./g, '');
    else if (s.split('.')[1].length === 3) s = s.replace('.', '');
    // else: single dot with !=3 digits => decimal, keep
  }
  const n = Number(s);
  if (!Number.isFinite(n)) return fallback;
  return neg ? -n : n;
}

/** Alias — parse string Rupiah ke number. */
export const parseRupiah = parseIDNumber;

const formatUtils = {
  LOCALE,
  formatNumber,
  formatRupiah,
  formatCurrency,
  formatIDR,
  formatRupiahShort,
  formatDateID,
  formatDateTimeID,
  parseIDNumber,
  parseRupiah,
};

export default formatUtils;
