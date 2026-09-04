#!/usr/bin/env python3
"""test_core_f10_layar_daftar.py — CORE TEST **F10**: layar daftar Portal Marketing
yang bisa DIPAKAI (tabel nyata · dicari · diurutkan · **diunduh**) dan tidak
menyembunyikan field yang sudah dikirim backend.

═══════════════════════════════════════════════════════════════════════════════
APA YANG DIBUKTIKAN (dan kenapa justru itu)
═══════════════════════════════════════════════════════════════════════════════
Audit sesi #10 atas **25 pintu** Portal Marketing menemukan dua hal:

1. **Hampir tidak ada layar yang bisa diunduh.** Hanya 2 dari 25 pintu punya
   tombol unduh. Artinya angka yang sudah benar di layar **tidak bisa dibawa ke
   rapat**: staf menyalin ulang dengan tangan ke WhatsApp/Excel (sumber salah-ketik
   paling umum di bisnis ini) atau menunggu orang lain membuatkan laporan. Layar
   yang benar tapi tidak bisa dipakai tetap membuat keputusan diambil dari angka
   yang diketik ulang.
2. **Laporan Harian menyembunyikan field yang dikirim backend.**
   `/api/marketing/reports/daily` mengirim `sales_status.entered_live` (status
   input omzet LIVE), tetapi layarnya hanya menampilkan `entered_total` ⇒ toko yang
   sudah mengisi omzet total tapi BELUM mengisi omzet live tampak "sudah beres"
   (centang hijau). Padahal angka live-lah yang dipakai menilai sesi live host.

Penjaga di berkas ini:
* `A-*` **Kontrak layar daftar**: setiap pintu daftar marketing wajib punya tabel
  nyata + pencarian/penyaring + **tombol unduh** dengan `data-testid`. Pintu yang
  memang bukan daftar (hub/dashboard/alat AI) dikecualikan **beserta alasannya**.
* `B-*` **Satu pembuat CSV**: semua layar memakai `lib/csv.js` (escaping + BOM
  Excel di satu tempat). Layar yang menulis CSV-nya sendiri = satu di antaranya
  akan lupa tanda kutip/BOM dan Excel menampilkan "Rp 1.000" sebagai tanggal.
  Juga: yang diunduh = baris yang TERLIHAT (bukan kueri ulang yang bisa berbeda).
* `C-*` **Tidak ada field yang disembunyikan** pada Laporan Harian: setiap kunci
  `sales_status` dari respons nyata punya rumah di layar.
* `D-*` **Runtime**: endpoint laporan harian hidup, membawa `entered_live`, dan
  tetap menghormati lingkup toko F6 (staf tanpa toko ⇒ 0 baris).

Pakai:  python3 /app/test_core_f10_layar_daftar.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
STAFF_NO_STORE = {"email": "staffmkt@dewiaditya.id", "password": "Dewi@123"}
FE = Path("/app/frontend/src/components/erp")
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
RES: list = []

# ── Pintu DAFTAR Portal Marketing → berkas layarnya ─────────────────────────
# Kontraknya: tabel nyata + cari/saring + tombol unduh (data-testid).
LIST_DOORS = {
    "marketing-accounts":         "AccountManagementModule.jsx",
    "marketing-sales":            "SalesDataEntryModule.jsx",
    "marketing-orders":           "marketing/UnifiedOrdersDashboard.jsx",
    "marketing-fulfillment":      "marketing/FulfillmentMonitorModule.jsx",
    "marketing-content-calendar": "marketing/ContentCalendarModule.jsx",
    "marketing-discounts":        "marketing/DiscountCampaignModule.jsx",
    "marketing-product-launches": "marketing/ProductLaunchModule.jsx",
    "marketing-health":           "marketing/AccountHealthDashboard.jsx",
    "marketing-change-log":       "marketing/MarketingChangeLogModule.jsx",
    "marketing-reviews":          "marketing/RatingReviewModule.jsx",
    "marketing-samples":          "marketing/SampleDeliveryModule.jsx",
    # tab "Laporan Harian" di dalam pintu marketing-reports
    "marketing-reports/harian":   "marketing/DailyReportModule.jsx",
    # SESI #20 — pintu BARU: daftar SKU platform yang belum dikenal master gudang.
    # Ia memang sebuah DAFTAR kerja (dibagi ke staf, dibawa ke rapat) ⇒ wajib
    # memenuhi kontrak tabel + cari + unduh, bukan dikecualikan.
    "sku-bridge":                 "SkuBridgeModule.jsx",
    # SESI #34 — pintu BARU: pencairan (settlement) marketplace di portal
    # Marketing. Ia DAFTAR uang yang benar-benar cair (dibawa ke rapat), jadi
    # wajib memenuhi kontrak tabel + penyaring + unduh — bukan dikecualikan,
    # meskipun marketing hanya boleh MELIHAT (input tetap di Finance).
    "marketing-settlements":      "marketing/MarketingSettlementsView.jsx",
}

# Layar yang isinya bisa lebih dari satu halaman ⇒ pencarian TEKS wajib.
PAGED_DOORS = {
    "marketing-orders", "marketing-fulfillment", "marketing-samples",
    "marketing-reviews", "marketing-change-log", "marketing-content-calendar",
    "marketing-discounts",
    # SESI #20 — 83 SKU tak-tertaut pada data hidup: satu halaman tidak cukup.
    "sku-bridge",
}

# Pintu yang BUKAN daftar — dikecualikan dengan alasan yang bisa diperiksa.
NOT_A_LIST = {
    "toko-dashboard": "dashboard ringkasan: angka resmi bulanan dari SSOT siklus "
                      "(target/omzet/anggaran/ROI) + grafik tren; daftar tokonya "
                      "ada di layar anaknya (Akun Platform → detail toko)",
    "marketing-import": "wizard langkah-demi-langkah (punya layar Riwayat sendiri)",
    "marketing-kol-hub": "hub berisi tab; daftarnya ada di layar anaknya",
    "marketing-live-hub": "hub berisi tab",
    "marketing-after-sales": "hub berisi tab (Komplain & Retur)",
    "marketing-reports": "hub berisi tab (Overview/Harian/Mingguan/Bulanan)",
    "marketing-ai-hub": "alat AI (masukan → keluaran), bukan daftar data toko",
    "marketing-task-hub": "papan Kanban tugas",
    "marketing-targets": "layar siklus: tabelnya di CycleView (punya CSV sendiri)",
    "marketing-catalog": "layar katalog: tabelnya di CatalogItemsView (punya CSV sendiri)",
    "marketing-account-review": "layar koreksi masif (setuju/tolak baris usulan)",
    "marketing-scheduler": "daftar jadwal otomasi (konfigurasi, bukan angka toko)",
    "marketing-integration-settings": "form pengaturan",
    "marketing-webhooks": "monitor teknis (log kiriman)",
    "maklon-notifications": "kotak masuk notifikasi",
}


def check(name: str, cond: bool, detail: str = "") -> bool:
    RES.append((name, bool(cond), detail))
    print(f"  {G}PASS{X}  {name}" if cond else f"  {R}FAIL{X}  {name}",
          f"— {detail}" if detail else "")
    return bool(cond)


def src(rel: str) -> str:
    p = FE / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def login(creds: dict):
    r = requests.post(f"{BASE}/api/auth/login", json=creds, timeout=60)
    r.raise_for_status()
    return r.json()["token"]


# ═══════════════════════════════════════════════════════════════════════════════
# [A] KONTRAK LAYAR DAFTAR
# ═══════════════════════════════════════════════════════════════════════════════
def section_contract() -> None:
    print(f"\n{Y}[A] Setiap pintu DAFTAR marketing: tabel · cari/saring · UNDUH{X}")
    missing_table, missing_search, missing_csv = [], [], []
    missing_text_search = []
    for door, rel in LIST_DOORS.items():
        s = src(rel)
        if not s:
            missing_table.append(f"{door} (berkas hilang: {rel})")
            continue
        if "<table" not in s:
            missing_table.append(door)
        # Menyempitkan daftar boleh dengan PENCARIAN TEKS atau PENYARING (pemilih
        # toko/status/platform) — yang tidak boleh: daftar tanpa cara menyempit.
        narrows = re.search(r"placeholder=[\"'].{0,40}[Cc]ari|data-testid=\"[a-z-]*search|"
                            r"set\w*(Search|Filter|Q)\w*\(|MarketingAccountSelect|"
                            r"data-testid=\"[a-z-]*filter", s)
        if not narrows:
            missing_search.append(door)
        # Layar yang bisa lebih dari satu halaman WAJIB punya pencarian teks:
        # menyaring per toko tidak menolong ketika satu toko punya 500 baris.
        if door in PAGED_DOORS and not re.search(
                r"data-testid=\"[a-z-]*search|placeholder=[\"'].{0,40}[Cc]ari", s):
            missing_text_search.append(door)
        # Harus DIPAKAI, bukan sekadar diimpor: `import ExportCsvButton` yang
        # komponennya tidak pernah dirender adalah tombol yang tidak ada di layar
        # (persis cacat yang dibuktikan lewat sabotase saat penjaga ini dibuat).
        if not re.search(r"<ExportCsvButton|downloadCsv\(|data-testid=\"[a-z-]*export",
                         s):
            missing_csv.append(door)
    check(f"A-1 {len(LIST_DOORS)} pintu daftar punya TABEL nyata",
          not missing_table, f"tanpa tabel: {missing_table}")
    check("A-2 setiap pintu daftar punya pencarian/penyaring",
          not missing_search, f"tanpa cari: {missing_search}")
    check("A-3 setiap pintu daftar bisa DIUNDUH (angka bisa dibawa ke rapat)",
          not missing_csv, f"tanpa unduh: {missing_csv}")
    check("A-3b layar berhalaman (ratusan baris) punya PENCARIAN TEKS, bukan hanya "
          "penyaring per toko", not missing_text_search,
          f"tanpa pencarian teks: {missing_text_search}")
    check("A-4 pengecualian 'bukan daftar' selalu punya ALASAN tertulis",
          all(str(v).strip() for v in NOT_A_LIST.values()),
          f"{len(NOT_A_LIST)} pengecualian")

    # Setiap pintu di navigasi marketing harus TERDAFTAR: entah sebagai daftar
    # (wajib bisa diunduh) atau sebagai pengecualian beralasan. Pintu BARU yang
    # lupa didaftarkan ⇒ gate merah (itulah gunanya penjaga ini).
    nav = (FE / "portal-shell/portalNav.js").read_text(encoding="utf-8")
    seg = nav.split("toko: {", 1)[1].split("collaboration: {", 1)[0]
    nav_ids = set(re.findall(r"\{ id: '([^']+)'", seg))
    known = set(LIST_DOORS) | set(NOT_A_LIST)
    unknown = sorted(i for i in nav_ids if i not in known)
    check("A-5 tidak ada pintu marketing yang belum diputuskan (daftar / bukan daftar)",
          not unknown, f"belum diputuskan: {unknown}")


# ═══════════════════════════════════════════════════════════════════════════════
# [B] SATU PEMBUAT CSV
# ═══════════════════════════════════════════════════════════════════════════════
def section_one_csv_maker() -> None:
    print(f"\n{Y}[B] Satu pembuat CSV (escaping + BOM Excel di SATU tempat){X}")
    lib = Path("/app/frontend/src/lib/csv.js")
    btn = FE.parent / "ui/export-csv-button.jsx"
    check("B-1 `lib/csv.js` ada & menyertakan BOM Excel + escaping tanda kutip",
          lib.exists() and "\\uFEFF" in lib.read_text(encoding="utf-8")
          and 'replace(/"/g, \'""\')' in lib.read_text(encoding="utf-8"), "")
    check("B-2 tombol unduh seragam (`ui/export-csv-button.jsx`) memakai lib itu",
          btn.exists() and "@/lib/csv" in btn.read_text(encoding="utf-8"), "")
    # Layar yang membuat CSV sendiri (tanpa lib) = pembuat CSV kedua.
    rogue = []
    for rel in LIST_DOORS.values():
        s = src(rel)
        if not s:
            continue
        makes_own = "new Blob(" in s and "text/csv" in s
        uses_lib = "@/lib/csv" in s or "ExportCsvButton" in s
        if makes_own and not uses_lib:
            rogue.append(rel)
    check("B-3 tidak ada layar yang menulis CSV-nya sendiri di luar lib",
          not rogue, f"pembuat CSV kedua: {rogue}")
    # Yang diunduh harus baris yang TERLIHAT: tombol unduh menerima `rows={...}`
    # dari state layar, bukan memanggil fetch sendiri di dalam tombol.
    btn_src = btn.read_text(encoding="utf-8") if btn.exists() else ""
    check("B-4 tombol unduh memakai baris yang SUDAH di layar (tidak kueri ulang)",
          "fetch(" not in btn_src and "axios" not in btn_src and "rows" in btn_src, "")
    check("B-5 tombol unduh MATI saat tidak ada baris (bukan berkas kosong)",
          "disabled={!list.length}" in btn_src, "")


# ═══════════════════════════════════════════════════════════════════════════════
# [C] TIDAK ADA FIELD YANG DISEMBUNYIKAN (Laporan Harian)
# ═══════════════════════════════════════════════════════════════════════════════
def section_no_hidden_field(payload: dict) -> None:
    print(f"\n{Y}[C] Laporan Harian: field yang dikirim backend punya rumah di layar{X}")
    s = src("marketing/DailyReportModule.jsx")
    accounts = payload.get("accounts") or []
    keys = sorted((accounts[0].get("sales_status") or {}).keys()) if accounts else []
    hidden = [k for k in keys if k not in s]
    check("C-1 semua kunci `sales_status` dipakai layar (tidak ada yang disembunyikan)",
          bool(keys) and not hidden, f"kunci={keys} · disembunyikan={hidden}")
    check("C-2 layar MEMISAHKAN input harian vs input LIVE (dua pertanyaan berbeda)",
          "entered_live" in s and "Input live" in s and "Input harian" in s, "")
    check("C-3 tabel bisa diurutkan per kolom (bukan urutan tetap)",
          "daily-sort-" in s and "toggleSort" in s, "")
    check("C-4 ada pengalih Tabel/Kartu (tampilan lama tidak dibuang)",
          "daily-view-table" in s and "daily-view-cards" in s, "")
    check("C-5 tombol 'Eksekusi' (input sales cepat) dipertahankan",
          "eksekusi-btn-" in s and "quick-sales-dialog" in s, "")
    check("C-6 staf tanpa toko tetap DIBERI TAHU sebabnya (panel lingkup)",
          "NoStoreScopeNotice" in s, "")


# ═══════════════════════════════════════════════════════════════════════════════
# [D] RUNTIME
# ═══════════════════════════════════════════════════════════════════════════════
def section_runtime(AT: str, ST: str | None) -> dict:
    print(f"\n{Y}[D] Endpoint laporan harian: hidup, lengkap, & berlingkup{X}")
    r = requests.get(f"{BASE}/api/marketing/reports/daily?date=2026-07-19",
                     headers={"Authorization": f"Bearer {AT}"}, timeout=60)
    d = r.json() if r.status_code == 200 else {}
    accounts = d.get("accounts") or []
    check("D-1 laporan harian menjawab 200 & memuat daftar toko",
          r.status_code == 200 and bool(accounts),
          f"HTTP {r.status_code} · {len(accounts)} toko")
    ss = (accounts[0].get("sales_status") or {}) if accounts else {}
    check("D-2 setiap toko membawa status input TOTAL dan LIVE",
          "entered_total" in ss and "entered_live" in ss, f"{sorted(ss.keys())}")
    check("D-3 ringkasan membawa angka yang dipakai kartu KPI",
          all(k in (d.get("summary") or {}) for k in
              ("accounts_total", "accounts_sales_entered", "sales_input_rate",
               "tasks_overdue")), f"{sorted((d.get('summary') or {}).keys())}")
    if ST:
        rs = requests.get(f"{BASE}/api/marketing/reports/daily?date=2026-07-19",
                          headers={"Authorization": f"Bearer {ST}"}, timeout=60)
        ds = rs.json() if rs.status_code == 200 else {}
        check("D-4 lingkup F6 tetap berlaku (staf tanpa toko ⇒ 0 toko, bukan 9)",
              rs.status_code == 200 and not (ds.get("accounts") or []),
              f"HTTP {rs.status_code} · {len(ds.get('accounts') or [])} toko")
    else:
        check("D-4 akun staf tanpa toko tersedia untuk uji lingkup", False, "login gagal")
    return d


def main() -> int:
    print(f"{B}{'=' * 88}{X}")
    print(f"{B}F10 — LAYAR DAFTAR MARKETING YANG BISA DIPAKAI (INV-F10){X}")
    print(f"{B}{'=' * 88}{X}")
    section_contract()
    section_one_csv_maker()
    try:
        AT = login(ADMIN)
    except Exception as e:                                        # noqa: BLE001
        print(f"{R}  backend/login admin tidak siap: {e}{X}")
        return 1
    try:
        ST = login(STAFF_NO_STORE)
    except Exception:                                             # noqa: BLE001
        ST = None
    payload = section_runtime(AT, ST)
    section_no_hidden_field(payload)

    ok = sum(1 for _, c, _ in RES if c)
    bad = [n for n, c, _ in RES if not c]
    print(f"\n{B}{'-' * 88}{X}")
    print(f"  INV-F10: {len(RES)} diperiksa — {len(bad)} temuan")
    if bad:
        print(f"  {R}{B}✗ INV-F10 MERAH{X}")
        for n in bad:
            print(f"    {R}·{X} {n}")
        return 1
    print(f"  {G}{B}✓ INV-F10 HIJAU — {ok}/{len(RES)}{X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
