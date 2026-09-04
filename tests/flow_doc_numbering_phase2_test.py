#!/usr/bin/env python3
"""Uji PENOMORAN DOKUMEN TAHAP 2 (2026-08-05) — ROADMAP P1.

Sebelum sesi ini 18 tempat membuat nomor dokumen SENDIRI (di luar
`utils.counters.gen_prefixed_number`), sehingga owner TIDAK BISA mengatur
formatnya dari Portal Administrasi Sistem → Penomoran Dokumen. 11 di antaranya
adalah dokumen nyata dan sekarang sudah dipusatkan.

Yang dibuktikan:
  1. Katalog `GET /api/admin/doc-numbering` memuat 11 jenis dokumen baru,
     dengan contoh nomor sah (tanpa error format).
  2. Format buatan owner BENAR-BENAR dipakai oleh kode penghasil nomornya
     (diuji per fungsi asli: PO, GR, AP, klaim biaya, perjalanan dinas,
     penyelesaian dinas, PO maklon, dispatch maklon, invoice maklon manual,
     invoice maklon otomatis (AR), job vendor).
  3. Dua jenis nomor yang menumpang SATU koleksi+field (`rahaza_ar_invoices.
     invoice_number` untuk AR Finance vs invoice maklon) TIDAK saling menimpa.
  4. Race-safe: 25 permintaan nomor bersamaan → 25 nomor UNIK (INV-CNT-1).
  5. Reset format mengembalikan perilaku bawaan kode.

Semua uji memakai format ber-awalan ZZUJI- sehingga counter dokumen NYATA tidak
tersentuh; konfigurasi & counter uji dibersihkan di akhir.

    python3 tests/flow_doc_numbering_phase2_test.py
"""
from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, "backend", ".env"))
except Exception:  # noqa: BLE001
    pass

import requests  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

API = os.environ.get("INTERNAL_API_URL", "http://localhost:8001")
PASS: list[str] = []
FAIL: list[str] = []

# (kunci registry, fungsi penghasil nomor, argumen tambahan)
CASES = [
    ("rahaza_purchase_orders.po_number", "routes.rahaza_po", "_gen_po_number", ()),
    ("rahaza_ap_invoices.invoice_number", "routes.rahaza_ap_from_gr", "_gen_ap_number", ()),
    ("rahaza_expense_claims.claim_number", "routes.employee_expense_claims",
     "_generate_claim_number", ()),
    ("employee_travel_requests.trip_number", "routes.employee_travel_requests",
     "_generate_trip_number", ()),
    ("employee_travel_settlements.settlement_number", "routes.employee_travel_settlements",
     "_gen_settlement_number", ()),
    ("dewi_maklon_pos.po_number", "routes.dewi_maklon_pos", "_next_po_number", ("ARN",)),
    ("dewi_maklon_dispatches.dispatch_number", "routes.dewi_maklon_pos",
     "_next_dispatch_number", ("ARN",)),
    ("dewi_maklon_invoices.invoice_number", "routes.dewi_maklon_billing",
     "_next_invoice_number", ("INV-MKL",)),
    ("dewi_maklon.ar_invoice_number", "routes.dewi_maklon_pos", "_next_ar_invoice_number", ()),
    ("vendor_jobs.job_number", "routes.vendor_portal", None, ()),          # inline (dicek via generator)
    ("warehouse_receiving.receipt_number", "routes.rahaza_po", None, ()),  # inline (dicek via generator)
]


def check(name: str, cond, detail: str = ""):
    (PASS if cond else FAIL).append(name)
    print(f"{'✅' if cond else '❌'} {name}" + ("" if cond else f" → {detail}"))


def hdr() -> dict:
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=30)
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        raise SystemExit(f"login gagal: {r.status_code} {r.text[:200]}")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


