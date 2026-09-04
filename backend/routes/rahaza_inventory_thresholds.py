"""rahaza_inventory_thresholds — Ambang Stok (minimum & titik pesan ulang).

W3 (permintaan pemilik, sesi #29): *"Alert & Reorder tidak pernah berbunyi"*.
Akar masalahnya bukan fiturnya, tetapi **333 dari 333 material tidak punya
ambang**. Mengisinya satu per satu lewat modal Master Item mustahil, jadi layar
"Ambang Stok" memakai endpoint di sini: satu tabel berisi stok nyata, ambang
sekarang, dan USULAN dari pemakaian nyata (ledger) yang bisa diterapkan massal.

Definisi "rendah" TIDAK ditulis di sini — semuanya dari SSOT
`core/stock_thresholds` supaya layar, notifikasi, dan dashboard tidak pernah
berbeda pendapat.
"""
from fastapi import HTTPException, Request

from auth import log_activity, require_auth, serialize_doc
from core import stock_thresholds as th
from database import get_db
from routes.rahaza_inventory_shared import router, _require_admin

_TYPE_GROUPS = {
    "bahan": ["yarn", "fabric", "kain", "benang", "interlining"],
    "aksesoris": ["accessory", "packaging"],
    "fg": ["fg"],
}


@router.get("/stock-thresholds")
async def list_stock_thresholds(request: Request, type: str = "", search: str = "",
                               status: str = "all", limit: int = 1000):
    """Daftar ambang + stok kanonik + usulan. `status`: all|missing|set|low."""
    await require_auth(request)
    db = get_db()
    if limit < 1 or limit > 5000:
        raise HTTPException(400, "limit harus 1..5000")
    if status not in ("all", "missing", "set", "low"):
        raise HTTPException(400, "status harus all|missing|set|low")
    types = _TYPE_GROUPS.get(type) or ([type] if type else None)
    rows = await th.evaluate(db, types=types, search=search.strip(), limit=limit)
    if status == "missing":
        rows = [r for r in rows if not r["has_threshold"]]
    elif status == "set":
        rows = [r for r in rows if r["has_threshold"]]
    elif status == "low":
        rows = [r for r in rows if r["status"] in ("low", "critical")]
    return serialize_doc({
        "items": rows,
        "total": len(rows),
        "summary": await th.summary(db),
        "catatan": ("Ambang minimum & titik pesan ulang diisi di sini (Master Item). "
                    "Usulan dihitung dari pemakaian 30 hari terakhir; material tanpa "
                    "pemakaian tidak diberi usulan (tidak ditebak)."),
    })


@router.get("/stock-thresholds/summary")
async def stock_threshold_summary(request: Request):
    """Angka untuk badge dashboard & kejujuran layar Alert & Reorder."""
    await require_auth(request)
    return serialize_doc(await th.summary(get_db()))


@router.post("/stock-thresholds/bulk")
async def save_stock_thresholds(request: Request):
    """Simpan ambang untuk banyak material sekaligus.

    Body: `{"items": [{"material_id", "min_stock_qty", "reorder_point"}]}`
    """
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    items = body.get("items")
    if not isinstance(items, list) or not items:
        raise HTTPException(400, "items wajib berisi minimal satu baris.")
    if len(items) > 2000:
        raise HTTPException(400, "Maksimal 2000 baris per simpanan.")
    for it in items:
        if not isinstance(it, dict) or not str(it.get("material_id") or "").strip():
            raise HTTPException(400, "Setiap baris wajib menyebut material_id.")
        for key in ("min_stock_qty", "reorder_point", "lead_time_days"):
            if key in it and it[key] not in (None, ""):
                try:
                    if float(it[key]) < 0:
                        raise HTTPException(400, f"{key} tidak boleh negatif.")
                except (TypeError, ValueError):
                    raise HTTPException(400, f"{key} harus berupa angka.")
    res = await th.apply_thresholds(db, items, actor=user)
    if res["not_found"]:
        raise HTTPException(404, f"Material tidak ditemukan: {res['not_found'][:5]}")
    await log_activity(user["id"], user.get("name", ""), "update",
                       "rahaza.stock_thresholds", f"{res['updated']} material")
    return serialize_doc({**res, "summary": await th.summary(db)})


@router.post("/stock-thresholds/bulk-fill")
async def bulk_fill_thresholds(request: Request):
    """**Isi Ambang Massal** dengan satu dasar yang jelas (sesi #33).

    Body:
      `mode`     : `usage_30d` | `purchase_lot` | `percent_onhand` | `fixed`
      `dry_run`  : true = PRATINJAU saja (tidak menulis apa pun)
      `params`   : {percent} · {lot_multiplier} · {min_stock_qty, reorder_point}
      `scope`    : {material_ids:[...]} ATAU {types:[...], search, status}

    Kenapa: usulan dari pemakaian 30 hari hanya berlaku untuk 5 dari 335 material
    di data nyata; 330 sisanya sebelumnya tidak punya jalan massal apa pun.
    """
    user = await _require_admin(request)
    body = await request.json()
    try:
        res = await th.bulk_fill(get_db(), mode=body.get("mode"), params=body.get("params"),
                                 scope=body.get("scope"), actor=user,
                                 dry_run=bool(body.get("dry_run", True)))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not res["dry_run"] and res["applied"]:
        await log_activity(user["id"], user.get("name", ""), "update",
                           "rahaza.stock_thresholds_bulk_fill",
                           f"{res['applied']} material · dasar {res['basis_label']}")
    return serialize_doc(res)


@router.post("/stock-thresholds/bulk-clear")
async def bulk_clear_thresholds(request: Request):
    """Kosongkan ambang untuk seleksi/filter — pembatal 'Isi Ambang Massal'.

    Body: `{"material_ids": [...]}` ATAU `{"scope": {...}}`
    """
    user = await _require_admin(request)
    body = await request.json()
    ids = body.get("material_ids")
    scope = body.get("scope")
    if not ids and not scope:
        raise HTTPException(400, "Sebutkan material_ids atau scope yang mau dikosongkan.")
    if ids is not None and (not isinstance(ids, list) or not ids):
        raise HTTPException(400, "material_ids harus daftar berisi minimal satu id.")
    res = await th.bulk_clear(get_db(), material_ids=ids, scope=scope, actor=user)
    if res["cleared"]:
        await log_activity(user["id"], user.get("name", ""), "update",
                           "rahaza.stock_thresholds_bulk_clear", f"{res['cleared']} material")
    return serialize_doc(res)
