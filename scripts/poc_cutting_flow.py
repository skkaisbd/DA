"""POC ALUR CUTTING — bukti alur inti bekerja sebelum UI dibangun.

Skenario (end-to-end, data nyata di DB dev):
  1. login admin
  2. buat master material KAIN (unit kg) + tambah stok awal lewat penyesuaian gudang
  3. buat Cutting Order  -> draft
  4. start                -> in_progress + master POTONGAN otomatis terbentuk
  5. input progress 2x    -> stok kain berkurang, stok potongan bertambah (ledger)
  6. complete             -> HPP potongan terhitung
  7. verifikasi: potongan muncul di master material & bisa dipakai Material Issue
"""
import json
import os
import sys
import urllib.request

BASE = "http://localhost:8001"
TOK = None


def call(method, path, body=None, expect=(200, 201)):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if TOK:
        req.add_header("Authorization", f"Bearer {TOK}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.loads(r.read().decode() or "{}")
            return r.status, out
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def step(n, ok, msg):
    print(f"  [{'PASS' if ok else 'FAIL'}] {n} — {msg}")
    if not ok:
        sys.exit(1)


print("=" * 80)
print("POC PORTAL CUTTING")
print("=" * 80)

st, r = call("POST", "/api/auth/login", {"email": "admin@garment.com", "password": "Admin@123"})
step("login", st == 200 and r.get("token"), f"status={st}")
TOK = r["token"]

# ── 1. Master kain
code = "POC-KAIN-RAYON-HITAM"
st, mats = call("GET", f"/api/rahaza/materials?search={code}")
mat = next((m for m in (mats if isinstance(mats, list) else []) if m.get("code") == code), None)
if not mat:
    st, mat = call("POST", "/api/rahaza/materials", {
        "code": code, "name": "POC Rayon Twill Hitam", "type": "fabric", "unit": "kg",
        "color": "HITAM", "unit_cost": 55000, "category": "FABRIC",
    })
    step("create-kain", st in (200, 201) and mat.get("id"), f"status={st} {str(mat)[:180]}")
else:
    print("  [INFO] material kain POC sudah ada, dipakai ulang")
MAT_ID = mat["id"]

# ── 2. Lokasi + stok awal kain
st, locs = call("GET", "/api/rahaza/locations")
step("locations", st == 200 and isinstance(locs, list) and locs, f"status={st}")
LOC = locs[0]["id"]

st, before = call("GET", f"/api/rahaza/material-stock?material_id={MAT_ID}")
st, r = call("POST", "/api/rahaza/material-receive", {
    "material_id": MAT_ID, "location_id": LOC, "qty": 100,
    "unit_cost": 55000, "ref_type": "receiving", "notes": "POC cutting — stok awal",
})
step("stok-awal-kain", st in (200, 201), f"status={st} {str(r)[:200]}")

# ── 3. Buat cutting order
st, order = call("POST", "/api/cutting/orders", {
    "input_material_id": MAT_ID,
    "planned_input_qty": 20,
    "planned_output_qty": 120,
    "style_name": "Dress Jemina",
    "style_sku": "SP-JEMINA",
    "output_color": "HITAM",
    "output_size": "L",
    "location_id": LOC,
    "notes": "POC alur cutting",
})
step("create-order", st in (200, 201) and order.get("number"), f"status={st} {str(order)[:200]}")
OID = order["id"]
print(f"       nomor = {order['number']}, status = {order['status']}")

# ── 4. Start
st, order = call("POST", f"/api/cutting/orders/{OID}/start")
step("start", st == 200 and order.get("status") == "in_progress",
     f"status={st} {str(order)[:200]}")
OUT_CODE = order.get("output_material_code")
OUT_ID = order.get("output_material_id")
step("output-material-dibuat", bool(OUT_ID and OUT_CODE), f"kode potongan = {OUT_CODE}")

# ── 5. Progress 2x
st, order = call("POST", f"/api/cutting/orders/{OID}/progress",
                 {"input_consumed": 8, "output_qty": 50, "waste_qty": 0.4, "note": "shift pagi"})
step("progress-1", st == 200 and order.get("produced_qty") == 50,
     f"produced={order.get('produced_qty')} consumed={order.get('consumed_input_qty')}")
st, order = call("POST", f"/api/cutting/orders/{OID}/progress",
                 {"input_consumed": 9, "output_qty": 62, "waste_qty": 0.5, "note": "shift siang"})
step("progress-2", st == 200 and order.get("produced_qty") == 112,
     f"produced={order.get('produced_qty')} consumed={order.get('consumed_input_qty')}")

# ── 6. Cek stok bergerak
st, detail = call("GET", f"/api/cutting/orders/{OID}")
print(f"       stok kain sekarang    = {detail.get('input_stock')}")
print(f"       stok potongan sekarang= {detail.get('output_stock')}")
step("stok-potongan-bertambah", _ := (float(detail.get("output_stock") or 0) >= 112),
     f"output_stock={detail.get('output_stock')}")

# ── 7. Complete + HPP
st, order = call("POST", f"/api/cutting/orders/{OID}/complete")
step("complete", st == 200 and order.get("status") == "completed",
     f"status={st} unit_cost_potongan={order.get('output_unit_cost')}")
expected = round(17 * 55000 / 112, 2)
step("hpp-benar", abs(float(order.get("output_unit_cost") or 0) - expected) < 1.0,
     f"HPP potongan = {order.get('output_unit_cost')} (harusnya ≈ {expected})")

# ── 8. Potongan terlihat sebagai master material (siap jadi BOM / Material Issue)
st, outs = call("GET", "/api/cutting/output-materials")
found = next((m for m in outs if m.get("code") == OUT_CODE), None)
step("potongan-di-master", bool(found), f"{OUT_CODE} ada di master potongan, stok={found and found.get('stock_qty')}")

st, allmats = call("GET", f"/api/rahaza/materials?search={OUT_CODE}")
found2 = next((m for m in (allmats if isinstance(allmats, list) else []) if m.get("code") == OUT_CODE), None)
step("potongan-di-master-gudang", bool(found2),
     f"{OUT_CODE} muncul di /api/rahaza/materials (dropdown Material Issue)")

# ── 9. Dashboard
st, dash = call("GET", "/api/cutting/dashboard")
step("dashboard", st == 200 and dash.get("total_orders", 0) >= 1,
     f"orders={dash.get('total_orders')} produced={dash.get('produced_qty')} yield={dash.get('avg_yield')}")

print("=" * 80)
print("SEMUA LANGKAH POC CUTTING LULUS")
print("=" * 80)
