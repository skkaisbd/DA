#!/usr/bin/env python3
"""
INV-MKTSCOPE — gate lingkup toko & mesin impor marketing.

APA YANG DIJAGA (dan kenapa layak jadi gate)
--------------------------------------------
Satu pertanyaan yang dipakai repo ini untuk memutuskan sebuah pemeriksaan layak
jadi gate: *"kalau pemeriksaan ini hilang, apakah UANG / DATA / ALUR PRODUK bisa
rusak tanpa ada yang tahu?"* Untuk marketing jawabannya ya, dan sudah terbukti:

* **MKS-1..15 (DATA + UANG).** Dokumen marketing tanpa `account_id` tidak akan
  pernah muncul di layar yang difilter per toko, dan tidak akan pernah ikut
  dijumlahkan di laporan per akun. Audit 2026-08-11 mengukur 60/60 order,
  25/25 iklan, 18/18 sesi live, 35/35 sample tanpa lingkup toko. Kerusakannya
  **tidak melahirkan error** — hanya angka yang lebih kecil dari kenyataan.
* **MKS-16 (DATA).** `account_id` yatim (menunjuk akun yang sudah tidak ada)
  sama buruknya: barisnya ada, tokonya tidak.
* **MKS-17..18 (ALUR PRODUK).** Tujuan koleksi impor harus tepat. Mesin impor
  lama menulis kampanye diskon ke `marketing_discount_campaigns` dan sample ke
  `marketing_sample_shipments` — dua koleksi yang **tidak pernah dibaca layar
  mana pun**. Impor "berhasil", datanya hilang.
* **MKS-19..20 (UANG).** Pembacaan angka & tanggal. "Rp 1.250.000" yang terbaca
  1.25 bukan hanya salah — ia salah dengan sopan, dan ikut ke laporan.
* **MKS-21 (ALUR PRODUK).** Pemetaan kolom harus jalan **tanpa AI** untuk header
  ekspor marketplace yang lazim. Kalau tidak, impor kembali bergantung layanan luar.
* **MKS-22 (gate menjaga dirinya).** Pemeriksaan lingkup diuji dengan
  **pelanggaran sintetis**: kalau detektornya rusak, gate ini harus merah.
* **MKS-23 (UANG).** Host/kreator yang belum di-assign ke toko harus DITOLAK;
  kalau tidak, jam kerja & komisi bisa dibebankan ke toko yang tidak memakainya.

Jalankan:  python3 scripts/verify_marketing_scope.py
           python3 scripts/verify_marketing_scope.py --explain   (uraian panjang)
"""
import os
import sys
import uuid
import asyncio
import argparse

sys.path.insert(0, "/app/backend")

from dotenv import load_dotenv                              # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient           # noqa: E402

load_dotenv("/app/backend/.env")

PASS, FAIL = [], []


def ok(code, msg):
    PASS.append(code)
    print(f"  ✓ {code:<12} {msg}")


def bad(code, msg):
    FAIL.append((code, msg))
    print(f"  ✗ {code:<12} {msg}")


# Koleksi marketing yang WAJIB berlingkup toko + kolom pembanding kalau ada.
SCOPED = {
    "marketing_orders": "MKS-1",
    "marketing_sales_data": "MKS-2",
    "marketing_ads_data": "MKS-3",
    "marketing_live_sessions": "MKS-4",
    "marketing_samples": "MKS-5",
    "marketing_content_calendar": "MKS-6",
    "marketing_discounts": "MKS-7",
    "marketing_product_launches": "MKS-8",
    "marketing_reviews": "MKS-9",
    "marketing_returns": "MKS-10",
    "marketing_complaints": "MKS-11",
    "marketing_account_health": "MKS-12",
    "marketing_tasks": "MKS-13",
    "marketing_livehost_shifts": "MKS-14",
    "marketing_catalogs": "MKS-15",
    # F18#3 — rincian produk per sesi live: baris ini menjumlahkan UANG per produk,
    # jadi kalau ada yang tak berlingkup toko, "produk terlaris toko A" ikut
    # menghitung penjualan toko B tanpa satu pun error.
    "marketing_live_session_products": "MKS-24",
}

