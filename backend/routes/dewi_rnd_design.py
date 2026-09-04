"""dewi_rnd — Dashboard + Variants + Patterns & Marking."""
from datetime import datetime
from fastapi import Depends, HTTPException, Query
from database import get_db
from auth import require_auth
from routes.dewi_rnd_shared import router, now_utc, sid, serialize
from routes.dewi_rnd_samples import RND_APPROVER_ROLES
from routes.shared import assert_can_act

# ──────────────────────────────────────────────────────────────────────────────
# DASHBOARD (Portal RnD)
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/dashboard')
async def get_rnd_dashboard(user: dict = Depends(require_auth)):
    """Comprehensive RnD Portal dashboard stats + recent activity"""
    db = get_db()

    total_styles    = await db.dewi_rnd_styles.count_documents({})
    active_styles   = await db.dewi_rnd_styles.count_documents({'status': 'active'})
    draft_styles    = await db.dewi_rnd_styles.count_documents({'status': 'draft'})
    # FIX B3: status 'review' TIDAK PERNAH ditulis flow RnD
    # (draft→pending_owner_review→approved_for_launch→active/promoted).
    # Hitung status yang benar-benar dipakai agar widget tidak basi (selalu 0).
    review_styles   = await db.dewi_rnd_styles.count_documents({'status': 'pending_owner_review'})
    approved_styles = await db.dewi_rnd_styles.count_documents({'status': 'approved_for_launch'})
    # NB: promote-to-production TIDAK mengubah status jadi 'promoted' (itu hanya nilai di response JSON);
    # sinyal promoted yang benar-benar ditulis ke DB adalah field 'promoted_to_model_id'.
    promoted_styles = await db.dewi_rnd_styles.count_documents({'promoted_to_model_id': {'$ne': None}})

    total_samples    = await db.dewi_rnd_sample_requests.count_documents({})
    pending_samples  = await db.dewi_rnd_sample_requests.count_documents({'status': 'submitted'})
    approved_samples = await db.dewi_rnd_sample_requests.count_documents({'status': 'approved'})
    rejected_samples = await db.dewi_rnd_sample_requests.count_documents({'status': 'rejected'})

    total_materials = await db.dewi_rnd_materials.count_documents({})
    total_revisions = await db.dewi_rnd_revisions.count_documents({})
    total_patterns  = await db.dewi_rnd_patterns.count_documents({})
    total_hpp       = await db.dewi_rnd_hpp.count_documents({})
    total_variants  = await db.dewi_rnd_variants.count_documents({})

    recent_samples = await db.dewi_rnd_sample_requests.find(
        {}, {'_id': 0}
    ).sort('created_at', -1).limit(5).to_list(5)

    recent_styles = await db.dewi_rnd_styles.find(
        {}, {'_id': 0}
    ).sort('created_at', -1).limit(5).to_list(5)

    recent_hpp = await db.dewi_rnd_hpp.find(
        {}, {'_id': 0}
    ).sort('created_at', -1).limit(5).to_list(5)

    def fmt(docs):
        result = []
        for d in docs:
            d2 = dict(d)
            for k, v in d2.items():
                if isinstance(v, datetime):
                    d2[k] = v.isoformat()
            result.append(d2)
        return result

    return {
        'kpi': {
            'total_styles':    total_styles,
            'active_styles':   active_styles,
            'draft_styles':    draft_styles,
            'review_styles':   review_styles,
            'approved_styles': approved_styles,
            'promoted_styles': promoted_styles,
            'pending_samples': pending_samples,
            'approved_samples':approved_samples,
            'rejected_samples':rejected_samples,
            'total_samples':   total_samples,
            'total_materials': total_materials,
            'total_revisions': total_revisions,
            'total_patterns':  total_patterns,
            'total_hpp':       total_hpp,
            'total_variants':  total_variants,
        },
        'recent_samples': fmt(recent_samples),
        'recent_styles':  fmt(recent_styles),
        'recent_hpp':     fmt(recent_hpp),
    }


# ──────────────────────────────────────────────────────────────────────────────
# VARIANTS (Color × Size per Style)
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/variants')
async def list_variants(
    style_id: str = None,
    user: dict = Depends(require_auth),
):
    db = get_db()
    q = {}
    if style_id:
        q['style_id'] = style_id
    docs = await db.dewi_rnd_variants.find(q, {'_id': 0}).sort('created_at', -1).to_list(500)
    return [serialize(d) for d in docs]


