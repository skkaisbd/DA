# LAPORAN VERIFIKASI PORTAL VENDOR CMT (End-to-End)

_Dibuat otomatis dari eksekusi nyata API — 21 Jul 2026 17:23 UTC_

**Hasil total: 51 PASS / 0 FAIL** dari 51 langkah, 3 skenario.

Sumber: `tests/vendor_portal_e2e_scenarios.py` (idempoten, self-clean). Log mentah: `tests/vendor_portal_e2e_log.json`.


## Ringkasan Alur (SSOT) yang Diuji
`Master Data (partner+akun)` → `PO Maklon` → `Konfirmasi` → `DA Dispatch Potongan (vendor_shipment)` → `Received`
→ **[PORTAL VENDOR]** `Inspeksi` → `Buat Job` → `Lapor Progress` → `Deklarasi Setoran ke DA`
→ **[DA]** `Terima & QC (cmt_receipt: qty_actual/reject) → Submit → Approve` → `Kirim ke Buyer (source_receipt_ids)` = **COMPLETE**

Aktor: **admin@garment.com** (DA), **vendor cmt_vendor** (dibuat tiap skenario), **klienmaklon** (uji RBAC).


## SKENARIO 1 — Happy Path (semua lolos)
_Alur normal penuh: 100 pcs dikirim, diterima utuh, diproduksi 100%, QC 0 reject (pass 100%), dikirim ke buyer. **Expected: selesai bersih.**_

**17/17 langkah PASS.**

