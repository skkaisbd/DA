#!/usr/bin/env python3
"""scenario_selisih_ssot.py — UJI TUNGGAL untuk SELISIH KIRIM CMT→DA & DA→BUYER.

Sumber kebenaran: memory/HANDOFF_SELISIH_CMT_BUYER.md (§1 aturan owner, §7 rancangan)
+ keputusan owner 2026-08-01:
  1. Selisih CMT→DA bukan klaim otomatis: dokumen vendor DIKOREKSI ke qty yang
     benar-benar diterima DA, dan sisa kirim vendor NAIK lagi supaya bisa dikirim ulang.
  2. Selisih DA→buyer diperlakukan sama (bisa ketinggalan / salah hitung → kirim ulang);
     keputusan finance (tanggungan CMT / DA) baru diambil saat PO ditutup.
  3. Koreksi deklarasi boleh sepihak oleh Admin DA + NOTIFIKASI ke vendor (tanpa sanggahan).
  4. Tanpa batas waktu: selisih tetap `open` sampai diselesaikan.

Jalankan:  python3 tests/scenario_selisih_ssot.py
Bersih-bersih: python3 tests/scenario_selisih_ssot.py --clean
"""
from __future__ import annotations

import io
import sys
import time
from datetime import date

import requests
from pymongo import MongoClient

API = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
VENDOR_EMAIL = "ujicmt@dewiaditya.id"
VENDOR_PASS = "Dewi@123"
VENDOR_ID = "uji-vendor-cmt-ssot"
MARK = "UJI-SELISIH"

G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
S = time.strftime("%H%M%S")

env = {}
for line in open("/app/backend/.env", encoding="utf-8"):
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')
db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]

PASS: list[str] = []
FAIL: list[str] = []


def ok(name, detail=""):
    PASS.append(name)
    print(f"  {G}✓ {name}{X} {detail}")


def bad(name, detail=""):
    FAIL.append(name)
    print(f"  {R}✗ {name}{X} {detail}")


def check(name, cond, detail=""):
    (ok if cond else bad)(name, detail)
    return bool(cond)


TOK = ""
VTOK = ""


def H(tok=None):
    return {"Authorization": f"Bearer {tok or TOK}", "Content-Type": "application/json"}


def call(m, p, body=None, ok_codes=(200, 201), tok=None, quiet=False):
    r = requests.request(m, f"{API}{p}", headers=H(tok), json=body, timeout=180)
    try:
        d = r.json()
    except Exception:
        d = {"raw": r.text[:200]}
    if not quiet:
        tag = f"{G}{r.status_code}{X}" if r.status_code in ok_codes else f"{R}{r.status_code}{X}"
        print(f"    {tag} {m} {p} {'' if r.status_code in ok_codes else str(d)[:300]}")
    return r.status_code, d


def fg_stock(sku: str) -> float:
    mat = db.rahaza_materials.find_one({"code": sku}, {"_id": 0, "id": 1})
    if not mat:
        return -1
    return sum(float(x.get("qty") or 0) for x in
               db.rahaza_material_stock.find({"material_id": mat["id"]}, {"_id": 0, "qty": 1}))


# ═══════════════════════════════════════════════════════════════════════════
# 0. BOOTSTRAP MASTER MINIMAL (vendor CMT + user vendor) — idempoten
# ═══════════════════════════════════════════════════════════════════════════
def bootstrap():
    global TOK, VTOK
    TOK = requests.post(f"{API}/api/auth/login", json=ADMIN, timeout=60).json()["token"]
    if not db.vendor_partners.find_one({"id": VENDOR_ID}):
        db.vendor_partners.insert_one({
            "id": VENDOR_ID, "code": "UJI-CMT-SSOT", "name": "CV Uji Jahit SSOT",
            "garment_name": "CV Uji Jahit SSOT", "garment_code": "UJI-CMT-SSOT",
            "partner_type": "cmt", "phone": "0800000000", "address": "Uji",
            "active": True, "notes": MARK,
        })
    u = db.users.find_one({"email": VENDOR_EMAIL})
    if not u:
        st, _ = call("POST", "/api/users", {
            "name": "Vendor Uji SSOT", "email": VENDOR_EMAIL, "password": VENDOR_PASS,
            "role": "cmt_vendor", "vendor_id": VENDOR_ID, "cmt_vendor_id": VENDOR_ID,
        }, ok_codes=(201, 409))
    else:
        db.users.update_one({"email": VENDOR_EMAIL},
                            {"$set": {"vendor_id": VENDOR_ID, "cmt_vendor_id": VENDOR_ID,
                                      "role": "cmt_vendor", "status": "active"}})
    VTOK = requests.post(f"{API}/api/auth/login",
                         json={"email": VENDOR_EMAIL, "password": VENDOR_PASS},
                         timeout=60).json().get("token", "")
    print(f"  token admin={'ok' if TOK else 'GAGAL'} · token vendor={'ok' if VTOK else 'GAGAL'}")


