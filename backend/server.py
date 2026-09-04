"""
End-to-End Fashion ERP - Main Server
All route logic has been modularized into routes/ directory.
This file handles app initialization, middleware, and router registration.
"""
# ruff: noqa: E402
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from database import get_db, client
from auth import seed_initial_data
import os
import logging
from datetime import datetime, timezone
import time

app = FastAPI(
    title="CV. Dewi Aditya — ERP API",
    version="2.0.0",
    description="""
## CV. Dewi Aditya — End-to-End Garment ERP

Full-stack ERP for garment manufacturing (CV. Dewi Aditya).

### Portals
| Portal | Prefix | Description |
|--------|--------|-------------|
| **SDM / HRIS** | `/api/rahaza/` | HR, payroll, attendance, KPI |
| **Produksi** | `/api/rahaza/` | Work orders, WIP, line assignments |
| **Keuangan** | `/api/rahaza/`, `/api/finance/` | AR/AP, journals, bank recon |
| **Gudang** | `/api/rahaza/`, `/api/wms/` | Inventory, movements, materials |
| **Maklon** | `/api/rahaza/maklon-*` | CMT orders, client portal |
| **Marketing** | `/api/marketing/`, `/api/dewi/` | KOL, products, content |
| **Manajemen** | `/api/dewi/` | Dashboard, analytics, OKR |
| **Portal Saya** | `/api/dewi/portal/`, `/api/rahaza/` | Self-service HR |

### API Versioning (v1)
All endpoints are accessible under `/api/v1/*` as a unified namespace:
- `/api/v1/employees` → `/api/rahaza/employees`
- `/api/v1/payroll/runs` → `/api/rahaza/payroll-runs`
- `/api/v1/kpi/periods` → `/api/dewi/kpi/periods`
- `/api/v1/journals` → `/api/rahaza/journals`
- See `middleware/api_v1.py` for full mapping.

### Authentication
All endpoints require `Authorization: Bearer <jwt_token>`.
Obtain token via `POST /api/auth/login`.
    """,
    contact={
        "name": "CV. Dewi Aditya — IT Team",
        "email": "it@dewiaditya.co.id",
    },
    license_info={
        "name": "Proprietary",
        "url": "https://dewiaditya.co.id",
    },
    openapi_tags=[
        {"name": "auth", "description": "Authentication & session management"},
        {"name": "rahaza-master", "description": "Master data: employees, departments, shifts, lines"},
        {"name": "rahaza-payroll", "description": "Payroll profiles, runs, payslips, allowances"},
        {"name": "rahaza-salary", "description": "Salary adjustments & raise approval workflow"},
        {"name": "rahaza-attendance", "description": "Attendance events & overtime requests"},
        {"name": "rahaza-production", "description": "Production: models, BOM, work orders, WIP"},
        {"name": "rahaza-inventory", "description": "Materials, stock, movements, material issues"},
        {"name": "rahaza-journals", "description": "General Ledger journal entries"},
        {"name": "rahaza-accounting", "description": "COA, periods, cost centers, bank recon"},
        {"name": "rahaza-ar", "description": "Accounts Receivable: invoices, payments"},
        {"name": "rahaza-ap", "description": "Accounts Payable: invoices, disbursements"},
        {"name": "dewi-kpi", "description": "KPI periods, questions, submissions, results"},
        {"name": "dewi-okr", "description": "OKR tracker: objectives, key results"},
        {"name": "dewi-hr", "description": "HR AI features, training, peer feedback"},
        {"name": "marketing", "description": "KOL management, products, content calendar"},
        {"name": "maklon", "description": "CMT/Maklon orders, client portal"},
        {"name": "admin", "description": "Admin: users, roles, permissions, audit log"},
        {"name": "ai-monitor", "description": "AI usage cost tracking & monitoring"},
        {"name": "health", "description": "Health check & status"},
    ],
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── GLOBAL ERROR HANDLER ────────────────────────────────────────────────────
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import uuid as _uuid_module
import traceback as _traceback

@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    """Attach a unique request_id to every incoming request for log correlation."""
    req_id = request.headers.get('x-request-id') or _uuid_module.uuid4().hex[:12]
    request.state.request_id = req_id
    start = time.time()
    try:
        response = await call_next(request)
    except Exception as exc:
        # Catch escaping exceptions (should rarely happen since handlers exist)
        logger.error(
            f"[{req_id}] uncaught {request.method} {request.url.path} {type(exc).__name__}: {exc}",
            exc_info=True
        )
        response = JSONResponse(
            {"detail": "Internal server error", "request_id": req_id},
            status_code=500,
        )
    duration_ms = round((time.time() - start) * 1000, 1)
    response.headers['x-request-id'] = req_id
    response.headers['x-response-time-ms'] = str(duration_ms)
    # Log slow requests (>1s) for perf monitoring
    if duration_ms > 1000:
        logger.warning(f"[{req_id}] SLOW {request.method} {request.url.path} {duration_ms}ms status={response.status_code}")
    return response

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = getattr(request.state, 'request_id', '-')
    # FASE 19: `str(exc.detail)` DULU mengubah detail terstruktur menjadi repr Python
    # (`\"{'error': ..., 'code': ...}\"`) sehingga klien tak bisa membaca kode error
    # secara mesin — mis. webhook HMAC perlu membedakan SIGNATURE_INVALID dari
    # SECRET_NOT_CONFIGURED. Detail dict/list sekarang dipertahankan apa adanya,
    # dan `code` diangkat ke level atas agar mudah dicek klien.
    detail = exc.detail
    body = {"status": exc.status_code, "request_id": req_id}
    if isinstance(detail, (dict, list)):
        body["detail"] = detail
        if isinstance(detail, dict) and isinstance(detail.get("code"), str):
            body["code"] = detail["code"]
    else:
        body["detail"] = str(detail)
    return JSONResponse(body, status_code=exc.status_code)

def _jsonable_validation_errors(errors: list) -> list:
    """Buat daftar error Pydantic AMAN untuk `json.dumps`.

    ┌─ BUG NYATA (FASE 14) ──────────────────────────────────────────────────────┐
    │ Pydantic v2 menaruh **objek exception aslinya** di `ctx["error"]` ketika    │
    │ sebuah `@field_validator` melempar `ValueError`. `exc.errors()` karena itu  │
    │ mengandung `ValueError(...)` yang TIDAK BISA di-JSON-kan, sehingga          │
    │ `JSONResponse(...)` di handler ini melempar                                │
    │     TypeError: Object of type ValueError is not JSON serializable          │
    │ → FastAPI jatuh ke handler generik → klien menerima **HTTP 500 "Internal   │
    │ server error"** padahal yang terjadi cuma input tidak valid (HTTP 422).    │
    │                                                                            │
    │ Dampaknya SISTEMIK, bukan satu endpoint: SETIAP model dengan validator      │
    │ custom terkena. Reproduksi:                                                │
    │   PUT /api/dewi/maklon/orders/<id>/status                                   │
    │   {"status":"produksi","stage_qty_update":{"cutting":-5}}   → dulu 500      │
    │ Validasinya sendiri BENAR (menolak qty negatif); yang rusak cara            │
    │ MELAPORKANNYA — dan 500 menyembunyikan alasan sebenarnya dari user.         │
    │                                                                            │
    │ Kenapa gate `adversarial_5xx` tidak menangkapnya: probe-nya mengirim tipe   │
    │ data yang salah (string di kolom angka, dll.) yang ditolak oleh validator   │
    │ BAWAAN Pydantic (ctx-nya JSON-safe), tidak pernah menyentuh validator       │
    │ CUSTOM yang melempar ValueError.                                           │
    └────────────────────────────────────────────────────────────────────────────┘

    Nilai yang tidak bisa di-JSON-kan diubah jadi `str(...)` — pesan validator
    (mis. "stage_qty_update['cutting'] tidak boleh negatif") TETAP sampai ke user
    lewat field `msg`, jadi tidak ada informasi yang hilang.
    """
    def safe(v):
        if isinstance(v, (str, int, float, bool)) or v is None:
            return v
        if isinstance(v, dict):
            return {str(k): safe(x) for k, x in v.items()}
        if isinstance(v, (list, tuple, set)):
            return [safe(x) for x in v]
        return str(v)

    return [safe(e) for e in (errors or [])]


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, 'request_id', '-')
    errors = _jsonable_validation_errors(exc.errors())
    logger.warning(f"[{req_id}] Validation error on {request.method} {request.url.path}: {errors}")
    return JSONResponse(
        {"detail": "Invalid request data", "errors": errors, "request_id": req_id},
        status_code=422,
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, 'request_id', '-')
    tb = _traceback.format_exc()
    logger.error(
        f"[{req_id}] Unhandled {request.method} {request.url.path}: {type(exc).__name__}: {exc}\n{tb}"
    )
    return JSONResponse(
        {"detail": "Internal server error. Please try again later.", "request_id": req_id},
        status_code=500,
    )

# ─── STARTUP ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    await seed_initial_data()
    await create_indexes()
    # Vendor Portal indexes
    try:
        await create_vendor_portal_indexes()
    except Exception as e:
        logger.warning(f"vendor_portal indexes: {e}")
    # PT Rahaza master data seed (idempotent)
    try:
        from routes.rahaza_master import seed_rahaza_master_data
        await seed_rahaza_master_data()
        from routes.rahaza_production import seed_rahaza_production_data
        await seed_rahaza_production_data()
        # F2 — master kategori produk (K-2, 14 kategori). Idempoten: dropdown
        # kategori tidak boleh pernah kosong di container segar, sebab
        # `category_id` sekarang WAJIB valid saat membuat produk.
        from core.product_master import seed_default_categories
        await seed_default_categories(get_db())
    except Exception as e:
        logger.warning(f"Rahaza master seed: {e}")
    # Init persistent storage
    try:
        from storage import init_storage
        init_storage()
    except Exception as e:
        logger.warning(f"Storage init: {e}")
    # Start Alert Rule Engine background task (Phase 18A)
    try:
        start_alerts_bg()
        logger.info("Alert rule engine started")
    except Exception as e:
        logger.warning(f"Alert engine start failed: {e}")
    # Phase 5b: BOM data migration (idempotent — fix string versions + missing is_active)
    try:
        from routes.rahaza_bom import migrate_bom_data
        from database import get_db as _get_db
        await migrate_bom_data(_get_db())
        logger.info("BOM migration complete (string versions + is_active fixed)")
    except Exception as e:
        logger.warning(f"BOM migration: {e}")
    # Master Product cleanup: drop legacy/duplicate product collections IF EMPTY (safe)
    try:
        from database import get_db as _get_db_cleanup
        _dbc = _get_db_cleanup()
        _existing = await _dbc.list_collection_names()
        for _legacy in ("products", "product_variants", "rahaza_styles"):
            if _legacy in _existing:
                _cnt = await _dbc[_legacy].count_documents({})
                if _cnt == 0:
                    await _dbc.drop_collection(_legacy)
                    logger.info(f"🧹 Legacy product collection dropped (empty): {_legacy}")
                else:
                    logger.warning(f"Legacy collection '{_legacy}' NOT dropped — has {_cnt} docs (kept for safety)")
    except Exception as e:
        logger.warning(f"Legacy product cleanup: {e}")
    # Phase 7D: Auto-seed COA & Posting Profiles (out-of-the-box deployment)
    try:
        from database import get_db as _get_db_seed
        _db = _get_db_seed()
        
        # Auto-seed COA if empty
        coa_count = await _db.rahaza_coa_accounts.count_documents({})
        if coa_count == 0:
            logger.info("COA empty, auto-seeding...")
            from routes.rahaza_coa import seed_coa_accounts
            await seed_coa_accounts(_db)
            logger.info(f"✅ COA auto-seeded on startup ({coa_count} → {await _db.rahaza_coa_accounts.count_documents({})} accounts)")
        
        # Auto-seed Posting Profiles if empty
        pp_count = await _db.rahaza_posting_profiles.count_documents({})
        if pp_count == 0:
            logger.info("Posting Profiles empty, auto-seeding...")
            from routes.rahaza_posting_profiles import seed_posting_profiles
            await seed_posting_profiles(_db)
            logger.info(f"✅ Posting Profiles auto-seeded on startup ({pp_count} → {await _db.rahaza_posting_profiles.count_documents({})} profiles)")
        # Audit finance 2026-09-04: skema akun kanonik 4-digit (idempoten, aman diulang):
        # seed akun 4-digit yang belum ada (GRNI 2-1150, dsb), normalisasi tipe, nonaktifkan
        # legacy 3-digit tak terpakai, remap posting profile & channel mapping.
        from routes.rahaza_coa import seed_coa_accounts as _seed_coa_canon, migrate_coa_canonical
        from routes.rahaza_posting_profiles import upgrade_posting_profiles
        await _seed_coa_canon(_db)
        _rep = await migrate_coa_canonical(_db)
        _prof = await upgrade_posting_profiles(_db)
        from routes.rahaza_ar_canonical import migrate_ar_canonical
        _arc = await migrate_ar_canonical(_db)
        logger.info(f"COA kanonik: deactivated={len(_rep['deactivated'])} type_fixed={len(_rep['type_fixed'])} "
                    f"parent_fixed={len(_rep['parent_fixed'])} legacy_used={_rep['legacy_still_used']} "
                    f"profiles_updated={_prof['updated']} ar_canonical_updated={_arc['updated']}")
    except Exception as e:
        logger.warning(f"Phase 7D auto-seed: {e}")
    
    # Phase 4 P1: APScheduler (auto-scan-overdue daily 08:00)
    try:
        from utils.scheduler import start_scheduler
        start_scheduler()
        logger.info("APScheduler started (jobs: scan_overdue_invoices @ 08:00 Asia/Jakarta)")

        # F0.6 (2026-08-12) — job `retry_queued_imports` DIHAPUS bersama mesin impor AI
        # lama (`routes/universal_import.py`). Jalur impor resmi satu-satunya sekarang
        # `routes/marketing_data_import.py` (tanpa AI, tanpa antrean yang bisa macet),
        # jadi tidak ada sesi "queued" yang perlu di-retry berkala.
    except Exception as e:
        logger.warning(f"Scheduler start failed: {e}")
    # ── PENJAGA LIMIT FILE DESCRIPTOR MONGOD (temuan 2026-07-31) ─────────────
    # supervisord menjalankan mongod dengan soft limit nofile 1024. Saat backup/
    # restore database besar (186 koleksi), WiredTiger kena "Too many open files"
    # → WT_PANIC → mongod ABORT → restore putus separuh jalan & portal balas 500.
    # Config supervisor READ-ONLY, jadi limit dinaikkan RUNTIME saat startup dan
    # dijaga periodik (mongod bisa restart kapan saja). Detail: utils/mongod_fdlimit.py
    try:
        from utils.mongod_fdlimit import ensure_and_log as ensure_mongod_fd
        ensure_mongod_fd("startup")
        try:
            from utils.scheduler import get_scheduler as _get_sched_fd
            _sched_fd = _get_sched_fd()
            if _sched_fd is not None:
                _sched_fd.add_job(ensure_mongod_fd, "interval", minutes=5,
                                  id="mongod_fd_guard", replace_existing=True,
                                  kwargs={"context": "guard"})
                logger.info("APScheduler: mongod_fd_guard registered (interval 5m)")
        except Exception as e:
            logger.warning(f"mongod_fd_guard job registration failed: {e}")
    except Exception as e:
        logger.warning(f"mongod fd-limit guard failed: {e}")
    logger.info("CV. Dewi Aditya API started")


