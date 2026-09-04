#!/usr/bin/env python3
"""VERIFIKASI FASE 16 — KEBIJAKAN ABSEN WAJIB (selfie+lokasi) & PERSETUJUAN IZIN.

Menjaga keputusan user 2026-07-26:
  · "Selfie + lokasi WAJIB" saat absen masuk/pulang.
  · "Izin keluar butuh persetujuan atasan/HR dulu, bukan langsung tercatat."
  · Menu HR "Rekap Istirahat & Izin" + export Excel.

Bug NYATA yang ditutup (ditemukan saat membaca kode 2026-07-26):
  BUG-F16-1  selfie tidak pernah disimpan — hanya 20 karakter base64 + "..."
             (`photo_selfie_url`), jadi bukti absen fiktif; clock-out bahkan
             MEMBUANG `photo_base64`.
  BUG-F16-2  `_determine_approval` menganggap geofence `not_verified` = lolos ⇒
             absen dari mana saja auto-approved walau kebijakan "wajib".
  BUG-F16-3  haversine disalin 3x; versi di `rahaza_attendance.py` meledak
             TypeError bila koordinat kantor masih None.
  BUG-F16-4  izin langsung memotong jam kerja tanpa persetujuan siapa pun.
  BUG-F16-5  `seed_role_accounts.py` tidak memuat .env ⇒ 7 akun role ter-seed ke
             database SALAH (login 401).

Jalankan: python3 /app/scripts/verify_fase16_absen.py      (self-cleaning)
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, "/app/backend")

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

BASE = "http://localhost:8001"
HR = {"email": "hr@dewiaditya.id", "password": "Dewi@123"}
STAFF = {"email": "gudang@dewiaditya.id", "password": "Dewi@123"}

# Kantor uji — Monas, Jakarta. Titik "jauh" = Bandung (± 120 km).
OFFICE = {"lat": -6.175392, "lng": 106.827153, "radius": 200}
NEAR = {"lat": -6.175500, "lng": 106.827300}      # ± 20 m dari kantor
FAR = {"lat": -6.917464, "lng": 107.619123}       # Bandung

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


def sec(title: str) -> None:
    print("\n" + "═" * 78)
    print(title)
    print("═" * 78)


def make_selfie_b64(px: int = 240) -> str:
    """JPEG asli (> 1 KB) supaya validasi ukuran/format ikut teruji."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (px, px), (200, 180, 160))
    d = ImageDraw.Draw(img)
    for i in range(0, px, 7):
        d.line([(0, i), (px, px - i)], fill=(90 + i % 120, 40, 160 - i % 120), width=2)
    d.ellipse([px * 0.25, px * 0.2, px * 0.75, px * 0.8], outline=(20, 20, 20), width=4)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


async def login(c: httpx.AsyncClient, cred: dict):
    r = await c.post(f"{BASE}/api/auth/login", json=cred)
    if r.status_code != 200:
        print(f"  LOGIN {cred['email']} GAGAL {r.status_code}: {r.text[:120]}")
        return None
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ═════════════════════════════════════════════════════════════════════════════
# S. STATIK — SSOT kebijakan dipakai, tidak ada salinan aturan
# ═════════════════════════════════════════════════════════════════════════════
def static_checks() -> None:
    sec("S. STATIK — SSOT kebijakan absen (tak ada salinan aturan/haversine)")
    be = Path("/app/backend")

    chk((be / "utils/attendance_policy.py").exists(),
        "S1 SSOT `utils/attendance_policy.py` ada")

    # Haversine hanya boleh hidup di SSOT.
    offenders = []
    for p in list((be / "routes").rglob("*.py")) + list((be / "utils").rglob("*.py")):
        if "_archive" in str(p) or p.name == "attendance_policy.py":
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        if "6371000" in src and "math.asin" in src:
            offenders.append(p.name)
    chk(not offenders, "S2 rumus haversine hanya di SSOT", f"masih ada di: {offenders}")

    selfie = (be / "routes/rahaza_auto_attendance_selfie.py").read_text(encoding="utf-8")
    chk("photo_b64[:20]" not in selfie,
        "S3 selfie tidak lagi disimpan terpotong 20 karakter")
    chk("save_selfie(" in selfie,
        "S4 selfie disimpan lewat SSOT `save_selfie` (storage lokal)")
    chk("enforce_attendance_policy" in selfie,
        "S5 clock-in & clock-out menegakkan kebijakan wajib",
        f"jumlah pemanggilan={selfie.count('enforce_attendance_policy(')}")
    chk(selfie.count("enforce_attendance_policy(db") >= 2,
        "S6 penegakan ada di KEDUA arah (masuk & pulang)")

    sess = (be / "routes/rahaza_attendance_sessions.py").read_text(encoding="utf-8")
    chk("is_session_counted" in sess and "APPROVAL_PENDING" in sess,
        "S7 sesi izin punya status persetujuan & hanya yang disetujui dihitung")

    seed = (be / "scripts/seed_role_accounts.py").read_text(encoding="utf-8")
    chk("load_dotenv" in seed,
        "S8 seeder akun role memuat .env (BUG-F16-5: dulu menulis ke DB salah)")

    # Semua modul absen memakai SSOT identitas (regresi FASE 15).
    bad = []
    for name in ("rahaza_attendance_permits.py", "rahaza_attendance_sessions.py",
                 "rahaza_auto_attendance_selfie.py"):
        src = (be / "routes" / name).read_text(encoding="utf-8")
        if not re.search(r"from utils\.employee_identity import", src):
            bad.append(name)
    chk(not bad, "S9 modul absen tetap memakai SSOT identitas", f"melanggar: {bad}")


