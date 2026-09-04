"""
Background scheduler for CV. Dewi Aditya ERP.
Uses APScheduler AsyncIOScheduler running inside the FastAPI event loop.

Currently registered jobs:
- scan_overdue_invoices: runs once a day at 08:00 server time. Idempotent.
  Logs each run to `dewi_scheduler_runs` for admin audit.

To add a new job: register it inside register_jobs(scheduler) below.
"""
import logging
import uuid
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from database import get_db

logger = logging.getLogger(__name__)

# Module-level singleton; set by start_scheduler(), used by API to introspect.
_scheduler: AsyncIOScheduler | None = None


# ══════════════════════════════════════════════════════════════════════════════
# JOBS
# ══════════════════════════════════════════════════════════════════════════════

async def job_scan_overdue_invoices():
    """Run notification scan-overdue. Idempotent (won't duplicate notifs)."""
    db = get_db()
    started = datetime.now(timezone.utc)
    run_doc = {
        'job_id': 'scan_overdue_invoices',
        'started_at': started,
        'status': 'running',
    }
    res = await db.dewi_scheduler_runs.insert_one(run_doc)
    run_id = res.inserted_id

    try:
        from routes.dewi_notifications import queue_for_client
        from datetime import date

        today = date.today().isoformat()
        invoices = await db.dewi_maklon_invoices.find({
            'status': {'$in': ['issued', 'partial_paid', 'overdue']},
            'balance_amount': {'$gt': 0},
            'due_date': {'$lt': today},
        }).to_list(length=5000)

        queued = 0
        for inv in invoices:
            existing = await db.notifications.find_one({
                'type':        'dewi',
                'subtype':     'invoice_overdue',
                'source_ref':  inv.get('id'),
            })
            if existing:
                continue
            client_id = inv.get('client_id')
            if not client_id:
                continue
            body = (
                f"Invoice {inv.get('invoice_number')} sebesar Rp "
                f"{int(inv.get('balance_amount', 0)):,} sudah lewat jatuh tempo "
                f"({inv.get('due_date')}). Mohon segera lakukan pembayaran."
            ).replace(',', '.')
            ids = await queue_for_client(
                db,
                client_id=client_id,
                subject=f"[OVERDUE] Invoice {inv.get('invoice_number')}",
                body=body,
                event_type='invoice_overdue',
                source_ref=inv.get('id'),
                meta={
                    'invoice_number': inv.get('invoice_number'),
                    'balance': inv.get('balance_amount'),
                    'auto_run': True,
                },
            )
            queued += len(ids)

        finished = datetime.now(timezone.utc)
        await db.dewi_scheduler_runs.update_one(
            {'_id': run_id},
            {'$set': {
                'status': 'success',
                'finished_at': finished,
                'duration_ms': int((finished - started).total_seconds() * 1000),
                'invoices_checked': len(invoices),
                'notifs_queued': queued,
            }},
        )
        logger.info(
            f"[scheduler] scan_overdue_invoices: checked={len(invoices)} queued={queued}"
        )
        return {'invoices_checked': len(invoices), 'notifs_queued': queued}
    except Exception as e:
        logger.exception("[scheduler] scan_overdue_invoices failed")
        await db.dewi_scheduler_runs.update_one(
            {'_id': run_id},
            {'$set': {
                'status': 'failed',
                'finished_at': datetime.now(timezone.utc),
                'error': str(e),
            }},
        )
        raise


async def job_birthday_anniversary_reminders():
    """Daily 07:00 — scan employees for birthday & work-anniversary today, notify HR."""
    db = get_db()
    started = datetime.now(timezone.utc)
    run_doc = {'job_id': 'birthday_anniversary_reminders', 'started_at': started, 'status': 'running'}
    res = await db.dewi_scheduler_runs.insert_one(run_doc)
    run_id = res.inserted_id
    try:
        from datetime import date
        today = date.today()
        mm = f"{today.month:02d}"
        dd = f"{today.day:02d}"
        # Find employees born on this date
        emps = await db.rahaza_employees.find(
            {"active": True},
            {"_id": 0, "id": 1, "name": 1, "employee_code": 1, "birth_date": 1, "joined_at": 1}
        ).to_list(length=10000)

        bdays, annivs = [], []
        for e in emps:
            bd = e.get("birth_date") or ""
            if len(bd) >= 10 and bd[5:10] == f"{mm}-{dd}":
                try:
                    year = int(bd[:4])
                    age = today.year - year
                except Exception:
                    age = 0
                bdays.append({"name": e["name"], "code": e["employee_code"], "age": age})

            ja = e.get("joined_at") or ""
            if len(ja) >= 10 and ja[5:10] == f"{mm}-{dd}":
                try:
                    year = int(ja[:4])
                    years = today.year - year
                except Exception:
                    years = 0
                if years > 0:
                    annivs.append({"name": e["name"], "code": e["employee_code"], "years": years})

        # Queue notifications to HR admins (SSOT type='rahaza')
        created = 0
        if bdays or annivs:
            from routes.rahaza_notifications import publish_notification

            # Find HR recipients
            hr_users = await db.users.find(
                {"role": {"$in": ["superadmin", "admin", "owner", "hr", "manager"]}},
                {"_id": 0, "id": 1, "name": 1}
            ).to_list(100)
            hr_user_ids = [u["id"] for u in hr_users if u.get("id")]

            for bd in bdays:
                title = f"🎂 Ulang Tahun: {bd['name']} ({bd['age']} thn)"
                body_msg = f"{bd['code']} — {bd['name']} berulang tahun hari ini. Kirim ucapan!"
                if hr_user_ids:
                    await publish_notification(
                        db,
                        type_='birthday',
                        severity='info',
                        title=title,
                        message=body_msg,
                        link_module='hris_employees',
                        link_id=bd['code'],
                        target_user_ids=hr_user_ids,
                        target_roles=["superadmin", "admin", "owner", "hr", "manager"],
                        dedup_key=f"birthday::{bd['code']}::{started.date().isoformat()}",
                    )
                    created += 1
            for av in annivs:
                title = f"🎉 Work Anniversary: {av['name']} ({av['years']} tahun)"
                body_msg = (
                    f"{av['code']} — {av['name']} merayakan {av['years']} tahun bekerja. "
                    f"Berikan apresiasi!"
                )
                if hr_user_ids:
                    await publish_notification(
                        db,
                        type_='anniversary',
                        severity='info',
                        title=title,
                        message=body_msg,
                        link_module='hris_employees',
                        link_id=av['code'],
                        target_user_ids=hr_user_ids,
                        target_roles=["superadmin", "admin", "owner", "hr", "manager"],
                        dedup_key=f"anniversary::{av['code']}::{started.date().isoformat()}",
                    )
                    created += 1

        await db.dewi_scheduler_runs.update_one(
            {'_id': run_id},
            {'$set': {'status': 'success', 'finished_at': datetime.now(timezone.utc),
                      'result': {'birthdays': len(bdays), 'anniversaries': len(annivs), 'notifs_queued': created}}}
        )
        logger.info(f"[scheduler] birthday/anniversary: {len(bdays)} bd, {len(annivs)} anv, {created} notifs")
        return {'birthdays': len(bdays), 'anniversaries': len(annivs), 'notifs_queued': created}
    except Exception as e:
        logger.exception("[scheduler] birthday job failed")
        await db.dewi_scheduler_runs.update_one(
            {'_id': run_id},
            {'$set': {'status': 'failed', 'finished_at': datetime.now(timezone.utc), 'error': str(e)}}
        )
        raise


