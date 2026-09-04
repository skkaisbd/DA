# ANALISIS FLOW MARKETING (Portal "toko") — AS-IS Terverifikasi

> Sesi analisis (read-only). GROUNDED ke kode nyata + diverifikasi LIVE via API + silang dengan
> `memory/PRODUKSI_E5_MARKETING.md` dan `docs/user-guide/marketing/flow-marketing-kol.md`.
> Tanggal review: sesi ini. Tanpa rebuild UI, tanpa implementasi.

---

## 0. TL;DR
- Portal Marketing (key `toko`) = **etalase + penampung DEMAND + fulfillment FG + after-sales + engagement**.
- **Peran inti**: (1) kelola akun toko/marketplace, (2) kelola katalog & harga jual, (3) tampung order
  dari marketplace/live/manual, (4) penuhi order dari **stok FG** (fulfillment) → potong stok + posting COGS,
  (5) akui pendapatan via **AR batch invoice** dari sales-data, (6) after-sales (komplain/retur/ulasan),
  (7) konten/kampanye/KOL/live, (8) target & laporan & AI.
- **Maklon TIDAK lewat marketing** (produk milik klien; katalog terpisah `dewi_maklon_buyer_catalog`).
- 2 "jembatan" ke portal lain: **Fulfillment → Gudang+Finance (COGS)** dan **Sales-data → Finance (AR)**.
- **Temuan penting**: (a) DEMAND online **tidak** auto-jadi PO Produksi (manual); (b) fulfillment dispatch
  **tidak** membuat Surat Jalan (SJ-ONLINE) walau tipe SJ-nya ada; (c) katalog kopel LONGGAR ke master
  (by SKU, bukan FK); (d) **banyak koleksi demand paralel** (marketing_orders / dewi_toko_orders /
  rahaza_orders / marketing_sales_data); (e) master data (akun/katalog/KOL/target) saat ini **kosong**
  di DB, sedangkan transaksi (order/live/konten/ulasan/retur/komplain) ada.

---

## 1. PETA PORTAL MARKETING (menu → modul → API) — dari `portalNav.js` (toko)

### Seksi 1 — PENJUALAN MULTI-CHANNEL
| Menu (id) | Modul FE | API utama | Fungsi |
|---|---|---|---|
| `marketing-accounts` (Kelola Akun) | (accounts) | `/api/marketing/accounts` (`marketing_accounts.py`) | Buat akun toko per platform (shopee/tiktokshop/tokopedia) → `marketing_platform_accounts` |
| `marketing-sales` (Input Sales) | — | `/api/marketing/sales-data` (`marketing_sales.py`) | Rekap penjualan → `marketing_sales_data` |
| `marketing-import` (Impor Data) | — | `/api/marketing/import/*` (`marketing_import.py`) | Upload → AI mapping (Emergent LLM) → preview → commit ke `marketing_sales_data` |
| `marketing-orders` (Order Terpadu) | UnifiedOrders | `/api/marketing/orders/*` (`marketing_orders_routes.py`) | Dashboard order gabungan → `marketing_orders` |
| `marketing-catalog` (Manajemen Katalog) | CatalogManagementModule | `/api/marketing/catalogs/*` (`marketing_catalog_*`) | Katalog & item (harga jual) per akun |
| `marketing-ar-bridge` (Buat Invoice) | MarketingARBridgeModule | `/api/marketing/sales-data/generate-ar-batch` | Rakit AR invoice dari sales-data → `rahaza_ar_invoices` (Finance) |

### Seksi 2 — KONTEN, KAMPANYE & KREATOR
| Menu | API | Status-machine |
|---|---|---|
| `marketing-content-calendar` (Kalender Konten) | `/api/marketing/content-calendar` | `draft → scheduled → posted` |
| `marketing-discounts` (Kampanye Diskon) | `/api/marketing/discounts` | promo/diskon per akun/produk |
| `marketing-product-launches` (Peluncuran Produk) | `/api/marketing/product-launches` | `planning → ready → launched` (+auto-create FG di `rahaza_materials`) |
| `marketing-kol-hub` (KOL & Kreator) — HUB | `/api/marketing` (kol) + `/kol-leaderboard` | creator CRUD, request, session, leaderboard, portal kreator |

