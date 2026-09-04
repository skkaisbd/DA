#!/usr/bin/env python3
"""verify_alert_stok_hidup.py — SESI #29 (permintaan pemilik W3, 2026-08-21).

GATE **INV-F34** — "ALERT STOK BENAR-BENAR BERBUNYI, DAN SEMUA LAYAR SEPAKAT
KAPAN STOK DISEBUT RENDAH."

═══════════════════════════════════════════════════════════════════════════════
KEADAAN SEBELUM PERBAIKAN (terukur di basis data hidup, 2026-08-21)
═══════════════════════════════════════════════════════════════════════════════
Keluhan pemilik: menu **Alert & Reorder** tidak pernah berbunyi.

  · `GET /api/rahaza/stock-thresholds/summary` → **333 material, 0 punya ambang**
    (`min_stock_qty` & `reorder_point` kosong SEMUA) ⇒ alarmnya tidak rusak,
    ambangnya belum pernah diisi, dan **tidak ada layar untuk mengisinya massal**
    (satu-satunya jalan: modal Master Item, satu material per kali — 333 kali).
  · Ada **TIGA definisi "rendah"** yang hidup terpisah:
      layar Alert & Reorder → HANYA `reorder_point`, on-hand kanonik
      notifikasi/bel        → HANYA `min_stock` (legacy), `SUM($qty)`
      dashboard low-stock   → `min_stock_qty`→%→`min_stock`, `SUM($qty)`
    ⇒ pemilik mengisi ambang di satu tempat, layar lain tetap berkata "aman".
  · `SUM($qty)` MELEWATKAN baris stok skema lama (`total_qty`/`available_quantity`)
    ⇒ stok bisa terbaca 0 padahal ada, atau sebaliknya.

INVARIAN YANG DIJAGA
--------------------
  A1  Endpoint ambang menyajikan stok KANONIK + usulan dari pemakaian NYATA
  A2  Usulan tidak menebak: tanpa pemakaian 30 hari ⇒ usulan 0 + `no_usage_data`
  A3  Simpan massal benar-benar menulis master; nilai negatif ditolak 400
  A4  ALARMNYA BERBUNYI: ambang di atas stok ⇒ material muncul di
      `/api/warehouse/alerts`; ambang dikosongkan ⇒ alert hilang (bukti 2 arah)
  A5  SATU definisi "rendah": layar alert, notifikasi (`check_low_stock`), dan
      dashboard (`?low_stock=true`) sepakat pada material uji yang sama
  A6  Stok dibaca kanonik: baris skema lama (`total_qty`) IKUT terhitung
  A7  Layar Alert & Reorder JUJUR: menyebut berapa material yang belum punya
      ambang dan mengarahkan ke tempat mengisinya (bukan "semua normal")
  A8  Pintunya ada: tab "Ambang Stok" di Master Item + kolom input + tombol usulan
  A9  ALAT UKUR BERSIH: ambang & baris stok uji dikembalikan persis seperti semula

Pakai:  python3 scripts/verify_alert_stok_hidup.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
PASS, FAIL = [], []

FE_HUB = ROOT / "frontend/src/components/erp/WarehouseMasterHub.jsx"
FE_TH = ROOT / "frontend/src/components/erp/StockThresholdsModule.jsx"
FE_SMART = ROOT / "frontend/src/components/erp/WarehouseSmartModule.jsx"


def ok(code, msg, detail=""):
    PASS.append(code)
    print(f"  {G}✓{X} {code} — {msg}" + (f" · {detail}" if detail else ""))


def bad(code, msg, detail=""):
    FAIL.append(code)
    print(f"  {R}✗ {code} — {msg}{X}" + (f" · {detail}" if detail else ""))


def head(t):
    print(f"\n{C}{B}{t}{X}")


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
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def main():
    print(f"{C}{B}INV-F34 — ALERT STOK HIDUP & SATU DEFINISI 'RENDAH'{X}")
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    from gr_common import db_handle
    db = db_handle()

    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}){X}")
        return 2

    # ── A1/A2 — katalog ambang + usulan dari pemakaian nyata ────────────────
    head("A1/A2 — daftar ambang: stok kanonik + usulan dari pemakaian NYATA")
    st1, d1 = call("GET", "/api/rahaza/stock-thresholds?limit=1000", token)
    items = d1.get("items") or []
    summ = d1.get("summary") or {}
    if st1 != 200 or not items:
        bad("A1", "endpoint daftar ambang stok tidak menyajikan data", f"HTTP {st1}")
        return 1
    from core import stock_service  # noqa: F401  (bukti reader kanonik dipakai core)
    contoh = next((i for i in items if i["onhand"] > 0), items[0])
    wajib = {"onhand", "min_stock_qty", "reorder_point", "status", "suggestion", "alert_at"}
    if not wajib.issubset(contoh):
        bad("A1", "baris ambang tidak lengkap", f"hilang={sorted(wajib - set(contoh))}")
    else:
        ok("A1", "daftar ambang menyajikan stok, ambang, status & usulan",
           f"{summ.get('total_materials')} material · {summ.get('with_threshold')} sudah punya ambang "
           f"· {summ.get('missing_threshold')} belum")

    tanpa_pakai = [i for i in items if i["suggestion"]["no_usage_data"]]
    salah_tebak = [i["code"] for i in tanpa_pakai
                   if i["suggestion"]["suggested_min_stock"] or i["suggestion"]["suggested_reorder_point"]]
    dengan_pakai = [i for i in items if not i["suggestion"]["no_usage_data"]]
    if salah_tebak:
        bad("A2", "material tanpa pemakaian diberi usulan (menebak)", f"{salah_tebak[:5]}")
    else:
        ok("A2", "usulan hanya untuk material dengan pemakaian nyata; sisanya 0 + ditandai",
           f"{len(dengan_pakai)} ada pemakaian · {len(tanpa_pakai)} tanpa pemakaian 30 hari")

    # ── Siapkan material uji: pilih yang punya stok > 0 ─────────────────────
    target = next((i for i in items if i["onhand"] > 0), None)
    if not target:
        bad("A4", "TIDAK TERUKUR: tidak ada material dengan stok > 0")
        return 1
    mid, code, onhand = target["material_id"], target["code"], target["onhand"]
    semula = db.rahaza_materials.find_one(
        {"id": mid}, {"_id": 0, "min_stock_qty": 1, "reorder_point": 1}) or {}

    # ── A3 — simpan massal & tolak nilai negatif ────────────────────────────
    head("A3 — simpan ambang massal (dan tolak nilai tidak masuk akal)")
    st_neg, _ = call("POST", "/api/rahaza/stock-thresholds/bulk", token,
                     {"items": [{"material_id": mid, "min_stock_qty": -5}]})
    ambang = round(onhand + 100, 2)
    st3, d3 = call("POST", "/api/rahaza/stock-thresholds/bulk", token,
                   {"items": [{"material_id": mid, "min_stock_qty": ambang,
                               "reorder_point": round(ambang + 50, 2)}]})
    tersimpan = db.rahaza_materials.find_one({"id": mid}, {"_id": 0, "min_stock_qty": 1})
    if st_neg != 400:
        bad("A3", "ambang negatif TIDAK ditolak", f"HTTP {st_neg}")
    elif st3 != 200 or float((tersimpan or {}).get("min_stock_qty") or 0) != ambang:
        bad("A3", "ambang tidak benar-benar tersimpan di master",
            f"HTTP {st3} · tersimpan={(tersimpan or {}).get('min_stock_qty')}")
    else:
        ok("A3", "ambang tersimpan ke master & nilai negatif ditolak 400",
           f"{code}: min={ambang} (stok {onhand}) · {d3.get('updated')} baris")

    # ── A4/A5 — alarmnya berbunyi & semua pembaca sepakat ───────────────────
    head("A4/A5 — alarm berbunyi dan SEMUA pembaca sepakat")
    st4, d4 = call("GET", "/api/warehouse/alerts?threshold=90", token)
    alerts = [a for a in (d4.get("data") or []) if a.get("type") == "low_stock"]
    kena = next((a for a in alerts if a.get("material_id") == mid), None)

    st5, d5 = call("GET", f"/api/rahaza/materials?low_stock=true&search={code}", token)
    dash = d5 if isinstance(d5, list) else (d5.get("items") or [])
    dash_kena = any(m.get("id") == mid for m in dash)

    import asyncio
    from routes import rahaza_alerts as ra
    notif = asyncio.run(ra.check_low_stock(_motor_db(), {}))
    notif_kena = any(n.get("link_id") == mid for n in notif)

    if not kena:
        bad("A4", "ambang dilanggar tetapi layar Alert & Reorder tetap sunyi",
            f"{len(alerts)} alert stok, {code} tidak ada di dalamnya")
    else:
        ok("A4", "alarm berbunyi begitu ambang dilanggar",
           f"{code}: stok {kena['current_qty']} < ambang {kena['alert_at']} · "
           f"kurang {kena['shortage']} · {kena['severity']}")

    if kena and dash_kena and notif_kena:
        ok("A5", "layar alert · dashboard low-stock · notifikasi SEPAKAT satu definisi",
           f"{code} muncul di ketiganya")
    else:
        bad("A5", "pembaca 'stok rendah' masih berbeda pendapat",
            f"alert={bool(kena)} dashboard={dash_kena} notifikasi={notif_kena}")

    # ── A6 — stok kanonik: baris skema lama ikut terhitung ──────────────────
    head("A6 — stok dibaca kanonik (baris skema lama ikut terhitung)")
    probe = {"id": "GATE-F34-LEGACY-ROW", "material_id": mid, "location_id": "GATE-F34-LOC",
             "total_qty": 999999, "available_quantity": 999999}
    db.rahaza_material_stock.insert_one(dict(probe))
    st6, d6 = call("GET", f"/api/rahaza/stock-thresholds?search={code}", token)
    row6 = next((i for i in (d6.get("items") or []) if i["material_id"] == mid), None)
    db.rahaza_material_stock.delete_one({"id": probe["id"]})
    if row6 and row6["onhand"] >= 999999:
        ok("A6", "baris stok skema lama (`total_qty`) IKUT terbaca",
           f"{code}: {onhand} → {row6['onhand']} setelah baris legacy ditambahkan")
    else:
        bad("A6", "baris stok skema lama tidak terbaca (blind spot kembali)",
            f"onhand={row6['onhand'] if row6 else 'n/a'}")

    # ── A7/A8 — kejujuran layar & pintu pengisian ambang ───────────────────
    head("A7/A8 — layar jujur & pintu pengisian ambang benar-benar ada")
    meta = d4.get("metadata") or {}
    smart = FE_SMART.read_text(encoding="utf-8")
    kurang7 = [k for k in ("materials_missing_threshold", "materials_with_threshold",
                           "materials_total") if k not in meta]
    if kurang7:
        bad("A7", "layar tidak diberi angka 'berapa yang belum punya ambang'",
            f"hilang dari metadata: {kurang7}")
    elif "wh-smart-threshold-notice" not in smart or "wh-smart-goto-thresholds" not in smart:
        bad("A7", "layar Alert & Reorder tidak memberi tahu & tidak mengarahkan pengisian")
    else:
        ok("A7", "layar menyebut sisa material tanpa ambang & mengarahkan pengisiannya",
           f"{meta['materials_with_threshold']}/{meta['materials_total']} dipantau · "
           f"{meta['materials_missing_threshold']} belum berambang")

    hub = FE_HUB.read_text(encoding="utf-8")
    th = FE_TH.read_text(encoding="utf-8")
    kurang8 = []
    for probe_s, where, nama in (
            ('data-testid="tab-thresholds"', hub, "tab Ambang Stok di Master Item"),
            ("StockThresholdsModule", hub, "modul ambang dipasang di hub"),
            ("threshold-min-", th, "kolom isi min stok"),
            ("threshold-rp-", th, "kolom isi titik pesan ulang"),
            ("threshold-use-suggestion-", th, "tombol pakai usulan per baris"),
            ("threshold-apply-all", th, "tombol pakai semua usulan"),
            ("stock-thresholds/bulk", th, "tombol simpan massal")):
        if probe_s not in where:
            kurang8.append(nama)
    if kurang8:
        bad("A8", "pintu pengisian ambang belum lengkap di layar", "; ".join(kurang8))
    else:
        ok("A8", "tab 'Ambang Stok' + kolom isi + usulan + simpan massal tersedia di Master Item")

    # ── A9 — pulangkan keadaan semula ──────────────────────────────────────
    head("A9 — alat ukur tidak mengotori")
    db.rahaza_materials.update_one({"id": mid}, {"$set": {
        "min_stock_qty": semula.get("min_stock_qty"),
        "reorder_point": semula.get("reorder_point", 0)}})
    kembali = db.rahaza_materials.find_one(
        {"id": mid}, {"_id": 0, "min_stock_qty": 1, "reorder_point": 1}) or {}
    sisa_probe = db.rahaza_material_stock.count_documents({"id": probe["id"]})
    if (kembali.get("min_stock_qty") == semula.get("min_stock_qty")
            and float(kembali.get("reorder_point") or 0) == float(semula.get("reorder_point") or 0)
            and sisa_probe == 0):
        ok("A9", "ambang material uji & baris stok uji dipulihkan persis",
           f"{code}: min_stock_qty={kembali.get('min_stock_qty')} "
           f"reorder_point={kembali.get('reorder_point')}")
    else:
        bad("A9", "gate meninggalkan perubahan pada data hidup",
            f"{kembali} · baris uji tersisa={sisa_probe}")

    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian alert stok terjaga{X}")
    return 0


def _motor_db():
    """Handle async (motor) untuk memanggil rule notifikasi apa adanya."""
    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return cli[os.environ["DB_NAME"]]


if __name__ == "__main__":
    sys.exit(main())
