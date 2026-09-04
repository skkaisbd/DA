# RENCANA EKSEKUSI MASTER — Marketing · Katalog · Konten · Laporan · Settlement
### Versi FINAL 2026-08-12 · menggantikan `RENCANA_EKSEKUSI_MARKETING_2026-08-11.md`

**Dokumen wajib dibaca bersama:**
1. `memory/VERIFIKASI_2026-08-12.md` — buku bukti: **apa yang masih rusak (D01–D22)** dan
   **apa yang sudah beres (jangan dikerjakan ulang)**.
2. `memory/SSOT_KONTRAK_DATA_2026-08-12.md` — **kontrak data**: nama koleksi & field kanonik,
   9 aturan yang tidak bisa dinegosiasi, peta jenis impor.

> Rencana lama **dibatalkan** karena memuat pekerjaan yang sudah selesai (M1–M5 katalog,
> pemutusan Marketing→AR, SSOT lingkup toko). Eksekusi mentah rencana lama = duplikasi.

---

## BAGIAN A — ATURAN KERJA UNTUK AGENT PENGEKSEKUSI (anti-halusinasi)

**A1. Sebelum menyentuh kode di fase apa pun — jalankan 3 perintah ini:**
```bash
cd /app/backend && python3 /app/scripts/_forensic_ssot_v3.py      # simpan baseline JSON
cd /app        && python3 scripts/_audit_ui_tables_v2.py
cd /app        && python3 scripts/gate_marketing_ssot.py          # ada setelah F0
```
**A2. Dilarang menebak.** Bila sebuah field/koleksi/endpoint tidak tertulis di
`SSOT_KONTRAK_DATA_2026-08-12.md`, **jangan dipakai**; perbarui kontraknya dulu
(1 commit khusus dokumen), baru kode.

**A3. Dilarang membuat koleksi baru** di luar `core/collection_registry.py` (dibuat F0.1).
Gate akan merah. Koleksi baru yang sah dalam rencana ini hanya **4**:
`marketing_settlements`, `marketing_period_locks`, `marketing_change_log`,
`marketing_data_import_formats` (sidik format impor — menggantikan `marketing_import_templates`
yang dihapus di F0.6).

**A4. Dilarang membuat modul UI baru** untuk hal yang sudah ada modulnya. Perintah owner:
*"jangan tambah baru namun duplikasi, saya prefer enhance yang sudah ada"*.
Modul baru yang sah dalam rencana ini: **0**. Semua pekerjaan UI = **menyunting modul yang ada**
(daftar berkas tepatnya ada di tiap fase).

**A5. Selesai ≠ kode jalan.** Fase dinyatakan selesai hanya bila **angka bukti** di bagian
"BUKTI SELESAI" fase itu **sama persis** dengan yang tertulis. Angka-angka itu berasal dari
berkas nyata `samples/TikTok_UntukDikirim_2026-07-19.xlsx` dan tidak boleh diubah.

**A6. Setelah fase selesai:** jalankan ulang A1. **Dilarang** bertambahnya:
`read_never_written`, `written_never_read`, `single_file_islands`, `collections_in_code`.
Bila bertambah → ada fitur baru yang berdiri sendiri → **perbaiki sebelum lanjut**.

**A7. Setiap endpoint daftar** wajib: menerima `account_id`, memakai
`visible_account_ids(user)` (setelah F6), memberi `total`, dan **tidak** memotong hitungan
ringkasan ke halaman aktif saja (pelajaran F11 katalog).

**A8. Setiap elemen UI interaktif** wajib `data-testid`. Setiap tabel wajib: sticky header,
sort, pencarian, pemilih kolom, ekspor CSV, dan **pengalih Tabel/Kartu** (Bagian B).

**A9. Migrasi data** selalu: `--dry-run` dulu (mencetak jumlah dokumen terdampak) →
laporkan → baru `--apply`. Semua migrasi idempoten dan ditulis di `backend/migrations/`.

**A10. Urutan fase tidak boleh ditukar** kecuali F7/F8/F9 (lihat Bagian D).

---

## BAGIAN B — STANDAR UI YANG BERLAKU DI SEMUA FASE

**B1. Dua tipe tampilan (keputusan owner).** Untuk setiap layar yang menampilkan *daftar
record*: **Tabel = default**, **Kartu/Grid = alternatif**, dipilih lewat pengalih yang sudah ada
di repo — **jangan bikin komponen baru**:
- pola: `const [viewMode, setViewMode] = useState('table')` seperti
  `components/erp/marketing/ProductLaunchModule.jsx`
- komponen: `components/ui/toggle-group.jsx`
- pilihan pengguna disimpan di `localStorage` per modul: `view:<moduleId>`

**B2. Kartu tetap sah** untuk: KPI tile ringkasan (angka besar), wizard, form, kalender.
Kartu **tidak sah** untuk daftar record (pesanan, item katalog, sample, kreator, konten).

**B3. Tabel wajib "informasi penuh"**. Cacat D19: `UnifiedOrdersDashboard` 3 kolom,
`KOLCreatorModule` 2 kolom padahal dokumennya punya 30+ field. Setiap tabel di fase ini
punya **daftar kolom yang ditulis di fase tersebut**, plus:
- pemilih kolom (tampil/sembunyi) tersimpan di `localStorage`
- kolom uang: rata kanan, format `Rp 1.234.567`, `0` ditulis `—` bila memang tidak ada data
- kolom turunan wajib punya penjelasan (tooltip) yang menyebut **sumber angkanya**

