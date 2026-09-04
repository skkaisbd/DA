"""
PT Rahaza — Phase F1 Accounting Core
Journal Entries & General Ledger (double-entry)

Collections:
  rahaza_journal_entries  — header (id, je_number, date, memo, source_module, source_ref, status, lines[], totals, created_by, posted_at, voided_at)
  rahaza_journal_lines    — flattened lines for GL query (optional: but we ALSO write lines for fast trial balance aggregation)

Status: draft → posted → voided
"""
from fastapi import APIRouter, Request, HTTPException, Query, Depends
from routes.shared import require_portal_dep
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from utils.counters import gen_prefixed_number  # noqa: F401  (dipakai jalur lain)
from core.doc_number_policy import issue_number
from pymongo.errors import DuplicateKeyError
import uuid
from datetime import datetime, timezone, date
from typing import Optional

router = APIRouter(prefix="/api/rahaza/journals", tags=["rahaza-journals"],
                   dependencies=[Depends(require_portal_dep("finance"))])  # RBAC: portal finance (BUG-RBAC-1)

JE_STATUS = ["draft", "posted", "voided"]
# SESI #19 — kunci kebijakan penomoran Jurnal Umum (registry `data/doc_number_registry.py`).
JE_DOCNUM_KEY = "rahaza_journal_entries.je_number"


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


async def _require_fin(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "admin", "owner", "accounting", "finance", "manager"):
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "finance.manage" in perms:
        return user
    raise HTTPException(403, "Forbidden: butuh permission finance.")


async def _gen_je_number(db, d: date, requested: str = "") -> str:
    """Nomor jurnal lewat SATU PINTU kebijakan penomoran (SESI #19).

    `d` tidak lagi dipakai untuk menyusun awalan (format tanggalnya diambil dari
    setelan owner, kalender WIB — lihat `utils.counters.render_format`), tetapi tetap
    ada di tanda tangan supaya pemanggil lama tidak perlu diubah.
    """
    return await issue_number(db, JE_DOCNUM_KEY, requested=requested)


async def _validate_lines(db, lines: list) -> tuple[float, float]:
    """Validate each line: account exists + not group, debit/credit numeric, sum balanced."""
    if not isinstance(lines, list) or len(lines) < 2:
        raise HTTPException(400, "Jurnal harus minimal 2 baris (Debit + Credit).")
    if not all(isinstance(ln, dict) for ln in lines):
        raise HTTPException(400, "Setiap baris jurnal harus berupa objek {account_code, debit, credit}.")
    total_d = 0.0
    total_c = 0.0
    # Batch fetch all referenced CoA accounts in single query
    codes_in_lines = list({(ln.get("account_code") or "").strip()
                            for ln in lines if (ln.get("account_code") or "").strip()})
    coa_map = {}
    if codes_in_lines:
        async for d in db.rahaza_coa_accounts.find(
            {"code": {"$in": codes_in_lines}, "active": True}, {"_id": 0}
        ):
            coa_map[d["code"]] = d
    for i, ln in enumerate(lines):
        code = (ln.get("account_code") or "").strip()
        if not code:
            raise HTTPException(400, f"Baris #{i+1}: account_code wajib diisi.")
        acc = coa_map.get(code)
        if not acc:
            raise HTTPException(400, f"Baris #{i+1}: akun '{code}' tidak ditemukan atau non-aktif.")
        if acc.get("is_group"):
            raise HTTPException(400, f"Baris #{i+1}: akun '{code}' adalah header (non-postable). Pilih akun leaf.")
        try:
            d = float(ln.get("debit") or 0)
            c = float(ln.get("credit") or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, f"Baris #{i+1}: debit/credit harus berupa angka.")
        if d < 0 or c < 0:
            raise HTTPException(400, f"Baris #{i+1}: debit/credit tidak boleh negatif.")
        if d > 0 and c > 0:
            raise HTTPException(400, f"Baris #{i+1}: satu baris hanya boleh debit ATAU credit.")
        if d == 0 and c == 0:
            raise HTTPException(400, f"Baris #{i+1}: debit atau credit harus > 0.")
        ln["account_code"] = code
        ln["account_name"] = acc.get("name")
        ln["account_type"] = acc.get("type")
        ln["debit"] = round(d, 2)
        ln["credit"] = round(c, 2)
        total_d += d
        total_c += c
    if round(total_d, 2) != round(total_c, 2):
        raise HTTPException(400, f"Jurnal tidak seimbang. Total Debit {total_d} ≠ Credit {total_c}")
    return round(total_d, 2), round(total_c, 2)


