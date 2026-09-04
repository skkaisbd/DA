#!/usr/bin/env python3
"""test_core_f07_accounts_ui.py — POC/CORE TEST untuk F0.7 (UI Manajemen Akun).

MEMBUKTIKAN (lewat HTTP nyata + verifikasi DB, bukan mock):
  T1  daftar akun mengembalikan field F0.7 (9 toko nyata + 3 demo)
  T2  /accounts/coa-options layak dipakai dropdown:
        · pendapatan  = hanya akun penjualan (is_sales, bukan grup, bukan kontra)
        · kas/bank    = hanya akun kas/bank/e-wallet (BUKAN piutang/persediaan/pajak)
        · piutang     = akun piutang, default 1-220
        · default_cash + fallback pendapatan per platform + opsi basis omzet
  T3  POST akun dengan SEMUA field F0.7 (termasuk PIC) tersimpan
  T4  POST otomatis membuat akun COA subledger piutang channel
        (anak `1-220`, kode tertulis balik ke `ar_account_code`)  ← permintaan owner
  T5  POST tanpa COA tetap dapat "alamat jurnal": pendapatan penampung per platform
        (4-114 Shopee / 4-126 TikTok / 4-131 Tokopedia) + kas default + piutang 1-220
  T6  POST/PUT dengan kode COA yang tidak ada di bagan akun ⇒ 400 + pesan jelas
  T7  POST dengan revenue_basis ngawur ⇒ 400
  T8  PUT mengubah SEMUA field baru (COA, basis, gudang platform, shop id, PIC,
        status, needs_owner_review) ⇒ tersimpan & terbaca kembali
  T9  DELETE (archive) ⇒ status inactive, dokumen tidak hilang
  T10 backfill subledger: 9 toko hasil seed (yang di-insert lewat skrip, bypass API)
        semuanya punya `ar_account_code` yang benar-benar ada di COA

Pakai:
    python3 /app/scripts/test_core_f07_accounts_ui.py
Keluar 0 bila semua PASS.
"""
from __future__ import annotations

import asyncio
import sys
import uuid

import requests

sys.path.insert(0, "/app/backend")

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}

RESULTS: list[tuple[str, bool, str]] = []
CREATED_IDS: list[str] = []


def ok(name: str, detail: str = ""):
    RESULTS.append((name, True, detail))
    print(f"  \033[92mPASS\033[0m  {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = ""):
    RESULTS.append((name, False, detail))
    print(f"  \033[91mFAIL\033[0m  {name}" + (f" — {detail}" if detail else ""))


def check(name: str, cond: bool, detail: str = ""):
    (ok if cond else fail)(name, detail)
    return cond


def login() -> str:
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    j = r.json()
    tok = j.get("token") or j.get("access_token") or (j.get("data") or {}).get("token")
    if not tok:
        raise SystemExit(f"login gagal, respons: {str(j)[:300]}")
    return tok


# ══════════════════════════════════════════════════════════════════════════════
def _db():
    """Akses DB langsung (pymongo/sinkron) — verifikasi bukti, bukan lewat API."""
    import os
    from dotenv import load_dotenv
    from pymongo import MongoClient
    load_dotenv("/app/backend/.env")
    cli = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000)
    return cli[os.environ.get("DB_NAME", "test_database")]


def db_get_account(account_id: str):
    return _db().marketing_platform_accounts.find_one({"id": account_id}, {"_id": 0})


def db_get_coa(code: str):
    return _db().rahaza_coa_accounts.find_one({"code": code}, {"_id": 0})


def db_cleanup(ids: list[str]):
    db = _db()
    for aid in ids:
        doc = db.marketing_platform_accounts.find_one({"id": aid}, {"_id": 0})
        if doc and doc.get("ar_account_code"):
            db.rahaza_coa_accounts.delete_many({"code": doc["ar_account_code"]})
        db.marketing_platform_accounts.delete_one({"id": aid})


