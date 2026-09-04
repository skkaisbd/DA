"""core/variant_identity.py — SSOT **identitas varian 3 dimensi** (Sesi #28).

═══════════════════════════════════════════════════════════════════════════════
MASALAH NYATA YANG DITUTUP BERKAS INI  (diukur pada 83 SKU platform HIDUP)
═══════════════════════════════════════════════════════════════════════════════
Sesi #20 membangun Jembatan SKU (``core/sku_bridge.py``) — mesinnya benar dan
gate INV-F29 hijau — tetapi **tidak satu barang pun berhasil dijembatani**:
``GET /api/sync-audit/report`` melaporkan ``A1 CRITICAL: NOL dari 601 baris
pesanan menunjuk master gudang`` dan ``A5: 553 pesanan di antrean gudang, tidak
satu pun siap dialokasikan``.

Sebabnya diukur, bukan ditebak. ``sku_bridge.parse_variation`` dijalankan pada 83
string variasi nyata:

    83 SKU berbeda  →  hanya 35 identitas
    17 kelompok TABRAKAN · 65 SKU (78%) · 489 pcs (81%) tertimpa
    18/83 warna tidak terbaca · 20/83 ukuran tidak terbaca

Tabrakan terburuk — **8 SKU berbeda jatuh ke satu identitas** ``hitam/XL``::

    BLACK, XL (LD 120 CM), PAKAI KARET            39 pcs
    POLKA BLACK, XL (LD 120 CM), PAKAI KARET (SMOOK)  12 pcs
    POLKA BLACK, XL (LD 120 CM), TANPA KARET      10 pcs
    BLACK, XL (LD 120 CM), TANPA KARET             7 pcs
    ...

Dua akar sebab:

1. **Warna majemuk dipotong.** Pencocokan lama memakai *substring*
   (``if alias in n``), sehingga ``POLKA WHITE`` menemukan alias ``white`` dan
   menjadi ``putih`` — motif polkadot HILANG dan barang polkadot menjadi
   identik dengan barang polos.
2. **Dimensi ketiga dibuang.** ``PAKAI KARET`` / ``TANPA KARET`` /
   ``PAKAI KARET (SMOOK)`` tidak dibaca sama sekali, padahal itu tiga barang
   yang berbeda harga dan berbeda cara jahit. Skema varian pun hanya punya dua
   sumbu (warna × ukuran), jadi tidak ada tempat menyimpannya.

Akibat kalau dibiarkan: gudang mengambil **barang yang salah** untuk 4 dari 5
pesanan. Ambang ``AUTO_MIN_CONFIDENCE`` menyelamatkan kita (tidak ada data salah
yang sempat tertulis) — tetapi harganya: seluruh 553 pesanan MANDEK.

KEPUTUSAN PEMILIK (dikonfirmasi 2026-08-19, jangan ditebak ulang)
----------------------------------------------------------------
* **1a** ``PAKAI KARET`` / ``TANPA KARET`` / ``PAKAI KARET (SMOOK)`` menjadi
  **dimensi ketiga resmi "Opsi"** pada master varian. SKU menjadi
  ``{MODEL}-{WARNA}-{UKURAN}-{OPSI}``, contoh ``BLS-0001-PBL-XL-KRT``.
* **2a** ``POLKA WHITE`` / ``POLKA BLACK`` adalah **warna master tersendiri**
  ("Polka White", "Polka Black") — bukan Putih/Hitam.
* **3a** Listing lama yang tidak menyebut karet (mis. ``POLKA WHITE, XL``, 74
  pcs — SKU terlaris) menjadi **varian tersendiri** dengan opsi
  **"Tidak Disebut"**. Tidak digabung ke PAKAI/TANPA KARET: menggabungkan =
  mengarang.
* **4a** ``ODI ALL SIZE WARNA RANDOM`` → warna master **"Random / Campur"**.
* **5a** ``JEPIT JEDAI`` = kategori **Aksesoris**, ukuran **BESAR/KECIL**;
  ``RASHA BLOUSE`` memakai ukuran master **JMB/STD** yang sudah ada;
  ``RACHEL ONESET`` · ``ONA DRESS`` · ``BIEL TOP`` · ``AISAR DRESS`` tidak punya
  ukuran ⇒ **ALLSIZE**.
* **6a** Warna master kembar (``Putih`` PTH+WHT · ``Hitam`` HTM+BLK · ``Merah``
  MRH+RED · ``Krem`` KRM+CRM) **dirapikan**: satu kode kanonik, sisanya
  dinonaktifkan dan rujukannya dialihkan.

ATURAN KERAS
------------
1. **Identitas wajib injektif.** Dua string variasi yang BERBEDA tidak boleh
   pernah menghasilkan satu identitas. String yang SAMA PERSIS wajib
   menghasilkan identitas yang sama (dua listing TikTok menjual varian yang
   sama — itu sah, dan memang terjadi 12 kali pada data ini).
2. **Tidak menebak, tetapi juga tidak menyerah diam-diam.** Bagian variasi yang
   tidak dikenali dilaporkan di ``unreadable`` — ia tidak boleh hilang tanpa
   suara. Ketidakhadiran diberi nama: warna → "Tidak Disebut", ukuran →
   "ALLSIZE", opsi → "Tidak Disebut".
3. **Menyalin ≠ menebak.** Warna yang tidak ada di kamus TIDAK dipaksa masuk
   warna master terdekat (itulah cacat #1); ia **disalin apa adanya** sebagai
   calon warna master baru, dan pemilik melihatnya di pratinjau sebelum
   ditulis.
4. **Aditif & kompatibel-balik.** 330 varian lama TIDAK boleh berubah SKU.
   Opsi "Tidak Disebut" (``NA``) sengaja **tidak** menambah akhiran pada SKU.
5. ``dry_run`` benar-benar tidak menulis apa pun — termasuk tidak memakai
   counter kode model (kode dipratinjau dengan mengintip counter, bukan
   menaikkannya).
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

VARIANTS = 'rahaza_model_variants'
MODELS = 'rahaza_models'
COLORS = 'rahaza_colors'
SIZES = 'rahaza_sizes'
OPTIONS = 'rahaza_variant_options'
MATERIALS = 'rahaza_materials'
ITEMS = 'marketing_catalog_items'
ORDERS = 'marketing_orders'
BRIDGE = 'marketing_sku_bridge'

#: Penanda asal dokumen yang lahir dari onboarding — dipakai rollback POC.
CREATED_VIA = 'variant_onboarding'


def _now():
    return datetime.now(timezone.utc)


def _uid():
    return str(uuid.uuid4())


def _f(v, d=0.0):
    try:
        return float(v if v is not None else d)
    except (TypeError, ValueError):
        return d


_PUNCT = re.compile(r'[^a-z0-9]+')


def norm(s) -> str:
    """Turunkan teks ke bentuk banding: huruf kecil, tanda baca → spasi."""
    return _PUNCT.sub(' ', str(s or '').lower()).strip()


# ══════════════════════════════════════════════════════════════════════════════
# DIMENSI 3 — master OPSI varian
# ══════════════════════════════════════════════════════════════════════════════
OPTION_NA = 'NA'

#: Master opsi bawaan. ``NA`` wajib ada: ia adalah nama resmi bagi
#: "listing ini tidak menyebut opsinya" (keputusan 3a) — supaya ketidakhadiran
#: punya identitas dan tidak diam-diam digabung ke opsi lain.
OPTION_SEED = (
    {'code': OPTION_NA, 'name': 'Tidak Disebut', 'order_seq': 0,
     'notes': 'Listing tidak menyebut opsi. Tidak menambah akhiran pada SKU '
              '(menjaga SKU varian lama tidak berubah).'},
    {'code': 'KRT', 'name': 'Pakai Karet', 'order_seq': 1,
     'notes': 'Pinggang/lengan memakai karet.'},
    {'code': 'NOK', 'name': 'Tanpa Karet', 'order_seq': 2,
     'notes': 'Tanpa karet.'},
    {'code': 'SMK', 'name': 'Pakai Karet Smook', 'order_seq': 3,
     'notes': 'Karet smook (kerut bersusun).'},
    # SESI #34 — opsi yang MEMANG dipakai listing pemilik (dari variasi nyata
    # 'HITAM, DEWASA & L ANAK (6-7th)' dan 'BUNDLING 2 PCS'). Segmen usia &
    # bundling membedakan barang di rak, jadi ia opsi — bukan keterangan.
    {'code': 'DWS', 'name': 'Dewasa', 'order_seq': 4,
     'notes': 'Listing ukuran dewasa.'},
    {'code': 'ANK', 'name': 'Anak', 'order_seq': 5,
     'notes': 'Listing ukuran anak.'},
    {'code': 'DWSANK', 'name': 'Dewasa & Anak', 'order_seq': 6,
     'notes': 'Satu listing memuat pasangan dewasa + anak (couple/family set).'},
    {'code': 'BDL', 'name': 'Bundling', 'order_seq': 7,
     'notes': 'Dijual sebagai paket beberapa pcs.'},
)

#: Alias opsi — **urut dari yang paling panjang**. Wajib: "pakai karet (smook)"
#: mengandung "pakai karet"; kalau yang pendek diperiksa lebih dulu, SMOOK
#: hilang dan dua barang berbeda menjadi satu.
OPTION_ALIASES = (
    # SESI #34 — dari variasi nyata: 'HITAM, DEWASA & L ANAK (6-7th)',
    # 'BUNDLING 2 PCS'. Segmen (anak/dewasa) dan bundling MEMANG membedakan
    # barang, jadi ia dimensi ketiga (opsi) — bukan keterangan.
    ('dewasa anak', 'DWSANK'),
    ('bundling', 'BDL'),
    ('bundle', 'BDL'),
    ('anak', 'ANK'),
    ('dewasa', 'DWS'),
    ('pakai karet smook', 'SMK'),
    ('karet smook', 'SMK'),
    ('smook', 'SMK'),
    ('smok', 'SMK'),
    ('tanpa karet', 'NOK'),
    ('non karet', 'NOK'),
    ('no karet', 'NOK'),
    ('tanpa elastis', 'NOK'),
    ('pakai karet', 'KRT'),
    ('dengan karet', 'KRT'),
    ('karet', 'KRT'),
)

OPTION_NAMES = {o['code']: o['name'] for o in OPTION_SEED}


# ══════════════════════════════════════════════════════════════════════════════
# WARNA — hanya terjemahan bahasa yang disatukan; nuansa TIDAK digabung
# ══════════════════════════════════════════════════════════════════════════════
#: Peta ini SENGAJA hanya memuat **sinonim bahasa** (white=putih, black=hitam).
#: Ia TIDAK memuat penggabungan nuansa seperti ``butter yellow → kuning`` atau
#: ``mocca → coklat`` yang dipakai kamus lama: nuansa adalah barang yang
#: berbeda di rak, dan menggabungkannya membuat gudang mengambil yang salah.
COLOR_TRANSLATE = {
    'putih': 'Putih', 'white': 'Putih',
    'hitam': 'Hitam', 'black': 'Hitam',
    'abu': 'Abu-abu', 'abu abu': 'Abu-abu', 'grey': 'Abu-abu', 'gray': 'Abu-abu',
    'navy': 'Navy', 'dongker': 'Navy',
    'biru': 'Biru', 'blue': 'Biru',
    'merah': 'Merah', 'red': 'Merah',
    'maroon': 'Maroon', 'marun': 'Maroon',
    'hijau': 'Hijau', 'green': 'Hijau',
    'kuning': 'Kuning', 'yellow': 'Kuning',
    'coklat': 'Coklat', 'brown': 'Coklat',
    'krem': 'Krem', 'cream': 'Krem',
    'pink': 'Pink',
    'ungu': 'Ungu', 'purple': 'Ungu',
    'oranye': 'Oranye', 'orange': 'Oranye', 'oren': 'Oranye',
    'tosca': 'Tosca',
}

#: Perbaikan EJAAN (kata yang sama, ditulis berbeda oleh admin toko).
#: Bukan penggabungan nuansa: ``nuvgett`` dan ``nuvget`` adalah satu kata.
COLOR_SPELLING = {
    'nuvgett': 'Nuvget',
    'nuget': 'Nuvget',
    'nuvget': 'Nuvget',
    'mahogani': 'Mahogany',
    'mahogany': 'Mahogany',
    'burgundi': 'Burgundy',
    'polkawhite': 'Polka White',
    'polkablack': 'Polka Black',
}

#: Nama resmi untuk SKU "warna acak" (keputusan 4a).
COLOR_RANDOM = 'Random / Campur'
RANDOM_TOKENS = ('random', 'acak', 'campur', 'mix')

#: Nama resmi untuk "variasi ini tidak menyebut warna" (mis. Jepit Jedai yang
#: hanya membedakan ukuran). Bukan kegagalan baca — memang tidak ada warnanya.
COLOR_ABSENT = 'Tidak Disebut'
COLOR_ABSENT_CODE = 'TDI'

#: Kode yang menyatakan KETIDAKHADIRAN. Ia punya nama & baris master (supaya
#: layar bisa menampilkannya apa adanya) tetapi **tidak ikut ke dalam SKU** —
#: `AKS-0001-BESAR` jauh lebih terbaca daripada `AKS-0001-TDI-BESAR`, dan
#: inilah juga yang menjaga SKU 330 varian lama tidak berubah.
ABSENT_CODES = frozenset({OPTION_NA, COLOR_ABSENT_CODE})

#: Kosakata yang menandai sebuah kata adalah WARNA walau tidak ada di kamus —
#: dipakai hanya untuk memutuskan "ini bagian warna", bukan untuk menebak
#: warnanya jadi apa.
_COLOR_VOCAB = (set(COLOR_TRANSLATE) | set(COLOR_SPELLING)
                | {w for k in COLOR_TRANSLATE for w in k.split()}
                | set(RANDOM_TOKENS) | {'polka', 'polkadot'})


# ══════════════════════════════════════════════════════════════════════════════
# UKURAN
# ══════════════════════════════════════════════════════════════════════════════
SIZE_TRANSLATE = {
    's': 'S', 'small': 'S',
    'm': 'M', 'medium': 'M',
    'l': 'L', 'large': 'L',
    'xl': 'XL', 'extra large': 'XL', 'extralarge': 'XL',
    'xxl': 'XXL', '2xl': 'XXL', 'xx l': 'XXL',
    'xxxl': 'XXXL', '3xl': 'XXXL',
    'all size': 'ALLSIZE', 'allsize': 'ALLSIZE', 'all': 'ALLSIZE',
    'one size': 'ALLSIZE', 'onesize': 'ALLSIZE', 'fit l': 'ALLSIZE',
    'standar': 'STD', 'standard': 'STD', 'std': 'STD', 'reguler': 'STD',
    'jumbo': 'JMB', 'jmb': 'JMB', 'big size': 'JMB', 'bigsize': 'JMB',
    # keputusan 5a — kosakata ukuran aksesoris
    'besar': 'BESAR', 'kecil': 'KECIL',
}

#: Ukuran yang mungkin belum ada di master (keputusan 5a) — disemai saat apply.
SIZE_SEED_EXTRA = (
    {'code': 'BESAR', 'name': 'Besar', 'order_seq': 40},
    {'code': 'KECIL', 'name': 'Kecil', 'order_seq': 41},
    {'code': 'XXXL', 'name': 'XXXL', 'order_seq': 6},
)

SIZE_ABSENT = 'ALLSIZE'

_SIZE_VOCAB = set(SIZE_TRANSLATE) | {w for k in SIZE_TRANSLATE for w in k.split()}

#: Satuan & kata pengukur yang bukan identitas (LD = lingkar dada).
_SPEC_KEYS = ('ld', 'pb', 'lp', 'lb')
_UNIT_TOKENS = {'cm', 'mm', 'inch', 'in'}

#: Kata nama toko/platform — dibuang dari usulan nama model.
SHOP_NOISE = {'tiktok', 'shopee', 'tokopedia', 'lazada', 'blibli', 'store',
              'shop', 'official', 'olshop', 'id', 'by', 'seller', 'mall'}


# ══════════════════════════════════════════════════════════════════════════════
# Pembacaan variasi → identitas 3 dimensi
# ══════════════════════════════════════════════════════════════════════════════
def _title(s: str) -> str:
    """Title-case yang mempertahankan bentuk khusus ('Random / Campur')."""
    s = re.sub(r'\s{2,}', ' ', str(s or '').strip())
    return ' '.join(w.capitalize() if w.isalpha() else w for w in s.split())


def _extract_spec(text: str) -> tuple:
    """Ambil angka ukur (LD/PB/LP + cm) → ``(sisa_teks, spec)``.

    ``XL (LD 120 CM)`` → ukuran XL, spec ``{'ld_cm': 120}``. Angka ini
    **keterangan**, bukan identitas: dua listing dengan LD sama tetapi opsi
    berbeda tetap barang berbeda, dan sebaliknya.
    """
    spec = {}
    t = text
    # ── SESI #34 — pola NYATA dari ekspor Shopee/TikTok pemilik ────────────────
    # Diukur pada data yang baru diimpor: 8 variasi tidak terbaca sama sekali
    # (INV-F30/V1c) karena tiga pola ini belum dikenal. Semuanya KETERANGAN,
    # bukan identitas barang, jadi diambil ke `spec` dan tidak lagi membuat
    # seluruh variasi gagal dibaca:
    #   'MAGENTA, L  (6-7th)'          → rentang usia anak  → spec.usia
    #   'JEDAI BESAR 1 PCS'            → jumlah kemasan     → spec.isi_pcs
    #   'ANNA - MAHOGANY, STANDAR / FIT TO M' → catatan muat → spec.fit_to
    # Pemisah rentang bisa hilang setelah `norm()` ('(6-7th)' → '6 7th'), jadi
    # tanda hubung MAUPUN spasi diterima. Tanpa ini, '6' tertinggal sebagai kata
    # tak terbaca dan seluruh variasi dianggap gagal.
    for mt in list(re.finditer(r'\b(\d+)\s*[-–\s]\s*(\d+)\s*(?:th|thn|tahun)\b', t)):
        spec['usia_tahun'] = f"{mt.group(1)}-{mt.group(2)}"
        t = t.replace(mt.group(0), ' ')
    for mt in list(re.finditer(r'\b(\d+)\s*(?:th|thn|tahun)\b', t)):
        spec.setdefault('usia_tahun', mt.group(1))
        t = t.replace(mt.group(0), ' ')
    for mt in list(re.finditer(r'\b(\d+)\s*(?:pcs|pc|pack|set|lusin)\b', t)):
        spec.setdefault('isi_pcs', _f(mt.group(1)))
        t = t.replace(mt.group(0), ' ')
    for mt in list(re.finditer(r'\bfit\s*to\s*([a-z0-9]+)\b', t)):
        spec.setdefault('fit_to', mt.group(1).upper())
        t = t.replace(mt.group(0), ' ')
    for key in _SPEC_KEYS:
        for mt in list(re.finditer(rf'\b{key}\s*(\d+(?:[.,]\d+)?)\s*(cm|mm|inch|in)?\b', t)):
            spec[f'{key}_cm'] = _f(mt.group(1).replace(',', '.'))
            t = t.replace(mt.group(0), ' ')
    for mt in list(re.finditer(r'\b(\d+(?:[.,]\d+)?)\s*(cm|mm|inch|in)\b', t)):
        spec.setdefault('ukuran_cm', _f(mt.group(1).replace(',', '.')))
        t = t.replace(mt.group(0), ' ')
    return re.sub(r'\s{2,}', ' ', t).strip(), spec


def resolve_color_name(text) -> tuple:
    """Teks warna → ``(nama_warna_master, sumber)``.

    Sumber: ``translated`` (sinonim bahasa) · ``spelling`` (ejaan dirapikan) ·
    ``transcribed`` (disalin apa adanya sebagai calon warna master baru) ·
    ``unreadable`` (tidak masuk akal sebagai warna — dilaporkan, tidak ditebak).

    **Tidak pernah** memakai pencocokan substring: itulah cacat yang membuat
    ``POLKA WHITE`` menjadi ``putih``.
    """
    n = norm(text)
    if not n:
        return None, 'absent'
    flat = n.replace(' ', '')
    if any(tok in n.split() for tok in RANDOM_TOKENS):
        return COLOR_RANDOM, 'random'
    if n in COLOR_SPELLING:
        return COLOR_SPELLING[n], 'spelling'
    if flat in COLOR_SPELLING:
        return COLOR_SPELLING[flat], 'spelling'
    if n in COLOR_TRANSLATE:
        return COLOR_TRANSLATE[n], 'translated'
    words = n.split()
    # Disalin apa adanya bila BENTUKNYA masuk akal sebagai nama warna:
    # 1–3 kata, semua huruf, tidak kepanjangan. Menyalin bukan menebak.
    if 1 <= len(words) <= 3 and all(w.isalpha() for w in words) and len(n) <= 24:
        return _title(n), 'transcribed'
    return None, 'unreadable'


def parse_identity(variation, *, product_name: str = '', shop_name: str = '') -> dict:
    """Baca variasi platform → identitas **3 dimensi** yang tidak menabrak.

    Contoh nyata (semua dari ekspor TikTok toko pemilik)::

      'POLKA WHITE, XL'
          → Polka White · XL  · NA   (listing lama, opsi tidak disebut)
      'POLKA WHITE, XL (LD 120 CM), PAKAI KARET'
          → Polka White · XL  · KRT
      'POLKA WHITE, XL (LD 120 CM), TANPA KARET'
          → Polka White · XL  · NOK
      'POLKA BLACK, XL (LD 120 CM), PAKAI KARET (SMOOK)'
          → Polka Black · XL  · SMK
      'ODI ALL SIZE WARNA RANDOM, XL (LD 120 CM), PAKAI KARET (SMOOK)'
          → Random / Campur · XL · SMK
      'AISAR - MAHOGANY'      → Mahogany     · ALLSIZE · NA
      'JEDAI BESAR 5 cm'      → Tidak Disebut · BESAR  · NA
      'PUTIH, JUMBO'          → Putih        · JMB     · NA

    Ke-empat contoh pertama dahulu jatuh ke SATU identitas ``putih/hitam · XL``.
    """
    raw = str(variation or '')
    parts = [p.strip() for p in re.split(r'[,;|]+', raw) if p.strip()]

    # Kata milik JUDUL PRODUK & NAMA TOKO bukan atribut varian: "AISAR - MAHOGANY"
    # dan "JEDAI BESAR 5 cm" mengulang nama produk di dalam variasinya.
    # Warna/ukuran/opsi DILINDUNGI supaya judul yang memuat warna tidak
    # menghapus warna variasinya.
    protected = _COLOR_VOCAB | _SIZE_VOCAB | {w for a, _ in OPTION_ALIASES for w in a.split()}
    noise = {t for t in norm(product_name).split() if len(t) > 2 and t not in protected}
    noise |= {t for t in norm(shop_name).split() if len(t) > 1 and t not in protected}
    noise |= SHOP_NOISE - protected

    color = color_src = None
    size = None
    option = None
    spec: dict = {}
    unreadable: list = []

    for part in parts:
        residual = norm(part)

        # ── 1. OPSI (dimensi ketiga) ─────────────────────────────────────────
        # SESI #34 — SEMUA alias yang cocok diambil, bukan hanya yang pertama.
        # Alasannya nyata: 'DEWASA & L ANAK (6-7th)' memuat DUA kata opsi;
        # dengan `break`, kata 'dewasa' tertinggal dan variasi dianggap tak
        # terbaca. Pasangan dewasa+anak digabung menjadi satu kode DWSANK karena
        # itu memang SATU barang (listing couple/family).
        found_opts: list = []
        for alias, code in OPTION_ALIASES:
            if alias in residual:
                found_opts.append(code)
                residual = residual.replace(alias, ' ').strip()
        if found_opts:
            codes = set(found_opts)
            merged = ('DWSANK' if {'DWS', 'ANK'} <= codes or 'DWSANK' in codes
                      else found_opts[0])
            if option is None:
                option = merged
            elif option != merged and 'DWSANK' in (option, merged):
                option = 'DWSANK'
        residual = re.sub(r'\s{2,}', ' ', residual).strip()

        # ── 2. Angka ukur (LD/PB/cm) — keterangan, bukan identitas ───────────
        residual, part_spec = _extract_spec(residual)
        spec.update(part_spec)

        toks = [t for t in residual.split() if t and t not in _UNIT_TOKENS]

        # ── 3. Warna acak (keputusan 4a) — diperiksa SEBELUM ukuran, karena
        #       "ODI ALL SIZE WARNA RANDOM" memuat kata 'all size'.
        if any(t in RANDOM_TOKENS for t in toks):
            if color is None:
                color, color_src = COLOR_RANDOM, 'random'
            continue

        # ── 4. Buang kata judul produk / nama toko ───────────────────────────
        toks = [t for t in toks if t not in noise]
        if not toks:
            continue

        # ── 5. UKURAN — hanya bila SELURUH sisa kata adalah kosakata ukuran.
        #       Aturan "seluruhnya" inilah yang mencegah "ODI ALL SIZE WARNA
        #       RANDOM" dibaca sebagai ukuran.
        spaced, flat = ' '.join(toks), ''.join(toks)
        hit = SIZE_TRANSLATE.get(spaced) or SIZE_TRANSLATE.get(flat)
        if not hit and toks and all(t in SIZE_TRANSLATE for t in toks):
            hit = SIZE_TRANSLATE[toks[0]]
        if hit:
            if size is None:
                size = hit
            elif size != hit:
                unreadable.append(f'ukuran ganda: {size} vs {hit}')
            continue

        # ── 6. WARNA ─────────────────────────────────────────────────────────
        nm, src = resolve_color_name(spaced)
        if nm:
            if color is None:
                color, color_src = nm, src
            elif color != nm:
                unreadable.append(f'warna ganda: {color} vs {nm}')
        else:
            unreadable.append(spaced)

    color_final = color or COLOR_ABSENT
    size_final = size or SIZE_ABSENT
    option_final = option or OPTION_NA
    return {
        'color_name': color_final,
        'color_source': color_src or ('absent' if not color else 'translated'),
        'size_code': size_final,
        'size_source': 'vocab' if size else 'absent',
        'option_code': option_final,
        'option_name': OPTION_NAMES.get(option_final, option_final),
        'option_source': 'detected' if option else 'absent',
        'spec': spec,
        'identity_key': f'{color_final}|{size_final}|{option_final}',
        'unreadable': unreadable,
        'parts': parts,
        'variation_raw': raw,
    }


def propose_model_name(product_name, *, shop_name: str = '', words: int = 2) -> str:
    """Usulkan NAMA MODEL dari judul iklan.

    Cacat mesin lama (`sku_bridge.clean_product_name`) yang ditutup di sini —
    diukur pada 8 judul nyata: ia justru **membuang nama produknya** dan
    menyisakan kalimat iklan::

      'ONA DRESS - Midi Dress Salur Wanita Busui Kancing Simple Motif'
          lama → 'Midi Dress Salur Wanita Busui Kancing Simple Motif'   ('ONA' HILANG)
          baru → 'Ona Dress'
      'OUTFIT BOUTIQUE BIEL TOP | ATASAN RAYON | ATASAN WANITA | BAJU'
          lama → 'Atasan Rayon'                                          ('BIEL TOP' HILANG)
          baru → 'Biel Top'

    Aturan: buang nama toko di depan, ambil segmen pertama, ambil ``words``
    kata pertama. Pemilik tetap bisa menyunting nama ini di pratinjau sebelum
    apa pun ditulis — jadi usulan yang kurang pas tidak pernah menjadi data.
    """
    s = str(product_name or '').strip()
    shop_toks = {t for t in norm(shop_name).split() if t and t not in SHOP_NOISE}

    # Buang nama toko di depan judul, sekata demi sekata.
    guard = 0
    while shop_toks and guard < 12:
        guard += 1
        m = re.match(r'^\s*[-–|:]*\s*([A-Za-z0-9&\']+)', s)
        if not m or norm(m.group(1)) not in shop_toks:
            break
        s = s[m.end():]
    s = s.lstrip(' -–|:.,')

    # Segmen pertama (judul marketplace memisah dengan ' - ' atau '|').
    seg = re.split(r'\s+[-–]\s+|\||\s+[-–]|[-–]\s+', s, maxsplit=1)[0].strip()
    seg = seg or s
    picked = [w for w in seg.split() if w][:max(1, int(words or 2))]
    out = _title(' '.join(picked)).strip()
    return out or _title(norm(product_name))[:60] or 'Produk Tanpa Nama'


#: Usulan kategori dari kata kunci judul → kode kategori master.
CATEGORY_HINTS = (
    ('jepit', 'AKSESORIS'), ('aksesoris', 'AKSESORIS'), ('hair clip', 'AKSESORIS'),
    ('rambut', 'AKSESORIS'), ('bros', 'AKSESORIS'), ('scrunchie', 'AKSESORIS'),
    ('oneset', 'SET'), ('one set', 'SET'), ('setelan', 'SET'), ('set ', 'SET'),
    ('dress', 'DRESS'), ('gamis', 'DRESS'),
    ('blouse', 'BLOUSE'), ('blus', 'BLOUSE'), ('atasan', 'BLOUSE'), ('top', 'BLOUSE'),
    ('kemeja', 'KEMEJA'), ('kaos', 'KAOS'), ('polo', 'POLO'),
    ('hoodie', 'HOODIE'), ('sweater', 'SWEATER'), ('cardigan', 'CARDIGAN'),
    ('jacket', 'JACKET'), ('jaket', 'JACKET'), ('vest', 'VEST'),
    ('rok', 'ROK'), ('celana', 'CELANA'), ('kulot', 'CELANA'),
)

#: Kategori yang mungkin belum ada di master (keputusan 5a: Jepit Jedai).
CATEGORY_SEED_EXTRA = (
    {'code': 'AKSESORIS', 'name': 'Aksesoris', 'sku_prefix': 'AKS',
     'description': 'Aksesoris fashion (jepit rambut, bros, scrunchie).'},
)


def propose_category_code(product_name) -> str:
    """Usulkan kode kategori master dari judul. Urutan kata kunci penting:
    'oneset'/'setelan' diperiksa sebelum 'celana' karena RACHEL ONESET adalah
    SET walau judulnya menyebut 'celana kulot'."""
    n = norm(product_name) + ' '
    for kw, code in CATEGORY_HINTS:
        if kw in n:
            return code
    return 'LAINNYA'


def make_sku(model_code, color_code, size_code, option_code=None) -> str:
    """``{MODEL}-{WARNA}-{UKURAN}[-{OPSI}]``.

    Kode yang menyatakan ketidakhadiran (:data:`ABSENT_CODES`) dilewati:
      * opsi ``NA`` tidak menambah akhiran ⇒ 330 SKU varian lama tidak berubah
        sedikit pun (aturan keras #4);
      * warna ``TDI`` (produk tanpa warna, mis. Jepit Jedai) tidak menyisipkan
        kode kosong ⇒ ``AKS-0001-BESAR``, bukan ``AKS-0001-TDI-BESAR``.

    Aman dilakukan karena tidak ada satu pun kode di repo ini yang memecah SKU
    per posisi (diaudit: 0 kemunculan ``sku.split('-')``) — linkage varian
    memakai field eksplisit, bukan penguraian string.
    """
    raw = [str(model_code or '').strip().upper(),
           str(color_code or '').strip().upper(),
           str(size_code or '').strip().upper(),
           str(option_code or '').strip().upper()]
    return '-'.join(p for p in raw if p and p not in ABSENT_CODES)


def propose_color_code(name: str, taken: set) -> str:
    """Kode warna 3 huruf yang bisa dibaca manusia & tidak bertabrakan.

    Majemuk memakai inisial + 2 huruf kata terakhir supaya 'Polka White' (PWH)
    dan 'Polka Black' (PBL) tidak sama-sama menjadi 'POL'.
    """
    if norm(name) == norm(COLOR_ABSENT):
        return COLOR_ABSENT_CODE          # dipatok: tidak pernah masuk SKU
    words = [w for w in re.sub(r'[^a-z ]', ' ', str(name or '').lower()).split() if w]
    if not words:
        base = 'WRN'
    elif len(words) == 1:
        base = words[0][:3].upper()
    else:
        base = (words[0][0] + words[-1][:2]).upper()
    base = (re.sub(r'[^A-Z]', '', base) or 'WRN')[:3]
    if base not in taken:
        return base
    for i in range(2, 100):
        cand = f'{base[:2]}{i}'
        if cand not in taken:
            return cand
    return f'W{uuid.uuid4().hex[:2].upper()}'


def product_key(product_name) -> str:
    """Kunci stabil & pendek untuk satu judul produk (aman dipakai di URL)."""
    return 'pk_' + hashlib.md5(norm(product_name).encode('utf-8')).hexdigest()[:10]


# ══════════════════════════════════════════════════════════════════════════════
# Penyiapan master (idempoten)
# ══════════════════════════════════════════════════════════════════════════════
async def ensure_option_master(db, *, user: dict = None) -> dict:
    """Semai 4 opsi bawaan. Idempoten."""
    created = 0
    for i, seed in enumerate(OPTION_SEED):
        existing = await db[OPTIONS].find_one({'code': seed['code']}, {'_id': 0})
        if existing:
            continue
        await db[OPTIONS].insert_one({
            'id': _uid(), 'code': seed['code'], 'name': seed['name'],
            'order_seq': seed.get('order_seq', i), 'active': True,
            'notes': seed.get('notes', ''),
            'is_default': seed['code'] == OPTION_NA,
            'created_at': _now(), 'updated_at': _now(),
            'created_by': (user or {}).get('id', 'system'),
        })
        created += 1
    return {'ok': True, 'created': created,
            'total': await db[OPTIONS].count_documents({})}


async def get_option(db, code: str) -> dict:
    code = str(code or OPTION_NA).strip().upper() or OPTION_NA
    doc = await db[OPTIONS].find_one({'code': code}, {'_id': 0})
    if not doc:
        await ensure_option_master(db)
        doc = await db[OPTIONS].find_one({'code': code}, {'_id': 0})
    return doc or {'code': code, 'name': OPTION_NAMES.get(code, code), 'id': None}


async def ensure_size_master(db) -> dict:
    """Semai ukuran tambahan (BESAR/KECIL/XXXL). Idempoten."""
    created = 0
    for seed in SIZE_SEED_EXTRA:
        if await db[SIZES].find_one({'code': seed['code']}, {'_id': 0, 'id': 1}):
            continue
        await db[SIZES].insert_one({
            'id': _uid(), 'code': seed['code'], 'name': seed['name'],
            'order_seq': seed.get('order_seq', 99), 'active': True,
            'created_at': _now(), 'updated_at': _now(),
            'created_via': CREATED_VIA,
        })
        created += 1
    return {'ok': True, 'created': created}


async def ensure_category_master(db) -> dict:
    """Semai kategori tambahan (Aksesoris, keputusan 5a). Idempoten."""
    created = 0
    for seed in CATEGORY_SEED_EXTRA:
        coll = db.rahaza_product_categories
        if await coll.find_one({'code': seed['code']}, {'_id': 0, 'id': 1}):
            continue
        await coll.insert_one({
            'id': _uid(), 'code': seed['code'], 'name': seed['name'],
            'sku_prefix': seed['sku_prefix'], 'description': seed.get('description', ''),
            'active': True, 'order_seq': 90,
            'created_at': _now(), 'updated_at': _now(),
            'created_via': CREATED_VIA,
        })
        created += 1
    return {'ok': True, 'created': created}


async def ensure_variant_option_index(db) -> dict:
    """Perluas index unik varian ke **4 sumbu** (model·warna·ukuran·opsi).

    Wajib: index lama ``model_size_color_variant_unique`` (3 sumbu) akan
    MENOLAK varian 'PAKAI KARET' vs 'TANPA KARET' yang model/warna/ukurannya
    sama — dimensi ketiga mustahil hidup tanpa langkah ini. Varian lama
    dibekali ``option_code='NA'`` lebih dulu supaya index konsisten dan SKU-nya
    tetap sama.
    """
    backfilled = await db[VARIANTS].update_many(
        {'option_code': {'$in': [None, '']}},
        {'$set': {'option_code': OPTION_NA, 'option_id': None,
                  'option_name': OPTION_NAMES[OPTION_NA]}})
    missing = await db[VARIANTS].update_many(
        {'option_code': {'$exists': False}},
        {'$set': {'option_code': OPTION_NA, 'option_id': None,
                  'option_name': OPTION_NAMES[OPTION_NA]}})
    dropped = False
    info = await db[VARIANTS].index_information()
    if 'model_size_color_variant_unique' in info:
        await db[VARIANTS].drop_index('model_size_color_variant_unique')
        dropped = True
    if 'model_size_color_option_unique' not in (await db[VARIANTS].index_information()):
        await db[VARIANTS].create_index(
            [('model_id', 1), ('size_id', 1), ('color_id', 1), ('option_code', 1)],
            unique=True, name='model_size_color_option_unique',
            partialFilterExpression={'active': True})
    return {'ok': True, 'legacy_index_dropped': dropped,
            'variants_backfilled': int(backfilled.modified_count or 0) + int(missing.modified_count or 0)}


async def ensure_all_masters(db, *, user: dict = None) -> dict:
    """Satu pintu penyiapan: opsi + ukuran + kategori + index. Idempoten."""
    return {
        'options': await ensure_option_master(db, user=user),
        'sizes': await ensure_size_master(db),
        'categories': await ensure_category_master(db),
        'index': await ensure_variant_option_index(db),
    }


async def resolve_color_strict(db, name: str, *, create: bool = False,
                               taken: set = None, user: dict = None) -> dict:
    """Ambil warna master **dengan nama yang persis** — atau buat baru.

    Berbeda dari ``sku_bridge._resolve_or_create_color``: berkas itu, saat nama
    tidak ditemukan, jatuh ke ``COLOR_ALIASES`` sehingga 'Butter Yellow' diam-
    diam menjadi 'Kuning'. Di sini nuansa TIDAK pernah digabung; kalau warnanya
    belum ada, ia lahir sebagai warna master baru (dan pemilik sudah melihatnya
    di pratinjau).
    """
    nm = str(name or '').strip()
    if not nm:
        return {}
    doc = await db[COLORS].find_one(
        {'name': {'$regex': f'^{re.escape(nm)}$', '$options': 'i'},
         'active': {'$ne': False}}, {'_id': 0})
    if doc:
        return doc
    if not create:
        return {}
    if taken is None:
        taken = {c['code'] for c in await db[COLORS].find({}, {'_id': 0, 'code': 1}).to_list(500)
                 if c.get('code')}
    code = propose_color_code(nm, taken)
    doc = {'id': _uid(), 'code': code, 'name': _title(nm), 'hex': '',
           'active': True, 'created_at': _now(), 'updated_at': _now(),
           'created_via': CREATED_VIA,
           'created_by': (user or {}).get('id', 'system'),
           'notes': 'Warna nyata dari variasi SKU platform (Onboarding Produk).'}
    await db[COLORS].insert_one(doc)
    doc.pop('_id', None)
    taken.add(code)
    return doc


async def resolve_size_strict(db, code: str) -> dict:
    """Ambil ukuran master. Tidak pernah membuat ukuran dari teks bebas —
    kosakata ukuran adalah keputusan master (BESAR/KECIL disemai eksplisit)."""
    c = str(code or SIZE_ABSENT).strip().upper() or SIZE_ABSENT
    doc = await db[SIZES].find_one({'code': c}, {'_id': 0})
    if doc:
        return doc
    await ensure_size_master(db)
    doc = await db[SIZES].find_one({'code': c}, {'_id': 0})
    if doc:
        return doc
    return await db[SIZES].find_one({'code': SIZE_ABSENT}, {'_id': 0}) or {}


async def peek_model_code(db, cat: dict) -> str:
    """Pratinjau kode model TANPA menaikkan counter (dry-run wajib tidak menulis).

    Counter memakai ``_id`` sebagai kunci (lihat ``utils.counters``), jadi
    membacanya cukup satu ``find_one`` — memanggil ``next_model_code`` di
    pratinjau akan MENULIS (menaikkan seq) dan itu melanggar aturan keras #5.
    """
    from utils.counters import peek_counter

    prefix = ((cat or {}).get('sku_prefix') or 'OTH').strip().upper() or 'OTH'
    cur = await peek_counter(db, f'model_code_{prefix}')
    return f'{prefix}-{str(int(cur or 0) + 1).zfill(4)}'


# ══════════════════════════════════════════════════════════════════════════════
# ONBOARDING PRODUK — dari SKU platform ke master yang bisa dipakai gudang
# ══════════════════════════════════════════════════════════════════════════════
async def _collect_rows(db, *, pkey: str = None, account_id: str = None,
                        include_mapped: bool = True) -> list:
    """Kumpulkan baris pesanan per ``platform_sku_id`` untuk satu judul produk.

    Berbeda dari ``sku_bridge.list_unmapped`` yang HANYA melihat baris belum
    tertaut: di sini yang sudah tertaut ikut dibawa (``include_mapped``) supaya
    rencana onboarding tetap bermakna & idempoten setelah dijalankan — kalau
    tidak, memanggil rencana kedua kali akan mengembalikan daftar kosong dan
    kita tidak bisa membuktikan "apply kedua tidak menggandakan apa pun".
    """
    q = {}
    if account_id:
        q['account_id'] = account_id
    groups: dict = {}
    async for o in db[ORDERS].find(q, {'_id': 0, 'items': 1, 'account_id': 1,
                                       'account_name': 1, 'order_date': 1,
                                       'purchase_channel': 1, 'order_id': 1}):
        for ln in (o.get('items') or []):
            if not isinstance(ln, dict):
                continue
            psid = str(ln.get('platform_sku_id') or '').strip()
            if not psid:
                continue
            pname = ln.get('product_name_raw') or ln.get('product_name') or ''
            if pkey and product_key(pname) != pkey:
                continue
            mapped = bool(ln.get('fg_material_id'))
            if mapped and not include_mapped:
                continue
            g = groups.setdefault(psid, {
                'platform_sku_id': psid, 'product_name': pname,
                'variation': ln.get('variation_raw') or '',
                'account_id': o.get('account_id'),
                'account_name': o.get('account_name') or '',
                'platform': o.get('purchase_channel') or '',
                'pcs': 0.0, 'lines': 0, 'value': 0.0, 'mapped_lines': 0,
            })
            g['pcs'] += _f(ln.get('quantity') or ln.get('qty'))
            g['lines'] += 1
            g['mapped_lines'] += 1 if mapped else 0
            g['value'] += _f(ln.get('sku_subtotal_after_discount') or ln.get('subtotal'))
    rows = list(groups.values())
    for r in rows:
        r['pcs'] = round(r['pcs'], 2)
        r['value'] = round(r['value'], 2)
        r['mapped'] = r['mapped_lines'] >= r['lines'] and r['lines'] > 0
    rows.sort(key=lambda r: -r['pcs'])
    return rows


async def list_product_groups(db, *, account_id: str = None, limit: int = 800,
                              only_unmapped: bool = True) -> dict:
    """Kelompokkan SKU platform **per PRODUK** — pintu masuk layar onboarding.

    Kenapa per produk dan bukan per SKU: pada data hidup ada **83 SKU** tetapi
    hanya **8 produk**. Menyuruh pemilik menyelesaikan 83 baris satu per satu
    adalah cara paling pasti membuat fitur ini tidak dipakai; per produk, ia
    mengambil 8 keputusan.
    """
    from core import sku_bridge as sb

    un = await sb.list_unmapped(db, account_id=account_id, limit=max(50, int(limit or 800)))
    rows = un['rows'] if only_unmapped else await _collect_rows(db, account_id=account_id)

    groups: dict = {}
    for r in rows:
        pname = r.get('product_name') or ''
        pk = product_key(pname)
        g = groups.setdefault(pk, {
            'product_key': pk, 'product_name': pname,
            'account_id': r.get('account_id'), 'account_name': r.get('account_name') or '',
            'platform': r.get('platform') or '',
            'sku_count': 0, 'pcs': 0.0, 'value': 0.0, 'order_lines': 0,
            'colors': set(), 'sizes': set(), 'options': set(),
            'identities': set(), 'unreadable': [], 'variations': [],
        })
        ident = parse_identity(r.get('variation'), product_name=pname,
                               shop_name=r.get('account_name'))
        g['sku_count'] += 1
        g['pcs'] += _f(r.get('pcs'))
        g['value'] += _f(r.get('value'))
        g['order_lines'] += int(r.get('orders') or r.get('lines') or 0)
        g['colors'].add(ident['color_name'])
        g['sizes'].add(ident['size_code'])
        g['options'].add(ident['option_code'])
        g['identities'].add(ident['identity_key'])
        g['variations'].append(r.get('variation') or '')
        g['unreadable'].extend(ident['unreadable'])

    out = []
    for g in groups.values():
        model_name = propose_model_name(g['product_name'], shop_name=g['account_name'])
        cat_code = propose_category_code(g['product_name'])
        cat = await db.rahaza_product_categories.find_one({'code': cat_code},
                                                          {'_id': 0, 'name': 1, 'code': 1}) or {}
        existing = await db[MODELS].find_one(
            {'name': {'$regex': f'^{re.escape(model_name)}$', '$options': 'i'}},
            {'_id': 0, 'id': 1, 'code': 1})
        distinct_variations = len({norm(v) for v in g['variations']})
        out.append({
            'product_key': g['product_key'], 'product_name': g['product_name'],
            'account_id': g['account_id'], 'account_name': g['account_name'],
            'platform': g['platform'],
            'sku_count': g['sku_count'], 'pcs': round(g['pcs'], 2),
            'value': round(g['value'], 2), 'order_lines': g['order_lines'],
            'proposed_model_name': model_name,
            'proposed_category_code': cat_code,
            'proposed_category_name': cat.get('name') or cat_code,
            'model_exists': bool(existing),
            'model_id': (existing or {}).get('id'),
            'model_code': (existing or {}).get('code'),
            'identity_count': len(g['identities']),
            'distinct_variations': distinct_variations,
            'collisions': max(0, distinct_variations - len(g['identities'])),
            'colors': sorted(g['colors']), 'sizes': sorted(g['sizes']),
            'options': sorted(g['options']),
            'unreadable': sorted(set(g['unreadable']))[:10],
        })
    out.sort(key=lambda p: -p['pcs'])
    return {'ok': True, 'products': out, 'total_products': len(out),
            'total_skus': sum(p['sku_count'] for p in out),
            'pcs_total': round(sum(p['pcs'] for p in out), 2),
            'value_total': round(sum(p['value'] for p in out), 2),
            'collisions_total': sum(p['collisions'] for p in out),
            'unreadable_total': sum(len(p['unreadable']) for p in out)}


async def _compute_plan(db, *, pkey: str, model_name: str = None,
                        category_code: str = None, account_id: str = None,
                        model_id: str = None) -> dict:
    """Hitung rencana onboarding satu produk. **Tidak menulis apa pun.**

    ``model_id`` (opsional) = pemilik MENUNJUK model master yang sudah ada dari
    pemilih (bukan mengetik namanya). Ini yang dipakai layar: mengetik nama
    model adalah cara paling pasti melahirkan model kembar — cacat yang dijaga
    gate INV-F14. Bila ``model_id`` kosong, nama DITURUNKAN dari judul platform
    dan hanya DITAMPILKAN.
    """
    rows = await _collect_rows(db, pkey=pkey, account_id=account_id)
    if not rows:
        return {'ok': False, 'status': 404,
                'message': 'Produk itu tidak ditemukan pada pesanan mana pun.'}

    pname = rows[0]['product_name']
    shop = rows[0].get('account_name') or ''
    acc = account_id or rows[0].get('account_id')
    if not acc:
        return {'ok': False, 'status': 400,
                'message': 'Toko (account_id) tidak diketahui untuk produk ini.'}

    mname = (model_name or '').strip() or propose_model_name(pname, shop_name=shop)
    ccode = (category_code or '').strip().upper() or propose_category_code(pname)
    cat = await db.rahaza_product_categories.find_one({'code': ccode}, {'_id': 0})
    cat_seed = next((c for c in CATEGORY_SEED_EXTRA if c['code'] == ccode), None)
    if not cat and cat_seed:
        cat = {**cat_seed, 'id': None}          # akan disemai saat apply
    if not cat:
        cat = await db.rahaza_product_categories.find_one({'code': 'LAINNYA'}, {'_id': 0}) or {}

    model = None
    if model_id:
        model = await db[MODELS].find_one({'id': model_id}, {'_id': 0})
        if not model:
            return {'ok': False, 'status': 404,
                    'message': f"Model '{model_id}' tidak ada di master."}
        mname = model.get('name') or mname
    if model is None:
        model = await db[MODELS].find_one(
            {'name': {'$regex': f'^{re.escape(mname)}$', '$options': 'i'}}, {'_id': 0})
    model_code = (model or {}).get('code') or await peek_model_code(db, cat)

    # ── Kelompokkan SKU per IDENTITAS (warna · ukuran · opsi) ─────────────────
    idents: dict = {}
    warnings: list = []
    for r in rows:
        ident = parse_identity(r.get('variation'), product_name=pname, shop_name=shop)
        if ident['unreadable']:
            warnings.append({'platform_sku_id': r['platform_sku_id'],
                             'variation': r.get('variation'),
                             'unreadable': ident['unreadable']})
        e = idents.setdefault(ident['identity_key'], {
            'color_name': ident['color_name'], 'size_code': ident['size_code'],
            'option_code': ident['option_code'], 'option_name': ident['option_name'],
            'platform_sku_ids': [], 'variations': set(), 'pcs': 0.0,
            'order_lines': 0, 'mapped_skus': 0, 'spec': ident['spec'],
        })
        e['platform_sku_ids'].append(r['platform_sku_id'])
        e['variations'].add(r.get('variation') or '')
        e['pcs'] += _f(r.get('pcs'))
        e['order_lines'] += int(r.get('lines') or 0)
        e['mapped_skus'] += 1 if r.get('mapped') else 0

    # ── Master yang perlu lahir ──────────────────────────────────────────────
    taken_codes = {c['code'] for c in await db[COLORS].find(
        {}, {'_id': 0, 'code': 1}).to_list(500) if c.get('code')}
    colors_plan: dict = {}
    for e in idents.values():
        nm = e['color_name']
        if nm in colors_plan:
            continue
        doc = await resolve_color_strict(db, nm, create=False)
        if doc:
            colors_plan[nm] = {'name': doc.get('name'), 'code': doc.get('code'),
                               'id': doc.get('id'), 'exists': True}
        else:
            code = propose_color_code(nm, taken_codes)
            taken_codes.add(code)
            colors_plan[nm] = {'name': _title(nm), 'code': code, 'id': None,
                               'exists': False}

    sizes_plan: dict = {}
    for e in idents.values():
        sc = e['size_code']
        if sc in sizes_plan:
            continue
        doc = await db[SIZES].find_one({'code': sc}, {'_id': 0})
        sizes_plan[sc] = {'code': sc, 'id': (doc or {}).get('id'),
                          'name': (doc or {}).get('name') or sc,
                          'exists': bool(doc)}

    options_plan: dict = {}
    for e in idents.values():
        oc = e['option_code']
        if oc in options_plan:
            continue
        doc = await db[OPTIONS].find_one({'code': oc}, {'_id': 0})
        options_plan[oc] = {'code': oc, 'name': (doc or {}).get('name') or OPTION_NAMES.get(oc, oc),
                            'id': (doc or {}).get('id'), 'exists': bool(doc)}

    # ── Varian: mana yang sudah ada, mana yang akan lahir ─────────────────────
    variants = []
    for key, e in sorted(idents.items(), key=lambda kv: -kv[1]['pcs']):
        cinfo, sinfo = colors_plan[e['color_name']], sizes_plan[e['size_code']]
        sku = make_sku(model_code, cinfo['code'], sinfo['code'], e['option_code'])
        exists = False
        vid = None
        if model and cinfo.get('id') and sinfo.get('id'):
            v = await db[VARIANTS].find_one(
                {'model_id': model['id'], 'color_id': cinfo['id'],
                 'size_id': sinfo['id'], 'option_code': e['option_code']},
                {'_id': 0, 'id': 1, 'sku': 1})
            if not v:
                v = await db[VARIANTS].find_one({'sku': sku}, {'_id': 0, 'id': 1, 'sku': 1})
            exists, vid = bool(v), (v or {}).get('id')
        variants.append({
            'identity_key': key, 'color_name': cinfo['name'],
            'color_code': cinfo['code'], 'size_code': sinfo['code'],
            'option_code': e['option_code'], 'option_name': e['option_name'],
            'sku': sku, 'exists': exists, 'variant_id': vid,
            'platform_sku_ids': e['platform_sku_ids'],
            'sku_count': len(e['platform_sku_ids']),
            'variations': sorted(e['variations']),
            'pcs': round(e['pcs'], 2), 'order_lines': e['order_lines'],
            'mapped_skus': e['mapped_skus'], 'spec': e['spec'],
        })

    distinct_variations = len({norm(r.get('variation')) for r in rows})
    return {
        'ok': True,
        'product': {'product_key': pkey, 'product_name': pname,
                    'account_id': acc, 'account_name': shop,
                    'platform': rows[0].get('platform') or '',
                    'sku_count': len(rows),
                    'pcs': round(sum(_f(r.get('pcs')) for r in rows), 2),
                    'value': round(sum(_f(r.get('value')) for r in rows), 2),
                    'order_lines': sum(int(r.get('lines') or 0) for r in rows)},
        'model': {'exists': bool(model), 'id': (model or {}).get('id'),
                  'name': (model or {}).get('name') or mname, 'code': model_code,
                  'code_exact': bool(model),
                  'category_code': cat.get('code') or 'LAINNYA',
                  'category_name': cat.get('name') or 'Lainnya',
                  'category_exists': bool(cat.get('id'))},
        'colors': sorted(colors_plan.values(), key=lambda c: (c['exists'], c['name'])),
        'sizes': sorted(sizes_plan.values(), key=lambda s: s['code']),
        'options': sorted(options_plan.values(), key=lambda o: o['code']),
        'variants': variants,
        'totals': {
            'identities': len(idents),
            'distinct_variations': distinct_variations,
            'collisions': max(0, distinct_variations - len(idents)),
            'variants_new': sum(1 for v in variants if not v['exists']),
            'variants_existing': sum(1 for v in variants if v['exists']),
            'colors_new': sum(1 for c in colors_plan.values() if not c['exists']),
            'sizes_new': sum(1 for s in sizes_plan.values() if not s['exists']),
            'options_new': sum(1 for o in options_plan.values() if not o['exists']),
            'skus_to_map': sum(1 for r in rows if not r.get('mapped')),
            'skus_already_mapped': sum(1 for r in rows if r.get('mapped')),
            'order_lines_to_link': sum(int(r.get('lines') or 0)
                                       for r in rows if not r.get('mapped')),
        },
        'warnings': warnings,
        '_idents': idents, '_rows': rows, '_cat': cat, '_model_doc': model,
        '_colors_plan': colors_plan, '_sizes_plan': sizes_plan,
    }


def _public_plan(plan: dict) -> dict:
    """Buang bagian internal sebelum dikirim ke layar."""
    return {k: v for k, v in plan.items() if not k.startswith('_')}


async def plan_onboarding(db, *, product_key: str, model_name: str = None,
                          category_code: str = None, account_id: str = None,
                          model_id: str = None) -> dict:
    """PRATINJAU onboarding satu produk. Dijamin tidak menulis apa pun."""
    plan = await _compute_plan(db, pkey=product_key, model_name=model_name,
                               category_code=category_code, account_id=account_id,
                               model_id=model_id)
    if not plan.get('ok'):
        return plan
    t = plan['totals']
    out = _public_plan(plan)
    out['dry_run'] = True
    out['message'] = (
        f"PRATINJAU — model '{plan['model']['name']}' ({plan['model']['category_name']}) "
        f"{'sudah ada' if plan['model']['exists'] else 'akan dibuat'}; "
        f"{t['variants_new']} varian baru + {t['variants_existing']} sudah ada; "
        f"{t['colors_new']} warna & {t['sizes_new']} ukuran baru; "
        f"{t['skus_to_map']} SKU akan ditautkan "
        f"(± {t['order_lines_to_link']} baris pesanan). Belum ada yang ditulis.")
    return out


async def apply_onboarding(db, *, product_key: str, model_name: str = None,
                           category_code: str = None, account_id: str = None,
                           model_id: str = None, user: dict = None) -> dict:
    """TERAPKAN onboarding satu produk: model → warna/ukuran/opsi → varian →
    FG → item katalog → pemetaan SKU → tautan pesanan. **Idempoten.**"""
    from core import product_master as pm
    from core import sku_bridge as sb

    await ensure_all_masters(db, user=user)
    plan = await _compute_plan(db, pkey=product_key, model_name=model_name,
                               category_code=category_code, account_id=account_id,
                               model_id=model_id)
    if not plan.get('ok'):
        return plan

    acc = plan['product']['account_id']
    cat = plan['_cat']
    if not cat.get('id'):
        cat = await db.rahaza_product_categories.find_one(
            {'code': cat.get('code') or 'LAINNYA'}, {'_id': 0}) or cat

    created = {'model': 0, 'colors': 0, 'sizes': 0, 'variants': 0}

    # ── Model ────────────────────────────────────────────────────────────────
    model = plan['_model_doc']
    if not model:
        code = await pm.next_model_code(db, cat)
        model = {'id': _uid(), 'code': code, 'name': plan['model']['name'],
                 'description': f"Dibuat dari onboarding produk platform: {plan['product']['product_name'][:180]}",
                 'active': True, 'retail_price': 0.0, 'base_hpp': 0.0, 'hpp': 0.0,
                 'weight_gram': 0.0, 'created_at': _now(), 'updated_at': _now(),
                 'created_by': (user or {}).get('id', 'system'),
                 'created_via': CREATED_VIA,
                 'source_product_name': plan['product']['product_name'],
                 'source_account_id': acc}
        model = pm.apply_category(model, cat)
        await db[MODELS].insert_one(model)
        model.pop('_id', None)
        created['model'] = 1

    # ── Warna & ukuran ───────────────────────────────────────────────────────
    color_docs: dict = {}
    taken = {c['code'] for c in await db[COLORS].find({}, {'_id': 0, 'code': 1}).to_list(500)
             if c.get('code')}
    for nm in plan['_colors_plan']:
        before = await resolve_color_strict(db, nm, create=False)
        doc = before or await resolve_color_strict(db, nm, create=True, taken=taken, user=user)
        if not before and doc:
            created['colors'] += 1
        if not doc:
            return {'ok': False, 'status': 400,
                    'message': f"Warna '{nm}' gagal disiapkan di master."}
        color_docs[nm] = doc

    size_docs: dict = {}
    for sc in plan['_sizes_plan']:
        before = await db[SIZES].find_one({'code': sc}, {'_id': 0})
        doc = before or await resolve_size_strict(db, sc)
        if not before and doc:
            created['sizes'] += 1
        if not doc:
            return {'ok': False, 'status': 400,
                    'message': f"Ukuran '{sc}' tidak ada di master."}
        size_docs[sc] = doc

    # ── Varian + pemetaan SKU ────────────────────────────────────────────────
    results, failures = [], []
    skus_mapped = order_lines = 0
    for e in sorted(plan['_idents'].values(), key=lambda x: -x['pcs']):
        color, size = color_docs[e['color_name']], size_docs[e['size_code']]
        opt = await get_option(db, e['option_code'])
        sku = make_sku(model.get('code'), color.get('code'), size.get('code'), e['option_code'])

        variant = await db[VARIANTS].find_one(
            {'model_id': model['id'], 'color_id': color['id'], 'size_id': size['id'],
             'option_code': e['option_code']}, {'_id': 0})
        if not variant:
            variant = await db[VARIANTS].find_one({'sku': sku}, {'_id': 0})
        if not variant:
            variant = {
                'id': _uid(), 'model_id': model['id'], 'model_code': model.get('code'),
                'model_name': model.get('name'),
                'size_id': size['id'], 'size_code': size.get('code'),
                'color_id': color['id'], 'color_code': color.get('code'),
                'color_name': color.get('name'), 'color_hex': color.get('hex', ''),
                'option_id': opt.get('id'), 'option_code': e['option_code'],
                'option_name': opt.get('name') or e['option_name'],
                'sku': sku, 'barcode': '', 'active': True,
                'notes': ('Lahir dari onboarding SKU platform. Variasi asli: '
                          + ' / '.join(sorted(e['variations']))[:300]),
                'spec': e.get('spec') or {},
                'created_at': _now(), 'updated_at': _now(),
                'created_via': CREATED_VIA,
            }
            await db[VARIANTS].insert_one(variant)
            variant.pop('_id', None)
            created['variants'] += 1

        for psid in e['platform_sku_ids']:
            res = await sb.apply_mapping(
                db, psid, variant_id=variant['id'], account_id=acc, user=user,
                method='product_onboarding', confidence=1.0,
                product_name=plan['product']['product_name'],
                variation=sorted(e['variations'])[0] if e['variations'] else '')
            if not res.get('ok'):
                failures.append({'platform_sku_id': psid, 'sku': sku,
                                 'message': res.get('message')})
                continue
            skus_mapped += 1
            order_lines += int(res.get('orders_updated') or 0)
        results.append({'sku': sku, 'color_name': color.get('name'),
                        'size_code': size.get('code'), 'option_code': e['option_code'],
                        'option_name': opt.get('name'),
                        'variant_id': variant['id'],
                        'platform_sku_ids': e['platform_sku_ids'],
                        'pcs': round(e['pcs'], 2)})

    return {
        'ok': not failures, 'dry_run': False,
        'product': plan['product'],
        'model': {'id': model['id'], 'code': model.get('code'), 'name': model.get('name'),
                  'category_name': cat.get('name')},
        'created': created, 'variants': results,
        'skus_mapped': skus_mapped, 'order_lines_linked': order_lines,
        'failures': failures,
        'message': (f"{created['variants']} varian baru lahir "
                    f"({len(results)} identitas), {skus_mapped} SKU ditautkan, "
                    f"{order_lines} baris pesanan ikut tertaut"
                    + (f'; {len(failures)} GAGAL' if failures else '.')),
    }


async def rollback_onboarding(db, *, model_id: str, user: dict = None) -> dict:
    """Batalkan onboarding satu model — **hanya** dokumen yang lahir darinya.

    Dipakai uji POC supaya bisa dijalankan berulang di data nyata tanpa
    mencemari baseline. Penjaga: hanya menyentuh dokumen ber-``created_via ==
    'variant_onboarding'``; data bisnis lain tidak pernah tersentuh.
    """
    from core import sku_bridge as sb

    model = await db[MODELS].find_one({'id': model_id}, {'_id': 0})
    if not model:
        return {'ok': False, 'status': 404, 'message': 'Model tidak ditemukan.'}

    variants = await db[VARIANTS].find({'model_id': model_id, 'created_via': CREATED_VIA},
                                       {'_id': 0}).to_list(2000)
    vids = [v['id'] for v in variants]
    skus = [v.get('sku') for v in variants if v.get('sku')]

    unmapped = 0
    async for b in db[BRIDGE].find({'variant_id': {'$in': vids}}, {'_id': 0, 'platform_sku_id': 1}):
        r = await sb.remove_mapping(db, b['platform_sku_id'], user=user)
        unmapped += 1 if r.get('ok') else 0

    fgs = await db[MATERIALS].find({'variant_id': {'$in': vids}, 'type': 'fg'},
                                   {'_id': 0, 'id': 1}).to_list(2000)
    fg_ids = [f['id'] for f in fgs]
    items = await db[ITEMS].delete_many({'fg_material_id': {'$in': fg_ids}})
    mats = await db[MATERIALS].delete_many({'id': {'$in': fg_ids}})
    vres = await db[VARIANTS].delete_many({'id': {'$in': vids}})

    model_deleted = 0
    if model.get('created_via') == CREATED_VIA and \
            not await db[VARIANTS].count_documents({'model_id': model_id}):
        await db[MODELS].delete_one({'id': model_id})
        model_deleted = 1

    # Warna yang lahir dari onboarding & sudah tidak dipakai varian mana pun.
    colors_deleted = 0
    async for c in db[COLORS].find({'created_via': CREATED_VIA}, {'_id': 0, 'id': 1}):
        if not await db[VARIANTS].count_documents({'color_id': c['id']}):
            await db[COLORS].delete_one({'id': c['id']})
            colors_deleted += 1

    return {'ok': True, 'model_deleted': model_deleted, 'skus_unmapped': unmapped,
            'variants_deleted': int(vres.deleted_count or 0),
            'fg_deleted': int(mats.deleted_count or 0),
            'catalog_items_deleted': int(items.deleted_count or 0),
            'colors_deleted': colors_deleted, 'skus': skus,
            'message': (f"Onboarding model '{model.get('name')}' dibatalkan: "
                        f"{vres.deleted_count} varian, {mats.deleted_count} FG, "
                        f"{items.deleted_count} item katalog dihapus; "
                        f"{unmapped} SKU dilepas.")}


# ══════════════════════════════════════════════════════════════════════════════
# PERAPIAN PALET WARNA (keputusan 6a) — pratinjau dulu, tidak pernah menebak
# ══════════════════════════════════════════════════════════════════════════════
def color_group_key(name) -> str:
    """Nama warna → kelompok kanonik.

    Menyatukan 'Abu' & 'Abu-abu' (nama beda, warna sama) DAN 'Putih' (PTH) &
    'Putih' (WHT) (nama sama, kode beda). Nuansa tetap TIDAK digabung: 'Butter
    Yellow' bukan 'Kuning'.
    """
    n = norm(name)
    return COLOR_TRANSLATE.get(n) or COLOR_SPELLING.get(n) or _title(n)


async def _color_refs(db, color_id: str) -> dict:
    """Hitung SEMUA rujukan satu warna — dipakai memutuskan aman/tidak."""
    variants = await db[VARIANTS].find(
        {'color_id': color_id},
        {'_id': 0, 'id': 1, 'sku': 1, 'model_id': 1, 'model_code': 1,
         'size_id': 1, 'size_code': 1, 'option_code': 1}).to_list(2000)
    fgs = await db[MATERIALS].find({'color_id': color_id},
                                   {'_id': 0, 'id': 1, 'code': 1}).to_list(2000)
    fg_ids = [f['id'] for f in fgs]
    return {
        'variants': variants, 'fgs': fgs,
        'catalog_items': await db[ITEMS].count_documents({'fg_material_id': {'$in': fg_ids}}),
        'stock_rows': await db.rahaza_material_stock.count_documents({'material_id': {'$in': fg_ids}}),
        'ledger_rows': await db.rahaza_stock_ledger.count_documents({'material_id': {'$in': fg_ids}}),
        'order_lines': await db[ORDERS].count_documents({'items.fg_material_id': {'$in': fg_ids}}),
    }


async def merge_duplicate_colors(db, *, dry_run: bool = True, user: dict = None) -> dict:
    """Satukan warna master kembar. Pratinjau dulu; data bernilai tidak disentuh.

    Kenapa perlu: palet punya 5 pasang kembar (``Putih`` PTH+WHT · ``Hitam``
    HTM+BLK · ``Merah`` MRH+RED · ``Krem`` KRM+CRM · ``Abu``+``Abu-abu``), dan
    akibatnya **satu model punya dua varian "Putih"** (``DA-TS01-PTH-S`` dan
    ``DA-TS01-WHT-S``). Pencocokan warna berdasarkan nama jadi mendua: mesin
    bisa memilih kode mana saja.

    Aturan aman:
      * Kanonik = kode dengan rujukan TERBANYAK (seri berjurus stok/katalog
        menang). Seri tanpa rujukan yang kalah dianggap kembaran.
      * Varian kembaran yang **kanoniknya sudah ada** (model·ukuran·opsi sama)
        DIHAPUS — tetapi HANYA bila tidak punya item katalog / baris stok /
        kartu stok / baris pesanan.
      * Varian kembaran yang **belum punya kanonik** DIALIHKAN (warna, kode,
        SKU, dan kode FG ditulis ulang) — ini satu-satunya jalan agar warnanya
        tidak hilang.
      * Apa pun yang punya stok/kartu/pesanan **TIDAK disentuh**; ia dilaporkan
        sebagai butuh keputusan pemilik. Membereskan diam-diam = mengubah uang.
    """
    cs = await db[COLORS].find({'active': {'$ne': False}}, {'_id': 0}).to_list(500)
    groups: dict = defaultdict(list)
    for c in cs:
        groups[color_group_key(c.get('name'))].append(c)

    plan, blocked = [], []
    deleted_variants = repointed_variants = retired_colors = 0

    for gname, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        scored = []
        for c in members:
            refs = await _color_refs(db, c['id'])
            weight = (refs['stock_rows'] * 1000 + refs['ledger_rows'] * 1000
                      + refs['order_lines'] * 1000 + refs['catalog_items'] * 100
                      + len(refs['variants']))
            scored.append((weight, c, refs))
        scored.sort(key=lambda x: -x[0])
        _, canon, canon_refs = scored[0]

        entry = {'group': gname,
                 'canonical': {'code': canon.get('code'), 'name': canon.get('name'),
                               'variants': len(canon_refs['variants']),
                               'catalog_items': canon_refs['catalog_items'],
                               'stock_rows': canon_refs['stock_rows']},
                 'duplicates': []}

        for _, dup, refs in scored[1:]:
            if refs['stock_rows'] or refs['ledger_rows'] or refs['order_lines']:
                blocked.append({'group': gname, 'code': dup.get('code'),
                                'reason': ('punya stok/kartu stok/baris pesanan — '
                                           'menyatukannya mengubah angka, perlu keputusan pemilik'),
                                'stock_rows': refs['stock_rows'],
                                'ledger_rows': refs['ledger_rows'],
                                'order_lines': refs['order_lines']})
                continue

            twins, moves = [], []
            for v in refs['variants']:
                canon_twin = await db[VARIANTS].find_one(
                    {'model_id': v.get('model_id'), 'size_id': v.get('size_id'),
                     'color_id': canon['id'],
                     'option_code': v.get('option_code') or OPTION_NA},
                    {'_id': 0, 'id': 1, 'sku': 1})
                if canon_twin:
                    twins.append({'sku': v.get('sku'), 'twin_sku': canon_twin.get('sku')})
                else:
                    moves.append({'sku': v.get('sku'),
                                  'new_sku': make_sku(v.get('model_code'), canon.get('code'),
                                                      v.get('size_code'),
                                                      v.get('option_code') or OPTION_NA)})

            entry['duplicates'].append({
                'code': dup.get('code'), 'name': dup.get('name'),
                'variants': len(refs['variants']),
                'to_delete': len(twins), 'to_repoint': len(moves),
                'delete_examples': twins[:5], 'repoint_examples': moves[:5],
                'catalog_items': refs['catalog_items'],
            })

            if dry_run:
                continue

            for v in refs['variants']:
                canon_twin = await db[VARIANTS].find_one(
                    {'model_id': v.get('model_id'), 'size_id': v.get('size_id'),
                     'color_id': canon['id'],
                     'option_code': v.get('option_code') or OPTION_NA},
                    {'_id': 0, 'id': 1})
                fg = await db[MATERIALS].find_one({'variant_id': v['id'], 'type': 'fg'},
                                                  {'_id': 0, 'id': 1})
                if canon_twin:
                    if fg:
                        await db[MATERIALS].delete_one({'id': fg['id']})
                    await db[VARIANTS].delete_one({'id': v['id']})
                    deleted_variants += 1
                else:
                    new_sku = make_sku(v.get('model_code'), canon.get('code'),
                                       v.get('size_code'), v.get('option_code') or OPTION_NA)
                    await db[VARIANTS].update_one({'id': v['id']}, {'$set': {
                        'color_id': canon['id'], 'color_code': canon.get('code'),
                        'color_name': canon.get('name'), 'color_hex': canon.get('hex', ''),
                        'sku': new_sku, 'updated_at': _now(),
                        'merged_from_color_code': dup.get('code')}})
                    if fg:
                        await db[MATERIALS].update_one({'id': fg['id']}, {'$set': {
                            'code': new_sku, 'sku': new_sku,
                            'color_id': canon['id'], 'color_code': canon.get('code'),
                            'color': canon.get('name'), 'color_name': canon.get('name'),
                            'updated_at': _now()}})
                    repointed_variants += 1

            await db[COLORS].update_one({'id': dup['id']}, {'$set': {
                'active': False, 'alias_of_color_id': canon['id'],
                'alias_of_code': canon.get('code'),
                'retired_at': _now(),
                'retired_by': (user or {}).get('id', 'system'),
                'notes': (f"Kembaran '{canon.get('name')}' ({canon.get('code')}) — "
                          'dinonaktifkan agar pemetaan warna tidak mendua (keputusan 6a).')}})
            retired_colors += 1

        if entry['duplicates'] or any(b['group'] == gname for b in blocked):
            plan.append(entry)

    return {'ok': True, 'dry_run': dry_run, 'groups': plan, 'blocked': blocked,
            'groups_affected': len(plan),
            'variants_deleted': deleted_variants,
            'variants_repointed': repointed_variants,
            'colors_retired': retired_colors,
            'message': (('PRATINJAU — ' if dry_run else '')
                        + f'{len(plan)} kelompok warna kembar; '
                        + (f'{sum(d["to_delete"] for e in plan for d in e["duplicates"])} varian kembar dihapus, '
                           f'{sum(d["to_repoint"] for e in plan for d in e["duplicates"])} dialihkan'
                           if dry_run else
                           f'{deleted_variants} varian dihapus, {repointed_variants} dialihkan, '
                           f'{retired_colors} warna dinonaktifkan')
                        + (f'; {len(blocked)} DILEWATI karena punya stok/pesanan' if blocked else ''))}
