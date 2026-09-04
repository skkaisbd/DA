# 🕵️ BUGHUNT SOP — Prosedur Bug-Hunting Berulang & Berkembang
**CV. Dewi Aditya ERP — Ekosistem Guardrails**

> **Versi:** 1.1.0  **Diperbarui:** 2026-07-05  **Pemilik:** Tim Engineering
> SOP ini WAJIB dijalankan sebelum klaim “selesai” untuk perubahan non-trivial.
> Tujuannya menghapus pengalaman menyakitkan vibe-coding: *“semua terlihat baik-baik saja”
> padahal tidak. Setiap “sambungan” **diverifikasi, bukan diasumsikan.**

---

## 0. Filosofi (kenapa SOP ini ada)

Bug paling mahal BUKAN yang bikin merah/500 — tapi yang **HIJAU-tapi-rusak**: HTTP 200,
tak ada error, tapi tabel kosong / uang salah / data bocor. AI (dan manusia) cenderung
berhenti di lapisan luar (“endpoint mengembalikan 200 → beres”). SOP ini memaksa bukti
berlapis: **statik → kontrak → runtime → integritas → adversarial → mutation → effort**.

Aturan emas: **SKIP ≠ PASS.** Klaim tanpa GATE_RECEIPT HIJAU = tidak sah.

---

## 1. Satu perintah (TL;DR)

```bash
cd /app
bash scripts/guard.sh bughunt        # jalankan SELURUH SOP (preflight + gate + meta)
# atau bertahap:
bash scripts/guard.sh preflight      # PRA-dev (statik, tanpa backend)
bash scripts/guard.sh gate           # POST-dev (integrity/state/concurrency/adversarial + advisory)
bash scripts/guard.sh meta           # mutation-test + effort-gate
bash scripts/guard.sh bughunt --strict   # mode blok penuh (untuk CI / rilis)
```

Bukti tertulis: `memory/GATE_RECEIPT.md` (verdict) + `test_reports/guardrails/*.json` (detail).

---

## 2. Peta ekosistem (apa memeriksa apa)

### Lapis PRA-DEVELOPMENT (persiapan, pemetaan, aturan) — statik, cepat, tanpa backend
| Gate | File | Menangkap |
|---|---|---|
| Kontrak FE↔BE | `scripts/preflight/verify_fe_be_contract.py` | duplicate route (blok), FE manggil endpoint hantu (404 senyap), orphan BE |
| Anti-pola statik | `scripts/guardrails/verify_static_antipatterns.py` | RC-5 `count_documents()+1`, koersi `float(body)` tak-guard, datetime naive, `except:` |
| Auth coverage | `scripts/guardrails/verify_auth_coverage.py` | endpoint tanpa penegakan auth |
| Integritas nav (INV-NAV-01) | `scripts/guardrails/check_nav_map.py` | section 1-item (MECE), menu ghost (id tak ada di registry), moduleId duplikat, depth>4 |
| Numeric bounds (INV-NUM-01) | `scripts/guardrails/verify_numeric_bounds.py` | field uang/qty Pydantic tanpa `ge=/gt=` (terima negatif/absurd) |
| Effort quality (INV-QUALITY-01) | `scripts/guardrails/verify_effort_quality.py` | `NotImplementedError` di router, `except:pass`, rahasia/URL hardcoded |

### Lapis POST-DEVELOPMENT (pengujian, gate pass) — runtime + DB
| Gate | File | Menangkap |
|---|---|---|
| Data integrity | `scripts/verify_data_integrity.py` | invarian GL/STK/AR/AP/CNT/LEAVE/WO/NUM (green-but-broken) |
| State machine | `scripts/verify_state_machine.py` | transisi menyimpang (double post/void, tak seimbang) |
| Concurrency | `scripts/verify_concurrency.py` | RC-5 TOCTOU live (CC1) + regresi statik unique-index (CC2) |
| Adversarial 5xx | `scripts/guardrails/verify_adversarial_5xx.py` | input hostile harus 4xx bukan 5xx |
| RBAC / IDOR | `scripts/guardrails/verify_rbac_idor.py` | unauth GET → 200; eskalasi lintas-role → 200 |
| Cross-entity (INV-CROSS-01) | `scripts/guardrails/verify_cross_entity.py` | FK yatim (journal_line→entry/COA, AR→customer, WO→order, maklon PO→client) |
| Health check (HEALTH-01) | `scripts/health_check.py` | `/api/health` + login + endpoint inti tak 5xx |

