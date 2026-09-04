#!/usr/bin/env python3
"""seed_uji_belanja_mingguan.py — data periksa untuk 3 layar sesi #33.

KENAPA ADA
----------
Di container segar **0 dari 335 material punya ambang**, jadi layar *Daftar
Belanja Mingguan* & *Alert & Reorder* memang KOSONG apa adanya (dan mengatakan
kenapa). Supaya pemilik/penguji bisa MELIHAT ketiga layar bekerja dengan data
NYATA, skrip ini memasang ambang pada beberapa barang yang benar-benar ada
stoknya — memakai endpoint resmi `bulk-fill` (bukan menulis langsung ke Mongo),
sehingga `threshold_basis`/siapa/kapan ikut tercatat seperti pemakaian sungguhan.

Rumusnya sengaja dipilih supaya keadaannya beragam:
  · `percent_onhand 100`  ⇒ ambang = stok, titik pesan ulang = 1,2 × stok
    ⇒ barang MASUK daftar belanja dengan kekurangan 20% dari stok (keadaan
      "perlu pesan ulang" yang wajar, bukan angka karangan)
  · `percent_onhand 50`   ⇒ ambang di bawah stok ⇒ barang AMAN (tidak diusulkan)
  · satu barang tanpa harga (`unit_cost = 0`) diikutkan bila ada, supaya layar
    memperlihatkan status **belum berharga**

Pakai:
  python3 scripts/seed_uji_belanja_mingguan.py            # pasang
  python3 scripts/seed_uji_belanja_mingguan.py --cleanup   # kosongkan lagi
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("API_BASE", "http://localhost:8001")
G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
CLEANUP = "--cleanup" in sys.argv
NEED = 6      # barang yang dibuat "perlu pesan ulang"
SAFE = 3      # barang yang dibuat "aman"


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {"raw": raw[:300].decode(errors="ignore")}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def main():
    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}login gagal HTTP {st}{X}")
        return 2

    st, thl = call("GET", "/api/rahaza/stock-thresholds?limit=2000", token)
    rows = (thl or {}).get("items") or []
    if st != 200 or not rows:
        print(f"{R}tidak bisa membaca daftar ambang (HTTP {st}){X}")
        return 1

    if CLEANUP:
        seeded = [r["material_id"] for r in rows
                  if r.get("has_threshold") and r.get("threshold_basis") == "percent_onhand"]
        if not seeded:
            print(f"{Y}tidak ada ambang hasil seed (`percent_onhand`) yang perlu dibersihkan{X}")
            return 0
        st, res = call("POST", "/api/rahaza/stock-thresholds/bulk-clear", token,
                       {"material_ids": seeded})
        print(f"{G}{res.get('cleared', 0)} ambang hasil seed dikosongkan{X} "
              f"(sisa berambang: {(res.get('summary') or {}).get('with_threshold')})")
        return 0 if st == 200 else 1

    with_stock = [r for r in rows if float(r.get("onhand") or 0) > 0
                  and not r.get("has_threshold")]
    valued = [r for r in with_stock if float(r.get("unit_cost") or 0) > 0]
    unvalued = [r for r in with_stock if float(r.get("unit_cost") or 0) <= 0]
    if not valued:
        print(f"{Y}semua barang berstok sudah punya ambang — tidak ada yang perlu diseed{X}")
        return 0

    need = valued[:NEED] + unvalued[:1]
    safe = valued[NEED:NEED + SAFE]
    out = []
    for label, group, pct in (("perlu pesan ulang", need, 100), ("aman", safe, 50)):
        if not group:
            continue
        st, res = call("POST", "/api/rahaza/stock-thresholds/bulk-fill", token, {
            "mode": "percent_onhand", "dry_run": False, "params": {"percent": pct},
            "scope": {"material_ids": [r["material_id"] for r in group]}})
        if st != 200:
            print(f"{R}gagal memasang ambang ({label}) HTTP {st}: "
                  f"{str(res)[:200]}{X}")
            return 1
        out.append(f"{res.get('applied')} barang → {label} ({pct}% dari stok)")

    st, wk = call("GET", "/api/rahaza/shopping-list/weekly", token)
    s = (wk or {}).get("summary") or {}
    print(f"{G}{B}SELESAI{X} — " + " · ".join(out))
    print(f"  {C}Daftar Belanja Mingguan sekarang: {s.get('need_buy')} barang perlu dibeli · "
          f"perkiraan {s.get('est_total_value')} · {s.get('unvalued_count')} belum berharga · "
          f"{s.get('without_threshold')} belum berambang{X}")
    print(f"  {Y}Buka: #wh-shopping-list · #wh-cost-history · #wh-master (tab Ambang Stok){X}")
    print(f"  {Y}Bersihkan lagi: python3 scripts/seed_uji_belanja_mingguan.py --cleanup{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
