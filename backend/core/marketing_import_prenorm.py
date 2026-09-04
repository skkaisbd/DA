"""core.marketing_import_prenorm — **penormal berkas ekspor Seller Center**.

KENAPA BERKAS INI ADA (F7.2, 2026-08-13)
----------------------------------------
Mesin impor (`core/marketing_import_engine.parse_table`) menganggap baris pertama
berkas adalah header — asumsi yang benar untuk ekspor pesanan, tetapi **salah untuk
seluruh berkas KPI Shopee**. Diukur pada 5 berkas contoh yang diunggah owner
(13 Agu 2026):

| berkas | bentuk nyata | akibat bila dibaca apa adanya |
|---|---|---|
| `export-sc__1d_*.csv` (Live harian) | baris 0 = **judul grup kolom** (`Data Utama`, `Konversi`…), baris 1 = header sebenarnya | seluruh kolom bernama `Data Utama`/kosong ⇒ 0 kolom terpetakan |
| `overview-v2_*.csv` (Live ringkas) | idem + **blok section** `Kunjungan - Sumber Penonton - …` di bawah baris data | baris section ikut terbaca sebagai data ⇒ angka sampah |
| `video-overview-v3_*.csv` | idem, header duplikat (`Penonton` 2×, `Persentase Klik` 2×) | kolom saling menimpa ⇒ angka tertukar |
| `Data+Keseluruhan+Iklan+Shopee-*.csv` | **6 baris metadata** (Username, Nama Toko, ID Toko, Periode) lalu tabel | header terbaca `Semua Laporan Iklan CPC` ⇒ impor mustahil |
| `*.shopee-shop-stats.*.xlsx` | 12 sheet; ringkasan rentang + rincian per jam + kontribusi kanal | hanya sheet pertama terbaca, tanggal berbentuk rentang `13-08-2026-13-08-2026` |

Karena itu berkas ini **menormalkan dulu**: memotong metadata, memilih baris header
yang benar, membuang baris section, menggabungkan sheet, lalu mengeluarkan tabel
dengan **nama kolom kanonik** (sama dengan `Field.name` di
`core/marketing_import_schema.py`). Setelah itu mesin impor lama bekerja seperti
biasa: coerce tipe, validasi, dedupe, commit, rollback.

ATURAN YANG DIPEGANG
--------------------
1. **Tanpa AI, tanpa tebakan.** Semua pemetaan kolom tertulis di modul ini. Header
   yang tidak dikenal dibiarkan (tidak dipetakan) — tidak pernah "dipaksa cocok".
2. **Header duplikat: dipakai yang PERTAMA.** Pada ekspor Shopee, blok pertama
   (`Kunjungan - Performa`) adalah angka utuh, blok berikutnya adalah rincian
   sumber penonton/alur konversi. Mengambil yang terakhir berarti melaporkan
   sebagian sebagai keseluruhan.
3. **Rentang tanggal tidak pernah dijadikan satu tanggal.** Kalau ekspor mencakup
   >1 hari, angka harian diambil dari baris RINCIAN per hari; kalau rincian yang
   tersedia hanya per JAM (ekspor 1 hari), pengunjung/klik diambil dari baris
   RINGKASAN — menjumlah pengunjung per jam menghitung orang yang sama berulang.
4. **GMV KPI bukan omzet pesanan.** Berkas ini tidak pernah menulis ke
   `marketing_sales_data`; hasilnya masuk `marketing_platform_kpi_daily`
   (KPI platform) atau `marketing_ads_data` (biaya iklan).
"""
from __future__ import annotations

import csv
import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_ROWS = 20000

# ═══════════════════════════════════════════════════════════════════════════════
# Pembantu
# ═══════════════════════════════════════════════════════════════════════════════
def _norm(s: Any) -> str:
    """Normalkan nama kolom: huruf kecil, tanpa tanda baca, spasi tunggal."""
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").strip().lower()).strip()


