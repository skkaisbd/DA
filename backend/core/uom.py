"""core.uom — SSOT konversi satuan (Unit of Measure) material.

LATAR BELAKANG
--------------
Audit 2026-07-27 (`docs/AUDIT_KONVERSI_SATUAN.md`) menemukan:

* Konversi kemasan hanya ada di Portal Aksesoris; 11 titik masuk stok lain
  (Gudang Receiving/PO/Putaway/Opname/Pengeluaran, Cutting, dll) tidak punya.
* Harga tidak ikut dikonversi saat input per kemasan → nilai persediaan &
  jurnal membengkak sebesar `pack_size` (BUG-1, sudah diperbaiki di F0.5).
* Struktur lama hanya sanggup **satu** tingkat kemasan dan **satu** jenis kemasan.

Modul ini menjadi **satu-satunya** tempat penghitungan faktor konversi, mengikuti
pola yang sudah dipakai `core/material_fields.py`.

INVARIAN YANG DIJAGA (lihat memory/INVARIANTS.md §U)
----------------------------------------------------
* **INV-UOM-1** `rahaza_materials.unit_cost` SELALU harga per **satuan dasar**.
  Satuan lain hanya alat bantu entri; hasil konversinya yang disimpan.
  (5 modul hilir — RnD HPP, HPP produksi, MRP, adapter produksi, posting GL —
  memakai rumus `amount = qty × unit_cost` dan mengasumsikan satuan dasar.)
* **INV-UOM-2** Semua qty di `rahaza_material_stock`, `rahaza_stock_ledger`,
  `rahaza_material_movements` SELALU dalam satuan dasar.
* **INV-UOM-3** `uoms[0]` wajib `is_base=True` & `factor=1`; setiap `factor > 0`;
  `code` unik dalam satu material.
* **INV-UOM-4** `unit` (lama) selalu sama dengan `base_uom` (baru).
* **INV-UOM-5** Mengedit daftar `uoms` tidak boleh mengubah angka stok yang ada.
* **INV-UOM-6** `factor` selalu relatif ke **satuan dasar**, bukan ke induknya.

BENTUK DATA
-----------
    material = {
      "unit": "pcs",            # lama — cermin dari base_uom
      "base_uom": "pcs",
      "uoms": [
        {"code":"pcs","name":"Pieces", "factor":1,   "is_base":True,"level":0},
        {"code":"bks","name":"Bungkus","factor":144, "parent":"pcs","level":1,
         "is_purchase_default":True},
        {"code":"ktn","name":"Karton", "factor":1728,"parent":"bks","level":2},
      ],
      "purchase_uom":"bks", "issue_uom":"pcs", "display_uom":"bks",
      # lama — tetap ditulis sebagai cermin supaya kode lama tidak pecah
      "pack_unit":"bks", "pack_size":144, "display_in_packs":True,
    }

KOMPATIBILITAS MUNDUR
---------------------
`resolve_uoms()` punya fallback berlapis sehingga 1.031 material yang ada
sekarang langsung bekerja **tanpa perlu dimigrasi**:
  1. ada `uoms` valid                       → pakai itu
  2. ada `pack_unit` + `pack_size > 1`      → bangun 2 baris on-the-fly
  3. tidak ada keduanya                     → 1 baris satuan dasar saja
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

# Kedalaman kemasan yang didukung: 0 = satuan dasar, 1 = bungkus, 2 = karton.
MAX_LEVEL = 2
MAX_UOMS = MAX_LEVEL + 1

# Toleransi pembulatan faktor (hindari 0.30000000000000004)
_ROUND = 6

DEFAULT_BASE = "pcs"


class UomError(ValueError):
    """Satuan tidak dikenal / daftar UOM tidak valid."""


# ─────────────────────────────────────────────────────────────────────────────
# Util dasar
# ─────────────────────────────────────────────────────────────────────────────
def normalize_code(code: Any) -> str:
    """Samakan penulisan kode satuan: buang spasi, huruf kecil."""
    return str(code or "").strip().lower()


def _num(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f and f not in (float("inf"), float("-inf")) else default


def _r(v: float) -> float:
    return round(_num(v), _ROUND)


def base_uom_of(material: dict | None) -> str:
    """Satuan dasar material. `base_uom` diutamakan, lalu `unit` (lama)."""
    m = material or {}
    return normalize_code(m.get("base_uom") or m.get("unit") or DEFAULT_BASE) or DEFAULT_BASE


# ─────────────────────────────────────────────────────────────────────────────
# Resolusi daftar UOM (dengan fallback berlapis)
# ─────────────────────────────────────────────────────────────────────────────
def _row(code: str, factor: float, *, name: str = "", is_base: bool = False,
         parent: Optional[str] = None, level: int = 0, **extra) -> dict:
    row = {
        "code": normalize_code(code),
        "name": (name or "").strip() or normalize_code(code).upper(),
        "factor": _r(factor),
        "is_base": bool(is_base),
        "level": int(level),
    }
    if parent:
        row["parent"] = normalize_code(parent)
    for k in ("is_purchase_default", "is_issue_default", "is_display_default"):
        if extra.get(k):
            row[k] = True
    for k in ("barcode", "notes"):
        if extra.get(k):
            row[k] = str(extra[k])
    return row


def build_from_legacy(material: dict | None) -> list[dict]:
    """Bangun daftar UOM dari field lama (`unit` + `pack_unit`/`pack_size`)."""
    m = material or {}
    base = base_uom_of(m)
    rows = [_row(base, 1, name=base.upper(), is_base=True, level=0)]

    pack_unit = normalize_code(m.get("pack_unit"))
    pack_size = _num(m.get("pack_size"), 1)
    if pack_unit and pack_unit != base and pack_size > 1:
        rows.append(_row(
            pack_unit, pack_size, name=pack_unit.upper(),
            parent=base, level=1,
            is_purchase_default=True,
            # `display_in_packs` lama = "tampilkan stok dalam kemasan"
            is_display_default=bool(m.get("display_in_packs")),
            notes=f"1 {pack_unit} = {_r(pack_size)} {base}",
        ))
    return rows


def resolve_uoms(material: dict | None) -> list[dict]:
    """Daftar UOM efektif material — SELALU mengembalikan minimal 1 baris.

    Baris pertama dijamin satuan dasar (`is_base=True`, `factor=1`).
    """
    m = material or {}
    raw = m.get("uoms")
    if isinstance(raw, list) and raw:
        base = base_uom_of(m)
        out: list[dict] = []
        seen: set[str] = set()
        for r in raw:
            if not isinstance(r, dict):
                continue
            code = normalize_code(r.get("code"))
            if not code or code in seen:
                continue
            factor = _num(r.get("factor"), 0)
            if code == base:
                factor = 1.0
            if factor <= 0:
                continue
            seen.add(code)
            out.append(_row(
                code, factor,
                name=r.get("name") or "",
                is_base=(code == base),
                parent=r.get("parent"),
                level=int(_num(r.get("level"), 0)),
                is_purchase_default=r.get("is_purchase_default"),
                is_issue_default=r.get("is_issue_default"),
                is_display_default=r.get("is_display_default"),
                barcode=r.get("barcode"),
                notes=r.get("notes"),
            ))
        if base not in seen:
            out.insert(0, _row(base, 1, is_base=True, level=0))
        out.sort(key=lambda x: (x["factor"], x["code"]))
        return out
    return build_from_legacy(m)


def find_uom(material: dict | None, code: Any) -> Optional[dict]:
    c = normalize_code(code)
    if not c:
        return None
    for r in resolve_uoms(material):
        if r["code"] == c:
            return r
    return None


def uom_codes(material: dict | None) -> list[str]:
    return [r["code"] for r in resolve_uoms(material)]


# ─────────────────────────────────────────────────────────────────────────────
# Konversi
# ─────────────────────────────────────────────────────────────────────────────
def factor_of(material: dict | None, code: Any = None, *, strict: bool = True) -> float:
    """Faktor satuan `code` terhadap satuan dasar.

    `code` kosong / sama dengan satuan dasar → 1.0.
    `strict=False` mengembalikan 1.0 untuk satuan tak dikenal (mode toleran,
    dipakai jalur lama supaya tidak memunculkan error baru).
    """
    c = normalize_code(code)
    if not c or c == base_uom_of(material):
        return 1.0
    row = find_uom(material, c)
    if row:
        return row["factor"]
    if strict:
        known = ", ".join(uom_codes(material)) or "-"
        raise UomError(f"Satuan '{c}' tidak dikenal untuk material ini. Tersedia: {known}")
    return 1.0


def to_base(material: dict | None, qty: Any, uom: Any = None, *, strict: bool = True) -> float:
    """Ubah `qty` dari satuan `uom` ke **satuan dasar** (INV-UOM-2)."""
    return _r(_num(qty) * factor_of(material, uom, strict=strict))


def from_base(material: dict | None, qty_base: Any, uom: Any = None, *, strict: bool = True) -> float:
    """Ubah `qty_base` (satuan dasar) ke satuan `uom` — untuk TAMPILAN saja."""
    f = factor_of(material, uom, strict=strict)
    return _r(_num(qty_base) / f) if f else _r(qty_base)


def cost_to_base(material: dict | None, cost: Any, uom: Any = None, *, strict: bool = True) -> float:
    """Ubah harga per satuan `uom` menjadi harga per **satuan dasar** (INV-UOM-1)."""
    f = factor_of(material, uom, strict=strict)
    return _r(_num(cost) / f) if f else _r(cost)


def cost_from_base(material: dict | None, cost_base: Any, uom: Any = None, *, strict: bool = True) -> float:
    """Ubah harga per satuan dasar menjadi harga per satuan `uom` — TAMPILAN saja."""
    return _r(_num(cost_base) * factor_of(material, uom, strict=strict))


def convert(material: dict | None, qty: Any, from_uom: Any, to_uom: Any, *, strict: bool = True) -> float:
    """Konversi langsung antar dua satuan pada material yang sama."""
    return from_base(material, to_base(material, qty, from_uom, strict=strict), to_uom, strict=strict)


# ─────────────────────────────────────────────────────────────────────────────
# Satuan default
# ─────────────────────────────────────────────────────────────────────────────
def _default_uom(material: dict | None, key: str, flag: str) -> str:
    m = material or {}
    explicit = normalize_code(m.get(key))
    if explicit and find_uom(m, explicit):
        return explicit
    for r in resolve_uoms(m):
        if r.get(flag):
            return r["code"]
    return base_uom_of(m)


def purchase_uom_of(material: dict | None) -> str:
    """Satuan default saat membeli / menerima barang."""
    return _default_uom(material, "purchase_uom", "is_purchase_default")


def issue_uom_of(material: dict | None) -> str:
    """Satuan default saat memakai / mengeluarkan barang."""
    return _default_uom(material, "issue_uom", "is_issue_default")


def display_uom_of(material: dict | None) -> str:
    """Satuan default saat menampilkan stok di daftar.

    Kompatibilitas: material lama yang hanya punya `display_in_packs=True`
    tetap ditampilkan dalam kemasannya walau `display_uom` belum diisi.
    """
    code = _default_uom(material, "display_uom", "is_display_default")
    m = material or {}
    if code == base_uom_of(m) and m.get("display_in_packs"):
        pack = normalize_code(m.get("pack_unit"))
        if pack and pack != code and find_uom(m, pack):
            return pack
    return code


# ─────────────────────────────────────────────────────────────────────────────
# Tampilan
# ─────────────────────────────────────────────────────────────────────────────
def _fmt(n: float) -> str:
    n = _r(n)
    if n == int(n):
        return f"{int(n):,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")


def format_qty(material: dict | None, qty_base: Any, uom: Any = None) -> str:
    """`"450 m"` — satu satuan saja."""
    code = normalize_code(uom) or base_uom_of(material)
    return f"{_fmt(from_base(material, qty_base, code, strict=False))} {code}"


def format_dual(material: dict | None, qty_base: Any, secondary: Any = None) -> str:
    """`"450 m (9 rol)"` — satuan dasar + satuan kemasan.

    Menjawab kebutuhan "double satuan": satu angka stok bisa dibaca dalam dua
    satuan sekaligus tanpa memaksa memilih salah satu.
    """
    base = base_uom_of(material)
    primary = f"{_fmt(_num(qty_base))} {base}"
    sec = normalize_code(secondary) or display_uom_of(material)
    if not sec or sec == base:
        return primary
    row = find_uom(material, sec)
    if not row:
        return primary
    return f"{primary} ({_fmt(from_base(material, qty_base, sec, strict=False))} {sec})"


# ─────────────────────────────────────────────────────────────────────────────
# Validasi & normalisasi payload
# ─────────────────────────────────────────────────────────────────────────────
def validate_uoms(uoms: Iterable[dict] | None, base_uom: str | None = None) -> tuple[bool, list[str]]:
    """Periksa INV-UOM-3 & INV-UOM-6. Mengembalikan (ok, daftar_pesan_error)."""
    errs: list[str] = []
    rows = list(uoms or [])
    if not rows:
        return True, []          # kosong = pakai fallback, sah
    base = normalize_code(base_uom) if base_uom else None

    seen: set[str] = set()
    n_base = 0
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            errs.append(f"Baris {i}: format tidak valid")
            continue
        code = normalize_code(r.get("code"))
        if not code:
            errs.append(f"Baris {i}: kode satuan wajib diisi")
            continue
        if code in seen:
            errs.append(f"Baris {i}: kode satuan '{code}' terduplikasi")
        seen.add(code)

        factor = _num(r.get("factor"), 0)
        if factor <= 0:
            errs.append(f"Satuan '{code}': faktor harus lebih besar dari 0")

        lvl = int(_num(r.get("level"), 0))
        if lvl < 0 or lvl > MAX_LEVEL:
            errs.append(f"Satuan '{code}': tingkat {lvl} di luar batas (0–{MAX_LEVEL})")

        if r.get("is_base") or (base and code == base):
            n_base += 1
            if factor != 1:
                errs.append(f"Satuan dasar '{code}' wajib berfaktor 1 (sekarang {factor})")

        parent = normalize_code(r.get("parent"))
        if parent and parent not in {normalize_code(x.get("code")) for x in rows}:
            errs.append(f"Satuan '{code}': induk '{parent}' tidak ada dalam daftar")
        if parent == code:
            errs.append(f"Satuan '{code}': induk tidak boleh dirinya sendiri")

    if len(rows) > MAX_UOMS:
        errs.append(f"Maksimal {MAX_UOMS} satuan per item (dasar + {MAX_LEVEL} tingkat kemasan)")
    if n_base == 0:
        errs.append("Harus ada tepat satu satuan dasar (faktor 1)")
    elif n_base > 1:
        errs.append("Hanya boleh ada satu satuan dasar")

    return (not errs), errs


def mirror_legacy(uoms: Iterable[dict] | None, base_uom: str) -> dict:
    """Hasilkan field lama (`unit`/`pack_unit`/`pack_size`/`display_in_packs`)
    dari daftar UOM baru — LAPIS L2 strategi nol-regresi.

    Kemasan yang dipilih sebagai cermin = satuan non-dasar dengan faktor
    TERKECIL (kemasan tingkat 1), karena itulah yang dulu disimpan di `pack_*`.
    """
    base = normalize_code(base_uom) or DEFAULT_BASE
    rows = [r for r in (uoms or []) if isinstance(r, dict)]
    packs = sorted(
        (r for r in rows if normalize_code(r.get("code")) and normalize_code(r.get("code")) != base
         and _num(r.get("factor"), 0) > 1),
        key=lambda r: _num(r.get("factor"), 0),
    )
    out = {"unit": base, "base_uom": base}
    if packs:
        p = packs[0]
        out["pack_unit"] = normalize_code(p.get("code"))
        out["pack_size"] = _r(_num(p.get("factor"), 1))
        out["display_in_packs"] = True
    else:
        out["pack_unit"] = "pack"
        out["pack_size"] = 1.0
        out["display_in_packs"] = False
    return out


def sanitize_uoms(uoms: Iterable[dict] | None, base_uom: str) -> list[dict]:
    """Bersihkan & urutkan daftar UOM sebelum disimpan.

    * memaksa satuan dasar berfaktor 1
    * membuang baris tanpa kode / faktor <= 0 / duplikat
    * mengurutkan menaik berdasarkan faktor (dasar → bungkus → karton)
    * menghitung ulang `level` mengikuti urutan faktor
    """
    base = normalize_code(base_uom) or DEFAULT_BASE
    cleaned: list[dict] = []
    seen: set[str] = set()
    for r in (uoms or []):
        if not isinstance(r, dict):
            continue
        code = normalize_code(r.get("code"))
        if not code or code in seen:
            continue
        factor = 1.0 if code == base else _num(r.get("factor"), 0)
        if factor <= 0:
            continue
        seen.add(code)
        cleaned.append(_row(
            code, factor,
            name=r.get("name") or "",
            is_base=(code == base),
            parent=r.get("parent"),
            level=0,
            is_purchase_default=r.get("is_purchase_default"),
            is_issue_default=r.get("is_issue_default"),
            is_display_default=r.get("is_display_default"),
            barcode=r.get("barcode"),
            notes=r.get("notes"),
        ))
    if base not in seen:
        cleaned.append(_row(base, 1, is_base=True, level=0))
    cleaned.sort(key=lambda x: (x["factor"], x["code"]))
    prev = None
    for i, r in enumerate(cleaned):
        r["level"] = min(i, MAX_LEVEL)
        if i > 0 and not r.get("parent"):
            r["parent"] = prev
        prev = r["code"]
    return cleaned[:MAX_UOMS]


def apply_payload(body: dict | None, current: dict | None = None) -> dict:
    """Susun potongan dokumen material dari body request.

    Mengembalikan dict berisi HANYA field UOM yang perlu di-`$set`, lengkap
    dengan cermin field lama. Melempar `UomError` bila tidak valid.

    Dipakai oleh POST/PUT material supaya validasi & mirroring terpusat di sini.
    """
    body = body or {}
    cur = current or {}

    base = normalize_code(body.get("base_uom") or body.get("unit")
                          or cur.get("base_uom") or cur.get("unit") or DEFAULT_BASE)

    if "uoms" in body:
        ok, errs = validate_uoms(body.get("uoms"), base)
        if not ok:
            raise UomError("; ".join(errs))
        rows = sanitize_uoms(body.get("uoms"), base)
    else:
        # tidak dikirim → pertahankan yang ada, atau bangun dari field lama
        merged = {**cur, **{k: body[k] for k in ("unit", "pack_unit", "pack_size") if k in body}}
        rows = resolve_uoms({**merged, "base_uom": base})

    out: dict = {"uoms": rows}
    out.update(mirror_legacy(rows, base))

    codes = {r["code"] for r in rows}
    pack_default = out.get("pack_unit") if out.get("display_in_packs") else None
    for key, fallback in (("purchase_uom", out.get("pack_unit") if out.get("display_in_packs") else base),
                          ("issue_uom", base),
                          ("display_uom", pack_default or base)):
        val = normalize_code(body.get(key) if key in body else cur.get(key))
        out[key] = val if val in codes else (fallback if fallback in codes else base)

    # `display_in_packs` boleh ditimpa manual (mis. punya kemasan tapi ingin
    # tetap tampil dalam satuan dasar)
    if "display_in_packs" in body:
        out["display_in_packs"] = bool(body["display_in_packs"])
    return out


__all__ = [
    "UomError", "MAX_LEVEL", "MAX_UOMS", "DEFAULT_BASE",
    "normalize_code", "base_uom_of", "resolve_uoms", "build_from_legacy",
    "find_uom", "uom_codes", "factor_of",
    "to_base", "from_base", "cost_to_base", "cost_from_base", "convert",
    "purchase_uom_of", "issue_uom_of", "display_uom_of",
    "format_qty", "format_dual",
    "validate_uoms", "sanitize_uoms", "mirror_legacy", "apply_payload",
]
