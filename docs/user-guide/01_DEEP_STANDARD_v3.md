# STANDAR KEDALAMAN v3 — "Deep, Evidence-First, Machine-Enforced"
### Cara membuat dokumen modul yang KOMPREHENSIF **dan dipaksa mesin** agar konsisten 1-pass

> Menggantikan `01_DEEP_STANDARD_v2.md`. Perubahan besar v3 (atas permintaan owner):
> 1. **Bug DIPISAH** dari dokumen training → materi pelatihan **tidak menampilkan bug**.
> 2. **Kepatuhan standar DIPAKSA MESIN** (extractor + template + validator), bukan sekadar niat.
> 3. **Kualitas ditingkatkan**: visual keadaan layar per langkah, worked example lebih panjang, bahasa lebih awam.
> Bahasa keluaran: **Bahasa Indonesia**.

---

## 0. MASALAH YANG DIPECAHKAN v3
| Masalah lama | Akibat | Solusi v3 |
|---|---|---|
| Standar hanya "kualitatif" (niat) | AI perlu berkali-kali revisi; hasil tak konsisten | **Validator otomatis** = gerbang Definition of Done (exit 0 wajib) |
| Komponen anak / endpoint terlewat (dangkal) | >40% permukaan modul hilang | **Extractor** meng-crawl kode → manifest "permukaan pasti" |
| Endpoint/label dikarang (halusinasi) | Dokumen tidak dapat dipercaya | Validator **menolak** endpoint/testid yang tidak ada di kode |
| Bug tampil di materi training | Dokumen pelatihan tampak "penuh cacat", tidak profesional | Bug **wajib** di `_qa/<moduleId>_bugs.md`; validator menolak tag bug di training |

---

## 1. PRINSIP INTI (tetap dari v2, dipertegas)
1. **CRAWL, jangan skim** — telusuri pohon komponen rekursif (kini **otomatis** via extractor).
2. **EXHAUSTIVE, bukan sampel** — dokumentasikan & uji SETIAP elemen & SETIAP endpoint.
3. **EVIDENCE-FIRST** — tiap klaim menunjuk `file:baris`; tanpa bukti → `⚠️ PERLU VERIFIKASI` (dan validator akan menolak dokumen "Done" yang masih memuat penanda ini).
4. **SPEC vs ACTUAL** — pisahkan "seharusnya (kode)" vs "nyata (run)".
5. **TRAINING-GRADE & AWAM** — klik-per-klik + **visual keadaan layar** + bahasa sederhana.
6. **HONEST tapi TERPISAH** — bug ditulis jujur, **tetapi di file QA terpisah**, bukan di materi training.

---

## 2. TOOLCHAIN WAJIB (INILAH "FORCING FUNCTION")
Tiga skrip di `scripts/docgen/` mengubah standar → aturan yang dicek mesin.

### 2.1 Extractor — `extract_module.py`
```
python3 scripts/docgen/extract_module.py --module-id <moduleId>
```
- Menemukan komponen induk dari `moduleRegistry.js`, crawl semua import anak (rekursif, **komentar di-strip** agar akurat).
- Mengekstrak SEMUA `/api/...` + SEMUA `data-testid` (dengan `file:baris`).
- Cross-ref ke tabel route backend (`backend/routes/*` + `server.py`, hitung prefix).
- Output: `docs/user-guide/_manifests/<moduleId>.manifest.json` = **permukaan modul yang pasti**.

### 2.2 Template — `docs/user-guide/_TEMPLATE_MODULE.md`
- Salin sebagai kerangka; struktur A/B/C/D sudah lengkap tanpa section bug.
- Semua penanda `<<...>>` WAJIB diisi/dihapus.

### 2.3 Validator — `validate_module.py` = **Definition of Done**
```
python3 scripts/docgen/validate_module.py --module-id <moduleId>
```
Menolak (exit ≠ 0) bila salah satu gagal:
| Cek | Aturan |
|---|---|
| C1 Struktur | Section wajib (Metadata, Bagian A/B/C, Peta Komponen, Inventaris, Katalog Endpoint, State Machine, Uji) ada. |
| C2 Diagram | ≥1 `stateDiagram-v2` **dan** ≥1 diagram alur (flowchart/graph/sequence). |
| C3 Coverage endpoint | SEMUA endpoint (verified) di manifest muncul di dokumen. |
| C4 Anti-halusinasi | SEMUA `/api` di dokumen ada di tabel route backend (prefix router diterima). |
| C5 Coverage komponen | SEMUA komponen erp di manifest disebut di dokumen. |
| C6 Coverage testid | SEMUA `data-testid` konkret di manifest disebut di dokumen. |
| C7 Bebas-bug | TIDAK ada `BUG-`/`OBS-` atau section bug/temuan/changelog perbaikan. |
| C8 Bebas-placeholder | TIDAK ada `<<ISI>>`/`TODO`/`TBD`/`PERLU VERIFIKASI`. |
| C9 Skor rubrik | Ada skor `NN/100` dan ≥ 95. |
| C10 Metadata | (WARN) konsistensi jumlah endpoint. |
| C11 Kedalaman | Dokumen ≥ `MIN_DOC_LINES` (default **800**) baris — cegah dokumen dangkal. Modul mayor ditargetkan ~1000+. |

