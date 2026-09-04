"""core/catalog_margin.py — **SATU rumus margin katalog marketing** (sesi #37).

═══════════════════════════════════════════════════════════════════════════════
MASALAH NYATA YANG DITUTUP BERKAS INI
═══════════════════════════════════════════════════════════════════════════════
Diukur sebelum sesi ini: `marketing_catalog_items` berisi 78 item dan **tidak
satu pun** punya `margin_pct` tersimpan. Endpoint daftar katalog memang
menghitungnya saat baca, tetapi dengan rumus yang menipu:

    row['margin_pct'] = round((hj - hpp) / hj * 100, 1) if hj > 0 else 0.0

Kalau `hpp` = 0 — dan itu keadaan MAYORITAS item, karena HPP baru lahir setelah
BOM/biaya jahit terisi — rumus itu menghasilkan **100%**. Kalau `harga_jual`
juga 0, hasilnya **0%**. Dua-duanya angka yang terlihat sah, dan dua-duanya
BOHONG: yang benar adalah "belum bisa diukur".

Bahayanya bukan teoretis. Marketing memakai kolom margin untuk memutuskan
diskon dan harga flash sale. Item yang HPP-nya belum diketahui akan tampil
sebagai margin 100% — yaitu item yang paling "aman" didiskon — padahal ia justru
satu-satunya item yang untung-ruginya TIDAK diketahui siapa pun.

═══════════════════════════════════════════════════════════════════════════════
ATURAN
═══════════════════════════════════════════════════════════════════════════════
1. **HPP EFEKTIF** dipilih menurut urutan yang paling dekat dengan biaya nyata:
   `hpp_fifo_avg` FG  →  `hpp` FG  →  `hpp` katalog.
   Sumbernya selalu ikut dilaporkan (`hpp_source_effective`) supaya pembaca
   laporan tahu angka itu berasal dari lapisan batch, dari master, atau dari
   ketikan tangan di katalog.
2. **HPP tidak diketahui ⇒ `margin_status='belum_bisa_diukur'`, `margin_pct=None`.**
   BUKAN 0, BUKAN 100. `None` memaksa layar menampilkan lencana, bukan angka.
3. Alasannya ditulis (`margin_reason`) — "belum bisa diukur" tanpa sebab hanya
   memindahkan kebingungan, bukan menyelesaikannya.
"""
from __future__ import annotations

OK = "ok"
UNKNOWN = "belum_bisa_diukur"

# Urutan sumber HPP, dari yang paling dekat dengan biaya nyata.
HPP_PRIORITY = (
    ("hpp_fifo_avg", "fg_fifo_avg"),
    ("hpp", "fg_master"),
)


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


async def fg_cost_map(db, material_ids: list) -> dict:
    """{material_id: {hpp, source}} — satu kueri, bukan N+1."""
    mids = [m for m in set(material_ids or []) if m]
    if not mids:
        return {}
    rows = await db.rahaza_materials.find(
        {"id": {"$in": mids}},
        {"_id": 0, "id": 1, "hpp": 1, "hpp_fifo_avg": 1, "hpp_source": 1},
    ).to_list(len(mids) + 10)
    out = {}
    for r in rows:
        chosen = 0.0
        src = ""
        for field, label in HPP_PRIORITY:
            val = _f(r.get(field))
            if val > 0:
                chosen, src = val, label
                break
        out[r["id"]] = {"hpp": chosen, "source": src}
    return out


def decorate(row: dict, fg_cost: dict = None) -> dict:
    """Isi `hpp_effective`, `margin`, `margin_pct`, `margin_status`, alasan.

    `fg_cost` = entri dari `fg_cost_map()` untuk FG yang tertaut (boleh None).
    Mengubah `row` di tempat DAN mengembalikannya (dipakai berantai).
    """
    harga_jual = _f(row.get("harga_jual"))
    fg = fg_cost or {}
    hpp = _f(fg.get("hpp"))
    source = fg.get("source") or ""
    if hpp <= 0:
        hpp = _f(row.get("hpp"))
        source = "catalog_manual" if hpp > 0 else "none"

    row["hpp_effective"] = round(hpp, 2)
    row["hpp_source_effective"] = source

    reasons = []
    if harga_jual <= 0:
        reasons.append("harga jual belum diisi")
    if hpp <= 0:
        if not row.get("fg_material_id"):
            reasons.append("belum tertaut ke Master Produk / FG, jadi HPP tidak "
                           "bisa diambil dari mana pun")
        else:
            reasons.append("FG-nya belum punya HPP — BOM atau biaya jahit "
                           "(SPK) belum tercatat")

    if reasons:
        row["margin"] = None
        row["margin_pct"] = None
        row["margin_status"] = UNKNOWN
        row["margin_reason"] = ("Belum bisa diukur: " + "; ".join(reasons) + ".")
    else:
        margin = harga_jual - hpp
        row["margin"] = round(margin, 2)
        row["margin_pct"] = round(margin / harga_jual * 100, 1)
        row["margin_status"] = OK
        row["margin_reason"] = ""
    return row


def summarize(rows: list) -> dict:
    """Ringkas kesehatan margin SELURUH katalog (bukan halaman yang tampil)."""
    measurable = [r for r in rows if r.get("margin_status") == OK]
    unknown = [r for r in rows if r.get("margin_status") == UNKNOWN]
    avg = (round(sum(_f(r.get("margin_pct")) for r in measurable) / len(measurable), 1)
           if measurable else None)
    return {
        "measurable": len(measurable),
        "unmeasurable": len(unknown),
        "avg_margin_pct": avg,
        "hpp_sources": {
            s: sum(1 for r in rows if r.get("hpp_source_effective") == s)
            for s in sorted({r.get("hpp_source_effective") or "none" for r in rows})
        },
        "note": ("Item tanpa HPP dilaporkan sebagai 'belum bisa diukur' dan TIDAK "
                 "ikut menghitung rata-rata margin — memasukkannya sebagai 0% atau "
                 "100% akan membuat rata-rata katalog menyesatkan."),
    }
