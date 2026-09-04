# PERMINTAAN OWNER — PDF EDITOR & KOP SURAT (dicatat 2026-08-17, akhir sesi #18)

> Dicatat VERBATIM di akhir sesi karena anggaran konteks sesi #18 habis. JANGAN mulai
> separuh jalan: ini pekerjaan satu sesi penuh. Kerjakan berurutan 0 → 4.

## 0) Penomoran lanjutan (kecil, kerjakan dulu sebagai pemanasan)
Tegakkan mode Otomatis/Manual untuk 3 jenis lagi: **Surat Jalan Gudang**
(`wh_delivery_notes.sj_number`), **PR Pengadaan** (`dewi_procurement_requests.request_number`),
**Jurnal Umum** (`rahaza_journal_entries.je_number`).
Pola SUDAH terbukti (sesi #18) — ulangi 4 langkah: tandai `policy_enforced` di
`backend/data/doc_number_registry.py` → ganti `gen_prefixed_number` jadi
`issue_number(db, KEY, requested=...)` di jalur tulisnya → pasang `<DocNumberField>` di formnya
→ daftarkan jalur tulisnya di `WRITE_PATHS` gate `scripts/verify_fase_g2_penomoran_ditegakkan.py`
(G1 akan MERAH kalau hanya ditandai tanpa disambungkan — itu memang tujuannya).

## 1) KELUHAN OWNER (kata-katanya)
- "untuk pdf konfigurasi saat ini **editor masih sangat buruk**"
- "cek **ada dua halaman berbeda ui ux**nya jelas. saya ingin perbaiki ui uxnya"
- "**header surat sangat buruk sekali**"

⇒ Langkah pertama WAJIB: temukan KEDUA layar konfigurasi PDF itu (cari modul id ber-'pdf' di
`frontend/src/components/erp/moduleRegistry.js` + `portalNav.js`), UKUR bedanya, lalu SATUKAN
jadi satu layar (satu pekerjaan = satu pintu, seperti Fase H-8).

## 2) YANG HARUS BISA DIATUR (PDF template editor)
- **Kop surat / header sebagai TEMPLATE yang bisa dikonfigurasi**: info PT (nama, alamat, telp,
  NPWP dll), **logo** (unggah), tata letak — bukan hardcode.
- **Kolom tabel**: bisa **ada/tidak** (show-hide), **urutannya bisa diubah**, dan bisa
  **ditambahkan** kolom baru.
- **Kolom tanda tangan**: **bisa lebih dari satu**. Struktur tiap blok:
  · ATAS = **subject** yang bisa di-custom ("Penerima", "Pengirim", dll)
  · TENGAH = ruang tanda tangan (kosong, untuk ditandatangani)
  · BAWAH = **nama** — kolomnya disediakan tetapi **dikosongkan** agar user bisa tanda tangan.
- **Format yang lebih bagus** secara umum.

## 3) PREVIEW/VIEWER
Ada **preview/viewer di SAMPING editor** supaya user langsung mengecek hasilnya tanpa mengunduh.

## 4) SASARAN LAMA YANG MENYATU DENGAN INI (ROADMAP F3/F4)
Rapikan **5 PDF tersering** (SPP · Invoice · Slip Gaji · Picklist · SJ Vendor) ke pola
`_pdf_data_table` — **tabel penuh lebar halaman + teks TIDAK tumpang tindih**.
Gate yang sudah menjaga ini: **INV-F17** (`0 tumpang tindih` + `tabel ≥97% lebar konten`,
diukur pymupdf — bukan dilihat mata). Sesi #16 sudah membuktikan cacat `leading` 9,5pt untuk
font 7,5pt menyebabkan tumpang tindih ±0,8pt di SEMUA dokumen; jangan ulangi polanya.

## CATATAN TEKNIS UNTUK PELAKSANA
- Generator PDF: `backend/routes/operations_pdf*.py` (+ helper `_pdf_data_table`).
- Frontend static bundle: setelah ubah `frontend/src/**` WAJIB
  `bash /app/scripts/rebuild_frontend.sh` (tidak ada hot reload).
- Simpan konfigurasi template di SATU koleksi (jangan dua tempat yang bisa berbeda pendapat),
  dan buat gate barunya (INV-F26?) yang mengukur: kop terisi dari konfigurasi, kolom
  show/hide+urutan benar-benar berlaku di PDF, jumlah blok tanda tangan sesuai setelan,
  dan 0 tumpang tindih (pymupdf).
