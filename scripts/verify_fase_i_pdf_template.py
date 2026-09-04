#!/usr/bin/env python3
"""verify_fase_i_pdf_template.py — SESI #19 (2026-08-17/18).

GATE **INV-F26** — "TEMPLATE PDF HARUS BENAR-BENAR TERCETAK, DAN CUKUP SATU PINTU."

YANG TERUKUR SEBELUM PERBAIKAN (semua bisa dibuktikan dari kode & PDF lama):
  · DUA layar mengatur satu dokumen: tab "PDF: Kolom Tabel" (`pdf_export_configs`)
    dan tab "PDF: Surat & TTD" (`pdf_document_settings`) — keluhan pemilik
    "cek ada dua halaman berbeda ui ux-nya jelas".
  · Kop tidak bisa memuat LOGO sama sekali: `show_logo` disimpan sejak P1d, tetapi
    tidak satu pun generator menggambar gambar apa pun.
  · Kolom hanya bisa DISEMBUNYIKAN (`_filter_columns` mempertahankan urutan kode),
    tidak bisa diurutkan, tidak bisa ditambah.
  · Blok tanda tangan dipotong tiga (`sig_defs[:3]`, `max_cols=3`) ⇒ blok keempat
    hilang tanpa pesan.
  · Pick List tidak punya kop (nama PT pun tidak ada) & tabelnya 174 mm dari 186 mm.

INVARIAN:
  P1  SATU PINTU: hub Pengaturan Sistem punya TEPAT SATU tab PDF, dan `mgmt-pdf`
      mengarah ke layar baru (statik — dibaca dari sumber, bukan dipercaya)
  P2  SATU KOLEKSI: `pdf_templates` punya dokumen global; setiap setelan lama
      (`pdf_document_settings`) sudah punya padanannya (migrasi tidak menyisakan yatim)
  P3  KOP DARI KONFIGURASI: nama PT + LOGO yang disetel benar-benar muncul di
      dokumen SUNGGUHAN (Surat Jalan), bukan hanya di pratinjau
  P4  KOLOM BERLAKU: urutan kolom yang disetel = urutan kolom di PDF; kolom yang
      disembunyikan HILANG; kolom tambahan MUNCUL (kosong, untuk ditulis tangan)
  P5  TANDA TANGAN: 4 blok yang disetel tercetak SEMUA (dulu blok ke-4 dipotong)
  P6  RAPI: 0 tumpang tindih (bbox pymupdf), tabel ≥97% lebar konten, tidak keluar margin
  P7  LOGO DIVALIDASI: bukan gambar / lebih dari 700 KB DITOLAK 400 dengan pesan
  P8  WARISAN TIDAK BERBOHONG: endpoint lama `/api/pdf-doc-settings/{jenis}` membaca
      template BARU (satu sumber kebenaran, bukan dua yang bisa berbeda)
  P9  PENYUNTING KOLOM TIDAK BERBOHONG: jenis yang mengaku kolomnya bisa diatur
      BENAR-BENAR melewati penerap kolom di jalur cetaknya, dan jenis yang belum
      (slip gaji A5, panduan produksi) dinyatakan terus-terangan di layar

Self-cleaning: template global & Surat Jalan dikembalikan ke keadaan semula.

Pakai:  python3 scripts/verify_fase_i_pdf_template.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

MARGIN_PT = 12 * 2.834645669
A4_W, A4_H = 595.276, 841.89
CONTENT_W_PORTRAIT = A4_W - 2 * MARGIN_PT
CONTENT_W_LANDSCAPE = A4_H - 2 * MARGIN_PT

# PNG 16×16 biru — logo uji (agar P3 bisa membuktikan gambar benar-benar tertanam).
LOGO_PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAFklEQVR4n"
            "GOQc1hPEmIY1TCqYfhqAAByJQ0QIpDAYQAAAABJRU5ErkJggg==")
NAMA_UJI = "PT UJI KOP SESI19"
DOC = "delivery-note"

PASS, FAIL = [], []


def ok(code, msg, extra=""):
    PASS.append(code)
    print(f"{G}  ✓ {code}{X} {msg}" + (f"\n         {C}{extra}{X}" if extra else ""))


def bad(code, msg, extra=""):
    FAIL.append(code)
    print(f"{R}  ✗ {code}{X} {msg}" + (f"\n         {extra}" if extra else ""))


def call(method, path, token=None, body=None, raw=False):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
            return r.status, (data if raw else json.loads(data.decode() or "{}"))
    except urllib.error.HTTPError as e:
        d = e.read()
        if raw:
            return e.code, d
        try:
            return e.code, json.loads(d or b"{}")
        except ValueError:
            return e.code, {"raw": d[:300].decode(errors="ignore")}
    except Exception as e:  # noqa: BLE001
        return 0, (str(e).encode() if raw else {"error": str(e)})


def det(d) -> str:
    if isinstance(d, bytes):
        return d[:300].decode(errors="ignore")
    return str((d or {}).get("detail") or (d or {}).get("raw") or d)[:300]


# ═══════════════════════ pengukuran PDF ═══════════════════════════════════════
def spans_of(pdf_bytes):
    import pymupdf
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = []
    imgs = 0
    for page in doc:
        imgs += len(page.get_images(full=True))
        for blk in page.get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                for sp in ln.get("spans", []):
                    if sp["text"].strip():
                        out.append({"text": sp["text"].strip(), "bbox": sp["bbox"],
                                    "page": page.number})
    return out, imgs, doc


def analyse(pdf_bytes, label, page_kind="portrait"):
    """Tumpang tindih + pemakaian lebar + luber margin — diukur dari PDF jadi."""
    spans, imgs, doc = spans_of(pdf_bytes)
    content_w = CONTENT_W_LANDSCAPE if page_kind == "landscape" else CONTENT_W_PORTRAIT
    overlaps, out_margin = [], []
    tx0 = tx1 = None
    for page in doc:
        ps = [s for s in spans if s["page"] == page.number]
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                a, b = ps[i]["bbox"], ps[j]["bbox"]
                if (a[0] < b[2] - 0.5 and b[0] < a[2] - 0.5
                        and a[1] < b[3] - 0.5 and b[1] < a[3] - 0.5):
                    overlaps.append((ps[i]["text"], ps[j]["text"]))
        for dr in page.get_drawings():
            r = dr["rect"]
            if r.width < 5:
                continue
            tx0 = r.x0 if tx0 is None else min(tx0, r.x0)
            tx1 = r.x1 if tx1 is None else max(tx1, r.x1)
        pw = page.rect.width
        for s in ps:
            if s["bbox"][0] < MARGIN_PT - 2 or s["bbox"][2] > pw - MARGIN_PT + 2:
                out_margin.append(s["text"])
    used = (tx1 - tx0) if (tx0 is not None and tx1 is not None) else 0
    return {"label": label, "spans": spans, "images": imgs, "overlaps": overlaps,
            "used": used, "content_w": content_w,
            "pct": (used / content_w * 100) if content_w else 0,
            "out_margin": out_margin,
            "texts": [s["text"] for s in spans]}


def header_order(spans, labels):
    """Urutan kolom yang BENAR-BENAR tercetak: cari label, urutkan berdasarkan X."""
    found = []
    for lb in labels:
        cand = [s for s in spans if s["text"] == lb]
        if cand:
            cand.sort(key=lambda s: (s["bbox"][1], s["bbox"][0]))
            found.append((cand[0]["bbox"][0], lb))
    found.sort()
    return [lb for _x, lb in found]


# ═══════════════════════ P1 & P2 — statik + koleksi ═══════════════════════════
def part_static(token):
    print(f"\n{B}[1] SATU PINTU & SATU KOLEKSI{X}")
    sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
    sys.path.insert(0, str(ROOT / "backend"))
    hub = (ROOT / "frontend/src/components/erp/hubs/ManagementSystemHub.jsx").read_text(encoding="utf-8")
    reg = (ROOT / "frontend/src/components/erp/moduleRegistry.js").read_text(encoding="utf-8")
    studio = ROOT / "frontend/src/components/erp/pdf/PdfTemplateStudio.jsx"
    masalah = []
    tab_pdf = [ln for ln in hub.splitlines() if "label:" in ln and "PDF" in ln]
    if len(tab_pdf) != 1:
        masalah.append(f"hub Pengaturan Sistem punya {len(tab_pdf)} tab PDF (harus 1)")
    if "PdfTemplateStudio" not in hub:
        masalah.append("hub tidak memakai layar PDF baru")
    for lama in ("PDFConfigModule", "PdfDocSettingsModule"):
        if lama in hub:
            masalah.append(f"hub masih merujuk layar lama {lama}")
    # `mgmt-pdf` harus MENGARAH ke tab hub (satu isi = satu pintu). Memasangnya
    # sebagai modul langsung membuat isi yang sama punya dua pintu (guard NAV-DUPTAB)
    # dan pemakai deep-link kehilangan tab tetangganya.
    if "'mgmt-pdf':          makeRedirect('mgmt-system-hub', 'pdf')" not in reg:
        masalah.append("moduleRegistry 'mgmt-pdf' tidak mengarah ke tab hub 'pdf'")
    for lama in ("PDFConfigModule", "PdfDocSettingsModule"):
        if f"lazy(() => import('./{lama}'))" in reg:
            masalah.append(f"moduleRegistry masih mengimpor layar lama {lama}")
    if not studio.exists():
        masalah.append("layar pdf/PdfTemplateStudio.jsx tidak ada")
    else:
        src = studio.read_text(encoding="utf-8")
        for probe in ("pdf-preview-image", "pdf-kolom-add", "pdf-ttd-add", "pdf-kop-logo-input"):
            if probe not in src:
                masalah.append(f"layar baru tidak punya kontrol '{probe}'")
    if masalah:
        bad("P1", "layar PDF belum benar-benar satu pintu", "; ".join(masalah))
    else:
        ok("P1", "SATU tab PDF di hub + layar baru (editor & pratinjau) dipakai "
                 "menu `mgmt-pdf`", "PDFConfigModule/PdfDocSettingsModule tidak dirujuk lagi")

    # ── P9: jenis yang MENGAKU kolomnya bisa diatur harus benar-benar lewat satu
    # pintu penerap kolom (`tpl_table_parts`/`apply_columns`) di jalur cetaknya, dan
    # layar HARUS menyembunyikan penyunting kolom untuk jenis yang belum. Pola yang
    # sama dengan G1 pada penomoran: setelan yang tersimpan tetapi tidak berlaku
    # lebih buruk daripada setelan yang tidak ada.
    from data.pdf_doc_registry import (COLUMNS_ENFORCED, COLUMNS_NOT_ENFORCED_REASON,
                                       PDF_COLUMN_DEFINITIONS, SUPPORTED_PDF_DOCS)
    m9 = []
    for dk, rel in COLUMNS_ENFORCED.items():
        src = (ROOT / rel).read_text(encoding="utf-8")
        if "tpl_table_parts" not in src and "apply_columns" not in src:
            m9.append(f"{dk} → {rel} tidak menerapkan kolom template")
    bertabel = [k for k in SUPPORTED_PDF_DOCS if PDF_COLUMN_DEFINITIONS.get(k)]
    belum = [k for k in bertabel
             if k not in COLUMNS_ENFORCED and k not in COLUMNS_NOT_ENFORCED_REASON]
    if belum:
        m9.append(f"jenis bertabel tanpa keterangan jujur: {belum}")
    studio_src = studio.read_text(encoding="utf-8") if studio.exists() else ""
    if "columns_enforced" not in studio_src or "pdf-kolom-locked" not in studio_src:
        m9.append("layar tidak menyembunyikan penyunting kolom untuk jenis yang belum ditegakkan")
    if "pdf-preview-caveat" not in studio_src:
        m9.append("pratinjau tidak menyatakan bahwa tata letak isi jenis khusus berbeda")
    if not m9:
        ok("P9", f"{len(COLUMNS_ENFORCED)} jenis kolomnya BENAR-BENAR diterapkan generator; "
                 f"{len(COLUMNS_NOT_ENFORCED_REASON)} jenis yang belum dinyatakan terus-terangan "
                 "di layar",
           "penyunting kolom hanya tampil untuk jenis yang menegakkannya")
    else:
        bad("P9", "penyunting kolom bisa berbohong", "; ".join(m9))

    # ── P2: satu koleksi + migrasi tanpa yatim ──
    from gr_common import db_handle
    db = db_handle()
    glob = db.pdf_templates.find_one({"scope": "global"}, {"_id": 0})
    lama = list(db.pdf_document_settings.find({}, {"_id": 0, "doc_type": 1}))
    yatim = []
    for old in lama:
        dk = old.get("doc_type")
        if dk and not db.pdf_templates.find_one({"scope": "doc", "doc_key": dk}, {"_id": 1}):
            yatim.append(dk)
    if not glob:
        bad("P2", "koleksi `pdf_templates` belum punya template GLOBAL "
                  "(migrasi startup tidak jalan)")
    elif yatim:
        bad("P2", "setelan PDF lama tidak termigrasi ⇒ dua sumber kebenaran",
            f"yatim: {yatim}")
    else:
        ok("P2", "satu koleksi `pdf_templates`: global ada & semua setelan lama termigrasi",
           f"{len(lama)} setelan lama · {db.pdf_templates.count_documents({})} dokumen template")
    return db


# ═══════════════════════ P3..P6 — dari PDF sungguhan ══════════════════════════
def part_runtime(token, db):
    print(f"\n{B}[2] TEMPLATE BENAR-BENAR TERCETAK (diukur dari PDF jadi){B}{X}")

    st, sj_list = call("GET", "/api/wms/delivery-notes?limit=1", token)
    items = (sj_list or {}).get("items") or []
    if not items:
        bad("P3", "tidak ada Surat Jalan untuk diuji — buat satu lewat Portal Gudang")
        return
    sj_id = items[0]["id"]

    # setelan uji: kop bernama khas + logo, kolom diurutkan ulang + 1 disembunyikan
    # + 1 kolom tambahan, dan 4 blok tanda tangan (dulu dipotong 3).
    urutan = [
        {"key": "no", "label": "No", "visible": True, "width": 0.6, "align": "left"},
        {"key": "qty", "label": "Qty", "visible": True, "width": 0.9, "align": "right"},
        {"key": "unit", "label": "Satuan", "visible": True, "width": 0.8, "align": "left"},
        {"key": "description", "label": "Uraian Barang", "visible": True, "width": 3.0},
        {"key": "material_code", "label": "Kode Material", "visible": True, "width": 1.2},
        {"key": "roll_no", "label": "No. Roll", "visible": True, "width": 1.2},
        {"key": "remarks", "label": "Keterangan", "visible": False},
        {"key": "cek_fisik", "label": "Cek Fisik", "visible": True, "width": 1.0,
         "custom": True},
    ]
    blok4 = [
        {"subject": "Pengirim", "name_source": "blank", "note": "Gudang"},
        {"subject": "Sopir", "name_source": "blank", "note": "Ekspedisi"},
        {"subject": "Penerima", "name_source": "blank", "note": "Penerima"},
        {"subject": "Diperiksa", "name_source": "custom",
         "custom_name": "Kepala Gudang", "note": "Supervisor"},
    ]
    st1, _ = call("PUT", f"/api/pdf-templates/{DOC}", token, {
        "override_header": True, "override_signatures": True, "override_footer": True,
        "header": {"show": True, "layout": "logo-left", "logo_data": LOGO_PNG,
                   "logo_height_mm": 14, "use_company_profile": False,
                   "company_name": NAMA_UJI, "address": "Jl. Uji Sesi 19 No. 26",
                   "phone": "0271-000000", "npwp": "01.234.567.8-901.000",
                   "show_divider": True, "show_title": True, "title_align": "center"},
        "signatures": {"show": True, "per_row": 2, "space_mm": 16, "blocks": blok4},
        "footer": {"show": True, "text": "FOOTER UJI SESI19", "show_printed_at": True},
        "columns": urutan,
    })
    if st1 != 200:
        bad("P3", f"menyimpan template uji gagal (HTTP {st1})")
        return

    st, pdf = call("GET", f"/api/wms/delivery-notes/{sj_id}/pdf", token, raw=True)
    if st != 200:
        bad("P3", f"gagal membuat PDF Surat Jalan ({st})", det(pdf))
        return
    a = analyse(pdf, "Surat Jalan (template uji)")

    # ── P3: kop + logo dari konfigurasi ──
    ada_nama = any(NAMA_UJI in t for t in a["texts"])
    ada_npwp = any("01.234.567.8-901.000" in t for t in a["texts"])
    if ada_nama and ada_npwp and a["images"] >= 1:
        ok("P3", "kop dokumen SUNGGUHAN terisi dari konfigurasi: nama PT, NPWP, dan LOGO",
           f"logo tertanam: {a['images']} gambar")
    else:
        bad("P3", "kop dokumen tidak mengikuti konfigurasi",
            f"nama={ada_nama} npwp={ada_npwp} gambar={a['images']}")

    # ── P4: urutan & tampil/tidak kolom ──
    diharapkan = ["No", "Qty", "Satuan", "Uraian Barang", "Kode Material", "No. Roll",
                  "Cek Fisik"]
    nyata = header_order(a["spans"], diharapkan + ["Keterangan"])
    masalah = []
    if "Keterangan" in nyata:
        masalah.append("kolom yang disembunyikan masih tercetak")
    if [x for x in nyata if x != "Keterangan"] != diharapkan:
        masalah.append(f"urutan kolom di PDF {nyata} ≠ setelan {diharapkan}")
    if not masalah:
        ok("P4", "urutan kolom, kolom disembunyikan, dan kolom tambahan benar-benar "
                 "berlaku di PDF", " → ".join(diharapkan))
    else:
        bad("P4", "setelan kolom tidak berlaku di PDF", "; ".join(masalah))

    # ── P5: 4 blok tanda tangan tercetak semua ──
    subjects = [b["subject"] for b in blok4]
    hilang = [s for s in subjects if not any(s == t for t in a["texts"])]
    ada_nama_kustom = any("Kepala Gudang" in t for t in a["texts"])
    if not hilang and ada_nama_kustom:
        ok("P5", "4 blok tanda tangan tercetak semua (blok ke-4 tidak lagi dipotong)",
           " · ".join(subjects))
    else:
        bad("P5", "blok tanda tangan hilang / nama kustom tidak tercetak",
            f"hilang={hilang} nama_kustom={ada_nama_kustom}")

    # ── P6: rapi (0 tumpang tindih, lebar, margin) — SJ + Pick List + SPP ──
    docs = [a]
    st, pl = call("GET", "/api/wms/picklist?limit=1", token)
    pls = (pl or {}).get("picklists") or []
    if pls:
        st, pdf2 = call("GET", f"/api/wms/picklist/{pls[0]['picklist_id']}/pdf", token, raw=True)
        if st == 200:
            docs.append(analyse(pdf2, "Pick List"))
    st, pos = call("GET", "/api/production-pos", token)
    po_rows = pos if isinstance(pos, list) else (pos or {}).get("items", [])
    for p in po_rows[:4]:
        st, pdf3 = call("GET", f"/api/export-pdf?type=production-po&id={p['id']}", token, raw=True)
        if st == 200:
            docs.append(analyse(pdf3, f"SPP {p.get('po_number')}", "landscape"))
            break
    st, pdf4 = call("POST", "/api/pdf-templates/preview", token,
                    {"doc_key": "invoice-maklon"}, raw=True)
    if st == 200:
        docs.append(analyse(pdf4, "Pratinjau Invoice"))

    ov = [d for d in docs if d["overlaps"]]
    sempit = [d for d in docs if d["pct"] < 97]
    luber = [d for d in docs if d["out_margin"]]
    if not ov and not sempit and not luber:
        ok("P6", f"{len(docs)} dokumen: 0 tumpang tindih · tabel ≥97% lebar konten · "
                 "tidak keluar margin",
           "; ".join(f"{d['label']}: {d['pct']:.0f}%" for d in docs))
    else:
        bad("P6", "dokumen belum rapi",
            "; ".join(
                [f"{d['label']} tumpang tindih: {d['overlaps'][:2]}" for d in ov]
                + [f"{d['label']} lebar {d['pct']:.0f}%" for d in sempit]
                + [f"{d['label']} keluar margin: {d['out_margin'][:2]}" for d in luber]))

    # ── P7: validasi logo ──
    st_bad, d_bad = call("PUT", f"/api/pdf-templates/{DOC}", token,
                         {"header": {"logo_data": "bukan-gambar"}})
    # 1,3 juta karakter base64 ≈ 950 KB setelah didekode → di atas batas 700 KB.
    besar = "data:image/png;base64," + ("A" * 1_300_000)
    st_big, d_big = call("PUT", f"/api/pdf-templates/{DOC}", token,
                         {"header": {"logo_data": besar}})
    if (st_bad == 400 and "data uri" in det(d_bad).lower()
            and st_big == 400 and ("melebihi batas" in det(d_big).lower()
                                   or "tidak bisa dibaca" in det(d_big).lower())):
        ok("P7", "logo divalidasi: bukan gambar & melebihi 700 KB DITOLAK dengan pesan",
           f"bukan gambar HTTP {st_bad} · kebesaran HTTP {st_big}")
    else:
        bad("P7", "logo tidak divalidasi sebagaimana mestinya",
            f"bukan gambar {st_bad} {det(d_bad)[:80]} · besar {st_big} {det(d_big)[:80]}")

    # ── P8: endpoint warisan membaca template baru ──
    st_l, d_l = call("GET", f"/api/pdf-doc-settings/{DOC}", token)
    if st_l == 200 and (d_l or {}).get("header_line1") == NAMA_UJI:
        ok("P8", "endpoint warisan `/api/pdf-doc-settings` membaca template BARU "
                 "(satu sumber kebenaran)", f"header_line1 = {d_l.get('header_line1')}")
    else:
        bad("P8", "endpoint warisan masih punya sumber kebenaran sendiri",
            f"HTTP {st_l} header_line1={(d_l or {}).get('header_line1')}")


def cleanup(token, db):
    st, _ = call("DELETE", f"/api/pdf-templates/{DOC}", token)
    n = db.pdf_templates.count_documents({"scope": "doc", "doc_key": DOC})
    print(f"\n{Y}  bersih-bersih: override template '{DOC}' dihapus "
          f"(HTTP {st}, sisa {n} dokumen){X}")


def main():
    print(f"{C}{B}SESI #19 — template PDF satu pintu & benar-benar tercetak (INV-F26){X}")
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        print(f"{R}pymupdf belum terpasang — jalankan: pip install pymupdf{X}")
        return 2
    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}){X}")
        return 2
    db = part_static(token)
    try:
        part_runtime(token, db)
    except Exception as e:  # noqa: BLE001
        bad("RUNTIME", "invarian runtime gagal dijalankan", str(e))
    finally:
        cleanup(token, db)
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian template PDF terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
