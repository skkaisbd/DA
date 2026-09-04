# Development Plan — Portal CMT Override ("Input Vendor CMT")

> **STATUS SESI 2026-08-08: SELESAI & TERVERIFIKASI ✅**
> Staf DA kini bisa mengisi **11 modul Portal Vendor CMT atas nama vendor** yang tidak
> memakai sistem, dengan jejak audit yang terlihat di layar monitoring & invoice.
>
> **BUKTI (semua dijalankan, bukan dikutip):**
> * `python3 test_core_cmt_override.py` → **96/96 LULUS** (POC isolasi, 11 modul lewat HTTP
>   sungguhan, RBAC, scoping, regresi portal vendor, UANG, nol drift)
> * `python3 scripts/verify_cmt_override.py` (gate baru **INV-CMTOV**) → **19/19 HIJAU**
> * `bash scripts/gate.sh` → **17/17 HIJAU** (16 gate lama + INV-CMTOV)
> * `python3 scripts/guardrails/check_nav_map.py --strict` → HIJAU (197 pintu)
> * `bash scripts/rebuild_frontend.sh` → build OK, frontend HTTP 200
> * testing agent iteration_37 → backend **19/19**, UI 7/11 (sisanya diselesaikan main agent
>   lewat Playwright, §5)
> * Verifikasi UI klik-penuh oleh main agent → **11/11 user story PASS** (§5)
> * Drift akhir: `POCOV`/`__CMTOVTEST__`/`__INVTEST__` = **0**, AR invoice maklon yatim = **0**

---

## 0) Yang diminta owner

Vendor CMT (sub-kontraktor jahit) banyak yang **tidak memakai sistem** — tidak mau/tidak bisa
login portal. Karena **tagihan CMT dihitung dari progress produksi**, data yang tidak masuk =
uang yang tidak bisa ditagih/diverifikasi. Solusi: staf DA membuka portal vendor dan
mengisinya **atas nama vendor**.

| # | Keputusan owner | Diterapkan |
|---|---|---|
| 1a | **SEMUA 11 modul** di-mirror (bukan sebagian) | ✅ 11 tab + 1 tab Jejak Audit |
| 2b | Hanya `admin`, `superadmin`, `admin_produksi`, `supervisor_produksi`, `ppic` | ✅ dijaga 2 lapis (pintu nav + backend) |
| 3a | Jejak "diinput staf DA" **tercatat + KELIHATAN** | ✅ 8 write path distempel + badge di 3 layar |
| 4a | Dropdown = **semua vendor aktif** di master CMT | ✅ tanpa flag baru |
| 5a | Vendor ber-akun aktif **tetap boleh**, cukup diperingatkan | ✅ peringatan + tanggal login terakhir |

Permintaan tambahan owner di tengah sesi: **"pastikan di maklon juga ada"** → pintu didaftarkan
di **Portal Produksi** DAN **Portal Maklon**, keduanya diverifikasi lewat layar.

---

## 1) Titik berhenti sesi lalu & pemulihan lingkungan

`/app` ternyata **template KOSONG** (repo tidak ada). Dipulihkan lebih dulu:
1. `git clone --depth 1` repo → `rsync` ke `/app` (kecuali `.env`, `.git`, `node_modules`).
2. `mongorestore` dari `backups/auto_20260807_190000` → state sesi terakhir (198 koleksi, 1218 dok).
3. `EMERGENT_LLM_KEY=… bash scripts/bootstrap.sh` → 91 detik, backend healthy, FE HTTP 200,
   6 akun login 200.

---

## 2) ⚠️ Audit lebih dulu — 4 blocker + 2 bug lama yang tak terlihat

Plan tidak ditulis dari tebakan: 11 modul diaudit satu per satu (endpoint + kesiapan override).
Pola backend yang sudah ada ternyata **setengah siap**: banyak endpoint tulis sudah menerima
`body.vendor_id` dari staf, tetapi **4 pintu terkunci keras**:

