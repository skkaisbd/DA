#!/usr/bin/env python3
"""backfill_quarantine_reject_reasons.py — rapikan bentuk `reject_reasons` (FASE 19 / AUDIT-2).

## Masalah

`GET /api/wms/quarantine/summary` bisa **HTTP 500** tergantung DATA, bukan kode:
`core.quarantine.summary()` melakukan `rr.get("code")` untuk setiap elemen
`reject_reasons`, sementara `routes/rahaza_grn_qc.py` DULU menyimpan nilai itu
**mentah dari body request**. Satu klien yang mengirim `["KOTOR", "SOBEK"]`
(list of string — bentuk yang sangat wajar) cukup untuk mematikan seluruh KPI
karantina, dan `qc-report` supplier ikut mati dengan sebab yang sama.

Kodenya sudah ditutup di gerbang tulis (`utils/reject_reasons.py` dipakai oleh
`quarantine_in`, `rahaza_grn_qc`, `wms_quarantine`). Skrip ini membersihkan
**dokumen yang sudah tersimpan** supaya tidak ada bom waktu yang tertinggal.

## Cakupan
  * `wh_quarantine_items.reject_reasons`
  * `warehouse_receiving.items[].reject_reasons`
  * `rahaza_grn_inspections.items[].reject_reasons`

IDEMPOTEN (normalisasi 2× == 1×, dibuktikan `scripts/poc_fase19_core.py` C11) dan
tidak mengubah arti data: kode alasan dipertahankan; qty hanya diisi bila bisa
diturunkan tanpa mengarang (lihat docstring `utils/reject_reasons.py`).

Jalankan:
    python3 /app/backend/migrations/backfill_quarantine_reject_reasons.py --dry-run
    python3 /app/backend/migrations/backfill_quarantine_reject_reasons.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")

from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from utils.reject_reasons import is_canonical, normalize_reject_reasons  # noqa: E402

DRY = "--dry-run" in sys.argv
G, R, Y, X = "\033[92m", "\033[91m", "\033[93m", "\033[0m"


def _qty(doc: dict, *keys: str) -> float:
    for k in keys:
        try:
            v = float(doc.get(k) or 0)
        except (TypeError, ValueError):
            continue
        if v > 0:
            return v
    return 0.0


async def fix_flat(db, coll: str) -> tuple[int, int]:
    """Dokumen dengan `reject_reasons` di level atas (wh_quarantine_items)."""
    scanned = fixed = 0
    async for doc in db[coll].find({}, {"_id": 0}):
        scanned += 1
        raw = doc.get("reject_reasons")
        if is_canonical(raw):
            continue
        norm = normalize_reject_reasons(raw, default_qty=_qty(doc, "remaining_qty", "qty"))
        print(f"    {Y}→{X} {coll}/{doc.get('id','?')}: {raw!r} ⇒ {norm!r}")
        if not DRY:
            await db[coll].update_one({"id": doc["id"]}, {"$set": {"reject_reasons": norm}})
        fixed += 1
    return scanned, fixed


async def fix_nested(db, coll: str) -> tuple[int, int]:
    """Dokumen dengan `items[].reject_reasons` (GRN + inspeksi)."""
    scanned = fixed = 0
    async for doc in db[coll].find({}, {"_id": 0}):
        scanned += 1
        items = doc.get("items")
        if not isinstance(items, list):
            continue
        dirty = False
        new_items = []
        for line in items:
            if not isinstance(line, dict):
                new_items.append(line)
                continue
            raw = line.get("reject_reasons")
            if "reject_reasons" in line and not is_canonical(raw):
                line = {**line, "reject_reasons": normalize_reject_reasons(
                    raw, default_qty=_qty(line, "rejected_qty", "qty"))}
                dirty = True
                print(f"    {Y}→{X} {coll}/{doc.get('id','?')} line {line.get('id','?')}: "
                      f"{raw!r} ⇒ {line['reject_reasons']!r}")
            new_items.append(line)
        if dirty:
            if not DRY:
                await db[coll].update_one({"id": doc["id"]}, {"$set": {"items": new_items}})
            fixed += 1
    return scanned, fixed


async def main() -> int:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    mode = f"{Y}DRY-RUN{X}" if DRY else f"{G}APPLY{X}"
    print(f"\nbackfill reject_reasons — mode {mode} · db={db.name}\n")

    total_fixed = 0
    for coll in ("wh_quarantine_items",):
        s, f = await fix_flat(db, coll)
        total_fixed += f
        print(f"  {coll:28s} discan {s:5d} · dirapikan {f}")
    for coll in ("warehouse_receiving", "rahaza_grn_inspections"):
        s, f = await fix_nested(db, coll)
        total_fixed += f
        print(f"  {coll:28s} discan {s:5d} · dirapikan {f}")

    if total_fixed == 0:
        print(f"\n  {G}✓ tidak ada dokumen berbentuk liar (tidak ada drift){X}\n")
    elif DRY:
        print(f"\n  {Y}! {total_fixed} dokumen perlu dirapikan — jalankan tanpa --dry-run{X}\n")
    else:
        print(f"\n  {G}✓ {total_fixed} dokumen dirapikan{X}\n")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
