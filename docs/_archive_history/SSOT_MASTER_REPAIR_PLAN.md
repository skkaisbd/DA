# 🔧 SSOT MASTER REPAIR PLAN — DA53 ERP (Definitif, Zero-Assumption)
**Dokumen perbaikan tunggal & menyeluruh untuk cacat aliran data (SSOT / Phantom / Stale / Orphan / Logic-defect) di SELURUH sistem.**

> **Versi 2 (Deep-Dive).** Menggantikan draf v1. Setiap temuan sudah ditelusuri **sampai ke akar logika** (bukan permukaan) dan diverifikasi lintas **5 dimensi**: (D1) Data DB nyata, (D2) Kode backend baris-per-baris, (D3) Frontend/modul pemakai, (D4) Linkage/idempotency/FK, (D5) Semantik (bug nyata vs false-positive vs dorman).

- **Status:** RENCANA. **BELUM ADA perubahan kode.**
- **Basis bukti:** `/app/backend/routes/*.py` (dibuka & dibaca), database `test_database` (schema + count + distinct values nyata), `SSOT_FORENSIC_RAW.json`.
- **Untuk siapa:** Agent/sesi berikutnya. Dokumen ini dirancang agar **tidak perlu menebak apa pun**. Jika item tak punya jawaban pasti → ditandai **⚠ STOP-VERIFY** dengan perintah verifikasi yang WAJIB dijalankan dulu.
- **Dokumen ini terdiri 2 file:** `SSOT_MASTER_REPAIR_PLAN.md` (fondasi + RC-01..RC-07) & `SSOT_MASTER_REPAIR_PLAN_PART2.md` (RC-08..RC-14 + backlog lama + roadmap + appendix). WAJIB baca keduanya.

---

# BAGIAN 0 — GOLDEN RULES (Konstitusi. Langgar = rusak lagi)

> Sistem "acak-acakan" karena agent sebelumnya menulis kode dengan **asumsi nama koleksi** & **tanpa cek schema**. Aturan berikut WAJIB dipatuhi tanpa kecuali.

1. **JANGAN PERNAH mengarang/menebak nama koleksi.** Sebelum menyentuh query apa pun, verifikasi keberadaan + schema:
   ```bash
   python3 -c "import os;from pymongo import MongoClient;c=MongoClient(os.environ['MONGO_URL'])[os.environ.get('DB_NAME','test_database')];\
   n='<COLLECTION>';print('exists',n in c.list_collection_names(),'count',c[n].count_documents({}) if n in c.list_collection_names() else 'NA');\
   d=c[n].find_one({},{'_id':0});print('keys',sorted(d.keys()) if d else 'EMPTY')"
   ```
2. **Repoint ≠ ganti nama saja.** Nama field sering beda (`quantity`↔`qty`, `check_in`↔`clock_in`, `revenue`↔`gmv`, `inspected_qty`↔`checked_qty`). **WAJIB** petakan field & verifikasi nilai.
3. **Status absensi = `hadir`/`izin`/`sakit`.** BUKAN `present`/`H`/`late`/`absent`/`alpha`. Filter status di luar 3 nilai itu = **selalu meleset** (diverifikasi `distinct('status')`).
4. **Semua posting GL WAJIB lewat engine `routes/rahaza_posting.py`** (`_create_posted_je`/`post_*`). JANGAN `insert_one` manual ke koleksi jurnal. Engine = idempoten (source_ref), validasi saldo, validasi akun COA, guard periode, mirror ke `rahaza_journal_lines` (yang dibaca laporan).
5. **Jangan "memaksa" angka.** Jika metrik tak punya SSOT (mis. HRIS belum dibangun), tampilkan jujur "belum ada data" — JANGAN buat koleksi/angka palsu.
6. **Satu item = satu perubahan kecil & reversibel.** Uji tiap item (endpoint 200 + angka masuk akal + render UI) SEBELUM lanjut.
7. **Metode wajib per item:** `bekukan → cek schema SSOT → repoint + peta field → verifikasi (curl+DB) → testing_agent → catat di CHANGELOG`.
8. **JANGAN sentuh:** `frontend/.env` `REACT_APP_BACKEND_URL`, `backend/.env` `MONGO_URL`. **JANGAN** re-seed (data sudah ada). **JANGAN** merge `hr_shifts`↔`rahaza_shifts` tanpa baca BACKLOG-B (PART2).
9. **Rate limit login:** `/api/auth/login` maks **10 req/60 dtk**. Beri jeda ≥65 dtk tiap 10 login, atau reuse token.
10. **Baca `/app/memory/ENGINEERING_GUARDRAILS.md`** sebelum mulai.

