"""core.marketing_live_fields — **SSOT nama field sesi live**.

CACAT YANG DISELESAIKAN BERKAS INI
---------------------------------
`marketing_live_sessions` punya DUA ejaan untuk angka yang sama, dan penulis
serta pembaca memakai ejaan yang berbeda:

| arti                  | yang DITULIS (seed/impor/CRUD) | yang DIBACA (ringkasan/analitik) |
|-----------------------|--------------------------------|----------------------------------|
| omzet sesi            | `revenue`                      | `gmv`                            |
| jumlah pesanan        | `orders`                       | `total_orders`                   |
| conversion rate       | `conversion_rate`              | `cr_rate`                        |
| penonton              | `total_viewers`                | `viewers`                        |

Akibatnya bisa dilihat langsung di satu layar: `GET /api/marketing/live/summary`
membalas `total_revenue: 0` dan `top_hosts` semuanya Rp 0, **padahal tabel di
bawahnya** (yang membaca dokumen mentah) menampilkan puluhan juta rupiah per sesi.
Layar yang membantah dirinya sendiri lebih merusak daripada layar yang error:
staf akan memilih angka yang enak dilihat, dan tidak ada yang tahu mana yang benar.

KEPUTUSAN
---------
Nama KANONIK = ejaan yang dipakai penulis dan layar tabel: `revenue`, `orders`,
`total_viewers`, `conversion_rate`, `engagement_rate`. Ejaan lama (`gmv`,
`total_orders`, `cr_rate`, `viewers`) tetap DIBACA sebagai cadangan lewat helper
di berkas ini, supaya dokumen lama yang sudah tersimpan tidak mendadak jadi nol —
tetapi **tidak ada penulis baru yang boleh memakainya**.

Kenapa dibuat helper, bukan `$ifNull` yang ditulis ulang di setiap pipeline:
`marketing_live_analytics.py` saja punya 7 pipeline. Menyalin ekspresi 7 kali
berarti perbaikan berikutnya akan melewatkan satu — persis cara cacat ini lahir.
"""
from __future__ import annotations

from typing import Any, Dict


def _fallback(*names: str, default: Any = 0) -> Dict[str, Any]:
    """`$ifNull` berlapis: pakai nama pertama yang ada, jatuh ke default."""
    expr: Any = default
    for n in reversed(names):
        expr = {"$ifNull": [f"${n}", expr]}
    return expr


# Angka uang & volume — kanonik dulu, ejaan lama sebagai cadangan.
REVENUE = _fallback("revenue", "gmv")
ORDERS = _fallback("orders", "total_orders")
UNITS = _fallback("units_sold", "products_featured")
VIEWERS = _fallback("total_viewers", "viewers")
PEAK_VIEWERS = _fallback("peak_viewers")
DURATION = _fallback("duration_minutes")
LIKES = _fallback("likes")
COMMENTS = _fallback("comments")
SHARES = _fallback("shares")
CONVERSION = _fallback("conversion_rate", "cr_rate")
ENGAGEMENT = _fallback("engagement_rate")

# AOV tidak disimpan; dihitung supaya tidak ada dua versi angka yang beredar.
AOV = {"$cond": [{"$gt": [ORDERS, 0]}, {"$divide": [REVENUE, ORDERS]}, 0]}

# Nama field yang WAJIB dipakai penulis baru (CRUD & impor).
CANONICAL_WRITE = (
    "account_id", "account_name", "platform", "host_id", "host_name",
    "session_date", "title", "duration_minutes", "peak_viewers",
    "total_viewers", "likes", "comments", "shares", "orders", "revenue",
    "units_sold", "products_featured", "conversion_rate", "engagement_rate",
    "status",
)

# Ejaan lama yang TIDAK BOLEH ditulis lagi (dijaga gate INV-MKTSCOPE).
DEPRECATED_WRITE = ("gmv", "total_orders", "cr_rate", "viewers", "orders_count",
                    "total_revenue_rp", "avg_order_value")


def compute_derived(doc: dict) -> dict:
    """Hitung ulang angka turunan dari angka mentah (dipakai CRUD & impor).

    Diletakkan di sini supaya CRUD manual, impor berkas, dan penyelarasan
    otomatis tidak pernah menghasilkan tiga versi `conversion_rate`.
    """
    def num(k, alt=None, d=0.0):
        v = doc.get(k)
        if v is None and alt:
            v = doc.get(alt)
        try:
            return float(v)
        except (TypeError, ValueError):
            return d

    viewers = num("total_viewers", "viewers")
    orders = num("orders", "total_orders")
    revenue = num("revenue", "gmv")
    inter = num("likes") + num("comments") + num("shares")
    doc["engagement_rate"] = round(inter / viewers * 100, 2) if viewers else 0
    doc["conversion_rate"] = round(orders / viewers * 100, 2) if viewers else 0
    doc["aov"] = round(revenue / orders, 2) if orders else 0
    return doc


def date_match(field: str, start, end) -> Dict[str, Any]:
    """Filter rentang tanggal yang TAHAN dua bentuk penyimpanan.

    Cacat nyata yang ditutup: `marketing_live_sessions.session_date` disimpan
    sebagai **datetime**, tetapi seluruh analitik live memfilternya dengan
    **string** ``"YYYY-MM-DD"``. Di MongoDB, string dan date berada di urutan tipe
    BSON yang berbeda, sehingga perbandingannya TIDAK PERNAH cocok ⇒ semua
    endpoint `/live/analytics/*` membalas 0 / daftar kosong tanpa satu pun error.
    """
    s_iso = start.date().isoformat() if hasattr(start, "date") else str(start)[:10]
    e_iso = end.date().isoformat() if hasattr(end, "date") else str(end)[:10]
    return {"$or": [
        {field: {"$gte": start, "$lte": end}},
        {field: {"$gte": s_iso, "$lte": e_iso + "\uffff"}},
    ]}


def date_as_string(field: str) -> Dict[str, Any]:
    """Proyeksikan tanggal menjadi "YYYY-MM-DD" apa pun tipe simpanannya."""
    return {"$cond": [
        {"$eq": [{"$type": f"${field}"}, "date"]},
        {"$dateToString": {"format": "%Y-%m-%d", "date": f"${field}"}},
        {"$substrBytes": [{"$ifNull": [f"${field}", ""]}, 0, 10]},
    ]}