### Lapis FORENSIK (pembuktian empiris & bukti completeness) — dikembangkan dari repo referensi
| Alat | File | Fungsi |
|---|---|---|
| Forensic repro | `scripts/forensic_repro.py` | PICU skenario nyata (N jurnal paralel / tak-seimbang / negatif) → cek STATE DB → verdict **TERBUKTI-BUG / AMAN / SKIP** + cleanup. "200 ≠ benar". |
| Root-cause matrix | `scripts/root_cause_matrix.py` | Bukti COMPLETENESS: matriks setiap file×penomoran atomik vs `count+1`; ringkasan field uang/qty bounded vs unbounded. |
| Endpoint sweep (coverage) | `scripts/audit_endpoint_sweep.py` | Sapu SELURUH endpoint via OpenAPI (2.084): probe auth+5xx pada semua GET + auth pada tulis (skip destruktif/DELETE). Beri **denominator coverage** untuk `CONFIDENCE_TRACKER.md`. |

### Lapis META (menguji mutu gate & mutu kerja AI)
| Gate | File | Menangkap |
|---|---|---|
| Mutation test | `scripts/meta/mutation_test.py` | apakah gate BENAR menangkap korupsi (SURVIVED = blind spot gate) |
| Effort gate | `scripts/meta/effort_gate.py` | respons AI low-effort (lihat `AI_QUALITY_CONTRACT.md`) |
| Guardrail registry (INV-META-01) | `scripts/guardrails/verify_guardrail_registry.py` | guardrail yang TAK ter-wire di `gate.sh` (cegah perlindungan mati diam-diam / "HIJAU-PALSU") |

---

## 2.1 Matriks Serangan A–L (parity metodologi repo referensi) + status coverage

| Kelas | Serangan | Gate/alat di proyek ini | Status |
|---|---|---|---|
| A | Auth bypass | `verify_auth_coverage` (INV-AUTH-01) | ✅ |
| B | RBAC / IDOR | `verify_rbac_idor` (INV-RBAC-01, BLOCKING) | ✅ |
| C | 5xx adversarial | `verify_adversarial_5xx` (INV-5XX-01) | ✅ |
| D | Boundary / numeric | `verify_numeric_bounds` (INV-NUM-01) | ✅ (baru — advisory) |
| E | Race / TOCTOU | `verify_concurrency` + `forensic_repro` P1 | ✅ |
| F | State-machine | `verify_state_machine` | ✅ |
| G | Idempotency | `verify_concurrency` / state_machine | ✅ |
| H | Cross-entity | `verify_cross_entity` (INV-CROSS-01) | ✅ (baru — advisory) |
| I | Injection / markup | `verify_adversarial_5xx` | ✅ |
| J | Empty / oversized | `verify_adversarial_5xx` | ✅ |
| K | Pagination bounds | (backlog) | ◻ |
| L | Deploy / secret | `verify_static_antipatterns` + `verify_effort_quality` | ✅ |
| +Nav | Integritas navigasi | `check_nav_map` (INV-NAV-01, BLOCKING) | ✅ (baru) |
| +Meta | HIJAU-PALSU / gate mati | `verify_guardrail_registry` (INV-META-01) + disiplin self-test | ✅ (baru) |

> **Disiplin anti "HIJAU-PALSU" (WAJIB):** tiap guard baru DIBUKTIKAN bisa MERAH (inject pelanggaran → gate MERAH dgn pesan tepat → revert → HIJAU) sebelum dipercaya. Contoh: `check_nav_map` sudah self-test-proven (single-item + ghost).

---

## 3. Alur langkah (SOP baku)

