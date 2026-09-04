#!/usr/bin/env python3
"""gate_marketing_ssot.py — GATE KONTRAK DATA MARKETING (F0.1/F0.8).

Gate ini menutup kelas cacat yang paling sering terjadi di repo ini, dan yang
paling dikeluhkan owner: *"database, collection dan field yang di panggil miss
semua … seperti fitur yang berdiri sendiri … dan duplikasi duplikasi."*

PEMERIKSAAN (semua harus HIJAU sebelum sebuah fase dinyatakan selesai)
----------------------------------------------------------------------
G1  Tidak ada koleksi di luar `core/collection_registry.py`.
G2  Tidak ada kode yang menyentuh koleksi DEPRECATED (mesin impor lama / tujuan salah).
G3  Tidak ada dokumen `marketing_sales_data` tanpa `metrics{}` (akar D01).
G4  Tidak ada dokumen `marketing_sales_data` yang duplikat pada
    (account_id, date, revenue_type) — kunci alaminya WAJIB unik.
G5  Bentuk dokumen rekap harian hanya boleh dibuat `core/marketing_sales_shape.py`:
    tidak boleh ada berkas lain yang menulis literal `"metrics": {` ke koleksi itu.
G6  Pembaca tidak boleh mengindeks `doc["metrics"]` / `doc["fulfillment"]` /
    `doc["customer_satisfaction"]` / `doc["live_metrics"]` LANGSUNG (penyebab HTTP 500).
G7  Indeks unik wajib terpasang: sales_data, orders, targets, creator_targets, budgets.
G8  Dokumen marketing pada koleksi ber-`account_scope='required'` wajib punya `account_id`.
G9  Tidak ada berkas kode yang masih mengimpor mesin impor yang sudah dihapus.
G10 Satuan persen konsisten: tidak ada dokumen rekap dengan rate > 100.

Pakai:
    cd /app && python3 scripts/gate_marketing_ssot.py
    cd /app && python3 scripts/gate_marketing_ssot.py --json /tmp/gate.json
Keluar dengan kode 1 bila ada pemeriksaan MERAH (bisa dipakai di CI/gate.sh).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

APP = Path("/app")
BE = APP / "backend"
sys.path.insert(0, str(BE))

SCAN_DIRS = [BE / "routes", BE / "core", BE / "services", BE / "utils"]
SKIP_PARTS = {"__pycache__", "tests", "legacy", "migrations"}

RE_ACCESS = re.compile(
    r"""db\s*(?:\.\s*(?P<attr>[A-Za-z_][A-Za-z0-9_]*)
              |\[\s*['"](?P<lit>[A-Za-z_][A-Za-z0-9_]*)['"]\s*\])
        \s*\.\s*(?P<op>[a-z_]+)\s*\(""",
    re.X,
)
NOT_A_COLLECTION = {"client", "command", "list_collection_names", "get_collection",
                    "name", "db", "admin", "drop_database", "create_collection"}

G, R, Y, B, E = "\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[0m"


class Gate:
    def __init__(self):
        self.results: list[dict] = []

    def add(self, code: str, ok: bool, title: str, detail: str = "", items=None):
        self.results.append({"code": code, "ok": ok, "title": title,
                             "detail": detail, "items": (items or [])[:40]})

    @property
    def failed(self):
        return [r for r in self.results if not r["ok"]]


def py_files():
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.py")):
            if set(p.parts) & SKIP_PARTS or p.name.startswith("test_"):
                continue
            yield p


async def main(as_json: str | None) -> int:
    from core.collection_registry import DEPRECATED, is_registered, all_allowed
    from core.marketing_import_schema import SOURCE_TYPES
    from database import get_db

    gate = Gate()
    db = get_db()

    # ── G1/G2: koleksi tak terdaftar & deprecated ───────────────────────────
    unregistered: dict[str, list] = {}
    deprecated_hits: dict[str, list] = {}
    for p in py_files():
        txt = p.read_text(errors="ignore")
        rel = str(p.relative_to(APP))
        for m in RE_ACCESS.finditer(txt):
            coll = m.group("attr") or m.group("lit")
            if not coll or coll in NOT_A_COLLECTION:
                continue
            line = txt.count("\n", 0, m.start()) + 1
            if coll in DEPRECATED:
                deprecated_hits.setdefault(coll, []).append(f"{rel}:{line}")
            elif not is_registered(coll):
                unregistered.setdefault(coll, []).append(f"{rel}:{line}")
    gate.add("G1", not unregistered,
             "semua koleksi yang dipakai kode TERDAFTAR di collection_registry",
             f"{len(unregistered)} koleksi tak terdaftar",
             [f"{k} ← {v[0]}" for k, v in sorted(unregistered.items())])
    gate.add("G2", not deprecated_hits,
             "tidak ada kode yang menyentuh koleksi DEPRECATED",
             f"{len(deprecated_hits)} koleksi",
             [f"{k} → pakai {DEPRECATED[k]} ({v[0]})" for k, v in sorted(deprecated_hits.items())])

    # ── G3/G4/G10: keadaan data rekap harian ────────────────────────────────
    no_metrics = await db.marketing_sales_data.count_documents({"metrics": {"$exists": False}})
    gate.add("G3", no_metrics == 0,
             "tidak ada dokumen marketing_sales_data tanpa `metrics{}` (D01)",
             f"{no_metrics} dokumen bermasalah")

    dup = await db.marketing_sales_data.aggregate([
        {"$group": {"_id": {"a": "$account_id", "d": "$date", "t": "$revenue_type"},
                    "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$limit": 20},
    ]).to_list(20)
    gate.add("G4", not dup,
             "kunci alami rekap harian (account_id, date, revenue_type) tidak duplikat",
             f"{len(dup)} kunci duplikat",
             [f"{d['_id']} ×{d['n']}" for d in dup])

    PCT = ["metrics.conversion_rate", "fulfillment.fulfillment_rate",
           "fulfillment.cancellation_rate", "fulfillment.return_rate",
           "fulfillment.late_shipment_rate", "customer_satisfaction.response_rate"]
    bad_pct = await db.marketing_sales_data.count_documents(
        {"$or": [{f: {"$gt": 100}} for f in PCT]})
    gate.add("G10", bad_pct == 0,
             "satuan persen konsisten 0–100 (tidak ada rate > 100)",
             f"{bad_pct} dokumen di luar rentang")

    # ── G5: pembuat bentuk tunggal ──────────────────────────────────────────
    shape_violators = []
    for p in py_files():
        if p.name == "marketing_sales_shape.py":
            continue
        txt = p.read_text(errors="ignore")
        if "marketing_sales_data" not in txt:
            continue
        for m in re.finditer(r"""["']metrics["']\s*:\s*\{""", txt):
            line = txt.count("\n", 0, m.start()) + 1
            shape_violators.append(f"{p.relative_to(APP)}:{line}")
    gate.add("G5", not shape_violators,
             "bentuk rekap harian HANYA dibuat core/marketing_sales_shape.py",
             f"{len(shape_violators)} penulisan literal `metrics:{{` di luar pembuat",
             shape_violators)

    # ── G6: pembaca defensif ────────────────────────────────────────────────
    direct_index = []
    pat = re.compile(r"""\[\s*["'](metrics|fulfillment|customer_satisfaction|live_metrics)["']\s*\]""")
    for p in py_files():
        if p.name == "marketing_sales_shape.py":
            continue
        txt = p.read_text(errors="ignore")
        if "marketing_sales_data" not in txt:
            continue
        for m in pat.finditer(txt):
            line = txt.count("\n", 0, m.start()) + 1
            src = txt.splitlines()[line - 1]
            if src.lstrip().startswith("#"):
                continue
            direct_index.append(f"{p.relative_to(APP)}:{line} → {src.strip()[:70]}")
    gate.add("G6", not direct_index,
             "tidak ada pembaca yang mengindeks grup rekap LANGSUNG (penyebab HTTP 500)",
             f"{len(direct_index)} lokasi", direct_index)

    # ── G7: indeks unik ─────────────────────────────────────────────────────
    need = {
        "marketing_sales_data": ("account_id", "date", "revenue_type"),
        "marketing_orders": ("account_id", "platform", "order_id"),
        "marketing_account_targets": ("account_id", "year", "month"),
        "marketing_creator_targets": ("creator_id", "year", "month"),
        "marketing_budgets": ("account_id", "period"),
    }
    missing_idx = []
    for coll, keys in need.items():
        info = await db[coll].index_information()
        ok = any(i.get("unique") and tuple(k for k, _ in i["key"]) == keys
                 for i in info.values())
        if not ok:
            missing_idx.append(f"{coll} ({', '.join(keys)})")
    gate.add("G7", not missing_idx, "indeks UNIK kunci alami terpasang",
             f"{len(missing_idx)} kurang", missing_idx)

    # ── G8: account_id wajib ────────────────────────────────────────────────
    scope_bad = []
    for st in SOURCE_TYPES.values():
        if st.account_scope != "required":
            continue
        n = await db[st.collection].count_documents(
            {"$or": [{"account_id": {"$exists": False}}, {"account_id": None},
                     {"account_id": ""}]})
        if n:
            scope_bad.append(f"{st.collection}: {n} dokumen tanpa account_id")
    gate.add("G8", not scope_bad,
             "semua dokumen marketing (scope wajib) punya `account_id`",
             f"{len(scope_bad)} koleksi", scope_bad)

    # ── G9: sisa impor mesin lama ───────────────────────────────────────────
    ghosts = []
    for p in py_files():
        txt = p.read_text(errors="ignore")
        for m in re.finditer(r"^\s*(?:from|import)\s+.*\b(universal_import\w*|marketing_import)\b",
                             txt, re.M):
            if "marketing_import_schema" in m.group(0) or "marketing_import_engine" in m.group(0):
                continue
            ghosts.append(f"{p.relative_to(APP)}:{txt.count(chr(10), 0, m.start()) + 1}")
    gate.add("G9", not ghosts, "tidak ada impor ke mesin impor yang sudah DIHAPUS",
             f"{len(ghosts)} lokasi", ghosts)

    # ── laporan ─────────────────────────────────────────────────────────────
    print(f"\n{B}GATE KONTRAK DATA MARKETING (INV-MKT-SSOT){E}")
    print(f"  koleksi terdaftar: {len(all_allowed())} · deprecated: {len(DEPRECATED)}\n")
    for r in gate.results:
        badge = f"{G}HIJAU{E}" if r["ok"] else f"{R}MERAH{E}"
        print(f"  [{r['code']:>3s}] {badge}  {r['title']}")
        if not r["ok"]:
            print(f"        {Y}{r['detail']}{E}")
            for it in r["items"]:
                print(f"          · {it}")
    ok_n = len(gate.results) - len(gate.failed)
    print(f"\n  {B}{ok_n}/{len(gate.results)} HIJAU{E}")
    if as_json:
        Path(as_json).write_text(json.dumps(gate.results, indent=1, ensure_ascii=False, default=str))
        print(f"  laporan JSON → {as_json}")
    if gate.failed:
        print(f"  {R}GATE MERAH — perbaiki sebelum fase dinyatakan selesai.{E}\n")
        return 1
    print(f"  {G}GATE HIJAU.{E}\n")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="as_json", default=None)
    a = ap.parse_args()
    os.chdir(BE)
    raise SystemExit(asyncio.run(main(a.as_json)))
