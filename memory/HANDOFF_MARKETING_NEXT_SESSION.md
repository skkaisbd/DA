# HANDOFF — Sesi Berikutnya (Marketing: AR-off, Katalog Pricing/HPP, Budget Marketing)

> **Untuk siapa:** agent sesi berikutnya yang akan **membuat plan** (belum implementasi).
> **Sifat:** hasil analisis read-only sesi ini + **keputusan user** + **info yang HARUS digali** sebelum plan final.
> **Aturan tetap:** JANGAN rebuild UI (pakai static view yg ada). Frontend = prebuilt bundle
> (`bash /app/scripts/rebuild_frontend.sh` sesudah ubah `frontend/src`). Backend hot-reload.
> `backend/.env` wajib ada `JWT_SECRET`. Preview: lihat `memory/PREVIEW_STABLE_MODE.md`.
> **Baca juga:** `memory/ANALYSIS_MARKETING_FLOW.md` (flow AS-IS + Adendum 2) &
> `memory/ANALYSIS_PDF_SJ_ABSEN_OVERLAP.md` (analisis area lain).


---
## ✅ UPDATE 2026-07-14 — SUDAH DIIMPLEMENTASIKAN (bukan lagi "belum implementasi")
Ketiga keputusan + quick-win **sudah selesai & teruji** oleh sesi implementasi. Lihat `plan.md`
bagian "STATUS — SELESAI" untuk ringkas. Keputusan final user yang dipakai:
- **#1 = 1.a** (hanya matikan bridge Sales→AR + sembunyikan menu "Buat Invoice"; Finance AR & Jurnal Manual tetap).
- **#2**: harga `harga_jual`(final) / `harga_coret`(promo ≥jual) / `harga_original`(list) / `hpp`(internal).
  CMT = **input manual** per model di RnD (keputusan 3.a, "biarkan dulu"). Material HPP = **auto dari BOM × unit_cost**,
  katalog **auto-refresh** (keputusan 4.a).
- **#5**: KOL = **kombinasi configurable** (fee fixed rate &/atau komisi % sales), Ads = **input manual**,
  granularitas budget = **per akun/kategori/bulan** (ads/kol/livehost/sample/diskon).
File kunci implementasi: `backend/routes/marketing_sales.py` (410), `backend/routes/marketing_catalog_items.py`
(+ `_normalize_pricing_read`/`_pricing_write_fields`), `backend/routes/dewi_rnd_hpp.py` (BOM + `_propagate_hpp`),
`backend/routes/marketing_budget.py` (baru), FE: `CatalogManagementModule.jsx`, `marketing/BudgetAllocationTab.jsx`,
`marketing/AccountTargetsModule.jsx`, `marketing/ContentCalendarModule.jsx`, `portal-shell/portalNav.js`.
> Catatan: seed_role_accounts + seed_marketing_demo perlu dijalankan pada DB baru (lihat PREVIEW_STABLE_MODE.md).
---

---

## 0. STATUS ENV (sudah dinaikkan sesi ini)
- Repo `da1307` sudah di `/app`. Backend healthy. Frontend static bundle ter-build & serving.
- Login OK (6 akun): `admin@garment.com/Admin@123` + `{hr,finance,spv,gudang,maklon}@dewiaditya.id/Dewi@123`
  (5 akun role dibuat via `backend/scripts/seed_role_accounts.py`).
- Seed marketing sekarang **timpang**: transaksi ada (orders 60, live 18, konten 30, ulasan 40, retur 30,
  komplain 40) tapi **master KOSONG** (accounts/catalogs/kol_creators/targets/sales_data = 0).
- **Bug kecil diketahui (belum diperbaiki):** `POST /api/rahaza/hr-seed/seed-kpi` → 500 (import modul terhapus
  `routes.dewi_kpi`; sudah pindah ke `dewi_kpi_questions.py`). Non-blok untuk marketing.

---

## 1. RANGKUMAN ANALISIS SESI INI (grounded, file:line)

### 1.1 Flow ke Finance (dikoreksi user)
- Marketing→AR **satu-satunya** jalur: `marketing_sales.py:171` `POST /api/marketing/sales-data/generate-ar-batch`
  → buat `rahaza_ar_invoices` (`:325`) → `post_ar_invoice` (`:333-335`). FE: `MarketingARBridgeModule.jsx`
  (menu `marketing-ar-bridge` "Buat Invoice", registry `moduleRegistry.js:790`).
