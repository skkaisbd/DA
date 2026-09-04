"""routes.marketing_change_log — LAYAR "SIAPA MENGUBAH APA" (F6.5).

KENAPA BERKAS INI ADA
---------------------
`marketing_change_log` sudah lahir di F5 dan sudah ditulis oleh SEMUA jalur yang
mengubah angka/kewenangan marketing (target, rencana anggaran, kunci periode,
assign staf toko). Tetapi sampai sesi #9 jejak itu hanya bisa dibaca dari **dua
sudut sempit**:

* panel kecil di dialog Siklus — hanya SATU toko × SATU bulan, 20 baris terakhir;
* tab Riwayat di layar Assign — hanya perubahan pemegang toko.

Akibatnya pertanyaan yang paling sering muncul di rapat tetap tidak terjawab:
*"siapa yang mengubah angka bulan lalu, kapan, dari berapa ke berapa, dan apa
alasannya?"* — untuk **semua** toko dan **semua** jenis perubahan sekaligus.
Jejak yang ada tetapi tidak bisa dicari sama saja dengan tidak ada.

YANG DIJAGA BERKAS INI
----------------------
1. **Lingkup F6 dihormati.** Staf berlingkup toko hanya melihat jejak toko yang
   di-assign kepadanya (`core.marketing_account_scope`). Jejak tanpa `account_id`
   (perubahan lintas-toko) **disembunyikan** dari staf berlingkup — dan itu
   DIKATAKAN di `data_notes`, bukan dibiarkan tampak seperti "tidak ada data".
2. **Total yang jujur.** Endpoint lama membalas `total = len(rows)` — jadi "50"
   berarti "50 baris pertama", bukan 50 perubahan. Di sini `total` dihitung
   `count_documents` dan halaman dilaporkan apa adanya.
3. **Nilai LAMA → BARU per field, bukan dua blob JSON.** Layar tidak boleh
   memaksa pembacanya membandingkan dua dokumen sendiri.
4. **id ⇒ nama.** Jejak assign menyimpan **id user**. Menampilkan uuid di layar
   audit sama dengan tidak menjawab "siapa" — jadi id diterjemahkan ke nama.
5. **READ-ONLY.** Tidak ada endpoint tulis di sini; jejak tidak boleh bisa
   disunting dari layar mana pun (itulah gunanya jejak).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request

from auth import require_auth, serialize_doc
from core import marketing_account_scope as _scope
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/change-log", tags=["Marketing-ChangeLog"])

COLL = "marketing_change_log"
ACCOUNTS = "marketing_platform_accounts"

# Label manusiawi — staf tidak mengenal nama koleksi/aksi.
ENTITY_LABEL = {
    "marketing_account_targets": "Target toko",
    "marketing_budgets": "Rencana anggaran",
    "marketing_period_locks": "Kunci periode",
    "marketing_platform_accounts": "Kewenangan toko (assign staf)",
    "marketing_creator_targets": "Target kreator",
    "marketing_data_import_sessions": "Sesi impor",
}
ACTION_LABEL = {
    "target_create": "Target dibuat",
    "target_update": "Target diubah",
    "budget_upsert": "Rencana anggaran diubah",
    "period_close": "Periode ditutup",
    "period_reopen": "Periode dibuka",
    "assign_staff": "Staf pemegang toko diubah",
    "assign_staff_noop": "Assign disimpan tanpa perubahan",
}
FIELD_LABEL = {
    "revenue_target": "Target omzet",
    "orders_target": "Target pesanan",
    "units_target": "Target pcs",
    "health_score_target": "Target skor kesehatan",
    "notes": "Catatan",
    "budget_by_category": "Anggaran per kategori",
    "assigned_staff": "Daftar staf pemegang",
    "added": "Staf ditambahkan",
    "removed": "Staf dicabut",
    "locked": "Status kunci",
    # kategori anggaran (before/after dokumen anggaran adalah dict per kategori)
    "ads": "Anggaran iklan", "kol": "Anggaran KOL", "komisi": "Anggaran komisi",
    "livehost": "Anggaran host live", "sample": "Anggaran sample",
    "diskon": "Anggaran diskon",
}
# Aksi yang MENGUBAH KEWENANGAN (bukan angka) — dibedakan di layar karena
# pertanyaannya berbeda: "kenapa akses toko saya dicabut?" vs "kok targetnya beda?".
PERMISSION_ACTIONS = ("assign_staff", "assign_staff_noop")


def _ser(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _empty(v: Any) -> bool:
    """`None`, teks kosong, daftar/objek kosong = "tidak ada isinya".

    KENAPA PERLU: dokumen `before` kadang belum punya field-nya sama sekali
    (`None`) sementara `after` mengisinya dengan daftar KOSONG (`[]`). Tanpa
    penyamaan ini, layar audit menampilkan baris "Staf dicabut: belum ada →
    kosong" — pembacanya mencari pencabutan yang sebenarnya tidak pernah terjadi.
    """
    return v is None or v == "" or v == [] or v == {}


def _diff(before: Any, after: Any) -> List[dict]:
    """Ubah dua dokumen menjadi daftar `field: lama → baru` (hanya yang BERUBAH)."""
    out: List[dict] = []
    if isinstance(before, dict) or isinstance(after, dict):
        b = before if isinstance(before, dict) else {}
        a = after if isinstance(after, dict) else {}
        for k in sorted(set(b) | set(a)):
            bv, av = _ser(b.get(k)), _ser(a.get(k))
            if bv == av or (_empty(bv) and _empty(av)):
                continue
            out.append({"field": k, "field_label": FIELD_LABEL.get(k, k),
                        "before": bv, "after": av,
                        "is_money": k in ("revenue_target",),
                        "is_list": isinstance(bv, list) or isinstance(av, list)})
    elif before != after and not (_empty(before) and _empty(after)):
        out.append({"field": "", "field_label": "Nilai", "before": _ser(before),
                    "after": _ser(after), "is_money": False, "is_list": False})
    return out


@router.get("")
async def list_change_log(
    request: Request,
    account_id: Optional[str] = Query(None, description="kosong = semua toko yang boleh dilihat"),
    entity: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    period: Optional[str] = Query(None, description="YYYY-MM"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD (waktu perubahan)"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD (inklusif)"),
    q: Optional[str] = Query(None, description="cari di alasan / nama pelaku / toko"),
    only_permissions: bool = Query(False, description="hanya perubahan KEWENANGAN"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
):
    """Jejak perubahan marketing — semua toko, semua jenis, bisa dicari & dihalaman."""
    user = await require_auth(request)
    db = get_db()

    query: Dict[str, Any] = {}
    scoped_hidden_global = False
    if account_id:
        await _scope.assert_account_visible(db, user, account_id)
        query["account_id"] = account_id
    else:
        visible = await _scope.visible_account_ids(db, user)
        if visible is not None:
            # Jejak tanpa `account_id` = perubahan lintas-toko ⇒ bukan wilayah
            # staf berlingkup. Disembunyikan, dan disebut di `data_notes`.
            query["account_id"] = {"$in": visible}
            scoped_hidden_global = True
    if entity:
        query["entity"] = entity
    if action:
        query["action"] = action
    elif only_permissions:
        query["action"] = {"$in": list(PERMISSION_ACTIONS)}
    if actor_id:
        query["actor_id"] = actor_id
    if period:
        query["period"] = period
    if date_from or date_to:
        rng: Dict[str, Any] = {}
        if date_from:
            rng["$gte"] = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if date_to:
            end = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            rng["$lte"] = end.replace(hour=23, minute=59, second=59)
        query["at"] = rng
    if q:
        rx = {"$regex": q.strip(), "$options": "i"}
        query["$or"] = [{"reason": rx}, {"actor_name": rx}, {"actor_role": rx},
                        {"entity": rx}, {"action": rx}]

    total = await db[COLL].count_documents(query)
    rows = await db[COLL].find(query, {"_id": 0}).sort("at", -1).skip(
        (page - 1) * page_size).limit(page_size).to_list(page_size)

    # id → nama (toko & user) supaya layar audit menjawab "siapa", bukan uuid
    acc_ids = {r.get("account_id") for r in rows if r.get("account_id")}
    accs = {a["id"]: a for a in await db[ACCOUNTS].find(
        {"id": {"$in": list(acc_ids)}},
        {"_id": 0, "id": 1, "account_name": 1, "account_code": 1, "platform": 1}
    ).to_list(500)} if acc_ids else {}
    uid_set: set = set()
    for r in rows:
        for blob in (r.get("before"), r.get("after")):
            if isinstance(blob, dict):
                for k in ("assigned_staff", "added", "removed"):
                    v = blob.get(k)
                    if isinstance(v, list):
                        uid_set.update(str(x) for x in v if x)
    users = {u["id"]: (u.get("name") or u.get("full_name") or u.get("email") or u["id"])
             for u in await db.users.find(
                 {"id": {"$in": list(uid_set)}},
                 {"_id": 0, "id": 1, "name": 1, "full_name": 1, "email": 1}
             ).to_list(500)} if uid_set else {}

    def names(v: Any) -> Any:
        if isinstance(v, list):
            return [users.get(str(x), str(x)) for x in v]
        return v

    out: List[dict] = []
    for r in rows:
        acc = accs.get(r.get("account_id")) or {}
        changes = _diff(r.get("before"), r.get("after"))
        for c in changes:
            if c["field"] in ("assigned_staff", "added", "removed"):
                c["before"], c["after"] = names(c["before"]), names(c["after"])
        act = r.get("action") or ""
        out.append({
            "id": r.get("id"),
            "at": _ser(r.get("at")),
            "account_id": r.get("account_id") or "",
            "account_name": acc.get("account_name") or ("(lintas toko)"
                                                        if not r.get("account_id") else "—"),
            "account_code": acc.get("account_code") or "",
            "platform": acc.get("platform") or "",
            "entity": r.get("entity") or "",
            "entity_label": ENTITY_LABEL.get(r.get("entity") or "", r.get("entity") or ""),
            "entity_id": r.get("entity_id") or "",
            "action": act,
            "action_label": ACTION_LABEL.get(act, act),
            "kind": "kewenangan" if act in PERMISSION_ACTIONS else "angka",
            "period": r.get("period") or "",
            "actor_id": r.get("actor_id") or "",
            "actor_name": r.get("actor_name") or "—",
            "actor_role": r.get("actor_role") or "",
            "reason": r.get("reason") or "",
            "changes": changes,
            "changes_count": len(changes),
        })

    # Pilihan filter DIHITUNG dari data yang boleh dilihat pemakai ini — bukan
    # daftar tetap yang bisa memuat nilai yang tidak pernah ada di DB.
    base_scope = {k: v for k, v in query.items()
                  if k in ("account_id",)} if query.get("account_id") else {}
    entities = await db[COLL].distinct("entity", base_scope)
    actions = await db[COLL].distinct("action", base_scope)
    actor_rows = await db[COLL].aggregate([
        {"$match": base_scope or {}},
        {"$group": {"_id": {"id": "$actor_id", "name": "$actor_name",
                            "role": "$actor_role"}, "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 50},
    ]).to_list(50)

    notes = [
        "Jejak ini READ-ONLY dan tidak bisa disunting dari layar mana pun — itulah "
        "gunanya jejak. Setiap baris menyimpan nilai LAMA dan BARU beserta nama, "
        "peran, waktu, dan alasan pelakunya.",
        "Perubahan KEWENANGAN (siapa pemegang toko) dan perubahan ANGKA (target, "
        "anggaran, kunci periode) ditandai berbeda karena pertanyaannya berbeda.",
    ]
    if scoped_hidden_global:
        notes.append("Anda melihat jejak untuk toko yang di-assign kepada Anda saja. "
                     "Perubahan lintas-toko (tanpa toko tertentu) TIDAK ditampilkan — "
                     "itu bukan berarti tidak ada.")
    if total == 0:
        notes.append("Tidak ada baris yang cocok dengan filter ini. Kalau Anda yakin "
                     "perubahannya terjadi, longgarkan filter tanggal/toko — jejak "
                     "tidak pernah dihapus oleh aplikasi.")

    return serialize_doc({
        "ok": True,
        "rows": out,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "filters": {
            "entities": [{"value": e, "label": ENTITY_LABEL.get(e, e)}
                         for e in sorted(x for x in entities if x)],
            "actions": [{"value": a, "label": ACTION_LABEL.get(a, a)}
                        for a in sorted(x for x in actions if x)],
            "actors": [{"id": (a["_id"] or {}).get("id") or "",
                        "name": (a["_id"] or {}).get("name") or "—",
                        "role": (a["_id"] or {}).get("role") or "",
                        "count": a["n"]}
                       for a in actor_rows if (a["_id"] or {}).get("id")],
        },
        "data_notes": notes,
    })


@router.get("/stats")
async def change_log_stats(request: Request,
                           days: int = Query(30, ge=1, le=365)):
    """Ringkasan untuk kartu di atas tabel: berapa perubahan, oleh berapa orang."""
    user = await require_auth(request)
    db = get_db()
    since = datetime.now(timezone.utc).timestamp() - days * 86400
    since_dt = datetime.fromtimestamp(since, tz=timezone.utc)
    query: Dict[str, Any] = {"at": {"$gte": since_dt}}
    visible = await _scope.visible_account_ids(db, user)
    if visible is not None:
        query["account_id"] = {"$in": visible}
    total = await db[COLL].count_documents(query)
    perm = await db[COLL].count_documents({**query,
                                           "action": {"$in": list(PERMISSION_ACTIONS)}})
    no_reason = await db[COLL].count_documents({**query, "$or": [
        {"reason": ""}, {"reason": {"$exists": False}}]})
    actors = len(await db[COLL].distinct("actor_id", query))
    accounts = len([a for a in await db[COLL].distinct("account_id", query) if a])
    return serialize_doc({
        "ok": True, "days": days,
        "total": total, "permission_changes": perm, "number_changes": total - perm,
        "actors": actors, "accounts_touched": accounts,
        "without_reason": no_reason,
        "data_notes": [
            f"{no_reason} dari {total} perubahan tercatat TANPA alasan. Alasan wajib "
            "hanya pada jalur yang menyentuh kewenangan (assign staf) dan kunci "
            "periode; jalur lain masih boleh kosong — itu batas yang diketahui, "
            "bukan data yang hilang." if total else
            "Belum ada perubahan tercatat pada rentang ini.",
        ],
    })
