"""
PT Rahaza Global Indonesia — Production Execution (Fase 4+)

Endpoints (all under /api/rahaza):
  - /models             : Model produk (Sweater V-Neck, dsb)  [CRUD]
  - /sizes              : Size (S/M/L/XL)                     [CRUD]
  - /line-assignments   : Assign operator+shift+target ke Line [CRUD]
  - /wip/events         : WIP event ledger (POST to record; GET to query)
  - /wip/summary        : Aggregated WIP per proses (computed)

WIP semantics (MVP):
  - Event type 'output' = operator line menghasilkan X pcs pada proses P
  - WIP di proses P = Σ output(P) − Σ output(next_of_P)
  - Urutan proses ditentukan oleh field `order_seq` pada rahaza_processes
  - Proses rework (is_rework=True) diperlakukan sebagai side-stream untuk
    perhitungan lanjut (akan diperluas di Fase 6).
"""
# ruff: noqa: E741
import logging
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from storage import put_object, delete_object, generate_storage_path
from core import material_fields  # FASE 6.6-B: SSOT nama field + alias legacy yarn_*
from core import product_master as pm  # F2–F5: SSOT kategori/HPP/kode otomatis/propagasi
import uuid
import io
from datetime import datetime, timezone, date
from typing import Optional

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-production"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


# ── Seed defaults for sizes ─────────────────────────────────────────────────
DEFAULT_SIZES = [
    {"code": "S",       "name": "S",        "order_seq": 1},
    {"code": "M",       "name": "M",        "order_seq": 2},
    {"code": "L",       "name": "L",        "order_seq": 3},
    {"code": "XL",      "name": "XL",       "order_seq": 4},
    {"code": "XXL",     "name": "XXL",      "order_seq": 5},
    {"code": "ALLSIZE", "name": "All Size", "order_seq": 6},   # GAP-5: produk one-size DA
    {"code": "STD",     "name": "Standar",  "order_seq": 7},   # GAP-5: kategori fit Standar
    {"code": "JMB",     "name": "Jumbo",    "order_seq": 8},   # GAP-5: kategori fit Jumbo
]


async def seed_rahaza_production_data():
    db = get_db()
    seeded_size = 0
    size_codes = [s["code"] for s in DEFAULT_SIZES]
    existing_size_codes = set()
    if size_codes:
        async for d in db.rahaza_sizes.find(
            {"code": {"$in": size_codes}}, {"_id": 0, "code": 1}
        ):
            existing_size_codes.add(d["code"])
    for s in DEFAULT_SIZES:
        if s["code"] in existing_size_codes:
            continue
        await db.rahaza_sizes.insert_one({
            "id": _uid(), **s, "active": True,
            "created_at": _now(), "updated_at": _now(),
        })
        seeded_size += 1
    if seeded_size:
        logging.getLogger(__name__).info(f"  · Rahaza sizes seeded ({seeded_size} baru)")


async def _require_admin(request: Request):
    # RBAC master product (keputusan user): SEMUA staff internal yang bisa akses
    # portal boleh CRUD master. Hanya role eksternal (vendor/klien) yang ditolak.
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("cmt_vendor", "vendor", "klien_maklon"):
        raise HTTPException(403, "Akses master hanya untuk staff internal.")
    return user


# ── MODELS (Model Produk) ───────────────────────────────────────────────────
@router.get("/models")
async def list_models(request: Request):
    await require_auth(request)
    db = get_db()
    rows = await db.rahaza_models.find({}, {"_id": 0}).sort("code", 1).to_list(500)
    # T1 — dokumen LAMA (promosi R&D) tidak punya `active`; layar & hitungan harus
    # memperlakukannya sebagai hidup, bukan menghilang. Diisi saat dibaca supaya
    # tidak ada pintu yang punya definisi sendiri.
    for r in rows:
        if r.get("active") is None:
            r["active"] = pm.model_is_live(r)
    return serialize_doc(rows)


async def _resolve_category_or_400(db, body: dict, *, required: bool = False) -> dict:
    """Validasi `category_id` di server (menutup P3). Tak dikenal/non-aktif ⇒ 400.

    Menerima juga `category` teks untuk dokumen/klien LAMA: dipetakan ke master
    lewat SSOT `product_master.resolve_category_by_text()` (K-5a). Kalau teksnya
    tidak dikenal, dijawab 400 dengan daftar pilihan — bukan diterima diam-diam.
    """
    cid = (body.get("category_id") or "").strip() or None
    if cid:
        cat = await pm.get_category(db, cid)
        if not cat:
            raise HTTPException(400, f"category_id '{cid}' tidak dikenal. "
                                     "Pilih dari master Kategori Produk.")
        if cat.get("active") is False:
            raise HTTPException(400, f"Kategori '{cat.get('name')}' sudah non-aktif — "
                                     "pilih kategori lain.")
        return cat
    text = (body.get("category") or "").strip()
    if text:
        cat = await pm.resolve_category_by_text(db, text, allow_create=False)
        if not cat:
            names = [c["name"] for c in await db.rahaza_product_categories.find(
                {"active": {"$ne": False}}, {"_id": 0, "name": 1}
            ).sort("order_seq", 1).to_list(50)]
            raise HTTPException(400, f"Kategori '{text}' tidak ada di master. "
                                     f"Pilihan: {', '.join(names)}")
        return cat
    if required:
        raise HTTPException(400, "category_id wajib diisi (pilih dari master Kategori Produk).")
    return {}


