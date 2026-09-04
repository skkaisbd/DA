"""
marketing_budget.py — Budget Marketing per Toko × Bulan × Kategori (KEPUTUSAN #5).

Tiap akun toko punya rencana budget per bulan yang dipecah per KATEGORI alokasi:
  ads · kol · livehost · sample · diskon
lalu di-compare dengan realisasi (spend) + ROI vs sales.

Sumber spend (grounded ke kode):
  - Ads / Sample / Diskon : input manual → marketing_spend_entries (KEPUTUSAN #5, ads=manual).
  - LiveHost : REAL → Σ total_pay shift 'calculated' (marketing_livehost_shifts) utk host
               yang assigned ke akun (marketing_livehosts.assigned_account_ids) + entri manual.
  - KOL/Kreator : KONFIGURABEL (KEPUTUSAN #5 = kombinasi) → fee (fixed rate) dan/atau
               komisi (% dari sales). Cost = Σ per kreator assigned ke akun, dihitung dari
               marketing_creator_sessions.revenue pada periode + entri manual.

Sales (ROI) : Σ marketing_sales_data.metrics.revenue (revenue_type='total') utk akun+periode.

Endpoints (prefix /api/marketing/budget):
  GET  /                         ?account_id=&period=YYYY-MM   → rencana budget
  PUT  /                         upsert rencana budget
  POST /spend                    catat spend manual
  GET  /spend                    ?account_id=&period=&category=
  DELETE /spend/{sid}
  GET  /kol-cost                 list kreator + cost_config
  GET  /kol-cost/{creator_id}
  PUT  /kol-cost/{creator_id}    set cost_config {fee_type, fixed_fee, commission_pct}
  GET  /summary                  ?account_id=&period=  → budget vs spend per kategori + ROI

F5 (2026-08-13) — di berkas ini juga tinggal **dua router tambahan**, dengan sengaja
BUKAN berkas baru, supaya anggaran berhenti menjadi pulau yang terpisah dari target
dan omzet:

  /api/marketing/cycle/summary     satu permintaan = target + omzet + anggaran + marjin + ROI
  /api/marketing/cycle/overview    semua toko × satu bulan (baris tabel + total)
  /api/marketing/periods/lock      tutup / buka periode (kunci angka yang sudah dirapatkan)
  /api/marketing/periods/locks     daftar periode terkunci

Semua rumusnya ada di `core/marketing_cycle.py` (SSOT) — endpoint di sini hanya
menjaga kewenangan & bentuk permintaan.
"""
import uuid
import logging
import calendar
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth, serialize_doc
from core import marketing_sales_shape as _shape
from core import marketing_cycle as _cycle
from core import marketing_account_scope as _scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/marketing/budget', tags=['Marketing-Budget'])
cycle_router = APIRouter(prefix='/api/marketing/cycle', tags=['Marketing-Cycle'])
periods_router = APIRouter(prefix='/api/marketing/periods', tags=['Marketing-Periods'])

# F5.2 — `komisi` DITAMBAH: komisi kreator adalah biaya penjualan nyata yang
# sebelumnya tidak punya tempat di rencana anggaran. Daftar kanoniknya ada di
# core/marketing_cycle supaya layar, gate, dan migrasi memakai daftar yang SAMA.
CATEGORIES = list(_cycle.CATEGORIES)
FEE_TYPES = ['none', 'fixed', 'commission', 'both']


def _uid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


def _num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def _empty_cat(default=0.0):
    return {c: float(default) for c in CATEGORIES}


# ── Pydantic ─────────────────────────────────────────────────────────────────
class BudgetUpsert(BaseModel):
    account_id: str
    period: str = Field(..., description="YYYY-MM")
    budget_by_category: dict = Field(default_factory=dict)
    notes: Optional[str] = ''
    # F6.5 (sesi #9) — ALASAN perubahan rencana anggaran (opsional, dicatat di
    # `marketing_change_log` dan ditampilkan di layar Jejak Perubahan).
    reason: Optional[str] = ''


