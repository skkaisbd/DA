#!/usr/bin/env python3
"""
POC — Phase 7A Fase 1: unified BOM materials[] end-to-end.

Membuktikan (via live API + 1 cek migrasi level-DB):
  1. Material master CRUD + kategori (rahaza_material_categories)
  2. BOM CRUD skema terunifikasi materials[] (create / read+enrich / update)
  3. Toleransi payload legacy (yarn_materials/accessory_materials → materials[])
  4. Preview kebutuhan (explode materials[] × qty)
  5. Copy-to-sizes
  6. Migrasi/reader legacy doc (get_bom_materials fallback) — insert doc legacy
     langsung ke Mongo lalu GET → wajib mengembalikan materials[] hasil konversi.

Jalankan: python3 /app/tests/poc_phase7a_bom_materials.py
"""
import os
import sys
import uuid
import requests
from datetime import datetime, timezone
from pymongo import MongoClient

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

_passed = 0
_failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ {name}  {detail}")


def login():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def main():
    print("=" * 70)
    print(" POC Phase 7A Fase 1 — Unified BOM materials[]")
    print("=" * 70)

    token = login()
    H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    db = MongoClient(MONGO_URL)[DB_NAME]

    # ── T1: categories ──────────────────────────────────────────────────────
    print("\n[T1] Material categories")
    cats = requests.get(f"{BASE}/api/rahaza/material-categories", headers=H, timeout=15).json()
    check("categories >= 3", len(cats) >= 3, f"got {len(cats)}")
    yarn_cat = next((c for c in cats if c["code"] == "YARN"), cats[0] if cats else {"code": "", "name": ""})

    # ── T2: material master CRUD + category ─────────────────────────────────
    print("\n[T2] Material master CRUD + kategori")
    code = f"POC-YRN-{uuid.uuid4().hex[:6].upper()}"
    body = {"code": code, "name": "POC Benang Test", "type": "yarn", "unit": "kg",
            "category": yarn_cat["code"], "category_name": yarn_cat["name"],
            "yarn_type": "Acrylic 100%"}
    r = requests.post(f"{BASE}/api/rahaza/materials", headers=H, json=body, timeout=15)
    check("create material HTTP 200", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
    mat = r.json() if r.status_code == 200 else {}
    check("material has category", mat.get("category") == yarn_cat["code"], f"cat={mat.get('category')}")
    lst = requests.get(f"{BASE}/api/rahaza/materials?type=yarn", headers=H, timeout=15).json()
    lst = lst if isinstance(lst, list) else lst.get("items", [])
    check("new material in yarn list", any(x.get("code") == code for x in lst), f"list={len(lst)}")

    # ── setup: model + sizes ─────────────────────────────────────────────────
    models = requests.get(f"{BASE}/api/rahaza/models", headers=H, timeout=15).json()
    sizes = [s for s in requests.get(f"{BASE}/api/rahaza/sizes", headers=H, timeout=15).json() if s.get("active")]
    if not models or len(sizes) < 2:
        print("‼️  Butuh minimal 1 model & 2 size. Jalankan seed-sample dulu."); sys.exit(1)
    model_id = models[0]["id"]
    # Pilih size yang BELUM punya BOM utk create bersih
    matrix = requests.get(f"{BASE}/api/rahaza/models/{model_id}/bom", headers=H, timeout=15).json()
    free = [row for row in matrix["matrix"] if not row["bom_id"]]
    used = [row for row in matrix["matrix"] if row["bom_id"]]
    target_size = free[0] if free else matrix["matrix"][0]
    size_id = target_size["size_id"]

    # ── T3: create BOM unified materials[] ──────────────────────────────────
    print("\n[T3] Create BOM (materials[] terunifikasi)")
    bom_body = {
        "model_id": model_id, "size_id": size_id, "color": "",
        "materials": [
            {"material_id": mat.get("id"), "code": code, "name": "POC Benang Test",
             "material_type": "yarn", "category": yarn_cat["code"], "category_name": yarn_cat["name"],
             "qty": 0.4, "unit": "kg", "notes": "utama"},
            {"code": "POC-ACC-BTN", "name": "Kancing POC", "material_type": "accessory",
             "category": "ACCESSORY", "category_name": "Aksesoris", "qty": 5, "unit": "pcs"},
        ],
        "notes": "POC BOM v1",
    }
    r = requests.post(f"{BASE}/api/rahaza/boms", headers=H, json=bom_body, timeout=15)
    check("create BOM HTTP 200", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
    bom = r.json() if r.status_code == 200 else {}
    bom_id = bom.get("id")
    check("materials[] len == 2", len(bom.get("materials", [])) == 2, str(bom.get("materials")))
    check("material_count == 2", bom.get("material_count") == 2, str(bom.get("material_count")))
    check("total_yarn_kg_per_pcs == 0.4", abs(float(bom.get("total_yarn_kg_per_pcs", 0)) - 0.4) < 1e-6,
          str(bom.get("total_yarn_kg_per_pcs")))
    check("yarn_count == 1", bom.get("yarn_count") == 1, str(bom.get("yarn_count")))
    check("category_name preserved", any(m.get("category_name") == "Aksesoris" for m in bom.get("materials", [])))

    # ── T4: GET enrich ──────────────────────────────────────────────────────
    print("\n[T4] GET BOM enrich")
    g = requests.get(f"{BASE}/api/rahaza/boms/{bom_id}", headers=H, timeout=15).json()
    check("GET returns materials[]", len(g.get("materials", [])) == 2)
    check("model_code enriched", bool(g.get("model_code")))
    check("no legacy yarn_materials field", "yarn_materials" not in g or not g.get("yarn_materials"))

    # ── T5: update BOM ──────────────────────────────────────────────────────
    print("\n[T5] Update BOM (PUT)")
    upd = {"materials": bom_body["materials"] + [
        {"code": "POC-LBL", "name": "Label POC", "material_type": "packaging", "qty": 1, "unit": "pcs"}],
        "notes": "POC BOM v1 (edited)"}
    r = requests.put(f"{BASE}/api/rahaza/boms/{bom_id}", headers=H, json=upd, timeout=15)
    check("update HTTP 200", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
    check("materials[] len == 3 after update", len(r.json().get("materials", [])) == 3)

    # ── T6: requirements preview (explode) ──────────────────────────────────
    print("\n[T6] Requirements preview (explode × qty)")
    r = requests.post(f"{BASE}/api/rahaza/boms/{bom_id}/requirements", headers=H,
                      json={"qty_pcs": 1000, "rounding": "none"}, timeout=15)
    check("requirements HTTP 200", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
    pr = r.json() if r.status_code == 200 else {}
    check("preview materials len == 3", len(pr.get("materials", [])) == 3)
    yarn_line = next((m for m in pr.get("materials", []) if m.get("code") == code), {})
    check("yarn qty_total == 400 (0.4*1000)", abs(float(yarn_line.get("qty_total", 0)) - 400) < 1e-6,
          str(yarn_line.get("qty_total")))
    check("total_yarn_kg == 400", abs(float(pr.get("total_yarn_kg", 0)) - 400) < 1e-6, str(pr.get("total_yarn_kg")))

    # ── T7: legacy-body tolerance ───────────────────────────────────────────
    print("\n[T7] Toleransi payload legacy (yarn_materials/accessory_materials)")
    legacy_size = None
    for row in requests.get(f"{BASE}/api/rahaza/models/{model_id}/bom", headers=H, timeout=15).json()["matrix"]:
        if not row["bom_id"] and row["size_id"] != size_id:
            legacy_size = row["size_id"]; break
    if legacy_size:
        legacy_body = {
            "model_id": model_id, "size_id": legacy_size, "color": "",
            "yarn_materials": [{"name": "Legacy Benang", "code": "LEG-YRN", "yarn_type": "cotton", "qty_kg": 0.25}],
            "accessory_materials": [{"name": "Legacy Kancing", "code": "LEG-ACC", "qty": 3, "unit": "pcs"}],
            "notes": "legacy payload",
        }
        r = requests.post(f"{BASE}/api/rahaza/boms", headers=H, json=legacy_body, timeout=15)
        check("legacy-body create HTTP 200", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
        lb = r.json() if r.status_code == 200 else {}
        check("legacy converted to materials[] (2)", len(lb.get("materials", [])) == 2, str(lb.get("materials")))
        ymat = next((m for m in lb.get("materials", []) if m.get("code") == "LEG-YRN"), {})
        check("legacy qty_kg -> qty 0.25", abs(float(ymat.get("qty", 0)) - 0.25) < 1e-6, str(ymat.get("qty")))
    else:
        check("legacy test skipped (no free size)", True)

    # ── T8: copy-to-sizes ───────────────────────────────────────────────────
    print("\n[T8] Copy-to-sizes")
    all_sizes = [s["id"] for s in sizes if s["id"] != size_id][:2]
    r = requests.post(f"{BASE}/api/rahaza/boms/{bom_id}/copy-to-sizes", headers=H,
                      json={"target_size_ids": all_sizes, "overwrite": True}, timeout=15)
    check("copy HTTP 200", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
    cp = r.json() if r.status_code == 200 else {}
    check("copy created+overwritten >= 1", len(cp.get("created", [])) + len(cp.get("overwritten", [])) >= 1, str(cp))

    # ── T9: migration/reader of a raw legacy doc (DB-level) ─────────────────
    print("\n[T9] Reader/migrasi doc legacy (insert raw ke Mongo)")
    raw_id = str(uuid.uuid4())
    db.rahaza_boms.insert_one({
        "id": raw_id, "model_id": model_id, "size_id": size_id, "color": "RAWLEGACY",
        "version": 1, "is_active": False, "active": True,
        "yarn_materials": [{"name": "Raw Yarn", "code": "RAW-YRN", "yarn_type": "wool", "qty_kg": 0.5}],
        "accessory_materials": [{"name": "Raw Zip", "code": "RAW-ZIP", "qty": 1, "unit": "pcs"}],
        "notes": "raw legacy doc", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
    })
    g = requests.get(f"{BASE}/api/rahaza/boms/{raw_id}", headers=H, timeout=15).json()
    check("legacy doc read as materials[] (2)", len(g.get("materials", [])) == 2, str(g.get("materials")))
    rawy = next((m for m in g.get("materials", []) if m.get("code") == "RAW-YRN"), {})
    check("raw yarn qty_kg 0.5 -> qty", abs(float(rawy.get("qty", 0)) - 0.5) < 1e-6, str(rawy.get("qty")))
    check("raw yarn type == yarn", rawy.get("material_type") == "yarn", str(rawy.get("material_type")))
    # cleanup raw doc
    db.rahaza_boms.delete_one({"id": raw_id})

    print("\n" + "=" * 70)
    print(f" RESULT: {_passed} passed / {_failed} failed")
    print("=" * 70)
    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    main()
