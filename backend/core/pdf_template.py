"""core/pdf_template.py — SATU sumber kebenaran template dokumen PDF (SESI #19).

MENGAPA BERKAS INI ADA (keluhan pemilik, dicatat di
`memory/PERMINTAAN_OWNER_PDF_EDITOR.md`)
------------------------------------------------------------------------------
  · "untuk pdf konfigurasi saat ini editor masih sangat buruk"
  · "cek ada dua halaman berbeda ui ux-nya jelas"
  · "header surat sangat buruk sekali"

Yang TERUKUR sebelum berkas ini:
  · DUA koleksi setelan yang tidak saling tahu — `pdf_document_settings` (kop &
    tanda tangan, 7 jenis surat) dan `pdf_export_configs` (kolom tabel, 13 jenis
    laporan) — dengan dua layar berbeda. Tiga jenis dokumen ada di KEDUANYA, jadi
    satu dokumen bisa punya dua "pendapat" tentang dirinya sendiri.
  · Kop surat tidak bisa memuat LOGO sama sekali (`show_logo` disimpan, tetapi tidak
    ada satu pun generator yang menggambar logo), tidak bisa memuat NPWP/telepon
    secara terpisah, dan tata letaknya tetap.
  · Kolom tabel hanya bisa DISEMBUNYIKAN, tidak bisa DIURUTKAN, dan tidak bisa
    DITAMBAH (mis. kolom kosong untuk dicentang tangan).
  · Blok tanda tangan dibatasi 3 dan bentuknya label+nama+peran; pemilik meminta
    bentuk baku: SUBJECT di atas, ruang kosong di tengah, NAMA di bawah.
  · Pick List sama sekali tidak punya kop surat (tidak ada nama PT!), dan tabelnya
    memakai lebar kolom milimeter tetap: 174 mm dari 186 mm lebar konten ⇒ tabel
    tidak penuh halaman.

Keputusan: SATU koleksi `pdf_templates` berisi satu dokumen GLOBAL (kop + tanda
tangan + footer bawaan untuk semua dokumen) dan satu dokumen OVERRIDE per jenis
dokumen. Kolom tabel selalu milik jenis dokumen (kolom SPP tidak berarti apa pun
untuk slip gaji). Setelan lama dimigrasi otomatis dan sekali jalan.
"""
from __future__ import annotations

import base64
import binascii
import io
import logging
import uuid
from datetime import datetime, timezone

from data.pdf_doc_registry import (SUPPORTED_PDF_DOCS, columns_of, default_signatures,
                                   page_of, required_keys, sample_context, sample_info,
                                   sample_rows, spec, weights_of)

log = logging.getLogger(__name__)

COLL = "pdf_templates"
LEGACY_DOC_SETTINGS = "pdf_document_settings"
LEGACY_EXPORT_CONFIGS = "pdf_export_configs"

# ── GEOMETRI HALAMAN (dipindah dari routes/operations_pdf_helpers.py) ──────────
# A4 dengan margin 12 mm. Angka ini pernah ditulis sebagai angka ajaib (515/786)
# dan menyebabkan tabel tidak penuh / meluber keluar halaman — penjaga INV-F17
# sekarang mengukurnya. Satu tempat saja supaya tidak bisa berbeda lagi.
PDF_MARGIN_PT = 12 * 2.834645669
CONTENT_W_PORTRAIT = round(595.276 - 2 * PDF_MARGIN_PT, 1)    # ≈ 527,2 pt
CONTENT_W_LANDSCAPE = round(841.89 - 2 * PDF_MARGIN_PT, 1)    # ≈ 773,8 pt


def content_width(page=None) -> float:
    """Lebar konten yang BENAR-BENAR tersedia — satu sumber untuk semua tabel."""
    return CONTENT_W_LANDSCAPE if page == 'landscape' else CONTENT_W_PORTRAIT


# ═══════════════════════════════════════════════════════════════════════════════
# BENTUK TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════════
HEADER_LAYOUTS = ("logo-left", "logo-center", "logo-right", "text-only")
NAME_SOURCES = ("custom", "field", "blank")
ALIGNS = ("left", "center", "right")

DEFAULT_HEADER = {
    "show": True,
    "layout": "logo-left",
    "logo_data": "",            # data URI base64 (disimpan di MongoDB, tanpa layanan luar)
    "logo_height_mm": 16,
    "use_company_profile": True,  # ambil nama/alamat/telp dari Pengaturan Perusahaan
    "company_name": "",
    "address": "",
    "phone": "",
    "email": "",
    "website": "",
    "npwp": "",
    "extra_line": "",
    "show_divider": True,
    "text_align": "left",
    "show_title": True,
    "title_align": "left",
    "title_override": "",
}

DEFAULT_SIGNATURES = {
    "show": True,
    "per_row": 3,
    "space_mm": 18,             # tinggi ruang kosong untuk tanda tangan basah
    "show_place_date": False,
    "place": "",
    "blocks": [],              # diisi dari registry per jenis dokumen
}

DEFAULT_FOOTER = {
    "show": True,
    "text": "",
    "show_printed_at": True,
}

DEFAULT_TABLE = {
    "header_bg": "#334155",
    "zebra": True,
    "font_size": 7.5,
    "grid": True,
}

MAX_LOGO_BYTES = 700 * 1024      # 700 KB — cukup untuk logo tajam, aman untuk 1 dokumen Mongo
MAX_SIGNATURE_BLOCKS = 6
MAX_EXTRA_COLUMNS = 6


