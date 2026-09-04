#!/usr/bin/env python3
"""verify_permak_dispatch_aksesoris.py — INV-F27 (2026-06, keluhan pemilik).

Menjaga LIMA cacat yang benar-benar dilaporkan pemilik pada alur produksi/maklon.
Semuanya sudah dibuktikan MERAH lebih dulu oleh
`scripts/_repro_5bug_produksi_maklon.py` (jangan hapus skrip itu — ia bukti
"sebelum"), gate ini bukti "sesudah" yang ikut jalan setiap sesi:

  F27-1  Permak dari form manual ("Buat Permak Baru", tanpa memilih baris
         penerimaan) HARUS ditautkan server ke baris penerimaan yang masih punya
         sisa reject. Dulu tersimpan tanpa tautan ⇒ permak berhasil TIDAK pernah
         menaikkan hasil permak di baris penerimaan.
  F27-2  Permak berhasil ⇒ `qty_reworked_ok` naik, stok FG dilepas, dan sisa
         bisa kirim ke buyer NAIK sebesar qty permak.
  F27-3  Qty permak melebihi sisa reject DITOLAK 400 dengan pesan yang
         menjelaskan, dan TIDAK meninggalkan dokumen permak yatim.
  F27-4  Dispatch lanjutan pada surat jalan yang SAMA (`shipment_id`) menambah
         `dispatch_seq` berikutnya — nomor surat jalan tidak berubah, tidak lahir
         surat jalan kedua untuk PO yang sama.
  F27-5  Lanjutan TIDAK melonggarkan pagar: melebihi sisa bisa kirim tetap 400;
         `shipment_id` asing 404.
  F27-6  Pratinjau aksesoris BOM di form buat PO = angka yang AKHIRNYA TERSIMPAN
         di `po_accessories` (satu mesin, bukan rumus kedua).
  F27-7  Surat jalan ANAK (pengganti/tambahan) TIDAK membawa daftar aksesoris PO
         — kalau tidak, form inspeksi vendor memuat aksesoris yang tak pernah
         dikirim dan lahir permintaan aksesoris palsu.
  F27-8  LAYAR benar-benar punya pintunya (anti "backend jadi, UI tidak"):
         tombol "+ Dispatch", panel aksesoris BOM di form PO, tombol permintaan
         PENGGANTI di portal vendor, dan modal yang meneruskan `request_type`.

Pakai:
    python3 scripts/verify_permak_dispatch_aksesoris.py
    python3 scripts/verify_permak_dispatch_aksesoris.py --clean
Keluar 0 bila semua invarian HIJAU.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "lib"))

import verify_fase_e_kapasitas_kirim as fe  # noqa: E402  (SATU pembangun skenario)
from gr_common import db_handle, test_doc_number  # noqa: E402

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
call, login = fe.call, fe.login
FE_DIR = Path("/app/frontend/src/components/erp/engine")

PASS, FAIL = [], []


def ok(code, msg, extra=""):
    PASS.append(code)
    print(f"{G}  ✓ {code}{X} {msg}" + (f"\n         {C}{extra}{X}" if extra else ""))


def bad(code, msg, extra=""):
    FAIL.append(code)
    print(f"{R}  ✗ {code}{X} {msg}" + (f"\n         {extra}" if extra else ""))


def _iv(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


# ══════════════════════════════════════════════════════════════════════════════
def cek_permak(db, adm, sc):
    """F27-1 · F27-2 · F27-3 — permak reject dari form manual."""
    poi, rid, line_id = sc["po_item_id"], [sc["receipt_id"]], sc["line_id"]

    # F27-3 lebih dulu: qty melebihi sisa reject harus DITOLAK dan tidak menulis apa pun.
    before = db.dewi_cmt_permak.count_documents({"po_item_id": poi})
    st, res = call("POST", "/api/dewi/cmt-permak", adm, {
        "po_id": sc["po_id"], "po_item_id": poi, "qty": fe.QTY_REJECT + 5,
        "source": "reject", "permak_type": "permak_sendiri", "reason": fe.MARK})
    after = db.dewi_cmt_permak.count_documents({"po_item_id": poi})
    detail = str(res.get("detail") or res)
    if st == 400 and "sisa reject" in detail and after == before:
        ok("F27-3", f"qty permak {fe.QTY_REJECT + 5} > sisa reject {fe.QTY_REJECT} "
                    f"DITOLAK dan tidak menulis dokumen", detail[:170])
    elif st in (200, 201):
        bad("F27-3", f"permak {fe.QTY_REJECT + 5} pcs DITERIMA padahal reject hanya "
                     f"{fe.QTY_REJECT} pcs — hasil permak akan melebihi barang cacatnya")
    else:
        bad("F27-3", f"respons tak terduga ({st}) / dokumen tertinggal "
                     f"({after - before})", detail[:200])

    # F27-1: form manual TANPA source_receipt_line_id → server menautkannya.
    st, permak = call("POST", "/api/dewi/cmt-permak", adm, {
        "po_id": sc["po_id"], "po_item_id": poi, "qty": fe.QTY_REJECT,
        "source": "reject", "permak_type": "permak_sendiri", "reason": fe.MARK})
    if st not in (200, 201):
        bad("F27-1", f"gagal membuat permak dari form manual ({st})",
            str(permak.get("detail"))[:200])
        return
    doc = db.dewi_cmt_permak.find_one({"id": permak["id"]}, {"_id": 0})
    if (doc or {}).get("source_receipt_line_id") == line_id and doc.get("source_link_auto"):
        ok("F27-1", "permak dari form manual OTOMATIS tertaut baris penerimaan "
                    "yang masih punya sisa reject",
           f"{permak.get('permak_number')} → baris {line_id[:8]}… "
           f"(source_receipt_id ikut terisi: {bool(doc.get('source_receipt_id'))})")
    else:
        bad("F27-1", "permak tersimpan TANPA tautan baris penerimaan — hasilnya "
                     "tidak akan pernah menambah stok FG / sisa kirim",
            json.dumps({k: doc.get(k) for k in
                        ("source_receipt_id", "source_receipt_line_id",
                         "source_link_auto")})[:200])
        return

    # F27-2: selesai berhasil → baris penerimaan + kapasitas kirim + stok FG.
    _, _, row_before = fe.cap_of(adm, rid, poi)
    st, res = call("POST", f"/api/dewi/cmt-permak/{permak['id']}/status", adm, {
        "status": "selesai_berhasil", "qty_fixed": fe.QTY_REJECT, "qty_scrap": 0,
        "note": fe.MARK})
    fresh = db.cmt_receipt_lines.find_one({"id": line_id}, {"_id": 0}) or {}
    _, _, row = fe.cap_of(adm, rid, poi)
    effect = ((res or {}).get("effect") or {})
    released = _iv(effect.get("stock_released"))
    naik = _iv(row.get("shippable")) - _iv(row_before.get("shippable"))
    if (st == 200 and _iv(fresh.get("qty_reworked_ok")) == fe.QTY_REJECT
            and _iv(row.get("reworked_ok")) == fe.QTY_REJECT
            and naik == fe.QTY_REJECT and released == fe.QTY_REJECT):
        ok("F27-2", f"permak berhasil ⇒ baris penerimaan +{fe.QTY_REJECT}, sisa bisa "
                    f"kirim naik {naik}, stok FG dilepas {released} pcs",
           f"angka inspeksi asli utuh: qty_actual {fresh.get('qty_actual')} · "
           f"reject_qty {fresh.get('reject_qty')}")
    else:
        bad("F27-2", "permak berhasil tapi rambatannya tidak lengkap",
            f"http={st} qty_reworked_ok={fresh.get('qty_reworked_ok')} "
            f"reworked_ok={row.get('reworked_ok')} Δsisa={naik} "
            f"stock_released={released}")


def cek_dispatch_lanjutan(db, adm, sc):
    """F27-4 · F27-5 — lanjutan dispatch pada surat jalan yang sama."""
    poi, rid = sc["po_item_id"], [sc["receipt_id"]]
    body = {"shipment_date": date.today().isoformat(), "notes": fe.MARK,
            "source_receipt_ids": rid, "receiver_type": "buyer"}

    st1, d1 = call("POST", "/api/buyer-shipments", adm, {
        **body, "items": [{"po_item_id": poi, "sku": sc["sku"], "qty_shipped": 40}]})
    if st1 not in (200, 201):
        bad("F27-4", f"dispatch pertama gagal ({st1})", str(d1.get("detail"))[:200])
        return
    sid, no1 = d1["id"], d1.get("shipment_number")

    st2, d2 = call("POST", "/api/buyer-shipments", adm, {
        **body, "shipment_id": sid,
        "items": [{"po_item_id": poi, "sku": sc["sku"], "qty_shipped": 30}]})
    n_sj = db.buyer_shipments.count_documents({"notes": fe.MARK, "receiver_type": "buyer"})
    seqs = sorted({_iv(i.get("dispatch_seq"))
                   for i in db.buyer_shipment_items.find({"shipment_id": sid}, {"_id": 0})})
    if (st2 in (200, 201) and d2.get("id") == sid
            and d2.get("shipment_number") == no1 and _iv(d2.get("dispatch_seq")) == 2
            and d2.get("is_new") is False and n_sj == 1 and seqs == [1, 2]):
        ok("F27-4", f"lanjutan masuk ke surat jalan yang SAMA sebagai dispatch #2 "
                    f"(nomor tetap {no1})",
           f"1 surat jalan untuk PO ini · dispatch_seq {seqs}")
    else:
        bad("F27-4", "lanjutan melahirkan surat jalan/urutan baru",
            f"http={st2} id_sama={d2.get('id') == sid} no={d2.get('shipment_number')} "
            f"seq={d2.get('dispatch_seq')} is_new={d2.get('is_new')} "
            f"jumlah_sj={n_sj} seqs={seqs}")

    # F27-5a: pagar kapasitas tetap berlaku pada lanjutan (sisa 20 dari 90 lolos QC).
    _, _, row = fe.cap_of(adm, rid, poi)
    sisa = _iv(row.get("shippable"))
    st3, d3 = call("POST", "/api/buyer-shipments", adm, {
        **body, "shipment_id": sid,
        "items": [{"po_item_id": poi, "sku": sc["sku"], "qty_shipped": sisa + 5}]})
    if st3 == 400:
        ok("F27-5", f"lanjutan TIDAK melonggarkan pagar: kirim {sisa + 5} pcs "
                    f"(sisa {sisa}) ditolak", str(d3.get("detail"))[:170])
    else:
        bad("F27-5", f"lanjutan menerima {sisa + 5} pcs padahal sisa hanya {sisa} "
                     f"({st3})", str(d3.get("detail") or d3)[:200])

    # F27-5b: shipment_id asing → 404 (bukan diam-diam membuat surat jalan baru),
    # dan diperiksa SEBELUM pagar qty supaya pesannya tidak menyesatkan.
    st4, d4 = call("POST", "/api/buyer-shipments", adm, {
        **body, "shipment_id": "TIDAK-ADA-9999",
        "items": [{"po_item_id": poi, "sku": sc["sku"], "qty_shipped": 1}]})
    st5, d5 = call("POST", "/api/buyer-shipments", adm, {
        **body, "shipment_id": "TIDAK-ADA-9999",
        "items": [{"po_item_id": poi, "sku": sc["sku"], "qty_shipped": 0}]})
    if st4 == 404 and st5 == 404:
        ok("F27-5b", "shipment_id yang tidak ada → 404 (juga saat qty 0), bukan surat "
                     "jalan baru senyap atau pesan qty yang menyesatkan",
           str(d4.get("detail"))[:150])
    else:
        bad("F27-5b", f"shipment_id asing menghasilkan {st4}/{st5} (harus 404/404)",
            f"{str(d4)[:120]} | {str(d5)[:120]}")


def cek_pratinjau_aksesoris(db, adm, sc):
    """F27-6 — pratinjau form PO = angka yang tersimpan di po_accessories."""
    poi = db.po_items.find_one({"id": sc["po_item_id"]}, {"_id": 0}) or {}
    cat_id = poi.get("catalog_item_id")
    qty = _iv(poi.get("qty"))
    if not cat_id:
        bad("F27-6", "item PO uji tidak punya catalog_item_id — pratinjau tak bisa diuji")
        return
    st, prev = call("POST", "/api/dewi/maklon/bom-templates/preview-accessories", adm,
                    {"items": [{"catalog_item_id": cat_id, "qty": qty}]})
    if st != 200:
        bad("F27-6", f"endpoint pratinjau aksesoris gagal ({st}) — form buat PO tidak "
                     f"punya sumber angka", str(prev)[:200])
        return
    tersimpan = {(r.get("accessory_name") or "").lower(): round(float(r.get("qty_needed") or 0), 3)
                 for r in db.po_accessories.find({"po_id": sc["po_id"]}, {"_id": 0})}
    pratinjau = {(r.get("accessory_name") or "").lower(): round(float(r.get("qty_needed") or 0), 3)
                 for r in (prev.get("accessories") or [])}
    if not tersimpan:
        bad("F27-6", "PO uji tidak punya baris po_accessories — BOM katalog demo kosong?")
    elif pratinjau == tersimpan:
        ok("F27-6", f"pratinjau form = {len(pratinjau)} baris aksesoris, IDENTIK dengan "
                    f"yang tersimpan saat PO disimpan",
           "; ".join(f"{k} {v}" for k, v in list(pratinjau.items())[:4])
           + f" · untuk {prev.get('total_pcs')} pcs")
    else:
        bad("F27-6", "pratinjau berbeda dari yang tersimpan (dua rumus)",
            f"pratinjau={json.dumps(pratinjau)[:150]} tersimpan={json.dumps(tersimpan)[:150]}")


def cek_surat_jalan_anak(db, adm, sc):
    """F27-7 — surat jalan anak tidak membawa aksesoris PO."""
    parent = db.vendor_shipments.find_one(
        {"po_id": sc["po_id"], "shipment_type": "NORMAL"}, {"_id": 0}) or {}
    n_acc_po = db.po_accessories.count_documents({"po_id": sc["po_id"]})
    child_id = "INVF27-CHILD-1"
    db.vendor_shipments.insert_one({
        "id": child_id, "shipment_number": "SJ-INVF27-CHILD-1",
        "vendor_id": parent.get("vendor_id"), "po_id": sc["po_id"],
        "shipment_type": "REPLACEMENT", "parent_shipment_id": parent.get("id"),
        "business_type": "maklon", "status": "Sent", "notes": fe.MARK})
    db.vendor_shipment_items.insert_one({
        "id": "INVF27-CHILD-ITEM-1", "shipment_id": child_id, "po_id": sc["po_id"],
        "po_item_id": sc["po_item_id"], "sku": sc["sku"], "qty_sent": 5,
        "shipment_type": "REPLACEMENT"})
    try:
        st, det = call("GET", f"/api/vendor-shipments/{child_id}", adm)
        st2, lst = call("GET", "/api/vendor-shipments", adm)
        row = next((s for s in (lst if isinstance(lst, list) else [])
                    if s.get("id") == child_id), {})
        n_child = len(det.get("po_accessories") or [])
        if (st == 200 and n_acc_po > 0 and n_child == 0
                and det.get("accessories_scope") == "own"
                and det.get("is_child_shipment") is True
                and _iv(row.get("po_accessories_count")) == 0):
            ok("F27-7", f"surat jalan anak: 0 baris aksesoris PO (PO-nya punya "
                        f"{n_acc_po}) — pengganti hanya membawa isi kirimannya",
               "detail & daftar sepakat (accessories_scope='own', "
               "po_accessories_count=0)")
        else:
            bad("F27-7", "surat jalan anak masih membawa aksesoris PO",
                f"http={st}/{st2} acc_po={n_acc_po} pada_anak={n_child} "
                f"scope={det.get('accessories_scope')} "
                f"count_daftar={row.get('po_accessories_count')}")
    finally:
        db.vendor_shipments.delete_one({"id": child_id})
        db.vendor_shipment_items.delete_one({"id": "INVF27-CHILD-ITEM-1"})


def cek_layar():
    """F27-8 — pintu di LAYAR benar-benar ada (anti 'backend jadi, UI tidak')."""
    wajib = [
        ("BuyerShipmentModule.jsx", "continue-dispatch-", 'tombol "+ Dispatch" pada daftar surat jalan'),
        ("BuyerShipmentModule.jsx", "payload.shipment_id = continueShip.id", "form mengirim shipment_id (lanjutan)"),
        ("ProductionPOModule.jsx", "po-bom-accessories-panel", "panel aksesoris BOM di form buat PO"),
        ("ProductionPOModule.jsx", "preview-accessories", "form memanggil pratinjau aksesoris"),
        ("VendorMaterialRequests.jsx", "vendor-create-replacement-request-btn", 'tombol "Buat Permintaan Pengganti" vendor CMT'),
        ("AdditionalRequestModal.jsx", "request_type: requestType", "modal meneruskan jenis permintaan (bukan ADDITIONAL hardcode)"),
    ]
    hilang = []
    for fname, needle, label in wajib:
        src = (FE_DIR / fname).read_text(encoding="utf-8") if (FE_DIR / fname).exists() else ""
        if needle not in src:
            hilang.append(f"{fname}: {label}")
    if hilang:
        bad("F27-8", f"{len(hilang)} pintu layar HILANG (fitur backend tak terjangkau "
                     f"pemakai)", " | ".join(hilang))
    else:
        ok("F27-8", f"{len(wajib)} pintu layar hadir: tombol lanjutan dispatch, panel "
                    f"aksesoris BOM, tombol permintaan pengganti vendor")


def verdict(db=None):
    if "--keep" not in sys.argv:
        try:
            fe.clean(db or db_handle())
        except Exception:  # noqa: BLE001
            pass
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian permak/dispatch/aksesoris terjaga{X}")
    return 0


def main():
    db = db_handle()
    if "--clean" in sys.argv:
        print(f"  dibersihkan {fe.clean(db)} dokumen uji")
        return 0
    adm = login("admin@garment.com", "Admin@123")
    if not adm:
        print(f"{R}login admin gagal{X}")
        return 2
    ven = login("cmtvendor@dewiaditya.id", "Dewi@123")

    print(f"{B}INV-F27 — permak↔reject, dispatch lanjutan, aksesoris BOM & pengganti{X}")
    fe.PO_NO = test_doc_number("production_pos.po_number_maklon", adm)
    fe.clean(db)
    sc = fe.build_scenario(db, adm, ven)
    if not sc:
        return 3

    cek_permak(db, adm, sc)
    cek_dispatch_lanjutan(db, adm, sc)
    cek_pratinjau_aksesoris(db, adm, sc)
    cek_surat_jalan_anak(db, adm, sc)
    cek_layar()
    return verdict(db)


if __name__ == "__main__":
    sys.exit(main())
