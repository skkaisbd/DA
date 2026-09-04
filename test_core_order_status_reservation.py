#!/usr/bin/env python3
"""test_core_order_status_reservation.py — POC Phase 1 · **F10**.

═══════════════════════════════════════════════════════════════════════════════
MASALAH YANG DIBUKTIKAN BERKAS INI
═══════════════════════════════════════════════════════════════════════════════
Reservasi stok order dilepas dengan BENAR hanya di SATU jalur
(`PATCH /api/marketing/orders/{id}/status`). Padahal ada **empat** jalur lain
yang mengubah/menghapus order, dan semuanya melewati siklus reservasi:

| Jalur                                             | Terpakai di UI?              | Akibat            |
|---------------------------------------------------|------------------------------|-------------------|
| `POST /api/marketing/orders/bulk-status`          | ya — "Order Terpadu" → Batal | reservasi BOCOR   |
| `DELETE /api/marketing/orders/{id}`               | ya — hapus order             | reservasi YATIM   |
| webhook marketplace (`_maybe_create_order`)       | ya — Shopee/Tokopedia batal  | reservasi BOCOR   |
| `PATCH` batal ⇒ lalu dibalik ke `new`             | ya — dropdown status         | OVERSELLING       |

"Bocor" artinya: `reserved_quantity` di `rahaza_material_stock` TETAP naik
walaupun ordernya sudah dibatalkan ⇒ stok jual turun **selamanya**. Barangnya
ada di gudang, tetapi sistem tidak akan pernah mau menjualnya lagi, dan tidak
ada satu dokumen pun yang menjelaskan kenapa. "Yatim" lebih parah: dokumen
ordernya ikut terhapus, jadi `reserved_rows` (satu-satunya catatan baris stok
mana yang dipesan) hilang bersamanya ⇒ mustahil dipulihkan tanpa hitung ulang
seluruh koleksi.

Skrip ini HTTP nyata, memakai fixture demo (`scripts/seed_katalog_order_demo.py`),
dan **mengembalikan stok ke angka semula** di akhir (jejak data uji = 0).

Pakai::

    python3 /app/test_core_order_status_reservation.py

Keluaran: PASS/FAIL per invarian + ringkasan. Exit code 0 = semua hijau.
"""
from __future__ import annotations

import os
import sys
import time
import uuid

import requests
from pymongo import MongoClient

BASE = os.environ.get('POC_BASE', 'http://localhost:8001')
MARK = 'POCORDSTATUS'
G, R, Y, X, BOLD, DIM = ('\033[92m', '\033[91m', '\033[93m', '\033[0m', '\033[1m', '\033[2m')

db = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
                 )[os.environ.get('DB_NAME', 'test_database')]
S = requests.Session()
OK: list = []
BAD: list = []


def chk(cond: bool, code: str, claim: str, detail: str = '') -> bool:
    if cond:
        OK.append(code)
        print(f'  {G}✓ {code}{X} {claim}' + (f'  {DIM}{detail}{X}' if detail else ''))
    else:
        BAD.append(code)
        print(f'  {R}✗ {code} {claim}{X}' + (f'  {Y}→ {detail}{X}' if detail else ''))
    return cond


def api(method: str, path: str, **kw):
    kw.setdefault('timeout', 60)
    return S.request(method, f'{BASE}{path}', **kw)


def j(r):
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# Pembacaan stok jual LIVE (angka yang harus kembali utuh setelah pembatalan)
# ══════════════════════════════════════════════════════════════════════════════
def live_available(sku: str) -> float:
    """Stok jual LIVE untuk satu SKU item katalog (lewat endpoint pemilih produk)."""
    d = j(api('GET', '/api/marketing/catalog-items/search',
              params={'q': sku, 'limit': 20}))
    for it in d.get('items') or []:
        if (it.get('sku') or '').upper() == sku.upper():
            return float(it.get('available') or 0)
    return -1.0


