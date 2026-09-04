#!/usr/bin/env python3
"""
audit_maklon_production_ssot.py — FORENSIK relasi data alur PRODUKSI & MAKLON.

Tujuan (READ-ONLY, tanpa menyentuh DB selain membaca):
  1) Untuk setiap file route di domain produksi/maklon/cmt/shipment:
     ekstrak SEMUA akses `db.<collection>.<op>` via AST → tahu siapa
     menulis/membaca collection apa.
  2) Balik peta itu: per-collection → siapa penulisnya, siapa pembacanya.
     Collection dengan >1 penulis dari domain berbeda = kandidat SSOT ganda.
  3) Cetak jumlah dokumen nyata per collection (dari Mongo) supaya bisa
     dibedakan "dipakai" vs "mati".
  4) Ekstrak field relasi (po_id, po_number, vendor_id, job_id, dst) yang
     BENAR-BENAR ada di dokumen → peta relasi faktual, bukan asumsi.

Pakai:
  python3 scripts/audit_maklon_production_ssot.py            # ringkas
  python3 scripts/audit_maklon_production_ssot.py --json     # dump JSON
"""
from __future__ import annotations
import ast
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES = ROOT / "backend" / "routes"
CORE = ROOT / "backend" / "core"
SERVICES = ROOT / "backend" / "services"

WRITE_OPS = {"insert_one", "insert_many", "update_one", "update_many",
             "replace_one", "delete_one", "delete_many", "find_one_and_update",
             "find_one_and_replace", "find_one_and_delete", "bulk_write"}
READ_OPS = {"find", "find_one", "count_documents", "aggregate", "distinct",
            "estimated_document_count"}

DOMAIN_HINTS = ("maklon", "cmt", "production", "produksi", "buyer", "shipment",
                "fg", "permak", "dispatch", "vendor", "exceptions", "wms")


def domain_files():
    out = []
    for base in (ROUTES, CORE, SERVICES):
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.py")):
            s = str(p)
            if "__pycache__" in s or "_archive" in s:
                continue
            if base is ROUTES and not any(h in p.name.lower() for h in DOMAIN_HINTS):
                continue
            out.append(p)
    return out


def collection_of(node):
    """db.<coll>.<op>(...)  |  db['<coll>'].<op>(...)  → (coll, op) or None."""
    if not isinstance(node, ast.Call):
        return None
    fn = node.func
    if not isinstance(fn, ast.Attribute):
        return None
    op = fn.attr
    if op not in WRITE_OPS | READ_OPS:
        return None
    owner = fn.value
    # db.coll
    if isinstance(owner, ast.Attribute):
        coll = owner.attr
        base = owner.value
        base_name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
        if base_name in ("db", "database", "_db"):
            return coll, op
        return None
    # db['coll']
    if isinstance(owner, ast.Subscript):
        base = owner.value
        base_name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
        if base_name in ("db", "database", "_db"):
            sl = owner.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                return sl.value, op
        return None
    return None


def scan():
    per_file = defaultdict(lambda: {"write": set(), "read": set()})
    per_coll = defaultdict(lambda: {"writers": set(), "readers": set()})
    for p in domain_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError as e:
            print(f"  !! SyntaxError {p}: {e}")
            continue
        rel = str(p.relative_to(ROOT))
        for node in ast.walk(tree):
            got = collection_of(node)
            if not got:
                continue
            coll, op = got
            kind = "write" if op in WRITE_OPS else "read"
            per_file[rel][kind].add(coll)
            per_coll[coll]["writers" if kind == "write" else "readers"].add(rel)
    return per_file, per_coll


def mongo_counts():
    try:
        from pymongo import MongoClient
        from dotenv import load_dotenv
        load_dotenv(ROOT / "backend" / ".env")
        db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=4000)[
            os.environ.get("DB_NAME", "test_database")]
        return db, {n: db[n].estimated_document_count() for n in db.list_collection_names()}
    except Exception as e:
        print(f"  !! mongo tidak terjangkau: {e}")
        return None, {}


