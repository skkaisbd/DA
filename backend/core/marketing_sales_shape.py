"""core.marketing_sales_shape — **SATU-SATUNYA** pembuat & pembaca bentuk `marketing_sales_data`.

KENAPA BERKAS INI ADA (cacat D01, terukur 2026-08-12)
-----------------------------------------------------
Rekap harian satu toko ditulis oleh **empat** pintu, dan sebelum berkas ini ada, ketiga
pintu pertama menghasilkan **tiga bentuk dokumen yang berbeda** untuk hal yang sama:

| Pintu | Bentuk sebelum perbaikan |
|---|---|
| Entri manual (`routes/marketing_sales.py`) | `metrics{revenue,orders,aov,gmv,conversion_rate}` + `fulfillment{}` + `customer_satisfaction{}` + `live_metrics{}` |
| Impor `sales_daily` (`routes/marketing_data_import.py`) | **RATA** — `revenue`/`orders`/`aov` di akar dokumen, **tanpa `metrics{}`** |
| Impor lama `marketing_import.py` (F0.6: dihapus) | `metrics{… + quantity, rating}` saja, tanpa 3 grup lain |
| Sinkron live (`routes/marketing_live_sales_sync.py`) | bersarang (sudah benar) |

Akibat yang bisa ditunjuk di layar untuk **satu** baris impor Rp 12.500.000:
`GET /api/marketing/targets/monthly-summary` ⇒ **Rp 0** (membaca `metrics.revenue`) ·
`GET /api/marketing/dashboard/overview` ⇒ **HTTP 500** (`sale["metrics"]` diindeks langsung) ·
ROI anggaran ⇒ Rp 12.500.000 (punya fallback) · Health Score ⇒ **15** vs **89** untuk
angka yang sama. Satu angka, empat jawaban.

ATURAN MODUL INI
----------------
1. **Tidak ada** tempat lain yang boleh menyusun dokumen `marketing_sales_data`.
   Semua penulis memanggil :func:`build_daily_doc`.
2. **Tidak ada** pembaca yang boleh mengindeks `doc["metrics"]` langsung.
   Semua pembaca memakai :func:`read_metrics` / :func:`read_group` (keduanya tetap
   benar untuk dokumen lama yang masih berbentuk rata).
3. Kunci alami dokumen: `(account_id, date, revenue_type)` — `date` selalu string
   `"YYYY-MM-DD"`, `revenue_type` ∈ {`total`, `live`}.
4. Grup **selalu ada** sebagai objek (boleh kosong) supaya pembaca tidak pernah
   bertemu `None`. Grup `live_metrics` sengaja `{}` untuk `revenue_type='total'`
   — ini mempertahankan makna skor **Engagement** pada `_recalculate_health_score`
   (yang menghitung hanya dokumen live yang punya `live_metrics`).
5. **Dua angka omzet** disimpan berdampingan (keputusan owner K1):
   `metrics.revenue_product` (Σ subtotal SKU setelah diskon penjual) dan
   `metrics.revenue_order_amount` (yang dibayar pembeli, termasuk ongkir).
   `metrics.revenue` = salah satunya sesuai `revenue_basis` toko, dan itulah yang
   dipakai Target/Dashboard/ROI supaya semua layar memakai satu makna.
"""
from __future__ import annotations

from datetime import datetime, date as _date, timezone
from typing import Any, Dict, Optional

# ── basis omzet (K1) ─────────────────────────────────────────────────────────
BASIS_PRODUCT = "produk_setelah_diskon"
BASIS_ORDER_AMOUNT = "order_amount"
DEFAULT_BASIS = BASIS_PRODUCT
VALID_BASIS = (BASIS_PRODUCT, BASIS_ORDER_AMOUNT)

REVENUE_TYPES = ("total", "live")

