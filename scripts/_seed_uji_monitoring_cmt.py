#!/usr/bin/env python3
"""_seed_uji_monitoring_cmt.py — data uji LAYAR untuk INV-F28 (sekali pakai).

Gate `verify_monitoring_cmt_potongan.py` membangun + MEMBERSIHKAN datanya sendiri,
jadi setelah gate jalan layar jadi kosong dan penguji UI tidak bisa melihat:
  · pelacak rantai PENGGANTI (butuh permintaan yang sudah DISETUJUI ⇒ SJ `…-R1`),
  · perbedaan chip "PO Berjalan" vs "Semua PO" (butuh PO berstatus Completed),
  · angka "dari PO Draft: X pcs" (butuh PO Draft).

Skrip ini menyiapkan ketiganya di atas skenario Fase E.
    python3 scripts/_seed_uji_monitoring_cmt.py          # buat
    python3 scripts/_seed_uji_monitoring_cmt.py --clean  # bersihkan
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "lib"))

import verify_fase_e_kapasitas_kirim as fe  # noqa: E402
from gr_common import db_handle, test_doc_number  # noqa: E402
from verify_monitoring_cmt_potongan import clean_extra  # noqa: E402

G, C, R, X = "\033[92m", "\033[96m", "\033[91m", "\033[0m"


def main():
    db = db_handle()
    if "--clean" in sys.argv:
        print(f"  dibersihkan {clean_extra(db)} dokumen uji")
        return 0
    adm = fe.login("admin@garment.com", "Admin@123")
    ven = fe.login("cmtvendor@dewiaditya.id", "Dewi@123")
    if not adm:
        print(f"{R}login admin gagal{X}")
        return 2

    fe.PO_NO = test_doc_number("production_pos.po_number_maklon", adm)
    clean_extra(db)
    sc = fe.build_scenario(db, adm, ven)
    if not sc:
        return 3

    parent = db.vendor_shipments.find_one({"po_id": sc["po_id"], "shipment_type": "NORMAL"}, {"_id": 0})
    vsi = db.vendor_shipment_items.find_one({"shipment_id": parent["id"]}, {"_id": 0})
    st, req = fe.call("POST", "/api/material-requests", ven or adm, {
        "vendor_id": parent["vendor_id"], "request_type": "REPLACEMENT",
        "original_shipment_id": parent["id"], "po_id": sc["po_id"], "reason": fe.MARK,
        "items": [{"shipment_item_id": vsi["id"], "po_item_id": sc["po_item_id"],
                   "sku": sc["sku"], "requested_qty": 5,
                   "reason": "bahan cacat saat inspeksi"}]})
    st2, appr = fe.call("PUT", f"/api/material-requests/{req.get('id')}", adm,
                        {"status": "Approved", "admin_notes": fe.MARK}) if st in (200, 201) else (0, {})

    st3, done = fe.call("POST", "/api/production-pos", adm, {
        "po_number": test_doc_number("production_pos.po_number_maklon", adm),
        "business_type": "maklon", "status": "Completed", "notes": fe.MARK,
        "po_date": date.today().isoformat(),
        "items": [{"sku": "UJI-SELESAI", "product_name": "PO sudah selesai",
                   "qty": 200, "cmt_price_snapshot": 5000}]})
    db.production_pos.update_one({"id": done.get("id")}, {"$set": {"status": "Completed"}})

    st4, draft = fe.call("POST", "/api/production-pos", adm, {
        "po_number": test_doc_number("production_pos.po_number_maklon", adm),
        "business_type": "maklon", "status": "Draft", "notes": fe.MARK,
        "po_date": date.today().isoformat(),
        "items": [{"sku": "UJI-DRAFT", "product_name": "PO masih draft (di gudang)",
                   "qty": 50, "cmt_price_snapshot": 4000}]})

    print(f"{G}data uji layar siap{X}")
    print(f"{C}  PO utama          : {fe.PO_NO} (order 100 · 90 lolos QC + 10 reject){X}")
    print(f"{C}  SJ material induk : {parent.get('shipment_number')} (Received + diinspeksi){X}")
    print(f"{C}  permintaan PENGGANTI: {req.get('request_number')} → SJ anak "
          f"{appr.get('child_shipment_number')} (http {st}/{st2}){X}")
    print(f"{C}  PO Completed      : {done.get('po_number')} 200 pcs (http {st3}){X}")
    print(f"{C}  PO Draft          : {draft.get('po_number')} 50 pcs (http {st4}){X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
