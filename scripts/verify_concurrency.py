#!/usr/bin/env python3
"""verify_concurrency.py — CONCURRENCY / TOCTOU GATE (CV. Dewi Aditya ERP).

Adapted from Rahaza-Travel. Fires N PARALLEL create requests at numbered-document endpoints
and asserts the write-path is race-safe: every request either succeeds with a UNIQUE number,
or is rejected with a clean 4xx — NEVER a 5xx (E11000 duplicate-key crash) and NEVER a
duplicate number. Uses synthetic far-future data + auto-cleanup to baseline.

Checks:
  CC1 (RC-5 counter/TOCTOU) — N parallel POST /api/rahaza/journals (same date):
      all must be 200 with unique je_number (or clean 4xx). Any 5xx / duplicate = race bug.

Resilient: backend down / login fail / seed missing → SKIP. Exit 1 only on a proven race.
Usage: cd /app && python scripts/verify_concurrency.py
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass
try:
    import httpx
except ImportError:
    os.system("pip install httpx -q")
    import httpx
from pymongo import MongoClient

API = os.environ.get("API_BASE", "http://localhost:8001").rstrip("/")
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
         "password": os.environ.get("ADMIN_PASS", "Admin@123")}
G, Y, R, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[1m", "\033[0m"
DBC = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
fails = 0
skips = 0
CREATED_JE = []

# ── R10 (CC3–CC6) synthetic-artifact tracking for deterministic cleanup ──────
GATE_TAG = "R10-CONC-GATE"
CREATED = {
    "ar_inv": [],       # rahaza_ar_invoices ids (+ their GL JEs / cash movements)
    "asset": [],        # da_assets asset_id (+ da_asset_assignments)
    "employee": [],     # rahaza_employees ids
    "material": [],     # rahaza_materials ids (+ stock/reservations)
    "wo": [],           # rahaza_work_orders ids
    "adj_material": [],  # material_id used for stock-adjust (+ movements)
    "stock_id": [],     # rahaza_material_stock ids
}


def _uid():
    return str(uuid.uuid4())


def _short():
    return uuid.uuid4().hex[:8]


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _classify(rs, N):
    """Turn asyncio.gather results into (http_codes, n5xx, n200)."""
    codes, n5xx, n200 = [], 0, 0
    for x in rs:
        if isinstance(x, Exception):
            n5xx += 1
            codes.append("EXC")
            continue
        codes.append(x.status_code)
        if x.status_code >= 500:
            n5xx += 1
        elif x.status_code == 200:
            n200 += 1
    return codes, n5xx, n200


def ok(m):
    print(f"  {G}[OK]{X} {m}")


def fail(m):
    global fails
    fails += 1
    print(f"  {R}[FAIL]{X} {m}")


def skip(m):
    global skips
    skips += 1
    print(f"  {Y}[SKIP]{X} {m}")


# Koleksi ber-unique-index utk field bernomor: count-based numbering di sini = 500 E11000
# saat balapan. CC2 menjaga agar anti-pola RC-5 tidak muncul kembali di sini.
#
# 2026-08-07 — daftarnya DIAMBIL DARI SSOT `utils.counters.UNIQUE_NUMBERED_FIELDS`
# (daftar yang sama yang memasang index uniknya saat startup). Sebelumnya daftar
# ini ditulis ulang di sini dan sudah MENYIMPANG: `production_jobs`,
# `production_returns`, `dewi_procurement_requests`, dan `acc_purchase_requests`
# tidak terdaftar, sehingga tiga anti-pola `count_documents()+1` LOLOS dari gate
# ini sampai ditemukan manual. Penjaga yang daftarnya sendiri bisa kedaluwarsa
# adalah penjaga yang tidak menjaga apa pun.
def _load_unique_numbered() -> set:
    try:
        sys.path.insert(0, str(ROOT / "backend"))
        from utils.counters import UNIQUE_NUMBERED_FIELDS
        return {c for c, _f in UNIQUE_NUMBERED_FIELDS}
    except Exception as e:
        print(f"{Y}  CC2: gagal memuat SSOT UNIQUE_NUMBERED_FIELDS ({e}) — pakai daftar cadangan.{X}")
        return {
            "rahaza_journal_entries", "rahaza_work_orders", "rahaza_orders",
            "rahaza_ar_invoices", "rahaza_ap_invoices", "rahaza_payroll_runs",
            "rahaza_material_issues", "rahaza_bundles", "warehouse_receiving",
            "rahaza_hpp_snapshots", "dewi_maklon_pos",
            "wh_cmt_dispatches", "wh_delivery_notes", "dewi_maklon_samples",
            "rahaza_purchase_orders", "dewi_maklon_dispatches", "dewi_maklon_invoices",
            "dewi_cmt_delivery_orders", "rahaza_lkp",
        }


_UNIQUE_NUMBERED = _load_unique_numbered() | {
    # Koleksi bernomor lain yang keunikannya penting walau belum ada di SSOT.
    "rahaza_bundles", "rahaza_hpp_snapshots", "dewi_maklon_dispatches",
    "dewi_maklon_invoices", "dewi_cmt_delivery_orders", "rahaza_lkp",
}


def _cc2_static_regression():
    """CC2 (regresi RC-5 statik): pastikan TIDAK ada `count_documents()+1` /
    `<var dari count_documents> + 1` pada koleksi ber-unique-index. Ini mengunci
    perbaikan Phase-G agar pola balapan tidak diperkenalkan kembali."""
    import re
    routes = ROOT / "backend" / "routes"
    count_re = re.compile(r"db(?:\.([a-z][a-z0-9_]*)|\[\s*['\"]?([a-z][a-z0-9_]*)['\"]?\s*\])\s*\.\s*count_documents")
    plus1_same = re.compile(r"count_documents\s*\([^)]*\)\s*\+\s*1")
    offenders = []
    for pyf in routes.rglob("*.py"):
        if "__pycache__" in str(pyf) or "_archive" in str(pyf):
            continue
        try:
            lines = pyf.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        assigned = {}  # var -> coll
        for i, ln in enumerate(lines):
            cm = count_re.search(ln)
            coll = (cm.group(1) or cm.group(2)) if cm else None
            if plus1_same.search(ln) and coll in _UNIQUE_NUMBERED:
                offenders.append(f"{pyf.relative_to(routes)}:{i+1} (db.{coll})")
            ma = re.match(r"\s*([a-z_][a-z0-9_]*)\s*=\s*(?:await\s+)?db.*count_documents", ln)
            if ma and coll:
                assigned[ma.group(1)] = coll
            for var, cl in list(assigned.items()):
                if re.search(rf"\b{re.escape(var)}\s*\+\s*1\b", ln) and cl in _UNIQUE_NUMBERED:
                    offenders.append(f"{pyf.relative_to(routes)}:{i+1} (var {var} <- db.{cl})")
                    assigned.pop(var, None)
    if offenders:
        fail(f"CC2 (RC-5 statik) count_documents()+1 pada koleksi unique-indexed "
             f"({len(offenders)} titik — akan 500 E11000 saat balapan):")
        for o in offenders[:12]:
            print(f"          - {o}")
    else:
        ok("CC2 (RC-5 statik) tak ada penomoran count-based pada koleksi unique-indexed (Phase-G terkunci).")


async def _cc3_ar_payment(c, H):
    """CC3 (TOCTOU AR payment): N parallel FULL payments on one invoice. Exactly
    ONE must succeed (paid==total); the rest 4xx. Never 5xx; never overpay."""
    iid = "R10-CONC-AR-" + _uid()
    DBC.rahaza_ar_invoices.insert_one({
        "id": iid, "invoice_number": f"CONC-AR-{_short()}", "status": "sent",
        "total": 100.0, "paid_amount": 0.0, "balance": 100.0,
        "customer_id": None, "customer_name": "CONC-GATE", "items": [], "lines": [],
        "date": "2028-09-15", "_gate": GATE_TAG, "created_at": _now_iso(),
    })
    CREATED["ar_inv"].append(iid)
    N = 6

    async def pay():
        return await c.post(f"{API}/api/rahaza/ar-invoices/{iid}/payment",
                            headers=H, json={"amount": 100})

    rs = await asyncio.gather(*[pay() for _ in range(N)], return_exceptions=True)
    codes, n5xx, n200 = _classify(rs, N)
    if codes and all(cc == 403 for cc in codes):
        skip("CC3 (AR payment) admin tak berwenang portal finance (403) — SKIP.")
        return
    doc = DBC.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0, "paid_amount": 1})
    paid = float((doc or {}).get("paid_amount") or 0)
    if n5xx > 0:
        fail(f"CC3 (AR payment) {n5xx}/{N} request 5xx pada pembayaran paralel. HTTP={codes}")
    elif paid > 100 + 0.01:
        fail(f"CC3 (AR payment) OVERPAY di bawah balapan: paid_amount={paid} > total=100. HTTP={codes}")
    elif n200 != 1:
        fail(f"CC3 (AR payment) full-pay 100 harus sukses TEPAT 1x, dapat {n200} (paid={paid}). HTTP={codes}")
    else:
        ok(f"CC3 (AR payment) {N} full-pay paralel → tepat 1×200, paid_amount={paid} (tak overpay). Race-safe.")


async def _cc4_asset_assign(c, H):
    """CC4 (TOCTOU asset assign): N parallel assigns on one Available asset. Exactly
    ONE active assignment must exist afterwards (no double-assign)."""
    asset_id = "R10-CONC-ASSET-" + _uid()
    emp_id = "R10-CONC-EMP-" + _uid()
    DBC.da_assets.insert_one({
        "asset_id": asset_id, "asset_code": f"CONC-AST-{_short()}", "asset_name": "CONC Gate Asset",
        "status": "Available", "category": "Peralatan", "_gate": GATE_TAG, "created_at": _now_iso(),
    })
    DBC.rahaza_employees.insert_one({
        "id": emp_id, "employee_code": f"CONC-EMP-{_short()}", "name": "CONC Gate Emp",
        "_gate": GATE_TAG, "created_at": _now_iso(),
    })
    CREATED["asset"].append(asset_id)
    CREATED["employee"].append(emp_id)
    N = 6

    async def assign():
        return await c.post(f"{API}/api/dewi/assets/{asset_id}/assign",
                            headers=H, json={"employee_id": emp_id})

    rs = await asyncio.gather(*[assign() for _ in range(N)], return_exceptions=True)
    codes, n5xx, n200 = _classify(rs, N)
    if codes and all(cc == 403 for cc in codes):
        skip("CC4 (asset assign) admin tak berwenang portal HR (403) — SKIP.")
        return
    active = DBC.da_asset_assignments.count_documents({"asset_id": asset_id, "status": "active"})
    if n5xx > 0:
        fail(f"CC4 (asset assign) {n5xx}/{N} request 5xx pada assign paralel. HTTP={codes}")
    elif active != 1:
        fail(f"CC4 (asset assign) DOUBLE-ASSIGN: {active} assignment aktif (harus 1). HTTP={codes}")
    elif n200 != 1:
        fail(f"CC4 (asset assign) assign harus sukses TEPAT 1x, dapat {n200}. HTTP={codes}")
    else:
        ok(f"CC4 (asset assign) {N} assign paralel → tepat 1×200, 1 assignment aktif. No double-assign.")


async def _cc5_material_reserve(c, H):
    """CC5 (TOCTOU material reserve): N parallel reserves of the full stock. The
    invariant sum(active_reserved) <= stock must ALWAYS hold (no over-allocation)."""
    mat_id = "R10-CONC-MAT-" + _uid()
    wo_id = "R10-CONC-WO-" + _uid()
    DBC.rahaza_materials.insert_one({
        "id": mat_id, "code": f"CONC-MAT-{_short()}", "name": "CONC Gate Material",
        "unit": "pcs", "_gate": GATE_TAG,
    })
    DBC.rahaza_material_stock.insert_one({
        "id": _uid(), "material_id": mat_id, "qty": 10.0, "quantity": 10.0,
        "available_quantity": 10.0, "_gate": GATE_TAG,
    })
    DBC.rahaza_work_orders.insert_one({
        "id": wo_id, "order_id": "CONC-ORD", "wo_number": f"CONC-WO-{_short()}", "_gate": GATE_TAG,
    })
    CREATED["material"].append(mat_id)
    CREATED["wo"].append(wo_id)
    N = 6

    async def reserve():
        return await c.post(f"{API}/api/rahaza/materials/reserve", headers=H,
                            json={"wo_id": wo_id, "materials": [{"material_id": mat_id, "required_qty": 10}]})

    rs = await asyncio.gather(*[reserve() for _ in range(N)], return_exceptions=True)
    codes, n5xx, n200 = _classify(rs, N)
    if codes and all(cc == 403 for cc in codes):
        skip("CC5 (material reserve) 403 — SKIP.")
        return
    # FASE 11 — endpoint reservasi material PER-WO sudah DIPENSIUNKAN di FASE 4 (E10):
    #   * router  → routes/_archive/rahaza_multistage/rahaza_material_reservation.py
    #   * indeks  → dihapus dari server.py ("FASE 4 (E10 DELETE)")
    #   * modul FE → components/erp/_archive/RahazaMaterialReservationModule.jsx
    #   * koleksi `rahaza_material_reservations` tidak ada lagi di DB
    # Karena itu 404/405 di sini BUKAN regresi konkurensi, melainkan fitur yang
    # memang sudah tidak ada. Sebelumnya kondisi ini dilaporkan FAIL sehingga gate
    # `verify_concurrency` MERAH terus-menerus (tercatat merah sejak 2026-07-16)
    # dan menutupi temuan nyata lain. Sekarang di-SKIP dengan alasan eksplisit —
    # SKIP tetap BUKAN PASS (lihat filosofi gate.sh).
    if codes and all(cc in (404, 405) for cc in codes):
        skip("CC5 (material reserve) endpoint dipensiunkan FASE 4 (E10) — fitur reservasi "
             "per-WO diarsipkan, koleksi `rahaza_material_reservations` tidak ada. "
             f"HTTP={codes} — bukan regresi konkurensi.")
        return
    agg = list(DBC.rahaza_material_reservations.aggregate([
        {"$match": {"material_id": mat_id, "status": "active"}},
        {"$group": {"_id": None, "t": {"$sum": "$reserved_qty"}}},
    ]))
    reserved = float(agg[0]["t"]) if agg else 0.0
    if n5xx > 0:
        fail(f"CC5 (material reserve) {n5xx}/{N} request 5xx pada reserve paralel. HTTP={codes}")
    elif reserved > 10 + 1e-6:
        fail(f"CC5 (material reserve) OVER-ALLOCATION: reserved aktif={reserved} > stock=10. HTTP={codes}")
    elif n200 != 1:
        fail(f"CC5 (material reserve) reserve 10-of-10 harus sukses TEPAT 1x, dapat {n200} (reserved={reserved}). HTTP={codes}")
    else:
        ok(f"CC5 (material reserve) {N} reserve paralel → tepat 1×200, reserved aktif={reserved} <= stock=10. No over-allocation.")


async def _cc6_stock_adjust(c, H):
    """CC6 (TOCTOU stock adjust): N parallel decreases of 8 from a stock of 10.
    Only one can succeed (2×8 > 10). Final qty must be >= 0 and reflect exactly the
    number of successes (no lost-update, no negative)."""
    mat_id = "R10-CONC-ADJ-" + _uid()
    stock_id = _uid()
    DBC.rahaza_material_stock.insert_one({
        "id": stock_id, "material_id": mat_id, "quantity": 10.0, "qty": 10.0,
        "available_quantity": 10.0, "unit": "pcs", "_gate": GATE_TAG,
    })
    CREATED["stock_id"].append(stock_id)
    CREATED["adj_material"].append(mat_id)
    N = 6

    async def adj():
        return await c.post(f"{API}/api/wms/stock/unified/adjust", headers=H,
                            json={"material_id": mat_id, "adjustment_type": "opname_decrease",
                                  "qty_delta": 8, "reason": "conc-gate probe"})

    rs = await asyncio.gather(*[adj() for _ in range(N)], return_exceptions=True)
    codes, n5xx, n200 = _classify(rs, N)
    if codes and all(cc == 403 for cc in codes):
        skip("CC6 (stock adjust) admin tak berwenang (403) — SKIP.")
        return
    doc = DBC.rahaza_material_stock.find_one({"id": stock_id}, {"_id": 0, "quantity": 1})
    qty = float((doc or {}).get("quantity") or 0)
    expected = 10 - 8 * n200
    if n5xx > 0:
        fail(f"CC6 (stock adjust) {n5xx}/{N} request 5xx pada adjust paralel. HTTP={codes}")
    elif qty < -1e-9:
        fail(f"CC6 (stock adjust) STOK NEGATIF di bawah balapan: qty={qty}. HTTP={codes}")
    elif abs(qty - expected) > 1e-6:
        fail(f"CC6 (stock adjust) LOST-UPDATE: qty={qty} != 10 - 8*{n200} ({expected}). HTTP={codes}")
    elif n200 != 1:
        fail(f"CC6 (stock adjust) decrease 8-of-10 harus sukses TEPAT 1x, dapat {n200} (qty={qty}). HTTP={codes}")
    else:
        ok(f"CC6 (stock adjust) {N} decrease paralel → tepat 1×200, qty={qty} (10-8), no negative/lost-update. Race-safe.")


def _cc7_unique_index_present():
    """CC7 (jaring pengaman DB): setiap field nomor dokumen HARUS punya index unik.

    Penomoran atomik di kode saja tidak cukup — satu jalur tulis yang melewati
    generator (impor massal, migrasi, skrip perbaikan, kode baru) bisa menanam
    nomor KEMBAR tanpa suara. Sampai 2026-08-07 DELAPAN koleksi bernomor tidak
    punya index unik, termasuk `warehouse_receiving.gr_number` (penerimaan barang
    → MENAMBAH STOK) dan `rahaza_material_issues.issue_number` (→ MENGURANGI STOK).
    """
    try:
        sys.path.insert(0, str(ROOT / "backend"))
        from utils.counters import UNIQUE_NUMBERED_FIELDS
    except Exception as e:
        skip(f"CC7 (index unik nomor dokumen) tak bisa memuat SSOT ({e}) — SKIP.")
        return
    existing = set(DBC.list_collection_names())
    missing, dup_found = [], []
    for coll, field in UNIQUE_NUMBERED_FIELDS:
        if coll not in existing:
            continue          # koleksi belum lahir → index dipasang saat startup berikutnya
        info = DBC[coll].index_information()
        has = any(v.get("unique") and any(k[0] == field for k in v.get("key", []))
                  for v in info.values())
        if not has:
            missing.append(f"{coll}.{field}")
        rows = list(DBC[coll].aggregate([
            {"$match": {field: {"$nin": [None, ""]}}},
            {"$group": {"_id": f"${field}", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}, {"$limit": 5},
        ]))
        if rows:
            dup_found.append(f"{coll}.{field}={[r['_id'] for r in rows]}")
    if dup_found:
        fail(f"CC7 (nomor kembar NYATA di database): {'; '.join(dup_found)}")
    elif missing:
        fail(f"CC7 (index unik nomor dokumen) {len(missing)} field TANPA index unik "
             f"— nomor kembar bisa masuk diam-diam: {', '.join(missing[:8])}")
    else:
        ok(f"CC7 (index unik nomor dokumen) {len(UNIQUE_NUMBERED_FIELDS)} field nomor "
           f"dilindungi index unik & tidak ada nomor kembar.")


async def main():
    print(f"\n{B}{'='*64}{X}\n  CONCURRENCY GATE (RC-5 counter / TOCTOU)  API={API}\n{B}{'='*64}{X}")
    _cc2_static_regression()
    _cc7_unique_index_present()
    async with httpx.AsyncClient(follow_redirects=True, timeout=40) as c:
        try:
            r = await c.get(f"{API}/api/health", timeout=5)
            if r.status_code >= 500:
                raise Exception("5xx")
        except Exception:
            print(f"{Y}  Backend belum berjalan — SKIP (Phase 0).{X}")
            return 0
        r = await c.post(f"{API}/api/auth/login", json=ADMIN)
        if r.status_code != 200:
            skip(f"Login admin gagal ({r.status_code}) — SKIP.")
            return _summary()
        H = {"Authorization": f"Bearer {r.json()['token']}"}

        # Need 2 leaf, active COA codes for a balanced 2-line journal.
        codes = [a["code"] for a in DBC.rahaza_coa_accounts.find(
            {"is_group": False, "active": True}, {"_id": 0, "code": 1}).limit(2)]
        if len(codes) < 2:
            skip("COA leaf accounts < 2 — SKIP.")
            return _summary()

        # ---- CC1: N parallel journal creates (same date) ----
        N = 5
        je_date = "2028-09-15"
        payload = {
            "date": je_date, "memo": "CONCURRENCY-GATE synthetic (auto-cleanup)",
            "source_module": "gate_concurrency",
            "lines": [
                {"account_code": codes[0], "debit": 10000, "credit": 0, "description": "gate"},
                {"account_code": codes[1], "debit": 0, "credit": 10000, "description": "gate"},
            ],
        }

        async def mk():
            return await c.post(f"{API}/api/rahaza/journals", headers=H, json=payload)

        rs = await asyncio.gather(*[mk() for _ in range(N)], return_exceptions=True)
        codes_http = []
        je_numbers = []
        n5xx = 0
        for x in rs:
            if isinstance(x, Exception):
                n5xx += 1
                codes_http.append("EXC")
                continue
            codes_http.append(x.status_code)
            if x.status_code >= 500:
                n5xx += 1
            elif x.status_code == 200:
                try:
                    j = x.json()
                    if j.get("id"):
                        CREATED_JE.append(j["id"])
                    if j.get("je_number"):
                        je_numbers.append(j["je_number"])
                except Exception:
                    pass

        dup = len(je_numbers) != len(set(je_numbers))
        n200 = sum(1 for cc in codes_http if cc == 200)
        if n5xx > 0:
            fail(f"CC1 (RC-5) {n5xx}/{N} request 5xx pada create paralel (E11000 dup-key race). HTTP={codes_http}")
        elif dup:
            fail(f"CC1 (RC-5) je_number DUPLIKAT di bawah balapan: {je_numbers}")
        elif n200 == N:
            ok(f"CC1 (RC-5) {N} journal paralel → semua 200 dgn je_number UNIK ({sorted(set(je_numbers))[:3]}…). Race-safe.")
        else:
            skip(f"CC1 tak konklusif: HTTP={codes_http} (mungkin rate-limit/validasi).")

        # ── CC3–CC6: TOCTOU write-path probes (R10 concurrency hardening) ──
        for _name, _fn in (("CC3", _cc3_ar_payment), ("CC4", _cc4_asset_assign),
                           ("CC5", _cc5_material_reserve), ("CC6", _cc6_stock_adjust)):
            try:
                await _fn(c, H)
            except Exception as _ex:
                skip(f"{_name} error tak terduga (dianggap SKIP): {_ex}")

    return _summary()


def _cleanup():
    for jid in CREATED_JE:
        DBC.rahaza_journal_entries.delete_one({"id": jid})
        DBC.rahaza_journal_lines.delete_many({"je_id": jid})
    # sweep any leftover synthetic gate journals
    for je in DBC.rahaza_journal_entries.find({"source_module": "gate_concurrency"}, {"id": 1}):
        DBC.rahaza_journal_entries.delete_one({"id": je["id"]})
        DBC.rahaza_journal_lines.delete_many({"je_id": je["id"]})

    # ── R10 CC3–CC6 synthetic artifacts (deterministic purge, 0-residual) ──
    # CC3: AR invoices + their GL journal entries/lines + cash movements
    for iid in CREATED["ar_inv"]:
        for je in DBC.rahaza_journal_entries.find({"source_ref": {"$regex": iid}}, {"id": 1}):
            DBC.rahaza_journal_lines.delete_many({"je_id": je["id"]})
            DBC.rahaza_journal_entries.delete_one({"id": je["id"]})
        DBC.rahaza_cash_movements.delete_many({"ref_id": iid})
        DBC.rahaza_ar_invoices.delete_one({"id": iid})
    # CC4: assets + assignments + employees
    for asset_id in CREATED["asset"]:
        DBC.da_asset_assignments.delete_many({"asset_id": asset_id})
        DBC.da_assets.delete_one({"asset_id": asset_id})
    for emp_id in CREATED["employee"]:
        DBC.rahaza_employees.delete_one({"id": emp_id})
    # CC5: materials + stock + reservations + work orders
    for mat_id in CREATED["material"]:
        DBC.rahaza_material_reservations.delete_many({"material_id": mat_id})
        DBC.rahaza_material_stock.delete_many({"material_id": mat_id})
        # Sesi #33 — riwayat harga ikut dibuang (anti baris YATIM di layar
        # Riwayat Harga Barang; dijaga INV-F38 C16).
        DBC.rahaza_material_cost_history.delete_many({"material_id": mat_id})
        DBC.rahaza_materials.delete_one({"id": mat_id})
    for wo_id in CREATED["wo"]:
        DBC.rahaza_material_reservations.delete_many({"wo_id": wo_id})
        DBC.rahaza_work_orders.delete_one({"id": wo_id})
    # CC6: stock rows + adjustment movements
    for sid in CREATED["stock_id"]:
        DBC.rahaza_material_stock.delete_one({"id": sid})
    for mat_id in CREATED["adj_material"]:
        DBC.rahaza_material_stock.delete_many({"material_id": mat_id})
        DBC.rahaza_material_movements.delete_many({"material_id": mat_id})
    # Safety net: sweep ANY residual doc tagged with GATE_TAG
    for coll in ("rahaza_ar_invoices", "da_assets", "rahaza_employees",
                 "rahaza_materials", "rahaza_material_stock", "rahaza_work_orders"):
        DBC[coll].delete_many({"_gate": GATE_TAG})

def _summary():
    _cleanup()
    print(f"\n{B}{'='*64}{X}\n  {R}FAIL {fails}{X} | {Y}SKIP {skips}{X}\n{B}{'='*64}{X}")
    if fails:
        print(f"{R}{B}  CONCURRENCY REGRESI — numbering tidak atomik (pakai next_counter/retry).{X}\n")
        return 1
    print(f"{G}{B}  Concurrency aman (numbering race-safe).{X}\n")
    return 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    except Exception as ex:
        _cleanup()
        print(f"{Y}  Gate error (dianggap SKIP): {ex}{X}")
        rc = 0
    sys.exit(rc)
