"""
warehouse.py — Legacy Warehouse Module (di-include via server.py, bridge /api/wms/legacy/*).

STATUS (FASE F, 2026-07-25): masih LIVE untuk beberapa handler yang di-bridge
`wms_legacy.py`, TETAPI seluruh ketergantungan ke ledger legacy sudah DIPUTUS:
  - LIVE (dipakai UI via /api/wms/legacy/*):
      * /locations (GET) → KANONIK (FASE F+): `location_resolver.list_storage_locations` (wh_zones +
        rahaza storage) + `wh_positions`. create/update/delete_location → 410 (SSOT = Struktur Gudang).
        `warehouse_locations` legacy DI-RETIRE (dropdown ReceivingModule pindah ke /api/rahaza/storage-locations).
      * /receiving[/{id}] (GR, 3-way match, QC) → koleksi `warehouse_receiving` (DIPERTAHANKAN).
      * /dashboard-kpi, /dashboard, /stock, /stock/summary, /movements → kini baca KANONIK
        (`rahaza_material_stock` + `rahaza_stock_ledger`), BUKAN `warehouse_stock`/`warehouse_movements`.
  - DIHAPUS (FASE F): endpoint legacy `/putaway` (transfer) & `/opname` (variance) — penulis
    ledger ganda `warehouse_stock`/`warehouse_movements` (INV-11). Kanonik = wms_putaway.py + wms_opname3.py.
  - Koleksi `warehouse_stock`/`warehouse_movements`/`warehouse_putaway`/`warehouse_opname` kini
    TANPA writer/reader → DROP via scripts/migrate_drop_warehouse_ledger_legacy.py.
  - Inbound GR menambah stok via `core.stock_service.add` (FASE E2) + `_record_material_movement`.

JANGAN tambah tulisan stok tersebar di sini — pakai `core/stock_service`.
"""
# ruff: noqa: ERA001
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from utils.counters import next_counter, gen_prefixed_number
from core import stock_service  # FASE E2: satu pintu inbound (add) + ledger kanonik
from core import location_resolver  # FASE F+: master lokasi KANONIK (wh_zones + rahaza storage)
from core import quarantine  # FASE 6 (INV-8): qty reject GR → lokasi KARANTINA (blocked)
from core import fabric_roll_engine  # FASE H-5: roll kain LAHIR dari penerimaan (nomor otomatis)
from core import accessory_valuation  # 2026-08-21: HPP terbentuk dari HARGA PEMBELIAN (WAC)
from datetime import datetime, timezone
import uuid
import logging
import re

logger = logging.getLogger(__name__)

# ⚠️  DEPRECATION NOTICE (Phase 3 — Dual API Conflict Resolution)
# This router is preserved for backward-compatibility only.
# All NEW frontend code MUST call the canonical mirror at /api/wms/legacy/*
# (see routes/wms_legacy.py — same handlers, same DB collections).
# Frontend migration completed for: LocationsModule, PutAwayModule,
# OpnameModule, ReceivingModule, WarehouseDashboard, MaklonMaterialIssuePanel.
# Once external clients (if any) finish migration, this entire file can
# be safely removed.
router = APIRouter(prefix="/api/warehouse", tags=["warehouse-legacy-deprecated"])


def new_id(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)


# ── Sprint 1.1: Sync bridge helper ────────────────────────────────────────────
# FASE F (2026-07-25): helper `_sync_to_material_stock` DIHAPUS.
# Satu-satunya penulis stok kini `core/stock_service`. Endpoint legacy
# putaway-transfer & opname-variance yang memakainya juga DIHAPUS di bawah.


async def _record_material_movement(db, material_id: str, location_id: str, location_name: str,
                                     qty: float, unit: str, reference_type: str,
                                     reference_id: str, reference_number: str,
                                     notes: str, user: dict, unit_cost: float = 0.0,
                                     material_name: str = None) -> dict:
    """Record a rahaza_material_movement for audit trail + stock module."""
    doc = {
        "id": new_id(),
        "material_id": material_id,
        "material_name": material_name,
        "unit_cost": float(unit_cost or 0),
        "location_id": location_id,
        "location_name": location_name,
        "type": "receive",
        "qty": float(qty),
        "unit": unit,
        "reference_type": reference_type,
        "reference_id": reference_id,
        "reference_number": reference_number,
        "notes": notes,
        "created_by": user["id"],
        "created_by_name": user.get("name", "-"),
        "created_at": now(),
    }
    await db.rahaza_material_movements.insert_one(dict(doc))
    return doc


# ── Locations / Bin ───────────────────────────────────────────────────────────

@router.get("/locations")
async def get_locations(request: Request):
    """FASE F+ (2026-07-25): master lokasi KANONIK. Sumber SSOT:
    `location_resolver.list_storage_locations` (wh_zones + rahaza storage) + `wh_positions` (bin).
    TIDAK lagi baca `warehouse_locations` (di-drop). Konsumen UI (ReceivingModule) kini pakai
    /api/rahaza/storage-locations langsung; endpoint ini shim kompat via bridge."""
    await require_auth(request)
    db = get_db()
    canonical = await location_resolver.list_storage_locations(db)
    for loc in canonical:
        loc.setdefault("source", "rahaza_location")
    positions = await db.wh_positions.find({}, {"_id": 0}).sort(
        [("building_code", 1), ("zone_code", 1), ("rack_code", 1), ("shelf_no", 1), ("slot_no", 1)]
    ).to_list(1000)
    mapped = []
    for p in positions:
        path = "/".join([str(p.get(k, "")) for k in ("building_code", "zone_code", "rack_code") if p.get(k)])
        mapped.append({
            "id": p.get("id"),
            "code": p.get("barcode") or p.get("label") or path,
            "name": p.get("label") or path or p.get("barcode", ""),
            "type": "position",
            "zone": p.get("zone_code", ""),
            "aisle": p.get("rack_code", ""),
            "bay": str(p.get("shelf_no", "")),
            "level": str(p.get("slot_no", "")),
            "capacity": 0,
            "active": p.get("status") != "inactive",
            "source": "wh_positions",
            "status": p.get("status", ""),
        })
    return serialize_doc(canonical + mapped)