> **Aturan mutlak:** dokumen **TIDAK BOLEH** ditandai `Done` di `00_INDEX.md` sebelum validator **LULUS**.
> Ini menghilangkan "revisi berkali-kali": AI tinggal memperbaiki sampai skrip hijau.

---

## 3. KEBIJAKAN BUG (BARU di v3)
- **Materi training** (`docs/user-guide/<portal>/<moduleId>.md`) **WAJIB bebas bug**:
  - Tidak ada tag `BUG-xxx`/`OBS-xxx`.
  - Tidak ada section "Bug Findings/Temuan/Changelog Perbaikan".
  - Test case boleh ada, tetapi tampilkan **perilaku benar** + hasil **PASS** (tanpa menautkan ke bug).
- **Semua temuan bug** dicatat di:
  - `docs/user-guide/_qa/<moduleId>_bugs.md` (detail: severity, repro, expected vs actual, perbaikan, bukti `file:baris`, verifikasi).
  - `docs/user-guide/_qa/BUG_REGISTER.md` (ringkasan lintas modul).
- **Alur saat menemukan bug:** catat di `_qa` → bug **High** langsung fix + verifikasi `testing_agent_v3` → set status. Med/Low dicatat; fix bila diminta owner.

---

## 4. PENINGKATAN KUALITAS WAJIB (BARU di v3)
Selain deliverable v2, dokumen modul WAJIB memuat:
1. **A9 Visual Keadaan Layar** — mockup ASCII layar di tiap langkah penting + `stateDiagram-v2` "perpindahan tampilan" (screen-state), agar user membayangkan tampilan.
2. **D4 Worked Example diperluas** — cerita realistis dengan persona (mis. staf PPIC), langkah 0..selesai, termasuk **revisi/penanganan error**, bukan hanya happy-path 5 baris.
3. **Bahasa lebih awam** — kalimat pendek, analogi, hindari jargon tak dijelaskan; sediakan **A10 "cara cepat membaca dokumen"**.

---

## 5. WORKFLOW PER MODUL (v3, urut)
1. `extract_module.py --module-id <id>` → baca manifest (komponen, endpoint, testid).
2. Salin `_TEMPLATE_MODULE.md` → `docs/user-guide/<portal>/<id>.md`.
3. Isi A1–A10, B1–B10, C1–C6, D1–D7 (grounded ke `file:baris`; pakai manifest untuk kelengkapan).
4. Uji backend (skrip, 5 tipe, self-cleanup) + UI (`testing_agent_v3`, semua panel & status) → isi `Actual`.
5. Temuan bug → tulis di `_qa/<id>_bugs.md` + `_qa/BUG_REGISTER.md` (bug **High** fix + retest).
6. `validate_module.py --module-id <id>` → perbaiki sampai **LULUS (exit 0)**.
7. Set header/skor, update `00_INDEX.md`. **Bersihkan data uji (DB pristine).**

---

## 6. DEFINITION OF DONE (per MODUL)
- [ ] Extractor dijalankan → manifest ada di `_manifests/`.
- [ ] Dokumen dari `_TEMPLATE_MODULE.md`, semua section terisi.
- [ ] `validate_module.py` **LULUS** (0 FAIL).
- [ ] Bug (bila ada) di `_qa/`, **bukan** di training doc.
- [ ] Test dijalankan; `Actual` terisi; **DB bersih**.
- [ ] `00_INDEX.md` di-update.

---

## 7. RUBRIK (0–100) — self-score di header (validator wajib ≥95)
| Dimensi | Bobot |
|---|---|
| Kelengkapan Fitur (B1,B2,B3) | 20 |
| Kelengkapan Flow (A7,A9,B6,B8) | 15 |
| Logic/State/RBAC (B6,B7) | 15 |
| Akurasi Kontrak Endpoint (B5,B9,B10) | 15 |
| Cakupan & Hasil Uji Nyata (C2,C3) | 20 |
| Kejelasan Guideline & Keawaman (A8,A9,A10,D4) | 10 |
| Bukti Anti-Halusinasi (file:baris + manifest + artefak) | 5 |
| **Total** | **100** |

---

## 8. CONTOH ACUAN (GOLD TEMPLATE)
- **`produksi/prod-orders.md`** — pilot yang sudah **LULUS validator** (1057 baris): bebas bug, 8/8 komponen, 11/11 endpoint, 22 testid, visual layar (A9), worked example (D4).
- Manifest: `_manifests/prod-orders.manifest.json` · QA: `_qa/prod-orders_bugs.md`.
