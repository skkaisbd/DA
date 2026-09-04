#!/usr/bin/env python3
"""repair_selisih_ssot.py — PERBAIKAN DATA LAMA untuk SSOT SELISIH KIRIM.

Dibutuhkan karena sebelum 2026-08-01 sistem:
  1. menyimpan KLAIM vendor sebagai "dokumen resmi" (`qty_shipped_by_cmt`) walau
     yang benar-benar sampai lebih sedikit → selisih kirim tidak punya identitas;
  2. TIDAK PERNAH mengeluarkan stok FG saat barang dikirim ke buyer (GAP E) →
     nilai persediaan gudang FG menggelembung (kirim 100 pcs, stok tetap 100).

Yang dikerjakan (idempoten, aman dijalankan berulang):
  A. Baris penerimaan CMT yang SUDAH selesai QC:
     · `qty_claimed_by_cmt`  ← klaim vendor (di-backfill dari `qty_shipped_by_cmt`)
     · `qty_shipped_by_cmt`  ← qty yang BENAR-BENAR sampai (`qty_actual + reject_qty`)
     · dokumen selisih `SEL-CMT-xxxxx` dibuat untuk setiap gap yang belum punya
       dokumen (status `open` = masih kewajiban vendor, TANPA batas waktu).
  B. Dispatch ke buyer yang belum punya mutasi stok keluar → dikeluarkan lewat
     SSOT stok (`core/stock_service`) + `rahaza_fg_movements` OUT. Bila stok tidak
     cukup (data lama tidak konsisten) hanya dilaporkan, TIDAK dipaksa minus.
  C. Buku kuantitas job item dihitung ulang dari dokumen sumber.

Pakai:
    python3 scripts/repair_selisih_ssot.py --dry-run     # hanya laporan
    python3 scripts/repair_selisih_ssot.py --apply       # perbaiki
    python3 scripts/repair_selisih_ssot.py --apply --topup-fg
        # KHUSUS DATA DEMO: bila stok FG tidak cukup untuk dispatch lama (seeder
        # demo membuat dokumen dispatch tanpa pernah mencatat hasil produksi ke
        # stok FG), stok FG ditambahkan dulu lalu mutasi keluar dijalankan.
        # JANGAN dipakai pada data nyata owner — di sana kekurangan stok berarti
        # ada dokumen/QC yang belum diselesaikan dan harus diperiksa manusia.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, "/app/backend")
from gr_common import load_env  # noqa: E402

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"


def _i(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


async def run(apply: bool, topup: bool = False) -> int:  # noqa: C901
    import os
    from motor.motor_asyncio import AsyncIOMotorClient
    from core.cmt_receipt_status import is_done
    from core import production_qty_ledger as qled
    from core import short_shipment as shortmod

    load_env()
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    actor = {"id": "system-repair", "name": "Perbaikan Data (repair_selisih_ssot)"}
    mode = f"{G}APPLY{X}" if apply else f"{Y}DRY-RUN{X}"
    print(f"{B}{C}PERBAIKAN SSOT SELISIH KIRIM{X} — mode {mode}\n")

    # ── A. Baris penerimaan CMT: klaim vs kenyataan + dokumen selisih ─────────
    print(f"{B}A. Penerimaan CMT (dokumen = kenyataan){X}")
    receipts = await db.cmt_receipts.find({}, {"_id": 0}).to_list(None)
    done = {r["id"]: r for r in receipts if is_done(r.get("status"))}
    lines = await db.cmt_receipt_lines.find(
        {"receipt_id": {"$in": list(done.keys())}}, {"_id": 0}).to_list(None) if done else []
    fixed_lines = shorts_created = 0
    for ln in lines:
        arrived = _i(ln.get("qty_actual")) + _i(ln.get("reject_qty"))
        claimed = _i(ln.get("qty_claimed_by_cmt")) or _i(ln.get("qty_shipped_by_cmt")) or arrived
        need_line_fix = (_i(ln.get("qty_claimed_by_cmt")) != claimed
                         or _i(ln.get("qty_shipped_by_cmt")) != arrived)
        gap = max(0, claimed - arrived)
        existing = await db.cmt_short_shipments.find_one(
            {"receipt_line_id": ln["id"]}, {"_id": 0, "id": 1})
        if not need_line_fix and (gap == 0 or existing):
            continue
        rec = done[ln["receipt_id"]]
        print(f"  {Y}{rec.get('receipt_code')}{X} {ln.get('sku_code') or ln['id'][:8]}: "
              f"klaim {claimed} · sampai {arrived} · selisih {gap}"
              + ("" if existing else (" → buat dokumen selisih" if gap else "")))
        if not apply:
            fixed_lines += 1 if need_line_fix else 0
            shorts_created += 1 if (gap and not existing) else 0
            continue
        if need_line_fix:
            await db.cmt_receipt_lines.update_one({"id": ln["id"]}, {"$set": {
                "qty_claimed_by_cmt": claimed, "qty_shipped_by_cmt": arrived,
                "qty_short": gap, "short_status": "open" if gap else "",
                "qty_short_resolved": _i(ln.get("qty_short_resolved"))}})
            fixed_lines += 1
        if gap and not existing:
            ji = await qled.resolve_job_item_for_line(db, ln)
            await shortmod.record_cmt_short(
                db, receipt=rec, line={**ln, "qty_claimed_by_cmt": claimed},
                claimed=claimed, arrived=arrived, job_item=ji, actor=actor,
                reason="Backfill data lama: selisih kirim belum pernah didokumentasikan")
            shorts_created += 1
    print(f"  baris dikoreksi={fixed_lines} · dokumen selisih dibuat={shorts_created}\n")

    # ── B. Stok FG keluar untuk dispatch buyer lama ───────────────────────────
    print(f"{B}B. Stok FG keluar untuk dispatch ke buyer (GAP E){X}")
    da_ids = set(await db.buyer_shipments.distinct("id", {"receiver_type": "da"}))
    ships = {s["id"]: s for s in await db.buyer_shipments.find(
        {"id": {"$nin": list(da_ids)}}, {"_id": 0}).to_list(None)}
    items = await db.buyer_shipment_items.find(
        {"shipment_id": {"$in": list(ships.keys())}}, {"_id": 0}).to_list(None) if ships else []
    issued = skipped = shortfall = topped = 0
    for it in items:
        if it.get("fg_issued_at"):
            continue
        qty = _i(it.get("qty_shipped"))
        if qty <= 0:
            continue
        sku = (it.get("sku") or "").strip()
        mat = await qled.resolve_fg_material(db, sku=sku) if sku else None
        if not mat:
            skipped += 1
            continue
        sh = ships.get(it["shipment_id"], {})
        if not apply:
            print(f"  {Y}{sh.get('shipment_number')}{X} {sku}: perlu keluar {qty} pcs")
            issued += qty
            continue
        try:
            res = await qled.issue_fg(
                db, material_id=mat["id"], qty=qty, sku=sku,
                ref={"source": "repair_fg_stock_backfill", "shipment_id": sh.get("id"),
                     "shipment_number": sh.get("shipment_number"),
                     "shipment_item_id": it.get("id"), "dispatch_seq": it.get("dispatch_seq")},
                actor=actor)
        except qled.FGStockShortfall as e:
            # `--topup-fg` (khusus DATA DEMO): seeder demo lama membuat dokumen
            # dispatch LANGSUNG di DB tanpa pernah menambah stok FG hasil produksi,
            # sehingga INV-18 merah di container baru. Dengan flag ini stok FG
            # hasil produksi ditambahkan dulu (jejaknya ditandai backfill), lalu
            # mutasi keluar dijalankan seperti alur nyata. TANPA flag, perilaku
            # lama dipertahankan: dilaporkan, tidak menyentuh stok.
            if not topup:
                print(f"  {R}{sh.get('shipment_number')} {sku}: {e}{X}")
                shortfall += 1
                continue
            from core import stock_service as _ss
            missing = max(0, int(qty) - int(e.have))
            fg_loc = await qled.resolve_fg_location_id(db)
            await _ss.add(mat["id"], fg_loc, missing, db=db,
                          meta={"material_code": mat.get("code"), "material_name": mat.get("name"),
                                "material_type": "fg", "ownership": "cv_da",
                                "inventory_category": "fg_internal", "unit": "pcs"},
                          ref={"source": "repair_fg_topup_demo", "sku": sku,
                               "shipment_number": sh.get("shipment_number")},
                          actor=actor)
            print(f"  {Y}{sh.get('shipment_number')}{X} {sku}: stok FG ditambah {missing} pcs "
                  f"(hasil produksi yang belum tercatat — data demo)")
            res = await qled.issue_fg(
                db, material_id=mat["id"], qty=qty, sku=sku,
                ref={"source": "repair_fg_stock_backfill", "shipment_id": sh.get("id"),
                     "shipment_number": sh.get("shipment_number"),
                     "shipment_item_id": it.get("id"), "dispatch_seq": it.get("dispatch_seq")},
                actor=actor)
            topped += missing
        await db.buyer_shipment_items.update_one({"id": it["id"]}, {"$set": {
            "fg_issued_at": qled._now().isoformat(), "fg_issued_qty": qty,
            "fg_material_id": mat["id"], "fg_issued_backfill": True}})
        await db.rahaza_fg_movements.insert_one({
            "id": __import__("uuid").uuid4().hex, "sku_code": sku, "movement_type": "OUT",
            "qty": qty, "source": "buyer_shipment", "ref_id": sh.get("id"),
            "ref_number": sh.get("shipment_number"), "material_id": mat["id"],
            "dispatch_seq": it.get("dispatch_seq"), "shipment_item_id": it.get("id"),
            "location_id": (res.get("issued") or [{}])[0].get("location_id", ""),
            "notes": "Backfill mutasi keluar (perbaikan data lama GAP E)",
            "created_by": actor["name"], "created_at": qled._now().isoformat()})
        issued += qty
        print(f"  {G}{sh.get('shipment_number')}{X} {sku}: keluar {qty} pcs")
    print(f"  qty dikeluarkan={issued} · SKU tanpa master FG (dilewati)={skipped} "
          f"· stok tidak cukup={shortfall}" + (f" · stok FG ditambah (demo)={topped}" if topped else "") + "\n")

    # ── C. Rekalkulasi buku kuantitas ────────────────────────────────────────
    print(f"{B}C. Rekalkulasi buku kuantitas job item{X}")
    poi_ids = await db.production_job_items.distinct("po_item_id", {"po_item_id": {"$nin": [None, ""]}})
    resynced = 0
    for poi in poi_ids:
        target = await qled.recompute_group_target(db, poi)
        jis = await db.production_job_items.find({"po_item_id": poi}, {"_id": 0}).to_list(None)
        cur = {f: sum(_i(j.get(f)) for j in jis) for f in target}
        if cur == target:
            continue
        diff = {k: f"{cur[k]}→{target[k]}" for k in target if cur[k] != target[k]}
        print(f"  {Y}{poi[:12]}{X} {diff}")
        if apply:
            await qled.resync_from_documents(db, po_item_id=poi)
        resynced += 1
    print(f"  po_item perlu/selesai disinkronkan={resynced}")

    print(f"\n{B}{'-' * 70}{X}")
    if apply:
        print(f"{G}{B}SELESAI — data lama disesuaikan dengan SSOT selisih kirim.{X}")
    else:
        print(f"{Y}{B}DRY-RUN — tidak ada perubahan. Jalankan dengan --apply untuk memperbaiki.{X}")
    return 0


def main() -> int:
    apply = "--apply" in sys.argv
    topup = "--topup-fg" in sys.argv
    return asyncio.run(run(apply, topup))


if __name__ == "__main__":
    sys.exit(main())