# ── sumber penulis (dipakai untuk kunci & label di layar) ────────────────────
SOURCE_ORDERS_AUTO = "orders_auto"            # F2 — diturunkan dari marketing_orders
SOURCE_LIVE_AUTO = "livehost_creator_auto"    # sudah ada — dari shift/sesi kreator
SOURCE_MANUAL = "manual"                      # diketik manusia
SOURCE_IMPORT = "import"                      # impor rekap harian (platform tanpa ekspor pesanan)
SOURCE_IMPORT_KPI = "import_kpi"              # F8 — hanya mengisi grup KPI
SOURCE_TASK = "task_action"                   # aksi dari modul Tugas
# F2 (2026-08-12) — SPV MENGGANTI angka turunan secara sadar (dengan alasan).
# Bukan "derived": angka ini boleh diedit lagi, tetapi TIDAK ditimpa rollup
# otomatis kecuali diminta paksa. Lihat core/marketing_daily_rollup.py.
SOURCE_MANUAL_OVERRIDE = "manual_override"

# Sumber yang angkanya DITURUNKAN sistem ⇒ entri manual ke grup `metrics` ditolak.
DERIVED_SOURCES = (SOURCE_ORDERS_AUTO,)

# ── skema grup: nama grup → {field: nilai default} ───────────────────────────
# Field ditulis apa adanya seperti di memory/SSOT_KONTRAK_DATA_2026-08-12.md §3.
METRICS_FIELDS: Dict[str, float] = {
    "revenue": 0.0,                 # = basis toko (lihat DEFAULT_BASIS)
    "revenue_product": 0.0,         # Σ items.sku_subtotal_after_discount
    "revenue_order_amount": 0.0,    # Σ order_amount (per pesanan, 1×)
    "gross_before_discount": 0.0,   # Σ items.sku_subtotal_before_discount (harga coret)
    "seller_discount": 0.0,         # Σ items.sku_seller_discount  → realisasi anggaran 'diskon'
    "platform_discount": 0.0,       # ditanggung platform (bukan biaya kita)
    "orders": 0,
    "units": 0,
    "buyers": 0,
    "aov": 0.0,
    "gmv": 0.0,
    "conversion_rate": 0.0,
}
FUNNEL_FIELDS: Dict[str, float] = {
    "uv": 0, "pv": 0, "product_clicks": 0, "ctr": 0.0,
    "atc_visitors": 0, "atc_units": 0,
    "cart_to_order_cr": 0.0, "order_to_paid_cr": 0.0,
}
BUYERS_MIX_FIELDS: Dict[str, float] = {
    "new_buyers": 0, "returning_buyers": 0,
    "sales_new": 0.0, "sales_returning": 0.0,
}
TRAFFIC_FIELDS: Dict[str, float] = {
    "live": 0.0, "video": 0.0, "ads": 0.0, "affiliate": 0.0,
    "campaign": 0.0, "organic": 0.0, "product_card": 0.0,
    "search": 0.0, "other": 0.0,
}
# 4 field pertama WAJIB ada (dipakai skor kesehatan); sisanya tambahan F2/F3.
FULFILLMENT_FIELDS: Dict[str, float] = {
    "fulfillment_rate": 0.0, "cancellation_rate": 0.0,
    "return_rate": 0.0, "late_shipment_rate": 0.0,
    "processing_hours": 0.0,
    "cancelled_orders": 0, "cancelled_value": 0.0,
    "returned_orders": 0, "returned_value": 0.0,
    # SESI #9 — "omzet setelah retur" (keputusan pemilik: tampilkan DUA angka).
    # `returned_value` sudah ada dan artinya **order amount** (yang dibayar
    # pembeli, termasuk ongkir). Basis omzet toko bisa `produk_setelah_diskon`,
    # jadi butuh nilai retur pada basis PRODUK juga — mengurangi order amount dari
    # omzet produk melahirkan net yang terlalu kecil tanpa ada yang tahu.
    "returned_revenue_product": 0.0,
    "returned_units": 0,
}
SATISFACTION_FIELDS: Dict[str, float] = {
    "rating": 0.0, "review_count": 0,
    "response_rate": 0.0, "response_time_hours": 0.0,
}
LIVE_FIELDS: Dict[str, float] = {
    "viewers": 0, "unique_viewers": 0, "avg_viewers": 0.0, "peak_viewers": 0,
    "watch_time_avg_sec": 0.0, "likes": 0, "shares": 0, "comments": 0,
    "new_followers": 0, "live_sessions": 0,
}
CONTENT_FIELDS: Dict[str, float] = {
    "video_views": 0, "video_completion_rate": 0.0, "saves": 0, "gmv_per_video": 0.0,
}

