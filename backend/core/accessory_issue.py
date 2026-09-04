"""core.accessory_issue — pengeluaran (issue) aksesoris KANONIK.

KENAPA ADA (FASE 10 / prasyarat drop `accessory_legacy`)
Logika "keluarkan stok aksesoris" selama ini HANYA hidup di dalam route
`POST /api/acc/stock/issue`. Akibatnya jalur permintaan internal SSOT
(`POST /api/dewi/accessory-requests/{id}/deliver`) tidak bisa memakainya —
dan itulah alasan endpoint SSOT belum bisa menggantikan endpoint legacy
`PUT /api/acc/internal-requests/{id}` (yang memotong stok). Selama endpoint
legacy masih jadi satu-satunya jalur yang memotong stok, koleksi
`acc_internal_requests` tidak akan pernah bisa di-drop.

Modul ini mengangkat logika itu menjadi FUNGSI yang bisa dipakai siapa saja:
  * `check_availability` — validasi SEMUA baris SEBELUM ada stok yang dipotong
    (mencegah pengeluaran separuh jalan saat satu item kurang).
  * `issue_accessory`    — potong stok + kartu stok bernilai + jurnal pemakaian
    + alarm "belum dinilai" (persis perilaku route lama, satu sumber kebenaran).

Catatan impor: helper pencatat kartu stok (`_log_movement`) ada di modul route.
Untuk menghindari impor siklik, modul itu diimpor MALAS (di dalam fungsi).
"""
from __future__ import annotations

import logging

from core import accessory_valuation
from core import uom as _uom          # SSOT konversi satuan (input_unit boleh kode satuan)
from core.accessory_stock import (
    add_stock as _add_stock,
    get_accessory_location_id as _get_accessory_location_id,
    stock_qty as _stock_qty,
)

_log = logging.getLogger(__name__)


class IssueError(ValueError):
    """Kesalahan yang layak ditampilkan ke user (bukan bug)."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


async def resolve_material(db, *, acc_id: str = "", code: str = "") -> dict | None:
    """Cari master aksesoris berdasarkan id, atau kode (fallback data lama)."""
    if acc_id:
        mat = await db.rahaza_materials.find_one(
            {"id": acc_id, "type": "accessory", "active": True})
        if mat:
            return mat
    if code:
        return await db.rahaza_materials.find_one(
            {"code": code, "type": "accessory", "active": True})
    return None


async def check_availability(db, items: list[dict]) -> list[dict]:
    """Validasi baris permintaan SEBELUM stok dipotong.

    `items`: [{material_id?, material_code?, qty, unit?, ...}]
    Return: daftar baris tervalidasi [{material, qty, unit}] — melempar `IssueError`
    dengan pesan yang bisa langsung dibaca user bila ada yang tidak lolos.
    """
    if not items:
        raise IssueError("Permintaan tidak punya baris item.")
    resolved: list[dict] = []
    problems: list[str] = []
    needed: dict[str, float] = {}
    for it in items:
        qty = float(it.get("qty") or it.get("qty_requested") or 0)
        mat = await resolve_material(
            db, acc_id=str(it.get("material_id") or it.get("acc_id") or ""),
            code=str(it.get("material_code") or it.get("acc_code") or ""))
        label = (it.get("material_code") or it.get("material_name")
                 or it.get("acc_name") or "(tanpa nama)")
        if not mat:
            problems.append(f"{label}: master aksesoris tidak ditemukan/nonaktif")
            continue
        if qty <= 0:
            problems.append(f"{mat.get('code') or label}: qty harus lebih dari 0")
            continue
        needed[mat["id"]] = needed.get(mat["id"], 0) + qty
        resolved.append({"material": mat, "qty": qty,
                         "unit": it.get("unit") or mat.get("unit", "pcs")})
    for mat_id, total in needed.items():
        onhand = await _stock_qty(db, mat_id)
        if onhand < total:
            mat = next(r["material"] for r in resolved if r["material"]["id"] == mat_id)
            problems.append(
                f"{mat.get('code') or mat.get('name')}: stok tidak cukup "
                f"(butuh {total:g}, tersedia {onhand:g})")
    if problems:
        raise IssueError("Tidak bisa mengeluarkan stok — " + "; ".join(problems))
    return resolved


async def issue_accessory(db, user: dict, *, acc_id: str, qty: float,
                          input_unit: str = "base", notes: str = "",
                          ref_type: str = "manual", ref_id: str = "") -> dict:
    """Keluarkan stok aksesoris (bernilai + berjurnal). Melempar `IssueError` bila tidak valid."""
    from routes.dewi_accessories_stock import _log_movement  # lazy: hindari impor siklik
    from routes.rahaza_posting import post_accessory_issue  # lazy: modul berat

    try:
        qty = float(qty)
    except (TypeError, ValueError):
        raise IssueError("qty harus angka")
    if not acc_id or qty <= 0:
        raise IssueError("acc_id dan qty > 0 wajib diisi")

    item = await db.rahaza_materials.find_one(
        {"id": acc_id, "type": "accessory", "active": True})
    if not item:
        raise IssueError("Aksesoris tidak ditemukan", status=404)

    pack_size = float(item.get("pack_size") or 1) or 1
    # 2026-08-05 — `input_unit` boleh: "base" | "pack" (legacy) | KODE SATUAN dari
    # SSOT UoM (mis. "box", "lusin", "gram"). Perilaku legacy tidak berubah.
    _u = str(input_unit or "base").strip().lower()
    if _u == "pack":
        qty_base = qty * pack_size
    elif _u in ("", "base"):
        qty_base = qty
    else:
        try:
            from core import bom_uom as _bom_uom   # cakupan lebar (kemasan + global)
            _f, _src = _bom_uom.factor_to_base(item, _u)
            qty_base = round(qty * _f, 4)
        except _uom.UomError as e:
            raise IssueError(str(e))

    current = await _stock_qty(db, acc_id)
    if current < qty_base:
        raise IssueError(f"Stok tidak cukup. Stok saat ini: {current:g}")

    loc_id = await _get_accessory_location_id(db)
    await _add_stock(db, acc_id, loc_id, -qty_base)

    unit_cost = accessory_valuation.resolve_unit_cost(item)
    mv = await _log_movement(
        db, user, material_id=acc_id, mv_type="issue", qty=-qty_base,
        related_type=ref_type, related_ref=ref_id, notes=notes, unit_cost=unit_cost,
    )
    je = {"posted": False,
          "error": "Harga satuan belum diisi — jurnal pemakaian tidak dibuat."}
    if unit_cost <= 0:
        await accessory_valuation.notify_unvalued(
            db, material=item, movement_type="issue", qty=qty_base, actor=user)
    elif mv:
        try:
            res = await post_accessory_issue(db, mv, user)
            je = {"posted": bool(res.get("ok")), "je_id": res.get("je_id"),
                  "je_number": res.get("je_number"), "error": res.get("error"),
                  "amount": res.get("amount")}
        except Exception as e:  # noqa: BLE001 — jurnal gagal tidak membatalkan stok
            _log.warning("[acc-issue] posting jurnal gagal: %s", e)
            je = {"posted": False, "error": str(e)}

    new_qty = await _stock_qty(db, acc_id)
    return {
        "ok": True,
        "material_id": acc_id,
        "material_code": item.get("code", ""),
        "material_name": item.get("name", ""),
        "new_qty": new_qty,
        "qty_issued": qty_base,
        "unit": item.get("unit", "pcs"),
        "unit_cost": round(unit_cost, 4),
        "value": round(qty_base * unit_cost, 2),
        "stock_value": round(new_qty * unit_cost, 2),
        "je": je,
    }