async def _ensure_unique_index(db, coll: str, keys: list, *, name: str,
                               partial: dict | None = None,
                               drop_conflicting: list | None = None):
    """Pasang indeks UNIK dengan aman pada koleksi yang mungkin sudah punya
    indeks non-unik untuk pola kunci yang sama (F0.5, 2026-08-12).

    MongoDB menolak dua indeks dengan pola kunci sama tetapi opsi berbeda
    (`IndexOptionsConflict`, code 85). Jadi: buang indeks lama yang disebutkan,
    lalu buat yang unik. Bila masih gagal karena **data duplikat**
    (`DuplicateKeyError`, code 11000), indeks TIDAK dipasang dan alasannya
    dicatat jelas — jalankan `backend/migrations/2026_08_12_sales_data_nested.py`
    untuk menggabungkan duplikat, lalu restart.
    """
    kwargs = {"unique": True, "name": name}
    if partial:
        kwargs["partialFilterExpression"] = partial
    for attempt in (1, 2):
        try:
            await db[coll].create_index(keys, **kwargs)
            return True
        except Exception as e:
            code = getattr(e, "code", None)
            if attempt == 1 and code in (85, 86):
                for old in (drop_conflicting or []):
                    try:
                        await db[coll].drop_index(old)
                        logger.info("[index] %s: indeks lama '%s' dibuang untuk "
                                    "digantikan indeks UNIK '%s'", coll, old, name)
                    except Exception:
                        pass
                continue
            if code == 11000:
                logger.error("[index] %s: indeks UNIK '%s' TIDAK dipasang — masih ada "
                             "DATA DUPLIKAT. Jalankan migrasi penggabung duplikat "
                             "lalu restart backend. Detail: %s", coll, name, e)
            else:
                logger.warning("[index] %s: gagal memasang '%s': %s", coll, name, e)
            return False


