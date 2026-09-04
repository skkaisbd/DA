"""core.material_fields — SSOT nama field material (kanonik) + kompatibilitas baca `yarn_*`.

LATAR BELAKANG
--------------
Proyek ini lahir dari pabrik **benang/knitting** sehingga banyak field data dinamai
`yarn_*` (`yarn_type`, `yarn_kg_per_pcs`, `default_yarn_cost_per_kg`, …). Sejak FASE 1
konsolidasi inventory, taksonomi resmi berubah menjadi **3 kategori netral**:
`Bahan · Aksesoris · Produk Jadi`. Akibatnya nama `yarn_*` menyesatkan (dipakai juga
untuk kain, interlining, bahkan aksesoris) dan sempat ditunda di FASE 5 (5.4).

RIWAYAT
-------
* **FASE 6.6-B** — strategi "canonical + alias": nama kanonik dipakai di kode baru,
  TAPI setiap write juga menulis alias legacy (mirror) supaya konsumen lama aman.
* **FASE 11 (2026-07-25)** — alias legacy **DIHENTIKAN PENULISANNYA**. Prasyarat
  `memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md` §5 sudah dipenuhi:
    1. semua penulisan alias terpusat di modul ini (`mirror`/`mirror_from_body`/
       `with_aliases`) — tidak ada route yang menulis `yarn_*` langsung;
    2. semua pembacaan memakai `read_field()` (backend) / `readField()` (frontend),
       jadi tidak ada kode yang bergantung pada nama legacy;
    3. `migrate_rename_yarn_fields.py` melaporkan **0 dokumen** yang perlu backfill —
       setiap dokumen ber-field legacy sudah punya pasangan kanoniknya.

APA YANG BERUBAH DI FASE 11
---------------------------
* `WRITE_ALIASES` **kosong** ⇒ `mirror()` menulis HANYA nama kanonik dan
  `with_aliases()` tidak lagi menambah `yarn_*` ke response API.
* `LEGACY_READ_ALIASES` **DIPERTAHANKAN** ⇒ `read_field()` tetap bisa membaca
  dokumen LAMA (mis. hasil restore backup, atau DB produksi yang belum dimigrasi).
  Ini murni jaring pengaman baca; tidak ada biaya dan tidak ada data yang hilang.
* Membersihkan kunci `yarn_*` dari DB: `migrate_rename_yarn_fields.py --drop-legacy`
  (idempoten; jalankan `--execute` dulu agar kanoniknya pasti ada).

Modul ini JUGA menjadi SSOT taksonomi tipe material (sebelumnya map `type → kategori`
disalin di `wms_putaway.py`, `rahaza_inventory_stock.py`, `rahaza_bom.py`, `lkp_pdf.py`).
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# TAKSONOMI 3 KATEGORI (SSOT) — selaras `frontend/src/lib/itemTaxonomy.js`
# ─────────────────────────────────────────────────────────────────────────────
# Tipe material yang diukur dalam satuan berat/panjang (kain, benang, interlining).
# Dipakai untuk menghitung "total bahan (kg)" pada BOM & kebutuhan material.
KGLIKE_TYPES = ("yarn", "fabric", "kain", "benang", "interlining")

CATEGORY_TYPES: dict[str, list[str]] = {
    "bahan": list(KGLIKE_TYPES),
    "aksesoris": ["accessory", "packaging"],
    "fg": ["fg"],
}

TYPE_TO_CATEGORY: dict[str, str] = {
    t: cat for cat, types in CATEGORY_TYPES.items() for t in types
}

CATEGORY_LABELS = {"bahan": "Bahan", "aksesoris": "Aksesoris", "fg": "Produk Jadi"}


def category_of(material_type: str | None) -> str:
    """Tipe material (legacy) → kategori kanonik. Default 'bahan'."""
    return TYPE_TO_CATEGORY.get((material_type or "").strip().lower(), "bahan")


def is_kglike(material_type: str | None) -> bool:
    """True bila tipe material diukur kg/meter (kain, benang, interlining)."""
    return (material_type or "").strip().lower() in KGLIKE_TYPES


def is_kglike_material(doc: dict | None) -> bool:
    """True bila DOKUMEN master material (`rahaza_materials`) bersatuan kg.

    SSOT untuk pertanyaan "pakai harga default per-kg atau per-unit?" pada
    perhitungan HPP. Dibuat di FASE 12 karena dua penghitung HPP memakai daftar
    tipe yang berbeda-beda dan lebih sempit dari taksonomi resmi:
      * `rahaza_hpp.py`              → `type == "yarn"`            (BUG-B2)
      * `production_internal_adapter`→ `type in ("yarn","fabric")` (BUG-B2)
    Akibatnya material `kain` / `benang` / `interlining` tanpa `unit_cost` diberi
    fallback harga AKSESORIS (per unit) sehingga HPP salah tanpa error.

    Menerima dokumen master (`type`) maupun baris BOM (`material_type`), dan
    tetap menghormati satuan eksplisit `kg`.
    """
    if not doc:
        return False
    if is_kglike(doc.get("type")) or is_kglike(doc.get("material_type")):
        return True
    return str(doc.get("unit") or "").strip().lower() == "kg"


def storage_role_of(material_type: str | None) -> str:
    """Kategori → peran zona storage (`core.location_resolver.ROLE_ZONE_CODES`)."""
    return category_of(material_type)


# ─────────────────────────────────────────────────────────────────────────────
# PETA RENAME FIELD
# ─────────────────────────────────────────────────────────────────────────────
# `LEGACY_READ_ALIASES` = kanonik → alias legacy, dipakai HANYA UNTUK MEMBACA
# dokumen lama. FASE 11 menghentikan penulisan alias, tetapi jaring pengaman baca
# ini sengaja DIPERTAHANKAN supaya DB produksi / hasil restore backup yang belum
# dimigrasi tetap terbaca dan tidak ada nilai yang "hilang" dari layar.
LEGACY_READ_ALIASES: dict[str, tuple[str, ...]] = {
    # komposisi/jenis bahan (mis. "Acrylic 100%", "Cotton Combed 30s")
    "composition": ("yarn_type",),
    # pemakaian bahan utama per pcs (kg) pada master model / progres produksi
    "material_kg_per_pcs": ("yarn_kg_per_pcs",),
    # fallback harga bahan per kg di costing settings (HPP)
    "default_material_cost_per_kg": ("default_yarn_cost_per_kg",),
    # hasil enrich BOM: total bahan satuan-kg per pcs
    "total_material_kg_per_pcs": ("total_yarn_kg_per_pcs",),
    # total kebutuhan bahan satuan-kg (requirements / preview BOM)
    "total_material_kg": ("total_yarn_kg",),
    # jumlah baris BOM bersatuan kg (dulu "jumlah benang")
    "bulk_line_count": ("yarn_count",),
}

# Daftar nama KANONIK (satu-satunya nama yang ditulis sejak FASE 11).
CANONICAL_FIELDS: tuple[str, ...] = tuple(LEGACY_READ_ALIASES.keys())

# FASE 11 — alias yang ikut DITULIS saat menyimpan. Sengaja KOSONG.
# Kalau suatu hari perlu memulihkan perilaku lama (mis. integrasi eksternal
# ternyata masih mencari `yarn_*`), cukup isi ulang map ini — tidak perlu
# menyentuh satu pun file route, karena semua write lewat `mirror()`.
WRITE_ALIASES: dict[str, tuple[str, ...]] = {}

LEGACY_TO_CANONICAL: dict[str, str] = {
    legacy: canon for canon, legacies in LEGACY_READ_ALIASES.items() for legacy in legacies
}

# Semua nama legacy yang dikenal — dipakai skrip migrasi `--drop-legacy`.
ALL_LEGACY_FIELDS: tuple[str, ...] = tuple(sorted(LEGACY_TO_CANONICAL.keys()))

# Label Indonesia untuk UI (dipakai FE lewat /api/meta bila diperlukan)
FIELD_LABELS = {
    "composition": "Komposisi",
    "material_kg_per_pcs": "Bahan utama/pcs (kg)",
    "default_material_cost_per_kg": "Harga bahan default (Rp/kg)",
    "total_material_kg_per_pcs": "Total bahan/pcs (kg)",
    "total_material_kg": "Total bahan (kg)",
    "bulk_line_count": "Baris bahan (kg)",
}


def _keys(canonical: str) -> tuple[str, ...]:
    """Rantai kunci BACA untuk sebuah field: kanonik dulu, lalu alias legacy.

    Tetap menyertakan alias legacy walau FASE 11 berhenti menulisnya — supaya
    dokumen lama (DB produksi / restore backup) masih terbaca.
    """
    return (canonical,) + LEGACY_READ_ALIASES.get(canonical, ())


def read_field(doc: dict | None, canonical: str, default=None):
    """Baca nilai field dengan rantai fallback kanonik → legacy.

    >>> read_field({"yarn_type": "acrylic"}, "composition")
    'acrylic'
    """
    if not doc:
        return default
    for k in _keys(canonical):
        v = doc.get(k)
        if v is not None and v != "":
            return v
    # nilai 0 / "" tetap dianggap ada bila kuncinya eksplisit
    for k in _keys(canonical):
        if k in doc:
            return doc.get(k)
    return default


def mirror(canonical: str, value) -> dict:
    """Fragment `$set` untuk sebuah field.

    FASE 11: hanya menulis nama KANONIK. `WRITE_ALIASES` sengaja kosong, jadi
    loop di bawah tidak menghasilkan apa-apa — tetapi tetap dipertahankan agar
    perilaku lama bisa dipulihkan hanya dengan mengisi ulang map itu (tanpa
    menyentuh satu pun file route).
    """
    out = {canonical: value}
    for legacy in WRITE_ALIASES.get(canonical, ()):
        out[legacy] = value
    return out


def mirror_from_body(body: dict | None, canonical: str, *, cast=None, default=None) -> dict:
    """Ambil nilai dari body request (kanonik dulu, lalu legacy) → fragment mirror.

    Mengembalikan `{}` bila body tidak menyebut field ini SAMA SEKALI dan `default`
    tidak diberikan ⇒ aman dipakai pada endpoint PATCH/PUT partial.
    """
    body = body or {}
    present = any(k in body for k in _keys(canonical))
    if not present:
        if default is None:
            return {}
        value = default
    else:
        value = read_field(body, canonical, default)
    if cast is not None:
        try:
            value = cast(value if value not in (None, "") else (default if default is not None else cast()))
        except (TypeError, ValueError):
            value = cast() if default is None else default
    return mirror(canonical, value)


def with_aliases(doc: dict, *canonicals: str) -> dict:
    """Normalkan dokumen response agar memakai nama KANONIK.

    FASE 11 mengubah arti fungsi ini:
      * DULU  — menyalin nilai ke nama kanonik DAN legacy (response bawa dua-duanya).
      * KINI  — bila dokumen lama hanya punya nama legacy, nilainya diangkat ke
                nama kanonik; nama legacy TIDAK ditambahkan dan yang sudah
                terlanjur ada di dokumen lama DIHAPUS dari response.

    Hasilnya response API bersih (satu nama per field) tanpa kehilangan data
    dari dokumen yang belum dimigrasi.
    """
    if not isinstance(doc, dict):
        return doc
    targets = canonicals or CANONICAL_FIELDS
    for canon in targets:
        keys = _keys(canon)
        found = None
        for k in keys:
            if k in doc and doc.get(k) is not None:
                found = doc.get(k)
                break
        if found is None:
            # tidak ada nilai — tetap bersihkan sisa kunci legacy bila ada
            for legacy in LEGACY_READ_ALIASES.get(canon, ()):
                doc.pop(legacy, None)
            continue
        doc[canon] = found
        for legacy in LEGACY_READ_ALIASES.get(canon, ()):
            doc.pop(legacy, None)
    return doc
