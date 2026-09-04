"""A5 — SSOT skema stok `rahaza_material_stock`.

Latar belakang (split-brain historis): satu koleksi ditulis oleh 3 kelompok
writer dengan skema berbeda:
  - Skema A (kanonik, mayoritas ERP): {material_id, location_id, qty}
  - Skema B (domain Aksesoris)      : {material_id, location:{id,code}, total_qty}
  - Skema C (alur Barang Jadi/FG)   : {material_id, quantity, available_quantity,
                                       reserved_quantity}

Keputusan unifikasi (disetujui user):
  * KANONIK = `qty` + `location_id` (datar). `qty` = jumlah fisik on-hand.
  * `total_qty`, `quantity` dipertahankan sebagai ALIAS jumlah fisik (selalu
    di-mirror sama dengan `qty`), agar reader lama tetap jalan.
  * `available_quantity` = qty - reserved_quantity (semantik reservasi FG).
  * `reserved_quantity` (alias lama: `reserved`) = jumlah ter-reserve.

ATURAN:
  - Semua WRITER wajib menjaga `qty` (pakai inc_all_qty / set_all_qty).
  - Semua READER jumlah fisik pakai read_qty() (rantai fallback lintas-skema).
"""
from __future__ import annotations

_QTY_KEYS = ("qty", "total_qty", "quantity", "available_quantity")
_AVAIL_KEYS = ("available_quantity", "qty", "total_qty", "quantity")
_RESERVED_KEYS = ("reserved_quantity", "reserved")


def _as_float(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def read_qty(doc) -> float:
    """Baca jumlah fisik on-hand kanonik dengan fallback lintas-skema."""
    if not doc:
        return 0.0
    for k in _QTY_KEYS:
        if doc.get(k) is not None:
            return _as_float(doc.get(k))
    return 0.0


def read_available(doc) -> float:
    """Baca jumlah tersedia (belum ter-reserve)."""
    if not doc:
        return 0.0
    for k in _AVAIL_KEYS:
        if doc.get(k) is not None:
            return _as_float(doc.get(k))
    return 0.0


def read_reserved(doc) -> float:
    """Baca jumlah ter-reserve."""
    if not doc:
        return 0.0
    for k in _RESERVED_KEYS:
        if doc.get(k) is not None:
            return _as_float(doc.get(k))
    return 0.0


def inc_all_qty(delta: float) -> dict:
    """Fragment $inc yang menjaga semua alias jumlah fisik tetap sinkron."""
    d = float(delta)
    return {"qty": d, "total_qty": d, "quantity": d}


def set_all_qty(value: float) -> dict:
    """Fragment $set yang menetapkan semua alias jumlah fisik ke satu nilai."""
    v = float(value)
    return {"qty": v, "total_qty": v, "quantity": v}
