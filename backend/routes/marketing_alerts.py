"""
Marketing Alert Engine — Phase 3 Week 11

Rule-based alert evaluation for Portal Marketing:
  1. expiring_discount   — kampanye diskon berakhir ≤ 3 hari
  2. sla_breach          — komplain overdue / at_risk
  3. upcoming_launch     — produk launch H-1 / H-3 / H-7
  4. content_today       — konten scheduled hari ini yang belum posted

Publishes to existing SSE notification system (rahaza_notifications.publish_notification).
Background job registered in utils/scheduler.py.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/alerts", tags=["marketing-alerts"])

SETTINGS_ID = "marketing_alert_settings_singleton"

DEFAULT_SETTINGS = {
    "id": SETTINGS_ID,
    "enabled": True,
    "discount_expiry_days": 3,
    "launch_warning_days": [7, 3, 1],
    "target_roles": ["superadmin", "admin"],
    "check_interval_minutes": 30,
    "alert_content_today": True,
    "alert_sla_breach": True,
    "alert_expiring_discount": True,
    "alert_upcoming_launch": True,
    # F5.4 — peringatan siklus (target tertinggal / anggaran terlampaui).
    # Ambangnya ditaruh di sini supaya owner bisa mengubahnya dari layar
    # Pengaturan Alert; rumusnya tetap satu di core/marketing_cycle.
    "alert_cycle": True,
    "target_behind_pct": 15.0,
    "target_behind_red_pct": 30.0,
    "budget_warn_ratio": 0.8,
    "budget_over_ratio": 1.0,
    "updated_at": None,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)

def _today() -> date:
    return datetime.now(timezone.utc).date()

def serialize(obj):
    if isinstance(obj, list):
        return [serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items() if k != "_id"}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


async def get_settings(db) -> dict:
    doc = await db.marketing_alert_settings.find_one({"id": SETTINGS_ID}, {"_id": 0})
    if not doc:
        doc = dict(DEFAULT_SETTINGS)
        await db.marketing_alert_settings.insert_one(doc)
    return {**DEFAULT_SETTINGS, **doc}


# ──────────────────────────────────────────────────────────────────
# CORE EVALUATOR
# ──────────────────────────────────────────────────────────────────
async def evaluate_marketing_alerts(db=None, settings_override: dict = None, dry_run: bool = False) -> dict:
    """
    Core evaluation function — called by scheduler job AND manual trigger endpoint.
    Returns summary dict of alerts fired.
    """
    if db is None:
        db = get_db()

    settings = settings_override or await get_settings(db)
    if not settings.get("enabled"):
        return {"skipped": True, "reason": "Alert engine disabled in settings"}

    try:
        from routes.rahaza_notifications import publish_notification
    except ImportError:
        logger.warning("[marketing_alerts] rahaza_notifications not available; using fallback")
        publish_notification = None

    target_roles = settings.get("target_roles", ["superadmin"])
    today = _today()
    today_str = today.isoformat()
    fired = []

    # ── 1. EXPIRING DISCOUNTS ────────────────────────────────
    if settings.get("alert_expiring_discount"):
        try:
            threshold = settings.get("discount_expiry_days", 3)
            threshold_date = (today + timedelta(days=threshold)).isoformat()
            # Discounts that end between today and threshold_date
            docs = await db.marketing_discounts.find(
                {"end_date": {"$gte": today_str, "$lte": threshold_date}},
                {"_id": 0, "id": 1, "name": 1, "end_date": 1, "account_name": 1, "platform": 1}
            ).to_list(100)

            for d in docs:
                days_left = (datetime.fromisoformat(d["end_date"]).date() - today).days
                title = f"🔔 Kampanye Diskon Habis {days_left} Hari Lagi"
                msg   = f"{d['name']} ({d.get('account_name','')}/{d.get('platform','')}) berakhir {d['end_date']}. Perbarui atau buat kampanye baru!"
                dedup = f"discount_expiry_{d['id']}_{today_str}"

                event_doc = {
                    "id": str(uuid.uuid4()),
                    "type": "expiring_discount",
                    "severity": "warning" if days_left <= 1 else "info",
                    "title": title, "message": msg,
                    "link_module": "marketing-discounts", "link_id": d["id"],
                    "dedup_key": dedup, "target_roles": target_roles,
                    "created_at": _now(), "dry_run": dry_run,
                }
                fired.append(event_doc)
                if not dry_run and publish_notification:
                    await publish_notification(
                        db, type_="expiring_discount",
                        severity="warning" if days_left <= 1 else "info",
                        title=title, message=msg,
                        link_module="marketing-discounts", link_id=d["id"],
                        target_roles=target_roles, dedup_key=dedup
                    )
        except Exception as e:
            logger.warning(f"[marketing_alerts] discount scan error: {e}")

    # ── 2. SLA BREACH (overdue complaints) ───────────────────
    if settings.get("alert_sla_breach"):
        try:
            overdue = await db.marketing_complaints.count_documents({"sla_status": "overdue"})
            at_risk  = await db.marketing_complaints.count_documents({"sla_status": "at_risk"})
            if overdue > 0 or at_risk > 0:
                title = f"⚠️ {overdue} Komplain Overdue, {at_risk} At Risk"
                msg   = f"SLA breach: {overdue} komplain sudah melewati batas waktu, {at_risk} akan segera melewati batas. Segera ditangani!"
                dedup = f"sla_breach_{today_str}"
                event_doc = {
                    "id": str(uuid.uuid4()),
                    "type": "sla_breach",
                    "severity": "error" if overdue > 0 else "warning",
                    "title": title, "message": msg,
                    "link_module": "marketing-complaints",
                    "dedup_key": dedup, "target_roles": target_roles,
                    "created_at": _now(), "dry_run": dry_run,
                }
                fired.append(event_doc)
                if not dry_run and publish_notification:
                    await publish_notification(
                        db, type_="sla_breach",
                        severity="error" if overdue > 0 else "warning",
                        title=title, message=msg,
                        link_module="marketing-complaints",
                        target_roles=target_roles, dedup_key=dedup
                    )
        except Exception as e:
            logger.warning(f"[marketing_alerts] sla scan error: {e}")

    # ── 3. UPCOMING PRODUCT LAUNCHES ──────────────────────
    if settings.get("alert_upcoming_launch"):
        try:
            warning_days = settings.get("launch_warning_days", [7, 3, 1])
            launches = await db.marketing_product_launches.find(
                {"status": {"$in": ["planning", "ready"]}},
                {"_id": 0, "id": 1, "product_name": 1, "launch_date": 1, "status": 1}
            ).to_list(200)

            for lch in launches:
                try:
                    ld = date.fromisoformat(lch["launch_date"][:10])
                    days_left = (ld - today).days
                    if days_left in warning_days:
                        urgency = "❗" if days_left == 1 else "📌"
                        title = f"{urgency} Launch H-{days_left}: {lch['product_name'][:40]}"
                        msg   = f"Produk '{lch['product_name']}' dijadwalkan launch tanggal {lch['launch_date']} (H-{days_left}). Pastikan semua persiapan sudah selesai!"
                        dedup = f"launch_h{days_left}_{lch['id']}_{today_str}"
                        event_doc = {
                            "id": str(uuid.uuid4()),
                            "type": "upcoming_launch",
                            "severity": "error" if days_left == 1 else ("warning" if days_left <= 3 else "info"),
                            "title": title, "message": msg,
                            "link_module": "marketing-product-launches", "link_id": lch["id"],
                            "dedup_key": dedup, "target_roles": target_roles,
                            "created_at": _now(), "dry_run": dry_run,
                        }
                        fired.append(event_doc)
                        if not dry_run and publish_notification:
                            await publish_notification(
                                db, type_="upcoming_launch",
                                severity="error" if days_left == 1 else ("warning" if days_left <= 3 else "info"),
                                title=title, message=msg,
                                link_module="marketing-product-launches", link_id=lch["id"],
                                target_roles=target_roles, dedup_key=dedup
                            )
                except Exception:
                    logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        except Exception as e:
            logger.warning(f"[marketing_alerts] launch scan error: {e}")

    # ── 4. CONTENT SCHEDULED TODAY NOT YET POSTED ─────────
    if settings.get("alert_content_today"):
        try:
            pending_today = await db.marketing_content_calendar.count_documents({
                "date": today_str, "status": "scheduled"
            })
            if pending_today > 0:
                title = f"📌 {pending_today} Konten Terjadwal Hari Ini"
                msg   = f"{pending_today} konten dijadwalkan posting hari ini ({today_str}) namun belum berstatus 'posted'. Cek Content Calendar!"
                dedup = f"content_today_{today_str}"
                event_doc = {
                    "id": str(uuid.uuid4()),
                    "type": "content_today",
                    "severity": "info",
                    "title": title, "message": msg,
                    "link_module": "marketing-content-calendar",
                    "dedup_key": dedup, "target_roles": target_roles,
                    "created_at": _now(), "dry_run": dry_run,
                }
                fired.append(event_doc)
                if not dry_run and publish_notification:
                    await publish_notification(
                        db, type_="content_today",
                        severity="info",
                        title=title, message=msg,
                        link_module="marketing-content-calendar",
                        target_roles=target_roles, dedup_key=dedup
                    )
        except Exception as e:
            logger.warning(f"[marketing_alerts] content today scan error: {e}")

    # ── 5. F5.4 — SIKLUS: TARGET TERTINGGAL & ANGGARAN TERLAMPAUI ────────────
    # Kenapa lewat `core/marketing_cycle.evaluate_flags` dan bukan rumus baru di
    # sini: layar Siklus memakai fungsi yang SAMA. Kalau notifikasi menilai
    # sendiri, isi lonceng dan isi layar bisa berbeda untuk toko yang sama pada
    # hari yang sama — dan staf akan belajar mengabaikan lonceng.
    if settings.get("alert_cycle", True):
        try:
            from core import marketing_cycle as _cycle
            period = _cycle.today_wib().strftime("%Y-%m")
            accounts = await db.marketing_platform_accounts.find(
                {"status": "active"}, {"_id": 0}).to_list(300)
            for acc in accounts:
                try:
                    summary = await _cycle.cycle_summary(db, acc, period, settings=settings)
                except Exception as exc:
                    logger.warning("[marketing_alerts] cycle summary gagal account=%s "
                                   "period=%s: %s", acc.get("id"), period, exc)
                    continue
                for fl in (summary.get("flags") or []):
                    if fl.get("code") not in ("target_behind", "budget_overrun",
                                              "budget_warning"):
                        continue
                    sev = {"red": "error", "yellow": "warning"}.get(fl.get("severity"), "info")
                    icon = "🎯" if fl["code"] == "target_behind" else "💸"
                    title = f"{icon} {acc.get('account_name', '')} — {fl.get('title')}"
                    msg = f"{fl.get('message')} (periode {period})"
                    dedup = f"{fl['code']}_{acc.get('id')}_{period}_{today_str}"
                    event_doc = {
                        "id": str(uuid.uuid4()),
                        "type": fl["code"], "severity": sev,
                        "title": title, "message": msg,
                        "link_module": "marketing-targets", "link_id": acc.get("id"),
                        "dedup_key": dedup, "target_roles": target_roles,
                        "created_at": _now(), "dry_run": dry_run,
                    }
                    fired.append(event_doc)
                    if not dry_run and publish_notification:
                        await publish_notification(
                            db, type_=fl["code"], severity=sev, title=title, message=msg,
                            link_module="marketing-targets", link_id=acc.get("id"),
                            target_roles=target_roles, dedup_key=dedup)
        except Exception as e:
            logger.warning(f"[marketing_alerts] cycle scan error: {e}")

    # Log run
    if not dry_run:
        try:
            await db.marketing_alert_runs.insert_one({
                "id": str(uuid.uuid4()),
                "fired_count": len(fired),
                "types": list(set(e["type"] for e in fired)),
                "ran_at": _now(),
                "dry_run": False,
            })
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    logger.info(f"[marketing_alerts] evaluated: {len(fired)} alerts fired (dry={dry_run})")
    return {
        "success": True,
        "fired": serialize(fired),
        "total_fired": len(fired),
        "evaluated_at": _now().isoformat(),
        "dry_run": dry_run,
    }


# ──────────────────────────────────────────────────────────────────
# API ENDPOINTS
# ──────────────────────────────────────────────────────────────────

@router.get("/settings")
async def read_settings(request: Request):
    await require_auth(request)
    db = get_db()
    s = await get_settings(db)
    return {"success": True, "data": serialize(s)}


class AlertSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    discount_expiry_days: Optional[int] = Field(default=None, ge=0)
    launch_warning_days: Optional[list] = None
    target_roles: Optional[list] = None
    check_interval_minutes: Optional[int] = None
    alert_content_today: Optional[bool] = None
    alert_sla_breach: Optional[bool] = None
    alert_expiring_discount: Optional[bool] = None
    alert_upcoming_launch: Optional[bool] = None
    # F5.4 — ambang peringatan siklus
    alert_cycle: Optional[bool] = None
    target_behind_pct: Optional[float] = Field(default=None, ge=0, le=100)
    target_behind_red_pct: Optional[float] = Field(default=None, ge=0, le=100)
    budget_warn_ratio: Optional[float] = Field(default=None, ge=0, le=10)
    budget_over_ratio: Optional[float] = Field(default=None, ge=0, le=10)


@router.put("/settings")
async def update_settings(body: AlertSettingsIn, request: Request):
    await require_auth(request)
    db = get_db()
    upd = {k: v for k, v in body.dict().items() if v is not None}
    upd["updated_at"] = _now()
    await db.marketing_alert_settings.update_one(
        {"id": SETTINGS_ID}, {"$set": upd}, upsert=True
    )
    s = await get_settings(db)
    return {"success": True, "data": serialize(s)}


@router.post("/evaluate")
async def manual_evaluate(request: Request):
    """Manual trigger — evaluates NOW and publishes notifications."""
    await require_auth(request)
    db = get_db()
    result = await evaluate_marketing_alerts(db=db)
    return result


@router.post("/preview")
async def preview_alerts(request: Request):
    """Dry run — returns what WOULD alert without publishing."""
    await require_auth(request)
    db = get_db()
    result = await evaluate_marketing_alerts(db=db, dry_run=True)
    return result


@router.get("/history")
async def get_history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100)
):
    await require_auth(request)
    db = get_db()
    runs = await db.marketing_alert_runs.find({}, {"_id": 0}).sort("ran_at", -1).limit(limit).to_list(limit)
    return {"success": True, "data": serialize(runs)}