### Seksi 3 — ANALITIK, LIVE & AI
| Menu | API |
|---|---|
| `marketing-reports` (Laporan) | `/api/marketing/reports` |
| `marketing-health` (Kesehatan Akun) | `/api/marketing/health` |
| `marketing-targets` (Target Bulanan) | `/api/marketing/targets` (`marketing_targets.py`) |
| `marketing-live-hub` (Live Selling) — HUB | `/api/marketing/live`, `/live/analytics`, `/livehost/*` (sessions + analytics + livehost) |
| `marketing-ai-hub` (AI Marketing) — HUB | `/ai-insights`, `/advanced-ai`, `/ai-content` (insights + advanced + content + image) |
| `marketing-scheduler` (Penjadwal Otomasi) | (scheduler UI; APScheduler backend: auto-create tasks, alerts, cleanup) |

### Seksi 4 — AFTER-SALES & PENGATURAN
| Menu | API | Catatan |
|---|---|---|
| `marketing-after-sales` (Komplain & Retur) — HUB | `/complaints`, `/returns` | **Konsolidasi 5 pintu** → 1 hub (complaints+returns+resolution log). `marketing-complaints`, `marketing-returns`, `toko-cs`, `toko-returns` semua redirect ke sini. |
| `marketing-reviews` (Rating & Ulasan) | `/api/marketing/reviews` | `pending → reviewed` |
| `marketing-samples` (Kirim Sample) | `/api/marketing/samples` | pengiriman sample produk |
| `marketing-task-hub` (Manajemen Tugas) — HUB | `/tasks`, `/task-templates` | Kanban + Approval + Templates |
| `marketing-integration-settings` (Integrasi API) | `/integration-settings` | kredensial/konfig marketplace |
| `marketing-webhooks` (Monitor Webhook) | `/webhooks/*` | monitor event masuk marketplace |
| `maklon-notifications` (Notifikasi) | (notifikasi) | dipinjam dari maklon |

> **Sudah dikonsolidasikan**: after-sales (5→1), live (sessions/analytics/livehost→1 hub), AI (4→1 hub),
> tugas (→1 hub). Ini bukti portal marketing sudah melewati de-duplikasi menu signifikan.

---

## 2. FLOW INTI — ORDER-TO-CASH (diverifikasi live)

```
                 ┌──────────── SUMBER DEMAND ────────────┐
 Webhook MP ───► marketing_webhook_events ──(_maybe_create_order, idempoten)──┐
 Universal Import (shopee/tiktok/tokopedia_orders) ───────────────────────────┤
 Manual POST /orders ─────────────────────────────────────────────────────────┤
                                                                               ▼
                                                                    ┌──── marketing_orders (60 live) ────┐
                                                                    │ status: new→packed→shipped→delivered│
                                                                    │        └→ cancelled / returned      │
                                                                    └───────────────┬────────────────────┘
                                                        status "packed" memicu fulfillment
                                                                                    ▼
        ┌──────────────── FULFILLMENT (/api/fulfillment) — jembatan Gudang+Finance ───────────────┐
        │ pending_fulfillment → allocate(FG dari rahaza_material_stock cv_da/fg_internal;          │
        │ available-=qty, reserved+=qty) → picking → packed_ready → DISPATCH                        │
        │ DISPATCH: kurangi stok FG + post_cogs_shipment (Dr COGS / Cr FG, pakai HPP) → GL Finance  │
        └───────────────────────────────────────────────────────────────────────────────────────┘

  PENDAPATAN (paralel, bukan dari order fisik):
    marketing_sales_data ──(generate-ar-batch: daily/weekly/monthly/platform)──► rahaza_ar_invoices
                                                                                  └► post_ar_invoice → GL
```

