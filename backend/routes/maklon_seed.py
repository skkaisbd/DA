"""Seeder Maklon SOMMERVILLE (AD-4: fresh re-seed berbasis production_jobs).

POST /api/seed/maklon-full (admin) — idempoten: demo PO lama dihapus via
cascade_delete_po lalu dibuat ulang, master & user di-upsert.

Menghasilkan:
  - Klien maklon  : dewi_maklon_clients (PT Aruna Activewear)
  - Vendor CMT    : vendor_partners (CV Jahit Mitra CMT) + user cmt_vendor
  - User klien    : klienmaklon@dewiaditya.id (role klien_maklon, buyer_id → klien)
  - PO-MK-DEMO-1  : Draft (2 item + 2 aksesoris) — bahan latihan alur penuh
  - PO-MK-DEMO-2  : In Production — vendor shipment Received + inspeksi (5 missing)
                    → production job + job items → progress parsial → dispatch #1
                    → mirror finance dewi_maklon_pos + Draft AR Invoice
"""
import json as _json
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, check_role, hash_password
from core.helpers import new_id, now
from cascade_delete import cascade_delete_po
from routes.production_rbac import PROD_ADMIN_ROLES
from routes.production_maklon_bridge import sync_po_to_maklon_finance
from routes.production_internal_adapter import (
    explode_po_accessories_from_bom, create_internal_job,
    resolve_operator_process, insert_wip_mirror,
)
from core import material_fields  # FASE 6.6-B: SSOT nama field + alias legacy yarn_*
from core import location_resolver  # FASE 12: SSOT peta zona penyimpanan

router = APIRouter(prefix="/api/seed", tags=["seed"])

_DEFAULT_CLIENT_ID = 'mk-client-demo-1'
_DEFAULT_VENDOR_ID = 'mk-vendor-demo-1'
# Module defaults. seed_maklon_full() rebinds these as LOCALS to the effective
# (possibly pre-existing same-code) id returned by _upsert — see reconcile note.
CLIENT_ID = _DEFAULT_CLIENT_ID
VENDOR_ID = _DEFAULT_VENDOR_ID
PO1_ID = 'po-mk-demo-1'
PO2_ID = 'po-mk-demo-2'
# Buyer Catalog articles (master produk maklon) — di-link ke po_items demo agar
# Panduan Produksi (SOP) buyer-catalog terlihat oleh vendor CMT via production-guide.
CAT_HOODIE = 'mk-cat-demo-hoodie'   # Jaket Hoodie Aruna (ARN-HD)
CAT_POLO   = 'mk-cat-demo-polo'     # Kaos Polo Aruna   (ARN-PL)


def _mk_catalog_doc(cat_id, artikel_code, product_name, colors, sizes, cmt_price, sop_steps, videos, t, client_id=None):
    """Bangun 1 dokumen buyer-catalog + varian ber-SKU + SOP (idempoten via upsert)."""
    variants = []
    ccode_map = {'navy': 'NVY', 'putih': 'PTH', 'hitam': 'HTM', 'abu-abu': 'ABU', 'biru': 'BIRU'}
    for color in colors:
        cc = ccode_map.get(color.strip().lower(), color.strip().upper()[:3])
        for size in sizes:
            variants.append({
                'id': f'{cat_id}-{cc}-{size}'.lower(),
                'sku': f'{artikel_code}-{cc}-{size}',
                'color': color, 'color_code': cc, 'size': size,
                'buyer_ref_code': '', 'active': True,
            })
    steps = []
    for i, (title, desc) in enumerate(sop_steps):
        steps.append({'id': f'{cat_id}-sop-{i+1}', 'seq': i + 1, 'title': title,
                      'description': desc, 'image_path': ''})
    return {
        'id': cat_id, 'client_id': client_id or CLIENT_ID, 'client_name': 'PT Aruna Activewear',
        'client_code': 'ARNA', 'artikel_code': artikel_code, 'buyer_ref_code': '',
        'product_name': product_name, 'category': 'Garment', 'season': '', 'gender': 'Unisex',
        'default_cmt_price': float(cmt_price), 'default_selling_price': float(cmt_price) * 3,
        'color_options': colors, 'size_options': sizes, 'variants': variants,
        'description': f'Artikel demo maklon — {product_name}',
        'hero_image_url': '', 'status': 'active',
        'sop_steps': steps,
        'reference_videos': videos,
        'reference_images': [],
        'sop_updated_at': t, 'sop_updated_by': 'seed',
        'total_qty_produced': 0, 'total_revenue': 0.0, 'last_used_at': None,
        'price_history': [], 'created_at': t, 'updated_at': t, 'created_by': 'seed',
    }


# ── FASE 5: fixture internal demo (fixed IDs, idempoten) ─────────────────────
INT_PO1 = 'po-int-demo-1'   # Draft — bahan E2E create→confirm
INT_PO2 = 'po-int-demo-2'   # In Production — MI issued + progress + dispatch #1
INT_PO3 = 'po-int-demo-3'   # In Production — MI draft (aksi gudang)
INT_MODEL = 'int-demo-model-1'
INT_BOM = 'int-demo-bom-1'
INT_EMP = 'int-demo-op-1'
INT_LOC = 'int-demo-loc-1'
# Module defaults; seed_maklon_full() rebinds INT_MODEL/INT_EMP/INT_LOC as
# LOCALS to the effective (possibly reconciled) id returned by _upsert.
_DEFAULT_INT_MODEL = INT_MODEL
_DEFAULT_INT_EMP = INT_EMP
_DEFAULT_INT_LOC = INT_LOC
INT_MAT_YARN_CODE = 'YRN-DA-CTN'
INT_MAT_ACC_CODE = 'ACC-DA-LBL'


