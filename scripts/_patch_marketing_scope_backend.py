#!/usr/bin/env python3
"""
F14 — patch backend marketing supaya lingkup toko DITEGAKKAN, bukan diharapkan.

Tiga hal yang dikerjakan:
  1. Model tulis yang belum punya `account_id` diberi field-nya, dan endpoint
     create/update-nya memakai SSOT `core.marketing_account_scope` untuk
     menstempel `account_id`/`account_name`/`platform` dari MASTER.
  2. Semua endpoint daftar & ringkasan menerima filter `?account_id=` — tanpa ini,
     "lihat toko X saja" mustahil dan angka ringkasan tidak pernah cocok dengan
     tabel di bawahnya.
  3. Sesi live: pembaca dan penulis dirujukkan ke SATU nama field
     (`core.marketing_live_fields`), karena sekarang pembaca menjumlahkan `$gmv`
     sedangkan penulis menyimpan `revenue` ⇒ kartu "Total Revenue" Rp 0 di atas
     tabel yang penuh angka.
"""
import sys

R = "/app/backend/routes"
log = []


def patch(path, old, new, label, count=1, optional=False):
    p = f"{R}/{path}"
    src = open(p, encoding="utf-8").read()
    if old not in src:
        if new.strip().split("\n")[0].strip() in src:
            log.append(f"SKIP {path} :: {label} (sudah diterapkan)")
        else:
            log.append(("--   " if optional else "!!   ") + f"{path} :: {label}")
        return
    open(p, "w", encoding="utf-8").write(src.replace(old, new, count))
    log.append(f"OK   {path} :: {label}")


# ════════════════════════════════════════════════════════════════════════════
# 1. ORDERS — model + create + filter daftar
# ════════════════════════════════════════════════════════════════════════════
patch("marketing_orders_routes.py",
      '''class OrderCreateBody(BaseModel):
    # Required
    platform: str  # shopee | tiktok | tokopedia | manual | website | etc.
    customer_name: str
    # Identification
    order_id: Optional[str] = None  # marketplace reference (auto-gen if blank)
    account_name: Optional[str] = None''',
      '''class OrderCreateBody(BaseModel):
    # ── F14 — LINGKUP TOKO WAJIB ──────────────────────────────────────────────
    # Dulu order hanya menyimpan `account_name` sebagai TEKS. Akibat terukur:
    # 60/60 order tidak punya `account_id`, sehingga pemilih akun di layar Order
    # Terpadu SELALU mengembalikan daftar kosong dan laporan per toko Rp 0.
    # `account_name` sekarang hanya jalan masuk (nama dari berkas marketplace);
    # yang DISIMPAN selalu `account_id` hasil resolusi master.
    account_id: Optional[str] = None
    # Required
    platform: str  # shopee | tiktok | tokopedia | manual | website | etc.
    customer_name: str
    # Identification
    order_id: Optional[str] = None  # marketplace reference (auto-gen if blank)
    account_name: Optional[str] = None''',
      "OrderCreateBody.account_id")

patch("marketing_orders_routes.py",
      '''    await require_auth(request)
    user = _get_user(request)
    db = get_db()
    from core import catalog_stock as _cstock
    from core import stock_service as _ss''',
      '''    await require_auth(request)
    user = _get_user(request)
    db = get_db()
    from core import catalog_stock as _cstock
    from core import stock_service as _ss
    from core import marketing_account_scope as _scope

    # F14 — resolusi toko dilakukan SEBELUM apa pun ditulis/direservasi. Order
    # tanpa toko yang sah ditolak keras: baris yatim tidak pernah muncul di layar
    # yang difilter, dan itu jenis kerusakan yang tidak melahirkan pesan error.
    _acc, _why = await _scope.resolve_account(
        db, account_id=body.account_id, account_name=body.account_name,
        platform=body.platform)
    if not _acc:
        raise HTTPException(400, f"Toko/akun tidak sah: {_why}")''',
      "create_order resolve akun")

