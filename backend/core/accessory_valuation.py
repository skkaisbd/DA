"""core.accessory_valuation — FASE 8: valuasi HPP aksesoris.

MASALAH SEBELUM FASE 8 (grounded)
---------------------------------
Harga satuan master aksesoris sudah bisa diisi (FASE G+) dan Opname Aksesoris sudah
memposting jurnal selisih (FASE G) — TAPI mutasi harian aksesoris (terima & keluar)
sama sekali TIDAK BERNILAI:
  * `POST /api/acc/stock/receive` hanya menambah qty; harga beli terbaru tidak pernah
    memperbarui HPP master ⇒ nilai persediaan makin jauh dari kenyataan.
  * `POST /api/acc/stock/issue` tidak menghitung nilai & tidak memposting jurnal ⇒
    beban pemakaian aksesoris tidak pernah masuk buku besar.
  * Kartu stok (`rahaza_material_movements`) tidak menyimpan `unit_cost`/`value` ⇒
    tidak bisa dibuat laporan valuasi/mutasi bernilai.
Akibatnya nilai persediaan aksesoris ≠ saldo akun persediaan di buku besar.

APA YANG MODUL INI SEDIAKAN
---------------------------
  * `resolve_unit_cost` — SSOT baca HPP aksesoris (`unit_cost`, alias legacy `hpp`).
  * `moving_average`   — hitung HPP rata-rata bergerak (WAC) tanpa menulis.
  * `apply_receipt_cost` — terapkan WAC ke master + catat riwayat perubahan HPP.
  * `set_unit_cost`    — set HPP manual (koreksi) + riwayat.
  * `summary`          — ringkasan valuasi (per item, per kategori, total, item belum dinilai).

METODE: **Moving Average / rata-rata bergerak** (konsisten dgn cara `post_inventory_*`
menilai memakai `rahaza_materials.unit_cost` saat posting jurnal).
    HPP_baru = (qty_lama × HPP_lama + qty_masuk × harga_masuk) / (qty_lama + qty_masuk)
Aturan aman:
  * `harga_masuk <= 0` ⇒ HPP TIDAK diubah (input kosong bukan berarti gratis).
  * `qty_lama <= 0`    ⇒ HPP_baru = harga_masuk (stok kosong: tidak ada yang dirata-rata).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from core import stock_service
from core.material_fields import category_of
from utils.notif_recipients import (
    partition_recipients_by_dedup,
    resolve_role_recipients,
)

COST_HISTORY = "rahaza_material_cost_history"
# Jenis material yang termasuk "aksesoris" bagi Portal Aksesoris. Dipakai untuk
# MENYARING riwayat harga supaya layar aksesoris tidak menampilkan kain (sesi #33).
ACCESSORY_TYPES = ("accessory", "packaging")
COST_METHOD = "moving_average"

_log = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def resolve_unit_cost(mat: dict | None) -> float:
    """HPP satuan material (SSOT `unit_cost`, alias legacy `hpp`). 0 = belum dinilai."""
    if not mat:
        return 0.0
    return _f(mat.get("unit_cost") if mat.get("unit_cost") not in (None, "") else mat.get("hpp"))


def moving_average(qty_before: float, cost_before: float, qty_in: float, cost_in: float) -> float:
    """HPP rata-rata bergerak setelah penerimaan. Lihat aturan aman di docstring modul."""
    qty_before, cost_before = _f(qty_before), _f(cost_before)
    qty_in, cost_in = _f(qty_in), _f(cost_in)
    if cost_in <= 0:
        return round(cost_before, 4)
    if qty_before <= 0 or cost_before <= 0:
        return round(cost_in, 4)
    total_qty = qty_before + qty_in
    if total_qty <= 0:
        return round(cost_in, 4)
    return round((qty_before * cost_before + qty_in * cost_in) / total_qty, 4)


async def _record_history(db, *, material_id: str, old_cost: float, new_cost: float,
                          qty_before: float, qty_in: float, cost_in: float,
                          source: str, actor: dict | None, notes: str = ""):
    await db[COST_HISTORY].insert_one({
        "id": _uid(),
        "material_id": material_id,
        "method": COST_METHOD if source == "receive" else "manual",
        "source": source,
        "qty_before": round(_f(qty_before), 4),
        "qty_in": round(_f(qty_in), 4),
        "unit_cost_in": round(_f(cost_in), 4),
        "old_unit_cost": round(_f(old_cost), 4),
        "new_unit_cost": round(_f(new_cost), 4),
        "notes": notes,
        "actor": {"id": (actor or {}).get("id", ""), "name": (actor or {}).get("name", "")},
        "created_at": _now(),
    })


async def apply_receipt_cost(db, material_id: str, qty_in: float, cost_in: float, *,
                             qty_before: float | None = None, actor: dict | None = None,
                             notes: str = "") -> dict:
    """Terapkan HPP rata-rata bergerak ke master saat penerimaan aksesoris.

    Return {old_unit_cost, new_unit_cost, changed, method, qty_before}.
    Bila `cost_in <= 0` → tidak ada perubahan (HPP lama dipertahankan).
    """
    mat = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
    old_cost = resolve_unit_cost(mat)
    if qty_before is None:
        qty_before = await stock_service.get_onhand(material_id, db=db)
    new_cost = moving_average(qty_before, old_cost, qty_in, cost_in)
    changed = abs(new_cost - old_cost) > 1e-6
    if changed:
        await db.rahaza_materials.update_one(
            {"id": material_id},
            {"$set": {
                "unit_cost": new_cost,
                "cost_method": COST_METHOD,
                "last_receipt_unit_cost": round(_f(cost_in), 4),
                "cost_updated_at": _now(),
                "updated_at": _now(),
            }},
        )
        await _record_history(db, material_id=material_id, old_cost=old_cost, new_cost=new_cost,
                              qty_before=qty_before, qty_in=qty_in, cost_in=cost_in,
                              source="receive", actor=actor, notes=notes)
    elif _f(cost_in) > 0:
        # harga masuk sama dengan HPP lama → tetap catat harga beli terakhir (jejak audit)
        await db.rahaza_materials.update_one(
            {"id": material_id},
            {"$set": {"last_receipt_unit_cost": round(_f(cost_in), 4), "cost_method": COST_METHOD}},
        )
    return {
        "old_unit_cost": round(old_cost, 4),
        "new_unit_cost": round(new_cost, 4),
        "changed": changed,
        "method": COST_METHOD,
        "qty_before": round(_f(qty_before), 4),
    }


async def set_unit_cost(db, material_id: str, new_cost: float, *, actor: dict | None = None,
                        notes: str = "") -> dict:
    """Koreksi HPP manual (mis. hasil audit) + riwayat. Tidak mengubah qty."""
    mat = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
    if not mat:
        return {"ok": False, "error": "Material tidak ditemukan."}
    new_cost = _f(new_cost)
    if new_cost < 0:
        return {"ok": False, "error": "Harga satuan tidak boleh negatif."}
    old_cost = resolve_unit_cost(mat)
    qty_before = await stock_service.get_onhand(material_id, db=db)
    await db.rahaza_materials.update_one(
        {"id": material_id},
        {"$set": {"unit_cost": new_cost, "cost_method": "manual",
                  "cost_updated_at": _now(), "updated_at": _now()}},
    )
    await _record_history(db, material_id=material_id, old_cost=old_cost, new_cost=new_cost,
                          qty_before=qty_before, qty_in=0, cost_in=new_cost,
                          source="manual", actor=actor, notes=notes)
    return {
        "ok": True,
        "material_id": material_id,
        "old_unit_cost": round(old_cost, 4),
        "new_unit_cost": round(new_cost, 4),
        "stock_qty": round(qty_before, 4),
        "stock_value": round(qty_before * new_cost, 2),
    }


async def summary(db, *, include_zero_stock: bool = True) -> dict:
    """Ringkasan valuasi persediaan aksesoris (per item + per kategori + total)."""
    mats = await db.rahaza_materials.find(
        {"type": "accessory", "active": True}, {"_id": 0}
    ).sort("name", 1).to_list(5000)
    onhand = await stock_service.onhand_map(db=db)

    items = []
    total_value = 0.0
    total_qty = 0.0
    valued_items = 0
    unvalued_items = 0
    unvalued_qty = 0.0
    by_cat: dict[str, dict] = {}

    for m in mats:
        qty = _f(onhand.get(m["id"], 0))
        cost = resolve_unit_cost(m)
        if not include_zero_stock and qty <= 0:
            continue
        value = round(qty * cost, 2)
        is_valued = cost > 0
        if is_valued:
            valued_items += 1
        else:
            unvalued_items += 1
            unvalued_qty += qty
        total_value += value
        total_qty += qty
        cat = m.get("category") or "Umum"
        slot = by_cat.setdefault(cat, {"category": cat, "items": 0, "qty": 0.0, "value": 0.0,
                                       "unvalued_items": 0})
        slot["items"] += 1
        slot["qty"] = round(slot["qty"] + qty, 4)
        slot["value"] = round(slot["value"] + value, 2)
        if not is_valued:
            slot["unvalued_items"] += 1
        items.append({
            "id": m["id"],
            "code": m.get("code", ""),
            "name": m.get("name", ""),
            "category": cat,
            "item_category": category_of(m.get("type")),
            "unit": m.get("unit", "pcs"),
            "stock_qty": round(qty, 4),
            "unit_cost": round(cost, 4),
            "stock_value": value,
            "valued": is_valued,
            "cost_method": m.get("cost_method") or ("manual" if is_valued else ""),
            "last_receipt_unit_cost": _f(m.get("last_receipt_unit_cost")),
            "cost_updated_at": m.get("cost_updated_at"),
        })

    items.sort(key=lambda x: (-x["stock_value"], x["name"].lower()))
    return {
        "items": items,
        "by_category": sorted(by_cat.values(), key=lambda x: -x["value"]),
        "totals": {
            "total_items": len(items),
            "total_qty": round(total_qty, 4),
            "total_value": round(total_value, 2),
            "valued_items": valued_items,
            "unvalued_items": unvalued_items,
            "unvalued_qty": round(unvalued_qty, 4),
            "avg_unit_cost": round(total_value / total_qty, 4) if total_qty > 0 else 0.0,
        },
        "cost_method": COST_METHOD,
        "generated_at": _now(),
    }


async def cost_history(db, material_id: str | None = None, *, limit: int = 100,
                      types: tuple | list | None = None) -> list:
    """Riwayat perubahan HPP (terbaru dulu).

    2026-08-23 (sesi #33) — parameter `types` DITAMBAHKAN karena koleksi ini
    dipakai SEMUA jenis material (kain, benang, aksesoris, dan nilai POTONGAN
    hasil cutting sejak sesi #32), sementara pemanggilnya adalah layar **Valuasi
    Aksesoris**. Tanpa filter jenis, layar aksesoris menampilkan riwayat material
    KAIN (terukur: 2 dari 7 material di daftar bertipe `fabric`) ⇒ layar
    berbohong tentang isinya. Riwayat lintas jenis punya layarnya sendiri:
    `/api/rahaza/material-costs/history` (SSOT `core/material_cost_history`).
    """
    q: dict = {"material_id": material_id} if material_id else {}
    if types:
        wanted = [str(t) for t in types if t]
        ids = [m["id"] for m in await db.rahaza_materials.find(
            {"type": {"$in": wanted}}, {"_id": 0, "id": 1}).to_list(20000) if m.get("id")]
        if not ids:
            return []
        if material_id:
            if material_id not in set(ids):
                return []
        else:
            q["material_id"] = {"$in": ids}
    return await db[COST_HISTORY].find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)


# ─────────────────────────────────────────────────────────────────────────────
# ALARM "BELUM DINILAI" — peringatan proaktif ke penanggung jawab gudang
# ─────────────────────────────────────────────────────────────────────────────
# Kenapa: item ber-HPP 0 membuat jurnal persediaan GAGAL TERBENTUK secara senyap.
# Selama ini user hanya tahu kalau membuka tab Valuasi. Sekarang setiap mutasi
# (terima/keluar/scrap) pada item tanpa harga langsung memicu notifikasi.
#
# Anti-spam: MAKSIMAL 1 notifikasi **per PENERIMA** per material per 24 jam.
# ┌─ FASE 14 — kenapa "per penerima", bukan "per material" ────────────────────┐
# │ Versi lama mengecek duplikat GLOBAL (`find_one` tanpa `user_id`). Begitu   │
# │ satu ronde terkirim, penerima yang BARU muncul (karyawan baru / user baru  │
# │ diaktifkan / baru naik role) DILEWATI DIAM-DIAM sampai 24 jam — padahal    │
# │ Admin Gudang & Admin Aksesoris baru adalah orang yang PERSIS ditugaskan    │
# │ mengisi HPP yang hilang itu. Dedup sekarang lewat SSOT                     │
# │ `utils/notif_recipients.partition_recipients_by_dedup()`.                  │
# │ Daftar penerima juga lewat SSOT — dulu fungsi ini LUPA menyaring           │
# │ `status='inactive'` sehingga alarm dikirim ke user yang sudah RESIGN.      │
# └────────────────────────────────────────────────────────────────────────────┘
UNVALUED_NOTIF_ROLES = (
    "superadmin", "admin", "owner", "admin_gudang", "admin_aksesoris", "accounting",
)
UNVALUED_SUBTYPE = "stock"
UNVALUED_WINDOW_HOURS = 24

_MV_LABEL_ID = {
    "receive": "penerimaan", "issue": "pengeluaran", "scrap": "scrap",
    "opname_adjust": "penyesuaian opname",
}


async def notify_unvalued(db, *, material: dict, movement_type: str, qty: float,
                          actor: dict | None = None, force: bool = False) -> dict:
    """Kirim peringatan "harga satuan belum diisi" ke Admin Gudang & penanggung jawab.

    Return {"sent": n, "skipped": alasan|None, "skipped_recent": m, "recipients": n_total}.
    SELALU aman dipanggil (tidak pernah melempar) — notifikasi bukan alasan untuk
    menggagalkan mutasi stok.

    Anti-spam **per penerima**: penerima yang sudah diperingatkan untuk material ini
    dalam `UNVALUED_WINDOW_HOURS` terakhir dilewati; penerima BARU tetap dikirimi.
    """
    try:
        mat_id = (material or {}).get("id")
        if not mat_id:
            return {"sent": 0, "skipped": "material tidak dikenal",
                    "skipped_recent": 0, "recipients": 0}

        users = await resolve_role_recipients(db, UNVALUED_NOTIF_ROLES)
        if not users:
            return {"sent": 0, "skipped": "tidak ada penerima",
                    "skipped_recent": 0, "recipients": 0}

        # Filter dedup memakai nama field seperti yang BENAR-BENAR tersimpan oleh
        # notif_insert(): `subtype` + `meta.*` + `created_at` (datetime).
        todo, already = await partition_recipients_by_dedup(
            db, users,
            dedup_filter={"subtype": UNVALUED_SUBTYPE,
                          "meta.unvalued_material_id": mat_id},
            window_hours=UNVALUED_WINDOW_HOURS,
            force=force,
        )
        if not todo:
            return {"sent": 0, "recipients": len(users), "skipped_recent": len(already),
                    "skipped": f"sudah diperingatkan < {UNVALUED_WINDOW_HOURS} jam"}

        from routes.notifications import create_notification  # lazy: hindari import siklik

        label = _MV_LABEL_ID.get(movement_type, movement_type or "mutasi")
        code = (material or {}).get("code") or mat_id
        name = (material or {}).get("name") or code
        unit = (material or {}).get("unit") or ""
        title = f"Harga satuan belum diisi: {code}"
        body = (
            f"Ada {label} {abs(float(qty or 0)):g} {unit} untuk aksesoris \"{name}\" "
            f"tetapi harga satuan (HPP) masih 0, sehingga jurnal persediaan TIDAK terbentuk. "
            f"Isi HPP di Aksesoris → Valuasi HPP → Set HPP agar nilai persediaan sinkron "
            f"dengan buku besar."
        )
        sent = 0
        for u in todo:
            await create_notification(
                db, user_id=u["id"], notif_type=UNVALUED_SUBTYPE,
                title=title, content=body,
                source_type="rahaza_materials", source_id=mat_id,
                source_url="#wh-accessory",
                metadata={
                    "unvalued_material_id": mat_id,
                    "material_code": code,
                    "material_name": name,
                    "movement_type": movement_type,
                    "qty": float(qty or 0),
                    "link_module": "wh-accessory",
                    "hub_tab": "valuasi",
                    "actor": (actor or {}).get("name", ""),
                },
            )
            sent += 1
        return {"sent": sent, "skipped": None, "recipients": len(users),
                "skipped_recent": len(already)}
    except Exception:  # noqa: BLE001 — notifikasi tidak boleh menggagalkan mutasi stok
        # F13 — kalimat "tidak boleh menggagalkan mutasi stok" tetap benar, TAPI
        # dulu kegagalannya hanya jadi teks di nilai balik. Alarm HPP-0 adalah
        # satu-satunya cara pemilik tahu ada barang masuk tanpa harga; kalau
        # pengirimannya mati diam-diam, alarm itu berhenti ada tanpa ada yang
        # sadar. Tetap non-blocking, sekarang bersuara.
        _log.exception("[acc-valuation] gagal mengirim notifikasi alarm HPP — "
                       "mutasi stok TIDAK dibatalkan, tapi alarm tidak terkirim")
        return {"sent": 0, "skipped": "gagal mengirim notifikasi",
                "skipped_recent": 0, "recipients": 0}


# ─────────────────────────────────────────────────────────────────────────────
# RINGKASAN ALARM HARIAN ("belum dinilai") — FASE 10
# ─────────────────────────────────────────────────────────────────────────────
# Kenapa: `notify_unvalued` memberi tahu SAAT KEJADIAN (1×/24 jam per material).
# Bagus untuk reaksi cepat, tapi kalau ada 12 item tanpa harga, penanggung jawab
# menerima 12 notifikasi terpisah dan tidak pernah melihat gambaran utuh
# ("berapa banyak yang masih menggantung?"). Digest harian menjawab itu: SATU
# notifikasi berisi SEMUA item ber-HPP 0 + konteks mutasinya + langkah perbaikan.
# Per-item TETAP jalan (permintaan user) — digest hanya menambah, tidak mengganti.
DIGEST_KIND = "unvalued_daily"
DIGEST_WINDOW_HOURS = 24
DIGEST_MAX_LINES = 15
_JAKARTA = "Asia/Jakarta"


def _jakarta_date_str(dt: datetime | None = None) -> str:
    """Tanggal kalender Asia/Jakarta (YYYY-MM-DD) — penanda idempoten digest harian.

    2026-08-07 (P3): implementasinya dipindah ke SSOT `utils/waktu.py` supaya hanya
    ada SATU pengertian "tanggal WIB" di seluruh repo.
    """
    from utils.waktu import wib_date_str
    return wib_date_str(dt or _now())


async def unvalued_report(db, *, window_hours: int = DIGEST_WINDOW_HOURS) -> dict:
    """Daftar aksesoris ber-HPP 0 + konteks mutasi terakhir (untuk digest & panel FE).

    Dipakai oleh: job `daily_unvalued_digest`, endpoint pratinjau digest, dan panel
    "Belum dinilai" di tab Valuasi HPP. Tidak menulis apa pun.
    """
    data = await summary(db)
    unvalued = [x for x in data["items"] if not x.get("valued")]
    ids = [x["id"] for x in unvalued]
    since = _now() - timedelta(hours=window_hours)

    moves: dict[str, dict] = {}
    if ids:
        cur = db.rahaza_material_movements.find(
            {"material_id": {"$in": ids}, "created_at": {"$gte": since}},
            {"_id": 0, "material_id": 1, "movement_type": 1, "created_at": 1, "qty": 1,
             "qty_signed": 1},
        )
        async for mv in cur:
            slot = moves.setdefault(mv["material_id"], {"count": 0, "last_at": None,
                                                        "types": []})
            slot["count"] += 1
            if mv.get("movement_type") and mv["movement_type"] not in slot["types"]:
                slot["types"].append(mv["movement_type"])
            at = mv.get("created_at")
            if at and (slot["last_at"] is None or at > slot["last_at"]):
                slot["last_at"] = at

    items = []
    for x in unvalued:
        mv = moves.get(x["id"], {})
        items.append({
            "id": x["id"],
            "code": x["code"],
            "name": x["name"],
            "category": x["category"],
            "unit": x["unit"],
            "stock_qty": x["stock_qty"],
            "movements_window": mv.get("count", 0),
            "last_movement_at": mv.get("last_at"),
            "movement_types": mv.get("types", []),
        })
    # yang paling "berisiko" dulu: ada mutasi terbaru, lalu stok terbanyak
    items.sort(key=lambda x: (-x["movements_window"], -x["stock_qty"], x["name"].lower()))

    return {
        "generated_at": _now(),
        "window_hours": window_hours,
        "items": items,
        "totals": {
            "items": len(items),
            "items_with_stock": sum(1 for x in items if x["stock_qty"] > 0),
            "items_with_movement": sum(1 for x in items if x["movements_window"] > 0),
            "total_qty": round(sum(x["stock_qty"] for x in items), 4),
            "movements_window": sum(x["movements_window"] for x in items),
        },
        "inventory_value": data["totals"]["total_value"],
    }


def _digest_text(report: dict) -> str:
    """Isi notifikasi digest: ringkas, konkret, dan menyebut langkah perbaikan."""
    t = report["totals"]
    lines = [
        f"{t['items']} aksesoris masih ber-HPP 0 ({t['items_with_stock']} di antaranya "
        f"punya stok). Selama harga satuan kosong, jurnal persediaan untuk item ini "
        f"TIDAK terbentuk sehingga nilai persediaan ≠ buku besar.",
        "",
    ]
    for x in report["items"][:DIGEST_MAX_LINES]:
        extra = (f" · {x['movements_window']} mutasi {report['window_hours']} jam terakhir"
                 if x["movements_window"] else "")
        lines.append(f"• {x['code']} — {x['name']}: stok {x['stock_qty']:g} {x['unit']}{extra}")
    sisa = t["items"] - min(t["items"], DIGEST_MAX_LINES)
    if sisa > 0:
        lines.append(f"• … dan {sisa} item lain")
    lines += [
        "",
        "Perbaikan: Aksesoris → Valuasi HPP → Set HPP (atau isi harga pada penerimaan "
        "berikutnya agar HPP terbentuk otomatis dari rata-rata bergerak).",
    ]
    return "\n".join(lines)


async def send_unvalued_digest(db, *, force: bool = False, actor: dict | None = None) -> dict:
    """Kirim SATU notifikasi ringkasan harian item ber-HPP 0 ke penanggung jawab.

    Idempoten **per penerima**: maksimal 1× per tanggal kalender Asia/Jakarta per
    penerima (kecuali `force`). Penerima yang BARU muncul setelah digest hari ini
    terkirim TETAP mendapatkannya — versi lama mengecek duplikat global sehingga
    orang baru dilewati sehari penuh (BUG-N3, FASE 14).

    Tidak ada item belum dinilai ⇒ TIDAK mengirim apa pun (tidak berisik).
    SELALU aman dipanggil: kegagalan dilaporkan lewat return value, tidak melempar.
    """
    day = _jakarta_date_str()
    try:
        report = await unvalued_report(db)
        if report["totals"]["items"] == 0:
            return {"sent": 0, "items": 0, "date": day, "recipients": [],
                    "skipped": "tidak ada aksesoris ber-HPP 0 — tidak perlu mengirim"}

        users = await resolve_role_recipients(db, UNVALUED_NOTIF_ROLES)
        if not users:
            return {"sent": 0, "items": report["totals"]["items"], "date": day,
                    "recipients": [], "skipped": "tidak ada penerima (role penanggung jawab kosong)"}

        # Dedup PER PENERIMA pada (jenis digest, tanggal Asia/Jakarta).
        # Tanpa window waktu: penandanya `digest_date` itu sendiri.
        todo, already = await partition_recipients_by_dedup(
            db, users,
            dedup_filter={"meta.digest_kind": DIGEST_KIND, "meta.digest_date": day},
            force=force,
        )
        if not todo:
            return {"sent": 0, "items": report["totals"]["items"], "date": day,
                    "recipients": [], "skipped_recent": len(already),
                    "skipped": f"digest {day} sudah dikirim hari ini"}

        from routes.notifications import create_notification  # lazy: hindari import siklik

        t = report["totals"]
        title = f"Ringkasan harian: {t['items']} aksesoris belum dinilai"
        body = _digest_text(report)
        codes = [x["code"] for x in report["items"]]
        sent = 0
        for u in todo:
            await create_notification(
                db, user_id=u["id"], notif_type=UNVALUED_SUBTYPE,
                title=title, content=body,
                source_type="rahaza_materials", source_id="",
                source_url="#wh-accessory",
                metadata={
                    "digest_kind": DIGEST_KIND,
                    "digest_date": day,
                    "unvalued_count": t["items"],
                    "unvalued_with_stock": t["items_with_stock"],
                    "unvalued_codes": codes[:50],
                    "movements_window": t["movements_window"],
                    "link_module": "wh-accessory",
                    "hub_tab": "valuasi",
                    "triggered_by": (actor or {}).get("name", "Sistem (jadwal harian)"),
                },
            )
            sent += 1
        return {"sent": sent, "items": t["items"], "date": day, "skipped": None,
                "skipped_recent": len(already),
                "recipients": [u.get("email") or u.get("name") for u in todo],
                "codes": codes[:50]}
    except Exception as e:  # noqa: BLE001 — digest tidak boleh mematikan job scheduler
        # F13 — nilai baliknya memang membawa pesan, tapi pemanggilnya adalah JOB
        # SCHEDULER: pesan itu hanya berakhir di satu dokumen `dewi_scheduler_runs`
        # dan tidak pernah dibaca siapa pun. Log-nya yang membuat digest yang mati
        # berminggu-minggu bisa ditemukan.
        _log.exception("[acc-valuation] digest harian item belum dinilai GAGAL "
                       "untuk tanggal %s", day)
        return {"sent": 0, "items": 0, "date": day, "recipients": [],
                "skipped": f"gagal mengirim digest: {type(e).__name__}: {e}"}
