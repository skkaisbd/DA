# ruff: noqa: F401
"""
marketing_accounts.py — Platform Account Management
Extracted from marketing.py (1757 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #3
Endpoints: POST /accounts, GET /accounts, GET /accounts/{id}, PUT /accounts/{id}, DELETE /accounts/{id}
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from database import get_db
from core import marketing_account_scope as scope
from auth import require_auth, serialize_doc, log_activity
from routes.marketing_shared import _uid, _now, _get_user, _sanitize, PlatformAccountCreate, PlatformAccountUpdate, SalesDataEntry
from core import marketing_sales_shape as _shape

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/marketing', tags=['Marketing-Accounts'])

# ══════════════════════════════════════════════════════════════════════════════
# F0.7 — pembantu tautan Finance (bagan akun `rahaza_coa_accounts`)
# Kenapa di sini: layar Manajemen Akun harus bisa MENGISI & MENAMPILKAN tautan
# COA per toko. Aturan keras: kode COA tidak pernah dikarang — kalau tidak ada
# di bagan akun, field dibiarkan kosong / permintaan ditolak 400.
# ══════════════════════════════════════════════════════════════════════════════
PLATFORM_TO_COA_CHANNEL = {"shopee": "shopee", "tiktokshop": "tiktok", "tokopedia": "tokopedia"}
DEFAULT_CASH_CODE = "1-1201"         # Bank BCA (kanonik 4-digit)
DEFAULT_RECEIVABLE_CODE = "1-1303"   # Piutang Platform Online Shop


def _usable_coa(row: dict) -> bool:
    """Akun yang boleh dipilih manusia: bukan akun grup/header dan masih aktif."""
    return bool(row) and not row.get("is_group") and row.get("active", True)


async def _coa_exists(db, code: str) -> bool:
    return bool(await db.rahaza_coa_accounts.find_one({"code": code}, {"_id": 0, "code": 1}))


def _flag(row: dict, key: str) -> bool:
    return bool((row.get("flags") or {}).get(key))


# Aturan peran akun: bukan cuma "ada di COA", tapi harus AKUN YANG BENAR.
# (Ditemukan lewat test_core_f07_accounts_ui.py: `9-000 BIAYA UMUM & ADMINISTRASI`
#  — akun grup beban — sebelumnya lolos sebagai "rekening pencairan".)
COA_ROLE_RULES = {
    "coa_revenue_code": {
        "field": "Akun Pendapatan",
        "label": "akun pendapatan penjualan",
        "ok": lambda r: r.get("type") == "REVENUE" and _flag(r, "is_sales") and not _flag(r, "is_contra"),
        "lenient": lambda r: r.get("type") == "REVENUE",
        "hint": "pilih akun penjualan toko (mis. 4-122 Penjualan – TikTok Outfit Boutique)",
    },
    "coa_cash_code": {
        "field": "Rekening Pencairan",
        "label": "rekening kas/bank penerima pencairan",
        "ok": lambda r: _flag(r, "is_bank") or _flag(r, "is_cash"),
        "lenient": lambda r: r.get("type") == "ASSET",
        "hint": "pilih rekening kas/bank/e-wallet (mis. 1-1201 Bank BCA)",
    },
    "coa_receivable_code": {
        "field": "Akun Piutang Platform",
        "label": "akun piutang platform",
        "ok": lambda r: _flag(r, "is_ar"),
        "lenient": lambda r: r.get("type") == "ASSET",
        "hint": "pilih akun piutang (mis. 1-1303 Piutang Platform Online Shop)",
    },
}


async def _validate_coa_role(db, fname: str, code: str) -> dict:
    """Pastikan `code` ada, bukan akun grup, masih aktif, dan berperan benar.
    Melempar HTTPException 400 dengan pesan yang bisa ditindaklanjuti staf."""
    rule = COA_ROLE_RULES.get(fname) or {}
    field = rule.get("field") or fname
    row = await db.rahaza_coa_accounts.find_one(
        {"code": code},
        {"_id": 0, "code": 1, "name": 1, "type": 1, "flags": 1, "is_group": 1, "active": 1})
    if not row:
        raise HTTPException(400, f"{field}: akun COA '{code}' tidak ada di bagan akun. "
                                 f"Buat dulu di Portal Keuangan → COA.")
    label = f"{code} — {row.get('name') or ''}".strip(" —")
    if row.get("is_group"):
        raise HTTPException(400, f"{field}: '{label}' adalah akun induk (grup) dan tidak bisa "
                                 f"dipakai untuk posting. Pilih akun rinciannya.")
    if not row.get("active", True):
        raise HTTPException(400, f"{field}: akun '{label}' sudah tidak aktif.")
    if rule:
        # Bila bagan akun belum memakai `flags` (DB lama), pakai pemeriksaan longgar
        # berbasis tipe akun supaya akun yang sah tidak ditolak keliru.
        checker = rule["ok"] if (row.get("flags") or {}) else rule["lenient"]
        if not checker(row):
            raise HTTPException(400, f"{field}: '{label}' bukan {rule['label']}. "
                                     f"Silakan {rule['hint']}.")
    return row


async def _fallback_revenue_code(db, platform: str) -> str:
    """Akun pendapatan penampung per platform (`4-114` Shopee · `4-126` TikTok ·
    `4-131` Tokopedia). Dipakai HANYA bila toko baru belum punya akun sendiri —
    supaya tidak ada toko tanpa alamat jurnal (RENCANA_EKSEKUSI_MASTER §F0.7)."""
    channel = PLATFORM_TO_COA_CHANNEL.get(platform or "")
    if not channel:
        return ""
    rows = await db.rahaza_coa_accounts.find(
        {"type": "REVENUE", "flags.is_sales": True, "flags.channel": channel},
        {"_id": 0, "code": 1, "name": 1, "is_group": 1, "active": 1},
    ).sort("code", 1).to_list(100)
    rows = [r for r in rows if _usable_coa(r)]
    if not rows:
        return ""
    catchall = [r for r in rows if "lain" in (r.get("name") or "").lower()]
    return (catchall[0] if catchall else rows[0])["code"]


async def _default_cash_code(db) -> str:
    """Rekening penerima pencairan default (1-1201); fallback ke kas/bank pertama."""
    row = await db.rahaza_coa_accounts.find_one(
        {"code": DEFAULT_CASH_CODE}, {"_id": 0, "code": 1, "is_group": 1, "active": 1})
    if _usable_coa(row):
        return DEFAULT_CASH_CODE
    row = await db.rahaza_coa_accounts.find_one(
        {"$or": [{"flags.is_bank": True}, {"flags.is_cash": True}],
         "is_group": {"$ne": True}},
        {"_id": 0, "code": 1}, sort=[("code", 1)])
    return (row or {}).get("code", "")


async def _resolve_pic(db, pic_user_id):
    """(pic_user_id, pic_user_name) — 400 bila id pengguna tidak ada."""
    pid = (pic_user_id or "").strip()
    if not pid:
        return None, None
    user = await db.users.find_one({"id": pid}, {"_id": 0, "name": 1, "email": 1})
    if not user:
        raise HTTPException(400, f"PIC dengan id '{pid}' tidak ditemukan di daftar pengguna")
    return pid, (user.get("name") or user.get("email"))


@router.post("/accounts")
async def create_platform_account(data: PlatformAccountCreate, request: Request):
    """
    Create new platform account.
    PIC Marketing can create unlimited accounts per platform.
    """
    await require_auth(request)
    db = get_db()
    
    # Validate platform
    valid_platforms = ["shopee", "tiktokshop", "tokopedia"]
    if data.platform not in valid_platforms:
        raise HTTPException(400, f"Platform harus salah satu dari: {', '.join(valid_platforms)}")
    
    # Check duplicate account_code
    existing = await db.marketing_platform_accounts.find_one({"account_code": data.account_code}, {"_id": 0})
    if existing:
        raise HTTPException(400, f"Kode akun '{data.account_code}' sudah dipakai toko "
                                 f"'{existing.get('account_name') or '-'}'. Pakai kode lain.")
    
    # ── F0.7 — validasi kode COA harus BENAR-BENAR ada di bagan akun ─────────
    coa_fields = {
        "coa_revenue_code": (data.coa_revenue_code or "").strip(),
        "coa_cash_code": (data.coa_cash_code or "").strip(),
        "coa_receivable_code": (data.coa_receivable_code or "").strip(),
    }
    for fname, code in coa_fields.items():
        if code:
            await _validate_coa_role(db, fname, code)
    # Tidak boleh ada toko tanpa alamat jurnal: bila kosong, isi otomatis dari akun
    # penampung platform + kas default + piutang platform (semua diverifikasi ada).
    revenue_source = "input" if coa_fields["coa_revenue_code"] else "fallback_platform"
    if not coa_fields["coa_revenue_code"]:
        coa_fields["coa_revenue_code"] = await _fallback_revenue_code(db, data.platform)
    if not coa_fields["coa_cash_code"]:
        coa_fields["coa_cash_code"] = await _default_cash_code(db)
    if not coa_fields["coa_receivable_code"]:
        coa_fields["coa_receivable_code"] = (
            DEFAULT_RECEIVABLE_CODE if await _coa_exists(db, DEFAULT_RECEIVABLE_CODE) else "")
    basis = data.revenue_basis or _shape.DEFAULT_BASIS
    if basis not in _shape.VALID_BASIS:
        raise HTTPException(400, "Basis omzet harus salah satu dari: "
                                 f"{', '.join(_shape.VALID_BASIS)}")
    pic_user_id, pic_user_name = await _resolve_pic(db, getattr(data, "pic_user_id", None))

    account = {
        "id": _uid(),
        "account_code": _sanitize(data.account_code, 100),
        "account_name": _sanitize(data.account_name, 200),
        "platform": data.platform,
        "username": _sanitize(data.username or "", 100),
        "status": "active",
        "group": data.group or "other",
        "credentials": {
            "api_key": "",
            "api_secret": "",
            "has_api_integration": data.has_api_integration
        },
        "import_config": {
            "saved_templates": []
        },
        "assigned_staff": [],
        "pic_id": getattr(request.state, 'user', {}).get("id", "system"),
        "health_score": None,  # None = belum ada data (UI tampilkan "N/A")
        # F0.7 — tautan Finance + basis omzet (SSOT §1)
        **coa_fields,
        "platform_warehouse_name": _sanitize(data.platform_warehouse_name or "", 200),
        "platform_shop_id": _sanitize(data.platform_shop_id or "", 100),
        "revenue_basis": basis,
        "coa_revenue_source": revenue_source,   # 'input' | 'fallback_platform' (badge di UI)
        "pic_user_id": pic_user_id,
        "pic_user_name": pic_user_name,
        "created_at": _now(),
        "created_by": getattr(request.state, 'user', {}).get("email", "system"),
        "updated_at": _now()
    }
    
    await db.marketing_platform_accounts.insert_one(account)
    # Phase 6: auto-create COA subledger (Piutang per-channel) — idempotent, non-fatal.
    # 2026-08-07 — DULU `except Exception: pass`. Channel marketing tanpa subledger
    # piutang berarti penjualan channel itu tidak punya akun Buku Besar sendiri.
    try:
        from routes.coa_auto import ensure_subledger_for_entity
        _u = getattr(request.state, 'user', {}) or {}
        await ensure_subledger_for_entity(db, "channel", account, _u)
    except Exception as e:  # noqa: BLE001
        logger.error(
            "[coa] subledger piutang channel GAGAL dibuat untuk %s — penjualan channel "
            "ini tidak punya akun Buku Besar: %s",
            account.get("account_name") or account.get("id"), e)
    
    await log_activity(
        getattr(request.state, 'user', {}).get("id", "system"),
        getattr(request.state, 'user', {}).get("name") or getattr(request.state, 'user', {}).get("email", "system"),
        "create",
        "marketing_account",
        f"Created platform account: {data.account_name} ({data.platform})"
    )
    
    # Baca ulang: `ensure_subledger_for_entity` menulis `ar_account_code` SETELAH insert.
    # Tanpa ini, UI tidak pernah melihat akun COA otomatis yang baru dibuat.
    saved = await db.marketing_platform_accounts.find_one({"id": account["id"]}, {"_id": 0})
    return serialize_doc({"message": "Platform account created", "account": saved or account})


@router.get("/accounts")
async def list_platform_accounts(
    request: Request,
    platform: Optional[str] = Query(None, description="Filter by platform"),
    status: Optional[str] = Query(None, description="Filter by status"),
    group: Optional[str] = Query(None, description="Filter by group")
):
    """
    List all platform accounts with optional filters.
    PIC Marketing sees all, Staff sees assigned only.
    """
    await require_auth(request)
    db = get_db()
    
    query = {}
    
    # Build query filters
    if platform:
        query["platform"] = platform
    if status:
        query["status"] = status
    if group:
        query["group"] = group
    
    # F6 (2026-08-13) — VISIBILITAS PER PEMAKAI ditegakkan di sini.
    # Sebelum ini semua peran melihat 9 toko: staf yang memegang 1 toko ikut melihat
    # omzet, biaya, dan target toko rekan kerjanya, dan setiap pemilih toko di layar
    # menampilkan toko yang bukan tanggung jawabnya — tanpa satu pun galat.
    _user = getattr(request.state, 'user', None) or {}
    query = await scope.scope_filter(db, _user, query, field='id')

    accounts = await db.marketing_platform_accounts.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    if not accounts and not scope.sees_all_accounts(_user):
        logger.info('[accounts] pemakai %s tanpa toko ter-assign (role=%s)',
                    _user.get('email'), _user.get('role'))
    return serialize_doc(accounts)


class LearnWarehouseBody(BaseModel):
    """Simpan nama gudang platform yang TERBACA dari ekspor Seller Center."""
    warehouse_name: str = Field(min_length=1, max_length=200)
    session_id: Optional[str] = None      # sesi impor asal (jejak)


@router.post("/accounts/{account_id}/learn-warehouse")
async def learn_platform_warehouse(account_id: str, data: LearnWarehouseBody,
                                   request: Request):
    """Isi `platform_warehouse_name` toko dari nama gudang di berkas ekspor.

    KENAPA ini ada
    --------------
    Penjaga toko (F1) hanya bisa menahan "berkas masuk toko yang salah" kalau
    master toko sudah menyimpan nama gudang platformnya. Dari 9 toko, hanya 1 yang
    terisi — dan meminta pemilik mengetik 8 nama dari ingatan berisiko: satu salah
    ketik membuat penjaga menolak berkas yang BENAR (lebih buruk daripada tidak ada
    penjaga, karena staf akan belajar mengabaikannya).

    Karena itu namanya diambil dari **ekspor platform itu sendiri**: saat impor
    pertama sebuah toko, layar menawarkan tombol "Simpan gudang ini ke master toko".

    Pagar yang dipasang:
      * kalau toko ini SUDAH punya nama gudang lain ⇒ **409** (tidak menimpa
        diam-diam; nama gudang adalah kunci penjaga, bukan catatan bebas);
      * kalau nama gudang itu sudah dipakai toko LAIN ⇒ **409** dengan nama toko
        pemiliknya (dua toko bergudang sama = penjaga jadi tidak ada artinya);
      * perubahan dicatat ke jejak aktivitas beserta sesi impor asalnya.
    """
    await require_auth(request)
    user = _get_user(request)
    db = get_db()

    name = (data.warehouse_name or "").strip()
    if not name:
        raise HTTPException(400, "Nama gudang platform kosong")

    acc = await db.marketing_platform_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acc:
        raise HTTPException(404, "Toko tidak ditemukan")

    current = (acc.get("platform_warehouse_name") or "").strip()
    if current and current.casefold() != name.casefold():
        raise HTTPException(409,
            f"Toko '{acc.get('account_name')}' sudah terdaftar dengan gudang platform "
            f"'{current}'. Kalau memang berubah, ubah lewat menu Kelola Akun "
            f"(Edit toko) supaya perubahannya sadar — bukan otomatis dari berkas.")
    if current:
        return serialize_doc({"ok": True, "changed": False,
                              "account_id": account_id,
                              "platform_warehouse_name": current,
                              "message": f"Gudang platform '{current}' sudah tersimpan "
                                         f"untuk toko ini."})

    owner = await db.marketing_platform_accounts.find_one(
        {"id": {"$ne": account_id}, "platform_warehouse_name": name},
        {"_id": 0, "account_name": 1, "account_code": 1})
    if owner:
        raise HTTPException(409,
            f"Gudang platform '{name}' sudah dipakai toko "
            f"'{owner.get('account_name')}' ({owner.get('account_code')}). "
            f"Satu gudang tidak boleh menempel pada dua toko — periksa dulu berkas "
            f"ini memang milik toko mana.")

    await db.marketing_platform_accounts.update_one(
        {"id": account_id},
        {"$set": {"platform_warehouse_name": name,
                  "platform_warehouse_source": "import_file",
                  "platform_warehouse_learned_at": _now(),
                  "platform_warehouse_learned_from_session": data.session_id or "",
                  "updated_at": _now()}})
    await log_activity(
        user.get("id", ""), user.get("name") or user.get("email", "system"),
        "learn_warehouse", "marketing_platform_accounts",
        f"Gudang platform toko '{acc.get('account_name')}' diisi dari berkas impor: "
        f"'{name}' (sesi {data.session_id or '-'})")
    return serialize_doc({
        "ok": True, "changed": True, "account_id": account_id,
        "platform_warehouse_name": name,
        "message": f"Gudang platform '{name}' disimpan ke toko "
                   f"'{acc.get('account_name')}'. Impor berikutnya untuk toko ini "
                   f"otomatis terjaga dari salah pilih toko."})


class ShipSlaBody(BaseModel):
    """Batas kirim per toko (dasar kolom 'lewat batas' di Monitoring Pengiriman)."""
    ship_sla_days: float = Field(ge=0.25, le=60)
    ship_sla_days_preorder: float = Field(ge=0.25, le=120)


@router.put("/accounts/{account_id}/ship-sla")
async def set_ship_sla(account_id: str, data: ShipSlaBody, request: Request):
    """Ubah batas kirim toko (hari) — normal & pre-order.

    Batas ini yang menentukan pesanan mana yang dihitung **lewat batas** di
    Monitoring Pengiriman. Sengaja disimpan di master toko dan bisa diubah dari
    layar: setiap platform (dan setiap kesepakatan pre-order) punya tenggat
    berbeda, dan aturan yang tersembunyi di kode akan melahirkan laporan "merah"
    yang tidak bisa dipertanggungjawabkan ke siapa pun.
    """
    await require_auth(request)
    user = _get_user(request)
    db = get_db()
    acc = await db.marketing_platform_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acc:
        raise HTTPException(404, "Toko tidak ditemukan")
    if data.ship_sla_days_preorder < data.ship_sla_days:
        raise HTTPException(400, "Batas pre-order tidak boleh lebih pendek daripada "
                                 "batas pesanan normal — pre-order justru butuh waktu "
                                 "lebih panjang.")
    await db.marketing_platform_accounts.update_one(
        {"id": account_id},
        {"$set": {"ship_sla_days": float(data.ship_sla_days),
                  "ship_sla_days_preorder": float(data.ship_sla_days_preorder),
                  "ship_sla_updated_at": _now(),
                  "ship_sla_updated_by": user.get("email", "system"),
                  "updated_at": _now()}})
    await log_activity(
        user.get("id", ""), user.get("name") or user.get("email", "system"),
        "set_ship_sla", "marketing_platform_accounts",
        f"Batas kirim toko '{acc.get('account_name')}' diubah menjadi "
        f"{data.ship_sla_days} hari (pre-order {data.ship_sla_days_preorder} hari)")
    return serialize_doc({"ok": True, "account_id": account_id,
                          "ship_sla_days": data.ship_sla_days,
                          "ship_sla_days_preorder": data.ship_sla_days_preorder,
                          "message": f"Batas kirim toko '{acc.get('account_name')}' "
                                     f"disimpan: {data.ship_sla_days} hari normal · "
                                     f"{data.ship_sla_days_preorder} hari pre-order"})


@router.post("/accounts/health/recompute-all")
async def recompute_all_health(request: Request):
    """Hitung ulang skor sehat (skala 1–5) SEMUA toko dari data 30 hari terakhir.

    Dipakai tombol "Hitung Ulang Skor" di layar Manajemen Akun: toko yang datanya
    baru masuk lewat impor langsung punya skor, bukan "Belum ada data" selamanya.
    """
    await require_auth(request)
    db = get_db()
    from routes.marketing_shared import _recalculate_health_score, health_grade_of

    accounts = await db.marketing_platform_accounts.find(
        {}, {"_id": 0, "id": 1, "account_name": 1}).to_list(500)
    scored = 0
    no_data = 0
    rows = []
    for acc in accounts:
        score = await _recalculate_health_score(db, acc["id"])
        grade, label = health_grade_of(score)
        if score is None:
            no_data += 1
        else:
            scored += 1
        rows.append({"account_id": acc["id"], "account_name": acc.get("account_name"),
                     "health_score": score, "health_grade": grade, "health_label": label})
    return serialize_doc({
        "ok": True, "accounts": len(accounts), "scored": scored, "no_data": no_data,
        "results": rows,
        "message": (f"{scored} toko punya skor sehat, {no_data} toko belum punya data "
                    f"30 hari terakhir")})


@router.get("/accounts/coa-options")
async def coa_options(request: Request):
    """F0.7 — daftar akun COA siap-pakai untuk pemilih di layar Manajemen Akun.

    Dikelompokkan sesuai perannya supaya staf tidak perlu menghafal nomor akun:
      · pendapatan  — akun penjualan per toko (`flags.is_sales`, bukan kontra/grup)
      · kas/bank    — rekening penerima pencairan (`flags.is_bank|is_cash`, termasuk ShopeePay)
      · piutang     — akun piutang platform (`flags.is_ar`, default `1-220`)

    Penyaringan memakai `flags` + `is_group` + `active` (BUKAN awalan kode) supaya
    daftar tidak tercemar akun grup, retur/diskon/potongan platform, persediaan,
    pajak, atau akun subledger otomatis.
    """
    await require_auth(request)
    db = get_db()
    rows = await db.rahaza_coa_accounts.find(
        {}, {"_id": 0, "code": 1, "name": 1, "type": 1, "flags": 1,
             "is_group": 1, "active": 1, "parent_code": 1}).sort("code", 1).to_list(2000)

    def flag(r, key):
        return bool((r.get("flags") or {}).get(key))

    def opt(r, extra=None):
        o = {"code": r["code"], "name": r.get("name") or r["code"], "type": r.get("type")}
        if extra:
            o.update(extra)
        return o

    usable = [r for r in rows if _usable_coa(r)]

    revenue = [opt(r, {"channel": (r.get("flags") or {}).get("channel") or ""})
               for r in usable
               if r.get("type") == "REVENUE" and flag(r, "is_sales") and not flag(r, "is_contra")]
    cash = [opt(r) for r in usable
            if (flag(r, "is_bank") or flag(r, "is_cash")) and not flag(r, "subledger")]
    receivable = [opt(r) for r in usable if flag(r, "is_ar") and not flag(r, "subledger")]

    # Fallback pendapatan per platform (akun penampung) — dihitung dari COA nyata.
    fallback = {}
    for plat in PLATFORM_TO_COA_CHANNEL:
        code = await _fallback_revenue_code(db, plat)
        if code:
            fallback[plat] = code

    default_recv = DEFAULT_RECEIVABLE_CODE if any(
        r["code"] == DEFAULT_RECEIVABLE_CODE for r in receivable) else (
        receivable[0]["code"] if receivable else "")

    return serialize_doc({
        "revenue": revenue,
        "cash": cash,
        "receivable": receivable,
        "default_receivable": default_recv,
        "default_cash": await _default_cash_code(db),
        "fallback_revenue_by_platform": fallback,
        "platform_channel_map": PLATFORM_TO_COA_CHANNEL,
        "revenue_basis_options": [
            {"value": "produk_setelah_diskon",
             "label": "Omzet produk (setelah diskon penjual, sebelum potongan platform)"},
            {"value": "order_amount",
             "label": "Order Amount (yang dibayar pembeli, termasuk ongkir)"},
        ],
    })


@router.get("/accounts/{account_id}")
async def get_platform_account(account_id: str, request: Request):
    """Get platform account detail"""
    await require_auth(request)
    db = get_db()
    
    account = await db.marketing_platform_accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(404, "Akun toko tidak ditemukan")
    
    return serialize_doc(account)


@router.put("/accounts/{account_id}")
async def update_platform_account(account_id: str, data: PlatformAccountUpdate, request: Request):
    """Update platform account"""
    await require_auth(request)
    db = get_db()
    
    account = await db.marketing_platform_accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(404, "Akun toko tidak ditemukan")
    
    # Build update dict
    update_data = {}
    if data.account_name is not None:
        update_data["account_name"] = data.account_name
    if data.username is not None:
        update_data["username"] = data.username
    if data.group is not None:
        update_data["group"] = data.group
    if data.status is not None:
        valid_status = ["active", "inactive", "suspended"]
        if data.status not in valid_status:
            raise HTTPException(400, f"Status harus salah satu dari: {', '.join(valid_status)}")
        update_data["status"] = data.status
    if data.has_api_integration is not None:
        update_data["credentials.has_api_integration"] = data.has_api_integration
    if data.pic_user_id is not None:
        pid, pname = await _resolve_pic(db, data.pic_user_id)
        update_data["pic_user_id"] = pid
        update_data["pic_user_name"] = pname

    # ── F0.7 — tautan Finance & basis omzet (divalidasi, bukan diterima mentah) ──
    for fname in ("coa_revenue_code", "coa_cash_code", "coa_receivable_code"):
        val = getattr(data, fname, None)
        if val is not None:
            if val:
                await _validate_coa_role(db, fname, val)
            update_data[fname] = val
            if fname == "coa_revenue_code" and val:
                update_data["coa_revenue_source"] = "input"
    if data.revenue_basis is not None:
        if data.revenue_basis not in _shape.VALID_BASIS:
            raise HTTPException(400, "Basis omzet harus salah satu dari: "
                                 f"{', '.join(_shape.VALID_BASIS)}")
        update_data["revenue_basis"] = data.revenue_basis
    if data.platform_warehouse_name is not None:
        update_data["platform_warehouse_name"] = _sanitize(data.platform_warehouse_name, 200)
    if data.platform_shop_id is not None:
        update_data["platform_shop_id"] = _sanitize(data.platform_shop_id, 100)
    # BD-5 — owner sudah mengoreksi nama/PIC/rekening toko hasil seed
    if data.needs_owner_review is not None:
        update_data["needs_owner_review"] = bool(data.needs_owner_review)
        if not data.needs_owner_review:
            update_data["owner_reviewed_at"] = _now()
            update_data["owner_reviewed_by"] = (_get_user(request)).get("email", "system")

    update_data["updated_at"] = _now()
    
    await db.marketing_platform_accounts.update_one(
        {"id": account_id},
        {"$set": update_data}
    )
    
    await log_activity(
        (_get_user(request)).get("id", "system"),
        (_get_user(request)).get("name") or (_get_user(request)).get("email", "system"),
        "update",
        "marketing_account",
        f"Updated platform account: {account['account_name']}"
    )
    
    # Get updated account
    updated = await db.marketing_platform_accounts.find_one({"id": account_id}, {"_id": 0})
    return serialize_doc({"message": "Platform account updated", "account": updated})


@router.delete("/accounts/{account_id}")
async def archive_platform_account(account_id: str, request: Request):
    """
    Archive (soft delete) platform account.
    Sets status to 'inactive' instead of hard delete.
    """
    await require_auth(request)
    db = get_db()
    
    account = await db.marketing_platform_accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(404, "Akun toko tidak ditemukan")
    
    await db.marketing_platform_accounts.update_one(
        {"id": account_id},
        {"$set": {"status": "inactive", "updated_at": _now()}}
    )
    
    await log_activity(
        (_get_user(request)).get("id", "system"),
        (_get_user(request)).get("name") or (_get_user(request)).get("email", "system"),
        "archive",
        "marketing_account",
        f"Archived platform account: {account['account_name']}"
    )
    
    return serialize_doc({"message": "Platform account archived"})


# ══════════════════════════════════════════════════════════════════════════════
# SALES DATA ENTRY (Manual for Phase 1)
# ══════════════════════════════════════════════════════════════════════════════
