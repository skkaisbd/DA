# QA Bug Register — Modul `prod-work-orders` (Work Order)

<!-- Dokumen QA internal. TIDAK ditampilkan sebagai materi training.
     Materi training (bebas-bug): ../produksi/prod-work-orders.md
     Standar: 01_DEEP_STANDARD_v3.md -->

> **Modul:** `prod-work-orders` · **Komponen induk:** `frontend/src/components/erp/RahazaWorkOrdersModule.jsx`
> **Status keseluruhan:** ✅ **1 temuan (Medium) FIXED + diverifikasi** (2026-07-08)
> **Kondisi DB setelah uji:** bersih (self-cleanup skrip).

---

## 1. Ringkasan Temuan
| ID | Severity | Judul singkat | Status | Verifikasi |
|----|----------|---------------|--------|------------|
| WO-BUG-001 | **Medium** | Cetak LKP Massal melewatkan WO `in_production` (typo status `in_progress`) | ✅ FIXED | skrip TC-23 |

---

## 2. Detail Temuan

### WO-BUG-001 — `lkp-bulk-today` memakai status `in_progress` (tidak valid) · Severity: Medium
- **Ditemukan saat:** grounding kode untuk dokumentasi (baca `rahaza_lkp.py`).
- **Repro:** buat WO → bawa ke status `in_production` → buka **Cetak LKP Massal** (`GET /api/rahaza/lkp-bulk-today`).
- **Expected:** WO `in_production` **muncul** di daftar (fitur seharusnya menampilkan WO aktif = released + in_production).
- **Actual (sebelum fix):** WO `in_production` **tidak muncul**. Query memakai `{"status": {"$in": ["released", "in_progress"]}}`, padahal state machine WO memakai `in_production` (bukan `in_progress`). Akibatnya hanya WO `released` yang muncul; semua WO yang sedang dikerjakan (`in_production`) senyap hilang dari fitur cetak massal.
- **Root cause:** salah nama status (`in_progress` vs `in_production`). `in_progress` tidak pernah ada di `WO_STATUSES` (`rahaza_work_orders.py:49`).
- **Perbaikan:** ganti `in_progress` → `in_production` di query + komentar.
- **File:** `backend/routes/rahaza_lkp.py` (`lkp-bulk-today`, ~`:647`).
- **Verifikasi:** skrip TC-23 (buat WO in_production → `lkp-bulk-today` menyertakannya) → PASS.

---

## 3. Observasi (non-blocking)
- **OBS-WO-A (Low):** field `line_code` yang ditampilkan di tabel Cetak LKP Massal (`bulk-lkp-row`) tidak diisi pada dokumen WO standar (WO create tidak menyimpan `line_code`), sehingga kolom "Line" bisa kosong. Bukan defect fungsional — kolom informatif. Dicatat sebagai enhancement (isi dari LKP/assignment bila perlu).

## 4. Bukti Uji (artefak)
- **Skrip backend:** `/app/tests/pilot_prod_work_orders_test.py` (idempoten, self-cleanup).
- **Kredensial uji:** `memory/test_credentials.md`.

## 5. Changelog Perbaikan (kode)
| Tanggal | Perubahan | File |
|---|---|---|
| 2026-07-08 | WO-BUG-001: `lkp-bulk-today` status `in_progress` → `in_production` | `backend/routes/rahaza_lkp.py` |
