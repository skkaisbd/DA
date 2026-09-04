# QA — Alur Inbound Gudang (`flow-gudang-inbound`)

> Catatan QA untuk dokumen berbasis alur Portal Gudang. Materi training di
> `gudang/flow-gudang-inbound.md` wajib bebas bug; temuan dicatat di sini + `BUG_REGISTER.md`.

## Ringkasan
- **Dokumen:** [`gudang/flow-gudang-inbound.md`](../gudang/flow-gudang-inbound.md) — LULUS `validate_flow.py` **10/10**, rubrik 97/100.
- **Skrip uji backend:** `tests/flow_gudang_inbound_test.py` — **16/16 PASS** (self-cleanup terverifikasi).
- **Uji UI E2E (Sesi #77, iteration_77):** **4/4 fase PASS (100%)** — PO→Approval→GRN→Put-away tuntas satu sesi.
- **Audit test-id statis:** `scripts/docgen/audit_testids.py --module-id wh-purchase-orders wh-receiving wh-putaway` — **0 FAIL**.
- **Modul tersentuh:** `wh-purchase-orders`, `wh-receiving`, `wh-putaway`.

## Temuan
| ID | Severity | Status | Ringkas |
|---|---|---|---|
| GI-01 | MEDIUM | ✅ FIXED (Sesi #77) | `submitPO` memakai `window.confirm()` native → memblokir otomasi & UX tidak konsisten, tombol Setujui tak muncul instan. Diganti **modal** `po-submit-confirm-btn` + `await fetchList()` (auto-refresh). |
| GI-02 | **HIGH** | ✅ FIXED (Sesi #77) | **Put-away selalu gagal 400**: frontend `PutAwayModule` mengirim `{stock_id, qty}` padahal backend `/api/wms/legacy/putaway` menunggu `{source_stock_id, quantity}`. Payload diselaraskan ke kontrak backend. |
| GI-03 | **HIGH** | ✅ FIXED (Sesi #77) | Dropdown lokasi tujuan put-away kosong: `binLocations` memfilter `type==='bin'\|\|'zone'` sedangkan lokasi simpan bertipe `storage` → tak pernah muncul. Filter diubah agar menyertakan storage/staging (exclude receiving/shipping). |
| GI-04 | MEDIUM | ✅ FIXED (Sesi #77) | Field input SKU di GRN tak punya testid — `scan-sku-{idx}` justru menunjuk **tombol** scanner → `page.fill` gagal. Ditambah `sku-input-{idx}` pada input; qty diberi `item-received-{idx}` & `item-expected-{idx}`. |
| GI-05 | LOW | ✅ FIXED (Sesi #77) | Opsi combobox lokasi/material sulit ditarget deterministik (value=UUID). Ditambah testid readable `gr-location-option-{code}` & `item-material-option-{code}` (via dukungan `opt.testId` di `Combobox.jsx`). |
| GI-06 | LOW | ✅ FIXED (Sesi #77) | List stok put-away tak menampilkan lokasi → tampak "100" tak berubah pasca put-away (padahal pindah ke rak). Ditambah label **kode–nama lokasi** per baris stok. |

### Observasi (bukan bug)
- **A4 WARN (Low, INFO):** sejumlah elemen interaktif non-kritikal (kontrol filter/paginasi,
  input di dialog master) belum ber-testid. Di luar jalur inbound; tidak menghambat E2E happy-path.
- **Dual receiving path (INFO):** GRN bisa dibuat dari **modul Penerimaan** (`/api/wms/legacy/receiving`)
  maupun langsung dari layar PO (`/api/rahaza/purchase-orders/{id}/create-gr`). Alur inti memakai
  modul Penerimaan (sesuai grup nav Inbound). Keduanya sah, bukan bug.

## Audit Statis (detail)
- A1 (duplikat lintas-file): **PASS** — 0 duplikat.
- A2 (duplikat dalam-file): **PASS**.
- A3 (prop-forwarding testid): **PASS**.
- A4 (interaktif tanpa testid): **WARN** (non-blocker, di luar jalur kritikal).