| # | Langkah | Aksi (endpoint) | Input inti | Expected | Output nyata | Status |
|---|---------|-----------------|------------|----------|--------------|:---:|
| 1 | M1 Buat Vendor Partner (master) | `POST /api/vendor-portal/partners` | name=CMT Alpha Jaya, code=CMT-ALP, contact_name=PIC CMT-ALP, contact_phone=0812-0000-0001 | 201/200 + partner tersimpan | HTTP 200 · id=light-mode-cards | ✅ |
| 2 | M2 Buat Akun Login Vendor (master) | `POST /api/vendor-portal/accounts` | email=alpha.cmt@dewi.test, name=CMT Alpha Jaya (User), password=***, partner_id=8332edf6-5 | 201/200 + akun cmt_vendor terhubung partner | HTTP 200 · id=light-mode-cards | ✅ |
| 3 | M3 Login Portal Vendor | `POST /api/auth/login` | email=alpha.cmt@dewi.test, password=*** | vendor bisa login (role cmt_vendor) | HTTP 200 · ok=True | ✅ |
| 4 | O1 Buat PO Maklon | `POST /api/production-pos` | po_number=PO-VP-S1, business_type=maklon, buyer_id=mk-client-demo-1, vendor_id=8332edf6-55 | 201 + business_type=maklon | HTTP 201 · id=light-mode-cards, status=Draft, po_number=PO-VP-S1 | ✅ |
| 5 | O2 Konfirmasi PO (Draft→Confirmed) | `POST /api/production-pos/8208f679-7ca7-43bd-91a9-637ca46d45dc/status` | status=Confirmed | 200 status=Confirmed | HTTP 200 · id=light-mode-cards, status=Confirmed, po_number=PO-VP-S1 | ✅ |
| 6 | D1 DA Dispatch Potongan ke CMT | `POST /api/vendor-shipments` | shipment_number=SJ-VP-S1, vendor_id=light-mode-cards, items=[{'po_id': | 201 shipment Sent | HTTP 201 · id=light-mode-cards, status=Sent, po_number=PO-VP-S1, shipment_number=SJ-VP-S1 | ✅ |
| 7 | D2 Tandai Shipment Received | `PUT /api/vendor-shipments/aa3d73c7-5da4-4b71-b973-40a03912db12` | status=Received | 200 status=Received | HTTP 200 · id=light-mode-cards, status=Received, po_number=PO-VP-S1, shipment_number=SJ-VP-S1 | ✅ |
| 8 | V1 Vendor Inspeksi Material (100 diterima) | `POST /api/vendor-material-inspections` | shipment_id=light-mode-cards, items=[{'shipment_item_id': 'df79b9b5-14 | 201 received 100 missing 0 | HTTP 201 · id=light-mode-cards, status=Submitted, shipment_number=SJ-VP-S1 | ✅ |
| 9 | V2 Vendor Buat Job Produksi | `POST /api/production-jobs` | vendor_shipment_id=light-mode-cards | 201 + item available_qty=100 | HTTP 201 · id=light-mode-cards, status=In Progress, po_number=PO-VP-S1, shipment_number=SJ-VP-S1 | ✅ |
| 10 | V3 Vendor Lapor Progress 100 (selesai) | `POST /api/production-progress` | job_item_id=light-mode-cards, completed_quantity=100 | 201 progress tercatat | HTTP 201 · id=light-mode-cards | ✅ |
| 11 | V4 Vendor Deklarasi Setoran ke DA | `POST /api/buyer-shipments` | po_id=light-mode-cards, job_id=light-mode-cards, r | 201 receiver_type=da + auto cmt_receipt Draft | HTTP 201 · id=light-mode-cards, po_number=PO-VP-S1, shipment_number=SJ-CMT-DA-202607-0005 | ✅ |
| 12 | A1 DA Temukan CMT Receipt (auto) | `GET /api/prod/cmt-receipts` | related_shipment_id=light-mode-cards | receipt Draft auto-terbentuk | HTTP 200 · id=light-mode-cards, status=Draft, po_number=PO-VP-S1, total_actual=0, total_rejected=0 | ✅ |
| 13 | A2 DA Isi Qty Aktual (100 lolos, 0 reject) | `PUT /api/prod/cmt-receipts/b8348440-0d72-4c76-b1b0-992c38562744/lines/bdf87869-0f0c-473b-b77e-8e8f55d05d39` | qty_actual=100, reject_qty=0 | 200 qty_actual=100 | HTTP 200 · id=light-mode-cards | ✅ |
| 14 | A3 DA Submit Receipt | `POST /api/prod/cmt-receipts/b8348440-0d72-4c76-b1b0-992c38562744/submit` |  | 200 status=Submitted | HTTP 200 · id=light-mode-cards, status=Submitted, po_number=PO-VP-S1, total_actual=100, total_rejected=0 | ✅ |
| 15 | A4 DA Approve Receipt (FG masuk) | `POST /api/prod/cmt-receipts/b8348440-0d72-4c76-b1b0-992c38562744/approve` |  | 200 status=Approved | HTTP 200 · id=light-mode-cards, status=Approved, po_number=PO-VP-S1, total_actual=100, total_rejected=0 | ✅ |
| 16 | A5 DA Kirim ke Buyer (COMPLETE) | `POST /api/buyer-shipments` | po_id=light-mode-cards, vendor_id=light-mode-cards | 201/200 buyer shipment dari receipt approved | HTTP 201 · id=light-mode-cards, po_number=PO-VP-S1, shipment_number=SJ-BYR-202607-0003 | ✅ |
| 17 | X1 Ringkasan PO (produced=100) | `GET /api/production-pos/8208f679-7ca7-43bd-91a9-637ca46d45dc/quantity-summary` |  | produced=100 | HTTP 200 · produced=100 | ✅ |

## SKENARIO 2 — Reject & Variance (ada masalah kualitas)
_Material kurang 5 saat inspeksi (95 diterima), produksi 95, QC DA menemukan 7 reject (pass 88/95 = 92,6%), variance underproduction 5. **Expected: kekurangan & reject terlacak.**_

**16/16 langkah PASS.**

| # | Langkah | Aksi (endpoint) | Input inti | Expected | Output nyata | Status |
|---|---------|-----------------|------------|----------|--------------|:---:|
| 1 | M1 Buat Vendor Partner (master) | `POST /api/vendor-portal/partners` | name=CMT Beta Karya, code=CMT-BET, contact_name=PIC CMT-BET, contact_phone=0812-0000-0001 | 201/200 + partner tersimpan | HTTP 200 · id=light-mode-cards | ✅ |
| 2 | M2 Buat Akun Login Vendor (master) | `POST /api/vendor-portal/accounts` | email=beta.cmt@dewi.test, name=CMT Beta Karya (User), password=***, partner_id=c2405abb-69 | 201/200 + akun cmt_vendor terhubung partner | HTTP 200 · id=light-mode-cards | ✅ |
| 3 | M3 Login Portal Vendor | `POST /api/auth/login` | email=beta.cmt@dewi.test, password=*** | vendor bisa login (role cmt_vendor) | HTTP 200 · ok=True | ✅ |
| 4 | O1 Buat PO Maklon | `POST /api/production-pos` | po_number=PO-VP-S2, business_type=maklon, buyer_id=mk-client-demo-1, vendor_id=c2405abb-69 | 201 + business_type=maklon | HTTP 201 · id=light-mode-cards, status=Draft, po_number=PO-VP-S2 | ✅ |
| 5 | O2 Konfirmasi PO (Draft→Confirmed) | `POST /api/production-pos/6c5ec5b0-37ec-48ab-807a-eb955c84bddf/status` | status=Confirmed | 200 status=Confirmed | HTTP 200 · id=light-mode-cards, status=Confirmed, po_number=PO-VP-S2 | ✅ |
| 6 | D1 DA Dispatch Potongan ke CMT | `POST /api/vendor-shipments` | shipment_number=SJ-VP-S2, vendor_id=light-mode-cards, items=[{'po_id': | 201 shipment Sent | HTTP 201 · id=light-mode-cards, status=Sent, po_number=PO-VP-S2, shipment_number=SJ-VP-S2 | ✅ |
| 7 | D2 Tandai Shipment Received | `PUT /api/vendor-shipments/081c858d-d86a-4bd1-8114-676330b7318c` | status=Received | 200 status=Received | HTTP 200 · id=light-mode-cards, status=Received, po_number=PO-VP-S2, shipment_number=SJ-VP-S2 | ✅ |
| 8 | V1 Vendor Inspeksi (95 diterima, 5 KURANG) | `POST /api/vendor-material-inspections` | shipment_id=light-mode-cards, items=[{'shipment_item_id': 'dbda6fd9-7e | 201 received 95 missing 5 | HTTP 201 · id=light-mode-cards, status=Submitted, shipment_number=SJ-VP-S2 | ✅ |
| 9 | V2 Vendor Buat Job (available=95 ikut inspeksi) | `POST /api/production-jobs` | vendor_shipment_id=light-mode-cards | 201 available_qty=95 | HTTP 201 · available_qty=95 | ✅ |
| 10 | V3 Vendor Progress 95 | `POST /api/production-progress` | job_item_id=light-mode-cards, completed_quantity=95 | 201 | HTTP 201 · id=light-mode-cards | ✅ |
| 11 | V4 Vendor Deklarasi Setoran 95 | `POST /api/buyer-shipments` | po_id=light-mode-cards, job_id=light-mode-cards, r | 201 receiver_type=da | HTTP 201 · id=light-mode-cards, po_number=PO-VP-S2, shipment_number=SJ-CMT-DA-202607-0006 | ✅ |
| 12 | V5 Vendor Lapor Variance UNDER (5) | `POST /api/production-variances` | job_id=light-mode-cards, variance_type=UNDERPRODUCTION, reason=Bahan k | 201 variance tercatat | HTTP 201 · id=light-mode-cards, status=Reported, po_number=PO-VP-S2 | ✅ |
| 13 | A1 DA Temukan Receipt | `GET /api/prod/cmt-receipts` |  | auto receipt Draft | HTTP 200 · id=light-mode-cards, status=Draft, po_number=PO-VP-S2, total_actual=0, total_rejected=0 | ✅ |
| 14 | A2 DA Isi Aktual (88 lolos, 7 REJECT) | `PUT .../lines/a257d881-4efe-435e-9355-df5ca9b39d88` | qty_actual=88, reject_qty=7 | 200 | HTTP 200 · id=light-mode-cards | ✅ |
| 15 | A3 DA Approve (reject tercatat) | `POST .../approve` |  | 200 Approved total_rejected=7 | HTTP 200 · id=light-mode-cards, status=Approved, po_number=PO-VP-S2, total_actual=88, total_rejected=7 | ✅ |
| 16 | X1 QC: total_actual=88 total_rejected=7 | `GET /api/prod/cmt-receipts/c93a06de-463d-4cdf-b980-77b8caecc958` |  | actual 88 reject 7 | HTTP 200 · total_actual=88, total_rejected=7 | ✅ |

## SKENARIO 3 — Validasi & Keamanan (uji negatif/edge)
_Uji proteksi: progress melebihi kuota ditolak, RBAC (vendor/klien tak boleh tulis PO), buyer-shipment wajib source_receipt_ids, scope antar-vendor, dan deteksi seri dobel (cek-seri). **Expected: semua proteksi bekerja.**_

**18/18 langkah PASS.**

| # | Langkah | Aksi (endpoint) | Input inti | Expected | Output nyata | Status |
|---|---------|-----------------|------------|----------|--------------|:---:|
| 1 | M1 Buat Vendor Partner (master) | `POST /api/vendor-portal/partners` | name=CMT Gamma Sentosa, code=CMT-GAM, contact_name=PIC CMT-GAM, contact_phone=0812-0000-00 | 201/200 + partner tersimpan | HTTP 200 · id=light-mode-cards | ✅ |
| 2 | M2 Buat Akun Login Vendor (master) | `POST /api/vendor-portal/accounts` | email=gamma.cmt@dewi.test, name=CMT Gamma Sentosa (User), password=***, partner_id=1ba6345 | 201/200 + akun cmt_vendor terhubung partner | HTTP 200 · id=light-mode-cards | ✅ |
| 3 | M3 Login Portal Vendor | `POST /api/auth/login` | email=gamma.cmt@dewi.test, password=*** | vendor bisa login (role cmt_vendor) | HTTP 200 · ok=True | ✅ |
| 4 | O1 Buat PO Maklon | `POST /api/production-pos` | po_number=PO-VP-S3, business_type=maklon, buyer_id=mk-client-demo-1, vendor_id=1ba63456-7a | 201 + business_type=maklon | HTTP 201 · id=light-mode-cards, status=Draft, po_number=PO-VP-S3 | ✅ |
| 5 | O2 Konfirmasi PO (Draft→Confirmed) | `POST /api/production-pos/607e519d-e13a-4870-ab34-b953bada4570/status` | status=Confirmed | 200 status=Confirmed | HTTP 200 · id=light-mode-cards, status=Confirmed, po_number=PO-VP-S3 | ✅ |
| 6 | D1 DA Dispatch Potongan ke CMT | `POST /api/vendor-shipments` | shipment_number=SJ-VP-S3, vendor_id=light-mode-cards, items=[{'po_id': | 201 shipment Sent | HTTP 201 · id=light-mode-cards, status=Sent, po_number=PO-VP-S3, shipment_number=SJ-VP-S3 | ✅ |
| 7 | D2 Tandai Shipment Received | `PUT /api/vendor-shipments/2194b2fb-5057-4db4-ab61-adb9d7de5447` | status=Received | 200 status=Received | HTTP 200 · id=light-mode-cards, status=Received, po_number=PO-VP-S3, shipment_number=SJ-VP-S3 | ✅ |
| 8 | C1 Progress 51 > tersedia 50 → DITOLAK | `POST /api/production-progress` | job_item_id=light-mode-cards, completed_quantity=51 | 400 ditolak | HTTP 400 · status=400, detail=Total produksi (51 pcs) melebihi material tersedia (50 pcs). | ✅ |
| 9 | C2 Progress 50 (pas) → OK | `POST /api/production-progress` | job_item_id=light-mode-cards, completed_quantity=50 | 201 | HTTP 201 · id=light-mode-cards | ✅ |
| 10 | C3 Vendor buat PO → DITOLAK (RBAC) | `POST /api/production-pos` | po_number=X-HACK | 403 | HTTP 403 · status=403, detail=Forbidden | ✅ |
| 11 | C4 Vendor hapus PO → DITOLAK (RBAC) | `DELETE /api/production-pos/607e519d-e13a-4870-ab34-b953bada4570` |  | 403 | HTTP 403 · status=403, detail=Forbidden | ✅ |
| 12 | C5 Klien akses /production-pos → DITOLAK | `GET /api/production-pos` |  | 403 | HTTP 403 · status=403, detail=Akses klien maklon hanya melalui endpoint tracking (/api/maklon-client/*) | ✅ |
| 13 | C6 DA kirim buyer tanpa source_receipt_ids → DITOLAK | `POST /api/buyer-shipments` | receiver_type=buyer, source_receipt_ids=MISSING | 400 wajib source_receipt_ids | HTTP 400 · status=400, detail=Buyer shipment dari DA wajib source_receipt_ids[] (mengacu ke cmt_receipts status Approved). Phase B enforcement. | ✅ |
| 14 | C7 Vendor Gamma hanya lihat job sendiri (scope) | `GET /api/production-jobs` |  | semua job vendor_id=light-mode-cards | HTTP 200 · count=1, all_own=True | ✅ |
| 15 | O1 Buat PO Maklon | `POST /api/production-pos` | po_number=PO-VP-S3B, business_type=maklon, buyer_id=mk-client-demo-1, vendor_id=1ba63456-7 | 201 + business_type=maklon | HTTP 201 · id=light-mode-cards, status=Draft, po_number=PO-VP-S3B | ✅ |
| 16 | O2 Konfirmasi PO (Draft→Confirmed) | `POST /api/production-pos/35845562-8234-4b12-b208-f39b6e876559/status` | status=Confirmed | 200 status=Confirmed | HTTP 200 · id=light-mode-cards, status=Confirmed, po_number=PO-VP-S3B | ✅ |
| 17 | C8 Cek-Seri deteksi SN-VP-S3-A dobel | `GET /api/dewi/cmt-intake/cek-seri?scope=maklon` |  | terdeteksi dobel | HTTP 200 · duplicate_count=1, found_SN-VP-S3-A=True | ✅ |
| 18 | C9 Serial-lookup SN-VP-S3-A exists=true | `GET /api/dewi/cmt-intake/serial-lookup` | serial=SN-VP-S3-A | exists=true (≥2 pakai) | HTTP 200 · exists=True, usages=2 | ✅ |

## Verifikasi UI Portal Vendor (testing_agent, iteration_145)
Login portal vendor di route terpisah **`/vendor-cmt`** (`cmtvendor@dewiaditya.id`):
- ✅ **11/11 modul render tanpa error** dengan data milik vendor: Dashboard, Penerimaan Material, Inspeksi Material, Permintaan Material, Pekerjaan Produksi, Progress Produksi, Pengiriman/Setoran, Serial Tracking, Variance, Reminder, Panduan Produksi.
- ✅ Form lapor progress tampil; dashboard menampilkan `activeJobs=2, totalProduced=245, progressPct=84%`.
- ✅ Portal admin — Monitoring CMT 7 tab OK (Dashboard Owner, Kejar CMT, Potongan Masuk, Cek Seri, Rekap Aksesoris, Kapasitas CMT, Rekonsiliasi).
- ✅ RBAC: klien akses `/api/production-pos` → 403 (ditolak). Data vendor ter-scope (hanya milik sendiri).

## Kesimpulan
Portal vendor CMT **terverifikasi end-to-end** dari set master data sampai complete, untuk 3 skenario (happy path, reject/variance, validasi/keamanan). Semua langkah backend **51/51 PASS**, seluruh modul UI vendor berfungsi. Tidak ada data mock; semua objek DB nyata & dibersihkan otomatis setelah tes.