_LOC_DEPRECATED = (
    "Endpoint dihapus (FASE F+, 2026-07-25). Kelola lokasi via Struktur Gudang "
    "(SSOT: wh_buildings/wh_zones/wh_racks) atau master rahaza_locations. "
    "`warehouse_locations` legacy sudah di-retire."
)


@router.post("/locations")
async def create_location(request: Request):
    """DEPRECATED (FASE F+) — 410. SSOT lokasi = Struktur Gudang / rahaza_locations."""
    await require_auth(request)
    raise HTTPException(410, _LOC_DEPRECATED)


@router.put("/locations/{location_id}")
async def update_location(location_id: str, request: Request):
    """DEPRECATED (FASE F+) — 410. SSOT lokasi = Struktur Gudang / rahaza_locations."""
    await require_auth(request)
    raise HTTPException(410, _LOC_DEPRECATED)


@router.delete("/locations/{location_id}")
async def delete_location(location_id: str, request: Request):
    """DEPRECATED (FASE F+) — 410. SSOT lokasi = Struktur Gudang / rahaza_locations."""
    await require_auth(request)
    raise HTTPException(410, _LOC_DEPRECATED)


# ── Goods Receiving ─────────────────────────────────────────────────────────

@router.get("/receiving")
async def get_receiving(request: Request):
    await require_auth(request)
    db = get_db()
    receipts = await db.warehouse_receiving.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return serialize_doc(receipts)


