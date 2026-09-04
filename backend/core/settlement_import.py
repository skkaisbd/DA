"""settlement_import — pembaca laporan pencairan Shopee/TikTok → draf angka form F9.

Aturan BD-2 (pemetaan kolom uang TIDAK BOLEH DITEBAK diam-diam) dipatuhi dengan cara:
  · hasil parse TIDAK disimpan — hanya PRATINJAU untuk mengisi form; staf yang menyimpan;
  · setiap field menyebut KOLOM SUMBER-nya, dan kolom angka yang tidak terpetakan
    DITAMPILKAN, supaya potongan yang belum dikenal tidak hilang tanpa nama.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from core.marketing_import_engine import parse_table, parse_number, parse_date, _norm_header

# field → (kata kunci header yang dikenal). Sumber: laporan "Penghasilan Saya" Shopee
# dan "Settlement / Statement" TikTok Shop. Kolom persentase/estimasi dikecualikan.
FIELD_KEYWORDS: Dict[str, List[str]] = {
    "gross_sales": ["harga asli produk", "total harga produk", "total revenue",
                    "subtotal before discount", "harga produk", "gross sales", "omzet bruto"],
    "refunds": ["pengembalian dana", "refund", "dana dikembalikan"],
    "seller_discount": ["diskon produk", "voucher ditanggung penjual", "seller discount",
                        "diskon penjual", "voucher penjual", "cashback koin ditanggung penjual"],
    "shipping_subsidy": ["subsidi ongkir", "shipping subsidy", "shipping fee subsidy",
                         "ongkir ditanggung platform", "platform shipping"],
    "platform_commission": ["biaya administrasi", "platform commission", "komisi platform",
                            "biaya komisi", "commission fee", "biaya admin"],
    "platform_service_fee": ["biaya layanan", "transaction fee", "service fee",
                             "biaya transaksi", "biaya proses pesanan", "biaya program"],
    "affiliate_commission": ["komisi ams", "affiliate commission", "komisi afiliasi",
                             "komisi affiliate", "ams"],
    "ads_deduction": ["iklan", "ads deduction", "biaya ads", "ads fee"],
    "other_deductions": ["biaya lainnya", "other fee", "potongan lain", "biaya lain",
                         "customer service fee", "other deduction"],
    "adjustments": ["adjustment", "penyesuaian", "kompensasi", "compensation"],
    "net_payout": ["total penghasilan", "total settlement amount", "settlement amount",
                   "jumlah dana dilepaskan", "jumlah pencairan", "net payout", "dana diterima",
                   "total penarikan"],
}
DATE_KEYWORDS = ["tanggal dana dilepaskan", "order settled time", "settlement date",
                 "tanggal pencairan", "statement date", "settled time", "waktu pencairan"]
PERIOD_KEYWORDS = ["waktu pesanan dibuat", "order created time", "tanggal pesanan",
                   "order create", "created time", "waktu pembayaran"]
ID_KEYWORDS = ["statement id", "settlement id", "no penarikan", "id pencairan",
               "nomor penarikan", "batch id", "id statement"]
EXCLUDE_TOKENS = ["persen", "%", "rate", "estimasi", "tarif", "qty", "jumlah produk", "kuantitas"]
ID_TOKENS = {"id", "no", "nomor", "sku", "kode"}
# Urutan cocok: yang lebih SPESIFIK dulu ("komisi AMS" = afiliasi, bukan komisi platform).
FIELD_PRIORITY = ["affiliate_commission", "ads_deduction", "net_payout", "refunds", "seller_discount",
                  "shipping_subsidy", "platform_service_fee", "platform_commission",
                  "other_deductions", "adjustments", "gross_sales"]

MAX_UNMAPPED = 30


def _is_id_column(norm: str) -> bool:
    return bool(ID_TOKENS & set(norm.split()))


def _match(norm: str, keywords: List[str]) -> bool:
    return any(_norm_header(k) in norm for k in keywords)


def _is_numeric_column(rows: List[dict], col: str) -> bool:
    seen = 0
    for r in rows[:50]:
        v = r.get(col)
        if v in (None, ""):
            continue
        seen += 1
        n, _ = parse_number(v)
        if n is None:
            return False
    return seen > 0


def _sum_column(rows: List[dict], col: str) -> float:
    total = 0.0
    for r in rows:
        n, _ = parse_number(r.get(col))
        if n is not None:
            total += n
    return total


def _first_nonempty(rows: List[dict], col: str) -> Optional[str]:
    for r in rows:
        v = r.get(col)
        if v not in (None, ""):
            return str(v).strip()
    return None


def _date_range(rows: List[dict], col: str) -> Tuple[Optional[str], Optional[str]]:
    ds = []
    for r in rows:
        d, _ = parse_date(r.get(col))
        if d:
            ds.append(d.date().isoformat())
    return (min(ds), max(ds)) if ds else (None, None)


def _fingerprint(headers: List[str]) -> str:
    import hashlib
    key = "|".join(sorted(_norm_header(h) for h in headers if _norm_header(h)))
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def compute_values(mapping: Dict[str, List[str]], column_totals: Dict[str, float]) -> Dict[str, float]:
    """Angka per field dari peta kolom + total per kolom. Dipakai server DAN dapat
    ditiru layar (klien menerima `column_totals`) supaya editor pemetaan menghitung sama."""
    values: Dict[str, float] = {}
    for field in FIELD_KEYWORDS:
        total = sum(float(column_totals.get(c) or 0) for c in (mapping.get(field) or []))
        # Platform menulis potongan sebagai angka negatif; form F9 memakai nilai positif
        # dengan arah yang sudah baku — kecuali `adjustments` yang boleh minus.
        values[field] = round(total if field == "adjustments" else abs(total), 2)
    return values


def parse_settlement_report(raw: bytes, filename: str,
                            saved_mapping: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    headers, rows = parse_table(raw, filename)
    if not headers:
        raise ValueError("Baris header tidak ditemukan di berkas")
    if not rows:
        raise ValueError("Berkas tidak punya baris data (hanya header)")

    mapping: Dict[str, List[str]] = {f: [] for f in FIELD_KEYWORDS}
    used: set = set()
    date_col = period_col = id_col = None
    numeric_cols: List[str] = []

    for h in headers:
        norm = _norm_header(h)
        if not norm:
            continue
        if date_col is None and _match(norm, DATE_KEYWORDS):
            date_col = h; used.add(h); continue
        if period_col is None and _match(norm, PERIOD_KEYWORDS):
            period_col = h; used.add(h); continue
        if id_col is None and _match(norm, ID_KEYWORDS):
            id_col = h; used.add(h); continue
        if any(t in norm for t in EXCLUDE_TOKENS) or _is_id_column(norm):
            continue
        if not _is_numeric_column(rows, h):
            continue
        numeric_cols.append(h)
        for field in FIELD_PRIORITY:
            if _match(norm, FIELD_KEYWORDS[field]):
                mapping[field].append(h); used.add(h)
                break

    # Kolom "ads"/"iklan" mudah bertabrakan dengan komisi afiliasi — afiliasi menang.
    for h in list(mapping["ads_deduction"]):
        if h in mapping["affiliate_commission"]:
            mapping["ads_deduction"].remove(h)

    column_totals = {c: round(_sum_column(rows, c), 2) for c in numeric_cols}

    mapping_source = "auto"
    if saved_mapping:
        # Pemetaan yang sudah DIKONFIRMASI staf untuk format ini menang atas tebakan —
        # hanya kolom yang benar-benar ada di berkas yang dipakai.
        confirmed = {f: [c for c in cols if c in column_totals]
                     for f, cols in saved_mapping.items() if f in FIELD_KEYWORDS}
        if any(confirmed.values()):
            mapping = {f: confirmed.get(f, []) for f in FIELD_KEYWORDS}
            used = set(used) | {c for cols in mapping.values() for c in cols}
            mapping_source = "saved"

    values = compute_values(mapping, column_totals)
    unmapped = [c for c in numeric_cols
                if not any(c in cols for cols in mapping.values())][:MAX_UNMAPPED]

    settlement_date = None
    if date_col:
        _, settlement_date = _date_range(rows, date_col)
    period_from = period_to = None
    if period_col:
        period_from, period_to = _date_range(rows, period_col)

    return {
        "row_count": len(rows),
        "filename": filename,
        "values": values,
        "settlement_id": _first_nonempty(rows, id_col) if id_col else None,
        "settlement_date": settlement_date,
        "period_from": period_from,
        "period_to": period_to,
        "mapping": {f: cols for f, cols in mapping.items() if cols},
        "mapping_source": mapping_source,
        "fingerprint": _fingerprint(headers),
        "column_totals": column_totals,
        "numeric_columns": numeric_cols,
        "meta_columns": {"settlement_date": date_col, "period": period_col, "settlement_id": id_col},
        "unmapped_numeric_columns": unmapped,
        "headers": headers,
    }


def guess_platform(headers: List[str]) -> str:
    joined = " ".join(_norm_header(h) for h in headers)
    if re.search(r"\b(settlement|statement|tiktok|affiliate commission)\b", joined):
        return "tiktokshop"
    if re.search(r"(penghasilan|dana dilepaskan|shopee|biaya administrasi)", joined):
        return "shopee"
    return ""
