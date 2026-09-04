#!/usr/bin/env python3
"""test_core_f14_form_pakai_master.py — CORE TEST **F14b**:
form tidak boleh meminta orang MENGETIK apa yang sudah punya MASTER.

═══════════════════════════════════════════════════════════════════════════════
APA YANG DIBUKTIKAN — DAN KENAPA ITU SOAL UANG, BUKAN KENYAMANAN
═══════════════════════════════════════════════════════════════════════════════
Temuan pemilik (2026-08-14): layar **Launching Produk** meminta staf mengetik
nama produk / bahan / model sebagai teks bebas — padahal yang diluncurkan adalah
produk **milik DA sendiri** yang sudah terdaftar di `rahaza_models` beserta
varian FG-nya. Kalimat pemiliknya: *"logicnya ini adalah product launch yang ada
di DA, kalau input custom field ya ini sama saja cacat"*.

Yang DIUKUR sesudah itu (bukan dugaan):

  1. **Master stok kotor.** `_auto_create_fg_from_launch()` membuat BARANG JADI
     dari teks yang diketik:
         code = style_code OR model OR product_name.replace(" ","-").upper()[:30]
     Untuk baris demo "Gamis Busui Friendly DA-2026 Series 1" itu melahirkan FG
     `GAMIS-BUSUI-FRIENDLY-DA-2026-S` — tanpa `model_id`, tanpa varian
     warna/ukuran, `hpp = 0`, kategori literal `"launch"`. Satu produk jadi DUA
     barang di master stok, dan "stok produk ini berapa?" punya dua jawaban.
  2. **Harga tak bisa direkonsiliasi.** Rencana menyebut harga ketikan; katalog
     menyebut `harga_jual`; master menyebut `retail_price`. Tidak ada yang tahu
     ketiganya seharusnya berhubungan.
  3. **Ejaan = identitas.** "Katun Linen Premium" ≠ "katun linen premium" bagi
     mesin. Setiap laporan yang mengelompokkan per produk/bahan salah DIAM-DIAM.
  4. **8 dari 8** rencana peluncuran yang ada tidak punya `model_id` sama sekali.

PENJAGA DI BERKAS INI
---------------------
* `A-*` **AUDIT MENYELURUH** (statik) — `scripts/_audit_form_master_refs.py`
  dijalankan ulang atas SELURUH layar; tidak boleh ada form yang meminta ketikan
  untuk konsep yang punya master. Audit ini sengaja dibuat SULIT MENUDUH
  (pembatas domain + form-milik-master + deteksi auto-fill) karena penjaga yang
  salah tuduh akan berhenti dipercaya — dan penjaga yang tidak dipercaya sama
  dengan tidak ada penjaga (pelajaran sesi #10).
* `B-*` **SATU PEMILIH, SATU SUMBER** — `MasterProductSelect` membaca
  `/api/marketing/catalogs/master-products`, endpoint yang SAMA dengan layar
  Katalog dari Master. Kalau tiap layar memanggil endpoint sendiri, suatu hari
  dua layar menampilkan daftar produk yang berbeda.
* `C-*` **SERVER SATU-SATUNYA PENULIS** (runtime) — identitas produk ditulis
  server dari master; kiriman browser diabaikan. Dibuktikan dengan MENGIRIM nama
  palsu dan memastikan yang tersimpan adalah nama master.
* `D-*` **BARANG JADI KEMBAR TIDAK BISA LAHIR LAGI** (runtime) — status
  → `launched` tidak menambah satu pun dokumen `rahaza_materials`.
* `E-*` **WARISAN DIAKUI, BUKAN DITEBAK** — dokumen lama tanpa `model_id`
  dihitung server (`master_link.unlinked_total`) dan ditandai di layar; tidak
  ada tebakan padanan nama (menebak = menautkan ke produk yang salah tanpa bisa
  dibedakan dari tautan yang benar).

Pakai:  python3 /app/test_core_f14_form_pakai_master.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import requests

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}

FE = Path("/app/frontend/src/components/erp")
BE = Path("/app/backend/routes")
AUDIT_JSON = Path("/app/memory/AUDIT_FORM_MASTER_REFS.json")

G, R, Y, X, B, C = ("\033[92m", "\033[91m", "\033[93m", "\033[0m",
                    "\033[1m", "\033[96m")
RES: list = []


def check(code: str, cond: bool, msg: str):
    RES.append((code, bool(cond), msg))
    print(f"  {G + '✓' + X if cond else R + '✗' + X} [{code}] {msg}")
    return bool(cond)


# ═══════════════════════════════════════════════════════════════════════════════
# [A] AUDIT MENYELURUH — tidak ada form yang mengetik apa yang punya master
# ═══════════════════════════════════════════════════════════════════════════════
def section_audit():
    print(f"\n{B}[A] Audit seluruh layar — form tidak mengetik apa yang punya master{X}")
    try:
        subprocess.run([sys.executable, "/app/scripts/_audit_form_master_refs.py"],
                       capture_output=True, timeout=300, check=False)
        rep = json.loads(AUDIT_JSON.read_text())
    except Exception as e:  # noqa: BLE001
        check("A-0", False, f"audit tidak bisa dijalankan/dibaca: {e}")
        return

    check("A-0", rep.get("scanned_files", 0) >= 300,
          f"audit benar-benar memindai layar ({rep.get('scanned_files')} berkas) "
          f"— audit yang memindai 0 berkas akan selalu 'lulus'")

    findings = rep.get("findings") or []
    detail = "; ".join(f"{Path(f['file']).name}:{f['line']} {f['field']}"
                       for f in findings[:6])
    check("A-1", not findings,
          f"tidak ada form yang meminta ketikan untuk konsep ber-master "
          f"({len(findings)} temuan)" + (f" — {detail}" if findings else ""))

    # Audit yang tidak punya pembatas domain akan MENUDUH SALAH. Dijaga supaya
    # pembatasnya tidak dihapus diam-diam demi "biar hijau".
    src = Path("/app/scripts/_audit_form_master_refs.py").read_text()
    check("A-2", "DOMAIN_DENY" in src and "MASTER_OWN_FORM" in src,
          "audit punya pembatas domain + daftar form-milik-master (tanpa itu ia "
          "menuduh kategori biaya HR & model aset IT sebagai cacat produk)")
    check("A-3", "_autofilled_from_picker" in src and '"target"' in src,
          "audit membedakan auto-fill dari pemilih vs KETIKAN (`e.target.value`) "
          "— tanpa ini audit pernah melaporkan 0 temuan padahal cacatnya utuh")


# ═══════════════════════════════════════════════════════════════════════════════
# [B] SATU PEMILIH, SATU SUMBER
# ═══════════════════════════════════════════════════════════════════════════════
SCOPE_FE = {
    "marketing/ProductLaunchModule.jsx": "rencana peluncuran produk DA",
    "marketing/AIContentGeneratorModule.jsx": "caption yang TAYANG ke pembeli",
    "CMTComponentRequestModule.jsx": "permintaan komponen ke vendor CMT",
}


def section_satu_pemilih():
    print(f"\n{B}[B] Satu pemilih produk, satu sumber daftar{X}")
    picker = FE / "pickers" / "MasterProductSelect.jsx"
    if not check("B-1", picker.exists(),
                 "komponen `MasterProductSelect` ada (satu pemilih dipakai lintas modul)"):
        return
    psrc = picker.read_text()
    check("B-2", "/api/marketing/catalogs/master-products" in psrc,
          "pemilih membaca endpoint master yang SAMA dengan layar Katalog dari "
          "Master — dua layar tidak mungkin menampilkan daftar produk berbeda")
    check("B-3", "CommandInput" in psrc,
          "pemilih punya kotak CARI (master produk tumbuh; dropdown 200 baris "
          "tanpa pencarian adalah 'tidak bisa dipakai' yang diperbaiki F10)")
    check("B-4", "erp_token" in psrc,
          "pemilih memakai kunci token yang benar (`erp_token`) — salah kunci "
          "membuat daftar selalu kosong dan orang menyimpulkan master kosong")

    for rel, why in SCOPE_FE.items():
        f = FE / rel
        name = Path(rel).name
        if not f.exists():
            check(f"B-5·{name}", False, f"{rel} tidak ditemukan")
            continue
        src = f.read_text()
        check(f"B-5·{name}", "MasterProductSelect" in src,
              f"{name} memakai pemilih master — {why}")
        # Tidak boleh ada lagi <Input> yang terikat ke nama produk.
        typed = re.search(r"<Input[^>]*value=\{\s*form\.product_name", src)
        check(f"B-6·{name}", not typed,
              f"{name} tidak lagi punya kotak ketik nama produk")


# ═══════════════════════════════════════════════════════════════════════════════
# [C] SERVER SATU-SATUNYA PENULIS (statik + runtime)
# ═══════════════════════════════════════════════════════════════════════════════
def section_server_penulis_statik():
    print(f"\n{B}[C] Server satu-satunya penulis identitas produk (statik){X}")
    f = BE / "marketing_product_launches_routes.py"
    src = f.read_text()
    check("C-1", "_resolve_master_model" in src,
          "ada SATU fungsi resolusi master (`_resolve_master_model`) — kalau "
          "tiap endpoint menyalin sendiri, suatu hari salah satunya lupa")
    check("C-2", "MASTER_DERIVED_FIELDS" in src
          and "for _f in MASTER_DERIVED_FIELDS" in src,
          "PUT membuang field turunan master kiriman browser (kalau tidak, staf "
          "bisa memilih produk A lalu menimpa namanya — terlihat 'tertaut' "
          "padahal isinya sudah berbeda: lebih berbahaya dari teks bebas)")
    check("C-3", re.search(r"class LaunchIn\(BaseModel\):(?:.|\n)*?model_id: str\b", src)
          is not None,
          "`model_id` WAJIB pada pembuatan rencana peluncuran (bukan Optional)")

    # `_auto_create_fg_from_launch` TIDAK boleh menulis ke master material.
    body = src.split("async def _auto_create_fg_from_launch")[-1]
    check("C-4", "rahaza_materials.insert_one" not in body,
          "penautan FG TIDAK PERNAH membuat barang jadi baru (akar cacat: FG "
          "karangan dari teks ⇒ produk kembar di master stok)")

    cmt = (BE / "dewi_cmt_component_requests.py").read_text()
    check("C-5", "_resolve_product_from_master" in cmt,
          "permintaan komponen CMT juga meresolusi produk lewat SATU fungsi")

    ai = (BE / "marketing_ai_content_tools.py").read_text()
    check("C-6", "model_id" in ai and "rahaza_models" in ai,
          "generator caption memakai identitas produk dari master (teksnya "
          "TAYANG ke pembeli — bahan karangan di caption adalah klaim salah)")


class Api:
    def __init__(self):
        r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=20)
        r.raise_for_status()
        self.h = {"Authorization": f"Bearer {r.json()['token']}"}

    def get(self, p, **kw):
        return requests.get(f"{BASE}{p}", headers=self.h, timeout=60, **kw)

    def post(self, p, **kw):
        return requests.post(f"{BASE}{p}", headers=self.h, timeout=60, **kw)

    def put(self, p, **kw):
        return requests.put(f"{BASE}{p}", headers=self.h, timeout=60, **kw)

    def delete(self, p, **kw):
        return requests.delete(f"{BASE}{p}", headers=self.h, timeout=60, **kw)


def _fg_count(api: Api) -> int:
    """Jumlah barang jadi di master — dibaca lewat endpoint master produk."""
    r = api.get("/api/marketing/catalogs/master-products", params={"limit": 300})
    if r.status_code != 200:
        return -1
    return sum(p.get("variant_count", 0) for p in r.json().get("products", []))


def section_runtime(api: Api):
    print(f"\n{B}[C/D/E] Runtime — dibuktikan dengan mengirim data, bukan membaca kode{X}")

    accs = api.get("/api/marketing/accounts", params={"page_size": 1})
    data = accs.json()
    lst = data if isinstance(data, list) else (data.get("data") or data.get("accounts") or [])
    if not lst:
        check("C-7", False, "tidak ada toko marketing untuk menguji")
        return
    acc_id = lst[0]["id"]

    mp = api.get("/api/marketing/catalogs/master-products", params={"limit": 5})
    prods = mp.json().get("products") or []
    if not prods:
        check("C-7", False, "master produk kosong — tidak bisa menguji runtime")
        return
    prod = next((p for p in prods if p.get("variant_count")), prods[0])
    model_id = prod["model_id"]

    # C-7 — tanpa `model_id` harus DITOLAK
    r = api.post("/api/marketing/product-launches",
                 json={"account_id": acc_id, "product_name": "Produk Karangan",
                       "launch_date": "2026-12-01"})
    check("C-7", r.status_code in (400, 422),
          f"rencana TANPA produk master ditolak (HTTP {r.status_code})")

    # C-8 — `model_id` yang tidak ada harus DITOLAK dengan alasan yang jelas
    r = api.post("/api/marketing/product-launches",
                 json={"account_id": acc_id, "model_id": "tidak-ada-ini",
                       "launch_date": "2026-12-01"})
    ok8 = r.status_code == 400 and "Master Produk" in (r.text or "")
    check("C-8", ok8,
          f"produk yang tidak ada di master ditolak DENGAN alasan (HTTP {r.status_code})")

    # C-9 — nama palsu kiriman browser DIABAIKAN
    fg_before = _fg_count(api)
    r = api.post("/api/marketing/product-launches",
                 json={"account_id": acc_id, "model_id": model_id,
                       "product_name": "NAMA PALSU KIRIMAN BROWSER",
                       "material": "BAHAN PALSU", "model": "MODEL PALSU",
                       "launch_date": "2026-12-01"})
    if not check("C-9", r.status_code == 200,
                 f"rencana dengan produk master diterima (HTTP {r.status_code})"):
        return
    doc = r.json()["data"]
    lid = doc["id"]
    try:
        check("C-10", doc.get("product_name") == prod["name"],
              f"nama tersimpan = nama MASTER ('{doc.get('product_name')}'), "
              f"bukan kiriman browser")
        check("C-11", doc.get("model_code") == prod["code"]
              and doc.get("material") != "BAHAN PALSU",
              "kode & bahan juga dari master (browser tidak bisa menimpanya)")

        # C-12 — PUT juga tidak bisa menimpa
        r2 = api.put(f"/api/marketing/product-launches/{lid}",
                     json={"product_name": "DITIMPA LEWAT PUT",
                           "material": "DITIMPA", "listing_price": 12345})
        d2 = r2.json().get("data", {})
        check("C-12", d2.get("product_name") == prod["name"]
              and float(d2.get("listing_price") or 0) == 12345,
              "PUT tidak bisa menimpa identitas master, tetapi field yang MEMANG "
              "milik rencana (harga listing) tetap bisa diubah")

        # D-1 — status → launched TIDAK menambah barang jadi
        r3 = api.post(f"/api/marketing/product-launches/{lid}/status",
                      json={"status": "launched"})
        body3 = r3.json() if r3.status_code == 200 else {}
        fg_after = _fg_count(api)
        check("D-1", fg_before == fg_after and fg_before >= 0,
              f"status → 'launched' TIDAK melahirkan barang jadi baru "
              f"({fg_before} → {fg_after})")
        check("D-2", body3.get("fg_auto_created") is False,
              "server menyatakan tegas: tidak ada FG yang dibuat "
              "(ditautkan ke varian master yang sudah ada)")
        if prod.get("variant_count"):
            check("D-3", body3.get("fg_linked") is True,
                  "rencana ditautkan ke varian FG master yang BENAR-BENAR ada")
    finally:
        api.delete(f"/api/marketing/product-launches/{lid}")

    # E-* — warisan diakui
    lst2 = api.get("/api/marketing/product-launches", params={"page_size": 5}).json()
    check("E-1", "master_link" in lst2 and "unlinked_total" in lst2["master_link"],
          "server MENGHITUNG jumlah rencana yang belum tertaut master "
          "(warisan diakui, bukan disembunyikan)")
    check("E-2", all("master_linked" in it for it in (lst2.get("data") or [])),
          "setiap baris membawa status tautannya sendiri (layar tidak menebak)")

    fe = (FE / "marketing" / "ProductLaunchModule.jsx").read_text()
    check("E-3", "launch-unlinked-banner" in fe,
          "layar menampilkan peringatan berisi JUMLAH rencana yang belum tertaut")
    check("E-4", "launch-legacy-warning" in fe,
          "form Edit dokumen warisan mengatakan keadaannya + cara memperbaikinya")

    mig = Path("/app/backend/migrations/relink_product_launches_to_master.py")
    check("E-5", mig.exists() and "TIDAK PERNAH DITEBAK" in mig.read_text(),
          "migrasi ADA dan menolak menebak padanan untuk dokumen NYATA "
          "(menebak = menautkan ke produk salah tanpa bisa dibedakan)")


def main() -> int:
    print(f"{B}══ CORE TEST F14b — FORM WAJIB MEMAKAI MASTER, BUKAN KETIKAN ══{X}")
    section_audit()
    section_satu_pemilih()
    section_server_penulis_statik()

    try:
        api = Api()
    except Exception as e:  # noqa: BLE001
        print(f"\n  {Y}▲ backend/auth tidak siap ({e}) — bagian runtime dilewati{X}")
        api = None
    if api:
        section_runtime(api)

    passed = sum(1 for _, p, _ in RES if p)
    total = len(RES)
    print(f"\n{B}{'═' * 70}{X}")
    for code, p, msg in RES:
        if not p:
            print(f"  {R}GAGAL{X} [{code}] {msg}")
    print(f"{B}HASIL: {passed}/{total} penjaga LULUS{X}")
    print("  " + (G + "HIJAU" + X if passed == total else R + "MERAH" + X))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
