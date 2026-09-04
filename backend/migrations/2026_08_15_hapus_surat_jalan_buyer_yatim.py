#!/usr/bin/env python3
"""2026_08_15_hapus_surat_jalan_buyer_yatim.py — FASE E.

MENGAPA MIGRASI INI ADA
-----------------------
`POST /api/buyer-shipments` DULU menulis header surat jalan
(`db.buyer_shipments.insert_one(...)`) SEBELUM menjalankan pagar qty. Setiap
percobaan simpan yang DITOLAK ("qty melebihi sisa", "stok FG tidak cukup", dst)
karena itu meninggalkan SURAT JALAN YATIM:

    header ada · item 0 · progres "0 / 0 pcs" · status Pending
    dan nomor surat jalannya sudah terpakai (counter dokumen naik)

Akibatnya daftar pengiriman memuat baris yang tidak bisa dijelaskan siapa pun,
dan pemakai menyangka pengiriman itu "sudah pernah dilakukan" — persis keluhan
pemilik. Penyebabnya sudah diperbaiki di kode (pagar dipindah ke ATAS sebelum
dokumen ditulis); skrip ini membersihkan dokumen yang sudah terbentuk.

AMAN: hanya menghapus surat jalan yang BENAR-BENAR tidak punya satu pun baris
item. Surat jalan dengan item — walau qty 0 — TIDAK disentuh, karena itu bisa
saja dokumen sah yang qty-nya dikoreksi. Jalankan dengan --apply untuk menghapus;
tanpa flag hanya melaporkan (dry-run).

Pakai:
    python3 backend/migrations/2026_08_15_hapus_surat_jalan_buyer_yatim.py
    python3 backend/migrations/2026_08_15_hapus_surat_jalan_buyer_yatim.py --apply
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

G, Y, R, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[1m", "\033[0m"


async def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    apply = "--apply" in sys.argv
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]

    orphans = await db.buyer_shipments.aggregate([
        {"$lookup": {"from": "buyer_shipment_items", "localField": "id",
                     "foreignField": "shipment_id", "as": "it"}},
        {"$match": {"it": {"$size": 0}}},
        {"$project": {"_id": 0, "id": 1, "shipment_number": 1, "ship_status": 1,
                      "receiver_type": 1, "created_by": 1, "created_at": 1,
                      "customer_name": 1, "po_number": 1}},
    ]).to_list(None)

    print(f"{B}Surat jalan buyer YATIM (0 baris item): {len(orphans)}{X}")
    for o in orphans:
        print(f"  · {o.get('shipment_number','?'):28s} "
              f"status={o.get('ship_status','?'):18s} "
              f"penerima={o.get('receiver_type','buyer'):6s} "
              f"buyer={o.get('customer_name') or '-'} "
              f"po={o.get('po_number') or '-'} "
              f"dibuat_oleh={o.get('created_by') or '-'}")

    if not orphans:
        print(f"{G}Tidak ada yang perlu dibersihkan.{X}")
        return 0
    if not apply:
        print(f"\n{Y}DRY-RUN — tidak ada yang dihapus. "
              f"Jalankan ulang dengan --apply untuk menghapus {len(orphans)} dokumen.{X}")
        return 0

    ids = [o["id"] for o in orphans]
    # sekalian bersihkan jejak turunan yang mungkin menempel pada header yatim
    extra = 0
    for coll in ("buyer_shipment_dispatches", "buyer_shorts"):
        try:
            extra += (await db[coll].delete_many({"shipment_id": {"$in": ids}})).deleted_count
        except Exception:  # noqa: BLE001
            pass
    res = await db.buyer_shipments.delete_many({"id": {"$in": ids}})
    print(f"\n{G}Dihapus {res.deleted_count} surat jalan yatim"
          + (f" + {extra} dokumen turunan" if extra else "") + f".{X}")
    print(f"{Y}Catatan: nomor surat jalan yang sudah terpakai TIDAK dikembalikan ke "
          f"counter — nomor dokumen tidak boleh didaur ulang (jejak audit).{X}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
