#!/usr/bin/env python3
"""_audit_form_master_refs.py — UKUR cacat "form mengetik ulang apa yang sudah
punya MASTER".

═══════════════════════════════════════════════════════════════════════════════
KENAPA ALAT INI ADA
═══════════════════════════════════════════════════════════════════════════════
Temuan pemilik (2026-08-14): layar **Launching Produk** meminta staf MENGETIK
nama produk / bahan / model sebagai teks bebas — padahal produk yang diluncurkan
adalah produk **milik DA sendiri** yang sudah terdaftar di master
(`rahaza_models` + varian FG + item katalog toko).

Ini bukan soal kenyamanan mengetik. Akibatnya berantai dan MAHAL:

  1. **Master jadi kotor.** `_auto_create_fg_from_launch()` membuat FG baru dari
     TEKS yang diketik (`"Gamis Busui Friendly DA-2026 Series 1"` ⇒ kode FG
     `GAMIS-BUSUI-FRIENDLY-DA-2026-S`). Produk yang sama yang sudah ada di master
     dengan kode `GMS-0001` TIDAK dikenali ⇒ **dua barang jadi untuk satu produk**
     di master stok.
  2. **Angka tidak bisa direkonsiliasi.** Rencana peluncuran menyebut harga yang
     diketik tangan; katalog menyebut `harga_jual`; master menyebut
     `retail_price`. Tidak ada satu pun yang tahu ketiganya seharusnya sama ⇒
     "kenapa harga di toko beda dengan rencana?" tidak bisa dijawab.
  3. **Ejaan = identitas.** "Katun Linen Premium" vs "katun linen premium" vs
     "Katun Linen" adalah TIGA bahan berbeda bagi mesin. Laporan apa pun yang
     mengelompokkan per bahan/produk akan salah, dan salahnya tidak terlihat.

Karena itu pemilik minta: **verifikasi SEMUA form**, bukan hanya Launching.

═══════════════════════════════════════════════════════════════════════════════
CARA ALAT INI MENGUKUR — DAN KENAPA IA SENGAJA TIDAK GAMPANG MENUDUH
═══════════════════════════════════════════════════════════════════════════════
Pelajaran sesi #10: penjaga yang MENUDUH SALAH lebih berbahaya daripada tidak
ada penjaga — sekali ia salah tuduh, orang berhenti mempercayainya. Maka:

  · Yang dicari hanya `<Input>` / `<Textarea>` yang **terikat ke state form**
    (`value={form.X}` / `value={data.X}` / `value={f.X}`), bukan sembarang teks.
  · Kolom **pencarian/penyaring** (`search`, `filter`, `q`, `keyword`, `cari`)
    DIKECUALIKAN — mengetik bebas di kotak cari memang benar.
  · Field yang isinya memang bebas (`notes`, `description`, `alasan`, `remark`,
    `address`, …) DIKECUALIKAN lewat `FREE_TEXT_OK`.
  · Sebuah temuan **DIGUGURKAN** kalau di berkas yang sama sudah ada pemilih
    (`*Select`, `*Picker`, `Combobox`) untuk konsep itu — artinya layar sudah
    benar dan `<Input>` itu cuma pelengkap (mis. catatan varian).
  · Konsep hanya dihitung kalau MASTER-nya BENAR-BENAR ADA di produk ini
    (kolom `master` di bawah diisi nama koleksi + endpoint nyata). Kalau master
    tidak ada, mengetik bebas BUKAN cacat — itu satu-satunya cara yang mungkin.

Keluaran: `memory/AUDIT_FORM_MASTER_REFS.json` + ringkasan layar.

Pakai:  python3 /app/scripts/_audit_form_master_refs.py [--json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SRC = Path("/app/frontend/src/components")
OUT = Path("/app/memory/AUDIT_FORM_MASTER_REFS.json")
G, R, Y, X, B, C = ("\033[92m", "\033[91m", "\033[93m", "\033[0m",
                    "\033[1m", "\033[96m")

# ── Konsep yang PUNYA master di produk ini ───────────────────────────────────
# `fields`  : nama field state form (lowercase) yang berarti konsep itu
# `master`  : koleksi SSOT + endpoint pemilih yang sudah ada (BUKTI master ada)
# `pickers` : komponen pemilih yang, kalau dipakai di berkas itu, menggugurkan
#             temuan (layar sudah benar)
# `cost`    : kenapa mengetik bebas di sini MAHAL (dipakai untuk urutan kerja)
CONCEPTS = {
    "produk": {
        "fields": {"product_name", "produk", "nama_produk", "item_name",
                   "product", "nama_barang", "product_title"},
        "master": "rahaza_models + varian FG · GET /api/marketing/catalogs/master-products",
        "pickers": {"MasterProductSelect", "CatalogItemSelect", "ProductSelect",
                    "FGSelect", "ModelSelect"},
        "cost": "barang jadi kembar di master stok + harga tak bisa direkonsiliasi",
    },
    "model": {
        "fields": {"model", "model_name", "style", "style_name", "kode_model"},
        "master": "rahaza_models (kode dibuat otomatis oleh core.product_master)",
        "pickers": {"MasterProductSelect", "ModelSelect", "StyleSelect",
                    "CatalogItemSelect"},
        "cost": "kode model kembar ⇒ BOM & HPP menempel ke model yang salah",
    },
    "bahan": {
        "fields": {"material", "material_name", "bahan", "fabric", "kain",
                   "nama_bahan"},
        "master": "rahaza_materials (type≠fg) · GET /api/rahaza/materials",
        "pickers": {"MaterialSelect", "FabricSelect", "MasterProductSelect"},
        "cost": "ejaan bahan berbeda = bahan berbeda ⇒ kebutuhan kain salah hitung",
    },
    "warna": {
        "fields": {"color", "warna", "color_name", "nama_warna"},
        "master": "SSOT warna (dijaga gate INV-COLOR)",
        "pickers": {"ColorSelect", "WarnaSelect", "MasterProductSelect",
                    "CatalogItemSelect"},
        "cost": "warna di luar SSOT ⇒ SKU varian tidak terbentuk / salah",
    },
    "ukuran": {
        "fields": {"size", "ukuran", "size_code", "nama_ukuran"},
        "master": "SSOT ukuran R&D (dijaga gate INV-RND / INV-RND2)",
        "pickers": {"SizeSelect", "UkuranSelect", "MasterProductSelect",
                    "CatalogItemSelect"},
        "cost": "ukuran bebas ⇒ padanan ukuran buyer↔DA putus",
    },
    "vendor": {
        "fields": {"vendor_name", "vendor", "supplier_name", "supplier",
                   "nama_vendor", "cmt_vendor"},
        "master": "vendor_partners (SSOT disatukan F13 core.cmt_vendor_master)",
        "pickers": {"VendorSelect", "VendorPicker", "SupplierSelect",
                    "CMTVendorSelect"},
        "cost": "vendor kembar ⇒ tagihan CMT terpecah dua & pembayaran dobel",
    },
    "karyawan": {
        "fields": {"employee_name", "karyawan", "nama_karyawan", "employee",
                   "pegawai", "staff_name"},
        "master": "employees",
        "pickers": {"EmployeeSelect", "KaryawanSelect", "EmployeePicker"},
        "cost": "gaji/kasbon menempel ke nama, bukan orang ⇒ salah bayar",
    },
    "kategori": {
        "fields": {"category", "kategori", "category_name", "nama_kategori"},
        "master": "rahaza_product_categories (14 kategori + sku_prefix)",
        "pickers": {"CategorySelect", "KategoriSelect", "MasterProductSelect"},
        "cost": "kategori bebas ⇒ prefix SKU salah & laporan per kategori bocor",
    },
    "toko": {
        "fields": {"account_name", "toko", "nama_toko", "shop_name", "store"},
        "master": "marketing_accounts · MarketingAccountSelect",
        "pickers": {"MarketingAccountSelect", "AccountSelect", "TokoSelect"},
        "cost": "data masuk toko yang salah (kelas cacat yang sama dgn INV-F12)",
    },
    "kreator": {
        "fields": {"creator_name", "kreator", "nama_kreator", "host_name"},
        "master": "marketing_creators · MarketingCreatorSelect",
        "pickers": {"MarketingCreatorSelect", "MarketingHostSelect",
                    "CreatorSelect"},
        "cost": "scorecard kreator pecah per ejaan nama",
    },
}

# Field yang isinya MEMANG bebas — mengetik di sini bukan cacat.
FREE_TEXT_OK = {
    "notes", "note", "catatan", "description", "deskripsi", "keterangan",
    "remark", "remarks", "alasan", "reason", "address", "alamat", "comment",
    "komentar", "title", "judul", "subject", "message", "pesan", "url", "link",
    "email", "phone", "telepon", "hp", "npwp", "no_rek", "bank_account",
    "launch_notes", "internal_notes", "rejection_reason", "caption",
}

# ── PEMBATAS DOMAIN — supaya penjaga ini tidak MENUDUH SALAH ─────────────────
# Kata yang sama berarti benda berbeda di domain berbeda. Tanpa daftar ini,
# audit menuduh 4 layar yang sebenarnya BENAR (terbukti pada jalan pertama):
#
#   · `EmployeeExpenseGLMappingModule.category` — kategori BIAYA (Transportasi,
#     Konsumsi) untuk pemetaan GL. Bukan kategori produk, dan form ini justru
#     yang MENDEFINISIKAN kategorinya.
#   · `HRKPIModule.category`  — kategori penilaian KPI ("Tanggung Jawab").
#   · `CreateAssetDialog.model` — model ASET IT ("XPS 13 9310"), bukan model
#     garmen. Master aset tidak menyimpan daftar model laptop.
#   · `MaklonBuyerCatalogModule.product_name` — form ini ADALAH master katalog
#     buyer; produk yang sedang dibuat belum ada di master mana pun.
#
# Menuduh keempatnya bukan cuma berisik: sekali penjaga salah tuduh, orang
# berhenti mempercayainya — dan penjaga yang tidak dipercaya sama dengan tidak
# ada penjaga (pelajaran sesi #10).
DOMAIN_DENY = {
    # konsep → potongan nama berkas yang BERADA DI LUAR domain konsep itu
    "kategori": ("Expense", "GLMapping", "HRKPI", "Payroll", "Kasbon", "Leave",
                 "Asset", "Aset", "Ticket", "Task", "Document", "Training"),
    "model":    ("Asset", "Aset", "Device", "Vehicle", "Kendaraan"),
    "bahan":    ("Asset", "Aset"),
    "warna":    ("Asset", "Aset", "Theme", "Setting"),
    "ukuran":   ("Asset", "Aset", "File", "Paper", "Page"),
    "produk":   (),
    "vendor":   (),
    "karyawan": (),
    "toko":     (),
    "kreator":  (),
}

# Form yang MEMBUAT masternya sendiri — di sini teks bebas adalah satu-satunya
# cara yang mungkin. Menuntut pemilih di form pembuat master = meminta orang
# memilih benda yang justru sedang ia buat.
MASTER_OWN_FORM = {
    "MaklonBuyerCatalogModule.jsx": "master katalog produk buyer (dewi_maklon_buyer_catalog)",
    "MasterProductModule.jsx":      "master produk internal (rahaza_models)",
    "RnDStylesTab.jsx":             "master style R&D (dewi_rnd_styles)",
    "ProductCategoriesModule.jsx":  "master kategori produk (rahaza_product_categories)",
    "MaterialMasterModule.jsx":     "master bahan (rahaza_materials)",
    "VendorPartnersModule.jsx":     "master vendor (vendor_partners)",
    "EmployeeMasterModule.jsx":     "master karyawan (employees)",
}

# Konteks pencarian / penyaring — mengetik bebas memang benar.
SEARCH_HINT = re.compile(
    r"search|filter|\bq\b|keyword|cari|query|lookup", re.I)

# `<Input ... value={form.field}` (atau Textarea) — terikat ke state form.
BIND_RE = re.compile(
    r"<(Input|Textarea)\b(?P<attrs>[^>]*?)value=\{\s*(?P<obj>[A-Za-z_$][\w$]*)"
    r"\.(?P<field>[A-Za-z_$][\w$]*)",
    re.S)
# state form yang lazim di produk ini
FORM_OBJECTS = {"form", "formData", "data", "f", "draft", "values", "payload",
                "newItem", "editForm", "item", "row", "state"}


def field_concept(field: str) -> str | None:
    fl = field.lower()
    if fl in FREE_TEXT_OK:
        return None
    for name, meta in CONCEPTS.items():
        if fl in meta["fields"]:
            return name
    return None


# Objek yang BUKAN sumber auto-fill sah: state form itu sendiri (menyalin dari
# diri sendiri bukan auto-fill), pembungkus setState yang lazim, dan objek
# EVENT — `product_name: e.target.value` adalah KETIKAN, bukan auto-fill.
# (Jebakan nyata: tanpa `e`/`ev`/`event` di daftar ini, audit melaporkan 0
# temuan padahal semua kotak ketik masih utuh.)
_SELF_OBJS = FORM_OBJECTS | {"prev", "p", "f", "cur", "current", "old", "s",
                             "e", "ev", "event", "evt"}


def _autofilled_from_picker(src: str, field: str) -> bool:
    """True kalau `field` diisi dari objek HASIL PILIHAN (bukan dari state form).

    Contoh yang dianggap SAH (layar sudah benar):
        product_name: cat.product_name          ← `cat` = item Buyer Catalog terpilih
        set('product_name', model.name)         ← `model` = master terpilih
    Contoh yang TIDAK dianggap auto-fill:
        product_name: form.product_name         ← menyalin dari diri sendiri
        product_name: prev.product_name?.trim() ← idem
        product_name: e.target.value            ← ini KETIKAN
    """
    fe = re.escape(field)
    pats = (
        rf"{fe}\s*:\s*([A-Za-z_$][\w$]*)\.(\w+)",
        rf"set\(\s*['\"]{fe}['\"]\s*,\s*([A-Za-z_$][\w$]*)\.(\w+)",
        rf"{fe}\s*:\s*[^,\n]*?\|\|\s*([A-Za-z_$][\w$]*)\.(\w+)",
    )
    for pat in pats:
        for m in re.finditer(pat, src):
            obj, prop = m.group(1), m.group(2)
            if obj in _SELF_OBJS or prop == "target":
                continue
            return True
    return False


def scan_file(path: Path) -> list[dict]:
    try:
        src = path.read_text(errors="ignore")
    except Exception:  # noqa: BLE001
        return []
    if "<Input" not in src and "<Textarea" not in src:
        return []
    # Form yang MEMBUAT masternya sendiri — dikecualikan seluruhnya.
    if path.name in MASTER_OWN_FORM:
        return []

    lines = src.splitlines()
    hits: list[dict] = []
    for m in BIND_RE.finditer(src):
        obj, field = m.group("obj"), m.group("field")
        if obj not in FORM_OBJECTS:
            continue
        concept = field_concept(field)
        if not concept:
            continue
        # Domain berbeda ⇒ kata yang sama bukan konsep yang sama.
        if any(tok.lower() in path.name.lower()
               for tok in DOMAIN_DENY.get(concept, ())):
            continue
        attrs = m.group("attrs") or ""
        # kotak cari / penyaring: dikecualikan
        if SEARCH_HINT.search(attrs) or SEARCH_HINT.search(field):
            continue
        # readOnly / disabled = tampilan, bukan input
        if "readOnly" in attrs or "readonly" in attrs:
            continue
        # CATATAN (aturan yang sempat SALAH): versi pertama menggugurkan temuan
        # begitu berkas itu memakai pemilih apa pun untuk konsep tersebut.
        # Terbukti terlalu longgar — satu berkas bisa punya pemilih DAN kotak
        # ketik untuk field yang sama sekaligus, dan justru itulah bentuk cacat
        # yang paling mudah lolos (pemilih terpasang, kotak ketik lupa dibuang).
        # Yang benar: temuan hanya gugur kalau field itu memang DIISI dari hasil
        # pilihan (lihat `_autofilled_from_picker`).
        # Field DIISI OTOMATIS dari pemilih lain di berkas yang sama (mis.
        # `product_name: cat.product_name` sesudah memilih Buyer Catalog) ⇒
        # `<Input>` itu hanya penimpa opsional, bukan sumber identitas.
        #
        # HATI-HATI (jebakan yang sempat membuat audit ini melaporkan 0 temuan
        # PADAHAL cacatnya masih ada): `product_name: form.product_name` juga
        # cocok dengan pola "diisi dari objek lain". Padahal `form`/`prev` ADALAH
        # state form itu sendiri — menyalin dari diri sendiri bukan auto-fill.
        # Karena itu sumbernya wajib objek DI LUAR state form.
        if _autofilled_from_picker(src, field):
            continue
        line_no = src[: m.start()].count("\n") + 1
        hits.append({
            "file": str(path.relative_to(SRC.parent.parent)),
            "line": line_no,
            "field": field,
            "concept": concept,
            "master": CONCEPTS[concept]["master"],
            "cost": CONCEPTS[concept]["cost"],
            "snippet": lines[line_no - 1].strip()[:140] if line_no <= len(lines) else "",
        })
    return hits


def main() -> int:
    files = sorted(SRC.rglob("*.jsx"))
    all_hits: list[dict] = []
    for f in files:
        if "/ui/" in str(f):          # komponen shadcn generik, bukan form produk
            continue
        all_hits.extend(scan_file(f))

    by_file: dict[str, list[dict]] = {}
    for h in all_hits:
        by_file.setdefault(h["file"], []).append(h)
    by_concept: dict[str, int] = {}
    for h in all_hits:
        by_concept[h["concept"]] = by_concept.get(h["concept"], 0) + 1

    report = {
        "scanned_files": len(files),
        "total_findings": len(all_hits),
        "files_affected": len(by_file),
        "by_concept": by_concept,
        "findings": all_hits,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print(f"{B}══ AUDIT: form mengetik ulang apa yang sudah punya MASTER ══{X}")
    print(f"  berkas dipindai : {len(files)}")
    print(f"  temuan          : {B}{len(all_hits)}{X} di {len(by_file)} layar")
    print(f"\n{B}Per konsep{X}")
    for k, v in sorted(by_concept.items(), key=lambda kv: -kv[1]):
        print(f"  {R if v else G}{v:3d}{X}  {k:10s} — {CONCEPTS[k]['cost']}")
    print(f"\n{B}Per layar (urut terbanyak){X}")
    for fname, hs in sorted(by_file.items(), key=lambda kv: -len(kv[1])):
        concepts = ", ".join(sorted({h["concept"] for h in hs}))
        print(f"  {Y}{len(hs):2d}{X}  {Path(fname).name:44s} [{concepts}]")
        for h in hs:
            print(f"        {C}L{h['line']:<5d}{X} {h['field']:16s} {h['snippet'][:80]}")
    print(f"\n  laporan: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
