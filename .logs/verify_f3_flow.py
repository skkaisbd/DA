#!/usr/bin/env python3
"""Verifikasi cepat berkas contoh Ekspor A/B/C lewat API (bukan pengganti gate).

Tujuan: memastikan berkas di /app/samples benar-benar bisa dipakai staf & agen
uji di layar — bukan hanya "ada di folder".
"""
import json
import sys

import requests

BASE = "http://localhost:8001"
API = f"{BASE}/api/marketing/data-import"
tok = open("/app/.logs/admin_token.txt").read().strip()
H = {"Authorization": f"Bearer {tok}"}
JH = {**H, "Content-Type": "application/json"}

accs = requests.get(f"{BASE}/api/marketing/accounts", headers=H,
                    params={"status": "active"}, timeout=60).json()
accs = accs if isinstance(accs, list) else (accs.get("accounts") or [])
acc = next(a for a in accs if a.get("platform") == "shopee")
print("TOKO:", acc["account_name"], acc["id"])


def upload(path, stype):
    with open(path, "rb") as fh:
        r = requests.post(f"{API}/upload", headers=H, timeout=180,
                          files={"file": (path.split("/")[-1], fh, "text/csv")},
                          data={"source_type": stype, "account_id": acc["id"]})
    if r.status_code != 200:
        print("  UPLOAD GAGAL", r.status_code, r.text[:400])
        return None, None
    d = r.json()
    return d, d["session"]["id"]


def show(d, label):
    s = d["session"]
    rep = s.get("mapping_report") or {}
    print(f"\n== {label}")
    print("   kolom terpetakan:", rep.get("mapped"), "/", rep.get("total_columns"),
          "| siap:", rep.get("ready"), "| wajib hilang:", rep.get("missing_required"))
    print("   metode:", rep.get("methods"))
    print("   ringkasan baris:", d.get("summary"))
    prev = d.get("preview") or []
    if prev:
        o = prev[0].get("original") or {}
        print("   CONTOH ISI (dipakai kolom 'Contoh isi' layar):",
              {k: o[k] for k in list(o)[:4]})
    for m in s.get("mapping") or []:
        if not m.get("field"):
            print("   TAK DIPAKAI:", m["column"], "usulan:",
                  [(c["field"], c["score"]) for c in (m.get("candidates") or [])])
    return prev


mode = sys.argv[1] if len(sys.argv) > 1 else "all"

if mode in ("all", "a"):
    d, sid = upload("/app/samples/ekspor_A_pesanan_contoh.csv", "marketplace_orders")
    if not d:
        sys.exit(1)
    show(d, "EKSPOR A — pesanan")
    rc = requests.post(f"{API}/sessions/{sid}/commit", headers=JH, timeout=180,
                       json={"on_duplicate": "update"})
    print("   COMMIT A:", rc.status_code, json.dumps(rc.json(), ensure_ascii=False)[:400]
          if rc.status_code == 200 else rc.text[:400])

if mode in ("all", "b"):
    d, sid = upload("/app/samples/ekspor_B_status_dikirim_contoh.csv",
                    "marketplace_fulfillment")
    if not d:
        sys.exit(1)
    show(d, "EKSPOR B — status pengiriman (update_only)")
    print("   (tidak di-commit; sesi ini dibiarkan siap untuk uji layar)")
