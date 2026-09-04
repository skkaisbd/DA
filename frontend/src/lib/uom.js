/**
 * lib/uom.js — SSOT konversi satuan di sisi frontend.
 *
 * Kembaran persis `backend/core/uom.py`. Setiap perubahan aturan WAJIB
 * dilakukan di kedua file supaya tampilan dan perhitungan server tidak
 * berbeda hasilnya.
 *
 * Invarian yang dijaga (lihat memory/INVARIANTS.md §U):
 *  - INV-UOM-1  `unit_cost` SELALU harga per satuan dasar
 *  - INV-UOM-2  semua qty stok SELALU dalam satuan dasar
 *  - INV-UOM-3  uoms[0] = satuan dasar, faktor 1, kode unik
 *  - INV-UOM-6  `factor` relatif ke satuan dasar, bukan ke induknya
 *
 * Fallback berlapis pada resolveUoms() membuat material lama (yang hanya
 * punya `unit` + `pack_unit`/`pack_size`) tetap bekerja tanpa migrasi.
 */

export const MAX_LEVEL = 2;          // 0 = satuan dasar, 1 = bungkus, 2 = karton
export const MAX_UOMS = MAX_LEVEL + 1;
export const DEFAULT_BASE = 'pcs';

const ROUND = 6;

/**
 * Daftar satuan dasar yang boleh dipakai — HARUS sama persis dengan
 * `MATERIAL_UNITS` di `backend/routes/rahaza_inventory_shared.py`.
 * Sebelumnya form hanya menawarkan 6 satuan padahal backend menerima 22 dan
 * data nyata memakai `rol`/`pak`/`lusin`/`yard` (136 material) — akibatnya
 * satuan bisa tertukar diam-diam saat material lama diedit.
 */
export const MATERIAL_UNITS = [
  'm', 'cm', 'yard', 'inch',
  'kg', 'gram', 'ton',
  'pcs', 'lusin', 'kodi', 'gross', 'helai', 'set', 'pair',
  'rol', 'gulung', 'bal', 'karton', 'pak', 'sak',
  'liter', 'ml',
];

export const normalizeCode = (c) => String(c ?? '').trim().toLowerCase();

const num = (v, d = 0) => {
  const f = Number(v);
  return Number.isFinite(f) ? f : d;
};

const r = (v) => Number(num(v).toFixed(ROUND));

export function baseUomOf(material) {
  const m = material || {};
  return normalizeCode(m.base_uom || m.unit || DEFAULT_BASE) || DEFAULT_BASE;
}

function mkRow(code, factor, opts = {}) {
  const c = normalizeCode(code);
  const row = {
    code: c,
    name: (opts.name || '').trim() || c.toUpperCase(),
    factor: r(factor),
    is_base: !!opts.is_base,
    level: Number.isFinite(opts.level) ? opts.level : 0,
  };
  if (opts.parent) row.parent = normalizeCode(opts.parent);
  ['is_purchase_default', 'is_issue_default', 'is_display_default'].forEach((k) => {
    if (opts[k]) row[k] = true;
  });
  ['barcode', 'notes'].forEach((k) => {
    if (opts[k]) row[k] = String(opts[k]);
  });
  return row;
}

/** Bangun daftar UOM dari field lama (`unit` + `pack_unit`/`pack_size`). */
export function buildFromLegacy(material) {
  const m = material || {};
  const base = baseUomOf(m);
  const rows = [mkRow(base, 1, { is_base: true, level: 0 })];
  const packUnit = normalizeCode(m.pack_unit);
  const packSize = num(m.pack_size, 1);
  if (packUnit && packUnit !== base && packSize > 1) {
    rows.push(mkRow(packUnit, packSize, {
      parent: base,
      level: 1,
      is_purchase_default: true,
      is_display_default: !!m.display_in_packs,
      notes: `1 ${packUnit} = ${r(packSize)} ${base}`,
    }));
  }
  return rows;
}

/** Daftar UOM efektif — selalu mengembalikan minimal 1 baris (satuan dasar). */
export function resolveUoms(material) {
  const m = material || {};
  if (Array.isArray(m.uoms) && m.uoms.length) {
    const base = baseUomOf(m);
    const seen = new Set();
    const out = [];
    m.uoms.forEach((row) => {
      if (!row || typeof row !== 'object') return;
      const code = normalizeCode(row.code);
      if (!code || seen.has(code)) return;
      const factor = code === base ? 1 : num(row.factor, 0);
      if (factor <= 0) return;
      seen.add(code);
      out.push(mkRow(code, factor, {
        name: row.name,
        is_base: code === base,
        parent: row.parent,
        level: num(row.level, 0),
        is_purchase_default: row.is_purchase_default,
        is_issue_default: row.is_issue_default,
        is_display_default: row.is_display_default,
        barcode: row.barcode,
        notes: row.notes,
      }));
    });
    if (!seen.has(base)) out.unshift(mkRow(base, 1, { is_base: true, level: 0 }));
    out.sort((a, b) => a.factor - b.factor || a.code.localeCompare(b.code));
    return out;
  }
  return buildFromLegacy(m);
}

