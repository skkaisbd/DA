# MASTERPLAN — Dokumentasi Pengguna & Test Spec (per Modul)
### DA37 ERP — CV. Dewi Aditya · FARM stack (FastAPI + React + MongoDB)

> **⚠️ UPDATE 2026-07-08 (v3):** Standar aktif kini **`01_DEEP_STANDARD_v3.md`** (menggantikan v2).
> Perubahan besar: (1) **bug dipisah** dari dokumen training (materi pelatihan bebas bug, catatan QA di `_qa/`);
> (2) kepatuhan **dipaksa mesin** via toolchain `scripts/docgen/` (extractor + template + validator);
> (3) peningkatan kualitas (visual keadaan layar, worked example panjang, bahasa awam). **Baca v3 sebelum bekerja.**
>
> **Toolchain wajib (per modul):**
> ```
> python3 scripts/docgen/extract_module.py  --module-id <id>   # -> _manifests/<id>.manifest.json
> cp docs/user-guide/_TEMPLATE_MODULE.md docs/user-guide/<portal>/<id>.md   # isi grounded
> python3 scripts/docgen/validate_module.py --module-id <id>   # WAJIB exit 0 sebelum "Done"
> ```
>
> **Status:** PILOT `prod-orders` **TERKUNCI** sebagai gold template (LULUS validator, 1057 baris).
> **Tujuan dokumen ini:** panduan kerja & handoff agar SIAPA PUN agent berikutnya melanjutkan dengan standar & disiplin SAMA.
> **Bahasa dokumen:** Bahasa Indonesia.

---

## 0. CARA PAKAI DOKUMEN INI (untuk agent penerus)
1. Baca **§2 Prinsip** & **§3 Anti-Halusinasi** dulu — ini tidak boleh dilanggar.
2. Ikuti **§7 Metodologi Kerja per Modul** langkah demi langkah.
3. Pakai **§6 Template Dokumen** persis (jangan mengarang struktur baru).
4. Update **§10 Index/Progress Tracker** setiap 1 modul selesai.
5. Jangan tandai modul "SELESAI" sebelum lulus **§9 Definition of Done**.

---

## 1. TUJUAN & RUANG LINGKUP

**Tujuan ganda tiap dokumen modul:**
- **Materi training** untuk user (paham fitur & alur kerja langkah-per-langkah).
- **Spesifikasi uji (test spec)** yang bisa dijalankan berulang untuk deteksi bug (regression).

**Unit dokumentasi = 1 MODUL = 1 file.**
"Modul" di sini = satu layar fitur yang benar-benar dilihat/dipakai user, yaitu:
- Modul standalone (mis. `fin-ar-invoices`, `prod-orders`), **dan**
- Setiap **tab di dalam Hub** (mis. tab "Pareto Cacat" di `prod-analytics-hub`) — didokumentasikan sebagai modul tersendiri, plus 1 dokumen "Hub" tipis yang menautkan tab-tabnya.

**Estimasi volume:** ~333 entri di `moduleRegistry.js`. Setelah dikurangi redirect/alias & digabung per fitur nyata, perkiraan **±180–220 dokumen modul**. → WAJIB dikerjakan **bertahap per portal** (lihat §8).

**Yang TIDAK termasuk (kecuali diminta):** dokumentasi kode/arsitektur internal (sudah ada di `docs/SYSTEM_ARCHITECTURE.md`), CI/CD, security hardening.

---

## 2. PRINSIP UTAMA
1. **Grounded ke kode nyata** — setiap kalimat fitur/field/endpoint/status HARUS bisa ditunjuk ke file sumbernya.
2. **Per modul, konsisten** — semua dokumen memakai template §6 yang sama.
3. **Detail & lengkap** — sampai level field, validasi, transisi status, dan hak akses (RBAC).
4. **Dapat diuji** — tiap flow punya test scenario + test case dengan input & output konkret.
5. **Sekalian testing** — test dijalankan (curl / testing_agent_v3), hasil aktual dicatat, bug dilaporkan.
6. **Bahasa Indonesia**, istilah/akronim domain dipertahankan (PO, AR, AP, GL, HPP, QC, BOM, dst).

---

## 3. ⛔ PROTOKOL ANTI-HALUSINASI (WAJIB — tidak boleh ditawar)

> Owner secara eksplisit meminta: **tidak boleh ada halusinasi & tidak boleh menutup-nutupi.**