def _master_money_fields(body: dict, existing: dict = None) -> dict:
    """F5 — HPP dasar / harga jual resmi / berat satuan.

    `base_hpp` menutup P1a/P1b (produk manual dulu lahir tanpa HPP ⇒ FG hpp=0 ⇒
    margin katalog mustahil). `retail_price` = harga jual RESMI (K-3a).
    `weight_gram` menutup P4 (`ensure_fg_material()` SUDAH membacanya, tetapi
    tidak ada penulis).
    """
    existing = existing or {}
    out = {}
    for key in ("base_hpp", "retail_price", "weight_gram"):
        if key in body and body.get(key) is not None:
            try:
                val = float(body.get(key) or 0)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{key} harus angka.") from None
            if val < 0:
                raise HTTPException(400, f"{key} tidak boleh negatif.")
            out[key] = val
    return out


@router.post("/models")
async def create_model(request: Request):
    """Buat master produk.

    K-1A — `code` **dibuat otomatis** dari `sku_prefix` kategori (`VST-0001`) bila
    tidak dikirim. Format SKU varian tetap `{MODEL}-{WARNA}-{SIZE}` ⇒ nol migrasi
    SKU/barcode (gate INV-RND-3 & PR-10 tetap hijau).

    T1 — pengecekan duplikat kode TIDAK LAGI bergantung `active: True`. Dokumen
    lama hasil promosi R&D hanya punya `status: 'active'`, sehingga filter lama
    melewatkannya dan kode kembar diterima HTTP 200.
    """
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    code = (body.get("code") or "").strip().upper()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")

    cat = await _resolve_category_or_400(db, body)
    if not code:
        if not cat:
            raise HTTPException(
                400, "Kode produk kosong. Pilih kategori dulu supaya kode bisa dibuat "
                     "otomatis dari prefix SKU-nya (mis. VST-0001), atau isi `code` manual.")
        code = await pm.next_model_code(db, cat)

    # T1 — satu definisi \"masih hidup\" (juga cocok utk dokumen tanpa `active`)
    if await db.rahaza_models.find_one(pm.live_model_filter({"code": code})):
        raise HTTPException(409, f"Kode '{code}' sudah terpakai. Gunakan kode lain.")

    doc = {
        "id": _uid(),
        "code": code,
        "name": name,
        # FASE 6.6-B: kanonik `material_kg_per_pcs` + alias legacy `yarn_kg_per_pcs`
        **material_fields.mirror_from_body(body, "material_kg_per_pcs", cast=float, default=0),
        "bundle_size": int(body.get("bundle_size") or 30),  # Phase 17A: default 30 pcs per bundle
        "description": body.get("description") or "",
        "sop_steps": [],
        "reference_videos": [],
        "reference_images": [],
        "active": True,
        "created_at": _now(), "updated_at": _now(),
    }
    pm.apply_category(doc, cat)
    doc.update(_master_money_fields(body))
    doc.setdefault("base_hpp", 0.0)
    doc.setdefault("retail_price", 0.0)
    doc.setdefault("weight_gram", 0.0)
    doc.setdefault("hpp_rnd", 0.0)   # F5 — produk manual: HPP R&D memang belum ada
    hpp, src = pm.resolve_hpp(doc)
    doc["hpp"] = hpp                 # nilai EFEKTIF (dibaca 34 pintu lama)
    doc["hpp_source"] = src
    doc["hpp_updated_at"] = _now() if hpp else None

    await db.rahaza_models.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.model", code)
    return serialize_doc(doc)


