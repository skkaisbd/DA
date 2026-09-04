# GAP ANALYSIS — Verifikasi & Guardrail: `da` (CV. Dewi Aditya ERP) vs `travel` (Rahaza-Travel)

> Analisis mendalam atas dokumen repair Part 1→5 + ENGINEERING_GUARDRAILS `da`, dibandingkan
> dengan metodologi verifikasi bug, guardrail, dan mitigasi di repo `akugendutkayababi/travel`.
> Tujuan: temukan **blind-spot** cakupan pengecekan `da`, implementasikan guardrail/mitigasi
> `travel` ke `da`, lalu buktikan secara **empiris** (bukan asumsi).
>
> Status implementasi: **SUDAH DIKERJAKAN** (lihat §6–§7). Gate suite `da` kini HIJAU
> (`memory/GATE_RECEIPT.md`), dan **2 kelas bug nyata ditemukan + diperbaiki** saat proses ini.

---

## 1. Ringkasan Eksekutif (TL;DR)

| | `da` (SEBELUM) | `travel` | `da` (SESUDAH sesi ini) |
|---|---|---|---|
| Model guardrail | **Checklist manual** (RC-1..RC-10), tergantung ingatan agen | **Kode otomatis** (`gate.sh` + 13 verifier) | **Kode otomatis** (`gate.sh` + 5 verifier inti) |
| Fokus | Layer **data-plumbing** (seed↔collection↔API↔FE) | + **business-logic / state / concurrency / cross-entity** | + business-logic / state / concurrency + adversarial |
| Concurrency / race (TOCTOU) | ❌ tidak ada | ✅ `verify_concurrency.py` | ✅ `verify_concurrency.py` |
| State-machine transisi menyimpang | ❌ tidak ada | ✅ `verify_state_machine.py` | ✅ `verify_state_machine.py` |
| Invarian data ter-kodifikasi | ❌ (hanya GET-sweep manual) | ✅ `verify_data_integrity.py` (INV-1..26) | ✅ `verify_data_integrity.py` (19 invarian) |
| Adversarial input → 5xx | ❌ tidak ada | ✅ `verify_adversarial_5xx.py` | ✅ `verify_adversarial_5xx.py` |
| Baseline forensik nol-asumsi | ❌ tidak ada | ✅ `forensic_dump.py` | ✅ `forensic_dump.py` |
| Orkestrator + receipt bukti | ❌ tidak ada | ✅ `gate.sh` → `GATE_RECEIPT.md` | ✅ `gate.sh` → `GATE_RECEIPT.md` |

**Temuan inti:** guardrail `da` sangat baik untuk kelas bug **"data desync"** (tabel kosong, Rp 0,
layar putih, 404/500 karena drift nama koleksi/field/shape). Tapi `da` **buta total** terhadap
kelas bug yang oleh forensik `travel` disebut **"green-but-broken"** — lolos semua gate happy-path
(seed bersih + single-thread + jalur normal) namun rusak saat **transisi state nyata, konkurensi,
lintas-periode, lintas-entitas, dan input adversarial**. Sesi ini menutup blind-spot itu dengan
mengadopsi arsitektur gate `travel`, dan langsung membuktikan nilainya dengan menemukan bug asli.

---

## 2. Metodologi masing-masing repo

### 2.1 `da` — Guardrail berbasis CHECKLIST (RC-1..RC-10)
Sumber: `memory/ENGINEERING_GUARDRAILS.md`, `SSOT_MASTER_REPAIR_PLAN_PART*.md`.

10 root-cause yang dikodifikasi **sebagai narasi/checklist** untuk diikuti agen:

| Kode | Root cause | Layer |
|---|---|---|
| RC-1 | Collection-name drift (seed vs API) | Data plumbing |
| RC-2 | Field-name drift | Data plumbing |
| RC-3 | Response-shape drift (list vs {items:[]}) | API↔FE contract |
| RC-4 | Missing import / router tak terdaftar | Wiring |
| RC-5 | **Counter desync** (nomor dok mulai dari 1 padahal seed sudah ada) | Data plumbing |
| RC-6 | Broken linkage antar entitas | Referential |
| RC-7 | **Semantic/calculation** (mis. beda basis pajak) | Business logic |
| RC-8 | Hardcoded value | Config |
| RC-9 | RBAC / portal access | Security |
| RC-10 | **False-positive testing** (uji lolos padahal fitur rusak) | Meta |

