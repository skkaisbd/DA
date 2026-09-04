#!/usr/bin/env python3
"""
POC — KEPUTUSAN #2 (Marketing): Pisah harga katalog + HPP dari RnD (BOM auto-costing).

Membuktikan (grounded, via API + DB) rantai:
  RnD material master (unit_cost)
    -> Tech-pack BOM (bom_items)
      -> HPP RnD auto (material = Σ qty × unit_cost) + CMT/cutting/packaging/overhead (manual)
        -> promote style -> rahaza_models
          -> katalog marketing (model_id) hpp AUTO-REFRESH saat HPP RnD berubah
  + Field harga terpisah: harga_jual / harga_coret / harga_original / hpp (+ legacy sync)
  + Backward-compat item lama (hanya price/original_price)

Self-cleanup: semua dokumen uji dihapus di akhir (DB pristine).
Exit 0 = ALL PASS.
"""
import os
import sys
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

BASE = "http://localhost:8001/api"
load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

PASS, FAIL = 0, 0
created = {
    "materials": [], "styles": [], "tech_packs": [], "hpp": [],
    "models": [], "accounts": [], "catalogs": [], "items": [],
}


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {msg}")
    else:
        FAIL += 1
        print(f"  ❌ {msg}")


def approx(a, b, tol=1.0):
    return abs(float(a) - float(b)) <= tol


