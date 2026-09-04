# QA / Bug Register — Flow Kas & Rekonsiliasi Bank (`flow-keuangan-kas-bank`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS, 30 assertions).

## Ringkasan
- **Status:** CLEAN (setelah 1 fix HIGH) — happy-path lintas 3 modul (Kas Kecil → Transfer Bank →
  Rekonsiliasi Bank) terverifikasi via `tests/flow_keuangan_kas_bank_test.py`.
- **Auto-posting GL:** aktif & idempoten untuk semua transaksi kas/bank (`source_ref`).
- **Guardrail:** saldo kas kecil, replenish-via-txn, fund closed, transfer akun-sama, void ganda,
  periode salah, sesi duplikat, approve-unmatched, approved-locked — semua menolak dengan kode benar.
- **DB:** PRISTINE setelah cleanup (0 residu; 0 JE ber-flag `is_matched`).

## Temuan
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| RC-FLOW-kasbank-1 | **High** | RBAC: `FINANCE_ROLES` pada `rahaza_petty_cash.py` & `rahaza_bank_transfers.py` hanya `('superadmin','admin','owner','finance')`. Role Finance kanonik di sistem = **`accounting`**/`staff_keuangan` (akun `finance@dewiaditya.id` → role `accounting`), sehingga staf Keuangan **DITOLAK 403** saat membuat/replenish/close dana kas kecil & membuat/void transfer bank. Kelas bug sama dengan RC-FLOW-expense-1. | ✅ FIXED + diverifikasi |
| KB-02 | INFO | `POST /api/finance/petty-cash/transactions` (expense/advance/return) hanya butuh `require_auth` (boleh kasir); pembuatan dana/replenish/close dibatasi FINANCE_ROLES (by-design: segregation of duties). | NOTED |
| KB-03 | INFO | Endpoint Bank-Recon (`/api/finance/bank-recon/*`) hanya butuh autentikasi (tanpa role-gate). Bila perlu pembatasan approver, tambahkan cek role di `approve_session`. | NOTED (enhancement) |
| KB-04 | INFO | Auto-match menulis flag `is_matched`/`matched_txn_id` (ADDITIVE) ke `rahaza_journal_entries`; tidak mengubah angka akuntansi. Skrip uji mereset flag ini saat cleanup agar seed JE tetap bersih. | NOTED |

## Detail RC-FLOW-kasbank-1 (High)
- **Repro (sebelum fix):** login `finance@dewiaditya.id` (`Dewi@123`, role `accounting`) →
  `POST /api/finance/petty-cash/funds` **→ 403**; `POST /api/finance/bank-transfers` **→ 403**.
- **Expected:** staf Keuangan boleh mengelola dana kas kecil & transfer bank.
- **Root cause:** daftar role finance di dua modul tidak menyertakan nama role kanonik `accounting`
  & `staff_keuangan` (bandingkan `employee_expense_claims.py:464` yang sudah menyertakannya).
- **Perbaikan (file:baris):**
  - `backend/routes/rahaza_petty_cash.py` → `FINANCE_ROLES = ('superadmin','admin','owner','finance','accounting','staff_keuangan','finance_manager')` (juga `ALL_ROLES`).
  - `backend/routes/rahaza_bank_transfers.py` → `FINANCE_ROLES = (... 'accounting','staff_keuangan','finance_manager')`.
- **Verifikasi (sesudah fix):** `POST .../petty-cash/funds` **→ 200**; `POST .../bank-transfers` **→ 200**
  (empiris via curl + skenario RBAC pada skrip uji, TC-11 & TC-12 PASS).
- **Sistemik:** koleksi `role_permissions` kosong → banyak endpoint mengandalkan cek role-string
  hardcode. Saat menambah role ke portal Keuangan, pastikan nama role-nya terdaftar di endpoint terkait.

## Bukti Uji
- `python3 tests/flow_keuangan_kas_bank_test.py` → **=== KAS & REKONSILIASI BANK FLOW: ALL PASS (30 assertions) ===**
  lalu `CLEANUP: … DB pristine`.
- Cakupan: kas kecil opening/expense/replenish/close (+guard), transfer bank + void (+guard),
  rekonsiliasi create/import-bulk/auto-match(2/2)/match/unmatch/approve (+guard 409/400), RBAC 200.
