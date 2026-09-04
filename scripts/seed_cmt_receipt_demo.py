#!/usr/bin/env python3
"""seed_cmt_receipt_demo.py — satu PENERIMAAN FG dari CMT (demo, idempoten).

MENGAPA SEEDER INI ADA (2026-08-17, sesi #17)
---------------------------------------------
Gate **INV-F23 S8** (Fase H-8) menjaga agar empat alias menu lama tidak berujung
layar kosong: `prod-cmt-packing` & `maklon-packing` diarahkan ke `da-cmt-receive`
(penerimaan FG dari CMT + QC, koleksi `cmt_receipts`). Bootstrap TIDAK PERNAH
menyeed koleksi itu, jadi setiap environment SEGAR memberi **MERAH PALSU**
("cmt_receipts kosong") dan membuat agent berikutnya mengira ada regresi —
persis penyakit yang sudah pernah terjadi pada baseline valuasi aksesoris & master
supplier (lihat komentar seedernya di `scripts/bootstrap.sh`).

Yang dibuat: SATU penerimaan FG (`status=on_qc`) yang ditautkan ke pengiriman
deklarasi CMT yang sudah ada (`buyer_shipments` milik vendor CMT). Barisnya
di-auto-populate oleh endpoint dari `buyer_shipment_items`, jadi angkanya BUKAN
tebakan seeder — ia datang dari dokumen pengiriman yang sudah ada.

Tidak menyentuh stok, tidak menjurnal (penerimaan masih `on_qc`; stok baru
bergerak saat QC disetujui), jadi baseline gate lain tidak berubah.

Pakai:  python3 scripts/seed_cmt_receipt_demo.py
        python3 scripts/seed_cmt_receipt_demo.py --cleanup
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(ROOT / "backend"))
from gr_common import db_handle

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, X = "\033[92m", "\033[93m", "\033[91m", "\033[0m"
NOTE = "Demo penerimaan FG dari CMT (seed bootstrap — INV-F23 S8)"


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        d = e.read()
        return e.code, (json.loads(d or b"{}") if d[:1] in (b"{", b"[")
                        else {"raw": d[:300].decode(errors="ignore")})
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def cleanup(db) -> int:
    ids = [r["id"] for r in db.cmt_receipts.find({"notes": NOTE}, {"_id": 0, "id": 1})]
    n_lines = db.cmt_receipt_lines.delete_many({"receipt_id": {"$in": ids}}).deleted_count
    n = db.cmt_receipts.delete_many({"notes": NOTE}).deleted_count
    print(f"{Y}  dibuang: {n} penerimaan · {n_lines} baris{X}")
    # ⚠️ PELAJARAN 2026-08-17 (ditemukan saat gate penuh dijalankan): `create_receipt`
    # menulis buku kuantitas job item secara INKREMENTAL (`$inc` qty_declared /
    # qty_accepted / qty_claimed_by_vendor). Menghapus dokumennya TIDAK mengurangi
    # angka itu, jadi cleanup tanpa rekalkulasi meninggalkan buku yang menggantung
    # dan gate INV-14 langsung MERAH ("buku kuantitas tidak konsisten dengan dokumen
    # sumber"). Karena itu cleanup WAJIB diikuti rekalkulasi dari dokumen sumber.
    if n or n_lines:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from recompute_qty_ledger import audit_ledger
            fixed = audit_ledger(db, apply=True, verbose=False)
            print(f"{G}  ✓ buku kuantitas job item direkalkulasi ({len(fixed)} diperbaiki){X}")
        except Exception as e:  # noqa: BLE001
            print(f"{R}  ! rekalkulasi buku kuantitas gagal ({e}) — jalankan manual: "
                  f"python3 scripts/recompute_qty_ledger.py{X}")
    return 0


def main() -> int:
    db = db_handle()
    if "--cleanup" in sys.argv:
        return cleanup(db)

    total = db.cmt_receipts.count_documents({})
    if total > 0:
        print(f"{G}  · cmt_receipts sudah berisi {total} dokumen — seed dilewati (idempoten){X}")
        return 0

    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}  ✗ login admin gagal (HTTP {st}) — seed dilewati{X}")
        return 1

    # Pengiriman deklarasi CMT yang SUDAH ADA. Prioritas: vendor yang jelas CMT
    # (bukan "Produksi Internal") supaya layar penerimaan FG masuk akal.
    ship = db.buyer_shipments.find_one(
        {"vendor_name": {"$regex": "cmt", "$options": "i"}}, {"_id": 0})
    if not ship:
        ship = db.buyer_shipments.find_one(
            {"vendor_name": {"$not": {"$regex": "internal", "$options": "i"}}}, {"_id": 0})
    if not ship:
        ship = db.buyer_shipments.find_one({}, {"_id": 0})
    if not ship:
        print(f"{Y}  ! belum ada buyer_shipments — jalankan seed maklon/demo dulu{X}")
        return 0

    st, d = call("POST", "/api/prod/cmt-receipts", token, {
        "related_shipment_id": ship["id"],
        "cmt_name": ship.get("vendor_name") or "CMT Mitra",
        "po_number": ship.get("po_number", ""),
        "po_id": ship.get("po_id", ""),
        "business_type": "maklon",
        "delivery_note": ship.get("shipment_number", ""),
        "notes": NOTE,
    })
    if st not in (200, 201):
        print(f"{R}  ✗ gagal membuat penerimaan demo (HTTP {st}): "
              f"{str(d)[:200]}{X}")
        return 1
    rid = (d or {}).get("id")
    n_lines = db.cmt_receipt_lines.count_documents({"receipt_id": rid})
    print(f"{G}  ✓ penerimaan FG demo dibuat: {(d or {}).get('receipt_code')} "
          f"dari {ship.get('vendor_name')} (SJ {ship.get('shipment_number')}) · "
          f"{n_lines} baris · status {(d or {}).get('status')}{X}")
    print("    buka layar: da-cmt-receive (alias prod-cmt-packing / maklon-packing)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
