"""dewi_rnd — Padankan Ukuran: petakan ukuran R&D "belum dipadankan" ke master produksi.

Kenapa layar ini ada (konsekuensi kebijakan B1 yang dijanjikan akan dilaporkan):
ukuran R&D sengaja dibiarkan **teks bebas** (keputusan owner #3), tapi PO produksi
internal MEWAJIBKAN `size_id` yang sah (`production_internal_adapter.validate_internal_item`
→ HTTP 400). Ukuran yang tidak punya padanan di master `rahaza_sizes` karena itu
**menghentikan alur R&D → PO** sampai seseorang memetakannya manual.

DAN ada kerusakan yang lebih mahal, sudah DIBUKTIKAN lewat
`scripts/poc_rnd_size_promotion.py` (jalankan sendiri untuk melihat):
promosi style ke produksi dulu memanggil `ensure_size(code=<label mentah>)`
sehingga label bebas mencemari MASTER ukuran:

    'All Size'  → master baru berkode 'ALL SIZE'  (padahal 'ALLSIZE' SUDAH ADA) ⇒ KEMBAR
    '2XL'       → master baru '2XL'               (padahal 'XXL' sudah ada)     ⇒ satu ukuran dua kode
    '28/30'     → master berkode '28/30'          ⇒ SKU FG jadi 'STYLE-NVY-28/30'

Karena itu perbaikannya SEPASANG, bukan hanya layar ini:
  · `utils.variant_ssot.resolve_master_size()` — SATU pintu pemadanan, dipakai
    layar (`build_size_map`) **dan** promosi (`promote_rnd_variants_to_master`),
    jadi keduanya tidak mungkin berbeda pendapat lagi.
  · layar ini — tempat manusia memutuskan padanan yang tidak bisa ditebak mesin.

Endpoint:
  · `GET  /api/dewi/rnd/size-mapping`        — semua label ukuran yang belum
                                               dipadankan (dari `size_list` style
                                               **dan** dari `dewi_rnd_variants.sizes`
                                               hasil impor Excel), + SARAN padanan
  · `POST /api/dewi/rnd/size-mapping/apply`  — padankan satu/beberapa label
  · `POST /api/dewi/rnd/size-mapping/auto`   — SEKALI KLIK: pakai saran bila ada,
                                               sisanya dibuatkan di master

Yang **TIDAK** dilakukan: mengubah `size_list` style. Ukuran tetap teks bebas milik
style — yang ditambahkan hanyalah `size_id` sebagai petunjuk di `size_map` (dan
`aliases[]` di master), persis kebijakan B1.
"""
from fastapi import Depends, HTTPException, Query
from database import get_db
from auth import require_auth
from routes.dewi_rnd_shared import router, now_utc, serialize
from routes.dewi_rnd_sizes import build_size_map, DEFAULT_SIZE_LIST, _clean_size_list
from utils.variant_ssot import (
    ensure_size, norm_size_key, resolve_master_size, size_alias_keys,
)

MAX_LABEL_LEN = 40


def _norm(label) -> str:
    """Kunci pembanding — SATU definisi dengan promosi (`norm_size_key`)."""
    return norm_size_key(label)


async def _master_sizes(db) -> list:
    rows = await db.rahaza_sizes.find({}, {'_id': 0}).sort('order_seq', 1).to_list(500)
    return [r for r in rows if r.get('active', True) is not False]


def _suggest(label: str, master: list) -> dict:
    """Saran padanan master untuk sebuah label. `reason` menjelaskan DASAR tebakannya.

    Sengaja hanya 3 dasar yang bisa dipertanggungjawabkan (kode / nama / alias baku).
    TIDAK ada pencocokan "mirip-mirip": salah menebak ukuran = salah potong kain.
    """
    key = _norm(label)
    if not key:
        return None
    for m in master:
        if _norm(m.get('code')) == key:
            return {**m, 'reason': 'kode master sama'}
    for m in master:
        if _norm(m.get('name')) == key:
            return {**m, 'reason': 'nama master sama'}
    for m in master:
        if key in {_norm(a) for a in (m.get('aliases') or [])}:
            return {**m, 'reason': f"sudah tercatat sebagai alias {m.get('code')}"}
    # alias baku lapangan (2XL ⇄ XXL, All Size ⇄ Free Size, …)
    candidates = size_alias_keys(label) - {key}
    for m in master:
        own = {_norm(m.get('code')), _norm(m.get('name'))}
        own.discard('')
        if own & candidates:
            return {**m, 'reason': f"alias umum garmen ({label} = {m.get('code')})"}
    return None