def _cells(raw: bytes) -> List[List[str]]:
    """CSV apa pun → matriks teks (delimiter dideteksi, BOM dibuang)."""
    text = raw.decode("utf-8-sig", errors="replace")
    sample = text[:4000]
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except Exception:  # noqa: BLE001 — berkas 1 kolom / campur; jatuh ke heuristik
        delim = ";" if sample.count(";") > sample.count(",") else ","
    out: List[List[str]] = []
    for row in csv.reader(io.StringIO(text), delimiter=delim):
        out.append([("" if c is None else str(c).strip()) for c in row])
        if len(out) > MAX_ROWS:
            break
    return out


def _blank(row: List[str]) -> bool:
    return all((c or "").strip() == "" for c in row)


_DUR_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([a-z:]+)", re.I)


def duration_seconds(raw: Any) -> Optional[float]:
    """Durasi gaya Shopee → detik.

    Bentuk nyata pada berkas contoh: ``"10j50m8d"`` (10 jam 50 menit 8 detik),
    ``"54d"``, ``"5d"``, dan ``"00:01:19"`` (hh:mm:ss). Tanpa pembaca ini,
    "durasi tonton" tersimpan sebagai teks dan tidak pernah bisa dijumlah.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ("", "-"):
        return None
    if ":" in s:
        parts = [p.strip() for p in s.split(":")]
        try:
            nums = [float(p.replace(",", ".")) for p in parts]
        except ValueError:
            return None
        while len(nums) < 3:
            nums.insert(0, 0.0)
        return nums[-3] * 3600 + nums[-2] * 60 + nums[-1]
    total = 0.0
    found = False
    for num, unit in _DUR_RE.findall(s):
        try:
            v = float(num.replace(",", "."))
        except ValueError:
            continue
        u = unit.lower()
        mult = {"j": 3600, "h": 3600, "jam": 3600,
                "m": 60, "menit": 60, "min": 60,
                "d": 1, "s": 1, "detik": 1, "sec": 1}.get(u)
        if mult is None:
            continue
        total += v * mult
        found = True
    return total if found else None


def _date_head(raw: Any) -> Optional[str]:
    """Ambil tanggal (YYYY-MM-DD) dari sel seperti ``13-08-2026``,
    ``13-08-2026 01:00``, ``13-08-2026-13-08-2026`` (rentang), atau ``13/08/2026``."""
    s = str(raw or "").strip()
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def _date_range(raw: Any) -> Tuple[Optional[str], Optional[str]]:
    """``13-08-2026-13-08-2026`` / ``07/08/2026 - 13/08/2026`` → (mulai, selesai)."""
    s = str(raw or "").strip()
    hits = re.findall(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)
    if not hits:
        iso = re.findall(r"(\d{4})-(\d{2})-(\d{2})", s)
        if iso:
            vals = [f"{a}-{b}-{c}" for a, b, c in iso]
            return vals[0], vals[-1]
        return None, None
    vals = [f"{int(y):04d}-{int(mo):02d}-{int(d):02d}" for d, mo, y in hits]
    return vals[0], vals[-1]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. KPI KONTEN SHOPEE (Live harian · Live ringkas · Video ringkas)
# ═══════════════════════════════════════════════════════════════════════════════
# Peta kolom DITULIS, bukan ditebak. Kunci = header apa adanya (dinormalkan),
# nilai = nama field kanonik di `marketing_import_schema`.
_CONTENT_MAP: Dict[str, str] = {
    "periode data": "date",
    "user id": "platform_user_id",
    "penjualan pesanan dibuat": "gmv_created",
    "penjualan pesanan siap dikirim": "gmv_ready",
    "pesanan pesanan dibuat": "orders_created",
    "pesanan pesanan siap dikirim": "orders_ready",
    "produk terjual pesanan dibuat": "products_sold",
    "pembeli pesanan dibuat": "buyers",
    "tambah ke keranjang": "add_to_cart",
    "persentase klik": "ctr",
    "suka": "likes",
    "share": "shares",
    "komentar": "comments",
    "pengikut baru dari livestream": "new_followers",
    "pengikut baru dari video": "new_followers",
    # ── Live ────────────────────────────────────────────────────────────────
    "jumlah livestream": "live_sessions",
    "jumlah durasi livestream": "live_duration_raw",
    "penonton": "viewers",
    "penonton aktif": "active_viewers",
    "dilihat": "views",
    "penonton tertinggi": "peak_viewers",
    "rata rata durasi ditonton": "avg_watch_raw",
    # ── Video ───────────────────────────────────────────────────────────────
    "durasi rata rata menonton jumlah video": "avg_watch_raw",
    "ditonton": "views",
    "penonton efektif menonton 3 detik": "effective_viewers",
    "video dengan produk": "videos_with_product",
    "tingkat video selesai ditonton": "completion_rate",
    # ── Voucher / promosi (dibawa apa adanya untuk jejak) ────────────────────
    "voucher toko diklaim": "voucher_shop_claimed",
    "voucher spesial live diklaim": "voucher_live_claimed",
    "koin diklaim": "coin_claimed",
}

_VIDEO_MARKERS = ("video dengan produk", "pengikut baru dari video",
                  "rasio video ditonton", "durasi rata rata menonton jumlah video",
                  "video berpendapatan pesanan dibuat")
_LIVE_MARKERS = ("jumlah livestream", "pengikut baru dari livestream",
                 "rasio live ditonton", "penonton tertinggi", "penonton aktif")


def _header_row_index(cells: List[List[str]], must_have: str,
                      also: str = "", limit: int = 12) -> int:
    """Cari baris header SEBENARNYA.

    Ekspor Shopee menaruh **judul grup kolom** di baris 0 (`Periode Data`, `Data
    Utama`, `Konversi`…) dan header sebenarnya di baris 1. Kalau kita berhenti di
    kecocokan pertama, seluruh kolom terbaca dari baris judul grup dan tidak ada
    satu pun kolom yang terpetakan. Karena itu baris header dipilih yang memuat
    **dua** penanda sekaligus (mis. `Periode Data` + `User Id`).
    """
    if also:
        for i, row in enumerate(cells[:limit]):
            hn = [_norm(c) for c in row]
            if must_have in hn and also in hn:
                return i
    for i, row in enumerate(cells[:limit]):
        if any(_norm(c) == must_have for c in row):
            return i
    return -1


def _detect_channel(headers_norm: List[str], filename: str) -> Tuple[str, str]:
    """→ (channel, source). Diputuskan dari HEADER, bukan dari nama berkas.

    Nama berkas boleh diubah staf (dan pasti diubah saat diunduh berulang), jadi
    ia bukan bukti apa pun. Yang membedakan kedua ekspor Live: ekspor RINGKAS
    (`overview`) membawa kolom `Jumlah Livestream` & `Jumlah Durasi Livestream`,
    sedangkan ekspor HARIAN (`export-sc`, banyak tanggal) tidak.
    """
    hset = set(headers_norm)
    if hset & set(_VIDEO_MARKERS):
        return "video", "shopee_video_overview"
    if hset & set(_LIVE_MARKERS):
        src = ("shopee_live_overview" if "jumlah livestream" in hset
               else "shopee_live_1d")
        return "live", src
    raise ValueError(
        "Berkas ini tidak dikenali sebagai KPI Live maupun Video Shopee "
        "(tidak ada kolom penanda seperti 'Jumlah Livestream', 'Penonton Aktif', "
        "atau 'Video dengan Produk'). Pastikan berkas diekspor dari Seller Center → "
        "Bisnis Saya → Live/Video, tanpa diubah kolomnya.")


def prenorm_shopee_content_kpi(raw: bytes, filename: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Ekspor Live/Video Shopee (CSV) → tabel KPI harian per kanal."""
    cells = _cells(raw)
    hidx = _header_row_index(cells, "periode data", also="user id")
    if hidx < 0:
        raise ValueError(
            "Kolom 'Periode Data' tidak ditemukan di 12 baris pertama. Berkas KPI "
            "Live/Video Shopee selalu memuatnya — sepertinya ini berkas jenis lain.")
    header = cells[hidx]
    hnorm = [_norm(c) for c in header]
    channel, source = _detect_channel(hnorm, filename)

    # header duplikat: dipakai yang PERTAMA (lihat aturan #2 di docstring)
    col_of: Dict[str, int] = {}
    for i, hn in enumerate(hnorm):
        canon = _CONTENT_MAP.get(hn)
        if canon and canon not in col_of:
            col_of[canon] = i

    rows: List[Dict[str, Any]] = []
    for row in cells[hidx + 1:]:
        if _blank(row):
            break                      # blok section di bawahnya bukan data harian
        d = _date_head(row[0] if row else "")
        if not d:
            break                      # baris judul section ("Kunjungan - Sumber …")
        rec: Dict[str, Any] = {"date": d, "channel": channel, "source": source}
        for canon, idx in col_of.items():
            if canon == "date":
                continue
            rec[canon] = row[idx] if idx < len(row) else ""
        # durasi teks → detik/menit (angka yang bisa dijumlah)
        secs = duration_seconds(rec.pop("avg_watch_raw", None))
        if secs is not None:
            rec["avg_watch_seconds"] = secs
        live_secs = duration_seconds(rec.pop("live_duration_raw", None))
        if live_secs is not None:
            rec["live_minutes"] = round(live_secs / 60.0, 2)
        rows.append(rec)

    if not rows:
        raise ValueError(
            "Tidak ada baris tanggal yang terbaca. Ekspor Live/Video Shopee harus "
            "memuat minimal satu baris 'Periode Data' berisi tanggal.")
    headers = sorted({k for r in rows for k in r})
    return headers, rows


