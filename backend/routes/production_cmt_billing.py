"""Tagihan CMT (AP jasa jahit) — endpoint BACA untuk pintu "Invoice".

Kenapa file ini ada (audit IA 2026-07-26, docs/PROPOSAL_IA_PRODUKSI.md §2):
    Alur uang produksi (internal maupun maklon) yang keluar ke vendor CMT SUDAH jalan
    di backend:
        Terima FG dari CMT (approve `cmt_receipts`)
          → production_maklon_bridge.mature_ap_from_cmt_receipt()
          → dokumen `dewi_cmt_payments` status draft
          → POST /api/dewi/maklon/finance/cmt-payments/{id}/post-ap
          → jurnal `cmt_ap_invoice` (Dr Biaya Jasa CMT / Cr Hutang Vendor)
    TAPI tidak ada satu pun layar yang menampilkan daftar `dewi_cmt_payments`
    (dibuktikan: nol pemanggil di frontend). Jadi tagihan yang sudah matang tidak
    pernah terlihat oleh pengguna.

File ini HANYA membaca + mengelompokkan. **Posting ke GL tetap memakai endpoint yang
sudah ada** (`/api/dewi/maklon/finance/cmt-payments/{id}/post-ap`) — sengaja tidak
dibuat handler kedua supaya logika jurnal tidak terduplikasi.

Pemisahan data (permintaan owner): Portal Produksi hanya melihat tagihan domain
INTERNAL, Portal Maklon hanya domain MAKLON.
    - punya `po_id`  → domain diambil dari `production_pos.business_type`
    - punya `job_ids`→ CMT-flow (DA menjahitkan produk DA sendiri) ⇒ INTERNAL
    - keduanya kosong→ 'unknown' (hanya muncul saat scope=all)
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from routes.production_rbac import deny_external_dep

from database import get_db
from auth import require_auth, serialize_doc
from core import cmt_vendor_master
from routes.production_rbac import deny_klien
from core.pagination import _paginate_params, _paginated_envelope

router = APIRouter(prefix="/api/production/cmt-billing", tags=["production-cmt-billing"], dependencies=[Depends(deny_external_dep)])
# status yang dianggap masih menjadi kewajiban (outstanding)
_OPEN_STATUS = ('draft', 'submitted', 'approved', 'pending', 'posted', 'partial_paid')


def _amount(p: dict) -> float:
    """Nilai tagihan bersih. Dokumen dari 2 penulis memakai nama field berbeda:
    bridge menulis `net_amount`, seeder CMT-flow menulis `total_amount`."""
    for k in ('net_amount', 'total_amount', 'subtotal'):
        v = p.get(k)
        if v not in (None, ''):
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


async def _domain_map(db, payments: list) -> dict:
    """payment_id -> 'internal' | 'maklon' | 'unknown'."""
    po_ids = list({p.get('po_id') for p in payments if p.get('po_id')})
    bt_by_po = {}
    if po_ids:
        pos = await db.production_pos.find(
            {'id': {'$in': po_ids}}, {'_id': 0, 'id': 1, 'business_type': 1}
        ).to_list(None)
        bt_by_po = {p['id']: ('internal' if p.get('business_type') == 'internal' else 'maklon')
                    for p in pos}
    out = {}
    for p in payments:
        if p.get('po_id'):
            out[p['id']] = bt_by_po.get(p['po_id'], 'unknown')
        elif p.get('job_ids'):
            # CMT-flow: DA menjahitkan produk DA sendiri lewat mitra CMT ⇒ internal
            out[p['id']] = 'internal'
        else:
            out[p['id']] = 'unknown'
    return out


def _enrich(p: dict, domain: str, entry: dict | None = None) -> dict:
    return {
        **serialize_doc(p),
        'business_type': domain,
        'amount': _amount(p),
        'penalty': float(p.get('total_penalty', 0) or 0),
        'gl_posted': bool(p.get('gl_je_id')),
        'paid_amount': float(p.get('paid_amount') or 0),
        'outstanding_amount': float(p.get('outstanding_amount') if p.get('outstanding_amount') is not None
                                    else _amount(p) - float(p.get('paid_amount') or 0)),
        # keputusan owner 3a — badge "diinput staf DA" pada tagihan CMT.
        **(entry or {'progress_entry_source': 'none', 'staff_entered_progress_qty': 0,
                     'staff_entered_by': [], 'declaration_entered_by_staff': False,
                     'declaration_entered_by': ''}),
    }


async def _staff_entry_map(db, payments: list) -> dict:
    """payment_id → ringkasan "siapa yang mengetik angka di balik tagihan ini".

    Kenapa ini ada: tagihan CMT dihitung dari progress produksi. Kalau vendornya
    tidak memakai sistem, angka itu DIKETIK STAF DA lewat Portal CMT Override.
    Owner memutuskan (3a) fakta itu harus KELIHATAN di layar invoice — supaya
    kalau nanti ada selisih tagihan, jelas angkanya datang dari vendor atau dari
    staf. Semua diambil batch (3 query) agar layar tetap ringan.
    """
    if not payments:
        return {}
    receipt_ids = [p['source_receipt_id'] for p in payments if p.get('source_receipt_id')]
    # F13 — id vendor DIRESOLUSI lewat SSOT `core.cmt_vendor_master`, bukan
    # `vendor_id or cmt_partner_id` mentah. Dulu: kalau dokumen hanya menyimpan id
    # master Portal CMT, pencarian `production_jobs.vendor_id` di bawah tidak
    # menemukan job apa pun ⇒ kolom "diinput staf DA" jadi `none` dan keputusan
    # owner 3a (harus KELIHATAN siapa yang mengetik angka tagihan) gagal diam-diam.
    canon = await cmt_vendor_master.canonical_map(db, payments)
    vendor_ids = [v for v in set(canon.values()) if v]

    # 1. deklarasi kirim CMT→DA di balik penerimaan
    decl_by_receipt: dict = {}
    if receipt_ids:
        receipts = await db.cmt_receipts.find(
            {'id': {'$in': receipt_ids}},
            {'_id': 0, 'id': 1, 'related_shipment_id': 1}).to_list(None)
        ship_ids = [r['related_shipment_id'] for r in receipts if r.get('related_shipment_id')]
        ships = await db.buyer_shipments.find(
            {'id': {'$in': ship_ids}},
            {'_id': 0, 'id': 1, 'entered_by_staff': 1, 'entered_by': 1}).to_list(None) if ship_ids else []
        ship_map = {s['id']: s for s in ships}
        for r in receipts:
            s = ship_map.get(r.get('related_shipment_id')) or {}
            decl_by_receipt[r['id']] = (s.get('entered_by_staff') is True, s.get('entered_by', ''))

    # 2. progress per job milik vendor-vendor yang ditagih
    jobs = await db.production_jobs.find(
        {'vendor_id': {'$in': vendor_ids}},
        {'_id': 0, 'id': 1, 'vendor_id': 1, 'po_id': 1}).to_list(None) if vendor_ids else []
    job_ids = [j['id'] for j in jobs]
    agg = await db.production_progress.aggregate([
        {'$match': {'job_id': {'$in': job_ids}}},
        {'$group': {'_id': {'job': '$job_id',
                            'staff': {'$eq': [{'$ifNull': ['$entered_by_staff', False]}, True]}},
                    'n': {'$sum': 1}, 'qty': {'$sum': {'$ifNull': ['$completed_quantity', 0]}},
                    'who': {'$addToSet': '$entered_by'}}},
    ]).to_list(None) if job_ids else []
    per_job: dict = {}
    for row in agg:
        b = per_job.setdefault(row['_id']['job'], {'s_n': 0, 's_qty': 0, 'v_n': 0, 'who': set()})
        if row['_id']['staff']:
            b['s_n'] += row['n']; b['s_qty'] += row['qty'] or 0
            b['who'].update(w for w in (row.get('who') or []) if w)
        else:
            b['v_n'] += row['n']

    out = {}
    for p in payments:
        vid = canon.get(p['id']) or ''
        pid = p.get('po_id') or ''
        mine = [j['id'] for j in jobs
                if j.get('vendor_id') == vid and (not pid or j.get('po_id') == pid)]
        s_n = s_qty = v_n = 0
        who: set = set()
        for jid in mine:
            b = per_job.get(jid)
            if not b:
                continue
            s_n += b['s_n']; s_qty += b['s_qty']; v_n += b['v_n']; who |= b['who']
        src = 'mixed' if (s_n and v_n) else 'staff' if s_n else 'vendor' if v_n else 'none'
        d_staff, d_by = decl_by_receipt.get(p.get('source_receipt_id'), (False, ''))
        out[p['id']] = {
            'progress_entry_source': src,
            'staff_entered_progress_qty': s_qty,
            'staff_entered_by': sorted(who),
            'declaration_entered_by_staff': d_staff,
            'declaration_entered_by': d_by,
        }
    return out


async def _load(db, request: Request):
    """Ambil + filter + kelompokkan tagihan sesuai query param."""
    sp = request.query_params
    scope = (sp.get('business_type') or 'all').lower()
    if scope not in ('internal', 'maklon', 'all'):
        scope = 'all'

    # Kedua filter di bawah memakai `$or`, jadi keduanya dikumpulkan ke `$and`.
    # Kalau ditulis langsung ke `q['$or']`, filter yang belakangan MENIMPA yang
    # sebelumnya — mencari nama vendor sambil memfilter per vendor akan diam-diam
    # kehilangan salah satu syaratnya (dan hasilnya tampak "kok tagihannya beda").
    q: dict = {}
    conds: list = []
    if sp.get('status'):
        q['status'] = sp['status']
    if sp.get('partner_id'):
        # F13 — filter per vendor lewat SSOT. Pemilih vendor di layar mengirim id
        # `vendor_partners`; filter lama (`cmt_partner_id == partner_id`) MEMBUANG
        # baris yang tersimpan dengan id master Portal CMT — dan yang terbuang itu
        # hutang jasa jahit yang benar-benar ada.
        conds.append(await cmt_vendor_master.payment_filter(db, sp['partner_id']))
    search = (sp.get('search') or '').strip()
    if search:
        conds.append({'$or': [
            {'payment_code': {'$regex': search, '$options': 'i'}},
            {'cmt_name': {'$regex': search, '$options': 'i'}},
            {'po_number': {'$regex': search, '$options': 'i'}},
            {'source_receipt_code': {'$regex': search, '$options': 'i'}},
        ]})
    if conds:
        q['$and'] = conds

    payments = await db.dewi_cmt_payments.find(q, {'_id': 0}).sort('created_at', -1).to_list(5000)
    domains = await _domain_map(db, payments)
    entries = await _staff_entry_map(db, payments)
    rows = [_enrich(p, domains.get(p['id'], 'unknown'), entries.get(p['id'])) for p in payments]
    if scope != 'all':
        rows = [r for r in rows if r['business_type'] == scope]
    return scope, rows


@router.get("")
async def list_cmt_billing(request: Request):
    """Daftar tagihan CMT (paginasi standar repo)."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    scope, rows = await _load(db, request)
    page, per_page, skip, wants = _paginate_params(request.query_params)
    if wants:
        return _paginated_envelope(rows[skip:skip + per_page], len(rows), page, per_page)
    return {'items': rows, 'total': len(rows), 'scope': scope}