# ══════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print("=" * 86)
    print("CORE TEST F0.7 — kontrak API Manajemen Akun untuk UI")
    print("=" * 86)
    token = login()
    H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    G = lambda p: requests.get(f"{BASE}{p}", headers=H, timeout=60)            # noqa: E731
    P = lambda p, b: requests.post(f"{BASE}{p}", headers=H, json=b, timeout=60)  # noqa: E731
    U = lambda p, b: requests.put(f"{BASE}{p}", headers=H, json=b, timeout=60)   # noqa: E731
    D = lambda p: requests.delete(f"{BASE}{p}", headers=H, timeout=60)         # noqa: E731

    F07_FIELDS = ("coa_revenue_code", "coa_cash_code", "coa_receivable_code",
                  "revenue_basis", "platform_warehouse_name", "platform_shop_id")

    # ── T1 daftar akun ────────────────────────────────────────────────────────
    print("\n[T1] GET /api/marketing/accounts")
    r = G("/api/marketing/accounts")
    accounts = r.json() if r.status_code == 200 else []
    check("T1.1 status 200 & list", r.status_code == 200 and isinstance(accounts, list),
          f"status={r.status_code} n={len(accounts) if isinstance(accounts, list) else '-'}")
    real = [a for a in accounts if a.get("coa_revenue_code")]
    check("T1.2 ada toko nyata ber-COA pendapatan", len(real) >= 9, f"{len(real)} toko")
    if real:
        miss = [f for f in F07_FIELDS if f not in real[0]]
        check("T1.3 field F0.7 ikut terkirim ke UI", not miss, f"hilang={miss}")

    # ── T2 coa-options ────────────────────────────────────────────────────────
    print("\n[T2] GET /api/marketing/accounts/coa-options")
    r = G("/api/marketing/accounts/coa-options")
    opt = r.json() if r.status_code == 200 else {}
    check("T2.1 status 200", r.status_code == 200, f"status={r.status_code}")
    rev = opt.get("revenue") or []
    cash = opt.get("cash") or []
    recv = opt.get("receivable") or []
    check("T2.2 grup pendapatan/kas/piutang terisi",
          bool(rev) and bool(cash) and bool(recv), f"rev={len(rev)} cash={len(cash)} recv={len(recv)}")
    rev_codes = {x["code"] for x in rev}
    check("T2.3 akun pendapatan per toko ada (4-111..4-131)",
          {"4-111", "4-122", "4-131"} <= rev_codes, f"contoh={sorted(rev_codes)[:6]}")
    check("T2.4 pendapatan TIDAK memuat akun kontra/grup (retur/diskon/potongan)",
          not ({"4-140", "4-141", "4-1200", "4-1300", "4-100", "4-1000"} & rev_codes),
          f"kotor={sorted({'4-140','4-141','4-1200','4-1300','4-100','4-1000'} & rev_codes)}")
    cash_codes = {x["code"] for x in cash}
    dirty_cash = {"1-1300", "1-1301", "1-1302", "1-1401", "1-1402", "1-1404",
                  "1-1500", "1-1501", "1-1502", "1-1600", "1-1610", "1-1620",
                  "1-120", "1-100", "1-1000", "1-1200", "1-130", "1-150"} & cash_codes
    check("T2.5 kas/bank bersih (bukan piutang/persediaan/pajak/grup)",
          not dirty_cash, f"kotor={sorted(dirty_cash)}")
    check("T2.6 kas/bank memuat rekening pencairan nyata (1-131, ShopeePay 1-154)",
          {"1-131", "1-154"} <= cash_codes, f"n={len(cash_codes)}")
    check("T2.7 default piutang = 1-220", opt.get("default_receivable") == "1-220",
          str(opt.get("default_receivable")))
    check("T2.8 default kas tersedia & valid",
          bool(opt.get("default_cash")) and opt.get("default_cash") in cash_codes,
          str(opt.get("default_cash")))
    fb = opt.get("fallback_revenue_by_platform") or {}
    check("T2.9 fallback pendapatan penampung per platform",
          fb.get("shopee") == "4-114" and fb.get("tiktokshop") == "4-126" and fb.get("tokopedia"),
          str(fb))
    basis_opts = opt.get("revenue_basis_options") or []
    check("T2.10 opsi basis omzet (2 pilihan berlabel)",
          len(basis_opts) == 2 and all(x.get("value") and x.get("label") for x in basis_opts),
          str([x.get("value") for x in basis_opts]))
    check("T2.11 setiap opsi pendapatan punya nama akun (label dropdown)",
          all(x.get("name") for x in rev), "")

    # PIC kandidat (dipakai T3/T8)
    ru = G("/api/auth/users?limit=100")
    users = ru.json() if ru.status_code == 200 else []
    users = users if isinstance(users, list) else (users.get("items") or users.get("users") or [])
    pic = next((u for u in users if u.get("id")), None)
    check("T2.12 daftar user untuk dropdown PIC", bool(pic), f"n={len(users)}")

    # ── T3 + T4 create lengkap + auto subledger COA ───────────────────────────
    print("\n[T3/T4] POST /api/marketing/accounts — semua field F0.7 + auto COA subledger")
    sfx = uuid.uuid4().hex[:6].upper()
    payload = {
        "account_code": f"POC-FULL-{sfx}",
        "account_name": f"POC Toko Lengkap {sfx}",
        "platform": "tiktokshop",
        "username": "poc_full_shop",
        "group": "official_store",
        "has_api_integration": True,
        "coa_revenue_code": "4-122",
        "coa_cash_code": "1-154",
        "coa_receivable_code": "1-220",
        "revenue_basis": "order_amount",
        "platform_warehouse_name": "Outfit Boutique",
        "platform_shop_id": "7495123456789",
    }
    if pic:
        payload["pic_user_id"] = pic["id"]
    r = P("/api/marketing/accounts", payload)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    acc = (body or {}).get("account") or {}
    created_ok = check("T3.1 POST 200", r.status_code == 200, f"status={r.status_code} {str(body)[:180]}")
    if created_ok and acc.get("id"):
        CREATED_IDS.append(acc["id"])
        for f, want in (("coa_revenue_code", "4-122"), ("coa_cash_code", "1-154"),
                        ("coa_receivable_code", "1-220"), ("revenue_basis", "order_amount"),
                        ("platform_warehouse_name", "Outfit Boutique"),
                        ("platform_shop_id", "7495123456789")):
            check(f"T3.2 {f} tersimpan", acc.get(f) == want, f"{acc.get(f)!r} (harap {want!r})")
        if pic:
            check("T3.3 PIC tersimpan sejak pembuatan",
                  acc.get("pic_user_id") == pic["id"] and bool(acc.get("pic_user_name")),
                  f"pic_user_name={acc.get('pic_user_name')!r}")
        # T4 — auto COA subledger
        ar_code = acc.get("ar_account_code")
        check("T4.1 respons create sudah memuat ar_account_code (akun COA otomatis)",
              bool(ar_code), f"ar_account_code={ar_code!r}")
        db_doc = (db_get_account(acc["id"])) or {}
        check("T4.2 dokumen toko di DB menyimpan ar_account_code",
              bool(db_doc.get("ar_account_code")), str(db_doc.get("ar_account_code")))
        coa_doc = (db_get_coa(db_doc.get("ar_account_code") or "__none__")) or {}
        check("T4.3 akun COA subledger BENAR-BENAR dibuat di bagan akun",
              bool(coa_doc.get("code")), f"{coa_doc.get('code')} · {coa_doc.get('name')}")
        check("T4.4 subledger anak dari 1-220 (Piutang Platform Online Shop)",
              coa_doc.get("parent_code") == "1-220", str(coa_doc.get("parent_code")))
        check("T4.5 subledger tertaut ke id toko (flags.subledger_entity_id)",
              (coa_doc.get("flags") or {}).get("subledger_entity_id") == acc["id"],
              str((coa_doc.get("flags") or {}).get("subledger_entity_id")))

    # ── T5 create tanpa COA ⇒ dapat alamat jurnal penampung ───────────────────
    print("\n[T5] POST tanpa COA ⇒ tetap punya alamat jurnal (akun penampung platform)")
    r = P("/api/marketing/accounts", {
        "account_code": f"POC-MIN-{sfx}",
        "account_name": f"POC Toko Minimal {sfx}",
        "platform": "shopee",
    })
    acc2 = (r.json() or {}).get("account") or {} if r.status_code == 200 else {}
    if acc2.get("id"):
        CREATED_IDS.append(acc2["id"])
    check("T5.1 POST minimal 200", r.status_code == 200, f"status={r.status_code}")
    check("T5.2 pendapatan default = penampung Shopee 4-114",
          acc2.get("coa_revenue_code") == "4-114", str(acc2.get("coa_revenue_code")))
    check("T5.3 kas default terisi", bool(acc2.get("coa_cash_code")), str(acc2.get("coa_cash_code")))
    check("T5.4 piutang default 1-220", acc2.get("coa_receivable_code") == "1-220",
          str(acc2.get("coa_receivable_code")))
    check("T5.5 basis omzet default produk_setelah_diskon",
          acc2.get("revenue_basis") == "produk_setelah_diskon", str(acc2.get("revenue_basis")))
    check("T5.6 akun COA otomatis juga terbentuk untuk toko minimal",
          bool(acc2.get("ar_account_code")), str(acc2.get("ar_account_code")))

    # ── T6 COA palsu ditolak ──────────────────────────────────────────────────
    print("\n[T6] Validasi: kode COA tidak ada / salah peran ⇒ 400")
    r = P("/api/marketing/accounts", {
        "account_code": f"POC-BAD-{sfx}", "account_name": "POC COA palsu",
        "platform": "shopee", "coa_revenue_code": "9-999",
    })
    det = (r.json() or {}).get("detail", "") if r.status_code != 200 else ""
    check("T6.1 POST COA palsu ⇒ 400", r.status_code == 400, f"status={r.status_code}")
    check("T6.2 pesan galat menyebut kode & tempat memperbaiki",
          "9-999" in str(det), str(det)[:160])
    if r.status_code == 200:
        bad = ((r.json() or {}).get("account") or {}).get("id")
        if bad:
            CREATED_IDS.append(bad)
    # akun GRUP/beban tidak boleh dipakai sebagai rekening pencairan
    r = P("/api/marketing/accounts", {
        "account_code": f"POC-GRP-{sfx}", "account_name": "POC akun grup",
        "platform": "shopee", "coa_cash_code": "9-000",
    })
    det = (r.json() or {}).get("detail", "") if r.status_code != 200 else ""
    check("T6.3 POST akun grup/beban sebagai kas ⇒ 400", r.status_code == 400,
          f"status={r.status_code}")
    check("T6.4 pesan galat menjelaskan sebabnya (grup / bukan kas-bank)",
          any(k in str(det).lower() for k in ("grup", "kas/bank")), str(det)[:170])
    if r.status_code == 200:
        bad = ((r.json() or {}).get("account") or {}).get("id")
        if bad:
            CREATED_IDS.append(bad)
    # akun pendapatan kontra (potongan platform) tidak boleh jadi akun pendapatan toko
    r = P("/api/marketing/accounts", {
        "account_code": f"POC-CTR-{sfx}", "account_name": "POC akun kontra",
        "platform": "shopee", "coa_revenue_code": "4-141",
    })
    check("T6.5 POST akun kontra (4-141 Potongan Platform) sebagai pendapatan ⇒ 400",
          r.status_code == 400, f"status={r.status_code}")
    if r.status_code == 200:
        bad = ((r.json() or {}).get("account") or {}).get("id")
        if bad:
            CREATED_IDS.append(bad)

    # ── T7 basis omzet ngawur ─────────────────────────────────────────────────
    print("\n[T7] Validasi: revenue_basis ngawur ⇒ 400")
    r = P("/api/marketing/accounts", {
        "account_code": f"POC-BASIS-{sfx}", "account_name": "POC basis ngawur",
        "platform": "shopee", "revenue_basis": "asal_asalan",
    })
    check("T7.1 POST basis ngawur ⇒ 400", r.status_code == 400, f"status={r.status_code}")
    if r.status_code == 200:
        bad = ((r.json() or {}).get("account") or {}).get("id")
        if bad:
            CREATED_IDS.append(bad)

    # ── T8 PUT semua field baru ───────────────────────────────────────────────
    print("\n[T8] PUT /api/marketing/accounts/{id} — ubah semua field baru")
    if CREATED_IDS:
        target = CREATED_IDS[0]
        upd = {
            "account_name": "POC Toko Lengkap (diedit)",
            "username": "poc_edited",
            "group": "reseller",
            "status": "suspended",
            "has_api_integration": False,
            "coa_revenue_code": "4-124",
            "coa_cash_code": "1-131",
            "coa_receivable_code": "1-230",
            "revenue_basis": "produk_setelah_diskon",
            "platform_warehouse_name": "Gudang Utama Sragen",
            "platform_shop_id": "8891234567",
            "needs_owner_review": False,
        }
        if pic:
            upd["pic_user_id"] = pic["id"]
        r = U(f"/api/marketing/accounts/{target}", upd)
        check("T8.1 PUT 200", r.status_code == 200, f"status={r.status_code} {str(r.text)[:160]}")
        after = G(f"/api/marketing/accounts/{target}")
        a = after.json() if after.status_code == 200 else {}
        for f, want in (("coa_revenue_code", "4-124"), ("coa_cash_code", "1-131"),
                        ("coa_receivable_code", "1-230"),
                        ("revenue_basis", "produk_setelah_diskon"),
                        ("platform_warehouse_name", "Gudang Utama Sragen"),
                        ("platform_shop_id", "8891234567"), ("status", "suspended")):
            check(f"T8.2 {f} ter-update", a.get(f) == want, f"{a.get(f)!r} (harap {want!r})")
        check("T8.3 needs_owner_review bisa ditutup dari UI",
              a.get("needs_owner_review") is False, str(a.get("needs_owner_review")))
        if pic:
            check("T8.4 PIC ter-update + nama ter-denormalisasi",
                  a.get("pic_user_id") == pic["id"] and bool(a.get("pic_user_name")),
                  str(a.get("pic_user_name")))
        r = U(f"/api/marketing/accounts/{target}", {"coa_cash_code": "9-000"})
        check("T8.5 PUT akun grup/beban sebagai kas ⇒ 400", r.status_code == 400,
              f"status={r.status_code}")
        r = U(f"/api/marketing/accounts/{target}", {"coa_revenue_code": "9-999"})
        check("T8.6 PUT COA palsu ⇒ 400", r.status_code == 400, f"status={r.status_code}")

        # ── T9 archive ────────────────────────────────────────────────────────
        print("\n[T9] DELETE (archive) ⇒ status inactive, dokumen tetap ada")
        r = D(f"/api/marketing/accounts/{target}")
        check("T9.1 DELETE 200", r.status_code == 200, f"status={r.status_code}")
        a = (G(f"/api/marketing/accounts/{target}").json() or {})
        check("T9.2 status jadi inactive", a.get("status") == "inactive", str(a.get("status")))

    # ── T10 backfill subledger untuk toko hasil seed ──────────────────────────
    print("\n[T10] Toko hasil seed (bypass API) juga punya akun COA piutang channel")
    r = G("/api/marketing/accounts")
    accounts = r.json() if r.status_code == 200 else []
    seeded = [a for a in accounts if a.get("seeded_by") == "F0.7"]
    check("T10.1 9 toko nyata hasil seed terbaca", len(seeded) >= 9, f"{len(seeded)} toko")
    no_ar = [a["account_code"] for a in seeded if not a.get("ar_account_code")]
    check("T10.2 semua toko seed punya ar_account_code", not no_ar, f"tanpa ar={no_ar}")
    bad_ar = []
    for a in seeded:
        code = a.get("ar_account_code")
        if code and not (db_get_coa(code)):
            bad_ar.append(f"{a['account_code']}→{code}")
    check("T10.3 setiap ar_account_code ADA di bagan akun", not bad_ar, f"menggantung={bad_ar}")

    # ── bersih-bersih data uji ────────────────────────────────────────────────
    if CREATED_IDS:
        db_cleanup(CREATED_IDS)
        print(f"\n  (bersih-bersih: {len(CREATED_IDS)} akun uji + subledger-nya dihapus)")

    # ── ringkas ───────────────────────────────────────────────────────────────
    passed = sum(1 for _, p, _ in RESULTS if p)
    failed = [(n, d) for n, p, d in RESULTS if not p]
    print("\n" + "=" * 86)
    print(f"RINGKAS: {passed}/{len(RESULTS)} PASS")
    if failed:
        print("GAGAL:")
        for n, d in failed:
            print(f"  · {n} — {d}")
    print("=" * 86)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