@router.put("/models/{mid}")
async def update_model(mid: str, request: Request):
    """Ubah master produk + **PROPAGASI** kategori/berat/HPP/harga ke FG & katalog.

    Menutup P2b: dulu `category` disalin sekali ke FG dan tidak pernah diperbarui,
    sehingga mengubah kategori di master membuat FG & katalog kategori LAMA selamanya.
    """
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    body.pop("_id", None)
    body.pop("id", None)
    body.pop("created_at", None)
    # field turunan tidak boleh ditulis klien — server yang menstempelnya
    for k in ("category_code", "category_name", "hpp_source", "hpp_updated_at",
              "hpp", "hpp_rnd"):
        body.pop(k, None)

    current = await db.rahaza_models.find_one({"id": mid}, {"_id": 0})
    if not current:
        raise HTTPException(404, "Not found")

    cat = {}
    if "category_id" in body or "category" in body:
        cat = await _resolve_category_or_400(db, body)
        body.pop("category_id", None)
        body.pop("category", None)

    money = _master_money_fields(body, current)
    for k in ("base_hpp", "retail_price", "weight_gram"):
        body.pop(k, None)

    if "code" in body:
        new_code = (body["code"] or "").strip().upper()
        if not new_code:
            body.pop("code")
        else:
            body["code"] = new_code
            if new_code != (current.get("code") or "").upper() and \
                    await db.rahaza_models.find_one(
                        pm.live_model_filter({"code": new_code, "id": {"$ne": mid}})):
                raise HTTPException(409, f"Kode '{new_code}' sudah terpakai. Gunakan kode lain.")
    # Phase 17A: sanitize bundle_size
    if "bundle_size" in body:
        try:
            body["bundle_size"] = max(1, int(body["bundle_size"]))
        except (TypeError, ValueError):
            body.pop("bundle_size")

    patch = dict(body)
    if cat:
        patch.update(pm.category_patch(cat))
    patch.update(money)
    # F5 — dokumen LAMA belum punya `hpp_rnd` (pemisah sumber). Sembuhkan sekali
    # di sini supaya mengubah `base_hpp` tidak membuat HPP R&D lama hilang atau
    # produk manual salah dilaporkan bersumber 'rnd'.
    if not current.get("hpp_rnd"):
        legacy_hpp = float(current.get("hpp") or 0)
        base_cur = float(current.get("base_hpp") or 0)
        patch["hpp_rnd"] = legacy_hpp if (
            legacy_hpp > 0 and (base_cur <= 0 or abs(legacy_hpp - base_cur) > 0.0001)
        ) else 0.0
    merged = {**current, **patch}
    merged.pop("hpp", None)  # `hpp` = nilai turunan; jangan dipakai menebak sumber
    hpp, src = pm.resolve_hpp(merged)
    if hpp != float(current.get("hpp") or 0) or src != current.get("hpp_source"):
        patch["hpp"] = hpp
        patch["hpp_source"] = src
        patch["hpp_updated_at"] = _now()
    patch["updated_at"] = _now()

    res = await db.rahaza_models.update_one({"id": mid}, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")

    after = await db.rahaza_models.find_one({"id": mid}, {"_id": 0})
    prop = await pm.propagate_master_changes(db, after)
    await log_activity(user["id"], user.get("name", ""), "update", "rahaza.model", mid)
    out = serialize_doc(after)
    if isinstance(out, dict):
        out["propagated"] = {"fg": prop.get("fg", 0), "catalog_items": prop.get("items", 0)}
    return out


@router.delete("/models/{mid}")
async def deactivate_model(mid: str, request: Request):
    """Nonaktifkan produk. **K-9a**: item katalog yang menawarkannya ikut
    dinonaktifkan, dan DAFTAR TERDAMPAK dikembalikan supaya staf tahu apa yang
    berubah (bukan perubahan senyap).
    """
    user = await _require_admin(request)
    db = get_db()
    model = await db.rahaza_models.find_one({"id": mid}, {"_id": 0, "id": 1, "code": 1, "name": 1})
    if not model:
        raise HTTPException(404, "Model tidak ditemukan.")
    affected = await pm.deactivate_catalog_items_for_model(db, mid)
    await db.rahaza_models.update_one({"id": mid}, {"$set": {"active": False,
                                                            "status": "inactive",
                                                            "updated_at": _now()}})
    await log_activity(user["id"], user.get("name", ""), "deactivate", "rahaza.model", mid)
    return {
        "status": "deactivated",
        "model": {"id": mid, "code": model.get("code"), "name": model.get("name")},
        "affected_catalog_items": affected,
        "affected_count": len(affected),
        "message": (f"Produk dinonaktifkan. {len(affected)} item katalog ikut dinonaktifkan "
                    "supaya barang yang sudah dihentikan tidak bisa dijual."
                    if affected else "Produk dinonaktifkan. Tidak ada item katalog terdampak."),
    }


# ── MODEL IMAGES (max 3 photos per model) ──────────────────────────────────
@router.post("/models/{mid}/images")
async def upload_model_image(mid: str, request: Request, file: UploadFile = File(...)):
    """Upload foto referensi untuk model (max 3 foto per model)."""
    user = await _require_admin(request)
    db = get_db()
    mod = await db.rahaza_models.find_one({"id": mid}, {"_id": 0})
    if not mod:
        raise HTTPException(404, "Model tidak ditemukan")
    images = list(mod.get("image_paths") or [])
    if len(images) >= 8:
        raise HTTPException(400, "Maksimal 8 foto per model. Hapus salah satu dulu.")
    # Validate content type (header check)
    ctype = (file.content_type or "").lower()
    if not ctype.startswith("image/"):
        raise HTTPException(400, "File harus berupa gambar (jpg/png/webp)")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Ukuran gambar maksimal 5MB")
    # M1: Validate magic bytes via Pillow (prevents header spoofing)
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        if img.format not in ('JPEG', 'PNG', 'WEBP', 'GIF', 'BMP'):
            raise HTTPException(400, "Format gambar tidak didukung (gunakan JPG/PNG/WEBP)")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "File bukan gambar yang valid")
    try:
        path = generate_storage_path(user["id"], file.filename or "model.jpg")
        result = put_object(path, data, ctype)
        storage_path = result.get("path", path)
    except RuntimeError:
        raise HTTPException(503, "Storage tidak tersedia")
    except Exception as e:
        raise HTTPException(500, f"Upload gagal: {str(e)}")
    images.append(storage_path)
    await db.rahaza_models.update_one({"id": mid}, {"$set": {"image_paths": images, "updated_at": _now()}})
    # Track in attachments collection for unified file tracking
    await db.attachments.insert_one({
        "id": _uid(), "storage_path": storage_path,
        "original_filename": file.filename, "content_type": ctype,
        "size": len(data), "entity_type": "rahaza_model", "entity_id": mid,
        "uploaded_by": user.get("name", ""), "uploaded_by_id": user["id"],
        "is_deleted": False, "created_at": _now(),
    })
    await log_activity(user["id"], user.get("name", ""), "upload_image", "rahaza.model", mid)
    return {"image_paths": images, "added": storage_path}


