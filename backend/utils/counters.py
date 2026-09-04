"""
P3 TD-010 Part A — Shared Counter Helper
========================================
Single Source Of Truth (SSOT) for atomic sequence counters across the ERP.

Before consolidation:
  - `counters`         (generic; rahaza_lkp, rahaza_ap_from_gr, warehouse, rahaza_po)
  - `dewi_counters`    (dewi_maklon_billing, dewi_maklon_pos, dewi_cmt_progress)
  - `rahaza_counters`  (rahaza_sprint22 — `{name: ..., seq: ...}` schema variant)

After consolidation:
  - `counters` (SSOT)  with `{_id, seq, namespace}` shape
    - `_id`: counter key (e.g., "lkp_2026", "mkl_BUY01_2026", "mi_number")
    - `namespace`: discriminator (`generic` | `dewi` | `rahaza` | …)
    - `seq`: atomic sequence integer

Pattern:
    from utils.counters import next_counter, next_counter_batch

    n = await next_counter(db, "lkp_2026", namespace="rahaza")
    # → returns increment-by-1, upsert behavior preserved

    start_seq = await next_counter_batch(db, "mi_number", count=5, namespace="rahaza")
    # → returns the FIRST seq of the reserved range (atomic batch)

Migration script: /app/backend/migrations/migrate_counters_unification.py
"""
from __future__ import annotations
import re
import time
from datetime import datetime, timezone
from pymongo import ReturnDocument
from typing import Optional

from utils.waktu import WIB, as_aware_utc


