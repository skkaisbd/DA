"""marketing_settlements — **F9: PENCAIRAN (SETTLEMENT) MARKETPLACE** (input MANUAL).

═══════════════════════════════════════════════════════════════════════════════
KENAPA INPUT MANUAL, BUKAN IMPOR BERKAS — DAN KENAPA ITU JUSTRU LEBIH AMAN
═══════════════════════════════════════════════════════════════════════════════
Rencana asli F9 adalah mengimpor berkas laporan pencairan Shopee/TikTok. Aturan
proyek ini (blokir data **BD-2**) melarangnya sampai ada contoh berkas ASLI:

    "1 contoh laporan Pencairan/Settlement TikTok dan Shopee — F9 tidak boleh
     dimulai; pemetaan kolom uang TIDAK BOLEH DITEBAK."

Larangan itu masuk akal. Modul ini menghitung `net_payout`, komisi platform,
potongan iklan, dan refund — lalu **membuat jurnal akuntansi**. Kalau kolom
ditebak (mis. "Total" dianggap omzet padahal artinya omzet setelah potongan),
angkanya akan terlihat rapi tetapi SALAH, dan salahnya masuk buku besar tanpa
satu pun galat.

Keputusan pemilik (2026-08-14): **"settlement pencairan sementara dibuatkan
manual input dulu"**. Itu menghapus blokirnya sepenuhnya, bukan menghindarinya:
kalau staf mengisi field yang NAMANYA JELAS satu per satu, tidak ada kolom yang
perlu ditebak siapa pun. Saat berkas asli tersedia nanti, impor bisa ditambahkan
di atas struktur yang sudah terbukti ini.

═══════════════════════════════════════════════════════════════════════════════
TIGA ATURAN YANG MEMBUAT ANGKA DI SINI BISA DIPERCAYA
═══════════════════════════════════════════════════════════════════════════════
1. **`net_payout` TIDAK PERNAH DIHITUNG SERVER — ia DIISI STAF dari mutasi bank
   / laporan platform.** Server justru menghitung *nilai yang seharusnya* lalu
   menampilkan **SELISIH**-nya. Ini kebalikan dari kebiasaan umum, dan
   sengaja: kalau server yang menghitung net, maka setiap potongan yang belum
   kita kenal akan HILANG diam-diam (angkanya tetap "cocok" karena kita sendiri
   yang membuatnya cocok). Dengan cara ini, potongan tak dikenal muncul sebagai
   selisih — dan selisih adalah satu-satunya petunjuk bahwa ada biaya yang
   belum kita catat.

2. **Selisih ≠ 0 ⇒ TIDAK BOLEH jadi jurnal.** Jurnal dari angka yang belum
   seimbang mustahil seimbang (Σ debit ≠ Σ kredit). Staf harus MENAMAI dulu
   selisihnya di `other_deductions` atau `adjustments` (dengan catatan). Jadi
   penolakan ini bukan birokrasi: ia memaksa biaya tak dikenal punya NAMA.

3. **Jurnalnya DRAFT.** Angka datang dari pihak luar; Keuangan yang memutuskan
   ia masuk buku besar (`POST /api/rahaza/journals/{je_id}/post`, endpoint yang
   sudah ada). Idempoten lewat `source_module` + `source_ref` ⇒ menekan tombol
   dua kali tidak melahirkan dua jurnal.

Kolom mengikuti spesifikasi F9.1 (`RENCANA_EKSEKUSI_MASTER` §F9), dan dedupe
`(platform, account_id, settlement_id)` mencegah satu pencairan tercatat dua kali.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from auth import require_auth
from core import marketing_account_scope as _scope
from core import settlement_import as _simport
from database import get_db
from routes.shared import require_portal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/settlements", tags=["marketing-settlements"])

COLL = "marketing_settlements"
SOURCE_MODULE = "marketplace_settlement"

# Status pesanan yang TIDAK ikut dihitung sebagai omzet periode saat
# rekonsiliasi: pesanan batal memang tidak pernah dicairkan platform.
CANCELLED_STATUSES = ("cancelled", "canceled")


async def _require_finance(request: Request) -> dict:
    """Sesi #37 — keputusan pemilik: **form pencairan milik Portal FINANCE.**

    Marketing tetap boleh MELIHAT (GET memakai `require_auth` + lingkup toko),
    tetapi mencatat/mengubah/menjurnal pencairan hanya boleh Finance. Tanpa
    pagar ini, layar Marketing yang "baca-saja" hanya baca-saja karena UI-nya
    tidak menyediakan tombol — endpoint-nya sendiri tetap terbuka bagi siapa
    pun yang bisa login.
    """
    return await require_portal(request, "finance")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ser(d: dict) -> dict:
    out = {}
    for k, v in (d or {}).items():
        if k == "_id":
            continue
        out[k] = v.isoformat() if isinstance(v, datetime) else v
    return out


# ── Peta akun (COA) — DITULIS DI SATU TEMPAT ────────────────────────────────
# Kalau setiap endpoint memilih akunnya sendiri, suatu hari salah satunya
# memakai akun berbeda dan laporan L/R berubah tanpa ada yang mengubah aturan.
COA = {
    "cash":        "1-1201",  # Bank BCA — uang yang benar-benar masuk
    "revenue":     "4-1100",  # Penjualan Garment (bruto)
    "returns":     "4-1200",  # Retur Penjualan (kontra-pendapatan)
    "discount":    "4-1300",  # Diskon Penjualan (kontra-pendapatan)
    "platform_fee": "4-141",  # Potongan Platform (Fee Shopee/TikTok)
    "ads":         "6-1100",  # Biaya Iklan & Promosi
    "other":       "7-4000",  # Pendapatan/Beban Lain-Lain
}

# Field uang + arahnya terhadap `net_payout`. Satu daftar ini dipakai oleh
# perhitungan selisih DAN pembuat jurnal, jadi keduanya mustahil berbeda.
MONEY_FIELDS = {
    "gross_sales":          +1,
    "refunds":              -1,
    "seller_discount":      -1,
    "shipping_subsidy":     +1,
    "platform_commission":  -1,
    "platform_service_fee": -1,
    "affiliate_commission": -1,
    "ads_deduction":        -1,
    "other_deductions":     -1,
    "adjustments":          +1,   # boleh negatif (koreksi platform)
}


class SettlementIn(BaseModel):
    account_id: str
    platform: str
    settlement_id: str = Field(min_length=1)
    settlement_date: str                 # YYYY-MM-DD — tanggal uang masuk
    period_from: Optional[str] = None
    period_to: Optional[str] = None

    gross_sales: float = Field(default=0, ge=0)
    refunds: float = Field(default=0, ge=0)
    seller_discount: float = Field(default=0, ge=0)
    shipping_subsidy: float = Field(default=0, ge=0)
    platform_commission: float = Field(default=0, ge=0)
    platform_service_fee: float = Field(default=0, ge=0)
    affiliate_commission: float = Field(default=0, ge=0)
    ads_deduction: float = Field(default=0, ge=0)
    other_deductions: float = Field(default=0, ge=0)
    # `adjustments` SENGAJA tanpa `ge=0`: koreksi platform bisa mengurangi.
    adjustments: float = 0
    # Diisi staf dari mutasi bank / laporan platform — BUKAN dihitung server.
    net_payout: float = Field(default=0, ge=0)
    notes: Optional[str] = ""
    other_deductions_note: Optional[str] = ""


def _expected_net(doc: dict) -> float:
    return round(sum(sign * float(doc.get(f) or 0)
                     for f, sign in MONEY_FIELDS.items()), 2)


# ── COA PER AKUN TOKO — sumber yang benar, global hanya untuk POTONGAN ───────
# JEBAKAN yang diperingatkan pemilik (sesi #37): ada DUA sumber akun di repo ini.
#   1. `COA` global di berkas ini (satu peta untuk semua toko)
#   2. `coa_revenue_code` / `coa_cash_code` / `coa_receivable_code` per akun toko
#      di `routes/marketing_accounts.py` — DIBUAT & DIVALIDASI saat toko dibuat.
# Kalau jurnal pencairan memakai peta global, uang dari SEMUA toko jatuh ke satu
# rekening `1-1201` dan satu akun penjualan `4-1100`; laporan per toko yang
# sudah dibangun di Portal Marketing jadi mustahil dipertanggungjawabkan —
# tanpa satu pun galat. Karena itu: kas & pendapatan WAJIB dari akun toko, dan
# kalau toko belum punya, permintaan DITOLAK dengan pesan yang bisa ditindak.
#
# Akun POTONGAN (retur, diskon, fee platform, iklan, lain-lain) tetap dari peta
# global karena memang tidak per toko — dan itu ditulis di respons agar terlihat.
ACCOUNT_COA_ROLES = {
    "cash": ("coa_cash_code", "Rekening Pencairan"),
    "revenue": ("coa_revenue_code", "Akun Pendapatan"),
}


async def _resolve_coa(db, account: dict) -> dict:
    """Peta akun EFEKTIF untuk satu pencairan. Melempar 400 bila toko belum
    punya akun kas/pendapatan sendiri — TIDAK diam-diam memakai `1-1201`."""
    eff = dict(COA)
    sources = {k: "global" for k in COA}
    missing = []
    for role, (field, label) in ACCOUNT_COA_ROLES.items():
        code = (account.get(field) or "").strip()
        if not code:
            missing.append(f"{label} (`{field}`)")
            continue
        acc = await db.rahaza_coa_accounts.find_one(
            {"code": code}, {"_id": 0, "code": 1, "name": 1, "is_group": 1, "active": 1})
        if not acc or acc.get("is_group") or not acc.get("active", True):
            missing.append(f"{label} (`{field}` = {code} tidak ada/tidak aktif/akun induk)")
            continue
        eff[role] = code
        sources[role] = "account"
    if missing:
        raise HTTPException(
            400,
            f"Toko '{account.get('account_name') or account.get('id')}' belum punya "
            f"tautan akun (COA) yang sah: {'; '.join(missing)}. Isi dulu di Portal "
            f"Marketing → Manajemen Akun (bagian Tautan Finance). Jurnal pencairan "
            f"TIDAK dibuat dengan akun bawaan, karena uang dari toko yang berbeda "
            f"akan jatuh ke rekening yang sama dan laporan per toko jadi tidak bisa "
            f"dipertanggungjawabkan.")
    return {"codes": eff, "sources": sources}


def _with_math(doc: dict) -> dict:
    """Tambahkan hasil pemeriksaan aritmetika — SELALU, bukan hanya saat gagal."""
    expected = _expected_net(doc)
    actual = round(float(doc.get("net_payout") or 0), 2)
    diff = round(actual - expected, 2)
    doc["expected_net_payout"] = expected
    doc["net_payout_diff"] = diff
    doc["math_verified"] = abs(diff) < 0.01
    total_ded = round(
        sum(float(doc.get(f) or 0) for f, s in MONEY_FIELDS.items() if s < 0), 2)
    doc["total_deductions"] = total_ded
    gross = float(doc.get("gross_sales") or 0)
    # Berapa persen omzet bruto yang dipotong platform — angka yang paling sering
    # ditanyakan pemilik dan paling jarang bisa dijawab.
    doc["deduction_pct"] = round(total_ded / gross * 100, 2) if gross else 0.0
    return doc


@router.get("/coa-map")
async def coa_map(request: Request):
    """Peta akun yang dipakai jurnal — DITAMPILKAN di layar, bukan disembunyikan.

    Kalau peta akun hanya ada di kode, orang yang membaca laporan tidak bisa
    memeriksa apakah potongan platform masuk ke akun yang benar.
    """
    await require_auth(request)
    db = get_db()
    out = []
    for role, code in COA.items():
        acc = await db.rahaza_coa_accounts.find_one(
            {"code": code}, {"_id": 0, "code": 1, "name": 1, "type": 1, "active": 1})
        out.append({"role": role, "code": code,
                    "name": (acc or {}).get("name"),
                    "type": (acc or {}).get("type"),
                    "found": bool(acc and acc.get("active"))})
    return {"ok": True, "coa": out,
            "missing": [o["code"] for o in out if not o["found"]]}

MAPS_COLL = "marketing_settlement_import_maps"


class ImportMappingIn(BaseModel):
    account_id: str
    headers: List[str]
    mapping: dict                      # field -> [kolom]
    meta_columns: Optional[dict] = None
    filename: Optional[str] = ""


@router.post("/import/preview")
async def import_preview(request: Request, file: UploadFile = File(...),
                         account_id: str = Form(default="")):
    """Baca laporan pencairan Shopee/TikTok → DRAF angka form. TIDAK menyimpan apa pun.

    Aturan BD-2: pemetaan kolom tidak boleh ditebak diam-diam — respons menyebut kolom
    sumber tiap field dan kolom angka yang TIDAK terpetakan, lalu staf memeriksa di form.
    Bila toko ini pernah MENGONFIRMASI pemetaan untuk format header yang sama, pemetaan
    itu dipakai (`mapping_source: saved`) — tebakan hanya untuk format yang belum dikenal.
    """
    await _require_finance(request)
    db = get_db()
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Berkas kosong.")
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(413, "Berkas melebihi 15 MB.")
    fname = file.filename or "laporan.csv"
    if not fname.lower().endswith((".csv", ".xlsx", ".xls", ".xlsm", ".tsv", ".txt")):
        raise HTTPException(415, "Hanya CSV atau Excel (.xlsx) yang didukung.")

    async def _parse(saved=None):
        try:
            return _simport.parse_settlement_report(raw, fname, saved_mapping=saved)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001
            logger.warning("import pencairan gagal dibaca: %s", e)
            raise HTTPException(400, f"Berkas tidak bisa dibaca: {e}")

    parsed = await _parse()
    saved_doc = None
    if account_id:
        saved_doc = await db[MAPS_COLL].find_one(
            {"account_id": account_id, "fingerprint": parsed["fingerprint"]}, {"_id": 0})
        if saved_doc:
            parsed = await _parse(saved_doc.get("mapping") or {})
    parsed["platform_guess"] = _simport.guess_platform(parsed["headers"])
    parsed["saved_mapping"] = _ser(saved_doc) if saved_doc else None
    draft = dict(parsed["values"])
    draft["expected_net_payout"] = round(sum(sign * float(draft.get(f) or 0)
                                             for f, sign in MONEY_FIELDS.items()), 2)
    if not parsed["mapping"]:
        raise HTTPException(
            400, "Tidak ada satu pun kolom uang yang dikenali di berkas ini. Pastikan yang "
                 "diunggah adalah laporan Penghasilan (Shopee) / Settlement (TikTok), bukan "
                 "ekspor pesanan.")
    return {"ok": True, **parsed, "draft": draft}


@router.post("/import/mapping")
async def save_import_mapping(body: ImportMappingIn, request: Request):
    """Simpan pemetaan kolom yang DIKONFIRMASI staf untuk (toko, sidik format header)."""
    user = await _require_finance(request)
    db = get_db()
    await _scope.require_account(db, body.account_id)
    valid_fields = set(_simport.FIELD_KEYWORDS)
    mapping = {f: [str(c) for c in cols] for f, cols in (body.mapping or {}).items()
               if f in valid_fields and cols}
    if not mapping:
        raise HTTPException(400, "Pemetaan kosong — minimal satu kolom harus dipetakan.")
    fp = _simport._fingerprint(body.headers)
    now = _now()
    doc = {
        "account_id": body.account_id, "fingerprint": fp, "headers": body.headers,
        "mapping": mapping, "meta_columns": body.meta_columns or {},
        "filename": body.filename or "", "updated_at": now,
        "updated_by": user.get("email") if isinstance(user, dict) else None,
    }
    res = await db[MAPS_COLL].update_one(
        {"account_id": body.account_id, "fingerprint": fp},
        {"$set": doc, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now}}, upsert=True)
    saved = await db[MAPS_COLL].find_one({"account_id": body.account_id, "fingerprint": fp}, {"_id": 0})
    return {"ok": True, "created": bool(res.upserted_id), "data": _ser(saved)}


@router.get("/import/mapping")
async def list_import_mappings(request: Request, account_id: str = Query(default="")):
    await require_auth(request)
    db = get_db()
    q = {"account_id": account_id} if account_id else {}
    rows = await db[MAPS_COLL].find(q, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return {"ok": True, "data": [_ser(r) for r in rows]}


@router.delete("/import/mapping/{map_id}")
async def delete_import_mapping(map_id: str, request: Request):
    await _require_finance(request)
    db = get_db()
    res = await db[MAPS_COLL].delete_one({"id": map_id})
    if not res.deleted_count:
        raise HTTPException(404, "Pemetaan tidak ditemukan.")
    return {"ok": True}


@router.get("/by-account")
async def summary_by_account(request: Request, month: str = Query(default="")):
    """Ringkasan per toko untuk satu bulan (YYYY-MM) — bandingkan % potongan antar toko."""
    user = await require_auth(request)
    db = get_db()
    q: dict = {}
    vis = await _scope.visible_account_ids(db, user)
    if vis is not None:
        q["account_id"] = {"$in": vis}

    months_raw = await db[COLL].aggregate([
        {"$match": q},
        {"$group": {"_id": {"$substr": ["$settlement_date", 0, 7]}}},
        {"$sort": {"_id": -1}},
    ]).to_list(60)
    months = [m["_id"] for m in months_raw if m.get("_id")]
    if month and not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(400, "Format bulan harus YYYY-MM")
    month = month or (months[0] if months else date.today().strftime("%Y-%m"))

    rows = await db[COLL].aggregate([
        {"$match": {**q, "settlement_date": {"$regex": f"^{month}"}}},
        {"$group": {"_id": "$account_id",
                    "platform": {"$first": "$platform"},
                    "count": {"$sum": 1},
                    "gross": {"$sum": "$gross_sales"},
                    "net": {"$sum": "$net_payout"},
                    "ded": {"$sum": "$total_deductions"},
                    "refunds": {"$sum": "$refunds"},
                    "ads": {"$sum": "$ads_deduction"},
                    "commission": {"$sum": {"$add": ["$platform_commission", "$platform_service_fee"]}},
                    "unverified": {"$sum": {"$cond": [{"$eq": ["$math_verified", False]}, 1, 0]}}}},
    ]).to_list(200)
    acc_ids = [r["_id"] for r in rows]
    accounts = {a["id"]: a for a in await db.marketing_platform_accounts.find(
        {"id": {"$in": acc_ids}}, {"_id": 0, "id": 1, "account_name": 1, "platform": 1}).to_list(200)}
    out = []
    for r in rows:
        gross = float(r.get("gross") or 0)
        ded = float(r.get("ded") or 0)
        out.append({
            "account_id": r["_id"],
            "account_name": accounts.get(r["_id"], {}).get("account_name") or r["_id"],
            "platform": accounts.get(r["_id"], {}).get("platform") or r.get("platform"),
            "count": r["count"],
            "gross_sales": round(gross, 2),
            "net_payout": round(float(r.get("net") or 0), 2),
            "total_deductions": round(ded, 2),
            "deduction_pct": round(ded / gross * 100, 2) if gross else 0.0,
            "commission_pct": round(float(r.get("commission") or 0) / gross * 100, 2) if gross else 0.0,
            "ads_pct": round(float(r.get("ads") or 0) / gross * 100, 2) if gross else 0.0,
            "refund_pct": round(float(r.get("refunds") or 0) / gross * 100, 2) if gross else 0.0,
            "unverified_count": r.get("unverified", 0),
        })
    out.sort(key=lambda x: -x["deduction_pct"])
    tot_gross = sum(o["gross_sales"] for o in out)
    tot_ded = sum(o["total_deductions"] for o in out)
    return {"ok": True, "month": month, "months": months, "data": out,
            "average_deduction_pct": round(tot_ded / tot_gross * 100, 2) if tot_gross else 0.0}




@router.get("")
async def list_settlements(
    request: Request,
    account_id: str = Query(default=""),
    platform: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, le=200),
    # Pelajaran Fase B: pengurutan dikerjakan SERVER supaya "pencairan terbesar"
    # berlaku untuk SELURUH data, bukan halaman yang kebetulan terbuka.
    sort_by: str = Query(default="settlement_date"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
):
    user = await require_auth(request)
    db = get_db()

    q: dict = {}
    vis = await _scope.visible_account_ids(db, user)
    if vis is not None:
        q["account_id"] = {"$in": vis}
    if account_id:
        q["account_id"] = account_id
    if platform:
        q["platform"] = platform
    if date_from:
        q.setdefault("settlement_date", {})["$gte"] = date_from
    if date_to:
        q.setdefault("settlement_date", {})["$lte"] = date_to
    if search:
        q["settlement_id"] = {"$regex": search, "$options": "i"}

    SORTABLE = {"settlement_date", "settlement_id", "platform", "gross_sales",
                "net_payout", "total_deductions", "deduction_pct", "created_at"}
    key = sort_by if sort_by in SORTABLE else "settlement_date"
    direction = -1 if sort_dir == "desc" else 1

    total = await db[COLL].count_documents(q)
    rows = await db[COLL].find(q, {"_id": 0}).sort(key, direction) \
        .skip((page - 1) * page_size).limit(page_size).to_list(page_size)

    # Ringkasan dihitung atas SELURUH data yang cocok (bukan halaman) — kalau
    # dihitung dari halaman, "total pencairan" akan berubah saat orang pindah
    # halaman dan tidak ada yang tahu angka mana yang benar.
    agg = await db[COLL].aggregate([
        {"$match": q},
        {"$group": {"_id": None,
                    "gross": {"$sum": "$gross_sales"},
                    "net": {"$sum": "$net_payout"},
                    "ded": {"$sum": "$total_deductions"}}},
    ]).to_list(1)
    s = agg[0] if agg else {}
    unverified = await db[COLL].count_documents({**q, "math_verified": False})
    bank_linked = await db[COLL].count_documents({**q, "bank_txn_id": {"$nin": [None, ""]}})

    return {
        "ok": True,
        "data": [_ser(r) for r in rows],
        "summary": {
            "gross_sales": round(float(s.get("gross") or 0), 2),
            "net_payout": round(float(s.get("net") or 0), 2),
            "total_deductions": round(float(s.get("ded") or 0), 2),
            "deduction_pct": round(float(s.get("ded") or 0) / float(s["gross"]) * 100, 2)
            if s.get("gross") else 0.0,
            "unverified_count": unverified,
            "bank_linked_count": bank_linked,
            "bank_unlinked_count": total - bank_linked,
        },
        "pagination": {"total": total, "page": page, "page_size": page_size,
                       "total_pages": max(1, (total + page_size - 1) // page_size)},
    }


@router.post("")
async def create_settlement(body: SettlementIn, request: Request):
    user = await _require_finance(request)
    db = get_db()
    account = await _scope.require_account(db, body.account_id)

    # Kunci duplikat = (toko, nomor pencairan). SENGAJA TANPA `platform`:
    # `_scope.stamp_account()` menimpa `platform` dengan platform milik toko,
    # sehingga nilai yang DICARI (kiriman browser) bisa berbeda dari yang
    # TERSIMPAN — dan pencarian duplikatnya jadi tidak pernah cocok. Terbukti:
    # nomor pencairan yang sama bisa masuk dua kali (HTTP 200 dua-duanya).
    # Platform juga redundan di sini: satu toko hanya ada di satu platform.
    dup = await db[COLL].find_one({
        "account_id": body.account_id, "settlement_id": body.settlement_id,
    }, {"_id": 0, "id": 1, "settlement_date": 1})
    if dup:
        raise HTTPException(
            409, f"Pencairan '{body.settlement_id}' untuk toko ini sudah pernah "
                 f"dicatat (tanggal {dup.get('settlement_date')}). Satu pencairan "
                 f"yang tercatat dua kali akan menggandakan pendapatan.")

    doc = body.dict()
    doc.update({
        "id": str(uuid.uuid4()),
        "je_id": None, "je_number": None, "je_status": None,
        "created_by": (getattr(request.state, "user", {}) or {}).get("email", "unknown"),
        "created_at": _now(), "updated_at": _now(),
    })
    _scope.stamp_account(doc, account)
    _with_math(doc)
    await db[COLL].insert_one(doc)
    return {"ok": True, "data": _ser(doc)}


async def _je_still_binding(db, doc: dict) -> bool:
    """Apakah jurnal pencairan ini masih MENGIKAT angka sumbernya?

    SESI #40 — jurnal yang sudah **void** tidak mengikat apa pun: nilainya sudah
    dikeluarkan dari buku besar. Sebelum ini pemeriksaannya hanya melihat ADA/TIDAK
    `je_id`, sehingga pesan "void jurnalnya dulu" mengarah ke jalan buntu —
    pencairan salah-input tidak bisa diperbaiki maupun dihapus selamanya.
    """
    je_id = doc.get("je_id")
    if not je_id:
        return False
    je = await db.rahaza_journal_entries.find_one({"id": je_id}, {"_id": 0, "status": 1})
    if not je:
        return False          # jurnalnya sudah tidak ada (draft dihapus Finance)
    return je.get("status") != "voided"


@router.put("/{sid}")
async def update_settlement(sid: str, body: SettlementIn, request: Request):
    await _require_finance(request)
    db = get_db()
    cur = await db[COLL].find_one({"id": sid}, {"_id": 0})
    if not cur:
        raise HTTPException(404, "Pencairan tidak ditemukan.")
    # Sudah ada jurnal ⇒ angkanya sudah dipakai akuntansi. Mengubahnya diam-diam
    # akan membuat jurnal dan sumbernya bercerita hal berbeda.
    # SESI #40 — jurnal yang SUDAH DI-VOID tidak lagi mengikat: pesan penolakan di
    # bawah menyuruh "void dulu", tetapi sebelum ini void tidak membuka apa pun
    # sehingga pencairan salah-input terkunci selamanya (tidak bisa diperbaiki
    # maupun dihapus). Tautan jurnalnya dilepas supaya jejaknya tetap jelas.
    if await _je_still_binding(db, cur):
        raise HTTPException(
            400, f"Pencairan ini sudah punya jurnal ({cur.get('je_number')}). "
                 f"Batalkan/void jurnalnya dulu di Portal Finance sebelum "
                 f"mengubah angkanya — kalau tidak, jurnal dan sumbernya akan "
                 f"menyebut angka yang berbeda.")
    upd = body.dict()
    if cur.get("bank_txn_id") and round(float(upd.get("net_payout") or 0), 2) != round(float(cur.get("net_payout") or 0), 2):
        locked = f"Rp {float(cur.get('net_payout') or 0):,.0f}".replace(",", ".")
        raise HTTPException(
            400, f"Nominal dicairkan sudah TERTAUT ke mutasi bank tanggal {cur.get('bank_txn_date')} "
                 f"({locked}). Lepas tautannya di Rekonsiliasi Bank dulu bila memang mutasinya yang salah.")
    if cur.get("je_id"):
        upd.update({"je_id": None, "je_number": None, "je_status": None,
                    "je_voided_ref": cur.get("je_number")})
    upd["updated_at"] = _now()
    merged = {**cur, **upd}
    _with_math(merged)
    upd.update({k: merged[k] for k in
                ("expected_net_payout", "net_payout_diff", "math_verified",
                 "total_deductions", "deduction_pct")})
    await db[COLL].update_one({"id": sid}, {"$set": upd})
    return {"ok": True, "data": _ser({**cur, **upd})}


@router.delete("/{sid}")
async def delete_settlement(sid: str, request: Request):
    await _require_finance(request)
    db = get_db()
    cur = await db[COLL].find_one({"id": sid}, {"_id": 0})
    if not cur:
        raise HTTPException(404, "Pencairan tidak ditemukan.")
    if await _je_still_binding(db, cur):
        raise HTTPException(
            400, f"Tidak bisa dihapus: sudah terbit jurnal {cur.get('je_number')}. "
                 f"Void jurnalnya dulu di Portal Finance.")
    if cur.get("bank_txn_id"):
        raise HTTPException(
            400, f"Tidak bisa dihapus: sudah tertaut ke mutasi bank tanggal {cur.get('bank_txn_date')}. "
                 f"Lepas tautannya di Rekonsiliasi Bank dulu.")
    await db[COLL].delete_one({"id": sid})
    return {"ok": True}


@router.post("/{sid}/journal")
async def create_draft_journal(sid: str, request: Request):
    """Buat jurnal **DRAFT** dari satu pencairan. Idempoten.

    SESI #37 — akun kas & pendapatan diambil dari **akun toko** (`coa_cash_code`,
    `coa_revenue_code`); peta global hanya dipakai untuk akun POTONGAN yang
    memang tidak per toko. Toko tanpa tautan akun ⇒ 400, bukan diam-diam
    memakai `1-1201`.

    Jurnal HANYA lahir dari PENCAIRAN. Tidak ada satu pun jalur di modul
    Marketing (pesanan, impor omzet, KPI) yang memposting penjualan ke GL —
    itu keputusan pemilik dan dijaga gate INV-F42.
    """
    user = await _require_finance(request)
    db = get_db()
    doc = await db[COLL].find_one({"id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Pencairan tidak ditemukan.")
    _with_math(doc)
    account = await _scope.require_account(db, doc.get("account_id"))
    coa = await _resolve_coa(db, account)
    ACC = coa["codes"]

    # ── Aturan 2: selisih harus BERNAMA dulu ──────────────────────────────────
    if not doc["math_verified"]:
        # Angka diformat SENDIRI-SENDIRI. Versi pertama memformat seluruh
        # kalimat dengan `.replace(",", ".")` dan itu ikut mengubah koma
        # kalimatnya ("…punya NAMA, bukan hilang" → "NAMA. bukan hilang").
        # Pesan yang rusak tata bahasanya membuat orang menduga sistemnya rusak.
        def _rp(v: float) -> str:
            return f"Rp {v:,.0f}".replace(",", ".")

        raise HTTPException(
            400,
            f"Angka belum seimbang: net payout yang diisi "
            f"{_rp(doc['net_payout'])} sedangkan hasil hitung dari rinciannya "
            f"{_rp(doc['expected_net_payout'])} (selisih "
            f"{_rp(doc['net_payout_diff'])}). Jurnal dari angka yang belum "
            f"seimbang MUSTAHIL seimbang. Catat dulu selisihnya sebagai "
            f"'Potongan lain' atau 'Penyesuaian' beserta keterangannya — supaya "
            f"biaya yang belum dikenal punya NAMA, bukan hilang.")

    from routes.rahaza_posting import _create_posted_je, _find_existing_je

    existing = await _find_existing_je(db, SOURCE_MODULE, doc["settlement_id"])
    if existing:
        await db[COLL].update_one({"id": sid}, {"$set": {
            "je_id": existing["id"], "je_number": existing["je_number"],
            "je_status": existing["status"], "updated_at": _now()}})
        return {"ok": True, "already": True, "je_number": existing["je_number"],
                "je_status": existing["status"],
                "message": f"Pencairan ini sudah punya jurnal "
                           f"{existing['je_number']} ({existing['status']}) — "
                           f"tidak dibuat dua kali."}

    g = lambda f: round(float(doc.get(f) or 0), 2)  # noqa: E731
    fee_total = g("platform_commission") + g("platform_service_fee") \
        + g("affiliate_commission")
    adj = g("adjustments")

    lines = [
        # Uang yang benar-benar masuk rekening — rekening MILIK TOKO ini
        {"account_code": ACC["cash"], "debit": g("net_payout"), "credit": 0,
         "description": f"Pencairan {doc['platform']} {doc['settlement_id']}"},
        # Pendapatan BRUTO — bukan angka bersih. Kalau yang dicatat angka bersih,
        # potongan platform tidak pernah terlihat sebagai biaya.
        {"account_code": ACC["revenue"], "debit": 0, "credit": g("gross_sales"),
         "description": "Penjualan bruto marketplace"},
        {"account_code": ACC["returns"], "debit": g("refunds"), "credit": 0,
         "description": "Refund / retur"},
        {"account_code": ACC["discount"], "debit": g("seller_discount"), "credit": 0,
         "description": "Diskon penjual"},
        {"account_code": ACC["other"], "debit": 0, "credit": g("shipping_subsidy"),
         "description": "Subsidi ongkir platform"},
        {"account_code": ACC["platform_fee"], "debit": fee_total, "credit": 0,
         "description": "Komisi + fee layanan + komisi afiliasi"},
        {"account_code": ACC["ads"], "debit": g("ads_deduction"), "credit": 0,
         "description": "Biaya iklan dipotong dari pencairan"},
        {"account_code": ACC["other"], "debit": g("other_deductions"), "credit": 0,
         "description": (doc.get("other_deductions_note") or "Potongan lain")},
        # Penyesuaian bisa dua arah — ditulis di sisi yang benar, bukan dipaksa.
        {"account_code": ACC["other"],
         "debit": (-adj if adj < 0 else 0), "credit": (adj if adj > 0 else 0),
         "description": "Penyesuaian platform"},
    ]

    res = await _create_posted_je(
        db,
        je_date=date.fromisoformat(str(doc["settlement_date"])[:10]),
        memo=f"Pencairan {doc['platform']} — {doc.get('account_name') or ''} "
             f"({doc['settlement_id']})",
        source_module=SOURCE_MODULE,
        source_ref=doc["settlement_id"],
        lines_raw=lines,
        user=user,
        status="draft",
    )
    if not res.get("ok"):
        raise HTTPException(400, res.get("error") or "Gagal membuat jurnal.")

    await db[COLL].update_one({"id": sid}, {"$set": {
        "je_id": res["je_id"], "je_number": res["je_number"],
        "je_status": "draft", "coa_used": ACC, "coa_source": coa["sources"],
        "updated_at": _now()}})
    return {"ok": True, "je_id": res["je_id"], "je_number": res["je_number"],
            "je_status": "draft", "coa_used": ACC, "coa_source": coa["sources"],
            "message": f"Jurnal DRAFT {res['je_number']} dibuat memakai rekening "
                       f"{ACC['cash']} & akun pendapatan {ACC['revenue']} milik toko "
                       f"ini. Tekan 'Posting' setelah angkanya diperiksa."}


@router.get("/reconcile")
async def reconcile(
    request: Request,
    account_id: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    settlement_id: str = Query(default="",
                               description="Bila diisi: periode & toko diambil dari "
                                           "pencairan itu (period_from..period_to)."),
):
    """Jawab pertanyaan "angka mana yang benar": omzet marketing vs pencairan.

    Dua angka ini SELALU berbeda, dan itu normal (pencairan tertinggal beberapa
    hari, dan sudah dipotong). Yang tidak normal adalah kalau bedanya tidak bisa
    dijelaskan. Karena itu selisihnya ditampilkan APA ADANYA beserta total
    potongan — tanpa ada yang "dirapikan" supaya kelihatan cocok.
    """
    user = await require_auth(request)
    db = get_db()

    # ── Mode "satu pencairan": periode & toko diambil dari dokumennya ─────────
    # Kenapa perlu: layar Finance mencocokkan SATU pencairan, dan periodenya
    # sudah tertulis di dokumen itu (`period_from`..`period_to`). Menyuruh staf
    # menyalin tanggalnya sendiri adalah cara termurah membuat rekonsiliasi
    # membandingkan periode yang salah tanpa ada yang tahu.
    focus = None
    if settlement_id:
        focus = await db[COLL].find_one(
            {"$or": [{"id": settlement_id}, {"settlement_id": settlement_id}]}, {"_id": 0})
        if not focus:
            raise HTTPException(404, f"Pencairan '{settlement_id}' tidak ditemukan.")
        _with_math(focus)
        account_id = focus.get("account_id") or account_id
        date_from = focus.get("period_from") or focus.get("settlement_date") or date_from
        date_to = focus.get("period_to") or focus.get("settlement_date") or date_to

    sq: dict = {}
    vis = await _scope.visible_account_ids(db, user)
    if vis is not None:
        sq["account_id"] = {"$in": vis}
    if account_id:
        sq["account_id"] = account_id
    if date_from:
        sq.setdefault("settlement_date", {})["$gte"] = date_from
    if date_to:
        sq.setdefault("settlement_date", {})["$lte"] = date_to
    if focus:
        # Fokus satu dokumen: `settlement_date` bisa jatuh di luar periode
        # omzetnya sendiri (uang cair beberapa hari kemudian), jadi menyaring
        # pencairan dengan tanggal PERIODE akan membuatnya menghilang.
        sq = {"id": focus["id"]}

    sagg = await db[COLL].aggregate([
        {"$match": sq},
        {"$group": {"_id": None, "n": {"$sum": 1},
                    "gross": {"$sum": "$gross_sales"},
                    "net": {"$sum": "$net_payout"},
                    "ded": {"$sum": "$total_deductions"},
                    "refunds": {"$sum": "$refunds"}}},
    ]).to_list(1)
    s = sagg[0] if sagg else {}

    # Omzet marketing dari SSOT pesanan (bukan koleksi turunan).
    #
    # HATI-HATI (jebakan yang sempat membuat rekonsiliasi ini BOHONG): versi
    # pertama memakai `total_amount` dan menyaring `order_date` sebagai STRING.
    # Field `total_amount` TIDAK ADA di `marketing_orders`, dan `order_date`
    # bertipe `datetime` — hasilnya "559 pesanan, omzet Rp 0". Angka nol yang
    # muncul di sebelah 559 pesanan bukan sekadar salah: ia membuat seluruh
    # selisih rekonsiliasi terlihat seperti kesalahan platform.
    #
    # `marketing_orders` punya TIGA angka omzet dengan arti berbeda, jadi
    # ketiganya dilaporkan APA ADANYA beserta labelnya — memilih satu diam-diam
    # berarti memutuskan definisi omzet atas nama pembaca laporan.
    oq: dict = {}
    if vis is not None:
        oq["account_id"] = {"$in": vis}
    if account_id:
        oq["account_id"] = account_id
    _dt = {}
    if date_from:
        _dt["$gte"] = datetime.fromisoformat(f"{date_from}T00:00:00+00:00")
    if date_to:
        _dt["$lte"] = datetime.fromisoformat(f"{date_to}T23:59:59+00:00")
    if _dt:
        oq["order_date"] = _dt
    # Pesanan BATAL tidak pernah dicairkan platform — memasukkannya membuat
    # "pesanan belum cair" selalu besar dan selisihnya tidak berarti apa-apa.
    oq["status"] = {"$nin": list(CANCELLED_STATUSES)}
    oagg = await db.marketing_orders.aggregate([
        {"$match": oq},
        {"$group": {"_id": None, "n": {"$sum": 1},
                    "order_amount": {"$sum": "$order_amount"},
                    "revenue_gross": {"$sum": "$revenue_gross"},
                    "revenue_product": {"$sum": "$revenue_product"}}},
    ]).to_list(1)
    o = oagg[0] if oagg else {}

    gross = round(float(s.get("gross") or 0), 2)
    omzet_gross = round(float(o.get("revenue_gross") or 0), 2)
    omzet_product = round(float(o.get("revenue_product") or 0), 2)
    order_amount = round(float(o.get("order_amount") or 0), 2)
    unverified = await db[COLL].count_documents({**sq, "math_verified": False})

    # ── SELISIH YANG DIBERI NAMA (sesi #37) ───────────────────────────────────
    # Angka selisih tanpa nama tidak bisa ditindaklanjuti: staf melihat
    # "Rp 12.480.000" dan tidak tahu apakah itu pesanan yang belum cair, atau
    # uang yang cair tanpa pesanan tercatat. Keduanya butuh tindakan BERBEDA
    # (yang pertama: tunggu/telusuri pencairan berikutnya; yang kedua: cari
    # pesanan yang belum diimpor). Karena itu selisihnya dipecah dan DINAMAI —
    # dan tetap ditampilkan APA ADANYA, tidak di-nol-kan.
    gap_gross = round(gross - omzet_gross, 2)
    cancelled_count = await db.marketing_orders.count_documents(
        {**{k: v for k, v in oq.items() if k != "status"},
         "status": {"$in": list(CANCELLED_STATUSES)}})
    named = []
    if abs(gap_gross) < 0.01:
        named.append({"name": "cocok", "amount": 0.0,
                      "label": "Bruto pencairan sama dengan omzet bruto periode.",
                      "action": "Tidak ada yang perlu ditelusuri."})
    elif gap_gross < 0:
        named.append({
            "name": "pesanan_belum_cair", "amount": round(-gap_gross, 2),
            "label": "Pesanan sudah tercatat tetapi uangnya belum ikut dicairkan "
                     "di pencairan ini.",
            "action": "Wajar bila pesanan akhir periode baru cair di pencairan "
                      "berikutnya. Telusuri bila angkanya tidak menyusut pada "
                      "pencairan sesudahnya.",
        })
    else:
        named.append({
            "name": "cair_tanpa_pesanan", "amount": round(gap_gross, 2),
            "label": "Uang cair lebih besar daripada omzet pesanan yang tercatat "
                     "pada periode ini.",
            "action": "Biasanya karena pesanan periode itu BELUM diimpor ke "
                      "Marketing, atau pencairan memuat lebih dari satu periode. "
                      "Impor dulu pesanannya sebelum menyimpulkan selisih.",
        })
    if cancelled_count:
        named.append({
            "name": "pesanan_batal_dikecualikan", "amount": 0.0,
            "label": f"{cancelled_count} pesanan berstatus batal TIDAK dihitung "
                     f"sebagai omzet periode.",
            "action": "Informasi saja — pesanan batal memang tidak dicairkan.",
        })
    if unverified:
        named.append({
            "name": "selisih_belum_bernama", "amount": 0.0,
            "label": f"{unverified} pencairan masih punya selisih aritmetika "
                     f"(net payout ≠ hasil hitung rinciannya).",
            "action": "Catat selisihnya sebagai 'Potongan lain' atau "
                      "'Penyesuaian' beserta keterangannya — jurnal ditolak "
                      "selama ini belum beres.",
        })

    return {
        "ok": True,
        "period": {"account_id": account_id or None,
                   "from": date_from or None, "to": date_to or None,
                   "from_settlement": (focus or {}).get("settlement_id")},
        "focus": ({
            "id": focus["id"], "settlement_id": focus["settlement_id"],
            "settlement_date": focus.get("settlement_date"),
            "period_from": focus.get("period_from"),
            "period_to": focus.get("period_to"),
            "gross_sales": focus.get("gross_sales"),
            "net_payout": focus.get("net_payout"),
            "math_verified": focus.get("math_verified"),
            "net_payout_diff": focus.get("net_payout_diff"),
            "je_number": focus.get("je_number"),
            "je_status": focus.get("je_status"),
        } if focus else None),
        "settlement": {
            "count": int(s.get("n") or 0),
            "gross_sales": gross,
            "net_payout": round(float(s.get("net") or 0), 2),
            "total_deductions": round(float(s.get("ded") or 0), 2),
            "refunds": round(float(s.get("refunds") or 0), 2),
            "deduction_pct": round(float(s.get("ded") or 0) / gross * 100, 2)
            if gross else 0.0,
            "unverified_count": unverified,
        },
        "marketing": {
            "order_count": int(o.get("n") or 0),
            # Ketiganya dilaporkan; labelnya ikut supaya tidak dibaca sebagai
            # angka yang seharusnya sama.
            "revenue_gross": omzet_gross,
            "revenue_product": omzet_product,
            "order_amount": order_amount,
            "labels": {
                "revenue_gross": "sebelum diskon penjual & potongan platform",
                "revenue_product": "sesudah diskon penjual, sebelum potongan platform",
                "order_amount": "nilai yang dibayar pembeli",
            },
        },
        "gap": {
            # Pembanding yang paling setara: bruto platform vs bruto marketing.
            "gross_vs_revenue_gross": round(gross - omzet_gross, 2),
            "net_vs_revenue_product": round(
                float(s.get("net") or 0) - omzet_product, 2),
            # Selisih yang SUDAH DIBERI NAMA — inilah yang dibaca layar Finance.
            "named": named,
            "cancelled_orders_excluded": cancelled_count,
            "why": ("Selisih WAJAR terjadi karena: (1) pencairan tertinggal "
                    "beberapa hari dari tanggal pesanan, (2) pesanan yang "
                    "dibatalkan/retur tidak ikut dicairkan, dan (3) satu "
                    "pencairan bisa memuat beberapa periode. Yang perlu "
                    "ditelusuri adalah selisih yang TIDAK bisa dijelaskan oleh "
                    "ketiga hal itu. Angka omzet ditampilkan dalam tiga definisi "
                    "karena ketiganya memang berbeda arti — bukan supaya salah "
                    "satunya dipilih agar 'cocok'."),
        },
    }


# ── POSTING JURNAL DRAF (sesi #37) ───────────────────────────────────────────
# Keputusan pemilik: jurnal lahir DRAFT, lalu ada tombol "Posting" terpisah.
# Endpoint ini ada supaya layar Finance tidak perlu berpindah modul hanya untuk
# menekan satu tombol — logikanya SAMA dengan
# `POST /api/rahaza/journals/{je_id}/post` (dipakai ulang, bukan disalin),
# supaya tidak mungkin ada dua definisi "posted" yang berbeda.
@router.post("/{sid}/post")
async def post_settlement_journal(sid: str, request: Request):
    user = await _require_finance(request)
    db = get_db()
    doc = await db[COLL].find_one({"id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Pencairan tidak ditemukan.")
    if not doc.get("je_id"):
        raise HTTPException(400, "Pencairan ini belum punya jurnal draf. "
                                 "Tekan 'Buat jurnal' dulu.")

    from routes.rahaza_journals import _check_period_open, _mirror_lines

    je = await db.rahaza_journal_entries.find_one({"id": doc["je_id"]})
    if not je:
        raise HTTPException(404, f"Jurnal {doc.get('je_number')} sudah tidak ada.")
    if je.get("status") == "posted":
        await db[COLL].update_one({"id": sid}, {"$set": {"je_status": "posted"}})
        return {"ok": True, "already": True, "je_number": je["je_number"],
                "je_status": "posted",
                "message": f"Jurnal {je['je_number']} sudah diposting — "
                           f"tidak diposting dua kali."}
    if je.get("status") != "draft":
        raise HTTPException(400, f"Hanya jurnal draf yang bisa diposting. "
                                 f"Status sekarang: {je.get('status')}.")
    await _check_period_open(db, date.fromisoformat(str(je["date"])[:10]))
    await db.rahaza_journal_entries.update_one(
        {"id": je["id"]},
        {"$set": {"status": "posted", "posted_at": _now(),
                  "posted_by": (user or {}).get("id"), "updated_at": _now()}})
    je["status"] = "posted"
    await _mirror_lines(db, je)
    await db[COLL].update_one({"id": sid}, {"$set": {
        "je_status": "posted", "updated_at": _now()}})
    return {"ok": True, "je_number": je["je_number"], "je_status": "posted",
            "message": f"Jurnal {je['je_number']} diposting ke buku besar."}


# ── DETAIL SATU PENCAIRAN ────────────────────────────────────────────────────
# SENGAJA DIDEKLARASIKAN PALING AKHIR. FastAPI mencocokkan rute menurut urutan
# deklarasi; kalau `GET /{sid}` ditulis di atas, ia akan menelan `GET /reconcile`
# dan `GET /coa-map` (keduanya cocok dengan pola `/{sid}`) dan dua endpoint itu
# mati tanpa satu pun galat.
@router.get("/{sid}")
async def get_settlement(sid: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    doc = await db[COLL].find_one({"id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Pencairan tidak ditemukan.")
    vis = await _scope.visible_account_ids(db, user)
    if vis is not None and doc.get("account_id") not in vis:
        raise HTTPException(403, "Pencairan ini milik toko yang tidak Anda pegang.")
    _with_math(doc)

    # Tautan akun DILAPORKAN, tidak divalidasi keras di sini: layar detail harus
    # bisa MENJELASKAN kenapa tombol "Buat jurnal" akan ditolak, bukan gagal
    # dimuat karena alasan yang sama.
    account = await db.marketing_platform_accounts.find_one(
        {"id": doc.get("account_id")},
        {"_id": 0, "id": 1, "account_name": 1, "platform": 1,
         "coa_cash_code": 1, "coa_revenue_code": 1, "coa_receivable_code": 1}) or {}
    coa_ready = bool((account.get("coa_cash_code") or "").strip()
                     and (account.get("coa_revenue_code") or "").strip())
    binding = await _je_still_binding(db, doc)
    return {
        "ok": True,
        "data": _ser(doc),
        "account": account,
        "coa": {
            "ready": coa_ready,
            "cash": account.get("coa_cash_code") or None,
            "revenue": account.get("coa_revenue_code") or None,
            "deduction_accounts": {k: v for k, v in COA.items()
                                   if k not in ("cash", "revenue")},
            "note": ("Akun kas & pendapatan diambil dari akun toko; akun potongan "
                     "(retur, diskon, fee platform, iklan, lain-lain) memakai peta "
                     "global karena tidak per toko."
                     if coa_ready else
                     "Toko ini belum punya tautan akun kas/pendapatan — jurnal "
                     "akan DITOLAK sampai diisi di Portal Marketing → Manajemen "
                     "Akun."),
        },
        "can": {
            # SESI #40 — jurnal yang sudah void tidak lagi mengunci pencairannya
            # (satu aturan, dipakai bersama PUT/DELETE lewat `_je_still_binding`).
            "edit": not binding,
            "journal": bool(doc.get("math_verified")) and not binding and coa_ready,
            "post": doc.get("je_status") == "draft",
        },
    }
