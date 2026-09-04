# ✅ AI QUALITY CONTRACT — Definisi “Minimal Working Quality”
**CV. Dewi Aditya ERP — Ekosistem Guardrails**

> **Versi:** 1.0.0  **Diperbarui:** 2026-07-05
> Kontrak ini mendefinisikan kapan sebuah perubahan boleh diklaim **“selesai”**. Ditegakkan
> otomatis oleh `scripts/meta/effort_gate.py`. Tujuannya: mencegah respons AI low-effort yang
> “mengerjakan lapisan luar saja” lalu bilang *everything is fine*.

---

## 1. Masalah yang dijawab

Model AI sering:
- berhenti di “HTTP 200 → beres” tanpa cek **isi** respons,
- tidak menambah test/verifikasi,
- meninggalkan `TODO`, `mock`, `placeholder`, `console.log`, stub `NotImplementedError`,
- mengklaim selesai tanpa menjalankan gate (atau memakai receipt basi).

Effort-gate menilai perubahan (via `git diff`) terhadap **BUKTI**, memberi **Grade A–F**, dan
(dengan `--strict`) MEMBLOK bila lensa wajib gagal.

---

## 2. Lima Lensa (rubrik)

| Lensa | Sifat | Lolos bila… |
|---|---|---|
| **L1 EXEC_EVIDENCE** | BLOK | `memory/GATE_RECEIPT.md` ada, VERDICT **HIJAU**, dan **mtime-nya lebih baru** dari file sumber yang diubah (bukti gate dijalankan SETELAH perubahan — bukan receipt basi). |
| **L2 TESTS_PRESENT** | WARN | Bila ada perubahan sumber non-trivial, ada pula test/verifier yang berubah/ditambah (`backend/tests/*`, `*_test.py`, `scripts/verify_*`, `scripts/meta/*`). |
| **L3 NO_LEFTOVER** | BLOK | Tak ada sisa low-effort di file berubah: `TODO/FIXME/XXX/HACK`, `mock/dummy/placeholder/lorem`, `console.log/debugger`, `print()` debug di backend, stub `pass #`, `NotImplementedError`. |
| **L4 MUTATION_KILLED** | BLOK\* | Bila `test_reports/guardrails/mutation.json` ada → `SURVIVED == 0`. (\*hanya mem-blok bila laporan tersedia.) |
| **L5 GATES_GREEN** | WARN | Semua `test_reports/guardrails/*.json` → `blocking == 0`. |

Grade: A=5 lolos, B=4, C=3, D=2, F≤1. Lensa BLOK gagal + `--strict` → exit code ≠ 0.

---

## 3. Cara pakai

```bash
cd /app
python scripts/meta/effort_gate.py                    # nilai perubahan uncommitted vs HEAD
python scripts/meta/effort_gate.py --base <git-ref>   # vs ref tertentu
python scripts/meta/effort_gate.py --changed a.py b.jsx   # daftar file eksplisit
python scripts/meta/effort_gate.py --strict           # mem-blok bila lensa BLOK gagal (CI/pre-commit)
```

Catatan: file di `scripts/` (tooling guardrail) DIKECUALIKAN dari L3 karena sengaja memuat
kata kunci smell sebagai pola regex.

---

## 4. Definition of Done (DoD) ringkas

Sebuah tugas SELESAI bila **semua** ini benar:
1. `bash scripts/guard.sh gate` → `GATE_RECEIPT.md` **HIJAU** (cakupan non-skip).
2. `python scripts/meta/mutation_test.py` → SURVIVED 0 (gate integrity efektif).
3. `python scripts/meta/effort_gate.py --strict` → HIJAU (Grade ≥ B; L1/L3/L4 lolos).
4. Endpoint yang diubah diuji **isi** (bukan cuma 200) + jalur adversarial.
5. CHANGELOG / PRD / `test_credentials.md` diperbarui bila relevan.

> Bila salah satu gagal: **jangan** klaim selesai. Perbaiki akar masalah, jalankan ulang.
> Jujur soal yang belum beres > klaim palsu “semua baik-baik saja”.

---

## 5. Versi & CHANGELOG

| Versi | Tanggal | Perubahan |
|---|---|---|
| 1.0.0 | 2026-07-05 | Kontrak awal: 5 lensa (L1–L5), integrasi effort_gate + pre-commit. |
