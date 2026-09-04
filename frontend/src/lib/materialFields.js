/**
 * lib/materialFields — SSOT nama field material di sisi frontend.
 *
 * Pasangan dari `backend/core/material_fields.py`. Kode lama proyek ini memakai nama
 * field `yarn_*` (warisan pabrik benang) padahal taksonomi resmi sudah netral
 * (Bahan · Aksesoris · Produk Jadi).
 *
 * RIWAYAT
 *  - FASE 6.6-B — pola "canonical + alias": backend menulis KEDUA nama, frontend baca
 *    kanonik dulu lalu fallback ke legacy, dan mengirim kedua nama.
 *  - FASE 11    — alias legacy BERHENTI DITULIS. `mirrorField()` kini hanya
 *    menghasilkan nama kanonik, dan response API tidak lagi membawa `yarn_*`.
 *    `readField()` SENGAJA tetap punya fallback baca supaya data lama (mis. state
 *    yang di-cache atau dokumen yang belum dimigrasi) tidak tampil kosong.
 *
 * Pakai:
 *   import { readField, FIELD } from '@/lib/materialFields';
 *   const komposisi = readField(material, FIELD.composition);
 */

export const FIELD = {
  composition: 'composition',
  materialKgPerPcs: 'material_kg_per_pcs',
  defaultMaterialCostPerKg: 'default_material_cost_per_kg',
  totalMaterialKgPerPcs: 'total_material_kg_per_pcs',
  totalMaterialKg: 'total_material_kg',
  bulkLineCount: 'bulk_line_count',
};

/**
 * kanonik → daftar alias legacy (urutan = prioritas fallback).
 * FASE 11: dipakai HANYA untuk MEMBACA data lama. Jangan dipakai untuk menulis.
 */
export const LEGACY_READ_ALIASES = {
  composition: ['yarn_type'],
  material_kg_per_pcs: ['yarn_kg_per_pcs'],
  default_material_cost_per_kg: ['default_yarn_cost_per_kg'],
  total_material_kg_per_pcs: ['total_yarn_kg_per_pcs'],
  total_material_kg: ['total_yarn_kg'],
  bulk_line_count: ['yarn_count'],
};

/**
 * FASE 11 — alias yang ikut DITULIS. Sengaja kosong (pasangan `WRITE_ALIASES`
 * di backend). Isi ulang map ini bila perlu memulihkan perilaku lama.
 */
export const WRITE_ALIASES = {};

/** Label Indonesia untuk UI — dipakai agar terminologi seragam di semua modul. */
export const FIELD_LABELS = {
  composition: 'Jenis / Komposisi',
  material_kg_per_pcs: 'Bahan utama/pcs (kg)',
  default_material_cost_per_kg: 'Default Bahan/kg',
  total_material_kg_per_pcs: 'Total bahan/pcs (kg)',
  total_material_kg: 'Total bahan (kg)',
  bulk_line_count: 'Baris bahan (kg)',
};

/**
 * Baca nilai field dengan rantai fallback kanonik → legacy.
 * @param {object} doc dokumen (material / bom / settings)
 * @param {string} canonical nama kanonik (pakai konstanta FIELD)
 * @param {*} fallback nilai bila tidak ada sama sekali
 */
export function readField(doc, canonical, fallback = '') {
  if (!doc || typeof doc !== 'object') return fallback;
  const keys = [canonical, ...(LEGACY_READ_ALIASES[canonical] || [])];
  for (const k of keys) {
    const v = doc[k];
    if (v !== undefined && v !== null && v !== '') return v;
  }
  for (const k of keys) {
    if (k in doc) return doc[k];
  }
  return fallback;
}

/** Baca sebagai angka (0 bila kosong / bukan angka). */
export function readNumber(doc, canonical, fallback = 0) {
  const v = Number(readField(doc, canonical, fallback));
  return Number.isFinite(v) ? v : fallback;
}

/**
 * Buat patch untuk optimistic-update state lokal.
 * FASE 11: hanya nama kanonik (backend juga hanya menulis kanonik).
 */
export function mirrorField(canonical, value) {
  const out = { [canonical]: value };
  (WRITE_ALIASES[canonical] || []).forEach((legacy) => { out[legacy] = value; });
  return out;
}
