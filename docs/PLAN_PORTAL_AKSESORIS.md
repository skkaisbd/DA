# Plan — Portal Aksesoris (Dedicated)

> Pemisahan domain Aksesoris dari Portal Gudang ke portal independen.
> Permintaan user: *"Aksesoris memiliki flow yang berbeda dengan divisinya sendiri maka saya memutuskan untuk membuat portal aksesoris."*

---

## 1) Latar Belakang & Alasan

Saat ini menu aksesoris bercampur dengan Portal Gudang:
- `wh-accessory-ops` (Master & Stok Aksesoris — modul `AccessoryModule.jsx`)
- `warehouse-accessory-requests` (Inbox Request — `AccessoryRequestInbox.jsx`)

Faktanya divisi aksesoris memiliki:
- **Flow distinct**: peminjaman (loan), opname terpisah, purchase request mandiri, request internal lintas divisi.
- **PIC khusus** (`admin_aksesoris`) yang tidak menangani inventori kain/FG.
- **Backend SSOT terpisah** di prefix `/api/acc/*` (items, stock, requests, loans, opname, purchase, dashboard).

Karena itu sebaiknya jadi **portal sendiri** seperti Maklon/Marketing/RnD.

---

## 2) State Saat Ini (apa yang sudah ada)

### Backend (READY — tidak perlu API baru untuk MVP)
File: `/app/backend/routes/dewi_accessories_full.py` (prefix `/api/acc`) sudah include sub-router:
- `dewi_accessories_items` — CRUD master aksesoris
- `dewi_accessories_stock` — pergerakan stok (in/out)
- `dewi_accessories_requests` — request internal antar divisi
- `dewi_accessories_loans` — peminjaman
- `dewi_accessories_opname` — stok opname
- `dewi_accessories_purchase` — purchase request
- `dewi_accessories_dashboard` — KPI/aggregate untuk dashboard

Koleksi MongoDB: `dewi_accessories_stock`, `dewi_accessory_requests`, `accessory_shipments`, `accessory_inspections`, `accessory_defects`, dst.

### Frontend (PARTIALLY DONE)
- ✅ `AccessoryModule.jsx` (1138 LOC) — sudah punya tab: Master, Request Internal, Stok Opname, Peminjaman, Purchase Request.
- ✅ `AccessoryRequestInbox.jsx` (525 LOC) — approval inbox.
- ⚠️ `portalNav.js` — section `accessories` sudah didefinisi tapi:
  - Icon `Plus`, `Edit2`, `DollarSign` **tidak di-import** → **build error**.
  - 20 menu items, mayoritas belum ada komponennya.
- ❌ `PortalSelector.jsx` — belum ada card `accessories`.
- ❌ `moduleRegistry.js` — belum ada wiring untuk 18 module ID baru (`accessories-dashboard`, `accessories-my-requests`, dst).
- ❌ `AccessoriesDashboard.jsx` — belum ada.

---

## 3) Pendekatan: MVP-First (Option A — Rekomendasi)

Daripada bikin 20 modul baru dari nol, kita **MAP** module ID baru → modul yang sudah ada,
dengan parameter `defaultTab` untuk menampilkan tab yang sesuai.

### Sidebar Portal Aksesoris (versi MVP — 8 menu, bukan 20)

```
PORTAL AKSESORIS
├── 📊 DASHBOARD
│   └── Dashboard Aksesoris        → AccessoriesDashboard (BARU)
│
├── 📦 INVENTORI
│   ├── Master & Stok Aksesoris    → AccessoryModule (tab: master)
│   └── Stok Opname                 → AccessoryModule (tab: opname)
│
├── 🔄 REQUEST & PEMINJAMAN
│   ├── Request Internal            → AccessoryModule (tab: request)
│   ├── Inbox Approval Request      → AccessoryRequestInbox
│   └── Peminjaman                  → AccessoryModule (tab: peminjaman)
│
├── 🛒 PENGADAAN
│   └── Purchase Request            → AccessoryModule (tab: purchase)
│
└── 📈 LAPORAN
    └── Laporan Aksesoris           → AccessoriesReports (BARU, simple)
```

Total komponen **baru** yang perlu dibuat: **2** (`AccessoriesDashboard` + `AccessoriesReports`).
Sisanya **reuse** modul existing.

---

## 4) Implementasi Detail (Fase 1 — MVP)