async def _storage_zone_for(db, material_type: str, fallback: str) -> str:
    """FASE 12 — zona penyimpanan KANONIK untuk sebuah tipe material.

    AKAR MASALAH YANG DITUTUP DI SINI (backlog `HANDOFF_NEXT_AGENT.md` #3):
    seeder ini dulu menaruh SEMUA stok demo di lokasi pseudo `GDG-UTAMA-DEMO`
    (`int-demo-loc-1`) yang **bukan zona penyimpanan** — tidak pernah muncul di
    dropdown lokasi (`location_resolver.list_storage_locations` hanya memuat
    `STORAGE_RAHAZA_CODES`), tidak terlihat di Put-Away maupun Opname per-bin,
    dan membuat "peta gudang" berantakan setiap kali di-seed ulang. Itu juga
    pemicu BUG-1 FASE 10 (pengeluaran aksesoris 500 karena stok tersebar).

    Sekarang stok demo mendarat di zona yang benar: Bahan → ZNA-KAIN,
    Aksesoris → ZNA-AKSESORIS, Produk Jadi → ZNA-FG. `fallback` dipakai hanya
    bila struktur zona sama sekali belum ada (mis. DB kosong).
    """
    try:
        idx = await location_resolver.storage_location_index(db)
        role = material_fields.storage_role_of(material_type)
        return (idx.get('roles') or {}).get(role) or fallback
    except Exception:
        return fallback


_RECONCILE_KEYS = ('code', 'employee_code')


async def _upsert(db, coll, doc):
    """Idempotent upsert by `id`, safe across seed generations.

    Some collections enforce a UNIQUE index on a business key (`code` for
    dewi_maklon_clients/vendor_partners/rahaza_models/…, `employee_code` for
    rahaza_employees). If another demo seed already created a record with the
    same business key under a DIFFERENT `id`, a plain upsert-by-id would insert
    a duplicate and raise DuplicateKeyError on the unique index (→ HTTP 500).
    To stay idempotent we instead UPDATE that pre-existing record in place
    (keeping its canonical id) and RETURN the effective id, so callers can
    rebind their id variable and keep ALL downstream references consistent
    against a single coherent record.
    """
    for key in _RECONCILE_KEYS:
        val = doc.get(key)
        if val:
            existing = await db[coll].find_one({key: val}, {'id': 1})
            if existing and existing.get('id') and existing['id'] != doc.get('id'):
                eff_id = existing['id']
                await db[coll].update_one({'id': eff_id}, {'$set': {**doc, 'id': eff_id}})
                return eff_id
    await db[coll].update_one({'id': doc['id']}, {'$set': doc}, upsert=True)
    return doc['id']


