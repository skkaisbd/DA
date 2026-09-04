# 🤝 HANDOFF — Sesi #29 (Portal Marketing: F14–F17) ✅ TERVERIFIKASI

> **BACA URUT**: berkas ini → `/app/plan.md` (bagian **LANJUTAN 2026-08-11**) →
> `/app/memory/AUDIT_MARKETING_PORTAL_2026-08-11.md` → `/app/memory/CHANGELOG.md`.
> Handoff sesi lama: `HANDOFF_NEXT_AGENT.md` (arsip, jangan dihapus).

## APA YANG DIKERJAKAN SESI INI

Permintaan owner: *"masih banyak logic error di portal marketing — form yang
seharusnya select ke tabel lain malah custom input, ada field tanpa input
(dead/useless), endpoint yang salah memanggil tabel/field sehingga fitur tidak
berfungsi"* + *"import data marketing harus bisa jalan tanpa AI"*.

Pendekatannya **mengukur dulu, baru memperbaiki**. Lima harness dibuat supaya
temuan bisa diulang siapa pun, bukan dipercaya:

| Harness | Menjawab |
|---|---|
| `scripts/audit_marketing_portal.py` | endpoint hantu · lintas domain · endpoint tanpa layar · koleksi |
| `scripts/audit_marketing_fields.py` | lingkup toko · teks bebas vs select · field mati · input hantu |
| `scripts/audit_marketing_integrity.py` | rujukan yatim pada data NYATA |
| `scripts/audit_marketing_runtime.py` | semua GET marketing dipanggil sungguhan |
| `scripts/audit_marketing_field_reads.py` | **field yang dibaca tapi tidak pernah ada di dokumen** |

## TEMUAN TERBESAR (dan kenapa sunyi)

1. **Data marketing tidak berlingkup toko.** 60/60 order · 25/25 iklan · 18/18 sesi
   live · 35/35 sample · 30/30 konten · 10/10 diskon · 8/8 peluncuran **tanpa
   `account_id`**. Filter "per toko" mengembalikan KOSONG dan laporan per akun
   Rp 0 — tanpa satu pun error.
2. **Live Selling melaporkan Rp 0.** Ringkasan menjumlahkan `$gmv`,
   `$total_orders`, `$cr_rate` yang **tidak pernah ada** (yang tersimpan
   `revenue`/`orders`/`conversion_rate`) ⇒ kartu "Total Revenue Rp 0" **tepat di
   atas tabel berisi puluhan juta**. Sekarang Rp 512 jt untuk 20 sesi.
3. **Seluruh `/live/analytics/*` mengembalikan 0/kosong.** `session_date` bertipe
   datetime tapi difilter dengan string `"YYYY-MM-DD"` — di MongoDB tipe berbeda
   tidak pernah cocok. 7 endpoint kini 200 dengan angka nyata.
4. **Impor 100% bergantung AI.** `universal_import.py` memanggil AI dua kali
   (deteksi skema + normalisasi SETIAP baris); AI gagal ⇒ impor mati total. Dan
   **dua jenis ditulis ke koleksi yang tidak pernah dibaca layar**
   (`marketing_discount_campaigns`, `marketing_sample_shipments`).
5. **Iklan & sesi live tidak punya CRUD sama sekali** (hanya GET) ⇒ mustahil
   memasukkan biaya iklan atau mencatat sesi live lewat aplikasi.

## YANG WAJIB DIPERTAHANKAN (jangan dibongkar tanpa alasan)

- **`core/marketing_account_scope.py` = SSOT lingkup toko.** SEMUA penulis data
  marketing lewat sini (`require_account` + `stamp_account`). `account_name` &
  `platform` **selalu turunan** dari master — jangan pernah menerimanya sebagai
  teks yang disimpan apa adanya.
- **`assert_host_assigned` / `assert_creator_assigned`.** Host/kreator yang belum
  di-assign ke toko HARUS ditolak 400. Kalau dilonggarkan, jam kerja host & komisi
  kreator bisa dibebankan ke toko yang tidak memakainya. Dijaga gate MKS-23.
- **`core/marketing_live_fields.py` = SSOT nama field sesi live.** Nama kanonik
  `revenue`/`orders`/`total_viewers`/`conversion_rate`. Ejaan lama (`gmv`,
  `total_orders`, `cr_rate`, `viewers`) hanya DIBACA sebagai cadangan — **jangan
  ditulis lagi**.
