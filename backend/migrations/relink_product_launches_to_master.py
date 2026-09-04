#!/usr/bin/env python3
"""relink_product_launches_to_master.py — tautkan rencana peluncuran ke MASTER PRODUK.

═══════════════════════════════════════════════════════════════════════════════
KENAPA SKRIP INI ADA
═══════════════════════════════════════════════════════════════════════════════
Temuan pemilik (2026-08-14): form **Launching Produk** meminta staf mengetik
nama/bahan/model sebagai teks bebas, padahal produknya sudah ada di
`rahaza_models`. Aturan barunya (F14b) sudah ditutup di server: `model_id`
WAJIB, dan identitas produk ditulis SERVER dari master.

Yang tersisa adalah **dokumen yang terlanjur ada**. Skrip ini menanganinya
dengan dua aturan yang sengaja dibedakan:

  · **Dokumen CONTOH** (`_seed_origin: True`) — dibuat oleh seeder lama dari
    daftar hardcode ("Gamis Busui Friendly DA-2026 Series 1", bahan "Katun Linen
    Premium") yang TIDAK ADA di master. Data contoh yang melanggar aturan bukan
    sekadar kotor: ia MENGAJARKAN pola yang salah — staf melihat 8 baris tanpa
    tautan master lalu menyimpulkan mengetik bebas itu wajar. Karena isinya
    memang karangan, dokumen ini **dibuang dan disemai ulang dari master**.

  · **Dokumen NYATA** (buatan pemakai) — **TIDAK PERNAH DITEBAK**. Menebak
    padanan berdasarkan kemiripan nama akan menautkan rencana ke produk yang
    SALAH, dan sesudah tertaut tidak ada yang bisa membedakannya dari tautan
    yang benar. Yang dilakukan hanya: memastikan `master_linked: False`
    tersimpan supaya jumlahnya **diakui di layar** (banner amber + penanda
    "belum tertaut" per baris) dan orang yang tahu produknya bisa memperbaiki
    lewat Edit. (Pelajaran `closed_at`: data warisan tidak ditebak diam-diam,
    jumlahnya diakui.)

Juga membersihkan **FG karangan** yang terlanjur lahir dari teks
(`created_via='product_launch_auto'`) — barang jadi yang tidak pernah ada di
master, `hpp=0`, kategori literal "launch". Hanya dibuang kalau BENAR-BENAR
tidak punya riwayat stok; kalau sudah pernah dipakai, ia DILAPORKAN (tidak
dihapus) karena menghapus barang yang punya mutasi akan merusak buku stok.

Pakai:
    python3 backend/migrations/relink_product_launches_to_master.py             # laporan saja
    python3 backend/migrations/relink_product_launches_to_master.py --execute   # kerjakan
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
EXECUTE = "--execute" in sys.argv

UNLINKED = {"$or": [{"model_id": {"$exists": False}},
                    {"model_id": None}, {"model_id": ""}]}


async def main() -> int:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    print(f"{B}══ Tautkan rencana peluncuran ke Master Produk "
          f"({'EKSEKUSI' if EXECUTE else 'LAPORAN SAJA'}) ══{X}")

    total = await db.marketing_product_launches.count_documents({})
    unlinked = await db.marketing_product_launches.count_documents(UNLINKED)
    seed_unlinked = await db.marketing_product_launches.count_documents(
        {**UNLINKED, "_seed_origin": True})
    real_unlinked = unlinked - seed_unlinked
    print(f"  rencana peluncuran : {total}")
    print(f"  belum tertaut      : {unlinked}  "
          f"(contoh: {seed_unlinked} · nyata: {real_unlinked})")

    models = await db.rahaza_models.count_documents(
        {"$or": [{"active": True}, {"active": {"$exists": False}}]})
    print(f"  master produk aktif: {models}")

    # ── 1. Dokumen CONTOH: buang, biar seeder baru menyemai dari master ──────
    if seed_unlinked:
        if models == 0:
            print(f"  {Y}▲ master produk KOSONG ⇒ contoh tidak dibuang{X} "
                  f"(layar kosong lebih jujur daripada 0 contoh + 0 master, "
                  f"tetapi membuang tanpa pengganti hanya memindahkan masalah)")
        elif EXECUTE:
            res = await db.marketing_product_launches.delete_many(
                {**UNLINKED, "_seed_origin": True})
            print(f"  {G}✓{X} {res.deleted_count} contoh warisan dibuang — "
                  f"seeder akan menyemai ulang DARI MASTER saat layar dibuka")
        else:
            print(f"  {Y}→{X} {seed_unlinked} contoh warisan AKAN dibuang & "
                  f"disemai ulang dari master")

    # ── 2. Dokumen NYATA: diakui, TIDAK ditebak ─────────────────────────────
    if real_unlinked:
        if EXECUTE:
            res = await db.marketing_product_launches.update_many(
                {**UNLINKED, "_seed_origin": {"$ne": True}},
                {"$set": {"master_linked": False}})
            print(f"  {G}✓{X} {res.modified_count} rencana NYATA ditandai "
                  f"'belum tertaut' — TIDAK ditebak (menebak padanan nama akan "
                  f"menautkan ke produk yang salah tanpa bisa dibedakan)")
        else:
            print(f"  {Y}→{X} {real_unlinked} rencana NYATA akan ditandai "
                  f"'belum tertaut' (tanpa menebak padanannya)")
    else:
        print(f"  {G}✓{X} tidak ada rencana NYATA yang belum tertaut")

    # ── 3. FG karangan hasil auto-create lama ───────────────────────────────
    ghosts = await db.rahaza_materials.find(
        {"created_via": "product_launch_auto"},
        {"_id": 0, "id": 1, "code": 1, "name": 1}).to_list(1000)
    print(f"\n{B}Barang jadi karangan (created_via='product_launch_auto'){X}")
    if not ghosts:
        print(f"  {G}✓{X} tidak ada — bersih")
    else:
        dihapus, ditahan = 0, []
        for g in ghosts:
            # Punya riwayat stok? Jangan disentuh — buku stok lebih penting
            # daripada kerapian master.
            used = await db.rahaza_stock_ledger.count_documents(
                {"material_id": g["id"]})
            if used:
                ditahan.append((g["code"], used))
                continue
            if EXECUTE:
                await db.rahaza_materials.delete_one({"id": g["id"]})
            dihapus += 1
        print(f"  {G if EXECUTE else Y}{'dihapus' if EXECUTE else 'akan dihapus'}"
              f"{X}: {dihapus} (tanpa riwayat stok)")
        for code, n in ditahan:
            print(f"  {R}DITAHAN{X} {code} — punya {n} baris riwayat stok; "
                  f"menghapusnya akan merusak buku stok. Gabungkan manual.")

    print(f"\n{B}{'SELESAI' if EXECUTE else 'LAPORAN SAJA — jalankan dengan --execute'}{X}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