def _now():
    return datetime.now(timezone.utc)


def _merge(default: dict, saved) -> dict:
    """Gabung setelan tersimpan di atas bawaan — kunci tak dikenal DIBUANG.

    Sengaja membuang kunci asing: setelan yang tidak pernah dipakai generator akan
    tampak "tersimpan" di layar dan membuat orang percaya sudah mengatur sesuatu.
    """
    out = dict(default)
    if isinstance(saved, dict):
        for k, v in saved.items():
            if k in out and v is not None:
                out[k] = v
    return out


def default_columns(doc_key: str) -> list[dict]:
    """Kolom bawaan (semua tampil, urutan registry, lebar otomatis)."""
    return [
        {"key": c["key"], "label": c["label"], "visible": True,
         "width": 0, "align": "left", "custom": False,
         "required": bool(c.get("required"))}
        for c in columns_of(doc_key)
    ]


def defaults_for(doc_key: str = "") -> dict:
    """Template bawaan lengkap untuk satu jenis dokumen (atau global bila kosong)."""
    sig = dict(DEFAULT_SIGNATURES)
    sig["blocks"] = default_signatures(doc_key) if doc_key else [
        {"subject": "Dibuat oleh", "name_source": "blank", "custom_name": "",
         "field_key": "", "note": ""},
        {"subject": "Disetujui oleh", "name_source": "blank", "custom_name": "",
         "field_key": "", "note": ""},
    ]
    return {
        "doc_key": doc_key,
        "header": dict(DEFAULT_HEADER),
        "signatures": sig,
        "footer": dict(DEFAULT_FOOTER),
        "table": dict(DEFAULT_TABLE),
        "columns": default_columns(doc_key) if doc_key else [],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# BACA / SIMPAN / GABUNG
# ═══════════════════════════════════════════════════════════════════════════════
async def load_raw(db, doc_key: str = "") -> dict:
    """Dokumen template apa adanya dari basis data ({} bila belum pernah disimpan)."""
    scope = "doc" if doc_key else "global"
    return await db[COLL].find_one({"scope": scope, "doc_key": doc_key or ""},
                                   {"_id": 0}) or {}


async def get_global(db) -> dict:
    raw = await load_raw(db, "")
    out = defaults_for("")
    out["header"] = _merge(DEFAULT_HEADER, raw.get("header"))
    out["signatures"] = _merge(out["signatures"], raw.get("signatures"))
    out["footer"] = _merge(DEFAULT_FOOTER, raw.get("footer"))
    out["table"] = _merge(DEFAULT_TABLE, raw.get("table"))
    out["scope"] = "global"
    out["updated_at"] = raw.get("updated_at")
    out["updated_by"] = raw.get("updated_by")
    return out


async def get_doc(db, doc_key: str) -> dict:
    """Setelan per dokumen APA ADANYA (termasuk bendera override) + bawaan."""
    raw = await load_raw(db, doc_key)
    out = defaults_for(doc_key)
    out["scope"] = "doc"
    out["override_header"] = bool(raw.get("override_header"))
    out["override_signatures"] = bool(raw.get("override_signatures"))
    out["override_footer"] = bool(raw.get("override_footer"))
    out["header"] = _merge(DEFAULT_HEADER, raw.get("header"))
    out["signatures"] = _merge(out["signatures"], raw.get("signatures"))
    out["footer"] = _merge(DEFAULT_FOOTER, raw.get("footer"))
    out["table"] = _merge(DEFAULT_TABLE, raw.get("table"))
    if raw.get("columns"):
        out["columns"] = normalize_columns(doc_key, raw["columns"])
    out["updated_at"] = raw.get("updated_at")
    out["updated_by"] = raw.get("updated_by")
    return out


async def resolve(db, doc_key: str) -> dict:
    """Template EFEKTIF yang dipakai generator: global + override per dokumen.

    Kolom selalu milik dokumen. Kop/tanda tangan/footer memakai global kecuali
    dokumen ini secara sengaja menyalakan override — jadi mengubah kop sekali
    berlaku untuk semua surat, dan dokumen yang perlu beda tetap bisa beda.
    """
    g = await get_global(db)
    d = await get_doc(db, doc_key)
    eff = {
        "doc_key": doc_key,
        "header": d["header"] if d.get("override_header") else g["header"],
        "signatures": d["signatures"] if d.get("override_signatures") else _sig_for_doc(g, doc_key),
        "footer": d["footer"] if d.get("override_footer") else g["footer"],
        "table": d["table"] if d.get("override_header") else g["table"],
        "columns": d["columns"],
        "page": page_of(doc_key),
        "title": spec(doc_key).get("title", spec(doc_key).get("label", doc_key)),
    }
    return eff


def _sig_for_doc(global_tpl: dict, doc_key: str) -> dict:
    """Tanda tangan global + blok BAWAAN dokumen bila global belum diatur.

    Alasannya: blok tanda tangan surat jalan ("Pengirim/Sopir/Penerima") tidak
    masuk akal untuk slip gaji. Global hanya menentukan TATA LETAK (jumlah kolom,
    tinggi ruang) selama pemilik belum menuliskan blok globalnya sendiri.
    """
    sig = dict(global_tpl.get("signatures") or DEFAULT_SIGNATURES)
    if not sig.get("blocks"):
        sig["blocks"] = default_signatures(doc_key)
    return sig


def normalize_columns(doc_key: str, cols) -> list[dict]:
    """Bersihkan daftar kolom: kunci dikenal, kolom wajib tetap tampil, tanpa kembar."""
    known = {c["key"]: c for c in columns_of(doc_key)}
    req = set(required_keys(doc_key))
    seen, out, extra = set(), [], 0
    for c in (cols or []):
        if not isinstance(c, dict):
            continue
        key = str(c.get("key") or "").strip()[:40]
        if not key or key in seen:
            continue
        is_custom = key not in known
        if is_custom:
            extra += 1
            if extra > MAX_EXTRA_COLUMNS:
                continue
        seen.add(key)
        out.append({
            "key": key,
            "label": (str(c.get("label") or known.get(key, {}).get("label") or key).strip())[:40],
            "visible": True if key in req else bool(c.get("visible", True)),
            "width": max(0, min(10, float(c.get("width") or 0))),
            "align": c.get("align") if c.get("align") in ALIGNS else "left",
            "custom": is_custom,
            "required": key in req,
        })
    # kolom registry yang tidak disebut tetap ada (di belakang) supaya kolom baru
    # yang ditambahkan pengembang tidak hilang diam-diam dari dokumen lama.
    for c in columns_of(doc_key):
        if c["key"] not in seen:
            out.append({"key": c["key"], "label": c["label"],
                        "visible": True if c["key"] in req else True,
                        "width": 0, "align": "left", "custom": False,
                        "required": c["key"] in req})
    return out


def normalize_signature_blocks(doc_key: str, blocks) -> list[dict]:
    allowed = {f["key"] for f in spec(doc_key).get("available_fields", [])} if doc_key else set()
    out = []
    for b in (blocks or [])[:MAX_SIGNATURE_BLOCKS]:
        if not isinstance(b, dict):
            continue
        src = b.get("name_source") if b.get("name_source") in NAME_SOURCES else "blank"
        fkey = str(b.get("field_key") or "")
        if src == "field" and doc_key and fkey and fkey not in allowed:
            src, fkey = "blank", ""
        out.append({
            "subject": (str(b.get("subject") or b.get("label") or "").strip())[:60],
            "name_source": src,
            "custom_name": (str(b.get("custom_name") or "").strip())[:80],
            "field_key": fkey[:60],
            "note": (str(b.get("note") or b.get("role_label") or "").strip())[:60],
        })
    return out


def validate_logo(data: str) -> str:
    """Logo base64: hanya PNG/JPEG/WEBP dan maksimal 700 KB. Mengembalikan data URI."""
    s = (data or "").strip()
    if not s:
        return ""
    if not s.startswith("data:image/"):
        raise ValueError("Logo harus berupa data URI gambar (data:image/png;base64,...).")
    try:
        meta, b64 = s.split(",", 1)
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, binascii.Error) as e:
        raise ValueError(f"Logo tidak bisa dibaca: {e}") from e
    if not any(t in meta for t in ("image/png", "image/jpeg", "image/jpg", "image/webp")):
        raise ValueError("Format logo harus PNG, JPG, atau WEBP.")
    if len(raw) > MAX_LOGO_BYTES:
        raise ValueError(
            f"Ukuran logo {len(raw) // 1024} KB melebihi batas {MAX_LOGO_BYTES // 1024} KB. "
            "Perkecil gambarnya dulu.")
    return s


