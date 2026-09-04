"""Peminjaman Aset (asset loans) — ACC-3.

KONTEKS (kenapa file ini ada):
    `memory/PRODUKSI_E9_AKSESORIS.md` §ACC-3 + `memory/PRODUKSI_E7_ASET.md` §AST-3:
    fitur "Peminjaman" salah domain. Ia dulu hidup di Portal **Aksesoris**
    (`routes/dewi_accessories_loans.py`, koleksi `acc_loans`) dan bekerja dengan
    MENGURANGI **qty stok** aksesoris. Padahal yang dipinjam-kembalikan itu
    **alat/aset** (unit fisik ber-nomor, bukan barang habis pakai).
    Invarian yang dikunci user: "Aksesoris habis-pakai = BOM→request→issue;
    **peminjaman ≠ konsumsi** (domain aset)."

DESAIN:
    * 1 pinjaman = 1 UNIT ASET (`dewi_assets`), bukan qty. Aset yang sedang
      dipinjam berstatus `on_loan` sehingga tidak bisa dipinjam dobel, tidak
      ikut dipilih untuk disposal/transfer tanpa disadari.
    * Riwayat per kejadian di koleksi `dewi_asset_loans` (+ `dispositions`
      bawaan berupa field pengembalian: tanggal, kondisi, catatan).
    * Kondisi saat kembali menentukan status aset: baik → `active`,
      rusak → `in_maintenance` (masuk radar pemeliharaan), hilang → `lost`.
    * Keterlambatan dihitung saat baca (bukan disimpan) supaya tidak pernah basi.

CATATAN: TIDAK menyentuh stok/`stock_service` sama sekali — aset bukan inventory.
"""
from datetime import date, datetime, timezone

from fastapi import Request, HTTPException

from auth import require_auth, log_activity
from database import get_db
from utils.counters import gen_prefixed_number

from ._helpers import router, _uid, _now, _ser

LOAN_COLL = "dewi_asset_loans"

# Status aset yang BOLEH dipinjam
LOANABLE_STATUS = ("active",)
# Alasan penolakan yang mudah dipahami user (bukan kode mentah)
_STATUS_REASON = {
    "on_loan": "aset sedang dipinjam pihak lain",
    "in_maintenance": "aset sedang dalam pemeliharaan",
    "under_repair": "aset sedang diperbaiki",
    "disposed": "aset sudah dilepas/dijual",
    "pending_disposal": "aset sedang menunggu proses disposal",
    "lost": "aset dinyatakan hilang",
}
# Kondisi pengembalian → status aset setelahnya
_CONDITION_TO_STATUS = {
    "good": "active",
    "damaged": "in_maintenance",
    "lost": "lost",
}
VALID_CONDITIONS = tuple(_CONDITION_TO_STATUS.keys())


def _today() -> str:
    return date.today().isoformat()


def _d(s):
    """Parse 'YYYY-MM-DD' → date, atau None."""
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _decorate(loan: dict, today: date | None = None) -> dict:
    """Tambah field turunan: overdue, days_overdue, days_out. Dihitung saat baca."""
    today = today or date.today()
    out = _ser(dict(loan))
    exp = _d(out.get("expected_return_date"))
    start = _d(out.get("loan_date")) or today
    active = out.get("status") == "active"
    out["is_overdue"] = bool(active and exp and exp < today)
    out["days_overdue"] = (today - exp).days if out["is_overdue"] else 0
    end = _d(out.get("return_date")) or today
    out["days_out"] = max((end - start).days, 0)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# LIST / SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/loans")
