#!/usr/bin/env python3
"""_verify_fe_contract_monitor_weekly_katalog.py — KONTRAK LAYAR ↔ BACKEND (4 kemampuan
2026-08-12 #5).

KENAPA BERKAS INI ADA
---------------------
`test_core_katalog_monitor_mingguan.py` membuktikan backend-nya BENAR (51/51), tetapi
ia memeriksa angka — bukan **nama field yang dibaca layar**. Layar yang membaca
`row.overdue_days` sementara backend mengirim `over_by_days` akan tampil "—" di
seluruh kolom TANPA satu pun galat: uji API hijau, staf melihat tabel kosong.

Skrip ini membandingkan, field demi field, apa yang dibaca JSX dengan apa yang
benar-benar dikirim endpoint — memakai HTTP sungguhan dan data nyata (berkas
ekspor TikTok 601 baris → 559 pesanan).

Pakai:
    python3 /app/scripts/_verify_fe_contract_monitor_weekly_katalog.py            # pakai data yang ada
    python3 /app/scripts/_verify_fe_contract_monitor_weekly_katalog.py --import   # impor berkas contoh dulu
"""
from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001"
SAMPLE = "/app/samples/TikTok_UntukDikirim_2026-07-19.xlsx"
XLSX = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
DO_IMPORT = "--import" in sys.argv

G, R, Y, X = "\033[92m", "\033[91m", "\033[93m", "\033[0m"
RES: list[tuple[str, bool, str]] = []


def ok(n, d=""):
    RES.append((n, True, d)); print(f"  {G}PASS{X}  {n}" + (f" — {d}" if d else ""))


def bad(n, d=""):
    RES.append((n, False, d)); print(f"  {R}FAIL{X}  {n}" + (f" — {d}" if d else ""))


def check(n, cond, d=""):
    (ok if cond else bad)(n, d); return bool(cond)


def keys_present(name: str, doc: dict, fields: list[str]) -> bool:
    """Semua field yang DIBACA layar harus ADA (boleh null, tidak boleh hilang)."""
    if not isinstance(doc, dict):
        return check(name, False, f"bukan objek: {type(doc).__name__}")
    miss = [f for f in fields if f not in doc]
    return check(name, not miss, "lengkap" if not miss else f"HILANG: {', '.join(miss)}")


