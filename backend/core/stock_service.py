"""stock_service — SATU-SATUNYA pintu mutasi stok `rahaza_material_stock`.

FASE 1B: modul fondasi. BELUM dipasang ke route mana pun (tidak mengubah
perilaku live). Akan di-wire bertahap di Fase 2.

Prinsip:
  * Identitas baris stok = (material_id, location_id). Satu material di satu
    lokasi = SATU baris. `ownership` & `inventory_category` disimpan sbg
    ATRIBUT baris (bukan bucket kuantitas terpisah) → semua reader lintas-skema
    melihat baris yang sama.
  * Setiap tulis WAJIB menjaga skema kanonik:
        qty  == total_qty == quantity   (jumlah fisik on-hand)
        reserved_quantity               (jumlah ter-reserve)
        available_quantity = qty - reserved_quantity
  * Operasi memakai aggregation-pipeline update (atomic, race-safe) sehingga
    `available_quantity` selalu konsisten dengan qty & reserved.
  * Setiap mutasi menulis 1 baris ledger ke `rahaza_stock_ledger` (jejak audit).

API:
  add(material_id, location_id, qty, ...)       -> inbound (produksi, GR, retur)
  issue(material_id, location_id, qty, ...)     -> outbound (guarded, tak minus)
  reserve(material_id, location_id, qty, ...)   -> reservasi (guarded by available)
  release(material_id, location_id, qty, ...)   -> lepas reservasi
  move(material_id, from_location, to_location, qty, ...) -> transfer antar lokasi
  adjust(material_id, location_id, counted_qty, ...)      -> opname (set absolut)
  get_onhand(material_id) / get_available(material_id) / list_rows(material_id)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from database import get_db
from core.stock_schema import read_qty, read_available, read_reserved
from core import uom as _uom
import logging

logger = logging.getLogger(__name__)

STOCK = "rahaza_material_stock"
LEDGER = "rahaza_stock_ledger"

_META_FIELDS = (
    "ownership", "inventory_category", "material_type", "material_code",
    "material_name", "category", "category_name", "unit", "location_code",
)


class InsufficientStock(Exception):
    """Dilempar saat qty/available tidak cukup untuk operasi outbound/reserve."""

    def __init__(self, material_id, location_id, requested, available):
        self.material_id = material_id
        self.location_id = location_id
        self.requested = requested
        self.available = available
        super().__init__(
            f"Stok tidak cukup untuk {material_id} @ {location_id}: "
            f"minta {requested}, tersedia {available}"
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


def _r(v) -> float:
    """Round 4 desimal untuk hindari galat float."""
    return round(float(v or 0), 4)


def _db(db):
    return db if db is not None else get_db()


def _reserved_expr():
    """Ekspresi reserved dengan fallback alias lama `reserved`."""
    return {"$ifNull": ["$reserved_quantity", {"$ifNull": ["$reserved", 0]}]}


def _qty_expr():
    return {"$ifNull": ["$qty", 0]}


def _meta_set(meta: dict | None) -> dict:
    """Bangun fragmen $set utk metadata yang disediakan caller (overwrite)."""
    out = {}
    if not meta:
        return out
    for k in _META_FIELDS:
        if meta.get(k) is not None:
            out[k] = meta[k]
    return out


def _recompute_stage():
    """Stage kedua: sinkronkan alias & hitung ulang available."""
    return {
        "$set": {
            "total_qty": "$qty",
            "quantity": "$qty",
            "available_quantity": {
                "$round": [{"$subtract": ["$qty", _reserved_expr()]}, 4]
            },
        }
    }


async def _log(db, *, op, material_id, location_id, delta, qty_after,
               ref=None, actor=None, meta=None, extra=None):
    doc = {
        "id": _uid(),
        "op": op,
        "material_id": material_id,
        "location_id": location_id,
        "delta": _r(delta),
        "qty_after": _r(qty_after),
        "ref": ref or {},
        "actor": actor or {},
        "created_at": _now(),
    }
    if meta:
        doc["meta"] = {k: meta[k] for k in _META_FIELDS if meta.get(k) is not None}
    if extra:
        doc.update(extra)
    await db[LEDGER].insert_one(doc)
    return doc


async def _row(db, material_id, location_id):
    return await db[STOCK].find_one(
        {"material_id": material_id, "location_id": location_id}, {"_id": 0}
    )


# ─────────────────────────────────────────────────────────────────────────────
# KONVERSI SATUAN (opsional — LAPIS L1 strategi nol-regresi)
# ─────────────────────────────────────────────────────────────────────────────
# Semua fungsi mutasi menerima `input_uom=None`. Bila TIDAK diisi, perilakunya
# sama persis seperti sebelumnya (qty dianggap sudah dalam satuan dasar),
# sehingga 52 pemanggil lama tidak perlu disentuh sama sekali.
#
# Bila diisi, qty dikonversi ke satuan dasar memakai `core/uom` dan jejaknya
# (`input_qty`, `input_uom`, `uom_factor`) dibekukan di baris ledger — supaya
# riwayat tetap terbaca benar walau isi kemasan diubah di kemudian hari
# (INV-UOM-2 & INV-UOM-5).
async def _conv(db, material_id, qty, input_uom):
    """Return (qty_base, jejak_dict). `jejak_dict` kosong bila tanpa konversi."""
    if not input_uom:
        return _r(qty), {}
    code = _uom.normalize_code(input_uom)
    mat = await db["rahaza_materials"].find_one({"id": material_id}, {"_id": 0})
    if not mat:
        # material tidak ditemukan → jangan menebak, perlakukan sbg satuan dasar
        return _r(qty), {}
    if code == _uom.base_uom_of(mat):
        return _r(qty), {}
    # 2026-08-05 — cakupan konversi DILEBARKAN agar sama dengan BOM/Costing:
    # selain kemasan resmi material, satuan sedimensi global (gram↔kg, cm↔m,
    # lusin↔pcs) dan kain m↔kg (via gramasi & lebar) juga diterima. Ini yang
    # membuat pemilih satuan di layar (put-away, opname, pengeluaran, cutting)
    # berguna walau kemasan per item belum diisi owner.
    source = "uom"
    try:
        factor = _uom.factor_of(mat, code)      # kemasan resmi material
    except _uom.UomError:
        from core import bom_uom as _bom_uom    # lazy: hindari impor siklik
        factor, source = _bom_uom.factor_to_base(mat, code)   # global / kain
    return _r(float(qty) * factor), {
        "input_qty": _r(qty),
        "input_uom": code,
        "uom_factor": factor,
        "uom_source": source,
    }


# ─────────────────────────────────────────────────────────────────────────────
# INBOUND
# ─────────────────────────────────────────────────────────────────────────────
async def add(material_id, location_id, qty, *, meta=None, ref=None,
              actor=None, db=None, input_uom=None):
    """Tambah stok (upsert). Idempotent-safe untuk penerimaan/retur.

    `input_uom` opsional: bila diisi, `qty` dianggap dalam satuan tersebut dan
    dikonversi ke satuan dasar. Tanpa argumen ini perilakunya tidak berubah.
    """
    db = _db(db)
    qty, _trace = await _conv(db, material_id, qty, input_uom)
    if qty <= 0:
        raise ValueError("qty harus > 0")
    key = {"material_id": material_id, "location_id": location_id}
    set_stage = {
        "material_id": material_id,
        "location_id": location_id,
        "qty": {"$round": [{"$add": [_qty_expr(), qty]}, 4]},
        "reserved_quantity": _reserved_expr(),
        "id": {"$ifNull": ["$id", _uid()]},
        "created_at": {"$ifNull": ["$created_at", _now()]},
        "updated_at": _now(),
    }
    set_stage.update(_meta_set(meta))
    await db[STOCK].update_one(key, [{"$set": set_stage}, _recompute_stage()], upsert=True)
    row = await _row(db, material_id, location_id)
    await _log(db, op="add", material_id=material_id, location_id=location_id,
               delta=qty, qty_after=read_qty(row), ref=ref, actor=actor, meta=meta,
               extra=_trace or None)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# OUTBOUND (guarded)
# ─────────────────────────────────────────────────────────────────────────────
async def issue(material_id, location_id, qty, *, ref=None, actor=None,
                allow_negative=False, db=None, input_uom=None):
    """Kurangi stok fisik. Guarded: tidak boleh minus (kecuali allow_negative).

    `input_uom` opsional — lihat catatan pada `add()`.
    """
    db = _db(db)
    qty, _trace = await _conv(db, material_id, qty, input_uom)
    if qty <= 0:
        raise ValueError("qty harus > 0")
    key = {"material_id": material_id, "location_id": location_id}
    filt = dict(key)
    if not allow_negative:
        filt["$expr"] = {"$gte": [_qty_expr(), qty]}
    set_stage = {
        "qty": {"$round": [{"$subtract": [_qty_expr(), qty]}, 4]},
        "reserved_quantity": _reserved_expr(),
        "updated_at": _now(),
    }
    res = await db[STOCK].update_one(filt, [{"$set": set_stage}, _recompute_stage()])
    if res.matched_count == 0:
        row = await _row(db, material_id, location_id)
        raise InsufficientStock(material_id, location_id, qty, read_qty(row))
    row = await _row(db, material_id, location_id)
    await _log(db, op="issue", material_id=material_id, location_id=location_id,
               delta=-qty, qty_after=read_qty(row), ref=ref, actor=actor,
               extra=_trace or None)
    return row


async def issue_row(stock_id, qty, *, release_reserved=False, ref=None, actor=None, db=None):
    """Kurangi stok pada BARIS spesifik (by row id) — untuk outbound fulfillment yang
    memilih baris stok tertentu. Opsional lepas `reserved` sejumlah qty. Jaga alias+available."""
    db = _db(db)
    qty = _r(qty)
    if qty <= 0:
        raise ValueError("qty harus > 0")
    filt = {"id": stock_id, "$expr": {"$gte": [_qty_expr(), qty]}}
    set_stage = {
        "qty": {"$round": [{"$subtract": [_qty_expr(), qty]}, 4]},
        "updated_at": _now(),
    }
    if release_reserved:
        set_stage["reserved_quantity"] = {"$round": [{"$max": [0, {"$subtract": [_reserved_expr(), qty]}]}, 4]}
    else:
        set_stage["reserved_quantity"] = _reserved_expr()
    res = await db[STOCK].update_one(filt, [{"$set": set_stage}, _recompute_stage()])
    if res.matched_count == 0:
        row = await db[STOCK].find_one({"id": stock_id}, {"_id": 0})
        raise InsufficientStock(
            (row or {}).get("material_id", stock_id), stock_id, qty, read_qty(row) if row else 0
        )
    row = await db[STOCK].find_one({"id": stock_id}, {"_id": 0})
    await _log(db, op="issue_row", material_id=(row or {}).get("material_id"),
               location_id=(row or {}).get("location_id"), delta=-qty,
               qty_after=read_qty(row), ref=ref, actor=actor,
               extra={"stock_id": stock_id, "released_reserved": release_reserved})
    return row


# ─────────────────────────────────────────────────────────────────────────────
# RESERVASI
# ─────────────────────────────────────────────────────────────────────────────
async def reserve(material_id, location_id, qty, *, ref=None, actor=None, db=None):
    """Reserve stok. Guarded oleh available (qty - reserved)."""
    db = _db(db)
    qty = _r(qty)
    if qty <= 0:
        raise ValueError("qty harus > 0")
    key = {"material_id": material_id, "location_id": location_id}
    filt = dict(key)
    filt["$expr"] = {"$gte": [{"$subtract": [_qty_expr(), _reserved_expr()]}, qty]}
    set_stage = {
        "reserved_quantity": {"$round": [{"$add": [_reserved_expr(), qty]}, 4]},
        "updated_at": _now(),
    }
    res = await db[STOCK].update_one(filt, [{"$set": set_stage}, _recompute_stage()])
    if res.matched_count == 0:
        row = await _row(db, material_id, location_id)
        raise InsufficientStock(material_id, location_id, qty, read_available(row))
    row = await _row(db, material_id, location_id)
    await _log(db, op="reserve", material_id=material_id, location_id=location_id,
               delta=qty, qty_after=read_qty(row), ref=ref, actor=actor,
               extra={"reserved_after": read_reserved(row)})
    return row


async def release(material_id, location_id, qty, *, ref=None, actor=None, db=None):
    """Lepas reservasi (floor di 0)."""
    db = _db(db)
    qty = _r(qty)
    if qty <= 0:
        raise ValueError("qty harus > 0")
    key = {"material_id": material_id, "location_id": location_id}
    set_stage = {
        "reserved_quantity": {
            "$round": [{"$max": [0, {"$subtract": [_reserved_expr(), qty]}]}, 4]
        },
        "qty": _qty_expr(),
        "updated_at": _now(),
    }
    res = await db[STOCK].update_one(key, [{"$set": set_stage}, _recompute_stage()])
    if res.matched_count == 0:
        raise InsufficientStock(material_id, location_id, qty, 0)
    row = await _row(db, material_id, location_id)
    await _log(db, op="release", material_id=material_id, location_id=location_id,
               delta=-qty, qty_after=read_qty(row), ref=ref, actor=actor,
               extra={"reserved_after": read_reserved(row)})
    return row


async def reserve_row(stock_id, qty, *, ref=None, actor=None, db=None):
    """Reserve pada BARIS spesifik (by row id) — untuk fulfillment yang memilih baris stok
    tertentu (mis. Schema C tanpa location_id). Guarded oleh available baris. Jaga alias+available."""
    db = _db(db)
    qty = _r(qty)
    if qty <= 0:
        raise ValueError("qty harus > 0")
    filt = {"id": stock_id,
            "$expr": {"$gte": [{"$subtract": [_qty_expr(), _reserved_expr()]}, qty]}}
    set_stage = {
        "reserved_quantity": {"$round": [{"$add": [_reserved_expr(), qty]}, 4]},
        "qty": _qty_expr(),
        "updated_at": _now(),
    }
    res = await db[STOCK].update_one(filt, [{"$set": set_stage}, _recompute_stage()])
    if res.matched_count == 0:
        row = await db[STOCK].find_one({"id": stock_id}, {"_id": 0})
        raise InsufficientStock(
            (row or {}).get("material_id", stock_id), stock_id, qty,
            read_available(row) if row else 0)
    row = await db[STOCK].find_one({"id": stock_id}, {"_id": 0})
    await _log(db, op="reserve_row", material_id=(row or {}).get("material_id"),
               location_id=(row or {}).get("location_id"), delta=qty,
               qty_after=read_qty(row), ref=ref, actor=actor,
               extra={"stock_id": stock_id, "reserved_after": read_reserved(row)})
    return row


async def reserve_material(material_id, qty, *, ref=None, actor=None, db=None):
    """Reserve stok level-material lintas semua baris (greedy by available desc).
    Dipakai reservasi FG manual (rahaza_fg_matrix) → menulis ke `reserved_quantity` kanonik
    (SATU sumber reservasi, sama dgn fulfillment). Rollback bila gagal di tengah."""
    db = _db(db)
    qty = _r(qty)
    if qty <= 0:
        raise ValueError("qty harus > 0")
    rows = await list_rows(material_id, db=db)
    total_avail = _r(sum(read_available(r) for r in rows))
    if total_avail < qty:
        raise InsufficientStock(material_id, None, qty, total_avail)
    rows.sort(key=lambda r: read_available(r), reverse=True)
    remaining = qty
    done = []  # (stock_id, amount) untuk rollback
    try:
        for r in rows:
            if remaining <= 0:
                break
            avail = read_available(r)
            if avail <= 0:
                continue
            take = _r(min(avail, remaining))
            await reserve_row(r["id"], take, ref=ref, actor=actor, db=db)
            done.append((r["id"], take))
            remaining = _r(remaining - take)
        if remaining > 0:  # race: kurang di tengah → rollback
            raise InsufficientStock(material_id, None, qty, _r(qty - remaining))
    except Exception:
        # 2026-08-07 — DULU rollback-nya `except Exception: pass` (bersarang).
        # Kalau pelepasan rollback gagal, stok tetap TER-RESERVE selamanya:
        # barang ada secara fisik tetapi tidak pernah bisa dipakai lagi, dan
        # tidak ada satu pun jejak yang menjelaskan kenapa. Sekarang setiap
        # kegagalan rollback dicatat lengkap dengan baris & jumlahnya supaya
        # bisa dibersihkan; error aslinya tetap dilempar ke pemanggil.
        for sid, amt in done:
            try:
                await _release_row(sid, amt, db=db)
            except Exception as re_err:  # noqa: BLE001
                logger.error(
                    "[stok] ROLLBACK reservasi GAGAL — stok akan tetap ter-reserve dan "
                    "tidak bisa dipakai. material=%s baris_stok=%s qty=%s: %s",
                    material_id, sid, amt, re_err)
        raise
    return {"material_id": material_id, "reserved": qty, "rows": done}


async def _release_row(stock_id, qty, *, db=None):
    """Lepas reservasi pada baris spesifik (floor 0). Internal helper (rollback/release material)."""
    db = _db(db)
    qty = _r(qty)
    set_stage = {
        "reserved_quantity": {"$round": [{"$max": [0, {"$subtract": [_reserved_expr(), qty]}]}, 4]},
        "qty": _qty_expr(),
        "updated_at": _now(),
    }
    await db[STOCK].update_one({"id": stock_id}, [{"$set": set_stage}, _recompute_stage()])


async def release_material(material_id, qty, *, ref=None, actor=None, db=None):
    """Lepas reservasi level-material lintas baris (greedy by reserved desc). Floor di 0."""
    db = _db(db)
    qty = _r(qty)
    if qty <= 0:
        raise ValueError("qty harus > 0")
    rows = await list_rows(material_id, db=db)
    rows.sort(key=lambda r: read_reserved(r), reverse=True)
    remaining = qty
    released = 0.0
    for r in rows:
        if remaining <= 0:
            break
        rsv = read_reserved(r)
        if rsv <= 0:
            continue
        take = _r(min(rsv, remaining))
        await _release_row(r["id"], take, db=db)
        released = _r(released + take)
        remaining = _r(remaining - take)
    await _log(db, op="release_material", material_id=material_id, location_id=None,
               delta=-released, qty_after=await get_onhand(material_id, db=db),
               ref=ref, actor=actor, extra={"requested": qty, "released": released})
    return {"material_id": material_id, "released": released}


async def adjust_material(material_id, delta, *, ref=None, actor=None, db=None):
    """Rekonsiliasi stok kanonik level-material sebesar DELTA (dipakai Opname), tanpa perlu location_id.
    delta>0 → tambahkan ke baris utama (qty terbanyak) / baris default bila belum ada.
    delta<0 → kurangi on-hand greedy lintas baris (floor 0, reserved TETAP dijaga).
    Return {applied: delta_yang_benar2_diterapkan}."""
    db = _db(db)
    delta = _r(delta)
    if delta == 0:
        return {"material_id": material_id, "applied": 0.0}
    rows = await list_rows(material_id, db=db)
    if delta > 0:
        if rows:
            primary = max(rows, key=lambda r: read_qty(r))
            await adjust(material_id, primary.get("location_id"),
                         _r(read_qty(primary) + delta), ref=ref, actor=actor, db=db)
        else:
            await add(material_id, None, delta, ref=ref, actor=actor, db=db)
        return {"material_id": material_id, "applied": delta}
    # delta < 0 → kurangi greedy
    need = _r(-delta)
    rows.sort(key=lambda r: read_qty(r), reverse=True)
    applied = 0.0
    for r in rows:
        if need <= 0:
            break
        cur = read_qty(r)
        if cur <= 0:
            continue
        take = _r(min(cur, need))
        await adjust(material_id, r.get("location_id"), _r(cur - take), ref=ref, actor=actor, db=db)
        applied = _r(applied + take)
        need = _r(need - take)
    return {"material_id": material_id, "applied": _r(-applied)}


# ─────────────────────────────────────────────────────────────────────────────
# TRANSFER
# ─────────────────────────────────────────────────────────────────────────────
async def move(material_id, from_location, to_location, qty, *, meta=None,
               ref=None, actor=None, db=None, input_uom=None):
    """Pindah stok antar lokasi (issue dari asal → add ke tujuan)."""
    db = _db(db)
    if from_location == to_location:
        raise ValueError("lokasi asal & tujuan tidak boleh sama")
    # konversi SEKALI di sini supaya kedua sisi memakai angka yang identik
    qty, _ = await _conv(db, material_id, qty, input_uom)
    await issue(material_id, from_location, qty,
                ref={**(ref or {}), "move_to": to_location}, actor=actor, db=db)
    row = await add(material_id, to_location, qty, meta=meta,
                    ref={**(ref or {}), "move_from": from_location}, actor=actor, db=db)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# ADJUSTMENT (opname)
# ─────────────────────────────────────────────────────────────────────────────
async def adjust(material_id, location_id, counted_qty, *, meta=None, ref=None,
                 actor=None, db=None, input_uom=None):
    """Set stok fisik ke hasil hitung fisik (opname). Reservasi dipertahankan.

    `input_uom` opsional — penting untuk opname yang dihitung per kemasan
    (mis. petugas menghitung "3 pak", bukan "432 pcs").
    """
    db = _db(db)
    counted_qty, _trace = await _conv(db, material_id, counted_qty, input_uom)
    if counted_qty < 0:
        raise ValueError("counted_qty tidak boleh negatif")
    key = {"material_id": material_id, "location_id": location_id}
    before = await _row(db, material_id, location_id)
    qty_before = read_qty(before)
    set_stage = {
        "material_id": material_id,
        "location_id": location_id,
        "qty": counted_qty,
        "reserved_quantity": _reserved_expr(),
        "id": {"$ifNull": ["$id", _uid()]},
        "created_at": {"$ifNull": ["$created_at", _now()]},
        "updated_at": _now(),
    }
    set_stage.update(_meta_set(meta))
    await db[STOCK].update_one(key, [{"$set": set_stage}, _recompute_stage()], upsert=True)
    row = await _row(db, material_id, location_id)
    await _log(db, op="adjust", material_id=material_id, location_id=location_id,
               delta=_r(counted_qty - qty_before), qty_after=read_qty(row),
               ref=ref, actor=actor, meta=meta,
               extra={"qty_before": qty_before, "counted_qty": counted_qty, **_trace})
    return row


# ─────────────────────────────────────────────────────────────────────────────
# READ (agregasi lintas-lokasi & lintas-skema)
# ─────────────────────────────────────────────────────────────────────────────
async def list_rows(material_id, *, db=None):
    db = _db(db)
    return await db[STOCK].find({"material_id": material_id}, {"_id": 0}).to_list(1000)


async def get_onhand(material_id, *, db=None):
    rows = await list_rows(material_id, db=db)
    return _r(sum(read_qty(r) for r in rows))


async def get_available(material_id, *, db=None):
    rows = await list_rows(material_id, db=db)
    return _r(sum(read_available(r) for r in rows))


async def onhand_map(material_ids=None, *, db=None):
    """Agregasi on-hand per material lintas SEMUA baris/skema (flat & nested, semua lokasi).
    Menghilangkan blind-spot reader keyed location_id (BUG-INV-12). Return {material_id: qty}."""
    db = _db(db)
    q = {}
    if material_ids is not None:
        ids = [m for m in material_ids if m]
        if not ids:
            return {}
        q = {"material_id": {"$in": ids}}
    rows = await db[STOCK].find(q, {"_id": 0}).to_list(20000)
    out: dict = {}
    for r in rows:
        mid = r.get("material_id")
        if not mid:
            continue
        out[mid] = _r(out.get(mid, 0.0) + read_qty(r))
    return out


async def available_map(material_ids=None, *, db=None):
    """Seperti onhand_map tapi available (qty - reserved). Return {material_id: available}."""
    db = _db(db)
    q = {}
    if material_ids is not None:
        ids = [m for m in material_ids if m]
        if not ids:
            return {}
        q = {"material_id": {"$in": ids}}
    rows = await db[STOCK].find(q, {"_id": 0}).to_list(20000)
    out: dict = {}
    for r in rows:
        mid = r.get("material_id")
        if not mid:
            continue
        out[mid] = _r(out.get(mid, 0.0) + read_available(r))
    return out
