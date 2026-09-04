# RENCANA EKSEKUSI — Marketing: Impor Seller Center, Katalog, Target/Anggaran, UI

**Tanggal:** 2026-08-11 · **Status:** MENUNGGU PERSETUJUAN — belum ada kode fitur yang ditulis.
**Sumber:** sintesis dari 2 dokumen analisis read-only + 1 audit UI read-only:
- `/app/memory/ANALISIS_IMPOR_SELLER_CENTER_KEPUTUSAN_2026-08-11.md`
- `/app/memory/ANALISIS_SIKLUS_TARGET_OMZET_ANGGARAN_2026-08-11.md`
- `scripts/_audit_marketing_ui_views.py` (dijalankan ulang hari ini, hasil di §5)

Dokumen ini **tidak mengulang** semua bukti — hanya menyatukan temuan jadi satu urutan
kerja yang bisa langsung dieksekusi, fase demi fase, dengan bukti-selesai yang terukur
di setiap fase.

---

## 0. PRINSIP YANG MENGIKAT SELURUH RENCANA

1. **Marketing = performa. Finance = uang yang benar-benar cair.**
   `marketing_orders`/`marketing_sales_data` **tidak pernah** menulis jurnal keuangan.
   AR real hanya boleh dipicu oleh laporan **Settlement/Pencairan** marketplace (belum
   ada jenis impornya — masuk Fase 5).
2. **Pesanan hasil impor jadi SATU sumber omzet marketing.** Rekap harian
   (`marketing_sales_data`) **diturunkan** (recompute, idempoten) dari pesanan — bukan
   diketik lagi. Pola ini **sudah terbukti berjalan** di `marketing_live_sales_sync.py`.
3. **Semua per-toko (SSOT `account_id`).** Toko dipilih di wizard, bukan ditebak dari
   kolom. Target, anggaran, katalog, dan omzet semua dikunci ke `account_id` yang sama.
4. **Tanpa AI adalah jalur utama** untuk impor pesanan. AI (AI-assist) hanya tombol
   opsional untuk header yang benar-benar asing.
5. **Stok tidak boleh keluar sebelum pernah masuk.** Potong stok saat bukti kirim
   ditunda sampai 4 syarat rantai FG terpenuhi (lihat Fase 4).
6. **Tidak ada kode yang ditulis sebelum Anda menjawab §7 (keputusan wajib).**

---

## 1. MASALAH YANG DISELESAIKAN RENCANA INI (ringkas dari 2 analisis)

| # | Masalah terbukti | Dampak terukur |
|---|---|---|
| A1 | Jenis impor `orders` tidak mengenal data TikTok nyata | 601/602 baris impor **gagal**, omzet tercatat **Rp 0** dari Rp 62,8 jt |
| A2 | `sales_daily` (impor) tidak membungkus `metrics{}` | Target **Rp 0**, Dashboard **HTTP 500**, Health Score **15 vs 89** — untuk angka yang sama |
| A3 | Omzet punya 2 dunia (`marketing_sales_data` vs `marketing_orders`) tak pernah didamaikan | 2 layar bisa tampilkan omzet berbeda, tanpa peringatan |
| A4 | Sales Performance menjumlah `total_payment` per baris + filter nama toko (teks) | Omzet **+16,8%** dobel pada pesanan multi-SKU; ganti nama toko = riwayat hilang diam-diam |
| A5 | Target ⇄ Anggaran ⇄ Pesanan: 8 dari 8 pertanyaan sambungan = TIDAK | Tidak ada 1 layar yang menjawab "target, anggaran, terpakai, omzet" sekaligus |
| A6 | Diskon penjual (biaya promosi terbesar, Rp 48 jt/2minggu = 80,3% omzet bersih) tidak pernah masuk Anggaran | Biaya promosi terbesar **tidak tercatat otomatis** padahal datanya ada di ekspor |
| A7 | Katalog marketing (`TokoProductCatalogModule.jsx`) 100% Card/Grid, tanpa status Draft/Pre-order/Active, tanpa toggle tabel | Sulit dibaca untuk katalog besar; status tidak akurat (hanya boolean `is_active`) |
| A8 | Stok "katalog" punya 3 rumus berbeda (M1–M5, `_prove_catalog_master_gaps.py`) + sinkron marketplace masih **MOCK** (M11) | Qty di katalog tidak bisa dipercaya; tidak sinkron ke marketplace nyata |
| A9 | Tidak ada kunci periode & RBAC di Target/Anggaran/Omzet | Siapa pun bisa mengubah bulan lalu tanpa jejak |

