#!/usr/bin/env python3
"""verify_tabel_stok_dan_ekspor_kolom.py — SESI #29 (permintaan pemilik W1 & W2).

GATE **INV-F32** — "TABEL STOK HARUS BISA DIBACA MANUSIA, DAN PEMAKAI YANG
MENCETAK HARUS BISA MEMILIH KOLOMNYA."

═══════════════════════════════════════════════════════════════════════════════
YANG TERUKUR SEBELUM PERBAIKAN (2026-08-19, data hidup)
═══════════════════════════════════════════════════════════════════════════════
W1 — layar "Stok & Akurasi":
  · Tab pertama (Viewer Stok Unified) menampilkan **kolom pertama = `material_id`
    (UUID)** dan mengekspornya ke CSV. Pemilik: *"material id seharusnya tidak
    perlu ada di table ini"*.
  · Tidak ada kolom **Kategori · Warna · Opsi** padahal ketiganya SUDAH tersimpan
    di master barang (hasil SSOT varian sesi #28) ⇒ orang tidak bisa menjawab
    "stok warna Hitam ukuran XL pakai karet berapa?" tanpa membaca kode SKU.
  · Layar menampilkan **BARIS STOK**, bukan daftar master: hanya **26 baris stok**
    untuk **321 barang jadi** ⇒ tampak "tidak sinkron" dengan Master Item.

W2 — ekspor PDF:
  · Kolom **Serial No** SUDAH terdaftar di SSOT `data/pdf_doc_registry`, tetapi
    satu-satunya cara memilih kolom adalah lewat layar SETELAN (template/konfig
    bernama) ⇒ pemakai yang sedang mencetak tidak punya pintu.
  · Lebih buruk: laporan produksi memfilter kolom DUA KALI (inline
    `_filter_columns` + `tpl_table_parts`) sehingga memakai konfigurasi kolom
    justru **menggagalkan cetakan (500 "list index out of range")**.

INVARIAN YANG DIJAGA
--------------------
  T1  API stok mengirim identitas barang dari MASTER (kode, kategori, warna, opsi,
      ukuran) — bukan hanya id & nama
  T2  `include_zero=1` menampilkan barang master yang belum punya baris stok
      (jumlahnya ≥ jumlah master aktif) sehingga bisa disamakan dengan Master Item
  T3  Viewer Unified diperkaya master + punya `facets` (pilihan filter kategori/
      warna/opsi yang benar-benar ada di data)
  T4  Filter kategori/warna/opsi BEKERJA (hasilnya benar-benar tersaring)
  T5  LAYAR tidak lagi menampilkan `material_id`, dan CSV-nya memakai KODE barang
      (header 'Kode Barang', bukan 'Material ID')
  T6  Kolom Kategori/Warna/Opsi + filter + saklar "tampilkan stok 0" ADA di kedua
      layar stok (Viewer Unified & Stok/Pergerakan)
  T7  Katalog kolom PDF memuat kolom SERIAL untuk dokumen produksi & maklon
  T8  `?cols=` benar-benar mengubah PDF: kolom yang tidak dicentang HILANG dan
      yang dicentang TETAP ada (diukur dari teks PDF jadi, bukan dari niat)
  T9  Kolom WAJIB tetap tercetak walau tidak dicentang; kunci karangan diabaikan
      (tidak 500) ⇒ tautan lama/typo tidak menggagalkan cetakan
  T10 Pintunya ADA di layar: `PdfColumnPicker` terpasang di Laporan Produksi &
      SPP Produksi/Maklon
  T11 Tidak ada penyaringan kolom GANDA di generator PDF (akar 500 lama)

Gate ini **hanya membaca** (GET) — tidak menulis satu dokumen pun.

Pakai:  python3 scripts/verify_tabel_stok_dan_ekspor_kolom.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
PASS: list = []
FAIL: list = []

FE_VIEWER = ROOT / "frontend/src/components/erp/UnifiedInventoryModule.jsx"
FE_STOCK = ROOT / "frontend/src/components/erp/RahazaStockModule.jsx"
FE_PICKER = ROOT / "frontend/src/components/erp/pdf/PdfColumnPicker.jsx"
FE_REPORTS = ROOT / "frontend/src/components/erp/ReportsModule.jsx"
FE_SPP = ROOT / "frontend/src/components/erp/engine/ProductionPOModule.jsx"
BE_PDF = ROOT / "backend/routes/operations_pdf.py"


def ok(code, msg, detail=""):
    PASS.append(code)
    print(f"  {G}✓{X} {code} — {msg}" + (f" · {detail}" if detail else ""))


def bad(code, msg, detail=""):
    FAIL.append(code)
    print(f"  {R}✗ {code} — {msg}{X}" + (f" · {detail}" if detail else ""))


def head(t):
    print(f"\n{C}{B}{t}{X}")


def call(method, path, token=None, body=None, raw=False):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
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


def pdf_text(raw: bytes) -> str:
    import pymupdf
    doc = pymupdf.open(stream=raw, filetype="pdf")
    return "\n".join(p.get_text() for p in doc)


# ═════════════════════════════════════════════════════════════════════════════
def t1_t2_stok(token):
    head("T1/T2 — API stok membawa identitas barang & bisa disamakan dengan master")
    st, rows = call("GET", "/api/rahaza/material-stock?type=fg", token)
    if st != 200 or not isinstance(rows, list) or not rows:
        bad("T1", "TIDAK TERUKUR: daftar stok FG tidak terbaca", f"HTTP {st}")
        return
    need = ("material_code", "category_name", "color_name", "option_name", "size_code")
    miss = [k for k in need if k not in rows[0]]
    if miss:
        bad("T1", "baris stok belum membawa identitas barang dari master", str(miss))
    else:
        withcat = sum(1 for r in rows if (r.get("category_name") or "").strip())
        ok("T1", "baris stok membawa kode·kategori·warna·opsi·ukuran dari MASTER",
           f"{len(rows)} baris FG · {withcat} punya kategori")

    st2, rows2 = call("GET", "/api/rahaza/material-stock?type=fg&include_zero=1", token)
    if st2 != 200 or not isinstance(rows2, list):
        bad("T2", "saklar include_zero gagal", f"HTTP {st2}")
        return
    zero = [r for r in rows2 if r.get("no_stock_row")]
    if len(rows2) > len(rows) and zero:
        ok("T2", "barang master yang belum punya baris stok ikut tampil (qty 0)",
           f"{len(rows)} baris stok → {len(rows2)} baris (termasuk {len(zero)} tanpa baris stok)")
    else:
        bad("T2", "daftar tidak bisa disamakan dengan Master Item Produk Jadi",
            f"{len(rows)} → {len(rows2)} baris, tanpa baris stok={len(zero)}")


def t3_t4_viewer(token):
    head("T3/T4 — Viewer Unified: diperkaya master + filter benar-benar menyaring")
    st, d = call("GET", "/api/wms/stock/unified?limit=5&include_zero=1&material_type=fg", token)
    if st != 200 or not isinstance(d, dict):
        bad("T3", "viewer unified tidak terbaca", f"HTTP {st}")
        return
    items = d.get("items") or []
    facets = d.get("facets") or {}
    if not items:
        bad("T3", "TIDAK TERUKUR: viewer unified kosong")
        return
    need = ("material_code", "category_name", "color_name", "option_name", "location_code")
    miss = [k for k in need if k not in items[0]]
    if miss or not facets.get("colors"):
        bad("T3", "viewer belum diperkaya master / tidak mengirim pilihan filter",
            f"kolom hilang={miss} facets={list(facets)}")
    else:
        ok("T3", "viewer diperkaya master & mengirim pilihan filter dari data nyata",
           f"total={d.get('total')} · {len(facets.get('categories') or [])} kategori · "
           f"{len(facets.get('colors') or [])} warna · {len(facets.get('options') or [])} opsi")

    color = (facets.get("colors") or [None])[0]
    if not color:
        bad("T4", "TIDAK TERUKUR: tidak ada warna untuk diuji filternya")
        return
    q = urllib.parse.quote(color)
    st4, d4 = call("GET", f"/api/wms/stock/unified?limit=200&include_zero=1&color={q}", token)
    got = d4.get("items") or []
    wrong = [i.get("material_code") for i in got
             if (i.get("color_name") or "").strip().lower() != color.strip().lower()]
    if st4 == 200 and got and not wrong:
        ok("T4", f"filter warna '{color}' benar-benar menyaring",
           f"{d4.get('total')} baris, 0 baris salah warna")
    else:
        bad("T4", "filter warna tidak menyaring dengan benar",
            f"HTTP {st4} · {len(got)} baris · salah={wrong[:3]}")


def t5_t6_layar():
    head("T5/T6 — layar stok: tanpa UUID, ada kategori/warna/opsi + saklar stok 0")
    viewer = FE_VIEWER.read_text(encoding="utf-8")
    stock = FE_STOCK.read_text(encoding="utf-8")

    # Yang dilarang adalah MENAMPILKAN/MENGEKSPOR UUID-nya. Pemakaian internal
    # (kunci baris, data-testid, parameter API) tetap sah — karena itu polanya
    # dicocokkan sebagai SEL TABEL / HEADER CSV, bukan sembarang kemunculan kata.
    import re as _re
    shows_uuid = bool(_re.search(r"<td[^>]*>\s*\{item\.material_id\}", viewer)) \
        or "'Material ID'" in viewer or '"Material ID"' in viewer
    if shows_uuid:
        bad("T5", "layar/ekspor masih menampilkan UUID material_id")
    elif "Kode Barang" not in viewer:
        bad("T5", "ekspor/layar belum memakai KODE barang")
    else:
        ok("T5", "UUID material_id hilang dari layar & ekspor; diganti KODE barang")

    need_viewer = ["inv-filter-category", "inv-filter-color", "inv-filter-option",
                   "inv-show-zero-toggle", "Kategori", "Opsi"]
    need_stock = ["stock-show-zero-toggle", "category_name", "color_name", "option_name"]
    miss = [k for k in need_viewer if k not in viewer] + [k for k in need_stock if k not in stock]
    if miss:
        bad("T6", "kolom/filter/saklar belum lengkap di layar stok", str(miss))
    else:
        ok("T6", "kedua layar stok punya kolom kategori·warna·opsi, filternya, "
                 "dan saklar 'tampilkan stok 0'")


def t7_t11_ekspor(token):
    head("T7–T11 — pemakai bisa MEMILIH kolom yang dicetak (termasuk Serial)")
    # T7 — katalog kolom memuat serial untuk dokumen produksi & maklon
    serial_docs = {"production-po": "serial", "report-production": "no_seri",
                   "production-report": "serial", "vendor-shipment": "serial",
                   "report-progress": "serial_number"}
    missing = []
    for doc, key in serial_docs.items():
        st, d = call("GET", f"/api/pdf-export-columns?type={doc}", token)
        keys = [c.get("key") for c in (d.get("columns") or [])]
        if st != 200 or key not in keys:
            missing.append(f"{doc}:{key}")
    if missing:
        bad("T7", "katalog kolom PDF belum memuat nomor serial", str(missing))
    else:
        ok("T7", "kolom Serial tersedia sebagai PILIHAN di katalog kolom PDF",
           " · ".join(serial_docs))

    # T8 — cols= benar-benar mengubah PDF jadi
    st_all, raw_all = call("GET", "/api/export-pdf?type=production-report", token, raw=True)
    st_sel, raw_sel = call(
        "GET", "/api/export-pdf?type=production-report&cols=no,serial,product,qty",
        token, raw=True)
    if st_all != 200 or st_sel != 200:
        bad("T8", "cetak laporan produksi gagal", f"semua={st_all} pilihan={st_sel}")
    else:
        try:
            t_all, t_sel = pdf_text(raw_all), pdf_text(raw_sel)
        except Exception as e:  # noqa: BLE001
            bad("T8", "PDF tidak bisa dibaca untuk diukur", str(e))
            t_all = t_sel = ""
        if t_all and t_sel:
            if ("Vendor" in t_all and "Vendor" not in t_sel
                    and "Serial" in t_sel):
                ok("T8", "kolom yang tidak dicentang HILANG dari PDF, yang dicentang TETAP",
                   f"semua {len(raw_all)}B (ada 'Vendor') → pilihan {len(raw_sel)}B "
                   "(tanpa 'Vendor', tetap ada 'Serial')")
            else:
                bad("T8", "pilihan kolom tidak terlihat pada PDF jadi",
                    f"Vendor(all)={'Vendor' in t_all} Vendor(sel)={'Vendor' in t_sel} "
                    f"Serial(sel)={'Serial' in t_sel}")

    # T9 — kolom wajib tetap ikut; kunci karangan diabaikan
    st9, raw9 = call("GET", "/api/export-pdf?type=production-report&cols=serial", token, raw=True)
    st9b, raw9b = call(
        "GET", "/api/export-pdf?type=production-report&cols=kolom-karangan,serial",
        token, raw=True)
    if st9 == 200 and st9b == 200:
        try:
            t9 = pdf_text(raw9)
        except Exception:  # noqa: BLE001
            t9 = ""
        if "No" in t9 and "Serial" in t9:
            ok("T9", "kolom WAJIB tetap tercetak & kunci karangan diabaikan (bukan 500)",
               "cols=serial → kolom 'No' tetap ada · cols karangan tetap HTTP 200")
        else:
            bad("T9", "kolom wajib hilang saat hanya satu kolom dipilih", t9[:120])
    else:
        bad("T9", "pilihan kolom minimal/karangan menggagalkan cetakan",
            f"HTTP {st9} / {st9b}")

    # T10 — pintunya ada di layar
    picker = FE_PICKER.read_text(encoding="utf-8") if FE_PICKER.exists() else ""
    reports = FE_REPORTS.read_text(encoding="utf-8")
    spp = FE_SPP.read_text(encoding="utf-8")
    miss10 = []
    if "pdf-export-columns" not in picker or "pdf-picker-confirm" not in picker:
        miss10.append("PdfColumnPicker tidak membaca katalog kolom / tanpa tombol konfirmasi")
    if "PdfColumnPicker" not in reports or "cols=" not in reports and "cols" not in reports:
        miss10.append("Laporan Produksi belum memakai pemilih kolom")
    if "PdfColumnPicker" not in spp:
        miss10.append("SPP Produksi/Maklon belum memakai pemilih kolom")
    if miss10:
        bad("T10", "pintu pemilih kolom tidak ada di layar", "; ".join(miss10))
    else:
        ok("T10", "pemilih kolom terpasang di layar Laporan Produksi & SPP (Produksi/Maklon)")

    # T11 — tidak ada penyaringan kolom ganda (akar 500 lama)
    src = BE_PDF.read_text(encoding="utf-8")
    dbl = [ln for ln in src.splitlines() if "_filter_columns(" in ln and not ln.strip().startswith("#")]
    if dbl:
        bad("T11", "generator PDF masih menyaring kolom dua kali (sumber 500 lama)",
            f"{len(dbl)} pemanggilan tersisa")
    else:
        ok("T11", "penyaringan kolom hanya di SATU tempat (`tpl_table_parts`)",
           "konfigurasi kolom bernama & pilihan sekali-cetak tidak lagi 500")


def main():
    print(f"{C}{B}INV-F32 — TABEL STOK TERBACA & KOLOM CETAK BISA DIPILIH{X}")
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
    t1_t2_stok(token)
    t3_t4_viewer(token)
    t5_t6_layar()
    t7_t11_ekspor(token)
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian tabel stok & ekspor kolom terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
