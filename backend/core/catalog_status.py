"""core/catalog_status.py — SATU-SATUNYA rumus status katalog (F4.1).

KENAPA BERKAS INI ADA
---------------------
Sebelum F4, "status" item katalog hanya `stock_status` (tersedia/rendah/habis) yang
dihitung dari stok. Itu menjawab pertanyaan gudang, **bukan** pertanyaan marketing:
*"produk ini sudah tayang di toko atau belum?"* Akibatnya di layar katalog, produk
yang **belum pernah diunggah ke marketplace** tampak persis sama dengan produk yang
sudah tayang dan sedang dijual — dan tidak ada satu pun cara memisahkannya. Rapat
lalu memakai daftar itu seolah semuanya sudah tayang.

Status di sini menggabungkan dua kenyataan yang berbeda:
  * `publish_state`  — keputusan MANUSIA (draft / published / rejected / archived),
    bukti tayangnya `platform_url`;
  * `available`      — stok jual dari SSOT `core/catalog_stock.item_sellable()`.

ATURAN YANG TIDAK BISA DINEGOSIASI (SSOT §4.1)
---------------------------------------------
`catalog_status` **TIDAK PERNAH DIKETIK**. Ia dihitung dari data setiap kali dibaca,
lalu disimpan sebagai *cache* (`catalog_status`, `catalog_status_reason`,
`catalog_status_at`) hanya untuk keperluan filter/indeks. Kalau cache berbeda dengan
hasil hitung, **hasil hitung yang benar** dan cache diperbarui — bukan sebaliknya.
Alasannya sederhana: status yang bisa diketik akan berbohong pada hari staf lupa
memperbaruinya, dan tidak ada yang bisa membuktikan angka mana yang benar.

Urutan keputusan (persis tabel SSOT §4.1):
| # | Syarat                                          | Hasil      |
|---|-------------------------------------------------|------------|
| 1 | `publish_state='archived'` atau `is_active=false`| NONAKTIF  |
| 2 | `publish_state='rejected'`                      | DITOLAK    |
| 3 | `publish_state='draft'`                         | DRAFT      |
| 4 | `published` DAN `is_preorder=true`              | PRE_ORDER  |
| 5 | `published` DAN `available > 0`                 | ACTIVE     |
| 6 | `published` DAN `available <= 0`                | HABIS      |
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional, Tuple

CATALOG_STATUSES = ('DRAFT', 'PRE_ORDER', 'ACTIVE', 'HABIS', 'NONAKTIF', 'DITOLAK')
PUBLISH_STATES = ('draft', 'published', 'rejected', 'archived')

# Label Bahasa Indonesia untuk layar (satu sumber, supaya 2 layar tidak menamai beda)
STATUS_LABEL = {
    'DRAFT': 'Draft (belum tayang)',
    'PRE_ORDER': 'Pre-order',
    'ACTIVE': 'Aktif (tayang & ada stok)',
    'HABIS': 'Habis (tayang, stok 0)',
    'NONAKTIF': 'Nonaktif / diarsipkan',
    'DITOLAK': 'Ditolak platform',
}
PUBLISH_LABEL = {
    'draft': 'Belum tayang',
    'published': 'Tayang',
    'rejected': 'Ditolak',
    'archived': 'Diarsipkan',
}

_URL_RE = re.compile(r'^https?://[^\s]+$', re.I)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_valid_url(url: str) -> bool:
    """URL bukti tayang harus http/https — bukan catatan bebas.

    Tanpa pemeriksaan ini, `platform_url` diisi hal-hal seperti "sudah tayang" atau
    nama toko, dan kolom "bukti tayang" berhenti menjadi bukti.
    """
    return bool(_URL_RE.match(str(url or '').strip()))


def publish_state_of(item: dict) -> str:
    """`publish_state` item, dengan pembacaan **defensif** untuk dokumen lama.

    Item yang lahir sebelum F4 tidak punya `publish_state` sama sekali. Menganggap
    semuanya 'draft' akan menyatakan ratusan produk yang JELAS sudah tayang (punya
    `platform_url`) sebagai belum tayang; menganggap semuanya 'published' lebih buruk
    lagi (mengarang bukti tayang). Karena itu: ada URL ⇒ 'published', tidak ada ⇒
    'draft'. Kesimpulan ini ditulis sekali ke dokumen oleh
    `migrations/2026_08_12_catalog_master_images.py` supaya tidak dihitung ulang
    selamanya, dan `publish_state_inferred=True` menandai barisnya agar layar bisa
    jujur bahwa nilainya turunan, bukan keputusan manusia.
    """
    st = str(item.get('publish_state') or '').strip().lower()
    if st in PUBLISH_STATES:
        return st
    return 'published' if str(item.get('platform_url') or '').strip() else 'draft'


def compute(item: dict, available: Optional[float]) -> Tuple[str, str]:
    """Kembalikan ``(catalog_status, alasan)`` — alasan WAJIB, bukan hiasan.

    `available` = hasil `core/catalog_stock.item_sellable()['available']`, atau
    ``None`` bila item belum tertaut ke master (stoknya memang tidak bisa dihitung).
    Item yang belum tertaut TIDAK boleh diklaim ACTIVE hanya karena tayang: tanpa
    tautan master, stok & HPP-nya tidak ada, jadi statusnya dilaporkan HABIS dengan
    alasan yang menyebutkan sebabnya.
    """
    item = item or {}
    state = publish_state_of(item)

    if state == 'archived' or item.get('is_active') is False:
        return 'NONAKTIF', ('Diarsipkan / dinonaktifkan — tidak ditawarkan lagi di toko.'
                            if state == 'archived'
                            else 'Item dinonaktifkan (is_active=false).')
    if state == 'rejected':
        why = str(item.get('rejected_reason') or '').strip()
        return 'DITOLAK', (f'Ditolak platform: {why}' if why
                           else 'Ditolak platform (alasan belum dicatat).')
    if state == 'draft':
        return 'DRAFT', ('Belum tayang di toko — belum ada URL produk sebagai bukti '
                         'tayang. Isi lewat tombol "Tayangkan".')

    # ── di sini pasti `published` ────────────────────────────────────────────────
    if item.get('is_preorder'):
        note = str(item.get('preorder_note') or '').strip()
        return 'PRE_ORDER', (f'Dijual pre-order: {note}' if note
                             else 'Dijual pre-order — stok belum harus ada.')
    if available is None:
        return 'HABIS', ('Tayang tetapi belum tertaut ke Master Produk, jadi stok jual '
                         'tidak bisa dihitung — anggap tidak bisa dikirim.')
    if float(available) > 0:
        return 'ACTIVE', f'Tayang & stok jual {float(available):g}.'
    return 'HABIS', 'Tayang tetapi stok jual 0 — berisiko pesanan tidak bisa dikirim.'


def cache_patch(item: dict, available: Optional[float]) -> dict:
    """Patch cache status untuk disimpan (dipakai saat tulis & saat baca)."""
    status, reason = compute(item, available)
    return {
        'catalog_status': status,
        'catalog_status_reason': reason,
        'catalog_status_at': _now(),
    }


def decorate(item: dict, available: Optional[float]) -> dict:
    """Tambahkan status + label + publish_state ke satu baris yang akan dikirim ke layar."""
    status, reason = compute(item, available)
    state = publish_state_of(item)
    out = dict(item)
    out['catalog_status'] = status
    out['catalog_status_reason'] = reason
    out['catalog_status_label'] = STATUS_LABEL.get(status, status)
    out['publish_state'] = state
    out['publish_state_label'] = PUBLISH_LABEL.get(state, state)
    out['publish_state_inferred'] = bool(
        str(item.get('publish_state') or '').strip().lower() not in PUBLISH_STATES)
    return out


def empty_by_status() -> dict:
    return {s: 0 for s in CATALOG_STATUSES}