# ══════════════════════════════════════════════════════════════════════════════
# RINGKASAN — dipakai endpoint GET dan dipakai ulang internal oleh /auto.
# Fungsi biasa (bukan handler) supaya tidak pernah menerima objek `Query` FastAPI
# sebagai nilai default saat dipanggil dari Python.
# ══════════════════════════════════════════════════════════════════════════════

async def _collect_labels(db, style_id: str, limit: int) -> dict:
    """Kumpulkan label ukuran R&D + dari MANA asalnya.

    DUA sumber, karena keduanya benar-benar dipakai produksi:
      1. `dewi_rnd_styles.size_list` — daftar yang dipilih di layar (F2).
      2. `dewi_rnd_variants.sizes`   — yang BENAR-BENAR dipromosikan ke master.
         Importir Excel menulis ini langsung (115 varian nyata) dan labelnya bisa
         TIDAK ADA di `size_list` mana pun. Kalau layar ini hanya membaca
         `size_list`, varian hasil impor tetap mentok — itu setengah perbaikan.
    """
    q = {'id': style_id} if style_id else {}
    styles = await db.dewi_rnd_styles.find(
        q, {'_id': 0, 'id': 1, 'style_code': 1, 'style_name': 1,
            'size_list': 1, 'size_map': 1},
    ).to_list(limit)
    by_id = {s['id']: s for s in styles}

    # groups: kunci ternormalisasi → {label, styles:[…], from_size_list, from_variants}
    groups: dict = {}
    styles_with_list = 0

    def add(label, style, source):
        key = _norm(label)
        if not key:
            return
        g = groups.setdefault(key, {
            'label': str(label).strip(), 'styles': {},
            'from_size_list': False, 'from_variants': False,
        })
        g[source] = True
        if style:
            g['styles'][style['id']] = {
                'style_id': style['id'],
                'style_code': style.get('style_code', ''),
                'style_name': style.get('style_name', ''),
            }

    for st in styles:
        stored = _clean_size_list(st.get('size_list'))
        if stored:
            styles_with_list += 1
            for label in stored:
                add(label, st, 'from_size_list')

    vq = {'style_id': style_id} if style_id else {}
    variants = await db.dewi_rnd_variants.find(
        vq, {'_id': 0, 'style_id': 1, 'sizes': 1}).to_list(5000)
    for v in variants:
        st = by_id.get(v.get('style_id'))
        for s in (v.get('sizes') or []):
            label = s if isinstance(s, str) else (s or {}).get('size') or (s or {}).get('code')
            add(label, st, 'from_variants')

    return {'groups': groups, 'styles': styles,
            'styles_with_custom_size_list': styles_with_list,
            'variants_scanned': len(variants)}


async def _overview(db, style_id: str = None, limit: int = 500) -> dict:
    """Ringkasan ukuran R&D yang belum punya padanan di master produksi.

    Dikelompokkan **per label**, bukan per style — satu label seperti `'28/30'`
    biasanya dipakai beberapa style, jadi sekali dipadankan semuanya beres.
    """
    collected = await _collect_labels(db, style_id, limit)
    master = await _master_sizes(db)

    items, matched_items = [], []
    for g in collected['groups'].values():
        doc = await resolve_master_size(db, g['label'], allow_create=False)
        row = {
            'label': g['label'],
            'used_by_count': len(g['styles']),
            'styles': list(g['styles'].values()),
            'from_size_list': g['from_size_list'],
            'from_variants': g['from_variants'],
        }
        if doc:
            matched_items.append({**row, 'size_id': doc['id'], 'code': doc.get('code'),
                                  'name': doc.get('name')})
            continue
        s = _suggest(g['label'], master)
        items.append({
            **row,
            'suggestion': ({'size_id': s['id'], 'code': s.get('code'), 'name': s.get('name'),
                            'reason': s.get('reason')} if s else None),
            # tanpa saran ⇒ jalan keluarnya membuat ukuran itu di master
            'proposed_new_code': _norm(g['label'])[:10] or None,
        })

    items.sort(key=lambda x: (-x['used_by_count'], x['label']))
    matched_items.sort(key=lambda x: x['label'])

    return {
        'styles_checked': len(collected['styles']),
        'styles_with_custom_size_list': collected['styles_with_custom_size_list'],
        'variants_scanned': collected['variants_scanned'],
        'total_labels': len(collected['groups']),
        'unmatched_labels': len(items),
        'matched_labels': len(matched_items),
        'auto_matchable': len([i for i in items if i['suggestion']]),
        'need_new_master_size': len([i for i in items if not i['suggestion']]),
        'blocked_styles': len({s['style_id'] for i in items for s in i['styles']}),
        'master_sizes': [{'size_id': m['id'], 'code': m.get('code'), 'name': m.get('name'),
                          'aliases': m.get('aliases') or []} for m in master],
        'items': items,
        'matched': matched_items,
        'default_size_list': list(DEFAULT_SIZE_LIST),
        'why': ('PO produksi internal mewajibkan size_id yang sah. Ukuran yang belum '
                'dipadankan menghentikan alur R&D → PO, dan saat style dipromosikan '
                'ukuran itu membuat ukuran master BARU (master bisa kembar).'),
    }