@router.delete("/models/{mid}/images")
async def delete_model_image(mid: str, request: Request):
    """Hapus 1 foto. Body: {storage_path: '...'}"""
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    target = body.get("storage_path")
    if not target:
        raise HTTPException(400, "storage_path required")
    mod = await db.rahaza_models.find_one({"id": mid}, {"_id": 0})
    if not mod:
        raise HTTPException(404, "Model tidak ditemukan")
    images = [p for p in (mod.get("image_paths") or []) if p != target]
    await db.rahaza_models.update_one({"id": mid}, {"$set": {"image_paths": images, "updated_at": _now()}})
    # M10: Actually delete the object from storage (not just soft-delete)
    try:
        delete_object(target)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"delete_model_image storage delete failed ({target}): {e}")
    await db.attachments.update_one(
        {"storage_path": target},
        {"$set": {"is_deleted": True, "deleted_at": _now()}}
    )
    await log_activity(user["id"], user.get("name", ""), "delete_image", "rahaza.model", mid)
    return {"image_paths": images}


# ── PRODUCTION SOP / PANDUAN PRODUKSI (per model, dibaca CMT) ────────────────
_ALLOWED_SOP_IMG_FORMATS = ('JPEG', 'PNG', 'WEBP', 'GIF', 'BMP')


@router.post("/models/{mid}/sop-image")
async def upload_sop_step_image(mid: str, request: Request, file: UploadFile = File(...)):
    """Upload 1 foto untuk langkah SOP. Return {storage_path}. Tidak masuk galeri foto produk."""
    user = await _require_admin(request)
    db = get_db()
    mod = await db.rahaza_models.find_one({"id": mid}, {"_id": 0})
    if not mod:
        raise HTTPException(404, "Model tidak ditemukan")
    ctype = (file.content_type or "").lower()
    if not ctype.startswith("image/"):
        raise HTTPException(400, "File harus berupa gambar (jpg/png/webp)")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Ukuran gambar maksimal 5MB")
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        if img.format not in _ALLOWED_SOP_IMG_FORMATS:
            raise HTTPException(400, "Format gambar tidak didukung (gunakan JPG/PNG/WEBP)")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "File bukan gambar yang valid")
    try:
        path = generate_storage_path(mid, file.filename or "sop.jpg")
        result = put_object(path, data, ctype)
        storage_path = result.get("path", path)
    except RuntimeError:
        raise HTTPException(503, "Storage tidak tersedia")
    except Exception as e:
        raise HTTPException(500, f"Upload gagal: {str(e)}")
    await db.attachments.insert_one({
        "id": _uid(), "storage_path": storage_path,
        "original_filename": file.filename, "content_type": ctype,
        "size": len(data), "entity_type": "rahaza_model_sop", "entity_id": mid,
        "uploaded_by": user.get("name", ""), "uploaded_by_id": user["id"],
        "is_deleted": False, "created_at": _now(),
    })
    return {"storage_path": storage_path}


def _clean_sop_steps(raw) -> list:
    steps = []
    for s in raw or []:
        if not isinstance(s, dict):
            continue
        title = (s.get("title") or "").strip()
        desc = (s.get("description") or "").strip()
        img = (s.get("image_path") or "").strip()
        if not title and not desc and not img:
            continue
        steps.append({
            "id": s.get("id") or _uid(),
            "title": title,
            "description": desc,
            "image_path": img,
        })
    for i, s in enumerate(steps):
        s["seq"] = i + 1
    return steps


