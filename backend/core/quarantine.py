"""core.quarantine — FASE 6 (INV-8): KARANTINA QC sebagai SSOT barang reject.

Masalah yang diselesaikan (BUG-INV-8):
  * GR (`warehouse.py update_receiving`) hanya memasukkan `net_qty = received − rejected`
    ke stok. Qty **reject hilang tanpa jejak fisik** → tidak bisa ditindaklanjuti
    (retur supplier / rework / scrap) dan tidak terlihat di laporan mana pun.
  * QC pasca-terima tidak bisa mengoreksi stok → risiko over-count.

Desain:
  * **Lokasi karantina kanonik** — utamakan zona `wh_*` peran 'karantina'
    (ZN-QRT/ZN-KARANTINA/ZN-QC), fallback + auto-provision `rahaza_locations`
    kode `ZNA-KARANTINA`. SENGAJA **di luar** `location_resolver.list_storage_locations`
    supaya tidak muncul di dropdown penerimaan/transfer normal.
  * **Blokir ketersediaan** — stok karantina ditulis via `stock_service.add` lalu
    `stock_service.reserve` sejumlah qty ⇒ `available_quantity = 0`. Fisik tercatat &
    auditable (ledger `rahaza_stock_ledger`), tapi TIDAK bisa dipakai produksi/BOM/jual.
  * **Jejak per-kejadian** — koleksi `wh_quarantine_items` (satu dok per kejadian
    karantina, punya `remaining_qty` + riwayat `dispositions`).
  * **Nilai (valued)** — `valued=False` bila barang belum pernah masuk nilai persediaan
    (reject saat GR: AP invoice pakai net qty ⇒ belum di-invoice/di-kapitalisasi);
    `valued=True` bila barang sudah masuk stok lalu dipindah ke karantina (re-inspeksi
    pasca-terima). Penentu apakah disposisi perlu jurnal keuangan.

Modul ini TIDAK meng-import `routes.*` (hindari circular import). Posting jurnal
dilakukan pemanggil (`routes/wms_quarantine.py`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core import stock_service
from core.stock_schema import read_qty, read_reserved
from utils.reject_reasons import normalize_reject_reasons, summarize_by_reason
import logging

logger = logging.getLogger(__name__)

QUARANTINE_COLL = "wh_quarantine_items"
QUARANTINE_CODE = "ZNA-KARANTINA"
QUARANTINE_ROLE = "karantina"

# Aksi disposisi yang sah
ACTION_RELEASE = "release"
ACTION_RETURN = "return_supplier"
ACTION_SCRAP = "scrap"
VALID_ACTIONS = (ACTION_RELEASE, ACTION_RETURN, ACTION_SCRAP)


def _now():
    return datetime.now(timezone.utc)


def _uid():
    return str(uuid.uuid4())


def _r(v) -> float:
    return round(float(v or 0), 4)


# ─────────────────────────────────────────────────────────────────────────────
# LOKASI KARANTINA
# ─────────────────────────────────────────────────────────────────────────────
async def get_quarantine_location_id(db) -> str:
    """Resolve (dan auto-provision) lokasi karantina. Selalu balik id yang valid."""
    # 1) zona kanonik wh_* peran 'karantina'
    #
    # 2026-08-07 — DULU `except Exception: pass`. Ini berbahaya HALUS: bila
    # pencarian zona kanonik gagal, fungsi diam-diam jatuh ke lokasi LEGACY,
    # sehingga stok karantina yang seharusnya satu lokasi bisa TERBELAH ke dua
    # id lokasi berbeda tanpa jejak. Angka karantina lalu tampak 0 di satu
    # tempat dan 10 di tempat lain — persis kebingungan yang memakan waktu
    # saat menelusuri INV-4. Fallback-nya tetap dipertahankan (fitur tidak
    # boleh mati), tetapi sekarang SELALU meninggalkan jejak.
    try:
        from core import location_resolver
        zid = await location_resolver.canonical_zone_id_for_role(db, QUARANTINE_ROLE)
        if zid:
            return zid
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[karantina] gagal resolusi zona kanonik peran '%s' — memakai lokasi legacy "
            "%s. Stok karantina bisa terbelah antar lokasi bila ini berulang: %s",
            QUARANTINE_ROLE, QUARANTINE_CODE, e)
    # 2) legacy rahaza_locations (auto-create bila belum ada)
    loc = await db.rahaza_locations.find_one({"code": QUARANTINE_CODE}, {"_id": 0, "id": 1})
    if loc:
        return loc["id"]
    new_id = _uid()
    await db.rahaza_locations.insert_one({
        "id": new_id,
        "code": QUARANTINE_CODE,
        "name": "Area Karantina QC",
        "description": "Barang reject QC menunggu keputusan (retur supplier / rework / scrap). "
                       "Stok di sini DIBLOKIR (tidak tersedia untuk produksi/penjualan).",
        "type": "warehouse",
        "role": QUARANTINE_ROLE,
        "blocked": True,
        "active": True,
        "created_at": _now(),
    })
    return new_id


async def get_quarantine_location_info(db) -> dict:
    """Info lokasi karantina utk UI: {id, code, name}."""
    qid = await get_quarantine_location_id(db)
    code, name = QUARANTINE_CODE, ""
    try:
        from core import location_resolver
        disp = (await location_resolver.build_display_map(db, [qid])).get(qid) or {}
        # build_display_map balik {id: {code, name, source}} — ambil string-nya
        name = disp.get("name") or ""
        code = disp.get("code") or code
    except Exception as e:  # noqa: BLE001 — hanya penamaan untuk UI; ada fallback
        # di bawah. Tetap dicatat supaya kegagalan resolusi nama tidak senyap.
        logger.debug("[karantina] gagal resolusi nama lokasi karantina %s: %s", qid, e)
    if not name:
        loc = await db.rahaza_locations.find_one({"id": qid}, {"_id": 0, "name": 1, "code": 1}) or {}
        name = loc.get("name") or "Area Karantina QC"
        code = loc.get("code") or code
    return {"id": qid, "code": code, "name": name}


# ─────────────────────────────────────────────────────────────────────────────
# MASUK KARANTINA
# ─────────────────────────────────────────────────────────────────────────────
async def quarantine_in(db, *, material_id: str, qty: float, unit: str = "pcs",
                        source: dict | None = None, reject_reasons: list | None = None,
                        valued: bool = False, unit_cost: float | None = None,
                        notes: str = "", actor: dict | None = None,
                        from_location_id: str | None = None) -> dict:
    """Masukkan `qty` material ke KARANTINA (stok fisik tercatat, available = 0).

    from_location_id = None  → barang BELUM pernah masuk stok (reject saat GR) ⇒ `add`.
    from_location_id = <loc> → barang SUDAH di stok ⇒ `move` (issue asal → add karantina).
    """
    qty = _r(qty)
    if qty <= 0:
        raise ValueError("qty karantina harus > 0")
    qloc = await get_quarantine_location_id(db)
    if from_location_id and from_location_id == qloc:
        raise ValueError("lokasi asal tidak boleh sama dengan lokasi karantina")

    mat = await db.rahaza_materials.find_one(
        {"id": material_id}, {"_id": 0, "code": 1, "name": 1, "unit": 1, "unit_cost": 1, "hpp": 1, "type": 1}) or {}
    if unit_cost is None:
        unit_cost = float(mat.get("unit_cost") or mat.get("hpp") or 0)

    ref = {"source": "quarantine_in", "reason": "qc_reject", **(source or {})}
    meta = {
        "unit": unit or mat.get("unit") or "pcs",
        "material_code": mat.get("code"),
        "material_name": mat.get("name"),
        "quarantine": True,
    }

    if from_location_id:
        await stock_service.move(material_id, from_location_id, qloc, qty,
                                 meta=meta, ref=ref, actor=actor, db=db)
    else:
        await stock_service.add(material_id, qloc, qty, meta=meta, ref=ref, actor=actor, db=db)

    # Blokir ketersediaan: reserve sebesar qty yang baru masuk.
    #
    # 2026-08-07 — DULU `except Exception: pass` dengan komentar "tidak fatal".
    # Komentar itu MENYESATKAN: kalau reserve gagal, barang REJECT tetap terhitung
    # sebagai stok TERSEDIA (`available = qty - reserved`), sehingga barang cacat
    # bisa ikut dipilih untuk produksi atau DIKIRIM KE PEMBELI. Penanda
    # `quarantine/blocked` di baris stok hanya menyembunyikannya dari dropdown UI
    # — ia tidak menghalangi jalur mana pun yang menghitung `available`.
    # Sekarang kegagalannya SELALU dicatat sebagai ERROR beserta konteksnya.
    blocked_ok = True
    try:
        await stock_service.reserve(material_id, qloc, qty,
                                   ref={**ref, "reason": "quarantine_block"}, actor=actor, db=db)
    except Exception as e:  # noqa: BLE001
        blocked_ok = False
        logger.error(
            "[karantina] GAGAL memblokir ketersediaan %s unit material %s di lokasi %s — "
            "barang REJECT masih terhitung tersedia dan bisa terpakai/terkirim. "
            "Segera periksa: %s", qty, material_id, qloc, e)
    await db[stock_service.STOCK].update_one(
        {"material_id": material_id, "location_id": qloc},
        {"$set": {"quarantine": True, "blocked": True}})

    doc = {
        "id": _uid(),
        "material_id": material_id,
        "material_code": mat.get("code", ""),
        "material_name": mat.get("name", ""),
        "material_type": mat.get("type", ""),
        "unit": unit or mat.get("unit") or "pcs",
        "unit_cost": _r(unit_cost),
        "qty": qty,
        "remaining_qty": qty,
        "location_id": qloc,
        "valued": bool(valued),
        "status": "open",
        "source": source or {},
        # SSOT bentuk alasan reject — dinormalisasi DI SINI (gerbang tulis terakhir)
        # supaya tak ada penulis yang bisa menyimpan bentuk liar (mis. list of string
        # dari `routes/rahaza_grn_qc.py`) yang dulu merobohkan `summary()` dengan 500.
        "reject_reasons": normalize_reject_reasons(reject_reasons, default_qty=qty),
        "notes": notes,
        # Ketersediaan benar-benar terblokir? Bila False, barang reject ini MASIH
        # terhitung tersedia dan harus ditangani manual. Disimpan supaya bisa
        # ditampilkan/di-audit, bukan hanya tenggelam di log server.
        "availability_blocked": bool(blocked_ok),
        "dispositions": [],
        "created_at": _now(),
        "created_by": (actor or {}).get("name", ""),
        "created_by_id": (actor or {}).get("id", ""),
        "updated_at": _now(),
    }
    await db[QUARANTINE_COLL].insert_one(doc)
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# KELUAR KARANTINA (dipakai router; JE ditangani pemanggil)
# ─────────────────────────────────────────────────────────────────────────────
async def quarantine_out(db, *, item: dict, action: str, qty: float,
                         to_location_id: str | None = None,
                         actor: dict | None = None, notes: str = "") -> dict:
    """Terapkan disposisi pada stok karantina. Return dict info mutasi.

    release          → move karantina → `to_location_id` (stok kembali tersedia)
    return_supplier  → issue keluar dari karantina (barang keluar gudang)
    scrap            → issue keluar dari karantina (dibuang)
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"action tidak dikenal: {action}")
    qty = _r(qty)
    if qty <= 0:
        raise ValueError("qty disposisi harus > 0")
    remaining = _r(item.get("remaining_qty") or 0)
    if qty - remaining > 1e-6:
        raise ValueError(f"qty {qty} melebihi sisa karantina {remaining}")

    qloc = item.get("location_id") or await get_quarantine_location_id(db)
    material_id = item["material_id"]
    ref = {"source": f"quarantine_{action}", "quarantine_item_id": item["id"],
           "quarantine_no": item.get("id"), "notes": notes}

    # Lepas blokir (reserved) sebesar qty agar mutasi fisik boleh jalan.
    #
    # 2026-08-07 — DULU `except Exception: pass`. Itu MERUSAK ANGKA STOK diam-diam:
    # `stock_service.issue()` menjaga qty FISIK (`qty >= qty_keluar`), BUKAN qty
    # tersedia. Jadi kalau pelepasan blokir gagal tetapi disposisi tetap lanjut,
    # qty fisik berkurang sementara `reserved_quantity` tetap ⇒
    # `available_quantity = qty - reserved` menjadi NEGATIF, tanpa error, tanpa
    # log, tanpa ada yang tahu. Stok "tersedia" yang negatif merusak semua
    # keputusan sesudahnya (produksi, penjualan, opname).
    #
    # Sekarang: SELALU dicatat, dan operasinya DIHENTIKAN. Menghentikan lebih
    # aman daripada melanjutkan — satu-satunya penyebab gagal yang wajar adalah
    # baris stoknya tidak ada, dan dalam kasus itu `move()`/`issue()` di bawah
    # PASTI gagal juga. Jadi tidak ada alur sah yang jadi mati karena ini.
    try:
        await stock_service.release(material_id, qloc, qty,
                                   ref={**ref, "reason": "quarantine_unblock"}, actor=actor, db=db)
    except Exception as e:  # noqa: BLE001
        logger.error(
            "[karantina] GAGAL melepas blokir sebelum disposisi %s — dihentikan supaya "
            "stok tersedia tidak jadi negatif. item=%s material=%s lokasi=%s qty=%s: %s",
            action, item.get("id"), material_id, qloc, qty, e)
        raise ValueError(
            f"Blokir karantina tidak bisa dilepas untuk {qty} unit "
            f"(material {item.get('material_code') or material_id}). "
            "Disposisi dibatalkan agar stok tersedia tidak menjadi negatif. "
            "Periksa baris stok di lokasi karantina, lalu ulangi."
        ) from e

    if action == ACTION_RELEASE:
        if not to_location_id:
            raise ValueError("to_location_id wajib untuk release")
        if to_location_id == qloc:
            raise ValueError("lokasi tujuan release tidak boleh lokasi karantina")
        await stock_service.move(material_id, qloc, to_location_id, qty,
                                 meta={"quarantine": False}, ref=ref, actor=actor, db=db)
        # baris tujuan bukan karantina
        await db[stock_service.STOCK].update_one(
            {"material_id": material_id, "location_id": to_location_id},
            {"$set": {"quarantine": False, "blocked": False}})
    else:
        await stock_service.issue(material_id, qloc, qty, ref=ref, actor=actor, db=db)

    new_remaining = _r(remaining - qty)
    disp = {
        "id": _uid(),
        "action": action,
        "qty": qty,
        "to_location_id": to_location_id if action == ACTION_RELEASE else None,
        "notes": notes,
        "at": _now(),
        "by": (actor or {}).get("name", ""),
        "by_id": (actor or {}).get("id", ""),
    }
    await db[QUARANTINE_COLL].update_one(
        {"id": item["id"]},
        {"$set": {"remaining_qty": new_remaining,
                  "status": "open" if new_remaining > 1e-6 else "closed",
                  "updated_at": _now()},
         "$push": {"dispositions": disp}})
    return {"disposition": disp, "remaining_qty": new_remaining,
            "closed": new_remaining <= 1e-6, "location_id": qloc}


