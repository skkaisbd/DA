"""
AI Cash Flow Prediction — CV. Dewi Aditya ERP
Endpoint: GET /api/finance/ai-cashflow

Aggregates AR aging + AP aging + 60-day cash movements, then calls LLM
(via emergentintegrations) to generate a short-term cash flow prediction
with risks & recommendations.
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc
from datetime import date, timedelta
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/finance", tags=["AI-CashFlow"])

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _fmt(n: float) -> str:
    """Format number as Rp X juta / miliar."""
    if n >= 1_000_000_000:
        return f"Rp {n/1_000_000_000:.2f} miliar"
    if n >= 1_000_000:
        return f"Rp {n/1_000_000:.1f} juta"
    return f"Rp {n:,.0f}"


async def _build_context(db) -> dict:
    """Fetch & aggregate data for the LLM prompt."""
    today = date.today()
    sixty_ago = (today - timedelta(days=60)).isoformat()
    today_iso = today.isoformat()

    # ── AR aging ──
    ar_invs = await db.rahaza_ar_invoices.find(
        {'status': {'$in': ['sent', 'partial']}}, {'_id': 0, 'balance': 1, 'due_date': 1, 'buyer_name': 1, 'total': 1}
    ).to_list(500)
    ar_buckets = {'current': 0, '1-30': 0, '31-60': 0, '61-90': 0, '90+': 0}
    for inv in ar_invs:
        bal = float(inv.get('balance', 0))
        dd = inv.get('due_date', '')
        try:
            diff = (today - date.fromisoformat(dd[:10])).days
        except Exception:
            diff = 0
        if diff <= 0:
            ar_buckets['current'] += bal
        elif diff <= 30:
            ar_buckets['1-30'] += bal
        elif diff <= 60:
            ar_buckets['31-60'] += bal
        elif diff <= 90:
            ar_buckets['61-90'] += bal
        else:
            ar_buckets['90+'] += bal

    total_ar = sum(ar_buckets.values())
    overdue_ar = ar_buckets['1-30'] + ar_buckets['31-60'] + ar_buckets['61-90'] + ar_buckets['90+']

    # ── AP aging ──
    ap_invs = await db.rahaza_ap_invoices.find(
        {'status': {'$in': ['sent', 'partial']}}, {'_id': 0, 'balance': 1, 'due_date': 1, 'vendor_name': 1}
    ).to_list(500)
    ap_buckets = {'current': 0, '1-30': 0, '31-60': 0, '61-90': 0, '90+': 0}
    for inv in ap_invs:
        bal = float(inv.get('balance', 0))
        dd = inv.get('due_date', '')
        try:
            diff = (today - date.fromisoformat(dd[:10])).days
        except Exception:
            diff = 0
        if diff <= 0:
            ap_buckets['current'] += bal
        elif diff <= 30:
            ap_buckets['1-30'] += bal
        elif diff <= 60:
            ap_buckets['31-60'] += bal
        elif diff <= 90:
            ap_buckets['61-90'] += bal
        else:
            ap_buckets['90+'] += bal

    total_ap = sum(ap_buckets.values())

    # ── Cash movements last 60 days (bank recon approved sessions + journals) ──
    cash_in_60 = 0.0
    cash_out_60 = 0.0

    # RC-08: SSOT arus kas aktual = rahaza_cash_movements (direction in/out).
    # (rahaza_ar_receipts / rahaza_ap_payments = phantom — tak pernah ditulis kode mana pun.)
    cm_docs = await db.rahaza_cash_movements.find(
        {'date': {'$gte': sixty_ago}}, {'_id': 0, 'amount': 1, 'direction': 1}
    ).to_list(1000)
    cash_in_60 = sum(float(m.get('amount', 0) or 0) for m in cm_docs if m.get('direction') == 'in')
    cash_out_60 = sum(float(m.get('amount', 0) or 0) for m in cm_docs if m.get('direction') == 'out')

    # Fallback: bank recon transactions from approved sessions
    if cash_in_60 == 0 and cash_out_60 == 0:
        sessions = await db.bank_recon_sessions.find(
            {'status': 'approved'}, {'_id': 0, 'id': 1}
        ).to_list(50)
        if sessions:
            sid_list = [s['id'] for s in sessions]
            txns = await db.bank_recon_txns.find(
                {'session_id': {'$in': sid_list}, 'txn_date': {'$gte': sixty_ago}},
                {'_id': 0, 'amount': 1, 'type': 1}
            ).to_list(500)
            cash_in_60  = sum(float(t.get('amount', 0)) for t in txns if t.get('type') == 'debit')
            cash_out_60 = sum(float(t.get('amount', 0)) for t in txns if t.get('type') == 'credit')

    # ── Upcoming AP due in 30 days ──
    next_30 = (today + timedelta(days=30)).isoformat()
    upcoming_ap = await db.rahaza_ap_invoices.find(
        {'status': {'$in': ['sent', 'partial']}, 'due_date': {'$gte': today_iso, '$lte': next_30}},
        {'_id': 0, 'vendor_name': 1, 'balance': 1, 'due_date': 1}
    ).sort('due_date', 1).to_list(10)

    # ── Upcoming AR due in 30 days ──
    upcoming_ar = await db.rahaza_ar_invoices.find(
        {'status': {'$in': ['sent', 'partial']}, 'due_date': {'$gte': today_iso, '$lte': next_30}},
        {'_id': 0, 'buyer_name': 1, 'balance': 1, 'due_date': 1}
    ).sort('due_date', 1).to_list(10)

    # ── Active production orders (cash commitment) ──
    active_orders = await db.rahaza_orders.count_documents({'status': {'$in': ['confirmed', 'in_production']}})

    return {
        'today': today_iso,
        'ar_buckets': ar_buckets, 'total_ar': total_ar, 'overdue_ar': overdue_ar,
        'ap_buckets': ap_buckets, 'total_ap': total_ap,
        'cash_in_60': cash_in_60, 'cash_out_60': cash_out_60,
        'upcoming_ar': upcoming_ar, 'upcoming_ap': upcoming_ap,
        'active_orders': active_orders,
    }


def _build_prompt(ctx: dict) -> str:
    ar = ctx['ar_buckets']
    ap = ctx['ap_buckets']
    upar = ctx['upcoming_ar']
    upap = ctx['upcoming_ap']
    prompt = f"""Anda adalah CFO digital untuk CV. Dewi Aditya, perusahaan garmen di Indonesia.
