"""core.cut_panel_health — PENJAGA & PEMBERSIH "POTONGAN YATIM" (SESI #32).

APA ITU POTONGAN YATIM
----------------------
Master material POTONGAN (`rahaza_materials.is_cut_panel = True`) dibuat OTOMATIS
oleh Portal Cutting saat sebuah order dimulai. Ia menjadi **yatim** ketika
induknya tidak ada lagi:

  · `order_missing`  — tidak ada satu pun order cutting yang menunjuk master ini
                       (`cutting_orders.output_material_id`), dan order pembuatnya
                       (`cutting_order_id`) juga sudah tidak ada;
  · `source_missing` — kain asalnya (`source_material_id`) sudah tidak ada di
                       master material;
  · `source_inactive`— kain asalnya masih ada tetapi sudah dinonaktifkan.

KENAPA MODUL INI LAHIR (bukti hidup, bukan dugaan)
--------------------------------------------------
Pemilik menemukan master `CUT-JEPIT-JEDAI-NAVY-L` yang menunjuk kain
`VFH6B-KAIN-174456` — kain itu tidak ada, order `CUT-2026-0018` tidak ada, dan
`rahaza_material_issues` tidak punya satu pun baris `source='cutting'`.
Penyebabnya DUA, dan dua-duanya nyata:

  1. **Alat ukur sendiri.** Gate INV-F24 (`verify_fase_h6b_cutting_issue.py`)
     membersihkan order + kain + dokumen + stok + kartu stok, tetapi menghapus
     master potongan dengan **regex kode** `^(VFH6B-|CUT-GATE-F24)`. Sejak sesi
     #30 kode potongan diturunkan dari NAMA MODEL di master (`CUT-JEPIT-JEDAI-…`)
     ⇒ regex itu tidak pernah cocok ⇒ satu master sampah menumpuk **setiap kali
     gate dijalankan**. (Pelajaran sesi #17 terulang: menambah dokumen turunan
     mewajibkan SEMUA alat uji alur itu ikut membersihkannya.)
  2. **Alur produk.** `start` melahirkan master potongan; `cancel` (sah selama
     belum ada progres) dulu meninggalkannya tanpa induk selamanya.

ATURAN AMAN PEMBERSIHAN (yang dijaga modul ini)
-----------------------------------------------
Master potongan hanya boleh DIHAPUS bila ia benar-benar **tidak pernah dipakai**:
stok on-hand 0 · tidak ada baris buku besar stok · tidak ada kartu stok · tidak
dirujuk BOM/pengeluaran material/permintaan · dan ia memang lahir dari cutting.
Kalau salah satu tidak terpenuhi, master DIPERTAHANKAN dan alasannya
(`block_reason`) dikatakan — menghapus master yang masih berstok akan membuat
stok jadi hantu (ada barisnya, masternya tidak ada), persis cacat yang sedang
diperbaiki.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from core import stock_service

_log = logging.getLogger(__name__)

REASON_LABEL = {
    "order_missing": "order cutting pembuatnya sudah tidak ada",
    "source_missing": "kain asalnya sudah tidak ada di master material",
    "source_inactive": "kain asalnya sudah dinonaktifkan",
    "source_unknown": "tidak menyimpan kain asal (data lama)",
}

# Koleksi yang boleh "menahan" penghapusan karena masih merujuk master potongan.
# Bentuk: (nama koleksi, field yang menyimpan material_id, label untuk layar)
REFERENCE_CHECKS = (
    ("rahaza_boms", "materials.material_id", "BOM produksi"),
    ("rahaza_material_issues", "items.material_id", "dokumen pengeluaran material"),
    ("rahaza_material_requests", "items.material_id", "permintaan material"),
    ("rahaza_stock_opname_lines", "material_id", "opname stok"),
    ("rahaza_purchase_orders", "items.material_id", "purchase order"),
    ("warehouse_receiving", "items.material_id", "penerimaan barang"),
)


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _now():
    return datetime.now(timezone.utc)


async def _references(db, panel_id: str) -> dict:
    out: dict = {}
    for coll, field, label in REFERENCE_CHECKS:
        try:
            n = await db[coll].count_documents({field: panel_id}, limit=1)
        except Exception:  # noqa: BLE001 — koleksi boleh belum ada di DB ini
            n = 0
        if n:
            out[label] = n
    return out


async def inspect(db, panel: dict, *, onhand: float | None = None) -> dict:
    """Periksa SATU master potongan: yatim atau tidak, dan boleh dibersihkan atau tidak."""
    pid = panel.get("id")
    reasons: list[str] = []

    src_id = (panel.get("source_material_id") or "").strip()
    src = None
    if src_id:
        src = await db.rahaza_materials.find_one(
            {"id": src_id}, {"_id": 0, "id": 1, "code": 1, "name": 1, "active": 1})
        if not src:
            reasons.append("source_missing")
        elif src.get("active") is False:
            reasons.append("source_inactive")
    else:
        reasons.append("source_unknown")

    orders_ref = await db.cutting_orders.count_documents({"output_material_id": pid})
    order_id = (panel.get("cutting_order_id") or "").strip()
    maker = None
    if order_id:
        maker = await db.cutting_orders.find_one(
            {"id": order_id}, {"_id": 0, "id": 1, "number": 1, "status": 1})
    if orders_ref == 0 and not maker:
        reasons.append("order_missing")

    qty = _f(onhand if onhand is not None else await stock_service.get_onhand(pid, db=db))
    ledger = await db.rahaza_stock_ledger.count_documents({"material_id": pid})
    cards = await db.rahaza_material_movements.count_documents({"material_id": pid})
    refs = await _references(db, pid)

    # "source_unknown" saja BUKAN yatim (data lama yang masih dipakai order aktif).
    orphan = bool([r for r in reasons if r != "source_unknown"])

    blocks: list[str] = []
    if qty > 0:
        blocks.append(f"masih ada stok {qty:g} {panel.get('unit') or 'pcs'} di gudang")
    if ledger:
        blocks.append(f"{ledger} baris buku besar stok")
    if cards:
        blocks.append(f"{cards} baris kartu stok")
    for label, n in refs.items():
        blocks.append(f"dipakai {n} {label}")
    if not panel.get("is_cut_panel"):
        blocks.append("bukan master potongan hasil cutting")

    return {
        "id": pid,
        "code": panel.get("code") or "",
        "name": panel.get("name") or "",
        "unit": panel.get("unit") or "pcs",
        "unit_cost": round(_f(panel.get("unit_cost") or panel.get("hpp")), 4),
        "value_status": panel.get("value_status") or ("valued" if _f(panel.get("unit_cost")) > 0
                                                     else "unvalued"),
        "stock_qty": round(qty, 4),
        "stock_value": round(qty * _f(panel.get("unit_cost") or panel.get("hpp")), 2),
        "ledger_rows": ledger,
        "card_rows": cards,
        "references": refs,
        "source_material_id": src_id,
        "source_material_code": panel.get("source_material_code") or (src or {}).get("code") or "",
        "cutting_order_id": order_id,
        "cutting_order_number": panel.get("cutting_order_number") or (maker or {}).get("number") or "",
        "orders_referencing": orders_ref,
        "orphan": orphan,
        "reasons": reasons,
        "reason_text": " · ".join(REASON_LABEL.get(r, r) for r in reasons),
        "cleanable": bool(orphan and not blocks),
        "block_reason": ("Tidak dihapus karena " + "; ".join(blocks) + ". Kosongkan/koreksi dulu "
                         "lewat Penyesuaian Stok di Gudang." if blocks else ""),
        "created_at": panel.get("created_at"),
        "notes": panel.get("notes") or "",
    }


async def scan(db, *, limit: int = 500, only_orphan: bool = True) -> dict:
    """Periksa SEMUA master potongan. Dipakai layar + gate INV-F37."""
    panels = await db.rahaza_materials.find(
        {"is_cut_panel": True}, {"_id": 0}).sort("code", 1).to_list(limit)
    ids = [p["id"] for p in panels]
    onhand = await stock_service.onhand_map(ids, db=db) if ids else {}
    items = []
    for p in panels:
        row = await inspect(db, p, onhand=_f(onhand.get(p["id"])))
        if row["orphan"] or not only_orphan:
            items.append(row)
    orphans = [r for r in items if r["orphan"]]
    return {
        "items": items,
        "panel_total": len(panels),
        "orphan_count": len(orphans),
        "cleanable_count": len([r for r in orphans if r["cleanable"]]),
        "blocked_count": len([r for r in orphans if not r["cleanable"]]),
        "unvalued_count": len([r for r in items if r["value_status"] == "unvalued"]),
        "checked_at": _now().isoformat(),
    }


async def cleanup(db, user: dict | None = None, *, ids: list[str] | None = None,
                  dry_run: bool = False) -> dict:
    """Hapus master potongan yatim yang TERBUKTI belum pernah dipakai.

    `ids=None` ⇒ semua yang layak. Idempoten: menjalankan dua kali menghasilkan
    `removed=0` pada panggilan kedua (tidak ada lagi yang layak).
    """
    q: dict = {"is_cut_panel": True}
    if ids:
        q["id"] = {"$in": list(ids)}
    panels = await db.rahaza_materials.find(q, {"_id": 0}).to_list(1000)
    removed, kept = [], []
    for p in panels:
        row = await inspect(db, p)
        if not row["cleanable"]:
            kept.append(row)
            continue
        if not dry_run:
            await db.rahaza_materials.delete_one({"id": p["id"]})
            _log.info("potongan yatim dibersihkan: %s (%s) oleh %s",
                      p.get("code"), row["reason_text"], (user or {}).get("name", "sistem"))
        removed.append(row)
    return {
        "removed": len(removed),
        "kept": len(kept),
        "removed_items": removed,
        "kept_items": kept,
        "dry_run": bool(dry_run),
    }


async def remove_if_unused(db, *, panel_id: str, order_id: str,
                           user: dict | None = None) -> dict | None:
    """Penjaga alur: buang master potongan yang dibuat order ini bila belum terpakai.

    Dipanggil saat order cutting DIBATALKAN / DIHAPUS. Dulu `start` melahirkan
    master potongan lalu `cancel` meninggalkannya sebagai sampah permanen di
    Master Item milik pemilik.
    """
    if not panel_id:
        return None
    panel = await db.rahaza_materials.find_one({"id": panel_id}, {"_id": 0})
    if not panel or not panel.get("is_cut_panel"):
        return None
    # hanya master yang MEMANG dibuat order ini (bukti kepemilikan)
    if (panel.get("cutting_order_id") or "") not in ("", order_id):
        return None
    row = await inspect(db, panel)
    # order ini sendiri masih menunjuk master → jangan hitung sebagai penahan
    others = await db.cutting_orders.count_documents(
        {"output_material_id": panel_id, "id": {"$ne": order_id}})
    if others:
        return None
    if row["stock_qty"] > 0 or row["ledger_rows"] or row["card_rows"] or row["references"]:
        return {"removed": False, "code": row["code"], "reason": row["block_reason"]}
    await db.rahaza_materials.delete_one({"id": panel_id})
    _log.info("potongan %s dibuang bersama order %s (belum pernah bergerak)",
              row["code"], order_id)
    return {"removed": True, "code": row["code"], "reason": ""}
