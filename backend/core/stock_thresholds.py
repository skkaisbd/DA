"""core/stock_thresholds.py — SSOT "kapan stok disebut RENDAH?" (W3, permintaan pemilik).

═══════════════════════════════════════════════════════════════════════════════
MASALAH YANG DISELESAIKAN (terukur 2026-08-19, data hidup)
═══════════════════════════════════════════════════════════════════════════════
Pemilik melaporkan menu **Alert & Reorder** (`#wh-smart`) "tidak pernah berbunyi".
Yang diukur: dari **333 material, 333 (100%) `min_stock_qty` kosong/0** dan **0
material punya `reorder_point` > 0** ⇒ fiturnya tidak usang, **ambangnya belum
pernah diisi siapa pun**.

Lebih dalam dari itu, ada TIGA definisi "stok rendah" yang hidup terpisah dan
saling tidak tahu — sumber klasik alarm yang diam:

| Pembaca | Ambang yang dipakai | Stok yang dibaca |
|---|---|---|
| `GET /api/warehouse/alerts` (layar Alert & Reorder) | HANYA `reorder_point` | on-hand kanonik |
| `rahaza_alerts.check_low_stock` (notifikasi/bel) | HANYA `min_stock` (legacy) | `SUM($qty)` |
| `GET /api/rahaza/materials?low_stock=true` (dashboard) | `min_stock_qty` → `%` → `min_stock` | `SUM($qty)` |

Akibatnya: pemilik mengisi ambang di satu tempat, lalu layar lain tetap berkata
"semua normal". Dan `SUM($qty)` **melewatkan baris stok skema lama** yang
menyimpan angkanya di `total_qty` / `available_quantity` (lihat FASE 6.6-A) ⇒
stok bisa terlihat 0 padahal ada, atau sebaliknya.

Berkas ini menjadi SATU definisi yang dipakai SEMUA pembaca itu:
  · ambang dibaca berurutan `min_stock_qty` → `min_stock` (legacy) → `min_stock_percentage`
  · `reorder_point` adalah TITIK PESAN ULANG (peringatan), bukan pengganti ambang minimum
  · on-hand SELALU lewat `core.stock_service.onhand_map` (semua lokasi, semua skema baris)
  · USULAN ambang dihitung dari PEMAKAIAN NYATA (`rahaza_stock_ledger`), dan bila
    30 hari terakhir tidak ada pemakaian, usulannya **0 + `no_usage_data`** —
    alat ini tidak pernah menebak angka yang tidak punya dasar.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core import stock_service

LEAD_TIME_DEFAULT_DAYS = 7.0
SAFETY_FACTOR = 0.2          # 20% penyangga — sama dengan rumus smart-reorder lama
USAGE_WINDOW_DAYS = 30
CONSUMPTION_OPS = ["issue", "issue_row"]


def _num(v):
    try:
        if v in (None, ""):
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _now():
    return datetime.now(timezone.utc)


def resolve_threshold(mat: dict) -> dict:
    """Ambang efektif satu material — SATU aturan untuk semua pembaca."""
    min_qty = _num(mat.get("min_stock_qty"))
    source = "min_stock_qty"
    if min_qty <= 0:
        legacy = _num(mat.get("min_stock"))
        if legacy > 0:
            min_qty, source = legacy, "min_stock"
    if min_qty <= 0:
        pct = _num(mat.get("min_stock_percentage"))
        if pct > 0:
            baseline = _num(mat.get("max_historical_qty")) or 100.0
            min_qty, source = round(baseline * pct / 100.0, 4), "min_stock_percentage"
    reorder_point = _num(mat.get("reorder_point"))
    if min_qty <= 0 and reorder_point <= 0:
        source = ""
    elif min_qty <= 0:
        source = "reorder_point"
    return {
        "min_qty": round(min_qty, 4),
        "reorder_point": round(reorder_point, 4),
        "threshold_source": source,
        "has_threshold": bool(min_qty > 0 or reorder_point > 0),
        "alert_at": round(max(min_qty, reorder_point), 4),
    }


def status_of(onhand: float, th: dict) -> str:
    """`no_threshold` · `critical` · `low` · `ok` — dipakai layar, alert & notifikasi."""
    if not th["has_threshold"]:
        return "no_threshold"
    if onhand <= 0:
        return "critical"
    if th["min_qty"] > 0 and onhand < th["min_qty"]:
        return "critical"
    if th["reorder_point"] > 0 and onhand <= th["reorder_point"]:
        return "low"
    return "ok"


async def usage_map(db, material_ids: list, days: int = USAGE_WINDOW_DAYS) -> dict:
    """Pemakaian NYATA per material dari ledger kanonik (bukan dugaan)."""
    ids = [m for m in (material_ids or []) if m]
    if not ids:
        return {}
    since = _now() - timedelta(days=days)
    out = {}
    cur = db.rahaza_stock_ledger.aggregate([
        {"$match": {"material_id": {"$in": ids}, "op": {"$in": CONSUMPTION_OPS},
                    "delta": {"$lt": 0}, "created_at": {"$gte": since}}},
        {"$group": {"_id": "$material_id",
                    "out": {"$sum": {"$abs": "$delta"}},
                    "n": {"$sum": 1}}},
    ])
    async for row in cur:
        total = float(row.get("out") or 0)
        out[row["_id"]] = {
            "out_qty": round(total, 4),
            "movements": int(row.get("n") or 0),
            "avg_daily": round(total / days, 4) if total > 0 else 0.0,
        }
    return out


def suggest(mat: dict, usage: dict | None) -> dict:
    """Usulan ambang dari pemakaian nyata. Tanpa pemakaian ⇒ TIDAK menebak."""
    u = usage or {}
    avg_daily = float(u.get("avg_daily") or 0)
    lead = _num(mat.get("lead_time_days")) or LEAD_TIME_DEFAULT_DAYS
    if avg_daily <= 0:
        return {
            "avg_daily_consumption": 0.0, "lead_time_days": lead, "safety_stock": 0.0,
            "suggested_min_stock": 0.0, "suggested_reorder_point": 0.0,
            "movements_30d": int(u.get("movements") or 0), "no_usage_data": True,
        }
    lead_need = avg_daily * lead
    safety = lead_need * SAFETY_FACTOR
    return {
        "avg_daily_consumption": round(avg_daily, 2),
        "lead_time_days": lead,
        "safety_stock": round(safety, 2),
        # Ambang MINIMUM = cukup untuk masa tunggu pembelian.
        "suggested_min_stock": round(lead_need, 2),
        # Titik pesan ulang = masa tunggu + penyangga (rumus smart-reorder lama).
        "suggested_reorder_point": round(lead_need + safety, 2),
        "movements_30d": int(u.get("movements") or 0),
        "no_usage_data": False,
    }


async def evaluate(db, *, material_ids: list | None = None, types: list | None = None,
                   search: str = "", include_inactive: bool = False,
                   with_suggestion: bool = True, limit: int = 5000) -> list:
    """Baris "Ambang Stok": identitas + stok kanonik + ambang + status + usulan."""
    q = {} if include_inactive else {"active": True}
    if material_ids:
        q["id"] = {"$in": [m for m in material_ids if m]}
    if types:
        q["type"] = {"$in": types}
    if search:
        import re
        pat = re.compile(re.escape(search), re.IGNORECASE)
        q["$or"] = [{"code": pat}, {"name": pat}]
    mats = await db.rahaza_materials.find(q, {"_id": 0}).sort(
        [("type", 1), ("code", 1)]).to_list(limit)
    ids = [m.get("id") for m in mats if m.get("id")]
    onhand = await stock_service.onhand_map(ids, db=db) if ids else {}
    usage = await usage_map(db, ids) if (with_suggestion and ids) else {}

    rows = []
    for m in mats:
        mid = m.get("id")
        th = resolve_threshold(m)
        qty = round(float(onhand.get(mid, 0) or 0), 4)
        row = {
            "material_id": mid,
            "code": m.get("code") or "",
            "name": m.get("name") or "",
            "type": m.get("type") or "",
            "category_name": m.get("category_name") or "",
            "unit": m.get("unit") or "",
            "onhand": qty,
            "min_stock_qty": _num(m.get("min_stock_qty")),
            "reorder_point": _num(m.get("reorder_point")),
            "min_stock_legacy": _num(m.get("min_stock")),
            "min_stock_percentage": _num(m.get("min_stock_percentage")),
            # Sesi #33 — ambang TIDAK boleh jadi angka anonim: layar harus bisa
            # mengatakan DARI MANA angka itu, siapa yang memasangnya, dan kapan.
            "threshold_basis": m.get("threshold_basis") or "",
            "threshold_basis_note": m.get("threshold_basis_note") or "",
            "threshold_set_by": m.get("threshold_set_by") or "",
            "threshold_set_at": m.get("threshold_set_at") or "",
            "unit_cost": _num(m.get("unit_cost")),
            **th,
            "status": status_of(qty, th),
            "shortage": round(max(0.0, th["alert_at"] - qty), 4) if th["has_threshold"] else 0.0,
        }
        if with_suggestion:
            row["suggestion"] = suggest(m, usage.get(mid))
        rows.append(row)
    return rows


async def low_stock_alerts(db, *, limit: int = 5000) -> list:
    """Daftar alert stok rendah — SATU sumber untuk layar, notifikasi & dashboard."""
    rows = await evaluate(db, with_suggestion=False, limit=limit)
    alerts = []
    for r in rows:
        if r["status"] not in ("critical", "low"):
            continue
        alerts.append({
            "type": "low_stock",
            "severity": "critical" if r["status"] == "critical" else "warning",
            "material_id": r["material_id"],
            "material_name": r["name"],
            "code": r["code"],
            "sku": r["code"],
            "current_qty": r["onhand"],
            "min_stock_qty": r["min_qty"],
            "reorder_point": r["reorder_point"],
            "threshold_source": r["threshold_source"],
            "alert_at": r["alert_at"],
            "shortage": r["shortage"],
            "unit": r["unit"],
            "message": (f"Stok {r['name']} ({r['onhand']:g} {r['unit']}) di bawah ambang "
                        f"{r['alert_at']:g} {r['unit']} — kurang {r['shortage']:g}"),
        })
    alerts.sort(key=lambda a: (0 if a["severity"] == "critical" else 1, -a["shortage"]))
    return alerts


async def summary(db) -> dict:
    """Angka untuk badge dashboard + kejujuran layar ("ambang belum diisi")."""
    rows = await evaluate(db, with_suggestion=False)
    with_th = [r for r in rows if r["has_threshold"]]
    return {
        "total_materials": len(rows),
        "with_threshold": len(with_th),
        "missing_threshold": len(rows) - len(with_th),
        "low": sum(1 for r in rows if r["status"] == "low"),
        "critical": sum(1 for r in rows if r["status"] == "critical"),
        "alerts": sum(1 for r in rows if r["status"] in ("low", "critical")),
    }


async def apply_thresholds(db, items: list, actor: dict | None = None) -> dict:
    """Simpan ambang untuk banyak material sekaligus (layar Ambang Stok).

    Nilai negatif ditolak pemanggil (route); di sini 0/None berarti "kosongkan"
    supaya pemilik bisa MEMBATALKAN ambang, bukan terjebak angka lama.
    """
    now = _now().isoformat()
    updated, missing = [], []
    for it in items or []:
        mid = str(it.get("material_id") or "").strip()
        if not mid:
            continue
        patch = {"updated_at": now}
        if "min_stock_qty" in it:
            v = _num(it.get("min_stock_qty"))
            patch["min_stock_qty"] = round(v, 4) if v > 0 else None
        if "reorder_point" in it:
            patch["reorder_point"] = round(_num(it.get("reorder_point")), 4)
        if "lead_time_days" in it and _num(it.get("lead_time_days")) > 0:
            patch["lead_time_days"] = round(_num(it.get("lead_time_days")), 2)
        res = await db.rahaza_materials.update_one({"id": mid}, {"$set": patch})
        if res.matched_count:
            updated.append(mid)
        else:
            missing.append(mid)
    return {"updated": len(updated), "updated_ids": updated, "not_found": missing,
            "by": (actor or {}).get("email") or (actor or {}).get("name") or ""}


# ═══════════════════════════════════════════════════════════════════════════════
# ISI AMBANG MASSAL (sesi #33) — kenapa bagian ini ada
# ═══════════════════════════════════════════════════════════════════════════════
# Layar "Ambang Stok" sudah punya tombol "Pakai semua usulan" sejak W3, tetapi
# usulannya HANYA lahir dari pemakaian 30 hari (`usage_map`). Terukur di data
# hidup 2026-08-23: dari **335 material, hanya 5** yang punya pemakaian nyata
# ⇒ tombol itu secara STRUKTURAL cuma bisa mengisi 5 baris, dan 330 material
# (98,5%) tidak punya jalan massal apa pun — harus diketik satu per satu.
#
# Maka disediakan EMPAT dasar yang semuanya punya PIJAKAN NYATA, dan dasarnya
# SELALU disimpan bersama siapa & kapan (`threshold_basis`, `threshold_set_by`,
# `threshold_set_at`) supaya layar tidak pernah menampilkan angka anonim:
#   · usage_30d       — pemakaian nyata 30 hari (rumus lama, tidak diubah)
#   · purchase_lot    — rata-rata SATU KALI BELI dari penerimaan pembelian nyata
#   · percent_onhand  — persen dari stok sekarang (stok sekarang dianggap normal)
#   · fixed           — angka yang diketik pemilik untuk seluruh seleksi
# Semua mode WAJIB bisa dipratinjau (dry-run) sebelum menulis, dan bisa
# dikosongkan lagi (`bulk_clear`) supaya salah isi tidak menjadi jebakan.
BASIS_LABEL = {
    "usage_30d": "pemakaian nyata 30 hari",
    "purchase_lot": "rata-rata satu kali beli",
    "percent_onhand": "persen dari stok sekarang",
    "fixed": "diketik pemilik",
}
LOT_MULTIPLIER_DEFAULT = 0.5
LOT_WINDOW_MONTHS = 12
RECEIVING_COLL = "warehouse_receiving"
RECEIVED_STATES = ("received", "completed")


class SkipRow(Exception):
    """Barang ini TIDAK bisa dihitung dengan dasar yang dipilih — sebutkan kenapa."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


