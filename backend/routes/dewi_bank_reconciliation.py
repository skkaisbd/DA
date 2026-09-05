"""
Rekonsiliasi Bank (H-05/H-06 — sesi 110)
Prefix: /api/finance/bank-recon

Koleksi:
  bank_recon_sessions  — sesi per periode & REKENING KAS/BANK (rahaza_cash_accounts → gl_account_code)
  bank_recon_txns      — mutasi rekening koran per sesi (impor CSV / manual). `direction`: in|out
  bank_recon_matches   — tautan mutasi ↔ baris jurnal GL akun bank (SSOT jurnal TIDAK ditulis)

Aturan auto-match (keputusan pemilik): arah sama + |selisih nominal| ≤ Rp 1.000 + |selisih tanggal| ≤ 3 hari,
satu-ke-satu, kandidat terbaik = selisih nominal terkecil → tanggal terdekat → kemiripan keterangan.
Semua tautan bisa dilepas/dibuat manual.
"""
from fastapi import APIRouter, Request, HTTPException, Query, UploadFile, File
from database import get_db
from auth import require_auth, serialize_doc
from datetime import datetime, timezone, date, timedelta
from typing import Optional
import calendar
import re
import uuid
import logging
import csv
import io

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/finance/bank-recon", tags=["bank-reconciliation"])

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
AMOUNT_TOLERANCE = 1000.0   # rupiah
DAYS_TOLERANCE = 3
SETTLEMENT_AMOUNT_TOLERANCE = 1.0


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc).isoformat()


def _validate_period(period: str):
    if not period or not PERIOD_RE.match(period):
        raise HTTPException(400, "period harus format YYYY-MM (mis. 2026-05)")


def _period_range(period: str):
    y, m = map(int, period.split("-"))
    return f"{period}-01", f"{period}-{calendar.monthrange(y, m)[1]:02d}"


def _direction(body_type: Optional[str], body_dir: Optional[str]) -> str:
    """Konvensi aplikasi: type 'debit' = uang MASUK (Dr Bank), 'credit' = uang KELUAR."""
    d = (body_dir or "").lower().strip()
    if d in ("in", "out"):
        return d
    return "out" if (body_type or "debit").lower() == "credit" else "in"


def _txn_doc(session_id: str, txn_date: str, description: str, reference: str, amount: float, direction: str) -> dict:
    return {
        "id": _uid(), "session_id": session_id, "txn_date": txn_date,
        "description": (description or "").strip(), "reference": (reference or "").strip(),
        "amount": round(abs(float(amount or 0)), 2), "direction": direction,
        "type": "debit" if direction == "in" else "credit",
        "is_matched": False, "match_id": None, "match_ref": None, "match_type": None, "created_at": _now(),
    }


def _days_between(a: str, b: str) -> Optional[int]:
    try:
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except (ValueError, TypeError):
        return None


async def _get_session(db, session_id: str, writable: bool = False) -> dict:
    s = await db.bank_recon_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Sesi tidak ditemukan")
    if writable and s.get("status") == "approved":
        raise HTTPException(400, "Sesi sudah disetujui, tidak bisa diubah.")
    return s


# ═══════════════════════════════════════════════════════════════════
# SISI GL — baris jurnal akun bank sesi + mutasi kas internal
# ═══════════════════════════════════════════════════════════════════

async def _bank_gl_lines(db, s: dict) -> list:
    """Baris jurnal POSTED pada akun GL rekening sesi, dalam periode sesi (H-06: dulu filter field yg tak ada)."""
    code = s.get("gl_account_code")
    if not code:
        return []
    start, end = _period_range(s["period"])
    matches = {m["target_key"]: m async for m in db.bank_recon_matches.find(
        {"session_id": s["id"], "target_type": "gl_line"}, {"_id": 0})}
    out = []
    async for je in db.rahaza_journal_entries.find(
            {"status": "posted", "date": {"$gte": start, "$lte": end}, "lines.account_code": code},
            {"_id": 0, "id": 1, "je_number": 1, "date": 1, "memo": 1, "source_module": 1, "source_ref": 1, "lines": 1}
    ).sort("date", 1):
        for idx, ln in enumerate(je.get("lines") or []):
            if ln.get("account_code") != code:
                continue
            debit = float(ln.get("debit") or 0)
            credit = float(ln.get("credit") or 0)
            if debit <= 0 and credit <= 0:
                continue
            key = f"{je['id']}:{idx}"
            m = matches.get(key)
            out.append({
                "key": key, "je_id": je["id"], "je_number": je.get("je_number"), "date": str(je.get("date"))[:10],
                "memo": je.get("memo") or "", "description": ln.get("description") or "",
                "source_module": je.get("source_module"), "source_ref": je.get("source_ref"),
                "debit": debit, "credit": credit, "direction": "in" if debit > 0 else "out",
                "amount": debit if debit > 0 else credit,
                "is_matched": bool(m), "matched_txn_id": (m or {}).get("txn_id"), "match_id": (m or {}).get("id"),
            })
    return out


async def _gl_balance_until(db, code: str, end: str) -> float:
    total = 0.0
    async for je in db.rahaza_journal_entries.find(
            {"status": "posted", "date": {"$lte": end}, "lines.account_code": code}, {"_id": 0, "lines": 1}):
        for ln in je.get("lines") or []:
            if ln.get("account_code") == code:
                total += float(ln.get("debit") or 0) - float(ln.get("credit") or 0)
    return round(total, 2)


