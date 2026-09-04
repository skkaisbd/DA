#!/usr/bin/env python3
"""
Patch seed demo marketing supaya SELALU berlingkup toko (F14).

Dijalankan sekali; hasilnya berupa perubahan berkas sumber (bukan runtime).
Alasan tiap perubahan ditulis sebagai komentar di berkas yang diubah.
"""
import re
import sys

R = "/app/backend/routes"
changes = []


def patch(path, old, new, label, count=1):
    p = f"{R}/{path}"
    src = open(p, encoding="utf-8").read()
    if new.strip() and new.split("\n")[0].strip() in src and old not in src:
        changes.append(f"SKIP (sudah ada) {path} :: {label}")
        return
    if old not in src:
        changes.append(f"!! GAGAL (pola tak ditemukan) {path} :: {label}")
        return
    src = src.replace(old, new, count)
    open(p, "w", encoding="utf-8").write(src)
    changes.append(f"OK   {path} :: {label}")


SCOPE_IMPORT = "from core import marketing_account_scope as _scope\n"

# ═════════════════════════════════════════════════════════════════════════════
# 1. ORDERS — daftar toko hardcoded (teks) → master akun
# ═════════════════════════════════════════════════════════════════════════════
patch("marketing_orders_routes.py",
      '''    platforms = [
        {"platform": "shopee",    "account_name": "DA Official Shopee",   "prefix": "SHP-2026050"},
        {"platform": "tiktok",    "account_name": "Daluna TikTok Shop",   "prefix": "TT-260500-"},
        {"platform": "shopee",    "account_name": "DA Shopee Premium",    "prefix": "SHP-2026051"},
    ]''',
      '''    # F14 — dulu daftar toko ditulis di sini sebagai TEKS tanpa `account_id`,
    # sehingga 60/60 order demo tidak berlingkup toko dan filter per akun di
    # layar Order Terpadu selalu mengembalikan kosong. Sekarang tokonya diambil
    # dari master akun (dibuat lebih dulu bila master masih kosong).
    from core import marketing_account_scope as _scope
    _accounts = await _scope.seed_account_pool(db)
    platforms = [
        {"account": a,
         "platform": a.get("platform", "shopee"),
         "account_name": a.get("account_name", ""),
         "prefix": f"{(a.get('account_code') or 'ORD')[:6].upper()}-"}
        for a in _accounts
    ]''',
      "toko seed order dari master akun")

patch("marketing_orders_routes.py",
      '''            "order_id":       f"{plat['prefix']}{i+1:03d}",
            "platform":       plat["platform"],
            "account_name":   plat["account_name"],''',
      '''            "order_id":       f"{plat['prefix']}{i+1:03d}",
            "platform":       plat["platform"],
            "account_id":     plat["account"]["id"],
            "account_name":   plat["account_name"],''',
      "order demo menulis account_id")

# ═════════════════════════════════════════════════════════════════════════════
# 2. ADS — tidak ada toko sama sekali
# ═════════════════════════════════════════════════════════════════════════════
patch("marketing_ads_routes.py",
      '''    platforms = ["meta", "tiktok", "google"]''',
      '''    # F14 — iklan demo dulu TIDAK punya `account_id` sama sekali (25/25 kosong),
    # jadi biaya iklan tidak bisa dibandingkan dengan omzet toko mana pun.
    # `platform` = platform TOKO (konsisten dengan modul lain); saluran iklannya
    # disimpan terpisah di `ad_platform` karena Shopee Ads ≠ Meta Ads.
    from core import marketing_account_scope as _scope
    _accounts = await _scope.seed_account_pool(db)
    ad_platforms = ["shopee_ads", "tiktok_ads", "meta_ads", "google_ads"]''',
      "ads seed ambil master akun")

patch("marketing_ads_routes.py",
      '''    for i in range(25):  # 25 campaign snapshots
        platform = random.choice(platforms)
        campaign = random.choice(campaign_names)''',
      '''    for i in range(25):  # 25 campaign snapshots
        account = random.choice(_accounts)
        platform = account.get("platform", "shopee")
        ad_platform = random.choice(ad_platforms)
        campaign = random.choice(campaign_names)''',
      "ads seed pilih akun")

patch("marketing_ads_routes.py",
      '''            "id": str(uuid.uuid4()),
            "platform": platform,
            "campaign_name": f"{campaign} - {platform.upper()}",''',
      '''            "id": str(uuid.uuid4()),
            "platform": platform,
            "ad_platform": ad_platform,
            "account_id": account["id"],
            "account_name": account.get("account_name", ""),
            "campaign_name": f"{campaign} - {ad_platform.upper()}",''',
      "ads demo menulis account_id")

