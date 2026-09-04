"""core.accessory_stock — helper stok Aksesoris KANONIK (Fase 2.8).

Menyatukan silo stok aksesoris ke model kanonik:
  * Item aksesoris SUDAH kanonik → `rahaza_materials` (type='accessory').
  * Stok aksesoris SEKARANG ditulis ke `rahaza_material_stock` FLAT {material_id, location_id}
    lewat `stock_service` (jaga qty+alias+available_quantity) — BUKAN lagi Schema-B nested
    {material_id, location.id} dengan `$inc` mentah.
  * Reader mengagregasi lintas SEMUA baris per material (flat baru + nested lama) → tidak ada
    blind-spot skema.

Modul ini menggantikan 4 helper terduplikasi (`_get_accessory_location_id`, `_stock_qty`,
`_all_accessory_stock`, `_add_stock`) yang sebelumnya disalin identik di 7 file dewi_accessories_*.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core import stock_service
from core.stock_schema import read_qty
import logging

logger = logging.getLogger(__name__)

ACC_LOC_CODE = "ZNA-AKSESORIS"


def _now():
    return datetime.now(timezone.utc)


def _uid():
    return str(uuid.uuid4())


async def get_accessory_location_id(db) -> str:
    """Resolve lokasi khusus aksesoris untuk penulisan stok.

    FASE C: utamakan **zona kanonik `wh_*`** (peran 'aksesoris' = ZN-AKS). Bila struktur
    kanonik belum ada, fallback ke lokasi legacy `rahaza_locations` (kode ZNA-AKSESORIS)
    — dibuat bila belum ada. Reader mengagregasi lintas semua baris → stok lama (rahaza id)
    tetap terhitung meski penulisan baru mengarah ke zona kanonik."""
    # 1) Canonical wh zone (jika ada)
    #
    # 2026-08-07 — DULU `except Exception: pass`. Sama seperti di
    # `core/quarantine.py`: kegagalan resolusi zona kanonik membuat penulisan
    # stok aksesoris diam-diam pindah ke lokasi LEGACY, sehingga stok satu
    # material bisa terbelah ke dua id lokasi tanpa jejak apa pun. Fallback
    # tetap ada (fitur tidak boleh mati), tapi wajib meninggalkan jejak.
    try:
        from core import location_resolver
        zid = await location_resolver.canonical_zone_id_for_role(db, "aksesoris")
        if zid:
            return zid
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[aksesoris] gagal resolusi zona kanonik peran 'aksesoris' — memakai lokasi "
            "legacy %s. Stok aksesoris bisa terbelah antar lokasi bila ini berulang: %s",
            ACC_LOC_CODE, e)
    # 2) Fallback legacy rahaza_locations
    loc = await db.rahaza_locations.find_one({"code": ACC_LOC_CODE}, {"_id": 0, "id": 1})
    if loc:
        return loc["id"]
    new_id = _uid()
    await db.rahaza_locations.insert_one({
        "id": new_id,
        "code": ACC_LOC_CODE,
        "name": "Area Aksesoris",
        "description": "Dedicated location for accessory items",
        "type": "warehouse",
        "active": True,
        "created_at": _now(),
    })
    return new_id


async def stock_qty(db, material_id: str) -> float:
    """On-hand aksesoris utk 1 material — agregasi lintas SEMUA baris (kanonik)."""
    return await stock_service.get_onhand(material_id, db=db)


async def all_accessory_stock(db) -> dict:
    """Map {material_id: on-hand} agregasi kanonik utk SEMUA material (aksesoris lookup by id)."""
    return await stock_service.onhand_map(db=db)


async def stock_rows(db, material_id: str) -> list[dict]:
    """Baris stok fisik 1 material (lintas lokasi), qty dibaca lintas-skema A/B/C.

    `flat=False` menandai baris warisan Skema-B (lokasi BERSARANG, tanpa field
    `location_id` di level atas) — baris itu hanya bisa dipotong lewat
    `stock_service.issue_row` (by row id), bukan `issue(material_id, location_id)`.
    """
    rows = await stock_service.list_rows(material_id, db=db)
    out = []
    for r in rows or []:
        qty = float(read_qty(r) or 0)
        if qty <= 0:
            continue
        flat_loc = r.get("location_id")
        nested = r.get("location") if isinstance(r.get("location"), dict) else {}
        loc = flat_loc or nested.get("id") or ""
        out.append({"stock_id": r.get("id"), "location_id": loc,
                    "qty": qty, "flat": bool(flat_loc)})
    return out


async def issue_across_locations(db, material_id: str, qty: float, *,
                                 preferred_location_id: str = "",
                                 actor=None, ref=None) -> list[dict]:
    """Potong stok aksesoris LINTAS LOKASI.

    KENAPA ADA (bug nyata, terbukti HTTP 500)
    Pembaca stok aksesoris mengagregasi SEMUA baris (`stock_service.onhand_map`),
    sementara penulis lama selalu memotong di SATU lokasi kanonik (ZN-AKS). Untuk
    item yang stoknya duduk di lokasi lain — data warisan, hasil put-away, atau
    seed demo (`ACC-BTN-12` 5.000 pcs di `int-demo-loc-1`) — validasi "stok cukup"
    LOLOS tetapi pemotongan melempar `InsufficientStock` ⇒ 500 di
    `/api/acc/stock/issue`, `/api/dewi/accessory-requests/{id}/deliver`, dan baris
    opname diam-diam terlewat.

    Urutan pemotongan: lokasi kanonik/preferensi DULU (supaya perilaku lama tetap
    sama untuk item normal), lalu baris dengan stok terbesar. Bila total lintas
    lokasi memang kurang, `InsufficientStock` tetap dilempar (caller mengubahnya
    jadi 400 yang ramah, bukan 500).

    Return: rencana pemotongan [{location_id, qty}] untuk jejak audit.
    """
    need = round(float(qty or 0), 4)
    if need <= 0:
        return []
    rows = await stock_rows(db, material_id)
    total = round(sum(r["qty"] for r in rows), 4)
    if total + 1e-6 < need:
        raise stock_service.InsufficientStock(
            material_id, preferred_location_id or "(semua lokasi)", need, total)

    rows.sort(key=lambda r: (0 if r["location_id"] == preferred_location_id else 1, -r["qty"]))
    plan: list[dict] = []
    remaining = need
    for r in rows:
        if remaining <= 1e-6:
            break
        take = round(min(r["qty"], remaining), 4)
        if take <= 0:
            continue
        if r["flat"]:
            await stock_service.issue(material_id, r["location_id"], take,
                                      ref=ref, actor=actor, db=db)
        else:  # baris warisan lokasi-bersarang → potong by row id
            await stock_service.issue_row(r["stock_id"], take,
                                          ref=ref, actor=actor, db=db)
        plan.append({"location_id": r["location_id"], "qty": take})
        remaining = round(remaining - take, 4)
    if remaining > 1e-6:  # balapan tulis dgn proses lain
        raise stock_service.InsufficientStock(
            material_id, preferred_location_id or "(semua lokasi)", need, need - remaining)
    return plan


async def add_stock(db, material_id: str, location_id: str, delta: float, *,
                    actor=None, ref=None):
    """Mutasi stok aksesoris via stock_service.

    delta > 0 → add (inbound/retur/opname naik) di lokasi kanonik.
    delta < 0 → issue LINTAS LOKASI (lihat `issue_across_locations`) supaya
    penulis simetris dengan pembaca yang mengagregasi semua lokasi.
    Guard tetap aktif → `InsufficientStock` bila total on-hand memang kurang."""
    delta = float(delta or 0)
    if delta == 0:
        return
    meta = {"inventory_category": "aksesoris", "material_type": "accessory"}
    _ref = {"source": "accessory"}
    if ref:
        _ref.update(ref)
    if delta > 0:
        await stock_service.add(material_id, location_id, delta,
                                meta=meta, ref=_ref, actor=actor, db=db)
    else:
        await issue_across_locations(db, material_id, abs(delta),
                                     preferred_location_id=location_id,
                                     actor=actor, ref=_ref)