# ═══════════════════════════════════════════════════════════════════════════════
# 2. STATISTIK TOKO SHOPEE (XLSX multi-sheet)
# ═══════════════════════════════════════════════════════════════════════════════
_BASIS_SHEETS = {
    "pesanan dibuat": "created",
    "pesanan siap dikirim": "ready",
    "pesanan dibayar": "paid",
}
_CHANNEL_SPLIT = {
    "penjualan dari halaman produk": "gmv_product_page",
    "penjualan dari live penjual": "gmv_live",
    "penjualan dari video penjual": "gmv_video",
    "penjualan dari affiliate": "gmv_affiliate",
    "penjualan dari iklan shopee": "gmv_ads",
}


def _sheet_matrix(ws) -> List[List[Any]]:
    out: List[List[Any]] = []
    for values in ws.iter_rows(values_only=True):
        out.append(list(values or []))
        if len(out) > 5000:
            break
    return out


def _rows_after(matrix: List[List[Any]], first_cell: str) -> Tuple[List[str], List[List[Any]]]:
    """Ambil (header, baris) dari blok yang dimulai baris ber-sel-pertama `first_cell`."""
    for i, row in enumerate(matrix):
        if row and _norm(row[0]) == first_cell:
            header = [_norm(c) for c in row]
            body: List[List[Any]] = []
            for r in matrix[i + 1:]:
                if not r or all(c in (None, "") for c in r):
                    break
                body.append(list(r))
            return header, body
    return [], []


