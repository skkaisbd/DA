#!/usr/bin/env python3
"""_verify_f1_shop_guard.py — BUKTI: PENJAGA TOKO (sidik gudang platform di berkas).

CACAT YANG DITUTUP (terjadi nyata 2026-08-12)
---------------------------------------------
Penjaga platform yang sudah ada hanya menangkap "berkas Shopee masuk toko TikTok".
Ia TIDAK menangkap kesalahan yang jauh lebih mudah terjadi: memilih **toko TikTok
yang salah** dari 5 toko TikTok yang namanya mirip (Daluna / Outfit Boutique /
Style by Moen / Fatimahijab / Dezza Kids). Saat uji UI berjalan, 559 pesanan
gudang 'Outfit Boutique' (Rp 59.783.811) masuk ke toko **TikTok Daluna** — commit
berhasil, rekap harian ikut terbentuk, dan **tidak ada satu pun layar yang
membantah**. Omzet satu toko muncul di toko lain, dan tidak ada cara menemukannya
selain menghitung ulang dari berkas asal.

Padahal buktinya ada di berkas: ekspor Seller Center membawa kolom
`Warehouse Name` = 'Outfit Boutique' pada SEMUA barisnya, dan master toko sudah
menyimpannya sejak F0.7 (`platform_warehouse_name`). Yang belum ada hanyalah
pembandingnya.

KONTRAK
-------
  SG-1  berkas gudang 'Outfit Boutique' ke toko yang gudangnya BEDA ⇒ 400,
        pesannya menyebut gudang berkas & gudang toko tujuan.
  SG-2  berkas yang sama ke toko yang BENAR ⇒ 200 (tidak ada regresi).
  SG-3  toko tujuan belum mengisi gudang, tapi gudang itu terdaftar pada toko
        LAIN ⇒ 400 yang MENYEBUT nama toko pemiliknya (bukan sekadar "salah").
  SG-4  toko tujuan belum mengisi gudang & tidak ada toko lain yang memilikinya
        ⇒ 200 + `shop_guard_hint` (tidak memblokir, tapi menjelaskan risikonya).
  SG-5  tidak ada berkas sampah tertinggal di /app/uploads untuk unggahan ditolak.

Pakai:  python3 /app/scripts/_verify_f1_shop_guard.py
"""
from __future__ import annotations


import glob
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

sys.path.insert(0, "/app/backend")

BASE = "http://localhost:8001"
SAMPLE = "/app/samples/TikTok_UntukDikirim_2026-07-19.xlsx"
UPLOAD_DIR = "/app/uploads/marketing-data-import"
RIGHT = "TIKTOK-OUTFIT"     # gudang platform 'Outfit Boutique'
WRONG = "TIKTOK-MOEN"       # toko TikTok lain
FAILED: list[str] = []


