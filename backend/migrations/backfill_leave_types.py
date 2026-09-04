#!/usr/bin/env python3
"""backfill_leave_types.py — samakan bentuk dokumen `rahaza_leave_types` (BUG-4).

Masalah: satu koleksi punya DUA bentuk dokumen.
  · Hasil seeder  → `unpaid`, `request_type`, `requires_document`, … (tanpa `paid`)
  · Hasil form HR → `paid`, `quota_default`, `description` (tanpa yang lain)

Pembacanya terbelah: `GET /leaves*` memakai `paid`, payroll & carry-forward
memakai `unpaid`. Akibatnya "Cuti Tahunan" dilaporkan TIDAK dibayar, dan jenis
cuti buatan HR tidak pernah kena potongan cuti-tanpa-upah.

Skrip ini IDEMPOTEN: menulis kedua field agar sinkron + melengkapi field wajib
yang hilang, tanpa mengubah arti data yang sudah ada.

Jalankan:  python3 /app/backend/migrations/backfill_leave_types.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")

from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from utils.leave_types import DEFAULT_COLOR, is_unpaid  # noqa: E402

DRY = "--dry-run" in sys.argv

DEFAULTS = {
    "request_type": "cuti",
    "requires_document": False,
    "max_days_without_doc": 0,
    "doc_note": "",
    "description": "",
    "color": DEFAULT_COLOR,
    "legal_basis": "",
    "max_carry_days": 0,
    "quota_default": 12,
    "active": True,
}


async def main() -> int:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "garment_erp")]
    rows = await db.rahaza_leave_types.find({}, {"_id": 0}).to_list(1000)
    print(f"Total jenis cuti: {len(rows)}")

    fixed = 0
    for lt in rows:
        unpaid = is_unpaid(lt)
        upd = {}
        if lt.get("unpaid") != unpaid:
            upd["unpaid"] = unpaid
        if lt.get("paid") != (not unpaid):
            upd["paid"] = not unpaid
        for k, v in DEFAULTS.items():
            if lt.get(k) is None:
                upd[k] = v
        if upd:
            fixed += 1
            print(f"  · {lt.get('code'):<14} {sorted(upd.keys())}")
            if not DRY:
                await db.rahaza_leave_types.update_one({"id": lt["id"]}, {"$set": upd})

    print(f"{'[DRY-RUN] akan diperbaiki' if DRY else 'Diperbaiki'}: {fixed} dokumen")

    # Verifikasi
    if not DRY:
        bad = [r["code"] for r in await db.rahaza_leave_types.find({}, {"_id": 0}).to_list(1000)
               if r.get("paid") is None or r.get("unpaid") is None
               or r.get("paid") == r.get("unpaid")]
        print(f"Sisa dokumen tidak sinkron: {len(bad)} {bad[:5]}")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
