# QA / Bug Register — Flow Jurnal & Akuntansi (`flow-keuangan-jurnal`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS).

## Ringkasan
- **Status:** CLEAN — happy-path (COA → jurnal berimbang → posting → laporan) terverifikasi via `tests/flow_keuangan_jurnal_test.py`.
- **Guard keseimbangan:** jurnal tidak seimbang (Debit≠Credit) ditolak 400.
- **Guard akun:** akun non-aktif / header (is_group) ditolak sebagai baris jurnal.
- **Guard periode:** posting ke periode closed/locked ditolak 423.

## Temuan
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| JE-01 | INFO | `general-ledger` report membutuhkan query `account_code`. | NOTED (didokumentasikan) |
| JE-02 | INFO | Jurnal dapat langsung diposting saat create (`post=true`) atau via `/journals/{id}/post`. | NOTED |

## Bukti Uji
- `python3 tests/flow_keuangan_jurnal_test.py` → **JURNAL FLOW ALL PASS** (jurnal posted berimbang 1.000.000; unbalanced ditolak; laporan trial-balance/balance-sheet/profit-loss/general-ledger 200).
