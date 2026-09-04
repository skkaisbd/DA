"""
services/rnd_decision_report.py — Rapor keputusan RnD mingguan.

PERMINTAAN OWNER (2026-08-07)
----------------------------
"Kirim ringkasan mingguan berisi style yang disetujui, ditolak, dan yang masih
menunggu terlalu lama." Pilihan owner: dikirim **setiap Senin 08:00 WIB**, lewat
**notifikasi dalam aplikasi** (email menyusul bila SMTP diisi — belum dipakai).

ATURAN
------
* Sumber data = koleksi RnD nyata: `dewi_rnd_styles` (keputusan owner),
  `dewi_rnd_sample_requests` (keputusan sample). Tidak ada tabel rapor terpisah.
* Ambang "menunggu terlalu lama" = `rnd_stale_days` di `dewi_mgmt_alert_config`
  (bawaan 7 hari) — satu tempat dengan ambang peringatan PO/AR.
* Penulis notifikasi SATU pintu: `utils/notif_unified.notif_insert`.
* **Idempoten per pekan ISO**: dijalankan ulang di pekan yang sama tidak
  membuat notifikasi ganda (kecuali dipaksa lewat tombol "Kirim sekarang").
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from services.management_alerts import _management_user_ids, get_alert_config, MANAGEMENT_ROLES
from utils.notif_unified import notif_insert

logger = logging.getLogger(__name__)

SUBTYPE = "rnd_weekly_decisions"
LINK_MODULE = "rnd-dashboard"


def _dt(v):
    """Tanggal apa pun (datetime / ISO string) → datetime UTC atau None."""
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _age_days(v, now: datetime) -> int:
    d = _dt(v)
    return max(0, (now - d).days) if d else 0


async def build_rnd_decision_report(db, *, days: int = 7, stale_days: int = None) -> dict:
    """Susun rapor: keputusan dalam N hari terakhir + antrean yang menunggu terlalu lama."""
    cfg = await get_alert_config(db)
    stale = int(stale_days) if stale_days is not None else int(cfg["rnd_stale_days"])
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=int(days))

    decided = await db.dewi_rnd_styles.find(
        {"owner_review_result": {"$in": ["approved", "rejected"]}}, {"_id": 0}).to_list(2000)
    approved, rejected = [], []
    for s in decided:
        at = _dt(s.get("owner_reviewed_at"))
        if not at or at < since:
            continue
        row = {
            "id": s.get("id"), "style_code": s.get("style_code") or "-",
            "style_name": s.get("style_name") or "-",
            "decided_by": s.get("owner_reviewed_by") or "-",
            "decided_at": at.isoformat(),
            "notes": s.get("owner_review_notes") or "",
            "status_now": s.get("status"),
            "promoted": bool(s.get("promoted_to_model_id")),
        }
        (approved if s["owner_review_result"] == "approved" else rejected).append(row)
    approved.sort(key=lambda r: r["decided_at"], reverse=True)
    rejected.sort(key=lambda r: r["decided_at"], reverse=True)

    waiting = await db.dewi_rnd_styles.find(
        {"status": "pending_owner_review"}, {"_id": 0}).to_list(1000)
    pending, stale_rows = [], []
    for s in waiting:
        age = _age_days(s.get("submitted_for_review_at") or s.get("updated_at")
                        or s.get("created_at"), now)
        row = {
            "id": s.get("id"), "style_code": s.get("style_code") or "-",
            "style_name": s.get("style_name") or "-",
            "requested_by": s.get("submitted_for_review_by") or s.get("created_by_name") or "-",
            "age_days": age,
        }
        pending.append(row)
        if age >= stale:
            stale_rows.append(row)
    pending.sort(key=lambda r: -r["age_days"])
    stale_rows.sort(key=lambda r: -r["age_days"])

    samples = await db.dewi_rnd_sample_requests.find(
        {"status": {"$in": ["approved", "rejected"]}}, {"_id": 0}).to_list(2000)
    sample_decided = [{
        "id": x.get("id"), "code": x.get("sample_code") or "-",
        "style_code": x.get("style_code") or "-", "result": x.get("status"),
        "decided_by": x.get("approved_by_name") or "-",
        "decided_at": (_dt(x.get("approved_at")) or now).isoformat(),
        "pic": x.get("sample_pic") or "",
    } for x in samples if (_dt(x.get("approved_at")) or since) >= since]
    sample_decided.sort(key=lambda r: r["decided_at"], reverse=True)

    iso = now.isocalendar()
    return {
        "generated_at": now.isoformat(),
        "period_from": since.date().isoformat(),
        "period_to": now.date().isoformat(),
        "days": int(days),
        "stale_days": stale,
        "week_key": f"{iso[0]}-W{iso[1]:02d}",
        "approved": approved, "rejected": rejected,
        "pending": pending, "stale": stale_rows,
        "sample_decisions": sample_decided,
        "counts": {
            "approved": len(approved), "rejected": len(rejected),
            "pending": len(pending), "stale": len(stale_rows),
            "sample_decisions": len(sample_decided),
        },
        "sources": [
            {"collection": "dewi_rnd_styles", "count": len(decided) + len(waiting),
             "note": "keputusan & antrean style"},
            {"collection": "dewi_rnd_sample_requests", "count": len(samples),
             "note": "keputusan sample"},
        ],
    }


def _report_text(rep: dict) -> str:
    c = rep["counts"]
    lines = [
        f"Periode {rep['period_from']} s/d {rep['period_to']}:",
        f"· {c['approved']} style disetujui, {c['rejected']} ditolak"
        + (f", {c['sample_decisions']} keputusan sample" if c["sample_decisions"] else ""),
        f"· {c['pending']} style masih menunggu keputusan"
        + (f" — {c['stale']} di antaranya sudah lebih dari {rep['stale_days']} hari"
           if c["stale"] else ""),
    ]
    for r in rep["stale"][:5]:
        lines.append(f"  ⚠ {r['style_code']} ({r['style_name']}) — {r['age_days']} hari, "
                     f"diajukan {r['requested_by']}")
    for r in rep["approved"][:3]:
        lines.append(f"  ✓ {r['style_code']} disetujui {r['decided_by']}")
    for r in rep["rejected"][:3]:
        lines.append(f"  ✗ {r['style_code']} ditolak {r['decided_by']}"
                     + (f" — {r['notes'][:70]}" if r["notes"] else ""))
    return "\n".join(lines)


async def send_rnd_decision_report(db, *, days: int = 7, stale_days: int = None,
                                   force: bool = False) -> dict:
    """Kirim rapor sebagai notifikasi in-app ke manajemen. Idempoten per pekan ISO."""
    rep = await build_rnd_decision_report(db, days=days, stale_days=stale_days)
    source_ref = f"rnd-weekly-{rep['week_key']}"
    existing = await db.notifications.find_one(
        {"type": "rahaza", "subtype": SUBTYPE, "source_ref": source_ref}, {"_id": 0, "id": 1})
    if existing and not force:
        return {**rep, "sent": 0, "skipped": "sudah dikirim pekan ini",
                "recipients": 0, "week_key": rep["week_key"]}

    user_ids = await _management_user_ids(db)
    c = rep["counts"]
    title = (f"Rapor keputusan RnD {rep['week_key']}: {c['approved']} disetujui · "
             f"{c['rejected']} ditolak · {c['stale']} tertunda lama")
    body = _report_text(rep)
    severity = "warning" if c["stale"] else "info"
    sent = 0
    for uid in (user_ids or [None]):
        await notif_insert(
            db, type="rahaza", subtype=SUBTYPE, title=title, body=body,
            severity=severity, user_id=uid, channel="in_app",
            target_roles=None if uid else list(MANAGEMENT_ROLES),
            source_type="rnd_weekly_report", source_ref=source_ref,
            source_url=f"#{LINK_MODULE}",
            meta={"link_module": LINK_MODULE, "week_key": rep["week_key"], **c},
            status="sent", sent_at=datetime.now(timezone.utc),
        )
        sent += 1
    logger.info("[rnd-weekly] %s → %s notifikasi (disetujui=%s ditolak=%s tertunda=%s)",
                rep["week_key"], sent, c["approved"], c["rejected"], c["stale"])
    return {**rep, "sent": sent, "skipped": None, "recipients": len(user_ids),
            "resent": bool(existing)}


async def job_weekly_rnd_decision_report():
    """Entry point scheduler mingguan (Senin 08:00 WIB)."""
    from database import get_db
    db = get_db()
    started = datetime.now(timezone.utc)
    run = {"job_id": "weekly_rnd_decision_report", "started_at": started, "status": "running"}
    res = await db.dewi_scheduler_runs.insert_one(run)
    try:
        out = await send_rnd_decision_report(db)
        await db.dewi_scheduler_runs.update_one(
            {"_id": res.inserted_id},
            {"$set": {"status": "success", "finished_at": datetime.now(timezone.utc),
                      "result": {"week_key": out["week_key"], "sent": out["sent"],
                                 "skipped": out["skipped"], **out["counts"]}}})
        return out
    except Exception as e:  # noqa: BLE001
        logger.exception("[rnd-weekly] gagal")
        await db.dewi_scheduler_runs.update_one(
            {"_id": res.inserted_id},
            {"$set": {"status": "failed", "finished_at": datetime.now(timezone.utc),
                      "error": str(e)}})
        raise
