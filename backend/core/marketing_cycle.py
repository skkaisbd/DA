"""core.marketing_cycle — SATU SUMBER ANGKA **SIKLUS** target → anggaran → omzet (F5).

KENAPA BERKAS INI ADA
---------------------
Sebelum F5, satu bulan kerja marketing dibaca dari **tiga pulau** yang tidak pernah
bertemu:

1. `marketing_account_targets`  — target bulanan (diketik SPV).
2. `marketing_budgets` + `marketing_spend_entries` — rencana & realisasi anggaran.
3. `marketing_sales_data`       — omzet harian (sejak F2 **diturunkan** dari pesanan).

Akibatnya nyata dan berulang di rapat:

* Layar **Target** menyebut capaian 59,8% sementara layar **Anggaran** menyebut ROI
  positif — keduanya benar menurut sumbernya sendiri, dan tidak ada satu pun cara
  membuktikan mana yang dipakai untuk mengambil keputusan.
* Kategori anggaran **`diskon` selalu Rp 0** walau 559 pesanan bulan itu memuat
  Rp 48 juta diskon penjual, karena realisasi diskon hanya bisa masuk lewat **entri
  manual** yang tidak pernah diisi siapa pun. Anggaran yang selalu "aman" membuat
  keputusan menaikkan diskon diambil tanpa tahu biayanya.
* Tidak ada **kunci periode**: angka bulan yang sudah dirapatkan masih bisa berubah
  seminggu kemudian, jadi notulen rapat dan sistem tidak lagi bisa disamakan.

Berkas ini menghitung SEMUANYA di satu tempat supaya layar Marketing, layar
Manajemen, notifikasi, dan lampiran export **tidak mungkin** berbeda angka.

ATURAN YANG TIDAK BISA DINEGOSIASI
----------------------------------
* **Omzet dibaca dari rekap harian turunan** (`marketing_sales_data`,
  `revenue_type='total'`) — bukan dihitung ulang dari pesanan di sini. Kalau F5
  menghitung sendiri, akan lahir angka omzet KEEMPAT. Override SPV (F2) otomatis
  ikut terpakai karena ia menulis ke dokumen yang sama.
* **Realisasi anggaran otomatis TIDAK menulis `marketing_spend_entries`.** Angka
  otomatis dihitung saat dibaca; menuliskannya akan dobel dengan entri manual pada
  hari staf mencatat hal yang sama.
* **Setiap angka otomatis membawa `evidence`** (jumlah dokumen sumbernya). Angka
  tanpa bukti tidak bisa dibantah maupun dipercaya.
* **Marjin selalu ditemani `hpp_coverage_pct`.** Marjin yang dihitung dari 3 item
  ber-HPP di antara 600 item adalah angka yang MENIPU; layar wajib bisa menyebut
  cakupannya.
* **Hari berjalan memakai jam Asia/Jakarta (WIB)**, bukan UTC. Memakai UTC membuat
  rapat pagi tanggal 1 membaca "bulan lalu" (cacat yang sama pernah terjadi di
  laporan mingguan).
"""
from __future__ import annotations

import calendar
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core import marketing_sales_shape as _shape
from core import marketing_daily_rollup as _rollup
from core import marketing_returns as _ret

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))

ACCOUNTS = "marketing_platform_accounts"
DAILY = "marketing_sales_data"
ORDERS = "marketing_orders"
TARGETS = "marketing_account_targets"
BUDGETS = "marketing_budgets"
SPEND = "marketing_spend_entries"
ADS = "marketing_ads_data"
CATALOG_ITEMS = "marketing_catalog_items"
LOCKS = "marketing_period_locks"
CHANGE_LOG = "marketing_change_log"
CREATORS = "marketing_kol_creators"

# Kategori anggaran — `komisi` DITAMBAH di F5 (D08/D09): komisi kreator selama ini
# tidak punya tempat, jadi biaya penjualan terbesar setelah diskon tidak pernah
# muncul di rencana anggaran.
CATEGORIES: Tuple[str, ...] = ('ads', 'kol', 'komisi', 'livehost', 'sample', 'diskon')

# Kategori yang realisasinya DIHITUNG SISTEM (bukan diketik). Layar menandainya
# `auto` supaya staf tidak mencatat ulang hal yang sama secara manual.
AUTO_CATEGORIES: Tuple[str, ...] = ('diskon', 'ads', 'komisi', 'kol', 'livehost')

# Status pesanan yang uangnya tidak pernah ada (sama dengan F2, ditulis sekali di
# marketing_daily_rollup — diimpor supaya tidak ada dua daftar yang bisa berbeda).
EXCLUDED_FOR_REVENUE = ('cancelled',)

# Ambang peringatan bawaan (bisa ditimpa `marketing_alert_settings`).
DEFAULT_THRESHOLDS = {
    'target_behind_pct': 15.0,     # selisih pace − capaian ⇒ kuning
    'target_behind_red_pct': 30.0,  # ⇒ merah
    'budget_warn_ratio': 0.8,      # terpakai / rencana ⇒ kuning
    'budget_over_ratio': 1.0,      # ⇒ merah
}

LOCK_ACTIONS = ('close', 'reopen')
# Peran yang boleh menutup/membuka periode. `spv_marketing` disiapkan untuk F6;
# `manager_marketing` adalah peran yang SUDAH ADA di DB (seed_role_accounts).
PERIOD_MANAGER_ROLES = ('superadmin', 'admin', 'owner', 'spv_marketing',
                        'manager_marketing', 'accounting')


# ══════════════════════════════════════════════════════════════════════════════
# UTIL
# ══════════════════════════════════════════════════════════════════════════════
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _num(v: Any, d: float = 0.0) -> float:
    try:
        if v is None or v == '':
            return float(d)
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def _int(v: Any, d: int = 0) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return int(d)


def _r(v: Any, nd: int = 2) -> float:
    return round(_num(v), nd)