def relation_fields(db, coll, limit=25):
    """Field relasi yang faktual ada di dokumen (bukan asumsi skema)."""
    if db is None:
        return {}
    keys = defaultdict(int)
    try:
        for d in db[coll].find({}, limit=limit):
            for k, v in d.items():
                if k == "_id":
                    continue
                lk = k.lower()
                if lk.endswith(("_id", "_ids", "_number", "_no", "_code", "_ref")) or lk in (
                        "po", "po_id", "po_number", "vendor", "vendor_id", "job_id",
                        "shipment_id", "parent_id", "child_ids", "source_id", "source"):
                    keys[k] += 1 if v not in (None, "", [], {}) else 0
    except Exception:
        pass
    return dict(keys)


def main():
    per_file, per_coll = scan()
    db, counts = mongo_counts()

    print("=" * 100)
    print("  FORENSIK SSOT — DOMAIN PRODUKSI / MAKLON / CMT / SHIPMENT")
    print("=" * 100)

    print(f"\n[1] File domain dipindai: {len(per_file)}   Collection tersentuh: {len(per_coll)}\n")

    print("-" * 100)
    print("[2] COLLECTION dengan LEBIH DARI SATU PENULIS (kandidat SSOT GANDA)")
    print("-" * 100)
    multi = {c: v for c, v in per_coll.items() if len(v["writers"]) > 1}
    for c in sorted(multi, key=lambda x: -len(per_coll[x]["writers"])):
        n = counts.get(c, "?")
        print(f"\n  ▸ {c}  (docs={n}, writers={len(multi[c]['writers'])})")
        for w in sorted(multi[c]["writers"]):
            print(f"      W  {w}")
        rd = sorted(multi[c]["readers"] - multi[c]["writers"])
        for r in rd[:8]:
            print(f"      r  {r}")
        if len(rd) > 8:
            print(f"      r  … +{len(rd) - 8} pembaca lain")

    print("\n" + "-" * 100)
    print("[3] COLLECTION KOSONG tapi masih ditulis/dibaca kode (kandidat alur MATI)")
    print("-" * 100)
    for c in sorted(per_coll):
        n = counts.get(c)
        if n == 0:
            print(f"  {c:<42} docs=0  W={len(per_coll[c]['writers'])} R={len(per_coll[c]['readers'])}"
                  f"  ← {', '.join(sorted(per_coll[c]['writers']))[:70]}")

    print("\n" + "-" * 100)
    print("[4] COLLECTION TAK ADA di DB sama sekali (typo / skema hantu)")
    print("-" * 100)
    for c in sorted(per_coll):
        if c not in counts:
            print(f"  {c:<42} TIDAK ADA  ← {', '.join(sorted(per_coll[c]['writers'] | per_coll[c]['readers']))[:80]}")

    print("\n" + "-" * 100)
    print("[5] PETA per FILE (write → read)")
    print("-" * 100)
    for f in sorted(per_file):
        w = sorted(per_file[f]["write"])
        r = sorted(per_file[f]["read"] - per_file[f]["write"])
        if not w and not r:
            continue
        print(f"\n  {f}")
        if w:
            print(f"     W: {', '.join(w)}")
        if r:
            print(f"     r: {', '.join(r)}")

    if "--json" in sys.argv:
        out = {
            "per_file": {k: {kk: sorted(vv) for kk, vv in v.items()} for k, v in per_file.items()},
            "per_coll": {k: {kk: sorted(vv) for kk, vv in v.items()} for k, v in per_coll.items()},
            "counts": counts,
        }
        p = ROOT / "docs" / "AUDIT_MAKLON_SSOT_RAW.json"
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(out, indent=1))
        print(f"\n  → JSON: {p}")


if __name__ == "__main__":
    main()
