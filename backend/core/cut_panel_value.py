"""core.cut_panel_value — NILAI POTONGAN LAHIR SAAT KAIN DIPOTONG (SESI #32).

MASALAH SEBELUM MODUL INI (terukur, POC `test_core_potongan_nilai_dan_yatim.py`)
------------------------------------------------------------------------------
Portal Cutting sudah memotong stok kain dan menambah stok POTONGAN lewat SSOT
`core.stock_service`, tetapi **nilainya tidak ikut berpindah**:

  · master potongan lahir dengan `unit_cost: 0`;
  · angka itu baru diisi saat order **di-complete**, dengan cara **MENIMPA**
    (bukan rata-rata bergerak) memakai `input_unit_cost` yang di-**snapshot saat
    order DIBUAT**.

Tiga akibat yang bisa diukur:

  1. **Nilai persediaan bocor selama order berjalan.** Kain keluar 10 m ×
     Rp30.000 = Rp300.000 hilang dari nilai persediaan, sementara 20 pcs
     potongan yang lahir dinilai Rp0. Laporan valuasi jadi lebih kecil dari
     kenyataan sampai (dan hanya bila) order ditutup.
  2. **Harga basi.** Bila kain dibeli lagi dengan harga berbeda, `complete`
     memakai harga LAMA. Pada POC: nilai sebenarnya Rp641.379,31 tetapi
     `complete` menghitung Rp600.000 ⇒ **Rp41.379 hilang** tanpa jejak.
  3. **Angka saling menghapus.** Satu master potongan dipakai berulang
     (kodenya deterministik per style+warna+ukuran). Order kedua MENIMPA HPP
     order pertama, padahal stok potongan lama masih ada di gudang.

APA YANG MODUL INI LAKUKAN
--------------------------
Satu pintu `apply_progress_value()` dipanggil TIAP laporan progres cutting,
SESUDAH stok bergerak:

    nilai kain keluar = qty kain terpakai × unit_cost kain **saat itu**
    HPP masuk/pcs     = nilai kain keluar / pcs potongan jadi
    HPP potongan baru = RATA-RATA BERGERAK(stok potongan lama, HPP lama,
                                           pcs masuk, HPP masuk/pcs)

Rata-rata bergerak & riwayat harganya memakai SSOT yang sudah ada
(`core.accessory_valuation`) — bukan rumus keempat. Sisa/limbah kain memang
ikut terserap ke dalam HPP potongan (itu memang biaya potongan), dan **upah**
TIDAK dimasukkan di sini supaya tidak dobel dengan `core.product_costing`
(HPP produk jadi = bahan + upah CMT + upah internal).

KEJUJURAN: kain yang belum punya harga (belum pernah dibeli) TIDAK dipaksa jadi
Rp0 yang seolah benar. Potongannya ditandai `value_status='unvalued'`, alasan +
jalan keluarnya dikembalikan ke layar, dan peringatan dikirim ke Admin Gudang
lewat SSOT `accessory_valuation.notify_unvalued`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from core import accessory_valuation, stock_service

_log = logging.getLogger(__name__)

VALUE_SOURCE = "cutting_fabric_wac"


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _now():
    return datetime.now(timezone.utc)


def unvalued_message(fabric_code: str, fabric_name: str = "") -> str:
    label = f"{fabric_code} — {fabric_name}".strip(" —") or "kain ini"
    return (
        f"Potongan BELUM BERNILAI karena harga satuan kain {label} belum ada. "
        "Harga kain lahir dari pembelian: buat PO lalu terima barang di Gudang "
        "(atau perbaiki di Gudang → Valuasi HPP). Selama harga kain 0, nilai "
        "persediaan potongan ini juga 0 — angkanya bukan gratis, hanya belum diketahui."
    )


async def panel_onhand(db, panel_id: str) -> float:
    """Stok potongan SEBELUM penambahan (wajib dibaca sebelum `stock_service.add`).

    Pelajaran sesi #30 (GR): rata-rata bergerak yang membaca stok SESUDAH barang
    masuk akan selalu salah, karena qty masuk sudah ikut terhitung di penyebut.
    """
    return round(_f(await stock_service.get_onhand(panel_id, db=db)), 4)


async def apply_progress_value(db, *, fabric_id: str, panel_id: str,
                               input_consumed: float, output_qty: float,
                               qty_before: float | None = None,
                               actor: dict | None = None,
                               reference: str = "") -> dict:
    """Pindahkan nilai kain yang keluar menjadi nilai potongan yang masuk.

    Selalu mengembalikan jejak lengkap (dipakai layar + dokumen + gate), dan
    TIDAK PERNAH melempar: nilai boleh gagal dihitung, kain sudah terpotong.
    """
    trace = {
        "value_source": VALUE_SOURCE,
        "fabric_unit_cost": 0.0,
        "value_out": 0.0,
        "cost_per_pcs_in": 0.0,
        "panel_unit_cost_before": 0.0,
        "panel_unit_cost_after": 0.0,
        "panel_qty_before": round(_f(qty_before), 4) if qty_before is not None else 0.0,
        "value_status": "unvalued",
        "value_note": "",
    }
    input_consumed, output_qty = _f(input_consumed), _f(output_qty)
    try:
        fabric = await db.rahaza_materials.find_one({"id": fabric_id}, {"_id": 0}) or {}
        panel = await db.rahaza_materials.find_one({"id": panel_id}, {"_id": 0}) or {}
        cost_in_fabric = accessory_valuation.resolve_unit_cost(fabric)
        trace["fabric_unit_cost"] = round(cost_in_fabric, 4)
        trace["panel_unit_cost_before"] = round(accessory_valuation.resolve_unit_cost(panel), 4)
        trace["panel_unit_cost_after"] = trace["panel_unit_cost_before"]

        if output_qty <= 0:
            trace["value_note"] = "pcs potongan 0 — tidak ada yang bisa dinilai"
            return trace

        if cost_in_fabric <= 0:
            trace["value_status"] = "unvalued"
            trace["value_note"] = unvalued_message(fabric.get("code", ""), fabric.get("name", ""))
            await _mark_panel(db, panel_id, "unvalued", trace["value_note"], fabric)
            try:
                await accessory_valuation.notify_unvalued(
                    db, material=fabric, movement_type="cutting_issue",
                    qty=input_consumed, actor=actor)
            except Exception:  # noqa: BLE001 — notifikasi bukan alasan gagal
                _log.warning("notify_unvalued gagal untuk kain %s", fabric_id)
            return trace

        value_out = round(cost_in_fabric * input_consumed, 4)
        cost_per_pcs = round(value_out / output_qty, 6)
        res = await accessory_valuation.apply_receipt_cost(
            db, panel_id, output_qty, cost_per_pcs,
            qty_before=qty_before, actor=actor,
            notes=(f"Potongan dari cutting {reference}" if reference else "Potongan dari cutting"),
        )
        trace.update({
            "value_out": value_out,
            "cost_per_pcs_in": cost_per_pcs,
            "panel_unit_cost_before": res.get("old_unit_cost", trace["panel_unit_cost_before"]),
            "panel_unit_cost_after": res.get("new_unit_cost", 0.0),
            "value_status": "valued",
            "value_note": (
                f"Nilai kain keluar {value_out:,.2f} dibagi {output_qty:g} pcs = "
                f"{cost_per_pcs:,.2f}/pcs, dirata-rata dengan stok potongan lama."),
        })
        await _mark_panel(db, panel_id, "valued", trace["value_note"], fabric)
        return trace
    except Exception as e:  # noqa: BLE001 — kain SUDAH terpotong; nilai tidak boleh membatalkannya
        _log.exception("nilai potongan gagal dihitung (panel=%s): %s", panel_id, e)
        trace["value_note"] = f"nilai potongan gagal dihitung: {e}"
        return trace


async def _mark_panel(db, panel_id: str, status: str, note: str, fabric: dict) -> None:
    """Tandai master potongan supaya LAYAR bisa mengatakan status nilainya."""
    patch = {
        "value_status": status,
        "value_source": VALUE_SOURCE,
        "value_note": note,
        "value_updated_at": _now(),
        "updated_at": _now(),
    }
    if fabric.get("code"):
        patch["source_material_code"] = fabric["code"]
    await db.rahaza_materials.update_one({"id": panel_id}, {"$set": patch})


async def order_value_totals(db, order_id: str) -> dict:
    """Nilai TERUKUR satu order cutting = Σ nilai kain yang benar-benar keluar.

    Dipakai `complete` supaya angkanya bukan hasil perkalian harga basi
    (`input_unit_cost` yang di-snapshot saat order dibuat).
    """
    total_value = 0.0
    total_out = 0.0
    total_in = 0.0
    traced = 0
    n = 0
    async for p in db.cutting_progress.find(
            {"cutting_order_id": order_id},
            {"_id": 0, "value_out": 1, "output_qty": 1, "input_consumed": 1}):
        n += 1
        total_out += _f(p.get("output_qty"))
        total_in += _f(p.get("input_consumed"))
        if p.get("value_out") is not None:
            traced += 1
            total_value += _f(p.get("value_out"))
    return {
        "progress_count": n,
        "traced_count": traced,
        "value_total": round(total_value, 4),
        "output_qty": round(total_out, 4),
        "input_qty": round(total_in, 4),
        "unit_cost": round(total_value / total_out, 4) if total_out > 0 else 0.0,
        "complete": bool(n) and traced == n,
    }
