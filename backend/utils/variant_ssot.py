"""
Canonical SSOT for internal product VARIANT identity & Finished-Goods (FG) materialization.

Single source of truth (user decision 2026-07-22):
  - Variant SSOT   : rahaza_model_variants   (model x color x size)
  - Canonical SKU  : {MODEL_CODE}-{COLOR_CODE}-{SIZE_CODE}  (UPPERCASE, NO "FG-" prefix)
  - FG identity    : rahaza_materials (type='fg') with code == variant.sku
  - Physical stock : rahaza_material_stock (per material_id per location)
  - "All Size"     : size code 'ALLSIZE'. COLOR is ALWAYS required (3-part SKU).

This module is the ONLY place allowed to build internal variant SKUs and to create/link
FG materials, so production / warehouse / marketing never diverge on SKU convention.

Kept dependency-light (only db passed in) to avoid circular imports. The WMS pending-inbound
helper is imported lazily inside the function that needs it.
"""
import re
import uuid
from datetime import datetime, timezone


def _u(s) -> str:
    return str(s or "").strip().upper()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def build_variant_sku(model_code, color_code, size_code, option_code=None) -> str:
    """Canonical SKU = {MODEL}-{COLOR}-{SIZE}[-{OPTION}] (uppercase, non-empty parts joined by '-').

    2026-08-19 (Sesi #28) — dimensi ke-3 "Opsi" ditambahkan secara ADITIF.
    Kode yang menyatakan ketidakhadiran (``NA`` = opsi tidak disebut, ``TDI`` =
    produk tanpa warna) DILEWATI, sehingga SKU varian lama tidak berubah
    sedikit pun dan pemanggil lama (3 argumen) tetap benar.
    """
    absent = {"NA", "TDI"}
    parts = [_u(model_code), _u(color_code), _u(size_code), _u(option_code)]
    return "-".join(p for p in parts if p and p not in absent)


def variant_sku(variant: dict) -> str:
    """Resolve the canonical SKU for a rahaza_model_variants doc (prefer stored sku)."""
    sku = _u(variant.get("sku"))
    if sku:
        return sku
    return build_variant_sku(
        variant.get("model_code"), variant.get("color_code"), variant.get("size_code"),
        variant.get("option_code"),
    )


def fg_display_name(variant: dict, model: dict = None) -> str:
    model = model or {}
    model_name = variant.get("model_name") or model.get("name") or variant.get("model_code") or ""
    color_name = variant.get("color_name") or variant.get("color") or ""
    size_code = variant.get("size_code") or ""
    # Opsi ikut ditampilkan: tanpa ini 'Pakai Karet' dan 'Tanpa Karet' punya kode
    # FG berbeda tetapi NAMA yang sama persis — picker gudang jadi menebak.
    option_name = variant.get("option_name") or ""
    if str(variant.get("option_code") or "").upper() in ("", "NA"):
        option_name = ""
    extra = " · ".join([x for x in [color_name, size_code, option_name] if x])
    return f"{model_name} [{extra}]" if extra else model_name


