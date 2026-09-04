"""
CV. Dewi Aditya / PT Rahaza — Tax & BPJS Calculator (Phase 8.8)

Indonesia-compliant calculation helpers for payroll:
  - PPh21 (Pajak Penghasilan Pasal 21) — progressive bracket based on PTKP
  - BPJS Kesehatan (health insurance) — 1% employee / 4% employer, ceiling 12M
  - BPJS Ketenagakerjaan (JHT/JP/JKK/JKM)

These are pure functions — no DB calls. Called from rahaza_payroll.py during
payroll run generation.

Reference (year 2024/2025 tarif):
  PTKP annual:
    TK/0 = 54,000,000   TK/1 = 58,500,000   TK/2 = 63,000,000   TK/3 = 67,500,000
    K/0  = 58,500,000   K/1  = 63,000,000   K/2  = 67,500,000   K/3  = 72,000,000

  PPh21 progressive (UU HPP):
    0 - 60,000,000       → 5%
    60 - 250,000,000     → 15%
    250 - 500,000,000    → 25%
    500 - 5,000,000,000  → 30%
    > 5,000,000,000      → 35%

  Biaya Jabatan: 5% × gross (max 6,000,000/year or 500,000/month)

  BPJS Kesehatan:
    Total 5% × gross (ceiling 12,000,000)
    Employee = 1%, Employer = 4%

  BPJS Ketenagakerjaan:
    JHT (Hari Tua): 5.7% = 2% employee + 3.7% employer (no ceiling)
    JP  (Pensiun):  3%   = 1% employee + 2%   employer (ceiling 10,042,300)
    JKK (Kecelakaan Kerja): 0.24% - 1.74% employer only (risk tier; default 0.54% = Very Low)
    JKM (Kematian): 0.30% employer only
"""
from typing import Dict


# ─── Constants ───────────────────────────────────────────────────────────────
PTKP_ANNUAL = {
    "TK/0": 54_000_000, "TK/1": 58_500_000, "TK/2": 63_000_000, "TK/3": 67_500_000,
    "K/0":  58_500_000, "K/1":  63_000_000, "K/2":  67_500_000, "K/3":  72_000_000,
}

PPH21_BRACKETS = [
    (60_000_000,      0.05),
    (250_000_000,     0.15),
    (500_000_000,     0.25),
    (5_000_000_000,   0.30),
    (float("inf"),    0.35),
]

BIAYA_JABATAN_RATE = 0.05
BIAYA_JABATAN_MAX_ANNUAL = 6_000_000

# BPJS
BPJS_KES_CEILING = 12_000_000
BPJS_KES_EMP_RATE = 0.01
BPJS_KES_COMP_RATE = 0.04

BPJS_JHT_EMP_RATE = 0.02
BPJS_JHT_COMP_RATE = 0.037

BPJS_JP_CEILING = 10_042_300
BPJS_JP_EMP_RATE = 0.01
BPJS_JP_COMP_RATE = 0.02

BPJS_JKK_RATES = {  # company pays, risk tier
    "very_low":  0.0024,
    "low":       0.0054,
    "medium":    0.0089,
    "high":      0.0127,
    "very_high": 0.0174,
}
BPJS_JKM_COMP_RATE = 0.003


# ─── PPh21 ───────────────────────────────────────────────────────────────────
def compute_biaya_jabatan_monthly(monthly_gross: float) -> float:
    """5% of gross, capped at 500k/month."""
    return min(monthly_gross * BIAYA_JABATAN_RATE, BIAYA_JABATAN_MAX_ANNUAL / 12)


def compute_pph21_annual(annual_net_taxable: float) -> float:
    """Apply progressive brackets to annual taxable income."""
    if annual_net_taxable <= 0:
        return 0
    tax = 0.0
    prev = 0
    for top, rate in PPH21_BRACKETS:
        if annual_net_taxable > top:
            tax += (top - prev) * rate
            prev = top
        else:
            tax += (annual_net_taxable - prev) * rate
            break
    return round(tax)


def compute_pph21_monthly(
    monthly_gross: float,
    ptkp_code: str = "TK/0",
    bpjs_employee_annual: float = 0,
) -> Dict:
    """
    Calculate PPh21 monthly deduction.
    Args:
        monthly_gross: Gaji bruto bulanan (sebelum potongan)
        ptkp_code: Kode PTKP (TK/0, K/1, dst)
        bpjs_employee_annual: BPJS employee contribution setahun (pengurang pajak)

    Returns: { 'pph21_monthly', 'pph21_annual', 'ptkp', 'taxable_annual',
               'biaya_jabatan_monthly', 'breakdown' }
    """
    ptkp = PTKP_ANNUAL.get(ptkp_code, PTKP_ANNUAL["TK/0"])
    annual_gross = monthly_gross * 12
    biaya_jabatan_monthly = compute_biaya_jabatan_monthly(monthly_gross)
    biaya_jabatan_annual = biaya_jabatan_monthly * 12

    # Net income = gross - biaya jabatan - JHT employee - JP employee (pengurang)
    net_annual = annual_gross - biaya_jabatan_annual - bpjs_employee_annual
    taxable = max(0, net_annual - ptkp)
    pph_annual = compute_pph21_annual(taxable)
    pph_monthly = round(pph_annual / 12)

    return {
        "pph21_monthly": pph_monthly,
        "pph21_annual": pph_annual,
        "ptkp_code": ptkp_code,
        "ptkp_annual": ptkp,
        "annual_gross": annual_gross,
        "biaya_jabatan_monthly": round(biaya_jabatan_monthly),
        "biaya_jabatan_annual": round(biaya_jabatan_annual),
        "bpjs_pengurang_annual": bpjs_employee_annual,
        "net_taxable_annual": round(net_annual),
        "taxable_after_ptkp": round(taxable),
    }


