#!/usr/bin/env python3
"""REPRO 5 keluhan owner (2026-06) — produksi/maklon.

Dipakai untuk MEMBUKTIKAN cacatnya ADA sebelum diperbaiki (dan hilang sesudah).
Memakai ulang pembangun skenario gate Fase E supaya tidak ada skenario kedua.

    python3 scripts/_repro_5bug_produksi_maklon.py
    python3 scripts/_repro_5bug_produksi_maklon.py --clean
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import verify_fase_e_kapasitas_kirim as fe  # noqa: E402
from gr_common import db_handle, test_doc_number  # noqa: E402

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
call, login = fe.call, fe.login


def main():
    db = db_handle()
    if "--clean" in sys.argv:
        print("dibersihkan", fe.clean(db))
        return 0
    adm = login("admin@garment.com", "Admin@123")
    ven = login("cmtvendor@dewiaditya.id", "Dewi@123")
    if not adm:
        print(f"{R}login admin gagal{X}")
        return 2
    fe.PO_NO = test_doc_number("production_pos.po_number_maklon", adm)
    fe.clean(db)
    sc = fe.build_scenario(db, adm, ven)
    if not sc:
        return 3
    rid, poi = [sc["receipt_id"]], sc["po_item_id"]

    # ── BUG 1: permak lewat form "Buat Permak Baru" (TANPA source_receipt_line_id)
    print(f"\n{B}BUG 1 — permak dari form manual (tanpa tautan baris penerimaan){X}")
    st, permak = call("POST", "/api/dewi/cmt-permak", adm, {
        "po_id": sc["po_id"], "po_item_id": poi, "qty": fe.QTY_REJECT,
        "source": "reject", "permak_type": "permak_sendiri", "reason": fe.MARK})
    print("  create:", st, permak.get("permak_number") or permak)
    if st in (200, 201):
        st2, res = call("POST", f"/api/dewi/cmt-permak/{permak['id']}/status", adm, {
            "status": "selesai_berhasil", "qty_fixed": fe.QTY_REJECT, "qty_scrap": 0})
        print("  selesai:", st2, json.dumps(res.get("effect") or {})[:300])
        ln = db.cmt_receipt_lines.find_one({"id": sc["line_id"]}, {"_id": 0})
        _, _, row = fe.cap_of(adm, rid, poi)
        print(f"  qty_reworked_ok baris penerimaan = {ln.get('qty_reworked_ok')}  "
              f"(harusnya {fe.QTY_REJECT})")
        print(f"  kapasitas kirim: good={row.get('good_from_cmt')} "
              f"permak={row.get('reworked_ok')} dikirim={row.get('dispatched')} "
              f"sisa={row.get('shippable')}  (harusnya sisa {fe.QTY_ORDER})")
        print(f"  {R if int(row.get('reworked_ok') or 0) == 0 else G}"
              f"→ BUG 1 {'TERBUKTI' if int(row.get('reworked_ok') or 0) == 0 else 'TIDAK ADA'}{X}")

    # ── BUG 2: dispatch partial tidak bisa dilanjutkan pada surat jalan yang sama
    print(f"\n{B}BUG 2 — lanjutan dispatch pada surat jalan yang SAMA{X}")
    st3, d3 = call("POST", "/api/buyer-shipments", adm, {
        "shipment_date": date.today().isoformat(), "notes": fe.MARK,
        "items": [{"po_item_id": poi, "sku": sc["sku"], "qty_shipped": 40}],
        "source_receipt_ids": rid, "receiver_type": "buyer"})
    print("  dispatch#1:", st3, d3.get("shipment_number"), "seq", d3.get("dispatch_seq"))
    sid = d3.get("id")
    st4, d4 = call("POST", "/api/buyer-shipments", adm, {
        "shipment_id": sid, "shipment_date": date.today().isoformat(), "notes": fe.MARK,
        "items": [{"po_item_id": poi, "sku": sc["sku"], "qty_shipped": 30}],
        "source_receipt_ids": rid, "receiver_type": "buyer"})
    print("  dispatch#2 (kirim shipment_id):", st4, d4.get("shipment_number"),
          "seq", d4.get("dispatch_seq"), "is_new", d4.get("is_new"))
    same = d4.get("id") == sid
    print(f"  {R if not same else G}→ BUG 2 "
          f"{'TERBUKTI (nomor baru, dispatch terpisah)' if not same else 'TIDAK ADA'}{X}")

    # ── BUG 5: surat jalan ANAK (pengganti) tetap membawa aksesoris PO
    print(f"\n{B}BUG 5 — surat jalan anak (ADDITIONAL/REPLACEMENT) membawa aksesoris PO{X}")
    acc_po = db.po_accessories.count_documents({"po_id": sc["po_id"]})
    print(f"  po_accessories PO uji = {acc_po}")
    parent = db.vendor_shipments.find_one({"po_id": sc["po_id"], "shipment_type": "NORMAL"},
                                          {"_id": 0})
    child = {
        "id": "REPRO-CHILD-1", "shipment_number": "SJ-REPRO-CHILD-1",
        "vendor_id": (parent or {}).get("vendor_id"), "po_id": sc["po_id"],
        "shipment_type": "REPLACEMENT", "parent_shipment_id": (parent or {}).get("id"),
        "business_type": "maklon", "status": "Sent", "notes": fe.MARK,
    }
    db.vendor_shipments.insert_one(dict(child))
    db.vendor_shipment_items.insert_one({
        "id": "REPRO-CHILD-ITEM-1", "shipment_id": child["id"], "po_id": sc["po_id"],
        "po_item_id": poi, "sku": sc["sku"], "qty_sent": 5,
        "shipment_type": "REPLACEMENT"})
    st5, d5 = call("GET", f"/api/vendor-shipments/{child['id']}", adm)
    n_acc = len(d5.get("po_accessories") or [])
    print(f"  detail surat jalan anak → po_accessories = {n_acc} baris "
          f"(harusnya 0; aksesoris hanya dari accessory_shipment_items miliknya)")
    print(f"  {R if n_acc else G}→ BUG 5 {'TERBUKTI' if n_acc else 'TIDAK ADA'}{X}")
    db.vendor_shipments.delete_one({"id": child["id"]})
    db.vendor_shipment_items.delete_one({"id": "REPRO-CHILD-ITEM-1"})

    # ── BUG 3: pratinjau aksesoris BOM untuk form buat PO
    print(f"\n{B}BUG 3 — pratinjau aksesoris BOM di form buat PO maklon{X}")
    cat = db.dewi_maklon_buyer_catalog.find_one({"artikel_code": "ARN-HD"}, {"_id": 0})
    st6, d6 = call("POST", "/api/dewi/maklon/bom-templates/preview-accessories", adm,
                   {"items": [{"catalog_item_id": (cat or {}).get("id"), "qty": 100}]})
    print(f"  POST preview-accessories → {st6} "
          f"{json.dumps(d6)[:200] if st6 != 404 else 'ENDPOINT TIDAK ADA'}")
    print(f"  {R if st6 == 404 else G}→ BUG 3 {'TERBUKTI (tak ada sumber pratinjau)' if st6 == 404 else 'TIDAK ADA'}{X}")

    # ── BUG 4: vendor membuat permintaan PENGGANTI
    print(f"\n{B}BUG 4 — vendor CMT membuat permintaan PENGGANTI (REPLACEMENT){X}")
    fe_src = Path("/app/frontend/src/components/erp/engine/VendorMaterialRequests.jsx").read_text()
    has_btn = "vendor-create-replacement-request-btn" in fe_src
    print(f"  tombol 'Buat Permintaan Pengganti' di portal vendor: "
          f"{'ADA' if has_btn else 'TIDAK ADA'}")
    print(f"  {R if not has_btn else G}→ BUG 4 {'TERBUKTI' if not has_btn else 'TIDAK ADA'}{X}")

    if "--keep" not in sys.argv:
        fe.clean(db)
        print(f"\n{C}data uji dibersihkan{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
