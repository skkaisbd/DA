> ## ✅ SELESAI 2026-07-27 — dokumen ini menjadi ARSIP
> Enam pekerjaan di bawah (A1, A2, A3, B1, B2, B3, B4) **sudah dikerjakan dan diuji**.
> Ringkasan lengkap: `memory/CHANGELOG.md` entri **2026-07-27 SESI #7**.
> Sisa pekerjaan lanjutan ada di `memory/ROADMAP.md` (P0 & P1).
>
> Catatan koreksi terhadap isi dokumen ini:
> - A1 hanya butuh **2** file (`wms_putaway.py`, `wms_opname3.py`). Tiga file lain di daftar
>   ternyata tidak boleh diubah — 2 endpoint-nya sudah 410, 1 hanya membalik delta satuan dasar.
> - Nama asisten dipastikan owner: **"Asisten ERP CV. Dewi Aditya"**.
> - Owner memilih Anthropic SDK resmi (kunci sendiri), BUKAN Emergent LLM key.

# SERAH-TERIMA — Antrean Pekerjaan Berikutnya (2026-07-27)

Owner sudah **menyetujui 1a, 2a, 3a** untuk lanjutan UOM, lalu menambahkan
**4 permintaan baru**. Agen sebelumnya kehabisan konteks sebelum sempat
mengerjakan; **belum ada satu baris kode pun** yang ditulis untuk daftar di
bawah ini.

Baca dulu: `docs/RANCANGAN_MULTI_UOM.md` (§ STATUS PELAKSANAAN) dan
`docs/AUDIT_KONVERSI_SATUAN.md`.

---

## A. Lanjutan UOM — sudah disetujui owner

### A1 · Pasang `input_uom` di 5 titik masuk stok yang tersisa  *(pekerjaan agen)*
Polanya **sudah terbukti** di 4 titik yang selesai kemarin — tinggal ditiru.
- `routes/wms_putaway.py`
- `routes/dewi_warehouse_smart.py`
- `routes/wms_opname3.py`  → paling penting, pola sama dengan `dewi_accessories_opname.py`
- `routes/dewi_accessories_loans.py`
- `routes/dewi_accessories_requests.py`

Caranya: terima field opsional (`input_uom` / `counted_uom` / `qty_uom`), lalu
teruskan ke `stock_service.*(..., input_uom=...)`. Tanpa field itu perilaku
lama HARUS tetap sama persis. Contoh terbaik: `dewi_accessories_opname.py`
baris ~325 dan `rahaza_inventory_shared.py::_norm_mi_items`.

### A2 · Tambahkan kolom kemasan ke Ekspor/Impor Excel  *(pekerjaan agen)*
`backend/routes/data_transfer.py` → REGISTRY["materials"]["columns"]:
tambahkan `pack_unit` (str), `pack_size` (num), `display_in_packs` (bool),
dan `base_uom` (str). Importer sudah punya dry-run → commit.
**Wajib**: setelah impor, panggil `core.uom.apply_payload` supaya `uoms` &
cerminnya konsisten (INV-UOM-4), lalu guardrail `verify_uom_integrity.py`
harus tetap HIJAU. Tujuan: owner mengisi 478 item lewat 1 file, bukan 478 form.

### A3 · Siapkan daftar 91 item bersatuan kemasan untuk di-rebase  *(agen + input owner)*
74 `rol`, 14 `pak`, 3 `lusin`. Buat skrip yang mengekspor Excel berisi
`code | name | satuan_sekarang | stok | HPP | [kolom kosong: 1 <satuan> = ? <satuan baru>]`.
Owner isi faktornya → skrip menjalankan rebase massal memakai endpoint yang
sudah ada `POST /api/rahaza/materials/{id}/rebase-uom` (mode `preview` dulu,
baru terapkan). Endpoint & UI-nya SUDAH JADI dan teruji.

---

## B. Permintaan baru owner (dari screenshot Portal Produksi)

### B1 · Dashboard Produksi — visualisasi sudah tidak relevan
Owner: *"banyak item di sini untuk visualisasi datanya sudah tidak relevan
dengan keadaan system sekarang."*
Modul: `Monitoring Progress → Dashboard Produksi`.
Terlihat di layar: TOTAL OUTPUT, TOTAL WIP, FLOW EFFICIENCY, "WIP per Proses
(Cutting → Sewing → Finishing → QC → Packing)".
**Perlu klarifikasi ke owner**: proses mana yang masih dipakai sekarang?
(Cutting sudah jadi portal sendiri; CMT ditangani vendor luar.) Jangan menebak.

