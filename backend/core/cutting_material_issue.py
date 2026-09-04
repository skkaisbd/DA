"""core/cutting_material_issue.py — FASE H-6b: CUTTING MENERBITKAN DOKUMEN
"PENGELUARAN MATERIAL" (`ref_type='cutting_issue'`).

MENGAPA MODUL INI ADA (diukur, bukan ditebak — 2026-08-17, sesi #17)
--------------------------------------------------------------------
Sisa terakhir Fase H. Yang TERUKUR sebelum modul ini dibuat:
  · `POST /api/cutting/orders/{id}/progress` SUDAH benar memotong stok kain
    (`core.stock_service.issue` ⇒ `rahaza_material_stock` + `rahaza_stock_ledger`),
    menambah stok potongan, dan mengurangi sisa gulungan
    (`core.fabric_roll_engine.consume_rolls` ⇒ `wh_fabric_rolls` +
    `wh_fabric_roll_movements`).
  · TETAPI ia TIDAK PERNAH menulis satu dokumen pun ke `rahaza_material_issues`
    dan TIDAK PERNAH menulis satu baris pun ke `rahaza_material_movements`.
    Akibatnya kain yang keluar gudang lewat Cutting **tidak muncul di layar
    "Pengeluaran Material"** dan **tidak muncul di kartu stok** — padahal itulah
    satu-satunya daftar tempat orang gudang menjawab "material apa saja yang
    keluar hari ini?". Dua pintu keluar lain (approve MI manual/job internal dan
    "Kirim Material CMT" lewat `core.material_issue_engine`) sudah punya dokumen;
    Cutting adalah SATU-SATUNYA arus keluar yang tak berdokumen.

KEPUTUSAN DESAIN
----------------
1. **STOK TIDAK DIPOTONG DI SINI.** Ini titik paling mudah salah: kalau modul ini
   memanggil `material_issue_engine.issue_material_issue()` (jalur approve MI),
   kain akan berkurang DUA KALI untuk satu kali potong. Jadi modul ini hanya
   MENERBITKAN DOKUMEN atas mutasi yang SUDAH terjadi di `routes/cutting.py`.
   Dokumen menyimpan `stock_moved_by='cutting'` supaya alasan itu terbaca dari
   datanya, bukan dari ingatan agent berikutnya.
2. **TIDAK ADA JURNAL.** `post_inventory_issue` menjurnal *Dr WIP / Cr Persediaan
   Bahan*. Cutting bukan pemakaian: nilai kain BERPINDAH menjadi nilai potongan
   (`unit_cost` master potongan diisi saat order di-`complete`), dan potongan itu
   masih tercatat sebagai persediaan di `rahaza_material_stock`. Menjurnalnya =
   nilai persediaan di buku besar TURUN sementara di sistem stok TETAP ADA ⇒ buku
   besar dan stok bercabang. Karena itu dokumen ditandai `gl_posted=False` +
   `gl_skip_reason` (dibaca layar), dan `POST /material-issues/{id}/post-to-gl`
   MENOLAK dokumen `cutting_issue` (kalau tidak, satu klik admin cukup untuk
   melahirkan beban hantu).
3. **SATU DOKUMEN PER LAPORAN PROGRES**, bukan per order. Satu laporan progres =
   satu kali kain benar-benar keluar dari satu lokasi. Idempoten dijaga DUA
   lapis: pencarian `cutting_progress_id` + indeks unik sparse pada koleksi MI
   (`ensure_cutting_indexes`), supaya klik ganda / backfill berulang tidak
   melahirkan dokumen kembar.
4. **STATUS LANGSUNG `issued`.** Tidak ada approval: barangnya sudah keluar.
   Menyetel `draft`/`pending_approval` akan MENGUNDANG orang menekan Approve →
   dan approve memotong stok lagi (lihat butir 1).
5. **NOMOR DARI SATU DERET** (`_gen_mi_number` ⇒ `MI-YYYYMMDD-NNN`) supaya daftar
   "Pengeluaran Material" tetap satu deret kronologis lintas sumber.
6. **KEGAGALAN TERBITNYA DOKUMEN TIDAK MEMBATALKAN POTONG KAIN** (stok sudah
   bergerak; melempar galat hanya akan membuat operator melapor dua kali). Tapi
   ia juga TIDAK BOLEH HILANG DIAM-DIAM: progres tanpa dokumen tampil di
   `GET /api/cutting/issue-docs/missing` dan bisa diterbitkan retroaktif lewat
   `POST /api/cutting/issue-docs/backfill` (idempoten) — pola yang sama dengan
   "Penerimaan tanpa roll" di Fase H-5.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SOURCE = "cutting"
REF_TYPE = "cutting_issue"
PROGRESS = "cutting_progress"
ORDERS = "cutting_orders"
MI = "rahaza_material_issues"

GL_SKIP_REASON = (
    "Cutting BUKAN pemakaian material: nilai kain berpindah menjadi nilai potongan "
    "(HPP potongan dihitung saat order Cutting diselesaikan) dan potongan masih "
    "tercatat sebagai persediaan. Menjurnal Dr WIP / Cr Persediaan di sini akan "
    "menurunkan nilai persediaan di buku besar sementara barangnya masih ada di "
    "sistem stok. Koreksi nilai dilakukan lewat Penyesuaian Stok, bukan di sini."
)

STOCK_NOTE = (
    "Stok kain & sisa gulungan SUDAH dipotong oleh Portal Cutting saat progres "
    "dilaporkan. Dokumen ini adalah bukti/jejak arus keluarnya — menyetujui atau "
    "meng-issue ulang akan memotong stok dua kali, jadi dokumen ini lahir "
    "langsung berstatus 'issued'."
)


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


async def ensure_indexes(db) -> None:
    """Indeks unik sparse: satu laporan progres cutting = MAKSIMAL satu dokumen MI.

    Dipanggil dari `routes/cutting.py::ensure_cutting_indexes()` (startup).
    Dibuat `sparse` karena dokumen MI dari sumber lain (manual/job/CMT) memang
    tidak punya field ini.
    """
    try:
        await db[MI].create_index(
            "cutting_progress_id", unique=True, sparse=True,
            name="uniq_cutting_progress_mi")
    except Exception as e:  # noqa: BLE001 — indeks lama bernama beda / data kembar
        logger.warning("H-6b: indeks unik cutting_progress_id tidak terpasang: %s", e)
    try:
        await db[MI].create_index("source", name="mi_source")
    except Exception as e:  # noqa: BLE001
        logger.warning("H-6b: indeks source tidak terpasang: %s", e)


def _roll_summary(progress: dict) -> tuple[list, list]:
    cons = list(progress.get("roll_consumption") or [])
    numbers = [str(p.get("roll_no") or "") for p in cons if p.get("roll_no")]
    if not numbers:
        numbers = [str(x) for x in (progress.get("roll_numbers") or []) if x]
    return cons, numbers


async def doc_for_progress(db, order: dict, progress: dict, user: dict,
                           *, backfilled: bool = False) -> dict:
    """Terbitkan (atau pakai-ulang) dokumen Material Issue untuk SATU laporan progres.

    TIDAK menyentuh stok — lihat keputusan desain 1 di docstring modul.
    Mengembalikan dokumen MI (sudah ter-`_enrich_mi`).
    """
    from routes.rahaza_inventory_shared import (
        _enrich_mi,
        _gen_mi_number,
        _log_movement,
        _now,
        _uid,
    )

    pid = progress.get("id")
    if not pid:
        raise ValueError("progress tanpa id — dokumen MI tidak bisa ditautkan")

    existing = await db[MI].find_one({"cutting_progress_id": pid}, {"_id": 0})
    if existing:
        await _enrich_mi(db, existing)
        existing["_already"] = True
        return existing

    qty = round(_f(progress.get("input_consumed")), 4)
    if qty <= 0:
        raise ValueError("progres tanpa kain terpakai — tidak ada arus keluar untuk didokumentasikan")

    material_id = order.get("input_material_id")
    if not material_id:
        raise ValueError("order cutting tanpa material kain — dokumen MI tidak bisa dibuat")

    # Lokasi: yang dicatat di progres (sejak H-6b) ⇒ tepat. Untuk progres LAMA
    # (backfill) dipakai lokasi order sekarang, dan asalnya ditandai supaya tidak
    # ada yang menganggap itu bukti fisik.
    loc_id = progress.get("location_id") or order.get("location_id")
    loc_source = "progress" if progress.get("location_id") else "order"

    cons, roll_numbers = _roll_summary(progress)
    mat = await db.rahaza_materials.find_one(
        {"id": material_id}, {"_id": 0, "code": 1, "name": 1, "unit": 1}) or {}

    item_notes = f"Cutting {order.get('number', '')}".strip()
    if roll_numbers:
        item_notes += " · gulungan " + ", ".join(roll_numbers)

    mi_number = await _gen_mi_number(db)
    doc = {
        "id": _uid(),
        "mi_number": mi_number,
        # ── sumber & jenis arus keluar ──────────────────────────────────────
        "source": SOURCE,
        "ref_type": REF_TYPE,
        "work_order_id": None,
        "wo_number_snapshot": "",
        "job_id": None,
        "qty_wo_pcs": 0,
        # ── ketelusuran ke Portal Cutting ───────────────────────────────────
        "cutting_order_id": order.get("id"),
        "cutting_order_number": order.get("number", ""),
        "cutting_progress_id": pid,
        "cutting_style_name": order.get("style_name") or order.get("style_sku") or "",
        "cutting_output_material_code": order.get("output_material_code") or "",
        "cutting_output_qty": round(_f(progress.get("output_qty")), 4),
        "cutting_waste_qty": round(_f(progress.get("waste_qty")), 4),
        "roll_numbers": roll_numbers,
        "roll_consumption": cons,
        "location_source": loc_source,
        # ── baris material ──────────────────────────────────────────────────
        "items": [{
            "id": _uid(),
            "material_id": material_id,
            "qty_required": qty,
            "qty_issued": qty,
            "location_id": loc_id,
            "notes": item_notes,
        }],
        # ── status & alasan (dibaca layar) ──────────────────────────────────
        "status": "issued",
        "issued_at": progress.get("created_at") or _now(),
        "issued_by": progress.get("created_by") or user.get("id"),
        "issued_by_name": progress.get("created_by_name") or user.get("name", ""),
        "stock_moved_by": SOURCE,
        "stock_note": STOCK_NOTE,
        "gl_posted": False,
        "gl_skip_reason": GL_SKIP_REASON,
        "backfilled": bool(backfilled),
        "notes": (
            f"Otomatis dari Portal Cutting {order.get('number', '')} — "
            f"{qty:g} {mat.get('unit') or ''} {mat.get('code') or ''} dipotong menjadi "
            f"{_f(progress.get('output_qty')):g} pcs {order.get('output_material_code') or 'potongan'}"
            + (f" (gulungan {', '.join(roll_numbers)})" if roll_numbers else "")
            + (" · diterbitkan retroaktif (FASE H-6b)" if backfilled else " (FASE H-6b)")
        ).strip(),
        "created_by": user.get("id"),
        "created_by_name": user.get("name", ""),
        "created_at": progress.get("created_at") or _now(),
        "updated_at": _now(),
    }

    try:
        await db[MI].insert_one(dict(doc))
    except Exception:
        # Tabrakan indeks unik `cutting_progress_id` = dokumennya SUDAH ada (klik
        # ganda / backfill bersamaan). Itu bukan kegagalan: pakai yang sudah ada.
        again = await db[MI].find_one({"cutting_progress_id": pid}, {"_id": 0})
        if again:
            await _enrich_mi(db, again)
            again["_already"] = True
            return again
        raise

    # Kartu stok (`rahaza_material_movements`) — sebelum H-6b arus keluar Cutting
    # tidak pernah muncul di kartu stok sama sekali.
    if loc_id:
        await _log_movement(
            db, {"id": doc["created_by"], "name": doc["created_by_name"]},
            type="issue", material_id=material_id, qty=qty,
            from_location_id=loc_id, to_location_id=None,
            ref_type=REF_TYPE, ref_id=doc["id"],
            notes=f"MI {mi_number} · Cutting {order.get('number', '')}".strip(" ·"),
        )

    await db[PROGRESS].update_one({"id": pid}, {"$set": {
        "material_issue_id": doc["id"],
        "material_issue_number": mi_number,
    }})
    await db[ORDERS].update_one({"id": order.get("id")}, {"$addToSet": {
        "material_issue_numbers": mi_number,
    }})

    out = await db[MI].find_one({"id": doc["id"]}, {"_id": 0})
    await _enrich_mi(db, out)
    out["_already"] = False
    return out


async def progress_without_doc(db, *, limit: int = 200,
                               order_id: str | None = None) -> dict:
    """Laporan progres cutting yang BELUM punya dokumen Pengeluaran Material.

    Sekalian MEMPERBAIKI tautan yang hilang: kalau dokumennya ternyata ada tetapi
    `material_issue_id` di progres kosong (mis. backend mati tepat di antara dua
    tulisan), tautannya dipulihkan dan barisnya TIDAK dilaporkan sebagai kurang —
    supaya angka "kurang" tidak pernah menuduh salah.
    """
    q: dict = {"$or": [{"material_issue_id": {"$exists": False}},
                       {"material_issue_id": None}, {"material_issue_id": ""}]}
    if order_id:
        q["cutting_order_id"] = order_id
    rows = await db[PROGRESS].find(q, {"_id": 0}).sort("created_at", -1).limit(
        max(1, min(int(limit or 200), 1000))).to_list(1000)
    if not rows:
        return {"items": [], "count": 0, "repaired": 0}

    ids = [r["id"] for r in rows if r.get("id")]
    have = {}
    async for m in db[MI].find(
            {"cutting_progress_id": {"$in": ids}},
            {"_id": 0, "id": 1, "mi_number": 1, "cutting_progress_id": 1}):
        have[m["cutting_progress_id"]] = m

    repaired = 0
    missing = []
    order_ids = list({r.get("cutting_order_id") for r in rows if r.get("cutting_order_id")})
    orders = {}
    async for o in db[ORDERS].find(
            {"id": {"$in": order_ids}},
            {"_id": 0, "id": 1, "number": 1, "style_name": 1, "input_material_code": 1,
             "input_material_name": 1, "input_unit": 1, "location_name": 1, "status": 1}):
        orders[o["id"]] = o
    for r in rows:
        found = have.get(r.get("id"))
        if found:
            await db[PROGRESS].update_one({"id": r["id"]}, {"$set": {
                "material_issue_id": found["id"],
                "material_issue_number": found.get("mi_number", ""),
            }})
            repaired += 1
            continue
        if _f(r.get("input_consumed")) <= 0:
            continue
        o = orders.get(r.get("cutting_order_id")) or {}
        missing.append({
            "progress_id": r.get("id"),
            "cutting_order_id": r.get("cutting_order_id"),
            "cutting_number": r.get("cutting_number") or o.get("number", ""),
            "order_status": o.get("status", ""),
            "style_name": o.get("style_name", ""),
            "material_code": o.get("input_material_code", ""),
            "material_name": o.get("input_material_name", ""),
            "unit": o.get("input_unit", ""),
            "location_name": o.get("location_name", ""),
            "input_consumed": round(_f(r.get("input_consumed")), 4),
            "output_qty": round(_f(r.get("output_qty")), 4),
            "roll_numbers": [x for x in (r.get("roll_numbers") or []) if x],
            "created_at": r.get("created_at"),
            "created_by_name": r.get("created_by_name", ""),
        })
    return {"items": missing, "count": len(missing), "repaired": repaired}


async def backfill(db, user: dict, *, limit: int = 500,
                   order_id: str | None = None) -> dict:
    """Terbitkan dokumen MI untuk progres cutting lama (idempoten).

    Tidak menyentuh stok: mutasinya sudah terjadi saat progres dilaporkan.
    """
    pending = await progress_without_doc(db, limit=limit, order_id=order_id)
    created, already, failed = [], 0, []
    orders_cache: dict = {}
    for row in pending["items"]:
        oid = row.get("cutting_order_id")
        o = orders_cache.get(oid)
        if o is None:
            o = await db[ORDERS].find_one({"id": oid}, {"_id": 0})
            orders_cache[oid] = o or {}
            o = orders_cache[oid]
        if not o:
            failed.append({"progress_id": row["progress_id"],
                           "error": "order cutting tidak ditemukan"})
            continue
        prog = await db[PROGRESS].find_one({"id": row["progress_id"]}, {"_id": 0})
        if not prog:
            failed.append({"progress_id": row["progress_id"],
                           "error": "progres tidak ditemukan"})
            continue
        try:
            mi = await doc_for_progress(db, o, prog, user, backfilled=True)
        except Exception as e:
            logger.exception("H-6b backfill gagal untuk progres %s", row["progress_id"])
            failed.append({"progress_id": row["progress_id"], "error": str(e)})
            continue
        if mi.get("_already"):
            already += 1
        else:
            created.append({"progress_id": row["progress_id"],
                            "mi_number": mi.get("mi_number"),
                            "cutting_number": row.get("cutting_number")})
    return {
        "ok": True,
        "scanned": pending["count"],
        "repaired_links": pending["repaired"],
        "created": len(created),
        "already": already,
        "failed": failed,
        "documents": created,
    }