---

# BAGIAN 0.5 — KOREKSI EMPIRIS (WAJIB BACA SEBELUM EKSEKUSI) ⚠️

> Bagian ini adalah hasil **Pass Pendalaman #2**: login nyata + panggil endpoint + cek data. Beberapa klaim awal (yang hanya dari baca kode) **TERBUKTI KELIRU / terlalu optimis**. **JANGAN percaya asumsi "repoint = beres".** Bukti angka nyata ada di **APPENDIX D (PART2)**.

**Konteks data:** Server today = **2026-07-02**. Data seed absensi & keuangan mencakup **2026-05-01 s/d 2026-07-31**. Kredensial login = 6 akun ROLE (admin/hr/finance/spv/gudang/maklon), **BUKAN** akun per-karyawan.

### Koreksi K1 — Absensi & Payroll: "repoint saja TIDAK cukup"
- **FAKTA:** `rahaza_attendance` dan `rahaza_attendance_events` saat ini **IDENTIK** (seed menulis ke keduanya: 1567 hadir / 36 izin / 47 sakit). Jadi `days_present` & `attendance_rate` **SUDAH BEKERJA** untuk bulan ber-data (uji: attendance-sync Juni → `days_present` 19-22 untuk 25 karyawan). Ini **BUKAN** kasus "selalu nol".
- **BUG SESUNGGUHNYA (3, lebih dalam):**
  1. **Staleness laten:** clock-in live hanya masuk `rahaza_attendance_events`, TIDAK ke `rahaza_attendance`. Hari ini identik; besok/nanti akan divergen → payroll baca yang seed-only jadi basi. → Repoint ke `_events` = benar (untuk masa depan), tapi **tak mengubah angka hari ini**.
  2. **Overtime SELALU 0 di KEDUA koleksi:** `rahaza_attendance_events` punya `overtime_hours` TAPI **semua bernilai 0.0** (0 dari 1650). Sumber lembur sebenarnya = `rahaza_overtime_requests` (7, semua `approved`) — **TAPI tanggalnya 2025-Q1**, sedangkan absensi/payroll 2026-Q2/Q3 → **disjoint periode**. → Memperbaiki overtime butuh: (a) payroll JOIN `rahaza_overtime_requests` per employee+period, DAN (b) **perbaikan SEED** (tanggal overtime harus sejajar periode). Repoint saja → tetap 0.
  3. **`is_late` MUSTAHIL dari data saat ini:** `rahaza_attendance_events` **tak punya field `is_late`**, dan **`shift_id` NULL di SEMUA 1650 record** → tak bisa join `rahaza_shifts` untuk hitung telat. → Butuh **perubahan model-data** (isi `shift_id`/`is_late` saat clock-in) atau seed diperbaiki. JANGAN mengarang telat.
- **KESIMPULAN K1:** RC-01 tetap valid arah-nya (repoint ke SSOT live + ambil overtime dari `rahaza_overtime_requests`), TAPI hasil "angka benar" **hanya tercapai** bila seed/model-data juga diperbaiki. **Dokumentasikan jujur ke user; jangan klaim beres setelah repoint.**