def _variant_linkage(variant: dict, model: dict = None) -> dict:
    """Explicit linkage fields carried onto the FG material so downstream consumers
    (FG matrix, marketing, reports) never rely on fragile code-string parsing.

    2026-08-10 (F3/F5) — kategori & angka master tidak lagi ditulis ad-hoc di sini.
    `core.product_master.master_display_fields()` adalah SATU-satunya sumber:
      * `category_id`/`category_code`/`category_name` (+ `category` legacy) — P2a
      * `weight_gram` — P4b (dulu DIBACA tetapi tidak pernah ditulis ⇒ berat FG 0)
      * `hpp` + `hpp_source` — P1b (urutan `model.hpp` R&D → `base_hpp` manual → 0)
    """
    from core import product_master as pm

    model = model or {}
    color_display = variant.get("color_name") or variant.get("color") or ""
    master = pm.master_display_fields(model)
    master.pop("retail_price_master", None)  # harga jual bukan atribut barang fisik
    return {
        "model_id": variant.get("model_id"),
        "model_code": variant.get("model_code") or model.get("code"),
        "model_name": variant.get("model_name") or model.get("name"),
        "size_id": variant.get("size_id"),
        "size_code": variant.get("size_code"),
        "color_id": variant.get("color_id"),
        "color_code": variant.get("color_code"),
        # `color` is the axis/label field read by fg-matrix & marketing → use human name
        "color": color_display,
        "color_name": color_display,
        "color_hex": variant.get("color_hex"),
        # Sesi #28 — dimensi ke-3 dibawa ke FG supaya konsumen hilir (matriks FG,
        # picklist gudang, katalog) bisa MEMBEDAKAN 'Pakai Karet' vs 'Tanpa Karet'
        # tanpa mengurai string SKU.
        "option_id": variant.get("option_id"),
        "option_code": variant.get("option_code") or "NA",
        "option_name": variant.get("option_name") or "Tidak Disebut",
        "variant_id": variant.get("id"),
        **master,
    }


async def ensure_fg_material(db, variant: dict, user: dict = None) -> dict:
    """Idempotently create (or link) the FG rahaza_materials doc whose code == variant.sku.

    - If an FG already exists with the same code (case-insensitive), backfill any MISSING
      linkage fields (never overwrite an existing non-null value) and return it.
    - Otherwise create a new FG (type='fg', unit='pcs', active=True, stock stays 0 until receipt).

    Returns the FG material document.
    """
    sku = variant_sku(variant)
    if not sku:
        raise ValueError("Varian tidak punya SKU yang bisa diresolusi (model/warna/size kosong).")

    model = None
    if variant.get("model_id"):
        model = await db.rahaza_models.find_one({"id": variant["model_id"]}, {"_id": 0})

    linkage = _variant_linkage(variant, model)

    existing = await db.rahaza_materials.find_one(
        {"type": "fg", "code": {"$regex": f"^{re.escape(sku)}$", "$options": "i"}},
        {"_id": 0},
    )
    if existing:
        # Field TAUTAN: hanya diisi bila masih kosong (jangan menimpa keputusan lama).
        patch = {k: v for k, v in linkage.items()
                 if v not in (None, "") and not existing.get(k)}
        # Field MILIK MASTER (kategori/berat/HPP): SELALU disegarkan — inilah P2b.
        # Salinan tanpa penyegar = laporan yang berbohong dengan sopan.
        for k in ("category_id", "category_code", "category_name", "category",
                  "weight_gram", "hpp", "hpp_source"):
            if k in linkage and existing.get(k) != linkage[k]:
                patch[k] = linkage[k]
        # Always ensure the canonical `sku` alias is present for by-sku resolvers.
        if not existing.get("sku"):
            patch["sku"] = sku
        if patch:
            patch["updated_at"] = now_utc()
            await db.rahaza_materials.update_one({"id": existing["id"]}, {"$set": patch})
            existing = {**existing, **patch}
        return existing

    doc = {
        "id": str(uuid.uuid4()),
        "code": sku,
        "sku": sku,
        "name": fg_display_name(variant, model),
        "type": "fg",
        "unit": "pcs",
        "active": True,
        "min_stock_qty": 0,
        "weight_gram": float((model or {}).get("weight_gram") or 0),
        "notes": "Auto-created from master variant (SSOT)",
        "created_at": now_utc(),
        "updated_at": now_utc(),
        **linkage,
    }
    await db.rahaza_materials.insert_one(doc)
    return doc


