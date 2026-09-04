#!/usr/bin/env python3
"""
audit_menu_zombie.py — cari "menu zombie": pintu menu yang endpoint-nya membaca
koleksi yang KOSONG atau TIDAK ADA sama sekali.

Latar belakang: migrasi SSOT dilakukan bertahap, tetapi banyak modul lama tidak
dibersihkan sehingga tetap tampil di menu walau gudang datanya sudah tidak
ditulisi siapa pun (contoh yang sudah ditemukan manual: Data Pelanggan →
rahaza_customers = 0 dokumen).

Cara pakai:
    python3 scripts/audit_menu_zombie.py            # laporan ringkas
    python3 scripts/audit_menu_zombie.py --verbose  # sertakan detail koleksi

Catatan: heuristik. Hasilnya DAFTAR KANDIDAT untuk diperiksa manusia, bukan
perintah hapus otomatis.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")

FE = Path("/app/frontend/src/components/erp")
BE = Path("/app/backend/routes")
NAV = FE / "portal-shell" / "portalNav.js"
REG = FE / "moduleRegistry.js"


def nav_menu_ids() -> dict:
    """{module_id: portal} dari SSOT navigasi."""
    src = NAV.read_text()
    body = src[src.index("export const PORTAL_NAV"):]
    out, portal = {}, "?"
    for line in body.splitlines():
        m = re.match(r"\s{2}([a-z_]+):\s*\{", line)
        if m:
            portal = m.group(1)
        for mid in re.findall(r"id:\s*'([a-z0-9\-]+)'", line):
            out.setdefault(mid, portal)
    return out


def registry_map() -> dict:
    """{module_id: component_name | 'REDIRECT:<target>'}"""
    src = REG.read_text()
    lazy = dict(re.findall(r"const\s+(\w+)\s*=\s*lazy\(\(\)\s*=>\s*import\('([^']+)'\)\)", src))
    out = {}
    for mid, val in re.findall(r"'([a-z0-9\-]+)':\s*([A-Za-z_]\w*|makeRedirect\([^)]*\))", src):
        if val.startswith("makeRedirect"):
            tgt = re.search(r"'([a-z0-9\-]+)'", val)
            out[mid] = f"REDIRECT:{tgt.group(1) if tgt else '?'}"
        else:
            out[mid] = lazy.get(val, val)
    return out


def api_paths(rel: str) -> set:
    f = (FE / f"{rel.lstrip('./')}.jsx")
    if not f.exists():
        f = (FE / f"{rel.lstrip('./')}.js")
    if not f.exists():
        return set()
    txt = f.read_text()
    return set(re.findall(r"/api/[a-zA-Z0-9_\-/]+", txt))


def collections_for(path: str) -> set:
    """Cari berkas route yang menangani path lalu ambil koleksi yang dibacanya."""
    parts = [p for p in path.split("/") if p and p != "api"]
    if not parts:
        return set()
    needles = ["/".join(parts[-2:]), parts[-1]]
    cols: set = set()
    for rf in BE.glob("*.py"):
        txt = rf.read_text(errors="ignore")
        if not any(f'"{n}' in txt or f"'{n}" in txt or f"/{n}" in txt for n in needles):
            continue
        cols |= set(re.findall(r"db\.([a-z_][a-z0-9_]*)", txt))
        cols |= set(re.findall(r'db\[["\']([a-z_][a-z0-9_]*)["\']\]', txt))
    return {c for c in cols if not c.startswith(("client", "command", "list_"))}


async def main() -> int:
    verbose = "--verbose" in sys.argv
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ.get("DB_NAME", "test_database")]
    existing = set(await db.list_collection_names())
    counts: dict = {}

    async def count(c: str) -> int:
        if c not in counts:
            counts[c] = await db[c].count_documents({}) if c in existing else -1
        return counts[c]

    nav = nav_menu_ids()
    reg = registry_map()
    zombies, no_api, redirects, ok = [], [], [], 0

    for mid, portal in sorted(nav.items()):
        comp = reg.get(mid)
        if not comp:
            zombies.append((portal, mid, "TIDAK ADA DI REGISTRY", []))
            continue
        if comp.startswith("REDIRECT:"):
            redirects.append((portal, mid, comp))
            continue
        paths = api_paths(comp)
        if not paths:
            no_api.append((portal, mid, comp))
            continue
        cols: set = set()
        for p in paths:
            cols |= collections_for(p)
        if not cols:
            no_api.append((portal, mid, comp))
            continue
        stats = []
        for c in sorted(cols):
            stats.append((c, await count(c)))
        live = [c for c, n in stats if n > 0]
        if not live:
            zombies.append((portal, mid, comp, stats))
        else:
            ok += 1
            if verbose:
                print(f"  OK  {portal:12} {mid:32} koleksi berisi: {len(live)}/{len(stats)}")

    print("\n" + "=" * 78)
    print("KANDIDAT MENU ZOMBIE (semua koleksi yang dibaca kosong / tidak ada)")
    print("=" * 78)
    if not zombies:
        print("  (tidak ada)")
    for portal, mid, comp, stats in zombies:
        print(f"\n  [{portal}] {mid}  →  {comp}")
        for c, n in stats[:10]:
            print(f"      {c:38} {'TIDAK ADA' if n < 0 else n}")

    print("\n" + "-" * 78)
    print(f"RINGKASAN: {ok} menu sehat · {len(zombies)} kandidat zombie · "
          f"{len(redirects)} redirect · {len(no_api)} tanpa panggilan API terdeteksi")
    print("-" * 78)
    if verbose:
        print("\nTANPA API TERDETEKSI (kemungkinan hub/tab atau UI statis):")
        for portal, mid, comp in no_api:
            print(f"  [{portal}] {mid} → {comp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
