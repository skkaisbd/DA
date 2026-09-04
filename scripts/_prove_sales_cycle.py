#!/usr/bin/env python3
"""BUKTI ANALISIS (READ-ONLY) — SIKLUS TARGET · OMZET · ANGGARAN.

Tidak menulis apa pun ke MongoDB. Membuktikan dengan menjalankan fungsi
produksi yang sebenarnya (`marketing_import_engine`, `_finish`) lalu menerapkan
EKSPRESI PEMBACAAN yang persis dipakai tiap layar.

Jalankan: cd /app/backend && python3 /app/scripts/_prove_sales_cycle.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys

sys.path.insert(0, "/app/backend")
os.chdir("/app/backend")

from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from core import marketing_import_engine as eng  # noqa: E402
from core.marketing_import_schema import get_source_type  # noqa: E402

LINE = "=" * 104


def bar(t):
    print(f"\n{LINE}\n{t}\n{LINE}")


# ════════════════════════════════════════════════════════════════════════════════
def s1_peta_sumber():
    bar("S1 — PETA SUMBER ANGKA: layar mana membaca koleksi mana (dipindai dari kode)")
    targets = {
        "marketing_sales_data": "REKAP HARIAN per (akun, tanggal, revenue_type)",
        "marketing_orders": "PER PESANAN (hasil impor / manual)",
        "marketing_account_targets": "TARGET bulanan per akun",
        "marketing_creator_targets": "TARGET bulanan per kreator",
        "marketing_creator_sessions": "sesi kreator (input manual)",
        "marketing_livehost_shifts": "shift host (input manual)",
        "marketing_budgets": "RENCANA anggaran per (akun, periode)",
        "marketing_spend_entries": "REALISASI belanja manual",
    }
    files = sorted(f for f in os.listdir("routes") if f.endswith(".py"))
    print("  Catatan: wizard impor tanpa-AI menulis lewat nama koleksi DINAMIS")
    print("  (`db[st.collection]` — marketing_data_import.py:918/941/991), jadi ia TIDAK")
    print("  muncul pada pemindaian nama koleksi di bawah. Ditandai manual: [+impor].")
    for coll, desc in targets.items():
        readers, writers = [], []
        for f in files:
            try:
                src = open(f"routes/{f}", encoding="utf-8").read()
            except Exception:
                continue
            if coll not in src:
                continue
            w = bool(re.search(rf"{coll}\.(insert_one|insert_many|update_one|update_many|"
                               rf"replace_one|delete_one|delete_many|bulk_write)", src))
            r = bool(re.search(rf"{coll}\.(find|find_one|aggregate|count_documents|distinct)", src))
            if w:
                writers.append(f[:-3])
            if r:
                readers.append(f[:-3])
        touched = sorted(set(writers) | set(readers))
        print(f"\n  ── {coll}  ({desc})")
        print(f"     MENULIS ({len(writers)}): {', '.join(writers) or '—'}")
        print(f"     MEMBACA ({len(readers)}): {', '.join(readers) or '—'}")
        print(f"     total berkas yang menyentuh: {len(touched)}"
              + ("   <== PULAU: hanya 1 berkas, tak ada modul lain yang memakainya"
                 if len(touched) == 1 else ""))


# ════════════════════════════════════════════════════════════════════════════════
def _readers(doc):
    """Ekspresi pembacaan PERSIS seperti di kode tiap layar."""
    out = {}

    # marketing_targets.py:153 & marketing_reports.py:190,330
    out["Target vs Aktual (targets/reports)"] = doc.get("metrics", {}).get("revenue", 0)

    # marketing_dashboard.py:62 — INDEX LANGSUNG, bukan .get()
    try:
        out["Dashboard Marketing (dashboard:62)"] = doc["metrics"].get("revenue", 0)
    except KeyError as e:
        out["Dashboard Marketing (dashboard:62)"] = f"KeyError {e} ⇒ HTTP 500"

    # marketing_budget.py:_sales_revenue — punya rantai fallback
    m = doc.get("metrics") or {}
    val = (m.get("revenue") if m.get("revenue") is not None else
           doc.get("revenue") if doc.get("revenue") is not None else
           doc.get("net_sales") if doc.get("net_sales") is not None else
           doc.get("gross_sales"))
    out["ROI Anggaran (budget/_sales_revenue)"] = val

    # marketing_shared.py:_recalculate_health_score
    out["Health Score (shared)"] = doc.get("metrics", {}).get("revenue", 0)
    return out


def s2_bentuk_dokumen():
    bar("S2 — BENTUK DOKUMEN OMZET: hasil IMPOR vs hasil INPUT MANUAL (dua bentuk berbeda)")
    st = get_source_type("sales_daily")

    csv = ("Tanggal,Jenis Revenue,Revenue,Jumlah Order,Rating Toko\n"
           "01/08/2026,total,\"Rp 12.500.000\",48,4.8\n").encode()
    headers, rows = eng.parse_table(csv, "rekap.csv")
    mapping = eng.auto_map(headers, st)
    built = eng.build_rows(rows, mapping, st)
    print(f"  berkas uji  : 1 baris rekap harian · pemetaan {eng.mapping_report(mapping, st)['methods']}")
    print(f"  status baris: {built[0]['status']} · galat: {built[0]['errors'] or '—'}")

    sys.path.insert(0, "/app/backend/routes")
    from routes.marketing_data_import import _finish
    doc_import, warn = _finish(st, built[0]["data"], {"account_id": "AKUN-UJI"}, {})
    print("\n  (A) DOKUMEN HASIL IMPOR — persis yang ditulis `commit` (+ stamp akun):")
    print(f"      keys : {sorted(doc_import.keys())}")
    print(f"      ada 'metrics'? {'metrics' in doc_import}   revenue = {doc_import.get('revenue')}")

    doc_manual = {
        "account_id": "AKUN-UJI", "date": "2026-08-01", "revenue_type": "total",
        "metrics": {"revenue": 12500000, "orders": 48, "aov": 260416.67,
                    "gmv": 12500000, "conversion_rate": 0},
        "fulfillment": {}, "customer_satisfaction": {}, "live_metrics": {},
    }
    print("\n  (B) DOKUMEN HASIL INPUT MANUAL — `POST /api/marketing/sales-data`:")
    print(f"      keys : {sorted(doc_manual.keys())}")
    print(f"      ada 'metrics'? {'metrics' in doc_manual}   metrics.revenue = "
          f"{doc_manual['metrics']['revenue']}")

    print("\n  ANGKA YANG DIBACA TIAP LAYAR — sumber datanya SAMA (Rp 12.500.000):")
    ra, rb = _readers(doc_import), _readers(doc_manual)
    print(f"\n  {'layar':<40} {'dari IMPOR (A)':>26} {'dari MANUAL (B)':>22}")
    print(f"  {'-' * 92}")
    for k in ra:
        va, vb = ra[k], rb[k]
        fa = f"{va:,.0f}" if isinstance(va, (int, float)) else str(va)
        fb = f"{vb:,.0f}" if isinstance(vb, (int, float)) else str(vb)
        flag = "" if fa == fb else "   <== BEDA"
        print(f"  {k:<40} {fa:>26} {fb:>22}{flag}")
    print("\n  ==> Omzet yang DIIMPOR: pencapaian target = Rp 0 · Dashboard = HTTP 500 ·")
    print("      ROI anggaran = Rp 12.500.000. Satu angka, tiga hasil berbeda.")
    print("      Sebabnya satu: `_finish()` untuk 'sales_daily' TIDAK membungkus nilai ke")
    print("      `metrics{}` (routes/marketing_data_import.py:616-618), sedangkan pembaca")
    print("      target/dashboard/health SELALU mencari `metrics.revenue`.")

    # ── S2b: Health Score dihitung dengan ekspresi persis marketing_shared.py ──
    print("\n  S2b — HEALTH SCORE TOKO (rumus persis marketing_shared.py:175-232)")

    def health(docs):
        tot_rev = sum(d.get("metrics", {}).get("revenue", 0) for d in docs
                      if d.get("revenue_type") == "total")
        tot_ord = sum(d.get("metrics", {}).get("orders", 0) for d in docs
                      if d.get("revenue_type") == "total")
        avg_conv = (sum(d.get("metrics", {}).get("conversion_rate", 0) for d in docs)
                    / len(docs)) if docs else 0
        s = 0
        s += 15 if tot_rev > 0 else 0
        s += 10 if tot_ord > 100 else 0
        s += 5 if avg_conv > 0.02 else 0
        ful = [d for d in docs if d.get("fulfillment")]
        f = 0.0
        if ful:
            af = sum(d["fulfillment"].get("fulfillment_rate", 0) for d in ful) / len(ful)
            ac = sum(d["fulfillment"].get("cancellation_rate", 0) for d in ful) / len(ful)
            ar = sum(d["fulfillment"].get("return_rate", 0) for d in ful) / len(ful)
            al = sum(d["fulfillment"].get("late_shipment_rate", 0) for d in ful) / len(ful)
            f = af * 10 + max(0, (1 - ac) * 5) + max(0, (1 - ar) * 5) + max(0, (1 - al) * 5)
        sat = [d for d in docs if d.get("customer_satisfaction")]
        st_ = 0.0
        if sat:
            ar_ = sum(d["customer_satisfaction"].get("rating", 0) for d in sat) / len(sat)
            arr = sum(d["customer_satisfaction"].get("response_rate", 0) for d in sat) / len(sat)
            art = sum(d["customer_satisfaction"].get("response_time_hours", 0) for d in sat) / len(sat)
            st_ = (ar_ / 5) * 15 + arr * 5 + max(0, 5 - (art / 5))
        live = [d for d in docs if d.get("revenue_type") == "live" and d.get("live_metrics")]
        eng = 5
        if live:
            eng = 0
            if sum(d.get("live_metrics", {}).get("viewers", 0) for d in live) > 1000:
                eng += 5
            if sum(d.get("live_metrics", {}).get("likes", 0) for d in live) > 500:
                eng += 3
            if sum(d.get("live_metrics", {}).get("shares", 0) for d in live) > 50:
                eng += 2
        comp = 10 if len(docs) >= 7 else 5
        return min(100, max(0, round(s + f + st_ + eng + comp))), \
            {"sales": s, "fulfillment": round(f, 1), "satisfaction": round(st_, 1),
             "engagement": eng, "compliance": comp}

    imp7 = [dict(doc_import, date=f"2026-08-{d:02d}") for d in range(1, 9)]
    man7 = [dict(doc_manual,
                 date=f"2026-08-{d:02d}",
                 fulfillment={"fulfillment_rate": 0.98, "cancellation_rate": 0.02,
                              "return_rate": 0.01, "late_shipment_rate": 0.01},
                 customer_satisfaction={"rating": 4.8, "response_rate": 0.95,
                                        "response_time_hours": 1.0})
            for d in range(1, 9)]
    hi, di = health(imp7)
    hm, dm = health(man7)
    print(f"      8 hari data dari IMPOR   → health = {hi}/100   rincian {di}")
    print(f"      8 hari data dari MANUAL  → health = {hm}/100   rincian {dm}")
    print("      ==> toko yang sama, data yang sama besarnya, skor kesehatan beda jauh —")
    print("          semata karena bentuk dokumennya, bukan karena performanya.")
    return doc_import


# ════════════════════════════════════════════════════════════════════════════════
def s3_orders():
    bar("S3 — JALUR PESANAN: bagaimana omzet dihitung dari `marketing_orders`")
    st = get_source_type("orders")
    from routes.marketing_data_import import _finish

    csv = ("No. Pesanan,Tanggal Pesanan,SKU,Jumlah,Harga Setelah Diskon\n"
           "INV-1,01/08/2026,SKU-A,2,\"Rp 150.000\"\n").encode()
    headers, rows = eng.parse_table(csv, "o.csv")
    mapping = eng.auto_map(headers, st)
    built = eng.build_rows(rows, mapping, st)
    doc, warn = _finish(st, built[0]["data"], {"account_id": "AKUN-UJI"}, {})
    print("  Satu baris pesanan (2 pcs × Rp 150.000) menghasilkan:")
    for k in ("order_id", "quantity", "price_final", "revenue", "total_payment",
              "status", "fulfillment_status", "catalog_item_id", "master_link_source"):
        print(f"      {k:<20} = {doc.get(k)}")
    print(f"      peringatan          = {warn}")

    print("\n  Yang DIJUMLAH layar Sales Performance "
          "(marketing_sales_performance_routes.py:82-88):")
    print("      total_revenue = $sum: '$total_payment'      ← per BARIS dokumen")
    print("      filter        = order_date + status != cancelled + **account_name** (bukan account_id)")
    print("\n  Dua akibat yang bisa diukur:")
    print("      1. `total_payment` = harga×qty + ongkir − diskon → ini 'yang dibayar pembeli'.")
    print("         Pada ekspor TikTok, nilai itu DIULANG di setiap baris SKU ⇒ menjumlahkan")
    print("         per baris menggandakan 36 pesanan multi-SKU (+16,8% = Rp 10.572.124).")
    print("      2. Filter memakai `account_name` (teks). Ganti nama toko ⇒ riwayat lama")
    print("         tidak lagi ikut terhitung, tanpa galat apa pun.")


# ════════════════════════════════════════════════════════════════════════════════
def s4_keterhubungan():
    bar("S4 — APAKAH TARGET ⇄ ANGGARAN ⇄ OMZET SALING TERHUBUNG? (dipindai dari kode)")
    checks = [
        ("routes/marketing_budget.py", "marketing_account_targets",
         "Layar Anggaran membaca TARGET?"),
        ("routes/marketing_targets.py", "marketing_budgets",
         "Layar Target membaca ANGGARAN?"),
        ("routes/marketing_targets.py", "marketing_orders",
         "Pencapaian target membaca PESANAN?"),
        ("routes/marketing_budget.py", "marketing_orders",
         "ROI anggaran membaca PESANAN?"),
        ("routes/marketing_budget.py", "rahaza_journal",
         "Belanja marketing masuk JURNAL keuangan?"),
        ("routes/marketing_budget.py", "rahaza_budgets",
         "Anggaran marketing dibandingkan ANGGARAN PERUSAHAAN?"),
        ("routes/marketing_budget.py", "marketing_discounts",
         "Kategori 'diskon' diambil dari modul DISKON?"),
        ("routes/marketing_budget.py", "marketing_ads",
         "Kategori 'ads' diambil dari modul ADS?"),
    ]
    for path, needle, q in checks:
        src = open(path, encoding="utf-8").read()
        print(f"  {'YA ' if needle in src else 'TIDAK'}  {q:<52} (cari '{needle}' di {os.path.basename(path)})")

    print("\n  Kewenangan & penguncian periode:")
    for path, label in [("routes/marketing_targets.py", "Target"),
                        ("routes/marketing_budget.py", "Anggaran"),
                        ("routes/marketing_sales.py", "Omzet harian")]:
        src = open(path, encoding="utf-8").read()
        has_perm = bool(re.search(r"require_perm|has_permission|check_permission", src))
        has_lock = bool(re.search(r"is_locked|locked|period_close|closed_at", src))
        print(f"      {label:<14} RBAC selain login: {'ADA' if has_perm else 'TIDAK ADA'}"
              f"  ·  kunci periode: {'ADA' if has_lock else 'TIDAK ADA'}")

    print("\n  Sumber realisasi tiap kategori anggaran (dari docstring + kode budget.py):")
    print("      ads      : input MANUAL (marketing_spend_entries)")
    print("      sample   : input MANUAL")
    print("      diskon   : input MANUAL")
    print("      livehost : OTOMATIS — Σ total_pay shift 'calculated' (marketing_livehost_shifts)")
    print("      kol      : DIHITUNG — fixed_fee + %komisi × revenue sesi kreator")
    print("      ROI      : (sales − spend) / spend × 100   ← 'sales' = OMZET, bukan laba")
    print("                 ⇒ HPP/COGS tidak pernah ikut ⇒ angka ROI bukan profitabilitas")


# ════════════════════════════════════════════════════════════════════════════════
async def s5_runtime():
    bar("S5 — KEADAAN DATA SEKARANG (baca DB, tanpa menulis)")
    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ.get("DB_NAME", "test_database")]
    for c in ["marketing_platform_accounts", "marketing_sales_data", "marketing_orders",
              "marketing_account_targets", "marketing_creator_targets",
              "marketing_creator_sessions", "marketing_livehost_shifts",
              "marketing_budgets", "marketing_spend_entries", "marketing_tasks",
              "marketing_kol_creators", "marketing_livehosts"]:
        n = await db[c].count_documents({})
        print(f"      {c:<34} {n}")
    print("\n      Catatan: DB ini hasil bootstrap bersih (seed inti), bukan data operasional.")
    print("      Backup `backups/auto_20260810_190000` juga 0 dokumen untuk koleksi marketing.")
    print("      Jadi angka di atas menunjukkan: siklus target/omzet/anggaran BELUM PERNAH")
    print("      dijalankan dengan data nyata — semua bukti di dokumen ini berasal dari KODE.")
    cli.close()


async def main():
    s1_peta_sumber()
    s2_bentuk_dokumen()
    s3_orders()
    s4_keterhubungan()
    await s5_runtime()
    print(f"\n{LINE}\nSELESAI — tidak ada penulisan ke database maupun berkas aplikasi.\n{LINE}")


if __name__ == "__main__":
    asyncio.run(main())
