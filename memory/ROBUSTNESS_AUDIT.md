# 🛡️ ROBUSTNESS + STATE-MACHINE AUDIT — Discovery Report (READ-ONLY)

> ## ✅ STATUS 2026-07-25 (FASE 11) — SEMUA TEMUAN AUDIT 1 SUDAH DITUTUP
> Dokumen di bawah adalah laporan **DISCOVERY** aslinya dan **dipertahankan sebagai arsip**.
> Jangan dibaca sebagai daftar pekerjaan yang masih terbuka.
>
> | Temuan | Status sekarang |
> |---|---|
> | **R11-A** — query param tak tervalidasi (~43 endpoint) | ✅ **DITUTUP** — 46 endpoint diperbaiki; sweep **7.184 request → 0 error 500** |
> | **R11-B** — `/api/rahaza/material-stock` 500 polos | ✅ sudah sehat (200) |
> | **R11-SM-1/2** — approve id hantu balas 200 palsu | ✅ sudah sehat (404) |
> | `/api/push/vapid-public-key` 503 | benign by-design (bukan bug) |
>
> **Alat pengganti yang harus dipakai mulai sekarang** (jangan mengulang audit manual):
> * `python3 scripts/sweep_query_robustness.py` — sapu SELURUH GET endpoint × 8 varian query rusak.
>   Sifat read-only. Keluar dengan kode ≠ 0 bila ada 5xx.
> * `python3 scripts/verify_fase11.py` — gate regresi FASE 11 (108 assertion).
> * `python3 scripts/map_broken_endpoints.py` — memetakan hasil sweep ke file + baris sumber.
>
> **Pelajaran metodologi:** audit awal memakai ~1.797 request dan menemukan 45 endpoint. Sweep FASE 11
> memakai 7.184 request dan menemukan 51. Menguji dengan **sampel** membuat sesi sebelumnya salah
> menyimpulkan R11-A sudah beres (7 dari 8 sampel kebetulan sudah sembuh). **Sapu semuanya, jangan sampel.**
>
> **Hati-hati false positive:** endpoint ber-LLM (mis. `/api/finance/ai-cashflow` ≈ 20 detik) menahan
> slot koneksi saat sweep paralel sehingga endpoint TETANGGA yang sehat ikut time-out dan terlaporkan
> sebagai error. 5 dari 51 temuan awal ternyata jenis ini. Selalu probe ulang SERIAL sebelum menuduh.


> Mode: **DISCOVERY** (tanpa perbaikan). AUDIT 1 = probe GET (read-only). AUDIT 2 = inventaris statik (tidak menembak endpoint write).

> Backend routes: **2268** · GET diprobe: **899** endpoint (~1797 request) · Login admin: OK


---


## AUDIT 1 — Endpoint GET yang mengembalikan 5xx (server error) — **45**

> 5xx pada GET = bug robustness (semestinya 200/400/404, bukan 500). Read-only, tak ada data berubah.

**Karakterisasi akar-masalah (verifikasi manual):**
- **R11-A — Query param tak tervalidasi → 500 (SISTEMIK, ~43 endpoint):** list-endpoint 500 saat query malformed. Pemicu bervariasi per endpoint: `limit=-1` (limit negatif diteruskan ke Motor `.limit()/.to_list()`), atau parsing tanggal/int (`date_from=notadate`, `skip=zzz`, `year=abcd`) tanpa `try/except`. **Seharusnya 400/422, bukan 500.** Contoh terverifikasi `limit=-1→500`: `/api/dewi/rnd/styles`, `/api/dewi/kasbon/requests`, `/api/hr/job-board/jobs`.
- **R11-B — `GET /api/rahaza/material-stock` → 500 PLAIN (tanpa param sekalipun):** endpoint 500 pada pemanggilan normal (bukan hanya adversarial) → **prioritas lebih tinggi** (dipakai `RahazaStockModule`, `InventoryScrapModule`, `RahazaFGInventoryModule`, `MaklonMaterialIssuePanel`). = **BUG-BE-500-1** di registry.
- **BENIGN (bukan bug):** `/api/push/vapid-public-key` → **503 "Web Push not configured"** (respons sengaja + JSON jelas; fitur push memang belum dikonfigurasi). Dikeluarkan dari hitungan bug.