# ─────────────────────────────────────────────────────────────────────────────
# BACA
# ─────────────────────────────────────────────────────────────────────────────
async def list_items(db, *, status: str | None = "open", material_id: str | None = None,
                     source_id: str | None = None, limit: int = 500,
                     needs_action: bool = False) -> list:
    q: dict = {}
    if status and status != "all":
        q["status"] = status
    if material_id:
        q["material_id"] = material_id
    if source_id:
        q["source.id"] = source_id
    rows = await db[QUARANTINE_COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    audit = await availability_audit(db)
    kurang = audit["shortfall_by_group"]
    for r in rows:
        r["value"] = _r(_r(r.get("remaining_qty")) * _r(r.get("unit_cost")))
        r["age_days"] = _age_days(r.get("created_at"))
        # `availability_blocked` DIHITUNG dari stok nyata (bukan sekadar membaca flag
        # yang disimpan saat karantina dibuat), supaya juga menangkap kasus stok yang
        # blokirnya hilang SETELAHNYA. Flag saat pembuatan tetap dibawa untuk audit.
        r["availability_blocked_at_intake"] = r.get("availability_blocked", True)
        gkey = f"{r.get('material_id')}|{r.get('location_id')}"
        r["availability_shortfall"] = kurang.get(gkey, 0.0) if r.get("status") == "open" else 0.0
        r["availability_blocked"] = not (r["availability_shortfall"] > 1e-6)
    if needs_action:
        rows = [r for r in rows if not r.get("availability_blocked")]
    return rows


async def availability_audit(db) -> dict:
    """Apakah SEMUA stok karantina yang masih terbuka benar-benar terblokir?

    2026-08-07 — dibuat saat menutup `except Exception: pass` di `quarantine_in()`.
    Menyimpan flag `availability_blocked` saat pembuatan saja TIDAK CUKUP, karena:
      * dokumen karantina LAMA (sebelum flag ada) tidak punya nilai apa pun, dan
      * blokir bisa hilang SETELAH karantina dibuat (mis. jalur lain memanggil
        `release`/`unreserve` pada material yang sama).

    Jadi kebenarannya diambil dari SSOT stok, bukan dari flag: untuk setiap
    (material, lokasi karantina), jumlah `remaining_qty` seluruh item terbuka HARUS
    tertutup penuh oleh `reserved_quantity` baris stoknya. Selisihnya = qty barang
    REJECT yang saat ini MASIH terhitung tersedia dan bisa ikut terpakai/terkirim.

    Return: {"shortfall_by_group": {"<material>|<lokasi>": qty}, "total_shortfall": qty,
             "groups": [ {...} ], "affected_items": n}
    """
    open_rows = await db[QUARANTINE_COLL].find(
        {"status": "open"},
        {"_id": 0, "id": 1, "material_id": 1, "location_id": 1, "remaining_qty": 1,
         "material_code": 1, "material_name": 1, "unit": 1},
    ).to_list(5000)
    if not open_rows:
        return {"shortfall_by_group": {}, "total_shortfall": 0.0, "groups": [],
                "affected_items": 0}

    grup: dict = {}
    for r in open_rows:
        key = f"{r.get('material_id')}|{r.get('location_id')}"
        g = grup.setdefault(key, {
            "material_id": r.get("material_id"), "location_id": r.get("location_id"),
            "material_code": r.get("material_code", ""), "material_name": r.get("material_name", ""),
            "unit": r.get("unit", "pcs"), "qty_karantina": 0.0, "items": [],
        })
        g["qty_karantina"] = _r(g["qty_karantina"] + _r(r.get("remaining_qty")))
        g["items"].append(r.get("id"))

    shortfall: dict = {}
    groups: list = []
    affected = 0
    for key, g in grup.items():
        row = await db[stock_service.STOCK].find_one(
            {"material_id": g["material_id"], "location_id": g["location_id"]}, {"_id": 0})
        reserved = read_reserved(row) if row else 0.0
        fisik = read_qty(row) if row else 0.0
        kurang = _r(max(0.0, g["qty_karantina"] - reserved))
        g.update({"reserved": _r(reserved), "qty_fisik": _r(fisik), "shortfall": kurang,
                  "stock_row_ada": bool(row)})
        if kurang > 1e-6:
            shortfall[key] = kurang
            affected += len(g["items"])
        groups.append(g)
    return {
        "shortfall_by_group": shortfall,
        "total_shortfall": _r(sum(shortfall.values())),
        "groups": groups,
        "affected_items": affected,
    }


async def retry_block(db, *, item_id: str, actor: dict | None = None) -> dict:
    """Coba blokir ULANG ketersediaan untuk satu item karantina.

    Dipakai tombol "Coba Blokir Ulang" di layar Karantina: tanpa ini, kegagalan
    blokir hanya bisa dibetulkan lewat database, dan daftar "perlu tindakan manual"
    jadi sekadar pengumuman yang tidak bisa ditindak.
    """
    item = await db[QUARANTINE_COLL].find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise ValueError("Item karantina tidak ditemukan")
    if item.get("status") != "open":
        raise ValueError("Item karantina sudah ditutup — tidak ada yang perlu diblokir")
    material_id = item.get("material_id")
    qloc = item.get("location_id") or await get_quarantine_location_id(db)
    audit = await availability_audit(db)
    kurang = audit["shortfall_by_group"].get(f"{material_id}|{qloc}", 0.0)
    if kurang <= 1e-6:
        await db[QUARANTINE_COLL].update_one(
            {"id": item_id}, {"$set": {"availability_blocked": True, "updated_at": _now()}})
        return {"ok": True, "sudah_terblokir": True, "diblokir": 0.0,
                "pesan": "Ketersediaan sudah terblokir penuh — tidak ada tindakan yang perlu."}
    try:
        await stock_service.reserve(material_id, qloc, kurang,
                                    ref={"source": "quarantine_in", "reason": "quarantine_block_retry",
                                         "quarantine_item_id": item_id},
                                    actor=actor, db=db)
    except Exception as e:  # noqa: BLE001
        logger.error(
            "[karantina] COBA BLOKIR ULANG GAGAL untuk item %s (material %s lokasi %s, "
            "kurang %s) — barang reject masih terhitung tersedia: %s",
            item_id, material_id, qloc, kurang, e)
        await db[QUARANTINE_COLL].update_one(
            {"id": item_id}, {"$set": {"availability_blocked": False, "updated_at": _now(),
                                       "availability_last_error": str(e)[:300]}})
        raise
    await db[stock_service.STOCK].update_one(
        {"material_id": material_id, "location_id": qloc},
        {"$set": {"quarantine": True, "blocked": True}})
    await db[QUARANTINE_COLL].update_one(
        {"id": item_id}, {"$set": {"availability_blocked": True, "updated_at": _now(),
                                   "availability_last_error": ""}})
    logger.info("[karantina] blokir ulang BERHASIL: %s unit material %s di lokasi %s (item %s)",
                kurang, material_id, qloc, item_id)
    return {"ok": True, "sudah_terblokir": False, "diblokir": _r(kurang),
            "pesan": f"Berhasil memblokir {_r(kurang)} unit. Barang reject ini tidak lagi "
                     f"terhitung tersedia."}


def _age_days(ts) -> int:
    if not ts:
        return 0
    try:
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0, (_now() - ts).days)
    except Exception:
        return 0


