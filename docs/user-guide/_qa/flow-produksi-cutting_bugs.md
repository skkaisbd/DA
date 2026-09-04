# QA / Bug Register — Flow Cutting (`flow-produksi-cutting`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS).

## Ringkasan
- **Status:** CLEAN — happy-path (request → approve → batch → eksekusi status) terverifikasi via `tests/flow_produksi_cutting_test.py`.
- **Guard transisi:** status batch forward-only (in_cutting → cut_done → assigned_to_cmt); transisi mundur & dari status terminal ditolak.
- **Guard approval:** hanya request `pending_approval` yang bisa di-approve/reject.

## Temuan
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| CUT-01 | LOW | `CuttingProcessModule.jsx` (tab Planning dari `CuttingHubModule`) minim `data-testid` pada elemen request/batch — testid ditambahkan untuk testabilitas E2E. | FIXED |
| CUT-02 | INFO | Batch dapat dibuat mandiri (tanpa request) atau tertaut request (request → in_cutting). | NOTED |

## Bukti Uji
- `python3 tests/flow_produksi_cutting_test.py` → **CUTTING FLOW ALL PASS** (request pending→approved; batch in_cutting→cut_done; guard backward ditolak; summary 200).