---

## 2. ARSITEKTUR TO-BE (satu gambar)

```
SELLER CENTER (TikTok/Shopee, 1 menu ekspor per platform)
  Ekspor A "Perlu Dikirim" ─┐
  Ekspor B "Dikirim/Selesai"─┼─► WIZARD IMPOR (tanpa AI, per-toko wajib, idempoten, rollback)
  Ekspor C "Batal/Retur"    ─┘
                                  │
                                  ▼
                    marketing_orders  (kunci: account_id+platform+order_id+platform_sku_id)
                                  │
        ┌─────────────┬──────────┼───────────────┬────────────────────┐
        ▼             ▼          ▼               ▼                    ▼
  REKAP OMZET   MONITORING   KAMUS PRODUK   REALISASI ANGGARAN   ATRIBUSI OTOMATIS
  (turunan,     KERJA        83 SKU→8       diskon (SKU Seller   LIVE 70,9% ·
  recompute,    · blm kirim  produk induk   Discount) · ads      31 kreator ·
  idempoten)      >N hari    → tautan ke    (modul Ads)          47 provinsi
  marketing_      · bocor      fg_material_
  sales_data       A→B tak     id (katalog)
  metrics{}        muncul
        │
        ▼
  ┌───────────────────────────────────────────────────────────┐
  │  SATU LAYAR SIKLUS (per toko, per bulan)                  │
  │  target · anggaran · terpakai · omzet · marjin · sisa hari│
  │  peringatan "ketinggalan" / "kelewat" pada ambang tertentu│
  └───────────────────────────────────────────────────────────┘

TERPISAH TOTAL — tidak ada garis ke atas:
  Settlement/Pencairan marketplace (jenis impor baru) ──► Finance AR (real)
```

Katalog (paralel, menyatu lewat `fg_material_id`):
```
rahaza_materials (type=fg, master RND: HPP, status aktif)
        │  refresh eksplisit (tombol), TIDAK auto-sync (belum ada scheduler/hook)
        ▼
marketing_catalog_items (per toko)
  status: DRAFT (belum publish) · PRE_ORDER (SKU ada, qty gudang=0) · ACTIVE (publish, qty>0)
  qty: dibaca SATU rumus resmi dari rahaza_material_stock (bukan 3 rumus berbeda)
        │
        ▼
  UI: TABEL (default) + toggle ke Grid/Card — bukan Card-only
```

---

## 3. FASE KERJA — URUTAN WAJIB (fase berikutnya bergantung pada fase sebelumnya)

### FASE 0 — Perbaiki cacat yang MEROBOHKAN layar lain (sebelum apa pun)
**Isi:**
- `sales_daily` (impor) dibuat menulis bentuk dokumen yang **sama** dengan input manual:
  `metrics{revenue,orders,conversion_rate,...}`, `fulfillment{}`, `customer_satisfaction{}`,
  `live_metrics{}` — plus migrasi dokumen lama yang sudah ada di DB.
**Bukti selesai:** impor 1 baris Rp 12.500.000 ⇒ Target **Rp 12.500.000** (bukan 0) ·
Dashboard **200** (bukan 500) · Health Score **89** (bukan 15). Gate baru: dokumen
`marketing_sales_data` tanpa `metrics` = **MERAH** di validator.
**Kenapa paling depan:** tanpa ini, Fase 2 (turunan omzet dari pesanan) akan menuang data
ke bentuk yang salah lagi — memperbaiki di hilir sebelum di hulu = kerja dua kali.

### FASE 1 — Jenis impor `marketplace_orders` (Ekspor A) — jalur utama omzet
**Isi:**
- Kamus **nilai** (bukan hanya header): status Indonesia TikTok/Shopee → status kanonik;
  kurir (`J&T Express`→`jnt`, dst.) → kamus.
