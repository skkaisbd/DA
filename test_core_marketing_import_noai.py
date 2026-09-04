#!/usr/bin/env python3
"""
POC — IMPOR DATA MARKETING TANPA AI (F17) + LINGKUP TOKO (F14).

Membuktikan (bukan mengklaim) user story Phase 1 `plan.md`:

  US-1  staf MEMILIH jenis data impor (tidak ditebak mesin)
  US-2  toko/akun WAJIB dipilih untuk jenis data berlingkup toko
  US-3  untuk sesi live: host dipilih dari yang SUDAH di-assign ke toko itu
        (host yang belum di-assign HARUS ditolak)
  US-4  template CSV/XLSX bisa diunduh per jenis data
  US-5  pratinjau valid/warning/error sebelum commit, dan bisa rollback

Ditambah pembuktian cacat yang diperbaiki:
  P-1   pemetaan kolom berjalan TANPA AI (exact → sinonim → fuzzy)
  P-2   angka gaya Indonesia ("Rp 1.250.000", "12,5%") terbaca benar
  P-3   commit MENULIS `account_id` (akar cacat 60/60 order tanpa lingkup toko)
  P-4   commit menulis ke KOLEKSI YANG BENAR (bukan marketing_discount_campaigns
        / marketing_sample_shipments seperti mesin lama)
  P-5   impor ulang berkas yang sama TIDAK menggandakan baris (dedupe)
  P-6   rollback hanya menghapus baris milik sesi itu
  P-7   kolom yang tak dikenali → sesi berstatus `mapping`, dan mapping manual
        membuatnya `ready` (tanpa AI sama sekali)

Jalankan:  python3 test_core_marketing_import_noai.py
"""
import io
import os
import sys
import json
import time
import uuid

import requests

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
API = f"{BASE}/api"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
MARK = "POCIMP"          # penanda agar data uji bisa dibersihkan
OK, FAIL = [], []
GAPS = []   # kesenjangan yang SENGAJA ditunda ke fase berikutnya (dicatat, bukan disembunyikan)


def say(msg):
    print(msg, flush=True)


def check(name, cond, detail=""):
    if cond:
        OK.append(name)
        say(f"  ✅ {name}")
    else:
        FAIL.append((name, detail))
        say(f"  ❌ {name}\n       {detail}")
    return bool(cond)


class C:
    def __init__(self):
        self.s = requests.Session()
        self.token = None

    def login(self):
        r = self.s.post(f"{API}/auth/login", json=ADMIN, timeout=60)
        r.raise_for_status()
        self.token = r.json().get("token") or r.json().get("access_token")
        self.s.headers["Authorization"] = f"Bearer {self.token}"
        return self.token

    def get(self, p, **kw):
        return self.s.get(f"{API}{p}", timeout=120, **kw)

    def post(self, p, **kw):
        return self.s.post(f"{API}{p}", timeout=180, **kw)

    def put(self, p, **kw):
        return self.s.put(f"{API}{p}", timeout=120, **kw)

    def delete(self, p, **kw):
        return self.s.delete(f"{API}{p}", timeout=120, **kw)


c = C()
created = {"accounts": [], "hosts": [], "creators": [], "catalogs": [],
           "sessions": []}

# Konteks uji — diisi oleh step_master(), dipakai langkah-langkah sesudahnya.
ACC_ID = ""
HOST_ID = ""
OTHER_HOST_ID = ""
CREATOR_ID = ""
CATALOG_ID = ""
SKU = ""
SFX = ""
ADS_SESSION = ""
LIVE_SESSION = ""
MANUAL_SESSION = ""


# ══════════════════════════════════════════════════════════════════════════════
def step_login():
    say("\n[0] LOGIN")
    t = c.login()
    check("login admin", bool(t), "token kosong")