**Aturan keras:**
- **DILARANG mengarang** nama field, nama endpoint, path, method, status, label, atau perilaku.
- Setiap **endpoint** yang ditulis harus sudah diverifikasi ada di backend (grep di `backend/routes/*` / `server.py`) — sertakan `METHOD /path` yang persis.
- Setiap **field input/output** harus berasal dari komponen React (`frontend/src/components/erp/...`) atau schema/handler backend — sertakan nama file.
- Setiap **Expected Output** pada test case harus berasal dari **perilaku yang benar-benar diamati** (dijalankan via curl/testing agent) — bukan asumsi. Bedakan jelas:
  - `Expected (spesifikasi)` = yang seharusnya terjadi menurut kode.
  - `Actual (hasil uji)` = yang benar-benar terjadi saat dijalankan.
- Jika ada yang **belum bisa dipastikan** → tulis apa adanya dengan penanda:
  - `⚠️ PERLU VERIFIKASI: <apa yang belum pasti & kenapa>` — JANGAN diisi tebakan.
- Jika menemukan **ketidaksesuaian** (mis. tombol UI memanggil endpoint yang tidak ada) → catat sebagai **BUG** di §8-dokumen, jangan disembunyikan atau "dirapikan" seolah normal.
- **Larangan menutup-nutupi kegagalan:** bila test gagal/observasi ganjil, tulis blak-blakan di bagian "Bug Findings" beserta bukti (log/console/screenshot path).

**Bukti yang wajib dilampirkan di tiap dokumen modul:**
- Daftar file sumber yang dibaca (frontend + backend).
- Daftar endpoint yang diverifikasi + cara verifikasi (grep/curl).
- Untuk test yang dijalankan: perintah/skenario + ringkasan hasil + path artefak (console log / report iterasi testing agent).

**Penanda status verifikasi (dipakai di header tiap dokumen):**
- `✅ VERIFIED` — dibaca dari kode + diuji.
- `🟡 CODE-READ` — dibaca dari kode, belum diuji runtime.
- `⚠️ UNVERIFIED` — ada bagian yang belum bisa dipastikan (list di dokumen).

---

## 4. SUMBER KEBENARAN (SOURCE OF TRUTH)
| Kebutuhan | File |
|---|---|
| Daftar portal + RBAC | `frontend/src/components/erp/PortalSelector.jsx`, `portalAccess.js` |
| Menu/nav (portal→section→modul) | `frontend/src/components/erp/portal-shell/portalNav.js` |
| moduleId → komponen React | `frontend/src/components/erp/moduleRegistry.js` |
| Isi Hub (daftar tab) | `frontend/src/components/erp/hubs/*.jsx` |
| Fitur/field/aksi/state UI | komponen modul di `frontend/src/components/erp/**/*.jsx` |
| Endpoint, validasi, status | `backend/routes/*.py`, `backend/server.py`, `backend/auth.py` |
| Guardrail nav | `scripts/guardrails/check_nav_map.py` |
| Kredensial uji | `memory/test_credentials.md` (login sekali, reuse token; rate-limit 10/60s) |

Navigasi runtime: **hash-based** — set `window.location.hash='<moduleId>'` lalu **reload**.

---

## 5. STRUKTUR FOLDER & PENAMAAN
```
docs/user-guide/
  00_MASTERPLAN.md              ← dokumen ini
  00_INDEX.md                   ← daftar semua dokumen + status (progress tracker)
  <portal>/                     ← 1 folder per portal (produksi, keuangan, gudang, sdm, ...)
    _PORTAL.md                  ← ringkasan portal + diagram alur bisnis lintas-modul
    <moduleId>.md               ← 1 file per modul (contoh: prod-orders.md)
    <hubId>.md                  ← dokumen Hub (tipis) + tautan ke tab-tabnya
```
- Nama file = `moduleId` persis (huruf kecil, tanda hubung) → mudah dilacak balik ke registry.
- Folder portal: `manajemen, produksi, gudang, aksesoris, keuangan, sdm, maklon, marketing, rnd, aset, kolaborasi, portal-saya`.

---

## 6. TEMPLATE DOKUMEN PER MODUL (WAJIB dipakai apa adanya)

