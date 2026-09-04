#!/usr/bin/env python3
"""map_document_numbers.py — petakan SEMUA penghasil nomor dokumen & SKU.

Dijalankan SEBELUM menulis fitur penomoran terpusat (permintaan eksplisit owner:
"petakan dulu semua flow & koleksi terdampak, jangan sampai memunculkan bug baru").

Keluaran: tabel {koleksi, field, prefix, lebar, berkas:baris} + daftar pola
penomoran manual (f-string) yang TIDAK lewat generator race-safe.

    python3 scripts/map_document_numbers.py            # tabel ringkas
    python3 scripts/map_document_numbers.py --json     # untuk diproses lanjut
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "backend"

# gen_prefixed_number(db, "coll", "field", prefix_expr, width)
CALL_RE = re.compile(
    r"gen_prefixed_number\(\s*db\s*,\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*(.+?)\s*(?:,\s*(\d+)\s*)?\)",
    re.S,
)
# f"XX-{n:04d}" / f"XX-{seq:03d}" — penomoran manual (kandidat race)
MANUAL_RE = re.compile(r"f[\"'][^\"']*\{[a-z_]+:0?\d+d\}[^\"']*[\"']")
# Pola tanggal (YYYY-MM / YYYY-MM-DD) — bukan nomor dokumen, jangan dilaporkan.
DATEISH_RE = re.compile(r"^f[\"']\{?[a-z_]+[:}\d]*[\"'-]?\}?-\{[a-z_]+:0?\d+d\}(-\{[a-z_]+:0?\d+d\})?[\"']$")


def _clean(expr: str) -> str:
    return re.sub(r"\s+", " ", expr.strip().strip('"').strip("'"))


def scan() -> dict:
    calls, manual = [], []
    for path in sorted(BE.rglob("*.py")):
        if "_archive" in path.parts or "migrations" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(ROOT))
        for m in CALL_RE.finditer(text):
            line = text[:m.start()].count("\n") + 1
            calls.append({
                "collection": _clean(m.group(1)),
                "field": _clean(m.group(2)),
                "prefix": _clean(m.group(3)),
                "width": int(m.group(4)) if m.group(4) else 4,
                "where": f"{rel}:{line}",
            })
        if "gen_prefixed_number" not in text:
            for m in MANUAL_RE.finditer(text):
                frag = m.group(0)
                if DATEISH_RE.match(frag) or re.search(r"\{(y|m|mon|month|day|last_day|idx)[:}]", frag):
                    continue
                line = text[:m.start()].count("\n") + 1
                manual.append({"pattern": frag, "where": f"{rel}:{line}"})
    return {"generated": calls, "manual": manual}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    data = scan()

    if args.json:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=1)
        return

    print(f"\n{'='*100}\nPENGHASIL NOMOR RACE-SAFE (gen_prefixed_number) — {len(data['generated'])} pemanggilan\n{'='*100}")
    seen: dict[tuple, list] = {}
    for c in data["generated"]:
        seen.setdefault((c["collection"], c["field"]), []).append(c)
    print(f"{'KOLEKSI':<34} {'FIELD':<20} {'PREFIX':<34} W  N")
    print("-" * 100)
    for (coll, field), rows in sorted(seen.items()):
        p = rows[0]["prefix"][:33]
        print(f"{coll:<34} {field:<20} {p:<34} {rows[0]['width']}  {len(rows)}")
    print(f"\nTotal jenis dokumen unik (koleksi × field): {len(seen)}")

    print(f"\n{'='*100}\nPENOMORAN MANUAL DI LUAR GENERATOR — {len(data['manual'])} temuan\n{'='*100}")
    for m in data["manual"][:40]:
        print(f"  {m['where']:<60} {m['pattern'][:50]}")


if __name__ == "__main__":
    main()
