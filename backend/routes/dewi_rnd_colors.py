"""dewi_rnd — F1: Warna multi (FAN-OUT) + master warna inline + SKU kanonik.

Latar (memory/PROPOSAL_RND_WARNA_UKURAN_TECHPACK_HPP.md §A, §2.5):

1. R&D dulu adalah PULAU: warna varian ditulis sebagai TEKS BEBAS dan tidak pernah
   menyentuh master `rahaza_colors` yang dipakai produksi/gudang/marketing.
2. Modal "Tambah Varian" hanya bisa SATU warna per simpan.
3. `autoGenSKU()` di frontend memakai urutan `{STYLE}-{SIZE}-{COLOR}` sedangkan SSOT
   ERP memakai `{MODEL}-{COLOR}-{SIZE}` (`utils/variant_ssot.build_variant_sku`),
   dan memakai 3 huruf NAMA warna, bukan KODE master ⇒ SKU R&D tidak akan pernah
   cocok dengan SKU FG di gudang.
4. Varian kembar (style + warna sama) bisa dibuat diam-diam.

Modul ini menutup keempatnya TANPA mengubah bentuk data (nol migrasi):
  · `GET/POST /api/dewi/rnd/color-options`      — proxy tipis ke master warna
  · `POST   /api/dewi/rnd/variants/bulk`        — FAN-OUT N warna → N dokumen varian
  · `GET    /api/dewi/rnd/variants/sku-audit`   — laporan SKU yang tidak sesuai SSOT
  · `POST   /api/dewi/rnd/variants/{id}/fix-sku`— perbaiki SKU per baris (owner memutuskan)

CATATAN PENTING soal `color_code` (jebakan nyata di data lama):
  Frontend R&D lama menulis **HEX** ke field `color_code` (`color_code: '#ffffff'`),
  padahal SSOT memakai `color_code` sebagai **KODE master** (mis. `NVY`).
  Karena itu dokumen baru menulis KEDUANYA secara eksplisit:
    · `color_code` = KODE master (NVY)  → dipakai SKU & penyambungan ke SSOT
    · `color_hex`  = HEX (#1B2A5B)      → dipakai swatch di UI
  Pembaca lama tetap aman: `color`/`color_code` tetap ada. Fungsi bantu
  `hex_of_variant()` / `resolve_color_code()` menangani dokumen lama yang
  menyimpan hex di `color_code`.
"""
import re
from fastapi import Depends, HTTPException, Query, Request
from database import get_db
from auth import require_auth
from routes.dewi_rnd_shared import router, now_utc, sid, serialize
from utils.variant_ssot import build_variant_sku, ensure_color

# Role eksternal tidak boleh menyentuh master warna (selaras rahaza_variants._require_admin)
EXTERNAL_ROLES = ('cmt_vendor', 'vendor', 'klien_maklon')

HEX_RE = re.compile(r'^#?[0-9A-Fa-f]{3,8}$')


def _looks_hex(value) -> str:
    """Kembalikan hex ter-normalisasi bila `value` memang hex, selain itu ''."""
    v = str(value or '').strip()
    if not v:
        return ''
    if v.startswith('#') and HEX_RE.match(v):
        return v
    return ''


def _norm_code(value) -> str:
    """KODE master warna: huruf/angka saja, UPPERCASE. Hex ditolak (bukan kode)."""
    v = str(value or '').strip()
    if _looks_hex(v):
        return ''
    return re.sub(r'[^A-Z0-9]', '', v.upper())[:10]


