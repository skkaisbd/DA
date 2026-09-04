"""routes/rnd_product_viewer.py — **VIEWER PRODUK HASIL RND (katalog internal)**.

KENAPA LAYAR/ENDPOINT INI ADA (sesi #34)
----------------------------------------
Pemilik: "di portal RND tidak memperlihatkan viewer product internal atau yang
sudah dibuat oleh RND … dibutuhkan viewer seperti catalog, sesuai dengan hasil
final RND menjadi master data … perlihatkan juga apakah ini sudah di-sync dengan
catalog marketing … pastikan SSOT master data ini tidak broken dan link ke
produksinya juga benar."

Yang diukur sebelum menulis endpoint ini:
* Master barang jadi (`rahaza_materials.type='fg'`) berisi **321 SKU**, tetapi
  RnD hanya punya layar per-style; tidak ada satu pun layar yang memperlihatkan
  "produk final" sebagai katalog.
* Item katalog marketing (`marketing_catalog_items`) menunjuk master lewat
  `fg_material_id`/`fg_product_id` — jadi status "sudah di-sync" BISA dihitung,
  belum pernah ditampilkan.

Endpoint ini **tidak memperbaiki data**; ia memperlihatkan apa adanya, termasuk
yang RUSAK. Tiap SKU membawa daftar `gaps[]`: BOM belum ada, HPP masih perkiraan
BOM (belum ada batch nyata), belum masuk katalog marketing, belum pernah
diproduksi, harga jual belum diisi. Itu sebabnya viewer ini juga menjadi
pemeriksa SSOT: yang tidak tersambung TERLIHAT, bukan diam-diam nol.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from auth import require_auth, serialize_doc
from database import get_db

router = APIRouter(prefix="/api/rnd/product-viewer", tags=["rnd-product-viewer"])


def _f(v, d=0.0) -> float:
    try:
        return float(v if v not in (None, "") else d)
    except (TypeError, ValueError):
        return float(d)


@router.get("")
async def list_products(request: Request,
                        q: str = Query("", description="cari SKU / nama / model"),
                        category: str = Query(""),
                        sync: str = Query("", description="synced | not_synced"),
                        sort: str = Query("", description="margin_asc | margin_desc"),
                        limit: int = Query(60, ge=1, le=200),
                        offset: int = Query(0, ge=0)):
    """Katalog produk final RnD + status sambungannya ke marketing & produksi."""
    await require_auth(request)
    db = get_db()

    query: dict = {"type": "fg", "active": {"$ne": False}}
    if q:
        query["$or"] = [{"code": {"$regex": q, "$options": "i"}},
                        {"name": {"$regex": q, "$options": "i"}},
                        {"model_name": {"$regex": q, "$options": "i"}},
                        {"model_code": {"$regex": q, "$options": "i"}}]
    if category:
        query["category_id"] = category

    total = await db.rahaza_materials.count_documents(query)
    mats = await db.rahaza_materials.find(query, {"_id": 0}).sort(
        [("model_name", 1), ("size_code", 1)]).skip(offset).limit(limit).to_list(limit)
    if not mats:
        return {"ok": True, "data": [], "total": total,
                "summary": {"total": total, "synced": 0, "no_bom": 0, "never_produced": 0}}

    ids = [m["id"] for m in mats]
    codes = [m.get("code") for m in mats if m.get("code")]
    model_ids = list({m.get("model_id") for m in mats if m.get("model_id")})

    cat_items = await db.marketing_catalog_items.find(
        {"$or": [{"fg_material_id": {"$in": ids}}, {"fg_product_id": {"$in": ids}},
                 {"sku": {"$in": codes}}, {"variant_sku": {"$in": codes}}]},
        {"_id": 0, "id": 1, "account_id": 1, "sku": 1, "variant_sku": 1, "name": 1,
         "fg_material_id": 1, "fg_product_id": 1, "harga_jual": 1, "unit_price": 1,
         "publish_state": 1, "is_active": 1, "images": 1}).to_list(3000)
    accounts = {a["id"]: a.get("account_name") for a in await db.marketing_platform_accounts.find(
        {}, {"_id": 0, "id": 1, "account_name": 1}).to_list(300)}

    boms = await db.rahaza_boms.find(
        {"model_id": {"$in": model_ids}}, {"_id": 0, "model_id": 1, "id": 1}).to_list(1000)
    bom_models = {b["model_id"] for b in boms}
    models = {m["id"]: m for m in await db.rahaza_models.find(
        {"id": {"$in": model_ids}}, {"_id": 0, "id": 1, "name": 1, "code": 1, "category_name": 1,
                                     "images": 1, "image_url": 1, "rnd_style_id": 1,
                                     "harga_original": 1, "created_by": 1, "created_at": 1}
    ).to_list(1000)}

    po_items = await db.po_items.find(
        {"$or": [{"sku": {"$in": codes}}, {"model_id": {"$in": model_ids}}]},
        {"_id": 0, "sku": 1, "model_id": 1, "qty": 1, "cmt_price_snapshot": 1,
         "po_number": 1}).to_list(5000)
    prod_by_sku: dict = {}
    for it in po_items:
        slot = prod_by_sku.setdefault(it.get("sku") or f"model::{it.get('model_id')}",
                                      {"qty": 0, "pos": set(), "sewing_filled": 0, "lines": 0})
        slot["qty"] += int(_f(it.get("qty")))
        slot["lines"] += 1
        if it.get("po_number"):
            slot["pos"].add(it["po_number"])
        if _f(it.get("cmt_price_snapshot")) > 0:
            slot["sewing_filled"] += 1

    layers = await db.fg_cost_layers.find(
        {"material_id": {"$in": ids}},
        {"_id": 0, "material_id": 1, "qty_remaining": 1, "unit_cost": 1}).to_list(5000)
    layer_by_mat: dict = {}
    for ly in layers:
        s = layer_by_mat.setdefault(ly["material_id"], {"qty": 0.0, "val": 0.0, "n": 0})
        s["n"] += 1
        rem = _f(ly.get("qty_remaining"))
        if rem > 0:
            s["qty"] += rem
            s["val"] += rem * _f(ly.get("unit_cost"))

    stock = await db.rahaza_stock.find({"material_id": {"$in": ids}},
                                       {"_id": 0, "material_id": 1, "qty": 1}).to_list(5000)
    stock_by_mat: dict = {}
    for s in stock:
        stock_by_mat[s["material_id"]] = stock_by_mat.get(s["material_id"], 0.0) + _f(s.get("qty"))

    out = []
    for m in mats:
        model = models.get(m.get("model_id") or "") or {}
        mine = [c for c in cat_items
                if c.get("fg_material_id") == m["id"] or c.get("fg_product_id") == m["id"]
                or c.get("sku") == m.get("code") or c.get("variant_sku") == m.get("code")]
        prod = prod_by_sku.get(m.get("code") or "") or \
            prod_by_sku.get(f"model::{m.get('model_id')}") or {}
        lay = layer_by_mat.get(m["id"]) or {}
        hpp_fifo = round(lay["val"] / lay["qty"], 2) if lay.get("qty") else 0.0
        images = (model.get("images") or [])
        if model.get("image_url"):
            images = [model["image_url"]] + list(images)
        if not images:
            for c in mine:
                if c.get("images"):
                    images = c["images"]
                    break
        sell = _f(model.get("harga_original")) or max(
            [_f(c.get("harga_jual")) or _f(c.get("unit_price")) for c in mine] or [0])

        gaps = []
        if m.get("model_id") not in bom_models:
            gaps.append("BOM model ini belum ada — HPP bahan tidak bisa dihitung")
        if not lay:
            gaps.append("belum ada batch produksi masuk gudang — HPP masih perkiraan BOM, "
                        "bukan biaya nyata")
        elif prod.get("lines") and prod.get("sewing_filled", 0) < prod.get("lines", 0):
            gaps.append(f"{prod['lines'] - prod['sewing_filled']} baris SPK belum diisi biaya jahit")
        if not mine:
            gaps.append("belum masuk katalog marketing — tidak bisa dijual/di-assign ke kreator")
        if not sell:
            gaps.append("harga jual belum diisi")
        if not prod.get("qty"):
            gaps.append("belum pernah masuk SPK produksi")
        if not images:
            gaps.append("belum ada foto produk")

        out.append({
            "material_id": m["id"], "sku": m.get("code"), "name": m.get("name"),
            "model_id": m.get("model_id"), "model_code": m.get("model_code"),
            "model_name": m.get("model_name"),
            "size": m.get("size_code"), "color": m.get("color_name") or m.get("color"),
            "color_hex": m.get("color_hex"), "unit": m.get("unit"),
            "category": m.get("category_name") or m.get("category"),
            "images": images[:6],
            "rnd": {"style_id": model.get("rnd_style_id") or "",
                    "created_by": model.get("created_by") or "",
                    "created_at": model.get("created_at")},
            "hpp": {"master": _f(m.get("hpp")), "source": m.get("hpp_source") or "none",
                    "fifo_avg": hpp_fifo, "layer_count": lay.get("n", 0),
                    "qty_on_layers": int(lay.get("qty", 0))},
            "price": {"selling": sell,
                      "margin": round(sell - (hpp_fifo or _f(m.get("hpp"))), 2) if sell else 0.0},
            "stock_qty": int(stock_by_mat.get(m["id"], 0)),
            "marketing_sync": {
                "synced": bool(mine), "item_count": len(mine),
                "accounts": [{"account_id": c.get("account_id"),
                              "account_name": accounts.get(c.get("account_id"), "—"),
                              "publish_state": c.get("publish_state") or "",
                              "active": c.get("is_active", True)} for c in mine[:10]],
            },
            "production": {
                "spk_lines": prod.get("lines", 0), "qty_ordered": prod.get("qty", 0),
                "po_numbers": sorted(prod.get("pos", []))[:6],
                "sewing_rate_filled": prod.get("sewing_filled", 0),
                "bom_ready": m.get("model_id") in bom_models,
            },
            "gaps": gaps,
            "ssot_ok": not gaps,
        })

    # PAPAN MARGIN (sesi #34) — urut dari margin PALING TIPIS supaya produk yang
    # merugikan muncul lebih dulu. Produk yang harga jual atau HPP-nya belum ada
    # TIDAK dianggap bermargin 0 (itu akan menutupi masalahnya); ia ditaruh di
    # akhir dengan sebab yang sudah tertulis di `gaps`.
    if sort in ("margin_asc", "margin_desc"):
        def _key(r):
            sell = r["price"]["selling"]
            hpp = r["hpp"]["fifo_avg"] or r["hpp"]["master"]
            known = bool(sell) and bool(hpp)
            return (0 if known else 1, r["price"]["margin"] if known else 0)
        out.sort(key=_key, reverse=(sort == "margin_desc"))
        if sort == "margin_desc":
            out.sort(key=lambda r: 0 if (r["price"]["selling"] and
                                         (r["hpp"]["fifo_avg"] or r["hpp"]["master"])) else 1)

    priced = [r for r in out if r["price"]["selling"] and (r["hpp"]["fifo_avg"] or r["hpp"]["master"])]
    return {
        "ok": True, "total": total, "data": serialize_doc(out),
        "summary": {
            "total": total, "shown": len(out),
            "synced": sum(1 for r in out if r["marketing_sync"]["synced"]),
            "no_bom": sum(1 for r in out if not r["production"]["bom_ready"]),
            "never_produced": sum(1 for r in out if not r["production"]["qty_ordered"]),
            "hpp_real": sum(1 for r in out if r["hpp"]["layer_count"] > 0),
            "ssot_ok": sum(1 for r in out if r["ssot_ok"]),
            # Papan margin: hanya dihitung dari produk yang HPP **dan** harga jualnya
            # sama-sama ada — sisanya disebut apa adanya, bukan dianggap margin 0.
            "margin_measurable": len(priced),
            "margin_unmeasurable": len(out) - len(priced),
            "margin_negative": sum(1 for r in priced if r["price"]["margin"] < 0),
            "margin_thin": sum(1 for r in priced
                               if 0 <= r["price"]["margin"] < 0.15 * r["price"]["selling"]),
            "margin_avg_pct": (round(sum(r["price"]["margin"] / r["price"]["selling"] * 100
                                         for r in priced) / len(priced), 1) if priced else 0.0),
        },
    }


@router.get("/{material_id}")
async def product_detail(material_id: str, request: Request):
    """Detail satu produk final — dipakai panel kanan viewer."""
    await require_auth(request)
    db = get_db()
    mat = await db.rahaza_materials.find_one({"id": material_id, "type": "fg"}, {"_id": 0})
    if not mat:
        raise HTTPException(404, "Produk barang jadi tidak ditemukan di master")
    from core import fg_cost_layers as fcl
    snap = await fcl.hpp_snapshot(db, material_id)
    cat = await db.marketing_catalog_items.find(
        {"$or": [{"fg_material_id": material_id}, {"fg_product_id": material_id},
                 {"sku": mat.get("code")}]}, {"_id": 0}).to_list(50)
    model = await db.rahaza_models.find_one({"id": mat.get("model_id")}, {"_id": 0}) or {}
    bom = await db.rahaza_boms.find_one({"model_id": mat.get("model_id")}, {"_id": 0}) or {}
    return {"ok": True, "material": serialize_doc(mat), "model": serialize_doc(model),
            "hpp_layers": serialize_doc(snap), "catalog_items": serialize_doc(cat),
            "bom": {"exists": bool(bom), "id": bom.get("id", ""),
                    "line_count": len(bom.get("items") or bom.get("lines") or [])}}
