#!/usr/bin/env python3
"""verify_surat_jalan_cmt.py — SESI #29 (permintaan pemilik W5, 2026-08-20).

GATE **INV-F33** — "BARANG JADI YANG DATANG DARI CMT HARUS PUNYA SURAT JALAN
YANG BISA DICETAK DARI LAYAR PENERIMAANNYA."

═══════════════════════════════════════════════════════════════════════════════
KEADAAN SEBELUM PERBAIKAN (terukur 2026-08-20)
═══════════════════════════════════════════════════════════════════════════════
Permintaan pemilik (verbatim): *"buatkan surat jalan CMT yang kirim ke DA,
export nya adakan saja di terima FG dari cmt"*. Diukur sebelum dikerjakan:

  · `data/pdf_doc_registry` memuat 3 jenis surat jalan (gudang, vendor material,
    dispatch buyer) — TIDAK ADA jenis untuk arah **CMT → DA**, padahal itu justru
    arah yang barangnya masuk gudang DA (`cmt_receipts` = SSOT penerimaannya).
  · Layar "Terima FG dari CMT" tidak punya satu pun tombol cetak ⇒ pengantar
    barang dari vendor tidak punya dokumen yang bisa ditandatangani.
  · `cmt_receipt_lines` TIDAK menyimpan `serial_number` ⇒ siapa pun yang membuat
    surat jalan ini WAJIB me-resolve serial dari `po_items` /
    `buyer_shipment_items`, kalau tidak kolom Serial akan selalu kosong.

INVARIAN YANG DIJAGA
--------------------
  S1  Jenis dokumen `cmt-delivery-note` ADA di katalog kolom PDF, kolom wajib
      (No · Qty Kirim) bertanda wajib, dan Serial + hasil QC tersedia sebagai
      PILIHAN (keputusan pemilik: satu dokumen, dua versi cetak)
  S2  Seri nomornya TERDAFTAR di katalog Penomoran Dokumen (pemilik bisa
      melihat & mengatur formatnya) dan berstatus "selalu otomatis" BERALASAN
  S3  PDF benar-benar tercetak dari penerimaan NYATA: memuat nomor surat jalan,
      kode penerimaan, nama vendor CMT, dan **nomor seri** hasil resolusi master
  S4  Nomornya IDEMPOTEN per penerimaan: cetak kedua memakai nomor yang SAMA
      dan tercatat di `cmt_delivery_notes` (jejak cetak bertambah)
  S5  `?cols=` benar-benar menyaring: kolom hasil QC yang tidak dicentang HILANG
      dari PDF, kolom WAJIB tetap tercetak
  S6  Input rusak dijawab 4xx, BUKAN 500 (tanpa id → 400, id karangan → 404)
  S7  PINTUNYA ADA di layar "Terima FG dari CMT": tombol per baris + pemilih
      kolom + default kolom versi kirim murni
  S8  Kop & tanda tangan MENGIKUTI konfigurasi PDF yang sudah ada (satu
      mekanisme, bukan yang kedua) — dibuktikan dari teks PDF jadi
  S9  Katalog `COLUMNS_ENFORCED` memuat jenis ini ⇒ layar template TIDAK
      berbohong soal kolom yang bisa diatur (aturan INV-F26/P9)
  S10 ALAT UKUR TIDAK MENGOTORI: dokumen surat jalan yang lahir karena gate ini
      dihapus lagi & nomor urutnya dikembalikan (aturan INV-F30 V15)

Pakai:  python3 scripts/verify_surat_jalan_cmt.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
PASS: list = []
FAIL: list = []

FE_SCREEN = ROOT / "frontend/src/components/erp/engine/DAReceiveFromCMTModule.jsx"
FE_PICKER = ROOT / "frontend/src/components/erp/pdf/PdfColumnPicker.jsx"
BE_PDF = ROOT / "backend/routes/operations_pdf.py"
BE_SSOT = ROOT / "backend/core/cmt_delivery_note.py"
DOC_KEY = "cmt-delivery-note"


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
def s1_s2_katalog(token):
    head("S1/S2 — jenis dokumen & seri nomornya terdaftar di katalog")
    st, d = call("GET", f"/api/pdf-export-columns?type={DOC_KEY}", token)
    cols = {c.get("key"): c for c in (d.get("columns") or [])}
    wajib = {k for k, c in cols.items() if c.get("required")}
    pilihan = {"serial", "qty_received", "qty_reject", "notes"}
    if st != 200 or not cols:
        bad("S1", "jenis dokumen surat jalan CMT belum ada di katalog kolom", f"HTTP {st}")
    elif wajib != {"no", "qty_sent"}:
        bad("S1", "kolom wajib surat jalan CMT tidak sebagaimana mestinya", f"wajib={wajib}")
    elif not pilihan.issubset(set(cols)):
        bad("S1", "kolom serial / hasil QC tidak tersedia sebagai pilihan",
            f"hilang={sorted(pilihan - set(cols))}")
    else:
        ok("S1", f"{len(cols)} kolom terdaftar; No & Qty Kirim wajib, Serial + hasil QC "
                 "jadi PILIHAN", " · ".join(cols))

    st2, d2 = call("GET", "/api/admin/doc-numbering", token)
    items = d2.get("items") if isinstance(d2, dict) else None
    entry = next((i for i in (items or []) if i.get("key") == "cmt_delivery_notes.dn_number"), None)
    if st2 != 200 or not entry:
        bad("S2", "seri nomor surat jalan CMT tidak ada di katalog Penomoran Dokumen",
            f"HTTP {st2}")
    elif not entry.get("auto_only") or not str(entry.get("alasan_otomatis") or "").strip():
        bad("S2", "seri nomor tidak berstatus 'selalu otomatis' beralasan",
            f"auto_only={entry.get('auto_only')}")
    else:
        ok("S2", "seri nomor terlihat & formatnya bisa diatur pemilik",
           f"format={entry.get('format')} · contoh={entry.get('contoh')}")


def s3_s5_s8_cetak(token, receipt, db):
    head("S3/S4/S5/S8 — PDF dari penerimaan NYATA, nomor idempoten, kolom menyaring")
    rid = receipt["id"]
    st, raw = call("GET", f"/api/export-pdf?type={DOC_KEY}&id={rid}", token, raw=True)
    if st != 200:
        bad("S3", "surat jalan CMT gagal dicetak", f"HTTP {st} · {raw[:160]}")
        return None
    txt = pdf_text(raw)
    dn = db.cmt_delivery_notes.find_one({"receipt_id": rid}, {"_id": 0})
    serial_expected = ""
    line = db.cmt_receipt_lines.find_one({"receipt_id": rid}, {"_id": 0})
    if line and line.get("po_item_id"):
        pi = db.po_items.find_one({"id": line["po_item_id"]}, {"_id": 0, "serial_number": 1})
        serial_expected = str((pi or {}).get("serial_number") or "").strip()
    kurang = [nama for nama, nilai in (
        ("nomor surat jalan", (dn or {}).get("dn_number", "")),
        ("kode penerimaan", receipt.get("receipt_code", "")),
        ("nama vendor CMT", receipt.get("cmt_name", "")),
    ) if nilai and nilai not in txt]
    if not dn:
        bad("S3", "surat jalan tercetak tetapi tidak tercatat di `cmt_delivery_notes`")
    elif kurang:
        bad("S3", "isi surat jalan tidak lengkap", f"tidak tercetak: {kurang}")
    elif serial_expected and serial_expected not in txt:
        bad("S3", "nomor seri tidak ter-resolve dari master",
            f"harap ada '{serial_expected}' pada PDF")
    else:
        ok("S3", "surat jalan memuat nomor SJ, kode penerimaan, vendor & nomor seri",
           f"{dn['dn_number']} · serial='{serial_expected or '(penerimaan ini tanpa serial)'}'")

    # S8 — kop & TTD mengikuti konfigurasi PDF yang sudah ada
    nama_pt = str(((db.company_settings.find_one({"type": "general"}) or {})
                   .get("company_name") or "")).strip()
    src = BE_PDF.read_text(encoding="utf-8")
    blok = src.split("elif pdf_type == 'cmt-delivery-note':", 1)[-1].split("elif pdf_type ==", 1)[0]
    pakai_ssot = all(x in blok for x in ("get_doc_settings(db, 'cmt-delivery-note')",
                                        "_pdf_header_branded", "_pdf_signature_block",
                                        "_pdf_footer_branded"))
    ttd_tercetak = "Pengirim" in txt and "Penerima" in txt
    if not pakai_ssot:
        bad("S8", "cabang PDF tidak memakai konfigurasi kop/TTD yang sudah ada")
    elif nama_pt and nama_pt not in txt:
        bad("S8", "kop surat tidak memakai profil perusahaan", f"'{nama_pt}' tidak tercetak")
    elif not ttd_tercetak:
        bad("S8", "blok tanda tangan tidak tercetak")
    else:
        ok("S8", "kop & tanda tangan mengikuti SATU konfigurasi PDF yang sudah ada",
           f"kop='{nama_pt or '(profil kosong)'}' · blok TTD Pengirim/QC/Penerima tercetak")

    # S4 — cetak kedua: nomor SAMA, jejak cetak bertambah
    st4, raw4 = call("GET", f"/api/export-pdf?type={DOC_KEY}&id={rid}", token, raw=True)
    dn2 = db.cmt_delivery_notes.find_one({"receipt_id": rid}, {"_id": 0})
    jumlah = db.cmt_delivery_notes.count_documents({"receipt_id": rid})
    if st4 == 200 and dn and dn2 and dn2["dn_number"] == dn["dn_number"] and jumlah == 1 \
            and int(dn2.get("print_count") or 0) > int(dn.get("print_count") or 0):
        ok("S4", "nomor surat jalan idempoten per penerimaan (cetak ulang tidak boros nomor)",
           f"{dn2['dn_number']} · cetak ke-{dn2.get('print_count')} · 1 dokumen")
    else:
        bad("S4", "cetak ulang menghasilkan nomor/dokumen baru",
            f"HTTP {st4} · dokumen={jumlah} · {(dn or {}).get('dn_number')} → "
            f"{(dn2 or {}).get('dn_number')}")

    # S5 — cols= menyaring
    st5, raw5 = call(
        "GET", f"/api/export-pdf?type={DOC_KEY}&id={rid}&cols=serial,sku,product", token, raw=True)
    if st5 != 200:
        bad("S5", "pilihan kolom menggagalkan cetakan", f"HTTP {st5}")
    else:
        # Diukur dari BARIS TABEL saja: catatan naratif di bawah tabel memang
        # menyebut nama kolom hasil QC, dan itu bukan bukti kolomnya tercetak.
        def tabel_saja(t):
            return "\n".join(ln for ln in t.splitlines()
                             if not ln.strip().startswith("Catatan"))
        t_all, t5 = tabel_saja(txt), tabel_saja(pdf_text(raw5))
        if "Qty Terima" in t_all and "Qty Terima" not in t5 and "Qty Kirim" in t5 and "No" in t5:
            ok("S5", "kolom hasil QC yang tidak dicentang HILANG; kolom wajib tetap tercetak",
               "cols=serial,sku,product → tanpa 'Qty Terima', tetap ada 'Qty Kirim'")
        else:
            bad("S5", "pilihan kolom tidak terlihat pada PDF jadi",
                f"QtyTerima(all)={'Qty Terima' in t_all} QtyTerima(sel)={'Qty Terima' in t5} "
                f"QtyKirim(sel)={'Qty Kirim' in t5}")
    return dn


def s6_input_rusak(token):
    head("S6 — input rusak dijawab 4xx, bukan 500")
    st_a, _ = call("GET", f"/api/export-pdf?type={DOC_KEY}", token, raw=True)
    st_b, _ = call("GET", f"/api/export-pdf?type={DOC_KEY}&id=tidak-ada-999", token, raw=True)
    if st_a == 400 and st_b == 404:
        ok("S6", "tanpa id → 400 · id karangan → 404 (tidak pernah 500)")
    else:
        bad("S6", "input rusak tidak dijawab dengan benar", f"tanpa id={st_a} · karangan={st_b}")


def s7_s9_layar():
    head("S7/S9 — pintunya ada di layar & katalog kolom tidak berbohong")
    scr = FE_SCREEN.read_text(encoding="utf-8") if FE_SCREEN.exists() else ""
    picker = FE_PICKER.read_text(encoding="utf-8") if FE_PICKER.exists() else ""
    miss = []
    for probe in ('receipt-surat-jalan-', 'PdfColumnPicker', f'docType="{DOC_KEY}"',
                  'type=cmt-delivery-note', 'SJ_DEFAULT_COLS'):
        if probe not in scr:
            miss.append(f"layar tidak punya '{probe}'")
    if "defaultKeys" not in picker:
        miss.append("pemilih kolom tidak mendukung kolom tercentang bawaan")
    if not BE_SSOT.exists() or "gen_prefixed_number" not in BE_SSOT.read_text(encoding="utf-8"):
        miss.append("SSOT core/cmt_delivery_note.py tidak memakai generator nomor race-safe")
    if miss:
        bad("S7", "pintu cetak surat jalan belum benar-benar ada di layar", "; ".join(miss))
    else:
        ok("S7", "tombol Surat Jalan ada di setiap baris penerimaan + pemilih kolom "
                 "(default = versi kirim murni)")

    from data.pdf_doc_registry import COLUMNS_ENFORCED, PDF_COLUMN_DEFINITIONS, SUPPORTED_PDF_DOCS
    m9 = []
    if DOC_KEY not in SUPPORTED_PDF_DOCS or DOC_KEY not in PDF_COLUMN_DEFINITIONS:
        m9.append("jenis dokumen belum ada di SSOT registry")
    if COLUMNS_ENFORCED.get(DOC_KEY) != "backend/routes/operations_pdf.py":
        m9.append("jenis ini tidak dinyatakan 'kolomnya ditegakkan' ⇒ layar template berbohong")
    if m9:
        bad("S9", "katalog jenis dokumen belum konsisten", "; ".join(m9))
    else:
        ok("S9", "jenis dokumen terdaftar di SSOT & dinyatakan menegakkan kolom "
                 "(INV-F26/P9 tetap hijau)")


def s10_bersih(db, sebelum_ids, counter_sebelum, counter_key):
    head("S10 — alat ukur tidak mengotori")
    baru = [d for d in db.cmt_delivery_notes.find({}, {"_id": 0, "id": 1, "dn_number": 1})
            if d["id"] not in sebelum_ids]
    for d in baru:
        db.cmt_delivery_notes.delete_one({"id": d["id"]})
    if baru and counter_key:
        # Nomor yang dipakai gate dikembalikan supaya urutan nomor pemilik tidak
        # bolong hanya karena diukur (aturan INV-F30 V15).
        if counter_sebelum is None:
            db.counters.delete_one({"_id": counter_key})
        else:
            db.counters.update_one({"_id": counter_key}, {"$set": {"seq": counter_sebelum}})
    sisa = db.cmt_delivery_notes.count_documents({})
    if sisa == len(sebelum_ids):
        ok("S10", "artefak gate dihapus & nomor urut dikembalikan",
           f"{len(baru)} dokumen uji dihapus · {sisa} dokumen surat jalan tersisa (sama "
           "seperti sebelum gate)")
    else:
        bad("S10", "gate meninggalkan dokumen surat jalan",
            f"sebelum={len(sebelum_ids)} sesudah={sisa}")


def main():
    print(f"{C}{B}INV-F33 — SURAT JALAN CMT → DA BISA DICETAK DARI PENERIMAAN FG{X}")
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        print(f"{R}pymupdf belum terpasang — jalankan: pip install pymupdf{X}")
        return 2
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    from gr_common import db_handle
    db = db_handle()

    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}){X}")
        return 2

    s1_s2_katalog(token)
    s7_s9_layar()
    s6_input_rusak(token)

    receipt = db.cmt_receipts.find_one({}, {"_id": 0})
    if not receipt:
        bad("S3", "TIDAK TERUKUR: belum ada penerimaan FG dari CMT di basis data")
    else:
        sebelum_ids = {x["id"] for x in db.cmt_delivery_notes.find({}, {"_id": 0, "id": 1})}
        sudah_ada = db.cmt_delivery_notes.find_one({"receipt_id": receipt["id"]}, {"_id": 0})
        counter_key = counter_sebelum = None
        if not sudah_ada:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            counter_key = f"autonum:cmt_delivery_notes:dn_number:SJ-CMT/{now:%Y}/{now:%m}/"
            row = db.counters.find_one({"_id": counter_key})
            counter_sebelum = row.get("seq") if row else None
        s3_s5_s8_cetak(token, receipt, db)
        s10_bersih(db, sebelum_ids, counter_sebelum, counter_key)

    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian surat jalan CMT → DA terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
