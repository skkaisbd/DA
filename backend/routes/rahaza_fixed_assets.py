"""
CV. Dewi Aditya ERP — Fixed Asset & Depreciation (Session 11)

Endpoints (prefix /api/rahaza/finance):
  GET    /fixed-assets                   — list aset tetap
  POST   /fixed-assets                   — daftarkan aset baru
  GET    /fixed-assets/{id}              — detail + jadwal depresiasi
  PUT    /fixed-assets/{id}              — update
  POST   /fixed-assets/{id}/dispose      — disposal aset
  GET    /fixed-assets/{id}/schedule     — jadwal depresiasi lengkap
  POST   /fixed-assets/{id}/post-depr/{period} — posting depresiasi periode YYYY-MM
  GET    /fixed-assets/depreciation-due  — daftar aset perlu posting depresiasi
  GET    /fixed-assets-summary           — ringkasan portfolio (total cost, NBV, akumulasi)

Koleksi: rahaza_fixed_assets, rahaza_depr_schedules
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc
from routes.shared import get_pagination_params, paginated_response
from datetime import datetime, timezone, date
from dateutil.relativedelta import relativedelta
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza/finance", tags=["rahaza-fixed-assets"])

def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)

ASSET_CATEGORIES = ["tanah", "bangunan", "mesin", "kendaraan", "peralatan", "it", "furnitur", "lain-lain"]
DEPR_METHODS    = ["straight_line", "double_declining", "none", "manual"]  # Phase 8B: added "none" & "manual"


# ─── HELPER: generate depreciation schedule ────────────────────────────────

def _generate_schedule(asset: dict) -> list:
    """
    Generate monthly depreciation schedule for the asset.
    Returns list of {period, depr_amount, accumulated_depr, book_value_start, book_value_end}
    """
    cost       = float(asset.get("purchase_cost") or 0)
    residual   = float(asset.get("residual_value") or 0)
    useful_life = int(asset.get("useful_life_months") or 12)
    method      = asset.get("depreciation_method", "straight_line")
    start_date_str = asset.get("purchase_date") or date.today().isoformat()
    try:
        start_date = date.fromisoformat(start_date_str[:10])
    except ValueError:
        start_date = date.today()
    # Start depreciation from the month AFTER purchase (or first day of purchase month)
    depr_start = date(start_date.year, start_date.month, 1)
    depr_start + relativedelta(months=useful_life)

    schedule = []
    book_value = cost
    accumulated = 0.0
    if method == "straight_line":
        monthly_depr = round((cost - residual) / useful_life, 2) if useful_life > 0 else 0
        for i in range(useful_life):
            period_date = depr_start + relativedelta(months=i)
            period_str  = period_date.strftime("%Y-%m")
            bv_start    = round(book_value, 2)
            depr_amt    = min(monthly_depr, max(0, book_value - residual))
            depr_amt    = round(depr_amt, 2)
            accumulated = round(accumulated + depr_amt, 2)
            book_value  = round(book_value - depr_amt, 2)
            schedule.append({
                "period":          period_str,
                "book_value_start": bv_start,
                "depr_amount":     depr_amt,
                "accumulated_depr": accumulated,
                "book_value_end":  book_value,
            })
    elif method == "double_declining":
        rate = 2 / useful_life if useful_life > 0 else 0
        for i in range(useful_life):
            period_date = depr_start + relativedelta(months=i)
            period_str  = period_date.strftime("%Y-%m")
            bv_start    = round(book_value, 2)
            depr_amt    = round(book_value * rate / 12, 2)  # monthly rate
            if book_value - depr_amt < residual:
                depr_amt = max(0, round(book_value - residual, 2))
            accumulated = round(accumulated + depr_amt, 2)
            book_value  = round(book_value - depr_amt, 2)
            schedule.append({
                "period":          period_str,
                "book_value_start": bv_start,
                "depr_amount":     depr_amt,
                "accumulated_depr": accumulated,
                "book_value_end":  book_value,
            })
    return schedule


# ─── CRUD ENDPOINTS ──────────────────────────────────────────────────────────

@router.get("/fixed-assets")
async def list_fixed_assets(request: Request, category: Optional[str] = None,
                             status: Optional[str] = None, search: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {}
    if category:
        q["category"] = category
    if status:
        q["status"]   = status
    else:
        q["status"]   = {"$ne": "disposed"}  # default: exclude disposed
    if search:
        import re
        p = re.compile(re.escape(search), re.IGNORECASE)
        q["$or"] = [{"code": p}, {"name": p}, {"serial_number": p}]
    use_pagination = "page" in request.query_params
    if use_pagination:
        page, limit, skip = get_pagination_params(request, default_limit=50)
        total = await db.rahaza_fixed_assets.count_documents(q)
        rows = await db.rahaza_fixed_assets.find(q, {"_id": 0}).sort("purchase_date", -1).skip(skip).limit(limit).to_list(length=10000)
        # Compute current NBV for each
        for r in rows:
            await _enrich_nbv(db, r)
        return paginated_response(serialize_doc(rows), total, page, limit)
    rows = await db.rahaza_fixed_assets.find(q, {"_id": 0}).sort("purchase_date", -1).to_list(500)
    for r in rows:
        await _enrich_nbv(db, r)
    return serialize_doc(rows)


async def _enrich_nbv(db, asset: dict):
    """Add current NBV and accumulated depreciation to asset dict."""
    aid = asset.get("id", "")
    today = date.today().strftime("%Y-%m")
    # Sum all posted depreciation up to today
    pipe = [{"$match": {"asset_id": aid, "period": {"$lte": today}, "posted": True}},
            {"$group": {"_id": None, "total_depr": {"$sum": "$depr_amount"}}}]
    agg = await db.rahaza_depr_schedules.aggregate(pipe).to_list(1)
    accum_depr = round((agg[0]["total_depr"] if agg else 0), 2)
    cost = float(asset.get("purchase_cost") or 0)
    asset["accumulated_depreciation"] = accum_depr
    asset["book_value_current"]       = round(cost - accum_depr, 2)


@router.post("/fixed-assets")
async def create_fixed_asset(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Nama aset wajib diisi")
    code = (body.get("code") or "").strip()
    # SESI #27 — kode aset lewat SATU PINTU kebijakan penomoran (Otomatis/Manual).
    # DUA cacat sekaligus yang diperbaiki di sini:
    #   1. dulu kode WAJIB diketik staf tanpa satu pun aturan bentuk ⇒ "FA1",
    #      "asset-baru", "AC RUANG QC" hidup berdampingan dan tak bisa diurutkan;
    #   2. jalur kapitalisasi otomatis dari penerimaan barang (warehouse.py)
    #      memanggil generator dengan nama field `asset_code` padahal field
    #      dokumennya `code` ⇒ penyemaian counter membaca field yang salah.
    from core.doc_number_policy import issue_number
    code = await issue_number(db, "rahaza_fixed_assets.code", requested=code)
    if await db.rahaza_fixed_assets.find_one({"code": code}):
        raise HTTPException(409, f"Kode aset '{code}' sudah digunakan")
    cat = body.get("category", "peralatan")
    if cat not in ASSET_CATEGORIES:
        raise HTTPException(400, f"Kategori harus salah satu dari: {ASSET_CATEGORIES}")
    method = body.get("depreciation_method", "straight_line")
    if method not in DEPR_METHODS:
        raise HTTPException(400, f"Metode depresiasi: {DEPR_METHODS}")
    doc = {
        "id":                     _uid(),
        "code":                   code,
        "name":                   name,
        "category":               cat,
        "purchase_date":          body.get("purchase_date") or date.today().isoformat(),
        "purchase_cost":          float(body.get("purchase_cost") or 0),
        "residual_value":         float(body.get("residual_value") or 0),
        "useful_life_months":     int(body.get("useful_life_months") or 60),
        "depreciation_method":    method,
        "account_id_asset":       body.get("account_id_asset"),
        "account_id_accum_depr": body.get("account_id_accum_depr"),
        "account_id_depr_expense": body.get("account_id_depr_expense"),
        "location":               (body.get("location") or "").strip(),
        "supplier":               (body.get("supplier") or "").strip(),
        "serial_number":          (body.get("serial_number") or "").strip(),
        "notes":                  (body.get("notes") or "").strip(),
        "status":                 "active",
        "created_at":             _now(),
        "created_by":             user.get("email"),
        "disposed_at":            None,
        "disposal_notes":         None,
    }
    await db.rahaza_fixed_assets.insert_one(doc)
    # Auto-generate depreciation schedule
    schedule = _generate_schedule(doc)
    if schedule:
        depr_docs = []
        for s in schedule:
            depr_docs.append({
                "id":              _uid(),
                "asset_id":        doc["id"],
                "asset_code":      doc["code"],
                "period":          s["period"],
                "book_value_start":s["book_value_start"],
                "depr_amount":     s["depr_amount"],
                "accumulated_depr":s["accumulated_depr"],
                "book_value_end":  s["book_value_end"],
                "posted":          False,
                "journal_entry_id":None,
                "posted_at":       None,
            })
        if depr_docs:
            await db.rahaza_depr_schedules.insert_many(depr_docs)
    return serialize_doc(doc)


@router.get("/fixed-assets/depreciation-due")
async def depreciation_due(request: Request):
    """Aset yang jadwal depresiasinya belum diposting untuk periode ini."""
    await require_auth(request)
    db = get_db()
    cur_period = date.today().strftime("%Y-%m")
    due = await db.rahaza_depr_schedules.find(
        {"period": cur_period, "posted": False, "depr_amount": {"$gt": 0}},
        {"_id": 0}
    ).to_list(500)
    # Enrich with asset name
    asset_ids = list({d["asset_id"] for d in due})
    assets = {a["id"]: a for a in await db.rahaza_fixed_assets.find({"id": {"$in": asset_ids}}, {"_id": 0}).to_list(500)} if asset_ids else {}
    for d in due:
        a = assets.get(d["asset_id"]) or {}
        d["asset_name"]     = a.get("name", "")
        d["asset_category"] = a.get("category", "")
    return serialize_doc(due)


@router.get("/fixed-assets-summary")
async def fixed_assets_summary(request: Request):
    await require_auth(request)
    db = get_db()
    assets = await db.rahaza_fixed_assets.find({"status": {"$ne": "disposed"}}, {"_id": 0}).to_list(500)
    total_cost = round(sum(float(a.get("purchase_cost") or 0) for a in assets), 2)
    # Accumulated depreciation from all posted schedule entries
    pipe = [{"$match": {"posted": True}},
            {"$group": {"_id": None, "total": {"$sum": "$depr_amount"}}}]
    agg = await db.rahaza_depr_schedules.aggregate(pipe).to_list(1)
    total_accum = round((agg[0]["total"] if agg else 0), 2)
    nbv = round(total_cost - total_accum, 2)
    # Count due this month
    cur_period = date.today().strftime("%Y-%m")
    due_count = await db.rahaza_depr_schedules.count_documents({"period": cur_period, "posted": False, "depr_amount": {"$gt": 0}})
    by_category = {}
    for a in assets:
        cat = a.get("category", "lain-lain")
        if cat not in by_category:
            by_category[cat] = {"count": 0, "cost": 0}
        by_category[cat]["count"] += 1
        by_category[cat]["cost"]  += float(a.get("purchase_cost") or 0)
    return {
        "total_assets":           len(assets),
        "total_cost":             total_cost,
        "total_accumulated_depr": total_accum,
        "total_nbv":              nbv,
        "depr_due_this_month":    due_count,
        "by_category":            by_category,
    }


@router.get("/fixed-assets/depreciation-summary")
async def get_depreciation_summary(request: Request, period: Optional[str] = None):
    """
    Phase 8B: Summary depreciation per period atau all-time.
    IMPORTANT: This route must be BEFORE /{aid} to avoid route conflict.
    """
    await require_auth(request)
    db = get_db()
    if not period:
        period = date.today().strftime("%Y-%m")
    pipe = [
        {"$match": {"period": period, "posted": True}},
        {"$group": {"_id": None, "total_depr": {"$sum": "$depr_amount"}, "count": {"$sum": 1}}}
    ]
    agg = await db.rahaza_depr_schedules.aggregate(pipe).to_list(1)
    total_depr = round((agg[0]["total_depr"] if agg else 0), 2)
    count = (agg[0]["count"] if agg else 0)
    assets_active = await db.rahaza_fixed_assets.count_documents({"status": "active"})
    assets_disposed = await db.rahaza_fixed_assets.count_documents({"status": "disposed"})
    return {
        "period": period,
        "total_depreciation": total_depr,
        "assets_count": count,
        "assets_active": assets_active,
        "assets_disposed": assets_disposed,
    }


@router.get("/fixed-assets/{aid}")
async def get_fixed_asset(aid: str, request: Request):
    await require_auth(request)
    db = get_db()
    asset = await db.rahaza_fixed_assets.find_one({"id": aid}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan")
    await _enrich_nbv(db, asset)
    return serialize_doc(asset)


@router.put("/fixed-assets/{aid}")
async def update_fixed_asset(aid: str, request: Request):
    await require_auth(request)
    db = get_db()
    asset = await db.rahaza_fixed_assets.find_one({"id": aid}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan")
    if asset.get("status") == "disposed":
        raise HTTPException(409, "Aset sudah di-dispose")
    body = await request.json()
    allowed = ["name", "location", "supplier", "serial_number", "notes",
               "account_id_asset", "account_id_accum_depr", "account_id_depr_expense"]
    update = {k: body[k] for k in allowed if k in body}
    if update:
        update["updated_at"] = _now()
        await db.rahaza_fixed_assets.update_one({"id": aid}, {"$set": update})
    out = await db.rahaza_fixed_assets.find_one({"id": aid}, {"_id": 0})
    await _enrich_nbv(db, out)
    return serialize_doc(out)


@router.get("/fixed-assets/{aid}/schedule")
async def get_depr_schedule(aid: str, request: Request):
    await require_auth(request)
    db = get_db()
    rows = await db.rahaza_depr_schedules.find({"asset_id": aid}, {"_id": 0}).sort("period", 1).to_list(length=10000)
    return serialize_doc(rows)


@router.post("/fixed-assets/{aid}/post-depr/{period}")
async def post_depreciation(aid: str, period: str, request: Request):
    """
    Posting depresiasi untuk aset pada periode YYYY-MM.
    Membuat jurnal: Dr Depreciation Expense / Cr Accumulated Depreciation.
    """
    user = await require_auth(request)
    db = get_db()
    asset = await db.rahaza_fixed_assets.find_one({"id": aid}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan")
    if asset.get("status") == "disposed":
        raise HTTPException(409, "Aset sudah di-dispose")
    sched = await db.rahaza_depr_schedules.find_one({"asset_id": aid, "period": period}, {"_id": 0})
    if not sched:
        raise HTTPException(404, f"Jadwal depresiasi untuk periode {period} tidak ditemukan")
    if sched.get("posted"):
        raise HTTPException(409, f"Depresiasi periode {period} sudah diposting")
    depr_amt = float(sched.get("depr_amount") or 0)
    if depr_amt <= 0:
        await db.rahaza_depr_schedules.update_one({"asset_id": aid, "period": period},
            {"$set": {"posted": True, "posted_at": _now()}})
        return {"ok": True, "message": "Jumlah depresiasi 0, posting tanpa jurnal"}
    # Create journal entry if account IDs are configured
    je_id = None
    acc_exp   = asset.get("account_id_depr_expense")
    acc_accum = asset.get("account_id_accum_depr")
    if acc_exp and acc_accum:
        try:
            from routes.rahaza_posting import post_journal
            je_body = {
                "date": f"{period}-01",
                "description": f"Depresiasi {asset['name']} ({asset['code']}) - {period}",
                "reference": f"DEPR/{asset['code']}/{period}",
                "lines": [
                    {"account_id": acc_exp,   "debit": depr_amt, "credit": 0,        "description": f"Depreciation Expense — {asset['name']}"},
                    {"account_id": acc_accum, "debit": 0,        "credit": depr_amt, "description": f"Accumulated Depreciation — {asset['name']}"},
                ],
                "auto_post": True,
            }
            je_id_resp = await post_journal(db, je_body, user)
            je_id = je_id_resp.get("journal_id")
        except Exception as e:
            logger.warning(f"[fixed_assets] Gagal buat jurnal depresiasi: {e}")
    await db.rahaza_depr_schedules.update_one({"asset_id": aid, "period": period}, {"$set": {
        "posted": True,
        "posted_at": _now(),
        "journal_entry_id": je_id,
    }})
    return {"ok": True, "depr_amount": depr_amt, "period": period, "journal_entry_id": je_id}


@router.post("/fixed-assets/{aid}/dispose")
async def dispose_asset(aid: str, request: Request):
    """Disposal aset — tandai sebagai disposed."""
    user = await require_auth(request)
    db = get_db()
    asset = await db.rahaza_fixed_assets.find_one({"id": aid}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan")
    if asset.get("status") == "disposed":
        raise HTTPException(409, "Aset sudah di-dispose sebelumnya")
    body = await request.json()
    disposal_date  = body.get("disposal_date") or date.today().isoformat()
    disposal_value = float(body.get("disposal_value") or 0)
    disposal_notes = (body.get("notes") or "").strip()
    # Calculate NBV at disposal date
    await _enrich_nbv(db, asset)
    nbv = float(asset.get("book_value_current") or 0)
    gain_loss = round(disposal_value - nbv, 2)
    await db.rahaza_fixed_assets.update_one({"id": aid}, {"$set": {
        "status":        "disposed",
        "disposed_at":   _now(),
        "disposal_date": disposal_date,
        "disposal_value": disposal_value,
        "disposal_notes": disposal_notes,
        "disposal_gain_loss": gain_loss,
        "nbv_at_disposal":    nbv,
    }})
    # Cancel future schedule entries
    await db.rahaza_depr_schedules.update_many(
        {"asset_id": aid, "period": {"$gt": disposal_date[:7]}, "posted": False},
        {"$set": {"cancelled": True}}
    )
    
    # Phase 10A: Auto-post GL for asset disposal
    posting_result = None
    try:
        from routes.rahaza_posting import post_asset_disposal
        asset_refresh = await db.rahaza_fixed_assets.find_one({"id": aid}, {"_id": 0})
        posting_result = await post_asset_disposal(db, asset_refresh, user)
    except Exception as e:
        logger.exception("Asset disposal GL posting failed")
        posting_result = {"ok": False, "error": str(e)}
    
    return {"ok": True, "gain_loss": gain_loss, "nbv_at_disposal": nbv, "posting_result": posting_result}



# ══════════════════════════════════════════════════════════════════════════════
# PHASE 8B: BATCH DEPRECIATION
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/fixed-assets/run-batch-depreciation")
async def run_batch_depreciation(request: Request):
    """
    Phase 8B: Run batch depreciation untuk periode tertentu.
    
    Body:
    {
        "period": "2026-05",  // YYYY-MM
        "asset_ids": [],      // Optional: kosong = semua assets aktif
        "auto_post": true     // Auto-post ke GL
    }
    
    Returns: summary + list asset yang di-depreciate
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    
    period = body.get("period", date.today().strftime("%Y-%m"))
    asset_ids = body.get("asset_ids", [])
    auto_post = body.get("auto_post", True)
    
    # Validate period format
    try:
        datetime.strptime(period, "%Y-%m")
    except ValueError:
        raise HTTPException(400, "Invalid period format. Use YYYY-MM")
    
    # Build query
    query = {"status": "active"}
    if asset_ids:
        query["id"] = {"$in": asset_ids}
    
    # Exclude assets dengan depreciation_method = "none" atau "manual"
    query["depreciation_method"] = {"$nin": ["none", "manual"]}
    
    assets = await db.rahaza_fixed_assets.find(query, {"_id": 0}).to_list(1000)
    
    if not assets:
        return {
            "ok": True,
            "message": "Tidak ada asset yang perlu di-depreciate untuk periode ini",
            "period": period,
            "assets_processed": 0,
            "total_depreciation": 0,
            "results": []
        }
    
    results = []
    total_depreciation = 0
    posted_count = 0
    
    for asset in assets:
        # Generate schedule if not exists
        asset_id = asset["id"]
        schedule = _generate_schedule(asset)
        
        # Find schedule entry for this period
        period_entry = next((s for s in schedule if s["period"] == period), None)
        
        if not period_entry:
            # Period tidak ada dalam schedule (sudah lewat useful life)
            results.append({
                "asset_id": asset_id,
                "asset_code": asset.get("code"),
                "asset_name": asset.get("name"),
                "status": "skipped",
                "reason": "Period tidak ada dalam schedule (asset sudah fully depreciated)",
                "depr_amount": 0,
            })
            continue
        
        depr_amount = period_entry.get("depr_amount", 0)
        if depr_amount <= 0:
            results.append({
                "asset_id": asset_id,
                "asset_code": asset.get("code"),
                "asset_name": asset.get("name"),
                "status": "skipped",
                "reason": "Depreciation amount = 0",
                "depr_amount": 0,
            })
            continue
        
        # Check if already posted
        existing_schedule = await db.rahaza_depr_schedules.find_one({
            "asset_id": asset_id,
            "period": period,
            "posted": True
        })
        
        if existing_schedule:
            results.append({
                "asset_id": asset_id,
                "asset_code": asset.get("code"),
                "asset_name": asset.get("name"),
                "status": "already_posted",
                "reason": f"Already posted on {existing_schedule.get('posted_at', 'N/A')}",
                "depr_amount": depr_amount,
                "je_number": existing_schedule.get("je_number"),
            })
            total_depreciation += depr_amount
            posted_count += 1
            continue
        
        # Create or update schedule entry
        schedule_id = _uid()
        schedule_doc = {
            "id": schedule_id,
            "asset_id": asset_id,
            "asset_code": asset.get("code"),
            "asset_name": asset.get("name"),
            "period": period,
            "book_value_start": period_entry.get("book_value_start", 0),
            "depr_amount": depr_amount,
            "accumulated_depr": period_entry.get("accumulated_depr", 0),
            "book_value_end": period_entry.get("book_value_end", 0),
            "posted": False,
            "created_at": _now(),
        }
        
        # Upsert schedule
        await db.rahaza_depr_schedules.update_one(
            {"asset_id": asset_id, "period": period},
            {"$setOnInsert": schedule_doc},
            upsert=True
        )
        
        # Auto-post GL if requested
        posting_result = None
        if auto_post:
            try:
                from routes.rahaza_posting import post_depreciation
                schedule_refresh = await db.rahaza_depr_schedules.find_one({"asset_id": asset_id, "period": period}, {"_id": 0})
                posting_result = await post_depreciation(db, schedule_refresh, asset, user)
                
                if posting_result.get("ok"):
                    # Mark as posted
                    await db.rahaza_depr_schedules.update_one(
                        {"asset_id": asset_id, "period": period},
                        {"$set": {
                            "posted": True,
                            "posted_at": _now(),
                            "posted_by": user.get("id"),
                            "je_id": posting_result.get("je_id"),
                            "je_number": posting_result.get("je_number"),
                        }}
                    )
                    posted_count += 1
                    total_depreciation += depr_amount
                    
                    results.append({
                        "asset_id": asset_id,
                        "asset_code": asset.get("code"),
                        "asset_name": asset.get("name"),
                        "status": "posted",
                        "depr_amount": depr_amount,
                        "je_number": posting_result.get("je_number"),
                    })
                else:
                    results.append({
                        "asset_id": asset_id,
                        "asset_code": asset.get("code"),
                        "asset_name": asset.get("name"),
                        "status": "error",
                        "reason": posting_result.get("error", "Unknown error"),
                        "depr_amount": depr_amount,
                    })
            except Exception as e:
                logger.exception(f"Failed to post depreciation for asset {asset_id}")
                results.append({
                    "asset_id": asset_id,
                    "asset_code": asset.get("code"),
                    "asset_name": asset.get("name"),
                    "status": "error",
                    "reason": str(e),
                    "depr_amount": depr_amount,
                })
        else:
            # Schedule created but not posted
            results.append({
                "asset_id": asset_id,
                "asset_code": asset.get("code"),
                "asset_name": asset.get("name"),
                "status": "scheduled",
                "depr_amount": depr_amount,
            })
            total_depreciation += depr_amount
    
    from auth import log_activity
    await log_activity(
        user.get("id", "system"),
        user.get("name", "system"),
        "run_batch_depreciation",
        "fixed_assets",
        f"Batch depreciation {period}: {len(assets)} assets, {posted_count} posted, total Rp {total_depreciation:,.0f}"
    )
    
    return {
        "ok": True,
        "message": f"Batch depreciation completed for period {period}",
        "period": period,
        "assets_processed": len(assets),
        "posted_count": posted_count,
        "total_depreciation": round(total_depreciation, 2),
        "results": results,
    }


# NOTE: GET /fixed-assets/depreciation-summary is defined above (before /{aid}) to avoid route conflict.