async def _internal_check(db, s: dict, gl_lines: list) -> dict:
    """H-05: mutasi kas internal (rahaza_cash_movements) vs jurnal GL akun bank — harus 1:1."""
    start, end = _period_range(s["period"])
    movements = await db.rahaza_cash_movements.find(
        {"account_id": s.get("cash_account_id"), "date": {"$gte": start, "$lte": end}}, {"_id": 0}).to_list(2000)
    je_ids_with_mv = set()
    issues = []
    rows = []
    for mv in movements:
        amt = round(float(mv.get("amount") or 0), 2)
        je_id = mv.get("gl_je_id")
        status = "ok"
        note = ""
        if not je_id:
            status = "no_gl"
            note = mv.get("post_error") or "Mutasi kas belum punya jurnal GL"
        else:
            je_ids_with_mv.add(je_id)
            ln = next((g for g in gl_lines if g["je_id"] == je_id), None)
            if not ln:
                je = await db.rahaza_journal_entries.find_one({"id": je_id}, {"_id": 0, "status": 1, "date": 1})
                status = "gl_missing" if not je else ("gl_voided" if je.get("status") != "posted" else "gl_outside_period")
                note = {"gl_missing": "Jurnal tidak ditemukan", "gl_voided": "Jurnal sudah di-void",
                        "gl_outside_period": f"Tanggal jurnal {str((je or {}).get('date'))[:10]} di luar periode"}[status]
            elif abs(ln["amount"] - amt) > 0.01 or ln["direction"] != mv.get("direction"):
                status = "amount_mismatch"
                note = f"GL {ln['direction']} {ln['amount']:,.0f} ≠ mutasi {mv.get('direction')} {amt:,.0f}"
        row = {"id": mv["id"], "date": mv.get("date"), "direction": mv.get("direction"), "amount": amt,
               "category": mv.get("category"), "ref_label": mv.get("ref_label"), "source_module": mv.get("source_module"),
               "gl_je_id": je_id, "gl_je_number": mv.get("gl_je_number"), "status": status, "note": note}
        rows.append(row)
        if status != "ok":
            issues.append(row)
    gl_without_movement = [g for g in gl_lines if g["je_id"] not in je_ids_with_mv]
    acc = await db.rahaza_cash_accounts.find_one({"id": s.get("cash_account_id")}, {"_id": 0, "balance": 1})
    return {
        "movements": rows, "issues": issues,
        "gl_without_movement": gl_without_movement,
        "card_balance": round(float((acc or {}).get("balance") or 0), 2),
        "gl_balance_now": await _gl_balance_until(db, s.get("gl_account_code"), "9999-12-31") if s.get("gl_account_code") else 0,
    }


async def _summary(db, s: dict, gl_lines: list) -> dict:
    _, end = _period_range(s["period"])
    gl_bal = await _gl_balance_until(db, s.get("gl_account_code"), end) if s.get("gl_account_code") else 0.0
    txns = await db.bank_recon_txns.find({"session_id": s["id"]}, {"_id": 0}).to_list(5000)
    un_bank = [t for t in txns if not t.get("is_matched")]
    un_gl = [g for g in gl_lines if not g["is_matched"]]
    ub_in = sum(t["amount"] for t in un_bank if t.get("direction", "in") == "in")
    ub_out = sum(t["amount"] for t in un_bank if t.get("direction", "in") == "out")
    ug_in = sum(g["amount"] for g in un_gl if g["direction"] == "in")
    ug_out = sum(g["amount"] for g in un_gl if g["direction"] == "out")
    closing = float(s.get("closing_balance") or 0)
    # saldo GL + mutasi bank yang belum dijurnal − jurnal yang belum tampak di bank ⇒ harus = saldo rekening koran
    adjusted = round(gl_bal + (ub_in - ub_out) - (ug_in - ug_out), 2)
    return {
        "gl_balance_end": gl_bal, "statement_closing": closing, "difference": round(closing - gl_bal, 2),
        "unmatched_bank_count": len(un_bank), "unmatched_bank_in": round(ub_in, 2), "unmatched_bank_out": round(ub_out, 2),
        "unmatched_gl_count": len(un_gl), "unmatched_gl_in": round(ug_in, 2), "unmatched_gl_out": round(ug_out, 2),
        "adjusted_gl_balance": adjusted, "unexplained": round(closing - adjusted, 2),
        "explained": abs(closing - adjusted) <= 0.01,
        "gl_count": len(gl_lines), "bank_count": len(txns),
    }


# ═══════════════════════════════════════════════════════════════════
# SESSIONS
# ═══════════════════════════════════════════════════════════════════

