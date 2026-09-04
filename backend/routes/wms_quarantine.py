"""wms_quarantine — FASE 6 (INV-8): KARANTINA QC (barang reject) & disposisinya.

Endpoint (prefix /api/wms/quarantine):
  GET    /                        → daftar item karantina (filter status/material/source)
  GET    /summary                 → KPI (item terbuka, qty, nilai, umur tertua, per-alasan)
  GET    /location                → info lokasi karantina kanonik
  GET    /reject-categories       → kategori alasan reject (reuse standar GRN QC)
  POST   /{item_id}/release       → lepas ke lokasi storage (barang jadi tersedia lagi)
  POST   /{item_id}/return-supplier → keluarkan utk retur ke supplier
  POST   /{item_id}/scrap         → buang (write-off)
  POST   /manual                  → masukkan material ke karantina secara manual (mis. temuan gudang)

ATURAN JURNAL (grounded, lihat plan.md FASE 6):
  * Reject **saat GR** ⇒ `valued=False` (AP invoice pakai net qty ⇒ belum pernah masuk
    nilai persediaan). Retur/scrap barang belum bernilai ⇒ **TANPA JE**. `release`
    barang belum bernilai ⇒ **kapitalisasi** via `post_inventory_adjust(+)`.
  * Reject dari **re-inspeksi pasca-terima** ⇒ `valued=True` (sudah masuk nilai).
    `scrap`/`return_supplier` ⇒ `post_inventory_adjust(−)` (`adjustment_reason='scrap'`
    → Dr Scrap Expense / Cr Inventory). `release` ⇒ tanpa JE (nilai tak berubah,
    hanya pindah lokasi).
"""
from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone
import uuid
import logging

from database import get_db
from auth import require_auth, check_role, log_activity, serialize_doc
from core import quarantine, location_resolver
from utils.reject_reasons import normalize_reject_reasons  # FASE 19: SSOT bentuk alasan reject
from routes.rahaza_posting import post_inventory_adjust

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wms/quarantine", tags=["wms-quarantine"])

# ─────────────────────────────────────────────────────────────────────────────
# RBAC — SSOT dipindah ke `core/stock_rbac.py` (FASE 8) agar dipakai bersama
# karantina QC + scrap aksesoris. Nama lokal dipertahankan supaya tidak ada
# perubahan perilaku di file ini.
#
# Catatan historis (FASE 6.5 temuan #2): daftar role sempat diisi nama TEBAKAN
# (`gudang`, `staff_gudang`, `warehouse`, `warehouse_manager`, `manajer`,
# `keuangan`) yang TIDAK ADA di master role (koleksi `roles`, 21 entri). Karena
# `auth.check_role` mencocokkan EXACT, role gudang NYATA (`spv_packing`,
# `tim_packing`, `admin_aksesoris`) justru selalu 403. Sekarang daftar kanonik
# ada di satu tempat — lihat komentar lengkap di `core/stock_rbac.py`.
# ─────────────────────────────────────────────────────────────────────────────
from core.stock_rbac import DISPOSE_ROLES, SCRAP_ROLES  # noqa: E402


def _uid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


async def _get_item_or_404(db, item_id: str) -> dict:
    item = await db[quarantine.QUARANTINE_COLL].find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Item karantina tidak ditemukan")
    return item