def _clean_videos(raw) -> list:
    vids = []
    for v in raw or []:
        if not isinstance(v, dict):
            continue
        url = (v.get("url") or "").strip()
        if not url:
            continue
        vids.append({"url": url, "title": (v.get("title") or "").strip()})
    return vids


def _clean_ref_images(raw) -> list:
    imgs = []
    for v in raw or []:
        if not isinstance(v, dict):
            continue
        url = (v.get("url") or "").strip()
        if not url:
            continue
        imgs.append({"url": url, "caption": (v.get("caption") or "").strip()})
    return imgs


@router.put("/models/{mid}/sop")
async def save_model_sop(mid: str, request: Request):
    """Simpan Panduan Produksi model: sop_steps[], reference_videos[], reference_images[]."""
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    upd = {
        "sop_steps": _clean_sop_steps(body.get("sop_steps")),
        "reference_videos": _clean_videos(body.get("reference_videos")),
        "reference_images": _clean_ref_images(body.get("reference_images")),
        "sop_updated_at": _now(),
        "sop_updated_by": user.get("name", ""),
        "updated_at": _now(),
    }
    res = await db.rahaza_models.update_one({"id": mid}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Model tidak ditemukan")
    await log_activity(user["id"], user.get("name", ""), "save_sop", "rahaza.model", mid)
    return serialize_doc(await db.rahaza_models.find_one({"id": mid}, {"_id": 0}))


# ── SIZES ────────────────────────────────────────────────────────────────────
@router.get("/sizes")
async def list_sizes(request: Request):
    await require_auth(request)
    db = get_db()
    rows = await db.rahaza_sizes.find({}, {"_id": 0}).sort("order_seq", 1).to_list(500)
    return serialize_doc(rows)


@router.post("/sizes")
async def create_size(request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    code = (body.get("code") or "").strip().upper()
    name = (body.get("name") or "").strip() or code
    if not code:
        raise HTTPException(400, "code required")
    if await db.rahaza_sizes.find_one({"code": code, "active": True}):
        raise HTTPException(409, f"Kode '{code}' sudah terpakai (aktif). Gunakan kode lain.")
    doc = {
        "id": _uid(),
        "code": code,
        "name": name,
        "order_seq": int(body.get("order_seq") or 0),
        "active": True,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_sizes.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.size", code)
    return serialize_doc(doc)


@router.put("/sizes/{sid}")
async def update_size(sid: str, request: Request):
    await _require_admin(request)
    db = get_db()
    body = await request.json()
    body.pop("_id", None)
    body.pop("id", None)
    body.pop("created_at", None)
    body["updated_at"] = _now()
    if "code" in body:
        body["code"] = body["code"].strip().upper()
    res = await db.rahaza_sizes.update_one({"id": sid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")
    return serialize_doc(await db.rahaza_sizes.find_one({"id": sid}, {"_id": 0}))


@router.delete("/sizes/{sid}")
async def deactivate_size(sid: str, request: Request):
    await _require_admin(request)
    db = get_db()
    await db.rahaza_sizes.update_one({"id": sid}, {"$set": {"active": False, "updated_at": _now()}})
    return {"status": "deactivated"}


# ── LINE ASSIGNMENTS ────────────────────────────────────────────────────────
@router.get("/line-assignments")
async def list_assignments(request: Request, line_id: Optional[str] = None, assign_date: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {}
    if line_id:
        q["line_id"] = line_id
    if assign_date:
        q["assign_date"] = assign_date  # YYYY-MM-DD
    rows = await db.rahaza_line_assignments.find(q, {"_id": 0}).sort([("assign_date", -1), ("line_id", 1)]).to_list(500)
    # Enrich with joined names
    line_ids = list({r["line_id"] for r in rows if r.get("line_id")})
    emp_ids  = list({r["operator_id"] for r in rows if r.get("operator_id")})
    shift_ids= list({r["shift_id"] for r in rows if r.get("shift_id")})
    model_ids= list({r["model_id"] for r in rows if r.get("model_id")})
    size_ids = list({r["size_id"] for r in rows if r.get("size_id")})

    async def _name_map(col, ids, id_field="id", name_field="name"):
        if not ids:
            return {}
        docs = await db[col].find({id_field: {"$in": ids}}, {"_id": 0}).to_list(500)
        return {d[id_field]: d.get(name_field) for d in docs}

    ln_map    = await _name_map("rahaza_lines", line_ids)
    emp_map   = await _name_map("rahaza_employees", emp_ids)
    sh_map    = await _name_map("rahaza_shifts", shift_ids)
    mod_map   = await _name_map("rahaza_models", model_ids)
    sz_map    = await _name_map("rahaza_sizes", size_ids)

    for r in rows:
        r["line_name"]     = ln_map.get(r.get("line_id"))
        r["operator_name"] = emp_map.get(r.get("operator_id"))
        r["shift_name"]    = sh_map.get(r.get("shift_id"))
        r["model_name"]    = mod_map.get(r.get("model_id"))
        r["size_name"]     = sz_map.get(r.get("size_id"))
    return serialize_doc(rows)


@router.post("/line-assignments")
async def create_assignment(request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    line_id = body.get("line_id")
    if not line_id:
        raise HTTPException(400, "line_id required")
    assign_date = body.get("assign_date") or date.today().isoformat()
    process_id   = body.get("process_id") or None
    process_code = body.get("process_code") or None

    # If process_id given but process_code missing, resolve it
    if process_id and not process_code:
        proc_doc = await db.rahaza_processes.find_one({"id": process_id}, {"_id": 0})
        if proc_doc:
            process_code = proc_doc.get("code")
    # If process_code given but process_id missing, resolve it
    if process_code and not process_id:
        proc_doc = await db.rahaza_processes.find_one({"code": process_code.upper(), "active": True}, {"_id": 0})
        if proc_doc:
            process_id = proc_doc.get("id")
            process_code = proc_doc.get("code")

    # Check collision on line+date+shift+process (same line can work different processes on same shift)
    q_collision = {
        "line_id": line_id, "assign_date": assign_date,
        "shift_id": body.get("shift_id"), "active": True,
    }
    if process_id:
        q_collision["process_id"] = process_id
    existing = await db.rahaza_line_assignments.find_one(q_collision)
    if existing:
        raise HTTPException(409, "Line sudah di-assign untuk tanggal, shift, dan proses tersebut.")
    doc = {
        "id": _uid(),
        "line_id": line_id,
        "operator_id": body.get("operator_id") or None,
        "shift_id": body.get("shift_id") or None,
        "model_id": body.get("model_id") or None,
        "size_id":  body.get("size_id") or None,
        "target_qty": int(body.get("target_qty") or 0),
        "assign_date": assign_date,
        "process_id": process_id,
        "process_code": process_code,
        "work_order_id": body.get("work_order_id") or None,
        "notes": body.get("notes") or "",
        "active": True,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_line_assignments.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.line_assignment", doc["id"])
    return serialize_doc(doc)


# ─── (DIHAPUS FASE 14) DUA HANDLER MATI: assignments/yesterday & assignments/bulk ──
# `GET/POST /api/rahaza/supervisor/assignments/{yesterday,bulk}` juga didefinisikan di
# `routes/rahaza_sprint22.py`, dan `rahaza_sprint22_router` di-include SETELAH router
# ini di server.py ⇒ definisi di sini SELALU tertimpa dan TIDAK PERNAH dieksekusi.
# Dibuktikan dari tabel route runtime (scripts/lib/route_table.py), bukan dugaan.
#
# Keduanya BUKAN salinan identik — perbedaannya berbahaya kalau sampai hidup:
#   · auth   : versi ini `require_auth` (siapa pun login) vs sprint22 `_require_supervisor`
#   · field  : versi ini `operator_id`/`target_qty` vs sprint22 `employee_id`/`target_pcs`
#   · respons: versi ini {date,count,assignments} vs sprint22 {source_date,target_date,…}
# Artinya salinan mati ini adalah jalur BYPASS RBAC yang menunggu urutan include tertukar.
#
# SSOT assignments supervisor: routes/rahaza_sprint22.py. Jangan definisikan ulang.


# FASE 14 — DEKORATOR HILANG (bug nyata): `update_assignment` di bawah ini TIDAK
# PERNAH terdaftar sebagai route karena dekoratornya tidak ada, padahal saudaranya
# `POST /line-assignments` (create) dan `DELETE /line-assignments/{aid}` terdaftar.
# Jadi "ubah assignment" hilang DIAM-DIAM dari API. Cacat ini tak terlihat oleh
# pemeriksa duplikat mana pun (fungsi tanpa dekorator = tidak ada route). Dijaga
# sekarang oleh CHECK D `ORPHAN_HANDLER` di scripts/preflight/verify_fe_be_contract.py.
@router.put("/line-assignments/{aid}")
async def update_assignment(aid: str, request: Request):
    await _require_admin(request)
    db = get_db()
    body = await request.json()
    body.pop("_id", None)
    body.pop("id", None)
    body.pop("created_at", None)
    body["updated_at"] = _now()
    res = await db.rahaza_line_assignments.update_one({"id": aid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")
    return serialize_doc(await db.rahaza_line_assignments.find_one({"id": aid}, {"_id": 0}))


@router.delete("/line-assignments/{aid}")
async def deactivate_assignment(aid: str, request: Request):
    await _require_admin(request)
    db = get_db()
    await db.rahaza_line_assignments.update_one({"id": aid}, {"$set": {"active": False, "updated_at": _now()}})
    return {"status": "deactivated"}


# ── WIP EVENTS ──────────────────────────────────────────────────────────────
@router.post("/wip/events")
async def record_wip_event(request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    line_id = body.get("line_id")
    process_id = body.get("process_id")
    qty = int(body.get("qty") or 0)
    if not (line_id and process_id and qty > 0):
        raise HTTPException(400, "line_id, process_id, qty(>0) required")

    # Look up context
    line = await db.rahaza_lines.find_one({"id": line_id}, {"_id": 0})
    if not line:
        raise HTTPException(404, "Line not found")
    proc = await db.rahaza_processes.find_one({"id": process_id}, {"_id": 0})  # FIX: fetch process

    event = {
        "id": _uid(),
        "timestamp": _now(),
        "event_date": _now().date().isoformat(),                        # FIX: date string for reports
        "line_id": line_id,
        "process_id": process_id,
        "process_code": proc.get("code") if proc else "",          # FIX: Pareto reports
        "location_id": line.get("location_id"),
        "model_id": body.get("model_id") or None,
        "size_id": body.get("size_id") or None,
        "line_assignment_id": body.get("line_assignment_id") or None,
        "work_order_id": body.get("work_order_id") or None,
        "event_type": body.get("event_type") or "output",
        "qty": qty,
        "notes": body.get("notes") or "",
        "operator_id": user.get("employee_id") or user["id"],      # FIX: payroll PCS
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
    }
    await db.rahaza_wip_events.insert_one(event)

    # ─── PACKING output → create PENDING INBOUND (WMS) ─────────────────────
    # Stok FG TIDAK langsung bertambah; butuh Scan-In oleh gudang.
    if proc and proc.get("code") == "PACKING" and event["event_type"] == "output":
        # ── SSOT (BUG-1 fix): FG receipt per-varian dgn SKU kanonik {MODEL}-{WARNA}-{SIZE}.
        # Resolve varian (warna+size) dari event → buat/link FG (code==sku) via helper SSOT.
        # Bila varian tak ter-resolusi (event lama tanpa warna), FG receipt DILEWATI agar
        # tidak membuat FG tanpa-warna yang memutus rantai Toko↔FG. ──
        import logging as _pack_log
        from utils.variant_ssot import resolve_variant, create_fg_pending_inbound_for_variant
        _variant = await resolve_variant(
            db,
            variant_id=body.get("rahaza_variant_id") or body.get("variant_id"),
            sku=body.get("variant_sku") or body.get("sku"),
        )
        if _variant:
            try:
                await create_fg_pending_inbound_for_variant(
                    db, _variant, float(qty),
                    source_type="production_packing", source_id=event["id"],
                    source_ref=body.get("work_order_id", ""), user=user,
                    notes=f"Output Packing {qty} pcs — scan-in diperlukan",
                )
            except Exception as e:
                _pack_log.getLogger(__name__).warning(f"WMS pending inbound (packing) gagal: {e}")
        else:
            _pack_log.getLogger(__name__).warning(
                "Packing output tanpa varian ter-resolusi (model=%s size=%s) — kirim "
                "rahaza_variant_id/variant_sku pada event agar FG per-warna terbentuk. FG receipt dilewati.",
                body.get("model_id"), body.get("size_id"))
    # ────────────────────────────────────────────────────────────────────────

    return serialize_doc(event)


@router.get("/wip/events")
async def list_wip_events(request: Request, line_id: Optional[str] = None, process_id: Optional[str] = None, limit: int = 100):
    await require_auth(request)
    db = get_db()
    q = {}
    if line_id:
        q["line_id"] = line_id
    if process_id:
        q["process_id"] = process_id
    rows = await db.rahaza_wip_events.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(500)
    return serialize_doc(rows)


@router.get("/wip/summary")
async def wip_summary(request: Request):
    """
    Return WIP per proses: qty yang masih berada di proses tsb.
    WIP at process P = Σ output(P) − Σ output(next_of_P)
    """
    await require_auth(request)
    db = get_db()

    processes = await db.rahaza_processes.find(
        {"active": True, "is_rework": False}, {"_id": 0}
    ).sort("order_seq", 1).to_list(500)

    # Aggregate total output per process (event_type=output)
    pipeline = [
        {"$match": {"event_type": "output"}},
        {"$group": {"_id": "$process_id", "total": {"$sum": "$qty"}}},
    ]
    raw = await db.rahaza_wip_events.aggregate(pipeline).to_list(500)
    total_by_proc = {r["_id"]: r["total"] for r in raw}

    # WIP = output(P) - output(P+1) ; for last process WIP = output(P)
    summary = []
    for idx, p in enumerate(processes):
        out_p = total_by_proc.get(p["id"], 0)
        out_next = 0
        if idx + 1 < len(processes):
            out_next = total_by_proc.get(processes[idx + 1]["id"], 0)
        wip = max(0, out_p - out_next)
        summary.append({
            "process_id": p["id"],
            "process_code": p["code"],
            "process_name": p["name"],
            "order_seq": p["order_seq"],
            "total_output": out_p,
            "wip_qty": wip,
        })
    return {"processes": summary, "updated_at": _now().isoformat()}


@router.get("/line-board")
async def line_board(request: Request, assign_date: Optional[str] = None):
    """
    Line Board per proses (non-rework) untuk tanggal tertentu (default hari ini).
    Struktur: { process: [{line, assignment, output_today, target}] }
    """
    await require_auth(request)
    db = get_db()
    today = assign_date or date.today().isoformat()

    lines = await db.rahaza_lines.find({"active": True}, {"_id": 0}).to_list(500)
    procs = await db.rahaza_processes.find({"active": True, "is_rework": False}, {"_id": 0}).sort("order_seq", 1).to_list(500)
    assignments = await db.rahaza_line_assignments.find({"assign_date": today, "active": True}, {"_id": 0}).to_list(500)

    # Enrich helper
    async def _name_map(col, ids, id_field="id"):
        if not ids:
            return {}
        docs = await db[col].find({id_field: {"$in": list(ids)}}, {"_id": 0}).to_list(500)
        return {d[id_field]: d for d in docs}

    emp_map = await _name_map("rahaza_employees", {a.get("operator_id") for a in assignments if a.get("operator_id")})
    sh_map  = await _name_map("rahaza_shifts",    {a.get("shift_id") for a in assignments if a.get("shift_id")})
    mod_map = await _name_map("rahaza_models",    {a.get("model_id") for a in assignments if a.get("model_id")})
    sz_map  = await _name_map("rahaza_sizes",     {a.get("size_id") for a in assignments if a.get("size_id")})
    loc_map = await _name_map("rahaza_locations", {l.get("location_id") for l in lines if l.get("location_id")})

    # Output today per line (event_type=output)
    start = datetime.combine(date.fromisoformat(today), datetime.min.time()).replace(tzinfo=timezone.utc)
    end   = datetime.combine(date.fromisoformat(today), datetime.max.time()).replace(tzinfo=timezone.utc)
    pipe = [
        {"$match": {"event_type": "output", "timestamp": {"$gte": start, "$lte": end}}},
        {"$group": {"_id": "$line_id", "total": {"$sum": "$qty"}}},
    ]
    out_agg = await db.rahaza_wip_events.aggregate(pipe).to_list(500)
    out_today = {r["_id"]: r["total"] for r in out_agg}

    # Group lines by process using ASSIGNMENTS (not line.process_id)
    by_proc = {p["id"]: [] for p in procs}
    assign_by_line = {}
    for a in assignments:
        assign_by_line.setdefault(a["line_id"], []).append(a)

    for ln in lines:
        loc = loc_map.get(ln.get("location_id"))
        line_assigns = []
        proc_ids_for_line = set()
        for a in assign_by_line.get(ln["id"], []):
            op  = emp_map.get(a.get("operator_id"))
            sh  = sh_map.get(a.get("shift_id"))
            mod = mod_map.get(a.get("model_id"))
            sz  = sz_map.get(a.get("size_id"))
            proc_id = a.get("process_id")
            if proc_id:
                proc_ids_for_line.add(proc_id)
            line_assigns.append({
                "id": a["id"],
                "operator_id": a.get("operator_id"),
                "operator_name": op.get("name") if op else None,
                "shift_id": a.get("shift_id"),
                "shift_name": sh.get("name") if sh else None,
                "model_id": a.get("model_id"),
                "model_name": mod.get("name") if mod else None,
                "size_id": a.get("size_id"),
                "size_code": sz.get("code") if sz else None,
                "target_qty": a.get("target_qty") or 0,
                "process_id": proc_id,
                "process_code": a.get("process_code"),
                "work_order_id": a.get("work_order_id"),
            })
        # Add line to each process it's assigned to
        for pid in proc_ids_for_line:
            if pid in by_proc:
                proc_assigns = [a for a in line_assigns if a.get("process_id") == pid]
                by_proc[pid].append({
                    "line_id": ln["id"],
                    "line_code": ln["code"],
                    "line_name": ln["name"],
                    "location_id": ln.get("location_id"),
                    "location_name": loc.get("name") if loc else None,
                    "capacity_per_hour": ln.get("capacity_per_hour") or 0,
                    "output_today": out_today.get(ln["id"], 0),
                    "assignments": proc_assigns,
                })
        # Fallback: if line has no process assignments, still add once using line.process_id
        if not proc_ids_for_line:
            pid = ln.get("process_id")
            if pid and pid in by_proc:
                by_proc[pid].append({
                    "line_id": ln["id"],
                    "line_code": ln["code"],
                    "line_name": ln["name"],
                    "location_id": ln.get("location_id"),
                    "location_name": loc.get("name") if loc else None,
                    "capacity_per_hour": ln.get("capacity_per_hour") or 0,
                    "output_today": out_today.get(ln["id"], 0),
                    "assignments": line_assigns,
                })

    board = []
    for p in procs:
        board.append({
            "process_id": p["id"],
            "process_code": p["code"],
            "process_name": p["name"],
            "order_seq": p["order_seq"],
            "lines": by_proc[p["id"]],
        })
    return {"date": today, "board": board}
