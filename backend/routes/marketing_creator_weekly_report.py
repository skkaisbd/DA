"""routes.marketing_creator_weekly_report — RAPOR KREATOR MINGGUAN (sesi #35).

Layar staf: Portal Marketing → KOL & Creator → tab **Rapor Mingguan**.
Kreator membaca rapornya sendiri lewat `GET /api/marketing/creator-portal/my-weekly-report`.

Pengiriman memakai SMTP yang SUDAH ada (Pusat Notifikasi → Konfigurasi Provider).
Bila SMTP belum diisi, rapor TETAP dibuat & tersimpan (status `skipped_no_smtp`) dan
kreator masih bisa membacanya di portalnya — tidak pernah gagal senyap.
WhatsApp sengaja TIDAK dipakai: butuh penyedia berbayar (keputusan pemilik).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import log_activity, require_auth, serialize_doc
from core import creator_weekly_report as wr
from database import get_db
from utils import email_sender

router = APIRouter(prefix="/api/marketing/kol", tags=["marketing-kol-weekly-report"])

RUNS = wr.RUNS
CONFIG_COLL = "dewi_provider_config"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _scoped_creator_ids(db, user) -> list[str] | None:
    """Kreator yang boleh dilihat pemakai ini (None = semua)."""
    from core import marketing_account_scope as _scope
    visible = await _scope.visible_account_ids(db, user)
    if visible is None:
        return None
    docs = await db[wr.CREATORS].find(
        {"assigned_account_ids": {"$in": visible}}, {"_id": 0, "id": 1}).to_list(500)
    return [d["id"] for d in docs]


@router.get("/weekly-report")
async def weekly_report(request: Request,
                        week_end: str = Query("", description="YYYY-MM-DD (bawaan: hari ini WIB)"),
                        creator_id: str = Query("")):
    user = await require_auth(request)
    db = get_db()
    ids: list[str] | None
    if creator_id:
        allowed = await _scoped_creator_ids(db, user)
        if allowed is not None and creator_id not in allowed:
            raise HTTPException(403, "Kreator ini tidak termasuk lingkup toko Anda.")
        ids = [creator_id]
    else:
        ids = await _scoped_creator_ids(db, user)
    try:
        data = await wr.build_report(db, week_end=week_end or None, creator_ids=ids)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    sent = {}
    for r in await db[RUNS].find(
            {"week_end": data["period"]["end"]},
            {"_id": 0, "body_text": 0, "subject": 0, "top_contents": 0}).to_list(1000):
        sent[r.get("creator_id")] = r
    for row in data["rows"]:
        run = sent.get(row["creator_id"])
        row["last_sent"] = serialize_doc(run) if run else None
    return serialize_doc({"ok": True, **data})


class SendIn(BaseModel):
    week_end: str = ""
    creator_ids: list[str] = Field(default_factory=list)
    force: bool = False


@router.post("/weekly-report/send")
async def send_weekly_report(body: SendIn, request: Request):
    """Kirim rapor pekan ini ke kreator (email). Idempoten per (kreator, pekan)."""
    user = await require_auth(request)
    db = get_db()
    allowed = await _scoped_creator_ids(db, user)
    if body.creator_ids and allowed is not None:
        outside = [c for c in body.creator_ids if c not in allowed]
        if outside:
            raise HTTPException(403, f"{len(outside)} kreator di luar lingkup toko Anda — "
                                     "rapor tidak dikirim.")
    ids = body.creator_ids if body.creator_ids else allowed
    try:
        data = await wr.build_report(db, week_end=body.week_end or None, creator_ids=ids)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    period = data["period"]
    cfg = await db[CONFIG_COLL].find_one({"_type": "main"}) or {}
    smtp_ready = email_sender.smtp_status(cfg)["configured"]

    results = []
    for row in data["rows"]:
        existing = await db[RUNS].find_one(
            {"creator_id": row["creator_id"], "week_end": period["end"]}, {"_id": 0})
        if existing and existing.get("status") == "sent" and not body.force:
            results.append({"creator_id": row["creator_id"], "creator_name": row["creator_name"],
                            "status": "already_sent", "sent_at": existing.get("sent_at"),
                            "message": "Rapor pekan ini sudah pernah dikirim — pakai 'Kirim ulang'."})
            continue
        subject, body_text = wr.compose_email(row, period)
        snapshot = {k: row[k] for k in (
            "contents", "posted", "with_kpi", "kpi_coverage_pct", "views", "engagement",
            "engagement_rate", "orders_kpi", "gmv_kpi", "order_revenue", "order_count",
            "pcs_week", "pcs_period", "target_pcs", "target_progress_pct",
            "incentive_total", "incentive_eligible")}
        doc = {
            "id": str(uuid.uuid4()),
            "creator_id": row["creator_id"], "creator_name": row["creator_name"],
            "creator_code": row["creator_code"], "email": row["login_email"],
            "week_start": period["start"], "week_end": period["end"],
            "subject": subject, "body_text": body_text, "snapshot": snapshot,
            "top_contents": row["top_contents"],
            "sent_by": user.get("name") or user.get("email") or "system",
            "sent_at": _now(), "status": "sent", "error": None,
        }
        if not row["login_email"]:
            doc.update({"status": "no_email",
                        "error": "Kreator belum punya email portal — buat akun portalnya dulu."})
        elif not smtp_ready:
            doc.update({"status": "skipped_no_smtp",
                        "error": ("SMTP belum dikonfigurasi (Pusat Notifikasi → Konfigurasi "
                                  "Provider). Rapor tersimpan & bisa dibaca kreator di "
                                  "portalnya.")})
        else:
            res = await email_sender.send_email(cfg, to=row["login_email"],
                                                subject=subject, body_text=body_text)
            if not res.get("ok"):
                doc.update({"status": "failed", "error": res.get("error")})
        await db[RUNS].delete_many({"creator_id": row["creator_id"], "week_end": period["end"]})
        await db[RUNS].insert_one(dict(doc))
        doc.pop("_id", None)
        results.append({"creator_id": doc["creator_id"], "creator_name": doc["creator_name"],
                        "status": doc["status"], "error": doc["error"],
                        "sent_at": doc["sent_at"]})

    ok = sum(1 for r in results if r["status"] == "sent")
    await log_activity(user.get("id", "system"), user.get("name") or user.get("email", "system"),
                       "create", "marketing_creator_weekly_report",
                       f"Rapor mingguan {period['start']}..{period['end']}: {ok}/{len(results)} terkirim")
    return serialize_doc({
        "ok": True, "period": period, "smtp_configured": smtp_ready,
        "summary": {"total": len(results), "sent": ok,
                    "failed": sum(1 for r in results if r["status"] == "failed"),
                    "no_email": sum(1 for r in results if r["status"] == "no_email"),
                    "skipped_no_smtp": sum(1 for r in results if r["status"] == "skipped_no_smtp"),
                    "already_sent": sum(1 for r in results if r["status"] == "already_sent")},
        "results": results,
    })


@router.get("/weekly-report/runs")
async def weekly_report_runs(request: Request,
                             creator_id: str = Query(""),
                             limit: int = Query(100, ge=1, le=500)):
    user = await require_auth(request)
    db = get_db()
    allowed = await _scoped_creator_ids(db, user)
    q: dict = {}
    if creator_id:
        if allowed is not None and creator_id not in allowed:
            raise HTTPException(403, "Kreator ini tidak termasuk lingkup toko Anda.")
        q["creator_id"] = creator_id
    elif allowed is not None:
        q["creator_id"] = {"$in": allowed}
    rows = await db[RUNS].find(q, {"_id": 0, "body_text": 0}).sort(
        "sent_at", -1).to_list(limit)
    return serialize_doc({"ok": True, "rows": rows, "total": len(rows)})