def main() -> int:
    tok = requests.post(f"{BASE}/api/auth/login", json={
        "email": "admin@garment.com", "password": "Admin@123"}, timeout=30).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    JH = {**H, "Content-Type": "application/json"}

    accs = requests.get(f"{BASE}/api/marketing/accounts", headers=H, timeout=60).json()
    accs = accs.get("accounts", accs) if isinstance(accs, dict) else accs
    by_code = {a.get("account_code"): a for a in accs}
    outfit = by_code.get("TIKTOK-OUTFIT")
    if not check("prasyarat: master toko nyata ada", bool(outfit), f"{len(accs)} toko"):
        return 1

    # ── layar Kelola Akun / wizard membaca field ini di daftar toko ─────────────
    keys_present("daftar toko memuat field yang dibaca wizard & monitor",
                 outfit, ["id", "account_code", "account_name", "platform",
                          "platform_warehouse_name"])

    print(f"\n{Y}[1] Impor berkas contoh (dasar layar Monitoring & Mingguan){X}")
    if DO_IMPORT:
        IMP = f"{BASE}/api/marketing/data-import"
        with open(SAMPLE, "rb") as fh:
            up = requests.post(f"{IMP}/upload", headers=H, timeout=300,
                               files={"file": (os.path.basename(SAMPLE), fh, XLSX)},
                               data={"source_type": "marketplace_orders",
                                     "account_id": outfit["id"]})
        if not check("unggah berkas contoh 200", up.status_code == 200,
                     f"{up.status_code} {up.text[:180]}"):
            return 1
        sess = up.json()["session"]
        keys_present("sesi impor memuat field yang dibaca wizard", sess,
                     ["id", "filename", "shop_guard_hint", "shop_guard_warehouse",
                      "account_name", "account_code", "account_platform"])
        cm = requests.post(f"{IMP}/sessions/{sess['id']}/commit",
                           headers=JH, json={"on_duplicate": "skip"}, timeout=600)
        check("commit 200", cm.status_code == 200, f"{cm.status_code} {cm.text[:160]}")
        print(f"    sesi: {sess['id']}  gudang di berkas: {sess.get('shop_guard_warehouse')!r}")
    else:
        print("    (dilewati — pakai data yang sudah ada)")

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{Y}[2] MONITORING PENGIRIMAN — field yang dibaca FulfillmentMonitorModule.jsx{X}")
    # ══════════════════════════════════════════════════════════════════════════
    r = requests.get(f"{BASE}/api/marketing/orders/fulfillment-monitor",
                     headers=H, params={"bucket": "belum_dikirim", "page_size": 5}, timeout=120)
    if not check("monitor 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}"):
        return 1
    m = r.json()
    keys_present("akar respons monitor", m,
                 ["ok", "totals", "per_store", "rows", "page", "total", "total_pages",
                  "data_notes", "sla_default", "bucket", "as_of"])
    keys_present("kartu angka (totals) monitor", m["totals"],
                 ["belum_dikirim", "lewat_batas", "batal", "retur", "sudah_dikirim",
                  "nilai_belum_dikirim", "nilai_lewat_batas", "umur_tertua_hari",
                  "pesanan_dibaca"])
    if m["rows"]:
        keys_present("baris 'belum dikirim' (kolom tabel layar)", m["rows"][0],
                     ["id", "order_id", "account_name", "status", "status_raw",
                      "is_preorder", "paid_at", "age_days", "sla_days", "over_by_days",
                      "deadline", "late", "courier", "order_channel", "quantity", "value"])
    else:
        bad("baris 'belum dikirim' ada", "0 baris — jalankan dengan --import")
    if m["per_store"]:
        keys_present("rekap per toko (tabel atas + tombol Batas kirim)", m["per_store"][0],
                     ["account_id", "account_code", "account_name", "platform",
                      "sla_days", "sla_days_preorder", "lewat_batas", "belum_dikirim",
                      "nilai_belum_dikirim", "umur_tertua_hari"])
    else:
        bad("rekap per toko ada", "kosong")

    rb = requests.get(f"{BASE}/api/marketing/orders/fulfillment-monitor",
                      headers=H, params={"bucket": "batal", "page_size": 5}, timeout=120)
    check("bucket 'batal' 200 (tabel kolom berbeda)", rb.status_code == 200,
          f"{rb.status_code}")
    check("catatan kejujuran data ikut dikirim", isinstance(m.get("data_notes"), list),
          f"{len(m.get('data_notes') or [])} catatan")

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{Y}[3] LAPORAN RAPAT MINGGUAN — field yang dibaca WeeklyMeetingReportModule.jsx{X}")
    # ══════════════════════════════════════════════════════════════════════════
    w = requests.get(f"{BASE}/api/marketing/reports/weekly",
                     headers=H, params={"week_start": "2026-07-15"}, timeout=180)
    if not check("laporan mingguan 200", w.status_code == 200, f"{w.status_code} {w.text[:160]}"):
        return 1
    wk = w.json()
    keys_present("akar respons mingguan", wk,
                 ["periode", "gabungan", "per_toko", "catatan_data"])
    keys_present("periode (judul + navigasi minggu)", wk["periode"],
                 ["minggu", "label", "mulai", "selesai", "dasar_minggu",
                  "minggu_sebelumnya"])
    keys_present("minggu pembanding", wk["periode"]["minggu_sebelumnya"], ["label"])
    keys_present("gabungan (6 kartu angka + baris GABUNGAN)", wk["gabungan"],
                 ["omzet", "pesanan", "pcs", "aov", "target_prorata",
                  "pencapaian_target_persen", "iklan_spend", "roas", "belum_dikirim",
                  "nilai_belum_dikirim", "kanal", "kanal_persen", "toko", "toko_berdata",
                  "batal", "vs_minggu_lalu"])
    keys_present("delta vs minggu lalu (gabungan)", wk["gabungan"]["vs_minggu_lalu"],
                 ["omzet"])
    keys_present("isi delta omzet", wk["gabungan"]["vs_minggu_lalu"]["omzet"],
                 ["persen"])
    kanal_fe = ["live", "video", "product_card", "ads", "affiliate", "campaign",
                "search", "organic", "other"]
    keys_present("pecahan kanal (9 kotak layar)", wk["gabungan"]["kanal"], kanal_fe)
    keys_present("persentase kanal", wk["gabungan"]["kanal_persen"], kanal_fe)
    if check("per_toko terisi", bool(wk["per_toko"]), f"{len(wk['per_toko'])} toko"):
        t0 = wk["per_toko"][0]
        keys_present("baris per toko (19 kolom tabel)", t0,
                     ["account_id", "account_code", "account_name", "omzet", "pesanan",
                      "pcs", "aov", "pencapaian_target_persen", "hari_berdata",
                      "sumber_angka", "vs_minggu_lalu", "target", "kanal", "pemenuhan",
                      "pesanan_mentah", "iklan"])
        keys_present("target per toko", t0["target"], ["lengkap", "revenue"])
        keys_present("pemenuhan per toko", t0["pemenuhan"], ["fulfillment_rate"])
        keys_present("pesanan mentah per toko", t0["pesanan_mentah"],
                     ["batal", "belum_dikirim"])
        keys_present("iklan per toko", t0["iklan"], ["terisi", "spend", "roas"])
    for fmt, mime in (("pdf", "application/pdf"),
                      ("excel", "spreadsheetml")):
        e = requests.get(f"{BASE}/api/marketing/reports/weekly/export-{fmt}",
                         headers=H, params={"week_start": "2026-07-15"}, timeout=180)
        check(f"tombol unduh {fmt.upper()} berfungsi", e.status_code == 200
              and mime in e.headers.get("content-type", ""),
              f"{e.status_code} · {e.headers.get('content-type','')[:40]} · "
              f"{len(e.content)//1024} KB")

    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{Y}[4] KATALOG DARI MASTER — field yang dibaca CatalogFromMasterModule.jsx{X}")
    # ══════════════════════════════════════════════════════════════════════════
    c = requests.get(f"{BASE}/api/marketing/catalogs/master-products",
                     headers=H, params={"account_id": outfit["id"]}, timeout=120)
    if not check("master produk 200", c.status_code == 200, f"{c.status_code} {c.text[:160]}"):
        return 1
    cm2 = c.json()
    keys_present("akar respons master produk", cm2,
                 ["ok", "products", "total_products", "total_variants", "catalog_id"])
    if check("produk master terbaca", bool(cm2["products"]),
             f"{cm2['total_products']} produk · {cm2['total_variants']} varian"):
        p0 = next((p for p in cm2["products"] if p.get("variants")), cm2["products"][0])
        keys_present("kartu produk master (baris kiri layar)", p0,
                     ["model_id", "code", "name", "category_name", "hpp",
                      "retail_price_master", "variant_count", "in_catalog_count",
                      "variants"])
        if check("varian ikut terkirim", bool(p0["variants"]),
                 f"{len(p0['variants'])} varian"):
            keys_present("baris varian (tabel varian)", p0["variants"][0],
                         ["fg_material_id", "code", "color", "size_code", "hpp",
                          "sellable_stock", "in_catalog"])
    q = requests.get(f"{BASE}/api/marketing/catalogs/master-products",
                     headers=H, params={"q": "hoodie"}, timeout=120)
    check("kotak pencarian produk bekerja di server", q.status_code == 200
          and q.json().get("total_products", 0) >= 0,
          f"{q.status_code} · {q.json().get('total_products')} hasil")

    print("\n" + "=" * 86)
    tot, fail = len(RES), sum(1 for _, o, _ in RES if not o)
    print(f"RINGKAS KONTRAK LAYAR↔BACKEND: {tot - fail}/{tot} PASS"
          + (f" · {R}{fail} GAGAL{X}" if fail else f" {G}(semua field yang dibaca layar ADA){X}"))
    print("=" * 86)
    if fail:
        for n, o, d in RES:
            if not o:
                print(f"  {R}·{X} {n} — {d}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
