# STANDAR KEDALAMAN v2 — "Deep, Evidence-First, Zero-Shallow"  ⛔ DIGANTIKAN OLEH v3
> **⚠️ USANG:** Standar aktif kini **`01_DEEP_STANDARD_v3.md`** (bug dipisah dari training + gerbang validator otomatis `scripts/docgen/` + peningkatan kualitas). Dokumen v2 ini disimpan sebagai arsip. **Jangan** dipakai untuk modul baru.

### Cara membuat dokumen modul yang benar-benar KOMPREHENSIF (target 100/100)

> Dokumen ini adalah **KOREKSI** atas pendekatan v1 yang dinilai owner **dangkal (20%)**.
> Semua agent WAJIB memakai standar ini. Menggantikan bagian metodologi & template di `00_MASTERPLAN.md`.
> Bahasa dokumen keluaran: **Bahasa Indonesia**.

---

## 0. AKAR MASALAH v1 (kenapa cuma 20%) — jujur
Contoh nyata dari pilot `prod-orders` (dibuktikan dengan kode):
| Aspek | v1 (dangkal) | Kenyataan (hasil crawl) |
|---|---|---|
| Komponen yang dibaca | 1 (parent) | **8** (parent + 7 anak: OnwardCTA, Modal, DataTableV2, AuditHistoryDrawer, POStageTrackingPanel, moduleAtoms, glass/button) |
| Endpoint didokumentasikan | 8 | **14** (kurang 6: audit-logs, stage-summary, stage-qty, dst) |
| Panel anak diuji | 0 | 2 memanggil API sendiri (Audit, StageTracking) |
| Fitur rusak yang terlewat | 0 | **1 (StageTracking 404 untuk order Rahaza)** |
| Walkthrough user | naratif umum | belum klik-per-klik |
| Referensi salah | 1 ("modul Master" tanpa verifikasi) | seharusnya `prod-models-bom` & `mgmt-rahaza-customers` |

**Pelajaran:** mendokumentasikan hanya komponen induk + 1 file route = melewatkan >40% permukaan modul. **Tidak boleh terulang.**

---

## 1. PRINSIP INTI v2
1. **CRAWL, jangan skim.** Telusuri pohon komponen secara rekursif (induk → semua anak/panel/dialog/drawer/tab). Setiap komponen anak yang dirender = bagian dari modul.
2. **EXHAUSTIVE, bukan sampel.** Dokumentasikan & uji **SETIAP** elemen interaktif dan **SETIAP** endpoint — bukan yang "utama" saja.
3. **EVIDENCE-FIRST.** Tiap klaim menunjuk bukti: `file.jsx:baris` (frontend) atau `route.py:baris` (backend). Tanpa bukti → tandai `⚠️ PERLU VERIFIKASI`.
4. **SPEC vs ACTUAL.** Selalu pisahkan "seharusnya (dari kode)" vs "nyata (hasil run)".
5. **TRAINING-GRADE.** Panduan user = klik-per-klik: apa yang diklik, apa yang diketik, apa yang harus terlihat.
6. **HONEST.** Bug/keanehan ditulis apa adanya. Bug **High → fix langsung → verifikasi via `testing_agent_v3`** (bukan via curl/nalar sendiri). Med/Low dicatat.

---

## 2. 10 DELIVERABLE WAJIB PER MODUL (semua harus ada)

### D1 — Peta Komponen (Component Map)
Pohon render lengkap: komponen induk + SEMUA anak (panel/dialog/drawer/tab/tabel/atoms). Tabel: Komponen | Peran | File | data-testid utama | Memanggil API? (Y/T).

### D2 — Inventaris Elemen (Element Inventory) — EXHAUSTIVE
Tabel SETIAP elemen interaktif: tombol, ikon-aksi, field, select, checkbox, tab, kolom tabel, filter, badge, empty-state CTA, tombol export, pagination.
Kolom: Elemen | data-testid | Aksi | Endpoint dipanggil | Syarat tampil (role/status) | Syarat enabled/disabled | Efek.
> **Aturan anti-dangkal:** jika ada elemen di kode yang TIDAK ada di tabel ini → dokumen BELUM selesai.

### D3 — Katalog Kontrak Endpoint — SETIAP /api call (induk + anak)
Untuk tiap endpoint (diverifikasi di backend): Method | Path | Request schema (field:tipe:wajib:validasi) | Response schema | SEMUA status code (200/400/403/404/409/500) | RBAC | Koleksi DB disentuh | Efek samping | `route.py:baris`.
> **Aturan:** jumlah endpoint di katalog = jumlah hasil grep `/api/` di induk+anak. Tidak boleh kurang.

### D4 — Kamus Data (Data Dictionary)
Skema dokumen/entitas MongoDB yang terlibat: field, tipe, default, enum, index. Sumber: handler backend + `server.py` index.

### D5 — Aturan Bisnis & Logika
SEMUA validasi (frontend DAN backend, + **ketidakcocokan FE/BE ditandai**), perhitungan, dependensi antar-data, aturan visibilitas.

### D6 — State Machine
Semua status + transisi (manual & OTOMATIS/side-effect) + pemicu + timestamp + status final. Diagram `mermaid stateDiagram-v2`.

### D7 — Flow Detail (semua cabang)
Flow utama + SEMUA alternatif/error/branch + lintas-modul + lintas-koleksi. Tiap flow: `mermaid` + narasi langkah + **state UI di tiap langkah**.

### D8 — Walkthrough Pengguna (training-grade)
Per tugas (Buat/Edit/Hapus/Transisi/Generate/Export/Riwayat/dll): langkah bernomor — "Klik X (testid) → ketik Y → akan muncul Z". Termasuk **Prasyarat/Setup Awal** (mis. harus ada Master Model/Pelanggan dulu — sebut modul & path yang BENAR).