async def create_fg_pending_inbound_for_variant(
    db,
    variant: dict,
    qty,
    *,
    source_type: str,
    source_id: str,
    source_ref: str = "",
    user: dict = None,
    notes: str = "",
) -> dict:
    """Canonical physical FG receipt for internal production.

    1) Ensure the FG master exists (code == variant.sku).
    2) Create a WMS PENDING INBOUND (warehouse scan-in adds the physical stock) —
       keeps warehouse control while making the identity per-variant (color+size).

    Returns { fg, pending }.
    """
    qty = float(qty or 0)
    fg = await ensure_fg_material(db, variant, user=user)
    if qty <= 0:
        return {"fg": fg, "pending": None}

    from routes.wms_receiving import helper_create_pending_inbound_fg

    created_by = (user or {}).get("name") or (user or {}).get("email") or "production"
    pending = await helper_create_pending_inbound_fg(
        db,
        material_id=fg["id"],
        material_code=fg["code"],
        material_name=fg["name"],
        qty=qty,
        unit="pcs",
        source_type=source_type,
        source_id=source_id or "",
        source_ref=source_ref or "",
        notes=notes or f"Output produksi {qty:g} pcs — scan-in gudang diperlukan",
        created_by=created_by,
    )
    return {"fg": fg, "pending": pending}


async def resolve_variant(db, *, variant_id=None, sku=None,
                          model_id=None, color_id=None, size_id=None) -> dict:
    """Resolve a rahaza_model_variants doc by (priority) id → sku → (model,color,size)."""
    if variant_id:
        v = await db.rahaza_model_variants.find_one({"id": variant_id}, {"_id": 0})
        if v:
            return v
    if sku:
        v = await db.rahaza_model_variants.find_one(
            {"sku": {"$regex": f"^{re.escape(_u(sku))}$", "$options": "i"}}, {"_id": 0}
        )
        if v:
            return v
    if model_id and color_id and size_id:
        v = await db.rahaza_model_variants.find_one(
            {"model_id": model_id, "color_id": color_id, "size_id": size_id}, {"_id": 0}
        )
        if v:
            return v
    return None


# ══════════════════════ Master colors / sizes (idempotent get-or-create) ═══════
async def _seed_color_palette_if_empty(db):
    """Lazy-seed palet warna standar SEBELUM get-or-create apa pun.

    JEBAKAN NYATA (ditemukan 2026-08-08, gate INV-RND-4 MERAH di DB hasil bootstrap
    bersih): `rahaza_colors` di-seed *lazy* hanya oleh `GET /api/rahaza/colors` dan
    `GET /api/dewi/rnd/color-options`, dan HANYA bila koleksinya masih KOSONG.
    Siapa pun yang memanggil `ensure_color()` lebih dulu (importir Excel, promosi
    varian R&D → master, skrip gate) akan MEMBUAT warna sampah lebih dulu —
    mis. `ensure_color(code='NVY')` → `{code:'NVY', name:'NVY', hex:'#CCCCCC'}`.

    Akibatnya dua hal yang mahal:
      1. Koleksi jadi tidak-kosong ⇒ palet 15 warna asli TIDAK PERNAH ter-seed,
         sehingga dropdown warna R&D hanya berisi warna sampah abu-abu.
      2. Warna yang sama terpecah dua: `NVY`/'NVY' (sampah) **dan** `NAV`/'Navy'
         (dibuat belakangan lewat nama) ⇒ deteksi varian kembar lolos, SKU pecah.

    Karena itu penyemaian palet dilakukan di PINTU TERBAWAH (di sini), bukan hanya
    di endpoint daftar. Tetap idempoten & hanya saat KOSONG, jadi warna yang sengaja
    dihapus pengguna tidak pernah dihidupkan kembali.
    """
    if await db.rahaza_colors.count_documents({}) == 0:
        from routes.rahaza_variants import _ensure_colors
        await _ensure_colors(db)


