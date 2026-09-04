# 🔧 SSOT MASTER REPAIR PLAN — BAGIAN 2 (RC-08..RC-14 + Backlog + Roadmap + Appendix)
> Lanjutan dari `SSOT_MASTER_REPAIR_PLAN.md`. Patuhi **GOLDEN RULES** & **SSOT REGISTRY** di file utama.

---

# BAGIAN 2B — REPAIR CARDS (RC-08 s/d RC-14)

## 🟠 RC-08 — Cashflow AI (`dewi_cashflow_ai.py`)
- **Prioritas:** P1. **Dampak:** **RahazaCashFlowModule.jsx** — proyeksi arus kas salah (penerimaan/pengeluaran aktual selalu kosong).
- **AKAR MASALAH:** Baca koleksi pembayaran yang tak ada; padahal pembayaran nyata dicatat sebagai *cash movement* + JE.
- **Item:**
  | Baris | ❌ Baca | ✅ SSOT | Peta |
  |---|---|---|---|
  | 95 | `rahaza_ar_receipts` (phantom) | `rahaza_cash_movements`(32) `direction:'in'` | `amount`,`date` |
  | 101 | `rahaza_ap_payments` (phantom) | `rahaza_cash_movements`(32) `direction:'out'` | `amount`,`date` |
  | 108,113 | `bank_recon_sessions`,`bank_recon_txns` (phantom) | ⚠ STOP-VERIFY (koleksi bank recon nyata; cek `dewi_bank_reconciliation.py`) | — |
  | 40,66,122,128 | `rahaza_ar_invoices`,`rahaza_ap_invoices` | BENAR (jangan ubah) | — |
- **⚠ STOP-VERIFY:** `distinct('direction')` & `distinct('category')` di `rahaza_cash_movements` untuk memilah AR receipt vs AP payment vs lainnya. Alternatif: agregasi `rahaza_journal_entries` `source_module in [ar_payment, ap_payment]`.
- **VERIFIKASI:** endpoint cashflow → penerimaan/pengeluaran > 0. **RISIKO:** Sedang.

## 🟠 RC-09 — AR-360 Statement (`rahaza_ar_360.py`) — pembayaran standalone stale
- **Prioritas:** P1. **AKAR:** `:370` baca `rahaza_ar_payments`(10, seed-only) sbg pembayaran standalone; juga baca payments embedded di invoice (`:355`). Pembayaran AR live diposting via `post_ar_payment` (JE + `rahaza_cash_movements`), **bukan** ke `rahaza_ar_payments` → statement kehilangan pembayaran baru.
- **⚠ STOP-VERIFY:** konfirmasi di mana pembayaran AR live tersimpan (embedded `invoice.payments[]`? `rahaza_cash_movements` `ref_id=invoice`? JE `source_module=ar_payment`?). Repoint jalur standalone ke SSOT itu, atau hapus jalur ganda bila redundan.
- **RISIKO:** Sedang. **DO-NOT:** jangan hapus baca embedded (masih dipakai sebagian flow).

## 🟠 RC-10 — Employee Expense GL Mapping (`employee_expense_gl_mapping.py`, `rahaza_admin.py`)
- **Prioritas:** P1. **AKAR:** baca phantom `rahaza_coa` & `rahaza_bank_accounts`. **FIX:** `rahaza_coa`→`rahaza_coa_accounts`(97); `rahaza_bank_accounts`→`rahaza_cash_accounts`(4). Terkait erat RC-05 (kerjakan bersama).
- **VERIFIKASI:** endpoint GL-mapping mengembalikan daftar akun COA nyata. **RISIKO:** Rendah.

## 🟠 RC-11 — Produksi/Report Misroute (variances, control tower, phase7)
- **Prioritas:** P1.
  | File | ❌ Baca | ✅ SSOT | Catatan |
  |---|---|---|---|
  | `production_variances.py` | `rahaza_products` | `rahaza_models`(3) | — |
  | `production_control_tower.py` | `rahaza_wo_bundles` | `rahaza_bundles`(45) | ⚠ verifikasi field bundle |
  | `dewi_phase7_reports.py` | `dewi_invoices` | `dewi_maklon_invoices`(3) | juga baca `dewi_cmt_progress_reports`(0, dorman) |
