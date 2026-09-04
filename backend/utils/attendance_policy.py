"""attendance_policy.py — SSOT KEBIJAKAN ABSEN (selfie wajib · geofence wajib · bukti foto).

═══════════════════════════════════════════════════════════════════════════════
KENAPA MODUL INI ADA (keputusan user 2026-07-26: "selfie + lokasi WAJIB")
═══════════════════════════════════════════════════════════════════════════════
Tiga penyakit nyata yang ditutup di akarnya:

1. **Selfie tidak pernah benar-benar disimpan.** `rahaza_auto_attendance_selfie.py`
   menulis::

       "photo_selfie_url": f"data:image/jpeg;base64,{photo_b64[:20]}..."

   yaitu **20 karakter pertama** base64 + "...". Tidak bisa dibuka, tidak bisa
   diaudit — jadi "bukti selfie" selama ini fiktif. Endpoint clock-out bahkan
   membuang `photo_base64` tanpa dipakai sama sekali
   (`body.get("photo_base64", "")` tanpa assignment).

2. **Kebijakan "wajib" tidak ditegakkan.** `_determine_approval()` memperlakukan
   geofence `not_verified` (kantor BELUM dikonfigurasi, atau GPS tidak dikirim)
   sebagai **lolos** ⇒ absen dari mana saja auto-approved. Sama untuk wajah:
   `no_reference` dan `error` dianggap lolos.

3. **Rumus haversine disalin 3 kali** (`rahaza_attendance.py` inline,
   `rahaza_auto_attendance_config.py`, `rahaza_auto_attendance_selfie.py`) —
   salah satunya (`rahaza_attendance.py`) bahkan meledak `TypeError` bila
   `office.lat` masih None karena langsung `math.radians(float(office["lat"]))`.

Modul ini adalah SATU-SATUNYA tempat aturan tersebut hidup. Jangan menyalin
ulang haversine / aturan wajib di modul lain — `scripts/verify_fase16_absen.py`
bagian S menjaganya lewat pemindaian statik.

═══════════════════════════════════════════════════════════════════════════════
KONFIGURASI (koleksi `rahaza_office_locations`, dokumen `is_primary: True`)
═══════════════════════════════════════════════════════════════════════════════
| field                | default | arti                                        |
|----------------------|---------|---------------------------------------------|
| `lat` / `lng`        | None    | titik kantor; WAJIB diisi bila geofence aktif|
| `geofence_radius_m`  | 300     | radius toleransi (meter)                     |
| `require_selfie`     | True    | absen tanpa foto ditolak                     |
| `require_geofence`   | True    | absen di luar radius / tanpa GPS ditolak     |
| `face_match_threshold`| 0.65   | ambang kemiripan wajah AI                    |

Semua nilai bisa diubah HR lewat `PUT /api/rahaza/attendance/office-location`.
"""
from __future__ import annotations

import base64
import binascii
import math
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException

import storage

DEFAULT_GEOFENCE_RADIUS_M = 300
DEFAULT_FACE_THRESHOLD = 0.65
MAX_SELFIE_BYTES = 4 * 1024 * 1024  # 4 MB — cukup untuk JPEG 480–1080p
MIN_SELFIE_BYTES = 1024             # < 1 KB pasti bukan foto wajah