@router.post("/maklon-full")
async def seed_maklon_full(request: Request):
    user = await require_auth(request)
    if not check_role(user, PROD_ADMIN_ROLES):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    t = now()

    # ── 1. Masters ─────────────────────────────────────────────────────────
    # Reconcile against any pre-existing same-`code` records (another demo seed
    # may have created 'ARNA'/'JMC' under different ids). _upsert returns the
    # effective id; we rebind CLIENT_ID/VENDOR_ID (local) so ALL downstream
    # references (buyer_id, vendor_id, cmt_vendor_id, catalog client_id) point
    # to a single coherent record instead of duplicating → no DuplicateKeyError.
    _pref_client, _pref_vendor = _DEFAULT_CLIENT_ID, _DEFAULT_VENDOR_ID
    CLIENT_ID = await _upsert(db, 'dewi_maklon_clients', {
        'id': _pref_client, 'code': 'ARNA', 'name': 'PT Aruna Activewear',
        'contact_name': 'Bu Sari', 'contact_phone': '0812-1111-2222',
        'address': 'Bandung', 'notes': 'Klien demo maklon SOMMERVILLE',
        'active': True, 'created_at': t, 'updated_at': t,
    })
    VENDOR_ID = await _upsert(db, 'vendor_partners', {
        'id': _pref_vendor, 'code': 'JMC', 'name': 'CV Jahit Mitra CMT',
        'contact_name': 'Pak Budi', 'contact_phone': '0813-3333-4444',
        'address': 'Sragen', 'notes': 'Vendor CMT demo maklon SOMMERVILLE',
        'active': True, 'is_active': True,
        # M3 KAPASITAS (Fase 4) — kapasitas jahit demo
        'capacity_pcs': 200, 'capacity_note': 'Kapasitas jahit demo (2 lini)',
        'created_at': t, 'updated_at': t,
    })

    # ── 1b. Buyer Catalog (master produk maklon) + SOP (Panduan Produksi) ────
    # Di-link ke po_items demo agar SOP terlihat vendor CMT via /production-jobs/{id}/production-guide.
    await _upsert(db, 'dewi_maklon_buyer_catalog', _mk_catalog_doc(
        CAT_HOODIE, 'ARN-HD', 'Jaket Hoodie Aruna', ['Navy'], ['M', 'L'], 18000,
        sop_steps=[
            ('Potong kain fleece', 'Gelar kain fleece 320gsm, potong sesuai pola hoodie size M/L. Toleransi ±0.5cm.'),
            ('Jahit body & hood', 'Gabungkan panel depan-belakang, pasang hood 2 lapis, obras semua tepi.'),
            ('Pasang zipper & kordon', 'Pasang zipper YKK 60cm rata, masukkan kordon pada hood, bartack ujung.'),
            ('Finishing & QC', 'Buang benang sisa, setrika uap, cek ukuran & kerapian jahitan, lipat + polybag.'),
        ],
        videos=[{'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'title': 'Referensi jahit hoodie'}],
        t=t, client_id=CLIENT_ID,
    ))
    await _upsert(db, 'dewi_maklon_buyer_catalog', _mk_catalog_doc(
        CAT_POLO, 'ARN-PL', 'Kaos Polo Aruna', ['Putih'], ['M', 'L'], 12000,
        sop_steps=[
            ('Potong kain pique', 'Gelar kain pique cotton, potong pola polo size M/L sesuai marker.'),
            ('Jahit body & kerah', 'Gabungkan badan, pasang kerah rib + placket kancing 3 lubang.'),
            ('Pasang kancing & finishing', 'Pasang 3 kancing, jahit label ukuran & brand, obras rapi.'),
            ('QC & packing', 'Cek jahitan kerah, ukuran, noda; setrika; lipat + polybag per pcs.'),
        ],
        videos=[],
        t=t, client_id=CLIENT_ID,
    ))

    # ── 1c. BOM Templates aktif (Fase 4: dasar rekap aksesoris turunan BOM) ──
    # Aksesoris per-pcs → rekap = qty_per_pcs × po_items.qty. Upsert by (buyer_catalog_id, version=1).
    async def _bom(catalog_id, materials):
        doc = {
            'id': f'bom-{catalog_id}', 'buyer_catalog_id': catalog_id, 'version': 1,
            'version_label': 'Initial (seed)', 'is_active': True, 'materials': materials,
            'notes': 'BOM demo (Fase 4 rekap aksesoris)', 'created_at': t, 'updated_at': t,
        }
        await db.dewi_maklon_bom_templates.update_one(
            {'id': doc['id']}, {'$set': doc}, upsert=True)
    await _bom(CAT_HOODIE, [
        {'material_name': 'Kain Fleece 320gsm', 'category': 'Kain', 'unit': 'meter', 'qty_per_pcs': 1.5, 'cost_per_unit': 45000, 'supplier': ''},
        {'material_name': 'Zipper YKK 60cm', 'category': 'Aksesoris', 'unit': 'pcs', 'qty_per_pcs': 1, 'cost_per_unit': 8000, 'supplier': ''},
        {'material_name': 'Kordon Hoodie', 'category': 'Aksesoris', 'unit': 'pcs', 'qty_per_pcs': 1, 'cost_per_unit': 2000, 'supplier': ''},
        {'material_name': 'Label Woven Aruna', 'category': 'Aksesoris', 'unit': 'pcs', 'qty_per_pcs': 1, 'cost_per_unit': 1500, 'supplier': ''},
    ])
    await _bom(CAT_POLO, [
        {'material_name': 'Kain Pique Cotton', 'category': 'Kain', 'unit': 'meter', 'qty_per_pcs': 0.8, 'cost_per_unit': 38000, 'supplier': ''},
        {'material_name': 'Kancing Polo', 'category': 'Aksesoris', 'unit': 'pcs', 'qty_per_pcs': 3, 'cost_per_unit': 500, 'supplier': ''},
        {'material_name': 'Label Woven Aruna', 'category': 'Aksesoris', 'unit': 'pcs', 'qty_per_pcs': 1, 'cost_per_unit': 1500, 'supplier': ''},
    ])

    # ── 2. Users (idempoten) ────────────────────────────────────────────────
    users_seeded = []
    for email, name, role, extra in [
        ('cmtvendor@dewiaditya.id', 'CV Jahit Mitra CMT (Vendor)', 'cmt_vendor', {'cmt_vendor_id': VENDOR_ID}),
        ('klienmaklon@dewiaditya.id', 'PT Aruna Activewear (Klien)', 'klien_maklon', {'buyer_id': CLIENT_ID}),
    ]:
        existing = await db.users.find_one({'email': email})
        if existing:
            await db.users.update_one({'email': email}, {'$set': {'role': role, **extra, 'status': 'active', 'updated_at': t}})
        else:
            await db.users.insert_one({
                'id': new_id(), 'name': name, 'email': email,
                'password': hash_password('Dewi@123'), 'role': role,
                'status': 'active', **extra, 'created_at': t, 'updated_at': t,
            })
        users_seeded.append(email)

    # ── 3. Fresh re-seed PO demo (cascade delete dulu) ─────────────────────
    for pid in (PO1_ID, PO2_ID):
        if await db.production_pos.find_one({'id': pid}):
            await cascade_delete_po(pid)
        await db.dewi_maklon_pos.delete_one({'id': pid})
        await db.rahaza_ar_invoices.delete_many({'linked_maklon_po_id': pid})

    def po_item(po_id, po_number, pid, name, sku, size, color, serial, qty, cmt,
                catalog_item_id=None, maklon_variant_id=None, buyer_ref=''):
        return {
            'id': pid, 'po_id': po_id, 'po_number': po_number,
            'product_id': None, 'product_name': name, 'variant_id': None,
            # [RELATION FIX] tautkan ke master data buyer-catalog + varian ber-SKU
            'catalog_item_id': catalog_item_id, 'maklon_variant_id': maklon_variant_id,
            # [DISPLAY FIX] kode artikel milik buyer (referensi) — kini ikut ke job item & tampil di portal vendor/produksi.
            'buyer_ref_code': buyer_ref,
            'size': size, 'color': color, 'sku': sku, 'qty': qty,
            'serial_number': serial,
            'selling_price_snapshot': 0.0, 'cmt_price_snapshot': float(cmt),
            'created_at': t,
        }

    # ── PO 1: Draft ─────────────────────────────────────────────────────────
    await db.production_pos.insert_one({
        'id': PO1_ID, 'po_number': 'PO-MK-DEMO-1',
        'customer_name': 'PT Aruna Activewear', 'buyer_id': CLIENT_ID,
        'vendor_id': VENDOR_ID, 'vendor_name': 'CV Jahit Mitra CMT',
        'po_date': t, 'deadline': None, 'delivery_deadline': None,
        'status': 'Draft', 'notes': 'Demo maklon — alur belum dimulai',
        'business_type': 'maklon',
        'created_by': 'seed', 'created_at': t, 'updated_at': t,
    })
    await db.po_items.insert_one(po_item(PO1_ID, 'PO-MK-DEMO-1', f'{PO1_ID}-i1', 'Jaket Hoodie Aruna', 'ARN-HD-M', 'M', 'Navy', 'SN-MK1-A', 150, 18000, catalog_item_id=CAT_HOODIE, maklon_variant_id=f'{CAT_HOODIE}-nvy-M'.lower(), buyer_ref='ARUNA-HOOD-NVY-M'))
    await db.po_items.insert_one(po_item(PO1_ID, 'PO-MK-DEMO-1', f'{PO1_ID}-i2', 'Jaket Hoodie Aruna', 'ARN-HD-L', 'L', 'Navy', 'SN-MK1-B', 100, 18000, catalog_item_id=CAT_HOODIE, maklon_variant_id=f'{CAT_HOODIE}-nvy-L'.lower(), buyer_ref='ARUNA-HOOD-NVY-L'))
    for acc_name, acc_code, qty_needed in [('Zipper YKK 60cm', 'ZIP-60', 250), ('Label Woven Aruna', 'LBL-ARN', 250)]:
        await db.po_accessories.insert_one({
            'id': new_id(), 'po_id': PO1_ID, 'accessory_id': None,
            'accessory_name': acc_name, 'accessory_code': acc_code,
            'qty_needed': qty_needed, 'unit': 'pcs', 'notes': '', 'created_at': t,
        })

    # ── PO 2: In Production dengan alur penuh ────────────────────────────────
    await db.production_pos.insert_one({
        'id': PO2_ID, 'po_number': 'PO-MK-DEMO-2',
        'customer_name': 'PT Aruna Activewear', 'buyer_id': CLIENT_ID,
        'vendor_id': VENDOR_ID, 'vendor_name': 'CV Jahit Mitra CMT',
        'po_date': t, 'deadline': None, 'delivery_deadline': None,
        'status': 'In Production', 'notes': 'Demo maklon — sedang berjalan',
        'business_type': 'maklon',
        'created_by': 'seed', 'created_at': t, 'updated_at': t,
    })
    i1, i2 = f'{PO2_ID}-i1', f'{PO2_ID}-i2'
    await db.po_items.insert_one(po_item(PO2_ID, 'PO-MK-DEMO-2', i1, 'Kaos Polo Aruna', 'ARN-PL-M', 'M', 'Putih', 'SN-MK2-A', 100, 12000, catalog_item_id=CAT_POLO, maklon_variant_id=f'{CAT_POLO}-pth-M'.lower(), buyer_ref='ARUNA-POLO-PTH-M'))
    await db.po_items.insert_one(po_item(PO2_ID, 'PO-MK-DEMO-2', i2, 'Kaos Polo Aruna', 'ARN-PL-L', 'L', 'Putih', 'SN-MK2-B', 50, 12000, catalog_item_id=CAT_POLO, maklon_variant_id=f'{CAT_POLO}-pth-L'.lower(), buyer_ref='ARUNA-POLO-PTH-L'))

    ship_id = f'{PO2_ID}-vs1'
    await db.vendor_shipments.insert_one({
        'id': ship_id, 'shipment_number': 'SJ-MK-DEMO-2', 'delivery_note_number': 'DN-MK-DEMO-2',
        'vendor_id': VENDOR_ID, 'vendor_name': 'CV Jahit Mitra CMT',
        'po_id': PO2_ID, 'po_number': 'PO-MK-DEMO-2',
        'shipment_date': t, 'shipment_type': 'NORMAL', 'parent_shipment_id': None,
        'status': 'Received', 'inspection_status': 'Inspected',
        'total_received': 145, 'total_missing': 5, 'inspected_at': t,
        'business_type': 'maklon', 'notes': 'Seed demo',
        'created_by': 'seed', 'created_at': t, 'updated_at': t,
    })
    vsi1, vsi2 = f'{ship_id}-l1', f'{ship_id}-l2'
    for sid, poi, name, sku, size, serial, qty in [
        (vsi1, i1, 'Kaos Polo Aruna', 'ARN-PL-M', 'M', 'SN-MK2-A', 100),
        (vsi2, i2, 'Kaos Polo Aruna', 'ARN-PL-L', 'L', 'SN-MK2-B', 50),
    ]:
        await db.vendor_shipment_items.insert_one({
            'id': sid, 'shipment_id': ship_id, 'shipment_number': 'SJ-MK-DEMO-2',
            'po_id': PO2_ID, 'po_number': 'PO-MK-DEMO-2',
            'po_item_id': poi, 'source_po_item_id': poi,
            'product_name': name, 'sku': sku, 'size': size, 'color': 'Putih',
            'serial_number': serial, 'qty_sent': qty, 'ordered_qty': qty,
            'shipment_type': 'NORMAL', 'parent_shipment_id': None, 'created_at': t,
        })

    insp_id = f'{PO2_ID}-insp1'
    await db.vendor_material_inspections.insert_one({
        'id': insp_id, 'shipment_id': ship_id, 'shipment_number': 'SJ-MK-DEMO-2',
        'vendor_id': VENDOR_ID, 'vendor_name': 'CV Jahit Mitra CMT',
        'inspection_date': t, 'total_received': 145, 'total_missing': 5,
        'total_acc_received': 0, 'total_acc_missing': 0,
        'overall_notes': 'Seed demo — 5 pcs bahan L kurang', 'status': 'Submitted',
        'submitted_by': 'seed', 'created_at': t, 'updated_at': t,
    })
    for vsi, sku, size, recv, miss in [(vsi1, 'ARN-PL-M', 'M', 100, 0), (vsi2, 'ARN-PL-L', 'L', 45, 5)]:
        await db.vendor_material_inspection_items.insert_one({
            'id': new_id(), 'inspection_id': insp_id, 'item_type': 'material',
            'shipment_item_id': vsi, 'sku': sku, 'product_name': 'Kaos Polo Aruna',
            'size': size, 'color': 'Putih', 'ordered_qty': recv + miss,
            'received_qty': recv, 'missing_qty': miss, 'condition_notes': '', 'created_at': t,
        })

    job_id = f'{PO2_ID}-job1'
    await db.production_jobs.insert_one({
        'id': job_id, 'job_number': 'JOB-MK-DEMO-2',
        'parent_job_id': None, 'parent_job_number': None,
        'vendor_id': VENDOR_ID, 'vendor_name': 'CV Jahit Mitra CMT',
        'po_id': PO2_ID, 'po_number': 'PO-MK-DEMO-2',
        'customer_name': 'PT Aruna Activewear',
        'vendor_shipment_id': ship_id, 'shipment_number': 'SJ-MK-DEMO-2',
        'shipment_type': 'NORMAL', 'deadline': None, 'delivery_deadline': None,
        'status': 'In Progress', 'business_type': 'maklon', 'notes': 'Seed demo',
        'created_by': 'seed', 'created_at': t, 'updated_at': t,
    })
    ji1, ji2 = f'{job_id}-ji1', f'{job_id}-ji2'
    for jid, poi, vsi, sku, size, serial, avail, prod in [
        (ji1, i1, vsi1, 'ARN-PL-M', 'M', 'SN-MK2-A', 100, 80),
        (ji2, i2, vsi2, 'ARN-PL-L', 'L', 'SN-MK2-B', 45, 20),
    ]:
        await db.production_job_items.insert_one({
            'id': jid, 'job_id': job_id, 'job_number': 'JOB-MK-DEMO-2',
            'po_item_id': poi, 'vendor_shipment_item_id': vsi,
            'product_name': 'Kaos Polo Aruna', 'sku': sku, 'size': size, 'color': 'Putih',
            'catalog_item_id': CAT_POLO, 'maklon_variant_id': f'{CAT_POLO}-pth-{size}'.lower(),
            # [DISPLAY FIX] buyer article code propagated from po_item → tampil di portal vendor/produksi.
            'buyer_ref_code': f'ARUNA-POLO-PTH-{size}', 'color_code': 'PTH',
            'serial_number': serial, 'ordered_qty': avail + (5 if size == 'L' else 0),
            'shipment_qty': avail + (5 if size == 'L' else 0), 'available_qty': avail,
            'produced_qty': prod, 'created_at': t,
        })
        await db.production_progress.insert_one({
            'id': new_id(), 'job_id': job_id, 'job_item_id': jid,
            'sku': sku, 'product_name': 'Kaos Polo Aruna', 'size': size, 'color': 'Putih',
            'progress_date': t, 'completed_quantity': prod,
            'notes': 'Seed demo progress', 'recorded_by': 'seed', 'created_at': t,
        })

    bs_id = f'{PO2_ID}-bs1'
    await db.buyer_shipments.insert_one({
        'id': bs_id, 'shipment_number': 'SJ-BYR-MK-DEMO-2',
        'vendor_id': VENDOR_ID, 'vendor_name': 'CV Jahit Mitra CMT',
        'po_id': PO2_ID, 'po_number': 'PO-MK-DEMO-2',
        'customer_name': 'PT Aruna Activewear', 'job_id': job_id,
        'ship_status': 'Partially Shipped', 'business_type': 'maklon',
        'last_dispatch': t, 'last_dispatch_seq': 1, 'notes': 'Seed demo dispatch #1',
        'created_by': 'seed', 'created_at': t, 'updated_at': t,
    })
    await db.buyer_shipment_items.insert_one({
        'id': new_id(), 'shipment_id': bs_id, 'dispatch_seq': 1, 'dispatch_date': t,
        'po_item_id': i1, 'job_item_id': ji1, 'job_id': job_id,
        'product_name': 'Kaos Polo Aruna', 'serial_number': 'SN-MK2-A',
        'size': 'M', 'color': 'Putih', 'sku': 'ARN-PL-M',
        'ordered_qty': 100, 'qty_shipped': 60, 'created_at': t,
    })

    # ── 4. Finance mirror + Draft AR untuk PO-2 ─────────────────────────────
    finance = await sync_po_to_maklon_finance(db, PO2_ID, user)

    # ── 5. FASE 5: seed Produksi Internal demo ─────────────────────────────
    internal = await _seed_internal(db, user, t)

    return {
        'status': 'success',
        'message': 'Seed portal produksi (maklon + internal) selesai — fresh re-seed',
        'client_id': CLIENT_ID, 'vendor_id': VENDOR_ID,
        'users': users_seeded,
        'pos': [
            {'id': PO1_ID, 'po_number': 'PO-MK-DEMO-1', 'status': 'Draft'},
            {'id': PO2_ID, 'po_number': 'PO-MK-DEMO-2', 'status': 'In Production',
             'job': 'JOB-MK-DEMO-2', 'dispatch_1_qty': 60},
        ],
        'internal': internal,
        'finance': finance,
    }


async def _seed_internal(db, user, t):
    """Demo Produksi Internal (business_type='internal') — reuse fungsi adapter asli
    (explode BOM, create job+MI draft, wip mirror) agar identik perilaku engine."""
    seed_user = {'id': user.get('id', 'seed'), 'name': user.get('name', 'Seeder')}

    # 5a. Bersihkan demo lama (idempoten)
    for pid in (INT_PO1, INT_PO2, INT_PO3):
        po_old = await db.production_pos.find_one({'id': pid}, {'id': 1})
        if po_old:
            jobs_old = await db.production_jobs.find({'po_id': pid}, {'id': 1}).to_list(None)
            for j in jobs_old:
                await db.rahaza_material_issues.delete_many({'job_id': j['id']})
                await db.rahaza_wip_events.delete_many({'job_id': j['id']})
                await db.rahaza_hpp_snapshots.delete_many({'job_id': j['id']})
                # job internal tidak punya vendor_shipment → cascade PO tidak menghapusnya
                await db.production_job_items.delete_many({'job_id': j['id']})
                await db.production_progress.delete_many({'job_id': j['id']})
                await db.production_jobs.delete_one({'id': j['id']})
            await cascade_delete_po(pid)

    # 5b. Masters internal
    INT_LOC = await _upsert(db, 'rahaza_locations', {
        'id': _DEFAULT_INT_LOC, 'code': 'GDG-UTAMA-DEMO', 'name': 'Gudang Utama (Demo)',
        'active': True, 'created_at': t,
    })
    sizes = await db.rahaza_sizes.find({'active': {'$ne': False}}, {'_id': 0}).sort('code', 1).to_list(1)
    if not sizes:
        await _upsert(db, 'rahaza_sizes', {'id': 'int-demo-size-m', 'code': 'M', 'name': 'M', 'active': True, 'created_at': t})
        sizes = [{'id': 'int-demo-size-m', 'code': 'M'}]
    size_id, size_code = sizes[0]['id'], sizes[0].get('code', '')
    proc = await db.rahaza_processes.find_one({'active': {'$ne': False}}, {'_id': 0})
    if not proc:
        await _upsert(db, 'rahaza_processes', {'id': 'int-demo-proc-1', 'code': 'SEW', 'name': 'Sewing', 'active': True, 'created_at': t})
        proc = {'id': 'int-demo-proc-1'}
    INT_MODEL = await _upsert(db, 'rahaza_models', {
        'id': _DEFAULT_INT_MODEL, 'code': 'DA-TS01', 'name': 'Kaos Basic DA',
        'bundle_size': 30, 'active': True, 'created_by': 'seed', 'created_at': t,
    })
    # ACC-2 — master material HARUS ada SEBELUM BOM dibuat supaya baris BOM
    # (terutama baris AKSESORIS) bisa langsung tertaut ke master (`material_id`).
    # Sebelumnya urutannya terbalik: BOM ditulis dengan `material_id: None`
    # sehingga data demo lahir dalam kondisi "lepas" → rantai BOM → kebutuhan
    # aksesoris PO → stok putus (accessory_id null, tak bisa dibandingkan stok).
    mats = {}
    mat_stock_loc: dict = {}   # FASE 12: material_id → zona penyimpanan kanonik
    for code, name, mtype, unit, cost in [
        (INT_MAT_YARN_CODE, 'Benang Cotton 30s', 'yarn', 'kg', 20000),
        (INT_MAT_ACC_CODE, 'Label Woven DA', 'accessory', 'pcs', 500),
    ]:
        m = await db.rahaza_materials.find_one({'code': code}, {'_id': 0})
        if not m:
            m = {'id': new_id(), 'code': code, 'name': name, 'type': mtype, 'unit': unit,
                 # FASE 6.6-B: kanonik `composition` + alias legacy `yarn_type`
                 **material_fields.mirror('composition', 'cotton' if mtype == 'yarn' else ''),
                 'color': '', 'min_stock': 0,
                 'unit_cost': cost, 'active': True, 'created_at': t, 'updated_at': t}
            await db.rahaza_materials.insert_one(m)
        else:
            await db.rahaza_materials.update_one({'id': m['id']}, {'$set': {'unit_cost': cost, 'active': True}})
        mats[code] = m
        # FASE 12: stok demo mendarat di ZONA PENYIMPANAN kanonik sesuai kategori
        # material, bukan lagi di lokasi pseudo `GDG-UTAMA-DEMO`.
        stock_loc = await _storage_zone_for(db, mtype, INT_LOC)
        mat_stock_loc[m['id']] = stock_loc
        await db.rahaza_material_stock.update_one(
            {'material_id': m['id'], 'location_id': stock_loc},
            {'$set': {'qty': 500.0 if mtype == 'yarn' else 2000.0, 'updated_at': t},
             '$setOnInsert': {'id': new_id()}}, upsert=True)
    await _upsert(db, 'rahaza_boms', {
        'id': INT_BOM, 'model_id': INT_MODEL, 'size_id': size_id, 'color': '',
        'version': 1, 'is_active': True, 'active': True,
        'materials': [
            {'material_id': mats[INT_MAT_YARN_CODE]['id'], 'name': 'Benang Cotton 30s', 'code': INT_MAT_YARN_CODE,
             'material_type': 'yarn', 'category': '', 'category_name': 'Benang', 'qty': 0.25, 'unit': 'kg', 'notes': ''},
            {'material_id': mats[INT_MAT_ACC_CODE]['id'], 'name': 'Label Woven DA', 'code': INT_MAT_ACC_CODE,
             'material_type': 'accessory', 'category': '', 'category_name': 'Aksesoris', 'qty': 1, 'unit': 'pcs', 'notes': ''},
        ],
        'created_by': 'seed', 'created_at': t,
    })
    INT_EMP = await _upsert(db, 'rahaza_employees', {
        'id': _DEFAULT_INT_EMP, 'name': 'Op. Demo Borongan', 'employee_code': 'OP-DEMO-1',
        'employment_type': 'daily', 'active': True, 'created_at': t,
    })
    await db.rahaza_payroll_profiles.update_one(
        {'employee_id': INT_EMP},
        {'$set': {'pay_scheme': 'pcs', 'base_rate': 500, 'pcs_process_rates': [], 'active': True},
         '$setOnInsert': {'id': new_id(), 'employee_id': INT_EMP, 'created_at': t}}, upsert=True)
    if not await db.rahaza_costing_settings.find_one({'id': 'GLOBAL'}):
        # FASE 12 / BUG-A: seeder ini dulu menulis alias legacy `default_yarn_cost_per_kg`
        # secara harfiah sehingga SETIAP DB baru langsung melanggar kontrak FASE 11
        # ("alias `yarn_*` tidak ditulis lagi") — ketahuan lewat verify_fase66.py B8.
        # Sekarang lewat SSOT `material_fields.mirror()`: menulis nama KANONIK saja
        # (dan otomatis ikut menulis alias lagi kalau WRITE_ALIASES diisi ulang).
        await db.rahaza_costing_settings.insert_one({
            'id': 'GLOBAL', 'overhead_rate_per_pcs': 1000,
            **material_fields.mirror('default_material_cost_per_kg', 0),
            'default_accessory_cost_per_unit': 0,
            'labor_rate_fallback_per_pcs': 0,
        })

    def int_po(pid, number, status, qty, notes):
        return {
            'id': pid, 'po_number': number, 'customer_name': 'Gudang FG Sendiri',
            'buyer_id': None, 'vendor_id': None, 'vendor_name': 'Produksi Internal',
            'po_date': t, 'deadline': None, 'delivery_deadline': None,
            'status': status, 'notes': notes, 'business_type': 'internal',
            'created_by': 'seed', 'created_at': t, 'updated_at': t,
        }

    def int_item(pid, number, qty, serial):
        return {
            'id': f'{pid}-i1', 'po_id': pid, 'po_number': number,
            'product_id': None, 'product_name': 'Kaos Basic DA', 'variant_id': None,
            'model_id': INT_MODEL, 'size_id': size_id,
            'size': size_code, 'color': 'Hitam', 'sku': f'DA-TS01-{size_code}',
            'qty': qty, 'serial_number': serial,
            'selling_price_snapshot': 0.0, 'cmt_price_snapshot': 0.0, 'created_at': t,
        }

    # 5c. PO-1 Draft
    await db.production_pos.insert_one(int_po(INT_PO1, 'PO-INT-DEMO-1', 'Draft', 200, 'Demo internal — belum dikonfirmasi'))
    await db.po_items.insert_one(int_item(INT_PO1, 'PO-INT-DEMO-1', 200, 'SN-INT1-A'))
    await explode_po_accessories_from_bom(db, INT_PO1)

    # 5d. PO-2 In Production: job + MI issued + progress + wip mirror + dispatch #1
    await db.production_pos.insert_one(int_po(INT_PO2, 'PO-INT-DEMO-2', 'Confirmed', 200, 'Demo internal — sedang produksi'))
    await db.po_items.insert_one(int_item(INT_PO2, 'PO-INT-DEMO-2', 200, 'SN-INT2-A'))
    await explode_po_accessories_from_bom(db, INT_PO2)
    _r2 = await create_internal_job(db, {'po_id': INT_PO2}, seed_user)
    job2 = _json.loads(_r2.body) if hasattr(_r2, 'body') else _r2
    ji2 = job2['items'][0]
    mi2 = job2.get('material_issue_draft') or {}
    # MI → issued (stok berkurang manual, tanpa JE — demo data)
    if mi2.get('id'):
        issued_items = []
        for it in mi2.get('items', []):
            # FASE 12: potong stok di ZONA tempat stok itu benar-benar berada.
            iss_loc = mat_stock_loc.get(it['material_id']) or INT_LOC
            await db.rahaza_material_stock.update_one(
                {'material_id': it['material_id'], 'location_id': iss_loc},
                {'$inc': {'qty': -float(it['qty_required'])}, '$set': {'updated_at': t}})
            issued_items.append({**it, 'qty_issued': it['qty_required'], 'location_id': iss_loc})
        await db.rahaza_material_issues.update_one({'id': mi2['id']}, {'$set': {
            'status': 'issued', 'issued_at': t, 'issued_by': 'seed',
            'items': issued_items,
            'updated_at': t,
        }})
    ctx = await resolve_operator_process(db, INT_EMP, proc['id'])
    total_prog = 0
    for qty_p in (70, 50):
        prog_id = new_id()
        await db.production_progress.insert_one({
            'id': prog_id, 'job_id': job2['id'], 'job_item_id': ji2['id'],
            'sku': f'DA-TS01-{size_code}', 'product_name': 'Kaos Basic DA',
            'size': size_code, 'color': 'Hitam', 'progress_date': t,
            'completed_quantity': qty_p, 'operator_id': INT_EMP, 'process_id': proc['id'],
            'notes': 'Seed demo progress internal', 'recorded_by': 'seed', 'created_at': t,
        })
        await insert_wip_mirror(db, job2, ji2, qty_p, ctx, seed_user, progress_id=prog_id)
        total_prog += qty_p
    await db.production_job_items.update_one({'id': ji2['id']}, {'$set': {'produced_qty': total_prog}})
    bs_id = f'{INT_PO2}-bs1'
    await db.buyer_shipments.insert_one({
        'id': bs_id, 'shipment_number': 'SJ-BYR-INT-DEMO-2',
        'vendor_id': None, 'vendor_name': 'Produksi Internal',
        'po_id': INT_PO2, 'po_number': 'PO-INT-DEMO-2',
        'customer_name': 'Gudang FG Sendiri', 'job_id': job2['id'],
        'ship_status': 'Partially Shipped', 'business_type': 'internal',
        'last_dispatch': t, 'last_dispatch_seq': 1, 'notes': 'Seed demo dispatch #1 internal',
        'created_by': 'seed', 'created_at': t, 'updated_at': t,
    })
    await db.buyer_shipment_items.insert_one({
        'id': new_id(), 'shipment_id': bs_id, 'dispatch_seq': 1, 'dispatch_date': t,
        'po_item_id': f'{INT_PO2}-i1', 'job_item_id': ji2['id'], 'job_id': job2['id'],
        'product_name': 'Kaos Basic DA', 'serial_number': 'SN-INT2-A',
        'size': size_code, 'color': 'Hitam', 'sku': f'DA-TS01-{size_code}',
        'ordered_qty': 200, 'qty_shipped': 80, 'created_at': t,
    })

    # 5e. PO-3 In Production dengan MI draft (bahan aksi gudang di UI)
    await db.production_pos.insert_one(int_po(INT_PO3, 'PO-INT-DEMO-3', 'Confirmed', 100, 'Demo internal — menunggu material gudang'))
    await db.po_items.insert_one(int_item(INT_PO3, 'PO-INT-DEMO-3', 100, 'SN-INT3-A'))
    await explode_po_accessories_from_bom(db, INT_PO3)
    _r3 = await create_internal_job(db, {'po_id': INT_PO3}, seed_user)
    job3 = _json.loads(_r3.body) if hasattr(_r3, 'body') else _r3

    return {
        'pos': [
            {'id': INT_PO1, 'po_number': 'PO-INT-DEMO-1', 'status': 'Draft'},
            {'id': INT_PO2, 'po_number': 'PO-INT-DEMO-2', 'status': 'In Production',
             'job': job2.get('job_number'), 'progress': total_prog, 'dispatch_1_qty': 80},
            {'id': INT_PO3, 'po_number': 'PO-INT-DEMO-3', 'status': 'In Production',
             'job': job3.get('job_number'), 'mi_status': 'draft'},
        ],
        'model': {'id': INT_MODEL, 'code': 'DA-TS01'},
        'operator': {'id': INT_EMP, 'rate_pcs': 500},
        'location': INT_LOC,
    }
