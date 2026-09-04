"""dewi_rnd — F2: daftar ukuran BEBAS per style (`dewi_rnd_styles.size_list`).

Latar (proposal §2.2, §B):
  · `DEFAULT_SIZES = ['XS','S','M','L','XL','XXL','2XL','3XL']` DI-HARDCODE di
    `RnDVariantModule.jsx:22` dan tidak ada tombol tambah/hapus ukuran.
  · Tech Pack punya `size_columns` bebas, TAPI `base_size`/`size_range` teks bebas
    dan `fabric_consumption.size` teks bebas ⇒ satu dokumen bisa memuat DUA daftar
    ukuran yang berbeda.

Keputusan owner #3: ukuran tetap **BEBAS**, tidak dikunci master `rahaza_sizes`.
Karena itu `size_list` adalah **data per style** (bukan kode, bukan master):
`['XS','S','M', 'All Size', '28/30', …]` — apa saja boleh.

Kebijakan **B1** (dipilih): tetap bebas, TAPI saat disimpan sistem mencocokkan
otomatis ke `rahaza_sizes` bila nama/kode-nya sama dan menyimpan `size_id` sebagai
**petunjuk opsional**. Yang tidak ketemu ditandai `matched:false` ("belum dipadankan").
Gunanya: PO produksi internal MEWAJIBKAN `size_id` yang sah
(`production_internal_adapter.py:53-56` → HTTP 400); dengan petunjuk ini alur
R&D → produksi tidak mentok, dan pengguna tidak dipaksa apa pun.

Semuanya ADITIF: style lama tanpa `size_list` tetap dapat daftar bawaan (fallback),
jadi tidak ada migrasi.
"""
import re
from fastapi import Depends, HTTPException
from database import get_db
from auth import require_auth
from routes.dewi_rnd_shared import router, now_utc, serialize
from utils.variant_ssot import resolve_master_size

# Fallback daftar ukuran lama (dulu di-hardcode di RnDVariantModule.jsx:22).
# Dipakai HANYA bila style belum pernah menyimpan `size_list`.
DEFAULT_SIZE_LIST = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '2XL', '3XL']


def _clean_size_list(raw) -> list:
    """Rapikan daftar ukuran: buang kosong, buang kembar (abaikan besar-kecil), URUTAN DIJAGA."""
    out, seen = [], set()
    for item in (raw or []):
        label = str(item.get('size') if isinstance(item, dict) else item or '').strip()
        if not label:
            continue
        key = re.sub(r'\s+', ' ', label).upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(label)
    return out


async def build_size_map(db, size_list: list) -> list:
    """B1 — padankan tiap ukuran ke master `rahaza_sizes` bila namanya/kodenya sama.

    Tidak pernah membuat ukuran baru di master dan tidak pernah menolak ukuran
    bebas; hanya menempelkan `size_id` sebagai petunjuk.

    2026-08-08 — pemadanan DIPINDAH ke `utils.variant_ssot.resolve_master_size()`
    supaya layar dan **promosi ke produksi** memakai logika yang SAMA. Sebelumnya
    keduanya punya aturan sendiri, sehingga layar bisa menampilkan "sudah
    dipadankan" sementara promosi tetap membuat ukuran master kembar
    (dibuktikan `scripts/poc_rnd_size_promotion.py` H2a). Efek samping yang
    disengaja: `aliases[]` master (diisi layar "Padankan Ukuran") kini ikut
    dikenali, jadi memadankan `'2XL'` → master `XXL` benar-benar membuat badge
    "belum dipadankan" hilang.
    """
    out = []
    for label in size_list:
        doc = await resolve_master_size(db, label, allow_create=False)
        out.append({
            'size': label,
            'size_id': (doc or {}).get('id'),
            'size_code': (doc or {}).get('code'),
            'size_name': (doc or {}).get('name'),
            'matched': doc is not None,
        })
    return out


