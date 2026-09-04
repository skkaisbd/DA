#!/usr/bin/env python3
"""
map_uom_impact.py
=================
Memetakan SELURUH titik di backend & frontend yang menyentuh satuan (UOM) dan
kuantitas material, sebagai prasyarat sebelum merombak struktur multi-satuan.

Tujuan: memastikan tidak ada flow yang terlewat (Produksi, RnD, Maklon, Cutting,
Gudang, Aksesoris, Finance/HPP, Marketing) sehingga perombakan tidak melahirkan
bug baru.

Output: docs/MAP_UOM_IMPACT.md
"""
from __future__ import annotations
import re
from collections import defaultdict
from pathlib import Path

BE = Path("/app/backend")
FE = Path("/app/frontend/src")
OUT = Path("/app/docs/MAP_UOM_IMPACT.md")

# ── Pola yang menandakan sentuhan ke satuan / konversi ───────────────────────
PATTERNS = {
    "baca_unit":      re.compile(r"""\.get\(\s*['"]unit['"]|\[\s*['"]unit['"]\s*\]|["']unit["']\s*:""" ),
    "unit_cost":      re.compile(r"""unit_cost"""),
    "pack":           re.compile(r"""pack_size|pack_unit|display_in_packs|input_unit"""),
    "uom_master":     re.compile(r"""wh_unit_master|wh_unit_conversions|units/convert"""),
    "stock_write":    re.compile(r"""stock_service\.(add|issue|adjust|move|issue_row)|_add_stock\(|inc_all_qty"""),
    "qty_field":      re.compile(r"""\bqty\b|qty_required|qty_requested|counted_qty|qty_received|planned_qty|qty_kg"""),
}

# ── Pemetaan file → domain bisnis ────────────────────────────────────────────
DOMAIN_RULES = [
    (re.compile(r"accessor", re.I),                       "Aksesoris"),
    (re.compile(r"cutting", re.I),                        "Cutting"),
    (re.compile(r"wms_|warehouse|inventory|putaway|opname|receiv|picklist|quarantine", re.I), "Gudang / WMS"),
    (re.compile(r"rnd|techpack|sample", re.I),            "RnD"),
    (re.compile(r"maklon|cmt", re.I),                     "Maklon / CMT"),
    (re.compile(r"production|prod_|work_order|wo_", re.I),"Produksi"),
    (re.compile(r"hpp|posting|journal|ap_|ar_|finance|coa|budget", re.I), "Finance / HPP"),
    (re.compile(r"marketing|kol|channel|toko", re.I),     "Marketing"),
    (re.compile(r"bom|material_requirement", re.I),       "BOM / MRP"),
    (re.compile(r"po\b|purchase|procure", re.I),          "Pengadaan"),
    (re.compile(r"fulfillment|shipment|delivery", re.I),  "Pengiriman"),
]


def domain_of(path: Path) -> str:
    name = path.name
    for rx, dom in DOMAIN_RULES:
        if rx.search(name):
            return dom
    return "Lain-lain"


COLL_RX = re.compile(r"db\.([a-z][a-z0-9_]{3,})")
ROUTE_RX = re.compile(r"""@router\.(get|post|put|patch|delete)\(\s*['"]([^'"]+)['"]""")
PREFIX_RX = re.compile(r"""APIRouter\([^)]*prefix\s*=\s*['"]([^'"]+)['"]""")


def scan_backend():
    rows = []
    for p in sorted(list(BE.glob("routes/*.py")) + list(BE.glob("core/*.py"))):
        try:
            src = p.read_text(errors="ignore")
        except Exception:
            continue
        hits = {k: len(rx.findall(src)) for k, rx in PATTERNS.items()}
        if not any(hits.values()):
            continue
        prefix = (PREFIX_RX.search(src) or [None, ""])[1]
        routes = [f"{m.group(1).upper()} {prefix}{m.group(2)}" for m in ROUTE_RX.finditer(src)]
        colls = sorted(set(COLL_RX.findall(src)))
        rows.append({
            "file": str(p.relative_to(BE)),
            "domain": domain_of(p),
            "hits": hits,
            "score": sum(hits.values()),
            "routes": routes,
            "colls": [c for c in colls if not c.startswith(("get_", "list_"))],
        })
    return rows