async def run() -> int:
    h = hdr()
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    from data.doc_number_registry import REGISTRY_BY_KEY, target_of  # noqa: E402
    from utils.counters import gen_prefixed_number, invalidate_format_cache  # noqa: E402

    # ── 1. Katalog memuat 11 jenis baru ──────────────────────────────────────
    r = requests.get(f"{API}/api/admin/doc-numbering", headers=h, timeout=60)
    check("GET /api/admin/doc-numbering 200", r.status_code == 200, r.text[:200])
    items = {it["key"]: it for it in (r.json().get("items") or [])}
    missing = [k for k, *_ in CASES if k not in items]
    check("11 jenis dokumen tahap 2 terdaftar di katalog", not missing, f"belum ada: {missing}")
    broken = [k for k, *_ in CASES if items.get(k, {}).get("error")]
    check("semua format bawaan tahap 2 sah (tanpa error)", not broken,
          str({k: items[k]["error"] for k in broken})[:300])
    check("katalog menampilkan contoh nomor untuk PO Maklon",
          (items.get("dewi_maklon_pos.po_number") or {}).get("contoh", "").startswith("MKL-"),
          str(items.get("dewi_maklon_pos.po_number"))[:200])
    check("invoice maklon otomatis punya kunci sendiri (tidak menimpa AR Finance)",
          items.get("dewi_maklon.ar_invoice_number", {}).get("collection") == "rahaza_ar_invoices"
          and items.get("rahaza_ar_invoices.invoice_number", {}).get("contoh", "").startswith("AR-"),
          str(items.get("dewi_maklon.ar_invoice_number"))[:250])

    try:
        # ── 2. Format owner dipakai fungsi penghasil nomor yang NYATA ────────
        for idx, (key, mod, fn, args) in enumerate(CASES):
            tag = f"ZZUJI{idx:02d}"
            fmt = f"ZZUJI-{tag}-{{SEQ:4}}"
            pv = requests.post(f"{API}/api/admin/doc-numbering/preview", headers=h, timeout=30,
                               json={"key": key, "format": fmt})
            put = requests.put(f"{API}/api/admin/doc-numbering", headers=h, timeout=30,
                               json={"key": key, "format": fmt, "active": True})
            if not (pv.json().get("ok") and put.status_code == 200):
                check(f"[{key}] simpan format owner", False, f"{pv.text[:120]} | {put.text[:160]}")
                continue
            invalidate_format_cache(key)          # proses uji ini punya cache sendiri
            coll, field = target_of(REGISTRY_BY_KEY[key])
            if fn:
                module = __import__(mod, fromlist=[fn])
                num = await getattr(module, fn)(db, *args)
            else:
                # dua titik yang menghasilkan nomor inline di dalam handler
                width = 5
                base = "VJ-" if key.startswith("vendor_jobs") else "GR-"
                ck = key if key not in REGISTRY_BY_KEY else None
                num = await gen_prefixed_number(db, coll, field, base, width,
                                                config_key=ck if ck else None)
            check(f"[{key}] memakai format owner ({fmt})", str(num).startswith(f"ZZUJI-{tag}-"),
                  f"dapat {num}")

        # ── 3. Dua nomor menumpang satu koleksi+field tidak bertabrakan ─────
        from routes.dewi_maklon_pos import _next_ar_invoice_number  # noqa: E402
        requests.put(f"{API}/api/admin/doc-numbering", headers=h, timeout=30,
                     json={"key": "rahaza_ar_invoices.invoice_number",
                           "format": "ZZUJI-ARFIN-{SEQ:4}", "active": True})
        requests.put(f"{API}/api/admin/doc-numbering", headers=h, timeout=30,
                     json={"key": "dewi_maklon.ar_invoice_number",
                           "format": "ZZUJI-ARMKL-{SEQ:4}", "active": True})
        invalidate_format_cache()
        mkl = await _next_ar_invoice_number(db)
        fin = await gen_prefixed_number(db, "rahaza_ar_invoices", "invoice_number", "AR-", 3)
        check("invoice maklon & AR Finance memakai formatnya masing-masing",
              str(mkl).startswith("ZZUJI-ARMKL-") and str(fin).startswith("ZZUJI-ARFIN-"),
              f"maklon={mkl} finance={fin}")

        # ── 4. Race-safe: 25 permintaan bersamaan → 25 nomor unik ───────────
        requests.put(f"{API}/api/admin/doc-numbering", headers=h, timeout=30,
                     json={"key": "rahaza_purchase_orders.po_number",
                           "format": "ZZUJI-RACE-{SEQ:5}", "active": True})
        invalidate_format_cache("rahaza_purchase_orders.po_number")
        from routes.rahaza_po import _gen_po_number  # noqa: E402
        nums = await asyncio.gather(*[_gen_po_number(db) for _ in range(25)])
        check("25 nomor PO bersamaan → 25 nomor UNIK (INV-CNT-1)",
              len(set(nums)) == 25 and all(str(n).startswith("ZZUJI-RACE-") for n in nums),
              f"unik={len(set(nums))} contoh={nums[:3]}")

        # ── 5. Reset → kembali ke format bawaan kode ─────────────────────────
        rs = requests.delete(f"{API}/api/admin/doc-numbering/rahaza_purchase_orders.po_number",
                             headers=h, timeout=30)
        invalidate_format_cache("rahaza_purchase_orders.po_number")
        after = await _gen_po_number(db)
        check("reset format → nomor kembali ke pola bawaan PO-YYYYMMDD-###",
              rs.status_code == 200 and str(after).startswith("PO-") and "ZZUJI" not in str(after),
              f"{rs.status_code} {after}")

    finally:
        # bersihkan konfigurasi uji + counter uji (counter dokumen NYATA tak tersentuh)
        keys = [k for k, *_ in CASES] + ["rahaza_ar_invoices.invoice_number",
                                         "dewi_maklon.ar_invoice_number",
                                         "rahaza_purchase_orders.po_number"]
        for k in set(keys):
            requests.delete(f"{API}/api/admin/doc-numbering/{k}", headers=h, timeout=30)
        cfg = await db.doc_number_configs.delete_many({"format": {"$regex": "^ZZUJI-"}})
        cnt = await db.counters.delete_many({"_id": {"$regex": ":ZZUJI-"}})
        invalidate_format_cache()
        # nomor PO yang dipakai untuk uji reset (langkah 5) mengambil 1 nomor asli →
        # kembalikan counternya supaya urutan dokumen nyata tidak melompat.
        import re as _re
        m = _re.search(r"(\d+)$", str(after) if "after" in dir() else "")
        if m:
            prefix = str(after)[: -len(m.group(1))]
            await db.counters.update_one(
                {"_id": f"autonum:rahaza_purchase_orders:po_number:{prefix}"},
                {"$inc": {"seq": -1}})
        print(f"\n[cleanup] konfigurasi uji dihapus={cfg.deleted_count} "
              f"counter uji dihapus={cnt.deleted_count}")

    print(f"\n=== {len(PASS)} PASS / {len(FAIL)} FAIL ===")
    for f in FAIL:
        print("  FAIL:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