def valid_period(period: str) -> Tuple[int, int]:
    """`YYYY-MM` **atau** `YYYY-MM-DD` → (tahun, bulan).

    SESI #34 — anggaran marketing kini boleh berperiode **7 hari** (kuncinya
    tanggal mulai, `YYYY-MM-DD`), sementara SIKLUS target/pace di modul ini tetap
    berbasis bulan. Sebelum perbaikan ini, fungsi ini hanya menerima `YYYY-MM`
    sehingga `GET /api/marketing/budget/summary?period=2026-08-17` menabrak
    `ValueError: unconverted data remains: -17` → 500, dan tab "Budget & Alokasi"
    menampilkan Rp 0 tanpa pesan apa pun (gagal diam-diam).

    Keputusan: periode 7 hari dipetakan ke BULAN tempat tanggal mulainya berada.
    Yang dipakai untuk realisasi 7 hari tetap rentang tanggal di
    `routes/marketing_budget.period_bounds` — fungsi ini hanya menjawab
    "bulan mana" untuk perhitungan pace/siklus yang memang bulanan.
    """
    raw = str(period or '').strip()
    for fmt in ('%Y-%m', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.year, dt.month
        except ValueError:
            continue
    raise ValueError(f"periode harus YYYY-MM atau YYYY-MM-DD, dapat: {raw!r}")


def period_of(year: int, month: int) -> str:
    return f"{int(year):04d}-{int(month):02d}"


def empty_categories(default: float = 0.0) -> Dict[str, float]:
    return {c: float(default) for c in CATEGORIES}


def today_wib() -> datetime:
    """Hari ini menurut jam dinding WIB — dasar `days_elapsed` & pace."""
    return datetime.now(WIB)


def month_progress(period: str, today: Optional[datetime] = None) -> Dict[str, Any]:
    """Berapa bagian bulan yang sudah berjalan (WIB).

    Bulan yang sudah lewat = 100%; bulan yang belum datang = 0%. Tanpa ini,
    "capaian 60%" pada tanggal 3 dibaca sebagai gagal, padahal bulannya baru mulai.
    """
    y, m = valid_period(period)
    days_total = calendar.monthrange(y, m)[1]
    now = (today or today_wib())
    if now.tzinfo is None:
        now = now.replace(tzinfo=WIB)
    now = now.astimezone(WIB)
    if (now.year, now.month) == (y, m):
        days_elapsed = min(days_total, now.day)
        state = 'running'
    elif (now.year, now.month) > (y, m):
        days_elapsed = days_total
        state = 'closed_month'
    else:
        days_elapsed = 0
        state = 'future'
    pace = round(days_elapsed / days_total * 100, 2) if days_total else 0.0
    return {'days_total': days_total, 'days_elapsed': days_elapsed,
            'pace_pct': pace, 'month_state': state,
            'date_from': f"{y:04d}-{m:02d}-01",
            'date_to': f"{y:04d}-{m:02d}-{days_total:02d}"}


# ══════════════════════════════════════════════════════════════════════════════
# OMZET (dibaca dari rekap harian turunan — SSOT F2)
# ══════════════════════════════════════════════════════════════════════════════
async def actual_from_daily(db, account_id: str, period: str) -> Dict[str, Any]:
    """Angka realisasi bulan ini dari rekap harian (`revenue_type='total'`).

    Mengembalikan juga `sources` (dari `source` dokumen) supaya layar bisa
    menyebut apakah angkanya turunan pesanan, impor rekap, atau override SPV —
    tiga hal yang tidak boleh terlihat sama.
    """
    rows = await db[DAILY].find(
        {'account_id': account_id, 'date': {'$regex': f'^{period}'},
         'revenue_type': 'total'},
        {'_id': 0},
    ).to_list(400)

    tot = {'revenue': 0.0, 'revenue_product': 0.0, 'revenue_order_amount': 0.0,
           'gross_before_discount': 0.0, 'seller_discount': 0.0,
           'platform_discount': 0.0, 'orders': 0, 'units': 0, 'buyers_daily_sum': 0}
    sources: Dict[str, int] = {}
    days = 0
    for r in rows:
        m = _shape.read_metrics(r)
        tot['revenue'] += _num(m.get('revenue'))
        tot['revenue_product'] += _num(m.get('revenue_product'))
        tot['revenue_order_amount'] += _num(m.get('revenue_order_amount'))
        tot['gross_before_discount'] += _num(m.get('gross_before_discount'))
        tot['seller_discount'] += _num(m.get('seller_discount'))
        tot['platform_discount'] += _num(m.get('platform_discount'))
        tot['orders'] += _int(m.get('orders'))
        tot['units'] += _int(m.get('units'))
        tot['buyers_daily_sum'] += _int(m.get('buyers'))
        src = r.get('source') or 'unknown'
        sources[src] = sources.get(src, 0) + 1
        days += 1

    for k in ('revenue', 'revenue_product', 'revenue_order_amount',
              'gross_before_discount', 'seller_discount', 'platform_discount'):
        tot[k] = _r(tot[k])
    tot['aov'] = _r(tot['revenue'] / tot['orders']) if tot['orders'] else 0.0
    tot['days_with_data'] = days
    tot['sources'] = sources
    # SESI #9 — bahan "omzet setelah retur" (KEDUA basis + cakupan hari). Angka
    # bruto di atas TIDAK disentuh; retur hanya DITAMBAHKAN sebagai angka sendiri.
    tot['returns_split'] = _ret.from_daily_rows(rows)
    return tot


# ══════════════════════════════════════════════════════════════════════════════
# MARJIN (HPP dari katalog — selalu dengan CAKUPAN)
# ══════════════════════════════════════════════════════════════════════════════
async def margin_from_orders(db, account_id: str, period: str) -> Dict[str, Any]:
    """Marjin kotor bulan ini + **cakupan HPP**.

    HPP tidak ikut di ekspor Seller Center, jadi ia diambil dari item katalog yang
    tertaut (`items[].catalog_item_id` → `marketing_catalog_items.hpp`). Item yang
    belum tertaut / ber-HPP 0 **tidak dikarang**: unitnya masuk `units_uncovered`
    dan cakupannya turun. Marjin dihitung HANYA atas bagian yang ber-HPP, dan
    layar wajib menyebut cakupannya.
    """
    y, m = valid_period(period)
    days_total = calendar.monthrange(y, m)[1]
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=days_total)
    date_from = f"{y:04d}-{m:02d}-01"
    date_to = f"{y:04d}-{m:02d}-{days_total:02d}"

    orders = await db[ORDERS].find({
        'account_id': account_id,
        '$or': [
            {'order_date': {'$gte': start, '$lt': end}},
            {'order_date': {'$gte': date_from, '$lte': date_to + '\uffff'}},
        ],
    }, {'_id': 0, 'status': 1, 'items': 1, 'buyer_username': 1,
        'customer_phone': 1, 'customer_name': 1}).to_list(30000)

    live = [o for o in orders if (o.get('status') or '') not in EXCLUDED_FOR_REVENUE]

    item_ids = set()
    for o in live:
        for it in (o.get('items') or []):
            if it.get('catalog_item_id'):
                item_ids.add(it['catalog_item_id'])
    hpp_map: Dict[str, float] = {}
    if item_ids:
        ids = list(item_ids)
        CHUNK = 500
        for n in range(0, len(ids), CHUNK):
            docs = await db[CATALOG_ITEMS].find(
                {'id': {'$in': ids[n:n + CHUNK]}}, {'_id': 0, 'id': 1, 'hpp': 1}
            ).to_list(CHUNK)
            for d in docs:
                hpp_map[d['id']] = _num(d.get('hpp'))

    units_total = units_cov = 0
    lines_total = lines_cov = 0
    rev_cov = rev_all = hpp_total = 0.0
    for o in live:
        for it in (o.get('items') or []):
            # Pembacaan DEFENSIF lewat SSOT `marketing_daily_rollup`: pesanan hasil
            # impor memakai `quantity`/`sku_subtotal_after_discount`, pesanan yang
            # diinput staf memakai `qty`/`price`. Membaca hanya satu bentuk membuat
            # marjin pesanan manual selalu Rp 0 tanpa satu pun galat.
            qty = _rollup.item_qty(it)
            rev = _rollup.item_revenue(it)
            units_total += qty
            lines_total += 1
            rev_all += rev
            hpp_unit = hpp_map.get(it.get('catalog_item_id') or '', 0.0)
            if hpp_unit > 0:
                units_cov += qty
                lines_cov += 1
                rev_cov += rev
                hpp_total += hpp_unit * qty

    buyers = {str(o.get('buyer_username') or o.get('customer_phone')
                  or o.get('customer_name') or '').strip().lower() for o in live}
    buyers.discard('')

    gross_profit = _r(rev_cov - hpp_total)
    coverage = _r(units_cov / units_total * 100) if units_total else 0.0
    return {
        'revenue': _r(rev_cov),
        'revenue_all_items': _r(rev_all),
        'hpp': _r(hpp_total),
        'gross_profit': gross_profit,
        'gross_margin_pct': _r(gross_profit / rev_cov * 100) if rev_cov > 0 else 0.0,
        'hpp_coverage_pct': coverage,
        'units_total': units_total,
        'units_covered': units_cov,
        'units_uncovered': units_total - units_cov,
        'lines_total': lines_total,
        'lines_covered': lines_cov,
        'orders_scanned': len(live),
        'buyers_unique': len(buyers),
        'trustworthy': coverage >= 80.0,
    }


