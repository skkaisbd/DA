# 📊 CONFIDENCE TRACKER — "Zero-Bug" Confidence

**CV. Dewi Aditya ERP** · Tujuan: melacak **keyakinan bahwa SELURUH code flow / menu / logic sudah benar & bebas bug.**
`100%` = yakin penuh tak ada bug di semua alur. `0%` = belum terverifikasi sama sekali.

> Angka ini **jujur & konservatif**: berbasis BUKTI (gate/forensic/testing_agent), bukan perasaan.
> Diperbarui tiap round verifikasi. Turun bila bug baru terbukti; naik bila surface diverifikasi bersih.

---

## 🔢 SKOR SAAT INI: **95%**  _(Round-10, 2026-07-06 — Concurrency/TOCTOU hardening)_

> **⬆️ 93% → 95%**: R10 menutup **kelas kerentanan TOCTOU/race** pada 4 write-path bernilai-tinggi dengan **atomic conditional update** (MongoDB), lalu dibuktikan paralel (CC3–CC6) + regresi sekuensial + testing_agent + gate HIJAU.
> - **AR/AP payment** (`/ar-invoices/{id}/payment`, `/ap-invoices/{id}/payment`): read-then-`$set` → **`find_one_and_update` dgn `$expr` guard overpay+status + pipeline recompute** paid/balance/status. 6 full-pay paralel → **tepat 1×200, tak overpay, 0×5xx** (CC3). Sekuensial (partial→lunas→overpay 400) tetap benar.
> - **Asset assign/return** (`/dewi/assets/{id}/assign|return`): read-status→insert → **atomic claim** `Available→Assigned` / `active→returned`. 6 assign paralel → **tepat 1 assignment aktif** (no double-assign, CC4).
> - **Material reserve** (`/materials/reserve`): read-availability→insert → **optimistic insert + verifikasi kumulatif deterministik + self-rollback**. 6 reserve paralel → **`sum(active_reserved) ≤ stock`** (no over-allocation, CC5).
> - **Stock adjust** (`/wms/stock/unified/adjust`): read→hitung→`$set` → **`find_one_and_update` dgn `$expr` guard non-negatif + pipeline `$add`**. 6 decrease paralel → **qty tak negatif & tak lost-update** (CC6).
> - **Bukti**: `verify_concurrency.py` kini **CC1–CC6 (FAIL 0)** & jadi gate permanen; testing_agent **34/34 PASS**; **gate.sh HIJAU 9/9**; **DB pristine (0 residual)**; **0 bug baru** (hardening, bukan bug sekuensial).
> **Sisa ~5% (bukan bug uang/ras):** kedalaman modul reporting/control-tower belum di-probe dalam; refactor `HRKPIModule.jsx` (~1950 baris); QC belum validasi `qty_inspected ≤ qty order`. Menembus **96%+** butuh probing reporting/control-tower.

<details><summary>R9 (93%) — QC + rework + double-allocation</summary>

> **⬆️ 92% → 93%**: R9 menutup celah QC & mengonfirmasi anti-double-allocation.
> - **Maklon QC**: ditemukan **R9-BUG-1** (qty_passed+rejected+rework bisa MELEBIHI qty_inspected → data QC korup) → **FIXED** (guard `_assert_qty_consistency` di create+update; verified over-count→400, valid→200).
> - **Rework** (`/rework/bundle/{bid}/close-manual`): **SAFE** — double-close di-guard (`status!=reworking`), `writeoff_qty` di-clamp `[0, qty_fail]`.
> - **Double-allocation SAFE**: aset (double-assign→400, hanya 1 active), material reserve (`available = stock − active_reserved` → over-reservasi ditolak).
> - **Gate HIJAU 9/9. DB pristine.**
</details>