def step_master():
    """Data master minimal yang NYATA (dibuat lewat endpoint resmi, bukan disuntik DB)."""
    say("\n[1] SIAPKAN MASTER (akun · host · kreator · katalog + item)")
    sfx = uuid.uuid4().hex[:6].upper()

    # -- akun toko
    r = c.post("/marketing/accounts", json={
        "account_code": f"{MARK}-{sfx}",
        "account_name": f"{MARK} Toko Uji {sfx}",
        "platform": "shopee",
        "username": f"poc_{sfx.lower()}",
    })
    if not check("buat akun marketing", r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"):
        return False
    acc = r.json()
    acc_id = acc.get("id") or (acc.get("account") or {}).get("id")
    created["accounts"].append(acc_id)
    check("akun punya id", bool(acc_id), json.dumps(acc)[:200])

    # -- host live yang DI-ASSIGN ke akun ini
    r = c.post("/marketing/livehost", json={
        "name": f"{MARK} Host Terassign {sfx}",
        "email": f"host.{sfx.lower()}@poc.id",
        "password": "Poc@12345",
        "employment_type": "part_time",
        "hourly_rate": 25000,
        "assigned_account_ids": [acc_id],
    })
    if not check("buat host (assigned)", r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"):
        return False
    host = r.json()
    host_id = host.get("id") or (host.get("host") or {}).get("id")
    created["hosts"].append(host_id)

    # -- host live yang TIDAK di-assign (untuk membuktikan penolakan)
    r = c.post("/marketing/livehost", json={
        "name": f"{MARK} Host Lain {sfx}",
        "email": f"host.other.{sfx.lower()}@poc.id",
        "password": "Poc@12345",
        "employment_type": "part_time",
        "hourly_rate": 25000,
        "assigned_account_ids": [],
    })
    other_host = r.json() if r.status_code in (200, 201) else {}
    other_host_id = other_host.get("id") or (other_host.get("host") or {}).get("id")
    if other_host_id:
        created["hosts"].append(other_host_id)

    # -- kreator KOL yang di-assign
    r = c.post("/marketing/kol/creators", json={
        "name": f"{MARK} Kreator {sfx}",
        "creator_code": f"KOL-{MARK}-{sfx}",
        "login_email": f"kol.{sfx.lower()}@poc.id",
        "login_password": "Poc@12345",
        "assigned_account_ids": [acc_id],
        "platforms": {"tiktok": f"@poc{sfx.lower()}"},
    })
    if not check("buat kreator (assigned)", r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"):
        return False
    cr = r.json()
    creator_id = cr.get("id") or (cr.get("creator") or {}).get("id")
    created["creators"].append(creator_id)

    # -- katalog toko + 1 item (untuk membuktikan penautan SKU)
    r = c.post("/marketing/catalogs", json={
        "account_id": acc_id,
        "name": f"Katalog {MARK} {sfx}",
        "platform": "shopee",
    })
    if not check("buat katalog toko", r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"):
        return False
    kat = r.json()
    catalog_id = kat.get("id") or (kat.get("catalog") or {}).get("id")
    created["catalogs"].append(catalog_id)

    sku = f"{MARK}-SKU-{sfx}"
    r = c.post(f"/marketing/catalogs/{catalog_id}/items", json={
        "sku": sku,
        "name": f"Gamis Uji {sfx}",
        "harga_jual": 189000,
        "hpp": 92000,
        "stock_quantity": 25,
    })
    check("buat item katalog", r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}")

    globals()["ACC_ID"] = acc_id
    globals()["HOST_ID"] = host_id
    globals()["OTHER_HOST_ID"] = other_host_id
    globals()["CREATOR_ID"] = creator_id
    globals()["CATALOG_ID"] = catalog_id
    globals()["SKU"] = sku
    globals()["SFX"] = sfx
    return True


def step_source_types():
    say("\n[2] US-1 — staf MEMILIH jenis data (tidak ditebak mesin)")
    r = c.get("/marketing/data-import/source-types")
    if not check("GET /source-types 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}"):
        return
    types = r.json().get("source_types") or []
    check("jenis data ≥ 12", len(types) >= 12, f"hanya {len(types)}")
    keys = {t["key"] for t in types}
    for need in ("orders", "ads", "live_sessions", "sales_daily", "samples",
                 "discounts", "content_calendar", "catalog_items"):
        check(f"jenis '{need}' tersedia", need in keys, f"keys={sorted(keys)}")
    # tujuan koleksi harus benar (cacat mesin lama)
    by = {t["key"]: t for t in types}
    check("discounts → marketing_discounts (bukan marketing_discount_campaigns)",
          by.get("discounts", {}).get("collection") == "marketing_discounts",
          str(by.get("discounts", {}).get("collection")))
    check("samples → marketing_samples (bukan marketing_sample_shipments)",
          by.get("samples", {}).get("collection") == "marketing_samples",
          str(by.get("samples", {}).get("collection")))
    check("live_sessions menuntut konteks host",
          "host" in (by.get("live_sessions", {}).get("context") or []),
          str(by.get("live_sessions", {}).get("context")))
    check("setiap jenis menyebut kolom wajib",
          all(t.get("required_columns") for t in types if t["key"] != "kol_creators"),
          "ada jenis tanpa kolom wajib")


def step_template():
    say("\n[3] US-4 — template bisa diunduh per jenis data")
    for st, fmt, magic in (("orders", "xlsx", b"PK"), ("ads", "csv", None),
                           ("live_sessions", "xlsx", b"PK")):
        r = c.get(f"/marketing/data-import/template/{st}?fmt={fmt}")
        ok = r.status_code == 200 and len(r.content) > 100
        if magic:
            ok = ok and r.content[:2] == magic
        check(f"template {st}.{fmt}", ok,
              f"{r.status_code} len={len(r.content)}")
    r = c.get("/marketing/data-import/template/tidak_ada?fmt=csv")
    check("jenis data ngawur ditolak 400", r.status_code == 400, str(r.status_code))


def step_context():
    say("\n[4] US-2/US-3 — lingkup toko & host WAJIB, host disaring per toko")
    r = c.get(f"/marketing/data-import/context-options?source_type=live_sessions&account_id={ACC_ID}")
    if not check("GET /context-options 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}"):
        return
    j = r.json()
    host_ids = {h["id"] for h in (j.get("hosts") or [])}
    check("host ter-assign muncul di pilihan", HOST_ID in host_ids, str(host_ids))
    check("host yang TIDAK di-assign tidak muncul",
          OTHER_HOST_ID not in host_ids if OTHER_HOST_ID else True, str(host_ids))
    check("daftar akun tersedia untuk pemilih", len(j.get("accounts") or []) >= 1)


def _rows(body, *keys):
    """Ambil daftar baris dari bentuk respons apa pun yang dipakai repo ini.

    Repo memakai tiga bentuk berbeda: list langsung · {key: [...]} ·
    {success, data: {key: [...]}}. POC harus tahan ketiganya, kalau tidak
    kegagalan parsing akan disalahartikan sebagai cacat produk.
    """
    if isinstance(body, list):
        return body
    if not isinstance(body, dict):
        return []
    node = body.get("data") if isinstance(body.get("data"), (dict, list)) else body
    if isinstance(node, list):
        return node
    for k in keys + ("items", "results", "rows"):
        v = (node or {}).get(k)
        if isinstance(v, list):
            return v
    return []


def _upload(source_type, csv_text, filename="data.csv", **ctx):
    files = {"file": (filename, io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
    data = {"source_type": source_type}
    data.update({k: v for k, v in ctx.items() if v})
    return c.post("/marketing/data-import/upload", files=files, data=data)


def step_scope_enforced():
    say("\n[5] P-3 — data berlingkup toko DITOLAK kalau toko tidak dipilih")
    csv_ads = ("Tanggal,Nama Kampanye,Biaya Iklan,Klik,Impresi\n"
               "2026-08-01,Kampanye Uji,Rp 1.250.000,120,10.000\n")
    r = _upload("ads", csv_ads)
    check("upload iklan tanpa account_id → 400", r.status_code == 400,
          f"{r.status_code} {r.text[:200]}")
    r = _upload("live_sessions", "Tanggal Sesi,Judul,Durasi (menit),Revenue (Rp)\n"
                                "2026-08-01,Live Uji,120,Rp 8.500.000\n",
                account_id=ACC_ID)
    check("upload sesi live tanpa host_id → 400", r.status_code == 400,
          f"{r.status_code} {r.text[:200]}")
    if OTHER_HOST_ID:
        r = _upload("live_sessions", "Tanggal Sesi,Judul,Durasi (menit),Revenue (Rp)\n"
                                    "2026-08-01,Live Uji,120,Rp 8.500.000\n",
                    account_id=ACC_ID, host_id=OTHER_HOST_ID)
        check("host yang belum di-assign → 400 dengan alasan jelas",
              r.status_code == 400 and "assign" in r.text.lower(),
              f"{r.status_code} {r.text[:250]}")


def step_ads_noai():
    say("\n[6] P-1/P-2 — iklan: pemetaan tanpa AI + angka gaya Indonesia")
    csv_ads = (
        "Tanggal;Nama Kampanye;Biaya Iklan;Klik;Impresi;Konversi;Penjualan dari iklan\n"
        "01/08/2026;Flash Sale Gamis;Rp 1.250.000;1.240;120.500;38;Rp 9.870.000\n"
        "02/08/2026;Flash Sale Gamis B;750000;900;80000;21;5.400.000\n"
        "03/08/2026;Iklan Video;Rp 500.000;410;33.000;9;1.200.000\n"
    )
    r = _upload("ads", csv_ads, filename="iklan.csv", account_id=ACC_ID)
    if not check("upload iklan (dengan toko) 200", r.status_code == 200,
                 f"{r.status_code} {r.text[:400]}"):
        return
    j = r.json()
    sess = j["session"]
    created["sessions"].append(sess["id"])
    check("sesi TIDAK memakai AI", sess.get("ai_used") is False, str(sess.get("ai_used")))
    check("status sesi 'ready' (semua kolom wajib terpetakan)",
          sess.get("status") == "ready",
          f"{sess.get('status')} · report={json.dumps(sess.get('mapping_report'))}")
    rep = sess.get("mapping_report") or {}
    check("tidak ada kolom wajib yang belum terpetakan",
          not rep.get("missing_required"), str(rep.get("missing_required")))
    check("pemetaan via exact/synonym/fuzzy (bukan AI)",
          (rep.get("methods", {}).get("exact", 0) + rep.get("methods", {}).get("synonym", 0)
           + rep.get("methods", {}).get("fuzzy", 0)) >= 5, json.dumps(rep.get("methods")))
    summ = j.get("summary") or {}
    check("3 baris terbaca, 0 error", summ.get("total") == 3 and summ.get("error") == 0,
          json.dumps(summ))
    prev = j.get("preview") or []
    if prev:
        d0 = prev[0]["data"]
        check("Rp 1.250.000 → 1250000.0", d0.get("spend") == 1250000.0, str(d0.get("spend")))
        check("'1.240' → 1240 (ribuan, bukan 1.24)", d0.get("clicks") == 1240,
              str(d0.get("clicks")))
        check("'120.500' → 120500", d0.get("impressions") == 120500,
              str(d0.get("impressions")))
        check("tanggal 01/08/2026 terbaca", str(d0.get("date", "")).startswith("2026-08-01"),
              str(d0.get("date")))

    r = c.post(f"/marketing/data-import/sessions/{sess['id']}/commit", json={})
    if not check("commit iklan 200", r.status_code == 200, f"{r.status_code} {r.text[:400]}"):
        return
    cj = r.json()
    check("3 baris masuk", cj.get("inserted") == 3, json.dumps(cj)[:300])
    check("koleksi tujuan marketing_ads_data",
          cj.get("target_collection") == "marketing_ads_data", str(cj.get("target_collection")))

    # bukti P-3: hasil impor MUNCUL saat difilter per toko
    r = c.get(f"/marketing/ads/campaigns?account_id={ACC_ID}&page_size=100")
    if r.status_code == 200:
        rows = _rows(r.json(), "campaigns")
        mine = [x for x in rows if x.get("account_id") == ACC_ID]
        check("iklan hasil impor MEMBAWA account_id (akar cacat 25/25 kosong)",
              len(mine) >= 1,
              f"{len(mine)} dari {len(rows)} baris membawa account_id={ACC_ID}")
        if len(mine) and len(mine) != len(rows):
            GAPS.append("GET /api/marketing/ads/campaigns mengabaikan filter "
                        "?account_id= (kerjakan di Phase 2C)")
    else:
        check("GET /marketing/ads/campaigns jalan", False, f"{r.status_code} {r.text[:200]}")

    # bukti P-5: impor ulang berkas yang sama tidak menggandakan
    r2 = _upload("ads", csv_ads, filename="iklan.csv", account_id=ACC_ID)
    if r2.status_code == 200:
        s2 = r2.json()["session"]
        created["sessions"].append(s2["id"])
        rc = c.post(f"/marketing/data-import/sessions/{s2['id']}/commit", json={})
        if rc.status_code == 200:
            cj2 = rc.json()
            check("impor ulang: 0 baris baru, 3 duplikat dilewati",
                  cj2.get("inserted") == 0 and cj2.get("skipped_duplicates") == 3,
                  json.dumps(cj2)[:300])
    globals()["ADS_SESSION"] = sess["id"]


def step_live_noai():
    say("\n[7] US-3/US-5 — sesi live: host wajib, performa & sales tertaut toko+host")
    csv_live = (
        "Tanggal Sesi,Judul / Tema Sesi,Durasi (menit),Total Penonton,Penonton Puncak,"
        "Likes,Komentar,Jumlah Order,Revenue (Rp),Jumlah Produk Dibawakan\n"
        "2026-08-01,Live Gamis Malam,120,7.200,2.100,5.500,2.700,180,Rp 24.500.000,8\n"
        "2026-08-02,Live Khimar Pagi,90,3.100,900,1.200,640,72,Rp 9.100.000,5\n"
    )
    r = _upload("live_sessions", csv_live, filename="live.csv",
                account_id=ACC_ID, host_id=HOST_ID)
    if not check("upload sesi live (toko+host) 200", r.status_code == 200,
                 f"{r.status_code} {r.text[:400]}"):
        return
    sess = r.json()["session"]
    created["sessions"].append(sess["id"])
    check("sesi menyimpan host terpilih", sess.get("host_id") == HOST_ID, str(sess.get("host_id")))
    r = c.post(f"/marketing/data-import/sessions/{sess['id']}/commit", json={})
    if not check("commit sesi live 200", r.status_code == 200, f"{r.status_code} {r.text[:400]}"):
        return
    cj = r.json()
    check("2 sesi live masuk", cj.get("inserted") == 2, json.dumps(cj)[:300])

    r = c.get(f"/marketing/live/sessions?account_id={ACC_ID}&page_size=100")
    if r.status_code == 200:
        rows = _rows(r.json(), "sessions")
        mine = [x for x in rows if x.get("account_id") == ACC_ID]
        if len(mine) and len(mine) != len(rows):
            GAPS.append("GET /api/marketing/live/sessions mengabaikan filter "
                        "?account_id= (kerjakan di Phase 2C)")
        check("sesi live hasil impor punya account_id", len(mine) >= 2,
              f"{len(mine)} dari {len(rows)}")
        if mine:
            check("sesi live hasil impor punya host_id", mine[0].get("host_id") == HOST_ID,
                  str(mine[0].get("host_id")))
            check("engagement_rate dihitung sistem",
                  isinstance(mine[0].get("engagement_rate"), (int, float)),
                  str(mine[0].get("engagement_rate")))
    else:
        check("GET /marketing/live/sessions?account_id= jalan", False,
              f"{r.status_code} {r.text[:200]}")
    globals()["LIVE_SESSION"] = sess["id"]


def step_orders_link():
    say("\n[8] penautan master — order dengan SKU katalog")
    csv_ord = (
        "No. Pesanan,Tanggal Pesanan,SKU,Jumlah,Harga Setelah Diskon,Nama Pembeli,Status Pesanan\n"
        f"POC-{SFX}-1,2026-08-01,{SKU},2,Rp 189.000,Siti Aminah,delivered\n"
        f"POC-{SFX}-2,2026-08-02,SKU-TIDAK-ADA-{SFX},1,Rp 150.000,Budi,delivered\n"
    )
    r = _upload("orders", csv_ord, filename="order.csv", account_id=ACC_ID)
    if not check("upload order 200", r.status_code == 200, f"{r.status_code} {r.text[:400]}"):
        return
    sess = r.json()["session"]
    created["sessions"].append(sess["id"])
    r = c.post(f"/marketing/data-import/sessions/{sess['id']}/commit", json={})
    if not check("commit order 200", r.status_code == 200, f"{r.status_code} {r.text[:400]}"):
        return
    cj = r.json()
    check("2 order masuk", cj.get("inserted") == 2, json.dumps(cj)[:300])
    notes = json.dumps(cj.get("row_notes") or [], ensure_ascii=False)
    check("SKU tak dikenal diberi PERINGATAN yang jelas (bukan diam-diam)",
          "katalog" in notes.lower(), notes[:300])

    r = c.get(f"/marketing/orders?account_id={ACC_ID}&page_size=100")
    if r.status_code == 200:
        rows = _rows(r.json(), "orders")
        rows = [x for x in rows if x.get("account_id") == ACC_ID]
        check("order hasil impor terlihat saat difilter per toko", len(rows) >= 2,
              f"{len(rows)} baris ber-account_id={ACC_ID}")
        linked = [x for x in rows if x.get("catalog_item_id")]
        check("order dengan SKU katalog tertaut item katalog", len(linked) >= 1,
              json.dumps([{k: x.get(k) for k in ("order_id", "catalog_item_id")}
                          for x in rows])[:300])
    else:
        check("GET /marketing/orders?account_id= jalan", False, f"{r.status_code} {r.text[:200]}")


def step_manual_mapping():
    say("\n[9] P-7 — kolom aneh: mapping MANUAL tanpa AI membuat sesi siap commit")
    csv_weird = (
        "kolom_a,kolom_b,duit_iklan,klak\n"
        "2026-08-05,Kampanye Aneh,Rp 300.000,55\n"
    )
    r = _upload("ads", csv_weird, filename="aneh.csv", account_id=ACC_ID)
    if not check("upload berkas berheader aneh 200", r.status_code == 200,
                 f"{r.status_code} {r.text[:300]}"):
        return
    sess = r.json()["session"]
    created["sessions"].append(sess["id"])
    check("sesi berstatus 'mapping' (kolom wajib belum jelas)",
          sess.get("status") == "mapping",
          f"{sess.get('status')} report={json.dumps(sess.get('mapping_report'))}")

    r = c.post(f"/marketing/data-import/sessions/{sess['id']}/commit", json={})
    check("commit ditolak selama pemetaan belum lengkap", r.status_code == 400,
          f"{r.status_code} {r.text[:200]}")

    manual = {"mapping": [
        {"column": "kolom_a", "field": "date"},
        {"column": "kolom_b", "field": "campaign_name"},
        {"column": "duit_iklan", "field": "spend"},
        {"column": "klak", "field": "clicks"},
    ]}
    r = c.put(f"/marketing/data-import/sessions/{sess['id']}/mapping", json=manual)
    if not check("PUT mapping manual 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}"):
        return
    j = r.json()
    check("pemetaan manual membuat sesi siap", j["mapping_report"]["ready"] is True,
          json.dumps(j["mapping_report"]))
    check("pratinjau ulang 1 baris valid", (j.get("summary") or {}).get("valid") == 1,
          json.dumps(j.get("summary")))

    # dua kolom ke satu field harus ditolak (sumber angka ganda)
    bad = {"mapping": [
        {"column": "kolom_a", "field": "date"},
        {"column": "kolom_b", "field": "campaign_name"},
        {"column": "duit_iklan", "field": "spend"},
        {"column": "klak", "field": "spend"},
    ]}
    r = c.put(f"/marketing/data-import/sessions/{sess['id']}/mapping", json=bad)
    check("dua kolom → satu field ditolak", r.status_code == 400, f"{r.status_code} {r.text[:200]}")

    r = c.post(f"/marketing/data-import/sessions/{sess['id']}/commit", json={})
    check("commit setelah mapping manual 200", r.status_code == 200,
          f"{r.status_code} {r.text[:300]}")
    globals()["MANUAL_SESSION"] = sess["id"]


def step_bad_rows():
    say("\n[10] US-5 — baris salah ditandai, bisa diunduh, dan tidak ikut commit")
    csv_bad = (
        "Tanggal,Nama Kampanye,Biaya Iklan,Klik\n"
        "2026-08-06,Kampanye Baik,Rp 100.000,10\n"
        "bukan-tanggal,Kampanye Rusak,seratus ribu,abc\n"
        ",Tanpa Tanggal,Rp 50.000,5\n"
    )
    r = _upload("ads", csv_bad, filename="rusak.csv", account_id=ACC_ID)
    if not check("upload berkas bermasalah 200", r.status_code == 200,
                 f"{r.status_code} {r.text[:300]}"):
        return
    sess = r.json()["session"]
    created["sessions"].append(sess["id"])
    summ = r.json().get("summary") or {}
    check("2 baris ditandai error", summ.get("error") == 2, json.dumps(summ))

    r = c.get(f"/marketing/data-import/sessions/{sess['id']}/errors.csv")
    check("laporan masalah bisa diunduh", r.status_code == 200 and b"masalah" in r.content[:200].lower(),
          f"{r.status_code} {r.content[:120]}")

    r = c.post(f"/marketing/data-import/sessions/{sess['id']}/commit", json={})
    if check("commit hanya baris valid", r.status_code == 200, f"{r.status_code} {r.text[:300]}"):
        cj = r.json()
        check("1 masuk, 2 ditolak",
              cj.get("inserted") == 1 and cj.get("rejected") == 2, json.dumps(cj)[:250])


def step_rollback():
    say("\n[11] US-5 — rollback hanya menghapus baris sesi itu")
    sid = globals().get("LIVE_SESSION")
    if not sid:
        check("rollback (sesi live tersedia)", False, "sesi live tidak terbentuk")
        return
    before = c.get(f"/marketing/live/sessions?account_id={ACC_ID}&page_size=100")
    n_before = 0
    if before.status_code == 200:
        n_before = len([x for x in _rows(before.json(), "sessions")
                        if x.get("account_id") == ACC_ID])
    r = c.post(f"/marketing/data-import/sessions/{sid}/rollback")
    if not check("rollback 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}"):
        return
    check("2 baris dihapus", r.json().get("deleted") == 2, json.dumps(r.json()))
    after = c.get(f"/marketing/live/sessions?account_id={ACC_ID}&page_size=100")
    if after.status_code == 200:
        n_after = len([x for x in _rows(after.json(), "sessions")
                       if x.get("account_id") == ACC_ID])
        check("sesi live milik toko ini berkurang tepat 2", n_before - n_after == 2,
              f"{n_before} → {n_after}")
    r = c.post(f"/marketing/data-import/sessions/{sid}/rollback")
    check("rollback kedua ditolak (idempoten)", r.status_code == 400, str(r.status_code))
    # order dari sesi lain TIDAK boleh ikut terhapus
    r = c.get(f"/marketing/orders?account_id={ACC_ID}&page_size=100")
    if r.status_code == 200:
        rows = [x for x in _rows(r.json(), "orders") if x.get("account_id") == ACC_ID]
        check("order dari sesi LAIN tidak ikut terhapus", len(rows) >= 2, f"{len(rows)}")


def step_history():
    say("\n[12] riwayat impor bisa ditelusuri")
    r = c.get("/marketing/data-import/history")
    if check("GET /history 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}"):
        h = r.json().get("history") or []
        mine = [x for x in h if x.get("account_id") == ACC_ID]
        check("riwayat memuat sesi milik toko uji", len(mine) >= 3, f"{len(mine)}")
        if mine:
            check("riwayat menyebut siapa yang commit",
                  bool(mine[0].get("committed_by") or mine[0].get("created_by")),
                  json.dumps(mine[0])[:200])


def step_cleanup():
    say("\n[13] BERSIH-BERSIH data uji")
    # rollback semua sesi yang masih committed, lalu hapus master uji
    r = c.get("/marketing/data-import/sessions?page_size=100")
    if r.status_code == 200:
        for s in r.json().get("sessions") or []:
            if s.get("account_id") != ACC_ID:
                continue
            if s.get("status") == "committed":
                c.post(f"/marketing/data-import/sessions/{s['id']}/rollback")
    for cid in created["catalogs"]:
        c.delete(f"/marketing/catalogs/{cid}")
    for hid in created["hosts"]:
        if hid:
            c.delete(f"/marketing/livehost/{hid}")
    for crid in created["creators"]:
        if crid:
            c.delete(f"/marketing/kol/creators/{crid}")
    for aid in created["accounts"]:
        if aid:
            c.delete(f"/marketing/accounts/{aid}")
    say("  (data uji dibersihkan sejauh endpoint mengizinkan)")


def main():
    t0 = time.time()
    say("=" * 78)
    say("POC — IMPOR MARKETING TANPA AI + LINGKUP TOKO")
    say("=" * 78)
    step_login()
    if not step_master():
        say("\nMASTER GAGAL DIBUAT — POC dihentikan supaya tidak melapor lulus palsu.")
    else:
        step_source_types()
        step_template()
        step_context()
        step_scope_enforced()
        step_ads_noai()
        step_live_noai()
        step_orders_link()
        step_manual_mapping()
        step_bad_rows()
        step_rollback()
        step_history()
        step_cleanup()

    say("\n" + "=" * 78)
    if GAPS:
        say("CATATAN KESENJANGAN (ditunda, sudah masuk rencana):")
        for g in sorted(set(GAPS)):
            say(f"  • {g}")
        say("")
    say(f"HASIL: {len(OK)} LULUS · {len(FAIL)} GAGAL · {time.time()-t0:.1f}s")
    if FAIL:
        say("\nYANG GAGAL:")
        for n, d in FAIL:
            say(f"  ✗ {n}\n      {d}")
    say("=" * 78)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