> Ringkas: **1 endpoint rusak-total (R11-B)** + **~43 endpoint rentan query-param (R11-A, sistemik)** + 1 benign. Semua **READ-ONLY** (tak ada data berubah).



| GET endpoint | Pemicu | HTTP |
|---|---|---:|
| `/api/ai-business/daily-summary/history` | adversarial-query | 500 |
| `/api/dewi/accessory-requests` | adversarial-query | 500 |
| `/api/dewi/ai-actions` | adversarial-query | 500 |
| `/api/dewi/cmt-component-requests` | adversarial-query | 500 |
| `/api/dewi/kasbon/requests` | adversarial-query | 500 |
| `/api/dewi/kreator-requests` | adversarial-query | 500 |
| `/api/dewi/lms/courses` | adversarial-query | 500 |
| `/api/dewi/lms/enrollments` | adversarial-query | 500 |
| `/api/dewi/onboarding/checklists` | adversarial-query | 500 |
| `/api/dewi/recruitment/candidates` | adversarial-query | 500 |
| `/api/dewi/recruitment/jobs` | adversarial-query | 500 |
| `/api/dewi/rnd/materials` | adversarial-query | 500 |
| `/api/dewi/rnd/revisions` | adversarial-query | 500 |
| `/api/dewi/rnd/sample-costing` | adversarial-query | 500 |
| `/api/dewi/rnd/sample-requests` | adversarial-query | 500 |
| `/api/dewi/rnd/styles` | adversarial-query | 500 |
| `/api/hr/ai/attrition/dashboard` | adversarial-query | 500 |
| `/api/hr/ai/coaching/history` | adversarial-query | 500 |
| `/api/hr/ai/resume-screen/history` | adversarial-query | 500 |
| `/api/hr/expenses/pending-approval` | adversarial-query | 500 |
| `/api/hr/job-board/applications` | adversarial-query | 500 |
| `/api/hr/job-board/jobs` | adversarial-query | 500 |
| `/api/hr/shift-scheduler/schedules` | adversarial-query | 500 |
| `/api/hr/skill-gap/analyses` | adversarial-query | 500 |
| `/api/lms/student/catalog` | adversarial-query | 500 |
| `/api/maklon/ai-quote/history` | adversarial-query | 500 |
| `/api/management/okr/objectives` | adversarial-query | 500 |
| `/api/marketing/ai-content/history` | adversarial-query | 500 |
| `/api/marketing/alerts/history` | adversarial-query | 500 |
| `/api/marketing/livehost/analytics/host-performance` | adversarial-query | 500 |
| `/api/marketing/livehost/analytics/shift-analysis` | adversarial-query | 500 |
| `/api/marketing/livehost/payment/status` | adversarial-query | 500 |
| `/api/marketing/tasks-stats` | adversarial-query | 500 |
| `/api/portal-saya/career-coach/reports` | adversarial-query | 500 |
| `/api/prod/control-tower/wo-list` | adversarial-query | 500 |
| `/api/production-jobs` | adversarial-query | 500 |
| `/api/production/predictive-maintenance/machines` | adversarial-query | 500 |
| `/api/production/predictive-maintenance/maintenance-logs` | adversarial-query | 500 |
| `/api/push/vapid-public-key` | plain | 503 |
| `/api/rahaza/3way-match` | adversarial-query | 500 |
| `/api/rahaza/management/top-customers` | adversarial-query | 500 |
| `/api/rahaza/management/top-models` | adversarial-query | 500 |
| `/api/rahaza/overtime` | adversarial-query | 500 |
| `/api/vendor-portal/progress-audit` | adversarial-query | 500 |
| `/api/wms/picklist` | adversarial-query | 500 |


## AUDIT 2 — Inventaris endpoint transisi status (coverage-gap map) — **167**

> Endpoint write bertransisi status (approve/reject/cancel/close/post/…). Yang SUDAH diuji adversarial di R6–R10: cutting, finishing, QC, asset assign/return, material reserve, AR/AP payment, stock adjust. Sisanya **belum diprobe transisi ilegal** (potensi risiko breadth).


### Per portal/domain