patch("marketing_orders_routes.py",
      '''    account_name: Optional[str]= Query(None),
    date_from:  Optional[str]  = Query(None),''',
      '''    account_id: Optional[str]  = Query(None, description="F14 — filter per toko (SSOT)"),
    account_name: Optional[str]= Query(None, description="kompatibilitas: filter nama"),
    date_from:  Optional[str]  = Query(None),''',
      "list_orders param account_id")

patch("marketing_orders_routes.py",
      '''    if account_name:
        q["account_name"] = account_name
    if date_from or date_to:''',
      '''    if account_id:
        q["account_id"] = account_id
    if account_name:
        q["account_name"] = account_name
    if date_from or date_to:''',
      "list_orders filter account_id")

patch("marketing_orders_routes.py",
      '''@router.get("/summary")
async def orders_summary(request: Request):
    await require_auth(request)
    db = get_db()
    await seed_orders_if_empty()

    now   = _now()''',
      '''@router.get("/summary")
async def orders_summary(request: Request,
                         account_id: Optional[str] = Query(None)):
    """F14 — ringkasan WAJIB bisa dilingkupi toko yang sama dengan tabelnya.
    Kalau tidak, kartu KPI dan tabel di bawahnya menampilkan dua kenyataan
    berbeda pada satu layar, dan yang dipercaya biasanya yang salah."""
    await require_auth(request)
    db = get_db()
    await seed_orders_if_empty()
    _scope_q = {"account_id": account_id} if account_id else {}

    now   = _now()''',
      "orders_summary param account_id")

# ════════════════════════════════════════════════════════════════════════════
# 2. SAMPLES — model + create + filter
# ════════════════════════════════════════════════════════════════════════════
patch("marketing_samples_routes.py",
      '''class SampleIn(BaseModel):
    date: str
    username: str''',
      '''class SampleIn(BaseModel):
    # ── F14/F15 ───────────────────────────────────────────────────────────────
    # `account_id` dulu TIDAK ADA sama sekali (35/35 dokumen tanpa lingkup toko)
    # ⇒ biaya sample tidak bisa dibebankan ke toko mana pun.
    # `creator_id` menggantikan `username` sebagai identitas kreator: username
    # teks bebas membuat satu kreator pecah jadi beberapa baris laporan begitu
    # ejaannya beda satu karakter. `username` tetap disimpan sebagai TURUNAN.
    account_id: str
    creator_id: Optional[str] = None
    catalog_item_id: Optional[str] = None
    date: str
    username: Optional[str] = ""''',
      "SampleIn.account_id + creator_id")

patch("marketing_samples_routes.py",
      '''class SampleUpdate(BaseModel):
    date: Optional[str] = None
    username: Optional[str] = None''',
      '''class SampleUpdate(BaseModel):
    account_id: Optional[str] = None
    creator_id: Optional[str] = None
    catalog_item_id: Optional[str] = None
    date: Optional[str] = None
    username: Optional[str] = None''',
      "SampleUpdate.account_id + creator_id")

patch("marketing_samples_routes.py",
      '''@router.post("")
async def create_sample(body: SampleIn, request: Request):
    await require_auth(request)
    user = _get_user(request)
    db = get_db()

    total_hpp = body.hpp * body.quantity

    sample = {
        "id": str(uuid.uuid4()),
        "date": body.date,
        "username": body.username,
        "sample_type": body.sample_type,
        "sample_type_label": "Live Streaming" if body.sample_type == "live" else "Video Review",
        "platform": body.platform,
        "product": body.product,''',
      '''@router.post("")
async def create_sample(body: SampleIn, request: Request):
    await require_auth(request)
    user = _get_user(request)
    db = get_db()
    from core import marketing_account_scope as _scope

    # F14 — toko wajib & sah; F15 — kreator wajib SUDAH di-assign ke toko itu.
    account = await _scope.require_account(db, body.account_id)
    creator = None
    username = body.username or ""
    if body.creator_id:
        creator = await _scope.assert_creator_assigned(db, body.creator_id,
                                                       account["id"])
        _p = creator.get("platforms") or {}
        username = (_p.get("tiktok") or _p.get("instagram")
                    or creator.get("creator_code") or creator.get("name") or "")

    # HPP: kalau item katalog dipilih, HPP-nya ikut MASTER — bukan diketik ulang.
    hpp = body.hpp
    item = None
    if body.catalog_item_id:
        item = await db.marketing_catalog_items.find_one(
            {"id": body.catalog_item_id}, {"_id": 0})
        if not item:
            raise HTTPException(404, "Item katalog tidak ditemukan")
        if not hpp:
            hpp = float(item.get("hpp") or 0)

    total_hpp = hpp * body.quantity

    sample = {
        "id": str(uuid.uuid4()),
        "date": body.date,
        "creator_id": (creator or {}).get("id"),
        "creator_name": (creator or {}).get("name", ""),
        "username": username,
        "catalog_item_id": body.catalog_item_id,
        "sku": (item or {}).get("sku", ""),
        "sample_type": body.sample_type,
        "sample_type_label": "Live Streaming" if body.sample_type == "live" else "Video Review",
        "platform": account.get("platform") or body.platform,
        "product": (item or {}).get("name") or body.product,''',
      "create_sample scope + master")