async def create_indexes():
    """Create MongoDB indexes for active collections only (PT Rahaza)."""
    db = get_db()
    try:
        # Auth / RBAC
        await db.users.create_index("email", unique=True)
        await db.roles.create_index("name", unique=True)
        await db.permissions.create_index("key", unique=True)
        await db.activity_logs.create_index([("timestamp", -1)])

        # MongoDB-backed Rate Limiter — TTL index for auto-cleanup
        await db.rate_limit_buckets.create_index("key")
        await db.rate_limit_buckets.create_index("ts")
        await db.rate_limit_buckets.create_index("expire_at", expireAfterSeconds=0)

        # Warehouse (reused) — only `warehouse_receiving` index retained.
        # `warehouse_locations`, `warehouse_stock`, `warehouse_movements`,
        # `warehouse_opname` indexes REMOVED in Session #11.16 Phase A
        # along with the collections themselves (SSOT successors:
        # wh_positions / rahaza_material_stock / rahaza_material_movements /
        # wh_opname_sessions2). See FORENSIC_04 Cluster 3.
        await db.warehouse_receiving.create_index("receipt_number", unique=True)
        await db.warehouse_receiving.create_index("status")
        await db.warehouse_receiving.create_index("created_at")

        # Accessories master index REMOVED in Session #11.16 Phase A
        # (`accessories` dropped — SSOT: rahaza_materials with type='accessory').
        # See FORENSIC_04 Cluster 1.

        # PT Rahaza master data — unique code on active records only
        # (use partial index so deactivated codes can be reused)
        pfe_active = {"partialFilterExpression": {"active": True}}
        # Drop old non-partial unique indexes if they exist
        for col in ["rahaza_locations", "rahaza_processes", "rahaza_shifts", "rahaza_machines", "rahaza_lines"]:
            try:
                await db[col].drop_index("code_1")
            except Exception:
                logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        try:
            await db["rahaza_employees"].drop_index("employee_code_1")
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

        await db.rahaza_locations.create_index("code", unique=True, **pfe_active)
        await db.rahaza_processes.create_index("code", unique=True)  # process seeded, no soft-delete reuse
        await db.rahaza_shifts.create_index("code", unique=True, **pfe_active)
        await db.rahaza_machines.create_index("code", unique=True, **pfe_active)
        # FASE 4: index rahaza_lines & rahaza_line_assignments dihapus (koleksi DELETE E10)
        await db.rahaza_employees.create_index("employee_code", unique=True, **pfe_active)

        # Rahaza production execution (Fase 4)
        await db.rahaza_models.create_index("code", unique=True, **pfe_active)
        await db.rahaza_sizes.create_index("code", unique=True, **pfe_active)
        await db.rahaza_wip_events.create_index([("line_id", 1), ("timestamp", -1)])
        await db.rahaza_wip_events.create_index([("process_id", 1), ("timestamp", -1)])
        await db.rahaza_wip_events.create_index("timestamp")
        await db.rahaza_wip_events.create_index([("event_date", -1)])                     # FIX: reports query
        await db.rahaza_wip_events.create_index([("event_type", 1), ("event_date", -1)])  # FIX: compound
        await db.rahaza_wip_events.create_index("process_code")                           # FIX: Pareto
        await db.rahaza_wip_events.create_index("operator_id")                            # FIX: payroll PCS

        # Rahaza orders (Fase 5)
        await db.rahaza_customers.create_index("code", unique=True, **pfe_active)
        await db.rahaza_orders.create_index("order_number", unique=True)
        await db.rahaza_orders.create_index("status")
        await db.rahaza_orders.create_index("order_date")
        await db.rahaza_orders.create_index("customer_id")

        # Rahaza BOM — unique (model_id, size_id, color) hanya untuk versi is_active=True.
        # Fase 1: color ditambahkan ke key agar BOM bisa PER-VARIAN (warna beda → BOM beda).
        # color kosong/null = BOM umum (berlaku semua warna).
        for idx_name in ("model_size_active_unique", "model_size_is_active_unique", "model_size_color_active_unique"):
            try:
                await db.rahaza_boms.drop_index(idx_name)
            except Exception:
                logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        await db.rahaza_boms.create_index(
            [("model_id", 1), ("size_id", 1), ("color", 1)],
            unique=True,
            name="model_size_color_active_unique",
            partialFilterExpression={"active": True, "is_active": True},
        )
        await db.rahaza_boms.create_index("model_id")

        # Fase 2 — Colors master + Model Variants (SKU unik per warna×size)
        await db.rahaza_colors.create_index("code", unique=True, **pfe_active)
        # SKU unik hanya untuk varian aktif (soft-deleted boleh reuse SKU)
        await db.rahaza_model_variants.create_index("sku", unique=True, **pfe_active)
        # Kombinasi (model, size, color) unik per varian aktif
        await db.rahaza_model_variants.create_index(
            [("model_id", 1), ("size_id", 1), ("color_id", 1)],
            unique=True, name="model_size_color_variant_unique",
            partialFilterExpression={"active": True},
        )
        await db.rahaza_model_variants.create_index("model_id")

        # FASE 4 (E10): index rahaza_work_orders dihapus (koleksi DELETE).
        # wip_events re-anchor job_id (E10) — index job_id utk payroll/HPP per job.
        await db.rahaza_wip_events.create_index("job_id")

        # Rahaza inventory (Fase 7)
        await db.rahaza_materials.create_index("code", unique=True, **pfe_active)
        await db.rahaza_materials.create_index("type")
        await db.rahaza_materials.create_index([("type", 1), ("active", 1)])          # Sprint 3.5: filter by type+active
        await db.rahaza_materials.create_index("min_stock_qty")                         # Sprint 3.5: low-stock queries
        await db.rahaza_material_stock.create_index([("material_id", 1), ("location_id", 1)], unique=True)
        await db.rahaza_material_stock.create_index("location_id")
        await db.rahaza_material_stock.create_index("material_id")                      # Sprint 3.5: stock lookups
        await db.rahaza_material_movements.create_index([("timestamp", -1)])
        await db.rahaza_material_movements.create_index("material_id")
        await db.rahaza_material_issues.create_index("mi_number", unique=True)
        await db.rahaza_material_issues.create_index("job_id")  # FASE 4 (E10): re-anchor job_id
        await db.rahaza_material_issues.create_index("status")

        # Rahaza attendance (Fase 8a)
        await db.rahaza_attendance_events.create_index([("employee_id", 1), ("date", 1)], unique=True)
        await db.rahaza_attendance_events.create_index("date")
        await db.rahaza_attendance_events.create_index("status")
        await db.rahaza_attendance_events.create_index("approval_status")  # Sprint 42 approval queue

        # Sprint 42 — Smart Auto-Attendance indexes
        await db.rahaza_webauthn_credentials.create_index("employee_id")
        await db.rahaza_webauthn_credentials.create_index("credential_id")
        await db.rahaza_webauthn_challenges.create_index("employee_id")
        await db.rahaza_webauthn_challenges.create_index("expires_at")
        await db.rahaza_zkteco_devices.create_index("ip")

        # Rahaza payroll (Fase 8b + 8c)
        await db.rahaza_payroll_profiles.create_index([("employee_id", 1), ("active", 1)])
        await db.rahaza_payroll_profiles.create_index("pay_scheme")
        await db.rahaza_payroll_runs.create_index("run_number", unique=True)
        await db.rahaza_payroll_runs.create_index([("period_from", 1), ("period_to", 1)])
        await db.rahaza_payroll_runs.create_index("status")
        await db.rahaza_payslips.create_index([("run_id", 1), ("employee_id", 1)])
        await db.rahaza_payslips.create_index("employee_id")

        # Sprint 42 — Salary Adjustments (Raise) with Dual Approval
        await db.rahaza_salary_adjustments.create_index("employee_id")
        await db.rahaza_salary_adjustments.create_index("manager_id")
        await db.rahaza_salary_adjustments.create_index("status")
        await db.rahaza_salary_adjustments.create_index([("created_at", -1)])
        await db.rahaza_salary_adjustments.create_index([("kpi_period_id", 1), ("employee_id", 1)])
        # P3 TD-010 Phase B (Session #11.12): notifications now SSOT-only — indexes
        # live alongside other SSOT indexes (see "Notifications SSOT" block below).

        # Rahaza finance (Fase 8.5)
        await db.rahaza_cost_centers.create_index([("code", 1), ("active", 1)])
        await db.rahaza_ar_invoices.create_index("invoice_number", unique=True)
        await db.rahaza_ar_invoices.create_index("status")
        await db.rahaza_ar_invoices.create_index("customer_id")
        await db.rahaza_ap_invoices.create_index("invoice_number", unique=True)
        await db.rahaza_ap_invoices.create_index("status")
        await db.rahaza_cash_accounts.create_index([("code", 1), ("active", 1)])
        await db.rahaza_cash_movements.create_index([("timestamp", -1)])
        await db.rahaza_cash_movements.create_index("account_id")
        await db.rahaza_expenses.create_index([("date", -1)])
        await db.rahaza_expenses.create_index("cost_center_id")

        # Rahaza costing / HPP (Fase 9)
        await db.rahaza_costing_settings.create_index("id", unique=True)
        # FASE 4 (E10): snapshot per-job — index unik lama work_order_id (non-partial)
        # bentrok dgn dokumen job-anchored (field null duplikat) → ganti partial unique.
        try:
            await db.rahaza_hpp_snapshots.drop_index("work_order_id_1")
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        await db.rahaza_hpp_snapshots.create_index(
            "job_id", unique=True, name="hpp_job_id_unique",
            partialFilterExpression={"job_id": {"$exists": True}})
        await db.rahaza_hpp_snapshots.create_index(
            "work_order_id", unique=True, name="hpp_wo_id_unique",
            partialFilterExpression={"work_order_id": {"$exists": True}})

        # FASE 4 (E10 DELETE): index rahaza_bundles & rahaza_andon_events dihapus.

        # Rahaza SOP (Phase 18D)
        await db.rahaza_model_process_sop.create_index([("model_id", 1), ("process_id", 1)])
        await db.rahaza_model_process_sop.create_index("active")

        # Rahaza Accounting Core (Phase F1)
        await db.rahaza_coa_accounts.create_index("code", unique=True)
        await db.rahaza_coa_accounts.create_index("type")
        await db.rahaza_coa_accounts.create_index("parent_code")
        await db.rahaza_coa_accounts.create_index("active")
        await db.rahaza_journal_entries.create_index("je_number", unique=True)
        await db.rahaza_journal_entries.create_index([("date", -1)])
        await db.rahaza_journal_entries.create_index("status")
        await db.rahaza_journal_entries.create_index("source_module")
        await db.rahaza_journal_lines.create_index("je_id")
        await db.rahaza_journal_lines.create_index([("account_code", 1), ("date", 1)])
        await db.rahaza_journal_lines.create_index("period_code")
        await db.rahaza_periods.create_index("period_code", unique=True)
        await db.rahaza_periods.create_index("year")

        # Rahaza Accounting Core (Phase F2 — Auto-posting)
        await db.rahaza_posting_profiles.create_index("event_type", unique=True)
        await db.rahaza_posting_profiles.create_index("active")
        # Idempotency: (source_module, source_ref) → exactly one active JE
        await db.rahaza_journal_entries.create_index([("source_module", 1), ("source_ref", 1), ("status", 1)])
        await db.rahaza_journal_lines.create_index("source_module")
        await db.rahaza_journal_lines.create_index("account_type")

        # Phase 21 — QC v2 + Downtime
        # FASE 4 (E10 DELETE): index rahaza_defect_codes & rahaza_qc_events dihapus (QC-2 BUANG).
        await db.rahaza_machine_downtime.create_index([("start_at", -1)])
        await db.rahaza_machine_downtime.create_index("machine_id")
        await db.rahaza_machine_downtime.create_index("status")
        # Phase 20C — AI
        await db.rahaza_ai_chat_history.create_index([("session_id", 1), ("created_at", 1)])
        await db.rahaza_ai_audit_logs.create_index([("created_at", -1)])
        await db.assistant_chat_history.create_index([("session_id", 1), ("created_at", 1)])
        
        # Phase 22A — Material Reservations & Shift Handovers
        # FASE 4 (E10 DELETE): index rahaza_material_reservations dihapus (per-WO).
        await db.rahaza_shift_handovers.create_index([("date", -1), ("shift_id", 1)])
        await db.rahaza_shift_handovers.create_index("shift_id")
        await db.rahaza_shift_handovers.create_index("supervisor_id")
        await db.rahaza_handover_templates.create_index("active")

        # M5: LKP indexes (race-condition safety + query performance)
        # FASE 4 (E10 DELETE): index rahaza_lkp dihapus (LKP per-WO).

        # Sprint 2.1: Purchase Orders (W-2)
        await db.rahaza_purchase_orders.create_index("po_number", unique=True)
        await db.rahaza_purchase_orders.create_index("status")
        await db.rahaza_purchase_orders.create_index("vendor_name")
        await db.rahaza_purchase_orders.create_index("supplier_id")
        await db.rahaza_purchase_orders.create_index("po_date")
        await db.rahaza_purchase_orders.create_index("created_at")

        # Portal Pengadaan (2026-08-06) — Master Supplier SSOT + price list
        await db.rahaza_suppliers.create_index("code", unique=True)
        await db.rahaza_suppliers.create_index("name_key", unique=True)
        await db.rahaza_suppliers.create_index("is_active")
        await db.rahaza_suppliers.create_index("categories")
        await db.rahaza_supplier_price_lists.create_index(
            [("supplier_id", 1), ("material_id", 1), ("uom", 1), ("is_active", 1)])
        await db.rahaza_supplier_price_lists.create_index("material_id")
        await db.rahaza_grn_inspections.create_index("supplier_id")

        # Sprint 2.3: Leave Management (HR-3)
        await db.rahaza_leave_types.create_index("code", unique=True, **pfe_active)
        await db.rahaza_leave_requests.create_index("employee_id")
        await db.rahaza_leave_requests.create_index("leave_type_id")
        await db.rahaza_leave_requests.create_index("status")
        await db.rahaza_leave_requests.create_index([("from_date", 1), ("to_date", 1)])
        await db.rahaza_leave_requests.create_index("created_at")

        # Sprint 3.1: HR Reports — fast attendance & payroll analytics
        await db.rahaza_attendance_events.create_index([("employee_id", 1), ("date", 1), ("status", 1)])
        await db.rahaza_attendance_events.create_index([("date", 1), ("status", 1)])
        await db.rahaza_payslips.create_index([("run_id", 1), ("status", 1)])
        await db.rahaza_payslips.create_index([("pay_period_from", 1), ("pay_period_to", 1)])

        # Sprint 3.4: Low stock — fast threshold queries
        await db.rahaza_materials.create_index([("type", 1), ("active", 1)])
        await db.rahaza_material_stock.create_index([("material_id", 1), ("quantity", 1)])

        # Phase 4: Maklon Client Portal (external auth)
        await db.dewi_client_users.create_index("email", unique=True)
        await db.dewi_client_users.create_index("client_id")
        await db.dewi_client_users.create_index([("client_id", 1), ("status", 1)])

        # ─── CV. Dewi Aditya — Maklon collections (Phase 2/3) ────────────────
        # Cutting & CMT
        # FASE 4 (E10 DELETE): index dewi_cutting_requests/batches dihapus (cutting engine lama).
        await db.dewi_cmt_partners.create_index("code", unique=True)
        await db.dewi_cmt_jobs.create_index("job_code", unique=True)
        await db.dewi_cmt_jobs.create_index([("partner_id", 1), ("status", 1)])

        # Maklon — clients, orders
        # P1.B cleanup (2026-05-23): dewi_maklon_orders dropped, SSOT is dewi_maklon_pos
        await db.dewi_maklon_clients.create_index("code", unique=True)
        await db.dewi_maklon_clients.create_index("status")

        # Maklon — samples
        await db.dewi_maklon_samples.create_index("sample_code", unique=True)
        await db.dewi_maklon_samples.create_index([("order_id", 1), ("status", 1)])
        await db.dewi_maklon_samples.create_index([("client_id", 1), ("status", 1)])
        await db.dewi_maklon_sample_revisions.create_index([("sample_id", 1), ("created_at", -1)])

        # Maklon — QC
        await db.dewi_maklon_qc_checks.create_index([("order_id", 1), ("created_at", -1)])
        await db.dewi_maklon_qc_checks.create_index([("stage", 1), ("created_at", -1)])

        # Maklon — billing
        await db.dewi_maklon_invoices.create_index("invoice_number", unique=True)
        await db.dewi_maklon_invoices.create_index([("client_id", 1), ("status", 1)])
        await db.dewi_maklon_invoices.create_index("status")
        await db.dewi_maklon_invoices.create_index("issue_date")
        await db.dewi_maklon_invoices.create_index("due_date")
        await db.dewi_maklon_payments.create_index([("invoice_id", 1), ("payment_date", -1)])
        await db.dewi_maklon_hpp.create_index("order_id", unique=True)

        # System config
        await db.dewi_system_config.create_index("key", unique=True)
        await db.dewi_system_config.create_index("category")

        # ── Production-Maklon Overhaul Indexes (New Collections) ──────────────
        # Maklon PO (New)
        await db.dewi_maklon_pos.create_index("po_number", unique=True)
        await db.dewi_maklon_pos.create_index([("client_id", 1), ("status", 1)])
        await db.dewi_maklon_pos.create_index("status")
        await db.dewi_maklon_pos.create_index([("created_at", -1)])
        await db.dewi_maklon_pos.create_index("ar_invoice_id")

        # Maklon Dispatches (New)
        await db.dewi_maklon_dispatches.create_index("dispatch_number", unique=True)
        await db.dewi_maklon_dispatches.create_index([("po_id", 1), ("status", 1)])
        await db.dewi_maklon_dispatches.create_index("client_id")
        await db.dewi_maklon_dispatches.create_index([("created_at", -1)])

        # Maklon Material Receive (New)
        await db.dewi_maklon_material_receive.create_index("po_id")
        await db.dewi_maklon_material_receive.create_index([("created_at", -1)])

        # Maklon BOM (New)
        await db.dewi_maklon_bom.create_index("po_id", unique=True)

        # ── Phase M1: Buyer Catalog (Master Artikel Buyer Maklon) ─────────────
        await db.dewi_maklon_buyer_catalog.create_index("client_id")
        await db.dewi_maklon_buyer_catalog.create_index("status")
        await db.dewi_maklon_buyer_catalog.create_index(
            [("client_id", 1), ("artikel_code", 1)], unique=True
        )
        await db.dewi_maklon_buyer_catalog.create_index("buyer_ref_code")
        await db.dewi_maklon_buyer_catalog.create_index([("updated_at", -1)])

        # ── Phase M2.1: Sample → Buyer Catalog link ───────────────────────────
        await db.dewi_maklon_samples.create_index("buyer_catalog_id")

        # ── Phase M2.2: BOM Template (versioned) ──────────────────────────────
        await db.dewi_maklon_bom_templates.create_index("buyer_catalog_id")
        await db.dewi_maklon_bom_templates.create_index(
            [("buyer_catalog_id", 1), ("version", 1)], unique=True
        )
        await db.dewi_maklon_bom_templates.create_index(
            [("buyer_catalog_id", 1), ("is_active", 1)]
        )

        # Maklon Inventory (material milik klien)
        await db.dewi_maklon_inventory.create_index("maklon_po_ref")
        await db.dewi_maklon_inventory.create_index("maklon_client_id")
        await db.dewi_maklon_inventory.create_index([("created_at", -1)])

        # Maklon Advance Payments
        await db.dewi_maklon_advance_payments.create_index("po_id")
        await db.dewi_maklon_advance_payments.create_index([("created_at", -1)])

        # CMT Progress Reports (New)
        await db.dewi_cmt_progress_reports.create_index([("cmt_job_id", 1), ("report_date", -1)])
        await db.dewi_cmt_progress_reports.create_index([("cmt_partner_id", 1), ("report_date", -1)])
        await db.dewi_cmt_progress_reports.create_index("report_date")
        await db.dewi_cmt_progress_reports.create_index("process_step")

        # CMT Delivery Orders (New)
        await db.dewi_cmt_delivery_orders.create_index("do_number", unique=True)
        await db.dewi_cmt_delivery_orders.create_index([("cmt_job_id", 1), ("status", 1)])
        await db.dewi_cmt_delivery_orders.create_index("cmt_partner_id")
        await db.dewi_cmt_delivery_orders.create_index([("created_at", -1)])

        # Inventory ownership fields (extend existing)
        await db.rahaza_material_stock.create_index("ownership")
        await db.rahaza_material_stock.create_index("inventory_category")
        await db.rahaza_material_stock.create_index("maklon_client_id")

        # P3 TD-010 Phase B (Session #11.12): Notifications SSOT — all 4 legacy
        # domains (dewi/rahaza/collab/marketing_livehost) now write to `notifications`
        # via utils.notif_unified.notif_insert. Indexes consolidated here.
        await db.notifications.create_index([("type", 1), ("created_at", -1)])
        await db.notifications.create_index([("type", 1), ("status", 1), ("created_at", -1)])
        await db.notifications.create_index([("type", 1), ("user_id", 1), ("read", 1)])
        await db.notifications.create_index([("type", 1), ("host_id", 1), ("created_at", -1)])
        await db.notifications.create_index([("type", 1), ("subtype", 1), ("source_ref", 1)])
        await db.notifications.create_index([("type", 1), ("client_id", 1), ("created_at", -1)])
        await db.notifications.create_index([("type", 1), ("channel", 1)])
        await db.notifications.create_index([("type", 1), ("meta.dismissed", 1), ("meta.read_by", 1)])
        await db.notifications.create_index([("type", 1), ("meta.dedup_key", 1), ("created_at", -1)])
        await db.notifications.create_index("id", unique=True, sparse=True)
        # FASE 14 — dedup alarm/digest "belum dinilai" kini PER PENERIMA
        # (`distinct('user_id', …)`). Tanpa index ini query dedup memindai seluruh
        # koleksi `notifications` setiap mutasi aksesoris tanpa harga.
        await db.notifications.create_index(
            [("subtype", 1), ("meta.unvalued_material_id", 1), ("created_at", -1)])
        await db.notifications.create_index(
            [("meta.digest_kind", 1), ("meta.digest_date", 1), ("user_id", 1)])

        # P2 Consolidation #12 (Session #11.14): Shipping SSOT indexes
        # `wh_delivery_notes` (SSOT for Customer Shipping outbound)
        # `wh_cmt_dispatches` (SSOT for CMT vendor outbound)
        # Both supersede `rahaza_shipments` and `dewi_cmt_delivery_orders` (legacy).
        await db.wh_delivery_notes.create_index("id", unique=True, sparse=True)
        await db.wh_delivery_notes.create_index("sj_number", unique=True, sparse=True)
        await db.wh_delivery_notes.create_index("status")
        await db.wh_delivery_notes.create_index([("created_at", -1)])
        await db.wh_delivery_notes.create_index("customer_id")
        await db.wh_cmt_dispatches.create_index("id", unique=True, sparse=True)
        await db.wh_cmt_dispatches.create_index("dispatch_no", unique=True, sparse=True)
        await db.wh_cmt_dispatches.create_index("status")
        await db.wh_cmt_dispatches.create_index([("created_at", -1)])
        await db.wh_cmt_dispatches.create_index("cmt_partner_id")

        # Scheduler audit log
        await db.dewi_scheduler_runs.create_index([("job_id", 1), ("started_at", -1)])
        await db.dewi_scheduler_runs.create_index([("started_at", -1)])

        # Phase 5 Sprint 32 — Toko Online (catalog + channels)
        # P1.D cleanup (2026-05-23): legacy collections dropped. Indexes moved to marketing_* SSOT.
        # Preserved: dewi_toko_flashsales, dewi_toko_pack_batches (no marketing equivalent yet).

        # Phase 5B — Toko Online: preserved collections only
        await db.dewi_toko_pack_batches.create_index("batch_code", unique=True)
        await db.dewi_toko_pack_batches.create_index([("status", 1), ("created_at", -1)])
        await db.dewi_toko_flashsales.create_index([("status", 1), ("start_at", -1)])
        await db.dewi_toko_flashsales.create_index("channel_code")
        # Dewi-KOL legacy indexes REMOVED in Session #11.16 Phase C \u2014
        # collections `dewi_kol_creators` + `dewi_kol_deals` + `dewi_kol_samples`
        # DROPPED. SSOTs: marketing_kol_creators + marketing_kol_sessions +
        # marketing_creator_item_requests. See FORENSIC_04 Cluster 6.

        # Phase 6.2 — LMS
        await db.dewi_lms_courses.create_index("course_id", unique=True)
        await db.dewi_lms_courses.create_index([("status", 1), ("category", 1)])
        await db.dewi_lms_materials.create_index([("course_id", 1), ("order", 1)])
        await db.dewi_lms_enrollments.create_index([("course_id", 1), ("employee_id", 1)], unique=True)
        await db.dewi_lms_enrollments.create_index("employee_id")
        await db.dewi_lms_enrollments.create_index([("status", 1), ("enrolled_at", -1)])

        # Phase 6.3 — Onboarding
        await db.dewi_onboarding_templates.create_index("template_id", unique=True)
        await db.dewi_onboarding_checklists.create_index("checklist_id", unique=True)
        await db.dewi_onboarding_checklists.create_index("employee_id")
        await db.dewi_onboarding_checklists.create_index([("status", 1), ("start_date", -1)])

        # Phase 12 — Kasbon & Pinjaman Karyawan
        await db.dewi_kasbon_requests.create_index("id", unique=True)
        await db.dewi_kasbon_requests.create_index([("employee_id", 1), ("status", 1)])
        await db.dewi_kasbon_requests.create_index([("status", 1), ("created_at", -1)])
        await db.rahaza_channel_gl_mapping.create_index("id", unique=True)
        await db.rahaza_channel_gl_mapping.create_index("channel_key", unique=True)
        await db.rahaza_channel_gl_mapping.create_index([("platform", 1), ("active", 1)])
        await db.dewi_kasbon_requests.create_index("request_number", unique=True)

        # Phase 6.4 — Recruitment / ATS
        await db.dewi_recruitment_jobs.create_index("job_id", unique=True)
        await db.dewi_recruitment_jobs.create_index([("status", 1), ("created_at", -1)])
        await db.dewi_recruitment_candidates.create_index("candidate_id", unique=True)
        await db.dewi_recruitment_candidates.create_index([("job_id", 1), ("stage", 1)])
        await db.dewi_recruitment_candidates.create_index([("stage", 1), ("applied_at", -1)])

        # Phase 6.5 — Org Chart
        await db.dewi_org_units.create_index("unit_id", unique=True)
        await db.dewi_org_units.create_index("parent_id")
        await db.dewi_org_units.create_index([("level", 1), ("is_active", 1)])
        await db.dewi_org_positions.create_index("position_id", unique=True)
        await db.dewi_org_positions.create_index("unit_id")
        
        # Phase 8 — DA KPI System
        await db.da_kpi_periods.create_index("period_id", unique=True)
        await db.da_kpi_periods.create_index([("status", 1), ("created_at", -1)])
        await db.da_kpi_questions.create_index("question_id", unique=True)
        await db.da_kpi_questions.create_index([("eval_type", 1), ("order", 1)])
        await db.da_kpi_submissions.create_index("submission_id", unique=True)
        await db.da_kpi_submissions.create_index([("period_id", 1), ("evaluator_id", 1), ("eval_type", 1)])
        await db.da_kpi_submissions.create_index([("period_id", 1), ("evaluatee_id", 1), ("eval_type", 1)])
        await db.da_kpi_perform.create_index([("period_id", 1), ("employee_id", 1)], unique=True)
        await db.da_kpi_results.create_index("result_id", unique=True)
        await db.da_kpi_results.create_index([("period_id", 1), ("employee_id", 1)], unique=True)
        await db.da_kpi_results.create_index([("employee_id", 1), ("publish_status", 1)])

        # Phase 8.5 — DA Assets + Payroll Allowances
        await db.da_assets.create_index("asset_id", unique=True)
        await db.da_assets.create_index([("category", 1), ("status", 1)])
        await db.da_assets.create_index("asset_code", unique=True)
        await db.da_asset_assignments.create_index("assignment_id", unique=True)
        await db.da_asset_assignments.create_index([("asset_id", 1), ("status", 1)])
        await db.da_asset_assignments.create_index([("employee_id", 1), ("status", 1)])
        await db.da_payroll_allowances.create_index("allowance_id", unique=True)

        # Phase 7 — RnD & Style Master
        await db.dewi_rnd_styles.create_index("style_code", unique=True)
        await db.dewi_rnd_styles.create_index([("status", 1), ("created_at", -1)])
        await db.dewi_rnd_styles.create_index("category")
        await db.dewi_rnd_styles.create_index("buyer")
        await db.dewi_rnd_sample_requests.create_index("sample_code", unique=True)
        await db.dewi_rnd_sample_requests.create_index([("style_id", 1), ("created_at", -1)])
        await db.dewi_rnd_sample_requests.create_index([("status", 1), ("due_date", 1)])
        await db.dewi_rnd_revisions.create_index([("style_id", 1), ("revision_number", -1)])
        await db.dewi_rnd_materials.create_index("material_code", unique=True)
        await db.dewi_rnd_materials.create_index([("category", 1), ("status", 1)])
        await db.dewi_rnd_sample_costing.create_index([("sample_request_id", 1)])

        # ── Session 27 — GAP P0 SOP Indexes ──────────────────────────────────
        await db.dewi_accessory_requests.create_index("request_code", unique=True)
        await db.dewi_accessory_requests.create_index([("status", 1), ("created_at", -1)])
        await db.dewi_accessory_requests.create_index("sample_request_id")
        await db.dewi_accessory_requests.create_index("style_id")
        await db.dewi_accessory_requests.create_index([("urgent", 1), ("status", 1)])

        await db.dewi_kreator_requests.create_index("request_code", unique=True)
        await db.dewi_kreator_requests.create_index([("status", 1), ("created_at", -1)])
        await db.dewi_kreator_requests.create_index("kreator_type")
        await db.dewi_kreator_requests.create_index("kreator_id")
        await db.dewi_kreator_requests.create_index("style_id")

        await db.dewi_cmt_component_requests.create_index("request_code", unique=True)
        await db.dewi_cmt_component_requests.create_index([("status", 1), ("created_at", -1)])
        await db.dewi_cmt_component_requests.create_index("cmt_partner_id")
        await db.dewi_cmt_component_requests.create_index("work_order_id")
        await db.dewi_cmt_component_requests.create_index([("request_type", 1), ("status", 1)])
        await db.dewi_cmt_component_requests.create_index([("urgent", 1), ("status", 1)])

        # ── Marketing Portal (Phase 1–5) ──────────────────────────────────────
        # Indexes kritis untuk query performance (audit: 50-80% improvement)
        await db.marketing_platform_accounts.create_index("id", unique=True)
        await db.marketing_platform_accounts.create_index([("platform", 1), ("status", 1)])
        await db.marketing_platform_accounts.create_index("status")

        # ── F0.5 (2026-08-12) — KUNCI ALAMI dipagari indeks UNIK ─────────────
        # Sebelum ini `sales_account_date_type` hanya indeks biasa, sehingga satu
        # (toko, tanggal, jenis) bisa punya BANYAK dokumen ⇒ omzet bulanan bisa
        # terhitung dua kali tanpa satu pun galat. Migrasi
        # `2026_08_12_sales_data_nested.py` menggabungkan duplikat lebih dulu.
        await _ensure_unique_index(
            db, "marketing_sales_data",
            [("account_id", 1), ("date", 1), ("revenue_type", 1)],
            name="uniq_sales_account_date_type",
            drop_conflicting=["sales_account_date_type"],
        )
        # indeks lama non-unik dengan pola kunci nyaris sama: redundan setelah
        # indeks unik di atas terpasang (hemat memori & tulis).
        try:
            await db.marketing_sales_data.drop_index("sales_account_date_type")
        except Exception:
            pass
        await db.marketing_sales_data.create_index([("date", -1)])
        await db.marketing_sales_data.create_index("account_id")
        await db.marketing_sales_data.create_index("source")

        # Pesanan marketplace: 1 dokumen = 1 pesanan (SSOT §2)
        await _ensure_unique_index(
            db, "marketing_orders",
            [("account_id", 1), ("platform", 1), ("order_id", 1)],
            name="uniq_order_account_platform_orderid",
            partial={"order_id": {"$exists": True}},
        )
        await db.marketing_orders.create_index("account_id")
        await db.marketing_orders.create_index("items.platform_sku_id", sparse=True)
        await db.marketing_orders.create_index("order_channel", sparse=True)
        await db.marketing_orders.create_index("creator_handle", sparse=True)

        # Target & anggaran: satu baris per (toko, periode)
        await _ensure_unique_index(
            db, "marketing_account_targets",
            [("account_id", 1), ("year", 1), ("month", 1)],
            name="uniq_target_account_year_month")
        await _ensure_unique_index(
            db, "marketing_creator_targets",
            [("creator_id", 1), ("year", 1), ("month", 1)],
            name="uniq_creator_target_year_month")
        await _ensure_unique_index(
            db, "marketing_budgets",
            [("account_id", 1), ("period", 1)],
            name="uniq_budget_account_period")

        await db.marketing_kol_creators.create_index("id", unique=True)
        await db.marketing_kol_creators.create_index("login_email", sparse=True)
        await db.marketing_kol_creators.create_index("status")

        # Brute-force login attempt tracking (Creator Portal)
        await db.marketing_kol_login_attempts.create_index("identifier", unique=True)
        await db.marketing_kol_login_attempts.create_index("locked_until")

        await db.marketing_creator_sessions.create_index([("creator_id", 1), ("session_date", -1)])
        await db.marketing_creator_sessions.create_index("creator_id")

        await db.marketing_creator_item_requests.create_index([("creator_id", 1), ("status", 1)])
        await db.marketing_creator_item_requests.create_index("status")

        # LiveHost Management indexes
        await db.marketing_livehosts.create_index("id", unique=True)
        await db.marketing_livehosts.create_index("email", sparse=True)
        await db.marketing_livehosts.create_index("status")
        
        await db.marketing_livehost_shifts.create_index("id", unique=True)
        await db.marketing_livehost_shifts.create_index([("date", -1)])
        await db.marketing_livehost_shifts.create_index([("host_id", 1), ("date", -1)])
        await db.marketing_livehost_shifts.create_index("account_id")
        await db.marketing_livehost_shifts.create_index("attendance_status")
        await db.marketing_livehost_shifts.create_index("payment_status")
        
        # Marketing Webhook Events (Phase 1/2)
        await db.marketing_webhook_events.create_index("id", unique=True)
        await db.marketing_webhook_events.create_index("idempotency_key", unique=True)
        await db.marketing_webhook_events.create_index([("received_at", -1)])
        await db.marketing_webhook_events.create_index("platform")
        await db.marketing_webhook_events.create_index("processed")
        await db.marketing_webhook_events.create_index("event_type")
        
        await db.marketing_livehost_scripts.create_index("id", unique=True)
        await db.marketing_livehost_scripts.create_index("category")
        await db.marketing_livehost_scripts.create_index("is_active")
        
        await db.marketing_livehost_training.create_index("id", unique=True)
        await db.marketing_livehost_training.create_index("category")
        await db.marketing_livehost_training.create_index("is_active")
        
        await db.marketing_livehost_training_progress.create_index("id", unique=True)
        await db.marketing_livehost_training_progress.create_index([("host_id", 1), ("training_id", 1)])
        await db.marketing_livehost_training_progress.create_index("status")
        
        # Payroll entries (for Finance sync)
        await db.payroll_entries.create_index("id", unique=True)
        await db.payroll_entries.create_index([("month", 1), ("employee_id", 1)])
        await db.payroll_entries.create_index("type")
        await db.payroll_entries.create_index("status")

        # Phase 4: LiveHost portal notifications now live in the unified SSOT
        # `notifications` collection (P3 TD-010 Phase B, Session #11.12). Indexes
        # for SSOT are declared in the "Notifications SSOT" block above. The
        # legacy `marketing_livehost_notifications` collection is empty and
        # scheduled for drop after 1-week monitor.

        # Session 28 — Multi-currency FX rates
        await db.fx_rates.create_index("id", unique=True)
        await db.fx_rates.create_index([("currency", 1), ("effective_date", -1)])
        await db.fx_revaluation_runs.create_index("id", unique=True)
        await db.fx_revaluation_runs.create_index([("run_date", -1)])

        await db.marketing_tasks.create_index([("status", 1), ("created_at", -1)])
        await db.marketing_tasks.create_index([("assigned_to", 1), ("status", 1)])
        await db.marketing_tasks.create_index("due_date")

        await db.marketing_catalogs.create_index([("account_id", 1), ("is_active", 1)])
        await db.marketing_catalogs.create_index("id", unique=True)

        await db.marketing_catalog_items.create_index(
            [("catalog_id", 1), ("sku", 1)],
            name="catalog_sku_compound"
        )
        await db.marketing_catalog_items.create_index("catalog_id")
        await db.marketing_catalog_items.create_index("material_id", sparse=True)
        await db.marketing_catalog_items.create_index([("catalog_id", 1), ("stock_status", 1)])

        await db.marketing_stock_syncs.create_index([("catalog_id", 1), ("synced_at", -1)])

        # ── Session 7: Performance indexes for high-traffic collections ─────────
        # Production Jobs — critical for production-jobs list (filter+sort)
        await db.production_jobs.create_index([("created_at", -1)])
        await db.production_jobs.create_index("status")
        await db.production_jobs.create_index("vendor_id")
        await db.production_jobs.create_index("parent_job_id")
        await db.production_jobs.create_index([("parent_job_id", 1), ("created_at", -1)])  # compound filter+sort

        # Production Job Items — used in batch prefetch (job_id $in query)
        await db.production_job_items.create_index("job_id")
        await db.production_job_items.create_index("po_item_id")

        # Buyer Shipment Items — used in batch prefetch (job_id + job_item_id + po_item_id)
        await db.buyer_shipment_items.create_index("job_id")
        await db.buyer_shipment_items.create_index("job_item_id")
        await db.buyer_shipment_items.create_index("po_item_id")
        await db.buyer_shipment_items.create_index("po_id")
        await db.buyer_shipment_items.create_index("shipment_id")

        # Production POs — critical for production-pos list
        await db.production_pos.create_index([("created_at", -1)])
        await db.production_pos.create_index("status")
        await db.production_pos.create_index("vendor_id")

        # PO Items — used in batch prefetch
        await db.po_items.create_index("po_id")
        await db.po_items.create_index("vendor_id")
        await db.po_items.create_index("serial_number")

        # Attachments — queried by (entity_type, entity_id)
        await db.attachments.create_index([("entity_type", 1), ("entity_id", 1)])
        await db.attachments.create_index([("uploaded_at", -1)])

        # Accessories shipments (kept).
        # `accessories` + `accessory_requests` indexes REMOVED in Session #11.16
        # Phase A — collections dropped (SSOTs: rahaza_materials + dewi_accessory_requests).
        # W3 de-dup: accessory_inspections + accessory_defects index REMOVED — route
        # /api/accessory-inspections + /api/accessory-defects DEPRECATED-NOOP (operations.py:
        # GET→[] , POST→410, tidak pernah menyentuh koleksi). Koleksi di-drop. See FORENSIC_04 Cluster 1.
        await db.accessory_shipments.create_index([("created_at", -1)])
        await db.accessory_shipments.create_index("vendor_id")
        await db.accessory_shipments.create_index("po_id")
        await db.accessory_shipment_items.create_index("shipment_id")

        # Invoices / Payments (legacy generic) indexes REMOVED in Session #11.16
        # Phase B \u2014 collections DROPPED (SSOTs: rahaza_ar_invoices +
        # rahaza_ap_invoices + dewi_maklon_invoices for invoices; per-domain
        # payment ledgers for payments). See FORENSIC_04 Cluster 5.

        # Shipments (rahaza_shipments) — list endpoint
        await db.rahaza_shipments.create_index([("shipment_date", -1)])
        await db.rahaza_shipments.create_index("status")
        await db.rahaza_shipments.create_index("customer_id")
        await db.rahaza_shipments.create_index("order_id")

        # DA KPI — paginated list endpoints
        await db.da_kpi_perform.create_index("period_id")
        # NOTE: da_kpi_perform already has unique (period_id, employee_id) index - skip duplicate
        await db.da_kpi_results.create_index("period_id")

        # Portal Kolaborasi Phase 3: Communication Hub + Study Groups
        await db.comm_channels.create_index([("members", 1), ("archived", 1)])
        await db.comm_channels.create_index([("type", 1), ("archived", 1)])
        await db.comm_messages.create_index([("channel_id", 1), ("created_at", -1)])
        await db.comm_messages.create_index([("conversation_id", 1), ("created_at", -1)])
        # Session 28 — thread replies
        await db.comm_messages.create_index([("thread_root_id", 1), ("created_at", 1)])
        await db.comm_conversations.create_index("participants")
        await db.comm_read_receipts.create_index([("user_id", 1), ("ref_id", 1)], unique=True)
        
        # Study Groups indexes (Phase 3.8)
        await db.study_groups.create_index([("members", 1), ("created_at", -1)])
        await db.study_groups.create_index("course_id")
        await db.study_groups.create_index("created_by")

        logger.info("Session 7: Performance indexes created for high-traffic collections")

        # ── Session 8: Push Notification indexes ─────────────────────────────
        await db.push_subscriptions.create_index([("user_id", 1)])
        await db.push_subscriptions.create_index("endpoint", unique=True)
        await db.portal_quick_links.create_index([("user_id", 1), ("order_seq", 1)])

        # ── Impor Data Marketing (jalur resmi tanpa AI) ──────────────────────
        # F0.6 (2026-08-12): `routes/universal_import_indexes.py` dihapus bersama
        # mesin impor AI lama. Indeks yang MASIH berguna dipindah ke sini:
        # `id` unik + `_import_session_id` pada koleksi tujuan impor, plus indeks
        # sesi impor jalur resmi.
        await db.marketing_data_import_sessions.create_index("id", unique=True)
        await db.marketing_data_import_sessions.create_index("status")
        await db.marketing_data_import_sessions.create_index("source_type")
        await db.marketing_data_import_sessions.create_index("file_hash")
        await db.marketing_data_import_sessions.create_index([("created_at", -1)])
        # F3 (2026-08-14) — jejak PEMULIHAN impor `update_only` (Ekspor B/C).
        # `session_id` dibaca setiap kali tombol "Batalkan impor" ditekan; tanpa
        # indeks, satu berkas 20.000 baris membuat pembatalan memindai seluruh
        # koleksi. `doc_id` dipakai audit "pesanan ini pernah diubah impor mana".
        await db.marketing_data_import_undo.create_index("id", unique=True)
        await db.marketing_data_import_undo.create_index([("session_id", 1),
                                                          ("restored_at", 1)])
        await db.marketing_data_import_undo.create_index("doc_id")
        # ── Sesi #20 — Jembatan SKU (marketing_sku_bridge) ────────────────────
        # `platform_sku_id` unik: satu SKU platform tidak boleh punya dua master
        # (kalau boleh, gudang akan mengirim barang yang berbeda untuk pesanan
        # yang sama tergantung dokumen mana yang terbaca lebih dulu).
        # `items.platform_sku_id` pada pesanan: backfill tautan memindai koleksi
        # ini setiap kali satu SKU dipetakan.
        try:
            from core import sku_bridge as _bridge
            await _bridge.ensure_indexes(db)
        except Exception as _e:
            logger.warning("[startup] indeks jembatan SKU gagal: %s", _e)
        # Indeks pesanan dibuat SATU PER SATU: `items.platform_sku_id` sudah ada
        # sebagai index SPARSE dari sesi lama, dan MongoDB menolak permintaan
        # dengan nama sama tetapi opsi beda. Kalau ketiganya dalam satu `try`,
        # penolakan yang tidak berbahaya itu ikut membatalkan dua indeks lain.
        for _spec in ("items.platform_sku_id", "items.fg_material_id", "fulfillment_status"):
            try:
                await db.marketing_orders.create_index(_spec)
            except Exception as _e:
                logger.debug("[startup] indeks marketing_orders.%s dilewati: %s", _spec, _e)
        for _coll in ["marketing_orders", "marketing_complaints", "marketing_reviews",
                      "marketing_ads_data", "marketing_account_health",
                      "marketing_live_sessions", "marketing_content_calendar",
                      "marketing_product_launches", "marketing_sales_data",
                      "marketing_samples", "marketing_returns", "marketing_discounts",
                      "marketing_catalog_items", "marketing_livehost_shifts",
                      "marketing_live_session_products", "marketing_kol_creators"]:
            # TANPA `sparse`/nama khusus: beberapa koleksi sudah punya `id_1` &
            # `_import_session_id_1` non-sparse; meminta opsi berbeda dengan nama
            # otomatis yang sama menimbulkan IndexKeySpecsConflict (code 86).
            try:
                await db[_coll].create_index("id", unique=True)
                await db[_coll].create_index("_import_session_id")
            except Exception as _e:
                logger.debug("[index] %s: %s", _coll, _e)

        # FASE IA-4 — Portal Cutting: pastikan koleksi cutting selalu ada
        # (syarat agar ikut ter-backup oleh mongodump, lihat routes/cutting.py).
        from routes.cutting import ensure_cutting_indexes
        await ensure_cutting_indexes()

        # UOM — pastikan master satuan & aturan konversi selalu ada.
        # Tanpa ini, setelah wipe DB layar "Satuan & Konversi" kosong dan
        # kalkulator konversi melempar 404 (BUG-3 audit 2026-07-27).
        from routes.wms_units import ensure_unit_master
        _uom_seed = await ensure_unit_master(db)
        if _uom_seed.get("units_created") or _uom_seed.get("conversions_created"):
            logger.info(f"[uom] master satuan disiapkan: {_uom_seed}")
        # Note: APScheduler retry_queued_imports job moved to startup() after start_scheduler()
        # in Session #11.17 to fix "scheduler not running" warning.

        # Brute-force protection indexes (Portal Saya)
        from routes.auth_routes import _ensure_brute_force_index
        await _ensure_brute_force_index(db)

        # Brute-force protection indexes (Maklon Client Portal)
        from routes.dewi_client_portal import _ensure_client_bf_index
        await _ensure_client_bf_index(db)

    except Exception as e:
        logger.warning(f"Index creation warning: {e}")

    # ── JARING PENGAMAN NOMOR DOKUMEN (2026-08-07) ───────────────────────────
    # SENGAJA di blok try SENDIRI: bila digabung dengan blok di atas, satu index
    # yang gagal akan MELEWATI semua index sesudahnya tanpa jejak yang jelas.
    # Fungsi ini tidak pernah melempar; ia melaporkan koleksi yang masih memuat
    # nomor dokumen kembar beserta nomornya agar bisa ditindak.
    try:
        from utils.counters import ensure_unique_number_indexes
        await ensure_unique_number_indexes(db, logger)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[nomor-dokumen] gagal memasang index unik: {e}")

    # ── TEMPLATE PDF: MIGRASI SETELAN LAMA (SESI #19) ────────────────────────
    # Dua koleksi setelan PDF lama (`pdf_document_settings` untuk kop & tanda tangan,
    # `pdf_export_configs` untuk kolom) disatukan ke `pdf_templates`. Migrasi
    # IDEMPOTEN dan tidak pernah menimpa setelan yang sudah dibuat di layar baru,
    # sehingga aman dijalankan tiap startup. Blok try SENDIRI: setelan PDF tidak
    # boleh bisa menggagalkan startup — dokumen tetap tercetak dengan bawaan.
    try:
        from core.pdf_template import migrate_legacy as _migrate_pdf_tpl
        await _migrate_pdf_tpl(db, logger)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[pdf-template] migrasi setelan PDF lama dilewati: {e}")