async def _post_je(db, *, item: dict, qty: float, direction: int, reason: str, user: dict) -> dict:
    """Buat movement `rahaza_material_movements` lalu posting JE inventory adjust.

    direction = +1 (kapitalisasi masuk nilai) atau -1 (write-off keluar nilai).
    """
    unit_cost = float(item.get("unit_cost") or 0)
    if unit_cost <= 0:
        return {"ok": False, "error": "Harga satuan (unit_cost) material = 0 — jurnal dilewati.",
                "skipped": True}
    mv = {
        "id": _uid(),
        "material_id": item["material_id"],
        "material_name": item.get("material_name", ""),
        "material_code": item.get("material_code", ""),
        "type": "adjust",
        "qty": float(qty) * (1 if direction > 0 else -1),
        "unit": item.get("unit", "pcs"),
        "unit_cost": unit_cost,
        "location_id": item.get("location_id"),
        "reference_type": "quarantine",
        "reference_id": item["id"],
        "related_type": "quarantine",
        "related_ref": item["id"],
        "adjustment_reason": reason,
        "notes": f"Karantina QC — {reason} {qty} {item.get('unit','pcs')} {item.get('material_code','')}",
        "created_by": user.get("id", ""),
        "created_by_name": user.get("name", ""),
        "created_at": _now(),
        "timestamp": _now(),
    }
    await db.rahaza_material_movements.insert_one(mv)
    mv.pop("_id", None)
    try:
        return await post_inventory_adjust(db, mv, user)
    except Exception as e:
        logger.exception("quarantine JE gagal")
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# READ
# ─────────────────────────────────────────────────────────────────────────────
@router.get("")
async def list_quarantine(
    request: Request,
    status: str = Query("open", description="open | closed | all"),
    material_id: Optional[str] = None,
    source_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    needs_action: bool = Query(False, description="hanya item yang ketersediaannya BELUM terblokir"),
):
    await require_auth(request)
    db = get_db()
    rows = await quarantine.list_items(db, status=status, material_id=material_id,
                                      source_id=source_id, limit=limit,
                                      needs_action=needs_action)
    return serialize_doc(rows)


@router.post("/{item_id}/retry-block")
async def retry_block_item(item_id: str, request: Request):
    """Coba blokir ULANG ketersediaan item karantina yang blokirnya gagal.

    Tanpa endpoint ini, daftar "Perlu Tindakan Manual" hanya bisa memberi tahu tanpa
    bisa memperbaiki — kegagalan blokir harus dibetulkan lewat database.
    """
    user = await require_auth(request)
    if not check_role(user, DISPOSE_ROLES):
        raise HTTPException(403, "Hanya staf gudang/supervisor yang boleh memblokir ulang stok karantina")
    db = get_db()
    actor = {"id": user.get("id", ""), "name": user.get("name", ""), "email": user.get("email", "")}
    try:
        res = await quarantine.retry_block(db, item_id=item_id, actor=actor)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            409,
            f"Gagal memblokir ulang ketersediaan: {e}. Biasanya karena stok fisik di "
            f"lokasi karantina lebih kecil dari qty karantina (stok sudah dipakai jalur "
            f"lain) — perlu opname/koreksi stok dulu.")
    await log_activity(user.get("id", ""), user.get("name", ""), "quarantine_retry_block",
                       "wh_quarantine_items",
                       f"Blokir ulang ketersediaan karantina {item_id}: {res.get('diblokir')}")
    return res


@router.get("/summary")
async def quarantine_summary(request: Request):
    await require_auth(request)
    db = get_db()
    return serialize_doc(await quarantine.summary(db))


@router.get("/location")
async def quarantine_location(request: Request):
    await require_auth(request)
    db = get_db()
    info = await quarantine.get_quarantine_location_info(db)
    storage = await location_resolver.list_storage_locations(db)
    info["storage_locations"] = [s for s in storage if s.get("id") != info["id"]]
    return serialize_doc(info)


@router.get("/reject-categories")
async def reject_categories(request: Request):
    await require_auth(request)
    from routes.rahaza_grn_qc import REJECT_CATEGORIES
    return REJECT_CATEGORIES


