"""
PT Rahaza ERP — Alert Rule Engine (Phase 18A)

Monitors three production-floor conditions and publishes notifications via the
existing SSE infrastructure (`publish_notification` from rahaza_notifications):

  1. behind_target    — Line actual/target ratio < threshold (default 70%)
  2. qc_fail_spike    — QC fail rate > threshold in last N minutes (default 15%)
  3. low_stock        — Material total qty < min_stock * threshold (default 20%)

Settings are configurable via `rahaza_alert_settings` singleton (id='default').
A background task runs `evaluate_all_rules()` every `check_interval_seconds`.

Endpoints:
  GET  /api/rahaza/alerts/settings   — read thresholds
  PUT  /api/rahaza/alerts/settings   — update thresholds (admin only)
  POST /api/rahaza/alerts/evaluate   — manual trigger (admin); publishes + returns counts
  GET  /api/rahaza/alerts/preview    — returns what WOULD alert; no publish
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth
from datetime import datetime, timezone, timedelta, date
from typing import Optional
import asyncio
import logging

from routes.rahaza_notifications import publish_notification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza/alerts", tags=["Alerts"])


# ─── Settings defaults ───────────────────────────────────────────────────────
SETTINGS_ID = "default"

DEFAULT_SETTINGS = {
    "id": SETTINGS_ID,
    "enabled": True,
    "behind_target_pct": 0.70,           # fire if actual/target < 70%
    "qc_spike_pct": 0.15,                # fire if fail / (pass+fail) > 15%
    "qc_spike_window_min": 60,           # over last 60 minutes
    "qc_spike_min_events": 5,            # need ≥5 QC submits to avoid noise
    "low_stock_pct_of_min": 0.20,        # warn if total < 20% of min_stock
    "check_interval_seconds": 300,       # background loop every 5 min
    "alert_target_roles": ["superadmin", "manager_production", "supervisor"],
}


async def _get_settings(db) -> dict:
    doc = await db.rahaza_alert_settings.find_one({"id": SETTINGS_ID}, {"_id": 0})
    if not doc:
        # initialize
        doc = {**DEFAULT_SETTINGS}
        await db.rahaza_alert_settings.insert_one(doc)
        doc.pop("_id", None)
    # merge defaults for any missing key
    merged = {**DEFAULT_SETTINGS, **doc}
    return merged


async def _require_admin(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role not in ("admin", "superadmin", "owner", "manager_production"):
        raise HTTPException(403, "Butuh role Admin/Manager Produksi untuk mengubah setting alert")
    return user


# ─── Rule: behind-target ─────────────────────────────────────────────────────
async def check_behind_target(db, settings: dict) -> list:
    """Evaluate behind-target for today's active line assignments."""
    threshold = float(settings.get("behind_target_pct") or 0.70)
    today = date.today().isoformat()

    assignments = await db.rahaza_line_assignments.find(
        {"assign_date": today, "active": True, "target_qty": {"$gt": 0}},
        {"_id": 0},
    ).to_list(500)

    if not assignments:
        return []

    # Aggregate today's output per line
    # wip_events with event_type=output in last 24h
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    pipe = [
        {"$match": {"event_type": "output", "timestamp": {"$gte": since}}},
        {"$group": {"_id": "$line_id", "qty": {"$sum": "$qty"}}},
    ]
    actuals = {}
    async for r in db.rahaza_wip_events.aggregate(pipe):
        if r.get("_id"):
            actuals[r["_id"]] = int(r.get("qty") or 0)

    alerts = []
    # Batch: prefetch line codes for all unique line_ids in assignments
    line_ids_alerts = list({a.get("line_id") for a in assignments if a.get("line_id")})
    line_map_alerts = {}
    if line_ids_alerts:
        async for d in db.rahaza_lines.find({"id": {"$in": line_ids_alerts}}, {"_id": 0, "id": 1, "code": 1}):
            line_map_alerts[d["id"]] = d
    for a in assignments:
        line_id = a.get("line_id")
        target = int(a.get("target_qty") or 0)
        actual = actuals.get(line_id, 0)
        if target <= 0:
            continue
        ratio = actual / target
        if ratio < threshold:
            line = line_map_alerts.get(line_id) or {}
            line_code = line.get("code") or "?"
            pct = int(ratio * 100)
            alerts.append({
                "type": "behind_target",
                "severity": "warning" if ratio > threshold * 0.6 else "error",
                "title": f"Line {line_code} di bawah target ({pct}%)",
                "message": f"Output hari ini {actual} pcs dari target {target} pcs (ambang {int(threshold * 100)}%). Cek blocker di line.",
                "link_module": "prod-line-board",
                "link_id": line_id,
                "target_roles": settings.get("alert_target_roles") or DEFAULT_SETTINGS["alert_target_roles"],
                "dedup_key": f"behind_target:{line_id}:{today}",
            })
    return alerts


