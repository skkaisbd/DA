"""core/doc_number_policy.py — kebijakan nomor dokumen: OTOMATIS atau MANUAL.

FASE G (2026-08-16, keputusan owner). Sebelum berkas ini, "mode" penomoran hanya
**implisit**: kolom nomor kosong → dibuatkan otomatis; kolom nomor diisi → dipakai
**apa adanya tanpa satu pun pemeriksaan**.

Akibat yang bisa dibuktikan di basis data ini: `production_pos` — sumber nomor SPP —
memang MEWAJIBKAN nomor diketik tangan (`routes/production_pos.py`: "Nomor PO wajib
diisi"), dan isinya hari ini bercampur: `PO-INT-DEMO-1`, `PO-MK-DEMO-1`,
`PO-MKL-GAB-A`. Nomor yang polanya bebas tidak bisa diurutkan, tidak bisa dicari,
dan tidak bisa dibuktikan sebagai dokumen ke-berapa — padahal itulah satu-satunya
gunanya sebuah nomor dokumen.

Keputusan owner: nomor MANUAL tetap **wajib mengikuti pola formatnya**; yang tidak
cocok DITOLAK beserta contoh yang benar. Mode OTOMATIS menolak nomor ketikan
(bukan mengabaikannya diam-diam — pemakai yang mengetik nomor lalu melihat nomor
lain muncul akan menyimpulkan sistemnya rusak).

Kebijakan disimpan di koleksi yang SAMA dengan format (`doc_number_configs`,
field `mode`), jadi tidak ada tempat kedua yang bisa berbeda pendapat.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import HTTPException

from data.doc_number_registry import REGISTRY_BY_KEY, target_of
from utils.counters import (CONFIG_COLL, gen_prefixed_number, peek_counter,
                            render_format, validate_format)

log = logging.getLogger(__name__)

MODES = ("auto", "manual")

# Token → apa yang boleh muncul di posisi itu pada nomor MANUAL.
_TOKEN_PATTERNS = {
    "YYYY": r"\d{4}", "YY": r"\d{2}", "MM": r"\d{2}", "DD": r"\d{2}",
}
_TOKEN_RE = re.compile(r"\{([A-Z_]+)(?::(\d+))?\}")


def _entry(key: str) -> dict:
    entry = REGISTRY_BY_KEY.get(key)
    if not entry:
        raise HTTPException(404, f"Jenis dokumen '{key}' tidak dikenal.")
    return entry


def pattern_for(fmt: str) -> str:
    """Regex yang harus dipenuhi nomor MANUAL untuk format ini.

    Token tanggal dipetakan ke digit; {SEQ:n} ke minimal n digit; token konteks
    (mis. {KLIEN}, {TIPE}) ke satu potongan kode tanpa spasi. Sisanya literal —
    supaya pemisah `/` atau `-` yang dipilih owner benar-benar ditegakkan.
    """
    out, pos = ["^"], 0
    for m in _TOKEN_RE.finditer(fmt or ""):
        out.append(re.escape(fmt[pos:m.start()]))
        token, width = m.group(1), m.group(2)
        if token == "SEQ":
            out.append(r"\d{%d,}" % int(width or 4))
        elif token in _TOKEN_PATTERNS:
            out.append(_TOKEN_PATTERNS[token])
        else:
            # SESI #19 — tanda hubung DIIZINKAN di token konteks. Terukur: format
            # Surat Jalan Gudang adalah `{TIPE}/{YYYY}/{MM}/{SEQ:4}` dan setiap
            # TIPE-nya memuat tanda hubung (SJ-CMT, SJ-MAKLON, SJ-INTERNAL, …).
            # Dengan kelas karakter lama ([A-Za-z0-9._]+), nomor manual yang BENAR
            # ("SJ-INTERNAL/2026/08/0007") selalu ditolak "tidak mengikuti pola" —
            # mode MANUAL akan mustahil dipakai untuk surat jalan.
            out.append(r"[A-Za-z0-9._-]+")
        pos = m.end()
    out.append(re.escape(fmt[pos:]))
    out.append("$")
    return "".join(out)


async def policy(db, key: str, ctx: Optional[dict] = None) -> dict:
    """Kebijakan nomor untuk satu jenis dokumen (mode + format + contoh + pola).

    `ctx` (SESI #19) mengisi token konteks (mis. {TIPE} pada Surat Jalan) supaya
    CONTOH yang ditampilkan layar memakai nilai yang benar-benar dipilih pemakai.
    Tanpa ini contohnya berbunyi "TIP/2026/08/0001" — nomor yang tidak akan pernah
    lahir, dan layar yang menyebut nomor palsu sama saja berbohong.
    """
    entry = _entry(key)
    cfg = await db[CONFIG_COLL].find_one({"key": key}, {"_id": 0}) or {}
    fmt = cfg.get("format") or entry["default_format"]
    mode = cfg.get("mode") or entry.get("default_mode") or "auto"
    if mode not in MODES:
        mode = "auto"
    seqd = entry.get("sequenced", True)
    try:
        contoh = validate_format(fmt, entry.get("tokens"), require_seq=seqd)
        if ctx:
            prefix, width = render_format(fmt, ctx=ctx, require_seq=seqd)
            contoh = f"{prefix}{1:0{width}d}" if width else prefix
        error = None
    except ValueError as e:
        contoh, error = None, str(e)
    return {
        "key": key, "label": entry["label"], "group": entry["group"],
        "format": fmt, "mode": mode, "mode_default": entry.get("default_mode") or "auto",
        "mode_is_custom": bool(cfg.get("mode")),
        "tokens": entry.get("tokens") or [], "sequenced": seqd,
        "contoh": contoh, "error": error, "pola": pattern_for(fmt) if not error else None,
        "catatan": entry.get("catatan", ""),
    }


async def next_preview(db, key: str, ctx: Optional[dict] = None) -> Optional[str]:
    """Nomor yang AKAN dipakai bila dibuat sekarang (tanpa menghabiskannya)."""
    entry = _entry(key)
    pol = await policy(db, key, ctx)
    if pol["error"] or not pol["sequenced"]:
        return pol["contoh"]
    coll, field = target_of(entry)
    try:
        prefix, width = render_format(pol["format"], ctx=ctx or {})
    except ValueError:
        return pol["contoh"]
    last = await peek_counter(db, f"autonum:{coll}:{field}:{prefix}")
    if last is None:
        # Counter belum pernah dipakai: generator akan menyemai dari nomor
        # tertinggi yang sudah ada di koleksi (lihat gen_prefixed_number).
        rx = re.compile(r"(\d+)\s*$")
        latest = await db[coll].find(
            {field: {"$regex": f"^{re.escape(prefix)}"}}, {field: 1, "_id": 0}
        ).sort(field, -1).limit(1).to_list(1)
        m = rx.search(str((latest or [{}])[0].get(field, ""))) if latest else None
        last = int(m.group(1)) if m else 0
    return f"{prefix}{last + 1:0{width}d}"


async def issue_number(db, key: str, *, ctx: Optional[dict] = None,
                       requested: str = "") -> str:
    """Nomor sah untuk dokumen baru — menghormati mode OTOMATIS/MANUAL.

    Satu-satunya pintu penomoran yang boleh dipakai endpoint yang MENERIMA nomor
    ketikan pemakai. Endpoint yang memang selalu otomatis tetap boleh memanggil
    `gen_prefixed_number` langsung.
    """
    entry = _entry(key)
    coll, field = target_of(entry)
    pol = await policy(db, key)
    requested = (requested or "").strip()

    if pol["mode"] == "manual":
        if not requested:
            raise HTTPException(400, (
                f"Penomoran {pol['label']} disetel MANUAL: nomor wajib diisi. "
                f"Pola yang berlaku: {pol['format']} (contoh: {pol['contoh']}). "
                "Ubah ke otomatis di Administrasi Sistem → Penomoran Dokumen bila "
                "ingin dibuatkan sistem."))
        if pol["error"]:
            raise HTTPException(400, (
                f"Format nomor {pol['label']} tidak sah ({pol['error']}) sehingga nomor "
                "manual tidak bisa diperiksa. Perbaiki formatnya dulu di Administrasi "
                "Sistem → Penomoran Dokumen."))
        if not re.match(pol["pola"], requested):
            raise HTTPException(400, (
                f"Nomor '{requested}' tidak mengikuti pola {pol['label']}: "
                f"{pol['format']} (contoh: {pol['contoh']}). Nomor berpola bebas tidak "
                "bisa diurutkan maupun dicari di arsip, jadi ditolak."))
        if await db[coll].find_one({field: requested}, {"_id": 1}):
            raise HTTPException(409, f"Nomor '{requested}' sudah dipakai dokumen lain.")
        return requested

    # ── mode otomatis ────────────────────────────────────────────────────────
    if requested:
        akan = await next_preview(db, key, ctx)
        raise HTTPException(400, (
            f"Penomoran {pol['label']} disetel OTOMATIS: nomor tidak boleh diketik "
            f"manual. Nomor yang akan dipakai: {akan}. Kosongkan kolom nomor, atau "
            "ubah mode ke manual di Administrasi Sistem → Penomoran Dokumen."))
    try:
        prefix, width = render_format(entry["default_format"], ctx=ctx or {})
    except ValueError:
        prefix, width = f"{key.split('.')[0][:3].upper()}-", 4
    return await gen_prefixed_number(db, coll, field, prefix, width, ctx, config_key=key)
