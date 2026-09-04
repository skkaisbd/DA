#!/usr/bin/env python3
"""verify_fase_h7_h8_surat_jalan.py — FASE H-7 & H-8 (2026-08-16).

Permintaan pemilik: *"satukan surat jalan vendor, buyer, dan gudang jadi satu daftar
cetak yang rapi"* + *"arahkan empat pintu lama Kirim CMT supaya tidak ada layar kosong"*.

YANG TERUKUR SEBELUM PERBAIKAN:
  · Layar "Surat Jalan" (Portal Gudang) HANYA membaca `wh_delivery_notes` — 2 dokumen,
    keduanya DEMO. Surat jalan yang benar-benar dipakai hidup di `vendor_shipments` (4)
    dan `buyer_shipments`/`buyer_shipment_items` (8 pengiriman), masing-masing dengan PDF
    sendiri di `operations_pdf.py` ⇒ pertanyaan "surat jalan apa saja yang keluar?" butuh
    membuka TIGA layar di DUA portal.
  · Empat alias (`cmt-progress`, `do-management`, `prod-cmt-packing`, `maklon-packing`)
    diarahkan ke `wms-cmt-dispatches` yang koleksinya (`wh_cmt_dispatches`) 0 dokumen —
    empat pintu yang selalu berujung layar kosong.

INVARIAN:
  S1  daftar lintas sumber memuat SELURUH dokumen ketiga sumber (tidak ada yang hilang)
  S2  tiap baris mengunduh PDF RESMI dari sumbernya (200 + magic %PDF) — bukan PDF baru
  S3  filter sumber / kata kunci / rentang tanggal benar-benar menyaring
  S4  dispatch buyer dipecah per PENGIRIMAN (bukan per PO) — dokumen ke-2 tidak tersembunyi
  S5  rekap PDF rapi: 0 tumpang tindih, tabel ≥97% lebar konten, tidak keluar margin
  S6  lapisan agregasi READ-ONLY: tidak menambah dokumen/nomor apa pun
  S7  empat alias lama TIDAK lagi menunjuk modul berkoleksi kosong
  S8  tujuan alias = modul yang datanya BERISI (anti "layar kosong" datang lagi)

Pakai:  python3 scripts/verify_fase_h7_h8_surat_jalan.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(ROOT / "backend"))
from gr_common import db_handle

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

MARGIN_PT = 12 * 2.834645669
A4_W, A4_H = 595.276, 841.89
CONTENT_W_LANDSCAPE = A4_H - 2 * MARGIN_PT

REGISTRY = ROOT / "frontend/src/components/erp/moduleRegistry.js"
DEAD_ALIASES = ["cmt-progress", "do-management", "prod-cmt-packing", "maklon-packing"]
# modul → koleksi yang membuktikan modul itu punya pekerjaan nyata
MODULE_DATA = {
    "prod-shipments-vendor": "vendor_shipments",
    "da-cmt-receive": "cmt_receipts",
    "cmt-monitor": "production_pos",
    "prod-shipments-buyer": "buyer_shipments",
}
EMPTY_MODULES = {"wms-cmt-dispatches": "wh_cmt_dispatches"}

PASS, FAIL = [], []


def ok(code, msg, extra=""):
    PASS.append(code)
    print(f"{G}  ✓ {code}{X} {msg}" + (f"\n         {C}{extra}{X}" if extra else ""))


def bad(code, msg, extra=""):
    FAIL.append(code)
    print(f"{R}  ✗ {code}{X} {msg}" + (f"\n         {extra}" if extra else ""))


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
        return e.code, (d if raw else (json.loads(d or b"{}") if d[:1] == b"{" else {"raw": d[:200].decode(errors="ignore")}))
    except Exception as e:  # noqa: BLE001
        return 0, ({"error": str(e)} if not raw else str(e).encode())


def part_h7(db, token):
    print(f"\n{B}[1] SATU DAFTAR SURAT JALAN LINTAS SUMBER (H-7){X}")
    n_gudang = db.wh_delivery_notes.count_documents({})
    n_vendor = db.vendor_shipments.count_documents({})
    dispatches = {(i.get("shipment_id"), int(i.get("dispatch_seq") or 1))
                  for i in db.buyer_shipment_items.find({}, {"_id": 0, "shipment_id": 1,
                                                             "dispatch_seq": 1})}
    n_buyer = len(dispatches)

    before = {c: db[c].count_documents({}) for c in
              ("wh_delivery_notes", "vendor_shipments", "buyer_shipments", "counters")}
    st, d = call("GET", "/api/wms/delivery-notes/sources", token)
    rows = (d or {}).get("items") or []
    by = (d or {}).get("by_source") or {}
    if (st == 200 and by.get("gudang") == n_gudang and by.get("vendor") == n_vendor
            and by.get("buyer") == n_buyer and len(rows) == n_gudang + n_vendor + n_buyer):
        ok("S1", "seluruh dokumen ketiga sumber masuk satu daftar",
           f"gudang {n_gudang} + vendor CMT {n_vendor} + buyer {n_buyer} = {len(rows)} dokumen")
    else:
        bad("S1", "daftar lintas sumber tidak lengkap / ganda",
            f"HTTP {st} by_source={by} vs DB gudang={n_gudang} vendor={n_vendor} buyer={n_buyer}")

    keys = [r.get("key") for r in rows]
    if len(keys) == len(set(keys)) and all(r.get("number") for r in rows):
        ok("S4", "dispatch buyer dipecah per PENGIRIMAN (nomor unik, tidak ada baris kembar)",
           f"{n_buyer} pengiriman buyer terlihat sebagai {n_buyer} baris")
    else:
        bad("S4", "ada baris kembar / tanpa nomor di daftar lintas sumber")

    # S2 — PDF resmi tiap sumber
    tested, fails = [], []
    for src in ("gudang", "vendor", "buyer"):
        row = next((r for r in rows if r.get("source") == src), None)
        if not row:
            continue
        st2, pdf = call("GET", row["pdf_url"], token, raw=True)
        tested.append(f"{src}:{row['number']} HTTP {st2}")
        if not (st2 == 200 and isinstance(pdf, bytes) and pdf[:5] == b"%PDF-"):
            fails.append(f"{src} → HTTP {st2}")
        if row.get("pdf_alt_url"):
            st3, pdf2 = call("GET", row["pdf_alt_url"], token, raw=True)
            if not (st3 == 200 and pdf2[:5] == b"%PDF-"):
                fails.append(f"{src} (kumulatif) → HTTP {st3}")
    if tested and not fails:
        ok("S2", "tiap sumber mencetak PDF resmi dokumen aslinya", " · ".join(tested))
    else:
        bad("S2", "ada baris yang tidak bisa dicetak", f"{fails} (diuji: {tested})")

    # S3 — filter
    st4, only_buyer = call("GET", "/api/wms/delivery-notes/sources?source=buyer", token)
    st5, ranged = call("GET", "/api/wms/delivery-notes/sources?date_from=2099-01-01", token)
    kw = next((r.get("recipient") for r in rows if r.get("recipient")), "")
    st6, searched = call(
        "GET", f"/api/wms/delivery-notes/sources?q={urllib.request.quote(kw[:6])}", token)
    f_ok = (st4 == 200 and (only_buyer.get("total") == n_buyer)
            and st5 == 200 and ranged.get("total") == 0
            and st6 == 200 and 0 < (searched.get("total") or 0) <= len(rows))
    if f_ok:
        ok("S3", "filter sumber, rentang tanggal, dan pencarian benar-benar menyaring",
           f"buyer={only_buyer.get('total')} · tanggal 2099={ranged.get('total')} · "
           f"cari '{kw[:6]}'={searched.get('total')}")
    else:
        bad("S3", "filter tidak menyaring dengan benar",
            f"buyer={only_buyer.get('total')}/{n_buyer} tgl2099={ranged.get('total')} "
            f"cari={searched.get('total')}")

    # S5 — rekap PDF rapi (diukur dari PDF jadi)
    st7, pdf = call("GET", "/api/wms/delivery-notes/sources/recap-pdf", token, raw=True)
    if st7 != 200 or not isinstance(pdf, bytes) or pdf[:5] != b"%PDF-":
        bad("S5", f"rekap PDF gagal dibuat (HTTP {st7})")
    else:
        try:
            import pymupdf
            doc = pymupdf.open(stream=pdf, filetype="pdf")
            # SESI #38 — tumpang tindih diukur PER HALAMAN. Dulu seluruh halaman
            # dikumpulkan ke satu daftar, jadi begitu rekap tumbuh menjadi 2
            # halaman, baris "Dicetak: …" di puncak halaman 2 dituduh menabrak
            # nama perusahaan di puncak halaman 1 — dua teks yang tidak pernah
            # bertemu di kertas mana pun.
            all_spans, tx0, tx1, out_margin, overlaps = [], None, None, [], []
            for page in doc:
                spans = []
                for blk in page.get_text("dict")["blocks"]:
                    for ln in blk.get("lines", []):
                        for sp in ln.get("spans", []):
                            if sp["text"].strip():
                                spans.append((sp["bbox"], sp["text"]))
                for dr in page.get_drawings():
                    r = dr["rect"]
                    if r.width < 5:
                        continue
                    tx0 = r.x0 if tx0 is None else min(tx0, r.x0)
                    tx1 = r.x1 if tx1 is None else max(tx1, r.x1)
                pw = page.rect.width
                for bbox, txt in spans:
                    if bbox[0] < MARGIN_PT - 2 or bbox[2] > pw - MARGIN_PT + 2:
                        out_margin.append(txt)
                for i in range(len(spans)):
                    for j in range(i + 1, len(spans)):
                        a, b = spans[i][0], spans[j][0]
                        if (a[0] < b[2] - 0.5 and b[0] < a[2] - 0.5
                                and a[1] < b[3] - 0.5 and b[1] < a[3] - 0.5):
                            overlaps.append((spans[i][1], spans[j][1]))
                all_spans.extend(spans)
            spans = all_spans
            used = (tx1 - tx0) if (tx0 is not None and tx1 is not None) else 0
            pct = used / CONTENT_W_LANDSCAPE * 100
            if not overlaps and pct >= 97 and not out_margin:
                ok("S5", "rekap PDF rapi: 0 tumpang tindih, tabel penuh lebar halaman",
                   f"{pct:.0f}% lebar konten ({used:.0f}/{CONTENT_W_LANDSCAPE:.0f} pt), "
                   f"{len(spans)} potongan teks")
            else:
                bad("S5", "rekap PDF tidak rapi",
                    f"tumpang tindih={len(overlaps)} {overlaps[:2]} · lebar={pct:.0f}% · "
                    f"keluar margin={len(out_margin)}")
        except ImportError:
            bad("S5", "pymupdf belum terpasang — kerapian rekap tidak bisa diukur",
                "pip install pymupdf")

    after = {c: db[c].count_documents({}) for c in before}
    if after == before:
        ok("S6", "lapisan agregasi READ-ONLY — tidak menambah dokumen/nomor apa pun",
           f"{', '.join(f'{k}={v}' for k, v in after.items())}")
    else:
        bad("S6", "membaca daftar lintas sumber MENULIS sesuatu",
            f"sebelum={before} sesudah={after}")


def part_h8(db):
    print(f"\n{B}[2] EMPAT PINTU LAMA TIDAK BERUJUNG LAYAR KOSONG (H-8){X}")
    src = REGISTRY.read_text()
    targets, broken = {}, []
    for alias in DEAD_ALIASES:
        m = re.search(rf"'{re.escape(alias)}':\s*makeRedirect\('([^']+)'", src)
        if not m:
            broken.append(f"{alias}: bukan redirect / tidak ditemukan")
            continue
        targets[alias] = m.group(1)
    dead_targets = {a: t for a, t in targets.items() if t in EMPTY_MODULES}
    if not broken and not dead_targets:
        ok("S7", "empat alias tidak lagi menunjuk modul berkoleksi kosong",
           " · ".join(f"{a} → {t}" for a, t in targets.items()))
    else:
        bad("S7", "masih ada alias yang berujung layar kosong",
            f"{broken} {dead_targets}")

    unknown, empty = [], []
    for alias, t in targets.items():
        if f"'{t}':" not in src:
            unknown.append(f"{alias} → {t} (tidak terdaftar di registry)")
            continue
        coll = MODULE_DATA.get(t)
        if coll and db[coll].count_documents({}) == 0:
            empty.append(f"{alias} → {t} ({coll} kosong)")
    if not unknown and not empty:
        ok("S8", "tujuan tiap alias adalah modul yang datanya BERISI",
           " · ".join(f"{t}:{MODULE_DATA.get(t, '?')}="
                      f"{db[MODULE_DATA[t]].count_documents({}) if MODULE_DATA.get(t) else '-'}"
                      for t in dict.fromkeys(targets.values())))
    else:
        bad("S8", "alias diarahkan ke modul yang tak punya data / tak terdaftar",
            f"{unknown} {empty}")


def main():
    print(f"{C}{B}FASE H-7 & H-8 — satu daftar surat jalan + pintu lama tanpa layar kosong{X}")
    db = db_handle()
    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token") if isinstance(d, dict) else None
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}){X}")
        return 2
    part_h7(db, token)
    part_h8(db)
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian surat jalan & pintu menu terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