> Login SEKALI, pakai token ulang (login rate-limit 10/60s). Admin: `admin@garment.com` / `Admin@123`.

**FASE A — Persiapan & Pemetaan (PRA-dev)**
1. Pastikan seed siap: login 200 + `verify_data_integrity.py` bisa jalan.
2. `guard.sh preflight` → baca duplicate-route (blok), FE-dead-call (triase), auth-gap, anti-pola.
3. Tetapkan cakupan uji berbasis TEMUAN, bukan ingatan. Setiap endpoint yang disentuh perubahan
   → masuk daftar uji (jangan cuma yang “teringat”).

**FASE B — Verifikasi Perilaku (POST-dev)**
4. `guard.sh gate` → integrity + state + concurrency + adversarial (+ advisory auth/rbac/static/contract).
5. Untuk tiap endpoint yang diubah: uji **isi**, bukan cuma status 200 (assert field, jumlah baris,
   nilai uang, referensi). Uji jalur sukses **dan** jalur gagal/adversarial.
6. Untuk fitur di balik auth/role: uji unauth (harap 401) + role-rendah (harap 403).

**FASE C — Uji Mutu Gate & Kerja (META)**
7. `guard.sh meta` → mutation-test (harus 100% KILLED/DB_ENFORCED) + effort-gate (grade & lensa).
8. Bila mutation SURVIVED > 0 → gate punya blind spot → tambah invarian di `verify_data_integrity.py`.

**FASE D — Bukti & Klaim**
9. Pastikan `GATE_RECEIPT.md` HIJAU untuk cakupan non-skip.
10. Baru boleh klaim “selesai”. Tanpa receipt HIJAU = void.

---

## 4. Teknik bug-hunting (checklist mendalam, di luar yang ter-otomasi)

- **Kontrak data:** apakah koleksi yang di-*seed* == koleksi yang di-*baca* API? (drift RC-1)
- **Bentuk respons:** field yang dibaca FE benar-benar dikembalikan BE? (RC-3)
- **Balapan:** buat N request paralel ke endpoint bernomor → nomor unik, tak ada 500? (RC-5)
- **Adversarial:** kirim tipe salah / non-numerik / string raksasa / list→string → 4xx? (RC-2)
- **Idempoten:** ulangi POST/void/post → tak dobel efek? (state machine)
- **Otorisasi:** login sbukan-admin → masih bisa baca finance/HR? (RBAC)
- **Referensial:** payment→invoice, stock→material, line→COA tidak yatim?
- **Batas numerik:** uang/qty tak negatif; balance ∈ [0, total].
- **Kosong ≠ bug:** tabel “Belum ada …” saat data jarang = wajar, jangan salah lapor.

---

## 5. Menambah gate baru (agar SOP berkembang)

1. Tulis skrip di `scripts/guardrails/` (runtime) atau `scripts/preflight/` (statik), pakai
   `scripts/lib/gr_common.py` (Report/Finding, ekstraksi route, login, dll).
2. Severity yang MEMBLOK di `block_sev`; sisanya WARN/INFO (kebijakan “deteksi & lapor”).
3. **Kalibrasi dulu** hingga bebas false-positive (gate berisik = kepercayaan runtuh). Uji terhadap
   endpoint yang PASTI benar; kalau ke-flag → perbaiki detektor, bukan diamkan.
4. Daftarkan di `scripts/gate.sh` (blok atau advisory) & `scripts/guard.sh`.
5. Tambahkan invarian ke `INVARIANTS.md` + (bila kelas bug baru) RC baru di `ENGINEERING_GUARDRAILS.md`.
6. Bila kelas bug bisa dikorupsi di DB → tambah mutasi di `meta/mutation_test.py` untuk membuktikan
   gate baru benar-benar menangkapnya.
7. **Naikkan versi SOP** (Bagian 7) + catat di CHANGELOG.

---

## 6. Prinsip kalibrasi (pelajaran nyata dari build ini)

