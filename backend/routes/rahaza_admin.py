"""rahaza_admin — thin orchestrator + purge + reset-and-seed endpoints.

Split dari monolith 1343 LOC → 4 modul.
"""
# ruff: noqa: E741
import logging
from fastapi import Request, HTTPException
from database import get_db
from auth import log_activity

from routes.rahaza_admin_shared import router, PURGE_COLLECTIONS, _now  # noqa: F401  re-exported
from routes.rahaza_admin_helpers import _require_super  # noqa: F401
# FASE 5 (AD-4): rahaza_admin_seed diarsip (seed-demo-data lama menulis koleksi
# engine multi-stage yang sudah di-drop). Seeder final: POST /api/seed/maklon-full.

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#   PURGE ENDPOINT
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/purge-demo-data")
async def purge_demo_data(request: Request):
    """Hapus seluruh data transaksional & master. Preserves user accounts."""
    user = await _require_super(request)
    db = get_db()
    summary = {}
    total = 0
    for col in PURGE_COLLECTIONS:
        try:
            res = await db[col].delete_many({})
            if res.deleted_count:
                summary[col] = res.deleted_count
                total += res.deleted_count
        except Exception as e:
            logger.warning(f"Purge {col} error: {e}")
    await log_activity(user["id"], user.get("name", ""), "purge_demo", "admin", f"total_deleted={total}")
    return {"ok": True, "total_deleted": total, "collections": summary}


# ──────────────────────────────────────────────────────────────────────────────
#   FULL RESET (purge + seed in one call)
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/reset-and-seed")
async def reset_and_seed(request: Request):
    """FASE 5 (AD-4): seeder demo lama diarsip — endpoint dinonaktifkan."""
    await _require_super(request)
    raise HTTPException(410, "Seeder lama sudah diarsip. Gunakan POST /api/seed/maklon-full "
                             "(seed final portal produksi: maklon + internal).")




# ──────────────────────────────────────────────────────────────────────────────
#   PHASE 7F: ADMIN SEED PANEL - MANUAL SEED ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/seed-coa")
async def seed_coa_endpoint(request: Request):
    """Phase 7F: Manual seed COA (idempotent)"""
    user = await _require_super(request)
    db = get_db()
    
    try:
        from routes.rahaza_coa import seed_coa_accounts
        count_before = await db.rahaza_coa_accounts.count_documents({})
        await seed_coa_accounts(db)
        count_after = await db.rahaza_coa_accounts.count_documents({})
        
        await log_activity(user["id"], user.get("name", ""), "seed_coa", "admin", 
                          f"COA seeded: {count_before} → {count_after} accounts")
        
        return {
            "ok": True, 
            "message": "COA seeded successfully",
            "count_before": count_before,
            "count_after": count_after,
        }
    except Exception as e:
        logger.exception("COA seed failed")
        return {"ok": False, "error": str(e)}


@router.post("/seed-posting-profiles")
async def seed_posting_profiles_endpoint(request: Request):
    """Phase 7F: Manual seed Posting Profiles (idempotent)"""
    user = await _require_super(request)
    db = get_db()
    
    try:
        from routes.rahaza_posting_profiles import seed_posting_profiles
        count_before = await db.rahaza_posting_profiles.count_documents({})
        await seed_posting_profiles(db)
        count_after = await db.rahaza_posting_profiles.count_documents({})
        
        await log_activity(user["id"], user.get("name", ""), "seed_posting_profiles", "admin",
                          f"Posting Profiles seeded: {count_before} → {count_after} profiles")
        
        return {
            "ok": True,
            "message": "Posting Profiles seeded successfully",
            "count_before": count_before,
            "count_after": count_after,
        }
    except Exception as e:
        logger.exception("Posting Profiles seed failed")
        return {"ok": False, "error": str(e)}


@router.post("/seed-all-accounting")
async def seed_all_accounting_endpoint(request: Request):
    """Phase 7F: One-click seed COA + Posting Profiles + EEM categories"""
    user = await _require_super(request)
    db = get_db()
    
    results = {}
    
    # Seed COA
    try:
        from routes.rahaza_coa import seed_coa_accounts
        count_before = await db.rahaza_coa_accounts.count_documents({})
        await seed_coa_accounts(db)
        count_after = await db.rahaza_coa_accounts.count_documents({})
        results["coa"] = {"ok": True, "count_before": count_before, "count_after": count_after}
    except Exception as e:
        logger.exception("COA seed failed in seed-all")
        results["coa"] = {"ok": False, "error": str(e)}
    
    # Seed Posting Profiles
    try:
        from routes.rahaza_posting_profiles import seed_posting_profiles
        count_before = await db.rahaza_posting_profiles.count_documents({})
        await seed_posting_profiles(db)
        count_after = await db.rahaza_posting_profiles.count_documents({})
        results["posting_profiles"] = {"ok": True, "count_before": count_before, "count_after": count_after}
    except Exception as e:
        logger.exception("Posting Profiles seed failed in seed-all")
        results["posting_profiles"] = {"ok": False, "error": str(e)}
    
    # Seed EEM Categories (optional)
    try:
        from routes.employee_expense_category_master import seed_default_categories
        count_before = await db.employee_expense_categories.count_documents({})
        await seed_default_categories()
        count_after = await db.employee_expense_categories.count_documents({})
        results["eem_categories"] = {"ok": True, "count_before": count_before, "count_after": count_after}
    except Exception as e:
        logger.warning(f"EEM categories seed (optional): {e}")
        results["eem_categories"] = {"ok": False, "error": str(e)}
    
    await log_activity(user["id"], user.get("name", ""), "seed_all_accounting", "admin",
                      "One-click seed: COA + Posting Profiles + EEM")
    
    return {"ok": True, "message": "All accounting seeds completed", "details": results}


@router.get("/accounting-status")
async def get_accounting_status(request: Request):
    """Phase 7F: Check status COA, Posting Profiles, dan EEM setup"""
    await _require_super(request)
    db = get_db()
    
    coa_count = await db.rahaza_coa_accounts.count_documents({})
    pp_count = await db.rahaza_posting_profiles.count_documents({})
    eem_count = await db.employee_expense_categories.count_documents({})
    eem_gl_mapping_count = await db.employee_expense_gl_mappings.count_documents({})
    
    return {
        "ok": True,
        "coa": {
            "count": coa_count,
            "status": "ready" if coa_count > 0 else "empty",
        },
        "posting_profiles": {
            "count": pp_count,
            "status": "ready" if pp_count > 0 else "empty",
        },
        "eem_categories": {
            "count": eem_count,
            "status": "ready" if eem_count > 0 else "empty",
        },
        "eem_gl_mapping": {
            "count": eem_gl_mapping_count,
            "status": "ready" if eem_gl_mapping_count > 0 else "empty",
        },
    }