# ══════════════════════════════════════════════════════════════════════════════
# REALISASI ANGGARAN OTOMATIS (F5.2)
# ══════════════════════════════════════════════════════════════════════════════
def _creator_cost(config: dict, revenue: float) -> float:
    """Biaya satu kreator dari `cost_config` (fee tetap dan/atau komisi %)."""
    if not config:
        return 0.0
    ft = (config.get('fee_type') or 'none').lower()
    cost = 0.0
    if ft in ('fixed', 'both'):
        cost += _num(config.get('fixed_fee'))
    if ft in ('commission', 'both'):
        cost += revenue * _num(config.get('commission_pct')) / 100.0
    return _r(cost)


async def _auto_diskon(db, account_id: str, period: str,
                       daily: Optional[dict] = None) -> Dict[str, Any]:
    """Realisasi kategori `diskon` — diskon penjual + subsidi ongkir penjual.

    Dihitung dari **pesanan** karena subsidi ongkir hanya ada di tingkat pesanan
    (rekap harian menyimpan diskon item saja). Toko yang belum memakai impor
    pesanan (masih impor rekap `sales_daily`) tetap dapat angka dari rekap, dengan
    `basis` yang menyebutkan asalnya — supaya "Rp 0" tidak pernah berarti dua hal.
    """
    y, m = valid_period(period)
    days_total = calendar.monthrange(y, m)[1]
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=days_total)
    date_from = f"{y:04d}-{m:02d}-01"
    date_to = f"{y:04d}-{m:02d}-{days_total:02d}"
    rows = await db[ORDERS].find({
        'account_id': account_id,
        '$or': [
            {'order_date': {'$gte': start, '$lt': end}},
            {'order_date': {'$gte': date_from, '$lte': date_to + '\uffff'}},
        ],
    }, {'_id': 0, 'status': 1, 'seller_discount_total': 1, 'discount_seller': 1,
        'items': 1, 'shipping_fee_seller_discount': 1}).to_list(30000)
    live = [r for r in rows if (r.get('status') or '') not in EXCLUDED_FOR_REVENUE]
    if live:
        # `discount_seller` (pesanan input manual) ikut terbaca lewat SSOT pembaca
        # defensif — kalau tidak, diskon yang diberikan staf lewat layar hilang
        # dari realisasi anggaran.
        disc = sum(_rollup.order_seller_discount(r) for r in live)
        ship = sum(_num(r.get('shipping_fee_seller_discount')) for r in live)
        return {'amount': _r(disc + ship), 'basis': 'orders',
                'evidence': f"{len(live)} pesanan (diskon penjual {_r(disc):,.0f} "
                            f"+ subsidi ongkir {_r(ship):,.0f})".replace(',', '.'),
                'docs': len(live),
                'breakdown': {'seller_discount': _r(disc), 'shipping_subsidy': _r(ship)}}
    d = daily or {}
    amount = _num(d.get('seller_discount'))
    if amount > 0:
        return {'amount': _r(amount), 'basis': 'daily_recap',
                'evidence': f"{_int(d.get('days_with_data'))} hari rekap "
                            f"(tanpa impor pesanan ⇒ subsidi ongkir belum terhitung)",
                'docs': _int(d.get('days_with_data')),
                'breakdown': {'seller_discount': _r(amount), 'shipping_subsidy': 0.0}}
    return {'amount': 0.0, 'basis': 'none',
            'evidence': 'belum ada pesanan/rekap bulan ini', 'docs': 0,
            'breakdown': {'seller_discount': 0.0, 'shipping_subsidy': 0.0}}


async def _auto_ads(db, account_id: str, period: str) -> Dict[str, Any]:
    """Biaya iklan bulan `period` dari `marketing_ads_data`.

    F7.2 — `date` di koleksi ini bisa berbentuk **string** `YYYY-MM-DD` (impor
    laporan iklan Shopee, entri manual) ATAU **datetime** (jenis impor `ads`
    lama). Kueri yang hanya memakai `$regex` melewatkan seluruh dokumen datetime,
    dan akibatnya realisasi anggaran iklan tampak Rp 0 padahal datanya ada — nol
    yang paling mahal, karena tampak seperti "belum belanja iklan".
    """
    y, m = valid_period(period)
    days_total = calendar.monthrange(y, m)[1]
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=days_total)
    rows = await db[ADS].find(
        {'account_id': account_id,
         '$or': [
             {'date': {'$regex': f'^{period}'}},
             {'date': {'$gte': start, '$lt': end}},
         ]},
        {'_id': 0, 'spend': 1, 'campaign_name': 1, 'period_start': 1, 'period_end': 1},
    ).to_list(5000)
    total = sum(_num(r.get('spend')) for r in rows)
    ranged = sorted({f"{str(r.get('period_start'))[:10]}..{str(r.get('period_end'))[:10]}"
                     for r in rows if r.get('period_start')})
    evidence = f"{len(rows)} baris data iklan"
    if ranged:
        evidence += f" (periode laporan: {', '.join(ranged[:4])})"
    return {'amount': _r(total), 'basis': 'ads_data',
            'evidence': evidence, 'docs': len(rows)}


async def _auto_komisi(db, account_id: str, period: str) -> Dict[str, Any]:
    """Komisi kreator dari pesanan yang MEMBAWA `creator_id`.

    Kalau ekspor platform tidak memuat kreator (kasus TikTok "Untuk Dikirim"),
    hasilnya 0 **dengan alasan tertulis** — bukan 0 yang tampak seperti "tidak ada
    komisi". Itu perbedaan antara data belum ada dan biaya benar-benar nol.
    """
    y, m = valid_period(period)
    days_total = calendar.monthrange(y, m)[1]
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=days_total)
    date_from = f"{y:04d}-{m:02d}-01"
    date_to = f"{y:04d}-{m:02d}-{days_total:02d}"
    rows = await db[ORDERS].find({
        'account_id': account_id,
        'creator_id': {'$nin': [None, '']},
        '$or': [
            {'order_date': {'$gte': start, '$lt': end}},
            {'order_date': {'$gte': date_from, '$lte': date_to + '\uffff'}},
        ],
    }, {'_id': 0, 'status': 1, 'creator_id': 1, 'revenue_product': 1,
        'order_amount': 1}).to_list(30000)
    live = [r for r in rows if (r.get('status') or '') not in EXCLUDED_FOR_REVENUE]
    if not live:
        return {'amount': 0.0, 'basis': 'orders_creator',
                'evidence': '0 pesanan membawa kreator (ekspor pesanan tidak memuat kreator)',
                'docs': 0, 'detail': []}
    per_creator: Dict[str, float] = {}
    for r in live:
        cid = r.get('creator_id')
        rev = _num(r.get('revenue_product')) or _num(r.get('order_amount'))
        per_creator[cid] = per_creator.get(cid, 0.0) + rev
    creators = await db[CREATORS].find(
        {'id': {'$in': list(per_creator.keys())}}, {'_id': 0}
    ).to_list(500)
    cfg_by_id = {c['id']: (c.get('cost_config') or {}) for c in creators}
    name_by_id = {c['id']: c.get('name', '') for c in creators}
    total = 0.0
    detail = []
    for cid, rev in per_creator.items():
        cfg = cfg_by_id.get(cid) or {}
        # Hanya bagian KOMISI (persentase) — fee tetap tetap milik kategori `kol`
        # supaya satu biaya tidak dihitung di dua kategori.
        pct = _num(cfg.get('commission_pct'))
        ft = (cfg.get('fee_type') or 'none').lower()
        cost = _r(rev * pct / 100.0) if ft in ('commission', 'both') else 0.0
        total += cost
        detail.append({'creator_id': cid, 'creator_name': name_by_id.get(cid, ''),
                       'revenue': _r(rev), 'commission_pct': pct, 'cost': cost})
    return {'amount': _r(total), 'basis': 'orders_creator',
            'evidence': f"{len(live)} pesanan · {len(per_creator)} kreator",
            'docs': len(live), 'detail': detail}


