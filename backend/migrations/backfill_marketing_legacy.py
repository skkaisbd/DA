"""
Backfill Legacy Marketing Records — Normalize legacy_toko docs to marketing schema
=====================================================================================

Context (Phase B.2 Toko Frontend Cutover):
- When `dewi_toko_returns` / `dewi_toko_reviews` were migrated to
  `marketing_returns` / `marketing_reviews` (P1.D), the data was copied with
  TOKO-shape fields (`customer_name`, `channel_code`, `decision`, etc.) into
  marketing collections. This works fine for legacy adapter reads, but the
  native marketing endpoints (`/api/marketing/returns`, `/api/marketing/reviews`)
  expect marketing-shape fields (`date`, `order_id`, `platform`, `product`,
  `price`, `refund_type`, etc.).

- This script BACKFILLS the legacy-shape docs with marketing-shape fields
  WITHOUT removing legacy fields (dual-shape, fully backward compatible).

Status:
- Idempotent: re-running is safe; only fills fields if missing.
- Read-only on `dewi_*` collections (already dropped); operates only on
  `marketing_returns` / `marketing_reviews` legacy-flagged docs.

Run:
    python3 /app/backend/migrations/backfill_marketing_legacy.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


# ── Status / Type mappings (legacy toko → marketing) ─────────────────────────

TOKO_RETURN_STATUS_TO_MKT = {
    "new": "pending",
    "investigating": "pending",
    "decision_made": "approved",  # default; overridden if decision==reject below
    "resolved": "completed",
    "closed": "completed",
    "pending": "pending",
}

TOKO_DECISION_TO_MKT_REFUND_TYPE = {
    "refund": "full_refund",
    "reship": "exchange",
    "reject": "no_refund",
    "pending": "no_refund",
}

REASON_LABELS = {
    "produk_tidak_sesuai": "Produk Tidak Sesuai Deskripsi",
    "ukuran_salah": "Ukuran Salah/Tidak Sesuai",
    "produk_cacat": "Produk Cacat/Rusak",
    "warna_berbeda": "Warna Berbeda dari Gambar",
    "tidak_sesuai_ekspektasi": "Tidak Sesuai Ekspektasi",
    "salah_pesan": "Salah Pesan",
    "terlambat_sampai": "Terlambat Sampai",
    "rusak_saat_pengiriman": "Rusak Saat Pengiriman",
    "lainnya": "Lainnya",
}

# Best-guess infer reason key from free text
def _infer_reason_key(text: str) -> str:
    if not text:
        return "lainnya"
    t = text.lower()
    if "ukuran" in t or "size" in t:
        return "ukuran_salah"
    if "cacat" in t or "defect" in t or "bolong" in t or "rusak" in t and "kirim" not in t:
        return "produk_cacat"
    if "warna" in t or "color" in t:
        return "warna_berbeda"
    if "kirim" in t or "ekspedisi" in t:
        return "rusak_saat_pengiriman"
    if "lambat" in t or "telat" in t:
        return "terlambat_sampai"
    if "tidak sesuai" in t or "beda" in t:
        return "produk_tidak_sesuai"
    if "salah pesan" in t or "salah order" in t:
        return "salah_pesan"
    if "ekspektasi" in t:
        return "tidak_sesuai_ekspektasi"
    return "lainnya"


TOKO_REVIEW_STATUS_TO_MKT = {
    "unread": "pending",
    "responded": "reviewed",
    "flagged": "pending",  # marketing doesn't have flagged; keep pending
    "pending": "pending",
    "reviewed": "reviewed",
}


# ── Backfill returns ─────────────────────────────────────────────────────────

async def backfill_returns(db, dry_run: bool = False) -> dict:
    stats = {"checked": 0, "updated": 0, "skipped": 0, "details": []}

    cursor = db.marketing_returns.find({"_legacy_toko": True})
    async for doc in cursor:
        stats["checked"] += 1

        patch: dict = {}

        # date ← created_at (ISO date string)
        if not doc.get("date"):
            ca = doc.get("created_at")
            if isinstance(ca, datetime):
                patch["date"] = ca.date().isoformat()
            elif isinstance(ca, str) and ca:
                patch["date"] = ca[:10]
            else:
                patch["date"] = datetime.now(timezone.utc).date().isoformat()

        # order_id ← order_number (legacy)
        if not doc.get("order_id") or doc.get("order_id") == doc.get("order_number"):
            # Use order_number if order_id is missing or equal to old uuid
            if doc.get("order_number"):
                patch["order_id"] = doc["order_number"]

        # platform ← channel_code
        if not doc.get("platform"):
            ch = doc.get("channel_code") or "shopee"
            # Map "tiktok_shop" → "tiktok"
            mapping = {"tiktok_shop": "tiktok"}
            patch["platform"] = mapping.get(ch, ch)

        # product — derive from customer_name or "(legacy toko)" placeholder
        if not doc.get("product"):
            doc.get("customer_name") or ""
            patch["product"] = f"Pesanan {doc.get('order_number') or doc.get('return_number') or 'legacy'}"

        # price ← estimated_value
        if doc.get("price") is None and doc.get("estimated_value") is not None:
            patch["price"] = float(doc.get("estimated_value") or 0)

        # reason: keep as-is if it's already a key, else infer
        if doc.get("reason") and doc.get("reason") not in REASON_LABELS:
            inferred = _infer_reason_key(str(doc.get("reason") or ""))
            patch["reason"] = inferred
            patch["reason_detail"] = str(doc.get("reason") or "")
        elif not doc.get("reason"):
            patch["reason"] = "lainnya"
            patch["reason_detail"] = doc.get("evidence_notes") or ""

        # reason_label
        if not doc.get("reason_label"):
            r_key = patch.get("reason") or doc.get("reason") or "lainnya"
            patch["reason_label"] = REASON_LABELS.get(r_key, r_key)

        # reason_detail
        if not doc.get("reason_detail") and "reason_detail" not in patch:
            patch["reason_detail"] = doc.get("evidence_notes") or doc.get("reason") or ""

        # courier ← (no legacy field), default
        if not doc.get("courier"):
            patch["courier"] = "jnt"

        # status ← map from toko status
        if not doc.get("status") or doc.get("status") in ("new", "investigating", "decision_made", "resolved", "closed"):
            toko_status = doc.get("status", "new")
            decision = doc.get("decision") or "pending"
            mkt_status = TOKO_RETURN_STATUS_TO_MKT.get(toko_status, "pending")
            # Override: if decision==reject, status='rejected'
            if toko_status == "decision_made" and decision == "reject":
                mkt_status = "rejected"
            elif toko_status == "decision_made" and decision in ("refund", "reship"):
                mkt_status = "approved"
            patch["status"] = mkt_status

        # refund_type ← from decision
        if not doc.get("refund_type"):
            decision = doc.get("decision") or "pending"
            patch["refund_type"] = TOKO_DECISION_TO_MKT_REFUND_TYPE.get(decision, "no_refund")

        # refund_amount
        if doc.get("refund_amount") is None:
            rt = patch.get("refund_type") or doc.get("refund_type") or "no_refund"
            price = patch.get("price") or doc.get("price") or doc.get("estimated_value") or 0
            if rt == "full_refund":
                patch["refund_amount"] = float(price)
            elif rt == "partial_refund":
                patch["refund_amount"] = float(price) * 0.7
            else:
                patch["refund_amount"] = 0.0

        # appeal_status / appeal_result
        if not doc.get("appeal_status"):
            decision = doc.get("decision") or "pending"
            if decision == "reject":
                patch["appeal_status"] = "rejected"
                patch["appeal_result"] = "Ditolak"
            elif decision in ("refund", "reship"):
                patch["appeal_status"] = "accepted"
                patch["appeal_result"] = "Disetujui"
            else:
                patch["appeal_status"] = "pending"
                patch["appeal_result"] = "Menunggu"

        # notes ← decision_notes or evidence_notes
        if not doc.get("notes"):
            patch["notes"] = doc.get("decision_notes") or doc.get("evidence_notes") or ""

        if patch:
            patch["updated_at"] = datetime.now(timezone.utc)
            stats["details"].append({"id": doc["id"], "fields": list(patch.keys())})
            if not dry_run:
                await db.marketing_returns.update_one(
                    {"id": doc["id"]},
                    {"$set": patch},
                )
            stats["updated"] += 1
        else:
            stats["skipped"] += 1

    return stats


# ── Backfill reviews ─────────────────────────────────────────────────────────

REVIEW_CATEGORIES = ["kualitas_produk", "ukuran_pas", "warna", "pengiriman", "pelayanan", "lainnya"]
REVIEW_CATEGORY_LABELS = {
    "kualitas_produk": "Kualitas Produk",
    "ukuran_pas": "Kesesuaian Ukuran",
    "warna": "Warna",
    "pengiriman": "Pengiriman",
    "pelayanan": "Pelayanan",
    "lainnya": "Lainnya",
}


async def backfill_reviews(db, dry_run: bool = False) -> dict:
    stats = {"checked": 0, "updated": 0, "skipped": 0, "details": []}

    cursor = db.marketing_reviews.find({"_legacy_toko": True})
    async for doc in cursor:
        stats["checked"] += 1
        patch: dict = {}

        # date ← created_at
        if not doc.get("date"):
            ca = doc.get("created_at")
            if isinstance(ca, datetime):
                patch["date"] = ca.date().isoformat()
            elif isinstance(ca, str) and ca:
                patch["date"] = ca[:10]
            else:
                patch["date"] = datetime.now(timezone.utc).date().isoformat()

        # order_id ← order_ref
        if not doc.get("order_id") and doc.get("order_ref"):
            patch["order_id"] = doc.get("order_ref")

        # platform ← channel_code (with mapping)
        if not doc.get("platform"):
            ch = doc.get("channel_code") or "shopee"
            mapping = {"tiktok_shop": "tiktok"}
            patch["platform"] = mapping.get(ch, ch)

        # product ← sku_code or customer_name fallback
        if not doc.get("product"):
            product_label = doc.get("sku_code") or f"Review dari {doc.get('customer_name') or 'pelanggan'}"
            patch["product"] = product_label

        # category default
        if not doc.get("category"):
            patch["category"] = "lainnya"
            patch["category_label"] = REVIEW_CATEGORY_LABELS["lainnya"]

        # status ← map from toko status
        if not doc.get("status") or doc.get("status") in ("unread", "responded", "flagged"):
            toko_status = doc.get("status", "unread")
            patch["status"] = TOKO_REVIEW_STATUS_TO_MKT.get(toko_status, "pending")

        # response_text might exist but no response_date
        if doc.get("response_text") and not doc.get("response_date"):
            patch["response_date"] = doc.get("responded_at") or doc.get("created_at")

        if patch:
            patch["updated_at"] = datetime.now(timezone.utc)
            stats["details"].append({"id": doc["id"], "fields": list(patch.keys())})
            if not dry_run:
                await db.marketing_reviews.update_one(
                    {"id": doc["id"]},
                    {"$set": patch},
                )
            stats["updated"] += 1
        else:
            stats["skipped"] += 1

    return stats


# ── Main entrypoint ──────────────────────────────────────────────────────────

async def main(dry_run: bool):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = os.environ.get("DB_NAME", "cv_dewi_aditya")
    db = client[db_name]

    print(f"== Backfill Marketing Legacy {'(DRY-RUN)' if dry_run else '(EXECUTE)'} ==")
    print(f"DB: {db_name}")
    print()

    rt = await backfill_returns(db, dry_run=dry_run)
    print(f"[returns]  checked={rt['checked']}  updated={rt['updated']}  skipped={rt['skipped']}")
    for d in rt["details"][:5]:
        print(f"           - {d['id']}: {d['fields']}")
    print()

    rv = await backfill_reviews(db, dry_run=dry_run)
    print(f"[reviews]  checked={rv['checked']}  updated={rv['updated']}  skipped={rv['skipped']}")
    for d in rv["details"][:5]:
        print(f"           - {d['id']}: {d['fields']}")
    print()

    print("Done.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(main(dry_run))