@app.on_event("shutdown")
async def shutdown():
    try:
        stop_alerts_bg()
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    try:
        from utils.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    client.close()

# ─── HEALTH & METRICS ────────────────────────────────────────────────────────
@app.get("/api/health", tags=["ops"])
async def health_check():
    """Health check: DB ping + uptime. Used by load balancers & monitoring."""
    db = get_db()
    db_ok = False
    db_latency_ms = None
    try:
        t0 = time.time()
        await db.command("ping")
        db_latency_ms = round((time.time() - t0) * 1000, 1)
        db_ok = True
    except Exception as e:
        logger.error(f"Health check DB ping failed: {e}")
    status = "ok" if db_ok else "degraded"
    return JSONResponse(
        {
            "status": status,
            "db": "connected" if db_ok else "unavailable",
            "db_latency_ms": db_latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "CV. Dewi Aditya API",
        },
        status_code=200 if db_ok else 503,
    )

@app.get("/api/metrics", tags=["ops"])
async def metrics():
    """Snapshot metrik untuk dashboard monitoring — PUBLIK by-design.

    Didaftarkan di `scripts/lib/public_endpoints.py` (keputusan user 2026-07-26):
    scraper Prometheus/Grafana tidak bisa membawa JWT user. Aman karena isinya
    **hanya agregat** — jumlah dokumen per koleksi + timestamp; tidak ada PII,
    tidak ada dokumen mentah, tidak ada nilai uang. Sifat itu DIBUKTIKAN ulang
    tiap run oleh `assert_no_sensitive_payload()` di `scripts/verify_fase19_audit.py`,
    jadi kalau suatu hari ada yang menambahkan field sensitif di sini, gate merah.
    """
    db = get_db()
    try:
        counts = {}
        for col in ["production_pos", "production_jobs", "rahaza_employees", "rahaza_material_issues",
                    "rahaza_payroll_runs", "rahaza_attendance_events", "rahaza_purchase_orders"]:
            counts[col] = await db[col].estimated_document_count()
        return {"status": "ok", "collections": counts, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        # Endpoint PUBLIK: JANGAN membocorkan `str(e)` (nama host DB / query internal).
        logger.error(f"/api/metrics gagal: {e}")
        return JSONResponse({"status": "error"}, status_code=503)

# ─── REQUEST TIMING & LOGGING MIDDLEWARE ─────────────────────────────────────
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    dur_ms = round((time.time() - t0) * 1000, 1)
    # Log slow requests (> 2s) and all errors
    if dur_ms > 2000 or response.status_code >= 500:
        logger.warning(
            f"[{response.status_code}] {request.method} {request.url.path} "
            f"— {dur_ms}ms client={getattr(request.client, 'host', 'unknown')}"
        )
    return response

# ─── RATE LIMITING MIDDLEWARE ────────────────────────────────────────────────
# MongoDB-backed rate limiter — multi-worker/multi-pod safe
# Collection: rate_limit_buckets, TTL index on expire_at auto-cleans records
# Tiered: auth=10/min, AI=20/min, general=300/min

_RL_TIERS = [
    # 2026-08-07 — dinaikkan 10 → 30. Batas 10/menit per IP membuat satu kantor
    # (banyak staf di belakang satu IP publik) saling memblokir saat jam masuk,
    # dan membuat skrip seed/uji internal gagal 429. Perlindungan sesungguhnya
    # ada di `routes/auth_routes._check_brute_force` (5 gagal/15 menit per
    # IP+email, 20 gagal/60 menit per email) yang menghitung KEGAGALAN, bukan
    # semua percobaan.
    ("/api/auth/login",              30,  60),   # brute-force guard (lapis 1)
    ("/api/rahaza/ai",               20,  60),   # AI cost guard
    ("/api/rahaza/hr/reports",       60,  60),   # report generation
    ("/api/marketing/import/upload", 10,  60),   # file upload guard
    ("/api/marketing/import",        20,  60),   # AI analyze + preview guard
    (None,                          300,  60),   # default
]

async def _get_rl_count(db, key: str, window: int, now: float) -> int:
    """Return request count for key in the past `window` seconds."""
    cutoff = datetime.fromtimestamp(now - window, tz=timezone.utc)
    return await db.rate_limit_buckets.count_documents({"key": key, "ts": {"$gte": cutoff}})

async def _record_rl_hit(db, key: str, window: int, now: float):
    """Record a new request hit and set TTL for auto-cleanup."""
    ts = datetime.fromtimestamp(now, tz=timezone.utc)
    expire_at = datetime.fromtimestamp(now + window + 5, tz=timezone.utc)
    await db.rate_limit_buckets.insert_one({"key": key, "ts": ts, "expire_at": expire_at})

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # In K8s/proxy environments, real client IP is in X-Forwarded-For header
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = getattr(request.client, "host", "unknown")
    path = request.url.path
    now = time.time()

    # Panggilan internal (skrip seed/maintenance/health-check) datang dari
    # loopback TANPA X-Forwarded-For; trafik pengguna selalu lewat ingress dan
    # PASTI membawa X-Forwarded-For. Jadi loopback-tanpa-XFF aman dibebaskan
    # supaya seeding/uji tidak terkena 429.
    if not forwarded_for and client_ip in ("127.0.0.1", "::1", "localhost"):
        return await call_next(request)

    # Pick tier
    max_req, window = 300, 60
    for prefix, limit, win in _RL_TIERS:
        if prefix is None or path.startswith(prefix):
            max_req, window = limit, win
            break

    key = f"{client_ip}:{path[:30]}"
    try:
        db = get_db()
        count = await _get_rl_count(db, key, window, now)
        if count >= max_req:
            return JSONResponse(
                {"error": f"Rate limit exceeded. Max {max_req} req/{window}s per IP."},
                status_code=429,
            )
        await _record_rl_hit(db, key, window, now)
    except Exception as e:
        # Fail open — if MongoDB is unavailable, don't block requests
        logger.warning(f"Rate limiter error (fail-open): {e}")
    return await call_next(request)

# ─── SLOW REQUEST LOGGING ────────────────────────────────────────────────────
# Logs any request that takes > SLOW_THRESHOLD_MS milliseconds
SLOW_THRESHOLD_MS = 500  # warn if endpoint takes > 500ms

@app.middleware("http")
async def slow_request_logger(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    elapsed_ms = (time.time() - t0) * 1000
    if elapsed_ms > SLOW_THRESHOLD_MS:
        logger.warning(
            f"[SLOW] {request.method} {request.url.path} "
            f"— {elapsed_ms:.0f}ms (threshold: {SLOW_THRESHOLD_MS}ms)"
        )
    return response
# Domain routers (active after PT Rahaza cleanup — Stage A Phase 1)
from routes.auth_routes import router as auth_router
from routes.master_data import router as master_data_router
# ── Fase 2 Adopsi SOMMERVILLE: engine produksi/maklon (port dari sommerville-adopt) ──
from routes.production_pos import router as production_pos_router
from routes.vendor_shipment import router as vendor_shipment_router
from routes.cmt_override_routes import router as cmt_override_router
from routes.production_execution import router as production_execution_router
from routes.exceptions import router as production_exceptions_router
from routes.buyer_shipment import router as buyer_shipment_router
from routes.production_maklon_bridge import router as maklon_bridge_router
from routes.production_stage_tracking import router as production_stage_tracking_router
from routes.production_internal_adapter import router as production_internal_adapter_router
from routes.maklon_client_tracking import router as maklon_client_tracking_router
from routes.maklon_seed import router as maklon_seed_router
# Session #11.16 Phase D — routes.finance entirely DELETED (was stub-only after Phase B).
# All endpoints (`/api/invoices`, `/api/payments`, `/api/invoice-adjustments`,
# `/api/invoice-edit-requests`, `/api/accounts-payable`, `/api/accounts-receivable`,
# `/api/financial-recap`) now return 404 router-level. SSOTs: /api/rahaza/ar/*,
# /api/rahaza/ap/*, /api/dewi/maklon/billing/*.
from routes.admin import router as admin_router
from routes.dashboard_routes import router as dashboard_router
# Restores backend for live Finance module `fin-approval` (ApprovalModule.jsx).
# Fixes BUG-FE-CONTRACT-3: `/api/invoice-edit-requests[/{id}/approve|reject]` was 404.
from routes.invoice_edit_requests import router as invoice_edit_requests_router
# P2 Refactor (Session #12): operations.py RETIRED — split into focused sub-modules (deprecated accessories REMOVED)
# Sprint A.0: Re-enable operations.py for deprecated accessory NOOP endpoints
from routes.operations import router as operations_router
from routes.operations_reminders import router as operations_reminders_router
from routes.operations_serials import router as operations_serials_router
from routes.operations_reports import router as operations_reports_router
from routes.operations_import import router as operations_import_router
from routes.operations_excel import router as operations_excel_router
from routes.operations_pdf import router as operations_pdf_router
from routes.operations_pdf_configs import router as operations_pdf_configs_router
from routes.pdf_document_settings import router as pdf_document_settings_router
from routes.pdf_templates import router as pdf_templates_router
from routes.document_number_configs import router as document_number_configs_router
from routes.file_storage import router as file_router
from routes.websocket import router as ws_router
# Session 25 — Hard Unification: warehouse legacy router REMOVED from includes.
# Frontend already uses /api/wms/legacy/* (bridge router) since Session 21.
# Collections (warehouse_locations, warehouse_stock, etc.) still used via bridge.
# File routes/warehouse.py kept for reference — do NOT re-include without migration plan.
from routes.warehouse import router as warehouse_router  # Phase 8A: Re-enabled for asset capitalization
# FASE 4: finishing & qc (engine template lama, dead code D5) → routes/_archive/rahaza_multistage/
from routes.rahaza_master import router as rahaza_master_router
from routes.rahaza_production import router as rahaza_production_router
from routes.rahaza_orders import router as rahaza_orders_router
from routes.rahaza_bom import router as rahaza_bom_router
from routes.rahaza_variants import router as rahaza_variants_router  # Fase 2: Colors + Model Variants + SKU
from routes.rahaza_product_categories import router as rahaza_product_categories_router  # F2: Master Kategori Produk
from routes.rahaza_material_requirements import router as rahaza_material_requirements_router  # Fase 5: MRP-lite agregasi kebutuhan material
from routes.product_costing import router as product_costing_router  # 2026-08-23: HPP per potong & per model
from routes.production_sewing_cost import router as production_sewing_cost_router  # sesi #34: biaya jahit SPK + HPP batch FIFO
from routes.marketing_kol_incentive import router as marketing_kol_incentive_router  # sesi #34: insentif & tipe kreator
from routes.rnd_product_viewer import router as rnd_product_viewer_router  # sesi #34: viewer produk final RnD + status SSOT
from routes.marketing_creator_weekly_report import router as marketing_creator_weekly_report_router  # sesi #35: rapor kreator mingguan
# FASE 4 (E10 DELETE): rahaza_work_orders & rahaza_execution → routes/_archive/rahaza_multistage/
from routes.rahaza_inventory import router as rahaza_inventory_router
from routes.rahaza_attendance import router as rahaza_attendance_router
from routes.rahaza_attendance_sessions import router as rahaza_attendance_sessions_router
from routes.rahaza_attendance_permits import router as rahaza_attendance_permits_router
from routes.rahaza_payroll_allowances import router as rahaza_payroll_allowances_router
from routes.rahaza_payroll_settings import router as rahaza_payroll_settings_router
from routes.rahaza_payroll_profiles import router as rahaza_payroll_profiles_router
from routes.rahaza_payroll_runs import router as rahaza_payroll_runs_router
from routes.rahaza_payroll_payslips import router as rahaza_payroll_payslips_router
from routes.rahaza_finance import router as rahaza_finance_router
from routes.rahaza_hpp import router as rahaza_hpp_router
from routes.rahaza_reports import router as rahaza_reports_router
from routes.rahaza_notifications import router as rahaza_notifications_router
from routes.notifications_unified import router as notifications_unified_router  # P3 TD-010
from routes.rahaza_audit import router as rahaza_audit_router
from routes.rahaza_shipments import router as rahaza_shipments_router
from routes.rahaza_next_actions import router as rahaza_next_actions_router
from routes.rahaza_setup import router as rahaza_setup_router
# FASE 4 (E10 DELETE): rahaza_bundles* → routes/_archive/rahaza_multistage/
from routes.rahaza_alerts import (
    router as rahaza_alerts_router,
    start_background_task as start_alerts_bg,
    stop_background_task as stop_alerts_bg,
)
# FASE 4 (E10 DELETE): andon, tv, aps, aps_scheduler, oee, rework → routes/_archive/rahaza_multistage/
from routes.rahaza_sop import router as rahaza_sop_router
# Phase F1 — Accounting Core
from routes.rahaza_coa import router as rahaza_coa_router
from routes.coa_auto import router as coa_auto_router  # Phase 5 — Auto-COA subledger
from routes.rahaza_journals import router as rahaza_journals_router
from routes.rahaza_fin_reports import router as rahaza_fin_reports_router
from routes.rahaza_periods import router as rahaza_periods_router
# Phase F2 — Auto-posting profiles
from routes.rahaza_posting_profiles import router as rahaza_posting_profiles_router
# Admin / Demo Data utilities
from routes.rahaza_admin import router as rahaza_admin_router
# Phase 21 — Decision Support & Quality Metrics
# FASE 4 (E10 DELETE): rahaza_qc_v2 (qc_events+defect_codes), rahaza_backlog,
# rahaza_line_monitoring → routes/_archive/rahaza_multistage/
from routes.rahaza_downtime import router as rahaza_downtime_router
# Staff Self-Service Portal
from routes.rahaza_self import router as rahaza_self_router
# Phase 20C — AI Layer
from routes.rahaza_ai import router as rahaza_ai_router
from routes.portal_assistant_routes import router as portal_assistant_router
from routes.doc_numbering import router as doc_numbering_router
from routes.doc_numbering import policy_router as doc_number_policy_router  # FASE G
from routes.production_dashboard import router as production_dashboard_router
# Phase 22A — Supervisor & PPIC Power Tools
# FASE 4 (E10 DELETE): rahaza_material_reservation (per-WO), rahaza_lkp → _archive/rahaza_multistage/
from routes.rahaza_shift_handover import router as rahaza_shift_handover_router
# Sprint 2.1 — Purchase Orders
from routes.rahaza_po import router as rahaza_po_router
# Sprint 2.3 — Leave Management
from routes.rahaza_leave import router as rahaza_leave_router
# Sprint 3.1 — HR Reports
from routes.rahaza_sprint22 import router as rahaza_sprint22_router
# Sprint 42 — Smart Auto-Attendance (Selfie+AI, WebAuthn, ZKTeco, Approval Queue)
from routes.rahaza_auto_attendance import router as rahaza_auto_attendance_router

# NOTE: legacy routers removed for PT Rahaza rebuild:
#   buyer_portal, retail, distribution, shipments, rnd, cutting
# These flows are not relevant for in-house knit manufacturer.

# Register all active routers
app.include_router(auth_router)
app.include_router(master_data_router)
app.include_router(production_pos_router)
app.include_router(vendor_shipment_router)
app.include_router(cmt_override_router)
app.include_router(production_execution_router)
app.include_router(production_exceptions_router)
app.include_router(buyer_shipment_router)
app.include_router(maklon_bridge_router)
app.include_router(production_stage_tracking_router)
app.include_router(production_internal_adapter_router)
app.include_router(maklon_client_tracking_router)
app.include_router(maklon_seed_router)
# Session #11.16 Phase D — finance_router REMOVED (file deleted, was stub-only after Phase B).
app.include_router(admin_router)
app.include_router(invoice_edit_requests_router)
app.include_router(dashboard_router)
# P2 Refactor: operations.py split — include all sub-routers (deprecated accessories omitted)
# Sprint A.0: Re-enable operations_router for deprecated accessory NOOP endpoints
app.include_router(operations_router)
app.include_router(operations_reminders_router)
app.include_router(operations_serials_router)
app.include_router(operations_reports_router)
app.include_router(operations_import_router)
app.include_router(operations_excel_router)
app.include_router(operations_pdf_router)
app.include_router(operations_pdf_configs_router)
app.include_router(pdf_document_settings_router)
# SESI #19 — layar SATU PINTU "PDF & Kop Surat" (menggantikan dua layar di atas)
app.include_router(pdf_templates_router)
app.include_router(document_number_configs_router)
app.include_router(file_router)
app.include_router(ws_router)
# warehouse_router REMOVED — Session 25 Hard Unification (use /api/wms/legacy/* via wms_legacy_router)
# FASE 4: finishing_router & qc_router diarsip (dead code D5)
app.include_router(rahaza_master_router)
app.include_router(rahaza_production_router)
app.include_router(rahaza_orders_router)
app.include_router(rahaza_bom_router)
app.include_router(rahaza_variants_router)  # Fase 2: Colors + Model Variants + SKU
app.include_router(rahaza_product_categories_router)  # F2: Master Kategori Produk (K-2)
app.include_router(rahaza_material_requirements_router)  # Fase 5: MRP-lite agregasi kebutuhan material
app.include_router(product_costing_router)  # 2026-08-23: HPP per potong & per model (/api/costing)
app.include_router(production_sewing_cost_router)  # sesi #34: biaya jahit SPK per SKU/pcs + HPP batch FIFO
app.include_router(marketing_kol_incentive_router)  # sesi #34: insentif kreator per pcs + periode 3 bulan
app.include_router(rnd_product_viewer_router)  # sesi #34: katalog produk final RnD + status sync marketing/produksi
app.include_router(marketing_creator_weekly_report_router)  # sesi #35: rapor kreator mingguan (7 hari bergulir)
# FASE 4: rahaza_work_orders_router & rahaza_execution_router diarsip (E10 DELETE)
app.include_router(rahaza_inventory_router)
app.include_router(rahaza_attendance_router)
app.include_router(rahaza_attendance_sessions_router)  # FASE 15: istirahat & izin keluar/masuk
app.include_router(rahaza_attendance_permits_router)  # FASE 16: persetujuan izin + export rekap
app.include_router(rahaza_payroll_allowances_router)
app.include_router(rahaza_payroll_settings_router)  # FASE 15: aturan potongan terlambat & bonus kehadiran
app.include_router(rahaza_payroll_profiles_router)
app.include_router(rahaza_payroll_runs_router)
app.include_router(rahaza_payroll_payslips_router)
app.include_router(rahaza_finance_router)
app.include_router(rahaza_hpp_router)
app.include_router(rahaza_reports_router)
app.include_router(notifications_unified_router)  # Must come before rahaza_notifications to win path race
app.include_router(rahaza_notifications_router)
app.include_router(rahaza_audit_router)
app.include_router(rahaza_shipments_router)
app.include_router(rahaza_next_actions_router)
app.include_router(rahaza_setup_router)
# FASE 4: bundles, andon, tv, aps, aps_scheduler, oee, rework diarsip (E10 DELETE)
app.include_router(rahaza_alerts_router)
app.include_router(rahaza_sop_router)
# Phase F1 — Accounting Core
app.include_router(rahaza_coa_router)
app.include_router(coa_auto_router)  # Phase 5 — Auto-COA subledger + posting integration
app.include_router(rahaza_journals_router)
app.include_router(rahaza_fin_reports_router)
app.include_router(rahaza_periods_router)
# Phase F2 — Auto-posting profiles
app.include_router(rahaza_posting_profiles_router)
# Admin / Demo Data utilities
app.include_router(rahaza_admin_router)
# Phase 21 — Decision Support & Quality Metrics
# FASE 4: qc_v2, backlog, line_monitoring diarsip (E10 DELETE)
app.include_router(rahaza_downtime_router)
# Staff Self-Service Portal
app.include_router(rahaza_self_router)
# Phase 20C — AI Layer
app.include_router(rahaza_ai_router)
app.include_router(portal_assistant_router)
app.include_router(doc_numbering_router)
app.include_router(doc_number_policy_router)  # FASE G: form dokumen baca mode nomor
app.include_router(production_dashboard_router)
# Phase 22A — Supervisor & PPIC Power Tools
# FASE 4: material_reservation (per-WO) & lkp diarsip (E10 DELETE)
app.include_router(rahaza_shift_handover_router)
# Sprint 2.1 — Purchase Orders
app.include_router(rahaza_po_router)
# Sprint 2.3 — Leave Management
app.include_router(rahaza_leave_router)
# Sprint 3.1 — HR Reports
from routes.rahaza_hr_reports import router as rahaza_hr_reports_router
app.include_router(rahaza_hr_reports_router)
# Sprint 22 — Supervisor Power Tools
app.include_router(rahaza_sprint22_router)
# Sprint 42 — Smart Auto-Attendance
app.include_router(rahaza_auto_attendance_router)
# Production Calendar (Phase 22B)
from routes.rahaza_production_calendar import router as rahaza_production_calendar_router
app.include_router(rahaza_production_calendar_router)
# Demo Seed
# FASE 5 (AD-4): rahaza_demo_seed diarsip — seeder final: POST /api/seed/maklon-full
from routes.rahaza_styles import router as rahaza_styles_router
app.include_router(rahaza_styles_router)

# Sprint 27 — AQL Sampling Calculator
from routes.rahaza_aql import router as rahaza_aql_router
app.include_router(rahaza_aql_router)

# Integration Settings (API Key management)
from routes.rahaza_integrations import router as rahaza_integrations_router
app.include_router(rahaza_integrations_router)

# Production Wizard (Automation P0)
# FASE 4: rahaza_wizard diarsip (E10 DELETE — pembuat WO+bundles engine lama)

# ─── CV. Dewi Aditya — Fase 2 & 3 Routes ─────────────────────────────────────
# Fase 2: Cutting & CMT Management
# FASE 4: dewi_cutting diarsip (E10 DELETE — cutting requests/batches engine lama)

# BACKLOG-C: 4 router CMT LEGACY di-ARSIP (routes/_archive/) — FE sudah redirect
# (moduleRegistry O1.1/O1.2: prod-cmt→vendor-admin, cmt-progress→wms-cmt-dispatches,
# do-management→wms-cmt-dispatches). SSOT dispatch = wh_cmt_dispatches.
# Yang TETAP AKTIF: dewi_cmt_lifecycle (vendor portal), dewi_cmt_packing
# (ProductionDashboardOverview), dewi_cmt_component_requests.
# from routes.dewi_cmt import router as dewi_cmt_router                       # ARCHIVED
# from routes.dewi_cmt_progress import router as dewi_cmt_progress_router     # ARCHIVED
# from routes.dewi_cmt_seed import router as dewi_cmt_seed_router             # ARCHIVED
# from routes.dewi_cmt_delivery_orders import router as dewi_cmt_do_router    # ARCHIVED

# ── Production-Maklon Overhaul — New Routes ────────────────────────────────────

# Fase 3: Portal Maklon
from routes.dewi_maklon import router as dewi_maklon_router
app.include_router(dewi_maklon_router)

# Maklon PO (New — Production-Maklon Overhaul)
from routes.dewi_maklon_pos import router as dewi_maklon_pos_router
app.include_router(dewi_maklon_pos_router)

# Phase M1: Buyer Catalog (Master Artikel Buyer Maklon)
from routes.dewi_maklon_buyer_catalog import router as dewi_maklon_buyer_catalog_router
app.include_router(dewi_maklon_buyer_catalog_router)

# Phase M2.2: BOM Template per Buyer Catalog (versioned)
from routes.dewi_maklon_bom_templates import router as dewi_maklon_bom_templates_router
app.include_router(dewi_maklon_bom_templates_router)

# Maklon PO 360° View Aggregator (Phase 25 — P2 Workflow Consolidation #1)
from routes.dewi_maklon_po_360 import router as dewi_maklon_po_360_router
app.include_router(dewi_maklon_po_360_router)

# CMT Permak / Rework (Maklon Revamp M1 — rework mengurangi FG, canonical progress)
from routes.dewi_cmt_permak import router as dewi_cmt_permak_router
app.include_router(dewi_cmt_permak_router)

# CMT KEJAR + Dashboard Owner (Maklon CMT Operasional — Fase 2, read-only aggregation)
from routes.cmt_kejar import router as cmt_kejar_router
app.include_router(cmt_kejar_router)

# CMT INTAKE — Potongan Masuk (batch) + Cek Seri dobel (Maklon CMT Operasional — Fase 3, read-only)
from routes.cmt_intake import router as cmt_intake_router
app.include_router(cmt_intake_router)

# CMT BELANJA — Rekap Aksesoris (po_accessories + BOM×qty) + Kapasitas CMT (Maklon CMT Operasional — Fase 4, read-only)
from routes.cmt_belanja import router as cmt_belanja_router
app.include_router(cmt_belanja_router)

# CMT RECON — Rekonsiliasi dispatch maklon(pcs) vs WMS(meter) + deteksi split-brain (Maklon CMT Operasional — Fase 5, read-only)
from routes.cmt_recon import router as cmt_recon_router
app.include_router(cmt_recon_router)

# SESI #33 — RIWAYAT HARGA BARANG (semua jenis material) + DAFTAR BELANJA MINGGUAN
# (usul beli dari ambang minimum → Permintaan Pengadaan). Prefix sendiri supaya
# tidak menabrak kontrak urutan route `/api/rahaza/materials/{id}` (gate INV-F24).
from routes.rahaza_material_costs import router as rahaza_material_costs_router
app.include_router(rahaza_material_costs_router)
from routes.rahaza_shopping_list import router as rahaza_shopping_list_router
app.include_router(rahaza_shopping_list_router)

# HR Approval Inbox Aggregator (Phase 26 — P2 Workflow Consolidation #2)
from routes.hr_approval_inbox import router as hr_approval_inbox_router
app.include_router(hr_approval_inbox_router)
from routes.approval_badge import router as approval_badge_router
app.include_router(approval_badge_router)

# AP Invoice from GR + 3-way Match Dashboard (Phase 27 — P2P Flow Completion)
from routes.rahaza_ap_from_gr import router as rahaza_ap_from_gr_router
app.include_router(rahaza_ap_from_gr_router)

# Production Control Tower (Phase 28 — P2 Workflow Consolidation #3)
from routes.production_control_tower import router as production_control_tower_router
app.include_router(production_control_tower_router)

# Tagihan CMT (pintu "Invoice" Portal Produksi/Maklon) — FASE IA-1 2026-07-26.
# Endpoint BACA saja; posting GL tetap lewat /api/dewi/maklon/finance/cmt-payments/{id}/post-ap.
from routes.production_cmt_billing import router as production_cmt_billing_router
app.include_router(production_cmt_billing_router)

# CMT Lifecycle Dashboard (Phase 29 — Cross-Module Vendor View)
from routes.dewi_cmt_lifecycle import router as dewi_cmt_lifecycle_router
app.include_router(dewi_cmt_lifecycle_router)

# AR 360° — Aging Matrix + Customer Statement (Phase 30 — OTC Completion)
from routes.rahaza_ar_360 import router as rahaza_ar_360_router
app.include_router(rahaza_ar_360_router)

# Maklon Finance Integration (Phase 4 — Fix AR/AP GL gap)
from routes.dewi_maklon_finance import router as dewi_maklon_finance_router
app.include_router(dewi_maklon_finance_router)

# Fase 3B: Sample Management + QC Tracking
from routes.dewi_maklon_samples import router as dewi_maklon_samples_router
app.include_router(dewi_maklon_samples_router)

from routes.dewi_maklon_qc import router as dewi_maklon_qc_router
app.include_router(dewi_maklon_qc_router)

# Fase 3C: Billing & Invoice + HPP
from routes.dewi_maklon_billing import router as dewi_maklon_billing_router
app.include_router(dewi_maklon_billing_router)

# GAP #6: Production Reports Export (CSV)
from routes.dewi_production_reports import router as dewi_production_reports_router
app.include_router(dewi_production_reports_router)

# System Config (used by Maklon & future integrations)
from routes.dewi_system_config import router as dewi_system_config_router
app.include_router(dewi_system_config_router)

# Fase 4: Maklon Client Portal (external login)
from routes.dewi_client_portal import router as dewi_client_portal_router
from routes.vendor_portal import router as vendor_portal_router, create_vendor_portal_indexes
from routes.dewi_client_admin import router as dewi_client_admin_router
from routes.dewi_client_uploads import router as dewi_client_uploads_router
from routes.dewi_notifications import router as dewi_notifications_router
from routes.dewi_scheduler import router as dewi_scheduler_router
from routes.dewi_toko import router as dewi_toko_router
from routes.dewi_push_notifications import router as dewi_push_router
app.include_router(dewi_client_portal_router)
app.include_router(vendor_portal_router)
app.include_router(dewi_client_admin_router)
app.include_router(dewi_client_uploads_router)
app.include_router(dewi_notifications_router)
app.include_router(dewi_scheduler_router)
app.include_router(dewi_toko_router)
app.include_router(dewi_push_router)

# Phase 5B — Portal Toko Online completion (Legacy - keeping for backward compatibility)
# Session #11.16 Phase D — routes.dewi_kol entirely DELETED (was stub-only after Phase C).
# All endpoints (`/api/dewi/kol/*`) now return 404 router-level. SSOT: /api/marketing/kol/*.
from routes.dewi_online_orders import router as dewi_online_orders_router

# NEW: Marketing Portal (Multi-Platform Management + KOL + Task Management + Smart Import)
from routes.marketing_accounts import router as marketing_accounts_router
from routes.marketing_sales import router as marketing_sales_router
from routes.marketing_dashboard import router as marketing_dashboard_router
from routes.marketing_tasks import router as marketing_tasks_router
from routes.marketing_task_templates import router as marketing_task_templates_router
from routes.marketing_kol import router as marketing_kol_router
from routes.marketing_livehost_hosts import router as marketing_livehost_hosts_router
from routes.marketing_livehost_shifts import router as marketing_livehost_shifts_router
from routes.marketing_livehost_scripts import router as marketing_livehost_scripts_router
from routes.marketing_livehost_training import router as marketing_livehost_training_router
from routes.marketing_livehost_analytics import router as marketing_livehost_analytics_router
from routes.marketing_livehost_portal import router as marketing_livehost_portal_router
from routes.marketing_catalog import router as marketing_catalog_router
from routes.marketing_targets import router as marketing_targets_router
from routes.marketing_budget import router as marketing_budget_router
# F5 — siklus (target+anggaran+omzet dalam 1 permintaan) & kunci periode.
# Sengaja tinggal di berkas marketing_budget.py: anggaran berhenti jadi pulau.
from routes.marketing_budget import cycle_router as marketing_cycle_router
from routes.marketing_budget import periods_router as marketing_periods_router
# F6.5 (sesi #9) — layar "siapa mengubah apa": jejak perubahan marketing yang
# bisa dicari & dihalaman (jejaknya sudah lahir di F5, pembacanya belum ada).
from routes.marketing_change_log import router as marketing_change_log_router
from routes.marketing_reports import router as marketing_reports_router
from routes.marketing_reports_weekly import router as marketing_reports_weekly_router
from routes.marketing_orders_routes import router as marketing_orders_router
from routes.marketing_complaints_routes import router as marketing_complaints_router
# Phase B.1 Toko Cutover — marketing-namespace replacements for legacy /api/dewi/toko/*
from routes.marketing_toko_dashboard_routes import router as marketing_toko_dashboard_router
from routes.marketing_toko_sync_routes import router as marketing_toko_sync_router
from routes.marketing_account_health_routes import router as marketing_health_router
from routes.marketing_sales_performance_routes import router as marketing_performance_router
from routes.marketing_ads_routes import router as marketing_ads_router
from routes.marketing_live_sessions_routes import router as marketing_live_router
# F17/F0.6 — Impor Data Marketing: SATU pintu, TANPA AI (SSOT jenis data + lingkup toko).
# Mesin lama `universal_import` (AI menebak jenis data) dan `marketing_import` (khusus
# rekap sales) DIHAPUS TOTAL pada F0.6 2026-08-12 — keduanya menulis ke koleksi tujuan
# yang salah, tanpa `account_id`, tanpa dedupe, dan berbagi ruang URL `/api/marketing/import/*`
# sehingga kebenaran aplikasi bergantung pada urutan `include_router`.
from routes.marketing_data_import import router as marketing_data_import_router
# Phase 6 — Fulfillment (Online Order Bridge)
from routes.fulfillment import router as fulfillment_router
app.include_router(marketing_data_import_router)
app.include_router(marketing_accounts_router)
app.include_router(marketing_sales_router)
app.include_router(marketing_dashboard_router)
app.include_router(marketing_tasks_router)
app.include_router(marketing_task_templates_router)
app.include_router(marketing_kol_router)
app.include_router(marketing_livehost_hosts_router)
app.include_router(marketing_livehost_shifts_router)
app.include_router(marketing_livehost_scripts_router)
app.include_router(marketing_livehost_training_router)
app.include_router(marketing_livehost_analytics_router)
app.include_router(marketing_livehost_portal_router)
app.include_router(marketing_catalog_router)
app.include_router(marketing_targets_router)
app.include_router(marketing_budget_router)
app.include_router(marketing_cycle_router)
app.include_router(marketing_periods_router)
app.include_router(marketing_change_log_router)
app.include_router(marketing_reports_router)
app.include_router(marketing_reports_weekly_router)
app.include_router(marketing_orders_router)
app.include_router(marketing_complaints_router)
# Phase B.1 Toko Cutover routers
app.include_router(marketing_toko_dashboard_router)
app.include_router(marketing_toko_sync_router)
app.include_router(marketing_health_router)
app.include_router(marketing_performance_router)
app.include_router(marketing_ads_router)
app.include_router(marketing_live_router)
app.include_router(fulfillment_router)  # Phase 6
# ── Sesi #20 — SINKRONISASI MARKETING ⇄ GUDANG ────────────────────────────────
# Keluhan pemilik: "list barang dari marketing untuk dikirimkan tim gudang tidak
# ada yang sama, id-nya tidak sinkron". Terukur (tests/poc_sync_forensic.py):
# 0 dari 601 baris pesanan menunjuk master gudang, 83 SKU platform tak dikenal.
# `sku_bridge`  = master pemetaan platform_sku_id ⇄ item katalog/varian/FG.
# `sync_audit`  = forensik yang dulu hanya ada di skrip agent, kini bisa dibuka pemilik.
from routes.sku_bridge import router as sku_bridge_router
from routes.sync_audit import router as sync_audit_router
app.include_router(sku_bridge_router)
app.include_router(sync_audit_router)
# ── Sesi #28 — ONBOARDING PRODUK PLATFORM → MASTER (identitas varian 3 dimensi)
# Jembatan #20 terbukti benar tapi 0 dari 601 baris pesanan pernah tertaut: 83 SKU
# dari 8 produk nyata tidak punya master, dan mesin lama menabrakkan 65 dari 83 SKU
# itu ke identitas yang sama (POLKA BLACK…PAKAI KARET = hitam/XL = BLACK…TANPA KARET).
# `variant_onboarding` = pintu per PRODUK (8 keputusan, bukan 83) + master Opsi.
from routes.variant_onboarding import router as variant_onboarding_router
app.include_router(variant_onboarding_router)
# Phase 2 Enhancement — Unified Inventory Viewer (WIP/FG/Material unified + stock adjustment)
from routes.unified_inventory import router as unified_inventory_router
app.include_router(unified_inventory_router)
# Phase 7 — Reporting & Dashboard (Daily/Monthly/Per-PO/Actual-vs-Target)
from routes.dewi_phase7_reports import router as dewi_phase7_reports_router
app.include_router(dewi_phase7_reports_router)

# Phase 3 Week 8-10: Content Calendar, Discounts, Product Launches
from routes.marketing_content_calendar_routes import router as marketing_content_calendar_router
from routes.marketing_discounts_routes import router as marketing_discounts_router
from routes.marketing_product_launches_routes import router as marketing_product_launches_router
# F9 (sesi #12) — Pencairan/Settlement marketplace, INPUT MANUAL.
# Blokir data BD-2 melarang MENEBAK kolom laporan pencairan; input manual
# menghapus blokirnya karena tidak ada kolom yang perlu ditebak siapa pun.
from routes.marketing_settlements import router as marketing_settlements_router
app.include_router(marketing_content_calendar_router)
app.include_router(marketing_discounts_router)
app.include_router(marketing_product_launches_router)
app.include_router(marketing_settlements_router)

# F7.2/F6.4 (2026-08-13) — KPI platform hasil impor Seller Center + Assign Toko (SPV).
# Keduanya memakai ruang URL sendiri (`/api/marketing/platform-kpi`,
# `/api/marketing/account-assign`) supaya TIDAK bertabrakan dengan rute berparameter
# `/api/marketing/accounts/{account_id}` — tabrakan seperti itu membuat endpoint baru
# menjawab 404 "Akun toko tidak ditemukan" dan sangat sulit ditelusuri.
from routes.marketing_platform_kpi_routes import router as marketing_platform_kpi_router
from routes.marketing_account_assign import router as marketing_account_assign_router
app.include_router(marketing_platform_kpi_router)
app.include_router(marketing_account_assign_router)

# Phase 3 Week 11-12: Alert Engine + Integration Settings
from routes.marketing_alerts import router as marketing_alerts_router
from routes.marketing_integration_settings_routes import router as marketing_integration_settings_router
app.include_router(marketing_alerts_router)
app.include_router(marketing_integration_settings_router)

# Phase 3 Week 13: Fitur Internal (Rating/Review, Returns, Sample Delivery)
from routes.marketing_reviews_routes import router as marketing_reviews_router
from routes.marketing_returns_routes import router as marketing_returns_router
from routes.marketing_samples_routes import router as marketing_samples_router
from routes.marketing_ai_insights_routes import router as marketing_ai_insights_router
from routes.marketing_advanced_ai_routes import router as marketing_advanced_ai_router
app.include_router(marketing_reviews_router)
app.include_router(marketing_returns_router)
app.include_router(marketing_samples_router)
app.include_router(marketing_ai_insights_router)
app.include_router(marketing_advanced_ai_router)

# WMS Phase 1 — Units, Structure, Receiving
from routes.wms_units import router as wms_units_router
from routes.wms_structure import router as wms_structure_router
from routes.wms_receiving import router as wms_receiving_router
# Fase 5 cleanup: routes.wms_opname (GEN2, /api/wms/opname*) DIHAPUS — digantikan wms_opname3 (scan-driven).
from routes.wms_labels import router as wms_labels_router
from routes.wms_audit import router as wms_audit_router
# WMS Phase 2 — P0 Garment-specific features
from routes.wms_fabric_rolls import router as wms_fabric_rolls_router
from routes.cutting import router as cutting_router
from routes.notification_categories import router as notif_category_router  # notifikasi berkategori per portal  # FASE IA-4 — Portal Cutting (roll kain ➜ potongan)
from routes.rbac_audit import router as rbac_audit_router  # audit approval & notifikasi (2026-08-07)
from routes.wms_delivery_notes import router as wms_delivery_notes_router
from routes.wms_cmt_dispatches import router as wms_cmt_dispatches_router
# Fase 5 cleanup: routes.wms_opname2 (GEN3, /api/wms/opname2) DIHAPUS — digantikan wms_opname3 (scan-driven + finance).
from routes.wms_putaway import router as wms_putaway_router  # Fase 3A: put-away kanonik sadar-lokasi
from routes.wms_opname3 import router as wms_opname3_router  # Fase 4: opname scan-driven sadar-lokasi
from routes.wms_quarantine import router as wms_quarantine_router  # FASE 6 (INV-8): karantina QC barang reject
from routes.wms_stock_schema import router as wms_stock_schema_router  # FASE 6.6-A: kesehatan & rekonsiliasi skema baris stok
# WMS Label Printing — Session #11.21
from routes.wms_material_labels import router as wms_material_labels_router
from routes.wms_fg_labels import router as wms_fg_labels_router
from routes.wms_barcode import router as wms_barcode_router  # FASE H-3: menu Buat Barcode
# WMS AI Insights — Powered by GPT-4o
from routes.wms_ai_insights import router as wms_ai_router
from routes.analytics_ai import router as analytics_ai_router
app.include_router(wms_units_router)
app.include_router(wms_structure_router)
app.include_router(wms_receiving_router)
app.include_router(warehouse_router)  # Phase 8A: Asset Capitalization requires /api/warehouse/receiving

app.include_router(wms_labels_router)
app.include_router(wms_audit_router)
app.include_router(wms_fabric_rolls_router)
app.include_router(cutting_router)
app.include_router(notif_category_router)
app.include_router(rbac_audit_router)
app.include_router(wms_delivery_notes_router)
app.include_router(wms_cmt_dispatches_router)
app.include_router(wms_putaway_router)  # Fase 3A: /api/wms/putaway (kanonik, sadar-lokasi)
app.include_router(wms_opname3_router)  # Fase 4: /api/wms/opname3 (scan-driven, sadar-lokasi)
app.include_router(wms_quarantine_router)  # FASE 6: /api/wms/quarantine (karantina QC + disposisi)
app.include_router(wms_stock_schema_router)  # FASE 6.6-A: /api/wms/stock-schema (health + reconcile + rollback)
app.include_router(wms_material_labels_router)  # Session #11.21
app.include_router(wms_fg_labels_router)  # Session #11.21
app.include_router(wms_barcode_router)  # FASE H-3 (2026-08-16): Buat Barcode
app.include_router(wms_ai_router)
app.include_router(analytics_ai_router)
from routes.dewi_returns import router as dewi_returns_router
from routes.dewi_demo_seed import router as dewi_demo_seed_router
from routes.dewi_hris_performance import router as dewi_hris_performance_router
# Session #11.16 Phase D — dewi_kol_router REMOVED (file deleted, was stub-only after Phase C).
app.include_router(dewi_online_orders_router)
app.include_router(dewi_returns_router)
app.include_router(dewi_demo_seed_router)
app.include_router(dewi_hris_performance_router)

# Phase 6 — HRIS Modules
from routes.dewi_lms import router as dewi_lms_router
from routes.dewi_onboarding import router as dewi_onboarding_router
from routes.dewi_recruitment import router as dewi_recruitment_router
from routes.dewi_kasbon import router as dewi_kasbon_router
from routes.rahaza_channel_gl_mapping import router as rahaza_channel_gl_router
from routes.dewi_org import router as dewi_org_router
app.include_router(dewi_lms_router)
app.include_router(dewi_onboarding_router)
app.include_router(dewi_recruitment_router)
app.include_router(dewi_kasbon_router)
app.include_router(rahaza_channel_gl_router)
app.include_router(dewi_org_router)

# Phase 8 — DA KPI System (Refactored Session #11.19 Final)
from routes.dewi_kpi_periods import router as dewi_kpi_periods_router
from routes.dewi_kpi_questions import router as dewi_kpi_questions_router
from routes.dewi_kpi_perform import router as dewi_kpi_perform_router
from routes.dewi_kpi_results import router as dewi_kpi_results_router
from routes.dewi_kpi_leaderboard import router as dewi_kpi_leaderboard_router
from routes.dewi_kpi_gamification import router as dewi_kpi_gamification_router
from routes.dewi_kpi_reports import router as dewi_kpi_reports_router
app.include_router(dewi_kpi_periods_router)
app.include_router(dewi_kpi_questions_router)
app.include_router(dewi_kpi_perform_router)
app.include_router(dewi_kpi_results_router)
app.include_router(dewi_kpi_leaderboard_router)
app.include_router(dewi_kpi_gamification_router)
app.include_router(dewi_kpi_reports_router)


# Phase 8.5 — DA Assets & Employee Management
from routes.dewi_assets import router as dewi_assets_router
app.include_router(dewi_assets_router)

# Phase 8.6 — AI Action Items
from routes.dewi_ai_actions import router as dewi_ai_actions_router
app.include_router(dewi_ai_actions_router)

# Phase 7.9 — WMS Pick-List Generator
from routes.wms_picklist import router as wms_picklist_router
app.include_router(wms_picklist_router)

# Phase 3 — Dual API Conflict Resolution
# Bridge router that exposes warehouse.py legacy endpoints under /api/wms/legacy/*
# so all WMS-related URLs live under a single /api/wms namespace.
from routes.wms_legacy import router as wms_legacy_router
app.include_router(wms_legacy_router)

# Phase 4 (Session 22) — P1-WH-3 FG Size/Color Matrix
# Aggregation endpoints for Finished Goods inventory pivoted by model × color × size
# with allocation/reservation support.
from routes.rahaza_fg_matrix import router as rahaza_fg_matrix_router
app.include_router(rahaza_fg_matrix_router)

# Phase 4 (Session 22) — P1 GRN Quality Check & Supplier Scorecard
# Inspection workflow, partial receive, reject categories, AQL sampling, and supplier
# performance scorecards based on aggregated inspection data.
from routes.rahaza_grn_qc import router as rahaza_grn_qc_router
app.include_router(rahaza_grn_qc_router)

# Phase 8.9 — Leave Balance Tracking (P0.3)
from routes.rahaza_leave_balances import router as rahaza_leave_balances_router
app.include_router(rahaza_leave_balances_router)

# Phase 9.1 — Overtime Request Workflow (P1.1)
from routes.rahaza_overtime import router as rahaza_overtime_router
app.include_router(rahaza_overtime_router)

# Phase 9.2-9.6 — P2 HRIS Features (Salary Grades, Resignation, Delegation, LMS Quiz, 360, HR Seed)
from routes.rahaza_salary_grades import router as rahaza_salary_grades_router
from routes.rahaza_resignation import router as rahaza_resignation_router
from routes.rahaza_approval_delegation import router as rahaza_approval_delegation_router
from routes.dewi_lms_quiz import router as dewi_lms_quiz_router
from routes.rahaza_360_feedback import router as rahaza_360_feedback_router
from routes.rahaza_hr_seed import router as rahaza_hr_seed_router
# Sprint 42 — P0: Salary Adjustment (Raise) Workflow with Dual Approval (Manager + HR)
from routes.rahaza_salary_adjustments import router as rahaza_salary_adjustments_router
app.include_router(rahaza_salary_grades_router)
app.include_router(rahaza_resignation_router)
app.include_router(rahaza_approval_delegation_router)
app.include_router(dewi_lms_quiz_router)
app.include_router(rahaza_360_feedback_router)
app.include_router(rahaza_hr_seed_router)
app.include_router(rahaza_salary_adjustments_router)

# Phase 7 — RnD & Style Master
from routes.dewi_rnd import router as dewi_rnd_router
app.include_router(dewi_rnd_router)

# Session 27 — GAP P0 SOP RnD/Produksi: Accessory Requests, Kreator Requests, CMT Shortage
from routes.dewi_accessory_requests import router as dewi_accessory_requests_router
from routes.dewi_kreator_requests import router as dewi_kreator_requests_router
from routes.dewi_cmt_component_requests import router as dewi_cmt_component_requests_router
app.include_router(dewi_accessory_requests_router)
app.include_router(dewi_kreator_requests_router)
app.include_router(dewi_cmt_component_requests_router)

# Blueprint §3.3 — Aksesoris Management Full
from routes.dewi_accessories_full import router as dewi_accessories_full_router
app.include_router(dewi_accessories_full_router)

from routes.dewi_portal_saya import router as dewi_portal_saya_router
app.include_router(dewi_portal_saya_router)

from routes.dewi_bank_reconciliation import router as dewi_bank_recon_router
app.include_router(dewi_bank_recon_router)

from routes.dewi_cashflow_ai import router as cashflow_ai_router
app.include_router(cashflow_ai_router)

# Blueprint §3.7 — Return & Refund Portal Gudang
from routes.dewi_wh_returns import router as dewi_wh_returns_router
app.include_router(dewi_wh_returns_router)

# Blueprint §2.7 — CMT Packing & Stok Opname
from routes.dewi_cmt_packing import router as dewi_cmt_packing_router
app.include_router(dewi_cmt_packing_router)

# Session 11 — Budget Module + Fixed Asset & Depreciation
from routes.rahaza_budget import router as rahaza_budget_router
from routes.rahaza_fixed_assets import router as rahaza_fixed_assets_router
from routes.marketing_ai_content_tools import router as marketing_ai_content_router
# FASE 14 — `marketing_task_templates_router` SUDAH di-include di baris ~1459.
# Import + include kedua di sini membuat 7 route (`/api/marketing/task-templates*`,
# `/api/marketing/tasks-stats`, `/api/marketing/auto-create-tasks/trigger`)
# TERDAFTAR DUA KALI di tabel route FastAPI. Handler-nya sama sehingga perilaku
# tidak berubah, tetapi tabel route menggelembung dan pemeriksaan duplikat jadi
# berisik. Scan dekorator TIDAK BISA melihat cacat ini (tiap route hanya ditulis
# sekali di file-nya) — ketemu lewat tabel route runtime. Jangan tambahkan lagi.
from routes.marketing_kol_leaderboard import router as marketing_kol_leaderboard_router
app.include_router(rahaza_budget_router)
from routes.rahaza_bank_recon import router as rahaza_bank_recon_router
app.include_router(rahaza_bank_recon_router)

app.include_router(rahaza_fixed_assets_router)
from routes.rahaza_accruals import router as rahaza_accruals_router
app.include_router(rahaza_accruals_router)

from routes.rahaza_employee_loans import router as rahaza_employee_loans_router
app.include_router(rahaza_employee_loans_router)


# Session 12 — AI Content Tools + Task Templates + KOL Leaderboard
# (task_templates_router sengaja TIDAK di-include lagi di sini — sudah di ~1459)
app.include_router(marketing_ai_content_router)
app.include_router(marketing_kol_leaderboard_router)

# Session 13 — SLA Dashboard, Management Tools, Smart Warehouse
from routes.dewi_maklon_sla import router as dewi_maklon_sla_router
from routes.dewi_management_tools import router as dewi_management_tools_router
from routes.dewi_warehouse_smart import router as dewi_warehouse_smart_router
app.include_router(dewi_maklon_sla_router)
app.include_router(dewi_management_tools_router)
app.include_router(dewi_warehouse_smart_router)

# Session 14 — AI Business Intelligence
from routes.dewi_ai_business import router as dewi_ai_business_router
app.include_router(dewi_ai_business_router)

# Session 15 — HR AI & Portal Saya Extensions
from routes.dewi_hr_ai import router as dewi_hr_ai_router
from routes.dewi_portal_saya_ext import router as dewi_portal_saya_ext_router
app.include_router(dewi_hr_ai_router)
app.include_router(dewi_portal_saya_ext_router)
# RC-29: mount ganda dewi_portal_saya_hr_router (tanpa prefix /api) DIHAPUS —
# mount kanonik sudah via routes/dewi_portal_saya.py (nested /api/portal/*).
# 12 path bare (/dashboard, /leave, /payslips, dst.) tak terjangkau ingress = noise openapi.

# Session 16 — Unified Search
from routes.unified_search import router as unified_search_router
app.include_router(unified_search_router)

# Session 17 Batch 1 — HR/SDM Features (P2-11, P2-12, P2-16, P2-20)
from routes.dewi_shift_scheduler import router as shift_scheduler_router
from routes.dewi_job_board import router as job_board_router
from routes.dewi_career_coach import router as career_coach_router
from routes.dewi_skill_gap import router as skill_gap_router
app.include_router(shift_scheduler_router)
app.include_router(job_board_router)
app.include_router(career_coach_router)
app.include_router(skill_gap_router)

# Session 18 — P2-3 OKR Tracker, P2-7 Predictive Maintenance, P2-19 Maklon AI Quote
from routes.dewi_okr import router as okr_router
from routes.dewi_predictive_maintenance import router as predictive_maintenance_router
from routes.dewi_maklon_quote import router as maklon_quote_router
app.include_router(okr_router)
app.include_router(predictive_maintenance_router)
app.include_router(maklon_quote_router)

# Session 19 — E-3 AI Cost Monitoring
from routes.ai_usage_monitor import router as ai_usage_router
app.include_router(ai_usage_router)

# New Portals — Communication Hub + Asset Management + Procurement + Workspace + LMS Student
from routes.dewi_communication import router as comm_router
from routes.dewi_asset_management import router as asset_router
from routes.dewi_procurement import router as procurement_router
from routes.procurement_suppliers import router as procurement_suppliers_router
from routes.procurement_dashboard import router as procurement_dashboard_router
from routes.workspace import router as workspace_router
from routes.lms_student import router as lms_student_router
from routes.notifications import router as notifications_router
from routes.search import router as search_router
from routes.activity_feed import router as activity_feed_router
from routes.study_groups import router as study_groups_router
app.include_router(comm_router)
app.include_router(asset_router)
app.include_router(procurement_router)
app.include_router(procurement_suppliers_router)
app.include_router(procurement_dashboard_router)

from routes.universal_scan import router as universal_scan_router
app.include_router(universal_scan_router)
app.include_router(workspace_router)
app.include_router(lms_student_router)
app.include_router(notifications_router)
app.include_router(search_router)
app.include_router(activity_feed_router)
app.include_router(study_groups_router)

# Berkas unggahan dilayani dari Emergent Object Storage (fallback: berkas lama di /app/uploads)
from fastapi import Response as _UploadResponse, HTTPException as _UploadHTTPException
import object_storage as _objstore


@app.get('/api/uploads/{path:path}')
async def serve_upload(path: str):
    if '..' in path:
        raise _UploadHTTPException(status_code=400, detail='path tidak valid')
    found = _objstore.get_object(path)
    if not found:
        raise _UploadHTTPException(status_code=404, detail='Berkas tidak ditemukan')
    return _UploadResponse(content=found[0], media_type=found[1])

# Phase 1/2 — Marketing Webhooks (Tokopedia, Shopee, TikTok)
from routes.marketing_webhooks import router as marketing_webhooks_router
app.include_router(marketing_webhooks_router)

# Phase 2 — Capacity Planning Lite (rule-based factory capacity check)
from routes.wms_capacity_planning import router as capacity_planning_router
app.include_router(capacity_planning_router)

# Phase 3 — Live Session Analytics
from routes.marketing_live_analytics import router as live_analytics_router
app.include_router(live_analytics_router)

# Phase 3 — Payroll Automation Layer
from routes.payroll_automation import router as payroll_automation_router
app.include_router(payroll_automation_router)

# Phase 3 — Executive Report Hub
from routes.dewi_executive_report import router as executive_report_router
app.include_router(executive_report_router)

# ─── Task 1.2: HR Shift Management ───────────────────────────────────────────
from routes.hr_shifts import router as hr_shifts_router
app.include_router(hr_shifts_router)

# ─── Task 2.4: Multi-Level Approval Workflow ─────────────────────────────────
from routes.approval_multilevel import router as approval_multilevel_router
app.include_router(approval_multilevel_router)

# ─── Task 2.5: Production Material Returns ───────────────────────────────────
from routes.production_material_returns import router as prod_material_returns_router
app.include_router(prod_material_returns_router)

# ─── Employee Expense Management (EEM) — Reimbursement & Perjalanan Dinas ────
from routes.employee_expense_claims import router as emp_expense_claims_router
from routes.employee_travel_requests import router as emp_travel_requests_router
from routes.employee_per_diem import router as emp_per_diem_router
from routes.employee_expense_summary import router as emp_expense_summary_router
from routes.employee_travel_settlements import router as emp_travel_settlements_router
from routes.employee_expense_gl_mapping import router as emp_expense_gl_mapping_router
app.include_router(emp_expense_claims_router)
app.include_router(emp_travel_requests_router)
app.include_router(emp_per_diem_router)
app.include_router(emp_expense_summary_router)
app.include_router(emp_travel_settlements_router)
app.include_router(emp_expense_gl_mapping_router)

# ─── EEM Category Master (Phase 5A) ─────────────────────────────────────────
from routes.employee_expense_category_master import router as emp_expense_category_master_router
app.include_router(emp_expense_category_master_router)

# ─── Phase 6B: Kas Kecil / Petty Cash ────────────────────────────────────────
from routes.rahaza_petty_cash import router as petty_cash_router
app.include_router(petty_cash_router)

# ─── Phase 6C: Bank Transfer Antar Rekening ──────────────────────────────────
from routes.rahaza_bank_transfers import router as bank_transfers_router
app.include_router(bank_transfers_router)

# ─── Admin Backup & Restore Management ───────────────────────────────────────
from routes.admin_backup import router as admin_backup_router
from routes.announcements import router as announcements_router
app.include_router(announcements_router)
app.include_router(admin_backup_router)

# ─── Universal Export / Import (registry-driven data transfer) ───────────────
from routes.data_transfer import router as data_transfer_router
app.include_router(data_transfer_router)

# ─── Production Seed ─────────────────────────────────────────────────────────
# FASE 5 (AD-4): production_seed_full diarsip (menulis koleksi engine lama yang
# sudah di-drop). Seeder final: POST /api/seed/maklon-full (maklon + internal).


# ─── Financial Recap Endpoint ────────────────────────────────────────────────
# Re-implements the deleted /api/financial-recap for FinancialRecapModule.jsx
from datetime import date as _date, timedelta
from dateutil.relativedelta import relativedelta

@app.get("/api/financial-recap", tags=["financial-recap"])
async def financial_recap(
    request: Request,
    date_from: str = "",
    date_to: str = "",
):
    """
    Aggregated financial snapshot used by FinancialRecapModule.jsx.
    Sources: rahaza_ar_invoices, rahaza_ap_invoices, rahaza_ar_payments, rahaza_ap_payments
    """
    from routes.shared import require_portal
    await require_portal(request, "finance")  # RBAC: data keuangan wajib portal finance (BUG-RBAC-1)
    db = get_db()
    today = _date.today()

    # Default: last 30 days
    if not date_from:
        date_from = (today - timedelta(days=30)).isoformat()
    if not date_to:
        date_to = today.isoformat()

    # Build filters
    date_filter = {"$gte": date_from, "$lte": date_to}

    # AR invoices (sales)
    ar_pipeline = [
        {"$match": {"issue_date": date_filter, "status": {"$ne": "cancelled"}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_amount"}, "count": {"$sum": 1}}}
    ]
    ar_agg = await db.rahaza_ar_invoices.aggregate(ar_pipeline).to_list(1)
    total_sales = ar_agg[0]["total"] if ar_agg else 0
    total_ar_invoices = ar_agg[0]["count"] if ar_agg else 0

    # AP invoices (vendor cost)
    ap_pipeline = [
        {"$match": {"issue_date": date_filter, "status": {"$ne": "cancelled"}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_amount"}, "count": {"$sum": 1}}}
    ]
    ap_agg = await db.rahaza_ap_invoices.aggregate(ap_pipeline).to_list(1)
    total_vendor = ap_agg[0]["total"] if ap_agg else 0
    total_ap_invoices = ap_agg[0]["count"] if ap_agg else 0

    # Cash In (AR payments)
    ci_pipeline = [
        {"$match": {"payment_date": date_filter}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    ci_agg = await db.rahaza_ar_payments.aggregate(ci_pipeline).to_list(1)
    total_cash_in = ci_agg[0]["total"] if ci_agg else 0

    # Cash Out (AP payments)
    co_pipeline = [
        {"$match": {"payment_date": date_filter}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    co_agg = await db.rahaza_ap_payments.aggregate(co_pipeline).to_list(1)
    total_cash_out = co_agg[0]["total"] if co_agg else 0

    # AR outstanding (all unpaid AR invoices)
    ar_out_pipeline = [
        {"$match": {"status": {"$in": ["unpaid", "partial", "overdue"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$outstanding_amount"}}}
    ]
    ar_out_agg = await db.rahaza_ar_invoices.aggregate(ar_out_pipeline).to_list(1)
    ar_outstanding = ar_out_agg[0]["total"] if ar_out_agg else 0

    # AP outstanding
    ap_out_pipeline = [
        {"$match": {"status": {"$in": ["unpaid", "partial", "overdue"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$outstanding_amount"}}}
    ]
    ap_out_agg = await db.rahaza_ap_invoices.aggregate(ap_out_pipeline).to_list(1)
    ap_outstanding = ap_out_agg[0]["total"] if ap_out_agg else 0

    # Gross margin
    gross_margin = total_sales - total_vendor
    gross_margin_pct = round((gross_margin / total_sales * 100), 1) if total_sales > 0 else 0

    # Monthly trend (last 6 months)
    monthly_trend = []
    for i in range(5, -1, -1):
        m_date = today - relativedelta(months=i)
        m_str = m_date.strftime("%Y-%m")
        m_label = m_date.strftime("%b %Y")
        m_start = f"{m_str}-01"
        m_end = (m_date + relativedelta(months=1) - timedelta(days=1)).strftime("%Y-%m-%d")
        m_filter = {"$gte": m_start, "$lte": m_end}

        m_ar = await db.rahaza_ar_invoices.aggregate([
            {"$match": {"issue_date": m_filter, "status": {"$ne": "cancelled"}}},
            {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
        ]).to_list(1)
        m_ap = await db.rahaza_ap_invoices.aggregate([
            {"$match": {"issue_date": m_filter, "status": {"$ne": "cancelled"}}},
            {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
        ]).to_list(1)
        m_ci = await db.rahaza_ar_payments.aggregate([
            {"$match": {"payment_date": m_filter}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]).to_list(1)
        m_co = await db.rahaza_ap_payments.aggregate([
            {"$match": {"payment_date": m_filter}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]).to_list(1)

        ms = m_ar[0]["total"] if m_ar else 0
        mc = m_ap[0]["total"] if m_ap else 0
        monthly_trend.append({
            "month": m_label,
            "sales": ms,
            "cost": mc,
            "margin": ms - mc,
            "cash_in": m_ci[0]["total"] if m_ci else 0,
            "cash_out": m_co[0]["total"] if m_co else 0,
        })

    return {
        "total_sales_value": total_sales,
        "total_vendor_cost": total_vendor,
        "total_buyer_invoices": total_ar_invoices,
        "total_vendor_invoices": total_ap_invoices,
        "total_cash_in": total_cash_in,
        "total_cash_out": total_cash_out,
        "total_adjustments": 0,
        "accounts_receivable_outstanding": ar_outstanding,
        "accounts_payable_outstanding": ap_outstanding,
        "gross_margin": gross_margin,
        "gross_margin_pct": gross_margin_pct,
        "monthly_trend": monthly_trend,
        "garment_summary": [],
        "date_from": date_from,
        "date_to": date_to,
    }

# ─── API v1 PATH REWRITER MIDDLEWARE ────────────────────────────────────────
# E-6/E-7: Provides /api/v1/* aliases for the legacy per-module paths.
from middleware.api_v1 import APIv1PathRewriteMiddleware
app.add_middleware(APIv1PathRewriteMiddleware)

# ─── JARING PENGAMAN LINGKUP TOKO MARKETING (F6.6, sesi #9) ─────────────────
# Tidak ada endpoint `/api/marketing/*` yang boleh melayani permintaan yang
# MENYEBUT toko di luar lingkup pemakai (path / query / body). Ini jaring
# pengaman untuk kelas masalah IDOR — BUKAN pengganti `scope_filter` pada
# endpoint daftar. Lihat middleware/marketing_scope_guard.py.
from middleware.marketing_scope_guard import MarketingScopeGuardMiddleware
app.add_middleware(MarketingScopeGuardMiddleware)

# ─── CORS MIDDLEWARE ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
