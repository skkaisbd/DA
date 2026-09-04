# E11 — SCOPING PORT "PORTAL VENDOR (CMT)" (SOMMERVILLE → DA)
> Analisis lanjutan. GROUNDED: SOMMERVILLE `frontend/.../erp/Vendor*.jsx` (14 komponen) +
> DA `vendor-cmt/VendorCMTPortalApp.jsx`, `routes/vendor_portal.py`, `routes/production_jobs.py`,
> `routes/dewi_cmt_*`. STATUS: ANALISIS. Scope §1b: portal VENDOR = SATU dari 4 yang diadopsi.

## 0. TEMUAN INTI
DA **SUDAH punya 2 sistem vendor-facing** (tak perlu bikin dari nol):
1. **Maklon CMT Portal** — `VendorCMTPortalApp.jsx` → `/api/dewi/cmt/vendor/*` + `/api/dewi/cmt/delivery-orders/vendor/*`
   (my-jobs, progress stage-based sewing/finishing/qc/packing, delivery-orders + confirm-receipt).
2. **Generic Vendor Portal** — `routes/vendor_portal.py` (`/api/vendor-portal/*`: partners, accounts, jobs,
   my-jobs, progress, progress-audit).
→ Port SOMMERVILLE = **ISI GAP fitur** ke portal Maklon CMT DA (UI komponen DA), BUKAN port `VendorPortalApp.jsx`.

## 1. PETA 14 KOMPONEN VENDOR SOMMERVILLE → DA
| SOMMERVILLE komponen | Endpoint SOMMERVILLE | Padanan DA | Status |
|---|---|---|---|
| VendorDashboard | `/vendor/dashboard` | CMT portal stats (VendorCMTPortalApp) | ✅ ADA (sesuaikan metrik) |
| VendorProductionJobs | `/production-jobs`, `/production-job-items` | `/api/dewi/cmt/vendor/my-jobs` | ✅ ADA (model beda: stage vs job SOMMERVILLE) |
| VendorProgress | `/production-progress`, `/production-job-items?job_id` | `/api/dewi/cmt/vendor/my-jobs/{id}/progress` | ✅ ADA (stage-based) → **selaraskan ke job-item + guard I-1** |
| VendorReceiving | `/vendor-shipments`, `/vendor-shipment-items` | `/api/dewi/cmt/delivery-orders/vendor/my-dos` + confirm-receipt | ⚠️ PARSIAL (DO≈shipment; tak ada inspeksi received/missing) |
| VendorMaterialInspection | `/vendor-material-inspections` | (cmt receipt QC `cmt_receipts`) | ❌ GAP vendor-facing (inspeksi material MASUK received/missing) |
| VendorMaterialRequests | `/material-requests` | `dewi_cmt_component_requests.py` | ⚠️ PARSIAL (samakan REQ-ACC/ADD/RPL) |
| VendorBuyerShipments / VendorShipmentModule | `/buyer-shipments`, `/buyer-shipment-dispatches` | `/api/dewi/cmt/delivery-orders/*` | ⚠️ PARSIAL (dispatch bertahap dispatch_seq belum tentu ada) |
| VendorDefectReports | `/material-defect-reports` | (`dewi_maklon_qc` QC-1=B) | ❌ GAP vendor-facing defect (potong kapasitas I-1) |
| VendorVarianceReport | `/production-variances` | `production_variances.py` (admin) | ❌ GAP vendor-facing (over/under) |
| VendorSerialTracking | `/serial-trace`, `/serial-list` | `operations_serials.py` | ⚠️ PARSIAL (cek expose ke vendor) |
| VendorReminderInbox | `/reminders` | — | ❌ GAP (reminder inbox vendor) |
| VendorShared / VendorPortalApp | (shell) | `VendorCMTPortalApp` shell DA | ✅ pakai shell DA (jangan port shell SOMMERVILLE) |

## 2. RINGKAS GAP untuk MAKLON (port fitur ke CMT portal DA)
- **GAP penuh**: Material Inspection (received/missing), Defect Reports (potong kapasitas), Variance Report
  (over/under), Reminder Inbox.
- **Selaraskan/PARSIAL**: Progress → basis job-item + guard I-1 (bukan hanya stage counter); Receiving →
  tambah langkah inspeksi; Buyer Shipments → dispatch bertahap (`dispatch_seq`, cap produced C-1);
  Material Requests → tipe REQ-ACC/ADD/RPL + kebijakan Phase 16.
- **Sudah ada**: Dashboard, Jobs list, shell portal.

## 3. CATATAN MODEL (Maklon identik vs CMT DA sekarang)
- CMT DA sekarang **stage-based** (sewing/finishing/qc/packing) — mirip sisa mesin multi-stage.
- SOMMERVILLE Maklon = **job → progress by job_item** (bukan stage). Keputusan #2 "Maklon identik SOMMERVILLE"
  → progress Maklon **di-selaraskan ke job_item + invarian**. (QC tetap `dewi_maklon_qc_checks`, QC-1=B.)
- **cmt_vendor** login + `cmt_vendor_id` sudah ada (RBAC E8) → tinggal remap allowed_roles saat expose endpoint.

## 4. IMPLIKASI EKSEKUSI (untuk Fase 2 Maklon)
Backend (backend-first, §7 plan): expose endpoint flow SOMMERVILLE untuk role `cmt_vendor` (my-shipments +
inspection, my-material-requests, my-jobs progress job-item, my-buyer-shipments dispatch, my-defect-reports,
my-variances, reminders) — filter `vendor_id`/`cmt_vendor_id`. Frontend: tambah tab/panel di
`VendorCMTPortalApp.jsx` (komponen DA) untuk fitur GAP; **batch build sekali** (§7). UI testing di AKHIR.

## 5. MICRO-DECISIONS
- **VP-1** Progress Maklon: ganti stage-counter → job-item + I-1 (selaras identik SOMMERVILLE)? [default: YA]
- **VP-2** Reminder Inbox vendor: port atau skip (low value)? [default: SKIP dulu, low priority]
- **VP-3** Serial tracking expose ke vendor: ya/tidak? [default: YA, read-only]

---
*E11 selesai. Analisis produksi/maklon (E1–E11) LENGKAP + adapter + scoping port. Siap eksekusi setelah lampu hijau.*
