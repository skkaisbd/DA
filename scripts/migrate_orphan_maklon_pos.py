#!/usr/bin/env python3
"""
migrate_orphan_maklon_pos.py — FASE 3: satukan SSOT PO Maklon.

MASALAH (audit 2026-07-31, cacat CRIT SSOT-1 / ORPH-1):
  `dewi_maklon_pos` secara arsitektur adalah MIRROR dari `production_pos`
  (`mirror_of='production_pos'`, ditulis production_maklon_bridge.py). Tetapi
  endpoint Portal Maklon dulu menulis PO **ASLI** ke collection mirror itu.
  Hasil nyata di DB: 10 dari 11 PO maklon YATIM — tidak punya baris
  `production_pos`, sehingga TIDAK BISA dibuatkan job CMT / dikirimi material /
  diterima / didispatch. 7 di antaranya berstatus `in_production`/`completed`/
  `invoiced` ⇒ PROGRES PALSU di layar.

APA YANG DILAKUKAN SKRIP INI (idempoten):
  Untuk setiap PO maklon yatim:
    1. Buat `production_pos` dengan **id yang sama** (kunci mirror) +
       `business_type='maklon'`, status dipetakan dari status maklon.
    2. Buat `po_items` dari `items[]` embedded (bawa serta buyer_catalog_id /
       maklon_variant_id / sku / color / size / qty / cmt_price_snapshot).
    3. Tandai dokumen maklon sebagai mirror (`mirror_of`, `production_po_id`)
       dan simpan jejak `migrated_from_orphan_at`.
  PO yang sudah punya `production_pos` DILEWATI.

Pakai:
    python3 scripts/migrate_orphan_maklon_pos.py --dry-run
    python3 scripts/migrate_orphan_maklon_pos.py
"""
from __future__ import annotations
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

MAKLON_TO_PO_STATUS = {
    'draft': 'Draft',
    'confirmed': 'Confirmed',
    'in_production': 'In Production',
    'partial_delivered': 'In Production',
    'completed': 'Completed',
    'invoiced': 'Completed',
    'cancelled': 'Cancelled',
}


def now():
    return datetime.now(timezone.utc)


def main():
    dry = "--dry-run" in sys.argv
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    pos = list(db.dewi_maklon_pos.find({}, {"_id": 0}))
    orphans = [p for p in pos if not db.production_pos.find_one({"id": p["id"]}, {"_id": 1})]
    print(f"{B}{C}MIGRASI PO MAKLON YATIM → SSOT production_pos{X}")
    print(f"  total PO maklon : {len(pos)}")
    print(f"  yatim           : {len(orphans)}")
    if dry:
        print(f"  {Y}(dry-run — tidak menulis){X}")
    if not orphans:
        print(f"  {G}tidak ada yang perlu dimigrasi{X}")
        return 0

    migrated = 0
    items_created = 0
    for p in orphans:
        status = MAKLON_TO_PO_STATUS.get((p.get("status") or "draft").lower(), "Draft")
        po_doc = {
            "id": p["id"],
            "po_number": p.get("po_number", ""),
            "customer_name": p.get("client_name", ""),
            "buyer_id": p.get("client_id"),
            "vendor_id": p.get("vendor_id"),
            "vendor_name": p.get("vendor_name", ""),
            "po_date": p.get("po_date"),
            "deadline": p.get("deadline"),
            "delivery_deadline": None,
            "status": status,
            "notes": (p.get("notes") or ""),
            "business_type": "maklon",
            "created_by": p.get("created_by_name") or "migrasi-ssot",
            "created_at": p.get("created_at") or now(),
            "updated_at": now(),
            "migrated_from_maklon_orphan": True,
        }
        rows = []
        for it in (p.get("items") or []):
            rows.append({
                "id": it.get("item_id") or str(uuid.uuid4()),
                "po_id": p["id"],
                "po_number": p.get("po_number", ""),
                "catalog_item_id": it.get("buyer_catalog_id"),
                "maklon_variant_id": it.get("maklon_variant_id"),
                "buyer_ref_code": it.get("buyer_ref_code", ""),
                "product_name": it.get("product_description") or it.get("artikel", ""),
                "sku": it.get("sku_code", ""),
                "color": it.get("color", ""),
                "size": it.get("size", ""),
                "qty": int(it.get("qty") or 0),
                "serial_number": it.get("seri_no", ""),
                "cmt_price_snapshot": float(it.get("cmt_rate_per_pcs") or 0),
                "selling_price_snapshot": 0.0,
                "created_at": it.get("created_at") or now(),
                "migrated_from_maklon_orphan": True,
            })
        print(f"   · {p.get('po_number'):<24} status {p.get('status'):<18} "
              f"{len(rows)} item → production_pos({status})")
        if not dry:
            db.production_pos.insert_one(dict(po_doc))
            if rows:
                db.po_items.insert_many([dict(r) for r in rows])
            db.dewi_maklon_pos.update_one(
                {"id": p["id"]},
                {"$set": {"mirror_of": "production_pos",
                          "production_po_id": p["id"],
                          "production_po_status": status,
                          "business_type": "maklon",
                          "migrated_from_orphan_at": now().isoformat(),
                          "updated_at": now()}})
        migrated += 1
        items_created += len(rows)

    print(f"\n  {G}selesai{X}: {migrated} PO, {items_created} item"
          + (f" {Y}(dry-run){X}" if dry else ""))
    if not dry:
        left = [p for p in db.dewi_maklon_pos.find({}, {"_id": 0, "id": 1})
                if not db.production_pos.find_one({"id": p["id"]}, {"_id": 1})]
        print(f"  sisa yatim: {len(left)}")
        return 0 if not left else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