@router.get("/summary")
async def cmt_billing_summary(request: Request):
    """KPI untuk header pintu Invoice."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    scope, rows = await _load(db, request)

    def _sum(pred):
        return round(sum(r['amount'] for r in rows if pred(r)), 2)

    st = lambda r: (r.get('status') or '').lower()  # noqa: E731
    return {
        'scope': scope,
        'total_bills': len(rows),
        'draft': len([r for r in rows if st(r) == 'draft']),
        'approved': len([r for r in rows if st(r) == 'approved']),
        'paid': len([r for r in rows if st(r) == 'paid']),
        'not_posted': len([r for r in rows if not r['gl_posted'] and st(r) != 'cancelled']),
        'variance_flagged': len([r for r in rows if r.get('variance_flagged')]),
        'total_amount': _sum(lambda r: st(r) != 'cancelled'),
        'outstanding_amount': round(sum(r['outstanding_amount'] for r in rows if st(r) in _OPEN_STATUS), 2),
        'paid_amount': round(sum(r['paid_amount'] for r in rows if st(r) != 'cancelled'), 2),
        'total_pcs': sum(int(r.get('total_pcs', 0) or 0) for r in rows if st(r) != 'cancelled'),
    }


@router.get("/vendors")
async def cmt_billing_vendors(request: Request):
    """Vendor CMT yang PUNYA tagihan — bahan dropdown filter di layar Invoice.

    **Kenapa endpoint sendiri, bukan dikumpulkan di browser dari baris tabel:**
    daftar baris menyusut begitu filter dipasang, jadi dropdown yang dibangun dari
    baris akan ikut menyusut dan pengguna tidak bisa berpindah vendor tanpa
    mereset filternya lebih dulu.

    **Kenapa dikelompokkan per id, bukan per `cmt_name`:** mengelompokkan tagihan
    berdasarkan NAMA adalah bentuk lain dari cacat yang diperbaiki F13 — dua ejaan
    ("CV Jahit Mitra" vs "CV. Jahit Mitra CMT") akan tampil sebagai dua vendor dan
    membelah hutang satu vendor jadi dua baris. Id dikanonkan lewat SSOT
    `core.cmt_vendor_master`, dan namanya diambil dari master `vendor_partners`
    (bukan dari dokumen tagihan) supaya satu vendor selalu satu nama.

    NB urutan deklarasi: rute ini WAJIB berada sebelum ``/{payment_id}``, kalau
    tidak FastAPI akan membaca "vendors" sebagai sebuah id tagihan.
    """
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()

    sp = request.query_params
    scope = (sp.get('business_type') or 'all').lower()
    if scope not in ('internal', 'maklon', 'all'):
        scope = 'all'

    # SENGAJA tanpa filter `partner_id`: daftar pilihan harus tetap lengkap.
    q = {}
    if sp.get('status'):
        q['status'] = sp['status']
    payments = await db.dewi_cmt_payments.find(q, {'_id': 0}).to_list(5000)
    if scope != 'all':
        domains = await _domain_map(db, payments)
        payments = [p for p in payments if domains.get(p['id'], 'unknown') == scope]
    if not payments:
        return {'vendors': [], 'total': 0, 'scope': scope}

    canon = await cmt_vendor_master.canonical_map(db, payments)
    ids = [v for v in set(canon.values()) if v]
    master = {m['id']: m for m in await db.vendor_partners.find(
        {'id': {'$in': ids}}, {'_id': 0, 'id': 1, 'name': 1, 'code': 1}).to_list(None)} \
        if ids else {}

    agg: dict = {}
    for p in payments:
        vid = canon.get(p['id']) or ''
        st = (p.get('status') or '').lower()
        m = master.get(vid) or {}
        key = vid or f"__unmapped__{p.get('cmt_name') or '?'}"
        b = agg.setdefault(key, {
            'vendor_id': vid,
            # Nama dari MASTER; `cmt_name` dokumen hanya cadangan supaya tagihan
            # yang belum terpetakan tetap bisa dilihat (dan kelihatan belum rapi).
            'vendor_name': m.get('name') or p.get('cmt_name') or '(tanpa nama)',
            'vendor_code': m.get('code') or '',
            'mapped': bool(vid),
            'bills': 0, 'amount': 0.0, 'outstanding': 0.0,
        })
        b['bills'] += 1
        if st != 'cancelled':
            b['amount'] += _amount(p)
        if st in _OPEN_STATUS:
            b['outstanding'] += _amount(p)

    vendors = sorted(agg.values(),
                     key=lambda v: (-v['outstanding'], -v['amount'],
                                    str(v['vendor_name']).lower()))
    for v in vendors:
        v['amount'] = round(v['amount'], 2)
        v['outstanding'] = round(v['outstanding'], 2)
    return {'vendors': vendors, 'total': len(vendors), 'scope': scope}


@router.get("/{payment_id}")
async def get_cmt_billing(payment_id: str, request: Request):
    """Detail 1 tagihan + rincian per baris + info jurnal GL."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    p = await db.dewi_cmt_payments.find_one({'id': payment_id}, {'_id': 0})
    if not p:
        raise HTTPException(404, 'Tagihan CMT tidak ditemukan')
    domains = await _domain_map(db, [p])
    entries = await _staff_entry_map(db, [p])
    row = _enrich(p, domains.get(payment_id, 'unknown'), entries.get(payment_id))

    je = None
    if p.get('gl_je_id'):
        je = await db.rahaza_journal_entries.find_one({'id': p['gl_je_id']}, {'_id': 0})
        if je:
            lines = await db.rahaza_journal_lines.find(
                {'je_id': p['gl_je_id']}, {'_id': 0}).to_list(50)
            je = {**serialize_doc(je), 'lines': serialize_doc(lines)}

    receipt = None
    if p.get('source_receipt_id'):
        receipt = await db.cmt_receipts.find_one({'id': p['source_receipt_id']}, {'_id': 0})

    return {'bill': row, 'journal': je, 'receipt': serialize_doc(receipt) if receipt else None}