# ─── Rule: QC spike ──────────────────────────────────────────────────────────
async def check_qc_spike(db, settings: dict) -> list:
    """Evaluate QC fail spike in the last N minutes."""
    threshold = float(settings.get("qc_spike_pct") or 0.15)
    window_min = int(settings.get("qc_spike_window_min") or 60)
    min_events = int(settings.get("qc_spike_min_events") or 5)

    since_dt = datetime.now(timezone.utc) - timedelta(minutes=window_min)

    pipe = [
        {"$match": {
            "event_type": {"$in": ["qc_pass", "qc_fail"]},
            "timestamp": {"$gte": since_dt},
        }},
        {"$group": {
            "_id": "$line_id",
            "pass_qty": {"$sum": {"$cond": [{"$eq": ["$event_type", "qc_pass"]}, "$qty", 0]}},
            "fail_qty": {"$sum": {"$cond": [{"$eq": ["$event_type", "qc_fail"]}, "$qty", 0]}},
            "events": {"$sum": 1},
        }},
    ]

    alerts = []
    # Materialize aggregate results, then batch-prefetch line codes (eliminate N+1)
    qc_rows = []
    async for r in db.rahaza_wip_events.aggregate(pipe):
        qc_rows.append(r)
    line_ids_qc = list({r.get("_id") for r in qc_rows if r.get("_id")})
    line_map_qc = {}
    if line_ids_qc:
        async for d in db.rahaza_lines.find({"id": {"$in": line_ids_qc}}, {"_id": 0, "id": 1, "code": 1}):
            line_map_qc[d["id"]] = d
    for r in qc_rows:
        line_id = r.get("_id")
        if not line_id:
            continue
        pq = int(r.get("pass_qty") or 0)
        fq = int(r.get("fail_qty") or 0)
        ev = int(r.get("events") or 0)
        total = pq + fq
        if total == 0 or ev < min_events:
            continue
        fail_rate = fq / total
        if fail_rate > threshold:
            line = line_map_qc.get(line_id) or {}
            line_code = line.get("code") or "?"
            pct = int(fail_rate * 100)
            alerts.append({
                "type": "qc_fail_spike",
                "severity": "error",
                "title": f"QC fail spike di {line_code} ({pct}%)",
                "message": (
                    f"Fail rate {pct}% ({fq}/{total} pcs) dalam {window_min} menit terakhir "
                    f"— ambang {int(threshold * 100)}%. Cek kualitas bahan/alat."
                ),
                "link_module": "prod-rework-board",
                "link_id": line_id,
                "target_roles": settings.get("alert_target_roles") or DEFAULT_SETTINGS["alert_target_roles"],
                "dedup_key": f"qc_spike:{line_id}:{since_dt.strftime('%Y%m%d%H')}",  # hourly bucket
            })
    return alerts


# ─── Rule: low stock ─────────────────────────────────────────────────────────
async def check_low_stock(db, settings: dict) -> list:
    """Notifikasi stok rendah — memakai SATU definisi SSOT `core/stock_thresholds`.

    W3: dulu rule ini hanya melihat field legacy `min_stock` dan menjumlahkan
    `$qty` saja, sedangkan layar Master Item menulis `min_stock_qty` dan baris
    stok skema lama menyimpan angkanya di `total_qty`/`available_quantity`.
    Akibatnya ambang yang diisi pemilik tidak pernah membangunkan notifikasi ini.
    """
    from core import stock_thresholds as _th

    threshold = float(settings.get("low_stock_pct_of_min") or 0.20)
    rows = await _th.evaluate(db, with_suggestion=False)

    alerts = []
    for r in rows:
        if r["status"] not in ("low", "critical"):
            continue
        alert_at = r["alert_at"]
        critical_cutoff = round(alert_at * threshold, 2)
        if r["onhand"] < critical_cutoff or r["status"] == "critical":
            severity = "error"
            headline = f"Stok kritis: {r['code']}"
        else:
            severity = "warning"
            headline = f"Stok menipis: {r['code']}"

        alerts.append({
            "type": "low_stock",
            "severity": severity,
            "title": headline,
            "message": (
                f"Total stok {r['onhand']:.1f} {r['unit']} — ambang "
                f"{alert_at:.1f} (kritis {critical_cutoff:.1f}). Segera reorder."
            ),
            "link_module": "prod-materials",
            "link_id": r["material_id"],
            "target_roles": ["warehouse_manager", "manager_production", "superadmin"],
            "dedup_key": f"low_stock:{r['material_id']}:{severity}",
        })
    return alerts