### 4.1 Fix Build Error (URGENT, harus dulu)
**File:** `/app/frontend/src/components/erp/portal-shell/portalNav.js`

Icon yang **dipakai tapi belum di-import**:
- `Plus` (lucide-react)
- `Edit2` (lucide-react)
- `DollarSign` (lucide-react)

**Aksi:** Tambah ke baris import lucide-react.
**ATAU:** Karena MVP layout-nya beda, kita rewrite section `accessories` di `portalNav.js` dengan icon yang sudah ada.

### 4.2 Rewrite Section `accessories` di `portalNav.js`
Ganti section yang ada dengan layout MVP 8-menu (lihat 3 di atas).
Gunakan **hanya icon yang sudah di-import**:
- `LayoutDashboard`, `Package`, `Boxes`, `ClipboardCheck`, `Inbox`, `RotateCcw`, `ShoppingCart`, `BarChart3`

### 4.3 Tambah Card di `PortalSelector.jsx`
**Posisi:** Setelah Portal Gudang (logis: gudang → aksesoris).

```jsx
{
  id: 'accessories',
  name: 'Portal Aksesoris',
  description: 'Manajemen master & stok aksesoris, peminjaman, request internal, opname, dan purchase request divisi aksesoris.',
  icon: Sparkles,           // sudah di-import
  accent: 'rnd',            // pakai accent purple (atau buat 'accessories': pink/teal)
  roles: ['admin', 'owner', 'admin_aksesoris', 'admin_gudang', 'spv_aksesoris'],
}
```

**Akses fallback:** Selama transisi, biarkan `admin_gudang` juga punya akses agar tidak terputus.

### 4.4 Update `moduleRegistry.js`

Gunakan helper `makeModuleWithTab` (sudah ada di file) untuk mapping tab default.

```js
const AccessoriesDashboard = lazy(() => import('./AccessoriesDashboard'));
const AccessoriesReports   = lazy(() => import('./AccessoriesReports'));

const MODULES = {
  // ... existing
  'accessories-dashboard':        AccessoriesDashboard,
  'accessories-master-stock':     makeModuleWithTab(AccessoryModule, 'master'),
  'accessories-opname':           makeModuleWithTab(AccessoryModule, 'opname'),
  'accessories-internal-request': makeModuleWithTab(AccessoryModule, 'request'),
  'accessories-inbox':            AccessoryRequestInbox,   // sama dengan warehouse-accessory-requests
  'accessories-loans':            makeModuleWithTab(AccessoryModule, 'peminjaman'),
  'accessories-purchase':         makeModuleWithTab(AccessoryModule, 'purchase'),
  'accessories-reports':          AccessoriesReports,
};
```

**Catatan:** `AccessoryModule` perlu menerima props `defaultTab` (cek apakah sudah; kalau belum, tambahkan).

### 4.5 Buat `AccessoriesDashboard.jsx` (BARU)

**Lokasi:** `/app/frontend/src/components/erp/AccessoriesDashboard.jsx`

**Konten (referensi pattern `FinanceDashboard.jsx`):**
- 4 KPI cards (use shadcn Card):
  - Total Item Aksesoris (count)
  - Item Low-Stock (count, link → master tab dengan filter low-stock)
  - Pending Request (count, link → inbox)
  - Peminjaman Aktif (count, link → loans)
- 2 panel:
  - **Quick View: 10 Item Low-Stock Terbaru** — table mini
  - **Quick View: 5 Request Menunggu Approval** — list mini
- Endpoint: `GET /api/acc/dashboard/summary` (sudah ada di `dewi_accessories_dashboard.py`)
  - Kalau response shape belum sesuai, kita panggil endpoint individual: `/api/acc/items?lowStockOnly=true`, `/api/acc/requests?status=pending`, dll.

**Komponen UI:**
- Pakai `<EmptyState />` untuk state kosong.
- Pakai `<Skeleton />` untuk loading.
- Test ID: `data-testid="accessories-dashboard"` dan turunannya.

**Ukuran target:** ≤300 LOC.

### 4.6 Buat `AccessoriesReports.jsx` (BARU, ringkas)

**Lokasi:** `/app/frontend/src/components/erp/AccessoriesReports.jsx`