- **RISIKO:** Rendah. **DO-NOT:** untuk CMT dorman → jangan karang; tampilkan 0/kosong.

## 🟡 RC-12 — Orphan Writes (data ditulis, tak pernah dibaca)
- **Prioritas:** P2 (latent — tak crash, tapi data "hilang" secara fungsional).
  | Koleksi | Ditulis oleh | Diagnosa | Rekomendasi |
  |---|---|---|---|
  | **`payroll_entries`(0)** | `marketing_livehost_analytics.py:362` | **ANOMALI:** modul marketing menghitung komisi host lalu insert ke `payroll_entries` (0 dok, tak dibaca payroll). Komentar kode: "Assuming Finance has payroll_entries". Komisi livehost **tak pernah masuk payroll nyata** (`rahaza_payslips`/`rahaza_payroll_runs`). | Integrasikan komisi ke payroll SSOT ATAU hapus write & buat alur yang benar. ⚠ keputusan produk |
  | `wh_fg_movements` | `wms_opname2.py` | audit mutasi FG tak ditampilkan | sambung ke laporan mutasi atau simpan sbg audit |
  | `wh_rca_audit` | `wms_audit.py` | audit RCA | idem |
  | `rahaza_rework_close_log` | `rahaza_rework.py` | log penutupan rework | idem |
  | `rahaza_maintenance_predictions` | `dewi_predictive_maintenance.py` | hasil prediksi AI tak tampil | tampilkan di modul maintenance |
  | `dewi_lms_attempts` | `dewi_lms_quiz.py` | attempt kuis tak dilaporkan | sambung ke laporan LMS |
  | `cutting_outputs` | `qc.py` | ⚠ TRACE | verifikasi |
  | `workspace_shares` | `workspace.py` | ⚠ TRACE | verifikasi |
  | `comm_conversations`(0) | `dewi_procurement.py` | ⚠ TRACE | verifikasi |
  | `dewi_maklon_advance_payments`(0), `dewi_maklon_inventory`(0) | maklon | 🔵 fitur maklon dorman | keputusan bisnis |
  | `accessories` | `operations_reports.py` | kemungkinan salah nama (`rahaza_materials` type accessory) | ⚠ TRACE |
- **RISIKO:** Rendah. **DO-NOT:** jangan hapus write audit tanpa memastikan tak ada kebutuhan jejak audit.

## 🟡 RC-13 — Notifikasi Write-Only (`dewi_notifications`)
- **Prioritas:** P2. **AKAR:** `dewi_notifications`(5) ditulis oleh `employee_expense_claims.py`, `employee_travel_requests.py`, `employee_travel_settlements.py` — **0 reader**. Kanonik = `notifications`(64). → notifikasi expense/travel tak pernah tampil ke user.
- **FIX:** ganti tulis ke `notifications` via helper `utils/notif_unified.py` `notif_insert()`. Kerjakan bersama RC-05 (file sama).
- **RISIKO:** Rendah. **DO-NOT:** jangan bikin reader baru untuk `dewi_notifications`; pakai kanonik.

## 🟡 RC-14 — Misc Phantom (dampak kecil / per-endpoint)
- **Prioritas:** P2.
  | File | ❌ Baca | ✅ SSOT / Aksi |
  |---|---|---|
  | `announcements.py` | `employees` | `rahaza_employees`(25) |
  | `rahaza_shipments.py` | `rahaza_company_settings` | `company_settings`(2) |
  | `unified_search.py` | `rahaza_invoices` | `rahaza_ar_invoices` |
  | `wms_picklist.py` | `dewi_material_issues` (no writer) | ⚠ TRACE (`rahaza_inventory_issues`?) atau empty jujur |
  | `wms_fg_labels.py` | `rahaza_fg_matrix` (no writer) | ⚠ dorman (ada `fg_matrix_seed.py`, belum seed) |
  | `universal_scan.py` | `wms_cmt_dispatches`,`dewi_delivery_orders`,`wms_fabric_rolls` | `wh_cmt_dispatches`(5); dua lain ⚠ TRACE/dorman |
  | `operations_reports/_pdf/_excel.py` | `vendor_shipments`,`buyer_shipments`,`accessory_shipments`,`material_request_items` | 🔵 subsistem dokumen produksi legacy (kosong/dorman) — ⚠ cek apakah masih dipakai UI sebelum aksi |
  | `production_variances.py` | `rahaza_products` | `rahaza_models` (duplikat RC-11) |
  | `dewi_cashflow_ai.py`,`dewi_hr_ai.py` | `hris_*`,`hr_ai_results` | 🔵 dorman |

