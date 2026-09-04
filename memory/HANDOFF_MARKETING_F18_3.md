# 🤝 HANDOFF — Sesi #30 (Portal Marketing: F18#3 rincian produk live + bugfix `platform`)

> **BACA URUT**: berkas ini → `/app/plan.md` (bagian **LANJUTAN 2026-08-11**) →
> `/app/memory/BISNIS_PROSES_F18_NOTA_KREDIT_DAN_AR_BATCH.md` →
> `/app/memory/CHANGELOG.md`. Handoff sesi sebelumnya:
> `HANDOFF_MARKETING_F14_F17.md` (arsip, jangan dihapus).

## KONDISI AWAL SESI INI

Repo dipulihkan dari GitHub ke `/app` (klon bersih), MongoDB direstore dari
`backups/auto_20260810_190000` (192 koleksi). Yang WAJIB ditulis ulang setiap
pemulihan karena gitignored:

* `backend/.env` → `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, **`JWT_SECRET`**
  (tanpa ini backend `RuntimeError` dan mati), `EMERGENT_LLM_KEY`.
* `frontend/.env` → `REACT_APP_BACKEND_URL` (JANGAN diubah) + `GENERATE_SOURCEMAP=false`,
  `DISABLE_ESLINT_PLUGIN=true`.
* `frontend/build/` hilang setiap pod bangun → `bash scripts/rebuild_frontend.sh`.

## APA YANG DIKERJAKAN SESI INI (hanya 2 hal, atas keputusan owner)

### A. BUGFIX — `platform: None` pada Ulasan & Retur ✅

Sesi sebelumnya membuat `platform` opsional di model **tanpa mengganti
sumbernya**, jadi setiap baris baru tersimpan `platform: null` dan kartu/filter
“per platform” kehilangan seluruh baris baru **tanpa error**.

Sekarang `POST/PUT /api/marketing/reviews` dan `/returns`:
`require_account()` (account_id WAJIB, 400 bila kosong) + `stamp_account()`
(`account_name`/`platform` **selalu** dari master). `platform`/`account_name` yang
dikirim layar **diabaikan**. Item katalog toko lain tetap ditolak 400.

### B. F18#3 — RINCIAN PRODUK PER SESI LIVE ✅ (end-to-end)

**SSOT BARU: `backend/core/marketing_live_products.py`** — koleksi
`marketing_live_session_products` (1 baris = 1 produk pada 1 sesi).
**Jangan tulis koleksi ini dari tempat lain**; semua aturan ada di sini:

| Aturan | Kenapa |
|---|---|
| produk WAJIB item katalog **toko sesi itu** | rincian toko A yang menunjuk produk toko B merusak dua laporan sekaligus |
| indeks unik `(session_id, catalog_item_id)` | satu produk sekali per sesi — dijaga **basis data**, bukan hanya kode |
| jumlah rincian ≤ omzet sesi (toleransi 2%) | kalau lebih, omzet live dihitung **dua kali** |
| `revenue > 0` dengan `units_sold = 0` ditolak | salah input yang pasti |
| `units_sold = 0` **SAH** | “dibawakan tapi tidak ada yang beli” justru informasi penting |
| lingkup toko **diwarisi dari sesi** | lingkup baris tidak mungkin berbeda dari sesinya |
| `reconcile()` satu-satunya sumber angka cakupan | layar & server memakai definisi + pembulatan yang sama |

**Endpoint:** `GET/PUT/POST /api/marketing/live/sessions/{id}/products` ·
`PUT/DELETE .../products/{line_id}` · `POST .../products/sync-session-totals`
(“Samakan total sesi” = **aksi eksplisit**, bukan efek samping — total sesi
biasanya berasal dari laporan resmi marketplace dan tidak boleh ditimpa diam-diam) ·
`products[]` diterima pada `POST/PUT /live/sessions` · hapus sesi ⇒ rincian ikut
(cascade) · `GET /live/sessions` menyertakan `products_detail` per baris dalam
SATU agregasi per halaman.

**Analitik:** `GET /live/analytics/product-performance` kini beragregasi dari
koleksi rincian (fallback `products[]` legacy), **memakai** filter `account_id`
yang selama ini diabaikan, dan mengembalikan kolom **Toko** — karena katalog tiap
toko boleh memakai SKU yang sama, tanpa kolom itu satu SKU tampak dobel.

**Impor tanpa AI (F17) diperluas:** jenis data ke-16 `live_session_products` +
konteks baru `live_session` (sesi **dipilih** di wizard). Baris ber-SKU yang tidak
ada di katalog toko **ditandai galat di PRATINJAU** dan ditolak saat commit
(`_finish` boleh mengembalikan `doc=None` = tolak baris). Commit yang akan
melebihi omzet sesi ditolak **sebelum** menulis.

**Frontend:** `LiveSessionProductsEditor.jsx` (baris pilih katalog + rekonsiliasi
hidup) · `LiveSessionProductsDialog.jsx` (tombol **Rincian** per baris tabel) ·
kolom **Rincian Produk** di `LiveSessionModule` · tab **Produk Terlaris** + filter
toko di `LiveSessionAnalyticsDashboard` · pemilih **sesi live** di `DataImportWizard`.

## BUKTI (dijalankan, bukan dikutip)

```
python3 test_core_live_session_products.py   → 71 LULUS / 0 GAGAL
python3 scripts/verify_marketing_scope.py    → 32 PASS / 0 FAIL  (dulu 28)
bash scripts/gate.sh                         → 21/21 VERDICT HIJAU
```

MKS-24..27 **BARU** (lingkup toko rincian · baris yatim · produk dobel · rincian
melebihi omzet sesi). MKS-25 & MKS-27 **dibuktikan MERAH** dengan pelanggaran
sintetis lalu dibersihkan; MKS-26 tidak bisa dilanggar lagi karena indeks unik
menolaknya di DB.

Layar diverifikasi lewat browser (bukan hanya screenshot statis):
tambah produk → rekonsiliasi hidup 65%→69,5% → **Simpan** 200 → kolom tabel ikut
berubah → **Samakan total sesi** 200 (omzet sesi = jumlah rincian, cakupan 100%) ·
over-alokasi diperingatkan MERAH di layar, ditolak 400, dan pesannya TAMPIL ·
Catat Sesi Live + rincian dalam satu simpan (201) · wizard impor: tombol Lanjut
tetap nonaktif sampai sesi live dipilih (7 sesi ditawarkan).

## CACAT YANG DITEMUKAN & DIPERBAIKI SAAT VERIFIKASI LAYAR

Satu angka cakupan tampil **tiga versi** di dialog yang sama: kolom tabel `69.5%`,
baris rekonsiliasi `69%` (dihitung ulang di JS dengan pembulatan lain), pesan
server `70%` (`:.0f` atas 69,5). Layar yang membantah dirinya sendiri membuat
orang memilih angka yang paling enak dilihat. Sekarang satu format di satu tempat:
`core.marketing_live_products.pct()` + `fmtPct()` di editor (satu desimal, tanpa
“.0” menggantung).

## SISA PEKERJAAN (F18 — belum dikerjakan)

1. **Nota kredit retur** — **DITUNDA owner**; analisis + pertanyaan keputusan ada
   di `memory/BISNIS_PROSES_F18_NOTA_KREDIT_DAN_AR_BATCH.md`. Temuan terpenting:
   tombol **“Selesaikan & Terbitkan Nota Kredit”** memanggil `/complete` yang
   **tidak menerbitkan apa pun**; endpoint `create-credit-note` (lengkap, sampai
   posting GL) **tidak dipanggil layar mana pun**; 15 retur approved/completed,
   `rahaza_credit_notes` = **0 dokumen**.
2. **`generate-ar-batch`** — butir handoff lama **KEDALUWARSA**: endpoint sudah
   membalas **410** dengan pesan jelas. Sisa kecil: model request masih mewajibkan
   `date_from`/`date_to`, jadi body tak lengkap dapat 422 dulu (bukan 410).
3. **LiveHost**: `shifts/calendar`, `training/progress`, `sop/download` — endpoint
   ada, layar belum.
4. **Daftar acuan** `content-calendar/platforms` & `discounts/types` masih disalin
   di JS (akan basi).
5. **Sisa teks bebas**: `ComplaintIn.product_name` (modul komplain **belum punya
   endpoint create** sama sekali — hanya seed + GET + PATCH status) ·
   `LaunchIn.material`/`.model` · `CatalogItemCreate.sku`.

## CATATAN LINGKUNGAN

* Frontend **TIDAK hot reload** (PREVIEW STABLE MODE) → sesudah mengubah
  `frontend/src/**` WAJIB `bash /app/scripts/rebuild_frontend.sh` (~60 detik).
* **JANGAN mengirim dua `search_replace` paralel ke BERKAS YANG SAMA** — di sesi
  ini satu perubahan (`TABS` analitik) hilang tertimpa karena itu, dan baru
  ketahuan dari screenshot. Edit berkas yang sama harus berurutan.
* Data demo: 3 akun toko → 3 katalog (18 item, **SKU sengaja sama antar toko**) →
  18 sesi live → **51 baris rincian produk** (seed `_seed_origin: True`).
  Seed rincian hanya jalan bila koleksinya kosong; hapus baris `_seed_origin`
  lalu restart backend untuk membuatnya ulang.
