"""rahaza_inventory — shared router, constants, utility helpers, MI helpers."""
# ruff: noqa: E741
from fastapi import APIRouter, Request, HTTPException
from auth import require_auth
import uuid
import logging
from datetime import datetime, timezone, date
from routes.shared import get_pagination_params, paginated_response  # noqa: F401

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza", tags=["rahaza-inventory"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


MATERIAL_TYPES = ["yarn", "accessory", "fg", "packaging", "fabric", "other"]

# FASE IA-5 — batas ambil dokumen master/stok.
# Dulu semua query master memakai `.to_list(500)`. Setelah master data NYATA DA
# dimuat (1.031 material + 730 baris stok), cap itu MEMOTONG DATA SECARA SENYAP:
# dropdown Material Issue kehilangan ratusan item, laporan low-stock salah hitung,
# dan tab "Bahan & Aksesoris" berhenti di angka 500. Dinaikkan ke 20.000 (jauh di
# atas volume nyata, tetap aman untuk memori) — untuk daftar panjang, gunakan
# parameter `?page=` yang sudah didukung endpoint (paginasi server-side).
MASTER_FETCH_LIMIT = 20000
MATERIAL_UNITS = [
    "m", "cm", "yard", "inch",
    "kg", "gram", "ton",
    "pcs", "lusin", "kodi", "gross", "helai", "set", "pair",
    "rol", "gulung", "bal", "karton", "pak", "sak",
    "liter", "ml",
]

# Kategori material (master, CONFIGURABLE via /api/rahaza/material-categories).
# Seed awal (bisa ditambah/edit user). `code` dipakai sbg referensi stabil.
DEFAULT_MATERIAL_CATEGORIES = [
    {"code": "FABRIC", "name": "Kain/Fabric", "order_seq": 1},
    {"code": "YARN", "name": "Benang", "order_seq": 2},
    {"code": "ACCESSORY", "name": "Aksesoris", "order_seq": 3},
    {"code": "PACKAGING", "name": "Packaging", "order_seq": 4},
    {"code": "SEWING_THREAD", "name": "Benang Jahit", "order_seq": 5},
    {"code": "INTERLINING", "name": "Interlining", "order_seq": 6},
    {"code": "OTHER", "name": "Lainnya", "order_seq": 99},
]


async def _require_admin(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "admin", "owner"):
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "inventory.manage" in perms or "warehouse.manage" in perms:
        return user
    raise HTTPException(403, "Forbidden: butuh permission inventory / warehouse.")


async def _require_mi_editor(request: Request):
    """Boleh MEMBUAT / mengubah / mengajukan Pengeluaran Material (MI).

    FASE H-2 (2026-08-16, keputusan owner): pembuat MI = **admin gudang** dan
    **supervisor produksi**. Sebelumnya gerbangnya `_require_admin` yang hanya
    meloloskan role `admin/superadmin/owner` ⇒ dua orang yang benar-benar
    mengerjakan pekerjaan ini (gudang yang mengeluarkan barang, produksi yang
    memintanya) mendapat **403** dan satu-satunya jalan membuat MI dari layar
    adalah endpoint maklon lama yang sudah `deprecated`.

    Approval TETAP terpisah (`_require_mi_approver`): yang membuat permintaan
    tidak boleh sekaligus menyetujui pemotongan stok.
    """
    from routes.shared import require_perm
    return await require_perm(
        request, "inv.material_issue.manage", "inventory.manage", "warehouse.manage",
        legacy_roles=("admin_gudang", "supervisor_produksi", "admin_produksi",
                      "warehouse_manager", "ppic", "manager", "production_manager"),
        message="Akses ditolak: butuh izin membuat pengeluaran material "
                "(inv.material_issue.manage).",
    )


async def _ensure_stock_row(db, material_id: str, location_id: str):
    existing = await db.rahaza_material_stock.find_one({"material_id": material_id, "location_id": location_id}, {"_id": 0})
    if existing:
        return existing
    doc = {"id": _uid(), "material_id": material_id, "location_id": location_id, "qty": 0.0, "updated_at": _now()}
    await db.rahaza_material_stock.insert_one(dict(doc))
    return doc


