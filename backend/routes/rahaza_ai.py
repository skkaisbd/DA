"""PT Rahaza — Phase 20C: AI Layer — Phase 0 OPTIMIZED.

Endpoints (prefix /api/rahaza):
  GET  /ai/daily-summary?date=         — ringkasan harian (LLM, app-cache)
  POST /ai/chat                         — chatbot supervisor (multi-turn)
  POST /ai/root-cause                   — root-cause assistant
  POST /ai/smart-search                 — pencarian natural language (DB-level)
  GET  /ai/predictive-delay?wo_id=      — prediksi delay WO
  GET  /ai/history?session_id=          — riwayat chat session

Optimisations vs previous version:
* All LLM calls go through unified `services.ai` client (Claude).
* `_build_daily_context` rewritten with $group aggregation — no more 500×6 doc fetches.
* `smart-search` rewritten to use MongoDB $regex at DB level.
* `predictive-delay` uses aggregation pipeline for daily output average.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from auth import require_auth
from utils.data_quality import SkipTracker
from database import get_db
from services.ai import SystemPrompts, call_claude, cached_call_claude
from services.ai_aggregates import rahaza_aggregates as rh_agg

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza", tags=["rahaza-ai"])


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _build_daily_context(db, target_date: date) -> dict:
    """Aggregate daily KPIs for AI prompts (DB-level, no full-collection fetch)."""
    d_start = target_date.isoformat()
    d_end = d_start + "T23:59:59Z"

    total_output = await rh_agg.daily_wip_output(db, d_start=d_start, d_end=d_end)
    qc = await rh_agg.daily_qc_summary(db, d_start=d_start, d_end=d_end)
    total_target = await rh_agg.daily_target_qty(db, assign_date=d_start)
    total_downtime = await rh_agg.daily_downtime(db, d_start=d_start, d_end=d_end)
    alerts = await rh_agg.active_alerts(db, limit=5)
    wo = await rh_agg.wo_backlog(db)

    fail_rate = round(qc["fail"] / max(qc["checked"], 1) * 100, 1)
    return {
        "tanggal": target_date.strftime("%d %B %Y"),
        "total_output_pcs": total_output,
        "target_output_pcs": total_target,
        "efisiensi_pct": round(total_output / max(total_target, 1) * 100, 1),
        "total_qc_checked": qc["checked"],
        "total_qc_fail": qc["fail"],
        "fail_rate_pct": fail_rate,
        "downtime_menit": total_downtime,
        "alert_aktif": len(alerts),
        "alert_sample": [a.get("message", "") for a in alerts[:3]],
        "wo_aktif": wo["active"],
        "wo_overdue": wo["overdue"],
    }


def _format_daily_user_prompt(ctx: dict) -> str:
    sample = (": " + ", ".join(ctx["alert_sample"])) if ctx["alert_sample"] else ""
    return (
        f"Kamu adalah asisten ERP pabrik rajut PT Rahaza. Buat RINGKASAN HARIAN produksi "
        f"yang padat dan informatif dalam Bahasa Indonesia.\n\n"
        f"DATA HARI INI ({ctx['tanggal']}):\n"
        f"- Output: {ctx['total_output_pcs']} pcs (target {ctx['target_output_pcs']} pcs, "
        f"efisiensi {ctx['efisiensi_pct']}%)\n"
        f"- QC: diperiksa {ctx['total_qc_checked']} pcs, gagal {ctx['total_qc_fail']} pcs "
        f"(fail rate {ctx['fail_rate_pct']}%)\n"
        f"- Downtime mesin: {ctx['downtime_menit']} menit\n"
        f"- Alert aktif: {ctx['alert_aktif']} item{sample}\n"
        f"- WO aktif: {ctx['wo_aktif']}, WO overdue: {ctx['wo_overdue']}\n\n"
        "Buat ringkasan 3-4 kalimat yang:\n"
        "1. Menyebutkan performa output vs target\n"
        "2. Menyoroti masalah QC atau downtime jika ada\n"
        "3. Memberikan 1 rekomendasi tindakan utama\n"
        "Jangan gunakan bullet points, cukup paragraf singkat."
    )


def _fallback_summary(ctx: dict) -> str:
    eff = ctx["efisiensi_pct"]
    text = (
        f"Produksi hari ini mencapai {ctx['total_output_pcs']} pcs dari target "
        f"{ctx['target_output_pcs']} pcs (efisiensi {eff}%). "
    )
    if ctx["fail_rate_pct"] > 10:
        text += f"QC fail rate {ctx['fail_rate_pct']}% perlu perhatian. "
    if ctx["downtime_menit"] > 30:
        text += f"Downtime mesin {ctx['downtime_menit']} menit tercatat hari ini. "
    if ctx["wo_overdue"] > 0:
        text += f"Terdapat {ctx['wo_overdue']} WO overdue yang perlu segera ditindaklanjuti."
    return text


@router.get("/ai/daily-summary")
async def daily_summary(
    request: Request,
    target_date: Optional[str] = Query(None, alias="date"),
):
    user = await require_auth(request)
    db = get_db()

    d = date.fromisoformat(target_date) if target_date else date.today()
    ctx = await _build_daily_context(db, d)
    user_prompt = _format_daily_user_prompt(ctx)

    try:
        cached = await cached_call_claude(
            db,
            system_message=SystemPrompts.RAHAZA_DAILY_SUMMARY,
            user_message=user_prompt,
            cache_namespace="rahaza_daily_summary",
            cache_key_extra=[d.isoformat()],
            ttl_seconds=1800,  # 30m — production data evolves fast
            session_tag=f"rahaza-daily-{d.isoformat()}",
        )
        summary_text = cached["text"]
        cache_hit = cached.get("cache_hit", False)
    except Exception as e:
        logger.error("AI daily summary error: %s", e)
        summary_text = _fallback_summary(ctx)
        cache_hit = False

    await db.rahaza_ai_audit_logs.insert_one({
        "id": _uid(),
        "user_id": user["id"],
        "feature": "daily_summary",
        "date": d.isoformat(),
        "created_at": _now().isoformat(),
        "cache_hit": cache_hit,
    })

    return {
        "ok": True,
        "date": d.isoformat(),
        "context": ctx,
        "summary": summary_text,
        "generated_at": _now().isoformat(),
        "cache_hit": cache_hit,
    }


@router.post("/ai/chat")
async def ai_chat(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    message = (body.get("message") or "").strip()
    session_id = body.get("session_id") or f"chat-{user['id'][:8]}-{date.today().isoformat()}"
    if not message:
        raise HTTPException(400, "message wajib diisi.")

    ctx = await _build_daily_context(db, date.today())
    system_msg = (
        f"{SystemPrompts.RAHAZA_CHAT}\n\n"
        "KONTEKS HARI INI:\n"
        f"- Output hari ini: {ctx['total_output_pcs']} pcs (target {ctx['target_output_pcs']} pcs)\n"
        f"- QC fail rate: {ctx['fail_rate_pct']}%\n"
        f"- Downtime: {ctx['downtime_menit']} menit\n"
        f"- Alert aktif: {ctx['alert_aktif']}\n"
        f"- WO aktif: {ctx['wo_aktif']}, overdue: {ctx['wo_overdue']}"
    )

    try:
        reply = await call_claude(
            system_message=system_msg,
            user_message=message,
            session_tag=session_id,
            db=db,
        )
    except Exception as e:
        logger.error("AI chat error: %s", e)
        reply = "Maaf, AI assistant sedang tidak tersedia. Silakan coba lagi nanti."

    now_iso = _now().isoformat()
    await db.rahaza_ai_chat_history.insert_many([
        {"id": _uid(), "session_id": session_id, "user_id": user["id"],
         "role": "user", "content": message, "created_at": now_iso},
        {"id": _uid(), "session_id": session_id, "user_id": user["id"],
         "role": "assistant", "content": reply, "created_at": now_iso},
    ])

    return {"ok": True, "session_id": session_id, "reply": reply, "created_at": now_iso}


@router.get("/ai/history")
async def ai_history(request: Request, session_id: Optional[str] = None):
    user = await require_auth(request)
    db = get_db()
    if not session_id:
        session_id = f"chat-{user['id'][:8]}-{date.today().isoformat()}"
    history = await db.rahaza_ai_chat_history.find(
        {"session_id": session_id}, {"_id": 0},
    ).sort("created_at", 1).to_list(500)
    return {"session_id": session_id, "messages": history}


@router.post("/ai/root-cause")
async def ai_root_cause(request: Request):
    await require_auth(request)
    db = get_db()
    body = await request.json()
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "question wajib diisi.")

    from_ = (date.today() - timedelta(days=7)).isoformat()
    to = date.today().isoformat()
    metrics = await rh_agg.weekly_qc_downtime(db, from_iso=from_, to_iso=to)
    fail_rate = round(metrics["qc_fail"] / max(metrics["qc_checked"], 1) * 100, 1)

    context = (
        f"DATA PRODUKSI 7 HARI TERAKHIR ({from_} s/d {to}):\n"
        f"- QC: checked {metrics['qc_checked']} pcs, fail {metrics['qc_fail']} pcs "
        f"(fail rate {fail_rate}%)\n"
        f"- Downtime total: {metrics['downtime_minutes']} menit dari "
        f"{metrics['downtime_event_count']} kejadian\n"
        f"- Alert aktif: {metrics['alerts_active']} "
        f"({', '.join((m or '')[:50] for m in metrics['alert_messages'])})\n"
        f"- Jumlah event QC: {metrics['qc_event_count']}"
    )
    user_prompt = (
        f"{context}\n\nPERTANYAAN: {question}\n\n"
        "Berikan analisis root cause dalam Bahasa Indonesia yang:\n"
        "1. Identifikasi kemungkinan penyebab utama berdasarkan data\n"
        "2. Sebutkan data pendukung (angka spesifik)\n"
        "3. Rekomendasikan 2-3 tindakan korektif\n"
        "Jawaban singkat, padat, max 200 kata."
    )

    try:
        answer = await call_claude(
            system_message=SystemPrompts.RAHAZA_ROOT_CAUSE,
            user_message=user_prompt,
            session_tag="root-cause",
            db=db,
        )
    except Exception as e:
        logger.error("Root cause error: %s", e)
        answer = (
            f"Berdasarkan data, fail rate QC {fail_rate}% dan downtime "
            f"{metrics['downtime_minutes']} menit perlu investigasi lebih lanjut."
        )

    return {"ok": True, "question": question, "analysis": answer, "data_period": f"{from_} s/d {to}"}


@router.post("/ai/smart-search")
async def ai_smart_search(request: Request):
    """Smart search across WOs, orders, employees — now DB-level via $regex."""
    await require_auth(request)
    db = get_db()
    body = await request.json()
    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "query wajib diisi.")

    results = await rh_agg.smart_search(db, query=query, limit=20)
    return {"ok": True, "query": query, "count": len(results), "results": results}


@router.get("/ai/predictive-delay")
async def predictive_delay(
    request: Request,
    wo_id: Optional[str] = None,
):
    await require_auth(request)
    db = get_db()

    wos = await rh_agg.list_predictive_targets(db, wo_id=wo_id)
    today = date.today()

    # Single aggregation for daily avg output (covers last 14 days).
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    avg_daily = await rh_agg.daily_wip_avg(db, since_iso=cutoff_iso)

    results = []
    # 2026-08-07 — DULU WO dengan `due_date` rusak di-`continue` DIAM-DIAM.
    # Ini alat PREDIKSI KETERLAMBATAN: WO yang datanya kacau justru kandidat
    # terkuat untuk terlambat, tetapi dialah yang dipastikan tidak pernah
    # muncul di daftar risiko. Sekarang dicatat + dikembalikan ke layar.
    dq = SkipTracker("prediksi keterlambatan WO")
    for wo in wos:
        due = wo.get("due_date")
        qty_target = wo.get("qty") or 0
        qty_produced = wo.get("qty_produced") or 0
        qty_remaining = max(0, int(qty_target) - int(qty_produced))
        if qty_remaining == 0:
            continue
        if not due:
            dq.skip(doc_id=wo.get("id"), label=wo.get("wo_number"), field="due_date",
                    value=due, reason="WO tanpa due date — risikonya tidak bisa dihitung")
            continue
        try:
            due_date = date.fromisoformat(str(due)[:10])
        except (ValueError, TypeError) as e:
            dq.skip(doc_id=wo.get("id"), label=wo.get("wo_number"), field="due_date",
                    value=due, error=e)
            continue
        days_left = (due_date - today).days
        days_needed = int(qty_remaining / avg_daily) + 1
        prob_delay = 0.0
        if days_needed > days_left:
            prob_delay = min(
                100,
                round((days_needed - days_left) / max(days_needed, 1) * 100 + 30, 0),
            )
        if prob_delay >= 40:
            risk_level = "high"
        elif prob_delay >= 20:
            risk_level = "medium"
        else:
            risk_level = "low"
        results.append({
            "wo_id": wo["id"],
            "wo_number": wo.get("wo_number", ""),
            "due_date": due,
            "days_left": days_left,
            "qty_remaining": qty_remaining,
            "avg_daily_output": round(avg_daily, 1),
            "days_needed": days_needed,
            "prob_delay_pct": prob_delay,
            "risk_level": risk_level,
            "message": (
                f"WO {wo.get('wo_number','')} butuh ~{days_needed} hari lagi, "
                f"tersisa {days_left} hari sebelum due date."
                if prob_delay > 0
                else ""
            ),
        })

    results.sort(key=lambda x: x["prob_delay_pct"], reverse=True)
    dq.log(logger)
    return {
        "ok": True,
        "total": len(results),
        "high_risk": sum(1 for r in results if r["risk_level"] == "high"),
        "data": results,
        "data_quality": dq.as_dict(),
    }