# Koleksi yang mesin impor lama tulis TAPI tidak pernah dibaca layar.
FORBIDDEN_TARGETS = {
    "marketing_discount_campaigns": "marketing_discounts",
    "marketing_sample_shipments": "marketing_samples",
}


async def check_scope(db, explain: bool):
    accounts = {a["id"] async for a in db.marketing_platform_accounts.find({}, {"id": 1})
                if a.get("id")}
    total_unscoped = 0
    for coll, code in SCOPED.items():
        n = await db[coll].count_documents({})
        if n == 0:
            ok(code, f"{coll}: kosong (tidak ada yang bisa cacat)")
            continue
        missing = await db[coll].count_documents(
            {"$or": [{"account_id": {"$exists": False}},
                     {"account_id": None}, {"account_id": ""}]})
        orphan = 0
        examples = []
        async for d in db[coll].find({"account_id": {"$nin": [None, ""]}},
                                     {"account_id": 1, "_id": 0}):
            if d["account_id"] not in accounts:
                orphan += 1
                if len(examples) < 3:
                    examples.append(d["account_id"])
        total_unscoped += missing + orphan
        if missing or orphan:
            hint = ""
            if explain:
                hint = ("\n                 → jalankan: python3 scripts/"
                        "migrate_marketing_account_scope.py --execute")
            bad(code, f"{coll}: {n} dokumen, {missing} TANPA account_id, "
                      f"{orphan} account_id YATIM {examples}{hint}")
        else:
            ok(code, f"{coll}: {n} dokumen, semuanya berlingkup toko yang sah")
    return total_unscoped


async def check_forbidden(db):
    hit = []
    names = await db.list_collection_names()
    for bad_name, right in FORBIDDEN_TARGETS.items():
        if bad_name in names:
            n = await db[bad_name].count_documents({})
            if n:
                hit.append(f"{bad_name} ({n} dokumen) — seharusnya {right}")
    if hit:
        bad("MKS-16b", "koleksi tujuan impor SALAH masih terisi: " + "; ".join(hit))
    else:
        ok("MKS-16b", "tidak ada data di koleksi tujuan impor yang salah")


def check_schema():
    from core.marketing_import_schema import SOURCE_TYPES, LEGACY_ALIASES, get_source_type

    wrong = [f"{k} → {t.collection}" for k, t in SOURCE_TYPES.items()
             if t.collection in FORBIDDEN_TARGETS]
    if wrong:
        bad("MKS-17", "jenis data menunjuk koleksi yang tidak dibaca layar: "
                      + ", ".join(wrong))
    else:
        ok("MKS-17", f"{len(SOURCE_TYPES)} jenis data, semua koleksi tujuannya dibaca layar")

    checks = [("discount_campaign", "marketing_discounts"),
              ("sample_shipping", "marketing_samples")]
    problems = []
    for legacy, expected in checks:
        try:
            got = get_source_type(legacy).collection
        except KeyError as e:
            problems.append(f"{legacy}: {e}")
            continue
        if got != expected:
            problems.append(f"{legacy} → {got} (harus {expected})")
    if problems:
        bad("MKS-18", "alias jenis data lama salah arah: " + "; ".join(problems))
    else:
        ok("MKS-18", f"{len(LEGACY_ALIASES)} alias jenis lama diarahkan ke koleksi benar")

    # setiap jenis berlingkup toko WAJIB punya field turunan account_id
    miss = [t.key for t in SOURCE_TYPES.values()
            if t.account_scope == "required" and t.field("account_id") is None]
    if miss:
        bad("MKS-18b", "jenis berlingkup toko tanpa field account_id: " + ", ".join(miss))
    else:
        ok("MKS-18b", "semua jenis berlingkup toko punya field account_id")


