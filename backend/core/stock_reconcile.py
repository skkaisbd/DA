"""core.stock_reconcile — FASE 6.6-A: rekonsiliasi baris stok skema lama A/B/C.

MASALAH (grounded, lihat `core/stock_schema.py` + `memory/INVENTORY_QTY_LOGIC_AUDIT.md`)
---------------------------------------------------------------------------------------
Koleksi `rahaza_material_stock` historis ditulis 3 kelompok writer dengan bentuk berbeda:

  * **Skema A** (kanonik)          `{material_id, location_id, qty}`
  * **Skema B** (Aksesoris lama)   `{material_id, location:{id,code}, total_qty}` → lokasi NESTED
  * **Skema C** (FG/CMT lama)      `{material_id, quantity, available_quantity, reserved_quantity}`
                                    → TANPA `location_id`

Sejak FASE 2 semua writer lewat `core/stock_service` (satu pintu, selalu kanonik), TAPI
**baris warisan** di database yang sudah berjalan bisa masih berbentuk B/C. Dampaknya:

  - Reader per-lokasi (Put-Away, Opname per-bin, dropdown lokasi, peta gudang) TIDAK
    melihat baris B/C ⇒ stok "hilang" dari layar walau total agregat benar.
  - Bisa muncul **baris kembar** untuk material+lokasi yang sama (satu A, satu B) ⇒
    penyesuaian/opname mengoreksi baris yang salah.
  - `available_quantity` basi (≠ qty − reserved) ⇒ reservasi/fulfillment over-allocate.

MODUL INI
---------
Alat **diagnosa + rekonsiliasi** yang: idempoten, punya mode dry-run, TIDAK PERNAH
mengubah TOTAL on-hand per material (hanya membenahi BENTUK baris & menggabungkan
kembar), dan menulis jurnal `wh_stock_schema_reconcile_log` (before/after per baris)
sehingga bisa di-rollback presisi.

Penyakit yang dideteksi (8):
  1. `nested_location`   — lokasi masih nested (`location.id`) ⇒ set `location_id` datar.
  2. `missing_location`  — tak punya lokasi ⇒ resolve zona kanonik sesuai kategori material.
  3. `alias_drift`       — `total_qty`/`quantity` ≠ `qty` ⇒ mirror ulang.
  4. `available_drift`   — `available_quantity` ≠ qty − reserved ⇒ hitung ulang.
  5. `duplicate_rows`    — >1 baris utk (material_id, location_id) ⇒ gabung ke baris tertua.
  6. `negative_qty`      — qty < 0 ⇒ **LAPOR SAJA** (butuh keputusan manusia/opname).
  7. `orphan_material`   — `material_id` tak ada di master ⇒ **LAPOR SAJA**.
  8. `unmapped_location` — **FASE 12** baris stok berada di lokasi yang BUKAN zona
     penyimpanan (mis. gudang demo warisan `int-demo-loc-1`, atau id lokasi yang
     sudah dihapus) ⇒ pindahkan ke zona kanonik sesuai kategori material lalu gabung
     bila baris tujuan sudah ada. Lantai produksi & karantina QC DIKECUALIKAN
     (`core.location_resolver.KIND_EXEMPT`) — stok di sana memang seharusnya di sana.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core import location_resolver
from core.material_fields import storage_role_of
from core.stock_schema import read_qty, read_reserved
import logging

logger = logging.getLogger(__name__)

COLL = "rahaza_material_stock"
LOG_COLL = "wh_stock_schema_reconcile_log"

TOL = 1e-6

ISSUE_KEYS = (
    "nested_location",
    "missing_location",
    "unmapped_location",
    "alias_drift",
    "available_drift",
    "duplicate_rows",
    "negative_qty",
    "orphan_material",
)

# Penyakit yang HANYA dilaporkan (tidak diperbaiki otomatis)
REPORT_ONLY = ("negative_qty", "orphan_material")

ISSUE_LABELS = {
    "nested_location": "Lokasi masih tersimpan bersarang (skema B lama)",
    "missing_location": "Baris stok tanpa lokasi (skema C lama)",
    "unmapped_location": "Stok berada di lokasi yang bukan zona penyimpanan",
    "alias_drift": "Alias jumlah (total_qty/quantity) tidak sama dengan qty",
    "available_drift": "Jumlah tersedia tidak sama dengan qty − reserved",
    "duplicate_rows": "Baris kembar untuk material + lokasi yang sama",
    "negative_qty": "Jumlah stok negatif (perlu opname / keputusan manual)",
    "orphan_material": "Material tidak ada di master (baris yatim)",
}

ISSUE_HINTS = {
    "nested_location": "Rekonsiliasi menyalin location.id → location_id lalu melepas field bersarang.",
    "missing_location": "Rekonsiliasi menetapkan zona storage kanonik sesuai kategori material.",
    "unmapped_location": (
        "Rekonsiliasi memindahkan baris ke zona penyimpanan kanonik sesuai kategori material "
        "(Bahan → Area Kain, Aksesoris → Area Aksesoris, Produk Jadi → Area Produk Jadi) dan "
        "menggabungkannya bila baris tujuan sudah ada. Total stok tidak berubah. "
        "Lantai produksi & karantina QC sengaja TIDAK ikut dipindahkan."
    ),
    "alias_drift": "Rekonsiliasi menyalin nilai qty ke semua alias.",
    "available_drift": "Rekonsiliasi menghitung ulang available_quantity = qty − reserved.",
    "duplicate_rows": "Rekonsiliasi menjumlahkan baris kembar ke baris tertua (total on-hand tidak berubah).",
    "negative_qty": "TIDAK diperbaiki otomatis — lakukan Opname Stok atau Penyesuaian resmi.",
    "orphan_material": "TIDAK diperbaiki otomatis — pulihkan master material atau hapus baris lewat Penyesuaian.",
}


def _now():
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _nested_location_id(row: dict) -> str:
    loc = row.get("location")
    if isinstance(loc, dict):
        return str(loc.get("id") or loc.get("location_id") or "").strip()
    return ""


def classify(row: dict) -> str:
    """Bentuk baris: 'B' (lokasi nested), 'C' (tanpa lokasi), 'A' (kanonik)."""
    if isinstance(row.get("location"), dict):
        return "B"
    if not str(row.get("location_id") or "").strip():
        return "C"
    return "A"


def _row_issues(row: dict, *, material_exists: bool, dup: bool,
                location_kind: str | None = None) -> list[str]:
    issues: list[str] = []
    loc_id = str(row.get("location_id") or "").strip()
    nested = _nested_location_id(row)
    qty = read_qty(row)
    # Baris yang butuh KEPUTUSAN MANUSIA (stok negatif / material yatim) tidak boleh
    # ikut dipindahkan otomatis — memindah+menggabungkan baris negatif akan diam-diam
    # MENGURANGI stok di zona tujuan, dan baris yatim tidak punya kategori material
    # sehingga zona tujuannya tidak bisa ditentukan. Karena itu penyakit
    # `unmapped_location` sengaja TIDAK dilaporkan untuk baris seperti ini (kalau
    # dilaporkan, `fixable_issues` tidak akan pernah nol ⇒ rekonsiliasi tampak gagal).
    report_only_row = (qty < -TOL) or (not material_exists)
    if isinstance(row.get("location"), dict):
        issues.append("nested_location")
    if not loc_id and not nested:
        issues.append("missing_location")
    elif location_kind == location_resolver.KIND_UNMAPPED and not report_only_row:
        # FASE 12 — punya lokasi, tapi lokasinya bukan zona penyimpanan.
        issues.append("unmapped_location")
    for alias in ("total_qty", "quantity"):
        if alias in row and abs(_f(row.get(alias)) - qty) > TOL:
            issues.append("alias_drift")
            break
    if "qty" not in row:
        # baris tanpa kunci kanonik `qty` sama sekali → alias wajib di-mirror
        if "alias_drift" not in issues:
            issues.append("alias_drift")
    if "available_quantity" in row:
        expected = qty - read_reserved(row)
        if abs(_f(row.get("available_quantity")) - expected) > TOL:
            issues.append("available_drift")
    if qty < -TOL:
        issues.append("negative_qty")
    if not material_exists:
        issues.append("orphan_material")
    if dup:
        issues.append("duplicate_rows")
    return issues


def _sort_key(row: dict):
    """Baris tertua menang saat merge (created_at, lalu id agar deterministik)."""
    ts = row.get("created_at") or row.get("updated_at")
    return (str(ts or "9999"), str(row.get("id") or ""))


async def _resolve_location_for(db, material: dict | None, cache: dict,
                                index: dict | None = None) -> tuple[str, str]:
    """Zona storage kanonik untuk sebuah material → (location_id, sumber).

    Urutan: zona kanonik `wh_zones` sesuai peran (bahan/aksesoris/fg) → lokasi legacy
    `rahaza_locations` storage sesuai peran → '' (tak terselesaikan).

    FASE 12: bila `index` (hasil `location_resolver.storage_location_index`) diberikan,
    pakai itu supaya SATU sumber kebenaran dan tanpa query berulang.
    """
    role = storage_role_of((material or {}).get("type"))
    if index is not None:
        target = (index.get("roles") or {}).get(role) or ""
        source = (index.get("role_source") or {}).get(role) or "unresolved"
        return (target, source if target else "unresolved")
    if role in cache:
        return cache[role]
    resolved = ("", "unresolved")
    # 2026-08-07 — DULU `except Exception: pass`. Rekonsiliasi stok yang salah
    # menebak lokasi tujuan akan MEMINDAHKAN baris stok ke lokasi yang salah.
    # Fallback legacy dipertahankan, tetapi kegagalannya wajib tercatat.
    try:
        zid = await location_resolver.canonical_zone_id_for_role(db, role)
        if zid:
            resolved = (zid, "wh_zones")
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[rekonsiliasi-stok] gagal resolusi zona kanonik peran '%s' — memakai lokasi "
            "legacy. Baris stok bisa dipindahkan ke lokasi yang salah: %s", role, e)
    if not resolved[0]:
        legacy_codes = {
            "bahan": "ZNA-KAIN",
            "aksesoris": "ZNA-AKSESORIS",
            "fg": "ZNA-FG",
        }
        code = legacy_codes.get(role)
        if code:
            loc = await db.rahaza_locations.find_one({"code": code}, {"_id": 0, "id": 1})
            if loc:
                resolved = (loc["id"], "rahaza_locations")
    cache[role] = resolved
    return resolved


# ─────────────────────────────────────────────────────────────────────────────
# SCAN (read-only)
# ─────────────────────────────────────────────────────────────────────────────
async def scan(db, *, detail_limit: int = 100) -> dict:
    """Diagnosa kesehatan skema — READ ONLY. Aman dipanggil kapan saja."""
    rows = await db[COLL].find({}, {"_id": 0}).to_list(50000)
    mat_ids = {str(r.get("material_id") or "") for r in rows if r.get("material_id")}
    mats: dict[str, dict] = {}
    if mat_ids:
        async for m in db.rahaza_materials.find(
            {"id": {"$in": list(mat_ids)}},
            {"_id": 0, "id": 1, "code": 1, "name": 1, "type": 1, "unit": 1},
        ):
            mats[m["id"]] = m

    # deteksi kembar berdasar (material_id, lokasi efektif)
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        eff_loc = str(r.get("location_id") or "").strip() or _nested_location_id(r)
        groups.setdefault((str(r.get("material_id") or ""), eff_loc), []).append(r)
    dup_ids = {
        str(r.get("id"))
        for key, grp in groups.items()
        if len(grp) > 1 and key[1]  # lokasi kosong ditangani oleh missing_location
        for r in grp
    }

    counts = {k: 0 for k in ISSUE_KEYS}
    by_schema = {"A": 0, "B": 0, "C": 0}
    details: list[dict] = []
    affected_rows = 0
    total_qty = 0.0

    # FASE 12 — indeks "peta gudang": lokasi mana yang storage / dikecualikan / liar.
    loc_index = await location_resolver.storage_location_index(db)
    loc_stats: dict[str, dict] = {}

    for r in rows:
        by_schema[classify(r)] += 1
        total_qty += read_qty(r)
        mat = mats.get(str(r.get("material_id") or ""))
        eff_loc = str(r.get("location_id") or "").strip() or _nested_location_id(r)
        loc_kind = location_resolver.classify_location(loc_index, eff_loc) if eff_loc else None
        suggested, sug_source = await _resolve_location_for(db, mat, {}, loc_index)

        # ringkasan per lokasi (peta gudang)
        if eff_loc:
            st = loc_stats.setdefault(eff_loc, {
                "location_id": eff_loc,
                **location_resolver.describe_location(loc_index, eff_loc),
                "rows": 0, "qty": 0.0,
            })
            st["rows"] += 1
            st["qty"] += read_qty(r)

        issues = _row_issues(r, material_exists=bool(mat),
                             dup=str(r.get("id")) in dup_ids, location_kind=loc_kind)
        if not issues:
            continue
        affected_rows += 1
        for i in issues:
            counts[i] += 1
        if len(details) < detail_limit:
            loc_meta = location_resolver.describe_location(loc_index, eff_loc)
            details.append({
                "row_id": r.get("id"),
                "material_id": r.get("material_id"),
                "material_code": (mat or {}).get("code") or "",
                "material_name": (mat or {}).get("name") or "(master tidak ditemukan)",
                "material_type": (mat or {}).get("type") or "",
                "unit": (mat or {}).get("unit") or "",
                "schema": classify(r),
                "location_id": r.get("location_id") or "",
                "location_code": loc_meta.get("code") or "",
                "location_name": loc_meta.get("name") or "",
                "location_kind": loc_kind or "",
                "nested_location_id": _nested_location_id(r),
                "suggested_location_id": suggested if ("unmapped_location" in issues or "missing_location" in issues) else "",
                "suggested_location_code": (
                    location_resolver.describe_location(loc_index, suggested).get("code")
                    if suggested and ("unmapped_location" in issues or "missing_location" in issues) else ""
                ),
                "suggested_source": sug_source if suggested else "",
                "qty": round(read_qty(r), 4),
                "reserved": round(read_reserved(r), 4),
                "available_quantity": r.get("available_quantity"),
                "issues": issues,
            })

    locations = sorted(
        ({**v, "qty": round(v["qty"], 4)} for v in loc_stats.values()),
        key=lambda d: (0 if d.get("kind") == location_resolver.KIND_UNMAPPED else 1, -d["rows"]),
    )
    role_targets = [
        {
            "role": role,
            "location_id": (loc_index.get("roles") or {}).get(role) or "",
            "source": (loc_index.get("role_source") or {}).get(role) or "",
            **{
                k: v for k, v in location_resolver.describe_location(
                    loc_index, (loc_index.get("roles") or {}).get(role)
                ).items() if k in ("code", "name")
            },
        }
        for role in location_resolver.STORAGE_ROLES
    ]

    fixable = sum(counts[k] for k in ISSUE_KEYS if k not in REPORT_ONLY)
    manual = sum(counts[k] for k in REPORT_ONLY)
    return {
        "total_rows": len(rows),
        "total_qty": round(total_qty, 4),
        "affected_rows": affected_rows,
        "healthy": affected_rows == 0,
        "fixable_issues": fixable,
        "manual_issues": manual,
        "by_schema": by_schema,
        "counts": counts,
        "labels": ISSUE_LABELS,
        "hints": ISSUE_HINTS,
        "report_only": list(REPORT_ONLY),
        "details": details,
        "details_truncated": affected_rows > len(details),
        "locations": locations,
        "role_targets": role_targets,
        "location_kinds": {
            "storage": "Zona penyimpanan resmi",
            "exempt": "Lantai produksi / karantina QC (sengaja dikecualikan)",
            "unmapped": "Bukan zona penyimpanan — perlu dirapikan",
        },
        "scanned_at": _now(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# RECONCILE (dry-run / apply)
# ─────────────────────────────────────────────────────────────────────────────
async def reconcile(db, *, dry_run: bool = True, actor: dict | None = None) -> dict:
    """Normalisasi bentuk baris + gabungkan kembar. TIDAK mengubah total on-hand.

    Urutan kerja (penting):
      1. Tetapkan `location_id` (dari nested, atau resolve zona kanonik).
      2. Gabungkan baris kembar (material_id + location_id sama).
      3. Mirror alias qty + hitung ulang available_quantity.

    Mode `dry_run=True` (default) hanya MENGHITUNG rencana, tanpa menulis apa pun.
    """
    rows = await db[COLL].find({}, {"_id": 0}).to_list(50000)
    mat_ids = {str(r.get("material_id") or "") for r in rows if r.get("material_id")}
    mats: dict[str, dict] = {}
    if mat_ids:
        async for m in db.rahaza_materials.find(
            {"id": {"$in": list(mat_ids)}}, {"_id": 0, "id": 1, "code": 1, "name": 1, "type": 1}
        ):
            mats[m["id"]] = m

    loc_cache: dict = {}
    actions: list[dict] = []
    unresolved: list[dict] = []
    skipped_manual: list[dict] = []
    # FASE 12 — indeks peta gudang (SSOT klasifikasi lokasi).
    loc_index = await location_resolver.storage_location_index(db)
    relocations: list[dict] = []

    # ── langkah 1: bentuk kerja (in-memory) dengan lokasi terselesaikan ────────
    work: list[dict] = []
    for r in rows:
        before = dict(r)
        cur = dict(r)
        fixes: list[str] = []
        loc_id = str(cur.get("location_id") or "").strip()
        nested = _nested_location_id(cur)

        if not loc_id and nested:
            cur["location_id"] = nested
            loc_id = nested
            fixes.append("nested_location")
        if isinstance(cur.get("location"), dict):
            cur.pop("location", None)
            if "nested_location" not in fixes:
                fixes.append("nested_location")
        if not loc_id:
            resolved, source = await _resolve_location_for(
                db, mats.get(str(cur.get("material_id") or "")), loc_cache, loc_index)
            if resolved:
                cur["location_id"] = resolved
                cur["location_resolved_by"] = f"stock_reconcile:{source}"
                loc_id = resolved
                fixes.append("missing_location")
            else:
                unresolved.append({
                    "row_id": cur.get("id"),
                    "material_id": cur.get("material_id"),
                    "reason": "zona storage kanonik untuk kategori material belum ada",
                })
        elif location_resolver.classify_location(loc_index, loc_id) == location_resolver.KIND_UNMAPPED:
            # ── FASE 12: baris berada di lokasi yang BUKAN zona penyimpanan ──────
            # (gudang demo warisan, gedung konsep, atau id lokasi yang sudah dihapus).
            # Pindahkan ke zona kanonik sesuai kategori material. Penggabungan bila
            # baris tujuan sudah ada ditangani langkah 2 — jadi total on-hand tetap.
            #
            # PENGAMAN (wajib): baris yang butuh keputusan manusia TIDAK ikut pindah.
            #   * qty negatif  → memindah+menggabungkan akan diam-diam MENGURANGI stok
            #                    di zona tujuan sehingga selisihnya hilang dari radar;
            #   * material yatim → kategori tidak diketahui ⇒ zona tujuan tak bisa
            #                    ditentukan dengan benar.
            # Keduanya tetap dilaporkan sebagai `negative_qty` / `orphan_material`.
            mat_row = mats.get(str(cur.get("material_id") or ""))
            hold_for_human = (read_qty(cur) < -TOL) or (mat_row is None)
            target, source = ("", "") if hold_for_human else await _resolve_location_for(
                db, mat_row, loc_cache, loc_index)
            if target and target != loc_id:
                cur["location_id"] = target
                cur["relocated_from"] = loc_id
                cur["location_resolved_by"] = f"stock_reconcile:relocate:{source}"
                fixes.append("unmapped_location")
                relocations.append({
                    "row_id": cur.get("id"),
                    "material_id": cur.get("material_id"),
                    "from_location_id": loc_id,
                    "from_location_code": location_resolver.describe_location(loc_index, loc_id).get("code"),
                    "to_location_id": target,
                    "to_location_code": location_resolver.describe_location(loc_index, target).get("code"),
                    "qty": round(read_qty(cur), 4),
                })
                loc_id = target
            elif not target and not hold_for_human:
                unresolved.append({
                    "row_id": cur.get("id"),
                    "material_id": cur.get("material_id"),
                    "reason": "lokasi bukan zona penyimpanan, tapi zona tujuan kanonik belum ada",
                })
        if read_qty(cur) < -TOL:
            skipped_manual.append({"row_id": cur.get("id"), "material_id": cur.get("material_id"),
                                   "issue": "negative_qty"})
        if str(cur.get("material_id") or "") not in mats:
            skipped_manual.append({"row_id": cur.get("id"), "material_id": cur.get("material_id"),
                                   "issue": "orphan_material"})
        work.append({"before": before, "cur": cur, "fixes": fixes, "deleted": False})

    # ── langkah 2: gabung kembar ──────────────────────────────────────────────
    groups: dict[tuple, list[dict]] = {}
    for w in work:
        loc = str(w["cur"].get("location_id") or "").strip()
        if not loc:
            continue  # tak bisa digabung tanpa identitas lokasi
        groups.setdefault((str(w["cur"].get("material_id") or ""), loc), []).append(w)

    merges: list[dict] = []
    for _key, grp in groups.items():
        if len(grp) < 2:
            continue
        grp.sort(key=lambda w: _sort_key(w["cur"]))
        keeper = grp[0]
        for loser in grp[1:]:
            add_qty = read_qty(loser["cur"])
            add_res = read_reserved(loser["cur"])
            keeper_before_merge = dict(keeper["cur"])
            new_qty = read_qty(keeper["cur"]) + add_qty
            new_res = read_reserved(keeper["cur"]) + add_res
            keeper["cur"]["qty"] = new_qty
            keeper["cur"]["reserved_quantity"] = new_res
            if "duplicate_rows" not in keeper["fixes"]:
                keeper["fixes"].append("duplicate_rows")
            loser["deleted"] = True
            merges.append({
                "deleted_row_id": loser["cur"].get("id"),
                "target_row_id": keeper["cur"].get("id"),
                "merged_qty": round(add_qty, 4),
                "merged_reserved": round(add_res, 4),
                "deleted_before": loser["before"],
                "target_before": keeper["before"],
                "_target_snapshot_before_merge": keeper_before_merge,
            })

    # ── langkah 3: mirror alias + available ───────────────────────────────────
    for w in work:
        if w["deleted"]:
            continue
        cur = w["cur"]
        qty = read_qty(cur)
        reserved = read_reserved(cur)
        alias_needed = (
            "qty" not in cur
            or any(a in cur and abs(_f(cur.get(a)) - qty) > TOL for a in ("total_qty", "quantity"))
        )
        cur["qty"] = qty
        cur["total_qty"] = qty
        cur["quantity"] = qty
        if alias_needed and "alias_drift" not in w["fixes"]:
            w["fixes"].append("alias_drift")
        expected_avail = qty - reserved
        if "available_quantity" in cur and abs(_f(cur.get("available_quantity")) - expected_avail) > TOL:
            w["fixes"].append("available_drift")
        cur["available_quantity"] = expected_avail
        cur["reserved_quantity"] = reserved

    # ── susun aksi ────────────────────────────────────────────────────────────
    for w in work:
        if w["deleted"]:
            continue
        if not w["fixes"]:
            continue
        after = dict(w["cur"])
        if not dry_run:
            after["updated_at"] = _now()
            after["schema_reconciled_at"] = _now()
        actions.append({
            "type": "normalize_row",
            "row_id": w["cur"].get("id"),
            "material_id": w["cur"].get("material_id"),
            "fixes": w["fixes"],
            "before": w["before"],
            "after": after,
        })
    for m in merges:
        actions.append({
            "type": "merge_row",
            "row_id": m["deleted_row_id"],
            "target_row_id": m["target_row_id"],
            "fixes": ["duplicate_rows"],
            "merged_qty": m["merged_qty"],
            "merged_reserved": m["merged_reserved"],
            "before": m["deleted_before"],
            "after": None,
        })

    summary = {
        "rows_scanned": len(rows),
        "rows_normalized": sum(1 for a in actions if a["type"] == "normalize_row"),
        "rows_merged": sum(1 for a in actions if a["type"] == "merge_row"),
        "rows_relocated": len(relocations),
        "fixes_by_type": {
            k: sum(1 for a in actions if k in (a.get("fixes") or []))
            for k in ISSUE_KEYS
            if k not in REPORT_ONLY
        },
        "unresolved_location": len(unresolved),
        "manual_attention": len(skipped_manual),
        "total_qty_before": round(sum(read_qty(r) for r in rows), 4),
    }

    if dry_run or not actions:
        return {
            "ok": True,
            "dry_run": True if dry_run else False,
            "applied": False,
            "log_id": None,
            "summary": summary,
            "actions_preview": [
                {k: v for k, v in a.items() if k not in ("before", "after")} for a in actions[:100]
            ],
            "relocations": relocations[:100],
            "unresolved": unresolved[:50],
            "manual_attention": skipped_manual[:50],
        }

    # ── EKSEKUSI ──────────────────────────────────────────────────────────────
    # PENTING: `rahaza_material_stock` punya UNIQUE index (material_id, location_id).
    # Baris kembar biasanya = satu baris kanonik (location_id terisi) + satu baris warisan
    # (lokasi nested/kosong => ter-index null). Saat baris warisan dinormalkan, location_id
    # jadi SAMA dengan baris kanonik; kalau kita menulis dulu lalu menghapus, MongoDB
    # menolak dengan DuplicateKeyError. Karena itu: HAPUS baris yang digabung LEBIH DULU,
    # baru tulis baris hasil normalisasi.
    log_id = _uid()
    for a in actions:
        if a["type"] == "merge_row":
            await db[COLL].delete_one({"id": a["row_id"]})
    for a in actions:
        if a["type"] == "normalize_row":
            doc = dict(a["after"])
            doc.pop("_id", None)
            await db[COLL].replace_one({"id": a["row_id"]}, doc, upsert=True)
    # baris keeper hasil merge sudah termasuk di actions normalize_row (fixes duplicate_rows)

    total_after = 0.0
    async for r in db[COLL].find({}, {"_id": 0}):
        total_after += read_qty(r)
    summary["total_qty_after"] = round(total_after, 4)
    summary["total_qty_preserved"] = abs(summary["total_qty_after"] - summary["total_qty_before"]) < 0.01

    await db[LOG_COLL].insert_one({
        "id": log_id,
        "created_at": _now(),
        "actor": {"id": (actor or {}).get("id", ""), "name": (actor or {}).get("name", "")},
        "dry_run": False,
        "summary": summary,
        "actions": actions,
        "relocations": relocations,
        "unresolved": unresolved,
        "manual_attention": skipped_manual,
        "rolled_back_at": None,
    })

    return {
        "ok": True,
        "dry_run": False,
        "applied": True,
        "log_id": log_id,
        "summary": summary,
        "actions_preview": [
            {k: v for k, v in a.items() if k not in ("before", "after")} for a in actions[:100]
        ],
        "relocations": relocations[:100],
        "unresolved": unresolved[:50],
        "manual_attention": skipped_manual[:50],
    }


async def rollback(db, log_id: str) -> dict:
    """Balikkan satu eksekusi rekonsiliasi ke kondisi sebelum (presisi per baris)."""
    log = await db[LOG_COLL].find_one({"id": log_id}, {"_id": 0})
    if not log:
        return {"ok": False, "error": f"Log rekonsiliasi '{log_id}' tidak ditemukan."}
    if log.get("rolled_back_at"):
        return {"ok": False, "error": "Log ini sudah pernah di-rollback."}

    restored = 0
    reinserted = 0
    acts = log.get("actions") or []
    # URUTAN PENTING (unique index material_id+location_id): pulihkan DULU baris yang
    # dinormalkan (location_id kembali ke bentuk lama/null), BARU hidupkan kembali baris
    # yang dihapus saat merge -- kalau dibalik, keduanya sempat memakai lokasi yang sama
    # dan MongoDB menolak insert.
    for a in acts:
        if a.get("type") != "normalize_row" or not a.get("before"):
            continue
        doc = dict(a["before"])
        doc.pop("_id", None)
        await db[COLL].replace_one({"id": a["row_id"]}, doc, upsert=True)
        restored += 1
    for a in acts:
        if a.get("type") != "merge_row" or not a.get("before"):
            continue
        doc = dict(a["before"])
        doc.pop("_id", None)
        exists = await db[COLL].find_one({"id": a["row_id"]}, {"_id": 0, "id": 1})
        if not exists:
            await db[COLL].insert_one(doc)
            reinserted += 1

    await db[LOG_COLL].update_one(
        {"id": log_id}, {"$set": {"rolled_back_at": _now()}}
    )
    return {"ok": True, "log_id": log_id, "rows_restored": restored, "rows_reinserted": reinserted}


async def logs(db, *, limit: int = 20) -> list:
    """Riwayat eksekusi rekonsiliasi (tanpa payload before/after yang besar)."""
    out = []
    async for d in db[LOG_COLL].find({}, {"_id": 0, "actions": 0}).sort("created_at", -1).limit(limit):
        out.append(d)
    return out
