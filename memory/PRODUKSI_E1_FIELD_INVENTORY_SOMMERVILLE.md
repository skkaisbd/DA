# E1 — FIELD INVENTORY LENGKAP (SOMMERVILLE = acuan Maklon identik + Produksi internal)
> Bagian analisis lanjutan (handoff §E1). GROUNDED ke kode:
> - SOMMERVILLE: `/tmp/sommerville/backend/server.py` (monolit 6.267 baris) — dijadikan acuan FIELD/COLLECTION persis untuk Maklon.
> - DA (fork): `/app/backend/routes/production_*.py` — dicek delta-nya per collection.
> Metode: baca dict `insert_one` tiap collection (bukan Pydantic — SOMMERVILLE pakai raw dict).
> STATUS: ANALISIS (belum eksekusi kode).

## 0. RINGKASAN — DA == SOMMERVILLE (terverifikasi ulang sesi ini)
- Dict `production_pos` & `po_items` DA (`routes/production_po.py:146-185`) **identik byte** dgn
  SOMMERVILLE (`server.py:810-837`) — DA hanya menambah batch-fetch variant/product (optimasi),
  field 100% sama, termasuk **2 harga** `selling_price_snapshot` + `cmt_price_snapshot`.
- Koleksi produksi DA = SOMMERVILLE: production_pos, po_items, po_accessories, production_jobs,
  production_job_items, production_progress, production_variances, production_returns,
  production_return_items, buyer_shipments, buyer_shipment_items, vendor_shipments,
  vendor_shipment_items, vendor_material_inspections, vendor_material_inspection_items,
  material_requests, material_defect_reports, invoices, payments.
- Frekuensi akses collection SOMMERVILLE (grep `db.<c>`): production_pos 60×, vendor_shipments 45×,
  production_jobs 45×, production_job_items 40×, vendor_shipment_items 38×, po_items 38×,
  buyer_shipment_items 37×, invoices 33×, material_requests 27×, buyer_shipments 23×,
  production_progress 19×, vendor_material_inspections 16×, production_returns 15×,
  po_accessories 12×, payments 13×, production_return_items 11×, material_defect_reports 11×,
  production_variances 10×.

**Implikasi adopsi:** Untuk **Maklon identik**, port collection+field ini APA ADANYA.
Untuk **Produksi internal**, pakai struktur sama + tambah field integrasi (ditandai `[DA+]`).

---

## 1. production_pos  (header PO produksi) — `server.py:810-819`, close `852-856`
| Field | Tipe | Asal/Default | Catatan |
|---|---|---|---|
| id | uuid str | new_id() | PK |
| po_number | str | body (WAJIB) | unik; dicek duplikat saat update (`906`) |
| customer_name | str | resolve dari buyer_id → `buyers.buyer_name` | |
| buyer_id | str | body | ref `buyers` |
| vendor_id | str | body | ref `garments` (vendor CMT) |
| vendor_name | str | resolve dari `garments.garment_name` | denormalisasi |
| po_date | datetime | parse_date / now() | |
| deadline | datetime | parse_date | deadline produksi |
| delivery_deadline | datetime | parse_date | deadline kirim |
| status | str | 'Draft'/'Confirmed' | state → Distributed → In Production → Completed → Closed |
| notes | str | body | |
| created_by, created_at, updated_at | str/dt | user/now | audit |
| **close_reason, close_notes, closed_by, closed_at** | on close | endpoint `/close` | field muncul saat status=Closed |
- **[DA+]** `production_po.py` dapat membuat PO dari `rahaza_orders` (demand internal) — lihat `:539-542`.

## 2. po_items  (line item PO) — `server.py:826-836`
| Field | Tipe | Catatan |
|---|---|---|
| id, po_id, po_number | str | FK ke PO (denormalisasi po_number) |
| product_id, product_name | str | ref `products` (SOMMERVILLE) / **[DA+] `rahaza_models`** utk internal |
| variant_id, size, color, sku | str | resolve dari `product_variants` |
| qty | int | qty dipesan (**ordered_qty**) |
| serial_number | str | optional |
| **selling_price_snapshot** | float | harga JUAL (dipakai INVOICE BYR / internal) |
| **cmt_price_snapshot** | float | harga jasa CMT (dipakai INVOICE VND / maklon) |
| created_at | dt | |
> Kunci: **satu item bawa 2 harga** → mendukung dua muka bisnis (jual internal vs jasa maklon).

## 3. po_accessories  (kebutuhan aksesoris PO) — `server.py:1001-1008` & `6016-6024`
| Field | Catatan |
|---|---|
| id, po_id | FK |
| accessory_id, accessory_name, accessory_code | ref accessories |
| qty_needed | int |
| unit | default 'pcs' |
| notes | |
| created_at / updated_at | |