### Koreksi K2 — Dashboard `/api/dashboard`: tidak semua nol
- **Bukti nyata:** `totalRevenue=296.800.000` (BENAR), `activeEmployees=25` (BENAR), `attendanceTodayCount=25 / Pct=100` (**BUKAN 0** — karena seed mencakup hari ini), `avgOEE=None` (**bug**, phantom `rahaza_oee_logs`).
- **Koreksi:** klaim "attendance today selalu 0" **KELIRU**. Ini **bug laten**: begitu tanggal melewati cakupan seed (2026-07-31) atau saat hanya ada data live → jadi 0 karena baca `rahaza_attendance` (seed-only). Fix RC-03 tetap perlu (repoint `_events` + OEE dari `rahaza_wip_events`), tapi framing = "cegah staleness", bukan "memperbaiki nol hari ini".

### Koreksi K3 — Executive Report: finance/production NOL, HR SEBAGIAN
- **Bukti:** `finance.revenue_rp=0, total_expenses_rp=0, invoice_count=0` (NOL ✅ bug), `production.total_wo=0, defect=0` (NOL ✅ bug), `hr.attendance_rate_pct=95.5` (**BEKERJA** dari seed), `hr.overtime_hours=0` (bug), `marketing` semua 0 (field mismatch). → RC-02 finance/production akurat; bagian HR attendance **tidak nol** (koreksi).

### Koreksi K4 — Portal Saya: rename koleksi TIDAK cukup (bug linkage lapisan-dalam)
- **Bukti:** `/api/portal-saya/me/payslips` & `/me/leaves` untuk akun admin → **HTTP 409/404 "Akun belum terhubung ke data karyawan."**
- **AKAR:** `_get_my_employee` (dewi_portal_saya_ext.py:52) cari karyawan via `email/id/employee_code` user. **TAK SATU PUN** dari 6 email user login cocok dengan email karyawan (`rahaza_employees`) → linkage gagal untuk SEMUA akun.
- **KESIMPULAN K4:** RC-06 (rename `rahaza_leaves`→`rahaza_leave_requests`, `rahaza_payroll_payslips`→`rahaza_payslips`) **BENAR & PERLU**, tapi **payslip/cuti tetap tak muncul** sampai ada **linkage user↔karyawan** (tautkan email akun ke karyawan, atau tambah field `employee_id` di user, atau seed akun login per-karyawan). Ini gap seed/desain — **repoint saja = tetap error**.

### Koreksi K5 — Cashflow: fix akan menghasilkan angka nyata
- **Bukti:** `rahaza_cash_movements` punya `direction: in=10, out=22`, tanggal 2026-05..07. → RC-08 (repoint ke `rahaza_cash_movements` by direction) **akan** menghasilkan cash-in/out nyata. Ini item "bersih".

### Koreksi K6 — Bug ganda (bukan sekadar rename)
- `announcements.py:101..295` — baca `db.employees` (phantom) **DAN** query `{employee_id: created_by}`. SSOT `rahaza_employees` pakai key `id`. → fix = koleksi **dan** field query (`{id: ...}`).
- `dewi_hr_ai.py:348-349` — filter status `"late"/"absent"/"alpha"` yang **tak pernah ada** (hanya hadir/izin/sakit) → attrition telat/absen selalu 0 meski koleksi benar.

### Ringkas: klasifikasi ulang setelah bukti empiris
| Item | Sebelumnya dikira | FAKTA empiris |
|---|---|---|
| Exec finance/production | nol | **NOL (bug murni)** ✅ |
| Exec/Dashboard HR attendance | nol | **BEKERJA dari seed** (bug = staleness + overtime/telat) |
| Dashboard attendance today | nol | **25/100% (seed hari ini)** — bug laten |
| Payroll days_present | nol/rusak | **BEKERJA** (bug = staleness, overtime, telat) |
| Overtime | tinggal repoint | **butuh join overtime_requests + fix seed (mismatch 2025 vs 2026)** |
| is_late | turunkan dari shift | **MUSTAHIL** tanpa isi shift_id/is_late (model-data) |
| Portal Saya payslip/cuti | rename koleksi | **rename + fix linkage user↔karyawan** |
| Cashflow | phantom | fix bersih → angka nyata |