async def _auto_kol_fee(db, account_id: str, period: str) -> Dict[str, Any]:
    """Fee kreator (bagian TETAP) untuk kreator yang di-assign ke toko ini."""
    creators = await db[CREATORS].find(
        {'assigned_account_ids': account_id}, {'_id': 0}
    ).to_list(500)
    total = 0.0
    detail = []
    for c in creators:
        cfg = c.get('cost_config') or {}
        ft = (cfg.get('fee_type') or 'none').lower()
        if ft not in ('fixed', 'both'):
            continue
        fee = _num(cfg.get('fixed_fee'))
        if fee <= 0:
            continue
        total += fee
        detail.append({'creator_id': c['id'], 'creator_name': c.get('name', ''),
                       'fixed_fee': _r(fee)})
    return {'amount': _r(total), 'basis': 'kol_cost_config',
            'evidence': f"{len(detail)} kreator ber-fee tetap", 'docs': len(detail),
            'detail': detail}


async def _auto_livehost(db, account_id: str, period: str) -> Dict[str, Any]:
    """Biaya Live Host = **GAJI BULANAN** dari master HR (sesi #34).

    Sebelumnya: Σ `total_pay` shift ber-status `calculated` (upah per sesi).
    Pemilik menghapus upah per-sesi — host digaji bulanan lewat payroll HR — jadi
    rumus lama sekarang SELALU menghasilkan Rp 0 dan biaya live host hilang dari
    anggaran marketing. Diganti: gaji bulanan host yang PUNYA shift di periode
    ini, dibagi rata antar toko yang dilayaninya (satu orang tidak dihitung penuh
    di dua toko) dan diprorata bila periode lebih pendek dari 30 hari (mode 7
    hari). Nominal dibaca dari `rahaza_employees` lewat `livehost.employee_id`;
    host yang belum tertaut TIDAK diberi angka karangan — ia disebut di `detail`
    dengan `salary_source: 'none'`.
    """
    y, m = valid_period(period)
    if len(str(period).strip()) == 10:      # periode 7 hari (YYYY-MM-DD)
        start = datetime.strptime(str(period).strip(), '%Y-%m-%d')
        end = start + timedelta(days=6)
        days = 7
    else:
        start = datetime(y, m, 1)
        days = calendar.monthrange(y, m)[1]
        end = datetime(y, m, days)
    lo, hi = start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')

    shifts = await db.marketing_livehost_shifts.find(
        {'date': {'$gte': lo, '$lte': hi + 'T23:59:59'}},
        {'_id': 0, 'host_id': 1, 'account_id': 1},
    ).to_list(20000)
    if not shifts:
        return {'amount': 0.0, 'basis': 'livehost_monthly_salary',
                'evidence': 'tidak ada jadwal live pada periode ini', 'docs': 0,
                'detail': []}
    host_accounts: Dict[str, set] = {}
    for s in shifts:
        host_accounts.setdefault(s.get('host_id'), set()).add(s.get('account_id'))
    hosts = await db.marketing_livehosts.find(
        {'id': {'$in': [h for h in host_accounts if h]}},
        {'_id': 0, 'id': 1, 'name': 1, 'employee_id': 1, 'monthly_salary': 1},
    ).to_list(500)
    from core import livehost_salary as _lhs
    sal = await _lhs.monthly_salary_map(db, hosts)

    total, detail, unlinked = 0.0, [], 0
    for h in hosts:
        accs = {a for a in host_accounts.get(h['id'], set()) if a}
        if account_id not in accs:
            continue
        info = sal.get(h['id']) or {'salary': 0.0, 'source': 'none', 'reason': ''}
        salary = _num(info.get('salary'))
        if salary <= 0:
            unlinked += 1
        charged = _r(salary / max(1, len(accs)) * min(1.0, days / 30.0))
        total += charged
        detail.append({'host_id': h['id'], 'host_name': h.get('name', ''),
                       'monthly_salary': _r(salary),
                       'salary_source': info.get('source'),
                       'salary_gap': info.get('reason') or '',
                       'accounts_served': len(accs), 'days_in_period': days,
                       'total_pay': charged})
    ev = f"{len(detail)} host bergaji bulanan (prorata {days} hari)"
    if unlinked:
        ev += f" · {unlinked} host belum ditautkan ke karyawan HR"
    return {'amount': _r(total), 'basis': 'livehost_monthly_salary',
            'evidence': ev, 'docs': len(detail), 'detail': detail}


async def manual_spend(db, account_id: str, period: str) -> Tuple[Dict[str, float], int]:
    rows = await db[SPEND].find(
        {'account_id': account_id, 'period': period}, {'_id': 0, 'category': 1, 'amount': 1}
    ).to_list(5000)
    by_cat = empty_categories()
    for r in rows:
        c = r.get('category')
        if c in by_cat:
            by_cat[c] += _num(r.get('amount'))
    return {k: _r(v) for k, v in by_cat.items()}, len(rows)


async def auto_spend(db, account_id: str, period: str,
                     daily: Optional[dict] = None) -> Tuple[Dict[str, float], List[dict]]:
    """Realisasi anggaran yang DIHITUNG SISTEM per kategori + daftar buktinya."""
    diskon = await _auto_diskon(db, account_id, period, daily)
    ads = await _auto_ads(db, account_id, period)
    komisi = await _auto_komisi(db, account_id, period)
    kol = await _auto_kol_fee(db, account_id, period)
    lh = await _auto_livehost(db, account_id, period)
    by_cat = empty_categories()
    by_cat['diskon'] = diskon['amount']
    by_cat['ads'] = ads['amount']
    by_cat['komisi'] = komisi['amount']
    by_cat['kol'] = kol['amount']
    by_cat['livehost'] = lh['amount']
    sources = [
        {'category': 'diskon', 'amount': diskon['amount'], 'source': 'auto',
         'basis': diskon['basis'], 'evidence': diskon['evidence'], 'docs': diskon['docs'],
         'breakdown': diskon.get('breakdown')},
        {'category': 'ads', 'amount': ads['amount'], 'source': 'auto',
         'basis': ads['basis'], 'evidence': ads['evidence'], 'docs': ads['docs']},
        {'category': 'komisi', 'amount': komisi['amount'], 'source': 'auto',
         'basis': komisi['basis'], 'evidence': komisi['evidence'], 'docs': komisi['docs'],
         'detail': komisi.get('detail')},
        {'category': 'kol', 'amount': kol['amount'], 'source': 'auto',
         'basis': kol['basis'], 'evidence': kol['evidence'], 'docs': kol['docs'],
         'detail': kol.get('detail')},
        {'category': 'livehost', 'amount': lh['amount'], 'source': 'auto',
         'basis': lh['basis'], 'evidence': lh['evidence'], 'docs': lh['docs'],
         'detail': lh.get('detail')},
    ]
    return by_cat, sources


