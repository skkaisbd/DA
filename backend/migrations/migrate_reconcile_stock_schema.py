"""Migration: FASE 6.6-A — rekonsiliasi baris stok skema lama A/B/C → kanonik.

Created: 2026-07-25
Reversible: YES (jurnal `wh_stock_schema_reconcile_log` → `--rollback <log_id>`)

Apa yang dikerjakan (lihat `core/stock_reconcile.py` untuk detail):
  * Skema B (lokasi NESTED `location.id`)  → `location_id` datar
  * Skema C (tanpa lokasi)                → zona storage kanonik sesuai kategori material
  * alias `total_qty`/`quantity`           → di-mirror = `qty`
  * `available_quantity`                   → dihitung ulang = qty − reserved
  * baris kembar (material+lokasi sama)    → digabung ke baris tertua (TOTAL on-hand TETAP)

TIDAK diperbaiki otomatis (dilaporkan saja): `qty` negatif & baris yatim (material_id
tak ada di master) — keduanya butuh keputusan manusia (opname / penyesuaian resmi).

Pakai:
    python3 migrations/migrate_reconcile_stock_schema.py                 # dry-run (default)
    python3 migrations/migrate_reconcile_stock_schema.py --execute       # terapkan
    python3 migrations/migrate_reconcile_stock_schema.py --rollback <id> # balikkan
    python3 migrations/migrate_reconcile_stock_schema.py --logs          # riwayat
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from core import stock_reconcile  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client, client[os.environ.get("DB_NAME", "test_database")]


def _p(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="terapkan perubahan (default dry-run)")
    ap.add_argument("--rollback", metavar="LOG_ID", help="balikkan satu eksekusi")
    ap.add_argument("--logs", action="store_true", help="tampilkan riwayat eksekusi")
    args = ap.parse_args()

    client, db = _db()
    try:
        if args.logs:
            _p("RIWAYAT REKONSILIASI SKEMA STOK")
            rows = await stock_reconcile.logs(db, limit=50)
            if not rows:
                print("(belum ada eksekusi)")
            for r in rows:
                print(f"- {r['id']} · {r.get('created_at')} · "
                      f"normalized={r.get('summary', {}).get('rows_normalized')} "
                      f"merged={r.get('summary', {}).get('rows_merged')} "
                      f"rolled_back={bool(r.get('rolled_back_at'))}")
            return

        if args.rollback:
            _p(f"ROLLBACK {args.rollback}")
            res = await stock_reconcile.rollback(db, args.rollback)
            print(json.dumps(res, default=str, indent=2))
            return

        _p("1/3 SCAN (read-only)")
        report = await stock_reconcile.scan(db, detail_limit=20)
        print(f"Baris stok        : {report['total_rows']}")
        print(f"Total on-hand     : {report['total_qty']}")
        print(f"Bentuk baris      : {report['by_schema']}")
        print(f"Baris bermasalah  : {report['affected_rows']}")
        for k, v in report["counts"].items():
            if v:
                print(f"  - {k:18s} {v:5d}  — {report['labels'][k]}")
        if report["healthy"]:
            print("\n✓ SEHAT — tidak ada yang perlu direkonsiliasi.")
            return

        _p("2/3 RENCANA (dry-run)")
        plan = await stock_reconcile.reconcile(db, dry_run=True)
        print(json.dumps(plan["summary"], default=str, indent=2))
        if plan.get("unresolved"):
            print(f"\n! {len(plan['unresolved'])} baris TANPA lokasi yang tak bisa diselesaikan "
                  f"(zona storage kanonik belum ada — buat lewat Struktur Gudang).")
        if plan.get("manual_attention"):
            print(f"! {len(plan['manual_attention'])} baris butuh keputusan manual (qty negatif / yatim).")

        if not args.execute:
            print("\nDRY-RUN. Jalankan ulang dengan --execute untuk menerapkan.")
            return

        _p("3/3 EKSEKUSI")
        res = await stock_reconcile.reconcile(db, dry_run=False, actor={"id": "cli", "name": "migration-cli"})
        print(json.dumps(res["summary"], default=str, indent=2))
        print(f"\nlog_id = {res['log_id']}  (rollback: --rollback {res['log_id']})")
        assert res["summary"].get("total_qty_preserved"), \
            "FATAL: total on-hand berubah setelah rekonsiliasi — segera rollback!"
        post = await stock_reconcile.scan(db, detail_limit=5)
        print(f"\nVerifikasi pasca-eksekusi: affected_rows={post['affected_rows']} "
              f"(sisa = penyakit report-only) by_schema={post['by_schema']}")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
