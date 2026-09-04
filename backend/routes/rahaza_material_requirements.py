"""
PT Rahaza — Master Product Fase 5: Laporan Kebutuhan Material (MRP-lite).

Agregasi kebutuhan material lintas banyak baris produksi (model × size × qty).
Berbeda dari `POST /api/rahaza/boms/{id}/requirements` (single BOM, single size),
endpoint ini menjumlahkan kebutuhan dari BANYAK item — cocok untuk perencanaan
pembelian (procurement) untuk satu PO produksi internal atau sekumpulan order.

Endpoint (prefix /api/rahaza):
  POST /material-requirements
    Body (salah satu sumber):
      A. { "lines": [ {model_id, size_id, qty_pcs}, ... ] }        # builder manual
      B. { "po_id": "<production_pos.id>" }                         # dari PO internal
    Opsi:
      rounding: "none" | "ceil" | "floor"   (default none) — dibulatkan pada TOTAL agregat
      include_stock: bool (default True)     — sertakan on-hand & kekurangan dari rahaza_material_stock

    Response:
      {
        source: "lines" | "po",
        po: { id, po_number, business_type } | null,
        lines_resolved: [ {model_id, model_code, size_id, size_code, qty_pcs, bom_id, version, material_count} ],
        lines_without_bom: [ {model_id, model_code, size_id, size_code, qty_pcs, reason} ],
        aggregated: [ {material_id, code, name, category, category_name, material_type, is_kglike,
                       unit, total_required, onhand, reserved, available, shortfall} ],
        totals: { grand_qty_pcs, total_material_lines, total_yarn_kg, total_shortfall_lines },
        warnings: [str]
      }

SSOT: BOM materials via routes.rahaza_bom.get_bom_materials (skema materials[] terunifikasi).
Stok fisik via core.stock_schema (read_qty/read_reserved) atas rahaza_material_stock.
"""
from __future__ import annotations

import math
from fastapi import APIRouter, Request, HTTPException

from database import get_db
from auth import require_auth, serialize_doc
from routes.rahaza_bom import get_bom_materials, _is_kglike
from core import bom_uom  # 2026-08-02: konversi satuan baris BOM → satuan dasar
from core.stock_schema import read_qty, read_reserved
from core import material_fields  # FASE 6.6-B: SSOT nama field + alias legacy yarn_*

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-material-requirements"])


def _round(v: float, kglike: bool, mode: str) -> float:
    if mode == "ceil":
        return math.ceil(v * 1000) / 1000 if kglike else float(math.ceil(v))
    if mode == "floor":
        return math.floor(v * 1000) / 1000 if kglike else float(math.floor(v))
    return round(v, 4)


async def _find_active_bom(db, model_id: str, size_id: str):
    """Cari BOM aktif utk (model_id, size_id). Prioritas is_active True; fallback versi tertinggi."""
    if not model_id or not size_id:
        return None
    bom = await db.rahaza_boms.find_one(
        {"model_id": model_id, "size_id": size_id, "active": True, "is_active": True}, {"_id": 0})
    if bom:
        return bom
    # fallback: BOM aktif apa pun utk kombinasi ini (versi tertinggi)
    cands = await db.rahaza_boms.find(
        {"model_id": model_id, "size_id": size_id, "active": True}, {"_id": 0}
    ).sort("version", -1).to_list(50)
    return cands[0] if cands else None


async def _stock_for_material(db, material_id: str):
    """Total on-hand / reserved / available utk sebuah material lintas lokasi."""
    if not material_id:
        return 0.0, 0.0, 0.0
    rows = await db.rahaza_material_stock.find({"material_id": material_id}, {"_id": 0}).to_list(2000)
    onhand = sum(read_qty(s) for s in rows)
    reserved = sum(read_reserved(s) for s in rows)
    available = max(0.0, onhand - reserved)
    return round(onhand, 4), round(reserved, 4), round(available, 4)


async def _get_costing_settings(db):
    s = await db.rahaza_costing_settings.find_one({"id": "GLOBAL"}, {"_id": 0}) or {}
    return {
        # FASE 6.6-B: baca kanonik `default_material_cost_per_kg` dulu, fallback legacy
        "default_yarn": float(material_fields.read_field(s, "default_material_cost_per_kg", 0) or 0),
        "default_acc": float(s.get("default_accessory_cost_per_unit") or 0),
    }


