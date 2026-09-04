#!/usr/bin/env python3
"""migrations/add_closed_at_to_production_jobs.py — backfill ``closed_at`` (fase 5).

═══════════════════════════════════════════════════════════════════════════════
KENAPA MIGRASI INI ADA
═══════════════════════════════════════════════════════════════════════════════
Rekap Harian/Mingguan CMT menjawab "apa yang MENUNGGU pada akhir tanggal X". Untuk
kolom Progress Produksi, "menunggu" = ada **job yang sedang jalan**. Sejak fase 5,
job menyimpan ``closed_at`` (ditulis SERVER lewat
``core.production_job_lifecycle.close_job``) sehingga job yang ditutup Rabu tetap
terhitung sebagai job jalan pada hari Senin — kelalaian yang sudah terjadi tidak
lagi terhapus sendiri.

Job yang **sudah tertutup sebelum fitur itu ada** tidak punya ``closed_at``.
Untuk dokumen itu waktu tutupnya tidak diketahui, dan
``core.production_job_lifecycle.was_open_at`` sengaja mengembalikan ``False``
(perilaku lama) alih-alih menebak diam-diam. Migrasi inilah yang memperbaikinya.

═══════════════════════════════════════════════════════════════════════════════
PERKIRAAN YANG DIPAKAI — DAN KENAPA IA DITANDAI
═══════════════════════════════════════════════════════════════════════════════
Waktu tutup yang sebenarnya **tidak tersimpan di mana pun**, jadi ia diperkirakan
dari ``updated_at``: kedua jalur penutup job (auto-complete di
``production_execution.py`` dan Quick Complete di ``production_pos.py``) SELALU
menulis ``updated_at`` pada saat menutup, dan job yang sudah tertutup hampir tidak
pernah disentuh lagi sesudahnya. Jadi ``updated_at`` adalah penanda terbaik yang
tersedia — tetapi ia tetap **perkiraan**.

Karena itu setiap dokumen hasil migrasi diberi ``closed_at_estimated: True``:

* laporan/auditor bisa membedakan stempel **teramati** dari **perkiraan**;
* ``close_job()`` boleh MENGGANTI stempel perkiraan dengan pengamatan sungguhan
  (stempel teramati tidak pernah ditimpa).

Kalau ``updated_at`` juga tidak ada, dipakai ``created_at``; kalau keduanya tidak
ada, dokumen **dilewati** dan dilaporkan — lebih baik jujur tidak tahu daripada
mengarang tanggal untuk laporan yang dipakai memverifikasi tagihan.

Idempoten: dokumen yang sudah punya ``closed_at`` tidak disentuh.

Pakai::

    cd /app/backend && python3 migrations/add_closed_at_to_production_jobs.py            # dry-run
    cd /app/backend && python3 migrations/add_closed_at_to_production_jobs.py --execute
    cd /app/backend && python3 migrations/add_closed_at_to_production_jobs.py --report    # ringkas saja
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from core.production_job_lifecycle import (JOB_CLOSED_STATUSES,  # noqa: E402
                                           needs_closed_at_backfill)
from utils.waktu import as_aware_utc  # noqa: E402

G, R, Y, B, X = '\033[92m', '\033[91m', '\033[93m', '\033[94m', '\033[0m'


async def run(execute: bool, report_only: bool) -> int:
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f'{B}{"=" * 78}{X}')
    print(f'  {B}BACKFILL closed_at pada production_jobs{X}  (DB={db_name})')
    print(f'  mode: {"EKSEKUSI" if execute else "DRY-RUN (tidak menulis apa pun)"}')
    print(f'{B}{"=" * 78}{X}')

    total = await db.production_jobs.count_documents({})
    closed = await db.production_jobs.count_documents({'status': {'$in': list(JOB_CLOSED_STATUSES)}})
    have = await db.production_jobs.count_documents({'closed_at': {'$exists': True, '$ne': None}})
    estimated = await db.production_jobs.count_documents({'closed_at_estimated': True})

    print(f'  job total                        : {total}')
    print(f'  job berstatus tertutup           : {closed}')
    print(f'  sudah punya closed_at            : {have}  (perkiraan: {estimated})')

    jobs = await db.production_jobs.find(
        {'status': {'$in': list(JOB_CLOSED_STATUSES)}},
        {'_id': 0, 'id': 1, 'job_number': 1, 'status': 1, 'created_at': 1,
         'updated_at': 1, 'closed_at': 1},
    ).to_list(None)

    todo = [j for j in jobs if needs_closed_at_backfill(j)]
    print(f'  {Y}perlu backfill                   : {len(todo)}{X}')

    if report_only or not todo:
        if not todo:
            print(f'\n  {G}✓ Tidak ada yang perlu di-backfill — semua job tertutup sudah '
                  f'punya stempel waktu tutup.{X}')
        client.close()
        return 0

    filled, skipped = 0, []
    for j in todo:
        est = as_aware_utc(j.get('updated_at')) or as_aware_utc(j.get('created_at'))
        if est is None:
            # Tidak ada satu pun penanda waktu ⇒ JANGAN mengarang.
            skipped.append(j.get('job_number') or j.get('id'))
            continue
        label = f"{j.get('job_number') or j.get('id')} [{j.get('status')}]"
        src = 'updated_at' if j.get('updated_at') else 'created_at'
        print(f'    · {label:28s} closed_at ← {est.isoformat()}  (perkiraan dari {src})')
        if execute:
            await db.production_jobs.update_one(
                {'id': j['id'],
                 '$or': [{'closed_at': {'$exists': False}}, {'closed_at': None}]},
                {'$set': {'closed_at': est, 'closed_at_estimated': True}},
            )
        filled += 1

    print()
    if execute:
        print(f'  {G}✓ {filled} job diberi closed_at (ditandai closed_at_estimated=True){X}')
        sisa = await db.production_jobs.count_documents(
            {'status': {'$in': list(JOB_CLOSED_STATUSES)},
             '$or': [{'closed_at': {'$exists': False}}, {'closed_at': None}]})
        print(f'  sisa job tertutup tanpa closed_at : {sisa}')
    else:
        print(f'  {Y}DRY-RUN: {filled} job AKAN diberi closed_at. Jalankan ulang dengan '
              f'--execute untuk menulis.{X}')

    if skipped:
        print(f'  {R}! {len(skipped)} job DILEWATI (tidak punya updated_at maupun '
              f'created_at — tidak ditebak): {", ".join(map(str, skipped[:10]))}{X}')

    client.close()
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--execute', action='store_true', help='benar-benar menulis ke DB')
    ap.add_argument('--report', action='store_true', help='hanya laporkan jumlah, tanpa daftar')
    a = ap.parse_args()
    sys.exit(asyncio.run(run(a.execute, a.report)))
