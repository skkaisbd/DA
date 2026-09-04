"""POC ALUR CUTTING v2 — memakai DATA NYATA hasil seed (bukan material buatan).

Menguji ulang bug QA-1: stok kain tersimpan PER GUDANG, sehingga order cutting harus
memakai gudang yang benar-benar memegang stok.

Langkah:
  1. login admin
  2. ambil daftar kain dari /api/cutting/input-materials → pilih yang stoknya > 0
  3. verifikasi field stock_locations / best_location_id terisi
  4. buat order TANPA mengirim location_id  (backend harus memilih gudang berstok)
  5. start → tidak boleh 400
  6. progress → stok kain turun, potongan naik
  7. complete → HPP terisi
  8. verifikasi potongan muncul di master material gudang
  9. kasus negatif: kain berstok 0 → start harus ditolak dengan pesan jelas
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8001"
TOK = None


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 method=method)
    req.add_header("Content-Type", "application/json")
    if TOK:
        req.add_header("Authorization", f"Bearer {TOK}")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def step(name, ok, msg=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {msg}")
    if not ok:
        sys.exit(1)


print("=" * 84)
print("POC CUTTING v2 — data nyata + validasi lokasi stok")
print("=" * 84)

st, r = call("POST", "/api/auth/login", {"email": "admin@garment.com", "password": "Admin@123"})
step("login", st == 200 and r.get("token"), f"status={st}")
TOK = r["token"]

st, mats = call("GET", "/api/cutting/input-materials")
step("daftar-kain", st == 200 and isinstance(mats, list) and mats, f"{len(mats)} kain")
in_stock = [m for m in mats if float(m.get("stock_qty") or 0) > 5]
step("ada-kain-berstok", bool(in_stock), f"{len(in_stock)} kain punya stok > 5")
M = sorted(in_stock, key=lambda x: -float(x["stock_qty"]))[0]
print(f"       dipakai: {M['code']} — stok {M['stock_qty']} {M['unit']} @ {M.get('best_location_name')}")
step("stock_locations-terisi", bool(M.get("stock_locations") and M.get("best_location_id")),
     f"{M.get('stock_locations')}")

st, order = call("POST", "/api/cutting/orders", {
    "input_material_id": M["id"],
    "planned_input_qty": 5, "planned_output_qty": 40,
    "style_name": "POC Dress Nyata", "style_sku": "POC-NYATA",
    "output_color": M.get("color") or "HITAM", "output_size": "L",
    "notes": "POC v2 tanpa location_id — backend harus pilih gudang berstok",
})
step("buat-order", st == 200 and order.get("number"), f"{order.get('number')}")
OID = order["id"]
step("lokasi-otomatis-benar", order.get("location_id") == M.get("best_location_id"),
     f"lokasi order = {order.get('location_name')} (stok di sini {order.get('stock_at_create')})")

st, order = call("POST", f"/api/cutting/orders/{OID}/start")
step("start", st == 200 and order.get("status") == "in_progress",
     f"status={st} kode potongan={order.get('output_material_code')} detail={str(order)[:160] if st != 200 else ''}")

st, order = call("POST", f"/api/cutting/orders/{OID}/progress",
                 {"input_consumed": 2, "output_qty": 18, "waste_qty": 0.1, "note": "POC v2"})
step("progress", st == 200 and float(order.get("produced_qty") or 0) == 18,
     f"status={st} produced={order.get('produced_qty')} consumed={order.get('consumed_input_qty')} err={str(order)[:160] if st != 200 else ''}")

st, detail = call("GET", f"/api/cutting/orders/{OID}")
before = float(M["stock_qty"])
after = float(detail.get("input_stock") or 0)
step("stok-kain-berkurang", abs((before - after) - 2) < 0.001,
     f"{before} → {after} (turun {round(before - after, 3)} {M['unit']})")
step("stok-potongan-bertambah", float(detail.get("output_stock") or 0) == 18,
     f"potongan = {detail.get('output_stock')} pcs")

st, order = call("POST", f"/api/cutting/orders/{OID}/complete")
step("complete", st == 200 and order.get("status") == "completed",
     f"HPP potongan = {order.get('output_unit_cost')}")

code = order.get("output_material_code")
st, allmats = call("GET", f"/api/rahaza/materials?search={code}")
step("potongan-di-master-gudang", any(m.get("code") == code for m in allmats),
     f"{code} muncul di /api/rahaza/materials")

# ── kasus negatif: kain tanpa stok
zero = [m for m in mats if float(m.get("stock_qty") or 0) == 0]
if zero:
    Z = zero[0]
    st, o2 = call("POST", "/api/cutting/orders", {
        "input_material_id": Z["id"], "planned_input_qty": 1, "planned_output_qty": 1,
        "style_name": "POC Kain Kosong",
    })
    step("buat-order-kain-kosong", st == 200, f"{o2.get('number')}")
    st, err = call("POST", f"/api/cutting/orders/{o2['id']}/start")
    step("start-ditolak-dgn-pesan-jelas", st == 400 and "kosong di semua gudang" in str(err.get("detail", "")),
         f"status={st} detail={err.get('detail')}")
    call("DELETE", f"/api/cutting/orders/{o2['id']}")

print("=" * 84)
print("POC CUTTING v2 — SEMUA LANGKAH LULUS")
print("=" * 84)
