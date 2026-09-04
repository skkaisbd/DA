"""HR aggregates for AI endpoints."""
from __future__ import annotations

from datetime import datetime


async def attendance_issues(db, *, since: datetime) -> int:
    """Count attendance records with late/absent status since date."""
    return await db.rahaza_attendance.count_documents(
        {"date": {"$gte": since.strftime("%Y-%m-%d")}, "status": {"$in": ["late", "absent"]}}
    )


async def production_employee_count(db) -> int:
    """Active employees in production departments."""
    return await db.rahaza_employees.count_documents({
        "employment_status": "active",
        "department": {"$in": ["Produksi", "Production", "Jahit"]},
    })
