"""Dewi Accessories — VALUASI HPP (FASE 8).

Endpoint (di bawah prefix /api/acc):
  GET  /valuation                  → ringkasan nilai persediaan aksesoris
                                     (per item + per kategori + total + item belum dinilai)
  GET  /valuation/movements        → mutasi aksesoris BERNILAI (kartu stok + jurnal)
  GET  /valuation/cost-history     → riwayat perubahan HPP (moving average / koreksi manual)
  POST /valuation/set-cost         → koreksi HPP manual (RBAC keuangan/penanggung jawab)

KENAPA ADA: sebelum FASE 8, nilai persediaan aksesoris tidak pernah dihitung di satu
tempat; layar stok hanya menampilkan qty, dan jurnal hanya muncul dari opname. Modul ini
menjadi "satu pintu" untuk melihat nilai persediaan aksesoris dan menemukan item yang
BELUM DINILAI (HPP = 0) — penyebab utama jurnal persediaan gagal terbentuk.
"""
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
import io
import logging

from database import get_db
from auth import require_auth, check_role, log_activity, serialize_doc
from core import accessory_valuation
from core.stock_rbac import SCRAP_ROLES, DISPOSE_ROLES
from services import accessory_valuation_mailer as mailer
from utils import accessory_valuation_export as export
from utils import email_sender

_log = logging.getLogger(__name__)
router = APIRouter(tags=["accessories-valuation"])

# Koreksi HPP = menyentuh nilai persediaan ⇒ gate sama ketatnya dengan write-off.
SET_COST_ROLES = SCRAP_ROLES
_FORBIDDEN_COST = (
    "Mengubah harga satuan (HPP) memengaruhi nilai persediaan & jurnal. Hanya Admin Gudang, "
    "Supervisor, Keuangan, atau Owner yang boleh melakukannya."
)

# Kirim ringkasan "belum dinilai" = tindakan INFORMATIF (tidak mengubah angka), jadi
# gate-nya operasional gudang — termasuk Admin Aksesoris yang justru paling
# berkepentingan melengkapi harga.
DIGEST_SEND_ROLES = DISPOSE_ROLES
_FORBIDDEN_DIGEST = (
    "Hanya tim gudang/aksesoris, supervisor, keuangan, atau owner yang boleh mengirim "
    "ringkasan item belum dinilai."
)
# Jadwal & pengiriman rapor menyentuh distribusi laporan keuangan ⇒ gate ketat.
_FORBIDDEN_SCHEDULE = (
    "Pengaturan & pengiriman rapor valuasi hanya boleh oleh Admin Gudang, Supervisor, "
    "Keuangan, atau Owner."
)

# Jenis mutasi yang relevan untuk laporan valuasi aksesoris.
_VALUED_TYPES = ("receive", "issue", "scrap", "opname_adjust", "adjust")


@router.get("/valuation")
async def get_valuation(request: Request, include_zero_stock: bool = Query(True)):
    """Ringkasan valuasi persediaan aksesoris (metode rata-rata bergerak)."""
    await require_auth(request)
    db = get_db()
    data = await accessory_valuation.summary(db, include_zero_stock=include_zero_stock)
    return serialize_doc(data)


