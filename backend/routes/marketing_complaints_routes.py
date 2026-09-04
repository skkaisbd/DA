"""
Complaints Management Module — Backend Routes
Phase 2 Week 5: Complaint tracking dengan SLA + AI classification
"""
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel
from database import get_db
from auth import require_auth
# F6 (sesi #9) — ringkasan & daftar WAJIB berlingkup toko.
from core import marketing_account_scope as _scope
from utils.query_guards import q_date
from ai_llm import LlmChat, UserMessage
import json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/complaints", tags=["marketing-complaints"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

COMPLAINT_CATEGORIES = [
    "missing_item", "wrong_item", "quality_defect",
    "size_mismatch", "late_delivery", "packaging_damage",
    "seller_unresponsive", "description_mismatch", "other"
]
COMPLAINT_STATUSES   = ["open", "in_progress", "resolved", "closed"]
SLA_HOURS            = 48   # 2 business days in hours

CATEGORY_LABELS_ID = {
    "missing_item":        "Produk Kurang",
    "wrong_item":          "Produk Salah",
    "quality_defect":      "Cacat/Rusak",
    "size_mismatch":       "Ukuran Salah",
    "late_delivery":       "Pengiriman Lambat",
    "packaging_damage":    "Kemasan Rusak",
    "seller_unresponsive": "Penjual Tidak Responsif",
    "description_mismatch":"Tidak Sesuai Deskripsi",
    "other":               "Lainnya",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)

def serialize(obj):
    if isinstance(obj, list):
        return [serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items() if k != "_id"}
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj

def _get_user(r: Request) -> dict:
    return getattr(r.state, "user", {}) or {}

def _compute_sla(complaint_date: datetime, status: str) -> dict:
    """Compute SLA due date and status."""
    # Ensure complaint_date is timezone-aware
    if complaint_date.tzinfo is None:
        complaint_date = complaint_date.replace(tzinfo=timezone.utc)
    
    sla_due = complaint_date + timedelta(hours=SLA_HOURS)
    now = _now()
    if status in ["resolved", "closed"]:
        return {"sla_due_at": sla_due, "sla_status": "resolved"}
    if now > sla_due:
        return {"sla_due_at": sla_due, "sla_status": "overdue"}
    hours_left = (sla_due - now).total_seconds() / 3600
    if hours_left < 8:
        return {"sla_due_at": sla_due, "sla_status": "at_risk"}
    return {"sla_due_at": sla_due, "sla_status": "on_time"}


# ── Seed Demo Data ─────────────────────────────────────────────────────────────