---

# BAGIAN 3 — KEPUTUSAN BISNIS YANG DIBUTUHKAN (blok bukan bug, tapi menentukan cara fix)

### RC-DASH-DECISION — Metrik "Output Produksi / Shipment" di Dashboard
`rahaza_shipments`(0) dipakai sbg proxy output. Pilihan SSOT:
- **(rekomendasi)** Throughput/output → `rahaza_wip_events`(525, `completed_qty`); Jumlah pengiriman pelanggan → `wh_delivery_notes`(8).
- Alternatif: output dari `rahaza_work_orders.completed_qty`.
- **Butuh keputusan user** sebelum RC-03/RC-04 bagian shipment difinalkan.

### DORMANT MODULES (kosong, belum dipakai — keputusan "pakai/seed" atau "arsip")
Sudah tercatat di `CLEANUP_MASTER_PLAN.md` (KEEP/T4). Ringkas:
- **HRIS performance** (`hris_*`) — belum dibangun (no writer). Portal Saya & HR-AI membacanya.
- **CMT lama** (`dewi_cmt_*`) — alur nyata via `wh_cmt_dispatches`+vendor portal.
- **RnD** (`dewi_rnd_*`), **Maklon sub** (`dewi_maklon_bom/hpp/inventory`), **Assets** (`da_assets`), **LMS materials**, **Marketing catalog/import**, **Toko flashsale**.
→ **Tidak memblok** perbaikan P0/P1. Putuskan setelah aliran data inti sehat.

---

# BAGIAN 4 — SINKRONISASI BACKLOG LAMA (yang belum kelar dari sesi sebelumnya)

Dari `CLEANUP_MASTER_PLAN.md` + `FORENSIC_MASTER_REPORT.md` (agar tak hilang):

### BACKLOG-A — Konsolidasi Komponen Frontend (Tier 3, BELUM) 🟠 dedup menu/UX
- **T3.3** `fin-journal-entry` + `fin-journal-list` → 1 modul 2 tab.
- **T3.4** Marketing AI 4× (`ai-insights`,`advanced-ai`,`ai-content`,`ai-image`) → 1 hub tab.
- **T3.5** HR AI 5× (`hr-ai-insights`,`attrition`,`skill-gap`,`coaching`,`ai-actions`) → 1 hub tab.
- **T3.6** Marketing Live 3× (`live`,`live-analytics`,`livehost`) → 1 hub tab.
- **T3.9** RnD `rnd-hpp` vs `rnd-costing` → gabung tab.
> Risiko rendah (frontend only), tapi butuh keputusan produk. **BUKAN** duplikat data. (T3.1 opname, T3.2 approval, T3.7 kreator, T3.8 notif sudah SELESAI/di-SKIP dengan alasan.)

### BACKLOG-B — Shift Dual-Active `hr_shifts`(7) vs `rahaza_shifts`(4) 🔴
- `rahaza_shifts` = kanonik operasional (coupling 10: aps_scheduler + attendance + assignments). `hr_shifts` = terisolasi (coupling 1, modul HR test, `hr_shifts.py`).
- **Arahan user (sesi ini):** prioritas = sistem benar; jika perlu hapus/rebuild salah satu fitur, boleh. → Verdict: jadikan `rahaza_shifts` kanonik; migrasi 7 `hr_shifts`→`rahaza_shifts` bila memang dipakai, ATAU rebuild modul HR shift agar pakai `rahaza_shifts`. **Uji absensi/penjadwalan menyeluruh.** ⚠ tetap verifikasi, jangan asumsi. **Terkait RC-01** (is_late butuh shift).

