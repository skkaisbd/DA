# Development Plan — MASTER KATEGORI PRODUK · HPP · HARGA JUAL · SSOT STOK KATALOG (Session 2026-08-10)

> Problem statement (owner): lanjutkan repo **https://github.com/kaamabagajana/DA**. 9 keputusan sudah FINAL (K-1…K-9) dan urutan kerja FINAL: **F1 → F7 → F2–F5 → F6 → F8 → F9**. Migrasi: **dry-run dulu**, lalu eksekusi.
>
> Fokus inti (core): **SSOT master produk ↔ FG ↔ katalog ↔ order** agar tidak ada **overselling / stok 0 / kategori basi / kode kembar**.

---

## 1) Objectives

1. Hilangkan bug **kode produk kembar** (T1) dan normalisasi `active` agar index unik bekerja dan dashboard akurat.
2. Terapkan **satu rumus stok jual** (K-6a/K-7a) dipakai konsisten oleh 3 pintu: `from-fg`, `sync-fg-stock`, `sync-from-wms` (menutup M1–M5, cegah overselling).
3. Bangun **Master Kategori Produk** (K-2) + `category_id` tervalidasi, propagate ke FG + katalog.
4. Lengkapi master produk: **base_hpp + retail_price + weight_gram**; HPP punya **source** (rnd/manual).
5. Perbaiki katalog: kategori bukan teks bebas, stok **live**, harga default dari master, margin bisa dihitung.
6. Perbaiki order: wajib tautan ke master (K-8a), reservasi saat confirm, allocate auto-suggest material.
7. Semua perubahan aman uang/data: **gate.sh tetap hijau**, migrasi idempoten + dry-run.

---

## 2) Implementation Steps (phased)

### Phase 1 — Core POC (Isolation) ✅ WAJIB
**Deliverable:** `test_core_master_katalog.py` (HTTP nyata, clean up 0 jejak data uji).

User stories (POC):
1. As staff, I can run one script and see PASS/FAIL for all invariants before code is merged.
2. As finance/ops, I can trust “stok katalog” never exceeds `on-hand - reserved`.
3. As marketing, a new item from FG never starts at stock 0 if stock exists.
4. As ops, updating master category/weight propagates to FG & catalog consistently.
5. As fulfillment, an order cannot be created with unknown SKU; it must link to a real catalog item/variant.

POC scope:
- Seed prerequisites (restore membuat `rahaza_colors`/`rahaza_sizes` kosong): ensure colors+sizes seeded.
- F1 assertions: duplicate code returns 409 even if existing doc only has `status:'active'`; no doc missing `active`; dashboard counts include promoted models.
- F7 assertions: `from-fg` == `sync-fg-stock` == `sync-from-wms` for same item; excludes `blocked/quarantine`; includes `variant_sku` links; uses `read_qty/read_reserved`.
- F2–F5 assertions: master categories endpoints; model code auto from prefix; `category_id` unknown → 400; delete category in use → 409; SKU format unchanged.
- F8/F9 assertions: refresh-from-master works; deactivate model/variant disables catalog items (K-9a); order create requires `catalog_item_id/variant_id`; confirm reserves; allocate suggests.

Do not proceed until POC is 100% green.

### Phase 2 — V1 App Development (apply changes per owner order)

#### F1 — Fix T1 (kode kembar) + normalisasi `active`
- Backend fixes:
  - `routes/rahaza_production.py`: duplicate check must not depend on `active: True` only.
  - `routes/dewi_rnd_styles.py`: promote writes `active: True` (stop using `status` as liveness).
  - Seeders (`rahaza_setup`, `rahaza_admin_helpers`): always write `active`; lookup not only `active: True`.
  - `routes/dashboard_routes.py`: counts must include promoted docs (legacy `status`).
  - Index review: `rahaza_models.code` partial unique needs compatibility with legacy docs.
- Migration (dry-run then apply): `backend/migrations/normalize_model_active.py` (report duplicates; no auto-merge).
- Gate: `scripts/verify_master_produk.py` PR-1..PR-3, PR-9.