async def seed_complaints_if_empty():
    db = get_db()
    if await db.marketing_complaints.count_documents({}) > 0:
        return

    import random

    products = [
        "Gamis Busui Friendly DA-001", "Celana Kulot DA-005",
        "Blouse Batik Modern DA-020",  "Gamis Syari Daluna DL-001",
        "Rok Plisket Premium DL-010",  "Kerudung Segiempat DA-010",
    ]

    # Gunakan platform accounts nyata jika ada
    real_accounts = await db.marketing_platform_accounts.find(
        {"status": "active"}, {"_id": 0, "id": 1, "account_name": 1, "platform": 1}
    ).to_list(50)

    if real_accounts:
        # Build seed accounts dari platform accounts nyata
        seed_accounts = [(a["id"], a["account_name"], a["platform"]) for a in real_accounts]
    else:
        seed_accounts = [
            (None, "DA Official Shopee",   "shopee"),
            (None, "DA Shopee Premium",    "shopee"),
            (None, "Daluna TikTok Shop",   "tiktok"),
        ]
    couriers  = ["J&T Express", "SiCepat", "JNE", "AnterAja", "Ninja Express"]
    names     = ["Siti Rahayu", "Zahra Wulandari", "Dewi Santoso", "Rina Mardiani",
                 "Fitri Amalia", "Nisa Kurniawan", "Anisa Rahman", "Eka Puspita"]
    texts_per_cat = {
        "missing_item":        ["Kak barangnya cuma dateng 1 padahal beli 2", "Ada yang kurang 1 pcs dari total 3 pcs yang dipesan", "Pesanan tidak lengkap"],
        "wrong_item":          ["Dapat warna biru muda tapi pesan yang hitam", "Produk yang datang beda dengan yang dipesan", "Kirimnya ukuran M tapi pesan XL"],
        "quality_defect":      ["Jahitannya sudah lepas dari kotak", "Kainnya tipis banget tidak sesuai foto", "Ada bolong di bagian samping"],
        "size_mismatch":       ["Size chart-nya tidak akurat", "XL terasa kecil banget", "Ukuran M ternyata lebih kecil dari biasanya"],
        "late_delivery":       ["Sudah 1 minggu belum sampai", "Lacaknya stuck di hub sudah 5 hari", "Minta update tracking dong kak"],
        "packaging_damage":    ["Kemasannya sobek waktu sampai", "Plastik pembungkus rusak", "Kotak sudah penyok"],
        "seller_unresponsive": ["Chat sudah 2 hari tidak dibalas", "Komplain tidak ada respon sama sekali", "Tolong segera ditangani"],
        "description_mismatch":["Foto di toko beda dengan barang asli", "Warnanya tidak sesuai foto", "Materialnya beda dengan deskripsi"],
        "other":               ["Minta refund", "Ingin tukar ukuran", "Ada pertanyaan tentang perawatan kain"],
    }
    resolutions = [
        "Sudah konfirmasi ke gudang, sedang diproses",
        "Barang pengganti sudah dikirim",
        "Refund sudah diproses dalam 1-3 hari kerja",
        "Sedang menunggu konfirmasi dari ekspedisi",
        ""
    ]
    response_templates = {
        "missing_item":    "Halo kak, mohon maaf atas ketidaknyamanannya. Tim kami sedang memproses pengiriman kekurangan produk. Mohon ditunggu ya 🙏",
        "wrong_item":      "Halo kak, mohon maaf ada kesalahan pengiriman. Kami akan kirim produk yang benar segera setelah produk salah kembali ke kami.",
        "quality_defect":  "Halo kak, mohon maaf produk tidak sesuai standar kami. Kami akan proses penggantian atau refund sesuai kebijakan toko.",
        "size_mismatch":   "Halo kak, mohon maaf ukurannya tidak sesuai. Silakan proses retur dan kami bantu tukar dengan ukuran yang tepat.",
        "late_delivery":   "Halo kak, maaf atas keterlambatannya. Kami sudah koordinasi dengan pihak ekspedisi untuk mempercepat pengiriman.",
        "packaging_damage":"Halo kak, mohon maaf kemasannya rusak dalam perjalanan. Silakan cek apakah isi produk masih baik, jika tidak kami proses klaim.",
        "seller_unresponsive":"Halo kak, mohon maaf response kami terlambat. Tim CS kami siap membantu sekarang.",
        "description_mismatch":"Halo kak, mohon maaf produk tidak sesuai ekspektasi. Kami akan tinjau deskripsi dan proses retur jika diperlukan.",
        "other":           "Halo kak, terima kasih sudah menghubungi kami. Tim kami akan segera membantu."
    }

    base_date = _now() - timedelta(days=14)
    complaints = []
    statuses_weighted = (["open"] * 8 + ["in_progress"] * 10 + ["resolved"] * 8 + ["closed"] * 4)
    cats_weighted = (
        ["missing_item"] * 8 + ["wrong_item"] * 6 + ["quality_defect"] * 5 +
        ["size_mismatch"] * 5 + ["late_delivery"] * 4 + ["packaging_damage"] * 3 +
        ["seller_unresponsive"] * 3 + ["description_mismatch"] * 3 + ["other"] * 3
    )

    for i in range(40):
        cat      = random.choice(cats_weighted)
        status   = random.choice(statuses_weighted)
        cdate    = base_date + timedelta(hours=random.randint(0, 14 * 24))
        acc_id, account, platform = random.choice(seed_accounts)
        sev_map  = {"missing_item": "high", "wrong_item": "high", "quality_defect": "medium",
                    "size_mismatch": "medium", "late_delivery": "medium", "packaging_damage": "low",
                    "seller_unresponsive": "critical", "description_mismatch": "low", "other": "low"}
        sla_info = _compute_sla(cdate, status)

        price = random.choice([45000, 75000, 85000, 98000, 110000, 125000])
        orders = [{"order_id": f"{platform.upper()[:3]}-2026050{i+1:03d}",
                   "qty": random.randint(1, 3),
                   "price": price,
                   "courier": random.choice(couriers)}]

        notes = []
        if status in ["in_progress", "resolved", "closed"]:
            notes.append({
                "id":       str(uuid.uuid4()),
                "text":     random.choice(resolutions),
                "author":   "cs@garment.com",
                "added_at": (cdate + timedelta(hours=random.randint(2, 24))).isoformat()
            })

        complaints.append({
            "id":               str(uuid.uuid4()),
            "complaint_number": f"KOMP-2026-{i+1:04d}",
            "platform":         platform,
            "account_id":       acc_id,
            "account_name":     account,
            "customer_name":    random.choice(names),
            "product_name":     random.choice(products),
            "price":            price,
            "complaint_date":   cdate,
            "complaint_text":   random.choice(texts_per_cat[cat]),
            "category":         cat,
            "category_label":   CATEGORY_LABELS_ID[cat],
            "severity":         sev_map.get(cat, "medium"),
            "status":           status,
            "sla_due_at":       sla_info["sla_due_at"],
            "sla_status":       sla_info["sla_status"],
            "orders":           orders,
            "ai_confidence":    round(random.uniform(0.78, 0.97), 2),
            "response_template":response_templates[cat],
            "resolution_text":  random.choice(resolutions) if status in ["resolved", "closed"] else "",
            "notes":            notes,
            "_source_type":     "complaints",
            "_import_session_id": "seed-demo",
            "created_at":       cdate,
            "updated_at":       cdate,
        })

    if complaints:
        await db.marketing_complaints.insert_many(complaints)
        # Create indexes safely (skip if exists)
        try:
            await db.marketing_complaints.create_index("id", unique=True, sparse=True)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        try:
            await db.marketing_complaints.create_index("status")
            await db.marketing_complaints.create_index("sla_status")
            await db.marketing_complaints.create_index("category")
            await db.marketing_complaints.create_index("complaint_date")
            await db.marketing_complaints.create_index("platform")
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        logger.info(f"[seed] Inserted {len(complaints)} demo complaints")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/summary")
async def complaints_summary(request: Request):
    user = await require_auth(request)
    db = get_db()
    await seed_complaints_if_empty()
    # F6 (sesi #9) — ringkasan komplain WAJIB berlingkup toko.
    _s = await _scope.scope_filter(db, user, None)

    # Refresh SLA statuses
    all_open = await db.marketing_complaints.find(
        {**_s, "status": {"$nin": ["resolved", "closed"]}},
        {"_id": 0, "id": 1, "complaint_date": 1, "status": 1}
    ).to_list(500)
    for c in all_open:
        sla_info = _compute_sla(c["complaint_date"], c["status"])
        await db.marketing_complaints.update_one(
            {"id": c["id"]}, {"$set": {"sla_status": sla_info["sla_status"]}}
        )

    # Aggregations — SEMUA memakai penyaring lingkup toko `_s` (F6). Kalau satu
    # pipeline saja lupa memakainya, angka "total" akan berbeda dari isi tabel
    # dan staf akan melihat komplain toko lain di pecahan kategori/platform.
    _match = [{"$match": _s}] if _s else []
    pipeline_status = _match + [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    pipeline_sla    = _match + [{"$group": {"_id": "$sla_status", "count": {"$sum": 1}}}]
    pipeline_cat    = _match + [{"$group": {"_id": "$category",   "count": {"$sum": 1}}}]
    pipeline_plat   = _match + [{"$group": {"_id": "$platform",   "count": {"$sum": 1}}}]
    pipeline_sev    = _match + [{"$group": {"_id": "$severity",   "count": {"$sum": 1}}}]

    by_status  = {}
    by_sla     = {}
    by_cat     = {}
    by_platform= {}
    by_severity= {}

    async for doc in db.marketing_complaints.aggregate(pipeline_status):
        by_status[doc["_id"]]   = doc["count"]
    async for doc in db.marketing_complaints.aggregate(pipeline_sla):
        by_sla[doc["_id"]]      = doc["count"]
    async for doc in db.marketing_complaints.aggregate(pipeline_cat):
        by_cat[doc["_id"]]      = doc["count"]
    async for doc in db.marketing_complaints.aggregate(pipeline_plat):
        by_platform[doc["_id"]] = doc["count"]
    async for doc in db.marketing_complaints.aggregate(pipeline_sev):
        by_severity[doc["_id"]] = doc["count"]

    total       = sum(by_status.values())
    overdue     = by_sla.get("overdue", 0)
    at_risk     = by_sla.get("at_risk",  0)
    resolved    = by_status.get("resolved", 0) + by_status.get("closed", 0)
    resolve_rate= round(resolved / total * 100, 1) if total > 0 else 0

    return {
        "total":          total,
        "overdue":        overdue,
        "at_risk":        at_risk,
        "resolved":       resolved,
        "resolve_rate":   resolve_rate,
        "by_status":      by_status,
        "by_sla":         by_sla,
        "by_category":    by_cat,
        "by_platform":    by_platform,
        "by_severity":    by_severity,
    }


@router.get("")
async def list_complaints(
    request: Request,
    platform:    Optional[str] = Query(None),
    status:      Optional[str] = Query(None),
    sla_status:  Optional[str] = Query(None),
    category:    Optional[str] = Query(None),
    severity:    Optional[str] = Query(None),
    date_from:   Optional[str] = Query(None),
    date_to:     Optional[str] = Query(None),
    search:      Optional[str] = Query(None),
    account_id:  Optional[str] = Query(None),
    page:        int           = Query(1, ge=1),
    page_size:   int           = Query(25, le=100),
    sort_by:     str           = Query("complaint_date"),
    sort_dir:    int           = Query(-1)
):
    user = await require_auth(request)
    db = get_db()
    await seed_complaints_if_empty()

    q: dict = await _scope.scope_filter(db, user, None)
    if platform:
        q["platform"]   = platform
    if status:
        q["status"]     = status
    if sla_status:
        q["sla_status"] = sla_status
    if category:
        q["category"]   = category
    if severity:
        q["severity"]   = severity
    if account_id:
        q["account_id"] = account_id
    if date_from or date_to:
        q["complaint_date"] = {}
        if date_from:
            # BUG-R11-A: validasi dulu — tanggal sampah dulu bikin HTTP 500
            q["complaint_date"]["$gte"] = datetime.fromisoformat(
                q_date(date_from, name="date_from").isoformat()
            )
        if date_to:
            q["complaint_date"]["$lte"] = datetime.fromisoformat(
                q_date(date_to, name="date_to").isoformat() + "T23:59:59"
            )
    if search:
        q["$or"] = [
            {"complaint_number":{"$regex": search, "$options": "i"}},
            {"complaint_text":  {"$regex": search, "$options": "i"}},
            {"product_name":    {"$regex": search, "$options": "i"}},
            {"customer_name":   {"$regex": search, "$options": "i"}},
        ]

    total = await db.marketing_complaints.count_documents(q)
    items = await db.marketing_complaints.find(
        q, {"_id": 0}
    ).sort(sort_by, sort_dir).skip((page - 1) * page_size).limit(page_size).to_list(500)

    # Recompute SLA on-the-fly
    for c in items:
        if c.get("status") not in ["resolved", "closed"] and c.get("complaint_date"):
            sla = _compute_sla(c["complaint_date"], c["status"])
            c["sla_due_at"]  = sla["sla_due_at"]
            c["sla_status"]  = sla["sla_status"]

    return serialize({
        "complaints": items,
        "pagination": {
            "page": page, "page_size": page_size, "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size)
        }
    })


@router.get("/{complaint_id}")
async def get_complaint(complaint_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    c = await db.marketing_complaints.find_one(
        {"$or": [{"id": complaint_id}, {"complaint_number": complaint_id}]}, {"_id": 0}
    )
    if not c:
        raise HTTPException(404, "Complaint not found")
    if c.get("status") not in ["resolved", "closed"] and c.get("complaint_date"):
        sla = _compute_sla(c["complaint_date"], c["status"])
        c["sla_due_at"] = sla["sla_due_at"]
        c["sla_status"] = sla["sla_status"]
    return serialize(c)


class StatusBody(BaseModel):
    status: str
    note: Optional[str] = None


@router.patch("/{complaint_id}/status")
async def update_complaint_status(complaint_id: str, body: StatusBody, request: Request):
    await require_auth(request)
    user = _get_user(request)
    db = get_db()

    if body.status not in COMPLAINT_STATUSES:
        raise HTTPException(400, f"Invalid status. Valid: {COMPLAINT_STATUSES}")

    c = await db.marketing_complaints.find_one({"id": complaint_id}, {"_id": 0, "complaint_date": 1})
    if not c:
        raise HTTPException(404, "Complaint not found")

    sla_info = _compute_sla(c["complaint_date"], body.status)
    update = {
        "status":     body.status,
        "sla_status": sla_info["sla_status"],
        "updated_at": _now(),
        "updated_by": user.get("email", "system")
    }
    if body.status in ["resolved", "closed"] and body.note:
        update["resolution_text"] = body.note

    # Add note to notes array
    if body.note:
        note_entry = {
            "id":       str(uuid.uuid4()),
            "text":     body.note,
            "author":   user.get("email", "system"),
            "added_at": _now().isoformat()
        }
        await db.marketing_complaints.update_one(
            {"id": complaint_id},
            {"$push": {"notes": note_entry}}
        )

    await db.marketing_complaints.update_one({"id": complaint_id}, {"$set": update})
    return {"ok": True, "new_status": body.status, "sla_status": sla_info["sla_status"]}


class NoteBody(BaseModel):
    text: str


@router.post("/{complaint_id}/notes")
async def add_note(complaint_id: str, body: NoteBody, request: Request):
    await require_auth(request)
    user = _get_user(request)
    db = get_db()

    c = await db.marketing_complaints.find_one({"id": complaint_id}, {"_id": 0, "id": 1})
    if not c:
        raise HTTPException(404, "Complaint not found")

    note = {
        "id":       str(uuid.uuid4()),
        "text":     body.text,
        "author":   user.get("email", "system"),
        "added_at": _now().isoformat()
    }
    await db.marketing_complaints.update_one(
        {"id": complaint_id},
        {"$push": {"notes": note}, "$set": {"updated_at": _now()}}
    )
    return serialize({"ok": True, "note": note})


@router.post("/{complaint_id}/ai-classify")
async def ai_reclassify(complaint_id: str, request: Request):
    await require_auth(request)
    db = get_db()

    c = await db.marketing_complaints.find_one({"id": complaint_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Complaint not found")

    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI not configured")

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"complaint-classify-{complaint_id[:8]}",
        system_message="Kamu adalah sistem klasifikasi komplain pelanggan marketplace Indonesia. Respond only with valid JSON."
    ).with_model("openai", "gpt-4o-mini")

    cats = ", ".join(COMPLAINT_CATEGORIES)
    prompt = (
        f"Klasifikasikan komplain marketplace Indonesia:\n"
        f"Teks: '{c.get('complaint_text', '')}' | Produk: {c.get('product_name', '')}\n\n"
        f"Return JSON persis: {{\"category\": \"<{cats}>\", \"severity\": \"low|medium|high|critical\", "
        f"\"sentiment_score\": -1.0, \"requires_immediate_action\": true, "
        f"\"response_template\": \"template respons Bahasa Indonesia\", \"confidence\": 0.9}}"
    )

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        result = json.loads(clean.strip())

        update = {
            "category":          result.get("category", c["category"]),
            "category_label":    CATEGORY_LABELS_ID.get(result.get("category", c["category"]), c["category"]),
            "severity":          result.get("severity", c.get("severity", "medium")),
            "ai_confidence":     result.get("confidence", 0.9),
            "response_template": result.get("response_template", c.get("response_template", "")),
            "updated_at":        _now()
        }
        await db.marketing_complaints.update_one({"id": complaint_id}, {"$set": update})
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(500, f"AI classification failed: {e}")
