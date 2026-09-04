"""rahaza_inventory — FG Movements + FG Issues (pengeluaran produk jadi)."""
# ruff: noqa: E741
from fastapi import Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from typing import Optional
import uuid
from datetime import datetime, timezone
from routes.rahaza_inventory_shared import router


def _fg_uid(): return str(uuid.uuid4())
def _fg_now(): return datetime.now(timezone.utc)


FG_ISSUE_REASONS = {
    "surat_jalan_internal": "Surat Jalan Internal",
    "sample":               "Sample / Contoh",
    "koreksi_stok":         "Koreksi Stok (Adjustment)",
    "retur":                "Retur / Rusak",
    "lainnya":              "Lainnya",
}


@router.get("/fg-movements")
async def list_fg_movements(request: Request, fg_code: Optional[str] = None,
                            direction: Optional[str] = None, limit: int = 50):
    await require_auth(request)
    db = get_db()
    q: dict = {}
    if fg_code:
        q["fg_code"] = fg_code
    if direction:
        q["direction"] = direction
    movements = await db.rahaza_fg_movements.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(500)
    return serialize_doc(movements)


@router.get("/fg-issues")
async def list_fg_issues(request: Request, limit: int = 50):
    await require_auth(request)
    db = get_db()
    issues = await db.rahaza_fg_issues.find({}, {"_id": 0}).sort("issued_at", -1).limit(limit).to_list(500)
    return serialize_doc(issues)


@router.post("/fg-issue")
async def create_fg_issue(request: Request):
    user = await require_auth(request)
    db   = get_db()
    body = await request.json()

    material_id = body.get("material_id")
    qty         = int(body.get("qty") or 0)
    reason      = body.get("reason", "lainnya")
    customer_id = body.get("customer_id")
    ref_no      = body.get("reference_number", "")
    notes       = body.get("notes", "")

    if not material_id:
        raise HTTPException(400, "material_id wajib diisi")
    if qty <= 0:
        raise HTTPException(400, "qty harus lebih dari 0")
    if reason not in FG_ISSUE_REASONS:
        raise HTTPException(400, f"reason harus salah satu: {list(FG_ISSUE_REASONS.keys())}")

    mat = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
    if not mat:
        raise HTTPException(404, "Material tidak ditemukan")
    if mat.get("type") != "fg":
        raise HTTPException(400, "Material bukan produk jadi (type=fg)")

    default_loc = await db.rahaza_locations.find_one({"active": True}, {"_id": 0})
    loc_id = default_loc["id"] if default_loc else None
    stock_doc = await db.rahaza_material_stock.find_one(
        {"material_id": material_id, "location_id": loc_id}, {"_id": 0}
    )
    available = float(stock_doc.get("qty", 0)) if stock_doc else 0
    if qty > available:
        raise HTTPException(400, f"Stok tidak cukup. Tersedia: {available} pcs, diminta: {qty} pcs")

    customer_name = None
    if customer_id:
        cust = await db.rahaza_customers.find_one({"id": customer_id}, {"_id": 0})
        customer_name = cust.get("name") if cust else None

    # SESI #27 — SATU PINTU kebijakan penomoran (Otomatis/Manual). Nama variabel
    # `issue_number` disimpan (dipakai di banyak baris di bawah) tetapi fungsi
    # penomoran diimpor dengan alias supaya tidak saling menimpa.
    from core.doc_number_policy import issue_number as _issue_doc_number
    issue_number = await _issue_doc_number(
        db, "rahaza_fg_issues.issue_number",
        requested=(body.get("issue_number") or "").strip())

    from core import stock_service
    if loc_id:
        try:
            await stock_service.issue(
                material_id, loc_id, qty,
                ref={"source": "fg_issue", "issue_number": issue_number, "customer_id": customer_id},
                actor={"id": str(user.get("id") or ""), "email": user.get("email", "")},
                db=db,
            )
        except stock_service.InsufficientStock:
            raise HTTPException(400, f"Stok tidak cukup. Tersedia: {available} pcs, diminta: {qty} pcs")

    issue_id = _fg_uid()
    issue_doc = {
        "id":               issue_id,
        "issue_number":     issue_number,
        "material_id":      material_id,
        "fg_code":          mat.get("code"),
        "fg_name":          mat.get("name"),
        "qty":              qty, "unit": mat.get("unit", "pcs"),
        "reason":           reason, "reason_label": FG_ISSUE_REASONS[reason],
        "customer_id":      customer_id, "customer_name": customer_name,
        "reference_number": ref_no, "notes": notes,
        "issued_by":        user.get("name", ""),
        "issued_by_id":     user.get("sub", ""),
        "issued_at":        _fg_now(),
        "stock_before":     available, "stock_after": available - qty,
        "location_id":      loc_id,
    }
    await db.rahaza_fg_issues.insert_one(issue_doc)
    await db.rahaza_fg_movements.insert_one({
        "id":              _fg_uid(),
        "fg_code":         mat.get("code"),
        "material_id":     material_id,
        "fg_issue_id":     issue_id,
        "direction":       "out", "qty": qty,
        "source":          "manual_issue", "reason": reason,
        "customer_id":     customer_id, "customer_name": customer_name,
        "reference_number": ref_no,
        "notes":           notes or FG_ISSUE_REASONS[reason],
        "issued_by":       user.get("name", ""),
        "timestamp":       _fg_now(),
    })
    await log_activity(user["id"], user.get("name", ""), "fg_issue_created", "rahaza.fg_issue",
                      f"{issue_number}: {mat.get('code')} qty={qty} reason={reason}")
    return serialize_doc({**issue_doc, "ok": True})
