# TEMUAN — AUDIT PORTAL MARKETING (sesi #40, 2026-08-26)

Permintaan pemilik: *"untuk portal marketing, development sesi terakhir (7 hari kebelakang)
sudahkah anda cek, apakah development sudah dilakukan semua? apakah ada bug? cek dan evaluasi
terlebih dahulu"* — dengan arahan tambahan: **catat dulu jadi temuan, jangan langsung diperbaiki**.
Lingkup: Marketing + jurnal Pencairan (Finance). Gate `--full` TIDAK dijalankan (pilihan pemilik).

---

## 1. Yang DIUKUR dan TERBUKTI SEHAT

| Alat | Hasil |
|---|---|
| 12 gate yang menyentuh marketing (`verify_marketing_scope`, `verify_marketing_cycle`, `test_core_f6_rbac_scope`, `verify_katalog_stok`, `verify_margin_katalog`, `verify_pencairan_finance`, `verify_cogs_fifo_jurnal`, `verify_biaya_jahit_hpp_batch_impor_pintar`, `verify_kpi_konten_rapor_mingguan`, `verify_fase_d_dashboard_marketing`, `verify_sinkronisasi_marketing_gudang`, `verify_jembatan_retur_marketing_gudang`) | **12/12 HIJAU** (log: `.logs/audit_marketing_sesi40/`) |
| `scripts/audit_sesi40_impor_marketing.py` (BARU) — deteksi → unggah → pratinjau → commit → UNDO memakai **7 berkas ASLI pemilik** | 29 OK · 1 temuan (T-6) |
| `scripts/audit_sesi40_undo_fulfillment.py` (BARU) — jalur `update_only` (Ekspor B/C) + rollback | 17 OK · 1 catatan (T-7) |
| `_verify_f1_shop_guard.py` (penjaga gudang platform) | SEMUA PASS |
| `audit_marketing_integrity.py` | 0 rujukan cacat |
| Layar (Playwright, admin): Impor Data · Pencairan Toko · Manajemen Katalog · Siklus Target & Anggaran | render semua · **0 console error** |

Bukti perilaku penting yang memang benar:
* impor pesanan/penjualan harian **TIDAK melahirkan jurnal GL** (hanya Pencairan yang berjurnal);
* rekap harian turunan dihitung ulang **saat commit DAN saat rollback** (15 tanggal, Rp 3.128.910 → Rp 0);
* **pratinjau = hasil commit** (6 diperbarui · 1 ditolak, angka identik);
* jalur `update_only` yang diperbaiki sesi #38/#39 BEKERJA: 6 baris diperbarui → 6 jejak UNDO →
  rollback memulihkan 5 baris + 1 pesanan terminal (`cancelled`) dilaporkan sebagai "hanya field"
  beserta alasannya; 0 jejak UNDO menggantung; rollback kedua ditolak dengan pesan yang benar;
* status MUNDUR & menghidupkan pesanan batal **ditolak** dengan alasan yang menyebut risikonya
  (overselling), bukan diam-diam.

---

## 2. TEMUAN

### T-1 · P0 · **SELESAI (sesi #40)** · LAYAR — langkah 1 "Impor Data" KOSONG kalau tidak mengetik kata kunci
`frontend/src/components/erp/marketing/DataImportWizard.jsx`
* `groupKey` awal `''` dan **`setGroupKey` tidak pernah dipanggil**; tanpa kata pencarian
  `visibleTypes = types.filter(t => t.group_key === groupKey)` ⇒ **selalu kosong**.
* Layar menampilkan *"Tidak ada jenis data yang cocok dengan “”"* dan penghitung
  **"0 dari 22 jenis data"** (terbukti dari layar).
* Pemilih **6 kelompok** hasil sesi #37 tidak ada di render: `groups`/`setGroups` (baris 105)
  dideklarasikan tetapi tidak pernah diisi maupun dipakai; `GET /api/marketing/data-import/source-groups`
  **tidak dipanggil satu berkas pun di seluruh frontend**.
* Dampak: staf hanya bisa menemukan jenis impor dengan **mengetik** kata kunci (mengetik "pesanan"
  → 6 dari 22 muncul). Pintu masuk utama modul impor tampak rusak/kosong saat dibuka.

### T-2 · P0 · **SELESAI (sesi #40)** · FITUR SESI #34 TANPA PINTU — deteksi otomatis jenis & platform tidak dipakai layar
* Backend HIDUP dan TERBUKTI BENAR: `POST /api/marketing/data-import/detect` mengenali 6 dari 7
  berkas asli pemilik dengan tepat (skor 0,89–1,0; platform shopee/tiktok benar).
* Frontend **tidak pernah memanggilnya**: `setDetectRes` & `detectRanking` mati, tidak ada
  pemanggilan `/detect` di `frontend/src`.
* Ikut mati: tombol "tampilkan jenis usang" (`setShowDeprecated`, `hiddenInGroup`).
* Jadi janji sesi #34 ("sistem membaca berkas dulu lalu mengusulkan jenis") **belum ada di layar** —
  melanggar aturan repo "backend baru wajib punya pintu di layar".

### T-3 · P1 · **SELESAI (sesi #40, jurnal di-void + pencairan dihapus)** · UANG — pencairan UJI tertinggal di data nyata beserta jurnal yang SUDAH DIPOSTING
* `marketing_settlements`: `SET-TEST-001` · toko *Shopee Official Store DEMO* · dicairkan
  **Rp 8.000.000** · dibuat **2026-08-25 17:56** oleh `finance@dewiaditya.id`.