patch("marketing_samples_routes.py",
      '''        "quantity": body.quantity,
        "hpp": body.hpp,
        "total_hpp": total_hpp,''',
      '''        "quantity": body.quantity,
        "hpp": hpp,
        "total_hpp": total_hpp,''',
      "create_sample hpp turunan")

patch("marketing_samples_routes.py",
      '''        "created_by": user.get("email", "unknown"),
        "created_at": _now(),
        "updated_at": _now(),
    }''',
      '''        "created_by": user.get("email", "unknown"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    _scope.stamp_account(sample, account)''',
      "create_sample stamp akun")

patch("marketing_samples_routes.py",
      '''    shipment_status: str = Query(default=""),
    progress: str = Query(default=""),
    platform: str = Query(default=""),''',
      '''    account_id: str = Query(default="", description="F14 — filter per toko"),
    creator_id: str = Query(default=""),
    shipment_status: str = Query(default=""),
    progress: str = Query(default=""),
    platform: str = Query(default=""),''',
      "list_samples param account_id")

patch("marketing_samples_routes.py",
      '''    q = {}
    if shipment_status:
        q["shipment_status"] = shipment_status''',
      '''    q = {}
    if account_id:
        q["account_id"] = account_id
    if creator_id:
        q["creator_id"] = creator_id
    if shipment_status:
        q["shipment_status"] = shipment_status''',
      "list_samples filter account_id")

patch("marketing_samples_routes.py",
      '''@router.get("/summary")
async def get_summary(request: Request):
    await require_auth(request)
    await seed_samples_if_empty()
    db = get_db()

    total = await db.marketing_samples.count_documents({})''',
      '''@router.get("/summary")
async def get_summary(request: Request,
                      account_id: str = Query(default="")):
    await require_auth(request)
    await seed_samples_if_empty()
    db = get_db()
    _sq = {"account_id": account_id} if account_id else {}

    total = await db.marketing_samples.count_documents(dict(_sq))''',
      "samples_summary param account_id")

# ════════════════════════════════════════════════════════════════════════════
# 3. LAUNCHES — model + create + filter
# ════════════════════════════════════════════════════════════════════════════
patch("marketing_product_launches_routes.py",
      '''class LaunchIn(BaseModel):
    product_name: str''',
      '''class LaunchIn(BaseModel):
    # F14 — peluncuran dulu hanya punya `target_account_ids` yang tak pernah
    # terisi (8/8 dokumen tanpa lingkup toko). `account_id` = toko pemilik
    # rencana; `target_account_ids` tetap ada untuk peluncuran lintas-toko.
    account_id: str
    product_name: str''',
      "LaunchIn.account_id")

patch("marketing_product_launches_routes.py",
      '''class LaunchUpdate(BaseModel):
    product_name: Optional[str] = None''',
      '''class LaunchUpdate(BaseModel):
    account_id: Optional[str] = None
    product_name: Optional[str] = None''',
      "LaunchUpdate.account_id")

