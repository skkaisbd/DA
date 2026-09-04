# QA / Bug Register — Flow Material WO (`flow-produksi-material-wo`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS).

## Ringkasan
- **Status:** CLEAN — happy-path (reservasi/Material Issue → pengeluaran/issue → retur) terverifikasi via `tests/flow_produksi_material_wo_test.py`.
- **Auto-posting GL:** issue → Dr WIP (1-330) / Cr Persediaan BB (1-310), `_posting_result.ok=true` (memerlukan material punya `unit_cost`).
- **Guard stok:** approve/issue menolak bila stok tidak cukup (shortage) dan TOCTOU-safe (find_one_and_update qty>=required).

## Temuan
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| MWO-01 | INFO | Auto-JE inventory issue bernilai 0 (tidak posting) bila material tanpa `unit_cost` — perilaku best-effort by design. | NOTED |
| MWO-02 | INFO | Stok RM diisi via inbound/receiving atau seed; tidak ada API stock-in langsung pada router material-issues. | NOTED |

## Bukti Uji
- `python3 tests/flow_produksi_material_wo_test.py` → **MATERIAL WO FLOW ALL PASS** (MI draft→pending→issued posting_ok=True; retur create→submit→approve→receive).