# ── SATUAN KANONIK: PERSEN 0–100 (bukan fraksi 0–1) ──────────────────────────
# Kenapa ini perlu ditulis: sebelum F0 ada DUA konvensi dalam SATU koleksi.
#   · Mesin impor (`core/marketing_import_schema` kind='pct') menyimpan 0–100
#     dan berlabel "(%)" — sama dengan yang dilaporkan Seller Center.
#   · Form entri manual bertanya "Conversion Rate (0-1)" dan menyimpan 0,98.
# Akibat terukur (dibuktikan `test_core_f0_sales_shape.py`): untuk data yang SAMA,
# `_recalculate_health_score` memberi **79** (jalur manual, dibaca sebagai fraksi)
# vs **100** (jalur impor, 98 dikali 10 ⇒ jauh di atas pagu). Satu kenyataan, dua skor.
#
# Keputusan: **persen 0–100** adalah satuan kanonik untuk seluruh field di bawah.
# Nilai `0 < v <= 1` ditafsirkan sebagai fraksi lama dan dikali 100 — aturan yang
# SAMA dengan yang sudah dipakai mesin impor, ditulis SEKALI di sini, dan setiap
# konversinya dicatat di `doc['unit_notes']` supaya tidak ada penyesuaian diam-diam.
PCT_FIELDS = {
    "metrics": ("conversion_rate",),
    "funnel": ("ctr", "cart_to_order_cr", "order_to_paid_cr"),
    "fulfillment": ("fulfillment_rate", "cancellation_rate", "return_rate",
                    "late_shipment_rate"),
    "customer_satisfaction": ("response_rate",),
    "content_metrics": ("video_completion_rate",),
}


def to_percent(value: Any) -> tuple[float, bool]:
    """→ (nilai dalam persen 0–100, apakah dikonversi dari fraksi)."""
    v = _num(value)
    if 0 < v <= 1:
        return round(v * 100, 4), True
    return round(v, 4), False


def to_fraction(value: Any) -> float:
    """Persen 0–100 → fraksi 0–1 untuk rumus yang memang butuh fraksi.

    Dipakai `_recalculate_health_score`. Nilai ≤ 1 dibiarkan (dokumen lama yang
    memang sudah fraksi) supaya skor lama tidak berubah tanpa sebab.
    """
    v = _num(value)
    return v / 100.0 if v > 1 else v

GROUPS: Dict[str, Dict[str, float]] = {
    "metrics": METRICS_FIELDS,
    "funnel": FUNNEL_FIELDS,
    "buyers_mix": BUYERS_MIX_FIELDS,
    "traffic": TRAFFIC_FIELDS,
    "fulfillment": FULFILLMENT_FIELDS,
    "customer_satisfaction": SATISFACTION_FIELDS,
    "live_metrics": LIVE_FIELDS,
    "content_metrics": CONTENT_FIELDS,
}

# Grup yang SELALU diisi lengkap (kompatibel dengan entri manual lama & skor kesehatan)
ALWAYS_FILLED = ("metrics", "fulfillment", "customer_satisfaction")
# Grup yang hanya diisi bila ada datanya (kosong = belum ada sumbernya, bukan nol)
FILL_IF_PRESENT = ("funnel", "buyers_mix", "traffic", "content_metrics")

