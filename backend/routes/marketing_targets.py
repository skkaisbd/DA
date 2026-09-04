"""
Marketing Account Monthly Targets
==================================
Manajemen target bulanan per akun platform & KOL/Creator.
"""
# ruff: noqa: E402
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid

from database import get_db
from auth import require_auth, serialize_doc
from core import marketing_sales_shape as _shape
from core import marketing_cycle as _cycle
from core import marketing_returns as _ret
from core import marketing_account_scope as _scope

router = APIRouter(prefix="/api/marketing/targets", tags=["marketing-targets"])


def _now(): return datetime.now(timezone.utc)
def _uid():  return str(uuid.uuid4())


def _ser_dt(v):
    """`order_date` bisa berupa string 'YYYY-MM-DD …' ATAU datetime (dua bentuk
    lahir dari dua jalur masuk: impor dan entri manual). Layar butuh satu bentuk
    yang bisa dipotong 10 huruf tanpa pengecualian."""
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v or "")


class TargetUpsert(BaseModel):
    account_id:          str
    year:                int = Field(..., ge=2020, le=2100)
    month:               int = Field(..., ge=1,    le=12)
    revenue_target:      float = Field(0, ge=0)
    orders_target:       int   = Field(0, ge=0)
    health_score_target: int   = Field(80, ge=0, le=100)
    notes:               Optional[str] = None
    # F6.5 (sesi #9) — ALASAN perubahan angka. Jejak yang menyimpan "dari 100 jt
    # ke 60 jt" tanpa alasan tetap tidak menjawab pertanyaan rapat yang sebenarnya
    # ("kenapa targetnya diturunkan?"). Tidak diwajibkan (menaikkan target rutin
    # tidak selalu punya cerita), tetapi disediakan, dicatat, dan ditampilkan.
    reason:              Optional[str] = None


# ── UPSERT ────────────────────────────────────────────────────────────────────
@router.post("", status_code=200)
async def upsert_target(data: TargetUpsert, request: Request):
    """Set/update monthly target untuk sebuah akun. Upsert by (account_id, year, month)."""
    user = await require_auth(request)
    db   = get_db()

    acc = await db.marketing_platform_accounts.find_one({"id": data.account_id}, {"_id": 0})
    if not acc:
        raise HTTPException(404, "Akun tidak ditemukan")

    # F6 — target adalah keputusan SPV/Manager Marketing. Staf toko yang bisa
    # menetapkan targetnya sendiri membuat capaian kehilangan arti.
    await _scope.assert_can_write_target(user, "target")
    await _scope.assert_account_visible(db, user, data.account_id)

    # F5.3 — target bulan yang sudah DITUTUP tidak boleh diubah lagi (HTTP 423).
    # Tanpa ini, angka yang sudah dirapatkan masih bisa berubah seminggu kemudian
    # dan notulen rapat berhenti bisa disamakan dengan sistem.
    await _cycle.assert_period_open(db, data.account_id,
                                    _cycle.period_of(data.year, data.month),
                                    action='mengubah target')

    existing = await db.marketing_account_targets.find_one(
        {"account_id": data.account_id, "year": data.year, "month": data.month},
        {"_id": 0}
    )

    if existing:
        await db.marketing_account_targets.update_one(
            {"id": existing["id"]},
            {"$set": {
                "revenue_target":      data.revenue_target,
                "orders_target":       data.orders_target,
                "health_score_target": data.health_score_target,
                "notes":               data.notes,
                "updated_by":          user.get("id"),
                "updated_at":          _now(),
            }}
        )
        doc = await db.marketing_account_targets.find_one({"id": existing["id"]}, {"_id": 0})
        await _cycle.log_change(
            db, account_id=data.account_id, entity="marketing_account_targets",
            entity_id=existing["id"], action="target_update",
            before={"revenue_target": existing.get("revenue_target"),
                    "orders_target": existing.get("orders_target")},
            after={"revenue_target": data.revenue_target,
                   "orders_target": data.orders_target},
            reason=(data.reason or "").strip(),
            user=user, period=_cycle.period_of(data.year, data.month))
        return serialize_doc({"message": "Target diupdate", "target": doc})

    doc = {
        "id":                  _uid(),
        "account_id":          data.account_id,
        "account_name":        acc.get("account_name", ""),
        "platform":            acc.get("platform", ""),
        "year":                data.year,
        "month":               data.month,
        "revenue_target":      data.revenue_target,
        "orders_target":       data.orders_target,
        "health_score_target": data.health_score_target,
        "notes":               data.notes,
        "created_by":          user.get("id"),
        "created_at":          _now(),
        "updated_at":          _now(),
    }
    await db.marketing_account_targets.insert_one(doc)
    await _cycle.log_change(
        db, account_id=data.account_id, entity="marketing_account_targets",
        entity_id=doc["id"], action="target_create", before=None,
        after={"revenue_target": data.revenue_target, "orders_target": data.orders_target},
        reason=(data.reason or "").strip(),
        user=user, period=_cycle.period_of(data.year, data.month))
    return serialize_doc({"message": "Target disimpan", "target": doc})


# ── LIST ──────────────────────────────────────────────────────────────────────
@router.get("")
async def list_targets(
    request: Request,
    year:       Optional[int] = Query(None),
    month:      Optional[int] = Query(None),
    account_id: Optional[str] = Query(None),
):
    """List target. Default: bulan & tahun berjalan."""
    user = await require_auth(request)
    db = get_db()
    now = _now()
    # F6 (sesi #10) — daftar target adalah ANGKA per toko: staf pemegang satu toko
    # tidak boleh membaca target sembilan toko.
    q: dict = await _scope.scope_filter(db, user, {
        "year":  year  or now.year,
        "month": month or now.month,
    })
    if account_id:
        q["account_id"] = account_id
    rows = await db.marketing_account_targets.find(q, {"_id": 0}).sort("account_name", 1).to_list(200)
    return serialize_doc(rows)


