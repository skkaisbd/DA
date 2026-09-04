"""
WS-G6 — Test posting WIP→FG on job internal completed (idempoten).
====================================================================
Membuktikan jalur AKTIF `post_wip_to_fg_on_job_complete` bekerja & idempoten
setelah orphan `post_wip_to_fg_on_wo_complete` dihapus (WS-G6 cleanup).

Self-contained: pakai motor langsung + HPP snapshot fallback (tidak butuh
seed job penuh / HTTP). Membersihkan datanya sendiri.
"""
import os
import sys
import uuid
import asyncio
import pytest
from dotenv import load_dotenv

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


def _db():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c[os.environ["DB_NAME"]]


async def _run_idempotent_check():
    from routes.rahaza_posting import post_wip_to_fg_on_job_complete

    db = _db()
    job_id = f"test-wsg6-{uuid.uuid4().hex[:8]}"
    job = {"id": job_id, "job_number": "TEST-WSG6", "business_type": "internal",
           "status": "Completed", "completed_at": "2026-07-21"}
    user = {"id": "test-user", "name": "pytest"}

    # HPP snapshot fallback -> total_cost 1.000.000 sehingga wip>0
    await db.rahaza_hpp_snapshots.insert_one({"id": str(uuid.uuid4()), "job_id": job_id,
                                              "total_cost": 1_000_000})
    try:
        # 1) posting pertama
        r1 = await post_wip_to_fg_on_job_complete(db, job, user)
        assert r1.get("ok") is True, f"posting gagal: {r1}"
        assert not r1.get("already_posted"), "harusnya JE baru (bukan already_posted)"
        je_id = r1["je_id"]

        # 2) JE ter-post & balanced Dr FG / Cr WIP
        je = await db.rahaza_journal_entries.find_one({"id": je_id}, {"_id": 0})
        assert je and je.get("status") == "posted"
        lines = await db.rahaza_journal_lines.find({"je_id": je_id}, {"_id": 0}).to_list(20)
        tot_d = sum(l.get("debit", 0) for l in lines)
        tot_c = sum(l.get("credit", 0) for l in lines)
        assert abs(tot_d - tot_c) < 0.001 and abs(tot_d - 1_000_000) < 0.001
        debit_line = next(l for l in lines if l.get("debit", 0) > 0)
        credit_line = next(l for l in lines if l.get("credit", 0) > 0)
        assert debit_line["account_code"] == "1-1404"   # FG
        assert credit_line["account_code"] == "1-330"    # WIP

        # 3) posting ulang -> idempoten (already_posted)
        r2 = await post_wip_to_fg_on_job_complete(db, job, user)
        assert r2.get("already_posted") is True, f"harusnya idempoten: {r2}"
        assert r2.get("je_id") == je_id
    finally:
        # cleanup
        await db.rahaza_hpp_snapshots.delete_many({"job_id": job_id})
        je = await db.rahaza_journal_entries.find_one({"source_ref": f"wip_fg_job:{job_id}"}, {"_id": 0})
        if je:
            await db.rahaza_journal_lines.delete_many({"je_id": je["id"]})
            await db.rahaza_journal_entries.delete_one({"id": je["id"]})
        await db.production_jobs.delete_many({"id": job_id})


def test_wip_to_fg_on_job_complete_idempotent():
    """Sync wrapper (tanpa pytest-asyncio) — jalankan coroutine via asyncio.run."""
    asyncio.run(_run_idempotent_check())


if __name__ == "__main__":
    asyncio.run(_run_idempotent_check())
    print("WS-G6 idempotency test PASSED")
