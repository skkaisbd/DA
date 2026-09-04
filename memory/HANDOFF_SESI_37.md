# HANDOFF — SESI #37 (eksekusi berikutnya)

Ditulis 2026-08-24 setelah audit menyeluruh sesi #35–#36. **Baca ini dulu, jangan mulai dari nol.**

---

## Keputusan pemilik (final, jangan ditawar ulang)

| # | Keputusan | Konsekuensi teknis |
|---|---|---|
| 1 | **Form pencairan ada di Portal FINANCE.** Marketing hanya MELIHAT nominalnya | layar baru di Finance; layar Marketing tetap baca-saja |
| 2 | Pencairan **dicocokkan ke omzet periode + tampilkan selisih**, DAN **membuat jurnal** kas masuk + potongan platform | endpoint reconcile + journal |
| 2b | ⚠️ **OMZET TIDAK MASUK FINANCE — HANYA PENCAIRAN.** | jurnal HANYA saat pencairan; jangan pernah memposting penjualan/omzet marketing ke GL |
| 2c | ⚠️ **Akun toko SUDAH punya COA otomatis per akun** (di Portal Marketing). Jangan bikin peta COA kedua | lihat "Jebakan COA" di bawah |
| 3 | Sinkron RnD → katalog marketing **tetap manual** (biarkan apa adanya) | tidak ada pekerjaan |
| 4 | **Margin dihitung otomatis**; kalau HPP 0 tampilkan "belum bisa diukur", BUKAN 0% | perubahan di katalog marketing |
| 5 | **22 jenis impor digabung jadi ±6 kelompok** | perubahan di data-import |
| — | 6 kolom harga katalog **by design** (pencatatan RnD) — JANGAN disatukan | temuan audit dicabut |
| — | Data demo/seed memang usang — **yang dinilai fungsi, bukan isi data** | jangan habiskan waktu memperbaiki data demo |

---

## Hasil audit yang sudah PASTI (jangan diaudit ulang)

* **RnD: logikanya BENAR, hanya datanya kosong.** Diuji e2e pada API nyata lalu dibersihkan:
  style → varian → review → approve → **promote menghasilkan 2 SKU kanonik** (`MODEL-WARNA-UKURAN`),
  FG `type=fg` tertaut `model_id`+`size_id`+`color_id`, `rahaza_model_variants` terbentuk,
  model membawa `rnd_style_id`, viewer RnD langsung menemukannya. Idempoten; kode model kembar ditolak 409.
* Viewer RnD mengembalikan kunci **`data`**, bukan `rows` (audit sebelumnya salah baca → laporan "0 baris" itu keliru).
* Sudah benar & terbukti: biaya jahit SPK · periode anggaran 7 hari · portal KOL (login, katalog hanya yang di-assign, **tanpa kebocoran HPP**) · livehost gaji bulanan (per-sesi = 0) · KPI konten per konten/jenis/toko/KOL.
* Belum tuntas: **pencairan (tidak ada form di mana pun)** dan **margin katalog (0 dari 78 item punya `margin_pct`)**.
* 64 gate hijau; 2.415 rute, **0 rute ganda**; katalog 78 item, **0 duplikat (akun, SKU)**.

---

## PEKERJAAN 1 — Pencairan marketplace di Portal Finance (P0)

### Yang SUDAH ada (jangan dibuat ulang)
`backend/routes/marketing_settlements.py` — prefix **`/api/marketing/settlements`**
* `GET ""` (daftar + ringkasan) · `POST ""` (buat, model `SettlementIn`) · `POST /{sid}/journal` (jurnal draf) ·
  `GET /reconcile` · `GET /coa-map`
* `SettlementIn`: `account_id, platform, settlement_id, settlement_date, period_from, period_to,
  gross_sales, refunds, seller_discount, shipping_subsidy, platform_commission, platform_service_fee,
  affiliate_commission, ads_deduction, other_deductions, adjustments, net_payout`
  (`net_payout` **diisi staf dari mutasi bank**, sengaja tidak dihitung server)
* Frontend baca-saja: `frontend/src/components/erp/marketing/MarketingSettlementsView.jsx`

### Yang HARUS ditambah / diedit

**Backend**
1. `POST /api/marketing/settlements` — **tambah pagar peran Finance** (saat ini `require_auth` + scope toko saja).
   Marketing boleh GET, hanya Finance yang boleh POST/journal.
2. `GET /api/marketing/settlements/{sid}` — **BELUM ADA**, dibutuhkan layar detail Finance.
3. `PUT /api/marketing/settlements/{sid}` — **BELUM ADA** (koreksi sebelum jurnal diposting; tolak bila sudah ada jurnal).
4. `GET /api/marketing/settlements/reconcile` — **sudah ada, perlu diperluas**: kembalikan omzet
   pesanan periode (`marketing_orders`, `order_date` dalam `period_from..period_to`, status ≠ cancelled)
   vs `gross_sales` pencairan, plus **selisihnya dengan nama** (mis. "pesanan belum cair", "cair tanpa pesanan").
   Jangan sembunyikan selisih 0-kan.
5. `POST /api/marketing/settlements/{sid}/journal` — **sudah ada, WAJIB diperbaiki** (lihat jebakan COA).
6. Opsional: `POST /api/marketing/settlements/{sid}/post` (finalisasi jurnal draf → posted).

