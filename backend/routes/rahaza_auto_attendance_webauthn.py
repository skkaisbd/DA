"""
Rahaza Auto-Attendance - WebAuthn Biometric
WebAuthn Fingerprint/Biometric (Touch ID, Face ID)
"""
import logging
import uuid
import json
import os
from datetime import datetime, timezone, date, timedelta
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from dotenv import load_dotenv

load_dotenv()

# WebAuthn imports (graceful fallback)
WEBAUTHN_AVAILABLE = False
try:
    import webauthn
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        AuthenticatorAttachment,
        UserVerificationRequirement,
        ResidentKeyRequirement,
        PublicKeyCredentialDescriptor,
    )
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

router = APIRouter(tags=["rahaza-auto-attendance-webauthn"])

# Config
RP_ID = os.environ.get("WEBAUTHN_RP_ID", "analytics-builds.preview.emergentagent.com")
RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "Dewi Aditya ERP")
ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "https://da37-cmt-bridge.preview.emergentagent.com")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _today_iso(): return date.today().isoformat()




async def _get_employee_webauthn_user(db, emp_id: str):
    emp = await db.rahaza_employees.find_one({"id": emp_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Karyawan tidak ditemukan.")
    return emp

@router.get("/attendance/webauthn/devices")
async def list_webauthn_devices(request: Request, employee_id: Optional[str] = None):
    """List semua credential WebAuthn yang terdaftar."""
    user = await require_auth(request)
    db = get_db()
    q = {}
    if employee_id:
        q["employee_id"] = employee_id
    else:
        # HR dapat lihat semua; karyawan hanya lihat milik sendiri
        if user.get("role") not in ("superadmin", "admin", "owner", "hr"):
            # Cari employee_id dari user
            emp = await db.rahaza_employees.find_one({"user_id": user["id"]}, {"_id": 0})
            if emp:
                q["employee_id"] = emp["id"]
    rows = await db.rahaza_webauthn_credentials.find(
        {**q, "revoked_at": None},
        {"_id": 0, "public_key": 0}  # hide public key from response
    ).to_list(500)
    return serialize_doc(rows)


@router.post("/attendance/webauthn/register/options")
async def webauthn_register_options(request: Request):
    """
    Mulai registrasi WebAuthn.
    Body: { employee_id }
    """
    user = await require_auth(request)
    db = get_db()
    try:
        body = await request.json()
        emp_id = body.get("employee_id", "")
    except Exception:
        raise HTTPException(422, "Body JSON diperlukan: {\"employee_id\": \"<uuid>\"}")
    if not emp_id:
        raise HTTPException(422, "employee_id wajib diisi di body")

    # FASE 15 — otorisasi: hanya untuk diri sendiri (atau HR untuk karyawan lain)
    from utils.employee_identity import resolve_employee_for
    emp = await resolve_employee_for(db, user, emp_id)
    emp_id = emp["id"]

    # Existing credentials (untuk exclude)
    existing_creds = await db.rahaza_webauthn_credentials.find(
        {"employee_id": emp_id, "revoked_at": None},
        {"_id": 0, "credential_id": 1}
    ).to_list(500)

    exclude_credentials = []
    for c in existing_creds:
        try:
            cid = base64url_to_bytes(c["credential_id"]) if isinstance(c["credential_id"], str) else c["credential_id"]
            exclude_credentials.append(
                PublicKeyCredentialDescriptor(id=cid)
            )
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    try:
        options = webauthn.generate_registration_options(
            rp_id=RP_ID,
            rp_name=RP_NAME,
            user_id=emp_id.encode(),
            user_name=emp.get("email") or emp.get("employee_code") or emp_id,
            user_display_name=emp.get("name", emp_id),
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=exclude_credentials,
        )
    except Exception as e:
        raise HTTPException(500, f"Gagal membuat opsi registrasi: {e}")

    # Simpan challenge ke DB (TTL 5 menit)
    challenge_b64 = bytes_to_base64url(options.challenge)
    await db.rahaza_webauthn_challenges.insert_one({
        "id": _uid(),
        "employee_id": emp_id,
        "challenge": challenge_b64,
        "type": "registration",
        "expires_at": _now() + timedelta(minutes=5),
        "used": False,
    })

    return json.loads(webauthn.options_to_json(options))


@router.post("/attendance/webauthn/register/verify")
async def webauthn_register_verify(request: Request):
    """
    Selesaikan registrasi WebAuthn.
    Body: credential object dari browser + employee_id + device_name
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    # FASE 15 — SSOT identitas + otorisasi: daftar biometrik hanya untuk diri
    # sendiri (atau oleh HR untuk karyawan lain).
    from utils.employee_identity import resolve_employee_for
    _emp = await resolve_employee_for(db, user, body.get("employee_id"))
    emp_id = _emp["id"]
    device_name = body.get("device_name") or "Device"

    # Ambil challenge dari DB
    ch = await db.rahaza_webauthn_challenges.find_one({
        "employee_id": emp_id,
        "type": "registration",
        "used": False,
        "expires_at": {"$gt": _now()},
    }, sort=[("_id", -1)])
    if not ch:
        raise HTTPException(400, "Challenge tidak ditemukan atau sudah kadaluarsa. Mulai ulang registrasi.")

    try:
        credential_id_raw = body.get("id") or body.get("rawId", "")
        credential = webauthn.helpers.structs.RegistrationCredential(
            id=credential_id_raw,
            raw_id=base64url_to_bytes(body.get("rawId", credential_id_raw)),
            response=webauthn.helpers.structs.AuthenticatorAttestationResponse(
                client_data_json=base64url_to_bytes(body["response"]["clientDataJSON"]),
                attestation_object=base64url_to_bytes(body["response"]["attestationObject"]),
            ),
            type=body.get("type", "public-key"),
        )
        verification = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(ch["challenge"]),
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            require_resident_key=False,
        )
    except InvalidRegistrationResponse as e:
        raise HTTPException(400, f"Verifikasi registrasi gagal: {e}")
    except Exception as e:
        raise HTTPException(500, f"Error registrasi: {e}")

    # Tandai challenge sebagai terpakai
    await db.rahaza_webauthn_challenges.update_one({"id": ch["id"]}, {"$set": {"used": True}})

    # Simpan credential
    cred_doc = {
        "id": _uid(),
        "employee_id": emp_id,
        "credential_id": bytes_to_base64url(verification.credential_id),
        "public_key": bytes_to_base64url(verification.credential_public_key),
        "sign_count": verification.sign_count,
        "device_name": device_name,
        "transports": body.get("response", {}).get("transports") or [],
        "aaguid": str(verification.aaguid) if verification.aaguid else None,
        "created_at": _now(),
        "last_used_at": None,
        "revoked_at": None,
    }
    await db.rahaza_webauthn_credentials.insert_one(cred_doc)

    emp = await db.rahaza_employees.find_one({"id": emp_id}, {"_id": 0, "name": 1})
    return {"ok": True, "message": f"Biometrik berhasil didaftarkan untuk {emp.get('name','?')}", "device": cred_doc["id"]}


@router.post("/attendance/webauthn/auth/options")
async def webauthn_auth_options(request: Request):
    """
    Mulai autentikasi WebAuthn untuk clock-in/out.
    Body: { employee_id }
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    # FASE 15 — SSOT identitas + otorisasi: `employee_id` orang lain hanya HR.
    from utils.employee_identity import resolve_employee_for
    _emp = await resolve_employee_for(db, user, body.get("employee_id"))
    emp_id = _emp["id"]

    creds = await db.rahaza_webauthn_credentials.find(
        {"employee_id": emp_id, "revoked_at": None},
        {"_id": 0}
    ).to_list(500)
    if not creds:
        raise HTTPException(400, "Belum ada biometrik terdaftar untuk karyawan ini. Lakukan registrasi terlebih dahulu.")

    allow_credentials = []
    for c in creds:
        try:
            cid = base64url_to_bytes(c["credential_id"])
            allow_credentials.append(
                PublicKeyCredentialDescriptor(
                    id=cid,
                    transports=c.get("transports") or [],
                )
            )
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    try:
        options = webauthn.generate_authentication_options(
            rp_id=RP_ID,
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.REQUIRED,
        )
    except Exception as e:
        raise HTTPException(500, f"Gagal membuat opsi autentikasi: {e}")

    challenge_b64 = bytes_to_base64url(options.challenge)
    await db.rahaza_webauthn_challenges.insert_one({
        "id": _uid(),
        "employee_id": emp_id,
        "challenge": challenge_b64,
        "type": "authentication",
        "expires_at": _now() + timedelta(minutes=5),
        "used": False,
    })

    return json.loads(webauthn.options_to_json(options))


@router.post("/attendance/webauthn/clock-in")
async def webauthn_clock_in(request: Request):
    """
    Clock-in via WebAuthn assertion.
    Body: credential assertion dari browser + employee_id
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    # FASE 15 — SSOT identitas + otorisasi: `employee_id` orang lain hanya HR.
    from utils.employee_identity import resolve_employee_for
    _emp = await resolve_employee_for(db, user, body.get("employee_id"))
    emp_id = _emp["id"]

    today = _today_iso()
    existing = await db.rahaza_attendance_events.find_one({"employee_id": emp_id, "date": today})
    if existing and existing.get("clock_in"):
        raise HTTPException(400, "Karyawan sudah clock-in hari ini.")

    # Cari challenge
    ch = await db.rahaza_webauthn_challenges.find_one({
        "employee_id": emp_id, "type": "authentication",
        "used": False, "expires_at": {"$gt": _now()},
    }, sort=[("_id", -1)])
    if not ch:
        raise HTTPException(400, "Challenge tidak ditemukan atau kadaluarsa.")

    # Cari credential yang dipakai
    cred_id_raw = body.get("id") or body.get("rawId", "")
    cred_doc = await db.rahaza_webauthn_credentials.find_one({
        "employee_id": emp_id,
        "credential_id": cred_id_raw,
        "revoked_at": None,
    })
    if not cred_doc:
        # Try to find by decoded credential id
        cred_doc = await db.rahaza_webauthn_credentials.find_one(
            {"employee_id": emp_id, "revoked_at": None},
        )
    if not cred_doc:
        raise HTTPException(400, "Credential tidak ditemukan.")

    try:
        assertion = webauthn.helpers.structs.AuthenticationCredential(
            id=cred_id_raw,
            raw_id=base64url_to_bytes(body.get("rawId", cred_id_raw)),
            response=webauthn.helpers.structs.AuthenticatorAssertionResponse(
                client_data_json=base64url_to_bytes(body["response"]["clientDataJSON"]),
                authenticator_data=base64url_to_bytes(body["response"]["authenticatorData"]),
                signature=base64url_to_bytes(body["response"]["signature"]),
                user_handle=base64url_to_bytes(body["response"]["userHandle"]) if body["response"].get("userHandle") else None,
            ),
            type=body.get("type", "public-key"),
        )
        verification = webauthn.verify_authentication_response(
            credential=assertion,
            expected_challenge=base64url_to_bytes(ch["challenge"]),
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=base64url_to_bytes(cred_doc["public_key"]),
            credential_current_sign_count=cred_doc.get("sign_count", 0),
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as e:
        raise HTTPException(401, f"Autentikasi biometrik gagal: {e}")
    except Exception as e:
        raise HTTPException(500, f"Error autentikasi: {e}")

    # Update sign count dan last_used
    await db.rahaza_webauthn_credentials.update_one(
        {"id": cred_doc["id"]},
        {"$set": {"sign_count": verification.new_sign_count, "last_used_at": _now()}}
    )
    await db.rahaza_webauthn_challenges.update_one({"id": ch["id"]}, {"$set": {"used": True}})

    now = _now()
    # FASE 16 — jalur biometrik TETAP wajib berada di area kantor (selfie
    # digantikan oleh sidik jari/Face ID perangkat). Dulu jalur ini menulis
    # `geo_status: "not_verified"` + `auto_approved` ⇒ celah absen dari rumah.
    from utils.attendance_policy import enforce_attendance_policy
    from utils.employee_identity import compute_late_minutes
    _pol = await enforce_attendance_policy(
        db, photo_b64=None, lat=body.get("lat"), lng=body.get("lng"),
        action="masuk", selfie_required=False)
    _geo = _pol["geo"]
    late = await compute_late_minutes(db, _emp, now, (existing or {}).get("shift_id"))
    doc_fields = {
        "clock_in": now, "attendance_method": "webauthn", **late,
        "geo_status": _geo.get("status"), "geo_distance_m": _geo.get("distance_m"),
        "clock_in_geo": {"lat": body.get("lat"), "lng": body.get("lng"),
                         "status": _geo.get("status"),
                         "distance_m": _geo.get("distance_m")},
        "face_match_score": 1.0,
        "face_match_status": "biometric_verified",
        "approval_status": "auto_approved",
        "status": "hadir", "source": "webauthn",
        "webauthn_credential_id": cred_doc["id"],
        "updated_by": user["id"], "updated_by_name": user.get("name", ""), "updated_at": now,
    }

    if existing:
        await db.rahaza_attendance_events.update_one({"id": existing["id"]}, {"$set": doc_fields})
        out = await db.rahaza_attendance_events.find_one({"id": existing["id"]}, {"_id": 0})
    else:
        doc_fields.update({
            "id": _uid(), "employee_id": emp_id, "date": today,
            "clock_out": None, "hours_worked": 0, "overtime_hours": 0, "notes": "",
            "created_by": user["id"], "created_by_name": user.get("name", ""), "created_at": now,
        })
        await db.rahaza_attendance_events.insert_one(doc_fields)
        out = doc_fields

    await log_activity(user["id"], user.get("name", ""), "webauthn-clock-in", "attendance", emp_id)
    return {"ok": True, "attendance": serialize_doc(out), "message": "Clock-in via biometrik berhasil!"}


@router.post("/attendance/webauthn/clock-out")
async def webauthn_clock_out(request: Request):
    """Clock-out via WebAuthn assertion."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    # FASE 15 — SSOT identitas + otorisasi: `employee_id` orang lain hanya HR.
    from utils.employee_identity import resolve_employee_for
    _emp = await resolve_employee_for(db, user, body.get("employee_id"))
    emp_id = _emp["id"]

    today = _today_iso()
    existing = await db.rahaza_attendance_events.find_one({"employee_id": emp_id, "date": today})
    if not existing or not existing.get("clock_in"):
        raise HTTPException(400, "Belum clock-in hari ini.")
    if existing.get("clock_out"):
        raise HTTPException(400, "Sudah clock-out hari ini.")

    # Simplified: re-use same WebAuthn verify flow (same as clock-in but just clock-out action)
    ch = await db.rahaza_webauthn_challenges.find_one({
        "employee_id": emp_id, "type": "authentication",
        "used": False, "expires_at": {"$gt": _now()},
    }, sort=[("_id", -1)])
    if not ch:
        raise HTTPException(400, "Challenge tidak ditemukan atau kadaluarsa.")

    cred_id_raw = body.get("id") or body.get("rawId", "")
    cred_doc = await db.rahaza_webauthn_credentials.find_one(
        {"employee_id": emp_id, "revoked_at": None}
    )
    if not cred_doc:
        raise HTTPException(400, "Credential tidak ditemukan.")

    try:
        assertion = webauthn.helpers.structs.AuthenticationCredential(
            id=cred_id_raw,
            raw_id=base64url_to_bytes(body.get("rawId", cred_id_raw)),
            response=webauthn.helpers.structs.AuthenticatorAssertionResponse(
                client_data_json=base64url_to_bytes(body["response"]["clientDataJSON"]),
                authenticator_data=base64url_to_bytes(body["response"]["authenticatorData"]),
                signature=base64url_to_bytes(body["response"]["signature"]),
                user_handle=base64url_to_bytes(body["response"]["userHandle"]) if body["response"].get("userHandle") else None,
            ),
            type=body.get("type", "public-key"),
        )
        verification = webauthn.verify_authentication_response(
            credential=assertion,
            expected_challenge=base64url_to_bytes(ch["challenge"]),
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=base64url_to_bytes(cred_doc["public_key"]),
            credential_current_sign_count=cred_doc.get("sign_count", 0),
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as e:
        raise HTTPException(401, f"Autentikasi biometrik gagal: {e}")
    except Exception as e:
        raise HTTPException(500, f"Error autentikasi: {e}")

    await db.rahaza_webauthn_credentials.update_one(
        {"id": cred_doc["id"]},
        {"$set": {"sign_count": verification.new_sign_count, "last_used_at": _now()}}
    )
    await db.rahaza_webauthn_challenges.update_one({"id": ch["id"]}, {"$set": {"used": True}})

    now = _now()
    cin = existing.get("clock_in")
    if isinstance(cin, str):
        try:
            cin = datetime.fromisoformat(cin.replace("Z", "+00:00"))
        except Exception:
            cin = None
    elif isinstance(cin, datetime):
        # Make timezone-aware if naive
        if cin.tzinfo is None:
            cin = cin.replace(tzinfo=timezone.utc)
    hours = round((now - cin).total_seconds() / 3600, 2) if cin else 0

    # FASE 16 — lokasi tetap wajib + sesi keluar harus ditutup + jam bersih
    # dihitung ulang (dulu clock-out biometrik mengabaikan ketiganya).
    from routes.rahaza_attendance_sessions import (is_permit_pending, is_session_out,
                                                   recompute_session_totals)
    from utils.attendance_policy import enforce_attendance_policy
    _pol = await enforce_attendance_policy(
        db, photo_b64=None, lat=body.get("lat"), lng=body.get("lng"),
        action="pulang", selfie_required=False)
    _geo = _pol["geo"]
    for s in (existing.get("sessions") or []):
        if is_session_out(s):
            raise HTTPException(
                400, f"Masih ada sesi {s.get('kind')} yang belum ditutup. "
                     "Tekan 'Kembali Kerja' dulu sebelum absen pulang.")
        if is_permit_pending(s):
            raise HTTPException(
                400, "Ada pengajuan izin yang masih menunggu persetujuan. "
                     "Batalkan pengajuan atau minta HR memprosesnya dulu.")
    totals = recompute_session_totals({**existing, "hours_worked": max(0.0, hours)})

    await db.rahaza_attendance_events.update_one({"id": existing["id"]}, {"$set": {
        "clock_out": now, "hours_worked": max(0.0, hours), **totals,
        "clock_out_geo": {"lat": body.get("lat"), "lng": body.get("lng"),
                          "status": _geo.get("status"),
                          "distance_m": _geo.get("distance_m")},
        "source": "webauthn", "updated_by": user["id"],
        "updated_by_name": user.get("name", ""), "updated_at": now,
    }})
    out = await db.rahaza_attendance_events.find_one({"id": existing["id"]}, {"_id": 0})
    await log_activity(user["id"], user.get("name", ""), "webauthn-clock-out", "attendance", emp_id)
    return {"ok": True, "attendance": serialize_doc(out), "hours_worked": hours, "message": "Clock-out via biometrik berhasil!"}


@router.delete("/attendance/webauthn/devices/{device_id}")
async def revoke_webauthn_device(device_id: str, request: Request):
    """Cabut/hapus credential WebAuthn."""
    user = await require_auth(request)
    db = get_db()
    cred = await db.rahaza_webauthn_credentials.find_one({"id": device_id})
    if not cred:
        raise HTTPException(404, "Credential tidak ditemukan.")
    await db.rahaza_webauthn_credentials.update_one(
        {"id": device_id}, {"$set": {"revoked_at": _now()}}
    )
    return {"ok": True, "message": "Biometrik berhasil dicabut."}


# ═══════════════════════════════════════════════════════════════════════════════
# 3) ZKTECO PHYSICAL DEVICE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