**Konten MVP (cukup sederhana):**
- 3 tab: **Pemakaian**, **Stock Level**, **Biaya**
- Tiap tab: filter periode (date range) + table sederhana + tombol Export CSV.
- Endpoint: `GET /api/acc/reports/usage`, `GET /api/acc/reports/stock-level`, `GET /api/acc/reports/cost`
  - **Verifikasi endpoint dulu**. Kalau belum ada, tampilkan placeholder `<EmptyState title="Laporan Coming Soon" />`.

**Ukuran target:** ≤250 LOC.

### 4.7 (Opsional) Hapus/Sembunyikan Aksesoris di Portal Gudang

Berdasarkan pilihan user (C vs D):
- **Opsi C (Full Separation):** Hapus `wh-accessory-ops` dan `warehouse-accessory-requests` dari section `OPERASIONAL GUDANG` di `portalNav.js`.
- **Opsi D (Cross-Link):** Biarkan dengan badge `→ Portal Aksesoris` di label.

**Default rekomendasi:** Opsi D (cross-link) untuk masa transisi 1–2 minggu, lalu Opsi C.

---

## 5) Acceptance Criteria (DoD)

- [ ] `yarn build` (atau `esbuild`) **lulus tanpa error** — Portal Aksesoris boleh dibuka tanpa error import.
- [ ] User dengan role `admin_aksesoris` (atau `admin`) login → muncul card **Portal Aksesoris** di selector.
- [ ] Klik card → masuk ke Portal Aksesoris, default land di `accessories-dashboard`.
- [ ] Dashboard menampilkan 4 KPI + 2 quick view tanpa error (boleh empty state kalau data kosong).
- [ ] Sidebar Portal Aksesoris bisa navigasi ke 8 menu, semua **tidak crash**.
- [ ] Klik **Master & Stok** → modul `AccessoryModule` terbuka di tab `master`.
- [ ] Klik **Inbox Approval** → modul `AccessoryRequestInbox` terbuka.
- [ ] Cross-portal: `wh-accessory-ops` di Portal Gudang **tetap berfungsi** kalau masih ada (no regression).
- [ ] Testing agent (FE + BE) lulus.

---

## 6) Risiko & Mitigasi

| Risiko | Mitigasi |
|--------|----------|
| `AccessoryModule` belum support `defaultTab` prop | Cek source; kalau belum, patch ringan (5 baris) di komponen utama. |
| Endpoint `/api/acc/dashboard/summary` belum ada | Fallback ke endpoint individual atau hard-coded "Coming Soon" untuk MVP. |
| Role `admin_aksesoris` belum terdaftar di DB | Tambah ke seed/data dummy, atau gunakan `admin_gudang` sebagai bridging. |
| User existing dengan link langsung ke `wh-accessory-ops` rusak | Tetap pertahankan module ID di `moduleRegistry.js` (backward compat). |
| Dashboard endpoint lambat | Lazy fetch + skeleton loader. |

---

## 7) Estimasi Waktu

| Task | Estimasi |
|------|----------|
| Fix icon import + rewrite portalNav section | 10 menit |
| Tambah card di PortalSelector | 10 menit |
| Update moduleRegistry + verify defaultTab prop di AccessoryModule | 20 menit |
| Buat AccessoriesDashboard | 45 menit |
| Buat AccessoriesReports (MVP) | 25 menit |
| Smoke test lokal (screenshot tool) | 20 menit |
| Testing agent (FE + BE) | 30 menit |
| Bugfix dari testing | 20–40 menit |
| **Total estimasi** | **~3 jam** |

---

## 8) Out-of-Scope (Fase Lanjutan — TIDAK di MVP)

Menu-menu di sidebar versi previous agent yang **TIDAK** di-include di MVP:
- `accessories-my-requests` (request saya per user)
- `accessories-create-request` (form khusus, sekarang via tab Request)
- `accessories-stock-movement` (sudah masuk Master & Stok tab)
- `accessories-adjustment` (stock adjustment terpisah — bisa di-add later)
- `accessories-borrowing-active` / `accessories-borrowing-history` (sudah dalam tab Peminjaman)
- `accessories-suppliers` (supplier khusus aksesoris — kalau dibutuhkan)
- `accessories-price-list` (katalog harga)
- `accessories-cost-analysis`
- `accessories-alerts` (low-stock alert dedicated module)
- `accessories-categories`, `accessories-units`, `accessories-settings` (master data)

Semua ini bisa ditambahkan di **Fase 2 Portal Aksesoris Enhancement** setelah MVP stabil dan user setuju arahnya.