async def save(db, doc_key: str, body: dict, user_label: str = "") -> dict:
    """Simpan template GLOBAL (doc_key kosong) atau per dokumen. Validasi ketat."""
    scope = "doc" if doc_key else "global"
    if doc_key and doc_key not in SUPPORTED_PDF_DOCS:
        raise ValueError(f"Jenis dokumen '{doc_key}' tidak dikenal.")

    # Patch SEBAGIAN digabung di atas nilai TERSIMPAN, bukan di atas bawaan.
    # Kalau digabung di atas bawaan, mengirim satu field saja (mis. hanya logo)
    # akan MENGHAPUS nama PT & alamat yang sudah diatur — kehilangan senyap yang
    # baru terlihat saat dokumen berikutnya dicetak.
    cur = await db[COLL].find_one({"scope": scope, "doc_key": doc_key or ""},
                                  {"_id": 0}) or {}

    def dasar(nama, bawaan):
        return _merge(bawaan, cur.get(nama))

    patch = {"scope": scope, "doc_key": doc_key or "",
             "updated_at": _now(), "updated_by": user_label}

    if "header" in body:
        hdr = _merge(dasar("header", DEFAULT_HEADER), body.get("header"))
        if hdr.get("layout") not in HEADER_LAYOUTS:
            hdr["layout"] = "logo-left"
        for k in ("text_align", "title_align"):
            if hdr.get(k) not in ALIGNS:
                hdr[k] = "left"
        hdr["logo_data"] = validate_logo(hdr.get("logo_data"))
        try:
            hdr["logo_height_mm"] = max(6, min(40, float(hdr.get("logo_height_mm") or 16)))
        except (TypeError, ValueError):
            hdr["logo_height_mm"] = 16
        for k in ("company_name", "address", "phone", "email", "website", "npwp",
                  "extra_line", "title_override"):
            hdr[k] = str(hdr.get(k) or "").strip()[:180]
        patch["header"] = hdr

    if "signatures" in body:
        sig = _merge(dasar("signatures", DEFAULT_SIGNATURES), body.get("signatures"))
        sig["blocks"] = normalize_signature_blocks(doc_key, (body.get("signatures") or {}).get("blocks"))
        try:
            sig["per_row"] = max(1, min(4, int(sig.get("per_row") or 3)))
            sig["space_mm"] = max(8, min(40, float(sig.get("space_mm") or 18)))
        except (TypeError, ValueError):
            sig["per_row"], sig["space_mm"] = 3, 18
        sig["place"] = str(sig.get("place") or "").strip()[:60]
        patch["signatures"] = sig

    if "footer" in body:
        ftr = _merge(dasar("footer", DEFAULT_FOOTER), body.get("footer"))
        ftr["text"] = str(ftr.get("text") or "").strip()[:240]
        patch["footer"] = ftr

    if "table" in body:
        tbl = _merge(dasar("table", DEFAULT_TABLE), body.get("table"))
        bg = str(tbl.get("header_bg") or "#334155").strip()
        tbl["header_bg"] = bg if (bg.startswith("#") and len(bg) in (4, 7)) else "#334155"
        try:
            tbl["font_size"] = max(6.0, min(10.0, float(tbl.get("font_size") or 7.5)))
        except (TypeError, ValueError):
            tbl["font_size"] = 7.5
        patch["table"] = tbl

    if doc_key:
        if "columns" in body:
            patch["columns"] = normalize_columns(doc_key, body.get("columns"))
        for flag in ("override_header", "override_signatures", "override_footer"):
            if flag in body:
                patch[flag] = bool(body.get(flag))

    await db[COLL].update_one(
        {"scope": scope, "doc_key": doc_key or ""},
        {"$set": patch, "$setOnInsert": {"id": str(uuid.uuid4())}},
        upsert=True,
    )
    return await (get_doc(db, doc_key) if doc_key else get_global(db))