FE_PATTERNS = {
    "tampil_unit": re.compile(r"""\.unit\b|['"]unit['"]|satuan""", re.I),
    "pack":        re.compile(r"""pack_size|pack_unit|display_in_packs|input_unit"""),
    "qty":         re.compile(r"""\bqty\b|qty_required|counted_qty|jumlah""", re.I),
}


def scan_frontend():
    rows = []
    for p in sorted(FE.rglob("*.jsx")):
        if "/ui/" in str(p) or "_archive" in str(p):
            continue
        try:
            src = p.read_text(errors="ignore")
        except Exception:
            continue
        hits = {k: len(rx.findall(src)) for k, rx in FE_PATTERNS.items()}
        if hits["tampil_unit"] == 0 and hits["pack"] == 0:
            continue
        rows.append({
            "file": str(p.relative_to(FE)),
            "domain": domain_of(p),
            "hits": hits,
            "score": hits["tampil_unit"] + hits["pack"] * 5,
        })
    return rows


def main():
    be = scan_backend()
    fe = scan_frontend()

    by_dom_be = defaultdict(list)
    for r in be:
        by_dom_be[r["domain"]].append(r)
    by_dom_fe = defaultdict(list)
    for r in fe:
        by_dom_fe[r["domain"]].append(r)

    L = []
    L.append("# Peta Dampak Perombakan Satuan (UOM)\n")
    L.append("Dihasilkan otomatis oleh `scripts/map_uom_impact.py`.\n")
    L.append("Dipakai sebagai daftar periksa agar perombakan multi-satuan tidak ")
    L.append("melahirkan bug baru di domain lain.\n\n")

    L.append("## Ringkasan\n\n")
    L.append(f"- File backend tersentuh: **{len(be)}**\n")
    L.append(f"- File frontend tersentuh: **{len(fe)}**\n")
    L.append(f"- Domain terdampak: **{len(set(list(by_dom_be) + list(by_dom_fe)))}**\n\n")

    L.append("| Domain | File BE | File FE | Titik tulis stok | Sudah sadar pack |\n")
    L.append("|---|---:|---:|---:|---:|\n")
    for dom in sorted(set(list(by_dom_be) + list(by_dom_fe))):
        b = by_dom_be.get(dom, [])
        f = by_dom_fe.get(dom, [])
        sw = sum(r["hits"]["stock_write"] for r in b)
        pk = sum(1 for r in b if r["hits"]["pack"]) + sum(1 for r in f if r["hits"]["pack"])
        L.append(f"| {dom} | {len(b)} | {len(f)} | {sw} | {pk} |\n")
    L.append("\n")

    L.append("## Backend — rinci per domain\n\n")
    for dom in sorted(by_dom_be):
        rows = sorted(by_dom_be[dom], key=lambda r: -r["score"])
        L.append(f"### {dom}\n\n")
        L.append("| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |\n")
        L.append("|---|---:|---:|---:|---:|---:|---|\n")
        for r in rows:
            h = r["hits"]
            pack = "**" + str(h["pack"]) + "**" if h["pack"] else "0"
            colls = ", ".join(f"`{c}`" for c in r["colls"][:5]) or "—"
            L.append(f"| `{r['file']}` | {h['baca_unit']} | {h['unit_cost']} | {pack} | "
                     f"{h['stock_write']} | {h['qty_field']} | {colls} |\n")
        L.append("\n")

    L.append("## Frontend — rinci per domain\n\n")
    for dom in sorted(by_dom_fe):
        rows = sorted(by_dom_fe[dom], key=lambda r: -r["score"])[:25]
        L.append(f"### {dom}  ({len(by_dom_fe[dom])} file)\n\n")
        L.append("| File | tampil satuan | pack-aware | qty |\n|---|---:|---:|---:|\n")
        for r in rows:
            h = r["hits"]
            pack = "**" + str(h["pack"]) + "**" if h["pack"] else "0"
            L.append(f"| `{r['file']}` | {h['tampil_unit']} | {pack} | {h['qty']} |\n")
        L.append("\n")

    OUT.write_text("".join(L))
    print(f"[map] ditulis ke {OUT}")
    print(f"[map] backend {len(be)} file, frontend {len(fe)} file")
    tot_sw = sum(r["hits"]["stock_write"] for r in be)
    pack_aware = sum(1 for r in be if r["hits"]["pack"])
    print(f"[map] titik tulis stok: {tot_sw} | file BE yang sudah pack-aware: {pack_aware}/{len(be)}")


if __name__ == "__main__":
    main()
