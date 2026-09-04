#!/usr/bin/env python3
"""
verify_produksi_maklon_invariants.py — GUARDRAIL alur PRODUKSI/MAKLON/CMT.

Menjaga invarian yang cacatnya dibuktikan pada audit 2026-07-31
(docs/AUDIT_PRODUKSI_MAKLON_CMT.md). Menjalankan ALUR NYATA lewat HTTP lalu
membandingkan ANGKA — bukan cek HTTP 200.

Invarian yang dijaga:
  INV-1  produced_qty vendor TIDAK berkurang karena reject DA          (100 tetap 100)
  INV-2  job item punya buku kuantitas: accepted + reject + rework     (INV-2 lama: tak ada field)
  INV-3  ringkasan kuantitas PO memuat accepted/reject/rework/scrap
  INV-4  stok FG bertambah TEPAT sebesar qty lolos QC, dan barisnya
         punya `location_id` kanonik (masuk SSOT stok, bukan stok hantu)
  INV-5  qty reject MASUK KARANTINA (tidak hilang)
  INV-6  permak_sendiri selesai → stok FG naik + accepted naik + rework_open turun
  INV-7  retur_ke_cmt → terbentuk SJ REWORK ke vendor & permak terlihat oleh vendor
  INV-8  AP vendor CMT = qty lolos × rate, mencatat total_rejected
  INV-9  penerimaan hanya punya 2 status kanonik: on_qc / completed_qc
  INV-10 endpoint antrean reject melaporkan sisa reject yang belum diputuskan
  INV-11 surat jalan buyer GABUNGAN lintas-PO bisa dibaca ulang (rincian per PO)
  INV-12 inspeksi qty KURANG → permintaan komponen otomatis
  INV-13 tidak ada referensi vendor YATIM
  INV-14 buku kuantitas KONSISTEN dengan dokumen sumber
  INV-15 tidak ada Surat Jalan REWORK yatim
  INV-16 klaim vendor = qty yang SAMPAI + selisih terdokumentasi (SELISIH KIRIM)
  INV-17 tidak ada selisih kirim tanpa dokumen penyelesaian (kewajiban tak hilang)
  INV-18 setiap dispatch ke buyer MENGURANGI stok FG (mutasi OUT tercatat)

Pakai:  python3 scripts/verify_produksi_maklon_invariants.py
Keluar: rc=0 semua invarian aman, rc=1 ada pelanggaran. Data uji dibersihkan
        di `finally` LANGSUNG ke Mongo (marker `__INVTEST__`).
"""
from __future__ import annotations
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("API_BASE", "http://localhost:8001")
MARK = "__INVTEST__"
# FASE G (2026-08-16): nomor PO uji WAJIB mengikuti pola resmi jenis dokumennya.
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from gr_common import test_doc_number  # noqa: E402
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

FAILS: list[str] = []
PASSES: list[str] = []
CREATED: dict[str, list] = {}
_tokens: dict = {}


def track(coll, _id):
    if _id:
        CREATED.setdefault(coll, []).append(_id)


# ─────────────────────────────────────────────────────────────────────────────
# PEMBACA STOK — HARUS SAMA DENGAN APLIKASI (anti false-negative)
# ─────────────────────────────────────────────────────────────────────────────
def _read_qty(row) -> float:
    """Jumlah fisik on-hand memakai pembaca RESMI `core.stock_schema.read_qty`.

    `rahaza_material_stock` ditulis 3 skema berbeda (qty / total_qty / quantity),
    itu sebabnya pembaca berantai ini ada. Membaca `row["qty"]` mentah membuat
    pemeriksaan bisa melaporkan 0 untuk baris yang sebenarnya berisi.
    """
    try:
        sys.path.insert(0, str(ROOT / "backend"))
        from core.stock_schema import read_qty
        return float(read_qty(row))
    except Exception:  # noqa: BLE001 — fallback setara bila import gagal
        for k in ("qty", "total_qty", "quantity", "available_quantity"):
            if (row or {}).get(k) is not None:
                try:
                    return float(row[k] or 0)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0


def _quarantine_location_id(db):
    """Lokasi karantina SEPERTI YANG DIPAKAI APLIKASI.

    `core.quarantine.get_quarantine_location_id()` LEBIH DULU memakai zona
    kanonik `wh_zones` (peran 'karantina') dan baru jatuh ke `rahaza_locations`
    kode ZNA-KARANTINA. Menebak langsung ke `rahaza_locations` membuat
    pemeriksaan membaca lokasi yang SALAH begitu struktur kanonik dibuat.
    """
    for e in (db.wh_location_migration_map.find({}, {"_id": 0})
              if "wh_location_migration_map" in db.list_collection_names() else []):
        if (e.get("role") or "").lower() == "karantina" and e.get("wh_zone_id"):
            z = db.wh_zones.find_one({"id": e["wh_zone_id"], "active": True}, {"_id": 0, "id": 1})
            if z:
                return z["id"]
    if "wh_zones" in db.list_collection_names():
        z = db.wh_zones.find_one({"code": "ZNA-KARANTINA", "active": True}, {"_id": 0, "id": 1})
        if z:
            return z["id"]
    return (db.rahaza_locations.find_one({"code": "ZNA-KARANTINA"},
                                         {"_id": 0, "id": 1}) or {}).get("id")


def login(email, pwd):
    if email in _tokens:
        return _tokens[email]
    for _ in range(6):
        r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, timeout=25)
        if r.status_code == 200:
            _tokens[email] = r.json().get("token", "")
            return _tokens[email]
        if r.status_code == 429:
            time.sleep(12)
            continue
        return None
    return None


def call(method, path, tok, **kw):
    try:
        r = requests.request(method, f"{BASE}{path}",
                             headers={"Authorization": f"Bearer {tok}",
                                      "Content-Type": "application/json"}, timeout=90, **kw)
    except Exception as e:
        return 0, str(e)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text[:400]


def db_handle():
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


def ok(code, msg, ev=None):
    PASSES.append(code)
    print(f"  {G}[OK]{X} {code} — {msg}" + (f" · {json.dumps(ev, default=str)[:200]}" if ev else ""))


def bad(code, msg, ev=None):
    FAILS.append(code)
    print(f"  {R}[FAIL]{X} {code} — {msg}")
    if ev is not None:
        print(f"         bukti: {json.dumps(ev, default=str)[:400]}")