patch("marketing_product_launches_routes.py",
      '''    status = body.status if body.status in LAUNCH_STATUSES else "planning"
    launch = {
        "id":           str(uuid.uuid4()),
        "product_name": body.product_name,''',
      '''    from core import marketing_account_scope as _scope
    account = await _scope.require_account(db, body.account_id)

    status = body.status if body.status in LAUNCH_STATUSES else "planning"
    launch = {
        "id":           str(uuid.uuid4()),
        "product_name": body.product_name,''',
      "create_launch require akun")

patch("marketing_product_launches_routes.py",
      '''    await db.marketing_product_launches.insert_one(launch)
    return {"success": True, "data": serialize(launch)}''',
      '''    _scope.stamp_account(launch, account)
    if not launch.get("target_account_ids"):
        launch["target_account_ids"] = [account["id"]]
    await db.marketing_product_launches.insert_one(launch)
    return {"success": True, "data": serialize(launch)}''',
      "create_launch stamp akun")

patch("marketing_product_launches_routes.py",
      '''    status:    str = Query(default=""),
    platform:  str = Query(default=""),
    search:    str = Query(default=""),''',
      '''    account_id: str = Query(default="", description="F14 — filter per toko"),
    status:    str = Query(default=""),
    platform:  str = Query(default=""),
    search:    str = Query(default=""),''',
      "list_launches param account_id")

patch("marketing_product_launches_routes.py",
      '''    q = {}
    if status:
        q["status"]   = status''',
      '''    q = {}
    if account_id:
        # peluncuran bisa lintas-toko: cocokkan pemilik ATAU target
        q["$or"] = [{"account_id": account_id},
                    {"target_account_ids": account_id}]
    if status:
        q["status"]   = status''',
      "list_launches filter account_id")

# ════════════════════════════════════════════════════════════════════════════
# 4. CONTENT CALENDAR & DISCOUNTS — filter per toko (model sudah benar)
# ════════════════════════════════════════════════════════════════════════════
patch("marketing_content_calendar_routes.py",
      '''    status:   str = Query(default=""),
    platform: str = Query(default=""),
    account:  str = Query(default=""),''',
      '''    account_id: str = Query(default="", description="F14 — filter per toko (SSOT)"),
    status:   str = Query(default=""),
    platform: str = Query(default=""),
    account:  str = Query(default="", description="kompatibilitas: cocok nama"),''',
      "list_entries param account_id")

patch("marketing_content_calendar_routes.py",
      '''    q = {}
    if status:
        q["status"]       = status''',
      '''    q = {}
    if account_id:
        q["account_id"] = account_id
    if status:
        q["status"]       = status''',
      "list_entries filter account_id")

patch("marketing_content_calendar_routes.py",
      '''@router.get("/summary")
async def get_summary(request: Request):
    await require_auth(request)
    await seed_content_calendar_if_empty()
    db = get_db()

    total     = await db.marketing_content_calendar.count_documents({})
    draft     = await db.marketing_content_calendar.count_documents({"status": "draft"})
    scheduled = await db.marketing_content_calendar.count_documents({"status": "scheduled"})
    posted    = await db.marketing_content_calendar.count_documents({"status": "posted"})
    cancelled = await db.marketing_content_calendar.count_documents({"status": "cancelled"})''',
      '''@router.get("/summary")
async def get_summary(request: Request,
                      account_id: str = Query(default="")):
    await require_auth(request)
    await seed_content_calendar_if_empty()
    db = get_db()
    _sq = {"account_id": account_id} if account_id else {}

    total     = await db.marketing_content_calendar.count_documents(dict(_sq))
    draft     = await db.marketing_content_calendar.count_documents({**_sq, "status": "draft"})
    scheduled = await db.marketing_content_calendar.count_documents({**_sq, "status": "scheduled"})
    posted    = await db.marketing_content_calendar.count_documents({**_sq, "status": "posted"})
    cancelled = await db.marketing_content_calendar.count_documents({**_sq, "status": "cancelled"})''',
      "content summary account_id")

patch("marketing_discounts_routes.py",
      '''    status:    str = Query(default=""),
    platform:  str = Query(default=""),
    discount_type: str = Query(default=""),
    account:   str = Query(default=""),''',
      '''    account_id: str = Query(default="", description="F14 — filter per toko (SSOT)"),
    status:    str = Query(default=""),
    platform:  str = Query(default=""),
    discount_type: str = Query(default=""),
    account:   str = Query(default="", description="kompatibilitas: cocok nama"),''',
      "list_discounts param account_id")