async def next_counter(db, key: str, *, namespace: str = 'generic') -> int:
    """Atomically increment counter for `key` by 1 and return new seq.

    Uses upsert + ReturnDocument.AFTER. `namespace` is recorded on first
    insert for traceability but does NOT participate in uniqueness — `_id`
    (the key) is globally unique across the unified `counters` collection.
    """
    doc = await db.counters.find_one_and_update(
        {'_id': key},
        {
            '$inc': {'seq': 1},
            '$setOnInsert': {'namespace': namespace},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc['seq'])


async def next_counter_batch(
    db, key: str, *, count: int, namespace: str = 'generic',
) -> int:
    """Atomically reserve `count` consecutive seq values; return FIRST in range.

    Example: if current seq=10 and count=3, returns 11 (range 11..13 reserved).
    Useful for batch creation (e.g., multiple work orders in one mutation).
    """
    if count < 1:
        raise ValueError('count must be >= 1')
    doc = await db.counters.find_one_and_update(
        {'_id': key},
        {
            '$inc': {'seq': count},
            '$setOnInsert': {'namespace': namespace},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc['seq']) - count + 1


async def peek_counter(db, key: str) -> Optional[int]:
    """Read current seq without incrementing (returns None if counter absent)."""
    doc = await db.counters.find_one({'_id': key}, {'seq': 1})
    return int(doc['seq']) if doc else None


async def gen_prefixed_number(db, collection: str, field: str, prefix: str,
                              width: int = 4, ctx: Optional[dict] = None,
                              config_key: Optional[str] = None) -> str:
    """Race-safe prefixed sequential number (RC-5 mitigation).

    Replaces the unsafe `count_documents(...) + 1` numbering anti-pattern that races
    under concurrency (→ duplicate number / E11000 500) and reuses numbers after
    void/delete. Uses the atomic `counters` SSOT (`$inc`) with a LAZY max-initialisation
    so it does not collide with historical count-based numbers already in the collection.

    key = f"autonum:{collection}:{field}:{prefix}". On first use it seeds the counter to
    the max trailing integer of existing docs under `prefix`, then increments atomically.

    Example:  await gen_prefixed_number(db, "rahaza_journal_entries", "je_number",
                                        f"JE-{d:%Y%m%d}-", 4)  ->  "JE-20260705-0007"

    FORMAT TERKONFIGURASI (2026-07): bila owner menyimpan format untuk
    "<collection>.<field>" di `doc_number_configs`, format itulah yang dipakai —
    `prefix`/`width` bawaan kode menjadi cadangan. Tidak ada generator kedua;
    ini tetap satu-satunya pintu penomoran race-safe.

    `config_key` (2026-08-05, tahap 2): dipakai bila SATU koleksi+field menampung
    LEBIH DARI SATU jenis dokumen dengan awalan berbeda — mis. `rahaza_ar_invoices.
    invoice_number` dipakai invoice AR Finance (AR-…) DAN invoice maklon otomatis
    (INV-MKL-…). Tanpa ini, satu format akan menimpa keduanya.
    """
    import re
    prefix, width = await resolve_format(db, collection, field, prefix, width, ctx,
                                         config_key=config_key)
    key = f"autonum:{collection}:{field}:{prefix}"
    if await db.counters.find_one({'_id': key}, {'_id': 1}) is None:
        start = 0
        latest = await db[collection].find(
            {field: {'$regex': f'^{re.escape(prefix)}'}}, {field: 1, '_id': 0}
        ).sort(field, -1).limit(1).to_list(1)
        if latest:
            m = re.search(r'(\d+)\s*$', str(latest[0].get(field, '')))
            if m:
                start = int(m.group(1))
        # atomic lazy-init (only the first writer wins; concurrent inits are idempotent)
        await db.counters.update_one(
            {'_id': key},
            {'$setOnInsert': {'seq': start, 'namespace': 'autonum'}},
            upsert=True,
        )
    seq = await next_counter(db, key, namespace='autonum')
    number = f"{prefix}{seq:0{width}d}"
    # ── PENYEMBUHAN DIRI: pencacah bisa TERTINGGAL di belakang dokumen nyata ──
    # Penyemai/impor yang menulis dokumen bernomor LANGSUNG ke koleksi (tanpa lewat
    # generator ini) tidak menaikkan pencacah. Lazy-init hanya jalan SEKALI, jadi
    # setelah itu nomor yang dikeluarkan bisa menabrak nomor yang sudah ada dan
    # seluruh endpoint balas 500 E11000 (terjadi nyata: pencacah GR di 64 padahal
    # dokumen sudah sampai GR-00308). Di sini kami periksa tabrakannya, lalu
    # mendorong pencacah ke angka tertinggi yang benar-benar ada dan mengulang.
    for _ in range(5):
        if await db[collection].find_one({field: number}, {'_id': 1}) is None:
            return number
        highest = 0
        async for doc in db[collection].find(
                {field: {'$regex': f'^{re.escape(prefix)}'}}, {field: 1, '_id': 0}):
            m = re.search(r'(\d+)\s*$', str(doc.get(field, '')))
            if m:
                highest = max(highest, int(m.group(1)))
        await db.counters.update_one({'_id': key}, {'$max': {'seq': highest}}, upsert=True)
        seq = await next_counter(db, key, namespace='autonum')
        number = f"{prefix}{seq:0{width}d}"
    return number


# ─── Format nomor dokumen yang bisa diatur owner ──────────────────────────────
# Layar: Portal Administrasi Sistem → Penomoran Dokumen.
CONFIG_COLL = 'doc_number_configs'
_SEQ_RE = re.compile(r'\{SEQ(?::(\d+))?\}')
_TOKEN_RE = re.compile(r'\{([A-Z_]+)(?::\d+)?\}')
_CFG_CACHE: dict[str, tuple[float, Optional[dict]]] = {}
_CFG_TTL = 10.0  # detik — perubahan format terasa hampir seketika tanpa membanjiri DB


def render_format(fmt: str, *, now: Optional[datetime] = None,
                  ctx: Optional[dict] = None, require_seq: bool = True) -> tuple[str, int]:
    """Ubah format owner menjadi (prefix, lebar_digit).

    Token: {YYYY} {YY} {MM} {DD} {SEQ:n} + token konteks per jenis dokumen.
    {SEQ:n} WAJIB berada di akhir; teks setelahnya tidak didukung karena
    generator menempelkan nomor urut di ujung.

    `require_seq=False` dipakai untuk KODE MASTER (mis. SKU potongan) yang
    keunikannya berasal dari kombinasi token, bukan dari nomor urut — lebar
    digit yang dikembalikan 0.

    Raises ValueError bila format tidak sah (dipakai juga oleh validasi API).
    """
    now = now or datetime.now(timezone.utc)
    # 2026-08-07 (P3) — token tanggal HARUS mengikuti kalender WIB, bukan jam UTC
    # server. Dulu `{YYYY}{MM}{DD}` diambil dari waktu UTC, sehingga setiap hari
    # antara 00:00–07:00 WIB nomor dokumen memakai TANGGAL KEMARIN (dan pada 1
    # Januari / tanggal 1, memakai TAHUN atau BULAN yang salah). Penomoran adalah
    # identitas dokumen — salah periode berarti salah arsip dan salah urutan.
    now_lokal = as_aware_utc(now).astimezone(WIB)
    ctx = {str(k).upper(): str(v) for k, v in (ctx or {}).items() if v not in (None, "")}

    m = _SEQ_RE.search(fmt or "")
    if not m and require_seq:
        raise ValueError("Format wajib memuat {SEQ} atau {SEQ:n}.")
    if m:
        if fmt[m.end():].strip():
            raise ValueError("{SEQ} harus berada di paling akhir format.")
        width = int(m.group(1) or 4)
        if not 1 <= width <= 10:
            raise ValueError("Jumlah digit {SEQ:n} harus antara 1 dan 10.")
        head = fmt[:m.start()]
    else:
        width, head = 0, fmt or ""

    base = {"YYYY": f"{now_lokal:%Y}", "YY": f"{now_lokal:%y}",
            "MM": f"{now_lokal:%m}", "DD": f"{now_lokal:%d}"}
    unknown = [t for t in _TOKEN_RE.findall(head) if t not in base and t not in ctx]
    if unknown:
        raise ValueError("Token tidak dikenal: " + ", ".join("{" + u + "}" for u in unknown))
    for token, value in {**base, **ctx}.items():
        head = head.replace("{" + token + "}", value)
    if not head.strip():
        raise ValueError("Format tidak boleh kosong.")
    return head, width


def validate_format(fmt: str, tokens: Optional[list] = None, *, require_seq: bool = True) -> str:
    """Validasi format & kembalikan contoh nomor (untuk pratinjau di layar admin)."""
    sample_ctx = {t: t[:3].upper() for t in (tokens or [])}
    prefix, width = render_format(fmt, ctx=sample_ctx, require_seq=require_seq)
    return f"{prefix}{1:0{width}d}" if width else prefix


async def resolve_master_code(db, key: str, ctx: dict, default: str) -> str:
    """Kode master (SKU) yang formatnya bisa diatur owner — tanpa nomor urut.

    Bila format belum diatur / tidak sah, `default` bawaan kode dipakai.
    """
    try:
        cfg = await db[CONFIG_COLL].find_one({"key": key, "active": True}, {"_id": 0, "format": 1})
        if cfg and cfg.get("format"):
            code, _ = render_format(cfg["format"], ctx=ctx, require_seq=False)
            return code
    except Exception as e:  # noqa: BLE001
        # 2026-08-07 — DULU `except (ValueError, Exception): pass`.
        # Dua masalah: (a) `(ValueError, Exception)` itu mubazir — `Exception`
        # sudah mencakup `ValueError`, jadi tuple-nya menyesatkan pembaca;
        # (b) yang lebih penting, owner bisa menyimpan format KODE MASTER di layar
        # admin, formatnya ditolak diam-diam, dan sistem terus memakai format
        # bawaan. Owner melihat formatnya "tersimpan" tetapi SKU baru tetap
        # memakai pola lama — tanpa satu pun pesan. Sekarang selalu tercatat.
        import logging
        logging.getLogger(__name__).warning(
            "[kode-master] format '%s' tidak bisa dipakai — memakai bawaan kode '%s'. "
            "Kode master baru TIDAK akan mengikuti format yang disimpan owner: %s",
            key, default, e)
    return default


async def resolve_format(db, collection: str, field: str, prefix: str,
                         width: int, ctx: Optional[dict] = None,
                         config_key: Optional[str] = None) -> tuple[str, int]:
    """Pakai format owner bila ada & sah; kalau tidak, pakai bawaan kode.

    Sengaja TIDAK pernah melempar error: format rusak = kembali ke perilaku lama,
    supaya salah ketik di layar admin tidak pernah memblokir transaksi.
    """
    key = config_key or f"{collection}.{field}"
    cached = _CFG_CACHE.get(key)
    nowts = time.time()
    if cached and nowts - cached[0] < _CFG_TTL:
        cfg = cached[1]
    else:
        try:
            cfg = await db[CONFIG_COLL].find_one({"key": key, "active": True}, {"_id": 0, "format": 1})
        except Exception:
            cfg = None
        _CFG_CACHE[key] = (nowts, cfg)
    if not cfg or not cfg.get("format"):
        return prefix, width
    try:
        return render_format(cfg["format"], ctx=ctx)
    except ValueError:
        return prefix, width


def invalidate_format_cache(key: Optional[str] = None) -> None:
    """Dipanggil layar admin setelah menyimpan supaya perubahan langsung berlaku."""
    if key:
        _CFG_CACHE.pop(key, None)
    else:
        _CFG_CACHE.clear()


# ─── JARING PENGAMAN DATABASE: NOMOR DOKUMEN WAJIB UNIK ───────────────────────
# 2026-08-07 — temuan saat menutup anti-pola RC-5 (`count_documents()+1`).
# Penomoran di KODE sudah atomik lewat `gen_prefixed_number`, TETAPI delapan
# koleksi bernomor sama sekali tidak punya index unik, antara lain:
#     warehouse_receiving.gr_number        (penerimaan barang → MENAMBAH STOK)
#     rahaza_material_issues.issue_number  (pengeluaran barang → MENGURANGI STOK)
#     dewi_procurement_requests.request_number
#     acc_purchase_requests.pr_number
#     production_jobs.job_number · production_returns.return_number
# Tanpa index unik, satu saja jalur tulis yang melewati generator (impor massal,
# migrasi, skrip perbaikan, atau kode baru) bisa menanam nomor KEMBAR secara
# diam-diam. Nomor kembar pada dokumen stok/uang berarti dua transaksi berbeda
# tampak sebagai satu dokumen — dan tidak ada yang tahu sampai angka tak cocok.
#
# `partialFilterExpression: {field: {"$gt": ""}}` HANYA mengindeks string tidak
# kosong, sehingga dokumen lama yang nomornya null/"" tidak menghalangi.
UNIQUE_NUMBERED_FIELDS: tuple[tuple[str, str], ...] = (
    ("rahaza_journal_entries", "je_number"),
    ("rahaza_work_orders", "wo_number"),
    ("rahaza_orders", "order_number"),
    ("rahaza_ar_invoices", "invoice_number"),
    ("rahaza_ap_invoices", "invoice_number"),
    ("rahaza_payroll_runs", "run_number"),
    ("rahaza_material_issues", "issue_number"),
    ("warehouse_receiving", "gr_number"),
    ("dewi_maklon_pos", "po_number"),
    ("rahaza_purchase_orders", "po_number"),
    ("wh_cmt_dispatches", "dispatch_number"),
    ("wh_delivery_notes", "dn_number"),
    ("cmt_delivery_notes", "dn_number"),
    ("dewi_maklon_samples", "sample_code"),
    ("production_jobs", "job_number"),
    ("production_returns", "return_number"),
    ("dewi_procurement_requests", "request_number"),
    ("acc_purchase_requests", "pr_number"),
)


async def find_duplicate_numbers(db, collection: str, field: str, limit: int = 20) -> list:
    """Nomor yang muncul lebih dari sekali (untuk laporan yang bisa ditindak)."""
    try:
        rows = await db[collection].aggregate([
            {"$match": {field: {"$nin": [None, ""]}}},
            {"$group": {"_id": f"${field}", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": limit},
        ]).to_list(limit)
        return [{"number": r["_id"], "count": r["n"]} for r in rows]
    except Exception:
        return []


async def ensure_unique_number_indexes(db, logger=None) -> dict:
    """Pasang index unik untuk semua field nomor dokumen. IDEMPOTEN.

    Sengaja TIDAK melempar error: bila sebuah koleksi sudah memuat nomor kembar,
    index-nya gagal dibuat — dan itu harus dilaporkan DENGAN NOMORNYA supaya bisa
    diperbaiki, bukan ditelan diam-diam. Nilai balik dipakai gate/laporan.
    """
    import logging
    log = logger or logging.getLogger(__name__)
    created, already, blocked = [], [], []
    for coll, field in UNIQUE_NUMBERED_FIELDS:
        try:
            await db[coll].create_index(
                field, unique=True, name=f"uniq_{field}",
                partialFilterExpression={field: {"$gt": ""}},
            )
            created.append(f"{coll}.{field}")
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "already exists" in msg or "IndexOptionsConflict" in msg or "same name" in msg:
                already.append(f"{coll}.{field}")
                continue
            dups = await find_duplicate_numbers(db, coll, field)
            blocked.append({"collection": coll, "field": field,
                            "duplicates": dups, "error": msg[:200]})
            log.error(
                "[nomor-dokumen] index unik %s.%s GAGAL — ada nomor KEMBAR: %s. "
                "Perbaiki duplikatnya, lalu restart backend supaya index terpasang.",
                coll, field, dups or msg[:120])
    if blocked:
        log.error("[nomor-dokumen] %d koleksi masih rawan nomor kembar.", len(blocked))
    else:
        log.info("[nomor-dokumen] semua %d field nomor dokumen dilindungi index unik.",
                 len(UNIQUE_NUMBERED_FIELDS))
    return {"created": created, "already": already, "blocked": blocked}