def run_db_audits():
    """AUDIT DB murni (INV-13..INV-18) — tidak membuat data uji.

    Dipisahkan supaya bisa dijalankan atas data NYATA milik owner:
        python3 scripts/verify_produksi_maklon_invariants.py --audit-only
    """
    # ── INV-13: TIDAK ADA referensi vendor YATIM (audit relasi data) ──────
    # Cacat nyata 2026-07-31: satu seeder memaku `vendor_id="demo-vn-jmc"`
    # sementara master JMC yang sah ber-id `mk-vendor-demo-1` (diadopsi karena
    # unique index `code`). Semua endpoint tetap 200, tapi job/tagihan itu tak
    # pernah terlihat di Portal Vendor CMT. Gerbang ini menahan pola tsb.
    dbi = db_handle()
    valid = {v["id"] for v in dbi.vendor_partners.find({}, {"_id": 0, "id": 1}) if v.get("id")}
    valid |= {v["id"] for v in dbi.dewi_cmt_partners.find({}, {"_id": 0, "id": 1}) if v.get("id")}
    orphan_map = {}
    for coll, field in (("production_pos", "vendor_id"), ("po_items", "vendor_id"),
                        ("production_jobs", "vendor_id"), ("vendor_shipments", "vendor_id"),
                        ("buyer_shipments", "vendor_id"), ("cmt_receipts", "cmt_vendor_id"),
                        ("dewi_cmt_permak", "vendor_id"), ("dewi_cmt_payments", "vendor_id"),
                        ("dewi_cmt_component_requests", "vendor_id"), ("dewi_cmt_jobs", "vendor_id")):
        bad_ids = sorted({
            r[field] for r in dbi[coll].find({field: {"$nin": [None, ""]}}, {"_id": 0, field: 1})
            if r.get(field) not in valid
        })
        if bad_ids:
            orphan_map[coll] = bad_ids[:5]
    if orphan_map:
        bad("INV-13", "ada referensi vendor YATIM (tidak ada di master vendor) — "
                      "jalankan scripts/repair_orphan_vendor_refs.py", orphan_map)
    else:
        ok("INV-13", "semua referensi vendor menunjuk master yang sah (0 yatim)",
           {"master_vendor": len(valid)})

    # ── INV-14: buku kuantitas KONSISTEN dengan dokumen sumber ────────────
    # Ledger ditulis inkremental (`$inc`). Kalau ada penerimaan/permak yang
    # dihapus atau diterapkan dua kali, angkanya menggantung dan UI bisa
    # menampilkan yang mustahil (accepted 190 > produced 145 — kejadian nyata
    # 2026-07-31). Gerbang ini membandingkannya dengan sumber.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from recompute_qty_ledger import audit_ledger  # noqa: E402
        findings = audit_ledger(dbi, apply=False, verbose=False)
        impossible = [
            {"sku": ji.get("sku"), "produced": ji.get("produced_qty"),
             "accepted": ji.get("qty_accepted")}
            for ji in dbi.production_job_items.find(
                {}, {"_id": 0, "sku": 1, "produced_qty": 1, "qty_accepted": 1})
            if float(ji.get("qty_accepted") or 0) > float(ji.get("produced_qty") or 0) > 0
        ]
        if findings or impossible:
            bad("INV-14", "buku kuantitas tidak konsisten dengan dokumen sumber — "
                          "jalankan scripts/recompute_qty_ledger.py",
                {"selisih": findings[:3], "accepted_melebihi_produced": impossible[:3]})
        else:
            ok("INV-14", "buku kuantitas job item konsisten dengan penerimaan + permak "
                         "(dan accepted tidak pernah melebihi produced)",
               {"job_item": dbi.production_job_items.count_documents({})})
    except Exception as e:  # noqa: BLE001
        bad("INV-14", f"audit buku kuantitas gagal dijalankan: {e}")

    # ── INV-15: TIDAK ADA Surat Jalan REWORK yatim ────────────────────────
    # Cacat nyata: permak dihapus (mis. pembersihan data demo) tapi SJ REWORK
    # tetap tinggal → Portal Vendor menampilkan surat jalan rework tanpa
    # pekerjaan yang menaunginya; vendor mengerjakan barang yang tak tercatat.
    valid_permak = {p["id"] for p in dbi.dewi_cmt_permak.find({}, {"_id": 0, "id": 1})}
    rwk_orphan = [s.get("shipment_number") for s in dbi.vendor_shipments.find(
        {"shipment_type": "REWORK"}, {"_id": 0, "shipment_number": 1, "rework_permak_id": 1})
        if s.get("rework_permak_id") and s["rework_permak_id"] not in valid_permak]
    if rwk_orphan:
        bad("INV-15", "ada Surat Jalan REWORK tanpa dokumen permak (yatim)",
            {"shipment": rwk_orphan[:5]})
    else:
        ok("INV-15", "semua Surat Jalan REWORK menunjuk permak yang ada",
           {"sj_rework": dbi.vendor_shipments.count_documents({"shipment_type": "REWORK"})})

    # ── INV-16: KLAIM VENDOR = SAMPAI + SELISIH (buku selisih kirim seimbang) ──
    # Aturan owner 2026-08-01: dokumen penerimaan berisi qty yang BENAR-BENAR
    # sampai; klaim vendor disimpan terpisah dan kekurangannya WAJIB punya
    # dokumen selisih. Gerbang ini menahan angka menggantung
    # ("declared 100" padahal hanya 90 yang sampai) yang dulu tak terlihat.
    from core.cmt_receipt_status import is_done as _is_done16
    done_ids16 = {r["id"] for r in dbi.cmt_receipts.find({}, {"_id": 0, "id": 1, "status": 1})
                  if _is_done16(r.get("status"))}
    lines16 = list(dbi.cmt_receipt_lines.find(
        {"receipt_id": {"$in": list(done_ids16)}}, {"_id": 0})) if done_ids16 else []
    shorts16: dict = {}
    for s in dbi.cmt_short_shipments.find({}, {"_id": 0}):
        shorts16.setdefault(s.get("receipt_line_id"), []).append(s)

    def _n16(v):
        try:
            return int(float(v or 0))
        except (TypeError, ValueError):
            return 0

    bad16, bad17 = [], []
    for ln in lines16:
        arrived = _n16(ln.get("qty_actual")) + _n16(ln.get("reject_qty"))
        claimed = _n16(ln.get("qty_claimed_by_cmt")) or _n16(ln.get("qty_shipped_by_cmt")) or arrived
        docs = shorts16.get(ln["id"], [])
        s_open = sum(max(0, _n16(s.get("qty_short")) - _n16(s.get("qty_resolved")))
                     for s in docs if s.get("status") == "open")
        s_res = sum(_n16(s.get("qty_resolved")) for s in docs if s.get("status") != "cancelled")
        # dokumen DIBATALKAN = klaim ternyata salah tulis lalu dikoreksi, jadi
        # gap-nya memang tidak ada lagi → tidak ikut dihitung.
        if claimed != arrived + s_open + s_res:
            bad16.append({"sku": ln.get("sku_code"), "claimed": claimed, "arrived": arrived,
                          "short_open": s_open, "short_resolved": s_res})
        if claimed > arrived and not [d for d in docs if d.get("status") != "cancelled"]:
            bad17.append({"sku": ln.get("sku_code"), "claimed": claimed, "arrived": arrived,
                          "receipt_line_id": ln["id"]})
    if bad16:
        bad("INV-16", "klaim vendor ≠ (yang sampai + selisih terdokumentasi) — "
                      "jalankan scripts/repair_selisih_ssot.py --apply", {"contoh": bad16[:3]})
    else:
        ok("INV-16", "klaim vendor = yang sampai + selisih terdokumentasi (buku selisih seimbang)",
           {"baris_selesai_qc": len(lines16)})

    # ── INV-17: TIDAK ADA selisih kirim TANPA dokumen penyelesaian ────────
    if bad17:
        bad("INV-17", "ada baris penerimaan SELESAI QC dengan klaim > yang sampai TANPA "
                      "dokumen selisih (kewajiban vendor hilang dari layar)",
            {"contoh": bad17[:3]})
    else:
        ok("INV-17", "setiap selisih kirim punya dokumen (open/resolved) — tidak ada "
                     "kewajiban vendor yang menggantung",
           {"dokumen_selisih": dbi.cmt_short_shipments.count_documents({})})

    # ── INV-18: STOK FG KELUAR untuk SETIAP dispatch ke buyer (GAP E) ─────
    # Bug nyata: kirim 100 pcs ke buyer, stok FG tetap 100 (tidak ada
    # `stock_service.issue`) → nilai persediaan menggelembung selamanya.
    da_ids18 = set(dbi.buyer_shipments.distinct("id", {"receiver_type": "da"}))
    ships18 = {s["id"]: s for s in dbi.buyer_shipments.find(
        {"id": {"$nin": list(da_ids18)}}, {"_id": 0, "id": 1, "shipment_number": 1})}
    fg_codes = {(m.get("code") or "").strip().lower() for m in
                dbi.rahaza_materials.find({"type": "fg"}, {"_id": 0, "code": 1})}
    missing18 = []
    for it in dbi.buyer_shipment_items.find(
            {"shipment_id": {"$in": list(ships18.keys())}}, {"_id": 0}):
        if _n16(it.get("qty_shipped")) <= 0 or it.get("fg_issued_at"):
            continue
        sku = (it.get("sku") or "").strip()
        if not sku or sku.lower() not in fg_codes:
            continue          # barang lama tanpa master FG: tidak ada stok utk dikurangi
        missing18.append({"sj": (ships18.get(it["shipment_id"]) or {}).get("shipment_number"),
                          "sku": sku, "qty": _n16(it.get("qty_shipped"))})
    if missing18:
        bad("INV-18", "ada dispatch ke buyer TANPA mutasi stok FG keluar — "
                      "jalankan scripts/repair_selisih_ssot.py --apply",
            {"contoh": missing18[:3], "total": len(missing18)})
    else:
        ok("INV-18", "setiap dispatch ke buyer sudah mengurangi stok FG (mutasi OUT tercatat)",
           {"dispatch_diperiksa": dbi.buyer_shipment_items.count_documents(
               {"shipment_id": {"$in": list(ships18.keys())}})})


