#!/usr/bin/env python3
"""
AUDIT "FIELD DIBACA TAPI TIDAK ADA" — kelas cacat paling sunyi di portal marketing.

CONTOH NYATA YANG MEMICU AUDIT INI
----------------------------------
`GET /api/marketing/live/summary` menjumlahkan `$gmv`, `$total_orders`, `$cr_rate`.
Tiga field itu **tidak pernah ada** di `marketing_live_sessions` — dokumennya
menyimpan `revenue`, `orders`, `conversion_rate`. Hasilnya: dasbor Live Selling
menampilkan **total revenue Rp 0 untuk 18 sesi**, dan "top host" semuanya Rp 0.
Tidak ada error, tidak ada baris merah — hanya angka nol yang salah, dan angka nol
yang salah tetap ikut dibawa ke rapat.

Kelas cacat ini tidak tertangkap audit endpoint (route-nya ADA dan balas 200)
maupun tes yang hanya memeriksa status HTTP.

CARA MEMBEDAKAN CACAT DARI RUJUKAN YANG SAH
-------------------------------------------
Dalam agregasi Mongo, `"$x"` boleh menunjuk field yang DIBUAT tahap sebelumnya
(`{"$group": {"x": {"$sum": ...}}}` lalu `{"$project": {"y": "$x"}}`). Karena itu
audit ini memakai dua tingkat keyakinan:

* **A. PASTI CACAT** — `"$x"` dibaca, `x` tidak pernah ada di dokumen, DAN `x`
  tidak pernah dibuat sebagai keluaran tahap mana pun di berkas itu.
* **B. RUJUKAN-DIRI** — pola `{"x": {"$sum": "$x"}}` / `{"$ifNull": ["$x", 0]}`
  dengan kunci yang sama: ini membaca `x` dari KOLEKSI (bukan dari tahap
  sebelumnya). Kalau `x` tidak ada di dokumen ⇒ hasilnya selalu 0. Inilah bentuk
  persis bug Live Selling.

Pakai:
  python3 scripts/audit_marketing_field_reads.py
  python3 scripts/audit_marketing_field_reads.py --json /tmp/reads.json
"""
import os
import re
import json
import argparse

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
ROUTES = "/app/backend/routes"

MONGO_OPS = {
    "sum", "avg", "min", "max", "group", "match", "project", "sort", "limit",
    "skip", "unwind", "lookup", "addFields", "set", "count", "ifNull", "cond",
    "gte", "lte", "gt", "lt", "eq", "ne", "in", "nin", "or", "and", "not",
    "exists", "regex", "options", "push", "first", "last", "size", "type",
    "multiply", "divide", "subtract", "add", "dateToString", "toDouble",
    "toInt", "concat", "arrayElemAt", "switch", "literal", "expr", "elemMatch",
    "all", "inc", "pull", "setOnInsert", "unset", "each", "slice", "round",
    "abs", "floor", "let", "map", "filter", "reduce", "mergeObjects",
    "replaceRoot", "facet", "sample", "dateFromString", "toString", "strLenCP",
    "trim", "toLower", "toUpper", "split", "sortArray", "objectToArray",
    "arrayToObject", "sqrt", "pow", "anyElementTrue", "isArray", "range",
    "zip", "indexOfArray", "reverseArray", "nor", "denseRank", "topN",
    "dateTrunc", "week", "month", "year", "dayOfMonth", "hour", "minute",
    "isoWeek", "isoWeekYear", "case", "then", "else", "branches", "default",
    "text", "search", "meta", "natural",
}
GENERIC = {"_id", "id"}

OWNERS = {
    "marketing_live_sessions": ["marketing_live_sessions_routes.py",
                                "marketing_live_analytics.py",
                                "marketing_live_sales_sync.py"],
    "marketing_ads_data": ["marketing_ads_routes.py"],
    "marketing_orders": ["marketing_orders_routes.py"],
    "marketing_samples": ["marketing_samples_routes.py"],
    "marketing_reviews": ["marketing_reviews_routes.py"],
    "marketing_returns": ["marketing_returns_routes.py"],
    "marketing_complaints": ["marketing_complaints_routes.py"],
    "marketing_content_calendar": ["marketing_content_calendar_routes.py"],
    "marketing_discounts": ["marketing_discounts_routes.py"],
    "marketing_product_launches": ["marketing_product_launches_routes.py"],
    "marketing_account_health": ["marketing_account_health_routes.py"],
    "marketing_sales_data": ["marketing_sales.py"],
    "marketing_platform_accounts": ["marketing_accounts.py"],
    "marketing_catalog_items": ["marketing_catalog_items.py"],
    "marketing_catalogs": ["marketing_catalog_mgmt.py"],
    "marketing_kol_creators": ["marketing_kol_creators.py"],
    "marketing_livehosts": ["marketing_livehost_hosts.py"],
    "marketing_livehost_shifts": ["marketing_livehost_shifts.py"],
    "marketing_tasks": ["marketing_tasks.py"],
}

