# AUDIT PORTAL MAKLON — 2026-09-03 (iteration_104, READ-ONLY, belum diperbaiki)

Cakupan: WO maklon → Kirim material CMT → CMT Receipt/QC → Serah terima FG (Dispatch ke Buyer) →
tagihan (AR klien / AP vendor) → tutup PO, backend + frontend. Metode: baca kode, probe API dengan
token admin/klien/vendor, testing agent UI sweep 24 menu (0 crash / 0 console error / 0 4xx-5xx),
skrip lama `tests/flow_maklon_*` (inti 17/17 & client_portal 29/29 lulus; sommerville/edges/cmt_vendor
sudah basi: memakai nomor PO bebas, status `Draft`, endpoint defect yang di-410 — bukan bug produk).

## TEMUAN (urut prioritas)

### P0 — Keamanan / kebocoran data
**M-01 RBAC lintas klien bocor di `/api/dewi/maklon/*` dan `/api/prod/cmt-receipts`.**
Token `klien_maklon` (Aruna) & `cmt_vendor` (JMC) mendapat 200 dan melihat data klien LAIN (PT Langit):
`GET /api/dewi/maklon/pos`, `/pos/{id}/360` (PO klien lain), `/invoices`, `/clients`, `/summary`,
`/payments`, `/reports/aging`, `/api/prod/cmt-receipts`. `/api/production/cmt-billing?scope=maklon`
menolak klien (403) tapi masih 200 untuk vendor. Engine (`/api/production-pos`) sudah benar (403 via
`deny_klien`). Akar: router `dewi_maklon*.py`, `dewi_maklon_po_360.py`, `dewi_maklon_billing.py`,
`dewi_cmt_packing.py` hanya `require_auth`.

**M-02 Klien/vendor bisa MENULIS penerimaan FG dari CMT.** Terbukti: klien `POST /api/prod/cmt-receipts`
→ 201, `POST …/lines` (qty_actual 20) → 201, `DELETE …/lines/{id}` → 200. Hanya `complete-qc`/`approve`/
`reject`/`short-shipments/resolve` yang berpagar `require_perm`. (`dewi_cmt_packing.py` L311-583)

### P1 — Logika angka / uang
**M-03 Mirror finance `dewi_maklon_pos` tidak disinkron saat PO ditutup.** `close_po` & `close_po_short`
(`production_pos.py` L587-696) tidak memanggil `try_sync_maklon_finance` (transisi status biasa memanggil).
Bukti: PO-MK-DEMO-3 `production_pos.status='Closed'` tapi mirror `production_po_status='In Production'`
→ Detail PO 360 / Dashboard Maklon / portal klien menampilkan status lama. Ditambah
`PO_STATUS_TO_MAKLON` (`production_maklon_bridge.py` L24) tidak punya kunci `'Closed Short'` → bila
disinkron, PO Closed Short dipetakan ke `'draft'`.

**M-04 Dua sistem invoice untuk satu PO maklon, seri nomor sama, saling menimpa.**
(a) Bridge membuat Draft AR otomatis di `rahaza_ar_invoices` (`INV-MKL-{YYYY}-{SEQ}`, counter
`dewi_maklon.ar_invoice_number`) saat PO Confirmed. (b) Layar **Invoice** (`MaklonBillingModule` →
`POST /api/dewi/maklon/invoices/generate`) membuat dokumen LAIN di `dewi_maklon_invoices` dengan prefix
`INV-MKL` dari counter berbeda → nomor kembar (demo: `INV-MKL-2026-0001` ada di KEDUA koleksi untuk PO
berbeda). `generate` juga menimpa `dewi_maklon_pos.ar_invoice_id/number` dengan id `dewi_maklon_invoices`
→ tautan ke AR draft hilang: `finalize_ar_on_short_close` & `GET /production-pos/{id}/maklon-finance`
mencari `rahaza_ar_invoices` dengan id yang salah (nota kredit / penyesuaian close-short TIDAK pernah
terbit), layar Invoice tidak menampilkan AR otomatis, dan pendapatan bisa dobel bila keduanya diposting
(AR 3.000.000 draft + invoice manual 3.330.000 untuk PO-MK-DEMO-3).

**M-05 Invoice manual menagih qty ORDER, bukan qty terkirim, dan meratakan harga.** `generate_invoice`
memakai `po_to_legacy_order` (`_maklon_adapter.py` L165+): satu baris `qty_ordered` × `avg_price`
(rata-rata tertimbang lintas item). PO 2 item dengan harga berbeda / pengiriman parsial ditagih penuh
dengan harga rata-rata; PPN default 11% dari config tanpa terlihat di form.

**M-06 AP ke vendor CMT = harga jual ke klien (margin maklon selalu 0).** `mature_ap_from_cmt_receipt`
(`production_maklon_bridge.py` L258-426) menghitung hutang vendor = Σ qty_actual × `po_items.cmt_price_snapshot`,
sedangkan AR ke klien memakai field yang SAMA (L81, L170). Tidak ada tarif vendor di `vendor_partners`,
`production_jobs`, maupun `vendor_shipments`. Untuk PO INTERNAL ini benar (cmt_price = upah jahit);
untuk MAKLON satu field dipakai untuk dua harga berbeda.

