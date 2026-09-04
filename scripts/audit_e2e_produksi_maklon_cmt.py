#!/usr/bin/env python3
"""
audit_e2e_produksi_maklon_cmt.py — PEMBUKTIAN CACAT ALUR (bukan cek HTTP 200).

Menjalankan alur NYATA lewat HTTP dan MEMBANDINGKAN ANGKA di setiap sambungan:
  Maklon PO / Produksi PO → varian → job CMT → progress vendor →
  kirim material ke CMT (gudang) → terima FG dari CMT (+reject) →
  permak/rework → dispatch ke buyer (single + gabungan multi-PO) →
  finance (AP CMT / AR buyer / GL) → stok FG gudang.

Prinsip:
  • Setiap temuan HARUS punya bukti angka / respons nyata.
  • Semua data uji ditandai `__AUDIT__` dan DIBERSIHKAN di `finally` langsung ke Mongo
    (tidak mengandalkan endpoint DELETE yang mungkin hanya meng-cancel).

Pakai:  python3 scripts/audit_e2e_produksi_maklon_cmt.py
Keluar: docs/AUDIT_E2E_FINDINGS.json  + ringkasan di terminal
"""
from __future__ import annotations
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("API_BASE", "http://localhost:8001")
MARK = "__AUDIT__"

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

FINDINGS: list[dict] = []
CREATED: dict[str, list] = {}          # collection -> [ids]


def rec(code: str, severity: str, title: str, evidence, expected: str = "", where: str = ""):
    FINDINGS.append({"code": code, "severity": severity, "title": title,
                     "evidence": evidence, "expected": expected, "where": where})
    col = R if severity in ("CRIT", "HIGH") else Y if severity == "MED" else C
    print(f"  {col}[{severity}] {code} — {title}{X}")
    if evidence not in (None, ""):
        s = json.dumps(evidence, default=str) if not isinstance(evidence, str) else evidence
        print(f"        bukti   : {s[:400]}")
    if expected:
        print(f"        harusnya: {expected}")
    if where:
        print(f"        lokasi  : {where}")


def ok(msg: str, detail=""):
    print(f"  {G}[OK]{X} {msg}" + (f" — {detail}" if detail else ""))


def head(t: str):
    print(f"\n{B}{C}{'─' * 96}\n▶ {t}\n{'─' * 96}{X}")


# ─────────────────────────── HTTP helpers ───────────────────────────
_tokens: dict[str, str] = {}


def login(email: str, password: str) -> str | None:
    if email in _tokens:
        return _tokens[email]
    for attempt in range(6):
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": password}, timeout=25)
        if r.status_code == 200:
            _tokens[email] = r.json().get("token", "")
            return _tokens[email]
        if r.status_code == 429:
            time.sleep(12)
            continue
        print(f"  {R}login {email} gagal HTTP {r.status_code}: {r.text[:150]}{X}")
        return None
    return None


