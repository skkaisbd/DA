#!/usr/bin/env python3
"""
seed_cmt_qc_flow_demo.py — FASE 22. Data demo untuk alur "Terima FG dari CMT"
(keluhan owner #5, #5b, #7) yang dibuat lewat **ENDPOINT ASLI**, bukan tulis
mentah ke Mongo, supaya angkanya identik dengan hasil kerja manual di UI.

Yang dihasilkan (idempoten — ditandai `delivery_note` MARK-*):
  1. `CMT-RCV-…` status **on_qc** (Sedang QC) — baris belum dihitung, jadi owner
     bisa mencoba isi qty & reject INLINE lalu klik "Selesaikan QC".
  2. `CMT-RCV-…` status **completed_qc** dengan reject:
        · sebagian reject → **Permak sendiri** (selesai → stok FG naik)
        · sebagian reject → **Retur ke CMT** (terbit Surat Jalan REWORK SJ-RWK-…,
          muncul di Portal Vendor + kolom "Vendor CMT / SJ Rework")
        · sebagian reject **belum diputuskan** → tampil di panel "Antrean Reject"
Pakai:
    python3 scripts/seed_cmt_qc_flow_demo.py
    python3 scripts/seed_cmt_qc_flow_demo.py --clean
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from gr_common import db_handle  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001")
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
         "password": os.environ.get("ADMIN_PASS", "Admin@123")}
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

MARK_OPEN = "DEMO-QC-ON"        # penerimaan yang masih Sedang QC
MARK_DONE = "DEMO-QC-DONE"      # penerimaan Selesai QC + reject bercabang


def call(method, path, token=None, body=None):
    req = urllib.request.Request(f"{API}{path}",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:  # noqa: BLE001
            return e.code, {}
    except Exception as e:  # noqa: BLE001
        return -1, {"error": str(e)}


def clean(db):
    ids = [r["id"] for r in db.cmt_receipts.find(
        {"delivery_note": {"$in": [MARK_OPEN, MARK_DONE]}}, {"_id": 0, "id": 1})]
    if ids:
        db.cmt_receipt_lines.delete_many({"receipt_id": {"$in": ids}})
        db.cmt_receipts.delete_many({"id": {"$in": ids}})
        db.dewi_cmt_permak.delete_many({"source_receipt_id": {"$in": ids}})
        print(f"  dibersihkan {len(ids)} penerimaan demo QC + baris + permak-nya")
    # Surat Jalan REWORK ikut dibersihkan: kalau permak-nya hilang tapi SJ-nya
    # tinggal, Portal Vendor menampilkan surat jalan rework TANPA pekerjaan yang
    # menaunginya (dokumen menggantung). Jangan tinggalkan sampah relasi.
    n = clean_orphan_rework_shipments(db)
    if n:
        print(f"  dibersihkan {n} Surat Jalan REWORK yatim (permak sudah tidak ada)")
    return len(ids)


def clean_orphan_rework_shipments(db) -> int:
    valid = {p["id"] for p in db.dewi_cmt_permak.find({}, {"_id": 0, "id": 1})}
    orphans = [s["id"] for s in db.vendor_shipments.find(
        {"shipment_type": "REWORK"}, {"_id": 0, "id": 1, "rework_permak_id": 1})
        if s.get("rework_permak_id") and s["rework_permak_id"] not in valid]
    if orphans:
        db.vendor_shipment_items.delete_many({"shipment_id": {"$in": orphans}})
        db.vendor_shipments.delete_many({"id": {"$in": orphans}})
    return len(orphans)


def pick_job(db):
    """Ambil job vendor CMT yang punya item ber-SKU + SISA kapasitas setor.

    PENTING: `qty_declared` (sudah pernah disetor & di-QC) TIDAK boleh melewati
    `produced_qty`. Kalau seeder menambah penerimaan di atas kapasitas, UI akan
    menampilkan angka mustahil "Lolos QC 190 / Diproduksi 145".
    """
    for j in db.production_jobs.find({"vendor_id": {"$nin": [None, ""]}}, {"_id": 0}).sort("created_at", -1):
        po = db.production_pos.find_one({"id": j.get("po_id")}, {"_id": 0})
        if not po or str(po.get("status")) in ("Closed", "Cancelled"):
            continue
        items = []
        for it in db.production_job_items.find({"job_id": j["id"]}, {"_id": 0}):
            if not it.get("po_item_id"):
                continue
            remaining = int(float(it.get("produced_qty") or 0)) - int(float(it.get("qty_declared") or 0))
            if remaining > 0:
                it["_remaining"] = remaining
                items.append(it)
        if items:
            items.sort(key=lambda x: -x["_remaining"])
            return j, po, items
    return None, None, None


def ensure_main_vendor_return(db, tok, other_vendor=None):
    """Pastikan vendor UTAMA (akun `cmtvendor@dewiaditya.id`) juga punya Surat Jalan
    REWORK, supaya alur "retur ke CMT" bisa dicoba owner dari portal vendor yang
    memang dipakainya — bukan hanya vendor kedua."""
    main_vendor = (db.users.find_one({"email": "cmtvendor@dewiaditya.id"}, {"_id": 0, "cmt_vendor_id": 1})
                   or {}).get("cmt_vendor_id")
    if not main_vendor or main_vendor == other_vendor:
        return
    if db.dewi_cmt_permak.count_documents({"vendor_id": main_vendor, "permak_type": "retur_ke_cmt"}):
        return
    st, q = call("GET", "/api/prod/cmt-reject-queue", tok)
    cand = next((i for i in (q or {}).get("items", [])
                 if i.get("vendor_id") == main_vendor and int(i.get("qty_undecided") or 0) >= 2), None)
    if not cand:
        print(f"{Y}  (tidak ada baris reject vendor utama yang bisa diretur){X}")
        return
    st, p3 = call("POST", "/api/dewi/cmt-permak/from-receipt-line", tok, {
        "receipt_line_id": cand["receipt_line_id"], "permak_type": "retur_ke_cmt",
        "qty": 2, "problem_type": "jahitan",
        "reason": "Retur ke vendor utama untuk diperbaiki (demo pipeline rework)",
    })
    if st in (200, 201) and p3.get("id"):
        doc = db.dewi_cmt_permak.find_one({"id": p3["id"]}, {"_id": 0})
        print(f"{G}  ✓ retur ke CMT 2 pcs untuk vendor utama → "
              f"Surat Jalan REWORK {(doc or {}).get('rework_shipment_number', '-')}{X}")
    else:
        print(f"{Y}  (retur vendor utama dilewati: {st} {p3}){X}")


def main() -> int:
    db = db_handle()
    if "--clean" in sys.argv:
        clean(db)
        return 0
    st, res = call("POST", "/api/auth/login", None, ADMIN)
    if st != 200:
        print(f"{R}login admin gagal ({st}){X}")
        return 1
    tok = res["token"]

    if db.cmt_receipts.count_documents({"delivery_note": {"$in": [MARK_OPEN, MARK_DONE]}}):
        print(f"{Y}  data demo QC sudah ada — idempoten, tidak diulang "
              f"(pakai --clean untuk membuat ulang){X}")
        ensure_main_vendor_return(db, tok)
        return 0

    job, po, items = pick_job(db)
    if not job:
        print(f"{R}  tidak ada job vendor CMT yang cocok — jalankan seed_demo_all.sh dulu{X}")
        return 1
    vendor_id, vendor_name = job.get("vendor_id"), job.get("vendor_name") or "Vendor CMT"
    print(f"{C}  PO {po.get('po_number')} · job {job.get('job_number')} · vendor {vendor_name}{X}")

    def new_receipt(mark, note):
        st, r = call("POST", "/api/prod/cmt-receipts", tok, {
            "cmt_name": vendor_name, "cmt_vendor_id": vendor_id,
            "po_id": po["id"], "po_number": po.get("po_number", ""),
            "business_type": po.get("business_type", "maklon"),
            "delivery_note": mark, "notes": note,
        })
        if st not in (200, 201):
            print(f"{R}  gagal buat penerimaan: {st} {r}{X}")
            return None
        return r

    def add_line(rcpt_id, it, shipped):
        st, r = call("POST", f"/api/prod/cmt-receipts/{rcpt_id}/lines", tok, {
            "sku_code": it.get("sku") or "", "product_name": it.get("product_name") or "",
            "size": it.get("size") or "", "color": it.get("color") or "",
            "qty_shipped_by_cmt": shipped, "qty_expected": shipped,
            "po_item_id": it.get("po_item_id"), "job_item_id": it.get("id"),
        })
        if st not in (200, 201):
            print(f"{R}  gagal tambah baris: {st} {r}{X}")
        return r

    # ── 1. Penerimaan yang MASIH Sedang QC (owner mencoba isi sendiri) ────────
    # item paling banyak sisa dipakai untuk penerimaan SELESAI QC (butuh 30 pcs),
    # item berikutnya (atau sisa item pertama) untuk penerimaan yang masih QC.
    it_done = items[0]
    done_qty = min(30, it_done["_remaining"])
    it_open = items[1] if len(items) > 1 else it_done
    open_room = it_open["_remaining"] - (done_qty if it_open is it_done else 0)
    open_qty = max(0, min(40, open_room))

    if open_qty > 0:
        r1 = new_receipt(MARK_OPEN, "Setoran CMT menunggu hitung fisik (demo alur QC inline)")
        if r1:
            add_line(r1["id"], it_open, open_qty)
            print(f"{G}  ✓ {r1['receipt_code']} — status Sedang QC "
                  f"({open_qty} pcs {it_open.get('sku')} belum dihitung){X}")
    else:
        print(f"{Y}  (tidak ada sisa kapasitas untuk penerimaan 'Sedang QC'){X}")

    # ── 2. Penerimaan SELESAI QC dengan reject bercabang ─────────────────────
    if done_qty < 12:
        print(f"{Y}  sisa kapasitas {done_qty} pcs terlalu kecil untuk skenario reject — lewati{X}")
        return 0
    r2 = new_receipt(MARK_DONE, "Setoran CMT sudah dihitung — ada reject (demo permak/retur)")
    if not r2:
        return 1
    it0 = it_done
    shipped = done_qty
    reject = 9 if shipped >= 21 else max(3, shipped // 3)
    accepted = shipped - reject
    ln = add_line(r2["id"], it0, shipped)
    if not ln or not ln.get("id"):
        return 1
    st, _ = call("PUT", f"/api/prod/cmt-receipts/{r2['id']}/lines/{ln['id']}", tok,
                 {"qty_actual": accepted, "reject_qty": reject, "reject_reason": "jahitan tidak rapi"})
    if st != 200:
        print(f"{R}  gagal isi qty baris: {st}{X}")
        return 1
    st, done = call("POST", f"/api/prod/cmt-receipts/{r2['id']}/complete-qc", tok, {})
    if st != 200:
        print(f"{R}  gagal Selesaikan QC: {st} {done}{X}")
        return 1
    print(f"{G}  ✓ {r2['receipt_code']} — Selesai QC: {accepted} lolos / {reject} reject{X}")

    # reject dipecah: 3 permak sendiri (diselesaikan), 4 retur ke CMT (SJ REWORK), sisa dibiarkan
    n_self = min(3, reject - 1)
    n_ret = min(4, reject - n_self - 1) if reject - n_self > 1 else 0
    st, p1 = call("POST", "/api/dewi/cmt-permak/from-receipt-line", tok, {
        "receipt_line_id": ln["id"], "permak_type": "permak_sendiri", "qty": n_self,
        "problem_type": "jahitan", "reason": "Jahitan bisa dirapikan sendiri",
    })
    if st in (200, 201) and p1.get("id"):
        call("POST", f"/api/dewi/cmt-permak/{p1['id']}/status", tok,
             {"status": "in_progress", "note": "Mulai permak di QC internal"})
        st3, r3 = call("POST", f"/api/dewi/cmt-permak/{p1['id']}/status", tok,
                       {"status": "selesai_berhasil", "qty_fixed": n_self, "qty_scrap": 0,
                        "note": f"{n_self} pcs selesai dipermak → masuk gudang FG"})
        if st3 != 200:
            print(f"{R}  gagal menyelesaikan permak: {st3} {r3}{X}")
        else:
            print(f"{G}  ✓ permak sendiri {n_self} pcs {p1.get('permak_number')} → selesai berhasil "
                  f"(stok FG +{(r3.get('effect') or {}).get('stock_released', n_self)}){X}")
    else:
        print(f"{R}  gagal buat permak sendiri: {st} {p1}{X}")

    st, p2 = call("POST", "/api/dewi/cmt-permak/from-receipt-line", tok, {
        "receipt_line_id": ln["id"], "permak_type": "retur_ke_cmt", "qty": n_ret,
        "problem_type": "jahitan", "reason": "Dikembalikan ke vendor untuk diperbaiki",
    })
    if st in (200, 201) and p2.get("id"):
        doc = db.dewi_cmt_permak.find_one({"id": p2["id"]}, {"_id": 0})
        sj = (doc or {}).get("rework_shipment_number") or "-"
        print(f"{G}  ✓ retur ke CMT {n_ret} pcs {p2.get('permak_number')} → Surat Jalan REWORK {sj}{X}")
    else:
        print(f"{R}  gagal buat retur ke CMT: {st} {p2}{X}")

    print(f"{B}  sisa {reject - n_self - n_ret} pcs reject sengaja BELUM diputuskan → "
          f"tampil di panel 'Antrean Reject'{X}")

    ensure_main_vendor_return(db, tok, other_vendor=vendor_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
