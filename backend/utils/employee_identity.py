"""employee_identity.py — SSOT IDENTITAS KARYAWAN (siapa saya / boleh atas nama siapa).

═══════════════════════════════════════════════════════════════════════════════
KENAPA MODUL INI ADA
═══════════════════════════════════════════════════════════════════════════════
Sebelum ini ada **4 versi berbeda** fungsi "cari karyawan dari user login":
  · routes/dewi_portal_saya_hr.py::_get_linked_employee        (hanya users.employee_id)
  · routes/dewi_portal_saya_workspace.py::_get_linked_employee (hanya users.employee_id)
  · routes/dewi_kpi_shared.py::_get_linked_employee            (employee_id → user_id → email)
  · routes/dewi_portal_saya_ext.py::_get_my_employee           (employee_id → email|id|code)

dan yang PALING berbahaya di `rahaza_auto_attendance_config.py::my-status`:

    emp = await db.rahaza_employees.find_one({"email": user.get("email")})
    if not emp:
        emp = await db.rahaza_employees.find_one({})   # ← KARYAWAN PERTAMA DI DB!

Akibatnya (DIBUKTIKAN 2026-07-26 lewat browser): login sebagai **Siti Rahayu
(DA-002, HR Manager)** lalu membuka halaman absen menampilkan **"Budi Operator
(OP-001)"** — karyawan yang sama sekali berbeda. Kalau tombol absen ditekan,
kehadiran tercatat ATAS NAMA ORANG LAIN.

Penyakit kedua: endpoint tulis absensi (`selfie/clock-in`, `webauthn/clock-in`)
menerima `employee_id` **dari body request tanpa pemeriksaan kepemilikan** ⇒
siapa pun yang punya token bisa "titip absen" untuk karyawan mana pun.

SSOT ini menutup keduanya:
  · `resolve_my_employee()` — urutan resolusi TUNGGAL, dan **tidak pernah**
    jatuh ke karyawan sembarangan. Tidak ketemu ⇒ `None` (bukan tebakan).
  · `resolve_employee_for()` — kalau pemanggil meminta karyawan LAIN, wajib
    role HR/admin. Kalau bukan ⇒ HTTP 403.

JANGAN menulis ulang query penerima/identitas di modul lain. Sentinel
`scripts/verify_fase15.py` bagian S memakai AST untuk menjaga aturan ini.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

# Zona waktu operasional perusahaan (WIB). Jam shift ("07:00") disimpan sebagai
# waktu LOKAL, sedangkan clock_in disimpan UTC — konversi wajib lewat sini.
#
# 2026-08-07 (P3) — definisinya DIPINDAH ke SSOT `utils/waktu.py`. Dulu repo ini
# punya tiga pengertian "waktu Jakarta" yang terpisah (di sini offset tetap +7, di
# `core/accessory_valuation` string "Asia/Jakarta", dan puluhan `datetime.now()`
# polos). Nama `WIB` dipertahankan supaya pemakai lama tidak berubah.
from utils.waktu import WIB  # noqa: F401 — re-export demi kompatibilitas

# Role yang boleh bertindak ATAS NAMA karyawan lain (input manual/koreksi HR).
HR_ROLES = {"superadmin", "admin", "owner", "hr", "hr_manager", "manager",
            "supervisor", "supervisor_produksi"}

# Karyawan aktif. `active` adalah field kanonik di `rahaza_employees`.
ACTIVE_EMPLOYEE_FILTER = {"active": {"$ne": False}}


def is_hr(user: dict) -> bool:
    """True bila user boleh bertindak atas nama karyawan lain."""
    role = (user.get("role") or "").lower()
    if role in HR_ROLES:
        return True
    perms = user.get("_permissions") or []
    return "*" in perms or "hr.manage" in perms


async def resolve_my_employee(db, user: dict) -> Optional[dict]:
    """Karyawan milik user yang login. `None` bila belum ditautkan.

    Urutan (SATU-SATUNYA yang sah):
      1. `users.employee_id`            → tautan eksplisit yang dibuat HR (`link-user`)
      2. `rahaza_employees.user_id`     → tautan arah sebaliknya
      3. `rahaza_employees.email`       → pencocokan email (huruf kecil)

    TIDAK ADA langkah 4. Kalau tiga-tiganya gagal, jawabannya **tidak tahu** —
    bukan "ambil karyawan pertama".
    """
    if not user:
        return None

    emp_id = user.get("employee_id")
    if emp_id:
        emp = await db.rahaza_employees.find_one(
            {"id": emp_id, **ACTIVE_EMPLOYEE_FILTER}, {"_id": 0})
        if emp:
            return emp
        # user doc di JWT bisa basi — coba ambil ulang dari koleksi users
    uid = user.get("id")
    if uid:
        emp = await db.rahaza_employees.find_one(
            {"user_id": uid, **ACTIVE_EMPLOYEE_FILTER}, {"_id": 0})
        if emp:
            return emp
        udoc = await db.users.find_one({"id": uid}, {"_id": 0, "employee_id": 1})
        if udoc and udoc.get("employee_id"):
            emp = await db.rahaza_employees.find_one(
                {"id": udoc["employee_id"], **ACTIVE_EMPLOYEE_FILTER}, {"_id": 0})
            if emp:
                return emp

    email = (user.get("email") or "").strip().lower()
    if email:
        emp = await db.rahaza_employees.find_one(
            {"email": email, **ACTIVE_EMPLOYEE_FILTER}, {"_id": 0})
        if emp:
            return emp

    return None


async def require_my_employee(db, user: dict) -> dict:
    """Sama seperti `resolve_my_employee` tapi melempar 404 yang JELAS."""
    emp = await resolve_my_employee(db, user)
    if not emp:
        raise HTTPException(
            404,
            "Akun Anda belum ditautkan ke data karyawan. Minta Admin HR menautkan "
            "lewat menu Data Karyawan → Tautkan Akun.",
        )
    return emp


async def resolve_employee_for(db, user: dict, requested_id: Optional[str] = None) -> dict:
    """Karyawan yang menjadi SASARAN aksi.

    · `requested_id` kosong → karyawan milik user (self-service).
    · `requested_id` = karyawan sendiri → boleh.
    · `requested_id` = karyawan LAIN → hanya HR/admin (else 403).

    Dipakai semua endpoint TULIS absensi supaya tidak bisa "titip absen".
    """
    mine = await resolve_my_employee(db, user)
    if not requested_id:
        if not mine:
            raise HTTPException(
                404,
                "Akun Anda belum ditautkan ke data karyawan. Minta Admin HR menautkan "
                "lewat menu Data Karyawan → Tautkan Akun.",
            )
        return mine

    if mine and mine.get("id") == requested_id:
        return mine

    if not is_hr(user):
        raise HTTPException(
            403,
            "Anda hanya boleh melakukan absensi untuk diri sendiri. "
            "Pencatatan atas nama karyawan lain hanya untuk HR/Supervisor.",
        )

    emp = await db.rahaza_employees.find_one({"id": requested_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Karyawan tidak ditemukan.")
    return emp


# ═════════════════════════════════════════════════════════════════════════════
# KETERLAMBATAN — dasar "POTONGAN TERLAMBAT" & "BONUS KEHADIRAN"
# ═════════════════════════════════════════════════════════════════════════════
DEFAULT_GRACE_MINUTES = 5


async def compute_late_minutes(db, emp: dict, clock_in_utc: datetime,
                               shift_id: Optional[str] = None) -> dict:
    """Hitung keterlambatan terhadap jam masuk shift.

    Sebelumnya sistem TIDAK PERNAH membandingkan `clock_in` dengan jam shift,
    sehingga kolom "POTONGAN TERLAMBAT" di sheet THP user mustahil diisi.

    Mengembalikan dict siap-simpan (selalu ada kuncinya, supaya laporan tidak
    perlu menebak): `{late_minutes, is_late, shift_code, shift_start, grace_minutes}`
    """
    out = {"late_minutes": 0, "is_late": False, "shift_code": None,
           "shift_start": None, "grace_minutes": DEFAULT_GRACE_MINUTES}
    if not clock_in_utc:
        return out

    sid = shift_id or (emp or {}).get("shift_id")
    shift = None
    if sid:
        shift = await db.rahaza_shifts.find_one({"id": sid}, {"_id": 0})
    if not shift:
        # Tanpa shift → tidak bisa menyimpulkan terlambat. Jangan mengarang.
        return out

    start_txt = (shift.get("start_time") or "").strip()
    if not start_txt or ":" not in start_txt:
        return out
    try:
        hh, mm = (int(x) for x in start_txt.split(":")[:2])
    except Exception:  # noqa: BLE001
        return out

    if clock_in_utc.tzinfo is None:
        clock_in_utc = clock_in_utc.replace(tzinfo=timezone.utc)
    local = clock_in_utc.astimezone(WIB)
    scheduled = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    diff = int((local - scheduled).total_seconds() // 60)
    grace = int(shift.get("grace_minutes") or DEFAULT_GRACE_MINUTES)

    out.update({
        "shift_code": shift.get("code"),
        "shift_start": start_txt,
        "grace_minutes": grace,
        "late_minutes": max(0, diff - grace) if diff > grace else 0,
    })
    out["is_late"] = out["late_minutes"] > 0
    return out