def check_numbers():
    from core.marketing_import_engine import parse_number, parse_date

    cases = [
        ("Rp 1.250.000", 1250000.0),
        ("1.250.000", 1250000.0),
        ("1,250,000.50", 1250000.50),
        ("1.250.000,50", 1250000.50),
        ("1.240", 1240.0),
        ("120.500", 120500.0),
        ("750000", 750000.0),
        ("12,5", 12.5),
        ("(1.500)", -1500.0),
        ("IDR 89.000", 89000.0),
        (89000, 89000.0),
        (89000.5, 89000.5),
    ]
    wrong = []
    for raw, want in cases:
        got, err = parse_number(raw)
        if err or got is None or abs(got - want) > 1e-6:
            wrong.append(f"{raw!r} → {got} (harus {want}) {err or ''}")
    if wrong:
        bad("MKS-19", "pembacaan angka salah: " + " | ".join(wrong))
    else:
        ok("MKS-19", f"{len(cases)} format angka rupiah/inggris terbaca benar")

    # yang HARUS ditolak, bukan ditebak
    for raw in ("seratus ribu", "abc", "12,34,56"):
        got, err = parse_number(raw)
        if err is None and got is not None:
            bad("MKS-19b", f"angka ngawur {raw!r} diterima sebagai {got}")
            break
    else:
        ok("MKS-19b", "angka yang ambigu/ngawur DITOLAK, tidak ditebak")

    dcases = ["2026-08-01", "01/08/2026", "01-08-2026", "2026/08/01",
              "1 Agustus 2026", "2026-08-01 11:04:49"]
    dwrong = []
    for raw in dcases:
        d, err = parse_date(raw)
        if err or d is None or (d.year, d.month, d.day) != (2026, 8, 1):
            dwrong.append(f"{raw!r} → {d} {err or ''}")
    if dwrong:
        bad("MKS-20", "pembacaan tanggal salah: " + " | ".join(dwrong))
    else:
        ok("MKS-20", f"{len(dcases)} format tanggal terbaca benar")
    d, err = parse_date("bukan-tanggal")
    if err is None:
        bad("MKS-20b", "tanggal ngawur diterima")
    else:
        ok("MKS-20b", "tanggal ngawur DITOLAK dengan pesan yang bisa ditindaklanjuti")


def check_mapping_without_ai():
    """Header nyata dari ekspor marketplace harus terpetakan tanpa AI."""
    from core.marketing_import_engine import auto_map, mapping_report
    from core.marketing_import_schema import get_source_type

    scenarios = [
        ("orders", ["No. Pesanan", "Waktu Pesanan Dibuat", "Nomor Referensi SKU",
                    "Nama Produk", "Jumlah", "Harga Setelah Diskon", "Total Pembayaran",
                    "Nama Penerima", "Kota/Kabupaten", "Status Pesanan", "Jasa Kirim"]),
        ("ads", ["Tanggal", "Nama Kampanye", "Biaya", "Impresi", "Klik",
                 "Produk Terjual", "Penjualan dari iklan"]),
        ("live_sessions", ["Tanggal Live", "Judul", "Durasi", "Penonton",
                           "Peak Viewers", "Pesanan", "GMV"]),
        ("sales_daily", ["Tanggal", "Jenis", "Omzet", "Jumlah Pesanan"]),
        ("returns", ["Tanggal", "No Pesanan", "Produk", "Alasan"]),
    ]
    problems = []
    for key, headers in scenarios:
        st = get_source_type(key)
        m = auto_map(headers, st)
        rep = mapping_report(m, st)
        if not rep["ready"]:
            problems.append(f"{key}: kolom wajib belum terpetakan "
                            f"{rep['missing_required']}")
        if rep["methods"].get("exact", 0) + rep["methods"].get("synonym", 0) == 0:
            problems.append(f"{key}: tidak ada satu pun kecocokan pasti/sinonim")
    if problems:
        bad("MKS-21", "pemetaan tanpa AI gagal: " + " | ".join(problems))
    else:
        ok("MKS-21", f"{len(scenarios)} skenario header marketplace terpetakan TANPA AI")

    # fuzzy tidak boleh diam-diam memindahkan kolom uang
    st = get_source_type("orders")
    m = auto_map(["Harga Coret"], st)
    picked = m[0].get("field")
    if picked in ("price_final", "price_original") and m[0]["method"] == "fuzzy":
        bad("MKS-21b", f"'Harga Coret' dipetakan otomatis ke {picked} — kolom uang "
                       f"tidak boleh dipindah oleh kemiripan teks")
    else:
        ok("MKS-21b", "kemiripan teks tidak memindahkan kolom uang tanpa konfirmasi")