**Kekuatan:** peta root-cause yang tajam & spesifik-domain. **Kelemahan fatal:** semuanya
**bergantung agen mengingat & menjalankan manual**. Tidak ada satu perintah pun yang bisa
membuktikan "semua invarian valid". RC-10 (false-positive testing) menyindir dirinya sendiri:
uji happy-path lewat testing-agent bisa HIJAU walau invarian bisnis bocor.

### 2.2 `travel` — Guardrail berbasis KODE (gate otomatis)
Sumber: `scripts/gate.sh`, `scripts/verify_*.py`, `scripts/guardrails/*.py`, `memory/INVARIANTS.md`,
`docs/DEEP_ANALYSIS_PLAYBOOK.md`, `FORENSIC_00_EXECUTIVE_SUMMARY.md`.

Filosofi eksplisit: **"ubah 'diingat developer' menjadi 'dipaksa oleh analisis kode' agar tidak
bergantung memori sesi."** Setiap invarian punya verifier yang:
- **Resilient**: backend mati/login gagal → **SKIP** (bukan FAIL) — aman dijalankan kapan pun.
- **Sintetis + auto-cleanup**: objek uji tanggal 2028 + hapus balik ke baseline (DB tak kotor).
- **Cek efek-samping DB**, bukan cuma HTTP 200.
- **Verdikt empiris**: TERBUKTI / TIDAK TERBUKTI / DORMANT / FALSE-POSITIVE.

---

## 3. Tesis "green-but-broken" (jantung analisis)

Forensik `travel` menemukan: gate lama (`da` maupun `travel` awal) hanya menguji **tiga kondisi ideal**:
1. **Seed bersih** (data konsisten hasil seeder),
2. **Single-thread** (satu request pada satu waktu),
3. **Happy-path** (urutan aksi normal, input valid).

Bug kelas berikut **lolos ketiganya** namun muncul di produksi nyata:

| Kelas | Contoh di ERP garment `da` | Kenapa lolos gate lama |
|---|---|---|
| **Concurrency / TOCTOU** | 2 user finance buat jurnal serentak di hari sama → nomor bentrok | Gate single-thread |
| **State-machine menyimpang** | Void jurnal 2×, post jurnal non-draft, terima GRN > qty PO | Gate hanya happy-path |
| **Lintas-periode** | Payroll periode X ter-post ulang di periode Y | Seed bersih tak punya 2 periode |
| **Lintas-entitas** | Stok FG sama dialokasikan ke 2 order | Seed tak punya kontensi |
| **Adversarial input** | `debit:"abc"` → `float()` crash 500 | Gate pakai input valid saja |

---

## 4. Matriks cakupan (apa yang DICEK tiap repo)

| Dimensi verifikasi | `da` sebelum | `travel` | `da` sesudah |
|---|:--:|:--:|:--:|
| Nama koleksi ada (anti-RC-1) | manual | ✅ | ✅ (forensic_dump: phantom_reads) |
| Field/shape kontrak FE↔BE | manual | ✅ verify_contract | ⚠️ (parsial via adversarial) |
| GL seimbang per-jurnal (ΣDr=ΣCr) | ❌ | ✅ INV | ✅ INV-GL-1 |
| Trial-balance global | ❌ | ✅ | ✅ INV-GL-2 |
| Ref. integrity (line→COA, pay→invoice) | manual | ✅ | ✅ INV-GL-3/REF-1 |
| Stok tak negatif + rekonsiliasi | ❌ | ✅ | ✅ INV-STK-1 |
| Nomor dok unik (anti-RC-5) | ❌ | ✅ | ✅ INV-CNT-1 |
| AR/AP paid≤total, balance≥0 | ❌ | ✅ | ✅ INV-AR/AP |
| Saldo cuti tak minus / tak over-consume | ❌ | ✅ | ✅ INV-LEAVE-1 |
| WO completed≤target | ❌ | ✅ | ✅ INV-WO-1 |
| **Concurrency numbering** | ❌ | ✅ | ✅ CC1 |
| **State-machine transisi menyimpang** | ❌ | ✅ | ✅ SM1-4 |
| **Adversarial → no 5xx** | ❌ | ✅ | ✅ INV-5XX-01 |
| Cross-entity double-alloc | ❌ | ✅ | ⚠️ belum (lihat §8) |
| Numeric-bounds statik (schema) | ❌ | ✅ | ⚠️ N/A* |
| Reservation-lock statik | ❌ | ✅ | ⚠️ belum |
| RBAC guard statik | manual (portalAccess SSOT) | ✅ | ⚠️ manual |
| Orkestrator + receipt | ❌ | ✅ | ✅ gate.sh |

