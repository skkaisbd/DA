#!/usr/bin/env python3
"""cleanup_uji_h5_h6.py — sapu data UJI Fase H-5/H-6 dari basis data.

KENAPA ADA: pembuktian H-5/H-6 (POC + agen uji + gate) membuat data nyata lewat API
sungguhan — material kain uji, penerimaan barang, gulungan, dan order cutting. Data itu
SENGAJA tidak dihapus otomatis supaya pemilik bisa memeriksanya sendiri di layar. Skrip
ini menyapunya kalau sudah tidak diperlukan.

YANG DISAPU (hanya yang berawalan kode uji — data nyata TIDAK disentuh):
  · `rahaza_materials` berkode POC-* / TEST-H5* / TEST-H6* / VFH5-* (+ potongan hasil
    cutting yang lahir darinya, lewat `source_material_id`)
  · stok + ledger + movement material tersebut (`rahaza_material_stock`,
    `rahaza_stock_ledger`, `rahaza_material_movements`)
  · gulungan + movement gulungan (`wh_fabric_rolls`, `wh_fabric_roll_movements`)
  · order + progres cutting yang memakai material tersebut
  · penerimaan barang (`warehouse_receiving`) yang HANYA berisi baris material uji

YANG TIDAK DISENTUH:
  · counter nomor (`counters`) — nomor gulungan/GR yang pernah dipakai tidak boleh
    dipakai lagi oleh dokumen lain, jadi urutannya dibiarkan maju.
  · penerimaan yang mencampur material uji DAN material nyata (dilaporkan, tidak dihapus).

Pakai:
    python3 scripts/cleanup_uji_h5_h6.py            # LAPORAN saja (tidak menghapus)
    python3 scripts/cleanup_uji_h5_h6.py --apply    # benar-benar menghapus
    python3 scripts/cleanup_uji_h5_h6.py --prefix TEST-H5,TEST-H6,VFH5 --apply
                                                    # hanya awalan tertentu (mis. sisakan skenario POC-*)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(ROOT / "backend"))
from gr_common import db_handle  # noqa: E402

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

DEFAULT_PREFIXES = ["POC-", "TEST-H5", "TEST-H6", "VFH5-"]


def prefixes_from_args() -> list[str]:
    for i, a in enumerate(sys.argv):
        if a == "--prefix" and i + 1 < len(sys.argv):
            return [p.strip() for p in sys.argv[i + 1].split(",") if p.strip()]
        if a.startswith("--prefix="):
            return [p.strip() for p in a.split("=", 1)[1].split(",") if p.strip()]
    return DEFAULT_PREFIXES


def main() -> int:
    apply = "--apply" in sys.argv
    prefixes = prefixes_from_args()
    code_rx = "^(" + "|".join(p.replace("-", r"\-") for p in prefixes) + ")"
    db = db_handle()
    mats = list(db.rahaza_materials.find({"code": {"$regex": code_rx}},
                                         {"_id": 0, "id": 1, "code": 1, "name": 1}))
    ids = [m["id"] for m in mats]
    panels = list(db.rahaza_materials.find({"source_material_id": {"$in": ids}},
                                           {"_id": 0, "id": 1, "code": 1}))
    pids = [p["id"] for p in panels]
    all_ids = ids + pids

    rolls = list(db.wh_fabric_rolls.find({"material_id": {"$in": all_ids}}, {"_id": 0, "id": 1}))
    rids = [r["id"] for r in rolls]
    orders = list(db.cutting_orders.find({"input_material_id": {"$in": all_ids}},
                                         {"_id": 0, "id": 1, "number": 1}))
    oids = [o["id"] for o in orders]

    grs_pure, grs_mixed = [], []
    for gr in db.warehouse_receiving.find({}, {"_id": 0, "id": 1, "receipt_number": 1, "items": 1}):
        items = gr.get("items") or []
        mids = {it.get("material_id") for it in items if it.get("material_id")}
        if not mids:
            continue
        if mids <= set(all_ids):
            grs_pure.append(gr)
        elif mids & set(all_ids):
            grs_mixed.append(gr)

    counts = {
        "rahaza_materials (kain/aksesoris uji)": len(mats),
        "rahaza_materials (potongan hasil cutting uji)": len(panels),
        "wh_fabric_rolls": len(rids),
        "wh_fabric_roll_movements": (db.wh_fabric_roll_movements.count_documents(
            {"roll_id": {"$in": rids}}) if rids else 0),
        "cutting_orders": len(oids),
        "cutting_progress": (db.cutting_progress.count_documents(
            {"cutting_order_id": {"$in": oids}}) if oids else 0),
        # FASE H-6b (2026-08-17) — progres cutting menerbitkan dokumen "Pengeluaran
        # Material" (`ref_type=cutting_issue`). Kalau tidak ikut disapu, dokumennya
        # tertinggal YATIM (menunjuk order cutting yang sudah dihapus) dan menumpuk
        # di layar Gudang. Dijaga oleh INV-F24 C14.
        "rahaza_material_issues (dokumen cutting uji)": (
            db.rahaza_material_issues.count_documents(
                {"cutting_order_id": {"$in": oids}}) if oids else 0),
        "rahaza_material_stock": (db.rahaza_material_stock.count_documents(
            {"material_id": {"$in": all_ids}}) if all_ids else 0),
        "rahaza_stock_ledger": (db.rahaza_stock_ledger.count_documents(
            {"material_id": {"$in": all_ids}}) if all_ids else 0),
        "rahaza_material_movements": (db.rahaza_material_movements.count_documents(
            {"material_id": {"$in": all_ids}}) if all_ids else 0),
        "warehouse_receiving (murni data uji)": len(grs_pure),
    }

    # ── FASE H-6b (2026-08-17) — DOKUMEN ARUS KELUAR CUTTING YANG YATIM ───────
    # Kebocoran NYATA: gate INV-F22 (dan alat uji lain yang dibuat SEBELUM H-6b)
    # menghapus order+progres cutting tanpa tahu bahwa progres kini MENERBITKAN
    # dokumen "Pengeluaran Material". Dokumen itu tertinggal menunjuk order yang
    # sudah tidak ada dan menumpuk di layar Gudang. Karena materialnya pun sudah
    # ikut terhapus, dokumen yatim TIDAK bisa ditemukan lewat awalan kode — jadi
    # disapu berdasarkan BUKTI ke-yatiman, bukan berdasarkan nama.
    # Invarian yang menjaganya: INV-F24 C14.
    live_orders = {o["id"] for o in db.cutting_orders.find({}, {"_id": 0, "id": 1})}
    live_progress = {p["id"] for p in db.cutting_progress.find({}, {"_id": 0, "id": 1})}
    orphan_mi = [m for m in db.rahaza_material_issues.find(
        {"ref_type": "cutting_issue"}, {"_id": 0, "id": 1, "mi_number": 1,
                                        "cutting_order_id": 1, "cutting_progress_id": 1})
        if m.get("cutting_order_id") not in live_orders
        or m.get("cutting_progress_id") not in live_progress]
    counts["rahaza_material_issues (dokumen cutting YATIM)"] = len(orphan_mi)

    print(f"{C}{B}Sapu data uji Fase H-5/H-6 — {'MENGHAPUS' if apply else 'LAPORAN saja'}"
          f" · awalan: {', '.join(prefixes)}{X}")
    for k, v in counts.items():
        print(f"  {k:48s} {v:6d}")
    if grs_mixed:
        print(f"{Y}  ! {len(grs_mixed)} penerimaan mencampur material uji & nyata — DIBIARKAN: "
              f"{', '.join(g.get('receipt_number', '?') for g in grs_mixed[:6])}{X}")
    if not apply:
        print(f"\n{Y}  Tidak ada yang dihapus. Jalankan ulang dengan --apply bila sudah yakin.{X}")
        return 0
    if rids:
        db.wh_fabric_roll_movements.delete_many({"roll_id": {"$in": rids}})
        db.wh_fabric_rolls.delete_many({"id": {"$in": rids}})
    if oids:
        mi_ids = [m["id"] for m in db.rahaza_material_issues.find(
            {"cutting_order_id": {"$in": oids}}, {"_id": 0, "id": 1})]
        if mi_ids:
            db.rahaza_material_movements.delete_many({"ref_id": {"$in": mi_ids}})
            db.rahaza_material_issues.delete_many({"id": {"$in": mi_ids}})
        db.cutting_progress.delete_many({"cutting_order_id": {"$in": oids}})
        db.cutting_orders.delete_many({"id": {"$in": oids}})
    if all_ids:
        for coll in ("rahaza_material_stock", "rahaza_stock_ledger", "rahaza_material_movements"):
            db[coll].delete_many({"material_id": {"$in": all_ids}})
        db.rahaza_materials.delete_many({"id": {"$in": all_ids}})
    if grs_pure:
        db.warehouse_receiving.delete_many({"id": {"$in": [g["id"] for g in grs_pure]}})
    if orphan_mi:
        oids_mi = [m["id"] for m in orphan_mi]
        db.rahaza_material_movements.delete_many({"ref_id": {"$in": oids_mi}})
        db.rahaza_material_issues.delete_many({"id": {"$in": oids_mi}})
        print(f"{Y}  · {len(oids_mi)} dokumen cutting YATIM dibuang: "
              f"{', '.join(m.get('mi_number', '?') for m in orphan_mi[:6])}{X}")
    print(f"\n{G}{B}  Selesai — data uji H-5/H-6 disapu. Nomor dokumen dibiarkan maju "
          f"(nomor bekas tidak dipakai ulang).{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
