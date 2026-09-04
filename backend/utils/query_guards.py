"""
utils/query_guards.py — penjaga parameter query (FASE 11, BUG-R11-A)
====================================================================

MASALAH YANG DISELESAIKAN
-------------------------
Audit `memory/ROBUSTNESS_AUDIT.md` menemukan pola sistemik: nilai query string
diteruskan mentah-mentah ke Motor/`int()`/`date.fromisoformat()`, sehingga input
sampah dari klien membuat server melempar `ValueError`/`TypeError` yang tidak
tertangkap → **HTTP 500**, padahal jawaban yang benar adalah **400/422**.

Empat kelas akar masalah yang terbukti (sweep 903 endpoint × 8 varian):

  1. LIMIT_NEG  — `limit: int = 50` tanpa `ge=1`; `-1` sampai ke Motor
                  `.to_list(length=-1)` → "length must be non-negative".
  2. INT_CAST   — `int(request.query_params.get("limit"))` tanpa try/except
                  → "invalid literal for int() with base 10".
  3. DATE_PARSE — `date.fromisoformat(param)` tanpa guard
                  → "Invalid isoformat string".
  4. MONTH_OOB  — `date(year, month, 1)` dengan month=99
                  → "month must be in 1..12".

CARA PAKAI
----------
Untuk parameter yang **dideklarasikan** di tanda tangan fungsi, cukup pasang
batas pada `Query(...)` — FastAPI otomatis membalas 422 yang rapi::

    limit: int = Query(50, ge=1, le=200)
    page:  int = Query(1,  ge=1)
    month: int = Query(None, ge=1, le=12)

Untuk endpoint yang membaca `request.query_params` sendiri, pakai helper di
bawah ini — semuanya melempar `HTTPException(400)` dengan pesan berbahasa
Indonesia yang menyebut nama parameter dan nilai yang ditolak::

    from utils.query_guards import q_int, q_date, q_year_month, q_period

    limit = q_int(sp.get("limit"), default=100, name="limit", minimum=1, maximum=500)
    df    = q_date(sp.get("date_from"), name="date_from")
    y, m  = q_year_month(year, month)          # None → bulan berjalan
    y, m  = q_period(month_str, name="month")  # format "YYYY-MM"

CATATAN DESAIN
--------------
* Semua helper **tidak pernah** melempar ValueError ke pemanggil — selalu
  `HTTPException` supaya klien dapat 400 yang bisa ditindaklanjuti.
* `q_int(..., clamp=True)` dipakai bila membatasi lebih ramah daripada menolak
  (mis. `limit` yang terlalu besar cukup dipangkas ke batas atas).
* `to_date()` disediakan di sini juga karena berbagi akar masalah dengan BUG-4:
  `datetime` adalah SUBCLASS `date`, jadi urutan `isinstance` sangat penting.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional, Tuple

from fastapi import HTTPException

__all__ = [
    "q_int",
    "q_float",
    "q_bool",
    "q_date",
    "q_year_month",
    "q_period",
    "to_date",
    "date_key",
]

# Batas wajar supaya `year` tidak dipakai membangun tanggal absurd.
MIN_YEAR = 1970
MAX_YEAR = 2999


def _reject(name: str, raw: Any, expected: str) -> None:
    raise HTTPException(
        status_code=400,
        detail=f"Parameter '{name}' tidak valid: {expected}. Diterima: '{raw}'.",
    )


def q_int(
    raw: Any,
    default: Optional[int] = None,
    *,
    name: str = "param",
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
    clamp: bool = False,
) -> Optional[int]:
    """Baca query param sebagai int dengan batas — 400 (bukan 500) bila salah.

    `raw` boleh None/"" → memakai `default`.
    `clamp=True` memangkas ke batas alih-alih menolak.
    """
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        value = default
    else:
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            _reject(name, raw, "harus berupa bilangan bulat")
            return None  # pragma: no cover (dijaga _reject)

    if value is None:
        return None

    if minimum is not None and value < minimum:
        if clamp:
            value = minimum
        else:
            _reject(name, raw, f"minimal {minimum}")
    if maximum is not None and value > maximum:
        if clamp:
            value = maximum
        else:
            _reject(name, raw, f"maksimal {maximum}")
    return value


def q_float(
    raw: Any,
    default: Optional[float] = None,
    *,
    name: str = "param",
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> Optional[float]:
    """Versi float dari :func:`q_int`."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        value = default
    else:
        try:
            value = float(str(raw).strip())
        except (TypeError, ValueError):
            _reject(name, raw, "harus berupa angka")
            return None  # pragma: no cover
    if value is None:
        return None
    if minimum is not None and value < minimum:
        _reject(name, raw, f"minimal {minimum}")
    if maximum is not None and value > maximum:
        _reject(name, raw, f"maksimal {maximum}")
    return value


