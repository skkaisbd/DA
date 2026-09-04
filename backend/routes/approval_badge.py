"""
CV. Dewi Aditya — Approval Badge Endpoint
==========================================
Endpoint ringan yang mengembalikan jumlah item yang memerlukan tindakan
berdasarkan peran pengguna yang sedang login.

Digunakan oleh komponen ApprovalBadge di TopBar untuk menampilkan badge count.

GET /api/approval-inbox/badge
  Response:
    {
      "total": 5,
      "pr_pending": 2,         # PR menunggu persetujuan (submitted)
      "ap_pending": 3,         # AP Invoice belum dibayar (sent/partial_paid)
      "hr_pending": 0,         # HR requests (cuti, lembur, dll)
      "categories": [
        {"key": "pr",   "label": "PR Menunggu",     "count": 2, "module_id": "fin-procurement-requests"},
        {"key": "ap",   "label": "AP Belum Bayar",  "count": 3, "module_id": "fin-ap-aging"},
        {"key": "hr",   "label": "HR Persetujuan",  "count": 0, "module_id": "hr-inbox"},
      ]
    }
"""
from fastapi import APIRouter, Request
from database import get_db
from auth import require_auth

router = APIRouter(prefix="/api/approval-inbox", tags=["approval-badge"])

# Peran yang bisa lihat AP invoices (finance-related)
_FINANCE_ROLES = {"superadmin", "admin", "owner", "accounting", "finance",
                  "staff_keuangan", "manager_keuangan"}

# Peran yang bisa lihat & approve PR
_PROCUREMENT_ROLES = {"superadmin", "admin", "owner", "accounting", "finance",
                      "staff_keuangan", "manager_keuangan", "admin_gudang",
                      "supervisor_produksi", "admin_produksi", "manager_produksi"}

# Peran yang bisa lihat HR inbox
_HR_ROLES = {"superadmin", "admin", "owner", "hr", "hr_manager", "staff_hr"}


@router.get("/badge")
async def get_approval_badge(request: Request):
    """
    Mengembalikan jumlah item yang memerlukan tindakan berdasarkan peran.
    Dipakai oleh ApprovalBadge di TopBar.
    """
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    db = get_db()

    pr_pending = 0
    ap_pending = 0
    hr_pending = 0

    # PR menunggu KEPUTUSAN SAYA.
    # 2026-08-07 — dulu: `count_documents({"status": "submitted"})` disaring
    # daftar peran ke-EMPAT yang ditulis ulang di berkas ini. Dua akibat nyata:
    #   · staf keuangan melihat angka PR tahap DEPARTEMEN (bukan pekerjaannya),
    #     sementara antrean `dept_approved` miliknya sendiri tidak pernah dihitung;
    #   · angka lencana tidak pernah cocok dengan isi kotak persetujuan.
    # Sekarang memakai mesin yang SAMA dengan inbox (`_eval_approval`).
    try:
        from core.pr_approval import pending_for_user
        pr_pending = len(await pending_for_user(db, user))
    except Exception:  # noqa: BLE001 — lencana tidak boleh mematikan TopBar
        pr_pending = 0

    # AP Invoice belum dibayar (perlu tindakan Finance)
    if role in _FINANCE_ROLES:
        ap_pending = await db.rahaza_ap_invoices.count_documents(
            {"status": {"$in": ["sent", "partial_paid"]}}
        )

    # HR requests pending approval
    if role in _HR_ROLES:
        leaves_c = await db.rahaza_leave_requests.count_documents(
            {"status": "pending_approval"}
        )
        overtime_c = await db.rahaza_overtime_requests.count_documents(
            {"status": "pending"}
        )
        sal_c = await db.rahaza_salary_adjustments.count_documents(
            {"status": {"$in": ["draft", "pending_manager", "pending_hr"]}}
        )
        hr_pending = leaves_c + overtime_c + sal_c

    total = pr_pending + ap_pending + hr_pending

    categories = []
    if pr_pending > 0 or role in _PROCUREMENT_ROLES:
        categories.append({
            "key": "pr",
            "label": "PR Menunggu Approval",
            "count": pr_pending,
            "module_id": "proc-requests",   # 2026-08-06 — pintu resmi Portal Pengadaan
            "icon": "shopping-cart",
        })
    if ap_pending > 0 or role in _FINANCE_ROLES:
        categories.append({
            "key": "ap",
            "label": "AP Invoice Belum Bayar",
            "count": ap_pending,
            "module_id": "fin-ap-aging",
            "icon": "hourglass",
        })
    if hr_pending > 0 or role in _HR_ROLES:
        categories.append({
            "key": "hr",
            "label": "HR Perlu Persetujuan",
            "count": hr_pending,
            "module_id": "hr-inbox",
            "icon": "users",
        })

    return {
        "total": total,
        "pr_pending": pr_pending,
        "ap_pending": ap_pending,
        "hr_pending": hr_pending,
        "categories": categories,
    }
