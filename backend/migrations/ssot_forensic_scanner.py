"""
SSOT Forensic Scanner (Session #12) — deteksi masalah SSOT/logic secara sistematis.

Memetakan setiap koleksi MongoDB <-> pembaca/penulis di kode (routes/ + services/),
memisahkan penulis SEED vs LIVE, lalu cross-reference dengan keberadaan koleksi di DB.

Klasifikasi:
  PHANTOM        : koleksi di-READ oleh kode tapi TIDAK ADA di DB (mis. dewi_attendance).
  STALE_SSOT     : punya LIVE reader, tapi WRITER hanya file SEED (mis. rahaza_attendance).
  ORPHAN_WRITE   : ditulis LIVE tapi tidak pernah dibaca (dead write).
  EMPTY_BUT_READ : ada di DB tapi KOSONG & dibaca live code (perlu cek apakah wajar).
  READ_ONLY_NOSEED: dibaca live, tidak ada writer sama sekali di kode (data eksternal/seed lain).

Read-only, tidak mengubah apa pun. Output: ringkasan + /app/SSOT_FORENSIC_RAW.json
"""
import asyncio
import json
import os
import re
from collections import defaultdict

from motor.motor_asyncio import AsyncIOMotorClient

BACKEND = "/app/backend"
SCAN_DIRS = [os.path.join(BACKEND, "routes"), os.path.join(BACKEND, "services")]
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

READ_OPS = {"find", "find_one", "aggregate", "count_documents", "distinct", "estimated_document_count"}
WRITE_OPS = {"insert_one", "insert_many", "update_one", "update_many", "replace_one",
             "delete_one", "delete_many", "bulk_write", "find_one_and_update",
             "find_one_and_replace", "find_one_and_delete"}

# db.<coll>.<op>(   and   db["<coll>"]  /  db['<coll>']
RE_DOT = re.compile(r"\bdb\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_]+)\s*\(")
RE_BRACKET = re.compile(r"""\bdb\[\s*['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]\s*\]\.([a-zA-Z_]+)\s*\(""")

SEED_HINTS = ("seed", "demo_seed", "_seed", "admin_seed", "hr_seed", "demo")


def is_seed_file(fname: str) -> bool:
    base = os.path.basename(fname).lower()
    return any(h in base for h in SEED_HINTS)


def scan_code():
    # coll -> {'read_live':set,'read_seed':set,'write_live':set,'write_seed':set}
    m = defaultdict(lambda: {"read_live": set(), "read_seed": set(),
                             "write_live": set(), "write_seed": set()})
    for d in SCAN_DIRS:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(d, fn)
            try:
                txt = open(path, encoding="utf-8").read()
            except Exception:
                continue
            seed = is_seed_file(fn)
            for rx in (RE_DOT, RE_BRACKET):
                for coll, op in rx.findall(txt):
                    if op in READ_OPS:
                        key = "read_seed" if seed else "read_live"
                        m[coll][key].add(fn)
                    elif op in WRITE_OPS:
                        key = "write_seed" if seed else "write_live"
                        m[coll][key].add(fn)
    return m


async def main():
    codemap = scan_code()
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    existing = set(await db.list_collection_names())
    counts = {}
    for c in existing:
        try:
            counts[c] = await db[c].count_documents({})
        except Exception:
            counts[c] = -1

    findings = {"PHANTOM": [], "STALE_SSOT": [], "ORPHAN_WRITE": [],
                "EMPTY_BUT_READ": [], "READ_ONLY_NOSEED": []}

    for coll, u in sorted(codemap.items()):
        exists = coll in existing
        cnt = counts.get(coll, "N/A")
        has_live_read = bool(u["read_live"])
        has_live_write = bool(u["write_live"])
        has_seed_write = bool(u["write_seed"])
        has_any_write = has_live_write or has_seed_write
        has_any_read = has_live_read or bool(u["read_seed"])

        rec = {
            "collection": coll, "exists": exists, "count": cnt,
            "read_live": sorted(u["read_live"]), "write_live": sorted(u["write_live"]),
            "write_seed": sorted(u["write_seed"]), "read_seed": sorted(u["read_seed"]),
        }

        # PHANTOM: read by live code but doesn't exist in DB
        if has_live_read and not exists:
            findings["PHANTOM"].append(rec)
        # STALE_SSOT: live readers present, but only SEED writes it (no live writer)
        if has_live_read and has_seed_write and not has_live_write:
            findings["STALE_SSOT"].append(rec)
        # ORPHAN_WRITE: live-written but never read anywhere
        if has_live_write and not has_any_read:
            findings["ORPHAN_WRITE"].append(rec)
        # EMPTY_BUT_READ: exists, empty, read by live code
        if exists and cnt == 0 and has_live_read:
            findings["EMPTY_BUT_READ"].append(rec)
        # READ_ONLY_NOSEED: read live, no writer at all in code
        if has_live_read and not has_any_write:
            findings["READ_ONLY_NOSEED"].append(rec)

    # Output
    with open("/app/SSOT_FORENSIC_RAW.json", "w", encoding="utf-8") as f:
        json.dump({"findings": findings,
                   "total_collections_in_code": len(codemap),
                   "total_collections_in_db": len(existing)}, f, indent=2)

    print(f"Koleksi dirujuk di kode: {len(codemap)} | Koleksi di DB: {len(existing)}")
    for cat in ["PHANTOM", "STALE_SSOT", "ORPHAN_WRITE", "EMPTY_BUT_READ"]:
        items = findings[cat]
        print(f"\n===== {cat} ({len(items)}) =====")
        for r in items:
            rl = ",".join(os.path.splitext(x)[0] for x in r["read_live"][:4])
            ws = ",".join(os.path.splitext(x)[0] for x in r["write_seed"][:3])
            print(f"  {r['collection']:38s} exists={str(r['exists']):5s} cnt={str(r['count']):>5s}"
                  f" | read_live=[{rl}] write_seed=[{ws}]")
    print(f"\nREAD_ONLY_NOSEED count: {len(findings['READ_ONLY_NOSEED'])} (lihat JSON untuk detail)")


if __name__ == "__main__":
    asyncio.run(main())
