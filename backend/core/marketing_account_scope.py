"""core.marketing_account_scope — **SSOT lingkup toko/akun untuk SELURUH marketing**.

MASALAH YANG DISELESAIKAN BERKAS INI
------------------------------------
Aturan bisnisnya sederhana dan tidak pernah diperdebatkan: **setiap baris data
marketing milik satu toko/akun**. Order itu order milik akun Shopee mana; biaya
iklan itu biaya akun TikTok mana; sesi live itu sesi di akun mana, dibawakan host
siapa. Tanpa itu, pertanyaan pertama setiap rapat — "toko mana yang untung?" —
tidak bisa dijawab.

Audit 2026-08-11 (`memory/AUDIT_MARKETING_PORTAL_2026-08-11.md`) mengukur bahwa
aturan itu **tidak ditegakkan di mana-mana**, dan tiap modul memutuskan sendiri:

* `marketing_orders`         — 60/60 dokumen `account_id` KOSONG (hanya `account_name` teks)
* `marketing_samples`        — 35/35 KOSONG (field-nya bahkan tidak ada di model)
* `marketing_ads_data`       — 25/25 KOSONG
* `marketing_live_sessions`  — 18/18 KOSONG (juga `host_id` & `creator_id`)
* `marketing_content_calendar` — 30/30 KOSONG (modelnya punya, penulisnya tidak mengisi)
* `marketing_discounts`      — 10/10 KOSONG (idem)
* `marketing_reviews/returns/complaints/account_health` — BENAR

Akibat yang bisa ditunjuk di layar, bukan teori:

1. **Filter "per akun" membuang semua baris.** Layar Order Terpadu punya pemilih
   akun; kueri-nya `{'account_id': <id>}`. Karena tidak ada dokumen yang punya
   `account_id`, daftar jadi KOSONG padahal 60 order ada. Tidak ada error —
   staf hanya menyimpulkan "datanya hilang".
2. **Laporan per toko melaporkan Rp 0.** Rekap per akun menjumlahkan dengan
   `account_id`; nol dokumen cocok ⇒ nol rupiah. Angka nol yang salah lebih
   berbahaya daripada error, karena ikut dibawa ke keputusan.
3. **Nama toko diketik ulang di tiap form.** `account_name` teks bebas berarti
   "DA Official Shopee" dan "DA Offical Shopee" jadi dua toko yang berbeda di
   laporan, dan tidak ada yang tahu mana yang benar.

APA YANG BERKAS INI BERIKAN
---------------------------
Satu tempat untuk semua pertanyaan lingkup akun, supaya tidak ada lagi endpoint
yang menebak sendiri:

* :func:`resolve_account`      — dari `account_id` ATAU `account_name`/`account_code`/
  `username` (mis. baris file impor) → dokumen akun yang SAH. Satu jalan masuk.
* :func:`stamp_account`        — menuliskan `account_id` + `account_name` + `platform`
  ke dokumen. `account_name`/`platform` **selalu turunan** dari master, jadi
  denormalisasi untuk tampilan tetap boleh tanpa risiko dua ejaan.
* :func:`require_account`      — HTTP 400/404 yang jelas bila akun tidak diberikan
  atau tidak ada. Lebih baik ditolak keras daripada menyimpan baris yatim.
* :func:`assert_creator_assigned` / :func:`assert_host_assigned` — menegakkan
  keputusan owner: kreator/host yang dipilih **harus sudah di-assign ke toko itu**.
  Kalau tidak ditegakkan, biaya KOL dan gaji host akan dibebankan ke toko yang
  tidak pernah memakai orangnya.
* :func:`account_options`      — daftar akun siap-pakai untuk pemilih di layar,
  supaya layar tidak lagi menyalin daftar toko sendiri.

KENAPA MENERJEMAHKAN NAMA → ID, BUKAN MELARANG NAMA
---------------------------------------------------
File impor dari Shopee/TikTok tidak pernah membawa `account_id` milik kita; yang
ada hanya nama toko. Karena itu :func:`resolve_account` menerima nama **sebagai
jalan masuk yang sah**, tetapi hasil yang DISIMPAN selalu `account_id`. Dengan
begitu satu kolom tidak pernah lagi menyimpan dua ruang-identitas.
"""
from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

logger = logging.getLogger(__name__)

