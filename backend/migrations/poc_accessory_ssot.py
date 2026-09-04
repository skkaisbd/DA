"""
POC: Accessory SSOT (Single Source of Truth) — End-to-End Flow Test

Membuktikan bahwa flow aksesoris (master + stock + movements) konsisten
ketika di-back oleh `rahaza_materials` / `rahaza_material_stock` / `rahaza_material_movements`,
bukan oleh `acc_items` / `acc_stock_movements`.

User stories yang ditest:
  US1. Admin membuat aksesoris via /api/acc/items (POST) -> tersimpan di rahaza_materials (type='accessory')
  US2. Admin menerima stok 10 pcs via /api/acc/stock/receive -> stok di rahaza_material_stock = 10
  US3. Admin issue 3 pcs via /api/acc/stock/issue -> saldo = 7, ada 2 movement record
  US4. /api/acc/stock list menunjukkan saldo 7 untuk item ini
  US5. /api/acc/stock/movements menunjukkan 2 record (IN dan OUT) untuk acc_id ini
  US6. /api/acc/dashboard menghitung total_items dengan benar (>=1)

Usage:
  cd /app/backend && python migrations/poc_accessory_ssot.py
"""
# ruff: noqa: E402

import asyncio
import sys
import httpx
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

BASE = "http://localhost:8001"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

# Use a fresh code per run to avoid collision
RUN_TAG = uuid.uuid4().hex[:6].upper()
TEST_CODE = f"POC-ACC-{RUN_TAG}"
TEST_NAME = f"POC Accessory {RUN_TAG}"


async def login(client: httpx.AsyncClient) -> str:
    r = await client.post(
        f"{BASE}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15.0,
    )
    r.raise_for_status()
    return r.json()["token"]


