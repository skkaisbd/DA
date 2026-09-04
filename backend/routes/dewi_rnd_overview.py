"""dewi_rnd — Style Overview + Analytics + Seed Data."""
from datetime import datetime, timedelta
from fastapi import Depends, Query
from database import get_db
from auth import require_auth
from fastapi import HTTPException
from routes.dewi_rnd_shared import router, now_utc, sid, serialize
from utils.waktu import now_wib

# ──────────────────────────────────────────────────────────────────────────────
# STYLE OVERVIEW (semua data terkait per style — untuk detail page)
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/styles/{style_id}/overview')
async def get_style_overview(style_id: str, user: dict = Depends(require_auth)):
    """Return style + all linked documents: variants, samples, patterns, hpp, revisions, tech-packs"""
    db = get_db()

    style = await db.dewi_rnd_styles.find_one({'id': style_id}, {'_id': 0})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan')

    variants    = await db.dewi_rnd_variants.find({'style_id': style_id}, {'_id': 0}).to_list(100)
    samples     = await db.dewi_rnd_sample_requests.find({'style_id': style_id}, {'_id': 0}).sort('created_at', -1).to_list(50)
    patterns    = await db.dewi_rnd_patterns.find({'style_id': style_id}, {'_id': 0}).sort('created_at', -1).to_list(50)
    hpp_records = await db.dewi_rnd_hpp.find({'style_id': style_id}, {'_id': 0}).sort('created_at', -1).to_list(20)
    revisions   = await db.dewi_rnd_revisions.find({'style_id': style_id}, {'_id': 0}).sort('revision_number', -1).to_list(50)
    tech_packs  = await db.dewi_rnd_tech_packs.find({'style_id': style_id}, {'_id': 0}).sort('created_at', -1).to_list(20)
    costings    = await db.dewi_rnd_sample_costing.find({'style_id': style_id}, {'_id': 0}).sort('created_at', -1).to_list(20)

    def fmt_list(docs):
        out = []
        for d in docs:
            d2 = dict(d)
            for k, v in d2.items():
                if isinstance(v, datetime):
                    d2[k] = v.isoformat()
            out.append(d2)
        return out

    style2 = serialize(style)
    return {
        'style':       style2,
        'variants':    fmt_list(variants),
        'samples':     fmt_list(samples),
        'patterns':    fmt_list(patterns),
        'hpp_records': fmt_list(hpp_records),
        'revisions':   fmt_list(revisions),
        'tech_packs':  fmt_list(tech_packs),
        'costings':    fmt_list(costings),
        'summary': {
            'total_variants':   len(variants),
            'total_samples':    len(samples),
            'total_patterns':   len(patterns),
            'total_hpp':        len(hpp_records),
            'total_revisions':  len(revisions),
            'total_tech_packs': len(tech_packs),
            'total_costings':   len(costings),
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# ANALYTICS
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/analytics')
async def get_analytics(user: dict = Depends(require_auth)):
    """Get RnD analytics"""
    db = get_db()

    total_styles     = await db.dewi_rnd_styles.count_documents({})
    active_styles    = await db.dewi_rnd_styles.count_documents({'status': 'active'})
    total_samples    = await db.dewi_rnd_sample_requests.count_documents({})
    pending_samples  = await db.dewi_rnd_sample_requests.count_documents({'status': 'submitted'})
    approved_samples = await db.dewi_rnd_sample_requests.count_documents({'status': 'approved'})
    total_materials  = await db.dewi_rnd_materials.count_documents({})
    active_materials = await db.dewi_rnd_materials.count_documents({'status': 'active'})
    total_revisions  = await db.dewi_rnd_revisions.count_documents({})

    return {
        'styles': {
            'total': total_styles,
            'active': active_styles,
        },
        'sample_requests': {
            'total': total_samples,
            'pending': pending_samples,
            'approved': approved_samples,
        },
        'materials': {
            'total': total_materials,
            'active': active_materials,
        },
        'revisions': {
            'total': total_revisions,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# SEED DATA
# ──────────────────────────────────────────────────────────────────────────────

@router.post('/seed')
async def seed_rnd_data(
    reset: bool = Query(True, description='Hapus data demo lama sebelum seed'),
    user: dict = Depends(require_auth),
):
    """Seed demo RnD data — kaya & idempotent."""
    db = get_db()
    uid = user['id']
    uname = user.get('name', '')

    if reset:
        await db.dewi_rnd_styles.delete_many({'is_demo': True})
        await db.dewi_rnd_sample_requests.delete_many({'is_demo': True})
        await db.dewi_rnd_revisions.delete_many({'is_demo': True})
        await db.dewi_rnd_materials.delete_many({'is_demo': True})
        await db.dewi_rnd_sample_costing.delete_many({'is_demo': True})
        # 2026-08-08: varian demo IKUT dibersihkan, kalau tidak seed ulang akan
        # menumpuk varian kembar (dan `POST /variants` menolak 409 karena warnanya
        # sudah terpakai) — seed harus tetap idempoten.
        await db.dewi_rnd_variants.delete_many({'is_demo': True})
        await db.dewi_rnd_hpp.delete_many({'is_demo': True})

    # ── STYLES ────────────────────────────────────────────────────────────
    style_seed = [
        ('ST-DEMO-001', 'Basic Tee Premium',     'T-Shirt', 'Zara',      'Cotton Combed 30s',  'Spring 2024', 'active', 'Classic crew neck t-shirt premium'),
        ('ST-DEMO-002', 'Polo Shirt Classic',    'Polo',    'Uniqlo',    'Pique Cotton',        'Summer 2024', 'active', 'Classic polo with collar'),
        ('ST-DEMO-003', 'Hoodie Oversized',      'Hoodie',  'H&M',       'Fleece Cotton 320',   'Fall 2024',   'active', 'Oversized hoodie streetwear'),
        ('ST-DEMO-004', 'Long Sleeve Heritage',  'T-Shirt', 'Zara',      'Cotton Combed 24s',   'Fall 2024',   'draft',  'Heritage style long sleeve'),
        ('ST-DEMO-005', 'Crewneck Sweatshirt',   'Sweater', 'Pull&Bear', 'Fleece Cotton 280',   'Winter 2024', 'active', 'Crewneck heavyweight sweatshirt'),
        ('ST-DEMO-006', 'Jogger Pants Slim',     'Pants',   'Uniqlo',    'Stretch Twill',       'Summer 2024', 'active', 'Slim fit jogger with elastic waist'),
        ('ST-DEMO-007', 'Bomber Jacket Light',   'Jacket',  'Pull&Bear', 'Nylon Taslan',        'Spring 2025', 'review', 'Lightweight bomber jacket'),
    ]
    styles = []
    for code, name, cat, buyer, fabric, season, status, desc in style_seed:
        styles.append({
            'id': sid(),
            'style_code': code,
            'style_name': name,
            'category': cat,
            'buyer': buyer,
            'fabric_type': fabric,
            'season': season,
            'description': desc,
            'status': status,
            'techpack_url': None,
            'techpack_name': None,
            'design_images': [],
            'variants': [
                {'size': 'S', 'color': 'Black', 'sku': f'{code}-S-BLK'},
                {'size': 'M', 'color': 'Black', 'sku': f'{code}-M-BLK'},
                {'size': 'L', 'color': 'White', 'sku': f'{code}-L-WHT'},
            ],
            'is_demo': True,
            'created_by': uid,
            'created_by_name': uname,
            'created_at': now_utc(),
            'updated_at': now_utc(),
        })
    if styles:
        await db.dewi_rnd_styles.insert_many(styles)

    # ── MATERIALS ─────────────────────────────────────────────────────────
    material_seed = [
        ('FAB-DEMO-001', 'Cotton Combed 30s',  'Fabric',    'PT Textile Indo',   '100% Cotton',                180, 25000,  100, 'Shrinkage: 3%, Color fastness: Grade 4',   'Premium segment'),
        ('FAB-DEMO-002', 'Pique Cotton',       'Fabric',    'PT Textile Indo',   '100% Cotton',                220, 35000,  100, 'Shrinkage: 2%, Color fastness: Grade 4-5', 'Polo shirt'),
        ('FAB-DEMO-003', 'Fleece Cotton 320',  'Fabric',    'PT Sentral Kain',   '80% Cotton, 20% Polyester',  320, 55000,  150, 'Shrinkage: 4%, Pilling: Grade 4',          'Heavy hoodie'),
        ('FAB-DEMO-004', 'Stretch Twill',      'Fabric',    'PT Sentral Kain',   '97% Cotton, 3% Spandex',     230, 42000,  150, 'Stretch recovery: 90%',                    'Jogger pants'),
        ('FAB-DEMO-005', 'Nylon Taslan',       'Fabric',    'PT Bahan Asia',     '100% Nylon',                  90, 38000,  200, 'Water repellent: Grade 4',                 'Light jacket'),
        ('AKS-DEMO-001', 'Tag Karton Premium', 'Accessory', 'PT Aksesoris Jaya', 'Karton 300gsm + Foil',        12,  1200, 1000, 'Print quality: A',                         'Branding tag'),
        ('AKS-DEMO-002', 'Resleting YKK 7"',  'Accessory', 'YKK Indonesia',     'Metal Brass',                 10,  4500,  500, 'Cycle test: 5000+',                        'Jacket / Pants'),
        ('BNG-DEMO-001', 'Benang Polyester',   'Thread',    'PT Benang Sentosa', '100% Polyester Spun',          1,  3500,  100, 'Tensile: high',                            'General sewing'),
    ]
    materials = []
    for code, name, cat, vendor, comp, weight, price, moq, test, notes in material_seed:
        materials.append({
            'id': sid(),
            'material_code': code,
            'material_name': name,
            'category': cat,
            'vendor': vendor,
            'composition': comp,
            'weight': weight,
            'price_per_meter': price,
            'min_order_qty': moq,
            'test_results': test,
            'notes': notes,
            'status': 'active',
            'is_demo': True,
            'created_by': uid,
            'created_by_name': uname,
            'created_at': now_utc(),
            'updated_at': now_utc(),
        })
    if materials:
        await db.dewi_rnd_materials.insert_many(materials)

    # ── SAMPLE REQUESTS ──────────────────────────────────────────────────
    today_str = now_wib().strftime('%Y%m%d')
    sample_specs = [
        (styles[0], 5,  'high',   2,  'submitted', None,       'Urgent for client presentation'),
        (styles[1], 3,  'normal', 5,  'approved',  'approved', 'Standard sample run'),
        (styles[2], 6,  'high',   3,  'submitted', None,       'Pre-production for Fall capsule'),
        (styles[3], 4,  'low',    10, 'draft',     None,       'Initial sketch — pending design lock'),
        (styles[4], 3,  'normal', 7,  'approved',  'approved', 'Confirmed by buyer'),
        (styles[5], 8,  'high',   4,  'rejected',  'rejected', 'Fabric stretch insufficient'),
    ]
    sample_requests = []
    for idx, (style, qty, prio, due_days, status, approval, notes) in enumerate(sample_specs, start=1):
        is_decided = status in ('approved', 'rejected')
        sample_requests.append({
            'id': sid(),
            'sample_code': f'SR-DEMO-{today_str}-{idx:03d}',
            'style_id': style['id'],
            'style_code': style['style_code'],
            'style_name': style['style_name'],
            'quantity': qty,
            'priority': prio,
            'due_date': (now_utc() + timedelta(days=due_days)).isoformat(),
            'notes': notes,
            'status': status,
            'approval_status': approval,
            'approved_by': uid if is_decided else None,
            'approved_by_name': uname if is_decided else None,
            'approved_at': now_utc() if is_decided else None,
            'approval_notes': (
                'Looks good' if approval == 'approved'
                else 'Need revision' if approval == 'rejected'
                else None
            ),
            'is_demo': True,
            'created_by': uid,
            'created_by_name': uname,
            'created_at': now_utc(),
            'updated_at': now_utc(),
        })
    if sample_requests:
        await db.dewi_rnd_sample_requests.insert_many(sample_requests)

    # ── REVISIONS ────────────────────────────────────────────────────────
    revisions = []
    rev_specs = [
        (styles[0], 'Rev 1 — Logo Update',    'Reposition logo dada kiri',        'Permintaan buyer'),
        (styles[0], 'Rev 2 — Fit Adjustment', 'Body length +2cm, sleeve +1cm',     'Hasil fitting sample 1'),
        (styles[2], 'Rev 1 — Pocket Detail',  'Tambah hidden pocket di dalam',     'Request brand identity'),
        (styles[3], 'Rev 1 — Color Block',    'Sleeve kontras warna abu',          'Trend research Fall 24'),
        (styles[6], 'Rev 1 — Lining Change',  'Ganti lining ke mesh untuk breath', 'Feedback wear-test'),
    ]
    rev_counter: dict = {}
    for style, name, summary, reason in rev_specs:
        n = rev_counter.get(style['id'], 0) + 1
        rev_counter[style['id']] = n
        revisions.append({
            'id': sid(),
            'style_id': style['id'],
            'style_code': style['style_code'],
            'revision_number': n,
            'revision_name': name,
            'changes_summary': summary,
            'reason': reason,
            'previous_revision_id': None,
            'is_demo': True,
            'created_by': uid,
            'created_by_name': uname,
            'created_at': now_utc(),
        })
    if revisions:
        await db.dewi_rnd_revisions.insert_many(revisions)

    # ── SAMPLE COSTING (untuk SR yang sudah approved) ────────────────────
    costing = []
    for sr in sample_requests:
        if sr['status'] != 'approved':
            continue
        bom_lines = [
            {
                'material_code': materials[0]['material_code'],
                'material_name': materials[0]['material_name'],
                'qty': 1.5, 'unit': 'm',
                'unit_cost': materials[0]['price_per_meter'],
                'total_cost': int(1.5 * materials[0]['price_per_meter']),
            },
            {
                'material_code': materials[5]['material_code'],
                'material_name': materials[5]['material_name'],
                'qty': 1, 'unit': 'pcs',
                'unit_cost': materials[5]['price_per_meter'],
                'total_cost': materials[5]['price_per_meter'],
            },
            {
                'material_code': materials[7]['material_code'],
                'material_name': materials[7]['material_name'],
                'qty': 200, 'unit': 'm',
                'unit_cost': materials[7]['price_per_meter'],
                'total_cost': 200 * materials[7]['price_per_meter'],
            },
        ]
        total_material = sum(line['total_cost'] for line in bom_lines)
        labor = 25000
        overhead = 10000
        costing.append({
            'id': sid(),
            'sample_request_id': sr['id'],
            'sample_code': sr['sample_code'],
            'bom_lines': bom_lines,
            'total_material_cost': total_material,
            'labor_cost': labor,
            'overhead_cost': overhead,
            'total_cost': total_material + labor + overhead,
            'notes': 'Costing demo — perkiraan untuk presentasi internal',
            'is_demo': True,
            'created_by': uid,
            'created_by_name': uname,
            'created_at': now_utc(),
            'updated_at': now_utc(),
        })
    if costing:
        await db.dewi_rnd_sample_costing.insert_many(costing)

    # ── DAFTAR UKURAN + VARIAN NYATA (2026-08-08) ────────────────────────
    # Kenapa ditambahkan: seeder ini dulu hanya menulis `styles[].variants[]`
    # (bentuk LAMA yang tertanam di dokumen style) dan TIDAK PERNAH mengisi
    # `dewi_rnd_styles.size_list` atau koleksi `dewi_rnd_variants`. Akibatnya di
    # database hasil bootstrap yang bersih, layar **Varian**, **Padankan Ukuran**,
    # dan promosi ke produksi semuanya KOSONG — fitur-fiturnya tidak bisa dipakai
    # maupun diperiksa tanpa mengetik data manual lebih dulu.
    #
    # Daftar ukurannya SENGAJA bercampur: ada yang persis master (`S/M/L/XL`),
    # ada teks bebas yang butuh alias (`2XL`), dan ada yang memang tidak ada di
    # master (`28/30`, `32/34`) — supaya layar "Padankan Ukuran" punya pekerjaan
    # SUNGGUHAN, bukan tabel kosong.
    size_plan = {
        'ST-DEMO-001': ['S', 'M', 'L', 'XL'],
        'ST-DEMO-002': ['S', 'M', 'L', 'XL', '2XL'],
        'ST-DEMO-003': ['M', 'L', 'XL', '2XL', '3XL'],
        'ST-DEMO-004': ['All Size'],
        'ST-DEMO-005': ['M', 'L', 'XL'],
        'ST-DEMO-006': ['28/30', '32/34', '36/38'],
        'ST-DEMO-007': ['M', 'L', 'XL', 'Free Size'],
    }
    color_plan = {
        'ST-DEMO-001': ['PTH', 'HTM', 'NVY'],
        'ST-DEMO-002': ['NVY', 'MRH'],
        'ST-DEMO-003': ['HTM', 'ABU'],
        'ST-DEMO-004': ['KRM'],
        'ST-DEMO-005': ['ABU', 'HJU'],
        'ST-DEMO-006': ['HTM', 'NVY'],
        'ST-DEMO-007': ['HJU'],
    }

    from routes.dewi_rnd_sizes import build_size_map, compute_size_range, pick_base_size
    from routes.dewi_rnd_colors import _norm_sizes, _resolve_color, hex_of_variant

    rnd_variants, sized_styles = [], 0
    for st in styles:
        labels = size_plan.get(st['style_code'])
        if not labels:
            continue
        size_map = await build_size_map(db, labels)
        await db.dewi_rnd_styles.update_one({'id': st['id']}, {'$set': {
            'size_list': labels,
            'size_map': size_map,
            'base_size': pick_base_size(labels),
            'size_range': compute_size_range(labels),
            'size_list_updated_at': now_utc(),
            'size_list_updated_by': uname,
        }})
        sized_styles += 1

        for ccode in color_plan.get(st['style_code'], []):
            cdoc, _ = await _resolve_color(db, {'code': ccode}, allow_create=True)
            if not cdoc:
                continue
            rnd_variants.append({
                'id': sid(),
                'style_id': st['id'],
                'style_code': st['style_code'],
                'style_name': st['style_name'],
                'color_id': cdoc['id'],
                'color': cdoc.get('name') or ccode,
                'color_code': cdoc.get('code') or ccode,
                'color_hex': hex_of_variant(cdoc) if cdoc.get('hex') else '#CCCCCC',
                'sizes': _norm_sizes([{'size': s, 'qty_plan': 25} for s in labels],
                                     style_code=st['style_code'],
                                     color_code=cdoc.get('code') or ccode),
                'status': 'active',
                'notes': 'Varian demo seed',
                'sku_convention': 'ssot',
                'is_demo': True,
                'created_by': uid,
                'created_by_name': uname,
                'created_at': now_utc(),
                'updated_at': now_utc(),
            })
    if rnd_variants:
        await db.dewi_rnd_variants.insert_many(rnd_variants)

    # ── HPP DEMO (2026-08-08) ────────────────────────────────────────────
    # Alasan yang sama seperti varian di atas: daftar HPP KOSONG di database
    # bersih, sehingga tanda "harga master sudah berubah" (permintaan owner) tidak
    # punya satu baris pun untuk ditandai dan tidak bisa dinilai siapa pun.
    #
    # Dihitung lewat `compute_cost_lines()` + `_calculate_hpp()` — fungsi yang SAMA
    # dipakai endpoint sungguhan — supaya angkanya bukan angka karangan seeder.
    # Satu dokumen HYBRID (master + manual) supaya sumber per-baris kelihatan, dan
    # satu dokumen bergaya LAMA (tanpa cost_lines) supaya jalur kompatibilitas
    # mundur ikut terwakili di layar.
    from routes.dewi_rnd_hpp import compute_cost_lines, _calculate_hpp

    master_priced = await db.rahaza_materials.find(
        {'unit_cost': {'$gt': 0}, 'type': {'$ne': 'fg'}},
        {'_id': 0, 'id': 1, 'code': 1, 'name': 1, 'unit_cost': 1},
    ).to_list(3)

    hpp_docs = []
    hybrid_style = next((s for s in styles if s['style_code'] == 'ST-DEMO-001'), None)
    if hybrid_style and master_priced:
        raw = [{'label': f"Bahan {m['name']}", 'source': 'master',
                'material_id': m['id'], 'qty': 1.5, 'unit': 'pcs'}
               for m in master_priced[:2]]
        raw.append({'label': 'Jahit & finishing (manual)', 'source': 'manual',
                    'qty': 1, 'unit': 'pcs', 'unit_cost_used': 12000})
        total, lines = await compute_cost_lines(db, raw)
        body = {'cmt_cost_per_pcs': 15000, 'cutting_cost_per_pcs': 2000,
                'packaging_cost_per_pcs': 1500, 'overhead_pct': 10, 'margin_pct': 30}
        hpp_docs.append({
            'id': sid(), 'hpp_code': 'HPP-DEMO-001',
            'style_id': hybrid_style['id'], 'style_code': hybrid_style['style_code'],
            'style_name': hybrid_style['style_name'],
            'fabric_usage_per_pcs': 0, 'fabric_price_per_meter': 0,
            'fabric_source': 'manual', 'fabric_size': '',
            'accessories_cost': [], 'cmt_cost_source': 'manual', 'cmt_cost_ref': '',
            'use_bom': False, 'bom_breakdown': [], 'cost_lines': lines,
            'notes': 'HPP demo hybrid — sumber biaya per baris (Master + Manual)',
            'status': 'draft', **body,
            **_calculate_hpp(body, cost_lines_total=total),
            'is_demo': True, 'created_by': uid, 'created_by_name': uname,
            'created_at': now_utc(), 'updated_at': now_utc(),
        })

    legacy_style = next((s for s in styles if s['style_code'] == 'ST-DEMO-002'), None)
    if legacy_style:
        body = {'fabric_usage_per_pcs': 1.8, 'fabric_price_per_meter': 35000,
                'accessories_cost': [{'name': 'Tag Karton', 'unit_cost': 1200, 'qty': 1},
                                     {'name': 'Benang', 'unit_cost': 800, 'qty': 1}],
                'cmt_cost_per_pcs': 18000, 'cutting_cost_per_pcs': 2500,
                'packaging_cost_per_pcs': 1500, 'overhead_pct': 10, 'margin_pct': 35}
        hpp_docs.append({
            'id': sid(), 'hpp_code': 'HPP-DEMO-002',
            'style_id': legacy_style['id'], 'style_code': legacy_style['style_code'],
            'style_name': legacy_style['style_name'],
            'fabric_source': 'manual', 'fabric_size': '',
            'cmt_cost_source': 'manual', 'cmt_cost_ref': '',
            'use_bom': False, 'bom_breakdown': [], 'cost_lines': [],
            'notes': 'HPP demo gaya lama — dibaca sebagai baris Manual, angka tidak diubah',
            'status': 'draft', **body, **_calculate_hpp(body),
            'is_demo': True, 'created_by': uid, 'created_by_name': uname,
            'created_at': now_utc(), 'updated_at': now_utc(),
        })
    if hpp_docs:
        await db.dewi_rnd_hpp.insert_many(hpp_docs)

    return {
        'success': True,
        'reset': reset,
        'styles': len(styles),
        'materials': len(materials),
        'sample_requests': len(sample_requests),
        'revisions': len(revisions),
        'sample_costing': len(costing),
        'styles_with_size_list': sized_styles,
        'rnd_variants': len(rnd_variants),
        'hpp_records': len(hpp_docs),
    }
