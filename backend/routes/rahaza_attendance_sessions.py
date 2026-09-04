"""rahaza_attendance_sessions.py — ISTIRAHAT & IZIN KELUAR/MASUK (bagian absensi).

═══════════════════════════════════════════════════════════════════════════════
KENAPA MODUL INI ADA
═══════════════════════════════════════════════════════════════════════════════
Permintaan user 2026-07-26: *"hanya simple clockin dan clockout tapi tidak ada
button untuk istirahat (keluar dan masuk) atau izin (keluar dan masuk) dimana
ini juga harus di record di hr"*.

Sebelum ini record absensi hanya punya `clock_in` / `clock_out`, sehingga:
  · jam istirahat ikut terhitung sebagai jam kerja (upah per jam jadi lebih besar),
  · izin keluar di tengah jam kerja tidak terlacak sama sekali.

Modul ini menambahkan **sesi keluar-masuk** di dalam satu hari kerja:
  kind = `istirahat` | `izin`
  simpan di `rahaza_attendance_events.sessions[]` (SATU dokumen per hari —
  tidak membuat koleksi baru, supaya tidak menambah SSOT baru).

Turunan yang dihitung ulang setiap perubahan (jangan dihitung di tempat lain):
  `break_minutes` · `permit_minutes` · `net_hours_worked`

`hours_worked` (rentang kotor clock-in→clock-out) SENGAJA tidak diubah artinya
supaya laporan lama tidak berubah diam-diam; payroll memakai `net_hours_worked`
bila tersedia.

═══════════════════════════════════════════════════════════════════════════════
FASE 16 (keputusan user 2026-07-26): IZIN WAJIB DISETUJUI ATASAN/HR
═══════════════════════════════════════════════════════════════════════════════
Istirahat tetap langsung jalan. **Izin** sekarang dua langkah:

  1. Karyawan MENGAJUKAN  → sesi dibuat `approval_status='pending'`, `out_at=None`
     (belum keluar, belum memotong jam kerja).
  2. HR/atasan MENYETUJUI → `approval_status='approved'` dan `out_at` diisi saat
     persetujuan (izin dihitung sejak DISETUJUI, bukan sejak diajukan, supaya
     karyawan tidak dirugikan/menguntungkan diri saat approval lama).
     MENOLAK → `approval_status='rejected'`, sesi tidak pernah menit-nya dihitung.

Endpoint persetujuan ada di `routes/rahaza_attendance_permits.py` (dipisah agar
berkas ini tetap < 500 LOC sesuai AGENT_DEVELOPMENT_RULES.md).

Kompatibilitas mundur: sesi izin LAMA tidak punya `approval_status`; itu dibaca
sebagai `approved` supaya laporan lama tidak berubah.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from auth import log_activity, require_auth, serialize_doc
from database import get_db
from utils.employee_identity import is_hr, resolve_employee_for

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-hr"])

VALID_KINDS = ("istirahat", "izin")


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today_iso() -> str:
    return date.today().isoformat()


def _aware(v):
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v if isinstance(v, datetime) else None


# ═════════════════════════════════════════════════════════════════════════════
# STATUS SESI (FASE 16) — SATU definisi, dipakai juga oleh permits & rekap HR
# ═════════════════════════════════════════════════════════════════════════════
APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"
APPROVAL_CANCELLED = "cancelled"
APPROVAL_NOT_REQUIRED = "not_required"   # istirahat


def session_approval(s: dict) -> str:
    """Status persetujuan sebuah sesi, aman untuk data LAMA.

    Sesi lama (sebelum FASE 16) tidak punya `approval_status`:
      · `istirahat` → `not_required`
      · `izin`      → dianggap `approved` (dulu memang langsung berlaku)
    """
    v = (s or {}).get("approval_status")
    if v:
        return v
    return APPROVAL_NOT_REQUIRED if (s or {}).get("kind") != "izin" else APPROVAL_APPROVED


def is_session_counted(s: dict) -> bool:
    """Sesi ini boleh memotong jam kerja?"""
    return session_approval(s) in (APPROVAL_NOT_REQUIRED, APPROVAL_APPROVED)


def is_session_out(s: dict) -> bool:
    """Karyawan sedang BERADA DI LUAR karena sesi ini (belum kembali)."""
    return bool(s) and is_session_counted(s) and bool(s.get("out_at")) and not s.get("in_at")


def is_permit_pending(s: dict) -> bool:
    return (s or {}).get("kind") == "izin" and session_approval(s) == APPROVAL_PENDING


def recompute_session_totals(rec: dict) -> dict:
    """SSOT turunan sesi. Dipanggil setiap kali `sessions[]` berubah.

    Dipakai juga oleh clock-out supaya `net_hours_worked` tidak pernah basi.

    FASE 16: sesi izin hanya dihitung bila **DISETUJUI**. Pengajuan yang masih
    `pending`, `rejected`, atau `cancelled` TIDAK boleh memotong jam kerja —
    kalau ikut dihitung, penolakan justru merugikan karyawan.
    """
    brk = 0.0
    prm = 0.0
    for s in rec.get("sessions") or []:
        if not is_session_counted(s):
            continue
        out_at, in_at = _aware(s.get("out_at")), _aware(s.get("in_at"))
        if not out_at or not in_at:
            continue
        mins = max(0.0, (in_at - out_at).total_seconds() / 60)
        if s.get("kind") == "izin":
            prm += mins
        else:
            brk += mins
    gross = float(rec.get("hours_worked") or 0)
    net = max(0.0, gross - (brk + prm) / 60)
    return {
        "break_minutes": round(brk),
        "permit_minutes": round(prm),
        "net_hours_worked": round(net, 2),
    }


async def _today_record(db, emp_id: str, day: Optional[str] = None) -> dict:
    day = day or _today_iso()
    rec = await db.rahaza_attendance_events.find_one(
        {"employee_id": emp_id, "date": day}, {"_id": 0})
    if not rec:
        raise HTTPException(
            400, "Belum ada absen masuk hari ini. Lakukan Absen Masuk dulu.")
    if not rec.get("clock_in"):
        raise HTTPException(
            400, "Belum absen masuk hari ini. Lakukan Absen Masuk dulu.")
    if rec.get("clock_out"):
        raise HTTPException(
            400, "Sudah absen pulang hari ini — sesi istirahat/izin tidak bisa dibuka lagi.")
    return rec


def _open_session(rec: dict) -> Optional[dict]:
    """Sesi yang membuat karyawan SEDANG di luar (istirahat / izin disetujui)."""
    for s in rec.get("sessions") or []:
        if is_session_out(s):
            return s
    return None


def _pending_permit(rec: dict) -> Optional[dict]:
    """Pengajuan izin yang masih menunggu keputusan."""
    for s in rec.get("sessions") or []:
        if is_permit_pending(s):
            return s
    return None


@router.get("/attendance/sessions/active")
async def active_session(request: Request, employee_id: Optional[str] = None):
    """Sesi istirahat/izin yang masih terbuka (untuk menentukan label tombol)."""
    user = await require_auth(request)
    db = get_db()
    emp = await resolve_employee_for(db, user, employee_id)
    rec = await db.rahaza_attendance_events.find_one(
        {"employee_id": emp["id"], "date": _today_iso()}, {"_id": 0})
    if not rec:
        return {"ok": True, "active": None, "pending_permit": None, "sessions": [],
                "break_minutes": 0, "permit_minutes": 0}
    return serialize_doc({
        "ok": True,
        "active": _open_session(rec),
        "pending_permit": _pending_permit(rec),
        "sessions": rec.get("sessions") or [],
        "break_minutes": rec.get("break_minutes", 0),
        "permit_minutes": rec.get("permit_minutes", 0),
        "net_hours_worked": rec.get("net_hours_worked"),
    })


@router.post("/attendance/sessions/start")
async def start_session(request: Request):
    """Mulai ISTIRAHAT, atau AJUKAN IZIN keluar.

    Body: `{ kind: 'istirahat'|'izin', reason?, lat?, lng?, employee_id? }`
    `employee_id` hanya boleh diisi HR (dijaga `resolve_employee_for`).

    FASE 16 — beda perlakuan:
      · `istirahat` → langsung keluar (`out_at` = sekarang).
      · `izin`      → **pengajuan**: `approval_status='pending'`, `out_at=None`.
        Karyawan baru resmi keluar setelah HR/atasan menyetujui.
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    kind = (body.get("kind") or "istirahat").strip().lower()
    if kind not in VALID_KINDS:
        raise HTTPException(400, f"kind harus salah satu: {list(VALID_KINDS)}")

    emp = await resolve_employee_for(db, user, body.get("employee_id"))
    rec = await _today_record(db, emp["id"])

    if _open_session(rec):
        raise HTTPException(
            400, "Masih ada sesi keluar yang belum ditutup. Tekan 'Kembali' dulu.")
    if _pending_permit(rec):
        raise HTTPException(
            400, "Masih ada pengajuan izin yang menunggu persetujuan. "
                 "Tunggu keputusan HR atau batalkan pengajuan Anda dulu.")

    reason = (body.get("reason") or "").strip()
    if kind == "izin" and not reason:
        raise HTTPException(400, "Alasan wajib diisi untuk izin keluar.")

    now = _now()
    is_izin = kind == "izin"
    geo = ({"lat": body.get("lat"), "lng": body.get("lng")}
           if body.get("lat") is not None else None)
    sess = {
        "id": _uid(),
        "kind": kind,
        # Izin belum keluar sampai disetujui → out_at menyusul saat approve.
        "out_at": None if is_izin else now,
        "in_at": None,
        "minutes": None,
        "reason": reason,
        "geo_out": geo,
        "geo_in": None,
        "by_user_id": user["id"],
        "by_user_name": user.get("name", ""),
        "on_behalf": bool(body.get("employee_id")) and is_hr(user),
        # ── FASE 16 approval ──────────────────────────────────────────────
        "approval_status": APPROVAL_PENDING if is_izin else APPROVAL_NOT_REQUIRED,
        "requested_at": now if is_izin else None,
        "approved_by": None,
        "approved_by_name": None,
        "approved_at": None,
        "decision_notes": None,
    }
    await db.rahaza_attendance_events.update_one(
        {"id": rec["id"]},
        {"$push": {"sessions": sess}, "$set": {"updated_at": now}},
    )
    await log_activity(user["id"], user.get("name", ""),
                       "izin-diajukan" if is_izin else "istirahat-keluar",
                       "attendance", emp["id"])

    if is_izin:
        await _notify_permit_requested(db, emp, sess, rec)

    fresh = await db.rahaza_attendance_events.find_one({"id": rec["id"]}, {"_id": 0})
    return serialize_doc({
        "ok": True,
        "session": sess,
        "attendance": fresh,
        "requires_approval": is_izin,
        "message": ("Pengajuan izin terkirim — menunggu persetujuan atasan/HR."
                    if is_izin else "Istirahat dimulai."),
    })