@router.get("/valuation/movements")
async def get_valued_movements(request: Request,
                               acc_id: str = Query(None),
                               limit: int = Query(100, ge=1, le=500)):
    """Mutasi aksesoris beserta nilai & nomor jurnalnya (kartu stok bernilai)."""
    await require_auth(request)
    db = get_db()
    q: dict = {"material_id": {"$exists": True}}
    if acc_id:
        q["material_id"] = acc_id
    else:
        # batasi ke material bertipe accessory
        acc_ids = [m["id"] async for m in db.rahaza_materials.find(
            {"type": "accessory"}, {"_id": 0, "id": 1})]
        q["material_id"] = {"$in": acc_ids}
    q["movement_type"] = {"$in": list(_VALUED_TYPES)}
    rows = await db.rahaza_material_movements.find(q, {"_id": 0}) \
        .sort("created_at", -1).to_list(limit)
    out = []
    for r in rows:
        qty = float(r.get("qty_signed") if r.get("qty_signed") is not None else (r.get("qty") or 0))
        unit_cost = float(r.get("unit_cost") or 0)
        out.append({
            "id": r.get("id"),
            "created_at": r.get("created_at"),
            "material_id": r.get("material_id"),
            "material_code": (r.get("material") or {}).get("code", ""),
            "material_name": r.get("material_name") or (r.get("material") or {}).get("name", ""),
            "unit": r.get("unit") or (r.get("material") or {}).get("unit", ""),
            "movement_type": r.get("movement_type"),
            "qty_signed": qty,
            "unit_cost": unit_cost,
            "value": float(r.get("value") or round(abs(qty) * unit_cost, 2)),
            "adjustment_reason": r.get("adjustment_reason", ""),
            "notes": r.get("notes", ""),
            "je_number": r.get("gl_je_number") or "",
            "je_id": r.get("gl_je_id") or "",
            "post_error": r.get("post_error") or "",
        })
    return serialize_doc(out)


@router.get("/valuation/cost-history")
async def get_cost_history(request: Request,
                           acc_id: str = Query(None),
                           limit: int = Query(100, ge=1, le=500)):
    """Riwayat perubahan HPP **AKSESORIS** (rata-rata bergerak / koreksi manual).

    Sesi #33: disaring ke jenis aksesoris. Sebelumnya layar ini menampilkan
    riwayat material KAIN juga (koleksi riwayat dipakai semua jenis material).
    Riwayat lintas jenis ada di layar Riwayat Harga Barang (portal Gudang).
    """
    await require_auth(request)
    db = get_db()
    return serialize_doc(await accessory_valuation.cost_history(
        db, acc_id, limit=limit, types=accessory_valuation.ACCESSORY_TYPES))


@router.get("/valuation/export")
async def export_valuation(request: Request,
                           format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
                           month: str = Query(None, description="YYYY-MM; kosong = semua periode")):
    """Rapor valuasi persediaan aksesoris untuk lampiran laporan keuangan.

    `format=xlsx` (diolah lagi) atau `format=pdf` (ditandatangani). `month=YYYY-MM`
    memfilter tabel MUTASI ke bulan tersebut; tabel valuasi selalu posisi TERKINI
    (nilai persediaan adalah saldo, bukan arus).
    """
    await require_auth(request)
    db = get_db()

    # Satu sumber kebenaran: konteks rapor dibangun oleh service yang sama dengan
    # yang dipakai job email bulanan → isi rapor manual & otomatis identik.
    try:
        ctx = await mailer.build_report_context(db, month or None)
    except (ValueError, IndexError):
        raise HTTPException(400, "Parameter month harus format YYYY-MM (mis. 2026-07).")
    summary, movements, company = ctx["summary"], ctx["movements"], ctx["company"]

    try:
        if format == "pdf":
            data, fname = export.build_pdf(company=company, summary=summary,
                                           movements=movements, month=month)
            media = "application/pdf"
        else:
            data, fname = export.build_xlsx(company=company, summary=summary,
                                            movements=movements, month=month)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except Exception as e:  # noqa: BLE001
        _log.exception("[acc-valuation-export] gagal membuat rapor")
        raise HTTPException(500, f"Gagal membuat rapor: {e}")

    return StreamingResponse(
        io.BytesIO(data), media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{fname}"',
                 "Access-Control-Expose-Headers": "Content-Disposition"},
    )


