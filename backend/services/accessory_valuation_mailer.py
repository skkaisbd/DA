"""services.accessory_valuation_mailer — FASE 10: rapor valuasi aksesoris via EMAIL otomatis.

MASALAH YANG DISELESAIKAN
Rapor valuasi (Excel & PDF) sudah bisa DIUNDUH manual dari tab "Valuasi HPP"
(`GET /api/acc/valuation/export`). Praktiknya bagian keuangan harus ingat membuka
aplikasi setiap awal bulan, membuka tab yang tepat, memilih bulan, lalu mengunduh
dua file. Kalau lupa, tutup buku bulanan berjalan tanpa lampiran valuasi persediaan.

SOLUSI
Setiap tanggal 1 pukul 06:00 (Asia/Jakarta) job `monthly_valuation_report_email`
membuat rapor periode BULAN SEBELUMNYA lalu mengirimkannya sebagai lampiran
(XLSX + PDF) ke seluruh user ber-role keuangan + daftar email tambahan yang bisa
diatur dari UI. Setiap pengiriman dicatat di `acc_valuation_report_runs` sehingga
bisa diaudit ("bulan Juni terkirim ke siapa, jam berapa, berapa lampiran").

PRINSIP
  * IDEMPOTEN per periode: satu periode hanya dikirim sekali (kecuali `force=True`
    dari tombol "Kirim sekarang").
  * TIDAK PERNAH gagal senyap: bila SMTP belum diisi, run dicatat dengan status
    `skipped_no_smtp` + notifikasi dalam aplikasi tetap dikirim ke keuangan berisi
    ringkasan angka + arahan mengunduh manual.
  * TIDAK ADA dependensi baru: memakai `utils/accessory_valuation_export.py`
    (openpyxl + reportlab) dan `utils/email_sender.py` (smtplib bawaan Python).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from core import accessory_valuation
from utils import accessory_valuation_export as export
from utils import email_sender
from utils.notif_recipients import resolve_role_recipients

_log = logging.getLogger(__name__)

RUNS_COLL = "acc_valuation_report_runs"
CONFIG_COLL = "dewi_provider_config"
JAKARTA = ZoneInfo("Asia/Jakarta")

# "Keuangan" = tim yang menutup buku. Owner/superadmin sengaja TIDAK otomatis ikut
# supaya kotak masuk pimpinan tidak penuh lampiran rutin; kalau perlu, tambahkan
# alamatnya di "email tambahan" pada UI.
FINANCE_ROLES = ("accounting", "staff_keuangan")

# Jenis mutasi yang masuk tabel "Mutasi Bernilai" pada rapor (sama dengan endpoint export).
VALUED_TYPES = ("receive", "issue", "scrap", "opname_adjust", "adjust")

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_PDF = "application/pdf"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


def previous_month(ref: datetime | None = None) -> str:
    """Periode default job = bulan SEBELUMNYA menurut kalender Asia/Jakarta ('YYYY-MM')."""
    d = (ref or _now()).astimezone(JAKARTA)
    first = d.replace(day=1)
    prev = first - timedelta(days=1)
    return f"{prev.year:04d}-{prev.month:02d}"


def month_bounds(month: str) -> tuple[datetime, datetime]:
    """Batas UTC untuk 'YYYY-MM'. Melempar ValueError bila format salah."""
    y, mo = [int(x) for x in str(month).split("-")[:2]]
    if not 1 <= mo <= 12:
        raise ValueError("bulan di luar rentang 1-12")
    start = datetime(y, mo, 1, tzinfo=timezone.utc)
    end = datetime(y + (mo == 12), (mo % 12) + 1, 1, tzinfo=timezone.utc)
    return start, end


def parse_extra_emails(value) -> list[str]:
    """Terima list ATAU string dipisah koma/baris baru/titik-koma → list email bersih."""
    if not value:
        return []
    if isinstance(value, str):
        raw = value.replace(";", ",").replace("\n", ",").split(",")
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        return []
    out = []
    for item in raw:
        e = str(item or "").strip()
        if e and "@" in e and e.lower() not in [x.lower() for x in out]:
            out.append(e)
    return out


async def get_config(db) -> dict:
    return await db[CONFIG_COLL].find_one({"_type": "main"}) or {}


async def resolve_recipients(db, config: dict | None = None) -> list[dict]:
    """Penerima rapor = user ber-role keuangan (punya email) + email tambahan dari config."""
    cfg = config if config is not None else await get_config(db)
    out: list[dict] = []
    seen: set[str] = set()
    users = await resolve_role_recipients(db, FINANCE_ROLES, require_email=True)
    for u in users:
        email = str(u.get("email") or "").strip()
        if not email or email.lower() in seen:
            continue
        seen.add(email.lower())
        out.append({"email": email, "name": u.get("name") or email,
                    "role": u.get("role"), "user_id": u.get("id"), "source": "role_keuangan"})
    for email in parse_extra_emails(cfg.get("valuation_report_extra_emails")):
        if email.lower() in seen:
            continue
        seen.add(email.lower())
        out.append({"email": email, "name": email, "role": None, "user_id": None,
                    "source": "email_tambahan"})
    return out


async def build_report_context(db, month: str | None) -> dict:
    """Data rapor: ringkasan valuasi TERKINI + mutasi bernilai pada periode `month`.

    Nilai persediaan adalah SALDO (posisi terkini), sedangkan `month` hanya memfilter
    tabel mutasi — ini yang sama dipakai endpoint unduh manual supaya isi rapor
    otomatis dan manual identik (satu sumber kebenaran).
    """
    summary = await accessory_valuation.summary(db)
    acc_ids = [m["id"] async for m in db.rahaza_materials.find(
        {"type": "accessory"}, {"_id": 0, "id": 1})]
    q: dict = {"movement_type": {"$in": list(VALUED_TYPES)}, "material_id": {"$in": acc_ids}}
    if month:
        start, end = month_bounds(month)
        q["created_at"] = {"$gte": start, "$lt": end}
    rows = await db.rahaza_material_movements.find(q, {"_id": 0}) \
        .sort("created_at", -1).to_list(2000)
    movements = []
    for r in rows:
        qty = float(r.get("qty_signed") if r.get("qty_signed") is not None else (r.get("qty") or 0))
        unit_cost = float(r.get("unit_cost") or 0)
        movements.append({
            "created_at": r.get("created_at"),
            "material_code": (r.get("material") or {}).get("code", ""),
            "material_name": r.get("material_name") or (r.get("material") or {}).get("name", ""),
            "unit": r.get("unit") or (r.get("material") or {}).get("unit", ""),
            "movement_type": r.get("movement_type"),
            "qty_signed": qty,
            "unit_cost": unit_cost,
            "value": float(r.get("value") or round(abs(qty) * unit_cost, 2)),
            "je_number": r.get("gl_je_number") or "",
        })
    cs = await db.company_settings.find_one({}, {"_id": 0, "company_name": 1}) or {}
    return {
        "company": cs.get("company_name") or "CV. Dewi Aditya",
        "summary": summary,
        "movements": movements,
        "month": month,
    }


def build_attachments(ctx: dict) -> list[dict]:
    """Bangun dua lampiran (XLSX + PDF) dari konteks rapor."""
    xlsx, xname = export.build_xlsx(company=ctx["company"], summary=ctx["summary"],
                                    movements=ctx["movements"], month=ctx["month"])
    pdf, pname = export.build_pdf(company=ctx["company"], summary=ctx["summary"],
                                  movements=ctx["movements"], month=ctx["month"])
    return [
        {"filename": xname, "content": xlsx, "mime": MIME_XLSX},
        {"filename": pname, "content": pdf, "mime": MIME_PDF},
    ]


def _rp(v) -> str:
    return f"Rp {float(v or 0):,.0f}".replace(",", ".")


def compose_email(ctx: dict) -> tuple[str, str, str]:
    """(subject, body_text, body_html) — ringkasan angka penting langsung di badan email."""
    period = export.period_label(ctx["month"])
    t = ctx["summary"]["totals"]
    company = ctx["company"]
    subject = f"[{company}] Rapor Valuasi Persediaan Aksesoris — {period}"
    warn_txt = ""
    warn_html = ""
    if t.get("unvalued_items"):
        warn_txt = (f"\nPERHATIAN: {t['unvalued_items']} item masih ber-HPP 0 "
                    f"({t.get('unvalued_qty', 0):g} unit) sehingga nilainya belum masuk "
                    f"jurnal persediaan. Mohon dilengkapi di Aksesoris → Valuasi HPP.\n")
        warn_html = (f"<p style='color:#b45309'><strong>Perhatian:</strong> "
                     f"{t['unvalued_items']} item masih ber-HPP 0 "
                     f"({t.get('unvalued_qty', 0):g} unit) sehingga nilainya belum masuk "
                     f"jurnal persediaan. Mohon dilengkapi di "
                     f"<em>Aksesoris → Valuasi HPP</em>.</p>")
    body_text = (
        f"Rapor valuasi persediaan aksesoris periode {period}.\n\n"
        f"Nilai persediaan (posisi terkini) : {_rp(t.get('total_value'))}\n"
        f"Item bernilai                     : {t.get('valued_items', 0)}\n"
        f"Item belum dinilai (HPP 0)        : {t.get('unvalued_items', 0)}\n"
        f"Mutasi bernilai pada periode      : {len(ctx['movements'])} baris\n"
        f"{warn_txt}\n"
        f"Lampiran:\n"
        f"  1. Excel (.xlsx) — untuk diolah/ditelusuri\n"
        f"  2. PDF          — untuk ditandatangani/diarsipkan\n\n"
        f"Nilai persediaan adalah SALDO posisi terkini; filter periode hanya berlaku "
        f"untuk tabel mutasi.\n\n"
        f"Email ini dikirim otomatis oleh sistem {company} setiap awal bulan.\n"
    )
    rows = "".join(
        f"<tr><td style='padding:4px 10px'>{k}</td>"
        f"<td style='padding:4px 10px;text-align:right'><strong>{v}</strong></td></tr>"
        for k, v in (
            ("Nilai persediaan (posisi terkini)", _rp(t.get("total_value"))),
            ("Item bernilai", t.get("valued_items", 0)),
            ("Item belum dinilai (HPP 0)", t.get("unvalued_items", 0)),
            ("Mutasi bernilai pada periode", f"{len(ctx['movements'])} baris"),
        )
    )
    body_html = (
        f"<div style='font-family:Segoe UI,Arial,sans-serif;color:#111'>"
        f"<h2 style='margin:0 0 4px'>Rapor Valuasi Persediaan Aksesoris</h2>"
        f"<p style='margin:0 0 12px;color:#555'>{company} · periode <strong>{period}</strong></p>"
        f"<table style='border-collapse:collapse;background:#f8fafc;border:1px solid #e2e8f0'>"
        f"{rows}</table>{warn_html}"
        f"<p>Lampiran: <strong>Excel (.xlsx)</strong> untuk diolah dan <strong>PDF</strong> "
        f"untuk ditandatangani/diarsipkan.</p>"
        f"<p style='color:#555;font-size:12px'>Nilai persediaan adalah saldo posisi terkini; "
        f"filter periode hanya berlaku untuk tabel mutasi. Email ini dikirim otomatis "
        f"setiap awal bulan.</p></div>"
    )
    return subject, body_text, body_html


async def last_run(db, month: str | None = None, *, only_success: bool = False) -> dict | None:
    q: dict = {}
    if month:
        q["month"] = month
    if only_success:
        q["status"] = "sent"
    return await db[RUNS_COLL].find_one(q, {"_id": 0}, sort=[("created_at", -1)])


async def list_runs(db, *, limit: int = 12) -> list[dict]:
    return await db[RUNS_COLL].find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)


async def send_monthly_report(db, *, month: str | None = None, force: bool = False,
                              actor: dict | None = None, source: str = "scheduler") -> dict:
    """Buat & kirim rapor valuasi periode `month` (default: bulan sebelumnya).

    Balasan = dokumen run yang juga disimpan di `acc_valuation_report_runs`.
    Tidak melempar exception untuk kegagalan operasional (SMTP mati, dsb) — semuanya
    dicatat sebagai status run supaya job scheduler tidak ikut mati.
    """
    started = _now()
    month = (month or previous_month()).strip()
    try:
        month_bounds(month)  # validasi awal
    except (ValueError, IndexError):
        return {"status": "invalid_month", "month": month,
                "message": "Format periode harus YYYY-MM (mis. 2026-06)."}

    run = {
        "id": _uid(),
        "month": month,
        "status": "running",
        "source": source,
        "forced": bool(force),
        "triggered_by": (actor or {}).get("name") or "Sistem (jadwal bulanan)",
        "triggered_by_id": (actor or {}).get("id") or "",
        "created_at": started,
        "recipients": [],
        "sent_count": 0,
        "failed_count": 0,
        "errors": [],
        "attachments": [],
    }

    # 1) Idempotensi — periode yang sudah pernah terkirim tidak dikirim ulang.
    if not force:
        prev = await last_run(db, month, only_success=True)
        if prev:
            run.update({
                "status": "skipped_already_sent",
                "message": (f"Rapor periode {month} sudah terkirim pada "
                            f"{prev.get('created_at')} ke {prev.get('sent_count', 0)} penerima."),
                "finished_at": _now(),
            })
            await db[RUNS_COLL].insert_one(dict(run))
            run.pop("_id", None)
            return run

    # 2) Bangun rapor (angka + dua lampiran)
    try:
        ctx = await build_report_context(db, month)
        attachments = build_attachments(ctx)
    except Exception as e:  # noqa: BLE001
        _log.exception("[valuation-mail] gagal membuat rapor")
        run.update({"status": "failed", "message": f"Gagal membuat rapor: {e}",
                    "finished_at": _now()})
        await db[RUNS_COLL].insert_one(dict(run))
        run.pop("_id", None)
        return run

    totals = ctx["summary"]["totals"]
    run["total_value"] = totals.get("total_value", 0)
    run["unvalued_items"] = totals.get("unvalued_items", 0)
    run["movement_rows"] = len(ctx["movements"])
    run["attachments"] = [{"filename": a["filename"], "size": len(a["content"]),
                           "mime": a["mime"]} for a in attachments]

    cfg = await get_config(db)
    recipients = await resolve_recipients(db, cfg)
    run["recipients"] = [{"email": r["email"], "name": r["name"], "source": r["source"]}
                         for r in recipients]
    subject, body_text, body_html = compose_email(ctx)

    # 3) Notifikasi DALAM APLIKASI selalu dikirim (tidak bergantung SMTP) supaya
    #    keuangan tetap tahu rapor sudah siap walau email belum bisa keluar.
    await _notify_in_app(db, ctx=ctx, month=month, recipients=recipients, run=run)

    smtp = email_sender.smtp_status(cfg)
    if not smtp["configured"]:
        run.update({
            "status": "skipped_no_smtp",
            "message": ("SMTP belum dikonfigurasi. Rapor sudah dibuat & ringkasannya "
                        "dikirim sebagai notifikasi dalam aplikasi; isi Pengaturan "
                        "Notifikasi → Email (SMTP) agar lampiran bisa dikirim otomatis."),
            "finished_at": _now(),
        })
        await db[RUNS_COLL].insert_one(dict(run))
        run.pop("_id", None)
        return run

    if not recipients:
        run.update({
            "status": "no_recipients",
            "message": ("Belum ada penerima: tidak ada user ber-role keuangan yang punya "
                        "email, dan daftar email tambahan kosong."),
            "finished_at": _now(),
        })
        await db[RUNS_COLL].insert_one(dict(run))
        run.pop("_id", None)
        return run

    # 4) Kirim satu per satu (alamat penerima tidak saling terlihat)
    sent, failed, errors = 0, 0, []
    for r in recipients:
        res = await email_sender.send_email(
            cfg, to=r["email"], subject=subject, body_text=body_text,
            body_html=body_html, attachments=attachments,
        )
        if res.get("ok"):
            sent += 1
        else:
            failed += 1
            errors.append({"email": r["email"], "error": res.get("error")})

    run.update({
        "status": "sent" if sent and not failed else ("partial" if sent else "failed"),
        "sent_count": sent,
        "failed_count": failed,
        "errors": errors[:20],
        "smtp": {"host": smtp["host"], "port": smtp["port"], "security": smtp["security"],
                 "from_email": smtp["from_email"]},
        "finished_at": _now(),
        "duration_ms": int((_now() - started).total_seconds() * 1000),
    })
    run["message"] = (
        f"Rapor {month} terkirim ke {sent} penerima "
        f"({len(attachments)} lampiran)." if sent else
        f"Gagal mengirim rapor {month}: {errors[0]['error'] if errors else 'tidak diketahui'}"
    )
    await db[RUNS_COLL].insert_one(dict(run))
    run.pop("_id", None)
    _log.info("[valuation-mail] %s → %s", month, run["message"])
    return run


async def _notify_in_app(db, *, ctx: dict, month: str, recipients: list[dict],
                         run: dict) -> int:
    """Notifikasi dalam aplikasi ke user keuangan (+admin) berisi ringkasan rapor."""
    try:
        from routes.notifications import create_notification

        users = await resolve_role_recipients(
            db, tuple(FINANCE_ROLES) + ("superadmin", "admin", "owner"))
        if not users:
            return 0
        t = ctx["summary"]["totals"]
        period = export.period_label(month)
        title = f"Rapor valuasi aksesoris {period} siap"
        body = (
            f"Nilai persediaan aksesoris {_rp(t.get('total_value'))} · "
            f"{t.get('valued_items', 0)} item bernilai · "
            f"{t.get('unvalued_items', 0)} item belum dinilai · "
            f"{len(ctx['movements'])} mutasi bernilai pada periode {period}.\n"
            f"Lampiran Excel & PDF dikirim ke: "
            f"{', '.join(r['email'] for r in recipients) or '(belum ada penerima email)'}.\n"
            f"Bisa juga diunduh manual di Aksesoris → Valuasi HPP → Rapor valuasi."
        )
        n = 0
        for u in users:
            await create_notification(
                db, user_id=u["id"], notif_type="stock", title=title, content=body,
                source_type="acc_valuation_report", source_id=run["id"],
                source_url="#wh-accessory",
                metadata={"report_month": month, "report_run_id": run["id"],
                          "link_module": "wh-accessory", "hub_tab": "valuasi",
                          "total_value": t.get("total_value", 0),
                          "unvalued_items": t.get("unvalued_items", 0)},
            )
            n += 1
        return n
    except Exception:  # noqa: BLE001 — notifikasi bukan alasan menggagalkan rapor
        _log.warning("[valuation-mail] notifikasi dalam aplikasi gagal", exc_info=True)
        return 0
