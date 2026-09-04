"""
T2.1 — Migrasi Pinjaman Legacy → Kasbon & Pinjaman (kanonik)
============================================================
Session #12, Wave T2.1 (CLEANUP_MASTER_PLAN.md).

Konteks (SUDAH diverifikasi sebelum menulis skrip ini):
  - `rahaza_employee_loans` (LEGACY) = 3 record pinjaman aktif (PIN/2026/001-003).
  - Menu `hr-employee-loans` ditandai "Pinjaman Karyawan (Legacy)".
  - Kanonik = `dewi_kasbon_requests` via modul `hr-kasbon` ("Kasbon & Pinjaman", BARU)
    yang merupakan SUPERSET: backend `dewi_kasbon.py` mendukung type "kasbon" & "pinjaman".
  - GL-SAFE: `rahaza_journal_entries` = 0 referensi ke 3 loan_id → murni seed tanpa histori GL.
    Skrip ini TIDAK membuat jurnal GL (menghindari double-posting); record bersifat historis.

Sifat skrip:
  - IDEMPOTEN: melewati record yang sudah pernah dimigrasi (marker `migrated_from_loan_id`).
  - AMAN: membuat backup JSON 3 record legacy sebelum menulis.
  - REVERSIBLE: koleksi legacy `rahaza_employee_loans` TIDAK dihapus (diarsipkan).
    Rollback = hapus dokumen dewi_kasbon_requests dengan {"migrated_from":"rahaza_employee_loans"}.

Jalankan: python migrations/t2_1_migrate_employee_loans_to_kasbon.py
"""
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
BACKUP_DIR = "/app/backups"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _map_legacy_to_kasbon(loan: dict, emp: dict | None) -> dict:
    """Peta 1 record rahaza_employee_loans → skema kanonik dewi_kasbon_requests (create-API)."""
    amount = float(loan.get("loan_amount") or loan.get("principal") or 0)
    installment_count = int(loan.get("tenor_months") or loan.get("installment_count") or 1)
    installment_amount = float(loan.get("monthly_installment") or loan.get("installment_amount") or 0)
    paid_amount = float(loan.get("paid_amount") or 0)
    outstanding = float(
        loan.get("outstanding_balance")
        if loan.get("outstanding_balance") is not None
        else loan.get("remaining_balance")
        if loan.get("remaining_balance") is not None
        else max(amount - paid_amount, 0)
    )
    disbursement_date = loan.get("disbursement_date") or loan.get("disbursed_at")
    approved_by = loan.get("approved_by") or ""
    emp = emp or {}
    return {
        "id": str(uuid.uuid4()),
        "request_number": loan.get("loan_number") or f"PIN/MIG/{loan.get('id', '')[:8]}",
        "employee_id": loan.get("employee_id"),
        "employee_name": loan.get("employee_name") or emp.get("name", ""),
        "employee_code": loan.get("employee_code") or emp.get("employee_code") or emp.get("code", ""),
        "employee_email": emp.get("email", ""),
        "department": emp.get("department", ""),
        "type": "pinjaman",
        "type_label": "Pinjaman",
        "amount": amount,
        "purpose": loan.get("purpose", ""),
        "notes": "Migrasi otomatis dari sistem Pinjaman Legacy (rahaza_employee_loans) — W-T2.1.",
        "documents": [],
        "installment_count": installment_count,
        "installment_amount": installment_amount,
        # Status: legacy 'active' = sudah dicairkan & sedang diangsur → 'disbursed'
        "status": "paid_off" if outstanding <= 0.01 else "disbursed",
        # HR review (dianggap sudah disetujui pada sistem legacy)
        "hr_reviewed_by": approved_by,
        "hr_reviewed_at": disbursement_date,
        "hr_notes": "Disetujui pada sistem legacy.",
        # Finance disbursal
        "disbursed_by": approved_by,
        "disbursed_at": loan.get("disbursed_at") or disbursement_date,
        "disbursement_date": disbursement_date,
        "deduction_start_period": None,
        "finance_notes": None,
        # Repayment tracking
        "paid_amount": paid_amount,
        "outstanding_balance": outstanding,
        "repayments": [],
        # Meta + traceability
        "submitted_by": approved_by,
        "submitted_by_name": loan.get("employee_name", ""),
        "created_at": loan.get("request_date") or _now_iso(),
        "updated_at": _now_iso(),
        # Marker migrasi (idempotency + rollback)
        "migrated_from": "rahaza_employee_loans",
        "migrated_from_loan_id": loan.get("id"),
        "migrated_at": _now_iso(),
    }


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    legacy = await db.rahaza_employee_loans.find({}, {"_id": 0}).to_list(length=1000)
    print(f"Legacy rahaza_employee_loans ditemukan: {len(legacy)} record")
    if not legacy:
        print("Tidak ada data legacy. Selesai.")
        return

    # 1) Backup
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"t2_1_employee_loans_backup_{ts}.json")
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(legacy, f, default=str, ensure_ascii=False, indent=2)
    print(f"Backup tersimpan: {backup_path}")

    # 2) Idempotent migrate
    migrated, skipped = 0, 0
    for loan in legacy:
        loan_id = loan.get("id")
        exists = await db.dewi_kasbon_requests.find_one(
            {"migrated_from_loan_id": loan_id}, {"_id": 0, "id": 1}
        )
        if exists:
            print(f"  SKIP (sudah dimigrasi): {loan.get('loan_number')} ({loan_id})")
            skipped += 1
            continue
        emp = await db.rahaza_employees.find_one(
            {"$or": [{"id": loan.get("employee_id")}, {"employee_id": loan.get("employee_id")}]},
            {"_id": 0},
        )
        doc = _map_legacy_to_kasbon(loan, emp)
        await db.dewi_kasbon_requests.insert_one(doc)
        print(
            f"  MIGRATED: {doc['request_number']} — {doc['employee_name']} "
            f"amount={doc['amount']:,.0f} outstanding={doc['outstanding_balance']:,.0f} status={doc['status']}"
        )
        migrated += 1

    # 3) Verify
    total_kasbon = await db.dewi_kasbon_requests.count_documents({})
    total_pinjaman = await db.dewi_kasbon_requests.count_documents({"type": "pinjaman"})
    total_migrated = await db.dewi_kasbon_requests.count_documents(
        {"migrated_from": "rahaza_employee_loans"}
    )
    print("\n=== RINGKASAN ===")
    print(f"Migrated baru: {migrated} | Skipped: {skipped}")
    print(f"dewi_kasbon_requests total     : {total_kasbon}")
    print(f"  - type=pinjaman              : {total_pinjaman}")
    print(f"  - migrated_from legacy loans : {total_migrated}")
    print(f"rahaza_employee_loans (arsip)  : {len(legacy)} (TIDAK dihapus, tetap sebagai arsip)")


if __name__ == "__main__":
    asyncio.run(main())