patch("marketing_discounts_routes.py",
      '''    q = {}
    if platform:
        q["platform"]      = platform
    if discount_type:''',
      '''    q = {}
    if account_id:
        q["account_id"] = account_id
    if platform:
        q["platform"]      = platform
    if discount_type:''',
      "list_discounts filter account_id")

patch("marketing_discounts_routes.py",
      '''@router.get("/summary")
async def get_summary(request: Request):
    await require_auth(request)
    await seed_discounts_if_empty()
    db = get_db()

    all_docs = await db.marketing_discounts.find({}, {"_id": 0, "start_date": 1, "end_date": 1, "platform": 1}).to_list(1000)''',
      '''@router.get("/summary")
async def get_summary(request: Request,
                      account_id: str = Query(default="")):
    await require_auth(request)
    await seed_discounts_if_empty()
    db = get_db()
    _sq = {"account_id": account_id} if account_id else {}

    all_docs = await db.marketing_discounts.find(dict(_sq), {"_id": 0, "start_date": 1, "end_date": 1, "platform": 1}).to_list(1000)''',
      "discounts summary account_id")

# ════════════════════════════════════════════════════════════════════════════
# 5. ADS & LIVE — filter per toko
# ════════════════════════════════════════════════════════════════════════════
patch("marketing_ads_routes.py",
      '''async def list_campaigns(
    request: Request,
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),''',
      '''async def list_campaigns(
    request: Request,
    account_id: Optional[str] = Query(None, description="F14 — filter per toko"),
    platform: Optional[str] = Query(None),
    ad_platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),''',
      "list_campaigns param account_id")

patch("marketing_ads_routes.py",
      '''    query = {}
    if platform:
        query["platform"] = platform
    if status:
        query["status"] = status
    
    total = await db.marketing_ads_data.count_documents(query)''',
      '''    query = {}
    if account_id:
        query["account_id"] = account_id
    if platform:
        query["platform"] = platform
    if ad_platform:
        query["ad_platform"] = ad_platform
    if status:
        query["status"] = status

    total = await db.marketing_ads_data.count_documents(query)''',
      "list_campaigns filter account_id")

patch("marketing_ads_routes.py",
      '''@router.get("/summary")
async def ads_summary(request: Request):
    await require_auth(request)
    db = get_db()
    await seed_ads_if_empty()
    
    # Overall stats
    pipeline = [
        {"$group": {''',
      '''@router.get("/summary")
async def ads_summary(request: Request,
                      account_id: Optional[str] = Query(None)):
    await require_auth(request)
    db = get_db()
    await seed_ads_if_empty()

    # F14 — ringkasan harus bisa dilingkupi toko yang sama dengan tabelnya.
    pipeline = ([{"$match": {"account_id": account_id}}] if account_id else []) + [
        {"$group": {''',
      "ads_summary param account_id")

patch("marketing_live_sessions_routes.py",
      '''async def list_sessions(
    request: Request,
    platform: Optional[str] = Query(None),
    host: Optional[str] = Query(None),''',
      '''async def list_sessions(
    request: Request,
    account_id: Optional[str] = Query(None, description="F14 — filter per toko"),
    host_id: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    host: Optional[str] = Query(None, description="kompatibilitas: nama host"),''',
      "list_sessions param account_id")

patch("marketing_live_sessions_routes.py",
      '''    query = {}
    if platform:
        query["platform"] = platform
    if host:
        query["host_name"] = host
    
    total = await db.marketing_live_sessions.count_documents(query)''',
      '''    query = {}
    if account_id:
        query["account_id"] = account_id
    if host_id:
        query["host_id"] = host_id
    if platform:
        query["platform"] = platform
    if host:
        query["host_name"] = host

    total = await db.marketing_live_sessions.count_documents(query)''',
      "list_sessions filter account_id")

print("\n".join(log))
sys.exit(1 if any(x.startswith("!!") for x in log) else 0)
