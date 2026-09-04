"""Ukur seberapa baik mesin impor mengenali 7 berkas ekspor NYATA (samples/marketplace_2026).

Untuk setiap berkas: coba SEMUA source type, hitung cakupan pemetaan (berapa field
kanonik yang ketemu / berapa kolom berkas terpakai), lalu urutkan. Output dipakai
untuk memutuskan (a) apakah deteksi otomatis mungkin, (b) sinonim apa yang hilang.
"""
import os
import sys
sys.path.insert(0, "/app/backend")

from core.marketing_import_schema import source_type_catalog, get_source_type  # noqa
from core import marketing_import_engine as eng  # noqa

DIR = "/app/samples/marketplace_2026"


def score(headers, st):
    mapping = eng.auto_map(headers, st)
    mapped = [m for m in mapping if m.get("field")]
    req = [f for f in st.input_fields if f.required]
    req_hit = [f for f in req if any(m.get("field") == f.name for m in mapped)]
    return {
        "type": st.key,
        "mapped_cols": len(mapped),
        "total_cols": len(headers),
        "req_hit": len(req_hit),
        "req_total": len(req),
        "req_missing": [f.name for f in req if f.name not in {m["field"] for m in mapped}],
        "cover": (len(mapped) / max(1, len(headers))),
        "req_cover": (len(req_hit) / max(1, len(req))),
    }


def main():
    cats = [get_source_type(t["key"]) for t in source_type_catalog()]
    for fn in sorted(os.listdir(DIR)):
        path = os.path.join(DIR, fn)
        raw = open(path, "rb").read()
        print("=" * 100)
        print(f"FILE: {fn}  ({len(raw)/1024:.0f} KB)")
        try:
            headers, rows = eng.parse_table(raw, fn, cats[0])
        except Exception as e:
            print(f"  !! parse_table GAGAL: {type(e).__name__}: {e}")
            continue
        print(f"  headers({len(headers)}): {headers[:18]}")
        if rows:
            r0 = rows[0]
            print(f"  row0 sample: {dict(list(r0.items())[:8])}")
        res = sorted((score(headers, st) for st in cats),
                     key=lambda r: (r["req_cover"], r["cover"]), reverse=True)
        for r in res[:4]:
            print(f"   - {r['type']:<24} req {r['req_hit']}/{r['req_total']}  "
                  f"cols {r['mapped_cols']}/{r['total_cols']}  missing={r['req_missing'][:6]}")


if __name__ == "__main__":
    main()