\* `da` mayoritas pakai `await request.json()` (tanpa Pydantic), jadi scan bound schema kurang
relevan; validasi bound diverifikasi **runtime** via adversarial gate + INV-NUM-1 di DB.

---

## 5. BLIND-SPOT `da` (jawaban langsung atas pertanyaan)

> "apakah pengecekan di project `da` masih kurang, apa blind-spot-nya?"

**Ya, kurang.** Sebelum sesi ini, seluruh verifikasi `da` hanya menyentuh **layer data-plumbing**
dan **happy-path**. Blind-spot konkret:

1. **BS-1 Concurrency (TERBUKTI berbahaya).** Pola penomoran `count_documents(...) + 1` dipakai di
   **~14 file route produksi** (jurnal, work-order, AP/AR, FG issue, delivery note, bank transfer,
   stock opname, dll). Semua rentan balapan → nomor duplikat / **crash 500 E11000**. Ini persis RC-5,
   tapi RC-5 `da` hanya memikirkan "seed vs counter", **bukan balapan runtime**.
2. **BS-2 State-machine.** Tak ada gate untuk transisi menyimpang. (Kabar baik: modul jurnal & cuti
   `da` ternyata **sudah** menjaga ini dengan baik — kini terlindungi regresi oleh SM1-4.)
3. **BS-3 Invarian akuntansi tak ter-kodifikasi.** Tak ada yang otomatis memastikan GL selalu
   seimbang, AR=Σ tak-terbayar, stok≥0. Hanya "lihat tabel tidak kosong".
4. **BS-4 Adversarial input (TERBUKTI).** Banyak endpoint pakai `float(request.json()[...])` tanpa
   guard → input non-numerik = **500**. Ditemukan 3 crash nyata.
5. **BS-5 Cross-entity contention.** Belum ada uji alokasi-ganda (stok/operator/mesin).
6. **BS-6 Tidak ada "bukti hijau" tunggal.** "Selesai" divonis dari "testing-agent lolos" — yang oleh
   RC-10 `da` sendiri diakui bisa false-positive. Kini ada `GATE_RECEIPT.md`.
7. **BS-7 Baseline nol-asumsi.** Tak ada snapshot koleksi/endpoint yang bisa dibandingkan antar sesi.

---

## 6. Yang DIIMPLEMENTASIKAN ke `da` (mitigasi/guardrail dari `travel`)

Semua di `/app/scripts/` (jalankan: `cd /app && bash scripts/gate.sh`).

| File | Kelas gate | Diadaptasi dari `travel` |
|---|---|---|
| `scripts/forensic_dump.py` | Baseline nol-asumsi (koleksi, count, keys, endpoint, akses-kode) | `forensic_dump.py` |
| `scripts/verify_data_integrity.py` | 19 invarian akuntansi/inventori/referensial | `verify_data_integrity.py` |
| `scripts/verify_concurrency.py` | RC-5 TOCTOU: N jurnal paralel → nomor unik / no-5xx | `verify_concurrency.py` |
| `scripts/verify_state_machine.py` | Transisi menyimpang jurnal (SM1-4) | `verify_state_machine.py` |
| `scripts/guardrails/verify_adversarial_5xx.py` | Input hostile → 4xx bukan 5xx | `guardrails/verify_adversarial_5xx.py` |
| `scripts/gate.sh` | Orkestrator + tulis `memory/GATE_RECEIPT.md` | `gate.sh` |
| `memory/INVARIANTS.md` | SSOT daftar invarian | `memory/INVARIANTS.md` |
| `memory/BUG_REGISTRY.md` | Registri bug ditemukan + status | `memory/BUG_REGISTRY.md` |