async def _add_stock(db, material_id: str, location_id: str, delta: float):
    await _ensure_stock_row(db, material_id, location_id)
    await db.rahaza_material_stock.update_one(
        {"material_id": material_id, "location_id": location_id},
        {"$inc": {"qty": float(delta)}, "$set": {"updated_at": _now()}},
    )
    if delta < 0:
        try:
            await _check_low_stock_alert(db, material_id)
        except Exception as e:
            import logging as _l
            _l.getLogger(__name__).warning(f"Low-stock alert check failed: {e}")


async def _check_low_stock_alert(db, material_id: str):
    mat = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
    if not mat:
        return
    min_stock = float(mat.get("min_stock") or 0)
    if min_stock <= 0:
        return
    rows = await db.rahaza_material_stock.find(
        {"material_id": material_id}, {"_id": 0, "qty": 1}
    ).to_list(MASTER_FETCH_LIMIT)
    total = sum(float(r.get("qty") or 0) for r in rows)
    if total < min_stock:
        from routes.rahaza_notifications import publish_notification
        await publish_notification(
            db, type_="low_stock",
            severity="warning" if total > min_stock * 0.5 else "error",
            title=f"Stok {mat.get('name', '')} di bawah minimum",
            message=f"Stok total {total:.1f} {mat.get('unit', '')} < min {min_stock:.1f}. Segera reorder.",
            link_module="wh-stock", link_id=material_id,
            target_roles=["warehouse_manager", "production_manager", "superadmin"],
            dedup_key=f"low_stock::{material_id}",
        )


async def _log_movement(db, user, **fields):
    ts = _now()
    doc = {"id": _uid(), "created_at": ts, "timestamp": ts,
           "created_by": user["id"], "created_by_name": user.get("name", ""), **fields}
    await db.rahaza_material_movements.insert_one(dict(doc))
    return doc


# ── MI helpers ────────────────────────────────────────────────────────────────────────

MI_DOCNUM_KEY = "rahaza_material_issues.mi_number"


async def _gen_mi_number(db, requested: str = "", *, sistem: bool = False):
    """Nomor Pengeluaran Material — SATU PINTU kebijakan penomoran (SESI #19).

    `sistem=True` untuk MI yang LAHIR OTOMATIS dari alur produksi internal (tidak ada
    orang yang mengetik nomornya); jalur itu tetap otomatis meski mode disetel MANUAL.
    """
    from utils.counters import gen_prefixed_number
    from utils.waktu import now_wib
    if sistem:
        today = now_wib().strftime("%Y%m%d")
        return await gen_prefixed_number(db, "rahaza_material_issues", "mi_number",
                                         f"MI-{today}-", 3, config_key=MI_DOCNUM_KEY)
    from core.doc_number_policy import issue_number
    return await issue_number(db, MI_DOCNUM_KEY, requested=requested)


MI_SOURCE_LABELS = {
    "cutting": "Cutting",
    "vendor_shipment": "Kirim Material CMT",
    "job": "Job Produksi",
    "work_order": "Work Order",
    "manual": "Manual",
}


def mi_source_of(mi: dict) -> str:
    """Klasifikasi SUMBER satu dokumen Pengeluaran Material.

    FASE H-6b — "satu daftar untuk seluruh arus keluar gudang" hanya berguna kalau
    setiap baris bisa menjawab "keluar lewat pintu mana?". Klasifikasinya dibaca
    dari BUKTI di dokumen (ref_type/tautan), bukan dari field `source` saja, supaya
    dokumen lama (yang belum punya `source`) tetap tergolong benar.
    """
    if not mi:
        return "manual"
    if mi.get("ref_type") == "cutting_issue" or mi.get("cutting_progress_id") \
            or mi.get("source") == "cutting":
        return "cutting"
    if mi.get("vendor_shipment_id") or mi.get("source") == "vendor_shipment":
        return "vendor_shipment"
    if mi.get("job_id"):
        return "job"
    if mi.get("work_order_id"):
        return "work_order"
    return "manual"