### Rubrik berbobot (per dimensi) — v8 (R10: concurrency/TOCTOU hardening)
| # | Dimensi | Bobot | Skor | Kontribusi | Basis bukti |
|---|---|---:|---:|---:|---|
| 1 | Menu / IA / Navigasi | 8% | 90% | 7.2 | INV-NAV-01 HIJAU + self-test + screenshot |
| 2 | Auth & RBAC (breadth) | 12% | 92% | 11.04 | sweep semua endpoint; RBAC gate PASS; publik-by-design dikonfirmasi owner |
| 3 | Finance core (Jurnal/GL) | 10% | 95% | 9.5 | numbering/saldo/state AMAN; **payment atomik race-safe (CC3)**; gate state+concurrency+data-integrity PASS |
| 4 | AR / AP | 6% | 98% | 5.88 | BUG-NUM-2/3/4 FIXED; **AR/AP payment atomic (no overpay/no lost-update di balapan — CC3, 34/34 agent)** |
| 5 | HR Payroll / Cuti | 6% | 92% | 5.52 | payroll state-machine ALL SAFE @total_net>0; leave overlap FIXED |
| 6 | Warehouse / Stok | 6% | 97% | 5.82 | receiving FIXED; OPNAME2 SAFE; **stock adjust atomic (no negatif/lost-update — CC6)** |
| 7 | Maklon | 5% | 94% | 4.7 | BUG-NUM-1 FIXED; PO validasi SAFE; QC consistency FIXED (R9-BUG-1); rework SAFE |
| 8 | Numeric bounds (global) | 10% | 93% | 9.3 | 134→1; runtime-verified lintas finance/maklon/marketing/cutting/finishing |
| 9 | Cross-entity / alokasi | 6% | 98% | 5.88 | INV-CROSS-01 HIJAU; **asset assign + material reserve race-safe (no double-assign/over-alloc — CC4/CC5)** |
| 10 | Robustness 5xx (breadth) | 12% | 95% | 11.4 | 932/934 GET non-5xx; adversarial gate PASS; **0×5xx di 4 write-path uang di bawah balapan N=6** |
| 11 | Code quality | 5% | 92% | 4.6 | INV-QUALITY-01 = 0 (except:pass/print/console.log/TODO bersih) |
| 12 | Write-path depth (global) | 14% | 99% | 13.86 | cutting/finishing/QC state-machine FIXED; **4 write-path bernilai-tinggi TOCTOU-hardened + terbukti paralel (CC3–CC6)** |
| | **TOTAL** | **100%** | | **≈ 95%** | |

---

## 📉 Kenapa belum tinggi (faktor penekan utama)
1. **1 bug TERBUKTI** (numeric bound, maklon rate negatif) + **134 field unbounded** belum ditutup → dimensi #7/#8 rendah.
2. **Surface luas belum diuji dalam**: AR/AP, HR payroll, warehouse, maklon baru diuji *reachability* (GET 200), belum *write-path adversarial* (create/paralel/negatif). 314 file route, mayoritas belum disentuh uji perilaku.
3. **cross-entity** belum bisa diuji (data relasi belum ter-seed cukup).

## 📈 Faktor penopang (kenapa tidak rendah)
- Inti **akuntansi jurnal & auth/RBAC & navigasi** terverifikasi kuat (empiris + dinamis).
- **RC-5 (penomoran) praktis BERSIH** di jalur live (setelah kalibrasi: 8 "kandidat" → 7 false-positive komentar, 1 sisa hanya di skrip seed non-konkuren).
- Gate menyeluruh **HIJAU** + guard baru **self-test-proven** (bukan hijau-palsu).

---

## 🧭 Proyeksi kenaikan (bila aksi dikerjakan — belum dilakukan)
| Aksi | Dimensi terdampak | Estimasi Δ |
|---|---|---:|
| Tutup 134 field unbounded (`Field(ge=0)`) + jadikan INV-NUM-01 blocking, verifikasi testing_agent | #7, #8, #10 | **+10–12%** |
| Perluas forensic_repro + testing_agent ke write-path AR/AP, payroll, material-issue, maklon PO (adversarial+paralel) | #4, #5, #6, #7 | **+12–15%** |
| Seed relasi + jalankan cross_entity bersih | #9 | **+4%** |
| Bereskan 84 `except:pass` kritikal + coverage-matrix endpoint | #11, #2 | **+5%** |
| **Target realistis setelah semua di atas** | | **≈ 90–92%** |

> Catatan: mencapai **100%** murni ~mustahil untuk sistem sebesar ini (314 route) tanpa coverage uji menyeluruh + waktu; 90–92% = "sangat yakin, risiko sisa terdokumentasi".

---