async def ensure_color(db, *, name=None, code=None, hex_val=None) -> dict:
    """Idempotent get-or-create a rahaza_colors doc.

    Resolution order: explicit code → exact name → create with a UNIQUE code.
    Unique-code creation prevents different color names that derive the same base
    code (e.g. 'Polcadot hitam' & 'Polcadot putih' → 'POL') from collapsing into one.
    """
    name = (name or "").strip()
    explicit = (code or "").strip().upper().replace(" ", "")
    if name or explicit:
        # Palet standar harus ada DULU supaya 'NVY'/'Navy' menemukan warna asli
        # (#1E3A5F) dan bukan membuat warna sampah baru. Lihat docstring di atas.
        await _seed_color_palette_if_empty(db)
    # 1) explicit code match
    if explicit:
        ex = await db.rahaza_colors.find_one({"code": explicit}, {"_id": 0})
        if ex:
            return ex
    # 2) exact name match (case-insensitive)
    if name:
        byname = await db.rahaza_colors.find_one(
            {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}, {"_id": 0}
        )
        if byname:
            return byname
    if not name and not explicit:
        return None
    # 3) create with a unique code (append numeric suffix on collision)
    base = explicit or re.sub(r"[^A-Z0-9]", "", name.upper())[:3] or "CLR"
    final = base
    i = 1
    while await db.rahaza_colors.find_one({"code": final}):
        i += 1
        final = f"{base}{i}"[:10]
    doc = {
        "id": str(uuid.uuid4()), "code": final, "name": name or final,
        "hex": hex_val or "#CCCCCC", "order_seq": 50, "active": True,
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    await db.rahaza_colors.insert_one(doc)
    return doc


async def ensure_size(db, *, code=None, name=None, order_seq=50) -> dict:
    """Idempotent get-or-create a rahaza_sizes doc (match by code).

    2026-08-08 — KODE DIBERSIHKAN sebelum dipakai. Dulu `code` hanya
    `.strip().upper()`, sehingga label R&D bebas seperti `'All Size'` masuk
    sebagai kode master **`'ALL SIZE'`** (pakai spasi) walau `'ALLSIZE'` SUDAH ADA
    ⇒ master ukuran KEMBAR, dan `'28/30'` membuat kode master bergaris-miring yang
    lalu ikut masuk ke SKU FG (`STYLE-NVY-28/30`). Terbukti lewat
    `scripts/poc_rnd_size_promotion.py` (H2a/H2c). Kode master sekarang selalu
    alfanumerik; `name` tetap menyimpan tulisan aslinya.
    """
    code = norm_size_key(code)
    if not code:
        return None
    existing = await db.rahaza_sizes.find_one({"code": code}, {"_id": 0})
    if existing:
        return existing
    doc = {
        "id": str(uuid.uuid4()), "code": code, "name": name or code,
        "order_seq": order_seq, "active": True,
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    await db.rahaza_sizes.insert_one(doc)
    return doc


# ══════════════════ SSOT resolusi UKURAN bebas → master rahaza_sizes ══════════
# SATU pintu dipakai oleh DUA sisi yang harus selalu sepakat:
#   · layar (`build_size_map` → badge "belum dipadankan")
#   · promosi ke produksi (`promote_rnd_variants_to_master` → size_id untuk SKU/PO)
# Kalau keduanya punya logika sendiri, layar bisa bilang "sudah dipadankan"
# sementara promosi tetap membuat ukuran master baru — itulah bug yang terbukti
# di `scripts/poc_rnd_size_promotion.py` (H2a).

# Alias ukuran yang lazim dipakai di lapangan garmen Indonesia.
# Sengaja PENDEK dan eksplisit — bukan pencocokan "mirip-mirip" yang bisa salah
# menebak ukuran produksi (salah ukuran = salah potong kain = uang hilang).
SIZE_ALIAS_GROUPS = [
    {"2XL", "XXL"},
    {"3XL", "XXXL"},
    {"4XL", "XXXXL"},
    {"5XL", "XXXXXL"},
    {"ALLSIZE", "ALL", "FREESIZE", "FREE", "ONESIZE"},
    {"S", "SMALL"},
    {"M", "MEDIUM"},
    {"L", "LARGE"},
    {"XS", "EXTRASMALL"},
]


def norm_size_key(label) -> str:
    """Kunci pembanding ukuran: HURUF/ANGKA saja, UPPERCASE.

    `'All Size'`→`'ALLSIZE'`, `'28/30'`→`'2830'`, `'xl'`→`'XL'`.
    Dipakai juga sebagai KODE master supaya kode tidak pernah berisi spasi atau
    garis miring (yang akan bocor ke SKU).
    """
    return re.sub(r"[^A-Z0-9]", "", str(label or "").upper())


def size_alias_keys(label) -> set:
    """Semua kunci yang dianggap ukuran yang SAMA dengan `label` (termasuk dirinya)."""
    key = norm_size_key(label)
    if not key:
        return set()
    keys = {key}
    for group in SIZE_ALIAS_GROUPS:
        if key in group:
            keys |= group
    return keys


async def resolve_master_size(db, label, *, size_map=None, allow_create=False,
                              order_seq=50) -> dict:
    """Ukuran master (`rahaza_sizes`) untuk sebuah label ukuran R&D yang bebas.

    Urutan (dari yang paling bisa dipercaya):
      1. **Petunjuk `size_map`** milik style (kebijakan B1) — inilah keputusan
         manusia dari layar "Padankan Ukuran", jadi ia menang atas tebakan apa pun.
      2. Kode master sama (setelah dibersihkan) → `'All Size'` = `ALLSIZE`.
      3. Nama master sama (tanpa peduli besar-kecil).
      4. `aliases[]` master — diisi oleh layar "Padankan Ukuran" saat pengguna
         memadankan `'2XL'` ke master `XXL`.
      5. Alias baku lapangan (`SIZE_ALIAS_GROUPS`), mis. `2XL` ⇄ `XXL`.
      6. `allow_create` ⇒ buat ukuran baru dengan kode BERSIH (nama = tulisan asli).

    `allow_create=False` (dipakai layar) tidak pernah menulis apa pun.
    """
    key = norm_size_key(label)
    if not key:
        return None

    # 1) petunjuk hasil pemadanan manual (menang atas segalanya)
    for entry in (size_map or []):
        if not isinstance(entry, dict) or not entry.get("size_id"):
            continue
        if norm_size_key(entry.get("size")) != key:
            continue
        doc = await db.rahaza_sizes.find_one({"id": entry["size_id"]}, {"_id": 0})
        if doc:
            return doc

    # 2) kode master sama
    doc = await db.rahaza_sizes.find_one({"code": key}, {"_id": 0})
    if doc:
        return doc

    # 3) nama master sama (case-insensitive)
    raw = str(label or "").strip()
    if raw:
        doc = await db.rahaza_sizes.find_one(
            {"name": {"$regex": f"^{re.escape(raw)}$", "$options": "i"}}, {"_id": 0})
        if doc:
            return doc

    # 4 & 5) alias master + alias baku lapangan
    candidates = size_alias_keys(label)
    rows = await db.rahaza_sizes.find({}, {"_id": 0}).to_list(500)
    for r in rows:
        if r.get("active") is False:
            continue
        own = {norm_size_key(r.get("code")), norm_size_key(r.get("name"))}
        own |= {norm_size_key(a) for a in (r.get("aliases") or [])}
        own.discard("")
        if own & candidates:
            return r

    if not allow_create:
        return None
    return await ensure_size(db, code=key, name=raw or key, order_seq=order_seq)


async def promote_rnd_variants_to_master(db, style: dict, model: dict, user: dict = None) -> dict:
    """GAP-3: From dewi_rnd_variants(style_id) create canonical rahaza_model_variants (+FG).

    RnD variant granularity = {color, sizes:[...]}. We explode color × size into the
    canonical SSOT (one SKU per color×size) and materialize an empty FG per SKU.
    Idempotent: existing (model,color,size) combos are skipped (FG still ensured).

    2026-08-08 — UKURAN kini lewat `resolve_master_size()` dan MENGHORMATI
    `style.size_map` (petunjuk kebijakan B1 / hasil layar "Padankan Ukuran").
    Sebelumnya fungsi ini memanggil `ensure_size(code=<label mentah>)`, sehingga
    label `'All Size'` yang **sudah dipadankan ke `ALLSIZE`** tetap membuat ukuran
    master kembar `'ALL SIZE'`, dan `'28/30'` mencemari SKU FG
    (`STYLE-NVY-28/30`). Dibuktikan `scripts/poc_rnd_size_promotion.py` H2a/H2c.

    Tambahan yang dikembalikan: `sizes_created` — ukuran master yang BARU dibuat
    karena labelnya belum dipadankan. Layar memakainya untuk mengarahkan pengguna
    ke "Padankan Ukuran" alih-alih membiarkan master ukuran diam-diam bertambah.
    """
    rnd_vars = await db.dewi_rnd_variants.find({"style_id": style["id"]}, {"_id": 0}).to_list(2000)
    size_map = style.get("size_map") or []
    known_size_ids = {s["id"] for s in
                      await db.rahaza_sizes.find({}, {"_id": 0, "id": 1}).to_list(1000)}
    created, skipped, sizes_created = [], [], []
    for rv in rnd_vars:
        # F1 fix: layar R&D lama menulis HEX ke `color_code` ('#1B2A5B'). Bila hex itu
        # diteruskan sebagai `code`, master warna bisa terisi kode sampah. Prioritas:
        # color_id (FK master) → color_code yang BUKAN hex → nama warna.
        raw_code = str(rv.get("color_code") or "").strip()
        code_arg = None if raw_code.startswith("#") else (raw_code or None)
        hex_arg = rv.get("color_hex") or (raw_code if raw_code.startswith("#") else None)
        color = None
        if rv.get("color_id"):
            color = await db.rahaza_colors.find_one({"id": rv["color_id"]}, {"_id": 0})
        if not color:
            color = await ensure_color(
                db, name=rv.get("color"), code=code_arg, hex_val=hex_arg
            )
        if not color:
            continue
        sizes = rv.get("sizes") or []
        for s in sizes:
            scode = s if isinstance(s, str) else (s.get("code") or s.get("size") or "")
            size = await resolve_master_size(db, scode, size_map=size_map, allow_create=True)
            if not size:
                continue
            if size["id"] not in known_size_ids:
                known_size_ids.add(size["id"])
                sizes_created.append({"label": str(scode), "code": size.get("code"),
                                      "size_id": size["id"]})
            dup = await db.rahaza_model_variants.find_one(
                {"model_id": model["id"], "color_id": color["id"], "size_id": size["id"]}, {"_id": 0}
            )
            if dup:
                await ensure_fg_material(db, dup, user=user)
                skipped.append(dup.get("sku"))
                continue
            sku = build_variant_sku(model["code"], color["code"], size["code"])
            vdoc = {
                "id": str(uuid.uuid4()),
                "model_id": model["id"], "model_code": model["code"], "model_name": model["name"],
                "size_id": size["id"], "size_code": size["code"],
                "color_id": color["id"], "color_code": color["code"],
                "color_name": color["name"], "color_hex": color.get("hex"),
                "sku": sku, "barcode": "", "notes": "Dari RnD promote (GAP-3)",
                "active": True, "created_at": now_utc(), "updated_at": now_utc(),
            }
            await db.rahaza_model_variants.insert_one(vdoc)
            await ensure_fg_material(db, vdoc, user=user)
            created.append(sku)
    return {"created": created, "skipped": skipped,
            "created_count": len(created), "skipped_count": len(skipped),
            "sizes_created": sizes_created, "sizes_created_count": len(sizes_created)}