* `rahaza_journal_entries`: **JE-20260820-0001** `je_status=posted`, total debit **Rp 10.100.000**,
  `source_module=marketplace_settlement`, `source_ref=SET-TEST-001`.
* Terlihat di layar **Pencairan Marketplace** (KPI "Total dicairkan Rp 8.000.000 · 1 pencairan
  tercatat") dan masuk buku besar/neraca saldo.
* Perlu keputusan: void jurnal + hapus pencairan, atau diakui sebagai data demo yang sengaja ada.

### T-4 · P1 · **SELESAI (sesi #40, 559 pesanan di-rollback)** · DATA — 559 pesanan uji belum di-rollback
* Sesi impor `00c29756-1d26-4abb-a2f9-d1933a12d060` (`TikTok_UntukDikirim_2026-07-19.xlsx`,
  commit **2026-08-26 02:23**, status `committed`) menyisakan **559 pesanan** di
  *TikTok Outfit Boutique* — satu-satunya toko yang punya pesanan di DB saat ini.
* Akibatnya omzet/rekap harian toko itu seluruhnya berasal dari berkas uji.
* Sumbernya: `scripts/_verify_f4_health_after_import.py` yang gagal di tengah (lihat T-5) sehingga
  langkah bersih-bersihnya tidak menghapus apa pun (`rollback deleted=0`).

### T-5 · P2 · ALAT UJI BASI (bukan regresi produk)
* `_verify_f4_health_after_import.py` → **6 FAIL**. Dua sebab, keduanya di skripnya:
  1. tidak idempoten — mengharap `inserted == 559` padahal 559 pesanan itu sudah ada (T-4) sehingga
     `on_duplicate=skip` menjawab 0;
  2. memaku tanggal — skor kesehatan memang `None` karena `_recalculate_health_score`
     memakai **jendela 30 hari** sedangkan data contoh bertanggal 2026-07-04…19 (hari ini 2026-08-26).
     Jadi jawaban "Belum ada data" itu **BENAR**.
* `_verify_f2_import_lock.py` → 1 FAIL dengan sebab yang sama ("impor pesanan: 559 masuk").
  Kontrak yang diuji (omzet turunan tidak ditimpa berkas, 423 periode terkunci) semuanya PASS.

### T-6 · P2 · **SELESAI (sesi #40, panel deteksi memperingatkan)** · LAYAR — berkas 0 baris tetap diusulkan tanpa peringatan
`samples/marketplace_2026/retur_refund_shopee.xls` = 46 kolom, **0 baris data**. `/detect`
mengusulkan "Retur & Refund" skor 0,80 (`rows_readable: 0` ada di jawaban) tetapi tidak ada
peringatan; staf baru tahu di langkah unggah (`400 Berkas tidak punya baris data`).

### T-7 · INFO (perilaku BENAR, bukan bug)
Berkas retur asli (`retur_refund_tiktok.xlsx`) menolak 4/4 baris karena nomor pesanannya bukan
bagian dari ekspor pesanan yang ada. Penolakannya menyebut langkah perbaikan. Untuk menguji jalur
`update_only` secara jujur dibuat berkas Ekspor B/C **sintetis** dari nomor pesanan yang benar-benar
sudah diimpor (lihat §1).

---

## 3. Status eksekusi (2026-08-26, sesudah persetujuan pemilik)
**SELESAI:** T-1, T-2 (satu berkas `DataImportWizard.jsx` + 2× rebuild), T-3 & T-4 (dibersihkan lewat
pintu resmi: void jurnal → hapus pencairan → rollback impor), T-6 (peringatan berkas 0 baris).
Bonus yang ikut ditutup: pencairan yang jurnalnya sudah **void** tidak lagi terkunci
(`_je_still_binding`), dan gate INV-F6RBAC berhenti menuduh 2 endpoint bocor atas jawaban kosong.
Gate baru **INV-F45** (27 invarian) menjaga semuanya. Rincian: `memory/CHANGELOG.md` entri **[#40]**.

**Diverifikasi penguji independen** (`/app/test_reports/iteration_97.json`, 0 critical / 0 bug layar);
satu catatannya langsung ditutup: penghitung langkah 1 kini memakai SATU sumber angka
("21 jenis data dalam 6 kelompok · 1 usang disembunyikan"), cocok dengan jumlah badge kartu.
Backlog kecil dari penguji: filter toko layar Pencairan masih `<select>` HTML (tidak seragam dengan
komponen Select shadcn), dan sesi impor staging yang tidak dilanjutkan (92 dokumen) belum punya TTL.

**BELUM:** T-5 (dua verifier ad-hoc `_verify_f2/_f4` masih tidak idempoten & memaku tanggal —
bukan regresi produk).

## 4. Usulan urutan perbaikan (arsip rencana awal)
1. **T-1 + T-2 sekaligus** (satu berkas, satu rebuild): panggil `/source-groups`, render 6 kartu
   kelompok, sambungkan `/detect` (unggah dulu → usulan jenis berperingkat + banner salah-pilih +
   pratinjau tabel mentah), hidupkan tombol "jenis usang". Ini memulihkan janji sesi #34 & #37.
2. **T-3 & T-4**: keputusan pemilik dulu (void + hapus, atau biarkan sebagai demo), lalu eksekusi.
3. **T-5**: buat kedua verifier idempoten (bersihkan dulu) & memakai tanggal relatif.
4. **T-6**: `/detect` menandai `rows_readable == 0` sebagai peringatan keras di layar.

Alat yang dipakai audit ini (dipertahankan): `scripts/audit_sesi40_impor_marketing.py`,
`scripts/audit_sesi40_undo_fulfillment.py`, `.logs/run_marketing_gates.sh`.
