"""
Rahaza Auto-Attendance - Orchestrator
"""
from fastapi import APIRouter
from routes import (
    rahaza_auto_attendance_selfie,
    rahaza_auto_attendance_webauthn,
    rahaza_auto_attendance_zkteco,
    rahaza_auto_attendance_approvals,
    rahaza_auto_attendance_config
)

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-auto-attendance"])

router.include_router(rahaza_auto_attendance_selfie.router, prefix="")
router.include_router(rahaza_auto_attendance_webauthn.router, prefix="")
router.include_router(rahaza_auto_attendance_zkteco.router, prefix="")
router.include_router(rahaza_auto_attendance_approvals.router, prefix="")
router.include_router(rahaza_auto_attendance_config.router, prefix="")
