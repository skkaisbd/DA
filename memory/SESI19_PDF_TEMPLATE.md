# SESI #19 — TEMPLATE PDF SATU PINTU + PENOMORAN LANJUTAN (2026-08-17/18)

> Menjawab `memory/PERMINTAAN_OWNER_PDF_EDITOR.md` (langkah 0 → 4). Dokumen ini
> catatan SERAH-TERIMA: apa yang diukur SEBELUM, apa yang berubah, dan penjaganya.

## 0) PENOMORAN LANJUTAN — SELESAI (gate INV-F25, invarian G1–G8 HIJAU)
Tiga jenis dokumen kini benar-benar menegakkan mode Otomatis/Manual:

| Jenis | Kunci registry | Jalur tulis | Form |
|---|---|---|---|
| Surat Jalan Gudang | `wh_delivery_notes.sj_number` | `routes/wms_delivery_notes.py::create_sj` | `WMSDeliveryNotesModule.jsx` |
| PR Pengadaan | `dewi_procurement_requests.request_number` | `routes/dewi_procurement.py::create_request` | `ProcurementRequestModule.jsx` |
| Jurnal Umum | `rahaza_journal_entries.je_number` | `routes/rahaza_journals.py::create_journal` | `RahazaJournalEntryModule.jsx` |

Temuan yang ikut diperbaiki (bukan permintaan, tetapi cacat nyata):
- `core/doc_number_policy.pattern_for()` memetakan token konteks ke `[A-Za-z0-9._]+`
  (tanpa tanda hubung). Format Surat Jalan `{TIPE}/{YYYY}/{MM}/{SEQ:4}` selalu memuat
  tanda hubung (SJ-CMT, SJ-INTERNAL, …) ⇒ **mode MANUAL mustahil dipakai**: nomor
  yang BENAR pun ditolak "tidak mengikuti pola". Kelas karakter ditambah `-`.
- `/api/doc-number-policy` sekarang menerima token konteks (`?ctx_TIPE=SJ-INTERNAL`).
  Tanpa itu pratinjau nomor di form berbunyi `TIP/2026/08/0001` — nomor yang tidak
  akan pernah lahir (layar berbohong).
- Pesan penolakan mode di `routes/doc_numbering.py` dulu menyebut daftar jenis
  ditegakkan secara HARDCODE (jadi basi setiap kali ada tambahan) → kini dari registry.
- Gate G4 dulu memakai `rahaza_journal_entries.je_number` sebagai contoh "belum
  ditegakkan"; setelah jurnal ditegakkan, kunci ujinya dipindah ke
  `rahaza_credit_notes.cn_number` (kalau tidak, G4 merah karena alasan yang salah).
- Jalur nomor yang **lahir tanpa manusia** tetap otomatis dan itu dicatat di `catatan`
  registry: SJ-CMT dari `wms_cmt_dispatches.execute_dispatch`, dan jurnal hasil posting
  otomatis (`routes/rahaza_posting.py`).
- `create_journal` dulu MENGGANTI nomor bentrok dengan nomor baru secara diam-diam;
  pada mode MANUAL itu berarti pemakai menyimpan JE-…-0007 lalu menemukan nomor lain
  di arsip ⇒ sekarang nomor ketikan yang bentrok dijawab 409.

## 1–3) EDITOR PDF SATU PINTU + PRATINJAU — SELESAI (gate INV-F26, P1–P8 HIJAU)

### Yang TERUKUR sebelum perbaikan
- **Dua layar** untuk satu dokumen: tab "PDF: Kolom Tabel" (`pdf_export_configs`,
  13 jenis laporan) dan tab "PDF: Surat & TTD" (`pdf_document_settings`, 7 jenis surat).
  Tiga jenis ada di KEDUANYA dengan label berbeda.
- Kop **tidak bisa memuat logo sama sekali**: `show_logo` disimpan sejak P1d tetapi
  tidak satu pun generator menggambar gambar.
- Kolom hanya bisa **disembunyikan** (`_filter_columns` mempertahankan urutan kode);
  tidak bisa diurutkan, tidak bisa ditambah.
- Blok tanda tangan dipotong tiga (`sig_defs[:3]`, `max_cols=3`) ⇒ blok ke-4 hilang.
- **Pick List tanpa kop sama sekali** (nama PT pun tidak ada) & tabel 174 mm dari 186 mm.
- **Surat Jalan Gudang** digambar `canvas.drawString` pada koordinat tetap: alamat
  dipotong 70 karakter, uraian barang dipotong 60 karakter & tidak pernah melipat.