**IMPLIKASI ke ROADMAP (PART2):** item yang butuh **lebih dari repoint** ditandai `[+DATA-MODEL]` atau `[+SEED]` atau `[+LINKAGE]`. Jangan tandai "selesai" hanya karena endpoint 200 — **verifikasi angka & render UI nyata**.

---


# BAGIAN 1 — SSOT CANONICAL REGISTRY (Tabel Kebenaran Tunggal)

Gunakan tabel ini sebagai SATU-SATUNYA acuan nama koleksi. "count" = jumlah dokumen saat audit (bukti hidup).

### 1A. Keuangan / GL
| Konsep | ✅ SSOT KANONIK (count) | ❌ Nama SALAH yang dipakai kode | Field kunci |
|---|---|---|---|
| Jurnal header | `rahaza_journal_entries` (2) | `journal_entries` | `je_number,date,status,source_module,source_ref,lines[]` |
| Jurnal baris (DIBACA LAPORAN) | `rahaza_journal_lines` (5) | — | `account_code,debit,credit,date,period_code,source_module` |
| Chart of Accounts | `rahaza_coa_accounts` (97) | `rahaza_coa` | `code,name,type,is_group,active` |
| Kas & Bank | `rahaza_cash_accounts` (4) | `rahaza_bank_accounts` | `id,code,name,gl_account_code,balance` |
| Arus kas aktual (in/out) | `rahaza_cash_movements` (32) | `rahaza_ar_receipts`, `rahaza_ap_payments` | `account_id,amount,direction,date,category,ref_id` |
| Mapping akun posting | `rahaza_posting_profiles` (33) | — | `event_type,mapping{},active` |
| Invoice penjualan (AR) | `rahaza_ar_invoices` (15) | `invoices`, `rahaza_invoices` | `total,balance,paid_amount,status,due_date,created_at` |
| Invoice pembelian (AP) | `rahaza_ap_invoices` (12) | `invoices` | idem AP |
| Invoice maklon | `dewi_maklon_invoices` (3) | `dewi_invoices` | — |
| Beban (expense) | `rahaza_expenses` (12) | — | `id,gl_debit_code,account_id,amount,date,cost_center_id` |
| Klaim reimburse karyawan | `rahaza_expense_claims` (4) | — | `bank_account_id,gl_debit_code,items[],status` |
| Transfer bank | `rahaza_bank_transfers` (4) | — | — |
| Periode akuntansi | `rahaza_periods` (12) | — | `period_code,status` |
| Cost center | `rahaza_cost_centers` (6) | — | — |

### 1B. HR / Absensi / Payroll
| Konsep | ✅ SSOT KANONIK (count) | ❌ Nama SALAH | Catatan field |
|---|---|---|---|
| **Absensi (SSOT LIVE)** | **`rahaza_attendance_events`** (1650) | `rahaza_attendance` (stale, seed-only 1650), `dewi_attendance` (phantom) | `date,clock_in,clock_out,hours_worked,overtime_hours,status,shift_id,source` — **status: hadir/izin/sakit** |
| Karyawan | `rahaza_employees` (25) | `employees` | `employment_status,department,join_date,shift_code` |
| Payslip | `rahaza_payslips` (75) | `rahaza_payroll_payslips` | `employee_id,days_present,overtime_hours,net_salary,period_from/to` |
| Payroll run | `rahaza_payroll_runs` (3) | — | `status,total_net_pay,period` |
| Profil payroll | `rahaza_payroll_profiles` (25) | — | — |
| Lembur | `rahaza_overtime_requests` (7) | `rahaza_overtime` | `hours,status,date,rate_multiplier` |
| Cuti | `rahaza_leave_requests` (8) | `rahaza_leaves` | `date_from,date_to,leave_type,status` |
| User login/role | `users` (6) | `rahaza_users` | `role,email,is_active` |
| Shift kerja | `rahaza_shifts` (4) | — | `code,start_time,check_in_time,working_hours` |