- Lewati baris deskripsi kolom otomatis (`skip_rows`/deteksi baris penjelas).
- Kunci baris: `(account_id, platform, order_id, platform_sku_id)` — 1 baris = 1 SKU.
- Kolom uang per-pesanan (`Order Amount`, ongkir, biaya layanan) ditulis **1× per Order ID**;
  kolom per-baris (`SKU Subtotal After Discount`, `Quantity`, `SKU Seller Discount`) per baris.
- Layar kamus **83 SKU platform → item katalog**, dikelompokkan per 8 produk induk (±15 menit).
- Toko wajib dipilih di wizard; `Purchase Channel` diperiksa (tolak kalau platform tak cocok),
  `Warehouse Name` jadi peringatan (bukan penolakan).
**Bukti selesai:** berkas asli 601 baris ⇒ **559 pesanan + 601 baris SKU, 0 ditolak**;
jalankan 2× ⇒ tidak ada tambahan; omzet produk **Rp 59.783.811** (bukan Rp 0).

### FASE 2 — Turunan rekap harian dari pesanan (menutup celah A2/A3)
**Isi:** fungsi recompute `(account_id, tanggal, revenue_type='total')` dari
`marketing_orders`, pola sama seperti `sync_live_sales_to_marketing()` — upsert, idempoten,
dipanggil setiap ada impor/ubah pesanan baru.
**Bukti selesai:** rekap harian terbentuk **tanpa diketik**; Target/Dashboard/ROI Anggaran
menunjukkan angka yang **sama** untuk bulan yang sama; hapus 1 pesanan ⇒ rekap ikut turun.
**Keputusan wajib sebelum fase ini (lihat §7‑T1/T2):** siapa pemilik omzet LIVE & kontribusi
kreator — impor atau shift/sesi yang diketik?

### FASE 3 — Jenis impor `marketplace_fulfillment` (Ekspor B & C) + Monitoring
**Isi:** satu jenis impor untuk Ekspor B ("Dikirim/Selesai") dan Ekspor C ("Batal/Retur") —
kolomnya identik, hanya kolom terisi yang beda. Menandai pesanan `sudah_dikirim`
(`Shipped Time`/`Delivered Time`) atau batal (`Cancelled Time`+`Refund Amount`).
Layar **Monitoring Pesanan**: belum dikirim >N hari, "bocor" (ada di A tak pernah muncul
di B), batal sesudah resi terbit.
**Bukti selesai:** impor B menandai n pesanan `sudah_dikirim`; daftar "belum diurus" muncul
dengan umur hari; rollback memulihkan keadaan sebelumnya.
**Potong stok TIDAK dinyalakan di fase ini** (lihat Fase 4 — bersyarat).

### FASE 4 — Katalog: status akurat + sinkron Qty/HPP dari master (bersyarat untuk potong stok)
**Isi:**
1. Perbaiki **M4** (`sync-from-wms` pakai `read_qty()`, bukan `.get('qty')` mentah) dan
   **M3** (ikutkan `reserved_quantity`, bukan overselling) dan **M5** (jangan lewati item
   yang tertaut lewat `variant_sku`) — satu rumus resmi untuk "qty katalog", dipakai di
   ketiga pintu (create/sync-item/sync-wms).
2. Status katalog 3-tingkat, dihitung dari data (bukan diketik):
   `DRAFT` = belum publish · `PRE_ORDER` = SKU/produk ada tapi qty gudang = 0 ·
   `ACTIVE` = publish + qty gudang > 0.
3. HPP disinkron dari `rahaza_materials.hpp` (tombol refresh sudah ada — pastikan dipanggil
   otomatis saat item dibuat, dan tersedia di UI baru).
4. **UI TokoProductCatalogModule** diubah dari Card-only → **Tabel (default) + toggle Grid**
   (komponen sudah ada: `toggle-group.jsx`, contoh pola: `ProductLaunchModule.jsx`).
5. **Syarat menyalakan potong-stok-saat-impor** (dari analisis impor §3.3/§3.4), keempatnya
   harus hijau sebelum sakelar bisa aktif:
   - master FG ada + `hpp` terisi;
   - item katalog toko tertaut `fg_material_id`;
   - kamus 83 SKU platform → item katalog terisi (dari Fase 1);
   - FG pernah masuk gudang (packing QC/penerimaan) ⇒ ada baris stok FG.
