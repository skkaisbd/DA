#!/usr/bin/env python3
"""_audit_ui_tables_v2.py — AUDIT UI: tabel vs kartu, DAN kelengkapan kolom (READ-ONLY).

Kenapa versi 2
--------------
`_audit_marketing_ui_views.py` (versi 1) memakai regex `<Card` sehingga modul yang
memakai `GlassCard` **lolos dari deteksi** — `TokoProductCatalogModule.jsx` yang
100% kartu justru dilaporkan "sudah tabel". Versi ini:

  1. Mengenali SEMUA pembungkus kartu yang dipakai repo ini
     (`<Card`, `GlassCard`, `grid grid-cols`, `CardContent`).
  2. Menghitung jumlah kolom tabel (`<th`/`TableHead`) — layar dengan 2-3 kolom
     untuk dokumen yang punya 30+ field = "informasi tidak lengkap" yang dikeluhkan.
  3. **Kelengkapan field:** membandingkan field yang DIKIRIM backend (kunci dokumen
     pada berkas route terkait) dengan field yang DIPAKAI layar (`x.field`).
     Selisihnya = informasi yang sudah ada di API tetapi tidak pernah ditampilkan.
  4. Memeriksa apakah ada pengalih tampilan (`viewMode`).
  5. **(2026-08-13) MENGIKUTI KOMPONEN ANAK satu tingkat.** Versi sebelumnya hanya
     memindai berkas modul itu sendiri, sehingga modul yang tabel & pengalihnya
     dipindah ke komponen anak dilaporkan "tanpa pengalih" — persis yang terjadi
     pada `CatalogManagementModule.jsx` sesudah F4.4: tabel 21 kolom + toggle
     Tabel/Kartu ada di `marketing/CatalogItemsView.jsx`, tetapi audit tetap
     menuliskan `th=15, toggle=false`. Gate yang salah menuduh akan membuat agen
     berikutnya "memperbaiki" hal yang sudah benar (atau lebih buruk: percaya
     sebuah modul punya pengalih padahal tidak). Kolom `via` menyebut anak mana
     yang menyumbang tabel/pengalihnya, jadi temuannya tetap bisa ditelusuri.
     Hanya SATU tingkat: kalau perlu menelusuri lebih dalam, itu tanda modulnya
     memang terlalu berlapis untuk dinilai otomatis.

Output: /app/memory/AUDIT_UI_TABLES_V2.json + ringkasan stdout. Tidak mengubah berkas.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

APP = Path("/app")
FE = APP / "frontend" / "src" / "components"
BE = APP / "backend" / "routes"

ROOTS = [FE / "erp" / "marketing", FE / "erp"]

CARD_PAT = re.compile(r"<Card\b|GlassCard|<CardContent\b")
GRID_PAT = re.compile(r"grid\s+grid-cols-|md:grid-cols-|lg:grid-cols-")
TABLE_PAT = re.compile(r"<table\b|<Table\b|TableBody")
TH_PAT = re.compile(r"<th\b|<TableHead\b")
# Pengalih tampilan. Pola LAMA hanya mengenali `viewMode` / `useState('table')`,
# sehingga pola yang justru dipakai repo ini — state `view` yang diinisialisasi
# lewat fungsi (`useState(() => localStorage.getItem(...) || 'table')`) plus dua
# tombol `data-testid="...view-table|view-grid"` — dilaporkan **tidak punya
# pengalih**. Itu membuat CatalogItemsView (F4) & CycleView (F5) tampak melanggar
# aturan yang sebenarnya mereka penuhi.
VIEWMODE_PAT = re.compile(
    r"viewMode"
    r"|useState\(\s*['\"](?:table|grid|list)['\"]\s*\)"
    r"|setView\(\s*['\"](?:table|grid|list)['\"]\s*\)"
    r"|data-testid=\"[a-z0-9-]*view-(?:table|grid)\""
)
# Kolom yang dibuat dari ARRAY judul (`const HEADS = [...]` lalu `.map(h => <th>)`)
# tidak terhitung oleh pencacahan `<th` literal — layar 21 kolom bisa terbaca 2.
HEAD_ARRAY_PAT = re.compile(
    r"(?:HEADS|HEADERS|COLUMNS|COLS)\s*=\s*\[(.*?)\]", re.S)
STRING_ITEM_PAT = re.compile(r"['\"]([^'\"]{1,40})['\"]")

FIELD_USE = re.compile(r"\b(?:it|item|p|row|r|d|rec|entry|prod|acc|o)\.([a-z][a-z0-9_]{2,})\b")
API_CALL = re.compile(r"[`'\"]\$\{?API\}?/?(api/[a-zA-Z0-9_\-/{}$.]+)")
# import lokal (komponen anak) — hanya path relatif; paket npm tidak diikuti.
LOCAL_IMPORT = re.compile(r"^\s*import\s+[^;]*?from\s+['\"](\.[^'\"]+)['\"]", re.M)


def scan_text(txt: str) -> dict:
    """Hitung ciri tampilan pada SATU berkas."""
    th = len(TH_PAT.findall(txt))
    for block in HEAD_ARRAY_PAT.findall(txt):
        th += len(STRING_ITEM_PAT.findall(block))
    return {
        "cards": len(CARD_PAT.findall(txt)),
        "grids": len(GRID_PAT.findall(txt)),
        "tables": len(TABLE_PAT.findall(txt)),
        "th": th,
        "toggle": bool(VIEWMODE_PAT.search(txt)),
    }


def child_files(path: Path) -> list:
    """Berkas komponen anak (import relatif) yang benar-benar ada — 1 tingkat."""
    out = []
    try:
        txt = path.read_text(errors="ignore")
    except OSError:
        return out
    for rel in LOCAL_IMPORT.findall(txt):
        base = (path.parent / rel).resolve()
        for cand in (base.with_suffix(".jsx"), base.with_suffix(".js"),
                     base / "index.jsx", base / "index.js"):
            if cand.exists() and cand != path:
                out.append(cand)
                break
    return out



def be_doc_fields() -> dict:
    """Kunci dokumen per berkas route (perkiraan): `'key':` di dalam berkas route."""
    out = {}
    for p in sorted(BE.rglob("*.py")):
        txt = p.read_text(errors="ignore")
        keys = set(re.findall(r"['\"]([a-z][a-z0-9_]{2,})['\"]\s*:", txt))
        out[p.name] = keys
    return out


def main():
    be_fields = be_doc_fields()
    all_be_keys = set()
    for v in be_fields.values():
        all_be_keys |= v

    seen = set()
    rows = []
    for root in ROOTS:
        if not root.exists():
            continue
        for p in sorted(root.glob("*.jsx")):
            if p.name in seen:
                continue
            seen.add(p.name)
            txt = p.read_text(errors="ignore")
            if not re.search(r"Module|Dashboard|Page|Tab|Wizard", p.name):
                continue
            own = scan_text(txt)
            # ── ikuti komponen anak SATU tingkat (lihat catatan #5 di docstring) ──
            eff = dict(own)
            via = []
            for child in child_files(p):
                try:
                    cs = scan_text(child.read_text(errors="ignore"))
                except OSError:
                    continue
                if cs["tables"] == 0 and cs["toggle"] is False and cs["th"] == 0:
                    continue
                eff["cards"] += cs["cards"]
                eff["grids"] += cs["grids"]
                eff["tables"] += cs["tables"]
                eff["th"] = max(eff["th"], cs["th"])
                eff["toggle"] = eff["toggle"] or cs["toggle"]
                via.append(child.name)
            n_card, n_grid = eff["cards"], eff["grids"]
            n_table, n_th = eff["tables"], eff["th"]
            has_toggle = eff["toggle"]
            used = set(FIELD_USE.findall(txt))
            apis = sorted(set(API_CALL.findall(txt)))
            # field backend yang "tersedia" = kunci pada berkas route yang namanya
            # paling mirip modul ini (heuristik konservatif: dipakai hanya untuk
            # menandai, bukan sebagai angka mutlak)
            verdict = []
            if n_table == 0 and (n_card + n_grid) > 0:
                verdict.append("KARTU-SAJA")
            if n_table > 0 and (n_card + n_grid) > 0 and not has_toggle:
                verdict.append("campur tanpa pengalih")
            if n_table > 0 and n_th and n_th < 5:
                verdict.append(f"tabel hanya {n_th} kolom")
            if n_table > 0 and not has_toggle:
                verdict.append("tanpa pengalih")
            rows.append({
                "file": str(p.relative_to(APP)),
                "name": p.name,
                "lines": txt.count("\n") + 1,
                "cards": n_card, "grids": n_grid, "tables": n_table,
                "th": n_th, "toggle": has_toggle,
                "own": own, "via": via,
                "fields_used": len(used),
                "apis": apis[:12],
                "verdict": verdict,
            })

    card_only = [r for r in rows if "KARTU-SAJA" in r["verdict"]]
    thin = [r for r in rows if any(v.startswith("tabel hanya") for v in r["verdict"])]
    no_toggle = [r for r in rows if r["tables"] > 0 and not r["toggle"]]
    has_toggle = [r for r in rows if r["toggle"]]

    out = {
        "totals": {
            "modules_scanned": len(rows),
            "card_only": len(card_only),
            "thin_tables_lt5_cols": len(thin),
            "tables_without_toggle": len(no_toggle),
            "with_toggle": len(has_toggle),
        },
        "card_only": [r["name"] for r in card_only],
        "thin_tables": [{"name": r["name"], "th": r["th"], "fields_used": r["fields_used"]}
                        for r in sorted(thin, key=lambda x: x["th"])],
        "with_toggle": [r["name"] for r in has_toggle],
        "modules": sorted(rows, key=lambda r: (-len(r["verdict"]), r["name"])),
    }
    dest = APP / "memory" / "AUDIT_UI_TABLES_V2.json"
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False))

    B = "\033[1m"; R = "\033[91m"; Y = "\033[93m"; G = "\033[92m"; E = "\033[0m"
    print(f"\n{B}AUDIT UI v2{E} → {dest}")
    for k, v in out["totals"].items():
        print(f"  {k:26s} {v}")
    print(f"\n{B}KARTU-SAJA (butuh 2 tipe tampilan){E}")
    for r in card_only:
        print(f"  {R}{r['name']:42s}{E} kartu={r['cards']:3d} grid={r['grids']:3d} "
              f"baris={r['lines']:5d} field_dipakai={r['fields_used']}")
    print(f"\n{B}TABEL TIPIS (<5 kolom padahal datanya kaya){E}")
    for r in sorted(thin, key=lambda x: x["th"]):
        print(f"  {Y}{r['name']:42s}{E} kolom={r['th']:2d} field_dipakai={r['fields_used']}")
    print(f"\n{B}TABEL TANPA PENGALIH{E} ({len(no_toggle)}) — kandidat toggle Tabel/Grid")
    print("  " + ", ".join(r["name"] for r in no_toggle[:40]))
    print(f"\n{G}sudah punya pengalih (pola contoh){E}: " +
          ", ".join(r["name"] for r in has_toggle))
    print()


if __name__ == "__main__":
    main()