Tanggal hari ini: {ctx['today']}.

DATA KEUANGAN AKTUAL:

Piutang Usaha (AR) yang belum terbayar:
- Belum jatuh tempo : {_fmt(ar['current'])}
- Telat 1-30 hari   : {_fmt(ar['1-30'])}
- Telat 31-60 hari  : {_fmt(ar['31-60'])}
- Telat 61-90 hari  : {_fmt(ar['61-90'])}
- Telat >90 hari    : {_fmt(ar['90+'])}
- TOTAL AR Outstanding: {_fmt(ctx['total_ar'])}  |  Overdue: {_fmt(ctx['overdue_ar'])}

Hutang Usaha (AP) yang belum dibayar:
- Belum jatuh tempo : {_fmt(ap['current'])}
- Jatuh tempo 1-30 h: {_fmt(ap['1-30'])}
- Jatuh tempo 31-60h: {_fmt(ap['31-60'])}
- TOTAL AP Outstanding: {_fmt(ctx['total_ap'])}

Arus Kas 60 hari terakhir:
- Kas masuk (penerimaan AR): {_fmt(ctx['cash_in_60'])}
- Kas keluar (bayar AP): {_fmt(ctx['cash_out_60'])}
- Net 60 hari: {_fmt(ctx['cash_in_60'] - ctx['cash_out_60'])}

Tagihan AR yang jatuh tempo 30 hari ke depan:
{chr(10).join(f"- {i.get('buyer_name','?')}: {_fmt(float(i.get('balance',0)))} (due: {i.get('due_date','')})" for i in upar) or '- Tidak ada'}

Kewajiban AP yang jatuh tempo 30 hari ke depan:
{chr(10).join(f"- {i.get('vendor_name','?')}: {_fmt(float(i.get('balance',0)))} (due: {i.get('due_date','')})" for i in upap) or '- Tidak ada'}

Order produksi aktif: {ctx['active_orders']} order

Berikan analisis arus kas dalam Bahasa Indonesia yang singkat dan actionable, mencakup:
1. **Ringkasan Posisi Kas** (2-3 kalimat)
2. **Risiko 30 Hari** (bullet poin, max 3 risiko utama)
3. **Risiko 60-90 Hari** (bullet poin, max 2 risiko)
4. **Rekomendasi Prioritas** (3 tindakan konkret)
5. **Estimasi Net Cash Flow** 30/60/90 hari berdasarkan tren

Format: ringkas, profesional, gunakan angka Rupiah. Jangan pakai disclaimer panjang."""
    return prompt


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/ai-cashflow")
async def ai_cashflow_prediction(request: Request):
    """
    AI Cash Flow Prediction — analisis arus kas 30/60/90 hari ke depan.
    Menggunakan data AR/AP aging + arus kas historis untuk menghasilkan
    prediksi dan rekomendasi berbasis LLM (GPT-4o).
    """
    await require_auth(request)
    db = get_db()

    llm_key = os.environ.get('EMERGENT_LLM_KEY')
    if not llm_key:
        raise HTTPException(503, "EMERGENT_LLM_KEY tidak tersedia di environment.")

    # ── Build context ──
    ctx = await _build_context(db)

    # ── Call LLM ──
    try:
        from ai_llm import LlmChat, UserMessage
        chat = LlmChat(
            api_key=llm_key,
            session_id=f"cashflow-{date.today().isoformat()}",
            system_message="Kamu adalah CFO digital yang ahli keuangan garmen Indonesia.",
        ).with_model("openai", "gpt-5.1")
        prompt = _build_prompt(ctx)
        response = await chat.send_message(UserMessage(text=prompt))
        analysis = response.text if hasattr(response, 'text') else str(response)
    except Exception as e:
        logger.error(f"LLM cashflow error: {e}")
        raise HTTPException(502, f"Gagal memanggil AI: {str(e)[:200]}")

    return {
        'analysis': analysis,
        'context': {
            'today': ctx['today'],
            'total_ar': ctx['total_ar'],
            'overdue_ar': ctx['overdue_ar'],
            'total_ap': ctx['total_ap'],
            'cash_in_60': ctx['cash_in_60'],
            'cash_out_60': ctx['cash_out_60'],
            'net_60': ctx['cash_in_60'] - ctx['cash_out_60'],
            'ar_aging': ctx['ar_buckets'],
            'ap_aging': ctx['ap_buckets'],
            'active_orders': ctx['active_orders'],
            'upcoming_ar': serialize_doc(ctx['upcoming_ar']),
            'upcoming_ap': serialize_doc(ctx['upcoming_ap']),
        }
    }