# ─────────────────────────────────────────────────────────────────────────────
# DISPOSISI
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/{item_id}/release")
async def release_item(item_id: str, request: Request):
    """Lepas barang karantina ke lokasi storage (mis. lolos re-inspeksi / setelah rework).
    Body: {qty?, to_location_id, notes?}"""
    user = await require_auth(request)
    if not check_role(user, DISPOSE_ROLES):
        raise HTTPException(403, "Hanya staf gudang/supervisor yang boleh melepas barang karantina")
    db = get_db()
    body = await request.json() if await request.body() else {}
    item = await _get_item_or_404(db, item_id)
    if item.get("status") != "open":
        raise HTTPException(400, "Item karantina sudah ditutup")

    qty = float(body.get("qty") or item.get("remaining_qty") or 0)
    to_loc = body.get("to_location_id")
    if not to_loc:
        raise HTTPException(400, "to_location_id wajib diisi (lokasi tujuan penyimpanan)")
    if not await location_resolver.location_exists(db, to_loc):
        raise HTTPException(404, "Lokasi tujuan tidak ditemukan")

    actor = {"id": user.get("id", ""), "name": user.get("name", ""), "email": user.get("email", "")}
    try:
        res = await quarantine.quarantine_out(db, item=item, action=quarantine.ACTION_RELEASE,
                                             qty=qty, to_location_id=to_loc, actor=actor,
                                             notes=body.get("notes", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))

    # JE: barang BELUM bernilai → kapitalisasi (+). Barang sudah bernilai → tanpa JE.
    posting = {"ok": True, "skipped": True, "reason": "sudah bernilai — pindah lokasi tidak mengubah nilai"}
    if not item.get("valued"):
        posting = await _post_je(db, item=item, qty=qty, direction=+1,
                                reason="quarantine_release", user=user)
        if posting.get("ok"):
            await db[quarantine.QUARANTINE_COLL].update_one({"id": item_id}, {"$set": {"valued": True}})

    await log_activity(user.get("id", ""), user.get("name", ""), "quarantine_release",
                       "wh_quarantine_items",
                       f"Lepas {qty} {item.get('unit','')} {item.get('material_code','')} dari karantina")
    return {"ok": True, "action": "release", "qty": qty, "to_location_id": to_loc,
            "remaining_qty": res["remaining_qty"], "closed": res["closed"], "posting": posting}


@router.post("/{item_id}/return-supplier")
async def return_to_supplier(item_id: str, request: Request):
    """Keluarkan barang karantina untuk diretur ke supplier. Body: {qty?, notes?}"""
    user = await require_auth(request)
    if not check_role(user, DISPOSE_ROLES):
        raise HTTPException(403, "Hanya staf gudang/supervisor yang boleh memproses retur supplier")
    db = get_db()
    body = await request.json() if await request.body() else {}
    item = await _get_item_or_404(db, item_id)
    if item.get("status") != "open":
        raise HTTPException(400, "Item karantina sudah ditutup")
    qty = float(body.get("qty") or item.get("remaining_qty") or 0)
    actor = {"id": user.get("id", ""), "name": user.get("name", ""), "email": user.get("email", "")}
    try:
        res = await quarantine.quarantine_out(db, item=item, action=quarantine.ACTION_RETURN,
                                              qty=qty, actor=actor, notes=body.get("notes", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))

    # JE hanya bila barang SUDAH bernilai (pernah masuk nilai persediaan)
    posting = {"ok": True, "skipped": True,
               "reason": "belum pernah masuk nilai persediaan (AP invoice pakai net qty)"}
    if item.get("valued"):
        posting = await _post_je(db, item=item, qty=qty, direction=-1,
                                 reason="return_supplier", user=user)

    await log_activity(user.get("id", ""), user.get("name", ""), "quarantine_return_supplier",
                       "wh_quarantine_items",
                       f"Retur supplier {qty} {item.get('unit','')} {item.get('material_code','')}")
    return {"ok": True, "action": "return_supplier", "qty": qty,
            "remaining_qty": res["remaining_qty"], "closed": res["closed"], "posting": posting}