# Registry of jobs that admin API can introspect & trigger manually.
async def job_kpi_deadline_reminders():
    """
    Daily job (09:00): cek periode KPI dengan close_date 7, 3, atau 1 hari lagi.
    Kirim notifikasi ke HR dan karyawan yang belum mengisi form.
    """
    from routes.rahaza_notifications import publish_notification
    from datetime import date

    db = get_db()
    today = date.today()
    started = datetime.now(timezone.utc)

    run_doc = {
        'job_id': 'kpi_deadline_reminders',
        'started_at': started,
        'status': 'running',
    }
    res = await db.dewi_scheduler_runs.insert_one(run_doc)
    run_id = res.inserted_id

    sent = 0
    try:
        # Find open periods with close_date in 7, 3, or 1 days
        open_periods = await db.da_kpi_periods.find(
            {"status": "open"},
            {"_id": 0, "period_id": 1, "name": 1, "close_date": 1, "participant_employee_ids": 1}
        ).to_list(2000)

        for period in open_periods:
            close_date_str = period.get("close_date")
            if not close_date_str:
                continue

            try:
                close_date = date.fromisoformat(close_date_str[:10])
            except Exception:
                continue

            days_left = (close_date - today).days
            if days_left not in (7, 3, 1):
                continue

            period_name = period.get("name", "")
            participant_ids = period.get("participant_employee_ids", [])

            # Find employees who haven't submitted self-assessment
            submitted_ids = await db.da_kpi_submissions.distinct(
                "evaluator_id",
                {"period_id": period["period_id"], "eval_type": "self", "status": "submitted"}
            )
            pending_ids = [eid for eid in participant_ids if eid not in submitted_ids]

            # Get user_ids for pending employees
            pending_emps = await db.rahaza_employees.find(
                {"id": {"$in": pending_ids}},
                {"_id": 0, "id": 1, "name": 1, "user_id": 1}
            ).to_list(2000)

            pending_user_ids = [e["user_id"] for e in pending_emps if e.get("user_id")]

            urgency = "‼️" if days_left == 1 else ("⚠️" if days_left == 3 else "🔔")
            msg_prefix = "MENDESAK: " if days_left == 1 else ""

            # Notify pending employees
            if pending_user_ids:
                dedup = f"kpi_emp_deadline_{period['period_id']}_{days_left}d"
                await publish_notification(
                    db,
                    type_="kpi_deadline",
                    severity="warning" if days_left <= 3 else "info",
                    title=f"{urgency} {msg_prefix}KPI Self-Assessment — {days_left} hari lagi",
                    message=(
                        f"{msg_prefix}Form self-assessment KPI periode '{period_name}' "
                        f"akan ditutup dalam {days_left} hari ({close_date_str}). "
                        f"Segera isi sebelum deadline!"
                    ),
                    link_module="kpi_portal",
                    link_id=period["period_id"],
                    target_user_ids=pending_user_ids,
                    dedup_key=dedup,
                )
                sent += len(pending_user_ids)

            # Notify HR about pending count
            dedup_hr = f"kpi_hr_deadline_{period['period_id']}_{days_left}d"
            await publish_notification(
                db,
                type_="kpi_deadline",
                severity="warning" if days_left <= 3 else "info",
                title=f"{urgency} KPI Deadline: {days_left} hari lagi — {period_name}",
                message=(
                    f"{len(pending_ids)} karyawan belum mengisi self-assessment untuk periode '{period_name}'. "
                    f"Deadline: {close_date_str} ({days_left} hari lagi)."
                ),
                link_module="hr_kpi",
                link_id=period["period_id"],
                target_roles=["hr", "superadmin", "admin"],
                dedup_key=dedup_hr,
            )
            sent += 1

        await db.dewi_scheduler_runs.update_one(
            {'_id': run_id},
            {'$set': {'status': 'ok', 'sent': sent, 'finished_at': datetime.now(timezone.utc)}}
        )
    except Exception as e:
        logger.exception("[scheduler] kpi_deadline_reminders error: %s", e)
        await db.dewi_scheduler_runs.update_one(
            {'_id': run_id},
            {'$set': {'status': 'error', 'error': str(e), 'finished_at': datetime.now(timezone.utc)}}
        )