**B4. Bahasa.** Semua label, pesan galat, dan tooltip dalam **Bahasa Indonesia** dan
menyebutkan **tindakan berikutnya** ("SKU ini belum ada di katalog toko — tambahkan di
Manajemen Katalog lalu impor ulang barisnya").

**B5. Keadaan wajib ditangani** di tiap layar: memuat, kosong (dengan ajakan aksi),
galat (dengan sebab), tanpa izin (dengan siapa yang bisa memberi), periode terkunci.

---

## BAGIAN C — KEPUTUSAN OWNER (FINAL, jadi dasar seluruh rencana)

| # | Keputusan | Konsekuensi teknis |
|---|---|---|
| K1 | **Dua angka omzet ditampilkan**; satu jadi dasar Target | `metrics.revenue_product` **dan** `metrics.revenue_order_amount` selalu disimpan; `marketing_platform_accounts.revenue_basis` (default `produk_setelah_diskon`) menentukan `metrics.revenue` & pencapaian Target |
| K2 | Rekap harian **diturunkan** dari pesanan impor; ketik manual **hanya** untuk platform tanpa ekspor | `core/marketing_daily_rollup.py`; dokumen `source=orders_auto` + `locked_source=true` menolak entri manual (409) |
| K3 | Impor **utamakan tanpa AI**; AI hanya pembantu karena format ekspor bisa banyak | kamus sinonim + `value_map` + **`format_fingerprint`** (format yang sudah dikenal → langsung terpetakan). Tombol AI hanya untuk kolom sisa |
| K4 | **Pencairan/Settlement** = satu-satunya pemicu Finance, dan hanya jadi **DRAFT jurnal** yang di-approve Finance | koleksi `marketing_settlements` + profil posting `marketplace_settlement` + `status='draft'` |
| K5 | Target & Anggaran diset **di dua portal** (Manajemen & Marketing) | satu komponen dipakai dua id modul; hak akses membedakan kemampuan |
| K6 | Kategori anggaran **+`komisi`**; gratis ongkir tidak perlu | `CATEGORIES = ['ads','kol','livehost','sample','diskon','komisi']` |
| K7 | Status katalog: DRAFT · PRE_ORDER · ACTIVE · HABIS · NONAKTIF/ARSIP · **DITOLAK** | `core/catalog_status.py` (turunan), `publish_state` (manual) |
| K8 | "Sudah tayang" = **staf menandai + mengisi link produk marketplace** | `publish_state='published'` wajib disertai `platform_url` |
| K9 | Foto master **dibawa** ke katalog; marketing tetap bisa unggah foto marketplace | `master_images[]` (turunan) + `images[]` (unggahan) |
| K10 | **Satu** modul katalog, 2 tampilan, filter per toko | `CatalogManagementModule` jadi satu-satunya; `toko-products` → redirect |
| K11 | Konten: tambah pemilik, link video terbit, dan KPI | field baru + jenis impor `content_performance` |
| K12 | Laporan: tambah **Mingguan** ke modul laporan yang ada; PDF & Excel | `GET /api/marketing/reports/weekly` + pengalih periode |
| K13 | KPI funnel: **siapkan dua jalur** — impor KPI **dan** form input mingguan | jenis impor `shop_kpi` + tab "KPI Mingguan" di `SalesDataEntryModule` |
| K14 | RBAC: `spv_marketing`, `staff_marketing`(=`pic_toko`), `content_creator`, `host_live`; lingkup toko ditegakkan | `visible_account_ids()` + penjaga di ~30 endpoint |
| K15 | **Hapus total** jalur impor AI lama + mesin impor sales lama; satukan jadi 1 pintu (`data-import`). **Data & riwayat lama diabaikan** (owner: "mulai saja, abaikan data lama") | 2 berkas route + 3 berkas UI dihapus, 7 titik `server.py` dibersihkan, 7 koleksi legacy di-drop. Tabrakan ruang URL `/api/marketing/import/*` hilang permanen |
| K16 | Ambang peringatan kuning **80%**, merah **100%**; kunci periode; pembuka = `owner`/`spv_marketing` | `marketing_period_locks` + 2 jenis alert baru |
| K17 | Potong stok saat impor **BELUM** dinyalakan — monitoring dulu | F3 hanya memantau; sakelar stok menyusul setelah rantai FG hijau |

---

## BAGIAN D — PETA FASE

```
F0  PAGAR & FONDASI (blocker)            ← WAJIB PERTAMA, tanpa ini fase lain menuang ke bentuk salah
F1  Impor Pesanan Marketplace (Ekspor A) ← jalur omzet resmi
F2  Rekap Harian TURUNAN                 ← menyatukan 2 dunia omzet
F3  Impor Fulfillment (Ekspor B/C) + Monitoring
F4  Katalog: status, foto, satu layar, kolom penuh
F5  Satu Layar Siklus (Target·Anggaran·Omzet·Marjin) + realisasi otomatis + alert
F6  RBAC per toko + kunci periode + jejak perubahan
F7  Konten & Content Creator (KPI + link terbit)        ┐ boleh paralel setelah F6
F8  KPI toko + Laporan Harian/Mingguan/Bulanan          ┤ (F8 butuh F2; F7 butuh F6)
F9  Settlement → Finance (DRAFT jurnal)                 ┘ butuh contoh berkas (BLOKIR-DATA)
F10 Konsolidasi duplikasi + gate akhir
```

**Ketergantungan data dari owner (BLOKIR-DATA):**
| Kode | Dibutuhkan | Memblokir | Bila belum ada |
|---|---|---|---|
| BD-1 | 1 contoh **Ekspor B** ("Dikirim/Selesai") & **Ekspor C** ("Batal/Retur") TikTok | F3 | F3 dikerjakan dengan asumsi kolom identik Ekspor A (kolom waktu terisi); harus diuji ulang saat berkas datang |
| BD-2 | 1 contoh laporan **Pencairan/Settlement** TikTok **dan** Shopee | F9 | F9 **tidak boleh** dimulai — pemetaan kolom uang tidak boleh ditebak |
| BD-3 | 1 contoh ekspor **KPI/Analisis** (Shopee "Data Toko" / TikTok "Analisis") | F8 jalur impor | jalur **form input mingguan** tetap dibangun (K13), impor menyusul |
| BD-4 | 1 contoh ekspor **Shopee Orders** | F1 (perluasan) | F1 selesai untuk TikTok; Shopee ditambahkan sebagai `format_fingerprint` kedua |
| BD-5 | Daftar **9 toko nyata** + PIC + rekening penerima pencairan | F0.7 | dipakai kode COA yang sudah ada (`4-111`…`4-131`) sebagai daftar awal, owner mengoreksi |

---

# FASE F0 — PAGAR & FONDASI

**Tujuan:** menghentikan kerusakan yang sedang berjalan, dan menyiapkan satu bentuk data
yang benar **sebelum** data nyata masuk. Tanpa F0, F1/F2 hanya menuang data ke bentuk salah.

### F0.1 Registry koleksi + gate
**Buat:** `backend/core/collection_registry.py`
```python
# Satu-satunya daftar koleksi yang SAH. Kunci = nama koleksi, nilai = (domain, pemilik_modul, catatan)
REGISTRY: dict[str, tuple[str, str, str]] = { ... }   # diisi dari memory/FORENSIC_SSOT_V3.json
DEPRECATED = {"marketing_discount_campaigns": "marketing_discounts",
              "marketing_sample_shipments":   "marketing_samples"}
def assert_registered(name: str) -> None: ...
```
**Buat:** `scripts/gate_marketing_ssot.py` — gate MERAH bila:
1. ada berkas di `backend/routes|core|services` menyentuh koleksi di luar `REGISTRY`;
2. ada dokumen `marketing_sales_data` tanpa kunci `metrics`;
3. ada dokumen marketing tanpa `account_id` pada koleksi yang `account_scope='required'`;
4. ada penulisan ke koleksi `DEPRECATED`;
5. `read_never_written` / `written_never_read` bertambah dari baseline
   (`memory/FORENSIC_SSOT_V3.json` disimpan sebagai baseline saat F0 selesai).

### F0.2 Satu pembuat bentuk rekap harian
**Buat:** `backend/core/marketing_sales_shape.py`
```python
def build_daily_doc(*, account: dict, date: str, revenue_type: str, flat: dict,
                    source: str, revenue_basis: str) -> dict
    """SATU-SATUNYA pembuat dokumen marketing_sales_data.
    `flat` = angka datar (dari form manual ATAU dari baris impor ATAU dari rollup).
    Mengembalikan dokumen bersarang lengkap sesuai SSOT §3 — semua grup SELALU ADA."""
def read_metrics(doc: dict) -> dict        # pembaca aman: dukung dokumen lama yang datar
def read_group(doc: dict, group: str) -> dict
```
**Ubah (pakai builder ini, hapus pembuatan dict manual):**
- `backend/routes/marketing_sales.py:59-95` (entri manual)
- `backend/routes/marketing_data_import.py::_finish` cabang `sales_daily`
- `backend/routes/marketing_live_sales_sync.py:60-90` (sudah bersarang — cukup dialihkan ke builder)
- `backend/routes/marketing_tasks.py` (penulis ke `marketing_sales_data` lewat aksi tugas)

### F0.3 Pembaca defensif (hapus indeks langsung)
Ganti semua `doc["metrics"]` / `doc["account_id"]` langsung menjadi `read_metrics(doc)`:
- `backend/routes/marketing_dashboard.py:62,63,66,72` **(sumber HTTP 500)**
- `backend/routes/marketing_targets.py:158-159`
- `backend/routes/marketing_budget.py:179-205` (`_sales_revenue`)
- `backend/routes/marketing_reports.py` (daily & monthly)
- `backend/routes/marketing_account_health_routes.py` (skor kesehatan)
- `backend/utils/scheduler.py` (job alert)
- `backend/routes/marketing_shared.py`

### F0.4 Migrasi dokumen lama
**Buat:** `backend/migrations/2026_08_12_sales_data_nested.py`
- temukan dokumen `marketing_sales_data` tanpa `metrics` → bungkus lewat `build_daily_doc`
- gabungkan duplikat `(account_id, date, revenue_type)` (jumlahkan, catat di `merged_from[]`)
- `--dry-run` wajib dulu. Cetak: jumlah datar, jumlah duplikat, jumlah setelah migrasi.

### F0.5 Indeks
`backend/server.py` (blok indeks, dekat baris 838-881):
- `marketing_sales_data` → **unique** `(account_id, date, revenue_type)` (setelah F0.4)
- `marketing_orders` → **unique** `(account_id, platform, order_id)`; tambah `account_id`,
  `items.platform_sku_id`, `order_channel`, `creator_handle`
- `marketing_account_targets` → unique `(account_id, year, month)`
- `marketing_creator_targets` → unique `(creator_id, year, month)`
- `marketing_budgets` → unique `(account_id, period)`

### F0.6 HAPUS TOTAL 2 mesin impor lama (K15 — keputusan owner: **opsi c**, data lama diabaikan)

> Owner memilih **hapus total berkas + rutenya**, dan **abaikan data lama**. Ini menghilangkan
> secara permanen: koleksi tujuan yang salah, dokumen tanpa `account_id`, commit tanpa dedupe,
> bentuk rekap harian ke-3, **dan** tabrakan ruang URL `/api/marketing/import/*`.
> Aman: di DB sekarang `marketing_import_sessions`=**0**, `marketing_import_uploads`=**0**,
> `marketing_import_templates`=**0**, `marketing_import_history`/`marketing_discount_campaigns`/
> `marketing_sample_shipments` **belum pernah ada**.

**(a) Hapus berkas backend**
| Berkas | Baris | Catatan |
|---|---|---|
| `backend/routes/universal_import.py` | 982 | mesin AI lama (peta koleksi salah, `**committed_data`, tanpa `account_id`, tanpa dedupe, WebSocket editor) |
| `backend/routes/marketing_import.py` | 983 | mesin khusus sales (bentuk `metrics{}` ke-3, upsert menimpa `id` dokumen) |
| `backend/routes/universal_import_indexes.py` | 33 | **pindahkan dulu** baris 26-31 (indeks `id` unik + `_import_session_id` untuk koleksi tujuan impor) ke blok indeks `server.py`, baru hapus berkasnya |

**(b) Bersihkan `backend/server.py` — 7 titik**
| Baris | Isi sekarang | Tindakan |
|---|---|---|
| 288-292 | `from routes.universal_import import retry_queued_sessions` (retry saat startup) | hapus seluruh blok |
| 928-929 | `db.marketing_import_uploads.create_index(...)` ×2 | hapus |
| 1016 | `from routes.universal_import_indexes import ensure_import_indexes` | ganti: indeks inline (hasil pindahan (a)) |
| 1585 | `from routes.marketing_import import router as marketing_import_router` | hapus |
| 1597 | `from routes.universal_import import router as universal_import_router` | hapus |
| 1613-1615 | komentar "MUST be registered BEFORE…" + `include_router(universal_import_router)` | hapus — **masalah urutan router hilang permanen** |
| 1622 | `include_router(marketing_import_router)` | hapus |

**(c) Hapus berkas frontend**
| Berkas | Baris | Catatan |
|---|---|---|
| `frontend/src/components/erp/marketing/ImportCenterPage.jsx` | 406 | daftar sesi AI lama |
| `frontend/src/components/erp/marketing/SmartImportEditorPage.jsx` | 576 | editor sel + WebSocket ke rute yang dihapus |
| `frontend/src/components/erp/SmartImportModule.jsx` | ~350 | **mesin impor ke-4 (ZOMBIE)** — di-`lazy()` di `moduleRegistry.js:384` tetapi **tidak pernah dipetakan ke id modul mana pun** ⇒ tidak bisa dibuka dari menu; ia memanggil `/api/marketing/import/upload|analyze|preview|execute|rollback` + `/api/marketing/import-templates` yang semuanya dihapus |
| `frontend/src/components/erp/moduleRegistry.js:384` | 1 baris | hapus baris `const SmartImportModule = lazy(...)` |
| `frontend/src/components/erp/ImportCenterModule.jsx` | 60 → ~15 | dipangkas: **langsung** me-render `<DataImportWizard token user />`, tanpa `Tabs`, tanpa state `selectedSessionId`. Menu `marketing-import` (`portal-shell/portalNav.js:652` "Impor Data") **tetap** dan langsung membuka wizard |

**(d) Bersihkan database & disk** — `backend/migrations/2026_08_12_drop_legacy_import.py`
- `--dry-run` mencetak jumlah dokumen per koleksi; `--apply` men-`drop()`:
  `marketing_import_sessions`, `marketing_import_uploads`, `marketing_import_templates`,
  `marketing_import_history`, semua `marketing_import_*` sisa,
  `marketing_discount_campaigns`, `marketing_sample_shipments`
- hapus folder `/app/uploads/marketing-imports` (milik mesin lama). Folder jalur benar
  `/app/uploads/marketing-data-import` **jangan disentuh**.

**(e) Perbaiki cacat sunyi yang ikut ketemu (D24)**
`backend/utils/scheduler.py::job_cleanup_old_marketing_uploads` menunjuk `/app/uploads/marketing`
— **folder itu tidak ada**, jadi job pembersih ini **tidak pernah membersihkan apa pun** sejak dibuat
(log-nya "not found, skipping"). Arahkan ke `/app/uploads/marketing-data-import`.

**(f) Registry** — ke-7 koleksi di (d) masuk `DEPRECATED` di `core/collection_registry.py`;
gate MERAH bila ada kode baru menyentuhnya.

### F0.7 Master toko nyata + tautan Finance (BD-5)
- Tambah field ke `marketing_platform_accounts` (lihat SSOT §1): `coa_revenue_code`,
  `coa_cash_code`, `coa_receivable_code` (default `1-220`), `platform_warehouse_name`,
  `platform_shop_id`, `revenue_basis`.
- **Ubah** `backend/routes/marketing_accounts.py`: model + validasi (kode COA harus ada di
  `rahaza_coa_accounts`), dan `GET /api/marketing/accounts/coa-options` untuk pemilih.
- **UI** `frontend/src/components/erp/AccountManagementModule.jsx`: tambah kolom tabel
  (PIC, Akun Pendapatan, Rekening Pencairan, Basis Omzet, Gudang Platform) + form.
- **Seed** `backend/scripts/seed_marketing_real_accounts.py` (idempoten). Kandidat toko diambil
  dari COA yang **sudah ada** (bukan karangan) — **9 toko**:
  | COA | Toko | platform |
  |---|---|---|
  | `4-111` | Shopee Grosirhijabsragen | shopee |
  | `4-112` | Shopee Daluna | shopee |
  | `4-113` | Shopee Moen | shopee |
  | `4-121` | TikTok Daluna | tiktok |
  | `4-122` | TikTok Outfit Boutique (`platform_warehouse_name='Outfit Boutique'`) | tiktok |
  | `4-123` | TikTok Style by Moen | tiktok |
  | `4-124` | TikTok Fatimahijab | tiktok |
  | `4-125` | TikTok Dezza Kids | tiktok |
  | `4-131` | Tokopedia | tokopedia |

  `4-114` "Shopee Lain-lain" dan `4-126` "TikTok Lain-lain" **bukan toko** — keduanya akun
  penampung; dipakai sebagai `coa_revenue_code` **default** bila toko baru belum punya akun sendiri.
  3 akun DEMO ditandai `status='closed'`, `is_demo=true` (**tidak dihapus** — dipakai uji).
  **BD-5:** owner mengoreksi daftar ini (nama, PIC, rekening pencairan) sebelum dipakai produksi.

### BUKTI SELESAI F0 (harus sama persis)
1. Impor `sales_daily` 1 baris `revenue=12.500.000, orders=48, date=2026-08-01` lewat wizard →
   `GET /api/marketing/targets/monthly-summary?year=2026&month=8` ⇒ `revenue_actual = 12500000`
   (**bukan 0**); `GET /api/marketing/dashboard/overview` ⇒ **HTTP 200** (bukan 500);
   skor kesehatan **identik** dengan hasil entri manual bernilai sama.
2. `python3 scripts/gate_marketing_ssot.py` ⇒ **0 pelanggaran**.
3. `POST /api/marketing/import/sessions` ⇒ **404** (rute sudah tidak ada);
   `grep -rn "universal_import\\|routes.marketing_import" backend/ frontend/src/` ⇒ **0 hasil**;
   backend hidup (`/api/health` 200) dan frontend **compile tanpa galat** setelah 3 berkas UI dihapus.
4. `db.marketing_sales_data.countDocuments({metrics:{$exists:false}})` ⇒ **0**.
5. Indeks unik terpasang: menulis 2 rekap harian dengan `(account_id,date,revenue_type)` sama ⇒
   yang kedua **ditolak/di-upsert**, tidak menambah dokumen.
6. `GET /api/marketing/accounts` ⇒ **9 toko nyata** (+3 demo `closed`), semuanya punya
   `coa_revenue_code` yang benar-benar ada di `rahaza_coa_accounts`.

---

# FASE F1 — IMPOR PESANAN MARKETPLACE (Ekspor A) → JALUR OMZET RESMI

**Prasyarat:** F0 selesai. **Berkas uji:** `samples/TikTok_UntukDikirim_2026-07-19.xlsx`.

### F1.1 Kemampuan baru mesin impor — `backend/core/marketing_import_engine.py`
| Kemampuan | Fungsi | Aturan |
|---|---|---|
| Lewati baris deskripsi | `strip_description_rows(headers, rows, st) -> (rows, n_skipped)` | baris **pertama** dianggap deskripsi bila ≥60% selnya teks yang **tidak** lolos `parse_number`/`parse_date` pada kolom yang bertipe `money/int/date`, **dan** panjang teks > 15 karakter. Dipanggil di `POST /upload` **dan** `_reparse()` — satu tempat, dua pemakai |
| Kamus nilai | `Field.value_map: dict[str,str]` + `Field.keep_raw: bool` | pencocokan longgar (huruf kecil, tanpa spasi ganda). **Nilai tak dikenal ⇒ baris DITOLAK** dengan pesan yang memuat nilai aslinya. `keep_raw=True` ⇒ nilai asli disimpan di `<field>_raw` |
| Kelompok per pesanan | `SourceType.group_by: tuple` + `SourceType.item_fields: tuple` | `build_rows()` menghasilkan **1 dokumen per nilai `group_by`** dengan `items[]`; kolom di `item_fields` masuk `items[]`, sisanya ke header (nilai dari baris pertama pesanan; **beda nilai antar baris ⇒ warning**, bukan galat) |
| Sidik format | `format_fingerprint(headers) -> str` | sha1 dari daftar header yang dinormalkan. Disimpan di sesi **dan** di koleksi baru `marketing_data_import_formats` (`{source_type, fingerprint, headers[], mapping[], platform, created_by, use_count, last_used_at}`, unik `(source_type, fingerprint)`). Fingerprint dikenal ⇒ pemetaan langsung dipakai (K3, tanpa AI); fingerprint baru ⇒ wizard **minta konfirmasi**, tidak pernah menebak diam-diam |
| Uang per pesanan vs per baris | `SourceType.per_order_money: tuple` | field di daftar ini **hanya** dari baris pertama pesanan; dilarang dijumlah antar baris |

### F1.2 Jenis impor baru — `backend/core/marketing_import_schema.py`
`MARKETPLACE_ORDERS = SourceType(key="marketplace_orders", label="Pesanan Marketplace (ekspor Seller Center)", group="Penjualan", collection="marketing_orders", account_scope="required", dedupe=("account_id","platform","order_id"), group_by=("order_id",), module_hint="marketing-orders")`

**Pemetaan 65 kolom (ekspor TikTok) — tulis SEMUANYA, jangan sebagian:**

*Header — identitas/status/waktu*
| Kolom ekspor | Field kanonik | Tipe | Catatan |
|---|---|---|---|
| Order ID | `order_id` | str **wajib** | kunci |
| Order Status | `status` | enum `value_map` **wajib** | `Perlu dikirim→paid`, `Dikirim→shipped`, `Selesai→completed`, `Dibatalkan→cancelled`, `Pengembalian→returned`; `keep_raw` |
| Order Substatus | `substatus_raw` | str | |
| Cancelation/Return Type | `return_type_raw` | str | |
| Normal or Pre-order | `is_preorder` | bool `value_map` | `Pre-order→true`, `Normal→false` |
| Created Time | `order_date` | datetime **wajib** | `DD/MM/YYYY HH:MM:SS` sudah didukung |
| Paid Time | `paid_at` | datetime | |
| RTS Time | `rts_at` | datetime | |
| Shipped Time | `shipped_at` | datetime | |
| Delivered Time | `delivered_at` | datetime | |
| Cancelled Time | `cancelled_at` | datetime | |
| Cancel By / Cancel Reason | `cancel_by` / `cancel_reason` | str | |
| Fulfillment Type | `fulfillment_type` | str | |
| Warehouse Name | `warehouse_name_raw` | str | dibandingkan `account.platform_warehouse_name` ⇒ **warning** bila beda |
| Purchase Channel | `purchase_channel` | str **wajib** | dibandingkan `account.platform` ⇒ **TOLAK berkas** bila beda platform |
| Order Channel | `order_channel` | enum `value_map` | `LIVE→live`, `Videos→video`, `Product cards→product_card`, lain→`other`; `keep_raw` |
| Creator Handle | `creator_handle` | str | dasar atribusi kreator & komisi |
| Tracking ID | `tracking_number` | str | |
| Delivery Option | `delivery_option` | str | |
| Shipping Provider Name | `courier` | enum `value_map` + `keep_raw` | `J&T Express→jnt`, `JNE Express Standard ID→jne`, `SPX/Shopee Express→spx`, `SiCepat→sicepat`, `AnterAja→anteraja`, `Ninja→ninja`, `Grab→grab`, `GoSend→gojek`, kosong→`lainnya` |
| Package ID | `package_id` | str | |
| Weight(kg) | `weight_kg` | num | |
| Payment Method | `payment_method` | str | |
| Buyer Username / Recipient / Phone # | `buyer_username` / `customer_name` / `customer_phone` | str | |
| Zipcode / Country / Province / Regency and City / Districts / Villages | `zipcode`/`country`/`province`/`city`/`district`/`village` | str | |
| Detail Address / Additional address information | `address_detail` | str (gabung) | |
| Buyer Message / Seller Note | `buyer_message` / `seller_note` | str | |
| Checked Status / Checked Marked by / Tokopedia Invoice Number | `checked_status`/`checked_by`/`tokopedia_invoice_no` | str | disimpan, tidak dipakai logika |

*Header — uang (`per_order_money`, ditulis 1×)*
`Order Amount→order_amount` · `Shipping Fee After Discount→shipping_fee_after_discount` ·
`Original Shipping Fee→original_shipping_fee` · `Shipping Fee Seller Discount→shipping_fee_seller_discount` ·
`Shipping Fee Platform Discount→shipping_fee_platform_discount` · `Distance Shipping Fee→distance_shipping_fee` ·
`Distance Fee→distance_fee` · `Order Refund Amount→order_refund_amount` ·
`Payment platform discount→payment_platform_discount` · `Buyer Service Fee→buyer_service_fee` ·
`Handling Fee→handling_fee` · `Shipping Insurance→shipping_insurance` · `Item Insurance→item_insurance`

*`items[]` (`item_fields`)*
`SKU ID→platform_sku_id` **wajib** · `Seller SKU→seller_sku` · `Product Name→product_name_raw` ·
`Variation→variation_raw` · `Product Category→product_category_raw` · `Quantity→quantity` **wajib** ·
`Sku Quantity of return→qty_returned` · `SKU Unit Original Price→sku_unit_original_price` ·
`SKU Subtotal Before Discount→sku_subtotal_before_discount` · `SKU Platform Discount→sku_platform_discount` ·
`SKU Seller Discount→sku_seller_discount` · `SKU Subtotal After Discount→sku_subtotal_after_discount`

> **Kolom komisi platform TIDAK ADA di ekspor ini.** Karena itu `platform_fee=null` &
> `fee_known=false`, dan setiap layar yang menampilkan omzet impor **wajib** memberi label
> **"sebelum potongan platform"**. Angka bersih hanya datang dari F9.

### F1.3 Penyelesai dokumen — `routes/marketing_data_import.py::_finish` cabang `marketplace_orders`
1. `revenue_product = Σ items.sku_subtotal_after_discount`; `revenue_gross`, `seller_discount_total`,
   `platform_discount_total`, `quantity` = Σ items.
2. `revenue = revenue_product` **dan** `total_payment = order_amount` (kompatibilitas pembaca lama).
3. `is_preorder` header = `true` bila **ada** item pre-order.
4. Tautan master per item, **urutan**: `platform_sku_ids[]` → `sku` sama → nama produk sama →
   `unlinked` (warning, **bukan** tolak — pesanan tetap masuk supaya omzet tidak hilang).
5. `hpp_snapshot` per item dari katalog (untuk marjin F5/F7).
6. `creator_id` dari `marketing_kol_creators.platforms.tiktok == creator_handle` (bila ada).
7. `fulfillment_status='unallocated'`, `stock_reserved=false` (K17: impor tidak memesan stok).
8. Panggil `rollup.recompute_daily()` (F2) untuk setiap tanggal terdampak — **setelah** commit.

### F1.4 Layar pemetaan SKU platform (83 SKU → item katalog)
**Endpoint baru** (di `routes/marketing_data_import.py`):
- `GET /api/marketing/data-import/sessions/{id}/sku-map` ⇒ daftar `platform_sku_id` belum
  terpetakan + `product_name_raw`, `variation_raw`, jumlah baris, jumlah pcs, **usulan** item
  katalog (kemiripan nama ≥0.7), dikelompokkan per **nama produk induk** (8 grup pada berkas nyata)
- `POST /api/marketing/data-import/sessions/{id}/sku-map` body `[{platform_sku_id, catalog_item_id}]`
  ⇒ menulis `platform_sku_ids[]` pada `marketing_catalog_items` (SSOT §4.3) + hitung ulang pratinjau
**UI:** langkah baru di `frontend/src/components/erp/marketing/DataImportWizard.jsx`
("Pemetaan SKU") — **tabel** (bukan kartu), aksi massal per grup produk induk,
tombol "Buat item katalog baru dari SKU ini" (memakai endpoint katalog yang sudah ada).

### F1.5 Perbaiki pembaca yang salah (D05)
`backend/routes/marketing_sales_performance_routes.py:64-88`:
- filter memakai **`account_id`** (hapus terjemahan ke `account_name`; simpan `account_name`
  hanya untuk kompatibilitas kueri lama lewat `$or`)
- `total_revenue` = `$sum:'$revenue_product'` (atau `revenue_order_amount` sesuai `revenue_basis`)
- `total_orders` = jumlah **dokumen** (1 dokumen = 1 pesanan)
- `total_items` = `$sum:'$quantity'`
- pecahan per SKU memakai `$unwind:'$items'`

### BUKTI SELESAI F1 (angka wajib sama)
Impor berkas nyata sebagai `marketplace_orders`, toko **TikTok Outfit Boutique**:
| Metrik | Nilai wajib |
|---|---|
| baris terbaca | **601** (baris deskripsi dilewati, tidak dihitung data) |
| pesanan masuk | **559** · item masuk **601** · **ditolak 0** |
| Σ `revenue_product` | **Rp 59.783.811** |
| Σ `order_amount` | **Rp 62.805.113** |
| Σ `seller_discount_total` | **Rp 48.020.983** |
| Σ `revenue_gross` | **Rp 109.179.000** |
| Σ `quantity` | **603 pcs** |
| pecahan `order_channel` | live **Rp 42.364.407** (389 pesanan) · video **Rp 9.590.333** (96) · product_card **Rp 7.829.071** (78) |
| kreator teratas | `iori.oliviara` **Rp 26.942.611** · `vivin.ir1994` **Rp 10.936.791** · tanpa kreator **Rp 7.979.170** |
| pre-order | **514 baris item** `is_preorder=true` |
| impor ulang berkas sama | **0 dokumen tambahan** |
| rollback sesi | `marketing_orders` untuk sesi itu **0** |
| `GET /api/marketing/performance/overview` | `total_revenue = 59.783.811` (**bukan** 73.377.237), `total_orders = 559` |
| impor ke toko **Shopee** dengan berkas TikTok | **ditolak** dengan pesan "Purchase Channel TikTok ≠ platform toko (shopee)" |

---

# FASE F2 — REKAP HARIAN TURUNAN (menutup dua-dunia omzet)

### F2.1 `backend/core/marketing_daily_rollup.py` (baru)
```python
async def recompute_daily(db, account_id: str, date: str) -> dict     # 1 tanggal, idempoten
async def recompute_range(db, account_id: str, d_from: str, d_to: str) -> dict
async def recompute_for_orders(db, order_ids: list[str]) -> dict      # cari tanggal terdampak
```
Aturan (mengikuti pola terbukti `marketing_live_sales_sync.sync_live_sales_to_marketing`):
- sumber: `marketing_orders` dengan `account_id`, `order_date` dalam hari itu (zona waktu Asia/Jakarta),
  `status ∉ {cancelled}` untuk omzet; pesanan `cancelled`/`returned` masuk grup `fulfillment.*`
- hasil: upsert `(account_id, date, revenue_type='total')` lewat `build_daily_doc(source='orders_auto')`
- isi `metrics.*` (revenue_product/order_amount/gross/discount/orders/units/buyers/aov) +
  `traffic.*` dari `order_channel` + `fulfillment.cancelled_*`/`returned_*`
- `buyers` = jumlah `buyer_username` unik hari itu
- **tidak** menyentuh grup `funnel`, `buyers_mix`, `customer_satisfaction`, `live_metrics`,
  `content_metrics` (itu milik F8/F7) — gunakan `$set` per-field, **bukan** ganti dokumen
- bila tidak ada pesanan **dan** dokumen sebelumnya `source='orders_auto'` ⇒ hapus dokumen
  (supaya angka tidak "nyangkut" setelah rollback)

### F2.2 Pemanggil (hook)
| Tempat | Kapan |
|---|---|
| `routes/marketing_data_import.py::commit` | setelah commit `marketplace_orders` / `marketplace_fulfillment` |
| `routes/marketing_data_import.py::rollback` | setelah menghapus dokumen |
| `core/order_status.py` (ubah status/batal) | setelah status berubah |
| `routes/marketing_orders_routes.py` (create/update/delete manual) | setelah tulis |
| `routes/fulfillment.py` | saat kirim/selesai |

### F2.3 Kunci entri manual
`routes/marketing_sales.py` (POST/PUT): bila dokumen sasaran `source='orders_auto'` ⇒ **409**
"Angka hari ini diturunkan dari pesanan toko ini. Untuk mengubahnya, perbaiki pesanannya
(atau minta SPV membuka kunci sumber)." Field non-`metrics` (mis. `customer_satisfaction`)
**tetap boleh** diisi manual.

### F2.4 Alat & UI
- `POST /api/marketing/sales/recompute?account_id&date_from&date_to` (role `spv_marketing`/`owner`)
- `frontend/src/components/erp/SalesDataEntryModule.jsx`: badge sumber per baris
  (`Turunan dari pesanan` / `Manual` / `Live otomatis`), tombol **"Hitung Ulang"**,
  baris turunan tampil **baca-saja**, + **pengalih Tabel/Kartu** (B1)

### BUKTI SELESAI F2
1. Setelah impor F1 (tanggal 16–19 Juli 2026): `marketing_sales_data` berisi dokumen
   `source='orders_auto'` untuk tiap tanggal; **Σ `metrics.revenue_product` bulan Juli 2026 = Rp 59.783.811**.
2. `GET /api/marketing/targets/monthly-summary?year=2026&month=7` ⇒ `revenue_actual = 59.783.811`
   (basis produk) — **angka yang sama** dengan `GET /api/marketing/performance/overview` dan
   dengan `GET /api/marketing/budget/summary` (`sales`).
3. `GET /api/marketing/dashboard/overview` ⇒ **200**, `total_revenue` sama.
4. Hapus 1 pesanan bernilai X ⇒ rekap harian tanggal itu turun **tepat X**; hapus semua ⇒ dokumen hilang.
5. `POST /api/marketing/sales` untuk tanggal turunan ⇒ **409** dengan pesan yang benar.
6. Jalankan `recompute_range` 3× ⇒ angka **tidak berubah** (idempoten).

---

# FASE F3 — IMPOR FULFILLMENT (Ekspor B & C) + MONITORING PEKERJAAN

**Prasyarat:** F1, F2. **BLOKIR-DATA:** BD-1 (bila belum ada, kerjakan dengan asumsi kolom
identik Ekspor A dan **tandai di kode + UI** bahwa pemetaan menunggu verifikasi berkas nyata).

### F3.1 Jenis impor `marketplace_fulfillment`
- `collection='marketing_orders'`, **mode `update_only`** (baru): baris yang `order_id`-nya tidak
  ada ⇒ **ditolak** dengan pesan "pesanan belum pernah diimpor (impor Ekspor A dulu)";
  **tidak pernah** membuat pesanan baru dari Ekspor B/C.
- field yang diperbarui: `status`, `substatus_raw`, `shipped_at`, `delivered_at`, `cancelled_at`,
  `cancel_by`, `cancel_reason`, `return_type_raw`, `order_refund_amount`, `tracking_number`,
  `courier`, `items[].qty_returned`
- transisi status dijaga `core/order_status.py`: dilarang mundur (`completed → paid`) kecuali
  ada `cancelled_at`/`return_type_raw` (kasus batal setelah selesai) ⇒ dicatat di `status_history[]`

### F3.2 Monitoring — **memperluas modul yang ada**
`frontend/src/components/erp/marketing/UnifiedOrdersDashboard.jsx` (jangan buat modul baru):
- tabel utama **kolom penuh** (D19 saat ini 3 kolom → menjadi):
  `order_id · tanggal · toko · channel · kreator · items(n) · qty · omzet produk · order amount ·
   diskon penjual · status · umur hari · kurir · resi · kota · pre-order`
- tab/filter baru: **"Belum dikirim > N hari"** (N dari pengaturan, default 2) ·
  **"Bocor"** (ada di Ekspor A, belum pernah muncul di B) · **"Batal setelah resi terbit"** ·
  **"Retur"**
- pengalih Tabel/Kartu (B1); ekspor CSV; aksi massal "tandai sudah dikirim" (manual, dengan alasan)
**Endpoint:** `GET /api/marketing/orders/monitoring?account_id&kind=unshipped|leak|cancel_after_awb|return&days=N`
(di `routes/marketing_orders_routes.py`, memakai agregasi + `visible_account_ids`).

### BUKTI SELESAI F3
1. Impor Ekspor B ⇒ n pesanan berubah `paid→shipped` dengan `shipped_at` terisi; **0** pesanan baru dibuat.
2. Baris dengan `order_id` tak dikenal ⇒ ditolak dengan pesan yang benar (bukan membuat pesanan).
3. `GET .../monitoring?kind=unshipped&days=2` ⇒ daftar dengan kolom `umur_hari` benar
   (dihitung dari `order_date`, bukan `created_at`).
4. `kind=leak` ⇒ pesanan Ekspor A yang tidak ada di B muncul; setelah B diimpor ⇒ hilang dari daftar.
5. Rollback impor B ⇒ status kembali ke keadaan sebelumnya (dari `status_history[]`).
6. Rekap harian ikut diperbarui (`fulfillment.cancelled_orders/value` berubah).

---

# FASE F4 — KATALOG: STATUS AKURAT · FOTO · SATU LAYAR · KOLOM PENUH

**Prasyarat:** F0. (Tidak menunggu F1, kecuali pemetaan `platform_sku_ids[]` yang datang dari F1.)

### F4.1 `backend/core/catalog_status.py` (baru) — satu rumus status
```python
CATALOG_STATUSES = ('DRAFT','PRE_ORDER','ACTIVE','HABIS','NONAKTIF','DITOLAK')
def compute(item: dict, available: float | None) -> tuple[str, str]   # (status, alasan)
```
Urutan keputusan = tabel SSOT §4.1. **Dilarang** menyimpan `catalog_status` sebagai nilai yang
diketik; ia dihitung saat dibaca **dan** disimpan sebagai cache (`catalog_status`,
`catalog_status_reason`, `catalog_status_at`) untuk keperluan filter/indeks.

### F4.2 Transisi penayangan (K8)
Endpoint baru di `routes/marketing_catalog_items.py`:
- `POST /{catalog_id}/items/{item_id}/publish` body `{platform_url}` ⇒ `publish_state='published'`,
  `published_at`, wajib `platform_url` (validasi http/https) — **400** bila kosong
- `POST /{catalog_id}/items/{item_id}/unpublish` body `{reason}` ⇒ `draft`
- `POST /{catalog_id}/items/{item_id}/reject` body `{reason}` ⇒ `rejected` + `rejected_reason`
- `POST /{catalog_id}/items/{item_id}/preorder` body `{is_preorder: bool, note}`
- `POST /{catalog_id}/items/{item_id}/archive`
Semua mencatat ke `marketing_change_log` (F6; sebelum F6 ⇒ tulis `updated_by/at` + `status_history[]`).

### F4.3 Foto master ikut terbawa (D13)
- `backend/core/product_master.py`: fungsi baru `master_images(model: dict) -> list[dict]`
  membaca `rahaza_models.image_paths` (dan `reference_images`) → `[{url, caption, from}]`
- `routes/marketing_catalog_items.py`:
  - `POST /{catalog_id}/items/from-fg` ⇒ tambahkan `doc['master_images'] = master_images(model)`
  - `POST /{catalog_id}/refresh-from-master` & `.../items/{id}/refresh-from-master` ⇒ segarkan `master_images`
  - `GET /{catalog_id}/items` ⇒ setiap baris menyertakan `primary_image`
    (= `images[0]` bila ada, jika tidak `master_images[0].url`) + `image_count`
- **Migrasi** `backend/migrations/2026_08_12_catalog_master_images.py`: isi `master_images` untuk
  item lama yang punya `model_id` (dry-run dulu).
- Marketing tetap memakai endpoint unggah yang **sudah ada** (`.../photos`, `.../photos/remove`).
  **Tambahan:** `POST .../photos/reorder` body `{urls:[...]}` supaya foto utama bisa dipilih.

### F4.4 Satu layar katalog, dua tampilan (K10, D14, D19)
- **Modul yang dipakai:** `frontend/src/components/erp/CatalogManagementModule.jsx` (1.817 baris,
  sudah tabel) — **ditingkatkan**, bukan diganti.
- **`toko-products`** di `components/erp/moduleRegistry.js:1080` ⇒ `makeRedirect('marketing-catalog')`
  (pola redirect sudah ada). `TokoProductCatalogModule.jsx` **tidak dihapus** dulu; ia menjadi
  sumber komponen **grid kartu + galeri foto** yang dipindahkan ke modul katalog
  (`CatalogGridView.jsx`, `CatalogPhotoManager.jsx` di folder yang sama) lalu berkasnya
  dihapus di F10 setelah verifikasi.
- **Kolom tabel wajib (default tampil):**
  `foto(thumb) · SKU · nama · varian · kategori(master) · STATUS(badge) · publish_state ·
   harga jual · harga coret · harga resmi master(Δ) · HPP + sumber · marjin Rp · marjin % ·
   stok jual(live) · reserved · in_sync · tautan master(FG/varian) · platform_url · terakhir sinkron`
  **kolom opsional:** `harga original · berat · tags · threshold · fg_onhand · fg_excluded ·
  jumlah foto · dibuat oleh · diperbarui`
- **Filter:** toko (wajib), status katalog (multi), `attention` (belum tertaut / stok basi),
  kategori master, rentang harga/marjin, punya foto / tanpa foto.
- **Aksi massal:** publish (isi URL satu per satu), tandai pre-order, sinkron stok FG,
  refresh dari master, arsipkan, ekspor CSV.
- **Kartu/Grid:** thumbnail besar, badge status, harga, stok, tombol foto.

### F4.5 Endpoint daftar diperluas
`GET /{catalog_id}/items` tambah query: `catalog_status` (multi, koma), `publish_state`,
`has_photo` (`true|false`), `sort` (`name|price|margin|stock|status|updated`), `order`.
Ringkasan `stock_summary` ditambah `by_status: {DRAFT:n, PRE_ORDER:n, ACTIVE:n, HABIS:n, NONAKTIF:n, DITOLAK:n}`
dihitung untuk **seluruh** katalog (bukan halaman aktif).

### BUKTI SELESAI F4
1. Item tanpa `platform_url` & `publish_state='draft'` ⇒ `catalog_status='DRAFT'`;
   set `is_preorder=true` + publish ⇒ `PRE_ORDER`; stok jual 10 + publish ⇒ `ACTIVE`;
   stok 0 + publish ⇒ `HABIS`; `reject` ⇒ `DITOLAK`; `archive` ⇒ `NONAKTIF`. **6/6 benar.**
2. `POST .../publish` tanpa `platform_url` ⇒ **400**.
3. Buat item dari FG yang model-nya punya foto RnD ⇒ `master_images` **≥1** tanpa upload manual;
   unggah foto marketplace ⇒ `images` bertambah, `primary_image` berubah ke foto marketplace.
4. `GET /api/marketing/catalogs/{id}/items` ⇒ setiap baris punya `primary_image`, `catalog_status`,
   `hpp`, `hpp_source`, `margin_pct`, `available`, `in_sync`.
5. Buka `marketing-catalog` ⇒ tabel **≥19 kolom** default, pengalih Tabel/Kartu bekerja,
   pilihan tampilan bertahan setelah reload. Buka `toko-products` ⇒ diarahkan ke `marketing-catalog`.
6. `stock_summary.by_status` menjumlah = total item katalog (tidak hanya halaman aktif).

---

# FASE F5 — SATU LAYAR SIKLUS + REALISASI OTOMATIS + PERINGATAN

**Prasyarat:** F2 (omzet turunan), F4 (HPP/marjin katalog).

### F5.1 Endpoint siklus (baru, 1 permintaan = semua angka)
`GET /api/marketing/cycle/summary?account_id=&period=YYYY-MM` (di `routes/marketing_budget.py`,
**bukan** berkas baru — supaya anggaran berhenti jadi pulau):
```json
{ "account": {...}, "period": "2026-07", "locked": false, "revenue_basis": "produk_setelah_diskon",
  "target": {"revenue": 0, "orders": 0, "units": 0, "aov": 0, "health_score": 80, "basis": "..."},
  "actual": {"revenue_product": 59783811, "revenue_order_amount": 62805113, "orders": 559,
             "units": 603, "buyers": 0, "aov": 106948, "gross_before_discount": 109179000,
             "seller_discount": 48020983},
  "achievement": {"revenue_pct": 0, "orders_pct": 0, "pace_pct": 0, "days_elapsed": 0, "days_total": 31},
  "budget": {"plan": {...6 kategori...}, "actual": {...}, "variance": {...}, "total_plan": 0, "total_spend": 0},
  "spend_sources": [{"category":"diskon","amount":48020983,"source":"auto","evidence":"559 pesanan"}],
  "margin": {"revenue": 0, "hpp": 0, "gross_profit": 0, "gross_margin_pct": 0, "hpp_coverage_pct": 0},
  "roi": {"spend": 0, "gross_profit": 0, "roi_pct": 0, "roas": 0},
  "flags": ["target_behind", "budget_warning"], "label": "Angka omzet SEBELUM potongan platform" }
```
`margin.hpp` = Σ `items.quantity × items.hpp_snapshot`; `hpp_coverage_pct` = % item yang punya HPP>0
(**wajib ditampilkan** — marjin tanpa cakupan HPP adalah angka yang menipu).

### F5.2 Realisasi anggaran otomatis (D08/D09)
Di `routes/marketing_budget.py` — tambah fungsi `_auto_spend(db, account_id, period)`:
| Kategori | Rumus |
|---|---|
| `diskon` | Σ `marketing_orders.seller_discount_total` + Σ `shipping_fee_seller_discount` (bulan, toko, status ≠ cancelled) |
| `ads` | Σ `marketing_ads_data.spend` (bulan, toko) |
| `komisi` | Σ komisi kreator dari `marketing_orders` per `creator_id` × konfigurasi biaya (`/budget/kol-cost`) |
| `livehost`, `kol` | tetap seperti sekarang (`_livehost_auto_spend`, `_kol_auto_spend`) |
| `sample` | manual (`marketing_spend_entries`) |
Setiap angka otomatis dilaporkan dengan `source:'auto'` + `evidence` (jumlah dokumen sumber).
**Tidak menulis** `marketing_spend_entries` (anti-dobel). `CATEGORIES` ditambah `'komisi'`
+ migrasi dokumen anggaran lama (isi `komisi: 0`).

### F5.3 Kunci periode (K16) — `marketing_period_locks`
- `GET/POST /api/marketing/periods/lock` `{account_id, period, action: close|reopen, reason}`
- penjaga di: `POST /api/marketing/targets`, `POST /api/marketing/targets/creator`,
  `PUT /api/marketing/budget`, `POST /api/marketing/budget/spend`,
  `POST/PUT /api/marketing/sales`, commit impor yang menyentuh tanggal terkunci ⇒ **HTTP 423**
- pembuka: `owner`, `spv_marketing` (F6). Semua aksi kunci/buka masuk `marketing_change_log`.

### F5.4 Peringatan (2 jenis baru)
`routes/marketing_alerts.py::evaluate_marketing_alerts` + `marketing_alert_settings`:
- `target_behind`: `pace_pct - revenue_pct > threshold` (default 15) ⇒ kuning; >30 ⇒ merah
- `budget_overrun`: `total_spend/total_plan ≥ 0.8` ⇒ kuning; `≥ 1.0` ⇒ merah (per kategori juga)
Muncul di lonceng notifikasi + kartu ringkasan; ambang bisa diubah di
`frontend/src/components/erp/RahazaAlertSettingsModule.jsx` (modul yang sudah ada).

### F5.5 UI (K5 — dua portal, satu komponen)
- **Tingkatkan** `frontend/src/components/erp/marketing/AccountTargetsModule.jsx` menjadi
  layar siklus: baris atas KPI (target, omzet 2 angka, anggaran, terpakai, marjin, sisa hari),
  lalu **tabel** semua toko × bulan (kolom: toko, target, omzet produk, omzet order amount,
  capaian %, pace %, anggaran, terpakai, sisa, marjin %, status kunci, flag) + pengalih Tabel/Kartu.
- `moduleRegistry.js`: tambah id **`mgmt-marketing-cycle`** yang me-render **komponen yang sama**
  (dengan prop `scope='management'` ⇒ semua toko, boleh set target/anggaran).
  `marketing-targets` tetap ada (prop `scope='marketing'`).
- `BudgetModule.jsx` (sudah punya pengalih) ⇒ tambah kolom realisasi otomatis + kolom `komisi`
  + tanda `auto`/`manual` per kategori + tautan bukti.

### BUKTI SELESAI F5
1. `GET /api/marketing/cycle/summary?account_id=<Outfit>&period=2026-07` ⇒ **satu** permintaan
   mengembalikan: `actual.revenue_product=59.783.811`, `actual.orders=559`,
   `spend_sources` memuat `{category:'diskon', amount:48.020.983, source:'auto'}`.
2. `budget/summary` kategori `diskon` **tidak 0** untuk bulan yang punya pesanan impor,
   tanpa satu pun entri manual.
3. Tutup periode 2026-07 ⇒ `POST /api/marketing/targets` untuk bulan itu ⇒ **423**;
   sebagai `spv_marketing` buka kunci ⇒ **200**; kedua aksi tercatat di `marketing_change_log`.
4. Target 100 jt & omzet 59,78 jt di hari ke-25 ⇒ flag `target_behind` muncul (pace 80,6% vs 59,8%).
5. Anggaran 40 jt & terpakai 48 jt ⇒ flag `budget_overrun` **merah**.
6. `mgmt-marketing-cycle` dan `marketing-targets` menampilkan **angka identik**.
7. `margin.hpp_coverage_pct` tampil; bila 0% layar menulis "marjin belum bisa dipercaya:
   0% item punya HPP".

---

# FASE F6 — RBAC PER TOKO + JEJAK PERUBAHAN

### F6.1 Role & izin
`backend/auth.py::_seed_default_roles` — tambah (idempoten):
`spv_marketing` (SPV Marketing — semua toko) · `staff_marketing` (Staff Marketing — toko yang di-assign) ·
`content_creator` (Content Creator — semua toko, modul konten) · `host_live` (Host Live — toko yang di-assign).
`pic_toko` **dipertahankan** sebagai alias `staff_marketing` (jangan hapus: 5 akun seed memakainya).
Kunci izin baru (dipakai `require_perm`): `marketing.target.set`, `marketing.budget.set`,
`marketing.period.close`, `marketing.period.reopen`, `marketing.import.commit`,
`marketing.catalog.publish`, `marketing.order.write`, `marketing.content.write`,
`marketing.report.view_all`, `marketing.settlement.import`.

### F6.2 Lingkup toko ditegakkan (D11)
`backend/core/marketing_account_scope.py` — tambah:
```python
async def visible_account_ids(db, user: dict) -> list[str] | None   # None = semua toko
async def assert_account_visible(db, user: dict, account_id: str) -> None   # 403 bila bukan haknya
```
Aturan: `owner`/`admin`/`superadmin`/`spv_marketing`/`content_creator` ⇒ `None` (semua);
`staff_marketing`/`pic_toko`/`host_live` ⇒ toko dengan `pic_id == user.id` **atau**
`user.id ∈ assigned_staff`. Bila hasilnya kosong ⇒ daftar kosong + pesan
"Belum ada toko yang di-assign ke Anda. Minta SPV Marketing meng-assign di Manajemen Akun."
**Pasang di semua endpoint daftar/ringkas** (minimal 30; daftar tepatnya dihasilkan
`grep -rn "account_id: *Optional\\[str\\] *= *Query" backend/routes/marketing_*.py`).

### F6.3 Matriks hak (ditulis di kode & di layar)
| Aksi | owner | spv_marketing | staff_marketing/pic_toko | content_creator | host_live | accounting |
|---|---|---|---|---|---|---|
| Lihat semua toko | ✔ | ✔ | ✖ (hanya assign) | ✔ | ✖ | ✔ (laporan) |
| Set target/anggaran | ✔ | ✔ | ✖ | ✖ | ✖ | ✖ |
| Tutup/buka periode | ✔ | ✔ | ✖ | ✖ | ✖ | ✖ |
| Commit impor | ✔ | ✔ | ✔ (toko sendiri) | ✖ | ✖ | ✖ |
| Publish katalog | ✔ | ✔ | ✔ (toko sendiri) | ✖ | ✖ | ✖ |
| Tulis konten & KPI konten | ✔ | ✔ | ✔ (toko sendiri) | ✔ (semua) | ✖ | ✖ |
| Impor settlement | ✔ | ✔ | ✖ | ✖ | ✖ | ✔ |
| Approve jurnal settlement | ✔ | ✖ | ✖ | ✖ | ✖ | ✔ |

### F6.4 Jejak perubahan — `marketing_change_log`
Helper `backend/core/marketing_audit.py::log_change(db, entity, entity_id, changes, user, reason=None)`
dipanggil di: target, anggaran, spend, rekap manual, publish/unpublish katalog, kunci periode,
impor commit/rollback, settlement. UI: drawer riwayat di layar siklus & katalog
(pakai `components/erp/AuditHistoryDrawer.jsx` **yang sudah ada**).

### BUKTI SELESAI F6
1. Login `staff_marketing` yang di-assign 1 toko ⇒ `GET /api/marketing/accounts` ⇒ **1 toko**;
   `GET /api/marketing/orders?account_id=<toko lain>` ⇒ **403**.
2. `POST /api/marketing/targets` sebagai `staff_marketing` ⇒ **403**; sebagai `spv_marketing` ⇒ **200**.
3. Ubah target ⇒ `marketing_change_log` berisi `old_value`/`new_value`/`actor_role`;
   drawer riwayat menampilkannya.
4. `content_creator` ⇒ bisa menulis KPI konten di semua toko, **tidak** bisa set target (**403**).
5. Semua endpoint daftar marketing (hasil grep) menerapkan `visible_account_ids`
   — dibuktikan skrip `scripts/gate_marketing_scope.py` (0 endpoint terlewat).

---

# FASE F7 — KONTEN & CONTENT CREATOR (KPI + LINK TERBIT)

### F7.1 Perluasan field (SSOT §7)
`backend/routes/marketing_content_calendar_routes.py`: `ContentEntryIn`/`Update` + penulis
ditambah: `creator_id`, `assignee_user_id`, `catalog_item_id`/`sku`, `brief`, `hook`,
`published_url`, `published_at`, `platform_post_id`, `kpi{}`, `kpi_updated_at`, `kpi_source`.
Aturan: `status='posted'` ⇒ `published_url` **wajib** (400 bila kosong);
`creator_id` divalidasi ada di `marketing_kol_creators` **dan** ter-assign ke toko itu
(`scope.assert_creator_assigned`, sudah ada).

### F7.2 Jenis impor `content_performance`
Kolom: `published_url` (atau `date`+`title`), `views`, `likes`, `comments`, `shares`, `saves`,
`watch_time_avg_sec`, `ctr`, `orders`, `gmv`, `gpm`. Sinonim Indonesia+Inggris
(`tayangan/views`, `suka/likes`, `disimpan/saves`, `durasi tonton`, `penjualan/gmv`).
Mode **`update_or_insert`**: bila `published_url` cocok ⇒ perbarui KPI; bila tidak ⇒ buat entri
`status='posted'` (konten yang terbit tanpa direncanakan — nyata terjadi).

### F7.3 Endpoint KPI & laporan kreator
- `POST /api/marketing/content/{id}/kpi` (manual, satu entri)
- `GET /api/marketing/content/performance?account_id&creator_id&date_from&date_to&group_by=creator|content_type|account`
  ⇒ per kreator: jumlah konten, views, engagement (`likes+comments+shares`), engagement rate,
  saves, CTR rata-rata, orders, GMV, GMV/konten, GPM
- `GET /api/marketing/content/creator-scorecard?creator_id&period` ⇒ konten vs target
  (`marketing_creator_targets.content_target`) + omzet kreator dari `marketing_orders.creator_id` (F1)

### F7.4 UI (enhance, bukan baru)
- `frontend/src/components/erp/marketing/ContentCalendarModule.jsx`:
  **Tabel default** (kolom: tanggal · toko · jenis · judul · kreator · SKU · status ·
  link terbit · views · likes · comments · shares · saves · CTR · order · GMV · diperbarui)
  + **pengalih Tabel/Kalender/Kartu**; tombol "Isi KPI"; validasi link terbit;
  filter kreator/jenis/status/rentang tanggal.
- `frontend/src/components/erp/marketing/KOLLeaderboardModule.jsx` (kartu-saja → tabel + kartu):
  tambah kolom konten & KPI konten, GMV dari pesanan (F1), komisi (F5).
- `frontend/src/components/erp/KOLCreatorModule.jsx` (tabel 2 kolom → kolom penuh):
  `nama · kode · username per platform · toko ter-assign · konten 30h · views 30h · GMV 30h ·
   komisi · sample terkirim · status`.

### BUKTI SELESAI F7
1. `status='posted'` tanpa `published_url` ⇒ **400**.
2. Impor `content_performance` 10 baris (5 URL sudah ada, 5 baru) ⇒ 5 diperbarui + 5 dibuat;
   jalan 2× ⇒ tidak ada tambahan.
3. `GET /api/marketing/content/performance?group_by=creator` ⇒ angka per kreator; total views
   = Σ baris impor (dibuktikan hitung tangan).
4. `creator-scorecard` menampilkan GMV kreator dari pesanan F1
   (mis. `iori.oliviara` = **Rp 26.942.611** bila `creator_handle` sudah dipetakan ke `creator_id`).
5. `ContentCalendarModule` punya ≥16 kolom + pengalih tampilan; `KOLCreatorModule` ≥10 kolom.

---

# FASE F8 — KPI TOKO + LAPORAN HARIAN/MINGGUAN/BULANAN

**Prasyarat:** F2. **BLOKIR-DATA:** BD-3 (jalur impor); jalur form **tidak** diblokir (K13).

### F8.1 KPI masuk lewat DUA jalur (K13)
**(a) Jenis impor `shop_kpi`** — koleksi `marketing_sales_data`, kunci
`(account_id, date, revenue_type='total')`, **hanya** mengisi grup `funnel`, `buyers_mix`,
`traffic`, `customer_satisfaction`, `live_metrics`, `content_metrics` (+ `metrics.buyers`,
`metrics.units`) dan **tidak pernah** menimpa `metrics.revenue*`/`orders` bila
`source='orders_auto'`. `kpi_source='import'`.
Kolom (prioritas-1 owner): `date`, `uv`, `pv`, `product_clicks`, `ctr`, `conversion_rate`,
`atc_visitors`, `atc_units`, `cart_to_order_cr`, `order_to_paid_cr`, `buyers`, `new_buyers`,
`returning_buyers`, `sales_new`, `sales_returning`, `units_ordered`, `units_paid`,
`sales_live`, `sales_video`, `sales_ads`, `sales_affiliate`, `sales_campaign`, `sales_organic`,
`cancelled_orders`, `cancelled_value`, `returned_orders`, `returned_value`,
`unique_viewers`, `peak_viewers`, `watch_time_avg_sec`, `new_followers`,
`video_views`, `video_completion_rate`, `saves`, `shop_performance_score`, `processing_hours`.
**(b) Form input mingguan** — tab baru **"KPI Mingguan"** di
`frontend/src/components/erp/SalesDataEntryModule.jsx`: pilih toko + minggu (ISO), isi angka
yang sama; disimpan **tersebar rata ke 7 tanggal** *atau* sebagai 1 dokumen mingguan?
⇒ **Keputusan teknis:** disimpan pada tanggal **hari terakhir minggu** dengan
`kpi_period='weekly'` + `kpi_week='2026-W29'`; agregator laporan menjumlahkan `kpi_period='daily'`
dan mengambil `weekly` **apa adanya** (tidak dijumlah dengan harian) — mencegah dobel hitung.

### F8.2 Laporan (K12) — `backend/routes/marketing_reports.py`
- `GET /api/marketing/reports/weekly?year=&week=&account_id=&all_accounts=` (**baru**)
- `GET /api/marketing/reports/monthly` (**diperluas**), `/daily` (**diperluas**)
- ketiganya mengembalikan blok yang sama sehingga UI cukup satu komponen:
  `periode`, `toko`, `penjualan{omzet produk, order amount, target, capaian%, MoM/WoW%}`,
  `pesanan{jumlah, unit, pembeli, AOV}`, `funnel{UV,PV,klik,CTR,CR,ATC,cart→order,order→paid}`,
  `pembeli{baru,lama,omzet masing-masing}`, `sumber_trafik{live,video,ads,afiliasi,kampanye,organik}`,
  `kehilangan{batal:n/Rp, retur:n/Rp}`, `live{penonton unik,PCU,durasi,engagement,sesi}`,
  `konten{jumlah,views,CTR,GMV,GPM}`, `anggaran{rencana,terpakai,ROI}`, `marjin{HPP,laba kotor,%}`,
  `kesehatan{skor,LSR,cancel,respon}`, `catatan_kualitas_data[]`
- **`catatan_kualitas_data`** wajib: menyebut angka yang **belum ada sumbernya**
  (mis. "UV/PV belum diimpor untuk 3 dari 7 hari") — supaya rapat tidak memakai nol sebagai fakta.
- Ekspor: `GET .../weekly/export-pdf`, `.../monthly/export-pdf` (generator PDF sudah ada),
  `.../weekly/export-xlsx`, `.../monthly/export-xlsx` (**baru**, `openpyxl`).

### F8.3 UI
`frontend/src/components/erp/marketing/MonthlyReportModule.jsx` dan `DailyReportModule.jsx`
(kartu-saja) **digabung perilakunya**: satu komponen laporan dengan **pengalih periode
Harian/Mingguan/Bulanan** + pemilih toko/semua toko + **tabel** rincian + kartu KPI di atas +
tombol PDF/Excel. `moduleRegistry` id `marketing-daily-report` & `marketing-monthly-report`
tetap ada (deep-link) tetapi me-render komponen yang sama dengan prop periode awal.

### BUKTI SELESAI F8
1. `GET /api/marketing/reports/weekly?year=2026&week=29&account_id=<Outfit>` ⇒ omzet produk minggu
   yang memuat 16–19 Juli 2026 = **Rp 59.783.811**; `sumber_trafik.live = Rp 42.364.407`.
2. Impor `shop_kpi` 7 baris ⇒ `funnel.uv` terisi, `metrics.revenue_product` **tidak berubah**.
3. Form KPI mingguan ⇒ 1 dokumen `kpi_period='weekly'`; laporan **tidak** menghitung dobel
   (dibuktikan: total sebelum = total sesudah + nilai weekly, tidak 2×).
4. PDF & Excel mingguan/bulanan terunduh, isi angkanya sama dengan JSON.
5. `catatan_kualitas_data` menyebut hari tanpa data KPI.

---

# FASE F9 — SETTLEMENT (PENCAIRAN) → FINANCE (DRAFT JURNAL)

**BLOKIR-DATA WAJIB:** BD-2. **Dilarang menebak kolom laporan pencairan.**

### F9.1 Jenis impor `marketplace_settlement` → `marketing_settlements` (SSOT §8)
Kolom minimum: `settlement_id`, `settlement_date`, `period_from/to`, `gross_sales`, `refunds`,
`seller_discount`, `shipping_subsidy`, `platform_commission`, `platform_service_fee`,
`affiliate_commission`, `ads_deduction`, `other_deductions`, `adjustments`, `net_payout`.
Dedupe `(platform, account_id, settlement_id)`. Semua baris asli disimpan di `raw{}`.

### F9.2 Profil posting + jurnal DRAFT (K4)
- Tambah dokumen `rahaza_posting_profiles` `event_type='marketplace_settlement'` dengan
  peta COA (lihat SSOT §8) — dibuat lewat `backend/scripts/seed_expense_categories.py`
  (idempoten) atau migrasi tersendiri.
- `backend/routes/rahaza_posting.py`: fungsi baru
  `post_marketplace_settlement(db, settlement, user, as_draft=True)` memakai `_create_posted_je`
  dengan `status='draft'`, `source_module='marketplace_settlement'`, `source_ref=settlement_id`
  (idempoten lewat `_find_existing_je`).
- Akun dari master toko: `coa_cash_code`, `coa_receivable_code`, `coa_revenue_code` (F0.7).
- Finance approve lewat endpoint yang **sudah ada** `POST /api/rahaza/journals/{je_id}/post`.

### F9.3 Rekonsiliasi (menjawab "angka mana yang benar")
`GET /api/marketing/settlements/reconcile?account_id&period` ⇒ tabel:
omzet marketing (produk & order amount) · gross_sales settlement · selisih ·
komisi platform · potongan lain · refund · **net_payout** · % potongan terhadap omzet.
**UI:** `frontend/src/components/erp/MarketingARBridgeModule.jsx` (sekarang halaman
"dinonaktifkan") **dijadikan** halaman **"Pencairan & Rekonsiliasi"** — modul yang sudah
terdaftar, jadi tidak menambah modul baru. Tabel + pengalih tampilan + tautan ke jurnal draft.

### BUKTI SELESAI F9
1. Impor 1 laporan pencairan ⇒ dokumen `marketing_settlements` + 1 **JE draft** yang
   **balance** (Σ debit = Σ kredit, dibuktikan endpoint jurnal).
2. Impor berkas sama 2× ⇒ **1** JE (idempoten), pesan "sudah pernah diposting".
3. Finance `POST /journals/{id}/post` ⇒ `status='posted'`, muncul di buku besar & laporan L/R.
4. `reconcile` menampilkan selisih omzet marketing vs settlement + % potongan platform.
5. Tidak ada satu pun jurnal yang lahir dari `marketing_orders`/`marketing_sales_data`
   (dibuktikan `grep` + gate: `source_module` jurnal tidak boleh bernilai itu).

---

# FASE F10 — KONSOLIDASI DUPLIKASI + GATE AKHIR

1. **Hapus** `TokoProductCatalogModule.jsx` setelah F4 terbukti (komponen grid/foto sudah dipindah).
2. `toko-orders`/`toko-packing`/`toko-shipping` ⇒ `makeRedirect('marketing-orders', tab)`;
   `TokoOrdersModule.jsx` (kartu-saja, 1.055 baris) dihapus setelah kolomnya dipindah ke
   `UnifiedOrdersDashboard` (F3).
3. `MarketingSchedulerModule.jsx` & `MarketingWebhooksModule.jsx` ⇒ tambah pengalih Tabel/Kartu.
4. `SampleDeliveryModule.jsx` (kartu-saja) ⇒ tabel default + kartu; kolom penuh
   (tanggal · toko · kreator · produk/SKU · qty · HPP · total HPP · ongkir · kurir · resi ·
   status kirim · progress · link video · umur hari).
5. `dewi_executive_report.py:247` (`marketing_kol_campaigns` yang tidak pernah ditulis) ⇒
   ganti sumbernya ke `marketing_content_calendar`/`marketing_kol_creators` **atau** hapus metriknya.
6. Bersihkan koleksi `DEPRECATED` (0 dokumen) & hapus dari `REGISTRY`.
7. Jalankan seluruh gate + `scripts/audit_marketing_field_reads.py` &
   `scripts/audit_marketing_integrity.py` **dengan data nyata** ⇒ wajib **0 pasti_cacat**,
   **0 rujukan cacat**.
8. Perbarui `memory/PRD.md`, `memory/CHANGELOG.md`, `memory/BUG_REGISTRY.md`, `plan.md`.

### BUKTI SELESAI F10
`_forensic_ssot_v3.py`: `written_never_read` ≤ baseline, `read_never_written` ≤ baseline − 1
(minimal `marketing_kol_campaigns` hilang), `collections_in_code` **berkurang** (7 koleksi legacy
impor di-drop di F0.6) dan hanya bertambah untuk **4 koleksi baru yang sah**.
`_audit_ui_tables_v2.py`: **0** modul kartu-saja di antara 12 modul daftar-record marketing/toko,
**0** tabel <5 kolom di modul tersebut.

---

## BAGIAN E — GATE YANG HARUS HIJAU SEBELUM FASE DINYATAKAN SELESAI

```bash
cd /app/backend && python3 /app/scripts/_forensic_ssot_v3.py     # A6: tidak ada penambahan
cd /app        && python3 scripts/gate_marketing_ssot.py         # F0.1
cd /app        && python3 scripts/gate_marketing_scope.py        # F6.2
cd /app        && python3 scripts/_audit_ui_tables_v2.py         # B1–B3
cd /app        && python3 scripts/verify_marketing_scope.py      # gate lama (32 PASS)
cd /app        && python3 scripts/audit_marketing_field_reads.py # setelah ada data nyata
cd /app        && python3 scripts/audit_marketing_integrity.py   # setelah ada data nyata
cd /app        && bash scripts/gate.sh                           # lint/import platform
```
Ditambah **uji fungsional** oleh testing agent per fase, memakai user stories Bagian F.

---

## BAGIAN F — USER STORIES (dipakai testing agent, per fase)

**F0** ① Sebagai admin, saya mengimpor 1 baris rekap harian dan melihat angkanya muncul di Target
dan Dashboard tanpa layar mati. ② Sebagai admin, saya membuka tab impor lama dan mendapat
penjelasan jelas bahwa jalur itu ditutup, tetapi riwayat lama masih bisa dilihat.
③ Sebagai owner, saya melihat 10 toko nyata dengan akun pendapatan (COA) masing-masing.

**F1** ① Sebagai staf, saya memilih toko lalu mengunggah ekspor TikTok apa adanya (65 kolom) dan
601 baris masuk tanpa satu pun ditolak. ② Saya melihat 83 SKU platform dikelompokkan per produk
induk dan memetakannya dalam beberapa menit. ③ Saya mengimpor berkas yang sama dua kali dan data
tidak berlipat. ④ Saya salah memilih toko Shopee untuk berkas TikTok dan sistem menolak dengan
alasan yang saya mengerti. ⑤ Saya melihat omzet, diskon yang saya tanggung, dan sumber pesanan
(live/video/kartu produk) untuk toko itu.

**F2** ① Sebagai SPV, saya melihat omzet yang sama di Target, Dashboard, Anggaran, dan Sales
Performance untuk bulan yang sama. ② Sebagai staf, saya mencoba mengetik omzet harian yang sudah
diturunkan dari pesanan dan sistem menjelaskan mengapa itu tidak boleh.

**F3** ① Sebagai staf, saya melihat daftar pesanan yang belum dikirim lebih dari 2 hari beserta
umurnya. ② Saya mengimpor bukti kirim dan status pesanan berubah tanpa membuat pesanan baru.
③ Saya melihat pesanan "bocor" yang ada di ekspor A tapi tak pernah muncul di ekspor B.

**F4** ① Sebagai staf, saya melihat katalog dalam tabel dengan foto, HPP, marjin, stok jual, dan
status yang benar; saya bisa beralih ke tampilan kartu. ② Saya menandai produk sudah tayang dan
harus mengisi link marketplace-nya. ③ Produk baru dari master langsung membawa foto desain RnD;
saya menambah foto versi marketplace sendiri. ④ Saya menyaring produk yang belum tertaut master
dan memperbaikinya.

**F5** ① Sebagai SPV, dalam satu layar saya melihat target, omzet, anggaran, terpakai, marjin, dan
sisa hari per toko. ② Diskon yang saya tanggung terisi otomatis tanpa saya ketik. ③ Saya menutup
bulan dan tidak ada lagi yang bisa mengubah angkanya. ④ Saya diberi tahu ketika target ketinggalan
atau anggaran hampir habis.

**F6** ① Sebagai staf marketing, saya hanya melihat toko yang di-assign kepada saya. ② Sebagai SPV,
saya melihat semua toko dan bisa menetapkan target. ③ Sebagai siapa pun, saya bisa melihat siapa
mengubah target bulan lalu dari nilai berapa ke berapa.

**F7** ① Sebagai content creator, saya mengisi rencana konten, menempelkan link video yang sudah
terbit, dan memasukkan KPI-nya. ② Sebagai SPV, saya melihat performa konten per kreator untuk
rapat mingguan. ③ Saya melihat omzet yang didorong tiap kreator.

**F8** ① Sebagai SPV, saya mencetak laporan mingguan untuk rapat Senin. ② Sebagai owner, saya
melihat laporan bulanan per toko dan gabungan, dengan catatan jujur tentang data yang belum ada.
③ Saya mengunduh Excel untuk diolah sendiri.

**F9** ① Sebagai accounting, saya mengimpor laporan pencairan dan mendapat jurnal draft yang
seimbang untuk saya periksa. ② Saya membandingkan omzet marketing dengan uang yang benar-benar
cair dan melihat berapa yang dipotong platform.

---

## BAGIAN G — RISIKO & CARA MENJINAKKANNYA

| Risiko | Jinakkan |
|---|---|
| `marketing_orders` diubah dari 1-baris-SKU → header+`items[]` sementara **41 pembaca** sudah ada | pertahankan `revenue`, `total_payment`, `quantity`, `sku_id`, `product_name` di header sebagai **kompatibilitas**; analisis per-SKU pakai `$unwind`. Jalankan `scripts/audit_marketing_field_reads.py` setelah F1 |
| Impor besar (>20k baris) memperlambat commit | `MAX_ROWS=20_000` sudah ada; commit per-batch 500 + `bulk_write`; rollup dipanggil **sekali per tanggal**, bukan per baris |
| Zona waktu: `Created Time` lokal (WIB), `order_date` disimpan UTC | rollup mengelompokkan dengan konversi **Asia/Jakarta** eksplisit; ditulis di `core/marketing_daily_rollup.py` dan diuji dengan pesanan jam 23:30 & 00:30 |
| Owner mengganti `revenue_basis` di tengah bulan | `marketing_account_targets.basis` menyimpan basis saat target dibuat; layar menampilkan peringatan bila basis toko ≠ basis target |
| RBAC baru mematikan akses staf yang sudah bekerja | `can_act()` sudah punya mode aman (`legacy_roles`/`legacy_any`); pasang bertahap + gate `gate_marketing_scope.py` melaporkan endpoint yang belum dijaga |
| Kolom ekspor berubah sewaktu-waktu | `format_fingerprint` + kamus sinonim; fingerprint baru ⇒ wizard meminta konfirmasi pemetaan (tidak pernah diam-diam) |
| Migrasi merusak data | semua migrasi `--dry-run` dulu; `scripts/backup.sh` sebelum `--apply` |

---

## BAGIAN H — YANG SENGAJA **TIDAK** DIKERJAKAN (supaya ekspektasi jelas)

1. **Integrasi API real-time** ke Seller Center — jalur resmi tetap impor berkas.
2. **Potong stok otomatis saat impor** (K17) — hanya monitoring; sakelar menyusul setelah
   rantai FG (master → gudang → katalog) terbukti hijau.
3. **Komisi platform pada pesanan** — tidak ada di ekspor A; hanya dari Settlement (F9).
4. **Biaya `sample`** tetap manual (tidak ada di ekspor mana pun).
5. **Pembukuan otomatis dari omzet marketing** — dilarang permanen (K4).
6. **Modul UI baru** — nol; semua peningkatan pada modul yang sudah ada (A4).
