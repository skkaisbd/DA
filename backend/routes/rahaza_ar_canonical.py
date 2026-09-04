"""Skema kanonik AR (H-01): satu koleksi `rahaza_ar_invoices` untuk piutang internal & maklon.
Kanonik: total_amount / amount_paid / amount_due, status issued|partial_paid|paid|overdue|written_off|cancelled|draft.
Field lama (total / paid_amount / balance, status 'sent') tetap DITULIS sebagai cermin agar pembaca lama tidak rusak."""
import logging
from datetime import date, datetime, timezone

log = logging.getLogger(__name__)
OPEN_STATUSES = ["issued", "sent", "partial_paid", "overdue"]
STATUS_MAP = {"sent": "issued"}


def canon(inv: dict) -> dict:
    """Pandangan kanonik satu dokumen AR (tanpa mengubah dokumen)."""
    total = inv.get("total_amount") if inv.get("total_amount") is not None else inv.get("total")
    paid = inv.get("amount_paid") if inv.get("amount_paid") is not None else inv.get("paid_amount")
    due = inv.get("amount_due") if inv.get("amount_due") is not None else inv.get("balance")
    total = float(total or 0)
    paid = float(paid or 0)
    due = float(due if due is not None else max(total - paid, 0))
    status = STATUS_MAP.get(inv.get("status"), inv.get("status") or "draft")
    return {
        **inv,
        "total_amount": round(total, 2), "amount_paid": round(paid, 2), "amount_due": round(due, 2),
        "total": round(total, 2), "paid_amount": round(paid, 2), "balance": round(due, 2),
        "status": status,
        "customer_name": inv.get("customer_name") or inv.get("client_name") or "",
        "source": "maklon" if inv.get("source_module") == "maklon_po" or inv.get("linked_maklon_po_id") else "internal",
    }


async def migrate_ar_canonical(db) -> dict:
    """Idempoten: isi field kanonik + cermin lama, status sent→issued."""
    n = 0
    async for inv in db.rahaza_ar_invoices.find({}, {"_id": 0}):
        c = canon(inv)
        upd = {k: c[k] for k in ("total_amount", "amount_paid", "amount_due", "total", "paid_amount", "balance", "status")
               if inv.get(k) != c[k]}
        if upd:
            upd["updated_at"] = datetime.now(timezone.utc)
            await db.rahaza_ar_invoices.update_one({"id": inv["id"]}, {"$set": upd})
            n += 1
    return {"updated": n}


def _bucket(days: int) -> str:
    if days <= 0:
        return "current"
    if days <= 30:
        return "1_30"
    if days <= 60:
        return "31_60"
    if days <= 90:
        return "61_90"
    return "90_plus"


async def compute_ar_aging(db, source: str = None) -> dict:
    """Aging piutang tunggal (internal + maklon). source='internal'|'maklon' untuk memfilter."""
    today = date.today()
    q = {"status": {"$in": OPEN_STATUSES}}
    rows_db = await db.rahaza_ar_invoices.find(q, {"_id": 0}).to_list(5000)
    buckets = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "90_plus": 0.0, "tanpa_jatuh_tempo": 0.0}
    rows, invalid = [], []
    for r in rows_db:
        c = canon(r)
        if source and c["source"] != source:
            continue
        if c["amount_due"] <= 0:
            continue
        try:
            due = date.fromisoformat(str(r.get("due_date"))[:10])
            days = (today - due).days
            bucket = _bucket(days)
            valid = True
        except (ValueError, TypeError):
            days, bucket, valid = 0, "tanpa_jatuh_tempo", False
            invalid.append({"id": r.get("id"), "invoice_number": r.get("invoice_number"), "due_date": r.get("due_date")})
        if valid and days > 0 and c["status"] == "issued":
            c["status"] = "overdue"
        buckets[bucket] += c["amount_due"]
        rows.append({**c, "days_overdue": max(days, 0), "bucket": bucket, "due_date_valid": valid,
                     "balance_amount": c["amount_due"], "client_name": c["customer_name"]})
    rows.sort(key=lambda x: -x["days_overdue"])
    return {"buckets": {k: round(v, 2) for k, v in buckets.items()},
            "total": round(sum(buckets.values()), 2), "count": len(rows), "rows": rows,
            "data_quality": {"skipped": 0, "invalid_due_date": invalid}}
