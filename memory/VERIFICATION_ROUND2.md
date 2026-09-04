# 🔎 VERIFICATION ROUND-2 — Laporan & History

**CV. Dewi Aditya ERP** · **Tanggal:** 2026-07-05/06 · **Mode:** DISCOVERY-ONLY (bug **TIDAK** diperbaiki, sesuai instruksi owner)
**Cakupan:** flow utama yang **CRITICAL** (akuntansi/jurnal, AR/AP, HR payroll/cuti, stok gudang, maklon PO, auth/RBAC, navigasi).

> Dokumen ini = **history** agar mudah dilanjutkan. Bug yang ditemukan **belum di-fix**; daftar aksi ada di §6.

---

## 1. Metodologi yang diadopsi (dari 2 repo referensi: `kn` + `travel`)
- **Matriks serangan A–L** (parity) → lihat `BUGHUNT_SOP.md` §2.1.
- **Bukti EMPIRIS** (`scripts/forensic_repro.py`): picu skenario nyata → cek STATE DB → verdict TERBUKTI/AMAN/SKIP + cleanup. Prinsip *"HTTP 200 ≠ benar"*.
- **Bukti COMPLETENESS** (`scripts/root_cause_matrix.py`): matriks numbering & numeric-bounds lintas SEMUA file (bukan spot-check).
- **Anti "HIJAU-PALSU"**: tiap guard baru dibuktikan bisa MERAH (self-test) sebelum dipercaya.
- **Effort/anti-underdelivery**: `verify_effort_quality.py` + `ANTI_UNDERDELIVERY_PROTOCOL.md` + `DEEP_ANALYSIS_PLAYBOOK.md`.
- **Autoritatif**: `testing_agent` (iterasi 55) untuk verifikasi dinamis flow kritis.

---

## 2. Ringkasan verdict

| Area (flow kritis) | Alat | Verdict | Bukti |
|---|---|---|---|
| Jurnal — penomoran RC-5 (race) | forensic_repro P1 + testing_agent | ✅ **AMAN** | 8 create paralel → 8 nomor UNIK, 0 dup, 0 5xx |
| Jurnal — invarian saldo/negatif | forensic_repro P2 + testing_agent | ✅ **AMAN** | tak-seimbang/negatif/non-numerik/<2 baris/akun-tak-ada/akun-grup → 400 |
| Jurnal — state machine | testing_agent | ✅ **AMAN** | re-post/void/delete posted → 400 (tak dobel reversal) |
| Auth/RBAC (endpoint sensitif) | testing_agent | ✅ **AMAN** | unauth GET journals/coa/payroll → 401 |
| Adversarial 5xx | testing_agent | ✅ **AMAN** | input hostile → 4xx, bukan 5xx |
| Gudang stok / Maklon PO / Payroll (reachability) | testing_agent | ✅ reachable | GET 200, tanpa crash |
| Navigasi IA v2 (Gudang/SDM/Marketing) | screenshot + testing_agent | ✅ **AMAN** | sidebar render, tanpa white-screen/console error, 0 ghost menu (INV-NAV-01 HIJAU) |
| Gate menyeluruh | `bash scripts/gate.sh` | ✅ **HIJAU** | receipt HIJAU dgn guard baru ter-wire |

**Tidak ada bug CRITICAL/blocking terbukti pada flow inti yang diprobe.** Namun **1 bug MED TERBUKTI** di luar inti: **BUG-NUM-1** — `POST /api/dewi/maklon/clients` menerima `standard_rate_per_pcs` **negatif** (HTTP 200, tersimpan −99999; positive control rate=5000→200). Ini instance nyata kelas INV-NUM-01. **Belum di-fix** (instruksi owner). Dicatat di `CONFIDENCE_TRACKER.md`.

---

## 3. Temuan STATIK (kandidat/risiko — bukan bukti bug runtime)

| Temuan | Alat | Jumlah | Sifat |
|---|---|---|---|
| **File RC-5 KANDIDAT** (setelah KALIBRASI anti-komentar) | root_cause_matrix | **1 file** (seed-only) | ⚠️ risiko rendah (non-konkuren) |
| **Field uang/kuantitas UNBOUNDED** (tanpa `ge=/gt=`) | verify_numeric_bounds (INV-NUM-01) | **134** | ⚠️ 1 TERBUKTI exploit, sisanya belum diprobe |
| `except…: pass` (telan error senyap) | verify_effort_quality | 84 | MED (advisory) |
| TODO/FIXME/console.log sisa | verify_effort_quality | 42 | LOW |
| Guardrail tak ter-wire | verify_guardrail_registry (INV-META) | 0 | ✅ semua ter-wire |
| FK yatim lintas-entity | verify_cross_entity | 0 diperiksa | ⚠️ perlu data ter-seed pada relasi tsb |