### BACKLOG-C — Arsip Backend CMT (`dewi_cmt_*`) 🟠
- Frontend sudah redirect (Wave 2). Backend route `dewi_cmt_*` masih ada (kosong, harmless). Coupling 4-8 (dibaca `dewi_phase7_reports.py`+`dewi_cmt_seed.py`). Arsip bertahap: bekukan endpoint → pastikan phase7 tetap jalan → pindah file ke `_archive` → verifikasi startup.

### BACKLOG-D — Seed Onboarding Routing
- `rahaza_hr_seed.py` seed `dewi_onboarding_templates` (kanonik). `rahaza_onboarding_checklists` sudah di-drop (W3). Modul `hr-onboarding` baca `dewi_onboarding_checklists`(0). → seed checklists ke koleksi kanonik agar modul berisi (feature-fix kecil) ATAU biarkan dorman.

### BACKLOG-E — Tailwind cosmetic warnings 🟢
- ~11 warning `ease-[cubic-bezier(...)]`/`ease-[var(--ease-out)]` ambiguous di 8 file (dev-server only, TIDAK muncul di production build). Fix opsional: named easing di `tailwind.config`. Prioritas terendah.

---

# BAGIAN 5 — ROADMAP EKSEKUSI (dengan dependency)

> User: "ikuti rekomendasi prioritas saya di dokumen." Urutan berdasarkan **risiko naik + dependency**:

| Gel | Isi | Prio | Risiko | Prasyarat | Uji |
|---|---|---|---|---|---|
| **W-A** | **Repoint MISROUTE murni** (SSOT pasti): RC-02 (exec finance/production: invoices/WO/QC/live-field), RC-07 (users/WO/invoices/live-field), RC-10 (COA/cash mapping), RC-11 (models/bundles/maklon-invoices), RC-14 (`announcements` **[+FIELD id]**, company_settings). **RC-08 cashflow** (fix bersih → angka nyata). **RC-06 [+LINKAGE]** (lihat catatan K4). | P0/P1 | **Rendah** | — | curl per-endpoint (bandingkan angka vs count DB) + testing_agent |
| **W-B** | **Absensi split-brain** RC-01 (5 reader → events). **[+DATA-MODEL][+SEED]** — lihat K1: repoint saja tak ubah angka hari ini; overtime butuh join `rahaza_overtime_requests` + perbaiki mismatch tanggal seed (2025 vs 2026); `is_late` mustahil tanpa isi `shift_id`/`is_late`. **Jangan klaim beres setelah repoint.** | P0 | Sedang | — | uji angka Juni + regression HR + render UI |
| **W-C** | **GL integrity** RC-05 + RC-13 (expense/travel → engine + notifikasi kanonik) | P0 | **Tinggi** | STOP-VERIFY COA | JE muncul di buku besar + laporan; regression finance |
| **W-D** | **Exec expense agg** RC-02 `_finance_kpis:81` (journal_lines) — setelah W-C agar data GL lengkap | P0 | Sedang | W-C | finance-snapshot expense>0 |
| **W-E** | **Dashboard** RC-03 (attendance/OEE) + RC-04 (analytics → GRN/wip/WO) | P0 | Sedang-tinggi | W-B + RC-DASH-DECISION | render dashboard + charts |
| **W-F** | **Cashflow/AR** RC-08 + RC-09 (⚠ setelah trace cash_movements) | P1 | Sedang | STOP-VERIFY | cashflow/statement |
| **W-G** | **Orphan & anomali** RC-12 (payroll_entries dll) | P2 | Rendah | keputusan produk | per fitur |
| **W-H** | **Backlog lama** BACKLOG-A..E (dedup komponen, shift, arsip CMT, onboarding, tailwind) | P1/P2 | Bervariasi | keputusan produk | per item |

**Catatan dependency penting:**
- RC-01 (absensi) mendahului RC-03/RC-07 bagian absensi & payroll akurat.
- RC-05 (GL engine) mendahului RC-02 expense-agg (butuh GL lengkap di journal_lines).
- RC-DASH-DECISION (keputusan user) mendahului finalisasi shipment di RC-03/RC-04.

