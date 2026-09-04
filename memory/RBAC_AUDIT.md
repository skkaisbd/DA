# 🔐 RBAC / BROKEN-ACCESS-CONTROL AUDIT — Discovery Report

> Mode: **DISCOVERY** (tanpa perbaikan). Uji: user role **`operator`** (custom role, **0 permission**) mencoba aksi sensitif.

> Write ber-`{param}` diuji dgn **ghost id** (entitas nyata tak tersentuh); create tanpa-param diuji body kosong + cleanup id.

> Low-priv login: OK (role=operator)

> Target sensitif: GET **95** · write ber-param **172** · create tanpa-param **100**

> Cleanup: purged **5** · residual user **0** · residual ghost-docs **0** → PRISTINE


**Interpretasi:** `403`=terlindungi (baik). Selain 403 (404/400/422/500/2xx) = otorisasi role **tidak** memblokir → **temuan BAC** (endpoint hanya cek login, bukan role).


---


## 🔴 A — GET sensitif BOCOR ke role rendah (200/handler) — **73**

> 200 = kebocoran data sensitif ke operator. Lain (404/500) = tetap terjangkau tanpa cek role.

| Method | Path | HTTP | File |
|---|---|---:|---|
| GET | `/api/acc/opname` | 200 | dewi_accessories_full_backup.py |
| GET | `/api/acc/opname/{session_id}` | 404 | dewi_accessories_full_backup.py |
| GET | `/api/auth/users` | 200 | auth_routes.py |
| GET | `/api/company-settings` | 200 | admin.py |
| GET | `/api/dewi/cmt/payments` | 404 | dewi_cmt.py |
| GET | `/api/dewi/hris/performance/assignments` | 200 | dewi_hris_performance.py |
| GET | `/api/dewi/hris/performance/assignments/{aid}` | 404 | dewi_hris_performance.py |
| GET | `/api/dewi/maklon/payments` | 200 | dewi_maklon_billing.py |
| GET | `/api/finance/bank-recon/gl-entries` | 422 | dewi_bank_reconciliation.py |
| GET | `/api/finance/bank-transfers` | 200 | rahaza_bank_transfers.py |
| GET | `/api/finance/bank-transfers/{tf_id}` | 404 | rahaza_bank_transfers.py |
| GET | `/api/global-search` | 200 | dashboard_routes.py |
| GET | `/api/hr/ai/coaching/history` | 200 | dewi_hr_ai.py |
| GET | `/api/hr/expenses/gl-mappings/resolve/{category}` | 200 | employee_expense_gl_mapping.py |
| GET | `/api/hr/expenses/settlement-summary` | 200 | employee_travel_settlements.py |
| GET | `/api/hr/expenses/settlements` | 200 | employee_travel_settlements.py |
| GET | `/api/hr/expenses/settlements/export` | 200 | employee_travel_settlements.py |
| GET | `/api/hr/expenses/settlements/{stl_id}` | 404 | employee_travel_settlements.py |
| GET | `/api/hr/expenses/travel/{req_id}/settlements` | 404 | employee_travel_settlements.py |
| GET | `/api/hr/shifts/assignments` | 200 | hr_shifts.py |
| GET | `/api/hr/shifts/assignments/employee/{employee_id}` | 200 | hr_shifts.py |
| GET | `/api/lms/student/courses/{course_id}/assignments` | 404 | lms_student.py |
| GET | `/api/management/audit/permissions` | 200 | dewi_management_tools.py |
| GET | `/api/marketing/livehost/payment/status` | 422 | marketing_livehost_analytics.py |
| GET | `/api/payroll/automation/alerts` | 200 | payroll_automation.py |
| GET | `/api/payroll/automation/attendance-sync` | 422 | payroll_automation.py |
| GET | `/api/payroll/automation/dashboard` | 200 | payroll_automation.py |
| GET | `/api/payroll/automation/history` | 200 | payroll_automation.py |
| GET | `/api/payroll/automation/schedule` | 200 | payroll_automation.py |
| GET | `/api/portal-saya/me/payslips` | 409 | dewi_portal_saya_ext.py |
| GET | `/api/portal/payslips` | 409 | dewi_portal_saya_backup.py |
| GET | `/api/push/status` | 200 | dewi_push_notifications.py |
| GET | `/api/rahaza/finance/fixed-assets/depreciation-due` | 200 | rahaza_fixed_assets.py |
| GET | `/api/rahaza/finance/fixed-assets/depreciation-summary` | 200 | rahaza_fixed_assets.py |
| GET | `/api/rahaza/finance/reports/balance-sheet` | 200 | rahaza_fin_reports.py |
| GET | `/api/rahaza/finance/reports/general-ledger` | 422 | rahaza_fin_reports.py |
| GET | `/api/rahaza/finance/reports/journal-list` | 200 | rahaza_fin_reports.py |
| GET | `/api/rahaza/finance/reports/profit-loss` | 200 | rahaza_fin_reports.py |
| GET | `/api/rahaza/finance/reports/trial-balance` | 200 | rahaza_fin_reports.py |
| GET | `/api/rahaza/grn-qc/reject-categories` | 200 | rahaza_grn_qc.py |
| GET | `/api/rahaza/line-assignments` | 200 | rahaza_production.py |
| GET | `/api/rahaza/management/payroll-summary` | 200 | rahaza_reports.py |
| GET | `/api/rahaza/payroll-allowances` | 200 | rahaza_payroll_allowances.py |
| GET | `/api/rahaza/payroll-profiles` | 200 | rahaza_payroll_profiles.py |
| GET | `/api/rahaza/payroll-profiles/{employee_id}` | 404 | rahaza_payroll_profiles.py |
| GET | `/api/rahaza/payroll-runs/{run_id}/pdf` | 404 | rahaza_payroll_payslips.py |
| GET | `/api/rahaza/payslips` | 200 | rahaza_payroll_payslips.py |
| GET | `/api/rahaza/payslips/{pid}` | 404 | rahaza_payroll_payslips.py |
| GET | `/api/rahaza/payslips/{pid}/pdf` | 404 | rahaza_payroll_payslips.py |
| GET | `/api/rahaza/posting-profiles` | 200 | rahaza_posting_profiles.py |
| GET | `/api/rahaza/posting-profiles/{event_type}` | 404 | rahaza_posting_profiles.py |
| GET | `/api/rahaza/salary-adjustments` | 200 | rahaza_salary_adjustments.py |
| GET | `/api/rahaza/salary-adjustments/my/pending-approvals` | 200 | rahaza_salary_adjustments.py |
| GET | `/api/rahaza/salary-adjustments/stats/summary` | 200 | rahaza_salary_adjustments.py |
| GET | `/api/rahaza/salary-adjustments/{adj_id}` | 404 | rahaza_salary_adjustments.py |
| GET | `/api/rahaza/salary-grades` | 200 | rahaza_salary_grades.py |
| GET | `/api/rahaza/salary-grades/audit` | 200 | rahaza_salary_grades.py |
| GET | `/api/rahaza/self/payslip/{slip_id}` | 409 | rahaza_self.py |
| GET | `/api/rahaza/self/payslips` | 409 | rahaza_self.py |
| GET | `/api/rahaza/setup/status` | 200 | rahaza_setup.py |
| GET | `/api/rahaza/supervisor/assignments/yesterday` | 200 | rahaza_production.py |
| GET | `/api/rahaza/supervisor/assignments/yesterday` | 200 | rahaza_sprint22.py |
| GET | `/api/warehouse/opname` | 200 | warehouse.py |
| GET | `/api/warehouse/opname/{opname_id}` | 404 | warehouse.py |
| GET | `/api/wms/legacy/opname` | 200 | wms_legacy.py |
| GET | `/api/wms/legacy/opname/{opname_id}` | 404 | wms_legacy.py |
| GET | `/api/wms/opname` | 200 | wms_opname.py |
| GET | `/api/wms/opname/{session_id}` | 404 | wms_opname.py |
| GET | `/api/wms/opname2` | 200 | wms_opname2.py |
| GET | `/api/wms/opname2/stats` | 200 | wms_opname2.py |
| GET | `/api/wms/opname2/{session_id}` | 404 | wms_opname2.py |
| GET | `/api/wms/opname2/{session_id}/count-sheet-pdf` | 404 | wms_opname2.py |
| GET | `/api/wms/stock/status` | 200 | wms_receiving.py |


