# QA / Bug Register — Flow AP/Hutang (`flow-keuangan-ap`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS).

## Ringkasan
- **Status:** CLEAN — happy-path (create bill → send/verifikasi → payment) terverifikasi via `tests/flow_keuangan_ap_test.py`.
- **Auto-posting GL:** aktif (send → Dr Persediaan/Beban / Cr Hutang Usaha; payment → Dr Hutang Usaha / Cr Bank), `_posting_result.ok=true`.
- **Guard overpay:** aktif (TOCTOU-safe via aggregation conditional update).

## Temuan
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| AP-01 | INFO | AP dapat dibuat manual (`/ap-invoices`) atau via 3-way match dari GR (`/ap-invoices/from-gr`). | NOTED |
| AP-02 | INFO | Pembayaran tanpa `account_id` tidak mengubah saldo kas (pencatatan hutang lunas tanpa link kas). | NOTED |

## Bukti Uji
- `python3 tests/flow_keuangan_ap_test.py` → **AP FLOW ALL PASS** (bill AP total 5.000.000 → sent (JE) → paid balance 0 (JE) → aging 200).
