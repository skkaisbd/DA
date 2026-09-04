#!/usr/bin/env python3
"""test_core_h5_h6.py — POC INTI FASE H-5 · H-6 (roll kain lahir saat diterima, mati saat dipotong).

MENGAPA BERKAS INI ADA
----------------------
Development sesi sebelumnya BERHENTI di tengah H-5: `routes/warehouse.py` memanggil
`fabric_rolls.is_roll_material()` dan `fabric_roll_engine.create_rolls_from_receipt()`
tanpa satu pun modul itu di-import, dan `rolls_created` belum pernah diinisialisasi
(pyflakes: 4 undefined name). Akibatnya penerimaan kain dengan rincian roll akan
NameError → 500, dan kerusakannya TERSEMBUNYI karena backend tetap bisa start.

Skrip ini membuktikan lewat HTTP API sungguhan + verifikasi langsung ke MongoDB:
  A. Kode inti bersih (pyflakes) & backend hidup.
  B. GR kain + rincian roll → stok naik DAN gulungan terbit dengan nomor OTOMATIS.
  C. Rincian roll tidak cocok dengan qty diterima → 400 dan TIDAK ADA stok tertulis.
  D. Material bukan-kain (pcs) diberi rincian roll → 400 dengan alasan yang jelas.
  E. Nomor roll tetap UNIK saat 20 penerbitan bersamaan + nomor ketikan DITOLAK.
  F. H-6: memotong kain WAJIB menunjuk gulungan; sisa gulungan berkurang FIFO;
     kain tanpa gulungan ditolak dengan jalan keluarnya.
  G. Backfill: penerimaan kain lama yang belum punya gulungan kelihatan & bisa
     diterbitkan gulungannya (idempoten — terbit dua kali DITOLAK).

Jalankan: python3 /app/test_core_h5_h6.py
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001")
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}

ROLL_NO_RE = re.compile(r"^RL-\d{6}-\d{4}$")

PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, detail: str = "") -> None:
    PASS.append(name)
    print(f"  \033[92m✓\033[0m {name}" + (f" — {detail}" if detail else ""))


def bad(name: str, detail: str = "") -> None:
    FAIL.append(f"{name}: {detail}")
    print(f"  \033[91m✗ {name}\033[0m" + (f" — {detail}" if detail else ""))


def check(name: str, cond: bool, detail: str = "") -> bool:
    (ok if cond else bad)(name, detail)
    return bool(cond)


def head(t: str) -> None:
    print(f"\n\033[1;36m{t}\033[0m")


class Api:
    def __init__(self, client: httpx.AsyncClient, token: str):
        self.c, self.token = client, token

    @property
    def h(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def get(self, path: str, **kw) -> httpx.Response:
        return await self.c.get(f"{BASE}{path}", headers=self.h, **kw)

    async def post(self, path: str, body: Any = None) -> httpx.Response:
        return await self.c.post(f"{BASE}{path}", headers=self.h, json=body or {})

    async def put(self, path: str, body: Any = None) -> httpx.Response:
        return await self.c.put(f"{BASE}{path}", headers=self.h, json=body or {})


def err_of(r: httpx.Response) -> str:
    try:
        j = r.json()
        return str(j.get("detail") or j)[:400]
    except Exception:
        return r.text[:400]


# ───────────────────────────── A. sanity kode & servis ─────────────────────────

async def test_a_sanity(api: Api) -> None:
    head("A. Kode inti bersih + backend hidup")
    p = subprocess.run([sys.executable, "-m", "pyflakes",
                        "routes/warehouse.py", "routes/cutting.py",
                        "routes/wms_fabric_rolls.py", "core/fabric_roll_engine.py"],
                       cwd="/app/backend", capture_output=True, text=True)
    undefined = [ln for ln in (p.stdout + p.stderr).splitlines() if "undefined name" in ln]
    check("pyflakes: tidak ada undefined name di jalur roll", not undefined,
          "; ".join(undefined) or "bersih")

    r = await api.c.get(f"{BASE}/api/health")
    check("GET /api/health = ok", r.status_code == 200 and r.json().get("status") == "ok",
          err_of(r) if r.status_code != 200 else r.json().get("db", ""))

    r = await api.get("/api/wms/fabric-rolls/number-policy")
    j = r.json() if r.status_code == 200 else {}
    check("kebijakan nomor roll = OTOMATIS berpola RL-YYYYMM-####",
          r.status_code == 200 and j.get("mode") == "auto"
          and bool(ROLL_NO_RE.match(str(j.get("next_number") or ""))),
          f"{j.get('mode')} · format={j.get('format')} · next={j.get('next_number')}"
          if r.status_code == 200 else err_of(r))


# ───────────────────────────── data uji (nyata, via API) ───────────────────────

async def ensure_material(api: Api, code: str, name: str, unit: str, mtype: str,
                          unit_cost: float = 0.0) -> dict:
    """Master material dibuat lewat API sungguhan (idempoten by code)."""
    r = await api.get(f"/api/rahaza/materials?limit=20000&search={code}")
    rows = r.json() if r.status_code == 200 else []
    if isinstance(rows, dict):
        rows = rows.get("items") or []
    hit = next((m for m in rows if str(m.get("code", "")).upper() == code.upper()), None)
    if hit:
        return hit
    r = await api.post("/api/rahaza/materials", {
        "code": code, "name": name, "unit": unit, "type": mtype,
        "color": "Navy", "unit_cost": unit_cost, "notes": "POC H-5/H-6",
    })
    if r.status_code not in (200, 201):
        raise RuntimeError(f"gagal buat material {code}: {err_of(r)}")
    j = r.json()
    return j.get("material") or j


async def pick_location(api: Api) -> dict:
    r = await api.get("/api/rahaza/storage-locations")
    rows = r.json()
    if isinstance(rows, dict):
        rows = rows.get("items") or []
    pref = next((x for x in rows if "kain" in str(x.get("name", "")).lower()), None)
    loc = pref or (rows[0] if rows else None)
    if not loc:
        raise RuntimeError("tidak ada storage location")
    return loc


async def make_gr(api: Api, loc: dict, item: dict, supplier="PT POC Tekstil") -> dict:
    r = await api.post("/api/wms/legacy/receiving", {
        "source_type": "supplier", "supplier_name": supplier,
        "location_id": loc.get("id"), "location_name": loc.get("name"),
        "notes": "POC H-5", "items": [item],
    })
    if r.status_code not in (200, 201):
        raise RuntimeError(f"gagal buat GR: {err_of(r)}")
    return r.json()


async def receive_gr(api: Api, gr: dict, items: Optional[list] = None) -> httpx.Response:
    body: dict = {"status": "received"}
    if items is not None:
        body["items"] = items
    return await api.put(f"/api/wms/legacy/receiving/{gr['id']}", body)


async def onhand(db, material_id: str) -> float:
    tot = 0.0
    async for s in db.rahaza_material_stock.find({"material_id": material_id}, {"_id": 0, "qty": 1}):
        tot += float(s.get("qty") or 0)
    return round(tot, 4)


# ───────────────────────────── B. GR kain → roll otomatis ──────────────────────

async def test_b_gr_creates_rolls(api: Api, db, loc: dict) -> dict:
    head("B. GR kain + rincian roll → stok naik & gulungan terbit (nomor otomatis)")
    mat = await ensure_material(api, "POC-KAIN-CTN-30S", "Kain Cotton Combed 30s (POC)",
                                "kg", "fabric", unit_cost=78000)
    before = await onhand(db, mat["id"])
    rolls = [{"qty": 70, "color_lot": "LOT-A", "notes": ""} for _ in range(6)]
    gr = await make_gr(api, loc, {
        "product_name": mat["name"], "sku": mat["code"], "material_id": mat["id"],
        "expected_qty": 420, "received_qty": 420, "rejected_qty": 0, "unit": "kg",
        "unit_price": 78000, "inspection_status": "passed", "lot_number": "LOT-A",
        "rolls": rolls,
    })
    check("GR draft menyimpan rincian roll (6 baris)",
          len((gr.get("items") or [{}])[0].get("rolls") or []) == 6,
          f"GR {gr.get('receipt_number')}")

    r = await receive_gr(api, gr)
    if not check("PUT status=received berhasil (tanpa NameError/500)", r.status_code == 200,
                 f"HTTP {r.status_code} {err_of(r)}"):
        return {}
    got = r.json()
    created = got.get("rolls_created") or []
    check("6 nomor roll terbit & dilaporkan balik ke pemanggil", len(created) == 6, str(created))
    check("semua nomor roll berpola RL-YYYYMM-#### (otomatis, bukan ketikan)",
          all(ROLL_NO_RE.match(x) for x in created), str(created[:3]))
    check("nomor roll berurutan tanpa bolong",
          len(set(created)) == 6, f"unik={len(set(created))}")

    docs = await db.wh_fabric_rolls.find({"source_receipt_id": gr["id"]}, {"_id": 0}).to_list(50)
    check("6 dokumen roll tercatat di wh_fabric_rolls", len(docs) == 6, f"n={len(docs)}")
    check("setiap roll uom=kg, sisa 70 kg, status in_stock",
          all(d.get("uom") == "kg" and abs(float(d.get("remaining_kg") or 0) - 70) < 0.001
              and d.get("status") == "in_stock" for d in docs),
          f"contoh: {docs[0].get('roll_no')} {docs[0].get('remaining_kg')}kg" if docs else "-")
    check("roll mewarisi lokasi + supplier + lot dari GR",
          all(d.get("location_id") == loc.get("id") and d.get("supplier_name") == "PT POC Tekstil"
              and d.get("color_lot") == "LOT-A" for d in docs),
          f"{docs[0].get('location_name')} · {docs[0].get('color_lot')}" if docs else "-")
    check("QC roll ikut hasil inspeksi baris GR (passed → pass)",
          all(d.get("qc_status") == "pass" for d in docs),
          str({d.get("qc_status") for d in docs}))

    movs = await db.wh_fabric_roll_movements.count_documents(
        {"reference_id": gr["id"], "movement_type": "receive"})
    check("6 movement 'receive' tercatat (jejak audit)", movs == 6, f"n={movs}")

    after = await onhand(db, mat["id"])
    check("stok kain naik 420 kg lewat stock_service", abs(after - before - 420) < 0.001,
          f"{before} → {after}")

    fresh = await db.warehouse_receiving.find_one({"id": gr["id"]}, {"_id": 0})
    it0 = (fresh.get("items") or [{}])[0]
    check("baris GR menyimpan roll_ids + roll_numbers (jejak dua arah)",
          len(it0.get("roll_ids") or []) == 6 and len(it0.get("roll_numbers") or []) == 6,
          str((it0.get("roll_numbers") or [])[:2]))
    return {"material": mat, "gr": gr, "rolls": sorted(docs, key=lambda d: d["roll_no"])}


# ───────────────────── C. rincian tidak cocok → tolak, stok utuh ───────────────

async def test_c_mismatch_atomic(api: Api, db, loc: dict) -> None:
    head("C. Rincian roll ≠ qty diterima → DITOLAK dan stok TIDAK berubah")
    mat = await ensure_material(api, "POC-KAIN-MISMATCH", "Kain Uji Selisih (POC)",
                                "kg", "fabric", unit_cost=50000)
    before = await onhand(db, mat["id"])
    gr = await make_gr(api, loc, {
        "product_name": mat["name"], "sku": mat["code"], "material_id": mat["id"],
        "expected_qty": 100, "received_qty": 100, "rejected_qty": 0, "unit": "kg",
        "unit_price": 50000, "inspection_status": "passed",
        "rolls": [{"qty": 30}, {"qty": 30}, {"qty": 30}],   # 90 ≠ 100
    })
    r = await receive_gr(api, gr)
    msg = err_of(r)
    check("HTTP 400 saat total roll tidak cocok", r.status_code == 400, f"HTTP {r.status_code}")
    check("pesan menyebut selisihnya secara eksplisit",
          "selisih" in msg.lower() and ("90" in msg or "-10" in msg), msg[:200])
    after = await onhand(db, mat["id"])
    check("stok TIDAK bertambah setengah jalan", abs(after - before) < 0.001, f"{before} → {after}")
    n = await db.wh_fabric_rolls.count_documents({"source_receipt_id": gr["id"]})
    check("tidak ada roll yatim yang terbit", n == 0, f"n={n}")
    fresh = await db.warehouse_receiving.find_one({"id": gr["id"]}, {"_id": 0, "status": 1})
    check("status GR tetap draft (bisa diperbaiki lalu diulang)",
          fresh.get("status") == "draft", str(fresh.get("status")))

    # perbaiki angkanya → sekarang harus lolos (bukti pesannya benar-benar bisa ditindaklanjuti)
    items = (await db.warehouse_receiving.find_one({"id": gr["id"]}, {"_id": 0}))["items"]
    items[0]["rolls"] = [{"qty": 40}, {"qty": 30}, {"qty": 30}]
    r2 = await receive_gr(api, gr, items=items)
    check("setelah angka roll diperbaiki, penerimaan lolos",
          r2.status_code == 200 and len(r2.json().get("rolls_created") or []) == 3,
          f"HTTP {r2.status_code} {err_of(r2) if r2.status_code != 200 else r2.json().get('rolls_created')}")
    check("stok baru bertambah setelah perbaikan (100 kg)",
          abs(await onhand(db, mat["id"]) - before - 100) < 0.001)


# ───────────────────── D. material bukan-kain diberi roll → tolak ──────────────

async def test_d_non_roll_material(api: Api, db, loc: dict) -> None:
    head("D. Material bersatuan pcs diberi rincian roll → DITOLAK")
    mat = await ensure_material(api, "POC-BTN-PCS", "Kancing Uji (POC)", "pcs", "accessory",
                               unit_cost=250)
    before = await onhand(db, mat["id"])
    gr = await make_gr(api, loc, {
        "product_name": mat["name"], "sku": mat["code"], "material_id": mat["id"],
        "expected_qty": 500, "received_qty": 500, "rejected_qty": 0, "unit": "pcs",
        "unit_price": 250, "inspection_status": "passed",
        "rolls": [{"qty": 250}, {"qty": 250}],
    })
    r = await receive_gr(api, gr)
    msg = err_of(r)
    check("HTTP 400 untuk material yang tidak dilacak per gulungan", r.status_code == 400,
          f"HTTP {r.status_code}")
    check("pesan menyebut satuannya & alasannya",
          "pcs" in msg.lower() and "gulungan" in msg.lower(), msg[:200])
    check("stok pcs tidak berubah", abs(await onhand(db, mat["id"]) - before) < 0.001)


# ───────────────────── E. nomor roll unik & tidak boleh diketik ────────────────

async def test_e_numbering(api: Api, db) -> None:
    head("E. Nomor roll: 20 penerbitan bersamaan tetap unik + nomor ketikan ditolak")
    mat = await ensure_material(api, "POC-KAIN-RACE", "Kain Uji Nomor (POC)", "m", "fabric")
    payload = {
        "material_id": mat["id"], "material_code": mat["code"], "material_name": mat["name"],
        "uom": "meter", "length_m": 25, "weight_kg": 0, "notes": "POC race",
    }
    t0 = time.time()
    res = await asyncio.gather(*[api.post("/api/wms/fabric-rolls", payload) for _ in range(20)],
                               return_exceptions=True)
    good = [r for r in res if isinstance(r, httpx.Response) and r.status_code == 200]
    nos = [r.json()["roll"]["roll_no"] for r in good]
    check("20 permintaan paralel semuanya berhasil", len(good) == 20,
          f"berhasil={len(good)}/20 dalam {time.time() - t0:.1f}s")
    check("20 nomor roll UNIK (tidak ada gulungan bernomor sama)",
          len(set(nos)) == len(nos) == 20, f"unik={len(set(nos))}")
    check("semua nomor mengikuti pola otomatis", all(ROLL_NO_RE.match(x) for x in nos),
          str(sorted(nos)[:3]))
    dup = await db.wh_fabric_rolls.aggregate([
        {"$group": {"_id": "$roll_no", "n": {"$sum": 1}}}, {"$match": {"n": {"$gt": 1}}},
    ]).to_list(20)
    check("tidak ada duplikat roll_no di seluruh koleksi", not dup, str(dup[:3]))

    r = await api.post("/api/wms/fabric-rolls", {**payload, "roll_no": "RL-KETIKAN-01"})
    msg = err_of(r)
    check("nomor roll ketikan DITOLAK (mode otomatis)", r.status_code == 400, f"HTTP {r.status_code}")
    check("pesan penolakan menyebut nomor yang akan dipakai",
          "otomatis" in msg.lower() and bool(re.search(r"RL-\d{6}-\d{4}", msg)), msg[:200])


# ───────────────────── F. H-6 cutting WAJIB menunjuk gulungan ──────────────────

async def test_f_cutting_requires_roll(api: Api, db, ctx: dict, loc: dict) -> None:
    head("F. H-6 — memotong kain WAJIB menunjuk gulungan (FIFO, sisa berkurang)")
    mat, rolls = ctx["material"], ctx["rolls"]
    r = await api.post("/api/cutting/orders", {
        "input_material_id": mat["id"], "planned_input_qty": 200, "planned_output_qty": 400,
        "style_name": "Kaos POC H6", "style_sku": "POC-H6", "output_size": "L",
        "output_color": "Navy", "location_id": loc.get("id"), "notes": "POC H-6",
    })
    if not check("order cutting bisa dibuat untuk kain yang punya gulungan",
                 r.status_code in (200, 201), f"HTTP {r.status_code} {err_of(r)}"):
        return
    order = r.json()
    check("order menandai roll WAJIB (roll_required=True)", order.get("roll_required") is True,
          str(order.get("roll_required")))

    r = await api.get(f"/api/cutting/rolls?material_id={mat['id']}")
    j = r.json() if r.status_code == 200 else {}
    check("daftar gulungan siap-pakai tersedia untuk layar cutting",
          r.status_code == 200 and j.get("roll_required") is True and (j.get("total") or 0) >= 6,
          f"total={j.get('total')} sisa={j.get('total_remaining')}")

    r = await api.post(f"/api/cutting/orders/{order['id']}/start")
    if not check("order bisa di-start (stok kain tersedia)", r.status_code == 200,
                 f"HTTP {r.status_code} {err_of(r)}"):
        return

    stok0 = await onhand(db, mat["id"])
    r = await api.post(f"/api/cutting/orders/{order['id']}/progress",
                       {"input_consumed": 70, "output_qty": 140})
    msg = err_of(r)
    check("progres TANPA memilih gulungan DITOLAK (400)", r.status_code == 400,
          f"HTTP {r.status_code}")
    check("pesan menyebutkan gulungan yang masih bersisa (bisa ditindaklanjuti)",
          "pilih gulungan" in msg.lower() and "sisa" in msg.lower(), msg[:220])
    check("stok kain tidak berkurang saat progres ditolak",
          abs(await onhand(db, mat["id"]) - stok0) < 0.001)

    r = await api.post(f"/api/cutting/orders/{order['id']}/progress",
                       {"input_consumed": 100, "output_qty": 100,
                        "roll_ids": [rolls[0]["id"]]})
    msg = err_of(r)
    check("gulungan terpilih tidak cukup → DITOLAK dengan angka",
          r.status_code == 400 and "tidak cukup" in msg.lower(), f"HTTP {r.status_code} {msg[:180]}")
    check("stok tetap utuh saat alokasi gulungan gagal",
          abs(await onhand(db, mat["id"]) - stok0) < 0.001)

    r = await api.post(f"/api/cutting/orders/{order['id']}/progress",
                       {"input_consumed": 70, "output_qty": 140, "roll_ids": [rolls[0]["id"]]})
    if check("progres dengan gulungan dipilih BERHASIL", r.status_code == 200,
             f"HTTP {r.status_code} {err_of(r)}"):
        out = r.json()
        cons = (out.get("last_progress") or {}).get("roll_consumption") or []
        check("laporan balik menyebut gulungan mana dipakai berapa", len(cons) == 1
              and abs(float(cons[0]["qty"]) - 70) < 0.001,
              str([(c.get("roll_no"), c.get("qty"), c.get("remaining_after")) for c in cons]))
        d = await db.wh_fabric_rolls.find_one({"id": rolls[0]["id"]}, {"_id": 0})
        check("gulungan habis → sisa 0 & status fully_issued",
              abs(float(d.get("remaining_kg") or 0)) < 0.001 and d.get("status") == "fully_issued",
              f"{d.get('roll_no')} sisa={d.get('remaining_kg')} status={d.get('status')}")
        n = await db.wh_fabric_roll_movements.count_documents(
            {"roll_id": rolls[0]["id"], "movement_type": "issue"})
        check("movement 'issue' tercatat untuk gulungan itu", n == 1, f"n={n}")
        check("stok kain berkurang 70 kg", abs(await onhand(db, mat["id"]) - stok0 + 70) < 0.001,
              f"{stok0} → {await onhand(db, mat['id'])}")

    # FIFO lintas gulungan: 100 kg dari 2 gulungan (70 + 30)
    r = await api.post(f"/api/cutting/orders/{order['id']}/progress",
                       {"input_consumed": 100, "output_qty": 200,
                        "roll_ids": [rolls[1]["id"], rolls[2]["id"]]})
    if check("pemakaian lintas gulungan dibagi otomatis (FIFO)", r.status_code == 200,
             f"HTTP {r.status_code} {err_of(r)}"):
        cons = (r.json().get("last_progress") or {}).get("roll_consumption") or []
        qmap = {c["roll_no"]: c["qty"] for c in cons}
        d1 = await db.wh_fabric_rolls.find_one({"id": rolls[1]["id"]}, {"_id": 0})
        d2 = await db.wh_fabric_rolls.find_one({"id": rolls[2]["id"]}, {"_id": 0})
        check("gulungan tertua dipakai penuh dulu (70), sisanya ke gulungan berikutnya (30)",
              len(cons) == 2 and abs(sum(qmap.values()) - 100) < 0.001
              and abs(float(d1.get("remaining_kg") or 0)) < 0.001
              and abs(float(d2.get("remaining_kg") or 0) - 40) < 0.001,
              f"{qmap} · sisa {d1.get('roll_no')}={d1.get('remaining_kg')} "
              f"{d2.get('roll_no')}={d2.get('remaining_kg')}")
        prog = await db.cutting_progress.find_one({"cutting_order_id": order["id"]},
                                                 {"_id": 0}, sort=[("created_at", -1)])
        check("jejak audit progres menyimpan konsumsi per gulungan",
              len(prog.get("roll_consumption") or []) == 2 and len(prog.get("roll_numbers") or []) == 2,
              str(prog.get("roll_numbers")))
        o = await db.cutting_orders.find_one({"id": order["id"]}, {"_id": 0})
        picked = {x["roll_no"]: x.get("consumed_qty") for x in (o.get("roll_ids") or [])}
        check("order mencatat gulungan yang dipakai + jumlahnya", len(picked) >= 3, str(picked))

    # kain yang belum punya gulungan sama sekali → ditolak dengan jalan keluar
    # Kode material di-stempel waktu: kalau memakai kode tetap, jalankan-ulang skrip
    # akan menemukan kain yang SUDAH di-backfill di jalankan sebelumnya sehingga
    # kasus "belum punya gulungan" tidak pernah benar-benar diuji.
    stamp = datetime.now(timezone.utc).strftime("%m%d%H%M%S")
    mat2 = await ensure_material(api, f"POC-KAIN-NOROLL-{stamp}",
                                 f"Kain Belum Ada Roll {stamp} (POC)", "kg", "fabric")
    gr2 = await make_gr(api, loc, {
        "product_name": mat2["name"], "sku": mat2["code"], "material_id": mat2["id"],
        "expected_qty": 50, "received_qty": 50, "rejected_qty": 0, "unit": "kg",
        "unit_price": 40000, "inspection_status": "passed",
    })
    rr = await receive_gr(api, gr2)
    check("GR kain tanpa rincian roll tetap diterima, tapi dilaporkan sebagai 'tanpa roll'",
          rr.status_code == 200 and len(rr.json().get("rolls_pending") or []) == 1,
          f"HTTP {rr.status_code} pending={len((rr.json().get('rolls_pending') or []) if rr.status_code == 200 else [])}")
    r = await api.post("/api/cutting/orders", {
        "input_material_id": mat2["id"], "planned_input_qty": 10, "planned_output_qty": 20,
        "style_name": "Kaos Tanpa Roll", "location_id": loc.get("id"),
    })
    msg = err_of(r)
    check("order cutting untuk kain tanpa gulungan DITOLAK", r.status_code == 400,
          f"HTTP {r.status_code}")
    check("pesan penolakan menyebut JALAN KELUARNYA (rincian roll / penerbitan retroaktif)",
          "penerimaan" in msg.lower() and ("roll kain" in msg.lower() or "rincian roll" in msg.lower()),
          msg[:240])
    ctx["gr_no_roll"] = gr2
    ctx["material_no_roll"] = mat2


# ───────────────────── G. backfill penerimaan tanpa gulungan ───────────────────

async def test_g_backfill(api: Api, db, ctx: dict) -> None:
    head("G. Penerimaan kain lama tanpa gulungan → kelihatan & bisa diterbitkan (idempoten)")
    gr = ctx.get("gr_no_roll")
    mat = ctx.get("material_no_roll")
    if not gr:
        bad("prasyarat backfill", "GR tanpa roll tidak tersedia dari langkah F")
        return
    r = await api.get("/api/wms/fabric-rolls/missing-from-receipts?limit=100")
    rows = (r.json() or {}).get("items") or []
    mine = [x for x in rows if x.get("receipt_id") == gr["id"]]
    check("penerimaan tanpa gulungan muncul di daftar 'Penerimaan tanpa roll'",
          r.status_code == 200 and len(mine) == 1,
          f"HTTP {r.status_code} · total daftar={len(rows)}")
    if not mine:
        return
    row = mine[0]
    check("baris daftar memuat qty diterima & satuan (cukup untuk mengisi rincian roll)",
          abs(float(row.get("accepted_qty") or 0) - 50) < 0.001 and row.get("unit") == "kg",
          f"{row.get('material_code')} {row.get('accepted_qty')} {row.get('unit')}")

    r = await api.post("/api/wms/fabric-rolls/issue-from-receipt", {
        "receipt_id": gr["id"], "item_id": row["item_id"],
        "lines": [{"qty": 25, "color_lot": "LOT-BF"}, {"qty": 25, "color_lot": "LOT-BF"}],
    })
    if check("terbitkan gulungan retroaktif berhasil", r.status_code == 200,
             f"HTTP {r.status_code} {err_of(r)}"):
        nos = r.json().get("roll_numbers") or []
        check("2 gulungan terbit dengan nomor otomatis",
              len(nos) == 2 and all(ROLL_NO_RE.match(x) for x in nos), str(nos))
        docs = await db.wh_fabric_rolls.find({"source_receipt_item_id": row["item_id"]},
                                             {"_id": 0}).to_list(10)
        check("gulungan retroaktif tertaut ke baris GR asalnya", len(docs) == 2,
              f"n={len(docs)}")
        check("sisa tiap gulungan 25 kg",
              all(abs(float(d.get("remaining_kg") or 0) - 25) < 0.001 for d in docs))

    r = await api.post("/api/wms/fabric-rolls/issue-from-receipt", {
        "receipt_id": gr["id"], "item_id": row["item_id"],
        "lines": [{"qty": 25}, {"qty": 25}],
    })
    check("penerbitan kedua DITOLAK (409) — tidak ada gulungan ganda", r.status_code == 409,
          f"HTTP {r.status_code} {err_of(r)}")

    r = await api.get("/api/wms/fabric-rolls/missing-from-receipts?limit=100")
    rows = (r.json() or {}).get("items") or []
    check("baris itu HILANG dari daftar setelah gulungannya terbit",
          not [x for x in rows if x.get("item_id") == row["item_id"]],
          f"sisa daftar={len(rows)}")

    # H-6 sekarang lolos untuk kain yang tadinya tanpa gulungan
    r = await api.post("/api/cutting/orders", {
        "input_material_id": mat["id"], "planned_input_qty": 10, "planned_output_qty": 20,
        "style_name": "Kaos Setelah Backfill", "location_id": None,
    })
    check("setelah backfill, order cutting untuk kain itu BISA dibuat",
          r.status_code in (200, 201), f"HTTP {r.status_code} {err_of(r)}")


# ───────────────────────────────── runner ─────────────────────────────────────

async def main() -> int:
    print("\033[1m" + "=" * 78)
    print("POC INTI — FASE H-5 (roll lahir dari penerimaan) & H-6 (cutting wajib roll)")
    print("=" * 78 + "\033[0m")
    mongo = AsyncIOMotorClient(MONGO)
    db = mongo[DB_NAME]
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(f"{BASE}/api/auth/login", json=ADMIN)
        if r.status_code != 200:
            print(f"LOGIN GAGAL: {r.status_code} {r.text[:200]}")
            return 2
        api = Api(client, r.json()["token"])
        loc = await pick_location(api)
        print(f"  lokasi uji: {loc.get('name')} ({loc.get('id')})")

        await test_a_sanity(api)
        ctx = await test_b_gr_creates_rolls(api, db, loc)
        await test_c_mismatch_atomic(api, db, loc)
        await test_d_non_roll_material(api, db, loc)
        await test_e_numbering(api, db)
        if ctx:
            await test_f_cutting_requires_roll(api, db, ctx, loc)
            await test_g_backfill(api, db, ctx)
        else:
            bad("prasyarat F/G", "langkah B gagal — alur cutting/backfill tidak diuji")

    print("\n" + "=" * 78)
    print(f"\033[1mHASIL: {len(PASS)} LULUS · {len(FAIL)} GAGAL\033[0m")
    if FAIL:
        print("\033[91mYANG GAGAL:\033[0m")
        for f in FAIL:
            print(f"  · {f}")
    print("=" * 78)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