def make_po(sku: str, qty: int, label: str, buyer="UJI Buyer Selisih"):
    """PO → kirim material → terima → inspeksi → job → progres (jalur ALAMI)."""
    st, po = call("POST", "/api/production-pos", {
        "po_number": f"{MARK}-{label}-{S}", "business_type": "maklon", "vendor_id": VENDOR_ID,
        "customer_name": buyer, "status": "Confirmed", "notes": MARK,
        "po_date": str(date.today()), "deadline": str(date.today()),
        "items": [{"product_name": f"Kaos Uji {label}", "sku": sku, "size": "L",
                   "color": "Hitam", "qty": qty}]})
    poi = db.po_items.find_one({"po_id": po["id"]}, {"_id": 0})
    st, vs = call("POST", "/api/vendor-shipments", {
        "shipment_number": f"{MARK}-SJM-{label}-{S}", "vendor_id": VENDOR_ID, "po_id": po["id"],
        "po_number": po["po_number"], "shipment_date": str(date.today()),
        "shipment_type": "NORMAL", "notes": MARK,
        "items": [{"po_id": po["id"], "po_item_id": poi["id"], "sku": sku,
                   "product_name": poi.get("product_name", ""), "size": poi.get("size", ""),
                   "color": poi.get("color", ""), "qty_sent": qty}]})
    call("PUT", f"/api/vendor-shipments/{vs['id']}", {"status": "Received"})
    vsi = db.vendor_shipment_items.find_one({"shipment_id": vs["id"]}, {"_id": 0})
    call("POST", "/api/vendor-material-inspections", {
        "shipment_id": vs["id"], "vendor_id": VENDOR_ID, "inspection_date": str(date.today()),
        "overall_notes": MARK,
        "items": [{"shipment_item_id": vsi["id"], "sku": sku, "ordered_qty": qty,
                   "received_qty": qty, "missing_qty": 0}]})
    st, job = call("POST", "/api/production-jobs",
                   {"vendor_shipment_id": vs["id"], "vendor_id": VENDOR_ID, "po_id": po["id"]})
    ji = db.production_job_items.find_one({"job_id": job["id"]}, {"_id": 0})
    call("POST", "/api/production-progress", {"job_item_id": ji["id"], "completed_quantity": qty,
                                              "progress_date": str(date.today())})
    return po, poi, job, db.production_job_items.find_one({"id": ji["id"]}, {"_id": 0})


def vendor_declare(po, ji, sku, qty):
    """Vendor CMT deklarasi kirim ke DA (otomatis membuat penerimaan DA)."""
    st, d = call("POST", "/api/buyer-shipments", {
        "po_id": po["id"], "job_id": ji["job_id"], "shipment_date": str(date.today()),
        "notes": MARK,
        "items": [{"po_item_id": ji["po_item_id"], "job_item_id": ji["id"], "sku": sku,
                   "product_name": ji.get("product_name", ""), "qty_shipped": qty}]},
        tok=VTOK)
    ship_id = d.get("id")
    rid = d.get("related_cmt_receipt_id")
    rec = (db.cmt_receipts.find_one({"id": rid}, {"_id": 0}) if rid else None)
    if not rec:
        rec = db.cmt_receipts.find_one({"related_shipment_id": ship_id}, {"_id": 0},
                                       sort=[("created_at", -1)])
    return d, rec


def ledger(job_item_id):
    return db.production_job_items.find_one({"id": job_item_id}, {"_id": 0}) or {}


