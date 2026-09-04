#!/usr/bin/env python3
"""repair_leaked_order_reservations.py — F10 · perbaiki reservasi stok yang BOCOR.

═══════════════════════════════════════════════════════════════════════════════
KENAPA MIGRASI INI ADA
═══════════════════════════════════════════════════════════════════════════════
Sebelum `backend/core/order_status.py` menjadi satu-satunya penulis status order,
**empat** jalur mengubah/menghapus order tanpa melepas reservasi stoknya
(`POST /bulk-status`, `DELETE /{id}`, webhook marketplace, dan pembalikan status
dari `cancelled` ke `new`). Kodenya sudah diperbaiki, tetapi **data yang sudah
rusak tidak sembuh sendiri**: setiap order yang pernah lewat jalur itu masih
menahan `reserved_quantity` di `rahaza_material_stock` ⇒ stok jual lebih rendah
daripada kenyataan, selamanya, tanpa dokumen yang menjelaskan.

Skrip ini punya TIGA pekerjaan yang sengaja dipisah menurut tingkat kepastiannya:

┌──┬──────────────────────────────┬──────────────────────────────────────────────┐
│  │ Temuan                       │ Perlakuan                                    │
├──┼──────────────────────────────┼──────────────────────────────────────────────┤
│ A│ Order `cancelled`/`returned` │ **DIPERBAIKI** dengan `--execute`. Pasti      │
│  │ yang masih menggenggam       │ salah, dan `reserved_rows`-nya masih ada, jadi│
│  │ reservasi                    │ pelepasannya presisi (baris & jumlah persis). │
├──┼──────────────────────────────┼──────────────────────────────────────────────┤
│ B│ Reservasi **YATIM**: jumlah  │ **HANYA DILAPORKAN.** Dokumen ordernya sudah  │
│  │ `reserved_quantity` yang     │ hilang (jalur DELETE lama), jadi tidak ada    │
│  │ tidak bisa dijelaskan oleh   │ catatan baris mana & berapa. Menebaknya =     │
│  │ pemegang reservasi mana pun  │ berisiko membebaskan reservasi order yang     │
│  │                              │ MASIH hidup ⇒ overselling. Butuh `--fix-orphans`│
│  │                              │ yang eksplisit + dicatat di ledger.          │
├──┼──────────────────────────────┼──────────────────────────────────────────────┤
│ C│ Order `shipped`/`delivered`  │ **HANYA DILAPORKAN** (bukan bug jalur ini).   │
│  │ yang masih menggenggam       │ Artinya order diselesaikan lewat modul Toko   │
│  │ reservasi                    │ saja, tanpa alur gudang, jadi on-hand belum   │
│  │                              │ turun & HPP belum dijurnal. Keputusan bisnis, │
│  │                              │ bukan sesuatu yang boleh ditebak skrip.      │
└──┴──────────────────────────────┴──────────────────────────────────────────────┘

Sifat: **idempoten** (jalan berkali-kali aman), **dry-run sebagai bawaan**, dan
setiap perbaikan diberi penanda `reservation_repaired_at` + `reservation_repaired_by`
supaya jejaknya bisa diaudit.

Pakai::

    python3 backend/migrations/repair_leaked_order_reservations.py            # laporan (dry-run)
    python3 backend/migrations/repair_leaked_order_reservations.py --execute  # perbaiki temuan A
    python3 backend/migrations/repair_leaked_order_reservations.py --execute --fix-orphans
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

APP_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_BACKEND not in sys.path:
    sys.path.insert(0, APP_BACKEND)

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

G, R, Y, X, BOLD, DIM = ('\033[92m', '\033[91m', '\033[93m', '\033[0m', '\033[1m', '\033[2m')

EXECUTE = '--execute' in sys.argv
FIX_ORPHANS = '--fix-orphans' in sys.argv
STOCK = 'rahaza_material_stock'


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


async def _explained_reserved(db) -> dict:
    """Reservasi yang BISA dijelaskan, dikelompokkan per `stock_id` / per material.

    Return ``{'by_row': {stock_id: qty}, 'by_material': {material_id: qty}}``.

    Tiga pemegang reservasi yang sah di sistem ini:
      1. `marketing_orders` — `reserved_rows` (tingkat order, K-8b) atau
         `items[].reserved_rows` (order warisan) selama statusnya BUKAN
         `cancelled`/`returned`;
      2. `marketing_orders.fulfillment_items[].reserved_rows` (alokasi gudang)
         selama `fulfillment_status` belum `dispatched`;
      3. `rahaza_fg_reservations` aktif (FG Matrix) — memesan per MATERIAL
         (`stock_service.reserve_material` tidak mencatat baris), jadi hanya bisa
         dibandingkan pada tingkat material.
    """
    by_row: dict = {}
    by_material: dict = {}
    leaked_by_row: dict = {}

    def add_rows(rows, bucket=None):
        target = by_row if bucket is None else bucket
        for d in rows or []:
            sid = (d or {}).get('stock_id')
            q = _f((d or {}).get('qty_reserved'))
            if sid and q > 0:
                target[sid] = round(target.get(sid, 0.0) + q, 4)

    cur = db.marketing_orders.find({}, {'_id': 0})
    async for o in cur:
        status = str(o.get('status') or '')
        if status in ('cancelled', 'returned'):
            # Reservasi ini SEHARUSNYA sudah dilepas ⇒ dilaporkan sebagai temuan A.
            # Dicatat terpisah supaya tidak muncul DUA KALI (sekali sebagai bocor,
            # sekali lagi sebagai "yatim"): laporan yang menghitung ganda membuat
            # pembacanya tidak bisa mempercayai angka mana pun.
            if o.get('reserved_rows'):
                add_rows(o.get('reserved_rows'), leaked_by_row)
            else:
                for ln in (o.get('items') or []):
                    if isinstance(ln, dict):
                        add_rows(ln.get('reserved_rows'), leaked_by_row)
        else:
            if o.get('reserved_rows'):
                add_rows(o.get('reserved_rows'))
            else:
                for ln in (o.get('items') or []):
                    if isinstance(ln, dict):
                        add_rows(ln.get('reserved_rows'))
        if str(o.get('fulfillment_status') or '') not in ('dispatched', 'delivered', 'cancelled'):
            for it in (o.get('fulfillment_items') or []):
                if isinstance(it, dict):
                    add_rows(it.get('reserved_rows'))

    try:
        cur = db.rahaza_fg_reservations.find(
            {'status': {'$nin': ['released', 'cancelled', 'consumed', 'fulfilled']}},
            {'_id': 0, 'material_id': 1, 'qty': 1})
        async for d in cur:
            mid = d.get('material_id')
            if mid:
                by_material[mid] = round(by_material.get(mid, 0.0) + _f(d.get('qty')), 4)
    except Exception as e:  # noqa: BLE001
        print(f'  {Y}! rahaza_fg_reservations tidak terbaca: {e}{X}')

    return {'by_row': by_row, 'by_material': by_material, 'leaked_by_row': leaked_by_row}


async def main() -> int:  # noqa: C901
    from core import order_status as ostat

    mongo = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    dbname = os.environ.get('DB_NAME', 'test_database')
    db = AsyncIOMotorClient(mongo)[dbname]

    mode = f'{R}EKSEKUSI{X}' if EXECUTE else f'{Y}DRY-RUN (laporan saja){X}'
    print(f'\n{BOLD}repair_leaked_order_reservations{X} — {mode}   db={dbname}\n')

    # ══════════════════════════════════════════════════════════════════════════
    # A — order batal/retur yang masih menggenggam reservasi (PASTI salah)
    # ══════════════════════════════════════════════════════════════════════════
    leaks = await db.marketing_orders.find(ostat.leak_query(), {'_id': 0}).to_list(5000)
    print(f'{BOLD}A. Order batal/retur yang masih menggenggam reservasi: '
          f'{R if leaks else G}{len(leaks)}{X}')
    total_a = 0.0
    for o in leaks:
        qty = _f(o.get('reserved_qty')) or sum(
            _f(d.get('qty_reserved')) for d in (o.get('reserved_rows') or []))
        total_a += qty
        print(f'   {DIM}·{X} {o.get("order_id") or o.get("id")}  status={o.get("status")}  '
              f'tertahan={qty}  baris={len(o.get("reserved_rows") or [])}')
    if leaks:
        print(f'   {Y}total stok tertahan: {round(total_a, 4)}{X}')

    repaired = 0
    released_total = 0.0
    if leaks and EXECUTE:
        for o in leaks:
            res = await ostat.release_reservations(db, o, reason='migration:repair_leak')
            patch = dict(res['patch'])
            patch.update({'reservation_repaired_at': datetime.now(timezone.utc),
                          'reservation_repaired_by': 'repair_leaked_order_reservations'})
            await db.marketing_orders.update_one({'id': o['id']}, {'$set': patch})
            await ostat.refresh_catalog_cache(db, res['touched'])
            repaired += 1
            released_total += res['released']
        print(f'   {G}✓ diperbaiki {repaired} order · stok dilepas {round(released_total, 4)}{X}')
    elif leaks:
        print(f'   {Y}→ jalankan ulang dengan --execute untuk memperbaiki{X}')

    # ══════════════════════════════════════════════════════════════════════════
    # C — order shipped/delivered yang masih menggenggam (LAPORAN, keputusan bisnis)
    # ══════════════════════════════════════════════════════════════════════════
    held = await db.marketing_orders.find(
        {'status': {'$in': ['shipped', 'delivered']},
         '$or': [{'stock_reserved': True}, {'reserved_rows.0': {'$exists': True}}]},
        {'_id': 0, 'id': 1, 'order_id': 1, 'status': 1, 'reserved_qty': 1,
         'fulfillment_status': 1}).to_list(5000)
    print(f'\n{BOLD}C. Order dikirim/terkirim yang masih menggenggam reservasi: '
          f'{Y if held else G}{len(held)}{X}  {DIM}(laporan saja){X}')
    for o in held[:20]:
        print(f'   {DIM}·{X} {o.get("order_id")}  status={o.get("status")}  '
              f'fulfillment={o.get("fulfillment_status")}  tertahan={_f(o.get("reserved_qty"))}')
    if held:
        print(f'   {Y}Artinya order ini diselesaikan di modul Toko saja, tanpa alur gudang, '
              f'jadi on-hand belum turun & HPP belum dijurnal.{X}')
        print(f'   {Y}Keputusan bisnis: (a) proses lewat /api/fulfillment/... supaya stok & '
              f'jurnal benar, atau (b) batalkan bila memang tidak pernah dikirim.{X}')

    # ══════════════════════════════════════════════════════════════════════════
    # B — reservasi YATIM (tidak bisa dijelaskan pemegang mana pun)
    # ══════════════════════════════════════════════════════════════════════════
    exp = await _explained_reserved(db)
    # Lingkup SENGAJA dibatasi ke material **FG**. Order Toko hanya pernah memesan
    # FG (`reserve_sellable` → `type: 'fg'`), sementara baris stok kain/aksesoris
    # dipesan oleh alur produksi/aksesoris yang TIDAK dicatat sebagai
    # `reserved_rows` di sini. Memasukkannya akan melahirkan "yatim" palsu — dan
    # `--fix-orphans` lalu akan MEMBEBASKAN reservasi produksi yang sah. Itu jauh
    # lebih berbahaya daripada tidak melaporkannya.
    fg_ids = {m['id'] for m in await db.rahaza_materials.find(
        {'type': 'fg'}, {'_id': 0, 'id': 1}).to_list(20000)}
    rows = await db[STOCK].find({'material_id': {'$in': list(fg_ids)}},
                                {'_id': 0}).to_list(20000)
    orphans = []
    for r in rows:
        actual = _f(r.get('reserved_quantity'))
        if actual <= 0.0001:
            continue
        explained = exp['by_row'].get(r.get('id'), 0.0)
        # reservasi yang sudah dilaporkan di temuan A (order batal/retur) BUKAN yatim
        leaked = exp['leaked_by_row'].get(r.get('id'), 0.0)
        # sisa reservasi tingkat-MATERIAL (FG Matrix) dipakai sebagai penjelas cadangan
        mat_left = exp['by_material'].get(r.get('material_id'), 0.0)
        unexplained = round(actual - explained - leaked - mat_left, 4)
        if unexplained > 0.0001:
            orphans.append({'stock_id': r.get('id'), 'material_id': r.get('material_id'),
                            'location_id': r.get('location_id'), 'reserved': actual,
                            'explained': round(explained + leaked + mat_left, 4),
                            'unexplained': unexplained})
    print(f'\n{BOLD}B. Reservasi YATIM (tak bisa dijelaskan): '
          f'{R if orphans else G}{len(orphans)} baris stok{X}'
          f'  {DIM}(lingkup: material FG saja — lihat komentar di kode){X}')
    for o in orphans[:20]:
        mat = await db.rahaza_materials.find_one({'id': o['material_id']},
                                                {'_id': 0, 'code': 1, 'name': 1}) or {}
        print(f'   {DIM}·{X} {mat.get("code") or o["material_id"]}  '
              f'reserved={o["reserved"]} dijelaskan={o["explained"]} '
              f'{R}yatim={o["unexplained"]}{X}')
    if orphans and not FIX_ORPHANS:
        print(f'   {Y}→ TIDAK diperbaiki otomatis. Reservasi yatim tidak punya catatan baris '
              f'asalnya, jadi melepasnya bisa membebaskan reservasi order yang masih hidup.{X}')
        print(f'   {Y}   Periksa daftar di atas, lalu jalankan: --execute --fix-orphans{X}')
    fixed_orphans = 0
    if orphans and EXECUTE and FIX_ORPHANS:
        from core import stock_service
        for o in orphans:
            try:
                await stock_service._release_row(o['stock_id'], o['unexplained'], db=db)
                fixed_orphans += 1
            except Exception as e:  # noqa: BLE001
                print(f'   {R}✗ gagal melepas {o["stock_id"]}: {e}{X}')
        print(f'   {G}✓ {fixed_orphans} baris stok yatim dibebaskan{X}')

    # ══════════════════════════════════════════════════════════════════════════
    print(f'\n{BOLD}RINGKASAN{X}')
    print(f'  A order bocor        : {len(leaks)}' + (f' → diperbaiki {repaired}' if EXECUTE else ''))
    print(f'  B baris stok yatim   : {len(orphans)}'
          + (f' → dibebaskan {fixed_orphans}' if (EXECUTE and FIX_ORPHANS) else ''))
    print(f'  C dikirim/terkirim   : {len(held)} (laporan)')
    if not EXECUTE and (leaks or orphans):
        print(f'  {Y}Belum ada perubahan ditulis (dry-run).{X}')
    # Verdict harus mencerminkan keadaan SETELAH pekerjaan ini, bukan sebelum —
    # laporan yang tetap merah padahal sudah diperbaiki melatih pembacanya
    # mengabaikan warna.
    leaks_left = len(leaks) - repaired
    orphans_left = len(orphans) - fixed_orphans
    verdict_clean = leaks_left == 0 and orphans_left == 0
    print('  status: ' + (f'{G}{BOLD}BERSIH{X}' if verdict_clean
                           else f'{Y}{BOLD}PERLU TINDAKAN{X} '
                                f'{DIM}(bocor sisa {leaks_left} · yatim sisa {orphans_left}){X}'))
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