- `post_ar_invoice` didefinisikan di `rahaza_posting.py:231`; **juga dipakai Finance** `rahaza_finance.py`
  (AR module resmi: `:187-486` ar-invoices/aging/payment/write-off). ⇒ **AR sub-ledger milik Finance itu SAH**;
  yang dikoreksi user hanya **auto-generate AR dari sales marketing**.
- **Manual Journal Entry Finance SUDAH ADA:** `rahaza_journals.py` (`/api/rahaza/journals`) + FE
  `RahazaJournalEntryModule.jsx`. Jadi finance bisa input jurnal manual.
- Fulfillment dispatch tetap posting **COGS** (`fulfillment.py` → `post_cogs_shipment`).

### 1.2 Katalog (pricing & HPP)
- Katalog per-toko + `from-fg` (dari master FG `rahaza_materials`) + filter per akun: **sudah benar**
  (`marketing_catalog_items.py:327`, FE `CatalogManagementModule.jsx:347,914`).
- Field harga sekarang: `price` (jual), `original_price` (**overloaded**: dilabel "HPP/base" di `:99`
  DAN "HPP/coret" di `:145`), `platform_price`. FE render coret bila `original_price>0`
  (`CatalogManagementModule.jsx:470-472`). ⇒ **satu field dipakai 2 makna** (masalah yg diakui user).
- Sumber HPP: **`dewi_rnd_hpp.py`** (HPP Calculator) SUDAH ada, komponen:
  `fabric_usage×fabric_price + Σ(acc.unit_cost×qty) + cmt_cost_per_pcs + cutting + packaging`,
  `+overhead% → hpp_total`, `selling_price = hpp/(1-margin%)` (`dewi_rnd_hpp.py:21-54`).
  **TAPI 100% INPUT MANUAL** (tidak tarik BOM×harga material), **standalone** (`dewi_rnd_hpp` collection),
  **tidak auto-link** ke `rahaza_models` maupun ke katalog. Ada Tech Pack dgn `bom_items` (`:166`).

### 1.3 Portal eksternal & lainnya (temuan, BELUM diputuskan user)
- LiveHost & Kreator: assign multi-toko **BENAR** (`assigned_account_ids` array). Akses kreator ketat (403).
- ⚠️ LiveHost `/portal/clock` baca `shift['shift_start_time']` langsung (`marketing_livehost_portal.py:306`)
  → risiko KeyError bila shift disimpan `scheduled_start`. **Perlu diverifikasi model ShiftCreate.**
- ⚠️ Kreator pakai katalog TERPISAH `marketing_creator_catalog` (`marketing_kol_ops.py:203`), bukan katalog
  utama → admin isi 2×. Kandidat konsolidasi.
- Content calendar: field `reference_link` ADA di backend (`marketing_content_calendar_routes.py:299`) tapi
  **phantom di FE** (tak ada input & tak dirender link). GAP kecil (untuk link Google Drive).
- LiveHost payment REAL (`marketing_livehost_analytics.py:202` `/payment/calculate` hourly_rate×jam →
  `/payment/sync-to-finance`). Ads spend **MOCK/random** (`marketing_ads_routes.py:50,73`).
- Kreator/KOL: **tidak ada** field komisi/biaya (hanya `kpi_targets` + sessions.revenue).

### 1.4 Akses (matriks)
- Portal `toko` (internal): `pic_toko, pic_marketing, staff_marketing, marketing_kol, cs_staff,
  manager_marketing` (+`buyer` di backend) + super (admin/owner). Sumber: `portalAccess.js` &
  `routes/shared.py:115-137`.
- Akun demo saat ini **tak punya role marketing** → hanya `admin` yg bisa buka Portal Marketing.
- Portal LiveHost & Kreator = auth terpisah (koleksi `marketing_livehosts` / `marketing_kol_creators`).

---

## 2. KEPUTUSAN USER (WAJIB dieksekusi di plan berikutnya)

### KEPUTUSAN #1 — Matikan AR otomatis dari marketing; finance pakai jurnal manual
**Scope pasti:**
- Nonaktifkan jalur **`marketing_sales.py generate-ar-batch`** dan **sembunyikan/arsipkan menu
  `marketing-ar-bridge`** ("Buat Invoice") dari Portal Marketing (`portalNav.js` seksi 1).
