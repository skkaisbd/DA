"""rahaza_inventory — Stock, Operations (receive/transfer/adjust), Movement Ledger."""
# ruff: noqa: E741
from fastapi import Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from typing import Optional
from routes.rahaza_inventory_shared import (
    router, log, _require_admin, _add_stock, _log_movement,
    get_pagination_params, paginated_response, MASTER_FETCH_LIMIT,
)
from routes.rahaza_posting import (
    post_inventory_receive,
    post_inventory_adjust,
)
from core import stock_service
from core import location_resolver


# ──────────────────────────────────────────────────────────────────────────────
# STOCK
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/material-stock")
async def list_stock(request: Request, material_id: Optional[str] = None,
                    location_id: Optional[str] = None, type: Optional[str] = None,
                    include_zero: Optional[str] = None):
    """Baris stok + identitas barang dari MASTER.

    W1 (sesi #29, permintaan pemilik) — dua perbaikan yang membuat layar ini
    berhenti "tampak tidak sinkron" dengan Master Item Produk Jadi:

    1. **Kategori · Warna · Opsi ikut dikirim.** Ketiganya SUDAH tersimpan di
       dokumen master barang (`category_name`, `color_name`/`color`,
       `option_name`/`option_code`) hasil SSOT varian sesi #28 — jadi layar tidak
       perlu (dan TIDAK BOLEH) menebaknya dengan memotong-motong string SKU.
    2. **`include_zero=1`** menambahkan barang master yang BELUM punya baris stok
       sebagai baris qty 0 (`no_stock_row: true`). Inilah akar keluhan "tabel FG
       tidak sinkron": layar ini menampilkan BARIS STOK, dan hanya ±12 dari 321
       barang jadi yang punya baris stok — sisanya tidak pernah kelihatan sama
       sekali walau masternya ada.
    """
    await require_auth(request)
    db = get_db()
    _inc_zero = str(include_zero or "").strip().lower() in ("1", "true", "yes", "y")

    def _num(v):
        """Safe float coercion; None if not a finite number (never raises)."""
        try:
            if v is None or v == "":
                return None
            f = float(v)
            if f != f or f in (float("inf"), float("-inf")):  # NaN / inf guard
                return None
            return f
        except (TypeError, ValueError):
            return None

    stock_q = {}
    if material_id:
        stock_q["material_id"] = material_id
    if location_id:
        stock_q["location_id"] = location_id
    stocks = await db.rahaza_material_stock.find(stock_q, {"_id": 0}).to_list(MASTER_FETCH_LIMIT)
    # Guard against docs missing material_id/location_id (would raise KeyError → 500).
    m_ids = list({s.get("material_id") for s in stocks if s.get("material_id")})
    l_ids = list({s.get("location_id") for s in stocks if s.get("location_id")})
    mats = await db.rahaza_materials.find({"id": {"$in": m_ids}}, {"_id": 0}).to_list(MASTER_FETCH_LIMIT) if m_ids else []
    m_map = {m["id"]: m for m in mats}
    # FASE C — dual-read tampilan lokasi: resolusi nama lintas skema (rahaza_locations
    # LAMA + wh_zones/wh_positions BARU). Fix P3 "Lokasi -" untuk id kanonik wh_*.
    l_map = await location_resolver.build_display_map(db, l_ids) if l_ids else {}
    rows = []
    for s in stocks:
        m = m_map.get(s.get("material_id")) or {}
        l = l_map.get(s.get("location_id")) or {}
        if type and m.get("type") != type:
            continue
        current_qty = _num(s.get("qty")) or 0.0
        is_low_stock = False
        low_stock_reason = None
        min_stock_qty = _num(m.get("min_stock_qty"))
        if min_stock_qty is not None and current_qty < min_stock_qty:
            is_low_stock = True
            low_stock_reason = f"Below min qty: {current_qty} < {min_stock_qty}"
        min_stock_pct = _num(m.get("min_stock_percentage"))
        if min_stock_pct is not None and not is_low_stock:
            baseline_max = 1000
            threshold_qty = baseline_max * (min_stock_pct / 100)
            if current_qty < threshold_qty:
                is_low_stock = True
                low_stock_reason = f"Below {min_stock_pct}% threshold: {current_qty} < {threshold_qty:.0f}"
        legacy_min = _num(m.get("min_stock"))
        if not is_low_stock and legacy_min is not None:
            if current_qty < legacy_min:
                is_low_stock = True
                low_stock_reason = f"Below legacy min_stock: {current_qty} < {legacy_min}"
        rows.append({
            **s,
            "material_code": m.get("code"), "material_name": m.get("name"),
            "material_type": m.get("type"), "unit": m.get("unit"),
            # W1 — identitas barang dari MASTER (bukan hasil memotong SKU)
            "category_name": m.get("category_name") or m.get("category") or "",
            "category_code": m.get("category_code") or "",
            "color_name": m.get("color_name") or m.get("color") or "",
            "option_name": m.get("option_name") or "",
            "option_code": m.get("option_code") or "",
            "size_code": m.get("size_code") or "",
            "variant_id": m.get("variant_id"),
            "sku": m.get("sku") or m.get("code"),
            "min_stock": m.get("min_stock", 0),
            "min_stock_qty": m.get("min_stock_qty"),
            "min_stock_percentage": m.get("min_stock_percentage"),
            "location_code": l.get("code"), "location_name": l.get("name"),
            "below_min": is_low_stock,
            "low_stock_reason": low_stock_reason,
            "no_stock_row": False,
        })

    # ── W1 — barang master yang BELUM punya baris stok (saklar "tampilkan stok 0")
    if _inc_zero and not material_id and not location_id:
        have = {s.get("material_id") for s in stocks if s.get("material_id")}
        mq: dict = {}
        if type:
            mq["type"] = type
        masters = await db.rahaza_materials.find(mq, {"_id": 0}).to_list(MASTER_FETCH_LIMIT)
        for m in masters:
            if m.get("id") in have or m.get("active") is False:
                continue
            _min_qty = _num(m.get("min_stock_qty"))
            rows.append({
                "id": None,
                "material_id": m.get("id"),
                "location_id": None,
                "qty": 0.0, "total_qty": 0.0, "quantity": 0.0,
                "reserved_quantity": 0.0, "available_quantity": 0.0,
                "material_code": m.get("code"), "material_name": m.get("name"),
                "material_type": m.get("type"), "unit": m.get("unit"),
                "category_name": m.get("category_name") or m.get("category") or "",
                "category_code": m.get("category_code") or "",
                "color_name": m.get("color_name") or m.get("color") or "",
                "option_name": m.get("option_name") or "",
                "option_code": m.get("option_code") or "",
                "size_code": m.get("size_code") or "",
                "variant_id": m.get("variant_id"),
                "sku": m.get("sku") or m.get("code"),
                "min_stock": m.get("min_stock", 0),
                "min_stock_qty": m.get("min_stock_qty"),
                "min_stock_percentage": m.get("min_stock_percentage"),
                "location_code": None, "location_name": None,
                "below_min": bool(_min_qty and _min_qty > 0),
                "low_stock_reason": ("Belum ada baris stok di lokasi mana pun"
                                     if _min_qty and _min_qty > 0 else None),
                "no_stock_row": True,
            })
    rows.sort(key=lambda r: (r.get("material_type") or "", r.get("material_code") or "", r.get("location_code") or ""))
    return serialize_doc(rows)