> Saat pertama dibuat, auth-coverage melaporkan **326 HIGH** (palsu) karena melewatkan pola
> `Depends(require_auth)` & helper `_require_*` yang diimpor. Setelah kalibrasi → **10 HIGH nyata**.
> Contract-gate mula-mula 238 “dead call” (palsu, karena path dinamis) → dikalibrasi memakai
> OpenAPI runtime + segment-match → tinggal 7 duplicate-route nyata + 50 triase.

Gate yang berisik lebih berbahaya daripada tak ada gate: ia melatih orang mengabaikan merah.
Selalu: **turunkan false-positive dulu, baru naikkan tingkat blok.**

---

## 7. Versi & CHANGELOG

| Versi | Tanggal | Perubahan |
|---|---|---|
| 1.2.0 | 2026-07-05 | **Round-2 adopsi metodologi 2 repo referensi (kn + travel).** Tambah gate: `check_nav_map` (INV-NAV-01, BLOCKING, self-test-proven), `verify_numeric_bounds` (D), `verify_cross_entity` (H), `verify_guardrail_registry` (META), `health_check`; + alat forensik `forensic_repro.py` (bukti empiris + cleanup) & `root_cause_matrix.py` (completeness). Adopsi lapisan **effort/anti-underdelivery** (`verify_effort_quality` INV-QUALITY-01 + `ANTI_UNDERDELIVERY_PROTOCOL.md` + `DEEP_ANALYSIS_PLAYBOOK.md`). Matriks serangan A–L + disiplin anti "HIJAU-PALSU". Verifikasi round-2 (flow kritis) → `memory/VERIFICATION_ROUND2.md`. |
| 1.1.0 | 2026-07-05 | **BUG-RBAC-1 ditutup**: read-guard otorisasi via `shared.require_portal`/`require_portal_dep` (SSOT `check_portal_access`) di router finance/HR + `/financial-recap`. **INV-RBAC-01 kini BLOCKING** di `gate.sh`. Kalibrasi klasifikasi sensitif RBAC (fix bug token `/ap`↔`/api`) + sweep 800. |
| 1.0.0 | 2026-07-05 | SOP awal. Ekosistem 3-lapis: preflight (contract/static/auth), gate (integrity/state/concurrency/adversarial), meta (mutation/effort). Runner tunggal `guard.sh` + pre-commit. RC-5 diperbaiki di 10 titik + regresi CC2. |

### Rencana peningkatan (backlog SOP)
- [x] ~~Tegakkan RBAC read-guard di kode (tutup BUG-RBAC-1) lalu ubah INV-RBAC-01 jadi blocking.~~ ✅ v1.1.0
- [x] ~~Cross-entity gate (referensial yatim).~~ ✅ v1.2.0 (`verify_cross_entity.py`, INV-CROSS-01)
- [x] ~~Integritas navigasi / single-item section.~~ ✅ v1.2.0 (`check_nav_map.py`, INV-NAV-01)
- [x] ~~Meta guardrail-registry (anti HIJAU-PALSU).~~ ✅ v1.2.0 (`verify_guardrail_registry.py`)
- [ ] Perluas RBAC read-guard ke sub-router finance lain (rahaza_ar_360, rahaza_bank_recon, rahaza_hpp, dst) + tutup BUG-AUTH-1 (auth `wms_legacy`).
- [ ] **Fix 8 file kandidat RC-5** (count+1/len+1 → koleksi unique-index) yang di-flag `root_cause_matrix.py` (triage dulu; forensic_repro belum membuktikan pada 8 file ini).
- [ ] **Bound 134 field uang/qty** yang di-flag INV-NUM-01 (tambah `Field(ge=0)`), lalu naikkan INV-NUM-01 → blocking.
- [ ] Cross-entity double-allocation (stok FG / operator / mesin) + pagination bounds (kelas K).
- [ ] N+1 query / latency probe (adopsi `fa_nplus1` dari repo referensi).
- [ ] UI white-screen smoke per-modul (RC-4) via Playwright headless.
- [ ] Coverage-matrix endpoint (endpoint yang TAK PERNAH tersentuh uji).