# ═══════════════════════════════════════════════════════════════════════════
def clean():
    po_ids = [p["id"] for p in db.production_pos.find({"notes": MARK}, {"_id": 0, "id": 1})]
    po_ids += [p["id"] for p in db.production_pos.find(
        {"po_number": {"$regex": f"^{MARK}"}}, {"_id": 0, "id": 1})]
    po_ids = list(set(po_ids))
    n = 0
    for pid in po_ids:
        item_ids = [i["id"] for i in db.po_items.find({"po_id": pid}, {"_id": 0, "id": 1})]
        job_ids = [j["id"] for j in db.production_jobs.find({"po_id": pid}, {"_id": 0, "id": 1})]
        ji_ids = [j["id"] for j in db.production_job_items.find(
            {"po_item_id": {"$in": item_ids}}, {"_id": 0, "id": 1})]
        rc_ids = [r["id"] for r in db.cmt_receipts.find({"po_id": pid}, {"_id": 0, "id": 1})]
        bs_ids = [s["id"] for s in db.buyer_shipments.find(
            {"$or": [{"po_id": pid}, {"po_ids": pid}]}, {"_id": 0, "id": 1})]
        for coll, q in (
            ("po_items", {"po_id": pid}), ("production_jobs", {"po_id": pid}),
            ("production_job_items", {"id": {"$in": ji_ids}}),
            ("cmt_receipt_lines", {"receipt_id": {"$in": rc_ids}}),
            ("cmt_receipts", {"id": {"$in": rc_ids}}),
            ("cmt_short_shipments", {"po_id": pid}),
            ("buyer_short_records", {"po_id": pid}),
            ("buyer_shipment_items", {"shipment_id": {"$in": bs_ids}}),
            ("buyer_shipments", {"id": {"$in": bs_ids}}),
            ("vendor_shipment_items", {"po_id": pid}),
            ("vendor_shipments", {"po_id": pid}),
            ("production_pos", {"id": pid}),
            ("dewi_maklon_pos", {"id": pid}),
        ):
            try:
                n += db[coll].delete_many(q).deleted_count
            except Exception:
                pass
    for coll in ("rahaza_fg_movements", "rahaza_stock_ledger", "wh_quarantine_items",
                 "rahaza_material_stock", "rahaza_materials", "notifications"):
        try:
            if coll == "rahaza_materials":
                mats = [m["id"] for m in db.rahaza_materials.find(
                    {"code": {"$regex": f"^{MARK}"}}, {"_id": 0, "id": 1})]
                n += db.rahaza_material_stock.delete_many({"material_id": {"$in": mats}}).deleted_count
                n += db.rahaza_materials.delete_many({"id": {"$in": mats}}).deleted_count
            elif coll == "notifications":
                n += db.notifications.delete_many({"body": {"$regex": MARK}}).deleted_count
            else:
                n += db[coll].delete_many({"sku_code": {"$regex": f"^{MARK}"}}).deleted_count
        except Exception:
            pass
    print(f"bersih-bersih: {n} dokumen uji dihapus")


