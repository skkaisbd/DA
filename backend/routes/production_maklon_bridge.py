"""Maklon Finance Bridge (Fase 2 — FIN-2 locked: invoices/payments SOMMERVILLE
TIDAK diadopsi; finance tetap `dewi_maklon_finance`).

Adapter: production_pos (business_type='maklon') → mirror `dewi_maklon_pos`
(id SAMA dengan po_id) + Draft AR Invoice di `rahaza_ar_invoices`, sehingga
seluruh modul finance maklon existing (post-ar, advance-payment, billing,
PO-360) tetap bekerja tanpa perubahan.

Yang TIDAK dilakukan adapter ini: membuat rahaza_work_orders (engine lama —
digantikan production_jobs, lihat PRODUKSI_E10_ADAPTER_MIGRASI.md).
"""
import logging
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, check_role, log_activity, serialize_doc
from core.helpers import new_id, now
from core import cmt_vendor_master
from routes.production_rbac import PROD_ADMIN_ROLES, deny_klien

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["maklon-finance-bridge"])

# production_pos status → dewi_maklon_pos status
PO_STATUS_TO_MAKLON = {
    'Draft': 'draft',
    'Confirmed': 'confirmed',
    'Distributed': 'confirmed',
    'In Production': 'in_production',
    'Production Complete': 'in_production',
    'Variance Review': 'in_production',
    'Return Review': 'in_production',
    'Ready to Close': 'completed',
    'Completed': 'completed',
    'Closed': 'completed',
    'Closed Short': 'completed',
    'Cancelled': 'cancelled',
}


def _iso_date(v):
    """dewi_maklon_pos menyimpan tanggal sebagai string ISO (yyyy-mm-dd) —
    konversi datetime production_pos agar modul finance existing tetap bekerja."""
    if v is None:
        return None
    if isinstance(v, str):
        return v[:10]
    try:
        return v.date().isoformat()
    except AttributeError:
        return str(v)[:10]


