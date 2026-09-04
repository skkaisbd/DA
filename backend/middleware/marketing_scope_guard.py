"""middleware.marketing_scope_guard — JARING PENGAMAN LINGKUP TOKO (F6.6).

MASALAH YANG DITUTUP (diukur, bukan dugaan)
-------------------------------------------
`core/marketing_account_scope.py` sudah menyediakan aturan "siapa boleh melihat
toko yang mana" sejak F6, tetapi pada awal sesi #9 hanya **7 dari 54** berkas
`routes/marketing_*.py` yang benar-benar memanggilnya. Artinya staf yang hanya
memegang satu toko masih bisa membuka angka toko rekan kerjanya hanya dengan
menukar `account_id` di URL — omzet, biaya iklan, komplain, sesi live, bahkan
menulis rekap harian toko orang lain. Tidak ada satu pun galat yang muncul.

Menambal 54 berkas satu per satu bisa (dan tetap dikerjakan untuk endpoint
DAFTAR yang tidak menyebut toko), tetapi tambalan per berkas punya kelemahan
mendasar: **berkas ke-55 tidak akan tahu aturan ini**. Middleware ini menutup
kelas masalahnya di satu tempat:

    Tidak ada endpoint `/api/marketing/*` yang boleh melayani permintaan yang
    MENYEBUT toko di luar lingkup pemakai — dari path, query, atau body.

BATAS YANG JUJUR (jangan salah paham)
-------------------------------------
* Ini **jaring pengaman**, bukan pengganti `scope_filter`. Endpoint yang TIDAK
  menyebut toko (mis. daftar "semua toko") tetap harus menyaring sendiri di
  route-nya — middleware tidak tahu apa isi jawabannya.
* Hanya dijalankan untuk pemakai berperan **berlingkup toko**
  (`SCOPED_ROLES`); admin/SPV/manager (dan token tak sah, yang akan ditolak
  route-nya sendiri dengan 401) dilewati tanpa biaya query.
* `account_id` yang tidak dikenal DB (mis. teks ngawur) tidak dijadikan 403 di
  sini — biarkan route-nya membalas 404 dengan pesannya sendiri. Yang ditolak
  hanyalah toko yang ADA tetapi bukan tanggung jawab pemakai (itu IDOR).
* Body JSON dibaca lalu **ditanam ulang** (`request._body`) supaya route tetap
  bisa membacanya. Body non-JSON (unggahan berkas/multipart) DILEWATI: ukurannya
  bisa besar dan `account_id`-nya sudah dijaga route impor.
"""
from __future__ import annotations

import json
import logging
from typing import List, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

PREFIX = "/api/marketing/"
# Path yang TIDAK boleh dijaga di sini karena memang bertugas mengubah kewenangan
# atau membaca daftar toko untuk pemilihan; route-nya punya penjaga peran sendiri.
SKIP_SUFFIXES = ("/account-assign/candidates", "/account-assign/overview")
MAX_BODY_BYTES = 512_000       # body lebih besar dari ini dilewati (bukan JSON kecil)


def _ids_from_path(path: str) -> Set[str]:
    """Ambil id sesudah segmen `/accounts/` (pola `/accounts/{id}/...`)."""
    out: Set[str] = set()
    parts = [p for p in path.split("/") if p]
    for i, p in enumerate(parts):
        if p == "accounts" and i + 1 < len(parts):
            cand = parts[i + 1]
            # hanya bentuk yang MUNGKIN id (uuid/kode), bukan sub-path kata biasa
            if len(cand) >= 8 and cand not in ("health", "options", "review", "bulk"):
                out.add(cand)
    return out


class MarketingScopeGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if not path.startswith(PREFIX) or any(path.endswith(s) for s in SKIP_SUFFIXES):
            return await call_next(request)

        # ── 1. hanya pemakai berlingkup toko yang perlu dijaga ────────────────
        try:
            from auth import verify_token
            from core import marketing_account_scope as scope
            user = verify_token(request)
            if not user:
                return await call_next(request)          # 401 urusan route
            role = str(user.get("role") or "").lower()
            if role not in scope.SCOPED_ROLES:
                return await call_next(request)          # lihat semua toko / bukan marketing
        except Exception as exc:                          # noqa: BLE001
            logger.warning("[scope-guard] gagal menilai pemakai: %s", exc)
            return await call_next(request)

        # ── 2. kumpulkan toko yang DISEBUT permintaan ────────────────────────
        named: Set[str] = set(_ids_from_path(path))
        qp = request.query_params
        for key in ("account_id", "account", "toko_id"):
            v = qp.get(key)
            if v:
                named.add(v)
        multi = qp.get("accounts") or qp.get("account_ids")
        if multi:
            named.update(x.strip() for x in multi.split(",") if x.strip())

        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            ctype = (request.headers.get("content-type") or "").lower()
            clen = int(request.headers.get("content-length") or 0)
            if "application/json" in ctype and 0 < clen <= MAX_BODY_BYTES:
                try:
                    raw = await request.body()
                    request._body = raw                   # tanam ulang untuk route
                    data = json.loads(raw or b"{}")
                    if isinstance(data, dict):
                        for key in ("account_id", "toko_id"):
                            if data.get(key):
                                named.add(str(data[key]))
                        for key in ("account_ids", "accounts"):
                            v = data.get(key)
                            if isinstance(v, list):
                                named.update(str(x) for x in v if x)
                except Exception:                         # noqa: BLE001
                    pass                                  # body aneh = urusan route

        if not named:
            return await call_next(request)

        # ── 3. tolak hanya toko yang ADA tetapi bukan lingkup pemakai ────────
        try:
            from core import marketing_account_scope as scope
            from database import get_db
            db = get_db()
            visible: List[str] | None = await scope.visible_account_ids(db, user)
            if visible is None:
                return await call_next(request)
            unknown = [a for a in named if a not in visible]
            if unknown:
                exists = await db[scope.ACCOUNTS].find(
                    {"id": {"$in": unknown}}, {"_id": 0, "id": 1, "account_name": 1}
                ).to_list(20)
                if exists:
                    names = ", ".join(e.get("account_name") or e["id"] for e in exists)
                    logger.info("[scope-guard] TOLAK %s %s untuk %s (toko: %s)",
                                request.method, path, user.get("email"), names)
                    return JSONResponse(
                        {"detail": f"Toko berikut tidak di-assign ke Anda, jadi datanya "
                                   f"tidak bisa dibuka atau diubah: {names}. "
                                   + scope.NO_ACCOUNT_HINT,
                         "status": 403, "scope_guard": True},
                        status_code=403)
        except Exception as exc:                          # noqa: BLE001
            # GAGAL-TERBUKA disengaja: jaring pengaman tidak boleh mematikan
            # aplikasi kalau DB sedang bermasalah — tetapi kegagalannya DICATAT,
            # tidak senyap (route tetap punya penjaganya sendiri).
            logger.warning("[scope-guard] gagal memeriksa lingkup (fail-open): %s", exc)
        return await call_next(request)