async def job_auto_create_tasks_from_templates():
    """
    Auto-create task dari marketing_task_templates berdasarkan recurrence config.
    Dijalankan setiap hari pukul 06:00.
    Recurrence types:
      - daily     : buat task setiap hari
      - weekly    : buat task pada hari tertentu (recurrence_config.day_of_week: 0=Mon, 6=Sun)
      - monthly   : buat task pada tanggal tertentu (recurrence_config.day_of_month: 1-31)
    Idempotent: cek apakah task dengan template_id + due_date hari ini sudah ada.
    """
    db = get_db()
    run_id = (await db.dewi_scheduler_runs.insert_one({
        'job': 'auto_create_tasks_from_templates',
        'started_at': datetime.now(timezone.utc),
        'status': 'running',
    })).inserted_id

    try:
        today = datetime.now(timezone.utc).date()
        today_str = today.isoformat()
        weekday = today.weekday()      # 0=Monday, 6=Sunday
        day_of_month = today.day

        templates = await db.marketing_task_templates.find(
            {'is_active': True}, {'_id': 0}
        ).to_list(2000)

        created = 0
        skipped = 0

        for tmpl in templates:
            recurrence = tmpl.get('recurrence', 'none')
            cfg = tmpl.get('recurrence_config') or {}

            # Decide if we should create today
            should_create = False
            if recurrence == 'daily':
                should_create = True
            elif recurrence == 'weekly':
                target_day = int(cfg.get('day_of_week', 0))
                should_create = (weekday == target_day)
            elif recurrence == 'monthly':
                target_day = int(cfg.get('day_of_month', 1))
                should_create = (day_of_month == target_day)

            if not should_create:
                skipped += 1
                continue

            # Idempotency: skip if task already created today from this template
            existing = await db.marketing_tasks.find_one({
                'template_id': tmpl['id'],
                'due_date': today_str,
            })
            if existing:
                skipped += 1
                continue

            # Generate task code
            count = await db.marketing_tasks.count_documents({})
            task_code = f"TKS-{str(count + 1 + created).zfill(4)}"

            task_doc = {
                'id': str(uuid.uuid4()),
                'task_code': task_code,
                'template_id': tmpl['id'],
                'title': tmpl.get('title', ''),
                'description': tmpl.get('description', ''),
                'task_type': tmpl.get('task_type', 'regular'),
                'recurrence': recurrence,
                'recurrence_config': cfg,
                'assigned_to': None,          # Template assigns by role, not user
                'assigned_role': tmpl.get('default_assigned_role'),
                'assigned_by': 'scheduler',
                'account_id': tmpl.get('account_id'),
                'priority': tmpl.get('priority', 'medium'),
                'due_date': today_str,
                'status': 'to_do',
                'checklist': [
                    {'text': item, 'done': False}
                    for item in (tmpl.get('checklist_template') or [])
                ],
                'attachments': [],
                'completion_notes': '',
                'approval_status': None,
                'approved_by': None,
                'approved_at': None,
                'auto_created': True,
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc),
            }

            await db.marketing_tasks.insert_one(task_doc)
            created += 1

        await db.dewi_scheduler_runs.update_one(
            {'_id': run_id},
            {'$set': {
                'status': 'ok',
                'created': created,
                'skipped': skipped,
                'templates_checked': len(templates),
                'finished_at': datetime.now(timezone.utc),
            }}
        )

        logger.info("[scheduler] auto_create_tasks: created=%d, skipped=%d", created, skipped)

    except Exception as e:
        logger.exception("[scheduler] auto_create_tasks error: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# P1-7: FILE CLEANUP JOB (Marketing Uploads > 30 Days)
# ══════════════════════════════════════════════════════════════════════════════

async def job_cleanup_old_marketing_uploads():
    """
    D24 / F0.6(e) 2026-08-12 — DULU menunjuk `/app/uploads/marketing` yang TIDAK PERNAH
    ADA, jadi job ini tidak pernah membersihkan apa pun sejak dibuat (log-nya hanya
    "not found, skipping" sehingga terlihat sehat). Folder unggahan yang benar-benar
    dipakai jalur impor resmi adalah `/app/uploads/marketing-data-import`
    (lihat routes/marketing_data_import.py UPLOAD_DIR).

    Hapus berkas unggahan impor yang lebih dari 30 hari. Jalan setiap hari 02:00.
    """
    from datetime import datetime, timezone, timedelta
    from pathlib import Path

    try:
        uploads_dir = Path("/app/uploads/marketing-data-import")

        if not uploads_dir.exists():
            logger.info("[scheduler] cleanup_uploads: %s tidak ada, dilewati", uploads_dir)
            return
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        deleted_count = 0
        deleted_size = 0

        # 2026-08-12 — berkas YATIM juga dibersihkan (bukan hanya yang tua).
        # Sesi impor bisa hilang lebih cepat dari 30 hari (dihapus staf, atau sesi
        # pratinjau yang tidak pernah di-commit lalu dibuang). Berkasnya tetap
        # tertinggal dan tidak akan pernah bisa dipakai lagi oleh siapa pun —
        # satu sore uji saja meninggalkan 73 berkas (±18 MB) di disk pod.
        # Karena itu: berkas yang TIDAK ditunjuk sesi mana pun langsung dihapus.
        referenced: set = set()
        try:
            db = get_db()
            async for s in db["marketing_data_import_sessions"].find(
                    {}, {"_id": 0, "file_path": 1}):
                if s.get("file_path"):
                    referenced.add(str(s["file_path"]))
        except Exception:
            # Kalau daftar sesi tidak bisa dibaca, JANGAN menghapus apa pun sebagai
            # "yatim" — lebih baik menyisakan berkas daripada membuang bukti impor.
            referenced = None
            logger.exception("[scheduler] cleanup_uploads: gagal membaca daftar sesi "
                             "— pembersihan berkas yatim dilewati")

        orphan_count = 0
        # Scan all files in marketing uploads
        for file_path in uploads_dir.rglob("*"):
            if file_path.is_file():
                # Get file modification time
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                is_orphan = (referenced is not None
                             and str(file_path) not in referenced
                             # jeda 1 jam: sesi yang BARU dibuat mungkin belum
                             # tersimpan saat job berjalan
                             and file_mtime < datetime.now(timezone.utc) - timedelta(hours=1))

                if file_mtime < cutoff_date or is_orphan:
                    try:
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        deleted_count += 1
                        deleted_size += file_size
                        if is_orphan:
                            orphan_count += 1
                        logger.info(
                            "[scheduler] cleanup_uploads: deleted %s (%s)",
                            file_path.name,
                            "yatim — tidak ada sesi yang memakainya" if is_orphan
                            else f"umur {(datetime.now(timezone.utc) - file_mtime).days} hari")
                    except Exception as e:
                        logger.error(f"[scheduler] cleanup_uploads: failed to delete {file_path}: {e}")

        deleted_size_mb = deleted_size / (1024 * 1024)
        logger.info("[scheduler] cleanup_uploads: deleted %s files (%s yatim), freed %.2f MB",
                    deleted_count, orphan_count, deleted_size_mb)
        
    except Exception as e:
        # Note: This job doesn't register a scheduler_runs entry so we can't update
        # error status here. Just log the exception. (Session #11.17: removed undefined
        # `db` and `run_id` references that triggered ruff F821.)
        logger.exception("[scheduler] cleanup_uploads error: %s", e)


async def job_marketing_alerts():
    """
    Marketing Alert Engine — evaluates conditions and publishes in-app notifications.
    Runs every 30 minutes. Covers: expiring discounts, SLA breaches,
    upcoming product launches, and content scheduled today.
    """
    db = get_db()
    try:
        from routes.marketing_alerts import evaluate_marketing_alerts
        result = await evaluate_marketing_alerts(db=db)
        fired = result.get("total_fired", 0)
        logger.info(f"[scheduler] job_marketing_alerts: fired {fired} alerts")
    except Exception as e:
        logger.exception(f"[scheduler] job_marketing_alerts error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# JOB: AUTO-CREATE MARKETING ACTIONABLE TASKS (Phase 4)
# ══════════════════════════════════════════════════════════════════════════════
async def job_auto_create_marketing_tasks():
    """
    Auto-generate actionable marketing tasks based on business events:
    1. Missing sales data: For each active account, if yesterday's sales not yet entered,
       create task type='data_entry' with related_entity='sales_data' and pre-filled account_id+date.
    2. Health drop alert: For each account with health_score < 60 (and no recent alert task),
       create task type='analysis' with related_entity='manual_check' to investigate.
    
    Runs daily at 10:00 (after morning import window).
    """
    import uuid as _uuid
    from datetime import timedelta
    
    db = get_db()
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    
    created_sales_tasks = 0
    created_health_tasks = 0
    
    try:
        # ─── 1. MISSING SALES DATA TASKS ───
        active_accounts = await db.marketing_platform_accounts.find(
            {"status": "active"}, {"_id": 0}
        ).to_list(500)
        
        for acc in active_accounts:
            account_id = acc.get("id")
            account_name = acc.get("account_name") or acc.get("name", "")
            if not account_id:
                continue
            
            # Check if sales data already entered for yesterday
            existing_sales = await db.marketing_sales_data.find_one({
                "account_id": account_id,
                "date": yesterday,
            }, {"_id": 0})
            if existing_sales:
                continue
            
            # Check if task already created today for same purpose
            existing_task = await db.marketing_tasks.find_one({
                "account_id": account_id,
                "related_entity": "sales_data",
                "related_form_data.date": yesterday,
                "status": {"$ne": "cancelled"},
            }, {"_id": 0})
            if existing_task:
                continue
            
            # Create actionable task
            task_doc = {
                "id": str(_uuid.uuid4()),
                "task_code": f"TSK-{now.strftime('%Y%m%d')}-{_uuid.uuid4().hex[:6].upper()}",
                "title": f"Input Sales Harian — {account_name} ({yesterday})",
                "description": f"Sales data untuk {account_name} pada tanggal {yesterday} belum diinput. Mohon segera input revenue/orders/visitors.",
                "task_type": "data_entry",
                "recurrence": "one-time",
                "recurrence_config": {},
                "assigned_to": acc.get("pic_user_id"),  # PIC of this account, if set
                "assigned_by": "system",
                "account_id": account_id,
                "priority": "high",
                "due_date": None,
                "status": "to_do",
                "checklist": [],
                "attachments": [],
                "completion_notes": "",
                "approval_status": None,
                "approved_by": None,
                "approved_at": None,
                "related_entity": "sales_data",
                "related_entity_id": None,
                "related_form_data": {
                    "account_id": account_id,
                    "date": yesterday,
                },
                "action_type": "submit_form",
                "action_executed_at": None,
                "action_result": None,
                "source": "auto_generated",
                "created_at": now,
                "updated_at": now,
            }
            await db.marketing_tasks.insert_one(task_doc)
            created_sales_tasks += 1

            # ── Kirim in-app notification ke PIC ──
            pic_id = acc.get("pic_user_id")
            if pic_id:
                try:
                    from routes.rahaza_notifications import publish_notification
                    await publish_notification(
                        db,
                        type_="marketing_task_created",
                        severity="info",
                        title=f"Task Baru: Input Sales {account_name}",
                        message=f"Sales data {account_name} untuk {yesterday} belum diinput. Silakan eksekusi dari Laporan Harian atau Kanban.",
                        link_module="marketing-daily-report",
                        target_user_ids=[pic_id],
                        dedup_key=f"sales_task_notif_{account_id}_{yesterday}",
                    )
                except Exception as _ne:
                    logger.warning(f"[scheduler] Gagal kirim notif sales task: {_ne}")
        
        # ─── 2. HEALTH SCORE DROP TASKS ───
        critical_accounts = [
            a for a in active_accounts
            if a.get("health_score") is not None and a.get("health_score") < 60
        ]
        
        for acc in critical_accounts:
            account_id = acc.get("id")
            account_name = acc.get("account_name") or acc.get("name", "")
            health = acc.get("health_score", 0)
            
            # Check if alert task already created in last 7 days
            week_ago = now - timedelta(days=7)
            existing_alert = await db.marketing_tasks.find_one({
                "account_id": account_id,
                "task_type": "analysis",
                "title": {"$regex": "Health Score", "$options": "i"},
                "created_at": {"$gte": week_ago},
                "status": {"$ne": "cancelled"},
            }, {"_id": 0})
            if existing_alert:
                continue
            
            task_doc = {
                "id": str(_uuid.uuid4()),
                "task_code": f"TSK-{now.strftime('%Y%m%d')}-{_uuid.uuid4().hex[:6].upper()}",
                "title": f"⚠️ Health Score Drop — {account_name} ({health}/100)",
                "description": f"Akun {account_name} memiliki health score kritis ({health}/100). Mohon investigasi:\n"
                               f"• Cek complaint/return rate\n• Cek response rate ke customer\n• Cek shipping performance",
                "task_type": "analysis",
                "recurrence": "one-time",
                "recurrence_config": {},
                "assigned_to": acc.get("pic_user_id"),
                "assigned_by": "system",
                "account_id": account_id,
                "priority": "high",
                "due_date": None,
                "status": "to_do",
                "checklist": [
                    {"item": "Review 7-day complaint trend", "completed": False},
                    {"item": "Review return rate breakdown", "completed": False},
                    {"item": "Check shipping/cancellation rate", "completed": False},
                    {"item": "Create improvement plan", "completed": False},
                ],
                "attachments": [],
                "completion_notes": "",
                "approval_status": None,
                "approved_by": None,
                "approved_at": None,
                "related_entity": "manual_check",
                "related_entity_id": None,
                "related_form_data": {"account_id": account_id, "health_score": health},
                "action_type": "manual_check",
                "action_executed_at": None,
                "action_result": None,
                "source": "auto_generated_health_alert",
                "created_at": now,
                "updated_at": now,
            }
            await db.marketing_tasks.insert_one(task_doc)
            created_health_tasks += 1

            # ── Kirim in-app notification ke PIC ──
            pic_id = acc.get("pic_user_id")
            if pic_id:
                try:
                    from routes.rahaza_notifications import publish_notification
                    await publish_notification(
                        db,
                        type_="marketing_health_alert",
                        severity="warning",
                        title=f"⚠️ Health Score Kritis: {account_name}",
                        message=f"Akun {account_name} health score turun ke {health}/100. Task investigasi sudah dibuat.",
                        link_module="marketing-tasks",
                        target_user_ids=[pic_id],
                        dedup_key=f"health_alert_notif_{account_id}_{now.strftime('%Y-%m-%d')}",
                    )
                except Exception as _ne:
                    logger.warning(f"[scheduler] Gagal kirim notif health alert: {_ne}")
        
        logger.info(
            f"[scheduler] job_auto_create_marketing_tasks: "
            f"created {created_sales_tasks} sales tasks, {created_health_tasks} health alerts"
        )
    except Exception as e:
        logger.exception(f"[scheduler] job_auto_create_marketing_tasks error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# JOB: SCAN OVERDUE MARKETING TASKS — kirim notif ke assigned + PIC
# ══════════════════════════════════════════════════════════════════════════════
async def job_scan_overdue_marketing_tasks():
    """
    Scan marketing tasks yang overdue (due_date < now, status masih to_do/in_progress).
    Kirim in-app notification ke:
    - User yang di-assign (assigned_to)
    - PIC akun terkait (pic_user_id dari marketing_platform_accounts)

    Dedup: 1 notif per task per hari, cegah spam.
    Runs daily 17:00 WIB.
    """
    db  = get_db()
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    try:
        overdue_tasks = await db.marketing_tasks.find(
            {
                "status":   {"$in": ["to_do", "in_progress"]},
                "due_date": {"$lt": now.isoformat()},
            },
            {"_id": 0}
        ).to_list(500)

        if not overdue_tasks:
            logger.info("[scheduler] job_scan_overdue_marketing_tasks: tidak ada task overdue")
            return

        from routes.rahaza_notifications import publish_notification

        notif_count = 0
        for task in overdue_tasks:
            task_id    = task.get("id", "")
            title      = task.get("title", "")[:60]
            account_id = task.get("account_id")
            assigned   = task.get("assigned_to")

            # Resolve PIC dari akun
            pic_id = None
            acc_name = ""
            if account_id:
                acc = await db.marketing_platform_accounts.find_one(
                    {"id": account_id}, {"_id": 0, "pic_user_id": 1, "account_name": 1}
                )
                if acc:
                    pic_id   = acc.get("pic_user_id")
                    acc_name = acc.get("account_name", "")

            # Kumpulkan user target (dedup)
            target_ids = list({u for u in [assigned, pic_id] if u})
            if not target_ids:
                continue

            dedup_key = f"overdue_task_{task_id}_{today_str}"
            await publish_notification(
                db,
                type_="marketing_task_overdue",
                severity="warning",
                title=f"Task Overdue: {title}",
                message=(
                    f"Task '{title}'"
                    + (f" [{acc_name}]" if acc_name else "")
                    + " sudah melewati due date dan belum selesai. Segera selesaikan."
                ),
                link_module="marketing-tasks",
                link_id=task_id,
                target_user_ids=target_ids,
                dedup_key=dedup_key,
            )
            notif_count += 1

        logger.info(
            f"[scheduler] job_scan_overdue_marketing_tasks: "
            f"{len(overdue_tasks)} overdue tasks, {notif_count} notif sent"
        )
    except Exception as e:
        logger.exception(f"[scheduler] job_scan_overdue_marketing_tasks error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# JOB: LEAVE CARRY-FORWARD — setiap 1 Januari
# ══════════════════════════════════════════════════════════════════════════════
async def job_leave_carry_forward():
    """
    Carry-forward saldo cuti yang tersisa ke tahun berikutnya.
    Rules:
    - Hanya tipe cuti yang paid=True dan unpaid=False
    - Maksimal carry: min(remaining, max_carry_days) — default max 5 hari
    - Idempotent: skip jika balance tahun baru sudah dibuat
    Runs: 1 Januari pukul 01:00
    """
    db  = get_db()
    now = datetime.now(timezone.utc)
    new_year = now.year
    old_year = new_year - 1

    logger.info(f"[scheduler] job_leave_carry_forward: carry {old_year} → {new_year}")

    try:
        # Fetch leave types yang bisa carry forward
        carryable_types = await db.rahaza_leave_types.find(
            {"active": True, "unpaid": {"$ne": True}},
            {"_id": 0, "id": 1, "name": 1, "quota_default": 1, "max_carry_days": 1}
        ).to_list(100)

        if not carryable_types:
            logger.info("[scheduler] job_leave_carry_forward: no carryable leave types")
            return

        # Fetch active employees
        employees = await db.rahaza_employees.find(
            {"active": True}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(500)

        carry_count = 0
        for emp in employees:
            emp_id = emp["id"]
            for lt in carryable_types:
                lt_id       = lt["id"]
                max_carry   = int(lt.get("max_carry_days") or 5)  # default 5 hari carry

                # Cek balance tahun lama
                old_bal = await db.rahaza_leave_balances.find_one(
                    {"employee_id": emp_id, "leave_type_id": lt_id, "year": old_year},
                    {"_id": 0}
                )
                if not old_bal:
                    continue

                remaining = float(old_bal.get("allocated", 0)) - float(old_bal.get("used", 0))
                carry_days = min(max(remaining, 0), max_carry)
                if carry_days <= 0:
                    continue

                # Cek apakah balance tahun baru sudah ada
                new_bal = await db.rahaza_leave_balances.find_one(
                    {"employee_id": emp_id, "leave_type_id": lt_id, "year": new_year},
                    {"_id": 0}
                )
                if new_bal:
                    # Sudah ada — tambahkan carry ke allocated
                    if not new_bal.get("_carry_applied"):
                        await db.rahaza_leave_balances.update_one(
                            {"id": new_bal["id"]},
                            {"$inc": {"allocated": carry_days},
                             "$set": {"_carry_applied": True, "carry_from_year": old_year,
                                      "carry_days": carry_days, "updated_at": now}}
                        )
                        carry_count += 1
                else:
                    # Buat balance baru dengan quota + carry
                    quota = int(lt.get("quota_default", 12))
                    doc = {
                        "id":             str(__import__("uuid").uuid4()),
                        "employee_id":    emp_id,
                        "leave_type_id":  lt_id,
                        "year":           new_year,
                        "allocated":      quota + carry_days,
                        "used":           0,
                        "adjustments":    [],
                        "_carry_applied": True,
                        "carry_from_year": old_year,
                        "carry_days":     carry_days,
                        "created_at":     now,
                        "updated_at":     now,
                    }
                    await db.rahaza_leave_balances.insert_one(doc)
                    carry_count += 1

        logger.info(
            f"[scheduler] job_leave_carry_forward: "
            f"{carry_count} balances carried forward from {old_year} to {new_year}"
        )
    except Exception as e:
        logger.exception(f"[scheduler] job_leave_carry_forward error: {e}")


async def job_auto_database_backup():
    """Automated daily database backup at 02:00 Asia/Jakarta"""
    import asyncio
    from datetime import datetime
    
    db = get_db()
    started = datetime.now(timezone.utc)
    backup_name = f"auto_{started.strftime('%Y%m%d_%H%M%S')}"
    
    logger.info(f"[scheduler] job_auto_database_backup: Starting backup '{backup_name}'")
    
    try:
        # Run backup script
        process = await asyncio.create_subprocess_exec(
            '/app/scripts/backup.sh',
            backup_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            logger.info(f"[scheduler] job_auto_database_backup: Backup '{backup_name}' completed successfully")
            
            # Send notification to all superadmins
            try:
                from routes.rahaza_notifications import send_notification
                superadmins = await db.users.find({"role": "superadmin"}).to_list(length=100)
                for admin in superadmins:
                    await send_notification(
                        user_id=admin["id"],
                        title="✅ Auto Backup Berhasil",
                        message=f"Database backup otomatis '{backup_name}' telah dibuat dengan sukses",
                        type="success",
                        category="system"
                    )
            except Exception as e:
                logger.warning(f"Failed to send backup notification: {e}")
            
            # Cleanup old backups (retention: 30 days)
            try:
                cleanup_process = await asyncio.create_subprocess_exec(
                    '/app/scripts/cleanup_old_backups.sh',
                    '30',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await cleanup_process.communicate()
                logger.info("[scheduler] job_auto_database_backup: Cleanup old backups completed")
            except Exception as e:
                logger.warning(f"Backup cleanup failed: {e}")
            
        else:
            error_msg = stderr.decode()
            logger.error(f"[scheduler] job_auto_database_backup: Backup failed - {error_msg}")
            
            # Send error notification to superadmins
            try:
                from routes.rahaza_notifications import send_notification
                superadmins = await db.users.find({"role": "superadmin"}).to_list(length=100)
                for admin in superadmins:
                    await send_notification(
                        user_id=admin["id"],
                        title="❌ Auto Backup Gagal",
                        message=f"Database backup otomatis '{backup_name}' gagal: {error_msg[:200]}",
                        type="error",
                        category="system"
                    )
            except Exception as e:
                logger.warning(f"Failed to send error notification: {e}")
                
    except Exception as e:
        logger.error(f"[scheduler] job_auto_database_backup: Exception - {str(e)}")


async def job_daily_unvalued_digest():
    """Harian 07:30 — SATU notifikasi ringkasan semua aksesoris ber-HPP 0.

    Kenapa: alarm per-item (`notify_unvalued`) memberi tahu saat kejadian, tapi tidak
    pernah memberi gambaran utuh berapa item yang masih menggantung. Digest ini
    melengkapinya (per-item tetap jalan). Idempoten: maks 1× per tanggal Asia/Jakarta.
    """
    db = get_db()
    started = datetime.now(timezone.utc)
    res_ins = await db.dewi_scheduler_runs.insert_one({
        'job_id': 'daily_unvalued_digest', 'started_at': started, 'status': 'running'})
    run_id = res_ins.inserted_id
    try:
        from core import accessory_valuation

        out = await accessory_valuation.send_unvalued_digest(db)
        finished = datetime.now(timezone.utc)
        await db.dewi_scheduler_runs.update_one({'_id': run_id}, {'$set': {
            'status': 'success',
            'finished_at': finished,
            'duration_ms': int((finished - started).total_seconds() * 1000),
            'unvalued_items': out.get('items', 0),
            'notifs_sent': out.get('sent', 0),
            'skipped_reason': out.get('skipped'),
            'digest_date': out.get('date'),
        }})
        logger.info("[scheduler] daily_unvalued_digest: items=%s sent=%s skipped=%s",
                    out.get('items'), out.get('sent'), out.get('skipped'))
        return {'unvalued_items': out.get('items', 0), 'notifs_sent': out.get('sent', 0),
                'skipped': out.get('skipped'), 'date': out.get('date')}
    except Exception as e:
        logger.exception("[scheduler] daily_unvalued_digest failed")
        await db.dewi_scheduler_runs.update_one({'_id': run_id}, {'$set': {
            'status': 'failed', 'finished_at': datetime.now(timezone.utc), 'error': str(e)}})
        raise


async def job_cmt_daily_recap_reminder():
    """Harian **16:00 WIB** — tegur vendor CMT yang hari ini belum menyetor data.

    F12 — KENAPA DIJADWALKAN
    ------------------------
    Rekap Harian sudah bisa menegur, tetapi tombolnya harus **diklik orang**.
    Artinya teguran hanya terkirim di hari ketika supervisor ingat membuka layar
    itu — dan justru pada hari sibuk (saat vendor paling mungkin bolong) tidak
    ada yang ingat. Karena progress produksi adalah dasar **tagihan CMT**, hari
    yang tidak tertegur menjadi hari yang tidak bisa diperdebatkan lagi nanti.

    Jam 16.00 WIB dipilih pemilik: masih di dalam jam kerja vendor, jadi teguran
    hari itu masih bisa ditindaklanjuti hari itu juga (kalau dikirim malam,
    teguran hanya menjadi catatan sejarah).

    AMAN DIULANG. Pengirimannya lewat SSOT
    :func:`core.cmt_daily_recap.send_recap_reminders` yang idempoten **per vendor
    per tanggal**, jadi kalau job ini misfire lalu dijalankan ulang (atau
    supervisor juga menekan tombolnya), vendor tetap menerima SATU teguran.
    Sasarannya hanya vendor berstatus ``pending`` — vendor yang sudah menyetor
    sebagian (``partial``) TIDAK ditegur, karena menegur orang yang sudah bekerja
    adalah cara tercepat membuat teguran berikutnya diabaikan.
    """
    db = get_db()
    started = datetime.now(timezone.utc)
    res_ins = await db.dewi_scheduler_runs.insert_one({
        'job_id': 'cmt_daily_recap_reminder', 'started_at': started, 'status': 'running'})
    run_id = res_ins.inserted_id
    try:
        from core.cmt_daily_recap import send_recap_reminders
        from utils.waktu import today_wib

        day = today_wib()
        out = await send_recap_reminders(db, day, actor=None, source='scheduler')
        finished = datetime.now(timezone.utc)
        await db.dewi_scheduler_runs.update_one({'_id': run_id}, {'$set': {
            'status': 'success',
            'finished_at': finished,
            'duration_ms': int((finished - started).total_seconds() * 1000),
            'recap_date': out.get('date'),
            'candidates': out.get('candidates', 0),
            'reminders_sent': out.get('sent_count', 0),
            'reminders_skipped': out.get('skipped_count', 0),
        }})
        logger.info('[scheduler] cmt_daily_recap_reminder %s: kandidat=%s terkirim=%s '
                    'dilewati(sudah ada)=%s', out.get('date'), out.get('candidates'),
                    out.get('sent_count'), out.get('skipped_count'))
        return out
    except Exception as e:
        logger.exception('[scheduler] cmt_daily_recap_reminder failed')
        await db.dewi_scheduler_runs.update_one({'_id': run_id}, {'$set': {
            'status': 'failed', 'finished_at': datetime.now(timezone.utc), 'error': str(e)}})
        raise


async def job_monthly_valuation_report_email():
    """Tanggal 1 pukul 06:00 — kirim rapor valuasi aksesoris BULAN LALU ke keuangan.

    Lampiran Excel + PDF dibuat dari data nyata (`utils/accessory_valuation_export.py`)
    dan dikirim lewat SMTP yang diatur di Pengaturan Notifikasi. Idempoten per periode.
    """
    db = get_db()
    started = datetime.now(timezone.utc)
    res_ins = await db.dewi_scheduler_runs.insert_one({
        'job_id': 'monthly_valuation_report_email', 'started_at': started, 'status': 'running'})
    run_id = res_ins.inserted_id
    try:
        from services import accessory_valuation_mailer as mailer

        out = await mailer.send_monthly_report(db, source='scheduler')
        finished = datetime.now(timezone.utc)
        await db.dewi_scheduler_runs.update_one({'_id': run_id}, {'$set': {
            'status': 'success' if out.get('status') in ('sent', 'skipped_already_sent',
                                                         'skipped_no_smtp') else 'failed',
            'finished_at': finished,
            'duration_ms': int((finished - started).total_seconds() * 1000),
            'report_month': out.get('month'),
            'report_status': out.get('status'),
            'emails_sent': out.get('sent_count', 0),
            'emails_failed': out.get('failed_count', 0),
            'message': out.get('message'),
        }})
        logger.info("[scheduler] monthly_valuation_report_email: %s", out.get('message'))
        return {'month': out.get('month'), 'report_status': out.get('status'),
                'emails_sent': out.get('sent_count', 0),
                'emails_failed': out.get('failed_count', 0),
                'message': out.get('message')}
    except Exception as e:
        logger.exception("[scheduler] monthly_valuation_report_email failed")
        await db.dewi_scheduler_runs.update_one({'_id': run_id}, {'$set': {
            'status': 'failed', 'finished_at': datetime.now(timezone.utc), 'error': str(e)}})
        raise


from services.management_alerts import job_management_alerts  # noqa: E402
from services.rnd_decision_report import job_weekly_rnd_decision_report  # noqa: E402

JOB_REGISTRY = {
    'daily_unvalued_digest': {
        'fn': job_daily_unvalued_digest,
        'description': ('Ringkasan harian aksesoris ber-HPP 0 (satu notifikasi berisi semua '
                        'item belum dinilai) ke Admin Gudang/Aksesoris/Keuangan.'),
        'cron': {'hour': 7, 'minute': 30},
        'cron_label': 'Setiap hari pukul 07:30',
    },
    'monthly_valuation_report_email': {
        'fn': job_monthly_valuation_report_email,
        'description': ('Kirim rapor valuasi persediaan aksesoris bulan lalu (lampiran Excel '
                        '+ PDF) ke email tim keuangan.'),
        'cron': {'day': 1, 'hour': 6, 'minute': 0},
        'cron_label': 'Setiap tanggal 1 pukul 06:00',
    },
    'management_alerts': {
        'fn': job_management_alerts,
        'description': ('Peringatan manajemen: PO mendekati/melewati deadline dan piutang '
                        'jatuh tempo. Ambang hari diatur owner (dewi_mgmt_alert_config). '
                        'Idempoten (satu notifikasi per dokumen per hari).'),
        'cron': {'hour': 7, 'minute': 0},
        'cron_label': 'Setiap hari pukul 07:00',
    },
    'weekly_rnd_decision_report': {
        'fn': job_weekly_rnd_decision_report,
        'description': ('Rapor keputusan RnD mingguan: style disetujui, ditolak, dan yang '
                        'menunggu keputusan terlalu lama. Idempoten per pekan ISO.'),
        'cron': {'day_of_week': 'mon', 'hour': 8, 'minute': 0},
        'cron_label': 'Setiap Senin pukul 08:00',
    },
    'scan_overdue_invoices': {
        'fn': job_scan_overdue_invoices,
        'description': 'Scan invoice yang sudah lewat jatuh tempo dan kirim notif overdue.',
        'cron': {'hour': 8, 'minute': 0},
        'cron_label': 'Setiap hari pukul 08:00',
    },
    'birthday_anniversary_reminders': {
        'fn': job_birthday_anniversary_reminders,
        'description': 'Cek karyawan yang ulang tahun / work-anniversary hari ini, kirim notif ke HR.',
        'cron': {'hour': 7, 'minute': 0},
        'cron_label': 'Setiap hari pukul 07:00',
    },
    'kpi_deadline_reminders': {
        'fn': job_kpi_deadline_reminders,
        'description': 'Kirim reminder KPI deadline ke karyawan & HR (7/3/1 hari sebelum close_date).',
        'cron': {'hour': 9, 'minute': 0},
        'cron_label': 'Setiap hari pukul 09:00',
    },
    'auto_create_tasks_from_templates': {
        'fn': job_auto_create_tasks_from_templates,
        'description': 'Auto-create task dari template berdasarkan recurrence (daily/weekly/monthly) setiap pagi.',
        'cron': {'hour': 6, 'minute': 0},
        'cron_label': 'Setiap hari pukul 06:00',
    },
    'marketing_alerts': {
        'fn': job_marketing_alerts,
        'description': 'Evaluasi kondisi marketing (expiring discount, SLA breach, upcoming launch, content today) dan kirim notifikasi.',
        'cron': {'minute': '*/30'},   # Every 30 minutes
        'cron_label': 'Setiap 30 menit',
    },
    'auto_create_marketing_tasks': {
        'fn': job_auto_create_marketing_tasks,
        'description': 'Auto-create actionable tasks untuk missing sales data harian + alert health score drop.',
        'cron': {'hour': 10, 'minute': 0},
        'cron_label': 'Setiap hari pukul 10:00',
    },
    'cleanup_old_marketing_uploads': {
        'fn': job_cleanup_old_marketing_uploads,
        'description': 'P1-7: Hapus file upload marketing yang lebih dari 30 hari.',
        'cron': {'hour': 2, 'minute': 0},   # Every day at 02:00 AM
        'cron_label': 'Setiap hari pukul 02:00',
    },
    'scan_overdue_marketing_tasks': {
        'fn': job_scan_overdue_marketing_tasks,
        'description': 'Scan marketing tasks overdue, kirim notifikasi ke assigned user + PIC akun.',
        'cron': {'hour': 17, 'minute': 0},
        'cron_label': 'Setiap hari pukul 17:00',
    },
    'leave_carry_forward': {
        'fn': job_leave_carry_forward,
        'description': 'Carry-forward saldo cuti tahunan ke tahun berikutnya setiap 1 Januari.',
        'cron': {'month': 1, 'day': 1, 'hour': 1, 'minute': 0},
        'cron_label': 'Setiap 1 Januari pukul 01:00',
    },
    'auto_database_backup': {
        'fn': job_auto_database_backup,
        'description': 'Automated daily database backup with 30-day retention policy.',
        'cron': {'hour': 2, 'minute': 0},
        'cron_label': 'Setiap hari pukul 02:00',
    },
    # F12 — teguran Rekap Harian CMT tidak lagi bergantung pada seseorang yang
    # ingat mengklik tombol. Idempoten per vendor per tanggal (SSOT
    # `core/cmt_daily_recap.send_recap_reminders`), jadi aman walau job ini
    # misfire lalu dijalankan ulang bersamaan dengan tombol manual.
    'cmt_daily_recap_reminder': {
        'fn': job_cmt_daily_recap_reminder,
        'description': ('Tegur vendor CMT yang belum menyetor data hari ini '
                        '(Rekap Harian). Idempoten per vendor per tanggal.'),
        'cron': {'hour': 16, 'minute': 0},
        'cron_label': 'Setiap hari pukul 16:00 WIB',
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# LIFECYCLE
# ══════════════════════════════════════════════════════════════════════════════

def register_jobs(scheduler: AsyncIOScheduler):
    # PENTING (bug FASE 10): `CronTrigger(**cfg['cron'])` TIDAK mewarisi timezone
    # scheduler. APScheduler hanya menyuntikkan `scheduler.timezone` bila trigger
    # dikirim sebagai alias string ('cron'); kalau kita mengirim INSTANS trigger,
    # trigger memakai timezone LOKAL proses (di container ini Etc/UTC). Akibatnya
    # semua job selama ini jalan 7 jam lebih lambat dari labelnya ("08:00" =
    # 15:00 WIB). Timezone kini dikirim eksplisit agar cocok dengan `cron_label`.
    for job_id, cfg in JOB_REGISTRY.items():
        scheduler.add_job(
            cfg['fn'],
            CronTrigger(**cfg['cron'], timezone=scheduler.timezone),
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True,
        )


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler
    _scheduler = AsyncIOScheduler(timezone='Asia/Jakarta')
    register_jobs(_scheduler)
    _scheduler.start()
    logger.info(
        "[scheduler] started with jobs: %s",
        ', '.join(JOB_REGISTRY.keys()),
    )
    return _scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] stopped")


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler
