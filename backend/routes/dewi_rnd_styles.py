"""dewi_rnd — Style Master + Design Selection Approval Workflow (GAP-R2)."""
from datetime import datetime
from fastapi import Depends, File, HTTPException, Query, UploadFile
from database import get_db
from auth import require_auth
from routes.dewi_rnd_shared import router, now_utc, sid, serialize
from routes.shared import assert_can_act
from core import product_master as pm  # F1/F3/F5: SSOT `active`, kategori, resolusi HPP
from utils.variant_ssot import promote_rnd_variants_to_master

# Keputusan akhir style RnD = hak owner/admin (pilihan owner, 2026-08-07).
OWNER_DECISION_ROLES = ('owner', 'admin', 'superadmin')

# Status siklus hidup: HANYA boleh berubah lewat endpoint keputusan
# (submit-for-review / owner-approve / owner-reject) supaya setiap perpindahan
# punya pemutus, waktu, dan alasan. Form edit umum tidak boleh menyentuhnya.
LIFECYCLE_STATUSES = frozenset({'pending_owner_review', 'approved_for_launch'})
# Status yang wajar diubah dari form edit biasa.
EDITABLE_STATUSES = frozenset({'draft', 'active', 'archived'})

# ──────────────────────────────────────────────────────────────────────────────
# STYLE MASTER (Master Style & Tech Pack)
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/styles')
async def list_styles(
    status: str = None,
    category: str = None,
    buyer: str = None,
    rnd_type: str = None,
    search: str = None,
    limit: int = Query(200, ge=1, le=1000),
    user: dict = Depends(require_auth),
):
    """List semua styles"""
    db = get_db()
    q = {}
    if status:
        q['status'] = status
    if category:
        q['category'] = category
    if buyer:
        q['buyer'] = buyer
    if rnd_type:
        q['rnd_type'] = rnd_type
    if search:
        import re
        q['$or'] = [
            {'style_code': {'$regex': re.escape(search), '$options': 'i'}},
            {'style_name': {'$regex': re.escape(search), '$options': 'i'}},
        ]

    styles = await db.dewi_rnd_styles.find(q).sort('created_at', -1).limit(limit).to_list(length=limit)
    return [serialize(s) for s in styles]


@router.get('/styles/pending-review')
async def list_styles_pending_review(user: dict = Depends(require_auth)):
    """List styles yang menunggu review owner"""
    db = get_db()
    styles = await db.dewi_rnd_styles.find(
        {'status': 'pending_owner_review'}, {'_id': 0}
    ).sort('submitted_for_review_at', -1).to_list(100)
    return [serialize(s) for s in styles]


@router.post('/styles')
async def create_style(body: dict, user: dict = Depends(require_auth)):
    """Create new style"""
    db = get_db()
    code = (body.get('style_code') or '').strip().upper()
    name = (body.get('style_name') or '').strip()

    if not code or not name:
        raise HTTPException(400, 'style_code dan style_name wajib diisi')

    existing = await db.dewi_rnd_styles.find_one({'style_code': code})
    if existing:
        raise HTTPException(409, f'Style code {code} sudah ada')

    doc = {
        'id': sid(),
        'style_code': code,
        'style_name': name,
        'category': body.get('category', ''),
        'buyer': body.get('buyer', ''),
        'fabric_type': body.get('fabric_type', ''),
        'season': body.get('season', ''),
        'description': body.get('description', ''),
        'status': body.get('status', 'draft'),
        'rnd_type': body.get('rnd_type', 'internal_product'),
        'client_id': body.get('client_id', None),
        'client_name': body.get('client_name', ''),
        'promoted_to_model_id': None,
        'techpack_url': None,
        'techpack_name': None,
        'design_images': [],
        'variants': [],
        # F2: daftar ukuran BEBAS per style (SATU sumber untuk modal Varian + Tech Pack).
        # Kosong = pakai daftar bawaan (lihat routes/dewi_rnd_sizes.DEFAULT_SIZE_LIST).
        'size_list': [],
        'size_map': [],
        'created_by': user['id'],
        'created_by_name': user.get('name', ''),
        'created_at': now_utc(),
        'updated_at': now_utc(),
    }
    await db.dewi_rnd_styles.insert_one(doc)
    return serialize(doc)


