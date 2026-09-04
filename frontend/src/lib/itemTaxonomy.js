/**
 * itemTaxonomy — SATU SUMBER kebenaran taksonomi item DA37 ERP.
 * ───────────────────────────────────────────────────────────────
 * Bisnis CV. Dewi Aditya hanya punya 3 JENIS item:
 *   1. Bahan        (kain/material kg-like)
 *   2. Aksesoris    (kancing, resleting, label, packaging — per pcs)
 *   3. Produk Jadi  (FG / barang jadi)
 *
 * Field data lama `type` (yarn/fabric/kain/benang/interlining/accessory/
 * packaging/fg/other) dipetakan ke 3 kategori ini HANYA untuk TAMPILAN.
 * Nilai yang DISIMPAN tetap kompatibel backend (fabric/accessory/fg) supaya
 * logika kg-like & costing lama tidak berubah. Rename field ditunda ke Fase 5.
 */

// Metadata kategori (label + satuan default + apakah kg-like).
export const ITEM_CATEGORIES = {
  bahan:     { key: 'bahan',     label: 'Bahan',       unit: 'kg',  kgLike: true },
  aksesoris: { key: 'aksesoris', label: 'Aksesoris',   unit: 'pcs', kgLike: false },
  fg:        { key: 'fg',        label: 'Produk Jadi', unit: 'pcs', kgLike: false },
};

// Opsi dropdown standar (urutan tampil).
export const CATEGORY_OPTIONS = [
  { value: 'bahan',     label: 'Bahan' },
  { value: 'aksesoris', label: 'Aksesoris' },
  { value: 'fg',        label: 'Produk Jadi' },
];

// tipe legacy → kategori (untuk display item lama).
const TYPE_TO_CATEGORY = {
  yarn: 'bahan', fabric: 'bahan', kain: 'bahan', benang: 'bahan', interlining: 'bahan',
  accessory: 'aksesoris', packaging: 'aksesoris',
  fg: 'fg',
};

// kategori (pilihan user) → nilai `type` yang disimpan (kompatibel backend).
const CATEGORY_TO_STORED_TYPE = {
  bahan: 'fabric',       // 'fabric' sudah termasuk kg-like di seluruh sistem
  aksesoris: 'accessory',
  fg: 'fg',
};

/** Kategori bisnis (bahan|aksesoris|fg) dari nilai type apa pun. Default: bahan. */
export function typeToCategory(type) {
  const t = String(type || '').toLowerCase();
  return TYPE_TO_CATEGORY[t] || 'bahan';
}

/** Nilai `type` untuk disimpan ketika user memilih sebuah kategori. */
export function categoryToStoredType(category) {
  return CATEGORY_TO_STORED_TYPE[category] || 'fabric';
}

/** Label tampilan (Bahan/Aksesoris/Produk Jadi) dari nilai type apa pun. */
export function categoryLabel(type) {
  return ITEM_CATEGORIES[typeToCategory(type)].label;
}

/** Satuan default untuk sebuah kategori. */
export function categoryUnit(category) {
  return (ITEM_CATEGORIES[category] || ITEM_CATEGORIES.bahan).unit;
}

/** Apakah item kg-like (Bahan) — dipakai untuk auto-set satuan kg. */
export function isKgLike(type) {
  return ITEM_CATEGORIES[typeToCategory(type)].kgLike;
}