def pick_two_sellable() -> list:
    """Dua item katalog BERBEDA yang bisa dijual & stoknya cukup untuk uji."""
    d = j(api('GET', '/api/marketing/catalog-items/search',
              params={'only_sellable': 'true', 'limit': 50}))
    rows = [x for x in (d.get('items') or []) if float(x.get('available') or 0) >= 6]
    seen, out = set(), []
    for r in rows:
        key = r.get('fg_material_id') or r.get('sku')
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) == 2:
            break
    return out


def create_order(items: list, tag: str) -> tuple[int, dict]:
    """items = [(row, qty), ...] — pakai catalog_item_id supaya tautan sah (K-8a)."""
    body = {
        'platform': 'shopee',
        'customer_name': f'{MARK} {tag}',
        'items': [{'catalog_item_id': row['catalog_item_id'],
                   'sku_code': row['sku'],
                   'product_name': row['name'],
                   'qty': qty,
                   'price': float(row.get('harga_jual') or 0)} for row, qty in items],
    }
    r = api('POST', '/api/marketing/orders', json=body)
    return r.status_code, j(r)


def order_ids_of_test_data() -> list:
    return [d['id'] for d in db.marketing_orders.find(
        {'customer_name': {'$regex': f'^{MARK}'}}, {'_id': 0, 'id': 1})]


def cleanup() -> None:
    """Lepas reservasi yang masih tergantung LALU hapus order uji (jejak = 0).

    Sengaja memakai jalur PATCH (satu-satunya jalur yang PASTI melepas, baik
    sebelum maupun sesudah perbaikan) supaya skrip ini tidak pernah meninggalkan
    stok hantu di data demo — termasuk ketika ia sedang membuktikan bug.
    """
    for oid in order_ids_of_test_data():
        doc = db.marketing_orders.find_one({'id': oid}, {'_id': 0}) or {}
        if doc.get('stock_reserved') or any(
                (ln or {}).get('reserved_rows') for ln in (doc.get('items') or [])):
            api('PATCH', f'/api/marketing/orders/{oid}/status', json={'status': 'cancelled'})
    db.marketing_orders.delete_many({'customer_name': {'$regex': f'^{MARK}'}})
    db.marketing_webhook_events.delete_many({'payload.data.ordersn': {'$regex': f'^{MARK}'}})


def sync_catalog_cache() -> None:
    """Segarkan cache stok item katalog supaya `available` yang dibaca = LIVE."""
    time.sleep(0.4)