@router.post("/valuation/set-cost")
async def set_cost(request: Request):
    """Koreksi HPP manual. Body: `{acc_id, unit_cost, notes?}`."""
    user = await require_auth(request)
    if not check_role(user, SET_COST_ROLES, "inv.stock.manage"):
        raise HTTPException(403, _FORBIDDEN_COST)
    db = get_db()
    body = await request.json()
    acc_id = (body.get("acc_id") or "").strip()
    if not acc_id:
        raise HTTPException(400, "acc_id wajib diisi.")
    try:
        new_cost = float(body.get("unit_cost"))
    except (TypeError, ValueError):
        raise HTTPException(400, "unit_cost harus berupa angka.")

    item = await db.rahaza_materials.find_one(
        {"id": acc_id, "type": "accessory"}, {"_id": 0, "id": 1, "code": 1})
    if not item:
        raise HTTPException(404, "Aksesoris tidak ditemukan.")

    res = await accessory_valuation.set_unit_cost(
        db, acc_id, new_cost, actor=user, notes=body.get("notes", ""))
    if not res.get("ok"):
        raise HTTPException(400, res.get("error") or "Gagal mengubah harga satuan.")
    await log_activity(user.get("id", ""), user.get("name", ""), "set_unit_cost",
                       "Aksesoris",
                       f"{item.get('code')} {res['old_unit_cost']} → {res['new_unit_cost']}")
    return serialize_doc(res)


# ═════════════════════════════════════════════════════════════════════════════
# FASE 10 — RINGKASAN ALARM HARIAN + JADWAL RAPOR BULANAN
# ═════════════════════════════════════════════════════════════════════════════
# Kenapa ada di sini: dua-duanya bersandar pada data valuasi yang sama, dan UI-nya
# hidup di tab "Valuasi HPP" (satu tempat untuk melihat nilai + apa yang menghambat).

@router.get("/valuation/unvalued-digest")
async def get_unvalued_digest(request: Request,
                              window_hours: int = Query(24, ge=1, le=168)):
    """Pratinjau ringkasan "belum dinilai" (isi yang sama dengan digest harian 07:30)."""
    await require_auth(request)
    db = get_db()
    data = await accessory_valuation.unvalued_report(db, window_hours=window_hours)
    last = await db.notifications.find_one(
        {"meta.digest_kind": accessory_valuation.DIGEST_KIND},
        {"_id": 0, "created_at": 1, "meta": 1, "title": 1},
        sort=[("created_at", -1)],
    )
    data["last_digest"] = {
        "created_at": (last or {}).get("created_at"),
        "date": ((last or {}).get("meta") or {}).get("digest_date"),
        "count": ((last or {}).get("meta") or {}).get("unvalued_count"),
        "triggered_by": ((last or {}).get("meta") or {}).get("triggered_by"),
    } if last else None
    data["schedule_label"] = "Setiap hari pukul 07:30 (Asia/Jakarta)"
    return serialize_doc(data)


@router.post("/valuation/unvalued-digest/send")
async def send_unvalued_digest_now(request: Request):
    """Kirim ringkasan "belum dinilai" SEKARANG (tanpa menunggu jadwal 07:30)."""
    user = await require_auth(request)
    if not check_role(user, DIGEST_SEND_ROLES, "inv.stock.manage"):
        raise HTTPException(403, _FORBIDDEN_DIGEST)
    db = get_db()
    out = await accessory_valuation.send_unvalued_digest(db, force=True, actor=user)
    await log_activity(user.get("id", ""), user.get("name", ""), "send_unvalued_digest",
                       "Aksesoris",
                       f"{out.get('items', 0)} item · {out.get('sent', 0)} notifikasi")
    return serialize_doc(out)


