"""
SSOT Forensic Scanner PART 3 — fokus domain Marketing / RnD / WMS.

Non-destructif. Output ke /tmp/ssot_part3_raw.json (TIDAK menimpa SSOT_FORENSIC_RAW.json).

Sama seperti scanner utama tapi:
 - Menandai tiap koleksi ke DOMAIN (marketing/rnd/wms/other) berdasarkan file pembaca.
 - Fokus laporan pada 3 domain target.
"""
import asyncio
import json
import os
import re
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient

BACKEND = "/app/backend"
SCAN_DIRS = [os.path.join(BACKEND, "routes"), os.path.join(BACKEND, "services")]
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

READ_OPS = {"find", "find_one", "aggregate", "count_documents", "distinct", "estimated_document_count"}
WRITE_OPS = {"insert_one", "insert_many", "update_one", "update_many", "replace_one",
             "delete_one", "delete_many", "bulk_write", "find_one_and_update",
             "find_one_and_replace", "find_one_and_delete"}

RE_DOT = re.compile(r"\bdb\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_]+)\s*\(")
RE_BRACKET = re.compile(r"""\bdb\[\s*['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]\s*\]\.([a-zA-Z_]+)\s*\(""")

SEED_HINTS = ("seed", "demo_seed", "_seed", "admin_seed", "hr_seed", "demo")

def is_seed_file(fname: str) -> bool:
    base = os.path.basename(fname).lower()
    return any(h in base for h in SEED_HINTS)

def domain_of(fname: str) -> str:
    f = fname.lower()
    if any(k in f for k in ("market", "kol", "livehost", "live_", "toko", "creator", "product_launch")):
        return "marketing"
    if any(k in f for k in ("rnd", "style", "sample", "_bom", "pattern", "hpp", "costing")):
        return "rnd"
    if any(k in f for k in ("wms", "warehouse", "opname", "fabric", "putaway", "picklist",
                             "receiving", "delivery", "dispatch", "fg_label", "_wh_", "wh_")):
        return "wms"
    return "other"

def scan_code():
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
                        m[coll]["read_seed" if seed else "read_live"].add(fn)
                    elif op in WRITE_OPS:
                        m[coll]["write_seed" if seed else "write_live"].add(fn)
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

    # Domain of a collection = domain of its live readers (fallback: any file)
    rows = []
    for coll, u in sorted(codemap.items()):
        exists = coll in existing
        cnt = counts.get(coll, "N/A")
        live_readers = sorted(u["read_live"])
        all_files = sorted(u["read_live"] | u["write_live"] | u["write_seed"] | u["read_seed"])
        doms = {domain_of(f) for f in (live_readers or all_files)}
        doms.discard("other")
        domain = ",".join(sorted(doms)) if doms else "other"

        has_live_read = bool(u["read_live"])
        has_live_write = bool(u["write_live"])
        has_seed_write = bool(u["write_seed"])
        has_any_write = has_live_write or has_seed_write
        has_any_read = has_live_read or bool(u["read_seed"])

        flags = []
        if has_live_read and not exists:
            flags.append("PHANTOM")
        if has_live_read and has_seed_write and not has_live_write:
            flags.append("STALE_SSOT")
        if has_live_write and not has_any_read:
            flags.append("ORPHAN_WRITE")
        if exists and cnt == 0 and has_live_read:
            flags.append("EMPTY_BUT_READ")
        if has_live_read and not has_any_write:
            flags.append("READ_ONLY_NOSEED")

        rows.append({
            "collection": coll, "domain": domain, "exists": exists, "count": cnt,
            "flags": flags,
            "read_live": [os.path.splitext(x)[0] for x in live_readers],
            "write_live": [os.path.splitext(x)[0] for x in sorted(u["write_live"])],
            "write_seed": [os.path.splitext(x)[0] for x in sorted(u["write_seed"])],
        })

    with open("/tmp/ssot_part3_raw.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)

    # Report per target domain
    for target in ("marketing", "rnd", "wms"):
        subset = [r for r in rows if target in r["domain"].split(",") and r["flags"]]
        print(f"\n{'='*70}\n{target.upper()} — {len(subset)} koleksi ber-flag\n{'='*70}")
        for r in sorted(subset, key=lambda x: (x['flags'][0], x['collection'])):
            fl = "/".join(r["flags"])
            rl = ",".join(r["read_live"][:3])
            print(f"  {r['collection']:34s} cnt={str(r['count']):>5s} [{fl}]")
            print(f"       readers=[{rl}]")

asyncio.run(main())