| Portal/prefix | Jumlah endpoint transisi |
|---|---:|
| `hr/expenses` | 11 |
| `dewi/maklon` | 10 |
| `dewi/rnd` | 5 |
| `procurement/requests` | 5 |
| `rahaza/finance` | 5 |
| `dewi/cmt` | 4 |
| `marketing/returns` | 4 |
| `production/material-returns` | 4 |
| `rahaza/purchase-orders` | 4 |
| `approvals/requests` | 3 |
| `dewi/cutting` | 3 |
| `lms/student` | 3 |
| `marketing/advanced-ai` | 3 |
| `marketing/livehost` | 3 |
| `prod/cmt-receipts` | 3 |
| `rahaza/ap-invoices` | 3 |
| `rahaza/ar-invoices` | 3 |
| `rahaza/leaves` | 3 |
| `rahaza/payroll-runs` | 3 |
| `wms/opname2` | 3 |
| `acc/opname` | 2 |
| `dewi/accessory-requests` | 2 |
| `dewi/assets` | 2 |
| `dewi/client-portal` | 2 |
| `dewi/kreator-requests` | 2 |
| `dewi/toko` | 2 |
| `hr/inbox` | 2 |
| `hr/job-board` | 2 |
| `marketing/tasks` | 2 |
| `production-pos/{po_id}` | 2 |
| `rahaza/360-feedback` | 2 |
| `rahaza/attendance` | 2 |
| `rahaza/journals` | 2 |
| `rahaza/overtime` | 2 |
| `rahaza/periods` | 2 |
| `wh/returns` | 2 |
| `wms/cmt-dispatches` | 2 |
| `wms/delivery-notes` | 2 |
| `wms/fabric-rolls` | 2 |
| `wms/opname` | 2 |
| `approvals/{event_id}` | 2 |
| `requests/{request_id}` | 2 |
| `acc/loans` | 1 |
| `acc/stock` | 1 |
| `dewi/hris` | 1 |
| `dewi/kasbon` | 1 |
| `dewi/lms` | 1 |
| `finance/bank-recon` | 1 |
| `finance/bank-transfers` | 1 |
| `finance/petty-cash` | 1 |
| `fulfillment/orders` | 1 |
| `marketing/complaints` | 1 |
| `marketing/content-calendar` | 1 |
| `marketing/orders` | 1 |
| `marketing/product-launches` | 1 |
| `marketing/samples` | 1 |
| `rahaza/andon` | 1 |
| `rahaza/boms` | 1 |
| `rahaza/expenses` | 1 |
| `rahaza/orders` | 1 |
| `rahaza/salary-adjustments` | 1 |
| `rahaza/shipments` | 1 |
| `rahaza/work-orders` | 1 |
| `wms/pending` | 1 |
| `wms/picklist` | 1 |
| `{req_id}/approve` | 1 |
| `{req_id}/reject` | 1 |
| `{loan_id}/return` | 1 |
| `{mid}/approve` | 1 |
| `{mid}/cancel` | 1 |
| `{mid}/confirm` | 1 |
| `{mid}/post-to-gl` | 1 |
| `{mid}/reject` | 1 |
| `{mid}/submit` | 1 |
| `{mv_id}/post-to-gl` | 1 |
| `{session_id}/cancel` | 1 |
| `{session_id}/complete` | 1 |
| `receive` | 1 |
| `assign` | 1 |
| `unassign` | 1 |

<details><summary>Daftar lengkap endpoint transisi (klik)</summary>