ACCOUNTS = "marketing_platform_accounts"
CREATORS = "marketing_kol_creators"
HOSTS = "marketing_livehosts"


# ── normalisasi teks ─────────────────────────────────────────────────────────
def norm(s: Any) -> str:
    """Normalisasi untuk PEMBANDINGAN saja (yang disimpan tetap apa adanya).

    "DA Official Shopee " · "da official shopee" · "DA  Official-Shopee"
    → "daofficialshopee". Ini yang membuat "salah spasi" tidak melahirkan toko baru.
    """
    if s is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())


# ── indeks akun (satu query, dipakai berulang) ───────────────────────────────
async def account_index(db) -> Dict[str, Any]:
    """Bangun indeks akun sekali untuk dipakai banyak baris (impor bisa ribuan baris).

    Mengembalikan dict berisi:
      by_id   : {account_id: doc}
      by_name : {norm(account_name): doc}
      by_code : {norm(account_code): doc}
      by_user : {norm(username): doc}
      docs    : [doc, ...] urut nama
    """
    docs = await db[ACCOUNTS].find({}, {"_id": 0}).to_list(2000)
    by_id, by_name, by_code, by_user = {}, {}, {}, {}
    for d in docs:
        aid = d.get("id")
        if not aid:
            continue
        by_id[aid] = d
        for key, bucket in (("account_name", by_name), ("account_code", by_code),
                            ("username", by_user)):
            v = norm(d.get(key))
            if v and v not in bucket:
                bucket[v] = d
        # nama alternatif: "Shopee Official Store DEMO" sering ditulis "Shopee Official"
        alias = d.get("aliases") or []
        for a in alias:
            v = norm(a)
            if v and v not in by_name:
                by_name[v] = d
    docs.sort(key=lambda x: (x.get("account_name") or ""))
    return {"by_id": by_id, "by_name": by_name, "by_code": by_code,
            "by_user": by_user, "docs": docs}


async def resolve_account(
    db,
    *,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    account_code: Optional[str] = None,
    username: Optional[str] = None,
    platform: Optional[str] = None,
    index: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[dict], str]:
    """Satu jalan masuk untuk "akun mana yang dimaksud".

    Mengembalikan ``(doc | None, alasan)``. `alasan` dipakai apa adanya sebagai
    pesan di layar/laporan impor — pesan yang tidak bisa ditindaklanjuti sama
    buruknya dengan tidak ada pesan.
    """
    idx = index or await account_index(db)

    if account_id:
        d = idx["by_id"].get(account_id)
        if d:
            return d, "cocok lewat account_id"
        return None, f"account_id '{account_id}' tidak ada di master akun"

    for value, bucket, label in (
        (account_code, idx["by_code"], "kode akun"),
        (account_name, idx["by_name"], "nama akun"),
        (username, idx["by_user"], "username akun"),
    ):
        if not value:
            continue
        d = bucket.get(norm(value))
        if d:
            if platform and norm(d.get("platform")) != norm(platform) and platform != "":
                return d, (f"cocok lewat {label} '{value}', tapi platform di master "
                           f"'{d.get('platform')}' beda dari file '{platform}'")
            return d, f"cocok lewat {label} '{value}'"

    # kecocokan sebagian: nama file impor sering membawa embel-embel
    if account_name:
        n = norm(account_name)
        if len(n) >= 5:
            hits = [d for k, d in idx["by_name"].items() if n in k or k in n]
            uniq = {d.get("id"): d for d in hits}
            if len(uniq) == 1:
                d = next(iter(uniq.values()))
                return d, (f"cocok SEBAGIAN dari nama '{account_name}' → "
                           f"'{d.get('account_name')}' (periksa sekali)")
            if len(uniq) > 1:
                names = ", ".join(sorted(x.get("account_name", "?") for x in uniq.values()))
                return None, (f"nama '{account_name}' cocok ke LEBIH DARI SATU akun "
                              f"({names}) — pilih akunnya secara eksplisit")

    given = account_id or account_code or account_name or username or "(kosong)"
    return None, f"akun '{given}' tidak dikenali; buat dulu di Kelola Akun"


