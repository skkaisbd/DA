"""routes/marketing_kol_incentive.py — **INSENTIF & TIPE KREATOR** (sesi #34).

KEPUTUSAN PEMILIK (2026-08-23)
------------------------------
* Kreator punya **3 tipe**: `new` (belum punya akun portal — datanya diinput staf
  marketing), `kontrak`, `continue`.
* **Hanya `kontrak` & `continue` mendapat insentif.** Bentuknya bisa DUA-DUANYA
  dan dikonfigurasi per kreator:
    - `per_pcs`      : Rp per pcs terjual (akumulatif)
    - `target_bonus` : bonus sekali bila target pcs periode tercapai
* **Yang menginput pcs terjual adalah STAF MARKETING** (bukan kreator) — jadi
  angka insentif tidak pernah lahir dari klaim orang yang dibayar.
* **Periode default 3 bulan**, bisa dikonfigurasi. Periode habis ⇒ hitungan
  kembali dari 0, tetapi periode lama TIDAK dihapus (jejaknya dipakai membayar).

CARA PERIODE DIHITUNG (dan kenapa begini)
-----------------------------------------
Periode TIDAK disimpan sebagai "sisa hari" yang harus di-update tiap hari (cara
itu pasti basi kalau tidak ada yang membuka layar). Ia dihitung dari
`period_start` + `period_months`: periode ke-n adalah jendela yang memuat hari
ini. Entri pcs menyimpan TANGGALnya, jadi "reset" bukan penghapusan — melainkan
jendela yang bergeser. Ini membuat angka periode lama tetap bisa dibuka kembali
kalau pembayarannya dipertanyakan.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import log_activity, require_auth, serialize_doc
from database import get_db

router = APIRouter(prefix="/api/marketing/kol", tags=["marketing-kol-incentive"])

CREATORS = "marketing_kol_creators"
ENTRIES = "marketing_creator_incentive_entries"

CREATOR_TYPES = ("new", "kontrak", "continue")
INCENTIVE_TYPES = ("new",)          # tipe yang TIDAK dapat insentif
DEFAULT_PERIOD_MONTHS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _f(v, d=0.0) -> float:
    try:
        return float(v if v not in (None, "") else d)
    except (TypeError, ValueError):
        return float(d)


def _add_months(d: date, months: int) -> date:
    y, m = divmod((d.month - 1) + months, 12)
    y += d.year
    m += 1
    day = min(d.day, [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def _period_window(cfg: dict, today: date | None = None) -> dict:
    """Jendela periode yang memuat HARI INI (bergulir dari `period_start`)."""
    today = today or datetime.now(timezone.utc).date()
    months = int(cfg.get("period_months") or DEFAULT_PERIOD_MONTHS)
    months = max(1, months)
    raw_start = cfg.get("period_start") or today.replace(day=1).isoformat()
    try:
        start = date.fromisoformat(str(raw_start)[:10])
    except ValueError:
        start = today.replace(day=1)
    idx = 0
    while True:
        end = _add_months(start, months)
        if today < end or idx > 200:
            break
        start = end
        idx += 1
    return {"start": start.isoformat(),
            "end": (_add_months(start, months)).isoformat(),
            "period_months": months, "period_index": idx}


def _norm_cfg(raw: dict | None) -> dict:
    raw = raw or {}
    return {
        "mode": (raw.get("mode") or "none"),            # none|per_pcs|target_bonus|both
        "rate_per_pcs": _f(raw.get("rate_per_pcs")),
        "target_pcs": int(_f(raw.get("target_pcs"))),
        "bonus_amount": _f(raw.get("bonus_amount")),
        "period_months": int(_f(raw.get("period_months"), DEFAULT_PERIOD_MONTHS)) or DEFAULT_PERIOD_MONTHS,
        "period_start": raw.get("period_start") or "",
        "notes": raw.get("notes") or "",
    }


async def _creator(db, creator_id: str) -> dict:
    c = await db[CREATORS].find_one({"id": creator_id}, {"_id": 0, "login_password_hash": 0})
    if not c:
        raise HTTPException(404, "Kreator tidak ditemukan")
    return c


async def _summary(db, creator: dict) -> dict:
    cfg = _norm_cfg(creator.get("incentive"))
    win = _period_window(cfg)
    ctype = creator.get("creator_type") or "new"
    rows = await db[ENTRIES].find(
        {"creator_id": creator["id"], "date": {"$gte": win["start"], "$lt": win["end"]}},
        {"_id": 0}).sort("date", -1).to_list(1000)
    pcs = int(sum(_f(r.get("pcs")) for r in rows))
    per_pcs_amount = 0.0
    bonus_amount = 0.0
    if ctype not in INCENTIVE_TYPES and cfg["mode"] in ("per_pcs", "both"):
        per_pcs_amount = round(pcs * cfg["rate_per_pcs"], 2)
    target_hit = bool(cfg["target_pcs"] and pcs >= cfg["target_pcs"])
    if ctype not in INCENTIVE_TYPES and cfg["mode"] in ("target_bonus", "both") and target_hit:
        bonus_amount = round(cfg["bonus_amount"], 2)
    return {
        "creator_id": creator["id"], "creator_name": creator.get("name"),
        "creator_code": creator.get("creator_code"),
        "creator_type": ctype,
        "eligible": ctype not in INCENTIVE_TYPES,
        "eligible_reason": ("Kreator tipe NEW belum dapat insentif (keputusan pemilik) — "
                            "ubah tipe ke kontrak/continue kalau sudah berhak."
                            if ctype in INCENTIVE_TYPES else ""),
        "config": cfg,
        "period": win,
        "pcs_sold": pcs,
        "target_pcs": cfg["target_pcs"],
        "target_hit": target_hit,
        "progress_pct": (round(pcs / cfg["target_pcs"] * 100, 1) if cfg["target_pcs"] else 0.0),
        "per_pcs_amount": per_pcs_amount,
        "bonus_amount": bonus_amount,
        "total_incentive": round(per_pcs_amount + bonus_amount, 2),
        "entries": serialize_doc(rows[:100]),
        "entry_count": len(rows),
    }


# ══════════════════════════════════════════════════════════════════════════════
@router.get("/creators/{creator_id}/incentive")
async def get_incentive(creator_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    return {"ok": True, **await _summary(db, await _creator(db, creator_id))}


class IncentiveCfgIn(BaseModel):
    mode: str = Field("none", description="none | per_pcs | target_bonus | both")
    rate_per_pcs: float = Field(0, ge=0)
    target_pcs: int = Field(0, ge=0)
    bonus_amount: float = Field(0, ge=0)
    period_months: int = Field(DEFAULT_PERIOD_MONTHS, ge=1, le=24)
    period_start: str = ""
    notes: str = ""


@router.put("/creators/{creator_id}/incentive")
async def set_incentive(creator_id: str, body: IncentiveCfgIn, request: Request):
    await require_auth(request)
    user = getattr(request.state, "user", {}) or {}
    db = get_db()
    creator = await _creator(db, creator_id)
    if body.mode not in ("none", "per_pcs", "target_bonus", "both"):
        raise HTTPException(400, "mode harus none | per_pcs | target_bonus | both")
    cfg = _norm_cfg(body.model_dump())
    if not cfg["period_start"]:
        cfg["period_start"] = datetime.now(timezone.utc).date().replace(day=1).isoformat()
    await db[CREATORS].update_one({"id": creator_id},
                                  {"$set": {"incentive": cfg, "updated_at": _now()}})
    await log_activity(user.get("id", "system"), user.get("name") or user.get("email", "system"),
                       "update", "marketing_kol_incentive",
                       f"Konfigurasi insentif {creator.get('name')}: {cfg['mode']}")
    creator["incentive"] = cfg
    return {"ok": True, **await _summary(db, creator)}


class EntryIn(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    pcs: int = Field(..., ge=1)
    account_id: str = ""
    note: str = ""


@router.post("/creators/{creator_id}/incentive/entries")
async def add_entry(creator_id: str, body: EntryIn, request: Request):
    """Tracker pcs terjual — DIINPUT STAF MARKETING (bukan kreator)."""
    await require_auth(request)
    user = getattr(request.state, "user", {}) or {}
    db = get_db()
    creator = await _creator(db, creator_id)
    try:
        date.fromisoformat(body.date[:10])
    except ValueError:
        raise HTTPException(400, "tanggal harus YYYY-MM-DD") from None
    doc = {
        "id": str(uuid.uuid4()), "creator_id": creator_id,
        "date": body.date[:10], "pcs": int(body.pcs),
        "account_id": body.account_id or "", "note": body.note or "",
        "entered_by": user.get("name") or user.get("email") or "system",
        "entered_by_id": user.get("id", ""), "created_at": _now(),
    }
    await db[ENTRIES].insert_one(dict(doc))
    await log_activity(user.get("id", "system"), doc["entered_by"], "create",
                       "marketing_kol_incentive",
                       f"Tracker insentif {creator.get('name')}: +{body.pcs} pcs ({body.date[:10]})")
    return {"ok": True, "entry": serialize_doc({k: v for k, v in doc.items() if k != "_id"}),
            **await _summary(db, creator)}


@router.delete("/creators/{creator_id}/incentive/entries/{entry_id}")
async def del_entry(creator_id: str, entry_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    creator = await _creator(db, creator_id)
    res = await db[ENTRIES].delete_one({"id": entry_id, "creator_id": creator_id})
    if not res.deleted_count:
        raise HTTPException(404, "Entri tracker tidak ditemukan")
    return {"ok": True, **await _summary(db, creator)}


@router.post("/creators/{creator_id}/incentive/close-period")
async def close_period(creator_id: str, request: Request):
    """Tutup periode & mulai periode baru HARI INI (hitungan kembali dari 0).

    Entri periode lama TIDAK dihapus — ia tetap bisa dibuka sebagai bukti bayar.
    """
    await require_auth(request)
    user = getattr(request.state, "user", {}) or {}
    db = get_db()
    creator = await _creator(db, creator_id)
    cfg = _norm_cfg(creator.get("incentive"))
    closing = await _summary(db, creator)
    # Periode BARU dimulai BESOK, bukan hari ini: entri bertanggal hari ini
    # adalah bagian periode yang baru saja DITUTUP (dan sudah dibayar). Kalau
    # dimulai hari ini, pcs hari ini terhitung dua kali — sekali di periode lama
    # yang dibayar, sekali lagi di periode baru.
    today = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    history = creator.get("incentive_history") or []
    history.append({
        "closed_at": _now().isoformat(), "closed_by": user.get("name") or "system",
        "period": closing["period"], "pcs_sold": closing["pcs_sold"],
        "total_incentive": closing["total_incentive"],
    })
    cfg["period_start"] = today
    await db[CREATORS].update_one(
        {"id": creator_id},
        {"$set": {"incentive": cfg, "incentive_history": history[-24:], "updated_at": _now()}})
    creator["incentive"] = cfg
    return {"ok": True, "closed": closing["total_incentive"],
            "closed_period": closing["period"], **await _summary(db, creator)}


@router.get("/creators-incentive-overview")
async def overview(request: Request, creator_type: str = Query("")):
    """Papan pantau insentif semua kreator periode berjalan (untuk staf marketing)."""
    user = await require_auth(request)
    db = get_db()
    q: dict = {"status": {"$ne": "inactive"}}
    if creator_type:
        q["creator_type"] = creator_type
    # LINGKUP TOKO (INV-F6RBAC): staf hanya melihat kreator yang di-assign ke
    # toko yang boleh ia lihat. Tanpa ini, papan insentif membocorkan angka
    # penjualan & nominal insentif SELURUH kreator ke staf toko mana pun.
    from core import marketing_account_scope as _scope
    visible = await _scope.visible_account_ids(db, user)
    if visible is not None:
        q["assigned_account_ids"] = {"$in": visible}
    creators = await db[CREATORS].find(q, {"_id": 0, "login_password_hash": 0}).to_list(500)
    rows = [await _summary(db, c) for c in creators]
    rows.sort(key=lambda r: -r["total_incentive"])
    return {
        "ok": True,
        "data": [{k: v for k, v in r.items() if k != "entries"} for r in rows],
        "totals": {
            "creators": len(rows),
            "eligible": sum(1 for r in rows if r["eligible"]),
            "pcs_sold": sum(r["pcs_sold"] for r in rows),
            "incentive": round(sum(r["total_incentive"] for r in rows), 2),
        },
    }
