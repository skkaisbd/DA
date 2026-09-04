# 🧾 GATE RECEIPT — CV. Dewi Aditya ERP

> Dihasilkan `scripts/gate.sh`. JANGAN edit manual.
> "Selesai" hanya sah bila receipt HIJAU untuk cakupan yang TIDAK di-skip.

- **Waktu:** 2026-08-26 03:26:12  ·  **Durasi:** 151s  ·  **Mode:** full
- **Backend:** RUNNING · **Auth:** READY

| Gate | Hasil |
|------|-------|
| UANG/DATA — invarian GL, stok, AR/AP (verify_data_integrity) | PASS |
| UANG — baseline valuasi aksesoris (SSOT acc_baseline) | PASS |
| UANG — state machine jurnal (draft→posted→voided) | PASS |
| UANG — nomor dokumen tak boleh kembar saat balapan (RC-5) | PASS |
| UANG — batas nilai AR/AP/maklon (round6) | PASS |
| KEAMANAN — akses lintas-role & tanpa token (RBAC/IDOR) | PASS |
| KETAHANAN — input jahat harus 4xx, bukan 500 | PASS |
| BISA DIPAKAI — endpoint kritis terjangkau | PASS |
| ALUR — produksi/maklon/CMT: reject, rework, stok FG, SJ gabungan | PASS |
| DATA/UANG — R&D: ukuran tech pack, SKU SSOT, HPP hybrid (INV-RND) | PASS |
| DATA — SSOT warna: palet master bebas warna sampah (INV-COLOR) | PASS |
| DATA/UANG — R&D: padankan ukuran + harga master basi (INV-RND2) | PASS |
| KEAMANAN/UANG — Portal CMT Override: kewenangan, scoping, jejak (INV-CMTOV) | PASS |
| UANG/PRODUK — Rekap Harian + Mingguan CMT: batas WIB, definisi terisi, SSOT export (INV-REKAP) | PASS |
| UANG/DATA — Master Produk: kode kembar, kategori, HPP, berat, SKU (INV-PRODUK) | PASS |
| UANG — Katalog: satu rumus stok jual, anti-overselling, tautan order (INV-KATALOG) | PASS |
| DATA/UANG — Marketing: lingkup toko + impor tanpa AI (INV-MKTSCOPE) | PASS |
| UANG/ARAH — Marketing: siklus target·anggaran·omzet + kunci periode (INV-MKTCYCLE) | PASS |
| DATA/UANG — Marketing: impor KPI Seller Center + assign toko + scorecard (INV-KPIIMPOR) | PASS |
| DATA/UANG — Marketing: status pengiriman (Ekspor B/C) + pemulihan impor (INV-MKTFULFILL) | PASS |
| DATA/KEWENANGAN — Marketing: assign toko · ingat pemetaan · scorecard kreator (INV-MKTOPS) | PASS |
| UANG/ARAH — Marketing: omzet bruto vs setelah retur (INV-RETUR) | PASS |
| KEAMANAN/DATA — Marketing: lingkup toko per pemakai + jejak perubahan (INV-F6RBAC) | PASS |
| BISA DIPAKAI — Marketing: layar daftar (tabel · cari · unduh) + field tak disembunyikan (INV-F10) | PASS |
| DATA/UANG — Marketing: pratinjau impor per baris = kenyataan (INV-F11) | PASS |
| DATA/UANG — Marketing: berkas ekspor tidak boleh masuk toko yang salah (INV-F12) | PASS |
| UANG/STOK — Dispatch ke buyer: satu rumus sisa kirim + hasil permak bisa dikirim (INV-F16) | PASS |
| DOKUMEN — PDF rapi: 0 tumpang tindih + tabel penuh lebar halaman (INV-F17) | PASS |
| STOK/UANG — Kirim material ke CMT menerbitkan MI + memotong stok + jurnal (INV-F18) | PASS |
| PRODUK/STOK — Gudang: tombol buat MI, Buat Barcode, menu mati dilepas (INV-F19) | PASS |
| LAYAR/UANG — Dashboard Marketing: ada pintunya + angka resmi dari SSOT siklus (INV-F20) | PASS |
| DATA — Nomor dokumen: mode Otomatis/Manual ditegakkan, nomor bebas ditolak (INV-F21) | PASS |
| STOK/PRODUK — Gulungan kain: lahir dari penerimaan, wajib ditunjuk saat dipotong (INV-F22) | PASS |
| DOKUMEN/NAVIGASI — Surat jalan satu daftar lintas sumber + pintu lama tak kosong (INV-F23) | PASS |
| STOK/DOKUMEN — Arus keluar Cutting berdokumen, stok turun sekali (INV-F24) | PASS |
| DATA — Setelan penomoran dokumen benar-benar ditegakkan (INV-F25) | PASS |
| DOKUMEN — Template PDF (kop/logo/kolom/TTD) benar-benar tercetak (INV-F26) | PASS |
| STOK/DOKUMEN — Permak menaikkan sisa kirim · dispatch lanjutan · aksesoris BOM (INV-F27) | PASS |
| UANG/DATA — Monitoring CMT: potongan sesuai order · scope PO · lacak pengganti (INV-F28) | PASS |
| DATA — Sinkronisasi identitas barang Marketing ⇄ Gudang (INV-F29) | PASS |
| DATA/STOK — Identitas barang: warna·ukuran·OPSI tidak menabrak (INV-F30) | PASS |
| ALUR/STOK — Retur pembeli Marketing → Retur Fisik gudang → stok (INV-F31) | PASS |
| LAYAR/DOKUMEN — Tabel stok terbaca & kolom cetak bisa dipilih (INV-F32) | PASS |
| DOKUMEN — Surat jalan CMT → DA bisa dicetak dari penerimaan FG (INV-F33) | PASS |
| STOK — Alert stok hidup & satu definisi 'rendah' (INV-F34) | PASS |
| STOK/PRODUKSI — Satuan gulungan, style dari master, harga dari pembelian (INV-F35) | PASS |
| UANG/PRODUKSI — HPP per potong dari pembelian & BOM mengisi cutting (INV-F36) | PASS |
| UANG/STOK — Nilai potongan lahir saat dipotong & tak ada potongan yatim (INV-F37) | PASS |
| UANG/STOK — Belanja mingguan dari ambang, riwayat harga, ambang massal (INV-F38) | PASS |
| UANG/DATA — Biaya jahit SPK, HPP batch FIFO, impor pintar, gaji host bulanan (INV-F39) | PASS |
| DATA — KPI konten per konten/jenis/toko/KOL + rapor kreator mingguan (INV-F40) | PASS |
| DATA — Impor master dari template Excel: dry-run, tolak cacat, idempoten (INV-F41) | PASS |
| UANG — Pencairan marketplace: form Finance, COA akun toko, selisih bernama (INV-F42) | PASS |
| UANG — Margin katalog: 0%/100% tidak dikarang saat HPP tak diketahui (INV-F43) | PASS |
| UANG — COGS pengiriman memakai biaya batch FIFO yang benar-benar keluar (INV-F44) | PASS |
| FITUR MATI — handler tergabung / kode setelah return | PASS |
| FITUR MATI — panggilan FE ke endpoint yang tak ada | PASS |
| NAVIGASI — menu hantu / duplikat / kedalaman | PASS |
| LAYAR — UANG/STOK di luar Marketing bisa dipakai & dibawa (INV-F13) | PASS |
| DATA/UANG — Form wajib memakai Master, bukan ketikan (INV-F14) | PASS |
| LAYAR — Kartu punya latar, tulisan terbaca, token tidak berbohong (INV-F15) | PASS |
| SERAH-TERIMA — mesin lint platform hidup (import validation + oxlint) | PASS |
| PRODUK — absen (selfie+geofence wajib) | PASS |
| PRODUK — cuti | PASS |
| PRODUK — payslip karyawan | PASS |
| PRODUK — alur lembur live (HRIS) | PASS |

## ✅ VERDICT: HIJAU — boleh lanjut / klaim selesai (untuk cakupan non-skip).

_SKIP bukan PASS. Jalankan ulang saat backend + auth hidup._
