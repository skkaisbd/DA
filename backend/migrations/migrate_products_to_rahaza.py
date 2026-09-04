"""
Migration: Legacy Master Product (products / product_variants)
          → Rahaza Master Product SSOT (rahaza_models / rahaza_model_variants / rahaza_colors)
================================================================================
Task     : FASE 4 legacy cleanup — Master Product consolidation
Created  : 2026-07-19
Reversible: NO (but idempotent — re-runs are safe and create 0 new docs).
            Legacy collections are NOT dropped by this script.

WHY
---
The legacy `products` / `product_variants` collections are DEPRECATED (see the
DEPRECATION banner in routes/master_data.py). The active UI uses:
  · rahaza_models          — the model header (Internal PO product master)
  · rahaza_model_variants  — Warna × Size variants with unique SKU
  · rahaza_colors          — dynamic color palette (SKU color code source)
This script mirrors any remaining legacy data into the new SSOT so a real
deployment (which may still hold `products`/`product_variants` rows) can be
migrated safely. In THIS environment both collections are empty → the script is
a verified NO-OP, but it is kept for real deployments.

MAPPINGS
--------
products → rahaza_models
    id              := product.id                 (reused → stable, idempotent)
    code            := product.product_code|derived (UPPER, unique per active)
    name            := product.product_name
    category        := product.category or "Sweater"
    description      := product.description or ""
    active          := (product.status != 'inactive')
    _migrated_from  := "products";  _source_id := product.id
    _legacy_prices  := {cmt_price, selling_price}   (reference only)

product_variants → rahaza_model_variants  (+ ensure rahaza_colors / rahaza_sizes)
    model           := resolved from product_variant.product_id mapping
    color           := matched in rahaza_colors by name→code, else CREATED
    size            := matched in rahaza_sizes  by code→name, else CREATED
    sku             := variant.sku or {model.code}-{color.code}-{size.code}
    (denormalized model_code/size_code/color_*/hex filled like the live API)
    _migrated_from  := "product_variants";  _source_id := variant.id

IDEMPOTENCY
-----------
  · rahaza_models         : skip-create if a model with the same UPPER code exists.
  · rahaza_colors         : match by name (ci) then code; create only if missing.
  · rahaza_sizes          : match by code (ci) then name; create only if missing.
  · rahaza_model_variants : skip if same SKU (active) OR same (model_id,size_id,color_id) exists.

USAGE
-----
    cd /app/backend
    python migrations/migrate_products_to_rahaza.py            # DRY-RUN (report only, no writes)
    python migrations/migrate_products_to_rahaza.py --execute  # apply for real
    python migrations/migrate_products_to_rahaza.py --json     # machine-readable report (dry-run)
    python migrations/migrate_products_to_rahaza.py --execute --json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv  # noqa: E402
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _color_code_from_name(name: str) -> str:
    """Mirror routes/rahaza_variants.create_color: default code = first 3 letters UPPER."""
    return (name or "")[:3].strip().upper().replace(" ", "") or "CLR"


def _make_sku(model_code: str, color_code: str, size_code: str) -> str:
    parts = [
        str(model_code or "").strip().upper(),
        str(color_code or "").strip().upper(),
        str(size_code or "").strip().upper(),
    ]
    return "-".join(p for p in parts if p)


class Report:
    """Collects the migration plan/result for human + JSON output."""

    def __init__(self, execute: bool):
        self.execute = execute
        self.models_created = []
        self.models_skipped = []      # already present
        self.colors_created = []
        self.colors_reused = []
        self.sizes_created = []
        self.sizes_reused = []
        self.variants_created = []
        self.variants_skipped = []    # already present / duplicate SKU
        self.warnings = []

    def to_dict(self):
        return {
            "mode": "execute" if self.execute else "dry-run",
            "summary": {
                "models_created": len(self.models_created),
                "models_skipped": len(self.models_skipped),
                "colors_created": len(self.colors_created),
                "colors_reused": len(self.colors_reused),
                "sizes_created": len(self.sizes_created),
                "sizes_reused": len(self.sizes_reused),
                "variants_created": len(self.variants_created),
                "variants_skipped": len(self.variants_skipped),
                "warnings": len(self.warnings),
            },
            "details": {
                "models_created": self.models_created,
                "models_skipped": self.models_skipped,
                "colors_created": self.colors_created,
                "sizes_created": self.sizes_created,
                "variants_created": self.variants_created,
                "variants_skipped": self.variants_skipped,
                "warnings": self.warnings,
            },
        }


async def _ensure_color(db, rep: Report, name: str, cache: dict):
    """Return a rahaza_colors doc for `name`. Match by name (ci) then code; create if missing.

    In dry-run mode, un-persisted synthetic docs are still cached so the SKU/id
    resolution stays consistent within a single run.
    """
    key = (name or "").strip().lower() or "warna"
    if key in cache:
        return cache[key]
    code = _color_code_from_name(name)
    # 1) match existing by name (ci)
    existing = await db.rahaza_colors.find_one(
        {"name": {"$regex": f"^{name.strip()}$", "$options": "i"}}) if name else None
    # 2) match by code
    if not existing:
        existing = await db.rahaza_colors.find_one({"code": code})
    if existing:
        rep.colors_reused.append({"name": name, "code": existing.get("code")})
        cache[key] = existing
        return existing
    # Create (respect unique-code: bump suffix if code taken)
    final_code = code
    n = 1
    while await db.rahaza_colors.find_one({"code": final_code}):
        n += 1
        final_code = f"{code}{n}"
    doc = {
        "id": _uid(), "code": final_code, "name": (name or "Warna").strip(),
        "hex": "#CCCCCC", "order_seq": 50, "active": True,
        "created_at": _now(), "updated_at": _now(),
        "_migrated_from": "product_variants.color",
    }
    if rep.execute:
        await db.rahaza_colors.insert_one(dict(doc))
    rep.colors_created.append({"name": doc["name"], "code": final_code})
    cache[key] = doc
    return doc


async def _ensure_size(db, rep: Report, size_text: str, cache: dict):
    """Return a rahaza_sizes doc for `size_text`. Match by code (ci) then name; create if missing."""
    key = (size_text or "").strip().upper() or "ONE"
    if key in cache:
        return cache[key]
    existing = await db.rahaza_sizes.find_one(
        {"code": {"$regex": f"^{key}$", "$options": "i"}})
    if not existing:
        existing = await db.rahaza_sizes.find_one(
            {"name": {"$regex": f"^{key}$", "$options": "i"}})
    if existing:
        rep.sizes_reused.append({"size": size_text, "code": existing.get("code")})
        cache[key] = existing
        return existing
    # next order_seq
    last = await db.rahaza_sizes.find_one(sort=[("order_seq", -1)])
    next_seq = int((last or {}).get("order_seq", 0)) + 1
    doc = {
        "id": _uid(), "code": key, "name": key, "order_seq": next_seq,
        "active": True, "created_at": _now(), "updated_at": _now(),
        "_migrated_from": "product_variants.size",
    }
    if rep.execute:
        await db.rahaza_sizes.insert_one(dict(doc))
    rep.sizes_created.append({"size": key, "order_seq": next_seq})
    cache[key] = doc
    return doc


async def migrate(db, execute: bool) -> Report:
    rep = Report(execute)

    n_products = await db.products.count_documents({})
    n_variants = await db.product_variants.count_documents({})
    if n_products == 0 and n_variants == 0:
        rep.warnings.append(
            "Legacy collections `products` and `product_variants` are EMPTY — nothing to migrate (NO-OP).")
        return rep

    # ── Phase 1: products → rahaza_models ────────────────────────────────────
    product_to_model = {}  # product.id -> resolved rahaza_models doc
    products = await db.products.find({}, {"_id": 0}).to_list(100000)
    for p in products:
        pid = p.get("id")
        raw_code = (p.get("product_code") or p.get("code") or "").strip().upper()
        if not raw_code:
            # derive from name; last resort from id
            base = (p.get("product_name") or "MODEL").strip().upper().replace(" ", "-")
            raw_code = base[:20] or f"MDL-{(pid or _uid())[:8].upper()}"
        # idempotent: reuse existing model with same code
        existing = await db.rahaza_models.find_one({"code": raw_code})
        if existing:
            product_to_model[pid] = existing
            rep.models_skipped.append({"code": raw_code, "name": p.get("product_name"), "reason": "code exists"})
            continue
        model_doc = {
            "id": pid or _uid(),
            "code": raw_code,
            "name": (p.get("product_name") or raw_code),
            "category": p.get("category") or "Sweater",
            "yarn_kg_per_pcs": float(p.get("yarn_kg_per_pcs") or 0),
            "bundle_size": int(p.get("bundle_size") or 30),
            "description": p.get("description") or "",
            "sop_steps": [], "reference_videos": [], "reference_images": [],
            "active": (p.get("status") != "inactive"),
            "created_at": p.get("created_at") or _now(),
            "updated_at": _now(),
            "_migrated_from": "products",
            "_source_id": pid,
            "_legacy_prices": {
                "cmt_price": p.get("cmt_price"),
                "selling_price": p.get("selling_price"),
            },
        }
        if execute:
            await db.rahaza_models.insert_one(dict(model_doc))
        product_to_model[pid] = model_doc
        rep.models_created.append({"code": raw_code, "name": model_doc["name"], "id": model_doc["id"]})

    # ── Phase 2: product_variants → rahaza_model_variants ────────────────────
    color_cache: dict = {}
    size_cache: dict = {}
    # track SKUs we plan to create within THIS run (dry-run consistency)
    planned_skus = set()
    variants = await db.product_variants.find({}, {"_id": 0}).to_list(500000)
    for v in variants:
        src_pid = v.get("product_id")
        model = product_to_model.get(src_pid)
        if not model:
            # try resolve directly (product may pre-exist as a model by code)
            rep.warnings.append({
                "variant_id": v.get("id"), "sku": v.get("sku"),
                "reason": f"no model mapping for product_id={src_pid} — variant skipped",
            })
            rep.variants_skipped.append({"sku": v.get("sku"), "reason": "orphan (no model)"})
            continue

        color = await _ensure_color(db, rep, v.get("color") or "", color_cache)
        size = await _ensure_size(db, rep, v.get("size") or "", size_cache)

        sku = (v.get("sku") or "").strip().upper() or _make_sku(
            model.get("code"), color.get("code"), size.get("code"))

        # idempotency: existing active variant with same SKU or same combo
        dup_sku = await db.rahaza_model_variants.find_one({"sku": sku, "active": True})
        dup_combo = await db.rahaza_model_variants.find_one({
            "model_id": model.get("id"), "size_id": size.get("id"),
            "color_id": color.get("id"), "active": True,
        })
        if dup_sku or dup_combo or sku in planned_skus:
            rep.variants_skipped.append({
                "sku": sku, "reason": "already exists" if (dup_sku or dup_combo) else "duplicate in source",
            })
            continue

        planned_skus.add(sku)
        var_doc = {
            "id": v.get("id") or _uid(),
            "model_id": model.get("id"), "model_code": model.get("code"), "model_name": model.get("name"),
            "size_id": size.get("id"), "size_code": size.get("code"),
            "color_id": color.get("id"), "color_code": color.get("code"), "color_name": color.get("name"),
            "color_hex": color.get("hex"),
            "sku": sku, "barcode": v.get("barcode") or "", "notes": v.get("notes") or "",
            "active": True,
            "created_at": v.get("created_at") or _now(), "updated_at": _now(),
            "_migrated_from": "product_variants", "_source_id": v.get("id"),
        }
        if execute:
            await db.rahaza_model_variants.insert_one(dict(var_doc))
        rep.variants_created.append({"sku": sku, "model_code": model.get("code")})

    return rep


def _print_human(rep: Report):
    s = rep.to_dict()["summary"]
    print("=" * 78)
    print(f"  MIGRATION products/product_variants → rahaza_*   [{'EXECUTE' if rep.execute else 'DRY-RUN'}]")
    print("=" * 78)
    print(f"  rahaza_models         created: {s['models_created']:>4}   (skipped/exists: {s['models_skipped']})")
    print(f"  rahaza_colors         created: {s['colors_created']:>4}   (reused: {s['colors_reused']})")
    print(f"  rahaza_sizes          created: {s['sizes_created']:>4}   (reused: {s['sizes_reused']})")
    print(f"  rahaza_model_variants created: {s['variants_created']:>4}   (skipped: {s['variants_skipped']})")
    if rep.warnings:
        print(f"  warnings: {s['warnings']}")
        for w in rep.warnings[:20]:
            print(f"    ! {w}")
    if not rep.execute:
        print("-" * 78)
        print("  DRY-RUN — no data written. Re-run with --execute to apply.")
    print("=" * 78)


async def _amain():
    ap = argparse.ArgumentParser(description="Migrate legacy products/product_variants → rahaza_* SSOT")
    ap.add_argument("--execute", action="store_true", help="Apply changes (default: dry-run)")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON report")
    args = ap.parse_args()

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    rep = await migrate(db, execute=args.execute)

    if args.json:
        print(json.dumps(rep.to_dict(), default=str, indent=2))
    else:
        _print_human(rep)

    client.close()
    # Exit 0 always (dry-run/no-op is success). Non-zero only on unexpected error.


if __name__ == "__main__":
    asyncio.run(_amain())