async def list_asset_loans(request: Request):
    """Daftar peminjaman aset.
    Query: status=active|returned|all (default all), overdue=1, search=, asset_id=
    """
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    q: dict = {}
    status = (sp.get("status") or "").strip()
    if status and status != "all":
        q["status"] = status
    if sp.get("asset_id"):
        q["asset_id"] = sp["asset_id"]
    search = (sp.get("search") or "").strip()
    if search:
        rx = {"$regex": search, "$options": "i"}
        q["$or"] = [{"loan_number": rx}, {"asset_number": rx}, {"asset_name": rx},
                    {"borrower_name": rx}, {"borrower_divisi": rx}, {"purpose": rx}]

    docs = await db[LOAN_COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    today = date.today()
    rows = [_decorate(d, today) for d in docs]
    if sp.get("overdue") in ("1", "true", "yes"):
        rows = [r for r in rows if r["is_overdue"]]
    return rows


@router.get("/loans/summary")
async def asset_loans_summary(request: Request):
    """KPI untuk header modul Peminjaman Alat."""
    await require_auth(request)
    db = get_db()
    today = date.today()
    month_prefix = today.isoformat()[:7]

    active = await db[LOAN_COLL].find({"status": "active"}, {"_id": 0}).to_list(1000)
    overdue = [a for a in active if (_d(a.get("expected_return_date")) or today) < today]
    returned_month = await db[LOAN_COLL].count_documents(
        {"status": "returned", "return_date": {"$regex": f"^{month_prefix}"}})
    available = await db.dewi_assets.count_documents({"status": {"$in": list(LOANABLE_STATUS)}})

    by_divisi: dict[str, int] = {}
    for a in active:
        key = (a.get("borrower_divisi") or "Tanpa Divisi").strip() or "Tanpa Divisi"
        by_divisi[key] = by_divisi.get(key, 0) + 1

    longest = 0
    for a in active:
        start = _d(a.get("loan_date")) or today
        longest = max(longest, (today - start).days)

    return {
        "active_loans": len(active),
        "overdue_loans": len(overdue),
        "returned_this_month": returned_month,
        "available_assets": available,
        "longest_out_days": longest,
        "by_divisi": [{"divisi": k, "count": v} for k, v in
                      sorted(by_divisi.items(), key=lambda kv: -kv[1])],
    }


@router.get("/loans/{loan_id}")
async def get_asset_loan(loan_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db[LOAN_COLL].find_one({"id": loan_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Data peminjaman tidak ditemukan.")
    return _decorate(doc)


# ─────────────────────────────────────────────────────────────────────────────
# CREATE
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/loans")
async def create_asset_loan(request: Request):
    """Pinjamkan 1 unit aset.
    Body: {asset_id*, borrower_name*, borrower_id?, borrower_divisi?, purpose?,
           loan_date?, expected_return_date?, notes?}
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    asset_id = (body.get("asset_id") or "").strip()
    borrower_name = (body.get("borrower_name") or "").strip()
    if not asset_id:
        raise HTTPException(400, "Aset wajib dipilih.")
    if not borrower_name:
        raise HTTPException(400, "Nama peminjam wajib diisi.")

    asset = await db.dewi_assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")
    a_status = (asset.get("status") or "active").lower()
    if a_status not in LOANABLE_STATUS:
        reason = _STATUS_REASON.get(a_status, f"status aset '{a_status}' tidak bisa dipinjam")
        raise HTTPException(400, f"Tidak bisa dipinjam: {reason}.")

    # Jaring kedua: pastikan tidak ada pinjaman aktif walau status aset terlanjur 'active'
    dup = await db[LOAN_COLL].find_one({"asset_id": asset_id, "status": "active"},
                                       {"_id": 0, "loan_number": 1, "borrower_name": 1})
    if dup:
        raise HTTPException(400, f"Aset ini masih dipinjam {dup.get('borrower_name', '')} "
                                 f"({dup.get('loan_number', '')}). Kembalikan dulu.")

    loan_date = (body.get("loan_date") or _today())[:10]
    expected = (body.get("expected_return_date") or "")[:10]
    ld, ed = _d(loan_date), _d(expected)
    if not ld:
        raise HTTPException(400, "Tanggal pinjam tidak valid (format YYYY-MM-DD).")
    if expected and not ed:
        raise HTTPException(400, "Target tanggal kembali tidak valid (format YYYY-MM-DD).")
    if ed and ed < ld:
        raise HTTPException(400, "Target tanggal kembali tidak boleh lebih awal dari tanggal pinjam.")

    year = ld.year
    loan_number = await gen_prefixed_number(db, LOAN_COLL, "loan_number", f"LOAN-AST-{year}-", 4)

    doc = {
        "id": _uid(),
        "loan_number": loan_number,
        "asset_id": asset_id,
        "asset_number": asset.get("asset_number", ""),
        "asset_name": asset.get("name", ""),
        "category_name": asset.get("category_name", ""),
        "borrower_id": (body.get("borrower_id") or "").strip(),
        "borrower_name": borrower_name,
        "borrower_divisi": (body.get("borrower_divisi") or "").strip(),
        "purpose": (body.get("purpose") or "").strip(),
        "loan_date": loan_date,
        "expected_return_date": expected,
        "status": "active",
        "condition_out": (body.get("condition_out") or "good").strip() or "good",
        "condition_in": None,
        "return_date": None,
        "return_notes": "",
        "returned_by_id": None,
        "returned_by_name": None,
        "notes": (body.get("notes") or "").strip(),
        "created_by": user.get("id", ""),
        "created_by_name": user.get("name", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[LOAN_COLL].insert_one(doc)
    await db.dewi_assets.update_one({"id": asset_id}, {"$set": {
        "status": "on_loan",
        "current_loan_id": doc["id"],
        "loaned_to_name": borrower_name,
        "loaned_expected_return": expected,
        "updated_at": _now(),
    }})
    await log_activity(user.get("id", ""), user.get("name", ""), "asset_loan_create", LOAN_COLL,
                       f"Pinjam {asset.get('asset_number', '')} → {borrower_name} ({loan_number})")
    return _decorate(doc)


# ─────────────────────────────────────────────────────────────────────────────
# RETURN
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/loans/{loan_id}/return")
async def return_asset_loan(loan_id: str, request: Request):
    """Terima kembali aset yang dipinjam.
    Body: {return_date?, condition? (good|damaged|lost), return_notes?}
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json() if await request.body() else {}

    loan = await db[LOAN_COLL].find_one({"id": loan_id}, {"_id": 0})
    if not loan:
        raise HTTPException(404, "Data peminjaman tidak ditemukan.")
    if loan.get("status") != "active":
        raise HTTPException(400, "Peminjaman ini sudah ditutup (aset sudah dikembalikan).")

    condition = (body.get("condition") or "good").strip().lower()
    if condition not in VALID_CONDITIONS:
        raise HTTPException(400, f"Kondisi tidak dikenal: '{condition}'. "
                                 f"Pilih salah satu: {', '.join(VALID_CONDITIONS)}.")
    return_date = (body.get("return_date") or _today())[:10]
    rd = _d(return_date)
    if not rd:
        raise HTTPException(400, "Tanggal kembali tidak valid (format YYYY-MM-DD).")
    ld = _d(loan.get("loan_date"))
    if ld and rd < ld:
        raise HTTPException(400, "Tanggal kembali tidak boleh lebih awal dari tanggal pinjam.")

    new_asset_status = _CONDITION_TO_STATUS[condition]
    await db[LOAN_COLL].update_one({"id": loan_id}, {"$set": {
        "status": "returned",
        "condition_in": condition,
        "return_date": return_date,
        "return_notes": (body.get("return_notes") or "").strip(),
        "returned_by_id": user.get("id", ""),
        "returned_by_name": user.get("name", ""),
        "updated_at": _now(),
    }})
    await db.dewi_assets.update_one({"id": loan.get("asset_id")}, {"$set": {
        "status": new_asset_status,
        "current_loan_id": None,
        "loaned_to_name": None,
        "loaned_expected_return": None,
        "updated_at": _now(),
    }})

    # Kondisi rusak → catat sebagai kebutuhan pemeliharaan supaya tidak hilang jejak
    if condition == "damaged":
        await db.dewi_asset_maintenance.insert_one({
            "id": _uid(),
            "asset_id": loan.get("asset_id"),
            "asset_name": loan.get("asset_name", ""),
            "type": "corrective",
            "description": f"Rusak saat dikembalikan dari peminjaman {loan.get('loan_number', '')} "
                           f"oleh {loan.get('borrower_name', '')}",
            "cost": 0.0,
            "performed_by": "",
            "maintenance_date": return_date,
            "next_scheduled": None,
            "status": "in_progress",
            "notes": (body.get("return_notes") or "").strip(),
            "created_by": user.get("id", ""),
            "created_at": _now(),
        })

    await log_activity(user.get("id", ""), user.get("name", ""), "asset_loan_return", LOAN_COLL,
                       f"Kembali {loan.get('asset_number', '')} dari {loan.get('borrower_name', '')} "
                       f"({loan.get('loan_number', '')}) kondisi={condition}")
    doc = await db[LOAN_COLL].find_one({"id": loan_id}, {"_id": 0})
    res = _decorate(doc)
    res["asset_status_after"] = new_asset_status
    res["maintenance_created"] = condition == "damaged"
    return res


# ─────────────────────────────────────────────────────────────────────────────
# ASET YANG BISA DIPINJAM (untuk dropdown form)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/loanable-assets")
async def loanable_assets(request: Request):
    """Daftar aset yang SIAP dipinjam (status active & tidak ada pinjaman aktif)."""
    await require_auth(request)
    db = get_db()
    active_ids = {a["asset_id"] async for a in
                  db[LOAN_COLL].find({"status": "active"}, {"_id": 0, "asset_id": 1})}
    rows = await db.dewi_assets.find(
        {"status": {"$in": list(LOANABLE_STATUS)}},
        {"_id": 0, "id": 1, "asset_number": 1, "name": 1, "category_name": 1,
         "location": 1, "serial_number": 1, "brand": 1, "model": 1},
    ).sort("asset_number", 1).to_list(1000)
    return [_ser(r) for r in rows if r["id"] not in active_ids]
