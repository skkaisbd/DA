"""
PT Rahaza — Production Calendar (Phase 22B)

Endpoints (prefix /api/rahaza):
  GET  /production-calendar                  — list entries (year, month filter)
  POST /production-calendar                  — create entry (holiday / exception day)
  PUT  /production-calendar/{id}             — update entry
  DELETE /production-calendar/{id}           — delete entry
  GET  /production-calendar/working-days     — count working days between dates
  POST /production-calendar/seed-national    — seed hari libur nasional Indonesia
"""
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth
from datetime import datetime, timezone, date, timedelta
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza", tags=["rahaza-production-calendar"])


def _uid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


# Hari libur nasional Indonesia 2026 (contoh — user bisa tambah/edit)
NATIONAL_HOLIDAYS_2026 = [
    {"date": "2026-01-01", "name": "Tahun Baru Masehi", "type": "holiday"},
    {"date": "2026-01-27", "name": "Isra Miraj Nabi Muhammad SAW", "type": "holiday"},
    {"date": "2026-01-29", "name": "Tahun Baru Imlek", "type": "holiday"},
    {"date": "2026-03-14", "name": "Hari Raya Nyepi", "type": "holiday"},
    {"date": "2026-03-20", "name": "Wafat Yesus Kristus", "type": "holiday"},
    {"date": "2026-04-02", "name": "Cuti Bersama Lebaran", "type": "holiday"},
    {"date": "2026-04-03", "name": "Cuti Bersama Lebaran", "type": "holiday"},
    {"date": "2026-04-06", "name": "Hari Raya Idul Fitri", "type": "holiday"},
    {"date": "2026-04-07", "name": "Hari Raya Idul Fitri", "type": "holiday"},
    {"date": "2026-04-08", "name": "Cuti Bersama Idul Fitri", "type": "holiday"},
    {"date": "2026-04-09", "name": "Cuti Bersama Idul Fitri", "type": "holiday"},
    {"date": "2026-05-01", "name": "Hari Buruh Internasional", "type": "holiday"},
    {"date": "2026-05-14", "name": "Kenaikan Yesus Kristus", "type": "holiday"},
    {"date": "2026-05-24", "name": "Hari Raya Waisak", "type": "holiday"},
    {"date": "2026-06-01", "name": "Hari Lahir Pancasila", "type": "holiday"},
    {"date": "2026-06-13", "name": "Hari Raya Idul Adha", "type": "holiday"},
    {"date": "2026-07-03", "name": "Tahun Baru Islam 1448 H", "type": "holiday"},
    {"date": "2026-08-17", "name": "Hari Kemerdekaan RI", "type": "holiday"},
    {"date": "2026-09-12", "name": "Maulid Nabi Muhammad SAW", "type": "holiday"},
    {"date": "2026-12-25", "name": "Hari Raya Natal", "type": "holiday"},
]


@router.get("/production-calendar")
async def list_calendar(
    request: Request,
    year: Optional[int] = None,
    month: Optional[int] = None,
    type_: Optional[str] = Query(None, alias="type", description="holiday | exception | special"),
):
    """List production calendar entries."""
    await require_auth(request)
    db = get_db()

    q = {}
    if year:
        q["year"] = year
    if month:
        q["month"] = month
    if type_:
        q["type"] = type_

    entries = await db.rahaza_production_calendar.find(q, {"_id": 0}).sort("date", 1).to_list(500)
    return entries


@router.post("/production-calendar")
async def create_calendar_entry(request: Request):
    """
    Create production calendar entry.
    Body: {date (YYYY-MM-DD), name, type (holiday|exception|special), notes, affects_shifts}
    type:
      holiday  — hari libur (tidak produksi)
      exception — hari kerja tidak biasa (half day, dll)
      special  — catatan khusus (audit, tamu buyer, dll)
    """
    user = await require_auth(request)
    db = get_db()

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    entry_date = body.get("date", "").strip()
    name = body.get("name", "").strip()
    entry_type = body.get("type", "holiday")

    if not entry_date or not name:
        raise HTTPException(400, "date dan name wajib diisi")
    if entry_type not in ("holiday", "exception", "special"):
        raise HTTPException(400, "type harus: holiday | exception | special")

    try:
        d = date.fromisoformat(entry_date)
    except ValueError:
        raise HTTPException(400, "Format date harus YYYY-MM-DD")

    existing = await db.rahaza_production_calendar.find_one({"date": entry_date})
    if existing:
        raise HTTPException(409, f"Sudah ada entri untuk tanggal {entry_date}")

    doc = {
        "id": _uid(),
        "date": entry_date,
        "year": d.year,
        "month": d.month,
        "day": d.day,
        "weekday": d.strftime("%A"),
        "name": name,
        "type": entry_type,
        "notes": body.get("notes", ""),
        "affects_shifts": body.get("affects_shifts", []),
        "created_at": _now().isoformat(),
        "created_by": user.get("id"),
        "created_by_name": user.get("name", user.get("email")),
    }
    await db.rahaza_production_calendar.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/production-calendar/{entry_id}")