# ─── Contract Expiry Check ───────────────────────────────────────────────────
async def check_expiring_contracts(db, settings: Optional[dict] = None) -> list:
    """
    Cek karyawan PKWT/Magang dengan kontrak mendekati berakhir.
    Kirim notifikasi pada H-30, H-14, H-7, H-1.
    """
    today = date.today()
    alerts = []

    emps = await db.rahaza_employees.find(
        {
            "active": True,
            "contract_end_date": {"$exists": True, "$nin": [None, ""]},
            "contract_type": {"$in": ["PKWT", "Magang"]},
        },
        {"_id": 0, "id": 1, "employee_code": 1, "name": 1, "contract_type": 1,
         "contract_end_date": 1, "department": 1}
    ).to_list(500)

    for emp in emps:
        end_str = emp.get("contract_end_date", "")
        if not end_str:
            continue
        try:
            end_dt = date.fromisoformat(str(end_str)[:10])
        except Exception:
            continue

        days_left = (end_dt - today).days

        # Determine alert threshold: fire when entering critical windows
        if days_left < 0:
            continue  # already expired

        if days_left <= 1:
            severity, label = "error", f"Kontrak berakhir {'HARI INI' if days_left == 0 else 'BESOK'}"
        elif days_left <= 7:
            severity, label = "error", f"Kontrak berakhir dalam {days_left} hari"
        elif days_left <= 14:
            severity, label = "warning", f"Kontrak berakhir dalam {days_left} hari"
        elif days_left <= 30:
            severity, label = "warning", f"Kontrak berakhir dalam {days_left} hari"
        else:
            continue  # too far ahead

        alerts.append({
            "type": "contract_expiry",
            "severity": severity,
            "title": f"{label}: {emp['name']} ({emp['employee_code']})",
            "message": (
                f"{emp.get('contract_type', 'PKWT')} {emp['name']} ({emp['employee_code']}) "
                f"berakhir pada {end_dt.strftime('%d %b %Y')}. "
                f"Sisa {days_left} hari."
                + (f" Divisi: {emp['department']}." if emp.get("department") else "")
            ),
            "link_module": "hr-employees",
            "link_id": emp["id"],
            "target_roles": ["superadmin", "hr", "admin", "manager"],
            "dedup_key": f"contract_expiry:{emp['id']}:{days_left}",
        })

    return alerts


# ─── Evaluate all rules ──────────────────────────────────────────────────────
async def evaluate_all_rules(db, settings: Optional[dict] = None, publish: bool = True) -> dict:
    """Run all rules and optionally publish notifications. Returns counts per rule."""
    if settings is None:
        settings = await _get_settings(db)

    counts = {"behind_target": 0, "qc_fail_spike": 0, "low_stock": 0, "contract_expiry": 0, "published": 0}
    preview = []

    rule_funcs = [
        ("behind_target", check_behind_target),
        ("qc_fail_spike", check_qc_spike),
        ("low_stock", check_low_stock),
        ("contract_expiry", check_expiring_contracts),
    ]
    for key, fn in rule_funcs:
        try:
            emits = await fn(db, settings)
            counts[key] = len(emits)
            for e in emits:
                preview.append(e)
                if publish:
                    res = await publish_notification(
                        db,
                        type_=e["type"],
                        severity=e["severity"],
                        title=e["title"],
                        message=e["message"],
                        link_module=e.get("link_module"),
                        link_id=e.get("link_id"),
                        target_roles=e.get("target_roles"),
                        dedup_key=e.get("dedup_key"),
                    )
                    if res:
                        counts["published"] += 1
        except Exception as ex:
            logger.exception(f"[alerts] rule {key} failed: {ex}")

    return {"counts": counts, "preview": preview}


