"""routes.marketing_data_import — **Impor Data Marketing: jalan utama TANPA AI**.

ALUR YANG DIPAKSAKAN (dan alasannya)
------------------------------------
``pilih jenis data`` → ``pilih toko/akun`` → (``pilih host/kreator/katalog`` bila
jenisnya menuntut) → ``unduh template`` → ``unggah`` → ``periksa pemetaan kolom``
→ ``pratinjau + validasi`` → ``commit`` → (``rollback`` bila salah)

Kenapa urutan ini, bukan "unggah dulu biar sistem menebak":

* **Jenis data dipilih manusia.** Mesin lama menebak lewat AI; salah tebak =
  baris masuk tabel yang salah dan tidak pernah muncul di layar mana pun.
* **Toko dipilih SEBELUM unggah.** Ini membuat satu berkas mustahil tercampur
  antar toko, dan membuat `account_id` selalu ada — akar dari cacat terbesar
  yang diukur audit (60/60 order, 25/25 iklan, 18/18 sesi live tanpa `account_id`).
* **Host/kreator dipilih dari yang SUDAH di-assign ke toko itu.** Kalau tidak,
  jam kerja & komisi bisa dibebankan ke toko yang tidak pernah memakai orangnya.
* **Pemetaan kolom ditampilkan sebelum commit**, dengan sumber keputusannya
  (`exact` / `synonym` / `fuzzy` / `usulan`). Pemetaan yang tidak bisa diperiksa
  manusia adalah pemetaan yang akan dipercaya sampai laporannya kacau.
* **AI opsional.** Tombol "Bantu petakan dengan AI" hanya MENGUSULKAN pemetaan
  untuk kolom yang belum terpetakan; tidak pernah menimpa yang sudah pasti,
  tidak pernah menjadi syarat.

Berkas yang diunggah disimpan di disk dan **dibaca ulang saat commit**, jadi
dokumen sesi tidak pernah membesar melewati batas dokumen Mongo — dan pratinjau
selalu bisa dihitung ulang dari sumber aslinya kalau pemetaan diubah.
"""
from __future__ import annotations

import os
import io
import csv
import json
import uuid
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# F6 (sesi #10) — endpoint DAFTAR/RINGKAS wajib menyaring sendiri (middleware
# hanya menolak permintaan yang MENYEBUT toko, ia tidak tahu isi jawaban).
from core import marketing_account_scope as _scope
from database import get_db
from auth import require_auth, log_activity
from core import marketing_account_scope as scope
from core.marketing_import_schema import (
    get_source_type, source_type_catalog, source_group_catalog, SourceType,
)
from core import marketing_import_engine as eng
from core import marketing_sales_shape as _shape
from core import marketing_cycle as _cycle
# Sesi #20 — SSOT kosakata status fulfillment. Impor pesanan dulu menulis
# 'unallocated' yang TIDAK dikenal antrean gudang ⇒ 559 pesanan "Perlu dikirim"
# tidak pernah terlihat tim gudang. Sekarang status awal diturunkan dari status
# platform lewat satu pintu (`initial_status`).
from core import fulfillment_status as _fstat

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/data-import", tags=["marketing-data-import"])

UPLOAD_DIR = "marketing-data-import"   # prefix di object storage (bukan folder pod)
from object_storage import put_object as _put_object, get_object as _get_object


def _read_session_file(path: str) -> Optional[bytes]:
    """Baca berkas sesi impor: object storage dulu, jatuh ke berkas pod lama (pra-migrasi)."""
    if not path:
        return None
    if os.path.isabs(path):
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except OSError:
            return None
    found = _get_object(path)
    return found[0] if found else None

SESSIONS = "marketing_data_import_sessions"
# F1 — ingatan susunan kolom: (source_type, fingerprint) → pemetaan yang sudah
# dikonfirmasi manusia. Fingerprint dikenal ⇒ pemetaan langsung dipakai (tanpa AI).
FORMATS = "marketing_data_import_formats"
# F3 — JEJAK PEMULIHAN untuk impor yang hanya MEMPERBARUI (Ekspor B & C).
# Rollback biasa cukup menghapus baris yang DIBUAT sesi ini. Impor fulfillment
# tidak membuat baris apa pun — ia mengubah pesanan milik impor Ekspor A — jadi
# satu-satunya cara "Batalkan impor" bisa menepati janjinya adalah menyimpan
# nilai SEBELUM diubah, per pesanan, di koleksi terpisah. Disimpan di luar
# dokumen sesi supaya batas 16 MB dokumen Mongo tidak pernah tersentuh oleh
# berkas 20.000 baris.
UNDO = "marketing_data_import_undo"
MAX_FILE_MB = 15
ROLLBACK_HOURS = 72

# Nama platform di berkas ekspor vs `platform` di master toko. Dipakai penjaga
# platform: berkas TikTok tidak boleh masuk toko Shopee (omzet pindah toko).
_PLATFORM_ALIASES = (
    ("tiktok", "tiktokshop", "tiktok shop", "tiktokid"),
    ("shopee", "shopeeid"),
    ("tokopedia", "toped"),
    ("lazada",),
    ("blibli",),
)


