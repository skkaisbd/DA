"""
Migrate legacy `acc_opname_sessions` + `acc_opname_lines` -> SSOT `wh_opname_sessions2`
with `domain='accessory'` and embedded `count_items`.

Idempotent. Safe to run multiple times.
Usage:
    # Preview only (no DB changes)
    python3 -m migrations.migrate_acc_opname --dry-run

    # Apply
    python3 -m migrations.migrate_acc_opname

Notes:
    - Status mapping: Active->open, Completed->approved, Cancelled->cancelled
    - Source collections preserved (NOT dropped) until manual cleanup after verification.
    - Each migrated session is tagged `migrated_from: 'acc_opname'` for traceability.
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')

_STATUS_ACC_TO_WH = {
    "Active": "open",
    "Completed": "approved",
    "Cancelled": "cancelled",
}


def _iso_to_dt(v: Any) -> Any:
    """Best-effort convert ISO str -> datetime (kept tz-aware). Pass-through other types."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            # Handle 'Z' suffix and tz offsets
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None
    return v


def _now():
    return datetime.now(timezone.utc)


async def migrate(dry_run: bool) -> dict:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "test_database")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    stats = {
        "acc_sessions_found": 0,
        "acc_sessions_migrated": 0,
        "acc_sessions_already_present": 0,
        "acc_lines_migrated": 0,
        "errors": [],
    }

    sessions = await db.acc_opname_sessions.find({}, {"_id": 0}).to_list(10000)
    stats["acc_sessions_found"] = len(sessions)

    if not sessions:
        print("⚠️  No acc_opname_sessions found — nothing to migrate.")
        return stats

    for s in sessions:
        sid = s.get("id")
        if not sid:
            stats["errors"].append(f"Skipped session with missing id: {s.get('ref_number', '?')}")
            continue

        # Skip if already migrated
        existing = await db.wh_opname_sessions2.find_one({"id": sid})
        if existing:
            stats["acc_sessions_already_present"] += 1
            continue

        # Load lines for this session
        acc_lines = await db.acc_opname_lines.find(
            {"session_id": sid}, {"_id": 0}
        ).to_list(10000)

        count_items = []
        for ln in acc_lines:
            counted_qty = ln.get("counted_qty")
            system_qty = float(ln.get("system_qty") or 0)
            counted = counted_qty is not None
            variance = ln.get("diff")
            if counted and variance is None:
                variance = float(counted_qty) - system_qty
            variance_pct = None
            if counted:
                if system_qty > 0:
                    variance_pct = (float(variance) / system_qty) * 100.0
                else:
                    variance_pct = 100.0 if float(counted_qty) > 0 else 0.0
            count_items.append({
                "line_id": ln.get("id") or "",
                "material_id": ln.get("acc_id") or "",
                "position_id": ln.get("acc_id") or "",
                "material_code": ln.get("acc_code") or "",
                "material_name": ln.get("acc_name") or "",
                "unit": ln.get("unit") or "pcs",
                "system_qty": system_qty,
                "counted_qty": counted_qty,
                "variance": variance,
                "variance_pct": variance_pct,
                "notes": ln.get("notes") or "",
                "counted_by": ln.get("counted_by") or "",
                "counted_at": ln.get("counted_at") or "",
                "counted": counted,
            })

        # Convert session
        legacy_status = s.get("status") or "Active"
        new_status = _STATUS_ACC_TO_WH.get(legacy_status, "open")
        counted_count = sum(1 for it in count_items if it.get("counted"))
        variance_items = sum(1 for it in count_items if it.get("counted") and (it.get("variance") or 0) != 0)
        total_variance_value = sum(
            abs(float(it.get("variance") or 0))
            for it in count_items
            if it.get("counted")
        )

        created_at = _iso_to_dt(s.get("started_at") or s.get("created_at")) or _now()
        approved_at = _iso_to_dt(s.get("completed_at")) if new_status == "approved" else None

        new_doc = {
            "id": sid,
            "session_no": s.get("ref_number") or "",
            "mode": "full_count",
            "scope_type": "all",
            "scope_id": "",
            "scope_label": "Aksesoris",
            "domain": "accessory",
            "status": new_status,
            "count_items": count_items,
            "total_items": s.get("total_items") or len(count_items),
            "counted_items": counted_count,
            "total_variance_items": variance_items,
            "total_variance_value": total_variance_value,
            "notes": s.get("notes") or "",
            "created_at": created_at,
            "created_by": s.get("started_by") or "",
            "counted_by": s.get("started_by") or None,
            "approved_by": s.get("completed_by") or None,
            "approved_at": approved_at,
            "closed_at": approved_at if new_status in ("approved", "cancelled") else None,
            "migrated_from": "acc_opname",
            "migrated_at": _now(),
        }

        if dry_run:
            print(f"  DRY-RUN would insert: id={sid}  ref={new_doc['session_no']}  status={new_status}  lines={len(count_items)}  counted={counted_count}")
        else:
            await db.wh_opname_sessions2.insert_one(new_doc)
            print(f"  ✅ Migrated: id={sid}  ref={new_doc['session_no']}  status={new_status}  lines={len(count_items)}")

        stats["acc_sessions_migrated"] += 1
        stats["acc_lines_migrated"] += len(count_items)

    return stats


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only (no DB writes)")
    args = parser.parse_args()

    mode = "DRY-RUN" if args.dry_run else "APPLY"
    print("=" * 60)
    print(f"Aksesoris Opname SSOT Migration — Mode: {mode}")
    print("=" * 60)

    stats = await migrate(dry_run=args.dry_run)

    print("\n📊 Migration summary:")
    print(f"   - Legacy acc_opname_sessions found:  {stats['acc_sessions_found']}")
    print(f"   - Sessions migrated (new):           {stats['acc_sessions_migrated']}")
    print(f"   - Sessions already present (skipped): {stats['acc_sessions_already_present']}")
    print(f"   - Lines migrated:                    {stats['acc_lines_migrated']}")
    if stats["errors"]:
        print("   - Errors:")
        for err in stats["errors"]:
            print(f"       * {err}")

    if args.dry_run:
        print("\n⚠️  Dry-run only. To apply, re-run without --dry-run.")
    else:
        print("\n✅ Migration complete.")
        print("   Legacy collections preserved (NOT dropped).")
        print("   After 1-week monitoring window, drop with:")
        print("       db.acc_opname_sessions.drop()")
        print("       db.acc_opname_lines.drop()")


if __name__ == "__main__":
    sys.path.insert(0, "/app/backend")
    asyncio.run(main())
