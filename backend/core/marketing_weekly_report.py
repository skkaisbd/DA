"""core.marketing_weekly_report — SATU pembuat isi **Laporan Rapat Mingguan**.

KENAPA BERKAS INI ADA
---------------------
Laporan rapat dipakai untuk mengambil keputusan uang: menaikkan/menurunkan iklan,
mengejar toko yang tertinggal, dan menilai host/kreator. Kalau perhitungannya
disalin di layar, di PDF, dan di Excel, suatu hari ketiganya akan menyebut tiga
angka berbeda untuk minggu yang sama — dan yang dibacakan di rapat biasanya yang
kebetulan terbuka. Karena itu: **hanya berkas ini** yang menghitung; layar, PDF,
dan Excel semuanya menerima hasilnya apa adanya.

SUMBER ANGKA (semuanya turunan, tidak ada yang diketik untuk rapat)
-------------------------------------------------------------------
* omzet, pesanan, pcs, pembeli, pecahan kanal, pemenuhan  → `marketing_sales_data`
  (rekap harian turunan F2, dibaca lewat `core.marketing_sales_shape`)
* target bulanan                                          → `marketing_account_targets`
* belanja iklan & klik                                    → `marketing_ads_data`
* pesanan mentah (untuk hitung batal/retur & belum kirim) → `marketing_orders`

KEJUJURAN DATA — bagian yang paling penting
-------------------------------------------
Laporan ini WAJIB memuat `catatan_data`: hari yang belum ada datanya, angka yang
diganti SPV (override), toko tanpa target, iklan yang belum diimpor (⇒ ROAS tidak
bisa dihitung, BUKAN 0), dan kenyataan bahwa omzet ini **sebelum potongan
platform**. Laporan yang tidak menyebut lubangnya sendiri akan dipakai seolah
lengkap, dan itu jauh lebih mahal daripada laporan yang mengaku belum lengkap.

Minggu = **Senin–Minggu** (kesepakatan owner 2026-08-12).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core import marketing_sales_shape as _shape
from core import marketing_daily_rollup as _rollup
from core import marketing_returns as _ret

DAILY = "marketing_sales_data"
ORDERS = "marketing_orders"
ACCOUNTS = "marketing_platform_accounts"
TARGETS = "marketing_account_targets"
ADS = "marketing_ads_data"

# Kanal trafik yang dilaporkan (urutan = urutan tampil di layar/PDF)
TRAFFIC_KEYS = ("live", "video", "product_card", "ads", "affiliate",
                "campaign", "search", "organic", "other")
TRAFFIC_LABEL = {
    "live": "Live", "video": "Video", "product_card": "Kartu Produk",
    "ads": "Iklan", "affiliate": "Afiliasi", "campaign": "Kampanye",
    "search": "Pencarian", "organic": "Organik", "other": "Lainnya",
}
_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
          "Agustus", "September", "Oktober", "November", "Desember"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def monday_of(value: Any = None) -> date:
    """Tanggal apa pun → **Senin** minggu itu (default: minggu berjalan)."""
    if value is None:
        d = _now().date()
    elif isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        s = str(value)[:10]
        try:
            d = datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("week_start harus format YYYY-MM-DD") from exc
    return d - timedelta(days=d.weekday())


def week_dates(start: date) -> List[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range(7)]


def week_label(start: date) -> str:
    end = start + timedelta(days=6)
    if start.month == end.month:
        return (f"{start.day}–{end.day} {_BULAN[end.month - 1]} {end.year}")
    if start.year == end.year:
        return (f"{start.day} {_BULAN[start.month - 1]} – "
                f"{end.day} {_BULAN[end.month - 1]} {end.year}")
    return (f"{start.day} {_BULAN[start.month - 1]} {start.year} – "
            f"{end.day} {_BULAN[end.month - 1]} {end.year}")


def iso_week(start: date) -> str:
    y, w, _ = start.isocalendar()
    return f"{y}-W{w:02d}"


def _delta(now_v: float, prev_v: float) -> Dict[str, Any]:
    """Selisih + persen. `pct=None` kalau pembanding 0 (bukan 0% — tidak terdefinisi)."""
    diff = round(now_v - prev_v)
    pct = round((now_v - prev_v) / prev_v * 100, 1) if prev_v else None
    return {"nilai": diff, "persen": pct, "pembanding": round(prev_v)}


async def _sales_rows(db, account_id: str, dates: List[str]) -> List[dict]:
    return await db[DAILY].find(
        {"account_id": account_id, "date": {"$in": dates}, "revenue_type": "total"},
        {"_id": 0},
    ).sort("date", 1).to_list(60)


def _sum_metrics(rows: List[dict]) -> Dict[str, float]:
    out = {"revenue": 0.0, "revenue_product": 0.0, "orders": 0.0, "units": 0.0,
           "buyers": 0.0, "seller_discount": 0.0, "gross_before_discount": 0.0}
    for r in rows:
        m = _shape.read_metrics(r)
        for k in out:
            out[k] += _num(m.get(k))
    return out


def _sum_traffic(rows: List[dict]) -> Dict[str, float]:
    out = {k: 0.0 for k in TRAFFIC_KEYS}
    for r in rows:
        t = _shape.read_group(r, "traffic")
        for k in out:
            out[k] += _num(t.get(k))
    return out


def _avg_fulfillment(rows: List[dict]) -> Dict[str, Optional[float]]:
    """Rata-rata tertimbang jumlah pesanan (bukan rata-rata sederhana per hari:
    hari dengan 3 pesanan tidak boleh setara dengan hari 300 pesanan)."""
    tot_orders = 0.0
    acc = {"fulfillment_rate": 0.0, "cancellation_rate": 0.0, "return_rate": 0.0,
           "late_shipment_rate": 0.0}
    seen = {k: False for k in acc}
    for r in rows:
        o = _num(_shape.read_metrics(r).get("orders"))
        f = _shape.read_group(r, "fulfillment")
        if o <= 0:
            continue
        tot_orders += o
        for k in acc:
            if f.get(k) not in (None, ""):
                acc[k] += _num(f.get(k)) * o
                seen[k] = True
    if tot_orders <= 0:
        return {k: None for k in acc}
    return {k: (round(acc[k] / tot_orders, 2) if seen[k] else None) for k in acc}


async def _ads(db, account_id: str, dates: List[str]) -> Dict[str, Any]:
    """Belanja iklan minggu itu. `terisi=False` ⇒ ROAS TIDAK dihitung (bukan 0)."""
    start = datetime.strptime(dates[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    rows = await db[ADS].find(
        {"account_id": account_id,
         "$or": [{"date": {"$gte": start, "$lt": end}},
                 {"date": {"$in": dates}}]},
        {"_id": 0}).to_list(2000)
    spend = sum(_num(r.get("spend")) for r in rows)
    clicks = sum(_num(r.get("clicks")) for r in rows)
    impressions = sum(_num(r.get("impressions")) for r in rows)
    return {"terisi": bool(rows), "kampanye": len({r.get("campaign_name") for r in rows}),
            "spend": round(spend), "clicks": round(clicks),
            "impressions": round(impressions), "baris": len(rows)}


async def _orders_side(db, account_id: str, dates: List[str]) -> Dict[str, Any]:
    """Angka yang HANYA ada di pesanan mentah: batal, retur, belum dikirim.

    SESI #9 — dua perbaikan yang bersifat UANG:
      · nilai dibaca lewat pembaca KANONIK (`core.marketing_daily_rollup`), bukan
        `revenue_product` dengan cadangan `revenue` yang dibaca langsung dari
        dokumen. Pembaca lama memberi **Rp 0** untuk pesanan yang diinput staf
        lewat layar (dokumen manual tidak punya `revenue_product`), sehingga
        "nilai retur" mingguan bisa nol padahal barangnya kembali;
      · retur dipisah dengan kalkulator retur tunggal (`core.marketing_returns`)
        supaya laporan mingguan, siklus bulanan, dan scorecard memberi angka retur
        yang SAMA untuk rentang yang sama.
    """
    start = datetime.strptime(dates[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    rows = await db[ORDERS].find(
        {"account_id": account_id, "order_date": {"$gte": start, "$lt": end}},
        {"_id": 0}).to_list(50000)
    batal = [r for r in rows if (r.get("status") or "").lower() == "cancelled"]
    belum = [r for r in rows
             if (r.get("status") or "").lower() in ("new", "paid", "packed")
             and not r.get("shipped_at")]
    split = _ret.split_from_orders(rows)
    val = lambda rs: round(sum(_rollup.order_revenue_product(r) for r in rs))  # noqa: E731
    return {"pesanan_dibaca": len(rows),
            "batal": len(batal), "nilai_batal": val(batal),
            "retur": split["returned_orders"], "nilai_retur": round(split["returned_revenue_product"]),
            "pcs_retur": split["returned_units"],
            "omzet_bruto": round(split["gross_revenue_product"]),
            "omzet_setelah_retur": round(split["net_revenue_product"]),
            "belum_dikirim": len(belum), "nilai_belum_dikirim": val(belum)}


async def _target_prorata(db, account_id: str, dates: List[str]) -> Dict[str, Any]:
    """Target bulanan → porsi minggu ini (**prorata jumlah hari**, diberi label).

    Minggu bisa memotong dua bulan; porsinya dihitung per bulan lalu dijumlah.
    Kalau salah satu bulannya belum punya target, itu DILAPORKAN (`lengkap=False`)
    supaya rapat tidak membandingkan realisasi dengan target setengah.
    """
    per_month: Dict[tuple, int] = {}
    for d in dates:
        dt = datetime.strptime(d, "%Y-%m-%d").date()
        per_month[(dt.year, dt.month)] = per_month.get((dt.year, dt.month), 0) + 1
    rev = ord_ = 0.0
    lengkap = True
    bulan_tanpa_target = []
    for (y, m), days in per_month.items():
        tgt = await db[TARGETS].find_one({"account_id": account_id, "year": y, "month": m},
                                         {"_id": 0})
        if not tgt:
            lengkap = False
            bulan_tanpa_target.append(f"{_BULAN[m - 1]} {y}")
            continue
        dim = calendar.monthrange(y, m)[1]
        rev += _num(tgt.get("revenue_target")) * days / dim
        ord_ += _num(tgt.get("orders_target")) * days / dim
    return {"revenue": round(rev), "orders": round(ord_), "lengkap": lengkap,
            "bulan_tanpa_target": bulan_tanpa_target, "dasar": "prorata jumlah hari"}


async def build_weekly_report(db, week_start: Any = None,
                              account_id: Optional[str] = None,
                              account_ids: Optional[List[str]] = None) -> dict:
    """Bangun seluruh isi laporan mingguan (per toko + gabungan + catatan data).

    ``account_ids`` (sesi #9, F6) = daftar toko yang boleh dilihat pemakai
    (``None`` = semua). Tanpa parameter ini, staf yang memegang satu toko melihat
    angka SEMBILAN toko di laporan rapat — termasuk omzet & biaya toko rekannya.
    """
    start = monday_of(week_start)
    dates = week_dates(start)
    prev_start = start - timedelta(days=7)
    prev_dates = week_dates(prev_start)

    q: Dict[str, Any] = {"id": account_id} if account_id else {}
    if account_ids is not None:
        q["id"] = {"$in": ([account_id] if account_id and account_id in account_ids
                           else ([] if account_id else account_ids))}
    accounts = await db[ACCOUNTS].find(q, {"_id": 0}).sort("account_code", 1).to_list(200)
    accounts = [a for a in accounts if (a.get("status") or "active") == "active"
                or account_id]

    per_store: List[dict] = []
    for acc in accounts:
        rows = await _sales_rows(db, acc["id"], dates)
        prev_rows = await _sales_rows(db, acc["id"], prev_dates)
        cur = _sum_metrics(rows)
        prev = _sum_metrics(prev_rows)
        traffic = _sum_traffic(rows)
        ful = _avg_fulfillment(rows)
        ads = await _ads(db, acc["id"], dates)
        osd = await _orders_side(db, acc["id"], dates)
        tgt = await _target_prorata(db, acc["id"], dates)

        hari_berdata = sorted({r["date"] for r in rows})
        sumber = sorted({(r.get("source") or "?") for r in rows})
        override_dates = sorted({r["date"] for r in rows
                                 if (r.get("source") or "") == _shape.SOURCE_MANUAL_OVERRIDE})
        rev = cur["revenue"]
        roas = round(rev / ads["spend"], 2) if ads["terisi"] and ads["spend"] else None

        per_store.append({
            "account_id": acc["id"],
            "account_code": acc.get("account_code") or "",
            "account_name": acc.get("account_name") or acc.get("name") or "",
            "platform": acc.get("platform") or "",
            "pic": acc.get("pic_name") or "",
            "omzet": round(rev),
            "omzet_produk": round(cur["revenue_product"]),
            "pesanan": int(cur["orders"]),
            "pcs": int(cur["units"]),
            "pembeli": int(cur["buyers"]),
            "aov": round(rev / cur["orders"]) if cur["orders"] else 0,
            "diskon_penjual": round(cur["seller_discount"]),
            # SESI #9 — dua angka omzet berdampingan. `omzet` TETAP bruto (dipakai
            # target, ROAS, dan pembanding minggu lalu); `omzet_setelah_retur`
            # angka baru untuk analisis.
            "nilai_retur": osd["nilai_retur"],
            "pcs_retur": osd["pcs_retur"],
            "omzet_setelah_retur": max(round(rev) - osd["nilai_retur"], 0),
            "retur_persen": (round(osd["nilai_retur"] / rev * 100, 1) if rev else 0.0),
            "vs_minggu_lalu": {
                "omzet": _delta(rev, prev["revenue"]),
                "pesanan": _delta(cur["orders"], prev["orders"]),
            },
            "target": tgt,
            "pencapaian_target_persen": (round(rev / tgt["revenue"] * 100, 1)
                                         if tgt["revenue"] else None),
            "kanal": {k: round(v) for k, v in traffic.items()},
            "kanal_persen": ({k: (round(v / sum(traffic.values()) * 100, 1)
                                  if sum(traffic.values()) else 0)
                              for k, v in traffic.items()}
                             if sum(traffic.values()) else {k: 0 for k in traffic}),
            "pemenuhan": ful,
            "pesanan_mentah": osd,
            "iklan": {**ads, "roas": roas},
            "hari_berdata": len(hari_berdata),
            "tanggal_berdata": hari_berdata,
            "sumber_angka": sumber,
            "tanggal_override_spv": override_dates,
        })

    def _tot(key: str) -> float:
        return sum(_num(s[key]) for s in per_store)

    tot_rev = _tot("omzet")
    tot_ord = _tot("pesanan")
    prev_rev = sum(s["vs_minggu_lalu"]["omzet"]["pembanding"] for s in per_store)
    prev_ord = sum(s["vs_minggu_lalu"]["pesanan"]["pembanding"] for s in per_store)
    tot_spend = sum(_num(s["iklan"]["spend"]) for s in per_store)
    ads_any = any(s["iklan"]["terisi"] for s in per_store)
    tot_tgt_rev = sum(_num(s["target"]["revenue"]) for s in per_store)
    kanal_tot = {k: sum(_num(s["kanal"].get(k)) for s in per_store) for k in TRAFFIC_KEYS}
    kanal_sum = sum(kanal_tot.values())

    gabungan = {
        "toko": len(per_store),
        "toko_berdata": sum(1 for s in per_store if s["hari_berdata"] > 0),
        "omzet": round(tot_rev),
        "pesanan": int(tot_ord),
        "pcs": int(_tot("pcs")),
        "aov": round(tot_rev / tot_ord) if tot_ord else 0,
        "vs_minggu_lalu": {"omzet": _delta(tot_rev, prev_rev),
                           "pesanan": _delta(tot_ord, prev_ord)},
        "target_prorata": round(tot_tgt_rev),
        "pencapaian_target_persen": (round(tot_rev / tot_tgt_rev * 100, 1)
                                     if tot_tgt_rev else None),
        "iklan_spend": round(tot_spend),
        "roas": (round(tot_rev / tot_spend, 2) if ads_any and tot_spend else None),
        "kanal": {k: round(v) for k, v in kanal_tot.items()},
        "kanal_persen": ({k: round(v / kanal_sum * 100, 1) for k, v in kanal_tot.items()}
                         if kanal_sum else {k: 0 for k in kanal_tot}),
        "batal": sum(s["pesanan_mentah"]["batal"] for s in per_store),
        "retur": sum(s["pesanan_mentah"]["retur"] for s in per_store),
        "nilai_retur": sum(s["nilai_retur"] for s in per_store),
        "omzet_setelah_retur": max(round(tot_rev) - sum(s["nilai_retur"] for s in per_store), 0),
        "belum_dikirim": sum(s["pesanan_mentah"]["belum_dikirim"] for s in per_store),
        "nilai_belum_dikirim": sum(s["pesanan_mentah"]["nilai_belum_dikirim"]
                                   for s in per_store),
    }

    # ── CATATAN KEJUJURAN DATA ────────────────────────────────────────────────
    notes: List[str] = [
        "Omzet di laporan ini adalah angka PERFORMA **sebelum potongan platform** "
        "(komisi, biaya layanan, ongkir yang ditanggung). Uang yang benar-benar "
        "masuk rekening hanya bisa dipastikan dari laporan Pencairan/Settlement.",
    ]
    kosong = [s["account_name"] for s in per_store if s["hari_berdata"] == 0]
    if kosong:
        notes.append(f"{len(kosong)} toko TIDAK punya data sama sekali minggu ini "
                     f"({', '.join(kosong[:6])}{'…' if len(kosong) > 6 else ''}) — "
                     f"angka gabungan di atas belum memuat toko-toko itu.")
    kurang = [(s["account_name"], s["hari_berdata"]) for s in per_store
              if 0 < s["hari_berdata"] < 7]
    if kurang:
        notes.append("Data belum penuh 7 hari: "
                     + ", ".join(f"{n} ({d}/7 hari)" for n, d in kurang[:8])
                     + " — pertumbuhan vs minggu lalu bisa menyesatkan.")
    ovr = [(s["account_name"], s["tanggal_override_spv"]) for s in per_store
           if s["tanggal_override_spv"]]
    if ovr:
        notes.append("Angka DIGANTI SPV (override, bukan turunan pesanan): "
                     + "; ".join(f"{n}: {', '.join(d)}" for n, d in ovr))
    no_tgt = [s["account_name"] for s in per_store if not s["target"]["lengkap"]]
    if no_tgt:
        notes.append(f"{len(no_tgt)} toko belum punya target bulan ini "
                     f"({', '.join(no_tgt[:6])}{'…' if len(no_tgt) > 6 else ''}) — "
                     f"kolom pencapaian target kosong, bukan 0%.")
    no_ads = [s["account_name"] for s in per_store if not s["iklan"]["terisi"]]
    if no_ads:
        notes.append(f"Belanja iklan belum diimpor untuk {len(no_ads)} toko ⇒ "
                     f"ROAS-nya TIDAK dihitung (bukan 0). Impor 'Biaya & Performa "
                     f"Iklan' di menu Impor Data.")
    if gabungan["batal"] == 0 and gabungan["retur"] == 0:
        notes.append("BATAL & RETUR terbaca 0 karena ekspor pesanan yang dipakai "
                     "('Untuk Dikirim') tidak memuat pesanan batal/retur. Jangan "
                     "disimpulkan sebagai 'tidak ada pembatalan'.")
    else:
        notes.append(f"Omzet BRUTO Rp {_ret.rp(gabungan['omzet'])} memasukkan "
                     f"{gabungan['retur']} pesanan RETUR senilai Rp "
                     f"{_ret.rp(gabungan['nilai_retur'])}; omzet setelah retur Rp "
                     f"{_ret.rp(gabungan['omzet_setelah_retur'])}. Target, ROAS, dan "
                     "pembanding minggu lalu tetap memakai BRUTO.")
    if gabungan["belum_dikirim"]:
        notes.append(f"{gabungan['belum_dikirim']} pesanan minggu ini masih BELUM "
                     f"DIKIRIM (nilai Rp "
                     f"{gabungan['nilai_belum_dikirim']:,}".replace(",", ".")
                     + ") — lihat menu Monitoring Pengiriman untuk daftar prioritasnya.")

    return {
        "periode": {
            "minggu": iso_week(start),
            "label": week_label(start),
            "mulai": start.isoformat(),
            "selesai": (start + timedelta(days=6)).isoformat(),
            "hari": [{"tanggal": d, "nama": _HARI[i]} for i, d in enumerate(dates)],
            "minggu_sebelumnya": {"mulai": prev_start.isoformat(),
                                  "label": week_label(prev_start)},
            "dasar_minggu": "Senin–Minggu",
        },
        "lingkup": {"account_id": account_id, "semua_toko": account_id is None},
        "gabungan": gabungan,
        "per_toko": per_store,
        "catatan_data": notes,
        "dibuat_pada": _now().isoformat(),
    }