def mi_source_query(source: str) -> dict:
    """Query Mongo untuk satu sumber (dipakai penyaring daftar & rekap)."""
    s = (source or "").strip().lower()
    if s == "cutting":
        return {"$or": [{"ref_type": "cutting_issue"}, {"source": "cutting"}]}
    if s == "vendor_shipment":
        return {"$or": [{"vendor_shipment_id": {"$nin": [None, ""]}},
                        {"source": "vendor_shipment"}]}
    if s == "job":
        return {"job_id": {"$nin": [None, ""]},
                "ref_type": {"$ne": "cutting_issue"}}
    if s == "work_order":
        return {"work_order_id": {"$nin": [None, ""]},
                "job_id": {"$in": [None, ""]}}
    if s == "manual":
        return {"ref_type": {"$ne": "cutting_issue"},
                "source": {"$nin": ["cutting", "vendor_shipment"]},
                "vendor_shipment_id": {"$in": [None, ""]},
                "job_id": {"$in": [None, ""]},
                "work_order_id": {"$in": [None, ""]}}
    return {}


async def _enrich_mi(db, mi):
    if not mi:
        return mi
    # FASE H-6b — setiap baris membawa sumbernya (dipakai kolom & chip "Sumber").
    mi["source_key"] = mi_source_of(mi)
    mi["source_label"] = MI_SOURCE_LABELS.get(mi["source_key"], "Manual")
    m_ids = list({it["material_id"] for it in (mi.get("items") or []) if it.get("material_id")})
    loc_ids = list({it["location_id"] for it in (mi.get("items") or []) if it.get("location_id")})
    mats = await db.rahaza_materials.find({"id": {"$in": m_ids}}, {"_id": 0}).to_list(MASTER_FETCH_LIMIT) if m_ids else []
    locs = await db.rahaza_locations.find({"id": {"$in": loc_ids}}, {"_id": 0}).to_list(MASTER_FETCH_LIMIT) if loc_ids else []
    m_map = {m["id"]: m for m in mats}
    l_map = {l["id"]: l for l in locs}
    for it in (mi.get("items") or []):
        m = m_map.get(it.get("material_id")) or {}
        l = l_map.get(it.get("location_id")) or {}
        it["material_code"] = m.get("code")
        it["material_name"] = m.get("name")
        it["unit"] = m.get("unit")
        it["material_type"] = m.get("type")
        it["location_code"] = l.get("code")
        it["location_name"] = l.get("name")
    return mi


def _norm_mi_items(raw_items, materials_by_id=None):
    """Normalkan baris Pengeluaran Material.

    `qty_uom` (opsional) memungkinkan operator mengetik jumlah dalam satuan
    kemasan. Konversi dilakukan DI SINI supaya `qty_required` yang tersimpan
    selalu dalam satuan dasar (INV-UOM-2) dan seluruh konsumen hilir
    (HPP, jurnal, MRP) tidak perlu tahu soal kemasan.
    Tanpa `qty_uom`, perilakunya persis seperti sebelumnya.
    """
    from core import uom as _uom  # impor lokal: hindari siklus impor

    mats = materials_by_id or {}
    cleaned = []
    for it in raw_items or []:
        mid = it.get("material_id")
        qty_req = float(it.get("qty_required") or 0)
        if not mid or qty_req <= 0:
            continue
        row = {
            "id": it.get("id") or _uid(),
            "material_id": mid,
            "qty_required": round(qty_req, 4),
            "qty_issued":   round(float(it.get("qty_issued") or 0), 4),
            "location_id":  it.get("location_id") or None,
            "notes":        it.get("notes") or "",
        }
        code = _uom.normalize_code(it.get("qty_uom"))
        mat = mats.get(mid)
        if code and mat and code != _uom.base_uom_of(mat):
            from core import bom_uom as _bom_uom   # cakupan lebar (kemasan + global + kain)
            factor, source = _bom_uom.factor_to_base(mat, code)   # UomError bila tak dikenal
            row["qty_required"] = round(qty_req * factor, 4)
            row["input_qty"] = round(qty_req, 4)
            row["input_uom"] = code
            row["uom_factor"] = factor
            row["uom_source"] = source
        cleaned.append(row)
    return cleaned


async def _require_mi_approver(request: Request):
    """Approval Pengeluaran Material (MI) — gerbang izin terpusat.

    2026-08-06: pindah ke `routes.shared.require_perm` (model fallback aman).
    Selama izin role belum diatur owner di layar "Peran & Hak Akses", daftar role
    lama di bawah tetap berlaku sehingga tidak ada fitur yang mati.
    """
    from routes.shared import require_perm
    return await require_perm(
        request, "inventory.approve", "warehouse.approve",
        legacy_roles=("manager", "ppic", "warehouse_manager", "production_manager"),
        message="Akses ditolak: butuh izin approve pengeluaran material (inventory.approve).",
    )