**⚠ LEGENDA TAG (dari KOREKSI EMPIRIS BAGIAN 0.5):**
- `[+DATA-MODEL]` = butuh perubahan struktur data, bukan sekadar repoint (mis. isi `shift_id`/`is_late` absensi).
- `[+SEED]` = butuh perbaikan data seed (mis. tanggal `rahaza_overtime_requests` 2025 → sejajar 2026).
- `[+LINKAGE]` = butuh menautkan relasi (mis. user login ↔ karyawan untuk Portal Saya).
- `[+FIELD ...]` = selain koleksi, field query juga salah.
> **ATURAN:** untuk item bertag ini, endpoint 200 **BUKAN** bukti selesai — WAJIB verifikasi angka nyata & render UI, dan sampaikan ke user bila hasil masih 0 karena keterbatasan seed/model.

**Rekomendasi mulai: W-A** (dampak visual besar, risiko terkecil, tanpa migrasi data).

---

# BAGIAN 6 — DEFINITION OF DONE (per item, WAJIB)
- [ ] File+baris dibuka; schema SSOT target dicek di DB (perintah §GOLDEN RULE 1).
- [ ] Query di-repoint + field dipetakan (tabel peta field diikuti).
- [ ] Endpoint 200 & angka masuk akal (bandingkan dg count DB, bukan sekadar "tidak error").
- [ ] `ruff` backend & `esbuild` frontend bersih; `supervisorctl` health 200.
- [ ] `testing_agent` (backend; frontend bila UI) hijau, 0 regresi.
- [ ] `/app/memory/CHANGELOG.md` + status `plan.md` diperbarui.

---

# APPENDIX A — SCANNER FALSE-POSITIVE REGISTRY (JANGAN disentuh)
Scanner menandai, tapi terverifikasi NORMAL:
- `payroll_automation_config`, `payroll_automation_log` — auto-create saat write pertama oleh `payroll_automation.py` sendiri (`:142`,`:208`).
- `marketing_kol_campaigns` — dibungkus try/except & hasil dibuang (`dewi_executive_report.py:245`).
- Runtime-empty normal: `attachments`, `login_attempts`, `client_login_attempts`, `dewi_scheduler_runs`(5), `capacity_config`, `rahaza_ai_audit_logs`(1), `rahaza_ai_usage_logs`.
- **CATATAN KOREKSI:** `rahaza_journals` **BUKAN** false-positive orphan — deep-trace membuktikan itu koleksi GL SALAH yang dipakai employee expense/travel (lihat RC-05). Scanner benar menandainya ORPHAN_WRITE.

# APPENDIX B — CHEATSHEET VERIFIKASI
```bash
# 0. ENV
URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)

# 1. Cek koleksi + schema + count
python3 -c "import os;from pymongo import MongoClient;c=MongoClient(os.environ['MONGO_URL'])[os.environ.get('DB_NAME','test_database')];\
n='rahaza_attendance_events';print(n in c.list_collection_names(),c[n].count_documents({}));print(sorted(c[n].find_one({},{'_id':0}).keys()))"

# 2. distinct nilai field (mis. status)
python3 -c "import os;from pymongo import MongoClient;c=MongoClient(os.environ['MONGO_URL'])[os.environ.get('DB_NAME','test_database')];print(c['rahaza_attendance_events'].distinct('status'))"

# 3. Login (rate-limit 10/60s!) → token
curl -s -X POST $URL/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@garment.com","password":"Admin@123"}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('token'))"

# 4. Uji endpoint
curl -s $URL/api/reports/executive/summary -H "Authorization: Bearer $T" | python3 -m json.tool

# 5. Re-run scanner (read-only) setelah fix untuk konfirmasi phantom berkurang
cd /app/backend && python3 migrations/ssot_forensic_scanner.py
```

# APPENDIX C — KREDENSIAL UJI (dari `/app/memory/test_credentials.md`)
`admin@garment.com` (superadmin) · `hr@dewiaditya.id` · `finance@dewiaditya.id` · `spv@dewiaditya.id` · `gudang@dewiaditya.id` · `maklon@dewiaditya.id` — password `Admin@123`/`password123`/`Dewi@123` (cek file).

