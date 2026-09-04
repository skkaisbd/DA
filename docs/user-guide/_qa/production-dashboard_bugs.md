# QA Bug Register — Modul `production-dashboard` (Dashboard Produksi hub)

<!-- Dokumen QA internal. TIDAK ditampilkan sebagai materi training.
     Materi training (bebas-bug): ../produksi/production-dashboard.md
     Standar: 01_DEEP_STANDARD_v3.md -->

> **Modul:** `production-dashboard` · **Komponen induk:** `frontend/src/components/erp/ProductionDashboardModule.jsx`
> **Status keseluruhan:** ✅ **1 temuan (Low) FIXED + diverifikasi** (2026-07-07)
> **Uji backend:** `tests/pilot_production_dashboard_test.py` → **33 PASS / 2 INFO / 0 FAIL** (INFO = data-dependent skip: tidak ada line master & tidak ada WO bar pada DB uji yang fresh).
> **Uji UI:** Playwright — 5 tab (Overview/Performa/Kualitas/Jadwal/AI) semua root panel render, tanpa error konsol.
> **Kondisi DB setelah uji:** bersih (preview run & RCA history dihapus by-id/window; tidak ada mutasi WO/seed).

---

## 1. Ringkasan Temuan
| ID | Severity | Judul singkat | Status | Verifikasi |
|----|----------|---------------|--------|------------|
| PD-BUG-001 | **Low** | `data-testid="production-dashboard"` duplikat (hub + Overview) → selector ambigu | ✅ FIXED | Playwright count hub=1, overview=1 |

---

## 2. Detail Temuan

### PD-BUG-001 — Duplikat `data-testid="production-dashboard"` · Severity: Low (testability)
- **Ditemukan saat:** verifikasi UI — `page.locator("[data-testid='production-dashboard']").count()` mengembalikan **2**.
- **Root cause:** dua elemen memakai testid yang sama — hub `ProductionDashboardModule.jsx:36` dan anak `ProductionDashboardOverview.jsx:102`. Saat tab Overview aktif keduanya ter-render (nested), sehingga selector `production-dashboard` **ambigu** (strict-mode Playwright akan gagal pada `click`/`fill`).
- **Dampak:** fungsional tidak terpengaruh (UI render normal); murni **testability** (automation strict-mode).
- **Perbaikan:** rename testid root komponen Overview menjadi `production-dashboard-overview` (semantik: panel tab Overview). Hub tetap `production-dashboard`.
- **File:** `frontend/src/components/erp/ProductionDashboardOverview.jsx:102`.
- **Verifikasi:** re-run Playwright → `production-dashboard` count = **1**, `production-dashboard-overview` count = **1**. `esbuild` OK. Tidak ada perubahan perilaku/tampilan.
- **Catatan manifest:** manifest v3 diekstrak sebelum fix (mencatat `production-dashboard` dari 2 lokasi). Validator C6 tetap terpenuhi karena `production-dashboard` masih ada (hub). Testid baru `production-dashboard-overview` juga didokumentasikan.

---

## 3. Observasi (non-blocking, by-design)
- **OBS-PD-A:** Pada DB uji yang **fresh** (`setup/status.needs_wizard = true`, 0 line, 0 WIP event), beberapa endpoint mengembalikan **guard 400 yang benar**, bukan bug:
  - `POST /api/rahaza/aps/auto-schedule/preview` → `400 "Tidak ada line aktif yang cocok dengan process terpilih."`
  - `POST /api/analytics/ai/production/rca` → `400 "Data produksi belum cukup (0 events, min 5)..."`
  Keduanya adalah validasi data-guard yang tepat; test menegaskannya sebagai skenario negatif/guard.
- **OBS-PD-B:** `production/rca` & `qc/rca` memakai LLM **Claude Sonnet 4.5** (integrasi `analytics_ai.py`). Karena DB fresh, guard 400 tercapai lebih dulu → LLM tidak dipanggil saat uji (hemat kredit, tanpa residu history).
- **OBS-PD-C:** Endpoint mutasi (reschedule WO, auto-schedule commit/rollback, seed-sample, skip/dismiss, close-manual, settings PUT) **tidak dimutasi** saat uji; hanya diuji lewat guard (invalid id → 4xx), idempoten (PUT settings nilai sama), atau RBAC tanpa token → 401/403. Ini menjaga DB tetap pristine.

## 4. Bukti Uji (artefak)
- **Skrip backend:** `/app/tests/pilot_production_dashboard_test.py` (35 TC; 26 endpoint; self-cleanup).
- **UI:** Playwright manual (screenshot Overview + Jadwal/APS) — 5 tab render, semua root testid resolve.
- **Kredensial uji:** `admin@garment.com` / `Admin@123`.

## 5. Changelog Perbaikan (kode)
| Tanggal | Perubahan | File |
|---|---|---|
| 2026-07-07 | PD-BUG-001: rename testid Overview → `production-dashboard-overview` (hilangkan duplikat) | `frontend/src/components/erp/ProductionDashboardOverview.jsx` |