def main() -> int:  # noqa: C901
    print(f'{BOLD}POC F10 — SSOT status order + siklus reservasi stok{X}  ({BASE})\n')

    r = S.post(f'{BASE}/api/auth/login', timeout=30,
               json={'email': 'admin@garment.com', 'password': 'Admin@123'})
    if r.status_code != 200:
        print(f'  {R}login gagal HTTP {r.status_code}{X}')
        return 2
    S.headers.update({'Authorization': f"Bearer {j(r).get('token') or j(r).get('access_token')}"})

    cleanup()
    rows = pick_two_sellable()
    if not chk(len(rows) == 2, 'PC-0',
               'dua item katalog siap-jual tersedia untuk uji',
               f'ditemukan {len(rows)} — jalankan scripts/seed_katalog_order_demo.py'):
        return 1
    A, B = rows[0], rows[1]
    a0, b0 = live_available(A['sku']), live_available(B['sku'])
    print(f'  {DIM}baseline: {A["sku"]}={a0}  ·  {B["sku"]}={b0}{X}\n')

    try:
        # ── PC-1 (baseline yang SUDAH benar) — PATCH cancelled melepas reservasi ──
        code, d = create_order([(A, 2)], 'patch-cancel')
        oid = d.get('id')
        a1 = live_available(A['sku'])
        ok_create = chk(code == 201 and abs(a1 - (a0 - 2)) < 0.001, 'PC-1a',
                        'order 2 pcs memesan stok (stok jual turun 2)',
                        f'HTTP {code} · {a0} → {a1}')
        if ok_create:
            rp = api('PATCH', f'/api/marketing/orders/{oid}/status', json={'status': 'cancelled'})
            a2 = live_available(A['sku'])
            chk(rp.status_code == 200 and abs(a2 - a0) < 0.001, 'PC-1b',
                'PATCH batal ⇒ reservasi DILEPAS (stok jual kembali utuh)',
                f'HTTP {rp.status_code} · {a1} → {a2} (harus {a0})')

        # ── PC-2 — BULK cancel WAJIB melepas reservasi SEMUA order ────────────────
        c1, d1 = create_order([(A, 2)], 'bulk-1')
        c2, d2 = create_order([(B, 3)], 'bulk-2')
        ids = [x.get('id') for x in (d1, d2) if x.get('id')]
        a3, b3 = live_available(A['sku']), live_available(B['sku'])
        chk(c1 == 201 and c2 == 201 and abs(a3 - (a0 - 2)) < 0.001
            and abs(b3 - (b0 - 3)) < 0.001, 'PC-2a',
            'dua order (produk berbeda) memesan stok masing-masing',
            f'{A["sku"]} {a0}→{a3} · {B["sku"]} {b0}→{b3}')
        rb = api('POST', '/api/marketing/orders/bulk-status',
                 json={'order_ids': ids, 'status': 'cancelled'})
        a4, b4 = live_available(A['sku']), live_available(B['sku'])
        chk(rb.status_code == 200 and abs(a4 - a0) < 0.001 and abs(b4 - b0) < 0.001, 'PC-2b',
            'BULK batal ⇒ reservasi SEMUA order dilepas (stok jual kembali utuh)',
            f'HTTP {rb.status_code} · {A["sku"]} {a3}→{a4} (harus {a0}) · '
            f'{B["sku"]} {b3}→{b4} (harus {b0})')
        left = [o for o in db.marketing_orders.find(
            {'id': {'$in': ids}}, {'_id': 0, 'id': 1, 'status': 1, 'stock_reserved': 1})
            if o.get('stock_reserved')]
        chk(not left, 'PC-2c',
            'order yang dibatalkan massal tidak lagi menggenggam reservasi',
            f'masih menggenggam: {len(left)}')
        cleanup()

        # ── PC-3 — DELETE order WAJIB melepas reservasi (bukan stok yatim) ────────
        c3, d3 = create_order([(A, 2)], 'delete')
        oid3 = d3.get('id')
        a5 = live_available(A['sku'])
        rd = api('DELETE', f'/api/marketing/orders/{oid3}')
        a6 = live_available(A['sku'])
        chk(c3 == 201 and rd.status_code == 200 and abs(a6 - a0) < 0.001, 'PC-3',
            'HAPUS order ⇒ reservasi dilepas (tidak meninggalkan stok hantu)',
            f'HTTP {rd.status_code} · {a5} → {a6} (harus {a0})')
        cleanup()

        # ── PC-4 — webhook marketplace 'cancelled' WAJIB melepas reservasi ────────
        ordersn = f'{MARK}-WH-{uuid.uuid4().hex[:6].upper()}'
        c4, d4 = create_order([(A, 2)], 'webhook')
        oid4 = d4.get('id')
        # order yang datang dari marketplace/impor punya `platform_order_id`;
        # order manual belum, jadi kita sematkan supaya webhook menemukannya.
        db.marketing_orders.update_one({'id': oid4}, {'$set': {'platform_order_id': ordersn}})
        a7 = live_available(A['sku'])
        rw = api('POST', '/api/marketing/webhooks/manual', json={
            'platform': 'shopee', 'event_type': 'order.status',
            'payload': {'data': {'ordersn': ordersn, 'status': 'CANCELLED',
                                 'buyer_username': f'{MARK} buyer',
                                 'total_amount': 0, 'item_list': []}}})
        time.sleep(1.5)  # background task
        a8 = live_available(A['sku'])
        after = db.marketing_orders.find_one({'id': oid4}, {'_id': 0}) or {}
        chk(c4 == 201 and rw.status_code == 200 and abs(a8 - a0) < 0.001, 'PC-4a',
            "webhook marketplace 'cancelled' ⇒ reservasi dilepas",
            f'HTTP {rw.status_code} · {a7} → {a8} (harus {a0})')
        chk(after.get('status') in ('cancelled', 'returned'), 'PC-4b',
            'status order jadi status KANONIK (bukan istilah mentah marketplace)',
            f"status={after.get('status')!r} platform_status={after.get('platform_status')!r}")
        cleanup()

        # ── PC-5 — transisi terminal: batal TIDAK boleh dibalik ke 'new' ──────────
        c5, d5 = create_order([(A, 2)], 'transition')
        oid5 = d5.get('id')
        api('PATCH', f'/api/marketing/orders/{oid5}/status', json={'status': 'cancelled'})
        a9 = live_available(A['sku'])
        rt = api('PATCH', f'/api/marketing/orders/{oid5}/status', json={'status': 'new'})
        a10 = live_available(A['sku'])
        doc5 = db.marketing_orders.find_one({'id': oid5}, {'_id': 0}) or {}
        chk(c5 == 201 and rt.status_code == 400, 'PC-5a',
            "order BATAL tidak bisa dihidupkan lagi ke 'new' (ditolak 400)",
            f'HTTP {rt.status_code} — {str(j(rt).get("detail"))[:110]}')
        chk(doc5.get('status') == 'cancelled' and abs(a10 - a9) < 0.001, 'PC-5b',
            'penolakan transisi tidak meninggalkan order "hidup tanpa reservasi"',
            f"status={doc5.get('status')} stok {a9} → {a10}")
        cleanup()

        # ── PC-6 — idempoten: batal dua kali TIDAK melepas dua kali ───────────────
        c6, d6 = create_order([(A, 2)], 'idempotent')
        oid6 = d6.get('id')
        api('PATCH', f'/api/marketing/orders/{oid6}/status', json={'status': 'cancelled'})
        a11 = live_available(A['sku'])
        api('PATCH', f'/api/marketing/orders/{oid6}/status', json={'status': 'cancelled'})
        a12 = live_available(A['sku'])
        chk(c6 == 201 and abs(a11 - a0) < 0.001 and abs(a12 - a0) < 0.001, 'PC-6',
            'batal dua kali = idempoten (stok tidak naik melebihi angka semula)',
            f'{a11} lalu {a12} (harus {a0} keduanya)')
        cleanup()

        # ── PC-7 — pemindaian SELURUH DB: nol order batal/retur yang menggenggam ──
        leak = list(db.marketing_orders.find(
            {'status': {'$in': ['cancelled', 'returned']},
             '$or': [{'stock_reserved': True},
                     {'reserved_rows.0': {'$exists': True}}]},
            {'_id': 0, 'id': 1, 'order_id': 1, 'status': 1, 'reserved_qty': 1}))
        chk(not leak, 'PC-7',
            'NOL order batal/retur di seluruh DB yang masih menggenggam reservasi',
            f'bocor: {len(leak)} → {[x.get("order_id") for x in leak[:5]]}')

    finally:
        cleanup()
        aF, bF = live_available(A['sku']), live_available(B['sku'])
        chk(abs(aF - a0) < 0.001 and abs(bF - b0) < 0.001, 'PC-CLEAN',
            'stok jual kembali ke angka semula setelah pembersihan (jejak = 0)',
            f'{A["sku"]} {a0}→{aF} · {B["sku"]} {b0}→{bF}')
        chk(db.marketing_orders.count_documents(
            {'customer_name': {'$regex': f'^{MARK}'}}) == 0, 'PC-CLEAN2',
            'nol dokumen order uji tersisa')

    total = len(OK) + len(BAD)
    print(f'\n  POC F10: {G if not BAD else R}{BOLD}{len(OK)}/{total} LULUS{X}'
          + (f'  {R}{len(BAD)} GAGAL: {BAD}{X}' if BAD else f'  {G}— HIJAU{X}'))
    return 1 if BAD else 0


if __name__ == '__main__':
    sys.exit(main())
