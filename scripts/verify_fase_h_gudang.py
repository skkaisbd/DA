#!/usr/bin/env python3
"""verify_fase_h_gudang.py — FASE H-2 · H-3 · H-4/H-9 (2026-08-16).

MEMBUKTIKAN tiga keluhan pemilik tentang Portal Gudang tertutup:
  *"kirim cmt & scan gudang itu menu mati, hapus saja"* ·
  *"pengeluaran material tidak ada tombol buatnya"* ·
  *"buat barcode belum ada menunya — padahal barang harus dilabeli"*

CACAT YANG DIJAGA (semuanya terukur sebelum perbaikan):

  H-2  `RahazaMaterialIssueModule.jsx` (488 baris) TIDAK punya jalur create sama
       sekali — hanya lihat/ajukan/setujui. Satu-satunya pembuatan MI dari layar
       adalah endpoint maklon lama yang backend-nya `deprecated=True`. Gerbang
       `POST /api/rahaza/material-issues` juga hanya meloloskan role
       `admin/superadmin/owner` ⇒ **admin gudang & supervisor produksi — dua orang
       yang benar-benar mengerjakan pekerjaan ini — mendapat 403.**

  H-3  Endpoint label bahan & barang jadi ada berbulan-bulan dengan **0 pemanggil
       UI**, hanya 1 label per item (tidak bisa "cetak 50 lembar"), dan jalur FG
       membaca `rahaza_fg_matrix` yang **KOSONG (0 dokumen)** sementara barang jadi
       nyata hidup di `rahaza_materials` (`type='fg'`) ⇒ setiap permintaan label FG
       dijawab **404** untuk barang yang jelas ADA.
       Bonus yang ikut tertutup: batch label bahan memakai 3 kolom × 90 mm pada A4
       selebar 210 mm ⇒ kolom ketiga tercetak DI LUAR halaman.

  H-4  Dua pintu Gudang menunjuk koleksi kosong: `wh-scan` (antrean
       `wh_pending_movements` = 0, endpoint pengisinya tanpa pemanggil) dan
       `wms-cmt-dispatches` (`wh_cmt_dispatches` = 0, pekerjaan nyatanya di
       Portal Produksi). Menu mati mengajarkan orang bahwa "layar kosong itu
       normal" — dan itu membuat layar yang BENAR-BENAR rusak tidak dilaporkan.

INVARIAN:
  H4-1  sidebar Gudang TIDAK lagi memuat `wh-scan` & `wms-cmt-dispatches`
  H4-2  keduanya MASIH terdaftar di moduleRegistry (deep-link lama tidak mati)
  H9-1  'Roll Kain' duduk di section INBOUND (rantai kain masuk → cutting)
  H2-4  layar MI benar-benar memanggil kedua jalur create (job/BOM & manual)
  H2-5  Portal Produksi punya pintu Pengeluaran Material (kewenangan baru
        supervisor produksi bisa dipakai — dia tidak punya akses Portal Gudang)
  H2-1  admin gudang BOLEH membuat MI manual (dulu 403)
  H2-2  supervisor produksi BOLEH membuat MI manual (dulu 403)
  H2-3  pembuat bisa MENGAJUKAN MI-nya (draft → pending_approval)
  H3-1  pintu 'Buat Barcode' ada di nav Gudang DAN termap di moduleRegistry
  H3-2  cetak batch menghormati jumlah lembar (copies) + tercatat di riwayat
  H3-3  label FG bisa dicetak dari SSOT `rahaza_materials` (dulu selalu 404)
  H3-4  kode di luar master DITOLAK (barcode harus bisa discan jadi item nyata)
  H3-5  melebihi batas lembar DITOLAK (bukan PDF ribuan halaman)
  H3-6  mode 'otomatis dari produksi' menyalin qty PO apa adanya
  H3-7  geometri label: tidak ada label yang jatuh di luar halaman A4

Pakai:
    python3 scripts/verify_fase_h_gudang.py
    python3 scripts/verify_fase_h_gudang.py --keep     # sisakan data uji
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
from gr_common import db_handle  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

NAV = ROOT / "frontend/src/components/erp/portal-shell/portalNav.js"
REG = ROOT / "frontend/src/components/erp/moduleRegistry.js"
MI_JSX = ROOT / "frontend/src/components/erp/RahazaMaterialIssueModule.jsx"
MARK = "VERIFY-FASE-H"

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
            if raw:
                return r.status, r.read(), dict(r.headers)
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        payload = e.read().decode()
        if raw:
            return e.code, payload.encode(), dict(e.headers)
        try:
            return e.code, json.loads(payload or "{}")
        except json.JSONDecodeError:
            return e.code, {"raw": payload}
    except Exception as e:  # noqa: BLE001
        return (0, b"", {}) if raw else (0, {"error": str(e)})


def login(email, pwd):
    st, r = call("POST", "/api/auth/login", None, {"email": email, "password": pwd})
    return r.get("token") if st == 200 else None


def warehouse_nav(text: str) -> str:
    i = text.index("  warehouse: {")
    j = text.index("  accessories: {", i)
    return text[i:j]


def production_nav(text: str) -> str:
    i = text.index("  production: {")
    j = text.index("  cutting: {", i)
    return text[i:j]


def strip_comments(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return "\n".join(ln for ln in js.splitlines() if not ln.strip().startswith("//"))


def section_of(js: str, module_id: str) -> str:
    """Nama section (label ALL-CAPS) yang memuat sebuah pintu.

    Hanya label TANPA huruf kecil yang dihitung — label pintu ('Roll Kain') juga
    diawali huruf besar, dan menghitungnya membuat penjaga ini MENUDUH SALAH.
    """
    idx = js.find(f"id: '{module_id}'")
    if idx < 0:
        return ""
    labels = [x for x in re.findall(r"label: '([^']*)'", js[:idx])
              if x and not any(ch.islower() for ch in x)]
    return labels[-1] if labels else ""


# ══════════════════════════════════════════════════════════════════════════════
# BAGIAN 1 — STATIK (layar & navigasi)
# ══════════════════════════════════════════════════════════════════════════════

def part_static():
    print(f"\n{B}[1] NAVIGASI & PINTU MASUK LAYAR{X}")
    nav_raw = NAV.read_text()
    nav = strip_comments(nav_raw)
    wh = warehouse_nav(nav)
    reg = REG.read_text()

    dead = [m for m in ("wh-scan", "wms-cmt-dispatches") if f"id: '{m}'" in wh]
    if dead:
        bad("H4-1", f"pintu mati masih ada di sidebar Gudang: {dead}",
            "keduanya menunjuk koleksi 0 dokumen; pekerjaan nyata 'Kirim CMT' ada "
            "di Portal Produksi (prod-shipments-vendor)")
    else:
        ok("H4-1", "sidebar Gudang bersih dari 'Scan Gudang' & 'Kirim CMT'")

    missing = [m for m in ("wh-scan", "wms-cmt-dispatches") if f"'{m}'" not in reg]
    if missing:
        bad("H4-2", f"moduleId dihapus dari registry ⇒ deep-link lama MATI: {missing}",
            "aturan IA: pintu boleh dilepas dari sidebar, id-nya TIDAK boleh hilang")
    else:
        ok("H4-2", "deep-link lama tetap hidup (id masih termap di moduleRegistry)")

    sec = section_of(wh, "wms-fabric-rolls")
    if "INBOUND" in sec:
        ok("H9-1", f"'Roll Kain' duduk di section {sec!r}")
    else:
        bad("H9-1", f"'Roll Kain' masih di section {sec!r} — bukan rantai inbound kain")

    mi = MI_JSX.read_text()
    has_job = "material-issues/draft-from-job" in mi
    has_manual = re.search(r"fetch\('/api/rahaza/material-issues',\s*\{\s*\n?\s*method:\s*'POST'", mi) \
        or "'/api/rahaza/material-issues'" in mi and "method: 'POST'" in mi
    has_btn = 'data-testid="mi-create-btn"' in mi
    if has_job and has_manual and has_btn:
        ok("H2-4", "layar MI punya tombol BUAT + dua jalur create (job/BOM & manual master)")
    else:
        bad("H2-4", "jalur create MI belum lengkap di layar",
            f"draft-from-job={bool(has_job)} manual={bool(has_manual)} tombol={has_btn}")

    prod = production_nav(nav)
    if "id: 'wh-material-issue'" in prod:
        ok("H2-5", "Portal Produksi punya pintu Pengeluaran Material",
           "tanpa ini kewenangan baru supervisor produksi tidak bisa dipakai dari layar")
    else:
        bad("H2-5", "supervisor produksi tidak punya pintu MI di portal mana pun")

    # H2-6 — regresi NYATA yang ditemukan penguji UI setelah H-2 dipasang:
    # begitu satu modul punya pintu di DUA portal, `findPortalForModule` yang
    # mengembalikan portal PERTAMA membuat `?module=wh-material-issue` bagi admin
    # gudang mendarat di Portal Produksi (tidak ia punyai) ⇒ dibuang ke "Pilih
    # Portal" tanpa pesan. Selama masih ada modul lintas-portal, penyelesaian
    # tautan WAJIB menyaring dengan hak akses.
    ids_per_portal = {}
    for pid, blk in re.findall(r"\n  ([a-z_]+): \{\n    title:(.*?)(?=\n  [a-z_]+: \{\n    title:|\Z)",
                               nav, flags=re.S):
        ids_per_portal[pid] = set(re.findall(r"id: '([a-z0-9-]+)'", blk))
    cross = sorted({m for a in ids_per_portal for m in ids_per_portal[a]
                    if sum(1 for b in ids_per_portal if m in ids_per_portal[b]) > 1})
    app_js = (ROOT / "frontend/src/App.js").read_text()
    guarded = "owners.find((p) => canAccessPortal(role, p))" in app_js
    if not cross:
        ok("H2-6", "tidak ada modul lintas-portal — penyelesaian tautan tidak ambigu")
    elif guarded:
        ok("H2-6", f"{len(cross)} modul lintas-portal diselesaikan lewat penyaringan hak akses",
           f"{', '.join(cross[:6])}")
    else:
        bad("H2-6", f"modul lintas-portal ({', '.join(cross[:6])}) tetapi findPortalForModule "
                    "memilih portal PERTAMA",
            "tautan `?module=` / `#modul` akan membuang pemakai ke portal yang tidak "
            "ia punyai tanpa satu pun pesan")

    if "id: 'wh-barcode'" in wh and "'wh-barcode'" in reg:
        ok("H3-1", "pintu 'Buat Barcode' hadir di nav Gudang dan termap di registry")
    else:
        bad("H3-1", "pintu 'Buat Barcode' belum lengkap",
            f"nav={'id: ' + chr(39) + 'wh-barcode' + chr(39) in wh} registry={chr(39)}wh-barcode{chr(39)} in reg")


def part_geometry():
    print(f"\n{B}[2] GEOMETRI LABEL (tidak boleh ada label keluar halaman){X}")
    try:
        from core import label_render as lr  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        bad("H3-7", f"core/label_render.py tidak bisa diimpor: {e}")
        return
    page_w, page_h = lr.A4
    detail = []
    broken = []
    for kind in ("material", "fg"):
        lw_mm, lh_mm = lr.label_size(kind)
        lw, lh = lw_mm * lr.mm, lh_mm * lr.mm
        cols, rows, mx, my = lr.grid_geometry(page_w, page_h, lw, lh)
        detail.append(f"{kind}: {cols}×{rows} label/halaman (margin {mx / lr.mm:.1f}×{my / lr.mm:.1f} mm)")
        if mx < 0 or my < 0 or cols * lw > page_w + 0.01 or rows * lh > page_h + 0.01:
            broken.append(f"{kind}: {cols}×{rows} tidak muat di A4")
    if broken:
        bad("H3-7", "label jatuh di luar halaman", "; ".join(broken))
    else:
        ok("H3-7", "kolom/baris dihitung dari ukuran halaman — 0 label keluar kertas",
           " · ".join(detail))


# ══════════════════════════════════════════════════════════════════════════════
# BAGIAN 3 — RUNTIME
# ══════════════════════════════════════════════════════════════════════════════

def clean(db):
    n = 0
    mis = list(db.rahaza_material_issues.find({"notes": {"$regex": MARK}}, {"_id": 0, "id": 1}))
    ids = [m["id"] for m in mis]
    if ids:
        n += db.rahaza_material_issues.delete_many({"id": {"$in": ids}}).deleted_count
    n += db.wh_barcode_print_jobs.delete_many({"note": {"$regex": MARK}}).deleted_count
    return n


def part_runtime(db):
    print(f"\n{B}[3] KEWENANGAN BUAT MI (H-2){X}")
    tok_gudang = login("gudang@dewiaditya.id", "Dewi@123")
    tok_spv = login("spv@dewiaditya.id", "Dewi@123")
    tok_admin = login("admin@garment.com", "Admin@123")
    if not tok_admin:
        bad("H2-1", "login admin gagal — sisa invarian runtime tidak bisa diuji")
        return

    mat = db.rahaza_materials.find_one({"type": {"$ne": "fg"}, "active": {"$ne": False}},
                                       {"_id": 0, "id": 1, "code": 1, "unit": 1})
    loc = db.rahaza_locations.find_one({}, {"_id": 0, "id": 1, "code": 1})
    if not mat:
        bad("H2-1", "tidak ada material non-FG di master — uji tidak bisa jalan")
        return

    def body(who):
        return {"items": [{"material_id": mat["id"], "qty_required": 1.5,
                           "location_id": (loc or {}).get("id")}],
                "notes": f"{MARK} manual oleh {who}"}

    created = []
    for code, tok, who in (("H2-1", tok_gudang, "admin gudang"),
                           ("H2-2", tok_spv, "supervisor produksi")):
        if not tok:
            bad(code, f"akun {who} tidak bisa login — kewenangan tidak terbukti")
            continue
        st, r = call("POST", "/api/rahaza/material-issues", tok, body(who))
        if st != 200:
            bad(code, f"{who} DITOLAK membuat MI manual (HTTP {st})", str(r)[:220])
            continue
        if not r.get("mi_number") or r.get("status") != "draft":
            bad(code, f"{who} membuat MI tetapi dokumennya tidak sah",
                f"mi_number={r.get('mi_number')} status={r.get('status')}")
            continue
        created.append((code, tok, r))
        ok(code, f"{who} bisa membuat MI manual dari master",
           f"{r['mi_number']} · {len(r.get('items') or [])} baris · {mat['code']} 1,5 {mat.get('unit')}")

    if created:
        code, tok, mi = created[0]
        st, r = call("POST", f"/api/rahaza/material-issues/{mi['id']}/submit", tok, {})
        if st == 200 and r.get("status") == "pending_approval":
            ok("H2-3", "pembuat bisa MENGAJUKAN MI-nya sendiri (draft → menunggu approval)",
               f"{mi['mi_number']} → {r.get('status')}")
        else:
            bad("H2-3", f"pengajuan MI oleh pembuatnya gagal (HTTP {st})", str(r)[:220])
    else:
        bad("H2-3", "tidak ada MI yang berhasil dibuat ⇒ pengajuan tidak bisa diuji")

    # ── H-3 barcode ──────────────────────────────────────────────────────────
    print(f"\n{B}[4] CETAK BARCODE (H-3){X}")
    before = db.wh_barcode_print_jobs.count_documents({})
    st, blob, hdr = call("POST", "/api/wms/barcode/batch-pdf", tok_admin,
                         {"kind": "material", "rows": [{"code": mat["code"], "copies": 7}],
                          "include_stock": True, "note": f"{MARK} batch bahan"}, raw=True)
    labels = hdr.get("X-Barcode-Labels") or hdr.get("x-barcode-labels")
    after = db.wh_barcode_print_jobs.count_documents({})
    if st != 200:
        bad("H3-2", f"cetak batch gagal (HTTP {st})", blob[:200].decode(errors="ignore"))
    elif not blob.startswith(b"%PDF"):
        bad("H3-2", "keluaran bukan PDF", str(blob[:40]))
    elif labels != "7":
        bad("H3-2", f"jumlah lembar tidak dihormati (X-Barcode-Labels={labels}, diminta 7)")
    elif after != before + 1:
        bad("H3-2", f"riwayat cetak tidak tercatat ({before} → {after})")
    else:
        pages = blob.count(b"/Type /Page") + blob.count(b"/Type/Page")
        ok("H3-2", "cetak batch menghormati jumlah lembar + tercatat di riwayat",
           f"{labels} label · {len(blob):,} byte · {pages} objek halaman · "
           f"riwayat {before} → {after}")

    fg = db.rahaza_materials.find_one({"type": "fg"}, {"_id": 0, "code": 1, "id": 1})
    fg_matrix = db.rahaza_fg_matrix.count_documents({})
    if not fg:
        bad("H3-3", "tidak ada barang jadi di master")
    else:
        st, blob, _ = call("GET", f"/api/wms/fg/{fg['code']}/label-pdf", tok_admin, raw=True)
        if st == 200 and blob.startswith(b"%PDF"):
            ok("H3-3", "label FG tercetak dari SSOT `rahaza_materials`",
               f"{fg['code']} · rahaza_fg_matrix berisi {fg_matrix} dokumen "
               f"(dulu jalur ini SELALU 404 karena hanya membaca koleksi itu)")
        else:
            bad("H3-3", f"label FG gagal (HTTP {st})", blob[:200].decode(errors="ignore"))

    st, r = call("POST", "/api/wms/barcode/batch-pdf", tok_admin,
                 {"kind": "material", "rows": [{"code": "KODE-KARANGAN-XYZ", "copies": 1}]})
    if st == 400 and "master" in json.dumps(r).lower():
        ok("H3-4", "kode di luar master DITOLAK beserta alasannya",
           str(r.get("detail"))[:150])
    else:
        bad("H3-4", f"kode karangan tidak ditolak (HTTP {st})", str(r)[:200])

    st, r = call("POST", "/api/wms/barcode/batch-pdf", tok_admin,
                 {"kind": "material", "rows": [{"code": mat["code"], "copies": 200},
                                               {"code": mat["code"], "copies": 200},
                                               {"code": mat["code"], "copies": 200}]})
    if st == 400 and "batas" in json.dumps(r).lower():
        ok("H3-5", "melebihi batas lembar DITOLAK dengan jalan keluar yang jelas",
           str(r.get("detail"))[:150])
    else:
        bad("H3-5", f"batas lembar tidak ditegakkan (HTTP {st})", str(r)[:200])

    po = db.production_pos.find_one({"business_type": "internal"}, {"_id": 0, "id": 1, "po_number": 1})
    if not po:
        bad("H3-6", "tidak ada PO internal untuk menguji mode otomatis")
    else:
        want = {}
        for it in db.po_items.find({"po_id": po["id"]}, {"_id": 0, "qty": 1}):
            want[len(want)] = int(it.get("qty") or 0)
        st, r = call("GET", f"/api/wms/barcode/from-production?po_id={po['id']}", tok_admin)
        got = [int(x.get("copies") or 0) for x in (r.get("rows") or [])]
        if st != 200:
            bad("H3-6", f"mode otomatis gagal (HTTP {st})", str(r)[:200])
        elif sorted(got) != sorted(want.values()):
            bad("H3-6", "jumlah label tidak sama dengan qty PO",
                f"PO={sorted(want.values())} label={sorted(got)}")
        else:
            ok("H3-6", "mode otomatis menyalin qty PO apa adanya (tidak diketik ulang)",
               f"{po['po_number']} · {len(got)} artikel · {sum(got)} label · "
               f"{r.get('unlinked_count')} artikel tanpa varian master (ditandai, tidak dicetak)")


def verdict():
    if "--keep" not in sys.argv:
        try:
            n = clean(db_handle())
            if n:
                print(f"\n{Y}  bersih-bersih: {n} dokumen uji dihapus{X}")
        except Exception:  # noqa: BLE001
            pass
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian Portal Gudang terjaga{X}")
    return 0


def main():
    print(f"{C}{B}FASE H — Portal Gudang: pintu MI · Buat Barcode · menu mati{X}")
    db = db_handle()
    clean(db)
    part_static()
    part_geometry()
    part_runtime(db)
    return verdict()


if __name__ == "__main__":
    sys.exit(main())
