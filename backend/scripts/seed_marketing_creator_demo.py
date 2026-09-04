#!/usr/bin/env python3
"""seed_marketing_creator_demo — data demo **KREATOR + KONTEN + SESI + TARGET**.

KENAPA SEEDER INI ADA (2026-08-14)
----------------------------------
Layar **Scorecard Kreator** (`/api/marketing/targets/creator/scorecard`) sudah
benar, tetapi environment hasil bootstrap TIDAK punya satu pun kreator, konten,
maupun sesi live — sehingga layarnya selalu berbunyi *"Belum ada kreator yang
bisa dinilai"*. Akibatnya dua hal yang sama-sama buruk:

* fitur yang sudah jadi **tampak belum jadi** (agent berikutnya mengerjakannya lagi);
* cacat sesungguhnya **tidak pernah terlihat** — layar kosong tidak bisa salah.

ATURAN YANG DIPATUHI SEEDER INI
-------------------------------
1. **Tidak membuat master toko baru.** Ia MEMAKAI toko aktif yang sudah ada.
   Membuat toko sendiri = master ganda (pelanggaran SSOT §aturan 1).
2. **Idempoten.** Dijalankan 2× ⇒ jumlah dokumen sama (kunci: `creator_code`,
   `published_url`, `(creator_id, date)`).
3. **Sengaja TIDAK sempurna**: satu kreator dibiarkan TANPA target dan beberapa
   konten TANPA KPI, supaya keadaan "belum ada target" (bukan 0%) dan "cakupan
   KPI < 100%" benar-benar terlihat di layar — dua hal yang paling sering
   disembunyikan oleh data demo yang terlalu rapi.
4. **Uang tidak dikarang.** Pesanan tidak dibuat di sini. Yang dilakukan hanya
   MENAUTKAN pesanan demo yang sudah ada (`DEMO-A-*`) ke seorang kreator, supaya
   kolom "Omzet pesanan" punya isi tanpa menambah omzet baru ke pembukuan.
5. **`viewers` DAN `peak_viewers` ditulis dua-duanya** — bentuk kanonik yang
   dipakai penulis nyata (`marketing_kol_ops`, `marketing_kol_portal`). Seeder
   lama hanya menulis `peak_viewers`, sehingga kolom "Penonton" scorecard 0.

Pakai:  cd /app/backend && python3 scripts/seed_marketing_creator_demo.py [--cleanup]
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db  # noqa: E402

MARK = "seed_creator_demo"          # penanda: hanya dokumen bertanda ini yang dibuang
G, Y, X = "\033[92m", "\033[93m", "\033[0m"


def _now() -> datetime:
    return datetime.now(timezone.utc)


CREATORS = [
    {"creator_code": "KRE-DEMO-01", "name": "Rina Live", "handle": "@rinalive",
     "tier": "mid", "commission_pct": 5.0},
    {"creator_code": "KRE-DEMO-02", "name": "Bayu Konten", "handle": "@bayukonten",
     "tier": "micro", "commission_pct": 4.0},
    # kreator ke-3 SENGAJA tidak diberi target bulan ini
    {"creator_code": "KRE-DEMO-03", "name": "Sinta Affiliate", "handle": "@sintaaff",
     "tier": "micro", "commission_pct": 3.5},
]

# (hari, jenis, judul, status, kpi | None → konten tanpa KPI)
CONTENTS = [
    (3,  "video",  "Racun cek keranjang kaos polos",  "posted",
     {"views": 42000, "likes": 3100, "comments": 210, "shares": 180, "saves": 260,
      "orders": 96, "gmv": 14200000}),
    (6,  "live",   "Live malam: hoodie fleece",       "posted",
     {"views": 18500, "likes": 1200, "comments": 340, "shares": 60, "saves": 90,
      "orders": 41, "gmv": 8100000}),
    (9,  "video",  "Before-after outfit kerja",        "posted", None),
    (12, "photo",  "Katalog warna baru",              "posted",
     {"views": 9200, "likes": 640, "comments": 45, "shares": 22, "saves": 130,
      "orders": 12, "gmv": 1850000}),
    (15, "video",  "Tips padu-padan hoodie",          "draft",  None),
]

SESSIONS = [
    (5,  "Live sore: kaos polos",  6200000, 1450, 210, 62),
    (11, "Live malam: hoodie",     9350000, 2100, 260, 88),
]


async def wipe(db) -> None:
    codes = [c["creator_code"] for c in CREATORS]
    creators = await db.marketing_kol_creators.find(
        {"creator_code": {"$in": codes}}, {"_id": 0, "id": 1}).to_list(50)
    ids = [c["id"] for c in creators]
    r1 = await db.marketing_content_calendar.delete_many({"_seed": MARK})
    r2 = await db.marketing_creator_sessions.delete_many({"_seed": MARK})
    r3 = await db.marketing_creator_targets.delete_many({"_seed": MARK})
    r4 = await db.marketing_kol_creators.delete_many({"creator_code": {"$in": codes}})
    if ids:
        await db.marketing_orders.update_many(
            {"creator_id": {"$in": ids}},
            {"$unset": {"creator_id": "", "creator_name": "", "_seed_creator_link": ""}})
    print(f"{Y}dibuang{X}: konten={r1.deleted_count} sesi={r2.deleted_count} "
          f"target={r3.deleted_count} kreator={r4.deleted_count}")


async def main(cleanup: bool = False) -> int:
    db = get_db()
    if cleanup:
        await wipe(db)
        return 0

    acc = await db.marketing_platform_accounts.find_one(
        {"status": "active"}, {"_id": 0, "id": 1, "account_name": 1, "platform": 1},
        sort=[("account_name", 1)])
    if not acc:
        print("TIDAK ADA toko aktif — jalankan seed marketing dulu "
              "(POST /api/marketing/seed-sample-data). Seeder ini TIDAK membuat toko.")
        return 1
    now = _now()
    y, m = now.year, now.month

    made = {"creators": 0, "contents": 0, "sessions": 0, "targets": 0, "orders": 0}
    creator_ids: list[str] = []
    for i, c in enumerate(CREATORS):
        doc = await db.marketing_kol_creators.find_one(
            {"creator_code": c["creator_code"]}, {"_id": 0, "id": 1})
        if doc:
            cid = doc["id"]
        else:
            cid = str(uuid.uuid4())
            await db.marketing_kol_creators.insert_one({
                "id": cid, "creator_code": c["creator_code"], "name": c["name"],
                "handle": c["handle"], "platform": acc.get("platform") or "shopee",
                "tier": c["tier"], "commission_pct": c["commission_pct"],
                "status": "active",
                "assigned_account_ids": [acc["id"]],
                "created_at": now, "created_by": MARK, "_seed": MARK,
            })
            made["creators"] += 1
        creator_ids.append(cid)

        # ── KONTEN + KPI ────────────────────────────────────────────────────
        for day, ctype, title, status, kpi in CONTENTS:
            date = f"{y:04d}-{m:02d}-{min(day + i, 28):02d}"
            url = (f"https://demo.shopee.co.id/video/{c['creator_code'].lower()}-"
                   f"{date}-{day}")
            # Kunci idempoten harus BUKAN `published_url`: konten berstatus
            # `draft` tidak punya link terbit (aturan F7: link wajib hanya untuk
            # `posted`), jadi dedupe by-URL akan menyisipkannya ulang setiap kali
            # seeder dijalankan — itu yang terjadi pada percobaan pertama.
            doc_id = f"seedc-{c['creator_code'].lower()}-{date}-{day}"
            if await db.marketing_content_calendar.find_one({"id": doc_id},
                                                            {"_id": 0, "id": 1}):
                continue
            d = {"id": doc_id, "date": date, "content_type": ctype,
                 "title": f"{title} — {c['name']}", "status": status,
                 "account_id": acc["id"], "account_name": acc.get("account_name"),
                 "creator_id": cid, "creator_name": c["name"],
                 "created_at": now, "created_by": MARK, "_seed": MARK}
            if status == "posted":
                d["published_url"] = url
                d["published_at"] = date
            if kpi:
                # Angka DIBEDAKAN per kreator. Data demo yang identik untuk semua
                # kreator membuat layar tampak salah (tiga baris dengan GMV & views
                # yang sama persis) dan menyembunyikan kesalahan agregasi kalau
                # nanti benar-benar ada.
                f = (1.0, 0.62, 0.38)[i % 3]
                kpi = {k: (round(v * f) if isinstance(v, (int, float)) else v)
                       for k, v in kpi.items()}
                eng = kpi["likes"] + kpi["comments"] + kpi["shares"]
                views = kpi["views"]
                d["kpi"] = dict(kpi, watch_time_avg_sec=0, ctr=0)
                d["kpi_derived"] = {
                    "engagement": eng,
                    "engagement_rate": round(eng / views * 100, 2) if views else 0.0,
                    "save_rate": round(kpi["saves"] / views * 100, 2) if views else 0.0,
                    "cvr": round(kpi["orders"] / views * 100, 4) if views else 0.0,
                    "gmv_per_view": round(kpi["gmv"] / views, 2) if views else 0.0,
                    "aov": round(kpi["gmv"] / kpi["orders"], 2) if kpi["orders"] else 0.0,
                }
                d["kpi_source"] = "seed_demo"
                d["kpi_updated_at"] = now
            await db.marketing_content_calendar.insert_one(d)
            made["contents"] += 1

        # ── SESI LIVE (dua kreator pertama saja) ───────────────────────────
        if i < 2:
            for day, name, rev, viewers, peak, orders in SESSIONS:
                date = f"{y:04d}-{m:02d}-{min(day + i, 28):02d}"
                if await db.marketing_creator_sessions.find_one(
                        {"creator_id": cid, "date": date}, {"_id": 0, "id": 1}):
                    continue
                await db.marketing_creator_sessions.insert_one({
                    "id": str(uuid.uuid4()), "creator_id": cid,
                    "creator_name": c["name"], "creator_code": c["creator_code"],
                    "account_id": acc["id"], "account_name": acc.get("account_name"),
                    "platform": acc.get("platform") or "shopee", "date": date,
                    "session_name": f"{name} — {c['name']}",
                    "duration_minutes": 95,
                    "viewers": round(viewers * (1.0, 0.62)[i % 2]),
                    "peak_viewers": round(peak * (1.0, 0.62)[i % 2]),
                    "revenue": round(rev * (1.0, 0.62)[i % 2]),
                    "orders": round(orders * (1.0, 0.62)[i % 2]),
                    "created_at": now, "created_by": MARK, "_seed": MARK,
                })
                made["sessions"] += 1

        # ── TARGET BULAN INI (kreator ke-3 SENGAJA tanpa target) ───────────
        if i < 2 and not await db.marketing_creator_targets.find_one(
                {"creator_id": cid, "year": y, "month": m}, {"_id": 0, "id": 1}):
            await db.marketing_creator_targets.insert_one({
                "id": str(uuid.uuid4()), "creator_id": cid,
                "creator_name": c["name"], "year": y, "month": m,
                "revenue_target": 25000000 if i == 0 else 12000000,
                "sessions_target": 4, "viewers_target": 5000,
                "notes": "target demo (seeder kreator)",
                "created_at": now, "created_by": MARK, "_seed": MARK,
            })
            made["targets"] += 1

    # ── TAUTKAN pesanan demo yang SUDAH ADA ke kreator #1 ────────────────────
    if creator_ids:
        res = await db.marketing_orders.update_many(
            {"order_id": {"$regex": "^DEMO-A-"},
             "$or": [{"creator_id": {"$in": [None, ""]}},
                     {"creator_id": {"$exists": False}}]},
            {"$set": {"creator_id": creator_ids[0], "creator_name": CREATORS[0]["name"],
                      "_seed_creator_link": MARK}})
        made["orders"] = res.modified_count
        # SESI #9 — JARING PENGAMAN: environment yang di-bootstrap TANPA impor
        # `samples/ekspor_A_*.csv` tidak punya satu pun pesanan `DEMO-A-`, jadi
        # kolom "omzet pesanan" di Scorecard Kreator SELALU Rp 0 dan kolom baru
        # "Setelah retur" tidak pernah bisa dinilai (nol tidak bisa salah).
        # Kalau begitu keadaannya, tautkan sebagian pesanan yang MEMANG ada —
        # termasuk yang berstatus retur — supaya layar memperlihatkan ketiga
        # angka (bruto · retur · setelah retur). Bertanda `_seed_creator_link`
        # sehingga `--cleanup` bisa melepasnya kembali.
        if not made["orders"]:
            agg = await db.marketing_orders.aggregate([
                {"$match": {"creator_id": {"$in": [None, ""]}}},
                {"$group": {"_id": "$account_id", "n": {"$sum": 1}}},
                {"$sort": {"n": -1}}, {"$limit": 1}]).to_list(1)
            if agg:
                aid = agg[0]["_id"]
                # utamakan pesanan RETUR supaya keadaan retur ikut terwakili
                ret_ids = [o["id"] for o in await db.marketing_orders.find(
                    {"account_id": aid, "status": "returned",
                     "creator_id": {"$in": [None, ""]}}, {"_id": 0, "id": 1}).to_list(10)]
                oth_ids = [o["id"] for o in await db.marketing_orders.find(
                    {"account_id": aid, "status": {"$ne": "returned"},
                     "creator_id": {"$in": [None, ""]}},
                    {"_id": 0, "id": 1}).sort("order_date", -1).to_list(40)]
                pick = ret_ids + oth_ids
                if pick:
                    res2 = await db.marketing_orders.update_many(
                        {"id": {"$in": pick}},
                        {"$set": {"creator_id": creator_ids[0],
                                  "creator_name": CREATORS[0]["name"],
                                  "_seed_creator_link": MARK}})
                    made["orders"] = res2.modified_count

    print(f"{G}SELESAI{X} — toko demo: {acc.get('account_name')} · "
          f"kreator +{made['creators']} · konten +{made['contents']} · "
          f"sesi +{made['sessions']} · target +{made['targets']} · "
          f"pesanan ditautkan {made['orders']}")
    print("   catatan: kreator ke-3 SENGAJA tanpa target, 2 konten SENGAJA tanpa KPI "
          "(supaya 'belum ada target' & 'cakupan KPI' terlihat di layar).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--cleanup" in sys.argv)))
