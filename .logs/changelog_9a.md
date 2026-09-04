# [2026-08-14 #9a] **RETUR TERLIHAT** — omzet bruto vs omzet setelah retur (+ gate MERAH ditutup)

## 1. Gate MERAH di titik berhenti sesi lalu — penyebab SEBENARNYA

Receipt hanya punya SATU gate FAIL, dan bukan yang diduga (`INV-KPIIMPOR` justru **40/40 PASS**).
Yang gagal: **`INV-MKTCYCLE` → `CYC-5c`** ("catatan kejujuran data menyebut HPP secara terbuka").

**Cacat produknya nyata, bukan tes cerewet.** `core/marketing_cycle._data_notes()` pada keadaan
"belum ada pesanan per baris" hanya berbunyi *"Marjin belum bisa dihitung…"* — kata **HPP tidak
pernah muncul**, jadi pembaca layar melihat **marjin 0%** tanpa pernah tahu SEBABNYA ("belum ada
dasar hitung" mudah dibaca sebagai "jualan tanpa untung"). Sekarang catatannya menyebut HPP terbuka
beserta alasannya (HPP hanya diketahui dari pesanan yang tertaut item katalog).

**Cacat kedua: environment segar melahirkan MERAH & layar kosong yang bukan salah produk.** Empat
seeder hanya hidup sebagai perintah manual di HANDOFF ⇒ `bootstrap.sh` saja menghasilkan 3 toko DEMO
(9 toko NYATA hilang), `marketing_orders` KOSONG (⇒ `CYC-8` di-SKIP), katalog tanpa varian internal.
Keempatnya kini terdaftar di `scripts/bootstrap.sh`: `seed_marketing_real_accounts.py --apply` ·
`seed_internal_variants.py` · `seed_katalog_order_demo.py` · `seed_marketing_cycle_demo.py`.

## 2. KEPUTUSAN PEMILIK: tampilkan DUA angka omzet (bukan menggeser yang lama)

> *"Pesanan retur — tampilkan dua-duanya: omzet bruto & omzet setelah retur, tanpa mengubah angka
> lama."*

    omzet bruto = definisi LAMA (semua status kecuali `cancelled`; retur IKUT)   ← TIDAK BERUBAH
    nilai retur = Σ pesanan berstatus `returned`                                  ← BARU
    omzet net   = bruto − nilai retur                                             ← BARU

Target, capaian, pace, ROAS, dan seluruh lampiran rapat yang sudah beredar **tetap** memakai bruto.

### Satu kalkulator: `backend/core/marketing_returns.py` (BARU)
`split_from_orders()` (dari pesanan) · `from_daily_rows()` (dari rekap harian) · `resolve()`
(pilih basis toko lalu hitung net & persen) · `evaluate_flags()` (`returns_high` kuning ≥5% / merah
≥10%) · `data_note()` · `rp()`. Tiga hal yang dijaga di dalamnya:
* **dua basis uang tidak boleh tertukar** — nilai retur disimpan pada basis *omzet produk* DAN
  *order amount*; mengurangi order amount retur dari omzet produk memberi net terlalu kecil;
* **cakupan jujur** — retur hanya diketahui dari pesanan per baris. Hari yang rekapnya
  DIIMPOR/DIKETIK dilaporkan **belum diketahui**, bukan "0 retur";
* **rumus retur kedua dilarang** — dua pembaca lama memakai `revenue_product` dengan cadangan
  `revenue` yang dibaca langsung dari dokumen ⇒ **Rp 0** untuk pesanan yang diinput staf lewat layar.
  Laporan mingguan sekarang memakai pembaca kanonik.

### Yang berubah
| Berkas | Perubahan |
|---|---|
| `core/marketing_returns.py` | **BARU** — satu-satunya kalkulator retur |
| `core/marketing_sales_shape.py` | grup `fulfillment` + `returned_revenue_product`, `returned_units` (+ label & daftar field turunan) |
| `core/marketing_daily_rollup.py` | `summarize_orders` menulis nilai retur pada kedua basis lewat kalkulator |
| `core/marketing_cycle.py` | `actual_from_daily` membawa `returns_split` · `cycle_summary.actual` + `revenue_gross`/`returned_amount`/`returned_orders`/`returned_units`/`revenue_net_returns`/`returns_pct` · blok `returns` (label + cakupan) · flag `returns_high` · catatan retur SELALU ada · `cycle_overview.totals` + total retur & net · **`CYC-5c` ditutup** |
| `core/marketing_weekly_report.py` | pembaca kanonik + `nilai_retur`/`pcs_retur`/`omzet_setelah_retur`/`retur_persen` per toko & gabungan + catatan |
| `routes/marketing_targets.py` | scorecard & rincian kreator: bruto · retur · setelah retur; catatan "PERLU KEPUTUSAN PEMILIK" **diganti** keputusan yang diambil |
| `utils/marketing_weekly_export.py` | Excel: 2 kolom retur di UJUNG (tidak menggeser indeks baris GABUNGAN) · PDF: kartu "SETELAH RETUR" |
| `CycleView.jsx` | kartu KPI `cycle-kpi-returns` · 2 kolom tabel · blok `cycle-detail-returns` di dialog · tampilan kartu · CSV |
| `CreatorScorecardView.jsx` | kolom Retur & Pesanan setelah retur · KPI `scorecard-kpi-returns` · kartu "Setelah retur" di dialog rincian · CSV |
| `WeeklyMeetingReportModule.jsx` | tile `weekly-tile-setelah-retur` + 2 kolom tabel (per toko & gabungan) |
| `backend/scripts/backfill_returns_daily.py` | **BARU** — mengisi nilai retur produk pada rekap harian turunan yang lahir sebelum sesi ini (idempoten, lewat mesin rekap yang sama) |
| `backend/scripts/seed_marketing_returns_demo.py` | **BARU** — membuat keadaan retur lewat SSOT status (reservasi dilepas) supaya fitur tidak tampak "belum jadi" di environment segar; didaftarkan di `bootstrap.sh` |
| `backend/scripts/seed_marketing_creator_demo.py` | jaring pengaman: bila tidak ada pesanan `DEMO-A-`, tautkan sebagian pesanan yang ADA (termasuk yang retur) ke kreator #1 — bertanda `_seed_creator_link` |
| `test_core_returns_visibility.py` · `scripts/gate.sh` | **51 penjaga baru** + gate **INV-RETUR** |

## 3. BUKTI

* `python3 test_core_returns_visibility.py` → **51/51 PASS**.
* **Dibuktikan MERAH (5 temuan)** saat net disabotase menjadi `net = bruto` ⇒ dipulihkan ⇒ 51/51.
* `bash scripts/gate.sh` → **26/26 · VERDICT HIJAU** (`memory/GATE_RECEIPT.md`).
* Layar (Playwright, bundel statis baru), **0 page error**: Siklus Jul 2026 ⇒ Omzet produk
  **Rp 59.783.811 TIDAK berubah** · kartu "Setelah retur" **Rp 57.561.529** · sel tabel
  `cycle-returned-TIKTOK-OUTFIT` = **Rp 2.222.282 · 6 pesanan** (−3,7%).
* `testing_agent_v3` (iterasi 10): **22/22 lulus · 0 bug** — 8 user story + 6 uji API + regresi 8 tab.

## 4. YANG TIDAK DIKERJAKAN (jujur)

* **F9 Settlement TIDAK dimulai** — berkas Pencairan/Settlement asli dari owner belum ada, jadi
  potongan platform (komisi/biaya) tetap di luar angka omzet. Label "sebelum potongan platform"
  dipertahankan di semua layar.
* Label **"pemetaan belum diverifikasi"** pada impor Ekspor B/C tetap dipasang (masih menunggu
  berkas ASLI dari owner).
* `returned` **tetap** dihitung di bruto — itu keputusan pemilik, bukan kelalaian. Kalau nanti
  diminta keluar dari omzet, itu kartu kerja sendiri (menyentuh F2 + F5 + F7.4) dan gate-nya harus
  dibalik: bukti bahwa angka historis MEMANG berubah + laporan migrasinya.

---