async def _notify_permit_requested(db, emp: dict, sess: dict, rec: dict) -> None:
    """Beritahu HR/atasan ada izin menunggu keputusan (tak boleh menggagalkan tulis)."""
    try:
        from routes.rahaza_notifications import publish_notification
        await publish_notification(
            db,
            type_="attendance_permit_request",
            severity="warning",
            title="Izin keluar menunggu persetujuan",
            message=(f"{emp.get('name', '-')} ({emp.get('employee_code', '-')}) "
                     f"mengajukan izin keluar: \"{sess.get('reason', '')}\""),
            link_module="hr-attendance-sessions",
            link_id=sess.get("id"),
            target_roles=["superadmin", "admin", "owner", "hr",
                          "manager", "supervisor", "supervisor_produksi"],
            dedup_key=f"permit-req-{sess.get('id')}",
        )
    except Exception:  # noqa: BLE001 — notifikasi tidak boleh menggagalkan absen
        import logging
        logging.getLogger(__name__).debug("notif izin gagal", exc_info=True)


@router.post("/attendance/sessions/end")
async def end_session(request: Request):
    """Tutup sesi keluar (kembali kerja). Body: `{ lat?, lng?, employee_id? }`"""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    emp = await resolve_employee_for(db, user, body.get("employee_id"))
    rec = await _today_record(db, emp["id"])

    sess = _open_session(rec)
    if not sess:
        if _pending_permit(rec):
            raise HTTPException(
                400, "Izin Anda belum disetujui — belum ada sesi berjalan yang "
                     "bisa ditutup.")
        raise HTTPException(400, "Tidak ada sesi istirahat/izin yang terbuka.")

    now = _now()
    out_at = _aware(sess.get("out_at"))
    minutes = round(max(0.0, (now - out_at).total_seconds() / 60)) if out_at else 0

    sessions = list(rec.get("sessions") or [])
    for s in sessions:
        if s.get("id") == sess.get("id"):
            s["in_at"] = now
            s["minutes"] = minutes
            s["geo_in"] = ({"lat": body.get("lat"), "lng": body.get("lng")}
                           if body.get("lat") is not None else None)
            break

    rec["sessions"] = sessions
    totals = recompute_session_totals(rec)
    await db.rahaza_attendance_events.update_one(
        {"id": rec["id"]},
        {"$set": {"sessions": sessions, "updated_at": now, **totals}},
    )
    await log_activity(user["id"], user.get("name", ""),
                       f"{sess.get('kind')}-masuk", "attendance", emp["id"])
    fresh = await db.rahaza_attendance_events.find_one({"id": rec["id"]}, {"_id": 0})
    return serialize_doc({"ok": True, "minutes": minutes, "attendance": fresh, **totals})


