"""
PT Rahaza ERP — AQL Sampling Calculator (Sprint 27)
Implements ANSI/ASQ Z1.4 (formerly MIL-STD-105E) Single Sampling Plan
for inline / final QC inspection.

Reference:
  - ANSI/ASQ Z1.4 — Sampling Procedures and Tables for Inspection by Attributes
  - General Inspection Level: I, II (default), III
  - AQL levels supported: 0.65, 1.0, 1.5, 2.5, 4.0, 6.5, 10.0
  - Inspection mode: Normal (default)
"""
import logging
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza/aql", tags=["AQL Sampling"])


# ─── Sample Size Code Letters per General Inspection Level ────────────
# (lot_size_min, lot_size_max, level_I, level_II, level_III)
LOT_SIZE_TABLE = [
    (2,        8,      "A", "A", "B"),
    (9,       15,      "A", "B", "C"),
    (16,      25,      "B", "C", "D"),
    (26,      50,      "C", "D", "E"),
    (51,      90,      "C", "E", "F"),
    (91,     150,      "D", "F", "G"),
    (151,    280,      "E", "G", "H"),
    (281,    500,      "F", "H", "J"),
    (501,   1200,      "G", "J", "K"),
    (1201,  3200,      "H", "K", "L"),
    (3201, 10000,      "J", "L", "M"),
    (10001, 35000,     "K", "M", "N"),
    (35001, 150000,    "L", "N", "P"),
    (150001, 500000,   "M", "P", "Q"),
    (500001, 10**12,   "N", "Q", "R"),
]

# Sample size for each code letter
CODE_TO_SAMPLE = {
    "A": 2,    "B": 3,    "C": 5,    "D": 8,
    "E": 13,   "F": 20,   "G": 32,   "H": 50,
    "J": 80,   "K": 125,  "L": 200,  "M": 315,
    "N": 500,  "P": 800,  "Q": 1250, "R": 2000,
}

# Master Single Normal Inspection Table — Ac/Re for AQL × code letter
# Source: ANSI/ASQ Z1.4 Master Table II-A
# value = (Ac, Re) | "↑" means use next larger sample (resolved at compute time) | "↓" smaller
ARROW_UP = "↑"
ARROW_DOWN = "↓"

# AQL columns we support
SUPPORTED_AQL = [0.65, 1.0, 1.5, 2.5, 4.0, 6.5, 10.0]