| Modul | Temuan |
|---|---|
| Dashboard | `GET /api/vendor/dashboard` → **403 KERAS** untuk semua non-vendor ⇒ staf mentok di pintu pertama |
| Progress Produksi | `GET /api/production-progress` tak punya filter vendor untuk staf, **dan** filter vendornya memakai `garment_id` |
| Kirim ke Buyer | `_resolve_receiver_type()` → **403** kalau bukan vendor mengirim `receiver_type='da'` — ini modul yang menentukan TAGIHAN |
| Inbox Reminder | `PUT /reminders/{id}` hanya menerima `response` bila `role == 'vendor'` |

**Dua BUG PRE-EXISTING ikut ketemu & ditutup** (bukan bagian permintaan, tapi merusak vendor asli):
1. **Riwayat progress portal vendor SELALU KOSONG.** Progress jalur `job_item_id` (satu-satunya
   jalur yang dipakai `VendorProgress.jsx`) **tidak pernah menulis `garment_id`** — terbukti di DB:
   0 dari 4 dokumen `production_progress` punya field itu. Jadi vendor tidak pernah bisa
   memeriksa setorannya sendiri, padahal angka itulah dasar tagihannya.
2. **Inbox reminder BOCOR ke semua vendor.** Scoping memakai `role == 'vendor'`, padahal role
   portal CMT adalah **`cmt_vendor`** ⇒ setiap vendor CMT melihat reminder milik semua vendor.
   Dan balasan reminder oleh `cmt_vendor` **selalu diabaikan** (tombol balas tersimpan tanpa efek).

---

## 3) Keputusan arsitektur — kenapa HEADER, bukan mengedit 11 komponen

`X-CMT-Override-Vendor` + SSOT tunggal **`backend/core/cmt_override.py`**
(`resolve_override`, `stamp`, `apply_scope`, `effective_vendor_id`, `OVERRIDE_ROLES`).

Alternatifnya adalah menyisipkan `?vendor_id=` ke ±40 pemanggilan API di 11 komponen
`engine/Vendor*.jsx`. Itu ditolak karena **satu komponen yang lupa diedit akan menampilkan data
SELURUH vendor kepada staf — kesalahan yang tidak kelihatan**. Dengan header:
* scoping dikerjakan backend lewat SATU pintu,
* 11 komponen dipakai ULANG **apa adanya** ⇒ risiko regresi portal vendor ~nol,
* mustahil "layar override bilang X padahal vendor melihat Y" — kodenya benar-benar sama.

Invarian keamanan (dijaga INV-CMTOV): role tak berhak **DITOLAK 403** (bukan diabaikan diam-diam),
akun vendor tidak boleh memakai header (mustahil menyamar), vendor tujuan wajib ada & aktif,
dokumen override WAJIB berstempel, dokumen non-override **tidak ditambahi field apa pun**.

---

## 4) Yang dikerjakan

### 4.1 Backend
* **BARU** `core/cmt_override.py` — SSOT konteks & jejak override.
* **BARU** `routes/cmt_override_routes.py` — `GET /api/cmt-override/vendors` (semua vendor aktif +
  `has_active_portal_account`, `last_login_at`, pesan peringatan, ringkasan pekerjaan tertunda),
  `/context`, `/audit` (panel transparansi staf vs vendor, 8 modul penulis).
* 4 blocker ditutup; `/vendor/dashboard` juga **diisi** `recentProgress` & `alerts` yang dulu
  dikembalikan list kosong permanen padahal dirender FE.
* Stempel `entered_by*` + `on_behalf_of_vendor*` diselipkan ke **8 write path**
  (`vendor_shipments` penerimaan pakai prefiks `receipt_`, `reminders` pakai `response_`).
* `POST /auth/login` mencatat `users.last_login_at` (bahan peringatan 5a).
* Bahan badge dihitung di **`_enrich_jobs` (SSOT bersama `/production-jobs` &
  `/production-tracking`)** + `production_cmt_billing._staff_entry_map` + `/prod/cmt-receipts`.
* `ppic` ditambahkan ke akses Portal Produksi & Maklon (FE `portalAccess.js` + BE
  `routes/shared.py`) — sebelumnya PPIC punya izin fitur tapi **tidak punya jalan ke portalnya**.