async def sync_po_to_maklon_finance(db, po_id: str, user: dict) -> dict:
    """Upsert mirror dewi_maklon_pos dari production_pos maklon + buat Draft AR
    Invoice sekali (idempoten) begitu PO sudah bukan Draft."""
    po = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
    if not po:
        return {'ok': False, 'error': 'PO tidak ditemukan'}
    if po.get('business_type') != 'maklon':
        return {'ok': False, 'skipped': True, 'error': 'PO bukan business_type=maklon'}

    po_items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).sort('created_at', 1).to_list(None)
    item_ids = [i['id'] for i in po_items]

    # Aggregate produced (production_job_items — child jobs ikut karena juga ber-po_item_id)
    prod_agg = await db.production_job_items.aggregate([
        {'$match': {'po_item_id': {'$in': item_ids}}},
        {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$produced_qty'}}},
    ]).to_list(None) if item_ids else []
    produced_by_item = {a['_id']: a['qty'] for a in prod_agg}
    # Aggregate dispatched ke klien — HANYA surat jalan ke BUYER (deklarasi CMT→DA
    # `receiver_type='da'` juga tersimpan di buyer_shipment_items; audit M-08).
    buyer_ship_ids = await _buyer_shipment_ids_for_po(db, po_id)
    disp_agg = await db.buyer_shipment_items.aggregate([
        {'$match': {'po_item_id': {'$in': item_ids}, 'shipment_id': {'$in': buyer_ship_ids}}},
        {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$qty_shipped'}}},
    ]).to_list(None) if (item_ids and buyer_ship_ids) else []
    dispatched_by_item = {a['_id']: a['qty'] for a in disp_agg}

    existing = await db.dewi_maklon_pos.find_one({'id': po_id}, {'_id': 0})
    ar_doc = None
    if (existing or {}).get('ar_invoice_id'):
        ar_doc = await db.rahaza_ar_invoices.find_one(
            {'id': existing['ar_invoice_id'], 'source_module': 'maklon_po'}, {'_id': 0, 'status': 1})
    if not ar_doc:
        # invoice legacy (dewi_maklon_invoices tanpa tautan AR) juga berarti "sudah ditagih"
        legacy_inv = await db.dewi_maklon_invoices.find_one(
            {'order_id': po_id, 'status': {'$ne': 'cancelled'}}, {'_id': 0, 'status': 1})
        if legacy_inv:
            ar_doc = {'status': 'issued'}

    items = []
    total_qty = 0
    total_value = 0.0
    total_cmt_cost = 0.0
    for idx, pi in enumerate(po_items, start=1):
        qty = int(pi.get('qty', 0) or 0)
        # Dua harga BERBEDA (keputusan pemilik 2026-09-03): `cmt_price_snapshot` = upah jahit
        # vendor CMT (BIAYA, dasar AP), `selling_price_snapshot` = harga jasa ke klien
        # (PENDAPATAN, dasar AR). Dulu AR memakai cmt_price ⇒ margin maklon selalu 0 (audit M-06).
        cmt_rate = float(pi.get('cmt_price_snapshot', 0) or 0)
        sell = float(pi.get('selling_price_snapshot', 0) or 0)
        rate = sell if sell > 0 else cmt_rate
        subtotal = round(rate * qty, 2)
        cmt_cost = round(cmt_rate * qty, 2)
        total_qty += qty
        total_value += subtotal
        total_cmt_cost += cmt_cost
        items.append({
            'item_id': pi['id'],
            'idx': idx,
            'seri_no': pi.get('serial_number') or f'S{idx:02d}',
            'artikel': pi.get('product_name', ''),
            'sku_code': pi.get('sku', ''),
            'color': pi.get('color', ''),
            'size': pi.get('size', ''),
            'qty': qty,
            'qty_produced': int(produced_by_item.get(pi['id'], 0) or 0),
            'qty_dispatched': int(dispatched_by_item.get(pi['id'], 0) or 0),
            'cmt_rate_per_pcs': cmt_rate,
            'selling_price_per_pcs': rate,
            'price_basis': 'selling' if sell > 0 else 'cmt_fallback',
            'subtotal': subtotal,
            'cmt_cost': cmt_cost,
            'product_description': pi.get('product_name', ''),
            'notes': '',
            'wo_id': None, 'wo_number': None,
            # FASE 3 (cacat MK-2): FK master ikut dibawa ke mirror supaya Portal
            # Maklon & portal klien bisa menampilkan varian yang benar dan
            # identitas varian tidak hilang saat dokumen dibaca dari mirror.
            'buyer_catalog_id': pi.get('catalog_item_id'),
            'maklon_variant_id': pi.get('maklon_variant_id'),
            'buyer_ref_code': pi.get('buyer_ref_code', ''),
            'status': 'in_production' if produced_by_item.get(pi['id']) else 'pending',
        })
    total_value = round(total_value, 2)
    total_cmt_cost = round(total_cmt_cost, 2)

    mirror_status = PO_STATUS_TO_MAKLON.get(po.get('status', 'Draft'), 'draft')
    total_dispatched = sum(i['qty_dispatched'] for i in items)
    if mirror_status == 'in_production' and total_dispatched > 0:
        mirror_status = 'partial_delivered'
    # Invoice yang sudah TERBIT (bukan draft) menang atas status produksi — layar finance
    # harus tetap melihat "Ditagih" walau PO baru saja ditutup (audit M-03/M-10).
    if ar_doc and (ar_doc.get('status') or 'draft') not in ('draft', 'cancelled') \
            and mirror_status != 'cancelled':
        mirror_status = 'invoiced'

    if not existing:
        # Mirror basi dgn po_number sama (PO lama sudah dihapus) → bersihkan agar
        # unique index po_number tidak menolak insert.
        stale = await db.dewi_maklon_pos.find_one(
            {'mirror_of': 'production_pos', 'po_number': po.get('po_number', ''), 'id': {'$ne': po_id}})
        if stale and not await db.production_pos.find_one({'id': stale['id']}):
            await db.rahaza_ar_invoices.delete_many({
                'linked_maklon_po_id': stale['id'], 'source_module': 'maklon_po', 'status': 'draft'})
            await db.dewi_maklon_pos.delete_one({'id': stale['id']})
    mirror_fields = {
        'po_number': po.get('po_number', ''),
        'client_id': po.get('buyer_id'),
        'client_name': po.get('customer_name', ''),
        'client_code': (existing or {}).get('client_code', 'CLT'),
        'po_date': _iso_date(po.get('po_date')),
        'deadline': _iso_date(po.get('deadline')),
        'payment_terms': (existing or {}).get('payment_terms', 'net_30'),
        'status': mirror_status,
        'items': items,
        'total_qty': total_qty,
        'total_value': total_value,
        'total_cmt_cost': total_cmt_cost,
        'gross_margin': round(total_value - total_cmt_cost, 2),
        'qty_dispatched': total_dispatched,
        'qty_produced': sum(i['qty_produced'] for i in items),
        'notes': po.get('notes', ''),
        'mirror_of': 'production_pos',
        'production_po_id': po_id,
        'production_po_status': po.get('status'),
        'business_type': 'maklon',
        'updated_at': now(),
    }
    if existing:
        await db.dewi_maklon_pos.update_one({'id': po_id}, {'$set': mirror_fields})
    else:
        await db.dewi_maklon_pos.insert_one({
            'id': po_id,
            **mirror_fields,
            'ar_invoice_id': None, 'ar_invoice_number': None,
            'payment_status': 'unpaid', 'advance_payment': 0.0, 'amount_paid': 0.0,
            'gl_posted_at': None, 'gl_je_id': None, 'post_error': None,
            'created_at': now(),
            'created_by': user.get('id', ''), 'created_by_name': user.get('name', ''),
        })

    # Draft AR Invoice — sekali saja, begitu PO confirmed (mirror != draft)
    ar_invoice_id = (existing or {}).get('ar_invoice_id')
    ar_invoice_number = (existing or {}).get('ar_invoice_number')
    ar_created = False
    if mirror_status != 'draft' and not ar_invoice_id:
        from datetime import date
        from routes.dewi_maklon_pos import _next_ar_invoice_number
        ar_invoice_number = await _next_ar_invoice_number(db)
        ar_invoice_id = new_id()
        lines = [{
            'line_id': new_id(),
            'description': f"Jasa Maklon — {it['artikel']} {it['color']} {it['size']} (Seri {it['seri_no']})".strip(),
            'qty': it['qty'],
            'unit_price': it['selling_price_per_pcs'],
            'subtotal': it['subtotal'],
            'item_id': it['item_id'],
        } for it in items]
        await db.rahaza_ar_invoices.insert_one({
            'id': ar_invoice_id,
            'invoice_number': ar_invoice_number,
            'source_module': 'maklon_po',
            'linked_maklon_po_id': po_id,
            'linked_maklon_po_number': po.get('po_number', ''),
            'customer_id': po.get('buyer_id'),
            'customer_name': po.get('customer_name', ''),
            'invoice_date': date.today().isoformat(),
            'due_date': None,
            'lines': lines,
            'subtotal': total_value,
            'tax_pct': 0.0, 'tax_amount': 0.0, 'discount_amount': 0.0,
            'total_amount': total_value,
            'amount_paid': 0.0, 'amount_due': total_value,
            'status': 'draft',
            'payment_terms': mirror_fields['payment_terms'],
            'notes': f"Auto-generated dari PO Produksi Maklon {po.get('po_number', '')}",
            'gl_posted_at': None, 'gl_je_id': None, 'post_error': None,
            'created_at': now(), 'updated_at': now(),
            'created_by': user.get('id', ''),
        })
        await db.dewi_maklon_pos.update_one({'id': po_id}, {'$set': {
            'ar_invoice_id': ar_invoice_id, 'ar_invoice_number': ar_invoice_number, 'updated_at': now(),
        }})
        ar_created = True

    return {
        'ok': True, 'po_id': po_id, 'po_number': po.get('po_number', ''),
        'mirror_status': mirror_status, 'total_value': total_value,
        'ar_invoice_id': ar_invoice_id, 'ar_invoice_number': ar_invoice_number,
        'ar_created': ar_created,
    }


async def try_sync_maklon_finance(db, po_id: str, user: dict):
    """Hook aman untuk dipanggil dari alur PO — tidak pernah mematahkan alur utama."""
    try:
        return await sync_po_to_maklon_finance(db, po_id, user)
    except Exception:
        logger.exception('Maklon finance sync failed for PO %s', po_id)
        return {'ok': False, 'error': 'sync failed (lihat log)'}


@router.post("/production-pos/{po_id}/sync-maklon-finance")
async def sync_maklon_finance_endpoint(po_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    result = await sync_po_to_maklon_finance(db, po_id, user)
    if not result.get('ok') and not result.get('skipped'):
        raise HTTPException(400, result.get('error', 'Sync gagal'))
    if result.get('skipped'):
        raise HTTPException(400, result.get('error'))
    await log_activity(user['id'], user['name'], 'Sync Finance', 'Maklon Bridge',
                       f"Sync maklon finance PO {result.get('po_number')} (AR: {result.get('ar_invoice_number')})")
    return result


@router.get("/production-pos/{po_id}/maklon-finance")
async def get_maklon_finance_state(po_id: str, request: Request):
    """Bukti keterhubungan finance: mirror dewi_maklon_pos + AR invoice detail."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    mirror = await db.dewi_maklon_pos.find_one({'id': po_id, 'mirror_of': 'production_pos'}, {'_id': 0})
    if not mirror:
        raise HTTPException(404, 'Mirror maklon finance belum ada — jalankan sync-maklon-finance')
    ar = None
    if mirror.get('ar_invoice_id'):
        ar = await db.rahaza_ar_invoices.find_one({'id': mirror['ar_invoice_id']}, {'_id': 0})
    credit_notes = await db.dewi_maklon_credit_notes.find(
        {'po_id': po_id}, {'_id': 0}).sort('created_at', -1).to_list(None)
    return {'mirror': serialize_doc(mirror), 'ar_invoice': serialize_doc(ar),
            'credit_notes': serialize_doc(credit_notes)}


# ═══════════════════════════════════════════════════════════════════════════
# PHASE B — CMT Receipt → AP Mature Helper (2026-07-16)
# ═══════════════════════════════════════════════════════════════════════════

async def mature_ap_from_cmt_receipt(db, receipt_id: str, user: dict) -> dict:
    """Phase B: after DA approves a `cmt_receipts`, mature the AP payable to
    the CMT vendor in `dewi_cmt_payments` (Draft status) with:
        amount = Σ (line.qty_actual × cmt_rate_per_pcs of matching po_item)
    Reject qty is NOT paid (variance = kerugian CMT).

    IDEMPOTENT: keyed by source_receipt_id. Second call returns the existing
    entry unchanged.

    Returns:
        {ok: bool, payment_id, payment_code, amount, already_matured, error?}
    """
    receipt = await db.cmt_receipts.find_one({'id': receipt_id}, {'_id': 0})
    if not receipt:
        return {'ok': False, 'error': 'cmt_receipt tidak ditemukan'}

    # Idempotent guard.
    existing = await db.dewi_cmt_payments.find_one(
        {'source_receipt_id': receipt_id}, {'_id': 0})
    if existing:
        return {
            'ok': True, 'already_matured': True,
            'payment_id': existing['id'],
            'payment_code': existing.get('payment_code'),
            'amount': existing.get('subtotal', 0),
        }

    lines = await db.cmt_receipt_lines.find(
        {'receipt_id': receipt_id}, {'_id': 0}).to_list(500)
    if not lines:
        return {'ok': False, 'error': 'cmt_receipt tanpa lines — tidak bisa mature AP'}

    # Resolve cmt_rate per line via po_item_id → cmt_price_snapshot.
    # Fallback: 0 → variance (Finance manual review).
    po_item_ids = list({ln.get('po_item_id') for ln in lines if ln.get('po_item_id')})
    po_items = await db.po_items.find(
        {'id': {'$in': po_item_ids}}, {'_id': 0}
    ).to_list(None) if po_item_ids else []
    rate_by_item = {pi['id']: float(pi.get('cmt_price_snapshot', 0) or 0) for pi in po_items}

    total_pcs = 0
    total_rejected = 0
    subtotal = 0.0
    breakdown = []
    for ln in lines:
        qty_actual = int(ln.get('qty_actual', 0) or 0)
        reject_qty = int(ln.get('reject_qty', 0) or 0)
        rate = rate_by_item.get(ln.get('po_item_id'), 0.0)
        line_amt = round(qty_actual * rate, 2)
        subtotal += line_amt
        total_pcs += qty_actual
        total_rejected += reject_qty
        breakdown.append({
            'line_id': ln.get('id'),
            'sku_code': ln.get('sku_code', ''),
            'qty_actual': qty_actual,
            'reject_qty': reject_qty,
            'cmt_rate_per_pcs': rate,
            'line_amount': line_amt,
            'po_item_id': ln.get('po_item_id', ''),
        })
    subtotal = round(subtotal, 2)

    # Vendor / cmt id resolution — cmt_vendor_id (Phase B) > related shipment vendor.
    cmt_vendor_id = receipt.get('cmt_vendor_id') or ''
    if not cmt_vendor_id and receipt.get('related_shipment_id'):
        ship = await db.buyer_shipments.find_one({'id': receipt['related_shipment_id']}, {'_id': 0})
        cmt_vendor_id = (ship or {}).get('vendor_id', '')
    # F13 — `vendor_id` pada dokumen pembayaran WAJIB id `vendor_partners` (SSOT).
    # Dulu nilai `cmt_vendor_id` dipakai apa adanya: kalau ia datang dari Portal
    # CMT (`dewi_cmt_partners`), kolom `vendor_id` ikut berisi id master lain, dan
    # dari situlah "satu kolom dua ruang-id" bermula. Kalau tidak terpetakan,
    # nilai aslinya tetap disimpan (lebih baik tercatat daripada hilang) — dan
    # `canonical_id()` sudah menulis peringatan beserta perintah migrasinya.
    canon_vendor_id = await cmt_vendor_master.canonical_id(db, cmt_vendor_id) or cmt_vendor_id
    # Cerminan master Portal CMT untuk kompatibilitas dokumen/layar lama.
    partner = None
    if cmt_vendor_id:
        partner = await db.dewi_cmt_partners.find_one({'id': cmt_vendor_id}) or \
                  await db.dewi_cmt_partners.find_one({'vendor_id': cmt_vendor_id}) or \
                  await db.dewi_cmt_partners.find_one({'vendor_partner_id': canon_vendor_id}) or \
                  await db.dewi_cmt_partners.find_one({'name': receipt.get('cmt_name', '')})

    # Reuse the same counter/prefix used by the archived dewi_cmt payments module.
    try:
        from utils.counters import gen_prefixed_number
        payment_code = await gen_prefixed_number(
            db, 'dewi_cmt_payments', 'payment_code', 'PAY-CMT-', 5
        )
    except Exception:
        # F13 — DULU jatuh ke nomor acak TANPA SUARA. Ini dokumen UANG: nomornya
        # keluar dari urutan resmi (`utils.counters`), jadi rekonsiliasi "PAY-CMT-
        # 00001..00N" akan menemukan lubang yang tidak bisa dijelaskan siapa pun.
        # Fallback-nya DIPERTAHANKAN (lebih baik pembayaran tercatat dengan nomor
        # aneh daripada hilang), tapi sekarang wajib meninggalkan jejak.
        payment_code = f"PAY-CMT-{new_id()[:8]}"
        logger.exception(
            "[maklon-bridge] penomoran resmi pembayaran CMT GAGAL — dipakai nomor "
            "darurat %s (di luar urutan counters). Dokumen uang ini perlu "
            "dirapikan manual; receipt=%s", payment_code, receipt.get('id'))

    payment_id = new_id()
    variance_flag = int(receipt.get('total_shipped_by_cmt', 0) or 0) != (total_pcs + total_rejected)
    doc = {
        'id': payment_id,
        'payment_code': payment_code,
        # ── FASE 7 (cacat HIGH FIN-3/CMT-3, audit 2026-07-31) ────────────────
        # Dulu kolom ini diisi id dari `vendor_partners` sementara dokumen lama
        # memakai id `dewi_cmt_partners` ⇒ SATU kolom menyimpan id dari DUA master
        # berbeda dan pengelompokan tagihan per CMT di Portal CMT jadi salah.
        # F13: penulisannya kini tegas satu arah — `vendor_id` SELALU id
        # `vendor_partners` (SSOT, lewat `core.cmt_vendor_master.canonical_id`),
        # `cmt_partner_id` hanya CERMINAN untuk layar/dokumen lama. Semua pembaca
        # memakai `cmt_vendor_master.payment_filter()` sehingga tidak ada lagi
        # layar yang mencari dengan ruang-id yang salah.
        'cmt_partner_id': (partner or {}).get('id') or canon_vendor_id or cmt_vendor_id or '',
        'vendor_id': canon_vendor_id or '',
        'vendor_name': receipt.get('cmt_name', ''),
        'cmt_name': receipt.get('cmt_name', ''),
        'source_receipt_id': receipt_id,
        'source_receipt_code': receipt.get('receipt_code', ''),
        'po_id': receipt.get('po_id', ''),
        'po_number': receipt.get('po_number', '') or receipt.get('wo_number', ''),
        'wo_id': receipt.get('wo_id', ''),
        'wo_number': receipt.get('wo_number', ''),
        'period_from': receipt.get('receipt_date', ''),
        'period_to': receipt.get('receipt_date', ''),
        'total_pcs': total_pcs,
        'total_rejected': total_rejected,
        'subtotal': subtotal,
        'total_penalty': 0.0,
        'net_amount': subtotal,
        # Alias nama field jumlah: dokumen lama memakai `total_amount`, dokumen
        # baru `net_amount`. Simpan keduanya supaya laporan lama & baru sama.
        'total_amount': subtotal,
        'status': 'draft',   # Finance still has to approve + post to GL
        'variance_flagged': variance_flag,
        'variance_reason': receipt.get('variance_reason', ''),
        'breakdown': breakdown,
        'notes': f"Auto-matured dari CMT Receipt {receipt.get('receipt_code','')} (Phase B).",
        'created_at': now(), 'updated_at': now(),
        'created_by': user.get('id', ''),
        'created_by_name': user.get('name', 'system'),
    }
    await db.dewi_cmt_payments.insert_one(doc)

    try:
        await log_activity(
            user.get('id', ''), user.get('name', 'system'),
            'Mature AP', 'CMT Payment',
            f"AP CMT {payment_code} — {receipt.get('cmt_name','')} — Rp {subtotal:,.0f} "
            f"({total_pcs} pcs actual, {total_rejected} pcs reject)"
        )
    except Exception as e:  # noqa: BLE001 — jejak aktivitas tidak boleh membatalkan
        # pematangan AP yang sudah tercatat, tapi hilangnya jejak audit uang
        # harus terlihat (dulu `pass` tanpa suara).
        logger.warning("[cmt] gagal mencatat jejak aktivitas pematangan AP %s: %s",
                       payment_code, e)

    return {
        'ok': True,
        'already_matured': False,
        'payment_id': payment_id,
        'payment_code': payment_code,
        'amount': subtotal,
        'total_pcs': total_pcs,
        'total_rejected': total_rejected,
        'variance_flagged': variance_flag,
    }



# ═══════════════════════════════════════════════════════════════════════════
# PHASE C — PO Closure (auto-close 100% + close-short + credit note)  2026-07-17
# ═══════════════════════════════════════════════════════════════════════════

async def _buyer_shipment_ids_for_po(db, po_id: str) -> list:
    """Phase D: shipment ids that are REAL DA→buyer dispatch TOUCHING this PO.

    Item-based (supports ONE consolidated surat jalan spanning MULTIPLE POs)
    UNION legacy header-based (old single-PO SJ / items not yet backfilled with
    po_id). Excludes Phase B CMT→DA declarations (receiver_type='da'); includes
    legacy docs without the field (backward compat)."""
    buyer_clause = [
        {'receiver_type': 'buyer'},
        {'receiver_type': {'$exists': False}},
        {'receiver_type': None},
    ]
    ids = set()
    # (a) legacy header-based (single-PO surat jalan)
    async for s in db.buyer_shipments.find(
            {'po_id': po_id, '$or': buyer_clause}, {'_id': 0, 'id': 1}):
        ids.add(s['id'])
    # (b) item-based: any buyer_shipment_item carrying this po_id (Phase D
    #     consolidated SJ where the header po_id may be null / another PO)
    item_ship_ids = await db.buyer_shipment_items.distinct('shipment_id', {'po_id': po_id})
    if item_ship_ids:
        async for s in db.buyer_shipments.find(
                {'id': {'$in': item_ship_ids}, '$or': buyer_clause}, {'_id': 0, 'id': 1}):
            ids.add(s['id'])
    return list(ids)


async def compute_po_fulfillment(db, po_id: str) -> dict:
    """Phase C: fulfillment snapshot for a PO based on BUYER-received qty.

    Effective received per item = qty_received when set, else qty_shipped
    (assume fully received). Counts only DA→buyer dispatch shipments.

    Returns dict with totals + per-item maps (used by auto-close + credit note).
    """
    po_items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).to_list(None)
    item_ids = [i['id'] for i in po_items]
    ordered_by_item = {i['id']: int(i.get('qty', 0) or 0) for i in po_items}
    # Harga jasa ke KLIEN (selling); `cmt_price_snapshot` adalah upah vendor, bukan harga tagihan.
    rate_by_item = {
        i['id']: float(i.get('selling_price_snapshot', 0) or 0) or float(i.get('cmt_price_snapshot', 0) or 0)
        for i in po_items}
    total_ordered = sum(ordered_by_item.values())

    bs_ids = await _buyer_shipment_ids_for_po(db, po_id)
    bitems = await db.buyer_shipment_items.find(
        {'po_item_id': {'$in': item_ids}, 'shipment_id': {'$in': bs_ids}}, {'_id': 0}
    ).to_list(None) if (item_ids and bs_ids) else []

    received_by_item: dict = {}
    shipped_by_item: dict = {}
    for bi in bitems:
        poi = bi.get('po_item_id')
        shipped = int(bi.get('qty_shipped', 0) or 0)
        recv = bi.get('qty_received')
        recv = int(recv) if recv is not None else shipped
        received_by_item[poi] = received_by_item.get(poi, 0) + recv
        shipped_by_item[poi] = shipped_by_item.get(poi, 0) + shipped

    total_received = sum(received_by_item.values())
    total_shipped = sum(shipped_by_item.values())

    # PO INTERNAL: "terpenuhi" = sudah DIPRODUKSI (masuk FG) — bukan hanya yang
    # sudah dikirim ke buyer. Tanpa ini PO dengan produksi nyata dilaporkan 100%
    # short saat ditutup (audit iteration_102).
    po_doc = await db.production_pos.find_one({'id': po_id}, {'_id': 0, 'business_type': 1})
    is_internal = (po_doc or {}).get('business_type') == 'internal'
    produced_by_item: dict = {}
    if is_internal and item_ids:
        async for ji in db.production_job_items.find(
                {'po_item_id': {'$in': item_ids}}, {'_id': 0, 'po_item_id': 1, 'produced_qty': 1}):
            poi = ji.get('po_item_id')
            produced_by_item[poi] = produced_by_item.get(poi, 0) + int(ji.get('produced_qty', 0) or 0)
    total_produced = sum(produced_by_item.values())
    fulfilled_by_item = {
        poi: max(received_by_item.get(poi, 0), produced_by_item.get(poi, 0)) for poi in item_ids
    } if is_internal else received_by_item
    total_fulfilled = sum(fulfilled_by_item.values())
    qty_short = max(0, total_ordered - total_fulfilled)
    qty_short_pct = round(qty_short / total_ordered * 100, 2) if total_ordered > 0 else 0.0
    return {
        'po_id': po_id,
        'basis': 'produced' if is_internal else 'buyer_received',
        'total_ordered': total_ordered,
        'total_received': total_received,
        'total_shipped': total_shipped,
        'total_produced': total_produced,
        'total_fulfilled': total_fulfilled,
        'qty_short': qty_short,
        'qty_short_pct': qty_short_pct,
        'is_full': total_ordered > 0 and total_fulfilled >= total_ordered,
        'ordered_by_item': ordered_by_item,
        'received_by_item': received_by_item,
        'rate_by_item': rate_by_item,
    }


async def billable_lines_for_po(db, po_id: str) -> dict:
    """SATU rumus tagihan klien maklon: qty yang DITERIMA buyer per item × harga jasa (selling).
    Dipakai `GET /invoices/eligible` (pratinjau) dan `POST /invoices/generate` (terbit) —
    layar dan dokumen tidak boleh berbeda angka (audit M-04/M-05)."""
    f = await compute_po_fulfillment(db, po_id)
    po_items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).sort('created_at', 1).to_list(None)
    lines = []
    subtotal = 0.0
    for pi in po_items:
        qty = int(f['received_by_item'].get(pi['id'], 0) or 0)
        if qty <= 0:
            continue
        rate = float(f['rate_by_item'].get(pi['id'], 0) or 0)
        sub = round(qty * rate, 2)
        subtotal += sub
        lines.append({
            'line_id': new_id(), 'item_id': pi['id'], 'sku': pi.get('sku', ''),
            'description': (f"Jasa Maklon — {pi.get('product_name', '')} {pi.get('color', '')} "
                            f"{pi.get('size', '')} (Seri {pi.get('serial_number') or '-'})").strip(),
            'qty': qty, 'qty_ordered': int(pi.get('qty', 0) or 0), 'unit': 'pcs',
            'unit_price': rate, 'subtotal': sub, 'line_total': sub,
        })
    return {'lines': lines, 'subtotal': round(subtotal, 2),
            'total_ordered': f['total_ordered'], 'total_received': f['total_received']}


async def try_auto_close_po_on_full(db, po_id: str, user: dict) -> dict:
    """Phase C §11.2: auto-transition PO → 'Completed' when buyer-received qty
    reaches the ordered qty. Idempotent + safe (never breaks the caller flow)."""
    try:
        po = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
        if not po:
            return {'closed': False, 'reason': 'po not found'}
        if po.get('status') in ('Completed', 'Closed', 'Closed Short'):
            return {'closed': False, 'already': po.get('status')}
        f = await compute_po_fulfillment(db, po_id)
        if not f['is_full']:
            return {'closed': False, 'fulfillment': f}
        await db.production_pos.update_one({'id': po_id}, {'$set': {
            'status': 'Completed',
            'closed_reason': 'full_fulfillment',
            'closed_at': now(),
            'updated_at': now(),
        }})
        if po.get('business_type') == 'maklon':
            await try_sync_maklon_finance(db, po_id, user)
        try:
            await log_activity(user.get('id', ''), user.get('name', 'system'),
                               'Auto-Close PO', 'Production PO',
                               f"PO {po.get('po_number')} auto-Completed (fulfilled "
                               f"{f['total_received']}/{f['total_ordered']} pcs).")
        except Exception as e:  # noqa: BLE001 — PO sudah tertutup; hanya jejaknya gagal.
            logger.warning("[maklon] gagal mencatat jejak aktivitas auto-close PO %s: %s",
                           po.get('po_number'), e)
        return {'closed': True, 'status': 'Completed', 'fulfillment': f}
    except Exception:
        logger.exception('try_auto_close_po_on_full failed for PO %s', po_id)
        return {'closed': False, 'error': True}


async def finalize_ar_on_short_close(db, po: dict, user: dict, fulfillment: dict) -> dict:
    """Phase C §11.2: on manual close-short of a maklon PO.

    - If AR invoice already ISSUED (status != draft): create a DRAFT credit note
      (`dewi_maklon_credit_notes`) for the short amount (Σ short_qty × cmt_rate).
    - If AR still DRAFT: adjust the draft invoice down to qty_received (invoice the
      buyer only for what was actually delivered).
    Idempotent (one credit note per PO). Non-maklon / no-shortfall → no-op.
    """
    if po.get('business_type') != 'maklon':
        return {'credit_note_created': False, 'skipped': 'not maklon'}
    qty_short = int(fulfillment.get('qty_short', 0) or 0)
    if qty_short <= 0:
        return {'credit_note_created': False, 'skipped': 'no shortfall'}

    ordered = fulfillment['ordered_by_item']
    received = fulfillment['received_by_item']
    rate = fulfillment['rate_by_item']
    short_amount = 0.0
    breakdown = []
    for iid, ord_q in ordered.items():
        rec = int(received.get(iid, 0) or 0)
        sh = max(0, int(ord_q) - rec)
        if sh > 0:
            amt = round(sh * float(rate.get(iid, 0.0) or 0.0), 2)
            short_amount += amt
            breakdown.append({'po_item_id': iid, 'short_qty': sh,
                              'cmt_rate_per_pcs': float(rate.get(iid, 0.0) or 0.0),
                              'amount': amt})
    short_amount = round(short_amount, 2)

    mirror = await db.dewi_maklon_pos.find_one({'id': po['id']}, {'_id': 0})
    ar = None
    if mirror and mirror.get('ar_invoice_id'):
        ar = await db.rahaza_ar_invoices.find_one({'id': mirror['ar_invoice_id']}, {'_id': 0})
    ar_status = (ar or {}).get('status')
    ar_issued = ar is not None and ar_status not in (None, 'draft')

    # ── Path 1: AR already issued → credit note draft (idempotent by po_id) ──
    if ar_issued:
        existing_cn = await db.dewi_maklon_credit_notes.find_one({'po_id': po['id']}, {'_id': 0})
        if existing_cn:
            return {'credit_note_created': False, 'already_exists': True,
                    'credit_note_id': existing_cn['id'],
                    'credit_note_number': existing_cn.get('credit_note_number'),
                    'amount': existing_cn.get('total_amount')}
        try:
            from utils.counters import gen_prefixed_number
            cn_number = await gen_prefixed_number(
                db, 'dewi_maklon_credit_notes', 'credit_note_number', 'CN-MKL-', 5)
        except Exception:
            # F13 — sama seperti nomor pembayaran CMT: nota kredit MENGURANGI
            # piutang, jadi nomor di luar urutan resmi membuat audit AR tidak bisa
            # dilacak. Non-blocking (nota tetap terbit), tapi bersuara.
            cn_number = f"CN-MKL-{new_id()[:8]}"
            logger.exception(
                "[maklon-bridge] penomoran resmi nota kredit maklon GAGAL — dipakai "
                "nomor darurat %s (di luar urutan counters) untuk po=%s",
                cn_number, po.get('id'))
        cn_id = new_id()
        await db.dewi_maklon_credit_notes.insert_one({
            'id': cn_id,
            'credit_note_number': cn_number,
            'po_id': po['id'],
            'po_number': po.get('po_number', ''),
            'source_ar_invoice_id': (ar or {}).get('id'),
            'source_ar_invoice_number': (ar or {}).get('invoice_number'),
            'customer_id': po.get('buyer_id'),
            'customer_name': po.get('customer_name', ''),
            'reason': 'po_close_short',
            'closed_reason': po.get('closed_reason', ''),
            'qty_short': qty_short,
            'breakdown': breakdown,
            'subtotal': short_amount,
            'total_amount': short_amount,
            'status': 'draft',
            'notes': f"Auto-generated credit note dari PO close-short {po.get('po_number', '')} (Phase C).",
            'gl_posted_at': None, 'gl_je_id': None,
            'created_at': now(), 'updated_at': now(),
            'created_by': user.get('id', ''),
            'created_by_name': user.get('name', 'system'),
        })
        try:
            await log_activity(user.get('id', ''), user.get('name', 'system'),
                               'Create Credit Note', 'Maklon Finance',
                               f"Credit note {cn_number} — PO {po.get('po_number')} — "
                               f"Rp {short_amount:,.0f} ({qty_short} pcs short).")
        except Exception as e:  # noqa: BLE001 — nota kredit sudah dibuat; hanya jejaknya gagal.
            logger.warning("[maklon] gagal mencatat jejak aktivitas nota kredit %s: %s",
                           cn_number, e)
        return {'credit_note_created': True, 'credit_note_id': cn_id,
                'credit_note_number': cn_number, 'amount': short_amount,
                'ar_status': ar_status}

    # ── Path 2: AR still draft → shrink draft invoice to qty_received ──
    adjusted = False
    if ar is not None and ar_status == 'draft':
        new_lines = []
        new_subtotal = 0.0
        for ln in ar.get('lines', []):
            iid = ln.get('item_id')
            rec = int(received.get(iid, ln.get('qty', 0)) or 0)
            unit = float(ln.get('unit_price', 0) or 0)
            sub = round(rec * unit, 2)
            new_subtotal += sub
            new_lines.append({**ln, 'qty': rec, 'subtotal': sub})
        new_subtotal = round(new_subtotal, 2)
        await db.rahaza_ar_invoices.update_one({'id': ar['id']}, {'$set': {
            'lines': new_lines,
            'subtotal': new_subtotal,
            'total_amount': new_subtotal,
            'amount_due': round(new_subtotal - float(ar.get('amount_paid', 0) or 0), 2),
            'notes': (ar.get('notes', '') + ' | Disesuaikan ke qty_received saat PO close-short (Phase C).').strip(),
            'updated_at': now(),
        }})
        await db.dewi_maklon_pos.update_one({'id': po['id']}, {'$set': {
            'total_value': new_subtotal, 'updated_at': now()}})
        adjusted = True
    return {'credit_note_created': False, 'ar_adjusted_to_received': adjusted,
            'ar_status': ar_status, 'short_amount': short_amount}


@router.get("/production-pos/{po_id}/credit-notes")
async def list_po_credit_notes(po_id: str, request: Request):
    """Phase C: list credit notes generated for a PO (draft/posted)."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    docs = await db.dewi_maklon_credit_notes.find(
        {'po_id': po_id}, {'_id': 0}).sort('created_at', -1).to_list(None)
    return serialize_doc(docs)
