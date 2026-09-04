"""
PT Rahaza — Order Management (Fase 5a)

Endpoints (prefix /api/rahaza):
  - /customers            : Pelanggan (rajut-specific: NPWP, payment terms)
  - /orders               : Order Produksi (header + items)
  - /orders/{id}/items    : Manage order items
  - /orders/{id}/status   : Transition lifecycle
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.rahaza_audit import log_audit
import uuid
from datetime import datetime, timezone, date
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-orders"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


def _clean_items(items, *, keep_id: bool = False) -> list:
    """Bersihkan DAN VALIDASI item pesanan (SSOT untuk create & update).

    2026-08-07 — DULU setiap baris bermasalah di-`continue` DIAM-DIAM, dengan
    komentar "BUG-002 fix: qty non-numerik -> item di-skip (hindari 500)".
    Menghindari 500 memang benar, tetapi CARANYA salah: baris yang sudah DIISI
    pengguna lalu hilang tanpa pesan = permintaan pelanggan LENYAP. Order
    tercatat kurang ⇒ produksi kurang ⇒ tagihan kurang, dan tidak ada satu pun
    jejak yang bisa ditelusuri. Pengguna melihat "Order tersimpan" lalu baru
    sadar sebulan kemudian bahwa satu size tidak pernah diproduksi.

    (Uji lama `tests/pilot_prod_orders_test_v2.py` TC-30b justru MENGABADIKAN
    perilaku itu — "mixed qty -> hanya valid". Uji tersebut ikut dikoreksi.)

    Aturan sekarang:
      * baris BENAR-BENAR KOSONG (baris template dari UI)  → dilewati; ini wajar
        dan bukan kehilangan data.
      * baris yang SUDAH DIISI tapi tidak lengkap, qty bukan angka, atau qty ≤ 0
        → HTTP 400 yang menyebut NOMOR BARIS-nya, supaya bisa langsung dibetulkan.
    """
    cleaned: list = []
    for idx, raw in enumerate(items or [], start=1):
        raw = raw if isinstance(raw, dict) else {}
        model_id = raw.get("model_id")
        size_id = raw.get("size_id")
        qty_raw = raw.get("qty")
        terisi = bool(model_id) or bool(size_id) or (qty_raw not in (None, "", 0, "0"))
        if not terisi:
            continue  # baris template kosong dari UI — bukan kehilangan data
        if not model_id or not size_id:
            raise HTTPException(
                400, f"Item baris {idx}: Model dan Size wajib dipilih. Baris yang sudah "
                     f"diisi tidak lagi dibuang diam-diam.")
        try:
            q = int(qty_raw or 0)
        except (ValueError, TypeError):
            raise HTTPException(
                400, f"Item baris {idx}: Qty '{qty_raw}' bukan angka bulat. Perbaiki "
                     f"qty-nya — baris ini TIDAK dibuang diam-diam lagi karena itu "
                     f"membuat pesanan tercatat kurang.")
        if q <= 0:
            raise HTTPException(400, f"Item baris {idx}: Qty harus lebih besar dari 0.")
        row = {
            "id": (raw.get("id") or _uid()) if keep_id else _uid(),
            "model_id": model_id,
            "size_id": size_id,
            "qty": q,
            "notes": raw.get("notes") or "",
        }
        cleaned.append(row)
    return cleaned




ORDER_STATUSES = ["draft", "confirmed", "in_production", "completed", "closed", "cancelled"]
ALLOWED_TRANSITIONS = {
    "draft":          ["confirmed", "cancelled"],
    "confirmed":      ["in_production", "cancelled"],
    "in_production":  ["completed", "cancelled"],
    "completed":      ["closed"],
    "closed":         [],
    "cancelled":      [],
}


async def _require_admin(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "admin"):
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "order.manage" in perms or "prod.master.manage" in perms or "customers.manage" in perms:
        return user
    raise HTTPException(403, "Forbidden: butuh permission order/customer.")


# ── CUSTOMERS ────────────────────────────────────────────────────────────────
@router.get("/customers")
async def list_customers(request: Request):
    await require_auth(request)
    db = get_db()
    rows = await db.rahaza_customers.find({}, {"_id": 0}).sort("code", 1).to_list(500)
    return serialize_doc(rows)


@router.post("/customers")
async def create_customer(request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    code = (body.get("code") or "").strip().upper()
    name = (body.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(400, "code & name required")
    if await db.rahaza_customers.find_one({"code": code, "active": True}):
        raise HTTPException(409, f"Kode '{code}' sudah terpakai (aktif). Gunakan kode lain.")
    doc = {
        "id": _uid(),
        "code": code,
        "name": name,
        "company_type": body.get("company_type") or "company",  # company | personal
        "npwp": (body.get("npwp") or "").strip(),
        "phone": (body.get("phone") or "").strip(),
        "email": (body.get("email") or "").strip(),
        "address": body.get("address") or "",
        "payment_terms": body.get("payment_terms") or "net_30",  # cash|net_7|net_14|net_30|custom
        "payment_terms_custom": body.get("payment_terms_custom") or "",
        "credit_limit": float(body.get("credit_limit") or 0),
        "notes": body.get("notes") or "",
        "active": True,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_customers.insert_one(doc)
    # Phase 6: auto-create COA subledger (Piutang per-pelanggan) — idempotent, non-fatal.
    # 2026-08-07 — DULU `except Exception: pass`. Pelanggan tanpa subledger piutang
    # berarti tagihannya tidak punya akun Buku Besar sendiri; saldo piutang
    # per-pelanggan jadi tidak bisa ditelusuri. Tetap non-fatal, tapi tercatat.
    try:
        from routes.coa_auto import ensure_subledger_for_entity
        await ensure_subledger_for_entity(db, "customer", doc, user)
    except Exception as e:  # noqa: BLE001
        logger.error("[coa] subledger piutang GAGAL dibuat untuk pelanggan %s (%s) — "
                     "saldo piutang pelanggan ini tidak punya akun Buku Besar: %s",
                     doc.get("name") or doc.get("id"), code, e)
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.customer", code)
    out = await db.rahaza_customers.find_one({"id": doc["id"]}, {"_id": 0})
    return serialize_doc(out)


@router.put("/customers/{cid}")
async def update_customer(cid: str, request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    body.pop("_id", None)
    body.pop("id", None)
    body.pop("created_at", None)
    body["updated_at"] = _now()
    if "code" in body:
        body["code"] = body["code"].strip().upper()
    res = await db.rahaza_customers.update_one({"id": cid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")
    await log_activity(user["id"], user.get("name", ""), "update", "rahaza.customer", cid)
    return serialize_doc(await db.rahaza_customers.find_one({"id": cid}, {"_id": 0}))


@router.delete("/customers/{cid}")
async def deactivate_customer(cid: str, request: Request):
    await _require_admin(request)
    db = get_db()
    await db.rahaza_customers.update_one({"id": cid}, {"$set": {"active": False, "updated_at": _now()}})
    return {"status": "deactivated"}


# ── ORDERS ──────────────────────────────────────────────────────────────────
async def _gen_order_number(db, requested: str = ""):
    """Nomor order penjualan — SATU PINTU kebijakan penomoran (Otomatis/Manual).

    SESI #27 (batch-3 Fase G): dulu selalu otomatis lewat `gen_prefixed_number`,
    jadi mode MANUAL milik owner tersimpan tetapi tidak pernah berlaku.
    """
    from core.doc_number_policy import issue_number
    return await issue_number(db, "rahaza_orders.order_number", requested=requested)


async def _enrich_orders(db, orders):
    if not orders:
        return orders
    customer_ids = list({o.get("customer_id") for o in orders if o.get("customer_id")})
    cust_map = {}
    if customer_ids:
        custs = await db.rahaza_customers.find({"id": {"$in": customer_ids}}, {"_id": 0}).to_list(500)
        cust_map = {c["id"]: c for c in custs}
    for o in orders:
        cust = cust_map.get(o.get("customer_id"))
        o["customer_name"] = cust["name"] if cust else (o.get("customer_name_snapshot") or ("Produksi Internal" if o.get("is_internal") else None))
        # items summary
        items = o.get("items") or []
        o["total_qty"] = sum(int(i.get("qty") or 0) for i in items)
        o["item_count"] = len(items)
    return orders


@router.get("/orders")
async def list_orders(request: Request, status: Optional[str] = None, customer_id: Optional[str] = None, limit: int = 100, skip: int = 0):
    await require_auth(request)
    db = get_db()
    q = {}
    if status:
        q["status"] = status
    if customer_id:
        q["customer_id"] = customer_id
    rows = await db.rahaza_orders.find(q, {"_id": 0}).sort("order_date", -1).skip(skip).limit(limit).to_list(500)
    await _enrich_orders(db, rows)
    return serialize_doc(rows)


@router.get("/orders/{oid}")
async def get_order(oid: str, request: Request):
    await require_auth(request)
    db = get_db()
    order = await db.rahaza_orders.find_one({"id": oid}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Not found")
    await _enrich_orders(db, [order])
    # enrich items with model/size names
    items = order.get("items") or []
    model_ids = list({i.get("model_id") for i in items if i.get("model_id")})
    size_ids  = list({i.get("size_id")  for i in items if i.get("size_id")})
    mods = await db.rahaza_models.find({"id": {"$in": model_ids}}, {"_id": 0}).to_list(500) if model_ids else []
    szs  = await db.rahaza_sizes.find({"id":  {"$in": size_ids}},  {"_id": 0}).to_list(500) if size_ids else []
    mod_map = {m["id"]: m for m in mods}
    sz_map  = {s["id"]: s for s in szs}
    for it in items:
        mod = mod_map.get(it.get("model_id"))
        sz  = sz_map.get(it.get("size_id"))
        it["model_code"] = mod["code"] if mod else None
        it["model_name"] = mod["name"] if mod else None
        it["size_code"]  = sz["code"]  if sz else None
    return serialize_doc(order)


@router.post("/orders")
async def create_order(request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    is_internal = bool(body.get("is_internal"))
    customer_id = body.get("customer_id") or None
    if not is_internal and not customer_id:
        raise HTTPException(400, "Pilih pelanggan atau tandai sebagai produksi internal.")
    if is_internal:
        customer_id = None
    customer_name_snapshot = ""
    if customer_id:
        cust = await db.rahaza_customers.find_one({"id": customer_id}, {"_id": 0})
        if not cust:
            raise HTTPException(404, "Pelanggan tidak ditemukan")
        customer_name_snapshot = cust["name"]

    # OBS-007 fix: validasi format tanggal (YYYY-MM-DD) bila dikirim
    for _df in ("order_date", "due_date"):
        _v = body.get(_df)
        if _v:
            try:
                date.fromisoformat(str(_v))
            except ValueError:
                raise HTTPException(400, f"{_df} harus berformat tanggal YYYY-MM-DD.")

    items = body.get("items") or []
    cleaned_items = _clean_items(items)

    # BUG-001 fix: order wajib punya minimal 1 item valid (samakan guard FE & BE)
    if not cleaned_items:
        raise HTTPException(400, "Minimal 1 item pesanan (Model + Size + Qty > 0).")

    doc = {
        "id": _uid(),
        "order_number": await _gen_order_number(db, (body.get("order_number") or "").strip()),
        "order_date": body.get("order_date") or date.today().isoformat(),
        "due_date": body.get("due_date") or None,
        "customer_id": customer_id,
        "customer_name_snapshot": customer_name_snapshot,
        "is_internal": is_internal,
        "status": "draft",
        "items": cleaned_items,
        "notes": body.get("notes") or "",
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_orders.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.order", doc["order_number"])
    await log_audit(db, entity_type="rahaza_order", entity_id=doc["id"], action="create",
                    before=None, after={k: v for k, v in doc.items() if k != "_id"},
                    user=user, request=request)
    await _enrich_orders(db, [doc])
    return serialize_doc(doc)


@router.put("/orders/{oid}")
async def update_order(oid: str, request: Request):
    user = await _require_admin(request)
    db = get_db()
    order = await db.rahaza_orders.find_one({"id": oid}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Not found")
    # Only draft orders can be edited fully
    if order.get("status") != "draft":
        raise HTTPException(400, f"Order status '{order.get('status')}' tidak bisa diedit. Gunakan transition endpoint.")
    body = await request.json()
    allowed = {}
    for k in ("order_date", "due_date", "customer_id", "is_internal", "notes", "items"):
        if k in body:
            allowed[k] = body[k]
    # OBS-007 fix: validasi format tanggal (bila dikirim)
    for _df in ("order_date", "due_date"):
        _v = body.get(_df)
        if _v:
            try:
                date.fromisoformat(str(_v))
            except ValueError:
                raise HTTPException(400, f"{_df} harus berformat tanggal YYYY-MM-DD.")
    # Cleanup items if present
    if "items" in allowed:
        cleaned = _clean_items(allowed["items"], keep_id=True)
        # BUG-001 fix: bila field items dikirim, tidak boleh kosong (min 1 item valid)
        if not cleaned:
            raise HTTPException(400, "Minimal 1 item pesanan (Model + Size + Qty > 0).")
        allowed["items"] = cleaned
    # Handle is_internal logic
    if allowed.get("is_internal"):
        allowed["customer_id"] = None
        allowed["customer_name_snapshot"] = ""
    elif "customer_id" in allowed and allowed["customer_id"]:
        cust = await db.rahaza_customers.find_one({"id": allowed["customer_id"]}, {"_id": 0})
        allowed["customer_name_snapshot"] = cust["name"] if cust else ""
    allowed["updated_at"] = _now()
    await db.rahaza_orders.update_one({"id": oid}, {"$set": allowed})
    await log_activity(user["id"], user.get("name", ""), "update", "rahaza.order", oid)
    out = await db.rahaza_orders.find_one({"id": oid}, {"_id": 0})
    await log_audit(db, entity_type="rahaza_order", entity_id=oid, action="update",
                    before=order, after=out, user=user, request=request)
    await _enrich_orders(db, [out])
    return serialize_doc(out)


@router.post("/orders/{oid}/status")
async def transition_status(oid: str, request: Request):
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    new_status = (body.get("status") or "").lower()
    if new_status not in ORDER_STATUSES:
        raise HTTPException(400, f"Status tidak valid. Pilih: {', '.join(ORDER_STATUSES)}")
    order = await db.rahaza_orders.find_one({"id": oid}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Not found")
    current = order.get("status", "draft")
    if new_status not in ALLOWED_TRANSITIONS.get(current, []):
        raise HTTPException(400, f"Tidak bisa pindah dari '{current}' ke '{new_status}'. Transisi valid: {ALLOWED_TRANSITIONS.get(current, [])}")
    update = {"status": new_status, "updated_at": _now()}
    # Stamp timestamps for key statuses
    if new_status == "confirmed":
        update["confirmed_at"]     = _now()
    if new_status == "in_production":
        update["in_production_at"] = _now()
    if new_status == "completed":
        update["completed_at"]     = _now()
    if new_status == "closed":
        update["closed_at"]        = _now()
    if new_status == "cancelled":
        update["cancelled_at"]     = _now()
    await db.rahaza_orders.update_one({"id": oid}, {"$set": update})
    await log_activity(user["id"], user.get("name", ""), f"status:{new_status}", "rahaza.order", oid)
    await log_audit(db, entity_type="rahaza_order", entity_id=oid, action="status_change",
                    before={"status": current}, after={"status": new_status, **{k: v for k, v in update.items() if k != "updated_at"}},
                    user=user, request=request)
    return {"status": new_status, "order_id": oid}


@router.delete("/orders/{oid}")
async def delete_order(oid: str, request: Request):
    user = await _require_admin(request)
    db = get_db()
    order = await db.rahaza_orders.find_one({"id": oid}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Not found")
    if order.get("status") not in ("draft", "cancelled"):
        raise HTTPException(400, "Hanya order Draft atau Cancelled yang bisa dihapus.")
    await db.rahaza_orders.delete_one({"id": oid})
    await log_activity(user["id"], user.get("name", ""), "delete", "rahaza.order", oid)
    await log_audit(db, entity_type="rahaza_order", entity_id=oid, action="delete",
                    before=order, after=None, user=user, request=request)
    return {"status": "deleted"}


# ── Helpers ─────────────────────────────────────────────────────────────────
@router.get("/orders-statuses")
async def get_statuses(request: Request):
    await require_auth(request)
    labels = {
        "draft": "Draft",
        "confirmed": "Confirmed",
        "in_production": "In Production",
        "completed": "Completed",
        "closed": "Closed",
        "cancelled": "Cancelled",
    }
    return [{"value": s, "label": labels[s], "allowed_next": ALLOWED_TRANSITIONS[s]} for s in ORDER_STATUSES]