```markdown
# [Nama Modul] — <Portal>
<!-- moduleId: <id> | Status verifikasi: ✅/🟡/⚠️ | Update: YYYY-MM-DD -->

## Metadata
- **moduleId:** `...`            **Portal:** ...        **Tipe:** standalone / tab-hub / hub
- **Komponen:** `frontend/src/components/erp/....jsx`
- **Endpoint utama:** `METHOD /api/...` (list; semua sudah diverifikasi ada)
- **Role yang boleh akses:** ... (sumber: portalAccess.js / check_role backend)
- **File sumber yang dibaca:** [list]

## 1. Ringkasan Modul
Apa fungsinya, untuk siapa (role), dipakai kapan dalam proses bisnis.

## 2. Konsep & Istilah
Glossary field & status penting (mis. status invoice: draft/sent/paid/void).

## 3. Logic & State  ← WAJIB detail
- **Aturan bisnis** (validasi, perhitungan, dependensi antar-data).
- **State machine / transisi status** + diagram mermaid (mis. draft → sent → paid).
- **RBAC**: aksi apa butuh role apa (sumber: kode).
- **Efek samping**: apa yang berubah di DB / modul lain saat aksi dilakukan.

## 4. Flow Detail (Business Process)  ← WAJIB detail
- Diagram mermaid alur end-to-end (termasuk cabang & titik sentuh modul/portal lain).
- Narasi langkah bermakna bisnis (bukan sekadar klik).

## 5. Penjelasan Fitur (per aksi)
Untuk TIAP aksi (Tambah/Edit/Hapus/Approve/Export/dll):
- **Expected Input:** tabel field | tipe | wajib? | validasi | contoh nilai.
- **Expected Output:** perubahan UI + data tersimpan + efek samping.
- **Logic/State terkait:** status berubah menjadi apa, aturan yang berlaku.

## 6. Referensi API
Tabel: Method | Path | Ringkas request | Ringkas response | Kode sukses | Kode error.
(Semua HARUS terverifikasi di backend — sebutkan file route.)

## 7. Test Scenarios (naratif)
Daftar skenario bermakna (mis. "SC-1: Buat invoice lalu bayar sebagian",
"SC-2: Coba approve tanpa hak akses"). Tiap skenario menjelaskan konteks & tujuan.

## 8. Test Cases (tabel — mendalam)
| ID | Skenario | Prasyarat | Langkah/Input (data konkret) | Expected Output (spesifikasi) | API + status | Tipe | Actual (hasil uji) | Verdict |
|----|----------|-----------|------------------------------|-------------------------------|--------------|------|--------------------|---------|
- **Tipe:** Happy / Edge / Negative / Permission / State-transition.
- Wajib mencakup: happy path, batas nilai (edge), input invalid (negative),
  akses tanpa role (permission), dan transisi status (state).
- Kolom **Actual** & **Verdict (PASS/FAIL/BUG)** diisi SETELAH dijalankan.

## 9. Bug Findings (hasil testing)  ← jujur, tanpa menutup-nutupi
| BUG-ID | Severity (High/Med/Low) | Deskripsi | Langkah repro | Expected vs Actual | Bukti (log/screenshot path) | Rekomendasi fix |
(“Tidak ditemukan bug” hanya ditulis bila SEMUA test case berstatus PASS.)

## 10. Troubleshooting Umum
Gejala → kemungkinan sebab → solusi (dari perilaku nyata).
```

---

## 7. METODOLOGI KERJA PER MODUL (urut, wajib)
1. **Identifikasi** — dari `moduleRegistry.js` cari komponen modul; bila tab-hub, buka file hub untuk konteks.
2. **Baca frontend** — komponen modul: daftar aksi, field form, state, panggilan `fetch`/axios (catat path API), pesan validasi, gating role.
3. **Baca backend** — untuk tiap path API dari langkah 2: cari di `backend/routes/*` → catat method, validasi, status code, efek DB, cek RBAC (`check_role`).
4. **Tulis §1–§6** dokumen (grounded; tandai `⚠️ PERLU VERIFIKASI` bila ada yang gelap).
5. **Susun §7 scenario + §8 test case** (mendalam; semua tipe).
6. **JALANKAN test:**
   - Backend/kontrak: `curl` (login sekali, reuse token) → isi kolom Actual.
   - Flow UI end-to-end: **`testing_agent_v3`** (batch beberapa modul sekaligus per portal agar hemat) → isi Actual + path report.
   - **JANGAN** uji drag-drop/kamera/voice via agent (batasan tool) — tandai "manual".
7. **Isi §9 Bug Findings** apa adanya. Bila ada bug:
   - Catat severity + repro + bukti.
   - **Keputusan fix menunggu owner** (lihat §8 kebijakan), KECUALI owner sudah menyetujui auto-fix.
   - Jika di-fix → **WAJIB** panggil `testing_agent_v3` lagi untuk verifikasi sebelum tandai selesai.
