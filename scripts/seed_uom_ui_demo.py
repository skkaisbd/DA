#!/usr/bin/env python3
"""seed_uom_ui_demo — data demo untuk PEMILIH SATUAN di 6 titik masuk/keluar stok.

Dibuat 2026-08-05 (ROADMAP P1). Semua dibuat lewat ENDPOINT RESMI supaya
invarian tetap terjaga (INV-UOM-*, INV-1, ledger, jurnal).

Yang disiapkan:
  1. Kemasan (uoms) pada 3 master material yang sudah ada → dropdown satuan
     punya pilihan "kemasan master", bukan hanya konversi global.
  2. 1 movement INBOUND menunggu scan  → Portal Gudang · Scan Gudang (Receiving)
  3. 1 penempatan put-away ke bin      → bin terisi, prasyarat Opname Gudang
  4. 1 Material Issue status DRAFT     → Pengeluaran Material (qty & satuan bisa diubah)
  5. 1 Cutting order status in_progress→ Portal Cutting (input progres per satuan)

Pakai:
  python3 scripts/seed_uom_ui_demo.py            # buat / perbarui (idempoten)
  python3 scripts/seed_uom_ui_demo.py --cleanup  # buang dokumen demo
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, "backend", ".env"))
except Exception:  # noqa: BLE001
    pass

import requests  # noqa: E402

API = os.environ.get("INTERNAL_API_URL", "http://localhost:8001")
NOTE = "DEMO UOM PICKER"


def hdr():
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=30)
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        raise SystemExit(f"login gagal: {r.status_code} {r.text[:200]}")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def ok(msg):
    print(f"  \033[92m✓\033[0m {msg}")


def warn(msg):
    print(f"  \033[93m!\033[0m {msg}")


def materials(h, **params):
    r = requests.get(f"{API}/api/rahaza/materials", headers=h, params=params, timeout=60)
    d = r.json() if r.status_code == 200 else []
    return d if isinstance(d, list) else d.get("items", [])


def cleanup(h):
    print("Membersihkan dokumen demo…")
    # Material Issue draft
    for mi in requests.get(f"{API}/api/rahaza/material-issues", headers=h, timeout=60).json() or []:
        if mi.get("notes") == NOTE:
            requests.delete(f"{API}/api/rahaza/material-issues/{mi['id']}", headers=h, timeout=30)
            ok(f"MI {mi.get('mi_number')} dihapus")
    # Pending movement
    for mv in requests.get(f"{API}/api/wms/pending", headers=h, timeout=60).json() or []:
        if mv.get("notes") == NOTE and mv.get("status") in ("pending", "partial"):
            requests.post(f"{API}/api/wms/pending/{mv['id']}/cancel", headers=h, timeout=30,
                          json={"reason": NOTE})
            ok(f"movement {mv.get('ref_number')} dibatalkan")
    # Cutting order (draft/in_progress → cancel, lalu hapus bila draft)
    for o in (requests.get(f"{API}/api/cutting/orders", headers=h, timeout=60).json() or []):
        if o.get("notes") == NOTE:
            requests.post(f"{API}/api/cutting/orders/{o['id']}/cancel", headers=h, timeout=30,
                          json={"reason": NOTE})
            requests.delete(f"{API}/api/cutting/orders/{o['id']}", headers=h, timeout=30)
            ok(f"cutting {o.get('number')} dibatalkan")
    print("Selesai. (kemasan master & penempatan bin dibiarkan — bagian dari master data)")


def seed_packs(h):
    print("1/5 Kemasan (uoms) pada master material")
    accs = [m for m in materials(h, type="accessory") if (m.get("unit") or "").lower() == "pcs"]
    yarns = [m for m in materials(h, type="yarn") if (m.get("unit") or "").lower() == "kg"]
    plan = []
    if accs:
        plan.append((accs[0], [
            {"code": "pcs", "name": "PCS", "factor": 1, "is_base": True, "level": 0},
            {"code": "box", "name": "BOX", "factor": 12, "level": 1, "parent": "pcs",
             "is_purchase_default": True, "is_display_default": True},
            {"code": "karton", "name": "KARTON", "factor": 144, "level": 2, "parent": "box"},
        ]))
    if len(accs) > 1:
        plan.append((accs[1], [
            {"code": "pcs", "name": "PCS", "factor": 1, "is_base": True, "level": 0},
            {"code": "pak", "name": "PAK", "factor": 100, "level": 1, "parent": "pcs",
             "is_purchase_default": True},
        ]))
    if yarns:
        plan.append((yarns[0], [
            {"code": "kg", "name": "KG", "factor": 1, "is_base": True, "level": 0},
            {"code": "rol", "name": "ROL", "factor": 25, "level": 1, "parent": "kg",
             "is_purchase_default": True},
        ]))
    for mat, uoms in plan:
        r = requests.put(f"{API}/api/rahaza/materials/{mat['id']}", headers=h, timeout=30,
                         json={"uoms": uoms, "unit": mat.get("unit")})
        if r.status_code == 200:
            ok(f"{mat['code']}: " + " · ".join(f"1 {u['code']} = {u['factor']} {uoms[0]['code']}"
                                               for u in uoms[1:]))
        else:
            warn(f"{mat['code']} gagal: {r.status_code} {r.text[:160]}")
    return (accs[0] if accs else None), (yarns[0] if yarns else None)


def seed_receiving(h, acc):
    print("2/5 Movement INBOUND menunggu scan (Portal Gudang → Scan Gudang)")
    if not acc:
        warn("tidak ada aksesoris — dilewati")
        return
    for mv in requests.get(f"{API}/api/wms/pending", headers=h, timeout=60).json() or []:
        if mv.get("notes") == NOTE and mv.get("status") in ("pending", "partial"):
            ok(f"sudah ada: {mv['ref_number']} ({mv['expected_qty']} {mv['unit']})")
            return
    r = requests.post(f"{API}/api/wms/pending", headers=h, timeout=30, json={
        "type": "inbound", "source_type": "manual", "material_id": acc["id"],
        "material_code": acc["code"], "material_name": acc["name"],
        "material_type": "accessory", "expected_qty": 240, "unit": "pcs", "notes": NOTE,
    })
    if r.status_code == 200:
        ok(f"{r.json()['movement']['ref_number']}: 240 pcs — coba scan 20 box")
    else:
        warn(f"gagal: {r.status_code} {r.text[:160]}")


def seed_putaway(h, acc):
    print("3/5 Penempatan put-away ke bin (prasyarat Opname Gudang)")
    if not acc:
        warn("tidak ada aksesoris — dilewati")
        return
    locs = requests.get(f"{API}/api/wms/putaway/locations", headers=h, timeout=30).json()
    pos = next((p for p in (locs.get("positions") or []) if p.get("is_empty")), None)
    pend = requests.get(f"{API}/api/wms/putaway/pending", headers=h, timeout=30).json()
    row = next((x for x in (pend.get("groups", {}).get("aksesoris") or [])
                if x["material_id"] == acc["id"] and x.get("unshelved", 0) >= 24), None)
    if not pos or not row:
        warn("tidak ada bin kosong / stok belum dirak yang cukup — dilewati")
        return
    r = requests.post(f"{API}/api/wms/putaway/place", headers=h, timeout=30, json={
        "material_id": acc["id"], "qty": 2, "position_id": pos["id"], "input_uom": "box",
    })
    if r.status_code == 200:
        ok(f"2 box (=24 pcs) {acc['code']} → {pos.get('full_label') or pos.get('label')}")
    else:
        warn(f"gagal: {r.status_code} {r.text[:200]}")


def seed_mi_draft(h, acc, yarn):
    print("4/5 Material Issue DRAFT (Pengeluaran Material)")
    for mi in requests.get(f"{API}/api/rahaza/material-issues", headers=h, timeout=60).json() or []:
        if mi.get("notes") == NOTE and mi.get("status") == "draft":
            ok(f"sudah ada: {mi['mi_number']}")
            return
    locs = requests.get(f"{API}/api/rahaza/locations", headers=h, timeout=30).json() or []
    loc_id = next((x["id"] for x in locs if x.get("active")), None)
    items = []
    if acc:
        items.append({"material_id": acc["id"], "qty_required": 24, "location_id": loc_id})
    if yarn:
        items.append({"material_id": yarn["id"], "qty_required": 5, "location_id": loc_id})
    if not items:
        warn("tidak ada material — dilewati")
        return
    r = requests.post(f"{API}/api/rahaza/material-issues", headers=h, timeout=30,
                      json={"notes": NOTE, "items": items})
    if r.status_code == 200:
        ok(f"{r.json()['mi_number']} draft — qty & satuan bisa diubah di layar")
    else:
        warn(f"gagal: {r.status_code} {r.text[:200]}")


def seed_cutting(h, yarn):
    print("5/5 Cutting order in_progress (Portal Cutting)")
    for o in (requests.get(f"{API}/api/cutting/orders", headers=h, timeout=60).json() or []):
        if o.get("notes") == NOTE and o.get("status") == "in_progress":
            ok(f"sudah ada: {o['number']}")
            return
    fab = None
    for m in materials(h, type="Bahan"):
        if (m.get("unit") or "").lower() in ("kg", "m") and not m.get("is_cut_panel"):
            fab = m
            break
    fab = fab or yarn
    if not fab:
        warn("tidak ada kain/benang bersatuan kg/m — dilewati")
        return
    r = requests.post(f"{API}/api/cutting/orders", headers=h, timeout=30, json={
        "input_material_id": fab["id"], "planned_input_qty": 50, "planned_output_qty": 200,
        "style_name": "Demo Satuan Cutting", "notes": NOTE,
    })
    if r.status_code != 200:
        warn(f"buat order gagal: {r.status_code} {r.text[:200]}")
        return
    oid = r.json()["id"]
    s = requests.post(f"{API}/api/cutting/orders/{oid}/start", headers=h, timeout=30, json={})
    if s.status_code == 200:
        ok(f"{r.json()['number']} ({fab['code']} {fab.get('unit')}) → in_progress")
    else:
        warn(f"start gagal: {s.status_code} {s.text[:200]}")


def main():
    h = hdr()
    if "--cleanup" in sys.argv:
        cleanup(h)
        return 0
    print("=" * 68)
    print(" SEED DEMO — PEMILIH SATUAN DI TITIK MASUK/KELUAR STOK")
    print("=" * 68)
    acc, yarn = seed_packs(h)
    seed_receiving(h, acc)
    seed_putaway(h, acc)
    seed_mi_draft(h, acc, yarn)
    seed_cutting(h, yarn)
    print("=" * 68)
    print(" Selesai. Layar yang bisa dicoba:")
    print("  • Portal Gudang → Scan Gudang (scan-in: pilih satuan box)")
    print("  • Portal Gudang → Put-Away (qty + satuan + pratinjau konversi)")
    print("  • Portal Gudang → Opname Scan (jumlah & satuan per scan)")
    print("  • Portal Gudang → Pengeluaran Material (qty & satuan per baris)")
    print("  • Portal Aksesoris → Master & Stok (terima/keluarkan per box/pak)")
    print("  • Portal Aksesoris → Stok Opname (satuan hitung per baris)")
    print("  • Portal Cutting → detail order → input progres (satuan pemakaian)")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
