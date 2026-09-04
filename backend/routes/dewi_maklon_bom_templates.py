"""
CV. Dewi Aditya — Portal Maklon: BOM Template (Phase M2.2)

Konsep:
- 1 Buyer Catalog bisa punya banyak versi BOM Template (v1, v2, v3, ...)
- Hanya 1 yang berstatus 'is_active = true' pada satu waktu (yang dipakai default)
- Saat buat PO Maklon, user bisa "Apply Template" → copy materials ke dewi_maklon_bom (per-PO override)
- Versi lama tetap tersimpan untuk audit/rollback

Collection: dewi_maklon_bom_templates
- One catalog → many templates
- Composite uniqueness (buyer_catalog_id + version) supaya tidak ada versi double

Endpoint prefix: /api/dewi/maklon
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from routes.production_rbac import deny_external_dep
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone

from database import get_db
from auth import require_auth, serialize_doc, log_activity
from core import bom_uom  # 2026-08-02: konversi satuan baris BOM → satuan dasar
from utils.money import parse_id_number, MoneyParseError  # 2026-08-07: SSOT angka locale-ID
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/dewi/maklon', tags=['Dewi-Maklon-BOM-Template'], dependencies=[Depends(deny_external_dep)])
def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────────────────────────────────────
# PYDANTIC MODELS
# ──────────────────────────────────────────────────────────────────────────────
class BOMMaterialItem(BaseModel):
    material_name: str = Field(..., min_length=1, max_length=255)
    category: Optional[str] = Field(default='', max_length=64)
    unit: str = Field(default='pcs', max_length=16)
    qty_per_pcs: float = Field(default=0, ge=0, description='Qty per pcs produk')
    cost_per_unit: float = Field(default=0, ge=0, description='Estimasi cost per unit (Rp)')
    supplier: Optional[str] = Field(default='', max_length=128)
    notes: Optional[str] = Field(default='', max_length=500)

    # ── GERBANG ANGKA UANG ────────────────────────────────────────────────────
    # 2026-08-07 — BUG UANG NYATA yang ditemukan saat memverifikasi perbaikan
    # `_compute_total_cost`. Pydantic v2 (mode longgar) MENGUBAH string angka
    # menjadi float dengan aturan Python, BUKAN aturan Indonesia:
    #
    #     cost_per_unit = "85.000"   →  Pydantic  →  85.0        (SALAH)
    #                                  seharusnya →  85000.0
    #
    # "85.000" adalah cara orang Indonesia menulis delapan puluh lima ribu, dan
    # layar BOM (`MaklonBuyerCatalogDetailDialog.jsx`) mengirim NILAI MENTAH dari
    # kotak input (`e.target.value`) — jadi string seperti ini benar-benar sampai
    # ke sini. Dibuktikan: total biaya per pcs tersimpan **51.0** padahal
    # seharusnya **51000.0** — SERIBU KALI lebih murah. Angka itu dasar quote/HPP
    # maklon, jadi perusahaan bisa menawarkan harga jauh di bawah biaya.
    #
    # Validator ini berjalan SEBELUM konversi Pydantic, dan memakai SSOT
    # `utils/money.parse_id_number` (titik = ribuan, koma = desimal) yang sudah
    # dipakai di tempat lain — bukan aturan baru. Bila formatnya tidak dikenali,
    # permintaan DITOLAK (422) dengan pesan yang jelas, bukan diam-diam jadi 0.
    @field_validator('qty_per_pcs', 'cost_per_unit', mode='before')
    @classmethod
    def _angka_locale_id(cls, v, info):
        if v is None or v == '':
            return 0
        if isinstance(v, bool):
            raise ValueError(f"{info.field_name}: nilai boolean bukan angka")
        if isinstance(v, (int, float)):
            return v
        try:
            return parse_id_number(v)
        except MoneyParseError as e:
            raise ValueError(
                f"{info.field_name}: nilai '{v}' tidak dikenali sebagai angka. "
                f"Gunakan titik untuk ribuan dan koma untuk desimal "
                f"(contoh: 85.000 atau 1.250,50). Detail: {e}")


class BOMTemplateIn(BaseModel):
    buyer_catalog_id: str = Field(..., description='FK ke dewi_maklon_buyer_catalog')
    version_label: Optional[str] = Field(default='', max_length=64, description='Label custom, mis: "Initial", "Revisi material baru"')
    materials: List[BOMMaterialItem] = Field(default_factory=list)
    notes: Optional[str] = Field(default='', max_length=1000)
    set_active: bool = Field(default=True, description='Set sebagai active version (set false untuk simpan as draft)')


class BOMTemplateUpdate(BaseModel):
    version_label: Optional[str] = Field(default=None, max_length=64)
    materials: Optional[List[BOMMaterialItem]] = None
    notes: Optional[str] = Field(default=None, max_length=1000)


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────
async def _ensure_catalog_exists(db, catalog_id: str) -> dict:
    cat = await db.dewi_maklon_buyer_catalog.find_one({'id': catalog_id}, {'_id': 0})
    if not cat:
        raise HTTPException(404, 'Buyer Catalog tidak ditemukan')
    return cat


async def _next_version(db, catalog_id: str) -> int:
    last = await db.dewi_maklon_bom_templates.find_one(
        {'buyer_catalog_id': catalog_id}, sort=[('version', -1)]
    )
    return int((last or {}).get('version', 0)) + 1


async def _deactivate_others(db, catalog_id: str, except_id: Optional[str] = None) -> None:
    """Set semua template untuk catalog ini → is_active=False kecuali except_id."""
    filt: dict = {'buyer_catalog_id': catalog_id, 'is_active': True}
    if except_id:
        filt['id'] = {'$ne': except_id}
    await db.dewi_maklon_bom_templates.update_many(
        filt, {'$set': {'is_active': False, 'updated_at': _now()}}
    )


def _compute_total_cost(materials: List[dict]) -> float:
    """Hitung total estimasi cost per pcs produk.

    2026-08-07 — DULU baris yang angkanya tidak sah di-`continue` DIAM-DIAM.
    Ini MERUSAK HARGA: satu baris material dengan `cost_per_unit` berisi teks
    (mis. "12.500" dengan titik ribuan, atau "" dari impor Excel) membuat
    biayanya dihitung NOL. `total_cost_per_pcs` jadi lebih murah dari
    kenyataan, dan angka itu dipakai sebagai dasar quote/HPP maklon ⇒
    perusahaan bisa menjual DI BAWAH biaya tanpa ada yang tahu.
    Karena ini ANGKA UANG, sekarang gagal keras dengan menyebut materialnya.
    """
    total = 0.0
    for idx, m in enumerate(materials or [], start=1):
        m = m if isinstance(m, dict) else {}
        nama = m.get('material_name') or m.get('material_code') or m.get('material_id') or f'baris {idx}'
        for field in ('qty_per_pcs', 'cost_per_unit'):
            nilai = m.get(field)
            if nilai in (None, ''):
                continue
            try:
                float(nilai)
            except (ValueError, TypeError):
                raise ValueError(
                    f"Material '{nama}': {field} bernilai '{nilai}' yang bukan angka. "
                    f"Perbaiki dulu — bila dibiarkan, biayanya dihitung 0 dan "
                    f"total biaya per pcs menjadi lebih murah dari kenyataan.")
        total += float(m.get('qty_per_pcs') or 0) * float(m.get('cost_per_unit') or 0)
    return round(total, 2)


# ──────────────────────────────────────────────────────────────────────────────
# CRUD ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────
@router.get('/bom-templates')
async def list_bom_templates(
    buyer_catalog_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    user: dict = Depends(require_auth),
):
    """List BOM templates. Filter by catalog atau is_active."""
    db = get_db()
    filt: dict = {}
    if buyer_catalog_id:
        filt['buyer_catalog_id'] = buyer_catalog_id
    if is_active is not None:
        filt['is_active'] = is_active
    cursor = db.dewi_maklon_bom_templates.find(filt).sort([('buyer_catalog_id', 1), ('version', -1)]).limit(500)
    items = [serialize_doc(d) async for d in cursor]
    return items


@router.post('/bom-templates', status_code=201)
async def create_bom_template(payload: BOMTemplateIn, user: dict = Depends(require_auth)):
    """Buat BOM Template baru (versi auto-increment per catalog)."""
    db = get_db()
    cat = await _ensure_catalog_exists(db, payload.buyer_catalog_id)

    version = await _next_version(db, payload.buyer_catalog_id)
    materials = [m.dict() for m in (payload.materials or [])]
    # ValueError dari `_compute_total_cost` = angka biaya tidak sah. Harus 400
    # (bukan 500): pesannya menyebut material mana yang perlu dibetulkan.
    try:
        total_cost = _compute_total_cost(materials)
    except ValueError as e:
        raise HTTPException(400, str(e))

    doc = {
        'id': _uid(),
        'buyer_catalog_id': payload.buyer_catalog_id,
        'catalog_artikel_code': cat.get('artikel_code', ''),
        'catalog_product_name': cat.get('product_name', ''),
        'client_id': cat.get('client_id'),
        'client_name': cat.get('client_name', ''),
        'version': version,
        'version_label': (payload.version_label or f'v{version}').strip() or f'v{version}',
        'materials': materials,
        'material_count': len(materials),
        'total_cost_per_pcs': total_cost,
        'notes': (payload.notes or '').strip(),
        'is_active': bool(payload.set_active),
        'created_at': _now(),
        'updated_at': _now(),
        'created_by_id': user.get('id') or '',
        'created_by_name': user.get('name') or user.get('email') or 'system',
    }
    await db.dewi_maklon_bom_templates.insert_one(doc)

    # Kalau set_active → deactivate yang lain
    if payload.set_active:
        await _deactivate_others(db, payload.buyer_catalog_id, except_id=doc['id'])

    await log_activity(
        user.get('id') or '',
        user.get('name') or user.get('email') or 'system',
        'bom_template.create',
        'dewi-maklon',
        f"catalog={payload.buyer_catalog_id} version={version} active={payload.set_active}",
    )
    return {'message': f'BOM Template v{version} dibuat', 'item': serialize_doc(doc)}


@router.get('/bom-templates/{template_id}')
async def get_bom_template(template_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_maklon_bom_templates.find_one({'id': template_id})
    if not doc:
        raise HTTPException(404, 'BOM Template tidak ditemukan')
    return serialize_doc(doc)


@router.put('/bom-templates/{template_id}')
async def update_bom_template(template_id: str, payload: BOMTemplateUpdate, user: dict = Depends(require_auth)):
    """Update BOM Template existing. NOTE: tidak menambah versi baru — overwrite versi ini."""
    db = get_db()
    doc = await db.dewi_maklon_bom_templates.find_one({'id': template_id})
    if not doc:
        raise HTTPException(404, 'BOM Template tidak ditemukan')

    update_data = payload.model_dump(exclude_unset=True)
    if 'materials' in update_data and update_data['materials'] is not None:
        materials_list = [
            (m.dict() if isinstance(m, BOMMaterialItem) else m)
            for m in update_data['materials']
        ]
        update_data['materials'] = materials_list
        update_data['material_count'] = len(materials_list)
        try:
            update_data['total_cost_per_pcs'] = _compute_total_cost(materials_list)
        except ValueError as e:
            raise HTTPException(400, str(e))
    if 'version_label' in update_data and isinstance(update_data['version_label'], str):
        update_data['version_label'] = update_data['version_label'].strip()
    if 'notes' in update_data and isinstance(update_data['notes'], str):
        update_data['notes'] = update_data['notes'].strip()
    update_data['updated_at'] = _now()

    await db.dewi_maklon_bom_templates.update_one({'id': template_id}, {'$set': update_data})
    refreshed = await db.dewi_maklon_bom_templates.find_one({'id': template_id})
    await log_activity(
        user.get('id') or '',
        user.get('name') or user.get('email') or 'system',
        'bom_template.update',
        'dewi-maklon',
        f"id={template_id}",
    )
    return {'message': 'BOM Template diperbarui', 'item': serialize_doc(refreshed)}


@router.post('/bom-templates/{template_id}/activate')
async def activate_bom_template(template_id: str, user: dict = Depends(require_auth)):
    """Set template ini sebagai active version untuk catalog-nya (deactivate yang lain)."""
    db = get_db()
    doc = await db.dewi_maklon_bom_templates.find_one({'id': template_id})
    if not doc:
        raise HTTPException(404, 'BOM Template tidak ditemukan')
    await _deactivate_others(db, doc['buyer_catalog_id'], except_id=template_id)
    await db.dewi_maklon_bom_templates.update_one(
        {'id': template_id}, {'$set': {'is_active': True, 'updated_at': _now()}}
    )
    await log_activity(
        user.get('id') or '',
        user.get('name') or user.get('email') or 'system',
        'bom_template.activate',
        'dewi-maklon',
        f"id={template_id} catalog={doc['buyer_catalog_id']}",
    )
    return {'message': f"v{doc['version']} sekarang aktif untuk artikel ini"}


@router.delete('/bom-templates/{template_id}')
async def delete_bom_template(template_id: str, user: dict = Depends(require_auth)):
    """Hapus permanen (boleh karena versioning sudah handle audit)."""
    db = get_db()
    doc = await db.dewi_maklon_bom_templates.find_one({'id': template_id})
    if not doc:
        raise HTTPException(404, 'BOM Template tidak ditemukan')
    await db.dewi_maklon_bom_templates.delete_one({'id': template_id})
    await log_activity(
        user.get('id') or '',
        user.get('name') or user.get('email') or 'system',
        'bom_template.delete',
        'dewi-maklon',
        f"id={template_id} catalog={doc['buyer_catalog_id']} version={doc['version']}",
    )
    return {'message': 'BOM Template dihapus'}


# ══════════════════════════════════════════════════════════════════════════════
# SAMBUNGAN BOM MAKLON (2026-08-01) — Template → Kebutuhan Material PO → SJ
#
# MASALAH SEBELUMNYA (terbukti dari kode, bukan asumsi):
#   1. `apply-to-po` mencari PO di `dewi_maklon_pos` (koleksi LEGACY), padahal
#      SSOT PO maklon sudah pindah ke `production_pos` + `po_items`. Akibatnya
#      template tidak pernah bisa diterapkan ke PO maklon yang dipakai sekarang.
#   2. Tidak ada pemicu otomatis: PO maklon dibuat/diubah → BOM tidak pernah
#      diledakkan (berbeda dari PO internal yang punya ACC-1).
#   3. Tombol "Apply Template" hanya ada di modul yang sudah DIARSIPKAN.
#   4. Bentuk baris hasil apply (`qty_per_pcs/qty_total_est/cost_per_unit`) beda
#      dengan yang dibaca UI & endpoint manual (`qty_estimated/qty_actual`), jadi
#      tabel BOM di Detail PO selalu tampak kosong.
#
# YANG DIKERJAKAN DI SINI: satu mesin explode yang menulis dalam SKEMA KANONIK
# `dewi_maklon_bom` (dipakai endpoint manual & PO-360), sekaligus menurunkan
# baris aksesoris ke `po_accessories` (source='bom_maklon_auto') supaya otomatis
# ikut tercetak di tabel aksesoris Surat Jalan.
# ══════════════════════════════════════════════════════════════════════════════
BULK_UNITS = {'kg', 'kgs', 'gram', 'gr', 'g', 'm', 'm2', 'meter', 'metre', 'mtr',
              'yard', 'yd', 'yds', 'roll', 'rol', 'ball', 'bal', 'ton', 'liter', 'ltr'}
_FABRIC_HINTS = ('kain', 'fabric', 'benang', 'yarn', 'rajut', 'knit', 'woven', 'katun', 'cotton')
_ACCESSORY_HINTS = ('aksesor', 'accessor', 'zipper', 'button', 'kancing', 'label', 'kordon',
                    'elastis', 'karet', 'benang jahit', 'hangtag')
_PACKAGING_HINTS = ('packing', 'packaging', 'kemasan', 'poly', 'karton', 'box', 'dus', 'plastik')

# Sumber baris BOM per-PO. Baris/dokumen dengan source manual TIDAK ditimpa oleh
# explode otomatis — supaya pilihan versi template atau angka aktual dari user aman.
SOURCE_AUTO = 'template_auto'
SOURCE_MANUAL = 'template_manual'
ACC_SOURCE_TAG = 'bom_maklon_auto'


def _classify_line(m: dict) -> tuple:
    """Klasifikasikan baris BOM template → (line_type, material_category kanonik).

    line_type 'bulk'      = kain/benang bersatuan meter/kg → dipasok klien, TIDAK
                            masuk daftar aksesoris (jadi ekspektasi penerimaan).
    line_type 'accessory' = barang hitungan pcs (aksesoris/kemasan) → ikut jadi
                            baris kebutuhan `po_accessories` & tercetak di SJ.
    """
    cat = (m.get('category') or '').strip().lower()
    name = (m.get('material_name') or m.get('name') or '').strip().lower()
    unit = (m.get('unit') or '').strip().lower()
    blob = f"{cat} {name}"
    if any(h in blob for h in _PACKAGING_HINTS):
        return 'accessory', 'packaging'
    if any(h in cat for h in _FABRIC_HINTS) or (not cat and unit in BULK_UNITS):
        return 'bulk', 'fabric'
    if any(h in blob for h in _ACCESSORY_HINTS):
        return 'accessory', 'accessories'
    if unit in BULK_UNITS:
        return 'bulk', 'fabric' if any(h in blob for h in _FABRIC_HINTS) else 'other'
    return 'accessory', 'accessories'


async def _active_template_for_catalog(db, catalog_id: str) -> Optional[dict]:
    return await db.dewi_maklon_bom_templates.find_one(
        {'buyer_catalog_id': catalog_id, 'is_active': True}, {'_id': 0})


async def _load_maklon_po(db, po_id: str) -> tuple:
    """Ambil PO maklon + itemnya dari SSOT (`production_pos`+`po_items`),
    dengan fallback ke koleksi legacy `dewi_maklon_pos` (items ter-embed)."""
    po = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
    if po:
        items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).to_list(None)
        norm = [{
            'catalog_id': it.get('catalog_item_id') or it.get('buyer_catalog_id'),
            'qty': int(it.get('qty') or it.get('qty_ordered') or 0),
            'label': it.get('product_name') or it.get('sku') or it.get('id'),
        } for it in items]
        return po, norm, 'production_pos'
    legacy = await db.dewi_maklon_pos.find_one({'id': po_id}, {'_id': 0})
    if legacy:
        norm = [{
            'catalog_id': it.get('buyer_catalog_id') or it.get('catalog_item_id'),
            'qty': int(it.get('qty') or 0),
            'label': it.get('product_name') or it.get('sku') or it.get('item_id'),
        } for it in (legacy.get('items') or [])]
        return legacy, norm, 'dewi_maklon_pos'
    return None, [], ''


async def _material_lookup(db) -> tuple:
    """Peta master material untuk menautkan baris BOM (template hanya punya nama)."""
    by_name, by_code = {}, {}
    async for m in db.rahaza_materials.find({'active': True}, {'_id': 0, 'id': 1, 'name': 1, 'code': 1}):
        if m.get('name'):
            by_name.setdefault(m['name'].strip().lower(), m)
        if m.get('code'):
            by_code.setdefault(m['code'].strip().upper(), m)
    return by_name, by_code


async def explode_maklon_bom_for_po(db, po_id: str, user: Optional[dict] = None,
                                    template_id: Optional[str] = None,
                                    force: bool = False) -> dict:
    """Ledakkan BOM template artikel → kebutuhan material PO maklon.

    Menulis:
      • `dewi_maklon_bom` (1 dokumen per po_id, skema kanonik yang dibaca UI
        PO-360 & endpoint manual `/bom/{po_id}`)
      • `po_accessories` baris `source='bom_maklon_auto'` untuk baris pcs, agar
        muncul di panel "Aksesoris terkait PO" dan tabel aksesoris Surat Jalan.

    Menjaga hasil kerja manual:
      • Dokumen ber-`source='template_manual'` (user memilih versi template
        sendiri) TIDAK ditimpa kecuali `force=True`.
      • `qty_actual`/`actual_cost` yang sudah diisi dipertahankan (cocokkan
        nama+satuan), dan baris tambahan manual (tanpa `source_template_id`)
        tetap dipertahankan.
      • Baris `po_accessories` manual (source ≠ 'bom_maklon_auto') tidak disentuh.
    """
    po, items, po_source = await _load_maklon_po(db, po_id)
    if not po:
        raise HTTPException(404, 'PO Maklon tidak ditemukan')

    existing = await db.dewi_maklon_bom.find_one({'po_id': po_id}, {'_id': 0})
    if existing and not force and existing.get('source') == SOURCE_MANUAL:
        return {'ok': True, 'skipped': True,
                'reason': 'BOM PO ini di-set manual (versi template dipilih user). '
                          'Gunakan tombol Sinkronkan untuk menimpa.',
                'materials': len(existing.get('materials') or [])}

    forced_template = None
    if template_id:
        forced_template = await db.dewi_maklon_bom_templates.find_one({'id': template_id}, {'_id': 0})
        if not forced_template:
            raise HTTPException(404, 'BOM Template tidak ditemukan')

    warnings: List[str] = []
    agg, total_pcs, warnings, templates_used = await aggregate_template_lines(
        db, items, forced_template=forced_template)

    # nilai aktual & baris manual dari dokumen sebelumnya dipertahankan
    prev_by_key, prev_manual = {}, []
    for pm in ((existing or {}).get('materials') or []):
        k = ((pm.get('material_name') or '').strip().lower(), (pm.get('unit') or '').strip().lower())
        prev_by_key[k] = pm
        if not pm.get('source_template_id'):
            prev_manual.append(pm)

    materials = []
    for key, row in agg.items():
        prev = prev_by_key.get(key) or {}
        qty_est = round(row['qty_estimated'], 4)
        qty_act = prev.get('qty_actual')
        cost = float(row['cost_per_unit'] or 0)
        materials.append({
            'item_id': prev.get('item_id') or _uid(),
            'material_name': row['material_name'],
            'material_category': row['material_category'],
            'line_type': row['line_type'],
            'ownership': prev.get('ownership') or 'client_provided',
            'unit': row['unit'],
            'qty_estimated': qty_est,
            'qty_actual': qty_act,
            'qty_per_pcs': round(qty_est / total_pcs, 6) if total_pcs else 0,
            'qty_total_est': qty_est,                       # alias kompatibilitas lama
            'cost_per_unit': cost,
            'estimated_cost': round(qty_est * cost, 2),
            'actual_cost': round(float(qty_act) * cost, 2) if qty_act else prev.get('actual_cost') or 0,
            'material_id': prev.get('material_id'),
            'supplier': row['supplier'],
            'notes': row['notes'] or prev.get('notes', ''),
            'source_template_id': row['source_template_id'],
            'source_template_version': row['source_template_version'],
            'source_template_label': row['source_template_label'],
        })
    materials.extend(prev_manual)          # baris manual user tetap hidup

    now_ = _now()
    doc_set = {
        'po_id': po_id,
        'po_number': po.get('po_number'),
        'client_id': po.get('client_id'),
        'client_name': po.get('client_name', ''),
        'total_qty': total_pcs or po.get('total_qty') or 0,
        'materials': materials,
        'source': SOURCE_MANUAL if template_id else SOURCE_AUTO,
        'source_templates': list(templates_used.values()),
        'warnings': warnings,
        'po_source': po_source,
        'synced_at': now_,
        'synced_by_name': (user or {}).get('name', 'sistem'),
        'updated_at': now_,
    }
    if existing:
        await db.dewi_maklon_bom.update_one({'po_id': po_id}, {'$set': doc_set})
    else:
        await db.dewi_maklon_bom.insert_one({**doc_set, 'id': _uid(), 'notes': '', 'created_at': now_})

    # ── Turunkan baris pcs ke kebutuhan aksesoris PO (tercetak di Surat Jalan) ──
    rows, unlinked, uom_issues = await accessory_rows_from_materials(db, materials)
    await db.po_accessories.delete_many({'po_id': po_id, 'source': ACC_SOURCE_TAG})
    for row in rows:
        await db.po_accessories.insert_one({
            **row, 'id': _uid(), 'po_id': po_id,
            'source': ACC_SOURCE_TAG, 'created_at': now_,
        })
    acc_rows = len(rows)
    by_name, by_code = await _material_lookup(db)
    # simpan hasil konversi pada baris BOM per-PO juga (dipakai SJ & checklist)
    for m in materials:
        nm = (m.get('material_name') or '').strip()
        mat = by_name.get(nm.lower()) or by_code.get(nm.upper())
        factor, base_unit, status, note = bom_uom.line_factor(mat, m.get('unit'))
        m['unit_base'] = base_unit if mat else m.get('unit')
        m['uom_factor'] = round(factor, 8)
        m['qty_base'] = round(float(m.get('qty_estimated') or 0) * factor, 4)
        m['uom_status'] = status
        if status == 'mismatch' and note and f"{nm}: {note}" not in uom_issues:
            uom_issues.append(f"{nm}: {note}")
    if unlinked:
        warnings.append(
            'Baris BOM berikut belum tertaut master material sehingga stoknya tidak bisa dicek: '
            + ', '.join(unlinked[:10]))
    warnings.extend(uom_issues[:10])
    await db.dewi_maklon_bom.update_one(
        {'po_id': po_id}, {'$set': {'warnings': warnings, 'materials': materials}})

    return {
        'ok': True, 'skipped': False,
        'po_id': po_id, 'po_number': po.get('po_number'), 'po_source': po_source,
        'total_pcs': total_pcs,
        'materials': len(materials),
        'bulk_rows': sum(1 for m in materials if m.get('line_type') == 'bulk'),
        'accessory_rows': acc_rows,
        'templates_used': list(templates_used.values()),
        'warnings': warnings,
    }


async def maklon_material_expectation(db, po_id: str) -> dict:
    """Checklist material yang DITUNGGU dari klien vs yang SUDAH datang.

    Dihitung on-the-fly: ekspektasi dari BOM per-PO (baris kain/benang & pcs),
    realisasi dari `dewi_maklon_material_receive`. Sengaja TIDAK menulis dokumen
    penerimaan palsu — koleksi itu juga memicu mutasi `dewi_maklon_inventory`,
    jadi menulis ekspektasi ke sana akan membuat stok klien salah hitung.
    """
    bom = await db.dewi_maklon_bom.find_one({'po_id': po_id}, {'_id': 0})
    receives = await db.dewi_maklon_material_receive.find({'po_id': po_id}, {'_id': 0}).to_list(None)
    got: dict = {}
    for r in receives:
        for it in (r.get('items') or []):
            k = ((it.get('material_name') or '').strip().lower(), (it.get('unit') or '').strip().lower())
            got[k] = got.get(k, 0.0) + float(it.get('qty') or 0)
    lines = []
    for m in ((bom or {}).get('materials') or []):
        k = ((m.get('material_name') or '').strip().lower(), (m.get('unit') or '').strip().lower())
        exp = float(m.get('qty_estimated') or 0)
        rec = round(got.get(k, 0.0), 4)
        out = round(max(0.0, exp - rec), 4)
        lines.append({
            'material_name': m.get('material_name'), 'material_category': m.get('material_category'),
            'line_type': m.get('line_type', 'accessory'), 'unit': m.get('unit'),
            'ownership': m.get('ownership', 'client_provided'),
            'qty_expected': round(exp, 4), 'qty_received': rec, 'qty_outstanding': out,
            'status': 'complete' if rec >= exp > 0 else ('partial' if rec > 0 else 'pending'),
        })
    lines.sort(key=lambda x: (x['status'] != 'pending', x['material_name'] or ''))
    return {
        'po_id': po_id,
        'has_bom': bool(bom),
        'source_templates': (bom or {}).get('source_templates', []),
        'warnings': (bom or {}).get('warnings', []),
        'lines': lines,
        'summary': {
            'total_lines': len(lines),
            'pending': sum(1 for x in lines if x['status'] == 'pending'),
            'partial': sum(1 for x in lines if x['status'] == 'partial'),
            'complete': sum(1 for x in lines if x['status'] == 'complete'),
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# APPLY-TO-PO — copy template materials ke dewi_maklon_bom (per-PO BOM)
# ──────────────────────────────────────────────────────────────────────────────
class ApplyToPOIn(BaseModel):
    po_id: str = Field(..., description='Target PO Maklon')
    template_id: Optional[str] = Field(default=None, description='Specific template ID; jika kosong → pakai active version')


@router.post('/bom-templates/apply-to-po')
async def apply_template_to_po(payload: ApplyToPOIn, user: dict = Depends(require_auth)):
    """Terapkan BOM Template ke PO Maklon (SSOT `production_pos` atau legacy).

    DIPERBAIKI 2026-08-01: dulu endpoint ini hanya mencari PO di `dewi_maklon_pos`
    sehingga PO maklon yang dipakai sekarang (`production_pos` + `po_items`) selalu
    404 → rantai template → kebutuhan material → Surat Jalan tidak pernah nyambung.
    Sekarang memakai mesin `explode_maklon_bom_for_po()`: hasilnya ditulis dalam
    skema kanonik `dewi_maklon_bom` + baris aksesoris diturunkan ke `po_accessories`.
    """
    db = get_db()
    result = await explode_maklon_bom_for_po(
        db, payload.po_id, user=user, template_id=payload.template_id, force=True)
    await log_activity(
        user.get('id') or '',
        user.get('name') or user.get('email') or 'system',
        'bom_template.apply', 'dewi-maklon',
        f"po={payload.po_id} template={payload.template_id or 'active'} "
        f"materials={result.get('materials')}",
    )
    tpl = (result.get('templates_used') or [{}])[0]
    return {
        'message': f"BOM PO {result.get('po_number') or payload.po_id} tersinkron "
                   f"({result.get('materials')} material: {result.get('bulk_rows')} kain/benang, "
                   f"{result.get('accessory_rows')} aksesoris)",
        'template_id': tpl.get('template_id'),
        'template_version': tpl.get('version'),
        'material_count': result.get('materials'),
        'accessory_rows': result.get('accessory_rows'),
        'warnings': result.get('warnings', []),
        'templates_used': result.get('templates_used', []),
    }


class BomSyncIn(BaseModel):
    template_id: Optional[str] = Field(default=None, description='Kosong = pakai template AKTIF tiap artikel')
    force: bool = Field(default=True, description='Timpa walau BOM PO ini sebelumnya diatur manual')


@router.post('/pos/{po_id}/bom-sync')
async def sync_po_bom_from_template(po_id: str, payload: Optional[BomSyncIn] = None,
                                    user: dict = Depends(require_auth)):
    """Tombol "Sinkronkan BOM" di Detail PO Maklon.

    Tanpa `template_id` → pakai template AKTIF tiap artikel (hasil ditandai
    otomatis, jadi ikut ter-refresh saat item PO diubah). Dengan `template_id` →
    versi pilihan user dan dokumen dikunci dari penimpaan otomatis.
    """
    db = get_db()
    body = payload or BomSyncIn()
    result = await explode_maklon_bom_for_po(
        db, po_id, user=user, template_id=body.template_id, force=body.force)
    return result


@router.get('/pos/{po_id}/bom-needs')
async def get_po_bom_needs(po_id: str, user: dict = Depends(require_auth)):
    """Kebutuhan material PO maklon (BOM per-PO) + daftar template yang dipakai."""
    db = get_db()
    bom = await db.dewi_maklon_bom.find_one({'po_id': po_id}, {'_id': 0})
    acc = await db.po_accessories.find({'po_id': po_id}, {'_id': 0}).to_list(None)
    return {
        'po_id': po_id,
        'bom': serialize_doc(bom) if bom else None,
        'accessory_needs': serialize_doc(acc),
        'auto_accessory_rows': sum(1 for a in acc if a.get('source') == ACC_SOURCE_TAG),
    }


@router.get('/pos/{po_id}/material-expectation')
async def get_po_material_expectation(po_id: str, user: dict = Depends(require_auth)):
    """Checklist material dari klien: ditunggu vs sudah datang (dari BOM per-PO)."""
    db = get_db()
    return await maklon_material_expectation(db, po_id)


# ══════════════════════════════════════════════════════════════════════════════
# SATU MESIN — dipakai explode (saat PO disimpan) DAN pratinjau (saat form diisi)
# ══════════════════════════════════════════════════════════════════════════════
# Keluhan pemilik 2026-06: "katalog maklon sudah ada BOM aksesorisnya, di surat
# jalan & SPP sudah muncul, tapi di FORM BUAT PO tidak auto load" — pemakai jadi
# menyangka BOM-nya belum kena dan mengetik ulang baris aksesoris (kerja dobel +
# baris kembar). Sebabnya: BOM baru diledakkan SESUDAH PO tersimpan, dan tidak
# ada satu pun sumber angka yang bisa dibaca form.
#
# Dua fungsi di bawah adalah PECAHAN dari `explode_maklon_bom_for_po` (bukan
# rumus kedua): explode memakainya untuk MENULIS, pratinjau memakainya untuk
# MEMBACA. Kalau rumusnya berubah, dua-duanya ikut berubah — layar tidak bisa
# lagi menjanjikan angka yang berbeda dari yang akhirnya tersimpan.
async def aggregate_template_lines(db, items: List[dict],
                                   forced_template: Optional[dict] = None) -> tuple:
    """items = [{'catalog_id', 'qty', 'label'}] → (agg, total_pcs, warnings, templates_used)."""
    warnings: List[str] = []
    templates_used: dict = {}
    agg: dict = {}                    # (nama.lower(), unit.lower()) → baris
    total_pcs = 0
    tpl_cache: dict = {}

    for it in items:
        qty = int(it.get('qty') or 0)
        total_pcs += qty
        if qty <= 0:
            continue
        tpl = forced_template
        if tpl is None:
            cat_id = it.get('catalog_id')
            if not cat_id:
                warnings.append(f"Item '{it.get('label')}' belum tertaut artikel Katalog Buyer — BOM dilewati.")
                continue
            if cat_id not in tpl_cache:
                tpl_cache[cat_id] = await _active_template_for_catalog(db, cat_id)
            tpl = tpl_cache[cat_id]
            if not tpl:
                cat = await db.dewi_maklon_buyer_catalog.find_one({'id': cat_id}, {'_id': 0, 'artikel_code': 1, 'product_name': 1})
                nama = (cat or {}).get('artikel_code') or (cat or {}).get('product_name') or cat_id
                warnings.append(f"Artikel '{nama}' belum punya BOM Template AKTIF — buat/aktifkan dulu di Katalog Buyer.")
                continue
        templates_used[tpl['id']] = {'template_id': tpl['id'], 'version': tpl.get('version'),
                                     'label': tpl.get('version_label', ''),
                                     'catalog_id': tpl.get('buyer_catalog_id')}
        for m in (tpl.get('materials') or []):
            name = (m.get('material_name') or '').strip()
            per = float(m.get('qty_per_pcs') or 0)
            if not name or per <= 0:
                continue
            unit = (m.get('unit') or 'pcs').strip() or 'pcs'
            line_type, mcat = _classify_line(m)
            key = (name.lower(), unit.lower())
            row = agg.setdefault(key, {
                'material_name': name, 'unit': unit, 'material_category': mcat,
                'line_type': line_type, 'qty_estimated': 0.0,
                'cost_per_unit': float(m.get('cost_per_unit') or 0),
                'supplier': m.get('supplier', ''), 'notes': m.get('notes', ''),
                'source_template_id': tpl['id'], 'source_template_version': tpl.get('version'),
                'source_template_label': tpl.get('version_label', ''),
            })
            row['qty_estimated'] += per * qty
            row['cost_per_unit'] = row['cost_per_unit'] or float(m.get('cost_per_unit') or 0)
    return agg, total_pcs, warnings, templates_used


async def accessory_rows_from_materials(db, materials: List[dict]) -> tuple:
    """Baris BOM pcs → payload kebutuhan aksesoris PO. (rows, unlinked, uom_issues).

    `rows` belum punya `id`/`po_id`/`source`/`created_at` — pemanggil yang
    menentukan (explode menyimpannya, pratinjau hanya menampilkan).
    """
    by_name, by_code = await _material_lookup(db)
    rows, unlinked, uom_issues = [], [], []
    for m in materials:
        if m.get('line_type') != 'accessory' or float(m.get('qty_estimated') or 0) <= 0:
            continue
        nm = (m.get('material_name') or '').strip()
        mat = by_name.get(nm.lower()) or by_code.get(nm.upper())
        if not mat:
            unlinked.append(nm)
        # 2026-08-02 · SATUAN: qty_needed HARUS satuan dasar material (dibandingkan
        # dengan stok & harga per satuan dasar). Template BOM maklon menulis satuan
        # bebas (mis. 'lusin'), jadi dikonversi dulu lewat core.bom_uom.
        factor, base_unit, uom_status, uom_note = bom_uom.line_factor(mat, m.get('unit'))
        qty_base = round(float(m['qty_estimated']) * factor, 3)
        if uom_status == 'mismatch':
            uom_issues.append(f"{nm}: {uom_note}")
        rows.append({
            'accessory_id': (mat or {}).get('id'),
            'accessory_name': nm,
            'accessory_code': (mat or {}).get('code', ''),
            'qty_needed': qty_base,
            'unit': base_unit if mat else (m.get('unit') or 'pcs'),
            'qty_input': round(float(m['qty_estimated']), 3),
            'unit_input': m.get('unit', 'pcs'),
            'uom_factor': round(factor, 8),
            'uom_status': uom_status,
            'notes': f"Auto dari BOM Template maklon v{m.get('source_template_version', '-')}"
                     + (f" · {m.get('unit')}→{base_unit}" if factor != 1 else ''),
            'unlinked': mat is None,
        })
    return rows, unlinked, uom_issues


class PreviewItemIn(BaseModel):
    catalog_item_id: Optional[str] = Field(default='', description='FK dewi_maklon_buyer_catalog')
    catalog_id: Optional[str] = Field(default='', description='alias catalog_item_id')
    qty: int = Field(default=0, ge=0)
    label: Optional[str] = Field(default='')


class PreviewAccessoriesIn(BaseModel):
    items: List[PreviewItemIn] = Field(default_factory=list)
    template_id: Optional[str] = None


@router.post('/bom-templates/preview-accessories')
async def preview_accessories_from_bom(payload: PreviewAccessoriesIn,
                                       user: dict = Depends(require_auth)):
    """PRATINJAU kebutuhan aksesoris untuk item PO yang MASIH DI FORM (belum disimpan).

    Read-only: tidak menulis `po_accessories`, `dewi_maklon_bom`, atau apa pun.
    Angkanya identik dengan yang akan tersimpan saat PO disimpan karena memakai
    `aggregate_template_lines` + `accessory_rows_from_materials` yang sama.
    """
    db = get_db()
    norm = [{'catalog_id': (it.catalog_item_id or it.catalog_id or '').strip(),
             'qty': int(it.qty or 0), 'label': it.label or ''}
            for it in (payload.items or [])]
    forced = None
    if payload.template_id:
        forced = await db.dewi_maklon_bom_templates.find_one({'id': payload.template_id}, {'_id': 0})
        if not forced:
            raise HTTPException(404, 'BOM Template tidak ditemukan')
    agg, total_pcs, warnings, templates_used = await aggregate_template_lines(
        db, norm, forced_template=forced)
    materials = []
    for row in agg.values():
        materials.append({
            'material_name': row['material_name'],
            'material_category': row['material_category'],
            'line_type': row['line_type'],
            'unit': row['unit'],
            'qty_estimated': round(row['qty_estimated'], 4),
            'source_template_version': row.get('source_template_version'),
        })
    acc_rows, unlinked, uom_issues = await accessory_rows_from_materials(db, materials)
    if unlinked:
        warnings.append(
            'Baris BOM berikut belum tertaut master material sehingga stoknya tidak bisa dicek: '
            + ', '.join(unlinked[:10]))
    warnings.extend(uom_issues[:10])
    return {
        'ok': True,
        'total_pcs': total_pcs,
        'accessories': acc_rows,
        'bulk': [m for m in materials if m.get('line_type') == 'bulk'],
        'templates_used': list(templates_used.values()),
        'warnings': warnings,
    }
