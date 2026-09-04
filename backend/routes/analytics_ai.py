"""
Phase 8 — Analytics & AI (Production & QC Root-Cause Analysis)

Pattern mirip dengan WMS RCA (Phase 7.8): mengumpulkan data dari beberapa
collection produksi / QC, meringkasnya, lalu minta Claude Sonnet menganalisis
pola dan menghasilkan rekomendasi dalam Bahasa Indonesia.

Endpoints:
  POST /api/analytics/ai/production/rca  — analisis pola produksi (bottleneck, delay, underperforming line)
  POST /api/analytics/ai/qc/rca          — analisis pola QC failure (defect pattern, high-fail line/model)
  GET  /api/analytics/ai/history         — riwayat RCA 20 terakhir untuk user ini

Requires: EMERGENT_LLM_KEY di environment.
"""
# ruff: noqa: E741

import os
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from database import get_db
from auth import require_auth, serialize_doc
from utils.data_quality import SkipTracker
import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics/ai", tags=["analytics-ai"])

MIN_DATA_POINTS = 5  # minimal supaya analisa tidak misleading


def _now():
    return datetime.now(timezone.utc)


def _parse_range(days: int) -> datetime:
    return _now() - timedelta(days=max(1, min(days, 180)))


# ── Pydantic input ───────────────────────────────────────────────────────────

class RCAFilter(BaseModel):
    days: int = 30
    line_id: Optional[str] = None
    model_id: Optional[str] = None
    process_code: Optional[str] = None


# ── Helper: call Claude via Emergent LLM Key ────────────────────────────────

