"""rahaza_inventory — Materials Master CRUD."""
# ruff: noqa: E741
from fastapi import Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from core import material_fields  # FASE 6.6-B: SSOT nama field + alias legacy yarn_*
from core import uom              # SSOT konversi satuan (multi-UOM berjenjang)
from core import bom_uom          # daftar satuan sah + faktornya (dipakai dropdown UI)
from routes.rahaza_inventory_shared import (
    router, _uid, _now, MATERIAL_TYPES, MATERIAL_UNITS, _require_admin,
    get_pagination_params, paginated_response, DEFAULT_MATERIAL_CATEGORIES,
    MASTER_FETCH_LIMIT,
)
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# MATERIALS MASTER
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/materials")
async def list_materials(request: Request, type: Optional[str] = None, search: Optional[str] = None,
                         low_stock: Optional[str] = None, include_inactive: Optional[str] = None,
                         exclude_type: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {}
    if not (include_inactive and include_inactive.lower() == "true"):
        q["active"] = True
    if type:
        # 3 kategori bisnis (Bahan/Aksesoris/Produk Jadi) → expand ke tipe legacy.
        CAT_GROUPS = {
            "bahan": ["yarn", "fabric", "kain", "benang", "interlining"],
            "aksesoris": ["accessory", "packaging"],
            "fg": ["fg"],
            "produk_jadi": ["fg"],
        }
        if type in CAT_GROUPS:
            q["type"] = {"$in": CAT_GROUPS[type]}
        elif type in MATERIAL_TYPES:
            q["type"] = type
        else:
            raise HTTPException(400, f"type harus: {MATERIAL_TYPES} atau kategori {list(CAT_GROUPS)}")
    # Fase A/P2: kecualikan tipe tertentu (mis. exclude_type=fg utk tab "Bahan & Aksesoris")
    if exclude_type and "type" not in q:
        ex = [t.strip() for t in exclude_type.split(",") if t.strip()]
        if ex:
            q["type"] = {"$nin": ex}
    if search:
        import re
        pattern = re.compile(re.escape(search), re.IGNORECASE)
        q["$or"] = [{"code": pattern}, {"name": pattern}]

    use_pagination = "page" in request.query_params
    if use_pagination:
        page, pg_limit, pg_skip = get_pagination_params(request, default_limit=50)

    if low_stock and low_stock.lower() == "true":
        # W3 — "rendah" TIDAK lagi dihitung di sini. Dulu blok ini menjumlahkan
        # `$qty` saja (⇒ baris stok skema lama yang menyimpan angkanya di
        # `total_qty`/`available_quantity` TIDAK TERBACA, stok terlihat 0) dan
        # memakai urutan ambang sendiri yang berbeda dari layar Alert & Reorder
        # maupun notifikasi. Sekarang SATU definisi dari core/stock_thresholds.
        from core import stock_thresholds as _th
        rows = await db.rahaza_materials.find(q, {"_id": 0}).sort([("type", 1), ("code", 1)]).to_list(MASTER_FETCH_LIMIT)
        ids = [m.get("id") for m in rows if m.get("id")]
        evals = {r["material_id"]: r for r in await _th.evaluate(
            db, material_ids=ids, with_suggestion=False, include_inactive=True)}
        low_rows = []
        for m in rows:
            ev = evals.get(m.get("id"))
            if not ev or ev["status"] not in ("low", "critical"):
                continue
            m["current_qty"] = ev["onhand"]
            m["is_low_stock"] = True
            m["threshold_source"] = ev["threshold_source"]
            m["alert_at"] = ev["alert_at"]
            m["shortage"] = ev["shortage"]
            m["stock_status"] = ev["status"]
            low_rows.append(m)
        if use_pagination:
            total = len(low_rows)
            paged = low_rows[pg_skip:pg_skip + pg_limit]
            return paginated_response(serialize_doc(paged), total, page, pg_limit)
        return serialize_doc(low_rows)

    if use_pagination:
        total = await db.rahaza_materials.count_documents(q)
        rows = await db.rahaza_materials.find(q, {"_id": 0}).sort([("type", 1), ("code", 1)]).skip(pg_skip).limit(pg_limit).to_list(length=10000)
        # FASE 11: response memakai nama KANONIK `composition` saja; bila dokumen lama
        # hanya punya `yarn_type`, nilainya diangkat ke `composition` lalu kunci
        # legacy-nya dibuang dari response.
        rows = [material_fields.with_aliases(r, "composition") for r in rows]
        return paginated_response(serialize_doc(rows), total, page, pg_limit)

    rows = await db.rahaza_materials.find(q, {"_id": 0}).sort([("type", 1), ("code", 1)]).to_list(MASTER_FETCH_LIMIT)
    rows = [material_fields.with_aliases(r, "composition") for r in rows]
    return serialize_doc(rows)


@router.get("/materials/reorder-alerts")
async def list_reorder_alerts(request: Request):
    """Material yang stoknya menyentuh titik pesan ulang / ambang minimum.

    W3: stoknya kini dibaca KANONIK (semua skema baris, semua lokasi) dan
    ambangnya memakai SSOT `core/stock_thresholds` — dulu endpoint ini hanya
    menjumlahkan `$qty` dan hanya melihat `reorder_point`, sehingga material yang
    ambang minimumnya dilanggar tidak pernah muncul di dashboard.
    """
    await require_auth(request)
    db = get_db()
    from core import stock_thresholds as _th
    rows = await _th.evaluate(db, with_suggestion=False)
    by_id = {r["material_id"]: r for r in rows if r["status"] in ("low", "critical")}
    if not by_id:
        return serialize_doc([])
    mats = await db.rahaza_materials.find(
        {"id": {"$in": list(by_id)}}, {"_id": 0}).to_list(MASTER_FETCH_LIMIT)
    alerts = []
    for m in mats:
        ev = by_id[m["id"]]
        alerts.append({**m, "current_qty": ev["onhand"], "shortage": ev["shortage"],
                       "alert_at": ev["alert_at"], "stock_status": ev["status"],
                       "threshold_source": ev["threshold_source"]})
    alerts.sort(key=lambda a: -float(a.get("shortage") or 0))
    return serialize_doc(alerts)


@router.post("/materials")
async def create_material(request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    code = (body.get("code") or "").strip().upper()
    name = (body.get("name") or "").strip()
    t    = (body.get("type") or "").strip().lower()
    unit = (body.get("unit") or "").strip().lower()
    if not code or not name:
        raise HTTPException(400, "code & name wajib diisi.")
    if t not in MATERIAL_TYPES:
        raise HTTPException(400, f"type harus salah satu: {MATERIAL_TYPES}")
    if unit not in MATERIAL_UNITS:
        raise HTTPException(400, f"unit harus salah satu: {MATERIAL_UNITS}")
    if await db.rahaza_materials.find_one({"code": code, "active": True}):
        raise HTTPException(409, f"Kode '{code}' sudah terpakai.")
    
    # Satuan & kemasan — divalidasi + dinormalkan terpusat di core/uom.
    # `apply_payload` mengembalikan `uoms` + cermin field lama (pack_unit/
    # pack_size/display_in_packs) sehingga kode lama tetap bekerja (INV-UOM-4).
    try:
        uom_patch = uom.apply_payload({**body, "unit": unit})
    except uom.UomError as e:
        raise HTTPException(400, f"Satuan tidak valid: {e}")

    doc = {
        "id": _uid(), "code": code, "name": name,
        "type": t, "unit": unit,
        # Fase 1: kategori material (configurable master). Simpan code + nama utk display.
        "category": (body.get("category") or "").strip(),
        "category_name": (body.get("category_name") or "").strip(),
        # FASE 11: `composition` = satu-satunya nama yang DISIMPAN. Alias legacy
        # `yarn_type` sudah tidak ditulis lagi (`WRITE_ALIASES` kosong), tetapi
        # `read_field` masih bisa membacanya dari dokumen lama.
        **material_fields.mirror(
            "composition",
            str(material_fields.read_field(body, "composition", "") or "").strip(),
        ),
        "color": (body.get("color") or "").strip(),
        "notes": body.get("notes") or "",
        "min_stock": float(body.get("min_stock") or 0),
        # FASE 6/7: harga satuan (HPP) — DASAR semua valuasi & jurnal persediaan
        # (post_inventory_receive/issue/adjust, karantina/scrap, nilai stok).
        # Sebelumnya tidak bisa diisi saat create → JE persediaan selalu gagal
        # dengan "Amount = 0 (set unit_cost material)".
        "unit_cost": float(body.get("unit_cost") if body.get("unit_cost") not in (None, "")
                           else (body.get("hpp") or body.get("price") or 0)),
        "min_stock_qty": float(body["min_stock_qty"]) if body.get("min_stock_qty") not in (None, "") else None,
        "min_stock_percentage": float(body["min_stock_percentage"]) if body.get("min_stock_percentage") not in (None, "") else None,
        "reorder_point": float(body.get("reorder_point") or 0),
        # 2026-08-02 · Kain: gramasi (g/m²) & lebar (cm). Dipakai core/bom_uom untuk
        # konversi meter ⇄ kg — kain rajut DIBELI per kg tapi DIPAKAI per meter,
        # tanpa dua angka ini biaya kain di BOM/HPP tidak bisa dihitung benar.
        "gsm": float(body["gsm"]) if body.get("gsm") not in (None, "") else None,
        "width_cm": float(body["width_cm"]) if body.get("width_cm") not in (None, "") else None,
        # Satuan & kemasan (uoms + cermin pack_*) — SSOT di core/uom
        **uom_patch,
        "active": True,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_materials.insert_one(doc)
    # Harga awal (opsional) ditandai `opening` supaya bedanya dengan harga yang
    # LAHIR DARI PEMBELIAN selalu kelihatan di layar (2026-08-21).
    if float(doc.get("unit_cost") or 0) > 0:
        await db.rahaza_materials.update_one(
            {"id": doc["id"]}, {"$set": {"cost_method": "opening"}})
        doc["cost_method"] = "opening"
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.material", code)
    return serialize_doc(doc)


@router.put("/materials/{mid}")
async def update_material(mid: str, request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    body.pop("_id", None)
    body.pop("id", None)
    body.pop("created_at", None)
    body["updated_at"] = _now()
    if "code" in body:
        body["code"] = body["code"].strip().upper()
    if "type" in body and body["type"] not in MATERIAL_TYPES:
        raise HTTPException(400, f"type harus: {MATERIAL_TYPES}")
    if "unit" in body and body["unit"] not in MATERIAL_UNITS:
        raise HTTPException(400, f"unit harus: {MATERIAL_UNITS}")
    if "min_stock_qty" in body:
        body["min_stock_qty"] = float(body["min_stock_qty"]) if body["min_stock_qty"] else None
    if "min_stock_percentage" in body:
        body["min_stock_percentage"] = float(body["min_stock_percentage"]) if body["min_stock_percentage"] else None
    # W3 — titik pesan ulang bisa diubah dari Master Item (bukan hanya layar Ambang Stok)
    if "reorder_point" in body:
        try:
            body["reorder_point"] = float(body["reorder_point"] or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, "reorder_point harus berupa angka.")
        if body["reorder_point"] < 0:
            raise HTTPException(400, "reorder_point tidak boleh negatif.")
    # 2026-08-02 · gramasi & lebar kain (konversi meter ⇄ kg di core/bom_uom)
    for _k in ("gsm", "width_cm"):
        if _k in body:
            try:
                body[_k] = float(body[_k]) if body[_k] not in (None, "") else None
            except (TypeError, ValueError):
                raise HTTPException(400, f"{_k} harus berupa angka.")
            if body[_k] is not None and body[_k] < 0:
                raise HTTPException(400, f"{_k} tidak boleh negatif.")
    # HARGA SATUAN (HPP) — keputusan pemilik 2026-08-21: **tidak lagi diketik di
    # Master Item**. Harga terbentuk otomatis dari HARGA PEMBELIAN (PO → GR,
    # rata-rata bergerak di core/accessory_valuation). Perubahan `unit_cost` yang
    # dikirim dari layar master DIABAIKAN — bukan dipakai diam-diam — dan
    # jawabannya menyebut jalan yang benar untuk koreksi (agar ada jejak audit).
    _cost_note = ""
    if "unit_cost" in body or "hpp" in body or "price" in body:
        try:
            _uc = body.get("unit_cost")
            if _uc in (None, ""):
                _uc = body.get("hpp") if body.get("hpp") not in (None, "") else body.get("price")
            _uc = float(_uc or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, "unit_cost harus berupa angka.")
        if _uc < 0:
            raise HTTPException(400, "unit_cost tidak boleh negatif.")
        body.pop("unit_cost", None)
        body.pop("hpp", None)
        body.pop("price", None)
        # Catatannya SELALU dikirim saat layar mengirim field harga — termasuk bila
        # angkanya sama. Kalau hanya muncul saat berbeda, operator yang mengetik
        # angka yang sama tidak akan pernah tahu master menolak input harga.
        _cost_note = (
            "Harga satuan TIDAK diubah dari Master Item. Harga terbentuk otomatis dari "
            "harga pembelian (PO → Penerimaan Barang, rata-rata bergerak). Untuk koreksi "
            "manual bernilai audit, pakai Aksesoris → Valuasi HPP → Set HPP."
        )
    
    # Satuan & kemasan — hanya diproses bila salah satu field satuan dikirim,
    # supaya PATCH parsial (mis. hanya ubah nama) tidak menyentuh `uoms`.
    if any(k in body for k in ("uoms", "unit", "base_uom", "pack_unit", "pack_size",
                               "display_in_packs", "purchase_uom", "issue_uom", "display_uom")):
        current = await db.rahaza_materials.find_one({"id": mid}, {"_id": 0})
        if not current:
            raise HTTPException(404, "Material tidak ditemukan.")
        try:
            body.update(uom.apply_payload(body, current))
        except uom.UomError as e:
            raise HTTPException(400, f"Satuan tidak valid: {e}")

    # FASE 11: masih MENERIMA `composition` (kanonik) ATAU `yarn_type` (legacy)
    # dari klien, tetapi yang DISIMPAN hanya nama kanonik.
    _comp = material_fields.mirror_from_body(body, "composition")
    if _comp:
        body.pop("yarn_type", None)
        body.pop("composition", None)
        body.update({k: (str(v or "").strip()) for k, v in _comp.items()})
    
    res = await db.rahaza_materials.update_one({"id": mid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Material tidak ditemukan.")
    await log_activity(user["id"], user.get("name", ""), "update", "rahaza.material", mid)
    out = serialize_doc(await db.rahaza_materials.find_one({"id": mid}, {"_id": 0}))
    if _cost_note:
        out["harga_satuan_catatan"] = _cost_note
    return out


@router.delete("/materials/{mid}")
async def deactivate_material(mid: str, request: Request):
    await _require_admin(request)
    db = get_db()
    await db.rahaza_materials.update_one({"id": mid}, {"$set": {"active": False, "updated_at": _now()}})
    return {"status": "deactivated"}


# ──────────────────────────────────────────────────────────────────────────────
# MATERIAL CATEGORIES MASTER (configurable) — Fase 1
# ──────────────────────────────────────────────────────────────────────────────

async def _ensure_material_categories(db):
    """Lazy-seed kategori default bila koleksi masih kosong."""
    if await db.rahaza_material_categories.count_documents({}) == 0:
        docs = [{
            "id": _uid(), "code": c["code"], "name": c["name"],
            "order_seq": c["order_seq"], "active": True,
            "created_at": _now(), "updated_at": _now(),
        } for c in DEFAULT_MATERIAL_CATEGORIES]
        if docs:
            await db.rahaza_material_categories.insert_many(docs)


@router.get("/material-categories")
async def list_material_categories(request: Request, include_inactive: bool = False):
    await require_auth(request)
    db = get_db()
    await _ensure_material_categories(db)
    q = {} if include_inactive else {"active": True}
    rows = await db.rahaza_material_categories.find(q, {"_id": 0}).sort("order_seq", 1).to_list(200)
    return serialize_doc(rows)


@router.post("/material-categories")
async def create_material_category(request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Nama kategori wajib diisi.")
    code = (body.get("code") or name).strip().upper().replace(" ", "_")
    if await db.rahaza_material_categories.find_one({"code": code, "active": True}):
        raise HTTPException(409, f"Kategori '{code}' sudah ada.")
    doc = {
        "id": _uid(), "code": code, "name": name,
        "order_seq": int(body.get("order_seq") or 50),
        "active": True, "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_material_categories.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.material_category", code)
    return serialize_doc(doc)


@router.put("/material-categories/{cid}")
async def update_material_category(cid: str, request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    upd = {"updated_at": _now()}
    if "name" in body:
        upd["name"] = (body["name"] or "").strip()
    if "order_seq" in body:
        upd["order_seq"] = int(body.get("order_seq") or 50)
    if "active" in body:
        upd["active"] = bool(body["active"])
    res = await db.rahaza_material_categories.update_one({"id": cid}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Kategori tidak ditemukan.")
    await log_activity(user["id"], user.get("name", ""), "update", "rahaza.material_category", cid)
    return serialize_doc(await db.rahaza_material_categories.find_one({"id": cid}, {"_id": 0}))


@router.delete("/material-categories/{cid}")
async def deactivate_material_category(cid: str, request: Request):
    await _require_admin(request)
    db = get_db()
    await db.rahaza_material_categories.update_one({"id": cid}, {"$set": {"active": False, "updated_at": _now()}})
    return {"status": "deactivated"}


# ═════════════════════════════════════════════════════════════════════════════
# UBAH SATUAN DASAR (rebase UOM) — aksi terkontrol & ber-audit
# ═════════════════════════════════════════════════════════════════════════════
# LATAR: 91 aksesoris memakai satuan KEMASAN sebagai satuan dasar
# (74 `rol`, 14 `pak`, 3 `lusin`). Contoh `A1 Bisban` berstok 9 dengan satuan
# `rol`. Kalau satuan dasarnya diubah jadi `m` begitu saja, angka 9 mendadak
# dibaca sebagai 9 METER (seharusnya 450 m) → korupsi data senyap.
#
# Karena itu perubahan satuan dasar TIDAK pernah otomatis (INV-UOM-5).
# Endpoint ini:
#   1. `?preview=true` → hanya menghitung dampaknya, TIDAK menulis apa pun
#   2. tanpa preview   → mengonversi SEMUA baris stok + unit_cost + min_stock,
#      menulis baris ledger `op="uom_rebase"` berisi nilai sebelum/sesudah
#      sehingga dapat ditelusuri dan dibatalkan.

@router.post("/materials/{mid}/rebase-uom")
async def rebase_material_uom(mid: str, request: Request):
    """Ubah satuan dasar material beserta konversi seluruh angka terkait.

    Body:
      new_base_uom : str    — satuan dasar baru (mis. "m")
      factor       : float  — 1 <satuan dasar LAMA> = factor <satuan BARU>
                              (mis. 1 rol = 50 m → factor 50)
      keep_old_as_pack : bool = True — satuan lama tetap tersedia sbg kemasan
      preview      : bool = False
    """
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()

    mat = await db.rahaza_materials.find_one({"id": mid}, {"_id": 0})
    if not mat:
        raise HTTPException(404, "Material tidak ditemukan.")

    old_base = uom.base_uom_of(mat)
    new_base = uom.normalize_code(body.get("new_base_uom"))
    if not new_base:
        raise HTTPException(400, "new_base_uom wajib diisi.")
    if new_base == old_base:
        raise HTTPException(400, f"Satuan dasar sudah '{old_base}'.")
    try:
        factor = float(body.get("factor") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "factor harus berupa angka.")
    if factor <= 0:
        raise HTTPException(400, "factor harus lebih besar dari 0.")

    keep_old = bool(body.get("keep_old_as_pack", True))
    preview = bool(body.get("preview"))

    rows = await db.rahaza_material_stock.find({"material_id": mid}, {"_id": 0}).to_list(1000)
    qty_before = round(sum(float(r.get("qty") or 0) for r in rows), 4)
    cost_before = float(mat.get("unit_cost") or 0)
    min_before = float(mat.get("min_stock") or 0)

    after = {
        "qty": round(qty_before * factor, 4),
        # harga per satuan LAMA dibagi factor → harga per satuan BARU
        "unit_cost": round(cost_before / factor, 6) if factor else cost_before,
        "min_stock": round(min_before * factor, 4),
    }

    # Susun daftar UOM baru: satuan baru jadi dasar, satuan lama jadi kemasan.
    new_rows = [{"code": new_base, "factor": 1, "is_base": True}]
    if keep_old:
        new_rows.append({"code": old_base, "factor": factor, "parent": new_base,
                         "is_purchase_default": True, "is_display_default": True,
                         "notes": f"1 {old_base} = {factor:g} {new_base}"})
    # kemasan lama yang lain ikut diskalakan (faktornya tetap relatif ke dasar)
    for r in uom.resolve_uoms(mat):
        c = uom.normalize_code(r.get("code"))
        if c in (old_base, new_base):
            continue
        new_rows.append({"code": c, "factor": round(float(r["factor"]) * factor, 6),
                         "name": r.get("name"), "notes": r.get("notes")})
    new_rows = uom.sanitize_uoms(new_rows, new_base)

    result = {
        "material_id": mid,
        "code": mat.get("code"),
        "name": mat.get("name"),
        "from_uom": old_base,
        "to_uom": new_base,
        "factor": factor,
        "stock_rows": len(rows),
        "before": {"total_qty": qty_before, "unit_cost": cost_before, "min_stock": min_before,
                   "uoms": [{"code": r["code"], "factor": r["factor"]} for r in uom.resolve_uoms(mat)]},
        "after": {"total_qty": after["qty"], "unit_cost": after["unit_cost"],
                  "min_stock": after["min_stock"],
                  "uoms": [{"code": r["code"], "factor": r["factor"]} for r in new_rows]},
        "nilai_persediaan_tetap": round(qty_before * cost_before, 2) == round(after["qty"] * after["unit_cost"], 2),
        "preview": preview,
    }
    if preview:
        return serialize_doc(result)

    # ── TULIS ────────────────────────────────────────────────────────────────
    from core import stock_service  # impor lokal: hindari siklus impor
    for r in rows:
        old_qty = float(r.get("qty") or 0)
        new_qty = round(old_qty * factor, 4)
        await db.rahaza_material_stock.update_one(
            {"material_id": mid, "location_id": r.get("location_id")},
            [{"$set": {
                "qty": new_qty,
                "reserved_quantity": {"$round": [{"$multiply": [
                    {"$ifNull": ["$reserved_quantity", 0]}, factor]}, 4]},
                "unit": new_base,
                "updated_at": _now(),
            }}, {"$set": {
                "total_qty": "$qty", "quantity": "$qty",
                "available_quantity": {"$round": [
                    {"$subtract": ["$qty", {"$ifNull": ["$reserved_quantity", 0]}]}, 4]},
            }}],
        )
        await db.rahaza_stock_ledger.insert_one({
            "id": _uid(), "op": "uom_rebase", "material_id": mid,
            "location_id": r.get("location_id"),
            "delta": round(new_qty - old_qty, 4), "qty_after": new_qty,
            "ref": {"source": "rebase_uom", "from_uom": old_base,
                    "to_uom": new_base, "factor": factor},
            "actor": {"id": str(user.get("id") or ""), "email": user.get("email", "")},
            "qty_before": old_qty, "input_uom": old_base, "uom_factor": factor,
            "created_at": _now(),
        })

    patch = {"unit": new_base, "unit_cost": after["unit_cost"], "min_stock": after["min_stock"],
             "uoms": new_rows, "updated_at": _now()}
    patch.update(uom.mirror_legacy(new_rows, new_base))
    patch["purchase_uom"] = old_base if keep_old else new_base
    patch["issue_uom"] = new_base
    patch["display_uom"] = old_base if keep_old else new_base
    await db.rahaza_materials.update_one({"id": mid}, {"$set": patch})

    await log_activity(user["id"], user.get("name", ""), "rebase_uom", "rahaza.material",
                       f"{mat.get('code')}: {old_base} → {new_base} (×{factor})")
    result["applied"] = True
    result["ledger_rows_written"] = len(rows)
    return serialize_doc(result)


# ──────────────────────────────────────────────────────────────────────────────
# SATUAN (UoM) — OPSI UNTUK DROPDOWN DI SEMUA TITIK MASUK/KELUAR STOK
#
# 2026-08-05. Backend sudah lama menerima `input_uom` / `qty_uom` / `counted_uom`,
# tetapi LAYARNYA tidak punya pemilih satuan sehingga operator hanya bisa
# memasukkan satuan dasar (ROADMAP P1). Endpoint ini menyediakan daftar satuan
# SAH + faktornya untuk satu atau banyak material sekaligus, supaya UI bisa:
#   1) menampilkan dropdown satuan yang PASTI bisa dikonversi server, dan
#   2) menunjukkan pratinjau "3 box = 36 pcs" SEBELUM disimpan.
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/materials/uom-options")
async def materials_uom_options(request: Request, material_ids: str = "", material_id: str = ""):
    """Daftar satuan sah + faktor ke satuan dasar untuk 1..N material.

    `material_ids` = daftar id dipisah koma (maks 200). `material_id` = bentuk
    tunggal (alias). Material yang tidak ditemukan dikembalikan di `missing`.
    """
    await require_auth(request)
    db = get_db()
    ids = [x.strip() for x in f"{material_ids},{material_id}".split(",") if x.strip()]
    if not ids:
        raise HTTPException(400, "material_ids wajib diisi")
    ids = list(dict.fromkeys(ids))[:200]
    rows = await db.rahaza_materials.find({"id": {"$in": ids}}, {"_id": 0}).to_list(length=len(ids))
    # Alias satuan global yang artinya sama (gr/g = gram, kgs/kilo = kg, …) —
    # disembunyikan dari dropdown supaya operator tidak bingung memilih.
    alias_hidden = {
        "gr", "g", "kgs", "kilo", "lbs", "oz", "mg",
        "metre", "meter", "mtr", "inci", '"', "feet", "yd", "yds", "dm", "km",
        "pc", "piece", "buah", "unit", "sheet", "helai", "batang", "pair",
        "dozen", "dz", "dus_lusin", "grosir", "rim",
        "cc", "ltr", "l", "gallon", "sqm", "inch2",
    }
    out = {}
    for m in rows:
        base = bom_uom.norm_unit(m.get("base_uom") or m.get("unit") or "pcs")
        units, seen_factor = [], set()
        for u in bom_uom.allowed_units(m):
            if u.get("source") == "global":
                if u["unit"] in alias_hidden or u["unit"] == base:
                    continue
                fkey = round(float(u.get("factor_to_base") or 0), 8)
                if fkey in seen_factor:
                    continue
                seen_factor.add(fkey)
            units.append(u)
        out[m["id"]] = {
            "material_id": m["id"],
            "code": m.get("code") or "",
            "name": m.get("name") or "",
            "base_unit": base,
            "unit_cost": float(m.get("unit_cost") or 0),
            "units": units,
            "has_fabric_dims": bool(bom_uom.fabric_kg_per_meter(m)),
        }
    return serialize_doc({
        "options": out,
        "missing": [i for i in ids if i not in out],
        "hint": ("Satuan di luar daftar tidak bisa dikonversi otomatis — tambahkan kemasannya "
                 "di Master Material (Satuan & Kemasan), atau untuk kain lengkapi gramasi & lebar."),
    })


# ══════════════════════════════════════════════════════════════════════════════
# GET SATU MATERIAL — HARUS TETAP MENJADI ROUTE TERAKHIR DI BERKAS INI
# ══════════════════════════════════════════════════════════════════════════════
# Ditambahkan 2026-08-17 (sesi #17) menutup temuan uji: `GET /api/rahaza/materials/{id}`
# membalas **405 Method Not Allowed** — pathnya ada (PUT/DELETE) tetapi GET-nya tidak,
# sehingga siapa pun yang mengintegrasikan API ini (mis. aplikasi lapangan) mendapat
# jawaban yang tidak menjelaskan apa pun. Sekarang simetris dengan
# `GET /material-issues/{mid}` yang sudah ada.
#
# ⚠️ KENAPA HARUS DI BARIS PALING BAWAH (pelajaran sesi #16, jangan diulang):
# berkas ini mendeklarasikan DUA route LITERAL di bawah prefix yang sama —
# `GET /materials/reorder-alerts` (baris 107) dan `GET /materials/uom-options`
# (baris 496). FastAPI mencocokkan route menurut URUTAN DEKLARASI, jadi kalau
# `GET /materials/{mid}` diletakkan sebelum salah satunya, route literal itu akan
# tertangkap sebagai `mid="uom-options"` dan mati DIAM-DIAM (dropdown satuan di
# seluruh layar berhenti bekerja tanpa satu pun galat di log).
@router.get("/materials/{mid}")
async def get_material(mid: str, request: Request):
    """Satu material master + ringkasan stoknya (read-only)."""
    await require_auth(request)
    db = get_db()
    m = await db.rahaza_materials.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Material tidak ditemukan.")
    # Sama seperti `list_materials`: alias legacy (`yarn_*`) tetap ikut supaya
    # pemanggil lama tidak kehilangan field.
    m = material_fields.with_aliases(m, "composition")
    rows = await db.rahaza_material_stock.find(
        {"material_id": mid}, {"_id": 0, "location_id": 1, "qty": 1}).to_list(MASTER_FETCH_LIMIT)
    loc_ids = [r.get("location_id") for r in rows if r.get("location_id")]
    locs = {}
    if loc_ids:
        async for loc in db.rahaza_locations.find({"id": {"$in": loc_ids}},
                                                 {"_id": 0, "id": 1, "code": 1, "name": 1}):
            locs[loc["id"]] = loc
    m["stock_by_location"] = [{
        "location_id": r.get("location_id"),
        "location_code": (locs.get(r.get("location_id")) or {}).get("code", ""),
        "location_name": (locs.get(r.get("location_id")) or {}).get("name", ""),
        "qty": round(float(r.get("qty") or 0), 4),
    } for r in rows]
    m["onhand_total"] = round(sum(x["qty"] for x in m["stock_by_location"]), 4)
    return serialize_doc(m)