# angka iklan demo tidak masuk akal (impresi ratusan juta, ROAS ribuan)
patch("marketing_ads_routes.py",
      '''        spend = random.uniform(500000, 5000000)
        impressions = int(spend * random.uniform(50, 200))  # impressions per Rp
        clicks = int(impressions * random.uniform(0.01, 0.05))  # CTR 1-5%
        conversions = int(clicks * random.uniform(0.02, 0.10))  # CVR 2-10%
        revenue = conversions * random.uniform(50000, 200000)  # avg order value''',
      '''        # F14 — angka demo lama tidak masuk akal (impresi ratusan juta, ROAS ribuan
        # kali) sehingga layar ROAS/CPA tidak bisa dipakai menilai apa pun. Sekarang
        # diturunkan dari CPM yang wajar untuk pasar Indonesia.
        spend = random.uniform(300000, 3000000)
        cpm = random.uniform(8000, 25000)                  # biaya per 1.000 impresi
        impressions = max(1, int(spend / cpm * 1000))
        clicks = int(impressions * random.uniform(0.008, 0.035))   # CTR 0,8-3,5%
        conversions = int(clicks * random.uniform(0.01, 0.06))     # CVR 1-6%
        revenue = conversions * random.uniform(70000, 220000)      # AOV''',
      "angka iklan demo dibuat wajar")

# ═════════════════════════════════════════════════════════════════════════════
# 3. LIVE SESSIONS — tidak ada toko & host nama teks
# ═════════════════════════════════════════════════════════════════════════════
patch("marketing_live_sessions_routes.py",
      '''    platforms = ["shopee", "tiktok", "instagram"]
    hosts = ["Bella Fashion", "Rini Style", "Dina Trendy", "Mega Boutique"]''',
      '''    # F14 — sesi live demo dulu hanya menyimpan `host_name` sebagai TEKS dan
    # tidak punya `account_id`/`host_id` (18/18 kosong). Akibatnya omzet live tidak
    # bisa dipertanggungjawabkan ke toko mana pun, dan jam kerja host tidak bisa
    # dihubungkan ke sesinya. Sekarang keduanya diambil dari master.
    from core import marketing_account_scope as _scope
    _accounts = await _scope.seed_account_pool(db)
    _hosts = await db.marketing_livehosts.find(
        {}, {"_id": 0, "id": 1, "name": 1, "assigned_account_ids": 1}).to_list(100)''',
      "live seed ambil master akun+host")

patch("marketing_live_sessions_routes.py",
      '''    for i in range(18):  # 18 live sessions
        platform = random.choice(platforms)
        host = random.choice(hosts)''',
      '''    for i in range(18):  # 18 live sessions
        account = random.choice(_accounts)
        platform = account.get("platform", "shopee")
        # host yang di-assign ke akun ini; kalau master host masih kosong, sesi
        # tetap dibuat TANPA host (jujur) — bukan diberi nama karangan.
        _cand = [h for h in _hosts
                 if account["id"] in (h.get("assigned_account_ids") or [])] or _hosts
        host_doc = random.choice(_cand) if _cand else None
        host = (host_doc or {}).get("name", "")''',
      "live seed pilih akun+host")

patch("marketing_live_sessions_routes.py",
      '''            "id": str(uuid.uuid4()),
            "platform": platform,
            "host_name": host,''',
      '''            "id": str(uuid.uuid4()),
            "platform": platform,
            "account_id": account["id"],
            "account_name": account.get("account_name", ""),
            "host_id": (host_doc or {}).get("id"),
            "host_name": host,''',
      "live demo menulis account_id+host_id")

# ═════════════════════════════════════════════════════════════════════════════
# 4. CONTENT CALENDAR
# ═════════════════════════════════════════════════════════════════════════════
patch("marketing_content_calendar_routes.py",
      '''    accounts = [
        {"account_name": "DA Official Shopee",  "platform": "shopee"},
        {"account_name": "Daluna TikTok Shop",  "platform": "tiktok"},
        {"account_name": "DA Instagram",         "platform": "instagram"},
        {"account_name": "DA Tokopedia",          "platform": "tokopedia"},
    ]''',
      '''    # F14 — model `ContentEntryIn` SUDAH punya `account_id`, tapi seed demo ini
    # menulis nama toko sebagai teks saja ⇒ 30/30 baris demo tak berlingkup toko.
    from core import marketing_account_scope as _scope
    accounts = await _scope.seed_account_pool(db)''',
      "kalender konten pakai master akun")

patch("marketing_content_calendar_routes.py",
      '''            "id":           str(uuid.uuid4()),
            "account_name": acc["account_name"],
            "platform":     acc["platform"],''',
      '''            "id":           str(uuid.uuid4()),
            "account_id":   acc["id"],
            "account_name": acc.get("account_name", ""),
            "platform":     acc.get("platform", "shopee"),''',
      "kalender konten menulis account_id")