## 4. vendor_shipments  (Admin kirim material ke Vendor) — `server.py:1309-1319`
| Field | Catatan |
|---|---|
| id, shipment_number, delivery_note_number | no. SJ material |
| vendor_id, vendor_name | tujuan vendor |
| po_id, po_number | ref PO |
| shipment_date | |
| shipment_type | 'NORMAL' \| 'ADDITIONAL' \| 'REPLACEMENT' |
| parent_shipment_id | untuk shipment turunan (ADDITIONAL/REPLACEMENT) |
| status | 'Sent' → (update) 'Received' |
| notes, created_by, created_at, updated_at | |
| **inspection_status, total_received, total_missing, inspected_at** | di-set saat inspeksi (`1491-1494`) |
- Efek samping: PO status Draft → **Distributed** saat ada shipment (`1346-1347`).

## 5. vendor_shipment_items — `server.py:1325-1339`
| Field | Catatan |
|---|---|
| id, shipment_id, shipment_number | FK |
| po_id, po_number, po_item_id, source_po_item_id | ref PO item |
| product_name, serial_number, size, color, sku | denormalisasi dari po_item |
| **qty_sent** | jumlah material dikirim ke vendor |
| ordered_qty | qty PO (kapasitas) |
| shipment_type, parent_shipment_id | |
| created_at | |
- Guard create (`1299-1307`): NORMAL tak boleh > sisa (ordered − already_sent).

## 6. vendor_material_inspections  (Vendor terima & inspeksi) — `server.py:1454-1462`
| Field | Catatan |
|---|---|
| id, shipment_id, shipment_number | FK |
| vendor_id, vendor_name | |
| inspection_date | |
| total_received, total_missing | agregat material |
| **total_acc_received, total_acc_missing** | agregat aksesoris |
| overall_notes | |
| status | 'Submitted' |
| submitted_by, created_at, updated_at | |
- Guard: 1 inspeksi per shipment (`1445-1446`).

## 7. vendor_material_inspection_items — `server.py:1466-1488` (dua subtipe)
**item_type='material'**: id, inspection_id, item_type, shipment_item_id, sku, product_name,
size, color, ordered_qty, **received_qty**, **missing_qty**, condition_notes, created_at.
**item_type='accessory'**: id, inspection_id, item_type, accessory_id, accessory_name,
accessory_code, unit, ordered_qty, received_qty, missing_qty, condition_notes, created_at.
- `received_qty` inspeksi → menjadi **available_qty** job_item (`1764`).
- Aksesoris kurang → auto `material_requests` REQ-ACC (`1548-1563`).

## 8. material_requests  (permintaan material/aksesoris tambahan/pengganti) — `server.py:1548-1561` & `3190`
| Field | Catatan |
|---|---|
| id, request_number | 'REQ-ACC-n-PO' / 'REQ-ADD-…' / 'REQ-RPL-…' |
| po_id, po_number, vendor_id, vendor_name | |
| request_type | 'ADDITIONAL' \| 'REPLACEMENT' |
| category | 'accessories' \| 'material' |
| original_shipment_id, original_shipment_number | asal |
| reason, vendor_notes | |
| status | 'Pending' → Approved/… |
| total_requested_qty | |
| items[] | [{accessory_name/sku, requested_qty, unit}] |
| created_by, created_at, updated_at | |
> Business rule Phase 16 (`1565-1569`): MISSING saat inspeksi → ADDITIONAL (vendor-driven);
> DEFECT saat produksi → REPLACEMENT (via defect-report flow).

## 9. production_jobs  (WO vendor) — `server.py:1740-1751`; child `1504-1516`
| Field | Catatan |
|---|---|
| id, job_number | 'JOB-0001'; child: '<parent>-A1' / '-R1' |
| parent_job_id, parent_job_number | untuk child job (ADDITIONAL/REPLACEMENT) |
| vendor_id, vendor_name | |
| po_id, po_number, customer_name | |
| vendor_shipment_id, shipment_number, shipment_type | asal material |
| deadline, delivery_deadline | dari PO |
| status | 'In Progress' → 'Completed' |
| notes, created_by, created_at, updated_at | |
- Guard: 1 job per vendor_shipment (`1720-1721`). Efek: PO → **In Production** (`1780-1781`).

## 10. production_job_items — `server.py:1765-1774`; child `1525-1533`
| Field | Catatan |
|---|---|
| id, job_id, job_number | FK |
| po_item_id, vendor_shipment_item_id | ref |
| product_name, sku, size, color, serial_number | |
| ordered_qty | dari po_item.qty |
| shipment_qty | qty_sent |
| **available_qty** | = received_qty inspeksi (kalau ada) atau qty_sent |
| **produced_qty** | 0 → diupdate oleh progress |
| created_at, updated_at | |
> Enrich GET (`1845-1862`): hitung shipped_to_buyer, received_to_buyer, remaining_to_ship,
> child_produced_qty, total_produced_qty (termasuk child jobs).