async def purchase_lot_map(db, material_ids: list, *, months: int = LOT_WINDOW_MONTHS) -> dict:
    """Rata-rata SATU KALI BELI dari penerimaan pembelian NYATA (bukan dugaan).

    Sumbernya `warehouse_receiving` berstatus diterima — dokumen yang sama yang
    melahirkan harga barang. Qty dikonversi ke satuan DASAR (`uom_factor`) dan
    baris ber-qty 0 (barang ditolak QC / belum diterima) TIDAK ikut supaya
    rata-ratanya tidak encer.
    """
    ids = [m for m in (material_ids or []) if m]
    if not ids:
        return {}
    since = _now() - timedelta(days=30 * max(1, months))
    out: dict = {}
    cur = db[RECEIVING_COLL].aggregate([
        {"$match": {"status": {"$in": list(RECEIVED_STATES)},
                    "created_at": {"$gte": since}}},
        {"$unwind": "$items"},
        {"$match": {"items.material_id": {"$in": ids},
                    "items.received_qty": {"$gt": 0}}},
        {"$project": {"mid": "$items.material_id", "created_at": 1,
                      "qty": {"$multiply": [
                          "$items.received_qty",
                          {"$ifNull": ["$items.uom_factor", 1]}]}}},
        {"$group": {"_id": "$mid", "lots": {"$sum": 1}, "total": {"$sum": "$qty"},
                    "last_at": {"$max": "$created_at"}}},
    ])
    async for row in cur:
        lots = int(row.get("lots") or 0)
        total = float(row.get("total") or 0)
        if lots <= 0 or total <= 0:
            continue
        out[row["_id"]] = {"lots": lots, "total_qty": round(total, 4),
                           "avg_qty": round(total / lots, 4), "last_at": row.get("last_at")}
    return out


