"""
money.py — Locale-Indonesia (id-ID) number parsing & formatting.
=============================================================================
SATU SUMBER KEBENARAN backend untuk PARSE & FORMAT angka Rupiah.

Locale ID: titik '.' = pemisah ribuan, koma ',' = desimal.
  "Rp 1.500.000"  -> 1500000.0
  "1.234.567,89"  -> 1234567.89
  "150,5"         -> 150.5
  "(1.000)"       -> -1000.0   (parentheses = negatif)

Toleran juga terhadap gaya US ("1,234,567.89") dengan aturan:
  - bila ADA titik & koma: pemisah desimal = yang muncul PALING KANAN.
  - bila hanya koma: 1 koma = desimal (ID), >1 koma = ribuan (US).
  - bila hanya titik: >1 titik = ribuan; 1 titik & 3 digit di belakang = ribuan
    (konvensi ID "150.000"), selain itu = desimal ("1.5", "150.75").
"""
import re
from typing import Optional


class MoneyParseError(ValueError):
    pass


def parse_id_number(value) -> float:
    """Parse angka locale-ID (toleran currency/US/parentheses). Raise MoneyParseError bila gagal."""
    if value is None:
        raise MoneyParseError("nilai kosong")
    if isinstance(value, bool):
        raise MoneyParseError("boolean bukan angka")
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if s == '' or s.lower() == 'nan' or s.lower() == 'none':
        raise MoneyParseError("nilai kosong")

    neg = False
    # Negatif via kurung: (1.000) -> -1000
    if s.startswith('(') and s.endswith(')'):
        neg = True
        s = s[1:-1].strip()

    # Buang simbol mata uang (Rp/IDR) & spasi/non-breaking space
    s = re.sub(r'(?i)(rp|idr)', '', s)
    s = s.replace('\u00a0', ' ').strip()

    if s.startswith('-'):
        neg = True
        s = s[1:].strip()
    elif s.startswith('+'):
        s = s[1:].strip()

    # Sisakan hanya digit, titik, koma
    s = re.sub(r'[^0-9.,]', '', s)
    if s == '':
        raise MoneyParseError("tidak ada digit")

    has_dot = '.' in s
    has_com = ',' in s

    if has_dot and has_com:
        if s.rfind(',') > s.rfind('.'):
            # koma paling kanan => koma desimal (ID): buang titik, koma->titik
            s = s.replace('.', '').replace(',', '.')
        else:
            # titik paling kanan => titik desimal (US): buang koma
            s = s.replace(',', '')
    elif has_com:
        if s.count(',') > 1:
            s = s.replace(',', '')          # ribuan (US)
        else:
            s = s.replace(',', '.')         # desimal (ID)
    elif has_dot:
        if s.count('.') > 1:
            s = s.replace('.', '')          # ribuan
        else:
            before, after = s.split('.')[0], s.split('.')[1]
            # "150.000" => ribuan (konvensi ID). TETAPI bila bagian bulatnya "0"
            # (atau kosong), itu MUSTAHIL memakai pemisah ribuan — tidak ada yang
            # menulis nol-ribu. Jadi "0.600" adalah DESIMAL (0,6), bukan 600.
            #
            # 2026-08-07 — penajaman ini ditambahkan saat memakai parser ini sebagai
            # gerbang angka BOM: `qty_per_pcs = "0.600"` (0,6 kg) dulu terbaca 600 kg
            # ⇒ kebutuhan material melonjak 1000× tanpa ada yang tahu.
            if len(after) == 3 and before.lstrip('0') != '':
                s = s.replace('.', '')      # "150.000" => ribuan (konvensi ID)
            # else: biarkan sebagai desimal ("1.5", "150.75", "0.600")

    try:
        val = float(s)
    except ValueError:
        raise MoneyParseError(f"format angka '{value}' tidak dikenali")
    return -val if neg else val


def parse_id_int(value) -> int:
    """Parse ke integer (pembulatan)."""
    return int(round(parse_id_number(value)))


def try_parse_id_number(value, default: Optional[float] = None):
    """Versi non-raising: kembalikan default bila gagal."""
    try:
        return parse_id_number(value)
    except MoneyParseError:
        return default


def format_idr(value, with_symbol: bool = True, decimals: int = 0) -> str:
    """Format angka -> "Rp 1.500.000" (titik ribuan, koma desimal)."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        n = 0.0
    neg = n < 0
    n = abs(n)
    s = f"{n:,.{decimals}f}"                 # gaya US: 1,234,567.89
    # tukar , <-> . agar jadi gaya ID
    s = s.replace(',', '\u0000').replace('.', ',').replace('\u0000', '.')
    out = ('-' if neg else '') + s
    return f"Rp {out}" if with_symbol else out
