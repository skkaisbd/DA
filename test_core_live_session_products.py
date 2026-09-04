#!/usr/bin/env python3
"""test_core_live_session_products.py — POC inti sesi ini (F18#3 + bugfix platform).

DUA HAL YANG DIBUKTIKAN BERKAS INI
----------------------------------
A. **`platform` & `account_name` pada Ulasan/Retur adalah TURUNAN master.**
   Uji terakhir sesi sebelumnya memperlihatkan `platform: None` pada setiap baris
   baru: modelnya sudah dibuat opsional, tetapi endpoint-nya masih menyimpan apa
   yang dikirim layar. Akibatnya filter & kartu "per platform" kehilangan seluruh
   baris baru tanpa satu pun error.
B. **Rincian produk per sesi live bisa DIISI, direkonsiliasi, dan MUNCUL di
   analitik.** Sebelum ini `GET /live/analytics/product-performance` membaca
   `products[]` yang tidak punya satu pun jalan pengisian ⇒ selalu kosong.

Dijalankan langsung terhadap server nyata (bukan mock):
    python3 test_core_live_session_products.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from pymongo import MongoClient

BASE = os.environ.get("API_BASE", "http://localhost:8001")
EMAIL = os.environ.get("TEST_EMAIL", "admin@garment.com")
PASSWORD = os.environ.get("TEST_PASSWORD", "Admin@123")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database").strip('"')

PASS, FAIL = 0, 0
FAILURES: list[str] = []
TAG = "UJI-F18-3"


def ok(name: str, cond: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  \033[92mLULUS\033[0m  {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        FAILURES.append(f"{name} — {detail}")
        print(f"  \033[91mGAGAL\033[0m  {name} — {detail}")
    return cond


def section(title: str) -> None:
    print(f"\n\033[96m=== {title} ===\033[0m")


class Api:
    def __init__(self):
        self.s = requests.Session()
        self.token = ""

    def login(self):
        r = self.s.post(f"{BASE}/api/auth/login",
                        json={"email": EMAIL, "password": PASSWORD}, timeout=30)
        r.raise_for_status()
        self.token = r.json().get("access_token") or r.json().get("token")
        self.s.headers.update({"Authorization": f"Bearer {self.token}"})
        return self.token

    def get(self, path, **kw):
        return self.s.get(f"{BASE}{path}", timeout=60, **kw)

    def post(self, path, **kw):
        return self.s.post(f"{BASE}{path}", timeout=90, **kw)

    def put(self, path, **kw):
        return self.s.put(f"{BASE}{path}", timeout=60, **kw)

    def delete(self, path, **kw):
        return self.s.delete(f"{BASE}{path}", timeout=60, **kw)


def body(r):
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text[:400]}


def detail(r):
    d = body(r)
    return str(d.get("detail") or d)[:220]


# ═══════════════════════════════════════════════════════════════════════════════
def main() -> int:
    api = Api()
    section("0 · Login & data master")
    api.login()
    ok("login admin", bool(api.token), f"token {len(api.token)} char")

    accounts = body(api.get("/api/marketing/accounts"))
    if isinstance(accounts, dict):
        accounts = accounts.get("accounts") or accounts.get("data") or []
    ok("ada minimal 2 akun toko", len(accounts) >= 2, f"{len(accounts)} akun")
    acc_a, acc_b = accounts[0], accounts[1]

    def items_of(acc_id):
        cats = body(api.get("/api/marketing/catalogs", params={"account_id": acc_id}))
        cats = cats.get("catalogs") or cats.get("data") or []
        out = []
        for c in cats:
            r = body(api.get(f"/api/marketing/catalogs/{c['id']}/items",
                             params={"page_size": 200}))
            out += (r.get("items") or r.get("data") or [])
        return out

    items_a, items_b = items_of(acc_a["id"]), items_of(acc_b["id"])
    ok("katalog toko A punya item", len(items_a) >= 3, f"{len(items_a)} item")
    ok("katalog toko B punya item", len(items_b) >= 1, f"{len(items_b)} item")

    ctx = body(api.get("/api/marketing/data-import/context-options",
                       params={"source_type": "live_sessions",
                               "account_id": acc_a["id"]}))
    hosts = ctx.get("hosts") or []
    ok("ada host ter-assign ke toko A", len(hosts) >= 1, f"{len(hosts)} host")
    if not (items_a and items_b and hosts):
        print("\n\033[91mData master belum cukup — hentikan.\033[0m")
        return 1
    host = hosts[0]

    # ══════════════════════════════════════════════════════════════════════════
    section("A · `platform` & `account_name` WAJIB turunan master (Ulasan & Retur)")
    today = datetime.now(timezone.utc).date().isoformat()

    # A1 — tanpa account_id harus DITOLAK dengan pesan yang bisa ditindaklanjuti
    r = api.post("/api/marketing/reviews", json={
        "date": today, "order_id": f"{TAG}-NOACC", "rating": 4,
        "review_text": "tanpa toko", "product": "apa saja"})
    ok("ulasan tanpa account_id ditolak 400", r.status_code == 400, detail(r))

    r = api.post("/api/marketing/returns", json={
        "date": today, "order_id": f"{TAG}-NOACC", "price": 100000,
        "reason": "barang_rusak", "reason_detail": "x", "courier": "jnt",
        "product": "apa saja"})
    ok("retur tanpa account_id ditolak 400", r.status_code == 400, detail(r))

    # A2 — platform yang DIKIRIM SALAH tidak boleh tersimpan
    wrong_platform = "tiktok" if acc_a.get("platform") != "tiktok" else "shopee"
    r = api.post("/api/marketing/reviews", json={
        "account_id": acc_a["id"], "account_name": "NAMA NGAWUR",
        "platform": wrong_platform, "date": today, "order_id": f"{TAG}-REV",
        "rating": 4, "review_text": "uji turunan platform",
        "catalog_item_id": items_a[0]["id"]})
    rev = body(r).get("data", {})
    review_id = rev.get("id")
    ok("ulasan tersimpan", r.status_code == 200 and bool(review_id), detail(r))
    ok("ulasan: platform = platform master (bukan yang dikirim)",
       rev.get("platform") == acc_a.get("platform"),
       f"tersimpan {rev.get('platform')!r}, master {acc_a.get('platform')!r}, "
       f"dikirim {wrong_platform!r}")
    ok("ulasan: account_name = nama master (bukan 'NAMA NGAWUR')",
       rev.get("account_name") == acc_a.get("account_name"),
       f"tersimpan {rev.get('account_name')!r}")
    ok("ulasan: produk & SKU ikut katalog",
       rev.get("product") == items_a[0]["name"] and rev.get("sku") == items_a[0]["sku"],
       f"{rev.get('product')!r} / {rev.get('sku')!r}")

    r = api.post("/api/marketing/returns", json={
        "account_id": acc_a["id"], "account_name": "NAMA NGAWUR",
        "platform": wrong_platform, "date": today, "order_id": f"{TAG}-RET",
        "price": 98000, "reason": "barang_rusak", "reason_detail": "uji",
        "courier": "jnt", "catalog_item_id": items_a[0]["id"]})
    ret = body(r).get("data", {})
    return_id = ret.get("id")
    ok("retur tersimpan", r.status_code == 200 and bool(return_id), detail(r))
    ok("retur: platform = platform master",
       ret.get("platform") == acc_a.get("platform"),
       f"tersimpan {ret.get('platform')!r}")
    ok("retur: produk & SKU ikut katalog",
       ret.get("product") == items_a[0]["name"] and ret.get("sku") == items_a[0]["sku"],
       f"{ret.get('product')!r} / {ret.get('sku')!r}")

    # A3 — item katalog toko LAIN harus ditolak
    r = api.post("/api/marketing/reviews", json={
        "account_id": acc_a["id"], "date": today, "order_id": f"{TAG}-XACC",
        "rating": 3, "review_text": "produk toko lain",
        "catalog_item_id": items_b[0]["id"]})
    ok("ulasan dengan item katalog toko lain ditolak",
       r.status_code == 400, f"{r.status_code} {detail(r)}")

    # A4 — PUT tidak boleh menimpa platform dengan teks bebas
    if review_id:
        r = api.put(f"/api/marketing/reviews/{review_id}",
                    json={"platform": wrong_platform, "account_name": "DIUBAH PAKSA",
                          "rating": 5})
        upd = body(r).get("data", {})
        ok("ubah ulasan: platform tetap turunan master",
           upd.get("platform") == acc_a.get("platform"),
           f"jadi {upd.get('platform')!r}")
        ok("ubah ulasan: account_name tetap master",
           upd.get("account_name") == acc_a.get("account_name"),
           f"jadi {upd.get('account_name')!r}")

    # bersihkan baris uji
    if review_id:
        api.delete(f"/api/marketing/reviews/{review_id}")
    if return_id:
        api.delete(f"/api/marketing/returns/{return_id}")

    # ══════════════════════════════════════════════════════════════════════════
    section("B1 · Catat sesi live BESERTA rincian produknya (satu simpan)")
    sess_date = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    it1, it2, it3 = items_a[0], items_a[1], items_a[2]
    payload = {
        "account_id": acc_a["id"], "host_id": host["id"],
        "session_date": sess_date, "title": f"{TAG} Live Uji Rincian",
        "duration_minutes": 90, "peak_viewers": 500, "total_viewers": 1200,
        "likes": 300, "comments": 120, "shares": 40,
        "orders": 20, "revenue": 3000000, "units_sold": 25,
        "status": "completed", "notes_text": "sesi uji",
        "products": [
            {"catalog_item_id": it1["id"], "units_sold": 10, "revenue": 980000, "orders": 8},
            {"catalog_item_id": it2["id"], "units_sold": 5, "revenue": 600000, "orders": 5},
            {"catalog_item_id": it3["id"], "units_sold": 0, "revenue": 0, "orders": 0},
        ],
    }
    r = api.post("/api/marketing/live/sessions", json=payload)
    d = body(r).get("data", {})
    session_id = d.get("id")
    ok("sesi live + 3 baris rincian tersimpan",
       r.status_code in (200, 201) and len(d.get("products") or []) == 3,
       f"{r.status_code} · {len(d.get('products') or [])} baris · {detail(r)}")
    rec = d.get("products_reconciliation") or {}
    ok("rekonsiliasi: total rincian = 1.580.000",
       rec.get("total_revenue") == 1580000, f"{rec.get('total_revenue')}")
    ok("rekonsiliasi: sisa belum terinci = 1.420.000",
       rec.get("unallocated_revenue") == 1420000, f"{rec.get('unallocated_revenue')}")
    ok("rekonsiliasi: status 'sebagian' + pesan bisa ditindaklanjuti",
       rec.get("status") == "sebagian" and "belum terinci" in (rec.get("message") or ""),
       f"{rec.get('status')} · {str(rec.get('message'))[:80]}")
    ok("baris 'dibawakan tapi tidak terjual' (0 unit) diizinkan",
       any((p.get("units_sold") == 0) for p in (d.get("products") or [])), "")
    lines = {p["catalog_item_id"]: p for p in (d.get("products") or [])}
    l1 = lines.get(it1["id"], {})
    ok("harga rata-rata dihitung server (98.000)", l1.get("price_avg") == 98000,
       f"{l1.get('price_avg')}")
    ok("nama & SKU produk ikut master",
       l1.get("product_name") == it1["name"] and l1.get("sku") == it1["sku"], "")
    ok("HPP & margin kotor dihitung dari master",
       l1.get("hpp") == it1.get("hpp")
       and l1.get("gross_margin") == round(980000 - (it1.get("hpp") or 0) * 10, 2),
       f"hpp {l1.get('hpp')} margin {l1.get('gross_margin')}")
    ok("lingkup toko diwarisi dari sesi",
       l1.get("account_id") == acc_a["id"] and l1.get("platform") == acc_a.get("platform"),
       f"{l1.get('account_id')} / {l1.get('platform')}")

    if not session_id:
        print("\n\033[91mSesi uji gagal dibuat — hentikan.\033[0m")
        return 1

    section("B2 · Aturan yang harus DITOLAK (bukan disimpan diam-diam)")
    r = api.post(f"/api/marketing/live/sessions/{session_id}/products",
                 json={"catalog_item_id": it1["id"], "units_sold": 1, "revenue": 1000})
    ok("produk yang sama dua kali pada satu sesi ditolak",
       r.status_code == 400, f"{r.status_code} {detail(r)}")

    r = api.post(f"/api/marketing/live/sessions/{session_id}/products",
                 json={"catalog_item_id": items_b[0]["id"], "units_sold": 1,
                       "revenue": 1000})
    ok("produk dari katalog toko lain ditolak",
       r.status_code == 400, f"{r.status_code} {detail(r)}")

    r = api.post(f"/api/marketing/live/sessions/{session_id}/products",
                 json={"catalog_item_id": items_a[3]["id"] if len(items_a) > 3 else it3["id"],
                       "units_sold": 0, "revenue": 500000})
    ok("omzet > 0 dengan 0 unit terjual ditolak",
       r.status_code == 400, f"{r.status_code} {detail(r)}")

    r = api.post(f"/api/marketing/live/sessions/{session_id}/products",
                 json={"catalog_item_id": items_a[3]["id"] if len(items_a) > 3 else it3["id"],
                       "units_sold": 50, "revenue": 9000000})
    ok("rincian yang MELEBIHI omzet sesi ditolak (uang tidak dihitung dua kali)",
       r.status_code == 400 and "MELEBIHI" in detail(r).upper(),
       f"{r.status_code} {detail(r)}")

    section("B3 · Ubah · hapus · samakan total sesi")
    r = api.put(f"/api/marketing/live/sessions/{session_id}/products/{l1['id']}",
                json={"units_sold": 20, "revenue": 1960000})
    up = body(r).get("data", {}).get("product", {})
    ok("ubah baris rincian menghitung ulang harga rata-rata",
       r.status_code == 200 and up.get("price_avg") == 98000,
       f"{r.status_code} · {up.get('price_avg')}")

    r = api.get(f"/api/marketing/live/sessions/{session_id}/products")
    got = body(r).get("data", {})
    ok("daftar rincian bisa dibaca ulang",
       r.status_code == 200 and len(got.get("products") or []) == 3,
       f"{len(got.get('products') or [])} baris")

    l3 = [p for p in got["products"] if p["catalog_item_id"] == it3["id"]][0]
    r = api.delete(f"/api/marketing/live/sessions/{session_id}/products/{l3['id']}")
    ok("hapus satu baris rincian", r.status_code == 200
       and body(r).get("reconciliation", {}).get("lines_count") == 2,
       detail(r))

    r = api.post(f"/api/marketing/live/sessions/{session_id}/products/sync-session-totals")
    sync = body(r).get("data", {})
    ok("samakan total sesi: omzet sesi = jumlah rincian",
       r.status_code == 200
       and sync.get("after", {}).get("revenue") == 2560000,
       f"{r.status_code} · sebelum {sync.get('before', {}).get('revenue')} → "
       f"sesudah {sync.get('after', {}).get('revenue')}")
    ok("sesudah disamakan, status rekonsiliasi = 'lengkap'",
       (sync.get("reconciliation") or {}).get("status") == "lengkap",
       f"{(sync.get('reconciliation') or {}).get('status')}")

    section("B4 · Daftar sesi memuat ringkasan rincian (untuk kolom tabel)")
    r = api.get("/api/marketing/live/sessions",
                params={"account_id": acc_a["id"], "page_size": 20})
    sessions = body(r).get("data", {}).get("sessions") or []
    mine = [s for s in sessions if s.get("id") == session_id]
    ok("sesi uji muncul di daftar per toko", len(mine) == 1, f"{len(sessions)} sesi")
    if mine:
        pd = mine[0].get("products_detail") or {}
        ok("ringkasan rincian ikut di daftar (2 item · Rp 2.560.000)",
           pd.get("lines_count") == 2 and pd.get("total_revenue") == 2560000,
           json.dumps(pd))
        ok("ringkasan: cakupan 100% sesudah disamakan",
           pd.get("coverage_pct") == 100.0, f"{pd.get('coverage_pct')}")

    section("B5 · Analitik 'Produk Terlaris saat Live' (dulu SELALU kosong)")
    r = api.get("/api/marketing/live/analytics/product-performance",
                params={"days": 30, "account_id": acc_a["id"], "limit": 20})
    pp = body(r)
    rows = pp.get("data") or []
    ok("product-performance mengembalikan data", r.status_code == 200 and len(rows) >= 2,
       f"{r.status_code} · {len(rows)} produk · sumber {pp.get('source')}")
    ok("sumber data = koleksi rincian produk (bukan tebakan)",
       pp.get("source") == "live_session_products", f"{pp.get('source')}")
    top = rows[0] if rows else {}
    ok("produk teratas memakai SKU & nama master",
       bool(top.get("sku")) and bool(top.get("name")), json.dumps(top)[:160])
    ok("metrik lengkap (unit · omzet · sesi · harga rata-rata · pangsa)",
       all(k in top for k in ("total_units_sold", "total_revenue", "sessions_featured",
                             "avg_price", "revenue_share_pct")), "")
    ok("nama toko ikut di baris (katalog antar toko boleh pakai SKU sama)",
       bool(top.get("account_name")), f"{top.get('account_name')!r}")
    ok("total blok totals konsisten dengan baris",
       (pp.get("totals") or {}).get("revenue") == round(sum(x["total_revenue"] for x in rows), 2),
       f"{(pp.get('totals') or {}).get('revenue')}")

    # filter toko HARUS berpengaruh (dulu diterima tapi diabaikan).
    # Catatan: SKU demo SENGAJA sama antar toko (katalog tiap toko memakai 6 SKU
    # yang sama dengan id item berbeda), jadi yang dibandingkan adalah
    # `catalog_item_id` — bukan SKU — supaya uji ini menguji lingkup, bukan ejaan.
    ids_a = {i["id"] for i in items_a}
    ok("filter account_id BENAR-BENAR menyaring (dulu diabaikan)",
       bool(rows) and all(x.get("catalog_item_id") in ids_a for x in rows),
       f"{len(rows)} baris, semua milik katalog toko A")
    r_all = api.get("/api/marketing/live/analytics/product-performance",
                    params={"days": 30, "limit": 50})
    tot_all = (body(r_all).get("totals") or {}).get("revenue") or 0
    tot_a = (pp.get("totals") or {}).get("revenue") or 0
    ok("tanpa filter toko, angkanya LEBIH BESAR daripada satu toko",
       tot_all >= tot_a, f"semua toko {tot_all} vs toko A {tot_a}")

    r_p = api.get("/api/marketing/live/analytics/product-performance",
                  params={"days": 30, "platform": "platform-yang-tidak-ada"})
    ok("filter platform tidak dikenal → kosong + pesan bisa ditindaklanjuti",
       (body(r_p).get("data") == []) and bool(body(r_p).get("note")),
       str(body(r_p).get("note"))[:110])

    # ══════════════════════════════════════════════════════════════════════════
    section("C · Impor tanpa AI: 'Rincian Produk per Sesi Live'")
    types = body(api.get("/api/marketing/data-import/source-types")).get("source_types") or []
    keys = [t["key"] for t in types]
    ok("jenis data baru terdaftar di wizard", "live_session_products" in keys,
       f"{len(keys)} jenis")

    cx = body(api.get("/api/marketing/data-import/context-options",
                      params={"source_type": "live_session_products",
                              "account_id": acc_a["id"]}))
    ok("context-options mengembalikan daftar sesi live per toko",
       len(cx.get("live_sessions") or []) >= 1,
       f"{len(cx.get('live_sessions') or [])} sesi")
    ok("konteks yang diminta = live_session", cx.get("context") == ["live_session"],
       f"{cx.get('context')}")

    r = api.get("/api/marketing/data-import/template/live_session_products",
                params={"fmt": "csv"})
    ok("template CSV bisa diunduh", r.status_code == 200 and len(r.content) > 30,
       f"{r.status_code} · {len(r.content)} byte")

    # unggah tanpa memilih sesi → harus ditolak
    csv_min = "SKU;Terjual;Omzet\n" + f"{it1['sku']};1;Rp 98.000\n"
    r = api.post("/api/marketing/data-import/upload",
                 data={"source_type": "live_session_products", "account_id": acc_a["id"]},
                 files={"file": ("x.csv", csv_min.encode(), "text/csv")})
    ok("unggah tanpa live_session_id ditolak 400", r.status_code == 400, detail(r))

    # sesi kedua sebagai tujuan impor (biar sesi pertama tetap 'lengkap')
    r = api.post("/api/marketing/live/sessions", json={
        "account_id": acc_a["id"], "host_id": host["id"], "session_date": sess_date,
        "title": f"{TAG} Live Uji Impor", "duration_minutes": 60,
        "total_viewers": 800, "peak_viewers": 300, "orders": 10,
        "revenue": 5000000, "status": "completed"})
    sess2 = body(r).get("data", {}).get("id")
    ok("sesi kedua (tujuan impor) dibuat", bool(sess2), detail(r))

    # berkas gaya ekspor marketplace: header Indonesia + angka rupiah + 1 SKU ngawur
    csv_txt = (
        "Nama Produk;Kode SKU;Jumlah Terjual;Total Penjualan;Jumlah Pesanan\n"
        f"{it1['name']};{it1['sku']};12;Rp 1.176.000;10\n"
        f"{it2['name']};{it2['sku']};4;Rp 480.000;4\n"
        "Produk Karangan;SKU-TIDAK-ADA;3;Rp 300.000;3\n"
    )
    r = api.post("/api/marketing/data-import/upload",
                 data={"source_type": "live_session_products",
                       "account_id": acc_a["id"], "live_session_id": sess2},
                 files={"file": ("rincian-live.csv", csv_txt.encode("utf-8"), "text/csv")})
    up = body(r)
    imp_id = (up.get("session") or {}).get("id")
    ok("unggah berhasil & pemetaan siap tanpa AI",
       r.status_code == 200 and (up.get("session") or {}).get("mapping_report", {}).get("ready"),
       f"{r.status_code} {detail(r)}")
    ok("5/5 kolom terpetakan otomatis (tanpa AI)",
       sum(1 for m in ((up.get("session") or {}).get("mapping") or []) if m.get("field")) == 5,
       json.dumps([(m.get("column"), m.get("field"), m.get("method"))
                   for m in ((up.get("session") or {}).get("mapping") or [])]))
    ok("angka gaya Indonesia terbaca ('Rp 1.176.000' → 1176000)",
       any((row.get("data") or {}).get("revenue") == 1176000
           for row in (up.get("preview") or [])), "")
    summ = up.get("summary") or {}
    ok("baris dengan SKU tak dikenal ditandai GALAT di pratinjau (bukan saat commit)",
       summ.get("error") == 1 and summ.get("valid") == 2, json.dumps(summ))

    r = api.post(f"/api/marketing/data-import/sessions/{imp_id}/commit", json={})
    cm = body(r)
    ok("commit: 2 baris masuk, 1 ditolak",
       r.status_code == 200 and cm.get("inserted") == 2 and cm.get("rejected") == 1,
       f"{r.status_code} · {json.dumps({k: cm.get(k) for k in ('inserted', 'rejected', 'updated')})}")
    ok("koleksi tujuan benar", cm.get("target_collection") == "marketing_live_session_products",
       f"{cm.get('target_collection')}")

    r = api.get(f"/api/marketing/live/sessions/{sess2}/products")
    got2 = body(r).get("data", {})
    ok("rincian hasil impor menempel pada sesi yang DIPILIH",
       len(got2.get("products") or []) == 2, f"{len(got2.get('products') or [])} baris")
    ok("baris impor tertaut item katalog (bukan teks bebas)",
       all(p.get("catalog_item_id") for p in (got2.get("products") or [])), "")

    r = api.get("/api/marketing/live/analytics/product-performance",
                params={"days": 30, "account_id": acc_a["id"], "limit": 20})
    rows2 = body(r).get("data") or []
    tot2 = (body(r).get("totals") or {}).get("revenue")
    ok("analitik ikut naik sesudah impor",
       tot2 and tot2 > (pp.get("totals") or {}).get("revenue", 0),
       f"{(pp.get('totals') or {}).get('revenue')} → {tot2}")
    ok("produk yang sama pada 2 sesi digabung jadi 1 baris",
       any(x.get("sessions_featured", 0) >= 2 for x in rows2),
       json.dumps([(x["sku"], x["sessions_featured"]) for x in rows2])[:180])

    # commit yang akan melebihi omzet sesi → ditolak SEBELUM menulis
    over_csv = ("Kode SKU;Jumlah Terjual;Total Penjualan\n"
                f"{it3['sku']};100;Rp 90.000.000\n")
    r = api.post("/api/marketing/data-import/upload",
                 data={"source_type": "live_session_products",
                       "account_id": acc_a["id"], "live_session_id": sess2},
                 files={"file": ("over.csv", over_csv.encode(), "text/csv")})
    over_id = (body(r).get("session") or {}).get("id")
    r = api.post(f"/api/marketing/data-import/sessions/{over_id}/commit", json={})
    ok("commit yang melebihi omzet sesi ditolak SEBELUM menulis",
       r.status_code == 400 and "MELEBIHI" in detail(r).upper(),
       f"{r.status_code} {detail(r)}")
    r = api.get(f"/api/marketing/live/sessions/{sess2}/products")
    ok("tidak ada baris setengah tersimpan dari commit yang gagal",
       len(body(r).get("data", {}).get("products") or []) == 2, "")

    r = api.post(f"/api/marketing/data-import/sessions/{imp_id}/rollback")
    ok("rollback impor menghapus tepat 2 baris",
       r.status_code == 200 and body(r).get("deleted") == 2,
       f"{r.status_code} · {body(r).get('deleted')}")
    r = api.get(f"/api/marketing/live/sessions/{sess2}/products")
    ok("sesudah rollback rincian sesi itu kosong kembali",
       (body(r).get("data", {}).get("products") or []) == [], "")

    # ══════════════════════════════════════════════════════════════════════════
    section("D · Hapus sesi tidak meninggalkan baris yatim")
    mdb = MongoClient(MONGO_URL)[DB_NAME]
    before = mdb.marketing_live_session_products.count_documents({"session_id": session_id})
    ok("sesi uji punya baris rincian sebelum dihapus", before == 2, f"{before} baris")
    r = api.delete(f"/api/marketing/live/sessions/{session_id}")
    ok("hapus sesi live", r.status_code == 200, detail(r))
    after = mdb.marketing_live_session_products.count_documents({"session_id": session_id})
    ok("baris rincian ikut terhapus (cascade)", after == 0, f"{after} baris tersisa")
    api.delete(f"/api/marketing/live/sessions/{sess2}")
    orphan = mdb.marketing_live_session_products.count_documents(
        {"session_id": {"$nin": [s["id"] for s in
                                 mdb.marketing_live_sessions.find({}, {"id": 1})]}})
    ok("tidak ada baris rincian yatim di seluruh koleksi", orphan == 0, f"{orphan} yatim")

    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print(f"  \033[92m{PASS} LULUS\033[0m / \033[91m{FAIL} GAGAL\033[0m")
    if FAILURES:
        print("\n  Yang gagal:")
        for f in FAILURES:
            print(f"   · {f}")
    print("=" * 72)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.HTTPError as e:
        print(f"\033[91mHTTP error: {e} — {getattr(e.response, 'text', '')[:300]}\033[0m")
        sys.exit(2)