async def resolve_scope(db, scope: dict | None, *, limit: int = 5000) -> list:
    """Terjemahkan lingkup layar (baris tercentang ATAU filter) menjadi master material."""
    scope = scope or {}
    ids = [str(x) for x in (scope.get("material_ids") or []) if x]
    q: dict = {} if scope.get("include_inactive") else {"active": True}
    if ids:
        q["id"] = {"$in": ids}
    else:
        types = [str(t) for t in (scope.get("types") or []) if t]
        # Layar mengirim NAMA GRUP ("bahan"/"aksesoris"/"fg"); dijabarkan lewat
        # SSOT grup jenis supaya filter layar & filter massal tidak pernah beda.
        group = str(scope.get("type") or "").strip().lower()
        if group and not types:
            from core.material_cost_history import TYPE_GROUPS
            types = TYPE_GROUPS.get(group) or [group]
        if types:
            q["type"] = {"$in": types}
        s = str(scope.get("search") or "").strip()
        if s:
            import re
            pat = re.compile(re.escape(s), re.IGNORECASE)
            q["$or"] = [{"code": pat}, {"name": pat}]
    mats = await db.rahaza_materials.find(q, {"_id": 0}).sort(
        [("type", 1), ("code", 1)]).to_list(limit)
    status = str(scope.get("status") or "all")
    if status in ("missing", "set", "low"):
        mids = [m.get("id") for m in mats if m.get("id")]
        onh = await stock_service.onhand_map(mids, db=db) if mids else {}
        keep = []
        for m in mats:
            th = resolve_threshold(m)
            stt = status_of(_num(onh.get(m.get("id"), 0)), th)
            if status == "missing" and not th["has_threshold"]:
                keep.append(m)
            elif status == "set" and th["has_threshold"]:
                keep.append(m)
            elif status == "low" and stt in ("low", "critical"):
                keep.append(m)
        mats = keep
    return mats


