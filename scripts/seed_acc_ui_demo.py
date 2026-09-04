#!/usr/bin/env python3
"""seed_acc_ui_demo — data uji UI untuk ACC-1/2/3 (dibuat lewat ALUR NYATA).

Menyiapkan:
  ACC-3  3 aset alat (2 siap dipinjam, 1 sedang dipinjam & TERLAMBAT)
  ACC-2  3 master material (1 kain + 2 aksesoris) + 1 BOM aktif yang baris
         aksesorisnya sudah tertaut ke master
  ACC-1  1 PO internal 120 pcs → kebutuhan aksesoris ter-explode dari BOM
         (stok kosong ⇒ semua baris "Kurang", siap dijadikan permintaan)

Pakai:
  python scripts/seed_acc_ui_demo.py            # buat
  python scripts/seed_acc_ui_demo.py --cleanup  # bersihkan
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8001")
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
PREFIX = "TEST-AU"


def H(t):
    return {"Authorization": f"Bearer {t}"}


def _rows(d):
    return d if isinstance(d, list) else (d.get("items") or [])


async def seed():
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{BASE}/api/auth/login", json=ADMIN)
        if r.status_code != 200:
            print(f"✗ login gagal: {r.status_code} {r.text[:120]}")
            return 1
        tok = r.json()["token"]
        h = H(tok)

        # ── ACC-3: aset + 1 pinjaman terlambat ───────────────────────────────
        r = await c.get(f"{BASE}/api/assets/categories", headers=h)
        cats = _rows(r.json())
        cat = next((x for x in cats if (x.get("code") or "") == "AP"), cats[0] if cats else None)
        if not cat:
            print("✗ tidak ada kategori aset")
            return 1

        assets = []
        for nm, brand, cost in [
            ("Mesin Obras Portabel", "Juki", 4500000),
            ("Bor Listrik Bengkel", "Bosch", 1250000),
            ("Trolley Kain Besar", "Lokal", 850000),
        ]:
            r = await c.post(f"{BASE}/api/assets", headers=h, json={
                "name": f"{PREFIX} {nm}", "category_id": cat["id"],
                "purchase_date": date.today().isoformat(), "purchase_cost": cost,
                "location": "Gudang Alat", "brand": brand, "department": "Produksi",
                "serial_number": f"{PREFIX}-{nm[:3].upper()}-001"})
            if r.status_code in (200, 201):
                assets.append(r.json())
        print(f"  ✓ {len(assets)} aset alat dibuat")

        if assets:
            r = await c.post(f"{BASE}/api/assets/loans", headers=h, json={
                "asset_id": assets[0]["id"],
                "borrower_name": f"{PREFIX} Budi Operator", "borrower_divisi": "Produksi",
                "purpose": "perbaikan mesin jahit line 2",
                "loan_date": (date.today() - timedelta(days=6)).isoformat(),
                "expected_return_date": (date.today() - timedelta(days=2)).isoformat(),
                "notes": "dibawa bersama 1 set kunci L"})
            if r.status_code in (200, 201):
                d = r.json()
                print(f"  ✓ pinjaman aktif TERLAMBAT: {d['loan_number']} ({d.get('days_overdue')} hari)")
            else:
                print(f"  ! gagal buat pinjaman: {r.status_code} {r.text[:140]}")

        # ── ACC-2: master material + BOM aktif ──────────────────────────────
        async def ensure_mat(code, name, mtype, unit, cost):
            r = await c.post(f"{BASE}/api/rahaza/materials", headers=h, json={
                "code": code, "name": name, "type": mtype, "unit": unit,
                "unit_cost": cost, "min_stock": 0, "category": "TEST"})
            if r.status_code in (200, 201):
                return r.json()
            r2 = await c.get(f"{BASE}/api/rahaza/materials?search={code}", headers=h)
            return next((x for x in _rows(r2.json()) if x.get("code") == code), {})

        kain = await ensure_mat(f"{PREFIX}-KAIN", f"{PREFIX} Kain Cotton Combed 24s", "fabric", "kg", 92000)
        btn = await ensure_mat(f"{PREFIX}-BTN", f"{PREFIX} Kancing Metal 15mm", "accessory", "pcs", 950)
        lbl = await ensure_mat(f"{PREFIX}-LBL", f"{PREFIX} Label Woven Brand", "accessory", "pcs", 420)
        print(f"  ✓ master material: {kain.get('code')}, {btn.get('code')}, {lbl.get('code')}")

        r = await c.get(f"{BASE}/api/rahaza/models", headers=h)
        models = [m for m in _rows(r.json()) if m.get("active")]
        r = await c.get(f"{BASE}/api/rahaza/sizes", headers=h)
        sizes = [s for s in _rows(r.json()) if s.get("active")]
        if not (models and sizes):
            print("  ! tidak ada master model/size — BOM & PO dilewati")
            return 0
        model, size = models[0], sizes[0]

        r = await c.post(f"{BASE}/api/rahaza/boms", headers=h, json={
            "model_id": model["id"], "size_id": size["id"], "color": f"{PREFIX}-WARNA",
            "notes": f"{PREFIX} BOM demo ACC-1/ACC-2",
            "materials": [
                {"material_id": kain["id"], "code": kain["code"], "name": kain["name"],
                 "material_type": "fabric", "qty": 0.32, "unit": "kg"},
                {"material_id": btn["id"], "code": btn["code"], "name": btn["name"],
                 "material_type": "accessory", "qty": 5, "unit": "pcs"},
                {"material_id": lbl["id"], "code": lbl["code"], "name": lbl["name"],
                 "material_type": "accessory", "qty": 2, "unit": "pcs"},
            ]})
        if r.status_code not in (200, 201):
            print(f"  ! gagal buat BOM: {r.status_code} {r.text[:180]}")
            return 0
        bom = r.json()
        await c.post(f"{BASE}/api/rahaza/boms/{bom['id']}/activate", headers=h, json={})
        print(f"  ✓ BOM aktif v{bom.get('version')} (3 baris, aksesoris tertaut master)")

        # ── ACC-1: PO internal → kebutuhan aksesoris otomatis ───────────────
        r = await c.post(f"{BASE}/api/production-pos", headers=h, json={
            "po_number": f"{PREFIX}-PO-DEMO", "business_type": "internal",
            "customer_name": "Gudang FG Sendiri", "po_date": date.today().isoformat(),
            "deadline": (date.today() + timedelta(days=21)).isoformat(),
            "notes": f"{PREFIX} demo kebutuhan aksesoris otomatis",
            "items": [{"model_id": model["id"], "size_id": size["id"], "qty": 120,
                       "color": f"{PREFIX}-WARNA", "product_name": model.get("name", "")}]})
        if r.status_code not in (200, 201):
            print(f"  ! gagal buat PO: {r.status_code} {r.text[:200]}")
            return 0
        po = r.json()
        exp = po.get("accessories_explode") or {}
        print(f"  ✓ PO internal {po['po_number']} (120 pcs) — explode BOM: "
              f"{exp.get('rows')} baris, tertaut {exp.get('linked_rows')}")

        r = await c.get(f"{BASE}/api/production-pos/{po['id']}/accessory-requirements", headers=h)
        if r.status_code == 200:
            d = r.json()
            for q in d.get("requirements", []):
                print(f"     · {q.get('material_code')} butuh {q.get('qty_needed')} {q.get('unit')} "
                      f"· tersedia {q.get('available')} · kurang {q.get('shortage')} · {q.get('status')}")
            print(f"     summary: {d.get('summary')}")
        print("\n  Siap untuk uji UI:")
        print("   #asset-loans        → Peminjaman Alat (1 terlambat, 2 aset siap dipinjam)")
        print("   #rnd-bom / BOM      → banner kesehatan kopling + indikator tertaut")
        print(f"   #prod-po → detail PO {PREFIX}-PO-DEMO → Kebutuhan Aksesoris + tombol Buat Permintaan")
        return 0


async def cleanup():
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "test_database")]
    mids = [m["id"] async for m in db.rahaza_materials.find(
        {"code": {"$regex": f"^{PREFIX}"}}, {"_id": 0, "id": 1})]
    pos = [p["id"] async for p in db.production_pos.find(
        {"po_number": {"$regex": f"^{PREFIX}"}}, {"_id": 0, "id": 1})]
    total = 0
    plans = [
        ("dewi_asset_loans", {"borrower_name": {"$regex": PREFIX}}),
        ("dewi_asset_maintenance", {"asset_name": {"$regex": PREFIX}}),
        ("dewi_assets", {"name": {"$regex": PREFIX}}),
        ("dewi_accessory_requests", {"po_number": {"$regex": PREFIX}}),
        ("po_accessories", {"po_id": {"$in": pos}}),
        ("po_items", {"po_number": {"$regex": f"^{PREFIX}"}}),
        ("production_pos", {"po_number": {"$regex": f"^{PREFIX}"}}),
        ("rahaza_boms", {"color": {"$regex": PREFIX}}),
        ("rahaza_material_stock", {"material_id": {"$in": mids}}),
        ("rahaza_stock_ledger", {"material_id": {"$in": mids}}),
        ("rahaza_materials", {"code": {"$regex": f"^{PREFIX}"}}),
    ]
    for coll, q in plans:
        res = await db[coll].delete_many(q)
        if res.deleted_count:
            print(f"  - {coll}: {res.deleted_count}")
        total += res.deleted_count
    print(f"TOTAL dihapus: {total}")
    return 0


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        sys.exit(asyncio.run(cleanup()))
    sys.exit(asyncio.run(seed()))
