#!/usr/bin/env python3
"""verify_fase_h1_kirim_material_potong_stok.py — FASE H-1 (2026-08-15).

MEMBUKTIKAN keluhan pemilik tertutup:
  *"kirim material ke cmt — bahan dikirimkan dan berkurang, tidak perlu ada ketik
    ketik lagi, otomatis terbuat dan langsung berkurang saja, begitupun aksesoris
    dan lainnya."*

CACAT YANG DIJAGA (terukur sebelum perbaikan):
  `POST /api/vendor-shipments` HANYA menulis `vendor_shipments` +
  `vendor_shipment_items`, dan baris itemnya adalah PO ITEM **GARMEN**
  (`sku`/`size`/`qty_sent`) — bukan material. NOL mutasi `rahaza_material_stock`,
  NOL dokumen `rahaza_material_issues`, NOL jurnal. Kain & aksesoris keluar gudang
  ke CMT TANPA JEJAK dan stok gudang tidak pernah turun.

INVARIAN:
  H1-1  Kirim material (PO INTERNAL) MENERBITKAN Material Issue otomatis
        berstatus `issued`, tanpa satu pun field diketik pemakai.
  H1-2  Stok material BENAR-BENAR berkurang sebesar BOM × qty dikirim
        (dihitung ulang dari BOM, bukan dari angka yang dilaporkan endpoint).
  H1-3  Jurnal persediaan ikut terposting (nilai keluar tercatat di buku besar).
  H1-4  Surat jalan menyimpan tautan `material_issue_id` (jejak dua arah).
  H1-5  Stok KURANG ⇒ surat jalan DITOLAK dan TIDAK ADA dokumen tertinggal
        (tidak ada surat jalan yatim, tidak ada stok terpotong sebagian).
  H1-6  MAKLON TIDAK memotong stok DA — material maklon milik KLIEN.
        (Aturan ini sudah ada di `create_mi_draft_from_job`; di sini dijaga
        supaya perbaikan H-1 tidak salah sasaran dan menghapus kain milik DA.)

Pakai:
    python3 scripts/verify_fase_h1_kirim_material_potong_stok.py
    python3 scripts/verify_fase_h1_kirim_material_potong_stok.py --clean
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from gr_common import db_handle, test_doc_number  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

MARK = "VERIFY-FASE-H1"
# FASE G (2026-08-16): nomor PO uji diisi saat jalan agar mengikuti pola resmi
# jenis dokumen PO Produksi Internal (nomor karangan sekarang ditolak backend).
PO_OK = "PO-INT-H1-OK"
PO_OVER = "PO-INT-H1-OVER"
QTY_OK = 10          # kecil, supaya stok demo cukup
QTY_OVER = 9_000_000  # dipastikan melebihi stok apa pun

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
    n = 0
    # Pembersihan berpegang pada penanda MARK di `notes` juga, karena sejak FASE G
    # nomor PO uji ditentukan saat jalan (mengikuti pola resmi), bukan konstanta.
    pos = list(db.production_pos.find(
        {"$or": [{"po_number": {"$in": [PO_OK, PO_OVER]}}, {"notes": MARK}]},
        {"_id": 0, "id": 1}))
    ids = [p["id"] for p in pos]
    if ids:
        vs = [s["id"] for s in db.vendor_shipments.find({"po_id": {"$in": ids}},
                                                        {"_id": 0, "id": 1})]
        mis = list(db.rahaza_material_issues.find(
            {"$or": [{"vendor_shipment_id": {"$in": vs}},
                     {"production_po_id": {"$in": ids}}]}, {"_id": 0, "id": 1, "items": 1}))
        mi_ids = [m["id"] for m in mis]

        # ── 2026-08-19 (Sesi #28) — KEMBALIKAN STOK YANG DIPAKAI ALAT UJI ────
        # DULU cleanup hanya menghapus dokumen MI-nya; stok yang sudah DIPOTONG
        # tidak pernah dikembalikan. Terukur pada data hidup: `ACC-DA-LBL`
        # (Label Woven DA) turun 10 pcs SETIAP kali gate dijalankan —
        # 1800 → 1790 → 1780 → 1770 → 1760 — sementara dokumen yang
        # menjelaskan penurunan itu ikut terhapus. Alat ukur menggerus stok
        # nyata (dan nilai persediaan) tanpa jejak.
        #
        # Pemulihan memakai angka yang PERSIS dipotong (`qty_issued` per baris,
        # di lokasi yang sama), jadi ia betul-betul kebalikan dari yang terjadi.
        restored = 0
        for m in mis:
            for it in (m.get("items") or []):
                mid, loc = it.get("material_id"), it.get("location_id")
                q = float(it.get("qty_issued") or 0)
                if not mid or q <= 0:
                    continue
                db.rahaza_material_stock.update_one(
                    {"material_id": mid, "location_id": loc},
                    {"$inc": {"qty": q, "quantity": q, "total_qty": q}},
                    upsert=True)
                restored += 1
        if restored:
            print(f"  stok alat uji dikembalikan: {restored} baris")

        for coll, q in (
            # Kartu stok menyimpan rujukan BERSARANG (`ref.ref_id`). Query lama
            # memakai `ref_id` di tingkat atas ⇒ TIDAK PERNAH cocok, sehingga
            # kartu stok uji tertinggal sebagai YATIM (menunjuk MI yang sudah
            # tidak ada). Keduanya dipakai agar bentuk lama pun ikut terhapus.
            ("rahaza_stock_ledger", {"$or": [{"ref_id": {"$in": mi_ids}},
                                             {"ref.ref_id": {"$in": mi_ids}}]}),
            ("rahaza_material_movements", {"$or": [{"ref_id": {"$in": mi_ids}},
                                                   {"ref.ref_id": {"$in": mi_ids}}]}),
            ("rahaza_material_issues", {"id": {"$in": mi_ids}}),
            ("vendor_shipment_items", {"shipment_id": {"$in": vs}}),
            ("vendor_shipments", {"id": {"$in": vs}}),
            ("po_items", {"po_id": {"$in": ids}}),
            ("production_pos", {"id": {"$in": ids}}),
        ):
            n += db[coll].delete_many(q).deleted_count
    return n


def stock_snapshot(db):
    out = {}
    for s in db.rahaza_material_stock.find({}, {"_id": 0}):
        out[(s.get("material_id"), s.get("location_id"))] = float(s.get("qty") or 0)
    return out


def bom_expected(db, model_id, size_id, qty):
    """Kebutuhan material yang DIHARAPKAN, dihitung ulang dari BOM (bukan dari API)."""
    bom = db.rahaza_boms.find_one({"model_id": model_id, "size_id": size_id}, {"_id": 0})
    if not bom:
        return {}
    need = {}
    for m in (bom.get("materials") or []):
        code = (m.get("code") or "").strip().upper()
        if not code:
            continue
        need[code] = need.get(code, 0.0) + float(m.get("qty") or 0) * qty
    return need


def make_internal_po(db, adm, po_number, qty, vendor_id):
    src = db.po_items.find_one({"model_id": {"$nin": [None, ""]},
                               "size_id": {"$nin": [None, ""]}}, {"_id": 0})
    if not src:
        print(f"{R}  tidak ada PO item internal ber-model/ukuran untuk dicontoh{X}")
        return None
    st, po = call("POST", "/api/production-pos", adm, {
        "po_number": po_number, "business_type": "internal", "status": "Confirmed",
        "vendor_id": vendor_id, "notes": MARK,
        "po_date": date.today().isoformat(), "deadline": date.today().isoformat(),
        "items": [{"model_id": src["model_id"], "size_id": src["size_id"],
                   "qty": qty, "serial_number": f"SN-{po_number}"}]})
    if st not in (200, 201):
        print(f"{R}  gagal buat PO internal {po_number}: {st} {po}{X}")
        return None
    poi = db.po_items.find_one({"po_id": po["id"]}, {"_id": 0})
    return {"po_id": po["id"], "po_item_id": poi["id"], "sku": poi.get("sku"),
            "model_id": poi.get("model_id"), "size_id": poi.get("size_id")}


def main():  # noqa: C901
    db = db_handle()
    if "--clean" in sys.argv:
        print(f"  dibersihkan {clean(db)} dokumen uji Fase H-1")
        return 0
    adm = login("admin@garment.com", "Admin@123")
    if not adm:
        print(f"{R}login admin gagal{X}")
        return 2
    vendor = db.vendor_partners.find_one({"code": "JMC"}, {"_id": 0})
    if not vendor:
        print(f"{R}vendor demo JMC belum ada{X}")
        return 3
    global PO_OK, PO_OVER
    PO_OK = test_doc_number("production_pos.po_number", adm)
    PO_OVER = test_doc_number("production_pos.po_number", adm, band=9500)

    print(f"{B}FASE H-1 — kirim material ke CMT harus MENGURANGI stok gudang{X}")
    clean(db)

    # ── skenario A: kirim material PO INTERNAL (stok cukup) ─────────────────
    a = make_internal_po(db, adm, PO_OK, QTY_OK, vendor["id"])
    if not a:
        return 3
    expected = bom_expected(db, a["model_id"], a["size_id"], QTY_OK)
    if not expected:
        bad("H1-0", "BOM aktif untuk model/ukuran ini tidak ditemukan — "
                    "uji tidak bisa membedakan kode salah vs data kurang")
        return verdict()
    codes = list(expected.keys())
    mat_ids = {}
    for c in codes:
        m = db.rahaza_materials.find_one({"code": c, "active": True}, {"_id": 0, "id": 1})
        if m:
            mat_ids[c] = m["id"]
    print(f"{C}  BOM {a['sku']} × {QTY_OK} pcs ⇒ "
          + ", ".join(f"{c} {v:g}" for c, v in expected.items()) + f"{X}")

    before = stock_snapshot(db)
    st, sj = call("POST", "/api/vendor-shipments", adm, {
        "vendor_id": vendor["id"], "shipment_number": f"SJ-MTR-{PO_OK}",
        "po_id": a["po_id"], "notes": MARK, "shipment_type": "NORMAL",
        "shipment_date": date.today().isoformat(),
        "items": [{"po_id": a["po_id"], "po_item_id": a["po_item_id"],
                   "sku": a["sku"], "qty_sent": QTY_OK}]})
    if st not in (200, 201):
        bad("H1-1", f"kirim material PO internal DITOLAK ({st})",
            str(sj.get("detail"))[:300])
        return verdict()
    after = stock_snapshot(db)

    mi_info = sj.get("material_issue") or {}
    mi_doc = db.rahaza_material_issues.find_one(
        {"vendor_shipment_id": sj["id"]}, {"_id": 0})
    if not mi_doc:
        bad("H1-1", "tidak ada dokumen Material Issue yang terbentuk")
    elif mi_doc.get("status") != "issued":
        bad("H1-1", f"MI terbentuk tapi status={mi_doc.get('status')} (harus 'issued')")
    else:
        ok("H1-1", f"Material Issue {mi_doc.get('mi_number')} terbit OTOMATIS "
                   f"berstatus issued — 0 field diketik pemakai",
           f"{len(mi_doc.get('items') or [])} baris material dari BOM, "
           f"lokasi dipilih sistem (stok terbanyak)")

    # ── H1-2: stok benar-benar berkurang sebesar BOM × qty ─────────────────
    wrong = []
    for c, need_qty in expected.items():
        mid = mat_ids.get(c)
        if not mid:
            wrong.append(f"{c}: master material tidak ditemukan")
            continue
        b = sum(v for (m, _l), v in before.items() if m == mid)
        aft = sum(v for (m, _l), v in after.items() if m == mid)
        delta = round(b - aft, 4)
        if abs(delta - round(need_qty, 4)) > 0.001:
            wrong.append(f"{c}: turun {delta:g} (harus {need_qty:g})")
    if wrong:
        bad("H1-2", "stok TIDAK berkurang sesuai BOM", "; ".join(wrong))
    else:
        ok("H1-2", "stok material berkurang TEPAT sebesar BOM × qty dikirim",
           "; ".join(f"{c} −{v:g}" for c, v in expected.items()))

    # ── H1-3: jurnal persediaan terposting ─────────────────────────────────
    je, je_no = None, None
    if mi_doc:
        je = mi_doc.get("gl_je_id")
        je_no = mi_doc.get("gl_je_number")
        if not je:
            j = db.rahaza_journal_entries.find_one(
                {"$or": [{"source_ref": f"mi:{mi_doc['id']}"},
                         {"ref_id": mi_doc["id"]},
                         {"reference": mi_doc.get("mi_number")}]}, {"_id": 0})
            je, je_no = (j or {}).get("id"), (j or {}).get("je_number")
    if je:
        nilai = 0.0
        for it in (mi_doc.get("items") or []):
            m = db.rahaza_materials.find_one({"id": it["material_id"]},
                                             {"_id": 0, "unit_cost": 1})
            nilai += float(it.get("qty_issued") or 0) * float((m or {}).get("unit_cost") or 0)
        ok("H1-3", "jurnal persediaan ikut terposting (nilai keluar masuk buku besar)",
           f"{je_no or str(je)[:12]} · nilai material keluar Rp {nilai:,.0f}"
           .replace(",", "."))
    else:
        bad("H1-3", "tidak ada jurnal untuk pengeluaran material ini",
            f"MI={(mi_doc or {}).get('mi_number')} · "
            f"post_error={(mi_doc or {}).get('post_error')}")

    # ── H1-4: tautan dua arah ──────────────────────────────────────────────
    fresh_sj = db.vendor_shipments.find_one({"id": sj["id"]}, {"_id": 0})
    if (fresh_sj or {}).get("material_issue_id") and mi_doc:
        ok("H1-4", "surat jalan ↔ Material Issue saling menunjuk (jejak dua arah)",
           f"SJ {fresh_sj.get('shipment_number')} → MI "
           f"{fresh_sj.get('material_issue_number')}")
    else:
        bad("H1-4", "surat jalan tidak menyimpan tautan material_issue_id")

    # ── H1-5: stok kurang ⇒ ditolak, tidak ada dokumen tertinggal ──────────
    b2 = make_internal_po(db, adm, PO_OVER, QTY_OVER, vendor["id"])
    if not b2:
        bad("H1-5", "gagal menyiapkan PO untuk uji stok kurang")
    else:
        snap = stock_snapshot(db)
        st2, d2 = call("POST", "/api/vendor-shipments", adm, {
            "vendor_id": vendor["id"], "shipment_number": f"SJ-MTR-{PO_OVER}",
            "po_id": b2["po_id"], "notes": MARK, "shipment_type": "NORMAL",
            "shipment_date": date.today().isoformat(),
            "items": [{"po_id": b2["po_id"], "po_item_id": b2["po_item_id"],
                       "sku": b2["sku"], "qty_sent": QTY_OVER}]})
        detail = str(d2.get("detail") or d2)
        left = db.vendor_shipments.count_documents(
            {"shipment_number": f"SJ-MTR-{PO_OVER}"})
        snap2 = stock_snapshot(db)
        moved = [f"{k}: {v} → {snap2.get(k)}" for k, v in snap.items()
                 if abs(snap2.get(k, v) - v) > 0.0001]
        if st2 in (200, 201):
            bad("H1-5", f"kirim {QTY_OVER} pcs DITERIMA padahal stok jelas tidak cukup")
        elif left:
            bad("H1-5", f"ditolak TAPI {left} surat jalan tertinggal (dokumen yatim)")
        elif moved:
            bad("H1-5", "ditolak TAPI stok sudah terpotong sebagian", "; ".join(moved[:3]))
        elif "tidak cukup" not in detail.lower() and "TIDAK dibuat" not in detail:
            bad("H1-5", f"ditolak dengan pesan yang tidak menjelaskan ({st2})", detail[:220])
        else:
            ok("H1-5", "stok kurang ⇒ surat jalan DITOLAK, 0 dokumen tertinggal, "
                       "0 stok terpotong", detail[:200])

    # ── H1-6: maklon TIDAK memotong stok DA ───────────────────────────────
    # Diuji dengan MEMBUAT kiriman maklon sungguhan (1 pcs) — bukan sekadar
    # memeriksa data lama — supaya invariannya tetap terjaga walau data demo hilang.
    mk = None
    for po in db.production_pos.find({"business_type": "maklon"}, {"_id": 0}).limit(20):
        for it in db.po_items.find({"po_id": po["id"]}, {"_id": 0}):
            sent = sum(int(v.get("qty_sent") or 0) for v in
                       db.vendor_shipment_items.find({"po_item_id": it["id"]}, {"_id": 0}))
            if int(it.get("qty") or 0) - sent >= 1 and po.get("vendor_id"):
                mk = {"po": po, "item": it}
                break
        if mk:
            break
    if not mk:
        print(f"{Y}  H1-6 dilewati: tidak ada PO maklon dengan sisa qty ke vendor{X}")
    else:
        snap3 = stock_snapshot(db)
        sjno = f"SJ-MTR-{MARK}-MK"
        st3, d3 = call("POST", "/api/vendor-shipments", adm, {
            "vendor_id": mk["po"]["vendor_id"], "shipment_number": sjno,
            "po_id": mk["po"]["id"], "notes": MARK, "shipment_type": "NORMAL",
            "shipment_date": date.today().isoformat(),
            "items": [{"po_id": mk["po"]["id"], "po_item_id": mk["item"]["id"],
                       "sku": mk["item"].get("sku"), "qty_sent": 1}]})
        if st3 not in (200, 201):
            bad("H1-6", f"kiriman material MAKLON justru DITOLAK ({st3}) — "
                        f"perbaikan H-1 tidak boleh memblokir alur maklon",
                str(d3.get("detail"))[:250])
        else:
            mi_mk = db.rahaza_material_issues.find_one(
                {"vendor_shipment_id": d3["id"]}, {"_id": 0})
            snap4 = stock_snapshot(db)
            moved_mk = [k for k, v in snap3.items() if abs(snap4.get(k, v) - v) > 0.0001]
            if mi_mk:
                bad("H1-6", "kiriman material MAKLON memotong stok DA — salah sasaran: "
                            "material maklon milik KLIEN",
                    f"MI {mi_mk.get('mi_number')} terbentuk")
            elif moved_mk:
                bad("H1-6", "kiriman MAKLON mengubah stok DA", str(moved_mk[:3]))
            elif d3.get("material_issue"):
                bad("H1-6", "respons maklon masih memuat material_issue",
                    json.dumps(d3.get("material_issue"))[:200])
            else:
                ok("H1-6", "kiriman MAKLON diterima TANPA memotong stok DA "
                           "(material milik klien, bukan gudang DA)",
                   f"SJ {sjno} · PO {mk['po'].get('po_number')} · "
                   f"0 baris stok berubah")
            db.vendor_shipment_items.delete_many({"shipment_id": d3["id"]})
            db.vendor_shipments.delete_one({"id": d3["id"]})

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
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian pengeluaran material terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