- **Input sales harian tetap jalan** → hanya untuk **dashboard marketing** (analitik), TIDAK memicu AR/GL.
- **JANGAN hapus** AR module Finance (`rahaza_finance.py`) & `post_ar_invoice` — itu milik Finance dan
  dipakai flow lain. Yang dimatikan HANYA auto-generate AR dari sales marketing.
- Revenue marketplace masuk finance lewat **Manual Journal Entry** (`rahaza_journals.py`) oleh finance.

**Info yg HARUS digali sebelum plan:**
1. Konfirmasi arti "matikan AR": (a) hanya matikan **bridge sales→AR** [interpretasi kami], atau
   (b) juga sembunyikan menu AR Invoice di Finance? → default (a).
2. Apakah `marketing-ar-bridge` dipakai/di-link modul lain? (cek `moduleRegistry.js`, redirect, dokumen).
3. Data `rahaza_ar_invoices` eksisting dari marketing (jika ada) — perlu dibersihkan/di-void atau dibiarkan?
4. Apakah perlu tinggalkan "jejak" (mis. tombol "Export rekap sales → template jurnal") untuk bantu finance
   input manual? (opsional, tanya user).

### KEPUTUSAN #2 — Pisah field harga di katalog + HPP dari RnD (BOM + biaya CMT)
**Scope pasti:**
- Katalog item WAJIB punya field **terpisah**: **`harga_jual`** (selling), **`harga_coret`** (strikethrough
  promo), **`harga_original`**, dan **`hpp`** (cost). Hentikan pemakaian ganda `original_price`.
- **HPP berangkat dari RnD** (`dewi_rnd_hpp.py`) — HPP model/style RnD dipropagasi ke FG → ke katalog item
  (jadi `hpp` katalog = HPP RnD, bukan input marketing).
- HPP RnD terdiri dari: material (BOM) + **biaya CMT** + cutting + packaging + overhead. Untuk **produksi
  internal**, "biaya CMT" = biaya konversi internal.

**Info yg HARUS digali sebelum plan (KRITIS — sumber biaya):**
1. **Semantik 3 harga (konfirmasi user):** beda pasti **`harga_original`** vs **`harga_coret`**?
   Hipotesis: `harga_jual` = harga transaksi final; `harga_coret` = harga dicoret utk efek promo (≥ jual);
   `harga_original` = harga normal/list resmi. → minta user definisikan + mana yg tampil ke customer.
2. **Biaya CMT produksi INTERNAL — sumbernya dari mana?** (pertanyaan eksplisit user). Opsi yg perlu
   diklarifikasi: (a) input manual per model di `dewi_rnd_hpp` (`cmt_cost_per_pcs`, kondisi sekarang);
   (b) tarif standar konversi internal (rate/pcs atau rate/menit × SAM) yg disimpan di master;
   (c) dari biaya produksi aktual (labor/attendance produksi) → butuh mapping. **Tanyakan preferensi user.**
3. **BOM → biaya material otomatis?** Sekarang fabric/acc HPP = manual. Apakah user mau HPP auto-hitung dari
   **BOM (tech_pack.bom_items) × harga material master** (`rahaza_materials.price`/moving avg)? Cek apakah
   material master menyimpan harga beli/HPP (verifikasi field harga di `rahaza_materials`).
4. **Jalur propagasi HPP RnD → FG → katalog:** verifikasi keterkaitan `dewi_rnd_hpp` ↔ `rahaza_models`
   (ada `style_id`/`model_id`?), dan `rahaza_models` ↔ FG `rahaza_materials` (`model_id`/`fg_code`), dan
   katalog `from-fg` (`fg_material_id`/`model_id`). Tentukan titik simpan HPP kanonik.
5. **Update HPP:** bila BOM/biaya berubah, HPP katalog auto-refresh atau snapshot? (kebijakan re-costing).

### KEPUTUSAN #5 — Budget Marketing per toko + monitoring alokasi (ads/KOL/kreator)
**Scope pasti:**
- Tiap **akun toko** punya **budget marketing** (rencana, per bulan) selain target sales (yg sudah ada di
  `marketing_account_targets`). Tambah **realisasi/spend** + **compare** (sisa, %, over/under).