## 11. production_progress  (catat output harian) — job-item path `server.py:1903-1910`; legacy WO `1927-1935`
**job_item path (utama):** id, job_id, job_item_id, sku, product_name, size, color,
progress_date, **completed_quantity**, notes, recorded_by, created_at.
- Efek: job_item.produced_qty += completed_quantity (`1912`); job → Completed bila semua item
  produced ≥ shipment_qty (`1918-1919`).
- **Guard I-1** (`1887-1902`): new_total ≤ available_qty − Σ defect_qty (H-3 fix).
**legacy work_order path:** id, work_order_id, distribution_code, garment_id/name, po_id/number,
progress_date, completed_quantity, notes, recorded_by, created_at (mengupdate `work_orders`).

## 12. buyer_shipments  (Vendor kirim FG ke Buyer) — `server.py:2059-2066`
| Field | Catatan |
|---|---|
| id, shipment_number | 'SJ-BYR-<po>' |
| vendor_id, vendor_name | |
| po_id, po_number, customer_name | |
| job_id | ref job (1 master shipment / job / vendor) |
| ship_status | 'Pending' → 'Partially Shipped' → (…'Shipped') |
| notes, created_by, created_at, updated_at | |
| **last_dispatch, last_dispatch_seq** | per dispatch (`2126-2128`) |

## 13. buyer_shipment_items  (per-dispatch) — `server.py:2108-2119`
| Field | Catatan |
|---|---|
| id, shipment_id | FK |
| **dispatch_seq, dispatch_date** | dispatch bertahap (nomor urut) |
| po_item_id, job_item_id, job_id | ref |
| product_name, serial_number, size, color, sku | |
| ordered_qty | |
| **qty_shipped** | jumlah dikirim buyer |
| **qty_received** | (opsional; di-set saat buyer terima) → efektif utk kapasitas re-ship |
| created_at | |
- **Guard C-1** (`2084-2103`): Σ received + qty_shipped ≤ Σ produced (semua job+child).
- **Guard M-1** (`2079-2081`): total dispatch > 0.

## 14. material_defect_reports — `server.py:3346-3361`
| Field | Catatan |
|---|---|
| id, vendor_id | |
| job_id, job_item_id, po_id, po_item_id | ref (M-3: vendor_id bisa diturunkan dari job) |
| sku, product_name, size, color | |
| **defect_qty** | mengurangi kapasitas produksi (I-1) |
| defect_type | default 'Material Cacat' |
| description, shipment_id, report_date | |
| status | 'Reported' |
| reported_by, created_at, updated_at | |

## 15. production_returns  (Buyer retur ke Admin) — `server.py:3453-3462`
| Field | Catatan |
|---|---|
| id, return_number | 'RTN-0001' |
| reference_po_id, reference_po_number | |
| customer_name, buyer_name | |
| return_date, return_reason, notes | |
| status | 'Repair Needed' → (repair flow) |
| total_return_qty | |
| created_by, created_at, updated_at | |
- **Guard C-2/H-4** (`3427-3450`): qty ≥ 1; ≤ max_returnable = Σ shipped − Σ already_returned.

## 16. production_return_items — `server.py:3467-3476`
| Field | Catatan |
|---|---|
| id, return_id, po_item_id | FK |
| sku, product_name, serial_number, size, color | |
| return_qty | |
| defect_type, repair_notes | |
| repaired_qty | 0 → diupdate saat repair |
| created_at | |

## 17. production_variances  (over/under produksi) — `server.py:6069-6086`
| Field | Catatan |
|---|---|
| id, vendor_id, vendor_name | |
| job_id, job_number, po_id, po_number | |
| **variance_type** | 'OVERPRODUCTION' \| 'UNDERPRODUCTION' |
| reason, notes | |
| items[] | [{job_item_id, product_name, sku, ordered_qty, produced_qty, variance_qty}] |
| total_variance_qty | Σ variance_qty |
| reported_by | |
| status | 'Reported' → 'Acknowledged' → 'Resolved' |
| created_at, updated_at | |
- **[DA+] Finance bridge** (`production_variances.py:217-281`, Phase 7C): endpoint
  `POST /production-variances/{vid}/post-gl` + `/retry-posting`. Field tambahan: **variance_value**,
  `_posting_result` (transient). GL: OVER → Dr 1-1404 Inventory FG / Cr 5-9100 Variance Income;
  UNDER → Dr 6-4100 Variance Loss / Cr 1-1403 WIP. Unit cost dari `rahaza_models.cost_per_unit/price`.