### 1C. Produksi / Warehouse
| Konsep | ✅ SSOT KANONIK (count) | ❌ Nama SALAH | Field kunci |
|---|---|---|---|
| Work Order | `rahaza_work_orders` (20) | `production_work_orders`, `production_pos`(0) | `qty,target_qty,completed_qty,status,due_date,model_name` |
| QC | `rahaza_qc_events` (35) | `rahaza_qc_records` | `checked_qty,pass_qty,fail_qty,verdict` |
| WIP/output (OEE & throughput) | `rahaza_wip_events` (525) | `production_progress`, `rahaza_oee_logs` | `completed_qty,line_id,date` (⚠ cek schema) |
| Bundle | `rahaza_bundles` (45) | `rahaza_wo_bundles` | — |
| Model/produk | `rahaza_models` (3) | `rahaza_products` | — |
| GRN inspeksi (defect vendor) | `rahaza_grn_inspections` (7) | `vendor_material_inspections` | `defect_rate,total_received_qty,total_accepted_qty,total_rejected_qty,supplier_name` |
| Penerimaan barang (lead time) | `warehouse_receiving` (13) | `vendor_shipments` | `po_number,supplier_name,status,created_at` |
| Vendor master | `rahaza_vendors` (7) | — | `name,code,rating` |
| Dispatch CMT | `wh_cmt_dispatches` (5) | `wms_cmt_dispatches` | — |
| Surat jalan pelanggan | `wh_delivery_notes` (8) | `rahaza_shipments`(0), `vendor_shipments` | — |
| Line produksi | `rahaza_production_lines` (7) / `rahaza_line_assignments` (105) | — | — |
| Setelan perusahaan | `company_settings` (2) | `rahaza_company_settings` | — |

### 1D. Marketing / Notifikasi
| Konsep | ✅ SSOT KANONIK (count) | ❌ Nama SALAH | Catatan |
|---|---|---|---|
| Live session | `marketing_live_sessions` (24) | — (nama benar, FIELD salah) | pakai `gmv`,`total_orders`,`session_date`(string) — kode baca `revenue`,`orders`,datetime |
| Notifikasi | `notifications` (64) | `dewi_notifications` (5, write-only) | pakai helper `utils/notif_unified.py` |
| Order marketplace | `marketing_orders` (60) | — | — |
| Audit log | `rahaza_audit_logs` (20) | — | `entity_type,action,diff,timestamp` |

### 1E. ⚠ TIDAK PUNYA SSOT (dibaca kode, TIDAK ADA writer di seluruh kode → fitur belum dibangun / dead-read)
`hris_reviews`, `hris_cycles`, `hris_kpi_assignments`, `hris_assignments`, `hris_training_completions`, `hr_issued_documents`, `rahaza_fg_matrix`, `wms_fabric_rolls`, `dewi_material_issues`, `dewi_cmt_orders`, `dewi_delivery_orders`, `hr_ai_results`, `dewi_kpi_submissions`, `capacity_config`, `procurement_requests`, `material_request_items`.
→ **Keputusan per fitur:** (a) fitur belum dibangun → empty-state jujur/sembunyikan, atau (b) writer ada tapi belum di-seed → seed. **JANGAN mengarang SSOT.**

---

# BAGIAN 2 — REPAIR CARDS (RC-01 s/d RC-07)

Format: `ID | Prioritas | Dampak | File:baris | AKAR MASALAH | SSOT+schema | PETA FIELD | LANGKAH | VERIFIKASI | ROLLBACK | RISIKO | DO-NOT`.

---

