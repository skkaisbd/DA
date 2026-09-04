#!/usr/bin/env python3
"""VERIFIKASI: status keputusan style RnD tidak bisa ditimpa lewat form edit.

LUBANG ALUR YANG DITUTUP (2026-08-07)
------------------------------------
`PUT /api/dewi/rnd/styles/{id}` dulu menerima `status` apa pun, sehingga:
  · siapa pun yang boleh menyunting style bisa menulis `approved_for_launch`
    langsung → keputusan owner terlewati, tanpa pemutus & tanpa alasan;
  · style yang sedang direview bisa ditarik kembali ke `draft` tanpa jejak.
Sekarang status siklus hidup HANYA berpindah lewat pintunya:
  submit-for-review · owner-approve · owner-reject.

ATURAN SKRIP INI: **tidak menyentuh data demo.** Semua uji memakai style
buangan `ZZ-VERIFY-*` yang dibuat lalu dihapus sendiri. Di akhir, status 4 style
demo hanya DIPERIKSA (bukan diubah).

Jalankan: API_URL=http://localhost:8001 python3 /app/scripts/verify_rnd_style_status_guard.py
"""
import os
import sys

import requests

BASE_URL = os.environ.get("API_URL", "http://localhost:8001")
ok = fail = 0

DEMO_EXPECTED = {
    "MK-JKT-RND": "draft",
    "DA-TS01-RND": "draft",
    "DA-HD02-RND": "pending_owner_review",
    "DA-PL03-RND": "approved_for_launch",
}


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS · {label}")
    else:
        fail += 1
        print(f"  FAIL · {label} {extra}")


def login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        print(f"  ! login {email} gagal: {r.status_code} {r.text[:120]}")
        return None
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


def make_style(H, code, name="Style verifikasi gerbang status"):
    r = requests.post(f"{BASE_URL}/api/dewi/rnd/styles", headers=H,
                      json={"style_code": code, "style_name": name}, timeout=30)
    if r.status_code not in (200, 201):
        return None
    return r.json()


def drop_style(H, sid):
    requests.delete(f"{BASE_URL}/api/dewi/rnd/styles/{sid}", headers=H, timeout=30)


def put(H, sid, body):
    r = requests.put(f"{BASE_URL}/api/dewi/rnd/styles/{sid}", headers=H, json=body, timeout=30)
    detail = ""
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", "")
        except ValueError:
            detail = r.text[:120]
    return r.status_code, detail, (r.json() if r.status_code < 400 else {})


def main():
    admin = login("admin@garment.com", "Admin@123")
    if not admin:
        print("Tidak bisa login admin — hentikan.")
        return 1
    hr = login("hr@dewiaditya.id", "Dewi@123")

    print("1. Form edit tidak boleh menyentuh status keputusan")
    draft = make_style(admin, "ZZ-VERIFY-DRAFT")
    if not draft:
        print("  ! gagal membuat style buangan")
        return 1
    try:
        code, detail, _ = put(admin, draft["id"], {"status": "approved_for_launch"})
        check("draft → approved_for_launch ditolak 403", code == 403, f"{code} {detail[:90]}")
        code, detail, _ = put(admin, draft["id"], {"status": "wakanda"})
        check("status ngawur ditolak 400", code == 400, f"{code} {detail[:90]}")
        code, _, body = put(admin, draft["id"], {"status": "archived"})
        check("draft → archived boleh (200)", code == 200 and body.get("status") == "archived", str(code))
        code, _, body = put(admin, draft["id"], {"status": "draft"})
        check("archived → draft boleh (200)", code == 200 and body.get("status") == "draft", str(code))
        code, _, body = put(admin, draft["id"], {"description": "sunting biasa", "status": "draft"})
        check("sunting field biasa tetap boleh (200)",
              code == 200 and body.get("description") == "sunting biasa", str(code))

        print("2. Style yang sedang direview terlindungi")
        r = requests.post(f"{BASE_URL}/api/dewi/rnd/styles/{draft['id']}/submit-for-review",
                          headers=admin, json={"notes": "verifikasi"}, timeout=30)
        check("submit-for-review menaikkan status ke pending_owner_review",
              r.status_code == 200 and r.json().get("status") == "pending_owner_review",
              f"{r.status_code} {r.text[:90]}")
        code, detail, _ = put(admin, draft["id"], {"status": "draft"})
        check("pending → draft lewat form edit ditolak 403", code == 403, f"{code} {detail[:90]}")
        code, _, body = put(admin, draft["id"], {"description": "boleh diubah",
                                                 "status": "pending_owner_review"})
        check("field lain masih bisa disunting saat menunggu keputusan",
              code == 200 and body.get("status") == "pending_owner_review", str(code))

        print("3. Keputusan hanya milik owner/admin")
        if hr:
            r = requests.post(f"{BASE_URL}/api/dewi/rnd/styles/{draft['id']}/owner-approve",
                              headers=hr, json={"notes": "coba"}, timeout=30)
            check("hr tidak bisa owner-approve → 403", r.status_code == 403, str(r.status_code))
            r = requests.post(f"{BASE_URL}/api/dewi/rnd/styles/{draft['id']}/owner-reject",
                              headers=hr, json={"notes": "coba"}, timeout=30)
            check("hr tidak bisa owner-reject → 403", r.status_code == 403, str(r.status_code))
        r = requests.post(f"{BASE_URL}/api/dewi/rnd/styles/{draft['id']}/owner-approve",
                          headers=admin, json={"notes": "verifikasi setuju"}, timeout=30)
        check("admin bisa owner-approve (draft → pending → approved_for_launch)",
              r.status_code == 200 and r.json().get("status") == "approved_for_launch",
              f"{r.status_code} {r.text[:90]}")
        code, detail, _ = put(admin, draft["id"], {"status": "draft"})
        check("style yang sudah disetujui tidak bisa dikembalikan lewat form edit → 403",
              code == 403, f"{code} {detail[:90]}")
    finally:
        drop_style(admin, draft["id"])
        print("  · style buangan dihapus")

    print("4. Data demo tidak berubah")
    r = requests.get(f"{BASE_URL}/api/dewi/rnd/styles?limit=50", headers=admin, timeout=30)
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    actual = {s["style_code"]: s["status"] for s in rows if s.get("style_code") in DEMO_EXPECTED}
    for code_, want in DEMO_EXPECTED.items():
        check(f"{code_} tetap {want}", actual.get(code_) == want, f"sekarang {actual.get(code_)}")
    check("tidak ada style buangan tertinggal",
          not [s for s in rows if str(s.get("style_code", "")).startswith("ZZ-VERIFY")])

    print(f"\n== {ok} PASS / {fail} FAIL ==")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