@router.get('/size-mapping')
async def size_mapping_overview(
    style_id: str = None,
    limit: int = Query(500, ge=1, le=2000),
    user: dict = Depends(require_auth),
):
    """Daftar ukuran R&D yang belum dipadankan ke master produksi (+ saran)."""
    return serialize(await _overview(get_db(), style_id, limit))


# ══════════════════════════════════════════════════════════════════════════════
# TERAPKAN
# ══════════════════════════════════════════════════════════════════════════════

async def _remap_styles_for_label(db, label: str, user: dict) -> int:
    """Hitung ulang `size_map` semua style yang memakai label ini (master berubah)."""
    key = _norm(label)
    touched = 0
    cursor = db.dewi_rnd_styles.find({'size_list': {'$exists': True, '$ne': []}},
                                     {'_id': 0, 'id': 1, 'size_list': 1})
    async for st in cursor:
        sl = _clean_size_list(st.get('size_list'))
        if not any(_norm(s) == key for s in sl):
            continue
        size_map = await build_size_map(db, sl)
        await db.dewi_rnd_styles.update_one({'id': st['id']}, {'$set': {
            'size_map': size_map,
            'size_map_updated_at': now_utc(),
            'size_map_updated_by': user.get('name', ''),
        }})
        touched += 1
    return touched


async def _count_variants_for_label(db, label: str) -> int:
    """Berapa varian R&D yang memakai label ini (angka yang benar-benar ke produksi)."""
    key = _norm(label)
    n = 0
    async for v in db.dewi_rnd_variants.find({}, {'_id': 0, 'sizes': 1}):
        for s in (v.get('sizes') or []):
            lab = s if isinstance(s, str) else (s or {}).get('size') or (s or {}).get('code')
            if _norm(lab) == key:
                n += 1
                break
    return n


async def _apply_one(db, entry: dict, master: list, user: dict) -> dict:
    """Padankan SATU label. Dua jalan: pakai `size_id` master, atau buat di master."""
    label = str(entry.get('label') or '').strip()
    if not label:
        raise HTTPException(400, 'Label ukuran kosong — tidak ada yang bisa dipadankan.')
    if len(label) > MAX_LABEL_LEN:
        raise HTTPException(400, f"Label ukuran '{label[:20]}…' terlalu panjang.")

    size_id = str(entry.get('size_id') or '').strip()
    create_new = bool(entry.get('create_new'))
    target = None

    if size_id:
        target = await db.rahaza_sizes.find_one({'id': size_id}, {'_id': 0})
        if not target:
            raise HTTPException(404, f"Ukuran master untuk '{label}' tidak ditemukan.")
        # Master dibuat MENGENALI tulisan R&D-nya (mis. master 'XXL' + alias '2XL'),
        # supaya `resolve_master_size()` — yang juga dipakai promosi — langsung kena
        # tanpa perlu tabel alias terpisah.
        if _norm(label) not in {_norm(target.get('code')), _norm(target.get('name'))}:
            aliases = sorted(set(target.get('aliases') or []) | {label})
            await db.rahaza_sizes.update_one({'id': size_id}, {'$set': {
                'aliases': aliases, 'updated_at': now_utc()}})
            target = {**target, 'aliases': aliases}
        action = 'dipadankan ke master'
    elif create_new:
        code = _norm(entry.get('code') or label)[:10]
        if not code:
            raise HTTPException(
                400, f"Kode master untuk '{label}' tidak bisa diturunkan — isi kodenya.")
        dup = await db.rahaza_sizes.find_one({'code': code}, {'_id': 0})
        target = dup or await ensure_size(db, code=code, name=label)
        if not target:
            raise HTTPException(400, f"Gagal membuat ukuran master untuk '{label}'.")
        if not dup:
            await db.rahaza_sizes.update_one({'id': target['id']}, {'$set': {
                'aliases': [label] if _norm(label) != _norm(code) else [],
                'created_from': 'rnd_size_mapping',
                'created_from_label': label,
                'updated_at': now_utc()}})
        elif _norm(label) not in {_norm(dup.get('code')), _norm(dup.get('name'))}:
            await db.rahaza_sizes.update_one({'id': dup['id']}, {'$set': {
                'aliases': sorted(set(dup.get('aliases') or []) | {label}),
                'updated_at': now_utc()}})
        action = 'dipakai master yang sudah ada' if dup else 'ukuran baru dibuat di master'
    else:
        s = _suggest(label, master)
        if not s:
            raise HTTPException(
                400,
                f"'{label}' tidak punya saran padanan. Pilih ukuran master untuk label "
                f"ini, atau centang 'buat di master'.",
            )
        return await _apply_one(db, {'label': label, 'size_id': s['id']}, master, user)

    styles_touched = await _remap_styles_for_label(db, label, user)
    variants = await _count_variants_for_label(db, label)
    return {
        'label': label, 'action': action,
        'size_id': target['id'], 'code': target.get('code'), 'name': target.get('name'),
        'styles_updated': styles_touched,
        'variants_affected': variants,
    }


