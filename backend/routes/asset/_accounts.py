"""routes/asset/_accounts.py — resolusi kode akun (CoA) untuk jurnal modul Aset.

BUG-5 (FASE 11, 2026-07-25)
---------------------------
**Gejala:** gate `verify_data_integrity` INV-GL-3 MERAH — baris jurnal memakai
`account_code` yang TIDAK ADA di Chart of Accounts.

**Akar:** modul Aset menulis kode akun secara HARDCODE dengan format 4-digit
(`"1500"`, `"1100"`, `"1590"`, `"8100"`, `"6300"`), padahal CoA proyek ini
memakai format bersegmen (`"1-2500"`, `"1-110"`, `"2-1100"`, …). Akibatnya:

  * setiap pembelian & disposal aset menghasilkan jurnal yang menunjuk **akun
    hantu** — tidak muncul di Buku Besar / Neraca Saldo per akun;
  * gate integritas data selalu merah sehingga temuan nyata lain ikut tenggelam.

Modul Aset juga satu-satunya yang MELEWATI sistem `rahaza_posting_profiles`,
padahal profil `asset_acquisition` dan `asset_disposal` SUDAH ADA dan kodenya
sudah valid terhadap CoA.

**Perbaikan:** semua kode akun modul Aset kini diambil dari posting profile
(SSOT), dengan fallback yang sudah diverifikasi ADA di CoA, dan nama akun
diambil langsung dari CoA supaya tampilan jurnal konsisten.
"""
from __future__ import annotations

from typing import Optional

from routes.rahaza_posting_profiles import get_mapping

# Fallback dipakai HANYA bila posting profile hilang/di-nonaktifkan.
# Semua kode di bawah sudah diverifikasi ada di `rahaza_coa_accounts`.
FALLBACK = {
    "fixed_asset": "1-2500",       # Aset Tetap
    "accum_depr": "1-2501",        # Akumulasi Penyusutan
    "cash": "1-1201",              # Bank BCA (kanonik 4-digit)
    "ap_clearing": "2-1150",       # Hutang Belum Ditagih (GRNI)
    "gain_on_disposal": "4-2200",  # Keuntungan Penjualan Aset Tetap
    "loss_on_disposal": "6-4200",  # Kerugian Penjualan Aset Tetap
    "depr_expense": "6-2700",      # Beban Penyusutan
}

# Tipe akun untuk baris jurnal (dipakai bila CoA tidak menyebutkan).
_ROLE_TYPE = {
    "fixed_asset": "asset",
    "accum_depr": "asset",
    "cash": "asset",
    "ap_clearing": "liability",
    "gain_on_disposal": "revenue",
    "loss_on_disposal": "expense",
    "depr_expense": "expense",
}


async def _coa_name(db, code: str) -> Optional[str]:
    doc = await db.rahaza_coa_accounts.find_one({"code": code}, {"_id": 0, "name": 1, "type": 1})
    return doc if doc else None


async def resolve_asset_accounts(db) -> dict:
    """Kembalikan peta `role → {code, name, type}` untuk jurnal modul Aset.

    Urutan sumber kebenaran:
      1. `rahaza_posting_profiles` (`asset_acquisition`, `asset_disposal`, `depreciation`)
      2. `FALLBACK` di modul ini (sudah pasti ada di CoA)
    Nama & tipe akun diambil dari CoA bila kodenya ditemukan.
    """
    acq = await get_mapping(db, "asset_acquisition") or {}
    disp = await get_mapping(db, "asset_disposal") or {}
    depr = await get_mapping(db, "depreciation") or {}

    raw = {
        "fixed_asset": acq.get("debit_fixed_asset") or disp.get("credit_fixed_asset"),
        "accum_depr": depr.get("credit_accum_depr") or disp.get("debit_accum_depr"),
        "cash": disp.get("debit_cash"),
        "ap_clearing": acq.get("credit_ap_clearing"),
        "gain_on_disposal": disp.get("credit_gain_on_disposal"),
        "loss_on_disposal": disp.get("debit_loss_on_disposal"),
        "depr_expense": depr.get("debit_depr_expense"),
    }

    out: dict[str, dict] = {}
    for role, fallback_code in FALLBACK.items():
        code = raw.get(role) or fallback_code
        coa = await _coa_name(db, code)
        if not coa:
            # kode dari profil ternyata tak ada di CoA → pakai fallback yang pasti ada
            code = fallback_code
            coa = await _coa_name(db, code)
        out[role] = {
            "code": code,
            "name": (coa or {}).get("name") or role.replace("_", " ").title(),
            "type": ((coa or {}).get("type") or _ROLE_TYPE.get(role, "asset")).lower(),
        }
    return out


def line(acc: dict, *, debit: float = 0.0, credit: float = 0.0, description: str = "") -> dict:
    """Bentuk satu baris jurnal dari hasil :func:`resolve_asset_accounts`."""
    return {
        "account_code": acc["code"],
        "account_name": acc["name"],
        "account_type": acc["type"],
        "debit": float(debit or 0),
        "credit": float(credit or 0),
        "description": description,
    }