def q_bool(raw: Any, default: Optional[bool] = None, *, name: str = "param") -> Optional[bool]:
    """Baca boolean toleran ('true/1/yes/ya' vs 'false/0/no/tidak')."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return default
    s = str(raw).strip().lower()
    if s in ("true", "1", "yes", "y", "ya"):
        return True
    if s in ("false", "0", "no", "n", "tidak"):
        return False
    _reject(name, raw, "harus true/false")
    return None  # pragma: no cover


def q_date(
    raw: Any,
    default: Optional[date] = None,
    *,
    name: str = "date",
) -> Optional[date]:
    """Baca tanggal ISO ('YYYY-MM-DD' atau ISO datetime) — 400 bila tak terbaca."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return default
    normalized = to_date(raw)
    if normalized is None:
        _reject(name, raw, "harus tanggal ISO 'YYYY-MM-DD'")
    return normalized


def q_year_month(
    year: Any = None,
    month: Any = None,
    *,
    year_name: str = "year",
    month_name: str = "month",
) -> Tuple[int, int]:
    """Validasi pasangan year/month; None → memakai bulan berjalan.

    Mengembalikan `(year, month)` yang DIJAMIN aman dipakai `date(year, month, 1)`.
    """
    today = date.today()
    y = q_int(year, default=today.year, name=year_name, minimum=MIN_YEAR, maximum=MAX_YEAR)
    m = q_int(month, default=today.month, name=month_name, minimum=1, maximum=12)
    return int(y), int(m)  # type: ignore[arg-type]


def q_period(raw: Any, *, name: str = "month", default: Optional[str] = None) -> Tuple[int, int]:
    """Validasi periode berformat 'YYYY-MM' → `(year, month)`.

    Dipakai endpoint yang menerima bulan sebagai string (mis. analitik live host).
    """
    value = raw if (raw is not None and str(raw).strip() != "") else default
    if value is None:
        today = date.today()
        return today.year, today.month
    s = str(value).strip()
    parts = s.split("-")
    if len(parts) < 2:
        _reject(name, raw, "harus berformat 'YYYY-MM'")
    y = q_int(parts[0], name=f"{name}(tahun)", minimum=MIN_YEAR, maximum=MAX_YEAR)
    m = q_int(parts[1], name=f"{name}(bulan)", minimum=1, maximum=12)
    return int(y), int(m)  # type: ignore[arg-type]


def to_date(v: Any) -> Optional[date]:
    """Normalisasi apa pun menjadi `datetime.date` murni (atau None).

    BUG-4 (FASE 11): `datetime` adalah SUBCLASS `date`, sehingga
    `isinstance(v, date)` juga True untuk `datetime`. Cek `datetime` HARUS
    lebih dulu, kalau tidak objek datetime lolos apa adanya dan perbandingan
    `datetime` vs `date` melempar TypeError → HTTP 500.
    """
    if v is None or v == "":
        return None
    if isinstance(v, datetime):      # WAJIB sebelum `date`
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def date_key(v: Any) -> str:
    """Kunci perbandingan seragam 'YYYY-MM-DD' (atau '') untuk str/date/datetime.

    Menghindari `TypeError: '<' not supported between 'datetime' and 'str'`
    saat menyortir/membandingkan dokumen Mongo yang tipenya campur.
    """
    d = to_date(v)
    return d.isoformat() if d else ""