# ══════════════════════════════════════════════════════════════════════════════
# KUNCI PERIODE (F5.3)
# ══════════════════════════════════════════════════════════════════════════════
async def lock_state(db, account_id: str, period: str) -> Dict[str, Any]:
    doc = await db[LOCKS].find_one(
        {'account_id': account_id, 'period': period}, {'_id': 0})
    if not doc:
        return {'locked': False, 'account_id': account_id, 'period': period}
    return {
        'locked': bool(doc.get('locked')),
        'account_id': account_id, 'period': period,
        'reason': doc.get('reason') or '',
        'closed_at': doc.get('closed_at'), 'closed_by_name': doc.get('closed_by_name') or '',
        'reopened_at': doc.get('reopened_at'), 'reopened_by_name': doc.get('reopened_by_name') or '',
        'history': (doc.get('history') or [])[-20:],
    }


async def is_locked(db, account_id: str, period: str) -> bool:
    doc = await db[LOCKS].find_one({'account_id': account_id, 'period': period},
                                   {'_id': 0, 'locked': 1})
    return bool((doc or {}).get('locked'))


async def locked_periods(db, account_id: Optional[str] = None) -> List[dict]:
    q: Dict[str, Any] = {'locked': True}
    if account_id:
        q['account_id'] = account_id
    return await db[LOCKS].find(q, {'_id': 0}).sort('period', -1).to_list(500)


def period_from_date(date_str: str) -> str:
    return str(date_str or '')[:7]


async def assert_period_open(db, account_id: str, period_or_date: str, *,
                             action: str = 'menyimpan data') -> None:
    """Melempar **HTTP 423** bila periode toko ini sudah ditutup.

    423 (Locked) dipilih dengan sengaja: 403 berarti "kamu tidak berhak" (yang
    membuat staf mengira akunnya salah), sedangkan yang terjadi adalah "bulannya
    sudah ditutup" — dan jalan keluarnya bukan minta hak baru, melainkan minta SPV
    membuka periode.
    """
    from fastapi import HTTPException  # impor lokal: core tidak mengikat web layer
    period = period_or_date if len(str(period_or_date)) == 7 else period_from_date(period_or_date)
    if not account_id or not period:
        return
    st = await lock_state(db, account_id, period)
    if st.get('locked'):
        who = st.get('closed_by_name') or 'SPV Marketing'
        raise HTTPException(
            423,
            f"Periode {period} untuk toko ini sudah DITUTUP oleh {who}"
            + (f" — alasan: {st.get('reason')}" if st.get('reason') else '')
            + f". {action.capitalize()} tidak bisa dilakukan sampai periode dibuka kembali "
              "(Siklus Marketing → tombol Buka Periode).",
        )


async def set_lock(db, *, account_id: str, period: str, action: str, reason: str,
                   user: dict, account: Optional[dict] = None) -> Dict[str, Any]:
    """Tutup / buka periode. Idempoten & selalu meninggalkan jejak."""
    from fastapi import HTTPException
    if action not in LOCK_ACTIONS:
        raise HTTPException(400, f"action harus salah satu: {', '.join(LOCK_ACTIONS)}")
    valid_period(period)
    if action == 'close' and not (reason or '').strip():
        raise HTTPException(400, 'Alasan penutupan periode wajib diisi — '
                                 'angka yang dibekukan harus bisa dipertanggungjawabkan.')
    if action == 'reopen' and not (reason or '').strip():
        raise HTTPException(400, 'Alasan pembukaan periode wajib diisi — '
                                 'membuka bulan yang sudah dirapatkan harus ada sebabnya.')
    now = _now()
    uname = user.get('name') or user.get('email') or user.get('id') or 'sistem'
    before = await lock_state(db, account_id, period)
    entry = {'action': action, 'reason': (reason or '').strip()[:500],
             'by': user.get('id', ''), 'by_name': uname, 'at': now}
    set_fields: Dict[str, Any] = {
        'locked': action == 'close',
        'reason': entry['reason'],
        'updated_at': now, 'updated_by': user.get('id', ''),
        'account_name': (account or {}).get('account_name', ''),
        'platform': (account or {}).get('platform', ''),
    }
    if action == 'close':
        set_fields.update({'closed_at': now, 'closed_by': user.get('id', ''),
                           'closed_by_name': uname})
    else:
        set_fields.update({'reopened_at': now, 'reopened_by': user.get('id', ''),
                           'reopened_by_name': uname})
    await db[LOCKS].update_one(
        {'account_id': account_id, 'period': period},
        {'$set': set_fields,
         '$push': {'history': {'$each': [entry], '$slice': -50}},
         '$setOnInsert': {'id': str(uuid.uuid4()), 'account_id': account_id,
                          'period': period, 'created_at': now}},
        upsert=True,
    )
    await log_change(db, account_id=account_id, entity='marketing_period_locks',
                     entity_id=f"{account_id}:{period}", action=f"period_{action}",
                     before={'locked': before.get('locked')},
                     after={'locked': action == 'close'},
                     reason=entry['reason'], user=user, period=period)
    return await lock_state(db, account_id, period)


def can_manage_period(user: dict) -> bool:
    role = (user or {}).get('role') or ''
    if role in PERIOD_MANAGER_ROLES:
        return True
    perms = (user or {}).get('_permissions') or []
    return ('*' in perms or 'marketing.period.close' in perms
            or 'marketing.period.reopen' in perms)


# ══════════════════════════════════════════════════════════════════════════════
# JEJAK PERUBAHAN (pendahuluan F6 — dipakai kunci periode sejak sekarang)
# ══════════════════════════════════════════════════════════════════════════════
async def log_change(db, *, account_id: Optional[str], entity: str, entity_id: str,
                     action: str, before: Any = None, after: Any = None,
                     reason: str = '', user: Optional[dict] = None,
                     period: Optional[str] = None) -> None:
    """Tulis satu baris `marketing_change_log`. **Tidak pernah** melempar galat.

    Kegagalan menulis jejak tidak boleh membatalkan aksi bisnisnya, tapi juga
    tidak boleh senyap — karena itu dicatat sebagai warning berstruktur.
    """
    try:
        await db[CHANGE_LOG].insert_one({
            'id': str(uuid.uuid4()),
            'account_id': account_id or '',
            'entity': entity, 'entity_id': entity_id, 'action': action,
            'period': period or '',
            'before': before, 'after': after,
            'reason': (reason or '')[:500],
            'actor_id': (user or {}).get('id', ''),
            'actor_name': (user or {}).get('name') or (user or {}).get('email') or '',
            'actor_role': (user or {}).get('role', ''),
            'at': _now(),
        })
    except Exception as exc:  # pragma: no cover — jejak, bukan jalur uang
        logger.warning('[marketing_cycle] gagal menulis marketing_change_log '
                       'entity=%s id=%s action=%s: %s', entity, entity_id, action, exc)