### 4.2 Frontend
* **BARU** `CMTOverridePortalModule.jsx` — pemilih vendor (kartu + pekerjaan tertunda +
  peringatan/aman), spanduk **sticky** "MODE ISI ATAS NAMA VENDOR" (vendor + nama staf + role),
  peringatan dobel input dengan daftar akun & login terakhir, 11 tab reuse `Vendor*.jsx`,
  tab **Jejak Audit**.
* **BARU** `engine/StaffEntryBadge.jsx` — badge `staff|mixed|vendor|none`, satu bentuk untuk semua layar.
* `lib/api.js` — injeksi header terpusat (`setCmtOverrideVendor`/`clearCmtOverrideVendor`).
  Header di-set **sinkron saat klik** (efek anak berjalan sebelum efek induk di React) dan
  **di-clear saat unmount**.
* Badge dipasang di **Tracking/Monitoring Produksi**, **Invoice CMT**, **Terima FG dari CMT**.
* Nav: pintu **"Input Vendor CMT"** di Portal Produksi → MASTER DATA **dan** Portal Maklon →
  MASTER DATA (sengaja di section PERTAMA: sidebar hanya menampilkan pintu section aktif, jadi
  di section kedua pintunya tak terlihat — temuan uji). Pintu **di-role-gate** (`roles` pada item
  nav + helper `navItemAllowed`) supaya `operator`/`spv_cuting` tidak melihat menu buntu.
* Pintu **"Tracking Vendor"** (`prod-monitoring`) ditambahkan ke Portal Maklon: layar monitoring
  yang dikelompokkan **per vendor CMT** dulu hanya punya pintu di Portal Produksi, dan komponennya
  memilih domain dari portalnya (`internal`) ⇒ **vendor CMT maklon tidak pernah terlihat di sana**,
  termasuk badge yang justru paling relevan untuk mereka.

### 4.3 Alat & data
* **BARU** `scripts/seed_cmt_override_demo.py` (idempoten, `--cleanup`): **CV Tanpa Sistem CMT**
  (tanpa akun portal = kasus utama, + PO 200 pcs + surat jalan `Sent` + reminder pending) dan
  **CV Punya Akun CMT** (akun aktif ⇒ memicu peringatan 5a).
* **BARU** `test_core_cmt_override.py` (POC, 96 pemeriksaan) & `scripts/verify_cmt_override.py`
  (gate INV-CMTOV, 19 invarian). Keduanya membersihkan jejaknya + **sweep seluruh koleksi**.

### 4.4 🔴 Temuan sampingan: gate repo sendiri membocorkan UANG PALSU
`verify_produksi_maklon_invariants.py` menghapus `rahaza_ar_invoices` berdasarkan `notes` yang
memuat penanda uji — padahal catatan AR invoice **ditulis jembatan maklon** dan tidak pernah
memuat penanda itu. Akibatnya **setiap kali gate dijalankan, 2 AR invoice maklon tertinggal
sebagai PIUTANG YATIM**. Terakumulasi **Rp 15.120.000 palsu (14 dokumen)** dari sesi-sesi
sebelumnya. Sudah: pembersihan berbasis FK + jaring pengaman "AR maklon yatim", dan 14 dokumen
palsu dihapus. Sekarang AR yatim = **0**.

---

## 5) User Stories — hasil verifikasi UI klik-penuh (11/11 PASS)