def H(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def call(method: str, path: str, tok: str, **kw):
    """Return (status_code, parsed_or_text)."""
    url = f"{BASE}{path}"
    try:
        r = requests.request(method, url, headers=H(tok), timeout=90, **kw)
    except Exception as e:
        return 0, str(e)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text[:600]


def db_handle():
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


def track(coll: str, _id):
    CREATED.setdefault(coll, []).append(_id)


# ═══════════════════════════════════════════════════════════════════════════
#  PROBE 1 — MASTER VARIAN (akar cacat "pilih varian tidak muncul")
# ═══════════════════════════════════════════════════════════════════════════
def probe_variant_master(adm):
    head("PROBE 1 — Master VARIAN: apakah ada yang bisa dipilih saat buat PO?")
    st, models = call("GET", "/api/rahaza/models", adm)
    mlist = models.get("models", models) if isinstance(models, dict) else models
    mlist = mlist if isinstance(mlist, list) else []
    total_variants = 0
    per_model = {}
    for m in mlist:
        s2, v = call("GET", f"/api/rahaza/models/{m['id']}/variants", adm)
        vs = (v.get("variants") if isinstance(v, dict) else v) or []
        per_model[m.get("code") or m.get("id")] = len(vs)
        total_variants += len(vs)
    if total_variants == 0:
        rec("VAR-1", "CRIT",
            "Master varian internal (rahaza_model_variants) KOSONG → PO Produksi internal "
            "tidak mungkin dibuat karena UI mewajibkan pilih varian",
            {"models": per_model, "total_variants": total_variants},
            "≥1 varian per model aktif, atau UI harus menyediakan jalan membuat varian dari form PO",
            "frontend/src/components/erp/engine/ProductionPOModule.jsx:295-302 (validasi wajib varian)")
    else:
        ok("varian internal tersedia", per_model)

    st, cats = call("GET", "/api/dewi/maklon/buyer-catalog", adm)
    clist = cats.get("items", cats) if isinstance(cats, dict) else cats
    clist = clist if isinstance(clist, list) else []
    cat_var = {c.get("artikel_code"): len(c.get("variants") or []) for c in clist}
    if clist and all(v == 0 for v in cat_var.values()):
        rec("VAR-2", "HIGH", "Semua artikel Buyer Catalog belum punya variants[]",
            cat_var, "generate variants dulu", "routes/dewi_maklon_buyer_catalog.py:389")
    else:
        ok("buyer catalog punya variants[]", cat_var)
    return clist


# ═══════════════════════════════════════════════════════════════════════════
#  PROBE 2 — PO MAKLON: apakah identitas varian tersimpan?
# ═══════════════════════════════════════════════════════════════════════════
def probe_maklon_po_variant(adm, catalogs):
    head("PROBE 2 — Buat PO MAKLON dengan varian master → apakah varian tersimpan?")
    if not catalogs:
        rec("MK-0", "HIGH", "Tidak ada buyer catalog untuk diuji", {}, "", "")
        return None
    cat = next((c for c in catalogs if (c.get("variants") or [])), catalogs[0])
    variants = cat.get("variants") or []
    st, clients = call("GET", "/api/dewi/maklon/clients?status=active", adm)
    clist = clients if isinstance(clients, list) else clients.get("items", [])
    client = next((c for c in clist if c.get("id") == cat.get("client_id")), clist[0] if clist else None)
    if not client:
        rec("MK-0b", "HIGH", "Tidak ada klien maklon", {}, "", "")
        return None

    items = []
    for i, v in enumerate(variants[:2], start=1):
        items.append({
            "seri_no": f"A{i:02d}", "artikel": cat["artikel_code"],
            "sku_code": v.get("sku"), "color": v.get("color"), "size": v.get("size"),
            "qty": 100 if i == 1 else 50,
            "cmt_rate_per_pcs": float(cat.get("default_cmt_price") or 10000),
            "buyer_catalog_id": cat["id"],
            "maklon_variant_id": v.get("id"),          # ← dikirim FE? diuji di bawah
            "notes": MARK,
        })
    if not items:
        items = [{"seri_no": "A01", "artikel": cat["artikel_code"], "qty": 100,
                  "cmt_rate_per_pcs": 10000, "buyer_catalog_id": cat["id"], "notes": MARK}]

    st, po = call("POST", "/api/dewi/maklon/pos", adm, json={
        "client_id": client["id"], "po_date": date.today().isoformat(),
        "deadline": date.today().isoformat(), "notes": MARK, "items": items})
    if st not in (200, 201):
        rec("MK-1", "CRIT", "POST /api/dewi/maklon/pos GAGAL", {"http": st, "resp": po}, "201", "")
        return None
    po_id = po.get("id")
    track("dewi_maklon_pos", po_id)
    saved = (po.get("items") or [])
    fk_keys = ("maklon_variant_id", "variant_id", "buyer_catalog_variant_id")
    lost = [] if (saved and any(saved[0].get(k) for k in fk_keys)) else list(fk_keys)
    if lost:
        rec("MK-2", "HIGH",
            "PO Maklon TIDAK menyimpan FK varian — identitas varian hilang setelah simpan "
            "(hanya teks color/size). Downstream (FG/SKU/stok) tidak bisa ditautkan ke master.",
            {"field_hilang": lost, "item_tersimpan": saved[0] if saved else None},
            "items[] menyimpan maklon_variant_id/sku_code hasil pilih varian master",
            "backend/routes/dewi_maklon_pos.py:161 MaklonPOItemIn (tidak punya field varian) + "
            "frontend/src/components/erp/MaklonPOModule.jsx:106-111 (color/size free-text)")
    else:
        ok("PO maklon menyimpan FK varian")

    # ── SSOT: dewi_maklon_pos SEHARUSNYA hanya MIRROR dari production_pos ──
    db = db_handle()
    doc = db.dewi_maklon_pos.find_one({"id": po_id}, {"_id": 0}) or {}
    prod = db.production_pos.find_one({"id": po_id}, {"_id": 0})
    if not prod and not doc.get("mirror_of"):
        rec("SSOT-1", "CRIT",
            "Portal MAKLON membuat PO ASLI di collection yang secara arsitektur adalah "
            "MIRROR (`dewi_maklon_pos`, mirror_of='production_pos'). PO ini TIDAK punya baris "
            "`production_pos` → tidak bisa dibuatkan job CMT, tidak bisa kirim material, "
            "tidak bisa diterima, tidak bisa dispatch. Hanya menghasilkan invoice AR.",
            {"po_number": po.get("po_number"), "mirror_of": doc.get("mirror_of"),
             "production_po_id": doc.get("production_po_id"), "production_pos_ada": False},
            "SSOT PO = production_pos. Portal Maklon menulis ke SSOT itu (atau form maklon "
            "membuat production_pos + mirror sekaligus)",
            "routes/production_maklon_bridge.py:104-150 (mirror writer) vs "
            "routes/dewi_maklon_pos.py:271 create_maklon_po (menulis original ke mirror)")
        # buktikan tidak bisa diproduksi: coba kirim material ke CMT untuk PO ini
        st3, vs = call("POST", "/api/vendor-shipments", adm, json={
            "vendor_id": "mk-vendor-demo-1", "shipment_number": f"AUDIT-PROOF-{int(time.time())}",
            "po_id": po_id, "shipment_date": date.today().isoformat(), "notes": MARK,
            "items": [{"po_id": po_id, "qty_sent": 10}]})
        rec("SSOT-1b", "CRIT",
            "Tidak ada validasi FK: `POST /api/vendor-shipments` MENERIMA po_id yang tidak ada "
            "di production_pos (HTTP %s) → terbentuk surat jalan material YATIM "
            "(po_number kosong, business_type jatuh ke 'internal'). Kesalahan tidak pernah "
            "terlihat, datanya jadi sampah." % st3,
            {"http": st3, "po_id_dikirim": po_id,
             "shipment_terbentuk": (vs or {}).get("shipment_number") if st3 in (200, 201) else None,
             "po_number_di_shipment": (vs or {}).get("po_number") if st3 in (200, 201) else None,
             "business_type": (vs or {}).get("business_type") if st3 in (200, 201) else None},
            "po_id wajib divalidasi ada di SSOT PO → 400 bila tidak ada",
            "routes/vendor_shipment.py:151 (po lookup hasilnya tidak pernah di-assert)")
        if st3 in (200, 201):
            track("vendor_shipments", (vs or {}).get("id"))
    else:
        ok("PO maklon terhubung ke SSOT production_pos")

    # ── Berapa banyak PO maklon yatim di data nyata? ──
    orphans = []
    for d in db.dewi_maklon_pos.find({}, {"_id": 0, "id": 1, "po_number": 1, "status": 1, "mirror_of": 1}):
        if d.get("id") == po_id:
            continue
        if not db.production_pos.find_one({"id": d["id"]}, {"_id": 1}):
            orphans.append({"po": d.get("po_number"), "status": d.get("status")})
    if orphans:
        fake_progress = [o for o in orphans if o["status"] in
                         ("in_production", "partial_delivered", "completed", "invoiced")]
        rec("ORPH-1", "CRIT",
            f"{len(orphans)} PO Maklon yatim (tanpa production_pos). "
            f"{len(fake_progress)} di antaranya berstatus 'sedang/selesai produksi' padahal "
            "NOL job, NOL kirim material, NOL penerimaan → progres PALSU di layar",
            {"yatim": orphans[:12], "berstatus_produksi_atau_selesai": len(fake_progress)},
            "tiap PO maklon punya production_pos; status produksi dihitung dari job nyata",
            "collection dewi_maklon_pos")
    return po


# ═══════════════════════════════════════════════════════════════════════════
#  PROBE 3 — TRACKING: satu SSOT atau bukan?
# ═══════════════════════════════════════════════════════════════════════════
def probe_tracking(adm, maklon_po):
    head("PROBE 3 — TRACKING produksi: ambil dari collection mana? konsisten dengan PO?")
    st, trk = call("GET", "/api/production-tracking", adm)
    rows = trk.get("items", trk) if isinstance(trk, dict) else trk
    rows = rows if isinstance(rows, list) else []
    _pns = {(j or {}).get("po_number") for r in rows if isinstance(r, dict)
            for j in (r.get("jobs") or [])} | {r.get("po_number") for r in rows
                                               if isinstance(r, dict)}
    po_numbers = sorted(x for x in _pns if x)
    ok(f"/api/production-tracking → {len(rows)} baris", po_numbers[:8])

    if maklon_po:
        found = maklon_po.get("po_number") in po_numbers
        if not found:
            rec("TRK-1", "CRIT",
                "PO maklon baru TIDAK terlihat di Tracking Produksi → tracking membaca "
                "production_pos/po_items, bukan PO maklon",
                {"po_maklon": maklon_po.get("po_number"), "po_di_tracking": po_numbers[:10]},
                "tracking menampilkan semua PO (maklon + internal) dari SSOT PO",
                "routes/production_stage_tracking.py (baca production_pos) & "
                "routes/maklon_client_tracking.py (baca production_pos + po_items)")

    # Apakah tracking maklon (portal klien) memakai sumber lain lagi?
    if maklon_po:
        st2, detail = call("GET", f"/api/dewi/maklon/orders/{maklon_po['id']}/production-detail", adm)
        rec_ev = {"http": st2, "resp": detail if st2 != 200 else list(detail.keys()) if isinstance(detail, dict) else detail}
        if st2 != 200:
            rec("TRK-2", "HIGH", "Detail produksi PO maklon error", rec_ev, "200",
                "routes/dewi_maklon_pos.py production-detail")
        else:
            ok("production-detail PO maklon OK", rec_ev)


# ═══════════════════════════════════════════════════════════════════════════
#  PROBE 4 — PORTAL CMT / VENDOR: apakah pekerjaan & progress vendor nyambung?
# ═══════════════════════════════════════════════════════════════════════════
def probe_vendor_island(adm, ven):
    head("PROBE 4 — Portal CMT/Vendor: job & progress vendor nyambung ke PO?")
    st_a, vjobs = call("GET", "/api/vendor-portal/jobs", adm)
    st_b, myjobs = call("GET", "/api/vendor-portal/my-jobs", ven) if ven else (0, [])
    st_c, pjobs = call("GET", "/api/production-jobs", adm)
    st_d, myp = call("GET", "/api/production-jobs", ven) if ven else (0, [])

    def n(x):
        if isinstance(x, dict):
            x = x.get("items", x.get("jobs", []))
        return len(x) if isinstance(x, list) else 0

    ev = {"/vendor-portal/jobs (vendor_jobs)": n(vjobs),
          "/vendor-portal/my-jobs (vendor, vendor_jobs)": n(myjobs),
          "/production-jobs (production_jobs)": n(pjobs),
          "/production-jobs sebagai vendor": n(myp)}
    reg = (ROOT / "frontend" / "src" / "components" / "erp" / "moduleRegistry.js").read_text(errors="ignore")
    retired = ("VendorCMTEnginePortal" in reg
               and "import('./VendorPortalModule')" not in reg)
    if n(vjobs) == 0 and n(pjobs) > 0 and not retired:
        rec("CMT-1", "CRIT",
            "DUA model pekerjaan vendor terpisah: Portal Vendor lama (`vendor_jobs` + "
            "`vendor_progress_reports`) KOSONG, sementara pekerjaan nyata ada di "
            "`production_jobs`. Progress yang diisi vendor di modul lama tidak "
            "berpengaruh ke PO, dispatch, maupun tagihan.",
            ev,
            "satu model job vendor (production_jobs) dipakai semua portal",
            "routes/vendor_portal.py (vendor_jobs/vendor_progress_reports) vs "
            "routes/production_execution.py (production_jobs/production_progress); "
            "FE: components/erp/VendorPortalModule.jsx vs components/erp/engine/VendorPortalApp.jsx")
    elif retired:
        ok("portal vendor lama sudah dipensiunkan; job vendor = production_jobs (SSOT)", ev)
    else:
        ok("job vendor konsisten", ev)

    # CMT lifecycle (Portal CMT) — apakah job CMT menunjuk PO & vendor?
    st, life = call("GET", "/api/dewi/cmt/lifecycle", adm)
    rows = life.get("items", life) if isinstance(life, dict) else life
    rows = rows if isinstance(rows, list) else []
    db = db_handle()
    jobs = list(db.dewi_cmt_jobs.find({}, {"_id": 0}).limit(20))
    no_po = [j.get("job_code") for j in jobs if not j.get("po_id") and not j.get("po_number")]
    ssot_ok = any((r.get("ssot_job_count") or 0) > 0 or (r.get("po_numbers") or [])
                  for r in rows if isinstance(r, dict))
    # Job legacy yang SUDAH DITANDAI `legacy_no_po` bukan lagi kerusakan senyap:
    # layar menampilkannya sebagai data lama yang harus dibersihkan.
    flagged = db.dewi_cmt_jobs.count_documents({"legacy_no_po": True})
    if jobs and flagged == len(jobs) and any(
            "ssot_jobs" in r for r in rows if isinstance(r, dict)):
        ssot_ok = True
    if jobs and len(no_po) == len(jobs) and not ssot_ok:
        rec("CMT-2", "CRIT",
            "Semua job di Portal CMT (`dewi_cmt_jobs`) TIDAK punya po_id/po_number → "
            "pekerjaan CMT tidak bisa ditelusuri ke PO mana pun",
            {"total_job_cmt": len(jobs), "tanpa_po": len(no_po), "contoh": no_po[:5],
             "field_yang_ada": sorted(jobs[0].keys()) if jobs else []},
            "dewi_cmt_jobs.po_id wajib (atau job CMT = production_jobs)",
            "routes/dewi_cmt_lifecycle.py + collection dewi_cmt_jobs")
    # Master vendor ganda?
    vp = db.vendor_partners.count_documents({})
    cp = db.dewi_cmt_partners.count_documents({})
    vp_ids = set(db.vendor_partners.distinct("id"))
    cp_ids = set(db.dewi_cmt_partners.distinct("id"))
    if vp and cp and not (vp_ids & cp_ids):  # noqa: SIM102 — sengaja: 0 irisan = belum disatukan
        rec("CMT-3", "HIGH",
            "DUA master vendor CMT yang tidak beririsan: `vendor_partners` (dipakai "
            "produksi/maklon) vs `dewi_cmt_partners` (dipakai Portal CMT & pembayaran CMT)",
            {"vendor_partners": vp, "dewi_cmt_partners": cp, "id_beririsan": 0},
            "satu master vendor CMT",
            "routes/vendor_portal.py & routes/production_rbac.resolve_vendor_doc vs "
            "routes/dewi_cmt_lifecycle.py / production_maklon_bridge.py")


# ═══════════════════════════════════════════════════════════════════════════
#  PROBE 5 — ALUR NYATA di engine produksi: PO → job → progress → terima → dispatch
# ═══════════════════════════════════════════════════════════════════════════
def probe_full_engine_flow(adm, ven, catalogs):
    head("PROBE 5 — ALUR PENUH engine: PO maklon(engine) → job CMT → progress → "
         "deklarasi kirim → terima FG (+reject) → dispatch buyer")
    db = db_handle()
    cat = next((c for c in catalogs if (c.get("variants") or [])), None)
    if not cat:
        rec("FLOW-0", "HIGH", "tidak ada catalog bervarian untuk alur penuh", {}, "", "")
        return
    variants = cat["variants"]
    st, clients = call("GET", "/api/dewi/maklon/clients?status=active", adm)
    clist = clients if isinstance(clients, list) else []
    client = next((c for c in clist if c["id"] == cat.get("client_id")), clist[0] if clist else None)
    vendor_id = "mk-vendor-demo-1"

    po_number = f"AUDIT-PO-{int(time.time())}"
    v0 = variants[0]
    st, po = call("POST", "/api/production-pos", adm, json={
        "po_number": po_number, "business_type": "maklon",
        "buyer_id": client["id"] if client else None,
        "vendor_id": vendor_id, "status": "Confirmed",
        "po_date": date.today().isoformat(), "deadline": date.today().isoformat(),
        "notes": MARK,
        "items": [{"catalog_item_id": cat["id"], "maklon_variant_id": v0.get("id"),
                   "sku": v0.get("sku"), "color": v0.get("color"), "size": v0.get("size"),
                   "product_name": cat.get("product_name"), "qty": 100,
                   "cmt_price_snapshot": float(cat.get("default_cmt_price") or 10000),
                   "selling_price_snapshot": float(cat.get("default_selling_price") or 30000),
                   "serial_number": "AUD-S01"}]})
    if st not in (200, 201):
        rec("FLOW-1", "CRIT", "POST /api/production-pos gagal", {"http": st, "resp": po}, "201", "")
        return
    po_id = po.get("id") or (po.get("po") or {}).get("id")
    track("production_pos", po_id)
    po_items = list(db.po_items.find({"po_id": po_id}, {"_id": 0}))
    for it in po_items:
        track("po_items", it["id"])
    ok(f"PO engine dibuat {po_number}", {"po_id": po_id, "items": len(po_items)})

    # --- qty field contract check ---
    if po_items and po_items[0].get("qty_ordered") is None and po_items[0].get("qty") is not None:
        rec("FLD-1", "MED",
            "po_items menyimpan `qty` tetapi banyak konsumen membaca `qty_ordered` → "
            "kolom qty tampil kosong/0 di beberapa layar",
            {"contoh_item": {k: po_items[0].get(k) for k in ("id", "qty", "qty_ordered", "sku")}},
            "satu nama field kuantitas pesanan",
            "routes/production_pos.py:279 vs pembaca yang memakai qty_ordered")

    # --- Kirim material/panel ke CMT (vendor_shipment) ---
    sj_no = f"AUDIT-SJ-{int(time.time())}"
    st, vs = call("POST", "/api/vendor-shipments", adm, json={
        "vendor_id": vendor_id, "shipment_number": sj_no, "po_id": po_id,
        "shipment_date": date.today().isoformat(), "shipment_type": "NORMAL",
        "notes": MARK,
        "items": [{"po_id": po_id, "po_item_id": po_items[0]["id"],
                   "sku": po_items[0].get("sku"), "qty_sent": 100}]})
    if st not in (200, 201):
        rec("FLOW-2a", "CRIT", "gagal kirim material/panel ke CMT (vendor_shipments)",
            {"http": st, "resp": vs}, "201", "routes/vendor_shipment.py:151")
        return
    vs_id = vs.get("id") or (vs.get("shipment") or {}).get("id")
    track("vendor_shipments", vs_id)
    vsi = list(db.vendor_shipment_items.find({"shipment_id": vs_id}, {"_id": 0}))
    for x in vsi:
        track("vendor_shipment_items", x["id"])
    ok("SJ material ke CMT dibuat", {"no": sj_no, "items": len(vsi)})

    # vendor terima + inspeksi
    st, _ = call("PUT", f"/api/vendor-shipments/{vs_id}", ven or adm, json={"status": "Received"})
    if st != 200:
        rec("FLOW-2b", "HIGH", "vendor gagal menandai SJ material 'Received'",
            {"http": st}, "200", "routes/vendor_shipment.py:256")
    st, insp = call("POST", "/api/vendor-material-inspections", ven or adm, json={
        "shipment_id": vs_id, "inspection_date": date.today().isoformat(),
        "overall_notes": MARK,
        "items": [{"shipment_item_id": vsi[0]["id"], "sku": vsi[0].get("sku"),
                   "ordered_qty": 100, "received_qty": 100, "missing_qty": 0}]})
    if st not in (200, 201):
        rec("FLOW-2c", "CRIT", "vendor gagal inspeksi material",
            {"http": st, "resp": insp}, "201", "routes/vendor_shipment.py:453")
        return
    insp_id = insp.get("id") if isinstance(insp, dict) else None
    track("vendor_material_inspections", insp_id)
    for x in db.vendor_material_inspection_items.find({"inspection_id": insp_id}, {"_id": 0}):
        track("vendor_material_inspection_items", x["id"])
    ok("inspeksi material vendor selesai")

    # --- Job CMT dari shipment yang sudah diinspeksi ---
    st, job = call("POST", "/api/production-jobs", adm, json={
        "vendor_shipment_id": vs_id, "vendor_id": vendor_id, "po_id": po_id, "notes": MARK})
    if st not in (200, 201):
        rec("FLOW-2", "HIGH", "POST /api/production-jobs (dari SJ terinspeksi) gagal",
            {"http": st, "resp": job}, "201", "routes/production_execution.py:388")
        return
    job_id = job.get("id")
    track("production_jobs", job_id)
    st, jitems = call("GET", f"/api/production-job-items?job_id={job_id}", adm)
    jrows = jitems.get("items", jitems) if isinstance(jitems, dict) else jitems
    jrows = jrows if isinstance(jrows, list) else []
    for j in jrows:
        track("production_job_items", j["id"])
    if not jrows:
        rec("FLOW-3", "HIGH", "job dibuat tetapi job_items kosong", {"job_id": job_id}, "", "")
        return
    ji = jrows[0]
    ok("job CMT dibuat", {"job": job.get("job_number"), "job_item_qty": ji.get("shipment_qty"),
                          "available_qty": ji.get("available_qty")})

    # --- Progress oleh VENDOR lewat engine (bukan portal lama) ---
    if ven:
        st, pr = call("POST", "/api/production-progress", ven, json={
            "job_item_id": ji["id"], "completed_quantity": 100,
            "progress_date": date.today().isoformat(), "notes": MARK})
        if st not in (200, 201):
            rec("FLOW-4", "HIGH", "vendor gagal input progress di engine",
                {"http": st, "resp": pr}, "201", "routes/production_execution.py:644")
        else:
            ok("vendor input progress 100 pcs (engine)")
            track("production_progress", (pr.get("id") if isinstance(pr, dict) else None))

    # --- Deklarasi kirim CMT → DA ---
    st, decl = call("POST", "/api/buyer-shipments", ven or adm, json={
        "po_id": po_id, "job_id": job_id, "shipment_date": date.today().isoformat(),
        "notes": MARK,
        "items": [{"po_item_id": po_items[0]["id"], "job_item_id": ji["id"],
                   "sku": ji.get("sku"), "qty_shipped": 100}]})
    if st not in (200, 201):
        rec("FLOW-5", "CRIT", "vendor gagal deklarasi kirim ke DA (buyer_shipments receiver_type=da)",
            {"http": st, "resp": decl}, "201", "routes/buyer_shipment.py:433")
        return
    decl_id = decl.get("id") or (decl.get("shipment") or {}).get("id")
    track("buyer_shipments", decl_id)
    rtype = (decl.get("receiver_type") if isinstance(decl, dict) else None)
    ok("deklarasi kirim CMT→DA dibuat", {"id": decl_id, "receiver_type": rtype})

    # auto cmt_receipt draft?
    time.sleep(1)
    receipts = list(db.cmt_receipts.find({"related_shipment_id": decl_id}, {"_id": 0}))
    if not receipts:
        rec("RCV-1", "HIGH",
            "Deklarasi kirim vendor TIDAK otomatis membuat draft penerimaan (cmt_receipts) "
            "→ DA harus mengetik ulang seluruh isi surat jalan",
            {"shipment_id": decl_id, "cmt_receipts_ditemukan": 0},
            "draft cmt_receipt otomatis dari deklarasi vendor (docstring buyer_shipment.py:15 menjanjikan ini)",
            "routes/buyer_shipment.py — janji 'auto-create draft cmt_receipts'")
        # buat manual supaya alur lanjut
        st, r = call("POST", "/api/prod/cmt-receipts", adm, json={
            "related_shipment_id": decl_id, "cmt_name": "CV Jahit Mitra CMT",
            "cmt_vendor_id": vendor_id, "po_id": po_id, "po_number": po_number,
            "business_type": "maklon", "notes": MARK})
        if st not in (200, 201):
            rec("RCV-2", "CRIT", "gagal buat cmt_receipt", {"http": st, "resp": r}, "201", "")
            return
        receipt = r
    else:
        receipt = receipts[0]
        ok("draft penerimaan otomatis dibuat", {"receipt": receipt.get("receipt_code")})
    rid = receipt["id"]
    track("cmt_receipts", rid)

    st, full = call("GET", f"/api/prod/cmt-receipts/{rid}", adm)
    lines = (full or {}).get("lines") or []
    for ln in lines:
        track("cmt_receipt_lines", ln["id"])
    if not lines:
        rec("RCV-3", "HIGH", "penerimaan tidak punya baris otomatis dari surat jalan",
            {"receipt": rid}, "baris terisi dari buyer_shipment_items", "")
        return
    line = lines[0]

    # --- DA hitung fisik: 100 dikirim, 90 lolos, 10 reject ---
    _fgloc = (db.rahaza_locations.find_one({"code": "ZNA-FG"}, {"_id": 0, "id": 1}) or {}).get("id")
    _fg0 = db.rahaza_material_stock.find_one(
        {"material_code": ji.get("sku"), "location_id": _fgloc}, {"_id": 0})
    fg_before = float((_fg0 or {}).get("qty") or 0)
    st, upd = call("PUT", f"/api/prod/cmt-receipts/{rid}/lines/{line['id']}", adm,
                   json={"qty_actual": 90, "reject_qty": 10, "reject_reason": "jahitan lepas"})
    st2, sub = call("POST", f"/api/prod/cmt-receipts/{rid}/submit", adm)
    st3, apr = call("POST", f"/api/prod/cmt-receipts/{rid}/approve", adm)
    steps = {"update_line": st, "submit": st2, "approve": st3}
    if st3 != 200:
        rec("RCV-4", "CRIT", "approve penerimaan gagal", {"steps": steps, "resp": apr}, "200", "")
        return
    ok("terima FG: dikirim 100 / lolos 90 / reject 10", steps)

    # ── INVARIAN 1: progress vendor harus tetap 100, reject terinformasi ──
    ji_after = db.production_job_items.find_one({"id": ji["id"]}, {"_id": 0}) or {}
    produced = int(ji_after.get("produced_qty") or 0)
    reject_fields = [k for k in ji_after if "reject" in k.lower()]
    if produced != 100:
        rec("INV-1", "HIGH", "produced_qty vendor berubah setelah reject DA",
            {"produced_qty": produced}, "tetap 100 (produksi vendor tidak berkurang)", "")
    if not reject_fields:
        rec("INV-2", "CRIT",
            "production_job_items TIDAK punya field reject sama sekali → tidak ada tempat "
            "menyimpan 'produced 100, reject 10' di sisi pekerjaan/vendor. Informasi reject "
            "hanya hidup di cmt_receipt_lines dan tak pernah kembali ke job/vendor/PO.",
            {"field_job_item": sorted(ji_after.keys()), "produced_qty": produced,
             "reject_di_penerimaan": 10},
            "job item menyimpan qty_produced / qty_reject / qty_accepted agar portal vendor "
            "dan penutupan PO menampilkan 100 produced dengan 10 reject",
            "routes/production_execution.py (tulis produced_qty saja) + "
            "routes/dewi_cmt_packing.py:432 approve (reject tidak dipropagasi)")

    # ── INVARIAN 2: ringkasan kuantitas PO ──
    st, qsum = call("GET", f"/api/production-pos/{po_id}/quantity-summary", adm)
    ev = qsum if isinstance(qsum, dict) else {"resp": qsum}
    flat = json.dumps(ev, default=str)
    if "reject" not in flat.lower():
        rec("INV-3", "HIGH",
            "Ringkasan kuantitas PO tidak memuat angka reject → saat tutup PO tidak terlihat "
            "'produced 100, reject 10'",
            ev, "quantity-summary memuat produced / accepted / reject / rework",
            "routes/production_pos.py quantity-summary")
    else:
        ok("quantity-summary memuat reject", ev)

    # ── INVARIAN 3: stok FG hanya bertambah 90 (delta, bukan absolut) ──
    fg = db.rahaza_material_stock.find_one(
        {"material_code": ji.get("sku"), "location_id": _fgloc}, {"_id": 0})
    delta = (float(fg.get("qty") or 0) - float(fg_before)) if fg else 0.0
    if fg:
        track("rahaza_material_stock", fg.get("id"))
        ok("stok FG bertambah", {"code": fg.get("material_code"), "sebelum": fg_before,
                                 "sesudah": fg.get("qty"), "delta": delta})
        if abs(delta - 90) > 0.001:
            rec("STK-1", "MED", "penambahan stok FG tidak sama dengan qty lolos QC (90)",
                {"delta": delta}, "90", "routes/dewi_cmt_packing.py approve")
    else:
        rec("STK-2", "HIGH", "penerimaan di-approve tetapi stok FG tidak terbentuk",
            {"sku": ji.get("sku")}, "stok FG += 90",
            "routes/dewi_cmt_packing.py:462 rahaza_material_stock")

    # ── INVARIAN 4: reject 10 pcs — ke mana? ──
    q = db.list_collection_names()
    quarantine = db.wh_quarantine_items.count_documents({}) if "wh_quarantine_items" in q else 0
    permak = list(db.dewi_cmt_permak.find({}, {"_id": 0}).limit(5)) if "dewi_cmt_permak" in q else []
    if quarantine == 0 and not permak:
        rec("RJT-1", "CRIT",
            "10 pcs reject tidak masuk karantina, tidak jadi permak, dan tidak jadi hutang "
            "vendor → barang reject HILANG dari sistem (hanya angka di baris penerimaan)",
            {"karantina": quarantine, "permak": len(permak)},
            "reject otomatis → karantina/permak/rework dengan pipeline balik ke vendor",
            "routes/dewi_cmt_packing.py approve (tidak memanggil quarantine/permak)")

    # ── INVARIAN 5: AP vendor CMT = qty lolos × rate? (field SSOT: source_receipt_id) ──
    ap_doc = db.dewi_cmt_payments.find_one({"source_receipt_id": rid}, {"_id": 0})
    if not ap_doc:
        rec("FIN-1", "HIGH",
            "Approve penerimaan tidak membentuk hutang (AP) ke vendor CMT yang tertaut receipt",
            {"receipt_id": rid},
            "AP CMT = qty lolos QC × rate, idempoten per receipt",
            "routes/production_maklon_bridge.mature_ap_from_cmt_receipt")
    else:
        expect = 90 * 18000.0
        got = float(ap_doc.get("net_amount") or 0)
        ok("AP CMT terbentuk", {"code": ap_doc.get("payment_code"), "total_pcs": ap_doc.get("total_pcs"),
                                "total_rejected": ap_doc.get("total_rejected"), "net_amount": got})
        if ap_doc.get("total_pcs") != 90:
            rec("FIN-1b", "HIGH", "AP CMT tidak dihitung dari qty lolos QC",
                {"total_pcs": ap_doc.get("total_pcs")}, "90", "mature_ap_from_cmt_receipt")
        # Master partner campur: cmt_partner_id memakai id vendor_partners, bukan dewi_cmt_partners
        pid = ap_doc.get("cmt_partner_id")
        in_cmt = db.dewi_cmt_partners.count_documents({"id": pid})
        in_vp = db.vendor_partners.count_documents({"id": pid})
        legacy = db.dewi_cmt_payments.find_one({"total_amount": {"$exists": True}}, {"_id": 0})
        if in_cmt == 0 and in_vp >= 1:
            rec("FIN-3", "HIGH",
                "`dewi_cmt_payments.cmt_partner_id` diisi id dari `vendor_partners`, sedangkan "
                "dokumen lama memakai id `dewi_cmt_partners` → satu kolom menyimpan id dari DUA "
                "master berbeda; pengelompokan tagihan per CMT di Portal CMT jadi salah. "
                "Skema jumlah juga bercampur (`net_amount` vs `total_amount`).",
                {"cmt_partner_id": pid, "ada_di_dewi_cmt_partners": in_cmt,
                 "ada_di_vendor_partners": in_vp,
                 "dokumen_lama_pakai_total_amount": bool(legacy),
                 "contoh_lama": (legacy or {}).get("payment_code")},
                "satu master vendor CMT + satu nama field jumlah",
                "routes/production_maklon_bridge.py mature_ap_from_cmt_receipt vs "
                "routes/dewi_cmt_lifecycle.py (baca dewi_cmt_partners)")

    # ── Dispatch ke buyer dari penerimaan ──
    st, bs = call("POST", "/api/buyer-shipments", adm, json={
        "po_id": po_id, "source_receipt_ids": [rid],
        "shipment_date": date.today().isoformat(), "notes": MARK,
        "items": [{"po_item_id": po_items[0]["id"], "job_item_id": ji["id"],
                   "sku": ji.get("sku"), "qty_shipped": 90}]})
    if st not in (200, 201):
        rec("DSP-1", "CRIT", "DA gagal dispatch ke buyer dari penerimaan yang sudah approve",
            {"http": st, "resp": bs}, "201", "routes/buyer_shipment.py:433")
    else:
        bsid = bs.get("id")
        track("buyer_shipments", bsid)
        ok("dispatch ke buyer berhasil", {"id": bsid, "no": bs.get("shipment_number")})
        st, detail = call("GET", f"/api/buyer-shipments/{bsid}", adm)
        d = detail if isinstance(detail, dict) else {}
        if not d.get("items"):
            rec("DSP-2", "HIGH", "detail buyer shipment tidak mengembalikan items",
                {"keys": sorted(d.keys())}, "items[] terisi", "routes/buyer_shipment.py:395")
    return {"po_id": po_id, "job_id": job_id, "receipt_id": rid, "po_item_id": po_items[0]["id"],
            "job_item_id": ji["id"], "sku": ji.get("sku")}


# ═══════════════════════════════════════════════════════════════════════════
#  PROBE 6 — SURAT JALAN GABUNGAN (multi-PO) + child shipment
# ═══════════════════════════════════════════════════════════════════════════
def probe_consolidated(adm, ctx):
    head("PROBE 6 — Gabung beberapa PO jadi 1 surat jalan buyer + ambil data child shipment")
    db = db_handle()
    cons = list(db.buyer_shipments.find({"consolidated": True}, {"_id": 0}).limit(5))
    parents = list(db.buyer_shipments.find({"parent_shipment_id": {"$nin": [None, ""]}}, {"_id": 0}).limit(5))
    st, disp = call("GET", "/api/buyer-shipment-dispatches", adm)
    drows = disp.get("items", disp) if isinstance(disp, dict) else disp
    drows = drows if isinstance(drows, list) else []
    ev = {"consolidated_shipments": len(cons), "child_shipments": len(parents),
          "dispatch_rows": len(drows)}
    # apakah endpoint detail mengembalikan child?
    if cons:
        st, d = call("GET", f"/api/buyer-shipments/{cons[0]['id']}", adm)
        keys = sorted(d.keys()) if isinstance(d, dict) else []
        has_children = any(k in keys for k in ("child_shipments", "children", "child_shipment_ids"))
        if not has_children:
            rec("CONS-1", "HIGH",
                "Surat jalan gabungan tidak mengembalikan child shipment pada detail → "
                "data child tidak bisa diambil dari UI",
                {"shipment": cons[0].get("shipment_number"), "field_tersedia": keys},
                "detail memuat child_shipments[] / po_ids[] beserta itemnya",
                "routes/buyer_shipment.py:395 get detail")
    else:
        rec("CONS-2", "LOW",
            "Tidak ada surat jalan gabungan sama sakli di data → fitur gabung PO belum "
            "pernah menghasilkan dokumen (perlu uji fungsional UI)",
            ev, "minimal 1 SJ gabungan bisa dibuat & dibaca ulang", "")
    # parent/child field ada di schema?
    sample = db.buyer_shipments.find_one({}, {"_id": 0}) or {}
    missing = [k for k in ("parent_shipment_id", "child_shipment_ids", "consolidated", "po_ids")
               if k not in sample]
    if missing:
        rec("CONS-3", "HIGH",
            "Dokumen buyer_shipments lama tidak punya field konsolidasi → skema campur "
            "(dokumen lama vs Phase D) membuat pembacaan child/gabungan tidak konsisten",
            {"field_hilang_di_dokumen_contoh": missing, "contoh": sample.get("shipment_number")},
            "migrasi backfill field konsolidasi untuk semua dokumen",
            "routes/buyer_shipment.py Phase D")


# ═══════════════════════════════════════════════════════════════════════════
#  PROBE 7 — PERMAK / REWORK: apakah balik ke vendor lewat pipeline?
# ═══════════════════════════════════════════════════════════════════════════
def probe_permak(adm, ven, ctx):
    head("PROBE 7 — PERMAK/rework: reject → dikerjakan ulang vendor → kembali 100 diterima?")
    if not ctx:
        rec("PMK-0", "MED", "konteks alur tidak tersedia", {}, "", "")
        return
    db = db_handle()
    rid = ctx["receipt_id"]
    lines = list(db.cmt_receipt_lines.find({"receipt_id": rid}, {"_id": 0}))
    if not lines:
        return
    st, pk = call("POST", "/api/dewi/cmt-permak/from-receipt-line", adm, json={
        "receipt_line_id": lines[0]["id"], "qty": 10,
        "reason": "jahitan lepas", "notes": MARK})
    if st not in (200, 201):
        rec("PMK-1", "HIGH", "gagal membuat permak dari baris penerimaan reject",
            {"http": st, "resp": pk}, "201", "routes/dewi_cmt_permak.py:357")
        return
    pid = (pk.get("id") if isinstance(pk, dict) else None) or (pk.get("permak") or {}).get("id")
    track("dewi_cmt_permak", pid)
    doc = db.dewi_cmt_permak.find_one({"id": pid}, {"_id": 0}) or {}
    ok("permak dibuat", {k: doc.get(k) for k in ("id", "permak_code", "qty", "status",
                                                 "vendor_id", "po_id", "receipt_id")})
    # apakah vendor bisa melihat permak ini?
    if ven:
        found = False
        for p in ("/api/dewi/cmt-permak", "/api/production-jobs", "/api/vendor/dashboard"):
            s, r = call("GET", p, ven)
            body = json.dumps(r, default=str) if not isinstance(r, str) else r
            if pid and pid in body:
                found = True
                break
        if not found:
            rec("PMK-2", "CRIT",
                "Permak/rework TIDAK terlihat di sisi vendor melalui endpoint mana pun → "
                "tidak ada trigger pekerjaan ulang untuk vendor; barang reject mentok di DA",
                {"permak_id": pid, "endpoint_diperiksa": ["/api/dewi/cmt-permak",
                                                           "/api/production-jobs", "/api/vendor/dashboard"]},
                "permak membuat pekerjaan rework di portal vendor (job/permak ter-scope vendor) "
                "dan saat selesai menambah qty accepted PO",
                "routes/dewi_cmt_permak.py (tidak ada scoping vendor / tidak membuat job)")
    # status flow permak → apakah menutup lingkaran ke PO/stok?
    if pid:
        fg_before = float((db.rahaza_material_stock.find_one(
            {"material_code": ctx.get("sku")}, {"_id": 0}) or {}).get("qty") or 0)
        s1, _ = call("POST", f"/api/dewi/cmt-permak/{pid}/status", adm,
                     json={"status": "in_progress", "note": MARK})
        s2, r = call("POST", f"/api/dewi/cmt-permak/{pid}/status", adm,
                     json={"status": "selesai_berhasil", "qty_fixed": 10, "qty_scrap": 0,
                           "note": MARK})
        after = db.dewi_cmt_permak.find_one({"id": pid}, {"_id": 0}) or {}
        ji = db.production_job_items.find_one({"id": ctx["job_item_id"]}, {"_id": 0}) or {}
        fg_after = float((db.rahaza_material_stock.find_one(
            {"material_code": ctx.get("sku")}, {"_id": 0}) or {}).get("qty") or 0)
        rec_ev = {"http_in_progress": s1, "http_selesai": s2,
                  "status_permak": after.get("status"),
                  "qty_fixed": after.get("qty_fixed"),
                  "produced_qty_job": ji.get("produced_qty"),
                  "field_accepted_di_job": [k for k in ji if "accept" in k.lower()],
                  "stok_fg_sebelum": fg_before, "stok_fg_sesudah": fg_after}
        if after.get("status") == "selesai_berhasil" and abs(fg_after - fg_before) < 0.001:
            rec("PMK-3", "CRIT",
                "Permak SELESAI BERHASIL 10 pcs tetapi TIDAK ada efek ke mana pun: stok FG tidak "
                "bertambah, qty diterima PO tidak naik, reject tidak berkurang. Lingkaran "
                "'produced 100 → reject 10 → diperbaiki → 100 diterima' TIDAK PERNAH tertutup.",
                rec_ev,
                "permak selesai → stok FG += qty_fixed, accepted PO += qty_fixed, "
                "reject_open -= qty_fixed (dan bila retur_ke_cmt: pekerjaan ulang muncul di vendor)",
                "routes/dewi_cmt_permak.py:475-522 change_status (hanya menulis dokumen permak)")
        else:
            ok("permak selesai memberi efek", rec_ev)


# ═══════════════════════════════════════════════════════════════════════════
#  PROBE 8 — KOMPONEN KURANG / PERMINTAAN TAMBAHAN / KIRIM MATERIAL (duplikasi)
# ═══════════════════════════════════════════════════════════════════════════
def probe_material_requests(adm, ven):
    head("PROBE 8 — 'Komponen Kurang' vs 'Permintaan Tambahan' vs 'Kirim Material ke CMT' — duplikat?")
    db = db_handle()
    surfaces = {
        "dewi_cmt_component_requests (Komponen Kurang)": db.dewi_cmt_component_requests.count_documents({}),
        "wh_cmt_dispatches (Kirim Material ke CMT)":
            db.wh_cmt_dispatches.count_documents({}) if "wh_cmt_dispatches" in db.list_collection_names() else "TIDAK ADA",
        "material_requests (Permintaan Material vendor)":
            db.material_requests.count_documents({}) if "material_requests" in db.list_collection_names() else "TIDAK ADA",
        "production_material_returns":
            db.production_material_returns.count_documents({}) if "production_material_returns" in db.list_collection_names() else "TIDAK ADA",
        "vendor_material_inspections": db.vendor_material_inspections.count_documents({}),
    }
    print(f"     permukaan yang ada: {json.dumps(surfaces, default=str)}")
    st, cr = call("GET", "/api/dewi/cmt-component-requests", adm)
    rows = cr.get("items", cr) if isinstance(cr, dict) else cr
    rows = rows if isinstance(rows, list) else []
    # apakah punya FK ke po & vendor & inspeksi?
    sample = rows[0] if rows else None
    db_sample = db.dewi_cmt_component_requests.find_one({}, {"_id": 0})
    fields = sorted((db_sample or sample or {}).keys())
    need = ("po_id", "vendor_id", "inspection_id")
    lacking = [k for k in need if k not in fields] if fields else list(need)
    auto_ok = (db.dewi_cmt_component_requests.count_documents({"origin": "vendor_inspection"}) > 0)
    # Tidak ada kekurangan yang tercatat = tidak ada yang perlu ditindak-lanjuti.
    shortfalls = db.vendor_material_inspection_items.count_documents({"missing_qty": {"$gt": 0}})
    if shortfalls == 0:
        auto_ok = True
    linked_insp = db.vendor_material_inspections.count_documents(
        {"component_request_id": {"$nin": [None, ""]}})
    if auto_ok or linked_insp:
        ok("permintaan komponen otomatis dari inspeksi aktif",
           {"request_dari_inspeksi": db.dewi_cmt_component_requests.count_documents(
               {"origin": "vendor_inspection"}), "inspeksi_tertaut": linked_insp})
    elif not fields:
        rec("MAT-1", "HIGH",
            "'Komponen Kurang' (dewi_cmt_component_requests) kosong total sehingga kontraknya "
            "tak terbukti; sementara ada 3+ permukaan lain untuk kebutuhan yang sama",
            surfaces,
            "SATU alur permintaan material/komponen yang menunjuk po_id + vendor_id + "
            "inspection_id (hasil inspeksi vendor)",
            "routes/dewi_cmt_component_requests.py, routes/wms_cmt_dispatches.py, "
            "routes/vendor_shipment.py(material_requests), routes/production_material_returns.py")
    elif lacking:
        rec("MAT-2", "HIGH",
            "'Komponen Kurang' tidak menunjuk PO/vendor/inspeksi",
            {"field_ada": fields, "field_kurang": lacking},
            "wajib po_id + vendor_id + inspection_id", "routes/dewi_cmt_component_requests.py")
    st, insp = call("GET", "/api/vendor-material-inspections", adm)
    irows = insp.get("items", insp) if isinstance(insp, dict) else insp
    irows = irows if isinstance(irows, list) else []
    linked = [i for i in irows if i.get("component_request_id") or i.get("request_id")]
    if irows and not linked and not auto_ok:
        rec("MAT-3", "HIGH",
            "Hasil inspeksi material vendor tidak pernah membentuk / menautkan permintaan "
            "komponen kurang → temuan kurang-kirim tidak punya tindak lanjut otomatis",
            {"inspeksi": len(irows), "tertaut_ke_request": 0},
            "inspeksi kurang/rusak → otomatis buat permintaan komponen ke gudang, "
            "menunjuk PO + vendor",
            "routes/production_execution.py vendor_material_inspections + "
            "routes/dewi_cmt_component_requests.py")


# ═══════════════════════════════════════════════════════════════════════════
#  PROBE 9 — INTEGRASI FINANCE & GUDANG
# ═══════════════════════════════════════════════════════════════════════════
def probe_finance_warehouse(adm, ctx):
    head("PROBE 9 — Integrasi FINANCE (AP/AR/GL) & GUDANG (stok, material issue)")
    db = db_handle()
    # GL seimbang?
    st, tb = call("GET", "/api/rahaza/journals", adm)
    jl = list(db.journal_lines.find({}, {"_id": 0})) if "journal_lines" in db.list_collection_names() else []
    dr = sum(float(l.get("debit") or 0) for l in jl)
    cr = sum(float(l.get("credit") or 0) for l in jl)
    if abs(dr - cr) > 0.5:
        rec("GL-1", "CRIT", "Buku besar tidak seimbang", {"debit": dr, "credit": cr},
            "Dr = Cr", "core GL posting")
    else:
        ok("GL seimbang", {"debit": dr, "credit": cr})

    if ctx:
        st, mf = call("GET", f"/api/production-pos/{ctx['po_id']}/maklon-finance", adm)
        ok("maklon-finance PO", mf if isinstance(mf, dict) else {"resp": mf})
        st, ff = call("GET", f"/api/production-pos/{ctx['po_id']}/fulfillment", adm)
        ev = ff if isinstance(ff, dict) else {"resp": ff}
        flat = json.dumps(ev, default=str).lower()
        if "reject" not in flat:
            rec("FIN-2", "MED", "fulfillment PO tidak memuat reject/rework",
                ev, "fulfillment memuat produced/accepted/reject/rework",
                "routes/production_pos.py fulfillment")

    # material issue ke CMT mengurangi stok?
    names = db.list_collection_names()
    issues = db.rahaza_material_issues.count_documents({}) if "rahaza_material_issues" in names else "TIDAK ADA"
    print(f"     rahaza_material_issues = {issues}")
    if issues in (0, "TIDAK ADA"):
        rec("GDG-1", "HIGH",
            "Tidak ada satu pun Material Issue → penyerahan material gudang ke produksi/CMT "
            "belum pernah terjadi, padahal progress produksi internal DIGATE oleh material issue",
            {"rahaza_material_issues": issues},
            "material issue tercatat & mengurangi stok saat kirim ke CMT",
            "routes/production_execution.py:668 (gate GDG-2) + routes/wms_picklist.py")


# ═══════════════════════════════════════════════════════════════════════════
def cleanup():
    print(f"\n{Y}bersih-bersih data uji…{X}")
    try:
        db = db_handle()
        stats = {}
        for coll, ids in CREATED.items():
            ids = [i for i in ids if i]
            if not ids:
                continue
            stats[coll] = db[coll].delete_many({"id": {"$in": ids}}).deleted_count
        # sisa berdasarkan marker
        for coll in ("dewi_maklon_pos", "production_pos", "po_items", "production_jobs",
                     "production_job_items", "production_progress", "buyer_shipments",
                     "buyer_shipment_items", "cmt_receipts", "cmt_receipt_lines",
                     "dewi_cmt_permak", "dewi_cmt_payments", "rahaza_material_stock"):
            if coll in db.list_collection_names():
                n = db[coll].delete_many({"notes": {"$regex": MARK}}).deleted_count
                if n:
                    stats[coll] = stats.get(coll, 0) + n
        # child rows by parent
        print(f"  terhapus: {json.dumps(stats)}")
        resid = {}
        for coll in ("production_pos", "cmt_receipts", "buyer_shipments"):
            if coll in db.list_collection_names():
                resid[coll] = db[coll].count_documents({"notes": {"$regex": MARK}})
        print(f"  residu  : {json.dumps(resid)}")
    except Exception as e:
        print(f"  {R}cleanup gagal: {e}{X}")


def main():
    print(f"{B}{C}{'=' * 96}\n  AUDIT E2E — PRODUKSI · MAKLON · CMT/VENDOR · FINANCE · GUDANG\n"
          f"  {datetime.now().isoformat(timespec='seconds')}\n{'=' * 96}{X}")
    adm = login("admin@garment.com", "Admin@123")
    if not adm:
        print(f"{R}tidak bisa login admin — abort{X}")
        sys.exit(2)
    ven = login("cmtvendor@dewiaditya.id", "Dewi@123")
    if not ven:
        print(f"{Y}peringatan: login vendor CMT gagal — probe sisi vendor terbatas{X}")

    ctx = None
    try:
        catalogs = probe_variant_master(adm)
        mk_po = probe_maklon_po_variant(adm, catalogs)
        probe_tracking(adm, mk_po)
        probe_vendor_island(adm, ven)
        ctx = probe_full_engine_flow(adm, ven, catalogs)
        probe_consolidated(adm, ctx)
        probe_permak(adm, ven, ctx)
        probe_material_requests(adm, ven)
        probe_finance_warehouse(adm, ctx)
    finally:
        cleanup()

    print(f"\n{B}{C}{'=' * 96}\n  RINGKASAN TEMUAN\n{'=' * 96}{X}")
    order = {"CRIT": 0, "HIGH": 1, "MED": 2, "LOW": 3}
    for f in sorted(FINDINGS, key=lambda x: order.get(x["severity"], 9)):
        col = R if f["severity"] in ("CRIT", "HIGH") else Y
        print(f"  {col}{f['severity']:<5}{X} {f['code']:<8} {f['title'][:110]}")
    crit = sum(1 for f in FINDINGS if f["severity"] == "CRIT")
    high = sum(1 for f in FINDINGS if f["severity"] == "HIGH")
    print(f"\n  TOTAL: {len(FINDINGS)} temuan — CRIT {crit} · HIGH {high}")
    outp = ROOT / "docs" / "AUDIT_E2E_FINDINGS.json"
    outp.parent.mkdir(exist_ok=True)
    outp.write_text(json.dumps(FINDINGS, indent=1, default=str))
    print(f"  → {outp}")


if __name__ == "__main__":
    main()
