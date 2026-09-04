"""routes/variant_onboarding.py — **Onboarding Produk Platform → Master** (Sesi #28).

Semua aturannya ada di :mod:`core.variant_identity`. Berkas ini hanya pintu
HTTP-nya, supaya identitas barang tidak pernah punya dua kamus.

Kenapa pintu ini ada (diukur pada data hidup, bukan tebakan):
``GET /api/sync-audit/report`` melaporkan **A1 CRITICAL: NOL dari 601 baris
pesanan menunjuk master gudang** dan **A5: 553 pesanan di antrean gudang, tidak
satu pun siap dialokasikan**. Penyebabnya: 83 SKU platform dari **8 produk
nyata** tidak punya master, dan mesin lama menabrakkan 65 dari 83 SKU itu
menjadi identitas yang sama (``POLKA BLACK … PAKAI KARET`` = ``hitam/XL`` =
``BLACK … TANPA KARET``). Menyelesaikan 83 baris satu per satu adalah cara
paling pasti membuat fitur ini tidak dipakai — jadi pintunya **per produk**:
8 keputusan, bukan 83.

Endpoint (prefix ``/api/variant-onboarding``):
  GET    /products            — 8 produk yang dipesan pembeli tetapi belum dikenal
  GET    /plan                — PRATINJAU satu produk (dijamin tidak menulis)
  POST   /apply               — terapkan (idempoten)
  POST   /rollback            — batalkan onboarding satu model (admin)
  GET    /identity-preview    — baca satu string variasi → identitas 3 dimensi
  GET    /options             — master Opsi varian (dimensi ke-3)
  POST   /options             — tambah/ubah opsi (admin)
  DELETE /options/{code}      — nonaktifkan opsi (admin)
  GET    /colors/duplicates   — pratinjau perapian palet warna kembar
  POST   /colors/merge        — terapkan perapian (admin)
  POST   /masters/ensure      — semai master opsi/ukuran/kategori + index (admin)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import check_role, log_activity, require_auth
from core import variant_identity as vi
from database import get_db

router = APIRouter(prefix='/api/variant-onboarding', tags=['variant-onboarding'])


def _admin(user: dict, perm: str):
    if not check_role(user, ['admin'], perm):
        raise HTTPException(status_code=403,
                            detail='Hanya System Admin yang boleh melakukan ini.')


class ApplyIn(BaseModel):
    product_key: str = Field(..., description='Kunci produk dari GET /products')
    model_id: Optional[str] = Field(None, description='Tunjuk model master yang SUDAH ada (dari pemilih)')
    model_name: Optional[str] = Field(None, description='Hanya untuk API/uji — layar tidak mengetik nama model')
    category_code: Optional[str] = Field(None, description='Kode kategori master')
    account_id: Optional[str] = None


class RollbackIn(BaseModel):
    model_id: str


class OptionIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=8)
    name: str = Field(..., min_length=1, max_length=60)
    order_seq: int = 50
    notes: str = ''
    active: bool = True


class MergeIn(BaseModel):
    apply: bool = Field(default=False, description='False = pratinjau (tidak menulis apa pun)')


# ══════════════════════════════════════════════════════════════════════════════
@router.get('/products')
async def products(account_id: Optional[str] = None,
                   only_unmapped: bool = Query(default=True),
                   limit: int = Query(default=800, ge=10, le=3000),
                   user: dict = Depends(require_auth)):
    """Produk yang dipesan pembeli tetapi belum dikenal master gudang.

    Satu kartu = satu produk (bukan satu SKU): pada data hidup 83 SKU hanya
    berasal dari 8 produk.
    """
    db = get_db()
    return await vi.list_product_groups(db, account_id=account_id, limit=limit,
                                        only_unmapped=only_unmapped)


@router.get('/plan')
async def plan(product_key: str = Query(...),
               model_id: Optional[str] = None,
               model_name: Optional[str] = None,
               category_code: Optional[str] = None,
               account_id: Optional[str] = None,
               user: dict = Depends(require_auth)):
    """PRATINJAU onboarding — **dijamin tidak menulis apa pun**.

    Pemilik melihat: model apa yang akan dipakai/dibuat, warna·ukuran·opsi baru
    apa yang akan lahir, daftar varian + SKU-nya, dan berapa SKU serta baris
    pesanan yang akan tertaut. Kode model pun dipratinjau dengan MENGINTIP
    counter, bukan menaikkannya.
    """
    db = get_db()
    res = await vi.plan_onboarding(db, product_key=product_key, model_id=model_id,
                                  model_name=model_name, category_code=category_code,
                                  account_id=account_id)
    if not res.get('ok'):
        raise HTTPException(status_code=res.get('status', 400), detail=res.get('message'))
    return res


@router.post('/apply')
async def apply(body: ApplyIn, user: dict = Depends(require_auth)):
    """Terapkan onboarding satu produk. Idempoten — klik dua kali tidak
    menggandakan apa pun."""
    db = get_db()
    res = await vi.apply_onboarding(db, product_key=body.product_key,
                                   model_id=body.model_id,
                                   model_name=body.model_name,
                                   category_code=body.category_code,
                                   account_id=body.account_id, user=user)
    if not res.get('ok') and res.get('status'):
        raise HTTPException(status_code=res['status'], detail=res.get('message'))
    await log_activity(user.get('id'), user.get('name'), 'onboarding_produk',
                       'variant-onboarding',
                       f"{res.get('model', {}).get('name')}: {res.get('message')}")
    return res


@router.post('/rollback')
async def rollback(body: RollbackIn, user: dict = Depends(require_auth)):
    """Batalkan onboarding satu model — hanya dokumen yang lahir darinya."""
    _admin(user, 'variant_onboarding.rollback')
    db = get_db()
    res = await vi.rollback_onboarding(db, model_id=body.model_id, user=user)
    if not res.get('ok'):
        raise HTTPException(status_code=res.get('status', 400), detail=res.get('message'))
    await log_activity(user.get('id'), user.get('name'), 'rollback_onboarding',
                       'variant-onboarding', res.get('message', ''))
    return res


@router.get('/identity-preview')
async def identity_preview(variation: str = Query(default=''),
                           product_name: str = Query(default=''),
                           shop_name: str = Query(default=''),
                           user: dict = Depends(require_auth)):
    """Baca satu string variasi platform → identitas 3 dimensi + apa yang TIDAK
    terbaca. Dipakai layar untuk menunjukkan alasannya, bukan hanya hasilnya."""
    ident = vi.parse_identity(variation, product_name=product_name, shop_name=shop_name)
    ident['proposed_model_name'] = vi.propose_model_name(product_name, shop_name=shop_name)
    ident['proposed_category_code'] = vi.propose_category_code(product_name)
    return {'ok': True, **ident}


# ── Master OPSI (dimensi ke-3) ────────────────────────────────────────────────
@router.get('/options')
async def list_options(include_inactive: bool = Query(default=False),
                       user: dict = Depends(require_auth)):
    """Master Opsi varian — dimensi ke-3 yang membuat 'Pakai Karet' dan
    'Tanpa Karet' menjadi dua barang, bukan satu."""
    db = get_db()
    await vi.ensure_option_master(db, user=user)
    q = {} if include_inactive else {'active': {'$ne': False}}
    rows = await db[vi.OPTIONS].find(q, {'_id': 0}).sort('order_seq', 1).to_list(200)
    for r in rows:
        r['variant_count'] = await db[vi.VARIANTS].count_documents({'option_code': r.get('code')})
    return {'ok': True, 'rows': rows, 'total': len(rows)}


@router.post('/options')
async def upsert_option(body: OptionIn, user: dict = Depends(require_auth)):
    """Tambah/ubah opsi varian."""
    _admin(user, 'variant_onboarding.options')
    db = get_db()
    code = body.code.strip().upper()
    existing = await db[vi.OPTIONS].find_one({'code': code}, {'_id': 0})
    patch = {'name': body.name.strip(), 'order_seq': int(body.order_seq),
             'notes': body.notes, 'active': bool(body.active),
             'updated_at': vi._now()}
    if existing:
        await db[vi.OPTIONS].update_one({'code': code}, {'$set': patch})
        # nama opsi ikut disegarkan pada varian supaya layar tidak berbohong
        await db[vi.VARIANTS].update_many({'option_code': code},
                                         {'$set': {'option_name': patch['name']}})
    else:
        await db[vi.OPTIONS].insert_one({'id': vi._uid(), 'code': code,
                                        'is_default': code == vi.OPTION_NA,
                                        'created_at': vi._now(),
                                        'created_by': user.get('id', 'system'), **patch})
    doc = await db[vi.OPTIONS].find_one({'code': code}, {'_id': 0})
    await log_activity(user.get('id'), user.get('name'),
                       'ubah_opsi_varian' if existing else 'tambah_opsi_varian',
                       'variant-onboarding', f"{code} — {patch['name']}")
    return {'ok': True, 'option': doc,
            'message': f"Opsi {code} ({patch['name']}) {'diperbarui' if existing else 'ditambahkan'}."}


@router.delete('/options/{code}')
async def deactivate_option(code: str, user: dict = Depends(require_auth)):
    """Nonaktifkan opsi. Ditolak bila masih dipakai varian (data tidak boleh
    menggantung) dan opsi bawaan ``NA`` tidak boleh dimatikan."""
    _admin(user, 'variant_onboarding.options')
    db = get_db()
    code = code.strip().upper()
    if code == vi.OPTION_NA:
        raise HTTPException(status_code=400,
                            detail="Opsi 'Tidak Disebut' (NA) adalah nama resmi bagi listing "
                                   'tanpa opsi — tidak boleh dimatikan.')
    used = await db[vi.VARIANTS].count_documents({'option_code': code, 'active': True})
    if used:
        raise HTTPException(status_code=409,
                            detail=f'Opsi {code} masih dipakai {used} varian aktif.')
    r = await db[vi.OPTIONS].update_one({'code': code},
                                       {'$set': {'active': False, 'updated_at': vi._now()}})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail=f'Opsi {code} tidak ada.')
    return {'ok': True, 'message': f'Opsi {code} dinonaktifkan.'}


# ── Perapian palet warna (keputusan 6a) ───────────────────────────────────────
@router.get('/colors/duplicates')
async def color_duplicates(user: dict = Depends(require_auth)):
    """Pratinjau warna master kembar + rencana perapiannya. Tidak menulis."""
    db = get_db()
    return await vi.merge_duplicate_colors(db, dry_run=True)


@router.post('/colors/merge')
async def color_merge(body: MergeIn, user: dict = Depends(require_auth)):
    """Rapikan palet warna kembar. ``apply=false`` = pratinjau."""
    if body.apply:
        _admin(user, 'variant_onboarding.colors')
    db = get_db()
    res = await vi.merge_duplicate_colors(db, dry_run=not body.apply, user=user)
    if body.apply:
        await log_activity(user.get('id'), user.get('name'), 'rapikan_palet_warna',
                           'variant-onboarding', res.get('message', ''))
    return res


@router.post('/masters/ensure')
async def masters_ensure(user: dict = Depends(require_auth)):
    """Semai master opsi/ukuran/kategori + perluas index unik varian ke 4 sumbu.
    Idempoten — aman dijalankan berulang."""
    _admin(user, 'variant_onboarding.masters')
    db = get_db()
    return {'ok': True, **(await vi.ensure_all_masters(db, user=user))}