# ══════════════════════════════════════════════════════════════════════════════
# PERINGATAN (F5.4)
# ══════════════════════════════════════════════════════════════════════════════
def thresholds_from(settings: Optional[dict]) -> Dict[str, float]:
    s = settings or {}
    out = dict(DEFAULT_THRESHOLDS)
    for k in out:
        if s.get(k) is not None:
            out[k] = _num(s.get(k), out[k])
    return out


def evaluate_flags(summary: dict, thresholds: Optional[dict] = None) -> List[dict]:
    """Ubah angka siklus menjadi daftar peringatan yang bisa dibaca manusia.

    Dipakai layar **dan** lonceng notifikasi dari SATU fungsi — kalau tiap
    pemakai menilai sendiri, badge dashboard dan isi notifikasi bisa berbeda
    untuk toko yang sama pada hari yang sama.
    """
    th = thresholds_from(thresholds)
    flags: List[dict] = []
    tgt = (summary.get('target') or {})
    ach = (summary.get('achievement') or {})
    bud = (summary.get('budget') or {})
    mrg = (summary.get('margin') or {})
    prog = (summary.get('progress') or {})

    rev_target = _num(tgt.get('revenue'))
    if rev_target > 0 and prog.get('month_state') != 'future':
        gap = _num(ach.get('pace_pct')) - _num(ach.get('revenue_pct'))
        if gap > th['target_behind_red_pct']:
            flags.append({'code': 'target_behind', 'severity': 'red',
                          'title': 'Omzet jauh di bawah pace target',
                          'message': f"Bulan sudah berjalan {_r(ach.get('pace_pct'))}% "
                                     f"tetapi capaian omzet baru {_r(ach.get('revenue_pct'))}% "
                                     f"(selisih {_r(gap)} poin).",
                          'value': _r(gap), 'threshold': th['target_behind_red_pct']})
        elif gap > th['target_behind_pct']:
            flags.append({'code': 'target_behind', 'severity': 'yellow',
                          'title': 'Omzet di bawah pace target',
                          'message': f"Pace {_r(ach.get('pace_pct'))}% vs capaian "
                                     f"{_r(ach.get('revenue_pct'))}% "
                                     f"(selisih {_r(gap)} poin).",
                          'value': _r(gap), 'threshold': th['target_behind_pct']})
    elif rev_target <= 0:
        flags.append({'code': 'target_missing', 'severity': 'info',
                      'title': 'Target bulan ini belum diisi',
                      'message': 'Tanpa target, capaian & pace tidak bisa dinilai — '
                                 'isi lewat tombol Set Target.',
                      'value': 0, 'threshold': 0})

    plan = _num(bud.get('total_plan'))
    spend = _num(bud.get('total_spend'))
    if plan > 0:
        ratio = spend / plan
        if ratio >= th['budget_over_ratio']:
            flags.append({'code': 'budget_overrun', 'severity': 'red',
                          'title': 'Anggaran terlampaui',
                          'message': f"Terpakai {_r(ratio * 100)}% dari rencana "
                                     f"({_r(spend):,.0f} dari {_r(plan):,.0f}).".replace(',', '.'),
                          'value': _r(ratio * 100), 'threshold': th['budget_over_ratio'] * 100})
        elif ratio >= th['budget_warn_ratio']:
            flags.append({'code': 'budget_warning', 'severity': 'yellow',
                          'title': 'Anggaran mendekati batas',
                          'message': f"Terpakai {_r(ratio * 100)}% dari rencana.",
                          'value': _r(ratio * 100), 'threshold': th['budget_warn_ratio'] * 100})
    elif spend > 0:
        flags.append({'code': 'budget_missing', 'severity': 'yellow',
                      'title': 'Ada realisasi tanpa rencana anggaran',
                      'message': f"Terpakai {_r(spend):,.0f} tetapi rencana anggaran "
                                 "bulan ini belum diisi.".replace(',', '.'),
                      'value': _r(spend), 'threshold': 0})

    # Pemeriksaan PER KATEGORI dijalankan TANPA memandang ada/tidaknya rencana total.
    # Kalau ia bersarang di dalam `if plan > 0`, bulan yang rencana totalnya masih 0
    # (keadaan paling umum di awal pemakaian) tidak akan pernah memberi tahu kategori
    # mana yang sudah menelan uang.
    for c in (bud.get('categories') or []):
        cp, cs = _num(c.get('plan')), _num(c.get('spend'))
        if cp > 0 and cs / cp >= th['budget_over_ratio']:
            flags.append({'code': 'budget_overrun_category', 'severity': 'red',
                          'title': f"Kategori {c.get('category')} melewati rencana",
                          'message': f"{c.get('category')}: terpakai "
                                     f"{_r(cs / cp * 100)}% dari rencana.",
                          'value': _r(cs / cp * 100), 'category': c.get('category'),
                          'threshold': th['budget_over_ratio'] * 100})
        elif cp <= 0 and cs > 0:
            # Kelas cacat yang ditemukan uji F5: biaya TERBESAR bulan itu bisa berada
            # di kategori yang rencananya Rp 0 (mis. diskon Rp 48 jt tanpa satu rupiah
            # pun direncanakan). Rumus "terpakai/rencana" tidak pernah menyalakannya
            # karena pembaginya nol — jadi pengeluaran yang sama sekali TIDAK
            # direncanakan justru yang paling tidak terlihat.
            flags.append({'code': 'budget_unplanned_category', 'severity': 'red',
                          'title': f"Kategori {c.get('category')} dibelanjakan "
                                   "tanpa rencana",
                          'message': f"{c.get('category')}: terpakai "
                                     f"{_r(cs):,.0f} sementara rencananya Rp 0 — isi "
                                     "rencananya atau akui ini biaya di luar "
                                     "anggaran.".replace(',', '.'),
                          'value': _r(cs), 'category': c.get('category'),
                          'threshold': 0})

    if _num(mrg.get('units_total')) > 0 and _num(mrg.get('hpp_coverage_pct')) < 80:
        flags.append({'code': 'hpp_coverage_low', 'severity': 'yellow',
                      'title': 'Marjin belum bisa dipercaya',
                      'message': f"Hanya {_r(mrg.get('hpp_coverage_pct'))}% unit terjual "
                                 "punya HPP — tautkan item katalog ke master produk "
                                 "supaya marjin bermakna.",
                      'value': _r(mrg.get('hpp_coverage_pct')), 'threshold': 80})
    return flags