**Status order** (`marketing_orders_routes.py:35-43`): `new → packed → shipped → delivered`,
cabang `cancelled` (dari new/packed) & `returned` (dari shipped/delivered).
**Status fulfillment** (`fulfillment.py:62`): `pending_fulfillment → allocated → picking → packed_ready → dispatched → delivered`.

**Verifikasi live:** `/orders/summary` = 60 order, revenue Rp 9.332.000 (returned 3 / shipped 15 /
delivered 26 / cancelled …). `/fulfillment/summary` = pending 6 / allocated 3 / picking 3 /
packed_ready 1 / dispatched_today 3. → **WIRED, bukan mock.**

---

## 3. SUMBER DEMAND — KOLEKSI PARALEL (dimensi OVERLAP)
| Koleksi | Asal | Live count | Peran |
|---|---|---|---|
| `marketing_orders` | webhook + universal import + manual | **60** | order marketplace/KOL/live → fulfillment |
| `dewi_toko_orders` | toko online (`_toko_adapter.py`, `dewi_online_orders.py`) | 0 | order online shop DA sendiri |
| `rahaza_orders` | penjualan internal/langsung | 0 | order internal → bisa buat PO produksi (`production_po.py:539`) |
| `marketing_sales_data` | import/manual sales | 0 | agregat harian → AR batch invoice |

> **Overlap nyata**: 3 koleksi "order" + 1 "sales agregat" hidup berdampingan. Risiko double-count
> pendapatan bila sales-data (AR) & order-fulfillment (COGS) dipakai untuk transaksi yang sama.
> (Ini bukan bug fatal — beda tujuan: AR=pengakuan pendapatan agregat, fulfillment=inventori/COGS —
> tapi butuh kebijakan agar tidak tumpang tindih.)

---

## 4. FLOW PENDUKUNG (ringkas, grounded)
- **Konten → Campaign → Review → Komplain** (flow terdokumentasi `flow-marketing-kol.md`):
  Kalender Konten (`draft→scheduled→posted`) → Peluncuran Produk (`planning→ready→launched`,
  auto-create FG `rahaza_materials`) → Rating/Ulasan (`pending→reviewed`) → Komplain
  (`open→in_progress→resolved`, SLA 48 jam).
- **KOL/Kreator**: admin CRUD creator → request kolaborasi → session → leaderboard + portal kreator
  (login terpisah `login_email`/`Creator@123`).
- **Live Selling**: sesi live (`marketing_live_sessions`, 18 live) + host (`marketing_livehosts`) +
  shift + script + training + analytics.
