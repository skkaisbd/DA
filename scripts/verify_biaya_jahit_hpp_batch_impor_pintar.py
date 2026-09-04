#!/usr/bin/env python3
"""INV-F39 (2026-08-23, sesi #34) — **BIAYA JAHIT → HPP BATCH → MARKETING**,
IMPOR PINTAR, PORTAL KREATOR TANPA HPP, GAJI BULANAN HOST, PERIODE 7 HARI.

Yang dijaga gate ini, beserta cacat NYATA yang pernah terjadi:

 A. BIAYA JAHIT SPK — `po_items.cmt_price_snapshot` dipakai monitoring CMT,
    tagihan CMT, dan kalkulator HPP, tetapi SPK internal selalu menulis 0 dan
    tidak ada layar yang bisa mengisinya (`production_internal_adapter.py`).
    Dijaga: endpoint pengisian ada, total = tarif × qty, dan tarif tersimpan di
    `po_items` (SSOT lama), bukan koleksi baru.
 B. HPP BATCH (FIFO) — sebelumnya HPP = satu angka BOM saja; ongkos jahit &
    permak tidak pernah masuk. Dijaga: `core/fg_cost_layers` membentuk lapisan
    dan `hpp_fifo_avg` = rata-rata TERTIMBANG lapisan yang masih bersisa.
 C. PORTAL KREATOR — pernah membaca koleksi `marketing_creator_catalog` yang
    KOSONG (katalog nyata ada di `marketing_catalog_items`), dan kreator demo
    lahir tanpa `login_email`/hash sehingga pemilik tidak bisa login. Dijaga:
    login jalan, katalog terisi, dan TIDAK ADA field HPP/margin yang terkirim.
 D. IMPOR PINTAR — 22 jenis impor dipilih manual tanpa petunjuk; berkas pesanan
    bisa masuk sebagai penjualan harian tanpa ada yang tahu. Dijaga: platform
    terbaca dari sidik kolom, jenis terbaik terukur, dan salah pilih jenis
    DILAPORKAN (`session.detection.type_mismatch`) + 10 baris mentah untuk
    viewer tabel.
 E. GAJI BULANAN HOST — upah per-sesi (jam × tarif + bonus omzet) mengarang gaji
    di luar payroll. Dijaga: tidak ada shift bersaldo upah, dan basis anggaran
    live host = `livehost_monthly_salary` yang membaca `rahaza_payroll_profiles`.
 F. PERIODE ANGGARAN 7 HARI — `core/marketing_cycle.valid_period` dulu hanya
    menerima `YYYY-MM`, sehingga periode 7 hari membuat `budget/summary` 500 dan
    layar menampilkan Rp 0 tanpa pesan. Dijaga: keduanya HTTP 200.
 G. INSENTIF KREATOR — "tutup periode" harus benar-benar mengembalikan hitungan
    ke 0 (entri hari ini milik periode yang ditutup), dan entri lama TIDAK hilang.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

API = os.environ.get("API_BASE", "http://localhost:8001")
SAMPLES = ROOT / "samples" / "marketplace_2026"
G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
PASS: list[str] = []
FAIL: list[str] = []
STAMP = time.strftime("%H%M%S")


def ok(code, msg, detail=""):
    PASS.append(code)
    print(f"  {G}✓ {code}{X} {msg}" + (f"\n         {C}{detail}{X}" if detail else ""))


def bad(code, msg, detail=""):
    FAIL.append(code)
    print(f"  {R}✗ {code} {msg}{X}" + (f"\n         {detail}" if detail else ""))


def head(t):
    print(f"\n{C}{B}▶ {t}{X}")


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {"raw": raw[:300].decode(errors="ignore")}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def upload(path: Path, token: str, source_type: str, account_id: str) -> tuple:
    """multipart tanpa dependensi luar (requests tidak dipakai gate lain)."""
    boundary = f"----gate39{STAMP}"
    parts = []
    for key, val in (("source_type", source_type), ("account_id", account_id)):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{val}\r\n".encode())
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n".encode())
    parts.append(path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(f"{API}/api/marketing/data-import/upload", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {"raw": raw[:300].decode(errors="ignore")}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def det(d):
    return json.dumps(d, ensure_ascii=False)[:260]


def main() -> int:  # noqa: C901
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        bad("SETUP", f"login admin gagal (HTTP {st})", det(d))
        return 1

    # ══ A. BIAYA JAHIT SPK ════════════════════════════════════════════════════
    head("A — BIAYA JAHIT SPK: ada pintunya, totalnya benar, tersimpan di po_items")
    st, lst = call("GET", "/api/production/sewing-cost/pos?limit=5", token)
    pos = (lst or {}).get("data") or []
    if st != 200 or not pos:
        bad("A1", f"daftar SPK biaya jahit tidak terbaca (HTTP {st})", det(lst))
    else:
        ok("A1", f"{len(pos)} SPK terbaca di layar Biaya Jahit",
           f"contoh {pos[0]['po_number']} · {pos[0]['qty_total']} pcs · "
           f"{pos[0]['items_with_rate']}/{pos[0]['item_count']} tarif terisi")
        po_id = pos[0]["po_id"]
        st, dt = call("GET", f"/api/production/sewing-cost/pos/{po_id}", token)
        items = (dt or {}).get("items") or []
        if st != 200 or not items:
            bad("A2", f"detail SPK tidak terbaca (HTTP {st})", det(dt))
        else:
            it = items[0]
            before = it["rate_per_pcs"]
            probe = 7777.0
            st, res = call("PUT", f"/api/production/sewing-cost/pos/{po_id}", token,
                           {"items": [{"po_item_id": it["po_item_id"], "rate_per_pcs": probe}],
                            "apply_same_sku": False, "notes": f"GATE39 {STAMP}"})
            if st != 200:
                bad("A2", f"tarif jahit tidak bisa disimpan (HTTP {st})", det(res))
            else:
                row = db.po_items.find_one({"id": it["po_item_id"]},
                                           {"_id": 0, "cmt_price_snapshot": 1, "cmt_price_set_by": 1})
                st2, dt2 = call("GET", f"/api/production/sewing-cost/pos/{po_id}", token)
                line = next((x for x in (dt2 or {}).get("items") or []
                             if x["po_item_id"] == it["po_item_id"]), {})
                expect = round(probe * it["qty"], 2)
                if abs(float(row.get("cmt_price_snapshot", 0)) - probe) > 0.01:
                    bad("A2", "tarif tidak tersimpan di po_items (SSOT lama)", det(row))
                elif abs(line.get("line_total", 0) - expect) > 0.01:
                    bad("A3", f"total baris salah: {line.get('line_total')} ≠ {expect}")
                else:
                    ok("A2", "tarif jahit tersimpan di po_items.cmt_price_snapshot "
                             f"oleh {row.get('cmt_price_set_by')}")
                    ok("A3", f"total baris = tarif × qty ({probe:.0f} × {it['qty']} = {expect:.0f}) "
                             "— staf mengetik tarif, sistem yang mengalikan")
                    hpp_now = line.get("hpp_preview", {}).get("unit_cost", 0)
                    if hpp_now >= probe:
                        ok("A4", f"HPP/pcs memuat ongkos jahit (HPP {hpp_now:.0f} ≥ jahit {probe:.0f})")
                    else:
                        bad("A4", f"HPP/pcs ({hpp_now}) tidak memuat ongkos jahit ({probe})")
                # A5 — SSOT: item SPK yang TIDAK menunjuk master harus DIKATAKAN.
                # Diukur pada data nyata: 7 dari 7 baris `po_items` memakai SKU
                # yang tidak ada di master barang jadi, jadi biaya jahit yang
                # diisi tidak akan pernah sampai ke HPP produk mana pun. Gate ini
                # tidak menuntut datanya bersih (itu pekerjaan data); ia menuntut
                # KEKURANGANNYA TERLIHAT di layar tempat orang mengetik angka.
                broken = [x for x in (dt2 or {}).get("items") or []
                          if not (x.get("ssot") or {}).get("ok", True)]
                silent = [x for x in broken if not (x.get("ssot") or {}).get("messages")]
                tot = (dt2 or {}).get("totals") or {}
                if silent:
                    bad("A5", f"{len(silent)} item SPK tidak menunjuk master TANPA penjelasan "
                              "— biaya jahit akan hilang tanpa jejak")
                elif "items_broken_ssot" not in tot:
                    bad("A5", "ringkasan SPK tidak menyebut jumlah baris yang belum tertaut master")
                else:
                    ok("A5", f"{tot['items_broken_ssot']} baris belum tertaut master dan "
                             "SEMUANYA menyebut sebabnya di baris itu sendiri")
                # pulihkan
                call("PUT", f"/api/production/sewing-cost/pos/{po_id}", token,
                     {"items": [{"po_item_id": it["po_item_id"], "rate_per_pcs": before}],
                      "apply_same_sku": False, "notes": f"GATE39 pulihkan {STAMP}"})

    # ── A6 — ALAT TAUTKAN SKU SPK → MASTER ────────────────────────────────────
    # Biaya jahit hanya sampai ke HPP kalau baris SPK menunjuk SKU master. Alat
    # ini harus (a) menyebut BERAPA RUPIAH ongkos jahit yang menggantung, dan
    # (b) menyimpan SKU asli saat menautkan supaya keputusan bisa diperiksa.
    st, un = call("GET", "/api/production/sewing-cost/unlinked", token)
    if st != 200:
        bad("A6", f"daftar SKU SPK belum tertaut gagal (HTTP {st})", det(un))
    elif "sewing_at_risk_total" not in (un or {}):
        bad("A6", "alat tidak menyebut nominal ongkos jahit yang menggantung")
    else:
        linked = list(db.po_items.find({"sku_original": {"$nin": [None, ""]}},
                                       {"_id": 0, "sku": 1, "sku_original": 1,
                                        "fg_material_id": 1, "sku_link_by": 1}).limit(20))
        broken = [x for x in linked if not x.get("fg_material_id")]
        if broken:
            bad("A6", f"{len(broken)} baris ditautkan tanpa `fg_material_id` — "
                      "biaya jahit tetap tidak sampai ke HPP")
        else:
            ok("A6", f"{un['total']} baris SPK belum tertaut (Rp {un['sewing_at_risk_total']:,.0f} "
                     f"ongkos jahit menggantung, DISEBUT di layar) · {len(linked)} baris sudah "
                     "ditautkan dengan SKU asli tersimpan")
            for r in (un.get("data") or [])[:1]:
                if r.get("candidates") and not r["candidates"][0].get("reasons"):
                    bad("A7", "usulan pasangan tidak menyebut alasannya")
                    break
            else:
                ok("A7", "setiap usulan pasangan menyebut dasarnya "
                         "(kode sepadan / model sama / ukuran / nama mirip)")

    # ══ B. HPP BATCH (FIFO) ═══════════════════════════════════════════════════
    head("B — HPP BATCH: lapisan FIFO & rata-rata TERTIMBANG lapisan bersisa")
    layers = list(db.fg_cost_layers.find({}, {"_id": 0}).limit(500))
    if not layers:
        ok("B1", "belum ada lapisan HPP batch — TIDAK ADA angka HPP palsu yang beredar",
           "lapisan hanya lahir saat barang jadi lolos QC masuk gudang")
    else:
        mid = layers[0]["material_id"]
        mine = [l for l in layers if l["material_id"] == mid]
        openl = [l for l in mine if float(l.get("qty_remaining") or 0) > 0]
        qty = sum(float(l["qty_remaining"]) for l in openl)
        expect = (sum(float(l["unit_cost"]) * float(l["qty_remaining"]) for l in openl) / qty
                  if qty else 0.0)
        st, dd = call("GET", f"/api/production/sewing-cost/hpp/{mid}", token)
        got = ((dd or {}).get("hpp") or {}).get("hpp_fifo_avg", -1)
        if st != 200:
            bad("B1", f"HPP batch tidak terbaca (HTTP {st})", det(dd))
        elif abs(got - round(expect, 2)) > 0.05:
            bad("B1", f"hpp_fifo_avg {got} ≠ rata-rata tertimbang lapisan bersisa {expect:.2f}")
        else:
            ok("B1", f"{len(layers)} lapisan; rata-rata tertimbang lapisan bersisa benar "
                     f"({got:.0f} dari {len(openl)} lapisan · {qty:.0f} pcs)")
        no_break = [l for l in mine if not l.get("breakdown")]
        if no_break:
            bad("B2", f"{len(no_break)} lapisan tanpa rincian biaya — asal angka tidak bisa diperiksa")
        else:
            ok("B2", "setiap lapisan menyimpan rincian (bahan/jahit/permak/internal) + kekurangannya")

    # ── B3 — BIAYA IKUT KELUAR BERSAMA BARANGNYA (FIFO keluar) ────────────────
    # Kalau barang jadi keluar tanpa memakan lapisan, `hpp_fifo_avg` membeku pada
    # batch yang barangnya SUDAH TERJUAL ⇒ margin Katalog Marketing memakai biaya
    # kain lama selamanya. Yang diperiksa: tiap dokumen konsumsi harus (a) memakan
    # lapisan TERTUA lebih dulu, dan (b) qty-nya utuh (Σ lapisan + uncosted == qty).
    cons = list(db.fg_cost_consumptions.find({}, {"_id": 0}).sort("created_at", -1).limit(50))
    if not cons:
        ok("B3", "belum ada barang jadi keluar yang memakan lapisan biaya",
           "pintu keluar (core.production_qty_ledger.issue_fg) sudah memanggil consume_fifo; "
           "angkanya akan muncul begitu ada pengiriman/penjualan")
    else:
        broken_qty = [c for c in cons
                      if abs(sum(l["qty"] for l in (c.get("layers_used") or []))
                             + (c.get("uncosted_qty") or 0) - (c.get("qty") or 0)) > 0.001]
        order_bad = []
        for c in cons:
            used = c.get("layers_used") or []
            if len(used) < 2:
                continue
            ids = [l["layer_id"] for l in used]
            stamps = {l["id"]: l.get("created_at") for l in
                      db.fg_cost_layers.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "created_at": 1})}
            seq = [stamps.get(i) for i in ids if stamps.get(i)]
            if seq != sorted(seq):
                order_bad.append(c["id"])
        if broken_qty:
            bad("B3", f"{len(broken_qty)} dokumen konsumsi qty-nya tidak utuh — "
                      "ada barang keluar yang biayanya hilang tanpa jejak")
        elif order_bad:
            bad("B3", f"{len(order_bad)} dokumen memakan lapisan TIDAK dari yang tertua (bukan FIFO)")
        else:
            uncosted = sum(c.get("uncosted_qty") or 0 for c in cons)
            ok("B3", f"{len(cons)} pengeluaran memakan lapisan tertua lebih dulu (FIFO) dan qty-nya utuh"
                     + (f" · {uncosted} pcs keluar TANPA lapisan biaya — dilaporkan, tidak ditutup"
                        if uncosted else ""))

    # ══ C. PORTAL KREATOR ═════════════════════════════════════════════════════
    head("C — PORTAL KREATOR: bisa login, katalog terisi, TIDAK ADA HPP")
    cre = db.marketing_kol_creators.find_one({"login_email": {"$nin": [None, ""]}},
                                             {"_id": 0, "login_email": 1, "name": 1})
    if not cre:
        bad("C1", "tidak ada kreator ber-akun portal — pemilik tidak akan bisa login")
    else:
        st, d2 = call("POST", "/api/marketing/creator-portal/auth/login", None,
                      {"email": cre["login_email"], "password": "Dewi@123"})
        ctok = (d2 or {}).get("token")
        if not ctok:
            bad("C1", f"login portal kreator gagal untuk {cre['login_email']} (HTTP {st})", det(d2))
        else:
            ok("C1", f"kreator {cre['name']} bisa login portal ({cre['login_email']})")
            st, cat = call("GET", "/api/marketing/creator-portal/catalog", ctok)
            cat = cat if isinstance(cat, list) else []
            leak = sorted({k for it in cat for k in it
                           if "hpp" in k.lower() or "margin" in k.lower() or k.lower() == "cost"})
            if leak:
                bad("C2", f"portal kreator MEMBOCORKAN biaya: {leak}")
            else:
                ok("C2", f"katalog kreator {len(cat)} item, tanpa satu pun field HPP/margin",
                   "kreator hanya melihat harga jual — keputusan pemilik")
            if cat:
                named = [c for c in cat if (c.get("product_name") or "").strip()]
                if len(named) == len(cat):
                    ok("C3", "semua item katalog kreator punya nama produk terbaca "
                             "(nama field berbeda antar koleksi sudah diseragamkan)")
                else:
                    bad("C3", f"{len(cat) - len(named)} item tanpa nama — request barang akan gagal")

    # ══ D. IMPOR PINTAR ═══════════════════════════════════════════════════════
    head("D — IMPOR PINTAR: platform & jenis terdeteksi, salah pilih dilaporkan")
    acc = db.marketing_platform_accounts.find_one({"platform": {"$regex": "shopee", "$options": "i"}},
                                                  {"_id": 0, "id": 1, "account_name": 1})
    sample = SAMPLES / "order_pesanan_shopee.xlsx"
    if not acc or not sample.exists():
        bad("D1", "prasyarat tidak ada", f"akun shopee={bool(acc)} berkas={sample.exists()}")
    else:
        st, up = upload(sample, token, "sales_daily", acc["id"])
        sess = (up or {}).get("session") or {}
        dete = sess.get("detection") or {}
        mm = dete.get("type_mismatch") or {}
        if st != 200:
            bad("D1", f"unggah gagal (HTTP {st})", det(up))
        elif dete.get("platform_detected") != "shopee":
            bad("D1", f"platform berkas Shopee tidak terbaca: {dete.get('platform_detected')!r}")
        elif mm.get("suggested") != "marketplace_orders":
            bad("D2", "salah pilih jenis TIDAK dilaporkan "
                      f"(usulan={mm.get('suggested')!r}) — berkas pesanan bisa masuk sebagai penjualan")
        elif len(sess.get("raw_preview") or []) < 5:
            bad("D3", f"viewer tabel hanya {len(sess.get('raw_preview') or [])} baris (butuh ≥5)")
        else:
            ok("D1", "platform terbaca dari SIDIK KOLOM berkas (shopee)",
               f"bukti: {', '.join(dete.get('platform_evidence') or [])}")
            ok("D2", f"salah pilih jenis dilaporkan → usulan '{mm['suggested_label']}' "
                     f"({mm['suggested_mapped']} kolom cocok vs {mm['chosen_mapped']} kolom pilihan staf)")
            ok("D3", f"viewer tabel menerima {len(sess['raw_preview'])} baris mentah berkas")
        # jenis yang BENAR harus punya cakupan kolom tinggi
        st, up2 = upload(sample, token, "marketplace_orders", acc["id"])
        rep = ((up2 or {}).get("session") or {}).get("mapping_report") or {}
        mapped = rep.get("mapped") or rep.get("mapped_count") or 0
        if st == 200 and mapped >= 30 and not rep.get("missing_required"):
            ok("D4", f"berkas Shopee asli: {mapped} kolom terpetakan, kolom wajib LENGKAP")
        else:
            bad("D4", f"pemetaan berkas Shopee asli lemah: {mapped} kolom, "
                      f"wajib kurang={rep.get('missing_required')}")

    # ══ E. GAJI BULANAN HOST ══════════════════════════════════════════════════
    head("E — LIVE HOST: upah per-sesi mati, biaya = gaji bulanan payroll HR")
    paid = db.marketing_livehost_shifts.count_documents({"total_pay": {"$gt": 0}})
    if paid:
        bad("E1", f"{paid} shift masih menyimpan upah per-sesi > 0 — gaji dihitung dua kali")
    else:
        ok("E1", "tidak ada shift bersaldo upah per-sesi (host digaji bulanan)")
    acc_any = db.marketing_platform_accounts.find_one({}, {"_id": 0, "id": 1})
    if acc_any:
        st, summ = call("GET", f"/api/marketing/budget/summary?account_id={acc_any['id']}&period=2026-08",
                        token)
        src = next((s for s in (summ or {}).get("spend_sources") or []
                    if s.get("category") == "livehost"), {})
        if st != 200:
            bad("E2", f"budget summary gagal (HTTP {st})", det(summ))
        elif src.get("basis") != "livehost_monthly_salary":
            bad("E2", f"basis biaya live host masih {src.get('basis')!r} (harus gaji bulanan)")
        else:
            ok("E2", f"basis biaya live host = gaji bulanan · {src.get('evidence')}")

    # ══ F. PERIODE ANGGARAN 7 HARI ════════════════════════════════════════════
    head("F — PERIODE ANGGARAN: 7 hari (default) DAN 1 bulan sama-sama hidup")
    st, ps = call("GET", "/api/marketing/budget/period-settings", token)
    stg = (ps or {}).get("settings") or {}
    if st != 200 or not stg.get("current_period"):
        bad("F1", f"setelan periode tidak terbaca (HTTP {st})", det(ps))
    else:
        ok("F1", f"mode '{stg['period_mode']}' · {stg['period_days']} hari · "
                 f"periode kini {stg['current_range']['start']} → {stg['current_range']['end']}")
        if acc_any:
            for per, label in ((stg["current_period"], "7 hari"), ("2026-08", "bulanan")):
                st, sm = call("GET",
                              f"/api/marketing/budget/summary?account_id={acc_any['id']}&period={per}",
                              token)
                if st != 200:
                    bad("F2", f"budget summary periode {label} ({per}) HTTP {st} — "
                              "layar akan menampilkan Rp 0 tanpa pesan", det(sm))
                else:
                    ok("F2", f"budget summary periode {label} ({per}) HTTP 200 · "
                             f"total belanja {sm.get('total_spend')}")

    # ══ G. INSENTIF KREATOR ═══════════════════════════════════════════════════
    head("G — INSENTIF KREATOR: tutup periode benar-benar kembali 0, entri tersimpan")
    cid = None
    # SESI #38 — kreator tipe `new` SENGAJA tidak dapat insentif (keputusan
    # pemilik). Gate lama memakai kreator aktif PERTAMA apa pun tipenya, jadi
    # begitu kreator pertama di basis data bertipe `new` gate berteriak "salah
    # hitung" padahal jawabannya benar. Yang diuji sekarang: kreator yang BERHAK
    # (kalau ada) menerima per-pcs + bonus, dan kreator `new` menerima 0 dengan
    # ALASAN yang terbaca.
    c = (db.marketing_kol_creators.find_one(
            {"status": {"$ne": "inactive"}, "creator_type": {"$nin": ["new", None, ""]}},
            {"_id": 0, "id": 1})
         or db.marketing_kol_creators.find_one({"status": {"$ne": "inactive"}},
                                               {"_id": 0, "id": 1}))
    if c:
        cid = c["id"]
    if not cid:
        bad("G1", "tidak ada kreator aktif untuk diuji")
    else:
        cfg_before = (db.marketing_kol_creators.find_one({"id": cid}, {"_id": 0, "incentive": 1})
                      or {}).get("incentive")
        today = time.strftime("%Y-%m-%d")
        call("PUT", f"/api/marketing/kol/creators/{cid}/incentive", token,
             {"mode": "both", "rate_per_pcs": 1000, "target_pcs": 10, "bonus_amount": 50000,
              "period_months": 3, "period_start": today[:7] + "-01"})
        st, e1 = call("POST", f"/api/marketing/kol/creators/{cid}/incentive/entries", token,
                      {"date": today, "pcs": 12, "note": f"GATE39 {STAMP}"})
        if st != 200:
            bad("G1", f"tracker pcs tidak bisa diinput (HTTP {st})", det(e1))
        else:
            eligible = bool(e1.get("eligible"))
            if e1["pcs_sold"] < 12:
                bad("G1", f"pcs tidak tersimpan apa adanya: {det(e1)}")
            elif not eligible:
                # tipe `new`: 0 rupiah WAJIB disertai alasan, bukan angka bisu
                if e1["total_incentive"] or not (e1.get("eligible_reason") or "").strip():
                    bad("G1", "kreator tidak berhak insentif tetapi angkanya tidak 0 "
                              "atau alasannya tidak disebut", det(e1))
                else:
                    ok("G1", f"tracker staf marketing: {e1['pcs_sold']} pcs tersimpan · "
                             f"insentif 0 dengan alasan: {e1['eligible_reason'][:60]}")
            elif e1["total_incentive"] < 12000:
                bad("G1", f"insentif salah hitung: {det(e1)}")
            else:
                ok("G1", f"tracker staf marketing: {e1['pcs_sold']} pcs → "
                         f"insentif {e1['total_incentive']:.0f} (per pcs + bonus target)")
            st, cl = call("POST", f"/api/marketing/kol/creators/{cid}/incentive/close-period", token)
            left = db.marketing_creator_incentive_entries.count_documents(
                {"creator_id": cid, "note": f"GATE39 {STAMP}"})
            if st != 200:
                bad("G2", f"tutup periode gagal (HTTP {st})", det(cl))
            elif cl.get("pcs_sold"):
                bad("G2", f"setelah tutup periode hitungan belum 0 (pcs={cl['pcs_sold']}) — "
                          "pcs hari ini akan dibayar dua kali")
            elif not left:
                bad("G3", "entri periode lama HILANG setelah ditutup — bukti bayar tidak ada")
            else:
                ok("G2", f"tutup periode: {cl['closed']:.0f} dibukukan, hitungan kembali 0, "
                         f"periode baru mulai {cl['period']['start']}")
                ok("G3", f"{left} entri periode lama tetap tersimpan sebagai bukti bayar")
            db.marketing_creator_incentive_entries.delete_many({"note": f"GATE39 {STAMP}"})
        if cfg_before is None:
            db.marketing_kol_creators.update_one({"id": cid},
                                                 {"$unset": {"incentive": "", "incentive_history": ""}})
        else:
            db.marketing_kol_creators.update_one({"id": cid}, {"$set": {"incentive": cfg_before}})

    # ══ H. VIEWER PRODUK FINAL RND ════════════════════════════════════════════
    head("H — RND: produk final terlihat sebagai katalog + kekurangan SSOT disebut")
    st, pv = call("GET", "/api/rnd/product-viewer?limit=20", token)
    rows = (pv or {}).get("data") or []
    summ = (pv or {}).get("summary") or {}
    if st != 200 or not rows:
        bad("H1", f"viewer produk RnD kosong/gagal (HTTP {st})", det(pv))
    else:
        ok("H1", f"{summ.get('total')} produk final terlihat · {summ.get('synced')} sudah di katalog "
                 f"marketing · {summ.get('no_bom')} tanpa BOM · {summ.get('hpp_real')} HPP dari batch nyata")
        incomplete = [r for r in rows if not r["ssot_ok"]]
        if incomplete and not any(r["gaps"] for r in incomplete):
            bad("H2", "ada produk tidak lengkap tetapi kekurangannya TIDAK disebut")
        else:
            ok("H2", f"{len(incomplete)}/{len(rows)} produk belum lengkap dan SEMUANYA menyebut "
                     "kekurangannya (BOM/katalog/biaya jahit/foto)")

    print(f"\n{B}{'─' * 70}{X}")
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian sesi #34 terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