# ══════════════════════════════════════════════════════════════════════════════
# SATU PERMINTAAN = SEMUA ANGKA (F5.1)
# ══════════════════════════════════════════════════════════════════════════════
async def cycle_summary(db, account: dict, period: str, *,
                        today: Optional[datetime] = None,
                        settings: Optional[dict] = None) -> Dict[str, Any]:
    """Ringkas siklus SATU toko × SATU bulan — dipakai layar, export, & notifikasi."""
    account_id = account['id']
    y, m = valid_period(period)
    prog = month_progress(period, today)

    daily = await actual_from_daily(db, account_id, period)
    margin = await margin_from_orders(db, account_id, period)
    tgt_doc = await db[TARGETS].find_one(
        {'account_id': account_id, 'year': y, 'month': m}, {'_id': 0}) or {}
    bud_doc = await db[BUDGETS].find_one(
        {'account_id': account_id, 'period': period}, {'_id': 0}) or {}
    plan = {**empty_categories(), **(bud_doc.get('budget_by_category') or {})}
    plan = {k: _r(plan.get(k)) for k in CATEGORIES}
    man, man_docs = await manual_spend(db, account_id, period)
    auto, sources = await auto_spend(db, account_id, period, daily)

    spend = {c: _r(man.get(c, 0) + auto.get(c, 0)) for c in CATEGORIES}
    cats = []
    total_plan = total_spend = 0.0
    for c in CATEGORIES:
        p, s = plan[c], spend[c]
        cats.append({
            'category': c, 'plan': p, 'spend': s,
            'manual': _r(man.get(c, 0)), 'auto': _r(auto.get(c, 0)),
            'variance': _r(p - s),
            'used_pct': _r(s / p * 100) if p > 0 else (0.0 if s == 0 else 100.0),
            'status': 'over' if s > p else 'under',
            'mode': 'auto' if c in AUTO_CATEGORIES else 'manual',
        })
        total_plan += p
        total_spend += s
    total_plan, total_spend = _r(total_plan), _r(total_spend)

    revenue = _num(daily.get('revenue'))
    rev_target = _num(tgt_doc.get('revenue_target'))
    ord_target = _int(tgt_doc.get('orders_target'))
    orders = _int(daily.get('orders'))
    achievement = {
        'revenue_pct': _r(revenue / rev_target * 100) if rev_target > 0 else 0.0,
        'orders_pct': _r(orders / ord_target * 100) if ord_target > 0 else 0.0,
        'pace_pct': prog['pace_pct'],
        'days_elapsed': prog['days_elapsed'], 'days_total': prog['days_total'],
        'revenue_gap': _r(rev_target - revenue) if rev_target > 0 else 0.0,
        'prorata_target': _r(rev_target * prog['days_elapsed'] / prog['days_total'])
        if rev_target > 0 and prog['days_total'] else 0.0,
        'run_rate': _r(revenue / prog['days_elapsed'] * prog['days_total'])
        if prog['days_elapsed'] else 0.0,
    }
    achievement['status'] = (
        'no_target' if rev_target <= 0 else
        'on_track' if achievement['revenue_pct'] >= achievement['pace_pct'] - 5 else
        'warning' if achievement['revenue_pct'] >= achievement['pace_pct'] - 15 else 'behind')

    gross_profit = _num(margin.get('gross_profit'))
    # ROI berbasis MARJIN hanya bermakna kalau HPP-nya diketahui. Tanpa pagar ini,
    # toko yang HPP-nya belum tertaut menampilkan "ROI −100%" — dibaca sebagai
    # kerugian total, padahal yang sebenarnya terjadi adalah HPP belum diisi.
    roi_reliable = bool(margin.get('trustworthy')) and _num(margin.get('units_total')) > 0
    roi = {
        'spend': total_spend,
        'gross_profit': gross_profit,
        'roi_pct': _r((gross_profit - total_spend) / total_spend * 100) if total_spend > 0 else 0.0,
        'roas': _r(revenue / total_spend) if total_spend > 0 else 0.0,
        'spend_of_revenue_pct': _r(total_spend / revenue * 100) if revenue > 0 else 0.0,
        'reliable': roi_reliable,
        'reliability_note': ('' if roi_reliable else
                            'ROI (berbasis marjin) belum bisa dipercaya: HPP hanya '
                            f"diketahui untuk {_r(margin.get('hpp_coverage_pct'))}% unit "
                            'terjual. ROAS tetap sah karena tidak memakai HPP.'),
    }

    lock = await lock_state(db, account_id, period)
    basis = _shape.resolve_basis(account, None)
    # SESI #9 — OMZET SETELAH RETUR. `revenue` (bruto) di atas tidak berubah;
    # `returns` adalah angka BARU di sebelahnya, memakai basis omzet toko supaya
    # "order amount retur" tidak pernah dikurangkan dari "omzet produk".
    returns = _ret.resolve(basis, revenue, daily.get('returns_split') or {})
    out: Dict[str, Any] = {
        'account': {'id': account_id, 'account_name': account.get('account_name', ''),
                    'account_code': account.get('account_code', ''),
                    'platform': account.get('platform', ''),
                    'status': account.get('status', ''),
                    'health_score': account.get('health_score')},
        'period': period, 'year': y, 'month': m,
        'progress': prog,
        'locked': bool(lock.get('locked')), 'lock': lock,
        'revenue_basis': basis,
        'target': {'revenue': _r(rev_target), 'orders': ord_target,
                   'units': _int(tgt_doc.get('units_target')),
                   'aov': _r(rev_target / ord_target) if ord_target > 0 else 0.0,
                   'health_score': tgt_doc.get('health_score_target'),
                   'notes': tgt_doc.get('notes') or '',
                   'exists': bool(tgt_doc), 'basis': basis},
        'actual': {'revenue': revenue,
                   'revenue_product': _num(daily.get('revenue_product')),
                   'revenue_order_amount': _num(daily.get('revenue_order_amount')),
                   'gross_before_discount': _num(daily.get('gross_before_discount')),
                   'seller_discount': _num(daily.get('seller_discount')),
                   'platform_discount': _num(daily.get('platform_discount')),
                   'orders': orders, 'units': _int(daily.get('units')),
                   'buyers': _int(margin.get('buyers_unique')),
                   'buyers_daily_sum': _int(daily.get('buyers_daily_sum')),
                   'aov': _num(daily.get('aov')),
                   'days_with_data': _int(daily.get('days_with_data')),
                   # Tiga angka BARU (sesi #9) — sengaja bernama sendiri supaya
                   # tidak ada satu pun pembaca lama yang berubah arti.
                   'revenue_gross': returns['revenue_gross'],
                   'returned_amount': returns['returned_amount'],
                   'returned_orders': returns['returned_orders'],
                   'returned_units': returns['returned_units'],
                   'revenue_net_returns': returns['revenue_net_returns'],
                   'returns_pct': returns['returns_pct'],
                   'sources': daily.get('sources') or {}},
        'achievement': achievement,
        'budget': {'plan': plan, 'actual': spend,
                   'variance': {c: _r(plan[c] - spend[c]) for c in CATEGORIES},
                   'categories': cats,
                   'total_plan': total_plan, 'total_spend': total_spend,
                   'total_remaining': _r(total_plan - total_spend),
                   'total_used_pct': _r(total_spend / total_plan * 100) if total_plan > 0 else 0.0,
                   'exists': bool(bud_doc), 'manual_entries': man_docs},
        'spend_sources': sources,
        'margin': margin,
        'returns': returns,
        'roi': roi,
        'label': 'Angka omzet SEBELUM potongan platform (komisi & biaya platform '
                 'hanya diketahui dari laporan Pencairan/Settlement).',
    }
    out['flags'] = evaluate_flags(out, settings)
    # Peringatan retur dihitung kalkulator retur (satu tempat) lalu digabung —
    # layar & lonceng notifikasi tetap membaca satu daftar `flags`.
    out['flags'] += _ret.evaluate_flags(returns, settings)
    out['data_notes'] = _data_notes(out)
    return out