# ═══════════════════════════════════════════════════════════════════════════
def main():  # noqa: C901
    print(f"{C}{B}{'═' * 88}\nUJI SSOT SELISIH KIRIM — CMT→DA & DA→BUYER\n{'═' * 88}{X}")
    print(f"\n{C}0. Bootstrap master minimal{X}")
    bootstrap()

    # ───────────────────────────────────────────────────────────────────────
    # BAGIAN A — SELISIH KIRIM CMT→DA (klaim 100, sampai 90)
    # ───────────────────────────────────────────────────────────────────────
    sku_a = f"{MARK}-A-{S}"
    print(f"\n{C}A1. PO 100 pcs + job + produksi 100 (jalur alami){X}")
    po_a, poi_a, job_a, ji_a = make_po(sku_a, 100, "A")

    print(f"\n{C}A2. Vendor deklarasi kirim 100 pcs ke DA{X}")
    decl, rec_a = vendor_declare(po_a, ji_a, sku_a, 100)
    check("A2 penerimaan DA otomatis terbentuk dari deklarasi vendor", bool(rec_a),
          f"receipt={(rec_a or {}).get('receipt_code')}")
    if not rec_a:
        return finish()
    line_a = db.cmt_receipt_lines.find_one({"receipt_id": rec_a["id"]}, {"_id": 0})
    decl_item = db.buyer_shipment_items.find_one({"shipment_id": decl["id"]}, {"_id": 0})

    print(f"\n{C}A3. DA hitung fisik: hanya 90 pcs sampai (0 reject) → selesaikan QC{X}")
    call("PUT", f"/api/prod/cmt-receipts/{rec_a['id']}/lines/{line_a['id']}",
         {"qty_actual": 90, "reject_qty": 0})
    st, done = call("POST", f"/api/prod/cmt-receipts/{rec_a['id']}/complete-qc", {})
    line_a = db.cmt_receipt_lines.find_one({"id": line_a["id"]}, {"_id": 0})
    led = ledger(ji_a["id"])
    short = db.cmt_short_shipments.find_one({"receipt_line_id": line_a["id"]}, {"_id": 0})
    decl_item = db.buyer_shipment_items.find_one({"id": decl_item["id"]}, {"_id": 0})

    check("A3a dokumen penerimaan DIKOREKSI ke kenyataan (qty_shipped_by_cmt=90)",
          int(line_a.get("qty_shipped_by_cmt") or 0) == 90,
          f"nilai={line_a.get('qty_shipped_by_cmt')}")
    check("A3b klaim vendor tersimpan terpisah (qty_claimed_by_cmt=100)",
          int(line_a.get("qty_claimed_by_cmt") or 0) == 100,
          f"nilai={line_a.get('qty_claimed_by_cmt')}")
    check("A3c baris punya identitas selisih (qty_short=10, status open)",
          int(line_a.get("qty_short") or 0) == 10 and line_a.get("short_status") == "open",
          f"qty_short={line_a.get('qty_short')} status={line_a.get('short_status')}")
    check("A3d dokumen selisih kirim dibuat (cmt_short_shipments)",
          bool(short) and int((short or {}).get("qty_short") or 0) == 10,
          f"no={(short or {}).get('short_number')} qty={(short or {}).get('qty_short')}")
    check("A3e buku kuantitas: declared 90 (bukan 100), accepted 90, short_open 10, claimed 100",
          int(led.get("qty_declared") or 0) == 90 and int(led.get("qty_accepted") or 0) == 90
          and int(led.get("qty_short_open") or 0) == 10
          and int(led.get("qty_claimed_by_vendor") or 0) == 100,
          f"declared={led.get('qty_declared')} accepted={led.get('qty_accepted')} "
          f"short_open={led.get('qty_short_open')} claimed={led.get('qty_claimed_by_vendor')}")
    check("A3f deklarasi vendor dirambatkan jadi 90 + ada jejak audit",
          int(decl_item.get("qty_shipped") or 0) == 90 and len(decl_item.get("edit_history") or []) > 0,
          f"qty_shipped={decl_item.get('qty_shipped')} history={len(decl_item.get('edit_history') or [])}")
    check("A3g stok FG naik 90 (bukan 100)", fg_stock(sku_a) == 90, f"stok={fg_stock(sku_a)}")
    notif = db.notifications.find_one({"meta.short_number": (short or {}).get("short_number")}, {"_id": 0})
    check("A3h vendor DAPAT NOTIFIKASI koreksi deklarasi", bool(notif),
          f"notif={(notif or {}).get('title')}")

    print(f"\n{C}A4. Portal vendor: sisa kirim harus NAIK lagi 10 pcs{X}")
    st, jobs = call("GET", "/api/production-jobs", tok=VTOK)
    jrow = next((j for j in (jobs if isinstance(jobs, list) else jobs.get("data", []))
                 if j.get("id") == job_a["id"]), None)
    check("A4a sisa kirim vendor = 10 pcs (kapasitas kirim ulang terbuka)",
          jrow is not None and int(jrow.get("remaining_to_ship") or 0) == 10,
          f"remaining_to_ship={(jrow or {}).get('remaining_to_ship')}")
    check("A4b portal vendor menampilkan kewajiban 'belum sampai' = 10",
          jrow is not None and int((jrow.get("qc_ledger") or {}).get("qty_short_open") or 0) == 10,
          f"qty_short_open={(jrow or {}).get('qc_ledger', {}).get('qty_short_open')}")

    print(f"\n{C}A5. Edit baris SETELAH QC selesai harus DITOLAK (409){X}")
    st, resp = call("PUT", f"/api/prod/cmt-receipts/{rec_a['id']}/lines/{line_a['id']}",
                    {"qty_actual": 100}, ok_codes=(409,))
    check("A5 PUT lines setelah QC selesai ditolak 409", st == 409, f"http={st}")
    line_chk = db.cmt_receipt_lines.find_one({"id": line_a["id"]}, {"_id": 0})
    check("A5b angka tidak bercabang (qty_actual tetap 90)",
          int(line_chk.get("qty_actual") or 0) == 90, f"qty_actual={line_chk.get('qty_actual')}")

    print(f"\n{C}A6. Vendor kirim ULANG 10 pcs yang belum sampai → selisih SELESAI{X}")
    decl2, rec_a2 = vendor_declare(po_a, ji_a, sku_a, 10)
    check("A6a vendor bisa membuat deklarasi kirim ulang 10 pcs", bool(rec_a2),
          f"receipt={(rec_a2 or {}).get('receipt_code')}")
    if rec_a2:
        line_a2 = db.cmt_receipt_lines.find_one({"receipt_id": rec_a2["id"]}, {"_id": 0})
        call("PUT", f"/api/prod/cmt-receipts/{rec_a2['id']}/lines/{line_a2['id']}",
             {"qty_actual": 10, "reject_qty": 0})
        call("POST", f"/api/prod/cmt-receipts/{rec_a2['id']}/complete-qc", {})
        led = ledger(ji_a["id"])
        short = db.cmt_short_shipments.find_one({"id": short["id"]}, {"_id": 0}) if short else None
        check("A6b selisih tertutup otomatis (short_open 0 · short_resolved 10)",
              int(led.get("qty_short_open") or 0) == 0 and int(led.get("qty_short_resolved") or 0) == 10,
              f"open={led.get('qty_short_open')} resolved={led.get('qty_short_resolved')}")
        check("A6c dokumen selisih berstatus resolved (dikirim_ulang)",
              (short or {}).get("status") == "resolved"
              and (short or {}).get("resolution") == "dikirim_ulang",
              f"status={(short or {}).get('status')} res={(short or {}).get('resolution')}")
        check("A6d angka akhir konsisten: declared 100 · accepted 100 · stok FG 100",
              int(led.get("qty_declared") or 0) == 100 and int(led.get("qty_accepted") or 0) == 100
              and fg_stock(sku_a) == 100,
              f"declared={led.get('qty_declared')} accepted={led.get('qty_accepted')} "
              f"stok={fg_stock(sku_a)}")

    # ───────────────────────────────────────────────────────────────────────
    # BAGIAN B — KOREKSI RESMI HASIL QC (salah input DA)
    # ───────────────────────────────────────────────────────────────────────
    sku_b = f"{MARK}-B-{S}"
    print(f"\n{C}B1. PO 50 pcs — DA salah input 45 (padahal 50 sampai){X}")
    po_b, poi_b, job_b, ji_b = make_po(sku_b, 50, "B")
    decl_b, rec_b = vendor_declare(po_b, ji_b, sku_b, 50)
    line_b = db.cmt_receipt_lines.find_one({"receipt_id": rec_b["id"]}, {"_id": 0})
    call("PUT", f"/api/prod/cmt-receipts/{rec_b['id']}/lines/{line_b['id']}",
         {"qty_actual": 45, "reject_qty": 0})
    call("POST", f"/api/prod/cmt-receipts/{rec_b['id']}/complete-qc", {})
    check("B1 selisih 5 terbentuk (salah input)",
          int(ledger(ji_b["id"]).get("qty_short_open") or 0) == 5,
          f"short_open={ledger(ji_b['id']).get('qty_short_open')}")

    print(f"\n{C}B2. Koreksi RESMI hasil QC 45 → 50 (stok & buku kuantitas ikut){X}")
    st, kor = call("POST",
                   f"/api/prod/cmt-receipts/{rec_b['id']}/lines/{line_b['id']}/koreksi-hasil-qc",
                   {"qty_actual": 50, "reject_qty": 0, "reason": "UJI: salah hitung, aktual 50"})
    led_b = ledger(ji_b["id"])
    line_b = db.cmt_receipt_lines.find_one({"id": line_b["id"]}, {"_id": 0})
    check("B2a koreksi resmi diterima (200)", st == 200, f"http={st}")
    check("B2b stok FG ikut naik jadi 50", fg_stock(sku_b) == 50, f"stok={fg_stock(sku_b)}")
    check("B2c buku kuantitas: accepted 50 · declared 50 · short_open 0",
          int(led_b.get("qty_accepted") or 0) == 50 and int(led_b.get("qty_declared") or 0) == 50
          and int(led_b.get("qty_short_open") or 0) == 0,
          f"accepted={led_b.get('qty_accepted')} declared={led_b.get('qty_declared')} "
          f"short_open={led_b.get('qty_short_open')}")
    check("B2d ada jejak koreksi di baris penerimaan",
          len(line_b.get("koreksi_history") or []) > 0,
          f"history={len(line_b.get('koreksi_history') or [])}")

    print(f"\n{C}B3. Koreksi deklarasi vendor (klaim salah tulis) 50 → 50 tanpa selisih{X}")
    st, kd = call("POST",
                  f"/api/prod/cmt-receipts/{rec_b['id']}/lines/{line_b['id']}/koreksi-deklarasi",
                  {"qty_claimed": 50, "reason": "UJI: klaim vendor dikoreksi"})
    check("B3 koreksi deklarasi berjalan (200) & selisih tetap 0", st == 200
          and int(ledger(ji_b["id"]).get("qty_short_open") or 0) == 0, f"http={st}")

    # ───────────────────────────────────────────────────────────────────────
    # BAGIAN C — STOK FG TURUN SAAT KIRIM KE BUYER + SELISIH BUYER
    # ───────────────────────────────────────────────────────────────────────
    print(f"\n{C}C1. Kirim 100 pcs PO-A ke buyer → stok FG harus TURUN{X}")
    src_ids = [r["id"] for r in db.cmt_receipts.find(
        {"po_id": po_a["id"]}, {"_id": 0, "id": 1})]
    stok_sebelum = fg_stock(sku_a)
    st, bs = call("POST", "/api/buyer-shipments", {
        "receiver_type": "buyer", "source_receipt_ids": src_ids, "vendor_id": VENDOR_ID,
        "shipment_date": str(date.today()), "notes": MARK,
        "items": [{"po_item_id": ji_a["po_item_id"], "job_item_id": ji_a["id"], "sku": sku_a,
                   "product_name": ji_a.get("product_name", ""), "qty_shipped": 100}]})
    stok_sesudah = fg_stock(sku_a)
    mv_out = db.rahaza_fg_movements.count_documents(
        {"sku_code": sku_a, "movement_type": "OUT"})
    check("C1a stok FG turun 100 (100 → 0)", stok_sebelum == 100 and stok_sesudah == 0,
          f"{stok_sebelum} → {stok_sesudah}")
    check("C1b ada mutasi FG OUT tercatat", mv_out >= 1, f"movement OUT={mv_out}")
    bsi = db.buyer_shipment_items.find_one({"shipment_id": bs.get("id")}, {"_id": 0})

    print(f"\n{C}C2. Buyer hanya menerima 95 → selisih 5 punya identitas & stok kembali{X}")
    st, recv = call("PUT", f"/api/buyer-shipment-items/{bsi['id']}/received",
                    {"qty_received": 95, "reason": "UJI: buyer hitung 95"})
    bsi = db.buyer_shipment_items.find_one({"id": bsi["id"]}, {"_id": 0})
    bshort = db.buyer_short_records.find_one({"shipment_item_id": bsi["id"]}, {"_id": 0})
    check("C2a catatan selisih buyer dibuat otomatis (open, 5 pcs)",
          bool(bshort) and int((bshort or {}).get("qty_short") or 0) == 5
          and (bshort or {}).get("status") == "open",
          f"no={(bshort or {}).get('short_number')} qty={(bshort or {}).get('qty_short')}")
    check("C2b dokumen SJ dikoreksi ke kenyataan (qty_shipped=95) + audit",
          int(bsi.get("qty_shipped") or 0) == 95 and len(bsi.get("edit_history") or []) > 0,
          f"qty_shipped={bsi.get('qty_shipped')}")
    check("C2c stok FG 5 pcs kembali (barang belum sampai = masih kewajiban DA)",
          fg_stock(sku_a) == 5, f"stok={fg_stock(sku_a)}")
    st, varr = call("GET", f"/api/buyer-receipt-variance?po_id={po_a['id']}")
    row = (varr or [{}])[0] if isinstance(varr, list) and varr else {}
    check("C2d laporan selisih buyer tetap menampilkan 5 pcs open",
          int(row.get("qty_short_open") or 0) == 5,
          f"qty_short_open={row.get('qty_short_open')}")

    print(f"\n{C}C3. Kirim ULANG 5 pcs (kapasitas harus terbuka — GAP F){X}")
    st, bs2 = call("POST", "/api/buyer-shipments", {
        "receiver_type": "buyer", "source_receipt_ids": src_ids, "vendor_id": VENDOR_ID,
        "shipment_date": str(date.today()), "notes": MARK,
        "items": [{"po_item_id": ji_a["po_item_id"], "job_item_id": ji_a["id"], "sku": sku_a,
                   "qty_shipped": 5}]})
    check("C3a kirim ulang 5 pcs BERHASIL", st in (200, 201), f"http={st}")
    check("C3b stok FG turun lagi jadi 0", fg_stock(sku_a) == 0, f"stok={fg_stock(sku_a)}")
    bshort = db.buyer_short_records.find_one({"id": (bshort or {}).get("id")}, {"_id": 0}) if bshort else None
    check("C3c catatan selisih buyer tertutup otomatis (resolved/dikirim_ulang)",
          (bshort or {}).get("status") == "resolved",
          f"status={(bshort or {}).get('status')} res={(bshort or {}).get('resolution')}")
    st, over = call("POST", "/api/buyer-shipments", {
        "receiver_type": "buyer", "source_receipt_ids": src_ids, "vendor_id": VENDOR_ID,
        "shipment_date": str(date.today()), "notes": MARK,
        "items": [{"po_item_id": ji_a["po_item_id"], "job_item_id": ji_a["id"], "sku": sku_a,
                   "qty_shipped": 1}]}, ok_codes=(400,))
    check("C3d kirim 1 pcs melebihi kapasitas tetap DITOLAK 400", over is not None and st == 400,
          f"http={st}")

    # ───────────────────────────────────────────────────────────────────────
    # BAGIAN D — PDF SURAT JALAN GABUNGAN MULTI-PO
    # ───────────────────────────────────────────────────────────────────────
    print(f"\n{C}D1. Dua PO buyer sama → satu SJ gabungan → PDF harus memuat kedua No PO{X}")
    sku_c, sku_d = f"{MARK}-C-{S}", f"{MARK}-D-{S}"
    po_c, poi_c, job_c, ji_c = make_po(sku_c, 20, "C", buyer="UJI Buyer Gabungan")
    po_d, poi_d, job_d, ji_d = make_po(sku_d, 30, "D", buyer="UJI Buyer Gabungan")
    recs = []
    for po_x, ji_x, sku_x, q in ((po_c, ji_c, sku_c, 20), (po_d, ji_d, sku_d, 30)):
        _, rec_x = vendor_declare(po_x, ji_x, sku_x, q)
        ln = db.cmt_receipt_lines.find_one({"receipt_id": rec_x["id"]}, {"_id": 0})
        call("PUT", f"/api/prod/cmt-receipts/{rec_x['id']}/lines/{ln['id']}",
             {"qty_actual": q, "reject_qty": 0})
        call("POST", f"/api/prod/cmt-receipts/{rec_x['id']}/complete-qc", {})
        recs.append(rec_x["id"])
    st, bsg = call("POST", "/api/buyer-shipments", {
        "receiver_type": "buyer", "source_receipt_ids": recs, "vendor_id": VENDOR_ID,
        "shipment_date": str(date.today()), "notes": MARK,
        "items": [
            {"po_item_id": ji_c["po_item_id"], "job_item_id": ji_c["id"], "sku": sku_c,
             "qty_shipped": 20},
            {"po_item_id": ji_d["po_item_id"], "job_item_id": ji_d["id"], "sku": sku_d,
             "qty_shipped": 30}]})
    check("D1a SJ gabungan 2 PO terbentuk", st in (200, 201) and len(bsg.get("po_ids") or []) == 2,
          f"po_ids={bsg.get('po_ids')}")
    check("D1b stok FG kedua SKU turun (20→0 dan 30→0)",
          fg_stock(sku_c) == 0 and fg_stock(sku_d) == 0,
          f"C={fg_stock(sku_c)} D={fg_stock(sku_d)}")
    r = requests.get(f"{API}/api/export-pdf?type=buyer-shipment&id={bsg.get('id')}",
                     headers=H(), timeout=180)
    txt = ""
    if r.status_code == 200:
        try:
            from PyPDF2 import PdfReader
            txt = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(r.content)).pages)
        except Exception as e:  # noqa: BLE001
            txt = f"__gagal_ekstrak__ {e}"
    check("D1c PDF SJ gabungan memuat NOMOR KEDUA PO",
          po_c["po_number"] in txt and po_d["po_number"] in txt,
          f"http={r.status_code} len={len(txt)}")
    check("D1d PDF punya subtotal per PO", txt.upper().count("SUBTOTAL") >= 2,
          f"subtotal={txt.upper().count('SUBTOTAL')}")

    # ───────────────────────────────────────────────────────────────────────
    # BAGIAN E — SELISIH BUYER SETELAH PO 'Completed' (keputusan finance)
    # ───────────────────────────────────────────────────────────────────────
    print(f"\n{C}E1. PO 'Completed' lalu ketahuan selisih → harus bisa disesuaikan{X}")
    db.production_pos.update_one({"id": po_c["id"]}, {"$set": {"status": "Completed"}})
    bsi_c = db.buyer_shipment_items.find_one(
        {"shipment_id": bsg.get("id"), "po_item_id": ji_c["po_item_id"]}, {"_id": 0})
    st, rc2 = call("PUT", f"/api/buyer-shipment-items/{bsi_c['id']}/received",
                   {"qty_received": 18, "reason": "UJI: buyer kurang 2 setelah PO selesai"})
    bshort_c = db.buyer_short_records.find_one({"shipment_item_id": bsi_c["id"]}, {"_id": 0})
    check("E1a catatan selisih buyer tetap terbentuk walau PO Completed",
          bool(bshort_c) and int((bshort_c or {}).get("qty_short") or 0) == 2,
          f"qty={(bshort_c or {}).get('qty_short')}")
    st, cs = call("POST", f"/api/production-pos/{po_c['id']}/close-short",
                  {"closed_reason": "buyer_material_shortage", "notes": "UJI pasca-Completed",
                   "confirm": True})
    check("E1b close-short SAH dari status 'Completed'", st == 200,
          f"http={st} status={cs.get('status')}")

    print(f"\n{C}E2. Keputusan finance atas selisih buyer (tanggungan CMT / DA){X}")
    if bshort_c:
        st, fin = call("POST", f"/api/buyer-shorts/{bshort_c['id']}/resolve",
                       {"resolution": "tanggungan_cmt", "notes": "UJI: dibebankan ke vendor CMT"})
        bshort_c = db.buyer_short_records.find_one({"id": bshort_c["id"]}, {"_id": 0})
        check("E2a keputusan finance tercatat (resolution=tanggungan_cmt, status resolved)",
              st == 200 and bshort_c.get("status") == "resolved"
              and bshort_c.get("resolution") == "tanggungan_cmt",
              f"http={st} status={bshort_c.get('status')}")
        check("E2b stok FG dihapusbukukan setelah dinyatakan hilang (0 pcs)",
              fg_stock(sku_c) == 0, f"stok={fg_stock(sku_c)}")

    print(f"\n{C}E3. Daftar selisih (API) untuk layar monitoring{X}")
    st, lst = call("GET", "/api/prod/short-shipments?status=all")
    check("E3a GET /api/prod/short-shipments jalan", st == 200 and isinstance(lst, dict),
          f"total={(lst or {}).get('total')}")
    st, lst2 = call("GET", "/api/buyer-shorts?status=all")
    check("E3b GET /api/buyer-shorts jalan", st == 200 and isinstance(lst2, dict),
          f"total={(lst2 or {}).get('total')}")
    return finish()


def finish():
    print(f"\n{B}{'─' * 88}{X}")
    print(f"  PASS {len(PASS)} · FAIL {len(FAIL)}")
    if FAIL:
        print(f"  {R}{B}MERAH — {len(FAIL)} pemeriksaan gagal:{X}")
        for f in FAIL:
            print(f"    {R}· {f}{X}")
        return 1
    print(f"  {G}{B}HIJAU — semua aturan owner terpenuhi{X}")
    return 0


if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean()
        sys.exit(0)
    rc = 1
    try:
        rc = main()
    finally:
        if "--keep" not in sys.argv:
            print()
            clean()
    sys.exit(rc)