@router.get('/styles/{style_id}')
async def get_style(style_id: str, user: dict = Depends(require_auth)):
    """Get style by ID"""
    db = get_db()
    s = await db.dewi_rnd_styles.find_one({'id': style_id})
    if not s:
        raise HTTPException(404, 'Style tidak ditemukan')
    return serialize(s)


# ── Riwayat revisi otomatis + foto desain (2026-08-07) ───────────────────────
# Owner: "tambah unggah foto desain di portal RnD" + "bandingkan revisi style
# berdampingan". Supaya bisa dibandingkan, SETIAP perubahan style dicatat sebagai
# revisi ber-snapshot (termasuk daftar foto saat itu). Revisi manual tetap jalan.

STYLE_TRACKED_FIELDS = [
    ('style_code', 'Kode Style'),
    ('style_name', 'Nama Style'),
    ('category', 'Kategori'),
    ('buyer', 'Buyer'),
    ('client_name', 'Klien'),
    ('fabric_type', 'Bahan'),
    ('season', 'Season'),
    ('description', 'Deskripsi'),
    ('status', 'Status'),
    ('rnd_type', 'Jenis RnD'),
]

MAX_IMAGE_BYTES = 10 * 1024 * 1024


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _style_images(raw) -> list:
    """Bentuk seragam daftar foto desain: string URL lama atau objek {id,url,caption}."""
    out = []
    for it in (raw or []):
        if isinstance(it, str):
            out.append({'id': it, 'url': it, 'caption': '', 'uploaded_by': '', 'uploaded_at': None})
        elif isinstance(it, dict) and (it.get('url') or it.get('storage_path')):
            out.append({
                'id': it.get('id') or it.get('url') or it.get('storage_path'),
                'url': it.get('url') or f"/api/files/{it.get('storage_path')}",
                'caption': it.get('caption') or it.get('original_filename') or '',
                'uploaded_by': it.get('uploaded_by') or '',
                'uploaded_at': _iso(it.get('uploaded_at')),
            })
    return out


def _style_snapshot(style: dict) -> dict:
    snap = {k: style.get(k) for k, _ in STYLE_TRACKED_FIELDS}
    snap['design_images'] = _style_images(style.get('design_images'))
    snap['techpack_name'] = style.get('techpack_name') or ''
    snap['variants_count'] = len(style.get('variants') or [])
    return snap


async def _record_style_revision(db, style: dict, user: dict, changed: list, *,
                                 revision_type: str = 'design',
                                 revision_name: str = None,
                                 summary: str = None):
    """Catat satu baris riwayat revisi (sumber 'auto') beserta snapshot style."""
    prev = await db.dewi_rnd_revisions.find(
        {'style_id': style['id']}).sort('revision_number', -1).to_list(1)
    number = (prev[0].get('revision_number') or 0) + 1 if prev else 1
    first = changed[0] if changed else {}
    doc = {
        'id': sid(),
        'style_id': style['id'],
        'style_code': style.get('style_code', ''),
        'style_name': style.get('style_name', ''),
        'revision_number': number,
        'revision_name': revision_name or f'Rev {number}',
        'revision_type': revision_type,
        'changes_summary': summary or '; '.join(
            f"{c['label']}: {c.get('old') or '—'} → {c.get('new') or '—'}" for c in changed),
        'old_value': str(first.get('old') or ''),
        'new_value': str(first.get('new') or ''),
        'changed_fields': changed,
        'snapshot': _style_snapshot(style),
        'source': 'auto',
        'notes': '',
        'created_by': user.get('id', ''),
        'created_by_name': user.get('name', ''),
        'created_at': now_utc(),
    }
    await db.dewi_rnd_revisions.insert_one(doc)
    return serialize(doc)


@router.put('/styles/{style_id}')
async def update_style(style_id: str, body: dict, user: dict = Depends(require_auth)):
    """Update style — perubahan field terlacak otomatis tercatat sebagai revisi.

    2026-08-07 — LUBANG ALUR DITUTUP: endpoint umum ini dulu menerima `status` apa
    pun, sehingga siapa pun yang boleh menyunting style bisa menulis
    `approved_for_launch` (melewati keputusan owner) atau menarik kembali style
    yang sedang direview menjadi `draft` tanpa jejak keputusan. Sekarang status
    siklus hidup HANYA boleh diubah lewat pintunya masing-masing:
      · `POST /styles/{id}/submit-for-review` → pending_owner_review
      · `POST /styles/{id}/owner-approve`     → approved_for_launch
      · `POST /styles/{id}/owner-reject`      → kembali ke draft + alasan
    """
    db = get_db()
    before = await db.dewi_rnd_styles.find_one({'id': style_id})
    if not before:
        raise HTTPException(404, 'Style tidak ditemukan')

    body.pop('_id', None)
    body.pop('id', None)
    body.pop('created_at', None)
    body.pop('created_by', None)

    # F2: `size_list` hanya boleh lewat PUT /styles/{id}/size-list supaya pemadanan
    # master (size_map), base_size, dan size_range selalu ikut terhitung.
    if 'size_list' in body:
        from routes.dewi_rnd_sizes import (
            _clean_size_list, build_size_map, compute_size_range, pick_base_size,
        )
        sl = _clean_size_list(body.get('size_list'))
        if sl:
            body['size_list'] = sl
            body['size_map'] = await build_size_map(db, sl)
            body['base_size'] = pick_base_size(sl, body.get('base_size') or before.get('base_size'))
            body['size_range'] = compute_size_range(sl)
        else:
            body.pop('size_list', None)

    if 'status' in body:
        new_status = (body.get('status') or '').strip()
        cur_status = (before.get('status') or 'draft').strip()
        if new_status != cur_status:
            if new_status in LIFECYCLE_STATUSES:
                raise HTTPException(
                    403,
                    'Status keputusan tidak boleh diubah dari form edit. '
                    'Pakai tombol "Ajukan Review" / "Setujui" / "Tolak" agar keputusan '
                    'tercatat beserta pemutus dan alasannya.')
            if cur_status in LIFECYCLE_STATUSES:
                raise HTTPException(
                    403,
                    f'Style sedang berstatus "{cur_status}". Selesaikan dulu lewat tombol '
                    'Setujui/Tolak — status tidak bisa ditimpa dari form edit.')
            if new_status not in EDITABLE_STATUSES:
                raise HTTPException(
                    400,
                    f'Status tidak dikenal: {new_status}. Pilihan: {", ".join(sorted(EDITABLE_STATUSES))}.')
        else:
            body.pop('status', None)  # tidak berubah → jangan dicatat sebagai revisi

    body['updated_at'] = now_utc()

    if 'style_code' in body:
        body['style_code'] = body['style_code'].strip().upper()

    await db.dewi_rnd_styles.update_one({'id': style_id}, {'$set': body})
    updated = await db.dewi_rnd_styles.find_one({'id': style_id})

    changed = [
        {'field': k, 'label': label,
         'old': '' if before.get(k) is None else str(before.get(k)),
         'new': '' if updated.get(k) is None else str(updated.get(k))}
        for k, label in STYLE_TRACKED_FIELDS
        if k in body and str(before.get(k) or '') != str(updated.get(k) or '')
    ]
    if changed:
        if any(c['field'] == 'fabric_type' for c in changed):
            rtype = 'material'
        elif all(c['field'] == 'status' for c in changed):
            rtype = 'other'
        else:
            rtype = 'design'
        await _record_style_revision(
            db, updated, user, changed, revision_type=rtype,
            revision_name=f"Ubah {', '.join(c['label'] for c in changed[:3])}")

    return serialize(updated)


