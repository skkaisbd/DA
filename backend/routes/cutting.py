"""
PORTAL CUTTING — Roll Kain ➜ Kain Pola (Potongan)
CV. Dewi Aditya ERP · FASE IA-4

MENGAPA MODUL INI ADA
---------------------
Di DA, kain datang sebagai ROLL (satuan Kg / Yard / Meter). Sebelum bisa dijahit,
roll harus dipotong jadi KAIN POLA ("potongan") per style + warna + size (satuan pcs).
Potongan inilah yang:
  · dihitung sebagai MATERIAL (bukan barang jadi) di gudang,
  · dipakai sebagai komponen BOM job produksi internal,
  · dikirim ke CMT lewat "Kirim Material CMT" / "Pengeluaran Material".
Sebelum modul ini, langkah tersebut tidak tercatat di sistem sehingga stok kain
tidak pernah berkurang dan potongan tidak pernah punya identitas stok.

KEPUTUSAN DESAIN (hasil pemetaan database — bukan tebakan)
----------------------------------------------------------
1. TIDAK membuat gudang/stok baru. Semua mutasi lewat SSOT `core.stock_service`
   (`issue()` untuk kain, `add()` untuk potongan) sehingga:
   `rahaza_material_stock` + `rahaza_stock_ledger` tetap satu-satunya kebenaran,
   dan seluruh laporan stok/valuasi lama otomatis ikut benar.
2. Output potongan = DOKUMEN BARU di `rahaza_materials` (master material) —
   sesuai keputusan owner. Ditandai `is_cut_panel: True`, `type: "fabric"`,
   `category: "POTONGAN"`, `unit: "pcs"`, plus `source_material_id` ke kain asalnya
   sehingga ketelusuran roll ➜ potongan tidak putus.
   Kode dibangkitkan deterministik: `CUT-<STYLE>-<WARNA>-<SIZE>`; bila sudah ada,
   dipakai ulang (idempoten) — mencegah duplikat master.
3. Roll fisik (`wh_fabric_rolls`) **WAJIB** untuk kain yang dilacak per gulungan
   (FASE H-6, keputusan owner 2026-08-16). Sebelum ini pemilihan roll bersifat
   opsional, artinya kain bisa dipotong tanpa satu gulungan pun berkurang: stok
   turun, roll tetap penuh, dan tidak ada cara menjawab "gulungan mana yang dipakai
   untuk order ini" saat buyer menuntut lot kain yang sama. Sekarang: sisa roll
   (`remaining_kg`/`remaining_m`) dikurangi FIFO lewat SATU pintu
   `core.fabric_roll_engine` (+ movement `wh_fabric_roll_movements`), TANPA
   memotong stok material dua kali (potong stok material hanya sekali, di sini).
   Bila kainnya belum punya gulungan sama sekali, permintaan DITOLAK dengan alasan
   yang menyebut jalan keluarnya (isi Rincian Roll di Penerimaan Barang, atau
   terbitkan gulungan retroaktif di Gudang → Roll Kain).
4. HPP: saat COMPLETE, harga satuan potongan dihitung
   = (qty kain terpakai × unit_cost kain) / qty potongan jadi, lalu ditulis ke
   `unit_cost` master potongan supaya jurnal persediaan & HPP hilir tetap benar.

STATE MACHINE
-------------
   draft ──start──▶ in_progress ──complete──▶ completed
     │                   │
     └───cancel──────────┘   (cancel hanya bila belum ada progres)

Koleksi baru (tidak bentrok dengan koleksi manapun yang sudah ada — sudah diverifikasi):
  · cutting_orders
  · cutting_progress
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from auth import require_auth, serialize_doc, log_activity
from core import stock_service
from core import fabric_roll_engine  # FASE H-6: gulungan WAJIB ditunjuk saat memotong
from core import cutting_material_issue  # FASE H-6b: arus keluar kain punya DOKUMEN
from core import cut_panel_value    # SESI #32: nilai kain berpindah jadi nilai potongan
from core import cut_panel_health   # SESI #32: penjaga & pembersih potongan yatim
from core import uom as _uom_core   # SSOT konversi satuan (operator boleh input per rol/kemasan)
from core import bom_uom as _bom_uom  # cakupan lebar: kemasan + global + kain (gsm & lebar)
from core import product_costing  # BOM → kebutuhan kain per pcs (rencana tidak lagi ditebak)
from core.stock_service import InsufficientStock
from database import get_db
from utils.counters import gen_prefixed_number, resolve_master_code

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cutting", tags=["cutting"])

ORDERS = "cutting_orders"
PROGRESS = "cutting_progress"

STATUS_DRAFT = "draft"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

# Satuan kain yang wajar jadi INPUT cutting (roll).
INPUT_UNITS = {"kg", "gram", "m", "cm", "yard", "inch", "rol", "gulung", "bal"}
OUTPUT_UNIT = "pcs"
OUTPUT_CATEGORY = "POTONGAN"


async def ensure_cutting_indexes():
    """Indeks + PEMBUATAN koleksi cutting saat startup.

    Kenapa dipanggil di startup (bukan lazy saat order pertama dibuat):
    `mongodump` hanya menyalin koleksi yang SUDAH ADA. Kalau koleksi cutting baru
    lahir saat transaksi pertama, backup yang diambil sebelum itu tidak memuatnya
    dan proses restore akan menghapus jejak modul ini. Membuat indeks di startup
    memastikan `cutting_orders` & `cutting_progress` selalu ikut ter-backup.
    """
    db = get_db()
    await db[ORDERS].create_index("id", unique=True)
    await db[ORDERS].create_index("number", unique=True)
    await db[ORDERS].create_index("status")
    await db[ORDERS].create_index("input_material_id")
    await db[ORDERS].create_index("output_material_id")
    await db[PROGRESS].create_index("id", unique=True)
    await db[PROGRESS].create_index("cutting_order_id")
    # FASE H-6b — satu laporan progres = MAKSIMAL satu dokumen Pengeluaran Material.
    # Indeks unik sparse-nya dibuat di satu tempat (core/cutting_material_issue)
    # supaya aturan idempotensinya tidak tersebar.
    await db[PROGRESS].create_index("material_issue_id")
    await cutting_material_issue.ensure_indexes(db)
    log.info("Cutting indexes created (cutting_orders, cutting_progress)")


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _slug(v: str, maxlen: int = 14) -> str:
    out = "".join(ch for ch in (v or "").upper() if ch.isalnum() or ch in (" ", "-"))
    out = "-".join(p for p in out.replace(" ", "-").split("-") if p)
    return out[:maxlen] or "NA"


async def _require_cutting_user(request: Request) -> dict:
    """Cutting = pekerjaan gudang/produksi.

    2026-08-06: gerbang izin dipusatkan ke `routes.shared.require_perm`
    (model fallback aman) supaya owner bisa memberi/mencabut hak lewat layar
    "Peran & Hak Akses" tanpa mengubah kode.
    """
    from routes.shared import require_perm
    return await require_perm(
        request, "cutting.manage", "cutting.input", "warehouse.manage",
        legacy_roles=(
            "spv_cuting", "operator_cuting",
            "supervisor_produksi", "admin_produksi", "supervisor",
            "admin_gudang",
        ),
        message="Akses ditolak: butuh izin cutting (cutting.manage / cutting.input).",
    )


async def _actor(user: dict) -> dict:
    return {"id": user.get("id"), "name": user.get("name", "")}


async def _get_order(db, oid: str) -> dict:
    doc = await db[ORDERS].find_one({"id": oid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Cutting order tidak ditemukan.")
    return doc


async def _stock_locations(db, material_id: str) -> list[dict]:
    """Daftar lokasi yang MEMANG punya stok untuk material ini, urut qty terbesar.

    Kenapa perlu: stok tidak disimpan global melainkan per (material, lokasi).
    Bug nyata yang ditemukan QA: cutting dibuat dengan lokasi bawaan sistem
    ("Gedung Produksi") padahal saldo kain berada di "Gudang Lantai 1/Area Gudang",
    sehingga validasi start LULUS (cek total lintas lokasi) tapi pemotongan stok
    GAGAL (cek per-lokasi). Sejak sekarang lokasi order selalu diarahkan ke lokasi
    yang benar-benar memegang stok.
    """
    from core.stock_schema import read_qty
    rows = await db.rahaza_material_stock.find({"material_id": material_id}, {"_id": 0}).to_list(500)
    out = []
    for r in rows:
        qty = float(read_qty(r) or 0)
        if qty <= 0:
            continue
        out.append({"location_id": r.get("location_id"), "qty": round(qty, 4)})
    if not out:
        return []
    ids = [o["location_id"] for o in out if o["location_id"]]
    names = {}
    async for loc in db.rahaza_locations.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "code": 1}):
        names[loc["id"]] = loc.get("name") or loc.get("code") or ""
    async for z in db.wh_zones.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "code": 1}):
        names.setdefault(z["id"], z.get("name") or z.get("code") or "")
    for o in out:
        o["location_name"] = names.get(o["location_id"], "Lokasi lain")
    out.sort(key=lambda x: -x["qty"])
    return out


async def _default_location(db, location_id: Optional[str] = None,
                            material_id: Optional[str] = None) -> tuple[str, str]:
    """Tentukan lokasi order cutting.

    Prioritas: (1) yang dipilih user, (2) lokasi dengan stok TERBANYAK untuk material
    tersebut, (3) lokasi bernama 'Gudang…', (4) lokasi aktif pertama.
    """
    if location_id:
        loc = await db.rahaza_locations.find_one({"id": location_id}, {"_id": 0})
        if loc:
            return loc["id"], loc.get("name") or loc.get("code") or ""
        z = await db.wh_zones.find_one({"id": location_id}, {"_id": 0})
        if z:
            return z["id"], z.get("name") or z.get("code") or ""
    if material_id:
        locs = await _stock_locations(db, material_id)
        if locs:
            return locs[0]["location_id"], locs[0]["location_name"]
    loc = await db.rahaza_locations.find_one(
        {"active": True, "name": {"$regex": "gudang", "$options": "i"}}, {"_id": 0}, sort=[("code", 1)])
    if not loc:
        loc = await db.rahaza_locations.find_one({"active": True}, {"_id": 0}, sort=[("code", 1)])
    if not loc:
        raise HTTPException(400, "Belum ada lokasi gudang (rahaza_locations). Buat lokasi dulu.")
    return loc["id"], loc.get("name") or loc.get("code") or ""


async def _enrich(db, o: dict) -> dict:
    o["progress_count"] = await db[PROGRESS].count_documents({"cutting_order_id": o["id"]})
    planned_in = _f(o.get("planned_input_qty"))
    consumed = _f(o.get("consumed_input_qty"))
    planned_out = _f(o.get("planned_output_qty"))
    produced = _f(o.get("produced_qty"))
    o["input_remaining"] = round(max(planned_in - consumed, 0), 4)
    o["output_remaining"] = round(max(planned_out - produced, 0), 4)
    o["progress_pct"] = round((produced / planned_out * 100), 1) if planned_out > 0 else 0.0
    o["yield_per_input"] = round(produced / consumed, 3) if consumed > 0 else 0.0
    return o


# ═════════════════════════════════════════════════════════════════════════════
# MASTER HELPERS — dipakai form frontend
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/input-materials")
async def list_input_materials(request: Request, q: Optional[str] = None):
    """Master material yang layak jadi INPUT cutting (kain/benang, BUKAN potongan)."""
    await require_auth(request)
    db = get_db()
    query: dict = {
        "active": True,
        "type": {"$in": ["fabric", "yarn"]},
        "is_cut_panel": {"$ne": True},
    }
    if q:
        query["$or"] = [
            {"code": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
            {"color": {"$regex": q, "$options": "i"}},
        ]
    mats = await db.rahaza_materials.find(query, {"_id": 0}).sort("name", 1).to_list(5000)
    ids = [m["id"] for m in mats]
    onhand = await stock_service.onhand_map(ids, db=db) if ids else {}
    rolls = {}
    if ids:
        cur = db.wh_fabric_rolls.aggregate([
            {"$match": {"material_id": {"$in": ids}, "status": {"$nin": ["fully_issued", "rejected"]}}},
            {"$group": {"_id": "$material_id", "n": {"$sum": 1}}},
        ])
        async for r in cur:
            rolls[r["_id"]] = r["n"]
    # Peta lokasi-berstok per material (1 query, bukan N query) — dipakai form agar
    # user langsung tahu stok kain ADA DI GUDANG MANA.
    loc_names = {}
    async for loc in db.rahaza_locations.find({}, {"_id": 0, "id": 1, "name": 1, "code": 1}):
        loc_names[loc["id"]] = loc.get("name") or loc.get("code") or ""
    from core.stock_schema import read_qty
    per_mat: dict[str, list] = {}
    if ids:
        async for r in db.rahaza_material_stock.find({"material_id": {"$in": ids}}, {"_id": 0}):
            q = float(read_qty(r) or 0)
            if q <= 0:
                continue
            per_mat.setdefault(r["material_id"], []).append({
                "location_id": r.get("location_id"),
                "location_name": loc_names.get(r.get("location_id"), "Lokasi lain"),
                "qty": round(q, 4),
            })
    for m in mats:
        locs = sorted(per_mat.get(m["id"], []), key=lambda x: -x["qty"])
        m["stock_qty"] = round(_f(onhand.get(m["id"])), 4)
        m["roll_count"] = rolls.get(m["id"], 0)
        m["stock_locations"] = locs
        m["best_location_id"] = locs[0]["location_id"] if locs else None
        m["best_location_name"] = locs[0]["location_name"] if locs else ""
    return serialize_doc(mats)


@router.get("/locations")
async def list_locations(request: Request):
    """Lokasi gudang untuk dropdown form cutting."""
    await require_auth(request)
    db = get_db()
    rows = await db.rahaza_locations.find({"active": True}, {"_id": 0}).sort("name", 1).to_list(500)
    return serialize_doc(rows)


@router.get("/rolls")
async def list_rolls(request: Request, material_id: str):
    """Gulungan yang masih bersisa untuk satu kain (WAJIB dipilih saat lapor progres).

    Urut nomor roll = FIFO penerimaan, sehingga gulungan tertua dipakai lebih dulu
    dan kain tidak menua di rak sampai warnanya berubah.
    """
    await require_auth(request)
    db = get_db()
    rows = await fabric_roll_engine.open_rolls(db, material_id)
    out = []
    for r in rows:
        out.append({**r,
                    "remaining": round(fabric_roll_engine.remaining_of(r), 3),
                    "remaining_uom": r.get("uom", "")})
    mat = await db.rahaza_materials.find_one(
        {"id": material_id}, {"_id": 0, "id": 1, "code": 1, "name": 1, "unit": 1,
                              "type": 1, "is_cut_panel": 1})
    tracked = bool(mat and fabric_roll_engine.is_roll_material(mat))
    return serialize_doc({
        "items": out,
        "total": len(out),
        # `roll_required` dipakai UI untuk menandai pemilih roll sebagai WAJIB (H-6)
        # dan menampilkan jalan keluar bila daftarnya kosong.
        "roll_required": tracked,
        "total_remaining": round(sum(x["remaining"] for x in out), 3),
        "uom": (out[0].get("uom") if out else (fabric_roll_engine.roll_uom(mat.get("unit")) if mat else "")),
    })


@router.get("/bom-requirement")
async def bom_requirement(request: Request, model_id: str, size_id: Optional[str] = None,
                          variant_id: Optional[str] = None, qty_pcs: float = 0,
                          input_material_id: Optional[str] = None):
    """Kebutuhan bahan menurut BOM untuk rencana potongan (dipakai dialog Order Cutting).

    KENAPA: sebelum ini `planned_input_qty` (rencana pemakaian kain) DITEBAK manual
    padahal BOM per model+size sudah menyimpan kebutuhan per pcs. Endpoint ini
    mengembalikan kebutuhan **per pcs** dan **total** dalam satuan DASAR kain
    (lewat SSOT `core/bom_uom`), plus daftar aksesoris yang ikut dibutuhkan.
    Jujur: BOM tidak ada / kain terpilih tidak ada di BOM / satuan belum jelas
    dilaporkan di `gaps` — bukan diam-diam kosong.
    """
    await _require_cutting_user(request)
    db = get_db()
    data = await product_costing.bom_requirement_for_cutting(
        db, model_id=model_id, size_id=size_id, variant_id=variant_id,
        qty_pcs=_f(qty_pcs), input_material_id=input_material_id)
    return serialize_doc(data)


@router.get("/output-materials")
async def list_output_materials(request: Request):
    """Semua master potongan yang pernah dihasilkan cutting.

    SESI #32 — layar Master Potongan tidak lagi hanya menampilkan QTY: tiap baris
    membawa NILAI (stok × HPP), STATUS nilainya (`valued`/`unvalued` + alasannya),
    ASAL-nya (kain sumber + nomor order cutting), dan penanda **yatim** beserta
    alasan mengapa ia belum boleh dibersihkan.
    """
    await require_auth(request)
    db = get_db()
    mats = await db.rahaza_materials.find(
        {"is_cut_panel": True, "active": True}, {"_id": 0}
    ).sort("code", 1).to_list(2000)
    ids = [m["id"] for m in mats]
    onhand = await stock_service.onhand_map(ids, db=db) if ids else {}
    for m in mats:
        qty = round(_f(onhand.get(m["id"])), 4)
        row = await cut_panel_health.inspect(db, m, onhand=qty)
        m["stock_qty"] = qty
        m["stock_value"] = row["stock_value"]
        m["value_status"] = row["value_status"]
        m["value_note"] = m.get("value_note") or ""
        m["orphan"] = row["orphan"]
        m["orphan_reasons"] = row["reasons"]
        m["orphan_reason_text"] = row["reason_text"]
        m["cleanable"] = row["cleanable"]
        m["block_reason"] = row["block_reason"]
        m["cutting_order_number"] = row["cutting_order_number"]
        m["source_material_code"] = row["source_material_code"]
    return serialize_doc(mats)


@router.get("/panels/health")
async def panels_health(request: Request, only_orphan: bool = True, limit: int = 500):
    """Kesehatan master POTONGAN: mana yang YATIM & mana yang boleh dibersihkan.

    Read-only. Dipakai kartu "Potongan yatim" di Portal Cutting dan gate INV-F37.
    """
    await require_auth(request)
    db = get_db()
    return serialize_doc(await cut_panel_health.scan(
        db, limit=limit, only_orphan=only_orphan))


@router.post("/panels/cleanup")
async def panels_cleanup(request: Request):
    """Bersihkan master potongan yatim yang TERBUKTI belum pernah dipakai.

    Body opsional: `{"ids": [...], "dry_run": true}`. Yang masih berstok / punya
    kartu stok / dirujuk dokumen lain TIDAK dihapus — alasannya dikembalikan.
    """
    user = await _require_cutting_user(request)
    db = get_db()
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — tombol tanpa argumen: bersihkan semua yang layak
        body = {}
    body = body or {}
    ids = [str(x) for x in (body.get("ids") or []) if str(x or "").strip()]
    res = await cut_panel_health.cleanup(
        db, user, ids=ids or None, dry_run=bool(body.get("dry_run")))
    if res.get("removed") and not res.get("dry_run"):
        await log_activity(user["id"], user.get("name", ""), "cleanup",
                           "cutting.panels", f"{res['removed']} potongan yatim")
    return serialize_doc(res)


async def _input_material(db, material_id: str) -> dict:
    return await db.rahaza_materials.find_one(
        {"id": material_id},
        {"_id": 0, "id": 1, "code": 1, "name": 1, "unit": 1, "type": 1,
         "is_cut_panel": 1, "color": 1},
    ) or {}


def _roll_hint(rolls: list[dict], maxn: int = 4) -> str:
    bits = [f"{r.get('roll_no')} (sisa {fabric_roll_engine.remaining_of(r):,.2f} {r.get('uom', '')})"
            for r in rolls[:maxn]]
    return ", ".join(bits) + (" …" if len(rolls) > maxn else "")


_NO_ROLL_WAY_OUT = (
    "Jalan keluarnya: isi kolom Rincian Roll saat Penerimaan Barang, atau terbitkan "
    "gulungan untuk penerimaan yang sudah lewat di Gudang → Roll Kain → tab "
    "\"Penerimaan tanpa roll\"."
)


async def _assert_rolls_available(db, mat: dict, label: str) -> list[dict]:
    """FASE H-6: kain yang dilacak per gulungan harus PUNYA gulungan bersisa.

    Diperiksa saat order dibuat (gagal cepat) supaya operator tidak menyiapkan order
    yang pasti mentok saat lapor progres.
    """
    if not fabric_roll_engine.is_roll_material(mat):
        return []
    rolls = await fabric_roll_engine.open_rolls(db, mat["id"])
    if not rolls:
        raise HTTPException(400, (
            f"Kain {label} belum punya satu pun gulungan bersisa di sistem, jadi tidak akan "
            f"bisa dibuktikan gulungan mana yang dipotong. {_NO_ROLL_WAY_OUT}"))
    return rolls


async def _plan_roll_consumption(db, o: dict, body: dict, input_used: float) -> tuple[list, dict]:
    """Rencana pemakaian gulungan untuk SATU laporan progres (H-6).

    Dihitung SEBELUM stok dipotong: kalau gulungan yang dipilih tidak cukup atau
    tidak dipilih, laporan ditolak tanpa menyisakan stok yang sudah turun sebagian.
    Kembalian `plan` kosong HANYA bila materialnya memang tidak dilacak per gulungan
    (mis. potongan bersatuan pcs) — bukan karena rollnya lupa dipilih.
    """
    mat = await _input_material(db, o["input_material_id"])
    label = f"{o.get('input_material_code', '')} — {o.get('input_material_name', '')}".strip(" —")
    if not fabric_roll_engine.is_roll_material(mat):
        return [], {"tracked": False}

    open_rolls = await fabric_roll_engine.open_rolls(db, o["input_material_id"])
    if not open_rolls:
        raise HTTPException(400, (
            f"Kain {label} belum punya satu pun gulungan bersisa di sistem, jadi tidak bisa "
            f"dibuktikan gulungan mana yang dipotong. {_NO_ROLL_WAY_OUT}"))

    picked = [str(x).strip() for x in (body.get("roll_ids") or []) if str(x or "").strip()]
    single = str(body.get("roll_id") or "").strip()
    if single and single not in picked:
        picked.append(single)
    if not picked:
        raise HTTPException(400, (
            f"Pilih gulungan yang dipotong untuk {label} — tanpa itu sisa gulungan di sistem "
            "akan menyimpang dari kenyataan dan lot kain tidak bisa dipertanggungjawabkan ke "
            f"buyer. Gulungan yang masih bersisa: {_roll_hint(open_rolls)}"))

    by_id = {r["id"]: r for r in open_rolls}
    by_no = {str(r.get("roll_no", "")): r for r in open_rolls}
    chosen, unknown = [], []
    for rid in picked:
        r = by_id.get(rid) or by_no.get(rid)
        if r and all(r["id"] != c["id"] for c in chosen):
            chosen.append(r)
        elif not r:
            unknown.append(rid)
    if unknown:
        others = await db.wh_fabric_rolls.find(
            {"$or": [{"id": {"$in": unknown}}, {"roll_no": {"$in": unknown}}]},
            {"_id": 0, "roll_no": 1, "material_code": 1, "status": 1},
        ).to_list(20)
        detail = "; ".join(
            f"{x.get('roll_no')} milik {x.get('material_code') or '?'} (status {x.get('status')})"
            for x in others) or "gulungan tidak dikenal"
        raise HTTPException(400, (
            f"Gulungan yang dipilih tidak bisa dipakai untuk {label}: {detail}. Pilih dari "
            f"gulungan kain ini yang masih bersisa: {_roll_hint(open_rolls)}"))

    # Urut nomor roll = FIFO penerimaan (gulungan tertua dipakai lebih dulu).
    chosen.sort(key=lambda r: str(r.get("roll_no", "")))
    unit_label = f" {chosen[0].get('uom', '')}" if chosen else ""
    plan = fabric_roll_engine.allocate(chosen, input_used, unit_label)
    return plan, {"tracked": True, "picked": [r["id"] for r in chosen],
                  "available": len(open_rolls)}


async def _ensure_output_material(db, o: dict, user: dict) -> dict:
    """Buat / pakai-ulang master material POTONGAN untuk order ini (idempoten)."""
    if o.get("output_material_id"):
        mat = await db.rahaza_materials.find_one({"id": o["output_material_id"]}, {"_id": 0})
        if mat:
            return mat
    code = (o.get("output_material_code") or "").strip().upper()
    if not code:
        default_code = "CUT-" + "-".join(
            x for x in [_slug(o.get("style_name") or o.get("style_sku") or "PANEL"),
                        _slug(o.get("output_color") or "", 10),
                        _slug(o.get("output_size") or "", 6)] if x and x != "NA"
        )
        code = await resolve_master_code(
            db, "rahaza_materials.cut_panel_code",
            {"STYLE": _slug(o.get("style_name") or o.get("style_sku") or "PANEL"),
             "WARNA": _slug(o.get("output_color") or "", 10),
             "SIZE": _slug(o.get("output_size") or "", 6)},
            default_code,
        )
    existing = await db.rahaza_materials.find_one({"code": code, "active": True}, {"_id": 0})
    if existing:
        return existing
    src = await db.rahaza_materials.find_one({"id": o.get("input_material_id")}, {"_id": 0}) or {}
    name_parts = [p for p in [o.get("style_name") or o.get("style_sku") or "Potongan",
                              o.get("output_color"), o.get("output_size")] if p]
    doc = {
        "id": _uid(),
        "code": code,
        "name": "Potongan " + " · ".join(name_parts),
        "type": "fabric",
        "unit": OUTPUT_UNIT,
        "category": OUTPUT_CATEGORY,
        "category_name": "Potongan / Kain Pola",
        "color": o.get("output_color") or "",
        "composition": src.get("composition") or "",
        "notes": f"Auto dari Cutting {o.get('number')} — sumber kain {src.get('code', '-')}",
        "min_stock": 0,
        "unit_cost": 0.0,
        # SESI #32 — status NILAI potongan dikatakan sejak lahir. Selama belum
        # ada progres, potongan memang belum bernilai (belum ada kain yang
        # berpindah nilainya) — itu keadaan, bukan harga Rp0 yang benar.
        "value_status": "unvalued",
        "value_note": "Belum ada progres potong — nilai lahir saat kain dipotong.",
        # Potongan selalu dihitung per satuan dasar (pcs). Struktur UOM
        # dibuat eksplisit agar guardrail INV-UOM-3/4 hijau dan agar item ini
        # bisa diberi kemasan sendiri lewat Master Material bila diperlukan.
        "base_uom": "pcs",
        "uoms": [{"code": "pcs", "name": "PCS", "factor": 1.0, "is_base": True, "level": 0}],
        "purchase_uom": "pcs", "issue_uom": "pcs", "display_uom": "pcs",
        "pack_unit": "pack", "pack_size": 1, "display_in_packs": False,
        # penanda domain — dipakai filter Gudang & modul cutting
        "is_cut_panel": True,
        "source_material_id": o.get("input_material_id"),
        "source_material_code": src.get("code") or "",
        # SESI #32 — BUKTI KEPEMILIKAN. Tanpa dua field ini, master potongan
        # tidak bisa dibuktikan milik order mana, sehingga (a) penjaga tidak bisa
        # membuangnya saat ordernya dibatalkan dan (b) alat ukur menghapus
        # ordernya lalu masternya tertinggal jadi sampah permanen di Master Item.
        "cutting_order_id": o.get("id") or "",
        "cutting_order_number": o.get("number") or "",
        "created_from": "cutting",
        "style_sku": o.get("style_sku") or "",
        "style_name": o.get("style_name") or "",
        "size": o.get("output_size") or "",
        "active": True,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_materials.insert_one(dict(doc))
    await log_activity(user["id"], user.get("name", ""), "create", "cutting.output_material", code)
    return doc


# ═════════════════════════════════════════════════════════════════════════════
# CRUD ORDER
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/orders")
async def list_orders(request: Request, status: Optional[str] = None,
                      q: Optional[str] = None, limit: int = 200, skip: int = 0):
    await require_auth(request)
    db = get_db()
    query: dict = {}
    if status:
        query["status"] = status
    if q:
        query["$or"] = [
            {"number": {"$regex": q, "$options": "i"}},
            {"style_name": {"$regex": q, "$options": "i"}},
            {"style_sku": {"$regex": q, "$options": "i"}},
            {"input_material_name": {"$regex": q, "$options": "i"}},
            {"output_material_code": {"$regex": q, "$options": "i"}},
        ]
    rows = await db[ORDERS].find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(500)
    for r in rows:
        await _enrich(db, r)
    return serialize_doc(rows)


@router.get("/dashboard")
async def dashboard(request: Request):
    await require_auth(request)
    db = get_db()
    by_status = {}
    cur = db[ORDERS].aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}])
    async for r in cur:
        by_status[r["_id"]] = r["n"]
    agg = await db[ORDERS].aggregate([
        {"$group": {
            "_id": None,
            "planned_output": {"$sum": "$planned_output_qty"},
            "produced": {"$sum": "$produced_qty"},
            "consumed": {"$sum": "$consumed_input_qty"},
            "waste": {"$sum": "$waste_qty"},
        }}
    ]).to_list(1)
    tot = agg[0] if agg else {}
    panels = await db.rahaza_materials.count_documents({"is_cut_panel": True, "active": True})
    recent = await db[ORDERS].find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
    consumed = _f(tot.get("consumed"))
    produced = _f(tot.get("produced"))
    return serialize_doc({
        "total_orders": sum(by_status.values()),
        "by_status": {
            "draft": by_status.get(STATUS_DRAFT, 0),
            "in_progress": by_status.get(STATUS_IN_PROGRESS, 0),
            "completed": by_status.get(STATUS_COMPLETED, 0),
            "cancelled": by_status.get(STATUS_CANCELLED, 0),
        },
        "planned_output_qty": round(_f(tot.get("planned_output")), 2),
        "produced_qty": round(produced, 2),
        "consumed_input_qty": round(consumed, 3),
        "waste_qty": round(_f(tot.get("waste")), 3),
        "avg_yield": round(produced / consumed, 3) if consumed > 0 else 0.0,
        "output_material_count": panels,
        "recent": recent,
    })


# ═════════════════════════════════════════════════════════════════════════════
# FASE H-6b — DOKUMEN PENGELUARAN MATERIAL UNTUK ARUS KELUAR CUTTING
# CATATAN URUTAN ROUTE (pelajaran sesi #16): dua route literal di bawah HARUS
# dideklarasikan SEBELUM `GET /orders/{oid}` — bukan karena bentrok segmen
# pertama, tetapi supaya kebiasaan "literal sebelum ber-parameter" tidak pernah
# dilanggar di berkas ini.
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/issue-docs/missing")
async def list_progress_without_issue_doc(request: Request, limit: int = 200,
                                          order_id: Optional[str] = None):
    """Progres cutting yang kainnya SUDAH keluar tetapi belum punya dokumen MI.

    Read-only (kecuali memulihkan tautan yang hilang — lihat docstring engine).
    Dipakai kartu "Progres tanpa dokumen MI" di Portal Cutting.
    """
    await require_auth(request)
    db = get_db()
    out = await cutting_material_issue.progress_without_doc(
        db, limit=limit, order_id=order_id)
    return serialize_doc(out)


@router.post("/issue-docs/backfill")
async def backfill_issue_docs(request: Request):
    """Terbitkan dokumen MI retroaktif untuk progres cutting lama (idempoten).

    TIDAK memotong stok: kain sudah berkurang saat progres dilaporkan.
    """
    user = await _require_cutting_user(request)
    db = get_db()
    body = {}
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — body OPSIONAL (tombol tanpa argumen)
        body = {}
    res = await cutting_material_issue.backfill(
        db, user, limit=int((body or {}).get("limit") or 500),
        order_id=(body or {}).get("order_id") or None)
    if res.get("created"):
        await log_activity(user["id"], user.get("name", ""), "backfill_mi",
                           "cutting.issue_docs", f"{res['created']} dokumen")
    return serialize_doc(res)


@router.get("/orders/{oid}")
async def get_order(oid: str, request: Request):
    await require_auth(request)
    db = get_db()
    o = await _get_order(db, oid)
    await _enrich(db, o)
    o["progress"] = await db[PROGRESS].find(
        {"cutting_order_id": oid}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    if o.get("output_material_id"):
        om = await db.rahaza_materials.find_one({"id": o["output_material_id"]}, {"_id": 0})
        if om:
            o["output_material"] = om
            o["output_stock"] = round(_f(await stock_service.get_onhand(om["id"], db=db)), 4)
    if o.get("input_material_id"):
        o["input_stock"] = round(_f(await stock_service.get_onhand(o["input_material_id"], db=db)), 4)
    return serialize_doc(o)


@router.post("/orders")
async def create_order(request: Request):
    user = await _require_cutting_user(request)
    db = get_db()
    body = await request.json()

    input_material_id = (body.get("input_material_id") or "").strip()
    if not input_material_id:
        raise HTTPException(400, "Material kain (input) wajib dipilih.")
    mat = await db.rahaza_materials.find_one({"id": input_material_id, "active": True}, {"_id": 0})
    if not mat:
        raise HTTPException(404, "Material kain tidak ditemukan / tidak aktif.")
    if mat.get("is_cut_panel"):
        raise HTTPException(400, "Material yang dipilih adalah POTONGAN, bukan kain roll.")
    unit = (mat.get("unit") or "").lower()
    if unit not in INPUT_UNITS:
        raise HTTPException(
            400, f"Satuan material '{unit}' bukan satuan kain roll ({sorted(INPUT_UNITS)}).")

    planned_input = _f(body.get("planned_input_qty"))
    planned_output = _f(body.get("planned_output_qty"))
    if planned_input <= 0:
        raise HTTPException(400, "Rencana pemakaian kain harus > 0.")
    if planned_output <= 0:
        raise HTTPException(400, "Rencana hasil potongan (pcs) harus > 0.")

    style_name = (body.get("style_name") or "").strip()
    # ── STYLE/PRODUK WAJIB DARI MASTER (keputusan pemilik 2026-08-21) ─────────
    # Dulu `style_name` adalah ketikan bebas, jadi order cutting TIDAK pernah
    # menunjuk model manapun: BOM (disimpan per model+size) dan produksi tidak
    # bisa tahu potongan ini milik produk yang mana, dan satu style bisa punya
    # banyak ejaan ("Dress Jemina", "dress jemina", "Jemina Dress").
    model_id = (body.get("model_id") or "").strip()
    if not model_id:
        raise HTTPException(400, (
            "Model/style wajib dipilih dari Master Produk — bukan diketik. "
            "Pilih model di dialog cutting, atau buat modelnya dulu lewat tombol "
            "\"Model Baru\" supaya BOM & produksi mengenali produk ini."))
    model = await db.rahaza_models.find_one({"id": model_id}, {"_id": 0})
    if not model:
        raise HTTPException(404, "Model produk tidak ditemukan di master.")
    if model.get("active") is False:
        raise HTTPException(400, f"Model '{model.get('name')}' sudah non-aktif — pilih model lain.")
    style_name = (model.get("name") or "").strip()
    style_sku = (model.get("code") or "").strip()

    # Varian (warna+size) juga dari master model itu, supaya kode potongan &
    # penelusuran ke BOM/SKU tidak pernah mengarang warna/ukuran.
    variant = None
    variant_id = (body.get("variant_id") or "").strip()
    if variant_id:
        variant = await db.rahaza_model_variants.find_one(
            {"id": variant_id, "model_id": model_id}, {"_id": 0})
        if not variant:
            raise HTTPException(400, "Varian (warna/size) bukan milik model yang dipilih.")
    output_color = ((variant or {}).get("color_name") or (variant or {}).get("color")
                    or body.get("output_color") or mat.get("color") or "").strip()
    output_size = ((variant or {}).get("size_code") or body.get("output_size") or "").strip()

    # 2026-08-23 — UKURAN TANPA VARIAN. Ada model yang BOM-nya sudah dibuat untuk
    # sebuah ukuran tetapi varian (warna×size) belum didaftarkan; dulu ukuran itu
    # MUSTAHIL dipilih di dialog cutting sehingga BOM-nya tidak bisa dipakai
    # (jalan buntu yang terlihat saat mencoba layarnya). Sekarang `size_id` boleh
    # dikirim langsung — divalidasi ke master ukuran — supaya order tetap menunjuk
    # (model + ukuran) yang sama dengan BOM.
    size_id_body = (body.get("size_id") or "").strip()
    size_doc = None
    if not variant and size_id_body:
        size_doc = await db.rahaza_sizes.find_one({"id": size_id_body}, {"_id": 0})
        if not size_doc:
            raise HTTPException(400, "Ukuran tidak ditemukan di master ukuran.")
        output_size = (size_doc.get("code") or output_size or "").strip()

    loc_id, loc_name = await _default_location(db, body.get("location_id"), mat["id"])
    avail_here = _f(await stock_service.get_onhand(mat["id"], db=db))
    stock_here = next((x["qty"] for x in await _stock_locations(db, mat["id"])
                       if x["location_id"] == loc_id), 0.0)

    rolls_in = body.get("roll_ids") or []
    roll_docs = []
    # FASE H-6: kain yang dilacak per gulungan harus punya gulungan bersisa SEBELUM
    # order dibuat — gagal cepat lebih baik daripada order yang mentok saat progres.
    open_rolls = await _assert_rolls_available(db, mat, f"{mat.get('code')} — {mat.get('name')}")
    if rolls_in:
        by_id = {r["id"]: r for r in open_rolls}
        by_no = {str(r.get("roll_no", "")): r for r in open_rolls}
        unknown = []
        for rid in rolls_in:
            r = by_id.get(str(rid)) or by_no.get(str(rid))
            if not r:
                unknown.append(str(rid))
                continue
            if any(x["roll_id"] == r["id"] for x in roll_docs):
                continue
            roll_docs.append({
                "roll_id": r["id"], "roll_no": r.get("roll_no", ""),
                "uom": r.get("uom", ""),
                "remaining": round(fabric_roll_engine.remaining_of(r), 3),
                "consumed_qty": 0.0,
            })
        if unknown:
            raise HTTPException(400, (
                f"Gulungan {', '.join(unknown)} bukan milik kain {mat.get('code')} atau sudah "
                f"habis. Gulungan yang bisa dipilih: {_roll_hint(open_rolls)}"))
        picked_total = sum(x["remaining"] for x in roll_docs)
        if picked_total + 0.0001 < planned_input:
            raise HTTPException(400, (
                f"Sisa gulungan terpilih {picked_total:,.2f} {roll_docs[0]['uom']} lebih kecil "
                f"dari rencana pemakaian {planned_input:,.2f} {unit}. Tambah gulungan atau "
                "turunkan rencana pemakaiannya."))
    elif open_rolls:
        # Tidak memilih di awal masih boleh (gulungan dipilih saat lapor progres),
        # tetapi order menyimpan pengingat bahwa gulungan WAJIB ditunjuk nanti.
        roll_docs = []

    number = await gen_prefixed_number(db, ORDERS, "number", f"CUT-{_now():%Y}-", 4)
    doc = {
        "id": _uid(),
        "number": number,
        "status": STATUS_DRAFT,
        # input
        "input_material_id": mat["id"],
        "input_material_code": mat.get("code", ""),
        "input_material_name": mat.get("name", ""),
        "input_unit": unit,
        "input_color": mat.get("color", ""),
        "input_unit_cost": _f(mat.get("unit_cost")),
        "planned_input_qty": round(planned_input, 4),
        "consumed_input_qty": 0.0,
        "roll_ids": roll_docs,
        "roll_required": bool(open_rolls),
        "location_id": loc_id,
        "location_name": loc_name,
        "stock_at_create": round(stock_here, 4),
        "stock_total_at_create": round(avail_here, 4),
        # output
        # output — identitasnya DARI MASTER (model + varian), bukan ketikan
        "style_sku": style_sku,
        "style_name": style_name,
        "model_id": model_id,
        "model_code": style_sku,
        "model_name": style_name,
        "variant_id": (variant or {}).get("id") or "",
        "variant_sku": (variant or {}).get("sku") or "",
        "size_id": (variant or {}).get("size_id") or (size_doc or {}).get("id") or "",
        "color_id": (variant or {}).get("color_id") or "",
        "output_color": output_color,
        "output_size": output_size,
        "output_unit": OUTPUT_UNIT,
        "output_material_id": None,
        "output_material_code": (body.get("output_material_code") or "").strip().upper(),
        "output_material_name": "",
        "planned_output_qty": round(planned_output, 4),
        "produced_qty": 0.0,
        "waste_qty": 0.0,
        "output_unit_cost": 0.0,
        # meta
        "target_date": body.get("target_date") or None,
        "notes": body.get("notes") or "",
        "created_by": user["id"], "created_by_name": user.get("name", ""),
        "created_at": _now(), "updated_at": _now(),
        "started_at": None, "completed_at": None,
    }
    await db[ORDERS].insert_one(dict(doc))
    await log_activity(user["id"], user.get("name", ""), "create", "cutting.order", number)
    await _enrich(db, doc)
    return serialize_doc(doc)


@router.put("/orders/{oid}")
async def update_order(oid: str, request: Request):
    user = await _require_cutting_user(request)
    db = get_db()
    o = await _get_order(db, oid)
    if o["status"] != STATUS_DRAFT:
        raise HTTPException(400, "Hanya cutting berstatus draft yang bisa diubah.")
    body = await request.json()
    patch: dict = {"updated_at": _now()}
    # Style/produk hanya boleh berganti lewat MASTER (model + varian) — bukan
    # ketikan bebas, agar order draft tidak bisa "lepas" dari master produk.
    if "model_id" in body:
        model = await db.rahaza_models.find_one(
            {"id": (body.get("model_id") or "").strip()}, {"_id": 0})
        if not model:
            raise HTTPException(404, "Model produk tidak ditemukan di master.")
        variant = None
        if (body.get("variant_id") or "").strip():
            variant = await db.rahaza_model_variants.find_one(
                {"id": body["variant_id"].strip(), "model_id": model["id"]}, {"_id": 0})
            if not variant:
                raise HTTPException(400, "Varian (warna/size) bukan milik model yang dipilih.")
        patch.update({
            "model_id": model["id"], "model_code": model.get("code", ""),
            "model_name": model.get("name", ""),
            "style_name": model.get("name", ""), "style_sku": model.get("code", ""),
            "variant_id": (variant or {}).get("id") or "",
            "variant_sku": (variant or {}).get("sku") or "",
            "size_id": (variant or {}).get("size_id") or "",
            "color_id": (variant or {}).get("color_id") or "",
        })
        if variant:
            patch["output_color"] = variant.get("color_name") or variant.get("color") or ""
            patch["output_size"] = variant.get("size_code") or ""
    elif any(k in body for k in ("style_name", "style_sku")):
        raise HTTPException(400, (
            "Nama style tidak bisa diketik langsung — kirim `model_id` dari Master Produk "
            "supaya BOM & produksi tetap mengenali produknya."))
    for k in ("notes", "target_date"):
        if k in body:
            patch[k] = (body.get(k) or "") if isinstance(body.get(k), str) else body.get(k)
    if "planned_input_qty" in body:
        v = _f(body["planned_input_qty"])
        if v <= 0:
            raise HTTPException(400, "Rencana pemakaian kain harus > 0.")
        patch["planned_input_qty"] = round(v, 4)
    if "planned_output_qty" in body:
        v = _f(body["planned_output_qty"])
        if v <= 0:
            raise HTTPException(400, "Rencana hasil potongan harus > 0.")
        patch["planned_output_qty"] = round(v, 4)
    if "location_id" in body:
        lid, lname = await _default_location(db, body.get("location_id"), o.get("input_material_id"))
        patch["location_id"], patch["location_name"] = lid, lname
    await db[ORDERS].update_one({"id": oid}, {"$set": patch})
    await log_activity(user["id"], user.get("name", ""), "update", "cutting.order", o["number"])
    return serialize_doc(await _enrich(db, await _get_order(db, oid)))


@router.delete("/orders/{oid}")
async def delete_order(oid: str, request: Request):
    user = await _require_cutting_user(request)
    db = get_db()
    o = await _get_order(db, oid)
    if o["status"] != STATUS_DRAFT:
        raise HTTPException(400, "Hanya draft yang bisa dihapus. Gunakan Batalkan untuk yang lain.")
    # SESI #32 — penjaga yang sama seperti `cancel`: draft yang (karena data lama)
    # sudah punya master potongan tidak boleh meninggalkannya jadi yatim.
    res_panel = await cut_panel_health.remove_if_unused(
        db, panel_id=o.get("output_material_id") or "", order_id=oid, user=user)
    await db[ORDERS].delete_one({"id": oid})
    await log_activity(user["id"], user.get("name", ""), "delete", "cutting.order", o["number"])
    out = {"ok": True}
    if res_panel and res_panel.get("removed"):
        out["notice"] = (f"Master potongan {res_panel['code']} ikut dibersihkan "
                         f"(belum pernah dipakai).")
    elif res_panel and res_panel.get("reason"):
        out["notice"] = (f"Master potongan {res_panel['code']} DIPERTAHANKAN — "
                         f"{res_panel['reason']}")
    return out


# ═════════════════════════════════════════════════════════════════════════════
# STATE TRANSITIONS
# ═════════════════════════════════════════════════════════════════════════════
@router.post("/orders/{oid}/start")
async def start_order(oid: str, request: Request):
    """draft ➜ in_progress. Sekalian membuat master material POTONGAN (output)."""
    user = await _require_cutting_user(request)
    db = get_db()
    o = await _get_order(db, oid)
    if o["status"] != STATUS_DRAFT:
        raise HTTPException(400, f"Status '{o['status']}' tidak bisa di-start.")

    # VALIDASI PER-LOKASI (perbaikan bug QA-1): stok disimpan per (material, lokasi),
    # sementara dulu di sini hanya dicek TOTAL lintas lokasi. Akibatnya order lolos
    # start tapi gagal saat progress ("tersedia 0.0") karena lokasi order ternyata
    # bukan lokasi yang memegang stok. Sekarang: kalau lokasi order kosong tapi ada
    # gudang lain yang punya stok, order otomatis diarahkan ke gudang tersebut.
    locs = await _stock_locations(db, o["input_material_id"])
    total = sum(x["qty"] for x in locs)
    if total <= 0:
        raise HTTPException(
            400, f"Stok kain {o['input_material_code']} kosong di semua gudang "
                 f"(0 {o['input_unit']}). Catat penerimaan barang di Gudang dulu.")
    here = next((x for x in locs if x["location_id"] == o.get("location_id")), None)
    moved_to = None
    if not here:
        best = locs[0]
        await db[ORDERS].update_one({"id": oid}, {"$set": {
            "location_id": best["location_id"],
            "location_name": best["location_name"],
        }})
        o["location_id"], o["location_name"] = best["location_id"], best["location_name"]
        moved_to = best["location_name"]

    out_mat = await _ensure_output_material(db, o, user)
    await db[ORDERS].update_one({"id": oid}, {"$set": {
        "status": STATUS_IN_PROGRESS,
        "output_material_id": out_mat["id"],
        "output_material_code": out_mat["code"],
        "output_material_name": out_mat["name"],
        "started_at": _now(), "updated_at": _now(),
    }})
    await log_activity(user["id"], user.get("name", ""), "start", "cutting.order", o["number"])
    out = await _enrich(db, await _get_order(db, oid))
    if moved_to:
        out["notice"] = f"Lokasi cutting dialihkan ke '{moved_to}' karena di sanalah stok kain berada."
    return serialize_doc(out)


@router.post("/orders/{oid}/progress")
async def add_progress(oid: str, request: Request):
    """Catat hasil potong sebagian: kain berkurang, potongan bertambah (SSOT stok)."""
    user = await _require_cutting_user(request)
    db = get_db()
    o = await _get_order(db, oid)
    if o["status"] != STATUS_IN_PROGRESS:
        raise HTTPException(400, "Progres hanya bisa diinput saat status 'in_progress'.")

    body = await request.json()
    input_used = _f(body.get("input_consumed"))
    output_qty = _f(body.get("output_qty"))
    waste = _f(body.get("waste_qty"))
    if input_used <= 0:
        raise HTTPException(400, "Kain terpakai harus > 0.")
    if output_qty <= 0:
        raise HTTPException(400, "Jumlah potongan jadi harus > 0.")

    # ── 2026-08-05 · SATUAN HITUNG OPERATOR (opsional, `input_uom`) ───────────
    # Kain dicatat di satuan order (`input_unit`, mis. "kg" atau "m"), tetapi
    # operator lantai sering menghitung dalam satuan lain (rol, gram, yard).
    # Bila `input_uom` dikirim, qty diterjemahkan DULU ke satuan order supaya
    # stok, sisa roll, dan akumulasi progres tetap satu bahasa.
    _op_uom = (body.get("input_uom") or "").strip().lower()
    _order_uom = (o.get("input_unit") or "").strip().lower()
    uom_applied = None
    if _op_uom and _op_uom != _order_uom:
        mat_in = await db.rahaza_materials.find_one({"id": o["input_material_id"]}, {"_id": 0})
        f_op, base_u, st_op, note_op = _bom_uom.line_factor(mat_in, _op_uom)
        if st_op not in ("base", "uom", "global", "fabric"):
            raise HTTPException(400, note_op or (
                f"Satuan '{_op_uom}' tidak bisa dikonversi ke '{_order_uom}'."))
        f_ord, _b, st_ord, _n = _bom_uom.line_factor(mat_in, _order_uom)
        if st_ord not in ("base", "uom", "global", "fabric") or not f_ord:
            f_ord = 1.0
        converted = round(float(input_used) * float(f_op) / float(f_ord), 4)
        if converted <= 0:
            raise HTTPException(400, "Hasil konversi kain terpakai harus > 0.")
        uom_applied = {"input_qty": input_used, "input_uom": _op_uom,
                       "qty_order_unit": converted, "order_unit": _order_uom,
                       "factor": float(f_op), "source": st_op}
        input_used = converted

    loc_id = o["location_id"]
    actor = await _actor(user)
    ref = {"type": "cutting", "id": o["id"], "no": o["number"]}

    # ── FASE H-6: rencana pemakaian GULUNGAN dihitung DULU (sebelum stok dipotong) ──
    # Kalau gulungan tidak dipilih / sisanya tidak cukup, laporan ditolak di sini —
    # bukan setelah stok kain sudah turun tanpa gulungan yang berkurang.
    roll_plan, roll_info = await _plan_roll_consumption(db, o, body, input_used)

    # 1) Kurangi stok KAIN (guarded — tidak boleh minus)
    try:
        await stock_service.issue(o["input_material_id"], loc_id, input_used,
                                  ref=ref, actor=actor, db=db)
    except InsufficientStock as e:
        locs = await _stock_locations(db, o["input_material_id"])
        where = ", ".join(f"{x['location_name']}: {x['qty']}" for x in locs) or "tidak ada stok di gudang manapun"
        raise HTTPException(
            400, f"Stok kain tidak cukup di '{o.get('location_name')}': minta {e.requested}, "
                 f"tersedia {e.available} {o['input_unit']}. Sebaran stok — {where}.")

    # 2) Tambah stok POTONGAN
    out_mat_id = o.get("output_material_id")
    if not out_mat_id:
        out_mat = await _ensure_output_material(db, o, user)
        out_mat_id = out_mat["id"]
        await db[ORDERS].update_one({"id": oid}, {"$set": {
            "output_material_id": out_mat["id"],
            "output_material_code": out_mat["code"],
            "output_material_name": out_mat["name"],
        }})
    # SESI #32 — stok potongan SEBELUM penambahan (dipakai rata-rata bergerak)
    panel_qty_before = await cut_panel_value.panel_onhand(db, out_mat_id)
    await stock_service.add(out_mat_id, loc_id, output_qty, ref=ref, actor=actor, db=db,
                            meta={"material_code": o.get("output_material_code"),
                                  "material_name": o.get("output_material_name"),
                                  "material_type": "fabric", "unit": OUTPUT_UNIT,
                                  "category": OUTPUT_CATEGORY})

    # ── SESI #32: NILAI KAIN YANG KELUAR **BERPINDAH** JADI NILAI POTONGAN ────
    # Dulu master potongan tetap Rp0 sampai order di-complete, dan angka complete
    # memakai harga kain yang di-snapshot saat order DIBUAT (harga basi). Sekarang
    # nilainya lahir di sini, dengan harga kain SAAT INI, lewat rata-rata bergerak
    # (SSOT core.accessory_valuation) supaya stok potongan lama tidak terhapus
    # angkanya. `panel_qty_before` WAJIB dibaca SEBELUM `stock_service.add` di
    # atas — kalau dibaca sesudahnya, qty masuk ikut jadi penyebut (pelajaran GR
    # sesi #30). Kain yang belum punya harga TIDAK dipaksa jadi 0 yang seolah
    # benar: potongannya ditandai `unvalued` dan alasannya dikembalikan ke layar.
    value_trace = await cut_panel_value.apply_progress_value(
        db, fabric_id=o["input_material_id"], panel_id=out_mat_id,
        input_consumed=input_used, output_qty=output_qty,
        qty_before=panel_qty_before, actor=actor,
        reference=o.get("number", ""))

    # 3) Roll fisik — SATU pintu pemakaian gulungan (`fabric_roll_engine.consume_rolls`)
    #    FIFO menurut nomor roll. Sebelum H-6 blok ini mengurangi roll secara manual dan
    #    hanya kalau `roll_id` dikirim; kini rencananya sudah tervalidasi di atas.
    roll_consumption: list = []
    if roll_plan:
        roll_consumption = await fabric_roll_engine.consume_rolls(
            db, roll_plan,
            {"type": "cutting", "id": o["id"], "number": o["number"],
             "notes": f"Cutting {o['number']} — {o.get('style_name', '')}".strip(" —")},
            user)
        for p in roll_consumption:
            hit = await db[ORDERS].update_one(
                {"id": oid, "roll_ids.roll_id": p["roll_id"]},
                {"$inc": {"roll_ids.$.consumed_qty": round(p["qty"], 3)},
                 "$set": {"roll_ids.$.remaining": p["remaining_after"]}},
            )
            if not hit.matched_count:
                # Gulungan yang baru dipilih saat progres ikut dicatat di order supaya
                # riwayat "gulungan mana dipakai order ini" tetap lengkap.
                await db[ORDERS].update_one({"id": oid}, {"$push": {"roll_ids": {
                    "roll_id": p["roll_id"], "roll_no": p.get("roll_no", ""),
                    "uom": p.get("uom", ""), "remaining": p["remaining_after"],
                    "consumed_qty": round(p["qty"], 3),
                }}})
    roll_id = (roll_consumption[0]["roll_id"] if roll_consumption
               else ((body.get("roll_id") or "").strip() or None))

    prog = {
        "id": _uid(),
        "cutting_order_id": oid,
        "cutting_number": o["number"],
        "input_consumed": round(input_used, 4),
        "output_qty": round(output_qty, 4),
        "waste_qty": round(waste, 4),
        "roll_id": roll_id,
        # Jejak audit H-6: gulungan mana dipakai berapa untuk laporan progres ini.
        "roll_ids": [p["roll_id"] for p in roll_consumption],
        "roll_numbers": [p.get("roll_no", "") for p in roll_consumption],
        "roll_consumption": roll_consumption,
        "roll_required": bool(roll_info.get("tracked")),
        "note": body.get("note") or "",
        # FASE H-6b: lokasi ASAL kain dicatat DI progres (bukan hanya di order)
        # supaya dokumen Pengeluaran Material menyebut gudang yang sebenarnya
        # dipotong, walau lokasi order berubah setelahnya.
        "location_id": loc_id,
        "location_name": o.get("location_name", ""),
        "uom_applied": uom_applied,   # jejak konversi satuan operator (bila ada)
        # SESI #32 — jejak NILAI: harga kain saat itu, nilai kain yang keluar,
        # dan HPP potongan sebelum→sesudah. Inilah yang membuat `complete` tidak
        # perlu lagi menebak dengan harga basi, dan yang dibaca gate INV-F37.
        "fabric_unit_cost": value_trace.get("fabric_unit_cost", 0.0),
        "value_out": value_trace.get("value_out", 0.0),
        "cost_per_pcs_in": value_trace.get("cost_per_pcs_in", 0.0),
        "panel_unit_cost_before": value_trace.get("panel_unit_cost_before", 0.0),
        "panel_unit_cost_after": value_trace.get("panel_unit_cost_after", 0.0),
        "panel_qty_before": value_trace.get("panel_qty_before", 0.0),
        "value_status": value_trace.get("value_status", "unvalued"),
        "value_note": value_trace.get("value_note", ""),
        "created_by": user["id"], "created_by_name": user.get("name", ""),
        "created_at": _now(),
    }
    await db[PROGRESS].insert_one(dict(prog))

    # ── FASE H-6b: TERBITKAN DOKUMEN "PENGELUARAN MATERIAL" (`cutting_issue`) ──
    # Stok & gulungan sudah dipotong di atas — modul ini HANYA membuat dokumen +
    # baris kartu stok supaya arus keluar Cutting ikut tampil di satu daftar
    # "Pengeluaran Material". Kegagalannya TIDAK membatalkan potong kain (barang
    # sudah keluar), tetapi juga tidak boleh hilang diam-diam: progres tanpa
    # dokumen muncul di `GET /api/cutting/issue-docs/missing` + bisa diterbitkan
    # ulang lewat `POST /api/cutting/issue-docs/backfill`.
    mi_doc = None
    mi_error = ""
    try:
        mi_doc = await cutting_material_issue.doc_for_progress(db, o, prog, user)
    except Exception as e:  # noqa: BLE001
        mi_error = str(e)
        log.exception("H-6b: dokumen MI gagal diterbitkan untuk progres cutting %s",
                      prog["id"])
    if mi_doc:
        prog["material_issue_id"] = mi_doc["id"]
        prog["material_issue_number"] = mi_doc.get("mi_number", "")
    await db[ORDERS].update_one({"id": oid}, {
        "$inc": {"consumed_input_qty": round(input_used, 4),
                 "produced_qty": round(output_qty, 4),
                 "waste_qty": round(waste, 4)},
        "$set": {"updated_at": _now()},
    })
    await log_activity(user["id"], user.get("name", ""), "progress", "cutting.order", o["number"])
    out = await _enrich(db, await _get_order(db, oid))
    # Umpan balik langsung ke layar: gulungan mana berkurang berapa & sisanya.
    out["last_progress"] = {
        "input_consumed": round(input_used, 4),
        "output_qty": round(output_qty, 4),
        "roll_consumption": roll_consumption,
        "roll_required": bool(roll_info.get("tracked")),
        # FASE H-6b — nomor dokumen arus keluar kain (Pengeluaran Material)
        "material_issue_id": (mi_doc or {}).get("id"),
        "material_issue_number": (mi_doc or {}).get("mi_number", ""),
        # SESI #32 — nilai yang berpindah (kain → potongan)
        "fabric_unit_cost": value_trace.get("fabric_unit_cost", 0.0),
        "value_out": value_trace.get("value_out", 0.0),
        "cost_per_pcs_in": value_trace.get("cost_per_pcs_in", 0.0),
        "panel_unit_cost_before": value_trace.get("panel_unit_cost_before", 0.0),
        "panel_unit_cost_after": value_trace.get("panel_unit_cost_after", 0.0),
        "value_status": value_trace.get("value_status", "unvalued"),
        "value_note": value_trace.get("value_note", ""),
    }
    notices = []
    if value_trace.get("value_status") == "valued":
        notices.append(
            f"Nilai kain {value_trace.get('value_out', 0):,.0f} berpindah ke potongan ⇒ HPP "
            f"potongan {value_trace.get('panel_unit_cost_before', 0):,.0f} → "
            f"{value_trace.get('panel_unit_cost_after', 0):,.0f}/pcs (rata-rata bergerak).")
    else:
        out["value_warning"] = value_trace.get("value_note") or ""
        if out["value_warning"]:
            notices.append(out["value_warning"])
    if mi_doc and mi_doc.get("mi_number"):
        notices.append(
            f"Dokumen Pengeluaran Material {mi_doc['mi_number']} diterbitkan "
            f"(arus keluar kain tampil di layar Pengeluaran Material).")
    elif mi_error:
        out["mi_warning"] = (
            "Kain & gulungan SUDAH berkurang, tetapi dokumen Pengeluaran Material "
            f"gagal diterbitkan: {mi_error}. Buka Portal Cutting → kartu 'Progres "
            "tanpa dokumen MI' lalu tekan 'Terbitkan dokumen' untuk melengkapinya.")
        notices.append(out["mi_warning"])
    if roll_consumption:
        notices.append("Gulungan dipakai: " + ", ".join(
            f"{p.get('roll_no')} −{p['qty']:,.2f} (sisa {p['remaining_after']:,.2f})"
            for p in roll_consumption))
    if notices:
        out["notice"] = " ".join(notices)
    return serialize_doc(out)


@router.post("/orders/{oid}/complete")
async def complete_order(oid: str, request: Request):
    """in_progress ➜ completed + rekap NILAI potongan (SESI #32).

    Nilai TIDAK lagi dihitung ulang dengan harga kain yang di-snapshot saat order
    dibuat (harga basi). Angka order = **Σ nilai kain yang benar-benar keluar**
    pada tiap laporan progres (`cutting_progress.value_out`), dan master potongan
    TIDAK ditimpa karena HPP-nya sudah lahir per progres lewat rata-rata bergerak.
    Order LAMA (progresnya dilaporkan sebelum sesi #32, jadi tidak punya jejak
    nilai) tetap dilayani: dipakai cara lama sebagai cadangan, dan master yang
    masih Rp0 diisi supaya nilai persediaannya tidak nol selamanya.
    """
    user = await _require_cutting_user(request)
    db = get_db()
    o = await _get_order(db, oid)
    if o["status"] != STATUS_IN_PROGRESS:
        raise HTTPException(400, f"Status '{o['status']}' tidak bisa di-complete.")
    produced = _f(o.get("produced_qty"))
    if produced <= 0:
        raise HTTPException(400, "Belum ada progres. Input hasil potong dulu sebelum menyelesaikan.")

    consumed = _f(o.get("consumed_input_qty"))
    mat = await db.rahaza_materials.find_one({"id": o["input_material_id"]}, {"_id": 0}) or {}
    totals = await cut_panel_value.order_value_totals(db, oid)
    value_source = "progress_trace"
    total_cost = _f(totals.get("value_total"))
    unit_cost_in = _f(mat.get("unit_cost")) or _f(o.get("input_unit_cost"))
    if not totals.get("complete") or total_cost <= 0:
        # cadangan untuk order lama / kain belum bernilai
        value_source = "fallback_unit_cost"
        total_cost = consumed * unit_cost_in
    out_unit_cost = round(total_cost / produced, 2) if produced > 0 else 0.0

    panel = await db.rahaza_materials.find_one(
        {"id": o.get("output_material_id")}, {"_id": 0}) if o.get("output_material_id") else None
    panel_cost = _f((panel or {}).get("unit_cost"))
    panel_filled = False
    if panel and panel_cost <= 0 < out_unit_cost:
        # Order LAMA: nilainya belum pernah berpindah per progres ⇒ isi sekali di
        # sini supaya persediaan potongan tidak bernilai nol selamanya.
        await db.rahaza_materials.update_one(
            {"id": panel["id"]},
            {"$set": {"unit_cost": out_unit_cost, "value_status": "valued",
                      "value_source": "cutting_complete_backfill",
                      "value_note": (f"Diisi saat order {o.get('number')} diselesaikan "
                                     f"(progres lama tanpa jejak nilai)."),
                      "updated_at": _now()}},
        )
        panel_filled = True

    await db[ORDERS].update_one({"id": oid}, {"$set": {
        "status": STATUS_COMPLETED,
        "output_unit_cost": out_unit_cost,
        "total_input_cost": round(total_cost, 2),
        "value_source": value_source,
        "completed_at": _now(), "updated_at": _now(),
    }})
    await log_activity(user["id"], user.get("name", ""), "complete", "cutting.order", o["number"])
    out = await _enrich(db, await _get_order(db, oid))
    notes = []
    if value_source == "progress_trace":
        notes.append(
            f"Nilai potongan order ini {total_cost:,.0f} (Σ nilai kain yang keluar) ⇒ "
            f"{out_unit_cost:,.0f}/pcs. HPP master potongan tidak ditimpa karena sudah "
            f"dihitung rata-rata bergerak tiap progres.")
    elif unit_cost_in <= 0:
        notes.append(
            f"HPP potongan = 0 karena harga satuan kain {o.get('input_material_code')} belum "
            f"ada. Harga kain lahir dari pembelian: buat PO lalu terima barang di Gudang, "
            f"atau perbaiki lewat Gudang → Valuasi HPP.")
    else:
        notes.append(
            f"Progres order ini dilaporkan sebelum jejak nilai ada, jadi nilai dihitung dari "
            f"harga kain sekarang ({unit_cost_in:,.0f}/{o.get('input_unit')}) × "
            f"{consumed:g} = {total_cost:,.0f}.")
    if panel_filled:
        notes.append(f"HPP master potongan diisi {out_unit_cost:,.0f}/pcs (sebelumnya kosong).")
    out["notice"] = " ".join(notes)
    return serialize_doc(out)


@router.post("/orders/{oid}/cancel")
async def cancel_order(oid: str, request: Request):
    user = await _require_cutting_user(request)
    db = get_db()
    o = await _get_order(db, oid)
    if o["status"] in (STATUS_COMPLETED, STATUS_CANCELLED):
        raise HTTPException(400, f"Status '{o['status']}' tidak bisa dibatalkan.")
    n = await db[PROGRESS].count_documents({"cutting_order_id": oid})
    if n > 0:
        raise HTTPException(
            400, "Sudah ada progres (stok sudah bergerak). Selesaikan cutting, "
                 "lalu koreksi lewat Penyesuaian Stok di Gudang bila perlu.")
    body = {}
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — BODY OPSIONAL: pembatalan boleh dikirim
        # tanpa body sama sekali (mis. tombol "Batalkan" tanpa alasan). Ini bukan
        # kegagalan, jadi memang tidak ada yang perlu dicatat — `reason` di bawah
        # akan menjadi string kosong. Sengaja dibiarkan tanpa log agar tidak
        # membanjiri log dengan kejadian normal.
        body = {}
    await db[ORDERS].update_one({"id": oid}, {"$set": {
        "status": STATUS_CANCELLED,
        "cancel_reason": (body or {}).get("reason") or "",
        "updated_at": _now(),
    }})
    # ── SESI #32 · PENJAGA ANTI-POTONGAN-YATIM ───────────────────────────────
    # `start` melahirkan master POTONGAN. Sebelum ini, membatalkan order (sah
    # selama belum ada progres) meninggalkan master itu tanpa induk SELAMANYA:
    # muncul di Master Item & daftar Master Potongan, nilainya Rp0, menunjuk order
    # yang statusnya dibatalkan. Sekarang master yang BELUM PERNAH BERGERAK
    # (0 stok, 0 buku besar, 0 kartu stok, tidak dirujuk dokumen apa pun) ikut
    # dibuang, dan yang sudah pernah bergerak DIPERTAHANKAN dengan alasan yang
    # dikatakan — bukan dihapus diam-diam (stok tidak boleh jadi hantu).
    panel_note = ""
    res_panel = await cut_panel_health.remove_if_unused(
        db, panel_id=o.get("output_material_id") or "", order_id=oid, user=user)
    if res_panel and res_panel.get("removed"):
        await db[ORDERS].update_one({"id": oid}, {"$unset": {"output_material_id": "",
                                                            "output_material_code": "",
                                                            "output_material_name": ""}})
        panel_note = (f"Master potongan {res_panel['code']} ikut dibersihkan karena belum "
                      f"pernah dipakai (0 stok, tanpa kartu stok).")
    elif res_panel and res_panel.get("reason"):
        panel_note = (f"Master potongan {res_panel['code']} DIPERTAHANKAN — "
                      f"{res_panel['reason']}")
    await log_activity(user["id"], user.get("name", ""), "cancel", "cutting.order", o["number"])
    out = await _enrich(db, await _get_order(db, oid))
    if panel_note:
        out["notice"] = panel_note
    return serialize_doc(out)
