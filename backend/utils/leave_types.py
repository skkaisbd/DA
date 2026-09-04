"""leave_types.py — SSOT MASTER JENIS/ALASAN CUTI (`rahaza_leave_types`).

═══════════════════════════════════════════════════════════════════════════════
KENAPA MODUL INI ADA (BUG-4 yang dilaporkan user 2026-07-26:
"error setup cuti karyawan + master alasan/jenis cuti (collection salah)")
═══════════════════════════════════════════════════════════════════════════════

Satu koleksi, DUA bentuk dokumen yang tidak kompatibel:

| Penulis                                   | Menulis                                   |
|-------------------------------------------|-------------------------------------------|
| `rahaza_hr_seed.py` (12 jenis bawaan)      | `unpaid`, `request_type`, `requires_document`, `max_days_without_doc`, `doc_note`, `color`, `legal_basis` |
| `POST /api/rahaza/leave-types` (form HR)   | HANYA `paid`, `quota_default`, `description` |

Akibat NYATA yang bisa dibuktikan:

1. **"Cuti Tahunan" tampil TIDAK DIBAYAR.** Pembaca memakai `lt.get("paid", False)`
   (`GET /leaves`, `/leaves/{id}`, `/leaves/balance`) sementara dokumen hasil seeder
   sama sekali tidak punya field `paid` — hanya `unpaid: False`. Default `False`
   ⇒ SEMUA jenis cuti bawaan dilaporkan tidak berbayar.

2. **Jenis cuti buatan HR tidak pernah bisa mewajibkan dokumen.** Form di
   `RahazaLeaveModule.jsx` MENGIRIM `request_type`, `requires_document`,
   `max_days_without_doc`, `doc_note` — tetapi endpoint POST **membuangnya diam-diam**.
   Jadi "Izin Sakit" buatan HR selalu `request_type='cuti'` dan tidak pernah
   meminta surat dokter.

3. **Potongan gaji cuti tanpa upah tidak jalan** untuk jenis buatan HR:
   payroll (`rahaza_payroll_shared.py`) dan carry-forward (`utils/scheduler.py`)
   memfilter `{"unpaid": True}` — field yang tidak pernah ditulis form HR.

4. `PUT /leave-types/{id}` mem-`$set` **seluruh body mentah** — bisa menulis field
   sembarang, mengganti `code` menjadi duplikat, atau mematikan `active` tanpa
   pemeriksaan apa pun.

Modul ini menjadikan **`unpaid` sebagai field kanonik** (dipakai payroll &
scheduler) dan **selalu menulis cermin `paid = not unpaid`** supaya pembaca lama
tidak pecah — pola yang sama dengan `core/material_fields.py` di modul gudang.

JANGAN menulis dokumen `rahaza_leave_types` langsung dari modul lain; pakai
`build_leave_type_doc()`. Dijaga `scripts/verify_fase17_cuti.py` bagian S.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

VALID_REQUEST_TYPES = ("cuti", "sakit", "izin")

DEFAULT_COLOR = "#3b82f6"
MAX_QUOTA_DAYS = 365


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_unpaid(lt: Optional[dict]) -> bool:
    """Jenis cuti ini TIDAK dibayar? — satu-satunya penafsir dua field lama.

    Urutan: `unpaid` (kanonik) → `paid` (cermin lama) → default dibayar.
    """
    if not lt:
        return False
    if lt.get("unpaid") is not None:
        return bool(lt["unpaid"])
    if lt.get("paid") is not None:
        return not bool(lt["paid"])
    return False


def is_paid(lt: Optional[dict]) -> bool:
    """Kebalikan `is_unpaid` — dipakai semua respons API (`is_paid`)."""
    return not is_unpaid(lt)


def _int_in_range(value, name: str, lo: int, hi: int, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        raise HTTPException(400, f"{name} harus berupa angka.")
    if not (lo <= v <= hi):
        raise HTTPException(400, f"{name} harus antara {lo} dan {hi}.")
    return v


def build_leave_type_doc(body: dict, existing: Optional[dict] = None) -> dict:
    """Bentuk dokumen jenis cuti yang LENGKAP & konsisten.

    Dipakai POST (existing=None) maupun PUT (existing=dokumen lama) supaya
    keduanya tidak pernah berbeda bentuk lagi.
    """
    existing = existing or {}
    body = body or {}

    def pick(key, fallback=None):
        return body[key] if key in body and body[key] not in (None, "") else \
            existing.get(key, fallback)

    code = str(pick("code", "") or "").strip().upper()
    name = str(pick("name", "") or "").strip()
    if not code or not name:
        raise HTTPException(400, "Kode & nama jenis cuti wajib diisi.")
    if len(code) > 32:
        raise HTTPException(400, "Kode maksimal 32 karakter.")

    request_type = str(pick("request_type", "cuti") or "cuti").strip().lower()
    if request_type not in VALID_REQUEST_TYPES:
        raise HTTPException(
            400, f"request_type harus salah satu: {list(VALID_REQUEST_TYPES)}")

    # unpaid = kanonik. Terima juga `paid` (form HR lama) sebagai kebalikannya.
    if "unpaid" in body and body["unpaid"] is not None:
        unpaid = bool(body["unpaid"])
    elif "paid" in body and body["paid"] is not None:
        unpaid = not bool(body["paid"])
    else:
        unpaid = is_unpaid(existing)

    quota = _int_in_range(pick("quota_default", None), "Kuota default", 0,
                          MAX_QUOTA_DAYS, int(existing.get("quota_default") or 12))
    requires_doc = bool(pick("requires_document", False))
    max_no_doc = _int_in_range(pick("max_days_without_doc", None),
                               "Maks. hari tanpa dokumen", 0, MAX_QUOTA_DAYS,
                               int(existing.get("max_days_without_doc") or 0))

    doc = {
        "code": code,
        "name": name,
        "request_type": request_type,
        # ── dibayar / tidak: DUA field ditulis bersamaan (kanonik + cermin) ──
        "unpaid": unpaid,
        "paid": not unpaid,
        "quota_default": quota,
        "requires_document": requires_doc,
        "max_days_without_doc": max_no_doc if requires_doc else 0,
        "doc_note": str(pick("doc_note", "") or ""),
        "description": str(pick("description", "") or ""),
        "color": str(pick("color", DEFAULT_COLOR) or DEFAULT_COLOR),
        "legal_basis": str(pick("legal_basis", "") or ""),
        "max_carry_days": _int_in_range(pick("max_carry_days", None),
                                        "Maks. hari carry-forward", 0, MAX_QUOTA_DAYS,
                                        int(existing.get("max_carry_days") or 0)),
        "active": bool(pick("active", True)),
        "updated_at": _now(),
    }
    return doc


def public_leave_type(lt: dict) -> dict:
    """Bentuk jenis cuti untuk API/UI — selalu punya `paid` & `unpaid` yang sinkron."""
    d = dict(lt or {})
    d.pop("_id", None)
    d["unpaid"] = is_unpaid(lt)
    d["paid"] = not d["unpaid"]
    d.setdefault("request_type", "cuti")
    d.setdefault("requires_document", False)
    d.setdefault("max_days_without_doc", 0)
    d.setdefault("quota_default", 12)
    d.setdefault("color", DEFAULT_COLOR)
    return d
