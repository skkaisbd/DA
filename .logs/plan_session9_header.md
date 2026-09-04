# SESI 2026-08-14 (#9) — **RENCANA & HASIL**: gate MERAH ditutup · retur terlihat · F6 · F10 · kualitas impor

> **Permintaan user:** *"lanjutkan development dari repo ini https://github.com/sakkajxxy/da — titik
> berhentinya: rebuild selesai, verifikasi layar impor bertindih HIJAU (panel 'sudah ada di sistem'
> = 1, 4 baris duplikat terdeteksi, 0 page error), tetapi `bash scripts/gate.sh` melaporkan
> **VERDICT: MERAH** padahal semua baris yang terlihat PASS."*

## 0) TITIK BERHENTI — DIUKUR, BUKAN DITEBAK

`/app` datang sebagai template kosong ⇒ repo diklon ulang + `rsync` (env platform dipertahankan) +
`scripts/bootstrap.sh`. Pod **restart di tengah `yarn build`** (gejala yang sama seperti sesi #8);
dipulihkan dengan `bootstrap.sh --skip-deps` ⇒ 6 akun login **HTTP 200**, bundel statis HTTP 200.

**Kenapa `grep FAIL` sesi lalu tidak menemukan apa pun:** `head -5` memotong keluaran; lima
kecocokan pertama adalah ringkasan INTERNAL skrip (`FAIL 0`), bukan baris gate. Baris yang benar
ada di `memory/GATE_RECEIPT.md`: **tepat satu gate FAIL**.

| Dugaan sesi lalu | Kenyataan |
|---|---|
| `INV-KPIIMPOR` gagal karena `reason` jadi WAJIB di sesi #8b | **SALAH** — `test_core_f7_kpi_impor.py` **40/40 PASS** |
| — | **`INV-MKTCYCLE` (`verify_marketing_cycle.py`) → `CYC-5c` GAGAL** |

### Cacat sesungguhnya (soal KEJUJURAN ANGKA, bukan tes yang cerewet)
`core/marketing_cycle._data_notes()` pada keadaan "belum ada pesanan per baris" hanya berbunyi
*"Marjin belum bisa dihitung: tidak ada pesanan per baris pada bulan ini"* — kata **HPP tidak pernah
muncul**. Akibatnya pembaca layar melihat **marjin 0%** tanpa pernah tahu SEBABNYA, dan "belum ada
dasar hitung" mudah dibaca sebagai "jualan tanpa untung". Catatan kejujuran sekarang menyebut HPP
terbuka: *"Marjin & HPP belum bisa dihitung … HPP hanya diketahui dari pesanan yang tertaut item
katalog — rekap yang diketik/diimpor per hari tidak membawa HPP."*

### Cacat kedua: environment segar melahirkan MERAH & layar kosong yang bukan salah produk
Empat seeder hanya hidup sebagai **perintah manual di HANDOFF**, jadi siapa pun yang cuma
menjalankan `bootstrap.sh` mendapat: 9 toko NYATA hilang (cuma 3 toko DEMO), `marketing_orders`
KOSONG ⇒ `CYC-8` di-SKIP, katalog tanpa varian internal ⇒ HPP tak punya dasar join. Keempatnya
sekarang **terdaftar di `scripts/bootstrap.sh`** (idempoten, lewat API resmi):
`seed_marketing_real_accounts.py --apply` · `seed_internal_variants.py` ·
`seed_katalog_order_demo.py` · `seed_marketing_cycle_demo.py`.

**BUKTI:** `bash scripts/gate.sh` → **25/25 · VERDICT HIJAU** (receipt: `memory/GATE_RECEIPT.md`).

## 1) KEPUTUSAN PEMILIK YANG DIAMBIL SESI INI

| Pertanyaan | Jawaban owner |
|---|---|
| Pesanan `returned` dikeluarkan dari omzet? | **Tampilkan DUA-DUANYA** — omzet bruto (tidak berubah) **dan** omzet setelah retur |
| Prioritas berikutnya | **Ketiganya**: F6 RBAC per toko + layar "siapa mengubah apa" · F10 konsolidasi layar marketing · kualitas impor bertindih |
| Berkas asli owner (Ekspor B/C, Settlement, `shop_kpi`, Shopee Orders) | belum ada ⇒ **F9 settlement TIDAK dimulai**, label "pemetaan belum diverifikasi" tetap dipasang |
| Cakupan uji | `gate.sh` cepat + `testing_agent_v3` per fitur |

## 2) URUTAN KERJA SESI INI

| Fase | Isi | Status |
|---|---|---|
| **0** | bring-up + `CYC-5c` ditutup + 4 seeder masuk bootstrap ⇒ gate HIJAU | ✅ SELESAI |
| **1** | **RETUR TERLIHAT** — satu kalkulator kanonik: `revenue_gross` (tetap) · `returned_amount` · `returned_orders` · `revenue_net_returns`; tampil di Siklus, Scorecard Kreator (+CSV), rekap harian/mingguan, Portal Manajemen; gate **INV-RETUR** membuktikan angka lama TIDAK bergeser | ⏳ |
| **2** | **F6** — `scope_filter`/`assert_account_visible` ke endpoint marketing yang masih unscoped + endpoint & **layar "Perubahan Marketing"** (filter toko/entitas/pelaku/tanggal, paginasi, CSV) + gate | ⏳ |
| **3** | **F10** — modul marketing KARTU-SAJA → tabel nyata (cari/sort/paginasi/CSV), diukur ulang `_audit_ui_tables_v2.py` | ⏳ |
| **4** | **Kualitas impor** — pratinjau "apa yang akan berubah" per baris sebelum commit (tanpa berkas owner) | ⏳ |

Aturan yang dipegang: satu rumus satu tempat (`core/marketing_cycle.py`, `core/marketing_daily_rollup.py`,
`core/order_status.py`) · setiap fitur baru wajib **layar + penjaga di `test_core_*` + entri gate** ·
setiap ubah `frontend/src` wajib `bash scripts/rebuild_frontend.sh` · gate hanya boleh menghapus
dokumen BERTANDA gate.

---