**Bukti selesai:** 3 rumus qty jadi 1 rumus (uji dengan `_prove_catalog_master_gaps.py` —
M1/M2/M3 harus jadi "TIDAK TERBUKTI" alias sudah diperbaiki); layar katalog tampil status
Draft/Pre-order/Active yang benar untuk data nyata; screenshot tabel + toggle.

### FASE 5 — Satu layar siklus Target · Anggaran · Omzet (per toko, per bulan) + realisasi otomatis
**Isi:**
- Satu endpoint/layar: target, anggaran, terpakai, omzet, marjin, sisa hari — untuk
  (`account_id`, bulan) yang sama.
- Realisasi anggaran otomatis: kategori `diskon` ← `SKU Seller Discount` (per baris, dari
  Fase 1); kategori `ads` ← `marketing_ads_data.spend` (modul Ads sudah ada, disambungkan).
- Peringatan "target ketinggalan" (>X% hari berlalu, <Y% tercapai) dan "anggaran kelewat"
  (>Z% terpakai) — ambang ditentukan Anda (§7‑Q6).
**Bukti selesai:** satu request API mengembalikan kelima angka; kategori `diskon` terisi
otomatis (bukan 0) untuk bulan yang punya data impor; peringatan muncul di ambang yang
ditetapkan.

### FASE 6 — Kunci periode + RBAC + jejak perubahan
**Isi:** setelah bulan ditutup, `target`/`anggaran`/`sales_data` untuk periode itu ditolak
diubah (kecuali peran berwenang, mis. superadmin/manajer) — dengan riwayat nilai lama
tersimpan (audit trail), bukan hanya `updated_by/updated_at`.
**Bukti selesai:** ubah target bulan tertutup ⇒ **403** untuk role biasa, **200** untuk role
berwenang, dan riwayat perubahan tercatat & bisa dilihat.

### FASE 7 (bersyarat, setelah Fase 4 selesai) — Marjin sebenarnya
ROI Anggaran dihitung dari **laba kotor** (omzet − HPP), bukan omzet saja — butuh HPP master
FG (Fase 4) dan snapshot HPP per Work Order sudah ada di sistem produksi.

### FASE 8 (terpisah, tidak memblokir apa pun di atas) — Settlement → Finance AR
Jenis impor baru untuk laporan **Settlement/Pencairan** marketplace (uang yang benar-benar
cair, sudah dipotong komisi platform). **Hanya jenis impor inilah** yang boleh memicu AR
di Finance. `marketing_orders`/`marketing_sales_data` tetap murni performa, selamanya.
Ini menuntaskan pemisahan Marketing vs Finance yang Anda minta secara permanen di level
arsitektur, bukan hanya kesepakatan lisan.

---

## 4. KUNCI/DEDUPE — RINGKASAN SATU TABEL (dipakai di semua fase impor)

| Tingkat | Kunci | Kolektor Mongo |
|---|---|---|
| Baris pesanan (SKU) | `account_id + platform + order_id + platform_sku_id` | `marketing_orders` |
| Nilai uang per pesanan (ditulis 1×) | `account_id + platform + order_id` | field di level pesanan |
| Produk | `platform_sku_id → catalog_item_id` (banyak-ke-satu) | `marketing_catalog_items` |
| Rekap harian (turunan) | `account_id + date + revenue_type` | `marketing_sales_data` |
| Anggaran/target | `account_id + period(YYYY-MM)` | `marketing_budgets`, `marketing_account_targets` |

---

## 5. AUDIT UI — HASIL NYATA (dijalankan ulang hari ini, `_audit_marketing_ui_views.py`)

Dari 49 modul yang diperiksa (`marketing/*Module.jsx` + `erp/*Module.jsx` terkait marketing):

- **Sudah Tabel saja:** 25 modul (mis. `CatalogManagementModule.jsx`, `KOLCreatorModule.jsx`,
  `BudgetModule.jsx`, `AccountTargetsModule.jsx`) — **tidak perlu diubah**.
- **Hanya Kartu (perlu 2 tipe tampilan):** `MarketingSchedulerModule.jsx`.
- **Kartu + Tabel tanpa toggle:** `MarketingWebhooksModule.jsx`.
- **Sudah punya toggle (contoh pola siap pakai):** `ProductLaunchModule.jsx`
  (`viewMode` table/timeline), `BuyerShipmentModule.jsx` (`viewMode` list), memakai
  `components/ui/toggle-group.jsx`.
