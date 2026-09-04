#!/usr/bin/env python3
"""backfill_marketing_channel_subledger.py — F0.7: lengkapi akun COA piutang
per toko (subledger `channel`) untuk toko yang dibuat TANPA lewat API.

KENAPA
------
`POST /api/marketing/accounts` memanggil `ensure_subledger_for_entity(db,'channel',…)`
sehingga setiap toko baru otomatis punya akun COA piutang sendiri (anak `1-220`)
dan kodenya ditulis ke `ar_account_code`. Toko yang di-insert langsung oleh skrip
seed (`seed_marketing_real_accounts.py`) melewati jalur itu ⇒ 9 toko nyata tidak
punya akun buku besar sendiri (pencairan F9 tak punya alamat jurnal per toko).

Skrip ini IDEMPOTEN: toko yang sudah punya `ar_account_code` valid dilewati.

Pakai:
    python3 backend/scripts/backfill_marketing_channel_subledger.py            # dry-run
    python3 backend/scripts/backfill_marketing_channel_subledger.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")

from database import get_db                                      # noqa: E402
from routes.coa_auto import ensure_subledger_for_entity          # noqa: E402

USER = {"id": "system", "name": "backfill-f0.7", "email": "system"}


async def main(apply: bool, prune: bool = False) -> int:
    db = get_db()
    accounts = await db.marketing_platform_accounts.find({}, {"_id": 0}).to_list(1000)
    print("=" * 78)
    print(f"F0.7 backfill subledger piutang channel — mode: {'APPLY' if apply else 'DRY-RUN'}")
    print("=" * 78)

    n_ok = n_new = n_fix = 0
    for acc in accounts:
        code = acc.get("ar_account_code")
        label = f"{acc.get('account_code','?'):20s} {acc.get('account_name','?')[:30]:30s}"
        if code:
            exists = await db.rahaza_coa_accounts.find_one({"code": code}, {"_id": 0, "code": 1})
            if exists:
                print(f"  {'SUDAH OK':>9s}  {label} → {code}")
                n_ok += 1
                continue
            print(f"  {'MENGGANTUNG':>9s}  {label} → {code} (akun COA tidak ada, dibuat ulang)")
            n_fix += 1
        else:
            print(f"  {'BARU':>9s}  {label} → akan dibuat subledger anak 1-220")
            n_new += 1
        if apply:
            res = await ensure_subledger_for_entity(db, "channel", acc, USER)
            if res.get("ok"):
                print(f"  {'':>9s}   ✓ {res.get('code')}")
            else:
                print(f"  {'':>9s}   ✗ GAGAL: {res.get('error') or res.get('reason')}")

    print(f"\n  ringkas: sudah_ok={n_ok} baru={n_new} diperbaiki={n_fix} total={len(accounts)}")

    # Akun subledger YATIM: tokonya sudah dihapus keras (mis. skrip uji dengan
    # `?hard=true`) tetapi akun COA-nya tertinggal di bagan akun.
    ids = {a.get("id") for a in accounts}
    orphans = [c async for c in db.rahaza_coa_accounts.find(
        {"flags.subledger_entity_type": "channel"}, {"_id": 0, "code": 1, "name": 1, "flags": 1})
        if (c.get("flags") or {}).get("subledger_entity_id") not in ids]
    if orphans:
        print(f"\n  akun subledger YATIM (toko sudah tidak ada): {len(orphans)}")
        for o in orphans:
            print(f"      {o['code']:26s} {o.get('name','')}")
        if prune:
            await db.rahaza_coa_accounts.delete_many(
                {"code": {"$in": [o["code"] for o in orphans]}})
            print("      ✓ dihapus (--prune-orphans)")
        else:
            print("      (jalankan dengan --prune-orphans untuk membersihkan)")

    if not apply:
        print("\n  DRY-RUN: tidak ada yang diubah. Jalankan ulang dengan --apply.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--prune-orphans", action="store_true",
                    help="hapus akun subledger yang tokonya sudah tidak ada")
    a = ap.parse_args()
    os.chdir("/app/backend")
    raise SystemExit(asyncio.run(main(a.apply, a.prune_orphans)))