# ═════════════════════════════════════════════════════════════════════════════
async def main() -> None:
    global FAIL
    static_checks()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "garment_erp")]
    today = date.today().isoformat()
    office_backup = await db.rahaza_office_locations.find_one({"is_primary": True})

    # Bersihkan jatah rate-limit login supaya skrip bisa dijalankan berulang.
    await db.rate_limit_buckets.delete_many({"key": {"$regex": "auth/login"}})

    selfie = make_selfie_b64()
    created_files: list[str] = []

    async with httpx.AsyncClient(timeout=90) as c:
        hr = await login(c, HR)
        staff = await login(c, STAFF)
        if not hr or not staff:
            print("\n  TIDAK BISA LOGIN — hentikan.")
            FAIL += 1
            return

        me_hr = (await c.get(f"{BASE}/api/rahaza/attendance/my-status", headers=hr)).json()
        me_staff = (await c.get(f"{BASE}/api/rahaza/attendance/my-status", headers=staff)).json()
        emp_hr = (me_hr.get("employee") or {}).get("id")
        emp_staff = (me_staff.get("employee") or {}).get("id")

        async def reset_today():
            await db.rahaza_attendance_events.delete_many(
                {"employee_id": {"$in": [emp_hr, emp_staff]}, "date": today})

        # ═════════════════════════════════════════════════════════════════
        sec("A. KONFIGURASI KANTOR — validasi & kebijakan tersimpan")
        # ═════════════════════════════════════════════════════════════════
        r = await c.put(f"{BASE}/api/rahaza/attendance/office-location", headers=hr,
                        json={"name": "Kantor Uji F16", "lat": OFFICE["lat"],
                              "lng": OFFICE["lng"], "geofence_radius_m": OFFICE["radius"],
                              "require_selfie": True, "require_geofence": True})
        chk(r.status_code == 200, "A1 HR bisa menyimpan lokasi kantor + kebijakan",
            f"HTTP {r.status_code}: {r.text[:120]}")

        r = await c.get(f"{BASE}/api/rahaza/attendance/office-location", headers=staff)
        cfg = r.json() if r.status_code == 200 else {}
        chk(cfg.get("configured") is True and cfg.get("require_selfie") is True,
            "A2 konfigurasi terbaca lengkap (configured/require_*)",
            f"configured={cfg.get('configured')} selfie={cfg.get('require_selfie')}")

        r = await c.put(f"{BASE}/api/rahaza/attendance/office-location", headers=hr,
                        json={"lat": 999, "lng": 0})
        chk(r.status_code == 400, "A3 koordinat di luar nalar ditolak", f"HTTP {r.status_code}")

        r = await c.put(f"{BASE}/api/rahaza/attendance/office-location", headers=hr,
                        json={"lat": OFFICE["lat"], "lng": OFFICE["lng"],
                              "geofence_radius_m": 3})
        chk(r.status_code == 400, "A4 radius tidak masuk akal ditolak", f"HTTP {r.status_code}")

        r = await c.put(f"{BASE}/api/rahaza/attendance/office-location", headers=staff,
                        json={"lat": 0, "lng": 0})
        chk(r.status_code == 403, "A5 non-HR tidak bisa mengubah lokasi kantor",
            f"HTTP {r.status_code}")

        # kembalikan konfigurasi uji yang benar
        await c.put(f"{BASE}/api/rahaza/attendance/office-location", headers=hr,
                    json={"name": "Kantor Uji F16", "lat": OFFICE["lat"],
                          "lng": OFFICE["lng"], "geofence_radius_m": OFFICE["radius"],
                          "require_selfie": True, "require_geofence": True})

        # ═════════════════════════════════════════════════════════════════
        sec("B. KEBIJAKAN WAJIB — selfie & lokasi (BUG-F16-1/2/3)")
        # ═════════════════════════════════════════════════════════════════
        await reset_today()
        url = f"{BASE}/api/rahaza/attendance/selfie/clock-in"

        r = await c.post(url, headers=staff, json={"do_face_check": False})
        chk(r.status_code == 400 and "Selfie" in r.text,
            "B1 absen tanpa selfie DITOLAK", f"HTTP {r.status_code}: {r.text[:90]}")

        r = await c.post(url, headers=staff,
                         json={"photo_base64": selfie, "do_face_check": False})
        chk(r.status_code == 400 and "GPS" in r.text,
            "B2 absen tanpa koordinat GPS DITOLAK", f"HTTP {r.status_code}: {r.text[:90]}")

        r = await c.post(url, headers=staff,
                         json={"photo_base64": selfie, "do_face_check": False, **FAR})
        chk(r.status_code == 403 and "ditolak" in r.text.lower(),
            "B3 absen di luar radius kantor DITOLAK", f"HTTP {r.status_code}: {r.text[:110]}")

        r = await c.post(url, headers=staff,
                         json={"photo_base64": "AAAA", "do_face_check": False, **NEAR})
        chk(r.status_code == 400, "B4 foto rusak/terlalu kecil DITOLAK",
            f"HTTP {r.status_code}: {r.text[:90]}")

        # kantor belum dikonfigurasi → pesan jelas, bukan lolos diam-diam
        await db.rahaza_office_locations.update_one(
            {"is_primary": True}, {"$set": {"lat": None, "lng": None}})
        r = await c.post(url, headers=staff,
                         json={"photo_base64": selfie, "do_face_check": False, **NEAR})
        chk(r.status_code == 409 and "Lokasi kantor belum diatur" in r.text,
            "B5 kantor belum diatur → 409 dengan langkah perbaikan",
            f"HTTP {r.status_code}: {r.text[:110]}")
        await db.rahaza_office_locations.update_one(
            {"is_primary": True}, {"$set": {"lat": OFFICE["lat"], "lng": OFFICE["lng"]}})

        r = await c.post(url, headers=staff,
                         json={"photo_base64": selfie, "do_face_check": False, **NEAR})
        ok_in = chk(r.status_code == 200, "B6 absen masuk di dalam radius DITERIMA",
                    f"HTTP {r.status_code}: {r.text[:120]}")

        rec = await db.rahaza_attendance_events.find_one(
            {"employee_id": emp_staff, "date": today}, {"_id": 0})
        purl = (rec or {}).get("photo_selfie_url") or ""
        chk(purl.startswith("/api/uploads/attendance/"),
            "B7 URL bukti selfie tersimpan (bukan potongan base64)", f"url={purl[:60]}")
        if purl:
            created_files.append(purl)
            rf = await c.get(f"{BASE}{purl}")
            chk(rf.status_code == 200 and len(rf.content) > 1024,
                "B8 file selfie benar-benar bisa dibuka",
                f"HTTP {rf.status_code} {len(rf.content)} bytes")
        else:
            chk(False, "B8 file selfie benar-benar bisa dibuka", "URL kosong")

        chk((rec or {}).get("geo_status") == "in_range"
            and (rec or {}).get("geo_distance_m") is not None,
            "B9 jarak & status geofence tercatat di record",
            f"status={(rec or {}).get('geo_status')} jarak={(rec or {}).get('geo_distance_m')}m")

        # ═════════════════════════════════════════════════════════════════
        sec("C. IZIN WAJIB DISETUJUI (BUG-F16-4)")
        # ═════════════════════════════════════════════════════════════════
        if not ok_in:
            chk(False, "C* dilewati", "absen masuk gagal")
        else:
            r = await c.post(f"{BASE}/api/rahaza/attendance/sessions/start",
                             headers=staff, json={"kind": "izin"})
            chk(r.status_code == 400, "C1 izin tanpa alasan ditolak", f"HTTP {r.status_code}")

            r = await c.post(f"{BASE}/api/rahaza/attendance/sessions/start", headers=staff,
                             json={"kind": "izin", "reason": "QA-F16 ke klinik", **NEAR})
            body = r.json() if r.status_code == 200 else {}
            sid = (body.get("session") or {}).get("id")
            chk(r.status_code == 200 and body.get("requires_approval") is True
                and (body.get("session") or {}).get("approval_status") == "pending"
                and (body.get("session") or {}).get("out_at") is None,
                "C2 izin masuk antrean PERSETUJUAN (belum keluar)",
                f"HTTP {r.status_code} status={(body.get('session') or {}).get('approval_status')}")

            r = await c.get(f"{BASE}/api/rahaza/attendance/sessions/active", headers=staff)
            act = r.json()
            chk(act.get("active") is None and (act.get("pending_permit") or {}).get("id") == sid,
                "C3 status: tidak ada sesi berjalan, ada pengajuan menunggu")

            # REGRESI (ditemukan lewat UI 2026-07-26): `my-status` memakai aturan
            # lama `if not in_at` sehingga pengajuan izin yang MASIH MENUNGGU
            # tampil sebagai kartu "Sedang IZIN keluar (disetujui)" dengan jam
            # keluar "--:--" di Portal Saya.
            r = await c.get(f"{BASE}/api/rahaza/attendance/my-status", headers=staff)
            ms = r.json()
            chk(ms.get("active_session") is None
                and (ms.get("pending_permit") or {}).get("id") == sid,
                "C3b my-status TIDAK menganggap izin pending sebagai sesi berjalan",
                f"active={bool(ms.get('active_session'))} pending={bool(ms.get('pending_permit'))}")

            r = await c.post(f"{BASE}/api/rahaza/attendance/sessions/end", headers=staff, json={})
            chk(r.status_code == 400 and "belum disetujui" in r.text,
                "C4 tidak bisa 'kembali kerja' sebelum izin disetujui",
                f"HTTP {r.status_code}: {r.text[:90]}")

            r = await c.post(f"{BASE}/api/rahaza/attendance/permits/{sid}/approve",
                             headers=staff, json={})
            chk(r.status_code == 403, "C5 karyawan tidak bisa menyetujui izinnya sendiri",
                f"HTTP {r.status_code}")

            r = await c.get(f"{BASE}/api/rahaza/attendance/permits?status=pending", headers=hr)
            ids = [i["id"] for i in (r.json().get("items") or [])]
            chk(r.status_code == 200 and sid in ids,
                "C6 pengajuan terlihat di daftar HR", f"total={r.json().get('total')}")

            r = await c.get(f"{BASE}/api/rahaza/attendance/permits/pending-count", headers=hr)
            chk(r.status_code == 200 and r.json().get("count", 0) >= 1,
                "C7 lencana jumlah menunggu tersedia", f"count={r.json().get('count')}")

            r = await c.post(f"{BASE}/api/rahaza/attendance/permits/{sid}/reject",
                             headers=hr, json={})
            chk(r.status_code == 400, "C8 penolakan tanpa alasan ditolak", f"HTTP {r.status_code}")

            r = await c.post(f"{BASE}/api/rahaza/attendance/permits/{sid}/approve",
                             headers=hr, json={"notes": "QA-F16 disetujui"})
            sd = (r.json() or {}).get("session") or {}
            chk(r.status_code == 200 and sd.get("approval_status") == "approved"
                and sd.get("out_at"),
                "C9 HR menyetujui → izin BERJALAN sejak persetujuan",
                f"HTTP {r.status_code} out_at={str(sd.get('out_at'))[:19]}")

            r = await c.post(f"{BASE}/api/rahaza/attendance/permits/{sid}/approve",
                             headers=hr, json={})
            chk(r.status_code == 400, "C10 tidak bisa menyetujui dua kali",
                f"HTTP {r.status_code}")

            await asyncio.sleep(1.2)
            r = await c.post(f"{BASE}/api/rahaza/attendance/sessions/end", headers=staff,
                             json=dict(NEAR))
            chk(r.status_code == 200, "C11 kembali kerja menutup sesi izin",
                f"HTTP {r.status_code}: {r.text[:90]}")

            # ── izin DITOLAK tidak boleh memotong jam kerja ──────────────
            r = await c.post(f"{BASE}/api/rahaza/attendance/sessions/start", headers=staff,
                             json={"kind": "izin", "reason": "QA-F16 izin ditolak", **NEAR})
            sid2 = ((r.json() or {}).get("session") or {}).get("id")
            r = await c.post(f"{BASE}/api/rahaza/attendance/permits/{sid2}/reject",
                             headers=hr, json={"notes": "QA-F16 tidak mendesak"})
            chk(r.status_code == 200
                and ((r.json() or {}).get("session") or {}).get("approval_status") == "rejected",
                "C12 HR menolak izin", f"HTTP {r.status_code}")

            rec = await db.rahaza_attendance_events.find_one(
                {"employee_id": emp_staff, "date": today}, {"_id": 0})
            rejected = [s for s in (rec.get("sessions") or [])
                        if s.get("approval_status") == "rejected"]
            chk(rejected and not rejected[0].get("out_at"),
                "C13 izin ditolak tidak punya jam keluar (tidak dihitung)")

            # ── pembatalan oleh pemohon ─────────────────────────────────
            r = await c.post(f"{BASE}/api/rahaza/attendance/sessions/start", headers=staff,
                             json={"kind": "izin", "reason": "QA-F16 dibatalkan", **NEAR})
            sid3 = ((r.json() or {}).get("session") or {}).get("id")
            r = await c.post(f"{BASE}/api/rahaza/attendance/permits/{sid3}/cancel",
                             headers=staff, json={})
            chk(r.status_code == 200, "C14 pemohon bisa membatalkan pengajuannya",
                f"HTTP {r.status_code}: {r.text[:90]}")

            # ── istirahat tetap langsung (tanpa approval) ────────────────
            r = await c.post(f"{BASE}/api/rahaza/attendance/sessions/start", headers=staff,
                             json={"kind": "istirahat", **NEAR})
            b = r.json() if r.status_code == 200 else {}
            chk(r.status_code == 200 and b.get("requires_approval") is False
                and (b.get("session") or {}).get("out_at"),
                "C15 ISTIRAHAT tetap langsung jalan (tanpa persetujuan)",
                f"HTTP {r.status_code}")
            await asyncio.sleep(1.2)
            await c.post(f"{BASE}/api/rahaza/attendance/sessions/end", headers=staff,
                         json=dict(NEAR))

        # ═════════════════════════════════════════════════════════════════
        sec("D. JAM BERSIH & PULANG")
        # ═════════════════════════════════════════════════════════════════
        r = await c.post(f"{BASE}/api/rahaza/attendance/selfie/clock-out", headers=staff,
                         json={"photo_base64": selfie, **NEAR})
        chk(r.status_code == 200, "D1 absen pulang (selfie+lokasi wajib) DITERIMA",
            f"HTTP {r.status_code}: {r.text[:110]}")

        rec = await db.rahaza_attendance_events.find_one(
            {"employee_id": emp_staff, "date": today}, {"_id": 0})
        out_url = (rec or {}).get("photo_selfie_out_url") or ""
        chk(out_url.startswith("/api/uploads/attendance/"),
            "D2 selfie PULANG juga tersimpan (dulu dibuang)", f"url={out_url[:60]}")
        if out_url:
            created_files.append(out_url)

        counted = [s for s in (rec or {}).get("sessions") or []
                   if s.get("approval_status") in (None, "approved", "not_required")
                   and s.get("in_at")]
        chk((rec or {}).get("permit_minutes", 0) >= 0
            and (rec or {}).get("net_hours_worked") is not None,
            "D3 turunan jam bersih tersimpan",
            f"kotor={(rec or {}).get('hours_worked')} net={(rec or {}).get('net_hours_worked')} "
            f"istirahat={(rec or {}).get('break_minutes')}m izin={(rec or {}).get('permit_minutes')}m "
            f"sesi_dihitung={len(counted)}")

        rejected_minutes = sum(int(s.get("minutes") or 0)
                               for s in (rec or {}).get("sessions") or []
                               if s.get("approval_status") in ("rejected", "cancelled"))
        chk(rejected_minutes == 0,
            "D4 sesi ditolak/dibatalkan bernilai 0 menit", f"total={rejected_minutes}")

        # ═════════════════════════════════════════════════════════════════
        sec("E. REKAP HR + EXPORT EXCEL")
        # ═════════════════════════════════════════════════════════════════
        r = await c.get(f"{BASE}/api/rahaza/attendance/sessions"
                        f"?from_date={today}&to_date={today}", headers=hr)
        d = r.json() if r.status_code == 200 else {}
        chk(r.status_code == 200 and d.get("total", 0) >= 1 and "summary" in d,
            "E1 rekap sesi + ringkasan tersedia untuk HR",
            f"total={d.get('total')} summary={d.get('summary')}")

        r = await c.get(f"{BASE}/api/rahaza/attendance/sessions"
                        f"?from_date={today}&to_date={today}&kind=izin&status=rejected",
                        headers=hr)
        chk(r.status_code == 200 and all(i["kind"] == "izin" and
                                         i["approval_status"] == "rejected"
                                         for i in r.json().get("items", [])),
            "E2 filter jenis + status bekerja", f"n={r.json().get('total')}")

        r = await c.get(f"{BASE}/api/rahaza/attendance/sessions/export.xlsx"
                        f"?from_date={today}&to_date={today}", headers=hr)
        ct = r.headers.get("content-type", "")
        chk(r.status_code == 200 and "spreadsheet" in ct and len(r.content) > 4000,
            "E3 export Excel terbentuk", f"HTTP {r.status_code} {len(r.content)}B {ct[:40]}")
        if r.status_code == 200:
            try:
                from openpyxl import load_workbook
                wsx = load_workbook(io.BytesIO(r.content)).active
                head = [cell.value for cell in wsx[5]]
                chk("Status" in head and "Alasan" in head,
                    "E4 kolom Excel lengkap (Status & Alasan)", f"header={head[:6]}…")
            except Exception as e:  # noqa: BLE001
                chk(False, "E4 kolom Excel lengkap", str(e)[:80])

        r = await c.get(f"{BASE}/api/rahaza/attendance/sessions", headers=staff)
        own = {i["employee_id"] for i in r.json().get("items", [])}
        chk(r.status_code == 200 and own <= {emp_staff},
            "E5 karyawan hanya melihat rekap MILIKNYA", f"employee_ids={own}")

    # ═════════════════════════════════════════════════════════════════════
    sec("F. PEMBERSIHAN ARTEFAK UJI")
    # ═════════════════════════════════════════════════════════════════════
    n = (await db.rahaza_attendance_events.delete_many(
        {"employee_id": {"$in": [emp_hr, emp_staff]}, "date": today})).deleted_count
    print(f"  – rahaza_attendance_events: {n}")
    nn = (await db.notifications.delete_many(
        {"subtype": {"$in": ["attendance_permit_request", "attendance_permit_decision"]}}
    )).deleted_count
    print(f"  – notifications: {nn}")
    for u in created_files:
        p = Path("/app/uploads") / u.replace("/api/uploads/", "")
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
    print(f"  – file selfie uji: {len(created_files)}")
    if office_backup:
        office_backup.pop("_id", None)
        await db.rahaza_office_locations.update_one(
            {"is_primary": True}, {"$set": office_backup}, upsert=True)
        print("  – konfigurasi kantor dikembalikan")
    else:
        await db.rahaza_office_locations.delete_many({"is_primary": True})
        print("  – konfigurasi kantor uji dihapus")

    sec("RINGKASAN")
    print(f"  {PASS} PASS / {FAIL} FAIL")
    if FAILED:
        for f in FAILED:
            print(f"    ✗ {f}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(1 if FAIL else 0)