- **Monitoring ALOKASI**: budget "dilarikan ke mana" — kategori minimal: **Ads**, **KOL/Kreator**,
  **LiveHost**, (opsional: **Sample**, **Diskon/Promo**). Simpan nominal per kategori per akun per periode.

**Penempatan (rekomendasi):** perluas menu **`marketing-targets` → "Target & Budget Bulanan"** (paling natural,
sudah per-akun/bulan). Alternatif: submenu baru **"Budget Marketing"** di Seksi 3 (Analitik).

**Info yg HARUS digali sebelum plan:**
1. **Sumber spend per kategori:**
   - LiveHost: **sudah real** (`/payment/calculate` hourly_rate×jam). Pakai ini sbg spend LiveHost. ✅
   - Ads: sekarang **MOCK**. → butuh **input spend iklan nyata** (manual entry per campaign/akun) —
     konfirmasi apakah user mau input manual atau integrasi API marketplace ads.
   - **KOL/Kreator: belum ada field biaya/komisi.** → butuh model baru (komisi per sesi / per penjualan /
     fee flat). **Tanyakan skema pembayaran kreator ke user.**
2. **Granularitas budget:** per akun per bulan saja, atau per akun per kategori per bulan?
3. **Relasi ke Finance:** apakah spend budget marketing harus tercermin di GL (biaya) atau cukup monitoring
   internal marketing? (Catatan: LiveHost payment sudah `sync-to-finance`; ads/KOL belum.)
4. **Sumber angka "hasil":** realisasi sales utk ROI budget diambil dari `marketing_sales_data` (dashboard)
   atau `marketing_orders`? (konsisten dgn keputusan #1 yg AR-nya dimatikan).

---

## 3. TEMUAN LAIN (belum diputuskan — untuk diprioritaskan user saat planning)
| # | Temuan | Ref | Saran |
|---|---|---|---|
| A | Content calendar link Google Drive = phantom | `ContentCalendarModule.jsx:64,179` | quick-win: tambah input + link |
| B | Bug `shift_start_time` di LiveHost `/portal/clock` | `marketing_livehost_portal.py:306` | verifikasi + guard |
| C | Overlap katalog kreator vs katalog utama | `marketing_kol_ops.py:203` vs `marketing_catalog_items` | konsolidasi |
| D | Ads spend MOCK | `marketing_ads_routes.py:50,73` | ganti input nyata (nyambung #5) |
| E | (Analisis lain) Payslip PDF & Surat Jalan SSOT hardcode; `company_settings` drift `type:'general'` | `ANALYSIS_PDF_SJ_ABSEN_OVERLAP.md` | keputusan terpisah |
| F | Seed master marketing kosong; role marketing & akun demo LiveHost/Kreator belum ada | §0 | seed utk uji RBAC & flow |
| G | seed-kpi 500 (import `routes.dewi_kpi`) | `rahaza_hr_seed.py` | fix import → `dewi_kpi_questions` |

---

## 4. LANGKAH YG DISARANKAN UNTUK SESI PLAN
1. Ajukan **pertanyaan klarifikasi** di §2 (terutama: definisi 3 harga, sumber biaya CMT internal, skema
   pembayaran KOL, sumber spend ads) — **jangan** mulai coding sebelum ini terjawab.
2. Verifikasi teknis cepat yg belum sempat: field harga di `rahaza_materials`, relasi `dewi_rnd_hpp`↔model,
   dan model `ShiftCreate` (bug B).
3. Susun `plan.md` fase-based mengikuti DoD repo (POC/endpoint → testid → E2E → doc). Urutan usulan:
   **Fase 1** matikan AR (#1, paling kecil & jelas) → **Fase 2** pricing+HPP katalog (#2) →
   **Fase 3** Budget Marketing (#5). Quick-wins (A) bisa disisipkan.
4. Semua tanpa rebuild UI; ubah minimal pada modul FE yg sudah ada + backend.

---

## 5. PERINTAH BRING-UP CEPAT (untuk sesi baru)
```bash
# backend
cd /app/backend && set -a && source .env && set +a
sudo supervisorctl status                 # pastikan backend+frontend RUNNING
curl -s localhost:8001/api/health
# login test
curl -s -X POST localhost:8001/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@garment.com","password":"Admin@123"}'
# sesudah ubah frontend/src:
bash /app/scripts/rebuild_frontend.sh
```