def _fill_values(mode: str, mat: dict, *, onhand: float, usage: dict | None,
                 lot: dict | None, params: dict) -> tuple:
    """(min_qty, reorder_point, catatan dasar) atau `SkipRow` beserta alasannya."""
    unit = mat.get("unit") or mat.get("base_uom") or ""
    if mode == "usage_30d":
        s = suggest(mat, usage)
        if s["no_usage_data"]:
            raise SkipRow("belum ada pemakaian 30 hari terakhir — pakai dasar "
                          "'rata-rata satu kali beli' atau isi angkanya sendiri")
        return (s["suggested_min_stock"], s["suggested_reorder_point"],
                f"pakai {s['avg_daily_consumption']:g} {unit}/hari × {s['lead_time_days']:g} hari "
                f"masa tunggu ({s['movements_30d']} transaksi dalam 30 hari)")
    if mode == "purchase_lot":
        if not lot or _num(lot.get("avg_qty")) <= 0:
            raise SkipRow(f"belum pernah ada penerimaan pembelian {LOT_WINDOW_MONTHS} bulan "
                          "terakhir — pakai dasar 'persen stok' atau isi angkanya sendiri")
        mult = _num(params.get("lot_multiplier")) or LOT_MULTIPLIER_DEFAULT
        mn = round(_num(lot["avg_qty"]) * mult, 4)
        return (mn, round(mn * (1 + SAFETY_FACTOR), 4),
                f"rata-rata satu kali beli {lot['avg_qty']:g} {unit} "
                f"({lot['lots']} penerimaan) × {mult:g}")
    if mode == "percent_onhand":
        if onhand <= 0:
            raise SkipRow("stok sekarang 0 — persentase tidak punya dasar; "
                          "isi angkanya sendiri atau pakai dasar lot pembelian")
        pct = _num(params.get("percent"))
        mn = round(onhand * pct / 100.0, 4)
        return (mn, round(mn * (1 + SAFETY_FACTOR), 4),
                f"{pct:g}% dari stok sekarang {onhand:g} {unit}")
    # fixed
    mn = _num(params.get("min_stock_qty"))
    rp = _num(params.get("reorder_point"))
    return (round(mn, 4), round(rp, 4),
            f"diketik pemilik: minimum {mn:g} {unit}" +
            (f" · titik pesan ulang {rp:g} {unit}" if rp > 0 else ""))


