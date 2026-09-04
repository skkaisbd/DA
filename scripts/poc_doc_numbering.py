#!/usr/bin/env python3
"""poc_doc_numbering.py — bukti format nomor dokumen yang diatur owner benar-benar dipakai.

Menguji jalur penuh: simpan format lewat API admin → generator resmi
`utils.counters.gen_prefixed_number` memakai format itu → hapus konfigurasi →
generator kembali ke format bawaan kode (tanpa regresi).

    python3 scripts/poc_doc_numbering.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

import requests  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from utils import counters as C  # noqa: E402

API = os.environ.get("INTERNAL_API_URL", "http://localhost:8001")
KEY = "wh_returns.return_code"
COLL, FIELD = KEY.rsplit(".", 1)

results = []


def check(cond, label):
    results.append((bool(cond), label))
    print(("  ✓ " if cond else "  ✗ ") + label)


def login():
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=30)
    r.raise_for_status()
    b = r.json()
    return {"Authorization": f"Bearer {b.get('access_token') or b.get('token')}"}


async def run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    hdr = login()

    print("\n0) Bersihkan sisa uji sebelumnya")
    await db.doc_number_configs.delete_one({"key": KEY})
    await db.counters.delete_many({"_id": {"$regex": r"^autonum:wh_returns:return_code:(ZZTEST|WH-RET-)"}})
    C.invalidate_format_cache()

    print("\n1) Format bawaan kode dipakai saat belum dikonfigurasi")
    n1 = await C.gen_prefixed_number(db, COLL, FIELD, "WH-RET-", 5)
    check(n1.startswith("WH-RET-") and len(n1) == 12, f"nomor bawaan = {n1}")

    print("\n2) Format tidak sah ditolak API")
    r = requests.put(f"{API}/api/admin/doc-numbering", headers=hdr, timeout=30,
                     json={"key": KEY, "format": "ZZTEST-{BULAN}-{SEQ:3}"})
    check(r.status_code == 400 and "Token tidak dikenal" in r.text,
          f"token asing ditolak 400 (dapat {r.status_code})")
    r = requests.put(f"{API}/api/admin/doc-numbering", headers=hdr, timeout=30,
                     json={"key": KEY, "format": "ZZTEST-{SEQ:3}-akhir"})
    check(r.status_code == 400, f"{{SEQ}} bukan di akhir ditolak 400 (dapat {r.status_code})")

    print("\n3) Simpan format kustom lewat API")
    r = requests.put(f"{API}/api/admin/doc-numbering", headers=hdr, timeout=30,
                     json={"key": KEY, "format": "ZZTEST/{YYYY}/{SEQ:3}"})
    check(r.status_code == 200, f"tersimpan (dapat {r.status_code}: {r.text[:80]})")
    check(r.json().get("contoh", "").endswith("/001"), f"contoh = {r.json().get('contoh')}")

    print("\n4) Generator resmi memakai format kustom")
    C.invalidate_format_cache()
    n2 = await C.gen_prefixed_number(db, COLL, FIELD, "WH-RET-", 5)
    n3 = await C.gen_prefixed_number(db, COLL, FIELD, "WH-RET-", 5)
    check(n2.startswith("ZZTEST/"), f"format kustom dipakai = {n2}")
    check(n2.endswith("001") and n3.endswith("002"), f"urut berlanjut: {n2} → {n3}")

    print("\n5) Setel titik awal nomor urut")
    r = requests.post(f"{API}/api/admin/doc-numbering/counter", headers=hdr, timeout=30,
                      json={"key": KEY, "start_from": 500})
    check(r.status_code == 200, f"counter diset (dapat {r.status_code}: {r.text[:80]})")
    C.invalidate_format_cache()
    n4 = await C.gen_prefixed_number(db, COLL, FIELD, "WH-RET-", 5)
    check(n4.endswith("501"), f"nomor berikutnya = {n4}")

    print("\n6) Hapus konfigurasi → kembali ke format bawaan")
    r = requests.delete(f"{API}/api/admin/doc-numbering/{KEY}", headers=hdr, timeout=30)
    check(r.status_code == 200, f"reset OK (dapat {r.status_code})")
    C.invalidate_format_cache()
    n5 = await C.gen_prefixed_number(db, COLL, FIELD, "WH-RET-", 5)
    check(n5.startswith("WH-RET-"), f"kembali ke bawaan = {n5}")

    print("\n7) Format rusak di DB tidak boleh memblokir transaksi")
    await db.doc_number_configs.insert_one(
        {"key": KEY, "format": "RUSAK-tanpa-seq", "active": True})
    C.invalidate_format_cache()
    n6 = await C.gen_prefixed_number(db, COLL, FIELD, "WH-RET-", 5)
    check(n6.startswith("WH-RET-"), f"jatuh ke bawaan dengan aman = {n6}")

    print("\n8) Bersih-bersih")
    await db.doc_number_configs.delete_one({"key": KEY})
    await db.counters.delete_many({"_id": {"$regex": r"^autonum:wh_returns:return_code:ZZTEST"}})
    C.invalidate_format_cache()
    print("  · konfigurasi & counter uji dihapus")


def main():
    asyncio.run(run())
    ok = sum(1 for c, _ in results if c)
    print(f"\n{'='*60}\n{ok}/{len(results)} LULUS")
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
