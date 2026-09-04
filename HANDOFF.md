# HANDOFF — DA12345 (Dewi Aditya ERP)

> **BAHASA:** Selalu balas & berkomunikasi dengan user dalam **Bahasa Indonesia**.
> **Dokumen ini** = instruksi lengkap untuk agent sesi berikutnya agar bisa langsung melanjutkan.

---

## 1. RINGKASAN STATUS

Aplikasi ERP full-stack (FastAPI + React + MongoDB) yang matang. Fitur besar terakhir yang
dikerjakan: **Panduan Produksi (SOP + foto + video)** yang diinput di Master Produk Internal
(`rahaza_models`) dan ditampilkan **read-only** ke Portal Vendor CMT, di-scope hanya untuk model
yang ditugaskan ke vendor tsb.

### Sudah SELESAI & TERUJI
- ✅ Phase 7A — BOM schema unification (`yarn_materials`/`accessory_materials` → `materials[]`).
- ✅ Maklon Buyer Catalog Variant UI (color chips, size chips, live SKU preview).
- ✅ Backend SOP endpoints (`rahaza_production.py`): field schema, limit gambar, `PUT /models/{mid}/sop`.
- ✅ Backend vendor scoping (`vendor_portal.py`): `model_id` di `vendor_jobs` + `GET /my-jobs/{id}/production-guide`.
- ✅ Legacy cleanup: drop koleksi kosong `products`, `product_variants`, `rahaza_styles` saat startup (`server.py`).
- ✅ Admin SOP UI (`RahazaModelsModule.jsx`) — tab "Panduan Produksi" (foto/video/langkah bernomor).
- ✅ Admin Vendor Jobs UI (`VendorAccountsAdminModule.jsx`) — form "Buat Job" + pilih `model_id`.
- ✅ Komponen `VendorProductionGuide.jsx` (engine) — **sudah dibuat & lengkap** (list job + detail SOP read-only).

---

## 2. ✅ TUGAS UTAMA P0 — SELESAI & TERUJI (Session lanjutan)

**STATUS: DONE.** `VendorProductionGuide.jsx` sudah di-*wire* ke shell navigasi
`VendorPortalApp.jsx` (3 titik: import komponen + ikon `BookOpen`, entri menu
`production-guide`, dan case render `<VendorProductionGuide user={user} />`).

Sudah di-rebuild (`bash /app/scripts/rebuild_frontend.sh`), diverifikasi via screenshot,
dan lolos E2E `testing_agent_v3` **100% (18/18 test)** — lihat
`/app/test_reports/iteration_124.json`. Scoping vendor & mode read-only terbukti benar.

> Catatan bring-up fresh clone (session ini): `backend/.env` ditambahi `JWT_SECRET`
> (wajib) + `EMERGENT_LLM_KEY=""`; `frontend/.env` ditambahi `GENERATE_SOURCEMAP=false`
> & `DISABLE_ESLINT_PLUGIN=true`. `MONGO_URL` & `REACT_APP_BACKEND_URL` TIDAK diubah.
> POC backend end-to-end: `/app/tests/poc_vendor_production_guide.py` (14/14 PASS).
> Data demo di-seed via `POST /api/seed/maklon-full` + POC script (vendor A/B + SOP + jobs).

### (Instruksi lama — tetap disimpan sebagai referensi wiring)
Komponen `VendorProductionGuide.jsx` di-*wire* ke `VendorPortalApp.jsx`:

**File yang perlu diedit (HANYA SATU FILE):**
`/app/frontend/src/components/erp/engine/VendorPortalApp.jsx`

### Perubahan persis yang diperlukan (3 titik):

**a) Tambah import** (di grup import komponen, setelah baris `import VendorReminderInbox ...`):
```jsx
import VendorProductionGuide   from './VendorProductionGuide';
```
Dan tambahkan ikon `BookOpen` ke import `lucide-react` di atas.

**b) Tambah entri menu** di array `modules` (posisi disarankan: setelah `production-jobs`):
```jsx
{ id: 'production-guide',   label: 'Panduan Produksi',      icon: BookOpen },
```

**c) Tambah case render** di `renderModule()`:
```jsx
case 'production-guide':    return <VendorProductionGuide user={user} />;
```

> Catatan: `VendorProductionGuide` hanya butuh prop `user` (dia ambil token sendiri dari
> `localStorage` via `apiGet`). Tidak perlu pass `token`.

### Setelah edit — WAJIB:
```bash
bash /app/scripts/rebuild_frontend.sh
```
> **JANGAN** jalankan `craco start` / `yarn start:dev`. Frontend disajikan sebagai
> **PREBUILT STATIC BUNDLE** via `node static_server.js` di port 3000. Setiap perubahan di
> `frontend/src` HARUS di-rebuild dengan script di atas sebelum screenshot/test.

---

## 3. VERIFIKASI YANG HARUS DILAKUKAN

1. **Screenshot** Portal Vendor CMT → login sebagai vendor, cek menu "Panduan Produksi" muncul,
   klik → daftar job tampil → klik job (yang punya model) → SOP steps + foto + video tampil.
