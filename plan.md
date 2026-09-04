# plan.md — SESI #34 (2026-08-23) · BIAYA JAHIT → HPP BATCH → MARKETING · IMPOR PINTAR · PORTAL KREATOR · GAJI HOST BULANAN

Status: **SELESAI & HIJAU** · `bash scripts/gate.sh` → **62 gate · VERDICT HIJAU**
(termasuk gate baru **INV-F39**). Rincian: `memory/CHANGELOG.md` entri **[#34]**,
`memory/INVARIANTS.md` bagian **INV-F39**.

## Keputusan pemilik yang mengunci desain (2026-08-23)
| Pertanyaan | Keputusan |
|---|---|
| Input biaya jahit di level mana | **Per SPK/batch, tarif diketik per SKU per pcs**, total dihitung sistem |
| Metode HPP | **FIFO per batch**; angka yang dipakai layar = **rata-rata lapisan yang MASIH bersisa** |
| Sumber data pencairan | **Manual + impor berkas** (backend F9 sudah menampung keduanya) |
| Siapa input pcs insentif | **Staf marketing** (bukan kreator) |
| Sesi live host | **Penggajian per-sesi dihapus**, log aktivitas live **tetap disimpan** |
| Gaji host | **Tersambung payroll HR** (`rahaza_payroll_profiles.base_rate`) |
| Layar pencairan di Marketing | **Marketing hanya MELIHAT** (input & jurnal tetap Finance) |
| Periode anggaran | **7 hari default**, mode **1 bulan tetap ada** & bisa dipilih |
| Periode insentif | **3 bulan default**, bisa dikonfigurasi |
| Insentif kreator | **per pcs dan/atau bonus target**, dikonfigurasi per kreator; tipe `new` tidak dapat insentif |

## Yang selesai di sesi ini
- **A. Biaya jahit SPK & HPP batch** — `core/fg_cost_layers.py`, `routes/production_sewing_cost.py`,
  layar **Biaya Jahit** (`prod-sewing-cost`), hook lapisan di `production_qty_ledger.post_fg_accepted`,
  sumber tarif baru `spk_actual` di `core/product_costing.resolve_cmt_rate`.
- **B. Impor pintar** — deteksi platform + peringkat jenis + banner salah-pilih + viewer tabel +
  pemetaan dibalik + sinonim dari **7 berkas ASLI pemilik** (`samples/marketplace_2026/`).
- **C. Pencairan marketplace** — layar `marketing-settlements` (lihat saja) + KPI + unduh CSV.
- **D. Periode anggaran 7 hari** — `/api/marketing/budget/period-settings`, `period_bounds`,
  `core/marketing_cycle.valid_period` menerima `YYYY-MM-DD`.
- **E. Portal Kreator** — login hidup, katalog dari SSOT tanpa HPP, request barang jalan, domisili,
  3 tipe, insentif + tracker + periode.
- **F. Live host** — gaji bulanan dari payroll HR (`core/livehost_salary.py`), upah per-sesi mati.
- **G. RnD Produk Final** — `routes/rnd_product_viewer.py` + layar `rnd-product-viewer`.
- **H. Mesin identitas varian** — pola nyata `(6-7th)`, `1 PCS`, `FIT TO M`, `DEWASA & L ANAK`,
  `BUNDLING`.

## Tambahan (lanjutan permintaan pemilik)
- **Tautkan SKU SPK** — alat usulan + penautan berjejak di layar Biaya Jahit; 4/7 baris demo
  ditautkan (bukti meyakinkan), **3 baris dibiarkan terlihat** karena masternya belum ada
  (`ARN-HD-L`, `ARN-PL-M`, `ARN-PL-L` — Rp 3.600.000 ongkos jahit menggantung).
- **Ditunda atas permintaan pemilik**: impor berkas pencairan (menunggu berkas asli) dan rapor
  kreator mingguan via WhatsApp (menunggu keputusan penyedia + nomor tujuan).

## Sudah selesai sesudah itu (fitur dulu, atas permintaan pemilik)
- **FIFO keluar dipasang** di `production_qty_ledger.issue_fg` (pintu barang jadi keluar) — lapisan
  tertua dimakan lebih dulu, COGS & `uncosted_qty` tercatat di baris pengiriman. Gate B3 mengikatnya.
- **Papan margin** di layar Produk Final RnD (urut margin tipis dulu + KPI margin + warna per kartu),
  dengan produk yang belum bisa dihitung disebut terpisah.

## PR berikutnya (belum dikerjakan — sengaja, bukan lupa)
0. **[DATA] Buat master untuk 3 SKU SPK yang belum ada** (`ARN-HD-L`, `ARN-PL-M`, `ARN-PL-L`) di Master
   Produk/RnD, lalu tautkan lewat layar Biaya Jahit — sesudah itu Rp 3,6 juta ongkos jahit punya
   jalan ke HPP.
1. ~~**Sambungkan COGS FIFO ke jurnal.**~~ **SELESAI sesi #38** —
   `routes/rahaza_posting.post_cogs_on_buyer_dispatch` sekarang memakai `fg_cogs` (biaya batch FIFO)
   sebagai dasar utama, snapshot HPP SPK hanya jalan mundur, dasarnya disebut (`basis`) di hasil &
   memo jurnal, dan `uncosted_qty` dilaporkan. Gate **INV-F44**. Layar: kolom **HPP Batch (FIFO)**
   di Riwayat Dispatch Buyer Shipment.
2. **[DATA] HPP batch masih Rp 0 untuk hampir semua SKU** karena BOM & tarif jahit historis belum lengkap
   (viewer RnD melaporkannya apa adanya: 20 dari 20 produk yang dilihat menyebut kekurangan).
   Ini pekerjaan **DATA**, bukan kode: isi BOM per model + tarif jahit per SPK berjalan.
3. **KPI konten per-konten** sudah ada di backend (`/api/marketing/content-calendar/performance`
   dengan `group_by=creator|content_type|account` + KPI per entri) dan sudah terpakai di
   `ContentPerformanceView`. Yang belum: **daftar drill-down per konten individual** di layar
   performa (sekarang harus dibuka dari Kalender Konten).
4. **Impor pencairan** — layar marketing hanya melihat; jenis impor `marketplace_settlement` perlu
   diuji dengan berkas pencairan asli (pemilik belum mengirimkan contohnya).
5. **`routes/marketing_data_import.py` 3.4k baris** — di atas ambang 700 baris; pecah menjadi
   detect / upload / mapping / commit / rollback.
