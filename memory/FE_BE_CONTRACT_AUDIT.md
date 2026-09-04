# 🔌 FE↔BE CONTRACT AUDIT — Discovery Report (READ-ONLY)

> Mode: **DISCOVERY / verifikasi saja** (tidak ada perbaikan). Analisis statik best-effort.

> Backend routes terindeks: **2268** · Frontend API call-site unik: **699**


---

## ⭐ RINGKASAN TEMUAN TERVERIFIKASI (manual + runtime probe)

> Status: **DISCOVERY** — dicatat, **belum diperbaiki** (sesuai instruksi user).

| ID | Modul (file) | Masalah | Bukti | Dampak | Status |
|---|---|---|---|---|---|
| **BUG-FE-AUTH-1** | `AdminSetupPanelModule.jsx`, `MarketingARBridgeModule.jsx` | `credentials:'include'` tanpa Bearer → 401 | curl 401→200; browser | Panel admin/AR-bridge rusak | ✅ **SUDAH DIPERBAIKI** (sesi ini) |
| **F1 (BUG-FE-CONTRACT-1)** | `PurchaseDiscountModule.jsx:21,61` | Path salah: `/api/rahaza/**finance**/ap-invoices[/{id}/payment]` — backend sebenarnya `/api/rahaza/ap-invoices` (tanpa `/finance`) | probe **404**; backend `rahaza_finance.py` prefix `/api/rahaza`, route `/ap-invoices/*` | Modul Purchase Discount (fetch AP + bayar) **gagal 404** | ✅ **DIPERBAIKI** (2026-07-06) — hapus segmen `/finance` di 2 fetch; verifikasi testing_agent iter_61 (GET `/api/rahaza/ap-invoices?status=sent`→200, path lama→404) |
| **F2 (BUG-FE-CONTRACT-2)** | `BadDebtWriteOffModule.jsx:29,50` | Path salah: `/api/rahaza/**finance**/ar-invoices/{overdue-report, write-off-bad-debt}` — sebenarnya `/api/rahaza/ar-invoices/*` | probe **404**; backend route `/ar-invoices/overdue-report` & `/ar-invoices/{id}/write-off-bad-debt` prefix `/api/rahaza` | Laporan overdue & write-off bad-debt **gagal 404** | ✅ **DIPERBAIKI** (2026-07-06) — hapus segmen `/finance` di 2 fetch; verifikasi testing_agent iter_61 (overdue-report→200, path lama→404) |
| **F3 (BUG-FE-CONTRACT-3)** | `ApprovalModule.jsx:41,69,101` | Endpoint `/api/invoice-edit-requests[/{id}/approve\|reject]` **tidak terdaftar** di backend (hanya disebut di komentar `server.py` — router lama dihapus di Session #11.16 Phase D) | grep backend = kosong; probe **404** | Modul Approval (invoice edit request) **gagal 404** | ✅ **DIPERBAIKI** (2026-07-06) — implementasi router BARU `routes/invoice_edit_requests.py` (GET/POST + PUT approve/reject; approve menerapkan after_snapshot ke invoice target + audit `invoice_change_history`; approve/reject butuh role admin). Registered di server.py. Verifikasi testing_agent iter_61 (create→approve→edge 400/404 semua benar) |
| **F4 (BUG-BE-500-1)** | BE `rahaza_inventory_stock.py` `GET /api/rahaza/material-stock` | Mengembalikan **HTTP 500** ("Internal server error") pada GET — akar: `s["material_id"]`/`s["location_id"]` tanpa `.get()` (KeyError) + perbandingan `current_qty < min_stock_qty` bila nilai string (TypeError) | curl (dgn auth) → 500 | Dipakai `RahazaStockModule`, `InventoryScrapModule`, `RahazaFGInventoryModule`, `MaklonMaterialIssuePanel` | ✅ **DIPERBAIKI** (2026-07-06) — helper `_num()` (koersi float aman + guard NaN/inf) + `.get()` untuk material_id/location_id. Diuji dgn menyuntik doc malformed (min_stock string, qty string, key hilang) → tetap **200**, testing_agent iter_61 semua kombinasi param → 200 |

**False-positive yang sudah ditriase (BUKAN bug):**
- `/api/rahaza/material-issues/draft-from-wo` → **ADA** (POST); GET-probe men-trigger route `/{mi_id}` → 404 handler-level (artefak probe).
- `/api/comm/messages/{id}/thread` → **ADA** (`communication/threads.py` GET); probe 404 = handler not-found utk id dummy.
- Cluster `/api/assets/*`, `/api/comm/*`, `/api/rahaza/material-*` lain (Bagian B3) → rute terdaftar (405/401/200), hanya gap static-matcher.
- 13 modul "no-auth" (live-host/marketing tabs, adapters, ShopFloorTV) → auth via prop `authH`/`headers`, atau `/api/tv/*` publik by-design.

---



## A. Anti-pattern `credentials: 'include'` (kelas BUG-FE-AUTH-1)

✅ **0 temuan** — anti-pattern sudah bersih (2 bug sebelumnya sudah diperbaiki: `AdminSetupPanelModule.jsx`, `MarketingARBridgeModule.jsx`).


## B. FE memanggil `/api/*` — klasifikasi via runtime GET-probe

> Static-match awal menandai **63** call-site 'unmatched'. Runtime GET-probe mengklasifikasikan ulang: **404**=rute tak terdaftar, **405/401/403/2xx/422**=rute ADA (false-positive matcher).


### B1. ⚠️ KANDIDAT RUTE HILANG (probe 404 di path & prefix) — **9**

| FE path | Normalisasi | GET | File:Line |
|---|---|---:|---|
| `/api/comm/messages/${rootMessage.id}/thread` | `/api/comm/messages/X/thread` | 404 | `components/erp/communication-hub/ThreadPanel.jsx:32` |
| `/api/invoice-edit-requests` | `/api/invoice-edit-requests` | 404 | `components/erp/ApprovalModule.jsx:41` |
| `/api/invoice-edit-requests/${selectedRequest.id}/approve` | `/api/invoice-edit-requests/X/approve` | 404 | `components/erp/ApprovalModule.jsx:69` |
| `/api/invoice-edit-requests/${selectedRequest.id}/reject` | `/api/invoice-edit-requests/X/reject` | 404 | `components/erp/ApprovalModule.jsx:101` |
| `/api/rahaza/finance/ap-invoices` | `/api/rahaza/finance/ap-invoices` | 404 | `components/erp/PurchaseDiscountModule.jsx:21` |
| `/api/rahaza/finance/ap-invoices/${paymentForm.invoice_id}/payment` | `/api/rahaza/finance/ap-invoices/X/payment` | 404 | `components/erp/PurchaseDiscountModule.jsx:61` |
| `/api/rahaza/finance/ar-invoices/${invoice.id}/write-off-bad-debt` | `/api/rahaza/finance/ar-invoices/X/write-off-bad-debt` | 404 | `components/erp/BadDebtWriteOffModule.jsx:50` |
| `/api/rahaza/finance/ar-invoices/overdue-report` | `/api/rahaza/finance/ar-invoices/overdue-report` | 404 | `components/erp/BadDebtWriteOffModule.jsx:29` |
| `/api/rahaza/material-issues/draft-from-wo` | `/api/rahaza/material-issues/draft-from-wo` | 404 | `components/erp/RahazaMaterialIssueModule.jsx:92` |

### B2. 🟡 LEAF-404 / AMBIGU (parent ada, leaf 404 — kemungkinan handler-level not-found) — **11**

| FE path | Normalisasi | prefix status | File:Line |
|---|---|---:|---|
| `/api/assets/categories/${category.id}` | `/api/assets/categories/X` | 200 | `components/erp/asset/dialogs/EditCategoryDialog.jsx:40` |
| `/api/assets/disposal-requests/${req.id}/${action}` | `/api/assets/disposal-requests/X/X` | 200 | `components/erp/asset/sections/DisposalApprovalInbox.jsx:41` |
| `/api/comm/channels/${activeView.id}/members` | `/api/comm/channels/X/members` | 200 | `components/erp/CommunicationHubPortal.jsx:106` |
| `/api/comm/channels/${activeView.id}/messages` | `/api/comm/channels/X/messages` | 200 | `components/erp/CommunicationHubPortal.jsx:124` |
| `/api/comm/channels/${activeView.id}/messages` | `/api/comm/channels/X/messages` | 200 | `components/erp/communication-hub/Composer.jsx:72` |
| `/api/comm/channels/${activeView.id}/pinned` | `/api/comm/channels/X/pinned` | 200 | `components/erp/CommunicationHubPortal.jsx:109` |
| `/api/rahaza/material-issues/${mi.id}` | `/api/rahaza/material-issues/X` | 200 | `components/erp/RahazaMaterialIssueModule.jsx:106` |
| `/api/rahaza/material-stock` | `/api/rahaza/material-stock` | 500 | `components/erp/InventoryScrapModule.jsx:54` |
| `/api/rahaza/material-stock` | `/api/rahaza/material-stock` | 500 | `components/erp/MaklonMaterialIssuePanel.jsx:78` |
| `/api/rahaza/material-stock` | `/api/rahaza/material-stock` | 500 | `components/erp/RahazaFGInventoryModule.jsx:59` |
| `/api/rahaza/material-stock` | `/api/rahaza/material-stock` | 500 | `components/erp/RahazaStockModule.jsx:136` |

### B3. ✅ FALSE-POSITIVE matcher (rute ADA — 405/401/403/2xx) — **43** (ringkas)

> Ini bukan bug: gap normalisasi static-matcher (mis. prefix di-import dari modul shared). Rute terbukti terdaftar via probe.

| Prefix (rute ADA) | jumlah call-site |
|---|---:|
| `/api/assets` | 10 |
| `/api/assets/batch-depreciate` | 1 |
| `/api/assets/categories` | 1 |
| `/api/assets/dashboard` | 1 |
| `/api/assets/disposal-requests` | 1 |
| `/api/assets/expiring-alerts` | 1 |
| `/api/assets/predictive-maintenance/acknowledge` | 1 |
| `/api/assets/predictive-maintenance/alerts` | 1 |
| `/api/assets/reports/utilization` | 1 |
| `/api/comm/channels` | 4 |
| `/api/comm/conversations` | 3 |
| `/api/comm/messages` | 4 |
| `/api/comm/read` | 1 |
| `/api/rahaza/material-adjust` | 2 |
| `/api/rahaza/material-issues` | 6 |
| `/api/rahaza/material-movements` | 2 |
| `/api/rahaza/material-receive` | 1 |
| `/api/rahaza/material-stock/summary` | 1 |
| `/api/rahaza/material-transfer` | 1 |


## Catatan metodologi

- Check A = string-scan pasti (reliable).
- Check B = normalisasi `${...}` → `X` dan `{param}` backend → `[^/]+`, lalu match penuh + fallback prefix-statik. Segmen dinamis kompleks dapat memunculkan false-positive; tiap baris WAJIB ditinjau manual sebelum diperbaiki.
- Endpoint publik by-design (`/api/tv/*`, `/api/metrics`, webhooks) BUKAN bug meski tanpa auth.