User stories:
1. As staff, I cannot create a model with a code that already exists (always 409).
2. As owner, dashboard product counts match actual list models.
3. As admin, promoted-from-R&D models behave like normal models (active=true).
4. As ops, legacy models still load and can be edited safely.
5. As QA, migration reports existing duplicates clearly before any write.

#### F7 — SSOT stok jual katalog (K-6a/K-7a)
- Add `core/catalog_stock.py`: `sellable_stock()` = Σ(read_qty) − Σ(read_reserved) for all locations except `blocked/quarantine`; resolve via `variant_sku` or `fg_material_id/material_id`.
- Update routes:
  - `marketing_catalog_items.py` `from-fg`: stop default-location logic; compute via SSOT; store cache + `in_sync`.
  - `sync-fg-stock`: use SSOT.
  - `marketing_catalog_stock.py` `sync-from-wms`: use SSOT; include variant-linked items; no raw `qty`.
  - `GET /{cid}/items`: include `available` live + `in_sync`.
- Gate: `scripts/verify_katalog_stok.py` KT-1..KT-5.
- FE `CatalogManagementModule.jsx`: show `available` live + badge “basi/tidak tertaut”.

User stories:
1. As marketing, “Sync from WMS” cannot inflate stock above sellable stock.
2. As staff, adding item from FG shows real stock immediately.
3. As ops, blocked/quarantine stock never appears as sellable.
4. As admin, items linked via variant SKU are included in sync.
5. As user, list items shows both cached stock and live available with sync status.

### Phase 3 — Master Produk & Katalog (F2–F6)

#### F2 — Master kategori produk
- New collection `rahaza_product_categories` + unique index on `code`.
- New endpoints CRUD `/api/rahaza/product-categories` (DELETE = deactivate, 409 if used).
- Migration seed: `seed_product_categories.py` for 14 categories.
- FE: new `RahazaProductCategoriesModule.jsx` + tab in `ProductionMasterProductHub.jsx`.

User stories:
1. As admin, I can add/edit/reorder categories and set SKU prefix.
2. As staff, I cannot delete a category still used by products.
3. As staff, category dropdown is consistent across modules.
4. As owner, category list is auditable (created_from).
5. As QA, category codes are unique and stable.

#### F3 — `category_id` on model + validation + propagation
- Add `core/product_master.py`: `apply_category`, `resolve_hpp`, `propagate_master_changes`.
- Update model create/update: validate `category_id` active; denormalize `category_code/name`; keep legacy `category` synced.
- Update `variant_ssot._variant_linkage()` + FG creation to carry `category_id/code`.
- Migrations: `backfill_model_category_id.py` (K-5a auto-create unknown categories) + `backfill_fg_from_model.py`.

User stories:
1. As staff, I cannot save a product with unknown/inactive category.
2. As marketing, changing a product category updates linked FG and catalog items.
3. As ops, legacy category text remains readable but is now controlled.
4. As admin, migration creates missing categories instead of losing data.
5. As QA, propagation touches only linked docs (by model_id).

#### F4 — Model code auto-generate from `sku_prefix` (K-1A)
- Add atomic counter utility; generate codes like `VST-0001` on create.
- Preserve variant SKU format `{MODEL}-{WARNA}-{SIZE}`.

User stories:
1. As staff, I can create a new product without typing code; code is generated.
2. As ops, SKU format stays stable (no barcode migration).
3. As owner, prefix makes category visible in SKU.
4. As QA, counters are collision-safe under concurrency.
5. As admin, manual code entry is either disallowed or validated strictly.

#### F5 — base_hpp + retail_price + weight_gram + revive fields
- Add fields on `rahaza_models`: `base_hpp`, `retail_price`, `weight_gram`, `hpp_source`, `hpp_updated_at`; show `techpack` summary.
- HPP resolution SSOT: `model.hpp (rnd) → base_hpp (manual) → 0`.
- Ensure `weight_gram` propagates to FG.