async def bulk_fill(db, *, mode: str, params: dict | None = None, scope: dict | None = None,
                    actor: dict | None = None, dry_run: bool = True,
                    limit: int = 5000) -> dict:
    """Isi ambang MASSAL dengan satu dasar yang jelas. `dry_run=True` = pratinjau."""
    mode = str(mode or "").strip()
    if mode not in BASIS_LABEL:
        raise ValueError(f"mode harus salah satu: {', '.join(BASIS_LABEL)}")
    params = params or {}
    if mode == "fixed":
        mn, rp = _num(params.get("min_stock_qty")), _num(params.get("reorder_point"))
        if mn < 0 or rp < 0:
            raise ValueError("Angka ambang tidak boleh negatif.")
        if mn <= 0 and rp <= 0:
            raise ValueError("Isi minimal salah satu: minimum stok atau titik pesan ulang (> 0).")
    elif mode == "percent_onhand":
        pct = _num(params.get("percent"))
        if pct <= 0 or pct > 100:
            raise ValueError("Persen harus lebih dari 0 dan maksimal 100.")
    elif mode == "purchase_lot":
        mult = _num(params.get("lot_multiplier")) or LOT_MULTIPLIER_DEFAULT
        if mult <= 0 or mult > 10:
            raise ValueError("Pengali lot harus lebih dari 0 dan maksimal 10.")

    mats = await resolve_scope(db, scope, limit=limit)
    ids = [m.get("id") for m in mats if m.get("id")]
    onhand = await stock_service.onhand_map(ids, db=db) if ids else {}
    usage = await usage_map(db, ids) if (mode == "usage_30d" and ids) else {}
    lots = await purchase_lot_map(db, ids) if (mode == "purchase_lot" and ids) else {}

    preview, skipped = [], []
    for m in mats:
        mid = m.get("id")
        qty = _num(onhand.get(mid, 0))
        try:
            mn, rp, note = _fill_values(mode, m, onhand=qty, usage=usage.get(mid),
                                        lot=lots.get(mid), params=params)
        except SkipRow as s:
            skipped.append({"material_id": mid, "code": m.get("code") or "",
                            "name": m.get("name") or "", "reason": s.reason})
            continue
        if mn <= 0 and rp <= 0:
            skipped.append({"material_id": mid, "code": m.get("code") or "",
                            "name": m.get("name") or "",
                            "reason": "hasil hitungannya 0 — tidak ada gunanya dipasang"})
            continue
        th = resolve_threshold(m)
        preview.append({
            "material_id": mid, "code": m.get("code") or "", "name": m.get("name") or "",
            "type": m.get("type") or "", "unit": m.get("unit") or m.get("base_uom") or "",
            "onhand": qty,
            "current_min": th["min_qty"], "current_reorder_point": th["reorder_point"],
            "min_stock_qty": mn, "reorder_point": rp, "basis_note": note,
        })

    applied = 0
    if not dry_run and preview:
        now = _now().isoformat()
        by = (actor or {}).get("email") or (actor or {}).get("name") or ""
        for row in preview:
            patch = {
                "min_stock_qty": row["min_stock_qty"] if row["min_stock_qty"] > 0 else None,
                "reorder_point": row["reorder_point"],
                "threshold_basis": mode,
                "threshold_basis_label": BASIS_LABEL[mode],
                "threshold_basis_note": row["basis_note"],
                "threshold_set_by": by,
                "threshold_set_at": now,
                "updated_at": now,
            }
            res = await db.rahaza_materials.update_one({"id": row["material_id"]},
                                                      {"$set": patch})
            applied += 1 if res.matched_count else 0

    return {
        "mode": mode,
        "basis_label": BASIS_LABEL[mode],
        "dry_run": bool(dry_run),
        "params_used": {**params, **({"lot_multiplier":
                                      _num(params.get("lot_multiplier")) or LOT_MULTIPLIER_DEFAULT}
                                     if mode == "purchase_lot" else {})},
        "scanned": len(mats),
        "eligible": len(preview),
        "applied": applied,
        "preview": preview[:500],
        "preview_truncated": len(preview) > 500,
        "skipped": skipped[:500],
        "skipped_count": len(skipped),
        "summary": await summary(db),
        "catatan": (f"Dasar '{BASIS_LABEL[mode]}' disimpan bersama setiap ambang, lengkap "
                    f"dengan siapa dan kapan — jadi angkanya tidak pernah anonim."),
    }