- **Invoice** margin 18 mm (dokumen lain 12 mm) + lebar kolom tetap 170 mm.

### Arsitektur baru
```
data/pdf_doc_registry.py    ← SATU katalog: 19 jenis dokumen, kolom, field TTD,
                              TTD bawaan, bobot lebar, data CONTOH untuk pratinjau
core/pdf_template.py        ← SATU sumber template: koleksi `pdf_templates`
                              (1 dokumen GLOBAL + override per jenis), penggambar
                              kop/TTD/footer, penerap kolom, migrasi warisan
routes/pdf_templates.py     ← /api/pdf-templates (catalog, global, {doc_key}, preview)
utils/pdf_common.py         ← JEMBATAN tipis: `get_doc_settings()` mengembalikan
                              bentuk LAMA + `_template`, jadi generator lama ikut
                              menghormati template tanpa ditulis ulang
frontend .../pdf/PdfTemplateStudio.jsx  ← editor kiri + PRATINJAU PDF kanan
```
- Struktur pilihan pemilik: **satu template GLOBAL + override per jenis dokumen**
  (kolom selalu milik jenis dokumen).
- **Logo base64 di MongoDB** (maks 700 KB, PNG/JPG/WEBP, divalidasi).
- **Pratinjau** = PDF sungguhan dari backend dengan data CONTOH; mode **Gambar**
  (PNG hasil render pymupdf) menjadi bawaan karena penampil PDF bawaan browser tidak
  selalu ada dan iframe-nya tampil kosong tanpa pesan.
- Migrasi startup **idempoten** dari `pdf_document_settings` + `pdf_export_configs`
  (is_default) → `pdf_templates`; tidak pernah menimpa setelan baru.

## 4) LIMA PDF TERSERING — memakai template
| Dokumen | Yang berubah |
|---|---|
| SPP (`production-po`) | kop/TTD/footer dari template + kolom bisa DIURUTKAN |
| SJ Vendor (`vendor-shipment`) | idem |
| Dispatch Buyer (`buyer-shipment-dispatch`) | idem |
| **Pick List** | DITULIS ULANG: dapat kop (dulu tidak ada), tabel penuh lebar, TTD dari setelan |
| **Surat Jalan Gudang** | DITULIS ULANG dari canvas → platypus + template |
| Invoice Maklon | kop/tabel/TTD/footer dari template, margin & lebar diseragamkan |
| Slip Gaji | kop dari template (logo/telp/NPWP); tata letak A5 & watermark tidak diubah |
| Rekap Surat Jalan | kolom rekap ikut template (baris TOTAL dibangun per KUNCI, bukan indeks) |
| Laporan Produksi + 9 `report-*` | kop/TTD/footer dari template **dan** tabelnya pindah ke `_pdf_data_table` — dulu `int(680/len(headers))` & `int(445/len(headers))` (angka ajaib) memakai STRING mentah tanpa word-wrap; sekarang 0 tumpang tindih & 100% lebar konten (diukur pymupdf) |

Cacat yang ditemukan penjaga sendiri saat ditulis (dan sudah diperbaiki):
- kop baru memakai `leading` 16,5 pt untuk font 13,5 pt (1,22×) ⇒ nama PT
  **bersinggungan** dengan baris alamat di SEMUA dokumen. Aturan sesi #16 dipakai
  ulang: `leading = 1,44 × ukuran font` (juga untuk info, TTD, footer, dan tabel
  yang ukuran fontnya kini bisa diatur pemilik).
- `save()` dulu menggabung patch di atas BAWAAN ⇒ mengirim satu field (mis. hanya
  logo) MENGHAPUS nama PT & alamat yang sudah diatur. Kini digabung di atas nilai
  TERSIMPAN.

## PENJAGA
- `scripts/verify_fase_g2_penomoran_ditegakkan.py` — INV-F25, 8 invarian (G1–G8).
- `scripts/verify_fase_i_pdf_template.py` — **INV-F26 baru**, 8 invarian (P1–P8):
  satu pintu · satu koleksi · kop+logo tercetak di dokumen SUNGGUHAN · urutan/hide/
  tambah kolom berlaku · 4 blok TTD tercetak · 0 tumpang tindih + tabel ≥97% lebar ·
  logo divalidasi · endpoint warisan membaca template yang sama.
