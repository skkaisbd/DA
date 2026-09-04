# E5 — MARKETING : Catalog ↔ Demand ↔ Fulfillment (AS-IS vs TO-BE)
> Handoff §E5. GROUNDED: `marketing_catalog*.py`, `marketing_orders_routes.py`, `fulfillment.py`,
> `marketing_accounts.py`, `dewi_maklon_buyer_catalog.py`. STATUS: ANALISIS.

## 0. RANTAI YANG BENAR (target): RnD→Model→**Katalog**→(jual online)→**Demand**→**Produksi**→FG→**Fulfillment**→kirim
Marketing = etalase (harga jual + plot akun toko) + penampung DEMAND + fulfillment FG.
**Maklon TIDAK lewat marketing** (produk milik klien; `dewi_maklon_buyer_catalog` terpisah).

## 1. KATALOG — AS-IS (`marketing_catalog*.py`)
| Objek | Collection | Field kunci | Catatan |
|---|---|---|---|
| Katalog (per akun toko) | `marketing_catalogs` | id, **account_id**, name, is_active | 1 katalog ⟶ 1 akun platform |
| Item katalog | `marketing_catalog_items` | id, catalog_id, account_id, **sku**, name, **price** (jual), image, is_active | dibuat 2 jalur: custom (`:174-211`) & dari FG (`fg_code`, `:385-423`) |
| Akun platform (toko) | `marketing_platform_accounts` | account_code, account_name, **platform** (shopee/tiktokshop/tokopedia) | PIC marketing buat unlimited akun (`marketing_accounts.py:23-66`) |
- **Kopling ke master produk = LONGGAR (by SKU/`fg_code`), BUKAN FK `model_id`.** Item katalog menyimpan
  `sku` + `price` sendiri; tak ada ref langsung ke `rahaza_models`. → risiko drift harga/master (D3-terkait).

## 2. DEMAND (order masuk) — AS-IS
| Sumber | Collection | Asal |
|---|---|---|
| Marketplace/KOL/Livehost | `marketing_orders` (52×) | impor/webhook/manual + fulfillment extend |
| Online shop | `dewi_toko_orders` (4×) | toko online (sebagian via `_toko_adapter.py`) |
| Sales internal | `rahaza_orders` (47×) | penjualan langsung/internal |
| Sales data agregat | `marketing_sales_data` | rekap penjualan harian (target vs actual) |

### ❗ GAP DEMAND→PRODUKSI (temuan)
- **Tidak ada auto-link `marketing_orders`/`dewi_toko_orders` → production_pos / WO** (grep pada
  `marketing_orders_routes.py`/`dewi_online_orders.py` = 0 pembuat produksi).
- Hanya `production_po.py:539` bisa buat PO produksi dari `rahaza_orders` (parsial). 
- Artinya: **DEMAND online tidak otomatis menjadi PO produksi** — sekarang manual. Ini persis akar
  gesekan yang disebut di FLOW_UX_AUDIT (butuh jembatan onward). Fulfillment jalan dari **STOK FG yang
  sudah ada**, bukan dari trigger produksi.

## 3. FULFILLMENT — AS-IS (`fulfillment.py`, `/api/fulfillment`)
- Sumber FG: **`rahaza_material_stock`** (ownership `cv_da`, inventory_category `fg_internal`).
- `marketing_orders` di-extend: `fulfillment_status`, `fulfillment_items[]`, `shipment_ref`, `dispatched_at`.
- Alur: **allocate** (pilih FG manual dari stok) → **picking** → **packed_ready** → **dispatched** → delivered.
  Statuses: `pending_fulfillment → allocated → picking → packed_ready → dispatched → delivered` (`:62`).
- Saat dispatch → **`post_cogs_shipment`** (E3): Dr COGS / Cr FG (pakai HPP snapshot). → **anchor rahaza HPP** (risiko FIN-1).

## 4. TO-BE — Marketing dalam ekosistem
| Edge | TO-BE | Catatan |
|---|---|---|
| Master → Katalog | item katalog **rujuk `rahaza_models` via model_id** (bukan hanya sku) + snapshot harga | rapikan D3; harga jual di katalog, cost di model |
| Katalog → Demand | order online tercatat di `marketing_orders` | tetap |
| **Demand → Produksi** | order yang butuh produksi → **buat `production_pos`** (jembatan onward) | tutup GAP; pakai fondasi `handleNavigate`/onward CTA |
| FG → Fulfillment | allocate dari `rahaza_material_stock` (cv_da/fg_internal) | tetap; COGS lihat FIN-1 |
| Maklon | **tak masuk marketing** (`dewi_maklon_buyer_catalog` terpisah, spek klien) | jangan campur |

## 5. DECISION POINTS
### ⚠️ MKT-1 (PERLU KEPUTUSAN) — jembatan Demand→Produksi
Tutup gap order→PO produksi:
- **Opsi A** — otomatis: order dgn qty melebihi stok FG → auto-draft `production_pos`.
- **Opsi B** — semi-manual: tombol onward "Buat PO Produksi" dari layar order (pakai `<OnwardCTA>` yg sudah ada).
- **Rekomendasi B** (kontrol perencanaan produksi; lebih aman drpd auto-PO). 

### ⚠️ MKT-2 — kopling katalog ke master
Tambah `model_id` FK pada `marketing_catalog_items` (selain sku) supaya harga jual & master produk tak drift.
[rek: ya, LOW effort, memperkuat rantai RnD→Model→Katalog]

## 6. INVARIAN
- Fulfillment allocate ≤ available FG (`rahaza_material_stock.available_quantity`).
- COGS hanya saat dispatch (idempotent `cogs:{shipment_id}`).
- Item katalog aktif harus punya harga jual > 0.
- Maklon: NOL keterkaitan ke marketing catalog/fulfillment.

---
*E5 selesai. Lanjut E6 (HR piece-rate).*
