"""core/fulfillment_status.py — SSOT **kosakata status fulfillment** (Sesi #20).

═══════════════════════════════════════════════════════════════════════════════
MASALAH NYATA YANG DITUTUP BERKAS INI  (diukur `tests/poc_sync_forensic.py`)
═══════════════════════════════════════════════════════════════════════════════
Dua penulis, dua kamus, dan tidak pernah bertemu:

| Penulis                                            | Nilai yang ditulis    |
|----------------------------------------------------|-----------------------|
| `routes/marketing_data_import.py` (impor pesanan)  | ``'unallocated'``     |
| `routes/marketing_orders_routes.py` (buat manual)  | ``'pending_fulfillment'`` |

Sementara pembacanya — antrean gudang `GET /api/fulfillment/queue` — hanya
mengenal::

    ['pending_fulfillment', 'allocated', 'picking', 'packed_ready', 'awaiting_scanout']

Akibat yang TERUKUR pada data hidup: **559 pesanan** berstatus "Perlu dikirim"
tersimpan dengan ``fulfillment_status='unallocated'``, dan antrean gudang
menampilkan **0**. Tim gudang tidak sedang salah membaca layar — layarnya
memang tidak pernah memuat pekerjaan itu. Inilah keluhan pemilik:
*"list barang dari marketing untuk dikirimkan oleh tim gudang tidak ada yang sama"*.

ATURAN KERAS
------------
1. **JANGAN** menyalin daftar status antrean ke route mana pun. Impor
   :data:`QUEUE_STATES` dari sini.
2. **JANGAN** menulis istilah baru (mis. ``'unallocated'``) tanpa mendaftarkannya
   di :data:`ALIASES` — kalau tidak, ia akan hilang dari antrean seperti dulu.
3. Status awal pesanan hasil impor DITURUNKAN dari status platformnya lewat
   :func:`initial_status`, bukan dipatok satu nilai untuk semua. Pesanan yang
   sudah selesai bertahun lalu tidak boleh membanjiri antrean hari ini.

JUJUR TENTANG BATASNYA
----------------------
Berkas ini TIDAK memindahkan stok dan TIDAK membuat jurnal. Ia hanya mengurus
*penamaan keadaan* supaya satu pekerjaan terlihat oleh orang yang harus
mengerjakannya.
"""
from __future__ import annotations

from core.order_status import STATUS_RANK

# ── Status kanonik ───────────────────────────────────────────────────────────
PENDING = 'pending_fulfillment'      # menunggu dialokasikan gudang
ALLOCATED = 'allocated'              # FG sudah dipesan untuk pesanan ini
PICKING = 'picking'                  # sedang diambil dari rak
PACKED = 'packed_ready'              # sudah dikemas
AWAITING_SCANOUT = 'awaiting_scanout'
DISPATCHED = 'dispatched'
DELIVERED = 'delivered'
CANCELLED = 'cancelled'
NOT_REQUIRED = 'not_required'        # platform sudah menyelesaikannya (impor riwayat)

FULFILLMENT_STATUSES: tuple = (
    PENDING, ALLOCATED, PICKING, PACKED, AWAITING_SCANOUT,
    DISPATCHED, DELIVERED, CANCELLED, NOT_REQUIRED,
)

# ── Alias WARISAN ────────────────────────────────────────────────────────────
# `'unallocated'` ditulis impor sejak F1 pada 559 pesanan nyata. Menghapusnya
# dengan migrasi diam-diam berarti menyentuh data pemilik tanpa ia melihatnya,
# jadi ia DIAKUI di sini sebagai sinonim BACA. Penulisan BARU memakai kanonik.
ALIASES: dict = {
    'unallocated': PENDING,
    'pending': PENDING,
    'menunggu': PENDING,
    '': PENDING,
    None: PENDING,
}

#: Keadaan yang berarti "gudang masih punya pekerjaan di pesanan ini".
QUEUE_STATES: tuple = (PENDING, 'unallocated', ALLOCATED, PICKING, PACKED, AWAITING_SCANOUT)

#: Keadaan yang berarti "belum tersentuh gudang" (butuh alokasi).
UNTOUCHED_STATES: tuple = (PENDING, 'unallocated')

#: Keadaan akhir — tidak ada pekerjaan gudang lagi.
CLOSED_STATES: tuple = (DISPATCHED, DELIVERED, CANCELLED, NOT_REQUIRED)

