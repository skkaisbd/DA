#!/usr/bin/env python3
"""verify_fase_f_pdf_rapi.py — FASE F (2026-08-15).

MENJAGA: dokumen PDF yang diunduh pemakai tidak boleh TUMPANG TINDIH dan tidak
boleh menyisakan setengah halaman kosong.

Keluhan pemilik (Surat Jalan Buyer kumulatif):
  "sangat buruk ada yang tumpang tindih, format tidak profesional … kenapa
   tabelnya kecil padahal margin kiri kananya masih sangat luas"

DUA SEBAB YANG TERBUKTI DARI KODE (bukan selera):
  1. Baris subtotal menulis teks `SUBTOTAL {po}` ke kolom 'Color' selebar 44 pt
     memakai `Table()` MENTAH berisi STRING (bukan `Paragraph`) ⇒ ReportLab tidak
     bisa word-wrap ⇒ teks meluber menimpa kolom angka sebelahnya.
  2. Lebar kolom hardcode berjumlah 569 pt, sedangkan lebar konten A4 landscape
     dengan margin 12 mm = 773,8 pt ⇒ tabel hanya mengisi 73% halaman.

CARA MENJAGA — DIUKUR DARI PDF SUNGGUHAN, bukan dari membaca kode:
  F-1  Tidak ada dua potongan teks yang bbox-nya beririsan (tumpang tindih).
  F-2  Tabel mengisi ≥ 97% lebar konten halaman.
  F-3  Tidak ada elemen yang keluar dari batas margin halaman.
  F-4  Dokumen kumulatif TIDAK lagi memuat baris "SUBTOTAL" (keputusan pemilik:
       rincian per pengiriman sudah punya surat jalannya sendiri).
  F-5  Sumber: tidak ada lagi lebar kolom hardcode pada dokumen surat jalan buyer.

Pakai:
    python3 scripts/verify_fase_f_pdf_rapi.py
Keluar 0 bila semua invarian HIJAU.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("API_BASE", "http://localhost:8001")
G, R, C, B, X = "\033[92m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

MARGIN_PT = 12 * 2.834645669           # 12 mm — sama dengan `_build_pdf()`
A4_W, A4_H = 595.276, 841.89
CONTENT_W_LANDSCAPE = A4_H - 2 * MARGIN_PT   # ≈ 773,8
CONTENT_W_PORTRAIT = A4_W - 2 * MARGIN_PT    # ≈ 527,2

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
        return e.code, e.read()[:400]
    except Exception as e:  # noqa: BLE001
        return 0, str(e).encode()


def analyse(pdf_bytes, label, page_kind):
    """Ukur tumpang tindih + pemakaian lebar dari PDF yang SUDAH jadi."""
    import pymupdf
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    content_w = CONTENT_W_LANDSCAPE if page_kind == "landscape" else CONTENT_W_PORTRAIT
    overlaps, table_x0, table_x1, out_of_margin, texts = [], None, None, [], []
    for page in doc:
        spans = []
        for blk in page.get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                for sp in ln.get("spans", []):
                    if sp["text"].strip():
                        spans.append((sp["bbox"], sp["text"]))
                        texts.append(sp["text"])
        for i in range(len(spans)):
            for j in range(i + 1, len(spans)):
                a, b = spans[i][0], spans[j][0]
                # toleransi 0,5 pt untuk pembulatan renderer
                if (a[0] < b[2] - 0.5 and b[0] < a[2] - 0.5
                        and a[1] < b[3] - 0.5 and b[1] < a[3] - 0.5):
                    overlaps.append((spans[i][1], spans[j][1]))
        for dr in page.get_drawings():
            r = dr["rect"]
            if r.width < 5:      # abaikan garis vertikal tipis
                continue
            table_x0 = r.x0 if table_x0 is None else min(table_x0, r.x0)
            table_x1 = r.x1 if table_x1 is None else max(table_x1, r.x1)
        pw = page.rect.width
        for bbox, txt in spans:
            if bbox[0] < MARGIN_PT - 2 or bbox[2] > pw - MARGIN_PT + 2:
                out_of_margin.append(txt)
    used = (table_x1 - table_x0) if (table_x0 is not None and table_x1 is not None) else 0
    return {
        "label": label, "overlaps": overlaps, "used": used, "content_w": content_w,
        "pct": (used / content_w * 100) if content_w else 0,
        "out_of_margin": out_of_margin, "texts": texts,
    }


def main():  # noqa: C901
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        print(f"{R}pymupdf belum terpasang — jalankan: pip install pymupdf{X}")
        return 2

    st, d = call("POST", "/api/auth/login", None,
                 {"email": "admin@garment.com", "password": "Admin@123"})
    token = (d or {}).get("token") if isinstance(d, dict) else None
    if not token:
        print(f"{R}login admin gagal ({st}){X}")
        return 2

    print(f"{B}FASE F — dokumen PDF rapi (diukur dari PDF sungguhan){X}")

    st, ships = call("GET", "/api/buyer-shipments", token)
    rows = ships if isinstance(ships, list) else (ships or {}).get("items", [])
    rows = [s for s in rows if (s.get("receiver_type") or "buyer") != "da"]
    if not rows:
        print(f"{R}  belum ada surat jalan buyer untuk diuji — jalankan dulu "
              f"scripts/seed_consolidated_buyer_shipment_demo.py{X}")
        return 3
    # utamakan surat jalan GABUNGAN (di situlah baris SUBTOTAL dulu tumpang tindih)
    rows.sort(key=lambda s: (not s.get("is_consolidated"), s.get("shipment_number", "")))
    target = rows[0]
    sid = target["id"]

    docs = []
    st, pdf = call("GET", f"/api/export-pdf?type=buyer-shipment&id={sid}", token, raw=True)
    if st != 200:
        bad("F-0", f"gagal membuat PDF kumulatif ({st})", str(pdf)[:200])
        return verdict()
    docs.append(analyse(pdf, f"kumulatif {target.get('shipment_number')}", "landscape"))
    st, pdf2 = call("GET", f"/api/export-pdf?type=buyer-shipment-dispatch"
                           f"&shipment_id={sid}&dispatch_seq=1", token, raw=True)
    if st == 200:
        docs.append(analyse(pdf2, f"dispatch #1 {target.get('shipment_number')}", "landscape"))
    # SPP (potrait/landscape lain) ikut diperiksa supaya penjaga tidak sempit
    st, pos = call("GET", "/api/production-pos", token)
    po_rows = pos if isinstance(pos, list) else (pos or {}).get("items", [])
    if po_rows:
        st, pdf3 = call("GET", f"/api/export-pdf?type=production-po&id={po_rows[0]['id']}",
                        token, raw=True)
        if st == 200:
            docs.append(analyse(pdf3, f"SPP {po_rows[0].get('po_number')}", "landscape"))

    # ── F-1 tumpang tindih ──────────────────────────────────────────────────
    with_ov = [d for d in docs if d["overlaps"]]
    if with_ov:
        ex = with_ov[0]
        bad("F-1", f"{len(with_ov)} dokumen masih TUMPANG TINDIH",
            f"{ex['label']}: " + "; ".join(f"{a!r} <-> {b!r}" for a, b in ex["overlaps"][:3]))
    else:
        ok("F-1", f"0 tumpang tindih pada {len(docs)} dokumen",
           ", ".join(d["label"] for d in docs))

    # ── F-2 pemakaian lebar ─────────────────────────────────────────────────
    narrow = [d for d in docs if d["pct"] < 97]
    if narrow:
        bad("F-2", "tabel masih menyisakan margin lebar",
            "; ".join(f"{d['label']}: {d['used']:.0f}/{d['content_w']:.0f} pt "
                      f"({d['pct']:.0f}%)" for d in narrow))
    else:
        ok("F-2", "semua tabel mengisi ≥97% lebar konten halaman",
           "; ".join(f"{d['label']}: {d['pct']:.0f}%" for d in docs))

    # ── F-3 tidak keluar margin ─────────────────────────────────────────────
    spill = [d for d in docs if d["out_of_margin"]]
    if spill:
        bad("F-3", "ada teks keluar batas margin halaman",
            "; ".join(f"{d['label']}: {d['out_of_margin'][:3]}" for d in spill))
    else:
        ok("F-3", "tidak ada teks yang keluar batas margin (12 mm)")

    # ── F-4 subtotal per PO sudah dibuang dari dokumen kumulatif ────────────
    cum = docs[0]
    subtotals = [t for t in cum["texts"] if "SUBTOTAL" in t.upper()]
    if subtotals:
        bad("F-4", "dokumen kumulatif masih memuat baris SUBTOTAL per PO",
            str(subtotals[:3]))
    elif not any("TOTAL" in t.upper() for t in cum["texts"]):
        bad("F-4", "dokumen kumulatif tidak punya baris TOTAL sama sekali")
    else:
        ok("F-4", "dokumen kumulatif: TOTAL ada, SUBTOTAL per PO sudah dibuang")

    # ── F-5 sumber: surat jalan buyer tidak boleh hardcode lebar kolom ──────
    src = Path("/app/backend/routes/operations_pdf.py").read_text()
    blocks = {}
    for name, marker in (("dispatch", "elif pdf_type == 'buyer-shipment-dispatch'"),
                         ("kumulatif", "elif pdf_type == 'buyer-shipment'")):
        i = src.find(marker)
        if i < 0:
            continue
        j = src.find("elif pdf_type ==", i + len(marker))
        blocks[name] = src[i:j if j > 0 else len(src)]
    offenders = []
    for name, blk in blocks.items():
        for m in re.finditer(r"colWidths\s*=\s*\[", blk):
            offenders.append(f"{name}: colWidths=[…] hardcode")
        if re.search(r"^\s*cw\s*=\s*\[", blk, re.M):
            offenders.append(f"{name}: cw=[…] hardcode")
    if not blocks:
        bad("F-5", "blok surat jalan buyer tidak ditemukan di operations_pdf.py")
    elif offenders:
        bad("F-5", "masih ada lebar kolom hardcode di surat jalan buyer",
            "; ".join(sorted(set(offenders))))
    else:
        ok("F-5", "surat jalan buyer memakai helper `_pdf_data_table` "
                  "(lebar proporsional + word-wrap), 0 lebar kolom hardcode")

    return verdict()


def verdict():
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian dokumen PDF terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