2. **`testing_agent_v3`** — E2E full flow (frontend + backend):
   - Admin buat job vendor + tautkan `model_id` yang punya SOP.
   - Vendor login → buka Panduan Produksi → verifikasi hanya melihat job miliknya (scoping benar).
   - Verifikasi read-only (tidak ada tombol edit).
3. Wajib **fix semua bug** dari test report (`/app/test_reports/iteration_*.json`) sebelum selesai.

---

## 4. REFERENSI TEKNIS

### Endpoint backend yang dipakai komponen (SUDAH ADA & BENAR):
- `GET /api/vendor-portal/my-jobs` — daftar job milik vendor (field: `id`, `job_number`, `title`,
  `process`, `model_id`, `model_code`, `model_name`).
- `GET /api/vendor-portal/my-jobs/{job_id}/production-guide` — response:
  ```json
  { "has_model": true|false, "model": { "code","name","description","image_paths",
    "sop_steps","reference_videos","reference_images" }, "message": "..." }
  ```
  (Scoped: hanya job dengan `partner_id` == vendor yang login. Jika model tidak tertaut →
  `has_model: false` + pesan.)

### Endpoint SOP admin (SUDAH ADA):
- `PUT /api/production/models/{mid}/sop`
- `POST /api/production/models/{mid}/images`

### Skema DB kunci:
- `rahaza_models`: `{ sop_steps[], reference_videos[], reference_images[], image_paths[], sop_updated_at, sop_updated_by }`
- `vendor_jobs`: `{ id, job_number, title, partner_id, wo_id, model_id, model_code, model_name, process, status, ... }`
- `dewi_maklon_buyer_catalog`: `{ color_options, size_options, variants }`

### File referensi:
- `/app/backend/routes/vendor_portal.py` — endpoint vendor + production-guide (lengkap).
- `/app/backend/routes/rahaza_production.py` — endpoint SOP master produk (lengkap).
- `/app/backend/server.py` — legacy cleanup startup.
- `/app/frontend/src/components/erp/engine/VendorProductionGuide.jsx` — komponen guide vendor (lengkap).
- `/app/frontend/src/components/erp/engine/VendorPortalApp.jsx` — **PERLU DIEDIT** (wiring nav).
- `/app/frontend/src/components/erp/RahazaModelsModule.jsx` — admin SOP UI.
- `/app/frontend/src/components/erp/MaklonBuyerCatalogModule.jsx` — Maklon variant/SKU UI.
- `/app/frontend/src/components/erp/VendorAccountsAdminModule.jsx` — form buat job vendor.

---

## 5. TUGAS BERIKUTNYA (setelah P0 selesai & lolos test)

- **P0 — Phase 3 Marketing/Toko:** Tautkan `variant_id` ke mapping stok Toko / Finished Goods.
- **P1 — Phase 4 Migrations:** Jalankan skrip migrasi pada data lama & bersihkan sisa referensi
  legacy `products`/`product_variants` di codebase bila masih ada.

> Sesuai kesepakatan user sebelumnya:
> - Master Produk Internal wajib punya SOP juga (bukan hanya Maklon). ✅ sudah.
> - Legacy kosong (`products`, `product_variants`, `rahaza_styles`) dihapus/arsip. ✅ sudah.
> - Create manual di Master Produk diberi tanda **"disarankan lewat R&D"**. (verifikasi label ini ada di `RahazaModelsModule.jsx`.)

---

## 6. ATURAN KRITIS (JANGAN DILANGGAR)

- 🗣️ **Balas user dalam Bahasa Indonesia.**
- 🏗️ Frontend = **prebuilt static bundle**. Selalu `bash /app/scripts/rebuild_frontend.sh` setelah
  ubah `frontend/src`. JANGAN `craco start`.
- 🔒 JANGAN ubah `REACT_APP_BACKEND_URL` (frontend/.env) & `MONGO_URL` (backend/.env).
- 🧩 Semua route backend prefix `/api`. Gunakan UUID (bukan ObjectId). Datetime pakai `timezone.utc`.
- 🧭 Vendor CMT memakai arsitektur **engine** (`VendorPortalApp.jsx` + `VendorCMTEnginePortal.jsx`),
  BUKAN `VendorPortalModule.jsx`. Semua perubahan vendor lewat engine apps.

---

## 7. KREDENSIAL TEST

- Admin: `admin@garment.com` / `Admin@123`
- Role lain (HR, Finance, SPV, Gudang, Maklon): `{role}@dewiaditya.id` / `Dewi@123`
- Vendor: gunakan akun vendor yang dibuat via Admin → Vendor Accounts (lihat `VendorAccountsAdminModule.jsx`).

---

## 8. TEST REPORTS & POC SEBELUMNYA
- `/app/test_reports/iteration_122.json`, `/app/test_reports/iteration_123.json`
- `/app/tests/poc_phase7a_bom_materials.py`
- `/app/tests/poc_master_product_sop.py`

**Health check:** Sehat. Tidak ada data yang di-mock. Tidak ada integrasi pihak ketiga berbayar
(upload gambar pakai local file storage `/api/files/`).