# ── MONTHLY SUMMARY (target vs actual) ───────────────────────────────────────
@router.get("/monthly-summary")
async def monthly_summary(
    request: Request,
    year:  int = Query(None, ge=1970, le=2999),
    month: int = Query(None, ge=1, le=12),
):
    """
    Semua akun aktif + target vs actual untuk bulan tertentu.
    Default: bulan & tahun berjalan.
    """
    await require_auth(request)
    db  = get_db()
    now = _now()
    y   = year  or now.year
    m   = month or now.month

    month_start = datetime(y, m, 1,  0, 0, 0, tzinfo=timezone.utc)
    if m == 12:
        month_end = datetime(y + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    else:
        month_end = datetime(y, m + 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    date_from = f"{y:04d}-{m:02d}-01"
    import calendar
    last_day  = calendar.monthrange(y, m)[1]
    date_to   = f"{y:04d}-{m:02d}-{last_day:02d}"

    # F6 — daftar toko dipotong ke yang di-assign ke pemakai ini
    _user = getattr(request.state, "user", None) or {}
    _q = await _scope.scope_filter(db, _user, {"status": "active"}, field="id")
    accounts = await db.marketing_platform_accounts.find(_q, {"_id": 0}).to_list(200)

    result = []
    total_rev_target = 0.0
    total_rev_actual = 0.0
    total_ord_target = 0
    total_ord_actual = 0

    for acc in accounts:
        acc_id = acc["id"]

        # Target
        tgt = await db.marketing_account_targets.find_one(
            {"account_id": acc_id, "year": y, "month": m}, {"_id": 0}
        )

        # Actual sales (total type only)
        sales = await db.marketing_sales_data.find(
            {"account_id": acc_id, "date": {"$gte": date_from, "$lte": date_to}, "revenue_type": "total"},
            {"_id": 0}      # F0.3 — dokumen lama menaruh `revenue` di akar
        ).to_list(500)

        rev_actual = sum(_shape.read_metrics(s).get("revenue", 0) for s in sales)
        ord_actual = sum(_shape.read_metrics(s).get("orders", 0) for s in sales)
        sales_days = len({s["date"] for s in sales})

        # Task stats for month
        task_count = await db.marketing_tasks.count_documents({
            "account_id": acc_id,
            "created_at": {"$gte": month_start, "$lt": month_end},
            "status": {"$ne": "cancelled"},
        })
        task_done = await db.marketing_tasks.count_documents({
            "account_id": acc_id,
            "created_at": {"$gte": month_start, "$lt": month_end},
            "status": "done",
        })

        rev_tgt = tgt["revenue_target"] if tgt else None
        ord_tgt = tgt["orders_target"]  if tgt else None

        rev_pct = round((rev_actual / rev_tgt * 100), 1) if rev_tgt and rev_tgt > 0 else None
        ord_pct = round((ord_actual / ord_tgt * 100), 1) if ord_tgt and ord_tgt > 0 else None

        result.append({
            "account_id":            acc_id,
            "account_name":          acc.get("account_name", ""),
            "account_code":          acc.get("account_code", ""),
            "platform":              acc.get("platform", ""),
            "health_score":          acc.get("health_score"),
            "target": {
                "revenue":      rev_tgt,
                "orders":       ord_tgt,
                "health_score": tgt["health_score_target"] if tgt else None,
                "notes":        tgt["notes"] if tgt else None,
            },
            "actual": {
                "revenue":    rev_actual,
                "orders":     ord_actual,
                "sales_days": sales_days,
            },
            "achievement": {
                "revenue_pct": rev_pct,
                "orders_pct":  ord_pct,
            },
            "task_stats": {
                "total":           task_count,
                "done":            task_done,
                "completion_rate": round(task_done / task_count * 100, 1) if task_count > 0 else None,
            },
        })

        total_rev_target += rev_tgt or 0
        total_rev_actual += rev_actual
        total_ord_target += ord_tgt or 0
        total_ord_actual += ord_actual

    return serialize_doc({
        "period":  {"year": y, "month": m, "date_from": date_from, "date_to": date_to},
        "summary": {
            "total_accounts":  len(accounts),
            "rev_target":      total_rev_target,
            "rev_actual":      total_rev_actual,
            "rev_pct":         round(total_rev_actual / total_rev_target * 100, 1) if total_rev_target > 0 else None,
            "ord_target":      total_ord_target,
            "ord_actual":      total_ord_actual,
        },
        "accounts": result,
    })


# ══════════════════════════════════════════════════════════════════════════════
# CREATOR TARGETS (KOL / Creator per-bulan)
# Collection: marketing_creator_targets
# Schema: { id, creator_id, creator_name, year, month,
#           revenue_target, sessions_target, viewers_target, notes }
# ══════════════════════════════════════════════════════════════════════════════

import calendar as _calendar


class CreatorTargetUpsert(BaseModel):
    creator_id:      str
    year:            int = Field(..., ge=2020, le=2100)
    month:           int = Field(..., ge=1,    le=12)
    revenue_target:  float = Field(0, ge=0)
    sessions_target: int   = Field(0, ge=0)
    viewers_target:  int   = Field(0, ge=0)
    notes:           Optional[str] = None


@router.post("/creator", status_code=200)
async def upsert_creator_target(data: CreatorTargetUpsert, request: Request):
    """Set/update monthly target untuk KOL Creator. Upsert by (creator_id, year, month).

    F5.3 — **kunci periode TIDAK dipasang di sini, dengan sengaja.** Kunci periode
    berlingkup **toko** (`marketing_period_locks.account_id`), sedangkan target
    kreator tidak milik satu toko: satu kreator bisa ditugaskan ke beberapa toko.
    Menolak target kreator karena SALAH SATU toko-nya tertutup akan menghukum
    pekerjaan yang tidak ada hubungannya, dan menolak hanya bila SEMUA toko
    tertutup adalah aturan yang tidak bisa dijelaskan ke staf. Kalau nanti F6
    memberi kreator lingkup toko yang tegas, penjaga ini ditambahkan di sini.
    """
    user = await require_auth(request)
    db   = get_db()

    creator = await db.marketing_kol_creators.find_one({"id": data.creator_id}, {"_id": 0})
    if not creator:
        raise HTTPException(404, "Creator tidak ditemukan")

    existing = await db.marketing_creator_targets.find_one(
        {"creator_id": data.creator_id, "year": data.year, "month": data.month},
        {"_id": 0}
    )

    if existing:
        await db.marketing_creator_targets.update_one(
            {"id": existing["id"]},
            {"$set": {
                "revenue_target":  data.revenue_target,
                "sessions_target": data.sessions_target,
                "viewers_target":  data.viewers_target,
                "notes":           data.notes,
                "updated_by":      user.get("id"),
                "updated_at":      _now(),
            }}
        )
        doc = await db.marketing_creator_targets.find_one({"id": existing["id"]}, {"_id": 0})
        return serialize_doc({"message": "Target creator diupdate", "target": doc})

    doc = {
        "id":              _uid(),
        "creator_id":      data.creator_id,
        "creator_name":    creator.get("name", ""),
        "creator_code":    creator.get("creator_code", ""),
        "year":            data.year,
        "month":           data.month,
        "revenue_target":  data.revenue_target,
        "sessions_target": data.sessions_target,
        "viewers_target":  data.viewers_target,
        "notes":           data.notes,
        "created_by":      user.get("id"),
        "created_at":      _now(),
        "updated_at":      _now(),
    }
    await db.marketing_creator_targets.insert_one(doc)
    return serialize_doc({"message": "Target creator disimpan", "target": doc})


@router.get("/creator")
async def list_creator_targets(
    request: Request,
    year:       Optional[int] = Query(None),
    month:      Optional[int] = Query(None),
    creator_id: Optional[str] = Query(None),
):
    """List target creator. Default: bulan & tahun berjalan."""
    user = await require_auth(request)
    db = get_db()
    now = _now()
    q: dict = {"year": year or now.year, "month": month or now.month}
    # F6 (sesi #10) — `marketing_creator_targets` tidak punya `account_id`; kreator
    # menempel ke toko lewat `assigned_account_ids`. Jadi lingkupnya dibaca dari
    # daftar kreator toko yang boleh dilihat pemakai ini.
    _vis = await _scope.visible_account_ids(db, user)
    if _vis is not None:
        _cids = [c["id"] for c in await db.marketing_kol_creators.find(
            {"assigned_account_ids": {"$in": _vis}}, {"_id": 0, "id": 1}).to_list(500)]
        q["creator_id"] = {"$in": _cids}
    if creator_id:
        q["creator_id"] = creator_id
    rows = await db.marketing_creator_targets.find(q, {"_id": 0}).sort("creator_name", 1).to_list(200)
    return serialize_doc(rows)


@router.get("/creator/monthly-summary")
async def creator_monthly_summary(
    request: Request,
    year:  int = Query(None, ge=1970, le=2999),
    month: int = Query(None, ge=1, le=12),
):
    """Semua creator aktif + target vs aktual sessions bulan ini."""
    user = await require_auth(request)
    db  = get_db()
    now = _now()
    y   = year  or now.year
    m   = month or now.month

    date_from = f"{y:04d}-{m:02d}-01"
    last_day  = _calendar.monthrange(y, m)[1]
    date_to   = f"{y:04d}-{m:02d}-{last_day:02d}"

    _cq: dict = {"status": "active"}
    _vis = await _scope.visible_account_ids(db, user)
    if _vis is not None:
        _cq["assigned_account_ids"] = {"$in": _vis}
    creators = await db.marketing_kol_creators.find(_cq, {"_id": 0}).to_list(500)

    result = []
    total_rev_tgt = 0.0
    total_rev_act = 0.0

    for c in creators:
        cid = c["id"]

        # Target per bulan ini
        tgt = await db.marketing_creator_targets.find_one(
            {"creator_id": cid, "year": y, "month": m}, {"_id": 0}
        )

        # Aktual dari sessions bulan ini
        sessions = await db.marketing_creator_sessions.find(
            {"creator_id": cid, "date": {"$gte": date_from, "$lte": date_to}},
            {"_id": 0, "revenue": 1, "viewers": 1, "orders": 1}
        ).to_list(500)

        rev_actual  = sum(s.get("revenue",  0) for s in sessions)
        sess_actual = len(sessions)
        view_actual = sum(s.get("viewers",  0) for s in sessions)

        rev_tgt  = tgt["revenue_target"]  if tgt else None
        sess_tgt = tgt["sessions_target"] if tgt else None
        view_tgt = tgt["viewers_target"]  if tgt else None

        rev_pct  = round(rev_actual  / rev_tgt  * 100, 1) if rev_tgt  and rev_tgt  > 0 else None
        sess_pct = round(sess_actual / sess_tgt * 100, 1) if sess_tgt and sess_tgt > 0 else None
        view_pct = round(view_actual / view_tgt * 100, 1) if view_tgt and view_tgt > 0 else None

        def _status(pct):
            if pct is None:
                return "no_target"
            if pct >= 90:
                return "on_track"
            if pct >= 70:
                return "warning"
            return "behind"

        result.append({
            "creator_id":   cid,
            "creator_name": c.get("name", ""),
            "creator_code": c.get("creator_code", ""),
            "status":       c.get("status", ""),
            "target": {
                "revenue":  rev_tgt,
                "sessions": sess_tgt,
                "viewers":  view_tgt,
                "notes":    tgt["notes"] if tgt else None,
            },
            "actual": {
                "revenue":  round(rev_actual),
                "sessions": sess_actual,
                "viewers":  view_actual,
            },
            "achievement": {
                "revenue_pct":    rev_pct,
                "sessions_pct":   sess_pct,
                "viewers_pct":    view_pct,
                "revenue_status": _status(rev_pct),
            },
        })

        total_rev_tgt += rev_tgt or 0
        total_rev_act += rev_actual

    return serialize_doc({
        "period": {"year": y, "month": m, "date_from": date_from, "date_to": date_to},
        "summary": {
            "total_creators": len(creators),
            "rev_target":     total_rev_tgt,
            "rev_actual":     round(total_rev_act),
            "rev_pct":        round(total_rev_act / total_rev_tgt * 100, 1) if total_rev_tgt > 0 else None,
        },
        "creators": result,
    })


@router.get("/creator/export-pdf")
async def export_creator_targets_pdf(
    request: Request,
    year:  Optional[int] = Query(None),
    month: Optional[int] = Query(None),
):
    """Export PDF Target KOL/Creator untuk bulan tertentu."""
    await require_auth(request)
    db  = get_db()
    now = _now()
    y   = year  or now.year
    m   = month or now.month

    date_from = f"{y:04d}-{m:02d}-01"
    last_day  = _calendar.monthrange(y, m)[1]
    date_to   = f"{y:04d}-{m:02d}-{last_day:02d}"

    creators = await db.marketing_kol_creators.find({"status": "active"}, {"_id": 0}).to_list(500)
    result = []
    total_rev_tgt = 0.0
    total_rev_act = 0.0

    for c in creators:
        cid = c["id"]
        tgt = await db.marketing_creator_targets.find_one(
            {"creator_id": cid, "year": y, "month": m}, {"_id": 0}
        )
        sessions = await db.marketing_creator_sessions.find(
            {"creator_id": cid, "date": {"$gte": date_from, "$lte": date_to}},
            {"_id": 0, "revenue": 1, "viewers": 1}
        ).to_list(500)

        rev_actual  = sum(s.get("revenue",  0) for s in sessions)
        sess_actual = len(sessions)
        view_actual = sum(s.get("viewers",  0) for s in sessions)

        rev_tgt  = tgt["revenue_target"]  if tgt else None
        sess_tgt = tgt["sessions_target"] if tgt else None
        view_tgt = tgt["viewers_target"]  if tgt else None

        def _pct(a, t): return round(a / t * 100, 1) if t and t > 0 else None
        def _st(p):
            if p is None:
                return "no_target"
            return "on_track" if p >= 90 else ("warning" if p >= 70 else "behind")

        result.append({
            "creator_id":   cid,
            "creator_name": c.get("name", ""),
            "creator_code": c.get("creator_code", ""),
            "target": {"revenue": rev_tgt, "sessions": sess_tgt, "viewers": view_tgt},
            "actual": {"revenue": round(rev_actual), "sessions": sess_actual, "viewers": view_actual},
            "achievement": {
                "revenue_pct":    _pct(rev_actual,  rev_tgt),
                "sessions_pct":   _pct(sess_actual, sess_tgt),
                "revenue_status": _st(_pct(rev_actual, rev_tgt)),
            },
        })
        total_rev_tgt += rev_tgt or 0
        total_rev_act += rev_actual

    summary_payload = {
        "period":  {"year": y, "month": m, "date_from": date_from, "date_to": date_to},
        "summary": {
            "total_creators": len(creators),
            "rev_target":     total_rev_tgt,
            "rev_actual":     round(total_rev_act),
            "rev_pct":        round(total_rev_act / total_rev_tgt * 100, 1) if total_rev_tgt > 0 else None,
        },
        "creators": result,
    }

    from utils.monthly_report_pdf import build_creator_target_pdf
    pdf_bytes = build_creator_target_pdf(summary_payload)

    month_names = ['','Jan','Feb','Mar','Apr','Mei','Jun','Jul','Ags','Sep','Okt','Nov','Des']
    filename = f"target-creator-{month_names[m]}-{y}.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ══════════════════════════════════════════════════════════════════════════════
# F7.4 — SCORECARD KREATOR: target vs pencapaian, dari TIGA sumber yang dipisah
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/creator/scorecard")
async def creator_scorecard(
    request: Request,
    year:       Optional[int] = Query(None, ge=2020, le=2100),
    month:      Optional[int] = Query(None, ge=1, le=12),
    creator_id: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
):
    """Pencapaian kreator bulan ini dibanding targetnya.

    **Kenapa tiga angka uang, bukan satu.** Untuk satu kreator, sistem ini punya
    tiga sumber angka yang definisinya beda:

    * `order_revenue` — omzet PESANAN NYATA yang membawa `creator_id`
      (`marketing_orders`, hasil impor Seller Center). Ini satu-satunya angka
      yang boleh dipakai untuk uang/komisi.
    * `session_revenue` — omzet yang dicatat pada sesi live kreator
      (`marketing_creator_sessions`, diketik staf saat/selepas sesi).
    * `gmv_kpi` — GMV per konten dari platform (`marketing_content_calendar.kpi`),
      angka promosi yang atribusinya milik platform.

    Menjumlahkannya = menghitung satu penjualan sampai tiga kali. Karena itu
    ketiganya ditampilkan berdampingan, dan **basis pencapaian dipilih secara
    tertulis** (`primary_basis`) dengan urutan: pesanan → sesi → GMV KPI. Layar
    wajib menampilkan basis itu supaya pembaca tahu angka mana yang sedang dinilai.
    """
    user = await require_auth(request)
    db   = get_db()
    now  = _now()
    y    = year  or now.year
    m    = month or now.month

    date_from = f"{y:04d}-{m:02d}-01"
    last_day  = _calendar.monthrange(y, m)[1]
    date_to   = f"{y:04d}-{m:02d}-{last_day:02d}"

    # ── lingkup toko (F6): staf hanya boleh melihat tokonya ───────────────────
    acc_filter: Optional[dict] = None
    if account_id:
        await _scope.assert_account_visible(db, user, account_id)
        acc_filter = account_id
    else:
        visible = await _scope.visible_account_ids(db, user)
        if visible is not None:
            acc_filter = {"$in": visible}

    creators = await db.marketing_kol_creators.find({}, {"_id": 0}).to_list(500)
    if creator_id:
        creators = [c for c in creators if c.get("id") == creator_id]

    # ── konten + KPI konten per kreator ──────────────────────────────────────
    cq: dict = {"date": {"$gte": date_from, "$lte": date_to}}
    if acc_filter is not None:
        cq["account_id"] = acc_filter
    content_by_creator: dict = {}
    for r in await db.marketing_content_calendar.find(cq, {"_id": 0}).to_list(10000):
        cid = r.get("creator_id") or ""
        b = content_by_creator.setdefault(cid, {"contents": 0, "posted": 0, "with_kpi": 0,
                                                "views": 0.0, "engagement": 0.0,
                                                "gmv_kpi": 0.0, "content_orders": 0.0})
        k = r.get("kpi") or {}
        b["contents"] += 1
        if str(r.get("status")) == "posted":
            b["posted"] += 1
        if r.get("kpi_updated_at"):
            b["with_kpi"] += 1
        b["views"] += float(k.get("views") or 0)
        b["engagement"] += sum(float(k.get(x) or 0) for x in ("likes", "comments", "shares"))
        b["gmv_kpi"] += float(k.get("gmv") or 0)
        b["content_orders"] += float(k.get("orders") or 0)

    # ── omzet PESANAN NYATA per kreator (SSOT uang) ──────────────────────────
    from core import marketing_daily_rollup as _rollup
    oq: dict = {"creator_id": {"$nin": [None, ""]},
                "$or": [
                    {"order_date": {"$gte": date_from, "$lte": date_to + "\uffff"}},
                    {"order_date": {"$gte": datetime(y, m, 1, tzinfo=timezone.utc),
                                    "$lt": datetime(y + (m // 12), (m % 12) + 1, 1,
                                                    tzinfo=timezone.utc)}},
                ]}
    if acc_filter is not None:
        oq["account_id"] = acc_filter
    order_by_creator: dict = {}
    for o in await db.marketing_orders.find(
            oq, {"_id": 0, "creator_id": 1, "status": 1, "revenue_product": 1,
                 "order_amount": 1, "items": 1, "total_payment": 1,
                 "quantity": 1}).to_list(30000):
        if (o.get("status") or "") in _cycle.EXCLUDED_FOR_REVENUE:
            continue
        b = order_by_creator.setdefault(o.get("creator_id"),
                                        {"order_revenue": 0.0, "order_count": 0,
                                         "returned_revenue": 0.0, "returned_orders": 0})
        rev = _rollup.order_revenue_product(o)
        b["order_revenue"] += rev
        b["order_count"] += 1
        # SESI #9 — retur DIPISAH memakai kalkulator retur tunggal, bukan
        # perbandingan string status yang ditulis ulang di layar ini.
        if _ret.is_returned(o):
            b["returned_revenue"] += rev
            b["returned_orders"] += 1

    def _pct(a, t):
        return round(a / t * 100, 1) if t and t > 0 else None

    def _status(pct):
        if pct is None:
            return "no_target"
        return "on_track" if pct >= 90 else ("warning" if pct >= 70 else "behind")

    rows = []
    tot = {"revenue_target": 0.0, "order_revenue": 0.0, "session_revenue": 0.0,
           "gmv_kpi": 0.0, "contents": 0, "posted": 0, "with_kpi": 0, "views": 0.0,
           "order_revenue_returned": 0.0, "orders_returned": 0,
           "order_revenue_net_returns": 0.0}
    for c in creators:
        cid = c["id"]
        tgt = await db.marketing_creator_targets.find_one(
            {"creator_id": cid, "year": y, "month": m}, {"_id": 0})
        sessions = await db.marketing_creator_sessions.find(
            {"creator_id": cid, "date": {"$gte": date_from, "$lte": date_to}},
            {"_id": 0, "revenue": 1, "viewers": 1}).to_list(500)
        sess_rev  = sum(float(s.get("revenue") or 0) for s in sessions)
        viewers   = sum(float(s.get("viewers") or 0) for s in sessions)
        cont      = content_by_creator.get(cid, {})
        orders    = order_by_creator.get(cid, {})
        order_rev = float(orders.get("order_revenue") or 0)
        gmv_kpi   = float(cont.get("gmv_kpi") or 0)
        rev_tgt   = float(tgt["revenue_target"]) if tgt else None
        sess_tgt  = tgt["sessions_target"] if tgt else None
        view_tgt  = tgt["viewers_target"] if tgt else None

        basis, basis_value = "none", 0.0
        if order_rev > 0:
            basis, basis_value = "orders", order_rev
        elif sess_rev > 0:
            basis, basis_value = "sessions", sess_rev
        elif gmv_kpi > 0:
            basis, basis_value = "gmv_kpi", gmv_kpi
        primary_pct = _pct(basis_value, rev_tgt)
        contents = int(cont.get("contents") or 0)

        rows.append({
            "creator_id": cid,
            "creator_name": c.get("name", ""),
            "creator_code": c.get("creator_code", ""),
            "status": c.get("status", ""),
            "target": {"revenue": rev_tgt, "sessions": sess_tgt, "viewers": view_tgt,
                       "notes": (tgt or {}).get("notes"), "has_target": bool(tgt)},
            "actual": {
                "order_revenue": round(order_rev, 2),
                "order_count": int(orders.get("order_count") or 0),
                # SESI #9 — omzet pesanan kreator: bruto (tetap dipakai basis
                # penilaian) + retur + net, bertiga berdampingan.
                "order_revenue_returned": round(float(orders.get("returned_revenue") or 0), 2),
                "orders_returned": int(orders.get("returned_orders") or 0),
                "order_revenue_net_returns": round(
                    max(order_rev - float(orders.get("returned_revenue") or 0), 0), 2),
                "session_revenue": round(sess_rev, 2),
                "sessions": len(sessions),
                "viewers": round(viewers),
                "gmv_kpi": round(gmv_kpi, 2),
                "content_orders": round(float(cont.get("content_orders") or 0)),
                "contents": contents,
                "posted": int(cont.get("posted") or 0),
                "with_kpi": int(cont.get("with_kpi") or 0),
                "views": round(float(cont.get("views") or 0)),
                "engagement": round(float(cont.get("engagement") or 0)),
                "kpi_coverage_pct": (round(int(cont.get("with_kpi") or 0) / contents * 100, 1)
                                     if contents else 0.0),
            },
            "achievement": {
                "primary_basis": basis,
                "primary_value": round(basis_value, 2),
                "primary_pct": primary_pct,
                "revenue_pct_orders": _pct(order_rev, rev_tgt),
                "revenue_pct_sessions": _pct(sess_rev, rev_tgt),
                "revenue_pct_gmv_kpi": _pct(gmv_kpi, rev_tgt),
                "sessions_pct": _pct(len(sessions), sess_tgt),
                "viewers_pct": _pct(viewers, view_tgt),
                "status": _status(primary_pct),
            },
        })
        tot["revenue_target"] += rev_tgt or 0
        tot["order_revenue"] += order_rev
        tot["order_revenue_returned"] += float(orders.get("returned_revenue") or 0)
        tot["orders_returned"] += int(orders.get("returned_orders") or 0)
        tot["session_revenue"] += sess_rev
        tot["gmv_kpi"] += gmv_kpi
        tot["contents"] += contents
        tot["posted"] += int(cont.get("posted") or 0)
        tot["with_kpi"] += int(cont.get("with_kpi") or 0)
        tot["views"] += float(cont.get("views") or 0)

    rows.sort(key=lambda r: (-(r["achievement"]["primary_value"]),
                             -(r["actual"]["gmv_kpi"]), r["creator_name"].lower()))
    for k in ("revenue_target", "order_revenue", "session_revenue", "gmv_kpi", "views",
              "order_revenue_returned"):
        tot[k] = round(tot[k], 2)
    tot["order_revenue_net_returns"] = round(
        max(tot["order_revenue"] - tot["order_revenue_returned"], 0), 2)
    tot["revenue_pct_orders"] = _pct(tot["order_revenue"], tot["revenue_target"])
    tot["kpi_coverage_pct"] = (round(tot["with_kpi"] / tot["contents"] * 100, 1)
                               if tot["contents"] else 0.0)
    without_target = [r["creator_name"] for r in rows if not r["target"]["has_target"]]

    return serialize_doc({
        "success": True,
        "period": {"year": y, "month": m, "date_from": date_from, "date_to": date_to},
        "rows": rows,
        "totals": tot,
        "creators_without_target": without_target,
        "data_notes": [
            "Tiga angka uang DIPISAH dan tidak dijumlah: omzet pesanan "
            "(marketing_orders.creator_id) · omzet sesi live (input staf) · GMV KPI "
            "konten (angka platform). Menjumlahkannya menghitung satu penjualan "
            "beberapa kali.",
            "Basis pencapaian dipilih berurutan: pesanan → sesi live → GMV KPI. "
            "Kolom 'Basis' menyebutkan angka mana yang sedang dinilai.",
            (f"{len(without_target)} kreator belum punya target bulan ini — "
             "pencapaiannya ditandai 'no_target', bukan 0%."),
            f"Cakupan KPI konten {tot['kpi_coverage_pct']}%: konten tanpa KPI tidak "
            "ikut menghitung views/engagement/GMV.",
            # SESI #9 — KEPUTUSAN PEMILIK: tampilkan dua-duanya. Kalimat ini
            # menggantikan catatan lama yang masih menunggu keputusan pemilik.
            (f"Omzet pesanan BRUTO Rp {_ret.rp(tot['order_revenue'])} memasukkan "
             f"{tot['orders_returned']} pesanan RETUR senilai Rp "
             f"{_ret.rp(tot['order_revenue_returned'])}; kolom 'Setelah retur' "
             f"Rp {_ret.rp(tot['order_revenue_net_returns'])}. Basis penilaian target "
             "kreator tetap memakai BRUTO — keputusan pemilik: dua angka "
             "ditampilkan, angka lama tidak digeser."),
        ],
    })


# ══════════════════════════════════════════════════════════════════════════════
# F7.4b — RINCIAN SATU KREATOR (2026-08-14)
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/creator/{creator_id}/detail")
async def creator_detail(
    creator_id: str,
    request:    Request,
    year:       Optional[int] = Query(None, ge=2020, le=2100),
    month:      Optional[int] = Query(None, ge=1, le=12),
    account_id: Optional[str] = Query(None),
    limit:      int = Query(200, ge=1, le=1000),
):
    """Dari mana angka satu baris scorecard berasal — baris demi baris.

    **Kenapa endpoint ini ada.** Scorecard menjawab "berapa", tetapi angka yang
    dibantah di rapat selalu menuntut jawaban "dari mana": konten mana yang
    membawa GMV itu, pesanan mana yang dihitung, sesi mana yang dicatat staf.
    Tanpa rincian, satu-satunya cara memeriksanya adalah membuka database —
    dan itu berarti angkanya dipercaya (atau ditolak) tanpa bukti.

    **Kontrak yang dijaga:** total di sini WAJIB sama dengan baris scorecard
    (`/creator/scorecard`) untuk kreator, bulan, dan toko yang sama:
    filter status pesanan (`EXCLUDED_FOR_REVENUE`), rumus omzet
    (`order_revenue_product`), dan definisi cakupan KPI dipakai dari sumber yang
    SAMA — bukan dihitung ulang dengan cara lain. Tiga sumber uang tetap
    DIPISAH; tidak ada satu pun angka gabungan di respons ini.
    """
    user = await require_auth(request)
    db   = get_db()
    now  = _now()
    y    = year  or now.year
    m    = month or now.month
    date_from = f"{y:04d}-{m:02d}-01"
    last_day  = _calendar.monthrange(y, m)[1]
    date_to   = f"{y:04d}-{m:02d}-{last_day:02d}"

    creator = await db.marketing_kol_creators.find_one({"id": creator_id}, {"_id": 0})
    if not creator:
        raise HTTPException(404, "Kreator tidak ditemukan")

    # lingkup toko (F6) — sama dengan scorecard
    acc_filter = None
    if account_id:
        await _scope.assert_account_visible(db, user, account_id)
        acc_filter = account_id
    else:
        visible = await _scope.visible_account_ids(db, user)
        if visible is not None:
            acc_filter = {"$in": visible}

    acc_names = {a["id"]: a.get("account_name") for a in
                 await db.marketing_platform_accounts.find(
                     {}, {"_id": 0, "id": 1, "account_name": 1}).to_list(300)}

    # ── KONTEN + KPI per konten ──────────────────────────────────────────────
    cq = {"creator_id": creator_id, "date": {"$gte": date_from, "$lte": date_to}}
    if acc_filter is not None:
        cq["account_id"] = acc_filter
    contents, c_tot = [], {"contents": 0, "posted": 0, "with_kpi": 0, "views": 0.0,
                           "engagement": 0.0, "gmv_kpi": 0.0, "content_orders": 0.0}
    for r in await db.marketing_content_calendar.find(cq, {"_id": 0}).sort(
            "date", 1).to_list(limit):
        k = r.get("kpi") or {}
        eng = sum(float(k.get(x) or 0) for x in ("likes", "comments", "shares"))
        c_tot["contents"] += 1
        if str(r.get("status")) == "posted":
            c_tot["posted"] += 1
        if r.get("kpi_updated_at"):
            c_tot["with_kpi"] += 1
        c_tot["views"] += float(k.get("views") or 0)
        c_tot["engagement"] += eng
        c_tot["gmv_kpi"] += float(k.get("gmv") or 0)
        c_tot["content_orders"] += float(k.get("orders") or 0)
        contents.append({
            "id": r.get("id"), "date": r.get("date"),
            "title": r.get("title") or r.get("content_title") or "(tanpa judul)",
            "content_type": r.get("content_type") or r.get("type") or "",
            "status": r.get("status") or "",
            "published_url": r.get("published_url") or "",
            "account_name": acc_names.get(r.get("account_id")) or "",
            "has_kpi": bool(r.get("kpi_updated_at")),
            "kpi_source": r.get("kpi_source") or "",
            "views": round(float(k.get("views") or 0)),
            "engagement": round(eng),
            "gmv_kpi": round(float(k.get("gmv") or 0), 2),
            "orders": round(float(k.get("orders") or 0)),
        })

    # ── PESANAN NYATA (SSOT uang) ────────────────────────────────────────────
    from core import marketing_daily_rollup as _rollup
    oq = {"creator_id": creator_id,
          "$or": [
              {"order_date": {"$gte": date_from, "$lte": date_to + "\uffff"}},
              {"order_date": {"$gte": datetime(y, m, 1, tzinfo=timezone.utc),
                              "$lt": datetime(y + (m // 12), (m % 12) + 1, 1,
                                              tzinfo=timezone.utc)}},
          ]}
    if acc_filter is not None:
        oq["account_id"] = acc_filter
    orders, o_tot = [], {"order_revenue": 0.0, "order_count": 0,
                         "excluded_count": 0, "excluded_revenue": 0.0,
                         "returned_counted": 0, "returned_counted_revenue": 0.0}
    for o in await db.marketing_orders.find(oq, {"_id": 0}).sort("order_date", 1).to_list(limit):
        rev = _rollup.order_revenue_product(o)
        status = (o.get("status") or "")
        excluded = status in _cycle.EXCLUDED_FOR_REVENUE
        if excluded:
            o_tot["excluded_count"] += 1
            o_tot["excluded_revenue"] += rev
        else:
            o_tot["order_revenue"] += rev
            o_tot["order_count"] += 1
            # SESI #9 — KEPUTUSAN PEMILIK SUDAH DIAMBIL: `returned` TETAP dihitung
            # sebagai omzet BRUTO (angka lama tidak digeser), dan nilai returnya
            # dilaporkan sebagai angka SENDIRI supaya "omzet setelah retur" bisa
            # dibaca di layar. Lihat core/marketing_returns.py.
            if _ret.is_returned(o):
                o_tot["returned_counted"] += 1
                o_tot["returned_counted_revenue"] += rev
        orders.append({
            "id": o.get("id"), "order_id": o.get("order_id"),
            "order_date": _ser_dt(o.get("order_date")),
            "status": status,
            "account_name": acc_names.get(o.get("account_id")) or "",
            "revenue_product": round(rev, 2),
            "items": len(o.get("items") or []),
            # baris yang TIDAK dihitung tetap ditampilkan, dengan sebabnya —
            # menyembunyikannya membuat total tampak "kurang" tanpa penjelasan
            "counted": not excluded,
            "why_not_counted": ("status pesanan dikecualikan dari omzet "
                                f"({status})" if excluded else ""),
            "note": ("status 'returned' — IKUT dihitung di omzet bruto, dan "
                     "nilainya dikurangkan di kolom 'setelah retur'"
                     if _ret.is_returned(o) and not excluded else ""),
        })

    # ── SESI LIVE (input staf) ───────────────────────────────────────────────
    sq = {"creator_id": creator_id, "date": {"$gte": date_from, "$lte": date_to}}
    sessions, s_tot = [], {"session_revenue": 0.0, "sessions": 0, "viewers": 0.0}
    for s in await db.marketing_creator_sessions.find(sq, {"_id": 0}).sort(
            "date", 1).to_list(limit):
        s_tot["session_revenue"] += float(s.get("revenue") or 0)
        s_tot["viewers"] += float(s.get("viewers") or 0)
        s_tot["sessions"] += 1
        sessions.append({
            "id": s.get("id"), "date": s.get("date"),
            # bentuk kanonik yang ditulis `marketing_kol_ops`/`marketing_kol_portal`
            # adalah `session_name`; dua nama lain hanya sisa data lama.
            "title": (s.get("session_name") or s.get("title")
                      or s.get("session_title") or ""),
            "account_name": (s.get("account_name")
                             or acc_names.get(s.get("account_id")) or ""),
            "revenue": round(float(s.get("revenue") or 0), 2),
            "viewers": round(float(s.get("viewers") or 0)),
            "peak_viewers": round(float(s.get("peak_viewers") or 0)),
            "orders": int(s.get("orders") or 0),
            "duration_minutes": s.get("duration_minutes") or None,
        })

    tgt = await db.marketing_creator_targets.find_one(
        {"creator_id": creator_id, "year": y, "month": m}, {"_id": 0})
    kpi_cov = (round(c_tot["with_kpi"] / c_tot["contents"] * 100, 1)
               if c_tot["contents"] else 0.0)
    return serialize_doc({
        "success": True,
        "creator": {"id": creator_id, "name": creator.get("name"),
                    "creator_code": creator.get("creator_code"),
                    "status": creator.get("status")},
        "period": {"year": y, "month": m, "date_from": date_from, "date_to": date_to},
        "target": {"revenue": (float(tgt["revenue_target"]) if tgt else None),
                   "sessions": (tgt or {}).get("sessions_target"),
                   "viewers": (tgt or {}).get("viewers_target"),
                   "has_target": bool(tgt)},
        "contents": contents,
        "orders": orders,
        "sessions": sessions,
        "totals": {
            "order_revenue": round(o_tot["order_revenue"], 2),
            "order_count": o_tot["order_count"],
            "orders_excluded": o_tot["excluded_count"],
            "orders_excluded_revenue": round(o_tot["excluded_revenue"], 2),
            "orders_returned_counted": o_tot["returned_counted"],
            "orders_returned_counted_revenue": round(o_tot["returned_counted_revenue"], 2),
            # SESI #9 — nama yang dipakai layar untuk kartu "Setelah retur".
            "order_revenue_net_returns": round(
                max(o_tot["order_revenue"] - o_tot["returned_counted_revenue"], 0), 2),
            "session_revenue": round(s_tot["session_revenue"], 2),
            "sessions": s_tot["sessions"],
            "viewers": round(s_tot["viewers"]),
            "gmv_kpi": round(c_tot["gmv_kpi"], 2),
            "content_orders": round(c_tot["content_orders"]),
            "contents": c_tot["contents"],
            "posted": c_tot["posted"],
            "with_kpi": c_tot["with_kpi"],
            "views": round(c_tot["views"]),
            "engagement": round(c_tot["engagement"]),
            "kpi_coverage_pct": kpi_cov,
        },
        "truncated": (len(contents) >= limit or len(orders) >= limit
                      or len(sessions) >= limit),
        "data_notes": [
            "Tiga daftar di bawah adalah TIGA SUMBER ANGKA yang berbeda dan TIDAK "
            "dijumlah: konten (GMV KPI platform) · pesanan (omzet SSOT) · sesi live "
            "(input staf). Total masing-masing sama dengan kolom yang bersesuaian di "
            "Scorecard Kreator.",
            "Pesanan berstatus dikecualikan (mis. batal/retur) tetap ditampilkan "
            "dengan tanda 'tidak dihitung' + sebabnya — bukan disembunyikan.",
            f"Cakupan KPI {kpi_cov}%: konten tanpa KPI tidak menyumbang "
            "views/engagement/GMV, jadi angka itu batas bawah, bukan angka final.",
        ] + ([
            (f"KEPUTUSAN PEMILIK (sesi #9): {o_tot['returned_counted']} pesanan "
             f"berstatus 'returned' senilai Rp {_ret.rp(o_tot['returned_counted_revenue'])} "
             "TETAP dihitung di omzet BRUTO — supaya target, capaian, dan lampiran "
             "rapat yang sudah beredar tidak berubah arti. Nilainya dikurangkan pada "
             "angka 'setelah retur' Rp "
             f"{_ret.rp(max(o_tot['order_revenue'] - o_tot['returned_counted_revenue'], 0))}, "
             "yang ditampilkan berdampingan (bukan menggantikan).")
        ] if o_tot["returned_counted"] else []),
    })