@router.post('/size-mapping/apply')
async def size_mapping_apply(body: dict, user: dict = Depends(require_auth)):
    """Padankan satu/beberapa label ukuran. Semua style yang memakainya ikut diperbarui.

    Body: `{"mappings": [{"label": "28/30", "create_new": true, "code": "2830"},
                         {"label": "2XL", "size_id": "<id master XXL>"}]}`
    Bentuk singkat satu baris juga diterima: `{"label": "2XL", "size_id": "…"}`.
    """
    db = get_db()
    mappings = body.get('mappings')
    if isinstance(body.get('label'), str):
        mappings = [body]
    if not isinstance(mappings, list) or not mappings:
        raise HTTPException(400, 'Tidak ada ukuran yang dipilih untuk dipadankan.')
    if len(mappings) > 200:
        raise HTTPException(400, 'Terlalu banyak ukuran sekaligus (maksimal 200).')

    master = await _master_sizes(db)
    results = []
    for m in mappings:
        results.append(await _apply_one(db, m or {}, master, user))
        master = await _master_sizes(db)   # master bisa bertambah → segarkan
    after = await _overview(db)
    return serialize({
        'ok': True,
        'applied': len(results),
        'styles_updated': sum(r['styles_updated'] for r in results),
        'variants_affected': sum(r['variants_affected'] for r in results),
        'unmatched_after': after['unmatched_labels'],
        'results': results,
    })


@router.post('/size-mapping/auto')
async def size_mapping_auto(body: dict = None, user: dict = Depends(require_auth)):
    """SEKALI KLIK: padankan semua yang punya saran; sisanya dibuatkan di master.

    Body opsional:
      · `{"create_missing": false}` — hanya pakai saran, jangan menambah master
        (supaya master ukuran tidak bertambah tanpa disengaja).
      · `{"style_id": "…"}`        — batasi ke satu style.
    """
    db = get_db()
    body = body or {}
    create_missing = body.get('create_missing', True)
    style_id = body.get('style_id')

    before = await _overview(db, style_id)
    master = await _master_sizes(db)

    done, skipped = [], []
    for it in before['items']:
        if it['suggestion']:
            done.append(await _apply_one(
                db, {'label': it['label'], 'size_id': it['suggestion']['size_id']}, master, user))
        elif create_missing:
            done.append(await _apply_one(
                db, {'label': it['label'], 'create_new': True,
                     'code': it['proposed_new_code']}, master, user))
        else:
            skipped.append(it['label'])
        master = await _master_sizes(db)

    after = await _overview(db, style_id)
    return serialize({
        'ok': True,
        'unmatched_before': before['unmatched_labels'],
        'applied': len(done),
        'skipped': skipped,
        'unmatched_after': after['unmatched_labels'],
        'styles_updated': sum(r['styles_updated'] for r in done),
        'variants_affected': sum(r['variants_affected'] for r in done),
        'results': done,
    })
