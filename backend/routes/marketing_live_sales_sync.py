"""
marketing_live_sales_sync.py — Sinkronisasi penjualan LIVE (LiveHost shift &
Creator session) ke koleksi pusat `marketing_sales_data` (revenue_type='live').

Latar: sales dari host/creator sering "slip" (tidak tercatat) di dashboard
Marketing. Helper ini me-RECOMPUTE (bukan increment) agregat live untuk
(account_id, date) dari sumbernya, sehingga idempotent & aman terhadap
edit/hapus/re-submit.

Semantik marketing_sales_data:
  - revenue_type='total' -> total omzet akun (dipakai untuk revenue utama & ROI)
  - revenue_type='live'  -> porsi dari live selling (host/creator), ditampilkan
    terpisah sebagai `total_revenue_live`. Budget ROI sengaja SKIP 'live' agar
    tidak dobel-hitung dengan 'total'.
"""
import uuid
from datetime import datetime, timezone

from core import marketing_sales_shape as _shape


def _now():
    return datetime.now(timezone.utc)


def _num(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


async def sync_live_sales_to_marketing(db, account_id, date):
    """Recompute marketing_sales_data (revenue_type='live') utk (account_id, date).

    Mengagregasi seluruh LiveHost shift (yg sudah ada performance) + Creator
    session pada account+date tsb. Aman dipanggil berulang kali.
    """
    if not account_id or not date:
        return
    account = await db.marketing_platform_accounts.find_one({'id': account_id}, {'_id': 0})
    if not account:
        return

    shifts = await db.marketing_livehost_shifts.find(
        {'account_id': account_id, 'date': date}, {'_id': 0}
    ).to_list(1000)
    sessions = await db.marketing_creator_sessions.find(
        {'account_id': account_id, 'date': date}, {'_id': 0}
    ).to_list(1000)

    revenue = sum(_num(s.get('revenue')) for s in shifts) + sum(_num(s.get('revenue')) for s in sessions)
    orders = int(sum(_num(s.get('orders')) for s in shifts) + sum(_num(s.get('orders')) for s in sessions))
    viewers = int(sum(_num(s.get('viewers')) for s in shifts) + sum(_num(s.get('viewers')) for s in sessions))
    peak = 0
    for s in shifts:
        peak = max(peak, int(_num(s.get('peak_viewers'))))
    live_sessions_count = len([s for s in shifts if s.get('reviewed_at') or _num(s.get('revenue')) > 0]) + len(sessions)
    aov = (revenue / orders) if orders else 0

    key = {'account_id': account_id, 'date': date, 'revenue_type': 'live'}
    existing = await db.marketing_sales_data.find_one(key, {'_id': 0, 'id': 1})

    # Jangan buat dokumen kosong bila memang tidak ada data bermakna.
    if not existing and revenue == 0 and orders == 0 and viewers == 0:
        return

    # F0.2 (2026-08-12) — bentuk dokumen dibuat pembuat kanonik yang SAMA dengan
    # entri manual & impor (`core.marketing_sales_shape`), supaya tidak ada lagi
    # tiga bentuk berbeda untuk rekap harian yang sama (D01).
    doc = _shape.build_daily_doc(
        account=account,
        date=date,
        revenue_type='live',
        flat={
            'revenue': round(revenue),
            'orders': orders,
            'aov': round(aov),
            'gmv': round(revenue),
            'viewers': viewers,
            'peak_viewers': peak,
            'live_sessions': live_sessions_count,
        },
        source=_shape.SOURCE_LIVE_AUTO,
    )
    # Penulis ini HANYA memiliki grup `metrics` & `live_metrics` untuk dokumen live.
    # Grup lain (kepuasan pelanggan, funnel, dll.) milik pintu lain — jangan ditimpa
    # jadi nol, tetapi pastikan ADA saat dokumen pertama kali dibuat.
    OWNED = ('metrics', 'live_metrics')
    META = ('account_code', 'account_name', 'platform', 'revenue_basis',
            'source', 'locked_source', 'shape_version', 'updated_at')
    set_doc = {k: v for k, v in doc.items() if k in OWNED or k in META}
    on_insert = {k: v for k, v in doc.items() if k not in set_doc and k not in key}
    on_insert.update({'id': str(uuid.uuid4()), 'import_history_id': None,
                      'created_at': _now(), 'created_by': 'system-auto'})

    await db.marketing_sales_data.update_one(
        key,
        {'$set': set_doc, '$setOnInsert': on_insert},
        upsert=True,
    )