- Keduanya terdaftar di `scripts/gate.sh` dan ikut hitungan VERDICT.

## CATATAN UNTUK AGEN BERIKUTNYA
- Layar lama `PDFConfigModule.jsx` & `PdfDocSettingsModule.jsx` **dipensiunkan**
  (diberi banner peringatan, tidak dirujuk menu). Penjaga INV-F26/P1 akan MERAH bila
  dipasang kembali.
- Endpoint warisan `/api/pdf-export-*` & `/api/pdf-doc-settings/*` masih hidup dan
  kini membaca template baru — jangan menambah tulisan baru ke dua koleksi lama.
- Setelah mengubah `frontend/src/**` WAJIB `bash scripts/rebuild_frontend.sh`
  (tidak ada hot reload).


## LANJUTAN SESI #19 — PENOMORAN MENYELURUH (batch-2)

**Masalah yang diukur:** dari 49 jenis dokumen, 38 hanya berlabel "belum ditegakkan"
tanpa keterangan. Pemilik tidak bisa membedakan "nanti bisa diatur" dari "memang
mustahil diatur karena dokumennya lahir tanpa manusia" — jadi layarnya menyuruh
menunggu sesuatu yang tidak akan pernah datang.

**Yang dikerjakan:**
1. **Klasifikasi 49/49 (tidak ada lagi yang menggantung).** Setiap entri registry kini
   berlabel TEPAT SATU:
   - `policy_enforced` → **14 jenis** bisa diatur Otomatis/Manual;
   - `auto_only` + `alasan_otomatis` → **18 jenis** yang LAHIR TANPA MANUSIA (mis.
     penerimaan barang dari PO, hutang dari GR, nota kredit dari retur, sesi opname,
     dispatch CMT, kode master/SKU) — layar menyebut alasannya apa adanya;
   - `pending_enforce` → **17 jenis** yang punya form dan memang belum disambungkan.
2. **Batch-2 ditegakkan (dokumen UANG & STOK yang diketik orang):**
   | Jenis | Jalur tulis | Form |
   |---|---|---|
   | Purchase Order (PO Pembelian) | `routes/rahaza_po.py` | `PurchaseOrderModule.jsx` |
   | Pengeluaran Material (MI) | `routes/rahaza_inventory_shared.py` | `RahazaMaterialIssueModule.jsx` |
   | Retur Gudang | `routes/dewi_wh_returns.py` | `WHReturnsModule.jsx` |
   Jalur yang lahir otomatis di dua jenis pertama (PO massal per vendor, MI dari alur
   produksi internal) memakai parameter `sistem=True` dan tetap otomatis — dicatat di
   docstring & registry, bukan disembunyikan.
3. **Pesan penolakan dibedakan** (`routes/doc_numbering.py`): "SELALU bernomor otomatis
   — <alasan>" vs "belum bisa diubah: jalur tulisnya belum disambungkan".
4. **Gate INV-F25 naik ke 9 invarian**: G9 baru menahan jenis yang statusnya
   menggantung / berlabel ganda / "selalu otomatis" tanpa alasan, dan menuntut layar
   admin menampilkan alasannya. G4 kini menguji DUA jenis penolakan terpisah supaya
   pesannya tidak boleh tertukar.

**Bukti:** `verify_fase_g2_penomoran_ditegakkan.py` HIJAU 9 invarian · Retur Gudang
diuji langsung (auto menolak nomor ketikan; manual menolak pola bebas, menerima
`WH-RET-99001`) · `bash scripts/gate.sh` **VERDICT HIJAU 44/44**.

**Sisa untuk sesi berikutnya (17 jenis `pending_enforce`)**, urutan saran: Permintaan
Beli Aksesoris · Order Penjualan · Transfer Bank · PO Maklon · Aset Tetap · Pinjaman
Karyawan · Klaim Biaya · Perjalanan Dinas (2) · Permak · Retur Material Produksi ·
Permintaan Komponen · Sampel Maklon · Aset Inventaris · Permintaan Aksesoris ·
Permintaan Kreator · Pengeluaran Barang Jadi. Polanya sudah 4 langkah baku
(registry → `issue_number` → `<DocNumberField>` → daftarkan di WRITE_PATHS/FORM_PATHS).