async def _resolve_unit_cost(db, rec: dict, settings: dict):
    """Resolusi harga satuan material (mirror logika HPP):
      1. dari master rahaza_materials (by material_id, lalu by code) → `unit_cost`
      2. fallback costing-settings: default_yarn_cost_per_kg (kain/benang) / default_accessory_cost_per_unit
    Return (unit_cost: float, source: 'material'|'default'|'none').
    """
    mat = None
    if rec.get("material_id"):
        mat = await db.rahaza_materials.find_one({"id": rec["material_id"]}, {"_id": 0, "unit_cost": 1})
    if not mat and rec.get("code"):
        mat = await db.rahaza_materials.find_one({"code": rec["code"]}, {"_id": 0, "unit_cost": 1})
    unit_cost = float((mat or {}).get("unit_cost") or 0)
    if unit_cost > 0:
        return round(unit_cost, 2), "material"
    fallback = settings["default_yarn"] if rec.get("is_kglike") else settings["default_acc"]
    if fallback > 0:
        return round(float(fallback), 2), "default"
    return 0.0, "none"


@router.post("/material-requirements")
async def aggregate_material_requirements(request: Request):
    await require_auth(request)
    db = get_db()
    body = await request.json()

    rounding = body.get("rounding", "none")
    if rounding not in ("none", "ceil", "floor"):
        rounding = "none"
    include_stock = bool(body.get("include_stock", True))
    include_cost = bool(body.get("include_cost", True))


    warnings: list[str] = []
    source = "lines"
    po_meta = None

    # ── Build the list of production lines: {model_id, size_id, qty_pcs} ──
    raw_lines: list[dict] = []

    po_id = body.get("po_id")
    if po_id:
        source = "po"
        po = await db.production_pos.find_one({"id": po_id}, {"_id": 0})
        if not po:
            raise HTTPException(404, "PO tidak ditemukan")
        po_meta = {"id": po.get("id"), "po_number": po.get("po_number"),
                   "business_type": po.get("business_type")}
        items = await db.po_items.find({"po_id": po_id}, {"_id": 0}).to_list(5000)
        if not items:
            warnings.append("PO tidak memiliki item.")
        for it in items:
            raw_lines.append({
                "model_id": it.get("model_id"),
                "size_id": it.get("size_id"),
                "qty_pcs": float(it.get("qty") or 0),
                "_label": it.get("product_name") or it.get("sku") or "",
            })
    else:
        lines_in = body.get("lines") or []
        if not isinstance(lines_in, list) or not lines_in:
            raise HTTPException(400, "Sertakan `lines` (daftar {model_id,size_id,qty_pcs}) atau `po_id`.")
        for ln in lines_in:
            raw_lines.append({
                "model_id": ln.get("model_id"),
                "size_id": ln.get("size_id"),
                "qty_pcs": float(ln.get("qty_pcs") or 0),
                "_label": "",
            })

    # ── Explode each line via its BOM and aggregate ──
    agg: dict = {}          # key -> aggregate record (raw sums)
    lines_resolved = []
    lines_without_bom = []
    uom_notices = []   # peringatan satuan yang perlu dibereskan di master/BOM
    grand_qty_pcs = 0.0

    for ln in raw_lines:
        model_id = ln.get("model_id")
        size_id = ln.get("size_id")
        qty_pcs = float(ln.get("qty_pcs") or 0)
        grand_qty_pcs += qty_pcs

        # resolve model/size codes (for display) — best effort
        model = await db.rahaza_models.find_one({"id": model_id}, {"_id": 0, "code": 1, "name": 1}) if model_id else None
        size = await db.rahaza_sizes.find_one({"id": size_id}, {"_id": 0, "code": 1}) if size_id else None
        model_code = (model or {}).get("code")
        size_code = (size or {}).get("code")

        if qty_pcs <= 0:
            lines_without_bom.append({
                "model_id": model_id, "model_code": model_code, "size_id": size_id,
                "size_code": size_code, "qty_pcs": qty_pcs, "reason": "qty 0",
            })
            continue

        bom = await _find_active_bom(db, model_id, size_id)
        if not bom:
            lines_without_bom.append({
                "model_id": model_id, "model_code": model_code, "size_id": size_id,
                "size_code": size_code, "qty_pcs": qty_pcs,
                "reason": "BOM aktif tidak ditemukan utk model+size ini",
                "label": ln.get("_label", ""),
            })
            continue

        # 2026-08-02 · SATUAN: qty BOM diubah ke SATUAN DASAR dulu (INV-UOM-2:
        # stok & harga selalu satuan dasar). Tanpa ini, baris BOM "250 gram"
        # dibandingkan dengan stok "kg" dan biaya dihitung 500× lipat.
        mats, uom_warnings = await bom_uom.ensure_uom(db, bom)
        for w in uom_warnings:
            if w not in uom_notices:
                uom_notices.append(w)
        lines_resolved.append({
            "model_id": model_id, "model_code": bom.get("model_code") or model_code,
            "size_id": size_id, "size_code": bom.get("size_code") or size_code,
            "qty_pcs": qty_pcs, "bom_id": bom.get("id"), "version": bom.get("version"),
            "material_count": len(mats),
            "label": ln.get("_label", ""),
        })

        for m in mats:
            key = m.get("material_id") or (m.get("code") or "").strip().upper() or (m.get("name") or "").strip().lower()
            if not key:
                continue
            qty_total = bom_uom.qty_base_of(m) * qty_pcs
            rec = agg.get(key)
            if not rec:
                rec = {
                    "material_id": m.get("material_id"),
                    "code": m.get("code"),
                    "name": m.get("name"),
                    "category": m.get("category"),
                    "category_name": m.get("category_name"),
                    "material_type": m.get("material_type"),
                    "unit": bom_uom.base_unit_of(m),
                    "unit_input": m.get("unit"),
                    "uom_status": m.get("uom_status"),
                    "is_kglike": _is_kglike({**m, "unit": bom_uom.base_unit_of(m)}),
                    "_raw_total": 0.0,
                }
                agg[key] = rec
            rec["_raw_total"] += qty_total

    # ── Finalize aggregate: rounding + stock/shortfall ──
    aggregated = []
    total_yarn_kg = 0.0
    total_shortfall_lines = 0
    grand_total_cost = 0.0
    settings = await _get_costing_settings(db) if include_cost else None
    for rec in agg.values():
        kglike = rec["is_kglike"]
        total_required = _round(rec["_raw_total"], kglike, rounding)
        onhand = reserved = available = None
        shortfall = None
        if include_stock and rec.get("material_id"):
            onhand, reserved, available = await _stock_for_material(db, rec["material_id"])
            shortfall = round(max(0.0, total_required - available), 4)
            if shortfall > 0:
                total_shortfall_lines += 1
        unit_cost = subtotal_cost = None
        cost_source = None
        if include_cost:
            unit_cost, cost_source = await _resolve_unit_cost(db, rec, settings)
            subtotal_cost = round(total_required * unit_cost, 2)
            grand_total_cost += subtotal_cost
        aggregated.append({
            "material_id": rec["material_id"],
            "code": rec["code"],
            "name": rec["name"],
            "category": rec["category"],
            "category_name": rec["category_name"],
            "material_type": rec["material_type"],
            "is_kglike": kglike,
            "unit": rec["unit"],
            "total_required": total_required,
            "onhand": onhand,
            "reserved": reserved,
            "available": available,
            "shortfall": shortfall,
            "unit_cost": unit_cost,
            "subtotal_cost": subtotal_cost,
            "cost_source": cost_source,
        })
        if kglike:
            total_yarn_kg += total_required

    # sort: kg-like (kain/benang) dulu, lalu nama
    aggregated.sort(key=lambda r: (0 if r["is_kglike"] else 1, (r.get("name") or "").lower()))

    if source == "po" and po_meta and po_meta.get("business_type") == "maklon":
        warnings.append("PO Maklon: item maklon umumnya tanpa BOM internal (produksi oleh vendor CMT), "
                        "sehingga baris tanpa BOM adalah normal.")
    if uom_notices:
        warnings.append("Satuan pada BOM perlu dibereskan: " + " | ".join(uom_notices[:5]))
    if include_cost and any(r.get("cost_source") == "default" for r in aggregated):
        warnings.append("Sebagian harga satuan memakai default costing-settings "
                        "(material belum punya unit_cost) — estimasi biaya bersifat kasar.")

    return serialize_doc({
        "source": source,
        "po": po_meta,
        "rounding": rounding,
        "include_stock": include_stock,
        "include_cost": include_cost,
        "lines_resolved": lines_resolved,
        "lines_without_bom": lines_without_bom,
        "aggregated": aggregated,
        "uom_notices": uom_notices,
        "totals": {
            "grand_qty_pcs": round(grand_qty_pcs, 4),
            "total_material_lines": len(aggregated),
            # FASE 6.6-B: kanonik `total_material_kg` + alias legacy `total_yarn_kg`
            **material_fields.mirror("total_material_kg", round(total_yarn_kg, 4)),
            "total_shortfall_lines": total_shortfall_lines,
            "grand_total_cost": round(grand_total_cost, 2),
            "lines_resolved_count": len(lines_resolved),
            "lines_without_bom_count": len(lines_without_bom),
        },
        "warnings": warnings,
    })
