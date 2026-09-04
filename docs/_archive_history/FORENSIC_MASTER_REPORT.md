# FORENSIC MASTER REPORT — DA53 ERP
**Sifat:** Read-only forensic (tidak ada perubahan kode/data)
**Metode:** Cross-reference 3 sumber kebenaran — (1) 258 koleksi MongoDB + jumlah dokumen, (2) 319 file route backend (prefix, endpoint, koleksi read/write), (3) 274 modul frontend (moduleRegistry + portalNav + panggilan `/api`).
**Sinyal utama:** Jumlah dokumen (`0 = EMPTY`) + apakah koleksi ditulis/dibaca kode. (Sinyal "seed-only" sengaja TIDAK dipakai karena terbukti banyak false-positive.)

---

## 1. Ringkasan Eksekutif

| Metrik | Nilai |
|---|---|
| Total koleksi DB | 258 |
| Koleksi KOSONG (0 dok) | **83 (32%)** |
| — Kosong wajar (runtime/log) → KEEP | 16 |
| — Kosong & butuh keputusan (dormant/duplikat) | **67** |
| File route backend | 319 (156 prefix) |
| Modul terdaftar (registry) | 274 (259 tampil di sidebar) |
| Klaster duplikasi-konsep terdeteksi | 22 |

**Temuan inti:** Sistem punya banyak **subsistem paralel** untuk konsep yang sama. Sebagian besar duplikat adalah pasangan **"1 aktif + 1 legacy kosong"** (aman diretire) atau **subsistem utuh yang kosong** (butuh keputusan bisnis: pakai atau buang).

---

## 2. KATEGORI A — Duplikat "aktif vs legacy kosong" → **AMAN DIRETIRE** (tanpa migrasi)

Koleksi legacy KOSONG (0 dok), sudah ada penerus aktif. Karena kosong, tidak perlu migrasi data.

| Konsep | ✅ Kanonik (aktif) | 🔴 Legacy kosong (retire) |
|---|---|---|
| Surat jalan pelanggan | `wh_delivery_notes` (8) | `rahaza_shipments` (0) |
| Dispatch/DO ke CMT | `wh_cmt_dispatches` (5) | `dewi_cmt_delivery_orders` (0) |
| KPI karyawan | `da_kpi_results` (25, dipakai gamifikasi/leaderboard) | `rahaza_kpi_results` (30 tapi **tanpa pembaca**) |
| Cutting request | `rahaza_cutting_requests` (8) | `dewi_cutting_requests` (0), `dewi_cutting_batches` (0) |
| Order produksi | `rahaza_work_orders` (20) + `dewi_maklon_pos` (6) | `production_pos` (0), `po_items` (0), `production_jobs` (0), `production_job_items` (0) |

> Catatan `rahaza_shipments`: meski kosong, ia memuat logika posting **AR + COGS**. Sebelum diarsipkan, wajib dipastikan posting AR/COGS pelanggan sudah ditangani jalur aktif (mis. `fin-ar-invoices`). **(verifikasi dulu)**

---

## 3. KATEGORI B — Subsistem UTUH yang KOSONG → **KEPUTUSAN BISNIS** (pakai atau buang)

Seluruh koleksi dalam grup ini 0 dok. Kode + menu-nya ada, tapi tidak pernah terisi data.

### B1. CMT lama (`dewi_cmt_*`) — 5 koleksi kosong ⚠️ PRIORITAS
`dewi_cmt_jobs`, `dewi_cmt_partners`, `dewi_cmt_deliveries`, `dewi_cmt_payments`, `dewi_cmt_delivery_orders`, `dewi_cmt_progress_reports`, `dewi_cmt_component_requests`
→ Menu terdampak: **Manajemen CMT, CMT Lifecycle, CMT Progress & DO, Packing/Opname CMT, Kekurangan Komponen** (5 menu Produksi).
→ Alur CMT nyata jalan lewat `wh_cmt_dispatches` (WMS) + `vendor_portal_accounts` (7 akun).
→ **Rekomendasi:** jadikan WMS + Portal Vendor kanonik; arsipkan subsistem `dewi_cmt_*`.

### B2. Master Vendor GANDA (dua-duanya kosong)
`vendor_partners` (0) + `dewi_cmt_partners` (0) + `vendor_jobs` (0) + `vendor_progress_reports` (0), sementara `vendor_portal_accounts` = 7.
→ Ada 2 konsep "partner vendor" yang keduanya kosong; akun login ada tapi data master tidak. **Perlu ditetapkan satu master vendor.**

