/**
 * rollLines.js — aturan bersama untuk RINCIAN GULUNGAN KAIN (FASE H-5).
 *
 * Kenapa ada berkas sendiri: rincian roll diisi di TIGA layar (Penerimaan Barang saat
 * membuat GR, Penerimaan Barang saat mengonfirmasi, dan Roll Kain untuk penerimaan
 * yang sudah lewat). Kalau aturan "total gulungan harus sama dengan qty diterima"
 * ditulis ulang di tiap layar, satu layar pasti tertinggal saat aturannya berubah —
 * dan gudang akan punya dua angka untuk satu penerimaan.
 *
 * Satuan yang dilacak per gulungan MENGIKUTI backend (`core/fabric_roll_engine.ROLL_UOM`).
 * Satuan kecil (gram/cm/inch) sengaja TIDAK ada: kain tidak diterima per gram.
 */

// satuan master material → satuan gulungan (kg | meter | yard)
export const ROLL_UOM = {
  kg: 'kg', bal: 'kg', ball: 'kg',
  meter: 'meter', m: 'meter', mtr: 'meter', rol: 'meter', gulung: 'meter',
  yard: 'yard', yd: 'yard',
};

export const rollUomOf = (unit) => ROLL_UOM[String(unit || '').trim().toLowerCase()] || null;

/** Satuan ini dilacak per gulungan? (kain / benang — bukan pcs, bukan barang jadi) */
export const isRollUnit = (unit) => !!rollUomOf(unit);

/** Material ini wajar dilacak per gulungan? (mengikuti `is_roll_material` di backend) */
export function isRollMaterial(mat) {
  if (!mat) return false;
  if (mat.type === 'fg' || mat.is_cut_panel) return false;
  return isRollUnit(mat.unit);
}

export const rollLine = (qty = '') => ({ qty, color_lot: '', notes: '' });

export const num = (v) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
};

export const totalOf = (lines) => (lines || []).reduce((s, l) => s + num(l.qty), 0);

/** Qty yang harus dijelaskan gulungan = diterima − ditolak (yang benar-benar masuk stok). */
export const acceptedOf = (item) => {
  if (!item) return 0;
  if (item.accepted_qty !== undefined && item.accepted_qty !== null && item.accepted_qty !== '') {
    return num(item.accepted_qty);
  }
  return Math.max(0, num(item.received_qty) - num(item.rejected_qty));
};

/** Toleransi SAMA dengan backend: max(0,01 ; 0,5% dari qty diterima). */
export const toleranceOf = (accepted) => Math.max(0.01, Math.abs(num(accepted)) * 0.005);

/**
 * Status rincian gulungan terhadap qty diterima.
 * `state`: 'empty' | 'match' | 'over' | 'under'
 */
export function rollLinesState(lines, accepted) {
  const list = lines || [];
  const total = totalOf(list);
  const acc = num(accepted);
  const diff = +(total - acc).toFixed(3);
  const bad = list.some((l) => num(l.qty) <= 0);
  if (!list.length) return { state: 'empty', total, diff, count: 0, hasZero: false };
  if (Math.abs(diff) <= toleranceOf(acc)) {
    return { state: bad ? 'under' : 'match', total, diff: 0, count: list.length, hasZero: bad };
  }
  return { state: diff > 0 ? 'over' : 'under', total, diff, count: list.length, hasZero: bad };
}

/** Bagi qty ke n gulungan sama rata; pembulatan sisa ditaruh di gulungan terakhir. */
export function splitEvenly(accepted, n) {
  const count = Math.max(1, Math.min(200, Math.floor(num(n) || 1)));
  const acc = num(accepted);
  if (acc <= 0) return Array.from({ length: count }, () => rollLine(''));
  const each = Math.floor((acc / count) * 1000) / 1000;
  const lines = Array.from({ length: count }, () => rollLine(each));
  const rest = +(acc - each * count).toFixed(3);
  if (rest !== 0) lines[count - 1].qty = +(each + rest).toFixed(3);
  return lines;
}

/** Bagi pemakaian ke gulungan terpilih, FIFO nomor roll — CERMIN `allocate()` backend. */
export function previewAllocation(rolls, qty) {
  const need = num(qty);
  const plan = [];
  let left = need;
  const sorted = [...(rolls || [])].sort((a, b) => String(a.roll_no || '').localeCompare(String(b.roll_no || '')));
  for (const r of sorted) {
    if (left <= 0.0001) break;
    const remaining = num(r.uom === 'kg' ? r.remaining_kg : r.remaining_m);
    const take = Math.min(remaining, left);
    if (take <= 0) continue;
    plan.push({ roll_id: r.id, roll_no: r.roll_no, qty: +take.toFixed(3), uom: r.uom, remaining_after: +(remaining - take).toFixed(3) });
    left = +(left - take).toFixed(4);
  }
  const available = sorted.reduce((s, r) => s + num(r.uom === 'kg' ? r.remaining_kg : r.remaining_m), 0);
  return { plan, shortage: +Math.max(0, need - available).toFixed(3), available: +available.toFixed(3) };
}

export const fmtQty = (n, d = 2) =>
  Number(num(n)).toLocaleString('id-ID', { minimumFractionDigits: d, maximumFractionDigits: d });
