#!/usr/bin/env python3
"""Transform sekali-jalan (P3): `datetime.now()` naive → WIB (SSOT utils/waktu).

Dipakai SEKALI pada 2026-08-07 untuk menutup Prioritas 3 backlog ("27 titik
datetime naive"). Setiap lokasi sudah diperiksa manual lebih dulu dan semuanya
hanya memakai hasilnya untuk `.strftime()`, `.year`, `.month`, atau default
parameter tanggal — jadi TIDAK ada datetime naive yang disimpan ke database
(penyimpanan tetap UTC aware lewat `now_utc()`/`datetime.now(timezone.utc)`).

Skrip ini disimpan sebagai jejak audit, bukan untuk dijalankan berulang.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BE = Path("/app/backend")

# `datetime.now()` → `now_wib()` (tanggal kalender & tampilan lokal)
FILES_NOW = [
    "routes/dewi_production_reports.py",
    "routes/admin_backup.py",
    "routes/employee_expense_claims.py",
    "routes/rahaza_admin_helpers.py",
    "routes/employee_per_diem.py",
    "routes/marketing_ai_insights_routes.py",
    "routes/dewi_rnd_overview.py",
    "routes/employee_travel_settlements.py",
    "routes/operations_pdf_helpers.py",
    "routes/operations_excel.py",
    "routes/buyer_shipment.py",
    "routes/operations_pdf.py",
    "routes/rahaza_360_feedback.py",
    "routes/production_pos.py",
    "routes/data_transfer.py",
    "routes/dewi_kpi_reports.py",
    "routes/employee_travel_requests.py",
    "utils/monthly_report_pdf.py",
    "utils/livehost_sop_pdf.py",
    "utils/qrcode_generator.py",
]

# `datetime.now().year` → `wib_year()` (periode cuti/payroll)
FILES_YEAR = [
    "routes/rahaza_leave.py",
    "routes/rahaza_leave_balances.py",
    "services/leave_service.py",
]

# `datetime.utcnow()` → `now_wib()` (stempel nama berkas dibaca manusia)
FILES_UTCNOW = ["storage.py"]

IMPORT_RE = re.compile(r"^(from|import)\s+\S")


def ensure_import(lines: list[str], simbol: str) -> list[str]:
    """Tambahkan `from utils.waktu import <simbol>` bila belum ada."""
    for ln in lines:
        if "from utils.waktu import" in ln:
            if simbol in ln:
                return lines
            # gabungkan ke import yang sudah ada
            idx = lines.index(ln)
            nama = ln.split("import", 1)[1].strip()
            lines[idx] = f"from utils.waktu import {nama}, {simbol}\n"
            return lines
    # cari baris import terakhir yang BUKAN di dalam docstring
    last = -1
    dq = 0
    for i, ln in enumerate(lines[:80]):
        dq += ln.count('"""') + ln.count("'''")
        if dq % 2 == 1:
            continue
        if IMPORT_RE.match(ln):
            last = i
    if last < 0:
        raise RuntimeError("tidak menemukan blok import")
    lines.insert(last + 1, f"from utils.waktu import {simbol}\n")
    return lines


def transform(rel: str, pola: str, ganti: str, simbol: str) -> tuple[int, str]:
    p = BE / rel
    src = p.read_text(encoding="utf-8")
    n = src.count(pola)
    if n == 0:
        return 0, "tidak ada pola"
    src = src.replace(pola, ganti)
    lines = ensure_import(src.splitlines(keepends=True), simbol)
    p.write_text("".join(lines), encoding="utf-8")
    return n, "ok"


def main() -> int:
    total = 0
    for rel in FILES_YEAR:  # paling spesifik dulu
        n, msg = transform(rel, "datetime.now().year", "wib_year()", "wib_year")
        total += n
        print(f"  {n:2d}x wib_year()  {rel}  [{msg}]")
    for rel in FILES_NOW:
        n, msg = transform(rel, "datetime.now()", "now_wib()", "now_wib")
        total += n
        print(f"  {n:2d}x now_wib()   {rel}  [{msg}]")
    for rel in FILES_UTCNOW:
        n, msg = transform(rel, "datetime.utcnow()", "now_wib()", "now_wib")
        total += n
        print(f"  {n:2d}x now_wib()   {rel}  [{msg}]")
    print(f"TOTAL titik diperbaiki: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
