#!/usr/bin/env python3
"""verify_fase_e_kapasitas_kirim.py — FASE E (2026-08-15).

MEMBANGUN SKENARIO PERSIS SEPERTI KELUHAN PEMILIK, lewat ENDPOINT ASLI, lalu
membuktikan ketiga cacatnya tertutup:

  Skenario: PO 100 pcs → dikirim ke CMT → dikerjakan → diterima DA dengan
            **90 LOLOS QC + 10 REJECT** → 90 dikirim ke buyer → 10 reject
            DIPERBAIKI (permak sendiri, berhasil).

  E-1  SATU rumus. Angka pada `/api/buyer-dispatch-capacity` (yang dibaca layar)
       HARUS identik dengan batas pagar `POST /api/buyer-shipments`.
       Dulu berbeda: layar mem-prefill 100, Simpan ditolak "maksimal 50".

  E-2  Sesudah 10 reject DIPERBAIKI, kapasitas kirim naik 10 dan 10 pcs itu
       BENAR-BENAR bisa dikirim.
       Dulu MUSTAHIL: `apply_rework_outcome()` hanya menaikkan stok FG + buku
       kuantitas job, tidak menyentuh `cmt_receipt_lines`, sedangkan pagar kirim
       membaca baris penerimaan ⇒ "seharusnya 100, sudah diperbaiki, tetap 90".

  E-3  `qty_actual` TIDAK boleh dipotong `reject_qty` lagi. Semantiknya terbukti
       di `dewi_cmt_packing.py` (`arrived = qty_actual + reject_qty`) — jadi
       `qty_actual` sudah NETTO lolos QC. Layar lama memotong reject DUA KALI:
       itulah "chip tertulis 90 kok di tabel jadi 80".

  E-4  `/api/buyer-dispatch-outstanding` (tab "Kekurangan Kirim") memisahkan
       dengan jelas "sisa ORDER" dan "sisa BISA dikirim".

Pakai:
    python3 scripts/verify_fase_e_kapasitas_kirim.py
    python3 scripts/verify_fase_e_kapasitas_kirim.py --clean
Keluar 0 bila semua invarian HIJAU.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from gr_common import db_handle, test_doc_number  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

MARK = "VERIFY-FASE-E"
PO_NO = "PO-MKL-FASE-E-9101"   # diganti saat jalan agar mengikuti pola resmi (FASE G)
QTY_ORDER = 100
QTY_GOOD = 90      # lolos QC
QTY_REJECT = 10    # reject → nanti dipermak

PASS, FAIL = [], []


def ok(code, msg, extra=""):
    PASS.append(code)
    print(f"{G}  ✓ {code}{X} {msg}" + (f"\n         {C}{extra}{X}" if extra else ""))


def bad(code, msg, extra=""):
    FAIL.append(code)
    print(f"{R}  ✗ {code}{X} {msg}" + (f"\n         {extra}" if extra else ""))


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return e.code, {"raw": raw}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def login(email, pwd):
    st, r = call("POST", "/api/auth/login", None, {"email": email, "password": pwd})
    return r.get("token") if st == 200 else None


def clean(db):
    # FASE G (2026-08-16): PO uji tidak lagi bernomor tetap `PO-FASE-E-REJECT` —
    # nomor manual sekarang wajib mengikuti pola resmi, jadi nomornya ditentukan
    # saat jalan. Pembersihan berpegang pada penanda MARK di `notes` (yang memang
    # selalu ditulis skenario ini), bukan pada nomornya.
    pos = list(db.production_pos.find(
        {"$or": [{"notes": MARK}, {"po_number": PO_NO}]}, {"_id": 0, "id": 1}))
    ids = [p["id"] for p in pos]
    n = 0
    if ids:
        item_ids = [i["id"] for i in db.po_items.find({"po_id": {"$in": ids}}, {"_id": 0, "id": 1})]
        jobs = [j["id"] for j in db.production_jobs.find({"po_id": {"$in": ids}}, {"_id": 0, "id": 1})]
        vs = [s["id"] for s in db.vendor_shipments.find({"po_id": {"$in": ids}}, {"_id": 0, "id": 1})]
        bs = [s["id"] for s in db.buyer_shipments.find(
            {"$or": [{"po_id": {"$in": ids}}, {"po_ids": {"$in": ids}}]}, {"_id": 0, "id": 1})]
        rcpt = [r["id"] for r in db.cmt_receipts.find({"po_id": {"$in": ids}}, {"_id": 0, "id": 1})]
        for coll, q in (
            ("dewi_cmt_permak", {"po_id": {"$in": ids}}),
            ("wh_quarantine_items", {"source.po_id": {"$in": ids}}),
            ("production_job_items", {"job_id": {"$in": jobs}}),
            ("production_progress", {"job_id": {"$in": jobs}}),
            ("production_jobs", {"id": {"$in": jobs}}),
            ("vendor_shipment_items", {"shipment_id": {"$in": vs}}),
            ("vendor_material_inspections", {"shipment_id": {"$in": vs}}),
            ("vendor_shipments", {"id": {"$in": vs}}),
            ("buyer_shipment_items", {"shipment_id": {"$in": bs}}),
            ("buyer_shipments", {"id": {"$in": bs}}),
            ("cmt_receipt_lines", {"receipt_id": {"$in": rcpt}}),
            ("cmt_receipts", {"id": {"$in": rcpt}}),
            ("dewi_cmt_payments", {"po_id": {"$in": ids}}),
            ("po_items", {"id": {"$in": item_ids}}),
            ("production_pos", {"id": {"$in": ids}}),
            ("dewi_maklon_pos", {"id": {"$in": ids}}),
        ):
            n += db[coll].delete_many(q).deleted_count
    return n


def build_scenario(db, adm, ven):
    """PO 100 → CMT → terima 90 lolos + 10 reject (selesai QC)."""
    client = db.dewi_maklon_clients.find_one({"code": "ARNA"}, {"_id": 0})
    cat = db.dewi_maklon_buyer_catalog.find_one({"artikel_code": "ARN-HD"}, {"_id": 0})
    vendor = db.vendor_partners.find_one({"code": "JMC"}, {"_id": 0})
    if not (client and cat and vendor):
        print(f"{R}  master demo belum ada (klien ARNA / katalog ARN-HD / vendor JMC){X}")
        return None
    variants = [v for v in (cat.get("variants") or []) if v.get("active") is not False]
    if not variants:
        print(f"{R}  katalog ARN-HD tidak punya varian aktif{X}")
        return None
    v = variants[0]

    st, po = call("POST", "/api/production-pos", adm, {
        "po_number": PO_NO, "business_type": "maklon", "buyer_id": client["id"],
        "vendor_id": vendor["id"], "status": "Confirmed", "notes": MARK,
        "po_date": date.today().isoformat(), "deadline": date.today().isoformat(),
        "items": [{"catalog_item_id": cat["id"],
                   "maklon_variant_id": v.get("id") or v.get("sku"),
                   "sku": v.get("sku"), "color": v.get("color"), "size": v.get("size"),
                   "product_name": cat.get("product_name"), "qty": QTY_ORDER,
                   "cmt_price_snapshot": 18000, "serial_number": "SN-FASE-E"}]})
    if st not in (200, 201):
        print(f"{R}  gagal buat PO: {st} {po}{X}")
        return None
    po_id = po["id"]
    poi = list(db.po_items.find({"po_id": po_id}, {"_id": 0}))[0]

    st, vs = call("POST", "/api/vendor-shipments", adm, {
        "vendor_id": vendor["id"], "shipment_number": f"SJ-MTR-{PO_NO}", "po_id": po_id,
        "notes": MARK, "shipment_date": date.today().isoformat(), "shipment_type": "NORMAL",
        "items": [{"po_id": po_id, "po_item_id": poi["id"], "sku": poi.get("sku"),
                   "qty_sent": QTY_ORDER}]})
    if st not in (200, 201):
        print(f"{R}  gagal kirim material: {st} {vs}{X}")
        return None
    vs_id = vs["id"]
    vsi = list(db.vendor_shipment_items.find({"shipment_id": vs_id}, {"_id": 0}))
    call("PUT", f"/api/vendor-shipments/{vs_id}", ven or adm, {"status": "Received"})
    call("POST", "/api/vendor-material-inspections", ven or adm, {
        "shipment_id": vs_id, "overall_notes": MARK,
        "items": [{"shipment_item_id": vsi[0]["id"], "sku": vsi[0].get("sku"),
                   "ordered_qty": QTY_ORDER, "received_qty": QTY_ORDER, "missing_qty": 0}]})
    st, job = call("POST", "/api/production-jobs", adm, {
        "vendor_shipment_id": vs_id, "vendor_id": vendor["id"], "po_id": po_id, "notes": MARK})
    if st not in (200, 201):
        print(f"{R}  gagal buat job: {st} {job}{X}")
        return None
    ji = list(db.production_job_items.find({"job_id": job["id"]}, {"_id": 0}))[0]
    call("POST", "/api/production-progress", ven or adm, {
        "job_item_id": ji["id"], "completed_quantity": QTY_ORDER,
        "progress_date": date.today().isoformat(), "notes": MARK})
    st, decl = call("POST", "/api/buyer-shipments", ven or adm, {
        "po_id": po_id, "job_id": job["id"], "notes": MARK,
        "shipment_date": date.today().isoformat(),
        "items": [{"po_item_id": poi["id"], "job_item_id": ji["id"],
                   "sku": ji.get("sku"), "qty_shipped": QTY_ORDER}]})
    if st not in (200, 201):
        print(f"{R}  gagal deklarasi kirim vendor: {st} {decl}{X}")
        return None
    time.sleep(1)
    rcpt = db.cmt_receipts.find_one({"related_shipment_id": decl["id"]}, {"_id": 0})
    if not rcpt:
        print(f"{R}  penerimaan CMT tidak terbentuk{X}")
        return None
    line = list(db.cmt_receipt_lines.find({"receipt_id": rcpt["id"]}, {"_id": 0}))[0]
    # INI INTI SKENARIO PEMILIK: 90 lolos + 10 reject dari 100 yang datang.
    call("PUT", f"/api/prod/cmt-receipts/{rcpt['id']}/lines/{line['id']}", adm,
         {"qty_actual": QTY_GOOD, "reject_qty": QTY_REJECT})
    st, _ = call("POST", f"/api/prod/cmt-receipts/{rcpt['id']}/complete-qc", adm)
    fresh = db.cmt_receipt_lines.find_one({"id": line["id"]}, {"_id": 0})
    print(f"{C}  skenario siap: {PO_NO} order {QTY_ORDER} · penerimaan "
          f"{rcpt.get('receipt_code')} lolos {fresh.get('qty_actual')} + reject "
          f"{fresh.get('reject_qty')} (selesai QC HTTP {st}){X}")
    return {"po_id": po_id, "po_item_id": poi["id"], "job_item_id": ji["id"],
            "sku": ji.get("sku"), "receipt_id": rcpt["id"], "line_id": line["id"]}


def cap_of(token, receipt_ids, poi):
    st, d = call("GET", "/api/buyer-dispatch-capacity?receipt_ids="
                 + ",".join(receipt_ids) + "&with_fg_stock=1", token)
    rows = {r["key"]: r for r in (d.get("items") or [])}
    return st, d, rows.get(f"poi:{poi}", {})


def main():  # noqa: C901
    db = db_handle()
    if "--clean" in sys.argv:
        print(f"  dibersihkan {clean(db)} dokumen uji Fase E")
        return 0
    adm = login("admin@garment.com", "Admin@123")
    if not adm:
        print(f"{R}login admin gagal{X}")
        return 2
    ven = login("cmtvendor@dewiaditya.id", "Dewi@123")

    # FASE G — nomor PO uji harus mengikuti pola resmi jenis dokumen PO maklon.
    global PO_NO
    PO_NO = test_doc_number("production_pos.po_number_maklon", adm)

    print(f"{B}FASE E — kapasitas kirim DA → buyer (skenario 100 = 90 lolos + 10 reject){X}")
    clean(db)
    sc = build_scenario(db, adm, ven)
    if not sc:
        return 3
    if "--scenario-only" in sys.argv:
        print(f"{Y}  --scenario-only: skenario dibuat, pengujian dilewati "
              f"(dipakai untuk memeriksa layar secara manual).{X}")
        return 0
    rid, poi = [sc["receipt_id"]], sc["po_item_id"]

    # ── E-3: kapasitas = Σ qty_actual (BUKAN qty_actual − reject) ────────────
    st, envelope, row = cap_of(adm, rid, poi)
    if st != 200 or not row:
        bad("E-3", f"endpoint kapasitas gagal ({st})", json.dumps(envelope)[:200])
        return verdict()
    if int(row["good_from_cmt"]) == QTY_GOOD:
        ok("E-3", f"lolos QC dilaporkan {QTY_GOOD} (BUKAN {QTY_GOOD - QTY_REJECT} — "
                  f"reject tidak dipotong dua kali)",
           f"rumus di respons: {envelope.get('formula')}")
    else:
        bad("E-3", f"lolos QC dilaporkan {row['good_from_cmt']}, seharusnya {QTY_GOOD}",
            json.dumps(row)[:220])

    if int(row["shippable"]) == QTY_GOOD:
        ok("E-1a", f"sisa bisa kirim awal = {QTY_GOOD} pcs (belum ada yang dikirim)")
    else:
        bad("E-1a", f"sisa bisa kirim awal {row['shippable']}, seharusnya {QTY_GOOD}")

    # ── E-1b: pagar backend menolak melebihi sisa, dengan ANGKA YANG SAMA ────
    st2, d2 = call("POST", "/api/buyer-shipments", adm, {
        "shipment_date": date.today().isoformat(), "notes": MARK,
        "items": [{"po_item_id": poi, "sku": sc["sku"], "qty_shipped": QTY_ORDER}],
        "source_receipt_ids": rid, "receiver_type": "buyer"})
    detail = str(d2.get("detail") or d2)
    if st2 == 400 and f"sisa {QTY_GOOD}" in detail:
        ok("E-1b", f"kirim {QTY_ORDER} DITOLAK dengan angka yang sama seperti layar",
           detail[:190])
    elif st2 in (200, 201):
        bad("E-1b", f"kirim {QTY_ORDER} DITERIMA padahal hanya {QTY_GOOD} yang lolos QC")
    else:
        bad("E-1b", f"respons tak terduga ({st2})", detail[:220])

    # ── E-5: penolakan TIDAK boleh meninggalkan surat jalan yatim ───────────
    # Cacat nyata: blok validasi dulu berjalan SESUDAH `insert_one(master_shipment)`
    # sehingga setiap Simpan yang ditolak tetap membuat surat jalan "0 / 0 pcs"
    # status Pending. Daftar pengiriman jadi berisi baris yang tak bisa dijelaskan,
    # dan pemakai menyangka pengirimannya sudah pernah dilakukan.
    orphans = list(db.buyer_shipments.aggregate([
        {"$lookup": {"from": "buyer_shipment_items", "localField": "id",
                     "foreignField": "shipment_id", "as": "it"}},
        {"$match": {"it": {"$size": 0}}},
        {"$project": {"_id": 0, "shipment_number": 1, "ship_status": 1}},
    ]))
    if orphans:
        bad("E-5", f"{len(orphans)} surat jalan YATIM (0 item) tertinggal dari "
                   f"percobaan yang ditolak",
            "; ".join(f"{o.get('shipment_number')} [{o.get('ship_status')}]"
                      for o in orphans[:5]))
    else:
        ok("E-5", "penolakan tidak meninggalkan surat jalan yatim "
                  "(pagar berjalan SEBELUM dokumen ditulis)")

    # ── kirim 90 (tepat sisa) → harus diterima ──────────────────────────────
    st3, d3 = call("POST", "/api/buyer-shipments", adm, {
        "shipment_date": date.today().isoformat(), "notes": MARK,
        "items": [{"po_item_id": poi, "sku": sc["sku"], "qty_shipped": QTY_GOOD}],
        "source_receipt_ids": rid, "receiver_type": "buyer"})
    if st3 not in (200, 201):
        bad("E-1c", f"kirim {QTY_GOOD} (tepat sisa) DITOLAK ({st3})",
            str(d3.get("detail"))[:220])
        return verdict()
    ok("E-1c", f"kirim {QTY_GOOD} pcs (tepat sisa) diterima",
       f"surat jalan {d3.get('shipment_number')}")

    _, _, row = cap_of(adm, rid, poi)
    if int(row["shippable"]) == 0 and int(row["dispatched"]) == QTY_GOOD:
        ok("E-1d", "sesudah kirim, sisa menjadi 0 dan 'sudah dikirim' = 90 "
                   "(baris akan ditandai LUNAS di layar)")
    else:
        bad("E-1d", f"sisa {row['shippable']} / dikirim {row['dispatched']} — "
                    f"seharusnya 0 / {QTY_GOOD}")

    # ── E-2: 10 reject DIPERBAIKI → boleh dikirim ───────────────────────────
    st4, permak = call("POST", "/api/dewi/cmt-permak/from-receipt-line", adm, {
        "receipt_line_id": sc["line_id"], "qty": QTY_REJECT,
        "permak_type": "permak_sendiri", "reason": MARK})
    if st4 not in (200, 201):
        bad("E-2a", f"gagal membuat permak ({st4})", str(permak.get("detail"))[:220])
        return verdict()
    st5, res = call("POST", f"/api/dewi/cmt-permak/{permak['id']}/status", adm, {
        "status": "selesai_berhasil", "qty_fixed": QTY_REJECT, "qty_scrap": 0, "note": MARK})
    if st5 != 200:
        bad("E-2a", f"gagal menyelesaikan permak ({st5})", str(res.get("detail"))[:220])
        return verdict()
    fresh = db.cmt_receipt_lines.find_one({"id": sc["line_id"]}, {"_id": 0})
    if int(fresh.get("qty_reworked_ok") or 0) != QTY_REJECT:
        bad("E-2a", "permak berhasil TAPI baris penerimaan tidak mencatat hasil permak",
            f"qty_reworked_ok = {fresh.get('qty_reworked_ok')} (harus {QTY_REJECT})")
    else:
        ok("E-2a", f"permak berhasil → baris penerimaan mencatat qty_reworked_ok "
                   f"{QTY_REJECT}",
           "angka inspeksi asli TIDAK diubah: "
           f"qty_actual masih {fresh.get('qty_actual')}, reject_qty masih "
           f"{fresh.get('reject_qty')} (jejak audit utuh)")

    _, _, row = cap_of(adm, rid, poi)
    if int(row["shippable"]) == QTY_REJECT and int(row["reworked_ok"]) == QTY_REJECT:
        ok("E-2b", f"kapasitas kirim NAIK {QTY_REJECT} sesudah permak "
                   f"(dulu mustahil — selamanya 0)",
           f"lolos QC {row['good_from_cmt']} + permak {row['reworked_ok']} − "
           f"dikirim {row['dispatched']} = sisa {row['shippable']}")
    else:
        bad("E-2b", f"kapasitas tidak naik: sisa {row['shippable']}, "
                    f"permak {row['reworked_ok']} (harus {QTY_REJECT}/{QTY_REJECT})",
            json.dumps(row)[:260])

    st6, d6 = call("POST", "/api/buyer-shipments", adm, {
        "shipment_date": date.today().isoformat(), "notes": MARK,
        "items": [{"po_item_id": poi, "sku": sc["sku"], "qty_shipped": QTY_REJECT}],
        "source_receipt_ids": rid, "receiver_type": "buyer"})
    if st6 in (200, 201):
        ok("E-2c", f"{QTY_REJECT} pcs hasil permak BENAR-BENAR terkirim ke buyer",
           f"surat jalan {d6.get('shipment_number')} — lingkaran "
           f"100 → 10 reject → diperbaiki → 100 terkirim akhirnya TERTUTUP")
    else:
        bad("E-2c", f"hasil permak masih tidak bisa dikirim ({st6})",
            str(d6.get("detail"))[:260])

    _, _, row = cap_of(adm, rid, poi)
    if int(row["dispatched"]) == QTY_ORDER and int(row["shippable"]) == 0:
        ok("E-2d", f"total terkirim {QTY_ORDER} pcs = qty PO, sisa 0")
    else:
        bad("E-2d", f"total terkirim {row['dispatched']} / sisa {row['shippable']} — "
                    f"seharusnya {QTY_ORDER} / 0")

    # ── E-4: daftar kekurangan kirim ────────────────────────────────────────
    st7, out = call("GET", "/api/buyer-dispatch-outstanding?include_settled=1", adm)
    if st7 != 200:
        bad("E-4", f"endpoint kekurangan kirim gagal ({st7})", json.dumps(out)[:200])
    else:
        items = out.get("items") or []
        wrong = [r for r in items
                 if r["shippable"] != max(0, r["good_from_cmt"] + r["reworked_ok"]
                                          - r["dispatched"])]
        mine = next((r for r in items if r["po_item_id"] == poi), None)
        if wrong:
            bad("E-4", "rumus sisa TIDAK konsisten di daftar kekurangan kirim",
                json.dumps(wrong[0])[:240])
        elif not mine:
            bad("E-4", "baris uji tidak muncul di daftar kekurangan kirim")
        elif mine["remaining_vs_order"] != 0:
            bad("E-4", f"sisa order dilaporkan {mine['remaining_vs_order']}, harus 0")
        else:
            ok("E-4", f"daftar kekurangan kirim konsisten — {len(items)} baris, "
                      f"rumus sama untuk SEMUA baris",
               f"baris uji: order {mine['ordered']} · dikirim {mine['dispatched']} · "
               f"sisa order {mine['remaining_vs_order']} · sisa bisa kirim {mine['shippable']}")

    return verdict()


def verdict():
    # Penjaga tidak boleh MENINGGALKAN sampah: gate ini dijalankan berkali-kali,
    # dan PO/surat jalan uji akan mengotori dashboard produksi kalau dibiarkan.
    # Lewati dengan --keep bila datanya mau diperiksa manual di layar.
    if "--keep" not in sys.argv:
        try:
            clean(db_handle())
        except Exception:  # noqa: BLE001
            pass
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian kapasitas kirim terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