export function findUom(material, code) {
  const c = normalizeCode(code);
  if (!c) return null;
  return resolveUoms(material).find((x) => x.code === c) || null;
}

export const uomCodes = (material) => resolveUoms(material).map((x) => x.code);

/** Faktor satuan terhadap satuan dasar. Satuan tak dikenal → 1 (mode toleran). */
export function factorOf(material, code) {
  const c = normalizeCode(code);
  if (!c || c === baseUomOf(material)) return 1;
  const row = findUom(material, c);
  return row ? row.factor : 1;
}

/** qty (satuan `uom`) → satuan dasar. */
export const toBase = (material, qty, uom) => r(num(qty) * factorOf(material, uom));

/** qty (satuan dasar) → satuan `uom`. Untuk TAMPILAN saja. */
export function fromBase(material, qtyBase, uom) {
  const f = factorOf(material, uom);
  return f ? r(num(qtyBase) / f) : r(qtyBase);
}

/** Harga per satuan `uom` → harga per satuan dasar (INV-UOM-1). */
export function costToBase(material, cost, uom) {
  const f = factorOf(material, uom);
  return f ? r(num(cost) / f) : r(cost);
}

/** Harga per satuan dasar → harga per satuan `uom`. Untuk TAMPILAN saja. */
export const costFromBase = (material, costBase, uom) => r(num(costBase) * factorOf(material, uom));

export const convert = (material, qty, fromUom, toUom) =>
  fromBase(material, toBase(material, qty, fromUom), toUom);

function defaultUom(material, key, flag) {
  const m = material || {};
  const explicit = normalizeCode(m[key]);
  if (explicit && findUom(m, explicit)) return explicit;
  const flagged = resolveUoms(m).find((x) => x[flag]);
  return flagged ? flagged.code : baseUomOf(m);
}

export const purchaseUomOf = (material) => defaultUom(material, 'purchase_uom', 'is_purchase_default');
export const issueUomOf = (material) => defaultUom(material, 'issue_uom', 'is_issue_default');

export function displayUomOf(material) {
  const code = defaultUom(material, 'display_uom', 'is_display_default');
  const m = material || {};
  if (code === baseUomOf(m) && m.display_in_packs) {
    const pack = normalizeCode(m.pack_unit);
    if (pack && pack !== code && findUom(m, pack)) return pack;
  }
  return code;
}

