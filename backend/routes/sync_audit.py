"""routes/sync_audit.py — **Kesehatan Sinkronisasi Data** lintas portal (Sesi #20).

Memindahkan skrip forensik agent ke dalam aplikasi supaya pemilik bisa mengukur
sendiri, kapan saja — bukan menunggu sesi pengembangan berikutnya.

Endpoint (prefix ``/api/sync-audit``):
  GET  /report            — laporan A–E + verdict + skor
  GET  /repairs           — daftar perbaikan yang tersedia + penjelasannya
  POST /repair            — jalankan perbaikan (bawaan PRATINJAU/dry-run)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import log_activity, require_auth
from core import sync_audit
from database import get_db

router = APIRouter(prefix='/api/sync-audit', tags=['sync-audit'])


class RepairIn(BaseModel):
    action: str = Field(..., description='Kunci perbaikan (lihat GET /repairs)')
    apply: bool = Field(default=False, description='False = pratinjau, tidak menulis apa pun')


@router.get('/report')
async def report(user: dict = Depends(require_auth)):
    """Laporan kesehatan sinkronisasi data — dihitung dari data hidup."""
    db = get_db()
    return await sync_audit.build_report(db)


@router.get('/repairs')
async def repairs(user: dict = Depends(require_auth)):
    return {'repairs': [{'action': k, **v} for k, v in sync_audit.REPAIRS.items()]}


@router.post('/repair')
async def repair(body: RepairIn, user: dict = Depends(require_auth)):
    """Jalankan perbaikan. **Bawaan pratinjau** — kirim `apply: true` untuk menulis."""
    db = get_db()
    res = await sync_audit.run_repair(db, body.action, dry_run=not body.apply, user=user)
    if not res.get('ok'):
        raise HTTPException(res.get('status', 400), res.get('message', 'Perbaikan gagal.'))
    if body.apply:
        await log_activity(user.get('id', ''), user.get('name', ''),
                          f"Perbaikan sinkronisasi '{body.action}': {res.get('affected', 0)} dokumen",
                          'sync-audit', body.action)
    return res
