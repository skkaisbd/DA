# QA Bug Register — Modul `prod-bundles` (Bundle Produksi / Penelusuran Bundle)

<!-- Dokumen QA internal. TIDAK ditampilkan sebagai materi training.
     Materi training (bebas-bug): ../produksi/prod-bundles.md
     Standar: 01_DEEP_STANDARD_v3.md -->

> **Modul:** `prod-bundles` · **Komponen induk:** `frontend/src/components/erp/RahazaBundlesModule.jsx`
> **Status keseluruhan:** ✅ **1 temuan (Low) FIXED + diverifikasi** (2026-07-07)
> **Uji backend:** `tests/pilot_prod_bundles_test.py` → **26/26 PASS** (idempoten, self-cleanup).
> **Uji UI:** verifikasi Playwright (login → list → modal → halaman detail) — semua `data-testid` resolve.
> **Kondisi DB setelah uji:** bersih (self-cleanup + hapus data seed UI manual).

---

## 1. Ringkasan Temuan
| ID | Severity | Judul singkat | Status | Verifikasi |
|----|----------|---------------|--------|------------|
| BDL-BUG-001 | **Low** | `<Modal>` tidak meneruskan prop `data-testid` ke DOM → `bundle-detail-modal` tak bisa ditarget test | ✅ FIXED | Playwright count=1 setelah fix |

---

## 2. Detail Temuan

### BDL-BUG-001 — `Modal` facade membuang `data-testid` · Severity: Low (testability, bukan fungsional)
- **Ditemukan saat:** verifikasi UI populated-state (`testing_agent_v3` gagal `wait_for_selector('bundle-detail-modal')` walau modal jelas terbuka di layar).
- **Repro (sebelum fix):**
  1. Buka **Penelusuran Bundle** (`prod-bundles`) dalam kondisi ada bundle.
  2. Klik ikon mata pada satu baris (`bundle-detail-<bundle_number>`) → modal detail terbuka & tampil normal.
  3. Cari elemen `data-testid="bundle-detail-modal"` di DOM → **tidak ada**.
- **Expected:** Elemen surface modal memiliki `data-testid="bundle-detail-modal"` sesuai yang dikirim `RahazaBundlesModule.jsx:456` (`<Modal ... data-testid="bundle-detail-modal">`), sehingga test/automation bisa menargetkan modal spesifik.
- **Actual (sebelum fix):** Prop `data-testid` **dibuang**. `Modal` (facade Radix Dialog) hanya men-destructure prop yang dikenal (`title/children/onClose/size/...`) dan **tidak** meneruskan `data-testid` ke `DialogPrimitive.Content`. Modal tetap berfungsi 100% untuk end-user (tampil, tombol jalan, ESC/overlay close). Hanya **tidak dapat ditest** via testid tersebut. Dampak melebar: 41+ pemanggil `Modal` lain yang mengirim `data-testid` juga tak ter-render.
- **Root cause:** Signature `Modal({...})` tidak menangkap/meneruskan prop tak-dikenal ke elemen DOM.
- **Perbaikan:** tambah `...rest` pada signature `Modal`, ambil `rest['data-testid']`, dan set `data-testid={dataTestId}` pada `DialogPrimitive.Content`.
- **File:** `frontend/src/components/erp/Modal.jsx` (signature `:34`, `data-testid` di `DialogPrimitive.Content` `:87`).
- **Verifikasi:** re-run Playwright — `bundle-detail-modal` count = **1**, dan seluruh testid halaman detail (`bundle-detail-page`, `bundle-detail-current-step`, `bundle-detail-next-step`, `bundle-detail-progress`, `bundle-detail-flow`, `bundle-detail-timeline`, `bundle-detail-meta`, `bundle-timeline-event-0`, dsb.) resolve tanpa error konsol.
- **Regresi:** Non-breaking. `Modal` hanya menambah 1 atribut DOM; tidak mengubah perilaku/tampilan. `esbuild` OK.

---

## 3. Observasi (non-blocking)
- **OBS-BDL-A (By-design):** Backend `generate-bundles` (`rahaza_bundles_mgmt.py:92`) **tidak** mewajibkan WO berstatus `released` — cukup non-`cancelled` + `qty>0` + ada master proses aktif. UI menyarankan alur "release dulu", tetapi kontrak backend lebih longgar (memudahkan koreksi). Bukan defect; didokumentasikan sebagai Spec vs UX di dokumen training (B6).
- **OBS-BDL-B (By-design):** Transisi status bundle setelah `created` (`in_process`/`qc`/`reworking`/`packed`/`shipped`/`closed`) **tidak** dilakukan oleh modul ini; digerakkan modul Eksekusi/QC/Rework/Shipment. Modul `prod-bundles` bersifat **read + trace + print + hapus (created)**.

## 4. Bukti Uji (artefak)
- **Skrip backend:** `/app/tests/pilot_prod_bundles_test.py` (26 TC, idempoten, self-cleanup).
- **UI:** Playwright manual (screenshot list + halaman detail) + `test_reports/iteration_70.json` (empty-state PASS).
- **Kredensial uji:** `admin@garment.com` / `Admin@123`.

## 5. Changelog Perbaikan (kode)
| Tanggal | Perubahan | File |
|---|---|---|
| 2026-07-07 | BDL-BUG-001: `Modal` meneruskan `data-testid` ke `DialogPrimitive.Content` | `frontend/src/components/erp/Modal.jsx` |