def _norm_plat(s: Any) -> str:
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def _platform_matches(account_platform: Any, file_value: Any) -> bool:
    """True bila nama platform di berkas menunjuk platform toko yang sama."""
    a, f = _norm_plat(account_platform), _norm_plat(file_value)
    if not a or not f:
        return True
    if a == f:
        return True
    for group in _PLATFORM_ALIASES:
        names = {_norm_plat(n) for n in group}
        if a in names and f in names:
            return True
    return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ser(obj):
    if isinstance(obj, list):
        return [_ser(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _ser(v) for k, v in obj.items() if k != "_id"}
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def _user(request: Request) -> dict:
    return getattr(request.state, "user", {}) or {}


# ═══════════════════════════════════════════════════════════════════════════════
# KATALOG JENIS DATA & KONTEKS
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/source-types")
async def list_source_types(request: Request, include_deprecated: bool = Query(True)):
    """Daftar resmi 'ini impor data apa' — dipakai kartu pilihan di layar.

    SESI #37 — bawaan `include_deprecated=True` DISENGAJA: pembaca lama
    (riwayat impor, audit kontrak FE↔BE) mencari sifat jenis lama di daftar ini,
    dan menghilangkannya diam-diam akan membuat label riwayat jadi kosong.
    Wizard yang ingin daftar pilihan bersih memakai `/source-groups`.
    """
    await require_auth(request)
    rows = source_type_catalog()
    if not include_deprecated:
        rows = [r for r in rows if not r["deprecated"]]
    return {"ok": True, "source_types": rows}


@router.get("/source-groups")
async def list_source_groups(request: Request,
                             include_deprecated: bool = Query(False)):
    """**6 KELOMPOK** impor (sesi #37) — langkah pertama wizard.

    22 jenis terlalu banyak untuk dipilih tanpa petunjuk, dan salah pilih jenis
    memasukkan data ke tabel yang salah tanpa satu pun galat. Jadi: staf memilih
    KELOMPOK (6 pintu), lalu jenis persisnya diusulkan `POST /detect` dari isi
    berkasnya. Jenis lama TETAP diterima `POST /upload` — hanya tidak ditawarkan.
    """
    await require_auth(request)
    groups = source_group_catalog(include_deprecated=include_deprecated)
    return {
        "ok": True,
        "groups": groups,
        "total_types": sum(g["type_count"] for g in groups),
        "hidden_types": sum(g["hidden_count"] for g in groups),
        "note": ("Jenis yang disembunyikan tetap DITERIMA saat mengunggah "
                 "(impor yang sudah jalan tidak putus) — ia hanya tidak lagi "
                 "ditawarkan karena ada jenis lain yang lebih lengkap penjaganya."),
    }


@router.get("/context-options")
async def context_options(
    request: Request,
    source_type: str = Query(...),
    account_id: Optional[str] = Query(None),
):
    """Pilihan konteks yang SAH untuk jenis data ini.

    Sengaja server yang menyaring: host/kreator yang dikembalikan **hanya** yang
    sudah di-assign ke akun terpilih. Kalau penyaringan dikerjakan di browser,
    satu layar yang lupa menyaring cukup untuk membebankan gaji host ke toko lain.
    """
    await require_auth(request)
    db = get_db()
    try:
        st = get_source_type(source_type)
    except KeyError as e:
        raise HTTPException(400, str(e)) from None

    out: Dict[str, Any] = {
        "ok": True,
        "source_type": st.key,
        "account_scope": st.account_scope,
        "context": list(st.context),
        "accounts": await scope.account_options(db),
    }
    if account_id:
        acc = await db[scope.ACCOUNTS].find_one({"id": account_id}, {"_id": 0})
        if not acc:
            raise HTTPException(404, f"Akun '{account_id}' tidak ditemukan")
        out["account"] = _ser(acc)
        if "creator" in st.context:
            out["creators"] = _ser(await scope.creator_options(db, account_id))
        if "host" in st.context:
            out["hosts"] = _ser(await scope.host_options(db, account_id))
        if "live_session" in st.context:
            # F18#3 — rincian produk menempel pada SATU sesi live tertentu. Sesi
            # dipilih di wizard (bukan dicocokkan dari judul di berkas), supaya
            # tidak ada baris yang menempel pada sesi yang salah karena judulnya
            # kebetulan mirip.
            sess = await db.marketing_live_sessions.find(
                {"account_id": account_id},
                {"_id": 0, "id": 1, "title": 1, "session_date": 1, "host_id": 1,
                 "host_name": 1, "revenue": 1, "orders": 1, "platform": 1}
            ).sort("session_date", -1).to_list(200)
            out["live_sessions"] = _ser(sess)
        if "catalog" in st.context:
            cats = await db.marketing_catalogs.find(
                {"account_id": account_id}, {"_id": 0, "id": 1, "name": 1,
                                             "platform": 1, "is_active": 1}
            ).to_list(200)
            out["catalogs"] = _ser(cats)
    return out


@router.get("/template/{source_type}")
async def download_template(source_type: str, request: Request,
                            fmt: str = Query("xlsx", pattern="^(xlsx|csv)$")):
    """Template kolom standar per jenis data — supaya staf tidak menebak header."""
    await require_auth(request)
    try:
        st = get_source_type(source_type)
    except KeyError as e:
        raise HTTPException(400, str(e)) from None

    if fmt == "csv":
        data = eng.build_template_csv(st)
        media = "text/csv"
        ext = "csv"
    else:
        data = eng.build_template_xlsx(st)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    fname = f"template-impor-{st.key}.{ext}"
    return StreamingResponse(
        io.BytesIO(data), media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ═══════════════════════════════════════════════════════════════════════════════
# UNGGAH → SESI
# ═══════════════════════════════════════════════════════════════════════════════
async def _validate_context(db, st: SourceType, account_id: Optional[str],
                            ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Tegakkan lingkup & konteks SEBELUM satu baris pun dibaca."""
    resolved: Dict[str, Any] = {}
    if st.account_scope == "required":
        acc = await scope.require_account(db, account_id)
        resolved["account"] = acc
    elif account_id:
        acc = await db[scope.ACCOUNTS].find_one({"id": account_id}, {"_id": 0})
        if not acc:
            raise HTTPException(404, f"Akun '{account_id}' tidak ditemukan")
        resolved["account"] = acc

    aid = (resolved.get("account") or {}).get("id")
    if "host" in st.context:
        hid = ctx.get("host_id")
        if not hid:
            raise HTTPException(400, "host_id wajib untuk jenis data ini: pilih host "
                                     "live yang membawakan sesinya")
        resolved["host"] = await scope.assert_host_assigned(db, hid, aid)
    if "creator" in st.context:
        cid = ctx.get("creator_id")
        if not cid:
            raise HTTPException(400, "creator_id wajib untuk jenis data ini: pilih "
                                     "kreator penerima sample")
        resolved["creator"] = await scope.assert_creator_assigned(db, cid, aid)
    if "catalog" in st.context:
        kid = ctx.get("catalog_id")
        if not kid:
            raise HTTPException(400, "catalog_id wajib untuk jenis data ini: pilih "
                                     "katalog toko tujuan")
        cat = await db.marketing_catalogs.find_one({"id": kid}, {"_id": 0})
        if not cat:
            raise HTTPException(404, f"Katalog '{kid}' tidak ditemukan")
        if aid and cat.get("account_id") != aid:
            raise HTTPException(400, f"Katalog '{cat.get('name')}' bukan milik akun "
                                     f"yang dipilih")
        resolved["catalog"] = cat
    if "live_session" in st.context:
        sid = ctx.get("live_session_id")
        if not sid:
            raise HTTPException(400, "live_session_id wajib untuk jenis data ini: "
                                     "pilih sesi live yang rinciannya diunggah")
        sess = await db.marketing_live_sessions.find_one({"id": sid}, {"_id": 0})
        if not sess:
            raise HTTPException(404, f"Sesi live '{sid}' tidak ditemukan")
        if aid and sess.get("account_id") != aid:
            raise HTTPException(
                400, f"Sesi live '{sess.get('title')}' bukan milik toko yang dipilih. "
                     f"Rincian produk harus menempel pada sesi milik toko itu.")
        resolved["live_session"] = sess
    return resolved


@router.post("/detect")
async def detect_file(
    request: Request,
    file: UploadFile = File(...),
    account_id: Optional[str] = Form(None),
):
    """Sesi #34 — **sistem membaca berkas dulu, lalu MENGUSULKAN jenis & platform.**

    Ini tidak menggantikan pilihan manusia: hasilnya hanya usulan berperingkat
    beserta BUKTI (berapa kolom cocok, kolom wajib apa yang hilang, sidik
    platform apa yang ditemukan). Pemilik meminta ini karena daftar 22 jenis
    impor terlalu panjang untuk dipilih tanpa petunjuk, dan salah pilih jenis
    membuat data masuk tabel yang salah.
    """
    await require_auth(request)
    db = get_db()
    raw = await file.read()
    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(400, f"Berkas lebih dari {MAX_FILE_MB} MB")
    fname = file.filename or "data.csv"
    if not fname.lower().endswith((".csv", ".xlsx", ".xls", ".xlsm", ".tsv", ".txt")):
        raise HTTPException(400, "Format berkas harus CSV atau Excel (.xlsx)")

    catalog = []
    for t in source_type_catalog():
        try:
            catalog.append(get_source_type(t["key"]))
        except KeyError:
            continue
    res = eng.detect_source_type(raw, fname, catalog, top=6)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error") or "Berkas tidak bisa dibaca")

    acc = None
    if account_id:
        acc = await db[scope.ACCOUNTS].find_one({"id": account_id}, {"_id": 0})
    plat_file = (res.get("platform") or {}).get("platform") or ""
    plat_acc = (acc or {}).get("platform") or ""
    warn = ""
    if plat_file and plat_acc and not _platform_matches(plat_acc, plat_file):
        warn = (f"Sidik kolom berkas menunjuk platform {plat_file.upper()}, sedangkan toko "
                f"'{acc.get('account_name')}' berplatform {str(plat_acc).upper()}.")

    # Toko yang platformnya COCOK dengan berkas — supaya staf tidak perlu menebak
    # toko mana yang benar dari daftar panjang.
    matching_accounts = []
    if plat_file:
        rows_acc = await db[scope.ACCOUNTS].find(
            {"status": {"$ne": "inactive"}},
            {"_id": 0, "id": 1, "account_name": 1, "account_code": 1, "platform": 1,
             "platform_warehouse_name": 1}).to_list(200)
        matching_accounts = [a for a in rows_acc
                             if _platform_matches(a.get("platform"), plat_file)][:20]

    # 10 baris MENTAH untuk viewer tabel di layar.
    sample_headers = res.get("headers") or []
    try:
        _h, sample_rows = eng.parse_table(raw, fname, None)
    except Exception:  # noqa: BLE001
        sample_rows = []
    return {
        "ok": True,
        "filename": fname,
        "file_size_kb": round(len(raw) / 1024, 1),
        "headers": sample_headers,
        "row_count": res.get("row_count") or 0,
        "raw_preview": [{k: (v.isoformat() if isinstance(v, datetime) else v)
                         for k, v in r.items()} for r in sample_rows[:10]],
        "platform": res.get("platform") or {},
        "platform_warning": warn,
        "matching_accounts": matching_accounts,
        "best": res.get("best"),
        "ranking": res.get("results") or [],
    }


@router.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    source_type: str = Form(...),
    account_id: Optional[str] = Form(None),
    host_id: Optional[str] = Form(None),
    creator_id: Optional[str] = Form(None),
    catalog_id: Optional[str] = Form(None),
    live_session_id: Optional[str] = Form(None),
):
    await require_auth(request)
    user = _user(request)
    db = get_db()

    try:
        st = get_source_type(source_type)
    except KeyError as e:
        raise HTTPException(400, str(e)) from None

    ctx_in = {"host_id": host_id, "creator_id": creator_id, "catalog_id": catalog_id,
              "live_session_id": live_session_id}
    resolved = await _validate_context(db, st, account_id, ctx_in)

    raw = await file.read()
    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(400, f"Berkas lebih dari {MAX_FILE_MB} MB")
    fname = file.filename or "data.csv"
    if not fname.lower().endswith((".csv", ".xlsx", ".xls", ".xlsm", ".tsv", ".txt")):
        raise HTTPException(400, "Format berkas harus CSV atau Excel (.xlsx)")

    try:
        headers, rows = eng.parse_table(raw, fname, st)
    except Exception as e:
        raise HTTPException(400, f"Berkas tidak bisa dibaca: {e}") from None
    if not headers:
        raise HTTPException(400, "Baris header tidak ditemukan di berkas")
    if not rows:
        raise HTTPException(400, "Berkas tidak punya baris data (hanya header)")

    session_id = str(uuid.uuid4())
    ext = os.path.splitext(fname)[1] or ".csv"
    path = f"{UPLOAD_DIR}/{session_id}{ext}"
    try:
        _put_object(path, raw, "application/octet-stream")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"Penyimpanan berkas tidak tersedia: {e}")

    mapping = eng.auto_map(headers, st)
    # ── F1 — sidik format: pemetaan yang sudah dikonfirmasi manusia DIINGAT ──
    #
    # "INGAT PEMETAAN SAYA" (dilengkapi 2026-08-14). Dua cacat ditutup di sini:
    #
    #  1. **Ingatan diam-diam.** Versi lama menimpa hasil `auto_map` dengan
    #     pemetaan tersimpan TANPA memberitahu siapa pun. Kalau pemetaan yang
    #     pernah dikonfirmasi ternyata salah (mis. kolom "Order Amount" dipetakan
    #     ke omzet SKU), setiap impor berikutnya mengulang kesalahan yang sama —
    #     dan layar tampak "otomatis benar". Sekarang asalnya DILAPORKAN
    #     (`format_memory`) dan bisa DILUPAKAN (`DELETE /formats/{fingerprint}`).
    #  2. **Pemetaan basi.** Field bisa berubah/dibuang saat skema jenis impor
    #     berkembang. Pemetaan tersimpan yang menunjuk field yang sudah tidak ada
    #     dulu diterima apa adanya ⇒ kolomnya hilang dari hasil tanpa satu pun
    #     galat. Sekarang entri seperti itu DIBUANG dan kolomnya dipetakan ulang
    #     oleh mesin, lalu disebut di `format_memory.dropped`.
    fingerprint = eng.format_fingerprint(headers)
    known_format = await db[FORMATS].find_one(
        {"source_type": st.key, "fingerprint": fingerprint}, {"_id": 0})
    format_known = False
    format_memory: Optional[dict] = None
    if known_format and known_format.get("mapping"):
        valid_fields = {f.name for f in st.input_fields}
        auto_by_col = {m["column"]: m for m in mapping}
        remembered, dropped = [], []
        for m in known_format["mapping"]:
            col = m.get("column")
            if col is None or col not in auto_by_col:
                continue                      # kolom tidak ada di berkas ini
            fld = m.get("field") or None
            if fld and fld not in valid_fields:
                dropped.append({"column": col, "field": fld})
                remembered.append(auto_by_col[col])     # dipetakan ulang mesin
                continue
            remembered.append({**auto_by_col[col], **{
                "column": col, "field": fld,
                "field_label": (st.field(fld).label if fld else None),
                "method": m.get("method") or ("manual" if fld else "none"),
                "score": m.get("score", 1.0 if fld else 0.0),
                # usulan mesin TETAP dibawa supaya pilihan lain masih sekali klik
                "candidates": (auto_by_col[col].get("candidates")
                               or m.get("candidates") or []),
                "note": m.get("note") or "",
            }})
        # kolom berkas yang tidak ada di ingatan tetap memakai hasil mesin
        seen_cols = {m["column"] for m in remembered}
        for m in mapping:
            if m["column"] not in seen_cols:
                remembered.append(m)
        if remembered:
            mapping = remembered
            format_known = True
            format_memory = {
                "fingerprint": fingerprint,
                "use_count": int(known_format.get("use_count") or 0),
                "last_used_at": _ser(known_format.get("last_used_at")),
                "last_used_by": known_format.get("last_used_by") or "",
                "saved_at": _ser(known_format.get("created_at")),
                "columns": len(known_format.get("headers") or headers),
                "dropped": dropped,
            }

    # ── F1 — baris DESKRIPSI KOLOM (baris ke-2 ekspor Seller Center) dibuang ──
    rows, desc_skipped = eng.strip_description_rows(rows, mapping, st)
    if not rows:
        raise HTTPException(400, "Setelah baris keterangan kolom dilewati, tidak ada "
                                 "baris data yang tersisa di berkas")

    preview = eng.build_rows(rows, mapping, st)
    report = eng.mapping_report(mapping, st)

    # ── sesi #34 — APA JENIS BERKAS INI SEBENARNYA? ───────────────────────────
    # Staf tetap yang MEMILIH jenis data (aturan anti-AI dipertahankan), tetapi
    # pilihan manusia bisa salah — dan salah pilih jenis berarti berkas pesanan
    # masuk sebagai penjualan harian. Di sini kecocokan header berkas terhadap
    # SETIAP jenis diukur, lalu dilaporkan apa adanya. Sistem tidak memindahkan
    # apa pun sendiri; ia hanya berhenti membiarkan kesalahan itu tak terlihat.
    detection = _detect_from_headers(headers, st, acc_platform=(resolved.get("account") or {}).get("platform"))

    # ── F1 — PENJAGA PLATFORM: berkas platform lain tidak boleh masuk toko ini ─
    acc_doc = resolved.get("account") or {}
    shop_guard_hint = ""
    shop_guard_warehouse = ""

    def _discard(p: str) -> None:
        """Buang berkas yang ditolak penjaga — jangan tinggalkan sampah di disk."""
        try:
            os.remove(p)
        except OSError:
            pass

    if st.platform_guard and acc_doc:
        found = {str((r.get("data") or {}).get(st.platform_guard) or "").strip()
                 for r in preview}
        found = {v for v in found if v}
        bad = sorted(v for v in found if not _platform_matches(acc_doc.get("platform"), v))
        if bad:
            try:
                os.remove(path)
            except OSError:
                pass
            raise HTTPException(400,
                f"Berkas ini berisi pesanan platform {', '.join(bad)}, sedangkan toko tujuan "
                f"'{acc_doc.get('account_name')}' berplatform "
                f"{acc_doc.get('platform')}. Pilih toko yang benar atau unggah berkas "
                f"ekspor toko ini — impor dibatalkan supaya omzet tidak masuk ke toko lain.")

    # ── F1 — PENJAGA TOKO: sidik toko di dalam berkas ("Warehouse Name") ─────
    # Penjaga platform di atas hanya menangkap "berkas Shopee masuk toko TikTok".
    # Ia TIDAK menangkap kesalahan yang jauh lebih mudah terjadi: memilih toko
    # TikTok yang SALAH dari 5 toko TikTok yang namanya mirip. Terbukti terjadi
    # 2026-08-12 — 559 pesanan gudang 'Outfit Boutique' (Rp 59.783.811) masuk ke
    # 'TikTok Daluna', dan tidak ada satu pun layar yang membantah. Ekspor Seller
    # Center membawa kolom `Warehouse Name` yang isinya sama untuk seluruh berkas,
    # dan master toko sudah menyimpannya (`platform_warehouse_name`, F0.7) — jadi
    # kesalahan ini BISA ditangkap sebelum satu baris pun tersimpan.
    if st.shop_guard and acc_doc:
        shops = sorted({str((r.get("data") or {}).get(st.shop_guard) or "").strip()
                        for r in preview} - {""})
        target = str(acc_doc.get("platform_warehouse_name") or "").strip()
        if shops:
            if target:
                bad = [v for v in shops if scope.norm(v) != scope.norm(target)]
                if bad:
                    _discard(path)
                    raise HTTPException(400,
                        f"Berkas ini berisi pesanan gudang platform "
                        f"'{', '.join(bad)}', sedangkan toko tujuan "
                        f"'{acc_doc.get('account_name')}' terdaftar dengan gudang "
                        f"platform '{target}'. Pilih toko yang benar — impor "
                        f"dibatalkan supaya omzet tidak masuk ke toko lain.")
            else:
                # Toko tujuan belum mengisi gudang platform. Kalau gudang di berkas
                # ternyata TERDAFTAR pada toko lain, hampir pasti tokonya salah pilih.
                owner = await db[scope.ACCOUNTS].find_one({
                    "id": {"$ne": acc_doc.get("id")},
                    "platform_warehouse_name": {"$in": shops},
                }, {"_id": 0, "account_name": 1, "account_code": 1,
                    "platform_warehouse_name": 1})
                if owner:
                    _discard(path)
                    raise HTTPException(400,
                        f"Berkas ini berisi pesanan gudang platform "
                        f"'{owner.get('platform_warehouse_name')}' yang di master toko "
                        f"terdaftar pada '{owner.get('account_name')}' "
                        f"({owner.get('account_code')}) — bukan pada toko tujuan "
                        f"'{acc_doc.get('account_name')}'. Pilih toko "
                        f"'{owner.get('account_name')}', atau kalau gudang ini memang "
                        f"milik '{acc_doc.get('account_name')}', isi dulu field "
                        f"'Gudang Platform' toko itu di menu Kelola Akun.")
                shop_guard_hint = (
                    f"Gudang platform di berkas: '{shops[0]}'. Toko tujuan "
                    f"'{acc_doc.get('account_name')}' belum mengisi 'Gudang Platform', "
                    f"jadi sistem TIDAK bisa memastikan berkas ini milik toko itu. "
                    f"Isi field itu di Kelola Akun supaya impor berikutnya terjaga "
                    f"otomatis dari salah pilih toko.")
                shop_guard_warehouse = shops[0]

    preview = await _annotate_master_links(
        db, st, {"account_id": acc_doc.get("id")}, preview)

    _live = resolved.get("live_session") or {}
    doc = {
        "id": session_id,
        "source_type": st.key,
        "source_label": st.label,
        "target_collection": st.collection,
        "filename": fname,
        "file_path": path,
        "file_size_kb": round(len(raw) / 1024, 1),
        # F12 — sidik ISI berkas. Satu berkas ekspor tidak mungkin milik dua toko,
        # jadi isi yang sama persis pada toko LAIN adalah bukti salah pilih toko.
        # Disimpan di sesi (bukan dihitung ulang) supaya riwayat lama pun bisa
        # dibandingkan tanpa membuka berkasnya lagi.
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "total_rows": len(rows),
        "description_rows_skipped": desc_skipped,
        "format_fingerprint": fingerprint,
        "format_known": format_known,
        # Asal-usul pemetaan yang dipakai layar untuk menjelaskan "kenapa kolom
        # ini sudah terpetakan padahal saya belum menyentuhnya".
        "format_memory": format_memory,
        "headers": headers,
        "mapping": mapping,
        "mapping_report": report,
        # ── sesi #34 — VIEWER TABEL: 10 baris MENTAH apa adanya dari berkas ────
        # Layar pemetaan dulu hanya menampilkan nama kolom; staf tidak pernah
        # melihat ISI berkasnya, jadi "kolom mana yang benar" harus dihafal.
        "raw_preview": [{k: (v.isoformat() if isinstance(v, datetime) else v)
                         for k, v in r.items()} for r in rows[:10]],
        # ── sesi #34 — BUKTI kecocokan jenis data & platform ──────────────────
        "detection": detection,
        "account_id": (resolved.get("account") or {}).get("id"),
        "account_name": (resolved.get("account") or {}).get("account_name"),
        "account_code": (resolved.get("account") or {}).get("account_code"),
        "account_platform": (resolved.get("account") or {}).get("platform"),
        # F1 — sidik toko: hasil PENJAGA TOKO supaya layar bisa menunjukkan
        # ke toko mana berkas ini akan masuk & kalau belum bisa dipastikan.
        "shop_guard_hint": shop_guard_hint,
        # Nama gudang yang TERBACA di berkas — dipakai tombol "Simpan gudang ini ke
        # master toko" supaya nama datang dari ekspor platform, bukan dari ingatan staf.
        "shop_guard_warehouse": shop_guard_warehouse,
        "host_id": ((resolved.get("host") or {}).get("id") or _live.get("host_id")),
        "host_name": ((resolved.get("host") or {}).get("name") or _live.get("host_name")),
        "creator_id": (resolved.get("creator") or {}).get("id"),
        "creator_name": (resolved.get("creator") or {}).get("name"),
        "catalog_id": (resolved.get("catalog") or {}).get("id"),
        "catalog_name": (resolved.get("catalog") or {}).get("name"),
        # F18#3 — sesi live tujuan rincian produk
        "live_session_id": _live.get("id"),
        "live_session_title": _live.get("title"),
        "live_session_date": _live.get("session_date"),
        "status": "mapping" if not report["ready"] else "ready",
        "ai_used": False,
        "ai_suggestion": None,
        "committed_ids": [],
        "committed_count": 0,
        "skipped_duplicates": 0,
        "rejected_count": 0,
        "committed_at": None,
        "rolled_back_at": None,
        "created_by": user.get("email", "system"),
        "created_by_id": user.get("id", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[SESSIONS].insert_one(dict(doc))
    doc.pop("_id", None)
    # Deteksi baris yang SUDAH ADA dilakukan di sini (bukan sesudah commit) supaya
    # pilihan "Lewati / Perbarui yang lama" diambil dengan angka di depan mata.
    dup = await _annotate_existing(db, st, doc, preview)
    return {"ok": True, "session": _ser(doc), "preview": _ser(preview[:50]),
            "preview_total": len(preview),
            "duplicates": dup,
            "summary": _summary(preview)}


def _detect_from_headers(headers: List[str], chosen: SourceType,
                         acc_platform: Any = None) -> dict:
    """Ukur kecocokan header berkas terhadap SEMUA jenis + sidik platform.

    Dipakai dua tempat: `POST /detect` (sebelum jenis dipilih) dan `POST /upload`
    (sesudah dipilih — untuk memberi tahu kalau pilihannya kemungkinan salah).
    """
    scored = []
    for t in source_type_catalog():
        try:
            st = get_source_type(t["key"])
        except KeyError:
            continue
        # Jenis ber-prenorm dinilai hanya bila berkas ini memang sudah dinormalkan
        # dengan penormal yang sama — kalau tidak, nilainya pasti 0 dan hanya
        # menambah kebisingan.
        if getattr(st, "prenorm", "") and st.prenorm != getattr(chosen, "prenorm", ""):
            continue
        scored.append(eng.score_headers(headers, st))
    scored.sort(key=lambda r: (-r["score"], -r["mapped_columns"]))
    mine = next((s for s in scored if s["source_type"] == chosen.key), None)
    best = scored[0] if scored else None
    plat = eng.detect_platform(headers)
    mismatch = None
    if mine and best and best["source_type"] != chosen.key:
        # Ambang: jenis lain menang JAUH (kolom wajibnya lengkap sementara pilihan
        # staf tidak, atau cakupan kolomnya dua kali lebih besar).
        if (best["required_cover"] >= 0.99 and mine["required_cover"] < 0.99) or \
           (best["score"] >= mine["score"] + 0.25):
            mismatch = {
                "chosen": chosen.key, "chosen_label": chosen.label,
                "chosen_mapped": mine["mapped_columns"], "chosen_score": mine["score"],
                "chosen_missing": mine["required_missing"],
                "suggested": best["source_type"], "suggested_label": best["label"],
                "suggested_mapped": best["mapped_columns"], "suggested_score": best["score"],
                "message": (
                    f"Anda memilih \u201c{chosen.label}\u201d, tetapi "
                    f"{best['mapped_columns']} dari {best['total_columns']} kolom berkas ini "
                    f"cocok dengan \u201c{best['label']}\u201d — sedangkan pilihan Anda hanya "
                    f"cocok {mine['mapped_columns']} kolom"
                    + (f" dan kolom wajibnya belum lengkap ({', '.join(mine['required_missing'][:3])})"
                       if mine["required_missing"] else "")
                    + ". Periksa dulu sebelum menyimpan."),
            }
    plat_mismatch = ""
    if plat.get("platform") and acc_platform:
        if not _platform_matches(acc_platform, plat["platform"]):
            plat_mismatch = (
                f"Sidik kolom berkas ini menunjuk platform {plat['platform'].upper()} "
                f"(mis. kolom: {', '.join(plat.get('evidence') or [])}), sedangkan toko "
                f"tujuan berplatform {str(acc_platform).upper()}. Pastikan tokonya benar.")
    return {
        "platform_detected": plat.get("platform") or "",
        "platform_confidence": plat.get("confidence") or 0.0,
        "platform_evidence": plat.get("evidence") or [],
        "platform_mismatch": plat_mismatch,
        "chosen": mine, "best": best, "ranking": scored[:5],
        "type_mismatch": mismatch,
    }


def _summary(rows: List[dict]) -> dict:
    return {
        "valid": sum(1 for r in rows if r["status"] == "valid"),
        "warning": sum(1 for r in rows if r["status"] == "warning"),
        "error": sum(1 for r in rows if r["status"] == "error"),
        "total": len(rows),
    }


def _commit_message(st: SourceType, inserted: int, updated: int, rejected: int) -> str:
    """F3.D — kalimat hasil impor yang MENYEBUT arti angkanya.

    Pesan lama selalu berbunyi ``"{inserted} baris masuk ke {label}"``. Untuk
    jenis ``update_only`` (Ekspor B & C) nilai itu **selalu 0 secara sengaja** —
    jenis ini tidak pernah melahirkan pesanan. Staf yang membaca "0 baris masuk"
    menyimpulkan impornya gagal, lalu mengunggah ulang Ekspor A; dan justru
    pengulangan itulah yang mengembalikan pesanan yang sudah dikirim ke daftar
    "perlu dikirim". Kalimat di bawah menutup salah-baca itu di sumbernya.
    """
    if not st.update_only:
        # SESI #38 — pembaruan TIDAK BOLEH hilang dari kalimat hasil. Ekspor iklan
        # & KPI platform yang diunggah ulang menghasilkan `inserted=0` dengan
        # `updated=4`; kalimat lama berbunyi "0 baris masuk" sehingga staf
        # menyimpulkan impornya gagal dan mengunggahnya lagi — padahal 4 baris
        # data lama BARU SAJA ditimpa.
        parts = [f"{inserted} baris masuk ke {st.label}."]
        if updated:
            parts.append(f"{updated} baris yang sudah ada DIPERBARUI (nilai lamanya "
                         "ditimpa) — tekan \u201cBatalkan impor\u201d bila keliru.")
        if rejected:
            parts.append(f"{rejected} baris ditolak — lihat rinciannya di tabel di bawah.")
        parts.append(f"Lihat di menu {st.module_hint}.")
        return " ".join(parts)
    parts = [f"{updated} pesanan diperbarui dari {st.label}."]
    parts.append("Jenis ini tidak pernah membuat pesanan baru, jadi "
                 "\u201cBaris masuk 0\u201d memang hasil yang benar.")
    if rejected:
        parts.append(f"{rejected} baris ditolak \u2014 nomor pesanannya belum pernah "
                     "diimpor, atau statusnya mundur tanpa bukti batal/retur. "
                     "Lihat rinciannya di tabel di bawah.")
    parts.append(f"Periksa hasilnya di menu {st.module_hint}.")
    return " ".join(parts)



async def _load_session(db, session_id: str) -> dict:
    s = await db[SESSIONS].find_one({"id": session_id})
    if not s:
        raise HTTPException(404, "Sesi impor tidak ditemukan")
    return s


def _reparse(session: dict) -> List[dict]:
    path = session.get("file_path")
    raw = _read_session_file(path)
    if raw is None:
        raise HTTPException(410, "Berkas sesi ini sudah tidak ada di server. "
                                "Unggah ulang berkasnya.")
    # F7.2 — jenis impor ber-`prenorm` HARUS dibaca lewat penormal yang sama seperti
    # saat upload. Kalau tidak, pratinjau (600 baris) dan commit (0 baris) berbeda.
    st_pre = None
    try:
        st_pre = get_source_type(session.get("source_type") or "")
    except Exception as e:  # noqa: BLE001
        logger.debug("jenis impor sesi %s tidak dikenali: %s", session.get("id"), e)
    _, rows = eng.parse_table(raw, session.get("filename") or "data.csv", st_pre)
    # F1 — baris keterangan kolom harus dilewati di SEMUA pemakai (pratinjau,
    # commit, unduh galat). Kalau hanya di `upload`, commit akan menghitung
    # 602 baris sementara pratinjau 601 — layar yang membantah dirinya sendiri.
    try:
        st = get_source_type(session.get("source_type") or "")
        rows, _n = eng.strip_description_rows(rows, session.get("mapping") or [], st)
    except Exception as e:  # noqa: BLE001
        logger.debug("strip_description_rows dilewati untuk sesi %s: %s",
                     session.get("id"), e)
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# SESI: baca · ubah pemetaan · pratinjau
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/formats")
async def list_formats(request: Request, source_type: Optional[str] = Query(None)):
    """Susunan kolom yang SUDAH DIINGAT sistem (“Ingat Pemetaan Saya”).

    Ingatan ini yang membuat impor rutin harian langsung siap tanpa memetakan
    ulang. Karena itu ia harus bisa DILIHAT dan DIHAPUS: ingatan yang salah
    mengulang kesalahan yang sama setiap hari sambil tampak otomatis benar.
    """
    await require_auth(request)
    db = get_db()
    q: Dict[str, Any] = {}
    if source_type:
        get_source_type(source_type)          # 404 kalau jenisnya ngawur
        q["source_type"] = source_type
    docs = await db[FORMATS].find(q, {"_id": 0}).sort("last_used_at", -1).to_list(200)
    out = []
    for d in docs:
        try:
            label = get_source_type(d.get("source_type")).label
        except HTTPException:
            label = d.get("source_type") or "(jenis sudah tidak ada)"
        mapped = [m for m in (d.get("mapping") or []) if m.get("field")]
        out.append({
            "fingerprint": d.get("fingerprint"),
            "source_type": d.get("source_type"),
            "source_label": label,
            "platform": d.get("platform") or "",
            "columns": len(d.get("headers") or []),
            "mapped_columns": len(mapped),
            "headers_preview": (d.get("headers") or [])[:8],
            "use_count": int(d.get("use_count") or 0),
            "last_used_at": _ser(d.get("last_used_at")),
            "last_used_by": d.get("last_used_by") or "",
            "created_at": _ser(d.get("created_at")),
            "created_by": d.get("created_by") or "",
        })
    return {"ok": True, "formats": out, "total": len(out),
            "note": ("Pemetaan diingat dari sidik susunan kolom berkas. Satu berkas "
                     "dengan susunan kolom berbeda tidak akan memakai ingatan ini — "
                     "tidak ada tebakan diam-diam.")}


@router.delete("/formats/{fingerprint}")
async def forget_format(fingerprint: str, request: Request,
                        source_type: str = Query(...)):
    """LUPAKAN satu susunan kolom yang diingat.

    Tanpa jalan ini, satu kesalahan pemetaan yang pernah di-commit akan terpasang
    otomatis pada setiap impor berikutnya dan **tidak ada cara membatalkannya dari
    aplikasi** — staf hanya bisa memperbaikinya manual setiap hari, atau (lebih
    sering) tidak sadar sama sekali.
    """
    user = await require_auth(request)
    db = get_db()
    st = get_source_type(source_type)
    res = await db[FORMATS].delete_one({"source_type": st.key,
                                        "fingerprint": fingerprint})
    if not res.deleted_count:
        raise HTTPException(404, "Susunan kolom ini tidak ada di ingatan sistem "
                                 "(mungkin sudah dilupakan sebelumnya).")
    await log_activity(user.get("id", ""), user.get("name", ""),
                       f"Lupakan pemetaan kolom tersimpan untuk {st.label}",
                       "marketing-data-import", fingerprint)
    return {"ok": True,
            "message": (f"Pemetaan tersimpan untuk susunan kolom ini DILUPAKAN. "
                        f"Impor {st.label} berikutnya akan dipetakan ulang oleh "
                        "mesin dan meminta konfirmasi Anda lagi.")}


@router.get("/sessions")
async def list_sessions(request: Request,
                        status: Optional[str] = Query(None),
                        source_type: Optional[str] = Query(None),
                        account_id: Optional[str] = Query(None),
                        page: int = Query(1, ge=1),
                        page_size: int = Query(20, ge=1, le=100)):
    user = await require_auth(request)
    db = get_db()
    # F6 (sesi #9) — RIWAYAT IMPOR juga berlingkup toko. Ini bukan sekadar daftar:
    # dari riwayat, staf bisa membuka rincian baris, mengunduh berkas galat, dan
    # menekan "Batalkan & pulihkan" — jadi riwayat toko orang lain = jalan pintas
    # mengubah data toko orang lain.
    q: Dict[str, Any] = await scope.scope_filter(db, user, None)
    if status:
        q["status"] = status
    if source_type:
        q["source_type"] = source_type
    if account_id:
        q["account_id"] = account_id
    total = await db[SESSIONS].count_documents(q)
    docs = await db[SESSIONS].find(q, {"_id": 0, "mapping": 0}).sort(
        "created_at", -1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    return {"ok": True, "sessions": _ser(docs),
            "pagination": {"total": total, "page": page, "page_size": page_size}}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request,
                      page: int = Query(1, ge=1),
                      page_size: int = Query(50, ge=1, le=500),
                      only: Optional[str] = Query(None, pattern="^(valid|warning|error)$")):
    await require_auth(request)
    db = get_db()
    s = await _load_session(db, session_id)
    st = get_source_type(s["source_type"])
    rows = _reparse(s)
    built = eng.build_rows(rows, s.get("mapping") or [], st, limit=eng.MAX_PREVIEW_ROWS)
    built = await _annotate_master_links(db, st, s, built)
    if only:
        built = [r for r in built if r["status"] == only]
    total = len(built)
    start = (page - 1) * page_size
    s.pop("_id", None)
    return {"ok": True, "session": _ser(s),
            "rows": _ser(built[start:start + page_size]),
            "summary": _summary(built),
            "pagination": {"total": total, "page": page, "page_size": page_size},
            "fields": [{"name": f.name, "label": f.label, "kind": f.kind,
                        "required": f.required, "choices": list(f.choices),
                        "note": f.note}
                       for f in st.input_fields]}


class MappingIn(BaseModel):
    mapping: List[dict]


@router.put("/sessions/{session_id}/mapping")
async def update_mapping(session_id: str, body: MappingIn, request: Request):
    """Pemetaan hasil koreksi manusia. Pratinjau dihitung ULANG dari berkas asli.

    F3 (2026-08-14) — **DASAR KEPUTUSAN TIDAK BOLEH HILANG.** Layar mengirim
    SELURUH pemetaan setiap kali satu kolom diubah. Versi lama menandai semuanya
    ``manual`` dan membuang ``candidates``, jadi begitu staf memperbaiki satu
    kolom, kolom lain kehilangan keterangan "pasti / sinonim / mirip" beserta
    usulannya — dan layar berubah dari "bisa diperiksa" menjadi "percaya saja".
    Itu berbahaya justru pada jenis impor yang pemetaannya BELUM terverifikasi
    (Ekspor B/C): di situ usulan mesin adalah satu-satunya bantuan yang dimiliki
    staf. Sekarang: ``method``/``score``/``candidates`` DIPERTAHANKAN untuk kolom
    yang pilihannya tidak berubah; hanya kolom yang benar-benar diubah manusia
    yang ditandai ``manual``.
    """
    await require_auth(request)
    db = get_db()
    s = await _load_session(db, session_id)
    if s.get("status") == "committed":
        raise HTTPException(400, "Sesi sudah di-commit; buat sesi baru untuk mengubah")
    st = get_source_type(s["source_type"])

    prev = {m.get("column"): m for m in (s.get("mapping") or [])}
    valid_fields = {f.name for f in st.input_fields}
    cleaned: List[dict] = []
    used_fields: set = set()
    for m in body.mapping:
        col = m.get("column")
        if col is None:
            continue
        fld = m.get("field") or None
        if fld and fld not in valid_fields:
            raise HTTPException(400, f"Field '{fld}' tidak ada pada jenis data "
                                     f"'{st.label}'")
        if fld and fld in used_fields:
            raise HTTPException(400, f"Field '{fld}' dipetakan lebih dari satu kolom")
        if fld:
            used_fields.add(fld)
        old = prev.get(col) or {}
        unchanged = (old.get("field") or None) == fld
        if unchanged and old.get("method"):
            method = old["method"]
            score = old.get("score", 1.0 if fld else 0.0)
        else:
            method = "manual" if fld else "none"
            score = 1.0 if fld else 0.0
        cleaned.append({"column": col, "field": fld,
                        "field_label": (st.field(fld).label if fld else None),
                        "method": method, "score": score,
                        # Usulan mesin (exact/synonym/fuzzy/suggest) tetap dibawa
                        # supaya staf bisa mengganti pilihannya lagi nanti tanpa
                        # mengunggah ulang berkasnya.
                        "candidates": (m.get("candidates")
                                       or old.get("candidates") or []),
                        "note": old.get("note") or m.get("note") or ""})

    report = eng.mapping_report(cleaned, st)
    rows = _reparse(s)
    built = eng.build_rows(rows, cleaned, st)
    built = await _annotate_master_links(db, st, s, built)
    await db[SESSIONS].update_one({"id": session_id}, {"$set": {
        "mapping": cleaned, "mapping_report": report,
        "status": "ready" if report["ready"] else "mapping",
        "updated_at": _now()}})
    dup = await _annotate_existing(db, st, s, built)
    return {"ok": True, "mapping": cleaned, "mapping_report": report,
            "duplicates": dup,
            "summary": _summary(built), "preview": _ser(built[:50])}


@router.get("/sessions/{session_id}/errors.csv")
async def download_errors(session_id: str, request: Request):
    """Laporan baris bermasalah — supaya staf memperbaiki di file aslinya."""
    await require_auth(request)
    db = get_db()
    s = await _load_session(db, session_id)
    st = get_source_type(s["source_type"])
    built = eng.build_rows(_reparse(s), s.get("mapping") or [], st)
    bad = [r for r in built if r["status"] != "valid"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["baris_ke", "status", "masalah"] + (s.get("headers") or []))
    for r in bad:
        w.writerow([r["row_id"] + 2, r["status"],
                    " | ".join(r["errors"] + r["warnings"])]
                   + [r["original"].get(h, "") for h in (s.get("headers") or [])])
    data = buf.getvalue().encode("utf-8-sig")
    return StreamingResponse(io.BytesIO(data), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="masalah-impor-{session_id[:8]}.csv"'})


# ═══════════════════════════════════════════════════════════════════════════════
# AI OPSIONAL — hanya MENGUSULKAN pemetaan yang belum pasti
# ═══════════════════════════════════════════════════════════════════════════════
@router.post("/sessions/{session_id}/ai-assist")
async def ai_assist(session_id: str, request: Request):
    """Usulan pemetaan dari AI untuk kolom yang BELUM terpetakan.

    Sengaja tidak pernah menimpa hasil `exact`/`synonym`/`manual`: kalau AI boleh
    menimpa yang sudah pasti, satu jawaban model yang berubah cukup untuk
    memindahkan kolom uang ke kolom lain tanpa ada yang sadar.
    """
    await require_auth(request)
    db = get_db()
    s = await _load_session(db, session_id)
    st = get_source_type(s["source_type"])
    mapping = s.get("mapping") or []
    unmapped = [m["column"] for m in mapping
                if not m.get("field") or m.get("method") in ("suggest", "none")]
    if not unmapped:
        return {"ok": True, "suggestion": [], "message": "Semua kolom sudah terpetakan"}

    key = os.environ.get("EMERGENT_LLM_KEY", "")
    if not key:
        raise HTTPException(503, "Bantuan AI tidak tersedia (EMERGENT_LLM_KEY belum "
                                 "diatur). Pemetaan manual tetap bisa dipakai.")
    try:
        from ai_llm import LlmChat, UserMessage
        fields_txt = "\n".join(
            f"- {f.name} :: {f.label} ({f.kind})" +
            (f" pilihan: {', '.join(f.choices)}" if f.choices else "")
            for f in st.input_fields)
        sample_rows = eng.build_rows(_reparse(s), mapping, st, limit=3)
        prompt = (
            f"Petakan nama kolom berkas ke field sistem untuk jenis data '{st.label}'.\n\n"
            f"FIELD SISTEM:\n{fields_txt}\n\n"
            f"KOLOM YANG BELUM TERPETAKAN: {json.dumps(unmapped, ensure_ascii=False)}\n\n"
            f"CONTOH BARIS: {json.dumps([r['original'] for r in sample_rows], ensure_ascii=False)[:1500]}\n\n"
            "Jawab HANYA JSON array: [{\"column\":\"...\",\"field\":\"nama_field_sistem_atau_null\","
            "\"confidence\":0.0-1.0,\"reason\":\"alasan singkat\"}]"
        )
        chat = LlmChat(api_key=key, session_id=f"import-map-{session_id}",
                       system_message="Kamu pemeta kolom berkas impor. Jawab JSON saja.")
        chat.with_model("openai", "gpt-4o-mini")
        reply = await chat.send_message(UserMessage(text=prompt))
        txt = (reply or "").strip()
        if txt.startswith("```"):
            txt = txt.split("```")[1]
            txt = txt[4:] if txt.lower().startswith("json") else txt
        suggestion = json.loads(txt)
    except Exception as e:
        logger.warning("ai_assist gagal untuk sesi %s: %s", session_id, e)
        raise HTTPException(502, f"Bantuan AI gagal: {e}. Pemetaan manual tetap "
                                 f"bisa dipakai.") from None

    valid = {f.name for f in st.input_fields}
    taken = {m["field"] for m in mapping if m.get("field")
             and m.get("method") not in ("suggest", "none")}
    out = []
    for item in suggestion if isinstance(suggestion, list) else []:
        col, fld = item.get("column"), item.get("field")
        if col not in unmapped:
            continue
        if fld and (fld not in valid or fld in taken):
            fld = None
        out.append({"column": col, "field": fld,
                    "field_label": (st.field(fld).label if fld else None),
                    "confidence": item.get("confidence"),
                    "reason": item.get("reason")})
    await db[SESSIONS].update_one({"id": session_id}, {"$set": {
        "ai_used": True, "ai_suggestion": out, "updated_at": _now()}})
    return {"ok": True, "suggestion": out,
            "message": "Usulan AI — terapkan hanya yang Anda setujui"}


# ═══════════════════════════════════════════════════════════════════════════════
# COMMIT & ROLLBACK
# ═══════════════════════════════════════════════════════════════════════════════
async def _reference_index(db, st: SourceType, session: dict) -> dict:
    """Indeks master untuk menautkan baris impor ke data yang sudah ada."""
    idx: Dict[str, Any] = {}
    aid = session.get("account_id")
    if st.key in ("orders", "samples", "product_launches", "returns",
                  "reviews", "complaints", "live_session_products", "marketplace_orders"):
        cat_ids = [c["id"] for c in await db.marketing_catalogs.find(
            {"account_id": aid}, {"_id": 0, "id": 1}).to_list(200)]
        items = await db.marketing_catalog_items.find(
            {"catalog_id": {"$in": cat_ids}} if cat_ids else {"catalog_id": "__none__"},
            {"_id": 0, "id": 1, "sku": 1, "name": 1, "hpp": 1, "harga_jual": 1,
             "price": 1, "fg_material_id": 1, "category": 1,
             "platform_sku_ids": 1, "variant_id": 1, "model_id": 1}).to_list(5000)
        idx["items_by_sku"] = {scope.norm(i.get("sku")): i for i in items if i.get("sku")}
        idx["items_by_name"] = {scope.norm(i.get("name")): i for i in items if i.get("name")}
        # F1 — SSOT §4.3: pemetaan SKU platform → item katalog (hasil layar Pemetaan SKU)
        by_psku: Dict[str, Any] = {}
        for i in items:
            for psid in (i.get("platform_sku_ids") or []):
                if psid:
                    by_psku[str(psid).strip()] = i
        idx["items_by_platform_sku"] = by_psku
    if st.key in ("returns", "reviews", "complaints"):
        orders = await db.marketing_orders.find(
            {"account_id": aid}, {"_id": 0, "id": 1, "order_id": 1}).to_list(20000)
        idx["order_ids"] = {o.get("order_id"): o.get("id") for o in orders if o.get("order_id")}
    if st.key == "marketplace_orders":
        # Atribusi kreator afiliasi: `Creator Handle` → master kreator.
        creators = await db[scope.CREATORS].find(
            {}, {"_id": 0, "id": 1, "name": 1, "platforms": 1, "creator_code": 1}).to_list(2000)
        cmap: Dict[str, Any] = {}
        for c in creators:
            for _plat, handle in (c.get("platforms") or {}).items():
                if handle:
                    cmap[scope.norm(handle)] = c
            if c.get("creator_code"):
                cmap.setdefault(scope.norm(c["creator_code"]), c)
        idx["creators_by_handle"] = cmap
    if st.key == "content_performance":
        # F7.2 — kolom "Kode/Username Kreator" ditautkan ke master kreator lewat
        # kode ATAU username platform, karena ekspor platform tidak pernah memuat
        # id internal. Tidak cocok ⇒ baris tetap masuk dengan peringatan (angka
        # konten tidak boleh hilang hanya karena pemiliknya belum terdaftar).
        creators = await db[scope.CREATORS].find(
            {}, {"_id": 0, "id": 1, "name": 1, "platforms": 1,
                 "creator_code": 1}).to_list(2000)
        cmap: Dict[str, Any] = {}
        for c in creators:
            for key in (c.get("creator_code"), c.get("name")):
                if key:
                    cmap.setdefault(scope.norm(key), c)
            for _plat, handle in (c.get("platforms") or {}).items():
                if handle:
                    cmap.setdefault(scope.norm(handle), c)
        idx["creators_by_code"] = cmap
    return idx


async def _annotate_derived_daily(db, st: SourceType, session: dict,
                                  built: List[dict]) -> List[dict]:
    """PRATINJAU: tandai baris `sales_daily` yang tanggalnya OMZET TURUNAN (F2).

    Kenapa di pratinjau dan bukan hanya saat commit: kalau peringatannya baru
    muncul sesudah tombol simpan ditekan, staf sudah percaya bahwa angka di
    berkasnya yang akan dipakai. Di sini dia melihat lebih dulu bahwa kolom omzet
    & jumlah pesanan akan diabaikan (karena diturunkan dari pesanan), sementara
    kolom lain tetap masuk — beserta jalan keluarnya (Override SPV).
    """
    if st.key != "sales_daily" or not built or not session.get("account_id"):
        return built
    keys = []
    for r in built:
        d = r.get("data") or {}
        date = _shape.norm_date(d.get("date"))
        rtype = (d.get("revenue_type") or "total").strip().lower()
        if date:
            keys.append((date, rtype))
    if not keys:
        return built
    docs = await db[_shape_daily_collection()].find(
        {"account_id": session["account_id"],
         "date": {"$in": sorted({k[0] for k in keys})}},
        {"_id": 0, "date": 1, "revenue_type": 1, "source": 1, "locked_source": 1},
    ).to_list(1000)
    locked = {(d.get("date"), d.get("revenue_type")) for d in docs if _shape.is_derived(d)}
    if not locked:
        return built
    for r in built:
        d = r.get("data") or {}
        date = _shape.norm_date(d.get("date"))
        rtype = (d.get("revenue_type") or "total").strip().lower()
        if (date, rtype) in locked:
            r["warnings"] = list(r.get("warnings") or []) + [
                _shape.derived_lock_message(date)]
            if r.get("status") == "valid":
                r["status"] = "warning"
    return built


def _shape_daily_collection() -> str:
    return "marketing_sales_data"


# Kunci dedupe yang nilainya DISTEMPEL dari konteks toko saat commit
# (`core.marketing_account_scope.stamp_account`) → nama field padanannya di sesi.
_ACCOUNT_STAMPED = {"account_id": "account_id", "platform": "account_platform",
                    "account_code": "account_code", "account_name": "account_name"}


async def _annotate_existing(db, st: SourceType, session: dict,
                            built: List[dict]) -> dict:
    """Tandai baris yang **SUDAH ADA** di sistem — di PRATINJAU, bukan sesudah commit.

    Pertanyaan nyata staf: *"saya sudah impor tanggal 1–7, sekarang saya impor
    5–12; tanggal 5–7 dobel, apakah sistem tahu?"* Sistem memang tahu — deteksinya
    **per BARIS** lewat kunci dedupe (mis. ``account_id + platform + order_id``),
    bukan per rentang tanggal, jadi rentang yang beririsan tidak membuat baris
    ganda. Tetapi sebelum ini jawabannya baru muncul **sesudah** tombol simpan
    ditekan (di catatan hasil), padahal justru SEBELUM itu staf harus memilih
    "Lewati" atau "Perbarui yang lama". Memilih tanpa tahu berapa baris yang
    terdampak = memilih dengan mata tertutup.

    Memakai KUNCI DEDUPE YANG SAMA dengan commit (``st.dedupe``) supaya angka di
    pratinjau tidak bisa berbeda dari kenyataan.
    """
    out = {"checked": False, "existing": 0, "new": 0, "dedupe": list(st.dedupe or ()),
           "file_date_from": "", "file_date_to": "",
           "overlap_date_from": "", "overlap_date_to": "", "sample": []}
    if not st.dedupe:
        return out
    out["checked"] = True
    dates, overlap_dates = [], []
    for r in built:
        if r.get("status") == "error":
            continue
        d = r.get("data") or {}
        key = {}
        ok = True
        for k in st.dedupe:
            # Field yang DISTEMPEL dari konteks toko (`scope.stamp_account`) baru
            # ada saat commit, jadi di pratinjau nilainya diambil dari SESI —
            # kalau tidak, kunci dedupe selalu gagal terbentuk dan setiap baris
            # dilaporkan "baru" (justru kesalahan yang paling menyesatkan di sini).
            if k in _ACCOUNT_STAMPED:
                v = session.get(_ACCOUNT_STAMPED[k])
            else:
                v = d.get(k)
            if v in (None, ""):
                ok = False
                break
            key[k] = v
        raw = d.get("date") or d.get("order_date") or d.get("session_date")
        day = (raw.strftime("%Y-%m-%d") if isinstance(raw, datetime)
               else str(raw or "")[:10])
        if day:
            dates.append(day)
        if not ok:
            out["new"] += 1
            continue
        hit = await db[st.collection].find_one(key, {"_id": 0, "id": 1, "status": 1})
        if hit:
            out["existing"] += 1
            r["exists"] = True
            if day:
                overlap_dates.append(day)
            if len(out["sample"]) < 5:
                out["sample"].append({
                    "row": r["row_id"] + 2,
                    "ref": str(d.get("order_id") or d.get("published_url")
                              or d.get("date") or ""),
                    "status_now": hit.get("status") or "",
                })
        else:
            out["new"] += 1
    if dates:
        out["file_date_from"], out["file_date_to"] = min(dates), max(dates)
    if overlap_dates:
        out["overlap_date_from"] = min(overlap_dates)
        out["overlap_date_to"] = max(overlap_dates)
    return out


async def _annotate_master_links(db, st: SourceType, session: dict,
                                 built: List[dict]) -> List[dict]:
    """Tandai baris yang TIDAK BISA ditautkan ke master sebagai galat di PRATINJAU.

    Kalau hal ini hanya diperiksa saat commit, pratinjau akan menampilkan "10
    baris valid" lalu commit melaporkan "10 ditolak" — layar yang membantah
    dirinya sendiri. Pemeriksaannya butuh basis data, karena itu dilakukan di
    sini dan bukan di `marketing_import_engine` (yang sengaja tanpa DB).
    """
    if st.key != "live_session_products" or not built:
        return await _annotate_derived_daily(db, st, session, built)
    refidx = await _reference_index(db, st, session)
    by_sku = refidx.get("items_by_sku", {})
    by_name = refidx.get("items_by_name", {})
    for r in built:
        d = r.get("data") or {}
        found = (by_sku.get(scope.norm(d.get("sku")))
                 or by_name.get(scope.norm(d.get("product_name"))))
        if not found:
            r["errors"] = list(r.get("errors") or []) + [
                f"SKU/produk '{d.get('sku') or d.get('product_name') or '(kosong)'}' "
                f"tidak ada di katalog toko ini — tambahkan dulu di Manajemen Katalog"]
            r["status"] = "error"
        elif (d.get("units_sold") or 0) == 0 and (d.get("revenue") or 0) > 0:
            r["errors"] = list(r.get("errors") or []) + [
                "omzet terisi tapi unit terjual 0 — perbaiki salah satunya"]
            r["status"] = "error"
    return built


def _finish(st: SourceType, data: dict, session: dict, refidx: dict,
            account: Optional[dict] = None) -> tuple:
    """Lengkapi satu dokumen: nilai turunan + tautan master.

    → ``(doc, warnings)``. **`doc = None` berarti baris ini DITOLAK** dan
    `warnings` berisi alasannya. Pengembalian None dipakai untuk baris yang tidak
    bisa ditautkan ke master: menyimpannya tanpa tautan akan melahirkan baris yang
    "berhasil diimpor" tetapi tidak pernah muncul di laporan mana pun.

    ``account`` diperlukan sejak F0.2 untuk jenis `sales_daily`: bentuk dokumen
    rekap harian dibuat oleh **satu** pembuat kanonik
    (`core.marketing_sales_shape.build_daily_doc`) yang butuh `account_code`,
    `platform`, dan `revenue_basis` toko.
    """
    warn: List[str] = []
    d = dict(data)

    def _num(k, default=0.0):
        v = d.get(k)
        return float(v) if isinstance(v, (int, float)) else default

    if st.key == "sales_daily":
        # F0.2/D01 — DULU cabang ini hanya menghitung `aov` dan menyimpan dokumen
        # RATA (tanpa `metrics{}`). Untuk 1 baris Rp 12.500.000 hasilnya:
        # Target Rp 0 · Dashboard HTTP 500 · Health Score 15 (vs 89 lewat entri
        # manual) — angka yang sama, empat jawaban. Sekarang bentuknya IDENTIK
        # dengan entri manual karena keduanya memakai pembuat yang sama.
        acc = account or {"id": session.get("account_id")}
        rtype = (d.get("revenue_type") or "total").strip().lower()
        if rtype not in _shape.REVENUE_TYPES:
            return None, [f"Jenis Revenue '{d.get('revenue_type')}' tidak dikenali "
                          f"(pilih: {', '.join(_shape.REVENUE_TYPES)})"]
        doc = _shape.build_daily_doc(
            account=acc,
            date=d.get("date"),
            revenue_type=rtype,
            flat={k: v for k, v in d.items()
                  if k not in ("account_id", "date", "revenue_type")},
            source=_shape.SOURCE_IMPORT,
        )
        return doc, warn

    elif st.key == "orders":
        item = None
        if d.get("sku_id"):
            item = refidx.get("items_by_sku", {}).get(scope.norm(d["sku_id"]))
        if item is None and d.get("product_name"):
            item = refidx.get("items_by_name", {}).get(scope.norm(d["product_name"]))
        if item:
            d["catalog_item_id"] = item["id"]
            d["fg_material_id"] = item.get("fg_material_id")
            d.setdefault("product_name", item.get("name"))
            d["master_link_source"] = "import_sku_match"
        else:
            d["catalog_item_id"] = None
            d["master_link_source"] = "unlinked"
            warn.append("SKU/produk tidak ada di katalog toko — order tersimpan "
                        "tapi belum tertaut master (alokasi stok harus manual)")
        qty = _num("quantity", 1) or 1
        price = _num("price_final") or _num("price_original")
        if not d.get("total_payment"):
            d["total_payment"] = round(price * qty + _num("shipping_cost")
                                       - _num("discount_seller"), 2)
        if not d.get("revenue"):
            d["revenue"] = round(price * qty - _num("discount_seller"), 2)
        d.setdefault("status", "new")
        # Impor TIDAK memesan stok: order lama sudah dikirim, dan memesan stok untuk
        # order lama akan mengunci barang yang sebenarnya sudah keluar.
        d["fulfillment_status"], _fs_reason = _fstat.initial_status(d)
        d["fulfillment_status_reason"] = _fs_reason
        d["allocations"] = []
        d["items"] = []
        if d.get("status") in ("new", "paid", "packed"):
            warn.append("Status masih belum terkirim — stok TIDAK dipesan oleh impor; "
                        "alokasikan di Fulfillment bila memang perlu dikirim")

    elif st.key == "marketplace_orders":
        # ── F1 — 1 DOKUMEN = 1 PESANAN (items[]) ─────────────────────────────
        # Semua uang produk dijumlah dari items[]; uang per pesanan (order_amount,
        # ongkir, biaya) dipakai APA ADANYA dari baris pertama (sudah dijaga mesin).
        items_in = list(d.pop("items", []) or [])
        raw_ids = d.pop("raw_row_ids", []) or []
        if not items_in:
            return None, ["Pesanan tanpa baris SKU — tidak ada yang bisa disimpan"]

        by_psku = refidx.get("items_by_platform_sku", {})
        by_sku = refidx.get("items_by_sku", {})
        by_name = refidx.get("items_by_name", {})

        items_out: List[dict] = []
        n_unlinked = 0
        rev_product = rev_gross = disc_seller = disc_platform = 0.0
        qty_total = qty_returned_total = 0
        any_preorder = False
        for it in items_in:
            it = dict(it)
            psid = str(it.get("platform_sku_id") or "").strip()
            master = None
            link = "unlinked"
            if psid and psid in by_psku:
                master, link = by_psku[psid], "sku_map"
            if master is None and it.get("seller_sku"):
                master = by_sku.get(scope.norm(it["seller_sku"]))
                link = "sku_exact" if master else link
            if master is None and psid:
                master = by_sku.get(scope.norm(psid))
                link = "sku_exact" if master else link
            if master is None and it.get("product_name_raw"):
                master = by_name.get(scope.norm(it["product_name_raw"]))
                link = "name_match" if master else link
            if master:
                it["catalog_item_id"] = master["id"]
                it["fg_material_id"] = master.get("fg_material_id")
                it["variant_id"] = master.get("variant_id")
                it["model_id"] = master.get("model_id")
                it["hpp_snapshot"] = master.get("hpp")
            else:
                it["catalog_item_id"] = None
                it["fg_material_id"] = None
                it["hpp_snapshot"] = None
                n_unlinked += 1
            it["master_link_source"] = link
            rev_product += float(it.get("sku_subtotal_after_discount") or 0)
            rev_gross += float(it.get("sku_subtotal_before_discount") or 0)
            disc_seller += float(it.get("sku_seller_discount") or 0)
            disc_platform += float(it.get("sku_platform_discount") or 0)
            qty_total += int(it.get("quantity") or 0)
            qty_returned_total += int(it.get("qty_returned") or 0)
            any_preorder = any_preorder or it.get("is_preorder") is True
            items_out.append(it)

        d["items"] = items_out
        d["items_count"] = len(items_out)
        d["raw_row_ids"] = raw_ids
        d["revenue_product"] = round(rev_product, 2)
        d["revenue_gross"] = round(rev_gross, 2)
        d["seller_discount_total"] = round(disc_seller, 2)
        d["platform_discount_total"] = round(disc_platform, 2)
        d["quantity"] = qty_total
        d["qty_returned_total"] = qty_returned_total
        d["is_preorder"] = any_preorder
        # kompatibilitas pembaca lama (41 pembaca memakai dua nama ini)
        d["revenue"] = d["revenue_product"]
        d["total_payment"] = round(float(d.get("order_amount") or 0), 2)
        # Komisi platform TIDAK ADA di ekspor ini — dilarang dikarang. Angka bersih
        # hanya boleh datang dari impor Pencairan/Settlement (F9).
        d["platform_fee"] = None
        d["fee_known"] = False
        d["revenue_label"] = "sebelum potongan platform"
        d.setdefault("status", "new")
        d.setdefault("courier", "lainnya")
        d["fulfillment_status"], _fs_reason = _fstat.initial_status(d)
        d["fulfillment_status_reason"] = _fs_reason
        d["stock_reserved"] = False
        d["allocations"] = []

        # atribusi kreator afiliasi
        handle = str(d.get("creator_handle") or "").strip()
        if handle:
            cr = (refidx.get("creators_by_handle") or {}).get(scope.norm(handle))
            if cr:
                d["creator_id"] = cr["id"]
                d["creator_name"] = cr.get("name")
            else:
                d["creator_id"] = None
                warn.append(f"Kreator '{handle}' belum ada di master kreator — "
                            f"omzetnya tetap masuk, tapi laporan kreator belum bisa menautkannya")

        # gudang platform: dibandingkan dengan master toko (peringatan, bukan tolak)
        wh_file = str(d.get("warehouse_name_raw") or "").strip()
        wh_master = str((account or {}).get("platform_warehouse_name") or "").strip()
        if wh_file and wh_master and scope.norm(wh_file) != scope.norm(wh_master):
            warn.append(f"Nama gudang di berkas ('{wh_file}') berbeda dengan gudang platform "
                        f"di master toko ('{wh_master}') — pastikan berkasnya milik toko ini")

        if n_unlinked:
            warn.append(f"{n_unlinked} dari {len(items_out)} SKU belum tertaut item katalog — "
                        f"omzet TETAP masuk; lengkapi lewat layar 'Pemetaan SKU'")

    elif st.key == "ads":
        spend, clicks = _num("spend"), _num("clicks")
        imp, conv, rev = _num("impressions"), _num("conversions"), _num("revenue")
        d["ctr"] = round(clicks / imp * 100, 2) if imp else 0
        d["cpa"] = round(spend / conv, 2) if conv else 0
        d["roas"] = round(rev / spend, 2) if spend else 0
        d.setdefault("status", "active")

    elif st.key == "live_sessions":
        d["host_id"] = session.get("host_id")
        d["host_name"] = session.get("host_name")
        viewers = _num("total_viewers")
        inter = _num("likes") + _num("comments") + _num("shares")
        d["engagement_rate"] = round(inter / viewers * 100, 2) if viewers else 0
        d["conversion_rate"] = round(_num("orders") / viewers * 100, 2) if viewers else 0
        d.setdefault("status", "completed")
        note = d.pop("notes_text", None)
        d["notes"] = ([{"id": str(uuid.uuid4()), "text": note, "at": _now().isoformat()}]
                      if note else [])

    elif st.key == "livehost_shifts":
        d["host_id"] = session.get("host_id")
        d.setdefault("shift_type", "evening")
        d.setdefault("status", "scheduled")

    elif st.key == "live_session_products":
        # F18#3 — rincian produk WAJIB tertaut item katalog toko. Baris yang
        # SKU-nya tidak dikenal DITOLAK (doc=None), bukan disimpan dengan
        # `catalog_item_id: null`: rincian tanpa tautan master tidak bisa
        # dijumlahkan per produk, jadi menyimpannya hanya menambah baris yang
        # kelihatan berhasil tapi tidak pernah muncul di laporan.
        item = None
        if d.get("sku"):
            item = refidx.get("items_by_sku", {}).get(scope.norm(d["sku"]))
        if item is None and d.get("product_name"):
            item = refidx.get("items_by_name", {}).get(scope.norm(d["product_name"]))
        if item is None:
            return None, [f"SKU/produk '{d.get('sku') or d.get('product_name')}' "
                          f"tidak ada di katalog toko ini — tambahkan dulu di "
                          f"Manajemen Katalog, lalu impor ulang barisnya"]
        units = int(_num("units_sold"))
        revenue = round(_num("revenue"), 2)
        if units == 0 and revenue > 0:
            return None, ["omzet terisi tapi unit terjual 0 — perbaiki salah satunya"]
        hpp = float(item.get("hpp") or 0)
        d["catalog_item_id"] = item["id"]
        d["sku"] = item.get("sku", "")
        d["product_name"] = item.get("name", "")
        d["category"] = item.get("category", "")
        d["hpp"] = hpp
        d["harga_jual_master"] = float(item.get("harga_jual") or item.get("price") or 0)
        d["units_sold"] = units
        d["revenue"] = revenue
        d["orders"] = int(_num("orders"))
        d["price_avg"] = round(revenue / units, 2) if units else 0.0
        d["hpp_total"] = round(hpp * units, 2)
        d["gross_margin"] = round(revenue - hpp * units, 2)
        d["gross_margin_pct"] = (round((revenue - hpp * units) / revenue * 100, 2)
                                 if revenue else 0.0)
        d["session_id"] = session.get("live_session_id")
        d["session_date"] = session.get("live_session_date")
        d["session_title"] = session.get("live_session_title")
        d["host_id"] = session.get("host_id")
        d["host_name"] = session.get("host_name")

    elif st.key == "catalog_items":
        d["catalog_id"] = session.get("catalog_id")
        d.setdefault("is_active", True)
        d.setdefault("stock_quantity", 0)
        # kompatibilitas pembaca lama (F1–F9): `price` cermin dari `harga_jual`
        d["price"] = d.get("harga_jual") or 0
        d["original_price"] = d.get("harga_coret") or 0

    elif st.key == "samples":
        d["creator_id"] = session.get("creator_id")
        d["username"] = session.get("creator_username") or session.get("creator_name") or ""
        item = None
        if d.get("sku"):
            item = refidx.get("items_by_sku", {}).get(scope.norm(d["sku"]))
        if item is None and d.get("product"):
            item = refidx.get("items_by_name", {}).get(scope.norm(d["product"]))
        if item:
            d["catalog_item_id"] = item["id"]
            d.setdefault("sku", item.get("sku"))
            if not d.get("hpp"):
                d["hpp"] = item.get("hpp") or 0
                if not d["hpp"]:
                    warn.append("HPP item katalog masih 0 — isi HPP di katalog supaya "
                                "biaya sample tidak dilaporkan Rp 0")
        else:
            d["catalog_item_id"] = None
            warn.append("Produk tidak ditemukan di katalog toko — HPP dipakai apa "
                        "adanya dari berkas")
        d["total_hpp"] = round(_num("hpp") * _num("quantity", 1), 2)
        d.setdefault("shipment_status", "pending")
        d.setdefault("progress", "open")
        d["sample_type_label"] = ("Live Streaming" if d.get("sample_type") == "live"
                                  else "Video Review")

    elif st.key == "kol_creators":
        plats = {}
        for k, fld in (("tiktok", "tiktok_username"), ("instagram", "instagram_username"),
                       ("shopee", "shopee_username")):
            v = d.pop(fld, None)
            if v:
                plats[k] = v
        d["platforms"] = plats
        aid = session.get("account_id")
        d["assigned_account_ids"] = [aid] if aid else []
        d.setdefault("status", "active")
        d.setdefault("kpi_targets", {})

    elif st.key == "returns":
        # F15 — nama produk dari berkas ditautkan ke ITEM KATALOG bila cocok,
        # supaya laporan "produk paling banyak diretur" tidak pecah karena ejaan.
        _it = (refidx.get("items_by_sku", {}).get(scope.norm(d.get("sku")))
               or refidx.get("items_by_name", {}).get(scope.norm(d.get("product"))))
        if _it:
            d["catalog_item_id"] = _it["id"]
            d["sku"] = _it.get("sku", "")
            d["product"] = _it.get("name") or d.get("product")
        else:
            d["catalog_item_id"] = None
            if d.get("product"):
                warn.append(f"Produk '{d.get('product')}' tidak ada di katalog toko — "
                            "baris tersimpan tapi tidak tertaut produk")
        oid = d.get("order_id")
        found = refidx.get("order_ids", {}).get(oid)
        d["order_ref_id"] = found
        if oid and not found:
            warn.append(f"No. Pesanan '{oid}' tidak ada di order akun ini — retur "
                        f"tersimpan tapi tidak tertaut order")
        d.setdefault("status", "pending")
        d.setdefault("refund_type", "full_refund")
        if d.get("refund_type") == "full_refund" and not d.get("refund_amount"):
            d["refund_amount"] = _num("price")

    elif st.key == "reviews":
        _it = refidx.get("items_by_name", {}).get(scope.norm(d.get("product")))
        if _it:
            d["catalog_item_id"] = _it["id"]
            d["sku"] = _it.get("sku", "")
            d["product"] = _it.get("name") or d.get("product")
        else:
            d["catalog_item_id"] = None
            if d.get("product"):
                warn.append(f"Produk '{d.get('product')}' tidak ada di katalog toko — "
                            "baris tersimpan tapi tidak tertaut produk")
        oid = d.get("order_id")
        if oid:
            d["order_ref_id"] = refidx.get("order_ids", {}).get(oid)
        d.setdefault("status", "pending")
        d.setdefault("response_text", "")

    elif st.key == "complaints":
        _it = refidx.get("items_by_name", {}).get(scope.norm(d.get("product_name")))
        if _it:
            d["catalog_item_id"] = _it["id"]
            d["sku"] = _it.get("sku", "")
            d["product_name"] = _it.get("name") or d.get("product_name")
        else:
            d["catalog_item_id"] = None
        d.setdefault("severity", "medium")
        d.setdefault("status", "open")
        d.setdefault("notes", [])
        d.setdefault("orders", [])
        hours = {"critical": 12, "high": 24, "medium": 48, "low": 72}[d["severity"]]
        base = d.get("complaint_date") or _now()
        if isinstance(base, datetime):
            d["sla_due_at"] = base + timedelta(hours=hours)
        oid = d.get("order_id")
        if oid:
            d["order_ref_id"] = refidx.get("order_ids", {}).get(oid)

    elif st.key == "account_health":
        d.setdefault("notes", [])
        ses = _num("ses_score")
        d["status"] = ("healthy" if ses >= 80 else "warning" if ses >= 60
                       else "critical" if ses > 0 else "unknown")

    # ── F7.2 — KPI PLATFORM HARIAN (statistik toko & konten Live/Video) ───────
    elif st.key in ("shopee_shop_kpi", "shopee_content_kpi"):
        # Angka turunan DIHITUNG di sini supaya layar tidak pernah menghitung
        # ulang dengan rumus berbeda (penyebab klasik "dua layar, dua angka").
        gmv = _num("gmv_created")
        orders = _num("orders_created")
        visitors = _num("visitors")
        views = _num("views")
        d["platform"] = (account or {}).get("platform") or "shopee"
        d["aov"] = round(gmv / orders, 2) if orders > 0 else 0.0
        d["conversion_rate_calc"] = (round(orders / visitors * 100, 4)
                                     if visitors > 0 else 0.0)
        d["gmv_per_view"] = round(gmv / views, 2) if views > 0 else 0.0
        eng_sum = _num("likes") + _num("comments") + _num("shares")
        d["engagement"] = round(eng_sum, 2)
        d["engagement_rate"] = round(eng_sum / views * 100, 2) if views > 0 else 0.0
        # PAGAR KEJUJURAN: angka ini KPI platform, bukan omzet SSOT. Ditulis pada
        # dokumennya sendiri supaya siapa pun yang membacanya di database pun tahu.
        d["revenue_basis"] = "platform_kpi"
        d["is_platform_kpi"] = True
        d["not_sales_ssot_note"] = (
            "KPI platform (definisi Shopee: pesanan dibuat/siap dikirim/dibayar). "
            "Jangan dijumlah dengan omzet pesanan (marketing_sales_data / "
            "marketing_orders) — itu menghitung satu penjualan dua kali.")

    # ── F7.2 — LAPORAN IKLAN CPC SHOPEE ──────────────────────────────────────
    elif st.key == "shopee_ads_cpc":
        spend = _num("spend")
        clicks = _num("clicks")
        impr = _num("impressions")
        conv = _num("conversions")
        rev = _num("revenue")
        d["ctr"] = round(clicks / impr * 100, 2) if impr > 0 else 0.0
        d["cpa"] = round(spend / conv, 2) if conv > 0 else 0.0
        d["cpc"] = round(spend / clicks, 2) if clicks > 0 else 0.0
        d["roas"] = round(rev / spend, 2) if spend > 0 else 0.0
        # Hari yang tercakup — dipakai layar untuk menampilkan biaya rata-rata/hari
        # TANPA menyimpan angka harian palsu (laporan ini memang per periode).
        try:
            _f = datetime.strptime(str(d.get("period_start"))[:10], "%Y-%m-%d")
            _t = datetime.strptime(str(d.get("period_end"))[:10], "%Y-%m-%d")
            days = (_t - _f).days + 1
        except Exception:  # noqa: BLE001 — periode sudah dijaga penormal
            days = 1
        d["period_days"] = max(1, days)
        d["spend_per_day_avg"] = round(spend / max(1, days), 2)
        d["campaign_id"] = d.get("product_code") or ""
        d.setdefault("status", "active")
        d["source_report"] = "shopee_ads_cpc"

    # ── F7.2 — KPI PER KONTEN (kunci link terbit) ────────────────────────────
    elif st.key == "content_performance":
        url = str(d.get("published_url") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return None, [f"Link terbit harus URL http/https — diterima: '{url[:60]}'"]
        kpi = {k: _num(k) for k in ("views", "likes", "comments", "shares", "saves",
                                    "watch_time_avg_sec", "ctr", "orders", "gmv")}
        for k in kpi:
            d.pop(k, None)
        views = kpi["views"]
        eng_sum = kpi["likes"] + kpi["comments"] + kpi["shares"]
        d["kpi"] = kpi
        d["kpi_derived"] = {
            "engagement": round(eng_sum, 2),
            "engagement_rate": round(eng_sum / views * 100, 2) if views > 0 else 0.0,
            "save_rate": round(kpi["saves"] / views * 100, 2) if views > 0 else 0.0,
            "cvr": round(kpi["orders"] / views * 100, 4) if views > 0 else 0.0,
            "gmv_per_view": round(kpi["gmv"] / views, 2) if views > 0 else 0.0,
            "aov": round(kpi["gmv"] / kpi["orders"], 2) if kpi["orders"] > 0 else 0.0,
        }
        d["kpi_source"] = "import"
        d["kpi_updated_at"] = _now()
        d["published_url"] = url
        d["status"] = "posted"
        d["published_at"] = str(d.get("date") or "")[:10]
        d["platform"] = (account or {}).get("platform") or ""
        d["account_name"] = (account or {}).get("account_name") or ""
        d.setdefault("content_type", "video_pendek")
        if not d.get("title"):
            d["title"] = f"Konten {url.rstrip('/').split('/')[-1][:40] or url[:40]}"
        code = str(d.pop("creator_code", "") or "").strip()
        if code:
            cr = refidx.get("creators_by_code", {}).get(scope.norm(code))
            if cr:
                d["creator_id"] = cr["id"]
                d["creator_name"] = cr.get("name", "")
            else:
                d["creator_id"] = None
                warn.append(f"Kreator '{code}' tidak ada di master kreator — KPI "
                            "tersimpan tanpa pemilik konten (scorecard kreator "
                            "tidak akan memuat baris ini)")
        elif session.get("creator_id"):
            d["creator_id"] = session["creator_id"]
            d["creator_name"] = session.get("creator_name", "")
    return d, warn


class CommitIn(BaseModel):
    on_duplicate: str = "skip"       # skip | update
    skip_warnings: bool = False      # True = baris ber-peringatan tidak di-commit


# ── F7.2 — jenis impor yang SELALU menyegarkan baris lama ─────────────────────
# KPI platform & KPI konten adalah SNAPSHOT: mengunggah ulang ekspor tanggal yang
# sama berarti "angka terbaru dari platform", bukan baris kedua. Kalau default
# 'skip' dipertahankan, koreksi angka platform (yang lazim: GMV H+1 berubah karena
# pesanan batal) tidak akan pernah masuk dan staf akan menganggap impornya gagal.
REFRESH_ON_DUPLICATE = ("shopee_shop_kpi", "shopee_content_kpi",
                        "shopee_ads_cpc", "content_performance")

# Field yang TIDAK boleh ditimpa impor KPI konten: konten sudah direncanakan staf
# (judul, tanggal rencana, jenis, pemilik). Impor hanya menempelkan ANGKA.
_CONTENT_KPI_PATCH = ("kpi", "kpi_derived", "kpi_source", "kpi_updated_at",
                      "published_url", "status", "platform_post_id")


def _update_payload(st: SourceType, doc: dict, existing: dict) -> dict:
    """Bagian dokumen yang boleh menimpa baris yang sudah ada.

    Untuk `content_performance`: hanya KPI + bukti terbit. Menimpa judul/tanggal/
    jenis konten dengan nilai turunan berkas akan MENGHAPUS rencana konten yang
    ditulis staf — kerusakan senyap yang baru terasa saat rapat mingguan.
    """
    if st.key != "content_performance":
        return doc
    out = {k: doc[k] for k in _CONTENT_KPI_PATCH if k in doc}
    if not existing.get("published_at") and doc.get("published_at"):
        out["published_at"] = doc["published_at"]
    if doc.get("creator_id") and not existing.get("creator_id"):
        out["creator_id"] = doc["creator_id"]
        out["creator_name"] = doc.get("creator_name", "")
    return out


class SkuMapIn(BaseModel):
    platform_sku_id: str
    catalog_item_id: str


# ══════════════════════════════════════════════════════════════════════════════
# FASE 4 (sesi #11) — PENGHALANG SELURUH COMMIT, DIPINDAH KE SATU TEMPAT
# ══════════════════════════════════════════════════════════════════════════════
# Tiga pemeriksaan di bawah ini membatalkan **seluruh** impor (bukan satu baris):
# periode iklan yang beririsan, omzet rincian sesi live yang melebihi omzet sesi,
# dan periode akuntansi yang sudah DITUTUP. Sebelumnya ketiganya ditulis di dalam
# `commit()`, sehingga staf baru mengetahuinya **sesudah** menekan "Simpan" —
# padahal semua bahannya sudah ada sejak pratinjau. Pratinjau yang mengatakan
# "600 baris siap" lalu commit yang menjawab 423 adalah layar yang membantah
# dirinya sendiri, dan yang dipercaya staf adalah yang pertama.
#
# Sekarang: SATU fungsi dipakai DUA pemanggil — `commit()` (yang menaikkan
# HTTPException persis seperti dulu) dan pratinjau `plan()` (yang menampilkannya
# sebagai panel merah + mematikan tombol Simpan). Menyalinnya akan melahirkan dua
# aturan yang bisa berbeda; satu-satunya cara pratinjau tidak bisa berbohong
# adalah memakai sumber yang sama.
async def _shop_evidence(db, st: SourceType, s: dict, built: List[dict],
                         account: Optional[dict]) -> tuple:
    """F12 — **BUKTI** bahwa berkas ini milik toko LAIN → ``(blockers, warnings)``.

    Kenapa ini ada, dan kenapa hanya "bukti" (bukan dugaan)
    ------------------------------------------------------
    Penjaga yang sudah ada hanya menutup dua kesalahan: berkas platform lain
    (`platform_guard`) dan gudang platform yang bukan milik toko tujuan
    (`shop_guard`) — dan keduanya HANYA ada pada `marketplace_orders`. Yang masih
    terbuka justru kesalahan yang paling mudah terjadi setiap hari:

      · **Ekspor B/C** tidak punya kolom platform maupun gudang. Berkas toko A
        yang diunggah ke toko B menjawab *"3 baris ditolak: belum pernah
        diimpor"* — benar, tetapi menyembunyikan sebabnya. Staf lalu mengira
        berkasnya rusak, atau (lebih mahal) memilih jenis "Pesanan Marketplace"
        supaya "mau masuk" ⇒ pesanan HANTU tanpa item & tanpa omzet.
      · Untuk jenis lain yang tidak punya sidik gudang, berkas toko A bisa
        MASUK ke toko B: omzet/komplain/konten toko A tercatat di toko B, dan
        tidak ada satu pun layar yang membantah.

    Dua bukti dipakai — keduanya fakta yang tercatat, bukan tebakan:

    1. **Tanda pengenal global milik toko lain** (`st.identity`): nomor pesanan
       platform, nomor komplain, URL konten. Kalau nomor itu SUDAH tercatat pada
       toko lain, berkasnya memang milik toko itu. Bila **mayoritas** baris
       (≥ setengah) begitu ⇒ PENGHALANG (commit ditolak); bila hanya sebagian
       ⇒ PERINGATAN yang menyebut toko & contohnya (bisa jadi berkas gabungan,
       jadi tidak boleh langsung dilarang).
    2. **Berkas dengan ISI yang sama persis pernah DISIMPAN ke toko lain**
       (`content_sha256`) — satu berkas ekspor tidak mungkin milik dua toko.
       Ini satu-satunya bukti yang tersedia untuk ekspor KPI/iklan yang isinya
       tidak membawa penanda toko apa pun (lihat `NO_IDENTITY_REASON`), jadi
       dibuat PERINGATAN (bukan penghalang): impor lama bisa saja sudah salah,
       dan staf yang memperbaiki keadaan tidak boleh ikut terhalang.

    Fungsi ini **hanya MEMBACA**. Ia dipakai `_commit_blockers()` (satu sumber
    dengan commit) dan pratinjau, jadi pesan yang dibaca staf di kedua tempat
    tidak bisa berbeda.
    """
    blockers: List[dict] = []
    warnings: List[dict] = []
    if not account or not s.get("account_id"):
        return blockers, warnings
    aid = account.get("id")

    # ── BUKTI 1 — tanda pengenal global yang sudah dimiliki toko lain ─────────
    if st.identity:
        refs = sorted({str((r.get("data") or {}).get(st.identity) or "").strip()
                       for r in built if r["status"] != "error"} - {""})
        if refs:
            coll = st.identity_collection or st.collection
            owners: Dict[str, dict] = {}
            hit_refs: set = set()
            async for row in db[coll].find(
                    {st.identity: {"$in": refs}, "account_id": {"$ne": aid}},
                    {"_id": 0, st.identity: 1, "account_id": 1, "account_name": 1}):
                oid = str(row.get("account_id") or "")
                if not oid:
                    continue
                hit_refs.add(str(row.get(st.identity) or ""))
                o = owners.setdefault(oid, {"name": row.get("account_name") or "",
                                            "n": 0, "sample": []})
                o["n"] += 1
                if len(o["sample"]) < 3:
                    o["sample"].append(str(row.get(st.identity) or ""))
            if owners:
                # Nama toko diambil dari master bila dokumennya belum ber-`account_name`
                # (dokumen lama) — pesan "toko (tanpa nama)" tidak bisa ditindaklanjuti.
                for oid, o in owners.items():
                    if not o["name"]:
                        acc = await db[scope.ACCOUNTS].find_one(
                            {"id": oid}, {"_id": 0, "account_name": 1})
                        o["name"] = (acc or {}).get("account_name") or oid[:8]
                top = max(owners.values(), key=lambda x: x["n"])
                rincian = "; ".join(
                    f"{o['name']} ({o['n']} {st.identity_label or 'baris'}, mis. "
                    f"{', '.join(o['sample'])})"
                    for o in sorted(owners.values(), key=lambda x: -x["n"]))
                n_hit, n_all = len(hit_refs), len(refs)
                if n_hit * 2 >= n_all:
                    blockers.append({"http": 409, "code": "berkas_milik_toko_lain",
                                     "message": (
                        f"Commit dibatalkan: {n_hit} dari {n_all} "
                        f"{st.identity_label or 'baris'} di berkas ini sudah tercatat "
                        f"pada toko LAIN — {rincian}. Berkas ini hampir pasti milik "
                        f"toko itu, bukan '{account.get('account_name')}'. Ganti toko "
                        f"tujuan ke '{top['name']}' di langkah 'Toko & konteks', atau "
                        f"ekspor ulang dari Seller Center "
                        f"'{account.get('account_name')}'. Kalau diteruskan, angka "
                        f"yang sama akan tercatat di DUA toko.")})
                else:
                    warnings.append({"code": "sebagian_milik_toko_lain", "message": (
                        f"Periksa dulu: {n_hit} dari {n_all} "
                        f"{st.identity_label or 'baris'} di berkas ini sudah tercatat "
                        f"pada toko lain — {rincian}. Baris itu akan MASUK ke "
                        f"'{account.get('account_name')}' juga (nomor yang sama pada "
                        f"dua toko), sehingga omzetnya terhitung dua kali. Kalau "
                        f"berkasnya campur, pisahkan dulu per toko.")})

    # ── BUKTI 2 — berkas dengan isi sama persis pernah masuk ke toko lain ─────
    h = str(s.get("content_sha256") or "")
    if h:
        other = await db[SESSIONS].find_one(
            {"content_sha256": h, "status": "committed", "rolled_back_at": None,
             "account_id": {"$ne": aid}, "id": {"$ne": s.get("id")}},
            {"_id": 0, "account_name": 1, "filename": 1, "committed_at": 1,
             "created_by": 1})
        if other is None:
            # Riwayat SEBELUM F12 belum menyimpan sidik isi. Melewatkannya berarti
            # bukti terkuat untuk ekspor KPI/iklan baru berlaku "mulai besok".
            # Jadi sidiknya dihitung DI MEMORI untuk calon yang masuk akal (jenis
            # sama, jumlah baris sama, toko lain, sudah tersimpan) — TIDAK
            # dituliskan ke DB, karena jalur pratinjau tidak boleh menulis apa pun
            # (aturan F11; kalau membuka layar bisa mengubah data, tidak ada yang
            # berani membukanya).
            cands = db[SESSIONS].find(
                {"source_type": st.key, "status": "committed",
                 "rolled_back_at": None, "account_id": {"$ne": aid},
                 "content_sha256": {"$in": [None, ""]},
                 "total_rows": s.get("total_rows")},
                {"_id": 0, "id": 1, "file_path": 1, "account_name": 1,
                 "filename": 1, "committed_at": 1, "created_by": 1}).limit(25)
            async for cand in cands:
                cand_raw = _read_session_file(cand.get("file_path") or "")
                if cand_raw is None:
                    continue      # berkasnya sudah tidak ada — jangan mengarang
                digest = hashlib.sha256(cand_raw).hexdigest()
                if digest == h:
                    other = cand
                    break
        if other:
            when = str(_ser(other.get("committed_at")) or "—")[:16].replace("T", " ")
            warnings.append({"code": "berkas_sudah_masuk_toko_lain", "message": (
                f"Berkas dengan ISI yang sama persis sudah pernah disimpan ke toko "
                f"'{other.get('account_name') or '(tanpa nama)'}' pada {when} "
                f"oleh {other.get('created_by') or '—'} (nama berkas saat itu: "
                f"{other.get('filename') or '—'}). Satu berkas ekspor tidak mungkin "
                f"milik dua toko. Kalau yang SALAH adalah impor terdahulu, buka "
                f"Riwayat impor toko itu dan tekan 'Batalkan impor' lebih dulu; kalau "
                f"yang salah toko tujuan sekarang, ganti tokonya.")})
    return blockers, warnings


async def _commit_blockers(db, st: SourceType, s: dict, built: List[dict],
                           account: Optional[dict], on_duplicate: str,
                           warnings_out: Optional[List[dict]] = None) -> List[dict]:
    """Alasan SELURUH commit akan ditolak. Kosong = tidak ada penghalang.

    → ``[{"http": 409|423|404|400, "code": "...", "message": "..."}]`` dengan
    URUTAN yang sama seperti pemeriksaan lama, supaya pesan pertama yang dilihat
    staf tidak berubah.
    """
    out: List[dict] = []

    # ── F7.2 — PAGAR TUMPANG-TINDIH PERIODE IKLAN ─────────────────────────────
    # Laporan iklan Shopee dipilih per RENTANG. Mengunggah "1–31 Agu" setelah
    # "7–13 Agu" akan membuat realisasi anggaran menghitung biaya yang sama dua
    # kali (Rp 374.074 muncul di dua dokumen berbeda) tanpa satu pun galat.
    # Rentang yang SAMA boleh diunggah ulang (itu koreksi, dan dedupe akan
    # memperbaruinya); rentang yang beririsan tapi berbeda ditolak dengan jalan keluar.
    if st.key == "shopee_ads_cpc" and s.get("account_id"):
        new_ranges = {(str((r.get("data") or {}).get("period_start"))[:10],
                       str((r.get("data") or {}).get("period_end"))[:10])
                      for r in built if r["status"] != "error"}
        new_ranges = {(a, b) for a, b in new_ranges if a and b and a != "None"}
        existing_ranges = set()
        async for row in db[st.collection].find(
                {"account_id": s["account_id"], "source_report": "shopee_ads_cpc"},
                {"_id": 0, "period_start": 1, "period_end": 1}):
            ps, pe = str(row.get("period_start"))[:10], str(row.get("period_end"))[:10]
            if ps and pe:
                existing_ranges.add((ps, pe))
        clashes = sorted(
            f"{ea}..{eb}" for ea, eb in existing_ranges
            for na, nb in new_ranges
            if (ea, eb) != (na, nb) and not (eb < na or ea > nb))
        if clashes:
            out.append({"http": 409, "code": "periode_iklan_bertindih", "message": (
                "Commit dibatalkan: toko ini sudah punya laporan iklan untuk periode "
                f"yang beririsan ({', '.join(dict.fromkeys(clashes))}) sedangkan berkas "
                f"ini {', '.join(f'{a}..{b}' for a, b in sorted(new_ranges))}. Biaya "
                "iklan akan terhitung dua kali di realisasi anggaran. Hapus dulu impor "
                "periode lama (Riwayat Impor → Rollback), atau ekspor ulang dengan "
                "rentang yang sama persis supaya baris lama diperbarui.")})

    # ── F18#3 — rincian produk tidak boleh membuat omzet sesi live dobel ──────
    if st.key == "live_session_products":
        live = await db.marketing_live_sessions.find_one(
            {"id": s.get("live_session_id")}, {"_id": 0})
        if not live:
            out.append({"http": 404, "code": "sesi_live_hilang",
                        "message": "Sesi live tujuan sudah tidak ada — commit dibatalkan"})
        else:
            from core import marketing_live_products as _LP
            existing_lines = await _LP.list_lines(db, live["id"])
            incoming = [{"revenue": (r["data"] or {}).get("revenue") or 0,
                         "units_sold": (r["data"] or {}).get("units_sold") or 0}
                        for r in built if r["status"] != "error"]
            if on_duplicate == "update":
                existing_lines = []   # baris lama akan ditimpa, jangan dihitung dobel
            try:
                _LP.assert_not_over_allocated(live, existing_lines + incoming)
            except HTTPException as exc:
                out.append({"http": exc.status_code, "code": "omzet_rincian_melebihi",
                            "message": str(exc.detail)})

    # ── F5.3 — PAGAR KUNCI PERIODE ────────────────────────────────────────────
    # Impor adalah jalur yang paling mudah menabrak periode tertutup: satu berkas
    # bisa menyentuh puluhan tanggal sekaligus, dan sesudah tersimpan angka bulan
    # yang sudah dirapatkan berubah tanpa ada yang tahu.
    if account and s.get("account_id"):
        touched_periods = set()
        for r in built:
            if r["status"] == "error":
                continue
            d = r.get("data") or {}
            raw = d.get("date") or d.get("order_date") or d.get("session_date")
            if isinstance(raw, datetime):
                touched_periods.add(raw.strftime("%Y-%m"))
            elif isinstance(raw, str) and len(raw) >= 7:
                touched_periods.add(raw[:7])
        # Berkas Ekspor B/C TIDAK punya kolom tanggal pesanan; yang ada hanya waktu
        # kirim/batal. Periode yang benar diambil dari BULAN PESANAN TUJUAN.
        if st.update_only:
            refs = sorted({str((r.get("data") or {}).get("order_id") or "").strip()
                           for r in built if r["status"] != "error"} - {""})
            if refs:
                async for row in db[st.collection].find(
                        {"account_id": s["account_id"], "order_id": {"$in": refs}},
                        {"_id": 0, "order_date": 1}):
                    raw = row.get("order_date")
                    if isinstance(raw, datetime):
                        touched_periods.add(raw.strftime("%Y-%m"))
                    elif isinstance(raw, str) and len(raw) >= 7:
                        touched_periods.add(raw[:7])
        locked_hits = []
        for p in sorted(touched_periods):
            if await _cycle.is_locked(db, s["account_id"], p):
                locked_hits.append(p)
        if locked_hits:
            out.append({"http": 423, "code": "periode_terkunci", "message": (
                "Commit dibatalkan: berkas ini menyentuh periode yang sudah DITUTUP "
                f"untuk toko {account.get('account_name', '')} — {', '.join(locked_hits)}. "
                "Minta SPV Marketing membuka periode itu (Siklus Marketing → Buka "
                "Periode), atau buang baris bulan tersebut dari berkas.")})

    # ── F12 — BERKAS MILIK TOKO LAIN (bukti, bukan dugaan) ────────────────────
    # Diletakkan PALING AKHIR supaya pesan pertama yang dilihat staf untuk keadaan
    # lama tidak bergeser. `warnings_out` diisi untuk pemanggil yang bisa
    # menampilkannya (pratinjau); `commit()` hanya peduli pada penghalang.
    ev_block, ev_warn = await _shop_evidence(db, st, s, built, account)
    out.extend(ev_block)
    if warnings_out is not None:
        warnings_out.extend(ev_warn)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# F3 — EKSPOR B & C: HANYA MEMPERBARUI PESANAN YANG SUDAH ADA
# ══════════════════════════════════════════════════════════════════════════════
# Field yang boleh disentuh berkas fulfillment. Daftar ini SENGAJA pendek: berkas
# B/C tidak memuat uang pesanan maupun item, jadi membiarkannya menimpa seluruh
# dokumen akan MENGHAPUS omzet, kreator, dan tautan katalog milik Ekspor A.
_FULFILLMENT_PATCH = (
    "substatus_raw", "return_type_raw", "cancel_by", "cancel_reason",
    "order_refund_amount", "tracking_number", "courier", "courier_raw",
    "status_raw", "shipped_at", "delivered_at", "cancelled_at",
)
# Tanggal dari berkas → stempel status di dokumen (dibaca "umur pesanan").
_FULFILLMENT_STAMPS = {"shipped_at": "shipped_date", "delivered_at": "delivered_date",
                       "cancelled_at": "cancelled_date"}
# Field yang IKUT berubah karena efek samping `order_status.apply_status`, jadi
# nilai sebelumnya WAJIB ikut disimpan supaya "Batalkan impor" tidak meninggalkan
# separuh keadaan lama dan separuh keadaan baru.
_FULFILLMENT_SIDE_EFFECTS = ("platform_status", "fulfillment_status",
                             "fulfillment_import_at", "fulfillment_import_session_id")
# JANGAN pernah dipulihkan: ini catatan reservasi stok. Membalikkannya berarti
# mengaku memesan stok yang reservasinya SUDAH dilepas ⇒ order batal yang masih
# "menggenggam" baris stok (persis yang dijaga gate KT-11) ⇒ barang yang sama
# bisa dijanjikan ke dua pembeli. Lihat `core/order_status.release_reservations`.
_NEVER_RESTORE = ("reserved_rows", "reserved_qty", "stock_reserved",
                  "reservation_released_at", "reservation_released_qty",
                  "reservation_released_reason", "status", "status_history",
                  "updated_at", "updated_by")
# TIDAK dipulihkan **bila statusnya tetap terminal** (batal/retur). Field-field ini
# MENERANGKAN status itu, jadi mengembalikannya ke nilai lama akan membuat sistem
# berbohong dengan cara yang berbeda:
#   · `fulfillment_status` → pesanan batal kembali masuk antrean gudang untuk
#     dipetik (padahal reservasinya sudah dilepas);
#   · `cancelled_date`/`returned_date` → "pembatalan tanpa tanggal" di laporan;
#   · `status_raw`/`platform_status` → istilah platform ("Dibatalkan") bertentangan
#     dengan status kanonik yang masih `cancelled`.
# Sisanya (resi, kurir, alasan, refund, jenis retur, qty retur, penanda impor)
# TETAP dipulihkan — dan laporan menyebut apa yang tinggal beserta alasannya.
_TERMINAL_KEEP = ("fulfillment_status", "cancelled_date", "returned_date",
                  "status_raw", "platform_status")


async def _apply_fulfillment_row(db, st: SourceType, doc: dict, existing: dict,
                                 user: dict, session_id: str) -> tuple:
    """Terapkan SATU baris Ekspor B/C ke pesanan yang sudah ada.

    → ``(action, why[], undo|None)`` dengan ``action`` ∈
    {``diperbarui``, ``dilewati``, ``ditolak``}.

    Semua perubahan status lewat `core.order_status.apply_status` — SATU penulis
    status, jadi jejak `status_history[]`, pelepasan reservasi (batal/retur),
    penyegaran cache stok katalog, dan hitung-ulang rekap harian ikut berjalan
    persis seperti kalau staf mengubahnya dari layar.
    """
    from core import order_status as _os

    prev_status = str(existing.get("status") or "")
    new_status = str(doc.get("status") or "")
    cancel_evidence = bool(doc.get("cancelled_at") or doc.get("return_type_raw"))

    # 1. field susulan (bukan status) — hanya yang benar-benar ada di berkas
    patch = {k: doc[k] for k in _FULFILLMENT_PATCH
             if k in doc and doc[k] not in (None, "", 0.0)}
    # 2. retur per SKU (opsional)
    sku = str(doc.get("platform_sku_id") or "").strip()
    qty_ret = doc.get("qty_returned")
    items_patch = None
    if sku and qty_ret is not None:
        items = [dict(it) for it in (existing.get("items") or [])]
        hit = next((it for it in items
                    if str(it.get("platform_sku_id") or "") == sku), None)
        if hit is None:
            return ("ditolak", [f"SKU '{sku}' tidak ada di pesanan "
                                f"{existing.get('order_id')} — periksa berkasnya "
                                "(jangan mengarang baris item baru)"], None)
        hit["qty_returned"] = int(qty_ret or 0)
        items_patch = items
        patch["items"] = items
        patch["qty_returned_total"] = sum(int(it.get("qty_returned") or 0)
                                          for it in items)

    undo = {
        "id": str(uuid.uuid4()), "session_id": session_id,
        "collection": st.collection, "doc_id": existing["id"],
        "order_ref": existing.get("order_id"),
        "account_id": existing.get("account_id"),
        "status_before": prev_status,
        # Nilai SEBELUM diubah. `items`/`qty_returned_total` sengaja TIDAK ikut
        # di sini: memulihkan seluruh array `items` akan menghidupkan kembali
        # `items[].reserved_rows` (lihat `_NEVER_RESTORE`). Yang dipulihkan hanya
        # angka `qty_returned` per SKU — satu-satunya isi `items` yang disentuh
        # berkas Ekspor B/C.
        "before": {k: existing.get(k) for k in sorted(
            (set(patch.keys()) | set(_FULFILLMENT_STAMPS.values())
             | set(_FULFILLMENT_SIDE_EFFECTS)) - set(_NEVER_RESTORE) - {"items",
                                                                        "qty_returned_total"})},
        "items_qty_before": ([{"platform_sku_id": str(it.get("platform_sku_id") or ""),
                               "qty_returned": it.get("qty_returned")}
                              for it in (existing.get("items") or [])]
                             if items_patch is not None else None),
        "qty_returned_total_before": (existing.get("qty_returned_total")
                                      if items_patch is not None else None),
        "created_at": _now(),
        "restored_at": None,
    }

    changed = False
    # 3. STATUS lewat SSOT (kalau berkasnya memang membawa status)
    if new_status and new_status != prev_status:
        stamps = {tgt: doc.get(src) for src, tgt in _FULFILLMENT_STAMPS.items()
                  if doc.get(src)}
        try:
            res = await _os.apply_status(
                db, existing, new_status, user=user, source=f"import:{st.key}",
                platform_status=doc.get("status_raw") or None,
                tracking_number=doc.get("tracking_number") or None,
                extra=patch or None, stamps=stamps or None,
                allow_import_vocab=True, forward_only=True,
                cancel_evidence=cancel_evidence)
        except _os.InvalidOrderTransition as exc:
            return ("ditolak", [str(exc)], None)
        changed = bool(res.get("changed")) or bool(patch)
    elif patch:
        patch["updated_at"] = _now()
        patch["updated_by"] = user.get("email", "system")
        for src, tgt in _FULFILLMENT_STAMPS.items():
            if doc.get(src):
                patch[tgt] = doc[src]
        await db[st.collection].update_one({"id": existing["id"]}, {"$set": patch})
        changed = True

    if not changed:
        return ("dilewati", ["tidak ada perubahan (status & field susulan sama)"], None)

    # 4. penanda bahwa pesanan ini SUDAH pernah terlihat di berkas fulfillment —
    #    dasar daftar "bocor" (ada di Ekspor A, belum pernah muncul di B).
    await db[st.collection].update_one({"id": existing["id"]}, {"$set": {
        "fulfillment_import_at": _now(),
        "fulfillment_import_session_id": session_id,
    }})
    return ("diperbarui", [], undo)


# ══════════════════════════════════════════════════════════════════════════════
# F3 — PEMULIHAN ("Batalkan impor") UNTUK IMPOR YANG HANYA MEMPERBARUI
# ══════════════════════════════════════════════════════════════════════════════
# Rollback impor biasa = hapus baris yang DIBUAT sesi ini. Impor Ekspor B/C tidak
# membuat baris apa pun; ia mengubah pesanan milik impor Ekspor A. Kalau tombol
# "Batalkan impor" hanya menghapus `committed_ids` (yang kosong), layar akan
# melaporkan "0 baris dihapus" sambil membiarkan SELURUH perubahan status tetap
# di tempatnya — janji yang tidak ditepati, dan staf tidak punya jalan keluar
# selain membetulkan satu-satu dari layar Pesanan.
#
# YANG JUJUR TIDAK BISA DIPULIHKAN (dan kenapa dibiarkan apa adanya)
# ------------------------------------------------------------------
# Pesanan yang berkasnya jadikan `cancelled`/`returned` sudah MELEPAS reservasi
# stoknya (`core/order_status.release_reservations`). Menghidupkannya kembali =
# order aktif yang tidak memesan stok apa pun ⇒ barang yang sama bisa dijanjikan
# ke pembeli lain. Karena itu untuk pesanan seperti itu:
#   · field susulan (resi, kurir, alasan batal, nilai refund, …) TETAP dipulihkan,
#   · status DIBIARKAN batal/retur,
#   · dan layar MENYEBUT nomor pesanannya + alasannya + langkah manualnya.
# Ini keputusan yang sama dengan `check_transition`: satu-satunya tempat aturan
# "order terminal tidak boleh dihidupkan" ditulis.
def _mk_field_undo(session_id: str, st: SourceType, existing: dict,
                   keys, status_before: str = "") -> dict:
    """SESI #38 — potret nilai SEBELUM ditimpa impor "perbarui yang lama".

    Bentuknya sengaja sama dengan jejak undo `update_only` (F3) supaya
    :func:`_restore_fulfillment_session` bisa memulihkannya tanpa cabang kedua.
    `updated_at`/`updated_by` tidak ikut dipulihkan: keduanya jejak audit, bukan
    isi data. Nilai yang dulu KOSONG disimpan sebagai ``None`` — pemulih
    membacanya sebagai ``$unset`` sehingga kolom yang lahir dari berkas benar-benar
    hilang lagi, bukan menjadi 0 karangan.
    """
    skip = set(_NEVER_RESTORE) | {"updated_at", "updated_by", "_import_session_id",
                                  "_import_source_type"}
    return {
        "id": str(uuid.uuid4()), "session_id": session_id,
        "kind": "field_update",
        "collection": st.collection, "doc_id": existing["id"],
        "order_ref": (existing.get("order_id") or existing.get("campaign_name")
                      or existing.get("sku") or existing.get("title")
                      or str(existing.get("date") or "") or existing["id"][:8]),
        "account_id": existing.get("account_id"),
        "status_before": status_before,
        "before": {k: existing.get(k) for k in sorted(set(keys) - skip)},
        "items_qty_before": None,
        "qty_returned_total_before": None,
        "created_at": _now(),
        "restored_at": None,
    }


async def _restore_fulfillment_session(db, session: dict, st: SourceType,
                                       user: dict) -> dict:
    """Pulihkan pesanan yang DIUBAH sesi impor ``update_only``. Idempoten.

    Return ``{restored, status_restored, fields_only, missing, notes[]}`` —
    ``notes`` selalu memuat nomor pesanan supaya laporan layar bisa ditindak.
    """
    from core import order_status as _os

    sid = session["id"]
    rows = await db[UNDO].find({"session_id": sid, "restored_at": None},
                               {"_id": 0}).to_list(eng.MAX_ROWS)
    out = {"restored": 0, "status_restored": 0, "fields_only": 0, "missing": 0,
           "notes": []}
    if not rows:
        return out

    now = _now()
    actor = user.get("email", "system")
    done_ids: List[str] = []
    for u in rows:
        coll = u.get("collection") or st.collection
        doc = await db[coll].find_one({"id": u.get("doc_id")}, {"_id": 0})
        if not doc:
            out["missing"] += 1
            out["notes"].append({
                "order": u.get("order_ref"), "result": "tidak ditemukan",
                "why": "dokumen pesanannya sudah tidak ada (dihapus sesudah impor) "
                       "— tidak ada yang bisa dipulihkan"})
            done_ids.append(u["id"])
            continue

        # 1. field susulan → nilai sebelum impor (None berarti dulu memang KOSONG)
        set_ops: Dict[str, Any] = {}
        unset_ops: Dict[str, str] = {}
        for k, v in (u.get("before") or {}).items():
            if k in _NEVER_RESTORE:
                continue
            if v in (None, ""):
                unset_ops[k] = ""
            else:
                set_ops[k] = v

        # 2. retur per SKU → HANYA angka `qty_returned` (reservasi tidak disentuh)
        if u.get("items_qty_before") is not None:
            before_map = {str(x.get("platform_sku_id") or ""): x.get("qty_returned")
                          for x in (u.get("items_qty_before") or [])}
            items = [dict(it) for it in (doc.get("items") or [])]
            for it in items:
                key = str(it.get("platform_sku_id") or "")
                if key not in before_map:
                    continue
                bv = before_map[key]
                if bv in (None, ""):
                    it.pop("qty_returned", None)
                else:
                    it["qty_returned"] = int(bv or 0)
            set_ops["items"] = items
            qb = u.get("qty_returned_total_before")
            if qb in (None, ""):
                unset_ops["qty_returned_total"] = ""
            else:
                set_ops["qty_returned_total"] = qb

        want = str(u.get("status_before") or "")
        status_now = str(doc.get("status") or "")
        note = (f"batalkan impor {st.label} (sesi {sid[:8]})")

        if want and want != status_now:
            try:
                # SATU penulis status, juga saat memulihkan: jejak `status_history`,
                # penyegaran cache stok, dan hitung-ulang rekap harian ikut jalan.
                await _os.apply_status(
                    db, doc, want, user=user, source=f"undo-import:{st.key}",
                    note=note, extra=set_ops or None, allow_import_vocab=True)
                if unset_ops:
                    await db[coll].update_one({"id": doc["id"]}, {"$unset": unset_ops})
                out["restored"] += 1
                out["status_restored"] += 1
                out["notes"].append({
                    "order": u.get("order_ref"), "result": "dipulihkan",
                    "why": f"status kembali '{status_now}' → '{want}' dan field "
                           "susulan dari berkas dibersihkan"})
            except _os.InvalidOrderTransition as exc:
                # Status tinggal di tempat. Yang MENERANGKAN status itu ikut
                # tinggal (lihat `_TERMINAL_KEEP`); sisanya tetap dipulihkan.
                keep = set(_TERMINAL_KEEP)
                ops: Dict[str, Any] = {}
                set_partial = {k: v for k, v in set_ops.items() if k not in keep}
                unset_partial = {k: v for k, v in unset_ops.items() if k not in keep}
                if set_partial:
                    ops["$set"] = {**set_partial, "updated_at": now, "updated_by": actor}
                if unset_partial:
                    ops["$unset"] = unset_partial
                if ops:
                    await db[coll].update_one({"id": doc["id"]}, ops)
                out["fields_only"] += 1
                out["notes"].append({
                    "order": u.get("order_ref"), "result": "sebagian",
                    "why": f"field susulan dari berkas dipulihkan (resi, kurir, "
                           f"alasan, refund, qty retur). Status TETAP "
                           f"'{status_now}' — beserta tanggal & istilah platformnya, "
                           f"supaya laporan tidak memuat pembatalan tanpa tanggal. "
                           f"{exc} Kalau pembatalan/retur ini keliru, buat pesanan "
                           "BARU dari layar Pesanan (reservasi stok baru) — jangan "
                           "menghidupkan yang lama."})
        else:
            ops = {}
            if set_ops:
                ops["$set"] = {**set_ops, "updated_at": now, "updated_by": actor}
            if unset_ops:
                ops["$unset"] = unset_ops
            if ops:
                await db[coll].update_one({"id": doc["id"]}, ops)
            out["restored"] += 1
            out["notes"].append({
                "order": u.get("order_ref"), "result": "dipulihkan",
                "why": ("nilai sebelum impor dipulihkan; kolom yang lahir dari "
                        "berkas dihapus lagi"
                        if u.get("kind") == "field_update" else
                        "status memang tidak diubah berkas ini; field susulan "
                        "dari berkas dibersihkan")})
        done_ids.append(u["id"])

    if done_ids:
        await db[UNDO].update_many({"id": {"$in": done_ids}}, {"$set": {
            "restored_at": now, "restored_by": actor}})
    return out


@router.get("/sessions/{session_id}/sku-map")
async def sku_map_list(session_id: str, request: Request,
                       only_unlinked: bool = Query(True)):
    """F1.4 — daftar SKU platform yang belum tertaut item katalog + USULAN.

    Kenapa perlu layar sendiri: ekspor Seller Center memakai `SKU ID` platform
    (angka panjang) yang TIDAK sama dengan SKU internal. Tanpa pemetaan, omzet
    tetap masuk (tidak boleh hilang) tetapi tidak bisa dihubungkan ke HPP/stok,
    sehingga marjin & ketersediaan tidak bisa dihitung.
    """
    await require_auth(request)
    db = get_db()
    import difflib as _dl
    s = await _load_session(db, session_id)
    st = get_source_type(s["source_type"])
    if not st.is_grouped:
        raise HTTPException(400, "Pemetaan SKU hanya untuk impor pesanan marketplace")
    aid = s.get("account_id")

    # sumber SKU: dokumen hasil commit bila sudah ada, kalau belum dari pratinjau
    groups: Dict[str, dict] = {}
    committed = await db[st.collection].count_documents({"_import_session_id": session_id})
    if committed:
        docs = await db[st.collection].find(
            {"_import_session_id": session_id}, {"_id": 0, "items": 1}).to_list(20000)
        item_lists = [d.get("items") or [] for d in docs]
    else:
        rows = _reparse(s)
        built = eng.build_rows(rows, s.get("mapping") or [], st, limit=eng.MAX_ROWS)
        item_lists = [(b.get("data") or {}).get("items") or [] for b in built]

    for items in item_lists:
        for it in items:
            psid = str(it.get("platform_sku_id") or "").strip()
            if not psid:
                continue
            if only_unlinked and it.get("catalog_item_id"):
                continue
            g = groups.setdefault(psid, {
                "platform_sku_id": psid,
                "seller_sku": it.get("seller_sku") or "",
                "product_name_raw": it.get("product_name_raw") or "",
                "variation_raw": it.get("variation_raw") or "",
                "product_category_raw": it.get("product_category_raw") or "",
                "rows": 0, "pcs": 0, "revenue": 0.0,
                "catalog_item_id": it.get("catalog_item_id"),
            })
            g["rows"] += 1
            g["pcs"] += int(it.get("quantity") or 0)
            g["revenue"] += float(it.get("sku_subtotal_after_discount") or 0)

    # usulan item katalog: kemiripan nama ≥ 0.7 (hanya USULAN, wajib dikonfirmasi)
    refidx = await _reference_index(db, st, s)
    by_name = refidx.get("items_by_name", {})
    name_keys = list(by_name.keys())
    catalog_items = [{"id": v["id"], "name": v.get("name"), "sku": v.get("sku"),
                      "hpp": v.get("hpp")} for v in by_name.values()]
    out = []
    for g in groups.values():
        suggestion = None
        key = scope.norm(g["product_name_raw"])
        if key:
            close = _dl.get_close_matches(key, name_keys, n=1, cutoff=0.7)
            if close:
                cand = by_name[close[0]]
                suggestion = {"catalog_item_id": cand["id"], "name": cand.get("name"),
                              "sku": cand.get("sku"),
                              "score": round(_dl.SequenceMatcher(None, key, close[0]).ratio(), 3)}
        g["revenue"] = round(g["revenue"], 2)
        g["suggestion"] = suggestion
        out.append(g)
    out.sort(key=lambda x: (-x["pcs"], x["product_name_raw"]))

    # kelompok per nama produk induk (aksi massal di layar)
    parents: Dict[str, dict] = {}
    for g in out:
        pname = g["product_name_raw"] or "(tanpa nama produk)"
        p = parents.setdefault(pname, {"product_name": pname, "sku_count": 0, "pcs": 0,
                                       "suggestion": g.get("suggestion")})
        p["sku_count"] += 1
        p["pcs"] += g["pcs"]
    return {"ok": True, "session_id": session_id, "account_id": aid,
            "source": "committed" if committed else "preview",
            "unmapped": out, "unmapped_total": len(out),
            "groups": sorted(parents.values(), key=lambda x: -x["pcs"]),
            "catalog_items": sorted(catalog_items, key=lambda x: (x.get("name") or "")),
            "catalog_items_total": len(catalog_items)}


@router.post("/sessions/{session_id}/sku-map")
async def sku_map_save(session_id: str, request: Request, body: List[SkuMapIn]):
    """F1.4 — simpan pemetaan `platform_sku_id` → item katalog (SSOT §4.3).

    Pemetaan ditulis ke `marketing_catalog_items.platform_sku_ids[]` (jadi impor
    BERIKUTNYA otomatis tertaut) **dan** langsung menautkan pesanan yang sudah
    masuk, supaya angka marjin/stok tidak menunggu impor berikutnya.
    """
    await require_auth(request)
    db = get_db()
    user = _user(request)
    s = await _load_session(db, session_id)
    st = get_source_type(s["source_type"])
    aid = s.get("account_id")
    if not body:
        raise HTTPException(400, "Tidak ada pemetaan yang dikirim")

    mapped = 0
    orders_touched = 0
    for row in body:
        psid = (row.platform_sku_id or "").strip()
        item_id = (row.catalog_item_id or "").strip()
        if not psid or not item_id:
            continue
        item = await db.marketing_catalog_items.find_one(
            {"id": item_id}, {"_id": 0, "id": 1, "name": 1, "hpp": 1, "fg_material_id": 1,
                              "variant_id": 1, "model_id": 1})
        if not item:
            raise HTTPException(400, f"Item katalog '{item_id}' tidak ditemukan")
        await db.marketing_catalog_items.update_one(
            {"id": item_id},
            {"$addToSet": {"platform_sku_ids": psid},
             "$set": {"updated_at": _now(),
                      "updated_by": user.get("email", "system")}})
        mapped += 1
        # tautkan pesanan yang SUDAH masuk (semua sesi toko ini, bukan hanya sesi ini)
        res = await db[st.collection].update_many(
            {"account_id": aid, "items.platform_sku_id": psid},
            {"$set": {"items.$[it].catalog_item_id": item["id"],
                      "items.$[it].fg_material_id": item.get("fg_material_id"),
                      "items.$[it].variant_id": item.get("variant_id"),
                      "items.$[it].model_id": item.get("model_id"),
                      "items.$[it].hpp_snapshot": item.get("hpp"),
                      "items.$[it].master_link_source": "sku_map",
                      "updated_at": _now()}},
            array_filters=[{"it.platform_sku_id": psid}])
        orders_touched += res.modified_count

    await log_activity(user.get("id", ""), user.get("name", ""),
                       f"Pemetaan SKU platform: {mapped} SKU ditautkan, "
                       f"{orders_touched} pesanan diperbarui",
                       "marketing-data-import", session_id)
    return {"ok": True, "mapped": mapped, "orders_updated": orders_touched,
            "message": (f"{mapped} SKU platform ditautkan ke item katalog dan "
                        f"{orders_touched} pesanan yang sudah masuk ikut diperbarui")}


# ══════════════════════════════════════════════════════════════════════════════
# FASE 4 (sesi #11) — PRATINJAU **PER BARIS**: "apa yang akan berubah?"
# ══════════════════════════════════════════════════════════════════════════════
# MASALAH YANG DITUTUP (diukur, bukan ditebak)
# -------------------------------------------
# Sebelum ini pratinjau impor bisa menjawab tiga hal saja: berapa baris terbaca,
# berapa yang valid/peringatan/galat, dan berapa banyak yang SUDAH ADA (jumlah
# agregat + 5 contoh). Yang TIDAK bisa dijawab justru pertanyaan yang menentukan
# pilihan staf:
#
#   · "kalau saya pilih **Perbarui yang lama**, nilai APA yang akan berubah di
#      baris yang sudah ada — dan dari berapa menjadi berapa?"
#   · "baris mana yang akan **dilewati**, mana yang akan **ditolak**, dan kenapa?"
#
# Akibat nyatanya bukan sekadar rasa tidak nyaman. Mode "Perbarui yang lama"
# dapat mengubah **status pesanan** (mis. `paid → cancelled`), dan perubahan itu
# MELEPAS reservasi stok serta menurunkan omzet bulan yang sudah dirapatkan.
# Memilih mode itu tanpa melihat daftar perubahannya = menandatangani surat yang
# belum dibaca. Satu-satunya jalan keluar yang tersedia dulu adalah "commit dulu,
# lihat hasilnya, kalau salah tekan Batalkan impor" — memakai DATA SUNGGUHAN
# sebagai kelinci percobaan.
#
# ATURAN YANG DIJAGA BERKAS INI
# -----------------------------
#  1. **Pratinjau tidak boleh menulis apa pun.** Tidak ada `update_one`,
#     `insert_one`, maupun `apply_status` di jalur ini. Yang dipakai hanyalah
#     pemeriksa MURNI dari SSOT status (`check_transition`/`assert_forward`).
#  2. **Pratinjau tidak boleh berbeda dari kenyataan.** Keputusan per baris
#     memakai fungsi yang SAMA dengan commit (`_finish`, `_update_payload`,
#     `st.dedupe`, `_shape.derived_safe_update`, `_FULFILLMENT_PATCH`), dan
#     penjaga `INV-IMPORPLAN` membuktikannya dengan menjalankan pratinjau lalu
#     commit pada sesi yang sama dan membandingkan KEEMPAT angkanya.
#  3. **Kosakata aksi sama dengan `row_notes` commit** supaya angka pratinjau dan
#     angka hasil bisa dibandingkan tanpa penerjemah:
#     `baru`(→disimpan) · `diperbarui` · `sebagian` · `dilewati` · `ditolak`.

# Kunci yang TIDAK ada artinya bagi pembaca layar (penanda waktu, jejak internal,
# id) — dibuang dari daftar "yang berubah" supaya perubahan yang PENTING tidak
# tenggelam di antara belasan baris derau.
_DIFF_HIDE = {
    "id", "created_at", "created_by", "updated_at", "updated_by",
    "status_history", "_import_session_id", "_import_source_type",
    "reserved_rows", "reserved_qty", "stock_reserved",
    "fulfillment_import_at", "fulfillment_import_session_id",
}
_DIFF_MAX = 14        # cukup untuk dibaca; sisanya diringkas "+N field lain"


def _disp(v: Any) -> str:
    """Nilai yang bisa dibaca manusia di kolom "lama → baru"."""
    if v is None or v == "":
        return "—"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M") if (v.hour or v.minute) else v.strftime("%Y-%m-%d")
    if isinstance(v, bool):
        return "ya" if v else "tidak"
    if isinstance(v, float):
        return f"{v:.0f}" if float(v).is_integer() else f"{v:.2f}"
    if isinstance(v, (list, tuple)):
        return f"{len(v)} baris"
    if isinstance(v, dict):
        return f"{len(v)} nilai"
    return str(v)


def _norm_dt(v: datetime) -> datetime:
    """Bentuk waktu yang bisa dibandingkan — SATU tempat.

    MongoDB mengembalikan `datetime` **naive** (isinya UTC), sedangkan berkas yang
    baru dibaca menghasilkan `datetime` **ber-zona** (`timezone.utc`). Di Python
    `aware == naive` **selalu** False, jadi tanpa penyamaan ini SETIAP kolom
    tanggal dilaporkan "berubah" padahal nilai yang akan ditulis sama — pratinjau
    berbunyi `Waktu Pesanan Dibuat: 2026-08-05 10:15 → 2026-08-05 10:15`.

    Akibatnya bukan sekadar jelek di layar:
      · staf belajar mengabaikan kolom "yang berubah" — padahal justru kolom itu
        alasan panel ini ada;
      · perubahan PALSU memakan kuota tampilan (`_DIFF_MAX`), sehingga perubahan
        NYATA bisa terdorong ke ringkasan "+N field lain" dan tak terlihat;
      · catatan jujur "tidak ada nilai yang berubah — hanya penanda waktu
        pembaruan yang ditulis" tidak pernah muncul, karena daftar perubahan
        tidak pernah kosong.
    """
    if v.tzinfo is not None:
        v = v.astimezone(timezone.utc).replace(tzinfo=None)
    return v.replace(second=0, microsecond=0)


def _same(a: Any, b: Any) -> bool:
    """Bandingkan seperti yang DILIHAT pembaca (1000 == 1000.0, tanggal per menit)."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(float(a) - float(b)) < 0.005
    if isinstance(a, datetime) and isinstance(b, datetime):
        return _norm_dt(a) == _norm_dt(b)
    return _disp(a) == _disp(b)


def _label_of(st: SourceType, name: str) -> str:
    f = st.field(name)
    return f.label if f else name


def _diff_changes(st: SourceType, payload: dict, existing: dict) -> tuple:
    """Daftar perubahan NYATA payload vs dokumen lama → ``(changes[], hidden_n)``."""
    changes: List[dict] = []
    hidden = 0
    for k in sorted(payload.keys()):
        if k in _DIFF_HIDE:
            continue
        new_v, old_v = payload[k], existing.get(k)
        if _same(new_v, old_v):
            continue
        if len(changes) >= _DIFF_MAX:
            hidden += 1
            continue
        changes.append({"field": k, "label": _label_of(st, k),
                        "before": _disp(old_v), "after": _disp(new_v)})
    return changes, hidden


def _new_row_changes(st: SourceType, doc: dict) -> tuple:
    """Untuk baris BARU: nilai yang akan ditulis (kolom "lama" kosong).

    Hanya field yang memang berasal dari berkas (`st.input_fields`) ditampilkan —
    stempel toko & nilai turunan bukan keputusan staf, jadi memajangnya hanya
    menambah derau di layar yang tugasnya membuat staf berani menekan Simpan.
    """
    changes: List[dict] = []
    hidden = 0
    for f in st.input_fields:
        v = doc.get(f.name)
        if v in (None, "", 0, 0.0, []):
            continue
        if len(changes) >= _DIFF_MAX:
            hidden += 1
            continue
        changes.append({"field": f.name, "label": f.label,
                        "before": "—", "after": _disp(v)})
    return changes, hidden


def _status_reject_reason(prev: str, new: str, cancel_evidence: bool) -> Optional[str]:
    """Alasan `apply_status` AKAN menolak baris ini — tanpa menulis apa pun.

    Memakai pemeriksa yang sama dengan penulis status (`core.order_status`), jadi
    baris yang di pratinjau berbunyi "ditolak: status mundur" pasti juga ditolak
    saat commit, dengan kalimat yang sama persis.
    """
    from core import order_status as _os

    allowed = _os.ORDER_STATUSES + _os.IMPORT_ONLY_STATUSES
    if new not in allowed:
        return (f"Status '{new}' tidak dikenal. Pilih: {', '.join(allowed)}")
    try:
        _os.check_transition(prev, new)
        _os.assert_forward(prev, new, cancel_evidence=cancel_evidence)
    except _os.InvalidOrderTransition as exc:
        return str(exc)
    return None


def _plan_fulfillment_row(st: SourceType, doc: dict, existing: dict) -> tuple:
    """Ramalan satu baris Ekspor B/C → ``(action, why[], changes[], hidden)``.

    Cerminan `_apply_fulfillment_row` **tanpa menulis**. Kesetaraan "berubah /
    tidak berubah" dipertahankan persis: commit menganggap baris BERUBAH bila ada
    `patch` (walau nilainya sama dengan yang tersimpan, karena `$set` tetap
    jalan), jadi pratinjau pun menghitungnya `diperbarui` — tetapi menjelaskan
    bahwa nilainya sama supaya angkanya tidak terbaca sebagai perubahan data.
    """
    prev_status = str(existing.get("status") or "")
    new_status = str(doc.get("status") or "")
    cancel_evidence = bool(doc.get("cancelled_at") or doc.get("return_type_raw"))

    patch = {k: doc[k] for k in _FULFILLMENT_PATCH
             if k in doc and doc[k] not in (None, "", 0.0)}

    # retur per SKU — SKU yang tak ada di pesanan DITOLAK (jangan mengarang item)
    sku = str(doc.get("platform_sku_id") or "").strip()
    qty_ret = doc.get("qty_returned")
    items_change = None
    if sku and qty_ret is not None:
        items = existing.get("items") or []
        hit = next((it for it in items
                    if str(it.get("platform_sku_id") or "") == sku), None)
        if hit is None:
            return ("ditolak", [f"SKU '{sku}' tidak ada di pesanan "
                                f"{existing.get('order_id')} — periksa berkasnya "
                                "(jangan mengarang baris item baru)"], [], 0)
        if int(hit.get("qty_returned") or 0) != int(qty_ret or 0):
            items_change = {"field": f"items[{sku}].qty_returned",
                            "label": f"Qty retur SKU {sku}",
                            "before": _disp(hit.get("qty_returned")),
                            "after": _disp(qty_ret)}

    changes: List[dict] = []
    status_moves = bool(new_status and new_status != prev_status)
    if status_moves:
        why = _status_reject_reason(prev_status, new_status, cancel_evidence)
        if why:
            return ("ditolak", [why], [], 0)
        changes.append({"field": "status", "label": "Status pesanan",
                        "before": _disp(prev_status), "after": _disp(new_status)})
        for src, tgt in _FULFILLMENT_STAMPS.items():
            if doc.get(src) and not _same(doc[src], existing.get(tgt)):
                changes.append({"field": tgt, "label": _label_of(st, src),
                                "before": _disp(existing.get(tgt)),
                                "after": _disp(doc[src])})

    field_changes, hidden = _diff_changes(st, patch, existing)
    changes.extend(field_changes)
    if items_change:
        changes.append(items_change)

    if not status_moves and not patch:
        return ("dilewati",
                ["tidak ada perubahan (status & field susulan sama)"], [], 0)

    notes: List[str] = []
    if status_moves and new_status in ("cancelled", "returned"):
        notes.append("status jadi batal/retur ⇒ reservasi stoknya DILEPAS dan "
                     "pesanan keluar dari antrean gudang")
    if not changes:
        notes.append("nilainya sama dengan yang tersimpan — hanya penanda "
                     "\u201csudah terlihat di berkas fulfillment\u201d yang diperbarui")
    return ("diperbarui", notes, changes, hidden)


def _row_ref(st: SourceType, data: dict) -> str:
    """Acuan baris yang dikenali staf (nomor pesanan / tanggal / judul)."""
    for k in ("order_id", "date", "order_date", "session_date", "title",
              "product_name", "sku", "campaign_name", "name", "username",
              "creator_code", "period_start"):
        v = data.get(k)
        if v not in (None, ""):
            return _disp(v)
    return ""


async def _plan_rows(db, st: SourceType, s: dict, built: List[dict], refidx: dict,
                     account: Optional[dict], on_duplicate: str,
                     skip_warnings: bool) -> tuple:
    """Ramalan SELURUH berkas → ``(plans[], counts{})``. TIDAK menulis apa pun."""
    plans: List[dict] = []
    counts = {"baru": 0, "diperbarui": 0, "sebagian": 0, "dilewati": 0,
              "ditolak": 0, "total": 0}

    def add(row_no: int, ref: str, action: str, why: List[str],
            changes: Optional[List[dict]] = None, hidden: int = 0,
            target_id: str = "", status_now: str = ""):
        counts[action] = counts.get(action, 0) + 1
        counts["total"] += 1
        plans.append({"row": row_no, "ref": ref, "action": action,
                      "why": [w for w in (why or []) if w],
                      "changes": changes or [], "changes_hidden": hidden,
                      "target_id": target_id, "status_now": status_now})

    for r in built:
        row_no = r["row_id"] + 2
        data = r.get("data") or {}
        ref = _row_ref(st, data)
        if r["status"] == "error" or (skip_warnings and r["status"] == "warning"):
            add(row_no, ref, "ditolak", r["errors"] or r["warnings"])
            continue
        doc, extra_warn = _finish(st, r["data"], s, refidx, account=account)
        if doc is None:
            add(row_no, ref, "ditolak", extra_warn)
            continue
        if account:
            scope.stamp_account(doc, account)

        existing = None
        if st.dedupe:
            key, ok = {}, True
            for k in st.dedupe:
                v = doc.get(k) if k != "account_id" else s.get("account_id")
                if v in (None, ""):
                    ok = False
                    break
                key[k] = v
            if ok:
                existing = await db[st.collection].find_one(key, {"_id": 0})

        if existing:
            status_now = str(existing.get("status") or "")
            if st.update_only:
                act, why, changes, hidden = _plan_fulfillment_row(st, doc, existing)
                add(row_no, ref, act, why, changes, hidden,
                    target_id=existing.get("id", ""), status_now=status_now)
                continue
            if st.key == "sales_daily" and _shape.is_derived(existing):
                safe, protected = _shape.derived_safe_update(doc)
                msg = _shape.derived_lock_message(
                    existing.get("date") or doc.get("date"), protected,
                    kept=len(safe))
                if safe:
                    changes, hidden = _diff_changes(st, safe, existing)
                    add(row_no, ref, "sebagian", [msg], changes, hidden,
                        target_id=existing.get("id", ""), status_now=status_now)
                else:
                    add(row_no, ref, "dilewati", [msg],
                        target_id=existing.get("id", ""), status_now=status_now)
                continue
            if on_duplicate == "update":
                payload = dict(_update_payload(st, doc, existing))
                notes: List[str] = []
                if st.collection == "marketing_orders":
                    new_st = str(payload.pop("status", "") or "")
                    payload.pop("status_history", None)
                    prev_st = str(existing.get("status") or "")
                    if new_st and new_st != prev_st:
                        why = _status_reject_reason(
                            prev_st, new_st,
                            bool(doc.get("cancelled_at") or doc.get("return_type_raw")))
                        if why:
                            notes.append(f"status TETAP '{prev_st}' — perubahan ke "
                                         f"'{new_st}' ditolak aturan status: {why}")
                        else:
                            payload["status"] = new_st
                            notes.append(f"status {prev_st} → {new_st} lewat aturan "
                                         "status (reservasi stok ikut disesuaikan)")
                changes, hidden = _diff_changes(st, payload, existing)
                if not changes:
                    notes.append("tidak ada nilai yang berubah — hanya penanda "
                                 "waktu pembaruan yang ditulis")
                add(row_no, ref, "diperbarui", notes, changes, hidden,
                    target_id=existing.get("id", ""), status_now=status_now)
            else:
                add(row_no, ref, "dilewati", ["sudah ada (duplikat)"],
                    target_id=existing.get("id", ""), status_now=status_now)
            continue

        if st.update_only:
            add(row_no, ref, "ditolak",
                [f"Pesanan '{doc.get('order_id') or '(tanpa nomor)'}' belum pernah "
                 "diimpor — impor 'Pesanan Marketplace (ekspor Seller Center)' dulu. "
                 "Berkas status pengiriman tidak boleh membuat pesanan baru "
                 "(pesanan tanpa item & tanpa omzet)."])
            continue

        changes, hidden = _new_row_changes(st, doc)
        add(row_no, ref, "baru", (r["warnings"] or []) + (extra_warn or []),
            changes, hidden)
    return plans, counts


async def _plan_context(db, session_id: str, on_duplicate: str,
                       skip_warnings: bool) -> dict:
    """Susun seluruh ramalan impor (dipakai layar & unduhan CSV)."""
    s = await _load_session(db, session_id)
    st = get_source_type(s["source_type"])
    rows = _reparse(s)
    built = eng.build_rows(rows, s.get("mapping") or [], st, limit=eng.MAX_ROWS)
    built = await _annotate_master_links(db, st, s, built)
    refidx = await _reference_index(db, st, s)
    account = None
    if s.get("account_id"):
        account = await db[scope.ACCOUNTS].find_one({"id": s["account_id"]}, {"_id": 0})
    if st.key == "samples" and s.get("creator_id"):
        cr = await db[scope.CREATORS].find_one({"id": s["creator_id"]}, {"_id": 0})
        if cr:
            plats = cr.get("platforms") or {}
            s["creator_username"] = (plats.get("tiktok") or plats.get("instagram")
                                     or cr.get("creator_code") or cr.get("name"))
    # F7.2 — jenis SNAPSHOT selalu memperbarui baris lama; pratinjau harus
    # memakai mode yang BENAR-BENAR akan dipakai commit, bukan yang dipilih layar.
    effective = "update" if st.key in REFRESH_ON_DUPLICATE else on_duplicate
    forced = effective != on_duplicate
    plans, counts = await _plan_rows(db, st, s, built, refidx, account,
                                     effective, skip_warnings)
    warnings: List[dict] = []
    blockers = await _commit_blockers(db, st, s, built, account, effective,
                                      warnings_out=warnings)
    return {"session": s, "st": st, "plans": plans, "counts": counts,
            "blockers": blockers, "warnings": warnings,
            "mode": effective, "mode_forced": forced,
            "account": account}


@router.get("/sessions/{session_id}/plan")
async def plan(session_id: str, request: Request,
               on_duplicate: str = Query("skip", pattern="^(skip|update)$"),
               skip_warnings: bool = Query(False),
               only: Optional[str] = Query(
                   None, pattern="^(baru|diperbarui|sebagian|dilewati|ditolak)$"),
               q: Optional[str] = Query(None),
               page: int = Query(1, ge=1),
               page_size: int = Query(50, ge=1, le=500)):
    """**Apa yang akan berubah kalau saya tekan Simpan** — per baris, sebelum commit.

    Hanya MEMBACA. Lihat catatan besar di atas untuk alasan & aturannya.
    """
    await require_auth(request)
    db = get_db()
    ctx = await _plan_context(db, session_id, on_duplicate, skip_warnings)
    st: SourceType = ctx["st"]
    rows = ctx["plans"]
    if only:
        rows = [r for r in rows if r["action"] == only]
    needle = (q or "").strip().lower()
    if needle:
        def hit(r: dict) -> bool:
            hay = " ".join([str(r.get("ref") or ""), str(r.get("action") or ""),
                            " ".join(r.get("why") or []),
                            " ".join(f"{c['label']} {c['before']} {c['after']}"
                                     for c in (r.get("changes") or []))]).lower()
            return needle in hay
        rows = [r for r in rows if hit(r)]
    total = len(rows)
    start = (page - 1) * page_size
    return {
        "ok": True,
        "source_type": st.key,
        "label": st.label,
        "update_only": st.update_only,
        "dedupe": list(st.dedupe or ()),
        "mode": ctx["mode"],
        "mode_forced": ctx["mode_forced"],
        "counts": ctx["counts"],
        "blockers": ctx["blockers"],
        # F12 — bukti "berkas ini milik toko lain" yang TIDAK mematikan Simpan
        # (sebagian baris / impor terdahulu yang mungkin salah), tetapi WAJIB
        # terlihat sebelum staf memutuskan.
        "warnings": ctx["warnings"],
        "rows": _ser(rows[start:start + page_size]),
        "pagination": {"total": total, "page": page, "page_size": page_size},
        "filtered": bool(only or needle),
    }


@router.get("/sessions/{session_id}/plan.csv")
async def plan_csv(session_id: str, request: Request,
                   on_duplicate: str = Query("skip", pattern="^(skip|update)$"),
                   skip_warnings: bool = Query(False),
                   only: Optional[str] = Query(
                       None, pattern="^(baru|diperbarui|sebagian|dilewati|ditolak)$")):
    """Ramalan impor sebagai CSV — supaya bisa diperiksa/diteruskan sebelum commit."""
    await require_auth(request)
    db = get_db()
    ctx = await _plan_context(db, session_id, on_duplicate, skip_warnings)
    rows = ctx["plans"]
    if only:
        rows = [r for r in rows if r["action"] == only]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Baris", "Acuan", "Akan", "Status sekarang", "Field",
                "Nilai lama", "Nilai baru", "Alasan / catatan"])
    for r in rows:
        why = " · ".join(r["why"])
        if r["changes"]:
            for c in r["changes"]:
                w.writerow([r["row"], r["ref"], r["action"], r["status_now"],
                            c["label"], c["before"], c["after"], why])
        else:
            w.writerow([r["row"], r["ref"], r["action"], r["status_now"],
                        "", "", "", why])
    buf.seek(0)
    fn = f"rencana-impor-{session_id[:8]}.csv"
    return StreamingResponse(iter(["\ufeff" + buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@router.get("/sessions/{session_id}/result.csv")
async def result_csv(session_id: str, request: Request,
                     only_rejected: bool = Query(False)):
    """Laporan HASIL impor (sesudah commit) — termasuk baris DITOLAK + alasannya.

    Kenapa perlu diunduh: `row_notes` hanya tampil 200 baris pertama di layar dan
    hilang begitu halaman ditutup. Baris yang ditolak harus bisa dibawa kembali ke
    berkas aslinya untuk diperbaiki — kalau tidak, "12 baris ditolak" berakhir
    sebagai 12 pesanan yang hilang tanpa jejak.
    """
    await require_auth(request)
    db = get_db()
    s = await _load_session(db, session_id)
    if s.get("status") != "committed":
        raise HTTPException(400, "Sesi ini belum di-commit — belum ada hasil untuk "
                                "diunduh. Pakai \u201cUnduh rencana (CSV)\u201d di "
                                "langkah pratinjau.")
    notes = s.get("row_notes") or []
    if only_rejected:
        notes = [n for n in notes if str(n.get("action") or "") == "ditolak"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Berkas", "Jenis", "Di-commit", "Baris", "Hasil",
                "Alasan / catatan", "ID tujuan"])
    fname = s.get("filename") or ""
    stype = s.get("source_type") or ""
    cat = str(s.get("committed_at") or "")[:19]
    for n in notes:
        w.writerow([fname, stype, cat, n.get("row", ""), n.get("action", ""),
                    " · ".join(n.get("why") or []), n.get("id", "")])
    if not notes:
        w.writerow([fname, stype, cat, "", "tidak ada catatan baris",
                    "semua baris masuk tanpa peringatan", ""])
    buf.seek(0)
    fn = f"hasil-impor-{session_id[:8]}.csv"
    return StreamingResponse(iter(["\ufeff" + buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})



@router.post("/sessions/{session_id}/commit")
async def commit(session_id: str, request: Request, body: Optional[CommitIn] = None):
    await require_auth(request)
    user = _user(request)
    db = get_db()
    opt = body or CommitIn()
    s = await _load_session(db, session_id)
    if s.get("status") == "committed":
        raise HTTPException(400, "Sesi ini sudah di-commit")
    st = get_source_type(s["source_type"])
    report = s.get("mapping_report") or {}
    if not report.get("ready"):
        raise HTTPException(400, "Pemetaan belum lengkap. Kolom wajib yang belum "
                                 f"terpetakan: {', '.join(report.get('missing_required', []))}")

    rows = _reparse(s)
    built = eng.build_rows(rows, s.get("mapping") or [], st, limit=eng.MAX_ROWS)
    built = await _annotate_master_links(db, st, s, built)
    refidx = await _reference_index(db, st, s)
    account = None
    if s.get("account_id"):
        account = await db[scope.ACCOUNTS].find_one({"id": s["account_id"]}, {"_id": 0})
    if st.key == "samples" and s.get("creator_id"):
        cr = await db[scope.CREATORS].find_one({"id": s["creator_id"]}, {"_id": 0})
        if cr:
            plats = cr.get("platforms") or {}
            s["creator_username"] = (plats.get("tiktok") or plats.get("instagram")
                                     or cr.get("creator_code") or cr.get("name"))

    inserted, updated, skipped, rejected = [], 0, 0, 0
    row_notes: List[dict] = []
    now = _now()
    # F3 — jejak UNDO untuk impor `update_only`. Impor yang hanya MEMPERBARUI tidak
    # bisa di-rollback dengan menghapus baris (barisnya bukan milik sesi ini!), jadi
    # keadaan sebelum diubah disimpan dulu. Tanpa ini, tombol "Batalkan impor" pada
    # Ekspor B/C hanya akan diam — janji yang tidak ditepati.
    undo_rows: List[dict] = []

    # ── F7.2 — snapshot KPI selalu disegarkan (lihat REFRESH_ON_DUPLICATE) ────
    if st.key in REFRESH_ON_DUPLICATE and opt.on_duplicate != "update":
        opt.on_duplicate = "update"

    # ── FASE 4 (sesi #11) — PENGHALANG SELURUH COMMIT: SATU SUMBER ────────────
    # Ketiga pemeriksaan yang dulu ditulis di sini (periode iklan bertindih ·
    # omzet rincian sesi live melebihi · periode akuntansi TERKUNCI) sekarang
    # hidup di `_commit_blockers()`, supaya **pratinjau** bisa menampilkannya
    # SEBELUM tombol Simpan ditekan. Perilaku di sini tidak berubah sedikit pun:
    # penghalang pertama tetap menaikkan HTTP & pesan yang sama, sebelum satu
    # baris pun tersimpan.
    for _blocker in await _commit_blockers(db, st, s, built, account,
                                          opt.on_duplicate):
        raise HTTPException(_blocker["http"], _blocker["message"])

    for r in built:
        if r["status"] == "error" or (opt.skip_warnings and r["status"] == "warning"):
            rejected += 1
            row_notes.append({"row": r["row_id"] + 2, "action": "ditolak",
                              "why": r["errors"] or r["warnings"]})
            continue
        doc, extra_warn = _finish(st, r["data"], s, refidx, account=account)
        if doc is None:
            # baris tidak bisa ditautkan ke master → ditolak dengan alasan jelas
            rejected += 1
            row_notes.append({"row": r["row_id"] + 2, "action": "ditolak",
                              "why": extra_warn})
            continue
        if account:
            scope.stamp_account(doc, account)
        elif st.account_scope == "required":
            raise HTTPException(400, "Akun sesi tidak ditemukan lagi — commit dibatalkan")

        if st.dedupe:
            key = {}
            ok = True
            for k in st.dedupe:
                v = doc.get(k) if k != "account_id" else s.get("account_id")
                if v in (None, ""):
                    ok = False
                    break
                key[k] = v
            if ok:
                # F2 (2026-08-12) — dokumen LENGKAP dibaca (bukan hanya `id`) karena
                # kita perlu tahu apakah dokumen tujuan itu TURUNAN. Lihat catatan di
                # `core/marketing_sales_shape.derived_safe_update`.
                existing = await db[st.collection].find_one(key, {"_id": 0})
                if existing:
                    # ── F3 — IMPOR YANG HANYA MEMPERBARUI (Ekspor B & C) ────
                    if st.update_only:
                        act, why, undo = await _apply_fulfillment_row(
                            db, st, doc, existing, user, session_id)
                        if undo:
                            undo_rows.append(undo)
                        if act == "diperbarui":
                            updated += 1
                        elif act == "dilewati":
                            skipped += 1
                        else:
                            rejected += 1
                        row_notes.append({"row": r["row_id"] + 2, "action": act,
                                          "why": why, "id": existing["id"]})
                        continue
                    # ── PAGAR F2: omzet turunan tidak boleh ditimpa berkas ──
                    if st.key == "sales_daily" and _shape.is_derived(existing):
                        safe, protected = _shape.derived_safe_update(doc)
                        msg = _shape.derived_lock_message(
                            existing.get("date") or doc.get("date"),
                            protected, kept=len(safe))
                        if safe:
                            safe["updated_at"] = now
                            safe["updated_by"] = user.get("email", "system")
                            undo_rows.append(_mk_field_undo(
                                session_id, st, existing, safe.keys()))
                            await db[st.collection].update_one(
                                {"id": existing["id"]}, {"$set": safe})
                            updated += 1
                            row_notes.append({"row": r["row_id"] + 2,
                                              "action": "sebagian disimpan",
                                              "why": [msg], "id": existing["id"]})
                        else:
                            skipped += 1
                            row_notes.append({"row": r["row_id"] + 2,
                                              "action": "dilewati",
                                              "why": [msg], "id": existing["id"]})
                        continue
                    if opt.on_duplicate == "update":
                        payload = _update_payload(st, doc, existing)
                        # ── LUBANG UANG/STOK YANG DITUTUP 2026-08-14 ──────────
                        # Skenario nyata: staf mengimpor ekspor tanggal 1–7, lalu
                        # mengimpor 5–12. Baris 5–7 memang terdeteksi duplikat
                        # (kunci `order_id`), tetapi pada mode "Perbarui yang
                        # lama" versi sebelumnya menulis SELURUH dokumen dengan
                        # `$set` — termasuk `status`. Akibatnya:
                        #   · pesanan yang di berkas baru "Dibatalkan" berubah
                        #     status TANPA melepas reservasi stok ⇒ pesanan batal
                        #     tetap menggenggam stok, dan barang yang sama bisa
                        #     dijanjikan ke pembeli lain (overselling);
                        #   · pesanan batal tetap tertinggal di antrean gudang
                        #     (`fulfillment_status` tidak ikut disesuaikan);
                        #   · status bisa MUNDUR diam-diam (mengunggah ulang
                        #     berkas lama membuat pesanan "selesai" kembali ke
                        #     "perlu dikirim") — cacat yang sama yang ditutup F3
                        #     untuk Ekspor B/C, tetapi pintunya masih terbuka di
                        #     sini.
                        # Sekarang status TIDAK PERNAH ditulis langsung: ia
                        # dijalankan lewat SSOT `core.order_status.apply_status`
                        # (aturan transisi + pelepasan reservasi + jejak), sama
                        # seperti jalur Ekspor B/C.
                        st_note: List[str] = []
                        status_before_undo = ""
                        if st.collection == "marketing_orders":
                            new_st = str(payload.pop("status", "") or "")
                            payload.pop("status_history", None)
                            prev_st = str(existing.get("status") or "")
                            if new_st and new_st != prev_st:
                                try:
                                    from core import order_status as _os
                                    await _os.apply_status(
                                        db, existing, new_st, user=user,
                                        source="import_orders",
                                        platform_status=doc.get("status_raw"),
                                        allow_import_vocab=True, forward_only=True,
                                        cancel_evidence=bool(
                                            doc.get("cancelled_at")
                                            or doc.get("return_type_raw")),
                                        note=(f"impor {st.label} (berkas "
                                              f"{s.get('filename') or '-'})"))
                                    st_note.append(f"status {prev_st} → {new_st} "
                                                   "lewat aturan status (reservasi "
                                                   "stok ikut disesuaikan)")
                                    status_before_undo = prev_st
                                except Exception as exc:
                                    st_note.append(
                                        f"status TETAP '{prev_st}' — perubahan ke "
                                        f"'{new_st}' ditolak aturan status: {exc}")
                        payload["updated_at"] = now
                        payload["updated_by"] = user.get("email", "system")
                        # SESI #38 — JEJAK UNDO untuk pembaruan BIASA.
                        # `undo_rows` dulu hanya diisi jalur `update_only`, jadi
                        # impor ulang ekspor iklan/KPI menimpa 4 baris lalu
                        # "Batalkan impor" menjawab "sesi ini tidak membuat
                        # maupun mengubah baris" — bantahan atas perubahan yang
                        # baru saja ia lakukan sendiri. Nilai sebelum ditimpa
                        # disimpan supaya tombol itu menepati janjinya.
                        undo_rows.append(_mk_field_undo(
                            session_id, st, existing, payload.keys(),
                            status_before=status_before_undo))
                        await db[st.collection].update_one(
                            {"id": existing["id"]}, {"$set": payload})
                        updated += 1
                        row_notes.append({"row": r["row_id"] + 2, "action": "diperbarui",
                                          "why": st_note, "id": existing["id"]})
                    else:
                        skipped += 1
                        row_notes.append({"row": r["row_id"] + 2, "action": "dilewati",
                                          "why": ["sudah ada (duplikat)"],
                                          "id": existing["id"]})
                    continue

        # ── F3 — jenis `update_only` TIDAK PERNAH membuat baris baru ──────────
        if st.update_only:
            rejected += 1
            row_notes.append({
                "row": r["row_id"] + 2, "action": "ditolak",
                "why": [f"Pesanan '{doc.get('order_id') or '(tanpa nomor)'}' belum "
                        "pernah diimpor — impor 'Pesanan Marketplace (ekspor Seller "
                        "Center)' dulu. Berkas status pengiriman tidak boleh "
                        "membuat pesanan baru (pesanan tanpa item & tanpa omzet)."]})
            continue

        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = now
        doc["updated_at"] = now
        doc["created_by"] = user.get("email", "system")
        doc["_import_session_id"] = session_id
        doc["_import_source_type"] = st.key
        await db[st.collection].insert_one(doc)
        inserted.append(doc["id"])
        if extra_warn or r["warnings"]:
            row_notes.append({"row": r["row_id"] + 2, "action": "disimpan",
                              "why": r["warnings"] + extra_warn, "id": doc["id"]})

    # F3 — jejak UNDO disimpan SEBELUM sesi ditandai selesai, supaya tombol
    # "Batalkan impor" pada Ekspor B/C benar-benar bisa memulihkan keadaan.
    if undo_rows:
        await db[UNDO].insert_many(undo_rows)

    await db[SESSIONS].update_one({"id": session_id}, {"$set": {
        "status": "committed",
        "committed_ids": inserted,
        "committed_count": len(inserted),
        "updated_count": updated,
        "skipped_duplicates": skipped,
        "rejected_count": rejected,
        "undo_count": len(undo_rows),
        "row_notes": row_notes[:1000],
        "committed_at": now,
        "committed_by": user.get("email", "system"),
        "updated_at": now,
    }})
    await log_activity(user.get("id", ""), user.get("name", ""),
                       f"Impor {st.label}: {len(inserted)} baris masuk, "
                       f"{updated} diperbarui, {skipped} duplikat, {rejected} ditolak",
                       "marketing-data-import", session_id)

    # F0.2 (2026-08-12) — EFEK SAMPING WAJIB, sama seperti entri manual.
    # Cacat yang ditemukan saat membuktikan F0: entri manual memanggil
    # `_recalculate_health_score`, sedangkan impor TIDAK — akibatnya toko yang
    # datanya masuk lewat impor punya `health_score = null` selamanya, dan layar
    # kesehatan menampilkan "N/A" padahal datanya lengkap.
    if account and st.key in ("sales_daily", "account_health", "reviews",
                              "returns", "complaints", "marketplace_orders"):
        try:
            from routes.marketing_shared import _recalculate_health_score
            await _recalculate_health_score(db, account["id"])
        except Exception:
            logger.exception("recalc health score setelah impor gagal (account=%s)",
                             account.get("id"))

    # ── F1 — INGAT susunan kolom berkas ini ──────────────────────────────────
    # Impor rutin harian memakai ekspor dengan susunan kolom yang sama. Setelah
    # commit berhasil, pemetaannya disimpan supaya impor berikutnya langsung siap
    # (tanpa AI, tanpa memetakan ulang) dan tidak pernah menebak diam-diam.
    if s.get("format_fingerprint"):
        try:
            await db[FORMATS].update_one(
                {"source_type": st.key, "fingerprint": s["format_fingerprint"]},
                {"$set": {"source_type": st.key,
                          "fingerprint": s["format_fingerprint"],
                          "headers": s.get("headers") or [],
                          "mapping": s.get("mapping") or [],
                          "platform": (account or {}).get("platform"),
                          "last_used_at": now,
                          "last_used_by": user.get("email", "system")},
                 "$inc": {"use_count": 1},
                 "$setOnInsert": {"created_at": now,
                                  "created_by": user.get("email", "system")}},
                upsert=True)
        except Exception:
            logger.exception("gagal menyimpan sidik format impor (sesi=%s)", session_id)

    # ── F2 — REKAP HARIAN TURUNAN dihitung ulang untuk tanggal yang terdampak ─
    rollup_result = None
    if st.key == "marketplace_orders" and (inserted or updated):
        try:
            from core import marketing_daily_rollup as rollup
            touched = set(await rollup.pairs_from_orders(
                db, {"_import_session_id": session_id}))
            rollup_result = await rollup.recompute_pairs(
                db, touched, actor=user.get("email", "system"))
            logger.info("[F2] rekap harian turunan: %s", {
                k: v for k, v in rollup_result.items() if k != "details"})
        except Exception:
            logger.exception("gagal menghitung rekap harian turunan (sesi=%s)", session_id)

    return {"ok": True, "session_id": session_id,
            "target_collection": st.collection,
            "inserted": len(inserted), "updated": updated,
            "skipped_duplicates": skipped, "rejected": rejected,
            # F3.D — layar hasil butuh DUA hal ini untuk bisa menjelaskan angka 0:
            # sifat jenis impor, dan banyaknya jejak pemulihan yang tersimpan.
            "update_only": st.update_only,
            "undo_count": len(undo_rows),
            "row_notes": row_notes[:200],
            "daily_rollup": ({k: v for k, v in rollup_result.items() if k != "details"}
                             if rollup_result else None),
            "message": _commit_message(st, len(inserted), updated, rejected)}


@router.post("/sessions/{session_id}/rollback")
async def rollback(session_id: str, request: Request):
    """Batalkan impor.

    Dua bentuk, karena ada dua bentuk impor:

    * impor yang MEMBUAT baris → hanya baris milik sesi ini yang dihapus;
    * impor ``update_only`` (F3, Ekspor B/C) → tidak ada baris untuk dihapus,
      jadi keadaan pesanan DIPULIHKAN dari jejak :data:`UNDO`
      (:func:`_restore_fulfillment_session`).

    Sebuah sesi bisa punya keduanya (mis. berkas campuran) dan laporannya
    menyebut angka masing-masing — bukan satu angka yang menyamarkan sisanya.
    """
    await require_auth(request)
    user = _user(request)
    db = get_db()
    s = await _load_session(db, session_id)
    # Urutan pemeriksaan ini PENTING. Versi lama memeriksa `status != committed`
    # lebih dulu, sehingga sesi yang SUDAH dibatalkan dijawab "Sesi ini belum
    # di-commit" — pesan yang menyesatkan pada satu-satunya saat staf paling
    # butuh kejelasan (ia baru saja menekan tombol yang sama dua kali).
    if s.get("rolled_back_at") or s.get("status") == "rolled_back":
        raise HTTPException(400, "Sesi ini sudah dibatalkan "
                                 f"({_ser(s.get('rolled_back_at'))} oleh "
                                 f"{s.get('rolled_back_by') or '-'}). Buka "
                                 "'Riwayat impor' untuk melihat laporan pemulihannya.")
    if s.get("status") != "committed":
        raise HTTPException(400, "Sesi ini belum di-commit")
    committed_at = s.get("committed_at")
    if isinstance(committed_at, datetime):
        ca = committed_at if committed_at.tzinfo else committed_at.replace(tzinfo=timezone.utc)
        if _now() - ca > timedelta(hours=ROLLBACK_HOURS):
            raise HTTPException(400, f"Rollback hanya bisa dalam {ROLLBACK_HOURS} jam "
                                     f"setelah commit")
    st = get_source_type(s["source_type"])
    ids = s.get("committed_ids") or []
    # F2 — tanggal terdampak dicatat SEBELUM dokumen dihapus, kalau tidak
    # rekap harian akan tetap memuat omzet dari pesanan yang sudah tidak ada.
    touched: set = set()
    if st.key == "marketplace_orders":
        try:
            from core import marketing_daily_rollup as rollup
            touched = set(await rollup.pairs_from_orders(
                db, {"id": {"$in": ids}, "_import_session_id": session_id}))
        except Exception:
            logger.exception("gagal mengumpulkan tanggal terdampak (sesi=%s)", session_id)
    res = await db[st.collection].delete_many({"id": {"$in": ids},
                                               "_import_session_id": session_id})
    # F3 — PEMULIHAN keadaan pesanan untuk impor yang hanya memperbarui.
    restore = await _restore_fulfillment_session(db, s, st, user)
    rolled = None
    if touched:
        try:
            from core import marketing_daily_rollup as rollup
            rolled = await rollup.recompute_pairs(db, touched,
                                                  actor=user.get("email", "system"))
            logger.info("[F2] rekap harian sesudah rollback: %s",
                        {k: v for k, v in rolled.items() if k != "details"})
        except Exception:
            logger.exception("gagal menghitung ulang rekap harian sesudah rollback")
    await db[SESSIONS].update_one({"id": session_id}, {"$set": {
        "status": "rolled_back", "rolled_back_at": _now(),
        "rolled_back_by": user.get("email", "system"),
        "rolled_back_count": res.deleted_count,
        # F3 — angka pemulihan disimpan di sesi supaya Riwayat Impor bisa
        # menampilkan hasilnya lagi besok (bukan hanya sekali lewat toast).
        "restored_count": restore["restored"],
        "restore_status_count": restore["status_restored"],
        "restore_fields_only": restore["fields_only"],
        "restore_missing": restore["missing"],
        "restore_notes": restore["notes"][:1000],
        "updated_at": _now()}})
    parts = []
    if res.deleted_count:
        parts.append(f"{res.deleted_count} baris hasil impor dihapus")
    if restore["restored"]:
        parts.append(f"{restore['restored']} baris dipulihkan ke keadaan sebelum impor")
    if restore["fields_only"]:
        parts.append(f"{restore['fields_only']} pesanan HANYA field-nya yang bisa "
                     "dipulihkan (statusnya sudah batal/retur — lihat rincian)")
    if restore["missing"]:
        parts.append(f"{restore['missing']} pesanan sudah tidak ada")
    if not parts:
        parts.append("tidak ada yang perlu dibatalkan (sesi ini tidak membuat "
                     "maupun mengubah baris)")
    await log_activity(user.get("id", ""), user.get("name", ""),
                       f"Rollback impor {st.label}: " + " · ".join(parts),
                       "marketing-data-import", session_id)
    return {"ok": True, "deleted": res.deleted_count,
            "restore": restore,
            "daily_rollup": ({k: v for k, v in rolled.items() if k != "details"}
                             if rolled else None),
            "message": " · ".join(parts)}


@router.get("/sessions/{session_id}/undo-report")
async def undo_report(session_id: str, request: Request):
    """F3 — apa yang BISA & SUDAH dipulihkan dari sesi impor ini.

    Dipakai layar Riwayat Impor supaya tombol "Batalkan impor" tidak menjanjikan
    yang tidak bisa ditepati, dan supaya hasil pembatalan tetap bisa dibaca lagi
    besok (bukan hanya sekali lewat toast). Sengaja TIDAK membaca ulang berkas
    aslinya (`_reparse`) — laporan ini harus tetap terbuka walau berkasnya sudah
    dibersihkan penjadwal.
    """
    await require_auth(request)
    db = get_db()
    s = await _load_session(db, session_id)
    st = get_source_type(s["source_type"])
    pending = await db[UNDO].count_documents({"session_id": session_id,
                                              "restored_at": None})
    done = await db[UNDO].count_documents({"session_id": session_id,
                                           "restored_at": {"$ne": None}})
    sample = await db[UNDO].find(
        {"session_id": session_id},
        {"_id": 0, "order_ref": 1, "status_before": 1, "restored_at": 1}
    ).limit(200).to_list(200)
    return {"ok": True, "session_id": session_id,
            "source_type": st.key, "source_label": st.label,
            "update_only": st.update_only,
            "status": s.get("status"),
            "committed_count": s.get("committed_count") or 0,
            "updated_count": s.get("updated_count") or 0,
            "undo_count": s.get("undo_count") or 0,
            "undo_pending": pending, "undo_restored": done,
            "restored_count": s.get("restored_count") or 0,
            "restore_status_count": s.get("restore_status_count") or 0,
            "restore_fields_only": s.get("restore_fields_only") or 0,
            "restore_missing": s.get("restore_missing") or 0,
            "restore_notes": _ser(s.get("restore_notes") or []),
            "rolled_back_at": _ser(s.get("rolled_back_at")),
            "rolled_back_by": s.get("rolled_back_by"),
            "trail": _ser(sample)}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    s = await _load_session(db, session_id)
    if s.get("status") == "committed":
        raise HTTPException(400, "Sesi yang sudah di-commit tidak boleh dihapus "
                                 "(jejak impor harus bisa ditelusuri). Pakai rollback.")
    path = s.get("file_path")
    if path and os.path.isabs(path) and os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            logger.warning("gagal menghapus berkas sesi %s: %s", session_id, e)
    # berkas di object storage tidak punya API hapus — referensinya cukup dilepas bersama sesi
    await db[SESSIONS].delete_one({"id": session_id})
    return {"ok": True}


@router.get("/history")
async def history(request: Request, page: int = Query(1, ge=1),
                  page_size: int = Query(20, ge=1, le=100)):
    user = await require_auth(request)
    db = get_db()
    # F6 (sesi #10) — riwayat impor berlingkup toko: dari baris riwayat ada tombol
    # "Batalkan & pulihkan", jadi riwayat toko orang lain = jalan pintas mengubah
    # data toko orang lain.
    q = await scope.scope_filter(
        db, user, {"status": {"$in": ["committed", "rolled_back"]}})
    total = await db[SESSIONS].count_documents(q)
    docs = await db[SESSIONS].find(
        q, {"_id": 0, "mapping": 0, "row_notes": 0, "restore_notes": 0}).sort(
        "committed_at", -1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    return {"ok": True, "history": _ser(docs),
            "pagination": {"total": total, "page": page, "page_size": page_size}}
