"""
Rahaza Auto-Attendance - ZKTeco Devices
Physical Fingerprint Device Sync (ZKTeco/Fingerspot)
"""
import logging
import uuid
import json
import os
from datetime import datetime, timezone, date
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

router = APIRouter(tags=["rahaza-auto-attendance-zkteco"])

# Config
RP_ID = os.environ.get("WEBAUTHN_RP_ID", "analytics-builds.preview.emergentagent.com")
RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "Dewi Aditya ERP")
ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "https://da37-cmt-bridge.preview.emergentagent.com")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _today_iso(): return date.today().isoformat()




@router.get("/devices/zkteco")
async def list_zkteco_devices(request: Request):
    """List semua device ZKTeco yang terkonfigurasi."""
    await require_auth(request)
    db = get_db()
    rows = await db.rahaza_zkteco_devices.find({}, {"_id": 0}).to_list(500)
    return serialize_doc(rows)


@router.post("/devices/zkteco")
async def add_zkteco_device(request: Request):
    """Tambah konfigurasi device ZKTeco/Fingerspot."""
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner", "hr"):
        raise HTTPException(403, "Hanya admin/HR.")
    db = get_db()
    body = await request.json()
    name = body.get("name", "").strip()
    ip = body.get("ip", "").strip()
    port = int(body.get("port") or 4370)
    if not name or not ip:
        raise HTTPException(400, "name dan ip wajib diisi.")

    doc = {
        "id": _uid(),
        "name": name,
        "ip": ip,
        "port": port,
        "password": int(body.get("password") or 0),
        "timezone": int(body.get("timezone") or 8),  # UTC+8 WIB
        "enabled": bool(body.get("enabled", True)),
        "last_sync_at": None,
        "last_sync_status": None,
        "last_sync_records": 0,
        "last_error": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.rahaza_zkteco_devices.insert_one(doc)
    return serialize_doc(doc)


@router.put("/devices/zkteco/{device_id}")
async def update_zkteco_device(device_id: str, request: Request):
    """Update konfigurasi device ZKTeco."""
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner", "hr"):
        raise HTTPException(403, "Hanya admin/HR.")
    db = get_db()
    body = await request.json()
    updates = {k: v for k, v in {
        "name": body.get("name"), "ip": body.get("ip"),
        "port": body.get("port"), "password": body.get("password"),
        "enabled": body.get("enabled"), "timezone": body.get("timezone"),
        "updated_at": _now(),
    }.items() if v is not None}
    result = await db.rahaza_zkteco_devices.update_one({"id": device_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Device tidak ditemukan.")
    return {"ok": True}


@router.delete("/devices/zkteco/{device_id}")
async def delete_zkteco_device(device_id: str, request: Request):
    """Hapus device ZKTeco."""
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner", "hr"):
        raise HTTPException(403, "Hanya admin/HR.")
    db = get_db()
    result = await db.rahaza_zkteco_devices.delete_one({"id": device_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Device tidak ditemukan.")
    return {"ok": True}


@router.post("/devices/zkteco/{device_id}/sync")
async def sync_zkteco_device(device_id: str, request: Request):
    """
    Sync attendance logs dari device ZKTeco ke sistem.
    Butuh hardware nyata; simulator mode tersedia untuk testing.
    """
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner", "hr"):
        raise HTTPException(403, "Hanya admin/HR.")
    db = get_db()
    device = await db.rahaza_zkteco_devices.find_one({"id": device_id}, {"_id": 0})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan.")

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    simulator_mode = (await request.json() if request.headers.get("content-type","").startswith("application/json") else {}).get("simulator", False) if False else False

    try:
        body_raw = await request.body()
        if body_raw:
            body = json.loads(body_raw)
        simulator_mode = body.get("simulator", False)
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    if simulator_mode:
        # Simulator mode: generate fake attendance logs for testing
        emps = await db.rahaza_employees.find({"active": True}, {"_id": 0, "id": 1, "name": 1}).limit(5).to_list(500)
        synced = 0
        today = _today_iso()
        for i, emp in enumerate(emps):
            # Check for ANY existing attendance record for this employee today (not just device_zkteco)
            existing = await db.rahaza_attendance_events.find_one(
                {"employee_id": emp["id"], "date": today}
            )
            if existing:
                continue
            clock_in_time = _now().replace(hour=7 + i % 2, minute=30 + i * 5, second=0, microsecond=0)
            doc = {
                "id": _uid(), "employee_id": emp["id"], "date": today,
                "clock_in": clock_in_time, "clock_out": None,
                "hours_worked": 0, "overtime_hours": 0, "status": "hadir",
                "attendance_method": "device_zkteco", "geo_status": "not_verified",
                "face_match_status": "biometric_verified", "face_match_score": 1.0,
                "approval_status": "auto_approved", "source": "device_zkteco",
                "device_source": device["name"], "device_event_id": f"{device_id}-sim-{today}-{i}",
                "notes": f"Sync dari device: {device['name']} (simulator)",
                "created_by": user["id"], "created_by_name": user.get("name", ""),
                "created_at": _now(), "updated_at": _now(),
                "updated_by": user["id"], "updated_by_name": user.get("name", ""),
            }
            await db.rahaza_attendance_events.insert_one(doc)
            synced += 1

        await db.rahaza_zkteco_devices.update_one({"id": device_id}, {"$set": {
            "last_sync_at": _now(), "last_sync_status": "success_simulator",
            "last_sync_records": synced, "last_error": None,
        }})
        return {"ok": True, "synced": synced, "mode": "simulator",
                "message": f"Simulator: {synced} record kehadiran berhasil disinkronkan."}

    # Real device sync via pyzk
    try:
        from zk import ZK
        zk = ZK(device["ip"], port=device.get("port", 4370),
                timeout=10, password=device.get("password", 0),
                ommit_ping=False)
        conn = None
        try:
            conn = zk.connect()
            conn.disable_device()
            attendances = conn.get_attendance()
            conn.enable_device()

            # Map ZKTeco user ID → employee
            users = conn.get_users()
            zk_user_map = {str(u.user_id): u.name for u in users}

            synced = 0
            skipped = 0
            for att in attendances:
                emp = await db.rahaza_employees.find_one(
                    {"$or": [
                        {"zkteco_user_id": str(att.user_id)},
                        {"employee_code": zk_user_map.get(str(att.user_id), "NOTFOUND")},
                    ]},
                    {"_id": 0}
                )
                if not emp:
                    skipped += 1
                    continue

                att_date = att.timestamp.date().isoformat() if att.timestamp else _today_iso()
                device_event_id = f"{device_id}-{att.user_id}-{att.timestamp}"

                existing = await db.rahaza_attendance_events.find_one({"device_event_id": device_event_id})
                if existing:
                    skipped += 1
                    continue

                # Determine if clock-in or clock-out by punch type
                is_clock_in = att.punch in (0, 254)  # 0=check-in in most models
                att_doc = {
                    "id": _uid(), "employee_id": emp["id"], "date": att_date,
                    "clock_in": att.timestamp if is_clock_in else None,
                    "clock_out": att.timestamp if not is_clock_in else None,
                    "hours_worked": 0, "overtime_hours": 0, "status": "hadir",
                    "attendance_method": "device_zkteco",
                    "geo_status": "not_verified", "face_match_status": "biometric_verified",
                    "face_match_score": 1.0, "approval_status": "auto_approved",
                    "source": "device_zkteco", "device_source": device["name"],
                    "device_event_id": device_event_id,
                    "notes": f"Sync dari device: {device['name']}",
                    "created_by": user["id"], "created_by_name": user.get("name", ""),
                    "created_at": _now(), "updated_at": _now(),
                    "updated_by": user["id"], "updated_by_name": user.get("name", ""),
                }
                await db.rahaza_attendance_events.insert_one(att_doc)
                synced += 1

            await db.rahaza_zkteco_devices.update_one({"id": device_id}, {"$set": {
                "last_sync_at": _now(), "last_sync_status": "success",
                "last_sync_records": synced, "last_error": None,
            }})
            return {"ok": True, "synced": synced, "skipped": skipped, "mode": "live",
                    "message": f"{synced} record berhasil disinkronkan dari device."}
        finally:
            if conn:
                conn.disconnect()
    except ImportError:
        raise HTTPException(500, "Library pyzk tidak tersedia.")
    except Exception as e:
        err_msg = str(e)[:300]
        await db.rahaza_zkteco_devices.update_one({"id": device_id}, {"$set": {
            "last_sync_at": _now(), "last_sync_status": "error",
            "last_sync_records": 0, "last_error": err_msg,
        }})
        raise HTTPException(503, f"Gagal terhubung ke device: {err_msg}. Pastikan device menyala dan IP/port benar.")


@router.get("/devices/zkteco/{device_id}/last-sync")
async def get_zkteco_last_sync(device_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    device = await db.rahaza_zkteco_devices.find_one({"id": device_id}, {"_id": 0})
    if not device:
        raise HTTPException(404, "Device tidak ditemukan.")
    return serialize_doc(device)


# ═══════════════════════════════════════════════════════════════════════════════
# 4) HR APPROVAL QUEUE
# ═══════════════════════════════════════════════════════════════════════════════

