#!/usr/bin/env python3
"""VERIFIKASI FASE 18 — BUG-3: SLIP GAJI PDF (tanda tangan · breakdown · watermark).

Permintaan user 2026-07-26: *"Verifikasi slip gaji PDF — tanda tangan, breakdown
pokok+tunjangan, watermark CV Dewi Aditya"*.

Yang diuji (isi PDF-nya BENAR-BENAR dibaca ulang, bukan sekadar HTTP 200):
  P1  Watermark memuat NAMA PERUSAHAAN + "RAHASIA".
  P2  Blok tanda tangan ada ("Disetujui oleh" / "Diterima oleh" + nama karyawan).
  P3  Breakdown pendapatan: GAJI POKOK + TUNJANGAN (per item) + lembur +
      Total Pendapatan.
  P4  Breakdown potongan (BPJS/PPh21/terlambat) + GAJI BERSIH.
  P5  Slip dari payroll run yang masih DRAFT ditandai "DRAFT - BELUM FINAL".

Bug yang ditutup di fase ini:
  BUG-P1  Karyawan TIDAK BISA mengunduh slip gajinya sendiri (403 "Hubungi HR")
          dan Portal Saya tidak punya tombol unduh sama sekali.
  BUG-P2  Pemeriksaan kepemilikan slip memakai `user.employee_id` MENTAH dari
          JWT (umur 24 jam) — karyawan yang baru ditautkan HR selalu ditolak.
  BUG-P3  Slip dari run DRAFT tidak dapat dibedakan dari slip final.

Jalankan: python3 /app/scripts/verify_fase18_payslip.py     (self-cleaning)
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "/app/backend")

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

BASE = "http://localhost:8001"
HR = {"email": "hr@dewiaditya.id", "password": "Dewi@123"}
STAFF = {"email": "gudang@dewiaditya.id", "password": "Dewi@123"}
TAG = "QAF18"

PASS = 0
FAIL = 0
FAILED: list[str] = []


def chk(cond, name: str, extra: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}" + (f" — {extra}" if extra else ""))
    else:
        FAIL += 1
        FAILED.append(name)
        print(f"  ❌ {name}" + (f" — {extra}" if extra else ""))
    return bool(cond)


def sec(t: str) -> None:
    print(f"\n{'═' * 78}\n{t}\n{'═' * 78}")


def pdf_text(blob: bytes) -> str:
    from PyPDF2 import PdfReader
    rd = PdfReader(io.BytesIO(blob))
    return "\n".join((p.extract_text() or "") for p in rd.pages)


def static_checks() -> None:
    sec("S. STATIK")
    src = Path("/app/backend/routes/rahaza_payroll_payslips.py").read_text(encoding="utf-8")
    chk("resolve_my_employee" in src,
        "S1 kepemilikan slip memakai SSOT identitas (BUG-P2)")
    chk("Karyawan hanya bisa melihat slip gaji melalui Portal Saya" not in src,
        "S2 karyawan tidak lagi diblokir mengunduh slipnya sendiri (BUG-P1)")
    chk("DRAFT - BELUM FINAL" in src, "S3 penanda DRAFT ada di generator PDF (BUG-P3)")
    fe = Path("/app/frontend/src/components/erp/PortalSayaPayslip.jsx").read_text(encoding="utf-8")
    chk("slip-download-" in fe, "S4 Portal Saya punya tombol Unduh PDF")


async def main() -> None:
    global FAIL
    static_checks()

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "garment_erp")]
    await db.rate_limit_buckets.delete_many({"key": {"$regex": "auth/login"}})

    today = date.today()
    p_from = today.replace(day=1).isoformat()
    p_to = today.isoformat()
    run_id = None
    allowance_id = None

    async with httpx.AsyncClient(timeout=180) as c:
        toks = {}
        for label, cred in (("hr", HR), ("staff", STAFF)):
            r = await c.post(f"{BASE}/api/auth/login", json=cred)
            if r.status_code != 200:
                print(f"  LOGIN {label} GAGAL {r.status_code}")
                FAIL += 1
                return
            toks[label] = {"Authorization": f"Bearer {r.json()['token']}"}

        # ═══════════════════════════════════════════════════════════════════
        sec("A. TUNJANGAN TETAP masuk ke slip (breakdown pokok + tunjangan)")
        # ═══════════════════════════════════════════════════════════════════
        r = await c.post(f"{BASE}/api/rahaza/payroll-allowances", headers=toks["hr"], json={
            "name": f"Tunjangan Transport {TAG}", "calc_type": "fixed",
            "amount": 500000, "applicable_to": "all", "is_active": True,
            "taxable": True, "is_fixed_wage": True,
        })
        d = r.json() if r.status_code in (200, 201) else {}
        d = d.get("allowance") or d          # endpoint membungkus dalam {"ok","allowance"}
        allowance_id = d.get("allowance_id") or d.get("id")
        chk(r.status_code in (200, 201) and allowance_id,
            "A1 HR bisa membuat master tunjangan tetap",
            f"HTTP {r.status_code}: {r.text[:120]}")

        # payroll run BARU supaya tunjangan ikut terhitung
        await db.rahaza_payroll_runs.delete_many({"notes": {"$regex": TAG}})
        r = await c.post(f"{BASE}/api/rahaza/payroll-runs", headers=toks["hr"], json={
            "period_from": p_from, "period_to": p_to, "notes": f"{TAG} run uji"})
        run = r.json() if r.status_code == 200 else {}
        run_id = run.get("id")
        chk(r.status_code == 200 and run_id, "A2 payroll run terbentuk",
            f"HTTP {r.status_code} emp={run.get('total_employees')}")

        slips = []
        if run_id:
            r = await c.get(f"{BASE}/api/rahaza/payslips?run_id={run_id}", headers=toks["hr"])
            slips = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        chk(len(slips) > 0, "A3 slip gaji terbentuk untuk karyawan", f"n={len(slips)}")

        target = next((s for s in slips if s.get("employee_code") == "DA-005"), slips[0] if slips else {})
        alw = target.get("allowances") or []
        chk(any(TAG in (a.get("label") or "") for a in alw),
            "A4 tunjangan tetap MASUK ke slip (bukan hanya gaji pokok)",
            f"tunjangan={[a.get('label') for a in alw]}")
        chk(float(target.get("allowance_total") or 0) >= 500000,
            "A5 total tunjangan terakumulasi benar",
            f"total={target.get('allowance_total')}")
        chk(len(target.get("earnings") or []) > 0,
            "A6 komponen gaji pokok tercatat",
            f"earnings={[e.get('label') for e in (target.get('earnings') or [])]}")

        # ═══════════════════════════════════════════════════════════════════
        sec("B. ISI PDF — watermark · tanda tangan · breakdown")
        # ═══════════════════════════════════════════════════════════════════
        pid = target.get("id")
        r = await c.get(f"{BASE}/api/rahaza/payslips/{pid}/pdf", headers=toks["hr"])
        ok_pdf = chk(r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > 2000,
                     "B1 PDF slip gaji terbentuk",
                     f"HTTP {r.status_code} {len(r.content)}B")
        txt = pdf_text(r.content) if ok_pdf else ""
        up = txt.upper()

        chk("DEWI ADITYA" in up and "RAHASIA" in up,
            "B2 watermark nama perusahaan + RAHASIA",
            f"ada_nama={'DEWI ADITYA' in up} ada_rahasia={'RAHASIA' in up}")
        chk("DISETUJUI OLEH" in up and "DITERIMA OLEH" in up,
            "B3 blok TANDA TANGAN lengkap")
        chk((target.get("employee_name") or "").upper() in up,
            "B4 nama karyawan tercetak di area tanda tangan",
            f"nama={target.get('employee_name')}")
        chk("GAJI POKOK" in up, "B5 breakdown GAJI POKOK tercetak")
        chk(TAG.upper() in up or "TUNJANGAN" in up,
            "B6 breakdown TUNJANGAN tercetak")
        chk("TOTAL PENDAPATAN" in up and "GAJI BERSIH" in up,
            "B7 subtotal pendapatan & gaji bersih tercetak")
        chk("POTONGAN" in up, "B8 blok potongan tercetak")
        chk("PERIODE" in up and str(today.year) in txt,
            "B9 periode penggajian tercetak")
        chk("DRAFT - BELUM FINAL" in up,
            "B10 slip dari run DRAFT ditandai jelas (BUG-P3)")

        # ═══════════════════════════════════════════════════════════════════
        sec("C. HAK AKSES UNDUH")
        # ═══════════════════════════════════════════════════════════════════
        r = await c.get(f"{BASE}/api/rahaza/payslips/{pid}/pdf", headers=toks["staff"])
        chk(r.status_code == 200 and r.content[:4] == b"%PDF",
            "C1 karyawan BISA mengunduh slip MILIKNYA (BUG-P1)",
            f"HTTP {r.status_code}: {r.text[:110] if r.status_code != 200 else 'PDF ok'}")

        other = next((s for s in slips if s.get("employee_code") != "DA-005"), None)
        if other:
            r = await c.get(f"{BASE}/api/rahaza/payslips/{other['id']}/pdf", headers=toks["staff"])
            chk(r.status_code == 403,
                "C2 karyawan TIDAK bisa mengunduh slip karyawan lain",
                f"HTTP {r.status_code}")
        else:
            chk(False, "C2 (persiapan) tidak ada slip pembanding")

        r = await c.get(f"{BASE}/api/rahaza/payslips/tidak-ada-id/pdf", headers=toks["hr"])
        chk(r.status_code == 404, "C3 id slip tak dikenal → 404", f"HTTP {r.status_code}")

        # ═══════════════════════════════════════════════════════════════════
        sec("D. BUNDLE SEMUA SLIP (1 file per run)")
        # ═══════════════════════════════════════════════════════════════════
        r = await c.get(f"{BASE}/api/rahaza/payroll-runs/{run_id}/pdf", headers=toks["hr"])
        chk(r.status_code == 200 and len(r.content) > 5000,
            "D1 bundle PDF semua slip terbentuk",
            f"HTTP {r.status_code} {len(r.content)}B")
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            from PyPDF2 import PdfReader
            pages = len(PdfReader(io.BytesIO(r.content)).pages)
            chk(pages >= len(slips), "D2 satu halaman per karyawan",
                f"halaman={pages} slip={len(slips)}")

    # ═══════════════════════════════════════════════════════════════════════
    sec("E. PEMBERSIHAN ARTEFAK UJI")
    # ═══════════════════════════════════════════════════════════════════════
    n = 0
    if run_id:
        n += (await db.rahaza_payslips.delete_many({"run_id": run_id})).deleted_count
        n += (await db.rahaza_payroll_runs.delete_many({"id": run_id})).deleted_count
    n += (await db.da_payroll_allowances.delete_many(
        {"name": {"$regex": TAG}})).deleted_count
    n += (await db.rahaza_payroll_runs.delete_many({"notes": {"$regex": TAG}})).deleted_count
    print(f"  TOTAL dihapus: {n}")
    left = await db.da_payroll_allowances.count_documents({"name": {"$regex": TAG}})
    print(f"  sisa artefak: {left} (harus 0)")

    sec("RINGKASAN")
    print(f"  {PASS} PASS / {FAIL} FAIL")
    for f in FAILED:
        print(f"    ✗ {f}")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(1 if FAIL else 0)
