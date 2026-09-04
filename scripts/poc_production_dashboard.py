#!/usr/bin/env python3
"""poc_production_dashboard.py — bukti angka Dashboard Produksi baru benar.

Menanam satu skenario lengkap (PO internal → cutting → kirim vendor → terima &
QC → permak → serah terima FG), memanggil `/api/prod/dashboard`, memeriksa tiap
angka, lalu membersihkan seluruh artefak uji.

    python3 scripts/poc_production_dashboard.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

import requests  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

API = os.environ.get("INTERNAL_API_URL", "http://localhost:8001")
TAG = "ZZPOC-PRODDASH"
results = []


def check(cond, label):
    results.append((bool(cond), label))
    print(("  ✓ " if cond else "  ✗ ") + label)


def uid():
    return str(uuid.uuid4())


def db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def login():
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=30)
    r.raise_for_status()
    b = r.json()
    return {"Authorization": f"Bearer {b.get('access_token') or b.get('token')}"}


async def teardown(d=None, quiet=False):
    d = d if d is not None else db()
    for coll, key in [("production_pos", "notes"), ("po_items", "notes"),
                      ("cutting_orders", "notes"), ("vendor_shipments", "notes"),
                      ("vendor_shipment_items", "notes"), ("cmt_receipts", "notes"),
                      ("buyer_shipments", "notes"), ("buyer_shipment_items", "notes"),
                      ("dewi_cmt_permak", "notes")]:
        await d[coll].delete_many({key: TAG})
    if not quiet:
        print("  · artefak uji dibersihkan")


async def seed():
    d = db()
    await teardown(d, quiet=True)
    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()

    po_id, po2_id = uid(), uid()
    await d.production_pos.insert_many([
        {"id": po_id, "po_number": "ZZPO-A", "business_type": "internal",
         "status": "In Production", "customer_name": "Internal DA", "notes": TAG,
         "created_at": now, "updated_at": now, "deadline": today},
        {"id": po2_id, "po_number": "ZZPO-B", "business_type": "internal",
         "status": "Draft", "customer_name": "Internal DA", "notes": TAG,
         "created_at": now, "updated_at": now},
    ])
    it1, it2 = uid(), uid()
    await d.po_items.insert_many([
        {"id": it1, "po_id": po_id, "qty": 300, "notes": TAG},
        {"id": it2, "po_id": po2_id, "qty": 120, "notes": TAG},
    ])

    await d.cutting_orders.insert_many([
        {"id": uid(), "number": "ZZCUT-1", "status": "in_progress", "notes": TAG,
         "planned_output_qty": 300, "produced_qty": 0, "consumed_input_qty": 0, "waste_qty": 0},
        {"id": uid(), "number": "ZZCUT-2", "status": "completed", "notes": TAG,
         "planned_output_qty": 200, "produced_qty": 200, "consumed_input_qty": 100, "waste_qty": 4},
    ])

    s1, s2 = uid(), uid()
    await d.vendor_shipments.insert_many([
        {"id": s1, "po_id": po_id, "vendor_name": "CMT Melati", "status": "Sent",
         "shipment_date": today, "notes": TAG},
        {"id": s2, "po_id": po_id, "vendor_name": "CMT Melati", "status": "Received",
         "shipment_date": today, "notes": TAG},
    ])
    await d.vendor_shipment_items.insert_many([
        {"id": uid(), "shipment_id": s1, "po_item_id": it1, "qty_sent": 180, "notes": TAG},
        {"id": uid(), "shipment_id": s2, "po_item_id": it1, "qty_sent": 120, "notes": TAG},
    ])

    await d.cmt_receipts.insert_many([
        {"id": uid(), "receipt_code": "ZZRCV-1", "business_type": "internal", "status": "Approved",
         "cmt_name": "CMT Melati", "total_actual": 110, "total_rejected": 10,
         "approved_at": today, "receipt_date": today, "notes": TAG},
        {"id": uid(), "receipt_code": "ZZRCV-2", "business_type": "internal", "status": "Submitted",
         "cmt_name": "CMT Melati", "total_actual": 50, "total_rejected": 0,
         "receipt_date": today, "notes": TAG},
    ])

    await d.dewi_cmt_permak.insert_many([
        {"id": uid(), "permak_number": "ZZPMK-1", "status": "open", "qty": 10, "notes": TAG},
        {"id": uid(), "permak_number": "ZZPMK-2", "status": "done", "qty": 4, "notes": TAG},
    ])

    b1 = uid()
    await d.buyer_shipments.insert_one(
        {"id": b1, "po_id": po_id, "shipment_date": today, "notes": TAG})
    await d.buyer_shipment_items.insert_one(
        {"id": uid(), "shipment_id": b1, "po_item_id": it1, "qty_shipped": 100, "notes": TAG})
    return po_id


def main():
    asyncio.run(seed())
    hdr = login()
    r = requests.get(f"{API}/api/prod/dashboard?business_type=internal&days=30",
                     headers=hdr, timeout=60)
    try:
        check(r.status_code == 200, f"HTTP 200 (dapat {r.status_code})")
        d = r.json()
        s, p = d["ringkasan"], {x["stage"]: x for x in d["pipeline"]}

        print("\n1) Ringkasan PO")
        check(s["po_aktif"] == 2, f"2 PO aktif (dapat {s['po_aktif']})")
        check(s["qty_aktif"] == 420, f"qty aktif 300+120=420 (dapat {s['qty_aktif']})")
        check(p["rencana"]["qty"] == 120, f"rencana (Draft) 120 pcs (dapat {p['rencana']['qty']})")

        print("\n2) Cutting")
        c = d["cutting"]
        check(c["in_progress"] == 1 and c["completed"] == 1,
              f"1 berjalan / 1 selesai (dapat {c['in_progress']}/{c['completed']})")
        check(c["qty_dalam_proses"] == 300, f"300 pcs sedang dipotong (dapat {c['qty_dalam_proses']})")
        check(c["rendemen"] == 2.0, f"rendemen 200/100 = 2.0 (dapat {c['rendemen']})")

        print("\n3) Di vendor CMT")
        v = d["vendor"]
        check(v["qty_terkirim"] == 300, f"300 pcs dikirim (dapat {v['qty_terkirim']})")
        check(v["qty_kembali"] == 120, f"120 pcs sudah kembali (dapat {v['qty_kembali']})")
        check(v["outstanding"] == 180, f"180 pcs masih di vendor (dapat {v['outstanding']})")
        check(v["per_vendor"] and v["per_vendor"][0]["vendor"] == "CMT Melati",
              "rincian per vendor terisi")

        print("\n4) Terima & QC")
        q = d["qc"]
        check(q["approved"] == 1 and q["submitted"] == 1,
              f"1 disetujui / 1 menunggu (dapat {q['approved']}/{q['submitted']})")
        check(q["qty_diterima"] == 110, f"110 pcs lolos (dapat {q['qty_diterima']})")
        check(q["tingkat_cacat"] == 8.33, f"cacat 10/120 = 8.33% (dapat {q['tingkat_cacat']})")
        check(q["menunggu_qty"] == 50, f"50 pcs menunggu diperiksa (dapat {q['menunggu_qty']})")

        print("\n5) Permak & serah terima")
        check(d["permak"]["terbuka"] == 1 and d["permak"]["qty_terbuka"] == 10,
              f"permak terbuka 1 / 10 pcs (dapat {d['permak']['terbuka']}/{d['permak']['qty_terbuka']})")
        check(d["handover"]["qty_periode"] == 100,
              f"100 pcs diserahterimakan (dapat {d['handover']['qty_periode']})")
        check(d["handover"]["label"] == "Serah Terima FG", "label internal benar")

        print("\n6) PO tertahan")
        check(len(d["aging"]) == 2 and d["aging"][0]["po_number"] in ("ZZPO-A", "ZZPO-B"),
              f"daftar PO tertahan terisi ({len(d['aging'])} baris)")

        print("\n7) Portal Maklon tidak ikut terhitung")
        rm = requests.get(f"{API}/api/prod/dashboard?business_type=maklon", headers=hdr, timeout=60).json()
        check(rm["ringkasan"]["po_aktif"] == 0,
              f"PO internal tidak bocor ke maklon (dapat {rm['ringkasan']['po_aktif']})")
    finally:
        print("\n8) Bersih-bersih")
        asyncio.run(teardown())

    ok = sum(1 for c, _ in results if c)
    print(f"\n{'='*60}\n{ok}/{len(results)} LULUS")
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
