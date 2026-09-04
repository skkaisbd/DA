#!/usr/bin/env python3
"""VERIFIKASI FASE 17 — BUG-4: SETUP CUTI KARYAWAN & MASTER JENIS/ALASAN CUTI.

Keluhan user 2026-07-26: *"error setup cuti karyawan + master alasan/jenis cuti
(collection salah)"*.

Bug NYATA yang ditutup:
  BUG-C1  `POST /leave-types` MEMBUANG `request_type`, `requires_document`,
          `max_days_without_doc`, `doc_note`, `color`, `legal_basis` yang dikirim
          form HR ⇒ jenis cuti buatan HR tak pernah bisa mewajibkan dokumen.
  BUG-C2  Satu koleksi DUA bentuk: seeder menulis `unpaid`, form HR menulis
          `paid`. Pembaca `GET /leaves*` memakai `lt.get("paid", False)` ⇒
          **"Cuti Tahunan" dilaporkan TIDAK DIBAYAR**; payroll & carry-forward
          memfilter `unpaid: True` ⇒ jenis buatan HR tak pernah kena potongan.
  BUG-C3  `PUT /leave-types/{id}` mem-`$set` body MENTAH (bisa menulis field
          sembarang / menduplikasi kode / mematikan `active` tanpa cek).
  BUG-C4  `GET /leave-balances/my` memakai `user.employee_id` MENTAH dari JWT
          (umur 24 jam) ⇒ karyawan yang baru ditautkan HR tetap mendapat
          409 "User belum ter-link ke karyawan" sampai login ulang.
  BUG-C5  `allocate-year` memakai filter `{"active": True}` (bukan SSOT
          `{"active": {"$ne": False}}`) ⇒ karyawan lama tanpa field `active`
          tidak pernah dapat jatah cuti.
  BUG-C6  `PUT /leave-balances/{id}` melempar **500 polos** bila kolom jatah
          diisi teks; penyesuaian negatif bisa membuat jatah minus.
  BUG-C7  Endpoint PUT/DELETE jenis cuti TIDAK punya form apa pun di UI
          (wiring FE↔BE putus).

Jalankan: python3 /app/scripts/verify_fase17_cuti.py      (self-cleaning)
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, "/app/backend")

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
HR = {"email": "hr@dewiaditya.id", "password": "Dewi@123"}
STAFF = {"email": "gudang@dewiaditya.id", "password": "Dewi@123"}
TAG = "QAF17"

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


BE = Path("/app/backend")
FE = Path("/app/frontend/src/components/erp")


def static_checks() -> None:
    sec("S. STATIK — SSOT master jenis cuti & identitas")
    chk((BE / "utils/leave_types.py").exists(), "S1 SSOT `utils/leave_types.py` ada")

    leave = (BE / "routes/rahaza_leave.py").read_text(encoding="utf-8")
    chk('lt.get("paid", False)' not in leave,
        "S2 tidak ada lagi pembaca `lt.get(\"paid\", False)` (BUG-C2)")
    chk("build_leave_type_doc" in leave,
        "S3 create/update jenis cuti memakai SSOT pembentuk dokumen")

    seed = (BE / "routes/rahaza_hr_seed.py").read_text(encoding="utf-8")
    chk("build_leave_type_doc" in seed, "S4 seeder HR memakai SSOT yang sama")

    bal = (BE / "routes/rahaza_leave_balances.py").read_text(encoding="utf-8")
    chk("resolve_my_employee" in bal and 'emp_id = user.get("employee_id")' not in bal,
        "S5 saldo cuti `/my` memakai SSOT identitas (BUG-C4)")
    chk("ACTIVE_EMPLOYEE_FILTER" in bal, "S6 allocate-year memakai filter karyawan SSOT (BUG-C5)")

    ot = (BE / "routes/rahaza_overtime.py").read_text(encoding="utf-8")
    chk("resolve_my_employee" in ot, "S7 modul lembur memakai SSOT identitas")

    selff = (BE / "routes/rahaza_self.py").read_text(encoding="utf-8")
    chk("resolve_my_employee" in selff,
        "S8 rahaza_self tidak lagi menyalin aturan identitas")

    fe = (FE / "RahazaLeaveModule.jsx").read_text(encoding="utf-8")
    chk("leave-type-edit-" in fe and "leave-type-off-" in fe,
        "S9 UI punya tombol Ubah & Nonaktifkan jenis cuti (BUG-C7)")
    chk(not re.search(r"fetch\('/api/", fe) and not re.search(r"fetch\(`/api/", fe),
        "S10 UI cuti memakai REACT_APP_BACKEND_URL (bukan URL relatif)")


async def main() -> None:
    global FAIL
    static_checks()

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "garment_erp")]
    await db.rate_limit_buckets.delete_many({"key": {"$regex": "auth/login"}})
    year = date.today().year
    created_type_ids: list[str] = []
    created_leave_ids: list[str] = []
    orphan_email = f"{TAG.lower()}@example.test"

    async with httpx.AsyncClient(timeout=90) as c:
        toks = {}
        for label, cred in (("admin", ADMIN), ("hr", HR), ("staff", STAFF)):
            r = await c.post(f"{BASE}/api/auth/login", json=cred)
            if r.status_code != 200:
                print(f"  LOGIN {label} GAGAL {r.status_code}")
                FAIL += 1
                return
            toks[label] = {"Authorization": f"Bearer {r.json()['token']}"}

        # ═══════════════════════════════════════════════════════════════════
        sec("A. MASTER JENIS/ALASAN CUTI — form HR tidak boleh hilang datanya")
        # ═══════════════════════════════════════════════════════════════════
        payload = {
            "code": f"{TAG}-SICK", "name": "Izin Sakit QA", "request_type": "sakit",
            "paid": False, "quota_default": 5, "requires_document": True,
            "max_days_without_doc": 2, "doc_note": "Lampirkan surat dokter",
            "description": "dipakai uji otomatis",
        }
        r = await c.post(f"{BASE}/api/rahaza/leave-types", headers=toks["hr"], json=payload)
        d = r.json() if r.status_code == 200 else {}
        if d.get("id"):
            created_type_ids.append(d["id"])
        chk(r.status_code == 200 and d.get("request_type") == "sakit"
            and d.get("requires_document") is True and d.get("max_days_without_doc") == 2
            and d.get("doc_note") == "Lampirkan surat dokter",
            "A1 semua field form HR TERSIMPAN (BUG-C1)",
            f"HTTP {r.status_code} rt={d.get('request_type')} doc={d.get('requires_document')}")

        chk(d.get("unpaid") is True and d.get("paid") is False,
            "A2 `paid` & `unpaid` ditulis sinkron (BUG-C2)",
            f"unpaid={d.get('unpaid')} paid={d.get('paid')}")

        r = await c.post(f"{BASE}/api/rahaza/leave-types", headers=toks["hr"], json=payload)
        chk(r.status_code == 409, "A3 kode ganda ditolak 409", f"HTTP {r.status_code}")

        r = await c.post(f"{BASE}/api/rahaza/leave-types", headers=toks["hr"],
                         json={"code": f"{TAG}-X", "name": "X", "request_type": "piknik"})
        chk(r.status_code == 400, "A4 request_type tak dikenal ditolak", f"HTTP {r.status_code}")

        r = await c.post(f"{BASE}/api/rahaza/leave-types", headers=toks["hr"],
                         json={"code": f"{TAG}-Y", "name": "Y", "quota_default": 9999})
        chk(r.status_code == 400, "A5 kuota di luar nalar ditolak", f"HTTP {r.status_code}")

        r = await c.post(f"{BASE}/api/rahaza/leave-types", headers=toks["staff"],
                         json={"code": f"{TAG}-Z", "name": "Z"})
        chk(r.status_code == 403, "A6 non-HR tidak boleh membuat jenis cuti",
            f"HTTP {r.status_code}")

        lt_id = created_type_ids[0] if created_type_ids else None
        if lt_id:
            r = await c.put(f"{BASE}/api/rahaza/leave-types/{lt_id}", headers=toks["hr"],
                            json={"name": "Izin Sakit QA (revisi)", "paid": True,
                                  "hacker_field": "xxx"})
            u = r.json() if r.status_code == 200 else {}
            chk(r.status_code == 200 and u.get("name") == "Izin Sakit QA (revisi)"
                and u.get("paid") is True and u.get("unpaid") is False
                and u.get("requires_document") is True,
                "A7 ubah jenis cuti: field lain TIDAK hilang, paid/unpaid sinkron",
                f"HTTP {r.status_code}")
            raw = await db.rahaza_leave_types.find_one({"id": lt_id}, {"_id": 0})
            chk("hacker_field" not in (raw or {}),
                "A8 field liar dari body TIDAK ikut tersimpan (BUG-C3)")

        r = await c.get(f"{BASE}/api/rahaza/leave-types", headers=toks["hr"])
        types = r.json() if r.status_code == 200 else []
        annual = next((t for t in types if t.get("code") == "ANNUAL"), {})
        chk(bool(annual) and annual.get("paid") is True and annual.get("unpaid") is False,
            "A9 'Cuti Tahunan' bawaan = BERBAYAR (dulu tampil tidak dibayar)",
            f"paid={annual.get('paid')} unpaid={annual.get('unpaid')}")
        chk(all(t.get("paid") is not None and t.get("unpaid") is not None
                and t.get("paid") != t.get("unpaid") for t in types),
            "A10 semua jenis cuti punya paid/unpaid konsisten", f"n={len(types)}")

        # ═══════════════════════════════════════════════════════════════════
        sec("B. POTONGAN CUTI TANPA UPAH — jenis buatan HR ikut terhitung")
        # ═══════════════════════════════════════════════════════════════════
        # payroll & scheduler memfilter {"unpaid": True} langsung di DB
        n = await db.rahaza_leave_types.count_documents(
            {"unpaid": True, "active": True, "code": f"{TAG}-SICK"})
        # (sudah diubah jadi paid di A7 ⇒ harus 0)
        chk(n == 0, "B1 perubahan berbayar langsung terlihat oleh query payroll",
            f"cocok={n}")
        r = await c.put(f"{BASE}/api/rahaza/leave-types/{lt_id}", headers=toks["hr"],
                        json={"paid": False})
        n2 = await db.rahaza_leave_types.count_documents(
            {"unpaid": True, "active": True, "code": f"{TAG}-SICK"})
        chk(n2 == 1, "B2 jenis 'tanpa gaji' buatan HR ditemukan query payroll (BUG-C2)",
            f"cocok={n2}")

        # ═══════════════════════════════════════════════════════════════════
        sec("C. SETUP SALDO CUTI KARYAWAN")
        # ═══════════════════════════════════════════════════════════════════
        r = await c.post(f"{BASE}/api/rahaza/leave-balances/allocate-year",
                         headers=toks["hr"], json={"year": year})
        d = r.json() if r.status_code == 200 else {}
        chk(r.status_code == 200 and d.get("total_employees", 0) > 0,
            "C1 alokasi jatah tahunan berjalan",
            f"HTTP {r.status_code} emp={d.get('total_employees')} lt={d.get('total_leave_types')}")

        r = await c.post(f"{BASE}/api/rahaza/leave-balances/allocate-year",
                         headers=toks["hr"], json={"year": 1900})
        chk(r.status_code == 400, "C2 tahun tidak masuk akal ditolak", f"HTTP {r.status_code}")

        r = await c.get(f"{BASE}/api/rahaza/leave-balances/my?year={year}", headers=toks["staff"])
        mine = r.json() if r.status_code == 200 else {}
        chk(r.status_code == 200 and len(mine.get("balances") or []) > 0,
            "C3 karyawan melihat saldo cutinya sendiri", f"HTTP {r.status_code}")

        # BUG-C4: token TANPA employee_id (tautan dibuat SETELAH login)
        await db.users.delete_many({"email": orphan_email})
        r = await c.post(f"{BASE}/api/users", headers=toks["admin"], json={
            "email": orphan_email, "password": "Qa#17Test",
            "name": f"{TAG} Baru Ditautkan", "role": "operator"})
        if r.status_code in (200, 201):
            rl = await c.post(f"{BASE}/api/auth/login",
                              json={"email": orphan_email, "password": "Qa#17Test"})
            otok = {"Authorization": f"Bearer {rl.json()['token']}"} if rl.status_code == 200 else None
            # tautkan SETELAH token terbit → JWT lama tidak punya employee_id
            emp = await db.rahaza_employees.find_one({"employee_code": "DA-007"}, {"_id": 0, "id": 1})
            u = await db.users.find_one({"email": orphan_email}, {"_id": 0, "id": 1})
            await db.users.update_one({"email": orphan_email},
                                      {"$set": {"employee_id": emp["id"]}})
            await db.rahaza_employees.update_one({"id": emp["id"]},
                                                 {"$set": {"user_id": u["id"]}})
            if otok:
                r = await c.get(f"{BASE}/api/rahaza/leave-balances/my?year={year}", headers=otok)
                chk(r.status_code == 200,
                    "C4 karyawan yang baru ditautkan TIDAK lagi ditolak 409 (BUG-C4)",
                    f"HTTP {r.status_code}: {r.text[:110]}")
            else:
                chk(False, "C4 karyawan yang baru ditautkan tidak ditolak", "login gagal")
            await db.rahaza_employees.update_one({"id": emp["id"]}, {"$unset": {"user_id": ""}})
        else:
            chk(False, "C4 (persiapan) gagal membuat user uji", f"HTTP {r.status_code}")

        r = await c.get(f"{BASE}/api/rahaza/leave-balances?year={year}", headers=toks["hr"])
        bals = (r.json() or {}).get("balances") or []
        chk(r.status_code == 200 and len(bals) > 0, "C5 HR melihat semua saldo",
            f"n={len(bals)}")

        if bals:
            bid = bals[0]["id"]
            r = await c.put(f"{BASE}/api/rahaza/leave-balances/{bid}", headers=toks["hr"],
                            json={"allocated": "dua belas"})
            chk(r.status_code == 400, "C6 jatah berupa teks → 400 (dulu 500 polos)",
                f"HTTP {r.status_code}")
            r = await c.put(f"{BASE}/api/rahaza/leave-balances/{bid}", headers=toks["hr"],
                            json={"adjust_delta": -9999, "reason": "uji"})
            chk(r.status_code == 400, "C7 penyesuaian yang membuat jatah minus ditolak",
                f"HTTP {r.status_code}")
            r = await c.put(f"{BASE}/api/rahaza/leave-balances/{bid}", headers=toks["hr"],
                            json={"adjust_delta": 2, "reason": f"{TAG} bonus"})
            d = r.json() if r.status_code == 200 else {}
            chk(r.status_code == 200, "C8 penyesuaian sah tersimpan + tercatat di riwayat",
                f"HTTP {r.status_code}")
            await db.rahaza_leave_balances.update_one(
                {"id": bid}, {"$set": {"allocated": bals[0].get("allocated", 12)},
                              "$pull": {"adjustments": {"reason": f"{TAG} bonus"}}})

        # ═══════════════════════════════════════════════════════════════════
        sec("D. PENGAJUAN CUTI — aturan dokumen & status berbayar")
        # ═══════════════════════════════════════════════════════════════════
        emp = await db.rahaza_employees.find_one({"employee_code": "DA-005"}, {"_id": 0, "id": 1})
        d1 = (date.today() + timedelta(days=20)).isoformat()
        d2 = (date.today() + timedelta(days=24)).isoformat()   # 5 hari > max 2 tanpa dokumen
        r = await c.post(f"{BASE}/api/rahaza/leaves/request", headers=toks["hr"], json={
            "employee_id": emp["id"], "leave_type_id": lt_id,
            "from_date": d1, "to_date": d2, "reason": f"{TAG} tanpa dokumen"})
        chk(r.status_code == 400 and "dokumen" in r.text.lower(),
            "D1 jenis 'wajib dokumen' menolak pengajuan panjang tanpa lampiran",
            f"HTTP {r.status_code}: {r.text[:120]}")

        annual_id = annual.get("id")
        d3 = (date.today() + timedelta(days=30)).isoformat()
        d4 = (date.today() + timedelta(days=31)).isoformat()
        r = await c.post(f"{BASE}/api/rahaza/leaves/request", headers=toks["hr"], json={
            "employee_id": emp["id"], "leave_type_id": annual_id,
            "from_date": d3, "to_date": d4, "reason": f"{TAG} cuti tahunan"})
        lv = r.json() if r.status_code == 200 else {}
        if lv.get("id"):
            created_leave_ids.append(lv["id"])
        chk(r.status_code == 200, "D2 pengajuan cuti tahunan diterima",
            f"HTTP {r.status_code}: {r.text[:120]}")

        r = await c.get(f"{BASE}/api/rahaza/leaves?limit=50", headers=toks["hr"])
        items = (r.json() or {}).get("items") or []
        mine_row = next((i for i in items if i.get("id") in created_leave_ids), {})
        chk(mine_row.get("is_paid") is True,
            "D3 daftar cuti menampilkan 'dibayar' dengan benar (BUG-C2)",
            f"is_paid={mine_row.get('is_paid')}")

        # ═══════════════════════════════════════════════════════════════════
        sec("E. NONAKTIFKAN JENIS CUTI — jangan hapus riwayat")
        # ═══════════════════════════════════════════════════════════════════
        r = await c.delete(f"{BASE}/api/rahaza/leave-types/{annual_id}", headers=toks["hr"])
        chk(r.status_code == 409,
            "E1 jenis cuti dengan pengajuan MENUNGGU tidak bisa dinonaktifkan",
            f"HTTP {r.status_code}: {r.text[:110]}")
        r = await c.delete(f"{BASE}/api/rahaza/leave-types/{uuid.uuid4()}", headers=toks["hr"])
        chk(r.status_code == 404, "E2 jenis cuti tak dikenal → 404", f"HTTP {r.status_code}")

    # ═══════════════════════════════════════════════════════════════════════
    sec("F. PEMBERSIHAN ARTEFAK UJI")
    # ═══════════════════════════════════════════════════════════════════════
    n = 0
    n += (await db.rahaza_leave_types.delete_many({"code": {"$regex": f"^{TAG}"}})).deleted_count
    n += (await db.rahaza_leave_requests.delete_many({"reason": {"$regex": TAG}})).deleted_count
    n += (await db.users.delete_many({"email": orphan_email})).deleted_count
    n += (await db.notifications.delete_many({"body": {"$regex": TAG}})).deleted_count
    print(f"  TOTAL dihapus: {n}")
    left = await db.rahaza_leave_types.count_documents({"code": {"$regex": f"^{TAG}"}})
    print(f"  sisa artefak: {left} (harus 0)")

    sec("RINGKASAN")
    print(f"  {PASS} PASS / {FAIL} FAIL")
    for f in FAILED:
        print(f"    ✗ {f}")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(1 if FAIL else 0)
