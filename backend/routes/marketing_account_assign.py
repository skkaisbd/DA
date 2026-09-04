"""marketing_account_assign — **Assign Toko (SPV)**: siapa memegang toko yang mana.

KENAPA LAYAR/ENDPOINT INI ADA (F6.4, 2026-08-13)
------------------------------------------------
F6 sudah menegakkan *visibilitas per toko*: staf hanya melihat toko yang
`pic_id`-nya dia atau yang id-nya ada di `assigned_staff`. Tetapi sampai sekarang
**tidak ada satu pun jalan aplikasi untuk MENGISI `assigned_staff`** — nilainya
hanya bisa berubah lewat skrip seed. Akibatnya aturan F6 benar di kode tapi tidak
bisa dipakai: staf baru tidak pernah bisa diberi toko, dan staf yang pindah tugas
tidak pernah bisa dicabut aksesnya.

ATURAN
------
1. **Hanya SPV/Manager/owner** yang boleh mengubah (sama dengan yang boleh
   menetapkan target, `scope.can_write_target`). Staf boleh MELIHAT daftar
   tokonya sendiri, tidak boleh mengubah.
2. **Setiap perubahan meninggalkan jejak** di `marketing_change_log`
   (`entity=marketing_platform_accounts`, `action=assign_staff`) berisi daftar
   LAMA & BARU + nama/peran pelaku + alasan. Tanpa ini, "siapa yang mencabut
   akses toko saya?" tidak akan pernah bisa dijawab.
3. **Kandidat staf tidak dikarang**: hanya pemakai yang perannya memang berlingkup
   toko (`scope.SCOPED_ROLES`) yang bisa di-assign. Meng-assign peran yang sudah
   melihat SEMUA toko tidak menambah apa pun dan hanya menyesatkan.
4. **Efek langsung**: begitu di-unassign, endpoint bertoko (siklus, pesanan,
   KPI) menjawab 403 untuk staf itu — dibuktikan test `test_core_f7_kpi_impor.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import require_auth, serialize_doc
from core import marketing_account_scope as scope
from core import marketing_cycle as cycle
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/account-assign", tags=["Marketing-AccountAssign"])

ACCOUNTS = scope.ACCOUNTS
CHANGE_LOG = cycle.CHANGE_LOG


class AssignIn(BaseModel):
    staff_ids: List[str] = Field(default_factory=list)
    reason: Optional[str] = ""


# Alasan sependek "ok" tidak menjelaskan apa pun ketika dibaca enam bulan
# kemudian. Batas 4 huruf sengaja RENDAH: yang dituntut adalah kalimat, bukan
# esai — tetapi kolom kosong tidak boleh lewat (lihat `set_assignment`).
MIN_REASON = 4


def _user(request: Request) -> dict:
    return getattr(request.state, "user", {}) or {}


async def _assert_can_assign(user: dict) -> None:
    if scope.can_write_target(user):
        return
    raise HTTPException(
        403, "Hanya SPV/Manager Marketing (atau owner/admin) yang boleh mengubah "
             "pemegang toko. Staf melihat toko yang di-assign kepadanya.")


async def _staff_index(db) -> Dict[str, dict]:
    rows = await db.users.find(
        {"role": {"$in": list(scope.SCOPED_ROLES)}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "status": 1},
    ).to_list(500)
    return {r["id"]: r for r in rows if r.get("id")}


def _is_inactive(u: dict) -> bool:
    """Akun pemakai yang sudah dimatikan.

    Penting untuk DITANDAI (bukan ditolak): toko yang staf pemegangnya nonaktif
    tampak "sudah ada yang pegang" padahal tidak ada satu orang pun yang bisa
    login untuk mengisi datanya — persis kelas kesalahan yang membuat laporan
    harian toko itu kosong tanpa satu pun peringatan.
    """
    st = str((u or {}).get("status") or "").lower()
    return st not in ("", "active", "aktif")


@router.get("/staff-options")
async def staff_options(request: Request):
    """Kandidat staf yang MASUK AKAL untuk di-assign (peran berlingkup toko)."""
    user = await require_auth(request)
    db = get_db()
    idx = await _staff_index(db)
    counts: Dict[str, int] = {}
    async for a in db[ACCOUNTS].find({}, {"_id": 0, "assigned_staff": 1, "pic_id": 1}):
        for sid in (a.get("assigned_staff") or []):
            counts[sid] = counts.get(sid, 0) + 1
    out = [{**s, "accounts_assigned": counts.get(s["id"], 0)} for s in idx.values()]
    out.sort(key=lambda r: (r.get("name") or "").lower())
    return serialize_doc({
        "success": True,
        "options": out,
        "can_edit": scope.can_write_target(user),
        "scoped_roles": list(scope.SCOPED_ROLES),
        "all_access_roles": list(scope.ALL_ACCOUNTS_ROLES),
        "note": ("Peran seperti SPV/Manager/Accounting sudah melihat SEMUA toko, "
                 "jadi tidak perlu (dan tidak bisa) di-assign per toko."),
    })


@router.get("/overview")
async def overview(request: Request, include_inactive: bool = Query(True)):
    """Daftar toko + pemegangnya. Dibatasi visibilitas pemakai (F6)."""
    user = await require_auth(request)
    db = get_db()
    q: Dict[str, Any] = {}
    if not include_inactive:
        q["status"] = "active"
    q = await scope.scope_filter(db, user, q, field="id")
    accounts = await db[ACCOUNTS].find(
        q, {"_id": 0, "id": 1, "account_name": 1, "account_code": 1, "platform": 1,
            "status": 1, "assigned_staff": 1, "pic_id": 1, "pic_user_id": 1,
            "pic_user_name": 1},
    ).sort("account_name", 1).to_list(300)
    idx = await _staff_index(db)
    # PIC bisa berperan apa pun (mis. manager) — namanya diambil dari users supaya
    # kolom "PIC" tidak pernah menampilkan UUID mentah.
    pic_ids = {a.get("pic_id") or a.get("pic_user_id") for a in accounts}
    pics = {u["id"]: u for u in await db.users.find(
        {"id": {"$in": [p for p in pic_ids if p]}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}).to_list(300)}
    rows = []
    for a in accounts:
        staff = []
        for sid in (a.get("assigned_staff") or []):
            s = idx.get(sid)
            staff.append(s if s else {"id": sid, "name": "(pemakai sudah dihapus)",
                                      "email": "", "role": "", "status": "unknown"})
        for s in staff:
            s["inactive"] = _is_inactive(s)
        pid = a.get("pic_id") or a.get("pic_user_id")
        rows.append({
            "id": a["id"], "account_name": a.get("account_name"),
            "account_code": a.get("account_code"), "platform": a.get("platform"),
            "status": a.get("status"),
            "assigned_staff": staff,
            "assigned_count": len(staff),
            # jumlah pemegang yang TIDAK bisa login lagi — toko ini praktisnya
            # tidak ada yang memegang walau kolomnya terisi.
            "inactive_count": sum(1 for s in staff if s.get("inactive")),
            "active_count": sum(1 for s in staff if not s.get("inactive")),
            "pic": pics.get(pid) or ({"id": pid, "name": a.get("pic_user_name") or ""}
                                     if pid else None),
        })
    unassigned = [r["account_name"] for r in rows if r["assigned_count"] == 0]
    stale = [r["account_name"] for r in rows
             if r["assigned_count"] > 0 and r["active_count"] == 0]
    notes = [
        "Staf tanpa toko tidak melihat data apa pun (bukan 'data kosong') — "
        "itu sebabnya assign harus dilakukan sebelum staf mulai bekerja.",
        "PIC toko tetap melihat tokonya walau tidak ada di daftar staf.",
        "Setiap perubahan WAJIB memakai alasan singkat; alasan itulah yang "
        "menjawab 'kenapa akses toko saya dicabut?' di Riwayat.",
    ]
    if stale:
        notes.append("Toko yang seluruh pemegangnya berakun NONAKTIF dihitung "
                     "belum terpegang: " + ", ".join(stale[:5])
                     + (" …" if len(stale) > 5 else ""))
    return serialize_doc({
        "success": True, "rows": rows, "total": len(rows),
        "can_edit": scope.can_write_target(user),
        "unassigned_count": len(unassigned),
        "stale_count": len(stale),
        "data_notes": notes,
    })


@router.get("/by-staff")
async def by_staff(request: Request):
    """Sudut pandang KEBALIKAN: satu staf memegang toko apa saja.

    Kenapa perlu tampilan sendiri: rotasi shift dan staf resign selalu ditanyakan
    per ORANG ("Rina pegang toko apa saja sekarang?"), sementara daftar per-toko
    memaksa SPV membuka 9 baris untuk menjawabnya. Yang lebih penting: staf yang
    memegang **0 toko** tidak muncul di mana pun pada tampilan per-toko — padahal
    justru dia yang membuka aplikasi dan melihat layar kosong tanpa penjelasan.
    """
    user = await require_auth(request)
    db = get_db()
    idx = await _staff_index(db)
    q = await scope.scope_filter(db, user, {}, field="id")
    accounts = await db[ACCOUNTS].find(
        q, {"_id": 0, "id": 1, "account_name": 1, "account_code": 1, "platform": 1,
            "status": 1, "assigned_staff": 1}).to_list(300)
    held: Dict[str, List[dict]] = {}
    for a in accounts:
        for sid in (a.get("assigned_staff") or []):
            held.setdefault(sid, []).append({
                "id": a["id"], "account_name": a.get("account_name"),
                "account_code": a.get("account_code"),
                "platform": a.get("platform"), "status": a.get("status")})
    rows = []
    for s in idx.values():
        acc = held.get(s["id"]) or []
        acc.sort(key=lambda x: (x.get("account_name") or "").lower())
        rows.append({**s, "inactive": _is_inactive(s),
                     "accounts": acc, "accounts_count": len(acc)})
    # yang belum punya toko naik ke atas: itu daftar kerja SPV, bukan sisa daftar
    rows.sort(key=lambda r: (r["accounts_count"] > 0, (r.get("name") or "").lower()))
    # staf yang di-assign tapi sudah tidak ada di master pemakai
    ghosts = sorted({sid for sid in held if sid not in idx})
    return serialize_doc({
        "success": True, "rows": rows, "total": len(rows),
        "can_edit": scope.can_write_target(user),
        "without_account": [r["name"] for r in rows if r["accounts_count"] == 0],
        "ghost_staff_ids": ghosts,
        "data_notes": [
            "Staf yang memegang 0 toko TIDAK melihat data apa pun — layarnya kosong "
            "tanpa penjelasan sampai SPV meng-assign tokonya.",
            "Peran SPV/Manager/Accounting tidak muncul di sini karena sudah melihat "
            "SEMUA toko; meng-assign mereka per toko tidak menambah apa pun.",
        ] + (["Ada id staf yang masih ter-assign tetapi sudah tidak ada di master "
              "pemakai — buka toko terkait dan simpan ulang daftarnya."] if ghosts else []),
    })


@router.get("/history")
async def history_all(request: Request,
                      page: int = Query(1, ge=1),
                      page_size: int = Query(10, ge=1, le=100),
                      account_id: Optional[str] = Query(None)):
    """Riwayat perubahan pemegang toko untuk SEMUA toko yang boleh dilihat.

    Riwayat per-toko sudah ada, tetapi pertanyaan yang paling sering muncul
    ("apa saja yang berubah minggu ini?") tidak bisa dijawab tanpa membuka satu
    per satu 9 dialog. Dibatasi visibilitas (F6) dan berpaginasi.
    """
    user = await require_auth(request)
    db = get_db()
    if account_id:
        await scope.assert_account_visible(db, user, account_id)
        acc_ids: Optional[List[str]] = [account_id]
    else:
        acc_ids = await scope.visible_account_ids(db, user)
    q: Dict[str, Any] = {"entity": ACCOUNTS,
                         "action": {"$in": ["assign_staff", "assign_staff_noop"]}}
    if acc_ids is not None:
        q["account_id"] = {"$in": acc_ids}
    total = await db[CHANGE_LOG].count_documents(q)
    rows = await db[CHANGE_LOG].find(q, {"_id": 0}).sort("at", -1).skip(
        (page - 1) * page_size).limit(page_size).to_list(page_size)
    idx = await _staff_index(db)
    names = {a["id"]: a.get("account_name") for a in await db[ACCOUNTS].find(
        {"id": {"$in": [r.get("account_id") for r in rows if r.get("account_id")]}},
        {"_id": 0, "id": 1, "account_name": 1}).to_list(300)}

    def _names(ids) -> List[str]:
        return [(idx.get(i, {}).get("name") or i) for i in (ids or [])]

    for r in rows:
        r["account_name"] = names.get(r.get("account_id")) or "(toko sudah dihapus)"
        r["before_names"] = _names((r.get("before") or {}).get("assigned_staff"))
        r["after_names"] = _names((r.get("after") or {}).get("assigned_staff"))
        r["added_names"] = _names((r.get("after") or {}).get("added"))
        r["removed_names"] = _names((r.get("after") or {}).get("removed"))
    return serialize_doc({
        "success": True, "rows": rows, "total": total,
        "pagination": {"page": page, "page_size": page_size, "total": total,
                       "total_pages": max(1, (total + page_size - 1) // page_size)},
    })


@router.get("/{account_id}/history")
async def history(account_id: str, request: Request,
                  limit: int = Query(50, ge=1, le=200)):
    """Riwayat assign/unassign satu toko (jejak F6)."""
    user = await require_auth(request)
    db = get_db()
    await scope.assert_account_visible(db, user, account_id)
    rows = await db[CHANGE_LOG].find(
        {"account_id": account_id, "entity": ACCOUNTS,
         "action": {"$in": ["assign_staff", "assign_staff_noop"]}},
        {"_id": 0},
    ).sort("at", -1).to_list(limit)
    idx = await _staff_index(db)

    def _names(ids) -> List[str]:
        return [(idx.get(i, {}).get("name") or i) for i in (ids or [])]

    for r in rows:
        r["before_names"] = _names((r.get("before") or {}).get("assigned_staff"))
        r["after_names"] = _names((r.get("after") or {}).get("assigned_staff"))
    return serialize_doc({"success": True, "rows": rows, "total": len(rows)})


@router.post("/{account_id}")
async def set_assignment(account_id: str, body: AssignIn, request: Request):
    """Tetapkan daftar staf pemegang toko (menggantikan daftar lama) + jejak."""
    user = await require_auth(request)
    await _assert_can_assign(user)
    db = get_db()
    acc = await db[ACCOUNTS].find_one({"id": account_id}, {"_id": 0})
    if not acc:
        raise HTTPException(404, "Akun toko tidak ditemukan")

    idx = await _staff_index(db)
    wanted, unknown, wrong_role = [], [], []
    for sid in dict.fromkeys(body.staff_ids or []):
        if sid in idx:
            wanted.append(sid)
            continue
        u = await db.users.find_one({"id": sid}, {"_id": 0, "id": 1, "role": 1, "name": 1})
        (wrong_role if u else unknown).append(u.get("name") if u else sid)
    if unknown:
        raise HTTPException(400, "Pemakai berikut tidak ada di master pemakai: "
                                 + ", ".join(map(str, unknown)))
    if wrong_role:
        raise HTTPException(
            400, "Peran berikut tidak berlingkup toko (sudah melihat semua toko), "
                 "jadi tidak perlu di-assign: " + ", ".join(map(str, wrong_role))
                 + ". Peran yang bisa di-assign: " + ", ".join(scope.SCOPED_ROLES))

    # ── ALASAN WAJIB (2026-08-14) ────────────────────────────────────────────
    # Sebelumnya `reason` opsional. Akibatnya jejak boleh lahir tanpa sebab, dan
    # satu-satunya pertanyaan yang benar-benar ditanyakan staf ("kenapa akses
    # toko saya dicabut?") tetap tidak terjawab walaupun riwayatnya lengkap.
    # Diperiksa SESUDAH validasi daftar staf supaya pesan galat yang lebih
    # spesifik (peran salah / pemakai tak ada) tidak tertutup oleh pesan ini.
    reason = (body.reason or "").strip()
    if len(reason) < MIN_REASON:
        raise HTTPException(
            400, "Alasan perubahan wajib diisi (minimal "
                 f"{MIN_REASON} huruf) — alasan inilah yang menjawab “kenapa akses "
                 "toko saya dicabut?” di Riwayat. Contoh: “rotasi shift Agustus”, "
                 "“staf resign”, “tambah PIC live”.")

    inactive_now = [idx[s].get("name") or s for s in wanted
                    if s in idx and _is_inactive(idx[s])]

    before = list(acc.get("assigned_staff") or [])
    if sorted(before) == sorted(wanted):
        await cycle.log_change(
            db, account_id=account_id, entity=ACCOUNTS, entity_id=account_id,
            action="assign_staff_noop", before={"assigned_staff": before},
            after={"assigned_staff": wanted}, reason=reason, user=user)
        return serialize_doc({
            "success": True, "changed": False,
            "message": "Tidak ada perubahan — daftar staf toko ini sudah sama.",
            "warnings": ([f"Akun berikut NONAKTIF, jadi tidak ada orang yang bisa "
                          f"login untuk toko ini: {', '.join(inactive_now)}"]
                         if inactive_now else []),
            "assigned_staff": [idx[s] for s in wanted if s in idx]})

    await db[ACCOUNTS].update_one({"id": account_id},
                                 {"$set": {"assigned_staff": wanted,
                                           "updated_at": datetime.now(timezone.utc)}})
    added = [s for s in wanted if s not in before]
    removed = [s for s in before if s not in wanted]
    await cycle.log_change(
        db, account_id=account_id, entity=ACCOUNTS, entity_id=account_id,
        action="assign_staff",
        before={"assigned_staff": before},
        after={"assigned_staff": wanted, "added": added, "removed": removed},
        reason=reason, user=user)
    logger.info("[assign_toko] %s: +%s -%s oleh %s", acc.get("account_name"),
                len(added), len(removed), user.get("email"))
    warnings: List[str] = []
    if inactive_now:
        warnings.append("Akun berikut NONAKTIF, jadi tidak ada orang yang bisa login "
                        "untuk toko ini: " + ", ".join(inactive_now))
    if not wanted:
        warnings.append("Toko ini sekarang TIDAK dipegang siapa pun. Data hariannya "
                        "hanya bisa diisi oleh SPV/Manager sampai ada staf di-assign.")
    return serialize_doc({
        "success": True, "changed": True,
        "message": (f"{len(added)} staf ditambahkan, {len(removed)} dicabut pada "
                    f"{acc.get('account_name')}."),
        "added": [idx.get(s, {"id": s}) for s in added],
        "removed": [idx.get(s, {"id": s}) for s in removed],
        "assigned_staff": [idx[s] for s in wanted if s in idx],
        "warnings": warnings,
        "reason": reason,
        "effect_note": ("Staf yang dicabut langsung kehilangan akses: endpoint "
                        "bertoko menjawab 403 pada permintaan berikutnya."),
    })
