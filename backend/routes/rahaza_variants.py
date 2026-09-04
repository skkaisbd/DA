"""
PT Rahaza — Fase 2 (Master Product Refactor): Warna (Colors) + Varian Model + SKU.

Prinsip: Product = header model (rahaza_models). Varian = kombinasi Warna × Size,
masing-masing punya SKU unik. SKU otomatis: {model.code}-{color.code}-{size.code}.

Endpoints (prefix /api/rahaza):
  Colors (master DINAMIS, configurable via UI):
    GET    /colors                                 : List (seed lazy palet techpack)
    POST   /colors                                 : Create
    PUT    /colors/{cid}                           : Update
    DELETE /colors/{cid}                           : Soft delete
  Model Variants:
    GET    /variants                               : List (filter model_id / include_inactive)
    GET    /models/{model_id}/variants             : List varian per model (enriched)
    POST   /models/{model_id}/variants/generate    : Generate matriks (color_ids × size_ids) → SKU auto
    POST   /variants                               : Create single variant
    PUT    /variants/{vid}                          : Update (active/barcode/notes)
    DELETE /variants/{vid}                          : Soft delete

Schema rahaza_colors:   {id, code, name, hex, order_seq, active, created_at, updated_at}
Schema rahaza_model_variants:
  {id, model_id, model_code, size_id, size_code, color_id, color_code, color_name,
   sku(UNIQUE aktif), barcode?, notes?, active, created_at, updated_at}
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from utils.variant_ssot import ensure_fg_material
from core import product_master as pm  # K-9a: varian dihentikan ⇒ item katalog nonaktif
import uuid
from datetime import datetime, timezone
from typing import Optional

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-variants"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


# ── Palet warna standar (techpack) — seed awal, bisa ditambah/hapus via UI ──
DEFAULT_COLORS = [
    {"code": "PTH", "name": "Putih",     "hex": "#FFFFFF", "order_seq": 1},
    {"code": "HTM", "name": "Hitam",     "hex": "#1A1A1A", "order_seq": 2},
    {"code": "ABU", "name": "Abu-abu",   "hex": "#9CA3AF", "order_seq": 3},
    {"code": "NVY", "name": "Navy",      "hex": "#1E3A5F", "order_seq": 4},
    {"code": "BIR", "name": "Biru",      "hex": "#2563EB", "order_seq": 5},
    {"code": "MRH", "name": "Merah",     "hex": "#DC2626", "order_seq": 6},
    {"code": "MRN", "name": "Maroon",    "hex": "#7F1D1D", "order_seq": 7},
    {"code": "HJU", "name": "Hijau",     "hex": "#16A34A", "order_seq": 8},
    {"code": "TSK", "name": "Tosca",     "hex": "#14B8A6", "order_seq": 9},
    {"code": "KNG", "name": "Kuning",    "hex": "#FACC15", "order_seq": 10},
    {"code": "ORG", "name": "Oranye",    "hex": "#EA580C", "order_seq": 11},
    {"code": "PNK", "name": "Pink",      "hex": "#EC4899", "order_seq": 12},
    {"code": "UNG", "name": "Ungu",      "hex": "#7C3AED", "order_seq": 13},
    {"code": "CKL", "name": "Coklat",    "hex": "#78350F", "order_seq": 14},
    {"code": "KRM", "name": "Krem",      "hex": "#F5E6D3", "order_seq": 15},
]


async def _require_admin(request: Request):
    """RBAC master product (keputusan user): SEMUA staff internal boleh CRUD.
    Hanya role eksternal (vendor/klien) yang ditolak."""
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("cmt_vendor", "vendor", "klien_maklon"):
        raise HTTPException(403, "Akses master hanya untuk staff internal.")
    return user


# ══════════════════════════════ COLORS MASTER ══════════════════════════════

async def _ensure_colors(db):
    """Lazy-seed palet warna default bila koleksi masih kosong."""
    if await db.rahaza_colors.count_documents({}) == 0:
        docs = [{
            "id": _uid(), "code": c["code"], "name": c["name"], "hex": c["hex"],
            "order_seq": c["order_seq"], "active": True,
            "created_at": _now(), "updated_at": _now(),
        } for c in DEFAULT_COLORS]
        if docs:
            await db.rahaza_colors.insert_many(docs)


@router.get("/colors")
async def list_colors(request: Request, include_inactive: bool = False):
    await require_auth(request)
    db = get_db()
    await _ensure_colors(db)
    q = {} if include_inactive else {"active": True}
    rows = await db.rahaza_colors.find(q, {"_id": 0}).sort("order_seq", 1).to_list(300)
    return serialize_doc(rows)


@router.post("/colors")
async def create_color(request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Nama warna wajib diisi.")
    # code = singkatan (dipakai di SKU). Default: 3 huruf pertama nama (upper).
    code = (body.get("code") or name[:3]).strip().upper().replace(" ", "")
    if not code:
        raise HTTPException(400, "Kode warna wajib diisi.")
    if await db.rahaza_colors.find_one({"code": code, "active": True}):
        raise HTTPException(409, f"Kode warna '{code}' sudah dipakai. Gunakan kode lain.")
    hex_val = (body.get("hex") or "#CCCCCC").strip()
    if not hex_val.startswith("#"):
        hex_val = "#" + hex_val
    doc = {
        "id": _uid(), "code": code, "name": name, "hex": hex_val,
        "order_seq": int(body.get("order_seq") or 50),
        "active": True, "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_colors.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.color", code)
    return serialize_doc(doc)


@router.put("/colors/{cid}")
async def update_color(cid: str, request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    upd = {"updated_at": _now()}
    if "name" in body:
        upd["name"] = (body["name"] or "").strip()
    if "code" in body:
        new_code = (body["code"] or "").strip().upper().replace(" ", "")
        if new_code:
            dup = await db.rahaza_colors.find_one({"code": new_code, "active": True, "id": {"$ne": cid}})
            if dup:
                raise HTTPException(409, f"Kode warna '{new_code}' sudah dipakai.")
            upd["code"] = new_code
    if "hex" in body:
        h = (body["hex"] or "").strip()
        if h and not h.startswith("#"):
            h = "#" + h
        upd["hex"] = h
    if "order_seq" in body:
        upd["order_seq"] = int(body.get("order_seq") or 50)
    if "active" in body:
        upd["active"] = bool(body["active"])
    res = await db.rahaza_colors.update_one({"id": cid}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Warna tidak ditemukan.")
    await log_activity(user["id"], user.get("name", ""), "update", "rahaza.color", cid)
    return serialize_doc(await db.rahaza_colors.find_one({"id": cid}, {"_id": 0}))


@router.delete("/colors/{cid}")
async def deactivate_color(cid: str, request: Request):
    user = await _require_admin(request)
    db = get_db()
    # Guard: cegah nonaktif bila warna dipakai varian aktif (jaga integritas SKU)
    in_use = await db.rahaza_model_variants.count_documents({"color_id": cid, "active": True})
    if in_use > 0:
        raise HTTPException(400, f"Warna dipakai oleh {in_use} varian aktif. Hapus/nonaktifkan varian terkait dulu.")
    res = await db.rahaza_colors.update_one({"id": cid}, {"$set": {"active": False, "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "Warna tidak ditemukan.")
    await log_activity(user["id"], user.get("name", ""), "deactivate", "rahaza.color", cid)
    return {"status": "deactivated"}


# ══════════════════════════════ MODEL VARIANTS ══════════════════════════════

def _make_sku(model_code: str, color_code: str, size_code: str) -> str:
    parts = [str(model_code or "").strip().upper(),
             str(color_code or "").strip().upper(),
             str(size_code or "").strip().upper()]
    return "-".join(p for p in parts if p)


async def _enrich_variant(db, v, model=None, colors_map=None, sizes_map=None):
    """Pastikan denormalized fields (model_code/size_code/color_*) terisi."""
    if not v:
        return v
    if not v.get("model_code"):
        model = model or await db.rahaza_models.find_one({"id": v.get("model_id")}, {"_id": 0})
        v["model_code"] = (model or {}).get("code")
        v["model_name"] = (model or {}).get("name")
    return v


@router.get("/variants")
async def list_variants(request: Request, model_id: Optional[str] = None, include_inactive: bool = False):
    await require_auth(request)
    db = get_db()
    q = {} if include_inactive else {"active": True}
    if model_id:
        q["model_id"] = model_id
    rows = await db.rahaza_model_variants.find(q, {"_id": 0}).sort("sku", 1).to_list(2000)
    return serialize_doc(rows)


@router.get("/models/{model_id}/variants")
async def list_model_variants(model_id: str, request: Request, include_inactive: bool = False):
    await require_auth(request)
    db = get_db()
    model = await db.rahaza_models.find_one({"id": model_id}, {"_id": 0})
    if not model:
        raise HTTPException(404, "Model tidak ditemukan.")
    q = {"model_id": model_id} if include_inactive else {"model_id": model_id, "active": True}
    rows = await db.rahaza_model_variants.find(q, {"_id": 0}).sort([("color_code", 1), ("size_code", 1)]).to_list(2000)
    return serialize_doc({
        "model": {"id": model["id"], "code": model["code"], "name": model["name"]},
        "variants": rows,
        "count": len(rows),
    })


@router.post("/models/{model_id}/variants/generate")
async def generate_variants(model_id: str, request: Request):
    """Generate matriks varian dari kombinasi color_ids × size_ids → SKU otomatis.
    Body: { color_ids: [..], size_ids: [..] (opsional=semua size aktif) }
    Idempoten: kombinasi (model,size,color) yang sudah ada → dilewati."""
    user = await _require_admin(request)
    db = get_db()
    model = await db.rahaza_models.find_one({"id": model_id}, {"_id": 0})
    if not model:
        raise HTTPException(404, "Model tidak ditemukan.")
    body = await request.json()
    color_ids = body.get("color_ids") or []
    if not color_ids:
        raise HTTPException(400, "Pilih minimal 1 warna.")
    size_ids = body.get("size_ids") or []

    # Resolve colors
    colors = await db.rahaza_colors.find({"id": {"$in": color_ids}, "active": True}, {"_id": 0}).to_list(300)
    if not colors:
        raise HTTPException(400, "Warna terpilih tidak valid/aktif.")
    # Resolve sizes (default: semua size aktif)
    if size_ids:
        sizes = await db.rahaza_sizes.find({"id": {"$in": size_ids}, "active": {"$ne": False}}, {"_id": 0}).sort("order_seq", 1).to_list(300)
    else:
        sizes = await db.rahaza_sizes.find({"active": {"$ne": False}}, {"_id": 0}).sort("order_seq", 1).to_list(300)
    if not sizes:
        raise HTTPException(400, "Tidak ada size aktif.")

    # Prefetch existing variants for this model (active) → idempotent skip
    existing = await db.rahaza_model_variants.find({"model_id": model_id, "active": True}, {"_id": 0}).to_list(5000)
    existing_combo = {(e.get("size_id"), e.get("color_id")) for e in existing}
    existing_sku = {e.get("sku") for e in existing}

    created, skipped = [], []
    to_insert = []
    for color in colors:
        for size in sizes:
            combo = (size["id"], color["id"])
            if combo in existing_combo:
                skipped.append({"size_code": size.get("code"), "color_code": color.get("code"), "reason": "sudah ada"})
                continue
            sku = _make_sku(model.get("code"), color.get("code"), size.get("code"))
            if sku in existing_sku or any(d["sku"] == sku for d in to_insert):
                skipped.append({"size_code": size.get("code"), "color_code": color.get("code"), "reason": f"SKU '{sku}' bentrok"})
                continue
            doc = {
                "id": _uid(),
                "model_id": model_id, "model_code": model.get("code"), "model_name": model.get("name"),
                "size_id": size["id"], "size_code": size.get("code"),
                "color_id": color["id"], "color_code": color.get("code"), "color_name": color.get("name"),
                "color_hex": color.get("hex"),
                "sku": sku, "barcode": "", "notes": "",
                "active": True, "created_at": _now(), "updated_at": _now(),
            }
            to_insert.append(doc)
            created.append({"sku": sku, "size_code": size.get("code"), "color_code": color.get("code")})
    if to_insert:
        await db.rahaza_model_variants.insert_many(to_insert)
        await log_activity(user["id"], user.get("name", ""), "generate_variants", "rahaza.model", model_id)
        # GAP-4: auto-create FG master (rahaza_materials type='fg', code==sku) per varian, stok 0.
        for v in to_insert:
            try:
                await ensure_fg_material(db, v, user=user)
            except Exception:
                import logging
                logging.getLogger(__name__).exception("ensure_fg_material gagal utk varian %s", v.get("sku"))
    return {"created": created, "skipped": skipped, "created_count": len(created), "skipped_count": len(skipped)}


@router.post("/variants")
async def create_variant(request: Request):
    """Create single variant (pilih model + warna + size → SKU auto)."""
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    model_id = body.get("model_id")
    size_id = body.get("size_id")
    color_id = body.get("color_id")
    if not (model_id and size_id and color_id):
        raise HTTPException(400, "model_id, size_id, color_id wajib diisi.")
    model = await db.rahaza_models.find_one({"id": model_id}, {"_id": 0})
    size = await db.rahaza_sizes.find_one({"id": size_id}, {"_id": 0})
    color = await db.rahaza_colors.find_one({"id": color_id}, {"_id": 0})
    if not model:
        raise HTTPException(404, "Model tidak ditemukan.")
    if not size:
        raise HTTPException(404, "Size tidak ditemukan.")
    if not color:
        raise HTTPException(404, "Warna tidak ditemukan.")
    # Idempotent: cek kombinasi
    dup = await db.rahaza_model_variants.find_one(
        {"model_id": model_id, "size_id": size_id, "color_id": color_id, "active": True}, {"_id": 0})
    if dup:
        raise HTTPException(409, f"Varian {dup.get('sku')} sudah ada.")
    sku = (body.get("sku") or _make_sku(model.get("code"), color.get("code"), size.get("code"))).strip().upper()
    if await db.rahaza_model_variants.find_one({"sku": sku, "active": True}):
        raise HTTPException(409, f"SKU '{sku}' sudah dipakai.")
    doc = {
        "id": _uid(),
        "model_id": model_id, "model_code": model.get("code"), "model_name": model.get("name"),
        "size_id": size_id, "size_code": size.get("code"),
        "color_id": color_id, "color_code": color.get("code"), "color_name": color.get("name"),
        "color_hex": color.get("hex"),
        "sku": sku, "barcode": (body.get("barcode") or "").strip(), "notes": body.get("notes") or "",
        "active": True, "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_model_variants.insert_one(doc)
    # GAP-4: auto-create FG master (code==sku) untuk varian tunggal, stok 0.
    try:
        await ensure_fg_material(db, doc, user=user)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("ensure_fg_material gagal utk varian %s", doc.get("sku"))
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.variant", sku)
    return serialize_doc(doc)


@router.put("/variants/{vid}")
async def update_variant(vid: str, request: Request):
    """Update varian: barcode/notes/active. (size/color/sku tidak diubah di sini —
    ganti varian = hapus & generate ulang untuk jaga konsistensi SKU)."""
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    upd = {"updated_at": _now()}
    if "barcode" in body:
        upd["barcode"] = (body["barcode"] or "").strip()
    if "notes" in body:
        upd["notes"] = body.get("notes") or ""
    if "active" in body:
        upd["active"] = bool(body["active"])
    res = await db.rahaza_model_variants.update_one({"id": vid}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Varian tidak ditemukan.")
    await log_activity(user["id"], user.get("name", ""), "update", "rahaza.variant", vid)
    return serialize_doc(await db.rahaza_model_variants.find_one({"id": vid}, {"_id": 0}))


@router.delete("/variants/{vid}")
async def deactivate_variant(vid: str, request: Request):
    """Nonaktifkan varian (SKU). **K-9a**: item katalog yang menawarkan SKU ini
    ikut dinonaktifkan dan DAFTAR TERDAMPAK dikembalikan ke staf."""
    user = await _require_admin(request)
    db = get_db()
    v = await db.rahaza_model_variants.find_one({"id": vid}, {"_id": 0, "sku": 1})
    if not v:
        raise HTTPException(404, "Varian tidak ditemukan.")
    affected = await pm.deactivate_catalog_items_for_variant(db, vid)
    await db.rahaza_model_variants.update_one({"id": vid}, {"$set": {"active": False, "updated_at": _now()}})
    await log_activity(user["id"], user.get("name", ""), "deactivate", "rahaza.variant", vid)
    return {
        "status": "deactivated",
        "sku": v.get("sku", ""),
        "affected_catalog_items": affected,
        "affected_count": len(affected),
        "message": (f"Varian {v.get('sku','')} dinonaktifkan. {len(affected)} item katalog "
                    "ikut dinonaktifkan." if affected
                    else f"Varian {v.get('sku','')} dinonaktifkan. Tidak ada item katalog terdampak."),
    }