## 🔴 RC-01 — Split-Brain Absensi (`rahaza_attendance` seed-only vs `rahaza_attendance_events` live)
- **⚠ BACA DULU KOREKSI K1 (BAGIAN 0.5):** repoint SAJA tidak mengubah angka hari ini (kedua koleksi identik); overtime butuh `rahaza_overtime_requests`+fix seed; `is_late` mustahil tanpa `shift_id`/`is_late` (model-data).
- **Prioritas:** P0. **Dampak:** Payroll (lembur/telat SELALU 0), rate kehadiran & metrik HR di 5 modul salah; absensi biometrik/selfie/webauthn nyata tak terhitung.
- **Bukti D2 (writer):** `rahaza_attendance` ← HANYA `production_seed_full.py:749` (seed), 0 writer live. `rahaza_attendance_events` ← SEMUA jalur live (`rahaza_attendance.py`, `_webauthn.py`, `_selfie.py`, `_zkteco.py`, `_approvals.py`, `hr_approval_inbox.py`, `rahaza_leave.py`).
- **Bukti D1 (schema):** `rahaza_attendance`={`check_in,check_out,work_hours,status,date`} **tanpa** `overtime_hours`/`is_late`. `rahaza_attendance_events`={`clock_in,clock_out,hours_worked,overtime_hours,status,shift_id,source,date`}, `status∈{hadir,izin,sakit}`, sampel `shift_id=None`.
- **AKAR MASALAH:** Reader menghitung `overtime_hours`/`is_late` dari koleksi yang tak punya field itu → 0; dan koleksi seed-only tak menerima absensi nyata.
- **Reader di-repoint (5):** `payroll_automation.py:260,:324` · `dewi_executive_report.py:182` · `dashboard_routes.py:120-122` · `dewi_management_tools.py:172` · `dewi_hr_ai.py`.
- **PETA FIELD:** `work_hours→hours_worked` · `check_in/out→clock_in/out` · `overtime_hours` (langsung `$sum`) · `status in [present,hadir,H]` → `status=='hadir'` · `is_late` → turunkan dari `clock_in` vs shift.
- **Catatan telat:** events tak punya `is_late`; `shift_id` sering None → join `rahaza_shifts.check_in_time` tak selalu bisa. **P0: hitung telat hanya bila shift tersedia; jika tidak → 0 + TODO.** Overtime aman.
- **LANGKAH:** (1) payroll pipeline → events; (2) exec `_hr_kpis`; (3) dashboard today; (4) management digest; (5) hr_ai; (6) setelah stabil → nonaktif seed `:749` (arsip, jangan drop 1 sesi).
- **VERIFIKASI:** `GET /api/reports/executive/hr-snapshot` → `attendance_rate_pct>0`, `overtime_hours` sesuai `rahaza_overtime_requests`.
- **ROLLBACK:** kembalikan nama koleksi per pipeline. **RISIKO:** Sedang (payroll). **DO-NOT:** jangan drop `rahaza_attendance` sebelum 1-5 verified; jangan pakai status 'present'/'H'; jangan mengarang is_late.

---

## 🔴 RC-02 — Executive Report Hub baca Phantom (`dewi_executive_report.py`)
- **Prioritas:** P0. **Dampak:** **ExecutiveReportModule.jsx** (`/api/reports/executive/*`) → revenue, laba, WO, defect **NOL**.
- **PETA per fungsi:**
  | Fungsi:baris | ❌ Baca | ✅ SSOT | Peta field |
  |---|---|---|---|
  | `_finance_kpis:71,:90` | `invoices` | `rahaza_ar_invoices` | `total_amount→total`; `balance_due→balance` |
  | `_finance_kpis:81` (expense) | `journal_entries` embedded `entries[]` | **`rahaza_journal_lines`** | buang `$unwind entries`; filter baris `account_code ^[56]` + `$sum debit`. Pola ada di `rahaza_fin_reports.py:147-199` |
  | `_production_kpis:122` | `production_work_orders` | `rahaza_work_orders` | `quantity→qty/target_qty`; `qty_completed→completed_qty` |
  | `_production_kpis:134` | `dewi_cmt_orders` (no writer) | `dewi_maklon_pos`(6) atau 0 jujur | — |
  | `_production_kpis:147` | `rahaza_qc_records` | `rahaza_qc_events` | `inspected_qty→checked_qty`; `defect_qty→fail_qty` |
  | `_hr_kpis:182,:194` | `rahaza_attendance`,`rahaza_overtime` | `rahaza_attendance_events`,`rahaza_overtime_requests` | RC-01; overtime `hours`+status |
  | `_marketing_kpis:236` | `marketing_live_sessions` (field salah) | sama | `total_revenue→gmv`; `orders_count→total_orders`; `session_date` string |