8. **Update `00_INDEX.md`** (status modul) + set penanda verifikasi header.

---

## 8. PRIORITAS, FASE & KEBIJAKAN BUG

**Urutan pengerjaan (usulan, bisa diubah owner):**
1. **PILOT 1 modul** (usul: `prod-orders` / `fin-ar-invoices`) → owner review format → kunci template.
2. **Portal per portal**, mulai dari yang paling kritikal secara bisnis:
   Produksi → Keuangan → Gudang → Maklon → Marketing → SDM → Aksesoris → RnD → Manajemen → Aset → Kolaborasi → Portal Saya.
3. Di tiap portal: kerjakan modul batch (±5–8 modul), lalu 1 sesi testing_agent_v3 untuk batch itu.

**Kebijakan bug (perlu keputusan owner — lihat §11):**
- Opsi A: **Dokumentasi + testing dulu**, semua bug dikumpulkan → owner prioritaskan → baru fix.
- Opsi B: **Fix sambil jalan** (bug High langsung fix + retest, bug Med/Low dicatat).

**Definition of Done — per MODUL:**
- [ ] §1–§10 terisi, tidak ada bagian kosong tak-berpenanda.
- [ ] Semua endpoint & field terverifikasi dari kode (atau ditandai ⚠️).
- [ ] Test case mencakup 5 tipe (Happy/Edge/Negative/Permission/State).
- [ ] Test dijalankan; kolom Actual & Verdict terisi.
- [ ] Bug (bila ada) tercatat jujur di §9.
- [ ] Header penanda verifikasi di-set; `00_INDEX.md` di-update.

**Definition of Done — per PORTAL:**
- [ ] Semua modul portal punya dokumen "Done".
- [ ] `_PORTAL.md` (diagram alur bisnis lintas-modul) selesai.
- [ ] 1 laporan ringkas bug portal.

---

## 9. STANDAR TESTING & PELAPORAN
- **Login sekali, reuse token** (rate-limit 10/60 detik). Kredensial: `memory/test_credentials.md` / admin `admin@garment.com` / `Admin@123`.
- **DB pristine:** setiap data uji yang dibuat WAJIB dibersihkan setelah tes (catat di dokumen bahwa cleanup dilakukan).
- **testing_agent_v3**: kirim daftar modul + skenario + kredensial; simpan path report (`/app/test_reports/iteration_*.json`) di §9 dokumen.
- **Severity bug:** High (blокир fungsi/500/data salah) · Med (fungsi jalan tapi keliru minor/UX) · Low (kosmetik/teks).

---

## 10. INDEX & PROGRESS TRACKER
Dibuat file `00_INDEX.md` berisi tabel: Portal | moduleId | Nama | Status (Belum/Draft/Testing/Done) | Verifikasi (✅/🟡/⚠️) | #Bug | Link file.
Di-update setiap modul selesai — inilah peta kemajuan untuk agent penerus.

---

## 11. KEPUTUSAN OWNER (SUDAH DIKUNCI — 2026-07-07)
1. **Target pembaca**: **BERLAPIS** — bagian user simpel + lampiran teknis (API/role). ✔
2. **Kebijakan bug**: **Opsi B — Fix sambil jalan** (bug High langsung fix + retest; Med/Low dicatat). ✔
3. **Modul pilot pertama**: **`prod-orders`** (Order Produksi / RahazaOrdersModule). ✔
4. **Screenshot**: **TIDAK** — cukup teks + diagram mermaid. ✔
5. **Kedalaman test**: **MENDALAM** (5 tipe skenario, sampai level field & transisi status). ✔

> Environment sudah disiapkan: repo di-clone ke `/app`, `.env` dipertahankan, `JWT_SECRET`
> ditambahkan ke `backend/.env`, dependency terpasang, service jalan, login admin terverifikasi.

---

## 12. CATATAN HANDOFF UNTUK AGENT BERIKUTNYA
- Jangan ubah `.env`, `MONGO_URL`, `REACT_APP_BACKEND_URL`.
- Jangan hapus moduleId di registry (deep-link).
- Pola konsolidasi IA & penamaan sudah selesai (lihat header `portalNav.js` — IA v2.1). Dokumen ini mengacu ke struktur nav TERBARU tersebut.
- Selalu jujur soal `⚠️ PERLU VERIFIKASI` dan bug — ini permintaan tegas owner.
- Kerjakan bertahap; update `00_INDEX.md` agar progres tak hilang antar sesi.
```
