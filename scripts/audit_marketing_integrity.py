#!/usr/bin/env python3
"""
AUDIT INTEGRITAS RUJUKAN — PORTAL MARKETING.

Pertanyaan yang dijawab: apakah kolom rujukan (account_id, catalog_item_id,
creator_id, host_id, sku, product) benar-benar MENUNJUK baris yang ada di
masternya? Kalau tidak: filter "per toko" akan mengembalikan kosong, laporan
per akun akan meleset, dan staf akan menyalahkan aplikasi tanpa tahu sebabnya.

Pakai:
  python3 scripts/audit_marketing_integrity.py
  python3 scripts/audit_marketing_integrity.py --json /tmp/integrity.json
"""
import os
import json
import argparse
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

# koleksi -> [(field, koleksi_master, field_master, wajib?)]
RULES = {
    "marketing_orders":           [("account_id", "marketing_platform_accounts", "id", True),
                                   ("catalog_item_id", "marketing_catalog_items", "id", False),
                                   ("sku_id", "marketing_catalog_items", "sku", False)],
    "marketing_sales_data":       [("account_id", "marketing_platform_accounts", "id", True)],
    "marketing_reviews":          [("account_id", "marketing_platform_accounts", "id", True)],
    "marketing_returns":          [("account_id", "marketing_platform_accounts", "id", True),
                                   ("order_id", "marketing_orders", "order_id", False)],
    "marketing_complaints":       [("account_id", "marketing_platform_accounts", "id", True),
                                   ("order_id", "marketing_orders", "order_id", False)],
    "marketing_samples":          [("account_id", "marketing_platform_accounts", "id", True),
                                   ("creator_id", "marketing_kol_creators", "id", False)],
    "marketing_content_calendar": [("account_id", "marketing_platform_accounts", "id", True)],
    "marketing_discounts":        [("account_id", "marketing_platform_accounts", "id", True)],
    "marketing_product_launches": [("account_id", "marketing_platform_accounts", "id", True)],
    "marketing_ads_data":         [("account_id", "marketing_platform_accounts", "id", True)],
    "marketing_live_sessions":    [("account_id", "marketing_platform_accounts", "id", True),
                                   ("host_id", "marketing_livehosts", "id", False),
                                   ("creator_id", "marketing_kol_creators", "id", False)],
    "marketing_livehost_shifts":  [("host_id", "marketing_livehosts", "id", True),
                                   ("account_id", "marketing_platform_accounts", "id", False)],
    "marketing_catalogs":         [("account_id", "marketing_platform_accounts", "id", True)],
    "marketing_catalog_items":    [("catalog_id", "marketing_catalogs", "id", True),
                                   ("fg_material_id", "rahaza_materials", "id", False)],
    "marketing_kol_creators":     [("assigned_account_ids", "marketing_platform_accounts", "id", False)],
    "marketing_livehosts":        [("assigned_account_ids", "marketing_platform_accounts", "id", False)],
    "marketing_tasks":            [("account_id", "marketing_platform_accounts", "id", True)],
    "marketing_account_health":   [("account_id", "marketing_platform_accounts", "id", True)],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = cli[os.environ.get("DB_NAME", "test_database")]
    existing = set(db.list_collection_names())

    master_cache = {}

    def master_keys(coll, field):
        k = (coll, field)
        if k not in master_cache:
            if coll not in existing:
                master_cache[k] = None
            else:
                master_cache[k] = {d.get(field) for d in db[coll].find({}, {field: 1})
                                   if d.get(field) is not None}
        return master_cache[k]

    report = []
    W = 82
    print("=" * W)
    print("AUDIT INTEGRITAS RUJUKAN — PORTAL MARKETING")
    print("=" * W)

    total_bad = 0
    for coll, rules in RULES.items():
        if coll not in existing:
            print(f"\n{coll}: KOLEKSI TIDAK ADA")
            continue
        n = db[coll].count_documents({})
        print(f"\n{coll}  ({n} dokumen)")
        if n == 0:
            print("   (kosong — tidak bisa dinilai)")
            continue
        for field, mcoll, mfield, required in rules:
            keys = master_keys(mcoll, mfield)
            if keys is None:
                print(f"   ! {field:22s} master `{mcoll}` TIDAK ADA di DB")
                continue
            missing_field = 0
            orphan = 0
            examples = []
            for d in db[coll].find({}, {field: 1}):
                v = d.get(field)
                if v in (None, "", []):
                    missing_field += 1
                    continue
                vals = v if isinstance(v, list) else [v]
                for x in vals:
                    if x not in keys:
                        orphan += 1
                        if len(examples) < 3:
                            examples.append(x)
                        break
            flag = "✗" if (orphan or (required and missing_field)) else "✓"
            if flag == "✗":
                total_bad += 1
            print(f"   {flag} {field:22s} → {mcoll}.{mfield:14s} "
                  f"kosong={missing_field:5d} yatim={orphan:5d}"
                  + (f"  contoh={examples}" if examples else ""))
            report.append({"coll": coll, "field": field, "master": mcoll,
                           "master_field": mfield, "required": required,
                           "docs": n, "empty": missing_field, "orphan": orphan,
                           "examples": [str(e) for e in examples]})

    print("\n" + "=" * W)
    print(f"RINGKAS: {total_bad} rujukan cacat (yatim atau kosong padahal wajib)")
    print("=" * W)

    if args.json_out:
        json.dump(report, open(args.json_out, "w"), indent=2, ensure_ascii=False, default=str)
        print(f"JSON -> {args.json_out}")


if __name__ == "__main__":
    main()
