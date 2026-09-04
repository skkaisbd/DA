"""wms_stock_schema — FASE 6.6-A: kesehatan & rekonsiliasi skema baris stok (A/B/C).

Endpoint (prefix /api/wms/stock-schema):
  GET  /health              → diagnosa read-only (siapa pun yang login)
  POST /reconcile           → rencana (dry_run=true, DEFAULT) atau eksekusi (dry_run=false) — ADMIN
  POST /reconcile/rollback  → balikkan satu eksekusi via log_id — ADMIN
  GET  /logs                → riwayat eksekusi rekonsiliasi

Kenapa terpisah dari `/api/wms/stock/*` (wms_receiving): supaya tidak bertabrakan
dengan `POST /api/wms/stock/reset-all` dan agar domain "integritas skema" jelas.

Rekonsiliasi TIDAK PERNAH mengubah total on-hand per material — hanya membenahi
BENTUK baris (lokasi datar, alias qty, available), MEMINDAHKAN baris yang duduk di
lokasi bukan-zona-penyimpanan ke zona kanonik sesuai kategori material (FASE 12,
penyakit `unmapped_location`), dan menggabungkan baris kembar.
Selalu ada jurnal `wh_stock_schema_reconcile_log` untuk rollback presisi.
"""
from fastapi import APIRouter, Request, HTTPException, Query
import logging

from database import get_db
from auth import require_auth, check_role, log_activity, serialize_doc
from core import stock_reconcile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wms/stock-schema", tags=["wms-stock-schema"])

# Rekonsiliasi = operasi struktural pada ledger stok ⇒ hanya penanggung jawab sistem.
# `check_role` otomatis meloloskan `superadmin`.
RECONCILE_ROLES = ["admin", "owner", "admin_gudang", "manager", "manajer"]
PERM_KEY = "inv.stock.manage"

_FORBIDDEN = (
    "Rekonsiliasi skema stok mengubah struktur baris ledger. "
    "Hanya Admin, Admin Gudang, atau Owner yang boleh menjalankannya — "
    "silakan ajukan ke penanggung jawab sistem."
)


def _guard(user: dict):
    if not check_role(user, RECONCILE_ROLES, PERM_KEY):
        raise HTTPException(403, _FORBIDDEN)


@router.get("/health")
async def schema_health(request: Request, detail_limit: int = Query(100, ge=1, le=500)):
    """Diagnosa kesehatan skema baris stok — READ ONLY, aman dipanggil kapan saja."""
    await require_auth(request)
    db = get_db()
    report = await stock_reconcile.scan(db, detail_limit=detail_limit)
    return serialize_doc(report)


@router.post("/reconcile")
async def schema_reconcile(request: Request):
    """Rekonsiliasi baris stok. Body: `{"dry_run": true|false}` (default true = pratinjau)."""
    user = await require_auth(request)
    _guard(user)
    db = get_db()
    try:
        body = await request.json()
    except Exception:
        body = {}
    dry_run = body.get("dry_run")
    dry_run = True if dry_run is None else bool(dry_run)

    result = await stock_reconcile.reconcile(db, dry_run=dry_run, actor=user)
    if not dry_run and result.get("applied"):
        await log_activity(
            user.get("id", ""), user.get("name", ""),
            "stock_schema_reconcile", "Gudang",
            f"log={result.get('log_id')} normalized={result['summary'].get('rows_normalized')} "
            f"merged={result['summary'].get('rows_merged')}",
        )
    return serialize_doc(result)


@router.post("/reconcile/rollback")
async def schema_reconcile_rollback(request: Request):
    """Balikkan satu eksekusi rekonsiliasi. Body: `{"log_id": "..."}`."""
    user = await require_auth(request)
    _guard(user)
    db = get_db()
    try:
        body = await request.json()
    except Exception:
        body = {}
    log_id = (body.get("log_id") or "").strip()
    if not log_id:
        raise HTTPException(400, "log_id wajib diisi.")
    result = await stock_reconcile.rollback(db, log_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "Rollback gagal.")
    await log_activity(
        user.get("id", ""), user.get("name", ""),
        "stock_schema_reconcile_rollback", "Gudang",
        f"log={log_id} restored={result.get('rows_restored')} reinserted={result.get('rows_reinserted')}",
    )
    return serialize_doc(result)


@router.get("/logs")
async def schema_reconcile_logs(request: Request, limit: int = Query(20, ge=1, le=100)):
    """Riwayat eksekusi rekonsiliasi (payload before/after tidak disertakan)."""
    await require_auth(request)
    db = get_db()
    return serialize_doc(await stock_reconcile.logs(db, limit=limit))