LABELS: dict = {
    PENDING: 'Belum dialokasikan',
    ALLOCATED: 'Sudah dialokasikan',
    PICKING: 'Sedang diambil',
    PACKED: 'Sudah dikemas',
    AWAITING_SCANOUT: 'Menunggu scan-out',
    DISPATCHED: 'Sudah dikirim',
    DELIVERED: 'Diterima pembeli',
    CANCELLED: 'Dibatalkan',
    NOT_REQUIRED: 'Tidak perlu diproses gudang',
}


def canon(value) -> str:
    """Kembalikan status kanonik dari nilai apa pun (termasuk alias warisan)."""
    v = str(value or '').strip().lower()
    if v in ALIASES:
        return ALIASES[v]
    return v if v in FULFILLMENT_STATUSES else PENDING


def label(value) -> str:
    return LABELS.get(canon(value), str(value or ''))


def in_queue(value) -> bool:
    """Apakah status ini berarti gudang masih punya pekerjaan?"""
    return str(value or '').strip().lower() in {s.lower() for s in QUEUE_STATES}


def queue_filter(status: str | None = None) -> dict:
    """Fragment query MongoDB untuk antrean gudang.

    Satu-satunya tempat daftar status antrean ditulis. `status` boleh berupa
    kanonik ATAU alias — keduanya dicocokkan supaya penyaring di layar tidak
    kehilangan baris warisan.
    """
    if status:
        c = canon(status)
        wanted = {c} | {k for k, v in ALIASES.items() if v == c and isinstance(k, str) and k}
        return {'fulfillment_status': {'$in': sorted(wanted)}}
    return {'fulfillment_status': {'$in': list(QUEUE_STATES)}}


def initial_status(order: dict) -> tuple:
    """Status fulfillment AWAL untuk pesanan hasil impor → ``(status, alasan)``.

    Diturunkan dari status platform (bukan satu nilai untuk semua) supaya:
      * pesanan yang memang **perlu dikirim** masuk antrean gudang, dan
      * riwayat yang sudah **selesai/dibatalkan** tidak membanjiri antrean.

    Berkas ini tidak memesan stok — impor tetap tidak menyentuh reservasi.
    """
    st = str((order or {}).get('status') or '').strip().lower()
    if st in ('cancelled', 'canceled'):
        return CANCELLED, 'pesanan dibatalkan di platform'
    if st == 'returned':
        return CANCELLED, 'pesanan diretur di platform'
    rank = STATUS_RANK.get(st)
    if rank is None:
        return PENDING, f"status platform '{st or '(kosong)'}' tidak dikenal — dimasukkan antrean agar terlihat"
    if rank <= 2:      # new · paid · packed  ⇒ barang belum keluar
        return PENDING, 'platform menyatakan pesanan masih perlu dikirim'
    return NOT_REQUIRED, 'platform menyatakan pesanan sudah dikirim/selesai'


def line_is_linked(line: dict) -> bool:
    """Apakah baris pesanan menunjuk barang gudang yang sah?"""
    return bool((line or {}).get('fg_material_id'))


def order_linkage(order: dict) -> dict:
    """Ringkas kesiapan sebuah pesanan untuk dikerjakan gudang.

    Return ``{lines, linked, unlinked, ready, pcs, pcs_linked, unmapped_skus[]}``.
    `ready=True` berarti SEMUA barisnya menunjuk master FG ⇒ gudang bisa langsung
    mengalokasikan. Kalau tidak, layar harus mengatakan **apa** yang kurang —
    bukan menampilkan daftar kosong.
    """
    lines = list((order or {}).get('items') or [])
    if not lines:
        has = bool((order or {}).get('fg_material_id'))
        qty = float((order or {}).get('quantity') or 0)
        return {'lines': 1 if (order or {}) else 0, 'linked': 1 if has else 0,
                'unlinked': 0 if has else 1, 'ready': has,
                'pcs': qty, 'pcs_linked': qty if has else 0.0,
                'unmapped_skus': [] if has else [str((order or {}).get('sku_id') or '')]}
    linked = 0
    pcs = pcs_linked = 0.0
    unmapped = []
    for ln in lines:
        q = float((ln or {}).get('quantity') or (ln or {}).get('qty') or 0)
        pcs += q
        if line_is_linked(ln):
            linked += 1
            pcs_linked += q
        else:
            psid = str((ln or {}).get('platform_sku_id') or '').strip()
            if psid:
                unmapped.append(psid)
    return {'lines': len(lines), 'linked': linked, 'unlinked': len(lines) - linked,
            'ready': linked == len(lines) and len(lines) > 0,
            'pcs': round(pcs, 2), 'pcs_linked': round(pcs_linked, 2),
            'unmapped_skus': unmapped}