async def main():
    print(f"=== POC Accessory SSOT (run={RUN_TAG}) ===")
    results = []

    async with httpx.AsyncClient() as client:
        token = await login(client)
        H = {"Authorization": f"Bearer {token}"}
        print(f"[OK] Login as {ADMIN_EMAIL}")

        # US1: Create accessory item
        r = await client.post(
            f"{BASE}/api/acc/items",
            headers=H,
            json={
                "code": TEST_CODE,
                "name": TEST_NAME,
                "category": "Kancing",
                "unit": "pcs",
                "description": "POC test item",
                "min_stock": 5,
                "supplier": "PT POC Supplier",
                "notes": "POC SSOT test",
            },
            timeout=15.0,
        )
        assert r.status_code == 201, f"US1 FAILED: status={r.status_code}, body={r.text}"
        item = r.json()
        acc_id = item["id"]
        assert item["code"] == TEST_CODE
        assert item["name"] == TEST_NAME
        assert float(item.get("stock_qty", 0)) == 0
        results.append(("US1: Create accessory item", True, f"id={acc_id}"))
        print(f"[PASS] US1: Created accessory id={acc_id}")

        # Verify it's in rahaza_materials with type='accessory'
        from database import get_db  # type: ignore
        db = get_db()
        mat = await db.rahaza_materials.find_one({"id": acc_id}, {"_id": 0})
        assert mat is not None, "US1 FAILED: item not in rahaza_materials"
        assert mat.get("type") == "accessory", f"US1 FAILED: type={mat.get('type')} (expected accessory)"
        results.append(("US1.b: rahaza_materials has type='accessory'", True, f"type={mat['type']}"))
        print("[PASS] US1.b: rahaza_materials.type='accessory'")

        # Verify NOT in acc_items (SSOT moved)
        legacy = await db.acc_items.find_one({"id": acc_id})
        assert legacy is None, "US1 FAILED: should NOT be in acc_items (legacy)"
        results.append(("US1.c: acc_items legacy NOT used", True, "no doc in acc_items"))
        print("[PASS] US1.c: no legacy acc_items doc")

        # US2: Receive 10 pcs
        r = await client.post(
            f"{BASE}/api/acc/stock/receive",
            headers=H,
            json={"acc_id": acc_id, "qty": 10, "notes": "POC initial receive"},
            timeout=15.0,
        )
        assert r.status_code == 201, f"US2 FAILED: status={r.status_code}, body={r.text}"
        rj = r.json()
        assert float(rj["new_qty"]) == 10, f"US2 FAILED: new_qty={rj['new_qty']} expected 10"
        results.append(("US2: Receive 10 pcs -> saldo=10", True, f"new_qty={rj['new_qty']}"))
        print(f"[PASS] US2: Receive 10 pcs, saldo={rj['new_qty']}")

        # Verify rahaza_material_stock has 10 for this material
        stock_rows = await db.rahaza_material_stock.find({"material_id": acc_id}, {"_id": 0}).to_list(10)
        total_stock = sum(float(s.get("qty") or 0) for s in stock_rows)
        assert total_stock == 10, f"US2.b FAILED: rahaza_material_stock total={total_stock}"
        results.append(("US2.b: rahaza_material_stock = 10", True, f"sum_qty={total_stock}"))
        print(f"[PASS] US2.b: rahaza_material_stock sum={total_stock}")

        # Verify rahaza_material_movements has 1 receive record
        mv_count = await db.rahaza_material_movements.count_documents(
            {"material_id": acc_id, "type": "receive"}
        )
        assert mv_count >= 1, f"US2.c FAILED: receive movement count={mv_count}"
        results.append(("US2.c: receive movement logged", True, f"count={mv_count}"))
        print(f"[PASS] US2.c: receive movement count={mv_count}")

        # US3: Issue 3 pcs
        r = await client.post(
            f"{BASE}/api/acc/stock/issue",
            headers=H,
            json={"acc_id": acc_id, "qty": 3, "notes": "POC issue"},
            timeout=15.0,
        )
        assert r.status_code == 201, f"US3 FAILED: status={r.status_code}, body={r.text}"
        rj = r.json()
        assert float(rj["new_qty"]) == 7, f"US3 FAILED: new_qty={rj['new_qty']} expected 7"
        results.append(("US3: Issue 3 pcs -> saldo=7", True, f"new_qty={rj['new_qty']}"))
        print(f"[PASS] US3: Issue 3 pcs, saldo={rj['new_qty']}")

        # US4: /api/acc/stock list shows saldo 7
        r = await client.get(f"{BASE}/api/acc/stock", headers=H, timeout=15.0)
        r.raise_for_status()
        stocks = r.json()
        our = [s for s in stocks if s["id"] == acc_id]
        assert len(our) == 1, "US4 FAILED: item not in stock list"
        assert float(our[0]["stock_qty"]) == 7, f"US4 FAILED: stock_qty={our[0]['stock_qty']}"
        results.append(("US4: /api/acc/stock shows saldo=7", True, f"stock_qty={our[0]['stock_qty']}"))
        print("[PASS] US4: /api/acc/stock shows saldo=7")

        # US5: /api/acc/stock/movements shows 2 records
        r = await client.get(
            f"{BASE}/api/acc/stock/movements?acc_id={acc_id}",
            headers=H,
            timeout=15.0,
        )
        r.raise_for_status()
        movements = r.json()
        assert len(movements) >= 2, f"US5 FAILED: movements count={len(movements)}"
        # Check types present
        types_seen = {m.get("movement_type") for m in movements}
        assert "IN" in types_seen or "receive" in types_seen, f"US5 FAILED: no IN movement, types={types_seen}"
        assert "OUT" in types_seen or "issue" in types_seen, f"US5 FAILED: no OUT movement, types={types_seen}"
        results.append(("US5: /api/acc/stock/movements >= 2 records", True, f"count={len(movements)}, types={types_seen}"))
        print(f"[PASS] US5: movements count={len(movements)}, types={types_seen}")

        # US6: Dashboard
        r = await client.get(f"{BASE}/api/acc/dashboard", headers=H, timeout=15.0)
        r.raise_for_status()
        dash = r.json()
        assert int(dash.get("total_items", 0)) >= 1, f"US6 FAILED: total_items={dash.get('total_items')}"
        results.append(("US6: Dashboard total_items >= 1", True, f"total_items={dash['total_items']}"))
        print(f"[PASS] US6: Dashboard total_items={dash['total_items']}")

        # ── CLEANUP (optional, keep traces for inspection) ──
        # await db.rahaza_materials.delete_one({"id": acc_id})
        # await db.rahaza_material_stock.delete_many({"material_id": acc_id})
        # await db.rahaza_material_movements.delete_many({"material_id": acc_id})

    print()
    print("=== POC RESULTS ===")
    all_pass = True
    for name, ok, info in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name} ({info})")
        if not ok:
            all_pass = False
    print()
    if all_pass:
        print("POC ACCESSORY SSOT: SUCCESS")
        return 0
    else:
        print("POC ACCESSORY SSOT: FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