@router.get("/valuation/report-schedule")
async def get_report_schedule(request: Request):
    """Status jadwal rapor bulanan: aktif/tidak, penerima, kesiapan SMTP, riwayat kirim."""
    await require_auth(request)
    db = get_db()
    cfg = await mailer.get_config(db)
    recipients = await mailer.resolve_recipients(db, cfg)
    runs = await mailer.list_runs(db, limit=12)
    next_run = None
    try:
        from utils.scheduler import get_scheduler

        sch = get_scheduler()
        job = sch.get_job("monthly_valuation_report_email") if sch else None
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()
    except Exception:  # noqa: BLE001 — informasi jadwal bersifat tambahan
        next_run = None
    return serialize_doc({
        "enabled": bool(cfg.get("valuation_report_enabled", True)),
        "extra_emails": mailer.parse_extra_emails(cfg.get("valuation_report_extra_emails")),
        "recipients": recipients,
        "finance_roles": list(mailer.FINANCE_ROLES),
        "smtp": email_sender.smtp_status(cfg),
        "schedule_label": "Setiap tanggal 1 pukul 06:00 (Asia/Jakarta)",
        "next_run_at": next_run,
        "default_month": mailer.previous_month(),
        "runs": runs,
    })


@router.put("/valuation/report-schedule")
async def update_report_schedule(request: Request):
    """Atur jadwal rapor: `{enabled?: bool, extra_emails?: str|list}`.

    Disimpan di koleksi yang sama dengan Pengaturan Notifikasi (`dewi_provider_config`)
    supaya tidak ada dua sumber kebenaran untuk konfigurasi email.
    """
    user = await require_auth(request)
    if not check_role(user, SET_COST_ROLES, "inv.stock.manage"):
        raise HTTPException(403, _FORBIDDEN_SCHEDULE)
    db = get_db()
    body = await request.json()
    update: dict = {"updated_at": datetime.now(timezone.utc),
                    "updated_by": user.get("name", "System")}
    if "enabled" in body:
        update["valuation_report_enabled"] = bool(body.get("enabled"))
    if "extra_emails" in body:
        emails = mailer.parse_extra_emails(body.get("extra_emails"))
        raw = body.get("extra_emails")
        raw_count = len([x for x in str(raw).replace(";", ",").replace("\n", ",").split(",")
                         if x.strip()]) if isinstance(raw, str) else len(raw or [])
        if raw_count and not emails:
            raise HTTPException(400, "Format email tidak valid (harus mengandung '@').")
        update["valuation_report_extra_emails"] = emails
    await db.dewi_provider_config.update_one({"_type": "main"},
                                             {"$set": update,
                                              "$setOnInsert": {"_type": "main"}},
                                             upsert=True)
    cfg = await mailer.get_config(db)
    await log_activity(user.get("id", ""), user.get("name", ""), "update_valuation_report_schedule",
                       "Aksesoris",
                       f"aktif={cfg.get('valuation_report_enabled', True)} "
                       f"email_tambahan={len(mailer.parse_extra_emails(cfg.get('valuation_report_extra_emails')))}")
    return serialize_doc({
        "enabled": bool(cfg.get("valuation_report_enabled", True)),
        "extra_emails": mailer.parse_extra_emails(cfg.get("valuation_report_extra_emails")),
        "recipients": await mailer.resolve_recipients(db, cfg),
    })


@router.post("/valuation/report-schedule/send-now")
async def send_report_now(request: Request,
                          month: str = Query(None, description="YYYY-MM; kosong = bulan lalu")):
    """Kirim rapor valuasi periode `month` SEKARANG (lampiran Excel + PDF) ke keuangan."""
    user = await require_auth(request)
    if not check_role(user, SET_COST_ROLES, "inv.stock.manage"):
        raise HTTPException(403, _FORBIDDEN_SCHEDULE)
    db = get_db()
    if month:
        try:
            mailer.month_bounds(month)
        except (ValueError, IndexError):
            raise HTTPException(400, "Parameter month harus format YYYY-MM (mis. 2026-06).")
    out = await mailer.send_monthly_report(db, month=month, force=True, actor=user,
                                           source="manual")
    await log_activity(user.get("id", ""), user.get("name", ""), "send_valuation_report",
                       "Aksesoris", f"{out.get('month')} · {out.get('message', '')[:160]}")
    return serialize_doc(out)