- **After-Sales**: Komplain (`marketing_complaints`, 40) + Retur/Refund (`marketing_returns`, 30) →
  **jembatan ke Gudang** `wh_returns` (RC-FLOW-UX-11, sesi #26) untuk retur fisik + koreksi stok.
- **Target & Kinerja**: `marketing_targets` (target bulanan per akun/platform) vs actual → performance & health.
- **AI**: insights, advanced-ai, content-tools (pakai Emergent LLM key).
- **Webhooks/Integrasi**: Shopee/TikTok/Tokopedia (idempoten, status map) + integration-settings.

---

## 5. INTEGRASI LINTAS-PORTAL (jembatan yang SUDAH ada)
| Edge | Mekanisme | File |
|---|---|---|
| Marketing → Gudang | order packed → fulfillment queue; allocate FG dari `rahaza_material_stock` | `fulfillment.py` |
| Marketing → Finance (COGS) | dispatch → `post_cogs_shipment` (Dr COGS/Cr FG) | `fulfillment.py` + `rahaza_posting.py` |
| Marketing → Finance (AR) | sales-data → `generate-ar-batch` → `rahaza_ar_invoices` → `post_ar_invoice` | `marketing_sales.py` |
| Marketing ↔ Gudang (retur) | `marketing_returns` ↔ `wh_returns` (link 2-arah) | `marketing_returns_routes.py`, `dewi_wh_returns.py` |
| Marketing ← RnD | product-launch auto-create FG di `rahaza_materials` | `marketing_product_launches_routes.py` |
| Maklon ⟂ Marketing | **TERPISAH** (produk klien, `dewi_maklon_buyer_catalog`) | by design |

---

## 6. GAP & OVERLAP (grounded — untuk keputusan, belum dieksekusi)
1. **GAP Demand→Produksi (MKT-1, dari E5):** order online **tidak** auto-jadi `production_pos`/WO.
   Fulfillment hanya jalan dari **stok FG yang sudah ada**. Rekomendasi E5 = tombol onward "Buat PO
   Produksi" (Opsi B, semi-manual).
2. **GAP Fulfillment→Surat Jalan:** `fulfillment.py` dispatch **tidak** membuat `wh_delivery_notes`
   (SJ-ONLINE) — padahal tipe SJ-ONLINE "Pengiriman Online Shop" sudah ada di `wms_delivery_notes.py`.
   → order online tidak menghasilkan surat jalan resmi. (Nyambung ke analisis Surat Jalan sebelumnya.)
3. **OVERLAP koleksi demand:** `marketing_orders` vs `dewi_toko_orders` vs `rahaza_orders` +
   `marketing_sales_data` (lihat §3). Perlu kebijakan owner tunggal per kanal.
4. **Kopling katalog LONGGAR (MKT-2):** `marketing_catalog_items` simpan `sku`+`price` sendiri, tanpa
   FK `model_id` ke `rahaza_models` → risiko drift harga/master.
5. **Inkonsistensi nama platform:** accounts memvalidasi `["shopee","tiktokshop","tokopedia"]`,
   sedang seed order pakai `"tiktok"` (bukan `tiktokshop`). Minor, tapi bisa memutus filter per-akun.
6. **Status seed timpang (konteks demo):** transaksi ada (orders 60, live 18, konten 30, ulasan 40,
   retur 30, komplain 40) tetapi **master kosong** (accounts/catalogs/kol_creators/targets = 0,
   sales_data/webhook_events/tasks/launches/discounts = 0). Akibatnya beberapa layar (Kelola Akun,
   Katalog, KOL, Target, toko-overview) tampil kosong walau flow-nya jalan.

---

## 7. STATUS SEED SAAT INI (live)
`marketing_orders=60 · live_sessions=18 · content_calendar=30 · reviews=40 · returns=30 · complaints=40`
`| KOSONG: platform_accounts, catalogs, catalog_items, kol_creators, targets, sales_data, webhook_events, tasks, product_launches, discounts, dewi_toko_orders, rahaza_orders`

> Untuk demo penuh flow order-to-cash + master, perlu seed tambahan (mis. `scripts/seed_marketing_demo.py`
> dan/atau seeder katalog/akun) — belum dijalankan sesi ini.

---
---

# ADENDUM 2 — KOREKSI FINANCE + KATALOG + KONTEN-LINK + PORTAL EKSTERNAL + BUDGET + AKSES
> Ditambahkan setelah klarifikasi user. GROUNDED ke kode (file:line). Tetap read-only.

## A2.1 — KOREKSI FLOW KE FINANCE (penting)
**Klarifikasi user (benar):** yang **otomatis ke finance** seharusnya **EXPORT PENCAIRAN (settlement/disbursement
marketplace, NET setelah potongan/fee)** — **BUKAN** dari sales harian maupun dari fulfillment. Input sales
harian cukup **masuk dashboard marketing** (analitik), bukan jurnal finance.

**Kondisi kode saat ini (AS-IS) — TIDAK sesuai intent user:**
- **Sales → AR (GROSS):** `MarketingARBridgeModule` (Phase 7E) memanggil
  `POST /api/marketing/sales-data/generate-ar-batch` (`marketing_sales.py:171`) → buat `rahaza_ar_invoices`
  → `post_ar_invoice` ke GL. Ini **memakai angka sales (bruto), tanpa potong fee marketplace**.
- **Fulfillment → COGS:** `fulfillment.py` saat dispatch → `post_cogs_shipment` (Dr COGS/Cr FG). (sisi biaya)
- **Order manual** simpan `fee_amount`/`net_amount` (`marketing_orders_routes.py:419-441`) tapi **tidak**
  dipakai untuk posting finance.
- **"Pencairan" di kode = HANYA HR** (kasbon/pinjaman/klaim: `dewi_kasbon.py`, `FinanceKasbonModule.jsx`).
  **Tidak ada** konsep **pencairan/settlement marketplace → finance**.

**⇒ GAP:** belum ada modul **"Export/Import Pencairan Marketplace"** (net-of-fee) sebagai satu-satunya
sumber otomatis ke finance. Jalur `generate-ar-batch` (sales→AR bruto) **bertentangan** dengan model bisnis
yang benar (ada potongan admin fee, ongkir ditanggung, refund, dsb). Perlu keputusan:
(a) **nonaktifkan/ubah** AR-bridge dari sales → jadikan **dashboard-only**; (b) buat **entitas pencairan**
(settlement) per akun/periode: gross → (−fee −ongkir −refund −adjustment) → **net cair** → post ke finance
(AR settle / kas masuk). Sumber data = file export marketplace (mirip pola `marketing_import.py`).

## A2.2 — KATALOG (verifikasi flow baru RnD→master→per toko)
**Sudah BENAR sebagian (mengikuti flow baru):**
- Katalog **per toko**: `marketing_catalogs.account_id` → item mewarisi `account_id`+`platform`
  (`marketing_catalog_items.py:193-194`). Filter per akun ada di FE (`CatalogManagementModule.jsx:347`
  `filterAccount` → query `account_id`).
- Ambil dari **master FG**: endpoint **`POST /{catalog_id}/items/from-fg`** (`:327`) baca
  `rahaza_materials` (type='fg'), auto-isi SKU/nama/warna/kategori + snapshot stok dari
  `rahaza_material_stock`. **Mode default FE untuk item baru = `from_fg`** (`CatalogManagementModule.jsx:914`). ✅
- **Harga jual** = `price`; **harga coret** ditampilkan `line-through` bila `original_price>0`
  (`CatalogManagementModule.jsx:470-472`). ✅ (secara tampilan sudah ada harga jual + harga coret)
- Link master model RnD: field **`model_id` FK ke `rahaza_models`** (MKT-2), divalidasi bila diisi (`:185-188`).

**Rantai master:** RnD Style → `promote-to-production` → **`rahaza_models`** (`dewi_rnd_styles.py:210`);
Product Launch → **auto-create FG** di `rahaza_materials` (`marketing_product_launches_routes.py:335`).
Katalog `from-fg` menarik dari `rahaza_materials` (FG). `model_id` opsional menautkan balik ke `rahaza_models`.

**⚠️ Isu/gap katalog:**
1. **Ambiguitas `original_price`**: di `CatalogItemCreate` dilabel *"HPP/base price"* (`:99`), di
   `CatalogItemFromFG` dilabel *"HPP/coret price (optional)"* (`:145`). Jadi **satu field dipakai untuk 2 makna**
   (HPP biaya vs harga coret/diskon). Tidak ada field **`discount_price`/`harga_coret`** khusus terpisah dari HPP.
   → Untuk kebutuhan "harga jual + harga jual coret (diskon)" sebaiknya **pisahkan** `harga_coret` dari HPP.
2. **`model_id` masih opsional** → kopling ke master RnD bisa kosong (drift, MKT-2 belum wajib).
3. Endpoint manual lama (`POST /{catalog_id}/items`) masih ada (source='manual', tanpa link FG) — legacy.

## A2.3 — CONTENT CALENDAR: LINK GOOGLE DRIVE
- Backend **mendukung** field **`reference_link`** (`marketing_content_calendar_routes.py:114,137,150,299`) —
  bisa diisi URL Google Drive apa pun. ✅ (data path siap)
- **FE: field ini "phantom"** — ada di *state* form (`ContentCalendarModule.jsx:64,179`) TAPI **tidak ada
  `<Input>` untuk mengisinya** dan **tidak dirender sebagai link** di list. ❌
  → **GAP kecil:** tinggal tambah 1 input (label "Link Referensi / Google Drive") + render `<a target=_blank>`
  di kartu/list. Tanpa rebuild — hanya sisipkan pada view yang ada.

## A2.4 — PORTAL EKSTERNAL: LIVE HOST & KREATOR (KOL)
### LiveHost (`/api/marketing/livehost/portal/*`, `marketing_livehost_portal.py`)
- **Auth terpisah**: `POST /portal/auth/login` (email+password_hash di `marketing_livehosts`) → **livehost JWT**
  (`_create_livehost_token`), brute-force 5x→lock 15m. Bukan role internal.
- **Input/Output (self-service):** `my-profile`, `my-shifts`, `scripts` (global + akun ter-assign),
  `training` + self-complete, **`POST /portal/clock`** (clock-in/out per shift, deteksi telat >15m),
  notifikasi (SSOT + SSE stream).
- **Assign ke toko = BENAR:** field **`assigned_account_ids` (ARRAY)** → **1 host bisa multi toko** ✅
  (`marketing_livehost_hosts.py:51`; update `:596-597`). Scripts & profil difilter per akun ter-assign.
- **Admin (require_auth):** CRUD host, assign akun, shift, script, training, analytics.
- **⚠️ Potensi bug field-drift:** `portal_clock_in_out` membaca `shift['shift_start_time']` **langsung**
  (`marketing_livehost_portal.py:306`, di LUAR try) padahal shift bisa tersimpan sebagai `scheduled_start`
  (dinormalisasi hanya di `my-shifts`). Bila shift dibuat tanpa `shift_start_time` → **KeyError/500**. Perlu verifikasi model `ShiftCreate`.

### Kreator/KOL (`/api/marketing/creator-portal/*`, `marketing_kol_portal.py`)
- **Auth terpisah**: `POST /creator-portal/auth/login` (`login_email`+`login_password_hash` di
  `marketing_kol_creators`) → **creator JWT** (audience='creator-portal'), brute-force protected.
- **Input/Output:** `auth/profile`, `catalog` (difilter akun ter-assign), **`POST /requests`** (minta sample
  produk, validasi akses akun, snapshot stok) → `marketing_creator_item_requests` (status `pending`),
  `my-requests`, `my-performance`, `my-kpi` (revenue/sessions/viewers vs `kpi_targets`).
- **Assign ke toko = BENAR:** `assigned_account_ids` (ARRAY) → **1 kreator multi toko** ✅. Akses katalog &
  request **divalidasi ketat** (`403` bila akun tak ter-assign, `:72-73`, `:97-98`). Kontrol akses solid.
- **⚠️ OVERLAP katalog:** kreator memakai **koleksi katalog TERPISAH** `marketing_creator_catalog`
  (di-CRUD admin via `marketing_kol_ops.py:203`), **BUKAN** `marketing_catalog_items` (katalog utama toko).
  → Produk di katalog toko **tidak otomatis** terlihat oleh kreator; admin harus isi 2x. Ini **inkonsistensi
  data** (2 sumber katalog). Kandidat konsolidasi: kreator baca dari katalog utama difilter `assigned_account_ids`.

## A2.5 — FITUR BUDGET (permintaan baru) — STATUS: **BELUM ADA**
**Yang diminta:** tiap **akun toko** punya **(a) target sales** + **(b) budget marketing**, lalu tracking
**realisasi/hasil/compare**.
**AS-IS:**
- **Target sales per akun: ADA** → `marketing_account_targets` (`revenue_target`, `orders_target`,
  `health_score_target`) + `GET /targets/monthly-summary` (target vs actual, %). (`marketing_targets.py:24-31,107`) ✅
- **Budget marketing per akun: TIDAK ADA** ❌ — model target **tidak punya** field budget/spend.
- `rahaza_budget.py` = **budget FINANCE/GL** (prefix `/api/rahaza/finance`, pakai `cost_center_id`/COA),
  **bukan** budget per-toko marketing.
- `marketing_ads_routes.py` punya `spend`/`roas`/`cpa` **TAPI DATANYA MOCK/RANDOM** (`:50 seed_ads_if_empty`,
  `:73 random.uniform`), tidak ada input budget vs realisasi nyata.

**⇒ REKOMENDASI PENEMPATAN (sub-menu yang sesuai):**
- **Perluas menu `marketing-targets` ("Target Bulanan")** menjadi **"Target & Budget Bulanan"**:
  tambah `budget_marketing` (rencana) + `budget_spent`/realisasi (dari input biaya iklan/promosi/sample per akun)
  ke `marketing_account_targets` → `monthly-summary` tampilkan **compare: target vs actual sales** dan
  **budget vs spend** (sisa budget, %, over/under). Ini paling natural (sudah per-akun/bulan).
- Alternatif: sub-menu baru **"Budget Marketing"** di Seksi 3 (Analitik) bila ingin dipisah dari target sales.
- Sumber "spend": input manual biaya per akun (iklan/promo/sample/komisi KOL) — **jangan** pakai angka mock ads.

## A2.6 — MATRIKS AKSES (grounded: `portalAccess.js` + `routes/shared.py:115-137`)
| Area | Auth | Role/akses |
|---|---|---|
| **Portal Marketing (`toko`)** internal | `require_auth` + `require_portal('toko')` | `pic_toko, pic_marketing, staff_marketing, marketing_kol, cs_staff, manager_marketing` (+`buyer` di backend) + SUPER (`superadmin/admin/owner`) |
| **Portal LiveHost** (eksternal) | `require_livehost_auth` (JWT sendiri) | akun di `marketing_livehosts` (email+password) — **hanya data dirinya**, difilter `assigned_account_ids` |
| **Portal Kreator/KOL** (eksternal) | `require_creator_auth` (JWT aud=`creator-portal`) | akun di `marketing_kol_creators` (`login_email`) — **hanya akun ter-assign** (403 di luar itu) |

**⚠️ Catatan akses/testing:** akun demo yang ada (`admin, hr, finance, spv, gudang, maklon`) **tidak** memuat
role marketing (`pic_marketing` dll). Jadi saat ini **hanya `admin` (super)** yang bisa membuka Portal Marketing;
untuk uji RBAC marketing sebenarnya perlu seed akun role marketing + akun demo LiveHost & Kreator.

## A2.7 — RINGKAS: GAP BARU vs KLARIFIKASI
| # | Item | Status | Aksi (belum dieksekusi) |
|---|---|---|---|
| 1 | Auto-ke-finance via **Pencairan (net fee)** | ❌ belum ada; malah pakai sales→AR bruto | Buat modul settlement/pencairan; jadikan sales dashboard-only |
| 2 | Katalog per-toko + from-FG + harga jual/coret | ✅ ada | Pisahkan `harga_coret` dari HPP; wajibkan `model_id` |
| 3 | Content calendar link Google Drive | ⚠️ field ada, UI tak render | Tambah input + link `<a target=_blank>` |
| 4 | LiveHost assign multi-toko + logic | ✅ benar | Cek bug field-drift `shift_start_time` di `/portal/clock` |
| 5 | Kreator assign multi-toko + akses | ✅ benar (akses ketat) | Konsolidasi `marketing_creator_catalog` ↔ katalog utama |
| 6 | Budget marketing per-toko + compare | ❌ belum ada (hanya target sales) | Perluas `marketing-targets` → Target & Budget |
| 7 | Ads spend | ⚠️ MOCK/random | Ganti input nyata bila dipakai untuk realisasi budget |