def check(name: str, cond, detail: str = "") -> bool:
    mark = "\033[92mPASS\033[0m" if cond else "\033[91mFAIL\033[0m"
    print(f"  {mark}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)
    return bool(cond)


def upload(H: dict, account_id: str):
    with open(SAMPLE, "rb") as fh:
        return requests.post(
            f"{BASE}/api/marketing/data-import/upload", headers=H,
            files={"file": (os.path.basename(SAMPLE), fh,
                            "application/vnd.openxmlformats-officedocument"
                            ".spreadsheetml.sheet")},
            data={"source_type": "marketplace_orders", "account_id": account_id},
            timeout=300)


def set_warehouse(account_code: str, value: str):
    """Ubah gudang platform master toko langsung di DB (pymongo — sinkron).

    Sengaja TIDAK memakai `motor` lewat asyncio.run(): klien motor mengunci event
    loop pertama yang memakainya, jadi panggilan kedua mati 'Event loop is closed'.
    """
    from pymongo import MongoClient
    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = cli[os.environ.get("DB_NAME", "test_database")]
    db.marketing_platform_accounts.update_one(
        {"account_code": account_code}, {"$set": {"platform_warehouse_name": value}})
    cli.close()


def main() -> int:
    tok = requests.post(f"{BASE}/api/auth/login", json={
        "email": "admin@garment.com", "password": "Admin@123"}, timeout=30).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}

    accs = requests.get(f"{BASE}/api/marketing/accounts", headers=H, timeout=30).json()
    accs = accs.get("accounts", accs) if isinstance(accs, dict) else accs
    by_code = {a.get("account_code"): a for a in accs}
    if not check("toko uji ada (TIKTOK-OUTFIT & TIKTOK-MOEN)",
                 RIGHT in by_code and WRONG in by_code):
        return 1
    check("master toko menyimpan gudang platform 'Outfit Boutique'",
          (by_code[RIGHT].get("platform_warehouse_name") or "").strip() == "Outfit Boutique",
          repr(by_code[RIGHT].get("platform_warehouse_name")))

    files_before = set(glob.glob(f"{UPLOAD_DIR}/*"))
    sessions: list[str] = []

    # ── SG-1 — toko tujuan punya gudang LAIN ─────────────────────────────────
    set_warehouse(WRONG, "Style by Moen")
    r = upload(H, by_code[WRONG]["id"])
    d = (r.json() or {}).get("detail", "") if r.status_code != 200 else ""
    check("SG-1 berkas gudang 'Outfit Boutique' ke toko bergudang lain ⇒ 400",
          r.status_code == 400, f"{r.status_code}")
    check("SG-1b pesan menyebut gudang berkas DAN gudang toko tujuan",
          "Outfit Boutique" in d and "Style by Moen" in d, d[:200])

    # ── SG-3 — toko tujuan belum mengisi gudang, tapi gudangnya milik toko lain ─
    set_warehouse(WRONG, "")
    r3 = upload(H, by_code[WRONG]["id"])
    d3 = (r3.json() or {}).get("detail", "") if r3.status_code != 200 else ""
    check("SG-3 gudang berkas terdaftar pada toko LAIN ⇒ 400", r3.status_code == 400,
          f"{r3.status_code}")
    check("SG-3b pesan MENYEBUT nama toko pemilik gudang",
          "TikTok Outfit Boutique" in d3, d3[:240])

    # ── SG-4 — tidak ada toko mana pun yang memiliki gudang itu ⇒ boleh + hint ─
    set_warehouse(RIGHT, "")
    try:
        r4 = upload(H, by_code[WRONG]["id"])
        ok4 = r4.status_code == 200
        hint = (r4.json().get("session", {}).get("shop_guard_hint") or "") if ok4 else ""
        check("SG-4 tidak ada pemilik gudang ⇒ 200 (tidak memblokir)", ok4,
              f"{r4.status_code} {'' if ok4 else str(r4.json())[:160]}")
        check("SG-4b sesi membawa `shop_guard_hint` yang menjelaskan risikonya",
              "Outfit Boutique" in hint and "Gudang Platform" in hint, hint[:220])
        if ok4:
            sessions.append(r4.json()["session"]["id"])
    finally:
        set_warehouse(RIGHT, "Outfit Boutique")
        set_warehouse(WRONG, "")

    # ── SG-2 — toko yang BENAR tetap boleh (tidak ada regresi) ───────────────
    r2 = upload(H, by_code[RIGHT]["id"])
    check("SG-2 berkas ke toko yang BENAR ⇒ 200", r2.status_code == 200,
          f"{r2.status_code} {'' if r2.status_code == 200 else str(r2.json())[:160]}")
    if r2.status_code == 200:
        s2 = r2.json()["session"]
        sessions.append(s2["id"])
        check("SG-2b sesi menyebut toko tujuan + kode + platform",
              s2.get("account_name") == "TikTok Outfit Boutique"
              and s2.get("account_code") == RIGHT
              and s2.get("account_platform") == "tiktokshop",
              f"{s2.get('account_name')} / {s2.get('account_code')} / {s2.get('account_platform')}")
        check("SG-2c toko yang benar TIDAK diberi peringatan gudang",
              not s2.get("shop_guard_hint"), repr(s2.get("shop_guard_hint"))[:120])

    # ── SG-5 — berkas unggahan yang DITOLAK tidak menumpuk di disk ───────────
    files_after = set(glob.glob(f"{UPLOAD_DIR}/*"))
    leftover = len(files_after - files_before) - len(sessions)
    check("SG-5 tidak ada berkas sampah dari unggahan yang ditolak",
          leftover <= 0, f"berkas baru={len(files_after - files_before)} sesi sah={len(sessions)}")

    # ── bersih-bersih ────────────────────────────────────────────────────────
    for sid in sessions:
        requests.delete(f"{BASE}/api/marketing/data-import/sessions/{sid}",
                        headers=H, timeout=60)
    print(f"  (bersih-bersih: {len(sessions)} sesi uji dihapus)")

    print()
    if FAILED:
        print(f"\033[91mGAGAL: {len(FAILED)}\033[0m — {FAILED}")
        return 1
    print("\033[92mSEMUA PASS — penjaga toko (sidik gudang) bekerja\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