def _data_notes(s: dict) -> List[str]:
    """Catatan kejujuran data — apa yang TIDAK diketahui angka di layar ini."""
    notes = [s['label']]
    act = s.get('actual') or {}
    mrg = s.get('margin') or {}
    src = act.get('sources') or {}
    if not act.get('days_with_data'):
        notes.append('Belum ada rekap harian pada bulan ini — semua angka realisasi '
                     'nol karena BELUM ADA DATA, bukan karena tidak ada penjualan.')
    if 'manual_override' in src:
        notes.append(f"{src['manual_override']} hari memakai angka OVERRIDE SPV "
                     '(bukan turunan pesanan) — lihat jejaknya di Input Sales.')
    if 'import' in src or 'manual' in src:
        notes.append('Sebagian hari berasal dari rekap yang diimpor/diketik, bukan dari '
                     'pesanan per baris; rincian per pesanan tidak tersedia untuk hari itu.')
    if _num(mrg.get('units_total')) > 0:
        notes.append(f"Marjin dihitung dari {_int(mrg.get('units_covered'))} dari "
                     f"{_int(mrg.get('units_total'))} unit yang HPP-nya diketahui "
                     f"(cakupan {_r(mrg.get('hpp_coverage_pct'))}%).")
    else:
        # KENAPA KATA "HPP" WAJIB ADA DI SINI (gate CYC-5c):
        # catatan kejujuran harus menyebut HPP pada SETIAP keadaan, termasuk saat
        # datanya nol. Versi lama hanya berbunyi "marjin belum bisa dihitung" —
        # pembaca layar tidak pernah tahu SEBABNYA (HPP hanya diketahui dari
        # pesanan per baris yang tertaut katalog), jadi "marjin 0%" mudah dibaca
        # sebagai "jualan tanpa untung" padahal artinya "belum ada dasar hitung".
        notes.append('Marjin & HPP belum bisa dihitung: tidak ada pesanan per baris pada '
                     'bulan ini. HPP hanya diketahui dari pesanan yang tertaut item '
                     'katalog — rekap yang diketik/diimpor per hari tidak membawa HPP.')
    notes.append('Realisasi anggaran bertanda `auto` dihitung dari data sumber setiap kali '
                 'dibaca dan TIDAK ditulis sebagai entri belanja, supaya tidak dobel dengan '
                 'catatan manual.')
    # SESI #9 — retur SELALU disebut, termasuk saat nilainya nol: "tidak ada retur"
    # dan "retur belum diketahui" adalah dua keadaan berbeda dan keduanya harus
    # bisa dibaca dari layar.
    rt = s.get('returns') or {}
    if _int(rt.get('returned_orders')) > 0 or not ((rt.get('coverage') or {}).get('complete', True)):
        notes.append(_ret.data_note(rt))
    else:
        notes.append('Tidak ada pesanan RETUR pada bulan ini, jadi omzet setelah retur '
                     'sama dengan omzet bruto.')
    return notes


async def cycle_overview(db, period: str, *, account_ids: Optional[Sequence[str]] = None,
                         today: Optional[datetime] = None,
                         settings: Optional[dict] = None) -> Dict[str, Any]:
    """Semua toko × satu bulan — baris tabel siklus + total gabungan.

    Peringkat & total dihitung DI SINI (bukan di browser) supaya layar Marketing,
    layar Manajemen, dan lampiran export tidak bisa mengurutkan berbeda.
    """
    q: Dict[str, Any] = {}
    if account_ids is not None:
        q['id'] = {'$in': list(account_ids)}
    accounts = await db[ACCOUNTS].find(q, {'_id': 0}).sort('account_name', 1).to_list(300)
    rows: List[dict] = []
    for acc in accounts:
        rows.append(await cycle_summary(db, acc, period, today=today, settings=settings))
    prog = month_progress(period, today)

    def s(path: Sequence[str]) -> float:
        tot = 0.0
        for r in rows:
            cur: Any = r
            for p in path:
                cur = (cur or {}).get(p) if isinstance(cur, dict) else 0
            tot += _num(cur)
        return _r(tot)

    rev_target = s(('target', 'revenue'))
    revenue = s(('actual', 'revenue'))
    returned_amount = s(('actual', 'returned_amount'))
    net_revenue = s(('actual', 'revenue_net_returns'))
    total_plan = s(('budget', 'total_plan'))
    total_spend = s(('budget', 'total_spend'))
    gross_profit = s(('margin', 'gross_profit'))
    units_total = int(s(('margin', 'units_total')))
    units_cov = int(s(('margin', 'units_covered')))
    totals = {
        'accounts': len(rows),
        'accounts_with_target': sum(1 for r in rows if _num((r.get('target') or {}).get('revenue')) > 0),
        'accounts_locked': sum(1 for r in rows if r.get('locked')),
        'target_revenue': rev_target,
        'revenue': revenue,
        'revenue_product': s(('actual', 'revenue_product')),
        'revenue_order_amount': s(('actual', 'revenue_order_amount')),
        'orders': int(s(('actual', 'orders'))),
        'units': int(s(('actual', 'units'))),
        # SESI #9 — retur gabungan. `revenue` tetap BRUTO (dipakai target/pace/ROAS).
        'returned_amount': returned_amount,
        'returned_orders': int(s(('actual', 'returned_orders'))),
        'returned_units': int(s(('actual', 'returned_units'))),
        'revenue_net_returns': net_revenue,
        'returns_pct': _r(returned_amount / revenue * 100) if revenue > 0 else 0.0,
        'returns_coverage_complete': all(
            ((r.get('returns') or {}).get('coverage') or {}).get('complete', True) for r in rows),
        'revenue_pct': _r(revenue / rev_target * 100) if rev_target > 0 else 0.0,
        'pace_pct': prog['pace_pct'],
        'total_plan': total_plan, 'total_spend': total_spend,
        'total_remaining': _r(total_plan - total_spend),
        'total_used_pct': _r(total_spend / total_plan * 100) if total_plan > 0 else 0.0,
        'gross_profit': gross_profit,
        'roas': _r(revenue / total_spend) if total_spend > 0 else 0.0,
        'roi_pct': _r((gross_profit - total_spend) / total_spend * 100) if total_spend > 0 else 0.0,
        'hpp_coverage_pct': _r(units_cov / units_total * 100) if units_total else 0.0,
        # ROI gabungan hanya sah kalau HPP mayoritas unit diketahui (lihat catatan
        # `roi.reliable` di cycle_summary). Total yang tampak "−100%" karena HPP
        # belum tertaut pernah dibaca sebagai kerugian nyata.
        'roi_reliable': bool(units_total and units_cov / units_total >= 0.8),
        'flags_red': sum(1 for r in rows for f in (r.get('flags') or []) if f.get('severity') == 'red'),
        'flags_yellow': sum(1 for r in rows for f in (r.get('flags') or []) if f.get('severity') == 'yellow'),
    }
    attention = sorted(
        [{'account_id': r['account']['id'], 'account_name': r['account']['account_name'],
          'account_code': r['account']['account_code'],
          'flags': [f for f in (r.get('flags') or []) if f.get('severity') in ('red', 'yellow')]}
         for r in rows if any(f.get('severity') in ('red', 'yellow') for f in (r.get('flags') or []))],
        key=lambda x: (-sum(1 for f in x['flags'] if f['severity'] == 'red'), x['account_name']))
    return {'period': period, 'progress': prog, 'rows': rows, 'totals': totals,
            'attention': attention, 'categories': list(CATEGORIES),
            'label': rows[0]['label'] if rows else
            'Angka omzet SEBELUM potongan platform.'}
