"""core.location_resolver — FASE C: SSOT resolusi lokasi storage (dual-model).

Menyatukan resolusi lokasi penyimpanan stok antara:
  * LEGACY  `rahaza_locations` (kode ZNA-KAIN/ZNA-AKSESORIS/ZNA-FG/ZNA-SAMPLE, dll)
  * KANONIK `wh_*` (building → zone → rack → bin) — target SSOT (Fase B).

Prinsip:
  - **Dual-read**: pembaca/penulis menerima id lokasi LAMA (rahaza_locations) MAUPUN
    BARU (wh_zones / wh_positions) selama masa transisi (sampai Fase F).
  - Peta migrasi tersimpan di koleksi `wh_location_migration_map` (dibuat Fase B via
    `/api/wms/structure/build-canonical-storage`): {rahaza_location_id, rahaza_code,
    wh_zone_id, wh_zone_code, role, ...}.
  - Semua fungsi **graceful**: bila struktur kanonik belum ada → fallback aman
    (mengembalikan None / list legacy) tanpa melempar error.

TIDAK menyentuh agregasi stok (onhand_map dkk. tetap lintas-lokasi = aman untuk
Marketing/BOM/Produksi/Finance). Modul ini murni soal IDENTITAS & TAMPILAN lokasi.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

# Peran storage → daftar kode zona wh_* kandidat (urutan = prioritas match).
# Selaras dgn CANONICAL_STORAGE_ZONES di routes/wms_structure.py.
ROLE_ZONE_CODES = {
    "bahan":     ["ZN-KAIN", "ZN-01"],
    "aksesoris": ["ZN-AKS", "ZN-AKSESORIS"],
    "fg":        ["ZN-FG"],
    "sample":    ["ZN-SAMPLE", "ZN-SMP"],
    # FASE 6: zona KARANTINA QC (barang reject menunggu keputusan). SENGAJA tidak
    # dimasukkan ke STORAGE_RAHAZA_CODES → tidak muncul di dropdown storage normal.
    "karantina": ["ZN-QRT", "ZN-KARANTINA", "ZN-QC"],
}

MIGRATION_MAP = "wh_location_migration_map"

# Kode rahaza_locations yang tergolong STORAGE (boleh jadi target stok gudang).
# Zona PRODUKSI (ZNA-CUTTING/SEWING/QC/PACKING) & gedung konsep (GED-A/B) SENGAJA
# TIDAK termasuk — itu milik model produksi/HR, bukan storage stok.
STORAGE_RAHAZA_CODES = {"ZNA-KAIN", "ZNA-AKSESORIS", "ZNA-FG", "ZNA-SAMPLE"}

# FASE 12 — kode legacy yang BUKAN storage tapi SAH menyimpan baris stok:
#   * zona PRODUKSI  → barang sedang dikerjakan (WIP) di lantai produksi;
#   * zona KARANTINA → barang reject menunggu keputusan QC (sengaja dipisah).
# Baris stok di sini TIDAK boleh dipindahkan otomatis oleh rekonsiliasi.
PRODUCTION_RAHAZA_CODES = {"ZNA-CUTTING", "ZNA-SEWING", "ZNA-QC", "ZNA-PACKING"}
QUARANTINE_RAHAZA_CODES = {"ZNA-KARANTINA"}

# Peran storage yang punya zona tujuan kanonik (dipakai rekonsiliasi lokasi).
STORAGE_ROLES = ("bahan", "aksesoris", "fg", "sample")

# Klasifikasi lokasi (dipakai `core.stock_reconcile` penyakit `unmapped_location`).
KIND_STORAGE = "storage"      # zona penyimpanan resmi → baris stok wajar di sini
KIND_EXEMPT = "exempt"        # produksi/karantina → sah, JANGAN dipindah otomatis
KIND_UNMAPPED = "unmapped"    # tidak ada di peta gudang mana pun → perlu dirapikan


# ─────────────────────────────────────────────────────────────────────────────
# MIGRATION MAP
# ─────────────────────────────────────────────────────────────────────────────
async def get_migration_map(db) -> list:
    """Semua entri peta migrasi aktif (rahaza storage location → wh zone)."""
    return await db[MIGRATION_MAP].find({"active": True}, {"_id": 0}).to_list(500)


async def rahaza_to_wh_map(db) -> dict:
    """{rahaza_location_id: wh_zone_id} — HANYA entri yang punya rahaza_location_id
    terselesaikan. Dipakai skrip migrasi & dual-read tulisan."""
    out: dict = {}
    for e in await get_migration_map(db):
        rid = e.get("rahaza_location_id")
        wid = e.get("wh_zone_id")
        if rid and wid:
            out[rid] = wid
    return out


# ─────────────────────────────────────────────────────────────────────────────
# CANONICAL ZONE RESOLUTION (by role)
# ─────────────────────────────────────────────────────────────────────────────
async def canonical_zone_id_for_role(db, role: str) -> str | None:
    """Kembalikan id `wh_zones` kanonik untuk sebuah peran storage (bahan/aksesoris/fg/sample).

    Strategi:
      1. Lihat peta migrasi (role) → wh_zone_id.
      2. Fallback: cari `wh_zones` dgn kode kandidat (ROLE_ZONE_CODES) di gedung aktif.
    Return None bila struktur kanonik belum ada (caller wajib fallback aman)."""
    role = (role or "").lower()
    # 1) via migration map
    for e in await get_migration_map(db):
        if (e.get("role") or "").lower() == role and e.get("wh_zone_id"):
            z = await db.wh_zones.find_one({"id": e["wh_zone_id"], "active": True}, {"_id": 0, "id": 1})
            if z:
                return z["id"]
    # 2) fallback: by candidate codes
    for code in ROLE_ZONE_CODES.get(role, []):
        z = await db.wh_zones.find_one({"code": code, "active": True}, {"_id": 0, "id": 1})
        if z:
            return z["id"]
    return None


async def to_canonical_location_id(db, location_id: str | None) -> str | None:
    """Dual-read: bila `location_id` adalah rahaza storage location yang ada di peta,
    kembalikan wh_zone_id-nya; selain itu kembalikan apa adanya (sudah kanonik / lokasi
    produksi / pseudo)."""
    if not location_id:
        return location_id
    mp = await rahaza_to_wh_map(db)
    return mp.get(location_id, location_id)


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY RESOLUTION (dual-read tampilan nama lokasi)
# ─────────────────────────────────────────────────────────────────────────────
async def build_display_map(db, ids) -> dict:
    """Resolusi nama untuk sekumpulan location_id lintas skema.
    Return {location_id: {"code": str, "name": str, "source": str}}.

    Sumber dicek berurutan: wh_zones (+gedung) → wh_positions (bin) → wh_buildings →
    rahaza_locations. Id tak dikenal → code=id, name="" (biar UI tak kosong total)."""
    ids = [i for i in {x for x in (ids or []) if x}]
    out: dict = {}
    if not ids:
        return out

    # wh_zones (dengan konteks gedung)
    for z in await db.wh_zones.find({"id": {"$in": ids}}, {"_id": 0}).to_list(1000):
        bc = z.get("building_code") or ""
        out[z["id"]] = {
            "code": z.get("code") or "",
            "name": (f"{bc} · {z.get('name')}" if bc else z.get("name")) or z.get("code") or "",
            "source": "wh_zone",
        }
    # wh_positions (bin)
    rem = [i for i in ids if i not in out]
    if rem:
        for p in await db.wh_positions.find({"id": {"$in": rem}}, {"_id": 0}).to_list(2000):
            out[p["id"]] = {
                "code": p.get("barcode") or p.get("label") or "",
                "name": p.get("label") or p.get("barcode") or "",
                "source": "wh_position",
            }
    # wh_buildings
    rem = [i for i in ids if i not in out]
    if rem:
        for b in await db.wh_buildings.find({"id": {"$in": rem}}, {"_id": 0}).to_list(500):
            out[b["id"]] = {"code": b.get("code") or "", "name": b.get("name") or b.get("code") or "", "source": "wh_building"}
    # rahaza_locations (legacy)
    rem = [i for i in ids if i not in out]
    if rem:
        for l in await db.rahaza_locations.find({"id": {"$in": rem}}, {"_id": 0}).to_list(1000):
            out[l["id"]] = {"code": l.get("code") or "", "name": l.get("name") or l.get("code") or "", "source": "rahaza_location"}
    # unknown/pseudo (DEMO-STAGING, dsb.)
    for i in ids:
        if i not in out:
            out[i] = {"code": i, "name": "", "source": "unknown"}
    return out


# ─────────────────────────────────────────────────────────────────────────────
# UNIFIED STORAGE LOCATION LIST (untuk dropdown/filter)
# ─────────────────────────────────────────────────────────────────────────────
async def list_storage_locations(db) -> list:
    """Daftar lokasi storage terpadu untuk dropdown/filter modul Stok.

    Utamakan zona kanonik `wh_*` (source='wh_zone'); tambahkan lokasi legacy
    `rahaza_locations` storage yang BELUM terpetakan (agar stok lama tetap terjangkau
    sebelum migrasi). Setiap entri: {id, code, name, source, role?}."""
    out: list = []
    seen: set = set()

    # 1) Zona kanonik wh_* (storage) — semua zona aktif di gedung aktif.
    zones = await db.wh_zones.find({"active": True}, {"_id": 0}).sort("code", 1).to_list(500)
    # role lookup dari peta migrasi (by wh_zone_id)
    role_by_zone: dict = {}
    for e in await get_migration_map(db):
        if e.get("wh_zone_id"):
            role_by_zone[e["wh_zone_id"]] = e.get("role")
    for z in zones:
        bc = z.get("building_code") or ""
        out.append({
            "id": z["id"],
            "code": z.get("code") or "",
            "name": (f"{bc} · {z.get('name')}" if bc else z.get("name")) or z.get("code") or "",
            "source": "wh_zone",
            "role": role_by_zone.get(z["id"]),
        })
        seen.add(z["id"])

    # 2) Legacy rahaza STORAGE locations yang BELUM terpetakan ke wh.
    #    Hanya kode storage (STORAGE_RAHAZA_CODES) — zona produksi TIDAK ditampilkan.
    mapped_ids = set((await rahaza_to_wh_map(db)).keys())
    legacy = await db.rahaza_locations.find({"active": True}, {"_id": 0}).sort("code", 1).to_list(500)
    for l in legacy:
        if l["id"] in mapped_ids or l["id"] in seen:
            continue
        if (l.get("code") or "").upper() not in STORAGE_RAHAZA_CODES:
            continue
        out.append({
            "id": l["id"],
            "code": l.get("code") or "",
            "name": l.get("name") or l.get("code") or "",
            "source": "rahaza_location",
            "role": None,
        })
        seen.add(l["id"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# EXISTENCE CHECK (dual-read tulisan)
# ─────────────────────────────────────────────────────────────────────────────
async def location_exists(db, location_id: str | None) -> bool:
    """True bila location_id valid di salah satu skema: rahaza_locations, wh_zones,
    atau wh_positions (bin). Dipakai validasi tulisan (mis. GR/receive) agar menerima
    id lama & baru selama transisi."""
    if not location_id:
        return False
    if await db.rahaza_locations.find_one({"id": location_id}, {"_id": 0, "id": 1}):
        return True
    if await db.wh_zones.find_one({"id": location_id}, {"_id": 0, "id": 1}):
        return True
    if await db.wh_positions.find_one({"id": location_id}, {"_id": 0, "id": 1}):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# FASE 12 — INDEKS KLASIFIKASI LOKASI (SSOT "peta gudang")
# ─────────────────────────────────────────────────────────────────────────────
async def storage_location_index(db) -> dict:
    """Peta identitas SEMUA lokasi yang boleh/biasa menyimpan stok.

    LATAR BELAKANG (temuan nyata, backlog `HANDOFF_NEXT_AGENT.md` #3)
    -----------------------------------------------------------------
    Sebagian baris stok mendarat di lokasi warisan yang **bukan zona penyimpanan**
    (contoh nyata di DB ini: `int-demo-loc-1` / `GDG-UTAMA-DEMO`). Totalnya benar
    dan pengeluaran tetap jalan (BUG-1 FASE 10 sudah memperbaiki pemotongan lintas
    lokasi), TAPI **peta gudang jadi menyesatkan**: layar per-lokasi (Put-Away,
    Opname per-bin, dropdown lokasi) tidak menampilkan stok itu di zona mana pun.

    Fungsi ini menjadi SSOT jawaban: sebuah `location_id` itu
      * `storage`  — zona penyimpanan resmi (kanonik `wh_*` atau legacy storage);
      * `exempt`   — sah tapi bukan storage (lantai produksi / karantina QC) ⇒
                     JANGAN dipindahkan otomatis;
      * `unmapped` — tidak ada di peta gudang mana pun ⇒ perlu dirapikan.

    Return:
        {
          "roles":       {role: location_id}   # zona tujuan kanonik per peran
          "role_source": {role: 'wh_zones'|'rahaza_locations'|''}
          "storage_ids": set[str],
          "exempt_ids":  set[str],
          "info":        {id: {code, name, source, kind}},
        }
    Selalu graceful: bila struktur kanonik `wh_*` belum dibangun, jatuh ke legacy.
    """
    storage_ids: set = set()
    exempt_ids: set = set()
    info: dict = {}
    roles: dict = {}
    role_source: dict = {}

    def _put(loc_id, code, name, source, kind):
        if not loc_id:
            return
        info[loc_id] = {"code": code or "", "name": name or code or "", "source": source, "kind": kind}
        (storage_ids if kind == KIND_STORAGE else exempt_ids).add(loc_id)

    # 1) Zona kanonik wh_* -----------------------------------------------------
    storage_zone_ids: set = set()
    try:
        zones = await db.wh_zones.find({"active": True}, {"_id": 0}).to_list(1000)
    except Exception:
        zones = []
    storage_codes = {c for r in STORAGE_ROLES for c in ROLE_ZONE_CODES.get(r, [])}
    quarantine_codes = set(ROLE_ZONE_CODES.get("karantina", []))
    for z in zones:
        code = (z.get("code") or "").upper()
        bc = z.get("building_code") or ""
        nm = (f"{bc} · {z.get('name')}" if bc else z.get("name")) or code
        if code in storage_codes:
            _put(z["id"], code, nm, "wh_zone", KIND_STORAGE)
            storage_zone_ids.add(z["id"])
        elif code in quarantine_codes:
            _put(z["id"], code, nm, "wh_zone", KIND_EXEMPT)

    # 2) Bin (wh_positions) mewarisi sifat zona induknya ------------------------
    try:
        if zones:
            zone_kind = {z["id"]: info.get(z["id"], {}).get("kind") for z in zones}
            async for p in db.wh_positions.find({}, {"_id": 0}):
                kind = zone_kind.get(p.get("zone_id"))
                if kind:
                    _put(p["id"], p.get("barcode") or p.get("label"), p.get("label"), "wh_position", kind)
    except Exception as e:  # noqa: BLE001 — indeks lokasi tetap berguna tanpa bin,
        # tetapi bin yang hilang membuat lokasi tampil sebagai id mentah di UI dan
        # bisa dianggap "lokasi tak dikenal" oleh penjaga stok. Dulu `pass` senyap.
        logger.warning("[lokasi] gagal memuat bin (wh_positions) — bin tidak akan "
                       "muncul di daftar/penamaan lokasi: %s", e)

    # 3) Lokasi legacy `rahaza_locations` --------------------------------------
    try:
        legacy = await db.rahaza_locations.find({}, {"_id": 0}).to_list(1000)
    except Exception:
        legacy = []
    legacy_by_code: dict = {}
    for loc in legacy:
        code = (loc.get("code") or "").upper()
        legacy_by_code[code] = loc
        if code in STORAGE_RAHAZA_CODES:
            _put(loc["id"], code, loc.get("name"), "rahaza_location", KIND_STORAGE)
        elif code in PRODUCTION_RAHAZA_CODES or code in QUARANTINE_RAHAZA_CODES:
            _put(loc["id"], code, loc.get("name"), "rahaza_location", KIND_EXEMPT)
        else:
            # Diketahui ADA, tapi bukan zona penyimpanan (gedung konsep, gudang demo
            # warisan, dst.) ⇒ tetap `unmapped` supaya muncul di layar kesehatan.
            info[loc["id"]] = {
                "code": code, "name": loc.get("name") or code,
                "source": "rahaza_location", "kind": KIND_UNMAPPED,
            }

    # 4) Zona tujuan kanonik per peran -----------------------------------------
    legacy_role_codes = {
        "bahan": "ZNA-KAIN", "aksesoris": "ZNA-AKSESORIS",
        "fg": "ZNA-FG", "sample": "ZNA-SAMPLE",
    }
    for role in STORAGE_ROLES:
        target, source = "", ""
        try:
            zid = await canonical_zone_id_for_role(db, role)
        except Exception:
            zid = None
        if zid:
            target, source = zid, "wh_zones"
        else:
            loc = legacy_by_code.get(legacy_role_codes.get(role, ""))
            if loc:
                target, source = loc["id"], "rahaza_locations"
        roles[role] = target
        role_source[role] = source

    return {
        "roles": roles,
        "role_source": role_source,
        "storage_ids": storage_ids,
        "exempt_ids": exempt_ids,
        "info": info,
    }


def classify_location(index: dict, location_id: str | None) -> str:
    """Klasifikasi satu `location_id` memakai hasil `storage_location_index`."""
    if not location_id:
        return KIND_UNMAPPED
    if location_id in (index.get("storage_ids") or set()):
        return KIND_STORAGE
    if location_id in (index.get("exempt_ids") or set()):
        return KIND_EXEMPT
    return (index.get("info", {}).get(location_id) or {}).get("kind") or KIND_UNMAPPED


def describe_location(index: dict, location_id: str | None) -> dict:
    """Label tampilan untuk satu lokasi (selalu mengembalikan dict siap pakai)."""
    if not location_id:
        return {"code": "", "name": "(tanpa lokasi)", "source": "", "kind": KIND_UNMAPPED}
    meta = (index.get("info") or {}).get(location_id)
    if meta:
        return dict(meta)
    return {"code": location_id, "name": "(lokasi tidak dikenal)", "source": "unknown",
            "kind": KIND_UNMAPPED}
