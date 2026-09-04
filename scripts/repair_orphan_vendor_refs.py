#!/usr/bin/env python3
"""
repair_orphan_vendor_refs.py — FASE 22 (audit relasi data, permintaan owner:
"audit relasi data, jangan asal HTTP 200").

MASALAH NYATA YANG DITEMUKAN (2026-07-31):
    production_jobs.vendor_id = "demo-vn-jmc"      ← TIDAK ADA di vendor_partners
    users.cmt_vendor_id       = "mk-vendor-demo-1" ← master JMC yang SAH
  ⇒ job PO-INT-DEMO-4 (dijahitkan ke JMC) TIDAK PERNAH muncul di Portal Vendor
    CMT, walaupun semua endpoint menjawab HTTP 200. Penyebabnya: satu seeder
    memakai id vendor yang dipaku (hardcode), seeder lain MENGADOPSI id master
    yang sudah ada karena unique index `code`. Dua id untuk satu vendor.

Skrip ini:
  1. Mengumpulkan id vendor yang SAH dari `vendor_partners` (+ `dewi_cmt_partners`).
  2. Memindai koleksi yang menunjuk vendor (`vendor_id` / `cmt_vendor_id`).
  3. Untuk referensi YATIM: cari master dengan NAMA yang sama → repoint.
     Kalau nama tidak ketemu, hanya dilaporkan (tidak menghapus apa pun).

Pakai:
    python3 scripts/repair_orphan_vendor_refs.py            # audit + perbaiki
    python3 scripts/repair_orphan_vendor_refs.py --dry-run  # hanya laporan
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from gr_common import db_handle  # noqa: E402

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

# koleksi → (field id vendor, field nama vendor)
TARGETS = [
    ("production_pos", "vendor_id", "vendor_name"),
    ("po_items", "vendor_id", "vendor_name"),
    ("production_jobs", "vendor_id", "vendor_name"),
    ("vendor_shipments", "vendor_id", "vendor_name"),
    ("buyer_shipments", "vendor_id", "vendor_name"),
    ("cmt_receipts", "cmt_vendor_id", "cmt_name"),
    ("dewi_cmt_permak", "vendor_id", "vendor_name"),
    ("dewi_cmt_payments", "vendor_id", "vendor_name"),
    ("dewi_cmt_component_requests", "vendor_id", "vendor_name"),
    ("dewi_cmt_jobs", "vendor_id", "vendor_name"),
]


def main() -> int:
    dry = "--dry-run" in sys.argv
    db = db_handle()
    masters = list(db.vendor_partners.find({}, {"_id": 0, "id": 1, "name": 1, "garment_name": 1, "code": 1}))
    masters += list(db.dewi_cmt_partners.find({}, {"_id": 0, "id": 1, "name": 1, "code": 1}))
    valid_ids = {m["id"] for m in masters if m.get("id")}
    by_name: dict[str, str] = {}
    for m in masters:
        for key in ("name", "garment_name"):
            nm = (m.get(key) or "").strip().lower()
            if nm and nm not in by_name:
                by_name[nm] = m["id"]

    print(f"{B}{C}AUDIT REFERENSI VENDOR — {len(valid_ids)} master sah{X}")
    total_orphan = 0
    total_fixed = 0
    for coll, id_field, name_field in TARGETS:
        rows = list(db[coll].find(
            {id_field: {"$nin": [None, ""]}},
            {"_id": 0, "id": 1, id_field: 1, name_field: 1},
        ))
        orphans = [r for r in rows if r.get(id_field) not in valid_ids]
        if not orphans:
            continue
        print(f"\n  {B}{coll}{X}: {len(orphans)} referensi yatim (dari {len(rows)})")
        for r in orphans:
            total_orphan += 1
            nm = (r.get(name_field) or "").strip().lower()
            target = by_name.get(nm)
            if target and not dry:
                db[coll].update_one({"id": r["id"]}, {"$set": {id_field: target}})
                total_fixed += 1
                print(f"    {G}fix{X} {r['id'][:12]}… {r.get(id_field)} → {target}  ({r.get(name_field)})")
            elif target:
                print(f"    {Y}akan di-fix{X} {r['id'][:12]}… {r.get(id_field)} → {target}")
            else:
                print(f"    {R}tak bisa{X} {r['id'][:12]}… {r.get(id_field)} (nama '{r.get(name_field)}' tak ada di master)")

    print(f"\n{B}ringkas:{X} yatim={total_orphan} diperbaiki={total_fixed}"
          f"{'  (dry-run)' if dry else ''}")
    if total_orphan == 0:
        print(f"{G}{B}HIJAU — semua referensi vendor menunjuk master yang sah{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