# Master table: code_letter → { aql: (Ac, Re) | "↑" | "↓" }
AQL_TABLE = {
    "A": {0.65: ARROW_DOWN, 1.0: ARROW_DOWN, 1.5: ARROW_DOWN, 2.5: ARROW_DOWN, 4.0: ARROW_DOWN, 6.5: ARROW_DOWN, 10.0: (0, 1)},
    "B": {0.65: ARROW_DOWN, 1.0: ARROW_DOWN, 1.5: ARROW_DOWN, 2.5: ARROW_DOWN, 4.0: ARROW_DOWN, 6.5: (0, 1),       10.0: ARROW_UP},
    "C": {0.65: ARROW_DOWN, 1.0: ARROW_DOWN, 1.5: ARROW_DOWN, 2.5: ARROW_DOWN, 4.0: (0, 1),     6.5: ARROW_UP,     10.0: (1, 2)},
    "D": {0.65: ARROW_DOWN, 1.0: ARROW_DOWN, 1.5: ARROW_DOWN, 2.5: (0, 1),     4.0: ARROW_UP,   6.5: (1, 2),       10.0: (2, 3)},
    "E": {0.65: ARROW_DOWN, 1.0: ARROW_DOWN, 1.5: (0, 1),     2.5: ARROW_UP,   4.0: (1, 2),     6.5: (2, 3),       10.0: (3, 4)},
    "F": {0.65: ARROW_DOWN, 1.0: (0, 1),     1.5: ARROW_UP,   2.5: (1, 2),     4.0: (2, 3),     6.5: (3, 4),       10.0: (5, 6)},
    "G": {0.65: (0, 1),     1.0: ARROW_UP,   1.5: (1, 2),     2.5: (2, 3),     4.0: (3, 4),     6.5: (5, 6),       10.0: (7, 8)},
    "H": {0.65: ARROW_UP,   1.0: (1, 2),     1.5: (2, 3),     2.5: (3, 4),     4.0: (5, 6),     6.5: (7, 8),       10.0: (10, 11)},
    "J": {0.65: (1, 2),     1.0: (2, 3),     1.5: (3, 4),     2.5: (5, 6),     4.0: (7, 8),     6.5: (10, 11),     10.0: (14, 15)},
    "K": {0.65: (2, 3),     1.0: (3, 4),     1.5: (5, 6),     2.5: (7, 8),     4.0: (10, 11),   6.5: (14, 15),     10.0: (21, 22)},
    "L": {0.65: (3, 4),     1.0: (5, 6),     1.5: (7, 8),     2.5: (10, 11),   4.0: (14, 15),   6.5: (21, 22),     10.0: ARROW_DOWN},
    "M": {0.65: (5, 6),     1.0: (7, 8),     1.5: (10, 11),   2.5: (14, 15),   4.0: (21, 22),   6.5: ARROW_DOWN,   10.0: ARROW_DOWN},
    "N": {0.65: (7, 8),     1.0: (10, 11),   1.5: (14, 15),   2.5: (21, 22),   4.0: ARROW_DOWN, 6.5: ARROW_DOWN,   10.0: ARROW_DOWN},
    "P": {0.65: (10, 11),   1.0: (14, 15),   1.5: (21, 22),   2.5: ARROW_DOWN, 4.0: ARROW_DOWN, 6.5: ARROW_DOWN,   10.0: ARROW_DOWN},
    "Q": {0.65: (14, 15),   1.0: (21, 22),   1.5: ARROW_DOWN, 2.5: ARROW_DOWN, 4.0: ARROW_DOWN, 6.5: ARROW_DOWN,   10.0: ARROW_DOWN},
    "R": {0.65: (21, 22),   1.0: ARROW_DOWN, 1.5: ARROW_DOWN, 2.5: ARROW_DOWN, 4.0: ARROW_DOWN, 6.5: ARROW_DOWN,   10.0: ARROW_DOWN},
}

CODE_ORDER = ["A","B","C","D","E","F","G","H","J","K","L","M","N","P","Q","R"]


def _lot_to_code_letter(lot_size: int, level: str) -> str:
    """Return sample-size code letter per inspection level (I/II/III)."""
    if lot_size < 2:
        raise ValueError("lot_size minimum 2")
    col_idx = {"I": 2, "II": 3, "III": 4}.get(level, 3)
    for row in LOT_SIZE_TABLE:
        if row[0] <= lot_size <= row[1]:
            return row[col_idx]
    return LOT_SIZE_TABLE[-1][col_idx]


def _resolve_arrow(code: str, aql: float, original_code: str = None) -> tuple:
    """Recursively resolve ↑/↓ until landing on a numeric (Ac, Re).

    Edge cases:
      - ARROW_UP beyond R: use Q with (21,22) — caps at largest sample plan.
      - ARROW_DOWN below A: fall back to (0, 1) on code A — equivalent to
        100% inspection with zero-defect acceptance for very small batches.
    """
    if code not in AQL_TABLE:
        raise ValueError(f"Unknown code letter {code}")
    cell = AQL_TABLE[code].get(aql)
    if cell is None:
        raise ValueError(f"AQL {aql} not supported")
    if cell == ARROW_UP:
        idx = CODE_ORDER.index(code)
        if idx + 1 >= len(CODE_ORDER):
            return (21, 22), code  # cap at current
        return _resolve_arrow(CODE_ORDER[idx + 1], aql, original_code or code)
    if cell == ARROW_DOWN:
        idx = CODE_ORDER.index(code)
        if idx == 0:
            return (0, 1), "A"  # smallest plan: 100% accept zero-defect
        return _resolve_arrow(CODE_ORDER[idx - 1], aql, original_code or code)
    return cell, code  # (Ac, Re), final_code


