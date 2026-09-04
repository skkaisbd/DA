"""core/fabric_roll_engine.py — roll kain LAHIR saat diterima, MATI saat dipotong.

FASE H-5 · H-6 (2026-08-16, keputusan owner).

KEADAAN SEBELUM BERKAS INI (terukur, bukan dugaan):
  · `wh_fabric_rolls` hanya bisa diisi MANUAL lewat layar Roll Kain — nomor rollnya
    pun diketik tangan (`RollIn.roll_no` wajib). Penerimaan barang (GR) menambah
    stok kain lewat `stock_service.add` **tanpa pernah menyentuh roll**. Jadi
    gudang bisa punya 420 kg kain di sistem dan NOL roll yang bisa ditunjuk.
  · Isi koleksinya hari ini: 4 dokumen, semuanya `DEMO-RL-000x` dengan
    `material_code` "0001".."0004" — data contoh, bukan kain sungguhan.
  · Portal Cutting SUDAH bisa mengurangi sisa roll, tetapi memilih roll bersifat
    **OPSIONAL** ("Roll Fisik (opsional)"). Artinya kain bisa dipotong tanpa satu
    gulungan pun berkurang: stok turun, roll tetap penuh, dan tidak ada cara
    menjawab "gulungan mana yang dipakai untuk order ini" saat buyer menuntut
    lot kain yang sama.

KEPUTUSAN OWNER (2026-08-16):
  H-5  Roll DIBUAT saat penerimaan: petugas mengisi jumlah roll + berat/panjang
       tiap roll, **nomor roll otomatis** (tidak boleh diketik — nomor ketikan
       membuat dua gulungan fisik bisa bernomor sama).
  H-6  Cutting **WAJIB** memilih roll untuk kain yang punya roll. Bila kainnya
       belum punya roll sama sekali, permintaan DITOLAK dengan alasan yang
       menyebut jalan keluarnya — bukan dilewati diam-diam.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

log = logging.getLogger(__name__)

# Satuan roll = SATUAN ASLI MATERIAL, tidak pernah dipaksa ke meter (2026-08-21).
#
# KENAPA DIUBAH (keluhan pemilik, terukur): kain dibeli **yard** (PO 650 yard,
# diterima 520, reject 130 ⇒ 390 yard dalam 4 gulungan @97,5), tetapi layar Roll
# Kain menulis kolomnya "(m)" dan `rol`/`gulung` DIPAKSA menjadi `meter` di sini.
# Akibatnya angka roll terbaca "97,50 m" — pemakai menyimpulkan yard-nya dikonversi
# dan barang yang diterima tidak cocok dengan PO. Tidak ada konversi yang benar-
# benar terjadi; yang salah adalah SATUAN YANG DITULIS SISTEM.
#
# Satuan kecil (gram/cm/inch) SENGAJA tidak ada: kain tidak diterima per gram.
ROLL_UOM = {
    "kg": "kg", "bal": "bal", "ball": "bal",
    "meter": "meter", "m": "meter", "mtr": "meter",
    "rol": "rol", "gulung": "gulung",
    "yard": "yard", "yd": "yard",
}
# Satuan BERAT → sisanya disimpan di `remaining_kg`; sisanya di `remaining_m`.
# Dokumen lama memakai uom 'kg' (dari bal) & 'meter' (dari rol/gulung) sehingga
# tetap jatuh di ember penyimpanan yang SAMA — tidak ada angka yang berpindah.
WEIGHT_UOMS = {"kg", "bal", "ball"}
# Faktor konversi ke meter — HANYA untuk info tambahan di layar ("97,50 yard ≈
# 89,15 m"). Angka yang disimpan & dipakai perhitungan tetap satuan aslinya.
TO_METER = {"meter": 1.0, "yard": 0.9144, "inch": 0.0254, "cm": 0.01}
ROLL_NUMBER_KEY = "wh_fabric_rolls.roll_no"
ROLLS = "wh_fabric_rolls"
ROLL_MOVES = "wh_fabric_roll_movements"
OPEN_STATUSES = ["in_stock", "partly_issued", "returned"]


def _now():
    return datetime.now(timezone.utc)


def _uid():
    return str(uuid.uuid4())


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def roll_uom(unit: Optional[str]) -> Optional[str]:
    return ROLL_UOM.get(str(unit or "").strip().lower())


def is_roll_material(mat: dict) -> bool:
    """Material yang WAJAR dilacak per gulungan (kain/benang), bukan pcs & bukan FG."""
    if not mat or mat.get("type") == "fg" or mat.get("is_cut_panel"):
        return False
    return roll_uom(mat.get("unit")) is not None


def remaining_of(roll: dict) -> float:
    return _f(roll.get("remaining_kg") if is_weight_uom(roll.get("uom")) else roll.get("remaining_m"))


def is_weight_uom(unit: Optional[str]) -> bool:
    return str(unit or "").strip().lower() in WEIGHT_UOMS


def total_of(roll: dict) -> float:
    return _f(roll.get("weight_kg") if is_weight_uom(roll.get("uom")) else roll.get("length_m"))


def meters_of(unit: Optional[str], qty: float) -> Optional[float]:
    """Info tambahan "≈ x m" untuk satuan panjang non-meter. None = tidak setara panjang."""
    f = TO_METER.get(str(unit or "").strip().lower())
    if f is None or f == 1.0:
        return None
    return round(_f(qty) * f, 2)


def with_display_uom(roll: dict) -> dict:
    """Tambahkan angka SATUAN ASLI + info konversi ke meter (tanpa mengubah data).

    Layar tidak boleh menebak satuan dari nama field (`length_m`/`remaining_m`
    adalah nama warisan, isinya bisa yard/rol). Semua pembaca memakai `uom`,
    `qty_total`, `qty_remaining` dari sini.
    """
    uom = str(roll.get("uom") or "").strip().lower()
    total, remaining = total_of(roll), remaining_of(roll)
    return {
        **roll,
        "uom": uom,
        "qty_total": round(total, 3),
        "qty_remaining": round(remaining, 3),
        "is_weight": is_weight_uom(uom),
        "qty_total_m": meters_of(uom, total),
        "qty_remaining_m": meters_of(uom, remaining),
    }


def remaining_field(roll: dict) -> str:
    return "remaining_kg" if is_weight_uom(roll.get("uom")) else "remaining_m"


def validate_roll_lines(lines, accepted_qty: float, unit: str, label: str) -> list[dict]:
    """Rincian roll harus BENAR-BENAR menjelaskan qty yang diterima.

    Kenapa dijumlahkan ketat: kalau total roll tidak sama dengan qty yang masuk
    stok, gudang punya dua angka untuk satu penerimaan — dan yang dipakai orang
    saat mencari kain adalah rollnya, sementara laporan memakai stoknya.
    """
    if not isinstance(lines, list) or not lines:
        raise HTTPException(400, f"Rincian roll untuk {label} kosong.")
    if len(lines) > 200:
        raise HTTPException(400, f"Terlalu banyak roll untuk {label} (maks 200 per baris).")
    out, total = [], 0.0
    for i, ln in enumerate(lines, start=1):
        qty = _f((ln or {}).get("qty"))
        if qty <= 0:
            raise HTTPException(400, f"Roll ke-{i} pada {label}: isi berat/panjangnya "
                                     "(harus lebih dari 0).")
        total += qty
        out.append({"qty": round(qty, 3),
                    "color_lot": str((ln or {}).get("color_lot") or "").strip(),
                    "notes": str((ln or {}).get("notes") or "").strip()})
    tol = max(0.01, abs(accepted_qty) * 0.005)
    if abs(total - accepted_qty) > tol:
        raise HTTPException(400, (
            f"Rincian roll {label} tidak cocok: {len(out)} roll = {total:,.3f} {unit}, "
            f"sedangkan qty diterima {accepted_qty:,.3f} {unit} "
            f"(selisih {total - accepted_qty:+,.3f} {unit}). Perbaiki angka rollnya — "
            "stok dan roll harus menjelaskan penerimaan yang sama."))
    return out


async def next_roll_no(db) -> str:
    """Nomor roll OTOMATIS lewat SSOT penomoran dokumen (mode auto, tidak diketik)."""
    from core.doc_number_policy import issue_number
    return await issue_number(db, ROLL_NUMBER_KEY)


async def issue_roll_no(db, requested: str = "") -> str:
    """Nomor roll untuk jalur yang MENERIMA ketikan pemakai (layar Roll Kain).

    Bedanya dengan `next_roll_no`: fungsi ini meneruskan nomor yang diketik ke
    kebijakan penomoran. Mode `auto` (bawaan) MENOLAK nomor ketikan dengan pesan
    yang menyebut nomor yang akan dipakai; mode `manual` memeriksa polanya. Jadi
    tidak ada jalur diam-diam yang bisa memasukkan nomor gulungan berpola bebas.
    """
    from core.doc_number_policy import issue_number
    return await issue_number(db, ROLL_NUMBER_KEY, requested=(requested or "").strip())


async def create_rolls_from_receipt(db, receipt: dict, item: dict, material: dict,
                                    lines: list[dict], user: dict) -> list[dict]:
    """Terbitkan roll dari SATU baris penerimaan (H-5)."""
    uom = roll_uom(material.get("unit")) or "meter"
    is_weight = is_weight_uom(uom)
    created = []
    for ln in lines:
        roll_no = await next_roll_no(db)
        qty = ln["qty"]
        doc = {
            "id": _uid(), "roll_no": roll_no,
            "material_id": material.get("id"),
            "material_code": material.get("code") or item.get("sku") or "",
            "material_name": material.get("name") or item.get("product_name") or "",
            "color": material.get("color") or material.get("color_name") or "",
            "color_lot": ln.get("color_lot") or item.get("lot_number") or "",
            "supplier_name": receipt.get("supplier_name") or "",
            # `uom` = SATUAN ASLI material (yard tetap yard). Nama field
            # `length_m`/`remaining_m` adalah warisan — isinya mengikuti `uom`.
            "uom": uom,
            "length_m": 0.0 if is_weight else qty,
            "weight_kg": qty if is_weight else 0.0,
            "remaining_m": 0.0 if is_weight else qty,
            "remaining_kg": qty if is_weight else 0.0,
            "received_date": (receipt.get("created_at") or _now().isoformat())[:10]
            if isinstance(receipt.get("created_at"), str) else _now().date().isoformat(),
            "po_no": receipt.get("po_number") or "",
            # QC roll mengikuti hasil inspeksi baris GR — roll yang datang dari baris
            # ber-reject tidak boleh diam-diam berstatus 'pass'.
            "qc_status": "pass" if (item.get("inspection_status") == "passed"
                                    and not _f(item.get("rejected_qty"))) else "pending",
            "status": "in_stock",
            "position_id": receipt.get("location_id") or "",
            "position_barcode": "",
            "location_id": receipt.get("location_id") or "",
            "location_name": receipt.get("location_name") or "",
            "unit_cost": _f(item.get("unit_price")),
            "notes": ln.get("notes") or f"Otomatis dari GR {receipt.get('receipt_number', '')}",
            "source_receipt_id": receipt.get("id"),
            "source_receipt_number": receipt.get("receipt_number") or "",
            "source_receipt_item_id": item.get("id"),
            "created_at": _now(), "created_by": user.get("name") or user.get("id"),
            "updated_at": _now(), "updated_by": user.get("name") or user.get("id"),
        }
        await db[ROLLS].insert_one(dict(doc))
        await db[ROLL_MOVES].insert_one({
            "id": _uid(), "roll_id": doc["id"], "roll_no": roll_no,
            "movement_type": "receive", "qty": qty, "unit": uom,
            "reference_type": "goods_receipt", "reference_id": receipt.get("id"),
            "reference_no": receipt.get("receipt_number") or "",
            "to_location": receipt.get("location_name") or "",
            "notes": f"Penerimaan GR {receipt.get('receipt_number', '')}",
            "created_at": _now(), "created_by": user.get("name") or user.get("id"),
        })
        doc.pop("_id", None)
        created.append(doc)
    return created


async def open_rolls(db, material_id: str) -> list[dict]:
    """Roll yang masih bersisa untuk satu material (urut nomor = FIFO penerimaan)."""
    rows = await db[ROLLS].find(
        {"material_id": material_id, "status": {"$in": OPEN_STATUSES}}, {"_id": 0}
    ).sort("roll_no", 1).to_list(500)
    return [r for r in rows if remaining_of(r) > 0]


def allocate(rolls: list[dict], qty: float, unit_label: str = "") -> list[dict]:
    """Bagi pemakaian ke roll-roll terpilih, FIFO menurut nomor roll.

    Kenapa dibagi otomatis: operator cutting tidak menimbang per gulungan saat
    memotong. Kalau pembagian diserahkan ke ketikan, sisa roll cepat menyimpang
    dari kenyataan dan lot kain tidak bisa dipertanggungjawabkan lagi.
    """
    left, plan = round(_f(qty), 4), []
    total = sum(remaining_of(r) for r in rolls)
    if left - total > 0.0001:
        raise HTTPException(400, (
            f"Sisa roll terpilih tidak cukup: butuh {left:,.3f}{unit_label}, "
            f"tersedia {total:,.3f}{unit_label} pada {len(rolls)} roll. "
            "Pilih roll tambahan atau kurangi jumlah pemakaian."))
    for r in rolls:
        if left <= 0.0001:
            break
        take = min(remaining_of(r), left)
        if take <= 0:
            continue
        plan.append({"roll_id": r["id"], "roll_no": r.get("roll_no", ""),
                     "qty": round(take, 3), "uom": r.get("uom", "")})
        left = round(left - take, 4)
    return plan


async def consume_rolls(db, plan: list[dict], ref: dict, user: dict) -> list[dict]:
    """Kurangi sisa roll sesuai rencana + catat movement (satu pintu pemakaian roll)."""
    done = []
    for p in plan:
        roll = await db[ROLLS].find_one({"id": p["roll_id"]}, {"_id": 0})
        if not roll:
            continue
        field = remaining_field(roll)
        new_remaining = round(max(remaining_of(roll) - p["qty"], 0.0), 3)
        status = "fully_issued" if new_remaining <= 0.0001 else "partly_issued"
        await db[ROLLS].update_one({"id": roll["id"]}, {"$set": {
            field: new_remaining, "status": status,
            "updated_at": _now(), "updated_by": user.get("name") or user.get("id"),
        }})
        await db[ROLL_MOVES].insert_one({
            "id": _uid(), "roll_id": roll["id"], "roll_no": roll.get("roll_no", ""),
            "movement_type": "issue", "qty": p["qty"], "unit": roll.get("uom", ""),
            "reference_type": ref.get("type", "cutting"), "reference_id": ref.get("id"),
            "reference_no": ref.get("number", ""),
            "notes": ref.get("notes", ""),
            "created_at": _now(), "created_by": user.get("name") or user.get("id"),
        })
        done.append({**p, "remaining_after": new_remaining, "status": status})
    return done


async def receipts_missing_rolls(db, limit: int = 50) -> list[dict]:
    """Penerimaan kain yang SUDAH masuk stok tetapi tidak punya rincian roll.

    Lubang ini harus KELIHATAN: kain yang ada di stok tetapi tidak punya gulungan
    akan menghentikan Cutting (H-6), dan orang gudang perlu tahu daftarnya
    sebelum bagian potong berhenti bekerja.
    """
    out = []
    cur = db.warehouse_receiving.find(
        {"status": "received"}, {"_id": 0, "id": 1, "receipt_number": 1, "items": 1,
                                 "supplier_name": 1, "created_at": 1, "location_name": 1}
    ).sort("created_at", -1).limit(400)
    async for gr in cur:
        for it in (gr.get("items") or []):
            mid = it.get("material_id")
            if not mid:
                continue
            accepted = _f(it.get("accepted_qty")) or (
                _f(it.get("received_qty")) - _f(it.get("rejected_qty")))
            if accepted <= 0:
                continue
            mat = await db.rahaza_materials.find_one(
                {"id": mid}, {"_id": 0, "id": 1, "code": 1, "name": 1, "unit": 1,
                              "type": 1, "is_cut_panel": 1})
            if not mat or not is_roll_material(mat):
                continue
            n = await db[ROLLS].count_documents({"source_receipt_item_id": it.get("id")})
            if n:
                continue
            out.append({
                "receipt_id": gr.get("id"), "receipt_number": gr.get("receipt_number"),
                "supplier_name": gr.get("supplier_name") or "",
                "location_name": gr.get("location_name") or "",
                "created_at": gr.get("created_at"),
                "item_id": it.get("id"), "material_id": mid,
                "material_code": mat.get("code"), "material_name": mat.get("name"),
                "unit": mat.get("unit"), "accepted_qty": round(accepted, 3),
            })
            if len(out) >= limit:
                return out
    return out