class SpendEntry(BaseModel):
    account_id: str
    period: str = Field(..., description="YYYY-MM")
    category: str
    amount: float = Field(..., ge=0)
    description: Optional[str] = ''
    ref_type: Optional[str] = ''   # e.g. 'ads_campaign', 'sample', 'promo'
    ref_id: Optional[str] = ''
    spend_date: Optional[str] = ''  # YYYY-MM-DD


class KolCostConfig(BaseModel):
    fee_type: str = Field('none', description="none | fixed | commission | both")
    fixed_fee: float = Field(0, ge=0)
    commission_pct: float = Field(0, ge=0, le=100)


def _valid_period(p: str):
    """Periode anggaran boleh 7-HARI (default) atau BULANAN.

    SESI #34 — keputusan pemilik: "periode budget menjadi 7 hari yang sebelumnya
    satu bulan… yang saat ini satu bulan jangan dihapus namun bisa dikonfigurasi".
    Jadi format yang diterima ADA DUA, dan keduanya adalah string yang sama-sama
    bisa dipakai sebagai kunci dokumen (tanpa mengubah 20+ pembaca yang sudah ada):

      * ``YYYY-MM``      — periode BULANAN (perilaku lama, tetap sah selamanya)
      * ``YYYY-MM-DD``   — periode 7 HARI yang MULAI pada tanggal itu (default baru)

    Kenapa tanggal-mulai dan bukan nomor minggu ISO: minggu ISO membuat pemilik
    harus menerjemahkan "minggu ke-34" menjadi tanggal, dan awal minggu marketing
    tidak selalu hari Senin (kampanye 7 hari bisa mulai kapan saja).
    """
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            datetime.strptime(p, fmt)
            return
        except Exception:
            continue
    raise HTTPException(400, "period harus YYYY-MM (bulanan) atau YYYY-MM-DD "
                             "(periode 7 hari, tanggal mulai)")


PERIOD_SETTINGS = 'marketing_budget_settings'
PERIOD_SETTINGS_ID = 'GLOBAL'
DEFAULT_PERIOD_MODE = 'weekly'      # keputusan pemilik sesi #34
DEFAULT_PERIOD_DAYS = 7


async def get_period_settings(db) -> dict:
    doc = await db[PERIOD_SETTINGS].find_one({'id': PERIOD_SETTINGS_ID}, {'_id': 0}) or {}
    return {
        'period_mode': doc.get('period_mode') or DEFAULT_PERIOD_MODE,   # weekly | monthly
        'period_days': int(doc.get('period_days') or DEFAULT_PERIOD_DAYS),
        'updated_at': doc.get('updated_at'),
        'updated_by': doc.get('updated_by') or '',
    }


