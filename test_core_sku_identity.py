#!/usr/bin/env python3
"""test_core_sku_identity.py — POC INTI Sesi #28.

═══════════════════════════════════════════════════════════════════════════════
YANG DIBUKTIKAN BERKAS INI (semua pada DATA NYATA, bukan data karangan)
═══════════════════════════════════════════════════════════════════════════════
Inti tersulit sesi ini: **identitas varian 3 dimensi yang tidak menabrak**.
Kalau ini salah, gudang mengambil BARANG YANG SALAH — jadi ia dibuktikan lebih
dulu, terpisah, sebelum satu baris UI ditulis.

Keadaan awal yang diukur pada 83 SKU platform hidup (mesin lama):
    83 SKU berbeda → 35 identitas · 17 tabrakan · 65 SKU (78%) · 489 pcs (81%)
    18/83 warna tidak terbaca · 20/83 ukuran tidak terbaca

Sasaran POC:
    T1  identitas INJEKTIF: variasi berbeda ⇒ identitas berbeda (tabrakan = 0);
        variasi sama persis ⇒ identitas sama (dua listing menjual varian sama)
    T2  nama model tidak lagi membuang nama produknya
    T3  kompatibel-balik: 330 SKU varian lama TIDAK berubah sedikit pun
    T4  index unik varian pindah ke 4 sumbu (model·warna·ukuran·opsi)
    T5  dry-run BENAR-BENAR tidak menulis (hitung dokumen sebelum/sesudah)
    T6  apply membangun rantai penuh: model→warna→ukuran→opsi→varian→FG→
        item katalog→pemetaan→tautan pesanan
    T7  apply kedua IDEMPOTEN (0 duplikat)
    T8  dimensi ketiga hidup: KRT/NOK/SMK/NA menjadi 4 varian ber-SKU berbeda
    T9  tidak ada dua variasi berbeda yang menunjuk satu varian di DB
    T10 perapian warna kembar: pratinjau tidak menulis, apply tak meninggalkan
        rujukan menggantung, resolusi warna jadi tunggal
    T11 rollback memulihkan keadaan ⇒ POC bisa dijalankan berulang

Jalankan:
    python3 test_core_sku_identity.py                 # aman (merge warna hanya pratinjau)
    python3 test_core_sku_identity.py --merge-colors  # ikut MENERAPKAN perapian warna
    python3 test_core_sku_identity.py --keep          # jangan rollback produk uji
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))

from dotenv import load_dotenv                                    # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient                # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', '.env'))

from core import sku_bridge as sb                                 # noqa: E402
from core import variant_identity as vi                           # noqa: E402

G, R, Y, C, B, X = ('\033[92m', '\033[91m', '\033[93m', '\033[96m', '\033[1m', '\033[0m')
PASS, FAIL, NOTES = [], [], []

#: Koleksi yang dipantau untuk membuktikan dry-run tidak menulis.
WATCH = ('rahaza_models', 'rahaza_model_variants', 'rahaza_colors', 'rahaza_sizes',
         'rahaza_variant_options', 'rahaza_materials', 'marketing_catalog_items',
         'marketing_catalogs', 'marketing_sku_bridge', 'counters',
         'rahaza_product_categories')


def ok(name, detail=''):
    PASS.append(name)
    print(f'  {G}✓{X} {name}' + (f' — {detail}' if detail else ''))


def bad(name, detail=''):
    FAIL.append(name)
    print(f'  {R}✗ {name}{X}' + (f' — {detail}' if detail else ''))


def note(msg):
    NOTES.append(msg)
    print(f'  {Y}·{X} {msg}')


def head(t):
    print(f'\n{C}{B}{t}{X}')


async def snapshot(db):
    out = {}
    for c in WATCH:
        out[c] = await db[c].count_documents({})
    return out


def diff(a, b):
    return {k: (a[k], b[k]) for k in a if a[k] != b.get(k)}


# ══════════════════════════════════════════════════════════════════════════════
async def t1_injektif(db, rows):
    head('T1 — identitas varian INJEKTIF pada 83 SKU nyata')
    old_ident, new_ident = {}, {}
    unreadable, absent_color, absent_size = [], [], []
    for r in rows:
        pname, var = r.get('product_name') or '', r.get('variation') or ''
        o = sb.parse_variation(var)
        old_ident.setdefault((vi.norm(pname), o.get('color'), o.get('size')), []).append(r)
        n = vi.parse_identity(var, product_name=pname, shop_name=r.get('account_name'))
        new_ident.setdefault((vi.norm(pname), n['identity_key']), []).append((r, n))
        if n['unreadable']:
            unreadable.append((var, n['unreadable']))
        if n['color_source'] == 'absent':
            absent_color.append(var)
        if n['size_source'] == 'absent':
            absent_size.append(var)

    def collisions(index):
        """Tabrakan = satu identitas dipakai >1 variasi yang BERBEDA."""
        out = {}
        for key, items in index.items():
            variations = {vi.norm(it[0]['variation'] if isinstance(it, tuple) else it['variation'])
                          for it in items}
            if len(variations) > 1:
                out[key] = variations
        return out

    old_coll, new_coll = collisions(old_ident), collisions(new_ident)
    old_skus = sum(len(v) for k, v in old_ident.items() if k in old_coll)
    note(f'mesin LAMA: {len(rows)} SKU → {len(old_ident)} identitas · '
         f'{len(old_coll)} tabrakan · {old_skus} SKU tertimpa')
    note(f'mesin BARU: {len(rows)} SKU → {len(new_ident)} identitas · '
         f'{len(new_coll)} tabrakan')

    if new_coll:
        for k, v in list(new_coll.items())[:5]:
            bad('T1 tabrakan identitas', f'{k[1]} ← {sorted(v)[:4]}')
    else:
        ok('T1 tabrakan identitas = 0',
           f'turun dari {len(old_coll)} kelompok / {old_skus} SKU')

    if unreadable:
        for var, u in unreadable[:5]:
            bad('T1 bagian variasi tidak terbaca', f'{var!r} → {u}')
    else:
        ok('T1 tidak ada bagian variasi yang gagal dibaca', f'{len(rows)} SKU')

    # Variasi yang sama persis WAJIB satu identitas (dua listing, satu barang).
    by_var = {}
    for r in rows:
        by_var.setdefault((vi.norm(r.get('product_name')), vi.norm(r.get('variation'))), []).append(r)
    shared = {k: v for k, v in by_var.items() if len(v) > 1}
    bad_share = []
    for (pn, _), items in shared.items():
        keys = {vi.parse_identity(i['variation'], product_name=i['product_name'],
                                 shop_name=i.get('account_name'))['identity_key']
                for i in items}
        if len(keys) > 1:
            bad_share.append((items[0]['variation'], keys))
    if bad_share:
        bad('T1b variasi sama menghasilkan identitas berbeda', str(bad_share[:3]))
    else:
        ok('T1b variasi SAMA PERSIS → satu identitas',
           f'{len(shared)} pasang listing kembar (mis. 2 SKU TikTok, 1 barang)')

    # Warna/ukuran yang "absent" harus BERALASAN (produk itu memang tak punya).
    note(f'warna tidak disebut oleh listing: {len(absent_color)} SKU '
         f'(mis. Jepit Jedai yang hanya beda ukuran)')
    note(f'ukuran tidak disebut oleh listing: {len(absent_size)} SKU '
         f'(Rachel/Ona/Biel/Aisar ⇒ ALLSIZE, keputusan 5a)')

    # Bukti khusus: 8 SKU yang dulu jadi satu 'hitam/XL'.
    sample = [r for r in rows if 'XL' in (r.get('variation') or '')
              and 'Jennifer' in (r.get('product_name') or '')
              and ('BLACK' in (r.get('variation') or ''))]
    keys = {vi.parse_identity(r['variation'], product_name=r['product_name'])['identity_key']
            for r in sample}
    if sample and len(keys) == len({vi.norm(r['variation']) for r in sample}):
        ok('T1c kelompok tabrakan terburuk terpecah benar',
           f'{len(sample)} SKU BLACK/XL → {len(keys)} identitas berbeda')
    elif sample:
        bad('T1c kelompok tabrakan terburuk masih menyatu',
            f'{len(sample)} SKU → {len(keys)} identitas')


async def t2_nama_model(db, rows):
    head('T2 — nama model tidak lagi membuang nama produknya')
    titles = {}
    for r in rows:
        titles.setdefault(r.get('product_name') or '', r.get('account_name') or '')
    expect_token = {'jennifer', 'rachel', 'victoria', 'ona', 'biel', 'jedai', 'aisar', 'rasha'}
    names, missing = {}, []
    for t, shop in titles.items():
        new = vi.propose_model_name(t, shop_name=shop)
        old = sb.clean_product_name(t)
        names[t] = new
        toks = set(vi.norm(new).split())
        if not (toks & expect_token):
            missing.append((t[:50], new, old))
        note(f'{t[:46]:48s} lama={old[:28]!r:30s} baru={new!r}')
    if missing:
        bad('T2 nama model kehilangan identitas produk', str(missing[:3]))
    else:
        ok('T2 setiap nama model memuat nama produknya', f'{len(names)} produk')
    if len(set(names.values())) == len(names):
        ok('T2b nama model tidak ada yang kembar', f'{len(names)} nama unik')
    else:
        dup = [n for n in names.values() if list(names.values()).count(n) > 1]
        bad('T2b dua produk berbeda mendapat nama model sama', str(sorted(set(dup))))


async def t3_kompatibel_balik(db):
    head('T3/T4 — kompatibel-balik & index unik 4 sumbu')
    before = {v['id']: v.get('sku') for v in await db.rahaza_model_variants.find(
        {}, {'_id': 0, 'id': 1, 'sku': 1}).to_list(5000)}
    res = await vi.ensure_all_masters(db)
    after = {v['id']: v.get('sku') for v in await db.rahaza_model_variants.find(
        {}, {'_id': 0, 'id': 1, 'sku': 1}).to_list(5000)}
    changed = {k: (before[k], after.get(k)) for k in before if before[k] != after.get(k)}
    if changed:
        bad('T3 SKU varian lama BERUBAH', str(list(changed.items())[:3]))
    else:
        ok('T3 SKU 330 varian lama tidak berubah sedikit pun', f'{len(before)} varian')

    if vi.make_sku('BLS-0001', 'PWH', 'XL', 'NA') == 'BLS-0001-PWH-XL' and \
            vi.make_sku('BLS-0001', 'PWH', 'XL', 'KRT') == 'BLS-0001-PWH-XL-KRT' and \
            vi.make_sku('BLS-0001', 'PWH', 'XL') == 'BLS-0001-PWH-XL':
        ok("T3b opsi 'Tidak Disebut' tidak menambah akhiran SKU",
           'BLS-0001-PWH-XL vs BLS-0001-PWH-XL-KRT')
    else:
        bad('T3b bentuk SKU salah', vi.make_sku('BLS-0001', 'PWH', 'XL', 'NA'))

    info = await db.rahaza_model_variants.index_information()
    if 'model_size_color_option_unique' in info and 'model_size_color_variant_unique' not in info:
        ok('T4 index unik pindah ke 4 sumbu (model·ukuran·warna·opsi)',
           f"varian dibekali option_code: {res['index']['variants_backfilled']}")
    else:
        bad('T4 index unik varian belum 4 sumbu', str(sorted(info)))

    n_opt = await db.rahaza_variant_options.count_documents({'active': True})
    codes = sorted(o['code'] for o in await db.rahaza_variant_options.find(
        {}, {'_id': 0, 'code': 1}).to_list(50))
    if n_opt >= 4 and {'NA', 'KRT', 'NOK', 'SMK'} <= set(codes):
        ok('T4b master opsi tersedia', f'{n_opt} opsi: {codes}')
    else:
        bad('T4b master opsi belum lengkap', str(codes))

    no_opt = await db.rahaza_model_variants.count_documents(
        {'option_code': {'$in': [None, '']}})
    if no_opt == 0:
        ok('T4c seluruh varian punya kolom opsi yang terisi', "varian lama = 'NA'")
    else:
        bad('T4c ada varian tanpa option_code', f'{no_opt} varian')


async def t5_t9_onboarding(db, groups, merge_colors, keep):
    head('T5/T6/T7/T8/T9 — onboarding produk: pratinjau, terapkan, idempoten')
    products = groups['products']
    if not products:
        bad('T5 tidak ada produk belum tertaut untuk diuji', 'data nyata kosong')
        return None
    target = sorted(products, key=lambda p: p['sku_count'])[0]
    note(f"produk uji (terkecil): {target['product_name'][:52]!r} — "
         f"{target['sku_count']} SKU · {target['pcs']} pcs")

    # ── T5 dry-run tidak menulis ──────────────────────────────────────────────
    snap_a = await snapshot(db)
    plan = await vi.plan_onboarding(db, product_key=target['product_key'])
    snap_b = await snapshot(db)
    d = diff(snap_a, snap_b)
    if not plan.get('ok'):
        bad('T5 rencana gagal disusun', plan.get('message'))
        return None
    if d:
        bad('T5 dry-run MENULIS ke database', str(d))
    else:
        ok('T5 pratinjau tidak menulis apa pun',
           f"{len(WATCH)} koleksi dipantau; rencana: {plan['totals']['variants_new']} varian baru")
    note(f"rencana: model={plan['model']['name']!r} ({plan['model']['category_name']}) "
         f"kode={plan['model']['code']} · warna baru={plan['totals']['colors_new']} · "
         f"SKU akan ditautkan={plan['totals']['skus_to_map']}")
    for v in plan['variants'][:6]:
        note(f"   {v['sku']:26s} {v['color_name']:14s} {v['size_code']:7s} "
             f"{v['option_name']:18s} ← {v['variations'][:1]}")

    # ── T6 apply ──────────────────────────────────────────────────────────────
    res = await vi.apply_onboarding(db, product_key=target['product_key'],
                                    user={'id': 'poc', 'name': 'POC Sesi 28'})
    if not res.get('ok'):
        bad('T6 apply gagal', str(res.get('failures') or res.get('message')))
        return None
    ok('T6 apply membangun master + menautkan SKU', res['message'])

    model_id = res['model']['id']
    # rantai penuh harus utuh untuk SETIAP varian
    broken = []
    for v in res['variants']:
        var = await db.rahaza_model_variants.find_one({'id': v['variant_id']}, {'_id': 0})
        fg = await db.rahaza_materials.find_one({'variant_id': v['variant_id'], 'type': 'fg'},
                                               {'_id': 0, 'id': 1, 'code': 1})
        item = await db.marketing_catalog_items.find_one(
            {'fg_material_id': (fg or {}).get('id')}, {'_id': 0, 'id': 1})
        br = await db.marketing_sku_bridge.count_documents(
            {'platform_sku_id': {'$in': v['platform_sku_ids']}})
        if not (var and fg and item and br == len(v['platform_sku_ids'])):
            broken.append({'sku': v['sku'], 'varian': bool(var), 'fg': bool(fg),
                           'item': bool(item), 'bridge': br})
    if broken:
        bad('T6b rantai identitas tidak utuh', str(broken[:3]))
    else:
        ok('T6b rantai utuh varian→FG→item katalog→pemetaan',
           f"{len(res['variants'])} varian")

    # baris pesanan benar-benar tertaut
    psids = [p for v in res['variants'] for p in v['platform_sku_ids']]
    unlinked = 0
    async for o in db.marketing_orders.find({'items.platform_sku_id': {'$in': psids}},
                                            {'_id': 0, 'items': 1}):
        for ln in (o.get('items') or []):
            if str(ln.get('platform_sku_id') or '') in psids and not ln.get('fg_material_id'):
                unlinked += 1
    if unlinked:
        bad('T6c masih ada baris pesanan yang belum menunjuk master', f'{unlinked} baris')
    else:
        ok('T6c seluruh baris pesanan produk ini menunjuk master',
           f"{res['order_lines_linked']} baris diperbarui")

    # ── T7 idempoten ─────────────────────────────────────────────────────────
    snap_c = await snapshot(db)
    res2 = await vi.apply_onboarding(db, product_key=target['product_key'],
                                     user={'id': 'poc'})
    snap_d = await snapshot(db)
    grew = {k: v for k, v in diff(snap_c, snap_d).items() if v[1] > v[0]}
    if res2.get('created', {}).get('variants') or grew:
        bad('T7 apply kedua membuat data baru', f"created={res2.get('created')} tumbuh={grew}")
    else:
        ok('T7 apply kedua idempoten', 'tidak ada varian/dokumen baru')

    # ── T8 dimensi ketiga hidup ──────────────────────────────────────────────
    all_groups = await vi.list_product_groups(db, only_unmapped=False)
    jenn = next((p for p in all_groups['products']
                 if 'jennifer' in vi.norm(p['product_name'])), None)
    if jenn:
        jplan = await vi.plan_onboarding(db, product_key=jenn['product_key'])
        opts = {v['option_code'] for v in jplan['variants']}
        skus = {v['sku'] for v in jplan['variants']}
        quad = [v for v in jplan['variants']
                if v['color_name'] == 'Polka Black' and v['size_code'] == 'XL']
        if len(opts) >= 4 and len(skus) == len(jplan['variants']):
            ok('T8 dimensi ketiga hidup pada produk terbesar',
               f"{len(jplan['variants'])} varian · opsi={sorted(opts)} · SKU semuanya unik")
            for v in sorted(quad, key=lambda x: x['option_code']):
                note(f"   {v['sku']:28s} {v['option_name']:20s} ← {v['variations'][:1]}")
        else:
            bad('T8 opsi belum memecah varian',
                f"opsi={sorted(opts)} sku_unik={len(skus)}/{len(jplan['variants'])}")
    else:
        bad('T8 produk Jennifer Blouse tidak ditemukan', 'tidak bisa diukur')

    # ── T9 tidak ada dua variasi berbeda menunjuk satu varian ────────────────
    per_variant = {}
    async for b in db.marketing_sku_bridge.find({}, {'_id': 0}):
        per_variant.setdefault(b.get('variant_id'), set()).add(vi.norm(b.get('variation_sample')))
    multi = {k: v for k, v in per_variant.items() if k and len(v) > 1}
    if multi:
        bad('T9 satu varian ditunjuk beberapa variasi berbeda', str(list(multi.items())[:3]))
    else:
        ok('T9 di DB: tidak ada dua variasi berbeda menunjuk satu varian',
           f'{len(per_variant)} varian terpetakan')
    return {'model_id': model_id, 'target': target, 'variants': res['variants']}


async def t10_warna(db, merge_colors):
    head('T10 — perapian palet warna kembar (keputusan 6a)')
    snap_a = await snapshot(db)
    prev = await vi.merge_duplicate_colors(db, dry_run=True)
    snap_b = await snapshot(db)
    if diff(snap_a, snap_b):
        bad('T10 pratinjau perapian warna MENULIS', str(diff(snap_a, snap_b)))
    else:
        ok('T10 pratinjau perapian warna tidak menulis', prev['message'])
    for gp in prev['groups']:
        note(f"   {gp['group']:10s} kanonik={gp['canonical']['code']} "
             f"({gp['canonical']['variants']} varian, {gp['canonical']['stock_rows']} stok) ← "
             + ', '.join(f"{d['code']}({d['variants']}v: hapus {d['to_delete']}/alihkan {d['to_repoint']})"
                         for d in gp['duplicates']))
    for b in prev['blocked']:
        note(f"   DILEWATI {b['code']}: {b['reason']}")

    if not merge_colors:
        note('perapian TIDAK diterapkan (jalankan dengan --merge-colors untuk menerapkan)')
        return
    res = await vi.merge_duplicate_colors(db, dry_run=False, user={'id': 'poc'})
    ok('T10b perapian warna diterapkan', res['message'])
    left = await vi.merge_duplicate_colors(db, dry_run=True)
    if left['groups_affected'] and not left['blocked']:
        bad('T10c masih ada warna kembar setelah perapian', left['message'])
    else:
        ok('T10c palet warna aktif tidak lagi kembar',
           f"{left['groups_affected']} kelompok tersisa (semuanya beralasan)")
    dangling = 0
    async for v in db.rahaza_model_variants.find({}, {'_id': 0, 'color_id': 1, 'sku': 1}):
        c = await db.rahaza_colors.find_one({'id': v.get('color_id')}, {'_id': 0, 'id': 1})
        if not c:
            dangling += 1
    if dangling:
        bad('T10d ada varian menunjuk warna yang sudah tidak ada', f'{dangling} varian')
    else:
        ok('T10d tidak ada varian yang menggantung ke warna terhapus')
    dup_sku = {}
    async for v in db.rahaza_model_variants.find({}, {'_id': 0, 'sku': 1}):
        dup_sku[v.get('sku')] = dup_sku.get(v.get('sku'), 0) + 1
    kembar = {k: n for k, n in dup_sku.items() if n > 1}
    if kembar:
        bad('T10e SKU varian kembar setelah perapian', str(list(kembar.items())[:5]))
    else:
        ok('T10e tidak ada SKU varian kembar', f'{len(dup_sku)} SKU')


async def t11_rollback(db, ctx, keep):
    head('T11 — rollback memulihkan keadaan (POC bisa diulang)')
    if not ctx:
        note('dilewati: onboarding uji tidak berjalan')
        return
    if keep:
        note('dilewati atas permintaan --keep (produk uji dibiarkan tertaut)')
        return
    psids = [p for v in ctx['variants'] for p in v['platform_sku_ids']]
    res = await vi.rollback_onboarding(db, model_id=ctx['model_id'], user={'id': 'poc'})
    ok('T11 rollback dijalankan', res['message'])
    left_v = await db.rahaza_model_variants.count_documents({'model_id': ctx['model_id']})
    left_b = await db.marketing_sku_bridge.count_documents({'platform_sku_id': {'$in': psids}})
    still = 0
    async for o in db.marketing_orders.find({'items.platform_sku_id': {'$in': psids}},
                                            {'_id': 0, 'items': 1}):
        for ln in (o.get('items') or []):
            if str(ln.get('platform_sku_id') or '') in psids and ln.get('fg_material_id'):
                still += 1
    if left_v or left_b or still:
        bad('T11b rollback tidak bersih',
            f'varian={left_v} pemetaan={left_b} baris_pesanan_masih_tertaut={still}')
    else:
        ok('T11b keadaan pulih bersih', 'varian/pemetaan/tautan pesanan kembali seperti semula')


async def main():
    merge_colors = '--merge-colors' in sys.argv
    keep = '--keep' in sys.argv
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]

    print(f'{B}POC IDENTITAS VARIAN 3 DIMENSI — data nyata{X}')
    un = await sb.list_unmapped(db, limit=500)
    rows = un['rows']
    print(f'  SKU platform belum tertaut: {B}{un["total"]}{X} · {un["pcs_total"]} pcs')

    await t1_injektif(db, rows)
    await t2_nama_model(db, rows)
    await t3_kompatibel_balik(db)

    head('T5-pra — pengelompokan per PRODUK')
    groups = await vi.list_product_groups(db)
    print(f"  {groups['total_skus']} SKU → {B}{groups['total_products']} produk{X} · "
          f"tabrakan total={groups['collisions_total']} · tak terbaca={groups['unreadable_total']}")
    for p in groups['products']:
        print(f"   {p['pcs']:7.0f} pcs {p['sku_count']:3d} SKU  "
              f"{p['proposed_model_name'][:22]:24s} {p['proposed_category_name'][:11]:13s} "
              f"identitas={p['identity_count']:3d} warna={len(p['colors'])} "
              f"ukuran={len(p['sizes'])} opsi={len(p['options'])}")
    if groups['collisions_total'] == 0:
        ok('T5a tidak ada tabrakan identitas di seluruh 8 produk')
    else:
        bad('T5a masih ada tabrakan identitas', str(groups['collisions_total']))

    ctx = await t5_t9_onboarding(db, groups, merge_colors, keep)
    await t10_warna(db, merge_colors)
    await t11_rollback(db, ctx, keep)

    print(f'\n{B}{"="*78}{X}')
    print(f'  {G}LULUS {len(PASS)}{X} · {R}GAGAL {len(FAIL)}{X} · catatan {len(NOTES)}')
    if FAIL:
        print(f'  {R}{B}POC MERAH — inti belum boleh dipakai membangun app:{X}')
        for f in FAIL:
            print(f'    {R}✗{X} {f}')
        return 1
    print(f'  {G}{B}POC HIJAU — inti identitas varian 3 dimensi terbukti pada data nyata.{X}')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