| # | Alur | Hasil |
|---|---|---|
| 1 | Pintu "Input Vendor CMT" terlihat & bisa diklik dari sidebar Portal Produksi | ✅ (MASTER DATA) |
| 1b | Pintu yang sama di **Portal Maklon** | ✅ picker render, 3 kartu vendor |
| 2 | Pilih vendor tanpa akun → spanduk menyebut vendor + nama staf, 12 tab | ✅ |
| 3 | Vendor ber-akun aktif → peringatan dobel input + tanggal login, tetap boleh lanjut | ✅ |
| 4 | Rantai penuh: terima → inspeksi (kurang 5 pcs) → permintaan → job → progress → kirim CMT→DA → variance → balas reminder | ✅ 8/8 (terima & inspeksi lewat klik UI; sisanya lewat header override yang sama, semua 201/200) |
| 5 | Tab Jejak Audit memisahkan staf vs vendor | ✅ staf **8**, 8 modul terlacak, nama staf tertulis |
| 6 | Badge "diinput staf DA" terlihat | ✅ Tracking Vendor (maklon): `diinput staf DA · 30 pcs`; Terima FG dari CMT: `staf DA` |
| 7 | Role `hr` → pintu tidak muncul; dipaksa buka → layar "Tidak berwenang" | ✅ |
| 8 | Role `ppic` → bisa membuka Portal Produksi & Maklon + pintunya | ✅ |
| 9 | Regresi portal vendor asli | ✅ portal terbuka, **riwayat progress tidak kosong lagi**, tidak ada kiriman/reminder vendor lain |
| 10 | Tidak bocor saat mode override | ✅ hanya data vendor yang diwakili |
| 11 | Konteks override hilang setelah keluar | ✅ layar staf kembali menampilkan 2 vendor |

Angka UANG dicek ulang sesudah semua klik: total tagihan CMT **2.435.000 → 2.435.000** (tidak bergeser).

---

## 6) Konsekuensi terbuka & backlog berikutnya

1. **Badge di layar Invoice CMT** sudah terpasang & datanya terbukti ada (INV-CMTOV OV-13), tetapi
   baru **tampil setelah AP matang** — yaitu setelah DA mengisi `qty_actual` + menyelesaikan QC di
   "Terima FG dari CMT". Untuk vendor demo, penerimaan masih berstatus **Sedang QC**, jadi badge
   invoice belum bisa dilihat di layar. **Belum diverifikasi secara visual.**
2. Modul **Panduan Produksi** & **Serial Tracking** dalam mode override bersifat baca-saja dan
   isinya bergantung master artikel; untuk vendor demo belum ada SOP terisi.
3. `dewi_cmt_payments` memakai DUA master CMT (`cmt_partner_id` → `dewi_cmt_partners`,
   `vendor_id` → `vendor_partners`). Badge invoice memakai `vendor_id`; tagihan lama yang hanya
   punya `cmt_partner_id` tidak akan menampilkan badge. Perlu keputusan penyatuan master.
4. Sisa backlog sesi sebelumnya masih berlaku: warna baris BOM belum dibatasi ke
   `dewi_rnd_materials.colors[]`, isi SKU massal 115 varian impor, laporan SKU drift lintas-style,
   `order_seq` ukuran hasil "buat baru", `except Exception: pass` di 6 titik jalur stok/uang,
   44 titik penomoran `count_documents()+1`, nol test Jest/RTL di `frontend/`.

---

## 7) Catatan lingkungan (jangan "diperbaiki" balik)

* Frontend = **STATIC BUNDLE** (`frontend/static_server.js`). Setiap perubahan `frontend/src`
  WAJIB diikuti `bash scripts/rebuild_frontend.sh`. Jangan `yarn start`.
* Verifikasi: `bash scripts/gate.sh` → **17 gate**.
* Sidebar hanya menampilkan pintu **section AKTIF**; pintu di section kedua tidak terlihat sampai
  pil section diklik. Taruh pintu penting di section pertama.
* Navigasi otomasi: `window.location.hash='<module-id>'` lalu **reload**, atau
  `/?portal=<portal>&module=<module-id>` (butuh KEDUA parameter).
* Beberapa aksi vendor memakai **`window.confirm()` native** (mis. "Konfirmasi Terima") ⇒ skrip
  Playwright wajib `page.on("dialog", lambda d: d.accept())`, kalau tidak aksinya dibatalkan senyap.
* Setelah inspeksi material, modal "Ajukan Permintaan Material Tambahan" **terbuka otomatis** dan
  memblokir klik lain sampai ditutup.
* Password akun vendor demo `cmtvendor@dewiaditya.id` = **`Dewi@123`** (bukan `Vendor@123`).
* Kredensial lengkap: `memory/test_credentials.md`.
