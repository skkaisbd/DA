#!/usr/bin/env python3
"""Seed IDEMPOTEN — data demo **perbandingan antar-pekan Rekap Mingguan CMT** (F12).

MENGAPA BERKAS INI ADA
----------------------
Panel "Bandingkan pekan lalu" hanya bisa dinilai kalau ada vendor yang benar-benar
**berubah arah** antara dua jendela 7 hari. Environment hasil `bootstrap.sh` hanya
punya satu vendor CMT dengan setoran di pekan berjalan, sehingga:

  · papan "vendor yang bergerak" selalu kosong / hanya berisi satu nama;
  · aturan "hari terlambat menang atas pcs" tidak pernah kelihatan bekerja;
  · aturan kejujuran "vendor tanpa pekerjaan di salah satu pekan TIDAK
    diperingkat" tidak punya contoh, padahal justru itu yang paling mudah salah.

Skrip ini membuat EMPAT vendor yang sengaja berbeda arahnya, sehingga layar dan
lampiran bisa diperiksa apa adanya:

  A. **CV Sinar Membaik (WCMBK)** — pekan lalu hampir selalu bolong, pekan ini
     penuh setoran+kiriman ⇒ harus muncul di daftar **MEMBAIK** (hari terlambat
     turun banyak).
  B. **CV Surya Memburuk (WCMBR)** — pekan lalu rapi tiap hari, pekan ini berhenti
     total ⇒ harus muncul paling atas di daftar **MEMBURUK**.
  C. **CV Tetap Stabil (WCSTB)** — pola pekan ini PERSIS sama dengan pekan lalu
     (hari yang sama, pcs yang sama) ⇒ harus dihitung **SAMA**, bukan naik/turun.
  D. **CV Baru Masuk (WCBRU)** — job-nya baru lahir di pekan ini saja ⇒ harus
     **TIDAK diperingkat** dengan alasan yang tertulis, bukan dipuji sebagai
     "paling membaik" hanya karena pekan lalu angkanya 0.

CARA DATANYA DIBUAT — dan apa yang TIDAK dipalsukan
---------------------------------------------------
Seluruh setoran & kiriman dibuat lewat **API sungguhan** dengan `progress_date` /
`shipment_date` yang memang lampau, jadi penomoran dokumen, jejak aktivitas, dan
turunan uangnya lahir sama seperti dipakai staf.

Satu-satunya hal yang ditulis langsung ke Mongo adalah **`created_at` job** ("kapan
job ini lahir"). Alasannya sama dengan POC `test_core_rekap_harian.py`: server
TIDAK menyediakan jalan untuk membuka job bertanggal lampau — dan tanpa job yang
sudah hidup di pekan sebelumnya, kedua jendela tidak punya "hari yang ada
pekerjaannya", sehingga yang diuji justru hilang. Perilaku yang diuji (kapan hari
dianggap terlambat/beres) tetap dihitung backend dari data asli.

Sifat:
  · IDEMPOTEN — dicek per kode vendor & nomor dokumen; dijalankan berulang tidak
    menggandakan setoran (progress dicek per tanggal per job item);
  · `--cleanup` membuang SELURUH jejaknya, termasuk turunan uang (AR invoice
    maklon + mirror `dewi_maklon_pos`) supaya tidak meninggalkan piutang palsu.

Pakai:
    python3 /app/scripts/seed_cmt_weekly_compare_demo.py
    python3 /app/scripts/seed_cmt_weekly_compare_demo.py --cleanup
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

import requests

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
API = f"{BASE}/api"
CLEANUP = "--cleanup" in sys.argv

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

TAG = "seed_cmt_weekly_compare_demo"
WIB = timezone(timedelta(hours=7))

G, R, Y, C, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[0m"


def ok(m): print(f"  {G}✓{X} {m}")
def warn(m): print(f"  {Y}!{X} {m}")
def err(m): print(f"  {R}✗{X} {m}")
def hdr(m): print(f"\n{C}▶ {m}{X}")


def today_wib() -> date:
    return datetime.now(WIB).date()


D0 = today_wib()


def ago(n: int) -> str:
    return (D0 - timedelta(days=n)).isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# POLA — offset hari dihitung dari HARI INI (0 = hari ini).
#   jendela berjalan  : offset 6 … 0
#   jendela sebelumnya: offset 13 … 7
# Pola dibuat SIMETRIS (offset k ↔ k+7) supaya "stabil" benar-benar stabil dan
# bukan kebetulan.
# ═══════════════════════════════════════════════════════════════════════════
VENDORS = [
    {
        "code": "WCMBK", "name": "CV Sinar Membaik",
        "expect": "MEMBAIK — hari terlambat turun tajam",
        # pekan lalu: cuma 1 hari terisi (6 hari bolong) · pekan ini: penuh
        "prev_days": [13],
        "cur_days": [6, 5, 4, 3, 2, 1, 0],
        "qty": 12,
    },
    {
        "code": "WCMBR", "name": "CV Surya Memburuk",
        "expect": "MEMBURUK — pekan lalu rapi, pekan ini berhenti total",
        "prev_days": [13, 12, 11, 10, 9, 8, 7],
        "cur_days": [],
        "qty": 12,
    },
    {
        "code": "WCSTB", "name": "CV Tetap Stabil",
        "expect": "SAMA — pola & pcs identik dengan pekan lalu",
        "prev_days": [12, 10, 8],
        "cur_days": [5, 3, 1],
        "qty": 10,
    },
    {
        "code": "WCBRU", "name": "CV Baru Masuk",
        "expect": "TIDAK DIPERINGKAT — pekan lalu belum punya pekerjaan",
        "prev_days": [],
        "cur_days": [4, 2],
        "qty": 15,
        # Job-nya lahir di jendela BERJALAN saja ⇒ pekan lalu days_with_work = 0.
        "job_born_offset": 5,
    },
]

DEFAULT_JOB_BORN_OFFSET = 16   # job lahir sebelum kedua jendela


def login() -> str:
    r = requests.post(f"{API}/auth/login", timeout=30,
                      json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    return r.json()["token"]


# `X-CMT-Override-Vendor` adalah pintu resmi "staf DA mengisikan data vendor yang
# tidak memakai sistem" — jalur yang MEMANG dipakai fitur ini. Memakainya di
# seeder membuat jejak audit (`override_*`) lahir sama seperti dipakai staf,
# bukan data yang muncul entah dari mana.
OVERRIDE_HEADER = "X-CMT-Override-Vendor"


def H(tok, vendor=None):
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    if vendor:
        h[OVERRIDE_HEADER] = vendor
    return h


def get_db():
    from pymongo import MongoClient
    return MongoClient(MONGO_URL)[DB_NAME]


def po_number(code): return f"PO-WCMP-{code}"
def sj_number(code): return f"SJ-WCMP-{code}"


# ═══════════════════════════════════════════════════════════════════════════
def do_cleanup() -> int:
    print("Membersihkan data demo perbandingan mingguan CMT…")
    db = get_db()
    codes = [v["code"] for v in VENDORS]
    vids = [v["id"] for v in db.vendor_partners.find({"code": {"$in": codes}}, {"_id": 0, "id": 1})]
    pos = [p["id"] for p in db.production_pos.find(
        {"po_number": {"$in": [po_number(c) for c in codes]}}, {"_id": 0, "id": 1})]
    ships = [s["id"] for s in db.vendor_shipments.find(
        {"vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
    jobs = [j["id"] for j in db.production_jobs.find(
        {"vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
    insps = [i["id"] for i in db.vendor_material_inspections.find(
        {"vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
    bss = [b["id"] for b in db.buyer_shipments.find(
        {"vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
    rcvs = [c["id"] for c in db.cmt_receipts.find(
        {"cmt_vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []

    ops = [
        ("production_progress", {"job_id": {"$in": jobs}}),
        ("production_job_items", {"job_id": {"$in": jobs}}),
        ("production_jobs", {"id": {"$in": jobs}}),
        ("vendor_material_inspection_items", {"inspection_id": {"$in": insps}}),
        ("vendor_material_inspections", {"id": {"$in": insps}}),
        ("vendor_shipment_items", {"shipment_id": {"$in": ships}}),
        ("accessory_shipment_items", {"shipment_id": {"$in": ships}}),
        ("vendor_shipments", {"id": {"$in": ships}}),
        ("material_requests", {"vendor_id": {"$in": vids}}),
        ("production_variances", {"vendor_id": {"$in": vids}}),
        ("reminders", {"vendor_id": {"$in": vids}}),
        ("dewi_cmt_component_requests", {"vendor_id": {"$in": vids}}),
        ("buyer_shipment_items", {"shipment_id": {"$in": bss}}),
        ("buyer_shipments", {"id": {"$in": bss}}),
        ("cmt_receipt_lines", {"receipt_id": {"$in": rcvs}}),
        ("cmt_receipts", {"id": {"$in": rcvs}}),
        ("dewi_cmt_payments", {"vendor_id": {"$in": vids}}),
        ("po_accessories", {"po_id": {"$in": pos}}),
        ("po_items", {"po_id": {"$in": pos}}),
        ("dewi_maklon_bom", {"po_id": {"$in": pos}}),
        ("rahaza_ar_invoices", {"linked_maklon_po_id": {"$in": pos}}),
        ("dewi_maklon_pos", {"production_po_id": {"$in": pos}}),
        ("production_pos", {"id": {"$in": pos}}),
        ("vendor_partners", {"id": {"$in": vids}}),
    ]
    total = 0
    for coll, q in ops:
        try:
            n = db[coll].delete_many(q).deleted_count
            if n:
                total += n
                print(f"    - {coll}: {n}")
        except Exception as e:  # noqa: BLE001
            warn(f"{coll}: {e}")
    ok(f"{total} dokumen demo dihapus")
    return 0


# ═══════════════════════════════════════════════════════════════════════════
def ensure_vendor(db, h, spec) -> str:
    existing = db.vendor_partners.find_one({"code": spec["code"]}, {"_id": 0, "id": 1})
    if existing:
        return existing["id"]
    r = requests.post(f"{API}/vendor-portal/partners", headers=h, timeout=30, json={
        "name": spec["name"], "code": spec["code"],
        "contact_name": "Bagian Produksi", "contact_phone": "0271-111222",
        "address": "Sragen, Jawa Tengah",
        "notes": f"Demo perbandingan mingguan — {spec['expect']} [{TAG}]",
        "capacity_pcs": 250, "capacity_note": "1 lini jahit",
    })
    if r.status_code not in (200, 201):
        raise RuntimeError(f"vendor {spec['code']}: HTTP {r.status_code} {r.text[:180]}")
    return r.json()["id"]


def ensure_po(db, h, spec, vid) -> str:
    num = po_number(spec["code"])
    doc = db.production_pos.find_one({"po_number": num}, {"_id": 0, "id": 1})
    if doc:
        return doc["id"]
    deadline = (D0 + timedelta(days=14)).isoformat()
    r = requests.post(f"{API}/production-pos", headers=h, timeout=60, json={
        "po_number": num, "business_type": "maklon", "vendor_id": vid,
        "customer_name": "PT Buyer Demo Mingguan", "status": "Confirmed",
        "po_date": ago(DEFAULT_JOB_BORN_OFFSET + 2), "deadline": deadline,
        "delivery_deadline": deadline,
        "notes": f"PO demo perbandingan mingguan CMT [{TAG}]",
        "items": [
            {"product_name": "Kaos Demo Mingguan", "sku": f"WCMP-{spec['code']}-M",
             "size": "M", "color": "Hitam", "color_code": "BLK", "qty": 200,
             "serial_number": f"SN-WCMP-{spec['code']}-1", "cmt_price_snapshot": 9500},
            {"product_name": "Kaos Demo Mingguan", "sku": f"WCMP-{spec['code']}-L",
             "size": "L", "color": "Hitam", "color_code": "BLK", "qty": 100,
             "serial_number": f"SN-WCMP-{spec['code']}-2", "cmt_price_snapshot": 9500},
        ]})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"PO {num}: HTTP {r.status_code} {r.text[:200]}")
    return r.json()["id"]


def ensure_shipment(db, h, spec, vid, po_id) -> str:
    num = sj_number(spec["code"])
    doc = db.vendor_shipments.find_one({"shipment_number": num}, {"_id": 0, "id": 1})
    if doc:
        return doc["id"]
    items = list(db.po_items.find({"po_id": po_id}, {"_id": 0, "id": 1, "qty": 1}))
    r = requests.post(f"{API}/vendor-shipments", headers=h, timeout=60, json={
        "shipment_number": num, "vendor_id": vid, "po_id": po_id,
        "shipment_type": "NORMAL", "shipment_date": ago(DEFAULT_JOB_BORN_OFFSET + 1),
        "notes": f"Kirim material demo perbandingan mingguan [{TAG}]",
        "items": [{"po_id": po_id, "po_item_id": it["id"], "qty_sent": it["qty"]}
                  for it in items]})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"SJ {num}: HTTP {r.status_code} {r.text[:200]}")
    return r.json()["id"]


def ensure_inspection(db, tok, vid, ship_id):
    # Barang harus DITERIMA dulu (status `Received`) sebelum bisa diinspeksi, dan
    # inspeksi harus selesai sebelum job bisa dibuka. Urutan ini bukan formalitas:
    # itu rantai yang sama yang dipakai staf di layar, dan `received_at` ditulis
    # SERVER (nilai dari klien diabaikan).
    ship = db.vendor_shipments.find_one({"id": ship_id}, {"_id": 0, "status": 1})
    if (ship or {}).get("status") != "Received":
        r0 = requests.put(f"{API}/vendor-shipments/{ship_id}", headers=H(tok, vid), timeout=60,
                          json={"status": "Received", "vendor_id": vid})
        if r0.status_code != 200:
            warn(f"tandai diterima gagal: HTTP {r0.status_code} {r0.text[:160]}")

    if db.vendor_material_inspections.find_one({"shipment_id": ship_id}, {"_id": 0, "id": 1}):
        return
    items = list(db.vendor_shipment_items.find({"shipment_id": ship_id}, {"_id": 0}))
    if not items:
        warn("tidak ada baris surat jalan — inspeksi dilewati")
        return
    r = requests.post(f"{API}/vendor-material-inspections", headers=H(tok, vid), timeout=60, json={
        "shipment_id": ship_id, "vendor_id": vid,
        "items": [{"shipment_item_id": si["id"], "sku": si.get("sku", ""),
                   "product_name": si.get("product_name", ""),
                   "size": si.get("size", ""), "color": si.get("color", ""),
                   "ordered_qty": int(si.get("qty_sent", 0) or 0),
                   "received_qty": int(si.get("qty_sent", 0) or 0),
                   "missing_qty": 0, "condition_notes": "lengkap"}
                  for si in items],
        "overall_notes": f"Inspeksi demo perbandingan mingguan [{TAG}]"})
    if r.status_code not in (200, 201):
        warn(f"inspeksi gagal: HTTP {r.status_code} {r.text[:160]}")


def ensure_job(db, tok, spec, vid, ship_id) -> str:
    doc = db.production_jobs.find_one({"vendor_shipment_id": ship_id}, {"_id": 0, "id": 1})
    if doc:
        job_id = doc["id"]
    else:
        r = requests.post(f"{API}/production-jobs", headers=H(tok, vid), timeout=60, json={
            "vendor_shipment_id": ship_id, "vendor_id": vid,
            "notes": f"Job demo perbandingan mingguan — {spec['expect']} [{TAG}]"})
        if r.status_code not in (200, 201):
            raise RuntimeError(f"job {spec['code']}: HTTP {r.status_code} {r.text[:200]}")
        job_id = r.json()["id"]

    # SATU-SATUNYA penulisan langsung ke Mongo: "kapan job ini lahir".
    born = spec.get("job_born_offset", DEFAULT_JOB_BORN_OFFSET)
    db.production_jobs.update_one(
        {"id": job_id},
        {"$set": {"created_at": datetime.now(timezone.utc) - timedelta(days=born)}})
    return job_id


def fill_days(db, tok, spec, vid, po_id, job_id, days_offsets) -> int:
    """Setoran + kiriman bertanggal untuk tiap offset hari. Idempoten per tanggal."""
    items = list(db.production_job_items.find({"job_id": job_id}, {"_id": 0}))
    if not items:
        warn(f"{spec['code']}: job belum punya item — pengisian dilewati")
        return 0
    target = items[0]
    qty = int(spec["qty"])
    filled = 0
    for off in days_offsets:
        day_iso = ago(off)
        already = db.production_progress.find_one(
            {"job_item_id": target["id"], "progress_date": day_iso}, {"_id": 0, "id": 1})
        if already:
            continue
        r1 = requests.post(f"{API}/production-progress", headers=H(tok, vid), timeout=60, json={
            "job_item_id": target["id"], "vendor_id": vid, "progress_date": day_iso,
            "completed_quantity": qty, "notes": f"Setoran demo {day_iso} [{TAG}]"})
        if r1.status_code not in (200, 201):
            warn(f"{spec['code']} setoran {day_iso} gagal: HTTP {r1.status_code} {r1.text[:140]}")
            continue
        # Kiriman WAJIB bertanggal sama & sebesar setoran, kalau tidak hari-hari
        # SESUDAHNYA jadi merah ("pcs selesai belum dikirim") dan polanya rusak.
        r2 = requests.post(f"{API}/buyer-shipments", headers=H(tok, vid), timeout=60, json={
            "shipment_number": f"SJB-WCMP-{spec['code']}-{off}-{uuid.uuid4().hex[:4].upper()}",
            "job_id": job_id, "po_id": po_id, "vendor_id": vid, "shipment_date": day_iso,
            "notes": f"Kiriman demo {day_iso} [{TAG}]",
            "items": [{"po_item_id": target.get("po_item_id"), "sku": target.get("sku", ""),
                       "product_name": target.get("product_name", ""),
                       "size": target.get("size", ""), "color": target.get("color", ""),
                       "qty_shipped": qty}]})
        if r2.status_code not in (200, 201):
            warn(f"{spec['code']} kiriman {day_iso} gagal: HTTP {r2.status_code} {r2.text[:140]}")
            continue
        filled += 1
    return filled


# ═══════════════════════════════════════════════════════════════════════════
def main() -> int:
    if CLEANUP:
        return do_cleanup()

    try:
        tok = login()
    except Exception as e:  # noqa: BLE001
        err(f"login admin gagal: {e}")
        return 1
    h = H(tok)
    db = get_db()

    print(f"Seed demo PERBANDINGAN MINGGUAN CMT (F12) — hari ini {D0.isoformat()} WIB")
    print(f"  jendela berjalan  : {ago(6)} … {ago(0)}")
    print(f"  jendela sebelumnya: {ago(13)} … {ago(7)}")

    for spec in VENDORS:
        hdr(f"{spec['name']} ({spec['code']}) — {spec['expect']}")
        try:
            vid = ensure_vendor(db, h, spec)
            ok(f"vendor siap ({vid[:8]}…)")
            po_id = ensure_po(db, h, spec, vid)
            ok("PO maklon siap (300 pcs, 2 varian)")
            ship_id = ensure_shipment(db, h, spec, vid, po_id)
            ensure_inspection(db, tok, vid, ship_id)
            ok("surat jalan material + inspeksi siap")
            job_id = ensure_job(db, tok, spec, vid, ship_id)
            born = spec.get("job_born_offset", DEFAULT_JOB_BORN_OFFSET)
            ok(f"job jalan, dicatat lahir {born} hari lalu ({ago(born)})")
            n_prev = fill_days(db, tok, spec, vid, po_id, job_id, spec["prev_days"])
            n_cur = fill_days(db, tok, spec, vid, po_id, job_id, spec["cur_days"])
            ok(f"pengisian baru: pekan lalu {n_prev} hari · pekan ini {n_cur} hari "
               f"(target {len(spec['prev_days'])} / {len(spec['cur_days'])})")
        except Exception as e:  # noqa: BLE001
            err(f"{spec['code']} gagal: {e}")
            return 1

    # ── Verifikasi lewat API yang SAMA dengan layar ──────────────────────────
    hdr("Verifikasi: panggil endpoint yang dipakai layar (?compare=true)")
    r = requests.get(f"{API}/cmt-override/weekly-recap?compare=true", headers=h, timeout=120)
    if r.status_code != 200:
        err(f"weekly-recap?compare=true HTTP {r.status_code} {r.text[:200]}")
        return 1
    cmp_ = (r.json() or {}).get("comparison") or {}
    movers = cmp_.get("movers") or {}
    counts = movers.get("counts") or {}
    by_code = {v["vendor_code"]: v for v in (cmp_.get("per_vendor") or [])}
    print(f"  comparable={cmp_.get('comparable')}  counts={counts}")
    print("  MEMBURUK :", [f"{v['vendor_name']} ({v['days_late_diff']:+d} hari)"
                           for v in movers.get("worsened") or []])
    print("  MEMBAIK  :", [f"{v['vendor_name']} ({v['days_late_diff']:+d} hari)"
                           for v in movers.get("improved") or []])

    bad = []
    for spec in VENDORS:
        v = by_code.get(spec["code"])
        if not v:
            bad.append(f"{spec['code']} tidak muncul di per_vendor")
            continue
        print(f"    {spec['code']:6} arah={v['direction']:12} "
              f"terlambat {v['days_late_prev']}→{v['days_late_now']} "
              f"({v['days_late_diff']:+d}) · pcs {v['qty_prev']}→{v['qty_now']} "
              f"({v['qty_diff']:+d}) · kerja {v['days_with_work_prev']}/{v['days_with_work_now']}"
              + (f" · {v['incomparable_reason']}" if v.get("incomparable_reason") else ""))
    expect_dir = {"WCMBK": "better", "WCMBR": "worse", "WCSTB": "flat",
                  "WCBRU": "incomparable"}
    for code, want in expect_dir.items():
        got = (by_code.get(code) or {}).get("direction")
        if got != want:
            bad.append(f"{code}: arah={got}, seharusnya {want}")

    print()
    if bad:
        for b in bad:
            err(b)
        err("SELESAI dengan catatan — pola demo belum sesuai harapan (lihat di atas).")
        return 1
    ok("SELESAI. Semua arah vendor sesuai harapan.")
    print("    Buka Portal Produksi → 'Input Vendor CMT' → tab Mingguan → "
          "tombol 'Bandingkan pekan lalu'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