# ─── Pydantic models ─────────────────────────────────────────────────
class AQLCalcInput(BaseModel):
    lot_size: int = Field(..., ge=2, le=10**9)
    aql: float = Field(2.5, description="0.65, 1.0, 1.5, 2.5, 4.0, 6.5, or 10.0")
    inspection_level: str = Field("II", pattern="^(I|II|III)$")


class AQLCalcResult(BaseModel):
    lot_size: int
    aql: float
    inspection_level: str
    code_letter: str
    final_code_letter: str
    sample_size: int
    accept_number: int
    reject_number: int
    decision_rule: str
    notes: list[str]


# ─── Endpoint ─────────────────────────────────────────────────────────
@router.post("/calculate", response_model=AQLCalcResult)
async def calculate_aql(payload: AQLCalcInput, request: Request):
    """
    Hitung sample size + Ac/Re berdasarkan ANSI/ASQ Z1.4 Single Sampling Normal Inspection.

    Input:
      - lot_size: jumlah pcs dalam batch produksi (min 2)
      - aql: Acceptable Quality Limit (0.65 - 10.0)
      - inspection_level: I (longgar) / II (umum, default) / III (ketat)

    Output:
      - sample_size: jumlah pcs yang harus dicek
      - accept_number (Ac): defect <= Ac → LULUS
      - reject_number (Re): defect >= Re → GAGAL (re-work batch)
      - decision_rule: penjelasan dalam bahasa Indonesia
    """
    await require_auth(request)

    if payload.aql not in SUPPORTED_AQL:
        raise HTTPException(400, f"AQL {payload.aql} tidak didukung. Pilih: {SUPPORTED_AQL}")

    try:
        original_code = _lot_to_code_letter(payload.lot_size, payload.inspection_level)
        ac_re, final_code = _resolve_arrow(original_code, payload.aql)
        sample_size = CODE_TO_SAMPLE[final_code]
        ac, re_ = ac_re

        notes = []
        if final_code != original_code:
            notes.append(
                f"Kode huruf bergeser dari {original_code} ke {final_code} karena tabel master menunjuk panah."
            )
        notes.append(f"Sample harus diambil acak (random) dari seluruh batch {payload.lot_size} pcs.")
        notes.append("Inspeksi dilakukan visual + dimensi sesuai master defect codes.")

        decision_rule = (
            f"Cek {sample_size} pcs sample. Jika defect ≤ {ac} → LULUS (terima batch). "
            f"Jika defect ≥ {re_} → GAGAL (rework atau re-inspect 100%). "
            f"Jika di antara, lakukan re-sample 1 kali."
        )

        return AQLCalcResult(
            lot_size=payload.lot_size,
            aql=payload.aql,
            inspection_level=payload.inspection_level,
            code_letter=original_code,
            final_code_letter=final_code,
            sample_size=sample_size,
            accept_number=ac,
            reject_number=re_,
            decision_rule=decision_rule,
            notes=notes,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/reference")
async def get_reference(request: Request):
    """Get supported AQL values + inspection level descriptions for UI."""
    await require_auth(request)
    return {
        "supported_aql": SUPPORTED_AQL,
        "inspection_levels": [
            {"code": "I", "label": "Level I (Longgar)", "description": "Untuk produk dengan track-record QC bagus / inspeksi dipersingkat"},
            {"code": "II", "label": "Level II (Umum)", "description": "Default untuk inspeksi normal — paling sering digunakan"},
            {"code": "III", "label": "Level III (Ketat)", "description": "Untuk produk kritis / new buyer / batch dengan history defect tinggi"},
        ],
        "aql_meaning": {
            "0.65": "Sangat ketat — produk premium / luxury",
            "1.0": "Ketat — produk export tier-1",
            "1.5": "Ketat-sedang — knit garment standar export",
            "2.5": "Standar — paling umum untuk garment",
            "4.0": "Longgar — produk lokal / mass-market",
            "6.5": "Sangat longgar — produk kelas C / sample produk",
            "10.0": "Inspeksi minimal — pemeriksaan visual cepat",
        },
    }
