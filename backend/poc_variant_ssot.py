"""
POC — Canonical Variant/FG SSOT chain (run standalone).

Validates end-to-end:
  A. Master: model → generate variants → FG auto-created (GAP-4) with canonical SKU
     {MODEL}-{COLOR}-{SIZE} incl. color (BUG-1 identity) + explicit linkage fields.
  B. Produksi internal → Gudang: canonical FG receipt (pending inbound) → scan-in →
     rahaza_material_stock incremented on FG code==sku (BUG-1 active-flow).
  C. Marketing Toko: catalog item from FG (by variant SKU) reads correct stock.
  D. RnD promote (GAP-3/GAP-6): style+variants+techpack → master model + canonical
     variants + FG + sop_steps propagated from techpack.

Usage:  cd /app/backend && python poc_variant_ssot.py
"""
import asyncio
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

BASE = "http://localhost:8001"
DBURL = "mongodb://localhost:27017"
DBNAME = "test_database"
PFX = "POCDA"  # prefix for all POC artifacts (easy cleanup)

_results = []


def check(name, cond, detail=""):
    _results.append(("PASS" if cond else "FAIL", name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  → {detail}" if detail else ""))
    return bool(cond)


def now():
    return datetime.now(timezone.utc)


async def cleanup(db):
    await db.rahaza_models.delete_many({"code": {"$regex": f"^{PFX}"}})
    await db.rahaza_model_variants.delete_many({"model_code": {"$regex": f"^{PFX}"}})
    await db.rahaza_materials.delete_many({"code": {"$regex": f"^{PFX}"}})
    await db.rahaza_material_stock.delete_many({})  # POC-only DB safe; only masters seeded
    await db.wh_pending_movements.delete_many({"source_type": {"$in": ["poc", "production_internal", "production_packing"]}})
    await db.dewi_rnd_styles.delete_many({"style_code": {"$regex": f"^{PFX}"}})
    await db.dewi_rnd_variants.delete_many({"style_code": {"$regex": f"^{PFX}"}})
    await db.dewi_rnd_tech_packs.delete_many({"style_id": {"$regex": f"^{PFX}"}})
    await db.marketing_catalogs.delete_many({"id": {"$regex": f"^{PFX}"}})
    await db.marketing_catalog_items.delete_many({"sku": {"$regex": f"^{PFX}"}})


async def main():
    db = AsyncIOMotorClient(DBURL)[DBNAME]
    await cleanup(db)

    async with httpx.AsyncClient(base_url=BASE, timeout=40) as cx:
        # ── login ──
        r = await cx.post("/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
        token = r.json().get("token")
        if not token:
            print("LOGIN FAILED", r.text); sys.exit(1)
        H = {"Authorization": f"Bearer {token}"}

        # ── ensure a warehouse location (scan-in needs one) ──
        if not await db.rahaza_locations.find_one({"active": True}):
            await db.rahaza_locations.insert_one({"id": str(uuid.uuid4()), "code": "WH-POC",
                                                  "name": "Gudang POC", "active": True})
            print("· seeded rahaza_locations WH-POC")

        # ══════════════ SCENARIO A: Master + GAP-4 + canonical SKU ══════════════
        colors = (await cx.get("/api/rahaza/colors", headers=H)).json()
        cmap = {c["code"]: c for c in colors}
        check("A0 colors master seeded", "PTH" in cmap and "HTM" in cmap, f"{len(colors)} warna")

        sizes = (await cx.get("/api/rahaza/sizes", headers=H)).json()
        sizes = sizes if isinstance(sizes, list) else sizes.get("data", [])
        smap = {s["code"]: s for s in sizes}
        check("A1 size ALLSIZE seeded (GAP-5)", "ALLSIZE" in smap, f"sizes={list(smap)}")

        mcode = f"{PFX}01"
        rm = await cx.post("/api/rahaza/models", headers=H,
                           json={"code": mcode, "name": "POC Blouse Jenifer", "category": "BLOUSE"})
        model = rm.json()
        check("A2 create model", rm.status_code in (200, 201) and model.get("code") == mcode, mcode)

        gv = await cx.post(f"/api/rahaza/models/{model['id']}/variants/generate", headers=H,
                           json={"color_ids": [cmap["PTH"]["id"], cmap["HTM"]["id"]],
                                 "size_ids": [smap["M"]["id"]]})
        gvj = gv.json()
        check("A3 generate variants (2 warna × M)", gvj.get("created_count") == 2, str(gvj.get("created")))

        variants = await db.rahaza_model_variants.find({"model_id": model["id"]}, {"_id": 0}).to_list(50)
        skus = sorted(v["sku"] for v in variants)
        expect = sorted([f"{mcode}-PTH-M", f"{mcode}-HTM-M"])
        check("A4 canonical SKU incl. WARNA (BUG-1 identity)", skus == expect, f"{skus}")

        fg_htm = await db.rahaza_materials.find_one({"type": "fg", "code": f"{mcode}-HTM-M"}, {"_id": 0})
        check("A5 FG auto-created on generate (GAP-4)", fg_htm is not None, f"code={mcode}-HTM-M")
        check("A6 FG carries explicit linkage (no code-parse)",
              bool(fg_htm) and fg_htm.get("color_code") == "HTM" and fg_htm.get("size_code") == "M"
              and fg_htm.get("model_id") == model["id"] and fg_htm.get("variant_id"),
              f"color_code={fg_htm.get('color_code') if fg_htm else None}")

        # ══════════════ SCENARIO B: Produksi internal → Gudang (BUG-1) ══════════
        from utils.variant_ssot import resolve_variant, create_fg_pending_inbound_for_variant
        variant_htm = await resolve_variant(db, sku=f"{mcode}-HTM-M")
        res = await create_fg_pending_inbound_for_variant(
            db, variant_htm, 25, source_type="poc", source_id=f"poc-{uuid.uuid4()}",
            source_ref="POC-JOB-1", user={"name": "poc"})
        pend = res.get("pending")
        check("B1 FG pending-inbound created (per-variant)",
              pend is not None and pend.get("material_code") == f"{mcode}-HTM-M",
              f"ref={pend.get('ref_number') if pend else None}")

        # scan-in → stock += 25
        mv = await db.wh_pending_movements.find_one({"material_code": f"{mcode}-HTM-M", "status": "pending"}, {"_id": 0})
        si = await cx.post(f"/api/wms/pending/{mv['id']}/scan-in", headers=H, json={"scanned_qty": 25})
        check("B2 scan-in success", si.status_code == 200, si.text[:120])

        loc = await db.rahaza_locations.find_one({"active": True}, {"_id": 0})
        stock = await db.rahaza_material_stock.find_one({"material_id": fg_htm["id"], "location_id": loc["id"]}, {"_id": 0})
        check("B3 gudang stock incremented on FG code==sku", bool(stock) and float(stock.get("qty", 0)) == 25.0,
              f"qty={stock.get('qty') if stock else None}")

        # ══════════════ SCENARIO C: Marketing Toko integration ══════════════════
        cat_id = f"{PFX}-CAT-{uuid.uuid4().hex[:6]}"
        await db.marketing_catalogs.insert_one({
            "id": cat_id, "name": "POC Toko Online", "platform": "shopee",
            "active": True, "created_at": now(), "updated_at": now(),
        })
        ff = await cx.post(f"/api/marketing/catalogs/{cat_id}/items/from-fg", headers=H,
                           json={"fg_material_id": fg_htm["id"], "price": 150000})
        ffj = ff.json() if ff.status_code in (200, 201) else {}
        check("C1 marketing item from FG (variant SKU)", ff.status_code in (200, 201),
              f"http={ff.status_code} {ff.text[:120]}")
        item = await db.marketing_catalog_items.find_one({"catalog_id": cat_id, "fg_material_id": fg_htm["id"]}, {"_id": 0})
        check("C2 catalog item links FG & snapshots stock=25",
              bool(item) and item.get("sku") == f"{mcode}-HTM-M" and float(item.get("stock_quantity", 0)) == 25.0,
              f"sku={item.get('sku') if item else None} stock={item.get('stock_quantity') if item else None}")

        # ══════════════ SCENARIO D: RnD promote (GAP-3 + GAP-6) ══════════════════
        style_id = f"{PFX}-STY-{uuid.uuid4().hex[:6]}"
        scode = f"{PFX}RND1"
        await db.dewi_rnd_styles.insert_one({
            "id": style_id, "style_code": scode, "style_name": "POC RnD Dress Cleo",
            "category": "DRESS", "buyer": "DA", "fabric_type": "RAYON", "season": "2026",
            "description": "POC promote", "rnd_type": "internal_product",
            "status": "approved_for_launch", "design_images": [],
            "created_at": now(), "updated_at": now(),
        })
        # RnD variant granularity: {color, sizes:[...]}
        await db.dewi_rnd_variants.insert_one({
            "id": str(uuid.uuid4()), "style_id": style_id, "style_code": scode,
            "color": "Merah", "color_code": "MRH", "sizes": ["M", "ALLSIZE"],
            "status": "approved", "created_at": now(),
        })
        # tech-pack with multi-line construction (→ sop_steps) + measurements
        await db.dewi_rnd_tech_packs.insert_one({
            "id": str(uuid.uuid4()), "style_id": style_id, "version": 1, "is_latest": True,
            "construction_notes": "Jahit kerut bahu agar puffy\nOverlock keliling badan\nPasang 3 kancing lubang empat",
            "stitch_type": "overlock", "seam_allowance_mm": 10,
            "measurements": [{"point": "LD", "M": "110", "L": "115"}],
            "size_range": "M-XL", "bom_items": [{"material": "RAYON", "qty": 2, "unit": "m"}],
            "created_at": now(),
        })
        pr = await cx.post(f"/api/dewi/rnd/styles/{style_id}/promote-to-production", headers=H, json={})
        prj = pr.json() if pr.status_code == 200 else {}
        check("D1 promote OK", pr.status_code == 200, f"http={pr.status_code} {pr.text[:160]}")

        model2 = await db.rahaza_models.find_one({"rnd_style_id": style_id}, {"_id": 0})
        check("D2 master model created from style", bool(model2), f"code={model2.get('code') if model2 else None}")
        mv2 = await db.rahaza_model_variants.find({"model_id": (model2 or {}).get("id")}, {"_id": 0}).to_list(50)
        skus2 = sorted(v["sku"] for v in mv2)
        exp2 = sorted([f"{scode}-MRH-M", f"{scode}-MRH-ALLSIZE"])
        check("D3 canonical variants generated from RnD (GAP-3)", skus2 == exp2, f"{skus2}")
        fg2 = await db.rahaza_materials.count_documents({"type": "fg", "code": {"$in": exp2}})
        check("D4 FG created for promoted variants", fg2 == 2, f"fg_count={fg2}")
        check("D5 techpack construction → model.sop_steps (GAP-6)",
              bool(model2) and len(model2.get("sop_steps") or []) == 3,
              f"steps={len(model2.get('sop_steps') or []) if model2 else 0}")

    # ── summary ──
    fails = [r for r in _results if r[0] == "FAIL"]
    print("\n" + "=" * 60)
    print(f"POC RESULT: {len(_results) - len(fails)}/{len(_results)} passed")
    if fails:
        print("FAILED:")
        for _, n, d in fails:
            print(f"  - {n}  {d}")
        sys.exit(1)
    print("ALL POC CHECKS PASSED ✅")


if __name__ == "__main__":
    asyncio.run(main())