- **Tidak terdeteksi regex tapi TERKONFIRMASI manual 100% Card/Grid, tanpa toggle, tanpa
  status akurat:** `TokoProductCatalogModule.jsx` (memakai `GlassCard` bukan `<Card`, jadi
  lolos dari regex audit — dicek langsung: grid 4 kolom, `is_active` boolean saja, tidak
  ada Draft/Pre-order). **Ini target utama Fase 4.**
- Catatan: `CatalogManagementModule.jsx` (1817 baris, sudah Tabel) tampaknya modul katalog
  **sisi admin/internal** yang berbeda dari `TokoProductCatalogModule.jsx` (sisi per-toko).
  Fase 4 akan memastikan **satu status & satu rumus qty** dipakai di kedua permukaan ini —
  bukan dua logika berbeda untuk hal yang sama.

**Kesimpulan §5:** keluhan Anda soal "Card/Grid dipaksakan" **secara faktual terkonsentrasi
di 3 titik** (`TokoProductCatalogModule`, `MarketingSchedulerModule`, `MarketingWebhooksModule`),
bukan menyebar ke seluruh modul marketing — 25 dari 32 modul relevan sudah Tabel. Fase 4
akan menuntaskan yang paling berdampak (katalog); 2 sisanya masuk pekerjaan UI kecil terpisah
(bisa disisipkan di Fase 4 sebagai "sekalian" karena polanya sama).

---

## 6. YANG SENGAJA TIDAK DIUBAH (agar ekspektasi jelas)

- Target & rencana anggaran **tetap diketik manusia** — tidak ada yang menebak dari data.
- Biaya `sample` **tetap manual** — tidak ada di ekspor manapun.
- Komisi platform **tetap tidak diketahui** sampai laporan settlement diimpor (Fase 8).
- Pembukuan **tetap manual** sesuai keputusan Anda sebelumnya — siklus ini laporan
  **marketing**, bukan laporan keuangan, dan layarnya akan mengatakan itu secara eksplisit.
- Integrasi API real-time ke Seller Center **tetap tidak dipakai** — jalur resmi adalah impor
  Excel/CSV, sesuai keputusan awal sesi ini.

---

## 7. KEPUTUSAN YANG WAJIB ANDA JAWAB SEBELUM FASE 1 DIMULAI

1. **T1 — Pemilik omzet LIVE:** impor (`Order Channel=LIVE`, saran saya) atau tetap dari
   shift host/sesi kreator yang diketik?
2. **T2 — Kontribusi kreator** (dasar hitung komisi KOL): dari ekspor `Creator Handle`
   (saran saya, 515/601 baris, gratis) atau dari sesi yang diketik manual?
3. **T3 — Label omzet:** cukup diberi label **"sebelum potongan platform"** (saran saya,
   paling cepat) atau langsung tambah jenis impor Settlement di Fase 8 sekarang juga?
4. **Potong stok:** mulai dengan **monitoring saja** dulu (Fase 1–3, saran saya) sambil
   rantai FG (Fase 4) dibangun, baru nyalakan potong-stok+COGS otomatis setelah 4 syarat
   terpenuhi — setuju urutan ini?
5. **Kunci periode & RBAC (Fase 6):** siapa saja yang boleh **menetapkan** target/anggaran
   (superadmin/manajer saja?) dan pada ambang berapa persen peringatan "ketinggalan"/
   "kelewat" muncul (contoh umum: kuning di 80%, merah di 100%)?
6. **`ANTHROPIC_API_KEY`:** dipasang untuk mengaktifkan tombol AI-assist opsional, atau
   dilewati (rencana ini tetap 100% jalan tanpa AI)?
7. **Urutan mulai:** setuju eksekusi dimulai dari **Fase 0 → 1 → 2 → 3 → 4 → 5 → 6**, dan
   **Fase 7–8 dikerjakan belakangan** sebagai pekerjaan terpisah?

Setelah Anda menjawab, saya akan langsung mulai dari **Fase 0** (perbaikan `sales_daily`)
karena itu satu perbaikan kecil yang membuat 5 layar sekaligus jujur, lalu **Fase 1**
(impor `marketplace_orders` memakai berkas TikTok Anda sebagai bukti nyata).