def _derive_code(name: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', str(name or '').upper())[:3] or 'CLR'


def hex_of_variant(v: dict) -> str:
    """Hex untuk swatch: `color_hex` baru → `color_code` lama (bila hex) → default."""
    return _looks_hex((v or {}).get('color_hex')) or _looks_hex((v or {}).get('color_code')) or '#CCCCCC'


def _ci(value: str) -> dict:
    return {'$regex': f'^{re.escape(str(value or ""))}$', '$options': 'i'}


async def _assert_internal(user: dict):
    if (user.get('role') or '').lower() in EXTERNAL_ROLES:
        raise HTTPException(403, 'Master warna hanya boleh diubah staff internal.')
    return user


# ══════════════════════════════════════════════════════════════════════════════
# COLOR OPTIONS — proxy tipis ke master `rahaza_colors`
# ══════════════════════════════════════════════════════════════════════════════

async def _seed_colors_if_empty(db):
    """Pakai seeder master yang SUDAH ada supaya paletnya satu sumber."""
    if await db.rahaza_colors.count_documents({}) == 0:
        from routes.rahaza_variants import _ensure_colors
        await _ensure_colors(db)


@router.get('/color-options')
async def color_options(
    include_inactive: bool = False,
    user: dict = Depends(require_auth),
):
    """Daftar warna master untuk dropdown layar R&D (varian, material, tech pack).

    Sengaja proxy tipis: layar R&D tidak perlu tahu detail master, dan master
    tetap SATU (`rahaza_colors`) bersama produksi/gudang/marketing.
    """
    db = get_db()
    await _seed_colors_if_empty(db)
    q = {} if include_inactive else {'active': True}
    rows = await db.rahaza_colors.find(q, {'_id': 0}).sort('order_seq', 1).to_list(500)
    return [{
        'color_id': r.get('id'),
        'code': r.get('code') or '',
        'name': r.get('name') or '',
        'hex': r.get('hex') or '#CCCCCC',
        'active': bool(r.get('active', True)),
    } for r in rows]


@router.post('/color-options')
async def create_color_option(body: dict, user: dict = Depends(require_auth)):
    """Tambah warna BARU ke master langsung dari layar R&D (keputusan owner #2).

    Tujuannya menghilangkan bolak-balik menu: hasilnya langsung bisa dipilih di
    dropdown yang sama. Ditulis ke master `rahaza_colors` — bukan koleksi bayangan.
    """
    await _assert_internal(user)
    db = get_db()
    await _seed_colors_if_empty(db)

    name = str(body.get('name') or '').strip()
    if not name:
        raise HTTPException(400, 'Nama warna wajib diisi.')

    code = _norm_code(body.get('code')) or _derive_code(name)
    hex_val = _looks_hex(body.get('hex')) or '#CCCCCC'

    dup_code = await db.rahaza_colors.find_one({'code': code, 'active': True}, {'_id': 0})
    if dup_code:
        raise HTTPException(
            409,
            f"Kode warna '{code}' sudah dipakai warna '{dup_code.get('name')}'. "
            f"Pakai kode lain (mis. {code}2) atau pilih warna itu dari daftar.",
        )
    dup_name = await db.rahaza_colors.find_one({'name': _ci(name), 'active': True}, {'_id': 0})
    if dup_name:
        raise HTTPException(
            409,
            f"Warna '{name}' sudah ada di master dengan kode '{dup_name.get('code')}'. "
            f"Pilih dari daftar, tidak perlu dibuat ulang.",
        )

    doc = {
        'id': sid(), 'code': code, 'name': name, 'hex': hex_val,
        'order_seq': int(body.get('order_seq') or 50), 'active': True,
        'created_at': now_utc(), 'updated_at': now_utc(),
        'created_from': 'rnd',
    }
    await db.rahaza_colors.insert_one(doc)
    return {'color_id': doc['id'], 'code': code, 'name': name, 'hex': hex_val, 'active': True}


# ══════════════════════════════════════════════════════════════════════════════
# Resolusi warna & SKU kanonik
# ══════════════════════════════════════════════════════════════════════════════

async def _resolve_color(db, item: dict, *, allow_create: bool):
    """Padankan satu entri warna ke master. Return (master_doc, created_bool).

    Urutan: `color_id` → KODE → NAMA. Bila tidak ketemu dan `allow_create`,
    warna dibuat di master (lewat `ensure_color`, kode unik) supaya R&D tidak
    mentok — dan SSOT tetap terisi, bukan teks bebas yang menggantung.
    """
    cid = str(item.get('color_id') or '').strip()
    if cid:
        doc = await db.rahaza_colors.find_one({'id': cid}, {'_id': 0})
        if doc:
            return doc, False

    code = _norm_code(item.get('code') or item.get('color_code'))
    if code:
        doc = await db.rahaza_colors.find_one({'code': code}, {'_id': 0})
        if doc:
            return doc, False

    name = str(item.get('name') or item.get('color') or '').strip()
    if name:
        doc = await db.rahaza_colors.find_one({'name': _ci(name)}, {'_id': 0})
        if doc:
            return doc, False

    if not allow_create or not (name or code):
        return None, False

    hex_val = _looks_hex(item.get('hex') or item.get('color_hex')) or '#CCCCCC'
    doc = await ensure_color(db, name=name or code, code=code or None, hex_val=hex_val)
    return doc, True


async def resolve_color_code(db, variant: dict) -> str:
    """KODE master warna untuk sebuah dokumen varian R&D (menangani data lama)."""
    doc, _ = await _resolve_color(db, {
        'color_id': variant.get('color_id'),
        'code': variant.get('color_code'),
        'name': variant.get('color'),
    }, allow_create=False)
    if doc:
        return str(doc.get('code') or '')
    return _norm_code(variant.get('color_code'))


def canonical_sku(style_code: str, color_code: str, size: str) -> str:
    """SKU kanonik SSOT = {STYLE}-{COLOR_CODE}-{SIZE} (memperbaiki bug §2.5.1)."""
    return build_variant_sku(style_code, color_code, size)


def size_rows(variant: dict) -> list:
    """Baris ukuran sebuah varian sebagai list dict — TAHAN dua bentuk yang nyata ada.

    Importir Excel (`dewi_rnd_techpack_import.py`) menulis `sizes` sebagai daftar
    **STRING** (`['S','M','L']`), sedangkan layar Varian menulis daftar **DICT**
    (`[{size, sku, qty_plan}]`). `utils/variant_ssot.promote_rnd_variants_to_master`
    sudah lama menangani keduanya; pembaca baru wajib ikut, kalau tidak
    `sku-audit` meledak 500 pada data hasil impor sungguhan.
    """
    out = []
    for s in (variant.get('sizes') or []):
        if isinstance(s, str):
            out.append({'size': s, 'sku': '', 'qty_plan': 0})
        elif isinstance(s, dict):
            out.append(dict(s))
    return out


def _norm_sizes(rows, *, style_code: str, color_code: str) -> list:
    """Normalkan baris ukuran → [{size, sku, qty_plan}] dengan SKU kanonik bila kosong."""
    out, seen = [], set()
    for r in (rows or []):
        if isinstance(r, str):
            r = {'size': r}
        size = str((r or {}).get('size') or '').strip()
        if not size:
            continue
        key = size.upper()
        if key in seen:
            continue
        seen.add(key)
        sku = str(r.get('sku') or '').strip().upper()
        if not sku:
            sku = canonical_sku(style_code, color_code, size)
        try:
            qty = float(r.get('qty_plan') or 0)
        except (TypeError, ValueError):
            qty = 0.0
        out.append({'size': size, 'sku': sku, 'qty_plan': qty})
    return out


# ══════════════════════════════════════════════════════════════════════════════
# BULK FAN-OUT — N warna dalam satu kali simpan
# ══════════════════════════════════════════════════════════════════════════════

@router.post('/variants/bulk')
async def create_variants_bulk(body: dict, user: dict = Depends(require_auth)):
    """FAN-OUT: satu kali input N warna × M ukuran → N dokumen `dewi_rnd_variants`.

    Body:
      style_id (wajib)
      colors : [{color_id?, code?, name?, hex?}]  (wajib, ≥1)
      sizes  : ['XS','S',...]  ATAU [{size, sku?, qty_plan?}]
      matrix : { "<color_id ATAU code>": { "<size>": {sku?, qty_plan?} } }   (opsional)
      status, notes

    Kenapa fan-out (bukan satu dokumen `colors:[]`): bentuk data TIDAK berubah ⇒
    nol migrasi, semua pembaca lama aman, dan butirannya sama dengan SSOT
    `rahaza_model_variants` (warna × ukuran) ⇒ mudah disambung ke produksi.
    """
    db = get_db()

    style_id = str(body.get('style_id') or '').strip()
    if not style_id:
        raise HTTPException(400, 'Pilih style terlebih dahulu.')
    style = await db.dewi_rnd_styles.find_one({'id': style_id}, {'_id': 0})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan.')

    colors_in = body.get('colors') or []
    if not isinstance(colors_in, list) or len(colors_in) == 0:
        raise HTTPException(400, 'Tambahkan minimal satu warna.')

    style_code = str(body.get('style_code') or style.get('style_code') or '').strip()
    style_name = str(body.get('style_name') or style.get('style_name') or '').strip()

    # 1) Resolusi semua warna ke master + tolak kembar DI DALAM permintaan ini
    resolved, created_master, dup_in_req = [], [], []
    seen_ids = {}
    for item in colors_in:
        if isinstance(item, str):
            item = {'name': item}
        doc, was_created = await _resolve_color(db, item or {}, allow_create=True)
        if not doc:
            raise HTTPException(400, 'Ada baris warna yang masih kosong — isi nama warna atau pilih dari master.')
        if was_created:
            created_master.append({'color_id': doc['id'], 'code': doc.get('code'), 'name': doc.get('name')})
        if doc['id'] in seen_ids:
            dup_in_req.append(doc.get('name') or doc.get('code'))
            continue
        seen_ids[doc['id']] = True
        resolved.append(doc)

    if dup_in_req:
        raise HTTPException(
            409,
            'Warna kembar di dalam satu input: ' + ', '.join(sorted(set(dup_in_req)))
            + '. Hapus barisnya, satu warna cukup satu baris.',
        )

    # 2) Tolak warna yang SUDAH punya varian di style ini (memperbaiki bug §2.5.2)
    existing = await db.dewi_rnd_variants.find({'style_id': style_id}, {'_id': 0}).to_list(2000)
    taken = {}
    for ev in existing:
        ecode = await resolve_color_code(db, ev)
        if ev.get('color_id'):
            taken[str(ev['color_id'])] = ev.get('color') or ecode
        if ecode:
            taken['code:' + ecode] = ev.get('color') or ecode
        if ev.get('color'):
            taken['name:' + str(ev['color']).strip().lower()] = ev.get('color')

    clash = [
        d.get('name') or d.get('code') for d in resolved
        if d['id'] in taken
        or ('code:' + str(d.get('code') or '')) in taken
        or ('name:' + str(d.get('name') or '').strip().lower()) in taken
    ]
    if clash:
        raise HTTPException(
            409,
            f"Style {style_code} sudah punya varian untuk warna: " + ', '.join(sorted(set(clash)))
            + '. Edit varian yang sudah ada, atau hapus warna itu dari daftar.',
        )

    # 3) Matriks warna × ukuran
    sizes_in = body.get('sizes') or []
    matrix = body.get('matrix') or {}
    if not sizes_in:
        raise HTTPException(400, 'Daftar ukuran masih kosong — tambahkan minimal satu ukuran.')

    docs = []
    for cdoc in resolved:
        ccode = str(cdoc.get('code') or '')
        cell = matrix.get(cdoc['id']) or matrix.get(ccode) or {}
        rows = []
        for s in sizes_in:
            size = s if isinstance(s, str) else str((s or {}).get('size') or '')
            size = size.strip()
            if not size:
                continue
            ov = cell.get(size) or cell.get(size.upper()) or {}
            rows.append({'size': size, 'sku': ov.get('sku') or '', 'qty_plan': ov.get('qty_plan') or 0})
        docs.append({
            'id': sid(),
            'style_id': style_id,
            'style_code': style_code,
            'style_name': style_name,
            # SSOT: color_id = FK master, color_code = KODE master, color_hex = warna tampilan
            'color_id':   cdoc['id'],
            'color':      cdoc.get('name') or ccode,
            'color_code': ccode,
            'color_hex':  cdoc.get('hex') or '#CCCCCC',
            'sizes':      _norm_sizes(rows, style_code=style_code, color_code=ccode),
            'status':     body.get('status', 'active'),
            'notes':      body.get('notes', ''),
            'sku_convention': 'ssot',
            'created_by':      user['id'],
            'created_by_name': user.get('name', ''),
            'created_at': now_utc(),
            'updated_at': now_utc(),
        })

    if docs:
        await db.dewi_rnd_variants.insert_many([dict(d) for d in docs])

    return {
        'ok': True,
        'created_count': len(docs),
        'colors_added_to_master': created_master,
        'variants': [serialize(d) for d in docs],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SKU AUDIT — laporan "SKU tidak sesuai SSOT" + perbaiki per baris
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/variants/sku-audit')
async def variants_sku_audit(
    style_id: str = None,
    limit: int = Query(500, ge=1, le=2000),
    user: dict = Depends(require_auth),
):
    """Bandingkan SKU tersimpan vs SKU kanonik `{STYLE}-{COLOR_CODE}-{SIZE}`.

    SKU lama **TIDAK** diubah otomatis (bisa sudah tersebar di dokumen lain).
    Layar R&D menampilkan daftar ini + tombol perbaiki per baris supaya owner
    yang memutuskan.
    """
    db = get_db()
    q = {'style_id': style_id} if style_id else {}
    rows = await db.dewi_rnd_variants.find(q, {'_id': 0}).sort('created_at', -1).to_list(limit)

    items, drift_total, unmatched_color = [], 0, 0
    for v in rows:
        ccode = await resolve_color_code(db, v)
        style_code = str(v.get('style_code') or '')
        if not ccode:
            unmatched_color += 1
        detail, drift = [], 0
        for s in size_rows(v):
            size = str(s.get('size') or '')
            if not size:
                continue
            now_sku = str(s.get('sku') or '').strip().upper()
            want = canonical_sku(style_code, ccode, size) if ccode else ''
            ok = bool(want) and now_sku == want
            if now_sku and want and not ok:
                drift += 1
            detail.append({'size': size, 'sku_now': now_sku, 'sku_canonical': want, 'ok': ok})
        drift_total += drift
        if drift > 0 or not ccode:
            items.append({
                'variant_id': v.get('id'),
                'style_id': v.get('style_id'),
                'style_code': style_code,
                'color': v.get('color') or '',
                'color_code': ccode,
                'color_hex': hex_of_variant(v),
                'color_in_master': bool(ccode),
                'drift_count': drift,
                'rows': detail,
            })

    return {
        'convention': '{STYLE}-{COLOR_CODE}-{SIZE}',
        'checked_variants': len(rows),
        'drift_variants': len([i for i in items if i['drift_count'] > 0]),
        'drift_rows': drift_total,
        'colors_not_in_master': unmatched_color,
        'items': items,
    }


@router.post('/variants/{variant_id}/fix-sku')
async def fix_variant_sku(variant_id: str, user: dict = Depends(require_auth)):
    """Tulis ulang SKU satu varian mengikuti SSOT + lengkapi `color_id`/`color_code`."""
    db = get_db()
    v = await db.dewi_rnd_variants.find_one({'id': variant_id}, {'_id': 0})
    if not v:
        raise HTTPException(404, 'Varian tidak ditemukan.')

    cdoc, _ = await _resolve_color(db, {
        'color_id': v.get('color_id'), 'code': v.get('color_code'), 'name': v.get('color'),
        'hex': hex_of_variant(v),
    }, allow_create=True)
    if not cdoc:
        raise HTTPException(
            400,
            'Warna varian ini tidak bisa dipadankan ke master (nama warna kosong). '
            'Edit varian dan pilih warna dari daftar master dulu.',
        )

    ccode = str(cdoc.get('code') or '')
    style_code = str(v.get('style_code') or '')
    changed = []
    sizes = []
    for s in size_rows(v):
        row = dict(s)
        size = str(row.get('size') or '')
        if size:
            want = canonical_sku(style_code, ccode, size)
            if str(row.get('sku') or '').strip().upper() != want:
                changed.append({'size': size, 'from': row.get('sku') or '', 'to': want})
            row['sku'] = want
        sizes.append(row)

    await db.dewi_rnd_variants.update_one({'id': variant_id}, {'$set': {
        'sizes': sizes,
        'color_id': cdoc['id'],
        'color': v.get('color') or cdoc.get('name'),
        'color_code': ccode,
        'color_hex': hex_of_variant(v) if hex_of_variant(v) != '#CCCCCC' else (cdoc.get('hex') or '#CCCCCC'),
        'sku_convention': 'ssot',
        'updated_at': now_utc(),
    }})
    return {'ok': True, 'variant_id': variant_id, 'color_code': ccode, 'changed': changed,
            'changed_count': len(changed)}
