"""marketing_reports_weekly — LAPORAN RAPAT MINGGUAN (per toko + gabungan).

    GET /api/marketing/reports/weekly?week_start=YYYY-MM-DD&account_id=
    GET /api/marketing/reports/weekly/export-pdf?...
    GET /api/marketing/reports/weekly/export-excel?...

Seluruh isinya dihitung oleh **satu** modul (`core.marketing_weekly_report`);
layar, PDF, dan Excel memakai hasil yang sama supaya tidak pernah ada tiga angka
untuk satu minggu. Lihat docstring modul itu untuk sumber tiap angka dan alasan
kenapa `catatan_data` wajib ikut.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from auth import require_auth, serialize_doc
from core import marketing_weekly_report as _wk
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/reports", tags=["marketing-reports-weekly"])

COMPANY = "CV. DEWI ADITYA"


async def _report(request: Request, week_start: Optional[str], account_id: Optional[str]):
    user = await require_auth(request)
    db = get_db()
    # F6 (sesi #9) — laporan rapat WAJIB berlingkup: staf pemegang satu toko tidak
    # boleh melihat omzet & biaya delapan toko lain di lampiran rapat.
    from core import marketing_account_scope as _scope
    if account_id:
        await _scope.assert_account_visible(db, user, account_id)
    visible = await _scope.visible_account_ids(db, user)
    try:
        return await _wk.build_weekly_report(db, week_start, account_id,
                                            account_ids=visible)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@router.get("/weekly")
async def weekly_report(
    request: Request,
    week_start: Optional[str] = Query(None, description="tanggal apa pun dalam minggu itu (YYYY-MM-DD); kosong = minggu berjalan"),
    account_id: Optional[str] = Query(None, description="kosong = semua toko + gabungan"),
):
    """Isi laporan rapat mingguan: per toko, gabungan, dan catatan kejujuran data."""
    return serialize_doc(await _report(request, week_start, account_id))


@router.get("/weekly/export-excel")
async def weekly_report_excel(
    request: Request,
    week_start: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
):
    """Excel 3 lembar: Ringkas per Toko · Pecahan Kanal · Catatan Data."""
    report = await _report(request, week_start, account_id)
    from utils.marketing_weekly_export import build_excel
    data, fname = build_excel(company=COMPANY, report=report)
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/weekly/export-pdf")
async def weekly_report_pdf(
    request: Request,
    week_start: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
):
    """PDF lanskap siap cetak untuk rapat (KPI gabungan + tabel per toko + catatan)."""
    report = await _report(request, week_start, account_id)
    from utils.marketing_weekly_export import build_pdf
    data, fname = build_pdf(company=COMPANY, report=report)
    return StreamingResponse(
        iter([data]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