async def _check_period_open(db, d: date):
    """Check if period (month) for given date is open. If closed/locked, block posting."""
    ym = d.strftime("%Y-%m")
    period = await db.rahaza_periods.find_one({"period_code": ym})
    if period and period.get("status") in ("closed", "locked"):
        raise HTTPException(423, f"Periode {ym} sudah {period['status']}. Posting ditolak.")


# ─────────────── CREATE / LIST / GET / POST / VOID ────────────────────────
@router.post("")
async def create_journal(request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    je_date_str = (body.get("date") or "").strip() or date.today().isoformat()
    try:
        je_date = date.fromisoformat(je_date_str)
    except ValueError:
        raise HTTPException(400, "Format tanggal harus YYYY-MM-DD.")
    memo = (body.get("memo") or "").strip()
    lines = body.get("lines") or []
    total_d, total_c = await _validate_lines(db, lines)
    post_now = bool(body.get("post", False))
    if post_now:
        await _check_period_open(db, je_date)

    je_number = await _gen_je_number(db, je_date, (body.get("je_number") or "").strip())
    je_id = _uid()
    doc = {
        "id": je_id,
        "je_number": je_number,
        "date": je_date.isoformat(),
        "memo": memo,
        "source_module": body.get("source_module") or "manual",
        "source_ref": body.get("source_ref") or None,
        "status": "posted" if post_now else "draft",
        "total_debit": total_d,
        "total_credit": total_c,
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "posted_at": _now() if post_now else None,
        "posted_by": user["id"] if post_now else None,
        "voided_at": None,
        "voided_by": None,
    }
    # embed lines for single-doc fetch
    doc["lines"] = [
        {
            "line_id": _uid(),
            "account_code": ln["account_code"],
            "account_name": ln["account_name"],
            "account_type": ln["account_type"],
            "debit": ln["debit"],
            "credit": ln["credit"],
            "description": (ln.get("description") or "").strip(),
            "cost_center_id": ln.get("cost_center_id") or None,
        }
        for ln in lines
    ]
    # RC-5 safety-net: retry with a fresh number if a concurrent insert wins the unique index.
    # SESI #19 — pada mode MANUAL nomornya DIKETIK orang: mengganti nomornya diam-diam
    # dengan nomor lain adalah kebohongan (pemakai menyimpan JE-…-0007 lalu menemukan
    # nomor lain di arsip). Karena itu nomor ketikan yang bentrok dijawab 409, dan
    # retry otomatis hanya berlaku untuk mode OTOMATIS.
    diketik = bool((body.get("je_number") or "").strip())
    for _attempt in range(6):
        try:
            await db.rahaza_journal_entries.insert_one(doc)
            break
        except DuplicateKeyError:
            doc.pop("_id", None)
            if diketik:
                raise HTTPException(
                    409, f"Nomor jurnal '{doc['je_number']}' sudah dipakai dokumen lain.")
            doc["je_number"] = await _gen_je_number(db, je_date)
    else:
        raise HTTPException(409, "Nomor jurnal bentrok berulang — silakan coba lagi.")
    je_number = doc["je_number"]

    # mirror lines to rahaza_journal_lines for fast GL/trial balance
    if post_now:
        await _mirror_lines(db, doc)

    await log_activity(user["id"], user.get("name", ""), "create_journal", "journal", je_number)
    return serialize_doc(doc)


async def _mirror_lines(db, je_doc: dict):
    """Denormalize posted lines into rahaza_journal_lines for fast aggregation."""
    rows = []
    for ln in je_doc.get("lines", []):
        rows.append({
            "id": _uid(),
            "je_id": je_doc["id"],
            "je_number": je_doc["je_number"],
            "date": je_doc["date"],
            "period_code": je_doc["date"][:7],
            "account_code": ln["account_code"],
            "account_name": ln["account_name"],
            "account_type": ln["account_type"],
            "debit": ln["debit"],
            "credit": ln["credit"],
            "description": ln.get("description", ""),
            "cost_center_id": ln.get("cost_center_id"),
            "source_module": je_doc.get("source_module"),
            "source_ref": je_doc.get("source_ref"),
            "created_at": _now(),
        })
    if rows:
        await db.rahaza_journal_lines.insert_many(rows)


async def _unmirror_lines(db, je_id: str):
    await db.rahaza_journal_lines.delete_many({"je_id": je_id})


@router.get("")
async def list_journals(
    request: Request,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 200,
):
    await require_auth(request)
    db = get_db()
    q = {}
    if from_date and to_date:
        q["date"] = {"$gte": from_date, "$lte": to_date}
    if status:
        q["status"] = status
    if source:
        q["source_module"] = source
    rows = await db.rahaza_journal_entries.find(q, {"_id": 0}).sort([("date", -1), ("je_number", -1)]).limit(limit).to_list(500)
    return serialize_doc(rows)


@router.get("/{je_id}")
async def get_journal(je_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    je = await db.rahaza_journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not je:
        raise HTTPException(404, "Jurnal tidak ditemukan.")
    return serialize_doc(je)


@router.post("/{je_id}/post")
async def post_journal(je_id: str, request: Request):
    user = await _require_fin(request)
    db = get_db()
    je = await db.rahaza_journal_entries.find_one({"id": je_id})
    if not je:
        raise HTTPException(404, "Jurnal tidak ditemukan.")
    if je["status"] != "draft":
        raise HTTPException(400, f"Hanya draft yang bisa di-post. Status sekarang: {je['status']}")
    je_date = date.fromisoformat(je["date"])
    await _check_period_open(db, je_date)
    await db.rahaza_journal_entries.update_one(
        {"id": je_id},
        {"$set": {"status": "posted", "posted_at": _now(), "posted_by": user["id"], "updated_at": _now()}},
    )
    je["status"] = "posted"
    await _mirror_lines(db, je)
    await log_activity(user["id"], user.get("name", ""), "post_journal", "journal", je["je_number"])
    return {"ok": True, "je_number": je["je_number"]}


@router.post("/{je_id}/void")
async def void_journal(je_id: str, request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    reason = (body.get("reason") or "").strip() if isinstance(body, dict) else ""
    je = await db.rahaza_journal_entries.find_one({"id": je_id})
    if not je:
        raise HTTPException(404, "Jurnal tidak ditemukan.")
    if je["status"] == "voided":
        raise HTTPException(400, "Jurnal sudah voided.")
    # period check for posted journals (cannot void in locked period)
    if je["status"] == "posted":
        await _check_period_open(db, date.fromisoformat(je["date"]))
    await db.rahaza_journal_entries.update_one(
        {"id": je_id},
        {"$set": {
            "status": "voided",
            "voided_at": _now(),
            "voided_by": user["id"],
            "void_reason": reason,
            "updated_at": _now(),
        }},
    )
    await _unmirror_lines(db, je_id)
    await log_activity(user["id"], user.get("name", ""), "void_journal", "journal", je["je_number"])
    return {"ok": True, "je_number": je["je_number"]}


@router.delete("/{je_id}")
async def delete_draft(je_id: str, request: Request):
    user = await _require_fin(request)
    db = get_db()
    je = await db.rahaza_journal_entries.find_one({"id": je_id})
    if not je:
        raise HTTPException(404, "Jurnal tidak ditemukan.")
    if je["status"] != "draft":
        raise HTTPException(400, "Hanya draft yang bisa di-delete.")
    await db.rahaza_journal_entries.delete_one({"id": je_id})
    await log_activity(user["id"], user.get("name", ""), "delete_draft_journal", "journal", je["je_number"])
    return {"ok": True}
