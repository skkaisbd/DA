"""rahaza_payroll_settings.py — ATURAN POTONGAN TERLAMBAT & BONUS KEHADIRAN.

FASE 15 (2026-07-26). Sheet "Data THP" milik user punya kolom **POTONGAN
TERLAMBAT** dan **BONUS KEHADIRAN**, tapi sistem sama sekali tidak punya
tempat menyimpan ATURANNYA. Menaruh angka di kode = HR tidak bisa mengubahnya
dan agent berikutnya akan menebak-nebak.

Prinsip yang dipegang (pelajaran FASE 12 BUG-B):
  **Kalau aturannya belum diisi, sistem TIDAK memotong apa pun.**
  Lebih baik tidak memotong daripada memotong dengan angka karangan.

Disimpan di `rahaza_payroll_settings` dengan `key` sebagai penanda dokumen
(pola SSOT yang sama seperti `rahaza_costing_settings`) — tidak menambah
koleksi baru per-fitur.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from auth import log_activity, serialize_doc
from database import get_db
from routes.rahaza_payroll_shared import _require_hr

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-payroll-settings"])

LATE_KEY = "late_penalty"
ATT_BONUS_KEY = "attendance_bonus"

VALID_LATE_MODES = ("per_minute", "tiered", "per_occurrence")

DEFAULT_LATE = {
    "key": LATE_KEY,
    "enabled": False,           # SENGAJA mati sampai HR mengisi aturannya
    "mode": "per_minute",
    "amount_per_minute": 0,
    "amount_per_occurrence": 0,
    "tiers": [],                # [{from_minutes, to_minutes|None, amount}]
    "note": ("Isi aturan lalu aktifkan. Selama 'enabled' = false, sistem TIDAK "
             "memotong keterlambatan sama sekali."),
}

DEFAULT_ATT_BONUS = {
    "key": ATT_BONUS_KEY,
    "enabled": False,
    "amount": 0,
    "require_full_attendance": True,   # tidak boleh alfa
    "forfeit_if_late": True,           # hangus bila pernah terlambat
    "max_late_days_allowed": 0,
    "min_days_present": 0,
    "note": ("Bonus kehadiran diberikan lewat template tunjangan; aturan di sini "
             "menentukan kapan bonus itu HANGUS."),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get(db, key: str, default: dict) -> dict:
    doc = await db.rahaza_payroll_settings.find_one({"key": key}, {"_id": 0})
    return doc or dict(default)


@router.get("/payroll-settings/late-penalty")
async def get_late_penalty(request: Request):
    await _require_hr(request)
    return serialize_doc(await _get(get_db(), LATE_KEY, DEFAULT_LATE))


@router.put("/payroll-settings/late-penalty")
async def set_late_penalty(request: Request):
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()

    mode = (body.get("mode") or "per_minute").strip()
    if mode not in VALID_LATE_MODES:
        raise HTTPException(400, f"mode harus salah satu: {list(VALID_LATE_MODES)}")

    tiers = []
    for t in (body.get("tiers") or []):
        try:
            frm = int(t.get("from_minutes") or 0)
            to = t.get("to_minutes")
            to = int(to) if to not in (None, "") else None
            amt = float(t.get("amount") or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, "tiers harus berisi angka (from_minutes/to_minutes/amount).")
        if frm < 0 or amt < 0 or (to is not None and to < frm):
            raise HTTPException(400, "Rentang tier tidak valid (to_minutes < from_minutes atau nilai negatif).")
        tiers.append({"from_minutes": frm, "to_minutes": to, "amount": amt})

    apm = float(body.get("amount_per_minute") or 0)
    apo = float(body.get("amount_per_occurrence") or 0)
    if apm < 0 or apo < 0:
        raise HTTPException(400, "Nominal potongan tidak boleh negatif.")

    enabled = bool(body.get("enabled"))
    if enabled:
        if mode == "per_minute" and apm <= 0:
            raise HTTPException(400, "mode 'per_minute' aktif tapi amount_per_minute masih 0.")
        if mode == "per_occurrence" and apo <= 0:
            raise HTTPException(400, "mode 'per_occurrence' aktif tapi amount_per_occurrence masih 0.")
        if mode == "tiered" and not tiers:
            raise HTTPException(400, "mode 'tiered' aktif tapi belum ada tier.")

    doc = {
        "key": LATE_KEY,
        "enabled": enabled,
        "mode": mode,
        "amount_per_minute": apm,
        "amount_per_occurrence": apo,
        "tiers": tiers,
        "updated_at": _now(),
        "updated_by": user["id"],
        "updated_by_name": user.get("name", ""),
    }
    await db.rahaza_payroll_settings.update_one({"key": LATE_KEY}, {"$set": doc}, upsert=True)
    await log_activity(user["id"], user.get("name", ""), "update",
                       "rahaza.payroll_settings", LATE_KEY)
    return serialize_doc({"ok": True, "settings": doc})


@router.get("/payroll-settings/attendance-bonus")
async def get_attendance_bonus(request: Request):
    await _require_hr(request)
    return serialize_doc(await _get(get_db(), ATT_BONUS_KEY, DEFAULT_ATT_BONUS))


@router.put("/payroll-settings/attendance-bonus")
async def set_attendance_bonus(request: Request):
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()
    try:
        amount = float(body.get("amount") or 0)
        max_late = int(body.get("max_late_days_allowed") or 0)
        min_days = int(body.get("min_days_present") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "amount/max_late_days_allowed/min_days_present harus angka.")
    if amount < 0 or max_late < 0 or min_days < 0:
        raise HTTPException(400, "Nilai tidak boleh negatif.")

    doc = {
        "key": ATT_BONUS_KEY,
        "enabled": bool(body.get("enabled")),
        "amount": amount,
        "require_full_attendance": bool(body.get("require_full_attendance", True)),
        "forfeit_if_late": bool(body.get("forfeit_if_late", True)),
        "max_late_days_allowed": max_late,
        "min_days_present": min_days,
        "updated_at": _now(),
        "updated_by": user["id"],
        "updated_by_name": user.get("name", ""),
    }
    await db.rahaza_payroll_settings.update_one({"key": ATT_BONUS_KEY}, {"$set": doc}, upsert=True)
    await log_activity(user["id"], user.get("name", ""), "update",
                       "rahaza.payroll_settings", ATT_BONUS_KEY)
    return serialize_doc({"ok": True, "settings": doc})


@router.get("/payroll-settings")
async def list_settings(request: Request, key: Optional[str] = None):
    """Semua pengaturan payroll (untuk panel HR)."""
    await _require_hr(request)
    db = get_db()
    if key:
        default = DEFAULT_LATE if key == LATE_KEY else DEFAULT_ATT_BONUS
        return serialize_doc(await _get(db, key, default))
    return serialize_doc({
        "ok": True,
        "late_penalty": await _get(db, LATE_KEY, DEFAULT_LATE),
        "attendance_bonus": await _get(db, ATT_BONUS_KEY, DEFAULT_ATT_BONUS),
    })