- **⚠ STOP-VERIFY (expense GL):** `python3 -c "...print(c['rahaza_journal_lines'].find_one({},{'_id':0}));print('acc56',c['rahaza_journal_lines'].count_documents({'account_code':{'$regex':'^[56]'}}))"` — samakan pola dg `rahaza_fin_reports.py` (SUDAH benar, jadikan acuan, JANGAN diubah).
- **VERIFIKASI:** `/summary` → `finance.revenue_rp>0`, `production.total_wo>0`. **RISIKO:** Sedang.

---

## 🔴 RC-03 — Dashboard Eksekutif (`dashboard_routes.py :: /api/dashboard`)
- **Prioritas:** P0. **Dampak:** kartu KPI dashboard utama.
- **Item:** `120-122` `rahaza_attendance`+fallback `dewi_attendance` → `rahaza_attendance_events` (date==today, status 'hadir'; hapus fallback). · `130-133` `rahaza_oee_logs`(phantom) → hitung dari `rahaza_wip_events`(525), reuse `rahaza_oee.py` (⚠ cek schema). · `94,166-169,211` `rahaza_shipments`(0) → lihat RC-DASH-DECISION (PART2).
- **SUDAH BENAR (jangan ubah):** `rahaza_orders/work_orders/ar_invoices/ap_invoices/employees/materials/models`, `users`.
- **VERIFIKASI:** `/api/dashboard` → `attendanceTodayPct`,`avgOEE` tak null bila ada data. **RISIKO:** Sedang.

---

## 🔴 RC-04 — Dashboard Analytics (`/api/dashboard/analytics`) — endpoint mati total
- **Prioritas:** P0. **Dampak:** **ManagementDashboard.jsx** semua grafik kosong.
- **Item:** `277,338` `vendor_shipments`→`warehouse_receiving`(13, vendor=`supplier_name`, status=`status`) · `291` `vendor_material_inspections`→`rahaza_grn_inspections`(7, `total_received_qty/total_rejected_qty/defect_rate/supplier_name`) · `311→318` `rahaza_shipments`(0)→`production_progress`(phantom) → `rahaza_wip_events`(525, `completed_qty`/minggu) · `328` `production_job_items`(0)→`rahaza_work_orders` group `model_name` · `342` `production_pos`(0)→`rahaza_work_orders.due_date`.
- **⚠ STOP-VERIFY:** schema `rahaza_wip_events` & `warehouse_receiving.items[]` sebelum fix throughput/lead-time.
- **RISIKO:** Sedang-tinggi. Fix bertahap per grafik. **DO-NOT:** jika lead-time vendor tak bisa akurat → kosong jujur.

---

## 🔴 RC-05 — GL Split & Bug Berlapis Employee Expense/Travel (INTEGRITAS AKUNTANSI)
- **Prioritas:** P0 (uang). **Dampak:** Jurnal reimburse & perjalanan dinas **tak muncul di Laba Rugi/Buku Besar**; notifikasi tak tampil; resolusi bank gagal diam.
- **File:** `employee_expense_claims.py`, `employee_travel_requests.py`, `employee_travel_settlements.py`.
- **AKAR MASALAH (3 cacat bertumpuk):**
  1. **GL salah koleksi** `:516` `db.rahaza_journals.insert_one` — SSOT GL = `rahaza_journal_entries`+`rahaza_journal_lines` (laporan baca lines). `rahaza_journals` 0 reader → JE invisible.
  2. **Bank phantom** `:487` `db.rahaza_bank_accounts.find_one` — koleksi tak ada → fallback `'1-1201'`. Bank asli = `rahaza_cash_accounts`(4).
  3. **Akun tak ada:** default Dr `'6-1001'` **tak ada** di `rahaza_coa_accounts`. Benar: `6-3500`(Reimbursement)/`6-3400`(Perjalanan Dinas), Cr kas `1-1101`.