## 🔴 B — AKSI sensitif ber-`{param}` terjangkau role rendah (bukan 403) — **104**

> Ghost-id → 404/400/500 berarti request LOLOS otorisasi & sampai handler (baru gagal krn entitas hantu). Seharusnya **403**.

| Method | Path | HTTP | File |
|---|---|---:|---|
| DELETE | `/api/dewi/maklon/payments/{payment_id}` | 404 | dewi_maklon_billing.py |
| DELETE | `/api/hr/shifts/assignments/{assignment_id}` | 200 | hr_shifts.py |
| DELETE | `/api/rahaza/payroll-allowances/{allowance_id}` | 200 | rahaza_payroll_allowances.py |
| PATCH | `/api/dewi/kasbon/requests/{req_id}/disburse` | 404 | dewi_kasbon.py |
| PATCH | `/api/hr/job-board/applications/{app_id}/status` | 422 | dewi_job_board.py |
| PATCH | `/api/marketing/advanced-ai/ab-tests/{exp_id}/status` | 422 | marketing_advanced_ai_routes.py |
| PATCH | `/api/marketing/complaints/{complaint_id}/status` | 422 | marketing_complaints_routes.py |
| PATCH | `/api/marketing/orders/{order_id}/status` | 422 | marketing_orders_routes.py |
| PATCH | `/disposal-requests/{req_id}/approve` | 404 | disposal.py |
| PATCH | `/disposal-requests/{req_id}/reject` | 404 | disposal.py |
| POST | `/api/acc/opname/{session_id}/cancel` | 404 | dewi_accessories_full_backup.py |
| POST | `/api/acc/opname/{session_id}/complete` | 404 | dewi_accessories_full_backup.py |
| POST | `/api/approvals/requests/{request_id}/approve` | 400 | approval_multilevel.py |
| POST | `/api/approvals/requests/{request_id}/cancel` | 404 | approval_multilevel.py |
| POST | `/api/approvals/requests/{request_id}/reject` | 400 | approval_multilevel.py |
| POST | `/api/dewi/accessory-requests/{request_id}/reject` | 404 | dewi_accessory_requests.py |
| POST | `/api/dewi/cutting/batches/{batch_id}/reject-roll` | 404 | dewi_cutting.py |
| POST | `/api/dewi/kasbon/requests/{req_id}/cancel` | 404 | dewi_kasbon.py |
| POST | `/api/dewi/kreator-requests/{request_id}/approve-by-rnd` | 404 | dewi_kreator_requests.py |
| POST | `/api/dewi/kreator-requests/{request_id}/reject` | 404 | dewi_kreator_requests.py |
| POST | `/api/dewi/maklon/invoices/{invoice_id}/cancel` | 404 | dewi_maklon_billing.py |
| POST | `/api/dewi/maklon/pos/{po_id}/cancel` | 404 | dewi_maklon_pos.py |
| POST | `/api/dewi/maklon/samples/{sample_id}/approve` | 404 | dewi_maklon_samples.py |
| POST | `/api/dewi/maklon/samples/{sample_id}/reject` | 422 | dewi_maklon_samples.py |
| POST | `/api/dewi/rnd/patterns/{pattern_id}/approve` | 200 | dewi_rnd_design.py |
| POST | `/api/dewi/rnd/sample-requests/{request_id}/approve` | 404 | dewi_rnd_samples.py |
| POST | `/api/dewi/rnd/sample-requests/{request_id}/reject` | 404 | dewi_rnd_samples.py |
| POST | `/api/dewi/rnd/styles/{style_id}/owner-approve` | 404 | dewi_rnd_styles.py |
| POST | `/api/dewi/rnd/styles/{style_id}/owner-reject` | 404 | dewi_rnd_styles.py |
| POST | `/api/dewi/rnd/tech-packs/{tp_id}/approve` | 200 | dewi_rnd_hpp.py |
| POST | `/api/finance/bank-recon/sessions/{session_id}/approve` | 404 | dewi_bank_reconciliation.py |
| POST | `/api/hr/ai/coaching/{employee_id}` | 404 | dewi_hr_ai.py |
| POST | `/api/hr/expenses/claims/{claim_id}/reject` | 422 | employee_expense_claims.py |
| POST | `/api/hr/expenses/settlements/{stl_id}/reject` | 422 | employee_travel_settlements.py |
| POST | `/api/hr/expenses/settlements/{stl_id}/submit` | 404 | employee_travel_settlements.py |
| POST | `/api/hr/expenses/travel/{req_id}/reject` | 422 | employee_travel_requests.py |
| POST | `/api/hr/expenses/travel/{req_id}/settlements` | 404 | employee_travel_settlements.py |
| POST | `/api/lms/student/assignments/{assignment_id}/submit` | 404 | lms_student.py |
| POST | `/api/marketing/advanced-ai/pricing/suggestions/{suggestion_id}/approve` | 404 | marketing_advanced_ai_routes.py |
| POST | `/api/marketing/advanced-ai/pricing/suggestions/{suggestion_id}/reject` | 404 | marketing_advanced_ai_routes.py |
| POST | `/api/marketing/content-calendar/{entry_id}/status` | 400 | marketing_content_calendar_routes.py |
| POST | `/api/marketing/product-launches/{launch_id}/status` | 400 | marketing_product_launches_routes.py |
| POST | `/api/marketing/returns/credit-notes/{cn_id}/post-to-gl` | 404 | marketing_returns_routes.py |
| POST | `/api/marketing/returns/{return_id}/approve` | 404 | marketing_returns_routes.py |
| POST | `/api/marketing/returns/{return_id}/reject` | 404 | marketing_returns_routes.py |
| POST | `/api/marketing/tasks/{task_id}/reject` | 422 | marketing_tasks.py |
| POST | `/api/procurement/requests/{req_id}/approve` | 404 | dewi_procurement.py |
| POST | `/api/procurement/requests/{req_id}/cancel` | 404 | dewi_procurement.py |
| POST | `/api/procurement/requests/{req_id}/reject` | 404 | dewi_procurement.py |
| POST | `/api/prod/cmt-receipts/{receipt_id}/approve` | 404 | dewi_cmt_packing.py |
| POST | `/api/prod/cmt-receipts/{receipt_id}/reject` | 404 | dewi_cmt_packing.py |
| POST | `/api/rahaza/andon/{event_id}/cancel` | 404 | rahaza_andon.py |
| POST | `/api/rahaza/finance/accruals/{accrual_id}/reverse` | 404 | rahaza_accruals.py |
| POST | `/api/rahaza/finance/budgets/{bid}/approve` | 404 | rahaza_budget.py |
| POST | `/api/rahaza/finance/fixed-assets/{aid}/dispose` | 404 | rahaza_fixed_assets.py |
| POST | `/api/rahaza/hr/employee-loans/{loan_id}/deduct-from-payroll` | 404 | rahaza_employee_loans.py |
| POST | `/api/rahaza/leaves/{leave_id}/cancel` | 404 | rahaza_leave.py |
| POST | `/api/rahaza/salary-adjustments/{adj_id}/approve-manager` | 404 | rahaza_salary_adjustments.py |
| POST | `/api/rahaza/salary-adjustments/{adj_id}/reject` | 404 | rahaza_salary_adjustments.py |
| POST | `/api/rahaza/shipments/{sid}/status` | 404 | rahaza_shipments.py |
| POST | `/api/wh/returns/{return_id}/cancel` | 404 | dewi_wh_returns.py |
| POST | `/api/wms/cmt-dispatches/{dispatch_id}/cancel` | 404 | wms_cmt_dispatches.py |
| POST | `/api/wms/delivery-notes/{sj_id}/cancel` | 404 | wms_delivery_notes.py |
| POST | `/api/wms/fabric-rolls/{roll_id}/reject` | 422 | wms_fabric_rolls.py |
| POST | `/api/wms/opname/{session_id}/cancel` | 404 | wms_opname.py |
| POST | `/api/wms/opname/{session_id}/complete` | 404 | wms_opname.py |
| POST | `/api/wms/opname/{session_id}/scan` | 422 | wms_opname.py |
| POST | `/api/wms/opname2/{session_id}/approve` | 404 | wms_opname2.py |
| POST | `/api/wms/opname2/{session_id}/cancel` | 404 | wms_opname2.py |
| POST | `/api/wms/opname2/{session_id}/scan` | 422 | wms_opname2.py |
| POST | `/api/wms/opname2/{session_id}/submit` | 404 | wms_opname2.py |
| POST | `/api/wms/pending/{movement_id}/cancel` | 404 | wms_receiving.py |
| POST | `/attendance/approvals/{event_id}/approve` | 404 | rahaza_auto_attendance_approvals.py |
| POST | `/attendance/approvals/{event_id}/reject` | 404 | rahaza_auto_attendance_approvals.py |
| POST | `/batch-depreciate/{period}` | 404 | depreciation_batch.py |
| POST | `/kol/requests/{request_id}/approve` | 404 | marketing_kol_ops.py |
| POST | `/kol/requests/{request_id}/reject` | 404 | marketing_kol_ops.py |
| POST | `/material-issues/{mid}/approve` | 404 | rahaza_inventory_issues.py |
| POST | `/material-issues/{mid}/cancel` | 404 | rahaza_inventory_workflow.py |
| POST | `/material-issues/{mid}/post-to-gl` | 404 | rahaza_inventory_workflow.py |
| POST | `/material-issues/{mid}/reject` | 404 | rahaza_inventory_issues.py |
| POST | `/material-movements/{mv_id}/post-to-gl` | 404 | rahaza_inventory_workflow.py |
| POST | `/opname/{session_id}/cancel` | 404 | dewi_accessories_opname.py |
| POST | `/opname/{session_id}/complete` | 404 | dewi_accessories_opname.py |
| POST | `/{asset_id}/assign` | 404 | assignments.py |
| POST | `/{asset_id}/depreciate/{period}` | 404 | depreciation_per.py |
| POST | `/{asset_id}/dispose` | 404 | disposal.py |
| POST | `/{asset_id}/transfer` | 404 | transfer.py |
| POST | `/{asset_id}/unassign` | 404 | assignments.py |
| PUT | `/api/acc/opname/{session_id}/count` | 400 | dewi_accessories_full_backup.py |
| PUT | `/api/dewi/cmt/jobs/{job_id}/status` | 404 | dewi_cmt.py |
| PUT | `/api/dewi/cmt/payments/{pay_id}/approve` | 404 | dewi_cmt.py |
| PUT | `/api/dewi/cmt/payments/{pay_id}/paid` | 404 | dewi_cmt.py |
| PUT | `/api/dewi/cutting/batches/{batch_id}/status` | 422 | dewi_cutting.py |
| PUT | `/api/dewi/cutting/requests/{req_id}/approve` | 404 | dewi_cutting.py |
| PUT | `/api/dewi/cutting/requests/{req_id}/reject` | 404 | dewi_cutting.py |
| PUT | `/api/dewi/hris/performance/assignments/{aid}` | 404 | dewi_hris_performance.py |
| PUT | `/api/dewi/maklon/dispatches/{dispatch_id}/cancel` | 404 | dewi_maklon_pos.py |
| PUT | `/api/dewi/maklon/orders/{order_id}/status` | 404 | dewi_maklon.py |
| PUT | `/api/hr/expenses/settlements/{stl_id}` | 404 | employee_travel_settlements.py |
| PUT | `/api/rahaza/payroll-allowances/{allowance_id}` | 404 | rahaza_payroll_allowances.py |
| PUT | `/api/warehouse/opname/{opname_id}` | 404 | warehouse.py |
| PUT | `/api/wms/legacy/opname/{opname_id}` | 404 | wms_legacy.py |
| PUT | `/opname/{session_id}/count` | 404 | dewi_accessories_opname.py |