# ─── BPJS ────────────────────────────────────────────────────────────────────
def compute_bpjs(
    monthly_gross: float,
    include_ketenagakerjaan: bool = True,
    jkk_risk_tier: str = "very_low",
) -> Dict:
    """
    Calculate BPJS deductions (Kesehatan + Ketenagakerjaan).

    Returns keys:
      kes_emp, kes_comp (BPJS Kesehatan)
      jht_emp, jht_comp (Jaminan Hari Tua)
      jp_emp, jp_comp   (Jaminan Pensiun)
      jkk_comp, jkm_comp (Kecelakaan Kerja, Kematian — company only)
      total_employee: total potongan dari karyawan (masuk deductions)
      total_company:  total kontribusi perusahaan (cost, bukan potongan)
    """
    # BPJS Kesehatan (ceiling 12M)
    kes_base = min(monthly_gross, BPJS_KES_CEILING)
    kes_emp = round(kes_base * BPJS_KES_EMP_RATE)
    kes_comp = round(kes_base * BPJS_KES_COMP_RATE)

    jht_emp = jht_comp = jp_emp = jp_comp = jkk_comp = jkm_comp = 0

    if include_ketenagakerjaan:
        # JHT — no ceiling, full gross
        jht_emp = round(monthly_gross * BPJS_JHT_EMP_RATE)
        jht_comp = round(monthly_gross * BPJS_JHT_COMP_RATE)

        # JP — ceiling 10.042.300
        jp_base = min(monthly_gross, BPJS_JP_CEILING)
        jp_emp = round(jp_base * BPJS_JP_EMP_RATE)
        jp_comp = round(jp_base * BPJS_JP_COMP_RATE)

        # JKK (company only, based on risk tier)
        jkk_rate = BPJS_JKK_RATES.get(jkk_risk_tier, BPJS_JKK_RATES["very_low"])
        jkk_comp = round(monthly_gross * jkk_rate)

        # JKM (company only)
        jkm_comp = round(monthly_gross * BPJS_JKM_COMP_RATE)

    total_employee = kes_emp + jht_emp + jp_emp
    total_company = kes_comp + jht_comp + jp_comp + jkk_comp + jkm_comp

    return {
        "kes_emp": kes_emp,
        "kes_comp": kes_comp,
        "jht_emp": jht_emp,
        "jht_comp": jht_comp,
        "jp_emp": jp_emp,
        "jp_comp": jp_comp,
        "jkk_comp": jkk_comp,
        "jkm_comp": jkm_comp,
        "total_employee": total_employee,
        "total_company": total_company,
    }


def compute_full_tax_and_bpjs(
    monthly_gross: float,
    ptkp_code: str = "TK/0",
    apply_bpjs: bool = True,
    apply_pph21: bool = True,
    include_ketenagakerjaan: bool = True,
    jkk_risk_tier: str = "very_low",
    bpjs_base: float | None = None,
) -> Dict:
    """
    One-shot calculator.
    Returns a list of 'deductions' [{label, amount, type}] + the raw calc.

    FASE 15 — `bpjs_base`: dasar iuran BPJS adalah **UPAH TETAP** (gaji pokok +
    tunjangan TETAP), bukan penghasilan bruto. Rujukan: PP 84/2013 jo. Perpres
    64/2020, dan ini juga cara hitung di sheet "Data THP" milik user:
    1% × (Gaji Pokok + Tunjangan Jabatan). Kalau `bpjs_base` tidak diberikan,
    perilaku lama dipertahankan (memakai `monthly_gross`) supaya tidak ada
    perubahan diam-diam pada pemanggil lain.
    PPh21 TETAP memakai `monthly_gross` (seluruh penghasilan) sesuai UU PPh.
    """
    base_for_bpjs = monthly_gross if bpjs_base is None else float(bpjs_base)
    bpjs = compute_bpjs(base_for_bpjs, include_ketenagakerjaan, jkk_risk_tier) if apply_bpjs else {
        "kes_emp": 0, "jht_emp": 0, "jp_emp": 0, "total_employee": 0, "total_company": 0,
    }

    bpjs_emp_annual = bpjs["total_employee"] * 12
    pph21 = compute_pph21_monthly(monthly_gross, ptkp_code, bpjs_emp_annual) if apply_pph21 else {
        "pph21_monthly": 0, "pph21_annual": 0,
    }

    deductions = []
    if apply_bpjs and bpjs["kes_emp"] > 0:
        deductions.append({"label": "BPJS Kesehatan (1%)", "amount": bpjs["kes_emp"], "type": "bpjs_kesehatan"})
    if apply_bpjs and include_ketenagakerjaan:
        if bpjs["jht_emp"] > 0:
            deductions.append({"label": "BPJS Ketenagakerjaan JHT (2%)", "amount": bpjs["jht_emp"], "type": "bpjs_jht"})
        if bpjs["jp_emp"] > 0:
            deductions.append({"label": "BPJS Ketenagakerjaan JP (1%)", "amount": bpjs["jp_emp"], "type": "bpjs_jp"})
    if apply_pph21 and pph21["pph21_monthly"] > 0:
        deductions.append({"label": f"PPh21 ({ptkp_code})", "amount": pph21["pph21_monthly"], "type": "pph21"})

    return {
        "deductions": deductions,
        "bpjs": bpjs,
        "pph21": pph21,
        "total_deductions": sum(d["amount"] for d in deductions),
    }
