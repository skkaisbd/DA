"""core/material_cost_history.py — SSOT "KAPAN & KENAPA harga barang berubah?" (sesi #33).

═══════════════════════════════════════════════════════════════════════════════
MASALAH YANG DISELESAIKAN (terukur 2026-08-23, data hidup)
═══════════════════════════════════════════════════════════════════════════════
Koleksi `rahaza_material_cost_history` sudah terisi otomatis sejak sesi #29/#30
(SSOT `core/accessory_valuation._record_history`) untuk SEMUA jenis material —
pembelian kain, aksesoris, benang, sampai rata-rata bergerak HPP **potongan**
yang lahir sesi #32. Tetapi satu-satunya PEMBACA adalah
`GET /api/acc/valuation/cost-history` milik layar **AKSESORIS**, dan query-nya
`{"material_id": ...} if material_id else {}` — **tanpa filter jenis**.

Akibatnya dua-duanya salah sekaligus:
  1. Layar "Valuasi Aksesoris" MENAMPILKAN riwayat material KAIN (terukur: 2 dari
     7 material di daftar bertipe `fabric`) ⇒ layar berbohong tentang isinya.
  2. Untuk 335 material lain **tidak ada layar mana pun** yang bisa menjawab
     "kenapa HPP potongan/produk saya berubah?", padahal seluruh HPP sesi #31/#32
     lahir dari angka-angka di koleksi ini.

Berkas ini menjadi SATU pembaca resmi: menggabungkan riwayat dengan identitas
barang, menghitung % perubahan per baris, dan MENYEBUT sumber tiap baris.
Kalau riwayatnya kosong, ia mengembalikan **alasan** — bukan tabel kosong tanpa
penjelasan (pelajaran berulang: layar yang diam membuat pemakai menebak).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

COLL = "rahaza_material_cost_history"
MASTER = "rahaza_materials"

# Jenis material yang dianggap "aksesoris" oleh Portal Aksesoris (dipakai juga
# untuk MENYARING layar itu supaya tidak lagi menampilkan kain).
ACCESSORY_TYPES = ("accessory", "packaging")

TYPE_GROUPS = {
    "bahan": ["yarn", "fabric", "kain", "benang", "interlining"],
    "aksesoris": list(ACCESSORY_TYPES),
    "fg": ["fg"],
    "panel": ["panel"],
}

SOURCE_LABEL = {
    "receive": "Pembelian (penerimaan barang)",
    "manual": "Koreksi manual",
    "adjust": "Penyesuaian stok",
    "return": "Retur",
}
# Riwayat nilai POTONGAN memakai jalur `apply_receipt_cost` yang sama (source
# `receive`), jadi dibedakan dari catatannya — lihat `core/cut_panel_value`.
PANEL_NOTE_PREFIX = "potongan dari cutting"


def _f(v) -> float:
    try:
        if v in (None, ""):
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _now():
    return datetime.now(timezone.utc)


def _pct(old: float, new: float):
    """% perubahan. `None` bila harga lama 0 (perubahan dari 0 bukan persentase)."""
    if old <= 0:
        return None
    return round((new - old) / old * 100.0, 2)


def source_label(row: dict) -> str:
    notes = str(row.get("notes") or "").strip().lower()
    if notes.startswith(PANEL_NOTE_PREFIX):
        return "Hasil cutting (nilai potongan)"
    return SOURCE_LABEL.get(str(row.get("source") or ""), str(row.get("source") or "—"))


def _parse_date(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        s = str(v).strip().replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


async def _master_index(db, ids: list) -> dict:
    ids = [i for i in set(ids or []) if i]
    if not ids:
        return {}
    rows = await db[MASTER].find({"id": {"$in": ids}}, {"_id": 0}).to_list(len(ids) + 10)
    return {r["id"]: r for r in rows if r.get("id")}


async def _ids_for_filter(db, *, types: list | None, search: str) -> list | None:
    """Terjemahkan filter identitas barang menjadi daftar id (None = tanpa filter)."""
    q: dict = {}
    if types:
        q["type"] = {"$in": types}
    if search:
        import re
        pat = re.compile(re.escape(search), re.IGNORECASE)
        q["$or"] = [{"code": pat}, {"name": pat}]
    if not q:
        return None
    rows = await db[MASTER].find(q, {"_id": 0, "id": 1}).to_list(20000)
    return [r["id"] for r in rows if r.get("id")]


def summarize(rows: list, master: dict | None) -> dict:
    """Ringkasan satu barang: harga kini, pertama, terendah, tertinggi, % perubahan.

    `rows` HARUS urut terbaru→lama (seperti yang dikirim `history`).
    """
    master = master or {}
    if not rows:
        return {
            "changes": 0, "current_unit_cost": round(_f(master.get("unit_cost")), 4),
            "first_unit_cost": 0.0, "min_unit_cost": 0.0, "max_unit_cost": 0.0,
            "change_pct": None, "last_change_at": None, "last_purchase_unit_cost":
                round(_f(master.get("last_receipt_unit_cost")), 4),
        }
    oldest = rows[-1]
    first = _f(oldest.get("old_unit_cost")) or _f(oldest.get("new_unit_cost"))
    seen = [_f(r.get("new_unit_cost")) for r in rows]
    seen += [_f(r.get("old_unit_cost")) for r in rows if _f(r.get("old_unit_cost")) > 0]
    seen = [v for v in seen if v > 0] or [0.0]
    current = _f(master.get("unit_cost")) or _f(rows[0].get("new_unit_cost"))
    purchases = [r for r in rows if str(r.get("source")) == "receive"]
    return {
        "changes": len(rows),
        "current_unit_cost": round(current, 4),
        "first_unit_cost": round(first, 4),
        "min_unit_cost": round(min(seen), 4),
        "max_unit_cost": round(max(seen), 4),
        "change_pct": _pct(first, current),
        "last_change_at": rows[0].get("created_at"),
        "last_purchase_unit_cost": round(
            _f((purchases[0] if purchases else {}).get("unit_cost_in")), 4),
    }


async def history(db, *, material_id: str = "", types: list | None = None, search: str = "",
                  date_from=None, date_to=None, limit: int = 300) -> dict:
    """Riwayat harga (terbaru dulu) + ringkasan + ALASAN bila kosong."""
    q: dict = {}
    material = None
    if material_id:
        q["material_id"] = material_id
        material = await db[MASTER].find_one({"id": material_id}, {"_id": 0})
    else:
        ids = await _ids_for_filter(db, types=types, search=(search or "").strip())
        if ids is not None:
            if not ids:
                return {"items": [], "summary": summarize([], None), "reason":
                        "Tidak ada barang yang cocok dengan filter ini, jadi riwayat harganya "
                        "juga tidak ada. Ubah kata pencarian atau jenis barangnya.",
                        "total": 0}
            q["material_id"] = {"$in": ids}

    dfrom, dto = _parse_date(date_from), _parse_date(date_to)
    if dfrom or dto:
        rng = {}
        if dfrom:
            rng["$gte"] = dfrom
        if dto:
            rng["$lte"] = dto + timedelta(days=1)
        q["created_at"] = rng

    rows = await db[COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(max(1, min(limit, 2000)))
    masters = await _master_index(db, [r.get("material_id") for r in rows])
    if material and material.get("id"):
        masters.setdefault(material["id"], material)

    items = []
    for r in rows:
        m = masters.get(r.get("material_id")) or {}
        old, new = _f(r.get("old_unit_cost")), _f(r.get("new_unit_cost"))
        # Barang bisa SUDAH DIHAPUS sementara riwayat harganya tertinggal. Layar
        # tidak boleh menampilkan sel kosong tanpa penjelasan (sesi #33: terukur
        # 10 dari 19 baris adalah sisa alat ukur). Baris yatim DIKATAKAN apa
        # adanya; sumbernya dijaga INV-F38 C16 (keadaan akhir 0 yatim).
        missing = not m
        items.append({
            **r,
            "material_code": m.get("code") or ("(barang sudah dihapus)" if missing else ""),
            "material_name": m.get("name") or ("Master barang ini tidak ada lagi — "
                                               "riwayatnya tertinggal" if missing else ""),
            "material_missing": missing,
            "material_type": m.get("type") or "",
            "unit": m.get("unit") or m.get("base_uom") or "",
            "change_abs": round(new - old, 4),
            "change_pct": _pct(old, new),
            "source_label": source_label(r),
            "actor_name": ((r.get("actor") or {}).get("name") or "").strip() or "sistem",
        })

    reason = ""
    if not items:
        if material:
            reason = (
                f"Belum ada perubahan harga tercatat untuk {material.get('code') or ''} "
                f"{material.get('name') or ''}. Harga barang LAHIR otomatis saat "
                f"Penerimaan Barang berstatus 'diterima' di gudang (rata-rata bergerak), "
                f"atau saat harga dikoreksi manual di layar Valuasi. "
                f"Harga sekarang: {_f(material.get('unit_cost')):,.2f}.")
        elif material_id:
            reason = ("Barang tidak ditemukan di Master Item — mungkin sudah dihapus. "
                      "Pilih barang lain dari daftar.")
        else:
            reason = ("Belum ada satu pun perubahan harga tercatat pada rentang/filter ini. "
                      "Riwayat terisi sendiri setiap kali barang diterima dari pembelian.")

    return {
        "items": items,
        "total": len(items),
        "summary": summarize(rows, masters.get(material_id) if material_id else None),
        "material": ({"id": material.get("id"), "code": material.get("code"),
                      "name": material.get("name"), "type": material.get("type"),
                      "unit": material.get("unit") or material.get("base_uom"),
                      "unit_cost": round(_f(material.get("unit_cost")), 4),
                      "cost_method": material.get("cost_method") or ""}
                     if material else None),
        "reason": reason,
    }


async def materials_index(db, *, types: list | None = None, search: str = "",
                          only_with_history: bool = False, limit: int = 2000) -> dict:
    """Daftar barang untuk pemilih layar + berapa kali harganya berubah."""
    q: dict = {"active": True}
    if types:
        q["type"] = {"$in": types}
    if (search or "").strip():
        import re
        pat = re.compile(re.escape(search.strip()), re.IGNORECASE)
        q["$or"] = [{"code": pat}, {"name": pat}]
    mats = await db[MASTER].find(q, {"_id": 0}).sort([("type", 1), ("code", 1)]).to_list(limit)
    ids = [m["id"] for m in mats if m.get("id")]
    counts: dict = {}
    last: dict = {}
    if ids:
        cur = db[COLL].aggregate([
            {"$match": {"material_id": {"$in": ids}}},
            {"$group": {"_id": "$material_id", "n": {"$sum": 1},
                        "last_at": {"$max": "$created_at"}}},
        ])
        async for row in cur:
            counts[row["_id"]] = int(row.get("n") or 0)
            last[row["_id"]] = row.get("last_at")
    out = []
    for m in mats:
        n = counts.get(m.get("id"), 0)
        if only_with_history and n <= 0:
            continue
        out.append({
            "material_id": m.get("id"), "code": m.get("code") or "",
            "name": m.get("name") or "", "type": m.get("type") or "",
            "unit": m.get("unit") or m.get("base_uom") or "",
            "unit_cost": round(_f(m.get("unit_cost")), 4),
            "changes": n, "last_change_at": last.get(m.get("id")),
        })
    total_changes = sum(counts.values())
    return {
        "items": out,
        "total": len(out),
        "summary": {
            "materials": len(mats),
            "with_history": sum(1 for m in mats if counts.get(m.get("id"), 0) > 0),
            "without_history": sum(1 for m in mats if counts.get(m.get("id"), 0) <= 0),
            "total_changes": total_changes,
            "unvalued": sum(1 for m in mats if _f(m.get("unit_cost")) <= 0),
        },
    }
