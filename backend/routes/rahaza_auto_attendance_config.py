"""
Rahaza Auto-Attendance - Config
Status & Configuration endpoints
"""
import uuid
import os
from datetime import datetime, timezone, date
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc
from dotenv import load_dotenv

load_dotenv()

# WebAuthn imports (graceful fallback)
WEBAUTHN_AVAILABLE = False
try:
    from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
    from webauthn.helpers.exceptions import (
        InvalidRegistrationResponse,
        InvalidAuthenticationResponse,
    )
    WEBAUTHN_AVAILABLE = True
except Exception:
    def base64url_to_bytes(s): return b""
    def bytes_to_base64url(b): return ""
    class InvalidRegistrationResponse(Exception):
        pass
    class InvalidAuthenticationResponse(Exception):
        pass

# AI Face Compare

router = APIRouter(tags=["rahaza-auto-attendance-config"])

# Config
RP_ID = os.environ.get("WEBAUTHN_RP_ID", "analytics-builds.preview.emergentagent.com")
RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "Dewi Aditya ERP")
ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "https://da37-cmt-bridge.preview.emergentagent.com")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _today_iso(): return date.today().isoformat()




@router.get("/attendance/my-status")
async def get_my_attendance_status(request: Request, employee_id: Optional[str] = None):
    """
    Ambil status kehadiran hari ini untuk karyawan (untuk /absen page).
    """
    user = await require_auth(request)
    db = get_db()

    # ── SSOT identitas (FASE 15) ──────────────────────────────────────────────
    # DULU: kalau email user tidak cocok karyawan mana pun, kode ini mengambil
    # `find_one({})` = KARYAWAN PERTAMA DI DATABASE. Terbukti 2026-07-26: login
    # sebagai Siti Rahayu (DA-002) menampilkan "Budi Operator (OP-001)" dan
    # tombol absen akan mencatat kehadiran ATAS NAMA ORANG LAIN.
    # Sekarang: satu resolver, tanpa tebakan; `employee_id` orang lain butuh HR.
    from utils.employee_identity import resolve_employee_for, resolve_my_employee
    if employee_id:
        emp = await resolve_employee_for(db, user, employee_id)
    else:
        emp = await resolve_my_employee(db, user)
    if not emp:
        return {
            "today": None,
            "employee": None,
            "linked": False,
            "message": ("Akun Anda belum ditautkan ke data karyawan. "
                        "Minta Admin HR menautkan lewat menu Data Karyawan → Tautkan Akun."),
        }
    emp_id = emp["id"]

    today = _today_iso()
    rec = await db.rahaza_attendance_events.find_one({"employee_id": emp_id, "date": today}, {"_id": 0})

    # Check WebAuthn credentials
    has_webauthn = await db.rahaza_webauthn_credentials.count_documents({"employee_id": emp_id, "revoked_at": None}) > 0

    # ── Sesi berjalan vs pengajuan menunggu (FASE 16) ────────────────────
    # DULU: `if not s.get("in_at")` — pengajuan izin yang MASIH MENUNGGU
    # persetujuan (out_at=None) ikut terbaca sebagai "sedang keluar", sehingga
    # Portal Saya menampilkan kartu "Sedang IZIN keluar (disetujui)" dengan jam
    # keluar "--:--". Pakai SSOT status sesi.
    from routes.rahaza_attendance_sessions import is_permit_pending, is_session_out
    active_session = None
    pending_permit = None
    for s in ((rec or {}).get("sessions") or []):
        if active_session is None and is_session_out(s):
            active_session = s
        if pending_permit is None and is_permit_pending(s):
            pending_permit = s

    return serialize_doc({
        "today": rec,
        "employee": emp,
        "linked": True,
        "has_webauthn": has_webauthn,
        "active_session": active_session,
        "pending_permit": pending_permit,
        "break_minutes": (rec or {}).get("break_minutes", 0),
        "permit_minutes": (rec or {}).get("permit_minutes", 0),
        "late_minutes": (rec or {}).get("late_minutes", 0),
        "date": today,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# 5) OFFICE CONFIG — Face threshold + Geofence + kebijakan WAJIB (FASE 16)
# ═══════════════════════════════════════════════════════════════════════════════
# Endpoint ini dan `/attendance/office-location` (rahaza_attendance.py) dulu
# adalah DUA sumber kebenaran untuk dokumen yang SAMA, dengan nama field berbeda
# (`office_lat` vs `lat`). Akibatnya UI Konfigurasi membaca `office_lat` tapi
# menulis `lat` ⇒ kolom koordinat tampak beku dan HR mengira fiturnya rusak.
# Sekarang keduanya membaca/menulis lewat SSOT `utils/attendance_policy`.

@router.get("/attendance/auto-config")
async def get_auto_config(request: Request):
    """Konfigurasi absen otomatis (alias nama lama + kanonik, satu sumber)."""
    await require_auth(request)
    from utils.attendance_policy import get_office
    o = await get_office(get_db())
    return serialize_doc({
        **o,
        # alias nama lama supaya UI/skrip lama tidak pecah
        "office_name": o["name"],
        "office_lat": o["lat"],
        "office_lng": o["lng"],
        "allow_out_of_range": not o["require_geofence"],
    })


@router.put("/attendance/auto-config")
async def update_auto_config(request: Request):
    """Update konfigurasi absen otomatis (menerima nama lama maupun kanonik)."""
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner", "hr"):
        raise HTTPException(403, "Hanya HR/Admin.")
    db = get_db()
    body = await request.json()
    from utils.attendance_policy import get_office
    cur = await get_office(db)

    def pick(*keys, default=None):
        for k in keys:
            if body.get(k) is not None and body.get(k) != "":
                return body[k]
        return default

    updates: dict = {"is_primary": True}

    thr = pick("face_match_threshold")
    if thr is not None:
        val = float(thr)
        if not (0 <= val <= 1):
            raise HTTPException(400, "face_match_threshold harus 0.0-1.0")
        updates["face_match_threshold"] = val

    rad = pick("geofence_radius_m")
    if rad is not None:
        rad = int(rad)
        if not (10 <= rad <= 20000):
            raise HTTPException(400, "Radius harus antara 10 dan 20.000 meter.")
        updates["geofence_radius_m"] = rad

    name = pick("name", "office_name")
    if name:
        updates["name"] = str(name)
    if body.get("address") is not None:
        updates["address"] = str(body["address"])

    for canon, alias, lo, hi in (("lat", "office_lat", -90, 90),
                                 ("lng", "office_lng", -180, 180)):
        raw = pick(canon, alias)
        if raw is not None:
            try:
                v = float(raw)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{canon} harus angka desimal.")
            if not (lo <= v <= hi):
                raise HTTPException(400, f"{canon} di luar rentang wajar ({lo}..{hi}).")
            updates[canon] = v

    if body.get("require_selfie") is not None:
        updates["require_selfie"] = bool(body["require_selfie"])
    if body.get("require_geofence") is not None:
        updates["require_geofence"] = bool(body["require_geofence"])
    elif body.get("allow_out_of_range") is not None:      # alias lama (terbalik)
        updates["require_geofence"] = not bool(body["allow_out_of_range"])

    final_geofence = updates.get("require_geofence", cur["require_geofence"])
    final_lat = updates.get("lat", cur["lat"])
    if final_geofence and final_lat is None:
        raise HTTPException(
            400,
            "Verifikasi lokasi diwajibkan tetapi koordinat kantor kosong. "
            "Isi Latitude/Longitude (tombol 'Pakai lokasi saya sekarang') atau "
            "matikan dulu kewajiban lokasi.")

    updates["updated_at"] = _now()
    updates["updated_by_name"] = user.get("name", "")
    await db.rahaza_office_locations.update_one(
        {"is_primary": True}, {"$set": updates}, upsert=True
    )
    o = await get_office(db)
    return {"ok": True, "updated": [k for k in updates if k != "is_primary"],
            "config": serialize_doc({**o, "office_name": o["name"],
                                     "office_lat": o["lat"], "office_lng": o["lng"]})}
