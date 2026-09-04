# QA / Bug Register — Flow Stock Opname (`flow-gudang-stock-opname2`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS, validator flow LULUS 10/10).

## Ringkasan
- **Status:** CLEAN — happy-path (start → scan → submit → approve + posting) terverifikasi via `tests/flow_gudang_stock_opname2_test.py`.
- **Posting terverifikasi:** `wh_positions.qty` 100 → 95 (variance −5) + jejak `wh_fg_movements` (source `opname_adjustment`).
- **Guardrail terverifikasi (5):**
  - Submit sesi tanpa item ter-count ditolak (400).
  - Approve sesi non-`pending_approval` ditolak (400).
  - Hanya 1 sesi warehouse `open` sekaligus (start kedua ditolak 400).
  - Scan pada sesi non-`open` (approved) ditolak (400).
  - Cancel sesi `approved` ditolak (400).
- **DB pristine:** hard-cleanup sesi + fixture posisi + movement.

## Temuan
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| OPN-01 | INFO | POC mengisolasi data via fixture `wh_positions` pada rack unik (`E2E-OPN-RACK`) + scope `rack`, sehingga posting hanya menyentuh posisi uji dan tidak memengaruhi data nyata. | NOTED |
| OPN-02 | LOW | Endpoint opname2 memakai guard `require_auth` (tanpa role-check di level API); pembatasan peran mengandalkan Portal/menu Gudang. Rekomendasi kebijakan maker–checker didokumentasikan di bagian RBAC. | NOTED |
| OPN-03 | INFO | `total_variance_value` dihitung sebagai `Σ|variance|` (nilai kuantitas, bukan nilai rupiah). Bila diperlukan nilai rupiah, perlu perkalian harga (di luar scope alur ini). | NOTED |
| OPN-04 | INFO | Scan berulang pada posisi yang sama menimpa nilai sebelumnya (last-write-wins), tidak menduplikasi item. By design. | NOTED |
| OPN-05 | INFO | Count-sheet PDF memerlukan pustaka `reportlab`; bila tidak tersedia, endpoint PDF dapat gagal (fitur pendukung, bukan happy-path). | NOTED |

## Bukti Uji
- `python3 tests/flow_gudang_stock_opname2_test.py` → **STOCK OPNAME FLOW ALL PASS**
  (start→scan(95/100)→submit→approve+posting; qty 100→95 + movement; 5 guardrail 400; DB pristine).
- `python3 scripts/docgen/validate_flow.py --flow-id flow-gudang-stock-opname2` → **LULUS 10/10**.
- `python3 scripts/docgen/audit_testids.py --module-id wms-opname-enhanced` → **LULUS (0 FAIL, 44 testid)**.
- **E2E UI (Playwright, Portal Gudang → Stok & Akurasi → tab Opname Stok):** buat sesi → buka detail → Scan (barcode E2EUIOPNPOS, qty 90 → System 100/Counted 90/Diff -10, toast "Counted 1/1") → Submit ("Menunggu Persetujuan") → Setujui ("Disetujui (adjustments applied)"). Posting terverifikasi (`wh_positions.qty` → 90 + 1 movement `opname_adjustment`). **Tidak ada logout**. Data E2E dibersihkan (DB pristine).

## Catatan E2E (agent-to-agent)
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| OPN-06 | LOW-UX | Setelah klik **Submit** pada dialog detail, dialog tidak auto-refresh ke status `pending_approval` sehingga tombol **Setujui** belum tampil di dialog yang sama; pengguna perlu menutup & membuka ulang detail. Fungsional benar (backend berubah ke pending). Rekomendasi minor: refresh `detailDialog` state setelah submit. | NOTED |
| OPN-07 | INFO | Selama E2E, klik Submit sempat gagal bila modal Scan masih terbuka (overlay). Setelah menutup modal Scan, submit → approve berjalan mulus. Artefak timing harness, bukan bug produk. | NOT-A-BUG |
| OPN-08 | INFO | Ditemukan & dibersihkan 18 residu E2E lintas koleksi (`rahaza_cash_movements`, `rahaza_material_issues`, `rahaza_material_movements`, `rahaza_material_stock`) sisa sesi flow sebelumnya (AP/Material WO/Cutting). DB kini pristine (0 residu). | CLEANED |
