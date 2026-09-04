"""core/order_status.py — SSOT **satu-satunya penulis status order Toko + siklus reservasi stok**.

═══════════════════════════════════════════════════════════════════════════════
MASALAH NYATA YANG DITUTUP BERKAS INI  (F10 · dibuktikan `test_core_order_status_reservation.py`)
═══════════════════════════════════════════════════════════════════════════════
Sejak M10/K-8b, `POST /api/marketing/orders` **memesan stok** (`reserved_quantity`
naik di `rahaza_material_stock`) untuk SETIAP baris order. Pelepasannya ditulis
dengan benar di SATU tempat saja: ``PATCH /api/marketing/orders/{id}/status``.
Padahal ada **empat** jalur lain yang mengubah atau menghapus order — dan
semuanya melewati siklus reservasi::

    POST /api/marketing/orders/bulk-status      ← UI "Order Terpadu" → pilihan "Batal"
    DELETE /api/marketing/orders/{id}           ← tombol hapus order
    webhook marketplace (_maybe_create_order)   ← Shopee/Tokopedia mengabarkan 'cancelled'
    PATCH batal ⇒ lalu dibalik ke 'new'         ← dropdown status

Bukti (POC, angka sungguhan): stok jual `HDI-0001-ABU-L` 25 → order 2 pcs → 23 →
bulk-batal → **tetap 23**. Barangnya ada di gudang; sistem tidak akan pernah mau
menjualnya lagi; dan **tidak ada satu dokumen pun yang menjelaskan kenapa**.
Jalur `DELETE` lebih parah: dokumen ordernya ikut hilang, jadi ``reserved_rows``
— satu-satunya catatan *baris stok mana* yang dipesan — hilang bersamanya ⇒
mustahil dipulihkan tanpa membongkar seluruh koleksi. Itulah **stok hantu**.

═══════════════════════════════════════════════════════════════════════════════
KENAPA PENULISNYA HARUS SATU (PELAJARAN YANG SUDAH DIBAYAR REPO INI)
═══════════════════════════════════════════════════════════════════════════════
Persis pola `core/production_job_lifecycle.py::close_job()`: dua jalur menutup
job produksi, masing-masing menulis ``closed_at`` sendiri, dan salah satunya
suatu hari lupa ⇒ laporan yang jadi dasar tagihan CMT bohong tanpa ada yang tahu.
Perbaikannya bukan "hati-hati menulis di lima tempat", tetapi **memindahkan
aturannya ke satu berkas** lalu memasang gate yang memindai SELURUH DB
(RK-29 di sana; **KT-11…KT-14** di sini) sehingga jalur ke-enam yang lupa
memakainya akan MERAH sebelum sampai ke pemilik.

ATURAN KERAS
------------
1. **JANGAN** menulis ``marketing_orders.status`` dengan ``update_one``/``update_many``
   di route mana pun. Satu penulis: :func:`apply_status`.
2. **JANGAN** menghapus dokumen order tanpa :func:`release_for_delete` lebih dulu.
3. **JANGAN** menyalin daftar status penutup/terminal. Impor konstanta di bawah.
4. **JANGAN** menerima istilah status mentah marketplace sebagai status kanonik —
   pakai :func:`map_external_status` (istilah mentahnya disimpan di
   ``platform_status`` supaya audit tetap punya aslinya).

APA YANG *TIDAK* DILAKUKAN BERKAS INI (jujur, supaya tidak disalahpahami)
------------------------------------------------------------------------
Menandai order ``shipped``/``delivered`` **tidak** menurunkan on-hand dan tidak
membuat jurnal HPP. Pengurangan stok fisik + COGS hanya terjadi lewat alur gudang
(`/api/fulfillment/...` → scan-out). Order yang statusnya diputar-putar di modul
Toko saja akan **tetap menggenggam reservasinya** — itu memang mencegah
overselling, tetapi on-hand-nya jadi tidak jujur. Keadaan itu **dilaporkan**
(bukan diperbaiki diam-diam) oleh
``backend/migrations/repair_leaked_order_reservations.py --report``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

COLL = 'marketing_orders'

# Status kanonik order Toko. Tambahkan di SINI kalau alur baru butuh status baru.
ORDER_STATUSES: tuple = ('new', 'packed', 'shipped', 'delivered', 'cancelled', 'returned')

# Status yang berarti "order ini tidak akan jalan" ⇒ reservasi stoknya WAJIB dilepas
# supaya barangnya bisa dijual lagi.
RESERVATION_RELEASING_STATUSES: frozenset = frozenset({'cancelled', 'returned'})

# Status AKHIR. Order yang sudah di sini tidak boleh "dihidupkan" lagi: reservasinya
# sudah dilepas, jadi menghidupkannya = menjual barang yang sama dua kali.
TERMINAL_STATUSES: frozenset = frozenset({'cancelled', 'returned'})

# Reservasi tingkat-ALOKASI (dibuat `fulfillment/allocate`) hanya boleh dilepas
# selama barang BELUM benar-benar keluar gudang. Setelah dispatch, on-hand sudah
# turun; melepas reservasi di titik itu akan menciptakan stok palsu.
FULFILLMENT_RELEASABLE: frozenset = frozenset({'allocated', 'picking', 'packed_ready'})

# Istilah status mentah marketplace → status kanonik. Yang tidak dikenal
# TIDAK menyentuh status kanonik (lihat map_external_status).
EXTERNAL_STATUS_MAP: dict = {
    # pembatalan / penolakan
    'cancelled': 'cancelled', 'canceled': 'cancelled', 'cancel': 'cancelled',
    'rejected': 'cancelled', 'unpaid_expired': 'cancelled', 'expired': 'cancelled',
    'invoice_cancelled': 'cancelled',
    # retur
    'returned': 'returned', 'return': 'returned', 'refunded': 'returned',
    'return_refund_requested': 'returned',
    # perjalanan normal
    'new_order': 'new', 'pending': 'new', 'unpaid': 'new', 'payment_verified': 'new',
    'ready_to_ship': 'packed', 'packing': 'packed', 'processed': 'packed',
    'waiting_pickup': 'packed', 'awb_generated': 'packed',
    'shipped': 'shipped', 'in_transit': 'shipped', 'shipping': 'shipped',
    'delivered': 'delivered', 'completed': 'delivered', 'done': 'delivered',
}

# ── F3 (2026-08-13) — KOSAKATA STATUS EKSPOR MARKETPLACE ─────────────────────
# `marketing_orders` hasil IMPOR memakai dua istilah yang tidak ada di
# `ORDER_STATUSES`: **`paid`** ("Perlu dikirim" — sudah dibayar, belum dikirim)
# dan **`completed`** ("Selesai" — pembeli sudah menyelesaikan pesanan). Keduanya
# ditulis oleh commit impor F1 sejak awal, jadi menghapusnya sekarang akan
# membuat 559 pesanan nyata kehilangan artinya. Yang dilakukan di sini: mengakui
# keduanya SECARA TERTULIS di SSOT ini (bukan membiarkan setiap pembaca menebak),
# lengkap dengan URUTAN majunya supaya Ekspor B/C tidak bisa MEMUNDURKAN status.
IMPORT_ONLY_STATUSES: tuple = ('paid', 'completed')
STATUS_RANK: dict = {'new': 0, 'paid': 1, 'packed': 2, 'shipped': 3,
                     'delivered': 4, 'completed': 5}


def status_rank(status: str | None) -> int | None:
    """Urutan maju status, atau ``None`` bila status terminal/asing."""
    return STATUS_RANK.get(str(status or '').strip().lower())


def assert_forward(previous: str | None, requested: str, *,
                   cancel_evidence: bool = False) -> None:
    """Ekspor B/C tidak boleh MEMUNDURKAN status pesanan.

    Kenapa ini penting (F3): berkas fulfillment sering diekspor beberapa kali dan
    urutan barisnya tidak dijamin. Kalau baris lama boleh menimpa yang baru,
    pesanan yang sudah `delivered` bisa kembali menjadi `paid` hanya karena staf
    mengunggah ekspor kemarin — dan monitoring "belum dikirim" langsung memuat
    pesanan yang sebenarnya sudah sampai. Mundur DIIZINKAN hanya bila ada bukti
    pembatalan/retur (`cancelled_at` / `return_type_raw`), karena batal setelah
    selesai itu kejadian nyata.
    """
    prev_r, req_r = status_rank(previous), status_rank(requested)
    if prev_r is None or req_r is None:
        return                              # terminal/asing → guard lain yang bekerja
    if req_r < prev_r and not cancel_evidence:
        raise InvalidOrderTransition(
            str(previous or ''), requested,
            f"Berkas ini memundurkan status pesanan dari '{previous}' ke "
            f"'{requested}' tanpa bukti pembatalan/retur. Baris ditolak supaya "
            "pesanan yang sudah dikirim/selesai tidak kembali muncul di daftar "
            "'belum dikirim'. Ekspor ulang berkas terbaru bila memang ada koreksi.")



class InvalidOrderTransition(Exception):
    """Transisi status ditolak (mis. menghidupkan order yang sudah dibatalkan)."""

    def __init__(self, previous: str, requested: str, reason: str):
        self.previous = previous
        self.requested = requested
        self.reason = reason
        super().__init__(reason)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def map_external_status(raw: str | None) -> str | None:
    """Istilah marketplace → status kanonik, atau ``None`` bila tidak dikenal.

    Sengaja mengembalikan ``None`` (bukan menebak) supaya istilah asing tidak
    pernah menjadi nilai ``status``. Dulu webhook menulis apa saja apa adanya
    (`'unpaid'`, `'in_transit'`, `'completed'`) sehingga kartu ringkasan
    Baru/Dipacking/Dikirim/Terkirim tidak pernah menjumlahkan order itu.
    """
    key = str(raw or '').strip().lower().replace('-', '_').replace(' ', '_')
    if not key:
        return None
    if key in ORDER_STATUSES:
        return key
    return EXTERNAL_STATUS_MAP.get(key)


def check_transition(previous: str | None, requested: str) -> None:
    """Naikkan :class:`InvalidOrderTransition` bila transisi berbahaya.

    Aturannya SENGAJA minimal — hanya menutup lubang yang benar-benar bisa
    membuat barang terjual dua kali. Alur nyata terlalu beragam (marketplace
    kadang melompat `new → shipped`) untuk dipaksa satu jalur kaku; memaksanya
    hanya akan membuat staf mengakali sistem.

    Yang DILARANG: menghidupkan kembali order yang sudah `cancelled`/`returned`.
    Reservasinya sudah dilepas, jadi order itu akan "hidup" tanpa memesan stok
    apa pun ⇒ stok yang sama bisa dijanjikan ke pembeli lain (overselling).
    Kalau pembelinya memang memesan lagi, buat order BARU (reservasi baru).
    """
    prev = str(previous or '')
    if prev in TERMINAL_STATUSES and requested != prev:
        raise InvalidOrderTransition(
            prev, requested,
            f"Order sudah '{prev}' dan tidak bisa dihidupkan lagi ke '{requested}'. "
            'Reservasi stoknya sudah dilepas, jadi menghidupkannya berisiko '
            'menjual stok yang sama dua kali (overselling). '
            'Buat order BARU bila pembeli memesan ulang.')


def touched_catalog_item_ids(order: dict) -> set:
    """Semua item katalog yang tersentuh order ini (K-8b — bukan hanya baris pertama)."""
    ids = {order.get('catalog_item_id')}
    for ln in (order.get('items') or []):
        if isinstance(ln, dict):
            ids.add(ln.get('catalog_item_id'))
    for ln in (order.get('fulfillment_items') or []):
        if isinstance(ln, dict):
            ids.add(ln.get('catalog_item_id'))
    return {i for i in ids if i}


async def refresh_catalog_cache(db, item_ids) -> int:
    """Segarkan cache stok item katalog supaya layar langsung jujur setelah reservasi berubah."""
    from core import catalog_stock as _cstock

    n = 0
    for cid in {i for i in (item_ids or []) if i}:
        try:
            it = await db.marketing_catalog_items.find_one({'id': cid}, {'_id': 0})
            if it:
                await _cstock.sync_item_cache(db, it)
                n += 1
        except Exception:
            # Kegagalan menyegarkan CACHE tidak boleh menggagalkan pembatalan order
            # (stok jual sudah benar; cache dihitung ulang setiap layar dibaca),
            # tetapi WAJIB tercatat — dulu kelas kesalahan ini ditelan `pass`.
            logger.exception('[order-status] gagal menyegarkan cache stok item katalog %s', cid)
    return n


async def release_reservations(db, order: dict, *, reason: str = 'status_change') -> dict:
    """Lepas SEMUA reservasi yang masih digenggam ``order``. Idempoten.

    Tiga tempat reservasi bisa tercatat — ketiganya diperiksa, karena melewatkan
    salah satunya adalah persis bug yang membuat berkas ini ada:

    1. tingkat-ORDER  — ``order.reserved_rows`` (gabungan semua baris, K-8b);
    2. tingkat-BARIS  — ``order.items[].reserved_rows`` (rincian per produk);
    3. tingkat-ALOKASI — ``order.fulfillment_items[].reserved_rows``, HANYA bila
       ``fulfillment_status`` masih di :data:`FULFILLMENT_RELEASABLE`.

    Return: ``{'released': float, 'patch': dict, 'touched': set}`` —
    ``patch`` adalah fragmen ``$set`` yang harus ditulis bersama perubahan status.
    """
    from core import catalog_stock as _cstock

    released = 0.0
    patch: dict = {}
    touched = touched_catalog_item_ids(order)

    # (1) tingkat-ORDER. `reserved_rows` tingkat-order adalah GABUNGAN semua baris
    #     (K-8b), jadi satu panggilan sudah melepas seluruh order.
    order_level_rows = order.get('reserved_rows') or []
    order_level_done = False
    if order_level_rows:
        released += await _cstock.release_rows(db, order_level_rows)
        order_level_done = True
    if order_level_done or order.get('stock_reserved'):
        patch.update({'stock_reserved': False, 'reserved_qty': 0.0, 'reserved_rows': []})

    # (2) tingkat-BARIS. WAJIB tidak melepas dua kali: kalau gabungan tingkat-order
    #     sudah dilepas, baris hanya dibersihkan jejaknya. Melepas dua kali akan
    #     menurunkan `reserved_quantity` melewati batas dan **membebaskan
    #     reservasi order LAIN** (stok yang sama dijanjikan ke dua pembeli).
    lines = order.get('items') or []
    if any(isinstance(ln, dict) and ln.get('reserved_rows') for ln in lines):
        for ln in lines:
            if not isinstance(ln, dict):
                continue
            if not order_level_done:
                # order warisan: gabungan tingkat-order kosong, jadi baris inilah
                # satu-satunya catatan reservasi yang nyata.
                released += await _cstock.release_rows(db, ln.get('reserved_rows') or [])
            ln['reserved_rows'] = []
            ln['reserved_qty'] = 0.0
            ln['reservation_released'] = True
        patch['items'] = lines

    fstat = str(order.get('fulfillment_status') or '')
    if fstat in FULFILLMENT_RELEASABLE:
        fitems = order.get('fulfillment_items') or []
        for it in fitems:
            if not isinstance(it, dict):
                continue
            released += await _cstock.release_rows(db, it.get('reserved_rows') or [])
            it['reserved_rows'] = []
            it['reservation_released'] = True
        if fitems:
            patch['fulfillment_items'] = fitems

    if patch:
        patch.update({'reservation_released_at': _now(),
                      'reservation_released_qty': round(released, 4),
                      'reservation_released_reason': reason})
    return {'released': round(released, 4), 'patch': patch, 'touched': touched}


async def apply_status(db, order, new_status: str, *, user: dict | None = None,
                       note: str | None = None, tracking_number: str | None = None,
                       source: str = 'api', platform_status: str | None = None,
                       extra: dict | None = None,
                       allow_import_vocab: bool = False,
                       forward_only: bool = False,
                       cancel_evidence: bool = False,
                       stamps: dict | None = None) -> dict:
    """**Satu-satunya** cara mengubah status order Toko. Idempoten & aman-stok.

    ``order`` boleh berupa ``order_id`` (str) atau dokumen order (dict).

    Yang dikerjakan, dalam satu tempat, untuk SEMUA pemanggil:
      * validasi status kanonik + guard transisi terminal (:func:`check_transition`);
      * stempel tanggal per status (``packed_date``/``shipped_date``/…) ditulis SERVER;
      * pelepasan reservasi bila status melepas (:func:`release_reservations`);
      * penyelarasan ``fulfillment_status`` saat order dibatalkan;
      * penyegaran cache stok SEMUA item katalog yang tersentuh;
      * jejak audit ``status_history[]`` (siapa, kapan, dari jalur mana).

    F3 (2026-08-13) — tiga argumen tambahan khusus jalur IMPOR fulfillment
    (Ekspor B/C), supaya impor tidak melahirkan penulis status kedua:
      * ``allow_import_vocab`` — terima juga ``paid``/``completed``
        (:data:`IMPORT_ONLY_STATUSES`) yang memang sudah dipakai dokumen impor F1;
      * ``forward_only`` — tolak baris yang MEMUNDURKAN status
        (:func:`assert_forward`), kecuali ``cancel_evidence=True``;
      * ``stamps`` — tanggal dari BERKAS (mis. ``{'shipped_date': dt}``) dipakai
        sebagai stempel, bukan jam server. Tanggal kirim yang benar adalah tanggal
        di ekspor platform; memakai jam impor membuat "umur pesanan" salah.

    Raise :class:`InvalidOrderTransition` (pemanggil → HTTP 400) atau ``KeyError``
    bila order tidak ada.
    """
    doc = order if isinstance(order, dict) else await db[COLL].find_one(
        {'id': order}, {'_id': 0})
    if not doc:
        raise KeyError(f'order {order!r} tidak ditemukan')

    allowed = ORDER_STATUSES + (IMPORT_ONLY_STATUSES if allow_import_vocab else ())
    if new_status not in allowed:
        raise InvalidOrderTransition(
            str(doc.get('status') or ''), new_status,
            f"Status '{new_status}' tidak dikenal. Pilih: {', '.join(allowed)}")

    previous = str(doc.get('status') or '')
    check_transition(previous, new_status)
    if forward_only:
        assert_forward(previous, new_status, cancel_evidence=cancel_evidence)

    now = _now()
    actor = (user or {}).get('email') or (user or {}).get('name') or 'system'
    update: dict = {'status': new_status, 'updated_at': now, 'updated_by': actor}
    if note:
        update['note'] = note
    if tracking_number:
        update['tracking_number'] = tracking_number
    if platform_status:
        update['platform_status'] = platform_status
    if new_status == 'packed':
        update['packed_date'] = now
    elif new_status == 'shipped':
        update['shipped_date'] = now
    elif new_status == 'delivered':
        update['delivered_date'] = now
    elif new_status == 'cancelled':
        update['cancelled_date'] = now
    elif new_status == 'returned':
        update['returned_date'] = now
    # F3 — tanggal dari BERKAS menimpa stempel jam server (lihat docstring).
    for k, v in (stamps or {}).items():
        if v:
            update[k] = v
    if extra:
        update.update(extra)

    released, touched = 0.0, touched_catalog_item_ids(doc)
    if new_status in RESERVATION_RELEASING_STATUSES:
        res = await release_reservations(db, doc, reason=f'status:{new_status}')
        released = res['released']
        update.update(res['patch'])
        touched |= res['touched']
        # Order yang dibatalkan tidak boleh tetap nongkrong di antrean gudang.
        if str(doc.get('fulfillment_status') or 'pending_fulfillment') in (
                {'pending_fulfillment'} | FULFILLMENT_RELEASABLE):
            update['fulfillment_status'] = 'cancelled'

    history = {'at': now, 'from': previous, 'to': new_status,
               'by': actor, 'source': source, 'released_qty': released}
    await db[COLL].update_one({'id': doc['id']},
                             {'$set': update, '$push': {'status_history': history}})

    if released or new_status in RESERVATION_RELEASING_STATUSES:
        await refresh_catalog_cache(db, touched)

    # ── F2/F5 (2026-08-13) — REKAP HARIAN IKUT MENYUSUL PERUBAHAN STATUS ──────
    # Rekap harian & siklus adalah TURUNAN dari pesanan: pesanan yang DIBATALKAN
    # tidak lagi dihitung sebagai omzet, dan yang DIRETUR masuk hitungan retur.
    # Sebelum hook ini, membatalkan pesanan dari layar TIDAK mengubah omzet hari
    # itu — jadi rekap masih menghitung uang yang sudah tidak ada, dan angka rapat
    # tidak pernah kembali benar tanpa "Hitung Ulang" manual yang jarang diingat.
    # Kegagalan hitung ulang tidak membatalkan perubahan status (stok & jejaknya
    # sudah sah) tetapi WAJIB meninggalkan jejak terstruktur.
    if previous != new_status and doc.get('account_id'):
        try:
            from core import marketing_daily_rollup as _rollup
            await _rollup.recompute_for_orders(db, [doc['id']], actor=f'{source}:{actor}')
        except Exception:
            logger.warning('[order_status] rekap harian GAGAL dihitung ulang sesudah '
                           'status berubah order=%s account=%s %s→%s',
                           doc.get('order_id'), doc.get('account_id'),
                           previous, new_status, exc_info=True)

    return {'ok': True, 'order_id': doc['id'], 'order_ref': doc.get('order_id'),
            'previous_status': previous, 'new_status': new_status,
            'released': released, 'changed': previous != new_status,
            'touched_catalog_items': sorted(touched)}


async def release_for_delete(db, order: dict, *, source: str = 'delete') -> dict:
    """Lepas reservasi SEBELUM dokumen order dihapus — cegah "stok hantu".

    Ini jalur yang paling berbahaya kalau dilupakan: begitu dokumennya hilang,
    ``reserved_rows`` (catatan baris stok mana yang dipesan) hilang juga, jadi
    stok yang tertahan tidak bisa dipulihkan dengan cara yang aman.
    """
    res = await release_reservations(db, order, reason=f'{source}:before_delete')
    if res['released'] or res['patch']:
        # Tulis dulu keadaan "sudah dilepas" supaya kalau penghapusan gagal di
        # tengah jalan, yang tertinggal adalah order tanpa reservasi (aman),
        # bukan reservasi tanpa order (stok hantu).
        await db[COLL].update_one({'id': order['id']}, {'$set': res['patch']})
    await refresh_catalog_cache(db, res['touched'])
    return res


def holds_reservation(order: dict) -> bool:
    """Order ini masih menggenggam reservasi? (dipakai gate & migrasi perbaikan)"""
    if not order:
        return False
    if order.get('stock_reserved') is True:
        return True
    if order.get('reserved_rows'):
        return True
    if _f(order.get('reserved_qty')) > 0:
        return True
    for ln in (order.get('items') or []):
        if isinstance(ln, dict) and ln.get('reserved_rows'):
            return True
    return False


def leak_query() -> dict:
    """Filter Mongo untuk order batal/retur yang MASIH menggenggam reservasi.

    Dipakai gate `INV-KATALOG` KT-11 **dan** migrasi perbaikan, supaya definisi
    "bocor" hanya ada di satu tempat.
    """
    return {
        'status': {'$in': sorted(RESERVATION_RELEASING_STATUSES)},
        '$or': [
            {'stock_reserved': True},
            {'reserved_rows.0': {'$exists': True}},
            {'items.reserved_rows.0': {'$exists': True}},
        ],
    }