@router.post("/{item_id}/scrap")
async def scrap_item(item_id: str, request: Request):
    """Buang barang karantina (write-off). Body: {qty?, notes?}"""
    user = await require_auth(request)
    if not check_role(user, SCRAP_ROLES):
        raise HTTPException(403, "Scrap = write-off nilai persediaan. Hanya Admin Gudang, Supervisor, "
                                 "Keuangan, atau Owner yang boleh melakukannya. Silakan ajukan ke atasan Anda.")
    db = get_db()
    body = await request.json() if await request.body() else {}
    item = await _get_item_or_404(db, item_id)
    if item.get("status") != "open":
        raise HTTPException(400, "Item karantina sudah ditutup")
    qty = float(body.get("qty") or item.get("remaining_qty") or 0)
    actor = {"id": user.get("id", ""), "name": user.get("name", ""), "email": user.get("email", "")}
    try:
        res = await quarantine.quarantine_out(db, item=item, action=quarantine.ACTION_SCRAP,
                                              qty=qty, actor=actor, notes=body.get("notes", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))

    posting = {"ok": True, "skipped": True,
               "reason": "belum pernah masuk nilai persediaan → tidak perlu write-off"}
    if item.get("valued"):
        posting = await _post_je(db, item=item, qty=qty, direction=-1, reason="scrap", user=user)

    await log_activity(user.get("id", ""), user.get("name", ""), "quarantine_scrap",
                       "wh_quarantine_items",
                       f"Scrap {qty} {item.get('unit','')} {item.get('material_code','')}")
    return {"ok": True, "action": "scrap", "qty": qty,
            "remaining_qty": res["remaining_qty"], "closed": res["closed"], "posting": posting}


# ─────────────────────────────────────────────────────────────────────────────
# MANUAL IN (temuan gudang: barang rusak ditemukan saat penyimpanan)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/manual")
async def manual_quarantine(request: Request):
    """Pindahkan stok yang SUDAH ada di lokasi storage ke KARANTINA.
    Body: {material_id, qty, from_location_id, reason_code?, notes?}"""
    user = await require_auth(request)
    if not check_role(user, DISPOSE_ROLES):
        raise HTTPException(403, "Hanya staf gudang/supervisor yang boleh mengarantina stok")
    db = get_db()
    body = await request.json()
    material_id = body.get("material_id")
    qty = float(body.get("qty") or 0)
    from_loc = body.get("from_location_id")
    if not material_id or qty <= 0 or not from_loc:
        raise HTTPException(400, "material_id, qty (>0) dan from_location_id wajib diisi")

    actor = {"id": user.get("id", ""), "name": user.get("name", ""), "email": user.get("email", "")}
    # Alasan bisa datang dalam 2 bentuk:
    #   * `reason_code` (dipakai FE ManualModal — 1 alasan untuk seluruh qty)
    #   * `reject_reasons` [{code, qty, notes}] (dipakai integrasi/script & jalur GR)
    # Terima keduanya supaya alasan tidak pernah hilang (dulu array diabaikan → alasan
    # tampil "-" di UI dan masuk bucket "OTHER" di ringkasan).
    # FASE 19: pembersihan ad-hoc di sini DIGANTI SSOT `utils/reject_reasons.py`
    # (dulu dua penulis punya aturan berbeda — itu akar 500 di ringkasan karantina).
    reasons = normalize_reject_reasons(body.get("reject_reasons"), default_qty=qty)
    if not reasons and body.get("reason_code"):
        reasons = normalize_reject_reasons(
            [{"code": body["reason_code"], "qty": qty, "notes": body.get("notes", "")}],
            default_qty=qty)
    try:
        doc = await quarantine.quarantine_in(
            db, material_id=material_id, qty=qty,
            # JANGAN paksa 'pcs': bila FE tak kirim unit, pakai satuan master material
            # (kain 'm' pernah tampil sebagai 'pcs' karena default hardcoded).
            unit=body.get("unit") or None,
            source={"type": "manual", "id": "", "number": "", "supplier_name": "", "po_number": ""},
            reject_reasons=reasons,
            # stok yang dipindah dari storage SUDAH masuk nilai persediaan
            valued=True, notes=body.get("notes", ""), actor=actor, from_location_id=from_loc)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Gagal mengarantina: {e}")

    await log_activity(user.get("id", ""), user.get("name", ""), "quarantine_manual_in",
                       "wh_quarantine_items",
                       f"Karantina manual {qty} {doc.get('material_code','')}")
    return serialize_doc(doc)
