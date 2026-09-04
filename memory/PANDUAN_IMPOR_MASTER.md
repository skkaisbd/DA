# PANDUAN IMPOR MASTER DATA — CV. Dewi Aditya

Berkas ini menjawab satu hal: **data apa yang wajib masuk lebih dulu supaya sistem bisa
bekerja**, dan bagaimana cara memasukkannya tanpa melahirkan data hantu.

## 1. Kenapa master dulu, bukan transaksi

Yang sudah **terbukti** di sistem ini (bukan teori):

| Kalau ini kosong | Yang langsung rusak |
|---|---|
| Ukuran (kode tidak sah) | SPK produksi internal **menolak** dibuat |
| BOM per model+ukuran | **HPP tidak bisa dihitung** → margin katalog kosong |
| Lokasi/gudang | stok tidak bisa masuk (penerimaan & mutasi tidak punya tujuan) |
| Master barang jadi (SKU) | SPK & pesanan menunjuk SKU yang tidak ada ⇒ **biaya menggantung** (kejadian nyata: 3 baris SPK, Rp 3,6 jt) |
| Karyawan + profil payroll | upah borongan & **gaji live host** tidak bisa dihitung |
| Akun toko | impor pesanan/iklan/pencairan tidak punya pemilik |
| Harga jual katalog | margin & keputusan diskon tidak bisa dibaca |

## 2. Urutan wajib (sheet di template mengikuti nomor ini)

```
01 LOKASI ─┬─ 02 KARYAWAN (+payroll) ──────────────┐
           └─ (gudang untuk stok)                  ├─ 16 LIVEHOST (gaji dari payroll)
03 WARNA ─┬─ 09 BARANG JADI (SKU) ─┬─ 14 KATALOG JUAL (harga jual per toko)
04 UKURAN ┘        ▲               └─ (stok, pesanan, pengiriman)
08 MODEL ──────────┤
06 KAIN/BENANG ─┬──┴─ 10 BOM  ⇒ HPP
07 AKSESORIS ───┘        ▲
05 PROSES ───────────────┘ (upah borongan per pcs)
13 AKUN TOKO ─── 15 KOL/KREATOR
11 VENDOR CMT · 12 KLIEN MAKLON (mitra)
```

**Aksesoris (07) bukan pelengkap** — ia punya master sendiri dan **ikut masuk BOM** persis
seperti kain, karena kancing/label/hangtag adalah bagian nyata dari HPP.

## 2b. Unduh berkasnya

| Berkas | Tautan (preview) | Isi |
|---|---|---|
| Template kosong | `/downloads/TEMPLATE_MASTER_DA.xlsx` | 16 sheet siap diisi + PETUNJUK + DAFTAR_PILIHAN |
| Contoh terisi | `/downloads/CONTOH_TERISI_MASTER_DA.xlsx` | 59 baris contoh saling tertaut (kode berawalan `CTH-`) |

Sumbernya juga ada di repo: `data_import/` (dibuat ulang kapan pun dengan
`scripts/master_template_generate.py` dan `scripts/master_template_example.py`).
Berkas contoh **dijaga gate INV-F41 C2**: ia wajib selalu lolos importirnya sendiri.

## 3. Langkah kerja

```bash
# 1. Buat template kosong (sudah ada di /app/data_import/TEMPLATE_MASTER_DA.xlsx)
python3 scripts/master_template_generate.py /app/data_import/TEMPLATE_MASTER_DA.xlsx

# 2. Isi Excel-nya (copy-paste dari file Anda). Baris berawalan # = contoh, dilewati.

# 3. PERIKSA dulu — tidak menulis apa pun:
python3 scripts/import_master_template.py /app/data_import/MASTER_SAYA.xlsx

# 4. Kalau laporan bersih, SIMPAN:
python3 scripts/import_master_template.py /app/data_import/MASTER_SAYA.xlsx --apply

# 5. Hanya sheet tertentu (mis. menambah BOM saja):
python3 scripts/import_master_template.py MASTER_SAYA.xlsx --only 10_BOM --apply
```

Setelah BOM masuk, hitung HPP: **Portal Produksi → Costing → Terapkan HPP** (atau
`POST /api/costing/apply-all`). HPP batch FIFO tetap lahir sendiri dari SPK + biaya jahit.

## 4. Jaminan importir (dijaga gate INV-F41, 22 invarian)

* **Dua tahap**: seluruh berkas diperiksa dulu; penyimpanan hanya jalan bila bersih ⇒
  **tidak ada impor separuh**.
* **Dry-run bawaan** — `--apply` harus diminta sadar.
* **Idempoten**: kode (kode/nik/sku/kode_akun) adalah kunci ⇒ impor ulang **memperbarui**.
* **Referensi silang di berkas yang sama dikenali** (BOM boleh menunjuk kain yang baru
  diisi di sheet 06 pada berkas itu juga).
* **TIDAK menghapus apa pun** — data lama/demo dibiarkan (pembersihan dilakukan di
  lingkungan produksi masing-masing).
* Yang **ditolak dengan alasan jelas**: kolom wajib kosong · enum ngawur · kode ukuran
  berspasi/garis miring (merusak SKU) · BOM menunjuk material tak dikenal · barang jadi
  dipakai sebagai komponen BOM · qty BOM bukan angka · harga jual katalog 0 · kreator
  tipe `new` diberi insentif · live host tanpa NIK karyawan · kode kembar dalam berkas.
* Setiap dokumen hasil impor diberi penanda `import_batch` sehingga satu gelombang impor
  bisa dilacak (dan dibatalkan manual bila perlu).

## 5. Yang SENGAJA tidak lewat Excel

* **Password portal kreator & live host** — dibuat dari layar Marketing (tidak pernah
  ditulis di berkas yang dikirim lewat WhatsApp/email).
* **Saldo awal** (stok awal per gudang, piutang/hutang berjalan, saldo kas/bank) — bukan
  master; diimpor terpisah setelah master siap agar nilainya bisa dicocokkan.
* **CoA & posting profile akuntansi** — sudah terpasang (353 akun · 33 profil).