def prenorm_shopee_shop_stats(raw: bytes, filename: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """XLSX `*.shopee-shop-stats.*` → satu baris KPI per TANGGAL (kanal `shop`)."""
    try:
        import openpyxl
    except ImportError as e:  # pragma: no cover — dependency inti
        raise ValueError("Server belum punya openpyxl untuk membaca Excel") from e
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    per_date: Dict[str, Dict[str, Any]] = {}
    single_date: Optional[str] = None
    notes: List[str] = []

    def _rec(d: str) -> Dict[str, Any]:
        return per_date.setdefault(d, {"date": d, "channel": "shop",
                                       "source": "shopee_shop_stats"})

    for ws in wb.worksheets:
        title_n = _norm(ws.title)
        basis = _BASIS_SHEETS.get(title_n)
        if not basis:
            continue
        matrix = _sheet_matrix(ws)
        # ── ringkasan (rentang) ────────────────────────────────────────────────
        sum_head, sum_body = _rows_after(matrix, "tanggal")
        rng_from = rng_to = None
        summary: Dict[str, Any] = {}
        if sum_body:
            rng_from, rng_to = _date_range(sum_body[0][0] if sum_body[0] else "")
            summary = {sum_head[i]: sum_body[0][i] if i < len(sum_body[0]) else None
                       for i in range(len(sum_head))}
        # ── rincian (per jam untuk ekspor 1 hari, per hari untuk rentang) ──────
        det_head, det_body = _rows_after(matrix, "waktu")

        if rng_from and rng_to and rng_from == rng_to:
            # Ekspor 1 hari: pengunjung & klik dari RINGKASAN (menjumlah per jam
            # akan menghitung pengunjung yang sama berkali-kali).
            single_date = rng_from
            rec = _rec(rng_from)
            rec[f"gmv_{basis}"] = summary.get("total penjualan idr")
            rec[f"orders_{basis}"] = summary.get("total pesanan")
            rec.setdefault("visitors", summary.get("total pengunjung"))
            rec.setdefault("product_clicks", summary.get("produk diklik"))
            if basis == "created":
                rec["conversion_rate"] = summary.get("tingkat konversi pesanan")
        elif det_body:
            for r in det_body:
                d = _date_head(r[0] if r else "")
                if not d:
                    continue
                rec = _rec(d)
                gm = det_head.index("total penjualan idr") if "total penjualan idr" in det_head else -1
                od = det_head.index("total pesanan") if "total pesanan" in det_head else -1
                vs = det_head.index("total pengunjung") if "total pengunjung" in det_head else -1
                pc = det_head.index("produk diklik") if "produk diklik" in det_head else -1
                if gm >= 0:
                    rec[f"gmv_{basis}"] = r[gm] if gm < len(r) else None
                if od >= 0:
                    rec[f"orders_{basis}"] = r[od] if od < len(r) else None
                if basis == "created":
                    if vs >= 0:
                        rec["visitors"] = r[vs] if vs < len(r) else None
                    if pc >= 0:
                        rec["product_clicks"] = r[pc] if pc < len(r) else None
        else:
            notes.append(f"sheet '{ws.title}' tidak punya blok tanggal/waktu")

    # ── kontribusi kanal (hanya sah bila ekspornya 1 hari) ────────────────────
    for ws in wb.worksheets:
        head, body = _rows_after(_sheet_matrix(ws), "tanggal")
        if not body or not head:
            continue
        if not any(h in _CHANNEL_SPLIT for h in head):
            continue
        row0 = body[0]
        status = str(row0[1] if len(row0) > 1 else "").strip().lower()
        if "dibuat" not in status:          # pakai basis 'Pesanan Dibuat' saja
            continue
        f, t = _date_range(row0[0] if row0 else "")
        if not f or f != t:
            notes.append("kontribusi kanal dilewati: ekspor mencakup lebih dari 1 hari")
            break
        rec = _rec(f)
        for i, h in enumerate(head):
            canon = _CHANNEL_SPLIT.get(h)
            if canon and i < len(row0):
                rec[canon] = row0[i]
        break

    try:
        wb.close()
    except Exception as e:  # noqa: BLE001
        logger.debug("gagal menutup workbook statistik toko: %s", e)

    if not per_date:
        raise ValueError(
            "Tidak ada sheet 'Pesanan Dibuat' / 'Pesanan Siap Dikirim' / "
            "'Pesanan Dibayar' yang bisa dibaca. Unggah berkas asli ekspor "
            "Seller Center → Data Bisnis → Statistik Toko (.xlsx), tanpa diedit.")
    rows = [per_date[k] for k in sorted(per_date)]
    if notes:
        logger.info("[prenorm shop_stats] %s (tanggal tunggal=%s)",
                    "; ".join(notes), single_date)
    headers = sorted({k for r in rows for k in r})
    return headers, rows


# ═══════════════════════════════════════════════════════════════════════════════
# 3. LAPORAN IKLAN CPC SHOPEE
# ═══════════════════════════════════════════════════════════════════════════════
_ADS_MAP: Dict[str, str] = {
    "nama iklan": "campaign_name",
    "status": "status",
    "jenis iklan": "ad_type",
    "kode produk": "product_code",
    "mode bidding": "bidding_mode",
    "penempatan iklan": "placement",
    "tanggal mulai": "campaign_started",
    "dilihat": "impressions",
    "jumlah klik": "clicks",
    "persentase klik": "ctr_platform",
    "tambah ke keranjang": "add_to_cart",
    "konversi": "conversions",
    "konversi langsung": "direct_conversions",
    "produk terjual": "products_sold",
    "terjual langsung": "direct_products_sold",
    "omzet penjualan": "revenue",
    "penjualan langsung gmv langsung": "direct_revenue",
    "biaya": "spend",
    "efektifitas iklan": "roas_platform",
    "efektivitas langsung": "direct_roas_platform",
    "persentase biaya iklan terhadap penjualan dari iklan acos": "acos",
}
_ADS_META = {
    "username": "shop_username",
    "nama toko": "shop_name",
    "id toko": "platform_shop_id",
    "periode": "_period",
}


def prenorm_shopee_ads_cpc(raw: bytes, filename: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """CSV `Data Keseluruhan Iklan Shopee` → satu baris per iklan + periode."""
    cells = _cells(raw)
    meta: Dict[str, Any] = {}
    hidx = -1
    for i, row in enumerate(cells[:30]):
        if not row:
            continue
        key = _norm(row[0])
        if key in _ADS_META and len(row) > 1:
            meta[_ADS_META[key]] = row[1].strip()
        if any(_norm(c) == "nama iklan" for c in row):
            hidx = i
            break
    if hidx < 0:
        raise ValueError(
            "Baris header 'Nama Iklan' tidak ditemukan. Unggah berkas asli "
            "Seller Center → Iklan Saya → Laporan Iklan (Semua Laporan Iklan CPC), "
            "tanpa mengubah baris judulnya.")
    p_from, p_to = _date_range(meta.pop("_period", ""))
    if not p_from or not p_to:
        raise ValueError(
            "Periode laporan tidak terbaca dari baris 'Periode' di kepala berkas. "
            "Tanpa periode, biaya iklan tidak bisa ditempatkan pada bulan yang benar.")
    if p_from[:7] != p_to[:7]:
        raise ValueError(
            f"Laporan ini mencakup dua bulan ({p_from} s/d {p_to}). Biaya iklan "
            "dipakai untuk realisasi anggaran BULANAN, jadi ekspor harus dibatasi "
            "dalam satu bulan — ekspor ulang per bulan lalu unggah masing-masing.")

    header = [_norm(c) for c in cells[hidx]]
    col_of: Dict[str, int] = {}
    for i, hn in enumerate(header):
        canon = _ADS_MAP.get(hn)
        if canon and canon not in col_of:
            col_of[canon] = i

    rows: List[Dict[str, Any]] = []
    for row in cells[hidx + 1:]:
        if _blank(row):
            continue
        name_i = col_of.get("campaign_name")
        if name_i is None or name_i >= len(row) or not row[name_i].strip():
            continue
        rec: Dict[str, Any] = {"date": p_from, "period_start": p_from, "period_end": p_to}
        rec.update(meta)
        for canon, idx in col_of.items():
            v = row[idx] if idx < len(row) else ""
            rec[canon] = "" if str(v).strip() == "-" else v
        rows.append(rec)

    if not rows:
        raise ValueError("Tidak ada baris iklan di bawah header — berkas kosong?")
    headers = sorted({k for r in rows for k in r})
    return headers, rows


# ═══════════════════════════════════════════════════════════════════════════════
# Titik masuk
# ═══════════════════════════════════════════════════════════════════════════════
PRENORMALIZERS = {
    "shopee_content_kpi": prenorm_shopee_content_kpi,
    "shopee_shop_stats": prenorm_shopee_shop_stats,
    "shopee_ads_cpc": prenorm_shopee_ads_cpc,
}


def prenormalize(raw: bytes, filename: str, key: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    fn = PRENORMALIZERS.get(key)
    if fn is None:
        raise ValueError(f"Penormal berkas '{key}' tidak dikenali")
    return fn(raw, filename)
