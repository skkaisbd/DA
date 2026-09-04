"""Penomoran Dokumen & SKU — konfigurasi format nomor oleh owner.

Layar: Portal Administrasi Sistem → Penomoran Dokumen.

Catatan arsitektur: modul ini TIDAK menghasilkan nomor sendiri. Ia hanya
menyimpan format; satu-satunya generator tetap
`utils.counters.gen_prefixed_number` yang membaca format ini.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import require_auth
from core import doc_number_policy as _policy
from core.doc_number_policy import MODES, pattern_for
from database import get_db
from data.doc_number_registry import (DOC_NUMBER_REGISTRY, REGISTRY_BY_KEY, GROUPS,
                                      target_of)
from utils.counters import (CONFIG_COLL, invalidate_format_cache, peek_counter,
                            render_format, validate_format)

router = APIRouter(prefix="/api/admin/doc-numbering", tags=["doc-numbering"])
# Kebijakan nomor dibaca juga oleh FORM dokumen (staf biasa) — karena itu router
# terpisah tanpa gerbang izin admin. Lihat `get_number_policy`.
policy_router = APIRouter(prefix="/api/doc-number-policy", tags=["doc-numbering"])

ALLOWED_ROLES = {"superadmin", "owner", "admin"}


async def _require_admin(request: Request) -> dict:
    """2026-08-06 — gerbang izin terpusat (fallback aman): izin `docnum.manage`
    bisa diberikan ke role non-admin lewat layar "Peran & Hak Akses"."""
    from routes.shared import require_perm
    return await require_perm(
        request, "docnum.manage", "settings.manage",
        legacy_roles=tuple(ALLOWED_ROLES),
        message="Akses ditolak: butuh izin kelola penomoran dokumen (docnum.manage).",
    )


class FormatIn(BaseModel):
    key: str
    # FASE G (2026-08-16): boleh menyimpan HANYA mode (format dibiarkan apa adanya),
    # supaya owner bisa memindah Otomatis↔Manual tanpa mengetik ulang formatnya.
    format: Optional[str] = Field(None, min_length=1, max_length=120)
    mode: Optional[str] = None
    active: bool = True


@router.get("")
async def list_formats(request: Request):
    """Katalog jenis dokumen + format aktif + nomor terakhir yang terpakai."""
    await _require_admin(request)
    db = get_db()
    saved = {c["key"]: c for c in await db[CONFIG_COLL].find({}, {"_id": 0}).to_list(500)}

    items = []
    for entry in DOC_NUMBER_REGISTRY:
        cfg = saved.get(entry["key"]) or {}
        fmt = cfg.get("format") or entry["default_format"]
        seqd = entry.get("sequenced", True)
        try:
            contoh = validate_format(fmt, entry.get("tokens"), require_seq=seqd)
            error = None
        except ValueError as e:
            contoh, error = None, str(e)
        collection, field = target_of(entry)
        terakhir = None
        if seqd and not error:
            prefix, _ = render_format(fmt, ctx={t: t[:3].upper() for t in entry.get("tokens", [])})
            terakhir = await peek_counter(db, f"autonum:{collection}:{field}:{prefix}")
        items.append({
            **entry,
            "collection": collection,
            "field": field,
            "format": fmt,
            "is_custom": bool(cfg.get("format")),
            # FASE G — mode penomoran: 'auto' (dibuat sistem) atau 'manual' (diketik,
            # tetapi wajib mengikuti pola). Bawaannya per jenis dokumen supaya
            # menyalakan fitur ini tidak mengubah perilaku yang sudah jalan.
            "mode": cfg.get("mode") or entry.get("default_mode") or "auto",
            "mode_default": entry.get("default_mode") or "auto",
            "mode_is_custom": bool(cfg.get("mode")),
            "pola": None if error else pattern_for(fmt),
            "active": cfg.get("active", True),
            "contoh": contoh,
            "error": error,
            "nomor_terakhir": terakhir,
            "updated_at": cfg.get("updated_at"),
            "updated_by": cfg.get("updated_by"),
        })
    return {"groups": GROUPS, "items": items,
            "tokens_umum": ["YYYY", "YY", "MM", "DD", "SEQ:n"]}


@router.post("/preview")
async def preview(request: Request):
    """Validasi format & tampilkan contoh nomor — tanpa menyimpan apa pun."""
    await _require_admin(request)
    body = await request.json()
    entry = REGISTRY_BY_KEY.get(body.get("key") or "")
    try:
        return {"ok": True, "contoh": validate_format(
            body.get("format") or "", (entry or {}).get("tokens"),
            require_seq=(entry or {}).get("sequenced", True))}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.put("")
async def save_format(request: Request, data: FormatIn):
    user = await _require_admin(request)
    entry = REGISTRY_BY_KEY.get(data.key)
    if not entry:
        raise HTTPException(404, f"Jenis dokumen '{data.key}' tidak dikenal.")
    if data.mode is not None and data.mode not in MODES:
        raise HTTPException(400, f"mode harus salah satu dari {MODES}.")
    # ── SESI #18 — SETELAN TIDAK BOLEH BERBOHONG ─────────────────────────────
    # Mode OTOMATIS/MANUAL hanya berarti untuk jenis dokumen yang JALUR TULISNYA
    # memanggil `core.doc_number_policy.issue_number` (ditandai `policy_enforced`).
    # Untuk jenis lain, menyimpan mode="manual" akan tersimpan RAPI di basis data
    # dan tampil di layar, tetapi dokumennya tetap bernomor otomatis — owner
    # mengira sudah mengubah sesuatu padahal tidak. Ditolak dengan menyebut
    # jalan keluarnya, bukan diterima diam-diam.
    if (data.mode is not None and data.mode != (entry.get("default_mode") or "auto")
            and not entry.get("policy_enforced")):
        # SESI #19 — pesan dibedakan supaya JUJUR, bukan seragam "belum bisa diubah":
        #  · auto_only        → dokumennya LAHIR TANPA MANUSIA, jadi mode manual tidak
        #                       akan pernah berarti (alasannya disebutkan apa adanya)
        #  · pending_enforce  → ada formnya, jalur tulisnya memang belum disambungkan
        if entry.get("auto_only"):
            raise HTTPException(400, (
                f"'{entry['label']}' SELALU bernomor otomatis. "
                f"{entry.get('alasan_otomatis', '')} "
                "FORMAT nomornya tetap bisa diubah di sini."))
        sudah = ", ".join(e["label"] for e in DOC_NUMBER_REGISTRY if e.get("policy_enforced"))
        raise HTTPException(400, (
            f"Mode penomoran untuk '{entry['label']}' belum bisa diubah: jalur dokumennya "
            "masih membuat nomor otomatis, jadi setelan manual tidak akan berlaku. "
            f"Yang SUDAH bisa diatur: {sudah}. FORMAT dokumen ini tetap bisa diubah."))

    db = get_db()
    cur = await db[CONFIG_COLL].find_one({"key": data.key}, {"_id": 0}) or {}
    fmt = (data.format or cur.get("format") or entry["default_format"]).strip()
    try:
        contoh = validate_format(fmt, entry.get("tokens"),
                                 require_seq=entry.get("sequenced", True))
    except ValueError as e:
        raise HTTPException(400, str(e))

    now = datetime.now(timezone.utc).isoformat()
    changes = {"format": fmt, "active": data.active,
               "label": entry["label"], "group": entry["group"],
               "updated_at": now, "updated_by": user.get("email", user.get("id"))}
    if data.mode is not None:
        changes["mode"] = data.mode
    await db[CONFIG_COLL].update_one(
        {"key": data.key},
        {"$set": changes,
         "$setOnInsert": {"id": str(uuid.uuid4()), "key": data.key}},
        upsert=True,
    )
    invalidate_format_cache(data.key)
    mode = changes.get("mode") or cur.get("mode") or entry.get("default_mode") or "auto"
    return {"ok": True, "key": data.key, "format": fmt, "contoh": contoh,
            "mode": mode, "pola": pattern_for(fmt)}


@policy_router.get("")
async def get_number_policy(request: Request, key: str = Query(..., min_length=3)):
    """Kebijakan nomor satu jenis dokumen — dibaca oleh FORM dokumen, bukan admin.

    FASE G: form pembuat dokumen harus tahu apakah kolom nomor boleh diketik.
    Tanpa ini, layar tetap menyuruh mengetik nomor lalu backend menolaknya —
    pemakai menanggung kebingungan atas setelan yang tidak pernah ia lihat.
    Sengaja `require_auth` (bukan izin admin): yang membutuhkannya adalah staf
    pembuat PO/dokumen, bukan pengelola sistem.

    SESI #19 — token konteks boleh dikirim sebagai `ctx_<TOKEN>` (mis.
    `?key=wh_delivery_notes.sj_number&ctx_TIPE=SJ-INTERNAL`). Tanpa itu, pratinjau
    Surat Jalan berbunyi "TIP/2026/08/0001" — nomor yang tidak akan pernah lahir.
    """
    await require_auth(request)
    db = get_db()
    ctx = {k[4:].upper(): v for k, v in request.query_params.items()
           if k.lower().startswith("ctx_") and v}
    # Iter 106 — token {PREFIX} invoice maklon mengikuti Pengaturan Sistem; tanpa ini
    # pratinjau layar Invoice berbunyi "PRE-2026-0001" (fallback 3 huruf token).
    if key == 'dewi_maklon_invoices.invoice_number' and 'PREFIX' not in ctx:
        from routes.dewi_system_config import get_config_value
        ctx['PREFIX'] = await get_config_value(db, 'maklon_invoice_prefix', 'INV-MKL') or 'INV-MKL'
    pol = await _policy.policy(db, key, ctx or None)
    pol["nomor_berikutnya"] = await _policy.next_preview(db, key, ctx or None)
    return pol


@router.delete("/{key}")
async def reset_format(request: Request, key: str):
    """Kembalikan ke format bawaan kode."""
    await _require_admin(request)
    if key not in REGISTRY_BY_KEY:
        raise HTTPException(404, f"Jenis dokumen '{key}' tidak dikenal.")
    db = get_db()
    await db[CONFIG_COLL].delete_one({"key": key})
    invalidate_format_cache(key)
    return {"ok": True, "key": key, "format": REGISTRY_BY_KEY[key]["default_format"]}


class CounterIn(BaseModel):
    key: str
    start_from: int = Field(..., ge=0)
    prefix: Optional[str] = None


@router.post("/counter")
async def set_counter(request: Request, data: CounterIn):
    """Setel ulang titik awal nomor urut (mis. mulai dari 100 untuk tahun baru).

    Menurunkan angka bisa menimbulkan nomor ganda pada dokumen yang sudah ada —
    karena itu penurunan hanya diizinkan bila belum ada dokumen memakai prefix ini.
    """
    user = await _require_admin(request)
    entry = REGISTRY_BY_KEY.get(data.key)
    if not entry:
        raise HTTPException(404, f"Jenis dokumen '{data.key}' tidak dikenal.")
    if not entry.get("sequenced", True):
        raise HTTPException(400, f"'{entry['label']}' tidak memakai nomor urut.")
    db = get_db()
    collection, field = target_of(entry)
    cfg = await db[CONFIG_COLL].find_one({"key": data.key}, {"_id": 0, "format": 1})
    fmt = (cfg or {}).get("format") or entry["default_format"]
    try:
        prefix, _ = render_format(fmt, ctx={t: t[:3].upper() for t in entry.get("tokens", [])})
    except ValueError as e:
        raise HTTPException(400, str(e))
    prefix = data.prefix or prefix

    counter_key = f"autonum:{collection}:{field}:{prefix}"
    current = await peek_counter(db, counter_key) or 0
    if data.start_from < current:
        used = await db[collection].count_documents({field: {"$regex": f"^{prefix}"}})
        if used:
            raise HTTPException(400, f"Tidak bisa mundur: sudah ada {used} dokumen memakai awalan '{prefix}'.")
    await db.counters.update_one(
        {"_id": counter_key},
        {"$set": {"seq": data.start_from, "namespace": "autonum",
                  "updated_by": user.get("email"), "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True, "key": data.key, "prefix": prefix,
            "nomor_berikutnya": f"{prefix}{data.start_from + 1:0{4}d}"}