@router.get("/storage-locations")
async def list_storage_locations(request: Request):
    """FASE C — Daftar lokasi storage TERPADU untuk dropdown/filter modul Stok.
    Utamakan zona kanonik `wh_*` (source='wh_zone'); sertakan lokasi legacy
    `rahaza_locations` yang belum terpetakan. Setiap entri: {id, code, name, source, role?}."""
    await require_auth(request)
    db = get_db()
    return serialize_doc(await location_resolver.list_storage_locations(db))


@router.get("/material-stock/summary")
async def stock_summary(request: Request):
    await require_auth(request)
    db = get_db()
    pipe = [
        {"$lookup": {"from": "rahaza_materials", "localField": "material_id", "foreignField": "id", "as": "mat"}},
        {"$unwind": "$mat"},
        {"$group": {"_id": "$mat.type", "total_qty": {"$sum": "$qty"}, "count": {"$sum": 1}}},
    ]
    rows = await db.rahaza_material_stock.aggregate(pipe).to_list(MASTER_FETCH_LIMIT)
    by_type = {r["_id"]: {"total_qty": r["total_qty"], "row_count": r["count"]} for r in rows}
    # 3 kategori bisnis (Bahan/Aksesoris/Produk Jadi) — agregasi lintas tipe legacy.
    _CAT_OF = {
        "yarn": "bahan", "fabric": "bahan", "kain": "bahan", "benang": "bahan", "interlining": "bahan",
        "accessory": "aksesoris", "packaging": "aksesoris", "fg": "fg",
    }
    by_category = {
        "bahan": {"total_qty": 0.0, "row_count": 0},
        "aksesoris": {"total_qty": 0.0, "row_count": 0},
        "fg": {"total_qty": 0.0, "row_count": 0},
    }
    for _t, _v in by_type.items():
        _cat = _CAT_OF.get((_t or "").lower(), "bahan")
        by_category[_cat]["total_qty"] += float(_v["total_qty"] or 0)
        by_category[_cat]["row_count"] += int(_v["row_count"] or 0)
    stocks = await db.rahaza_material_stock.find({}, {"_id": 0}).to_list(MASTER_FETCH_LIMIT)
    mats_raw = await db.rahaza_materials.find({}, {"_id": 0}).to_list(MASTER_FETCH_LIMIT)
    mat_by_id = {m["id"]: m for m in mats_raw}
    total_by_mat: dict = {}
    for s in stocks:
        total_by_mat[s["material_id"]] = total_by_mat.get(s["material_id"], 0) + float(s.get("qty") or 0)
    low_materials = []
    for mid, total in total_by_mat.items():
        m = mat_by_id.get(mid)
        if not m:
            continue
        if m.get("min_stock") and total < float(m["min_stock"]):
            low_materials.append({"material_id": mid, "material_code": m["code"], "name": m["name"],
                                   "type": m["type"], "unit": m["unit"], "qty": total, "min_stock": m["min_stock"]})
    return {"by_type": by_type, "by_category": by_category, "low_stock_count": len(low_materials), "low_materials": low_materials}