def main():
    print(f"{B}{C}{'=' * 92}\n  GUARDRAIL — INVARIAN ALUR PRODUKSI · MAKLON · CMT\n{'=' * 92}{X}")
    adm = login("admin@garment.com", "Admin@123")
    if not adm:
        print(f"{R}login admin gagal — abort{X}")
        return 2
    ven = login("cmtvendor@dewiaditya.id", "Dewi@123")
    db = db_handle()

    try:
        # ── siapkan PO maklon lewat engine ──
        st, cats = call("GET", "/api/dewi/maklon/buyer-catalog", adm)
        clist = cats if isinstance(cats, list) else cats.get("items", [])
        cat = next((c for c in clist if (c.get("variants") or [])), None)
        st, clients = call("GET", "/api/dewi/maklon/clients?status=active", adm)
        client = (clients if isinstance(clients, list) else [None])[0] if clients else None
        if not cat or not client:
            # DB tanpa data master maklon (mis. container segar / sebelum restore
            # backup owner): skenario HTTP tidak bisa dijalankan. Itu BUKAN
            # pelanggaran invarian — audit DB (INV-13..18) tetap dijalankan supaya
            # gerbang ini tetap berguna dan tidak MERAH palsu.
            print(f"  {Y}[SKIP]{X} SETUP — data master maklon belum ada "
                  f"(buyer catalog bervarian / klien aktif). Skenario HTTP dilewati; "
                  f"audit DB tetap dijalankan.")
            run_db_audits()
            print(f"\n{B}{'-' * 92}{X}")
            print(f"  PASS {len(PASSES)} · FAIL {len(FAILS)} (skenario HTTP: SKIP)")
            if FAILS:
                print(f"  {R}{B}MERAH — pelanggaran: {', '.join(FAILS)}{X}")
                return 1
            print(f"  {G}{B}HIJAU — audit data bersih (skenario HTTP dilewati: data master belum ada){X}")
            return 0
        v0 = cat["variants"][0]
        # SESI #38 — id vendor DICARI lewat KODE, tidak dipaku. Justru pelajaran
        # INV-13 sendiri: `_upsert` di `routes/maklon_seed.py` mengadopsi master
        # JMC yang sudah ada (id `demo-vn-jmc`) sehingga `mk-vendor-demo-1` tidak
        # pernah lahir ⇒ surat jalan uji dibuat TANPA baris dan gate ini pecah
        # (IndexError), bukan melaporkan pelanggaran.
        vend = (db.vendor_partners.find_one({"code": "JMC"}, {"_id": 0, "id": 1})
                or db.vendor_partners.find_one({"active": {"$ne": False}}, {"_id": 0, "id": 1}))
        if not vend:
            bad("SETUP", "tidak ada master vendor CMT untuk uji", {})
            return 1
        vendor_id = vend["id"]
        rate = float(cat.get("default_cmt_price") or 10000)
        # FASE G (2026-08-16): nomor manual wajib mengikuti pola resmi PO maklon.
        po_number = test_doc_number("production_pos.po_number_maklon", adm)
        st, po = call("POST", "/api/production-pos", adm, json={
            "po_number": po_number, "business_type": "maklon", "buyer_id": client["id"],
            "vendor_id": vendor_id, "status": "Confirmed", "notes": MARK,
            "po_date": date.today().isoformat(), "deadline": date.today().isoformat(),
            "items": [{"catalog_item_id": cat["id"], "maklon_variant_id": v0.get("id"),
                       "sku": v0.get("sku"), "color": v0.get("color"), "size": v0.get("size"),
                       "product_name": cat.get("product_name"), "qty": 100,
                       "cmt_price_snapshot": rate, "serial_number": "INV-S01"}]})
        if st not in (200, 201):
            bad("SETUP", "gagal buat PO", {"http": st, "resp": po})
            return 1
        po_id = po.get("id")
        track("production_pos", po_id)
        po_items = list(db.po_items.find({"po_id": po_id}, {"_id": 0}))
        for i in po_items:
            track("po_items", i["id"])
        poi = po_items[0]

        # SJ material ke CMT + inspeksi + job
        sj = f"INV-SJ-{int(time.time())}"
        st, vs = call("POST", "/api/vendor-shipments", adm, json={
            "vendor_id": vendor_id, "shipment_number": sj, "po_id": po_id, "notes": MARK,
            "shipment_date": date.today().isoformat(), "shipment_type": "NORMAL",
            "items": [{"po_id": po_id, "po_item_id": poi["id"], "sku": poi.get("sku"), "qty_sent": 100}]})
        vs_id = vs.get("id")
        track("vendor_shipments", vs_id)
        vsi = list(db.vendor_shipment_items.find({"shipment_id": vs_id}, {"_id": 0}))
        for x in vsi:
            track("vendor_shipment_items", x["id"])
        call("PUT", f"/api/vendor-shipments/{vs_id}", ven or adm, json={"status": "Received"})
        st, insp = call("POST", "/api/vendor-material-inspections", ven or adm, json={
            "shipment_id": vs_id, "overall_notes": MARK,
            "items": [{"shipment_item_id": vsi[0]["id"], "sku": vsi[0].get("sku"),
                       "ordered_qty": 100, "received_qty": 100, "missing_qty": 0}]})
        track("vendor_material_inspections", (insp or {}).get("id"))
        for x in db.vendor_material_inspection_items.find({"inspection_id": (insp or {}).get("id")}, {"_id": 0}):
            track("vendor_material_inspection_items", x["id"])
        st, job = call("POST", "/api/production-jobs", adm,
                       json={"vendor_shipment_id": vs_id, "vendor_id": vendor_id,
                             "po_id": po_id, "notes": MARK})
        if st not in (200, 201):
            bad("SETUP", "gagal buat job", {"http": st, "resp": job})
            return 1
        job_id = job["id"]
        track("production_jobs", job_id)
        jrows = list(db.production_job_items.find({"job_id": job_id}, {"_id": 0}))
        for x in jrows:
            track("production_job_items", x["id"])
        ji = jrows[0]

        # progress vendor 100
        st, pr = call("POST", "/api/production-progress", ven or adm, json={
            "job_item_id": ji["id"], "completed_quantity": 100,
            "progress_date": date.today().isoformat(), "notes": MARK})
        track("production_progress", (pr or {}).get("id"))

        # deklarasi kirim CMT → DA
        st, decl = call("POST", "/api/buyer-shipments", ven or adm, json={
            "po_id": po_id, "job_id": job_id, "notes": MARK,
            "shipment_date": date.today().isoformat(),
            "items": [{"po_item_id": poi["id"], "job_item_id": ji["id"],
                       "sku": ji.get("sku"), "qty_shipped": 100}]})
        decl_id = (decl or {}).get("id")
        track("buyer_shipments", decl_id)
        for x in db.buyer_shipment_items.find({"shipment_id": decl_id}, {"_id": 0}):
            track("buyer_shipment_items", x["id"])
        time.sleep(1)
        rcpt = db.cmt_receipts.find_one({"related_shipment_id": decl_id}, {"_id": 0})
        if not rcpt:
            bad("SETUP", "draft penerimaan tidak terbentuk otomatis")
            return 1
        rid = rcpt["id"]
        track("cmt_receipts", rid)

        # ── INV-9: status kanonik ──
        st, rlist = call("GET", f"/api/prod/cmt-receipts?po_id={po_id}", adm)
        row = next((r for r in (rlist if isinstance(rlist, list) else []) if r.get("id") == rid), None)
        if row and row.get("status") == "on_qc" and row.get("status_label"):
            ok("INV-9", "penerimaan berstatus kanonik on_qc", {"status": row["status"],
                                                               "label": row["status_label"],
                                                               "baris_ikut_di_daftar": len(row.get("lines") or [])})
        else:
            bad("INV-9", "status penerimaan bukan kanonik on_qc", row)

        lines = list(db.cmt_receipt_lines.find({"receipt_id": rid}, {"_id": 0}))
        for x in lines:
            track("cmt_receipt_lines", x["id"])
        line = lines[0]

        # stok FG sebelum (HANYA lokasi gudang FG — karantina dihitung terpisah)
        # 2026-08-07 — DUA sumber salah-baca yang pernah membuat gate ini MERAH
        # tanpa ada kerusakan produk (false negative, mahal karena menyesatkan
        # agent berikutnya):
        #   1. lokasi karantina DITEBAK dari `rahaza_locations.code = ZNA-KARANTINA`,
        #      padahal aplikasi memakai `core.quarantine.get_quarantine_location_id()`
        #      yang LEBIH DULU mencari zona kanonik `wh_zones` (peran 'karantina').
        #      Begitu struktur kanonik ada, stok karantina ditulis ke id LAIN dan
        #      pemeriksaan ini membaca 0 — lalu melaporkan "stok FG salah";
        #   2. jumlah dibaca dari field `qty` MENTAH, padahal koleksi ini ditulis
        #      3 skema berbeda (lihat core/stock_schema.py) dan pembaca resminya
        #      adalah `read_qty()`.
        # Keduanya sekarang memakai jalur yang SAMA dengan aplikasi.
        fg_loc = (db.rahaza_locations.find_one({"code": "ZNA-FG"}, {"_id": 0, "id": 1}) or {}).get("id")
        q_loc = _quarantine_location_id(db)
        fg_mat = db.rahaza_materials.find_one({"type": "fg", "code": ji.get("sku")}, {"_id": 0})
        fg_before = 0.0
        if fg_mat:
            rowx = db.rahaza_material_stock.find_one(
                {"material_id": fg_mat["id"], "location_id": fg_loc}, {"_id": 0})
            fg_before = _read_qty(rowx)
        q_before = db.wh_quarantine_items.count_documents({}) if "wh_quarantine_items" in db.list_collection_names() else 0

        # ── QC: 100 dikirim, 90 lolos, 10 reject ──
        call("PUT", f"/api/prod/cmt-receipts/{rid}/lines/{line['id']}", adm,
             json={"qty_actual": 90, "reject_qty": 10, "reject_reason": "jahitan lepas"})
        st, done = call("POST", f"/api/prod/cmt-receipts/{rid}/complete-qc", adm)
        if st != 200:
            bad("SETUP", "complete-qc gagal", {"http": st, "resp": done})
            return 1
        if done.get("status") == "completed_qc":
            ok("INV-9b", "selesai QC satu aksi (complete-qc)", {"status": done["status"]})
        else:
            bad("INV-9b", "status setelah complete-qc salah", done.get("status"))

        # ── INV-1 & INV-2 ──
        ji_after = db.production_job_items.find_one({"id": ji["id"]}, {"_id": 0}) or {}
        if int(ji_after.get("produced_qty") or 0) == 100:
            ok("INV-1", "produced vendor tetap 100 setelah reject 10")
        else:
            bad("INV-1", "produced vendor berubah", {"produced_qty": ji_after.get("produced_qty")})
        led = {k: int(ji_after.get(k) or 0) for k in
               ("qty_declared", "qty_accepted", "qty_reject", "qty_rework_open",
                "qty_repaired", "qty_scrap")}
        if led["qty_accepted"] == 90 and led["qty_reject"] == 10 and led["qty_rework_open"] == 10:
            ok("INV-2", "buku kuantitas job item benar", led)
        else:
            bad("INV-2", "buku kuantitas job item salah", led)

        # ── INV-3 ──
        st, qs = call("GET", f"/api/production-pos/{po_id}/quantity-summary", adm)
        tot = (qs or {}).get("totals", {}) if isinstance(qs, dict) else {}
        if tot.get("accepted") == 90 and tot.get("reject") == 10 and "reject_open" in tot:
            ok("INV-3", "ringkasan kuantitas PO memuat QC", {k: tot.get(k) for k in
                                                             ("produced", "accepted", "reject", "reject_open", "scrap")})
        else:
            bad("INV-3", "ringkasan kuantitas PO tidak memuat QC yang benar", tot)

        # ── INV-4: stok FG lokasi gudang FG += 90 (reject 10 ada di karantina) ──
        #
        # 2026-08-07 — PENJAGA INI SENDIRI YANG BUG (bukan produknya).
        # `q_loc` diambil SEBELUM QC dijalankan, padahal
        # `core.quarantine.get_quarantine_location_id()` MENG-AUTO-PROVISION lokasi
        # karantina saat pertama kali dipakai. Pada database yang BARU di-bootstrap
        # lokasi itu belum ada ⇒ `q_loc = None` ⇒ 10 pcs reject terbaca sebagai
        # "stok di lokasi lain" ⇒ INV-4 MERAH, padahal produknya benar
        # (INV-5 "10 pcs reject masuk karantina" lulus di run yang sama).
        # Akibatnya gate HIJAU tidak pernah reproducible dari bootstrap bersih —
        # justru kondisi yang dihadapi setiap sesi/agen baru.
        # Sekarang lokasi karantina di-resolve ULANG di sini, SETELAH aplikasi
        # berkesempatan membuatnya.
        q_loc = _quarantine_location_id(db) or q_loc
        fg_mat = fg_mat or db.rahaza_materials.find_one({"type": "fg", "code": ji.get("sku")}, {"_id": 0})
        fg_after, q_stock, no_loc = 0.0, 0.0, 0
        # Setiap lokasi LAIN yang memegang stok material ini dicatat. Dulu baris
        # seperti ini dilewati tanpa jejak, sehingga stok yang "nyasar" ke lokasi
        # tak terduga tampil sebagai `stok_karantina: 0` — pesan gagal yang
        # menyembunyikan penyebabnya dan memakan waktu sesi berikutnya.
        elsewhere: dict = {}
        for rowx in db.rahaza_material_stock.find({"material_id": (fg_mat or {}).get("id")}, {"_id": 0}):
            qv = _read_qty(rowx)
            if not rowx.get("location_id"):
                no_loc += 1
            elif rowx.get("location_id") == fg_loc:
                fg_after += qv
            elif rowx.get("location_id") == q_loc:
                q_stock += qv
            elif qv:
                elsewhere[str(rowx.get("location_id"))] = qv
            track("rahaza_material_stock", rowx.get("id"))
        delta = fg_after - fg_before
        if abs(delta - 90) < 0.001 and no_loc == 0 and q_stock >= 10:
            ok("INV-4", "stok FG gudang +90 & reject 10 tercatat di karantina (semua punya location_id)",
               {"delta_fg": delta, "stok_karantina": q_stock, "baris_tanpa_location_id": no_loc})
        else:
            bad("INV-4", "stok FG salah / di luar SSOT stok",
                {"delta_fg": delta, "stok_karantina": q_stock,
                 "baris_tanpa_location_id": no_loc,
                 "lokasi_karantina_yang_diperiksa": q_loc,
                 "lokasi_fg_yang_diperiksa": fg_loc,
                 # Kalau stok karantina 0 tetapi ada isi di sini, artinya lokasi
                 # karantina yang dipakai aplikasi BUKAN yang diperiksa.
                 "stok_di_lokasi_lain": elsewhere})

        # ── INV-5: reject masuk karantina ──
        q_items = list(db.wh_quarantine_items.find(
            {"source.receipt_id": rid}, {"_id": 0})) if "wh_quarantine_items" in db.list_collection_names() else []
        for x in q_items:
            track("wh_quarantine_items", x["id"])
        if q_items and int(q_items[0].get("qty") or 0) == 10:
            ok("INV-5", "10 pcs reject masuk karantina",
               {"qty": q_items[0]["qty"], "material": q_items[0].get("material_code")})
        else:
            bad("INV-5", "reject TIDAK masuk karantina",
                {"karantina_sebelum": q_before, "ditemukan": len(q_items)})

        # ── INV-8: AP CMT ──
        ap = db.dewi_cmt_payments.find_one({"source_receipt_id": rid}, {"_id": 0})
        track("dewi_cmt_payments", (ap or {}).get("id"))
        if ap and int(ap.get("total_pcs") or 0) == 90 and int(ap.get("total_rejected") or 0) == 10 \
                and abs(float(ap.get("net_amount") or 0) - 90 * rate) < 1:
            ok("INV-8", "AP CMT = 90 × rate, reject tercatat",
               {"total_pcs": ap["total_pcs"], "reject": ap["total_rejected"], "net": ap["net_amount"]})
        else:
            bad("INV-8", "AP CMT salah", ap and {k: ap.get(k) for k in
                                                 ("total_pcs", "total_rejected", "net_amount")})

        # ── INV-10: antrean reject ──
        st, rq = call("GET", "/api/prod/cmt-reject-queue", adm)
        rows = (rq or {}).get("items", []) if isinstance(rq, dict) else []
        mine = [r for r in rows if r.get("receipt_id") == rid]
        if mine and mine[0]["qty_undecided"] == 10:
            ok("INV-10", "antrean reject melaporkan 10 pcs belum diputuskan", mine[0])
        else:
            bad("INV-10", "antrean reject tidak melaporkan reject ini",
                {"total_baris": len(rows)})

        # ── INV-6: permak sendiri 6 pcs → stok +6, accepted 96 ──
        st, pk = call("POST", "/api/dewi/cmt-permak/from-receipt-line", adm, json={
            "receipt_line_id": line["id"], "qty": 6, "permak_type": "permak_sendiri",
            "reason": "jahitan lepas", "notes": MARK})
        pid = (pk or {}).get("id")
        track("dewi_cmt_permak", pid)
        if st not in (200, 201):
            bad("INV-6", "gagal buat permak sendiri", {"http": st, "resp": pk})
        else:
            fg_mid = fg_before + 90
            call("POST", f"/api/dewi/cmt-permak/{pid}/status", adm,
                 json={"status": "in_progress", "note": MARK})
            st2, res = call("POST", f"/api/dewi/cmt-permak/{pid}/status", adm,
                            json={"status": "selesai_berhasil", "qty_fixed": 6,
                                  "qty_scrap": 0, "note": MARK})
            fg_now = float((db.rahaza_material_stock.find_one(
                {"material_id": (fg_mat or {}).get("id"), "location_id": fg_loc},
                {"_id": 0}) or {}).get("qty") or 0)
            ji2 = db.production_job_items.find_one({"id": ji["id"]}, {"_id": 0}) or {}
            ev = {"http": st2, "stok_sebelum": fg_mid, "stok_sesudah": fg_now,
                  "qty_accepted": ji2.get("qty_accepted"), "qty_repaired": ji2.get("qty_repaired"),
                  "qty_rework_open": ji2.get("qty_rework_open")}
            if abs(fg_now - (fg_mid + 6)) < 0.001 and int(ji2.get("qty_accepted") or 0) == 96 \
                    and int(ji2.get("qty_rework_open") or 0) == 4:
                ok("INV-6", "permak sendiri selesai → stok +6, accepted 96, rework_open 4", ev)
            else:
                bad("INV-6", "permak selesai tidak menutup lingkaran", ev)

        # ── INV-7: retur ke CMT 4 pcs → SJ REWORK + terlihat vendor ──
        st, pk2 = call("POST", "/api/dewi/cmt-permak/from-receipt-line", adm, json={
            "receipt_line_id": line["id"], "qty": 4, "permak_type": "retur_ke_cmt",
            "reason": "harus dijahit ulang vendor", "notes": MARK})
        pid2 = (pk2 or {}).get("id")
        track("dewi_cmt_permak", pid2)
        rework = (pk2 or {}).get("rework") or {}
        track("vendor_shipments", rework.get("shipment_id"))
        for x in db.vendor_shipment_items.find({"shipment_id": rework.get("shipment_id")}, {"_id": 0}):
            track("vendor_shipment_items", x["id"])
        seen_by_vendor = False
        if ven and pid2:
            stv, vlist = call("GET", "/api/dewi/cmt-permak", ven)
            body = json.dumps(vlist, default=str) if not isinstance(vlist, str) else vlist
            seen_by_vendor = pid2 in body
        ev = {"http": st, "shipment_number": rework.get("shipment_number"),
              "parent_shipment_id": rework.get("parent_shipment_id"),
              "karantina": rework.get("quarantine"), "terlihat_vendor": seen_by_vendor,
              "vendor_id_permak": (pk2 or {}).get("vendor_id")}
        if rework.get("ok") and seen_by_vendor:
            ok("INV-7", "retur ke CMT → SJ REWORK terbentuk & permak terlihat vendor", ev)
        else:
            bad("INV-7", "retur ke CMT belum memicu pekerjaan vendor", ev)

        # ── INV-11: surat jalan buyer GABUNGAN 2 PO → child & rincian per PO ──
        st, po2 = call("POST", "/api/production-pos", adm, json={
            "po_number": test_doc_number("production_pos.po_number_maklon", adm),
            "business_type": "maklon", "buyer_id": client["id"],
            "vendor_id": vendor_id, "status": "Confirmed", "notes": MARK,
            "po_date": date.today().isoformat(), "deadline": date.today().isoformat(),
            "items": [{"catalog_item_id": cat["id"], "maklon_variant_id": v0.get("id"),
                       "sku": v0.get("sku"), "color": v0.get("color"), "size": v0.get("size"),
                       "product_name": cat.get("product_name"), "qty": 20,
                       "cmt_price_snapshot": rate, "serial_number": "INV-S02"}]})
        if st in (200, 201):
            po2_id = po2["id"]
            track("production_pos", po2_id)
            poi2 = list(db.po_items.find({"po_id": po2_id}, {"_id": 0}))[0]
            track("po_items", poi2["id"])
            # jalur ringkas: kirim material → inspeksi → job → progress → deklarasi → QC
            sj2 = f"INV-SJ2-{int(time.time())}"
            st, vs2 = call("POST", "/api/vendor-shipments", adm, json={
                "vendor_id": vendor_id, "shipment_number": sj2, "po_id": po2_id, "notes": MARK,
                "shipment_date": date.today().isoformat(), "shipment_type": "NORMAL",
                "items": [{"po_id": po2_id, "po_item_id": poi2["id"], "sku": poi2.get("sku"),
                           "qty_sent": 20}]})
            vs2_id = (vs2 or {}).get("id")
            track("vendor_shipments", vs2_id)
            vsi2 = list(db.vendor_shipment_items.find({"shipment_id": vs2_id}, {"_id": 0}))
            for x in vsi2:
                track("vendor_shipment_items", x["id"])
            call("PUT", f"/api/vendor-shipments/{vs2_id}", ven or adm, json={"status": "Received"})
            st, insp2 = call("POST", "/api/vendor-material-inspections", ven or adm, json={
                "shipment_id": vs2_id, "overall_notes": MARK,
                "items": [{"shipment_item_id": vsi2[0]["id"], "sku": vsi2[0].get("sku"),
                           "ordered_qty": 20, "received_qty": 20, "missing_qty": 0}]})
            track("vendor_material_inspections", (insp2 or {}).get("id"))
            for x in db.vendor_material_inspection_items.find(
                    {"inspection_id": (insp2 or {}).get("id")}, {"_id": 0}):
                track("vendor_material_inspection_items", x["id"])
            st, job2 = call("POST", "/api/production-jobs", adm, json={
                "vendor_shipment_id": vs2_id, "vendor_id": vendor_id, "po_id": po2_id, "notes": MARK})
            job2_id = (job2 or {}).get("id")
            track("production_jobs", job2_id)
            ji2 = list(db.production_job_items.find({"job_id": job2_id}, {"_id": 0}))[0]
            track("production_job_items", ji2["id"])
            st, pr2 = call("POST", "/api/production-progress", ven or adm, json={
                "job_item_id": ji2["id"], "completed_quantity": 20,
                "progress_date": date.today().isoformat(), "notes": MARK})
            track("production_progress", (pr2 or {}).get("id"))
            st, decl2 = call("POST", "/api/buyer-shipments", ven or adm, json={
                "po_id": po2_id, "job_id": job2_id, "notes": MARK,
                "shipment_date": date.today().isoformat(),
                "items": [{"po_item_id": poi2["id"], "job_item_id": ji2["id"],
                           "sku": ji2.get("sku"), "qty_shipped": 20}]})
            track("buyer_shipments", (decl2 or {}).get("id"))
            for x in db.buyer_shipment_items.find({"shipment_id": (decl2 or {}).get("id")}, {"_id": 0}):
                track("buyer_shipment_items", x["id"])
            time.sleep(1)
            r2 = db.cmt_receipts.find_one({"related_shipment_id": (decl2 or {}).get("id")}, {"_id": 0})
            if r2:
                track("cmt_receipts", r2["id"])
                l2 = list(db.cmt_receipt_lines.find({"receipt_id": r2["id"]}, {"_id": 0}))
                for x in l2:
                    track("cmt_receipt_lines", x["id"])
                call("PUT", f"/api/prod/cmt-receipts/{r2['id']}/lines/{l2[0]['id']}", adm,
                     json={"qty_actual": 20, "reject_qty": 0})
                call("POST", f"/api/prod/cmt-receipts/{r2['id']}/complete-qc", adm)
                track("dewi_cmt_payments",
                      (db.dewi_cmt_payments.find_one({"source_receipt_id": r2["id"]}, {"_id": 0}) or {}).get("id"))
                # SJ buyer GABUNGAN: item dari 2 PO sekaligus
                st, cons = call("POST", "/api/buyer-shipments", adm, json={
                    "source_receipt_ids": [rid, r2["id"]], "notes": MARK,
                    "shipment_date": date.today().isoformat(),
                    "items": [
                        {"po_item_id": poi["id"], "job_item_id": ji["id"],
                         "sku": ji.get("sku"), "qty_shipped": 10},
                        {"po_item_id": poi2["id"], "job_item_id": ji2["id"],
                         "sku": ji2.get("sku"), "qty_shipped": 20},
                    ]})
                cons_id = (cons or {}).get("id")
                track("buyer_shipments", cons_id)
                for x in db.buyer_shipment_items.find({"shipment_id": cons_id}, {"_id": 0}):
                    track("buyer_shipment_items", x["id"])
                if st not in (200, 201):
                    bad("INV-11", "gagal buat surat jalan buyer GABUNGAN 2 PO",
                        {"http": st, "resp": cons})
                else:
                    st, det = call("GET", f"/api/buyer-shipments/{cons_id}", adm)
                    bd = (det or {}).get("po_breakdown") or []
                    ev = {"po_ids": (det or {}).get("po_ids"),
                          "is_consolidated": (det or {}).get("is_consolidated"),
                          "po_breakdown": bd,
                          "child_shipment_count": (det or {}).get("child_shipment_count"),
                          "source_receipts": len((det or {}).get("source_receipts") or [])}
                    if len(bd) == 2 and (det or {}).get("is_consolidated") \
                            and len((det or {}).get("source_receipts") or []) == 2:
                        ok("INV-11", "SJ gabungan 2 PO bisa dibaca ulang (rincian per PO + sumber penerimaan)", ev)
                    else:
                        bad("INV-11", "SJ gabungan tidak mengembalikan rincian per PO / sumber",
                            ev)

        # ── INV-12: inspeksi dengan qty KURANG → permintaan komponen OTOMATIS ──
        sj3 = f"INV-SJ3-{int(time.time())}"
        st, vs3 = call("POST", "/api/vendor-shipments", adm, json={
            "vendor_id": vendor_id, "shipment_number": sj3, "po_id": po_id, "notes": MARK,
            "shipment_date": date.today().isoformat(), "shipment_type": "ADDITIONAL",
            "parent_shipment_id": vs_id,
            "items": [{"po_id": po_id, "po_item_id": poi["id"], "sku": poi.get("sku"), "qty_sent": 10}]})
        vs3_id = (vs3 or {}).get("id")
        track("vendor_shipments", vs3_id)
        vsi3 = list(db.vendor_shipment_items.find({"shipment_id": vs3_id}, {"_id": 0}))
        for x in vsi3:
            track("vendor_shipment_items", x["id"])
        if vs3_id:
            call("PUT", f"/api/vendor-shipments/{vs3_id}", ven or adm, json={"status": "Received"})
            st, insp3 = call("POST", "/api/vendor-material-inspections", ven or adm, json={
                "shipment_id": vs3_id, "overall_notes": MARK,
                "items": [{"shipment_item_id": vsi3[0]["id"], "sku": vsi3[0].get("sku"),
                           "ordered_qty": 10, "received_qty": 7, "missing_qty": 3,
                           "condition_notes": "3 pcs panel kurang"}]})
            track("vendor_material_inspections", (insp3 or {}).get("id"))
            for x in db.vendor_material_inspection_items.find(
                    {"inspection_id": (insp3 or {}).get("id")}, {"_id": 0}):
                track("vendor_material_inspection_items", x["id"])
            for x in db.production_jobs.find({"vendor_shipment_id": vs3_id}, {"_id": 0}):
                track("production_jobs", x["id"])
                for y in db.production_job_items.find({"job_id": x["id"]}, {"_id": 0}):
                    track("production_job_items", y["id"])
            cr = (insp3 or {}).get("component_request") if isinstance(insp3, dict) else None
            if not cr:
                cr = db.dewi_cmt_component_requests.find_one(
                    {"inspection_id": (insp3 or {}).get("id")}, {"_id": 0})
            if cr:
                track("dewi_cmt_component_requests", cr.get("id"))
            ev = {"http": st,
                  "request_code": (cr or {}).get("request_code"),
                  "po_id": (cr or {}).get("po_id"), "vendor_id": (cr or {}).get("vendor_id"),
                  "inspection_id": (cr or {}).get("inspection_id"),
                  "origin": (cr or {}).get("origin"),
                  "qty": sum(float(i.get("qty") or 0) for i in ((cr or {}).get("items") or []))}
            if cr and cr.get("po_id") and cr.get("vendor_id") and cr.get("inspection_id") \
                    and abs(ev["qty"] - 3) < 0.001:
                ok("INV-12", "inspeksi kurang 3 pcs → permintaan komponen otomatis "
                             "(menunjuk PO + vendor + inspeksi)", ev)
            else:
                bad("INV-12", "temuan kurang saat inspeksi tidak membentuk permintaan komponen "
                              "yang menunjuk PO/vendor/inspeksi", ev)

        run_db_audits()

    finally:
        stats = {}

        try:
            dbc = db_handle()
            for coll, ids in CREATED.items():
                ids = [i for i in ids if i]
                if ids:
                    n = dbc[coll].delete_many({"id": {"$in": ids}}).deleted_count
                    if n:
                        stats[coll] = n
            for coll in ("dewi_maklon_pos", "rahaza_ar_invoices", "production_pos",
                         "vendor_shipments", "buyer_shipments", "cmt_receipts",
                         "dewi_cmt_permak", "rahaza_fg_movements", "rahaza_stock_ledger"):
                if coll in dbc.list_collection_names():
                    n = dbc[coll].delete_many({"notes": {"$regex": MARK}}).deleted_count
                    if n:
                        stats[coll] = stats.get(coll, 0) + n

            # ── UANG PALSU (temuan 2026-08-08) ───────────────────────────────
            # `rahaza_ar_invoices` ADA di daftar di atas, tetapi disaring lewat
            # `notes` yang memuat MARK — padahal catatan AR invoice DITULIS OLEH
            # jembatan maklon ("Auto-generated dari PO Produksi Maklon <no>") dan
            # TIDAK PERNAH memuat MARK. Akibatnya setiap kali gate ini jalan, dua
            # AR invoice maklon (Rp 1.800.000 + Rp 360.000) tertinggal sebagai
            # PIUTANG YATIM — PO-nya sudah dihapus, tapi tagihannya masih ada dan
            # ikut terbaca laporan Keuangan. Terhitung Rp 15.120.000 palsu sudah
            # menumpuk dari sesi-sesi sebelumnya sebelum ini ditemukan.
            # Sekarang dihapus berdasarkan FK ke PO yang memang dibuat gate ini.
            _po_ids = [i for i in CREATED.get("production_pos", []) if i]
            if _po_ids and "rahaza_ar_invoices" in dbc.list_collection_names():
                n = dbc.rahaza_ar_invoices.delete_many(
                    {"linked_maklon_po_id": {"$in": _po_ids}}).deleted_count
                if n:
                    stats["rahaza_ar_invoices"] = stats.get("rahaza_ar_invoices", 0) + n
            # Jaring pengaman: AR invoice maklon YATIM (PO-nya sudah tidak ada).
            if "rahaza_ar_invoices" in dbc.list_collection_names():
                _orphans = []
                for inv in dbc.rahaza_ar_invoices.find(
                        {"source_module": "maklon_po"},
                        {"_id": 1, "linked_maklon_po_id": 1}):
                    pid = inv.get("linked_maklon_po_id")
                    if not pid:
                        continue
                    if not dbc.production_pos.find_one({"id": pid}, {"_id": 1}) and \
                       not dbc.dewi_maklon_pos.find_one({"id": pid}, {"_id": 1}):
                        _orphans.append(inv["_id"])
                if _orphans:
                    n = dbc.rahaza_ar_invoices.delete_many({"_id": {"$in": _orphans}}).deleted_count
                    stats["rahaza_ar_invoices_yatim"] = n
            print(f"\n{Y}bersih-bersih:{X} {json.dumps(stats)}")
        except Exception as e:
            print(f"{R}cleanup gagal: {e}{X}")

    print(f"\n{B}{'-' * 92}{X}")
    print(f"  PASS {len(PASSES)} · FAIL {len(FAILS)}")
    if FAILS:
        print(f"  {R}{B}MERAH — pelanggaran: {', '.join(FAILS)}{X}")
        return 1
    print(f"  {G}{B}HIJAU — semua invarian alur produksi/maklon/CMT aman{X}")
    return 0


def audit_only() -> int:
    print(f"{B}{C}{'=' * 92}\n  AUDIT DATA (INV-13..INV-18) — tanpa membuat data uji\n{'=' * 92}{X}")
    run_db_audits()
    print(f"\n{B}{'-' * 92}{X}")
    print(f"  PASS {len(PASSES)} · FAIL {len(FAILS)}")
    if FAILS:
        print(f"  {R}{B}MERAH — pelanggaran: {', '.join(FAILS)}{X}")
        return 1
    print(f"  {G}{B}HIJAU — audit data bersih{X}")
    return 0


if __name__ == "__main__":
    sys.exit(audit_only() if "--audit-only" in sys.argv else main())