const fmt = (n) => {
  const v = r(n);
  return Number.isInteger(v)
    ? v.toLocaleString('id-ID')
    : v.toLocaleString('id-ID', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

/** `"450 m"` */
export function formatQty(material, qtyBase, uom) {
  const code = normalizeCode(uom) || baseUomOf(material);
  return `${fmt(fromBase(material, qtyBase, code))} ${code}`;
}

/**
 * `"450 m (9 rol)"` — menjawab kebutuhan "double satuan": satu angka stok
 * terbaca dalam dua satuan sekaligus tanpa harus memilih salah satu.
 */
export function formatDual(material, qtyBase, secondary) {
  const base = baseUomOf(material);
  const primary = `${fmt(num(qtyBase))} ${base}`;
  const sec = normalizeCode(secondary) || displayUomOf(material);
  if (!sec || sec === base) return primary;
  if (!findUom(material, sec)) return primary;
  return `${primary} (${fmt(fromBase(material, qtyBase, sec))} ${sec})`;
}

/** Periksa INV-UOM-3 & INV-UOM-6. → { ok, errors[] } */
export function validateUoms(uoms, baseUom) {
  const errors = [];
  const rows = Array.isArray(uoms) ? uoms : [];
  if (!rows.length) return { ok: true, errors };
  const base = normalizeCode(baseUom);
  const seen = new Set();
  const allCodes = new Set(rows.map((x) => normalizeCode(x?.code)));
  let nBase = 0;

  rows.forEach((row, i) => {
    if (!row || typeof row !== 'object') {
      errors.push(`Baris ${i + 1}: format tidak valid`);
      return;
    }
    const code = normalizeCode(row.code);
    if (!code) { errors.push(`Baris ${i + 1}: kode satuan wajib diisi`); return; }
    if (seen.has(code)) errors.push(`Baris ${i + 1}: kode satuan "${code}" terduplikasi`);
    seen.add(code);

    const factor = num(row.factor, 0);
    if (factor <= 0) errors.push(`Satuan "${code}": faktor harus lebih besar dari 0`);

    const lvl = num(row.level, 0);
    if (lvl < 0 || lvl > MAX_LEVEL) errors.push(`Satuan "${code}": tingkat ${lvl} di luar batas (0–${MAX_LEVEL})`);

    if (row.is_base || (base && code === base)) {
      nBase += 1;
      if (factor !== 1) errors.push(`Satuan dasar "${code}" wajib berfaktor 1 (sekarang ${factor})`);
    }

    const parent = normalizeCode(row.parent);
    if (parent && !allCodes.has(parent)) errors.push(`Satuan "${code}": induk "${parent}" tidak ada dalam daftar`);
    if (parent && parent === code) errors.push(`Satuan "${code}": induk tidak boleh dirinya sendiri`);
  });

  if (rows.length > MAX_UOMS) errors.push(`Maksimal ${MAX_UOMS} satuan per item (dasar + ${MAX_LEVEL} tingkat kemasan)`);
  if (nBase === 0) errors.push('Harus ada tepat satu satuan dasar (faktor 1)');
  else if (nBase > 1) errors.push('Hanya boleh ada satu satuan dasar');

  return { ok: errors.length === 0, errors };
}

/** Bersihkan & urutkan daftar UOM sebelum dikirim ke backend. */
export function sanitizeUoms(uoms, baseUom) {
  const base = normalizeCode(baseUom) || DEFAULT_BASE;
  const seen = new Set();
  const cleaned = [];
  (uoms || []).forEach((row) => {
    if (!row || typeof row !== 'object') return;
    const code = normalizeCode(row.code);
    if (!code || seen.has(code)) return;
    const factor = code === base ? 1 : num(row.factor, 0);
    if (factor <= 0) return;
    seen.add(code);
    cleaned.push(mkRow(code, factor, {
      name: row.name,
      is_base: code === base,
      parent: row.parent,
      level: 0,
      is_purchase_default: row.is_purchase_default,
      is_issue_default: row.is_issue_default,
      is_display_default: row.is_display_default,
      barcode: row.barcode,
      notes: row.notes,
    }));
  });
  if (!seen.has(base)) cleaned.push(mkRow(base, 1, { is_base: true, level: 0 }));
  cleaned.sort((a, b) => a.factor - b.factor || a.code.localeCompare(b.code));
  let prev = null;
  cleaned.forEach((row, i) => {
    row.level = Math.min(i, MAX_LEVEL);
    if (i > 0 && !row.parent) row.parent = prev;
    prev = row.code;
  });
  return cleaned.slice(0, MAX_UOMS);
}

/**
 * Hitung faktor terhadap satuan dasar dari input user yang berbentuk
 * "1 <satuan ini> = N <satuan induk>".
 * Pemakai form hanya mengetik N relatif ke induk; fungsi ini yang mengalikannya
 * sampai ke satuan dasar (INV-UOM-6).
 */
export function factorFromParent(rows, parentCode, perParent) {
  const parent = (rows || []).find((x) => normalizeCode(x.code) === normalizeCode(parentCode));
  const parentFactor = parent ? num(parent.factor, 1) : 1;
  return r(num(perParent, 1) * parentFactor);
}

/** Ringkasan hierarki untuk ditampilkan: "1 ktn = 12 bks = 1.728 pcs". */
export function describeHierarchy(rows, baseUom) {
  const base = normalizeCode(baseUom) || DEFAULT_BASE;
  const sorted = [...(rows || [])].sort((a, b) => num(a.factor) - num(b.factor));
  if (sorted.length < 2) return '';
  const top = sorted[sorted.length - 1];
  const parts = [`1 ${top.code}`];
  for (let i = sorted.length - 2; i >= 0; i -= 1) {
    parts.push(`${fmt(num(top.factor) / num(sorted[i].factor, 1))} ${sorted[i].code}`);
  }
  void base;
  return parts.join(' = ');
}

export default {
  MAX_LEVEL, MAX_UOMS, DEFAULT_BASE, MATERIAL_UNITS,
  normalizeCode, baseUomOf, resolveUoms, buildFromLegacy, findUom, uomCodes,
  factorOf, toBase, fromBase, costToBase, costFromBase, convert,
  purchaseUomOf, issueUomOf, displayUomOf,
  formatQty, formatDual, validateUoms, sanitizeUoms,
  factorFromParent, describeHierarchy,
};