async def summary(db) -> dict:
    rows = await db[QUARANTINE_COLL].find({}, {"_id": 0}).to_list(5000)
    open_rows = [r for r in rows if r.get("status") == "open"]
    # `by_reason` DULU melakukan `rr.get("code")` langsung sehingga satu dokumen lama
    # berbentuk `["KOTOR"]` (list of string) mematikan SELURUH KPI dengan HTTP 500.
    # Sekarang agregasinya lewat SSOT yang tahan bentuk apa pun (utils/reject_reasons.py).
    by_reason = summarize_by_reason(open_rows, qty_field="remaining_qty")
    disposed = sum(len(r.get("dispositions") or []) for r in rows
                   if isinstance(r.get("dispositions"), (list, tuple)))
    qloc = await get_quarantine_location_info(db)
    audit = await availability_audit(db)
    return {
        "open_items": len(open_rows),
        "open_qty": _r(sum(_r(r.get("remaining_qty")) for r in open_rows)),
        "open_value": _r(sum(_r(r.get("remaining_qty")) * _r(r.get("unit_cost")) for r in open_rows)),
        "valued_items": len([r for r in open_rows if r.get("valued")]),
        "unvalued_items": len([r for r in open_rows if not r.get("valued")]),
        "closed_items": len([r for r in rows if r.get("status") == "closed"]),
        "dispositions_total": disposed,
        "oldest_age_days": max([_age_days(r.get("created_at")) for r in open_rows] or [0]),
        "by_reason": by_reason,
        "location": qloc,
        # 2026-08-07 — KPI BARU: barang reject yang blokirnya GAGAL/HILANG sehingga
        # masih terhitung TERSEDIA (bisa terpakai produksi atau terkirim ke pembeli).
        # Ini yang membuat kegagalan `reserve` di `quarantine_in()` bisa ditindak,
        # bukan hanya tenggelam di log server.
        "unblocked_items": audit["affected_items"],
        "unblocked_qty": audit["total_shortfall"],
        "unblocked_groups": [g for g in audit["groups"] if g.get("shortfall", 0) > 1e-6],
    }


async def quarantine_qty_map(db, material_ids=None) -> dict:
    """{material_id: qty} yang sedang berada di lokasi karantina (fisik ada, tidak tersedia)."""
    qloc = await get_quarantine_location_id(db)
    q: dict = {"location_id": qloc}
    if material_ids is not None:
        ids = [m for m in material_ids if m]
        if not ids:
            return {}
        q["material_id"] = {"$in": ids}
    rows = await db[stock_service.STOCK].find(q, {"_id": 0}).to_list(20000)
    out: dict = {}
    for r in rows:
        mid = r.get("material_id")
        if mid:
            out[mid] = _r(out.get(mid, 0) + read_qty(r))
    return out