# ──────────────────────────────────────────────────────────────────────────────
# MOVEMENT LEDGER
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/material-movements")
async def list_movements(request: Request, material_id: Optional[str] = None, limit: int = 100):
    await require_auth(request)
    db = get_db()
    q = {}
    if material_id:
        q["material_id"] = material_id
    use_pagination = "page" in request.query_params
    if use_pagination:
        page, pg_limit, pg_skip = get_pagination_params(request, default_limit=50)
        total = await db.rahaza_material_movements.count_documents(q)
        rows = await db.rahaza_material_movements.find(q, {"_id": 0}).sort("created_at", -1).skip(pg_skip).limit(pg_limit).to_list(length=10000)
    else:
        rows = await db.rahaza_material_movements.find(q, {"_id": 0}).sort("created_at", -1).limit(int(limit)).to_list(500)
    m_ids = list({r["material_id"] for r in rows if r.get("material_id")})
    loc_ids = list({x for r in rows for x in (r.get("from_location_id"), r.get("to_location_id")) if x})
    mats = await db.rahaza_materials.find({"id": {"$in": m_ids}}, {"_id": 0}).to_list(MASTER_FETCH_LIMIT) if m_ids else []
    locs = await db.rahaza_locations.find({"id": {"$in": loc_ids}}, {"_id": 0}).to_list(MASTER_FETCH_LIMIT) if loc_ids else []
    l_map = {l["id"]: l for l in locs}
    missing_ids = [lid for lid in loc_ids if lid not in l_map]
    if missing_ids:
        # FASE F+: fallback nama lokasi ke SSOT `wh_zones` (bukan `warehouse_locations` yg di-drop).
        wh_locs = await db.wh_zones.find({"id": {"$in": missing_ids}}, {"_id": 0}).to_list(MASTER_FETCH_LIMIT)
        for wl in wh_locs:
            l_map[wl["id"]] = {"id": wl["id"], "name": wl.get("name") or wl.get("code")}
    m_map = {m["id"]: m for m in mats}
    for r in rows:
        m = m_map.get(r.get("material_id")) or {}
        r["material_code"] = m.get("code")
        r["material_name"] = m.get("name")
        r["unit"] = m.get("unit")
        r["from_location_name"] = (l_map.get(r.get("from_location_id")) or {}).get("name")
        r["to_location_name"]   = (l_map.get(r.get("to_location_id")) or {}).get("name")
    if use_pagination:
        return paginated_response(serialize_doc(rows), total, page, pg_limit)
    return serialize_doc(rows)