## 18. invoices  (VND jasa & BYR jual) — `server.py:2424-2436`
| Field | Catatan |
|---|---|
| id, invoice_number | 'INV-VND-<po>-Rn' / 'INV-BYR-<po>-Rn' |
| invoice_type | 'MANUAL' (juga jalur auto) |
| **invoice_category** | 'VENDOR' (jasa CMT, pakai cmt_price) \| 'BUYER'/BYR (jual, pakai selling_price) |
| source_po_id, po_number | |
| vendor_or_customer_id, vendor_or_customer_name | |
| garment_id/name, vendor_id/name, customer_name | denormalisasi |
| invoice_items[] | [{..., invoice_qty, subtotal}]; invoice_qty MANUAL (bisa != produced) |
| total_amount, paid_amount, total_paid, remaining_balance | |
| status | 'Unpaid' → 'Partial' → 'Paid' |
| revision_number, discount, notes | |
| created_by, created_at, updated_at | |
- Terkait: `invoice_adjustments`, `invoice_edit_requests`, `invoice_change_history`.

## 19. payments — `server.py:2802-2811`
| Field | Catatan |
|---|---|
| id, invoice_id, invoice_number | FK |
| **payment_type** | 'VENDOR_PAYMENT' (bayar vendor CMT) \| 'CUSTOMER_PAYMENT' (terima dari buyer) |
| garment_id/name, vendor_or_customer_name | |
| payment_date, amount, payment_method | |
| reference_number, notes, recorded_by, created_at | |
- Guard: 0 < amount ≤ outstanding (`2798-2799`). Efek: invoice status/total_paid (`2816-2820`).

---

## 20. INVARIAN (dari PRODUCTION_FLOW_AUDIT.md — WAJIB dijaga saat port)
- **I-1** produced_qty ≤ available_qty − Σ defect_qty (progress guard).
- **I-2** Σ qty_shipped(buyer) ≤ Σ produced_qty (job+child).
- **I-3** Σ return_qty ≤ Σ shipped − Σ already_returned.
- **I-4** return_qty ≥ 1; qty_shipped ≥ 0; produced_qty > 0.
- **I-5** produced vs ordered = BEBAS (fitur variance over/under — JANGAN dibatasi).

## 21. BUG SOMMERVILLE yang HARUS di-fix saat port Maklon (jangan diwarisi)
> Sudah ada perbaikannya di SOMMERVILLE terbaru (Phase A) — verifikasi ada saat port:
- **C-1** cap ship = produced (bukan ordered) — SUDAH di `2084-2103`.
- **C-2** cap return = max_returnable — SUDAH di `3427-3450`.
- **C-3** job `total_shipped_to_buyer` query — cek enrich `1837-1862`.
- **H-1** clamp `remaining_qty_to_ship` + `over_shipped_qty` (PO list `:516`).
- **H-3** progress cap = available − defect — SUDAH di `1887-1902`.
- **H-4** reject return_qty<1 — SUDAH di `3436-3437`.
- **M-1** reject 0-qty dispatch — SUDAH di `2079-2081`.
- **H-2** auto REQ-RPL missing material — DIGANTI kebijakan Phase 16 (ADDITIONAL vendor-driven, `1565-1569`).
- **M-3** derive vendor_id di defect — cek `3345`.

## 22. STATE MACHINE RINGKAS (acuan port)
- **PO**: Draft → Confirmed → Distributed → In Production → Completed → Closed.
- **vendor_shipment**: Sent → Received (inspection_status: Inspected).
- **job**: In Progress → Completed.
- **buyer_shipment**: Pending → Partially Shipped → Shipped.
- **return**: Repair Needed → (repair) → …
- **variance**: Reported → Acknowledged → Resolved (+[DA] posted-gl).
- **invoice**: Unpaid → Partial → Paid.

## 23. DELTA DA vs SOMMERVILLE (yang harus disesuaikan utk PRODUKSI INTERNAL)
| Aspek | SOMMERVILLE (Maklon acuan) | DA Produksi internal [DA+] |
|---|---|---|
| Master produk | `products`/`product_variants`/`garments` | **`rahaza_models`+`rahaza_boms`** (dari RnD) |
| Sumber demand | manual PO | `rahaza_orders`/`marketing_orders`/`dewi_toko_orders` → PO (`production_po.py:539`) |
| Variance→GL | tak ada | `post-gl` Phase 7C (akun 1-1404/5-9100/6-4100/1-1403) |
| Costing unit | cmt_price/selling_price snapshot | `rahaza_models.cost_per_unit/price` |
| Material owner | vendor terima dari admin | Gudang DA (`rahaza_material_stock`) [bridge E4] |

---
*E1 selesai. Lanjut E2 (QC & Retur detail).*