@router.delete('/styles/{style_id}')
async def delete_style(style_id: str, user: dict = Depends(require_auth)):
    """Delete style + riwayat revisinya (cegah revisi yatim)."""
    db = get_db()
    res = await db.dewi_rnd_styles.delete_one({'id': style_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Style tidak ditemukan')
    revs = await db.dewi_rnd_revisions.delete_many({'style_id': style_id})
    return {'success': True, 'revisions_deleted': revs.deleted_count}


# ── GAP-R2: Design Selection Approval Workflow ────────────────────────────────

@router.post('/styles/{style_id}/submit-for-review')
async def submit_style_for_review(
    style_id: str,
    body: dict = {},
    user: dict = Depends(require_auth),
):
    """RnD staff submits style for Owner review."""
    db = get_db()
    style = await db.dewi_rnd_styles.find_one({'id': style_id})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan')
    if style.get('status') not in ('draft', 'active'):
        raise HTTPException(
            400,
            f"Hanya style berstatus draft/active yang bisa diajukan review "
            f"(saat ini: {style.get('status')})",
        )

    now = now_utc()
    await db.dewi_rnd_styles.update_one(
        {'id': style_id},
        {'$set': {
            'status': 'pending_owner_review',
            'submitted_for_review_by': user.get('name', ''),
            'submitted_for_review_by_id': user.get('id', ''),
            'submitted_for_review_at': now,
            'review_notes': body.get('notes', ''),
            'owner_review_result': None,
            'owner_reviewed_by': None,
            'owner_reviewed_at': None,
            'owner_review_notes': None,
            'updated_at': now,
        }},
    )
    updated = await db.dewi_rnd_styles.find_one({'id': style_id})
    return serialize(updated)


@router.post('/styles/{style_id}/owner-approve')
async def owner_approve_style(
    style_id: str,
    body: dict = {},
    user: dict = Depends(require_auth),
):
    """Owner/SuperAdmin approves a style design."""
    assert_can_act(user, 'management.manage', 'rnd.approve',
                   legacy_roles=OWNER_DECISION_ROLES,
                   what='menyetujui keputusan style RnD (khusus owner/admin)')
    db = get_db()
    style = await db.dewi_rnd_styles.find_one({'id': style_id})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan')
    if style.get('status') != 'pending_owner_review':
        raise HTTPException(
            400,
            f"Style harus berstatus pending_owner_review untuk disetujui "
            f"(saat ini: {style.get('status')})",
        )

    now = now_utc()
    await db.dewi_rnd_styles.update_one(
        {'id': style_id},
        {'$set': {
            'status': 'approved_for_launch',
            'owner_review_result': 'approved',
            'owner_reviewed_by': user.get('name', ''),
            'owner_reviewed_by_id': user.get('id', ''),
            'owner_reviewed_at': now,
            'owner_review_notes': body.get('notes', ''),
            'updated_at': now,
        }},
    )
    updated = await db.dewi_rnd_styles.find_one({'id': style_id})
    return serialize(updated)


@router.post('/styles/{style_id}/promote-to-production')
async def promote_style_to_production(
    style_id: str,
    body: dict = {},
    user: dict = Depends(require_auth),
):
    """Promote approved RnD Internal Style ke Production Model."""
    db = get_db()
    style = await db.dewi_rnd_styles.find_one({'id': style_id})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan')
    if style.get('rnd_type') == 'maklon_product':
        raise HTTPException(400, 'Style maklon tidak di-promote ke Production Model (produk milik buyer)')
    if style.get('status') != 'approved_for_launch':
        raise HTTPException(
            400,
            f"Style harus berstatus approved_for_launch untuk di-promote "
            f"(saat ini: {style.get('status')})",
        )
    if style.get('promoted_to_model_id'):
        raise HTTPException(400, 'Style sudah pernah di-promote ke Production Model')

    model_id = sid()
    model_code = body.get('model_code') or style['style_code']

    # ── GAP-6: propagate latest Tech Pack spec (BOM/construction/measurements) ke Master Product.
    # sop_steps dibaca oleh Panduan Produksi (production-guide) untuk produk internal. ──
    techpack = await db.dewi_rnd_tech_packs.find_one(
        {'style_id': style_id, 'is_latest': True}, {'_id': 0}
    ) or await db.dewi_rnd_tech_packs.find_one(
        {'style_id': style_id}, {'_id': 0}, sort=[('version', -1)]
    )
    sop_steps, reference_images, techpack_snapshot = [], [], None
    if techpack:
        # construction_notes (multi-baris) → sop_steps terstruktur
        raw_notes = (techpack.get('construction_notes') or '').strip()
        lines = [ln.strip(' -•\t') for ln in raw_notes.splitlines() if ln.strip(' -•\t')]
        for i, ln in enumerate(lines):
            sop_steps.append({'id': sid(), 'seq': i + 1, 'title': f'Langkah {i + 1}',
                              'description': ln, 'image_path': ''})
        techpack_snapshot = {
            'tech_pack_id': techpack.get('id'),
            'version': techpack.get('version'),
            'bom_items': list(techpack.get('bom_items') or []),
            'construction_notes': raw_notes,
            'stitch_type': techpack.get('stitch_type', ''),
            'seam_allowance_mm': techpack.get('seam_allowance_mm'),
            'measurements': list(techpack.get('measurements') or []),
            'size_range': techpack.get('size_range', ''),
            'base_size': techpack.get('base_size', ''),
        }
    reference_images = [{'url': u, 'title': ''} for u in (style.get('design_images') or [])]

    # ── F1/T1 — `active` WAJIB ditulis. Dulu jalur ini hanya menulis
    # `status: 'active'`, sementara index unik `rahaza_models.code` memakai
    # `partialFilterExpression {active: true}` ⇒ produk hasil promosi berada di
    # LUAR index dan pengecekan duplikat API melewatkannya ⇒ KODE KEMBAR
    # diterima HTTP 200. Terbukti lewat HTTP; jangan dihapus. ──
    if await db.rahaza_models.find_one(pm.live_model_filter({'code': model_code})):
        raise HTTPException(
            409, f"Kode produk '{model_code}' sudah terpakai di Master Produk. "
                 'Ganti `model_code` saat promosi.')

    # ── F3/F5 — kategori style R&D dipetakan ke MASTER kategori, dan angka R&D
    # (HPP rencana, harga jual, berat) dibawa turun supaya produk hasil promosi
    # tidak lahir tanpa HPP/harga (P1a/P1b). ──
    cat = await pm.resolve_category_by_text(db, style.get('category') or '',
                                            allow_create=False)
    rnd_hpp = 0.0
    hpp_doc = await db.dewi_rnd_hpp.find_one(
        {'style_id': style_id}, {'_id': 0}, sort=[('created_at', -1)]) or {}
    for key in ('hpp_per_pcs', 'hpp', 'total_hpp_per_pcs'):
        if hpp_doc.get(key) is not None:
            try:
                rnd_hpp = float(hpp_doc.get(key) or 0)
            except (TypeError, ValueError):
                rnd_hpp = 0.0
            if rnd_hpp:
                break

    def _num(*vals):
        for v in vals:
            try:
                f = float(v or 0)
            except (TypeError, ValueError):
                continue
            if f:
                return f
        return 0.0

    model_doc = {
        'id': model_id,
        'code': model_code,
        'name': style['style_name'],
        'fabric_type': style.get('fabric_type', ''),
        'description': style.get('description', ''),
        'rnd_style_id': style_id,
        'rnd_style_code': style['style_code'],
        'image_paths': list(style.get('design_images') or []),  # FIX G1: bawa foto RnD → Master Data (rahaza_models.image_paths)
        'sop_steps': sop_steps,                    # GAP-6: konstruksi → panduan produksi
        'reference_images': reference_images,      # GAP-6: foto desain → referensi produksi
        'techpack': techpack_snapshot,             # GAP-6: snapshot spec techpack
        'sop_updated_at': now_utc() if sop_steps else None,
        'sop_updated_by': user.get('name', '') if sop_steps else '',
        'hpp': rnd_hpp,
        'hpp_rnd': rnd_hpp,     # F5 — nilai ASAL R&D (pemisah sumber HPP)
        'base_hpp': 0.0,
        'retail_price': _num(style.get('target_price'), style.get('retail_price'),
                             hpp_doc.get('harga_jual'), hpp_doc.get('suggested_price')),
        'weight_gram': _num(style.get('weight_gram'), (techpack or {}).get('weight_gram')),
        'active': True,          # F1/T1 — penanda hidup/mati KANONIK
        'status': 'active',      # dibaca dokumen/laporan lama
        'created_by': user['id'],
        'created_by_name': user.get('name', ''),
        'created_at': now_utc(),
        'updated_at': now_utc(),
    }
    pm.apply_category(model_doc, cat)
    if not model_doc.get('category'):
        model_doc['category'] = style.get('category', '')
    _hpp, _src = pm.resolve_hpp(model_doc)
    model_doc['hpp'] = _hpp
    model_doc['hpp_source'] = _src
    model_doc['hpp_updated_at'] = now_utc() if _hpp else None
    await db.rahaza_models.insert_one(model_doc)
    await db.dewi_rnd_styles.update_one(
        {'id': style_id},
        {'$set': {
            'promoted_to_model_id': model_id,
            'promoted_at': now_utc(),
            'promoted_by': user['id'],
            'updated_at': now_utc(),
        }},
    )

    # ── GAP-3: generate canonical rahaza_model_variants (+FG kosong) dari varian RnD. ──
    try:
        variants_result = await promote_rnd_variants_to_master(db, style, model_doc, user=user)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('promote_rnd_variants_to_master gagal utk style %s', style_id)
        variants_result = {'created_count': 0, 'skipped_count': 0, 'error': True}

    return {
        'status': 'promoted',
        'model_id': model_id,
        'model_code': model_code,
        'variants': variants_result,
        'sop_steps_count': len(sop_steps),
        'message': (
            f'Style {style["style_code"]} berhasil di-promote ke Production Model {model_code} '
            f'({variants_result.get("created_count", 0)} varian + FG dibuat, '
            f'{len(sop_steps)} langkah SOP dari techpack)'
        ),
    }


@router.post('/styles/{style_id}/owner-reject')
async def owner_reject_style(
    style_id: str,
    body: dict = {},
    user: dict = Depends(require_auth),
):
    """Owner/SuperAdmin rejects a style design."""
    assert_can_act(user, 'management.manage', 'rnd.approve',
                   legacy_roles=OWNER_DECISION_ROLES,
                   what='menolak keputusan style RnD (khusus owner/admin)')
    db = get_db()
    style = await db.dewi_rnd_styles.find_one({'id': style_id})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan')
    if style.get('status') != 'pending_owner_review':
        raise HTTPException(
            400,
            f"Style harus berstatus pending_owner_review untuk ditolak "
            f"(saat ini: {style.get('status')})",
        )
    if not body.get('notes'):
        raise HTTPException(400, 'Catatan penolakan wajib diisi')

    now = now_utc()
    await db.dewi_rnd_styles.update_one(
        {'id': style_id},
        {'$set': {
            'status': 'draft',
            'owner_review_result': 'rejected',
            'owner_reviewed_by': user.get('name', ''),
            'owner_reviewed_by_id': user.get('id', ''),
            'owner_reviewed_at': now,
            'owner_review_notes': body.get('notes', ''),
            'updated_at': now,
        }},
    )
    updated = await db.dewi_rnd_styles.find_one({'id': style_id})
    return serialize(updated)


# ── FOTO DESAIN (unggah dari portal RnD → galeri di Cockpit Manajemen) ───────

@router.post('/styles/{style_id}/images')
async def upload_style_design_image(
    style_id: str,
    file: UploadFile = File(...),
    caption: str = Query(''),
    user: dict = Depends(require_auth),
):
    """Unggah foto / sketsa desain untuk satu style."""
    from storage import put_object, generate_storage_path
    db = get_db()
    style = await db.dewi_rnd_styles.find_one({'id': style_id})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan')

    content = await file.read()
    if not content:
        raise HTTPException(400, 'Berkas kosong')
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(400, 'Gambar terlalu besar (maks 10MB)')
    ctype = file.content_type or 'image/jpeg'
    if not ctype.startswith('image/'):
        raise HTTPException(400, 'Hanya berkas gambar yang boleh diunggah')

    path = generate_storage_path(user['id'], f'rnd_style_{style_id[:8]}_{file.filename}')
    try:
        stored = put_object(path, content, ctype).get('path', path)
    except Exception as e:
        raise HTTPException(500, f'Upload gagal: {e}')

    await db.attachments.insert_one({
        'id': sid(), 'storage_path': stored,
        'original_filename': file.filename, 'content_type': ctype,
        'size': len(content), 'entity_type': 'rnd_style', 'entity_id': style_id,
        'uploaded_by': user.get('name', ''), 'uploaded_by_id': user['id'],
        'is_deleted': False, 'created_at': now_utc(),
    })

    before_count = len(_style_images(style.get('design_images')))
    label = (caption or file.filename or 'foto').strip()
    entry = {
        'id': sid(), 'url': f'/api/files/{stored}', 'storage_path': stored,
        'caption': label, 'content_type': ctype, 'size': len(content),
        'uploaded_by': user.get('name', ''), 'uploaded_at': now_utc(),
    }
    await db.dewi_rnd_styles.update_one(
        {'id': style_id},
        {'$push': {'design_images': entry}, '$set': {'updated_at': now_utc()}},
    )

    updated = await db.dewi_rnd_styles.find_one({'id': style_id})
    await _record_style_revision(
        db, updated, user,
        [{'field': 'design_images', 'label': 'Foto Desain',
          'old': f'{before_count} foto', 'new': f'{before_count + 1} foto'}],
        revision_name=f'Tambah foto desain: {label}',
        summary=f'Foto desain ditambahkan ({label})',
    )
    return serialize(entry)


@router.delete('/styles/{style_id}/images/{img_id}')
async def delete_style_design_image(
    style_id: str, img_id: str, user: dict = Depends(require_auth),
):
    """Hapus satu foto desain dari style."""
    db = get_db()
    style = await db.dewi_rnd_styles.find_one({'id': style_id})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan')

    images = list(style.get('design_images') or [])
    target = next((im for im in images if isinstance(im, dict) and im.get('id') == img_id), None)
    if not target:
        raise HTTPException(404, 'Foto tidak ditemukan')
    remaining = [im for im in images if not (isinstance(im, dict) and im.get('id') == img_id)]

    await db.dewi_rnd_styles.update_one(
        {'id': style_id},
        {'$set': {'design_images': remaining, 'updated_at': now_utc()}},
    )
    if target.get('storage_path'):
        await db.attachments.update_one(
            {'storage_path': target['storage_path']},
            {'$set': {'is_deleted': True, 'deleted_at': now_utc()}},
        )

    updated = await db.dewi_rnd_styles.find_one({'id': style_id})
    await _record_style_revision(
        db, updated, user,
        [{'field': 'design_images', 'label': 'Foto Desain',
          'old': f'{len(images)} foto', 'new': f'{len(remaining)} foto'}],
        revision_name=f"Hapus foto desain: {target.get('caption') or 'foto'}",
        summary='Foto desain dihapus',
    )
    return {'ok': True, 'total_images': len(remaining)}


# ── BANDINGKAN REVISI STYLE (side-by-side) ──────────────────────────────────

@router.get('/styles/{style_id}/revisions/compare')
async def compare_style_revisions(
    style_id: str,
    left: str = Query('', description="id revisi atau 'current'"),
    right: str = Query('', description="id revisi atau 'current'"),
    user: dict = Depends(require_auth),
):
    """Dua revisi berdampingan: field yang berubah + foto desain masing-masing."""
    db = get_db()
    style = await db.dewi_rnd_styles.find_one({'id': style_id})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan')

    revs = await db.dewi_rnd_revisions.find(
        {'style_id': style_id}).sort('revision_number', -1).to_list(500)
    by_id = {r.get('id'): r for r in revs}

    available = [{
        'id': 'current', 'revision_number': None, 'label': 'Kondisi Sekarang',
        'created_at': _iso(style.get('updated_at')), 'created_by_name': '', 'source': 'live',
    }] + [{
        'id': r.get('id'), 'revision_number': r.get('revision_number'),
        'label': f"#{r.get('revision_number')} — {r.get('revision_name') or 'Revisi'}",
        'created_at': _iso(r.get('created_at')),
        'created_by_name': r.get('created_by_name') or '',
        'source': r.get('source') or 'manual',
    } for r in revs]

    def side(ref: str):
        if ref == 'current':
            return {
                'id': 'current', 'revision_number': None,
                'revision_name': 'Kondisi Sekarang', 'label': 'Kondisi Sekarang',
                'created_at': _iso(style.get('updated_at')), 'created_by_name': '',
                'source': 'live', 'changes_summary': '', 'notes': '',
                'snapshot': _style_snapshot(style), 'has_snapshot': True,
            }
        r = by_id.get(ref)
        if not r:
            return None
        snap = r.get('snapshot') or {}
        return {
            'id': r.get('id'), 'revision_number': r.get('revision_number'),
            'revision_name': r.get('revision_name') or 'Revisi',
            'label': f"#{r.get('revision_number')} — {r.get('revision_name') or 'Revisi'}",
            'created_at': _iso(r.get('created_at')),
            'created_by_name': r.get('created_by_name') or '',
            'source': r.get('source') or 'manual',
            'changes_summary': r.get('changes_summary') or '',
            'notes': r.get('notes') or '',
            'snapshot': snap, 'has_snapshot': bool(snap),
        }

    # Bawaan: revisi terbaru vs kondisi sekarang; bila ada ≥2 revisi → dua revisi terakhir.
    if not left:
        left = revs[1]['id'] if len(revs) >= 2 else (revs[0]['id'] if revs else 'current')
    if not right:
        right = revs[0]['id'] if len(revs) >= 2 else 'current'

    ls, rs = side(left), side(right)
    if ls is None or rs is None:
        raise HTTPException(400, 'Revisi pembanding tidak ditemukan')

    rows = []
    compare_fields = STYLE_TRACKED_FIELDS + [
        ('variants_count', 'Jumlah Varian'), ('techpack_name', 'Tech Pack')]
    for k, label in compare_fields:
        lv = (ls.get('snapshot') or {}).get(k)
        rv = (rs.get('snapshot') or {}).get(k)
        rows.append({
            'key': k, 'label': label,
            'left': '' if lv is None else str(lv),
            'right': '' if rv is None else str(rv),
            'changed': str(lv or '') != str(rv or ''),
        })

    limg = (ls.get('snapshot') or {}).get('design_images') or []
    rimg = (rs.get('snapshot') or {}).get('design_images') or []
    lurls = {i.get('url') for i in limg}
    rurls = {i.get('url') for i in rimg}

    return {
        'style': {
            'id': style.get('id'), 'style_code': style.get('style_code'),
            'style_name': style.get('style_name'), 'status': style.get('status'),
        },
        'available': available,
        'total_revisions': len(revs),
        'left': ls, 'right': rs,
        'fields': rows,
        'changed_count': sum(1 for r in rows if r['changed']),
        'images': {
            'left': limg, 'right': rimg,
            'added': [i for i in rimg if i.get('url') not in lurls],
            'removed': [i for i in limg if i.get('url') not in rurls],
        },
    }