# ═════════════════════════════════════════════════════════════════════════════
# 5. DISCOUNTS
# ═════════════════════════════════════════════════════════════════════════════
patch("marketing_discounts_routes.py",
      '''    accounts = [
        {"account_name": "DA Official Shopee",  "platform": "shopee"},
        {"account_name": "Daluna TikTok Shop",  "platform": "tiktok"},
        {"account_name": "DA Tokopedia",          "platform": "tokopedia"},
    ]''',
      '''    # F14 — sama seperti kalender konten: modelnya sudah benar, seed-nya belum.
    from core import marketing_account_scope as _scope
    accounts = await _scope.seed_account_pool(db)''',
      "diskon pakai master akun")

patch("marketing_discounts_routes.py",
      '''            "id":           str(uuid.uuid4()),
            "account_name": acc["account_name"],
            "platform":     acc["platform"],''',
      '''            "id":           str(uuid.uuid4()),
            "account_id":   acc["id"],
            "account_name": acc.get("account_name", ""),
            "platform":     acc.get("platform", "shopee"),''',
      "diskon menulis account_id")

# ═════════════════════════════════════════════════════════════════════════════
# 6. PRODUCT LAUNCHES
# ═════════════════════════════════════════════════════════════════════════════
patch("marketing_product_launches_routes.py",
      '''    all_platforms = ["shopee", "tiktok", "tokopedia"]''',
      '''    # F14 — peluncuran demo dulu hanya menyimpan daftar nama platform, tanpa
    # `account_id` maupun `target_account_ids` yang terisi ⇒ 8/8 tak berlingkup toko.
    from core import marketing_account_scope as _scope
    _accounts = await _scope.seed_account_pool(db)
    all_platforms = sorted({a.get("platform", "shopee") for a in _accounts})''',
      "peluncuran pakai master akun")

patch("marketing_product_launches_routes.py",
      '''        entries.append({
            "id":           str(uuid.uuid4()),
            "product_name": prod["name"],''',
      '''        _acc = _accounts[i % len(_accounts)]
        _targets = [a["id"] for a in _accounts if a.get("platform") in plats] or [_acc["id"]]
        entries.append({
            "id":           str(uuid.uuid4()),
            "account_id":   _acc["id"],
            "account_name": _acc.get("account_name", ""),
            "target_account_ids": _targets,
            "product_name": prod["name"],''',
      "peluncuran menulis account_id")

# ═════════════════════════════════════════════════════════════════════════════
# 7. SAMPLES — tidak ada toko & kreator; username teks bebas
# ═════════════════════════════════════════════════════════════════════════════
patch("marketing_samples_routes.py",
      '''    usernames = [
        "@ayufashion", "@budihijab", "@citramuslimah", "@dinarmodest",
        "@evisyari", "@farahbusana", "@ginaootd", "@hanastyle"
    ]''',
      '''    # F14 — sample demo dulu memakai `username` teks bebas dan TIDAK punya
    # `account_id`/`creator_id` (35/35 kosong) ⇒ biaya sample tidak bisa dibebankan
    # ke toko mana pun, dan performa kreator tidak bisa dihitung.
    from core import marketing_account_scope as _scope
    _accounts = await _scope.seed_account_pool(db)
    _creators = await db.marketing_kol_creators.find(
        {}, {"_id": 0, "id": 1, "name": 1, "creator_code": 1, "platforms": 1,
             "assigned_account_ids": 1}).to_list(100)

    def _creator_handle(c):
        p = (c or {}).get("platforms") or {}
        return p.get("tiktok") or p.get("instagram") or (c or {}).get("creator_code") \\
            or (c or {}).get("name") or ""

    usernames = [_creator_handle(c) for c in _creators] or [
        "@ayufashion", "@budihijab", "@citramuslimah", "@dinarmodest",
        "@evisyari", "@farahbusana", "@ginaootd", "@hanastyle"
    ]''',
      "sample pakai master kreator")

patch("marketing_samples_routes.py",
      '''        entries.append({
            "id": str(uuid.uuid4()),
            "date": sample_date.date().isoformat(),
            "username": random.choice(usernames),''',
      '''        _acc = random.choice(_accounts)
        _cand = [c for c in _creators
                 if _acc["id"] in (c.get("assigned_account_ids") or [])] or _creators
        _cr = random.choice(_cand) if _cand else None
        entries.append({
            "id": str(uuid.uuid4()),
            "date": sample_date.date().isoformat(),
            "account_id": _acc["id"],
            "account_name": _acc.get("account_name", ""),
            "creator_id": (_cr or {}).get("id"),
            "username": (_creator_handle(_cr) if _cr else random.choice(usernames)),''',
      "sample menulis account_id+creator_id")

# platform sample harus ikut toko, bukan diacak sendiri
patch("marketing_samples_routes.py",
      '''            "platform": "tiktok" if sample_type == "live" else random.choice(["tiktok", "instagram"]),''',
      '''            "platform": _acc.get("platform", "tiktok"),''',
      "platform sample ikut toko")

print("\n".join(changes))
sys.exit(1 if any(c.startswith("!!") for c in changes) else 0)
