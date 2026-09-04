"""
core/production_qty_ledger.py — SSOT BUKU KUANTITAS PRODUKSI (per job item).

MASALAH YANG DIPERBAIKI (audit 2026-07-31, docs/AUDIT_PRODUKSI_MAKLON_CMT.md):
  `production_job_items` hanya punya `produced_qty`. Tidak ada tempat menyimpan
  hasil QC penerimaan DA, sehingga "dikirim 100, lolos 90, reject 10" hanya hidup
  sebagai angka di `cmt_receipt_lines` dan TIDAK PERNAH kembali ke job / portal
  vendor / ringkasan PO / penutupan PO. 10 pcs reject hilang dari sistem.

BUKU KUANTITAS (semua di `production_job_items`, satuan pcs):
  ordered_qty      qty pesanan PO untuk item ini
  available_qty    material yang benar-benar ada di vendor (hasil inspeksi)
  produced_qty     OUTPUT VENDOR — **TIDAK PERNAH BERKURANG** karena reject.
                   (permintaan owner: "dikirim 100 reject 10 → progress tetap 100")
  qty_declared     qty yang dideklarasikan vendor terkirim ke DA
  qty_accepted     lolos QC DA (masuk stok FG)
  qty_reject       hasil QC DA yang ditolak (kumulatif, tidak turun)
  qty_rework_open  reject yang MASIH menunggu / sedang dikerjakan ulang
  qty_repaired     reject yang berhasil diperbaiki → menambah qty_accepted
  qty_scrap        reject yang dibuang (rugi)

INVARIAN (dijaga guardrail scripts/verify_produksi_maklon_invariants.py):
  produced_qty  >= qty_accepted + qty_reject           (tidak boleh overcount)
  qty_reject    == qty_rework_open + qty_repaired + qty_scrap + qty_reject_undecided
  qty_accepted  == Σ cmt_receipt_lines.qty_actual + Σ permak.qty_fixed (permak_sendiri)

Semua mutasi HANYA lewat modul ini supaya tidak ada lagi dua sumber angka.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

LEDGER_FIELDS = (
    "qty_declared",
    "qty_accepted",
    "qty_reject",
    "qty_rework_open",
    "qty_repaired",
    "qty_scrap",
    # ── SELISIH KIRIM CMT→DA (aturan owner 2026-08-01) ────────────────────────
    # `qty_declared` HANYA berisi barang yang BENAR-BENAR SAMPAI (accepted+reject);
    # klaim vendor disimpan terpisah supaya dua angka tidak saling menimpa.
    "qty_claimed_by_vendor",   # Σ klaim surat jalan vendor (dokumen asli)
    "qty_short_open",          # belum sampai — masih kewajiban vendor (harus dicari/kirim ulang)
    "qty_short_resolved",      # selisih yang sudah diselesaikan (dikirim ulang / diputuskan)
)

FG_LOCATION_CODE = "ZNA-FG"


def _now():
    return datetime.now(timezone.utc)


def _i(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# LOKASI FG — resolusi tahan-banting (SSOT stok butuh location_id yang NYATA)
# ─────────────────────────────────────────────────────────────────────────────
async def resolve_fg_location_id(db) -> str | None:
    """id lokasi gudang FG kanonik.

    BUG YANG DIPERBAIKI: `dewi_cmt_packing.approve` dulu menulis baris stok dengan
    `location: "gudang_fg"` (string bebas) dan TANPA `location_id`, sehingga baris
    itu tidak terlihat oleh `core/stock_service` (kunci: material_id+location_id),
    tidak terlihat opname, karantina, maupun rekonsiliasi stok. FG dari CMT jadi
    stok "hantu" di luar SSOT.
    """
    try:
        from core.location_resolver import canonical_zone_id_for_role
        zid = await canonical_zone_id_for_role(db, "fg")
        if zid:
            return zid
    except Exception:
        logger.debug("canonical_zone_id_for_role gagal", exc_info=True)
    loc = await db.rahaza_locations.find_one(
        {"code": FG_LOCATION_CODE}, {"_id": 0, "id": 1})
    if loc:
        return loc["id"]
    # fallback terakhir: lokasi storage aktif apa pun bertipe zona
    loc = await db.rahaza_locations.find_one(
        {"type": "zona", "active": True}, {"_id": 0, "id": 1})
    return loc["id"] if loc else None


# ─────────────────────────────────────────────────────────────────────────────
# BACA / BACKFILL
# ─────────────────────────────────────────────────────────────────────────────
async def ensure_ledger(db, job_item: dict) -> dict:
    """Isi field buku kuantitas yang belum ada (idempoten, aman untuk data lama)."""
    if not job_item:
        return job_item
    missing = {f: 0 for f in LEDGER_FIELDS if f not in job_item}
    if missing:
        await db.production_job_items.update_one(
            {"id": job_item["id"]}, {"$set": missing})
        job_item.update(missing)
    return job_item


def ledger_view(ji: dict) -> dict:
    """Bentuk seragam untuk dibaca UI/laporan (tidak menulis)."""
    produced = _i(ji.get("produced_qty"))
    accepted = _i(ji.get("qty_accepted"))
    reject = _i(ji.get("qty_reject"))
    rework_open = _i(ji.get("qty_rework_open"))
    repaired = _i(ji.get("qty_repaired"))
    scrap = _i(ji.get("qty_scrap"))
    declared = _i(ji.get("qty_declared"))
    short_open = _i(ji.get("qty_short_open"))
    short_resolved = _i(ji.get("qty_short_resolved"))
    claimed = _i(ji.get("qty_claimed_by_vendor")) or (declared + short_open + short_resolved)
    return {
        "ordered_qty": _i(ji.get("ordered_qty")),
        "available_qty": _i(ji.get("available_qty")),
        "produced_qty": produced,
        "qty_declared": declared,
        "qty_accepted": accepted,
        "qty_reject": reject,
        "qty_rework_open": rework_open,
        "qty_repaired": repaired,
        "qty_scrap": scrap,
        # selisih kirim (barang TIDAK sampai) — Kasus 2 aturan owner
        "qty_claimed_by_vendor": claimed,
        "qty_short_open": short_open,
        "qty_short_resolved": short_resolved,
        # reject yang belum diputuskan mau dipermak sendiri / retur ke CMT / buang
        "qty_reject_undecided": max(0, reject - rework_open - repaired - scrap),
        "reject_rate_pct": round(reject / produced * 100, 1) if produced else 0.0,
    }


async def resolve_job_item_for_line(db, line: dict) -> dict | None:
    """Cari job item pemilik sebuah `cmt_receipt_lines`.

    Prioritas: job_item_id eksplisit → po_item_id (job terbaru).
    """
    if line.get("job_item_id"):
        ji = await db.production_job_items.find_one(
            {"id": line["job_item_id"]}, {"_id": 0})
        if ji:
            return ji
    if line.get("po_item_id"):
        rows = await db.production_job_items.find(
            {"po_item_id": line["po_item_id"]}, {"_id": 0}
        ).sort("created_at", -1).to_list(10)
        if rows:
            return rows[0]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# MUTASI 1 — HASIL QC PENERIMAAN DA (dipanggil saat penerimaan CMT diselesaikan)
# ─────────────────────────────────────────────────────────────────────────────
async def apply_receipt_result(db, receipt: dict, lines: list, actor: dict | None = None) -> dict:
    """Teruskan hasil QC penerimaan ke buku kuantitas job item + karantina reject.

    IDEMPOTEN: ditandai `qty_ledger_applied_at` di dokumen penerimaan.

    ATURAN OWNER 2026-08-01 (SELISIH KIRIM — Kasus 2, barang TIDAK sampai):
      "dokumen data apa yang dikirimkan harus sesuai" ⇒ dokumen penerimaan
      DIKOREKSI menjadi qty yang benar-benar sampai (accepted + reject), klaim
      vendor disimpan terpisah (`qty_claimed_by_cmt` di baris,
      `qty_claimed_by_vendor` di buku kuantitas), dan kekurangannya menjadi
      `qty_short_open` = KEWAJIBAN VENDOR (sisa kirim vendor naik lagi supaya
      bisa dikirim ulang). Bukan klaim finansial otomatis.

    Efek per baris:
      claimed  = qty_claimed_by_cmt (atau qty_shipped_by_cmt bila kosong)
      arrived  = qty_actual + reject_qty        ← INI yang jadi dokumen resmi
      short    = max(0, claimed − arrived)      ← identitas selisih kirim
      job_item.qty_claimed_by_vendor += claimed
      job_item.qty_declared          += arrived   (BUKAN klaim!)
      job_item.qty_accepted          += qty_actual
      job_item.qty_reject            += reject_qty
      job_item.qty_rework_open       += reject_qty   (menunggu keputusan permak/retur)
      job_item.qty_short_open        += short
      produced_qty                   TIDAK DIUBAH (produksi vendor tetap — Kasus 1)
      reject fisik                   → KARANTINA (stok tercatat, available 0)
      barang yang sampai juga MENUTUP selisih lama item yang sama (kirim ulang).
    """
    out = {"applied": False, "job_items": 0, "quarantined": 0,
           "accepted": 0, "rejected": 0, "short": 0, "short_resolved": 0,
           "shorts": [], "errors": []}
    if receipt.get("qty_ledger_applied_at"):
        out["already_applied"] = True
        return out

    from core import quarantine as qmod
    from core import short_shipment as shortmod

    for ln in lines:
        qty_actual = _i(ln.get("qty_actual"))
        reject_qty = _i(ln.get("reject_qty"))
        arrived = qty_actual + reject_qty
        claimed = _i(ln.get("qty_claimed_by_cmt")) or _i(ln.get("qty_shipped_by_cmt")) or arrived
        short_qty = max(0, claimed - arrived)
        ji = await resolve_job_item_for_line(db, ln)

        # ── Dokumen = kenyataan: baris penerimaan dikoreksi ke qty yang SAMPAI ──
        await db.cmt_receipt_lines.update_one(
            {"id": ln["id"]},
            {"$set": {"qty_claimed_by_cmt": claimed,
                      "qty_shipped_by_cmt": arrived,
                      "qty_short": short_qty,
                      "qty_short_resolved": 0,
                      "short_status": "open" if short_qty > 0 else "",
                      "updated_at": _now()}})
        ln["qty_claimed_by_cmt"] = claimed
        ln["qty_shipped_by_cmt"] = arrived
        ln["qty_short"] = short_qty

        # ── Barang yang sampai menutup selisih LAMA (kirim ulang) ─────────────
        if arrived > 0:
            try:
                res = await shortmod.resolve_cmt_shorts_on_arrival(
                    db, po_item_id=ln.get("po_item_id"),
                    job_item_id=(ji or {}).get("id") or ln.get("job_item_id"),
                    qty=arrived, receipt=receipt, line=ln, actor=actor,
                    exclude_line_ids=[ln["id"]])
                out["short_resolved"] += _i(res.get("resolved"))
            except Exception as e:  # noqa: BLE001
                logger.exception("penutupan selisih lama gagal (line %s)", ln.get("id"))
                out["errors"].append(f"penutupan selisih gagal: {e}")

        # ── Selisih BARU (klaim > yang sampai) ────────────────────────────────
        if short_qty > 0:
            try:
                sdoc = await shortmod.record_cmt_short(
                    db, receipt=receipt, line=ln, claimed=claimed, arrived=arrived,
                    job_item=ji, actor=actor)
                out["short"] += short_qty
                if sdoc:
                    out["shorts"].append({"short_number": sdoc.get("short_number"),
                                          "sku": ln.get("sku_code"), "qty_short": short_qty})
            except Exception as e:  # noqa: BLE001
                logger.exception("pencatatan selisih kirim gagal (line %s)", ln.get("id"))
                out["errors"].append(f"pencatatan selisih gagal: {e}")

        if ji:
            await ensure_ledger(db, ji)
            inc = {
                "qty_claimed_by_vendor": claimed,
                "qty_declared": arrived,
                "qty_accepted": qty_actual,
                "qty_reject": reject_qty,
                "qty_rework_open": reject_qty,
                "qty_short_open": short_qty,
            }
            inc = {k: v for k, v in inc.items() if v}
            if inc:
                await db.production_job_items.update_one(
                    {"id": ji["id"]},
                    {"$inc": inc, "$set": {"updated_at": _now()}})
                out["job_items"] += 1
        else:
            out["errors"].append(
                f"baris {ln.get('sku_code') or ln.get('id')} tanpa job item "
                "(po_item_id/job_item_id kosong) — angka QC tidak bisa dipropagasi")
        out["accepted"] += qty_actual
        out["rejected"] += reject_qty

        # ── reject fisik masuk KARANTINA (bukan hilang) ──
        if reject_qty > 0:
            material_id = ln.get("fg_material_id") or ""
            if not material_id and ln.get("sku_code"):
                mat = await db.rahaza_materials.find_one(
                    {"type": "fg", "code": ln["sku_code"]}, {"_id": 0, "id": 1})
                material_id = (mat or {}).get("id", "")
            if material_id:
                try:
                    await qmod.quarantine_in(
                        db, material_id=material_id, qty=reject_qty, unit="pcs",
                        source={"type": "cmt_receipt",
                                "receipt_id": receipt.get("id"),
                                "receipt_code": receipt.get("receipt_code"),
                                "receipt_line_id": ln.get("id"),
                                "po_id": receipt.get("po_id"),
                                "po_number": receipt.get("po_number"),
                                "vendor_id": receipt.get("cmt_vendor_id"),
                                "vendor_name": receipt.get("cmt_name"),
                                "job_item_id": (ji or {}).get("id"),
                                "sku": ln.get("sku_code")},
                        reject_reasons=[{"reason": ln.get("reject_reason") or "qc_reject",
                                         "qty": reject_qty}],
                        notes=f"Reject QC penerimaan {receipt.get('receipt_code')}",
                        actor=actor)
                    out["quarantined"] += reject_qty
                except Exception as e:  # noqa: BLE001
                    logger.exception("karantina reject gagal (line %s)", ln.get("id"))
                    out["errors"].append(f"karantina gagal: {e}")
            else:
                out["errors"].append(
                    f"reject {reject_qty} pcs SKU {ln.get('sku_code')} tidak bisa "
                    "dikarantina — master FG tidak ditemukan")

    await db.cmt_receipts.update_one(
        {"id": receipt["id"]},
        {"$set": {"qty_ledger_applied_at": _now().isoformat(),
                  "qty_ledger_result": {k: out[k] for k in
                                        ("job_items", "quarantined", "accepted", "rejected",
                                         "short", "short_resolved")}}})
    out["applied"] = True
    return out


# ─────────────────────────────────────────────────────────────────────────────
# MUTASI 2 — STOK FG LOLOS QC (lewat SSOT stok, bukan tulis mentah)
# ─────────────────────────────────────────────────────────────────────────────
async def post_fg_accepted(db, *, material_id: str, qty: int, ref: dict,
                           actor: dict | None = None, meta: dict | None = None) -> dict:
    """Tambah stok FG lewat `core/stock_service` supaya baris punya `location_id`
    kanonik, tercatat di ledger mutasi, dan terlihat opname/rekonsiliasi.

    SESI #34 — barang jadi yang masuk gudang juga MEMBAWA BIAYANYA: satu lapisan
    HPP batch (FIFO) dicatat lewat `core/fg_cost_layers`. Tanpa ini, upah jahit
    yang diisi di SPK dan ongkos permak tidak pernah sampai ke HPP.
    """
    from core import stock_service
    loc = await resolve_fg_location_id(db)
    if not loc:
        raise RuntimeError("lokasi gudang FG (ZNA-FG) tidak ditemukan — "
                           "buat lokasi dulu di Master Lokasi Gudang")
    row = await stock_service.add(material_id, loc, qty,
                                  meta={"inventory_category": "fg_internal",
                                        "ownership": "cv_da", **(meta or {})},
                                  ref=ref, actor=actor, db=db)
    layer = None
    try:
        from core import fg_cost_layers as fcl
        po_item = None
        poi_id = (ref or {}).get("po_item_id") or (meta or {}).get("po_item_id")
        if poi_id:
            po_item = await db.po_items.find_one({"id": poi_id}, {"_id": 0})
        layer = await fcl.push_layer(db, material_id=material_id, qty=qty,
                                     po_item=po_item or {}, ref=ref, actor=actor)
    except Exception:  # noqa: BLE001
        # Stok fisik TIDAK boleh gagal karena biaya gagal dihitung — tetapi
        # kegagalannya harus terlihat di log, bukan hilang.
        logger.exception("lapisan HPP batch gagal dicatat (material=%s qty=%s)", material_id, qty)
    return {"location_id": loc, "row": row, "cost_layer": layer}


# ─────────────────────────────────────────────────────────────────────────────
# MUTASI 3 — HASIL REWORK / PERMAK
# ─────────────────────────────────────────────────────────────────────────────
async def apply_rework_outcome(db, permak: dict, *, qty_fixed: int, qty_scrap: int,
                               actor: dict | None = None) -> dict:
    """Tutup lingkaran reject → rework.

    permak_sendiri  : barang ada di karantina DA.
                      qty_fixed → dilepas karantina ke gudang FG (stok +) & accepted +
                      qty_scrap → dikeluarkan dari karantina (dibuang) & scrap +
    retur_ke_cmt    : barang sudah dikembalikan ke vendor saat permak dibuat.
                      Penyelesaian TIDAK menambah stok di sini — stok bertambah saat
                      barang rework diterima kembali lewat penerimaan CMT (pipeline benar).
    """
    out = {"stock_released": 0, "scrapped": 0, "ledger": None, "mode": permak.get("permak_type")}
    from core import quarantine as qmod

    job_item = None
    if permak.get("po_item_id"):
        rows = await db.production_job_items.find(
            {"po_item_id": permak["po_item_id"]}, {"_id": 0}
        ).sort("created_at", -1).to_list(5)
        job_item = rows[0] if rows else None

    is_return_to_cmt = (permak.get("permak_type") == "retur_ke_cmt")

    # ── stok karantina ──
    if not is_return_to_cmt:
        q_item = None
        if permak.get("source_receipt_line_id"):
            q_item = await db.wh_quarantine_items.find_one(
                {"source.receipt_line_id": permak["source_receipt_line_id"],
                 "status": "open"}, {"_id": 0})
        if q_item:
            fg_loc = await resolve_fg_location_id(db)
            if qty_fixed > 0 and fg_loc:
                try:
                    await qmod.quarantine_out(db, item=q_item, action="release",
                                              qty=min(qty_fixed, _i(q_item.get("remaining_qty"))),
                                              to_location_id=fg_loc, actor=actor,
                                              notes=f"Permak {permak.get('permak_number')} berhasil")
                    out["stock_released"] = qty_fixed
                    q_item = await db.wh_quarantine_items.find_one(
                        {"id": q_item["id"]}, {"_id": 0})
                except Exception as e:  # noqa: BLE001
                    logger.exception("release karantina gagal")
                    out["error_release"] = str(e)
            if qty_scrap > 0 and q_item:
                try:
                    await qmod.quarantine_out(db, item=q_item, action="scrap",
                                              qty=min(qty_scrap, _i(q_item.get("remaining_qty"))),
                                              actor=actor,
                                              notes=f"Permak {permak.get('permak_number')} gagal → buang")
                    out["scrapped"] = qty_scrap
                except Exception as e:  # noqa: BLE001
                    logger.exception("scrap karantina gagal")
                    out["error_scrap"] = str(e)
        else:
            out["warning"] = ("item karantina untuk baris penerimaan ini tidak ditemukan — "
                              "stok tidak diubah (buku kuantitas tetap diperbarui)")

    # ── buku kuantitas ──
    if job_item:
        await ensure_ledger(db, job_item)
        inc = {"qty_rework_open": -(qty_fixed + qty_scrap)}
        if not is_return_to_cmt:
            if qty_fixed:
                inc["qty_repaired"] = qty_fixed
                inc["qty_accepted"] = qty_fixed
            if qty_scrap:
                inc["qty_scrap"] = qty_scrap
        else:
            # retur ke CMT: reject keluar dari "menunggu" menjadi "sedang dikerjakan vendor"
            # accepted akan naik lewat penerimaan rework.
            if qty_scrap:
                inc["qty_scrap"] = qty_scrap
        inc = {k: v for k, v in inc.items() if v}
        if inc:
            await db.production_job_items.update_one(
                {"id": job_item["id"]}, {"$inc": inc, "$set": {"updated_at": _now()}})
        fresh = await db.production_job_items.find_one({"id": job_item["id"]}, {"_id": 0})
        out["ledger"] = ledger_view(fresh or {})

    # ── FASE E (2026-08-15) — HASIL PERMAK MEMBUKA KAPASITAS KIRIM KE BUYER ──
    # CACAT NYATA yang ditutup di sini (keluhan pemilik: "test-po-2 seharusnya
    # 100, 10 reject sudah diperbaiki, tapi yang tertulis tetap 90"):
    # fungsi ini dulu hanya menaikkan stok FG + buku kuantitas job. Pagar kirim
    # ke buyer justru membaca `cmt_receipt_lines.qty_actual`, jadi 10 pcs yang
    # sudah jadi bagus TIDAK PERNAH boleh dikirim — selamanya.
    #
    # Kenapa memakai field BARU (`qty_reworked_ok`) dan bukan menaikkan
    # `qty_actual` / menurunkan `reject_qty`: angka itu adalah HASIL INSPEKSI
    # saat barang datang. Mengubahnya retroaktif akan membuat laporan variance,
    # AP vendor (dibayar per qty lolos), dan gate INV-14 (buku kuantitas vs
    # dokumen sumber) berubah diam-diam. Menambah field terpisah membuat
    # kapasitas kirim ikut naik TANPA memalsukan riwayat.
    #
    # `retur_ke_cmt` SENGAJA dikecualikan: barangnya dikerjakan ulang vendor dan
    # masuk lagi lewat PENERIMAAN CMT baru (qty_actual naik sendiri di sana).
    # Menambahkannya di sini akan menghitung dua kali.
    if not is_return_to_cmt and permak.get("source_receipt_line_id"):
        line_inc = {}
        if qty_fixed:
            line_inc["qty_reworked_ok"] = qty_fixed
        if qty_scrap:
            line_inc["qty_reject_scrapped"] = qty_scrap
        if line_inc:
            try:
                await db.cmt_receipt_lines.update_one(
                    {"id": permak["source_receipt_line_id"]},
                    {"$inc": line_inc, "$set": {"updated_at": _now()}})
                out["dispatch_capacity"] = {
                    "receipt_line_id": permak["source_receipt_line_id"], **line_inc}
            except Exception as e:  # noqa: BLE001
                logger.exception("gagal menambah kapasitas kirim dari permak %s",
                                 permak.get("permak_number"))
                out["error_dispatch_capacity"] = str(e)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# AGREGASI PO — dipakai quantity-summary / fulfillment / penutupan PO
# ─────────────────────────────────────────────────────────────────────────────
async def po_ledger_totals(db, po_id: str) -> dict:
    """Total buku kuantitas satu PO (dari job items + baris penerimaan)."""
    items = await db.po_items.find({"po_id": po_id}, {"_id": 0, "id": 1, "qty": 1}).to_list(None)
    item_ids = [i["id"] for i in items]
    jis = await db.production_job_items.find(
        {"po_item_id": {"$in": item_ids}}, {"_id": 0}).to_list(None) if item_ids else []
    per_item: dict = {}
    tot = {k: 0 for k in ("ordered", "produced", "declared", "accepted", "reject",
                          "rework_open", "repaired", "scrap",
                          "claimed_by_vendor", "short_open", "short_resolved")}
    tot["ordered"] = sum(_i(i.get("qty")) for i in items)
    for ji in jis:
        v = ledger_view(ji)
        p = per_item.setdefault(ji.get("po_item_id"), {k: 0 for k in tot})
        p["produced"] += v["produced_qty"]
        p["declared"] += v["qty_declared"]
        p["accepted"] += v["qty_accepted"]
        p["reject"] += v["qty_reject"]
        p["rework_open"] += v["qty_rework_open"]
        p["repaired"] += v["qty_repaired"]
        p["scrap"] += v["qty_scrap"]
        p["claimed_by_vendor"] += v["qty_claimed_by_vendor"]
        p["short_open"] += v["qty_short_open"]
        p["short_resolved"] += v["qty_short_resolved"]
    # total dijumlahkan dari per_item supaya 1 po_item dengan banyak job item tidak dobel
    for k in ("produced", "declared", "accepted", "reject", "rework_open", "repaired", "scrap",
              "claimed_by_vendor", "short_open", "short_resolved"):
        tot[k] = sum(p[k] for p in per_item.values())
    tot["reject_undecided"] = max(
        0, tot["reject"] - tot["rework_open"] - tot["repaired"] - tot["scrap"])
    tot["reject_rate_pct"] = round(tot["reject"] / tot["produced"] * 100, 1) if tot["produced"] else 0.0
    return {"totals": tot, "per_po_item": per_item}


# ─────────────────────────────────────────────────────────────────────────────
# ANTREAN REJECT — supaya reject TIDAK PERNAH hilang dari layar
# ─────────────────────────────────────────────────────────────────────────────
async def reject_queue(db, *, po_id: str | None = None, vendor_id: str | None = None,
                       only_open: bool = True, limit: int = 300) -> list:
    """Daftar baris reject dari penerimaan CMT beserta sisa yang belum diputuskan."""
    rq: dict = {"reject_qty": {"$gt": 0}}
    lines = await db.cmt_receipt_lines.find(rq, {"_id": 0}).sort("created_at", -1).to_list(limit * 3)
    rec_ids = list({ln.get("receipt_id") for ln in lines if ln.get("receipt_id")})
    receipts = await db.cmt_receipts.find({"id": {"$in": rec_ids}}, {"_id": 0}).to_list(None) if rec_ids else []
    rmap = {r["id"]: r for r in receipts}
    permaks = await db.dewi_cmt_permak.find(
        {"source_receipt_line_id": {"$in": [ln["id"] for ln in lines]}}, {"_id": 0}
    ).to_list(None) if lines else []
    pmap: dict = {}
    for p in permaks:
        pmap.setdefault(p.get("source_receipt_line_id"), []).append(p)

    out = []
    for ln in lines:
        r = rmap.get(ln.get("receipt_id")) or {}
        if po_id and r.get("po_id") != po_id:
            continue
        if vendor_id and r.get("cmt_vendor_id") != vendor_id:
            continue
        ps = pmap.get(ln["id"], [])
        handled = sum(_i(p.get("qty")) for p in ps)
        undecided = max(0, _i(ln.get("reject_qty")) - handled)
        if only_open and undecided <= 0:
            continue
        out.append({
            "receipt_line_id": ln["id"],
            "receipt_id": r.get("id"),
            "receipt_code": r.get("receipt_code"),
            "receipt_status": r.get("status"),
            "po_id": r.get("po_id"), "po_number": r.get("po_number"),
            "vendor_id": r.get("cmt_vendor_id"), "vendor_name": r.get("cmt_name"),
            "sku": ln.get("sku_code"), "product_name": ln.get("product_name"),
            "color": ln.get("color"), "size": ln.get("size"),
            "qty_declared": _i(ln.get("qty_shipped_by_cmt")),
            "qty_accepted": _i(ln.get("qty_actual")),
            "qty_reject": _i(ln.get("reject_qty")),
            "reject_reason": ln.get("reject_reason", ""),
            "qty_handled": handled,
            "qty_undecided": undecided,
            "permaks": [{"id": p.get("id"), "permak_number": p.get("permak_number"),
                         "permak_type": p.get("permak_type"), "qty": _i(p.get("qty")),
                         "status": p.get("status")} for p in ps],
            "po_item_id": ln.get("po_item_id"),
            "job_item_id": ln.get("job_item_id"),
        })
        if len(out) >= limit:
            break
    return out



# ─────────────────────────────────────────────────────────────────────────────
# MUTASI 4 — STOK FG KELUAR SAAT KIRIM KE BUYER (GAP E, audit 2026-07-31)
# ─────────────────────────────────────────────────────────────────────────────
# BUG NYATA yang diperbaiki: `create_buyer_shipment` TIDAK PERNAH mengeluarkan
# stok FG. Kirim 100 pcs ke buyer → stok FG tetap 100 (`rahaza_fg_movements`
# hanya berisi IN). Nilai persediaan gudang FG menggelembung selamanya.
class FGStockShortfall(Exception):
    """Stok FG fisik tidak cukup untuk dikeluarkan (dispatch ke buyer)."""

    def __init__(self, sku: str, need: int, have: float):
        self.sku, self.need, self.have = sku, need, have
        super().__init__(
            f"Stok FG {sku} tidak cukup: butuh {need} pcs, tersedia {have:g} pcs. "
            "Selesaikan QC penerimaan CMT dulu atau perbaiki stok lewat Opname.")


async def resolve_fg_material(db, *, sku: str = "", material_id: str = "") -> dict | None:
    """Master FG untuk sebuah SKU (dipakai mutasi stok keluar/masuk)."""
    if material_id:
        m = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
        if m:
            return m
    sku = (sku or "").strip()
    if not sku:
        return None
    import re as _re
    rx = {"$regex": f"^{_re.escape(sku)}$", "$options": "i"}
    return (await db.rahaza_materials.find_one({"type": "fg", "code": rx}, {"_id": 0})
            or await db.rahaza_materials.find_one({"code": rx}, {"_id": 0}))


async def issue_fg(db, *, material_id: str, qty: int, ref: dict,
                  actor: dict | None = None, sku: str = "") -> dict:
    """Kurangi stok FG lewat SSOT stok. Prioritas lokasi FG kanonik, lalu baris
    stok lain (kecuali karantina). Tidak pernah membuat stok minus."""
    from core import stock_service
    from core import quarantine as qmod
    qty = _i(qty)
    if qty <= 0:
        return {"issued": [], "qty": 0}
    try:
        qloc = await qmod.get_quarantine_location_id(db)
    except Exception:  # noqa: BLE001
        # F13 — DULU `qloc = None` TANPA SUARA, dan itu bukan kegagalan kosmetik.
        # `qloc` dipakai untuk MENGECUALIKAN baris karantina dari sumber
        # pengurangan stok FG di bawah. Kalau ia None, barang yang sedang
        # dikarantina (reject/menunggu keputusan) ikut dipakai memenuhi
        # pengeluaran — stok karantina bocor jadi barang jual, dan tidak ada
        # satu baris log pun yang menjelaskan kenapa. Perilakunya tetap
        # non-blocking (pengeluaran jalan), TAPI sekarang bersuara keras.
        logger.exception(
            "[qty_ledger] lokasi KARANTINA tidak bisa dibaca — pengurangan stok FG "
            "material=%s qty=%s lanjut TANPA pengecualian karantina; periksa master "
            "lokasi (baris karantina berisiko ikut terpakai)", material_id, qty)
        qloc = None
    fg_loc = await resolve_fg_location_id(db)
    rows = await stock_service.list_rows(material_id, db=db)
    def _q(r):
        try:
            return float(r.get("qty") or r.get("quantity") or 0)
        except (TypeError, ValueError):
            return 0.0
    usable = [r for r in rows if r.get("location_id") != qloc and _q(r) > 0]
    usable.sort(key=lambda r: (0 if r.get("location_id") == fg_loc else 1, -_q(r)))
    have = sum(_q(r) for r in usable)
    if have + 0.0001 < qty:
        raise FGStockShortfall(sku or material_id, qty, have)
    left, issued = qty, []
    for r in usable:
        if left <= 0:
            break
        take = min(left, int(_q(r)))
        if take <= 0:
            continue
        await stock_service.issue(material_id, r["location_id"], take,
                                  ref=ref, actor=actor, db=db)
        issued.append({"location_id": r["location_id"], "qty": take})
        left -= take
    out = {"issued": issued, "qty": qty - left}
    # ── SESI #34 (lanjutan) — BIAYA IKUT KELUAR BERSAMA BARANGNYA ─────────────
    # Lapisan HPP batch (FIFO) dibentuk saat barang jadi MASUK gudang
    # (`post_fg_accepted`). Kalau keluarnya tidak memakan lapisan, `qty_remaining`
    # tidak pernah berkurang ⇒ `hpp_fifo_avg` (angka margin di Katalog Marketing)
    # membeku pada batch-batch lama yang barangnya SUDAH TERJUAL, dan HPP tidak
    # akan pernah mengikuti kenaikan harga kain. Di sini lapisan tertua dimakan
    # sebanyak barang yang keluar, dan HPP hasilnya ditulis ulang ke master.
    #
    # Barang tetap boleh keluar walau biayanya gagal dihitung (stok fisik adalah
    # kebenaran gudang), tetapi kekurangannya DILAPORKAN: `uncosted_qty` > 0
    # berarti ada barang keluar tanpa lapisan biaya — itu tanda batch masuknya
    # belum pernah punya HPP, bukan tanda semuanya beres.
    try:
        from core import fg_cost_layers as fcl
        cogs = await fcl.consume_fifo(db, material_id=material_id, qty=out["qty"],
                                      ref=ref, actor=actor)
        out["cogs"] = cogs.get("cogs", 0.0)
        out["cogs_layers"] = cogs.get("layers_used") or []
        out["uncosted_qty"] = cogs.get("uncosted_qty", 0)
        if out["uncosted_qty"]:
            logger.warning(
                "[qty_ledger] %s pcs FG keluar TANPA lapisan biaya (material=%s sku=%s ref=%s) "
                "— HPP batch untuk qty ini tidak diketahui; periksa apakah batch masuknya "
                "punya biaya jahit & BOM", out["uncosted_qty"], material_id, sku, ref)
    except Exception:  # noqa: BLE001
        logger.exception("[qty_ledger] konsumsi lapisan HPP batch gagal "
                         "(material=%s qty=%s)", material_id, out["qty"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# REKALKULASI BUKU KUANTITAS DARI DOKUMEN (mesin fitur KOREKSI)
# ─────────────────────────────────────────────────────────────────────────────
# Handoff §7: "pakai scripts/recompute_qty_ledger.py sebagai fungsi, jangan tulis
# rumus baru". Versi async ini adalah SATU-SATUNYA rumus yang dipakai fitur
# koreksi (deklarasi & hasil QC) supaya tidak ada rumus kedua yang menyimpang.
TERMINAL_PERMAK = ("selesai_berhasil", "gagal_buang")


async def recompute_group_target(db, po_item_id: str) -> dict:
    """Target buku kuantitas untuk satu `po_item` dihitung dari DOKUMEN SUMBER."""
    from core.cmt_receipt_status import is_done as _done
    lines = await db.cmt_receipt_lines.find({"po_item_id": po_item_id}, {"_id": 0}).to_list(None)
    rec_ids = list({ln.get("receipt_id") for ln in lines if ln.get("receipt_id")})
    receipts = await db.cmt_receipts.find(
        {"id": {"$in": rec_ids}}, {"_id": 0, "id": 1, "status": 1}).to_list(None) if rec_ids else []
    done_ids = {r["id"] for r in receipts if _done(r.get("status"))}
    rows = [ln for ln in lines if ln.get("receipt_id") in done_ids]

    accepted_base = sum(_i(ln.get("qty_actual")) for ln in rows)
    reject = sum(_i(ln.get("reject_qty")) for ln in rows)
    arrived = accepted_base + reject
    claimed = sum(_i(ln.get("qty_claimed_by_cmt")) or _i(ln.get("qty_shipped_by_cmt"))
                  or (_i(ln.get("qty_actual")) + _i(ln.get("reject_qty"))) for ln in rows)

    shorts = await db.cmt_short_shipments.find({"po_item_id": po_item_id}, {"_id": 0}).to_list(None)
    short_open = sum(max(0, _i(s.get("qty_short")) - _i(s.get("qty_resolved")))
                     for s in shorts if s.get("status") == "open")
    short_resolved = sum(_i(s.get("qty_resolved")) for s in shorts if s.get("status") != "cancelled")

    permaks = await db.dewi_cmt_permak.find({"po_item_id": po_item_id}, {"_id": 0}).to_list(None)
    repaired = scrap = closed = 0
    for p in permaks:
        if str(p.get("status") or "") not in TERMINAL_PERMAK:
            continue
        qf, qs = _i(p.get("qty_fixed")), _i(p.get("qty_scrap"))
        closed += qf + qs
        scrap += qs
        if p.get("permak_type") != "retur_ke_cmt":
            repaired += qf
    return {
        "qty_declared": arrived,
        "qty_accepted": accepted_base + repaired,
        "qty_reject": reject,
        "qty_rework_open": max(0, reject - closed),
        "qty_repaired": repaired,
        "qty_scrap": scrap,
        "qty_claimed_by_vendor": claimed,
        "qty_short_open": short_open,
        "qty_short_resolved": short_resolved,
    }


async def resync_from_documents(db, *, po_item_id: str, prefer_job_item_id: str = "") -> dict:
    """Tulis ulang buku kuantitas satu `po_item` agar SAMA dengan dokumen sumber.

    Bila `po_item` punya BEBERAPA job item (mis. job anak hasil rework), selisih
    total ditambahkan ke satu job item saja (`prefer_job_item_id` bila diberikan)
    supaya TOTAL per po_item benar tanpa menghapus jejak rework.
    """
    if not po_item_id:
        return {"ok": False, "reason": "po_item_id kosong"}
    target = await recompute_group_target(db, po_item_id)
    jis = await db.production_job_items.find({"po_item_id": po_item_id}, {"_id": 0}).to_list(None)
    if not jis:
        return {"ok": False, "reason": "job item tidak ditemukan", "target": target}
    cur_total = {f: sum(_i(ji.get(f)) for ji in jis) for f in target}
    if len(jis) == 1:
        await db.production_job_items.update_one(
            {"id": jis[0]["id"]}, {"$set": {**target, "updated_at": _now()}})
        return {"ok": True, "mode": "set", "job_item_id": jis[0]["id"],
                "before": cur_total, "after": target}
    pick = next((ji for ji in jis if ji["id"] == prefer_job_item_id), None) or jis[-1]
    new_vals = {}
    for f, tgt in target.items():
        delta = tgt - cur_total[f]
        new_vals[f] = max(0, _i(pick.get(f)) + delta)
    await db.production_job_items.update_one(
        {"id": pick["id"]}, {"$set": {**new_vals, "updated_at": _now()}})
    return {"ok": True, "mode": "delta", "job_item_id": pick["id"],
            "before": cur_total, "after": target}