async def _call_claude(system_msg: str, prompt: str, session_tag: str) -> dict:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(503, "EMERGENT_LLM_KEY belum dikonfigurasi.")
    try:
        from ai_llm import LlmChat, UserMessage
        chat = LlmChat(
            api_key=key,
            session_id=session_tag,
            system_message=system_msg,
        ).with_model("executive")
        resp = await chat.send_message(UserMessage(text=prompt))
        raw = resp if isinstance(resp, str) else str(resp)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.lstrip().startswith("json"):
                raw = raw.lstrip()[4:]
        try:
            return json.loads(raw.strip())
        except Exception:
            return {
                "root_cause_hypothesis": "Parsing gagal",
                "confidence": "rendah",
                "reasoning": raw[:500],
                "risk_level": "sedang",
                "recommended_actions": ["Retry analisa", "Verifikasi data sumber"],
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"AI RCA gagal: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCTION RCA — pola bottleneck, delay WO, line underperforming
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/production/rca")
async def production_rca(data: RCAFilter, request: Request):
    """
    Analisis pola produksi N hari terakhir (default 30):
    - Throughput per process (input vs output)
    - WO delay (target vs actual completion)
    - Line performance ranking
    """
    user = await require_auth(request)
    db = get_db()
    since = _parse_range(data.days)

    wip_q = {"timestamp": {"$gte": since}, "event_type": {"$in": ["input", "output"]}}
    if data.line_id:
        wip_q["line_id"] = data.line_id
    if data.model_id:
        wip_q["model_id"] = data.model_id
    if data.process_code:
        wip_q["process_code"] = data.process_code

    # Aggregate per process: total input, total output, discrepancy
    pipeline_proc = [
        {"$match": wip_q},
        {"$group": {
            "_id": {"proc": "$process_code", "type": "$event_type"},
            "total_qty": {"$sum": "$qty"},
        }},
    ]
    proc_rows = await db.rahaza_wip_events.aggregate(pipeline_proc).to_list(500)
    proc_summary = {}
    for r in proc_rows:
        proc = r["_id"].get("proc") or "unknown"
        typ = r["_id"].get("type")
        proc_summary.setdefault(proc, {"input": 0, "output": 0})
        proc_summary[proc][typ] = r["total_qty"]
    # Sort by discrepancy (input - output)
    proc_list = [
        {"process": p, "input": v.get("input", 0), "output": v.get("output", 0),
         "discrepancy": (v.get("input", 0) - v.get("output", 0))}
        for p, v in proc_summary.items()
    ]
    proc_list.sort(key=lambda x: -x["discrepancy"])

    # Aggregate per line
    pipeline_line = [
        {"$match": {**wip_q, "event_type": "output"}},
        {"$group": {"_id": "$line_id", "total_output": {"$sum": "$qty"}, "events": {"$sum": 1}}},
        {"$sort": {"total_output": -1}},
    ]
    line_rows = await db.rahaza_wip_events.aggregate(pipeline_line).to_list(500)
    # Enrich line names
    line_ids = [r["_id"] for r in line_rows if r["_id"]]
    line_map = {}
    if line_ids:
        async for ln in db.rahaza_lines.find({"id": {"$in": line_ids}}, {"_id": 0}):
            line_map[ln["id"]] = ln.get("name", ln.get("code", "-"))
    line_list = [
        {"line": line_map.get(r["_id"]) or r["_id"] or "unknown",
         "total_output": r["total_output"], "events": r["events"]}
        for r in line_rows
    ]

    # WO delay analysis — count overdue vs on-time
    wo_q = {"status": {"$in": ["in_progress", "complete", "completed"]}}
    wos = await db.rahaza_work_orders.find(
        wo_q, {"_id": 0, "id": 1, "wo_number": 1, "target_end_date": 1,
               "completed_at": 1, "status": 1, "qty": 1}
    ).limit(100).to_list(500)
    overdue_count = 0
    on_time_count = 0
    # 2026-08-07 — DULU WO dengan `target_end_date` rusak di-`continue` DIAM-DIAM.
    # Di sini akibatnya khas dan berbahaya: yang mengecil adalah PENYEBUT KPI,
    # sehingga persentase ketepatan waktu justru NAIK karena datanya rusak.
    # Angka ini lalu dikirim ke LLM sebagai bahan analisis, jadi kesimpulan AI-nya
    # ikut salah. Sekarang selalu tercatat, dan jumlahnya ikut disebut di prompt.
    dq = SkipTracker("analisis keterlambatan WO")
    for w in wos:
        tgt = w.get("target_end_date")
        comp = w.get("completed_at")
        if not tgt:
            dq.skip(doc_id=w.get("id"), label=w.get("wo_number"),
                    field="target_end_date", value=tgt,
                    reason="WO tanpa target tanggal selesai")
            continue
        try:
            tgt_dt = datetime.fromisoformat(tgt) if isinstance(tgt, str) else tgt
        except (ValueError, TypeError) as e:
            dq.skip(doc_id=w.get("id"), label=w.get("wo_number"),
                    field="target_end_date", value=tgt, error=e)
            continue
        if comp:
            comp_dt = datetime.fromisoformat(comp) if isinstance(comp, str) else comp
            if comp_dt.replace(tzinfo=timezone.utc) > tgt_dt.replace(tzinfo=timezone.utc) if not tgt_dt.tzinfo else comp_dt > tgt_dt:
                overdue_count += 1
            else:
                on_time_count += 1

    total_events = await db.rahaza_wip_events.count_documents(wip_q)
    dq.log(logger)
    if total_events < MIN_DATA_POINTS:
        raise HTTPException(400, f"Data produksi belum cukup ({total_events} events, min {MIN_DATA_POINTS}). Pastikan modul produksi sudah aktif digunakan.")

    # Build prompt
    filters_desc = []
    if data.line_id:
        filters_desc.append(f"line={data.line_id}")
    if data.model_id:
        filters_desc.append(f"model={data.model_id}")
    if data.process_code:
        filters_desc.append(f"process={data.process_code}")

    prompt = f"""Kamu adalah konsultan operasional manufaktur garment yang berpengalaman.
Analisis pola produksi pada periode {data.days} hari terakhir dan berikan RCA + rekomendasi action.

FILTER: {', '.join(filters_desc) if filters_desc else 'Semua line/model/process'}
Total WIP events: {total_events}

TOP 5 PROCESS (berdasarkan discrepancy input-output — bottleneck kandidat):
{chr(10).join([f"  - {p['process']}: Input {p['input']}, Output {p['output']}, Gap {p['discrepancy']}" for p in proc_list[:5]])}

TOP 5 LINE (berdasarkan output):
{chr(10).join([f"  - {l['line']}: {l['total_output']} pcs ({l['events']} events)" for l in line_list[:5]])}

WO DELAY STATUS (sample {len(wos)} WO):
  - On-time: {on_time_count}
  - Overdue: {overdue_count}
  - TIDAK BISA DINILAI (tanggal target kosong/rusak): {dq.count} — angka ketepatan waktu di atas dihitung TANPA WO ini, jadi jangan menyimpulkan ketepatan waktu membaik bila jumlah ini besar.

TUGAS:
Berikan RCA dengan format JSON:
{{
  "root_cause_hypothesis": "hipotesis utama dalam 1 kalimat (pilih: 'bottleneck proses tertentu', 'kapasitas line kurang', 'model complexity tinggi', 'absensi operator', 'material delay', 'fluktuasi normal')",
  "confidence": "tinggi|sedang|rendah",
  "reasoning": "penjelasan 2-3 kalimat mengacu ke data di atas",
  "risk_level": "tinggi|sedang|rendah",
  "bottleneck_process": "kode proses yang paling menghambat (atau null)",
  "weakest_line": "nama line paling bawah (atau null)",
  "recommended_actions": [
    "aksi 1 (imperative, Bahasa Indonesia)",
    "aksi 2",
    "aksi 3"
  ]
}}

Balas HANYA dengan JSON valid tanpa markdown."""

    analysis = await _call_claude(
        "Kamu adalah analis produksi manufaktur garment yang memberikan RCA singkat, actionable, berbasis data, dalam format JSON.",
        prompt,
        f"prod-rca-{user['id'][:8]}-{int(_now().timestamp())}",
    )

    result = {
        "period_days": data.days,
        "scope": {"line_id": data.line_id, "model_id": data.model_id, "process_code": data.process_code},
        "stats": {
            "total_wip_events": total_events,
            "processes_analyzed": len(proc_list),
            "lines_analyzed": len(line_list),
            "wo_on_time": on_time_count, "wo_overdue": overdue_count,
            "top_bottleneck_process": proc_list[0] if proc_list else None,
            "top_line": line_list[0] if line_list else None,
        },
        "analysis": analysis,
        "generated_at": _now().isoformat(),
    }

    # Log
    await db.ai_rca_history.insert_one({
        "id": str(uuid.uuid4()),
        "type": "production",
        "user_id": user.get("id"),
        "user_email": user.get("email"),
        "filters": data.model_dump(),
        "result": result,
        "created_at": _now(),
    })
    return serialize_doc(result)


# ══════════════════════════════════════════════════════════════════════════════
# QC RCA — pola kegagalan QC, defect pattern, high-fail line/model
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/qc/rca")
async def qc_rca(data: RCAFilter, request: Request):
    """
    Analisis pola QC N hari terakhir:
    - Fail rate overall
    - Top defect types
    - Line/model dengan fail rate tertinggi
    """
    user = await require_auth(request)
    db = get_db()
    since = _parse_range(data.days)

    q = {"created_at": {"$gte": since.isoformat()}}
    if data.line_id:
        q["line_id"] = data.line_id
    if data.model_id:
        q["model_id"] = data.model_id

    rows = await db.rahaza_qc_events.find(q, {"_id": 0}).limit(1000).to_list(500)
    if len(rows) < MIN_DATA_POINTS:
        raise HTTPException(400, f"Data QC belum cukup ({len(rows)} events, min {MIN_DATA_POINTS}).")

    total_checked = sum(r.get("checked_qty", 0) for r in rows)
    total_pass = sum(r.get("pass_qty", 0) for r in rows)
    total_fail = sum(r.get("fail_qty", 0) for r in rows)
    fail_rate = (total_fail / total_checked * 100) if total_checked else 0

    # Aggregate by line
    line_agg = {}
    for r in rows:
        lid = r.get("line_id") or "unknown"
        if lid not in line_agg:
            line_agg[lid] = {"checked": 0, "fail": 0, "events": 0}
        line_agg[lid]["checked"] += r.get("checked_qty", 0)
        line_agg[lid]["fail"] += r.get("fail_qty", 0)
        line_agg[lid]["events"] += 1
    line_ids = list(line_agg.keys())
    line_map = {}
    async for ln in db.rahaza_lines.find({"id": {"$in": line_ids}}, {"_id": 0}):
        line_map[ln["id"]] = ln.get("name", ln.get("code", "-"))
    line_list = [
        {
            "line": line_map.get(lid) or lid[:8] + "…" if lid != "unknown" else "unknown",
            "checked": v["checked"], "fail": v["fail"], "events": v["events"],
            "fail_rate": round(v["fail"] / v["checked"] * 100, 2) if v["checked"] else 0,
        }
        for lid, v in line_agg.items()
    ]
    line_list.sort(key=lambda x: -x["fail_rate"])

    # Aggregate by model
    model_agg = {}
    for r in rows:
        mid = r.get("model_id") or "unknown"
        if mid not in model_agg:
            model_agg[mid] = {"checked": 0, "fail": 0, "events": 0}
        model_agg[mid]["checked"] += r.get("checked_qty", 0)
        model_agg[mid]["fail"] += r.get("fail_qty", 0)
        model_agg[mid]["events"] += 1
    model_ids = list(model_agg.keys())
    model_map = {}
    async for m in db.rahaza_models.find({"id": {"$in": model_ids}}, {"_id": 0}):
        model_map[m["id"]] = m.get("name", m.get("code", "-"))
    model_list = [
        {
            "model": model_map.get(mid) or mid[:8] + "…" if mid != "unknown" else "unknown",
            "checked": v["checked"], "fail": v["fail"],
            "fail_rate": round(v["fail"] / v["checked"] * 100, 2) if v["checked"] else 0,
        }
        for mid, v in model_agg.items()
    ]
    model_list.sort(key=lambda x: -x["fail_rate"])

    # Top defects (from defect_code_ids / defect_details)
    defect_codes = {}
    for r in rows:
        for code_id in (r.get("defect_code_ids") or []):
            defect_codes[code_id] = defect_codes.get(code_id, 0) + 1
    defect_ids = list(defect_codes.keys())
    defect_map = {}
    if defect_ids:
        async for d in db.rahaza_defect_codes.find({"id": {"$in": defect_ids}}, {"_id": 0}):
            defect_map[d["id"]] = d.get("name", d.get("code", "-"))
    top_defects = sorted(
        [{"defect": defect_map.get(did, did[:8] + "…"), "count": c} for did, c in defect_codes.items()],
        key=lambda x: -x["count"]
    )[:10]

    prompt = f"""Kamu adalah konsultan quality assurance garment yang berpengalaman.
Analisis pola QC failure pada periode {data.days} hari terakhir dan beri RCA + rekomendasi action.

RINGKASAN:
  - Total checked: {total_checked} pcs
  - Total pass:    {total_pass} pcs
  - Total fail:    {total_fail} pcs
  - Fail rate:     {fail_rate:.2f}%
  - Total QC events: {len(rows)}

TOP 5 LINE DENGAN FAIL RATE TERTINGGI:
{chr(10).join([f"  - {l['line']}: {l['fail_rate']}% ({l['fail']}/{l['checked']} pcs, {l['events']} events)" for l in line_list[:5]])}

TOP 5 MODEL DENGAN FAIL RATE TERTINGGI:
{chr(10).join([f"  - {m['model']}: {m['fail_rate']}% ({m['fail']}/{m['checked']} pcs)" for m in model_list[:5]])}

TOP DEFECT CODES:
{chr(10).join([f"  - {d['defect']}: {d['count']}x" for d in top_defects[:5]]) or '  (tidak ada defect code tercatat)'}

TUGAS:
Berikan RCA dengan format JSON:
{{
  "root_cause_hypothesis": "hipotesis utama 1 kalimat (pilih: 'skill operator rendah pada line tertentu', 'model design complexity', 'alat/mesin butuh kalibrasi', 'material quality issue', 'target kecepatan terlalu tinggi', 'training gap', 'fluktuasi normal')",
  "confidence": "tinggi|sedang|rendah",
  "reasoning": "2-3 kalimat merujuk ke data",
  "risk_level": "tinggi|sedang|rendah",
  "worst_line": "nama line dengan fail rate tertinggi (atau null)",
  "worst_model": "nama model dengan fail rate tertinggi (atau null)",
  "primary_defect_pattern": "deskripsi singkat pola defect dominan (atau null)",
  "recommended_actions": [
    "aksi 1 imperative Bahasa Indonesia",
    "aksi 2",
    "aksi 3"
  ]
}}

Balas HANYA dengan JSON valid tanpa markdown."""

    analysis = await _call_claude(
        "Kamu adalah analis QA manufaktur garment yang memberikan RCA actionable berbasis data, format JSON.",
        prompt,
        f"qc-rca-{user['id'][:8]}-{int(_now().timestamp())}",
    )

    result = {
        "period_days": data.days,
        "scope": {"line_id": data.line_id, "model_id": data.model_id},
        "stats": {
            "total_checked": total_checked,
            "total_pass": total_pass,
            "total_fail": total_fail,
            "fail_rate_pct": round(fail_rate, 2),
            "qc_events": len(rows),
            "lines_analyzed": len(line_list),
            "models_analyzed": len(model_list),
            "top_defects": top_defects,
            "worst_line": line_list[0] if line_list else None,
            "worst_model": model_list[0] if model_list else None,
        },
        "analysis": analysis,
        "generated_at": _now().isoformat(),
    }

    await db.ai_rca_history.insert_one({
        "id": str(uuid.uuid4()),
        "type": "qc",
        "user_id": user.get("id"),
        "user_email": user.get("email"),
        "filters": data.model_dump(),
        "result": result,
        "created_at": _now(),
    })
    return serialize_doc(result)


# ══════════════════════════════════════════════════════════════════════════════
# HISTORY — last RCA analyses
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/history")
async def rca_history(request: Request, type: Optional[str] = None, limit: int = Query(20, le=100)):
    user = await require_auth(request)
    db = get_db()
    q = {"user_id": user.get("id")}
    if type:
        q["type"] = type
    rows = await db.ai_rca_history.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(500)
    return serialize_doc(rows)