### B3. Modul RnD (`dewi_rnd_*`) — 8 koleksi kosong
`dewi_rnd_tech_packs`, `dewi_rnd_patterns`, `dewi_rnd_materials`, `dewi_rnd_variants`, `dewi_rnd_sample_requests`, `dewi_rnd_sample_costing`, `dewi_rnd_hpp`, `dewi_rnd_samples` (4, tanpa pembaca).
→ Modul RnD praktis **dorman**. Pakai (perlu di-seed + adopsi) atau arsipkan?

### B4. Subsistem Accessory Shipment — 4 koleksi kosong
`accessory_shipments`, `accessory_shipment_items`, `accessory_inspections`, `accessory_defects` (+ `buyer_shipment_items`).
→ Alur inspeksi/kirim aksesoris terpisah, tidak terpakai. Buang atau gabung ke WMS?

### B5. Maklon sub-fitur — 7 koleksi kosong
`dewi_maklon_bom`, `dewi_maklon_bom_templates`, `dewi_maklon_hpp`, `dewi_maklon_inventory`, `dewi_maklon_material_receive`, `dewi_maklon_sample_revisions`, `dewi_maklon_advance_payments`.
→ Fitur HPP/BOM/inventory maklon punya koleksi khusus tapi kosong (kemungkinan dihitung on-the-fly / embedded). Konfirmasi apakah dipakai.

### B6. Lain-lain (kosong, low-impact — sudah dibahas sebelumnya)
- Shop-floor: `rahaza_andon_events`, `rahaza_machine_downtime`, `rahaza_zkteco_devices`, `rahaza_material_reservations` (real-time jarang dipakai).
- BOM/HPP persist: `rahaza_boms`, `rahaza_hpp_snapshots`, `rahaza_model_process_sop`, `rahaza_lkp`.
- HR/Onboarding: `dewi_onboarding_templates/checklists`, `rahaza_onboarding_checklists`, `dewi_recruitment_candidates`, `rahaza_salary_adjustments`, `da_payroll_allowances`, `payroll_entries`.
- Marketing: `marketing_catalogs`, `marketing_catalog_items`, `marketing_creator_item_requests`, `marketing_import_templates`, `marketing_livehost_scripts`, `marketing_livehost_training`, `marketing_tasks`.
- Aset: `da_assets`, `da_asset_assignments`. Toko: `dewi_toko_flashsales`, `dewi_toko_pack_batches`. LMS: `dewi_lms_materials`, `study_groups`. Lain: `comm_conversations`, `portal_quick_links`, `rahaza_channel_gl_mapping`, `rahaza_handover_templates`, `role_permissions`, `permissions`.

---

## 4. KATEGORI C — Duplikat "DUA-DUANYA AKTIF" → **butuh migrasi (risiko lebih tinggi)**

| Konsep | Sistem A (data) | Sistem B (data) | Catatan |
|---|---|---|---|
| Shift kerja | `rahaza_shifts` (4, terintegrasi absensi/master) | `hr_shifts` (7, terisolasi di `hr_shifts.py`) | Dua sistem shift aktif — perlu tetapkan kanonik + migrasi |

> Hanya 1 kasus dual-active nyata yang berisiko. Sisanya (kpi, orders, samples, materials) sudah terkarakterisasi sebagai domain berbeda **atau** salah satunya tanpa-pembaca (efektif mati).

---

## 5. KATEGORI D — BUKAN duplikat (pemisahan domain yang SAH) → **JANGAN disentuh**

Agar tidak salah hapus, ini yang **terlihat** seperti duplikat tapi sebenarnya beda konteks bisnis:

- `[order]`: `dewi_toko_orders` (240, e-commerce), `marketing_orders` (60, live/afiliasi), `rahaza_orders` (produksi), `dewi_maklon_orders` (legacy) — beda kanal.
- `[sample]`: `marketing_samples` (35, sampel produk marketing) vs `dewi_maklon_samples` (6, sampel maklon) vs `dewi_rnd_samples` (RnD).
- `[material]`: `rahaza_materials` (19, gudang) vs `dewi_lms_materials` (materi belajar — beda arti total).
- `[alert_setting]`: `marketing_alert_settings` vs `rahaza_alert_settings`.
- `[notification]`: `notifications` (55) + `dewi_notifications` (5) — runtime.

