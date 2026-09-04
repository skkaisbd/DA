#!/usr/bin/env python3
"""INV-CMTOV — invarian **Portal CMT Override** (staf DA mengisi atas nama vendor CMT).

KELAS MASALAH YANG DIJAGA (semuanya pernah NYATA, bukan hipotesis)
------------------------------------------------------------------
Fitur ini membuka jalan bagi staf DA untuk MENULIS dokumen produksi atas nama
vendor. Yang ditulis termasuk **progress produksi — dasar perhitungan tagihan
CMT**. Jadi tiga hal harus dijaga selamanya:

  1. **KEWENANGAN.** Kalau header override dihormati untuk role yang tidak
     berhak, staf mana pun bisa menulis angka tagihan. Dan kalau header itu
     hanya *diabaikan* (bukan ditolak), kesalahan integrasi tidak pernah
     terlihat sampai suatu hari header-nya mulai dihormati.
  2. **SCOPING.** Kalau scoping bocor, staf melihat/mengubah pekerjaan vendor
     LAIN — salah vendor = salah tagihan = uang keluar ke pihak yang salah.
  3. **JEJAK.** Kalau stempel `entered_by_staff` hilang, tidak ada cara
     membedakan angka dari vendor dan angka dari staf saat terjadi selisih
     tagihan. Owner secara eksplisit meminta ini terlihat (keputusan 3a).

Ditambah dua bug PRE-EXISTING yang ditutup bersamaan dan harus tidak kambuh:
  * riwayat progress portal vendor SELALU KOSONG (filter memakai `garment_id`
    yang tidak pernah ditulis di jalur `job_item_id`);
  * inbox reminder BOCOR ke semua vendor (scoping memakai role `vendor` saja,
    padahal role portal CMT adalah `cmt_vendor`).

SIFAT SKRIP
-----------
Self-contained: membuat sendiri vendor uji, akun vendor uji, staf uji, PO, dan
surat jalan lewat API sungguhan; lalu MENGHAPUS seluruh jejaknya di `finally`
langsung ke Mongo — termasuk turunan UANG (AR invoice maklon + mirror PO) dan
sweep seluruh koleksi, karena riwayat repo ini menunjukkan daftar-hapus manual
selalu ketinggalan satu efek samping (dan pernah meninggalkan piutang palsu).

Pakai:
    cd /app && python3 scripts/verify_cmt_override.py
    cd /app && python3 scripts/verify_cmt_override.py --keep    # sisakan data uji
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
API = f"{BASE}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
KEEP = "--keep" in sys.argv

MARK = "__CMTOVTEST__"
OVH = "X-CMT-Override-Vendor"

# FASE G (2026-08-16): nomor PO uji WAJIB mengikuti pola resmi jenis dokumennya —
# nomor karangan seperti `__CMTOVTEST__-PO-9F2A1B` sekarang ditolak backend.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gr_common import test_doc_number  # noqa: E402

G, R, Y, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[94m", "\033[0m"
PASSES: list[str] = []
FAILS: list[str] = []


def ok(code: str, msg: str, ev=None):
    PASSES.append(code)
    ex = f" · {json.dumps(ev, default=str)[:150]}" if ev else ""
    print(f"  {G}[OK]{X} {code} — {msg}{ex}")


def bad(code: str, msg: str, ev=None):
    FAILS.append(code)
    ex = f" · {json.dumps(ev, default=str)[:220]}" if ev else ""
    print(f"  {R}[FAIL]{X} {code} — {msg}{ex}")


def expect(cond, code, msg_ok, msg_bad, ev=None):
    (ok if cond else bad)(code, msg_ok if cond else msg_bad, ev)
    return bool(cond)


def H(tok, vendor=None):
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    if vendor:
        h[OVH] = vendor
    return h


def call(method, path, tok=None, vendor=None, body=None, timeout=60):
    fn = getattr(requests, method.lower())
    kw = {"headers": H(tok, vendor) if tok else {"Content-Type": "application/json"},
          "timeout": timeout}
    if body is not None:
        kw["json"] = body
    r = fn(f"{API}{path}", **kw)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text


def login(email, password):
    c, b = call("post", "/auth/login", body={"email": email, "password": password})
    return b.get("token") if c == 200 and isinstance(b, dict) else None


def rows(body):
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for k in ("items", "vendors", "entries", "data"):
            if isinstance(body.get(k), list):
                return body[k]
    return []


def get_db():
    from pymongo import MongoClient
    return MongoClient(MONGO_URL)[DB_NAME]


# ═══════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(f"{B}{'=' * 78}{X}")
    print(f"  {B}INV-CMTOV{X} — Portal CMT Override: kewenangan · scoping · jejak audit · UANG")
    print(f"{B}{'=' * 78}{X}")

    db = get_db()
    created_users: list[str] = []
    vid = None

    try:
        admin = login("admin@garment.com", "Admin@123")
        if not admin:
            bad("OV-0", "login superadmin gagal — gate tidak bisa berjalan")
            return 1

        # ── setup: vendor uji + akun vendornya + staf berwenang ──────────────
        c, vb = call("post", "/vendor-portal/partners", admin, body={
            "name": f"{MARK} Vendor Uji", "code": f"CMTOV{uuid.uuid4().hex[:4].upper()}",
            "notes": f"{MARK} data uji gate", "capacity_pcs": 100})
        vid = vb.get("id") if isinstance(vb, dict) else None
        if not expect(c == 200 and vid, "OV-0", "vendor uji dibuat",
                      "gagal membuat vendor uji", {"http": c}):
            return 1

        v_email = f"cmtovtest.vendor.{uuid.uuid4().hex[:6]}@example.test"
        c, _ = call("post", "/vendor-portal/accounts", admin, body={
            "email": v_email, "name": f"{MARK} Akun Vendor",
            "password": "GateOv@123", "partner_id": vid})
        u = db.users.find_one({"email": v_email}, {"_id": 0, "id": 1})
        if u:
            created_users.append(u["id"])
        vendor_tok = login(v_email, "GateOv@123")

        s_email = f"cmtovtest.staff.{uuid.uuid4().hex[:6]}@example.test"
        c, su = call("post", "/users", admin, body={
            "name": f"{MARK} Staf", "email": s_email, "password": "GateOv@123",
            "role": "admin_produksi", "department": "Produksi"})
        if isinstance(su, dict) and su.get("id"):
            created_users.append(su["id"])
        staff = login(s_email, "GateOv@123")
        if not expect(bool(staff), "OV-0", "staf admin_produksi uji siap",
                      "login staf uji gagal"):
            return 1
        hr = login("hr@dewiaditya.id", "Dewi@123")

        # PO + surat jalan supaya 11 modul punya isi
        po_number = test_doc_number("production_pos.po_number_maklon", admin)
        dl = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
        c, po = call("post", "/production-pos", admin, body={
            "po_number": po_number, "business_type": "maklon", "vendor_id": vid,
            "customer_name": f"{MARK} Buyer", "status": "Confirmed",
            "deadline": dl, "delivery_deadline": dl, "notes": f"{MARK}",
            "items": [{"product_name": f"{MARK} Kaos", "sku": f"{MARK}-M", "size": "M",
                       "color": "Navy", "qty": 50, "serial_number": f"{MARK}-SN1",
                       "cmt_price_snapshot": 8000}]})
        po_id = po.get("id") if isinstance(po, dict) else None
        if not expect(c in (200, 201) and po_id, "OV-0", "PO maklon uji dibuat",
                      "gagal membuat PO uji", {"http": c}):
            return 1
        po_items = list(db.po_items.find({"po_id": po_id}, {"_id": 0, "id": 1, "qty": 1}))
        sj = f"{MARK}-SJ-{uuid.uuid4().hex[:6].upper()}"
        c, sh = call("post", "/vendor-shipments", admin, body={
            "shipment_number": sj, "vendor_id": vid, "po_id": po_id,
            "shipment_type": "NORMAL", "notes": f"{MARK}",
            "items": [{"po_id": po_id, "po_item_id": it["id"], "qty_sent": it["qty"]}
                      for it in po_items]})
        ship_id = sh.get("id") if isinstance(sh, dict) else None
        if not expect(c in (200, 201) and ship_id, "OV-0", "surat jalan uji dibuat",
                      "gagal membuat surat jalan uji", {"http": c}):
            return 1
        c, rem = call("post", "/reminders", admin, body={
            "vendor_id": vid, "po_id": po_id, "po_number": po_number,
            "subject": f"{MARK} reminder", "message": f"{MARK}", "priority": "normal"})
        rem_id = rem.get("id") if isinstance(rem, dict) else None

        money_before = (call("get", "/production/cmt-billing/summary", admin)[1] or {})\
            .get("total_amount")

        # ── OV-1 — role tak berwenang DITOLAK (bukan diabaikan) ──────────────
        c1, _ = call("get", "/vendor/dashboard", hr, vendor=vid)
        c2, _ = call("get", "/cmt-override/vendors", hr)
        expect(c1 == 403 and c2 == 403, "OV-1",
               "role tak berwenang ditolak 403 walau mengirim header override",
               "role tak berwenang TIDAK ditolak — header override dihormati/diabaikan diam-diam",
               {"dashboard": c1, "vendors": c2})

        # ── OV-2 — akun vendor tidak boleh menyamar jadi vendor lain ─────────
        if vendor_tok:
            other = db.vendor_partners.find_one(
                {"id": {"$ne": vid}}, {"_id": 0, "id": 1}) or {}
            c3, _ = call("get", "/vendor-shipments", vendor_tok,
                         vendor=other.get("id") or vid)
            expect(c3 == 403, "OV-2",
                   "akun vendor ditolak memakai header override",
                   "akun vendor BOLEH memakai header override (bisa menyamar vendor lain)",
                   {"http": c3})
        else:
            bad("OV-2", "akun vendor uji tidak bisa login — invarian tak teruji")

        # ── OV-3 — vendor tujuan wajib sah ──────────────────────────────────
        c4, _ = call("get", "/vendor/dashboard", staff, vendor="tidak-ada-vendor-ini")
        db.vendor_partners.update_one({"id": vid}, {"$set": {"is_active": False}})
        c5, _ = call("get", "/vendor/dashboard", staff, vendor=vid)
        db.vendor_partners.update_one({"id": vid}, {"$set": {"is_active": True}})
        expect(c4 == 404 and c5 == 400, "OV-3",
               "vendor tidak ada → 404, vendor non-aktif → 400 (pesan jelas, bukan 500)",
               "validasi vendor tujuan tidak benar", {"tak_ada": c4, "non_aktif": c5})

        # ── OV-4 — staf berwenang TANPA memilih vendor tetap ditolak ─────────
        c6, _ = call("get", "/vendor/dashboard", staff)
        expect(c6 == 403, "OV-4",
               "staf tanpa memilih vendor tidak bisa membuka dashboard vendor",
               "staf tanpa konteks vendor bisa membuka dashboard vendor (data vendor mana?)",
               {"http": c6})

        # ── OV-5 — peringatan dobel input punya bahan yang benar ────────────
        c7, vl = call("get", "/cmt-override/vendors", staff)
        vmap = {v["id"]: v for v in rows(vl)}
        mine = vmap.get(vid, {})
        withacct = [v for v in rows(vl) if v.get("has_active_portal_account")]
        expect(c7 == 200 and vid in vmap and mine.get("has_active_portal_account") is True
               and "dobel input" in (mine.get("warning") or ""), "OV-5",
               "daftar vendor memuat semua vendor aktif + peringatan dobel input",
               "peringatan dobel input tidak terbentuk untuk vendor yang punya akun aktif",
               {"total": len(vmap), "punya_akun": len(withacct),
                "warning": (mine.get("warning") or "")[:90]})

        # ── OV-6..OV-7 — 11 modul jalan + setiap tulisan berstempel ──────────
        read_status = {}
        for name, path in (
            ("dashboard", "/vendor/dashboard"),
            ("penerimaan", "/vendor-shipments"),
            ("inspeksi", "/vendor-material-inspections"),
            ("permintaan", "/material-requests?request_type=ADDITIONAL"),
            ("pekerjaan", "/production-jobs"),
            ("progress", "/production-progress"),
            ("kirim-buyer", "/buyer-shipments"),
            ("serial", f"/serial-trace?serial={MARK}-SN1"),
            ("variance", "/production-variances"),
            ("variance-stats", "/production-variances/stats"),
            ("reminder", "/reminders"),
            ("selisih", "/prod/short-shipments?status=open"),
        ):
            read_status[name] = call("get", path, staff, vendor=vid)[0]
        expect(all(v == 200 for v in read_status.values()), "OV-6",
               "semua modul portal vendor bisa DIBACA staf dalam mode override",
               "ada modul yang tidak bisa dibaca staf dalam mode override", read_status)

        stamps = {}
        # penerimaan
        call("put", f"/vendor-shipments/{ship_id}", staff, vendor=vid,
             body={"status": "Received"})
        sdoc = db.vendor_shipments.find_one({"id": ship_id}, {"_id": 0}) or {}
        stamps["penerimaan"] = sdoc.get("receipt_entered_by_staff") is True \
            and sdoc.get("receipt_on_behalf_of_vendor") == vid
        # inspeksi
        sitems = list(db.vendor_shipment_items.find({"shipment_id": ship_id}, {"_id": 0}))
        c, insp = call("post", "/vendor-material-inspections", staff, vendor=vid, body={
            "shipment_id": ship_id, "overall_notes": MARK,
            "items": [{"shipment_item_id": it["id"], "sku": it.get("sku", ""),
                       "product_name": it.get("product_name", ""),
                       "ordered_qty": it.get("qty_sent", 0),
                       "received_qty": max(0, int(it.get("qty_sent", 0)) - 5),
                       "missing_qty": 5, "condition_notes": MARK} for it in sitems]})
        insp_id = insp.get("id") if isinstance(insp, dict) else None
        idoc = db.vendor_material_inspections.find_one({"id": insp_id}, {"_id": 0}) or {}
        stamps["inspeksi"] = idoc.get("entered_by_staff") is True
        # permintaan material
        c, mr = call("post", "/material-requests", staff, vendor=vid, body={
            "request_type": "ADDITIONAL", "original_shipment_id": ship_id,
            "po_id": po_id, "po_number": po_number, "notes": MARK,
            "items": [{"shipment_item_id": sitems[0]["id"], "sku": sitems[0].get("sku", ""),
                       "requested_qty": 5}]})
        mdoc = db.material_requests.find_one(
            {"id": (mr or {}).get("id")}, {"_id": 0}) or {}
        stamps["permintaan"] = mdoc.get("entered_by_staff") is True
        # pekerjaan produksi
        c, job = call("post", "/production-jobs", staff, vendor=vid,
                      body={"vendor_shipment_id": ship_id, "notes": MARK})
        job_id = job.get("id") if isinstance(job, dict) else None
        jdoc = db.production_jobs.find_one({"id": job_id}, {"_id": 0}) or {}
        stamps["pekerjaan"] = jdoc.get("entered_by_staff") is True and jdoc.get("vendor_id") == vid
        # progress produksi (angka dasar TAGIHAN)
        c, jit = call("get", f"/production-job-items?job_id={job_id}", staff, vendor=vid)
        items = rows(jit)
        prog_id = None
        if items:
            c, pr = call("post", "/production-progress", staff, vendor=vid, body={
                "job_item_id": items[0]["id"], "completed_quantity": 20, "notes": MARK})
            prog_id = (pr or {}).get("id")
        pdoc = db.production_progress.find_one({"id": prog_id}, {"_id": 0}) or {}
        stamps["progress"] = pdoc.get("entered_by_staff") is True \
            and pdoc.get("on_behalf_of_vendor") == vid
        # deklarasi kirim CMT → DA
        c, bs = call("post", "/buyer-shipments", staff, vendor=vid, body={
            "shipment_number": f"{MARK}-SJDA-{uuid.uuid4().hex[:5].upper()}",
            "job_id": job_id, "po_id": po_id, "notes": MARK,
            "items": [{"po_item_id": items[0].get("po_item_id") if items else None,
                       "sku": items[0].get("sku", "") if items else "",
                       "qty_shipped": 20}]})
        bs_id = bs.get("id") if isinstance(bs, dict) else None
        bdoc = db.buyer_shipments.find_one({"id": bs_id}, {"_id": 0}) or {}
        stamps["kirim-buyer"] = bdoc.get("entered_by_staff") is True and bdoc.get("receiver_type") == "da"
        # variance
        c, vr = call("post", "/production-variances", staff, vendor=vid, body={
            "job_id": job_id, "variance_type": "UNDERPRODUCTION", "reason": MARK,
            "items": [{"job_item_id": items[0]["id"] if items else None, "variance_qty": 5}]})
        vdoc = db.production_variances.find_one({"id": (vr or {}).get("id")}, {"_id": 0}) or {}
        stamps["variance"] = vdoc.get("entered_by_staff") is True
        # balasan reminder
        if rem_id:
            call("put", f"/reminders/{rem_id}", staff, vendor=vid,
                 body={"response": f"{MARK} dibalas staf"})
            rdoc = db.reminders.find_one({"id": rem_id}, {"_id": 0}) or {}
            stamps["reminder"] = rdoc.get("response_entered_by_staff") is True \
                and rdoc.get("status") == "responded"

        expect(all(stamps.values()), "OV-7",
               "SEMUA dokumen hasil mode override membawa stempel entered_by_staff + vendor",
               "ada dokumen hasil override TANPA stempel jejak (selisih tagihan tak bisa ditelusuri)",
               stamps)

        # ── OV-8 — scoping baca tidak bocor ─────────────────────────────────
        _, ships = call("get", "/vendor-shipments", staff, vendor=vid)
        _, jobs_l = call("get", "/production-jobs", staff, vendor=vid)
        _, prog_l = call("get", "/production-progress", staff, vendor=vid)
        _, rem_l = call("get", "/reminders", staff, vendor=vid)
        leak = {
            "shipments": [s for s in rows(ships) if s.get("vendor_id") != vid],
            "jobs": [j for j in rows(jobs_l) if j.get("vendor_id") != vid],
            "progress": [p for p in rows(prog_l) if p.get("job_id") != job_id],
            "reminders": [r for r in rows(rem_l) if r.get("vendor_id") != vid],
        }
        expect(all(len(v) == 0 for v in leak.values()), "OV-8",
               "pembacaan mode override HANYA berisi data vendor yang diwakili",
               "data vendor LAIN bocor ke layar override (risiko salah vendor = salah tagihan)",
               {k: len(v) for k, v in leak.items()})

        # ── OV-9 — tulis lintas vendor ditolak ──────────────────────────────
        foreign_item = db.production_job_items.find_one(
            {"job_id": {"$nin": [job_id]}}, {"_id": 0, "id": 1})
        if foreign_item:
            c8, _ = call("post", "/production-progress", staff, vendor=vid,
                         body={"job_item_id": foreign_item["id"], "completed_quantity": 1})
            expect(c8 == 403, "OV-9",
                   "menulis progress ke pekerjaan vendor lain ditolak 403",
                   "BISA menulis progress ke pekerjaan vendor LAIN saat mode override",
                   {"http": c8})
        else:
            ok("OV-9", "tidak ada job vendor lain untuk diuji (dilewati aman)")

        # ── OV-10 — deklarasi CMT→DA: boleh override, tetap tertutup tanpanya ─
        c9, _ = call("post", "/buyer-shipments", staff, body={
            "shipment_number": f"{MARK}-NEG-{uuid.uuid4().hex[:5].upper()}",
            "receiver_type": "da", "vendor_id": vid, "po_id": po_id,
            "items": [{"qty_shipped": 1}]})
        expect(bdoc.get("receiver_type") == "da" and c9 == 403, "OV-10",
               "receiver_type=da boleh lewat mode override, TETAP 403 tanpa mode override",
               "penjaga receiver_type=da tidak lagi menutup jalur tanpa override",
               {"override_ok": bdoc.get("receiver_type"), "tanpa_override": c9})

        # ── OV-11 — panel audit memisahkan staf vs vendor ───────────────────
        c10, aud = call("get", "/cmt-override/audit", staff, vendor=vid)
        mods = {e.get("module") for e in rows(aud)}
        need = {"Penerimaan Material", "Inspeksi Material", "Permintaan Material",
                "Pekerjaan Produksi", "Progress Produksi", "Kirim ke Buyer",
                "Laporan Variance", "Inbox Reminder"}
        expect(c10 == 200 and need.issubset(mods)
               and (aud or {}).get("totals", {}).get("staff", 0) >= 8, "OV-11",
               "panel audit melacak 8 modul penulis + memisahkan staf vs vendor",
               "panel audit tidak melacak semua modul penulis",
               {"kurang": sorted(need - mods), "totals": (aud or {}).get("totals")})

        # ── OV-12 — REGRESI portal vendor asli (2 bug lama tetap tertutup) ──
        if vendor_tok:
            c11, vprog = call("get", "/production-progress", vendor_tok)
            c12, vrem = call("get", "/reminders", vendor_tok)
            c13, vship = call("get", "/vendor-shipments", vendor_tok)
            own_prog = rows(vprog)
            expect(c11 == 200 and len(own_prog) >= 1
                   and all(p.get("job_id") == job_id for p in own_prog)
                   and c12 == 200 and all(r.get("vendor_id") == vid for r in rows(vrem))
                   and c13 == 200 and all(s.get("vendor_id") == vid for s in rows(vship)),
                   "OV-12",
                   "portal vendor asli: riwayat progress TAMPIL & semua daftar ter-scope",
                   "portal vendor asli rusak: riwayat progress kosong atau data vendor lain bocor",
                   {"progress": len(own_prog), "reminder": len(rows(vrem)),
                    "shipment": len(rows(vship))})
        else:
            bad("OV-12", "akun vendor uji tidak bisa login — regresi portal vendor tak teruji")

        # ── OV-13 — bahan badge tersedia di monitoring & invoice ────────────
        c14, trk = call("get", "/production-tracking?business_type=maklon", admin)
        grp = next((g for g in rows(trk) if g.get("vendor_id") == vid), None)
        c15, bill = call("get", "/production/cmt-billing", admin)
        bill_ok = all("progress_entry_source" in r for r in rows(bill))
        expect(c14 == 200 and grp is not None
               and grp.get("progress_entry_source") == "staff"
               and int(grp.get("staff_entered_progress_qty") or 0) == 20
               and c15 == 200 and bill_ok, "OV-13",
               "monitoring & invoice menerima bahan badge 'diinput staf DA'",
               "layar monitoring/invoice tidak tahu angkanya diketik staf (badge mustahil tampil)",
               {"source": (grp or {}).get("progress_entry_source"),
                "qty": (grp or {}).get("staff_entered_progress_qty"),
                "invoice_field": bill_ok})

        # ── OV-16 — F13: SATU MASTER vendor untuk pembayaran CMT ────────────
        # KELAS MASALAH (cacat HIGH FIN-3/CMT-3; nyata di DB sesi ini: irisan id
        # antara `vendor_partners` dan `dewi_cmt_partners` = 0). Satu kolom
        # (`dewi_cmt_payments.cmt_partner_id`) menyimpan id dari DUA master:
        # dokumen lama dari Portal CMT, dokumen baru dari
        # `production_maklon_bridge` (yang menulis id `vendor_partners`).
        # Akibatnya HUTANG JASA JAHIT HILANG DARI LAYAR — pembaca memakai satu
        # ruang-id, dokumennya memakai yang lain, dan yang tampil adalah
        # "outstanding Rp 0" tanpa satu pun error. Uang yang tidak terlihat tidak
        # akan ditagih maupun dibayar.
        #
        # Diuji dengan PELANGGARAN SINTETIS DUA ARAH, karena bug-nya memang dua
        # arah dan menutup satu arah saja akan terasa "sudah beres":
        #   (a) pembayaran gaya-BRIDGE (hanya `vendor_id`) harus terlihat di
        #       halaman vendor Portal CMT yang dibuka dengan id master CMT;
        #   (b) pembayaran gaya-LAMA (hanya `cmt_partner_id`) harus tertangkap
        #       filter layar Invoice yang mengirim id `vendor_partners`.
        # Kalau penerjemah SSOT (`core.cmt_vendor_master`) dilepas suatu hari,
        # salah satu arah langsung merah di sini.
        legacy_cp_id = f"cp-{uuid.uuid4().hex[:12]}"
        pay_bridge_id = f"payb-{uuid.uuid4().hex[:10]}"
        pay_legacy_id = f"payl-{uuid.uuid4().hex[:10]}"
        prev_link = (db.vendor_partners.find_one({"id": vid}, {"_id": 0, "cmt_partner_id": 1})
                     or {}).get("cmt_partner_id")
        try:
            # Master Portal CMT dengan id BERBEDA dari vendor_partners, ditautkan
            # dua arah — persis hasil `scripts/migrate_unify_cmt_vendor_master.py`.
            db.dewi_cmt_partners.insert_one({
                "id": legacy_cp_id, "code": f"{MARK}CPLEG",
                "name": f"{MARK} Mitra CMT Warisan",
                "vendor_partner_id": vid, "is_active": True,
            })
            db.vendor_partners.update_one({"id": vid},
                                          {"$set": {"cmt_partner_id": legacy_cp_id}})
            base_pay = {
                "cmt_name": f"{MARK} Mitra CMT Warisan",
                "vendor_name": f"{MARK} Mitra CMT Warisan",
                "net_amount": 123456.0, "total_amount": 123456.0,
                "status": "draft", "notes": f"{MARK} pelanggaran sintetis F13",
                "created_at": datetime.now(timezone.utc),
            }
            # (a) gaya BRIDGE: hanya id vendor_partners.
            db.dewi_cmt_payments.insert_one({
                **base_pay, "id": pay_bridge_id,
                "payment_code": f"{MARK}-PAYBRIDGE", "vendor_id": vid})
            # (b) gaya LAMA: hanya id master Portal CMT.
            db.dewi_cmt_payments.insert_one({
                **base_pay, "id": pay_legacy_id,
                "payment_code": f"{MARK}-PAYLEGACY", "cmt_partner_id": legacy_cp_id})

            # (a) halaman vendor Portal CMT dibuka dengan id master CMT
            c_v, vdet = call("get", f"/dewi/cmt/lifecycle/{legacy_cp_id}", admin)
            kpis = (vdet or {}).get("kpis") or {}
            billed = float(kpis.get("total_billed") or 0)
            saw_bridge = billed >= 123456.0

            # (b) filter layar Invoice memakai id vendor_partners
            c_f, bill_f = call("get", f"/production/cmt-billing?partner_id={vid}", admin)
            codes_f = {r.get("payment_code") for r in rows(bill_f)}
            saw_legacy = f"{MARK}-PAYLEGACY" in codes_f

            expect(c_v == 200 and saw_bridge and c_f == 200 and saw_legacy, "OV-16",
                   "pembayaran CMT ditemukan dari KEDUA arah id (gaya bridge lewat "
                   "halaman Portal CMT, gaya lama lewat filter layar Invoice) ⇒ satu "
                   "master vendor (SSOT core.cmt_vendor_master) benar-benar dipakai "
                   "semua pembaca",
                   "hutang jasa jahit HILANG dari layar karena pembaca memakai ruang-id "
                   "master yang berbeda dari dokumennya ⇒ 'outstanding Rp 0' padahal "
                   "uangnya ada, dan tidak ada error yang memberi tahu",
                   {"portal_cmt_http": c_v, "total_billed": billed,
                    "ketemu_gaya_bridge": saw_bridge,
                    "invoice_http": c_f, "ketemu_gaya_lama": saw_legacy,
                    "kode_terlihat": sorted(codes_f)[:6]})
        finally:
            # Dibersihkan APA PUN yang terjadi: gate yang meninggalkan pembayaran
            # palsu akan membuat laporan uang salah dan gate berikutnya merah
            # karena ulah gate ini sendiri.
            db.dewi_cmt_payments.delete_many({"id": {"$in": [pay_bridge_id, pay_legacy_id]}})
            db.dewi_cmt_partners.delete_one({"id": legacy_cp_id})
            if prev_link:
                db.vendor_partners.update_one({"id": vid},
                                              {"$set": {"cmt_partner_id": prev_link}})
            else:
                db.vendor_partners.update_one({"id": vid},
                                              {"$unset": {"cmt_partner_id": ""}})

        # ── OV-14 — UANG tidak bergeser ─────────────────────────────────────
        money_after = (call("get", "/production/cmt-billing/summary", admin)[1] or {})\
            .get("total_amount")
        expect(money_before == money_after, "OV-14",
               "total tagihan CMT yang sudah ada TIDAK bergeser karena alur override",
               "total tagihan CMT BERGESER — mode override menyentuh uang yang sudah tercatat",
               {"sebelum": money_before, "sesudah": money_after})

        return 0

    finally:
        if KEEP:
            print(f"\n  {Y}--keep: data uji dibiarkan (bersihkan manual!){X}")
        else:
            stats = {}
            try:
                pos = [p["id"] for p in db.production_pos.find(
                    {"$or": [{"notes": {"$regex": MARK}},
                             {"customer_name": {"$regex": MARK}}]}, {"_id": 0, "id": 1})]
                vids = [v["id"] for v in db.vendor_partners.find(
                    {"name": {"$regex": MARK}}, {"_id": 0, "id": 1})]
                jobs = [j["id"] for j in db.production_jobs.find(
                    {"vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
                ships = [s["id"] for s in db.vendor_shipments.find(
                    {"vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
                insps = [i["id"] for i in db.vendor_material_inspections.find(
                    {"vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
                bss = [b["id"] for b in db.buyer_shipments.find(
                    {"vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
                rcv = [c["id"] for c in db.cmt_receipts.find(
                    {"cmt_vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
                for coll, q in (
                    ("production_progress", {"job_id": {"$in": jobs}}),
                    ("production_job_items", {"job_id": {"$in": jobs}}),
                    ("production_jobs", {"id": {"$in": jobs}}),
                    ("vendor_material_inspection_items", {"inspection_id": {"$in": insps}}),
                    ("vendor_material_inspections", {"id": {"$in": insps}}),
                    ("vendor_shipment_items", {"shipment_id": {"$in": ships}}),
                    ("vendor_shipments", {"id": {"$in": ships}}),
                    ("material_requests", {"vendor_id": {"$in": vids}}),
                    ("production_variances", {"vendor_id": {"$in": vids}}),
                    ("reminders", {"vendor_id": {"$in": vids}}),
                    ("dewi_cmt_component_requests", {"vendor_id": {"$in": vids}}),
                    ("buyer_shipment_items", {"shipment_id": {"$in": bss}}),
                    ("buyer_shipments", {"id": {"$in": bss}}),
                    ("cmt_receipt_lines", {"receipt_id": {"$in": rcv}}),
                    ("cmt_receipts", {"id": {"$in": rcv}}),
                    ("dewi_cmt_payments", {"vendor_id": {"$in": vids}}),
                    ("po_accessories", {"po_id": {"$in": pos}}),
                    ("po_items", {"po_id": {"$in": pos}}),
                    ("dewi_maklon_bom", {"po_id": {"$in": pos}}),
                    # UANG: mirror PO maklon + AR invoice turunannya
                    ("rahaza_ar_invoices", {"linked_maklon_po_id": {"$in": pos}}),
                    ("dewi_maklon_pos", {"production_po_id": {"$in": pos}}),
                    ("production_pos", {"id": {"$in": pos}}),
                    ("users", {"id": {"$in": created_users}}),
                    ("vendor_partners", {"id": {"$in": vids}}),
                ):
                    n = db[coll].delete_many(q).deleted_count
                    if n:
                        stats[coll] = n
                # SWEEP TOTAL — daftar di atas ditulis tangan; efek samping baru di
                # backend akan lolos darinya tanpa ada yang tahu. Riwayat repo ini:
                # alat uji pernah meninggalkan jurnal GL & piutang palsu.
                swept = {}
                for coll in db.list_collection_names():
                    if coll in ("rate_limit_buckets", "counters"):
                        continue
                    dead = [d["_id"] for d in db[coll].find({}).limit(20000)
                            if MARK in json.dumps(d, default=str)]
                    if dead:
                        db[coll].delete_many({"_id": {"$in": dead}})
                        swept[coll] = len(dead)
                if swept:
                    stats["_sweep"] = swept
                rest = {}
                for coll in db.list_collection_names():
                    if coll in ("rate_limit_buckets", "counters"):
                        continue
                    k = sum(1 for d in db[coll].find({}).limit(20000)
                            if MARK in json.dumps(d, default=str))
                    if k:
                        rest[coll] = k
                print(f"\n{Y}bersih-bersih:{X} {json.dumps(stats, default=str)}")
                expect(not rest, "OV-15",
                       "alat uji ini tidak meninggalkan satu pun dokumen di database",
                       "alat uji meninggalkan data (drift) — laporan bisa memuat angka palsu",
                       rest)
            except Exception as e:  # noqa: BLE001
                print(f"{R}cleanup gagal: {e}{X}")

        print(f"\n{B}{'-' * 78}{X}")
        print(f"  PASS {len(PASSES)} · FAIL {len(FAILS)}")
        if FAILS:
            print(f"  {R}MERAH — pelanggaran: {', '.join(sorted(set(FAILS)))}{X}")
        else:
            print(f"  {G}HIJAU — Portal CMT Override aman (kewenangan · scoping · jejak · UANG){X}")


if __name__ == "__main__":
    rc = 0
    try:
        rc = main() or 0
    except KeyboardInterrupt:
        rc = 130
    sys.exit(1 if (rc or FAILS) else 0)