@router.get("/attendance/sessions")
async def list_sessions(request: Request, from_date: Optional[str] = None,
                        to_date: Optional[str] = None,
                        employee_id: Optional[str] = None,
                        kind: Optional[str] = None,
                        status: Optional[str] = None,
                        limit: int = 1000):
    """Rekap sesi istirahat/izin untuk HR (dan karyawan untuk dirinya sendiri).

    Filter: `from_date`, `to_date` (YYYY-MM-DD), `employee_id`, `kind`
    (istirahat|izin), `status` (pending|approved|rejected|cancelled|not_required).
    Menyertakan ringkasan agar UI tidak perlu menghitung ulang.
    """
    user = await require_auth(request)
    db = get_db()

    q: dict = {"sessions.0": {"$exists": True}}
    if employee_id or not is_hr(user):
        emp = await resolve_employee_for(db, user, employee_id)
        q["employee_id"] = emp["id"]
    if from_date or to_date:
        rng = {}
        if from_date:
            rng["$gte"] = from_date
        if to_date:
            rng["$lte"] = to_date
        q["date"] = rng

    limit = max(1, min(int(limit or 1000), 5000))
    rows = await db.rahaza_attendance_events.find(q, {"_id": 0}).sort("date", -1).to_list(limit)
    emp_ids = list({r["employee_id"] for r in rows if r.get("employee_id")})
    emps = await db.rahaza_employees.find(
        {"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "name": 1, "employee_code": 1}
    ).to_list(500) if emp_ids else []
    e_map = {e["id"]: e for e in emps}

    out = []
    summary = {"istirahat_count": 0, "izin_count": 0,
               "istirahat_minutes": 0, "izin_minutes": 0,
               "pending": 0, "approved": 0, "rejected": 0, "cancelled": 0}
    for r in rows:
        e = e_map.get(r.get("employee_id")) or {}
        for s in r.get("sessions") or []:
            if kind and s.get("kind") != kind:
                continue
            appr = session_approval(s)
            if status and appr != status:
                continue
            mins = int(s.get("minutes") or 0)
            if s.get("kind") == "izin":
                summary["izin_count"] += 1
                if is_session_counted(s):
                    summary["izin_minutes"] += mins
            else:
                summary["istirahat_count"] += 1
                summary["istirahat_minutes"] += mins
            if appr in summary:
                summary[appr] += 1
            out.append({
                **s,
                "approval_status": appr,
                "counted": is_session_counted(s),
                "date": r.get("date"),
                "employee_id": r.get("employee_id"),
                "employee_name": e.get("name", "?"),
                "employee_code": e.get("employee_code", "-"),
            })
    out.sort(key=lambda x: (x.get("date") or "", str(x.get("out_at") or x.get("requested_at") or "")),
             reverse=True)
    return serialize_doc({"ok": True, "total": len(out), "items": out, "summary": summary})