### D9 — Spesifikasi & Hasil Uji
- **Scenario** (naratif) menutup semua fitur.
- **Test case** menutup **SETIAP elemen (D2), SETIAP endpoint (D3), SETIAP cabang (D7), SETIAP status (D6)**; 5 tipe (Happy/Edge/Negative/Permission/State).
- Tiap case: Input konkret → Expected (spec) → **Actual (run)** → Verdict.
- **Dijalankan sungguhan:** backend via skrip (semua endpoint + edge), UI via `testing_agent_v3` (SEMUA panel & SEMUA status, termasuk membuka detail saat in_production/completed).

### D10 — Bug Findings + Troubleshooting + Lampiran Bukti
- Bug jujur (severity, repro, expected vs actual, bukti, rekomendasi). **High → fix + verifikasi testing_agent.**
- Troubleshooting berbasis perilaku nyata.
- Lampiran: daftar file dibaca (+baris), endpoint diverifikasi, path artefak uji (report iterasi + console log).

---

## 3. ATURAN CAKUPAN ("DONE" bila dan hanya bila)
- [ ] **100% komponen anak** yang dirender sudah dipetakan (D1) & dicakup.
- [ ] **100% elemen interaktif** ada di Inventaris (D2) & diuji (D9).
- [ ] **100% endpoint** (induk+anak) ada di Katalog (D3), terverifikasi backend, & dieksekusi di uji.
- [ ] **Setiap status** (D6) tercapai di minimal 1 test case.
- [ ] **0 klaim tanpa bukti** (atau ditandai ⚠️).
- [ ] **0 bug High terbuka** (sudah di-fix + diverifikasi testing_agent).
- [ ] Skor rubric (§4) **≥ 95/100**.

---

## 4. RUBRIK PENILAIAN (0–100) — self-score di header tiap dokumen
| Dimensi | Bobot | Kriteria penuh |
|---|---|---|
| Kelengkapan Fitur (D1,D2) | 20 | semua komponen anak + semua elemen terdokumentasi |
| Kelengkapan Flow (D7) | 15 | flow utama + semua cabang + lintas-modul/koleksi |
| Logic/State/RBAC (D5,D6) | 15 | semua validasi FE/BE + state machine + RBAC |
| Akurasi Kontrak Endpoint (D3,D4) | 15 | semua endpoint + schema + status code + koleksi DB |
| Cakupan & Hasil Uji Nyata (D9) | 20 | semua elemen/endpoint/status diuji + Actual terisi |
| Kejelasan Guideline (D8) | 10 | walkthrough klik-per-klik + prasyarat |
| Bukti Anti-Halusinasi (D10) | 5 | referensi file:baris + artefak uji |
| **Total** | **100** | **Done ≥ 95 & 0 bug High terbuka** |

---

## 5. WORKFLOW PER MODUL (urut, v2)
1. **Identifikasi**: `moduleRegistry.js` → komponen; bila hub, buka file hub.
2. **Crawl komponen**: baca induk → daftar `import` → baca SEMUA anak (rekursif) → susun **D1**.
3. **Ekstrak endpoint**: `grep /api/` di induk+semua anak → daftar lengkap.
4. **Verifikasi backend**: tiap endpoint → cari `route.py:baris` → catat method, schema, status code, RBAC, koleksi DB, efek samping → **D3, D4**.
5. **Susun D2 (elemen), D5 (logika), D6 (state), D7 (flow)** — semua grounded.
6. **Tulis D8 (walkthrough)** klik-per-klik + prasyarat setup.
7. **Uji backend**: skrip mencakup SEMUA endpoint + 5 tipe + edge → isi Actual.
8. **Uji UI**: `testing_agent_v3` mencakup SEMUA elemen, SEMUA panel, SEMUA status (buka detail saat in_production/completed, buka Riwayat, dsb) → isi Actual + path report.
9. **Fix bug High** langsung → **panggil `testing_agent_v3` lagi** untuk verifikasi (WAJIB, bukan curl/nalar).
10. **Isi D10**, hitung rubric, set header, update `00_INDEX.md`. Bersihkan data uji (DB pristine).

---

## 6. TEMPLATE DOKUMEN v2 (urutan section)
```
Header: # <Nama> — <Portal>  | moduleId | Status | Skor rubric /100 | Update
Metadata (komponen, endpoint count, RBAC, file dibaca)
BAGIAN A — PANDUAN PENGGUNA: 1 Ringkasan · 2 Konsep · 7 Flow · 8 Walkthrough (D8)
BAGIAN B — LAMPIRAN TEKNIS: D1 Peta Komponen · D2 Inventaris Elemen · D3 Katalog Endpoint · D4 Kamus Data · D5 Logika · D6 State Machine
BAGIAN C — UJI & TEMUAN: D9 Scenario+Test case (Actual) · D10 Bug+Troubleshooting+Bukti
Footer: Rubric self-score (tabel §4) + tanggal
```

---

## 7. CONTOH TARGET (prod-orders) — 14 endpoint yang WAJIB dicakup
Induk: `/api/rahaza/orders` (GET,POST), `/orders/{id}` (GET,PUT,DELETE), `/orders/{id}/status` (POST), `/orders/{id}/generate-work-orders` (POST), `/customers` (GET), `/models` (GET), `/sizes` (GET), `/orders-statuses` (GET).
Anak: `/api/audit-logs` (GET, dari AuditHistoryDrawer), `/api/production-pos/{id}/stage-summary` (GET) & `/stage-qty` (dari POStageTrackingPanel).
> Plus BUG-003 (StageTracking 404) HARUS diselesaikan + diverifikasi testing_agent.