User stories:
1. As marketing, products created manually still have usable HPP (base_hpp).
2. As owner, retail price exists at product level and can be compared.
3. As warehouse, FG weight is correct for shipping calculations.
4. As staff, UI shows HPP value plus its source (rnd/manual).
5. As QA, changing weight/category updates FG and catalog.

#### F6 — Catalog uses master (category_id + pricing defaults)
- Make catalog category read-only/dropdown from FG link (no free text).
- Filter by `category_id` server-side.
- Default `harga_jual` from `retail_price`; show delta vs official.
- `_resolve_rnd_hpp` fallback to `base_hpp` + `hpp_source='manual'`; margin display.

User stories:
1. As marketing, I can filter catalog items by master category reliably.
2. As marketing, new items prefill price from retail_price but can override per platform.
3. As owner, I can see deviation of platform price vs official.
4. As finance, margin is computable even for non-R&D products.
5. As staff, category cannot be mistyped in catalog items.

### Phase 4 — Hardening flows (F8–F9)

#### F8 — Refresh-from-master + K-9a enforcement
- Add `POST /api/marketing/catalogs/{cid}/refresh-from-master`.
- Expand `propagate_master_changes()` to include name/weight/category.
- Enforce K-9a: deactivating model/variant auto-deactivates linked catalog items + returns impacted list.
- `from-fg` rejects FG whose model inactive.

User stories:
1. As marketing, I can refresh catalog display fields from master in one action.
2. As ops, inactive products cannot be re-listed accidentally.
3. As admin, I get a list of catalog items affected by deactivation.
4. As QA, no orphan catalog items remain.
5. As staff, “from-fg” prevents adding discontinued items.

#### F9 — Orders must link to master + reserve on confirm
- Update `POST /api/marketing/orders`: require `catalog_item_id` or `variant_id`; fill `fg_material_id`; reject unknown SKU (400); legacy orders remain readable.
- `PATCH /{order_id}/status` confirmed: reserve stock.
- `fulfillment.allocate`: auto-suggest `material_id` from order link.
- FE orders: select product from catalog (no free-text SKU).

User stories:
1. As staff, I cannot create an order for an unknown SKU.
2. As fulfillment, allocate suggests the right FG automatically.
3. As ops, confirming an order immediately reserves stock.
4. As manager, legacy orders still show in history.
5. As finance, order-to-stock linkage is auditable.

---

## 3) Next Actions (immediate)

1. Implement **Phase 1 POC script** `test_core_master_katalog.py` (seed colors/sizes, run assertions, cleanup).
2. Add minimal scaffolding for new gates: `verify_master_produk.py` + `verify_katalog_stok.py` (can start as failing, then make green).
3. Start F1 code changes (active normalization + duplicate checks + dashboard counts) until POC F1 section green.
4. Start F7 SSOT stock module + route rewires until POC F7 section green.
5. After each phase: run `bash scripts/gate.sh` and update `test_result.md` + plan status.

---

## 4) Success Criteria

- POC script: **100% PASS**, leaves **0** test artifacts.
- `bash scripts/gate.sh`: stays **VERDICT HIJAU**.
- Invariants:
  - No duplicate `rahaza_models.code` (legacy `status` docs included); create always 409 on collision.
  - Stock sellable formula consistent across 3 entry points; never oversells; excludes blocked/quarantine.
  - Categories are validated by `category_id`; propagate to FG + catalog; delete in-use returns 409.
  - Model code auto-generated by prefix; variant SKU format unchanged.
  - Catalog uses master: category not free text; live available shown; price defaults from master.
  - Orders link to master; unknown SKU rejected; confirm reserves; allocate suggests.

**Out of scope (explicit):** marketplace sync real providers (M11), unify Maklon categories (K-4b), price-per-variant (K-3c), fixing dual-meaning `rahaza_materials.category` (T4), deprecated `products/product_variants`.