# Sinonim field datar → (grup, field kanonik). Dipakai supaya pemanggil boleh
# mengirim nama lama tanpa harus tahu strukturnya.
_ALIAS: Dict[str, tuple] = {}
for _g, _fields in GROUPS.items():
    for _f in _fields:
        _ALIAS.setdefault(_f, (_g, _f))
# alias eksplisit (nama lama / nama di form)
_ALIAS.update({
    "quantity": ("metrics", "units"),
    "total_revenue": ("metrics", "revenue"),
    "total_orders": ("metrics", "orders"),
    "peak_viewers": ("live_metrics", "peak_viewers"),
    "watch_time": ("live_metrics", "watch_time_avg_sec"),
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _num(v: Any, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _int(v: Any, default: int = 0) -> int:
    return int(_num(v, default))


def norm_date(value: Any) -> str:
    """Apa pun → `"YYYY-MM-DD"`. Wajib: kunci dokumen memakai string, bukan datetime."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, _date):
        return value.strftime("%Y-%m-%d")
    s = str(value or "").strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    # toleransi "DD/MM/YYYY"
    if len(s) >= 10 and s[2] == "/" and s[5] == "/":
        return f"{s[6:10]}-{s[3:5]}-{s[0:2]}"
    return s


def resolve_basis(account: Optional[dict], override: Optional[str] = None) -> str:
    """Basis omzet toko: override → `account.revenue_basis` → default."""
    for cand in (override, (account or {}).get("revenue_basis")):
        if cand in VALID_BASIS:
            return cand
    return DEFAULT_BASIS


def build_daily_doc(
    *,
    account: dict,
    date: Any,
    revenue_type: str,
    flat: Dict[str, Any],
    source: str,
    revenue_basis: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Susun dokumen `marketing_sales_data` yang **kanonik**.

    ``flat`` = angka datar dengan nama field kanonik (atau alias di ``_ALIAS``),
    dari mana pun asalnya: form manual, baris impor, atau hasil hitung ulang pesanan.
    Nilai yang tidak dikirim **tidak ditebak** — ia memakai default 0 pada grup
    ``ALWAYS_FILLED``, dan grup ``FILL_IF_PRESENT`` dibiarkan **kosong** supaya
    layar bisa membedakan \"nol\" dari \"belum ada sumbernya\".

    Dokumen yang dikembalikan **tanpa** `id`/`created_at` — itu tanggung jawab
    pemanggil (insert vs upsert `$setOnInsert`).
    """
    if revenue_type not in REVENUE_TYPES:
        raise ValueError(f"revenue_type harus salah satu dari {REVENUE_TYPES}, bukan '{revenue_type}'")

    basis = resolve_basis(account, revenue_basis)
    src = dict(flat or {})

    # ── sebar nilai datar ke grup yang benar ─────────────────────────────────
    buckets: Dict[str, Dict[str, Any]] = {g: {} for g in GROUPS}
    unknown: Dict[str, Any] = {}
    for k, v in src.items():
        if v is None:
            continue
        # bentuk bersarang boleh dikirim langsung (mis. {"traffic": {...}})
        if k in GROUPS and isinstance(v, dict):
            buckets[k].update(v)
            continue
        target = _ALIAS.get(k)
        if target:
            buckets[target[0]][target[1]] = v
        else:
            unknown[k] = v

    # ── satuan persen dijadikan kanonik (0–100) di SATU tempat ───────────────
    unit_notes: list = []
    for gname, fields in PCT_FIELDS.items():
        for fname in fields:
            if fname in buckets[gname] and buckets[gname][fname] is not None:
                newv, converted = to_percent(buckets[gname][fname])
                if converted:
                    unit_notes.append(
                        f"{gname}.{fname}: {buckets[gname][fname]} ditafsirkan {newv}% "
                        f"(skala 0–1 → 0–100)")
                buckets[gname][fname] = newv

    m = buckets["metrics"]

    # ── dua angka omzet + basis (K1) ─────────────────────────────────────────
    rev_product = _num(m.get("revenue_product"), None) if "revenue_product" in m else None
    rev_order = _num(m.get("revenue_order_amount"), None) if "revenue_order_amount" in m else None
    rev_plain = _num(m.get("revenue"), None) if "revenue" in m else None

    if rev_product is None and rev_order is None:
        # Entri manual/impor rekap: satu angka omzet yang diketik dianggap
        # OMZET PRODUK (setelah diskon penjual, sebelum potongan platform).
        rev_product = rev_plain if rev_plain is not None else 0.0
    if rev_product is None:
        rev_product = 0.0
    if rev_order is None:
        rev_order = 0.0

    revenue = rev_order if basis == BASIS_ORDER_AMOUNT else rev_product
    if not revenue and rev_plain:
        revenue = rev_plain

    m["revenue_product"] = round(rev_product, 2)
    m["revenue_order_amount"] = round(rev_order, 2)
    m["revenue"] = round(revenue, 2)

    orders = _int(m.get("orders"))
    m["orders"] = orders
    if not _num(m.get("aov")) and orders > 0:
        m["aov"] = round(revenue / orders, 2)
    if not _num(m.get("gmv")):
        m["gmv"] = m["revenue"]

    # ── isi grup dengan default yang benar ───────────────────────────────────
    doc_groups: Dict[str, dict] = {}
    for gname, defaults in GROUPS.items():
        vals = buckets[gname]
        if gname == "live_metrics":
            # Sengaja `{}` untuk dokumen non-live (menjaga makna skor Engagement).
            if revenue_type != "live" and not vals:
                doc_groups[gname] = {}
                continue
            doc_groups[gname] = {k: (_cast(defaults[k], vals.get(k, defaults[k]))) for k in defaults}
            continue
        if gname in ALWAYS_FILLED:
            doc_groups[gname] = {k: (_cast(defaults[k], vals.get(k, defaults[k]))) for k in defaults}
        else:
            doc_groups[gname] = ({k: _cast(defaults[k], vals[k]) for k in defaults if k in vals}
                                 if vals else {})

    doc = {
        "account_id": account.get("id") or account.get("account_id"),
        "account_code": account.get("account_code", ""),
        "account_name": account.get("account_name", ""),
        "platform": account.get("platform", ""),
        "date": norm_date(date),
        "revenue_type": revenue_type,
        **doc_groups,
        "revenue_basis": basis,
        "source": source,
        "locked_source": source in DERIVED_SOURCES,
        "unit_pct_scale": "0-100",
        "shape_version": 2,
        "updated_at": _now(),
    }
    if unit_notes:
        doc["unit_notes"] = unit_notes
    if unknown:
        # Tidak dibuang diam-diam: disimpan terpisah supaya bisa ditelusuri,
        # tetapi TIDAK pernah menjadi field akar (akar = kontrak, bukan tebakan).
        doc["extra_raw"] = unknown
    if extra:
        doc.update(extra)
    return doc


def _cast(default: Any, value: Any) -> Any:
    return _int(value) if isinstance(default, int) and not isinstance(default, bool) else round(_num(value), 4)


# ══════════════════════════════════════════════════════════════════════════════
# PEMBACA AMAN — juga benar untuk dokumen LAMA yang masih berbentuk rata
# ══════════════════════════════════════════════════════════════════════════════
def read_group(doc: Optional[dict], group: str) -> dict:
    """Ambil satu grup dengan aman. Dokumen lama (rata) direkonstruksi apa adanya."""
    if not doc:
        return {}
    val = doc.get(group)
    if isinstance(val, dict) and val:
        return val
    defaults = GROUPS.get(group, {})
    flat = {k: doc[k] for k in defaults if k in doc}
    return flat


def read_metrics(doc: Optional[dict]) -> dict:
    """`metrics` yang **selalu** punya angka yang dipakai layar.

    Dokumen kanonik ⇒ dikembalikan apa adanya (dilengkapi default).
    Dokumen lama berbentuk rata ⇒ `revenue`/`orders`/`aov`/`gmv` diambil dari akar
    sehingga Target & Dashboard tetap jujur **sebelum** migrasi dijalankan.
    """
    if not doc:
        return dict(METRICS_FIELDS)
    m = doc.get("metrics")
    if not isinstance(m, dict) or not m:
        m = {k: doc[k] for k in METRICS_FIELDS if k in doc}
    out = dict(METRICS_FIELDS)
    out.update({k: v for k, v in (m or {}).items() if v is not None})
    # jaga-jaga dokumen lama yang hanya punya `revenue`
    if not _num(out.get("revenue_product")) and _num(out.get("revenue")):
        out["revenue_product"] = out["revenue"]
    return out


def revenue_of(doc: Optional[dict], basis: Optional[str] = None) -> float:
    """Omzet satu dokumen sesuai basis (default: basis yang tercatat di dokumen)."""
    m = read_metrics(doc)
    b = basis or (doc or {}).get("revenue_basis") or DEFAULT_BASIS
    if b == BASIS_ORDER_AMOUNT and _num(m.get("revenue_order_amount")):
        return _num(m["revenue_order_amount"])
    return _num(m.get("revenue")) or _num(m.get("revenue_product"))


def flatten(doc: Optional[dict]) -> dict:
    """Bentuk datar untuk form/UI (kebalikan `build_daily_doc`)."""
    out: Dict[str, Any] = {}
    for g in GROUPS:
        out.update(read_group(doc, g))
    for k in ("account_id", "date", "revenue_type", "source", "revenue_basis", "locked_source"):
        if doc and k in doc:
            out[k] = doc[k]
    return out


def is_derived(doc: Optional[dict]) -> bool:
    """True bila angka `metrics` dokumen ini dihitung sistem (tidak boleh diketik)."""
    if not doc:
        return False
    if doc.get("locked_source") is True:
        return True
    return (doc.get("source") or "") in DERIVED_SOURCES


# ══════════════════════════════════════════════════════════════════════════════
# PAGAR F2 UNTUK **SEMUA** PENULIS (bukan hanya entri manual)
# ══════════════════════════════════════════════════════════════════════════════
# Cacat yang ditutup 2026-08-12 (terbukti `scripts/_verify_f2_import_lock.py`):
# `POST /api/marketing/sales-data` sudah menolak 409 untuk tanggal turunan, tetapi
# Wizard Impor punya jenis data `sales_daily` yang menulis ke koleksi yang SAMA
# dengan kunci alami yang SAMA. Dengan mode "perbarui", satu berkas Excel
# menimpa omzet turunan **tanpa peringatan**: Rp 4.213.092 / 45 pesanan (dari 559
# pesanan nyata) berubah menjadi Rp 1.000.000 / 5 pesanan, dan dokumennya
# kehilangan kuncinya (`source='import'`, `locked_source=False`) sehingga rollup
# berikutnya pun tidak memulihkannya. Dua angka omzet untuk satu hari kembali lagi.
#
# Prinsipnya SAMA dengan aturan rollup: **lindungi angkanya, jangan buang datanya.**
# Grup di bawah adalah milik mesin turunan; sisanya (rating, funnel, live, konten)
# tidak bisa dihitung dari pesanan sehingga impor tetap boleh mengisinya.
DERIVED_GROUPS = ("metrics", "traffic")
DERIVED_FULFILLMENT_KEYS = ("cancelled_orders", "cancelled_value", "returned_orders",
                            "returned_value", "cancellation_rate", "return_rate",
                            "fulfillment_rate")
# Field akar yang menyatakan ASAL & KUNCI dokumen — penulis lain tidak boleh
# menyentuhnya (kalau ditimpa, dokumen turunan berubah jadi dokumen impor).
PROTECTED_ROOT_FIELDS = ("id", "account_id", "date", "revenue_type", "source",
                         "locked_source", "derived_from", "derived_at",
                         "override_reason", "override_by", "override_at",
                         "created_at", "created_by", "_import_session_id",
                         "_import_source_type")

# Label manusiawi untuk pesan di layar (staf tidak mengenal nama field).
_DERIVED_FIELD_LABELS = {
    "revenue": "Omzet", "revenue_product": "Omzet produk",
    "revenue_order_amount": "Nilai pesanan", "orders": "Jumlah pesanan",
    "units": "Jumlah pcs", "buyers": "Jumlah pembeli", "aov": "AOV",
    "gmv": "GMV", "gross_before_discount": "Harga coret",
    "seller_discount": "Diskon penjual", "platform_discount": "Diskon platform",
    "conversion_rate": "Conversion rate",
    "fulfillment_rate": "Tingkat pemenuhan", "cancellation_rate": "Tingkat pembatalan",
    "return_rate": "Tingkat retur", "cancelled_orders": "Pesanan batal",
    "returned_orders": "Pesanan retur",
    "returned_value": "Nilai retur (order amount)",
    "returned_revenue_product": "Nilai retur (omzet produk)",
    "returned_units": "Pcs retur",
}


def derived_safe_update(incoming: Optional[dict]) -> tuple[Dict[str, Any], list]:
    """Pisahkan dokumen rekap harian menjadi bagian yang AMAN ditulis vs DILINDUNGI.

    Dipakai penulis mana pun (impor `sales_daily`, sinkron, dsb.) ketika dokumen
    tujuan ternyata **turunan** (:func:`is_derived`).

    → ``($set datar bertitik untuk update aman, [label field yang dilindungi])``

    Aturan:
      * grup :data:`DERIVED_GROUPS` dan field :data:`DERIVED_FULFILLMENT_KEYS`
        **tidak pernah** ikut — itu milik `core.marketing_daily_rollup`;
      * field akar :data:`PROTECTED_ROOT_FIELDS` tidak pernah ikut — supaya
        dokumen turunan tidak berubah identitas/asalnya;
      * hanya nilai **berarti** (bukan 0/kosong) yang ditulis, karena
        `build_daily_doc` mengisi grup wajib dengan 0; menulis 0 apa adanya akan
        MENGHAPUS angka yang sudah diisi sumber lain (mis. rating dari F8).
    """
    safe: Dict[str, Any] = {}
    protected: list = []
    if not incoming:
        return safe, protected

    def meaningful(v: Any) -> bool:
        if v is None or v == "":
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return float(v) != 0.0
        return True

    for group, fields in GROUPS.items():
        vals = incoming.get(group)
        if not isinstance(vals, dict):
            continue
        for key, value in vals.items():
            if not meaningful(value):
                continue
            is_prot = (group in DERIVED_GROUPS
                       or (group == "fulfillment" and key in DERIVED_FULFILLMENT_KEYS))
            if is_prot:
                protected.append(_DERIVED_FIELD_LABELS.get(key, f"{group}.{key}"))
            else:
                safe[f"{group}.{key}"] = value

    for key, value in incoming.items():
        if key in PROTECTED_ROOT_FIELDS or key in GROUPS:
            continue
        if key in ("updated_at", "updated_by", "unit_notes", "notes"):
            continue
        if meaningful(value):
            safe[key] = value

    return safe, protected


def derived_lock_message(date: Any, protected: Optional[list] = None,
                         kept: int = 0) -> str:
    """Satu kalimat yang menjelaskan APA yang terjadi & APA jalan keluarnya."""
    what = ", ".join(dict.fromkeys(protected or [])) or "Omzet, Jumlah pesanan"
    msg = (f"Angka omzet & jumlah pesanan {norm_date(date)} DITURUNKAN dari pesanan "
           f"toko ini, jadi kolom dari berkas ({what}) TIDAK dipakai.")
    if kept:
        msg += f" {kept} kolom lain yang bukan turunan tetap disimpan."
    msg += (" Kalau angka pesanan memang salah: perbaiki lewat impor Pesanan "
            "Marketplace, atau pakai Override SPV di layar Input Sales "
            "(alasannya akan tercatat).")
    return msg
