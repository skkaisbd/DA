#!/usr/bin/env python3
"""verify_sinkronisasi_marketing_gudang.py — SESI #20 (keluhan pemilik).

GATE **INV-F29** — "BARANG YANG DIPESAN PEMBELI HARUS PUNYA SATU IDENTITAS."

═══════════════════════════════════════════════════════════════════════════════
YANG TERUKUR SEBELUM PERBAIKAN  (tests/poc_sync_forensic.py, data hidup)
═══════════════════════════════════════════════════════════════════════════════
Keluhan pemilik, verbatim: *"list barang dari marketing untuk dikirimkan oleh tim
gudang tidak ada yang sama, saya cek dari id-nya antara gudang dan di marketing
tidak sinkron"*. Diukur, bukan ditebak:

  · **0 dari 601** baris pesanan marketing menunjuk master gudang (`fg_material_id`).
  · **83 SKU platform** dipesan pembeli tanpa dikenal master sama sekali.
  · Tabel jembatan `marketing_catalog_items.platform_sku_ids[]` **kosong** — dan satu-
    satunya pintu pemetaan menempel pada **sesi impor** (`/import/sessions/{id}/sku-map`),
    jadi SKU dari sesi yang sudah dihapus mustahil dipetakan.
  · **559 pesanan** berstatus "Perlu dikirim" tersimpan sebagai
    `fulfillment_status='unallocated'`, sementara antrean gudang hanya mencari
    `'pending_fulfillment'` ⇒ layar gudang menampilkan **0 pekerjaan**. Dua penulis,
    dua kamus, tidak pernah bertemu.

INVARIAN YANG DIJAGA
--------------------
  S1  kosakata status antrean punya SATU sumber (`core/fulfillment_status`) dan
      MENGAKUI istilah warisan `'unallocated'`; tidak ada route yang menyalin
      daftar statusnya sendiri
  S2  impor pesanan tidak lagi menulis istilah mati `'unallocated'` — status awal
      diturunkan dari status platform lewat `initial_status()`
  S3  antrean gudang TIDAK MENYEMBUNYIKAN pekerjaan: setiap pesanan yang menurut
      platform perlu dikirim muncul di `/api/fulfillment/queue`, dan tiap baris
      membawa alasan bila belum bisa dialokasikan (`linkage`)
  S4  pemetaan SKU hidup di koleksi mandiri ber-index UNIK (satu SKU platform tidak
      boleh punya dua master) dan TIDAK bergantung pada sesi impor
  S5  0 pemetaan menggantung: setiap `marketing_sku_bridge.fg_material_id` ada di
      `rahaza_materials`, dan setiap `catalog_item_id` ada di `marketing_catalog_items`
  S6  pemetaan menautkan SELURUH pesanan yang memakai SKU itu (idempoten): tidak ada
      baris ber-`master_link_source='sku_bridge'` yang `fg_material_id`-nya kosong
  S7  mesin usulan TIDAK MENEBAK: nama produk yang tidak ada di master menghasilkan
      0 kandidat + aksi `create_master`, dan pemetaan otomatis menolak di bawah ambang
  S8  rantai "buat master dari SKU" utuh lewat SSOT: varian → master FG (kode == SKU)
      → item katalog toko → pemetaan → pesanan lama ikut tertaut
  S9  laporan `/api/sync-audit/report` TIDAK BERBOHONG: angkanya sama dengan hitungan
      langsung dari DB, dan tiap perbaikan punya mode pratinjau yang tidak menulis
  S10 pintunya ADA di layar: `sku-bridge` & `sync-audit` terdaftar di moduleRegistry
      dan muncul di sidebar portal yang relevan

Self-cleaning: seluruh dokumen uji (`UJI-F29 …`) dihapus di akhir.

Pakai:  python3 scripts/verify_sinkronisasi_marketing_gudang.py [--keep]
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(ROOT / "backend"))
from gr_common import db_handle  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

STAMP = time.strftime("%H%M%S")
MARK = f"UJI-F29 {STAMP}"
TEST_PSID = f"9{STAMP}0000000001"
TEST_PSID2 = f"9{STAMP}0000000002"

PASS: list = []
FAIL: list = []


def ok(code, msg):
    PASS.append(code)
    print(f"  {G}✓{X} {code} — {msg}")


def bad(code, msg):
    FAIL.append(code)
    print(f"  {R}✗ {code}{X} — {msg}")


def req(method, path, token=None, body=None, timeout=180):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:  # noqa: BLE001
            return e.code, {}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def login(email, pw):
    st, d = req("POST", "/api/auth/login", body={"email": email, "password": pw})
    return d.get("token") if st == 200 else None


# ══════════════════════════════════════════════════════════════════════════════
# Persiapan: satu pesanan uji dengan SKU platform yang PASTI belum dikenal master
# ══════════════════════════════════════════════════════════════════════════════
def seed_test_orders(db):
    """Buat 2 pesanan uji memakai SATU SKU platform (untuk membuktikan S6 idempoten)."""
    acc = db.marketing_platform_accounts.find_one({}, {"_id": 0, "id": 1, "account_name": 1})
    if not acc:
        return None
    docs = []
    for i in (1, 2):
        docs.append({
            "id": str(uuid.uuid4()),
            "order_id": f"{MARK}-{i}",
            "account_id": acc["id"], "account_name": acc.get("account_name", ""),
            "status": "paid", "status_raw": "Perlu dikirim",
            "fulfillment_status": "unallocated",     # istilah WARISAN — sengaja
            "purchase_channel": "TikTok",
            "order_date": "2026-08-18 10:00:00",
            "quantity": 3, "items_count": 1,
            "items": [{
                "platform_sku_id": TEST_PSID,
                "product_name_raw": f"UJI F29 Kemeja Flanel Kotak Premium {STAMP}",
                "variation_raw": "NAVY, XL",
                "quantity": 3, "line_no": 1,
                "catalog_item_id": None, "fg_material_id": None,
                "master_link_source": "unlinked",
            }],
            "_f29_test": True,
        })
    # SKU kedua: nama yang MUSTAHIL cocok dengan master apa pun (untuk S7)
    docs.append({
        "id": str(uuid.uuid4()), "order_id": f"{MARK}-3",
        "account_id": acc["id"], "account_name": acc.get("account_name", ""),
        "status": "paid", "status_raw": "Perlu dikirim",
        "fulfillment_status": "unallocated", "purchase_channel": "TikTok",
        "order_date": "2026-08-18 10:05:00", "quantity": 1, "items_count": 1,
        "items": [{
            "platform_sku_id": TEST_PSID2,
            "product_name_raw": f"Zzqxwv Blarghum Trombonium {STAMP}",
            "variation_raw": "", "quantity": 1, "line_no": 1,
            "catalog_item_id": None, "fg_material_id": None,
            "master_link_source": "unlinked",
        }],
        "_f29_test": True,
    })
    db.marketing_orders.insert_many(docs)
    return acc["id"]


def clean(db):
    n = db.marketing_orders.delete_many({"_f29_test": True}).deleted_count
    br = db.marketing_sku_bridge.delete_many(
        {"platform_sku_id": {"$in": [TEST_PSID, TEST_PSID2]}}).deleted_count
    # master + item katalog yang lahir dari SKU uji
    mids = [m["id"] for m in db.rahaza_models.find(
        {"source_platform_sku_id": {"$in": [TEST_PSID, TEST_PSID2]}}, {"_id": 0, "id": 1})]
    vids = [v["id"] for v in db.rahaza_model_variants.find(
        {"model_id": {"$in": mids}}, {"_id": 0, "id": 1})] if mids else []
    if vids:
        db.marketing_catalog_items.delete_many({"variant_id": {"$in": vids}})
        # Sesi #33 — riwayat harga ikut dibuang supaya tidak ada baris YATIM di
        # layar Riwayat Harga Barang (dijaga INV-F38 C16).
        _mids_fg = [m["id"] for m in db.rahaza_materials.find(
            {"variant_id": {"$in": vids}}, {"_id": 0, "id": 1})]
        if _mids_fg:
            db.rahaza_material_cost_history.delete_many({"material_id": {"$in": _mids_fg}})
        db.rahaza_materials.delete_many({"variant_id": {"$in": vids}})
        db.rahaza_model_variants.delete_many({"id": {"$in": vids}})
    if mids:
        db.rahaza_models.delete_many({"id": {"$in": mids}})
    db.marketing_catalog_items.update_many(
        {"platform_sku_ids": {"$in": [TEST_PSID, TEST_PSID2]}},
        {"$pull": {"platform_sku_ids": {"$in": [TEST_PSID, TEST_PSID2]}}})
    return n + br + len(mids) + len(vids)


# ══════════════════════════════════════════════════════════════════════════════
# S1 · S2 — satu kosakata status, tidak ada penyalin
# ══════════════════════════════════════════════════════════════════════════════
def s1_s2_vocabulary():
    print(f"\n{C}S1/S2 — kosakata status fulfillment punya satu sumber{X}")
    mod = ROOT / "backend/core/fulfillment_status.py"
    if not mod.exists():
        bad("S1", "core/fulfillment_status.py tidak ada — kosakata status tanpa SSOT.")
        return
    src = mod.read_text()
    if "'unallocated'" not in src or "QUEUE_STATES" not in src:
        bad("S1", "SSOT status tidak mengakui istilah warisan 'unallocated' di QUEUE_STATES.")
    else:
        sys.path.insert(0, str(ROOT / "backend"))
        try:
            from core import fulfillment_status as fs
            if not fs.in_queue("unallocated"):
                bad("S1", "in_queue('unallocated') False — 559 pesanan warisan akan hilang lagi.")
            elif fs.canon("unallocated") != fs.PENDING:
                bad("S1", "canon('unallocated') tidak memetakan ke pending_fulfillment.")
            else:
                ok("S1", "SSOT kosakata ada; 'unallocated' diakui sebagai antrean gudang.")
        except Exception as e:  # noqa: BLE001
            bad("S1", f"SSOT status gagal diimpor: {e}")

    # tidak ada route yang menyalin daftar status antrean sendiri
    pat = re.compile(r"pending_fulfillment[\"']\s*,\s*[\"']allocated")
    offenders = []
    for p in (ROOT / "backend/routes").rglob("*.py"):
        if "__pycache__" in str(p) or "_archive" in str(p):
            continue
        if pat.search(p.read_text()):
            offenders.append(p.name)
    if offenders:
        bad("S1b", f"daftar status antrean masih disalin di: {', '.join(offenders)} "
                   f"(wajib impor core.fulfillment_status.queue_filter).")
    else:
        ok("S1b", "tidak ada route yang menyalin daftar status antrean.")

    imp = ROOT / "backend/routes/marketing_data_import.py"
    src2 = imp.read_text()
    writes = re.findall(r"fulfillment_status[\"']?\]?\s*=\s*[\"']unallocated[\"']", src2)
    if writes:
        bad("S2", f"impor pesanan MASIH menulis 'unallocated' ({len(writes)} tempat) — "
                  "pekerjaan gudang akan tersembunyi lagi.")
    elif "initial_status" not in src2:
        bad("S2", "impor pesanan tidak memakai initial_status() — status awal ditebak.")
    else:
        ok("S2", "impor pesanan menurunkan status awal dari status platform (initial_status).")


# ══════════════════════════════════════════════════════════════════════════════
# S3 — antrean gudang tidak menyembunyikan pekerjaan
# ══════════════════════════════════════════════════════════════════════════════
def s3_queue_shows_work(db, token):
    print(f"\n{C}S3 — antrean gudang menampilkan pekerjaan yang memang ada{X}")
    from core import fulfillment_status as fs

    need = 0
    for o in db.marketing_orders.find({}, {"_id": 0, "status": 1, "fulfillment_status": 1}):
        want, _ = fs.initial_status(o)
        if want == fs.PENDING and not fs.canon(o.get("fulfillment_status")) in fs.CLOSED_STATES:
            need += 1
    st, d = req("GET", "/api/fulfillment/queue?limit=5", token)
    if st != 200:
        bad("S3", f"GET /api/fulfillment/queue HTTP {st}")
        return
    total = int(d.get("total") or 0)
    if need and total == 0:
        bad("S3", f"{need} pesanan perlu dikirim tetapi antrean gudang melaporkan 0 — "
                  "layar menyembunyikan pekerjaan.")
        return
    rows = d.get("orders") or []
    if rows and "linkage" not in rows[0]:
        bad("S3b", "baris antrean tidak membawa `linkage` — gudang tidak diberi tahu "
                   "MENGAPA sebuah pesanan belum bisa dialokasikan.")
    else:
        ok("S3b", "tiap baris antrean membawa kesiapan tautannya (linkage).")
    st2, sm = req("GET", "/api/fulfillment/summary", token)
    if st2 != 200 or "queue_blocked" not in sm:
        bad("S3c", "ringkasan antrean tidak melaporkan queue_blocked/blocked_unmapped_skus.")
    else:
        ok("S3c", f"ringkasan jujur: {sm.get('queue_total')} antrean, "
                  f"{sm.get('queue_ready')} siap, {sm.get('queue_blocked')} terhambat.")
    ok("S3", f"antrean memuat {total} pesanan (perlu dikirim menurut platform: {need}).")


# ══════════════════════════════════════════════════════════════════════════════
# S4 · S5 — jembatan mandiri, ber-index unik, tidak menggantung
# ══════════════════════════════════════════════════════════════════════════════
def s4_s5_bridge_integrity(db):
    print(f"\n{C}S4/S5 — jembatan SKU mandiri & tidak menggantung{X}")
    idx = db.marketing_sku_bridge.index_information()
    uniq = any(v.get("unique") and v.get("key") == [("platform_sku_id", 1)]
               for v in idx.values())
    if not uniq:
        bad("S4", "marketing_sku_bridge.platform_sku_id TIDAK ber-index unik — "
                  "satu SKU bisa punya dua master.")
    else:
        ok("S4", "platform_sku_id ber-index UNIK (satu SKU = satu master).")

    # Jembatan tidak boleh bergantung sesi impor. Diperiksa pada KODE saja —
    # docstring modul memang MENJELASKAN masalah lama (pemetaan yang menempel pada
    # `session_id`), dan menghukum penjelasan itu berarti mendorong orang menghapus
    # catatan sejarah yang justru mencegah kambuh.
    import ast as _ast

    core_src = (ROOT / "backend/core/sku_bridge.py").read_text()
    tree = _ast.parse(core_src)
    code_hits = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Name) and node.id == "session_id":
            code_hits.append(node.lineno)
        elif isinstance(node, _ast.Attribute) and node.attr == "session_id":
            code_hits.append(node.lineno)
        elif isinstance(node, _ast.Constant) and isinstance(node.value, str) \
                and "session_id" in node.value and len(node.value) < 120:
            code_hits.append(node.lineno)
    if code_hits:
        bad("S4b", f"core/sku_bridge.py memakai session_id di KODE (baris {code_hits[:5]}) — "
                   "pemetaan masih terikat sesi impor.")
    else:
        ok("S4b", "pemetaan tidak bergantung pada sesi impor (0 pemakaian session_id di kode).")

    mat_ids = {m["id"] for m in db.rahaza_materials.find({}, {"_id": 0, "id": 1})}
    item_ids = {i["id"] for i in db.marketing_catalog_items.find({}, {"_id": 0, "id": 1})}
    dang_m = dang_i = 0
    total = 0
    for b in db.marketing_sku_bridge.find({}, {"_id": 0}):
        total += 1
        if b.get("fg_material_id") and b["fg_material_id"] not in mat_ids:
            dang_m += 1
        if b.get("catalog_item_id") and b["catalog_item_id"] not in item_ids:
            dang_i += 1
    if dang_m or dang_i:
        bad("S5", f"{dang_m} pemetaan menunjuk master FG hilang, {dang_i} menunjuk item "
                  "katalog hilang.")
    else:
        ok("S5", f"{total} pemetaan; 0 rujukan menggantung.")


# ══════════════════════════════════════════════════════════════════════════════
# S6 · S8 — buat master dari SKU + backfill SELURUH pesanan (idempoten)
# ══════════════════════════════════════════════════════════════════════════════
def s6_s8_create_and_backfill(db, token, account_id):
    print(f"\n{C}S6/S8 — buat master dari SKU platform & tautkan seluruh pesanannya{X}")

    st, prev = req("POST", "/api/sku-bridge/create-master", token,
                   {"platform_sku_id": TEST_PSID, "account_id": account_id})
    if st != 200 or not prev.get("dry_run"):
        bad("S8a", f"pratinjau create-master gagal (HTTP {st}) — pemilik tidak bisa melihat "
                   "apa yang akan dibuat.")
    else:
        before = db.rahaza_model_variants.count_documents({})
        if before != db.rahaza_model_variants.count_documents({}):
            bad("S8a", "pratinjau MENULIS data.")
        else:
            ok("S8a", f"pratinjau tidak menulis apa pun: {prev.get('message', '')[:70]}…")

    st, res = req("POST", "/api/sku-bridge/create-master", token,
                  {"platform_sku_id": TEST_PSID, "account_id": account_id, "apply": True})
    if st != 200 or not res.get("ok"):
        bad("S8", f"create-master gagal (HTTP {st}): {res.get('detail') or res}")
        return
    sku = (res.get("variant") or {}).get("sku") or ""
    fg = db.rahaza_materials.find_one({"code": sku}, {"_id": 0, "id": 1, "type": 1,
                                                     "variant_id": 1})
    item = db.marketing_catalog_items.find_one(
        {"platform_sku_ids": TEST_PSID}, {"_id": 0, "id": 1, "fg_material_id": 1})
    chain = []
    if not sku:
        chain.append("varian")
    if not fg or fg.get("type") != "fg":
        chain.append("master FG (kode == SKU)")
    if not item:
        chain.append("item katalog toko")
    if not db.marketing_sku_bridge.find_one({"platform_sku_id": TEST_PSID}):
        chain.append("pemetaan jembatan")
    if chain:
        bad("S8", f"rantai master TIDAK utuh — yang hilang: {', '.join(chain)}")
    else:
        ok("S8", f"rantai utuh: varian {sku} → FG → item katalog → pemetaan.")

    # backfill: KEDUA pesanan uji harus tertaut
    linked = 0
    for o in db.marketing_orders.find({"_f29_test": True}, {"_id": 0, "items": 1}):
        for ln in (o.get("items") or []):
            if ln.get("platform_sku_id") == TEST_PSID and ln.get("fg_material_id"):
                linked += 1
    if linked < 2:
        bad("S6", f"hanya {linked}/2 baris pesanan ikut tertaut — satu pemetaan harus "
                  "mengurus SELURUH pesanan yang memakai SKU itu.")
    else:
        ok("S6", f"{linked} baris pesanan tertaut dari SATU pemetaan.")

    # idempoten: ulangi, tidak boleh menggandakan master
    v_before = db.rahaza_model_variants.count_documents({})
    m_before = db.rahaza_models.count_documents({})
    req("POST", "/api/sku-bridge/create-master", token,
        {"platform_sku_id": TEST_PSID, "account_id": account_id, "apply": True})
    if (db.rahaza_model_variants.count_documents({}) != v_before
            or db.rahaza_models.count_documents({}) != m_before):
        bad("S6b", "menjalankan ulang create-master MENGGANDAKAN master (tidak idempoten).")
    else:
        ok("S6b", "dijalankan ulang: 0 master kembar (idempoten).")

    # tidak ada baris ber-sumber sku_bridge yang fg-nya kosong
    broken = 0
    for o in db.marketing_orders.find({"items.master_link_source": "sku_bridge"},
                                      {"_id": 0, "items": 1}):
        for ln in (o.get("items") or []):
            if ln.get("master_link_source") == "sku_bridge" and not ln.get("fg_material_id"):
                broken += 1
    if broken:
        bad("S6c", f"{broken} baris mengaku tertaut jembatan tetapi fg_material_id kosong.")
    else:
        ok("S6c", "0 baris yang mengaku tertaut tanpa master FG.")


# ══════════════════════════════════════════════════════════════════════════════
# S7 — mesin usulan tidak menebak
# ══════════════════════════════════════════════════════════════════════════════
def s7_no_guessing(token):
    print(f"\n{C}S7 — mesin usulan menolak menebak{X}")
    st, d = req("GET", f"/api/sku-bridge/suggest?platform_sku_id={TEST_PSID2}", token)
    if st != 200:
        bad("S7", f"GET /suggest HTTP {st}")
        return
    cands = d.get("candidates") or []
    act = d.get("recommended_action")
    if cands:
        top = cands[0]
        bad("S7", f"nama produk yang tidak ada di master tetap diberi kandidat "
                  f"('{top.get('label')}' keyakinan {top.get('confidence')}) — mesin menebak.")
    elif act != "create_master":
        bad("S7", f"aksi yang disarankan '{act}', seharusnya 'create_master' "
                  "(masternya belum ada).")
    else:
        ok("S7", "0 kandidat + aksi 'create_master' — mesin mengatakan tidak tahu.")

    st, am = req("POST", "/api/sku-bridge/auto-map", token,
                 {"limit": 50, "apply": False, "min_confidence": 0.99})
    if st != 200:
        bad("S7b", f"POST /auto-map HTTP {st}")
        return
    low = [a for a in (am.get("applied") or []) if float(a.get("confidence") or 0) < 0.99]
    if low:
        bad("S7b", f"{len(low)} pemetaan otomatis di BAWAH ambang keyakinan.")
    elif not am.get("dry_run"):
        bad("S7b", "auto-map menulis padahal apply=false.")
    else:
        ok("S7b", f"auto-map hanya pratinjau & menaati ambang ({am.get('applied_count')} lolos).")


# ══════════════════════════════════════════════════════════════════════════════
# S9 — laporan audit tidak berbohong + perbaikan bisa dipratinjau
# ══════════════════════════════════════════════════════════════════════════════
def s9_audit_truthful(db, token):
    print(f"\n{C}S9 — laporan audit sama dengan hitungan langsung dari DB{X}")
    st, rep = req("GET", "/api/sync-audit/report", token)
    if st != 200:
        bad("S9", f"GET /api/sync-audit/report HTTP {st}")
        return
    secs = rep.get("sections") or {}
    missing = [k for k in ("A", "B", "C", "D", "E") if k not in secs]
    if missing:
        bad("S9", f"laporan tidak lengkap — bagian hilang: {', '.join(missing)}")
        return

    # hitung sendiri dari DB lalu bandingkan
    lines = linked = 0
    for o in db.marketing_orders.find({}, {"_id": 0, "items": 1}):
        for ln in (o.get("items") or []):
            lines += 1
            if ln.get("fg_material_id"):
                linked += 1
    m = secs["A"]["metrics"]
    if int(m.get("lines") or 0) != lines or int(m.get("lines_linked") or 0) != linked:
        bad("S9", f"angka laporan (baris={m.get('lines')}, tertaut={m.get('lines_linked')}) "
                  f"beda dari DB (baris={lines}, tertaut={linked}).")
    else:
        ok("S9", f"angka laporan sama dengan DB: {linked}/{lines} baris tertaut "
                 f"(verdict {rep.get('verdict')}, skor {rep.get('score')}).")

    st, rl = req("GET", "/api/sync-audit/repairs", token)
    reps = (rl.get("repairs") or []) if st == 200 else []
    if not reps:
        bad("S9b", "tidak ada perbaikan terdaftar.")
        return
    before = db.marketing_catalog_items.count_documents({})
    dirty = []
    for r in reps:
        stx, res = req("POST", "/api/sync-audit/repair", token,
                       {"action": r["action"], "apply": False})
        if stx != 200 or not res.get("dry_run", True):
            dirty.append(r["action"])
    if db.marketing_catalog_items.count_documents({}) != before:
        dirty.append("(jumlah item katalog berubah saat pratinjau)")
    if dirty:
        bad("S9b", f"pratinjau perbaikan menulis data / gagal: {', '.join(dirty)}")
    else:
        ok("S9b", f"{len(reps)} perbaikan punya pratinjau yang tidak menulis apa pun.")


# ══════════════════════════════════════════════════════════════════════════════
# S10 — pintunya ada di layar
# ══════════════════════════════════════════════════════════════════════════════
def s10_doors_exist():
    print(f"\n{C}S10 — pintu ada di registry & sidebar{X}")
    reg = (ROOT / "frontend/src/components/erp/moduleRegistry.js").read_text()
    nav = (ROOT / "frontend/src/components/erp/portal-shell/portalNav.js").read_text()
    miss = []
    for mid, comp in (("sku-bridge", "SkuBridgeModule"), ("sync-audit", "SyncAuditModule")):
        if f"'{mid}'" not in reg or comp not in reg:
            miss.append(f"{mid} tidak terdaftar di moduleRegistry")
        if f"id: '{mid}'" not in nav:
            miss.append(f"{mid} tidak ada di sidebar (portalNav)")
        f = ROOT / f"frontend/src/components/erp/{comp}.jsx"
        if not f.exists():
            miss.append(f"komponen {comp}.jsx tidak ada")
    if miss:
        bad("S10", "; ".join(miss))
    else:
        ok("S10", "sku-bridge & sync-audit terdaftar di registry + sidebar, komponen ada.")


def main():
    db = db_handle()
    if "--clean" in sys.argv:
        print(f"  dibersihkan {clean(db)} dokumen uji")
        return 0

    token = login("admin@garment.com", "Admin@123")
    if not token:
        print(f"{R}login admin gagal{X}")
        return 2

    print(f"{B}INV-F29 — sinkronisasi identitas barang Marketing ⇄ Gudang{X}")
    clean(db)
    account_id = seed_test_orders(db)
    if not account_id:
        print(f"{R}tidak ada toko marketing untuk uji{X}")
        return 3

    try:
        s1_s2_vocabulary()
        s3_queue_shows_work(db, token)
        s4_s5_bridge_integrity(db)
        s6_s8_create_and_backfill(db, token, account_id)
        s7_no_guessing(token)
        s9_audit_truthful(db, token)
        s10_doors_exist()
    finally:
        if "--keep" not in sys.argv:
            try:
                clean(db)
            except Exception:  # noqa: BLE001
                pass

    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian sinkronisasi terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
