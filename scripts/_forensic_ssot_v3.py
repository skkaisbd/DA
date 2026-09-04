#!/usr/bin/env python3
"""_forensic_ssot_v3.py — FORENSIK SSOT MENYELURUH (READ-ONLY, statik + DB).

Kenapa alat ini ada
-------------------
Owner melaporkan: "database, collection dan field yang di panggil ini miss semua …
seperti fitur yang berdiri sendiri lupa hubunganya dengan api lain … dan duplikasi".
Klaim seperti itu tidak boleh dijawab dengan opini. Alat ini menghitungnya:

  A. MATRIKS AKSES  — untuk SETIAP koleksi: siapa MENULIS, siapa MEMBACA (file:line).
                      Menemukan: koleksi ditulis-tak-pernah-dibaca (data masuk kubur),
                      dibaca-tak-pernah-ditulis (layar selalu kosong), dan
                      "pulau" (hanya 1 berkas yang menyentuh = fitur berdiri sendiri).
  B. KONTRAK FIELD  — field yang DIBACA (agregasi `$x`, filter, projeksi) tetapi
                      TIDAK PERNAH DITULIS oleh penulis koleksi yang sama ⇒ nol sunyi.
  C. DUPLIKASI      — koleksi berbeda untuk konsep yang sama (token nama mirip),
                      koleksi di kode tapi tak ada di DB, dan sebaliknya.
  D. IMPOR TERPADU  — daftar jenis impor resmi vs koleksi tujuan vs apakah koleksi
                      tujuan itu benar-benar dibaca oleh endpoint.

Output: /app/memory/FORENSIC_SSOT_V3.json  + ringkasan ke stdout.
Tidak menulis ke MongoDB. Tidak mengubah berkas aplikasi.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

APP = Path("/app")
BE = APP / "backend"
SKIP_DIR_PARTS = {"__pycache__", "node_modules", "tests", "test", "legacy", "migrations", "scripts"}

WRITE_OPS = {"insert_one", "insert_many", "update_one", "update_many", "replace_one",
             "delete_one", "delete_many", "find_one_and_update", "find_one_and_replace",
             "find_one_and_delete", "bulk_write", "create_index", "drop"}
READ_OPS = {"find", "find_one", "aggregate", "count_documents", "distinct",
            "estimated_document_count"}

# db.<coll>.<op>(   |   db["<coll>"].<op>(   |   db[CONST].<op>(
RE_ACCESS = re.compile(
    r"""db\s*(?:
            \.\s*(?P<attr>[A-Za-z_][A-Za-z0-9_]*)
          | \[\s*['"](?P<lit>[A-Za-z_][A-Za-z0-9_]*)['"]\s*\]
          | \[\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*\]
        )\s*\.\s*(?P<op>[a-z_]+)\s*\(""",
    re.X,
)
RE_CONST = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*['\"]([a-z][a-z0-9_]*)['\"]\s*$", re.M)
RE_DOLLAR_FIELD = re.compile(r"['\"]\$([a-zA-Z_][a-zA-Z0-9_.]*)['\"]")
RE_DICT_KEY = re.compile(r"['\"]([a-zA-Z_][a-zA-Z0-9_.]*)['\"]\s*:")
NON_FIELD = {"$sum", "$avg", "$min", "$max", "$push", "$set", "$inc", "$group", "$match"}


def py_files():
    for p in sorted(BE.rglob("*.py")):
        parts = set(p.parts)
        if parts & SKIP_DIR_PARTS:
            continue
        if p.name.startswith("test_") or p.name.endswith("_test.py"):
            continue
        yield p


def block_after(text: str, start: int, max_chars: int = 900) -> str:
    """Ambil potongan teks setelah posisi `start` (perkiraan argumen operasi)."""
    return text[start:start + max_chars]


def main():
    access = defaultdict(lambda: {"writers": [], "readers": []})
    write_fields = defaultdict(set)
    read_fields = defaultdict(set)
    file_touch = defaultdict(set)  # coll -> {files}

    for p in py_files():
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        consts = dict((m.group(1), m.group(2)) for m in RE_CONST.finditer(text))
        rel = str(p.relative_to(APP))
        for m in RE_ACCESS.finditer(text):
            coll = m.group("attr") or m.group("lit")
            if not coll and m.group("var"):
                coll = consts.get(m.group("var"))
            if not coll:
                continue
            if coll in {"client", "command", "list_collection_names", "get_collection",
                        "name", "db", "admin"}:
                continue
            op = m.group("op")
            line = text.count("\n", 0, m.start()) + 1
            blk = block_after(text, m.end())
            if op in WRITE_OPS:
                if op not in {"create_index", "drop"}:
                    access[coll]["writers"].append(f"{rel}:{line}:{op}")
                    file_touch[coll].add(rel)
                    for k in RE_DICT_KEY.findall(blk):
                        if not k.startswith("$"):
                            write_fields[coll].add(k.split(".")[0])
            elif op in READ_OPS:
                access[coll]["readers"].append(f"{rel}:{line}:{op}")
                file_touch[coll].add(rel)
                for f in RE_DOLLAR_FIELD.findall(blk):
                    if f not in NON_FIELD:
                        read_fields[coll].add(f.split(".")[0])
                for k in RE_DICT_KEY.findall(blk):
                    if not k.startswith("$"):
                        read_fields[coll].add(k.split(".")[0])

    # ── DB state ──────────────────────────────────────────────────────────────
    db_counts = {}
    try:
        from pymongo import MongoClient
        cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
                          serverSelectionTimeoutMS=3000)
        d = cli[os.environ.get("DB_NAME", "test_database")]
        for n in d.list_collection_names():
            db_counts[n] = d[n].estimated_document_count()
    except Exception as e:  # pragma: no cover
        print(f"[warn] Mongo tidak terbaca: {e}")

    code_colls = set(access)
    only_written = sorted(c for c in code_colls if access[c]["writers"] and not access[c]["readers"])
    only_read = sorted(c for c in code_colls if access[c]["readers"] and not access[c]["writers"])
    islands = sorted(c for c in code_colls if len(file_touch[c]) == 1)
    in_db_not_code = sorted(set(db_counts) - code_colls)
    in_code_not_db = sorted(c for c in code_colls - set(db_counts))

    # ── duplikasi konsep (token nama) ─────────────────────────────────────────
    def tokens(name: str):
        t = [x for x in name.split("_") if x not in {"marketing", "rahaza", "dewi", "wh", "acc"}]
        # samakan bentuk tunggal/jamak sederhana
        return tuple(sorted(x[:-1] if x.endswith("s") and len(x) > 4 else x for x in t))

    by_tok = defaultdict(list)
    for c in sorted(code_colls | set(db_counts)):
        by_tok[tokens(c)].append(c)
    dup_exact = {"_".join(k): v for k, v in by_tok.items() if len(v) > 1}

    # kemiripan sebagian (satu nama superset token yang lain)
    dup_partial = []
    names = sorted(code_colls | set(db_counts))
    for i, a in enumerate(names):
        ta = set(tokens(a))
        for b in names[i + 1:]:
            tb = set(tokens(b))
            if not ta or not tb or ta == tb:
                continue
            if ta < tb or tb < ta:
                dup_partial.append([a, b])

    # ── field dibaca tapi tak pernah ditulis ─────────────────────────────────
    field_gaps = {}
    for c in sorted(code_colls):
        if not access[c]["writers"]:
            continue
        gaps = sorted(f for f in read_fields[c] - write_fields[c]
                      if not f.startswith("_") and len(f) > 2)
        if gaps:
            field_gaps[c] = gaps

    # ── impor terpadu: jenis → koleksi → dibaca? ─────────────────────────────
    import_types = []
    sys.path.insert(0, str(BE))
    try:
        from core.marketing_import_schema import SOURCE_TYPES  # type: ignore
        for t in SOURCE_TYPES.values():
            coll = t.collection
            import_types.append({
                "key": t.key, "label": t.label, "group": t.group, "collection": coll,
                "account_scope": t.account_scope, "context": list(t.context),
                "dedupe": list(t.dedupe), "module_hint": t.module_hint,
                "n_fields": len(t.fields),
                "n_input_fields": len(t.input_fields),
                "collection_readers": len(access.get(coll, {}).get("readers", [])),
                "collection_writers": len(access.get(coll, {}).get("writers", [])),
                "in_db": coll in db_counts,
                "db_docs": db_counts.get(coll, 0),
            })
    except Exception as e:
        print(f"[warn] schema impor tidak terbaca: {e}")

    out = {
        "generated_by": "scripts/_forensic_ssot_v3.py",
        "totals": {
            "collections_in_code": len(code_colls),
            "collections_in_db": len(db_counts),
            "written_never_read": len(only_written),
            "read_never_written": len(only_read),
            "single_file_islands": len(islands),
            "dup_same_tokens": len(dup_exact),
            "dup_partial_pairs": len(dup_partial),
            "collections_with_field_gaps": len(field_gaps),
        },
        "written_never_read": only_written,
        "read_never_written": only_read,
        "single_file_islands": islands,
        "in_db_not_in_code": in_db_not_code,
        "in_code_not_in_db": in_code_not_db,
        "dup_same_tokens": dup_exact,
        "dup_partial_pairs": dup_partial,
        "field_read_never_written": field_gaps,
        "import_types": import_types,
        "access": {c: {"writers": v["writers"], "readers": v["readers"],
                       "files": sorted(file_touch[c])}
                   for c, v in sorted(access.items())},
        "db_counts": db_counts,
    }
    dest = APP / "memory" / "FORENSIC_SSOT_V3.json"
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False))

    B = "\033[1m"; R = "\033[91m"; G = "\033[92m"; Y = "\033[93m"; E = "\033[0m"
    print(f"\n{B}FORENSIK SSOT v3{E} → {dest}")
    for k, v in out["totals"].items():
        print(f"  {k:34s} {v}")
    print(f"\n{B}A. DITULIS TAPI TIDAK PERNAH DIBACA{E} ({len(only_written)}) — data masuk kubur")
    for c in only_written:
        print(f"  {R}{c}{E}  ({db_counts.get(c, '—')} dok)  penulis: {access[c]['writers'][:2]}")
    print(f"\n{B}B. DIBACA TAPI TIDAK PERNAH DITULIS{E} ({len(only_read)}) — layar selalu kosong")
    for c in only_read:
        print(f"  {Y}{c}{E}  ({db_counts.get(c, '—')} dok)  pembaca: {access[c]['readers'][:2]}")
    print(f"\n{B}C. DUPLIKASI KONSEP — token nama sama{E}")
    for k, v in dup_exact.items():
        print(f"  {R}{k}{E}: {v}")
    print(f"\n{B}D. KOLEKSI DI KODE TAPI TIDAK ADA DI DB{E} ({len(in_code_not_db)})")
    print("  " + ", ".join(in_code_not_db[:40]))
    print(f"\n{B}E. KOLEKSI DI DB TAPI TIDAK DISENTUH KODE{E} ({len(in_db_not_code)})")
    print("  " + ", ".join(in_db_not_code[:40]))
    print(f"\n{B}F. IMPOR TERPADU — jenis → koleksi → pembaca{E}")
    print(f"  {'key':26s} {'collection':34s} {'pembaca':>7s} {'penulis':>7s} {'dok':>5s}")
    for t in import_types:
        flag = R + " ← TIDAK DIBACA" + E if t["collection_readers"] == 0 else ""
        print(f"  {t['key']:26s} {t['collection']:34s} {t['collection_readers']:7d} "
              f"{t['collection_writers']:7d} {t['db_docs']:5d}{flag}")
    print(f"\n{G}selesai — nol penulisan ke DB / berkas aplikasi{E}")


if __name__ == "__main__":
    main()