def period_bounds(period: str, days: int = DEFAULT_PERIOD_DAYS) -> tuple:
    """(tanggal_mulai, tanggal_akhir) inklusif, sebagai string 'YYYY-MM-DD'.

    Dipakai SEMUA pembaca angka realisasi supaya periode 7 hari membaca rentang
    tanggal yang benar (regex '^YYYY-MM' hanya bekerja untuk periode bulanan).
    """
    if len(period) == 7:                       # YYYY-MM
        start = datetime.strptime(period + "-01", "%Y-%m-%d")
        last = calendar.monthrange(start.year, start.month)[1]
        return period + "-01", f"{period}-{last:02d}"
    start = datetime.strptime(period, "%Y-%m-%d")
    end = start + timedelta(days=max(1, int(days)) - 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _date_filter(period: str, days: int = DEFAULT_PERIOD_DAYS) -> dict:
    a, b = period_bounds(period, days)
    return {'$gte': a, '$lte': b + 'T23:59:59'}


# ── Cost helpers ───────────────────────────────────────────────────────────────
def _creator_cost(config: dict, revenue: float) -> float:
    """Hitung biaya kreator dari config (kombinasi fee + komisi)."""
    if not config:
        return 0.0
    ft = (config.get('fee_type') or 'none').lower()
    fixed = _num(config.get('fixed_fee'), 0)
    pct = _num(config.get('commission_pct'), 0)
    cost = 0.0
    if ft in ('fixed', 'both'):
        cost += fixed
    if ft in ('commission', 'both'):
        cost += revenue * pct / 100.0
    return round(cost, 2)


async def _creator_revenue(db, creator_id: str, account_id: str, period: str) -> float:
    rows = await db.marketing_creator_sessions.find(
        {'creator_id': creator_id, 'account_id': account_id,
         'date': _date_filter(period)},
        {'_id': 0, 'revenue': 1}
    ).to_list(2000)
    return round(sum(_num(r.get('revenue'), 0) for r in rows), 2)


async def _kol_auto_spend(db, account_id: str, period: str):
    """Biaya KOL otomatis: Σ kreator assigned ke akun × cost_config-nya."""
    creators = await db.marketing_kol_creators.find(
        {'assigned_account_ids': account_id}, {'_id': 0}
    ).to_list(500)
    total = 0.0
    detail = []
    for c in creators:
        cfg = c.get('cost_config') or {}
        if not cfg or (cfg.get('fee_type') or 'none') == 'none':
            continue
        rev = await _creator_revenue(db, c['id'], account_id, period)
        cost = _creator_cost(cfg, rev)
        if cost <= 0:
            continue
        total += cost
        detail.append({
            'creator_id': c['id'], 'creator_name': c.get('name', ''),
            'fee_type': cfg.get('fee_type'), 'fixed_fee': _num(cfg.get('fixed_fee'), 0),
            'commission_pct': _num(cfg.get('commission_pct'), 0),
            'revenue': rev, 'cost': cost,
        })
    return round(total, 2), detail


async def _livehost_auto_spend(db, account_id: str, period: str):
    """Biaya LiveHost = **GAJI BULANAN** host yang bertugas di toko ini (sesi #34).

    Sebelumnya angka ini = Σ `total_pay` shift (upah per sesi). Pemilik menghapus
    upah per-sesi: host digaji bulanan lewat payroll HR. Jadi biaya marketing
    untuk satu toko = gaji host yang PUNYA shift di periode ini, dibagi rata
    antar toko yang dilayaninya pada periode itu (satu orang tidak boleh
    dihitung penuh di dua toko), dan diprorata bila periode < 1 bulan.

    Gaji dibaca dari MASTER HR (`rahaza_employees`) lewat `livehost.employee_id`;
    host yang belum tertaut TIDAK diberi angka karangan — ia muncul di detail
    dengan `salary_source: 'none'`.
    """
    settings = await get_period_settings(db)
    start, end = period_bounds(period, settings['period_days'])
    days = (datetime.strptime(end, '%Y-%m-%d') - datetime.strptime(start, '%Y-%m-%d')).days + 1
    shifts = await db.marketing_livehost_shifts.find(
        {'date': {'$gte': start, '$lte': end + 'T23:59:59'}},
        {'_id': 0, 'host_id': 1, 'account_id': 1, 'date': 1}
    ).to_list(20000)
    if not shifts:
        return 0.0, []
    host_accounts: dict = {}
    for s in shifts:
        host_accounts.setdefault(s.get('host_id'), set()).add(s.get('account_id'))
    host_ids = [h for h in host_accounts if h]
    hosts = await db.marketing_livehosts.find(
        {'id': {'$in': host_ids}},
        {'_id': 0, 'id': 1, 'name': 1, 'employee_id': 1, 'monthly_salary': 1}).to_list(500)
    from core import livehost_salary as _lhs
    sal = await _lhs.monthly_salary_map(db, hosts)
    total = 0.0
    detail = []
    for h in hosts:
        accs = {a for a in host_accounts.get(h['id'], set()) if a}
        if account_id not in accs:
            continue
        info = sal.get(h['id']) or {'salary': 0.0, 'source': 'none', 'reason': ''}
        salary = _num(info.get('salary'), 0)
        share = salary / max(1, len(accs))
        prorated = round(share * min(1.0, days / 30.0), 2)
        total += prorated
        detail.append({
            'host_id': h['id'], 'host_name': h.get('name', ''),
            'monthly_salary': salary,
            'salary_source': info.get('source'),
            'salary_gap': info.get('reason') or '',
            'accounts_served': len(accs), 'days_in_period': days,
            'charged_to_this_account': prorated,
        })
    return round(total, 2), detail


async def _manual_spend(db, account_id: str, period: str):
    rows = await db.marketing_spend_entries.find(
        {'account_id': account_id, 'period': period}, {'_id': 0}
    ).to_list(5000)
    by_cat = _empty_cat()
    for r in rows:
        cat = r.get('category')
        if cat in by_cat:
            by_cat[cat] += _num(r.get('amount'), 0)
    return {k: round(v, 2) for k, v in by_cat.items()}


async def _sales_revenue(db, account_id: str, period: str) -> float:
    """Total sales (revenue) akun pada periode utk ROI.

    Robust ke dua bentuk dokumen marketing_sales_data:
      - entry endpoint resmi: {revenue_type:'total'|'live', metrics:{revenue}}
      - seed/demo lama: {gross_sales, net_sales} tanpa revenue_type
    Entri 'live' di-skip agar tidak dobel-hitung dengan 'total'.
    """
    rows = await db.marketing_sales_data.find(
        {'account_id': account_id, 'date': _date_filter(period)},
        {'_id': 0}      # F0.3 — proyeksi penuh: bentuk dokumen bisa kanonik/rata/seed lama
    ).to_list(10000)
    tot = 0.0
    for r in rows:
        if (r.get('revenue_type') or '') == 'live':
            continue
        m = _shape.read_metrics(r)
        val = (m.get('revenue') if m.get('revenue') else
               r.get('net_sales') if r.get('net_sales') is not None else
               r.get('gross_sales'))
        tot += _num(val, 0)
    return round(tot, 2)


# ── BUDGET PLAN ────────────────────────────────────────────────────────────────
@router.get('/period-settings')
async def read_period_settings(request: Request):
    """Setelan panjang periode anggaran (default 7 hari — keputusan pemilik #34)."""
    await require_auth(request)
    db = get_db()
    st = await get_period_settings(db)
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    st['current_period'] = (today if st['period_mode'] == 'weekly' else today[:7])
    a, b = period_bounds(st['current_period'], st['period_days'])
    st['current_range'] = {'start': a, 'end': b}
    st['options'] = [
        {'mode': 'weekly', 'label': f"{st['period_days']} hari (default)"},
        {'mode': 'monthly', 'label': '1 bulan (perilaku lama)'},
    ]
    return {'ok': True, 'settings': st}


class PeriodSettingsIn(BaseModel):
    period_mode: str = Field('weekly', description='weekly | monthly')
    period_days: int = Field(DEFAULT_PERIOD_DAYS, ge=1, le=60)


@router.put('/period-settings')
async def save_period_settings(body: PeriodSettingsIn, request: Request):
    await require_auth(request)
    user = getattr(request.state, 'user', {}) or {}
    if body.period_mode not in ('weekly', 'monthly'):
        raise HTTPException(400, "period_mode harus 'weekly' atau 'monthly'")
    db = get_db()
    await db[PERIOD_SETTINGS].update_one(
        {'id': PERIOD_SETTINGS_ID},
        {'$set': {'period_mode': body.period_mode, 'period_days': int(body.period_days),
                  'updated_at': datetime.now(timezone.utc),
                  'updated_by': user.get('name') or user.get('email') or 'system'},
         '$setOnInsert': {'id': PERIOD_SETTINGS_ID}}, upsert=True)
    return {'ok': True, 'settings': await get_period_settings(db)}



@router.get('')
async def get_budget(request: Request, account_id: str = Query(...), period: str = Query(...)):
    await require_auth(request)
    _valid_period(period)
    db = get_db()
    doc = await db.marketing_budgets.find_one({'account_id': account_id, 'period': period}, {'_id': 0})
    if not doc:
        return {'account_id': account_id, 'period': period,
                'budget_by_category': _empty_cat(), 'total_budget': 0.0, 'exists': False}
    bbc = {**_empty_cat(), **(doc.get('budget_by_category') or {})}
    doc['budget_by_category'] = {k: round(_num(v), 2) for k, v in bbc.items() if k in CATEGORIES}
    doc['total_budget'] = round(sum(doc['budget_by_category'].values()), 2)
    doc['exists'] = True
    return serialize_doc(doc)


@router.put('')
async def upsert_budget(data: BudgetUpsert, request: Request):
    user = await require_auth(request)
    _valid_period(data.period)
    db = get_db()
    acc = await db.marketing_platform_accounts.find_one({'id': data.account_id}, {'_id': 0})
    if not acc:
        raise HTTPException(404, 'Akun platform tidak ditemukan.')
    # F6 — rencana anggaran adalah keputusan SPV, bukan staf toko
    await _scope.assert_can_write_target(user, 'rencana anggaran')
    await _scope.assert_account_visible(db, user, data.account_id)
    # F5.3 — periode yang sudah ditutup tidak boleh berubah lagi (HTTP 423).
    await _cycle.assert_period_open(db, data.account_id, data.period,
                                    action='mengubah rencana anggaran')
    bbc = {c: round(_num((data.budget_by_category or {}).get(c), 0), 2) for c in CATEGORIES}
    now = _now()
    before = await db.marketing_budgets.find_one(
        {'account_id': data.account_id, 'period': data.period},
        {'_id': 0, 'budget_by_category': 1})
    await db.marketing_budgets.update_one(
        {'account_id': data.account_id, 'period': data.period},
        {'$set': {'budget_by_category': bbc, 'notes': data.notes or '',
                  'account_name': acc.get('account_name', ''), 'updated_at': now,
                  'updated_by': user.get('id', '')},
         '$setOnInsert': {'id': _uid(), 'account_id': data.account_id,
                          'period': data.period, 'created_at': now}},
        upsert=True,
    )
    await _cycle.log_change(db, account_id=data.account_id, entity='marketing_budgets',
                            entity_id=f"{data.account_id}:{data.period}",
                            action='budget_upsert',
                            before=(before or {}).get('budget_by_category'),
                            after=bbc, reason=(data.reason or '').strip(),
                            user=user, period=data.period)
    doc = await db.marketing_budgets.find_one({'account_id': data.account_id, 'period': data.period}, {'_id': 0})
    doc['total_budget'] = round(sum(bbc.values()), 2)
    return serialize_doc(doc)


# ── SPEND ENTRIES (manual) ──────────────────────────────────────────────────────
@router.post('/spend')
async def add_spend(data: SpendEntry, request: Request):
    user = await require_auth(request)
    _valid_period(data.period)
    if data.category not in CATEGORIES:
        raise HTTPException(400, f"category harus salah satu: {', '.join(CATEGORIES)}")
    db = get_db()
    # F5.3 — belanja tidak boleh ditambahkan ke bulan yang sudah ditutup.
    await _cycle.assert_period_open(db, data.account_id, data.period,
                                    action='mencatat belanja')
    if data.category in _cycle.AUTO_CATEGORIES:
        logger.info('[budget] entri MANUAL pada kategori otomatis category=%s account=%s '
                    'period=%s amount=%s — bisa dobel dengan angka auto',
                    data.category, data.account_id, data.period, data.amount)
    doc = {
        'id': _uid(), 'account_id': data.account_id, 'period': data.period,
        'category': data.category, 'amount': round(_num(data.amount), 2),
        'description': (data.description or '')[:500], 'ref_type': data.ref_type or '',
        'ref_id': data.ref_id or '', 'spend_date': data.spend_date or '',
        'source': 'manual', 'created_at': _now(), 'created_by': user.get('id', ''),
    }
    await db.marketing_spend_entries.insert_one(doc)
    return {'ok': True, 'entry': serialize_doc(doc)}


@router.get('/spend')
async def list_spend(request: Request, account_id: str = Query(...), period: str = Query(...),
                     category: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {'account_id': account_id, 'period': period}
    if category:
        q['category'] = category
    rows = await db.marketing_spend_entries.find(q, {'_id': 0}).sort('created_at', -1).to_list(2000)
    return {'ok': True, 'entries': [serialize_doc(r) for r in rows], 'total': len(rows)}


@router.delete('/spend/{sid}')
async def delete_spend(sid: str, request: Request):
    await require_auth(request)
    db = get_db()
    res = await db.marketing_spend_entries.delete_one({'id': sid})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Spend entry tidak ditemukan.')
    return {'ok': True}


# ── KOL COST CONFIG ──────────────────────────────────────────────────────────────
@router.get('/kol-cost')
async def list_kol_cost(request: Request, account_id: Optional[str] = None):
    user = await require_auth(request)
    db = get_db()
    # F6 (sesi #10) — biaya KOL menempel pada toko yang memakainya.
    q: dict = {}
    _vis = await _scope.visible_account_ids(db, user)
    if _vis is not None:
        q['assigned_account_ids'] = {'$in': _vis}
    if account_id:
        q['assigned_account_ids'] = account_id
    rows = await db.marketing_kol_creators.find(q, {'_id': 0}).to_list(500)
    out = []
    for c in rows:
        out.append({
            'creator_id': c['id'], 'name': c.get('name', ''),
            'creator_code': c.get('creator_code', ''),
            'assigned_account_ids': c.get('assigned_account_ids', []),
            'cost_config': c.get('cost_config') or {'fee_type': 'none', 'fixed_fee': 0, 'commission_pct': 0},
        })
    return {'ok': True, 'creators': out, 'total': len(out)}


@router.get('/kol-cost/{creator_id}')
async def get_kol_cost(creator_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    c = await db.marketing_kol_creators.find_one({'id': creator_id}, {'_id': 0})
    if not c:
        raise HTTPException(404, 'Kreator tidak ditemukan.')
    return {'creator_id': creator_id, 'name': c.get('name', ''),
            'cost_config': c.get('cost_config') or {'fee_type': 'none', 'fixed_fee': 0, 'commission_pct': 0}}


@router.put('/kol-cost/{creator_id}')
async def set_kol_cost(creator_id: str, data: KolCostConfig, request: Request):
    await require_auth(request)
    if data.fee_type not in FEE_TYPES:
        raise HTTPException(400, f"fee_type harus salah satu: {', '.join(FEE_TYPES)}")
    db = get_db()
    c = await db.marketing_kol_creators.find_one({'id': creator_id}, {'_id': 0})
    if not c:
        raise HTTPException(404, 'Kreator tidak ditemukan.')
    cfg = {'fee_type': data.fee_type, 'fixed_fee': round(_num(data.fixed_fee), 2),
           'commission_pct': round(_num(data.commission_pct), 2)}
    await db.marketing_kol_creators.update_one(
        {'id': creator_id}, {'$set': {'cost_config': cfg, 'updated_at': _now()}}
    )
    return {'ok': True, 'creator_id': creator_id, 'cost_config': cfg}


# ── SUMMARY (budget vs spend + ROI) ──────────────────────────────────────────────
@router.get('/summary')
async def budget_summary(request: Request, account_id: str = Query(...), period: str = Query(...)):
    """Rencana vs realisasi per kategori + ROI.

    F5.2 — realisasi kategori `diskon`, `ads`, `komisi`, `kol`, `livehost` sekarang
    **dihitung sistem** dari data sumbernya (pesanan, data iklan, konfigurasi biaya
    kreator, shift live host) dan setiap angkanya membawa `evidence`. Sebelum ini,
    `diskon` selalu Rp 0 walau bulan itu memuat puluhan juta diskon penjual —
    anggaran yang selalu "aman" membuat keputusan diskon diambil tanpa biayanya.
    Angka otomatis TIDAK ditulis sebagai entri belanja (anti dobel-hitung).
    """
    await require_auth(request)
    _valid_period(period)
    db = get_db()

    budget_doc = await db.marketing_budgets.find_one({'account_id': account_id, 'period': period}, {'_id': 0})
    budget = {**_empty_cat(), **((budget_doc or {}).get('budget_by_category') or {})}

    daily = await _cycle.actual_from_daily(db, account_id, period)
    manual, manual_docs = await _cycle.manual_spend(db, account_id, period)
    auto, spend_sources = await _cycle.auto_spend(db, account_id, period, daily)

    spend = {c: round(_num(manual.get(c)) + _num(auto.get(c)), 2) for c in CATEGORIES}

    categories = []
    total_budget = total_spend = 0.0
    for c in CATEGORIES:
        b = round(_num(budget.get(c)), 2)
        s = round(_num(spend.get(c)), 2)
        remaining = round(b - s, 2)
        pct = round((s / b * 100) if b > 0 else (0 if s == 0 else 100), 2)
        categories.append({
            'category': c, 'budget': b, 'spend': s, 'remaining': remaining,
            'manual': round(_num(manual.get(c)), 2), 'auto': round(_num(auto.get(c)), 2),
            'mode': 'auto' if c in _cycle.AUTO_CATEGORIES else 'manual',
            'used_pct': pct, 'status': 'over' if s > b else 'under',
        })
        total_budget += b
        total_spend += s

    sales = _num(daily.get('revenue')) or await _sales_revenue(db, account_id, period)
    total_budget = round(total_budget, 2)
    total_spend = round(total_spend, 2)
    roi_pct = round(((sales - total_spend) / total_spend * 100) if total_spend > 0 else 0, 2)
    spend_of_sales_pct = round((total_spend / sales * 100) if sales > 0 else 0, 2)
    lock = await _cycle.lock_state(db, account_id, period)

    return {
        'account_id': account_id, 'period': period,
        'categories': categories,
        'total_budget': total_budget, 'total_spend': total_spend,
        'total_remaining': round(total_budget - total_spend, 2),
        'total_used_pct': round((total_spend / total_budget * 100) if total_budget > 0 else 0, 2),
        'sales': sales, 'roi_pct': roi_pct, 'spend_of_sales_pct': spend_of_sales_pct,
        'spend_sources': spend_sources,
        'manual_entries': manual_docs,
        'locked': bool(lock.get('locked')), 'lock': lock,
        # kompatibilitas layar lama (dulu hanya dua rincian ini yang ada)
        'kol_detail': next((s.get('detail') for s in spend_sources
                            if s.get('category') == 'kol'), []) or [],
        'livehost_detail': next((s.get('detail') for s in spend_sources
                                 if s.get('category') == 'livehost'), []) or [],
        'label': 'Angka omzet SEBELUM potongan platform.',
    }


# ══════════════════════════════════════════════════════════════════════════════
# F5.1 — SIKLUS: SATU PERMINTAAN = SEMUA ANGKA
# ══════════════════════════════════════════════════════════════════════════════
@cycle_router.get('/summary')
async def cycle_summary_endpoint(request: Request,
                                 account_id: str = Query(..., description='toko'),
                                 period: str = Query(..., description='YYYY-MM')):
    """Target + omzet + anggaran + marjin + ROI untuk SATU toko × SATU bulan."""
    user = await require_auth(request)
    _valid_period(period)
    db = get_db()
    acc = await db.marketing_platform_accounts.find_one({'id': account_id}, {'_id': 0})
    if not acc:
        raise HTTPException(404, 'Akun toko tidak ditemukan.')
    # F6 — toko yang tidak di-assign ke pemakai ini ⇒ 403 (bukan angka orang lain)
    await _scope.assert_account_visible(db, user, account_id)
    settings = await _alert_settings(db)
    return serialize_doc(await _cycle.cycle_summary(db, acc, period, settings=settings))


@cycle_router.get('/overview')
async def cycle_overview_endpoint(request: Request,
                                 period: str = Query(..., description='YYYY-MM'),
                                 account_id: Optional[str] = Query(None),
                                 status: Optional[str] = Query('active')):
    """Semua toko × satu bulan: baris tabel siklus + total + papan perhatian.

    Peringkat & total dihitung di backend supaya layar Marketing, layar Manajemen,
    dan lampiran export tidak mungkin mengurutkan/menjumlah berbeda.
    """
    user = await require_auth(request)
    _valid_period(period)
    db = get_db()
    ids = None
    if account_id:
        await _scope.assert_account_visible(db, user, account_id)
        ids = [account_id]
    elif status:
        rows = await db.marketing_platform_accounts.find(
            {'status': status}, {'_id': 0, 'id': 1}).to_list(300)
        ids = [r['id'] for r in rows]
    # F6 — potong daftar ke toko yang di-assign (None = semua toko)
    visible = await _scope.visible_account_ids(db, user)
    if visible is not None:
        ids = [i for i in (ids or visible) if i in visible]
    settings = await _alert_settings(db)
    return serialize_doc(await _cycle.cycle_overview(db, period, account_ids=ids,
                                                     settings=settings))


async def _alert_settings(db) -> dict:
    """Ambang peringatan dari layar Pengaturan Alert (bila ada)."""
    try:
        return await db.marketing_alert_settings.find_one(
            {'id': 'marketing_alert_settings_singleton'}, {'_id': 0}) or {}
    except Exception as exc:
        logger.warning('[cycle] gagal membaca marketing_alert_settings: %s', exc)
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# F5.3 — KUNCI PERIODE
# ══════════════════════════════════════════════════════════════════════════════
class PeriodLockIn(BaseModel):
    account_id: str
    period: str = Field(..., description='YYYY-MM')
    action: str = Field(..., description='close | reopen')
    reason: str = Field('', description='alasan (wajib)')


@periods_router.get('/lock')
async def get_period_lock(request: Request, account_id: str = Query(...),
                          period: str = Query(...)):
    await require_auth(request)
    _valid_period(period)
    db = get_db()
    return serialize_doc(await _cycle.lock_state(db, account_id, period))


@periods_router.get('/locks')
async def list_period_locks(request: Request, account_id: Optional[str] = Query(None)):
    await require_auth(request)
    db = get_db()
    rows = await _cycle.locked_periods(db, account_id)
    return serialize_doc({'ok': True, 'locks': rows, 'total': len(rows)})


@periods_router.post('/lock')
async def set_period_lock(data: PeriodLockIn, request: Request):
    """Tutup / buka periode satu toko.

    Kenapa dijaga peran: menutup periode membekukan angka yang dipakai rapat &
    laporan; membukanya kembali berarti angka rapat bisa berubah. Keduanya harus
    punya nama dan alasan — karena itu selalu masuk `marketing_change_log`.
    """
    user = await require_auth(request)
    _valid_period(data.period)
    if not _cycle.can_manage_period(user):
        raise HTTPException(
            403, 'Hanya SPV/Manager Marketing (atau owner) yang boleh menutup & membuka '
                 'periode. Minta SPV Marketing melakukannya dari layar Siklus Marketing.')
    db = get_db()
    acc = await db.marketing_platform_accounts.find_one({'id': data.account_id}, {'_id': 0})
    if not acc:
        raise HTTPException(404, 'Akun toko tidak ditemukan.')
    st = await _cycle.set_lock(db, account_id=data.account_id, period=data.period,
                               action=data.action, reason=data.reason, user=user,
                               account=acc)
    return serialize_doc({'ok': True, 'lock': st,
                          'message': ('Periode ditutup — angka bulan ini dibekukan.'
                                      if data.action == 'close' else
                                      'Periode dibuka — perubahan angka dicatat di jejak.')})



# ══════════════════════════════════════════════════════════════════════════════
# F6.4 — JEJAK PERUBAHAN (siapa mengubah target bulan lalu, dari berapa ke berapa)
# ══════════════════════════════════════════════════════════════════════════════
@periods_router.get('/change-log')
async def list_change_log(request: Request,
                          account_id: Optional[str] = Query(None),
                          period: Optional[str] = Query(None),
                          entity: Optional[str] = Query(None),
                          limit: int = Query(50, ge=1, le=300)):
    """Riwayat perubahan angka marketing — target, anggaran, kunci periode.

    KENAPA ini perlu ada di LAYAR: "target bulan lalu kok beda dengan notulen rapat"
    adalah pertanyaan yang tidak pernah bisa dijawab sebelum ini. Sekarang setiap
    perubahan menyimpan nilai LAMA & BARU beserta nama dan peran pelakunya.
    """
    user = await require_auth(request)
    db = get_db()
    q: dict = {}
    if account_id:
        await _scope.assert_account_visible(db, user, account_id)
        q['account_id'] = account_id
    else:
        visible = await _scope.visible_account_ids(db, user)
        if visible is not None:
            q['account_id'] = {'$in': visible}
    if period:
        q['period'] = period
    if entity:
        q['entity'] = entity
    rows = await db.marketing_change_log.find(q, {'_id': 0}).sort('at', -1).to_list(limit)
    return serialize_doc({'ok': True, 'total': len(rows), 'entries': rows})
