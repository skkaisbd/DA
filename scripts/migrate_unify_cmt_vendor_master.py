#!/usr/bin/env python3
"""
migrate_unify_cmt_vendor_master.py — FASE 7: satukan master vendor CMT.

MASALAH (audit 2026-07-31, cacat HIGH CMT-3 / FIN-3):
  Ada DUA master vendor CMT yang TIDAK BERIRISAN sama sekali (irisan id = 0):
    · `vendor_partners`     → dipakai engine produksi/maklon (PO.vendor_id,
                              production_jobs, vendor_shipments, portal vendor)
    · `dewi_cmt_partners`   → dipakai Portal CMT (lifecycle) & pembayaran CMT
  Akibat nyata: `dewi_cmt_payments.cmt_partner_id` menyimpan id dari DUA master
  berbeda (dokumen baru dari `vendor_partners`, dokumen lama dari
  `dewi_cmt_partners`) ⇒ pengelompokan tagihan per CMT salah, dan 4 vendor CMT
  di Portal CMT TIDAK BISA dipakai di PO/produksi sama sekali.

APA YANG DILAKUKAN (idempoten):
  1. Untuk setiap `dewi_cmt_partners` yang belum punya pasangan di
     `vendor_partners` (cocok by code/nama) → buat entri `vendor_partners`
     dengan **id yang sama** supaya vendor itu langsung bisa dipakai di PO,
     surat jalan material, job, dan portal vendor.
  2. Tautkan dua arah: `dewi_cmt_partners.vendor_partner_id` dan
     `vendor_partners.cmt_partner_id`.
  3. Normalisasi `dewi_cmt_payments`: isi `vendor_id` (id vendor_partners) dan
     alias jumlah (`net_amount` ↔ `total_amount`) bila salah satunya kosong.

Pakai:
    python3 scripts/migrate_unify_cmt_vendor_master.py --dry-run
    python3 scripts/migrate_unify_cmt_vendor_master.py
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
G, Y, C, B, X = "\033[92m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"


def norm(s):
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def main():
    dry = "--dry-run" in sys.argv
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
    now = datetime.now(timezone.utc)
    print(f"{B}{C}UNIFIKASI MASTER VENDOR CMT{X}" + (f" {Y}(dry-run){X}" if dry else ""))

    vps = list(db.vendor_partners.find({}, {"_id": 0}))
    cps = list(db.dewi_cmt_partners.find({}, {"_id": 0}))
    by_name = {norm(v.get("name")): v for v in vps}
    by_code = {norm(v.get("code")): v for v in vps}
    vp_ids = {v["id"] for v in vps}
    print(f"  vendor_partners={len(vps)}  dewi_cmt_partners={len(cps)}  "
          f"irisan_id={len(vp_ids & {c['id'] for c in cps})}")

    created = linked = 0
    for c in cps:
        match = (db.vendor_partners.find_one({"id": c["id"]}, {"_id": 0})
                 or by_name.get(norm(c.get("name")))
                 or by_code.get(norm(c.get("code"))))
        if match:
            if not dry:
                db.dewi_cmt_partners.update_one(
                    {"id": c["id"]}, {"$set": {"vendor_partner_id": match["id"], "updated_at": now}})
                db.vendor_partners.update_one(
                    {"id": match["id"]}, {"$set": {"cmt_partner_id": c["id"], "updated_at": now}})
            linked += 1
            print(f"   · {c.get('code','?'):<10} {c.get('name','')[:28]:<28} → tertaut ke vendor_partners {match['id'][:8]}")
            continue
        doc = {
            "id": c["id"],                      # id SAMA → langsung bisa dipakai lintas modul
            "code": c.get("code") or f"CMT-{c['id'][:4].upper()}",
            "name": c.get("name", ""),
            "contact_name": c.get("pic_name") or c.get("contact_name", ""),
            "contact_phone": c.get("pic_phone") or c.get("phone", ""),
            "address": c.get("address", ""),
            "capacity_pcs": int(c.get("capacity_per_day") or c.get("capacity_pcs") or 0) or None,
            "capacity_note": c.get("notes", ""),
            "notes": f"Dimigrasi dari dewi_cmt_partners (unifikasi master CMT).",
            "is_active": (c.get("status", "active") == "active"),
            "active": (c.get("status", "active") == "active"),
            "cmt_partner_id": c["id"],
            "created_at": c.get("created_at") or now,
            "updated_at": now,
        }
        print(f"   · {doc['code']:<10} {doc['name'][:28]:<28} → {G}dibuat di vendor_partners{X}")
        if not dry:
            db.vendor_partners.insert_one(dict(doc))
            db.dewi_cmt_partners.update_one(
                {"id": c["id"]}, {"$set": {"vendor_partner_id": c["id"], "updated_at": now}})
        created += 1

    # ── arah sebaliknya: vendor produksi/maklon yang belum ada di master CMT ──
    # Tanpa ini `dewi_cmt_payments.cmt_partner_id` untuk vendor engine (mis.
    # `mk-vendor-demo-1`) tetap tidak punya pasangan di `dewi_cmt_partners`,
    # sehingga Portal CMT tidak bisa menampilkan tagihannya.
    created_cmt = 0
    for v in list(db.vendor_partners.find({}, {"_id": 0})):
        if db.dewi_cmt_partners.find_one({"id": v["id"]}, {"_id": 1}):
            continue
        if db.dewi_cmt_partners.find_one({"vendor_partner_id": v["id"]}, {"_id": 1}):
            continue
        doc = {
            "id": v["id"],
            "code": v.get("code") or f"CMT-{v['id'][:4].upper()}",
            "name": v.get("name", ""),
            "pic_name": v.get("contact_name", ""),
            "pic_phone": v.get("contact_phone", ""),
            "address": v.get("address", ""),
            "status": "active" if v.get("is_active", True) else "inactive",
            "vendor_partner_id": v["id"],
            "notes": "Dicerminkan dari vendor_partners (unifikasi master CMT).",
            "created_at": v.get("created_at") or now,
            "updated_at": now,
        }
        print(f"   · {doc['code']:<10} {doc['name'][:28]:<28} → {G}dicerminkan ke dewi_cmt_partners{X}")
        if not dry:
            db.dewi_cmt_partners.insert_one(dict(doc))
            db.vendor_partners.update_one({"id": v["id"]},
                                          {"$set": {"cmt_partner_id": v["id"], "updated_at": now}})
        created_cmt += 1

    # ── tandai job CMT legacy tanpa PO supaya TERLIHAT, bukan diam-diam salah ──
    legacy_q = {"po_id": {"$in": [None, ""]}}
    legacy_n = db.dewi_cmt_jobs.count_documents(legacy_q)
    if legacy_n and not dry:
        db.dewi_cmt_jobs.update_many(legacy_q, {"$set": {
            "legacy_no_po": True,
            "legacy_note": ("Job CMT lama tanpa PO — tidak bisa ditelusuri. Pekerjaan CMT "
                            "yang benar dibuat lewat PO → Surat Jalan material → inspeksi "
                            "→ production_jobs."),
            "updated_at": now}})
    print(f"  job CMT legacy tanpa PO ditandai : {legacy_n}")

    # normalisasi pembayaran CMT
    fixed = 0
    for p in db.dewi_cmt_payments.find({}, {"_id": 0}):
        upd = {}
        vid = p.get("vendor_id") or p.get("cmt_partner_id")
        if vid and not p.get("vendor_id"):
            upd["vendor_id"] = vid
        if p.get("net_amount") is None and p.get("total_amount") is not None:
            upd["net_amount"] = p["total_amount"]
        if p.get("total_amount") is None and p.get("net_amount") is not None:
            upd["total_amount"] = p["net_amount"]
        if not p.get("vendor_name"):
            upd["vendor_name"] = p.get("cmt_name", "")
        if upd and not dry:
            db.dewi_cmt_payments.update_one({"id": p["id"]}, {"$set": {**upd, "updated_at": now}})
        if upd:
            fixed += 1

    print(f"\n  vendor_partners dibuat : {created}")
    print(f"  dewi_cmt_partners dicerminkan : {created_cmt}")
    print(f"  tertaut                : {linked}")
    print(f"  pembayaran dinormalkan : {fixed}")
    if not dry:
        vp_ids = set(db.vendor_partners.distinct("id"))
        cp_ids = set(db.dewi_cmt_partners.distinct("id"))
        print(f"  {G}irisan id sekarang: {len(vp_ids & cp_ids)} / {len(cp_ids)} master CMT{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