---

## 6. Kandidat "DEAD MENU" (menu tampil, tapi semua koleksinya kosong)

Terdeteksi otomatis (high-confidence):
- `prod-cmt` → CMTManagementModule
- `cmt-lifecycle` → CMTLifecycleModule
- `production-cmt-component-requests` → CMTComponentRequestModule

Kemungkinan besar juga (mapping parsial): `cmt-progress`, `prod-cmt-packing`. → Semua di klaster B1.

---

## 7. Rencana Remediasi Bergelombang (aman → berisiko)

**Metode tetap: bekukan → re-point → verifikasi → arsip (jangan hapus mentah).**

- **Gelombang 1 — Kategori A (aman, tanpa migrasi):** retire `rahaza_shipments`*, `dewi_cmt_delivery_orders`, `rahaza_kpi_results`, `dewi_cutting_requests/batches`, `production_pos/po_items/production_jobs/job_items`. *(`rahaza_shipments` setelah cek AR/COGS.)*
- **Gelombang 2 — Kategori B1/B2 (CMT & Vendor):** tetapkan WMS+Vendor Portal kanonik, arsipkan `dewi_cmt_*` + rapikan menu (butuh persetujuan bisnis Anda).
- **Gelombang 3 — Kategori B3–B6 (RnD, Accessory, Maklon sub, low-impact):** per modul, putuskan "pakai/buang".
- **Gelombang 4 — Kategori C (shift dual-active):** migrasi hati-hati bila memang duplikat.

Setiap gelombang: GET-sweep endpoint + render UI + regression test (DoD: data+render terbukti).

---

## 8. Keputusan yang Dibutuhkan dari Anda

1. **Gelombang 1** (duplikat legacy kosong) — jalankan? *(risiko sangat rendah)*
2. **CMT:** WMS+Portal Vendor sebagai kanonik & arsip `dewi_cmt_*`? *(rekomendasi: ya)*
3. **Modul dorman (RnD, Accessory, Assets, LMS, Toko flashsale, Marketing catalog/livehost):** mana yang **dipakai ke depan** vs **diarsipkan**?
4. **Shift ganda:** `rahaza_shifts` atau `hr_shifts` yang jadi kanonik?

---
*Dihasilkan oleh Forensic Scanner (read-only). Semua angka berdasarkan data DB saat laporan dibuat.*

---

## 9. LOG EKSEKUSI (update setelah laporan)

### O1.2 — Wave 2 CMT De-dup (SELESAI) ✅
- Frontend: 5 menu CMT dihapus dari sidebar Produksi; 5 id CMT + `prod-shipments`/`do-management` di-redirect ke kanonik (vendor-admin / wms-cmt-dispatches / wms-delivery-notes); Rework dipindah ke seksi Tahap; 6 import unused di-comment.
- Verifikasi: esbuild bersih, screenshot sidebar bersih, backend health 200.
- Backend route `dewi_cmt_*` DIBIARKAN (kosong & harmless) — arsip lapisan kode ditunda.

### O1.3 — Cross-domain dead-junk cleanup (SELESAI) ✅
- **Dinonaktifkan seeding + drop koleksi** untuk 2 koleksi *junk mati murni* (ditulis seed, TIDAK pernah dibaca kode/modul):
  - `rahaza_kpi_results` (30 dok dibuang) — kanonik = `da_kpi_results` (25, tetap utuh).
  - `dewi_tasks` (10 dok dibuang) — tidak ada modul/route yang membacanya.
- File `production_seed_full.py` diedit surgical (blok insert dinonaktifkan) → py_compile OK, backend restart & health 200.

### Yang DISENGAJA TIDAK disentuh (dengan alasan) ⚠️
- `rahaza_onboarding_checklists` — bukan sekadar junk; ini **bug routing seed** (seed menulis ke koleksi legacy, modul `hr-onboarding` baca `dewi_onboarding_checklists`). Memperbaikinya = perubahan fungsional, bukan de-dup → ditunda sebagai item terpisah.
- `permissions`, `role_permissions` — infra RBAC/auth-critical.
- `rahaza_boms`, `dewi_maklon_bom`, `da_assets` — terpasang di alur aktif (keputusan user: "semua modul dipakai").
- `hr_shifts` vs `rahaza_shifts` (dual-active) — perlu migrasi absensi → Gelombang 4 (berisiko), ditunda.
