#!/usr/bin/env python3
"""verify_monitoring_cmt_potongan.py — INV-F28 (2026-06, keluhan pemilik).

Monitoring CMT (`cmt-monitor`) memakai `services/cmt_kejar.py`. Empat cacat yang
dilaporkan pemilik dan dibuktikan skrip ini:

  F28-1  "Potongan ke CMT" menjumlahkan SEMUA `vendor_shipment_items` — termasuk
         surat jalan ANAK (PENGGANTI/TAMBAHAN) — sehingga potongan yang dilaporkan
         MELEBIHI qty order. Potongan harus SESUAI ORDER (hanya kiriman NORMAL);
         kiriman pengganti dilaporkan terpisah, bukan dihilangkan.
  F28-2  Akibat F28-1, "Sisa di CMT" (dikirim − disetor) memunculkan sisa HANTU
         walaupun CMT sudah menyetor semuanya.
  F28-3  Papan hanya membuang PO `Closed/Cancelled/Selesai`; PO **`Completed`**
         tetap ikut dihitung. Harus ada dua sudut pandang: `scope=running`
         (default, PO berjalan) dan `scope=all`.
  F28-4  Tidak ada angka "potongan yang belum dikirim ke CMT" (masih di gudang)
         maupun "potongan yang sudah dikirim ke buyer" — padahal keduanya bisa
         dihitung dari SSOT yang sudah ada.
  F28-5  Rantai PENGGANTI tidak terlacak di layar: permintaan yang disetujui
         menerbitkan surat jalan anak, tetapi tidak ada penunjuk balik
         (anak → permintaan) maupun rekap qty anak di surat jalan induk.

Pakai:
    python3 scripts/verify_monitoring_cmt_potongan.py
    python3 scripts/verify_monitoring_cmt_potongan.py --clean
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "lib"))

import verify_fase_e_kapasitas_kirim as fe  # noqa: E402
from gr_common import db_handle, test_doc_number  # noqa: E402

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
call, login = fe.call, fe.login
FE_DIR = Path("/app/frontend/src/components/erp")

QTY_REPLACE = 5      # pcs pengganti yang disetujui
QTY_DRAFT = 50       # PO draft (belum dikirim ke CMT sama sekali)
QTY_TO_BUYER = 40    # dispatch ke buyer

PASS, FAIL = [], []


def ok(code, msg, extra=""):
    PASS.append(code)
    print(f"{G}  ✓ {code}{X} {msg}" + (f"\n         {C}{extra}{X}" if extra else ""))


def bad(code, msg, extra=""):
    FAIL.append(code)
    print(f"{R}  ✗ {code}{X} {msg}" + (f"\n         {extra}" if extra else ""))


def _iv(v):
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def rows_of(token, scope=None):
    q = f"?scope={scope}" if scope else ""
    st, d = call("GET", f"/api/dewi/cmt-kejar{q}", token)
    return st, {r.get("po_number"): r for r in (d.get("rows") or [])}, d


def dash_of(token, scope=None):
    q = f"?scope={scope}" if scope else ""
    st, d = call("GET", f"/api/dewi/cmt-kejar/dashboard{q}", token)
    return st, d


def clean_extra(db):
    """Hapus jejak yang di luar cakupan fe.clean(): permintaan material + SJ anak."""
    n = 0
    reqs = list(db.material_requests.find({"reason": fe.MARK}, {"_id": 0, "id": 1,
                                                               "child_shipment_id": 1}))
    child_ids = [r.get("child_shipment_id") for r in reqs if r.get("child_shipment_id")]
    if child_ids:
        n += db.vendor_shipment_items.delete_many({"shipment_id": {"$in": child_ids}}).deleted_count
        n += db.accessory_shipment_items.delete_many({"shipment_id": {"$in": child_ids}}).deleted_count
        n += db.vendor_shipments.delete_many({"id": {"$in": child_ids}}).deleted_count
    n += db.material_requests.delete_many({"reason": fe.MARK}).deleted_count
    n += fe.clean(db)
    return n


# ══════════════════════════════════════════════════════════════════════════════
def buat_pengganti(db, adm, ven, sc):
    """Vendor mengajukan PENGGANTI, admin menyetujui ⇒ surat jalan anak terbit."""
    parent = db.vendor_shipments.find_one(
        {"po_id": sc["po_id"], "shipment_type": "NORMAL"}, {"_id": 0})
    if not parent:
        bad("F28-0", "surat jalan material NORMAL tidak ditemukan di skenario")
        return None, None
    vsi = db.vendor_shipment_items.find_one({"shipment_id": parent["id"]}, {"_id": 0})
    st, req = call("POST", "/api/material-requests", ven or adm, {
        "vendor_id": parent["vendor_id"], "request_type": "REPLACEMENT",
        "original_shipment_id": parent["id"], "po_id": sc["po_id"],
        "reason": fe.MARK,
        "items": [{"shipment_item_id": vsi["id"], "po_item_id": sc["po_item_id"],
                   "sku": sc["sku"], "requested_qty": QTY_REPLACE,
                   "reason": "bahan cacat saat inspeksi"}]})
    if st not in (200, 201):
        bad("F28-0", f"vendor gagal mengajukan PENGGANTI ({st})", str(req)[:200])
        return parent, None
    st, appr = call("PUT", f"/api/material-requests/{req['id']}", adm,
                    {"status": "Approved", "admin_notes": fe.MARK})
    if st != 200 or not appr.get("child_shipment_id"):
        bad("F28-0", f"admin gagal menyetujui PENGGANTI ({st})", str(appr)[:200])
        return parent, None
    return parent, appr


def cek_potongan(adm, sc, po_no):
    """F28-1 · F28-2 — potongan sesuai order, pengganti dilaporkan terpisah."""
    st, rows, _ = rows_of(adm)
    row = rows.get(po_no) or {}
    if st != 200 or not row:
        bad("F28-1", f"PO uji tidak ada di papan KEJAR ({st})", json.dumps(list(rows))[:150])
        return
    order = _iv(row.get("qty_ordered"))
    sent = _iv(row.get("qty_sent_cmt"))
    extra = _iv(row.get("qty_sent_extra"))
    if sent == order and extra == QTY_REPLACE:
        ok("F28-1", f"potongan ke CMT = {sent} pcs (SESUAI order {order}); kiriman "
                    f"pengganti {extra} pcs dilaporkan terpisah",
           f"rincian: {json.dumps(row.get('qty_sent_extra_by_type') or {})}")
    elif sent > order:
        bad("F28-1", f"potongan ke CMT {sent} pcs MELEBIHI order {order} pcs — kiriman "
                     f"pengganti ikut dijumlahkan",
            f"qty_sent_extra={row.get('qty_sent_extra')} (harus {QTY_REPLACE})")
    else:
        bad("F28-1", f"potongan {sent} (order {order}) / pengganti dilaporkan "
                     f"{extra} — harus {order} dan {QTY_REPLACE}", json.dumps(row)[:220])

    outstanding = _iv(row.get("qty_outstanding_cmt"))
    returned = _iv(row.get("qty_returned"))
    if outstanding == max(0, sent - returned) and outstanding == 0:
        ok("F28-2", f"sisa di CMT = 0 (dikirim {sent} − disetor {returned}) — tidak ada "
                    f"sisa hantu dari kiriman pengganti")
    else:
        bad("F28-2", f"sisa di CMT {outstanding} pcs padahal dikirim {sent} & disetor "
                     f"{returned} — sisa hantu dari kiriman pengganti", json.dumps(row)[:200])


def cek_scope(db, adm, sc, po_no):
    """F28-3 — PO 'Completed' tidak ikut pada scope berjalan."""
    st, done = call("POST", "/api/production-pos", adm, {
        "po_number": fe.test_doc_number("production_pos.po_number_maklon", adm)
        if hasattr(fe, "test_doc_number") else test_doc_number("production_pos.po_number_maklon", adm),
        "business_type": "maklon", "buyer_id": None, "status": "Completed", "notes": fe.MARK,
        "po_date": date.today().isoformat(), "items": []})
    if st not in (200, 201):
        bad("F28-3", f"gagal membuat PO uji berstatus Completed ({st})", str(done)[:200])
        return
    db.production_pos.update_one({"id": done["id"]}, {"$set": {"status": "Completed"}})
    st1, run_rows, drun = rows_of(adm, "running")
    st2, all_rows, dall = rows_of(adm, "all")
    no_done = done.get("po_number")
    if st1 == 200 and st2 == 200 and no_done not in run_rows and no_done in all_rows:
        ok("F28-3", f"PO {no_done} (Completed) DIBUANG dari 'PO Berjalan' dan tetap "
                    f"terlihat di 'Semua PO'",
           f"berjalan {drun.get('count')} PO · semua {dall.get('count')} PO")
    else:
        bad("F28-3", "papan tidak bisa memisahkan PO berjalan vs semua",
            f"http={st1}/{st2} completed_di_running={no_done in run_rows} "
            f"completed_di_all={no_done in all_rows}")
    _, dsh_run = dash_of(adm, "running")
    _, dsh_all = dash_of(adm, "all")
    if dsh_run.get("scope") == "running" and _iv(dsh_all.get("total_po")) > _iv(dsh_run.get("total_po")):
        ok("F28-3b", f"kartu ikut berubah: berjalan {dsh_run.get('total_po')} PO vs semua "
                     f"{dsh_all.get('total_po')} PO (kartu menyebut scope-nya)")
    else:
        bad("F28-3b", "kartu tidak membedakan scope",
            f"run={dsh_run.get('total_po')}/{dsh_run.get('scope')} all={dsh_all.get('total_po')}")


def cek_kartu_baru(db, adm, sc, po_no):
    """F28-4 — belum dikirim ke CMT (termasuk PO Draft) + sudah dikirim ke buyer."""
    st, draft = call("POST", "/api/production-pos", adm, {
        "po_number": test_doc_number("production_pos.po_number_maklon", adm),
        "business_type": "maklon", "status": "Draft", "notes": fe.MARK,
        "po_date": date.today().isoformat(),
        "items": [{"sku": "DRAFT-BELUM-KIRIM", "product_name": "Uji draft",
                   "qty": QTY_DRAFT, "cmt_price_snapshot": 1000}]})
    if st not in (200, 201):
        bad("F28-4", f"gagal membuat PO Draft uji ({st})", str(draft)[:200])
        return
    # dispatch sebagian ke buyer supaya angka "sudah dikirim ke buyer" bisa diuji
    call("POST", "/api/buyer-shipments", adm, {
        "po_id": sc["po_id"], "shipment_date": date.today().isoformat(), "notes": fe.MARK,
        "source_receipt_ids": [sc["receipt_id"]], "receiver_type": "buyer",
        "items": [{"po_item_id": sc["po_item_id"], "sku": sc["sku"],
                   "qty_shipped": QTY_TO_BUYER}]})

    st, rows, _ = rows_of(adm, "running")
    row = rows.get(po_no) or {}
    drow = rows.get(draft.get("po_number")) or {}
    _, dsh = dash_of(adm, "running")
    if _iv(row.get("qty_shipped_buyer")) == QTY_TO_BUYER and _iv(dsh.get("qty_shipped_buyer")) >= QTY_TO_BUYER:
        ok("F28-4a", f"potongan yang SUDAH dikirim ke buyer = {QTY_TO_BUYER} pcs "
                     f"(kartu total {dsh.get('qty_shipped_buyer')})",
           f"sisa bisa kirim menurut papan: {row.get('qty_shippable_buyer')}")
    else:
        bad("F28-4a", "angka 'sudah dikirim ke buyer' tidak ada / salah",
            f"baris={row.get('qty_shipped_buyer')} kartu={dsh.get('qty_shipped_buyer')} "
            f"(harus {QTY_TO_BUYER})")

    if (_iv(drow.get("qty_not_sent_cmt")) == QTY_DRAFT
            and _iv(dsh.get("qty_not_sent_cmt")) >= QTY_DRAFT
            and _iv(dsh.get("qty_not_sent_draft")) >= QTY_DRAFT):
        ok("F28-4b", f"potongan BELUM dikirim ke CMT: PO Draft {QTY_DRAFT} pcs terhitung "
                     f"penuh (kartu {dsh.get('qty_not_sent_cmt')} pcs, dari draft "
                     f"{dsh.get('qty_not_sent_draft')} pcs)")
    else:
        bad("F28-4b", "angka 'belum dikirim ke CMT' tidak ada / tidak memuat PO Draft",
            f"baris_draft={drow.get('qty_not_sent_cmt')} kartu={dsh.get('qty_not_sent_cmt')} "
            f"draft={dsh.get('qty_not_sent_draft')} (harus ≥{QTY_DRAFT})")

    # F28-4c: kartu = penjumlahan baris papan (satu sumber, bukan dua rumus)
    st, rows2, d2 = rows_of(adm, "running")
    tot = {k: sum(_iv(r.get(k)) for r in rows2.values())
           for k in ("qty_ordered", "qty_sent_cmt", "qty_sent_extra",
                     "qty_shipped_buyer", "qty_not_sent_cmt")}
    _, dsh2 = dash_of(adm, "running")
    beda = {k: (v, _iv(dsh2.get(k))) for k, v in tot.items() if v != _iv(dsh2.get(k))}
    if not beda:
        ok("F28-4c", "kartu ringkasan = penjumlahan baris papan untuk 5 angka "
                     "(potongan · pengganti · ke buyer · belum kirim · order)")
    else:
        bad("F28-4c", "kartu tidak sama dengan penjumlahan barisnya (dua rumus)",
            json.dumps(beda)[:220])


def cek_lacak_pengganti(db, adm, ven, parent, appr):
    """F28-5 — rantai pengganti terlacak dua arah."""
    if not appr:
        bad("F28-5", "tidak ada permintaan pengganti yang disetujui untuk diuji")
        return
    child_id = appr.get("child_shipment_id")
    st, child = call("GET", f"/api/vendor-shipments/{child_id}", adm)
    st2, pdet = call("GET", f"/api/vendor-shipments/{parent['id']}", adm)
    st3, mrs = call("GET", "/api/material-requests?request_type=REPLACEMENT", adm)
    mr = next((m for m in (mrs if isinstance(mrs, list) else [])
               if m.get("id") == appr.get("id")), {})
    child_qty = _iv(pdet.get("child_qty_total"))
    if (st == 200 and child.get("material_request_number")
            and child.get("is_child_shipment") is True
            and st2 == 200 and child_qty == QTY_REPLACE
            and st3 == 200 and mr.get("child_shipment_number")
            and mr.get("child_shipment_status")):
        ok("F28-5", f"rantai pengganti terlacak: permintaan {mr.get('request_number')} → "
                    f"SJ {mr.get('child_shipment_number')} (status "
                    f"{mr.get('child_shipment_status')}) → induk melaporkan "
                    f"{child_qty} pcs pengganti",
           f"anak menunjuk balik ke {child.get('material_request_number')}")
    else:
        bad("F28-5", "rantai pengganti belum terlacak dua arah",
            f"http={st}/{st2}/{st3} anak→permintaan={child.get('material_request_number')} "
            f"induk.child_qty_total={pdet.get('child_qty_total')} (harus {QTY_REPLACE}) "
            f"permintaan.child_status={mr.get('child_shipment_status')}")


def cek_keseimbangan(adm, po_no):
    """F28-7 — 12 kartu harus bisa dipertanggungjawabkan: 5 identitas + penyebutan PO."""
    st, rows, _ = rows_of(adm, "running")
    row = rows.get(po_no) or {}
    _, dsh = dash_of(adm, "running")
    bal = dsh.get("balance") or {}
    checks = {c.get("key"): c for c in (bal.get("checks") or [])}
    if st != 200 or sorted(checks) != ["buyer", "cmt", "order", "qc", "reject"]:
        bad("F28-7", "backend tidak melaporkan 5 identitas keseimbangan",
            json.dumps(sorted(checks))[:150])
        return

    # identitas diuji pada PO uji sendiri (bebas dari data demo lama)
    o, ns, sc_ = _iv(row.get("qty_ordered")), _iv(row.get("qty_not_sent_cmt")), _iv(row.get("qty_sent_cmt"))
    out, ret = _iv(row.get("qty_outstanding_cmt")), _iv(row.get("qty_returned"))
    acc, rej = _iv(row.get("qty_accepted")), _iv(row.get("qty_reject"))
    rep, scr, ropen = _iv(row.get("qty_repaired")), _iv(row.get("qty_scrap")), _iv(row.get("qty_reject_open"))
    shp, shb = _iv(row.get("qty_shipped_buyer")), _iv(row.get("qty_shippable_buyer"))
    pecah = []
    if o != ns + sc_: pecah.append(f"order {o} ≠ {ns}+{sc_}")
    if sc_ != out + ret: pecah.append(f"keCMT {sc_} ≠ {out}+{ret}")
    if ret != acc + rej: pecah.append(f"disetor {ret} ≠ {acc}+{rej}")
    if rej != rep + scr + ropen: pecah.append(f"reject {rej} ≠ {rep}+{scr}+{ropen}")
    if acc + rep != shp + shb: pecah.append(f"siap {acc}+{rep} ≠ {shp}+{shb}")
    if pecah:
        bad("F28-7", f"angka PO uji TIDAK seimbang: {' · '.join(pecah)}", json.dumps(row)[:250])
    else:
        ok("F28-7", f"5 identitas cocok pada PO uji: order {o} = gudang {ns} + keCMT {sc_} · "
                    f"disetor {ret} = lolos {acc} + reject {rej} · reject = permak {rep} + "
                    f"scrap {scr} + belum jelas {ropen} · siap {acc + rep} = terkirim {shp} + "
                    f"sisa {shb}")

    # identitas yang pecah secara agregat WAJIB menyebut PO penyebabnya
    bisu = [k for k, c in checks.items() if not c.get("ok") and not (c.get("offenders") or [])]
    if bisu:
        bad("F28-7b", f"{len(bisu)} identitas pecah TANPA menyebut PO penyebab: {bisu} — "
                      f"pemakai tidak bisa menelusuri", json.dumps(
            {k: {kk: checks[k].get(kk) for kk in ("left", "right", "diff")} for k in bisu})[:200])
    else:
        rusak = [k for k, c in checks.items() if not c.get("ok")]
        ok("F28-7b", "setiap identitas yang pecah menyebut PO penyebabnya"
                     + (f" (pecah: {rusak})" if rusak else " (semuanya seimbang)"),
           "; ".join(f"{k}: {checks[k].get('offenders')}" for k in rusak)[:200] or None)


def cek_layar():
    """F28-6 — pintu di layar benar-benar ada."""
    wajib = [
        ("CMTMonitorModule.jsx", "monitor-scope-", "chip 'PO Berjalan' ↔ 'Semua PO'"),
        ("CMTMonitorModule.jsx", "kpi-belum-ke-cmt", "kartu 2 'Belum dikirim ke CMT'"),
        ("CMTMonitorModule.jsx", "kpi-lolos-qc", "kartu 6 'Lolos QC'"),
        ("CMTMonitorModule.jsx", "kpi-reject-belum-jelas", "kartu 7 'Reject Belum Jelas'"),
        ("CMTMonitorModule.jsx", "kpi-permak-berhasil", "kartu 8 'Permak Berhasil'"),
        ("CMTMonitorModule.jsx", "kpi-scrap", "kartu 9 'Scrap / Hilang'"),
        ("CMTMonitorModule.jsx", "kpi-sisa-bisa-kirim", "kartu 10 'Sisa Bisa Kirim'"),
        ("CMTMonitorModule.jsx", "kpi-ke-buyer", "kartu 11 'Sudah dikirim ke buyer'"),
        ("CMTMonitorModule.jsx", "kpi-biaya-permak", "kartu 12 biaya (jahit + permak dipisah)"),
        ("CMTMonitorModule.jsx", "monitor-balance-strip", "baris pemeriksa keseimbangan"),
        ("CMTMonitorModule.jsx", "chip-po-telat", "penanda PO TELAT (turun dari kartu)"),
        ("CMTMonitorModule.jsx", "chip-komponen-kurang", "penanda Komponen Kurang"),
        ("CMTMonitorModule.jsx", "qty_sent_extra", "rincian pengganti/tambahan pada kartu potongan"),
        ("engine/BuyerShipmentModule.jsx", "outstanding-po-board", "papan sisa kirim per PO"),
        ("engine/BuyerShipmentModule.jsx", "board-dispatch-", "tombol lanjut dispatch di papan"),
        ("engine/MaterialRequestTracker.jsx", "mr-tracker-", "pelacak rantai pengganti"),
        ("engine/VendorMaterialRequests.jsx", "MaterialRequestTracker", "pelacak dipakai di portal vendor"),
        ("engine/VendorShipmentModule.jsx", "MaterialRequestTracker", "pelacak dipakai di layar admin"),
    ]
    hilang = []
    for fname, needle, label in wajib:
        p = FE_DIR / fname
        src = p.read_text(encoding="utf-8") if p.exists() else ""
        if needle not in src:
            hilang.append(f"{fname}: {label}")
    if hilang:
        bad("F28-6", f"{len(hilang)} pintu layar HILANG", " | ".join(hilang))
    else:
        ok("F28-6", f"{len(wajib)} pintu layar hadir: chip scope, 2 kartu baru, rincian "
                    f"pengganti, papan sisa kirim + tombolnya, pelacak pengganti")


def verdict(db):
    if "--keep" not in sys.argv:
        try:
            clean_extra(db)
        except Exception:  # noqa: BLE001
            pass
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian monitoring CMT terjaga{X}")
    return 0


def main():
    db = db_handle()
    if "--clean" in sys.argv:
        print(f"  dibersihkan {clean_extra(db)} dokumen uji")
        return 0
    adm = login("admin@garment.com", "Admin@123")
    if not adm:
        print(f"{R}login admin gagal{X}")
        return 2
    ven = login("cmtvendor@dewiaditya.id", "Dewi@123")

    print(f"{B}INV-F28 — potongan sesuai order · scope PO · kartu baru · lacak pengganti{X}")
    fe.PO_NO = test_doc_number("production_pos.po_number_maklon", adm)
    clean_extra(db)
    sc = fe.build_scenario(db, adm, ven)
    if not sc:
        return 3
    po_no = fe.PO_NO

    parent, appr = buat_pengganti(db, adm, ven, sc)
    cek_potongan(adm, sc, po_no)
    cek_scope(db, adm, sc, po_no)
    cek_kartu_baru(db, adm, sc, po_no)
    cek_keseimbangan(adm, po_no)
    cek_lacak_pengganti(db, adm, ven, parent or {}, appr)
    cek_layar()
    return verdict(db)


if __name__ == "__main__":
    sys.exit(main())
