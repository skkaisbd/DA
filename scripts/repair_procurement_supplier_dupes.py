#!/usr/bin/env python3
"""
repair_procurement_supplier_dupes.py — gabungkan Master Supplier kembar.

KENAPA ADA (kejadian nyata 2026-08-06):
  Saat merapikan nama data demo, `name` dibersihkan TAPI `name_key` tidak
  (regex hanya mencocokkan huruf besar, `name_key` disimpan huruf kecil).
  Akibatnya pencarian "sudah ada supplier ini?" GAGAL dan migrasi berikutnya
  membuat master BARU untuk perusahaan yang SAMA — tepat cacat yang hendak
  dicegah oleh Master Supplier.

  Skrip ini memperbaiki keadaan itu TANPA menyentuh angka transaksi:
    1. tentukan master KANONIK per perusahaan (kode terkecil / SUP-000x),
    2. arahkan ulang seluruh rujukan `supplier_id` ke master kanonik,
    3. hapus baris daftar harga kembar (material+satuan+supplier sama),
    4. hapus master kembar yang sudah tidak dirujuk,
    5. tulis ulang `name_key` kanonik supaya pencocokan berikutnya benar.

  Stok, jurnal, nilai PO/GR/faktur TIDAK diubah — hanya kolom rujukan.

Pakai:
  python3 scripts/repair_procurement_supplier_dupes.py            # laporan saja
  python3 scripts/repair_procurement_supplier_dupes.py --apply    # jalankan
"""
from __future__ import annotations

import os
import re
import sys

from pymongo import MongoClient

APPLY = "--apply" in sys.argv
db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
    os.environ.get("DB_NAME", "test_database")
]

# Koleksi + field yang menyimpan rujukan supplier.
REF_FIELDS = [
    ("rahaza_purchase_orders", "supplier_id"),
    ("rahaza_grn_inspections", "supplier_id"),
    ("warehouse_receiving", "supplier_id"),
    ("rahaza_ap_invoices", "supplier_id"),
    ("rahaza_supplier_price_lists", "supplier_id"),
]

LEGAL_PREFIX = re.compile(r"^(pt\.?|cv\.?|ud\.?|pd\.?|koperasi|toko)\s+", re.I)
TAG = re.compile(r"\s+[0-9a-f]{6}\b", re.I)


def canon_key(name: str) -> str:
    """Kunci pencocokan: buang gelar badan usaha, tag uji, dan spasi ganda."""
    s = (name or "").strip().lower()
    s = TAG.sub("", s)
    s = LEGAL_PREFIX.sub("", s)
    return re.sub(r"[\s.]+", " ", s).strip()


def main() -> int:
    sups = list(db.rahaza_suppliers.find({}, {"_id": 0}).sort("code", 1))
    groups: dict[str, list] = {}
    for s in sups:
        groups.setdefault(canon_key(s.get("name")), []).append(s)

    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    if not dupes:
        print("✓ Tidak ada Master Supplier kembar.")
        return 0

    print(f"Ditemukan {len(dupes)} perusahaan dengan master kembar:")
    plan = []
    for key, rows in dupes.items():
        rows.sort(key=lambda r: r.get("code") or "")
        keep, drop = rows[0], rows[1:]
        print(f"  · {key}: SIMPAN {keep['code']} ({keep['name']}) "
              f"← gabung {[d['code'] for d in drop]}")
        plan.append((keep, drop))

    if not APPLY:
        print("\n(laporan saja — jalankan ulang dengan --apply untuk memperbaiki)")
        return 0

    moved = {c: 0 for c, _ in REF_FIELDS}
    removed_pl = 0
    for keep, drop in plan:
        drop_ids = [d["id"] for d in drop]
        for coll, field in REF_FIELDS:
            res = db[coll].update_many({field: {"$in": drop_ids}},
                                       {"$set": {field: keep["id"]}})
            moved[coll] += res.modified_count
        # daftar harga kembar: sisakan satu per (material_id, uom)
        seen = set()
        for row in db.rahaza_supplier_price_lists.find(
                {"supplier_id": keep["id"]}, {"_id": 1, "material_id": 1, "uom": 1}).sort("_id", 1):
            sig = (row.get("material_id"), row.get("uom"))
            if sig in seen:
                db.rahaza_supplier_price_lists.delete_one({"_id": row["_id"]})
                removed_pl += 1
            else:
                seen.add(sig)
        db.rahaza_suppliers.delete_many({"id": {"$in": drop_ids}})

    # name_key kanonik untuk SEMUA master (juga yang tak kembar)
    fixed_keys = 0
    used: set[str] = set()
    for s in db.rahaza_suppliers.find({}, {"_id": 1, "id": 1, "name": 1, "name_key": 1}).sort("code", 1):
        key = canon_key(s.get("name"))
        if not key or key in used:
            used.add(s.get("name_key") or "")
            continue
        used.add(key)
        if s.get("name_key") != key:
            db.rahaza_suppliers.update_one({"_id": s["_id"]}, {"$set": {"name_key": key}})
            fixed_keys += 1

    print("\n✓ Selesai.")
    print("  rujukan dipindah:", {k: v for k, v in moved.items() if v})
    print("  daftar harga kembar dihapus:", removed_pl)
    print("  name_key dirapikan:", fixed_keys)
    print("  master tersisa:", db.rahaza_suppliers.count_documents({}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
