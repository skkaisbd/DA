"""Configurable document numbering (Phase D).

Generic, race-safe document numbering with a per-doc-type FORMAT template stored
in `document_number_configs`. Falls back to a sensible default when no config
exists. Reuses the atomic `counters` SSOT (`utils.counters.next_counter`) for the
sequence so numbering never races/duplicates under concurrency.

Format tokens (case-insensitive):
  {PREFIX}  -> config.prefix (optional free text)
  {YYYY}    -> 4-digit year         {YY} -> 2-digit year
  {MM}      -> 2-digit month        {DD} -> 2-digit day
  {SEQ}     -> sequence padded to seq_width
  {SEQn}    -> sequence padded to n digits (e.g. {SEQ5})
  {PO}      -> context['po_number']
  {BUYER}   -> context['buyer'] slug (A-Z0-9, uppercased, max 12)

seq_reset: 'yearly' | 'monthly' | 'never'  -> controls the counter bucket
(so the running number resets each year/month or never).

Manual override still wins: callers should only auto-generate when the user did
NOT provide an explicit document number.
"""
from __future__ import annotations
import re
from datetime import datetime

from utils.counters import next_counter
from utils.waktu import now_wib

# Built-in defaults (used when no saved config for the doc_type). Kept generic so
# new doc types can be added just by referencing them from a caller.
DEFAULT_CONFIGS = {
    'buyer_shipment_da': {
        'label': 'Surat Jalan CMT → DA',
        'format': 'SJ-CMT-DA-{YYYY}{MM}-{SEQ}',
        'prefix': '', 'seq_width': 4, 'seq_reset': 'yearly',
    },
    'buyer_shipment_buyer': {
        'label': 'Surat Jalan DA → Buyer',
        'format': 'SJ-BYR-{YYYY}{MM}-{SEQ}',
        'prefix': '', 'seq_width': 4, 'seq_reset': 'monthly',
    },
}

SEQ_RESETS = ('yearly', 'monthly', 'never')


def _base_config(doc_type: str) -> dict:
    base = DEFAULT_CONFIGS.get(doc_type)
    if base is None:
        base = {
            'label': doc_type,
            'format': f'{doc_type.upper()}-{{YYYY}}-{{SEQ}}',
            'prefix': '', 'seq_width': 4, 'seq_reset': 'yearly',
        }
    return dict(base)


async def get_number_config(db, doc_type: str) -> dict:
    """Return effective config for a doc_type: saved (if any) merged over default."""
    cfg = _base_config(doc_type)
    saved = await db.document_number_configs.find_one({'_id': doc_type}, {'_id': 0})
    if saved:
        cfg.update({k: v for k, v in saved.items() if v is not None})
    cfg['doc_type'] = doc_type
    cfg.setdefault('enabled', True)
    # sanity
    try:
        cfg['seq_width'] = max(1, min(10, int(cfg.get('seq_width') or 4)))
    except (TypeError, ValueError):
        cfg['seq_width'] = 4
    if cfg.get('seq_reset') not in SEQ_RESETS:
        cfg['seq_reset'] = 'yearly'
    fmt = str(cfg.get('format') or '').strip()
    if not fmt:
        fmt = _base_config(doc_type)['format']
    # guarantee a sequence token so numbers are always unique
    if not re.search(r'\{SEQ\d*\}', fmt, flags=re.IGNORECASE):
        fmt = fmt.rstrip('-') + '-{SEQ}'
    cfg['format'] = fmt
    return cfg


def _slug(value, n: int = 12) -> str:
    return re.sub(r'[^A-Za-z0-9]', '', str(value or '')).upper()[:n]


def _reset_bucket(seq_reset: str, dt: datetime) -> str:
    if seq_reset == 'monthly':
        return f'{dt:%Y%m}'
    if seq_reset == 'never':
        return 'all'
    return f'{dt:%Y}'


def render_number(cfg: dict, *, seq, context: dict | None = None,
                  dt: datetime | None = None) -> str:
    """Render a format string with a concrete (or None) sequence.

    When seq is None the {SEQ} tokens render empty (used to compute a stable key
    or a placeholder). seq_width comes from cfg.
    """
    context = context or {}
    # 2026-08-07 (P3) — WIB, bukan UTC. Token {YYYY}{MM}{DD} pada nomor dokumen
    # dan bucket reset counter harus mengikuti kalender lokal; lihat utils/waktu.py.
    dt = dt or now_wib()
    seq_width = int(cfg.get('seq_width') or 4)
    out = str(cfg.get('format') or '')
    repl = {
        '{PREFIX}': str(cfg.get('prefix', '') or ''),
        '{YYYY}': f'{dt:%Y}', '{YY}': f'{dt:%y}',
        '{MM}': f'{dt:%m}', '{DD}': f'{dt:%d}',
        '{PO}': str(context.get('po_number', '') or ''),
        '{BUYER}': _slug(context.get('buyer', '')),
    }
    for k, v in repl.items():
        out = re.sub(re.escape(k), v, out, flags=re.IGNORECASE)

    def _seq_sub(m):
        if seq is None:
            return ''
        w = int(m.group(1)) if m.group(1) else seq_width
        return str(seq).zfill(w)

    out = re.sub(r'\{SEQ(\d*)\}', _seq_sub, out, flags=re.IGNORECASE)
    return out


def preview_number(cfg: dict, *, context: dict | None = None,
                   sample_seq: int = 1, dt: datetime | None = None) -> str:
    """Render an example number WITHOUT touching the counter (for UI preview)."""
    return render_number(cfg, seq=sample_seq, context=context, dt=dt)


async def gen_document_number(db, doc_type: str, *, context: dict | None = None,
                              dt: datetime | None = None) -> str:
    """Atomically generate the next configured document number for doc_type."""
    dt = dt or now_wib()
    cfg = await get_number_config(db, doc_type)
    bucket = _reset_bucket(cfg.get('seq_reset', 'yearly'), dt)
    counter_key = f'docnum:{doc_type}:{bucket}'
    seq = await next_counter(db, counter_key, namespace='docnum')
    return render_number(cfg, seq=seq, context=context, dt=dt)
