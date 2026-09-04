#!/usr/bin/env python3
"""seed_acc_valuation_baseline — data baseline VALUASI HPP AKSESORIS (lewat API nyata).

KENAPA ADA
Setelah clone baru / DB fresh, tab "Valuasi HPP" dan rapor valuasi kosong sehingga
fitur (rapor bulanan, digest "belum dinilai") tidak bisa diverifikasi secara nyata.
Skrip ini membangun baseline yang WAJAR memakai endpoint produksi (bukan tulis DB
langsung), sehingga HPP rata-rata bergerak, jurnal persediaan, dan kartu stok
terbentuk seperti pemakaian sesungguhnya.

Isi baseline:
  5 aksesoris BERNILAI  (punya HPP + stok + jurnal)   → total nilai persediaan wajar
  2 aksesoris BELUM DINILAI (stok masuk tanpa harga)  → memicu alarm & digest
  1 pengeluaran + 1 scrap                             → kartu mutasi bernilai terisi

Idempoten: item yang kodenya sudah ada TIDAK dibuat/ditambah stok lagi.

Pakai:
    python3 /app/scripts/seed_acc_valuation_baseline.py
    python3 /app/scripts/seed_acc_valuation_baseline.py --cleanup
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

load_dotenv("/app/backend/.env")

BASE = os.environ.get("BASE_URL", "http://localhost:8001")
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
PREFIX = "DEMO-ACC"

# (kode, nama, satuan, kategori, [(qty, harga_satuan)])
VALUED = [
    ("BTN-15L", "Kancing Kemeja 15L Putih", "pcs", "Kancing", [(5000, 150), (3000, 175)]),
    ("LBL-WVN", "Label Woven Dewi Aditya", "pcs", "Label", [(4000, 300)]),
    ("ZIP-20", "Zipper Nylon 20cm Hitam", "pcs", "Zipper", [(1200, 1250)]),
    ("THR-40S", "Benang Jahit 40s Putih", "roll", "Benang", [(150, 8500)]),
    ("HTG-KRT", "Hangtag Karton Cetak", "pcs", "Hangtag", [(6000, 220)]),
]
# (kode, nama, satuan, kategori, qty_masuk_tanpa_harga)
UNVALUED = [
    ("ELS-25", "Elastis Karet 2.5cm", "meter", "Elastis", 800),
    ("SNP-BTN", "Kancing Snap Logam", "pcs", "Kancing", 2500),
]


def H(t):
    return {"Authorization": f"Bearer {t}"}


def code_of(suffix: str) -> str:
    return f"{PREFIX}-{suffix}"


async def _login(c) -> str:
    r = await c.post(f"{BASE}/api/auth/login", json=ADMIN)
    r.raise_for_status()
    return r.json()["token"]


async def _existing(c, tok) -> dict:
    """map kode → id untuk item aksesoris yang sudah ada."""
    r = await c.get(f"{BASE}/api/acc/items?limit=500", headers=H(tok))
    rows = r.json()
    rows = rows if isinstance(rows, list) else (rows.get("items") or [])
    return {x.get("code"): x.get("id") for x in rows if x.get("code")}


async def seed() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        tok = await _login(c)
        have = await _existing(c, tok)
        made = 0

        for suffix, name, unit, cat, receipts in VALUED:
            code = code_of(suffix)
            if code in have:
                print(f"  = {code} sudah ada, dilewati")
                continue
            r = await c.post(f"{BASE}/api/acc/items", headers=H(tok), json={
                "code": code, "name": name, "unit": unit, "category": cat, "unit_cost": 0,
            })
            if r.status_code not in (200, 201):
                print(f"  ! gagal membuat {code}: {r.status_code} {r.text[:120]}")
                continue
            body = r.json()
            acc_id = body.get("id") or (body.get("item") or {}).get("id")
            for qty, cost in receipts:
                rr = await c.post(f"{BASE}/api/acc/stock/receive", headers=H(tok), json={
                    "acc_id": acc_id, "qty": qty, "unit_cost": cost,
                    "notes": "Baseline demo — penerimaan pembelian",
                })
                st = "ok" if rr.status_code in (200, 201) else f"gagal {rr.status_code}"
                print(f"  + {code}: terima {qty} @ {cost} → {st}")
            made += 1

        for suffix, name, unit, cat, qty in UNVALUED:
            code = code_of(suffix)
            if code in have:
                print(f"  = {code} sudah ada, dilewati")
                continue
            r = await c.post(f"{BASE}/api/acc/items", headers=H(tok), json={
                "code": code, "name": name, "unit": unit, "category": cat, "unit_cost": 0,
            })
            if r.status_code not in (200, 201):
                print(f"  ! gagal membuat {code}: {r.status_code} {r.text[:120]}")
                continue
            body = r.json()
            acc_id = body.get("id") or (body.get("item") or {}).get("id")
            rr = await c.post(f"{BASE}/api/acc/stock/receive", headers=H(tok), json={
                "acc_id": acc_id, "qty": qty,
                "notes": "Baseline demo — masuk tanpa harga (memicu alarm belum dinilai)",
            })
            print(f"  + {code}: terima {qty} TANPA harga → "
                  f"{'ok' if rr.status_code in (200, 201) else f'gagal {rr.status_code}'}")
            made += 1

        # mutasi keluar + scrap pada item bernilai supaya kartu mutasi terisi
        have = await _existing(c, tok)
        btn = have.get(code_of("BTN-15L"))
        lbl = have.get(code_of("LBL-WVN"))
        if btn:
            r = await c.post(f"{BASE}/api/acc/stock/issue", headers=H(tok), json={
                "acc_id": btn, "qty": 1200, "notes": "Baseline demo — pemakaian produksi"})
            print(f"  · pengeluaran 1200 kancing → {r.status_code}")
        if lbl:
            r = await c.post(f"{BASE}/api/acc/stock/scrap", headers=H(tok), json={
                "acc_id": lbl, "qty": 50, "reason": "Rusak",
                "notes": "Baseline demo — label salah cetak"})
            print(f"  · scrap 50 label → {r.status_code}")

        val = (await c.get(f"{BASE}/api/acc/valuation", headers=H(tok))).json()
        tot = val.get("totals") or {}
        print(f"\nBASELINE SIAP · item baru: {made}")
        print(f"  nilai persediaan aksesoris : Rp {float(tot.get('total_value') or 0):,.0f}"
              .replace(",", "."))
        print(f"  item bernilai / belum dinilai: {tot.get('valued_items')} / "
              f"{tot.get('unvalued_items')}")
    return 0


async def cleanup() -> int:
    """Hapus artefak baseline (material + stok + mutasi + ledger + HPP + jurnal terkait)."""
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    mats = await db.rahaza_materials.find({"code": {"$regex": f"^{PREFIX}-"}},
                                          {"_id": 0, "id": 1}).to_list(200)
    ids = [m["id"] for m in mats]
    if not ids:
        print("Tidak ada artefak baseline.")
        return 0
    total = 0
    mv = await db.rahaza_material_movements.find(
        {"material_id": {"$in": ids}}, {"_id": 0, "gl_je_id": 1}).to_list(2000)
    je_ids = [m["gl_je_id"] for m in mv if m.get("gl_je_id")]
    for coll, q in (
        ("rahaza_material_stock", {"material_id": {"$in": ids}}),
        ("rahaza_material_movements", {"material_id": {"$in": ids}}),
        ("rahaza_stock_ledger", {"material_id": {"$in": ids}}),
        ("rahaza_material_cost_history", {"material_id": {"$in": ids}}),
        ("notifications", {"meta.unvalued_material_id": {"$in": ids}}),
        ("rahaza_journal_lines", {"je_id": {"$in": je_ids}}),
        ("rahaza_journal_entries", {"id": {"$in": je_ids}}),
        ("rahaza_materials", {"id": {"$in": ids}}),
    ):
        res = await db[coll].delete_many(q)
        if res.deleted_count:
            print(f"  - {coll}: {res.deleted_count}")
            total += res.deleted_count
    print(f"TOTAL artefak dihapus: {total}")
    client.close()
    return 0


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        raise SystemExit(asyncio.run(cleanup()))
    raise SystemExit(asyncio.run(seed()))
