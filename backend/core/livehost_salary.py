"""core/livehost_salary.py — **SATU sumber gaji bulanan host live** (sesi #34).

Pemilik: "livehost digaji bulanan bukan persesi" + "harus tersambung ke payroll HR".

Di mana gaji bulanan SEBENARNYA tinggal (diukur 2026-08-23):
* `rahaza_employees` (16 dokumen) **tidak punya field gaji sama sekali** —
  isinya identitas karyawan saja. Membaca `basic_salary` dari sini selalu 0.
* Yang memegang angka gaji adalah **`rahaza_payroll_profiles`** (16 dokumen):
  `pay_scheme='monthly'` + `base_rate` per `employee_id`. Inilah SSOT payroll HR.

Modul ini menjadi satu-satunya pembaca angka itu supaya tiga layar (anggaran
marketing, rekap pembayaran livehost, laporan biaya) tidak masing-masing menebak
tempat gaji disimpan — dan supaya "host belum ditautkan ke karyawan HR" selalu
DIKATAKAN, bukan diam-diam menjadi Rp 0.
"""
from __future__ import annotations


def _num(v, d: float = 0.0) -> float:
    try:
        return float(v if v not in (None, "") else d)
    except (TypeError, ValueError):
        return float(d)


async def monthly_salary_map(db, hosts: list[dict]) -> dict:
    """{host_id: {'salary','source','employee_id','reason'}} untuk daftar host.

    `source` bernilai:
      * ``payroll_profile`` — dari `rahaza_payroll_profiles.base_rate` (SSOT HR)
      * ``host_master``     — nominal darurat yang diisi di master host
      * ``none``            — TIDAK ADA angka; `reason` menjelaskan kekurangannya
    """
    emp_ids = [h.get("employee_id") for h in hosts if h.get("employee_id")]
    profiles = {}
    if emp_ids:
        rows = await db.rahaza_payroll_profiles.find(
            {"employee_id": {"$in": emp_ids}, "active": {"$ne": False}},
            {"_id": 0, "employee_id": 1, "base_rate": 1, "pay_scheme": 1}).to_list(500)
        for r in rows:
            profiles[r["employee_id"]] = r
    employees = {}
    if emp_ids:
        for e in await db.rahaza_employees.find(
                {"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "name": 1, "employee_code": 1}
        ).to_list(500):
            employees[e["id"]] = e

    out = {}
    for h in hosts:
        eid = h.get("employee_id") or ""
        prof = profiles.get(eid)
        fallback = _num(h.get("monthly_salary"))
        if prof and _num(prof.get("base_rate")) > 0:
            out[h["id"]] = {
                "salary": _num(prof["base_rate"]), "source": "payroll_profile",
                "employee_id": eid, "employee_name": (employees.get(eid) or {}).get("name", ""),
                "pay_scheme": prof.get("pay_scheme") or "monthly", "reason": "",
            }
        elif fallback > 0:
            out[h["id"]] = {
                "salary": fallback, "source": "host_master", "employee_id": eid,
                "employee_name": (employees.get(eid) or {}).get("name", ""),
                "pay_scheme": "monthly",
                "reason": ("nominal diisi di master host, BUKAN dari payroll HR — "
                           "tautkan host ke karyawan & isi profil payroll agar satu angka"),
            }
        else:
            out[h["id"]] = {
                "salary": 0.0, "source": "none", "employee_id": eid,
                "employee_name": (employees.get(eid) or {}).get("name", ""),
                "pay_scheme": "", "reason": (
                    "host belum ditautkan ke karyawan HR" if not eid else
                    f"karyawan {eid} belum punya profil payroll bulanan (base_rate)"),
            }
    return out