## 🗂️ HISTORY (append tiap round)
| Round | Tanggal | Skor | Perubahan utama | Bug terbukti (kumulatif) |
|---|---|---:|---|---|
| R2 | 2026-07-06 | 62% | Baseline tracker. IA v2 diverifikasi. RC-5 dikalibrasi (bersih di live). Adopsi guardrail A–L + forensic tools. **BUG-NUM-1** terbukti. | 1 |
| R3 | 2026-07-06 | 66% | **Coverage menyeluruh**: sweep 1.679/2.084 endpoint (80,6%) auth+5xx nyaris bersih. | 1 |
| R4 | 2026-07-06 | **62%** | **Deep write-path**: testing_agent probe AR/AP/payroll/stok/maklon/discount. **3 bug baru TERBUKTI** (BUG-NUM-2/3/4). SAFE: AR overpayment/negatif-payment guard, Maklon PO validasi. Skor jujur TURUN. | **4** |
| R5 | 2026-07-06 | **63%** | **Cross-entity + data hygiene**: INV-CROSS-01 HIJAU (0 orphan) setelah **purge artefak R4** (cleanup R4 tak-lengkap: 8 invoice test korup + 1 orphan PO + 1 customer test). Payroll create menolak employee tak-ada (SAFE). **0 bug baru.** Cakupan write-path HR/gudang/opname/accessories TERBATAS (DB kosong data operasional). Ceiling verifikasi-only ≈68–72% dikonfirmasi. | **4** |
| R6 | 2026-07-06 | **85%** | **FASE FIX (diotorisasi owner)**: BUG-NUM-1/2/3/4 **DITUTUP**, **134→1** field ter-bound (`Field(ge=0)` + validator), **NEW-BUG-2/3** (warehouse receiving negatif) ditemukan+FIXED. Verifikasi 3-lapis (harness 14/14 + agent 15/15 + gate INV-MONEY-01). NEW-BUG-1 (payroll double-pay) & NEW-BUG-4 (opname 404) = **FALSE POSITIVE** (RCA di bawah). Gate HIJAU 9/9. **CAP dicabut.** | **0 OPEN** (6 fixed) |
| R7 | 2026-07-06 | **91%** | **Deep coverage + quality**: payroll state-machine `total_net>0` **ALL SAFE**; **NEW-BUG-5 (overlapping leave) FIXED**; write-path produksi/marketing bounds→422 verified; **106 `except:pass`→0** (refactor massal); cross-entity HIJAU. Gate HIJAU 9/9. **Target >90% tercapai.** | **0 OPEN** (7 fixed) |
| R8 | 2026-07-06 | **92%** | **Produksi + opname2 + quality**: **OPNAME2 state-machine SAFE**; **4 bug produksi FIXED** (cutting reject-after-approve, cutting status mundur, finishing qty negatif, finishing progress after-shipped); **42 LOW quality → 0** (console.log/print/TODO bersih). Gate HIJAU 9/9. DB pristine. | **0 OPEN** (11 fixed) |
| R9 | 2026-07-06 | **93%** | **QC + rework + double-allocation**: **R9-BUG-1 (QC qty over-count) FIXED**; rework SAFE (double-close guard + writeoff clamp); double-allocation SAFE (asset double-assign→400, material reserve available=stock−reserved). Gate HIJAU 9/9. DB pristine. | **0 OPEN** (12 fixed) |
| R10 | 2026-07-06 | **95%** | **Concurrency/TOCTOU hardening (4 write-path)**: AR/AP payment, asset assign/return, material reserve, stock adjust → **atomic conditional update** (`find_one_and_update` + `$expr` guard + pipeline / optimistic-insert+deterministic-rollback). Bukti: **CC3–CC6** ditambahkan ke `verify_concurrency.py` (FAIL 0), testing_agent **34/34 PASS**, regresi sekuensial 12/12, **gate HIJAU 9/9**, **DB pristine**. **0 bug baru** (hardening). | **0 OPEN** (12 fixed) |

### 🧹 DATA HYGIENE (R5–R6 — sudah dibereskan + dicegah berulang)
Cleanup Round-4 **TIDAK tuntas** → menyisakan polusi test di DB live (8 invoice test korup, 1 orphan PO, 1 customer test). **Semua dipurge di R5.**
**R6:** ditemukan sumber polusi berulang → gate `verify_adversarial_5xx.py` **membuat** AP invoice adversarial tapi tak membersihkannya. **Diperbaiki: gate kini auto-cleanup** artefaknya (vendor `WEIRD/adv`, `ADV-5XX*`, dll). Verifikasi akhir: **0 AR/AP/customer/PO/client** tersisa, 0 negatif, 0 oversized, INV-CROSS-01 HIJAU.
> **Pelajaran (ditegakkan): harness adversarial WAJIB cleanup deterministik + verifikasi 0-residual.**