async def bulk_clear(db, *, material_ids: list | None = None, scope: dict | None = None,
                     actor: dict | None = None, limit: int = 5000) -> dict:
    """Kosongkan ambang untuk seleksi — salah isi massal tidak boleh jadi jebakan.

    Ikut mengosongkan `min_stock` (legacy) & `min_stock_percentage`, karena
    `resolve_threshold` juga membacanya — kalau tidak, ambang \"terhapus\" tetapi
    alertnya masih berbunyi dan pemakai tidak paham kenapa.
    """
    mats = (await resolve_scope(db, {"material_ids": material_ids}, limit=limit)
            if material_ids else await resolve_scope(db, scope, limit=limit))
    now = _now().isoformat()
    by = (actor or {}).get("email") or (actor or {}).get("name") or ""
    cleared, ids = 0, []
    for m in mats:
        res = await db.rahaza_materials.update_one({"id": m.get("id")}, {"$set": {
            "min_stock_qty": None, "reorder_point": 0.0,
            "min_stock": 0.0, "min_stock_percentage": None,
            "threshold_basis": "", "threshold_basis_label": "", "threshold_basis_note": "",
            "threshold_set_by": "", "threshold_set_at": "",
            "threshold_cleared_by": by, "threshold_cleared_at": now, "updated_at": now,
        }})
        if res.matched_count:
            cleared += 1
            ids.append(m.get("id"))
    return {"cleared": cleared, "material_ids": ids, "by": by,
            "summary": await summary(db)}