## 🔴 C — CREATE sensitif tanpa-param terjangkau role rendah (bukan 403) — **54**

| Method | Path | HTTP | File |
|---|---|---:|---|
| DELETE | `/api/dewi/cmt/seed/vendor-demo` | 404 | dewi_cmt_seed.py |
| POST | `/api/acc/opname` | 201 | dewi_accessories_full_backup.py |
| POST | `/api/admin/backup/restore` | 422 | admin_backup.py |
| POST | `/api/admin/backup/restore-selective` | 422 | admin_backup.py |
| POST | `/api/dewi/cmt/payments` | 404 | dewi_cmt.py |
| POST | `/api/dewi/cmt/seed/vendor-demo` | 404 | dewi_cmt_seed.py |
| POST | `/api/dewi/hris/performance/assignments` | 422 | dewi_hris_performance.py |
| POST | `/api/dewi/kasbon/apply-payroll-deductions` | 400 | dewi_kasbon.py |
| POST | `/api/dewi/kasbon/seed` | 200 | dewi_kasbon.py |
| POST | `/api/dewi/kpi/gamification/seed-demo` | 200 | dewi_kpi_gamification.py |
| POST | `/api/dewi/lms/seed` | 200 | dewi_lms.py |
| POST | `/api/dewi/maklon/payments` | 422 | dewi_maklon_billing.py |
| POST | `/api/dewi/onboarding/seed` | 200 | dewi_onboarding.py |
| POST | `/api/dewi/org/seed` | 200 | dewi_org.py |
| POST | `/api/dewi/recruitment/seed` | 200 | dewi_recruitment.py |
| POST | `/api/dewi/rnd/seed` | 200 | dewi_rnd_overview.py |
| POST | `/api/finance/bank-transfers` | 422 | rahaza_bank_transfers.py |
| POST | `/api/hr/expenses/claims/bulk-approve` | 422 | employee_expense_claims.py |
| POST | `/api/hr/expenses/gl-mappings` | 422 | employee_expense_gl_mapping.py |
| POST | `/api/hr/expenses/gl-mappings/bulk-resolve` | 422 | employee_expense_gl_mapping.py |
| POST | `/api/hr/expenses/settlements/bulk-approve` | 422 | employee_travel_settlements.py |
| POST | `/api/hr/expenses/settlements/bulk-post` | 422 | employee_travel_settlements.py |
| POST | `/api/hr/expenses/travel/bulk-approve` | 422 | employee_travel_requests.py |
| POST | `/api/hr/shifts/assignments` | 422 | hr_shifts.py |
| POST | `/api/marketing/catalogs/seed-demo` | 200 | marketing_catalog_backup.py |
| POST | `/api/marketing/catalogs/seed-demo` | 200 | marketing_catalog_stock.py |
| POST | `/api/marketing/livehost/payment/calculate` | 422 | marketing_livehost_analytics.py |
| POST | `/api/marketing/livehost/payment/sync-to-finance` | 422 | marketing_livehost_analytics.py |
| POST | `/api/marketing/livehost/training/assign` | 422 | marketing_livehost_training.py |
| POST | `/api/marketing/seed-sample-data` | 200 | marketing_dashboard.py |
| POST | `/api/payroll/automation/attendance-sync` | 422 | payroll_automation.py |
| POST | `/api/payroll/automation/schedule` | 200 | payroll_automation.py |
| POST | `/api/payroll/automation/trigger` | 422 | payroll_automation.py |
| POST | `/api/rahaza/defect-codes/seed` | 200 | rahaza_qc_v2.py |
| POST | `/api/rahaza/fg-matrix/seed-demo` | 200 | rahaza_fg_matrix.py |
| POST | `/api/rahaza/finance/fixed-assets/run-batch-depreciation` | 200 | rahaza_fixed_assets.py |
| POST | `/api/rahaza/grn-qc/seed-demo` | 200 | rahaza_grn_qc.py |
| POST | `/api/rahaza/handover-templates/seed-default` | 200 | rahaza_shift_handover.py |
| POST | `/api/rahaza/hr/employee-loans/disburse` | 400 | rahaza_employee_loans.py |
| POST | `/api/rahaza/payroll-allowances` | 400 | rahaza_payroll_allowances.py |
| POST | `/api/rahaza/production-calendar/seed-national` | 200 | rahaza_production_calendar.py |
| POST | `/api/rahaza/supervisor/assignments/bulk` | 200 | rahaza_production.py |
| POST | `/api/rahaza/supervisor/assignments/bulk` | 200 | rahaza_sprint22.py |
| POST | `/api/warehouse/opname` | 200 | warehouse.py |
| POST | `/api/wms/ai/opname/predict-variances` | 200 | wms_ai_insights.py |
| POST | `/api/wms/legacy/opname` | 200 | wms_legacy.py |
| POST | `/api/wms/opname/start` | 422 | wms_opname.py |
| POST | `/api/wms/opname2/start` | 200 | wms_opname2.py |
| POST | `/api/wms/structure/seed-demo` | 200 | wms_structure.py |
| POST | `/api/wms/units/seed` | 200 | wms_units.py |
| POST | `/kol/seed-demo` | 404 | marketing_kol_ops.py |
| POST | `/material-adjust` | 404 | rahaza_inventory_stock.py |
| POST | `/material-transfer` | 404 | rahaza_inventory_stock.py |
| POST | `/opname` | 404 | dewi_accessories_opname.py |


## 🟢 Terlindungi (403) — **134** · dilewati (405/401/neterr) — **2**


## Batasan

- 'BAC' di sini = **otorisasi role tidak memblokir** (endpoint hanya `require_auth`). Sebagian mungkin **memang** boleh diakses semua staff (by-design) — WAJIB tinjau manual per baris untuk memastikan sensitivitasnya.
- Tidak ada mutasi data nyata (ghost id + cleanup id + verifikasi residual = 0).