### ✅ Daftar bug — STATUS FINAL (pasca-FIX R6)
| ID | Endpoint | Deskripsi | Sev | Status |
|---|---|---|---|---|
| BUG-NUM-2 | `POST /api/rahaza/ar-invoices` | qty/price/tax_pct negatif & discount>total → total negatif | CRITICAL | ✅ **FIXED** (guard `_norm_invoice_items` + `_validate_tax_discount`; verified 400) |
| BUG-NUM-4 | `POST /api/rahaza/ap-invoices` | amount negatif → total AP negatif | CRITICAL | ✅ **FIXED** (guard qty/price ≥0; verified 400) |
| BUG-NUM-3 | `POST /api/rahaza/ar-invoices/{id}/payment` (+AP) | bayar invoice cancelled/void/written_off | HIGH | ✅ **FIXED** (state-machine guard; verified 400) |
| BUG-NUM-1 | `POST /api/dewi/maklon/clients` | `standard_rate_per_pcs` negatif | MED | ✅ **FIXED** (`Field(ge=0)`; verified 422) |
| NEW-BUG-2 | `POST /api/warehouse/receiving` | `received_qty` negatif diterima | HIGH | ✅ **FIXED** (guard non-negatif item; verified 400) |
| NEW-BUG-3 | `POST /api/warehouse/receiving` | `unit_price/unit_cost` negatif diterima | HIGH | ✅ **FIXED** (guard non-negatif; verified 400) |
| NEW-BUG-5 | `POST /api/rahaza/leaves/request` | pengajuan cuti **tumpang-tindih** diterima (200) | MED (konflik jadwal/saldo) | ✅ **FIXED** (guard overlap; verified overlap→400, non-overlap→200) |
| R8-BUG-1 | `PUT /api/dewi/cutting/requests/{id}/reject` | reject request yang sudah approved (transisi ilegal) | HIGH | ✅ **FIXED** (guard status=pending_approval; verified 400) |
| R8-BUG-2 | `PUT /api/dewi/cutting/batches/{id}/status` | transisi status **mundur** (cut_done→in_cutting) | HIGH | ✅ **FIXED** (forward-only guard; verified 400) |
| R8-BUG-3 | `POST /api/finishing/batches/{id}/progress` | qty **negatif** diterima & tersimpan | CRITICAL | ✅ **FIXED** (guard qty≥0 + non-numeric; verified 400) |
| R8-BUG-4 | `POST /api/finishing/batches/{id}/progress` | progress setelah batch **shipped/final** | HIGH | ✅ **FIXED** (guard shipped_at/status terminal; verified 400) |
| R9-BUG-1 | `POST/PUT /api/dewi/maklon/qc` | qty_passed+rejected+rework bisa **melebihi** qty_inspected (data QC korup) | MED (integritas data QC/reject-rate) | ✅ **FIXED** (guard `_assert_qty_consistency`; verified over→400, valid→200) |

### 🟡 FALSE POSITIVE (R6 — di-RCA, bukan bug)
- **NEW-BUG-1** payroll `POST /payroll-runs/{id}/pay` "double pay": posting **idempotent** via `source_ref=payrollpay:{id}` (JE kedua tak dibuat → tak ada double-disbursement). "200/200" muncul karena run seed minimal `total_net=0` → posting `ok:False` (status `payment_error`, bukan `paid`) → retry lolos & tetap 200. **Bukan kerentanan finansial.**
- **NEW-BUG-4** opname `complete → 404`: path `/api/warehouse/opname/{id}/complete` **tidak ada** (opname `/complete` di `/api/wms/opname2/*`). 404 = path salah harness (router `wms_opname` deprecated).
- Unified-stock "Infinity" → transport error sisi klien (Infinity bukan JSON valid); "huge value" → **422 (aman)**.

### 133 field bounds — ter-tutup
`verify_numeric_bounds` (INV-NUM-01): **134 → 1**. Sisa 1 = `OrderStatusIn.stage_qty_update: Dict[str,int]` yang **dilindungi `field_validator`** (guard statik tak deteksi validator). Runtime-verified: maklon client & catalog item negatif → 422.

### 🎯 Status target — 95% (R10 TERCAPAI). Sisa ~5% (kedalaman, bukan bug terbukti):
- ✅ **Race TOCTOU DITUTUP (R10)** pada AR/AP payment, assign aset, reserve material, stock adjust: kini **atomic conditional update** (state/qty/paid dipindah ke filter `$expr` + `find_one_and_update`/pipeline; reserve pakai optimistic-insert + rollback deterministik). Terbukti paralel (CC3–CC6, N=6) & jadi gate permanen.
- Kedalaman modul reporting/control-tower belum di-probe dalam & refactor `HRKPIModule.jsx` (~1950 baris).
- QC belum validasi `qty_inspected <= qty diproduksi order` (butuh join ke order qty).
> **12 bug DITUTUP & terverifikasi** lintas R6–R9 + **kelas TOCTOU di-hardening (R10)**. Menembus **96%+** butuh probing modul reporting/control-tower (kedalaman), bukan lagi concurrency.

### By-design (dikonfirmasi owner — bukan bug)
- AUTH-OPEN GET: `/api/metrics`, `/api/tv/*`. WRITE tanpa token: `/api/marketing/webhooks/*` (verifikasi signature). `GET /api/push/vapid-public-key → 503` graceful.

---

## Cara update tracker (agar konsisten)
1. Jalankan round verifikasi (gate + forensic_repro + testing_agent) untuk dimensi target.
2. Sesuaikan skor dimensi berdasar BUKTI (naik bila bersih, turun bila bug terbukti).
3. Hitung ulang total berbobot → tambah baris di HISTORY + daftar bug.
4. Bug terbukti WAJIB masuk daftar; jangan naikkan skor tanpa bukti (anti "hijau-palsu").