@router.post('/variants')
async def create_variant(body: dict, user: dict = Depends(require_auth)):
    """Buat SATU varian. Untuk banyak warna sekaligus pakai `POST /variants/bulk`.

    F1 (§2.5.2): dulu endpoint ini tidak memeriksa apa pun sehingga dua varian
    dengan style+warna SAMA bisa dibuat diam-diam. Sekarang kembar ditolak 409
    dengan pesan yang menyebut warnanya, dan warna dipadankan ke master supaya
    `color_code` berisi KODE master (bukan hex) untuk SKU kanonik.
    """
    db = get_db()
    from routes.dewi_rnd_colors import (
        _resolve_color, _norm_sizes, hex_of_variant, resolve_color_code,
    )

    style_id = body.get('style_id', '')
    if not style_id:
        raise HTTPException(400, 'Pilih style terlebih dahulu.')

    cdoc, _created = await _resolve_color(db, {
        'color_id': body.get('color_id'),
        'code': body.get('color_code'),
        'name': body.get('color'),
        'hex': body.get('color_hex') or body.get('color_code'),
    }, allow_create=True)
    if not cdoc:
        raise HTTPException(400, 'Isi nama warna (atau pilih dari master warna).')

    # Tolak varian kembar (style + warna) — bandingkan lewat master, bukan teks bebas.
    for ev in await db.dewi_rnd_variants.find({'style_id': style_id}, {'_id': 0}).to_list(2000):
        same = (
            (ev.get('color_id') and ev['color_id'] == cdoc['id'])
            or (await resolve_color_code(db, ev) == str(cdoc.get('code') or '') and cdoc.get('code'))
            or str(ev.get('color') or '').strip().lower() == str(cdoc.get('name') or '').strip().lower()
        )
        if same:
            raise HTTPException(
                409,
                f"Varian untuk warna '{cdoc.get('name')}' sudah ada di style ini. "
                f"Edit varian yang sudah ada, jangan buat kembar.",
            )

    ccode = str(cdoc.get('code') or '')
    style_code = body.get('style_code', '')
    doc = {
        'id':         sid(),
        'style_id':   style_id,
        'style_code': style_code,
        'style_name': body.get('style_name', ''),
        'color_id':   cdoc['id'],
        'color':      cdoc.get('name') or ccode,
        'color_code': ccode,
        'color_hex':  hex_of_variant({'color_hex': body.get('color_hex'),
                                      'color_code': body.get('color_code')})
                      if (body.get('color_hex') or body.get('color_code'))
                      else (cdoc.get('hex') or '#CCCCCC'),
        'sizes':      _norm_sizes(body.get('sizes', []), style_code=style_code, color_code=ccode),
        'status':     body.get('status', 'active'),
        'notes':      body.get('notes', ''),
        'sku_convention': 'ssot',
        'created_by':      user['id'],
        'created_by_name': user.get('name', ''),
        'created_at': now_utc(),
        'updated_at': now_utc(),
    }
    await db.dewi_rnd_variants.insert_one(doc)
    return serialize(doc)


@router.put('/variants/{variant_id}')
async def update_variant(variant_id: str, body: dict, user: dict = Depends(require_auth)):
    """Ubah satu varian. Kembar (style+warna) tetap ditolak, kecuali dirinya sendiri."""
    db = get_db()
    from routes.dewi_rnd_colors import _resolve_color, resolve_color_code

    existing = await db.dewi_rnd_variants.find_one({'id': variant_id}, {'_id': 0})
    if not existing:
        raise HTTPException(404, 'Variant tidak ditemukan')

    upd = {k: v for k, v in body.items() if k not in ('id', '_id', 'created_at', 'created_by')}

    # Bila warna disentuh, padankan ke master + jaga kembar.
    if any(k in body for k in ('color', 'color_code', 'color_id', 'color_hex')):
        cdoc, _created = await _resolve_color(db, {
            'color_id': body.get('color_id', existing.get('color_id')),
            'code': body.get('color_code', existing.get('color_code')),
            'name': body.get('color', existing.get('color')),
            'hex': body.get('color_hex', existing.get('color_hex')),
        }, allow_create=True)
        if not cdoc:
            raise HTTPException(400, 'Isi nama warna (atau pilih dari master warna).')
        style_id = body.get('style_id', existing.get('style_id'))
        for ev in await db.dewi_rnd_variants.find(
            {'style_id': style_id, 'id': {'$ne': variant_id}}, {'_id': 0}
        ).to_list(2000):
            same = (
                (ev.get('color_id') and ev['color_id'] == cdoc['id'])
                or (cdoc.get('code') and await resolve_color_code(db, ev) == str(cdoc.get('code')))
                or str(ev.get('color') or '').strip().lower() == str(cdoc.get('name') or '').strip().lower()
            )
            if same:
                raise HTTPException(
                    409,
                    f"Varian untuk warna '{cdoc.get('name')}' sudah ada di style ini.",
                )
        upd['color_id'] = cdoc['id']
        upd['color'] = cdoc.get('name') or str(cdoc.get('code') or '')
        upd['color_code'] = str(cdoc.get('code') or '')
        if body.get('color_hex'):
            upd['color_hex'] = body['color_hex']
        elif not existing.get('color_hex'):
            upd['color_hex'] = cdoc.get('hex') or '#CCCCCC'

    upd['updated_at'] = now_utc()
    res = await db.dewi_rnd_variants.update_one({'id': variant_id}, {'$set': upd})
    if res.matched_count == 0:
        raise HTTPException(404, 'Variant tidak ditemukan')
    return {'ok': True}