- **FIX (WAJIB lewat engine):** (1) buat/gunakan posting profile `expense_claim` (`debit_expense_default:6-3500,credit_cash_default:1-1101`); (2) ganti blok manual `:480-516` → `_create_posted_je`/`post_expense`; (3) `bank_account_id`→`rahaza_cash_accounts`; (4) notifikasi→`notifications` (RC-13).
- **⚠ STOP-VERIFY:** cek akun `6-3400/6-3500/1-1101` ada & postable (`is_group=False`) di `rahaza_coa_accounts`.
- **VERIFIKASI:** disburse 1 klaim → `rahaza_journal_entries`+`rahaza_journal_lines` bertambah (source_module='expense_claim'); `finance-snapshot.total_expenses_rp` naik; muncul di buku besar.
- **RISIKO:** **Tinggi**. **DO-NOT:** jangan lanjut tanpa STOP-VERIFY; jangan biarkan 2 jalur GL aktif; pertimbangkan repost 10 dok lama `rahaza_journals` via engine (opsional).

---

## 🔴 RC-06 — Portal Saya Karyawan (`dewi_portal_saya_ext.py`)
- **⚠ BACA DULU KOREKSI K4 (BAGIAN 0.5):** rename koleksi PERLU tapi TIDAK cukup — Portal Saya 409/404 untuk SEMUA 6 akun karena linkage user↔karyawan gagal. Wajib `[+LINKAGE]`.
- **Prioritas:** P1 (dilihat semua karyawan). **Dampak:** **PortalSayaPayslip.jsx** & **PortalSayaCuti.jsx** kosong.
- **FIX pasti:** `rahaza_payroll_payslips`→`rahaza_payslips`(75, filter `employee_id`); `rahaza_leaves`→`rahaza_leave_requests`(8, filter `employee_id`).
- **⚠ DORMANT (bukan rename):** `hris_reviews/cycles/assignments/kpi_assignments`,`hr_issued_documents` → tak ada writer (HRIS belum dibangun) → empty-state jujur.
- **VERIFIKASI:** login `hr@dewiaditya.id` → Portal Saya → payslip & cuti tampil. **RISIKO:** Rendah.

---

## 🟠 RC-07 — Management Tools (`dewi_management_tools.py`)
- **Prioritas:** P1. **Dampak:** `/api/management/audit/permissions` (role kosong) & `/api/management/weekly-digest` (nol).
- **Item:** `91` `rahaza_users`→`users`(6, field `is_active`) · `142-148` `production_work_orders`→`rahaza_work_orders` · `151` `rahaza_invoices`→`rahaza_ar_invoices` · `172` `rahaza_attendance`→`rahaza_attendance_events` (issues `izin`/`sakit`) · `184-189` `marketing_live_sessions` field `revenue/orders`,datetime → `gmv/total_orders`,string · `192-197` `rahaza_racks`+`occupied/total_slots` → `wh_racks`(6) **TANPA** field okupansi → **drop metrik okupansi jujur** atau hitung dari sumber lain.
- **RISIKO:** Rendah-sedang. **DO-NOT:** jangan karang okupansi rak.

---

**➡ LANJUT: `SSOT_MASTER_REPAIR_PLAN_PART2.md`** (RC-08 Cashflow · RC-09 AR-360 · RC-10 GL-Mapping · RC-11 Variances/ControlTower/Phase7 · RC-12 Orphan Writes + anomali payroll_entries · RC-13 Notifikasi write-only · RC-14 Misc phantom · BACKLOG lama · ROADMAP eksekusi · APPENDIX verifikasi & false-positive registry).