async def require_account(db, account_id: Optional[str]) -> dict:
    """Akun WAJIB. Menolak keras, bukan menyimpan baris yatim diam-diam."""
    if not account_id:
        raise HTTPException(400, "account_id wajib: pilih toko/akun dulu")
    doc = await db[ACCOUNTS].find_one({"id": account_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, f"Akun '{account_id}' tidak ditemukan di master akun")
    return doc


def stamp_account(doc: dict, account: dict) -> dict:
    """Tulis lingkup akun ke dokumen. `account_name`/`platform` SELALU turunan.

    Denormalisasi nama tetap berguna (tabel tidak perlu join), tapi karena nilainya
    diambil dari master — bukan dari yang diketik pengguna — tidak akan lahir dua
    ejaan untuk satu toko.
    """
    doc["account_id"] = account.get("id")
    doc["account_name"] = account.get("account_name") or account.get("name") or ""
    if account.get("platform"):
        doc["platform"] = account.get("platform")
    if account.get("account_code"):
        doc["account_code"] = account.get("account_code")
    return doc


def scope_query(account_id: Optional[str], field: str = "account_id") -> dict:
    return {field: account_id} if account_id else {}


# ── kreator & host: harus SUDAH di-assign ke toko itu ────────────────────────
async def assert_creator_assigned(db, creator_id: str, account_id: str) -> dict:
    creator = await db[CREATORS].find_one({"id": creator_id}, {"_id": 0})
    if not creator:
        raise HTTPException(404, f"Kreator '{creator_id}' tidak ditemukan")
    assigned = creator.get("assigned_account_ids") or []
    if account_id and account_id not in assigned:
        raise HTTPException(
            400,
            f"Kreator '{creator.get('name')}' belum di-assign ke akun ini. "
            f"Assign dulu di KOL & Kreator, supaya biaya/komisinya tidak "
            f"terbebankan ke toko yang tidak memakainya.",
        )
    return creator


async def assert_host_assigned(db, host_id: str, account_id: str) -> dict:
    host = await db[HOSTS].find_one({"id": host_id}, {"_id": 0})
    if not host:
        raise HTTPException(404, f"Host live '{host_id}' tidak ditemukan")
    assigned = host.get("assigned_account_ids") or []
    if account_id and account_id not in assigned:
        raise HTTPException(
            400,
            f"Host '{host.get('name')}' belum di-assign ke akun ini. "
            f"Assign dulu di Live Selling → Host, supaya jam kerja & gajinya "
            f"tidak dibebankan ke toko yang tidak memakainya.",
        )
    return host


# ── data demo: TIDAK BOLEH melahirkan baris tanpa toko ──────────────────────
# Semua seed demo marketing WAJIB lewat sini. Sebelum ini tiap seed menulis
# daftar toko sendiri sebagai TEKS (`account_name`) tanpa `account_id`, sehingga
# data demo yang dilihat staf pertama kali justru MENGAJARKAN bentuk yang salah:
# 60 order, 25 iklan, 18 sesi live, 35 sample, 30 konten, 10 diskon, 8 peluncuran
# semuanya tak berlingkup toko. Layar yang difilter per toko lalu tampak "kosong"
# dan aplikasinya yang disalahkan.
_DEMO_ACCOUNTS = (
    {"account_code": "DA-SHOPEE", "account_name": "DA Official Shopee",
     "platform": "shopee", "username": "da_official", "group": "official_store"},
    {"account_code": "DL-TIKTOK", "account_name": "Daluna TikTok Shop",
     "platform": "tiktok", "username": "daluna.official", "group": "official_store"},
    {"account_code": "DA-TOKPED", "account_name": "DA Tokopedia",
     "platform": "tokopedia", "username": "dewiaditya", "group": "official_store"},
)


async def ensure_demo_accounts(db) -> List[dict]:
    """Pastikan master akun tidak kosong, lalu kembalikan akun aktif yang SAH.

    Dipakai oleh seluruh seed demo marketing. Kembaliannya selalu dokumen master
    yang benar-benar ada, jadi seed tidak pernah bisa menulis `account_id: None`.
    """
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz

    docs = await db[ACCOUNTS].find({}, {"_id": 0}).to_list(500)
    if not docs:
        now = _dt.now(_tz.utc)
        fresh = []
        for a in _DEMO_ACCOUNTS:
            fresh.append({
                "id": str(_uuid.uuid4()),
                **a,
                "status": "active",
                "credentials": {"has_api_integration": False},
                "import_config": {"saved_templates": []},
                "assigned_staff": [],
                "health_score": 0,
                "created_at": now,
                "updated_at": now,
                "created_by": "seed",
            })
        await db[ACCOUNTS].insert_many(fresh)
        logger.info("[marketing-scope] master akun kosong → %d akun demo dibuat",
                    len(fresh))
        docs = [{k: v for k, v in d.items() if k != "_id"} for d in fresh]

    active = [d for d in docs if d.get("status") != "inactive" and d.get("id")]
    return active or [d for d in docs if d.get("id")]


async def seed_account_pool(db) -> List[dict]:
    """Alias yang lebih jelas maksudnya untuk dipakai di fungsi `seed_*_if_empty`."""
    return await ensure_demo_accounts(db)


async def account_options(db, *, active_only: bool = True) -> List[dict]:
    """Daftar akun untuk pemilih di layar — satu sumber, bukan disalin per modul."""
    q = {"status": {"$ne": "inactive"}} if active_only else {}
    docs = await db[ACCOUNTS].find(q, {"_id": 0, "id": 1, "account_name": 1,
                                       "account_code": 1, "platform": 1,
                                       "username": 1, "status": 1}).to_list(500)
    docs.sort(key=lambda d: (d.get("platform") or "", d.get("account_name") or ""))
    return docs


async def creator_options(db, account_id: Optional[str] = None) -> List[dict]:
    q = {"assigned_account_ids": account_id} if account_id else {}
    docs = await db[CREATORS].find(q, {"_id": 0, "id": 1, "name": 1,
                                       "creator_code": 1, "platforms": 1,
                                       "status": 1,
                                       "assigned_account_ids": 1}).to_list(500)
    docs.sort(key=lambda d: d.get("name") or "")
    return docs


async def host_options(db, account_id: Optional[str] = None) -> List[dict]:
    q = {"assigned_account_ids": account_id} if account_id else {}
    docs = await db[HOSTS].find(q, {"_id": 0, "id": 1, "name": 1, "email": 1,
                                    "employment_type": 1, "status": 1,
                                    "assigned_account_ids": 1}).to_list(500)
    docs.sort(key=lambda d: d.get("name") or "")
    return docs


# ══════════════════════════════════════════════════════════════════════════════
# F6 — VISIBILITAS PER PEMAKAI (bukan hanya lingkup data)
# ══════════════════════════════════════════════════════════════════════════════
# KENAPA BAGIAN INI ADA
# ---------------------
# Sampai F5, seluruh berkas ini menjaga **lingkup DATA** (setiap dokumen wajib
# punya `account_id` yang sah). Yang BELUM dijaga: **siapa boleh melihat toko yang
# mana**. Akibatnya nyata: staf yang hanya memegang 1 toko melihat angka 9 toko —
# termasuk omzet, biaya, dan target toko rekan kerjanya — dan setiap layar per toko
# menampilkan daftar toko yang bukan tanggung jawabnya. Tidak ada satu pun galat
# yang muncul, jadi kesalahan ini tidak pernah "terasa".
#
# Aturan (matriks F6.3):
#   * `owner/admin/superadmin/spv_marketing/manager_marketing/accounting/
#      content_creator/marketing_kol`  ⇒ SEMUA toko (None = tanpa filter)
#   * `staff_marketing/pic_toko/host_live/cs_staff`               ⇒ hanya toko yang
#      DI-ASSIGN (`pic_id == user.id` ATAU `user.id ∈ assigned_staff`)
#   * peran lain                                                  ⇒ tidak ada toko
# Hasil KOSONG bukan berarti "belum ada data" — pesannya harus menyebut jalan
# keluarnya (minta SPV meng-assign di Manajemen Akun).
ALL_ACCOUNTS_ROLES = ("owner", "admin", "superadmin", "spv_marketing",
                      "manager_marketing", "accounting", "content_creator",
                      "marketing_kol")
SCOPED_ROLES = ("staff_marketing", "pic_toko", "host_live", "cs_staff")
# Peran yang boleh MENETAPKAN target/anggaran & menutup periode (F6.3).
TARGET_WRITER_ROLES = ("owner", "admin", "superadmin", "spv_marketing",
                       "manager_marketing")

NO_ACCOUNT_HINT = ("Belum ada toko yang di-assign ke Anda. Minta SPV Marketing "
                   "meng-assign toko Anda di layar Manajemen Akun.")


def _role(user: Optional[dict]) -> str:
    return str((user or {}).get("role") or "").lower()


def sees_all_accounts(user: Optional[dict]) -> bool:
    if _role(user) in ALL_ACCOUNTS_ROLES:
        return True
    perms = (user or {}).get("_permissions") or []
    return "*" in perms or "marketing.report.view_all" in perms


def can_write_target(user: Optional[dict]) -> bool:
    """Boleh set target/anggaran? (staf toko TIDAK — itu keputusan SPV)."""
    if _role(user) in TARGET_WRITER_ROLES:
        return True
    perms = (user or {}).get("_permissions") or []
    return "*" in perms or "marketing.target.set" in perms


async def visible_account_ids(db, user: Optional[dict]) -> Optional[List[str]]:
    """Daftar id toko yang boleh dilihat pemakai ini. ``None`` = semua toko."""
    if sees_all_accounts(user):
        return None
    uid = (user or {}).get("id")
    if not uid or _role(user) not in SCOPED_ROLES:
        return []
    rows = await db[ACCOUNTS].find(
        {"$or": [{"pic_id": uid}, {"assigned_staff": uid}]}, {"_id": 0, "id": 1}
    ).to_list(300)
    return [r["id"] for r in rows]


async def scope_filter(db, user: Optional[dict], base: Optional[dict] = None,
                       field: str = "account_id") -> dict:
    """Tambahkan penyaring visibilitas ke sebuah kueri Mongo."""
    q = dict(base or {})
    ids = await visible_account_ids(db, user)
    if ids is None:
        return q
    existing = q.get(field)
    if isinstance(existing, str):
        # permintaan menyebut satu toko: pertahankan hanya bila boleh dilihat
        q[field] = existing if existing in ids else "__tidak_boleh_dilihat__"
        return q
    q[field] = {"$in": ids}
    return q


async def visible_accounts(db, user: Optional[dict], *,
                           base: Optional[dict] = None,
                           projection: Optional[dict] = None,
                           sort: Optional[list] = None,
                           limit: int = 300) -> List[dict]:
    """Dokumen toko yang boleh dilihat pemakai ini — **satu pintu** untuk semua
    layar DAFTAR/RINGKAS.

    KENAPA HELPER INI ADA (sesi #9). Setiap layar daftar sebelumnya menulis
    sendiri ``db.marketing_platform_accounts.find({"status": "active"})`` — 14
    endpoint terbukti mengirim angka SEMBILAN toko kepada staf yang hanya
    memegang satu (omzet, biaya iklan, komplain, sesi live, riwayat impor).
    Menyalin filter lingkup ke 14 tempat berarti tempat ke-15 akan lupa; memakai
    helper ini berarti aturannya hanya ada di SATU berkas.

    ``base`` = filter tambahan (mis. ``{"status": "active"}``). Untuk pemakai yang
    melihat semua toko, hasilnya persis sama dengan kueri lama.
    """
    q = dict(base or {})
    ids = await visible_account_ids(db, user)
    if ids is not None:
        q["id"] = {"$in": ids}
    cur = db[ACCOUNTS].find(q, projection if projection is not None else {"_id": 0})
    if sort:
        cur = cur.sort(sort)
    return await cur.to_list(limit)


async def assert_account_visible(db, user: Optional[dict], account_id: Optional[str]) -> None:
    """403 bila toko itu bukan tanggung jawab pemakai ini."""
    from fastapi import HTTPException
    if not account_id:
        return
    ids = await visible_account_ids(db, user)
    if ids is None or account_id in ids:
        return
    raise HTTPException(
        403, "Toko ini tidak di-assign ke Anda, jadi angkanya tidak bisa dibuka. "
             + NO_ACCOUNT_HINT)


async def assert_can_write_target(user: Optional[dict], what: str = "target") -> None:
    from fastapi import HTTPException
    if can_write_target(user):
        return
    raise HTTPException(
        403, f"Hanya SPV/Manager Marketing (atau owner) yang boleh menetapkan {what}. "
             "Staf toko mengisi data harian; angka {what} adalah keputusan SPV.".replace(
                 "{what}", what))