Semua verifier mewarisi properti aman `travel`: **resilient (SKIP≠FAIL)**, **sintetis + auto-cleanup**,
**cek efek-samping DB**, **kalibrasi anti-false-positive** (lihat INV-MKL-1 di §7).

---

## 7. Bug NYATA yang ditemukan + diperbaiki (bukti empiris)

Detail lengkap di `memory/BUG_REGISTRY.md`. Ringkas:

### BUG-1 — RC-5 Concurrency: penomoran jurnal balapan (P1, DIPERBAIKI)
- **Repro:** 5 `POST /api/rahaza/journals` paralel (tanggal sama) → **4/5 = HTTP 500 (E11000)**.
- **Akar:** `_gen_je_number` pakai `count_documents+1` (non-atomik) + ada unique index `je_number`.
- **Fix:** helper baru `utils/counters.gen_prefixed_number()` (atomic `$inc` SSOT + lazy max-init)
  + retry-on-DuplicateKey. Setelah fix: **5/5 = 200 dengan nomor unik**. Gate CC1 HIJAU.
- **Sistemik:** pola sama ada di ~14 file lain (recipe migrasi di BUG_REGISTRY untuk ditindaklanjuti).

### BUG-2 — Adversarial 5xx: crash pada input non-numerik (P1, DIPERBAIKI)
- **Repro:** `debit:"abc"`, `lines:"bukan-list"` → 500; `POST .../payment {amount:"abc"}` → 500.
- **Akar:** `float(...)` tanpa guard di `_validate_lines` (jurnal) & handler pembayaran AR/AP.
- **Fix:** validasi tipe/isinstance + `_to_amount()` → kini semua **400**. Gate INV-5XX-01 HIJAU.

### FALSE-POSITIVE yang dicegah — INV-MKL-1 (RC-7 basis pajak)
- Gate awal menandai 2 maklon PO "amount_paid > total_value". **Verifikasi empiris:** rasio tepat
  **1.11 (PPN 11%)** — `amount_paid` sudah termasuk pajak (= total invoice), `total_value` pra-pajak.
  Pembayaran **konsisten** dengan invoice. **Tindakan benar:** kalibrasi invarian jadi tax-aware
  (bandingkan ke total invoice tax-inclusive) + turunkan jadi **WARN** untuk mendokumentasikan
  *semantic smell* (satu dokumen mencampur basis pra-pajak & tax-incl). Ini mendemonstrasikan
  prinsip `travel`: **gate tak boleh false-positive** (hindari "merah palsu").

---

## 8. Gap tersisa & rekomendasi (roadmap)

Masih ada blind-spot yang belum ditutup penuh (jujur, bukan diklaim selesai):

1. **Broaden BUG-1 ke ~14 endpoint lain** (WO, AP/AR, FG issue, delivery note, bank transfer,
   opname, payroll profile) — pakai `gen_prefixed_number`. Recipe di `BUG_REGISTRY.md`.
2. **`verify_cross_entity.py`** — uji alokasi-ganda stok FG / operator / mesin (kelas RC-6 runtime).
3. **`verify_reservation_locks.py` (statik)** — pastikan jalur alokasi stok serialize via lock/atomic.
4. **`verify_rbac_guards.py` (statik)** — otomatiskan cek portalAccess SSOT (kini masih manual).
5. **Lintas-periode payroll** — uji post payroll periode ganda tak double-count.
6. **Validasi AP invoice** — saat ini menerima body tanpa `items` → invoice Rp 0 (200). Sebaiknya 400.
7. **Integrasikan `gate.sh` ke workflow rilis** — jadikan syarat sebelum klaim "selesai".

---

## 9. Cara pakai

```bash
cd /app
bash scripts/gate.sh                       # jalankan semua gate + tulis receipt
cat memory/GATE_RECEIPT.md                 # lihat verdikt HIJAU/MERAH
python scripts/verify_data_integrity.py    # cek invarian data saja (butuh Mongo)
python scripts/verify_concurrency.py       # cek balapan penomoran (butuh backend+auth)
python scripts/forensic_dump.py            # perbarui baseline SSOT_FORENSIC_RAW_DA.json
```

**Aturan emas (dari `travel`, kini berlaku di `da`):** *"Selesai" hanya sah bila `GATE_RECEIPT.md`
HIJAU untuk cakupan yang tidak di-SKIP. SKIP bukan PASS.*