def login():
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def main():
    H = login()
    _purge_poc()  # pre-clean residu run sebelumnya (idempoten)
    print("\n== STEP A: seed material master (rahaza_materials.unit_cost) ==")
    import uuid
    fab_id, acc_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.rahaza_materials.insert_many([
        {"id": fab_id, "code": "POC-FAB-1", "name": "POC Cotton", "type": "fabric",
         "unit": "m", "unit_cost": 25000, "is_poc": True},
        {"id": acc_id, "code": "POC-ACC-1", "name": "POC Button", "type": "accessory",
         "unit": "pcs", "unit_cost": 1200, "is_poc": True},
    ])
    created["materials"] += [fab_id, acc_id]
    check(True, "2 material master seeded (fabric unit_cost=25000, acc unit_cost=1200)")

    print("\n== STEP B: create RnD style ==")
    r = requests.post(f"{BASE}/dewi/rnd/styles", headers=H,
                      json={"style_code": "POC-STYLE-1", "style_name": "POC Kaos Uji",
                            "category": "Kaos", "rnd_type": "internal_product"}, timeout=15)
    check(r.status_code == 200, f"create style -> {r.status_code}")
    style = r.json()
    style_id = style["id"]
    created["styles"].append(style_id)

    print("\n== STEP C: create tech-pack with BOM ==")
    bom = [
        {"material_id": fab_id, "material_code": "POC-FAB-1", "qty": 1.5, "unit": "m"},
        {"material_id": acc_id, "material_code": "POC-ACC-1", "qty": 3, "unit": "pcs"},
    ]
    expected_material = 1.5 * 25000 + 3 * 1200  # 41100
    r = requests.post(f"{BASE}/dewi/rnd/tech-packs", headers=H,
                      json={"style_id": style_id, "style_code": "POC-STYLE-1",
                            "style_name": "POC Kaos Uji", "bom_items": bom}, timeout=15)
    check(r.status_code == 200, f"create tech-pack -> {r.status_code}")
    created["tech_packs"].append(r.json()["id"])

    print("\n== STEP D: preview HPP from BOM (auto material cost) ==")
    manual = {"cmt_cost_per_pcs": 15000, "cutting_cost_per_pcs": 2000,
              "packaging_cost_per_pcs": 1000, "overhead_pct": 10, "margin_pct": 30}
    r = requests.post(f"{BASE}/dewi/rnd/hpp-calculator/compute-from-bom", headers=H,
                      json={"style_id": style_id, **manual}, timeout=15)
    check(r.status_code == 200, f"compute-from-bom -> {r.status_code}")
    calc = r.json()
    check(approx(calc["bom_material_cost"], expected_material),
          f"material cost auto dari BOM = {calc.get('bom_material_cost')} (expect {expected_material})")
    # direct = 41100+15000+2000+1000 = 59100; overhead 10% = 5910; hpp = 65010
    check(approx(calc["hpp_total"], 65010),
          f"hpp_total = {calc.get('hpp_total')} (expect 65010)")
    check(approx(calc["selling_price_proposal"], 65010 / 0.7, 2),
          f"selling_price_proposal = {calc.get('selling_price_proposal')} (expect ~{round(65010/0.7,2)})")
    check(len(calc.get("material_breakdown", [])) == 2, "material_breakdown punya 2 baris")
    check(all(b["cost_source"] == "rahaza_materials.unit_cost" for b in calc["material_breakdown"]),
          "unit_cost ter-resolve dari material master (rahaza_materials.unit_cost)")

    print("\n== STEP E: save HPP (use_bom) — auto-propagate (belum ada model/katalog) ==")
    r = requests.post(f"{BASE}/dewi/rnd/hpp-calculator", headers=H,
                      json={"style_id": style_id, "style_code": "POC-STYLE-1",
                            "style_name": "POC Kaos Uji", "use_bom": True, **manual}, timeout=15)
    check(r.status_code == 200, f"create HPP (use_bom) -> {r.status_code}")
    hpp_doc = r.json()
    hpp_id = hpp_doc["id"]
    created["hpp"].append(hpp_id)
    check(approx(hpp_doc["hpp_total"], 65010), f"saved hpp_total = {hpp_doc.get('hpp_total')}")
    check(hpp_doc.get("material_source") == "bom", "material_source = 'bom'")

    print("\n== STEP F: promote style -> production model ==")
    requests.post(f"{BASE}/dewi/rnd/styles/{style_id}/submit-for-review", headers=H, json={}, timeout=15)
    requests.post(f"{BASE}/dewi/rnd/styles/{style_id}/owner-approve", headers=H, json={}, timeout=15)
    r = requests.post(f"{BASE}/dewi/rnd/styles/{style_id}/promote-to-production", headers=H, json={}, timeout=15)
    check(r.status_code == 200, f"promote-to-production -> {r.status_code} {r.text[:120]}")
    model_id = r.json().get("model_id")
    check(bool(model_id), f"model_id created = {model_id}")
    if model_id:
        created["models"].append(model_id)

    print("\n== STEP G: create marketing account + catalog ==")
    r = requests.post(f"{BASE}/marketing/accounts", headers=H,
                      json={"account_code": "POC-ACC-SHOP", "account_name": "POC Toko",
                            "platform": "shopee"}, timeout=15)
    check(r.status_code in (200, 201), f"create account -> {r.status_code}")
    acc = r.json()
    acc_pk = acc.get("account", {}).get("id") or acc.get("id")
    created["accounts"].append(acc_pk)
    r = requests.post(f"{BASE}/marketing/catalogs", headers=H,
                      json={"account_id": acc_pk, "name": "POC Katalog", "platform": "shopee"}, timeout=15)
    check(r.status_code in (200, 201), f"create catalog -> {r.status_code} {r.text[:120]}")
    cat = r.json()
    catalog_id = cat.get("catalog", {}).get("id") or cat.get("id")
    created["catalogs"].append(catalog_id)
    check(bool(catalog_id), f"catalog_id = {catalog_id}")

    print("\n== STEP H: create catalog item w/ separated prices + model_id ==")
    r = requests.post(f"{BASE}/marketing/catalogs/{catalog_id}/items", headers=H,
                      json={"sku": "POC-SKU-1", "name": "POC Produk", "model_id": model_id,
                            "harga_jual": 150000, "harga_coret": 180000, "harga_original": 200000}, timeout=15)
    check(r.status_code in (200, 201), f"create item -> {r.status_code} {r.text[:150]}")
    item = r.json().get("item", {})
    item_id = item.get("id")
    created["items"].append(item_id)
    check(approx(item.get("harga_jual"), 150000), f"harga_jual={item.get('harga_jual')}")
    check(approx(item.get("harga_coret"), 180000), f"harga_coret={item.get('harga_coret')}")
    check(approx(item.get("harga_original"), 200000), f"harga_original={item.get('harga_original')}")
    check(approx(item.get("price"), 150000), f"legacy price sinkron ke harga_jual ({item.get('price')})")
    check(approx(item.get("original_price"), 180000), f"legacy original_price sinkron ke harga_coret ({item.get('original_price')})")

    print("\n== STEP I: propagate HPP -> catalog item.hpp AUTO ==")
    r = requests.post(f"{BASE}/dewi/rnd/hpp-calculator/{hpp_id}/propagate", headers=H, json={}, timeout=15)
    check(r.status_code == 200, f"propagate -> {r.status_code}")
    prop = r.json().get("propagation", {})
    check(prop.get("models", 0) >= 1, f"propagasi ke {prop.get('models')} model")
    check(prop.get("catalog_items", 0) >= 1, f"propagasi ke {prop.get('catalog_items')} item katalog")
    # GET item to confirm hpp set
    r = requests.get(f"{BASE}/marketing/catalogs/{catalog_id}/items", headers=H, timeout=15)
    items = r.json().get("items", [])
    it = next((x for x in items if x["id"] == item_id), {})
    check(approx(it.get("hpp"), 65010), f"item.hpp ter-refresh dari RnD = {it.get('hpp')} (expect 65010)")
    check(it.get("hpp_source") == "rnd", "item.hpp_source = 'rnd'")

    print("\n== STEP J: AUTO-REFRESH — ubah CMT di HPP -> item.hpp ikut berubah ==")
    r = requests.put(f"{BASE}/dewi/rnd/hpp-calculator/{hpp_id}", headers=H,
                     json={"style_id": style_id, "use_bom": True, "cmt_cost_per_pcs": 20000,
                           "cutting_cost_per_pcs": 2000, "packaging_cost_per_pcs": 1000,
                           "overhead_pct": 10, "margin_pct": 30}, timeout=15)
    check(r.status_code == 200, f"update HPP -> {r.status_code}")
    # direct = 41100+20000+2000+1000=64100; overhead 10%=6410; hpp=70510
    new_hpp = r.json().get("hpp_total")
    check(approx(new_hpp, 70510), f"HPP baru = {new_hpp} (expect 70510)")
    r = requests.get(f"{BASE}/marketing/catalogs/{catalog_id}/items", headers=H, timeout=15)
    it = next((x for x in r.json().get("items", []) if x["id"] == item_id), {})
    check(approx(it.get("hpp"), 70510), f"item.hpp AUTO-refresh = {it.get('hpp')} (expect 70510)")

    print("\n== STEP K: backward-compat item lama (hanya price/original_price) ==")
    legacy_id = str(uuid.uuid4())
    db.marketing_catalog_items.insert_one({
        "id": legacy_id, "catalog_id": catalog_id, "sku": "POC-LEGACY",
        "name": "POC Legacy", "price": 99000, "original_price": 120000,
        "is_active": True, "is_poc": True,
    })
    created["items"].append(legacy_id)
    r = requests.get(f"{BASE}/marketing/catalogs/{catalog_id}/items", headers=H, timeout=15)
    lit = next((x for x in r.json().get("items", []) if x["id"] == legacy_id), {})
    check(approx(lit.get("harga_jual"), 99000), f"legacy: harga_jual dipetakan dari price ({lit.get('harga_jual')})")
    check(approx(lit.get("harga_coret"), 120000), f"legacy: harga_coret dipetakan dari original_price ({lit.get('harga_coret')})")
    check(approx(lit.get("hpp"), 0), "legacy: hpp default 0 (belum tertaut RnD)")

    print("\n== STEP L: Refresh HPP dari RnD (item#1) — per-item + bulk ==")
    # kosongkan hpp item utama, lalu refresh per-item
    db.marketing_catalog_items.update_one({"id": item_id}, {"$set": {"hpp": 0}})
    r = requests.post(f"{BASE}/marketing/catalogs/{catalog_id}/items/{item_id}/refresh-hpp", headers=H, json={}, timeout=15)
    check(r.status_code == 200, f"refresh-hpp per-item -> {r.status_code}")
    check(approx(r.json().get("hpp"), 70510), f"per-item refresh hpp = {r.json().get('hpp')} (expect 70510)")
    check(r.json().get("source") == "rahaza_models", f"source = {r.json().get('source')}")
    # kosongkan lagi, lalu bulk refresh
    db.marketing_catalog_items.update_one({"id": item_id}, {"$set": {"hpp": 0}})
    r = requests.post(f"{BASE}/marketing/catalogs/{catalog_id}/refresh-hpp", headers=H, json={}, timeout=15)
    check(r.status_code == 200, f"refresh-hpp bulk -> {r.status_code}")
    check(r.json().get("updated") >= 1, f"bulk updated = {r.json().get('updated')}")
    r = requests.get(f"{BASE}/marketing/catalogs/{catalog_id}/items", headers=H, timeout=15)
    it = next((x for x in r.json().get("items", []) if x["id"] == item_id), {})
    check(approx(it.get("hpp"), 70510), f"item.hpp setelah bulk refresh = {it.get('hpp')} (expect 70510)")
    # legacy item tanpa sumber -> per-item refresh harus 400
    r = requests.post(f"{BASE}/marketing/catalogs/{catalog_id}/items/{legacy_id}/refresh-hpp", headers=H, json={}, timeout=15)
    check(r.status_code == 400, f"refresh-hpp item tanpa sumber ditolak 400 (got {r.status_code})")


