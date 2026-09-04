"""
PT Rahaza — Bill of Materials (Fase 5b — Multi-Version) + Phase 7A Fase 1
GENERIK: satu daftar `materials[]` (bukan lagi yarn_materials/accessory_materials).

Endpoints (prefix /api/rahaza):
  - GET    /boms                       : List BOMs (filter by model_id)
  - GET    /boms/{id}                  : BOM detail
  - GET    /models/{model_id}/bom      : All BOMs for model (all sizes) dengan active version
  - GET    /boms/versions              : List versions per model_id+size_id
  - POST   /boms                       : Create new BOM version
  - PUT    /boms/{id}                  : Update BOM (untuk edit versi aktif)
  - POST   /boms/{id}/activate         : Activate versi (dan deactivate yang lain)
  - POST   /boms/{id}/requirements     : Preview kebutuhan material untuk X pcs
  - DELETE /boms/{id}                  : Soft-delete
  - POST   /boms/{id}/copy-to-sizes    : Copy this BOM to other sizes (same model)

Schema (rahaza_boms) — Phase 7A Fase 1:
  {
    id, model_id, size_id, color, version (int), is_active (bool),
    materials: [{
        material_id?, code, name,
        material_type,          # yarn | fabric | accessory | packaging | other
        category, category_name,# kategori material (master rahaza_material_categories)
        qty, unit, notes,       # qty per pcs (dalam `unit`)
    }],
    material_count, total_yarn_kg_per_pcs: <auto/enrich>,
    notes, active (soft delete), created_at, updated_at
  }

Versioning Rules:
  - Setiap model+size(+color) bisa punya multiple versions (version: 1,2,3,...)
  - Hanya 1 version yang is_active=true per model+size(+color)
  - Edit version aktif menggunakan PUT /boms/{id}
  - Create version baru menggunakan POST /boms (auto increment version number)
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity, check_role
from core import material_fields  # FASE 6.6-B: SSOT nama field + alias legacy yarn_*
from core import bom_uom          # 2026-08-02: konversi satuan baris BOM → satuan dasar
import uuid
import math
from datetime import datetime, timezone
from typing import Optional

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-bom"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


# material_type yang dihitung sebagai "kain/benang" (satuan kg) untuk kompat lama.
_KGLIKE_TYPES = {"yarn", "fabric", "kain", "benang", "interlining"}
_KGLIKE_UNITS = {"kg", "gram", "g", "m", "meter", "yard", "roll"}


def _parse_version(v) -> int:
    """Normalize version field: int, str '1', str 'v1' → int. Returns 0 on failure."""
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v.lstrip('vV').strip())
        except (ValueError, AttributeError):
            return 0
    return 0


def _infer_material_type(unit, provided=None) -> str:
    """Tebak material_type dari unit bila tak disediakan eksplisit."""
    if provided:
        return str(provided).strip().lower()
    u = (unit or "").strip().lower()
    return "fabric" if u in _KGLIKE_UNITS else "accessory"


def _clean_materials(raw):
    """Bersihkan daftar `materials[]` generik. Menerima juga baris legacy (qty_kg)
    demi kompat payload lama. Baris tanpa nama / qty<=0 diabaikan."""
    cleaned = []
    for m in raw or []:
        name = (m.get("name") or "").strip()
        raw_qty = m.get("qty")
        if raw_qty in (None, ""):
            raw_qty = m.get("qty_kg") or 0
        try:
            qty = float(raw_qty or 0)
        except (ValueError, TypeError):
            qty = 0.0
        if not name or qty <= 0:
            continue
        unit = (m.get("unit") or "").strip().lower() or "pcs"
        mtype = _infer_material_type(unit, m.get("material_type") or m.get("type"))
        item = {
            "material_id": m.get("material_id") or None,
            "code": (m.get("code") or "").strip().upper(),
            "name": name,
            "material_type": mtype,
            "category": (m.get("category") or "").strip(),
            "category_name": (m.get("category_name") or "").strip(),
            "qty": round(qty, 4),
            "unit": unit,
            "notes": m.get("notes") or "",
        }
        cleaned.append(item)
    return cleaned


def get_bom_materials(bom):
    """SSOT reader — daftar materials[] terunifikasi untuk sebuah BOM.
    Prefer field baru `materials`; fallback konversi dari legacy
    yarn_materials/accessory_materials (untuk dok yang belum termigrasi).
    Dipakai SEMUA konsumer BOM (HPP, PDF, explode, requirements)."""
    if not bom:
        return []
    mats = bom.get("materials")
    if isinstance(mats, list) and mats:
        # Normalisasi field alias (material_name/quantity/material_code) → kanonik.
        norm = []
        for m in mats:
            nm = (m.get("name") or m.get("material_name") or "").strip()
            if not nm:
                continue
            raw_qty = m.get("qty")
            if raw_qty in (None, ""):
                raw_qty = m.get("quantity", m.get("qty_kg", 0))
            try:
                q = float(raw_qty or 0)
            except (ValueError, TypeError):
                q = 0.0
            unit = (m.get("unit") or "pcs")
            mtype = (m.get("material_type") or m.get("type") or "").strip().lower() \
                or _infer_material_type(unit)
            norm.append({
                "material_id": m.get("material_id"),
                "code": (m.get("code") or m.get("material_code") or "").strip().upper(),
                "name": nm,
                "material_type": mtype,
                "category": m.get("category") or "",
                "category_name": m.get("category_name") or "",
                "qty": round(q, 4),
                "unit": unit,
                "notes": m.get("notes") or "",
                # 2026-08-02: hasil konversi satuan ikut diteruskan apa adanya.
                # Baris BOM lama belum punya field ini → konsumen memakai
                # `core.bom_uom.ensure_uom()` yang menghitungnya saat runtime.
                "qty_base": m.get("qty_base"),
                "unit_base": m.get("unit_base"),
                "uom_factor": m.get("uom_factor"),
                "uom_status": m.get("uom_status"),
                "uom_note": m.get("uom_note"),
                "unit_cost_base": m.get("unit_cost_base"),
                "unlinked": m.get("unlinked"),
            })
        return norm
    out = []
    for y in bom.get("yarn_materials") or []:
        nm = (y.get("name") or "").strip()
        if not nm:
            continue
        out.append({
            "material_id": y.get("material_id"), "code": (y.get("code") or "").strip().upper(),
            "name": nm, "material_type": "yarn",
            "category": y.get("category") or "", "category_name": y.get("category_name") or "",
            "qty": round(float(y.get("qty_kg") or 0), 4), "unit": (y.get("unit") or "kg"),
            "notes": y.get("notes") or "",
        })
    for a in bom.get("accessory_materials") or []:
        nm = (a.get("name") or "").strip()
        if not nm:
            continue
        out.append({
            "material_id": a.get("material_id"), "code": (a.get("code") or "").strip().upper(),
            "name": nm, "material_type": "accessory",
            "category": a.get("category") or "", "category_name": a.get("category_name") or "",
            "qty": round(float(a.get("qty") or 0), 4), "unit": (a.get("unit") or "pcs"),
            "notes": a.get("notes") or "",
        })
    return out


def _is_kglike(m) -> bool:
    return (m.get("unit") == "kg") or (str(m.get("material_type") or "").lower() in _KGLIKE_TYPES)


async def migrate_bom_data(db):
    """
    Idempotent migration (dijalankan saat startup):
    1. Convert string versions ("v1","v2") → int.
    2. Set is_active pada versi tertinggi per model+size jika belum ada yang aktif.
    3. Phase 7A Fase 1: convert legacy yarn_materials/accessory_materials → materials[].
    """
    # Step 1: Fix string versions
    bad_version_boms = await db.rahaza_boms.find(
        {"version": {"$type": "string"}, "active": True}, {"_id": 0, "id": 1, "version": 1}
    ).to_list(500)
    for b in bad_version_boms:
        new_v = _parse_version(b.get("version")) or 1
        await db.rahaza_boms.update_one({"id": b["id"]}, {"$set": {"version": new_v}})

    # Step 2: Fix missing is_active — collect model+size combos
    boms_no_active = await db.rahaza_boms.find(
        {"active": True, "is_active": {"$in": [None, False, True]}}, {"_id": 0}
    ).to_list(500)
    from collections import defaultdict
    groups = defaultdict(list)
    for b in boms_no_active:
        groups[(b.get("model_id"), b.get("size_id"))].append(b)
    for (mid, sid), group in groups.items():
        already_active = any(b.get("is_active") is True for b in group)
        if not already_active:
            sorted_group = sorted(group, key=lambda b: _parse_version(b.get("version", 0)), reverse=True)
            winner = sorted_group[0]
            await db.rahaza_boms.update_one(
                {"id": winner["id"]}, {"$set": {"is_active": True, "updated_at": _now()}})
            for b in sorted_group[1:]:
                if b.get("is_active") is not False:
                    await db.rahaza_boms.update_one(
                        {"id": b["id"]}, {"$set": {"is_active": False, "updated_at": _now()}})

    # Step 3: Phase 7A Fase 1 — legacy → materials[]
    legacy = await db.rahaza_boms.find(
        {"materials": {"$exists": False},
         "$or": [{"yarn_materials": {"$exists": True}}, {"accessory_materials": {"$exists": True}}]},
        {"_id": 0}
    ).to_list(5000)
    migrated = 0
    for b in legacy:
        mats = get_bom_materials(b)
        await db.rahaza_boms.update_one(
            {"id": b["id"]},
            {"$set": {"materials": mats, "updated_at": _now()},
             "$unset": {"yarn_materials": "", "accessory_materials": ""}})
        migrated += 1
    if migrated:
        import logging
        logging.getLogger(__name__).info(f"[rahaza_bom] migrated {migrated} BOM legacy → materials[]")


async def _require_admin(request: Request):
    # RBAC master product/BOM (keputusan user): SEMUA staff internal boleh CRUD.
    # Hanya role eksternal (vendor/klien) yang ditolak.
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("cmt_vendor", "vendor", "klien_maklon"):
        raise HTTPException(403, "Akses master hanya untuk staff internal.")
    return user


# ACC-2 — perbaikan MASSAL kopling BOM (`relink-materials`) menulis ulang
# `material_id` di SELURUH BOM sekaligus. Itu operasi perbaikan data, bukan
# pekerjaan harian, jadi TIDAK boleh dibuka seluas CRUD BOM biasa (_require_admin
# sengaja longgar: semua staff internal). Yang boleh: Owner/Admin + pemilik
# domain produk (produksi & RnD). HR/Keuangan/Marketing → 403.
# Catatan: `check_role` otomatis meloloskan superadmin, dan `admin` lolos lewat
# permission '*' yang di-set require_auth.
BOM_REPAIR_ROLES = [
    "admin", "owner", "manager_produksi", "admin_produksi",
    "supervisor_produksi", "supervisor", "rnd_staff",
]


async def _require_bom_repair(request: Request):
    user = await require_auth(request)
    if not check_role(user, BOM_REPAIR_ROLES):
        raise HTTPException(
            403,
            "Perbaikan massal kopling BOM hanya untuk Admin/Owner atau tim Produksi & RnD "
            "(pemilik master produk). Silakan minta admin produksi menjalankannya.",
        )
    return user


async def _enrich_bom(db, bom):
    if not bom:
        return bom
    mod = await db.rahaza_models.find_one({"id": bom.get("model_id")}, {"_id": 0})
    sz  = await db.rahaza_sizes.find_one({"id": bom.get("size_id")},  {"_id": 0})
    bom["model_code"] = mod["code"] if mod else None
    bom["model_name"] = mod["name"] if mod else None
    bom["size_code"]  = sz["code"]  if sz else None
    bom["size_name"]  = sz["name"]  if sz else None
    mats = get_bom_materials(bom)
    bom["materials"] = mats
    bom["material_count"] = len(mats)
    # Derived (kompat lama)
    # FASE 6.6-B: nama kanonik `total_material_kg_per_pcs` / `bulk_line_count`,
    # alias legacy `total_yarn_kg_per_pcs` / `yarn_count` tetap ikut (mirror).
    _kg_lines = [m for m in mats if _is_kglike(m)]
    bom.update(material_fields.mirror(
        "total_material_kg_per_pcs",
        round(sum(float(m.get("qty") or 0) for m in _kg_lines), 4),
    ))
    bom.update(material_fields.mirror("bulk_line_count", len(_kg_lines)))
    bom["accessory_count"] = len([m for m in mats if not _is_kglike(m)])
    return bom


@router.get("/boms")
async def list_boms(request: Request, model_id: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {"active": True}
    if model_id:
        q["model_id"] = model_id
    rows = await db.rahaza_boms.find(q, {"_id": 0}).sort("updated_at", -1).to_list(500)
    for r in rows:
        await _enrich_bom(db, r)
    return serialize_doc(rows)


@router.get("/boms/versions")
async def list_bom_versions(request: Request, model_id: str, size_id: str):
    """List all versions untuk model_id+size_id combination."""
    await require_auth(request)
    db = get_db()
    if not model_id or not size_id:
        raise HTTPException(400, "model_id dan size_id wajib diisi")
    versions = await db.rahaza_boms.find(
        {"model_id": model_id, "size_id": size_id, "active": True}, {"_id": 0}
    ).sort("version", -1).to_list(500)
    for v in versions:
        await _enrich_bom(db, v)
    return serialize_doc(versions)


# ─────────────────────────────────────────────────────────────────────────────
# ACC-2 — AUDIT & PERBAIKAN KOPLING BOM ↔ MASTER MATERIAL
# CATATAN LETAK: kedua endpoint ini WAJIB didaftarkan SEBELUM `GET /boms/{bid}`,
# kalau tidak "link-health" akan tertangkap sebagai `bid` (FastAPI cocokkan urut).
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/boms/link-health")
async def bom_link_health(request: Request):
    """Laporan baris BOM yang BELUM terhubung ke master material.

    Dipakai untuk mengukur kesehatan data sebelum/ sesudah relink, dan sebagai
    peringatan di UI (baris aksesoris tanpa `material_id` = rantai ke stok putus).
    """
    await require_auth(request)
    db = get_db()
    boms = await db.rahaza_boms.find({"active": True}, {"_id": 0}).to_list(2000)

    total_lines = acc_lines = unlinked_total = unlinked_acc = 0
    offenders = []
    for b in boms:
        mats = get_bom_materials(b)
        bad = []
        for m in mats:
            total_lines += 1
            is_acc = _is_accessory_line(m)
            if is_acc:
                acc_lines += 1
            if not m.get("material_id"):
                unlinked_total += 1
                if is_acc:
                    unlinked_acc += 1
                bad.append({"name": m.get("name", ""), "code": m.get("code", ""),
                            "material_type": m.get("material_type", ""), "is_accessory": is_acc})
        if bad:
            offenders.append({
                "bom_id": b.get("id"), "model_id": b.get("model_id"), "size_id": b.get("size_id"),
                "color": b.get("color", ""), "version": b.get("version"),
                "unlinked_lines": bad,
            })

    return {
        "total_boms": len(boms),
        "total_lines": total_lines,
        "accessory_lines": acc_lines,
        "unlinked_lines": unlinked_total,
        "unlinked_accessory_lines": unlinked_acc,
        "healthy": unlinked_acc == 0,
        "offenders": offenders[:200],
    }


@router.post("/boms/relink-materials")
async def bom_relink_materials(request: Request):
    """Auto-link baris BOM ke master material berdasarkan KODE (idempotent).

    Body: {dry_run?: bool}  — default dry_run=false (langsung terapkan).
    Hanya menyentuh baris yang `material_id`-nya kosong DAN kodenya cocok persis
    dengan master. Baris tanpa kode / kode tak dikenal SENGAJA tidak diubah
    (harus diperbaiki manual oleh user agar tidak salah tautan).
    """
    user = await _require_bom_repair(request)
    db = get_db()
    body = await request.json() if await request.body() else {}
    dry_run = bool(body.get("dry_run"))

    master_by_code = {}
    async for d in db.rahaza_materials.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1}):
        code = (d.get("code") or "").strip().upper()
        if code:
            master_by_code[code] = d

    boms = await db.rahaza_boms.find({"active": True}, {"_id": 0}).to_list(2000)
    linked = skipped = touched_boms = 0
    still_unlinked = []
    for b in boms:
        mats = get_bom_materials(b)
        changed = False
        for m in mats:
            if m.get("material_id"):
                continue
            master = master_by_code.get((m.get("code") or "").strip().upper())
            if master:
                m["material_id"] = master["id"]
                m["name"] = m.get("name") or master.get("name") or ""
                linked += 1
                changed = True
            else:
                skipped += 1
                still_unlinked.append({"bom_id": b.get("id"), "name": m.get("name", ""),
                                       "code": m.get("code", ""),
                                       "is_accessory": _is_accessory_line(m)})
        if changed and not dry_run:
            await db.rahaza_boms.update_one(
                {"id": b["id"]},
                {"$set": {"materials": mats, "updated_at": _now()},
                 "$unset": {"yarn_materials": "", "accessory_materials": ""}})
        if changed:
            touched_boms += 1

    if not dry_run:
        await log_activity(user["id"], user.get("name", ""), "relink_materials", "rahaza.bom",
                           f"{linked} baris BOM ditautkan ke master")
    return {
        "dry_run": dry_run,
        "boms_scanned": len(boms),
        "boms_touched": touched_boms,
        "lines_linked": linked,
        "lines_still_unlinked": skipped,
        "still_unlinked_sample": still_unlinked[:50],
    }



@router.get("/boms/{bid}")
async def get_bom(bid: str, request: Request):
    await require_auth(request)
    db = get_db()
    bom = await db.rahaza_boms.find_one({"id": bid}, {"_id": 0})
    if not bom:
        raise HTTPException(404, "BOM tidak ditemukan")
    await _enrich_bom(db, bom)
    return serialize_doc(bom)


@router.get("/models/{model_id}/bom")
async def get_model_bom(model_id: str, request: Request):
    """Return BOM summary untuk all sizes of a given model (matrix view) dengan active version."""
    await require_auth(request)
    db = get_db()
    model = await db.rahaza_models.find_one({"id": model_id}, {"_id": 0})
    if not model:
        raise HTTPException(404, "Model tidak ditemukan")
    sizes = await db.rahaza_sizes.find({"active": True}, {"_id": 0}).sort("order_seq", 1).to_list(500)
    boms = await db.rahaza_boms.find({"model_id": model_id, "active": True, "is_active": True}, {"_id": 0}).to_list(500)
    bom_by_size = {b["size_id"]: b for b in boms}
    matrix = []
    for s in sizes:
        b = bom_by_size.get(s["id"])
        mats = get_bom_materials(b) if b else []
        matrix.append({
            "size_id": s["id"],
            "size_code": s["code"],
            "size_name": s["name"],
            "size_order_seq": s.get("order_seq", 0),
            "bom_id": b["id"] if b else None,
            "version": b.get("version", 1) if b else None,
            "material_count": len(mats),
            # FASE 6.6-B: kanonik + alias legacy (total_yarn_kg_per_pcs / yarn_count)
            **material_fields.mirror(
                "total_material_kg_per_pcs",
                round(sum(float(m.get("qty") or 0) for m in mats if _is_kglike(m)), 4),
            ),
            **material_fields.mirror("bulk_line_count", len([m for m in mats if _is_kglike(m)])),
            "accessory_count": len([m for m in mats if not _is_kglike(m)]),
            "notes":           b.get("notes", "") if b else "",
            "updated_at":      b.get("updated_at") if b else None,
        })
    return {
        "model": {"id": model["id"], "code": model["code"], "name": model["name"]},
        "matrix": matrix,
    }


def _materials_from_body(body, fallback_bom=None):
    """Ambil materials[] dari body. Prioritas field `materials`; kompat legacy
    (yarn_materials/accessory_materials) dikonversi via get_bom_materials."""
    if body.get("materials") is not None:
        return _clean_materials(body.get("materials"))
    if body.get("yarn_materials") is not None or body.get("accessory_materials") is not None:
        merged = {
            "yarn_materials": body.get("yarn_materials")
            if body.get("yarn_materials") is not None
            else (fallback_bom or {}).get("yarn_materials"),
            "accessory_materials": body.get("accessory_materials")
            if body.get("accessory_materials") is not None
            else (fallback_bom or {}).get("accessory_materials"),
        }
        return _clean_materials(get_bom_materials(merged))
    return None


# ─────────────────────────────────────────────────────────────────────────────
# ACC-2 — KOPLING BARIS BOM ↔ MASTER MATERIAL
#
# Masalah (memory/PRODUKSI_E9_AKSESORIS.md §ACC-2): `material_id` pada baris BOM
# selama ini OPSIONAL. Baris yang diketik bebas (hanya nama/kode) tidak nyambung
# ke master `rahaza_materials`, sehingga rantai BOM → kebutuhan → issue stok putus:
# sistem tak tahu stok mana yang harus dipotong, dan nama/kode gampang drift
# ("Kancing 15mm" vs "Kancing Metal 15mm").
#
# Kebijakan (sengaja bertingkat supaya data lama tidak rusak):
#   * ASESORIS/PACKAGING → `material_id` WAJIB. Kalau kosong, coba auto-link
#     lewat `code` (exact, case-insensitive); kalau tetap gagal → tolak 400
#     dengan pesan yang menyebut baris mana & cara memperbaikinya.
#   * BAHAN/KAIN & lainnya → auto-link bila kodenya cocok; kalau tidak ketemu
#     TIDAK ditolak (kompat data lama), hanya ditandai `unlinked: true` supaya UI
#     bisa memberi peringatan.
# ─────────────────────────────────────────────────────────────────────────────
_ACC_TYPES = {"accessory", "aksesoris", "packaging", "kemasan"}


def _is_accessory_line(m) -> bool:
    return str(m.get("material_type") or "").strip().lower() in _ACC_TYPES


async def resolve_bom_materials(db, materials, *, strict_accessory: bool = True):
    """Lengkapi & validasi kopling `material_id` pada baris BOM.

    Return: (materials_terselesaikan, daftar_masalah)
    Raise HTTPException(400) bila ada baris aksesoris yang tak bisa dikaitkan
    dan `strict_accessory=True`.
    """
    out, problems = [], []
    if not materials:
        return out, problems

    ids = [m.get("material_id") for m in materials if m.get("material_id")]
    codes = [(m.get("code") or "").strip().upper() for m in materials if (m.get("code") or "").strip()]

    # 2026-08-02: proyeksi diperluas — konversi satuan butuh `uoms`, cermin
    # pack_unit/pack_size, gramasi/lebar kain, dan `unit_cost` (harga satuan dasar).
    _PROJ = {"_id": 0, "id": 1, "code": 1, "name": 1, "unit": 1, "type": 1,
             "base_uom": 1, "uoms": 1, "pack_unit": 1, "pack_size": 1,
             "unit_cost": 1, "gsm": 1, "width_cm": 1}
    by_id, by_code = {}, {}
    if ids:
        async for d in db.rahaza_materials.find({"id": {"$in": ids}}, _PROJ):
            by_id[d["id"]] = d
    if codes:
        async for d in db.rahaza_materials.find({"code": {"$in": codes}}, _PROJ):
            by_code[(d.get("code") or "").upper()] = d

    for i, m in enumerate(materials):
        line = dict(m)
        mid = line.get("material_id")
        master = by_id.get(mid) if mid else None

        if mid and not master:
            # id menunjuk master yang sudah dihapus/ganti → jangan diam-diam disimpan
            problems.append({"index": i, "name": line.get("name", ""), "code": line.get("code", ""),
                             "reason": "material_id tidak ditemukan di master"})
            line["material_id"] = None
            mid = None

        if not mid:
            master = by_code.get((line.get("code") or "").strip().upper())
            if master:
                line["material_id"] = master["id"]
                mid = master["id"]

        if master:
            # Selaraskan kode/nama ke master supaya tidak drift.
            line["code"] = (master.get("code") or line.get("code") or "").upper()
            if not line.get("name"):
                line["name"] = master.get("name") or ""
            line["unlinked"] = False
        else:
            line["unlinked"] = True
            if _is_accessory_line(line):
                problems.append({
                    "index": i, "name": line.get("name", ""), "code": line.get("code", ""),
                    "reason": "baris aksesoris belum terhubung ke master material",
                })

        # ── 2026-08-02 · KONVERSI SATUAN (laporan owner: "satuan & konversi
        # material belum ada di BOM") ──────────────────────────────────────────
        # Simpan hasil konversi ke SATUAN DASAR pada barisnya: `qty_base`,
        # `unit_base`, `uom_factor`, `uom_status`. Semua konsumen hilir (MRP,
        # pengeluaran material gudang, Surat Jalan, HPP RnD/produksi, posting GL)
        # memakai `qty × unit_cost` dengan asumsi keduanya satuan dasar
        # (INV-UOM-1/2) — tanpa langkah ini, "250 gram" dihitung 250 kg.
        line = bom_uom.annotate_line(line, master)
        if line.get("uom_status") == "mismatch":
            problems.append({
                "index": i, "name": line.get("name", ""), "code": line.get("code", ""),
                "reason": line.get("uom_note") or "satuan tidak bisa dikonversi ke satuan dasar",
                "kind": "uom",
            })
        out.append(line)

    if strict_accessory:
        blocking = [p for p in problems
                    if p.get("kind") != "uom"
                    and ("aksesoris" in p["reason"] or "tidak ditemukan" in p["reason"])]
        if blocking:
            detail = "; ".join(
                f"baris {p['index'] + 1} \"{p['name'] or p['code'] or '(tanpa nama)'}\" — {p['reason']}"
                for p in blocking)
            raise HTTPException(
                400,
                "Baris aksesoris pada BOM wajib dipilih dari master material "
                "(klik ikon 🔍 'Pilih dari master' di editor BOM), supaya kebutuhan aksesoris "
                f"bisa dipotong dari stok yang benar. Perbaiki: {detail}.")
    return out, problems


# ══════════════════════════════════════════════════════════════════════════════
# SATUAN & KONVERSI BOM (2026-08-02) — endpoint pendukung editor & audit
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/bom-material-units/{material_id}")
async def bom_material_units(material_id: str, request: Request):
    """Daftar satuan yang SAH untuk baris BOM material ini (untuk dropdown editor).

    Isi: satuan dasar + kemasan resmi material (`uoms`) + satuan sedimensi dari
    tabel konversi global (gram/kg/ton, mm/cm/m/inch/yard, pcs/lusin/kodi/gross,
    ml/liter) + konversi silang meter⇄kg khusus kain bila `gsm` & `width_cm` ada.
    Setiap opsi menyertakan `factor_to_base` supaya editor bisa menampilkan
    pratinjau "= x kg" sebelum disimpan.
    """
    await require_auth(request)
    db = get_db()
    mat = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
    if not mat:
        raise HTTPException(404, "Material tidak ditemukan")
    units = bom_uom.allowed_units(mat)
    return {
        "material_id": material_id,
        "code": mat.get("code"),
        "name": mat.get("name"),
        "base_unit": bom_uom.norm_unit(mat.get("base_uom") or mat.get("unit") or "pcs"),
        "unit_cost": float(mat.get("unit_cost") or 0),
        "gsm": mat.get("gsm"),
        "width_cm": mat.get("width_cm"),
        "units": units,
        "hint": ("Satuan yang tidak ada di daftar ini tidak bisa dikonversi otomatis. "
                 "Tambahkan kemasannya di master material (Satuan & Kemasan), atau untuk "
                 "kain lengkapi gramasi (gsm) & lebar (cm)."),
    }


@router.get("/bom-uom-audit")
async def bom_uom_audit(request: Request, limit: int = 500):
    """Audit satuan seluruh BOM: baris mana yang satuannya belum bisa dikonversi.

    Dipakai untuk memastikan rantai BOM → kebutuhan material → pengeluaran gudang
    → HPP tidak lagi menghitung "gram" sebagai "kg".
    """
    await require_auth(request)
    db = get_db()
    boms = await db.rahaza_boms.find({"active": True}, {"_id": 0}).to_list(limit)
    models = {m["id"]: m async for m in db.rahaza_models.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1})}
    sizes = {s["id"]: s async for s in db.rahaza_sizes.find({}, {"_id": 0, "id": 1, "name": 1, "code": 1})}
    issues, counts = [], {"ok": 0, "base": 0, "uom": 0, "global": 0, "fabric": 0,
                          "mismatch": 0, "unlinked": 0}
    total_lines = 0
    for b in boms:
        mats, _w = await bom_uom.ensure_uom(db, b)
        for m in mats:
            total_lines += 1
            st = m.get("uom_status") or "base"
            counts[st] = counts.get(st, 0) + 1
            if st in ("mismatch", "unlinked"):
                mdl = models.get(b.get("model_id")) or {}
                sz = sizes.get(b.get("size_id")) or {}
                issues.append({
                    "bom_id": b.get("id"), "version": b.get("version"),
                    "model": mdl.get("code") or mdl.get("name") or b.get("model_id"),
                    "size": sz.get("name") or sz.get("code") or b.get("size_id"),
                    "material": m.get("name"), "code": m.get("code"),
                    "qty": m.get("qty"), "unit": m.get("unit"),
                    "unit_base": m.get("unit_base"),
                    "status": st, "note": m.get("uom_note"),
                })
    return {
        "boms_checked": len(boms),
        "lines_checked": total_lines,
        "status_counts": counts,
        "issues": issues,
        "clean": len(issues) == 0,
    }


@router.post("/bom-uom-backfill")
async def bom_uom_backfill(request: Request):
    """Hitung & simpan `qty_base/unit_base` untuk SEMUA baris BOM yang belum punya.

    Idempoten dan tidak mengubah `qty`/`unit` yang diinput user — hanya menambah
    hasil konversinya supaya konsumen hilir & UI tidak perlu menghitung ulang.
    """
    user = await _require_admin(request)
    db = get_db()
    updated, lines = 0, 0
    async for b in db.rahaza_boms.find({}, {"_id": 0}):
        mats = get_bom_materials(b)
        if not mats:
            continue
        annotated, _w = await bom_uom.annotate_materials(db, mats)
        if not annotated:
            continue
        await db.rahaza_boms.update_one({"id": b["id"]}, {"$set": {"materials": annotated}})
        updated += 1
        lines += len(annotated)
    await log_activity(user.get("id", ""), user.get("name", "system"),
                       "bom.uom_backfill", "rahaza-bom", f"boms={updated} lines={lines}")
    return {"ok": True, "boms_updated": updated, "lines_annotated": lines}


@router.post("/boms")
async def create_bom(request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    model_id = body.get("model_id")
    size_id  = body.get("size_id")
    if not (model_id and size_id):
        raise HTTPException(400, "model_id & size_id wajib diisi.")
    if not await db.rahaza_models.find_one({"id": model_id}):
        raise HTTPException(404, "Model tidak ditemukan")
    if not await db.rahaza_sizes.find_one({"id": size_id}):
        raise HTTPException(404, "Size tidak ditemukan")
    materials = _materials_from_body(body) or []
    if not materials:
        raise HTTPException(400, "BOM harus berisi minimal 1 material.")
    # ACC-2 — wajibkan kopling material_id untuk baris aksesoris (auto-link by code bila bisa)
    materials, _link_problems = await resolve_bom_materials(db, materials)
    # Fase 1: BOM per-varian. color "" = BOM umum (berlaku semua warna).
    color = (body.get("color") or "").strip()
    color_q = {"color": color} if color else {"color": {"$in": ["", None]}}

    # Auto-increment version number — scan versi utk (model,size,color) yang sama
    existing_versions = await db.rahaza_boms.find(
        {"model_id": model_id, "size_id": size_id, "active": True, **color_q},
        {"_id": 0, "version": 1}
    ).to_list(500)
    max_version = 0
    for ev in existing_versions:
        v = _parse_version(ev.get("version", 0))
        if v > max_version:
            max_version = v
    new_version = max_version + 1

    is_active = body.get("is_active", new_version == 1)
    if is_active:
        await db.rahaza_boms.update_many(
            {"model_id": model_id, "size_id": size_id, "active": True, **color_q},
            {"$set": {"is_active": False, "updated_at": _now()}}
        )

    doc = {
        "id": _uid(),
        "model_id": model_id,
        "size_id": size_id,
        "color": color,
        "version": new_version,
        "is_active": is_active,
        "materials": materials,
        "notes": body.get("notes") or "",
        "active": True,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_boms.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.bom", doc["id"])
    await _enrich_bom(db, doc)
    return serialize_doc(doc)


@router.put("/boms/{bid}")
async def update_bom(bid: str, request: Request):
    """Update BOM (untuk edit versi aktif atau versi lainnya)."""
    user = await _require_admin(request)
    db = get_db()
    bom = await db.rahaza_boms.find_one({"id": bid})
    if not bom:
        raise HTTPException(404, "BOM tidak ditemukan")
    body = await request.json()
    upd = {"updated_at": _now()}
    new_mats = _materials_from_body(body, fallback_bom=bom)
    if new_mats is not None:
        # ACC-2 — validasi kopling material_id sebelum menyimpan
        new_mats, _link_problems = await resolve_bom_materials(db, new_mats)
        upd["materials"] = new_mats
    if "notes" in body:
        upd["notes"] = body.get("notes") or ""
    # Validasi minimal 1 material tersisa
    final_mats = upd.get("materials", get_bom_materials(bom))
    if not final_mats:
        raise HTTPException(400, "BOM harus berisi minimal 1 material.")
    if "materials" in upd:
        await db.rahaza_boms.update_one(
            {"id": bid}, {"$set": upd, "$unset": {"yarn_materials": "", "accessory_materials": ""}})
    else:
        await db.rahaza_boms.update_one({"id": bid}, {"$set": upd})
    out = await db.rahaza_boms.find_one({"id": bid}, {"_id": 0})
    await _enrich_bom(db, out)
    await log_activity(user["id"], user.get("name", ""), "update", "rahaza.bom", bid)
    return serialize_doc(out)


@router.post("/boms/{bid}/activate")
async def activate_bom_version(bid: str, request: Request):
    """Activate a specific BOM version (and deactivate others for same model+size+color)."""
    user = await _require_admin(request)
    db = get_db()
    bom = await db.rahaza_boms.find_one({"id": bid, "active": True}, {"_id": 0})
    if not bom:
        raise HTTPException(404, "BOM tidak ditemukan")
    _c = (bom.get("color") or "").strip()
    _color_q = {"color": _c} if _c else {"color": {"$in": ["", None]}}
    await db.rahaza_boms.update_many(
        {"model_id": bom["model_id"], "size_id": bom["size_id"], "active": True, **_color_q},
        {"$set": {"is_active": False, "updated_at": _now()}}
    )
    await db.rahaza_boms.update_one({"id": bid}, {"$set": {"is_active": True, "updated_at": _now()}})
    await log_activity(user["id"], user.get("name", ""), "activate_version", "rahaza.bom", bid)
    out = await db.rahaza_boms.find_one({"id": bid}, {"_id": 0})
    await _enrich_bom(db, out)
    return serialize_doc(out)


@router.post("/boms/{bid}/requirements")
async def preview_requirements(bid: str, request: Request):
    """Preview kebutuhan material untuk X pcs (materials[] terunifikasi)."""
    await require_auth(request)
    db = get_db()
    bom = await db.rahaza_boms.find_one({"id": bid, "active": True}, {"_id": 0})
    if not bom:
        raise HTTPException(404, "BOM tidak ditemukan")

    body = await request.json()
    qty_pcs = float(body.get("qty_pcs", 0))
    if qty_pcs <= 0:
        raise HTTPException(400, "qty_pcs harus lebih dari 0")

    rounding = body.get("rounding", "none")  # none|ceil|floor

    materials = []
    total_yarn_kg = 0.0
    for m in get_bom_materials(bom):
        qty_per_pcs = float(m.get("qty") or 0)
        qty_total = qty_per_pcs * qty_pcs
        kglike = _is_kglike(m)
        if rounding == "ceil":
            qty_total = math.ceil(qty_total * 1000) / 1000 if kglike else math.ceil(qty_total)
        elif rounding == "floor":
            qty_total = math.floor(qty_total * 1000) / 1000 if kglike else math.floor(qty_total)
        materials.append({
            "material_id": m.get("material_id"),
            "name": m.get("name"),
            "code": m.get("code"),
            "material_type": m.get("material_type"),
            "category": m.get("category"),
            "category_name": m.get("category_name"),
            "qty_per_pcs": round(qty_per_pcs, 4),
            "qty_total": round(qty_total, 4),
            "unit": m.get("unit"),
            "notes": m.get("notes", ""),
        })
        if kglike:
            total_yarn_kg += qty_total

    await _enrich_bom(db, bom)
    return serialize_doc({
        "bom_id": bom["id"],
        "model_code": bom.get("model_code"),
        "model_name": bom.get("model_name"),
        "size_code": bom.get("size_code"),
        "version": bom.get("version"),
        "qty_pcs": qty_pcs,
        "rounding": rounding,
        "materials": materials,
        "total_material_lines": len(materials),
        # FASE 6.6-B: kanonik `total_material_kg` + alias legacy `total_yarn_kg`
        **material_fields.mirror("total_material_kg", round(total_yarn_kg, 4)),
    })


@router.delete("/boms/{bid}")
async def delete_bom(bid: str, request: Request):
    user = await _require_admin(request)
    db = get_db()
    res = await db.rahaza_boms.update_one({"id": bid}, {"$set": {"active": False, "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "BOM tidak ditemukan")
    await log_activity(user["id"], user.get("name", ""), "deactivate", "rahaza.bom", bid)
    return {"status": "deactivated"}


@router.post("/boms/{bid}/copy-to-sizes")
async def copy_bom_to_sizes(bid: str, request: Request):
    """
    Copy BOM (materials) dari source BOM ke target_size_ids pada model yang sama.
    Body: { target_size_ids: [..], overwrite: bool, copy_as_new_version: bool }
    """
    user = await _require_admin(request)
    db = get_db()
    src = await db.rahaza_boms.find_one({"id": bid, "active": True}, {"_id": 0})
    if not src:
        raise HTTPException(404, "BOM sumber tidak ditemukan")
    body = await request.json()
    target_size_ids = body.get("target_size_ids") or []
    overwrite = bool(body.get("overwrite"))
    copy_as_new_version = bool(body.get("copy_as_new_version", False))
    if not target_size_ids:
        raise HTTPException(400, "target_size_ids wajib diisi.")

    existing_active_map: dict = {}
    all_versions_by_size: dict = {}
    if target_size_ids:
        async for d in db.rahaza_boms.find(
            {"model_id": src["model_id"], "size_id": {"$in": target_size_ids},
             "active": True, "is_active": True}, {"_id": 0}
        ):
            existing_active_map[d["size_id"]] = d
        async for d in db.rahaza_boms.find(
            {"model_id": src["model_id"], "size_id": {"$in": target_size_ids}, "active": True},
            {"_id": 0, "size_id": 1, "version": 1}
        ):
            all_versions_by_size.setdefault(d["size_id"], []).append(d)

    src_materials = get_bom_materials(src)
    created, skipped, overwritten = [], [], []
    for sid in target_size_ids:
        if sid == src["size_id"]:
            skipped.append({"size_id": sid, "reason": "sama dengan sumber"})
            continue
        existing = existing_active_map.get(sid)
        payload = {
            "materials": src_materials,
            "notes": src.get("notes") or "",
            "updated_at": _now(),
        }
        if existing:
            if copy_as_new_version:
                existing_vers = all_versions_by_size.get(sid, [])
                max_v = max((_parse_version(ev.get("version", 0)) for ev in existing_vers), default=0)
                doc = {
                    "id": _uid(), "model_id": src["model_id"], "size_id": sid,
                    "color": src.get("color", ""), "version": max_v + 1, "is_active": False,
                    **payload, "active": True, "created_at": _now(),
                }
                await db.rahaza_boms.insert_one(doc)
                created.append(sid)
            elif not overwrite:
                skipped.append({"size_id": sid, "reason": "sudah ada BOM aktif (pakai overwrite=true atau copy_as_new_version=true)"})
                continue
            else:
                await db.rahaza_boms.update_one(
                    {"id": existing["id"]},
                    {"$set": payload, "$unset": {"yarn_materials": "", "accessory_materials": ""}})
                overwritten.append(sid)
        else:
            doc = {
                "id": _uid(), "model_id": src["model_id"], "size_id": sid,
                "color": src.get("color", ""), "version": 1, "is_active": True,
                **payload, "active": True, "created_at": _now(),
            }
            await db.rahaza_boms.insert_one(doc)
            created.append(sid)
    await log_activity(user["id"], user.get("name", ""), "copy", "rahaza.bom", bid)
    return {"created": created, "overwritten": overwritten, "skipped": skipped}