# Pesan dipakai UI apa adanya (Bahasa Indonesia, menyebut LANGKAH PERBAIKAN).
MSG_OFFICE_UNSET = (
    "Lokasi kantor belum diatur, padahal kebijakan absen mewajibkan verifikasi "
    "lokasi. Minta Admin HR mengisinya di menu Absensi → Konfigurasi → Lokasi Kantor."
)
MSG_SELFIE_REQUIRED = (
    "Selfie wajib untuk absen. Izinkan akses kamera lalu ambil foto sebelum mengirim."
)
MSG_GPS_REQUIRED = (
    "Lokasi GPS wajib untuk absen. Aktifkan izin lokasi di browser/HP Anda, "
    "lalu coba lagi."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═════════════════════════════════════════════════════════════════════════════
# JARAK — SATU-SATUNYA implementasi haversine di repo
# ═════════════════════════════════════════════════════════════════════════════
def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Jarak permukaan bumi (meter) antara dua koordinat desimal."""
    R = 6371000.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dlat = p2 - p1
    dlng = math.radians(float(lng2)) - math.radians(float(lng1))
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def check_geofence(lat, lng, office: Optional[dict]) -> dict:
    """Status geofence — TIDAK melempar exception (dipakai juga untuk laporan).

    Return: `{status, distance_m, in_range, radius_m}` dengan
    `status ∈ {not_verified, in_range, out_of_range}`.
    `not_verified` berarti **tidak bisa disimpulkan** (kantor/GPS tak lengkap) —
    penegakan "tolak atau tidak" ada di `enforce_attendance_policy`.
    """
    radius = float((office or {}).get("geofence_radius_m") or DEFAULT_GEOFENCE_RADIUS_M)
    if not office or office.get("lat") is None or office.get("lng") is None:
        return {"status": "not_verified", "distance_m": None,
                "in_range": None, "radius_m": radius}
    if lat is None or lng is None:
        return {"status": "not_verified", "distance_m": None,
                "in_range": None, "radius_m": radius}
    try:
        dist = haversine_m(office["lat"], office["lng"], float(lat), float(lng))
    except (TypeError, ValueError):
        return {"status": "not_verified", "distance_m": None,
                "in_range": None, "radius_m": radius}
    return {
        "status": "in_range" if dist <= radius else "out_of_range",
        "distance_m": round(dist),
        "in_range": dist <= radius,
        "radius_m": radius,
    }


# ═════════════════════════════════════════════════════════════════════════════
# KONFIGURASI
# ═════════════════════════════════════════════════════════════════════════════
async def get_office(db) -> dict:
    """Konfigurasi kantor utama + default yang eksplisit (tak pernah None)."""
    doc = await db.rahaza_office_locations.find_one({"is_primary": True}, {"_id": 0}) or {}
    return {
        "is_primary": True,
        "name": doc.get("name") or "Kantor Utama",
        "address": doc.get("address") or "",
        "lat": doc.get("lat"),
        "lng": doc.get("lng"),
        "geofence_radius_m": int(doc.get("geofence_radius_m") or DEFAULT_GEOFENCE_RADIUS_M),
        # Kebijakan user 2026-07-26: WAJIB by default (dulu longgar diam-diam).
        "require_selfie": bool(doc.get("require_selfie", True)),
        "require_geofence": bool(doc.get("require_geofence", True)),
        "face_match_threshold": float(doc.get("face_match_threshold") or DEFAULT_FACE_THRESHOLD),
        "configured": doc.get("lat") is not None and doc.get("lng") is not None,
        "updated_at": doc.get("updated_at"),
    }


# ═════════════════════════════════════════════════════════════════════════════
# PENEGAKAN
# ═════════════════════════════════════════════════════════════════════════════
def _decode_selfie(photo_b64: str) -> bytes:
    raw = (photo_b64 or "").strip()
    if raw.startswith("data:"):                      # buang prefix data-URL
        raw = raw.split(",", 1)[-1]
    try:
        blob = base64.b64decode(raw, validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Foto selfie tidak terbaca (base64 rusak). Ambil ulang foto.")
    if len(blob) < MIN_SELFIE_BYTES:
        raise HTTPException(400, "Foto selfie terlalu kecil/kosong. Ambil ulang foto.")
    if len(blob) > MAX_SELFIE_BYTES:
        raise HTTPException(413, "Ukuran foto selfie melebihi 4 MB. Turunkan resolusi kamera.")
    return blob


def save_selfie(employee_id: str, photo_b64: str, kind: str = "in") -> Optional[str]:
    """Simpan selfie ke penyimpanan lokal, kembalikan URL `/api/uploads/...`.

    Dipanggil SETELAH `enforce_attendance_policy` supaya file tidak ditulis untuk
    absen yang toh akan ditolak.
    """
    if not photo_b64:
        return None
    blob = _decode_selfie(photo_b64)
    path = (f"attendance/{employee_id}/{date.today().isoformat()}_{kind}_"
            f"{uuid.uuid4().hex[:8]}.jpg")
    return storage.put_object(path, blob, "image/jpeg")["url"]


async def enforce_attendance_policy(db, *, photo_b64: Optional[str],
                                    lat, lng, action: str = "masuk",
                                    selfie_required: Optional[bool] = None) -> dict:
    """Tegakkan kebijakan sebelum absen dicatat. Melempar HTTPException bila gagal.

    `selfie_required=False` dipakai jalur BIOMETRIK (WebAuthn/fingerprint) yang
    sudah membuktikan identitas tanpa foto — lokasinya TETAP diperiksa.

    Return `{office, geo}` supaya pemanggil tidak perlu query ulang.
    """
    office = await get_office(db)

    need_selfie = office["require_selfie"] if selfie_required is None else bool(selfie_required)
    if need_selfie and not (photo_b64 or "").strip():
        raise HTTPException(400, MSG_SELFIE_REQUIRED)

    geo = check_geofence(lat, lng, office)
    if office["require_geofence"]:
        if not office["configured"]:
            raise HTTPException(409, MSG_OFFICE_UNSET)
        if lat is None or lng is None:
            raise HTTPException(400, MSG_GPS_REQUIRED)
        if geo["status"] == "out_of_range":
            raise HTTPException(
                403,
                f"Absen {action} ditolak: Anda berada {geo['distance_m']} m dari "
                f"{office['name']} (batas {int(geo['radius_m'])} m). "
                "Absen hanya bisa dilakukan di area kantor.",
            )
        if geo["status"] == "not_verified":
            raise HTTPException(400, MSG_GPS_REQUIRED)
    return {"office": office, "geo": geo}


def determine_approval(geo: dict, face: dict, office: dict) -> str:
    """`auto_approved` atau `pending` (menunggu HR).

    Perbedaan dengan versi lama: geofence `not_verified` TIDAK lagi dianggap
    lolos — kalau lokasi tak bisa dipastikan, HR yang memutuskan.
    """
    threshold = float((office or {}).get("face_match_threshold") or DEFAULT_FACE_THRESHOLD)
    geo_ok = geo.get("in_range") is True
    if not (office or {}).get("require_geofence", True):
        geo_ok = geo.get("in_range") is not False   # geofence dimatikan HR

    face_status = (face or {}).get("status", "not_checked")
    if face_status == "checked":
        face_ok = face.get("match") is True and float(face.get("confidence") or 0) >= threshold
    else:
        # not_checked / no_reference / error → tidak bisa disimpulkan.
        # Kalau selfie diwajibkan, ini HARUS jadi antrean HR, bukan lolos diam-diam.
        face_ok = not (office or {}).get("require_selfie", True)
    return "auto_approved" if (geo_ok and face_ok) else "pending"
