#!/usr/bin/env python3
"""
backfill_produksi_field_contracts.py — FASE 1/3/6: rapikan kontrak field lintas dokumen.

Memperbaiki 3 cacat data yang dibuktikan audit 2026-07-31
(docs/AUDIT_PRODUKSI_MAKLON_CMT.md):

  FLD-1  `po_items` menyimpan `qty` sementara banyak pembaca (laporan/PDF/UI lama)
         membaca `qty_ordered` ⇒ kolom tampil kosong/0. → backfill `qty_ordered`.

  CONS-3 Dokumen `buyer_shipments` LAMA tidak punya field konsolidasi
         (`po_ids`, `consolidated`, `parent_shipment_id`, `child_shipment_ids`,
         `receiver_type`) sehingga pembacaan surat jalan gabungan / child tidak
         konsisten (skema campur pra/pasca Phase D). → backfill.

  LEDGER `production_job_items` lama belum punya buku kuantitas QC
         (`qty_accepted`, `qty_reject`, `qty_rework_open`, `qty_repaired`,
         `qty_scrap`, `qty_declared`). → set 0 supaya agregasi tidak None.

Idempoten. Pakai:
    python3 scripts/backfill_produksi_field_contracts.py --dry-run
    python3 scripts/backfill_produksi_field_contracts.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
G, Y, C, B, X = "\033[92m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"

LEDGER_FIELDS = ("qty_declared", "qty_accepted", "qty_reject",
                 "qty_rework_open", "qty_repaired", "qty_scrap")


def main():
    dry = "--dry-run" in sys.argv
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
    print(f"{B}{C}BACKFILL KONTRAK FIELD PRODUKSI{X}" + (f" {Y}(dry-run){X}" if dry else ""))

    # ── FLD-1 ───────────────────────────────────────────────────────────────
    n = db.po_items.count_documents({"qty_ordered": {"$exists": False}})
    print(f"  po_items tanpa qty_ordered : {n}")
    if n and not dry:
        for d in db.po_items.find({"qty_ordered": {"$exists": False}}, {"_id": 1, "qty": 1}):
            db.po_items.update_one({"_id": d["_id"]},
                                   {"$set": {"qty_ordered": int(d.get("qty") or 0)}})
        print(f"    {G}→ {n} diisi dari `qty`{X}")

    # ── CONS-3 ──────────────────────────────────────────────────────────────
    q = {"$or": [{"po_ids": {"$exists": False}}, {"consolidated": {"$exists": False}},
                 {"receiver_type": {"$exists": False}}]}
    rows = list(db.buyer_shipments.find(q, {"_id": 1, "id": 1, "po_id": 1, "vendor_id": 1,
                                            "receiver_type": 1, "po_ids": 1}))
    print(f"  buyer_shipments tanpa field konsolidasi : {len(rows)}")
    if rows and not dry:
        for d in rows:
            item_pos = db.buyer_shipment_items.distinct("po_id", {"shipment_id": d.get("id")})
            po_ids = sorted({p for p in ([d.get("po_id")] + list(item_pos)) if p})
            upd = {
                "po_ids": d.get("po_ids") or po_ids,
                "consolidated": len(po_ids) > 1,
                "parent_shipment_id": d.get("parent_shipment_id"),
                "child_shipment_ids": d.get("child_shipment_ids") or [],
                # Dokumen lama = surat jalan DA → buyer (receiver_type belum ada
                # sebelum Phase B). Vendor→DA selalu punya related_cmt_receipt_id.
                "receiver_type": d.get("receiver_type") or "buyer",
                "backfilled_consolidation_at": True,
            }
            db.buyer_shipments.update_one({"_id": d["_id"]}, {"$set": upd})
        print(f"    {G}→ {len(rows)} dokumen dilengkapi{X}")

    # ── LEDGER ──────────────────────────────────────────────────────────────
    q2 = {"$or": [{f: {"$exists": False}} for f in LEDGER_FIELDS]}
    n2 = db.production_job_items.count_documents(q2)
    print(f"  production_job_items tanpa buku kuantitas : {n2}")
    if n2 and not dry:
        db.production_job_items.update_many(q2, {"$set": {f: 0 for f in LEDGER_FIELDS}})
        print(f"    {G}→ {n2} diisi 0{X}")

    # ── MAT-3: kekurangan inspeksi HISTORIS belum punya tindak lanjut ──────────
    import uuid as _uuid
    from datetime import datetime, timezone
    _now = datetime.now(timezone.utc)
    pending = []
    for insp in db.vendor_material_inspections.find({}, {"_id": 0}):
        if insp.get("component_request_id"):
            continue
        miss = list(db.vendor_material_inspection_items.find(
            {"inspection_id": insp["id"], "missing_qty": {"$gt": 0}}, {"_id": 0}))
        if miss:
            pending.append((insp, miss))
    print(f"  inspeksi lama dengan kekurangan tanpa tindak lanjut : {len(pending)}")
    if pending and not dry:
        for insp, miss in pending:
            ship = db.vendor_shipments.find_one({"id": insp.get("shipment_id")}, {"_id": 0}) or {}
            po_id = ship.get("po_id") or ""
            po = db.production_pos.find_one({"id": po_id}, {"_id": 0}) if po_id else None
            code = f"REQ-KRG-BF-{str(_uuid.uuid4())[:6].upper()}"
            items = [{
                "component_type": m.get("product_name") or m.get("sku") or m.get("accessory_name") or "material",
                "size": m.get("size", ""), "color": m.get("color", ""),
                "qty": float(m.get("missing_qty") or 0), "unit": m.get("unit", "pcs"),
                "kind": "accessory" if m.get("item_type") == "accessory" else "material",
                "notes": m.get("condition_notes", ""),
            } for m in miss]
            doc = {
                "id": str(_uuid.uuid4()), "request_code": code, "request_type": "component",
                "cmt_partner_id": insp.get("vendor_id", ""), "cmt_partner_name": insp.get("vendor_name", ""),
                "vendor_id": insp.get("vendor_id", ""), "vendor_name": insp.get("vendor_name", ""),
                "po_id": po_id, "po_number": (po or {}).get("po_number", ""),
                "work_order_id": "", "work_order_code": (po or {}).get("po_number", ""),
                "product_name": items[0]["component_type"] if items else "",
                "inspection_id": insp["id"],
                "source_shipment_id": insp.get("shipment_id", ""),
                "source_shipment_number": insp.get("shipment_number", ""),
                "origin": "vendor_inspection", "items": items, "urgent": True,
                "needed_by_date": "",
                "notes": ("Backfill: kekurangan pada inspeksi "
                          f"{insp.get('shipment_number','')} belum pernah ditindak-lanjuti."),
                "status": "pending", "requester_id": "", "requester_name": "backfill",
                "fulfilled_shipment_id": None, "fulfilled_shipment_number": None,
                "created_at": _now, "updated_at": _now,
            }
            db.dewi_cmt_component_requests.insert_one(dict(doc))
            db.vendor_material_inspections.update_one(
                {"id": insp["id"]},
                {"$set": {"component_request_id": doc["id"], "component_request_code": code}})
        print(f"    {G}→ {len(pending)} permintaan komponen dibuat dari kekurangan lama{X}")

    if dry:
        print(f"  {Y}(tidak ada perubahan ditulis){X}")
    else:
        print(f"  {G}selesai{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
