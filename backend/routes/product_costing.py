"""routes.product_costing — API **HPP per Potong & per Model** (`/api/costing`).

Layar "HPP per Potong" memakai router ini. Semua angka datang dari SSOT
`core/product_costing` — modul ini hanya HTTP + RBAC + validasi input.

Endpoint:
  GET    /api/costing/models                      daftar HPP semua model (ringkas + kekurangan)
  GET    /api/costing/models/{model_id}           rincian per ukuran (baris BOM, upah, margin)
  POST   /api/costing/models/{model_id}/apply     terapkan HPP → master + FG + item katalog
  PUT    /api/costing/models/{model_id}/labor     kunci upah CMT / upah internal produk ini
  POST   /api/costing/apply-all                   terapkan untuk semua model yang siap
  GET    /api/costing/settings                    setelan (overhead, target margin, tarif proses)
  PUT    /api/costing/settings                    simpan setelan
  GET    /api/costing/processes                   daftar proses produksi (untuk tarif standar)
  GET    /api/costing/snapshots                   riwayat penerapan HPP (audit)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from auth import log_activity, require_auth, serialize_doc
from core import product_costing as pc
from database import get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/costing", tags=["product-costing"])

WRITE_ROLES = {"superadmin", "admin", "owner", "director", "manager", "accounting",
               "finance", "staff_keuangan", "admin_produksi", "supervisor_produksi",
               "admin_maklon", "rnd_staff"}


async def _read_user(request: Request) -> dict:
    user = await require_auth(request)
    if (user.get("role") or "") == "klien_maklon":
        raise HTTPException(403, "Akses klien maklon hanya lewat portal tracking.")
    return user


async def _write_user(request: Request) -> dict:
    user = await _read_user(request)
    role = (user.get("role") or "").lower()
    perms = user.get("_permissions") or []
    if role in WRITE_ROLES or "*" in perms or "finance.manage" in perms or "hpp.manage" in perms:
        return user
    raise HTTPException(403, "Butuh hak Keuangan/Produksi untuk mengubah HPP produk.")


def _b(v, default=None):
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _num(v, default=None):
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@router.get("/models")
async def list_models(request: Request, q: str | None = None, only_gaps: bool = False,
                      include_overhead: str | None = None, target_margin_pct: str | None = None,
                      limit: int = 200):
    await _read_user(request)
    db = get_db()
    data = await pc.list_models_cost(
        db, q=q, only_gaps=_b(only_gaps, False),
        include_overhead=_b(include_overhead, None),
        target_margin_pct=_num(target_margin_pct, None),
        limit=max(1, min(int(limit or 200), 500)))
    return serialize_doc(data)


@router.get("/settings")
async def get_settings(request: Request):
    await _read_user(request)
    return serialize_doc(await pc.get_settings(get_db()))


@router.put("/settings")
async def put_settings(request: Request):
    user = await _write_user(request)
    body = await request.json()
    try:
        out = await pc.save_settings(get_db(), body, user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await log_activity(user["id"], user.get("name", ""), "update", "costing.settings", "GLOBAL")
    return serialize_doc(out)


@router.get("/processes")
async def list_processes(request: Request):
    """Proses produksi + tarif standar yang sudah tersimpan (untuk layar setelan upah)."""
    await _read_user(request)
    db = get_db()
    settings = await pc.get_settings(db)
    saved = {r.get("process_id"): r for r in settings["process_rates"]}
    rows = []
    async for p in db.rahaza_processes.find({}, {"_id": 0}).sort("code", 1):
        code = (p.get("code") or "").upper()
        rows.append({
            "process_id": p.get("id"), "code": code, "name": p.get("name") or "",
            "active": p.get("active", True),
            "is_cmt": code in pc.CMT_PROCESS_CODES,
            "rate_per_pcs": float((saved.get(p.get("id")) or {}).get("rate_per_pcs") or 0),
        })
    return {"items": rows, "count": len(rows),
            "cmt_process_codes": sorted(pc.CMT_PROCESS_CODES),
            "settings": serialize_doc(settings)}


@router.get("/snapshots")
async def snapshots(request: Request, model_id: str | None = None, limit: int = 50):
    await _read_user(request)
    rows = await pc.list_snapshots(get_db(), model_id=model_id,
                                   limit=max(1, min(int(limit or 50), 200)))
    return {"items": serialize_doc(rows), "count": len(rows)}


@router.get("/models/{model_id}")
async def model_detail(model_id: str, request: Request, include_overhead: str | None = None,
                       target_margin_pct: str | None = None, size_id: str | None = None):
    await _read_user(request)
    try:
        data = await pc.compute_model_cost(
            get_db(), model_id, size_id=size_id,
            include_overhead=_b(include_overhead, None),
            target_margin_pct=_num(target_margin_pct, None))
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return serialize_doc(data)


@router.put("/models/{model_id}/labor")
async def put_labor(model_id: str, request: Request):
    """Kunci upah CMT / upah cutting-internal untuk produk ini (dengan jejak siapa & kapan)."""
    user = await _write_user(request)
    db = get_db()
    if not await db.rahaza_models.find_one({"id": model_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Model tidak ditemukan.")
    body = await request.json()
    try:
        out = await pc.save_override(db, model_id, body, user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await log_activity(user["id"], user.get("name", ""), "update", "costing.labor", model_id)
    return serialize_doc(out)


@router.post("/models/{model_id}/apply")
async def apply_model(model_id: str, request: Request):
    """Hitung & TERAPKAN HPP: master produk + FG per ukuran + item katalog Marketing."""
    user = await _write_user(request)
    db = get_db()
    if not await db.rahaza_models.find_one({"id": model_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Model tidak ditemukan.")
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    size_ids = body.get("size_ids") or None
    if size_ids is not None and not isinstance(size_ids, list):
        raise HTTPException(400, "`size_ids` harus berupa daftar.")
    out = await pc.apply_model_cost(db, model_id, user, size_ids=size_ids,
                                    include_overhead=_b(body.get("include_overhead"), None))
    if not out["ok"]:
        raise HTTPException(400, (
            "Belum ada ukuran yang bisa diterapkan — semua ukuran belum punya BOM atau HPP-nya 0. "
            "Perbaiki kekurangan yang tertera dulu."))
    await log_activity(user["id"], user.get("name", ""), "apply", "costing.hpp", model_id)
    return serialize_doc(out)


@router.post("/apply-all")
async def apply_all(request: Request):
    """Terapkan HPP untuk SEMUA model yang sudah bisa dihitung (idempoten)."""
    user = await _write_user(request)
    db = get_db()
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    include_overhead = _b(body.get("include_overhead"), None)
    models = await db.rahaza_models.find(
        {"$or": [{"active": True}, {"active": {"$exists": False}}, {"status": "active"}]},
        {"_id": 0, "id": 1, "code": 1, "name": 1}).to_list(500)
    applied, skipped = [], []
    for m in models:
        try:
            out = await pc.apply_model_cost(db, m["id"], user, include_overhead=include_overhead)
        except Exception as e:                                   # noqa: BLE001 - laporkan, jangan gagal total
            skipped.append({"model_id": m["id"], "code": m.get("code"), "reason": str(e)[:200]})
            continue
        if out["ok"]:
            applied.append({"model_id": m["id"], "code": m.get("code"),
                            "hpp_model": out["hpp_model"], "sizes": len(out["applied"]),
                            "fg_updated": out["fg_updated"],
                            "catalog_items_updated": out["catalog_items_updated"]})
        else:
            skipped.append({"model_id": m["id"], "code": m.get("code"),
                            "reason": "belum ada ukuran yang bisa dihitung"})
    await log_activity(user["id"], user.get("name", ""), "apply", "costing.hpp", "ALL")
    return {"ok": True, "applied": applied, "skipped": skipped,
            "applied_count": len(applied), "skipped_count": len(skipped),
            "fg_updated": sum(a["fg_updated"] for a in applied),
            "catalog_items_updated": sum(a["catalog_items_updated"] for a in applied)}
