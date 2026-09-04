"""
HR Shift Management Service — Task 1.2
CV. Dewi Aditya

Logika bisnis:
- Create/update/delete shift templates (MORNING, EVENING, NIGHT, dll)
- Assign shift ke employee dengan effective_from/until
- Get employee active shift untuk tanggal tertentu (dengan fallback DEFAULT)
- Calculate work hours + overtime based on shift rules
- Detect shift overlap dalam assignment
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, time, timedelta
from typing import Dict, List, Optional
from utils.counters import next_counter

logger = logging.getLogger(__name__)

# Default shift ketika employee belum punya assignment
DEFAULT_SHIFT = {
    "id": "default",
    "shift_code": "DEFAULT",
    "shift_name": "Shift Default (08:00-17:00)",
    "start_time": "08:00",
    "end_time": "17:00",
    "break_duration_minutes": 60,
    "effective_hours": 8.0,
    "days_active": ["Mon", "Tue", "Wed", "Thu", "Fri"],
    "is_default": True,
    "color": "#64748b",
    "status": "active",
}

# Seed data
DEFAULT_SHIFT_TEMPLATES: List[Dict] = [
    {
        "shift_code": "PAGI",
        "shift_name": "Shift Pagi",
        "start_time": "07:00",
        "end_time": "15:00",
        "break_duration_minutes": 60,
        "effective_hours": 7.0,
        "days_active": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "color": "#f59e0b",
        "description": "Shift pagi untuk produksi",
    },
    {
        "shift_code": "SIANG",
        "shift_name": "Shift Siang",
        "start_time": "15:00",
        "end_time": "23:00",
        "break_duration_minutes": 60,
        "effective_hours": 7.0,
        "days_active": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "color": "#3b82f6",
        "description": "Shift siang/sore",
    },
    {
        "shift_code": "MALAM",
        "shift_name": "Shift Malam",
        "start_time": "23:00",
        "end_time": "07:00",
        "break_duration_minutes": 60,
        "effective_hours": 7.0,
        "days_active": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "color": "#8b5cf6",
        "description": "Shift malam (24-jam operation)",
        "is_overnight": True,
    },
    {
        "shift_code": "NORMAL",
        "shift_name": "Jam Kerja Normal",
        "start_time": "08:00",
        "end_time": "17:00",
        "break_duration_minutes": 60,
        "effective_hours": 8.0,
        "days_active": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "color": "#10b981",
        "description": "Jam kerja kantor normal",
    },
    {
        "shift_code": "FLEKSIBEL",
        "shift_name": "Shift Fleksibel",
        "start_time": "08:00",
        "end_time": "16:00",
        "break_duration_minutes": 60,
        "effective_hours": 7.0,
        "days_active": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "color": "#ec4899",
        "description": "Jadwal fleksibel untuk tim kreatif / marketing",
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── BACKLOG-B: `rahaza_shifts` = KOLEKSI KANONIK shift (dipakai attendance, APS
# scheduler, line assignments — coupling 10). Modul HR Shifts di-repoint ke sana.
# Dok kanonik: {id(uuid), code, name, start_time, end_time, check_in_time,
# check_out_time, working_hours, active}. Field HR (break/days/color/dst.) disimpan
# ADDITIVE di dok yang sama — pembaca kanonik tidak terganggu.

def _active_shift_query(status: Optional[str] = "active") -> Dict:
    """Filter yang kompatibel dgn dok kanonik lama (active bool) & dok HR (status str)."""
    if status == "active":
        return {"$or": [{"status": "active"}, {"active": True, "status": {"$exists": False}}]}
    if status:
        return {"$or": [{"status": status}, {"active": status == "active"}]}
    return {}


def _to_hr_shape(doc: Dict) -> Dict:
    """Normalisasi dok rahaza_shifts (kanonik/legacy) ke bentuk yang dipakai UI HR Shifts."""
    if not doc:
        return doc
    d = {k: v for k, v in doc.items() if k != "_id"}
    d["shift_code"] = d.get("shift_code") or d.get("code") or ""
    d["shift_name"] = d.get("shift_name") or d.get("name") or ""
    d.setdefault("break_duration_minutes", 60)
    if d.get("effective_hours") is None:
        d["effective_hours"] = d.get("working_hours", 8.0)
    d.setdefault("days_active", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
    d.setdefault("is_overnight", False)
    d.setdefault("is_default", False)
    d.setdefault("color", "#64748b")
    d.setdefault("description", "")
    if not d.get("status"):
        d["status"] = "active" if d.get("active", True) else "inactive"
    return d


def _parse_time(t: str) -> time:
    """Parse 'HH:MM' string to time object."""
    h, m = map(int, t.split(":"))
    return time(h, m)


def _minutes_between(start: str, end: str, overnight: bool = False) -> int:
    """Hitung menit antara dua waktu HH:MM. Jika overnight, tambah 24 jam."""
    st = _parse_time(start)
    et = _parse_time(end)
    s_min = st.hour * 60 + st.minute
    e_min = et.hour * 60 + et.minute
    if overnight or e_min <= s_min:
        e_min += 24 * 60
    return e_min - s_min


def _calc_effective_hours(start: str, end: str, break_min: int, overnight: bool = False) -> float:
    total_min = _minutes_between(start, end, overnight)
    return round((total_min - break_min) / 60, 2)


async def seed_default_shifts(db) -> None:
    """Seed shift templates ke rahaza_shifts (kanonik) — IDEMPOTENT by code, TANPA delete
    (JANGAN pernah menghapus shift kanonik: dipakai attendance/APS)."""
    import uuid as _uuid
    existing_codes = set()
    async for d in db.rahaza_shifts.find({}, {"_id": 0, "code": 1, "shift_code": 1}):
        if d.get("code"):
            existing_codes.add(d["code"])
        if d.get("shift_code"):
            existing_codes.add(d["shift_code"])
    now = _now().isoformat()
    seeded = 0
    for tmpl in DEFAULT_SHIFT_TEMPLATES:
        if tmpl["shift_code"] in existing_codes:
            continue
        overnight = tmpl.get("is_overnight", False)
        eff = _calc_effective_hours(
            tmpl["start_time"], tmpl["end_time"],
            tmpl.get("break_duration_minutes", 60), overnight)
        doc = {
            "id": str(_uuid.uuid4()),
            # ── field kanonik rahaza_shifts ──
            "code": tmpl["shift_code"],
            "name": tmpl["shift_name"],
            "start_time": tmpl["start_time"],
            "end_time": tmpl["end_time"],
            "check_in_time": tmpl["start_time"],
            "check_out_time": tmpl["end_time"],
            "working_hours": eff,
            "active": True,
            # ── field tambahan HR (additive) ──
            "shift_code": tmpl["shift_code"],
            "shift_name": tmpl["shift_name"],
            "break_duration_minutes": tmpl.get("break_duration_minutes", 60),
            "effective_hours": eff,
            "days_active": tmpl["days_active"],
            "is_overnight": overnight,
            "is_default": False,
            "color": tmpl.get("color", "#64748b"),
            "description": tmpl.get("description", ""),
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        await db.rahaza_shifts.insert_one(doc)
        seeded += 1
    logger.info("Seeded %d default HR shifts into rahaza_shifts (canonical).", seeded)


async def create_shift(db, data: Dict) -> Dict:
    """Buat shift template baru di rahaza_shifts (kanonik)."""
    import uuid as _uuid
    # Validate time format
    try:
        _parse_time(data["start_time"])
        _parse_time(data["end_time"])
    except Exception:
        raise ValueError("Format waktu tidak valid. Gunakan HH:MM.")

    code = (data.get("shift_code") or "").upper()
    dup = await db.rahaza_shifts.find_one(
        {"$or": [{"code": code}, {"shift_code": code}]}, {"_id": 0, "id": 1})
    if dup:
        raise ValueError(f"Kode shift '{code}' sudah dipakai.")

    now = _now().isoformat()
    overnight = data.get("is_overnight", False)
    eff = _calc_effective_hours(
        data["start_time"], data["end_time"],
        int(data.get("break_duration_minutes", 60)), overnight)
    doc = {
        "id": str(_uuid.uuid4()),
        # kanonik
        "code": code,
        "name": data.get("shift_name") or "",
        "start_time": data["start_time"],
        "end_time": data["end_time"],
        "check_in_time": data["start_time"],
        "check_out_time": data["end_time"],
        "working_hours": eff,
        "active": True,
        # tambahan HR
        "shift_code": code,
        "shift_name": data.get("shift_name") or "",
        "break_duration_minutes": int(data.get("break_duration_minutes", 60)),
        "effective_hours": eff,
        "days_active": data.get("days_active", ["Mon", "Tue", "Wed", "Thu", "Fri"]),
        "is_overnight": overnight,
        "is_default": bool(data.get("is_default", False)),
        "color": data.get("color", "#64748b"),
        "description": data.get("description", ""),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await db.rahaza_shifts.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


async def assign_shift(
    db,
    employee_id: str,
    shift_id,
    effective_from: str,
    effective_until: Optional[str],
    assigned_by: str,
    department: str = "",
    notes: str = "",
) -> Dict:
    """Assign shift ke employee. Menonaktifkan assignment aktif sebelumnya."""
    # Verify shift exists — BACKLOG-B: kanonik rahaza_shifts
    _id = int(shift_id) if str(shift_id).isdigit() else shift_id
    shift_raw = await db.rahaza_shifts.find_one(
        {"id": _id, **_active_shift_query("active")}, {"_id": 0})
    if not shift_raw:
        raise ValueError(f"Shift ID {shift_id!r} tidak ditemukan atau tidak aktif.")
    shift = _to_hr_shape(shift_raw)

    # Deactivate previous active assignment for same employee
    await db.hr_shift_assignments.update_many(
        {"employee_id": employee_id, "status": "active"},
        {"$set": {"status": "superseded", "updated_at": _now().isoformat()}},
    )

    aid = await next_counter(db, "hr_shift_assignments")
    now = _now().isoformat()
    doc = {
        "_id": aid,
        "id": aid,
        "employee_id": employee_id,
        "shift_id": _id,
        "shift_code": shift["shift_code"],
        "shift_name": shift["shift_name"],
        "shift_color": shift.get("color", "#64748b"),
        "effective_from": effective_from,
        "effective_until": effective_until,
        "department": department,
        "assigned_by": assigned_by,
        "notes": notes,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await db.hr_shift_assignments.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


async def get_employee_shift(db, employee_id: str, for_date: str) -> Dict:
    """Return active shift for employee on given date. Falls back to DEFAULT."""
    # Find active assignment covering this date
    assign = await db.hr_shift_assignments.find_one(
        {
            "employee_id": employee_id,
            "status": "active",
            "effective_from": {"$lte": for_date},
            "$or": [
                {"effective_until": None},
                {"effective_until": ""},
                {"effective_until": {"$gte": for_date}},
            ],
        },
        {"_id": 0},
    )
    if not assign:
        return DEFAULT_SHIFT

    shift = await db.rahaza_shifts.find_one({"id": assign["shift_id"]}, {"_id": 0})
    return _to_hr_shape(shift) if shift else DEFAULT_SHIFT


def calculate_shift_hours(
    clock_in: str,
    clock_out: str,
    shift: Dict,
) -> Dict:
    """
    Hitung jam kerja efektif dan overtime berdasarkan shift.
    Returns: {work_hours, overtime_hours, early_minutes, late_minutes}
    """
    try:
        ci = datetime.fromisoformat(clock_in) if "T" in clock_in else datetime.strptime(clock_in, "%Y-%m-%d %H:%M:%S")
        co = datetime.fromisoformat(clock_out) if "T" in clock_out else datetime.strptime(clock_out, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return {"work_hours": 0, "overtime_hours": 0, "early_minutes": 0, "late_minutes": 0}

    total_minutes = (co - ci).total_seconds() / 60
    break_min = shift.get("break_duration_minutes", 60)
    work_min = max(0, total_minutes - break_min)
    work_hours = round(work_min / 60, 2)

    # Effective shift hours
    eff_hours = shift.get("effective_hours", 8.0)
    overtime_hours = max(0.0, round(work_hours - eff_hours, 2))

    # Lateness vs shift start
    shift_start = _parse_time(shift.get("start_time", "08:00"))
    expected_start = ci.replace(hour=shift_start.hour, minute=shift_start.minute, second=0, microsecond=0)
    late_min = max(0, int((ci - expected_start).total_seconds() / 60))

    # Earliness (left before shift end)
    shift_end_str = shift.get("end_time", "17:00")
    shift_end = _parse_time(shift_end_str)
    expected_end = co.replace(hour=shift_end.hour, minute=shift_end.minute, second=0, microsecond=0)
    if shift.get("is_overnight") and expected_end <= expected_start:
        expected_end += timedelta(days=1)
    early_min = max(0, int((expected_end - co).total_seconds() / 60))

    return {
        "work_hours": work_hours,
        "overtime_hours": overtime_hours,
        "early_minutes": early_min,
        "late_minutes": late_min,
    }