- **`core/marketing_import_schema.py` = satu-satunya sumber tujuan koleksi impor.**
  Jangan menambah peta koleksi di tempat lain; itulah cara cacat "impor berhasil
  tapi datanya hilang" lahir.
- **AI pada impor tetap OPSIONAL.** `ai-assist` hanya MENGUSULKAN untuk kolom yang
  belum terpetakan, tidak pernah menimpa `exact`/`synonym`/`manual`.

## BUKTI (dijalankan, bukan dikutip)

```
python3 test_core_marketing_import_noai.py    → 81 LULUS / 0 GAGAL
python3 scripts/verify_marketing_scope.py     → 28 PASS / 0 FAIL   (INV-MKTSCOPE)
python3 scripts/audit_marketing_integrity.py  → 0 rujukan cacat    (sebelumnya 9)
python3 scripts/audit_marketing_field_reads.py→ rujukan-diri 0     (sebelumnya 3)
python3 scripts/audit_marketing_portal.py     → hantu 0
bash scripts/gate.sh                          → 21/21 VERDICT HIJAU
```
Layar diverifikasi lewat browser: wizard impor 6 langkah (15 kartu jenis data,
9/9 kolom terpetakan **pasti** tanpa AI, commit 2 baris, riwayat menyebut toko &
pengguna) · Live Selling (KPI Rp 512 jt, kolom Toko, dialog Catat Sesi Live) ·
Ads (dialog Input Biaya Iklan + blok hitungan) · Kirim Sample (pemilih kreator &
item katalog, ukuran/warna jadi select).

## SISA PEKERJAAN (F18 — belum dikerjakan)

1. **Nota kredit retur** — 4 endpoint tanpa layar (`returns/credit-notes*`,
   `returns/{id}/create-credit-note`). Akibat sekarang: retur berhenti di
   "disetujui", uang tidak pernah dikembalikan di buku.
2. **LiveHost**: `shifts/calendar`, `training/progress`, `sop/download` — endpoint
   ada, layar belum.
3. **`live/analytics/product-performance`** masih tanpa sumber: `products[]` per
   sesi belum bisa diisi (CRUD & impor belum menerima rincian per produk).
   Pesannya sudah dibuat bisa ditindaklanjuti, bukan "no data".
4. **`POST /api/marketing/sales-data/generate-ar-batch`** masih menerima 8 field
   tanpa efek — jadikan penolakan eksplisit (410) sesuai keputusan owner 1.a.
5. **Daftar acuan** `content-calendar/platforms` & `discounts/types` masih belum
   dipakai layar (daftar platform/jenis masih disalin di JS ⇒ akan basi).
6. **Teks bebas yang BELUM diubah jadi select** (`audit_marketing_fields.py`
   masih melaporkan 57 field). Yang sudah dikerjakan: Kirim Sample (kreator,
   produk, ukuran, warna, HPP) · Peluncuran (akun). Yang **belum**:
   `ReviewIn.product` & `.category` · `ReturnIn.product` · `ComplaintIn.product_name`
   · `LaunchIn.material`/`.model` · `CatalogItemCreate.sku`. Pola perbaikannya
   sudah ada dan tinggal dipakai ulang: `CatalogItemSelect` dari
   `marketing/pickers/MarketingPickers.jsx` + `catalog_item_id` di model backend.
   Catatan: `platform` pada banyak model kini SAH sebagai turunan akun
   (`stamp_account` menimpanya), jadi laporan audit untuk field itu bukan cacat.
7. 67 endpoint marketing masih "tanpa layar" (`audit_marketing_portal.py --verbose`);
   sebagian sah (portal kreator/livehost dipakai aplikasi portal terpisah), tapi
   daftar ini layak ditinjau satu per satu.

## CATATAN LINGKUNGAN

- Frontend **TIDAK hot reload** (PREVIEW STABLE MODE). Sesudah mengubah
  `frontend/src/**` WAJIB `bash /app/scripts/rebuild_frontend.sh` (~2 menit).
- Migrasi F14 sudah dijalankan (`scripts/migrate_marketing_account_scope.py`).
  Untuk DB baru, seed sudah benar sejak awal — tidak perlu migrasi lagi.
- Data demo marketing kini **koheren**: 8 akun → 8 katalog (48 item) → 60 order
  memakai SKU katalog (0 yatim) → 30 retur & 40 ulasan menempel order nyata.
