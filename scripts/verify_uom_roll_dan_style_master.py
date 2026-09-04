#!/usr/bin/env python3
"""verify_uom_roll_dan_style_master.py — SESI #30 (keluhan pemilik, 2026-08-21).

GATE **INV-F35** — "SATUAN GULUNGAN JUJUR, STYLE POTONGAN DARI MASTER, HARGA
SATUAN LAHIR DARI PEMBELIAN."

═══════════════════════════════════════════════════════════════════════════════
KEADAAN SEBELUM PERBAIKAN (terukur, keluhan verbatim pemilik)
═══════════════════════════════════════════════════════════════════════════════
1. *"ketika purchasing itu yard namun di tracking roll menjadi meter jadinya yang
   diterima tidak sesuai dengan apa yang di PO … di roll itu jangan di paksakan
   meter agar uomnya jadi tidak kacau"*
   Yang diukur: TIDAK ADA konversi yang benar-benar terjadi (PO 650 yard →
   diterima 520 → reject 130 ⇒ 390 yard dibagi 4 gulungan @97,5). Yang salah:
     · `core/fabric_roll_engine.ROLL_UOM` MEMAKSA `rol`/`gulung` → `meter`;
     · layar Roll Kain menulis kolomnya mati sebagai "Sisa / Total **(m)**" dan
       membaca `remaining_m`/`length_m` (nama field warisan) sebagai "meter";
     · dialog Issue punya pilihan satuan meter/kg: gulungan YARD yang dikeluarkan
       sebagai "meter" tetap mengurangi angka yard (label bohong), dan bila
       dipilih "kg" sistem menjawab "sisa 0" padahal gulungannya penuh.
2. *"ketika cutting harusnya ini nama produk atau style mengambil dari master
   data … jadi ketika pembuatan bom dan ketika produksi sudah jelas ini produk ada"*
   Yang diukur: `POST /api/cutting/orders` menerima `style_name` sebagai KETIKAN
   BEBAS dan tidak menyimpan `model_id` apa pun ⇒ order potongan tidak pernah
   menunjuk model di master (`rahaza_models`), padahal BOM disimpan per
   model+size. Satu style bisa punya banyak ejaan.
3. *"untuk harga satuan otomatis dari pembelian purchase order, jangan dari input
   ketika masterdata … untuk semua jenis kain maupun aksesoris"*
   Yang diukur: mesin HPP rata-rata bergerak (`core/accessory_valuation`) HANYA
   dipanggil dari penerimaan aksesoris; **Penerimaan Barang (GR) dari PO tidak
   pernah menyentuh harga**, sehingga harga hanya bisa diketik di Master Item.

INVARIAN YANG DIJAGA
--------------------
  U1  Satuan gulungan = SATUAN MATERIAL; `rol`/`gulung` tidak lagi dipaksa meter
  U2  API gulungan mengirim satuan + jumlah apa adanya (`uom`, `qty_total`,
      `qty_remaining`) plus info konversi (`qty_*_m`) — bukan menebak dari nama field
  U3  Mengeluarkan gulungan dengan satuan LAIN ditolak 400 (bukan diam-diam)
  U4  Layar Roll Kain memakai satuan dari data (tak ada lagi "(m)" yang dipaksakan)
  U5  Order cutting WAJIB menunjuk model master; identitasnya (nama/kode/warna/
      size) diambil dari master, bukan ketikan
  U6  Order cutting tidak bisa "lepas" dari master lewat pengubahan nama style
  U7  Layar cutting menyediakan pilihan model + varian + tombol "Model Baru"
  U8  HARGA LAHIR DARI PEMBELIAN: GR bernilai memperbarui HPP material
      (rata-rata bergerak) & mencatat harga beli terakhir — untuk kain maupun aksesoris
  U9  Harga TIDAK bisa diketik dari Master Item (perubahan diabaikan + diberi
      penjelasan), dan layar master menampilkannya sebagai angka turunan
  U10 ALAT UKUR BERSIH: seluruh artefak uji (material, PO, GR, gulungan, karantina,
      order cutting, stok, ledger) dihapus kembali

Pakai:  python3 scripts/verify_uom_roll_dan_style_master.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

API = os.environ.get("API_BASE", "http://localhost:8001")
G, R, C, B, X = "\033[92m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
PASS, FAIL = [], []
STAMP = time.strftime("F35%H%M%S")
MARK = f"gate INV-F35 {STAMP}"

FE_ROLL = ROOT / "frontend/src/components/erp/WMSFabricRollsModule.jsx"
FE_CUT = ROOT / "frontend/src/components/erp/cutting/CuttingOrdersModule.jsx"
FE_MAT = ROOT / "frontend/src/components/erp/RahazaMaterialsModule.jsx"


def ok(code, msg, detail=""):
    PASS.append(code)
    print(f"  {G}✓{X} {code} — {msg}" + (f" · {detail}" if detail else ""))


def bad(code, msg, detail=""):
    FAIL.append(code)
    print(f"  {R}✗ {code} — {msg}{X}" + (f" · {detail}" if detail else ""))


def head(t):
    print(f"\n{C}{B}{t}{X}")


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {"raw": raw[:200].decode(errors="ignore")}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def det(d):
    return str((d or {}).get("detail") or (d or {}).get("error") or d)[:140]


def cleanup(db, ctx):
    mids = [m for m in [ctx.get("mid")] if m]
    cuts = list(db.cutting_orders.find({"notes": MARK}, {"_id": 0, "id": 1, "output_material_id": 1}))
    cut_ids = [c["id"] for c in cuts]
    out_mids = [c.get("output_material_id") for c in cuts if c.get("output_material_id")]
    rids = [r["id"] for r in db.wh_fabric_rolls.find({"material_id": {"$in": mids}}, {"_id": 0, "id": 1})]
    gr_ids = [g for g in [ctx.get("gr_id")] if g]
    gr_nos = [g for g in [ctx.get("gr_no")] if g]
    for coll, q in (
        ("wh_fabric_roll_movements", {"roll_id": {"$in": rids}}),
        ("wh_fabric_rolls", {"id": {"$in": rids}}),
        ("wh_quarantine_items", {"material_id": {"$in": mids}}),
        # Sesi #32 — nama field yang benar adalah `cutting_order_id` (bukan
        # `order_id`), jadi dulu baris progres alat ukur ini tidak pernah terhapus.
        ("cutting_progress", {"cutting_order_id": {"$in": cut_ids}}),
        ("cutting_orders", {"id": {"$in": cut_ids}}),
        ("rahaza_stock_ledger", {"material_id": {"$in": mids + out_mids}}),
        ("rahaza_material_stock", {"material_id": {"$in": mids + out_mids}}),
        ("warehouse_movements", {"material_id": {"$in": mids + out_mids}}),
        # Sesi #33 — alat ukur ini MEMBELI kain (harga lahir dari pembelian) dan
        # MEMOTONGNYA (nilai potongan lahir, sesi #32). Kedua peristiwa itu
        # menulis `rahaza_material_cost_history`, tetapi baris riwayatnya dulu
        # TIDAK dihapus ⇒ setiap kali gate.sh dijalankan, 3 baris riwayat harga
        # YATIM (materialnya sudah tidak ada) menumpuk di layar Riwayat Harga
        # Barang milik pemilik. Terukur: 10 dari 19 baris riwayat adalah sampah
        # alat ukur. Dijaga sekarang oleh INV-F38 C16 (keadaan akhir: 0 yatim).
        ("rahaza_material_cost_history", {"material_id": {"$in": mids + out_mids}}),
        ("warehouse_receiving", {"id": {"$in": gr_ids}}),
        ("rahaza_purchase_orders", {"id": {"$in": [p for p in [ctx.get("po_id")] if p]}}),
        ("rahaza_materials", {"id": {"$in": mids + out_mids}}),
        ("rahaza_journal_entries", {"reference": {"$in": gr_nos}}),
        ("journal_entries", {"reference": {"$in": gr_nos}}),
    ):
        try:
            db[coll].delete_many(q)
        except Exception:  # noqa: BLE001
            pass


def main():
    print(f"{C}{B}INV-F35 — SATUAN GULUNGAN, STYLE DARI MASTER, HARGA DARI PEMBELIAN{X}")
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    from gr_common import db_handle
    db = db_handle()
    ctx: dict = {}

    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}){X}")
        return 2

    try:
        # ── U1 — pemetaan satuan tidak lagi memaksa meter ───────────────────
        head("U1 — satuan gulungan mengikuti satuan material")
        from core.fabric_roll_engine import ROLL_UOM, roll_uom
        paksa = {k: v for k, v in ROLL_UOM.items()
                 if k in ("rol", "gulung") and v == "meter"}
        if paksa or roll_uom("yard") != "yard":
            bad("U1", "satuan gulungan masih dipaksakan", f"{paksa or roll_uom('yard')}")
        else:
            ok("U1", "yard→yard · rol→rol · gulung→gulung · kg→kg (tidak ada pemaksaan meter)",
               f"{ROLL_UOM['yard']}/{ROLL_UOM['rol']}/{ROLL_UOM['gulung']}")

        # ── Siapkan alur nyata: material YARD → PO → GR → gulungan ─────────
        head("U2/U3/U8 — alur nyata: kain YARD dibeli, diterima, jadi gulungan")
        st, mat = call("POST", "/api/rahaza/materials", token, {
            "code": f"GF35-KAIN-{STAMP}", "name": f"Kain Gate F35 {STAMP}",
            "type": "fabric", "unit": "yard", "color": "Navy", "notes": MARK})
        if st != 200 or not mat.get("id"):
            bad("U2", "gagal menyiapkan material uji", det(mat))
            return 1
        ctx["mid"] = mat["id"]

        st, po = call("POST", "/api/rahaza/purchase-orders", token, {
            "vendor_name": f"Pemasok Gate {STAMP}", "notes": MARK,
            "items": [{"material_id": ctx["mid"], "uom": "yard",
                       "qty_input": 650, "unit_cost_input": 42000}]})
        ctx["po_id"] = po.get("id")
        st, _ = call("POST", f"/api/rahaza/purchase-orders/{ctx['po_id']}/submit", token, {"notes": MARK})
        for _ in range(4):
            st, r = call("POST", f"/api/rahaza/purchase-orders/{ctx['po_id']}/approve", token,
                         {"notes": MARK})
            if (r or {}).get("status") == "approved":
                break
        st, gr = call("POST", f"/api/rahaza/purchase-orders/{ctx['po_id']}/create-gr", token, {})
        ctx["gr_id"], ctx["gr_no"] = gr.get("id"), gr.get("receipt_number")
        if not ctx["gr_id"]:
            bad("U2", "gagal membuat penerimaan dari PO", det(gr))
            return 1
        st, locs = call("GET", "/api/warehouse/locations", token)
        locs = locs if isinstance(locs, list) else (locs or {}).get("items") or []
        loc = next((x for x in locs if x.get("id")), {})
        items = [{**it, "received_qty": 520, "rejected_qty": 130,
                  "location_id": loc.get("id"),
                  "rolls": [{"qty": 97.5} for _ in range(4)]} for it in (gr.get("items") or [])]
        st, upd = call("PUT", f"/api/warehouse/receiving/{ctx['gr_id']}", token,
                       {"status": "received", "items": items, "location_id": loc.get("id")})
        rolls_created = (upd or {}).get("rolls_created") or []
        if st != 200 or len(rolls_created) != 4:
            bad("U2", "penerimaan + penerbitan gulungan gagal", f"HTTP {st} · {det(upd)}")
            return 1

        st, rl = call("GET", f"/api/wms/fabric-rolls?material_id={ctx['mid']}", token)
        rows = (rl or {}).get("items") or []
        r0 = rows[0] if rows else {}
        salah = [k for k in ("uom", "qty_total", "qty_remaining", "qty_total_m") if k not in r0]
        if salah:
            bad("U2", "API gulungan tidak mengirim satuan/jumlah apa adanya", f"hilang={salah}")
        elif r0["uom"] != "yard" or abs(r0["qty_total"] - 97.5) > 0.01:
            bad("U2", "gulungan tidak memakai satuan & angka PO",
                f"uom={r0['uom']} total={r0['qty_total']}")
        elif abs((r0.get("qty_total_m") or 0) - 89.15) > 0.05:
            bad("U2", "info konversi ke meter tidak benar", f"{r0.get('qty_total_m')}")
        else:
            ok("U2", "gulungan terbit dalam SATUAN PO (yard) + info konversi meter",
               f"{len(rows)} gulungan @{r0['qty_total']} {r0['uom']} (≈{r0['qty_total_m']} m) "
               f"= {round(sum(x['qty_total'] for x in rows), 2)} yard dari 520−130 diterima")

        st_bad, res_bad = call("POST", f"/api/wms/fabric-rolls/{r0.get('id')}/issue", token,
                               {"qty": 1, "unit": "meter", "reference_type": "manual"})
        st_ok, res_ok = call("POST", f"/api/wms/fabric-rolls/{r0.get('id')}/issue", token,
                             {"qty": 1, "unit": "yard", "reference_type": "manual",
                              "notes": MARK})
        if st_bad != 400 or "yard" not in det(res_bad):
            bad("U3", "pengeluaran dengan satuan salah TIDAK ditolak",
                f"HTTP {st_bad} · {det(res_bad)}")
        elif st_ok != 200 or abs(float((res_ok or {}).get("remaining", 0)) - 96.5) > 0.01:
            bad("U3", "pengeluaran dengan satuan benar gagal", f"HTTP {st_ok} · {det(res_ok)}")
        else:
            ok("U3", "satuan pengeluaran wajib sama dengan satuan gulungan",
               f"'meter' ditolak 400 · 'yard' berhasil (sisa {res_ok.get('remaining')} yard)")

        st, m2 = call("GET", f"/api/rahaza/materials/{ctx['mid']}", token)
        if float((m2 or {}).get("unit_cost") or 0) != 42000:
            bad("U8", "HPP tidak mengikuti harga pembelian PO",
                f"unit_cost={m2.get('unit_cost')} (harga PO 42000)")
        elif (m2.get("cost_method") or "") != "moving_average" or \
                float(m2.get("last_receipt_unit_cost") or 0) != 42000:
            bad("U8", "jejak sumber harga tidak lengkap",
                f"metode={m2.get('cost_method')} terakhir={m2.get('last_receipt_unit_cost')}")
        else:
            ok("U8", "harga satuan LAHIR dari harga PO saat barang diterima",
               f"Rp{int(float(m2['unit_cost'])):,} / {m2.get('unit')} · metode "
               f"{m2['cost_method']} · harga beli terakhir Rp{int(float(m2['last_receipt_unit_cost'])):,}")

        # ── U9 — harga tidak bisa diketik dari master ───────────────────────
        head("U9 — harga tidak bisa diketik dari Master Item")
        st, m3 = call("PUT", f"/api/rahaza/materials/{ctx['mid']}", token, {"unit_cost": 999})
        if st != 200:
            bad("U9", "menyimpan master jadi gagal total", f"HTTP {st} · {det(m3)}")
        elif float((m3 or {}).get("unit_cost") or 0) != 42000 or not m3.get("harga_satuan_catatan"):
            bad("U9", "harga masih bisa ditimpa dari master (atau tanpa penjelasan)",
                f"unit_cost={m3.get('unit_cost')} catatan={bool(m3.get('harga_satuan_catatan'))}")
        else:
            fe = FE_MAT.read_text(encoding="utf-8")
            if "mat-cost-derived" not in fe or "mat-cost-value" not in fe:
                bad("U9", "layar master belum menampilkan harga sebagai angka turunan")
            else:
                ok("U9", "harga master tidak bisa diketik; layar menampilkannya sebagai turunan",
                   f"kiriman 999 diabaikan → tetap {int(float(m3['unit_cost'])):,}")

        # ── U5/U6 — order cutting dari master ──────────────────────────────
        head("U5/U6 — order potongan wajib menunjuk model master")
        st_free, res_free = call("POST", "/api/cutting/orders", token, {
            "input_material_id": ctx["mid"], "planned_input_qty": 10,
            "planned_output_qty": 5, "style_name": f"Ketikan Bebas {STAMP}",
            "notes": MARK})
        st, models = call("GET", "/api/rahaza/models", token)
        models = models if isinstance(models, list) else (models or {}).get("items") or []
        model = next((m for m in models if m.get("active") is not False), None)
        if not model:
            st, model = call("POST", "/api/rahaza/models", token,
                             {"code": f"MDL-F35-{STAMP}", "name": f"Model Gate {STAMP}"})
            ctx["model_created"] = model.get("id")
        st, vars_ = call("GET", f"/api/rahaza/models/{model['id']}/variants", token)
        vars_ = vars_ if isinstance(vars_, list) else (vars_ or {}).get("items") or []
        st_m, order = call("POST", "/api/cutting/orders", token, {
            "input_material_id": ctx["mid"], "planned_input_qty": 10,
            "planned_output_qty": 5, "model_id": model["id"],
            "variant_id": (vars_[0]["id"] if vars_ else ""),
            "location_id": loc.get("id"), "notes": MARK})
        if st_free != 400 or "master" not in det(res_free).lower():
            bad("U5", "order cutting masih bisa dibuat dengan style ketikan bebas",
                f"HTTP {st_free} · {det(res_free)}")
        elif st_m != 200 or not order.get("model_id") or \
                order.get("style_name") != model.get("name"):
            bad("U5", "order cutting dari master tidak menyimpan identitas master",
                f"HTTP {st_m} · {det(order)}")
        else:
            ok("U5", "style/produk potongan diambil dari master (BOM & produksi bisa mengenalinya)",
               f"{order['number']} → {order['style_name']} ({order.get('style_sku') or 'tanpa kode'})"
               f"{' · ' + order['output_color'] if order.get('output_color') else ''}"
               f"{' · ' + order['output_size'] if order.get('output_size') else ''}")

        st_put, res_put = call("PUT", f"/api/cutting/orders/{order.get('id')}", token,
                               {"style_name": "Ganti Nama Bebas"})
        if st_put != 400:
            bad("U6", "nama style masih bisa dilepaskan dari master lewat PUT",
                f"HTTP {st_put} · {det(res_put)}")
        else:
            ok("U6", "nama style tidak bisa diketik ulang; harus lewat model master",
               det(res_put)[:80])

        # ── U4/U7 — layar ───────────────────────────────────────────────────
        head("U4/U7 — layar memakai satuan dari data & pilihan master")
        roll_fe = FE_ROLL.read_text(encoding="utf-8")
        kurang4 = []
        if "Sisa / Total (m)" in roll_fe or "Sisa / Total (kg)" in roll_fe:
            kurang4.append("kolom masih menulis satuan mati (m)/(kg)")
        for probe in ("rollUom(", "qty_remaining_m", 'data-testid={`roll-uom-'):
            if probe not in roll_fe:
                kurang4.append(f"layar tidak memakai '{probe}'")
        if kurang4:
            bad("U4", "layar Roll Kain masih memaksakan satuan", "; ".join(kurang4))
        else:
            ok("U4", "layar Roll Kain memakai satuan dari data + info konversi meter")

        cut_fe = FE_CUT.read_text(encoding="utf-8")
        kurang7 = [p for p in ("cutting-model-select", "cutting-variant-select",
                               "cutting-new-model-btn", "new-model-submit")
                   if p not in cut_fe]
        if "cutting-style-name" in cut_fe:
            kurang7.append("kolom ketikan nama style masih ada")
        if kurang7:
            bad("U7", "layar cutting belum memakai master produk", "; ".join(kurang7))
        else:
            ok("U7", "layar cutting: pilih model + varian dari master, plus tombol Model Baru")

    finally:
        head("U10 — alat ukur tidak mengotori")
        cleanup(db, ctx)
        sisa = {
            "material": db.rahaza_materials.count_documents({"notes": MARK}),
            "po": db.rahaza_purchase_orders.count_documents({"notes": MARK}),
            "gr": db.warehouse_receiving.count_documents(
                {"id": {"$in": [g for g in [ctx.get("gr_id")] if g]}}),
            "cutting": db.cutting_orders.count_documents({"notes": MARK}),
            "gulungan": db.wh_fabric_rolls.count_documents(
                {"material_id": {"$in": [m for m in [ctx.get("mid")] if m]}}),
            "karantina": db.wh_quarantine_items.count_documents(
                {"material_id": {"$in": [m for m in [ctx.get("mid")] if m]}}),
        }
        if any(sisa.values()):
            bad("U10", "gate meninggalkan artefak di basis data", f"{sisa}")
        else:
            ok("U10", "semua artefak uji dihapus (material, PO, GR, gulungan, karantina, order)")

    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian satuan/master/harga terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
