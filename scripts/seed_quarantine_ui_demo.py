#!/usr/bin/env python3
"""seed_quarantine_ui_demo — data uji KARANTINA untuk verifikasi UI (FASE 6.5).

Bukan mock: data dibuat lewat ALUR NYATA (master material → Goods Receipt dengan
qty reject → GR di-set `received` sehingga `warehouse.update_receiving` mengalirkan
accepted→storage dan rejected→karantina), plus 1 karantina MANUAL (barang yang sudah
bernilai) supaya UI punya campuran `valued=False` & `valued=True`.

Prefix semua artefak = `TEST-Q6` sehingga mudah dibersihkan.

Pakai:
    python scripts/seed_quarantine_ui_demo.py            # buat data
    python scripts/seed_quarantine_ui_demo.py --cleanup  # hapus semua artefak TEST-Q6
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8001")
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
PREFIX = "TEST-Q6"


def H(t):
    return {"Authorization": f"Bearer {t}"}


async def login(c):
    r = await c.post(f"{BASE}/api/auth/login", json=ADMIN)
    if r.status_code != 200:
        print(f"  ✗ login gagal: {r.status_code} {r.text[:160]}")
        return None
    return r.json().get("token")


async def ensure_material(c, tok, code, name, mtype, unit, unit_cost):
    r = await c.post(f"{BASE}/api/rahaza/materials", headers=H(tok), json={
        "code": code, "name": name, "type": mtype, "unit": unit,
        "unit_cost": unit_cost, "min_stock": 0, "category": "TEST"})
    if r.status_code in (200, 201):
        return r.json()
    r2 = await c.get(f"{BASE}/api/rahaza/materials?search={code}", headers=H(tok))
    d = r2.json()
    rows = d if isinstance(d, list) else (d.get("items") or [])
    return next((x for x in rows if x.get("code") == code), {})


async def seed():
    async with httpx.AsyncClient(timeout=120) as c:
        tok = await login(c)
        if not tok:
            return 1

        # lokasi storage tujuan (SSOT — karantina sengaja TIDAK ada di daftar ini)
        r = await c.get(f"{BASE}/api/rahaza/storage-locations", headers=H(tok))
        sl = r.json()
        sl = sl if isinstance(sl, list) else (sl.get("items") or [])
        if not sl:
            print("  ✗ tidak ada lokasi storage — jalankan seed master dulu")
            return 1
        target = sl[0]
        print(f"  · lokasi storage tujuan: {target.get('code')} · {target.get('name')}")

        kain = await ensure_material(c, tok, f"{PREFIX}-KAIN", f"{PREFIX} Kain Cotton Combed 30s",
                                     "fabric", "m", 45000)
        acc = await ensure_material(c, tok, f"{PREFIX}-BTN", f"{PREFIX} Kancing Metal 15mm",
                                    "accessory", "pcs", 1200)
        if not kain.get("id") or not acc.get("id"):
            print("  ✗ gagal siapkan material")
            return 1
        print(f"  ✓ material: {kain['code']} + {acc['code']}")

        # ── GR dengan reject → karantina otomatis (valued=False) ──────────────
        r = await c.post(f"{BASE}/api/warehouse/receiving", headers=H(tok), json={
            "source_type": "supplier",
            "supplier_name": f"{PREFIX} PT Tekstil Nusantara",
            "location_id": target["id"], "location_name": target.get("name") or "",
            "notes": f"{PREFIX} kiriman dengan temuan QC",
            "items": [
                {"material_id": kain["id"], "sku": kain["code"], "product_name": kain["name"],
                 "unit": "m", "expected_qty": 300, "received_qty": 300, "rejected_qty": 18,
                 "unit_price": 45000,
                 "reject_reasons": [{"code": "FABRIC_DEFECT", "qty": 12, "notes": "kotor & stain di 3 titik"},
                                    {"code": "COLOR_MISMATCH", "qty": 6, "notes": "warna beda batch"}]},
                {"material_id": acc["id"], "sku": acc["code"], "product_name": acc["name"],
                 "unit": "pcs", "expected_qty": 5000, "received_qty": 5000, "rejected_qty": 250,
                 "unit_price": 1200,
                 "reject_reasons": [{"code": "WRONG_ITEM", "qty": 250, "notes": "ukuran 12mm, seharusnya 15mm"}]},
            ]})
        if r.status_code not in (200, 201):
            print(f"  ✗ buat GR gagal: {r.status_code} {r.text[:200]}")
            return 1
        gr = r.json()
        print(f"  ✓ GR dibuat: {gr.get('receipt_number')}")

        r = await c.put(f"{BASE}/api/warehouse/receiving/{gr['id']}", headers=H(tok),
                        json={"status": "received"})
        if r.status_code != 200:
            print(f"  ✗ set GR received gagal: {r.status_code} {r.text[:200]}")
            return 1
        qs = (r.json() or {}).get("quarantine_summary") or {}
        print(f"  ✓ GR received — quarantine_summary total_qty={qs.get('total_qty')}")

        # ── karantina MANUAL (barang sudah bernilai → scrap wajib JE) ─────────
        # NOTE: pakai bentuk body yang SAMA dengan FE ManualModal (`reason_code` + `unit`)
        # supaya seeder benar-benar mencerminkan alur user, bukan jalur khusus script.
        r = await c.post(f"{BASE}/api/wms/quarantine/manual", headers=H(tok), json={
            "material_id": kain["id"], "qty": 7, "from_location_id": target["id"],
            "unit": kain.get("unit") or "m",
            "reason_code": "MEASUREMENT_OUT",
            "notes": f"{PREFIX} lebar kain 148cm, spec 150cm (temuan saat cutting)"})
        if r.status_code in (200, 201):
            print(f"  ✓ karantina manual (valued=True): qty 7 {kain['code']}")
        else:
            print(f"  ! karantina manual gagal: {r.status_code} {r.text[:200]}")

        r = await c.get(f"{BASE}/api/wms/quarantine/summary", headers=H(tok))
        print("  → summary:", json.dumps(r.json(), default=str)[:300])
        r = await c.get(f"{BASE}/api/wms/quarantine?status=open", headers=H(tok))
        d = r.json()
        rows = d if isinstance(d, list) else (d.get("items") or [])
        print(f"  → {len(rows)} item karantina terbuka siap untuk uji UI")
        for it in rows:
            print(f"     · {it.get('material_code')} qty={it.get('qty')} sisa={it.get('remaining_qty')} "
                  f"valued={it.get('valued')} sumber={(it.get('source') or {}).get('type')}")
        return 0


async def cleanup():
    """Hapus semua artefak TEST-Q6 langsung di DB (idempotent)."""
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    dbname = os.environ.get("DB_NAME", "test_database")
    db = AsyncIOMotorClient(mongo)[dbname]

    mats = [m async for m in db.rahaza_materials.find(
        {"code": {"$regex": f"^{PREFIX}"}}, {"_id": 0, "id": 1, "code": 1})]
    mids = [m["id"] for m in mats]
    print(f"MODE: CLEANUP | material {[m['code'] for m in mats]}")

    total = 0
    plans = [
        ("rahaza_materials", {"id": {"$in": mids}}),
        ("rahaza_material_stock", {"material_id": {"$in": mids}}),
        ("rahaza_stock_ledger", {"material_id": {"$in": mids}}),
        ("rahaza_material_movements", {"material_id": {"$in": mids}}),
        ("wh_quarantine_items", {"material_id": {"$in": mids}}),
        ("warehouse_receiving", {"supplier_name": {"$regex": f"^{PREFIX}"}}),
        ("rahaza_grn_inspections", {"supplier_name": {"$regex": f"^{PREFIX}"}}),
    ]
    for coll, q in plans:
        if mids or "supplier_name" in json.dumps(q):
            res = await db[coll].delete_many(q)
            print(f"  - {coll}: {res.deleted_count}")
            total += res.deleted_count

    # jurnal hasil disposisi karantina — field memo/source_module (BUKAN description/reference:
    # skema JE di proyek ini memakai `memo` + `lines[]` embedded + koleksi rahaza_journal_lines)
    jes = [j async for j in db.rahaza_journal_entries.find(
        {"$or": [{"memo": {"$regex": PREFIX}},
                 {"description": {"$regex": PREFIX}},
                 {"reference": {"$regex": PREFIX}},
                 {"ref.material_id": {"$in": mids}}]}, {"_id": 0, "id": 1, "je_number": 1})]
    jids = [j["id"] for j in jes]
    if jids:
        # FK di rahaza_journal_lines = `je_id` (BUKAN journal_entry_id) — kalau salah field,
        # baris jurnal jadi YATIM setelah entry-nya dihapus.
        r1 = await db.rahaza_journal_lines.delete_many(
            {"$or": [{"je_id": {"$in": jids}}, {"journal_entry_id": {"$in": jids}}]})
        r2 = await db.rahaza_journal_entries.delete_many({"id": {"$in": jids}})
        print(f"  - rahaza_journal_lines: {r1.deleted_count}\n  - rahaza_journal_entries: {r2.deleted_count} "
              f"({', '.join(j.get('je_number', '') for j in jes)})")
        total += r1.deleted_count + r2.deleted_count

    # sapu baris jurnal yang memo/description-nya TEST-Q6 tapi entry-nya sudah lebih dulu hilang
    r3 = await db.rahaza_journal_lines.delete_many({"description": {"$regex": PREFIX}})
    if r3.deleted_count:
        print(f"  - rahaza_journal_lines (yatim): {r3.deleted_count}")
        total += r3.deleted_count

    print(f"TOTAL dihapus: {total}")
    print("sisa:", {
        "rahaza_materials": await db.rahaza_materials.count_documents({"code": {"$regex": f"^{PREFIX}"}}),
        "wh_quarantine_items": await db.wh_quarantine_items.count_documents({"material_id": {"$in": mids}}),
        "warehouse_receiving": await db.warehouse_receiving.count_documents({"supplier_name": {"$regex": f"^{PREFIX}"}}),
        "rahaza_journal_entries": await db.rahaza_journal_entries.count_documents({"memo": {"$regex": PREFIX}}),
    })
    return 0


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        sys.exit(asyncio.run(cleanup()))
    sys.exit(asyncio.run(seed()))