### B2 · Asisten ERP — nama salah & fungsinya usang
- Namanya **"Asisten ERP Triyasa"** → harus **CV. Dewi Aditya**. Cari string
  `Triyasa` di `frontend/src/` dan `backend/`.
- Fungsinya diubah menjadi **sadar-portal**: menjawab tentang portal yang
  sedang dibuka — cara pengerjaan, pengertian alur, daftar fitur.
- **Minim AI**: siapkan basis pengetahuan terstruktur per portal (mis.
  `backend/data/portal_kb/*.md` atau koleksi `portal_knowledge`), dijawab
  langsung tanpa LLM. **Hanya** pertanyaan kompleks yang dilempar ke AI.
- Saran pertanyaan bawaan sekarang ("Berapa downtime mesin hari ini?") juga
  tidak relevan — ganti mengikuti portal aktif.

### B3 · Konfigurasi Penomoran Dokumen & SKU otomatis  *(fitur baru, Portal Administrasi Sistem)*
Owner ingin **kontrol penuh** atas semua nomor dokumen (No. SJ, PO, WO, JE,
invoice, PR, MI, dst.) dan **SKU master data** supaya tidak diketik manual.
- Layar konfigurasi: pilih jenis dokumen → susun format dari **field data
  koleksi terkait** (mis. `{PREFIX}-{YYYY}{MM}-{SEQ:4}`, atau untuk SKU
  `{KATEGORI}-{WARNA}-{SIZE}-{SEQ:3}`).
- Sudah ada fondasinya: `backend/utils/counters.py::gen_prefixed_number`
  (race-safe, dipakai di banyak route) — **jadikan itu basisnya**, jangan
  bikin generator kedua.
- Petakan dulu SEMUA tempat yang menghasilkan nomor (cari `gen_prefixed_number`
  dan pola `f"...-{n:04d}"`), lalu arahkan ke konfigurasi terpusat.
- INV-CNT-1 (`memory/INVARIANTS.md` §E) mewajibkan nomor dokumen UNIK —
  guardrail ini WAJIB tetap hijau.

### B4 · Backup/Restore — perlu dirombak jadi lebih canggih
Modul sekarang: `mgmt-backup-restore` (`routes/data_transfer.py` +
`mongodump`/`mongorestore`). Owner minta dianalisis & dikembangkan:
- Kosongkan (clear) data **per koleksi**, bukan seluruh DB
- Impor data **per koleksi**
- Usulan tambahan yang perlu dianalisis dulu: jadwal backup otomatis, retensi,
  pratinjau isi backup sebelum restore, restore selektif, dan **konfirmasi
  berlapis** untuk operasi destruktif.
- **Hati-hati**: ini operasi paling berbahaya di sistem. Wajib RBAC super_admin,
  konfirmasi ketik-ulang nama koleksi, dan backup otomatis sebelum clear.

---

## Urutan yang disarankan
1. **A1** (cepat, pola sudah terbukti, menutup lubang konversi)
2. **A2** lalu **A3** (membuka jalan owner mengisi data)
3. **B2** (nama salah = paling terlihat, perbaikan string cepat; KB menyusul)
4. **B3** (fitur besar — petakan dulu semua penghasil nomor)
5. **B4** (fitur besar & berisiko — analisis dulu, minta persetujuan rancangan)
6. **B1** (butuh klarifikasi owner lebih dulu)

## Aturan yang tidak boleh dilanggar
- Bahasa ke owner: **Indonesia**.
- Frontend = **build statis**. Setelah ubah `frontend/src`, jalankan
  `bash /app/scripts/rebuild_frontend.sh` (±2 menit). **Jangan** `yarn start`.
- Sebelum menulis kode untuk fitur besar (B3/B4): **petakan dulu semua flow &
  koleksi terdampak**, seperti `scripts/map_uom_impact.py`. Ini permintaan
  eksplisit owner: *"jangan sampai malah memunculkan bug baru."*
- Guardrail wajib hijau: `verify_uom_integrity.py`, `check_nav_map.py`,
  `verify_rbac_idor.py`.
- Bersihkan SEMUA data uji setelah pengujian. Baseline DB:
  **1.031 material · 730 stok · 730 ledger · 0 jurnal**.
- Kredensial: `admin@garment.com` / `Admin@123`.
EOF
