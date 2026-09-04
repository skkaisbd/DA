"""core.cmt_vendor_master — **SSOT identitas vendor CMT** (F13, cacat HIGH FIN-3/CMT-3).

MASALAH YANG DISELESAIKAN BERKAS INI
------------------------------------
Ada DUA master vendor CMT yang lahir dari dua sejarah berbeda dan **tidak
beririsan sama sekali** (audit 2026-07-31 mencatat irisan id = 0):

* ``vendor_partners``    — master vendor produksi/maklon. Dipakai ``PO.vendor_id``,
  ``production_jobs.vendor_id``, ``vendor_shipments``, portal vendor, dan Rekap
  Harian/Mingguan CMT.
* ``dewi_cmt_partners``  — master Portal CMT (lifecycle) dan pembayaran CMT lama.

Akibatnya SATU kolom, ``dewi_cmt_payments.cmt_partner_id``, menyimpan id dari DUA
ruang-id berbeda: dokumen lama memakai id ``dewi_cmt_partners``, dokumen baru dari
`production_maklon_bridge` memakai id ``vendor_partners``. Konsekuensi yang bisa
dilihat pengguna, dan semuanya soal UANG:

1. **Tagihan hilang dari layar vendornya.** Portal CMT membaca
   ``{'cmt_partner_id': <id dewi_cmt_partners>}``; pembayaran yang tersimpan
   dengan id ``vendor_partners`` TIDAK cocok ⇒ halaman vendor menampilkan
   *outstanding Rp 0* padahal hutang jasa jahitnya ada. Tidak ada error, tidak ada
   baris kosong — angkanya hanya lebih kecil daripada kenyataan.
2. **Filter "per vendor" di layar Invoice membuang baris.** Pemilih vendor di
   layar memberi id ``vendor_partners``; baris yang tersimpan dengan id master
   lain lolos dari filter.
3. **Bukti "diinput staf DA" menguap.** Layar Invoice mencari
   ``production_jobs.vendor_id`` memakai id pembayaran. Kalau id itu dari master
   lain, tidak ada job yang cocok ⇒ kolom sumber pengisian jadi ``none`` dan
   keputusan owner (3a: harus KELIHATAN siapa yang mengetik angkanya) gagal
   tanpa suara.

APA YANG BERKAS INI BERIKAN
---------------------------
Satu tempat untuk pertanyaan "**vendor mana** yang dimaksud id ini", sehingga
tidak ada lagi endpoint yang menebak sendiri:

* :func:`alias_ids`        — semua id yang menunjuk vendor yang SAMA (kedua master).
* :func:`payment_filter`   — filter Mongo pembayaran CMT satu vendor, apa pun
  ruang-id yang tersimpan di dokumennya.
* :func:`canonical_id`     — id ``vendor_partners`` (SSOT) untuk sebuah id apa pun.
* :func:`canonical_map`    — versi BATCH untuk daftar pembayaran (2 query, bukan
  satu query per baris — layar Invoice bisa berisi ribuan baris).

KENAPA MENERJEMAHKAN, BUKAN MENGHAPUS SALAH SATU MASTER
-------------------------------------------------------
Menghapus ``dewi_cmt_partners`` berarti menulis ulang Portal CMT (lifecycle, DO,
QC, permak) dalam satu langkah besar di atas data uang yang sudah berjalan. Yang
dilakukan di sini justru pola yang sudah terbukti di repo ini: **satu penerjemah
tunggal** dipakai semua pembaca/penulis, ditambah migrasi yang menautkan kedua
master dua arah (``scripts/migrate_unify_cmt_vendor_master.py``). Hasilnya sama —
tidak ada lagi layar yang menghitung dengan master yang berbeda — tanpa jendela
waktu di mana pembayaran tidak bisa dibaca siapa pun.

Penulisan tetap satu arah dan jelas: ``vendor_id`` **selalu** id
``vendor_partners`` (lihat :func:`canonical_id`), ``cmt_partner_id`` hanya
cerminan untuk kompatibilitas dokumen lama.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

VP = 'vendor_partners'
CP = 'dewi_cmt_partners'

# Kolom pembayaran yang pernah dipakai menyimpan "vendor mana". Keduanya diperiksa
# saat mencari, karena riwayat dokumen memang berisi dua-duanya.
PAYMENT_VENDOR_KEYS = ('vendor_id', 'cmt_partner_id')


async def alias_ids(db, any_id: str) -> list[str]:
    """Semua id yang menunjuk vendor CMT yang SAMA, dari KEDUA master.

    Menerima id dari master mana pun (``vendor_partners`` atau
    ``dewi_cmt_partners``) dan mengembalikan daftar id yang setara — termasuk id
    yang dikirim. Aman dipakai walau migrasi penautan belum dijalankan: kalau
    tautannya belum ada, hasilnya hanya berisi id itu sendiri (perilaku lama),
    bukan error.
    """
    seed = (any_id or '').strip()
    if not seed:
        return []
    ids = {seed}

    # 1. id ini ada di master vendor produksi? ambil cerminan CMT-nya.
    vp = await db[VP].find_one({'id': seed}, {'_id': 0, 'id': 1, 'cmt_partner_id': 1})
    if vp and vp.get('cmt_partner_id'):
        ids.add(vp['cmt_partner_id'])

    # 2. id ini ada di master Portal CMT? ambil cerminan vendor produksinya.
    cp = await db[CP].find_one(
        {'id': seed}, {'_id': 0, 'id': 1, 'vendor_partner_id': 1, 'vendor_id': 1})
    if cp:
        for k in ('vendor_partner_id', 'vendor_id'):
            if cp.get(k):
                ids.add(cp[k])

    # 3. arah sebaliknya — dokumen master yang MENUNJUK id ini.
    async for d in db[CP].find({'$or': [{'vendor_partner_id': seed}, {'vendor_id': seed}]},
                               {'_id': 0, 'id': 1}):
        if d.get('id'):
            ids.add(d['id'])
    async for d in db[VP].find({'cmt_partner_id': seed}, {'_id': 0, 'id': 1}):
        if d.get('id'):
            ids.add(d['id'])

    return sorted(ids)


async def payment_filter(db, any_id: str) -> dict:
    """Filter Mongo ``dewi_cmt_payments`` untuk SATU vendor, lintas ruang-id.

    Dipakai menggantikan ``{'cmt_partner_id': vid}``. Perbedaannya bukan gaya:
    filter lama membuang pembayaran yang kolomnya berisi id master yang lain, dan
    yang terbuang itu adalah hutang jasa jahit.
    """
    ids = await alias_ids(db, any_id)
    if not ids:
        # Tidak ada id ⇒ filter yang MUSTAHIL cocok. Sengaja bukan ``{}``:
        # mengembalikan filter kosong akan menjumlahkan pembayaran SELURUH vendor
        # ke halaman satu vendor.
        return {'id': '__no_vendor__'}
    return {'$or': [{k: {'$in': ids}} for k in PAYMENT_VENDOR_KEYS]}


async def canonical_id(db, any_id: str) -> str:
    """Id ``vendor_partners`` (SSOT) untuk id apa pun; ``''`` bila tak terpetakan.

    Dipakai SAAT MENULIS supaya kolom ``vendor_id`` pada dokumen baru tidak
    pernah lagi berisi id master lain.
    """
    seed = (any_id or '').strip()
    if not seed:
        return ''
    if await db[VP].find_one({'id': seed}, {'_id': 1}):
        return seed
    cp = await db[CP].find_one(
        {'id': seed}, {'_id': 0, 'vendor_partner_id': 1, 'vendor_id': 1})
    for k in ('vendor_partner_id', 'vendor_id'):
        cand = (cp or {}).get(k)
        if cand and await db[VP].find_one({'id': cand}, {'_id': 1}):
            return cand
    vp = await db[VP].find_one({'cmt_partner_id': seed}, {'_id': 0, 'id': 1})
    if vp:
        return vp['id']
    logger.warning(
        '[cmt-vendor-master] id vendor CMT %s tidak terpetakan ke %s — dokumen '
        'uang bisa tidak muncul di layar vendornya. Jalankan '
        'scripts/migrate_unify_cmt_vendor_master.py', seed, VP)
    return ''


async def canonical_map(db, payments: list) -> dict:
    """``{payment_id: canonical_vendor_id}`` untuk BANYAK pembayaran sekaligus.

    Versi batch (2 query) karena layar Invoice memuat ribuan baris; satu query
    per baris akan membuat layar keuangan melambat seiring jumlah tagihan.
    Preferensi field mengikuti aturan SSOT: ``vendor_id`` dulu, ``cmt_partner_id``
    hanya sebagai cadangan dokumen lama.
    """
    raw: set = set()
    for p in payments or []:
        for k in PAYMENT_VENDOR_KEYS:
            if p.get(k):
                raw.add(p[k])
    if not raw:
        return {}

    ids = list(raw)
    vp_ids = {d['id'] async for d in db[VP].find({'id': {'$in': ids}}, {'_id': 0, 'id': 1})}
    # Peta id master CMT → id vendor_partners (dua arah tautan yang ada).
    cp_to_vp: dict = {}
    async for d in db[CP].find(
            {'$or': [{'id': {'$in': ids}}, {'vendor_partner_id': {'$in': ids}},
                     {'vendor_id': {'$in': ids}}]},
            {'_id': 0, 'id': 1, 'vendor_partner_id': 1, 'vendor_id': 1}):
        target = d.get('vendor_partner_id') or d.get('vendor_id') or ''
        if d.get('id') and target:
            cp_to_vp[d['id']] = target
    async for d in db[VP].find({'cmt_partner_id': {'$in': ids}},
                               {'_id': 0, 'id': 1, 'cmt_partner_id': 1}):
        cp_to_vp.setdefault(d['cmt_partner_id'], d['id'])

    def _resolve(one: str) -> str:
        if not one:
            return ''
        if one in vp_ids:
            return one
        return cp_to_vp.get(one, '')

    out = {}
    for p in payments or []:
        got = ''
        for k in PAYMENT_VENDOR_KEYS:
            got = _resolve(p.get(k) or '')
            if got:
                break
        out[p.get('id')] = got
    return out
