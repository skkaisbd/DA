"""STEP D2 — Classify all phantom/empty collections referenced in code (read-only).
For each collection referenced in routes/ or services/:
  - detect READERS (find/find_one/aggregate/count_documents/distinct) per file
  - detect WRITERS (insert_one/insert_many/update_one/update_many/replace_one/bulk_write/find_one_and_update) per file
Classify:
  SELF_CONSISTENT  -> some file both reads & writes (or same module family) => dormant if empty
  READ_ONLY        -> readers but NO writer anywhere => dead-read / misroute candidate
  WRITE_ONLY       -> writers but no reader => orphan write
Cross-ref READ_ONLY collections with populated "twin" collections (similar name, count>0).
"""
import os, re, json
from collections import defaultdict
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from pymongo import MongoClient

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"].strip('"')]
COLLS = {c: db[c].estimated_document_count() for c in db.list_collection_names()}

READ_OPS = r"(?:find|find_one|aggregate|count_documents|estimated_document_count|distinct)"
WRITE_OPS = r"(?:insert_one|insert_many|update_one|update_many|replace_one|bulk_write|find_one_and_update|find_one_and_replace|delete_one|delete_many)"

pat_read = re.compile(r"db\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\.\s*" + READ_OPS)
pat_write = re.compile(r"db\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\.\s*" + WRITE_OPS)
pat_read_br = re.compile(r"db\[[\"']([a-zA-Z_][a-zA-Z0-9_]*)[\"']\]\s*\.\s*" + READ_OPS)
pat_write_br = re.compile(r"db\[[\"']([a-zA-Z_][a-zA-Z0-9_]*)[\"']\]\s*\.\s*" + WRITE_OPS)

readers = defaultdict(set)
writers = defaultdict(set)
SEED_FILES = {"production_seed_full", "dewi_demo_seed", "rahaza_demo_seed", "rahaza_admin_seed",
              "rahaza_hr_seed", "dewi_cmt_seed", "vendor_portal_seed", "fg_matrix_seed",
              "seed_marketing_demo", "seed_expense_categories"}

for base in ("/app/backend/routes", "/app/backend/services", "/app/backend/utils"):
    for root, _, files in os.walk(base):
        if "__pycache__" in root or "_archive" in root:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            mod = f[:-3]
            src = open(os.path.join(root, f), encoding="utf-8", errors="replace").read()
            for m in pat_read.finditer(src): readers[m.group(1)].add(mod)
            for m in pat_read_br.finditer(src): readers[m.group(1)].add(mod)
            for m in pat_write.finditer(src): writers[m.group(1)].add(mod)
            for m in pat_write_br.finditer(src): writers[m.group(1)].add(mod)

all_colls = set(readers) | set(writers)
report = {"READ_ONLY_EMPTY": [], "SELF_CONSISTENT_EMPTY": [], "WRITE_ONLY": [], "OK": []}

def twins(name, limit=4):
    """populated collections with similar naming"""
    toks = [t for t in re.split(r"_", name) if len(t) > 3 and t not in ("dewi", "rahaza", "marketing", "wms")]
    out = []
    for c, cnt in COLLS.items():
        if c == name or cnt == 0: continue
        score = sum(1 for t in toks if t.rstrip("s") in c)
        if score >= max(1, len(toks) - 1):
            out.append(f"{c}({cnt})")
    return out[:limit]

for coll in sorted(all_colls):
    cnt = COLLS.get(coll, "MISSING")
    empty = (cnt == "MISSING" or cnt == 0)
    r, w = readers.get(coll, set()), writers.get(coll, set())
    live_w = w - SEED_FILES
    if not empty:
        report["OK"].append((coll, cnt))
        continue
    if r and not live_w and not (w & SEED_FILES):
        report["READ_ONLY_EMPTY"].append({"coll": coll, "cnt": str(cnt), "readers": sorted(r), "twins": twins(coll)})
    elif r and not live_w and (w & SEED_FILES):
        report["READ_ONLY_EMPTY"].append({"coll": coll, "cnt": str(cnt), "readers": sorted(r), "twins": twins(coll), "note": "seed-writer-only:" + ",".join(sorted(w & SEED_FILES))})
    elif r and live_w:
        report["SELF_CONSISTENT_EMPTY"].append({"coll": coll, "cnt": str(cnt), "rw_overlap": sorted(r & live_w), "readers": sorted(r)[:5], "writers": sorted(live_w)[:5]})
    elif live_w and not r:
        report["WRITE_ONLY"].append({"coll": coll, "cnt": str(cnt), "writers": sorted(live_w)})

print(f"populated={len(report['OK'])}  read_only_empty={len(report['READ_ONLY_EMPTY'])}  self_consistent_empty={len(report['SELF_CONSISTENT_EMPTY'])}  write_only={len(report['WRITE_ONLY'])}")
print("\n===== READ-ONLY EMPTY (dead-read / MISROUTE candidates) =====")
for it in report["READ_ONLY_EMPTY"]:
    tw = " | twins: " + ", ".join(it["twins"]) if it["twins"] else ""
    nt = " [" + it.get("note", "") + "]" if it.get("note") else ""
    print(f"  {it['coll']:38s} readers={','.join(it['readers'][:5])}{tw}{nt}")
print("\n===== SELF-CONSISTENT but EMPTY (dormant — DO NOT repoint) =====")
for it in report["SELF_CONSISTENT_EMPTY"]:
    print(f"  {it['coll']:38s} rw_overlap={','.join(it['rw_overlap'][:4])}")
print("\n===== WRITE-ONLY (orphan writes) =====")
for it in report["WRITE_ONLY"]:
    print(f"  {it['coll']:38s} writers={','.join(it['writers'][:5])}")
json.dump(report, open("/tmp/d2_phantom_report.json", "w"), indent=1, default=list)
