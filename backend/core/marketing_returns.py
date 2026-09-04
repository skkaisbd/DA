"""core.marketing_returns — **SATU** kalkulator "omzet bruto vs omzet setelah retur".

KENAPA BERKAS INI ADA
---------------------
Sampai sesi #9, pesanan berstatus ``returned`` **ikut dihitung** sebagai omzet:
``EXCLUDED_FOR_REVENUE = ('cancelled',)``. Itu bukan kekeliruan hitung — uangnya
memang pernah masuk — tetapi akibatnya satu pertanyaan pemilik tidak pernah bisa
dijawab dari layar: *"berapa omzet saya SESUDAH barang yang diretur?"*.

**Keputusan pemilik (sesi #9): tampilkan DUA-DUANYA.** Angka lama TIDAK BOLEH
bergeser — semua target, capaian, pace, ROAS, dan lampiran rapat yang sudah
beredar memakai omzet **bruto**. Angka baru (retur & net) DITAMBAHKAN di
sebelahnya, dengan namanya sendiri, supaya tidak ada satu pun angka lama yang
berubah arti diam-diam.

    omzet bruto  = definisi lama (semua status KECUALI `cancelled`)      ← TETAP
    nilai retur  = Σ pesanan berstatus `returned`
    omzet net    = bruto − nilai retur                                   ← BARU

TIGA HAL YANG DIJAGA BERKAS INI
-------------------------------
1. **Satu rumus, satu tempat.** Sebelumnya `returned` dihitung ulang di empat
   tempat (rekap harian, laporan mingguan, scorecard kreator, rincian kreator) —
   dua di antaranya memakai pembaca uang sendiri (`r.get("revenue_product") or
   r.get("revenue")`) yang memberi **Rp 0** untuk pesanan yang diinput staf lewat
   layar. Semua pembaca sekarang memanggil fungsi di sini.
2. **Dua basis uang tidak boleh tertukar.** Toko bisa memakai basis
   ``produk_setelah_diskon`` atau ``order_amount`` (lihat
   ``core.marketing_sales_shape.resolve_basis``). Nilai retur karena itu disimpan
   pada KEDUA basis, dan yang dipakai di layar dipilih sesuai basis toko —
   mengurangi "order amount retur" dari "omzet produk" akan melahirkan net yang
   terlalu kecil tanpa ada yang tahu.
3. **Jujur soal CAKUPAN.** Retur hanya diketahui dari pesanan per baris. Hari yang
   rekapnya DIIMPOR/DIKETIK (platform tanpa ekspor pesanan, atau override SPV)
   tidak membawa informasi retur sama sekali — itu **bukan nol**, itu **belum
   diketahui**. Karena itu setiap ringkasan membawa ``coverage`` dan layar wajib
   menyebutnya; pola yang sama dipakai cakupan HPP pada marjin.

RESERVASI STOK — TIDAK BERUBAH SEDIKIT PUN
------------------------------------------
``core.order_status`` sudah memasukkan ``returned`` ke
``RESERVATION_RELEASING_STATUSES`` + ``TERMINAL_STATUSES``: begitu pesanan
diretur, reservasi stoknya DILEPAS dan statusnya tidak bisa dihidupkan lagi
(termasuk oleh "batalkan impor"). Menampilkan pesanan retur di laporan **tidak**
mengubah itu — berkas ini murni pembaca angka, tidak pernah menulis.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core import marketing_daily_rollup as _rollup
from core import marketing_sales_shape as _shape

# Status "barang kembali". Sengaja tuple (bukan set literal di tempat pemakaian)
# supaya tidak ada daftar kedua yang bisa berbeda.
RETURNED_STATUSES: Tuple[str, ...] = ("returned",)

# Ambang peringatan retur (bisa ditimpa `marketing_alert_settings`).
DEFAULT_RETURN_THRESHOLDS = {
    "returns_warn_pct": 5.0,    # nilai retur / omzet bruto ⇒ kuning
    "returns_red_pct": 10.0,    # ⇒ merah
}

LABEL_GROSS = ("Omzet BRUTO — definisi lama yang dipakai target, capaian, dan "
               "ROAS: semua pesanan KECUALI yang dibatalkan (pesanan retur IKUT).")
LABEL_NET = ("Omzet SETELAH RETUR — bruto dikurangi nilai pesanan berstatus "
             "retur. Angka analisis; target & capaian TIDAK memakainya supaya "
             "angka rapat yang sudah beredar tidak berubah arti.")


def _r(v: Any, nd: int = 2) -> float:
    try:
        return round(float(v or 0), nd)
    except (TypeError, ValueError):
        return 0.0


def _int(v: Any) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def rp(v: Any) -> str:
    """Rupiah gaya Indonesia (ribuan pakai titik).

    Dipakai kalimat catatan/peringatan. **Jangan** memakai
    ``f"{x:,.0f}".replace(",", ".")`` pada seluruh kalimat — itu juga mengubah
    koma prosa menjadi titik (cacat kecil yang membuat kalimat terputus).
    """
    return f"{_r(v):,.0f}".replace(",", ".")


def is_returned(order: dict) -> bool:
    """Apakah satu dokumen pesanan berstatus retur (apa pun kapitalisasinya)."""
    return str((order or {}).get("status") or "").strip().lower() in RETURNED_STATUSES


def order_units(order: dict) -> int:
    """Jumlah pcs satu pesanan — memakai pembaca kanonik item (impor & manual)."""
    q = _int((order or {}).get("quantity"))
    if q:
        return q
    return sum(_rollup.item_qty(it) for it in ((order or {}).get("items") or []))


# ══════════════════════════════════════════════════════════════════════════════
# DARI PESANAN MENTAH  (dipakai rollup harian, scorecard kreator, laporan mingguan)
# ══════════════════════════════════════════════════════════════════════════════
def split_from_orders(orders: Iterable[dict]) -> Dict[str, Any]:
    """Pecah daftar pesanan menjadi bruto · retur · net pada KEDUA basis uang.

    ``orders`` = dokumen `marketing_orders` apa adanya (bentuk impor MAUPUN
    manual — pembacanya defensif lewat `core.marketing_daily_rollup`).

    Kontrak yang dijaga: ``gross_* == net_* + returned_*`` selalu, dan bruto
    memakai filter status yang PERSIS SAMA dengan rekap harian
    (`EXCLUDED_FOR_REVENUE`), jadi angka lama tidak bisa bergeser karena fungsi
    ini dipanggil.
    """
    rows = list(orders or [])
    live = [o for o in rows
            if str(o.get("status") or "").strip().lower()
            not in _rollup.EXCLUDED_FOR_REVENUE]
    ret = [o for o in live if is_returned(o)]

    gross_p = sum(_rollup.order_revenue_product(o) for o in live)
    gross_a = sum(_rollup.order_amount_of(o) for o in live)
    ret_p = sum(_rollup.order_revenue_product(o) for o in ret)
    ret_a = sum(_rollup.order_amount_of(o) for o in ret)
    ret_units = sum(order_units(o) for o in ret)

    return {
        "gross_revenue_product": _r(gross_p),
        "gross_order_amount": _r(gross_a),
        "returned_revenue_product": _r(ret_p),
        "returned_order_amount": _r(ret_a),
        "returned_orders": len(ret),
        "returned_units": ret_units,
        "net_revenue_product": _r(gross_p - ret_p),
        "net_order_amount": _r(gross_a - ret_a),
        "orders_counted": len(live),
    }


# ══════════════════════════════════════════════════════════════════════════════
# DARI REKAP HARIAN  (dipakai siklus F5 — satu bulan bisa ratusan dokumen)
# ══════════════════════════════════════════════════════════════════════════════
def from_daily_rows(rows: Sequence[dict], basis: Optional[str] = None) -> Dict[str, Any]:
    """Ringkas retur satu bulan dari dokumen `marketing_sales_data`.

    Hanya hari yang rekapnya DITURUNKAN dari pesanan (`source` ∈
    :data:`core.marketing_sales_shape.DERIVED_SOURCES`) yang benar-benar tahu
    soal retur. Hari lain dilaporkan sebagai **belum diketahui** — bukan nol.
    """
    basis = basis if basis in _shape.VALID_BASIS else _shape.DEFAULT_BASIS
    ret_p = ret_a = 0.0
    ret_orders = ret_units = 0
    days_known = days_total = 0
    unknown_sources: Dict[str, int] = {}
    for r in rows or []:
        days_total += 1
        src = r.get("source") or "unknown"
        ful = _shape.read_group(r, "fulfillment") if hasattr(_shape, "read_group") else (
            r.get("fulfillment") or {})
        # Dokumen turunan yang lahir SEBELUM sesi #9 tidak punya
        # `returned_revenue_product`. Menganggapnya 0 akan melahirkan net yang
        # SALAH (bruto utuh padahal ada retur), jadi hari itu dinyatakan BELUM
        # DIKETAHUI sampai rekapnya dihitung ulang
        # (`backend/scripts/backfill_returns_daily.py` atau tombol "Hitung Ulang").
        stale = (_int(ful.get("returned_orders")) > 0
                 and float(ful.get("returned_value") or 0) > 0
                 and float(ful.get("returned_revenue_product") or 0) == 0)
        if stale:
            unknown_sources["rekap_turunan_sebelum_sesi9"] = (
                unknown_sources.get("rekap_turunan_sebelum_sesi9", 0) + 1)
            continue
        if src in _shape.DERIVED_SOURCES:
            days_known += 1
            ret_p += float(ful.get("returned_revenue_product") or 0)
            ret_a += float(ful.get("returned_value") or 0)
            ret_orders += _int(ful.get("returned_orders"))
            ret_units += _int(ful.get("returned_units"))
        else:
            # Hari yang angkanya diimpor/diketik/di-override: retur tidak diketahui.
            # Kalau dokumennya kebetulan MEMBAWA angka retur (mis. impor rekap yang
            # kolomnya ada), angkanya tetap dipakai — yang tidak boleh adalah
            # menganggap ketidakhadiran kolom sebagai "nol retur".
            has_any = any(float(ful.get(k) or 0) for k in
                          ("returned_value", "returned_revenue_product", "returned_orders"))
            if has_any:
                days_known += 1
                ret_p += float(ful.get("returned_revenue_product") or 0)
                ret_a += float(ful.get("returned_value") or 0)
                ret_orders += _int(ful.get("returned_orders"))
                ret_units += _int(ful.get("returned_units"))
            else:
                unknown_sources[src] = unknown_sources.get(src, 0) + 1
    return {
        "returned_revenue_product": _r(ret_p),
        "returned_order_amount": _r(ret_a),
        "returned_orders": ret_orders,
        "returned_units": ret_units,
        "basis": basis,
        "coverage": {
            "days_known": days_known,
            "days_total": days_total,
            "coverage_pct": _r(days_known / days_total * 100) if days_total else 0.0,
            "complete": days_total == 0 or days_known == days_total,
            "unknown_sources": unknown_sources,
        },
    }


def resolve(basis: Optional[str], gross_revenue: Any, split: Dict[str, Any]) -> Dict[str, Any]:
    """Pilih angka retur sesuai **basis omzet toko** lalu hitung net + persennya.

    ``gross_revenue`` = angka bruto yang SUDAH dipakai layar (``actual.revenue``)
    supaya net benar-benar "bruto yang itu" dikurangi retur — bukan angka bruto
    kedua yang dihitung ulang di sini.
    """
    basis = basis if basis in _shape.VALID_BASIS else _shape.DEFAULT_BASIS
    gross = _r(gross_revenue)
    returned = _r(split.get("returned_order_amount")
                  if basis == _shape.BASIS_ORDER_AMOUNT
                  else split.get("returned_revenue_product"))
    # Pagar: net tidak pernah negatif. Nilai retur bisa MELEBIHI omzet bulan ini
    # kalau pesanannya dibuat bulan lalu dan diretur bulan ini; itu keadaan nyata,
    # jadi selisihnya dilaporkan (`over_returned`) daripada dibulatkan diam-diam.
    net = _r(gross - returned)
    return {
        "revenue_gross": gross,
        "returned_amount": returned,
        "returned_orders": _int(split.get("returned_orders")),
        "returned_units": _int(split.get("returned_units")),
        "revenue_net_returns": max(net, 0.0),
        "returns_pct": _r(returned / gross * 100) if gross > 0 else 0.0,
        "over_returned": net < 0,
        "basis": basis,
        "coverage": split.get("coverage") or {},
        "label_gross": LABEL_GROSS,
        "label_net": LABEL_NET,
    }


def thresholds_from(settings: Optional[dict]) -> Dict[str, float]:
    out = dict(DEFAULT_RETURN_THRESHOLDS)
    for k in out:
        v = (settings or {}).get(k)
        if v is not None:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                pass
    return out


def evaluate_flags(returns: Dict[str, Any],
                   settings: Optional[dict] = None) -> List[dict]:
    """Peringatan retur — dipakai layar **dan** notifikasi dari satu fungsi."""
    th = thresholds_from(settings)
    pct = _r((returns or {}).get("returns_pct"))
    n = _int((returns or {}).get("returned_orders"))
    flags: List[dict] = []
    if n <= 0:
        return flags
    if pct >= th["returns_red_pct"]:
        sev = "red"
    elif pct >= th["returns_warn_pct"]:
        sev = "yellow"
    else:
        return flags
    flags.append({
        "code": "returns_high", "severity": sev,
        "title": "Nilai retur tinggi",
        "message": (f"{n} pesanan retur senilai Rp {rp(returns.get('returned_amount'))} "
                    f"= {pct}% dari omzet bruto. Omzet setelah retur "
                    f"Rp {rp(returns.get('revenue_net_returns'))}."),
        "value": pct,
        "threshold": th["returns_red_pct"] if sev == "red" else th["returns_warn_pct"],
    })
    return flags


def data_note(returns: Dict[str, Any]) -> str:
    """Satu kalimat kejujuran untuk `data_notes` — SELALU menyebut kata 'retur'."""
    cov = (returns or {}).get("coverage") or {}
    base = (f"Omzet bruto Rp {rp(returns.get('revenue_gross'))} memasukkan "
            f"{_int(returns.get('returned_orders'))} pesanan RETUR senilai "
            f"Rp {rp(returns.get('returned_amount'))}; omzet setelah retur "
            f"Rp {rp(returns.get('revenue_net_returns'))}. Target & capaian "
            "tetap memakai BRUTO supaya angka yang sudah beredar tidak berubah.")
    if not cov.get("complete", True):
        base += (f" Cakupan data retur baru {_r(cov.get('coverage_pct'))}% hari "
                 f"({_int(cov.get('days_known'))} dari {_int(cov.get('days_total'))}): "
                 "hari yang rekapnya diimpor/diketik tidak membawa informasi retur "
                 "— itu BELUM DIKETAHUI, bukan nol.")
    if returns.get("over_returned"):
        base += (" Nilai retur MELEBIHI omzet bulan ini — biasanya karena pesanannya "
                 "dibuat bulan sebelumnya lalu diretur bulan ini.")
    return base