# ──────────────────────────────────────────────────────────────────────────────
# OPERATIONS (receive / transfer / adjust)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/material-receive")
async def material_receive(request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    material_id = body.get("material_id")
    location_id = body.get("location_id")
    qty = float(body.get("qty") or 0)
    if not (material_id and location_id) or qty <= 0:
        raise HTTPException(400, "material_id, location_id, qty(>0) wajib diisi.")
    mat = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
    if not mat:
        raise HTTPException(404, "Material tidak ditemukan.")
    # FASE C — dual-read tulisan: terima id lokasi LAMA (rahaza_locations) MAUPUN
    # BARU (wh_zones/wh_positions) selama transisi.
    if not await location_resolver.location_exists(db, location_id):
        raise HTTPException(404, "Location tidak ditemukan.")
    _mtype = (mat.get("type") or "").lower()
    await stock_service.add(
        material_id, location_id, qty,
        meta={"material_type": _mtype or None, "material_code": mat.get("code"),
              "material_name": mat.get("name"), "unit": mat.get("unit"),
              "ownership": "cv_da",
              "inventory_category": "fg_internal" if _mtype == "fg" else "raw_material"},
        ref={"source": "material_receive", "ref_type": body.get("ref_type") or "receiving", "ref_id": body.get("ref_id")},
        actor={"id": str(user.get("id") or ""), "email": user.get("email", "")},
        db=db,
    )
    mv = await _log_movement(db, user,
        type="receive", material_id=material_id, qty=qty,
        unit_cost=float(body.get("unit_cost") or 0),
        from_location_id=None, to_location_id=location_id,
        ref_type=body.get("ref_type") or "receiving", ref_id=body.get("ref_id") or None,
        notes=body.get("notes") or "",
    )
    await log_activity(user["id"], user.get("name", ""), f"receive:{qty}", "rahaza.material", material_id)
    posting_result = None
    try:
        posting_result = await post_inventory_receive(db, mv, user)
    except Exception as e:
        log.exception("Inventory receive auto-post failed")
        posting_result = {"ok": False, "error": str(e)}
    mv_refresh = await db.rahaza_material_movements.find_one({"id": mv["id"]}, {"_id": 0})
    mv_refresh["_posting_result"] = posting_result
    return serialize_doc(mv_refresh)


@router.post("/material-transfer")
async def material_transfer(request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    material_id = body.get("material_id")
    from_loc = body.get("from_location_id")
    to_loc = body.get("to_location_id")
    qty = float(body.get("qty") or 0)
    if not (material_id and from_loc and to_loc) or qty <= 0:
        raise HTTPException(400, "material_id, from_location_id, to_location_id, qty(>0) wajib.")
    if from_loc == to_loc:
        raise HTTPException(400, "Lokasi asal dan tujuan tidak boleh sama.")
    try:
        await stock_service.move(
            material_id, from_loc, to_loc, qty,
            ref={"source": "material_transfer"},
            actor={"id": str(user.get("id") or ""), "email": user.get("email", "")},
            db=db,
        )
    except stock_service.InsufficientStock as e:
        raise HTTPException(400, f"Stok tidak cukup di lokasi asal (tersedia: {e.available}).")
    mv = await _log_movement(db, user,
        type="transfer", material_id=material_id, qty=qty,
        from_location_id=from_loc, to_location_id=to_loc,
        ref_type="transfer", ref_id=None, notes=body.get("notes") or "",
    )
    return serialize_doc(mv)


@router.post("/material-adjust")
async def material_adjust(request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    material_id = body.get("material_id")
    location_id = body.get("location_id")
    delta = float(body.get("qty") or 0)
    reason = body.get("reason") or ""
    if not (material_id and location_id) or delta == 0:
        raise HTTPException(400, "material_id, location_id, qty (≠0) wajib.")
    cur = await db.rahaza_material_stock.find_one({"material_id": material_id, "location_id": location_id}) or {"qty": 0}
    if float(cur.get("qty") or 0) + delta < 0:
        raise HTTPException(400, "Penyesuaian akan membuat stok negatif.")
    _actor = {"id": str(user.get("id") or ""), "email": user.get("email", "")}
    _ref = {"source": "material_adjust", "reason": reason}
    if delta > 0:
        await stock_service.add(material_id, location_id, delta, ref=_ref, actor=_actor, db=db)
    else:
        await stock_service.issue(material_id, location_id, abs(delta), ref=_ref, actor=_actor, db=db)
    mv = await _log_movement(db, user,
        type="adjust", material_id=material_id, qty=delta,
        from_location_id=None, to_location_id=location_id,
        ref_type="adjustment", ref_id=None, notes=reason,
    )
    posting_result = None
    try:
        posting_result = await post_inventory_adjust(db, mv, user)
    except Exception as e:
        log.exception("Inventory adjust auto-post failed")
        posting_result = {"ok": False, "error": str(e)}
    mv_refresh = await db.rahaza_material_movements.find_one({"id": mv["id"]}, {"_id": 0})
    mv_refresh["_posting_result"] = posting_result
    return serialize_doc(mv_refresh)