async def check_selftest(db):
    """PELANGGARAN SINTETIS — kalau detektornya rusak, gate ini harus merah."""
    coll = "marketing_ads_data"
    marker = f"GATE-MKS-{uuid.uuid4().hex[:8]}"
    await db[coll].insert_one({"id": marker, "campaign_name": marker,
                              "spend": 1, "_gate_selftest": True})
    missing = await db[coll].count_documents(
        {"$or": [{"account_id": {"$exists": False}}, {"account_id": None},
                 {"account_id": ""}]})
    detected = missing >= 1
    await db[coll].delete_one({"id": marker})
    left = await db[coll].count_documents({"_gate_selftest": True})
    if detected and left == 0:
        ok("MKS-22", "detektor lingkup TERBUKTI mendeteksi pelanggaran sintetis "
                     "dan jejak ujinya bersih")
    elif not detected:
        bad("MKS-22", "detektor lingkup TIDAK mendeteksi dokumen tanpa account_id "
                      "— gate ini tidak bisa dipercaya")
    else:
        bad("MKS-22", f"jejak uji gate tertinggal di {coll} ({left} dokumen)")


async def check_assignment(db):
    """Host/kreator yang belum di-assign harus ditolak — bukan diterima diam-diam."""
    from fastapi import HTTPException
    from core import marketing_account_scope as scope

    hid = f"GATE-HOST-{uuid.uuid4().hex[:6]}"
    aid = f"GATE-ACC-{uuid.uuid4().hex[:6]}"
    await db.marketing_livehosts.insert_one(
        {"id": hid, "name": "Gate Host", "assigned_account_ids": [], "_gate": True})
    raised = False
    try:
        await scope.assert_host_assigned(db, hid, aid)
    except HTTPException as e:
        raised = e.status_code == 400 and "assign" in str(e.detail).lower()
    await db.marketing_livehosts.delete_one({"id": hid})
    if raised:
        ok("MKS-23", "host yang belum di-assign ke toko DITOLAK dengan alasan jelas")
    else:
        bad("MKS-23", "host yang belum di-assign ke toko DITERIMA — jam kerja & gaji "
                      "bisa dibebankan ke toko yang tidak memakainya")

    cid = f"GATE-CR-{uuid.uuid4().hex[:6]}"
    await db.marketing_kol_creators.insert_one(
        {"id": cid, "name": "Gate Creator", "assigned_account_ids": [], "_gate": True})
    raised = False
    try:
        await scope.assert_creator_assigned(db, cid, aid)
    except HTTPException as e:
        raised = e.status_code == 400
    await db.marketing_kol_creators.delete_one({"id": cid})
    if raised:
        ok("MKS-23b", "kreator yang belum di-assign ke toko DITOLAK")
    else:
        bad("MKS-23b", "kreator yang belum di-assign ke toko DITERIMA")