**M-07 Kapasitas kirim menghitung penerimaan yang BELUM selesai QC.** `core/dispatch_capacity.py`
`_rows_from_receipt_lines` tidak menyaring status `cmt_receipts` → `qty_actual` yang diketik saat masih
`on_qc` sudah masuk `shippable` di `/buyer-dispatch-capacity`, `/buyer-dispatch-outstanding`, dan
`map_for_validation` (jalur po_item "missing"). Terbukti: receipt on_qc qty_actual 20 → shippable 20.
Pagar `source_receipt_ids` masih menolak receipt on_qc, tapi kapasitas layar & jalur po_item lain tidak.

**M-08 `sync_po_to_maklon_finance.qty_dispatched` tidak menyaring `receiver_type`.** Agregasi
`buyer_shipment_items` (L70-74) ikut menghitung deklarasi CMT→DA (`receiver_type='da'`) → mirror bisa
"partial_delivered" & qty_dispatched naik padahal barang baru sampai DA, belum ke buyer.
(`compute_po_fulfillment` sudah benar memakai `_buyer_shipment_ids_for_po`.)

### P2 — Tampilan angka tidak konsisten antar layar
**M-09 Detail PO 360 membaca koleksi legacy.** `dewi_maklon_po_360.py` L118-138 memakai
`dewi_maklon_dispatches` (kosong) → "Dikirim 0/150" & "0/200", `dispatch_pct 0`, `item.qty_dispatched`
ditimpa 0 (L137) padahal di respons yang sama `progress_breakdown.qty_dispatched=60`. Invoice 360 hanya dari
`dewi_maklon_invoices`.

**M-10 Satu PO, empat label status.** PO-MK-DEMO-2: `In Production` (PO Maklon, Tutup PO), `Sebagian
Terkirim`/`partial_delivered` (Detail PO, mirror), `Packing` (Dashboard Maklon via `PO_TO_LEGACY_STATUS`),
`Partially Shipped` (Dispatch). PO-MK-DEMO-3: `Closed` vs `Ditagih`/`invoiced`.

**M-11 Dashboard Maklon (`/api/dewi/maklon/summary`)**: `total_revenue` = Σ `total_value` SEMUA PO
(termasuk Draft/cancelled, bukan invoice terbit); `in_production` dihitung dari status legacy
(`cutting/sewing/qc/packing`) yang tidak pernah ditulis mirror; `completed_orders=0` padahal DEMO-3 Closed;
"Order Terbaru" menyembunyikan PO Draft.

**M-12 Tutup PO tab "Perlu Ditutup"** memuat PO Draft tanpa produksi (noise); **Dispatch ke Buyer**
progres per SJ "60 / 100" berbasis item yang ada di SJ, bukan total PO (150) — bertentangan dengan aturan
"satu PO = satu SJ yang progresnya naik ke 100%".

**M-13 Portal klien tidak terjangkau dari login biasa.** `klien_maklon` login di `/` → PortalSelector
"Tidak ada akses" di semua kartu; jalur klien hanya `/klien-maklon` (App.js L439-442, tidak ada redirect
seperti `cmt_vendor` L672/L883).

### P3 — Kebersihan
**M-14 Endpoint tulis engine LEGACY masih hidup tanpa UI:** `POST /api/dewi/maklon/pos`, `/pos/{id}/confirm`
(membuat AR + production_pos), `/dispatches`, `/dispatches/{id}/confirm` (`dewi_maklon_pos.py`). Jalur
kedua untuk membuat PO/dispatch/invoice maklon di luar engine → sumber angka bercabang & nomor bersaing.
**M-15 Skrip uji maklon basi** (`flow_maklon_sommerville_test.py`, `flow_maklon_edges_test.py`,
`flow_maklon_cmt_vendor_test.py`) — regresi otomatis maklon praktis tidak berjalan.

## USULAN PERBAIKAN (menunggu persetujuan pemilik)
1. M-01/M-02: `deny_klien` + scope `buyer_id` di semua router dewi_maklon*/po_360/billing; pagar tulis
   `require_perm('cmt.manage')` untuk create/lines/delete receipt; vendor hanya receipt miliknya.
2. M-03/M-08: panggil `try_sync_maklon_finance` di `close_po` & `close_po_short`; tambah `'Closed Short'`
   ke peta status; filter `receiver_type='buyer'` pada agregasi dispatched.
3. M-04/M-05: SATU sumber invoice — layar Invoice menampilkan/menerbitkan AR bridge (`rahaza_ar_invoices`)
   per PO engine; `generate` legacy hanya untuk PO tanpa mirror/production_pos, dan tidak menimpa
   `ar_invoice_id`; qty tagihan = qty terkirim/diterima per item dengan harga per item.
4. M-06: field tarif vendor terpisah (`po_items.vendor_cmt_rate` / `production_jobs.rate_per_pcs`, default
   dari master vendor) untuk AP; `cmt_price_snapshot` tetap harga jual jasa ke klien.
5. M-07: `_rows_from_receipt_lines` hanya receipt `completed_qc` (SSOT `core/cmt_receipt_status`).
6. M-09..M-12: 360 & Dashboard membaca `buyer_shipments` + status engine (`production_pos`) lewat satu
   pemetaan label Indonesia; Tutup PO sembunyikan Draft tanpa produksi; progres SJ berbasis total PO.
7. M-13: redirect `klien_maklon` → `/klien-maklon` setelah login.
8. M-14/M-15: matikan (410) endpoint tulis legacy atau alihkan ke engine; perbarui suite uji maklon.