async def reset(db, doc_key: str) -> dict:
    """Hapus override satu dokumen → kembali mengikuti template global + bawaan."""
    await db[COLL].delete_one({"scope": "doc", "doc_key": doc_key})
    return await get_doc(db, doc_key)


# ═══════════════════════════════════════════════════════════════════════════════
# PROFIL PERUSAHAAN (satu pembaca)
# ═══════════════════════════════════════════════════════════════════════════════
async def company_profile(db) -> dict:
    """Profil perusahaan ternormalisasi dari `company_settings` (tahan drift skema).

    Dipindah ke sini dari `utils/pdf_common.py` supaya kop surat punya SATU pembaca
    (pdf_common kini meneruskan ke fungsi ini).
    """
    doc = await db.company_settings.find_one({"type": "general"}, {"_id": 0})
    if not doc:
        doc = await db.company_settings.find_one({}, {"_id": 0}) or {}

    def pick(*keys, default=""):
        for k in keys:
            v = doc.get(k)
            if v:
                return v
        return default

    return {
        "company_name": pick("company_name", default="CV. Dewi Aditya"),
        "address": pick("company_address", "address"),
        "phone": pick("company_phone", "phone"),
        "email": pick("company_email", "email"),
        "website": pick("company_website", "website"),
        "npwp": pick("npwp"),
        "tagline": pick("company_tagline", "tagline"),
        "logo_url": pick("company_logo_url", "logo_url"),
        "pdf_header_line1": pick("pdf_header_line1"),
        "pdf_header_line2": pick("pdf_header_line2"),
        "pdf_footer_text": pick("pdf_footer_text"),
    }