### KOREKSI PENTING — RC-5 setelah kalibrasi (kejujuran anti "hijau-palsu")
Deteksi awal `root_cause_matrix` menandai **8 file** RC-5. Setelah detektor dikalibrasi (buang teks komentar sebelum match), ternyata **7 dari 8 adalah FALSE-POSITIVE** — hanya komentar historis `# RC-5 fix: ... (was count_documents()+1)`; kodenya **sudah** pakai `gen_prefixed_number`/`next_counter` (atomik). **Hanya 1** pola `len()+1` asli tersisa: `production_seed_full.py:2620` (skrip seed, non-konkuren → risiko rendah). **Kesimpulan: RC-5 di jalur LIVE praktis BERSIH** — fix session lalu lebih tuntas dari dugaan awal.

---

## 4. Temuan dari testing_agent (iterasi 55) — koreksi harness (BUKAN bug aplikasi)
- AR/AP diprobe di path salah `/api/rahaza/ar/invoices` → path benar **`/api/rahaza/ar-invoices`** (hyphen). 404 = salah harness, bukan bug app.
- Leave requests `/api/rahaza/leave/requests` 404 → path perlu diverifikasi (kemungkinan beda penamaan).
- Portal cards di selector belum punya `data-testid` → auto-click sulit (nav manual sudah terverifikasi via screenshot). LOW.

---

## 5. HONEST ASSESSMENT (wajib)
- **Diuji & terbukti aman:** jurnal (numbering RC-5, saldo, negatif, state machine), auth/RBAC endpoint sensitif, adversarial→4xx, navigasi IA v2, gate menyeluruh.
- **BELUM diuji tuntas (jujur):**
  1. **8 file RC-5 kandidat** — belum diprobe paralel per-endpoint.
  2. **Write-path adversarial mendalam** untuk AR/AP, payroll run, material issue, maklon PO (baru reachability GET; belum probe create/negatif/paralel karena path/skema perlu dipetakan).
  3. **cross_entity** — relasi FK belum ada data ter-seed cukup untuk uji orphan.
  4. **134 field unbounded** — belum diuji satu per satu di runtime (statik saja).
  5. Pagination/query bounds (kelas K) — belum ada gate.
- **Confidence:** ~**80%** pada flow **inti akuntansi & auth** (kuat, empiris + dinamis). **Lebih rendah** pada AR/AP/HR/warehouse/maklon write-path (baru sebagian). Ini **minimum-known-bug**, **bukan** klaim zero-bug.
- **Mocked:** tidak ada yang di-mock pada round ini.

---

## 6. AKSI TERBUKA (belum dikerjakan — menunggu keputusan owner; TIDAK di-fix sesuai instruksi)
1. **[P1]** Triase + probe empiris 8 file RC-5 kandidat (§3). Bila terbukti → ganti ke `gen_prefixed_number`/`next_counter`.
2. **[P1]** Perluas `forensic_repro.py`: probe write-path AR/AP (path `-invoices`), payroll run, material issue (stok negatif), maklon PO (paralel numbering).
3. **[P2]** Tambah `Field(ge=0)` pada 134 field uang/qty → lalu naikkan INV-NUM-01 jadi blocking.
4. **[P2]** Seed relasi lalu jalankan `verify_cross_entity` untuk uji FK yatim nyata.
5. **[P3]** Tambah `data-testid` pada portal cards; gate pagination bounds (kelas K).

---

## 7. Artefak round ini
- Guardrail baru: `check_nav_map.py` (INV-NAV-01), `verify_numeric_bounds.py` (INV-NUM-01), `verify_cross_entity.py` (INV-CROSS-01), `verify_guardrail_registry.py` (INV-META-01), `verify_effort_quality.py` (INV-QUALITY-01), `health_check.py`.
- Alat forensik: `forensic_repro.py`, `root_cause_matrix.py`.
- Dokumen: `IA_BLUEPRINT.md`, `ANTI_UNDERDELIVERY_PROTOCOL.md`, `DEEP_ANALYSIS_PLAYBOOK.md`, `BUGHUNT_SOP.md` v1.2.0, `INVARIANTS.md` (§O–T).
- Laporan mesin: `test_reports/guardrails/*.json` (INV-NUM-01, INV-QUALITY-01, forensic_repro.json, root_cause_matrix.json), `test_reports/iteration_55.json` (testing_agent).
- Semua ter-wire di `scripts/gate.sh` → `bash scripts/guard.sh bughunt`.
