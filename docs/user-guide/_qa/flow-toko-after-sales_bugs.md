# QA — flow-toko-after-sales
### Bukti verifikasi & catatan mutu untuk alur After-Sales/Retur & Refund

> File QA terpisah dari dokumen utama (agar dokumen utama fokus operasional/pelatihan).
> Referensi utama: [`docs/user-guide/toko/flow-toko-after-sales.md`](../toko/flow-toko-after-sales.md).

---

## 1. Ringkasan Verifikasi

| Aspek | Metode | Hasil |
|---|---|---|
| Backend endpoint | `python3 tests/flow_toko_after_sales_test.py` | **PASS 11/11 langkah** |
| Frontend UI redirect | `auto_frontend_testing_agent` iter#68 | **PASS 6/6** (setelah bug-fix StrictMode) |
| Idempotensi jembatan | Ulang panggilan `create-wh-return` | `already_exists=true` — no duplicate |
| Callback sinkron | POST resolve + GET marketing return | `wh_return_status='Resolved'` ter-sinkron |
| Soft-warning complete | POST complete tanpa wh_return | Field `warning` non-null (RC-FLOW-UX-11c opsi B) |
| Restock efek stok | POST resolve action=Restock qty=1 | `rahaza_fg_inventory.total_qty` naik +1 |
| Auto-post GL | POST create-credit-note | JE `Dr Sales Returns / Cr AR` posted |

## 2. Katalog `data-testid` Terpakai
Diambil dari manifest `_manifests/marketing-after-sales.manifest.json` + `_manifests/wh-returns.manifest.json`:

**Hub & tab:**
- `after-sales-hub` (line 205 MarketingAfterSalesHub.jsx)
- `tab-complaints` (line 218)
- `tab-returns` (line 227)
- `tab-resolution-log` (line 236)
- `resolution-log` (line 111)
- `log-item-{type}-{id}` (line 125, dynamic)

**Modul refund:**
- `returns-refunds-module` (line 300 ReturnsRefundsModule.jsx)
- `return-account-select` (line 483)
- `btn-create-wh-return` (line 626) — RC-FLOW-UX-11a
- `btn-open-wh-return` (line 643) — RC-FLOW-UX-11b

**Modul komplain (untuk konteks hub, di luar happy-path retur):**
- `complaints-dashboard`, `complaint-row-{id}`, `btn-complaint-detail-{id}`, `search-complaints`, `note-textarea`

**Active account bar (dipakai lintas tab):**
- `active-account-bar`, `switch-account-btn`, `switch-to-{id}`, `clear-active-account`

**Modul Gudang (WHReturnsModule.jsx) — OnwardCTA:**
- `onward-issue-credit-note` — CTA "Terbitkan Credit Note & Refund"
- `onward-check-stock` — CTA "Cek Stok FG"

## 3. Verifikasi Grounding Endpoint
Semua 8 critical_endpoints (di `flow.json`) diverifikasi eksis di backend routes:

| Endpoint (normalized) | Backend file | Line | Verified |
|---|---|---|---|
| `/api/marketing/returns` | `backend/routes/marketing_returns_routes.py` | 210, 292 | ✅ |
| `/api/marketing/returns/{}/approve` | `backend/routes/marketing_returns_routes.py` | 353 | ✅ |
| `/api/marketing/returns/{}/create-wh-return` | `backend/routes/marketing_returns_routes.py` | 438 | ✅ |
| `/api/wh/returns/{}/receive` | `backend/routes/dewi_wh_returns.py` | ~180 | ✅ |
| `/api/wh/returns/{}/inspect` | `backend/routes/dewi_wh_returns.py` | ~230 | ✅ |
| `/api/wh/returns/{}/resolve` | `backend/routes/dewi_wh_returns.py` | 300 | ✅ |
| `/api/marketing/returns/{}/complete` | `backend/routes/marketing_returns_routes.py` | 396 | ✅ |
| `/api/marketing/returns/{}/create-credit-note` | `backend/routes/marketing_returns_routes.py` | ~560 | ✅ |

Ekstraksi manifest melaporkan 16 endpoint marketing-after-sales & 7 endpoint wh-returns, seluruhnya `verified=true` (unverified=0).