async def check_live_products(db):
    """F18#3 — rincian produk sesi live: yatim · dobel · melebihi omzet sesi.

    Tiga cacat ini semuanya SUNYI dan semuanya soal UANG:
      · baris yatim (sesinya sudah dihapus) tetap terhitung di "produk terlaris";
      · produk dobel dalam satu sesi membuat satu penjualan dihitung dua kali;
      · jumlah rincian yang melebihi omzet sesi berarti omzet live dihitung dua
        kali — sekali di total sesi, sekali di rinciannya.
    """
    from core import marketing_live_products as LP

    coll = LP.COLLECTION
    n = await db[coll].count_documents({})
    if n == 0:
        ok("MKS-25", f"{coll}: kosong (tidak ada yang bisa cacat)")
        ok("MKS-26", f"{coll}: kosong")
        ok("MKS-27", f"{coll}: kosong")
        return

    session_ids = {s["id"] async for s in db.marketing_live_sessions.find({}, {"id": 1})
                   if s.get("id")}
    orphan, dupe_keys, per_session = 0, [], {}
    seen = set()
    async for d in db[coll].find({}, {"_id": 0, "session_id": 1, "catalog_item_id": 1,
                                      "revenue": 1}):
        sid = d.get("session_id")
        if sid not in session_ids:
            orphan += 1
            continue
        key = (sid, d.get("catalog_item_id"))
        if key in seen:
            dupe_keys.append(key)
        seen.add(key)
        per_session.setdefault(sid, 0.0)
        per_session[sid] += LP.num(d.get("revenue"))

    if orphan:
        bad("MKS-25", f"{coll}: {orphan} baris rincian YATIM (sesi live-nya sudah "
                      f"tidak ada) — masih ikut terhitung di laporan produk terlaris")
    else:
        ok("MKS-25", f"{coll}: {n} baris, tidak ada yang yatim")

    if dupe_keys:
        bad("MKS-26", f"{coll}: {len(dupe_keys)} produk DOBEL dalam satu sesi "
                      f"{dupe_keys[:3]} — satu penjualan terhitung dua kali")
    else:
        ok("MKS-26", f"{coll}: tidak ada produk dobel dalam satu sesi")

    over = []
    async for s in db.marketing_live_sessions.find(
            {"id": {"$in": list(per_session)}},
            {"_id": 0, "id": 1, "title": 1, "revenue": 1, "gmv": 1}):
        s_rev = LP.num(s.get("revenue") or s.get("gmv"))
        det = per_session.get(s["id"], 0.0)
        if s_rev > 0 and det > s_rev * (1 + LP.OVER_TOLERANCE):
            over.append(f"{s.get('title')}: rincian {LP.rp(det)} > sesi {LP.rp(s_rev)}")
    if over:
        bad("MKS-27", f"{len(over)} sesi live dengan rincian MELEBIHI omzetnya: "
                      + " | ".join(over[:3]))
    else:
        ok("MKS-27", f"{len(per_session)} sesi berincian, tidak ada yang melebihi omzetnya")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--explain", action="store_true")
    args = ap.parse_args()

    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ.get("DB_NAME", "test_database")]

    print("=" * 82)
    print("INV-MKTSCOPE — lingkup toko & mesin impor marketing")
    print("=" * 82)
    print("\n· LINGKUP TOKO (setiap baris marketing milik satu toko)")
    await check_scope(db, args.explain)
    print("\n· TUJUAN KOLEKSI IMPOR")
    await check_forbidden(db)
    check_schema()
    print("\n· RINCIAN PRODUK SESI LIVE (F18#3)")
    await check_live_products(db)
    print("\n· PEMBACAAN ANGKA & TANGGAL")
    check_numbers()
    print("\n· PEMETAAN KOLOM TANPA AI")
    check_mapping_without_ai()
    print("\n· GATE MENJAGA DIRINYA & KEWENANGAN")
    await check_selftest(db)
    await check_assignment(db)

    print("\n" + "=" * 82)
    print(f"HASIL: {len(PASS)} PASS · {len(FAIL)} FAIL")
    if FAIL:
        print("\nYANG MERAH:")
        for code, msg in FAIL:
            print(f"  ✗ {code} — {msg}")
    print("=" * 82)
    cli.close()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