async def update_calendar_entry(entry_id: str, request: Request):
    """Update calendar entry."""
    user = await require_auth(request)
    db = get_db()

    entry = await db.rahaza_production_calendar.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(404, "Entri tidak ditemukan")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    updates = {}
    for field in ("name", "type", "notes", "affects_shifts"):
        if field in body:
            updates[field] = body[field]

    if updates:
        updates["updated_at"] = _now().isoformat()
        updates["updated_by"] = user.get("id")
        await db.rahaza_production_calendar.update_one({"id": entry_id}, {"$set": updates})

    updated = await db.rahaza_production_calendar.find_one({"id": entry_id}, {"_id": 0})
    return updated


@router.delete("/production-calendar/{entry_id}")
async def delete_calendar_entry(entry_id: str, request: Request):
    """Delete calendar entry."""
    await require_auth(request)
    db = get_db()

    result = await db.rahaza_production_calendar.delete_one({"id": entry_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Entri tidak ditemukan")

    return {"ok": True, "entry_id": entry_id}


@router.get("/production-calendar/working-days")
async def get_working_days(
    request: Request,
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    include_saturday: bool = Query(False),
):
    """
    Calculate working days between two dates.
    Excludes Sundays and production calendar holidays.
    """
    await require_auth(request)
    db = get_db()

    try:
        d_from = date.fromisoformat(from_date)
        d_to = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(400, "Format date harus YYYY-MM-DD")

    if d_from > d_to:
        raise HTTPException(400, "from_date harus sebelum to_date")

    # Get all holidays in range
    holidays = await db.rahaza_production_calendar.find(
        {"date": {"$gte": from_date, "$lte": to_date}, "type": "holiday"},
        {"date": 1}
    ).to_list(500)
    holiday_set = {h["date"] for h in holidays}

    total_days = 0
    working_days = 0
    holiday_count = 0
    weekend_count = 0

    current = d_from
    while current <= d_to:
        total_days += 1
        is_sunday = current.weekday() == 6
        is_saturday = current.weekday() == 5
        is_holiday = current.isoformat() in holiday_set
        is_working = not is_sunday and not is_holiday and (include_saturday or not is_saturday)

        if is_working:
            working_days += 1
        if is_holiday:
            holiday_count += 1
        if is_sunday or (is_saturday and not include_saturday):
            weekend_count += 1

        current += timedelta(days=1)

    return {
        "from_date": from_date,
        "to_date": to_date,
        "total_calendar_days": total_days,
        "working_days": working_days,
        "holidays": holiday_count,
        "weekends_excluded": weekend_count,
        "include_saturday": include_saturday,
    }


@router.post("/production-calendar/seed-national")
async def seed_national_holidays(request: Request):
    """Seed hari libur nasional Indonesia 2026."""
    await require_auth(request)
    db = get_db()

    seeded = 0
    skipped = 0
    # Batch prefetch existing holiday dates
    target_dates = [h["date"] for h in NATIONAL_HOLIDAYS_2026]
    existing_dates = set()
    if target_dates:
        async for d in db.rahaza_production_calendar.find(
            {"date": {"$in": target_dates}}, {"_id": 0, "date": 1}
        ):
            existing_dates.add(d["date"])
    docs_to_insert = []
    for h in NATIONAL_HOLIDAYS_2026:
        if h["date"] in existing_dates:
            skipped += 1
            continue
        d = date.fromisoformat(h["date"])
        docs_to_insert.append({
            "id": _uid(),
            "date": h["date"],
            "year": d.year,
            "month": d.month,
            "day": d.day,
            "weekday": d.strftime("%A"),
            "name": h["name"],
            "type": h["type"],
            "notes": "Hari libur nasional Indonesia 2026",
            "affects_shifts": [],
            "created_at": _now().isoformat(),
            "created_by": "system",
            "created_by_name": "System",
        })
        seeded += 1
    if docs_to_insert:
        await db.rahaza_production_calendar.insert_many(docs_to_insert)

    return {"ok": True, "seeded": seeded, "skipped": skipped}
