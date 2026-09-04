#!/usr/bin/env python3
"""_verify_f4_health_after_import.py — bukti F4: skor sehat 1–5 TERISI sesudah impor.

Alur: login → impor berkas contoh (upload+commit) → hitung ulang skor →
periksa `health_score`/`health_grade`/`health_label`/`health_breakdown` toko
TIKTOK-OUTFIT → **rollback** supaya data seed kembali bersih.

Kenapa perlu: layar Manajemen Akun menampilkan bintang dari 4 field itu. Kalau
`health_breakdown` kosong, tooltip "kenapa skornya segitu" jadi kosong dan
pemilik toko tidak bisa menindaklanjuti apa pun.
"""
from __future__ import annotations

import sys
import requests

BASE = "http://localhost:8001"
SAMPLE = "/app/samples/TikTok_UntukDikirim_2026-07-19.xlsx"
CODE = "TIKTOK-OUTFIT"
FAILED: list[str] = []


def check(name: str, cond, detail: str = "") -> bool:
    mark = "\033[92mPASS\033[0m" if cond else "\033[91mFAIL\033[0m"
    print(f"  {mark}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)
    return bool(cond)


def main() -> int:
    tok = requests.post(f"{BASE}/api/auth/login", json={
        "email": "admin@garment.com", "password": "Admin@123"}, timeout=30).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}

    accs = requests.get(f"{BASE}/api/marketing/accounts", headers=H, timeout=30).json()
    accs = accs.get("accounts", accs) if isinstance(accs, dict) else accs
    acc = next((a for a in accs if a.get("account_code") == CODE), None)
    if not check("toko TIKTOK-OUTFIT ada", acc is not None):
        return 1
    aid = acc["id"]

    with open(SAMPLE, "rb") as fh:
        up = requests.post(
            f"{BASE}/api/marketing/data-import/upload", headers=H,
            files={"file": (SAMPLE.rsplit("/", 1)[-1], fh,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"source_type": "marketplace_orders", "account_id": aid}, timeout=300)
    if not check("upload 200", up.status_code == 200, str(up.status_code)):
        print(up.text[:500])
        return 1
    sid = up.json()["session"]["id"]

    cm = requests.post(f"{BASE}/api/marketing/data-import/sessions/{sid}/commit",
                       headers=H, json={"on_duplicate": "skip"}, timeout=300)
    check("commit 200 · 559 pesanan masuk",
          cm.status_code == 200 and cm.json().get("inserted") == 559,
          f"{cm.status_code} inserted={cm.json().get('inserted') if cm.status_code == 200 else '-'}")

    try:
        rc = requests.post(f"{BASE}/api/marketing/accounts/health/recompute-all",
                           headers=H, timeout=180)
        check("hitung ulang skor 200", rc.status_code == 200,
              f"scored={rc.json().get('scored')} no_data={rc.json().get('no_data')}")

        accs2 = requests.get(f"{BASE}/api/marketing/accounts", headers=H, timeout=30).json()
        accs2 = accs2.get("accounts", accs2) if isinstance(accs2, dict) else accs2
        a2 = next((a for a in accs2 if a.get("account_code") == CODE), {})
        score, grade = a2.get("health_score"), a2.get("health_grade")
        label, bd = a2.get("health_label"), a2.get("health_breakdown") or {}

        check("skor 0–100 terisi (bukan None)", isinstance(score, (int, float)), str(score))
        check("grade dalam SKALA 1–5", grade in (1, 2, 3, 4, 5), str(grade))
        check("label bukan 'Belum ada data'",
              bool(label) and label != "Belum ada data", str(label))
        pillars = {"sales", "fulfillment", "satisfaction", "engagement", "compliance"}
        check("rincian pilar lengkap (5 pilar)", pillars.issubset(set(bd.keys())),
              ",".join(sorted(bd.keys())))
        check("setiap pilar punya nilai & bobot",
              all(isinstance(bd.get(p), dict) and "score" in bd[p] and "max" in bd[p]
                  for p in pillars if p in bd),
              str({k: bd.get(k) for k in list(pillars)[:2]})[:200])
        check("hari berdata dicatat", (a2.get("health_days_with_data") or 0) > 0,
              str(a2.get("health_days_with_data")))
    finally:
        rb = requests.post(f"{BASE}/api/marketing/data-import/sessions/{sid}/rollback",
                           headers=H, timeout=300)
        print(f"  (bersih-bersih rollback: {rb.status_code} "
              f"deleted={rb.json().get('deleted') if rb.status_code == 200 else '-'})")
        requests.post(f"{BASE}/api/marketing/accounts/health/recompute-all", headers=H, timeout=180)

    print()
    if FAILED:
        print(f"\033[91mGAGAL: {len(FAILED)}\033[0m — {FAILED}")
        return 1
    print("\033[92mSEMUA PASS — F4 skor sehat 1–5 + rincian pilar terbukti\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