# APPENDIX D — BUKTI EMPIRIS "SEBELUM" (Pass #2, login nyata 2026-07-02)
> Baseline nyata sebelum perbaikan. Ulangi setelah fix untuk membuktikan perbaikan.

**Cakupan data seed:** absensi & keuangan **2026-05-01 → 2026-07-31**. `rahaza_attendance` == `rahaza_attendance_events` (identik, 1567 hadir/36 izin/47 sakit). `rahaza_overtime_requests` = 7 (semua `approved`, **tanggal 2025-Q1** — mismatch). `rahaza_attendance_events`: `overtime_hours>0` = **0/1650**, `shift_id != null` = **0/1650**, field `is_late` = **TIDAK ADA**.

| Endpoint | Hasil nyata (BEFORE) | Diagnosa |
|---|---|---|
| `/api/reports/executive/summary` | finance.revenue_rp=**0**, total_expenses_rp=**0**, invoice_count=**0**; production.total_wo=**0**, defect=**0**, cmt=**0**; hr.attendance_rate=**95.5**, overtime=**0**; marketing=**0** | finance/prod baca phantom → NOL; HR attendance jalan (seed); overtime phantom |
| `/api/dashboard` | totalRevenue=**296.800.000**, activeEmployees=**25**, attendanceToday=**25/100%**, avgOEE=**None**, pendingShipments=**0** | revenue/employees OK; attendance-today OK (seed hari ini, LATEN); OEE phantom |
| `/api/dashboard/analytics` | vendorLeadTimes=**[]**, defectRates=**[]**, weeklyThroughput=**[0..]**, productCompletion=**[]**, shipmentStatus=**[]**, deadlineDistribution=**semua 0** | seluruhnya phantom/kosong → MATI TOTAL |
| `/api/management/weekly-digest` | production=**0/0**, finance=**0**, hr.leave=**0** / attendance_issues=**18**, marketing=**0**, alerts.low_stock=**19** / racks=**0** | WO/invoice/racks phantom; attendance_issues(izin)=18 & low_stock jalan |
| `/api/payroll/automation/attendance-sync` (Juni) | with_attendance_data=**25**, days_present **19-22**, days_late=**0** | **days_present JALAN**; days_late=0 (field is_late tak ada) |
| `/api/payroll/automation/attendance-sync` (April) | with_attendance_data=**0** | benar-benar kosong (memang tak ada data April) |
| `/api/portal-saya/me/payslips` & `/me/leaves` | **HTTP 409/404 "Akun belum terhubung ke data karyawan"** | linkage user↔karyawan gagal untuk SEMUA 6 akun (email tak cocok) |
| `rahaza_cash_movements` | direction in=**10**, out=**22**, tanggal 2026-05..07 | RC-08 cashflow → akan hasil nyata |

# APPENDIX E — CAKUPAN & BLIND-SPOT SCANNER (kejujuran metodologi)
- Scanner (`ssot_forensic_scanner.py`) menangkap pola `db.<coll>.<op>()` & `db["<coll>"]` di `routes/` + `services/`. 
- **Blind-spot terverifikasi & AMAN:** `get_collection(` = 0 pemakaian; `X = db[...]` (variabel) = 0. Akses dinamis `db[variable]` HANYA di **helper generik** (counters, universal_import, seed-delete, `dashboard_routes.py:21 _sum_field`, admin-delete) — nama koleksi datang dari pemanggil, **bukan phantom bisnis**. `services/` (8 file) sudah tercakup.
- **Kesimpulan:** cakupan scanner untuk logika bisnis memadai; tidak ada set besar phantom tersembunyi. Namun tetap patuhi GOLDEN RULE 1 (cek schema) per item.
- **Sisa yang belum ditelusuri 1-per-1:** ~110 phantom sisanya dikelompokkan pola (false-positive/dorman) — bila menyentuh modul di luar RC-01..RC-14, WAJIB verifikasi ulang modul itu sebelum ubah.

---
*Diperbarui via Pass Pendalaman #2 (read-only): login nyata + uji endpoint + inspeksi data. Beberapa klaim v2 dikoreksi (lihat BAGIAN 0.5). BELUM ada perubahan kode.*