## 4. Catatan Verifikasi Sesi #86

### 4.1 Bug tertangani (mid-loop)
**React 18 StrictMode initializer side-effect** — `useState(activeTab)` awalnya memanggil `sessionStorage.removeItem` di initializer function. StrictMode invoke initializer 2x di dev mode → call ke-2 dapat `null` → default `complaints`. Efek: redirect `#marketing-returns` & `#toko-returns` tampil tab yang salah.

**Fix:** `MarketingAfterSalesHub.jsx` line 178-197. Initializer sekarang PURE (hanya baca). `removeItem` dipindah ke `useEffect(() => {...}, [])`.

Hasil: A2 & A4 redirect PASS di re-test.

### 4.2 Keputusan user diterapkan
- **11a=B** (link manual) — endpoint baru `create-wh-return` + tombol UI. Bukan auto-sync.
- **11c=B** (soft-warning) — field `warning` di response `complete`, banner UI 24-jam. Bukan hard-block.
- **11d=A** (konsolidasi ketat) — 4 pintu legacy → `makeRedirect` ke hub tab. Sidebar Gudang rename "Retur Fisik (Gudang)".
- **11e** (terminologi) — poles diseragamkan: "Refund & Nota Kredit" (Toko), "Retur Fisik & Restock (Gudang)" (Gudang).
- **11f** (log merge) — ResolutionLogTab 3-way merge (complaints + returns + wh_returns Resolved), dedup via wh_return_id set.

## 5. Hasil Eksekusi Terakhir

### 5.1 Backend (`tests/flow_toko_after_sales_test.py`)
```
PASS login (admin@garment.com)
PASS create marketing_return E2E-AFTER-195658 (id=2e28d26b, status=pending)
PASS approve marketing_return -> status=approved
PASS create-wh-return RET-20260708-002 (wh_id=8fc6afdc, status=Pending)
PASS idempotency create-wh-return (no duplicate)
PASS wh_returns receive -> status=Received
PASS wh_returns inspect -> status=Inspected
PASS wh_returns resolve(Restock qty=1) -> status=Resolved
PASS sync marketing_returns.wh_return_status=Resolved (callback berjalan)
PASS complete marketing_return (warning=null karena wh_return_id ada)
PASS create-credit-note CN-20260708-001 (id=e926cdd4)
INFO cleanup best-effort selesai (DB pristine terjaga)

=== FLOW-TOKO-AFTER-SALES ALL PASS ===
```

### 5.2 Frontend UI (auto_frontend_testing_agent iter#68)
```
✅ A1 marketing-complaints → complaints tab active
✅ A2 marketing-returns → returns tab active (after StrictMode fix)
✅ A3 toko-cs → complaints tab active
✅ A4 toko-returns → returns tab active (after StrictMode fix)
✅ E Log Penyelesaian merge: 3 items badge "Retur Fisik" (emerald) visible
✅ F Zero-regression: #marketing-orders renders correctly

RESULT: 6/6 PASS (100%)
```

## 6. Rubrik Mutu — Skor 97/100

| Kriteria | Bobot | Skor | Catatan |
|---|--:|--:|---|
| Akurasi teknis (grounded ke kode) | 30 | 29 | Semua endpoint verified via extract_module; 1 poin dikurangi krn RBAC role belum di-enforce di backend (masih mock via require_auth generik) |
| Kelengkapan happy-path | 25 | 24 | 8 fase tercover; 1 poin dikurangi krn "Reshipment/Appeal/Dispose/Donasi" hanya di-sketch (bukan happy-path utama) |
| Kejelasan langkah & testid | 20 | 20 | 20+ testid didokumentasikan; screenshot flow lengkap |
| Aturan bisnis & kasus tepi | 15 | 14 | 18 test cases; 1 poin dikurangi krn void CN belum ada |
| Bukti uji | 10 | 10 | 11/11 backend + 6/6 UI PASS |
| **Total** | **100** | **97** | Lolos threshold 95 |

---

Selesai — file QA `flow-toko-after-sales_bugs.md` versi Sesi #86.