def _purge_poc():
    """Hapus semua residu data POC (idempoten)."""
    db.rahaza_materials.delete_many({"is_poc": True})
    db.dewi_rnd_styles.delete_many({"style_code": {"$regex": "^POC-"}})
    db.dewi_rnd_tech_packs.delete_many({"style_code": {"$regex": "^POC-"}})
    db.dewi_rnd_hpp.delete_many({"style_code": {"$regex": "^POC-"}})
    db.rahaza_models.delete_many({"rnd_style_code": {"$regex": "^POC-"}})
    poc_accts = list(db.marketing_platform_accounts.find({"account_code": {"$regex": "^POC-"}}, {"id": 1}))
    acct_ids = [a["id"] for a in poc_accts]
    db.marketing_platform_accounts.delete_many({"account_code": {"$regex": "^POC-"}})
    poc_cats = list(db.marketing_catalogs.find({"$or": [{"name": {"$regex": "^POC "}}, {"account_id": {"$in": acct_ids}}]}, {"id": 1}))
    cat_ids = [c["id"] for c in poc_cats]
    db.marketing_catalogs.delete_many({"$or": [{"name": {"$regex": "^POC "}}, {"account_id": {"$in": acct_ids}}]})
    db.marketing_catalog_items.delete_many({"$or": [{"is_poc": True}, {"catalog_id": {"$in": cat_ids}}, {"sku": {"$regex": "^POC-"}}]})


def cleanup():
    print("\n== CLEANUP ==")
    try:
        _purge_poc()
        print("  ✅ cleanup done")
    except Exception as e:
        print(f"  ⚠️ cleanup error: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        FAIL += 1
    finally:
        cleanup()
    print(f"\n==== RESULT: {PASS} PASS / {FAIL} FAIL ====")
    sys.exit(0 if FAIL == 0 else 1)