MONEY = re.compile(r"(revenue|gmv|spend|amount|total|price|hpp|order|qty|"
                   r"quantity|viewer|rate|score|refund|cost|fee|conv|click|"
                   r"impress|units)", re.I)


def actual_fields(db, coll, sample=400):
    keys, n = set(), 0
    for d in db[coll].find({}, limit=sample):
        n += 1
        keys |= set(d.keys())
        for k, v in d.items():
            if isinstance(v, dict):
                keys |= {f"{k}.{sk}" for sk in v.keys()}
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                keys |= {f"{k}.{sk}" for sk in v[0].keys()}
    return keys, n


def analyse(path):
    """-> (dibaca {field: [baris]}, dibuat {field}, rujukan_diri {field: [baris]})"""
    src = open(path, encoding="utf-8").read()
    read, made, selfref = {}, set(), {}

    for m in re.finditer(r'"\$([a-zA-Z_][a-zA-Z0-9_.]*)"', src):
        name = m.group(1)
        if name.split(".")[0] in MONGO_OPS:
            continue
        read.setdefault(name, []).append(src[:m.start()].count("\n") + 1)

    # keluaran tahap: "nama": { ... }  atau  "nama": "$x"
    for m in re.finditer(r'"([a-zA-Z_][a-zA-Z0-9_]*)"\s*:\s*(\{|")', src):
        made.add(m.group(1))

    # rujukan-diri: "x": <ekspresi yang memuat "$x">
    for m in re.finditer(r'"([a-zA-Z_][a-zA-Z0-9_]*)"\s*:\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})',
                         src):
        name, expr = m.group(1), m.group(2)
        if f'"${name}"' in expr:
            selfref.setdefault(name, []).append(src[:m.start()].count("\n") + 1)
    return read, made, selfref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = cli[os.environ.get("DB_NAME", "test_database")]
    existing = set(db.list_collection_names())

    print("=" * 86)
    print("AUDIT FIELD DIBACA TAPI TIDAK ADA DI DOKUMEN")
    print("=" * 86)

    hard, selfrefs, empty = [], [], []
    for coll, files in OWNERS.items():
        if coll not in existing:
            empty.append((coll, "koleksi tidak ada"))
            continue
        keys, n = actual_fields(db, coll)
        if n == 0:
            empty.append((coll, "kosong — tidak bisa dinilai"))
            continue
        for fname in files:
            path = os.path.join(ROUTES, fname)
            if not os.path.exists(path):
                continue
            read, made, selfref = analyse(path)

            a = []
            for f, lines in sorted(read.items()):
                base = f.split(".")[0]
                if f in keys or base in keys or f in GENERIC:
                    continue
                if base in made:
                    continue
                a.append({"field": f, "lines": sorted(set(lines))[:4]})
            if a:
                hard.append({"coll": coll, "file": fname, "docs": n, "fields": a})

            b = []
            for f, lines in sorted(selfref.items()):
                if f in keys or f in GENERIC:
                    continue
                b.append({"field": f, "lines": sorted(set(lines))[:4]})
            if b:
                selfrefs.append({"coll": coll, "file": fname, "docs": n, "fields": b})

    def show(title, group, sym):
        money = sum(1 for g in group for x in g["fields"] if MONEY.search(x["field"]))
        print(f"\n{title} (menyangkut angka: {money})")
        for g in group:
            print(f"  {sym} {g['coll']}  ({g['file']}, {g['docs']} dokumen)")
            for x in g["fields"]:
                tag = " ← ANGKA" if MONEY.search(x["field"]) else ""
                print(f"       ${x['field']:<32} baris {x['lines']}{tag}")

    show("[A] PASTI CACAT — dibaca, tak pernah ada di dokumen, tak pernah dibuat tahap mana pun",
         hard, "✗")
    show("[B] RUJUKAN-DIRI — `{'x': {'$sum': '$x'}}` padahal `x` tidak ada ⇒ hasil selalu 0",
         selfrefs, "✗")

    print(f"\n[C] KOLEKSI TIDAK BISA DINILAI : {len(empty)}")
    for coll, why in empty:
        print(f"  · {coll} — {why}")

    tot_a = sum(len(g["fields"]) for g in hard)
    tot_b = sum(len(g["fields"]) for g in selfrefs)
    print("\n" + "=" * 86)
    print(f"RINGKAS: pasti_cacat={tot_a}  rujukan_diri={tot_b}  tak_ternilai={len(empty)}")
    print("=" * 86)

    if args.json_out:
        json.dump({"hard": hard, "selfref": selfrefs, "empty": empty},
                  open(args.json_out, "w"), indent=2, ensure_ascii=False)
        print(f"JSON -> {args.json_out}")


if __name__ == "__main__":
    main()