def effective_header_text(hdr: dict, profile: dict) -> dict:
    """Isi kop yang BENAR-BENAR dicetak (template dulu, profil perusahaan sebagai isi)."""
    hdr = hdr or {}
    profile = profile or {}
    use_p = hdr.get("use_company_profile", True)

    def val(key, *pkeys):
        v = str(hdr.get(key) or "").strip()
        if v:
            return v
        if use_p:
            for pk in pkeys:
                pv = str(profile.get(pk) or "").strip()
                if pv:
                    return pv
        return ""

    return {
        "company_name": val("company_name", "company_name") or "CV. Dewi Aditya",
        "address": val("address", "address"),
        "phone": val("phone", "phone"),
        "email": val("email", "email"),
        "website": val("website", "website"),
        "npwp": val("npwp", "npwp"),
        "extra_line": str(hdr.get("extra_line") or "").strip(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PENERAPAN KOLOM (show/hide + URUTAN + kolom tambahan)
# ═══════════════════════════════════════════════════════════════════════════════
def apply_columns(tpl_columns, all_keys: list, all_headers: list, rows: list):
    """Susun ulang tabel mengikuti template: tampil/tidak, URUTAN, kolom tambahan.

    Mengembalikan (headers, rows, keys_aktif). `keys_aktif` dipakai pemanggil untuk
    menghitung kolom rata-kanan & baris TOTAL — tanpa itu, mengurutkan ulang kolom
    akan membuat TOTAL muncul di kolom yang salah.

    Kolom tambahan (`custom: True`) dicetak KOSONG: itu memang gunanya — ruang
    untuk dicentang/ditulis tangan di lapangan.
    """
    if not tpl_columns:
        return list(all_headers), [list(r) for r in rows], list(all_keys)
    idx = {k: i for i, k in enumerate(all_keys)}
    headers, keys, picks = [], [], []
    for c in tpl_columns:
        if not c.get("visible", True):
            continue
        k = c.get("key")
        if k in idx:
            headers.append(c.get("label") or all_headers[idx[k]])
            keys.append(k)
            picks.append(idx[k])
        elif c.get("custom"):
            headers.append(c.get("label") or k)
            keys.append(k)
            picks.append(None)
    if not headers:      # semua disembunyikan = dokumen tanpa tabel; jangan pernah kosong
        return list(all_headers), [list(r) for r in rows], list(all_keys)
    out_rows = []
    for r in rows:
        out_rows.append([("" if p is None else (r[p] if p < len(r) else "")) for p in picks])
    return headers, out_rows, keys


def column_weights(tpl_columns, keys: list, fallback: dict | None = None) -> list:
    """Bobot lebar kolom: dari template bila >0, kalau tidak dari bobot bawaan kode."""
    fallback = fallback or {}
    by_key = {c.get("key"): c for c in (tpl_columns or [])}
    out = []
    for k in keys:
        w = float((by_key.get(k) or {}).get("width") or 0)
        out.append(w if w > 0 else float(fallback.get(k, 1)))
    return out


def right_col_indexes(keys: list, tpl_columns=None, numeric_keys=()) -> list:
    """Index kolom rata-kanan: dari setelan align template, atau dari daftar kunci angka."""
    by_key = {c.get("key"): c for c in (tpl_columns or [])}
    out = []
    for i, k in enumerate(keys):
        al = (by_key.get(k) or {}).get("align")
        if al == "right" or (al in (None, "left") and k in set(numeric_keys) and not al):
            if al == "right" or k in set(numeric_keys):
                out.append(i)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# PENGGAMBAR (reportlab) — dipakai generator PDF dan pratinjau
# ═══════════════════════════════════════════════════════════════════════════════
def _esc(v) -> str:
    return (str(v if v is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _logo_flowable(logo_data: str, height_mm: float):
    """Logo dari data URI base64 → Image reportlab dengan rasio terjaga."""
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image
    if not logo_data or "," not in logo_data:
        return None
    try:
        raw = base64.b64decode(logo_data.split(",", 1)[1])
        bio = io.BytesIO(raw)
        iw, ih = ImageReader(bio).getSize()
        h = float(height_mm or 16) * mm
        w = h * (iw / ih if ih else 1)
        bio.seek(0)
        return Image(bio, width=w, height=h)
    except Exception as e:  # noqa: BLE001
        # Logo rusak TIDAK boleh menggagalkan dokumen (surat jalan harus tetap
        # tercetak), tetapi harus tercatat supaya tahu kenapa logonya hilang.
        log.warning("[pdf-template] logo tidak bisa dipakai, kop dicetak tanpa logo: %s", e)
        return None


def header_flowables(hdr: dict, profile: dict, title: str, *, subtitle: str = "",
                     info_pairs=None, avail: float = CONTENT_W_PORTRAIT) -> list:
    """Kop surat dari template: logo + identitas PT + garis + judul (+ info)."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    hdr = _merge(DEFAULT_HEADER, hdr or {})
    if not hdr.get("show", True):
        return []
    txt = effective_header_text(hdr, profile)
    al = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}
    align = al.get(hdr.get("text_align"), TA_LEFT)

    # `leading` = 1,44 × ukuran font. BUKAN selera: kotak glyph yang diukur pymupdf
    # lebih tinggi daripada ukuran font, dan penjaga INV-F17/INV-F26 mengukur
    # PERSINGGUNGAN bbox. Kop pertama sesi #19 memakai leading 16,5 pt untuk font
    # 13,5 pt (1,22×) dan nama PT langsung BERSINGGUNGAN dengan baris alamat di
    # SEMUA dokumen — cacat yang sama persis dengan sesi #16.
    s_name = ParagraphStyle("kopName", fontSize=13.5, leading=19.5,
                            fontName="Helvetica-Bold", alignment=align)
    s_line = ParagraphStyle("kopLine", fontSize=8.5, leading=12.3, alignment=align)
    s_title = ParagraphStyle("kopTitle", fontSize=11.5, leading=16.6,
                             fontName="Helvetica-Bold",
                             alignment=al.get(hdr.get("title_align"), TA_LEFT))

    lines = [Paragraph(f"<b>{_esc(txt['company_name'])}</b>", s_name)]
    if txt["address"]:
        lines.append(Paragraph(_esc(txt["address"]), s_line))
    contact = " | ".join(x for x in [
        f"Telp: {txt['phone']}" if txt["phone"] else "",
        txt["email"], txt["website"],
        f"NPWP: {txt['npwp']}" if txt["npwp"] else "",
    ] if x)
    if contact:
        lines.append(Paragraph(_esc(contact), s_line))
    if txt["extra_line"]:
        lines.append(Paragraph(_esc(txt["extra_line"]), s_line))

    out = []
    logo = _logo_flowable(hdr.get("logo_data"), hdr.get("logo_height_mm")) \
        if hdr.get("layout") != "text-only" else None

    if logo is None:
        out.extend(lines)
    elif hdr.get("layout") == "logo-center":
        lg = Table([[logo]], colWidths=[avail])
        lg.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        out.append(lg)
        out.extend(lines)
    else:
        logo_w = min(avail * 0.28, float(hdr.get("logo_height_mm") or 16) * mm * 3.2)
        cells = ([logo, lines] if hdr.get("layout") == "logo-left" else [lines, logo])
        widths = ([logo_w, avail - logo_w] if hdr.get("layout") == "logo-left"
                  else [avail - logo_w, logo_w])
        t = Table([cells], colWidths=widths)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("ALIGN", (1, 0), (1, 0), "RIGHT" if hdr.get("layout") == "logo-right" else "LEFT"),
        ]))
        out.append(t)

    if hdr.get("show_divider", True):
        hr = Table([[""]], colWidths=[avail])
        hr.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.9,
                                colors.HexColor("#334155")),
                                ("TOPPADDING", (0, 0), (-1, -1), 2),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        out.append(Spacer(1, 1.5 * mm))
        out.append(hr)

    if hdr.get("show_title", True):
        out.append(Spacer(1, 3 * mm))
        out.append(Paragraph(f"<b>{_esc(hdr.get('title_override') or title)}</b>", s_title))
    if subtitle:
        out.append(Paragraph(_esc(subtitle), s_line))
    if info_pairs:
        out.append(Spacer(1, 2 * mm))
        out.extend(info_flowables(info_pairs, avail=avail))
    return out


def info_flowables(info_pairs, avail: float = CONTENT_W_PORTRAIT) -> list:
    """Blok info dokumen (label: nilai) 2 pasang per baris, nilai auto-wrap."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    if not info_pairs:
        return []
    k = ParagraphStyle("ik2", fontSize=8.5, leading=12.3, fontName="Helvetica-Bold")
    v = ParagraphStyle("iv2", fontSize=8.5, leading=12.3, wordWrap="LTR")
    rows, row = [], []
    for i, (label, value) in enumerate(info_pairs):
        row.extend([Paragraph(_esc(label), k),
                    Paragraph(_esc(value if value not in (None, "") else "-"), v)])
        if len(row) >= 4 or i == len(info_pairs) - 1:
            while len(row) < 4:
                row.append("")
            rows.append(row)
            row = []
    lw = max(70, avail * 0.16)
    vw = (avail - 2 * lw) / 2
    t = Table(rows, colWidths=[lw, vw, lw, vw])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [t, Spacer(1, 4 * mm)]


def signature_flowables(sig_cfg: dict, context: dict, *, avail: float = CONTENT_W_PORTRAIT) -> list:
    """Blok tanda tangan: SUBJECT di atas · ruang kosong · NAMA di bawah · catatan.

    Bentuk ini permintaan pemilik (sesi #19). Blok boleh LEBIH DARI SATU dan bila
    melebihi `per_row` akan turun ke baris berikutnya — dulu blok ke-4 hilang
    diam-diam karena generator memotong daftarnya (`[:max_cols]`).
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    sig_cfg = _merge(DEFAULT_SIGNATURES, sig_cfg or {})
    if not sig_cfg.get("show", True):
        return []
    blocks = [b for b in (sig_cfg.get("blocks") or []) if (b.get("subject") or b.get("label"))]
    if not blocks:
        return []

    per_row = int(sig_cfg.get("per_row") or 3)
    space = float(sig_cfg.get("space_mm") or 18)
    s_sub = ParagraphStyle("sgSub", fontSize=9, leading=13, alignment=TA_CENTER)
    s_name = ParagraphStyle("sgName", fontSize=9, leading=13, alignment=TA_CENTER,
                            fontName="Helvetica-Bold")
    s_note = ParagraphStyle("sgNote", fontSize=7, leading=10.1, alignment=TA_CENTER,
                            textColor=colors.HexColor("#64748b"))

    out = [Spacer(1, 8 * mm)]
    if sig_cfg.get("show_place_date") and sig_cfg.get("place"):
        from utils.waktu import now_wib
        s_pd = ParagraphStyle("sgPd", fontSize=9, leading=13)
        out.append(Paragraph(
            _esc(f"{sig_cfg['place']}, {now_wib().strftime('%d/%m/%Y')}"), s_pd))
        out.append(Spacer(1, 2 * mm))

    for start in range(0, len(blocks), per_row):
        chunk = blocks[start:start + per_row]
        n = len(chunk)
        subs, names, notes = [], [], []
        for b in chunk:
            subs.append(Paragraph(_esc(b.get("subject") or b.get("label") or ""), s_sub))
            nm = resolve_name(b, context or {})
            names.append(Paragraph(
                _esc(f"( {nm} )") if nm else "( ............................ )", s_name))
            notes.append(Paragraph(_esc(b.get("note") or b.get("role_label") or ""), s_note))
        col_w = [avail / max(1, per_row)] * n
        t = Table([subs, [""] * n, names, notes], colWidths=col_w)
        t.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 1), (-1, 1), space * mm / 2),
            ("BOTTOMPADDING", (0, 1), (-1, 1), space * mm / 2),
            ("TOPPADDING", (0, 3), (-1, 3), 1),
        ]))
        out.append(t)
        if start + per_row < len(blocks):
            out.append(Spacer(1, 6 * mm))
    return out


def footer_flowables(footer_cfg: dict, profile: dict | None = None) -> list:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer
    from utils.waktu import now_wib
    cfg = _merge(DEFAULT_FOOTER, footer_cfg or {})
    if not cfg.get("show", True):
        return []
    s = ParagraphStyle("ftr", fontSize=7.5, leading=10.8)
    out = [Spacer(1, 6 * mm)]
    text = cfg.get("text") or (profile or {}).get("pdf_footer_text") or ""
    if text:
        out.append(Paragraph(_esc(text), s))
    if cfg.get("show_printed_at", True):
        out.append(Paragraph(
            f"<i>Dicetak: {now_wib().strftime('%d/%m/%Y %H:%M')} WIB</i>", s))
    return out


def resolve_name(sig: dict, context: dict) -> str:
    """Nama penandatangan: 'custom' → diketik, 'field' → dari data, lain → DIKOSONGKAN."""
    src = (sig or {}).get("name_source", "blank")
    if src == "custom":
        return (sig.get("custom_name") or "").strip()
    if src == "field":
        return str((context or {}).get(sig.get("field_key", ""), "") or "").strip()
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# PRATINJAU (data CONTOH — tidak menyentuh dokumen sungguhan)
# ═══════════════════════════════════════════════════════════════════════════════
async def build_preview(db, doc_key: str, tpl: dict | None = None) -> io.BytesIO:
    """PDF pratinjau dari template yang SEDANG DIEDIT (belum tentu tersimpan)."""
    from routes.operations_pdf_helpers import _build_pdf, _pdf_data_table
    profile = await company_profile(db)
    eff = await resolve(db, doc_key)
    if tpl:
        # Lingkup DOKUMEN dikenali dari adanya bendera override. Pratinjaunya HARUS
        # menghormati bendera itu: bila "pakai kop khusus" mati, yang tercetak adalah
        # kop GLOBAL — pratinjau yang menampilkan kop dokumen (padahal tidak dipakai)
        # akan membuat pemilik menyetel sesuatu yang tidak pernah muncul di cetakan.
        lingkup_dokumen = any(k in tpl for k in
                              ("override_header", "override_signatures", "override_footer"))
        if lingkup_dokumen:
            if tpl.get("override_header"):
                eff["header"] = tpl.get("header") or eff["header"]
                eff["table"] = tpl.get("table") or eff["table"]
            if tpl.get("override_signatures"):
                eff["signatures"] = tpl.get("signatures") or eff["signatures"]
            if tpl.get("override_footer"):
                eff["footer"] = tpl.get("footer") or eff["footer"]
            if tpl.get("columns") is not None:
                eff["columns"] = tpl["columns"]
        else:
            for k in ("header", "signatures", "footer", "table", "columns"):
                if tpl.get(k) is not None:
                    eff[k] = tpl[k]
        # Template GLOBAL boleh belum punya blok tanda tangan sendiri; yang benar-benar
        # tercetak pada keadaan itu adalah blok BAWAAN dokumen (aturan `_sig_for_doc`).
        # Tanpa baris ini pratinjau global tampil TANPA tanda tangan sementara dokumen
        # sungguhan tetap mencetaknya — pratinjau yang berbohong.
        if isinstance(eff.get("signatures"), dict) and not (eff["signatures"].get("blocks")):
            eff["signatures"] = {**eff["signatures"], "blocks": default_signatures(doc_key)}
    page = page_of(doc_key)
    avail = content_width(page)

    all_cols = columns_of(doc_key)
    all_keys = [c["key"] for c in all_cols]
    all_headers = [c["label"] for c in all_cols]
    rows = sample_rows(doc_key, all_keys, 4) if all_keys else []
    headers, rows2, keys = apply_columns(eff.get("columns"), all_keys, all_headers, rows)

    elements = header_flowables(
        eff.get("header"), profile,
        spec(doc_key).get("title", doc_key),
        info_pairs=sample_info(doc_key), avail=avail)

    if headers:
        numeric = {"qty", "amount", "price", "total_qty", "qty_sent", "harga", "cmt", "hpp",
                   "paid", "remaining", "ordered", "this_dispatch", "cumul_shipped",
                   "output_qty", "qty_progress", "defect_qty"}
        elements.append(_pdf_data_table(
            headers, rows2,
            weights=column_weights(eff.get("columns"), keys, weights_of(doc_key)),
            right_cols=[i for i, k in enumerate(keys) if k in numeric],
            page=page, style=eff.get("table")))
    else:
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph
        elements.append(Paragraph(
            "<i>Jenis dokumen ini tidak memakai tabel kolom yang bisa diatur.</i>",
            ParagraphStyle("noTbl", fontSize=8.5, leading=12.3)))

    elements.extend(signature_flowables(eff.get("signatures"), sample_context(doc_key),
                                        avail=avail))
    elements.extend(footer_flowables(eff.get("footer"), profile))
    return _build_pdf(io.BytesIO(), elements, page=page)


# ═══════════════════════════════════════════════════════════════════════════════
# MIGRASI SETELAN LAMA (sekali jalan, idempoten)
# ═══════════════════════════════════════════════════════════════════════════════
async def migrate_legacy(db, logger=None) -> dict:
    """Pindahkan `pdf_document_settings` + `pdf_export_configs` → `pdf_templates`.

    Dijalankan saat startup. IDEMPOTEN: dokumen yang sudah ada tidak ditimpa, jadi
    setelan baru pemilik tidak pernah dikembalikan paksa ke setelan lama.
    """
    lg = logger or log
    hasil = {"global": 0, "docs": 0, "columns": 0}
    try:
        if not await db[COLL].find_one({"scope": "global"}, {"_id": 1}):
            prof = await company_profile(db)
            hdr = dict(DEFAULT_HEADER)
            hdr["use_company_profile"] = True
            ftr = dict(DEFAULT_FOOTER)
            ftr["text"] = prof.get("pdf_footer_text") or ""
            await db[COLL].insert_one({
                "id": str(uuid.uuid4()), "scope": "global", "doc_key": "",
                "header": hdr, "signatures": dict(DEFAULT_SIGNATURES),
                "footer": ftr, "table": dict(DEFAULT_TABLE),
                "migrated_from": "company_settings",
                "updated_at": _now(), "updated_by": "migrasi-sesi-19",
            })
            hasil["global"] = 1

        async for old in db[LEGACY_DOC_SETTINGS].find({}, {"_id": 0}):
            dk = old.get("doc_type")
            if not dk or dk not in SUPPORTED_PDF_DOCS:
                continue
            if await db[COLL].find_one({"scope": "doc", "doc_key": dk}, {"_id": 1}):
                continue
            hdr = dict(DEFAULT_HEADER)
            hdr["company_name"] = old.get("header_line1") or ""
            hdr["address"] = old.get("header_line2") or ""
            hdr["logo_enabled"] = bool(old.get("show_logo", True))
            ftr = dict(DEFAULT_FOOTER)
            ftr["text"] = old.get("footer_text") or ""
            sig = dict(DEFAULT_SIGNATURES)
            sig["show"] = bool(old.get("show_signatures", True))
            sig["blocks"] = normalize_signature_blocks(dk, [
                {"subject": s.get("label"), "name_source": s.get("name_source"),
                 "custom_name": s.get("custom_name"), "field_key": s.get("field_key"),
                 "note": s.get("role_label")}
                for s in (old.get("signatures") or [])
            ]) or default_signatures(dk)
            punya_kop = bool(old.get("header_line1") or old.get("header_line2"))
            await db[COLL].insert_one({
                "id": str(uuid.uuid4()), "scope": "doc", "doc_key": dk,
                "override_header": punya_kop,
                "override_signatures": bool(old.get("signatures")),
                "override_footer": bool(old.get("footer_text")),
                "header": hdr, "signatures": sig, "footer": ftr,
                "table": dict(DEFAULT_TABLE),
                "columns": default_columns(dk),
                "migrated_from": LEGACY_DOC_SETTINGS,
                "updated_at": _now(), "updated_by": "migrasi-sesi-19",
            })
            hasil["docs"] += 1

        # kolom: hanya konfigurasi BAWAAN (is_default) yang punya arti otomatis —
        # konfigurasi bernama lain tetap tersimpan di koleksi lamanya sebagai arsip.
        async for cfg in db[LEGACY_EXPORT_CONFIGS].find({"is_default": True}, {"_id": 0}):
            dk = cfg.get("pdf_type")
            if not dk or dk not in SUPPORTED_PDF_DOCS or not cfg.get("columns"):
                continue
            dipilih = set(cfg["columns"])
            cols = [
                {"key": c["key"], "label": c["label"],
                 "visible": c["key"] in dipilih or bool(c.get("required")),
                 "width": 0, "align": "left", "custom": False,
                 "required": bool(c.get("required"))}
                for c in columns_of(dk)
            ]
            await db[COLL].update_one(
                {"scope": "doc", "doc_key": dk},
                {"$set": {"columns": cols, "updated_at": _now(),
                          "updated_by": "migrasi-sesi-19"},
                 "$setOnInsert": {"id": str(uuid.uuid4()), "scope": "doc", "doc_key": dk,
                                  "header": dict(DEFAULT_HEADER),
                                  "signatures": dict(DEFAULT_SIGNATURES),
                                  "footer": dict(DEFAULT_FOOTER),
                                  "table": dict(DEFAULT_TABLE),
                                  "migrated_from": LEGACY_EXPORT_CONFIGS}},
                upsert=True)
            hasil["columns"] += 1

        if any(hasil.values()):
            lg.info("[pdf-template] migrasi setelan PDF lama: %s", hasil)
        return hasil
    except Exception as e:  # noqa: BLE001
        # Migrasi TIDAK boleh menggagalkan startup: dokumen tetap tercetak dengan
        # bawaan bila migrasi gagal, tetapi kegagalannya harus terlihat.
        lg.error("[pdf-template] migrasi setelan PDF lama GAGAL: %s", e)
        return hasil


# ── Jembatan ke bentuk LAMA (`get_doc_settings`) ───────────────────────────────
async def legacy_doc_settings(db, doc_key: str) -> dict:
    """Template efektif dalam BENTUK LAMA supaya generator lama tidak perlu diubah.

    Generator yang belum dipindah ke pipeline template (mis. laporan) tetap membaca
    `show_logo/header_line1/signatures[...]`. Dengan jembatan ini mereka langsung
    ikut menghormati template baru, dan pemilik tidak perlu menunggu semua generator
    ditulis ulang untuk melihat perubahan kop suratnya.
    """
    eff = await resolve(db, doc_key)
    hdr, sig, ftr = eff["header"], eff["signatures"], eff["footer"]
    profile = await company_profile(db)
    txt = effective_header_text(hdr, profile)
    return {
        "doc_type": doc_key,
        "label": spec(doc_key).get("label", doc_key),
        "show_logo": bool(hdr.get("logo_data")) and hdr.get("layout") != "text-only",
        "show_signatures": bool(sig.get("show", True)),
        "header_line1": txt["company_name"],
        "header_line2": txt["address"],
        "footer_text": ftr.get("text") or "",
        "signatures": [
            {"key": b.get("subject", ""), "label": b.get("subject", ""),
             "name_source": b.get("name_source", "blank"),
             "custom_name": b.get("custom_name", ""),
             "field_key": b.get("field_key", ""),
             "role_label": b.get("note", "")}
            for b in (sig.get("blocks") or [])
        ],
        "_template": eff,
    }