@router.get("/receiving/{receipt_id}")
async def get_receipt(receipt_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    receipt = await db.warehouse_receiving.find_one({"id": receipt_id}, {"_id": 0})
    if not receipt:
        raise HTTPException(404, "Receipt not found")
    return serialize_doc(receipt)


@router.post("/receiving")
async def create_receiving(request: Request):
    user = await require_auth(request)
    body = await request.json()
    db = get_db()
    
    # W-4: Atomic counter for receipt_number (unified counters SSOT)
    seq = await next_counter(db, "gr_number", namespace="generic")
    receipt_number = f"GR-{seq:05d}"
    
    # Sprint 2.1: PO reference for 3-way matching (optional but recommended)
    po_id = body.get("po_id") or None
    po_number = body.get("po_number") or ""
    
    receipt = {
        "id": new_id(),
        "receipt_number": receipt_number,
        "source_type": body.get("source_type", "supplier"),
        "source_ref": body.get("source_ref", ""),
        "supplier_name": body.get("supplier_name", ""),
        "location_id": body.get("location_id", ""),
        "location_name": body.get("location_name", ""),
        "status": "draft",
        "items": [],
        "notes": body.get("notes", ""),
        "received_by": user["name"],
        "received_by_id": user["id"],
        # Sprint 2.1: Link to Purchase Order
        "po_id": po_id,
        "po_number": po_number,
        "created_at": now(),
        "updated_at": now(),
    }
    
    for item in body.get("items", []):
        # BUG-guard (numeric bounds): reject negative qty/harga in receiving items.
        try:
            expected_qty = float(item.get("expected_qty", 0) or 0)
            received_qty = float(item.get("received_qty", item.get("qty", item.get("quantity", 0))) or 0)
            rejected_qty = float(item.get("rejected_qty", 0) or 0)
            unit_price = float(item.get("unit_price", item.get("unit_cost", 0)) or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, "qty/harga item penerimaan harus berupa angka.")
        if min(expected_qty, received_qty, rejected_qty, unit_price) < 0:
            raise HTTPException(400, "qty/harga item penerimaan tidak boleh negatif.")
        receipt_item = {
            "id": new_id(),
            "product_name": item.get("product_name", ""),
            "sku": item.get("sku", ""),
            # Sprint 1.1: material_id links to rahaza_materials for sync bridge
            "material_id": item.get("material_id") or None,
            "material_name": item.get("material_name") or item.get("product_name", ""),
            "expected_qty": expected_qty,
            "received_qty": received_qty,
            "rejected_qty": rejected_qty,
            "unit": item.get("unit", "pcs"),
            "inspection_status": item.get("inspection_status") or "pending",
            "inspection_notes": item.get("inspection_notes") or "",
            # FASE 6 (INV-8): alasan reject WAJIB ikut tersimpan — dipakai karantina QC
            # (ringkasan per-alasan & tindak lanjut retur/scrap). Sebelumnya hilang.
            "reject_reasons": item.get("reject_reasons") or [],
            "accepted_qty": float(item.get("accepted_qty") if item.get("accepted_qty") is not None
                                  else max(0.0, received_qty - rejected_qty)),
            "lot_number": item.get("lot_number") or "",
            "expiry_date": item.get("expiry_date") or None,
            # ── FASE H-5: rincian gulungan per baris kain ────────────────────────
            # Disimpan APA ADANYA di draft (belum divalidasi) — pemeriksaan ketat
            # "total roll = qty diterima" dilakukan saat GR di-set 'received', karena
            # qty diterima masih bisa berubah selama masih draft/inspeksi.
            "rolls": [
                {
                    "qty": float(ln.get("qty") or 0),
                    "color_lot": str(ln.get("color_lot") or "").strip(),
                    "notes": str(ln.get("notes") or "").strip(),
                }
                for ln in (item.get("rolls") or []) if isinstance(ln, dict)
            ],
            # Phase 8A: Asset vs Material differentiation
            "item_type": item.get("item_type", "material"),  # "material" or "asset"
            "unit_price": unit_price,  # For asset capitalization
            "asset_category": item.get("asset_category") or None,  # For auto-create fixed asset
        }
        receipt["items"].append(receipt_item)
    
    await db.warehouse_receiving.insert_one(receipt)
    await log_activity(user["id"], user["name"], "create", "warehouse_receiving", f"Created GR {receipt_number}")
    return serialize_doc(receipt)


@router.put("/receiving/{receipt_id}")
async def update_receiving(receipt_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    
    existing = await db.warehouse_receiving.find_one({"id": receipt_id})
    if not existing:
        raise HTTPException(404, "Receipt not found")
    
    body = await request.json()
    updates = {}
    
    if "status" in body:
        updates["status"] = body["status"]
    if "items" in body:
        updates["items"] = body["items"]
    if "notes" in body:
        updates["notes"] = body["notes"]
    # 2026-08-19 — LOKASI TUJUAN boleh ditetapkan saat KONFIRMASI. GR yang lahir
    # dari PO dibuat tanpa lokasi (`location_id: ""`), dan lokasi fisiknya baru
    # diketahui ketika barangnya benar-benar diletakkan. Tanpa ini, stok masuk ke
    # baris berlokasi KOSONG: ada di sistem, tidak ada di rak mana pun, dan
    # Put-Away tidak bisa menemukannya.
    if body.get("location_id"):
        updates["location_id"] = body["location_id"]
        if body.get("location_name"):
            updates["location_name"] = body["location_name"]
    updates["updated_at"] = now()
    
    # ── Sprint 1.1: Dual-ledger sync bridge ────────────────────────────────
    # When transitioning to 'received', update BOTH ledgers:
    #   1. warehouse_stock (bin-level, used by put-away / dashboard)
    #   2. rahaza_material_stock (material-level, used by Material Issue / BOM)
    if body.get("status") == "received" and existing.get("status") != "received":
        items_to_process = body.get("items") or existing.get("items", [])
        loc_name = body.get("location_name") or existing.get("location_name", "")
        loc_id   = body.get("location_id") or existing.get("location_id", "")

        # ── PENJAGA (2026-08-19) — PENERIMAAN KOSONG DITOLAK ────────────────
        # Cacat yang dilaporkan pemilik & terbukti pada GR-00001: `expected_qty=100`
        # tetapi `received_qty=0` walau status sudah `received`. GR yang lahir dari
        # PO selalu dibuat `received_qty=0.0` (benar — barangnya belum dihitung),
        # dan dulu layar detail hanya MENAMPILKAN angka itu tanpa kolom isian, jadi
        # satu-satunya tindakan yang tersedia adalah mengkonfirmasi NOL. Hasilnya
        # penerimaan tercatat "received", PO ikut terhitung, tetapi stok TIDAK
        # bertambah sedikit pun — pembelian mustahil menambah barang.
        #
        # Kolomnya sudah dipasang di layar; penjaga ini menutup pintu yang sama di
        # tingkat API supaya integrasi/skrip pun tidak bisa membuat penerimaan hampa.
        def _qty(v):
            try:
                return float(v or 0)
            except (TypeError, ValueError):
                return 0.0

        _touched = sum(_qty(it.get("received_qty")) + _qty(it.get("rejected_qty"))
                       for it in items_to_process)
        if _touched <= 0:
            raise HTTPException(
                400,
                "Qty diterima masih 0 — penerimaan kosong ditolak. Isi 'Qty Diterima' "
                "pada tiap baris (atau tekan \"Terima semua sesuai PO\") sebelum "
                "dikonfirmasi. Mengkonfirmasi 0 akan mencatat penerimaan tanpa "
                "menambah stok sama sekali.",
            )

        # ── PENJAGA LOKASI (2026-08-19) ─────────────────────────────────────
        # GR dari PO lahir tanpa `location_id`. Kalau dikonfirmasi begitu saja,
        # stok mendarat di baris berlokasi KOSONG: barangnya ada di sistem tetapi
        # tidak ada di rak mana pun, sehingga Put-Away & pencarian posisi tidak
        # bisa menemukannya. Ditegakkan di API (bukan hanya di layar) karena
        # integrasi/skrip memakai pintu yang sama — dan itulah yang terbukti
        # terjadi: satu penerimaan uji lolos lewat API tanpa lokasi.
        if not loc_id:
            raise HTTPException(
                400,
                "Lokasi tujuan belum dipilih — penerimaan ditolak. Kirim "
                "`location_id` (atau pilih 'Lokasi Tujuan' di layar) supaya stok "
                "yang masuk mendarat di rak yang jelas.",
            )

        # ── P1.C: Anti over-receive validation ─────────────────────────────
        # Jika GR linked ke PO dan enforce_po_qty=True, validasi bahwa net_qty
        # (received - rejected) untuk tiap material_id tidak melebihi qty
        # remaining di PO.
        po_id_link = existing.get("po_id")
        enforce_po = bool(existing.get("enforce_po_qty", bool(po_id_link)))
        if po_id_link and enforce_po:
            po_doc = await db.rahaza_purchase_orders.find_one({"id": po_id_link}, {"_id": 0})
            if po_doc:
                # Build remaining map per material_id
                remaining_map: dict = {}
                for po_it in (po_doc.get("items") or []):
                    mid = po_it.get("material_id")
                    if not mid:
                        continue
                    remaining = max(
                        0.0,
                        float(po_it.get("qty_ordered") or 0) - float(po_it.get("qty_received") or 0),
                    )
                    remaining_map[mid] = remaining_map.get(mid, 0.0) + remaining

                # Sum net_qty per material_id in this GR
                net_per_material: dict = {}
                for it in items_to_process:
                    mid = it.get("material_id")
                    if not mid:
                        continue
                    net = float(it.get("received_qty", 0)) - float(it.get("rejected_qty", 0))
                    if net <= 0:
                        continue
                    net_per_material[mid] = net_per_material.get(mid, 0.0) + net

                # Validate
                for mid, net in net_per_material.items():
                    remaining = remaining_map.get(mid, 0.0)
                    if net - remaining > 0.0001:  # small epsilon for float
                        # Find name for friendlier error
                        mat = await db.rahaza_materials.find_one({"id": mid}, {"_id": 0, "name": 1, "code": 1})
                        nm = (mat and (mat.get("name") or mat.get("code"))) or mid
                        raise HTTPException(
                            400,
                            f"Over-receive ditolak untuk {nm}: net qty {net} melebihi sisa PO {remaining} "
                            f"(PO {existing.get('po_number')}).",
                        )
        
        # ── FASE E2: INBOUND TUNGGAL VIA stock_service ─────────────────────
        # Dokumen GR tetap SATU-SATUNYA pintu inbound (PO→GR, QC, lot/expiry,
        # 3-way matching). Penambahan stok DIALIRKAN lewat `stock_service.add`
        # (satu pintu kanonik → `rahaza_material_stock` + ledger `rahaza_stock_ledger`).
        #
        # Ledger ganda `warehouse_stock` + `warehouse_movements` TIDAK ditulis lagi
        # (sumber duplikasi INV-11). Reader legacy yang masih baca `warehouse_stock`
        # akan dimigrasi/dihapus di Fase F. Movement kanonik tetap dicatat di
        # `rahaza_material_movements` (via `_record_material_movement`).
        # ── FASE 6 (INV-8): qty REJECT → KARANTINA (bukan hilang tanpa jejak) ──
        # accepted (net) → lokasi storage GR; rejected → lokasi KARANTINA (stok
        # diblokir/available=0) + dok `wh_quarantine_items` utk disposisi lanjutan.
        # ── FASE H-5 (2026-08-16): ROLL KAIN LAHIR DI SINI ──────────────────
        # Sebelum ini, GR menambah stok kain lewat `stock_service.add` tanpa pernah
        # menyentuh `wh_fabric_rolls` — gudang bisa punya 420 kg kain di sistem dan
        # NOL gulungan yang bisa ditunjuk, sementara Portal Cutting memerlukan roll
        # untuk melacak lot kain. Rincian roll (jumlah + berat/panjang tiap roll)
        # DIVALIDASI DULU untuk SEMUA baris sebelum satu pun stok ditulis, supaya
        # tidak ada GR setengah jadi: stok bertambah tapi rollnya gagal dibuat.
        roll_plan: dict = {}
        rolls_created: list = []      # nomor roll yang benar-benar terbit di GR ini
        rolls_pending: list = []      # baris kain yang MASUK STOK tanpa rincian roll
        for item in items_to_process:
            mid = item.get("material_id")
            lines = item.get("rolls") or []
            if not mid:
                continue
            mat_r = await db.rahaza_materials.find_one(
                {"id": mid}, {"_id": 0, "id": 1, "code": 1, "name": 1, "unit": 1,
                              "type": 1, "is_cut_panel": 1, "color": 1, "color_name": 1})
            if not mat_r:
                if not lines:
                    continue
                raise HTTPException(400, f"Material baris penerimaan tidak ditemukan: {mid}")
            accepted_probe = float(item.get("accepted_qty") if item.get("accepted_qty") is not None
                                   else max(0.0, float(item.get("received_qty", 0) or 0)
                                            - float(item.get("rejected_qty", 0) or 0)))
            if not lines:
                # Kain yang masuk stok TANPA rincian roll bukan kesalahan fatal (GR bisa
                # datang dari jalur otomatis/PO tanpa timbangan per gulungan), tetapi
                # lubangnya harus KELIHATAN: baris ini dilaporkan balik ke UI dan muncul
                # di daftar "Penerimaan tanpa roll" untuk diterbitkan kemudian (backfill).
                if accepted_probe > 0 and fabric_roll_engine.is_roll_material(mat_r):
                    rolls_pending.append({
                        "item_id": item.get("id"),
                        "material_id": mid,
                        "material_code": mat_r.get("code") or "",
                        "material_name": mat_r.get("name") or "",
                        "unit": mat_r.get("unit") or "",
                        "accepted_qty": round(accepted_probe, 3),
                    })
                continue
            if not fabric_roll_engine.is_roll_material(mat_r):
                raise HTTPException(400, (
                    f"{mat_r.get('code')} bersatuan '{mat_r.get('unit')}' tidak dilacak per "
                    "gulungan, jadi rincian roll tidak berlaku untuk baris ini."))
            accepted = accepted_probe
            if accepted <= 0:
                raise HTTPException(400, (
                    f"{mat_r.get('code')} — {mat_r.get('name')}: qty diterima 0, jadi tidak ada "
                    "gulungan yang bisa diterbitkan. Hapus rincian rollnya atau perbaiki qty."))
            roll_plan[item.get("id")] = (
                mat_r,
                fabric_roll_engine.validate_roll_lines(
                    lines, accepted, mat_r.get("unit") or "",
                    f"{mat_r.get('code')} — {mat_r.get('name')}"),
            )

        quarantined_total = 0.0
        quarantine_records = []
        for item in items_to_process:
            received_qty = float(item.get("received_qty", 0) or 0)
            rejected_qty = float(item.get("rejected_qty", 0) or 0)
            net_qty = received_qty - rejected_qty

            sku   = item.get("sku", "")
            pname = item.get("product_name", "")
            unit  = item.get("unit", "pcs")
            lot_number  = item.get("lot_number") or ""
            expiry_date = item.get("expiry_date") or None
            material_id = item.get("material_id")

            if not material_id:
                # Tanpa material_id item tak bisa masuk stok kanonik. JANGAN tulis
                # ledger bayangan — catat warning & lewati (GR tetap tercatat).
                logger.warning(
                    f"GR {existing.get('receipt_number','')}: item '{pname or sku}' "
                    f"tanpa material_id — dilewati (tidak masuk stok kanonik)."
                )
                continue

            if net_qty > 0:
                # ── Satu pintu: stock_service.add (kanonik + ledger) ─────────────
                # FATAL bila gagal: biarkan exception naik → status GR TIDAK di-set
                # 'received' (baris update di ~L476 tak tercapai) → tidak ada stok
                # bayangan / GR "received" tanpa stok. User bisa retry.
                # Stok SEBELUM barang masuk — dipakai menghitung HPP rata-rata
                # bergerak di bawah (harus dibaca sebelum `add`, bukan sesudah).
                qty_before_receipt = float(await stock_service.get_onhand(material_id, db=db) or 0)
                await stock_service.add(
                    material_id, loc_id, net_qty,
                    meta={
                        "inventory_category": item.get("inventory_category"),
                        "unit": unit,
                        "material_name": pname or None,
                        "material_code": sku or None,
                        "location_code": loc_name or None,
                    },
                    ref={
                        "source": "goods_receipt",
                        "ref_type": "goods_receipt",
                        "ref_id": receipt_id,
                        "ref_number": existing.get("receipt_number", ""),
                        "lot_number": lot_number,
                        "expiry_date": expiry_date,
                    },
                    actor={"id": user.get("id"), "name": user.get("name"), "email": user.get("email", "")},
                    db=db,
                )

                # ── Movement kanonik (audit) — non-fatal ─────────────────────────
                gr_mv = None
                try:
                    gr_mv = await _record_material_movement(
                        db, material_id, loc_id, loc_name, net_qty, unit,
                        "goods_receipt", receipt_id,
                        existing.get("receipt_number", ""),
                        f"GR {existing.get('receipt_number', '')} — {pname} dari {existing.get('supplier_name', existing.get('source_type', ''))}",
                        user,
                        unit_cost=float(item.get("unit_price") or item.get("unit_cost") or 0),
                        material_name=pname,
                    )
                except Exception as e:
                    logger.error(f"GR movement log failed (material_id={material_id}): {e}")
                    # Non-fatal: stok kanonik sudah tertulis; jangan putus flow.
                # ── C-02 (audit 2026-09-04): GR bernilai → Dr Persediaan / Cr GRNI (2-1150).
                # Tagihan supplier (AP-dari-GR) kemudian Dr GRNI / Cr Hutang Usaha. Non-fatal.
                if gr_mv and gr_mv.get("unit_cost", 0) > 0:
                    try:
                        from routes.rahaza_posting import post_inventory_receive
                        gr_gl = await post_inventory_receive(db, gr_mv, user)
                        item["gl_je_number"] = gr_gl.get("je_number")
                        item["gl_error"] = gr_gl.get("error")
                    except Exception as e:
                        logger.error(f"GR GL posting gagal (material_id={material_id}): {e}")
                logger.info(f"GR inbound via stock_service: material_id={material_id} +{net_qty} {unit} @ loc={loc_id}")

                # ── HARGA SATUAN (HPP) DARI PEMBELIAN — keputusan pemilik 2026-08-21 ──
                # Sebelumnya harga satuan HANYA bisa diketik di Master Item, dan
                # penerimaan barang (GR) tidak pernah menyentuhnya: PO boleh berisi
                # harga per satuan, barang masuk, tetapi nilai persediaan tetap
                # memakai angka ketikan lama (atau 0 ⇒ jurnal persediaan tidak
                # terbentuk). Sekarang setiap penerimaan bernilai memperbarui HPP
                # dengan **rata-rata bergerak** (SSOT core/accessory_valuation) —
                # berlaku untuk SEMUA jenis barang (kain, aksesoris, benang, dll),
                # bukan hanya aksesoris seperti sebelumnya.
                cost_in = float(item.get("unit_price") or item.get("unit_cost") or 0)
                if cost_in > 0:
                    try:
                        res_cost = await accessory_valuation.apply_receipt_cost(
                            db, material_id, net_qty, cost_in,
                            qty_before=qty_before_receipt,
                            actor={"id": user.get("id"), "name": user.get("name", "")},
                            notes=(f"GR {existing.get('receipt_number', '')}"
                                   f"{' · PO ' + str(existing.get('po_number')) if existing.get('po_number') else ''}"),
                        )
                        item["unit_cost_applied"] = res_cost["new_unit_cost"]
                        logger.info(
                            f"GR HPP: material_id={material_id} {res_cost['old_unit_cost']} → "
                            f"{res_cost['new_unit_cost']} (harga beli {cost_in}, qty {net_qty})")
                    except Exception as e:  # noqa: BLE001 — HPP tidak boleh menggagalkan penerimaan
                        logger.error(f"GR HPP gagal (material_id={material_id}): {e}")

                # ── FASE H-5: terbitkan roll untuk baris kain (nomor otomatis) ──
                if item.get("id") in roll_plan:
                    mat_r, lines_ok = roll_plan[item["id"]]
                    made = await fabric_roll_engine.create_rolls_from_receipt(
                        db, {**existing, "location_name": loc_name, "location_id": loc_id},
                        item, mat_r, lines_ok, user)
                    rolls_created.extend(r["roll_no"] for r in made)
                    item["roll_ids"] = [r["id"] for r in made]
                    item["roll_numbers"] = [r["roll_no"] for r in made]

            # ── FASE 6: reject masuk KARANTINA (non-fatal, GR tetap 'received') ──
            if rejected_qty > 0:
                try:
                    qdoc = await quarantine.quarantine_in(
                        db,
                        material_id=material_id,
                        qty=rejected_qty,
                        unit=unit,
                        source={
                            "type": "goods_receipt",
                            "id": receipt_id,
                            "number": existing.get("receipt_number", ""),
                            "line_id": item.get("id"),
                            "supplier_name": existing.get("supplier_name", ""),
                            "po_number": existing.get("po_number", ""),
                        },
                        reject_reasons=item.get("reject_reasons") or [],
                        # reject saat GR: qty ini TIDAK di-invoice (AP pakai net qty)
                        # ⇒ belum pernah masuk nilai persediaan.
                        valued=False,
                        notes=f"Reject saat penerimaan GR {existing.get('receipt_number','')}",
                        actor={"id": user.get("id"), "name": user.get("name"), "email": user.get("email", "")},
                    )
                    item["quarantined_qty"] = rejected_qty
                    item["quarantine_item_id"] = qdoc["id"]
                    quarantined_total += rejected_qty
                    quarantine_records.append({"material_id": material_id, "qty": rejected_qty,
                                               "quarantine_item_id": qdoc["id"]})
                    logger.info(f"GR reject → karantina: material_id={material_id} {rejected_qty} {unit}")
                except Exception as e:
                    logger.error(f"GR quarantine gagal (material_id={material_id}): {e}")

        if quarantine_records:
            updates["items"] = items_to_process
            updates["quarantine_summary"] = {
                "total_qty": round(quarantined_total, 4),
                "records": quarantine_records,
                "location": (await quarantine.get_quarantine_location_info(db)),
                "at": now(),
            }

        # ── FASE H-5: simpan jejak roll di dokumen GR (dipakai UI + backfill) ──
        # `items` WAJIB ikut tersimpan supaya `roll_ids`/`roll_numbers` per baris tidak
        # hilang — daftar "Penerimaan tanpa roll" memakai `source_receipt_item_id`,
        # jadi baris GR harus tetap bisa dipasangkan dengan gulungannya.
        if rolls_created or rolls_pending:
            updates["items"] = items_to_process
            updates["rolls_created"] = rolls_created
            updates["rolls_pending"] = rolls_pending
            updates["rolls_summary"] = {
                "issued_count": len(rolls_created),
                "issued_numbers": rolls_created,
                "pending_lines": len(rolls_pending),
                "at": now(),
            }
            if rolls_created:
                logger.info(
                    f"GR {existing.get('receipt_number','')}: {len(rolls_created)} roll terbit "
                    f"({', '.join(rolls_created[:5])}{'…' if len(rolls_created) > 5 else ''})")

        # ── Sprint 2.1: Update PO received qty (3-way matching) ───────────────
        po_id = existing.get("po_id")
        if po_id:
            try:
                from routes.rahaza_po import update_po_received_qty
                # Build items list with material_id and qty for PO update
                items_for_po = []
                for item in items_to_process:
                    net_qty = float(item.get("received_qty", 0)) - float(item.get("rejected_qty", 0))
                    if net_qty > 0:
                        items_for_po.append({
                            "material_id": item.get("material_id"),
                            "po_item_id": item.get("po_item_id"),
                            "qty": net_qty,
                        })
                if items_for_po:
                    await update_po_received_qty(db, po_id, items_for_po)
                    logger.info(f"GR {existing.get('receipt_number')} updated PO {existing.get('po_number')} received qty")
            except Exception as e:
                logger.error(f"Failed to update PO received qty: {e}")
                # Non-fatal: don't break the receive flow
        
        # ── Phase 8A: Asset Capitalization (Auto-create Fixed Asset + GL Posting) ───
        try:
            await _capitalize_assets_from_grn(db, receipt_id, existing, items_to_process, user)
        except Exception as e:
            logger.error(f"Failed to capitalize assets from GR: {e}")
            # Non-fatal: log warning but don't break the receive flow
    
    await db.warehouse_receiving.update_one({"id": receipt_id}, {"$set": updates})
    await log_activity(user["id"], user["name"], "update", "warehouse_receiving",
                       f"{existing.get('receipt_number', '')} → {body.get('status', 'updated')}")
    
    updated = await db.warehouse_receiving.find_one({"id": receipt_id}, {"_id": 0})
    return serialize_doc(updated)


@router.delete("/receiving/{receipt_id}")
async def delete_receiving(receipt_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    receipt = await db.warehouse_receiving.find_one({"id": receipt_id})
    if not receipt:
        raise HTTPException(404, "Receipt not found")
    if receipt.get("status") == "received":
        raise HTTPException(400, "Tidak bisa hapus GR yang sudah 'received'")
    await db.warehouse_receiving.delete_one({"id": receipt_id})
    return {"status": "deleted"}


# ── Stock Summary & Movements ─────────────────────────────────────────────────

@router.get("/stock")
async def get_stock(request: Request, location_id: str = None, sku: str = None):
    """FASE F: baca stok KANONIK `rahaza_material_stock` (bukan lagi `warehouse_stock`).
    Endpoint legacy tanpa konsumen UI aktif; dipertahankan sbg shim read-only kanonik."""
    await require_auth(request)
    db = get_db()
    query = {"qty": {"$gt": 0}}
    if location_id:
        query["location_id"] = location_id
    if sku:
        query["$or"] = [
            {"material_code": {"$regex": re.escape(sku), "$options": "i"}},
            {"sku": {"$regex": re.escape(sku), "$options": "i"}},
        ]
    stock = await db.rahaza_material_stock.find(query, {"_id": 0}).to_list(500)
    return serialize_doc(stock)


@router.get("/stock/summary")
async def get_stock_summary(request: Request):
    """FASE F: ringkasan stok KANONIK dari `rahaza_material_stock`."""
    await require_auth(request)
    db = get_db()
    pipeline = [
        {"$match": {"qty": {"$gt": 0}}},
        {"$group": {
            "_id": None,
            "total_skus": {"$sum": 1},
            "total_qty": {"$sum": "$qty"},
            "total_value": {"$sum": {"$multiply": ["$qty", {"$ifNull": ["$unit_cost", 0]}]}}
        }}
    ]
    results = await db.rahaza_material_stock.aggregate(pipeline).to_list(1)
    return serialize_doc(results[0] if results else {"total_skus": 0, "total_qty": 0, "total_value": 0})


@router.get("/movements")
async def get_movements(request: Request, location_id: str = None, sku: str = None, limit: int = 100):
    """FASE F: pergerakan stok KANONIK dari `rahaza_stock_ledger` (bukan `warehouse_movements`)."""
    await require_auth(request)
    db = get_db()
    query = {}
    if location_id:
        query["location_id"] = location_id
    if sku:
        query["material_id"] = {"$regex": re.escape(sku), "$options": "i"}
    movements = await db.rahaza_stock_ledger.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(500)
    return serialize_doc(movements)


# ── Dashboard ──────────────────────────────────────────────────

@router.get("/dashboard-kpi")
async def warehouse_dashboard_kpi(request: Request):
    """Sprint 3.4 + FASE F: KPI KANONIK untuk WarehouseDashboard.jsx.
    total_items/total_qty/total_locations dari `rahaza_material_stock` (SSOT);
    pending_gr tetap dari `warehouse_receiving` (masih aktif via GR)."""
    await require_auth(request)
    db = get_db()

    pending_gr = await db.warehouse_receiving.count_documents({"status": {"$in": ["draft", "inspecting"]}})

    pipeline = [
        {"$match": {"qty": {"$gt": 0}}},
        {"$group": {
            "_id": None,
            "total_items": {"$sum": 1},
            "total_qty": {"$sum": "$qty"},
            "locations": {"$addToSet": "$location_id"},
        }},
    ]
    agg = await db.rahaza_material_stock.aggregate(pipeline).to_list(1)
    row = agg[0] if agg else {}
    total_items = int(row.get("total_items", 0))
    total_qty = float(row.get("total_qty", 0) or 0)
    total_locations = len([x for x in (row.get("locations") or []) if x])

    return serialize_doc({
        "total_items": total_items,
        "total_locations": total_locations,
        "pending_gr": pending_gr,
        "total_qty": round(total_qty, 2),
    })


@router.get("/dashboard")
async def warehouse_dashboard(request: Request):
    """FASE F: dashboard gudang KANONIK dari `rahaza_material_stock` + `rahaza_stock_ledger`."""
    await require_auth(request)
    db = get_db()

    pending_receipts = await db.warehouse_receiving.count_documents({"status": {"$in": ["draft", "inspecting"]}})

    pipeline = [
        {"$match": {"qty": {"$gt": 0}}},
        {"$group": {
            "_id": None,
            "total_skus": {"$sum": 1},
            "total_qty": {"$sum": "$qty"},
            "locations": {"$addToSet": "$location_id"},
        }},
    ]
    agg = await db.rahaza_material_stock.aggregate(pipeline).to_list(1)
    row = agg[0] if agg else {}
    total_skus = int(row.get("total_skus", 0))
    total_qty = float(row.get("total_qty", 0) or 0)
    total_locations = len([x for x in (row.get("locations") or []) if x])

    recent_movements = await db.rahaza_stock_ledger.find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(500)

    return serialize_doc({
        "total_locations": total_locations,
        "total_skus": total_skus,
        "total_qty": total_qty,
        "pending_receipts": pending_receipts,
        "recent_movements": recent_movements,
    })


# ── Put-Away & Stock Opname (LEGACY) — DIHAPUS (FASE F, 2026-07-25) ─────────────
# Endpoint `/api/warehouse/putaway` (transfer) & `/api/warehouse/opname` (variance)
# adalah GEN-1 legacy penulis ledger ganda `warehouse_stock`/`warehouse_movements`
# (sumber INV-11). Tidak ada konsumen UI/BE (audit Fase F = 0). Kanonik:
#   Put-Away → /api/wms/putaway/*  (routes/wms_putaway.py, sadar-lokasi)
#   Opname   → /api/wms/opname3/*  (routes/wms_opname3.py, scan-driven + finance)
# Koleksi terkait DROP via scripts/migrate_drop_warehouse_ledger_legacy.py.


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 8A: ASSET CAPITALIZATION DARI GRN
# ══════════════════════════════════════════════════════════════════════════════

async def _capitalize_assets_from_grn(db, receipt_id: str, grn: dict, items: list, user: dict):
    """
    Phase 8A: Auto-create Fixed Assets + GL Posting untuk GRN items dengan item_type='asset'.
    
    Logic:
    1. Detect items dengan item_type='asset'
    2. Create fixed asset record di rahaza_fixed_assets
    3. Auto-post GL: Dr. Fixed Asset / Cr. AP Clearing
    4. Link GRN item dengan asset_id
    """
    from routes.rahaza_posting import post_asset_acquisition
    
    assets_created = []
    
    for item in items:
        # Check if this is an asset item
        if item.get("item_type", "material") != "asset":
            continue
        
        net_qty = float(item.get("received_qty", 0)) - float(item.get("rejected_qty", 0))
        if net_qty <= 0:
            continue
        
        # Get asset parameters
        unit_price = float(item.get("unit_price", 0))
        if unit_price <= 0:
            logger.warning(f"GRN item {item.get('product_name')} is asset but unit_price=0, skipping capitalization")
            continue
        
        total_cost = round(unit_price * net_qty, 2)
        asset_category = item.get("asset_category", "lain-lain")
        
        # Generate asset code — SESI #27: field yang benar adalah `code` (nama
        # dokumennya), bukan `asset_code`. Dengan nama field yang salah,
        # penyemaian counter membaca `asset_code` yang TIDAK PERNAH ada di
        # dokumen ⇒ counter selalu mulai dari 0 saat pertama kali dipakai.
        # `config_key` menyambungkannya ke katalog Penomoran Dokumen owner.
        asset_code = await gen_prefixed_number(
            db, "rahaza_fixed_assets", "code", "FA-", 5,
            config_key="rahaza_fixed_assets.code")
        
        # Default useful life per category (months)
        useful_life_map = {
            "tanah": 0,  # No depreciation
            "bangunan": 240,  # 20 years
            "mesin": 120,  # 10 years
            "kendaraan": 60,  # 5 years
            "peralatan": 60,  # 5 years
            "it": 36,  # 3 years
            "furnitur": 60,  # 5 years
            "lain-lain": 60,  # 5 years default
        }
        useful_life = useful_life_map.get(asset_category, 60)
        
        # Create fixed asset
        asset_doc = {
            "id": new_id(),
            "code": asset_code,
            "name": item.get("product_name", "Unnamed Asset"),
            "category": asset_category,
            "serial_number": item.get("serial_number", ""),
            "purchase_date": now().date().isoformat(),
            "purchase_cost": total_cost,
            "residual_value": 0,  # Default: no residual
            "useful_life_months": useful_life,
            "depreciation_method": "straight_line" if useful_life > 0 else "none",
            "status": "active",
            "location": grn.get("location_name", ""),
            "notes": f"Auto-created from GR {grn.get('receipt_number', '')} - {item.get('product_name', '')}",
            "grn_id": receipt_id,
            "grn_number": grn.get("receipt_number", ""),
            "grn_item_id": item.get("id", ""),
            "po_id": grn.get("po_id"),
            "po_number": grn.get("po_number", ""),
            "supplier_name": grn.get("supplier_name", ""),
            "qty_received": net_qty,
            "unit": item.get("unit", "pcs"),
            "created_at": now(),
            "updated_at": now(),
            "created_by": user.get("id", "system"),
            "created_by_name": user.get("name", "system"),
        }
        
        await db.rahaza_fixed_assets.insert_one(asset_doc)
        logger.info(f"✅ Fixed asset created: {asset_code} - {asset_doc['name']} (Rp {total_cost:,.0f})")
        
        # Auto-post GL: Dr. Fixed Asset / Cr. AP Clearing
        posting_result = None
        try:
            asset_refresh = await db.rahaza_fixed_assets.find_one({"id": asset_doc["id"]}, {"_id": 0})
            posting_result = await post_asset_acquisition(db, asset_refresh, user)
            logger.info(f"✅ Asset GL posted: {asset_code} - JE {posting_result.get('je_number', 'N/A')}")
        except Exception as e:
            logger.exception(f"Asset GL posting failed for {asset_code}")
            posting_result = {"ok": False, "error": str(e)}
        
        # Update GRN item dengan asset_id
        await db.warehouse_receiving.update_one(
            {"id": receipt_id, "items.id": item.get("id")},
            {"$set": {
                "items.$.asset_id": asset_doc["id"],
                "items.$.asset_code": asset_code,
                "items.$.capitalized": True,
                "items.$.capitalized_at": now(),
            }}
        )
        
        assets_created.append({
            "asset_id": asset_doc["id"],
            "asset_code": asset_code,
            "asset_name": asset_doc["name"],
            "total_cost": total_cost,
            "posting_result": posting_result,
        })
    
    if assets_created:
        logger.info(f"🎯 Phase 8A: {len(assets_created)} fixed assets capitalized from GR {grn.get('receipt_number', '')}")
    
    return assets_created

