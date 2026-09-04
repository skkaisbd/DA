# QA — Alur Outbound Gudang (Surat Jalan)

## Ringkasan
- **Dokumen:** [`gudang/flow-gudang-outbound.md`](../gudang/flow-gudang-outbound.md)
- **Skrip uji backend:** `tests/flow_gudang_outbound_test.py` — Pick List + Surat Jalan **ALL PASS**.
- **Uji UI E2E (iteration_78):** Surat Jalan draft -> issue -> received **PASS 100%**.
- **Modul tersentuh:** `wh-picklist`, `wms-delivery-notes`.

## Temuan
| ID | Severity | Status | Ringkas |
|---|---|---|---|
| GO-01 | MEDIUM | ✅ FIXED | UI Surat Jalan tidak punya tombol **Terima** (receive) padahal endpoint `/receive` ada di backend (FE<->BE gap). Ditambah tombol `receive-btn-{sj_number}` untuk SJ berstatus `issued`. |
| GO-02 | LOW | ✅ FIXED (testing agent) | `handleIssue` memanggil `/issue` tanpa body → potensi 422. Ditambah `body: JSON.stringify({})`. |

### Observasi (bukan bug)
- Pick List UI dibuat dari **source** (shipment/material issue/pending movement); pembuatan manual item didukung di API. Alur inti UI difokuskan pada Surat Jalan (dokumen legal pengiriman) yang self-contained.
