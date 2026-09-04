# HANDOFF — SESI #39 (eksekusi berikutnya)

Ditulis 2026-08-26 sesudah sesi #38. **Baca ini dulu.** Rincian sesi #38:
`memory/CHANGELOG.md` entri **[#38]**, invarian baru **INV-F44** di `memory/INVARIANTS.md`.
`bash scripts/gate.sh --full` → **65 gate · VERDICT HIJAU**.

---

## 1. Kalau container terlihat kosong/rusak (urutan WAJIB, ±5 menit)
```bash
mongorestore --quiet --gzip --drop --nsInclude='test_database.*' --dir=/app/backups/<terbaru>
pip install -r /app/backend/requirements.txt          # + cd /app/frontend && yarn install
EMERGENT_LLM_KEY=<key> bash /app/scripts/bootstrap.sh --skip-deps
bash /app/.logs/bringup.sh                            # seed marketing/konten/siklus
cd /app/backend && python3 scripts/seed_role_accounts.py   # ← WAJIB: tanpa ini absen/cuti/payslip MERAH
bash /app/scripts/rebuild_frontend.sh                 # frontend disajikan dari BUILD STATIS (±2 menit)
```
* `backend/.env` **wajib** memuat `JWT_SECRET` — tanpa itu backend menolak menyala (penjaga, bukan bug).
* Frontend memakai **PREVIEW_STABLE_MODE**: perubahan `frontend/src` TIDAK terlihat sampai
  `rebuild_frontend.sh` dijalankan. Jangan `craco start`.
* Kredensial uji: `memory/test_credentials.md` (sudah lengkap sejak sesi #38).

## 2. Kalau gate MERAH sesudah restore — cek ini SEBELUM menyalahkan kode
Sesi #38 menemukan 17 gate merah dan **nol** di antaranya regresi kode sesi #37. Alat yang memang
disediakan untuk memperbaiki data warisan:
```bash
python3 scripts/recompute_qty_ledger.py                      # buku kuantitas job vs dokumen
python3 scripts/repair_selisih_ssot.py --apply --topup-fg     # dispatch tanpa mutasi stok FG
cd backend && python3 migrations/add_closed_at_to_production_jobs.py --execute
curl -X POST .../api/wh/returns/sync-marketing -H "Authorization: Bearer $ADMIN"   # retur pembeli → gudang
curl -X POST .../api/seed/maklon-full          -H "Authorization: Bearer $ADMIN"   # master ARNA/ARN-HD/JMC
```
⚠️ `POST /api/seed/maklon-full` **menulis dokumen bernomor langsung tanpa menaikkan buku kuantitas**,
jadi sesudah menjalankannya `recompute_qty_ledger.py` + `repair_selisih_ssot.py` HARUS diulang.
Itu cacat penyemai yang belum ditutup — kandidat pekerjaan kecil bernilai.

---

## 3. Pekerjaan berikutnya (urut nilai, semuanya dari `plan.md` + audit sesi #38)

### P0 — DATA, bukan kode (pemilik sudah tahu, tinggal dieksekusi)
1. **HPP batch masih Rp 0 untuk hampir semua SKU.** Buktinya terlihat sendiri di sesi #38: gate
   INV-F44/J10 harus menyuntik biaya sendiri karena tidak ada satu pun batch nyata yang berbiaya.
   Yang dibutuhkan: **BOM per model** + **tarif jahit per SPK berjalan**. Sesudah itu jurnal COGS
   otomatis memakai `basis=fifo_batch` tanpa perubahan kode apa pun.
2. **Master untuk 3 SKU SPK yang belum ada** (`ARN-HD-L`, `ARN-PL-M`, `ARN-PL-L`) — Rp 3,6 juta
   ongkos jahit masih menggantung tanpa jalan ke HPP.

### P1 — kode
3. **Penyemai maklon menaikkan buku kuantitas sendiri** (lihat peringatan di §2). Satu penyemai yang
   memakai pintu resmi (`core.production_qty_ledger`) menghapus dua langkah perbaikan manual selamanya.
4. **Drill-down per konten individual** di layar Performa Konten. Backend sudah ada
   (`/api/marketing/content-calendar/performance` dengan `group_by=creator|content_type|account`);
   yang belum: daftar per konten di layar performa (sekarang harus dibuka dari Kalender Konten).
5. **`routes/marketing_data_import.py` 3.480 baris** (ambang repo 700) — pecah menjadi
   detect / upload / mapping / commit / rollback. Murni refactor, tidak terlihat pemakai; kerjakan
   hanya kalau ada waktu sisa.
6. **Impor berkas pencairan marketplace** — jenis `marketplace_settlement` menunggu **berkas asli**
   dari pemilik. Jangan menebak susunan kolomnya.

### Sudah selesai — jangan dikerjakan ulang
* Pencairan marketplace di Portal Finance + jurnal ber-COA akun toko (**INV-F42**, sesi #37)
* Margin katalog "belum bisa diukur" bukan 0% (**INV-F43**, sesi #37)
* 22 jenis impor → **6 kelompok** + deteksi otomatis (`/data-import/source-groups`, sesi #37)
* COGS pengiriman memakai biaya batch FIFO + kolom **HPP Batch (FIFO)** di baris expand **dan**
  dialog Detail (**INV-F44**, 11 invarian, sesi #38). Regresi tambahan:
  `cd /app/backend && python3 -m pytest tests/test_iter96_cogs_fifo_journal.py` (13 uji).
  ⚠️ Kalau menambah baris/kolom pada `_fifo_cogs_for_dispatch`: jumlahkan `uncosted_qty` **sebelum**
  `continue` — itu lubang yang sudah pernah membuat 10 pcs keluar gratis tanpa jejak.

---

## 4. Aturan kerja di repo ini (tidak berubah)
* **Ukur dulu, baru klaim.** Setiap pernyataan di laporan harus punya angka dari API/DB.
* Sesudah perubahan logika: `bash scripts/gate.sh --full` harus **0 FAIL**.
* Backend baru **wajib punya pintu di layar** (`portalNav.js` + `moduleRegistry.js`) **di sesi yang sama**.
* Jangan pernah membuat sumber kedua untuk satu angka rupiah (pelajaran COA pencairan & COGS).
* Bahasa jawaban ke pemilik: **Indonesia**.