@router.delete('/variants/{variant_id}')
async def delete_variant(variant_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    res = await db.dewi_rnd_variants.delete_one({'id': variant_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Variant tidak ditemukan')
    return {'ok': True}


# ──────────────────────────────────────────────────────────────────────────────
# PATTERNS & MARKING (Dokumentasi Pola)
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/patterns')
async def list_patterns(
    style_id: str = None,
    search: str = None,
    user: dict = Depends(require_auth),
):
    db = get_db()
    q: dict = {}
    if style_id:
        q['style_id'] = style_id
    if search:
        q['$or'] = [
            {'pattern_code':  {'$regex': search, '$options': 'i'}},
            {'style_name':    {'$regex': search, '$options': 'i'}},
        ]
    docs = await db.dewi_rnd_patterns.find(q, {'_id': 0}).sort('created_at', -1).to_list(500)
    return [serialize(d) for d in docs]


@router.post('/patterns')
async def create_pattern(body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    doc = {
        'id':            sid(),
        'pattern_code':  body.get('pattern_code', ''),
        'style_id':      body.get('style_id', ''),
        'style_code':    body.get('style_code', ''),
        'style_name':    body.get('style_name', ''),
        'size_range':    body.get('size_range', ''),
        'total_pieces':  body.get('total_pieces', 0),
        'fabric_width':  body.get('fabric_width', 150),
        'fabric_usage_per_pcs': body.get('fabric_usage_per_pcs', 0.0),
        'hpp_fabric_per_pcs':   body.get('hpp_fabric_per_pcs', 0.0),
        'efficiency_pct':       body.get('efficiency_pct', 0.0),
        'marking_photo_url':    body.get('marking_photo_url', None),
        'pattern_file_url':     body.get('pattern_file_url', None),
        'notes':         body.get('notes', ''),
        'status':        body.get('status', 'draft'),
        'approved_by':   None,
        'approved_at':   None,
        'created_by':      user['id'],
        'created_by_name': user.get('name', ''),
        'created_at': now_utc(),
        'updated_at': now_utc(),
    }
    await db.dewi_rnd_patterns.insert_one(doc)
    return serialize(doc)


@router.put('/patterns/{pattern_id}')
async def update_pattern(pattern_id: str, body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    upd = {k: v for k, v in body.items() if k not in ('id', '_id', 'created_at', 'created_by')}
    upd['updated_at'] = now_utc()
    res = await db.dewi_rnd_patterns.update_one({'id': pattern_id}, {'$set': upd})
    if res.matched_count == 0:
        raise HTTPException(404, 'Pattern tidak ditemukan')
    return {'ok': True}


@router.post('/patterns/{pattern_id}/approve')
async def approve_pattern(pattern_id: str, user: dict = Depends(require_auth)):
    assert_can_act(user, 'rnd.approve', portal='rnd', legacy_roles=RND_APPROVER_ROLES,
                   what='menyetujui pola/marking')
    db = get_db()
    res = await db.dewi_rnd_patterns.update_one(
        {'id': pattern_id},
        {'$set': {
            'status': 'approved',
            'approved_by': user.get('name', ''),
            'approved_at': now_utc(),
            'updated_at': now_utc(),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, 'Pattern tidak ditemukan')
    return {'ok': True}


@router.delete('/patterns/{pattern_id}')
async def delete_pattern(pattern_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    res = await db.dewi_rnd_patterns.delete_one({'id': pattern_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Pattern tidak ditemukan')
    return {'ok': True}


# ── Marking Media Attachments (GAP-R4) ───────────────────────────────────────

@router.post('/patterns/{pattern_id}/attach-media')
async def attach_pattern_media(pattern_id: str, body: dict, user: dict = Depends(require_auth)):
    """Attach uploaded media (foto/video marking) to a pattern."""
    db = get_db()
    pat = await db.dewi_rnd_patterns.find_one({'id': pattern_id})
    if not pat:
        raise HTTPException(404, 'Pattern not found')

    media_item = {
        'attachment_id': body.get('attachment_id') or '',
        'storage_path':  body.get('storage_path') or '',
        'url':           body.get('url') or '',
        'content_type':  body.get('content_type') or '',
        'original_filename': body.get('original_filename') or '',
        'size':          int(body.get('size') or 0),
        'kind':          'video' if (body.get('content_type') or '').startswith('video') else 'photo',
        'uploaded_by':   user.get('name', ''),
        'uploaded_by_id': user.get('id', ''),
        'uploaded_at':   now_utc(),
    }
    media_list = pat.get('marking_media') or []
    media_list.append(media_item)
    await db.dewi_rnd_patterns.update_one(
        {'id': pattern_id},
        {'$set': {'marking_media': media_list, 'updated_at': now_utc()}},
    )
    media_item_resp = {**media_item, 'uploaded_at': media_item['uploaded_at'].isoformat()}
    return {'ok': True, 'media': media_item_resp, 'total_media': len(media_list)}


@router.delete('/patterns/{pattern_id}/media/{attachment_id}')
async def remove_pattern_media(
    pattern_id: str,
    attachment_id: str,
    user: dict = Depends(require_auth),
):
    db = get_db()
    pat = await db.dewi_rnd_patterns.find_one({'id': pattern_id})
    if not pat:
        raise HTTPException(404, 'Pattern not found')

    media_list = [m for m in (pat.get('marking_media') or []) if m.get('attachment_id') != attachment_id]
    await db.dewi_rnd_patterns.update_one(
        {'id': pattern_id},
        {'$set': {'marking_media': media_list, 'updated_at': now_utc()}},
    )
    return {'ok': True, 'total_media': len(media_list)}


# ──────────────────────────────────────────────────────────────────────────────
# KOKPIT APPROVAL RnD (2026-08-06)
#
# Owner: "ringkasan rnd juga tidak jelas, hanya cards yang besar sangat buruk
# secara ui ux dan fungsionalitasnya tidak ada padahal ini step lifecycle crusial
# yang butuh approve koordinasi antara staff rnd dengan manajement/executive."
#
# Endpoint approval-nya SUDAH ADA sejak lama tapi tidak pernah dipakai UI:
#   POST /styles/{id}/owner-approve · /owner-reject
#   POST /sample-requests/{id}/approve · /reject
#   POST /tech-packs/{id}/approve
# Endpoint di bawah menyatukan "apa saja yang menunggu keputusan" beserta umur
# tunggu (SLA) supaya manajemen bisa memutuskan dari satu layar.
# ──────────────────────────────────────────────────────────────────────────────
def _age_days(v) -> int:
    """Umur tunggu dalam hari dari nilai tanggal apa pun (datetime/str)."""
    if not v:
        return 0
    try:
        if isinstance(v, datetime):
            dt = v
        else:
            dt = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            from datetime import timezone as _tz
            dt = dt.replace(tzinfo=_tz.utc)
        from datetime import timezone as _tz2
        return max(0, (datetime.now(_tz2.utc) - dt).days)
    except (ValueError, TypeError):
        return 0


def _images(raw) -> list:
    """Samakan bentuk lampiran gambar: string URL atau objek {url|path|src}."""
    out = []
    for it in (raw or []):
        if isinstance(it, str):
            url, cap = it, ''
        elif isinstance(it, dict):
            url = it.get('url') or it.get('path') or it.get('src') or it.get('file_url') or ''
            cap = it.get('caption') or it.get('name') or it.get('label') or ''
        else:
            continue
        if url:
            out.append({'url': url, 'caption': cap})
    return out


def _sla(age: int, attention: int = 3, stale: int = 7) -> str:
    """Status antrean berdasarkan umur tunggu.

    Ambang `attention` (kuning) & `stale` (merah) diatur owner di
    `dewi_mgmt_alert_config` (layar Ringkasan Bisnis → Ambang Peringatan).
    Sebelum 2026-08-07 keduanya dipatok 3 & 7 hari di kode.
    """
    if stale >= 0 and age >= stale:
        return 'terlambat'
    if attention >= 0 and age >= attention:
        return 'perlu perhatian'
    return 'baru'


@router.get('/approvals/pending')
async def rnd_pending_approvals(user: dict = Depends(require_auth)):
    """Semua item RnD yang menunggu keputusan manajemen + umur tunggu.

    Bentuk seragam supaya UI bisa merender satu daftar keputusan:
      {kind, id, code, title, subtitle, requested_by, waiting_since, age_days,
       sla, approve_url, reject_url, reject_requires_notes}
    """
    db = get_db()
    items = []
    # Ambang SLA antrean (diatur owner) — dipakai untuk label & hitungan terlambat.
    from services.management_alerts import get_alert_config
    _cfg = await get_alert_config(db)
    att_days, stale_days = int(_cfg['rnd_attention_days']), int(_cfg['rnd_stale_days'])

    styles = await db.dewi_rnd_styles.find(
        {'status': 'pending_owner_review'}, {'_id': 0}).to_list(500)
    # Jumlah revisi per style → tombol "Bandingkan Revisi" di cockpit tahu ada riwayatnya.
    rev_counts = {}
    if styles:
        agg = db.dewi_rnd_revisions.aggregate([
            {'$match': {'style_id': {'$in': [s.get('id') for s in styles]}}},
            {'$group': {'_id': '$style_id', 'n': {'$sum': 1}}},
        ])
        rev_counts = {r['_id']: r['n'] async for r in agg}
    for s in styles:
        age = _age_days(s.get('submitted_for_review_at') or s.get('updated_at') or s.get('created_at'))
        items.append({
            'kind': 'style', 'kind_label': 'Style / Desain',
            'id': s.get('id'), 'code': s.get('style_code') or '-',
            'title': s.get('style_name') or '(tanpa nama)',
            'subtitle': ' · '.join([x for x in [
                s.get('rnd_type'), s.get('category'), s.get('fabric_type'),
                s.get('client_name') or s.get('buyer')] if x]) or '-',
            'requested_by': s.get('created_by_name') or s.get('created_by') or '-',
            'waiting_since': (s.get('submitted_for_review_at') or s.get('updated_at')),
            'age_days': age, 'sla': _sla(age, att_days, stale_days),
            # Detail supaya manajemen bisa memutuskan TANPA pindah layar.
            'detail': {
                'Deskripsi': s.get('description') or '-',
                'Jenis RnD': s.get('rnd_type') or '-',
                'Kategori': s.get('category') or '-',
                'Bahan': s.get('fabric_type') or '-',
                'Season': s.get('season') or '-',
                'Klien / Buyer': s.get('client_name') or s.get('buyer') or '-',
                'Jumlah Varian': len(s.get('variants') or []),
                'Jumlah Revisi': rev_counts.get(s.get('id'), 0),
                'Dibuat': s.get('created_at'),
            },
            'revisions_count': rev_counts.get(s.get('id'), 0),
            'images': _images(s.get('design_images')),
            'attachment_url': s.get('techpack_url') or '',
            'attachment_name': s.get('techpack_name') or '',
            'approve_url': f"/api/dewi/rnd/styles/{s.get('id')}/owner-approve",
            'reject_url': f"/api/dewi/rnd/styles/{s.get('id')}/owner-reject",
            'reject_requires_notes': True,
            'next_step': 'Setelah disetujui, style bisa dinaikkan menjadi model produksi.',
        })

    samples = await db.dewi_rnd_sample_requests.find(
        {'status': 'submitted'}, {'_id': 0}).to_list(500)
    for s in samples:
        age = _age_days(s.get('submitted_at') or s.get('updated_at') or s.get('created_at'))
        items.append({
            'kind': 'sample', 'kind_label': 'Permintaan Sample',
            'id': s.get('id'), 'code': s.get('request_code') or s.get('sample_code') or '-',
            'title': s.get('style_name') or s.get('product_name') or '(tanpa nama)',
            'subtitle': ' · '.join([str(x) for x in [
                s.get('sample_type'), s.get('client_name'),
                (f"PIC {s.get('sample_pic')}" if s.get('sample_pic') else None),
                (f"qty {s.get('qty') or s.get('quantity')}"
                 if (s.get('qty') or s.get('quantity')) else None)] if x]) or '-',
            'requested_by': s.get('requested_by_name') or s.get('created_by_name') or '-',
            'waiting_since': (s.get('submitted_at') or s.get('updated_at')),
            'age_days': age, 'sla': _sla(age, att_days, stale_days),
            'detail': {
                'Jenis Sample': s.get('sample_type') or '-',
                'Qty': s.get('qty') or s.get('quantity') or '-',
                'PIC / Pembuat Sample': s.get('sample_pic') or '(belum ditentukan)',
                'Target Selesai': s.get('due_date') or '-',
                'Klien': s.get('client_name') or '-',
                'Catatan': s.get('notes') or '-',
                'Dibuat': s.get('created_at'),
            },
            'images': _images(s.get('images') or s.get('photos') or s.get('reference_images')),
            'attachment_url': s.get('attachment_url') or '',
            'attachment_name': s.get('attachment_name') or '',
            'approve_url': f"/api/dewi/rnd/sample-requests/{s.get('id')}/approve",
            'reject_url': f"/api/dewi/rnd/sample-requests/{s.get('id')}/reject",
            'reject_requires_notes': False,
            'next_step': 'Setelah disetujui, sample dikerjakan lalu dihitung costing-nya.',
        })

    tps = await db.dewi_rnd_tech_packs.find(
        {'status': {'$in': ['draft', 'submitted', 'pending', 'pending_approval']}},
        {'_id': 0}).to_list(500)
    for t in tps:
        age = _age_days(t.get('updated_at') or t.get('created_at'))
        items.append({
            'kind': 'tech_pack', 'kind_label': 'Tech Pack',
            'id': t.get('id'), 'code': t.get('tech_pack_code') or t.get('code') or '-',
            'title': t.get('style_name') or t.get('name') or '(tanpa nama)',
            'subtitle': f"status {t.get('status')}",
            'requested_by': t.get('created_by') or '-',
            'waiting_since': (t.get('updated_at') or t.get('created_at')),
            'age_days': age, 'sla': _sla(age, att_days, stale_days),
            'detail': {
                'Style': t.get('style_name') or '-',
                'Status': t.get('status') or '-',
                'Dibuat': t.get('created_at'),
            },
            'images': _images(t.get('images') or t.get('sketch_images')),
            'attachment_url': t.get('file_url') or t.get('url') or '',
            'attachment_name': t.get('file_name') or '',
            'approve_url': f"/api/dewi/rnd/tech-packs/{t.get('id')}/approve",
            'reject_url': '',
            'reject_requires_notes': False,
            'next_step': 'Tech pack disetujui = spesifikasi siap dipakai produksi.',
        })

    items.sort(key=lambda r: -r['age_days'])

    # Tahapan lifecycle 7 langkah — dari SATU helper (`rnd_lifecycle`) supaya angka
    # kartu funnel dan tabel "Posisi Tiap Style" tidak pernah berbeda.
    lc = await rnd_lifecycle(db, include_styles=False)
    funnel = lc['stages']

    return {
        'items': items,
        'total': len(items),
        'by_kind': {
            'style': sum(1 for i in items if i['kind'] == 'style'),
            'sample': sum(1 for i in items if i['kind'] == 'sample'),
            'tech_pack': sum(1 for i in items if i['kind'] == 'tech_pack'),
        },
        'overdue': sum(1 for i in items if i['sla'] == 'terlambat'),
        'attention': sum(1 for i in items if i['sla'] == 'perlu perhatian'),
        # Ambang aktif supaya UI bisa menjelaskan artinya (dan dari mana diaturnya)
        'thresholds': {
            'attention_days': att_days, 'stale_days': stale_days,
            'source': 'dewi_mgmt_alert_config',
            'note': (f'Kuning bila menunggu ≥ {att_days} hari, merah bila ≥ {stale_days} hari. '
                     'Diatur di Portal Manajemen → Ringkasan Bisnis → Ambang Peringatan.'),
        },
        'funnel': funnel,
        'sources': [
            {'collection': 'dewi_rnd_styles', 'count': lc['total_styles'], 'note': 'style desain'},
            {'collection': 'dewi_rnd_sample_requests', 'count': len(samples), 'note': 'sample menunggu'},
            {'collection': 'dewi_rnd_tech_packs', 'count': len(tps), 'note': 'tech pack menunggu'},
        ],
    }


# ── TAHAPAN LIFECYCLE LENGKAP (2026-08-07) ───────────────────────────────────
# Owner: "tampilkan tahap Tech Pack dan pembuat sample di kokpit manajemen,
# bukan hanya 4 langkah." Satu style menempati SATU tahap terjauh yang sudah
# dicapai, jadi jumlah seluruh tahap = jumlah style (funnel yang jujur).
STAGE_ORDER = [
    ('draft', 'Draft', 'Masih digarap staf RnD'),
    ('pending_owner_review', 'Menunggu Keputusan', 'Bola ada di manajemen'),
    ('approved_for_launch', 'Disetujui', 'Menunggu tech pack'),
    ('techpack', 'Tech Pack', 'Spesifikasi tersedia'),
    ('pattern', 'Pola & Marking', 'Pola terdokumentasi'),
    ('sample', 'Sample', 'Sample diminta / dikerjakan'),
    ('promoted', 'Naik Produksi', 'Sudah jadi model produksi'),
]
STAGE_LABEL = {k: label for k, label, _ in STAGE_ORDER}


def _latest(rows: list, key: str):
    """Dokumen terakhir menurut `key` (versi / tanggal) — aman untuk nilai kosong."""
    best = None
    for r in rows:
        if best is None or str(r.get(key) or '') >= str(best.get(key) or ''):
            best = r
    return best


async def rnd_lifecycle(db, *, include_styles: bool = True, limit: int = 300) -> dict:
    """Posisi setiap style di 7 tahap lifecycle RnD + rinciannya per style."""
    styles = await db.dewi_rnd_styles.find({}, {'_id': 0}).sort('updated_at', -1).to_list(2000)
    ids = [s['id'] for s in styles if s.get('id')]

    async def _count_by_style(coll: str) -> dict:
        out: dict = {}
        if not ids:
            return out
        cur = db[coll].aggregate([
            {'$match': {'style_id': {'$in': ids}}},
            {'$group': {'_id': '$style_id', 'n': {'$sum': 1}}},
        ])
        async for r in cur:
            out[r['_id']] = r['n']
        return out

    variant_docs = await _count_by_style('dewi_rnd_variants')
    pattern_docs = await _count_by_style('dewi_rnd_patterns')
    hpp_docs = await _count_by_style('dewi_rnd_hpp')
    revision_docs = await _count_by_style('dewi_rnd_revisions')

    tp_rows, sample_rows = [], []
    if ids:
        tp_rows = await db.dewi_rnd_tech_packs.find(
            {'style_id': {'$in': ids}}, {'_id': 0}).to_list(2000)
        sample_rows = await db.dewi_rnd_sample_requests.find(
            {'style_id': {'$in': ids}}, {'_id': 0}).to_list(2000)

    tp_by, sm_by = {}, {}
    for t in tp_rows:
        tp_by.setdefault(t.get('style_id'), []).append(t)
    for x in sample_rows:
        sm_by.setdefault(x.get('style_id'), []).append(x)

    counts = {k: 0 for k, _, _ in STAGE_ORDER}
    rows = []
    for s in styles:
        sid_ = s.get('id')
        status = (s.get('status') or 'draft')
        tps = tp_by.get(sid_, [])
        sms = sm_by.get(sid_, [])
        n_pattern = pattern_docs.get(sid_, 0)
        n_variant = variant_docs.get(sid_, 0) or len(s.get('variants') or [])
        tp_latest = _latest(tps, 'version')
        sm_latest = _latest(sms, 'created_at')
        waiting = _age_days(s.get('submitted_for_review_at') or s.get('updated_at'))

        if s.get('promoted_to_model_id'):
            stage = 'promoted'
            next_action = 'Sudah menjadi model produksi — dikelola di Master Produk.'
        elif status == 'pending_owner_review':
            stage = 'pending_owner_review'
            next_action = f'Menunggu keputusan manajemen ({waiting} hari).'
        elif status in ('draft', 'archived'):
            stage = 'draft'
            next_action = ('Perbaiki sesuai catatan penolakan lalu ajukan ulang.'
                           if s.get('owner_review_result') == 'rejected'
                           else 'Lengkapi desain/foto lalu ajukan ke manajemen.')
        elif sms:
            stage = 'sample'
            st = (sm_latest or {}).get('status')
            next_action = {
                'draft': 'Sample masih draft — ajukan ke manajemen.',
                'submitted': 'Sample menunggu persetujuan manajemen.',
                'approved': 'Sample disetujui — siap dinaikkan ke produksi.',
                'rejected': 'Sample ditolak — perbaiki lalu ajukan ulang.',
            }.get(st, 'Pantau progres sample.')
        elif n_pattern:
            stage = 'pattern'
            next_action = 'Belum ada permintaan sample — buat sample request.'
        elif tps:
            stage = 'techpack'
            next_action = 'Belum ada dokumentasi pola & marking.'
        else:
            stage = 'approved_for_launch'
            next_action = 'Belum ada tech pack — minta RnD menyiapkan spesifikasi.'

        counts[stage] += 1
        if include_styles:
            rows.append({
                'id': sid_, 'style_code': s.get('style_code') or '-',
                'style_name': s.get('style_name') or '-',
                'status': status, 'rnd_type': s.get('rnd_type') or '',
                'client': s.get('client_name') or s.get('buyer') or '',
                'stage': stage, 'stage_label': STAGE_LABEL[stage],
                'next_action': next_action,
                'waiting_days': waiting if stage == 'pending_owner_review' else 0,
                'age_days': _age_days(s.get('updated_at') or s.get('created_at')),
                'variants': n_variant,
                'photos': len(s.get('design_images') or []),
                'revisions': revision_docs.get(sid_, 0),
                'patterns': n_pattern,
                'hpp': hpp_docs.get(sid_, 0),
                'techpack': {
                    'count': len(tps),
                    'version': (tp_latest or {}).get('version') or '',
                    'status': (tp_latest or {}).get('status') or '',
                    'approved': sum(1 for t in tps if (t.get('status') or '') == 'approved'),
                },
                'sample': {
                    'count': len(sms),
                    'code': (sm_latest or {}).get('sample_code') or '',
                    'status': (sm_latest or {}).get('status') or '',
                    'pic': (sm_latest or {}).get('sample_pic') or '',
                    'qty': (sm_latest or {}).get('quantity') or 0,
                    'due_date': (sm_latest or {}).get('due_date') or '',
                    'approved': sum(1 for x in sms if (x.get('status') or '') == 'approved'),
                },
                'owner_review_result': s.get('owner_review_result') or '',
                'owner_reviewed_by': s.get('owner_reviewed_by') or '',
            })

    stages = [{'key': k, 'stage': label, 'count': counts[k], 'hint': hint}
              for k, label, hint in STAGE_ORDER]

    out = {
        'stages': stages,
        'total_styles': len(styles),
        'totals': {
            'tech_packs': len(tp_rows),
            'tech_packs_approved': sum(1 for t in tp_rows if (t.get('status') or '') == 'approved'),
            'samples': len(sample_rows),
            'samples_approved': sum(1 for x in sample_rows if (x.get('status') or '') == 'approved'),
            'sample_pics': len({(x.get('sample_pic') or '').strip()
                                for x in sample_rows if (x.get('sample_pic') or '').strip()}),
            'patterns': sum(pattern_docs.values()),
            'hpp': sum(hpp_docs.values()),
        },
        'sources': [
            {'collection': 'dewi_rnd_styles', 'count': len(styles), 'note': 'style desain'},
            {'collection': 'dewi_rnd_tech_packs', 'count': len(tp_rows), 'note': 'tech pack'},
            {'collection': 'dewi_rnd_patterns', 'count': sum(pattern_docs.values()), 'note': 'pola'},
            {'collection': 'dewi_rnd_sample_requests', 'count': len(sample_rows), 'note': 'sample'},
        ],
    }
    if include_styles:
        rows.sort(key=lambda r: ([k for k, _, _ in STAGE_ORDER].index(r['stage']),
                                 -r['waiting_days']))
        out['styles'] = rows[:limit]
        out['styles_shown'] = len(out['styles'])
    return out


@router.get('/lifecycle')
async def get_rnd_lifecycle(
    limit: int = Query(300, ge=1, le=1000),
    user: dict = Depends(require_auth),
):
    """Tahapan lifecycle RnD lengkap + posisi tiap style (dipakai kokpit manajemen)."""
    return await rnd_lifecycle(get_db(), include_styles=True, limit=limit)


# ── RAPOR KEPUTUSAN RnD MINGGUAN (2026-08-07) ────────────────────────────────
@router.get('/reports/weekly-decisions')
async def preview_weekly_rnd_report(
    days: int = Query(7, ge=1, le=90),
    stale_days: int = Query(None, ge=0, le=60),
    user: dict = Depends(require_auth),
):
    """Pratinjau rapor mingguan (tidak mengirim notifikasi)."""
    from services.rnd_decision_report import build_rnd_decision_report
    return await build_rnd_decision_report(get_db(), days=days, stale_days=stale_days)


@router.post('/reports/weekly-decisions/send')
async def send_weekly_rnd_report(body: dict = None, user: dict = Depends(require_auth)):
    """Kirim rapor sekarang ke notifikasi manajemen (tombol 'Kirim sekarang')."""
    from services.rnd_decision_report import send_rnd_decision_report
    b = body or {}
    try:
        days = int(b['days']) if b.get('days') not in (None, '') else 7
        stale = int(b['stale_days']) if b.get('stale_days') not in (None, '') else None
    except (TypeError, ValueError):
        raise HTTPException(400, 'days / stale_days harus angka hari.')
    if not 1 <= days <= 90:
        raise HTTPException(400, 'days harus 1..90.')
    return await send_rnd_decision_report(get_db(), days=days, stale_days=stale, force=True)


@router.get('/approvals/history')
async def rnd_approval_history(limit: int = 50, user: dict = Depends(require_auth)):
    """Riwayat keputusan RnD: siapa menyetujui/menolak, kapan, dan alasannya.

    Owner: "tampilkan siapa menyetujui atau menolak style dan alasannya di satu daftar."
    """
    db = get_db()
    limit = max(1, min(int(limit or 50), 200))
    rows = []

    styles = await db.dewi_rnd_styles.find(
        {'owner_review_result': {'$in': ['approved', 'rejected']}}, {'_id': 0}).to_list(1000)
    for s in styles:
        rows.append({
            'kind': 'style', 'kind_label': 'Style / Desain',
            'id': s.get('id'), 'code': s.get('style_code') or '-',
            'title': s.get('style_name') or '-',
            'result': s.get('owner_review_result'),
            'decided_by': s.get('owner_reviewed_by') or '-',
            'decided_at': s.get('owner_reviewed_at'),
            'notes': s.get('owner_review_notes') or '',
            'status_now': s.get('status'),
            'promoted': bool(s.get('promoted_to_model_id')),
        })

    samples = await db.dewi_rnd_sample_requests.find(
        {'status': {'$in': ['approved', 'rejected']}}, {'_id': 0}).to_list(1000)
    for s in samples:
        rows.append({
            'kind': 'sample', 'kind_label': 'Permintaan Sample',
            'id': s.get('id'), 'code': s.get('request_code') or s.get('sample_code') or '-',
            'title': s.get('style_name') or s.get('product_name') or '-',
            'result': s.get('approval_status') or s.get('status'),
            'decided_by': s.get('approved_by_name') or '-',
            'decided_at': s.get('approved_at'),
            'notes': s.get('approval_notes') or s.get('rejection_notes') or '',
            'status_now': s.get('status'), 'promoted': False,
        })

    tps = await db.dewi_rnd_tech_packs.find({'status': 'approved'}, {'_id': 0}).to_list(1000)
    for t in tps:
        rows.append({
            'kind': 'tech_pack', 'kind_label': 'Tech Pack',
            'id': t.get('id'), 'code': t.get('tech_pack_code') or t.get('code') or '-',
            'title': t.get('style_name') or t.get('name') or '-',
            'result': 'approved',
            'decided_by': t.get('approved_by') or '-',
            'decided_at': t.get('approved_at'),
            'notes': t.get('approval_notes') or '',
            'status_now': t.get('status'), 'promoted': False,
        })

    rows.sort(key=lambda r: str(r.get('decided_at') or ''), reverse=True)
    return {
        'items': rows[:limit],
        'total': len(rows),
        'approved': sum(1 for r in rows if r['result'] == 'approved'),
        'rejected': sum(1 for r in rows if r['result'] == 'rejected'),
        'sources': [
            {'collection': 'dewi_rnd_styles', 'count': len(styles), 'note': 'keputusan style'},
            {'collection': 'dewi_rnd_sample_requests', 'count': len(samples), 'note': 'keputusan sample'},
            {'collection': 'dewi_rnd_tech_packs', 'count': len(tps), 'note': 'tech pack disetujui'},
        ],
    }