**Frontend (baru)**
* `frontend/src/components/erp/finance/FinanceSettlementModule.jsx` — form input + daftar + tombol
  "Cocokkan" dan "Buat jurnal". Daftarkan di `moduleRegistry.js` + `portalNav.js` **di Portal Finance**.
* `MarketingSettlementsView.jsx` tetap baca-saja; tambahkan kalimat "input dilakukan di Portal Finance".

### ⚠️ JEBAKAN COA (ini yang pemilik peringatkan)
Ada **DUA** sumber akun sekarang:
* Global di `routes/marketing_settlements.py` → `COA = {cash:'1-1201', revenue:'4-1100', returns:'4-1200',
  discount:'4-1300', platform_fee:'4-141', ads:'6-1100', other:'7-4000'}`
* **Per akun toko** di `routes/marketing_accounts.py` → field `coa_revenue_code`, `coa_cash_code`,
  `coa_receivable_code` (sudah ada validator `_validate_coa_role`, dan akun toko men-generate COA-nya sendiri).

**Aturan yang harus ditegakkan:** jurnal pencairan WAJIB memakai **COA milik akun toko** bila ada,
global hanya cadangan; bila akun toko belum punya COA → **tolak dengan pesan jelas**, jangan diam-diam
memakai `1-1201`. Dan sekali lagi: **jurnal hanya untuk PENCAIRAN** (kas masuk + potongan platform).
`revenue`/omzet **tidak boleh** diposting ke GL dari jalur marketing mana pun.

---

## PEKERJAAN 2 — Margin di katalog marketing (P0, kecil)

Fakta: `marketing_catalog_items` 78 item → **`margin_pct` tidak ada di satu pun**, `hpp` terisi 10 item.

* Edit endpoint daftar/detail katalog di `routes/marketing_catalog_items.py`
  (prefix `/api/marketing/catalogs`): hitung saat baca (jangan simpan ganda)
  `margin_rp = harga_jual − hpp_efektif`, `margin_pct = margin_rp / harga_jual × 100`.
* **HPP efektif** = urutan: `hpp_fifo_avg` FG → `hpp` FG → `hpp` katalog. Sertakan `hpp_source`.
* Bila HPP 0 / tidak diketahui → kirim `margin_status: "belum_bisa_diukur"` + alasannya
  (mis. "SPK belum tertaut master", "BOM belum ada"). **Jangan kirim 0%.**
* Frontend katalog & `RnDProductViewer.jsx` menampilkan lencana "belum bisa diukur", bukan 0%.

---

## PEKERJAAN 3 — Konsolidasi 22 jenis impor → ±6 kelompok (P1)

Sekarang `GET /api/marketing/data-import/source-types` mengembalikan **22** jenis, banyak yang tumpang tindih:
`orders · marketplace_orders · sales_daily` | `ads · shopee_ads_cpc` |
`live_sessions · livehost_shifts · live_session_products` | `content_performance · shopee_content_kpi · content_calendar` |
`returns · complaints · reviews` | `catalog_items · discounts · product_launches · samples · kol_creators ·
account_health · marketplace_fulfillment · shopee_shop_kpi`

Usulan kelompok: **Pesanan & Penjualan · Iklan · Retur/Komplain/Ulasan · Konten · Live · Katalog & Lainnya**.

* Tambah `GET /api/marketing/data-import/source-groups` (kelompok → daftar jenis di dalamnya).
* Wizard memilih **kelompok** dulu; jenis persisnya ditentukan **deteksi otomatis** (`POST /detect` sudah ada).
* Jenis lama **tetap diterima** oleh `POST /upload` (jangan putus impor yang sudah jalan); cukup
  disembunyikan dari pilihan dan ditandai `deprecated: true` bila tumpang tindih.
* File: `backend/core/marketing_import_schema.py`, `backend/routes/marketing_data_import.py`,
  `frontend/src/components/erp/marketing/DataImportWizard.jsx`.

---

## Aturan kerja di repo ini

* **Ukur dulu, baru klaim.** Setiap pernyataan di laporan harus punya angka dari API/DB.
* Setelah perubahan logika: `bash scripts/gate.sh --full` harus **0 FAIL** (sekarang 64 gate hijau).
* Tambah gate baru untuk pekerjaan di atas — usul: **INV-F42** (pencairan: jurnal pakai COA akun toko,
  omzet tidak pernah masuk GL, selisih rekonsiliasi disebut, dobel-jurnal ditolak) dan
  **INV-F43** (margin: 0% tidak pernah ditampilkan saat HPP tidak diketahui).
* Frontend memakai **PREVIEW_STABLE_MODE**: setelah edit FE jalankan `bash scripts/rebuild_frontend.sh`
  (±2 menit, jalankan di latar belakang). Jangan `craco start`.
* Kredensial uji: `memory/test_credentials.md`. Panduan impor master: `memory/PANDUAN_IMPOR_MASTER.md`.
* Bahasa jawaban ke pemilik: **Indonesia**.

---

## Urutan eksekusi yang disarankan
1. Pencairan (backend endpoint + pagar COA) → gate INV-F42 → layar Finance → rebuild FE
2. Margin katalog (backend hitung + lencana FE) → gate INV-F43
3. Konsolidasi impor → uji ulang wizard (testing agent, frontend saja)