@router.get("/sessions")
async def list_sessions(request: Request, skip: int = 0, limit: int = 20, status: Optional[str] = None,
                        cash_account_id: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {}
    if status:
        q["status"] = status
    if cash_account_id:
        q["cash_account_id"] = cash_account_id
    total = await db.bank_recon_sessions.count_documents(q)
    rows = await db.bank_recon_sessions.find(q, {"_id": 0}).sort("period", -1).skip(skip).limit(limit).to_list(500)
    return {"total": total, "skip": skip, "limit": limit, "has_more": (skip + limit) < total, "items": serialize_doc(rows)}


@router.post("/sessions")
async def create_session(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    period = body.get("period", "")
    _validate_period(period)
    cash_account_id = (body.get("cash_account_id") or "").strip()
    if not cash_account_id:
        raise HTTPException(400, "cash_account_id wajib: pilih rekening kas/bank (Master Rekening).")
    acc = await db.rahaza_cash_accounts.find_one({"id": cash_account_id}, {"_id": 0})
    if not acc:
        raise HTTPException(404, "Rekening kas/bank tidak ditemukan")
    if not acc.get("gl_account_code"):
        raise HTTPException(400, f"Rekening {acc.get('name')} belum punya akun GL (gl_account_code).")
    if await db.bank_recon_sessions.find_one({"period": period, "cash_account_id": cash_account_id}):
        raise HTTPException(409, f"Sesi rekonsiliasi {period} untuk rekening {acc.get('name')} sudah ada.")

    doc = {
        "id": _uid(), "period": period,
        "cash_account_id": cash_account_id, "cash_account_code": acc.get("code"), "gl_account_code": acc["gl_account_code"],
        "bank_name": acc.get("bank_name") or acc.get("name"), "account_no": acc.get("account_number") or "",
        "account_name": acc.get("name"),
        "opening_balance": float(body.get("opening_balance") or 0), "closing_balance": float(body.get("closing_balance") or 0),
        "status": "draft", "total_bank_txns": 0, "matched_count": 0, "unmatched_count": 0, "difference": 0.0,
        "notes": body.get("notes", ""), "created_by": user["id"], "created_by_name": user.get("name", ""),
        "created_at": _now(), "updated_at": _now(), "approved_at": None, "approved_by": None,
    }
    await db.bank_recon_sessions.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    s = await _get_session(db, session_id)
    gl_lines = await _bank_gl_lines(db, s)
    s["gl_lines"] = gl_lines
    s["summary"] = await _summary(db, s, gl_lines)
    return serialize_doc(s)


@router.get("/sessions/{session_id}/gl-lines")
async def session_gl_lines(session_id: str, request: Request, matched: Optional[bool] = None):
    await require_auth(request)
    db = get_db()
    s = await _get_session(db, session_id)
    rows = await _bank_gl_lines(db, s)
    if matched is not None:
        rows = [r for r in rows if r["is_matched"] == matched]
    return {"total": len(rows), "items": serialize_doc(rows), "gl_account_code": s.get("gl_account_code")}


@router.get("/sessions/{session_id}/internal-check")
async def session_internal_check(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    s = await _get_session(db, session_id)
    return serialize_doc(await _internal_check(db, s, await _bank_gl_lines(db, s)))


@router.put("/sessions/{session_id}")
async def update_session(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    await _get_session(db, session_id, writable=True)
    body = await request.json()
    allowed = ["opening_balance", "closing_balance", "notes"]
    upd = {k: v for k, v in body.items() if k in allowed}
    upd["updated_at"] = _now()
    await db.bank_recon_sessions.update_one({"id": session_id}, {"$set": upd})
    return serialize_doc(await db.bank_recon_sessions.find_one({"id": session_id}, {"_id": 0}))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    s = await _get_session(db, session_id)
    if s.get("status") == "approved":
        raise HTTPException(400, "Sesi approved tidak dapat dihapus.")
    await db.marketing_settlements.update_many({"bank_session_id": session_id}, {"$set": {
        "bank_txn_id": None, "bank_session_id": None, "bank_txn_date": None, "bank_linked_at": None}})
    await db.bank_recon_sessions.delete_one({"id": session_id})
    await db.bank_recon_txns.delete_many({"session_id": session_id})
    await db.bank_recon_matches.delete_many({"session_id": session_id})
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════
# BANK TRANSACTIONS (per session)
# ═══════════════════════════════════════════════════════════════════

@router.get("/sessions/{session_id}/transactions")
async def list_transactions(session_id: str, request: Request, skip: int = Query(0, ge=0),
                            limit: int = Query(50, ge=1, le=500), matched: Optional[bool] = None):
    await require_auth(request)
    db = get_db()
    q = {"session_id": session_id}
    if matched is not None:
        q["is_matched"] = matched
    total = await db.bank_recon_txns.count_documents(q)
    rows = await db.bank_recon_txns.find(q, {"_id": 0}).sort("txn_date", 1).skip(skip).limit(limit).to_list(500)
    for r in rows:
        r.setdefault("direction", "in" if r.get("type", "debit") == "debit" else "out")
    return {"total": total, "skip": skip, "limit": limit, "has_more": (skip + limit) < total, "items": rows}


@router.post("/sessions/{session_id}/transactions")
async def add_transaction(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    await _get_session(db, session_id, writable=True)
    body = await request.json()
    if not body.get("txn_date"):
        raise HTTPException(400, "txn_date wajib diisi")
    if float(body.get("amount") or 0) == 0:
        raise HTTPException(400, "amount wajib > 0")
    doc = _txn_doc(session_id, body["txn_date"], body.get("description"), body.get("reference"),
                   body.get("amount"), _direction(body.get("type"), body.get("direction")))
    await db.bank_recon_txns.insert_one(doc)
    doc.pop("_id", None)
    await _recalculate_session(db, session_id)
    return doc


@router.post("/sessions/{session_id}/import-bulk")
async def import_bulk_transactions(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    await _get_session(db, session_id, writable=True)
    body = await request.json()
    txns = body.get("transactions", [])
    if not txns or not isinstance(txns, list):
        raise HTTPException(400, "transactions harus berupa list.")
    docs = [_txn_doc(session_id, t.get("txn_date", ""), t.get("description"), t.get("reference"),
                     t.get("amount"), _direction(t.get("type"), t.get("direction"))) for t in txns[:500]]
    docs = [d for d in docs if d["amount"] > 0 and d["txn_date"]]
    if docs:
        await db.bank_recon_txns.insert_many(docs)
        for d in docs:
            d.pop("_id", None)
    await _recalculate_session(db, session_id)
    return {"imported": len(docs), "message": f"{len(docs)} transaksi berhasil diimpor."}


@router.delete("/sessions/{session_id}/transactions/{txn_id}")
async def delete_transaction(session_id: str, txn_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    await _get_session(db, session_id, writable=True)
    await _release_txn(db, session_id, txn_id)
    res = await db.bank_recon_txns.delete_one({"id": txn_id, "session_id": session_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Transaksi tidak ditemukan.")
    await _recalculate_session(db, session_id)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════
# MATCHING (manual + otomatis) — tautan disimpan di bank_recon_matches
# ═══════════════════════════════════════════════════════════════════

async def _release_txn(db, session_id: str, txn_id: str):
    txn = await db.bank_recon_txns.find_one({"id": txn_id, "session_id": session_id}, {"_id": 0})
    if txn and txn.get("match_type") == "settlement" and txn.get("match_id"):
        await db.marketing_settlements.update_one(
            {"id": txn["match_id"], "bank_txn_id": txn_id},
            {"$set": {"bank_txn_id": None, "bank_session_id": None, "bank_txn_date": None, "bank_linked_at": None}})
    await db.bank_recon_matches.delete_many({"session_id": session_id, "txn_id": txn_id})
    await db.bank_recon_txns.update_one({"id": txn_id, "session_id": session_id}, {"$set": {
        "is_matched": False, "match_id": None, "match_ref": None, "match_type": None, "matched_at": None,
        "match_score": None, "auto_matched": None, "amount_diff": None}})


async def _link_gl_line(db, s: dict, txn: dict, gl: dict, matched_by: str, score: Optional[int] = None) -> dict:
    diff = round(float(txn["amount"]) - float(gl["amount"]), 2)
    m = {"id": _uid(), "session_id": s["id"], "txn_id": txn["id"], "target_type": "gl_line", "target_key": gl["key"],
         "je_id": gl["je_id"], "je_number": gl.get("je_number"), "amount_bank": float(txn["amount"]),
         "amount_gl": float(gl["amount"]), "diff": diff, "days_apart": _days_between(txn.get("txn_date", ""), gl.get("date", "")),
         "matched_by": matched_by, "score": score, "created_at": _now()}
    await db.bank_recon_matches.insert_one(dict(m))
    ref = f"{gl.get('je_number')} · {gl.get('memo') or gl.get('description') or ''}".strip(" ·")
    await db.bank_recon_txns.update_one({"id": txn["id"]}, {"$set": {
        "is_matched": True, "match_id": gl["je_id"], "match_ref": ref, "match_type": "gl_line", "match_key": gl["key"],
        "matched_at": _now(), "match_score": score, "auto_matched": matched_by == "auto", "amount_diff": diff}})
    return m


@router.post("/sessions/{session_id}/match")
async def match_transaction(session_id: str, request: Request):
    """Cocokkan manual. Body: {txn_id, target_key} (key baris GL) — kompatibel lama: {gl_entry_id} = je_id."""
    await require_auth(request)
    db = get_db()
    s = await _get_session(db, session_id, writable=True)
    body = await request.json()
    txn = await db.bank_recon_txns.find_one({"id": body.get("txn_id"), "session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(404, "Transaksi tidak ditemukan.")
    if txn.get("is_matched"):
        raise HTTPException(409, "Mutasi ini sudah dicocokkan. Lepas dulu tautannya (unmatch).")
    gl_lines = await _bank_gl_lines(db, s)
    key = body.get("target_key")
    gl = next((g for g in gl_lines if g["key"] == key), None) if key else \
        next((g for g in gl_lines if g["je_id"] == body.get("gl_entry_id") and not g["is_matched"]), None)
    if not gl:
        raise HTTPException(404, "Baris jurnal akun bank tidak ditemukan di periode sesi ini.")
    if gl["is_matched"]:
        raise HTTPException(409, f"Baris jurnal {gl.get('je_number')} sudah tertaut ke mutasi lain.")
    txn_dir = txn.get("direction") or ("in" if txn.get("type", "debit") == "debit" else "out")
    if txn_dir != gl["direction"]:
        raise HTTPException(400, "Arah berbeda: mutasi bank " + ("MASUK" if txn_dir == "in" else "KELUAR")
                            + " tetapi baris jurnal " + ("MASUK (Dr bank)" if gl["direction"] == "in" else "KELUAR (Cr bank)") + ".")
    m = await _link_gl_line(db, s, txn, gl, "manual")
    await _recalculate_session(db, session_id)
    return {"ok": True, "txn_id": txn["id"], "matched_to": gl["je_id"], "target_key": gl["key"], "diff": m["diff"],
            "warning": (f"Selisih nominal Rp {abs(m['diff']):,.0f} — pertimbangkan penyesuaian bank." if abs(m["diff"]) > 0.01 else None)}


@router.post("/sessions/{session_id}/unmatch")
async def unmatch_transaction(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    await _get_session(db, session_id, writable=True)
    body = await request.json()
    await _release_txn(db, session_id, body.get("txn_id"))
    await _recalculate_session(db, session_id)
    return {"ok": True}


def _desc_overlap(a: str, b: str) -> float:
    aw = set(re.sub(r"[^a-z0-9]", " ", (a or "").lower()).split()) - {"dan", "ke", "di", "dari", "untuk", "the", "a"}
    bw = set(re.sub(r"[^a-z0-9]", " ", (b or "").lower()).split())
    return len(aw & bw) / len(aw) if aw else 0.0


@router.post("/sessions/{session_id}/auto-match")
async def auto_match_transactions(session_id: str, request: Request):
    """Arah sama + |Δnominal| ≤ 1.000 + |Δhari| ≤ 3; satu-ke-satu; terbaik = Δnominal → Δhari → keterangan."""
    await require_auth(request)
    db = get_db()
    s = await _get_session(db, session_id, writable=True)
    txns = await db.bank_recon_txns.find({"session_id": session_id, "is_matched": False}, {"_id": 0}).to_list(2000)
    gl_free = [g for g in await _bank_gl_lines(db, s) if not g["is_matched"]]
    if not txns or not gl_free:
        return {"matched": 0, "attempted": len(txns), "gl_candidates": len(gl_free), "message": "Tidak ada data untuk dicocokkan."}

    pairs = []
    for t in txns:
        t_dir = t.get("direction") or ("in" if t.get("type", "debit") == "debit" else "out")
        t_desc = f"{t.get('description', '')} {t.get('reference', '')}"
        for g in gl_free:
            if g["direction"] != t_dir:
                continue
            diff = abs(float(t["amount"]) - float(g["amount"]))
            if diff > AMOUNT_TOLERANCE:
                continue
            days = _days_between(t.get("txn_date", ""), g["date"])
            if days is None or days > DAYS_TOLERANCE:
                continue
            ov = _desc_overlap(t_desc, f"{g.get('memo', '')} {g.get('description', '')} {g.get('je_number', '')}")
            pairs.append((diff, days, -ov, t["id"], g["key"], t, g))
    pairs.sort(key=lambda p: p[:3])
    used_t, used_g, matched = set(), set(), []
    for diff, days, neg_ov, tid, gkey, t, g in pairs:
        if tid in used_t or gkey in used_g:
            continue
        score = int(100 - min(diff / AMOUNT_TOLERANCE, 1) * 40 - min(days / DAYS_TOLERANCE, 1) * 20 + (-neg_ov) * 10)
        await _link_gl_line(db, s, t, g, "auto", score)
        used_t.add(tid); used_g.add(gkey)
        matched.append({"txn_id": tid, "target_key": gkey, "je_number": g.get("je_number"), "diff": round(diff, 2), "days": days})
    await _recalculate_session(db, session_id)
    return {"matched": len(matched), "attempted": len(txns), "gl_candidates": len(gl_free), "pairs": matched,
            "rule": {"amount_tolerance": AMOUNT_TOLERANCE, "days_tolerance": DAYS_TOLERANCE},
            "message": f"Auto-match selesai: {len(matched)} dari {len(txns)} mutasi dicocokkan (±Rp {AMOUNT_TOLERANCE:,.0f}, ±{DAYS_TOLERANCE} hari)."}


@router.get("/sessions/{session_id}/transactions/{txn_id}/candidates")
async def gl_candidates(session_id: str, txn_id: str, request: Request):
    """Kandidat baris GL untuk satu mutasi (arah sama), diurutkan Δnominal → Δhari. Untuk pencocokan manual."""
    await require_auth(request)
    db = get_db()
    s = await _get_session(db, session_id)
    txn = await db.bank_recon_txns.find_one({"id": txn_id, "session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(404, "Transaksi tidak ditemukan.")
    t_dir = txn.get("direction") or ("in" if txn.get("type", "debit") == "debit" else "out")
    out = []
    for g in await _bank_gl_lines(db, s):
        if g["is_matched"] or g["direction"] != t_dir:
            continue
        diff = round(float(txn["amount"]) - float(g["amount"]), 2)
        days = _days_between(txn.get("txn_date", ""), g["date"])
        out.append({**g, "amount_diff": diff, "days_apart": days,
                    "within_rule": abs(diff) <= AMOUNT_TOLERANCE and days is not None and days <= DAYS_TOLERANCE})
    out.sort(key=lambda x: (not x["within_rule"], abs(x["amount_diff"]), x["days_apart"] if x["days_apart"] is not None else 9999))
    return {"txn": txn, "items": out[:30], "rule_count": sum(1 for o in out if o["within_rule"])}


# ═══════════════════════════════════════════════════════════════════
# PENYESUAIAN BANK DARI MUTASI (biaya admin / bunga) → JE ke akun bank SESI → auto-tautkan
# ═══════════════════════════════════════════════════════════════════

@router.post("/sessions/{session_id}/transactions/{txn_id}/adjust")
async def adjust_from_txn(session_id: str, txn_id: str, request: Request):
    """Body: {adjustment_type: bank_charge|interest_income|service_fee|other, description?, expense_account?, income_account?}."""
    user = await require_auth(request)
    db = get_db()
    s = await _get_session(db, session_id, writable=True)
    txn = await db.bank_recon_txns.find_one({"id": txn_id, "session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(404, "Transaksi tidak ditemukan.")
    if txn.get("is_matched"):
        raise HTTPException(409, "Mutasi sudah dicocokkan.")
    body = await request.json()
    atype = body.get("adjustment_type") or "bank_charge"
    t_dir = txn.get("direction") or ("in" if txn.get("type", "debit") == "debit" else "out")
    if atype in ("bank_charge", "service_fee") and t_dir != "out":
        raise HTTPException(400, "Biaya bank adalah uang KELUAR — mutasi ini uang masuk.")
    if atype == "interest_income" and t_dir != "in":
        raise HTTPException(400, "Bunga bank adalah uang MASUK — mutasi ini uang keluar.")
    from routes.rahaza_posting import post_bank_recon_adjustment
    adj = {
        "id": _uid(), "bank_account_id": s["cash_account_id"], "bank_account_name": s.get("account_name"),
        "bank_account_code": s.get("gl_account_code"), "adjustment_type": atype, "adjustment_date": txn.get("txn_date"),
        "amount": round(float(txn["amount"]), 2), "description": body.get("description") or txn.get("description") or atype,
        "reference_number": txn.get("reference") or "", "expense_account": body.get("expense_account") or "",
        "income_account": body.get("income_account") or "", "status": "draft", "session_id": session_id, "txn_id": txn_id,
        "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
        "created_by": user.get("id"), "created_by_name": user.get("name", ""),
    }
    await db.rahaza_bank_recon_adjustments.insert_one(dict(adj))
    res = await post_bank_recon_adjustment(db, adj, user)
    if not res.get("ok"):
        await db.rahaza_bank_recon_adjustments.delete_one({"id": adj["id"]})
        raise HTTPException(400, res.get("error") or "Posting penyesuaian gagal")
    await db.rahaza_bank_recon_adjustments.update_one({"id": adj["id"]}, {"$set": {
        "status": "posted", "posted_at": datetime.now(timezone.utc), "posted_by": user.get("id"),
        "je_id": res.get("je_id"), "je_number": res.get("je_number")}})
    delta = adj["amount"] if t_dir == "in" else -adj["amount"]
    await db.rahaza_cash_accounts.update_one({"id": s["cash_account_id"]}, {"$inc": {"balance": delta}})
    await db.rahaza_cash_movements.insert_one({
        "id": _uid(), "account_id": s["cash_account_id"], "account_name": s.get("account_name"), "direction": t_dir,
        "amount": adj["amount"], "category": "bank_adjustment", "ref_id": adj["id"], "ref_label": adj["description"],
        "source_module": "bank_recon", "date": txn.get("txn_date"), "notes": atype, "timestamp": datetime.now(timezone.utc),
        "created_by": user.get("id"), "created_by_name": user.get("name", ""),
        "gl_je_id": res.get("je_id"), "gl_je_number": res.get("je_number"), "gl_posted_at": datetime.now(timezone.utc)})
    gl = next((g for g in await _bank_gl_lines(db, s) if g["je_id"] == res.get("je_id") and not g["is_matched"]), None)
    if gl:
        await _link_gl_line(db, s, txn, gl, "adjustment")
    await _recalculate_session(db, session_id)
    return {"ok": True, "adjustment_id": adj["id"], "je_number": res.get("je_number"), "matched": bool(gl),
            "message": f"Penyesuaian {atype} Rp {adj['amount']:,.0f} dijurnal ({res.get('je_number')}) ke akun {s.get('gl_account_code')}."}


# ═══════════════════════════════════════════════════════════════════
# TAUTAN MUTASI BANK ↔ PENCAIRAN MARKETPLACE (F9)
# ═══════════════════════════════════════════════════════════════════

@router.get("/sessions/{session_id}/transactions/{txn_id}/settlement-candidates")
async def settlement_candidates(session_id: str, txn_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    txn = await db.bank_recon_txns.find_one({"id": txn_id, "session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(404, "Transaksi tidak ditemukan.")
    t_dir = txn.get("direction") or ("in" if txn.get("type", "debit") == "debit" else "out")
    if t_dir != "in":
        raise HTTPException(400, "Pencairan marketplace adalah uang MASUK — baris mutasi ini adalah uang keluar.")
    amount = float(txn.get("amount") or 0)
    rows = await db.marketing_settlements.find(
        {"$or": [{"bank_txn_id": None}, {"bank_txn_id": {"$exists": False}}, {"bank_txn_id": txn_id}]},
        {"_id": 0, "id": 1, "settlement_id": 1, "settlement_date": 1, "net_payout": 1, "gross_sales": 1, "platform": 1,
         "account_id": 1, "je_number": 1, "je_status": 1, "math_verified": 1, "bank_txn_id": 1}).to_list(2000)
    acc_ids = list({r.get("account_id") for r in rows if r.get("account_id")})
    accounts = {a["id"]: a.get("account_name") for a in await db.marketing_platform_accounts.find(
        {"id": {"$in": acc_ids}}, {"_id": 0, "id": 1, "account_name": 1}).to_list(500)}
    out = []
    for r in rows:
        diff = round(float(r.get("net_payout") or 0) - amount, 2)
        days = _days_between(r.get("settlement_date") or "", txn.get("txn_date") or "")
        out.append({**r, "account_name": accounts.get(r.get("account_id")) or r.get("account_id"), "amount_diff": diff,
                    "amount_match": abs(diff) <= SETTLEMENT_AMOUNT_TOLERANCE, "days_apart": days,
                    "linked_here": r.get("bank_txn_id") == txn_id})
    out.sort(key=lambda x: (not x["amount_match"], x["days_apart"] if x["days_apart"] is not None else 9999, abs(x["amount_diff"])))
    return {"ok": True, "txn": txn, "items": out[:15], "exact_count": sum(1 for o in out if o["amount_match"])}


@router.post("/sessions/{session_id}/link-settlement")
async def link_settlement(session_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    await _get_session(db, session_id, writable=True)
    body = await request.json()
    txn_id = body.get("txn_id")
    sdoc_id = body.get("settlement_doc_id")
    txn = await db.bank_recon_txns.find_one({"id": txn_id, "session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(404, "Transaksi tidak ditemukan.")
    if txn.get("is_matched"):
        raise HTTPException(409, "Mutasi ini sudah dicocokkan. Lepas dulu tautannya (unmatch).")
    t_dir = txn.get("direction") or ("in" if txn.get("type", "debit") == "debit" else "out")
    if t_dir != "in":
        raise HTTPException(400, "Pencairan marketplace adalah uang MASUK — baris mutasi ini adalah uang keluar.")
    st = await db.marketing_settlements.find_one({"id": sdoc_id}, {"_id": 0})
    if not st:
        raise HTTPException(404, "Pencairan tidak ditemukan.")
    if st.get("bank_txn_id") and st.get("bank_txn_id") != txn_id:
        raise HTTPException(409, f"Pencairan {st.get('settlement_id')} sudah tertaut ke mutasi lain (tanggal {st.get('bank_txn_date')}).")
    diff = round(float(st.get("net_payout") or 0) - float(txn.get("amount") or 0), 2)
    if abs(diff) > SETTLEMENT_AMOUNT_TOLERANCE:
        rp = lambda v: f"Rp {float(v or 0):,.0f}".replace(",", ".")  # noqa: E731
        raise HTTPException(400, f"Nominal berbeda: mutasi bank {rp(txn.get('amount'))} vs pencairan {st.get('settlement_id')} "
                                 f"{rp(st.get('net_payout'))} (selisih {rp(diff)}). Koreksi 'Nominal dicairkan' di Pencairan "
                                 f"Marketplace agar sama dengan mutasi bank, lalu tautkan lagi.")
    now = _now()
    ref = f"Pencairan {st.get('settlement_id')} · {st.get('platform') or ''}".strip(" ·")
    await db.bank_recon_txns.update_one({"id": txn_id}, {"$set": {
        "is_matched": True, "match_id": sdoc_id, "match_ref": ref, "match_type": "settlement", "matched_at": now}})
    await db.bank_recon_matches.insert_one({"id": _uid(), "session_id": session_id, "txn_id": txn_id, "target_type": "settlement",
                                            "target_key": sdoc_id, "je_id": st.get("je_id"), "je_number": st.get("je_number"),
                                            "amount_bank": float(txn["amount"]), "amount_gl": float(st.get("net_payout") or 0),
                                            "diff": -diff, "matched_by": "manual", "created_at": now})
    await db.marketing_settlements.update_one({"id": sdoc_id}, {"$set": {
        "bank_txn_id": txn_id, "bank_session_id": session_id, "bank_txn_date": txn.get("txn_date"), "bank_linked_at": now,
        "bank_linked_by": user.get("email")}})
    await _recalculate_session(db, session_id)
    return {"ok": True, "txn_id": txn_id, "settlement_doc_id": sdoc_id, "match_ref": ref,
            "message": f"Mutasi {txn.get('txn_date')} ditautkan ke pencairan {st.get('settlement_id')}."}


# ═══════════════════════════════════════════════════════════════════
# GL ENTRIES LOOKUP (kompat lama) — kini per sesi/akun bank, bukan semua JE
# ═══════════════════════════════════════════════════════════════════

@router.get("/gl-entries")
async def get_gl_entries(request: Request, period: str = Query(...), session_id: Optional[str] = None,
                         gl_account_code: Optional[str] = None):
    await require_auth(request)
    _validate_period(period)
    db = get_db()
    if session_id:
        s = await _get_session(db, session_id)
    elif gl_account_code:
        s = {"id": "", "period": period, "gl_account_code": gl_account_code}
    else:
        raise HTTPException(400, "session_id atau gl_account_code wajib — GL sisi bank harus per akun rekening.")
    rows = await _bank_gl_lines(db, s)
    return {"period": period, "total": len(rows), "items": serialize_doc(rows)}


# ═══════════════════════════════════════════════════════════════════
# CSV FILE IMPORT
# ═══════════════════════════════════════════════════════════════════

def _parse_idr(val: str) -> float:
    val = (val or "").strip().replace(" ", "")
    for sym in ["Rp", "IDR", "rp"]:
        val = val.replace(sym, "").strip()
    negative = val.startswith("-") or (val.startswith("(") and val.endswith(")"))
    val = val.lstrip("-(").rstrip(")")
    if re.search(r",\d{1,2}$", val):
        val = val.replace(".", "").replace(",", ".")
    else:
        val = val.replace(".", "").replace(",", "")
    try:
        result = float(val)
    except ValueError:
        result = 0.0
    return -result if negative else result


def _parse_date(val: str) -> str:
    val = (val or "").strip()
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y", "%m/%d/%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d"]:
        try:
            return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.match(r"(\d{1,2})[\-/](\d{1,2})[\-/](\d{2,4})", val)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            pass
    return val


@router.post("/sessions/{session_id}/import-csv")
async def import_csv_file(session_id: str, request: Request, file: UploadFile = File(...)):
    """CSV rekening koran. Kolom Debit/Keluar = uang KELUAR, Kredit/Masuk = uang MASUK (konvensi bank);
    kolom nominal tunggal: positif = masuk, negatif = keluar."""
    await require_auth(request)
    db = get_db()
    await _get_session(db, session_id, writable=True)
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    sample = text[:2048]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        raise HTTPException(400, "File CSV kosong.")

    header_row = [h.strip().lower() for h in rows[0]]
    data_start = 1
    DATE_KEYS = ["tanggal", "date", "tgl", "transaction date", "posting date"]
    DESC_KEYS = ["keterangan", "description", "deskripsi", "uraian", "narasi", "trans description", "remark"]
    DEBIT_KEYS = ["debit", "pengeluaran", "keluar", "db", "withdrawal"]
    CREDIT_KEYS = ["credit", "kredit", "pemasukan", "masuk", "cr", "deposit"]
    AMT_KEYS = ["nominal", "amount", "jumlah", "nilai", "mutasi"]
    REF_KEYS = ["referensi", "reference", "ref", "no ref", "no. ref", "no.ref", "cheque no"]

    def _find_col(keys):
        for k in keys:
            for i, h in enumerate(header_row):
                if k in h:
                    return i
        return None

    col_date, col_desc = _find_col(DATE_KEYS), _find_col(DESC_KEYS)
    col_debit, col_credit = _find_col(DEBIT_KEYS), _find_col(CREDIT_KEYS)
    col_amt, col_ref = _find_col(AMT_KEYS), _find_col(REF_KEYS)
    if col_date is None:
        data_start, col_date, col_desc, col_amt = 0, 0, 1, 2

    docs, skipped = [], 0
    for row in rows[data_start:]:
        if not row or all(not c.strip() for c in row):
            continue

        def _get(idx):
            return row[idx].strip() if idx is not None and idx < len(row) else ""

        raw_date = _get(col_date)
        if not raw_date:
            skipped += 1
            continue
        if col_debit is not None and col_credit is not None:
            d_val, c_val = _parse_idr(_get(col_debit)), _parse_idr(_get(col_credit))
            if c_val and not d_val:
                amount, direction = abs(c_val), "in"
            elif d_val:
                amount, direction = abs(d_val), "out"
            else:
                skipped += 1
                continue
        elif col_amt is not None:
            raw_amt = _parse_idr(_get(col_amt))
            amount, direction = abs(raw_amt), ("out" if raw_amt < 0 else "in")
        else:
            skipped += 1
            continue
        if amount == 0:
            skipped += 1
            continue
        docs.append(_txn_doc(session_id, _parse_date(raw_date), _get(col_desc), _get(col_ref), amount, direction))
        if len(docs) >= 1000:
            break

    if docs:
        await db.bank_recon_txns.insert_many(docs)
        for d in docs:
            d.pop("_id", None)
    await _recalculate_session(db, session_id)
    return {"imported": len(docs), "skipped": skipped,
            "message": f"{len(docs)} transaksi berhasil diimpor{f', {skipped} baris dilewati' if skipped else ''}."}


# ═══════════════════════════════════════════════════════════════════
# APPROVE / SUMMARY / HELPER
# ═══════════════════════════════════════════════════════════════════

@router.post("/sessions/{session_id}/approve")
async def approve_session(session_id: str, request: Request):
    from routes.shared import require_perm
    user = await require_perm(request, 'finance.approve', 'finance.manage',
                              legacy_roles=('accounting', 'manager_keuangan', 'staff_keuangan', 'owner', 'admin', 'superadmin'),
                              message='Akses ditolak: Anda tidak berhak menyetujui rekonsiliasi bank.')
    db = get_db()
    s = await _get_session(db, session_id, writable=True)
    if s.get("unmatched_count", 0) > 0:
        raise HTTPException(400, f"Masih ada {s['unmatched_count']} mutasi bank yang belum dicocokkan. Selesaikan dulu sebelum approve.")
    summary = await _summary(db, s, await _bank_gl_lines(db, s))
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    if not summary["explained"] and not body.get("confirm_unexplained"):
        raise HTTPException(409, {
            "code": "unexplained_difference", "unexplained": summary["unexplained"],
            "message": f"Selisih Rp {summary['unexplained']:,.0f} belum terjelaskan (saldo GL disesuaikan "
                       f"{summary['adjusted_gl_balance']:,.0f} vs rekening koran {summary['statement_closing']:,.0f}). "
                       "Kirim confirm_unexplained=true untuk tetap menyetujui."})
    await db.bank_recon_sessions.update_one({"id": session_id}, {"$set": {
        "status": "approved", "approved_at": _now(), "approved_by": user["id"], "approved_by_name": user.get("name", ""),
        "approved_summary": summary, "approved_with_unexplained": not summary["explained"],
        "approval_note": (body.get("note") or "").strip()}})
    return serialize_doc(await db.bank_recon_sessions.find_one({"id": session_id}, {"_id": 0}))


@router.get("/summary")
async def get_summary(request: Request):
    await require_auth(request)
    db = get_db()
    total = await db.bank_recon_sessions.count_documents({})
    draft = await db.bank_recon_sessions.count_documents({"status": "draft"})
    in_progress = await db.bank_recon_sessions.count_documents({"status": "in_progress"})
    approved = await db.bank_recon_sessions.count_documents({"status": "approved"})
    agg = await db.bank_recon_sessions.aggregate([
        {"$match": {"status": {"$nin": ["approved"]}}},
        {"$group": {"_id": None, "total_unmatched": {"$sum": "$unmatched_count"}}}]).to_list(1)
    recent = await db.bank_recon_sessions.find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
    return {"total_sessions": total, "draft": draft, "in_progress": in_progress, "approved": approved,
            "total_unmatched": agg[0]["total_unmatched"] if agg else 0, "recent": serialize_doc(recent)}


async def _recalculate_session(db, session_id: str):
    total_txns = await db.bank_recon_txns.count_documents({"session_id": session_id})
    matched = await db.bank_recon_txns.count_documents({"session_id": session_id, "is_matched": True})
    amounts = await db.bank_recon_txns.aggregate([
        {"$match": {"session_id": session_id}},
        {"$group": {"_id": "$direction", "total": {"$sum": "$amount"}}}]).to_list(10)
    in_total = next((a["total"] for a in amounts if a["_id"] == "in"), 0)
    out_total = next((a["total"] for a in amounts if a["_id"] == "out"), 0)
    session = await db.bank_recon_sessions.find_one({"id": session_id}, {"_id": 0, "status": 1})
    current = (session or {}).get("status", "draft")
    next_status = "approved" if current == "approved" else ("in_progress" if total_txns > 0 else "draft")
    await db.bank_recon_sessions.update_one({"id": session_id}, {"$set": {
        "total_bank_txns": total_txns, "matched_count": matched, "unmatched_count": total_txns - matched,
        "debit_total": in_total, "credit_total": out_total, "in_total": in_total, "out_total": out_total,
        "difference": in_total - out_total, "is_balanced": (total_txns > 0 and total_txns == matched),
        "status": next_status, "updated_at": _now()}})
