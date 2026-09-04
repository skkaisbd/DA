#!/usr/bin/env python3
"""INV-F43 (sesi #37) — **MARGIN KATALOG: 0% / 100% TIDAK PERNAH DIKARANG**.

Yang diukur SEBELUM sesi ini (bukan dugaan): `marketing_catalog_items` berisi 78
item dan **tidak satu pun** punya `margin_pct`; `hpp` hanya terisi di 10 item.
Endpoint daftar katalog memang menghitung margin saat baca, tetapi dengan rumus
`(harga_jual - hpp) / harga_jual` tanpa memeriksa apakah `hpp` DIKETAHUI — jadi:

    hpp = 0  ⇒  margin 100%      (item yang untung-ruginya TIDAK diketahui
                                  justru tampil sebagai yang paling aman didiskon)
    harga_jual = 0  ⇒  margin 0%

Yang dijaga gate ini:
 A. HPP tidak diketahui ⇒ `margin_status='belum_bisa_diukur'`, `margin_pct=None`
    — **bukan 0, bukan 100** — dan alasannya ditulis.
 B. HPP EFEKTIF mengikuti urutan `hpp_fifo_avg` FG → `hpp` FG → `hpp` katalog,
    dan sumbernya dilaporkan (`hpp_source_effective`).
 C. Ringkasan katalog tidak memasukkan item "belum bisa diukur" ke rata-rata.
 D. Layar tidak pernah mencetak "0%"/"100%" untuk item tanpa HPP (statik:
    setiap tempat yang menampilkan `margin_pct` menjaga `margin_status`).

Skrip ini MEMBERSIHKAN artefaknya sendiri (katalog + item + FG uji).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

API = os.environ.get("API_BASE", "http://localhost:8001")
G, R, C, B, X = "\033[92m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
PASS: list[str] = []
FAIL: list[str] = []
STAMP = time.strftime("%H%M%S")
TAG = f"GATE43-{STAMP}"


def ok(code, msg, detail=""):
    PASS.append(code)
    print(f"  {G}✓ {code}{X} {msg}" + (f"\n         {C}{detail}{X}" if detail else ""))


def bad(code, msg, detail=""):
    FAIL.append(code)
    print(f"  {R}✗ {code} {msg}{X}" + (f"\n         {detail}" if detail else ""))


def head(t):
    print(f"\n{C}{B}▶ {t}{X}")


def det(d):
    return json.dumps(d, ensure_ascii=False, default=str)[:300]


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


def main() -> int:  # noqa: C901
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        bad("SETUP", f"login admin gagal (HTTP {st})", det(d))
        return 1

    cat_id = f"{TAG}-cat"
    fg_id = str(uuid.uuid4())
    items = [
        # (suffix, harga_jual, hpp katalog, tertaut FG?)
        ("NOHPP", 200_000, 0, False),
        ("MANUAL", 200_000, 120_000, False),
        ("FGFIFO", 200_000, 120_000, True),      # FG punya hpp_fifo_avg 150k
        ("NOPRICE", 0, 120_000, False),
    ]
    try:
        db.marketing_catalogs.insert_one({
            "id": cat_id, "name": f"{TAG} Katalog Uji", "account_id": "",
            "platform": "shopee", "notes": TAG})
        db.rahaza_materials.insert_one({
            "id": fg_id, "code": f"{TAG}-FG", "name": f"{TAG} FG",
            "type": "fg", "hpp": 130_000, "hpp_fifo_avg": 150_000,
            "hpp_source": "fifo_batch", "notes": TAG})
        for suffix, hj, hpp, linked in items:
            db.marketing_catalog_items.insert_one({
                "id": f"{TAG}-{suffix}", "catalog_id": cat_id,
                "sku": f"{TAG}-{suffix}", "name": f"{TAG} {suffix}",
                "harga_jual": hj, "price": hj, "hpp": hpp,
                "is_active": True, "stock_quantity": 0,
                "fg_material_id": fg_id if linked else None,
                "fg_code": f"{TAG}-FG" if linked else "",
                "notes": TAG,
            })

        st, r = call("GET", f"/api/marketing/catalogs/{cat_id}/items?limit=50", token)
        if st != 200:
            bad("SETUP", f"daftar katalog gagal (HTTP {st})", det(r))
            return 1
        rows = {i["sku"].rsplit("-", 1)[-1]: i for i in r.get("items", [])}
        if len(rows) != len(items):
            bad("SETUP", f"hanya {len(rows)} dari {len(items)} item uji terbaca",
                det(sorted(rows)))
            return 1

        # ══ A. TIDAK DIKETAHUI ⇒ DIKATAKAN ════════════════════════════════════
        head("A — HPP TIDAK DIKETAHUI ⇒ 'belum bisa diukur', BUKAN 0% / 100%")

        it = rows["NOHPP"]
        if (it.get("margin_status") == "belum_bisa_diukur"
                and it.get("margin_pct") is None and it.get("margin") is None):
            ok("A1", "item tanpa HPP: margin_pct=None + status 'belum_bisa_diukur' "
                     "(dulu 100%)")
        else:
            bad("A1", "item tanpa HPP masih dikirim sebagai angka",
                det({k: it.get(k) for k in ("hpp_effective", "margin", "margin_pct",
                                            "margin_status")}))
        if (it.get("margin_reason") or "").lower().startswith("belum bisa diukur"):
            ok("A2", "alasannya ditulis, bukan hanya statusnya", det(it["margin_reason"]))
        else:
            bad("A2", "tidak ada alasan kenapa margin tidak bisa diukur",
                det(it.get("margin_reason")))

        it = rows["NOPRICE"]
        if it.get("margin_status") == "belum_bisa_diukur" and it.get("margin_pct") is None:
            ok("A3", "harga jual belum diisi juga 'belum bisa diukur' (dulu 0%)")
        else:
            bad("A3", "harga jual 0 masih menghasilkan angka margin",
                det({k: it.get(k) for k in ("margin_pct", "margin_status")}))

        # ══ B. HPP EFEKTIF & SUMBERNYA ════════════════════════════════════════
        head("B — HPP EFEKTIF: lapisan FIFO FG → HPP FG → HPP katalog, sumber dilaporkan")

        it = rows["MANUAL"]
        if (it.get("hpp_effective") == 120_000
                and it.get("hpp_source_effective") == "catalog_manual"
                and it.get("margin_pct") == 40.0):
            ok("B1", "HPP ketikan katalog dipakai bila tidak ada FG; margin 40%")
        else:
            bad("B1", "HPP katalog tidak dipakai / margin salah",
                det({k: it.get(k) for k in ("hpp_effective", "hpp_source_effective",
                                            "margin_pct")}))

        it = rows["FGFIFO"]
        if (it.get("hpp_effective") == 150_000
                and it.get("hpp_source_effective") == "fg_fifo_avg"):
            ok("B2", "lapisan FIFO FG (150.000) MENGALAHKAN hpp FG (130.000) dan "
                     "hpp katalog (120.000) — urutan sesuai keputusan pemilik")
        else:
            bad("B2", "urutan HPP efektif tidak dipatuhi",
                det({k: it.get(k) for k in ("hpp_effective", "hpp_source_effective")}))
        if it.get("margin_pct") == 25.0:
            ok("B3", "margin dihitung dari HPP efektif (200.000−150.000 = 25%)")
        else:
            bad("B3", f"margin memakai HPP yang salah (margin_pct={it.get('margin_pct')})")

        # ══ C. RINGKASAN JUJUR ════════════════════════════════════════════════
        head("C — RATA-RATA MARGIN TIDAK DIRACUNI ITEM YANG TIDAK TERUKUR")

        ms = r.get("margin_summary") or {}
        if ms.get("measurable") == 2 and ms.get("unmeasurable") == 2:
            ok("C1", "2 terukur / 2 belum bisa diukur dilaporkan terpisah")
        else:
            bad("C1", "hitungan terukur vs tidak terukur salah", det(ms))
        if ms.get("avg_margin_pct") == 32.5:
            ok("C2", "rata-rata margin = (40+25)/2 = 32,5% — item tak terukur TIDAK "
                     "ikut sebagai 0% atau 100%")
        else:
            bad("C2", f"rata-rata margin salah ({ms.get('avg_margin_pct')}); "
                      f"kalau item tak terukur ikut, angkanya akan 16,25% atau 66,25%")
        if (ms.get("hpp_sources") or {}) == {"catalog_manual": 2, "fg_fifo_avg": 1,
                                             "none": 1}:
            ok("C3", "sumber HPP dilaporkan per kategori", det(ms.get("hpp_sources")))
        else:
            bad("C3", "sumber HPP tidak dilaporkan", det(ms.get("hpp_sources")))

        # ══ D. LAYAR TIDAK MENCETAK ANGKA KARANGAN ════════════════════════════
        head("D — LAYAR MENJAGA margin_status SEBELUM MENCETAK PERSEN")

        fe = ROOT / "frontend" / "src" / "components" / "erp" / "marketing" / "CatalogItemsView.jsx"
        src = fe.read_text(encoding="utf-8")
        if "belum_bisa_diukur" in src and "belum bisa diukur" in src:
            ok("D1", "CatalogItemsView menampilkan lencana 'belum bisa diukur'")
        else:
            bad("D1", "layar katalog masih mencetak margin_pct tanpa penjaga status")
        rnd = ROOT / "frontend" / "src" / "components" / "erp" / "RnDProductViewer.jsx"
        if "belum bisa diukur" in rnd.read_text(encoding="utf-8"):
            ok("D2", "RnDProductViewer juga mengatakannya, bukan mengosongkan kolom")
        else:
            bad("D2", "RnDProductViewer membiarkan kolom margin kosong tanpa penjelasan")

        # Endpoint pencarian katalog (dipakai form pesanan) memakai rumus yang sama.
        search = ROOT / "backend" / "routes" / "marketing_catalog_search.py"
        s2 = search.read_text(encoding="utf-8")
        if "catalog_margin" in s2 and "/ hj * 100" not in s2:
            ok("D3", "pencarian katalog memakai SSOT margin yang sama "
                     "(tidak ada rumus kedua)")
        else:
            bad("D3", "marketing_catalog_search masih punya rumus margin sendiri")

    finally:
        db.marketing_catalog_items.delete_many({"notes": TAG})
        db.marketing_catalogs.delete_many({"notes": TAG})
        db.rahaza_materials.delete_many({"notes": TAG})
        left = (db.marketing_catalog_items.count_documents({"notes": TAG})
                + db.rahaza_materials.count_documents({"notes": TAG}))
        if left == 0:
            ok("Z1", "katalog, item, dan FG uji dibersihkan")
        else:
            bad("Z1", f"{left} artefak uji tertinggal")

    print(f"\n{B}{'─' * 70}{X}")
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian margin (INV-F43) terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