| Method | Path | File |
|---|---|---|
| PUT | `/api/acc/loans/{loan_id}/return` | dewi_accessories_full_backup.py |
| POST | `/api/acc/opname/{session_id}/cancel` | dewi_accessories_full_backup.py |
| POST | `/api/acc/opname/{session_id}/complete` | dewi_accessories_full_backup.py |
| POST | `/api/acc/stock/receive` | dewi_accessories_full_backup.py |
| POST | `/api/approvals/requests/{request_id}/approve` | approval_multilevel.py |
| POST | `/api/approvals/requests/{request_id}/cancel` | approval_multilevel.py |
| POST | `/api/approvals/requests/{request_id}/reject` | approval_multilevel.py |
| POST | `/api/dewi/accessory-requests/{request_id}/reject` | dewi_accessory_requests.py |
| POST | `/api/dewi/accessory-requests/{request_id}/submit` | dewi_accessory_requests.py |
| POST | `/api/dewi/assets/{asset_id}/assign` | dewi_assets.py |
| POST | `/api/dewi/assets/{asset_id}/return` | dewi_assets.py |
| POST | `/api/dewi/client-portal/samples/{sample_id}/approve` | dewi_client_portal.py |
| POST | `/api/dewi/client-portal/samples/{sample_id}/reject` | dewi_client_portal.py |
| PUT | `/api/dewi/cmt/deliveries/{delivery_id}/receive` | dewi_cmt.py |
| POST | `/api/dewi/cmt/delivery-orders/{do_id}/receive` | dewi_cmt_delivery_orders.py |
| PUT | `/api/dewi/cmt/jobs/{job_id}/status` | dewi_cmt.py |
| PUT | `/api/dewi/cmt/payments/{pay_id}/approve` | dewi_cmt.py |
| PUT | `/api/dewi/cutting/batches/{batch_id}/status` | dewi_cutting.py |
| PUT | `/api/dewi/cutting/requests/{req_id}/approve` | dewi_cutting.py |
| PUT | `/api/dewi/cutting/requests/{req_id}/reject` | dewi_cutting.py |
| PUT | `/api/dewi/hris/performance/reviews/{rid}/submit` | dewi_hris_performance.py |
| POST | `/api/dewi/kasbon/requests/{req_id}/cancel` | dewi_kasbon.py |
| POST | `/api/dewi/kreator-requests/{request_id}/reject` | dewi_kreator_requests.py |
| POST | `/api/dewi/kreator-requests/{request_id}/submit` | dewi_kreator_requests.py |
| POST | `/api/dewi/lms/quizzes/{quiz_id}/submit` | dewi_lms_quiz.py |
| POST | `/api/dewi/maklon/bom-templates/{template_id}/activate` | dewi_maklon_bom_templates.py |
| PUT | `/api/dewi/maklon/dispatches/{dispatch_id}/cancel` | dewi_maklon_pos.py |
| PUT | `/api/dewi/maklon/dispatches/{dispatch_id}/confirm` | dewi_maklon_pos.py |
| POST | `/api/dewi/maklon/invoices/{invoice_id}/cancel` | dewi_maklon_billing.py |
| PUT | `/api/dewi/maklon/orders/{order_id}/status` | dewi_maklon.py |
| POST | `/api/dewi/maklon/pos/{po_id}/cancel` | dewi_maklon_pos.py |
| POST | `/api/dewi/maklon/pos/{po_id}/confirm` | dewi_maklon_pos.py |
| POST | `/api/dewi/maklon/samples/{sample_id}/approve` | dewi_maklon_samples.py |
| POST | `/api/dewi/maklon/samples/{sample_id}/reject` | dewi_maklon_samples.py |
| POST | `/api/dewi/maklon/samples/{sample_id}/submit` | dewi_maklon_samples.py |
| POST | `/api/dewi/rnd/patterns/{pattern_id}/approve` | dewi_rnd_design.py |
| POST | `/api/dewi/rnd/sample-requests/{request_id}/approve` | dewi_rnd_samples.py |
| POST | `/api/dewi/rnd/sample-requests/{request_id}/reject` | dewi_rnd_samples.py |
| POST | `/api/dewi/rnd/sample-requests/{request_id}/submit` | dewi_rnd_samples.py |
| POST | `/api/dewi/rnd/tech-packs/{tp_id}/approve` | dewi_rnd_hpp.py |
| POST | `/api/dewi/toko/flashsales/{flashsale_id}/activate` | dewi_toko.py |
| POST | `/api/dewi/toko/pack-batches/{batch_id}/close` | dewi_online_orders.py |
| POST | `/api/finance/bank-recon/sessions/{session_id}/approve` | dewi_bank_reconciliation.py |
| POST | `/api/finance/bank-transfers/{tf_id}/void` | rahaza_bank_transfers.py |
| POST | `/api/finance/petty-cash/funds/{fund_id}/close` | rahaza_petty_cash.py |
| POST | `/api/fulfillment/orders/{order_id}/dispatch` | fulfillment.py |
| POST | `/api/hr/expenses/claims/{claim_id}/approve` | employee_expense_claims.py |
| POST | `/api/hr/expenses/claims/{claim_id}/reject` | employee_expense_claims.py |
| POST | `/api/hr/expenses/claims/{claim_id}/submit` | employee_expense_claims.py |
| POST | `/api/hr/expenses/settlements/{stl_id}/approve` | employee_travel_settlements.py |
| POST | `/api/hr/expenses/settlements/{stl_id}/post` | employee_travel_settlements.py |
| POST | `/api/hr/expenses/settlements/{stl_id}/reject` | employee_travel_settlements.py |
| POST | `/api/hr/expenses/settlements/{stl_id}/submit` | employee_travel_settlements.py |
| POST | `/api/hr/expenses/travel/{req_id}/approve` | employee_travel_requests.py |
| POST | `/api/hr/expenses/travel/{req_id}/complete` | employee_travel_requests.py |
| POST | `/api/hr/expenses/travel/{req_id}/reject` | employee_travel_requests.py |
| POST | `/api/hr/expenses/travel/{req_id}/submit` | employee_travel_requests.py |
| POST | `/api/hr/inbox/{req_type}/{req_id}/approve` | hr_approval_inbox.py |
| POST | `/api/hr/inbox/{req_type}/{req_id}/reject` | hr_approval_inbox.py |
| PATCH | `/api/hr/job-board/applications/{app_id}/status` | dewi_job_board.py |
| PATCH | `/api/hr/job-board/jobs/{job_id}/close` | dewi_job_board.py |
| POST | `/api/lms/student/assignments/{assignment_id}/submit` | lms_student.py |
| POST | `/api/lms/student/materials/{material_id}/complete` | lms_student.py |
| POST | `/api/lms/student/quiz/{material_id}/submit` | lms_student.py |
| PATCH | `/api/marketing/advanced-ai/ab-tests/{exp_id}/status` | marketing_advanced_ai_routes.py |
| POST | `/api/marketing/advanced-ai/pricing/suggestions/{suggestion_id}/approve` | marketing_advanced_ai_routes.py |
| POST | `/api/marketing/advanced-ai/pricing/suggestions/{suggestion_id}/reject` | marketing_advanced_ai_routes.py |
| PATCH | `/api/marketing/complaints/{complaint_id}/status` | marketing_complaints_routes.py |
| POST | `/api/marketing/content-calendar/{entry_id}/status` | marketing_content_calendar_routes.py |
| POST | `/api/marketing/livehost/portal/training/{progress_id}/complete` | marketing_livehost_portal.py |
| POST | `/api/marketing/livehost/training/assign` | marketing_livehost_training.py |
| POST | `/api/marketing/livehost/training/progress/{progress_id}/complete` | marketing_livehost_training.py |
| PATCH | `/api/marketing/orders/{order_id}/status` | marketing_orders_routes.py |
| POST | `/api/marketing/product-launches/{launch_id}/status` | marketing_product_launches_routes.py |
| POST | `/api/marketing/returns/credit-notes/{cn_id}/post-to-gl` | marketing_returns_routes.py |
| POST | `/api/marketing/returns/{return_id}/approve` | marketing_returns_routes.py |
| POST | `/api/marketing/returns/{return_id}/complete` | marketing_returns_routes.py |
| POST | `/api/marketing/returns/{return_id}/reject` | marketing_returns_routes.py |
| POST | `/api/marketing/samples/{sample_id}/ship` | marketing_samples_routes.py |
| POST | `/api/marketing/tasks/{task_id}/approve` | marketing_tasks.py |
| POST | `/api/marketing/tasks/{task_id}/reject` | marketing_tasks.py |
| POST | `/api/procurement/requests/{req_id}/approve` | dewi_procurement.py |
| POST | `/api/procurement/requests/{req_id}/cancel` | dewi_procurement.py |
| POST | `/api/procurement/requests/{req_id}/complete` | dewi_procurement.py |
| POST | `/api/procurement/requests/{req_id}/reject` | dewi_procurement.py |
| POST | `/api/procurement/requests/{req_id}/submit` | dewi_procurement.py |
| POST | `/api/prod/cmt-receipts/{receipt_id}/approve` | dewi_cmt_packing.py |
| POST | `/api/prod/cmt-receipts/{receipt_id}/reject` | dewi_cmt_packing.py |
| POST | `/api/prod/cmt-receipts/{receipt_id}/submit` | dewi_cmt_packing.py |
| POST | `/api/production-pos/{po_id}/close` | production_po.py |
| POST | `/api/production-pos/{po_id}/status` | production_po.py |
| POST | `/api/production/material-returns/{return_id}/approve` | production_material_returns.py |
| POST | `/api/production/material-returns/{return_id}/receive` | production_material_returns.py |
| POST | `/api/production/material-returns/{return_id}/reject` | production_material_returns.py |
| POST | `/api/production/material-returns/{return_id}/submit` | production_material_returns.py |
| POST | `/api/rahaza/360-feedback/cycles/{cycle_id}/close` | rahaza_360_feedback.py |
| POST | `/api/rahaza/360-feedback/cycles/{cycle_id}/submit` | rahaza_360_feedback.py |
| POST | `/api/rahaza/andon/{event_id}/cancel` | rahaza_andon.py |
| POST | `/api/rahaza/ap-invoices/{iid}/payment` | rahaza_finance.py |
| POST | `/api/rahaza/ap-invoices/{iid}/post-to-gl` | rahaza_finance.py |
| POST | `/api/rahaza/ap-invoices/{iid}/status` | rahaza_finance.py |
| POST | `/api/rahaza/ar-invoices/{iid}/payment` | rahaza_finance.py |
| POST | `/api/rahaza/ar-invoices/{iid}/post-to-gl` | rahaza_finance.py |
| POST | `/api/rahaza/ar-invoices/{iid}/status` | rahaza_finance.py |
| POST | `/api/rahaza/attendance/approvals/{event_id}/approve` | rahaza_auto_attendance_backup.py |
| POST | `/api/rahaza/attendance/approvals/{event_id}/reject` | rahaza_auto_attendance_backup.py |
| POST | `/api/rahaza/boms/{bid}/activate` | rahaza_bom.py |
| POST | `/api/rahaza/expenses/{eid}/post-to-gl` | rahaza_finance.py |
| POST | `/api/rahaza/finance/accruals/{accrual_id}/post` | rahaza_accruals.py |
| POST | `/api/rahaza/finance/accruals/{accrual_id}/reverse` | rahaza_accruals.py |
| POST | `/api/rahaza/finance/bank-recon-adjustments/{adjustment_id}/post` | rahaza_bank_recon.py |
| POST | `/api/rahaza/finance/budgets/{bid}/approve` | rahaza_budget.py |
| POST | `/api/rahaza/finance/budgets/{bid}/reopen` | rahaza_budget.py |
| POST | `/api/rahaza/journals/{je_id}/post` | rahaza_journals.py |
| POST | `/api/rahaza/journals/{je_id}/void` | rahaza_journals.py |
| POST | `/api/rahaza/leaves/{leave_id}/approve` | rahaza_leave.py |
| POST | `/api/rahaza/leaves/{leave_id}/cancel` | rahaza_leave.py |
| POST | `/api/rahaza/leaves/{leave_id}/reject` | rahaza_leave.py |
| POST | `/api/rahaza/orders/{oid}/status` | rahaza_orders.py |
| PUT | `/api/rahaza/overtime/{ot_id}/approve` | rahaza_overtime.py |
| PUT | `/api/rahaza/overtime/{ot_id}/reject` | rahaza_overtime.py |
| POST | `/api/rahaza/payroll-runs/{run_id}/finalize` | rahaza_payroll_runs.py |
| POST | `/api/rahaza/payroll-runs/{run_id}/post-to-gl` | rahaza_payroll_runs.py |
| POST | `/api/rahaza/payroll-runs/{run_id}/void-payment` | rahaza_payroll_runs.py |
| POST | `/api/rahaza/periods/{period_code}/close` | rahaza_periods.py |
| POST | `/api/rahaza/periods/{period_code}/reopen` | rahaza_periods.py |
| POST | `/api/rahaza/purchase-orders/{po_id}/approve` | rahaza_po.py |
| POST | `/api/rahaza/purchase-orders/{po_id}/cancel` | rahaza_po.py |
| POST | `/api/rahaza/purchase-orders/{po_id}/reject` | rahaza_po.py |
| POST | `/api/rahaza/purchase-orders/{po_id}/submit` | rahaza_po.py |
| POST | `/api/rahaza/salary-adjustments/{adj_id}/reject` | rahaza_salary_adjustments.py |
| POST | `/api/rahaza/shipments/{sid}/status` | rahaza_shipments.py |
| POST | `/api/rahaza/work-orders/{wid}/status` | rahaza_work_orders.py |
| POST | `/api/wh/returns/{return_id}/cancel` | dewi_wh_returns.py |
| POST | `/api/wh/returns/{return_id}/receive` | dewi_wh_returns.py |
| POST | `/api/wms/cmt-dispatches/{dispatch_id}/cancel` | wms_cmt_dispatches.py |
| POST | `/api/wms/cmt-dispatches/{dispatch_id}/dispatch` | wms_cmt_dispatches.py |
| POST | `/api/wms/delivery-notes/{sj_id}/cancel` | wms_delivery_notes.py |
| POST | `/api/wms/delivery-notes/{sj_id}/receive` | wms_delivery_notes.py |
| POST | `/api/wms/fabric-rolls/{roll_id}/reject` | wms_fabric_rolls.py |
| POST | `/api/wms/fabric-rolls/{roll_id}/return` | wms_fabric_rolls.py |
| POST | `/api/wms/opname/{session_id}/cancel` | wms_opname.py |
| POST | `/api/wms/opname/{session_id}/complete` | wms_opname.py |
| POST | `/api/wms/opname2/{session_id}/approve` | wms_opname2.py |
| POST | `/api/wms/opname2/{session_id}/cancel` | wms_opname2.py |
| POST | `/api/wms/opname2/{session_id}/submit` | wms_opname2.py |
| POST | `/api/wms/pending/{movement_id}/cancel` | wms_receiving.py |
| POST | `/api/wms/picklist/{picklist_id}/complete` | wms_picklist.py |
| POST | `/attendance/approvals/{event_id}/approve` | rahaza_auto_attendance_approvals.py |
| POST | `/attendance/approvals/{event_id}/reject` | rahaza_auto_attendance_approvals.py |
| PATCH | `/disposal-requests/{req_id}/approve` | disposal.py |
| PATCH | `/disposal-requests/{req_id}/reject` | disposal.py |
| POST | `/kol/requests/{request_id}/approve` | marketing_kol_ops.py |
| POST | `/kol/requests/{request_id}/reject` | marketing_kol_ops.py |
| PUT | `/loans/{loan_id}/return` | dewi_accessories_loans.py |
| POST | `/material-issues/{mid}/approve` | rahaza_inventory_issues.py |
| POST | `/material-issues/{mid}/cancel` | rahaza_inventory_workflow.py |
| POST | `/material-issues/{mid}/confirm` | rahaza_inventory_workflow.py |
| POST | `/material-issues/{mid}/post-to-gl` | rahaza_inventory_workflow.py |
| POST | `/material-issues/{mid}/reject` | rahaza_inventory_issues.py |
| POST | `/material-issues/{mid}/submit` | rahaza_inventory_issues.py |
| POST | `/material-movements/{mv_id}/post-to-gl` | rahaza_inventory_workflow.py |
| POST | `/opname/{session_id}/cancel` | dewi_accessories_opname.py |
| POST | `/opname/{session_id}/complete` | dewi_accessories_opname.py |
| POST | `/stock/receive` | dewi_accessories_stock.py |
| POST | `/{asset_id}/assign` | assignments.py |
| POST | `/{asset_id}/unassign` | assignments.py |

</details>


## Catatan

- AUDIT 1 aman total (GET). Endpoint `{param}` diisi `probe`; 404 handler-level itu normal, hanya 5xx yang dianggap temuan.
- AUDIT 2 sengaja **tidak** menembak endpoint (mencegah mutasi/polusi DB). Untuk memvalidasi transisi ilegal butuh seed synthetic + probe + cleanup (seperti R8/R9) — direkomendasikan sebagai audit lanjutan bila diizinkan.
