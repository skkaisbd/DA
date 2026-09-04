# QA — Alur Penggajian (SDM/HRIS)

## Ringkasan
- **Dokumen:** [`sdm/flow-sdm-payroll.md`](../sdm/flow-sdm-payroll.md)
- **Skrip uji backend:** `tests/flow_sdm_payroll_test.py` — Run -> Finalize(JE) -> Pay(JE) **ALL PASS** (net 5jt, 2 JE ter-posting).
- **Uji UI E2E (iteration_81):** Buat Run -> Finalisasi -> Bayar Gaji **PASS 100%**.
- **Modul tersentuh:** `hr-payroll-hub` (tab Proses Gaji).

## Temuan
| ID | Severity | Status | Ringkas |
|---|---|---|---|
| PR-01 | — | ✅ CLEAN | Tidak ada bug fungsional/testabilitas. Modul Payroll Run sudah punya `data-testid` lengkap (pr-create, pr-create-from/to, pr-create-submit, pr-row-{no}, pr-finalize-{no}, pay-btn-{no}, pay-dialog, pay-confirm-btn). |

### Observasi (bukan bug)
- Payroll Run hanya memproses karyawan yang memiliki **payroll profile aktif**; tanpa profil, create run menolak dengan 400 (by design).
- Finalisasi dan Bayar keduanya auto-post JE (idempotent). Bank pembayaran divalidasi terhadap COA (`rahaza_coa_accounts`).
