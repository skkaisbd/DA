"""routes/production_sewing_cost.py — **BIAYA JAHIT SPK & HPP BATCH (FIFO)**.

KENAPA LAYAR/ENDPOINT INI ADA (diukur 2026-08-23, sesi #34)
-----------------------------------------------------------
`po_items.cmt_price_snapshot` (upah jahit per pcs) sudah dipakai tiga tempat:
Monitoring CMT (`services/cmt_kejar.ongkos_jahit_terhitung`), tagihan CMT, dan
kalkulator HPP. Tetapi untuk **SPK produksi internal** nilainya SELALU 0 —
`routes/production_internal_adapter.py` menulis `'cmt_price_snapshot': 0.0` dan
tidak ada satu pun layar yang bisa mengubahnya. Akibatnya:

* HPP produk = biaya bahan saja ⇒ margin di Katalog Marketing terlalu bagus.
* Ongkos jahit yang nyata dibayar tidak pernah masuk buku biaya per produk.

Modul ini membuka pintunya, dengan aturan pemilik (2026-08-23):

    "input harganya PER SKU PER PCS, baru dari sana kalkulasi total biaya"

Jadi yang diketik staf adalah **tarif per pcs untuk tiap SKU di dalam SPK**, dan
sistem yang mengalikan dengan qty (total per baris + total SPK). Tarif tersimpan
di `po_items.cmt_price_snapshot` (SSOT yang sudah ada — bukan koleksi baru),
lengkap dengan jejak siapa & kapan (`cmt_price_set_by`, `cmt_price_set_at`).

HPP BATCH (FIFO) — kenapa ditampilkan di sini
---------------------------------------------
Upah jahit hanya berarti kalau ia sampai ke HPP. Saat barang jadi lolos QC dan
masuk gudang FG, `core.production_qty_ledger.post_fg_accepted` mencatat satu
**lapisan biaya batch** (`core/fg_cost_layers`) = bahan (BOM) + jahit (SPK) +
permak + upah internal. Endpoint `GET /hpp/{material_id}` memperlihatkan lapisan
itu apa adanya: berapa per batch, sisa stok tiap batch, dan rata-rata lapisan
yang MASIH ada stoknya (angka yang dipakai margin Katalog Marketing).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import check_role, log_activity, require_auth
from core import fg_cost_layers as fcl
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/production/sewing-cost", tags=["production-sewing-cost"])

WRITE_ROLES = ["admin", "admin_produksi", "supervisor_produksi", "accounting", "maklon"]
READ_ROLES = WRITE_ROLES + ["spv", "staff_produksi", "marketing", "admin_marketing"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _f(v, d: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(d)
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def _user(request: Request) -> dict:
    return getattr(request.state, "user", {}) or {}


def _guard(user: dict, roles: list, what: str) -> None:
    if not check_role(user, roles, "production.manage"):
        raise HTTPException(403, f"Akses ditolak: butuh izin {what}")


class RateIn(BaseModel):
    po_item_id: str
    rate_per_pcs: float = Field(..., ge=0)


class RatesIn(BaseModel):
    items: list[RateIn]
    # Tarif SKU yang sama di dalam SPK ini ikut terisi — menghindari ketikan
    # berulang untuk 8 ukuran dari satu model.
    apply_same_sku: bool = False
    notes: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# USULAN TARIF — dari data nyata, bukan tebakan
# ══════════════════════════════════════════════════════════════════════════════
async def _suggestions(db, items: list[dict]) -> dict:
    """{po_item_id: {rate, source, note}} dari SPK sebelumnya / master partner."""
    out: dict = {}
    skus = [i.get("sku") for i in items if i.get("sku")]
    models = [i.get("model_id") for i in items if i.get("model_id")]
    prev_by_sku: dict = {}
    prev_by_model: dict = {}
    if skus or models:
        q = {"cmt_price_snapshot": {"$gt": 0}}
        ors = []
        if skus:
            ors.append({"sku": {"$in": skus}})
        if models:
            ors.append({"model_id": {"$in": models}})
        if ors:
            q["$or"] = ors
        rows = await db.po_items.find(q, {"_id": 0, "sku": 1, "model_id": 1, "po_number": 1,
                                          "cmt_price_snapshot": 1, "created_at": 1}
                                      ).sort("created_at", -1).to_list(500)
        for r in rows:
            if r.get("sku") and r["sku"] not in prev_by_sku:
                prev_by_sku[r["sku"]] = r
            if r.get("model_id") and r["model_id"] not in prev_by_model:
                prev_by_model[r["model_id"]] = r
    partners = await db.dewi_cmt_partners.find(
        {"rate_per_pcs": {"$gt": 0}, "status": {"$ne": "inactive"}},
        {"_id": 0, "name": 1, "rate_per_pcs": 1}).sort("rate_per_pcs", 1).to_list(50)
    partner_rate = _f(partners[0].get("rate_per_pcs")) if partners else 0.0
    for it in items:
        hit = prev_by_sku.get(it.get("sku")) or prev_by_model.get(it.get("model_id"))
        if hit:
            out[it["id"]] = {
                "rate": round(_f(hit.get("cmt_price_snapshot")), 2),
                "source": "spk_sebelumnya",
                "note": f"Tarif SPK {hit.get('po_number') or '—'} untuk SKU/model yang sama",
            }
        elif partner_rate > 0:
            out[it["id"]] = {"rate": round(partner_rate, 2), "source": "master_partner_cmt",
                             "note": f"Tarif termurah master partner CMT ({partners[0].get('name')})"}
        else:
            out[it["id"]] = {"rate": 0.0, "source": "none",
                             "note": "Belum ada tarif nyata — isi manual"}
    return out


# ══════════════════════════════════════════════════════════════════════════════
# DAFTAR SPK + STATUS PENGISIAN BIAYA JAHIT
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/pos")
async def list_pos(request: Request,
                   q: str | None = Query(None, description="cari nomor SPK/PO"),
                   only_missing: bool = Query(False, description="hanya SPK yang biaya jahitnya belum lengkap"),
                   limit: int = Query(50, ge=1, le=200)):
    await require_auth(request)
    _guard(_user(request), READ_ROLES, "lihat produksi")
    db = get_db()
    query: dict = {"status": {"$nin": ["Cancelled", "Rejected"]}}
    if q:
        query["po_number"] = {"$regex": q, "$options": "i"}
    pos = await db.production_pos.find(query, {"_id": 0}).sort("created_at", -1).to_list(300)
    po_ids = [p["id"] for p in pos]
    items = await db.po_items.find({"po_id": {"$in": po_ids}}, {"_id": 0}).to_list(5000)
    by_po: dict = {}
    for it in items:
        by_po.setdefault(it["po_id"], []).append(it)
    out = []
    for p in pos:
        its = by_po.get(p["id"], [])
        qty = sum(int(_f(i.get("qty"))) for i in its)
        filled = [i for i in its if _f(i.get("cmt_price_snapshot")) > 0]
        total = sum(_f(i.get("cmt_price_snapshot")) * int(_f(i.get("qty"))) for i in its)
        row = {
            "po_id": p["id"], "po_number": p.get("po_number"),
            "business_type": p.get("business_type") or ("internal" if not p.get("vendor_id") else "maklon"),
            "vendor_name": p.get("vendor_name") or "Produksi Internal",
            "customer_name": p.get("customer_name") or "",
            "status": p.get("status"), "po_date": p.get("po_date"),
            "item_count": len(its), "qty_total": qty,
            "items_with_rate": len(filled),
            "sewing_total": round(total, 2),
            "sewing_avg_per_pcs": round(total / qty, 2) if qty else 0.0,
            "complete": bool(its) and len(filled) == len(its),
        }
        if only_missing and row["complete"]:
            continue
        out.append(row)
    return {"ok": True, "data": out[:limit], "total": len(out)}


# ══════════════════════════════════════════════════════════════════════════════
# DETAIL SATU SPK — tarif per SKU + pratinjau HPP batch
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/pos/{po_id}")
async def get_po_sewing(po_id: str, request: Request):
    await require_auth(request)
    _guard(_user(request), READ_ROLES, "lihat produksi")
    db = get_db()
    po = await db.production_pos.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "SPK/PO produksi tidak ditemukan")
    items = await db.po_items.find({"po_id": po_id}, {"_id": 0}).to_list(2000)
    if not items:
        raise HTTPException(400, "SPK ini belum punya item")
    sug = await _suggestions(db, items)

    # ── SSOT: apakah item SPK ini benar-benar menunjuk MASTER? (sesi #34) ──────
    # Diukur pada data nyata: 7 dari 7 baris `po_items` memakai SKU yang TIDAK ADA
    # di master barang (`ARN-HD-M`, `DA-TS01-ALLSIZE`, …) dan 4 di antaranya tidak
    # punya `model_id` sama sekali. Akibatnya biaya jahit yang diisi di sini tidak
    # akan pernah sampai ke HPP produk mana pun, dan BOM tidak bisa dihitung.
    # Kekurangan ini DIKATAKAN per baris — bukan dibiarkan menjadi Rp 0 senyap.
    skus = [i.get("sku") for i in items if i.get("sku")]
    model_ids = [i.get("model_id") for i in items if i.get("model_id")]
    master_codes = {m["code"] for m in await db.rahaza_materials.find(
        {"code": {"$in": skus}}, {"_id": 0, "code": 1}).to_list(2000)} if skus else set()
    master_models = {m["id"] for m in await db.rahaza_models.find(
        {"id": {"$in": model_ids}}, {"_id": 0, "id": 1}).to_list(2000)} if model_ids else set()

    rows = []
    for it in items:
        qty = int(_f(it.get("qty")))
        rate = _f(it.get("cmt_price_snapshot"))
        cost = await fcl.compute_batch_unit_cost(db, po_item=it, qty=max(1, qty))
        sku_ok = bool(it.get("sku")) and it.get("sku") in master_codes
        model_ok = bool(it.get("model_id")) and it.get("model_id") in master_models
        ssot_msgs = []
        if not sku_ok:
            ssot_msgs.append(
                f"SKU '{it.get('sku') or '(kosong)'}' tidak ada di master barang jadi — "
                "biaya jahit baris ini TIDAK akan sampai ke HPP produk. Tautkan lewat "
                "Jembatan SKU / Master Produk dulu.")
        if not model_ok:
            ssot_msgs.append(
                "Item ini tidak menunjuk model master — BOM (biaya bahan) tidak bisa dihitung.")
        rows.append({
            "ssot": {"sku_in_master": sku_ok, "model_in_master": model_ok,
                     "ok": sku_ok and model_ok, "messages": ssot_msgs},
            "po_item_id": it["id"], "sku": it.get("sku") or "",
            "product_name": it.get("product_name") or "",
            "model_id": it.get("model_id") or "", "size": it.get("size") or "",
            "color": it.get("color") or "", "qty": qty,
            "rate_per_pcs": round(rate, 2),
            "line_total": round(rate * qty, 2),
            "set_by": it.get("cmt_price_set_by") or "",
            "set_at": it.get("cmt_price_set_at"),
            "suggestion": sug.get(it["id"]) or {},
            "hpp_preview": {
                "material_cost": cost["material_cost"], "material_source": cost["material_source"],
                "sewing_cost": cost["sewing_cost"], "permak_cost": cost["permak_cost"],
                "internal_labor_cost": cost["internal_labor_cost"],
                "overhead_cost": cost["overhead_cost"], "unit_cost": cost["unit_cost"],
                "gaps": cost["gaps"],
            },
        })
    qty_total = sum(r["qty"] for r in rows)
    sewing_total = round(sum(r["line_total"] for r in rows), 2)
    hpp_total = round(sum(r["hpp_preview"]["unit_cost"] * r["qty"] for r in rows), 2)
    return {
        "ok": True,
        "po": {"id": po["id"], "po_number": po.get("po_number"), "status": po.get("status"),
               "vendor_name": po.get("vendor_name") or "Produksi Internal",
               "business_type": po.get("business_type") or "",
               "customer_name": po.get("customer_name") or "",
               "notes": po.get("notes") or ""},
        "items": rows,
        "totals": {
            "qty": qty_total, "sewing_total": sewing_total,
            "sewing_avg_per_pcs": round(sewing_total / qty_total, 2) if qty_total else 0.0,
            "hpp_total": hpp_total,
            "hpp_avg_per_pcs": round(hpp_total / qty_total, 2) if qty_total else 0.0,
            "items_missing_rate": sum(1 for r in rows if r["rate_per_pcs"] <= 0),
            "items_broken_ssot": sum(1 for r in rows if not r["ssot"]["ok"]),
        },
    }


@router.put("/pos/{po_id}")
async def set_po_sewing(po_id: str, body: RatesIn, request: Request):
    await require_auth(request)
    user = _user(request)
    _guard(user, WRITE_ROLES, "kelola produksi (production.manage)")
    db = get_db()
    po = await db.production_pos.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "SPK/PO produksi tidak ditemukan")
    items = await db.po_items.find({"po_id": po_id}, {"_id": 0}).to_list(2000)
    by_id = {i["id"]: i for i in items}
    actor = user.get("name") or user.get("email") or "system"
    updated = 0
    touched_skus: dict = {}
    for r in body.items:
        it = by_id.get(r.po_item_id)
        if not it:
            raise HTTPException(400, f"Item {r.po_item_id} bukan bagian SPK {po.get('po_number')}")
        await db.po_items.update_one(
            {"id": r.po_item_id},
            {"$set": {"cmt_price_snapshot": round(_f(r.rate_per_pcs), 2),
                      "cmt_price_set_by": actor, "cmt_price_set_at": _now()}})
        updated += 1
        if it.get("sku"):
            touched_skus[it["sku"]] = round(_f(r.rate_per_pcs), 2)
    same_sku = 0
    if body.apply_same_sku and touched_skus:
        for sku, rate in touched_skus.items():
            res = await db.po_items.update_many(
                {"po_id": po_id, "sku": sku, "id": {"$nin": [r.po_item_id for r in body.items]}},
                {"$set": {"cmt_price_snapshot": rate, "cmt_price_set_by": actor,
                          "cmt_price_set_at": _now()}})
            same_sku += res.modified_count
    await log_activity(user.get("id", "system"), actor, "update", "Biaya Jahit SPK",
                       f"SPK {po.get('po_number')}: {updated} tarif jahit diisi"
                       + (f" (+{same_sku} baris SKU sama)" if same_sku else "")
                       + (f" — {body.notes}" if body.notes else ""))
    return {"ok": True, "updated": updated, "also_updated_same_sku": same_sku}


# ══════════════════════════════════════════════════════════════════════════════
# HPP BATCH (FIFO) — apa adanya
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/hpp/{material_id}")
async def hpp_layers(material_id: str, request: Request):
    await require_auth(request)
    _guard(_user(request), READ_ROLES, "lihat produksi")
    db = get_db()
    mat = await db.rahaza_materials.find_one({"id": material_id},
                                             {"_id": 0, "id": 1, "code": 1, "name": 1,
                                              "type": 1, "hpp": 1, "hpp_source": 1})
    if not mat:
        raise HTTPException(404, "Master barang tidak ditemukan")
    snap = await fcl.hpp_snapshot(db, material_id)
    return {"ok": True, "material": mat, "hpp": snap}


@router.get("/hpp-by-sku/{sku}")
async def hpp_by_sku(sku: str, request: Request):
    await require_auth(request)
    _guard(_user(request), READ_ROLES, "lihat produksi")
    db = get_db()
    mat = await db.rahaza_materials.find_one({"type": "fg", "code": sku},
                                             {"_id": 0, "id": 1, "code": 1, "name": 1})
    if not mat:
        raise HTTPException(404, f"SKU barang jadi '{sku}' tidak ada di master")
    snap = await fcl.hpp_snapshot(db, mat["id"])
    return {"ok": True, "material": mat, "hpp": snap}


# ══════════════════════════════════════════════════════════════════════════════
# TAUTKAN SKU SPK → MASTER BARANG JADI (sesi #34)
# ══════════════════════════════════════════════════════════════════════════════
# Diukur: 7 dari 7 baris `po_items` memakai SKU yang TIDAK ADA di master barang
# jadi (`ARN-HD-M`, `DA-TS01-ALLSIZE`, …). Akibatnya biaya jahit yang diisi tidak
# pernah sampai ke HPP produk mana pun — lapisan HPP batch lahir dari
# `material_id` master, dan master itu tidak pernah ketemu.
#
# Alat ini TIDAK menautkan sendiri. Ia mengusulkan pasangan beserta ALASANNYA
# (kode sepadan / model sama / ukuran sama / nama mirip) dan staf yang memutuskan.
# SKU asli disimpan (`sku_original`) supaya penautan bisa diperiksa & dibatalkan.
def _code_parts(code: str) -> list:
    return [p for p in str(code or "").upper().replace("_", "-").split("-") if p]


def _score_candidate(item: dict, mat: dict) -> tuple:
    """(skor 0..1, alasan) — dihitung dari bukti, bukan tebakan bebas."""
    import difflib
    reasons = []
    score = 0.0
    ip, mp = _code_parts(item.get("sku")), _code_parts(mat.get("code"))
    shared = [p for p in ip if p in mp]
    if ip and shared:
        frac = len(shared) / len(ip)
        score += 0.45 * frac
        reasons.append(f"kode sepadan: {'-'.join(shared)}")
    if item.get("model_id") and item.get("model_id") == mat.get("model_id"):
        score += 0.3
        reasons.append("model master sama")
    size_item = next((p for p in ip if p in ("S", "M", "L", "XL", "XXL", "XXXL", "ALLSIZE")), "")
    if size_item and str(mat.get("size_code") or "").upper() == size_item:
        score += 0.15
        reasons.append(f"ukuran sama ({size_item})")
    elif size_item and mat.get("size_code"):
        score -= 0.25
        reasons.append(f"ukuran BEDA (SPK {size_item} vs master {mat.get('size_code')})")
    nm = difflib.SequenceMatcher(
        None, str(item.get("product_name") or "").lower(), str(mat.get("name") or "").lower()
    ).ratio()
    score += 0.25 * nm
    if nm > 0.5:
        reasons.append(f"nama mirip {round(nm * 100)}%")
    return max(0.0, min(1.0, round(score, 3))), reasons


@router.get("/unlinked")
async def list_unlinked(request: Request, limit: int = Query(100, ge=1, le=500)):
    """Baris SPK yang SKU-nya tidak ada di master + usulan pasangannya."""
    await require_auth(request)
    _guard(_user(request), READ_ROLES, "lihat produksi")
    db = get_db()
    items = await db.po_items.find({}, {"_id": 0}).to_list(5000)
    codes = {m["code"]: m for m in await db.rahaza_materials.find(
        {"type": "fg"}, {"_id": 0, "id": 1, "code": 1, "name": 1, "model_id": 1,
                         "size_code": 1, "color_name": 1, "hpp": 1}).to_list(5000)}
    mats = list(codes.values())
    out = []
    for it in items:
        if it.get("sku") and it["sku"] in codes:
            continue
        scored = sorted(((*_score_candidate(it, m), m) for m in mats),
                        key=lambda x: -x[0])[:5]
        out.append({
            "po_item_id": it["id"], "po_number": it.get("po_number") or "",
            "po_id": it.get("po_id") or "",
            "sku": it.get("sku") or "", "product_name": it.get("product_name") or "",
            "model_id": it.get("model_id") or "", "qty": int(_f(it.get("qty"))),
            "rate_per_pcs": round(_f(it.get("cmt_price_snapshot")), 2),
            "sewing_at_risk": round(_f(it.get("cmt_price_snapshot")) * _f(it.get("qty")), 2),
            "reason": ("SKU tidak ada di master barang jadi"
                       if it.get("sku") else "item SPK tidak punya SKU"),
            "candidates": [{
                "material_id": m["id"], "code": m["code"], "name": m.get("name"),
                "size": m.get("size_code"), "color": m.get("color_name"),
                "score": sc, "reasons": rs,
                "confident": sc >= 0.7,
            } for sc, rs, m in scored if sc > 0.2],
        })
    total_risk = round(sum(r["sewing_at_risk"] for r in out), 2)
    rupiah = f"{total_risk:,.0f}".replace(",", ".")
    return {"ok": True, "data": out[:limit], "total": len(out),
            "sewing_at_risk_total": total_risk,
            "note": (f"Selama belum ditautkan, ongkos jahit sebesar Rp {rupiah} "
                     "tidak akan pernah masuk HPP produk.")}


class LinkIn(BaseModel):
    material_id: str
    note: str = ""


@router.post("/link/{po_item_id}")
async def link_item(po_item_id: str, body: LinkIn, request: Request):
    """Tautkan satu baris SPK ke SKU master (keputusan manusia, berjejak)."""
    await require_auth(request)
    user = _user(request)
    _guard(user, WRITE_ROLES, "kelola produksi (production.manage)")
    db = get_db()
    it = await db.po_items.find_one({"id": po_item_id}, {"_id": 0})
    if not it:
        raise HTTPException(404, "Baris SPK tidak ditemukan")
    mat = await db.rahaza_materials.find_one(
        {"id": body.material_id, "type": "fg"},
        {"_id": 0, "id": 1, "code": 1, "name": 1, "model_id": 1, "size_id": 1, "size_code": 1})
    if not mat:
        raise HTTPException(404, "SKU master barang jadi tidak ditemukan")
    actor = user.get("name") or user.get("email") or "system"
    await db.po_items.update_one({"id": po_item_id}, {"$set": {
        "sku": mat["code"],
        "sku_original": it.get("sku_original") or it.get("sku") or "",
        "fg_material_id": mat["id"],
        "model_id": mat.get("model_id") or it.get("model_id") or "",
        "size_id": mat.get("size_id") or it.get("size_id") or "",
        "sku_link_by": actor, "sku_link_at": _now(),
        "sku_link_note": body.note or "",
    }})
    await log_activity(user.get("id", "system"), actor, "update", "Tautkan SKU SPK",
                       f"SPK {it.get('po_number')}: '{it.get('sku')}' ditautkan ke master "
                       f"{mat['code']}" + (f" — {body.note}" if body.note else ""))
    return {"ok": True, "po_item_id": po_item_id, "sku": mat["code"],
            "material_id": mat["id"], "sku_original": it.get("sku")}