# ─── Background task ─────────────────────────────────────────────────────────
_bg_task: Optional[asyncio.Task] = None


async def _background_loop():
    """Periodic evaluator — runs forever until app shutdown."""
    logger.info("[alerts] background rule evaluator started")
    # small startup delay so app finishes booting and indexes complete
    await asyncio.sleep(10)
    while True:
        try:
            db = get_db()
            settings = await _get_settings(db)
            if settings.get("enabled", True):
                res = await evaluate_all_rules(db, settings=settings, publish=True)
                if res["counts"]["published"] > 0:
                    logger.info(f"[alerts] cycle published {res['counts']['published']} notifications: {res['counts']}")
            # FASE 4 (E10 DELETE): Andon SLA escalation dihapus (engine andon diarsip).
            interval = int(settings.get("check_interval_seconds") or 300)
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            logger.exception(f"[alerts] background cycle error: {ex}")
            interval = 300
        await asyncio.sleep(max(30, interval))


def start_background_task():
    """Called from server.py startup — idempotent."""
    global _bg_task
    if _bg_task and not _bg_task.done():
        return _bg_task
    _bg_task = asyncio.create_task(_background_loop())
    return _bg_task


def stop_background_task():
    global _bg_task
    if _bg_task and not _bg_task.done():
        _bg_task.cancel()


# ─── Endpoints ───────────────────────────────────────────────────────────────
@router.get("/settings")
async def get_alert_settings(request: Request):
    await require_auth(request)
    db = get_db()
    settings = await _get_settings(db)
    return settings


@router.put("/settings")
async def update_alert_settings(request: Request):
    user = await _require_admin(request)
    db = get_db()
    try:
        body = await request.json()
    except Exception:
        body = {}
    body.pop("_id", None)
    body["id"] = SETTINGS_ID

    # Clamp + type-coerce
    def _float(k, default, lo=0.0, hi=1.0):
        try:
            v = float(body.get(k, default))
            return max(lo, min(hi, v))
        except Exception:
            return default

    def _int(k, default, lo=1, hi=100000):
        try:
            v = int(body.get(k, default))
            return max(lo, min(hi, v))
        except Exception:
            return default

    cur = await _get_settings(db)
    doc = {
        "id": SETTINGS_ID,
        "enabled": bool(body.get("enabled", cur.get("enabled", True))),
        "behind_target_pct": _float("behind_target_pct", cur["behind_target_pct"], 0.05, 1.0),
        "qc_spike_pct": _float("qc_spike_pct", cur["qc_spike_pct"], 0.01, 1.0),
        "qc_spike_window_min": _int("qc_spike_window_min", cur["qc_spike_window_min"], 5, 24 * 60),
        "qc_spike_min_events": _int("qc_spike_min_events", cur["qc_spike_min_events"], 1, 1000),
        "low_stock_pct_of_min": _float("low_stock_pct_of_min", cur["low_stock_pct_of_min"], 0.01, 1.0),
        "check_interval_seconds": _int("check_interval_seconds", cur["check_interval_seconds"], 30, 24 * 3600),
        "alert_target_roles": body.get("alert_target_roles") or cur.get("alert_target_roles") or DEFAULT_SETTINGS["alert_target_roles"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user.get("name") or user.get("email"),
    }
    await db.rahaza_alert_settings.update_one(
        {"id": SETTINGS_ID},
        {"$set": doc},
        upsert=True,
    )
    return doc


@router.post("/evaluate")
async def manual_evaluate(request: Request):
    """Admin trigger: evaluate all rules + publish notifications right now."""
    await _require_admin(request)
    db = get_db()
    settings = await _get_settings(db)
    res = await evaluate_all_rules(db, settings=settings, publish=True)
    return {"ok": True, **res}


@router.get("/preview")
async def preview_alerts(request: Request):
    """Return what WOULD be alerted without publishing (handy for settings UI)."""
    await require_auth(request)
    db = get_db()
    settings = await _get_settings(db)
    res = await evaluate_all_rules(db, settings=settings, publish=False)
    return {"ok": True, **res}