def compute_size_range(size_list: list) -> str:
    """`size_range` DIHITUNG, tidak diketik (menutup tumpang tindih §2.2)."""
    sl = [s for s in (size_list or []) if str(s).strip()]
    if not sl:
        return ''
    if len(sl) == 1:
        return str(sl[0])
    return f'{sl[0]}-{sl[-1]}'


def pick_base_size(size_list: list, current=None) -> str:
    """`base_size` HARUS salah satu dari daftar (bukan teks bebas)."""
    sl = [s for s in (size_list or []) if str(s).strip()]
    if not sl:
        return str(current or '')
    if current:
        for s in sl:
            if str(s).strip().upper() == str(current).strip().upper():
                return s
    return sl[len(sl) // 2]


async def resolve_style_sizes(db, style_id: str) -> dict:
    """SATU sumber daftar ukuran untuk modal Varian DAN Tech Pack.

    Dipakai juga oleh `dewi_rnd_hpp.create/update_tech_pack` supaya
    `base_size`/`size_range`/kolom ukuran tidak bisa menyimpang lagi.
    """
    style = await db.dewi_rnd_styles.find_one({'id': style_id}, {'_id': 0}) if style_id else None
    stored = _clean_size_list((style or {}).get('size_list'))
    source = 'style' if stored else 'default'
    size_list = stored or list(DEFAULT_SIZE_LIST)
    size_map = (style or {}).get('size_map') if source == 'style' else None
    if not size_map or len(size_map) != len(size_list):
        size_map = await build_size_map(db, size_list)
    return {
        'style_id': style_id,
        'style_code': (style or {}).get('style_code', ''),
        'style_name': (style or {}).get('style_name', ''),
        'size_list': size_list,
        'size_map': size_map,
        'unmatched': [m['size'] for m in size_map if not m.get('matched')],
        'base_size': pick_base_size(size_list, (style or {}).get('base_size')),
        'size_range': compute_size_range(size_list),
        'source': source,
        'default_size_list': list(DEFAULT_SIZE_LIST),
    }


@router.get('/styles/{style_id}/size-list')
async def get_style_size_list(style_id: str, user: dict = Depends(require_auth)):
    """Daftar ukuran style ini (+ petunjuk pemadanan master B1).

    `source='default'` berarti style belum pernah menyimpan daftar sendiri dan
    sedang memakai daftar bawaan — layar boleh langsung menyuntingnya.
    """
    db = get_db()
    style = await db.dewi_rnd_styles.find_one({'id': style_id}, {'_id': 0})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan')
    return serialize(await resolve_style_sizes(db, style_id))


@router.put('/styles/{style_id}/size-list')
async def put_style_size_list(style_id: str, body: dict, user: dict = Depends(require_auth)):
    """Simpan daftar ukuran style (bebas). Kembar dibuang, urutan dijaga.

    `base_size` wajib salah satu isi daftar; `size_range` dihitung otomatis.
    """
    db = get_db()
    style = await db.dewi_rnd_styles.find_one({'id': style_id}, {'_id': 0})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan')

    size_list = _clean_size_list(body.get('size_list'))
    if not size_list:
        raise HTTPException(
            400,
            'Daftar ukuran tidak boleh kosong. Tambahkan minimal satu ukuran '
            '(boleh apa saja, mis. "All Size").',
        )
    if len(size_list) > 60:
        raise HTTPException(400, 'Terlalu banyak ukuran (maksimal 60).')

    size_map = await build_size_map(db, size_list)
    base_size = pick_base_size(size_list, body.get('base_size') or style.get('base_size'))
    upd = {
        'size_list': size_list,
        'size_map': size_map,
        'base_size': base_size,
        'size_range': compute_size_range(size_list),
        'size_list_updated_at': now_utc(),
        'size_list_updated_by': user.get('name', ''),
        'updated_at': now_utc(),
    }
    await db.dewi_rnd_styles.update_one({'id': style_id}, {'$set': upd})
    return serialize(await resolve_style_sizes(db, style_id))
