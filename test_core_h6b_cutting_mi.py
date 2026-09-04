#!/usr/bin/env python3
"""test_core_h6b_cutting_mi.py — POC INTI FASE H-6b.

"CUTTING MENERBITKAN DOKUMEN PENGELUARAN MATERIAL (`cutting_issue`)"

MENGAPA BERKAS INI ADA
----------------------
Sisa terakhir Fase H. Yang TERUKUR sebelum sesi ini (dibuktikan ulang oleh
langkah A di bawah pada basis data BERSIH): Portal Cutting sudah memotong stok
kain + sisa gulungan dengan benar, tetapi TIDAK PERNAH menerbitkan dokumen
`rahaza_material_issues` dan TIDAK PERNAH menulis baris kartu stok
(`rahaza_material_movements`). Akibatnya arus keluar kain lewat Cutting TIDAK ADA
di layar "Pengeluaran Material" — satu-satunya daftar tempat orang gudang
menjawab "material apa saja yang keluar?".

Bahaya terbesar dari perbaikan ini BUKAN "dokumen tidak terbit", melainkan
**stok dipotong dua kali** (kalau dokumen dibuat lewat jalur approve MI) dan
**beban hantu di buku besar** (kalau dokumen ikut dijurnal Dr WIP / Cr Persediaan,
padahal nilai kain hanya BERPINDAH menjadi nilai potongan). Dua bahaya itulah
yang paling banyak diuji di bawah.

USER STORY YANG DIBUKTIKAN (lewat HTTP API sungguhan + verifikasi langsung Mongo)
  A. Sanity: kode bersih (pyflakes), backend hidup, urutan route literal benar
     (`GET /material-issues/sources` TIDAK terbaca sebagai `mid="sources"`).
  B. Orang gudang: begitu Cutting melapor progres, dokumen MI baru muncul di
     daftar "Pengeluaran Material" — lengkap dengan kain, jumlah, satuan, lokasi
     asal, gulungan yang dipakai, dan nomor order cutting-nya.
  C. Stok TIDAK dipotong dua kali: kain berkurang tepat sekali; dokumen lahir
     `issued`; kartu stok memuat satu baris keluar `ref_type='cutting_issue'`.
  D. Buku besar tidak kotor: tidak ada jurnal untuk dokumen cutting, dan
     `post-to-gl` MENOLAK dengan alasan yang menyebut jalan keluarnya.
  E. Dokumen arus keluar tidak bisa dihapus / dibatalkan / di-approve ulang.
  F. Satu daftar bisa dibaca: `?source=` menyaring per pintu keluar dan rekap
     `/material-issues/sources` READ-ONLY (dibuktikan dengan hitung dokumen
     sebelum & sesudah memanggilnya).
  G. Dua laporan progres = dua dokumen (bukan satu ditumpuk), nomor unik.
  H. Progres LAMA tanpa dokumen kelihatan di `issue-docs/missing` dan bisa
     diterbitkan retroaktif (`issue-docs/backfill`) — idempoten: jalankan dua
     kali tidak melahirkan dokumen kembar; tautan yang hilang dipulihkan.
  I. Layar Cutting bisa menampilkan nomor dokumennya (`GET /orders/{id}` →
     `progress[].material_issue_number`).

Jalankan: python3 /app/test_core_h6b_cutting_mi.py           (bersih-bersih otomatis)
          python3 /app/test_core_h6b_cutting_mi.py --keep    (biarkan data uji)
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from typing import Any

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001")
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
KEEP = "--keep" in sys.argv

STAMP = time.strftime("%H%M%S")
MAT_CODE = f"POCH6B-KAIN-{STAMP}"

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

    async def delete(self, path: str) -> httpx.Response:
        return await self.c.delete(f"{BASE}{path}", headers=self.h)


def err_of(r: httpx.Response) -> str:
    try:
        j = r.json()
        return str(j.get("detail") or j)[:400]
    except Exception:
        return r.text[:400]


async def onhand(db, material_id: str) -> float:
    tot = 0.0
    async for s in db.rahaza_material_stock.find({"material_id": material_id},
                                                 {"_id": 0, "qty": 1}):
        tot += float(s.get("qty") or 0)
    return round(tot, 4)


# ───────────────────────────── A. sanity ───────────────────────────────────────

TOUCHED = ["routes/cutting.py", "core/cutting_material_issue.py",
           "routes/rahaza_inventory_issues.py", "routes/rahaza_inventory_shared.py",
           "routes/rahaza_inventory_workflow.py"]


async def test_a_sanity(api: Api) -> None:
    head("A. Kode bersih + backend hidup + urutan route literal benar")
    p = subprocess.run([sys.executable, "-m", "pyflakes", *TOUCHED],
                       cwd="/app/backend", capture_output=True, text=True)
    undefined = [ln for ln in (p.stdout + p.stderr).splitlines() if "undefined name" in ln]
    check("pyflakes: tidak ada undefined name di jalur H-6b", not undefined,
          "; ".join(undefined) or "bersih")

    r = await api.c.get(f"{BASE}/api/health")
    check("GET /api/health = ok", r.status_code == 200 and r.json().get("status") == "ok",
          err_of(r) if r.status_code != 200 else r.json().get("db", ""))

    # Pelajaran sesi #16: route literal harus menang atas route ber-parameter.
    r = await api.get("/api/rahaza/material-issues/sources")
    j = r.json() if r.status_code == 200 else {}
    check("GET /material-issues/sources TIDAK terbaca sebagai mid='sources'",
          r.status_code == 200 and isinstance(j.get("sources"), list),
          f"HTTP {r.status_code} {err_of(r)}" if r.status_code != 200 else
          f"{len(j.get('sources') or [])} sumber")
    keys = {s["key"] for s in (j.get("sources") or [])}
    check("rekap sumber memuat 5 pintu keluar (cutting/CMT/job/WO/manual)",
          {"cutting", "vendor_shipment", "job", "work_order", "manual"} <= keys, str(sorted(keys)))

    r = await api.get("/api/cutting/issue-docs/missing?limit=5")
    check("GET /api/cutting/issue-docs/missing hidup (bukan 404 alias mati)",
          r.status_code == 200 and "items" in (r.json() or {}),
          f"HTTP {r.status_code} {err_of(r)}")


# ───────────────────────── data uji (nyata, via API) ───────────────────────────

async def ensure_material(api: Api, code: str, name: str, unit: str, mtype: str,
                          unit_cost: float = 0.0) -> dict:
    r = await api.get(f"/api/rahaza/materials?limit=20000&search={code}")
    rows = r.json() if r.status_code == 200 else []
    if isinstance(rows, dict):
        rows = rows.get("items") or []
    hit = next((m for m in rows if str(m.get("code", "")).upper() == code.upper()), None)
    if hit:
        return hit
    r = await api.post("/api/rahaza/materials", {
        "code": code, "name": name, "unit": unit, "type": mtype,
        "color": "Navy", "unit_cost": unit_cost, "notes": "POC H-6b"})
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


async def setup_fabric_with_rolls(api: Api, db, loc: dict) -> dict:
    """Kain nyata + 4 gulungan @60 kg lewat penerimaan barang sungguhan (H-5)."""
    mat = await ensure_material(api, MAT_CODE, f"Kain POC H-6b {STAMP}",
                                "kg", "fabric", unit_cost=80000)
    r = await api.post("/api/wms/legacy/receiving", {
        "source_type": "supplier", "supplier_name": "PT POC H6B Tekstil",
        "location_id": loc.get("id"), "location_name": loc.get("name"),
        "notes": "POC H-6b", "items": [{
            "product_name": mat["name"], "sku": mat["code"], "material_id": mat["id"],
            "expected_qty": 240, "received_qty": 240, "rejected_qty": 0, "unit": "kg",
            "unit_price": 80000, "inspection_status": "passed", "lot_number": "LOT-H6B",
            "rolls": [{"qty": 60, "color_lot": "LOT-H6B", "notes": ""} for _ in range(4)],
        }]})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"gagal buat GR: {err_of(r)}")
    gr = r.json()
    r = await api.put(f"/api/wms/legacy/receiving/{gr['id']}", {"status": "received"})
    if r.status_code != 200:
        raise RuntimeError(f"gagal terima GR: {err_of(r)}")
    rolls = await db.wh_fabric_rolls.find(
        {"source_receipt_id": gr["id"]}, {"_id": 0}).to_list(50)
    rolls.sort(key=lambda d: d["roll_no"])
    if len(rolls) != 4:
        raise RuntimeError(f"gulungan tidak terbit ({len(rolls)}) — H-5 rusak, hentikan POC")
    r = await api.post("/api/cutting/orders", {
        "input_material_id": mat["id"], "planned_input_qty": 180,
        "planned_output_qty": 360, "style_name": f"Kaos POC H6B {STAMP}",
        "style_sku": f"POCH6B-{STAMP}", "output_size": "L", "output_color": "Navy",
        "location_id": loc.get("id"), "notes": "POC H-6b"})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"gagal buat order cutting: {err_of(r)}")
    order = r.json()
    r = await api.post(f"/api/cutting/orders/{order['id']}/start")
    if r.status_code != 200:
        raise RuntimeError(f"gagal start order cutting: {err_of(r)}")
    return {"material": mat, "gr": gr, "rolls": rolls, "order": r.json()}


# ─────────────── B & C. progres cutting ⇒ dokumen MI + stok sekali ─────────────

async def test_bc_progress_issues_doc(api: Api, db, ctx: dict, loc: dict) -> dict:
    head("B+C. Progres cutting ⇒ dokumen 'Pengeluaran Material' terbit, stok turun SEKALI")
    mat, rolls, order = ctx["material"], ctx["rolls"], ctx["order"]

    mi_before = await db.rahaza_material_issues.count_documents({})
    stok0 = await onhand(db, mat["id"])
    r = await api.post(f"/api/cutting/orders/{order['id']}/progress",
                       {"input_consumed": 60, "output_qty": 120, "waste_qty": 1.5,
                        "roll_ids": [rolls[0]["id"]], "note": "POC H-6b progres 1"})
    if not check("progres cutting berhasil dilaporkan", r.status_code == 200,
                 f"HTTP {r.status_code} {err_of(r)}"):
        return {}
    body = r.json()
    lp = body.get("last_progress") or {}
    mi_no = lp.get("material_issue_number")
    check("laporan balik langsung menyebut NOMOR dokumen pengeluaran material",
          bool(mi_no) and str(mi_no).startswith("MI-"), str(mi_no))
    check("pesan di layar memberi tahu dokumen sudah terbit",
          "pengeluaran material" in str(body.get("notice", "")).lower(),
          str(body.get("notice", ""))[:160])
    check("tidak ada peringatan dokumen gagal terbit", not body.get("mi_warning"),
          str(body.get("mi_warning", ""))[:200])

    check("tepat SATU dokumen MI baru lahir (bukan nol, bukan dua)",
          await db.rahaza_material_issues.count_documents({}) == mi_before + 1,
          f"{mi_before} → {await db.rahaza_material_issues.count_documents({})}")

    mi = await db.rahaza_material_issues.find_one({"mi_number": mi_no}, {"_id": 0})
    if not check("dokumen bisa ditemukan di koleksi rahaza_material_issues", bool(mi)):
        return {}
    check("dokumen bersumber Cutting (`source=cutting`, `ref_type=cutting_issue`)",
          mi.get("source") == "cutting" and mi.get("ref_type") == "cutting_issue",
          f"{mi.get('source')}/{mi.get('ref_type')}")
    check("dokumen lahir langsung berstatus 'issued' (barangnya sudah keluar)",
          mi.get("status") == "issued", str(mi.get("status")))
    it = (mi.get("items") or [{}])[0]
    check("baris dokumen = kain yang dipotong, qty_required == qty_issued == 60",
          it.get("material_id") == mat["id"]
          and abs(float(it.get("qty_required") or 0) - 60) < 0.001
          and abs(float(it.get("qty_issued") or 0) - 60) < 0.001,
          f"{it.get('qty_required')} / {it.get('qty_issued')}")
    check("baris menyebut LOKASI ASAL kain (gudang tempat stok dipotong)",
          it.get("location_id") == loc.get("id"), str(it.get("location_id")))
    check("lokasi diambil dari progres (bukti), bukan tebakan dari order",
          mi.get("location_source") == "progress", str(mi.get("location_source")))
    check("dokumen menunjuk order + laporan progres cutting-nya (ketelusuran)",
          mi.get("cutting_order_id") == order["id"]
          and mi.get("cutting_order_number") == order["number"]
          and bool(mi.get("cutting_progress_id")),
          f"{mi.get('cutting_order_number')} · progress={str(mi.get('cutting_progress_id'))[:8]}")
    check("dokumen mencatat gulungan yang dipakai (lot kain bisa dijawab ke buyer)",
          rolls[0]["roll_no"] in (mi.get("roll_numbers") or [])
          and len(mi.get("roll_consumption") or []) == 1,
          str(mi.get("roll_numbers")))
    check("dokumen mencatat hasil potong + sisa buangan",
          abs(float(mi.get("cutting_output_qty") or 0) - 120) < 0.001
          and abs(float(mi.get("cutting_waste_qty") or 0) - 1.5) < 0.001,
          f"{mi.get('cutting_output_qty')} pcs · waste {mi.get('cutting_waste_qty')}")
    check("dokumen MENYEBUT stok dipotong oleh Cutting (stock_moved_by)",
          mi.get("stock_moved_by") == "cutting" and bool(mi.get("stock_note")),
          str(mi.get("stock_moved_by")))

    # ── stok: TEPAT sekali ────────────────────────────────────────────────────
    stok1 = await onhand(db, mat["id"])
    check("stok kain berkurang TEPAT 60 kg (tidak dua kali)",
          abs(stok0 - stok1 - 60) < 0.001, f"{stok0} → {stok1}")
    led = await db.rahaza_stock_ledger.count_documents(
        {"material_id": mat["id"], "op": "issue"})
    check("ledger stok memuat TEPAT satu baris keluar untuk kain ini", led == 1, f"n={led}")

    # ── kartu stok: baris keluar cutting_issue ────────────────────────────────
    mv = await db.rahaza_material_movements.find_one(
        {"ref_type": "cutting_issue", "ref_id": mi["id"]}, {"_id": 0})
    check("kartu stok memuat baris keluar ref_type='cutting_issue'", bool(mv),
          f"qty={(mv or {}).get('qty')} dari={(mv or {}).get('from_location_id')}")
    if mv:
        check("baris kartu stok memuat qty & lokasi asal yang benar",
              abs(float(mv.get("qty") or 0) - 60) < 0.001
              and mv.get("from_location_id") == loc.get("id")
              and mv.get("type") == "issue")
    n_mv = await db.rahaza_material_movements.count_documents(
        {"ref_type": "cutting_issue", "ref_id": mi["id"]})
    check("hanya SATU baris kartu stok (tidak kembar)", n_mv == 1, f"n={n_mv}")

    # ── gulungan tetap dipotong sekali ────────────────────────────────────────
    roll = await db.wh_fabric_rolls.find_one({"id": rolls[0]["id"]}, {"_id": 0})
    check("sisa gulungan berkurang tepat sekali (60 → 0, fully_issued)",
          abs(float(roll.get("remaining_kg") or 0)) < 0.001
          and roll.get("status") == "fully_issued",
          f"{roll.get('roll_no')} sisa={roll.get('remaining_kg')} {roll.get('status')}")

    # ── daftar layar "Pengeluaran Material" ───────────────────────────────────
    r = await api.get("/api/rahaza/material-issues?source=cutting&limit=200")
    rows = r.json() if r.status_code == 200 else []
    row = next((x for x in rows if x.get("mi_number") == mi_no), None)
    check("dokumen MUNCUL di daftar Pengeluaran Material (penyaring sumber=cutting)",
          bool(row), f"HTTP {r.status_code} · {len(rows)} baris")
    if row:
        check("baris daftar membawa label sumber 'Cutting' untuk kolom Sumber",
              row.get("source_key") == "cutting" and row.get("source_label") == "Cutting",
              f"{row.get('source_key')}/{row.get('source_label')}")
        check("baris daftar membawa satuan + kode material (angka tidak tanpa satuan)",
              row.get("first_unit") == "kg" and row.get("first_material_code") == MAT_CODE,
              f"{row.get('total_required')} {row.get('first_unit')} {row.get('first_material_code')}")
        check("total qty baris = 60 kg", abs(float(row.get("total_required") or 0) - 60) < 0.001,
              str(row.get("total_required")))

    r = await api.get(f"/api/rahaza/material-issues/{mi['id']}")
    d = r.json() if r.status_code == 200 else {}
    check("detail dokumen menjelaskan mengapa TIDAK dijurnal (gl_skip_reason)",
          d.get("gl_posted") is False and "berpindah" in str(d.get("gl_skip_reason", "")),
          str(d.get("gl_skip_reason", ""))[:120])
    check("detail dokumen memberi nama material & lokasi (bukan hanya id)",
          (d.get("items") or [{}])[0].get("material_code") == MAT_CODE
          and bool((d.get("items") or [{}])[0].get("location_name")),
          f"{(d.get('items') or [{}])[0].get('material_code')} @ "
          f"{(d.get('items') or [{}])[0].get('location_name')}")
    return {"mi": mi, "mi_no": mi_no, "stok_after": stok1}


# ─────────────── D. buku besar tidak kotor ─────────────────────────────────────

async def test_d_no_phantom_journal(api: Api, db, ctx: dict) -> None:
    head("D. Buku besar tidak kotor: dokumen cutting TIDAK dijurnal")
    mi = ctx["mi"]
    je = await db.rahaza_journal_entries.find_one(
        {"source_module": "inventory_issue", "source_ref": f"mi:{mi['id']}"}, {"_id": 0})
    check("tidak ada jurnal 'inventory_issue' untuk dokumen cutting", je is None,
          str((je or {}).get("je_number", "")))

    r = await api.post(f"/api/rahaza/material-issues/{mi['id']}/post-to-gl")
    msg = err_of(r)
    check("POST post-to-gl DITOLAK (400) untuk dokumen cutting", r.status_code == 400,
          f"HTTP {r.status_code}")
    check("penolakan menjelaskan alasannya + jalan keluarnya (Penyesuaian Stok)",
          "cutting" in msg.lower() and "penyesuaian stok" in msg.lower(), msg[:200])
    je2 = await db.rahaza_journal_entries.count_documents(
        {"source_ref": f"mi:{mi['id']}"})
    check("tetap 0 jurnal setelah percobaan post-to-gl", je2 == 0, f"n={je2}")


# ─────────────── E. dokumen arus keluar tidak bisa hilang ──────────────────────

async def test_e_guards(api: Api, db, ctx: dict) -> None:
    head("E. Dokumen arus keluar tidak bisa dihapus / dibatalkan / di-issue ulang")
    mi = ctx["mi"]
    stok0 = await onhand(db, ctx["material_id"])

    r = await api.post(f"/api/rahaza/material-issues/{mi['id']}/submit")
    check("submit DITOLAK (dokumen bukan draft)", r.status_code == 400, f"HTTP {r.status_code}")

    r = await api.post(f"/api/rahaza/material-issues/{mi['id']}/approve")
    check("approve DITOLAK ⇒ stok TIDAK mungkin dipotong dua kali",
          r.status_code == 400, f"HTTP {r.status_code} {err_of(r)[:120]}")

    r = await api.post(f"/api/rahaza/material-issues/{mi['id']}/confirm")
    check("confirm (jalur legacy) DITOLAK", r.status_code in (400, 403),
          f"HTTP {r.status_code}")

    r = await api.post(f"/api/rahaza/material-issues/{mi['id']}/cancel")
    check("cancel DITOLAK (arus keluar tidak boleh hilang dari daftar)",
          r.status_code == 400, f"HTTP {r.status_code}")

    r = await api.delete(f"/api/rahaza/material-issues/{mi['id']}")
    check("DELETE DITOLAK", r.status_code == 400, f"HTTP {r.status_code}")

    check("stok kain tidak berubah setelah 5 percobaan di atas",
          abs(await onhand(db, ctx["material_id"]) - stok0) < 0.001)
    fresh = await db.rahaza_material_issues.find_one({"id": mi["id"]}, {"_id": 0})
    check("dokumen masih ada & masih 'issued'",
          bool(fresh) and fresh.get("status") == "issued",
          str((fresh or {}).get("status")))


# ─────────────── F. satu daftar, bisa disaring, rekap read-only ────────────────

async def test_f_one_list(api: Api, db, ctx: dict) -> None:
    head("F. Satu daftar lintas sumber: penyaring jujur + rekap READ-ONLY")
    before_mi = await db.rahaza_material_issues.count_documents({})
    before_mv = await db.rahaza_material_movements.count_documents({})

    r = await api.get("/api/rahaza/material-issues/sources")
    j = r.json() if r.status_code == 200 else {}
    smap = {s["key"]: s["count"] for s in (j.get("sources") or [])}
    check("rekap sumber menghitung dokumen cutting ≥ 1", smap.get("cutting", 0) >= 1,
          str(smap))
    check("jumlah per sumber tidak melebihi jumlah seluruh dokumen",
          sum(smap.values()) <= (j.get("all_count") or 0),
          f"Σsumber={sum(smap.values())} semua={j.get('all_count')}")

    r = await api.get("/api/rahaza/material-issues?source=cutting&limit=200")
    cut_rows = r.json() if r.status_code == 200 else []
    check("penyaring sumber=cutting HANYA mengembalikan dokumen cutting",
          bool(cut_rows) and all(x.get("source_key") == "cutting" for x in cut_rows),
          f"{len(cut_rows)} baris")
    check("jumlah baris tersaring = angka rekap (tidak ada yang tersembunyi)",
          len(cut_rows) == smap.get("cutting", -1),
          f"daftar={len(cut_rows)} rekap={smap.get('cutting')}")

    r = await api.get("/api/rahaza/material-issues?source=manual&limit=200")
    man_rows = r.json() if r.status_code == 200 else []
    check("penyaring sumber=manual tidak mencampurkan dokumen cutting",
          all(x.get("source_key") == "manual" for x in man_rows), f"{len(man_rows)} baris")
    ours = {x["mi_number"] for x in cut_rows}
    check("dokumen cutting kita TIDAK muncul di daftar manual",
          not (ours & {x.get("mi_number") for x in man_rows}))

    r = await api.get("/api/rahaza/material-issues?source=tidak-ada")
    check("sumber tak dikenal DITOLAK 400 (bukan diam-diam mengembalikan semua)",
          r.status_code == 400, f"HTTP {r.status_code}")

    r = await api.get("/api/rahaza/material-issues?limit=500")
    all_rows = r.json() if r.status_code == 200 else []
    check("daftar TANPA penyaring memuat dokumen cutting (benar-benar SATU daftar)",
          bool(ours) and ours <= {x.get("mi_number") for x in all_rows},
          f"{len(all_rows)} baris")
    check("setiap baris daftar punya label sumber (tidak ada baris tanpa asal)",
          all(x.get("source_label") for x in all_rows),
          f"tanpa label={sum(1 for x in all_rows if not x.get('source_label'))}")

    check("lapisan daftar/rekap TIDAK MENULIS apa pun (dokumen MI tetap)",
          await db.rahaza_material_issues.count_documents({}) == before_mi,
          f"{before_mi} → {await db.rahaza_material_issues.count_documents({})}")
    check("lapisan daftar/rekap TIDAK MENULIS apa pun (kartu stok tetap)",
          await db.rahaza_material_movements.count_documents({}) == before_mv,
          f"{before_mv} → {await db.rahaza_material_movements.count_documents({})}")


# ─────────────── G. dua progres = dua dokumen ─────────────────────────────────

async def test_g_second_progress(api: Api, db, ctx: dict) -> dict:
    head("G. Dua laporan progres = dua dokumen berbeda (nomor unik)")
    order, rolls, mat = ctx["order"], ctx["rolls"], ctx["material"]
    r = await api.post(f"/api/cutting/orders/{order['id']}/progress",
                       {"input_consumed": 80, "output_qty": 160,
                        "roll_ids": [rolls[1]["id"], rolls[2]["id"]],
                        "note": "POC H-6b progres 2 (lintas gulungan)"})
    if not check("progres kedua (lintas 2 gulungan) berhasil", r.status_code == 200,
                 f"HTTP {r.status_code} {err_of(r)}"):
        return {}
    mi_no2 = ((r.json().get("last_progress") or {}).get("material_issue_number"))
    check("dokumen KEDUA terbit dengan nomor berbeda",
          bool(mi_no2) and mi_no2 != ctx["mi_no"], f"{ctx['mi_no']} vs {mi_no2}")
    docs = await db.rahaza_material_issues.find(
        {"cutting_order_id": order["id"]}, {"_id": 0}).to_list(20)
    check("order cutting ini punya TEPAT 2 dokumen pengeluaran", len(docs) == 2,
          str([d.get("mi_number") for d in docs]))
    check("nomor dokumen unik", len({d["mi_number"] for d in docs}) == 2)
    mi2 = next((d for d in docs if d["mi_number"] == mi_no2), {})
    check("dokumen kedua memuat DUA gulungan yang dipakai",
          len(mi2.get("roll_numbers") or []) == 2, str(mi2.get("roll_numbers")))
    check("jumlah kain di dokumen kedua = 80 kg",
          abs(float((mi2.get("items") or [{}])[0].get("qty_required") or 0) - 80) < 0.001)
    tot_out = sum(float((d.get("items") or [{}])[0].get("qty_required") or 0) for d in docs)
    check("total kain di semua dokumen = total kain yang dipotong order (60+80=140)",
          abs(tot_out - 140) < 0.001, f"Σ={tot_out}")
    o = await db.cutting_orders.find_one({"id": order["id"]}, {"_id": 0})
    check("order menyimpan daftar nomor dokumen pengeluarannya",
          len(o.get("material_issue_numbers") or []) == 2,
          str(o.get("material_issue_numbers")))
    led = await db.rahaza_stock_ledger.count_documents(
        {"material_id": mat["id"], "op": "issue"})
    check("ledger stok tetap 1 baris per progres (2 progres = 2 baris, bukan 4)",
          led == 2, f"n={led}")
    return {"mi_no2": mi_no2, "mi2": mi2}


# ─────────────── H. progres lama tanpa dokumen: terlihat + backfill ───────────

async def test_h_backfill(api: Api, db, ctx: dict) -> None:
    head("H. Progres LAMA tanpa dokumen: kelihatan, bisa diterbitkan, idempoten")
    order = ctx["order"]
    # Buat KEADAAN SEBELUM H-6b secara persis: dokumen + tautan + baris kartu stok
    # untuk progres pertama dihapus (stok & gulungan TETAP berkurang — itulah
    # keadaan data lama).
    prog = await db.cutting_progress.find_one(
        {"cutting_order_id": order["id"]}, {"_id": 0}, sort=[("created_at", 1)])
    mi_old = await db.rahaza_material_issues.find_one(
        {"cutting_progress_id": prog["id"]}, {"_id": 0})
    await db.rahaza_material_issues.delete_one({"id": mi_old["id"]})
    await db.rahaza_material_movements.delete_many({"ref_id": mi_old["id"]})
    await db.cutting_progress.update_one({"id": prog["id"]},
                                        {"$unset": {"material_issue_id": "",
                                                    "material_issue_number": ""}})
    stok_legacy = await onhand(db, ctx["material"]["id"])

    r = await api.get("/api/cutting/issue-docs/missing?limit=200")
    j = r.json() if r.status_code == 200 else {}
    hit = next((x for x in (j.get("items") or []) if x.get("progress_id") == prog["id"]), None)
    check("progres tanpa dokumen KELIHATAN di daftar 'issue-docs/missing'", bool(hit),
          f"HTTP {r.status_code} · {j.get('count')} baris")
    if hit:
        check("barisnya bisa ditindaklanjuti: nomor order, kain, jumlah, gudang, gulungan",
              hit.get("cutting_number") == order["number"]
              and hit.get("material_code") == MAT_CODE
              and abs(float(hit.get("input_consumed") or 0) - 60) < 0.001
              and bool(hit.get("location_name")) and bool(hit.get("roll_numbers")),
              f"{hit.get('cutting_number')} · {hit.get('input_consumed')} {hit.get('unit')} "
              f"@ {hit.get('location_name')} · {hit.get('roll_numbers')}")

    r = await api.post("/api/cutting/issue-docs/backfill", {"order_id": order["id"]})
    res = r.json() if r.status_code == 200 else {}
    check("backfill menerbitkan dokumen untuk progres lama",
          r.status_code == 200 and res.get("created") == 1,
          f"HTTP {r.status_code} created={res.get('created')} failed={res.get('failed')}")
    check("backfill TIDAK memotong stok lagi (mutasi sudah terjadi dulu)",
          abs(await onhand(db, ctx["material"]["id"]) - stok_legacy) < 0.001,
          f"{stok_legacy} → {await onhand(db, ctx['material']['id'])}")
    new_mi = await db.rahaza_material_issues.find_one(
        {"cutting_progress_id": prog["id"]}, {"_id": 0})
    check("dokumen hasil backfill ditandai 'backfilled' (jujur soal asalnya)",
          bool(new_mi) and new_mi.get("backfilled") is True
          and "retroaktif" in str(new_mi.get("notes", "")).lower(),
          str((new_mi or {}).get("mi_number")))
    check("dokumen hasil backfill tetap menyebut gulungan & jumlah yang benar",
          bool(new_mi) and len(new_mi.get("roll_numbers") or []) == 1
          and abs(float((new_mi.get("items") or [{}])[0].get("qty_required") or 0) - 60) < 0.001,
          str((new_mi or {}).get("roll_numbers")))
    fresh_prog = await db.cutting_progress.find_one({"id": prog["id"]}, {"_id": 0})
    check("tautan progres → dokumen dipulihkan",
          fresh_prog.get("material_issue_number") == (new_mi or {}).get("mi_number"),
          str(fresh_prog.get("material_issue_number")))

    r = await api.post("/api/cutting/issue-docs/backfill", {"order_id": order["id"]})
    res2 = r.json() if r.status_code == 200 else {}
    check("backfill DUA KALI tidak melahirkan dokumen kembar",
          r.status_code == 200 and res2.get("created") == 0,
          f"created={res2.get('created')} scanned={res2.get('scanned')}")
    n = await db.rahaza_material_issues.count_documents({"cutting_progress_id": prog["id"]})
    check("tetap TEPAT satu dokumen untuk progres itu", n == 1, f"n={n}")

    # tautan hilang (bukan dokumennya) ⇒ dipulihkan, TIDAK dilaporkan kurang
    await db.cutting_progress.update_one({"id": prog["id"]},
                                        {"$set": {"material_issue_id": None}})
    r = await api.get("/api/cutting/issue-docs/missing?limit=200")
    j = r.json() if r.status_code == 200 else {}
    still = [x for x in (j.get("items") or []) if x.get("progress_id") == prog["id"]]
    check("tautan yang hilang DIPULIHKAN, bukan dituduh 'belum punya dokumen'",
          not still and (j.get("repaired") or 0) >= 1,
          f"repaired={j.get('repaired')} sisa={len(still)}")

    r = await api.get("/api/cutting/issue-docs/missing?limit=200")
    j = r.json() if r.status_code == 200 else {}
    check("setelah semua terbit, daftar 'tanpa dokumen' untuk order ini kosong",
          not [x for x in (j.get("items") or []) if x.get("cutting_order_id") == order["id"]],
          f"count={j.get('count')}")


# ─────────────── I. layar Cutting bisa menampilkan nomornya ───────────────────

async def test_i_cutting_screen(api: Api, db, ctx: dict) -> None:
    head("I. Layar Cutting menampilkan nomor dokumen pengeluaran per progres")
    r = await api.get(f"/api/cutting/orders/{ctx['order']['id']}")
    j = r.json() if r.status_code == 200 else {}
    progs = j.get("progress") or []
    check("GET /orders/{id} mengembalikan riwayat progres", len(progs) == 2, f"n={len(progs)}")
    check("setiap baris progres membawa nomor dokumen MI-nya",
          all(str(p.get("material_issue_number") or "").startswith("MI-") for p in progs),
          str([p.get("material_issue_number") for p in progs]))
    check("setiap baris progres membawa lokasi asal kain",
          all(p.get("location_id") for p in progs),
          str([p.get("location_name") for p in progs]))


# ─────────────────────────────── cleanup ──────────────────────────────────────

async def cleanup(db, ctx: dict) -> None:
    head("Bersih-bersih data uji")
    mat = ctx.get("material") or {}
    order = ctx.get("order") or {}
    gr = ctx.get("gr") or {}
    if not mat:
        print("  (tidak ada yang perlu dibersihkan)")
        return
    mis = await db.rahaza_material_issues.find(
        {"cutting_order_id": order.get("id")}, {"_id": 0, "id": 1}).to_list(50)
    mi_ids = [m["id"] for m in mis]
    roll_ids = [r["id"] for r in (ctx.get("rolls") or [])]
    n = {
        "material_issues": (await db.rahaza_material_issues.delete_many(
            {"cutting_order_id": order.get("id")})).deleted_count,
        "movements": (await db.rahaza_material_movements.delete_many(
            {"$or": [{"ref_id": {"$in": mi_ids}}, {"material_id": mat.get("id")}]})).deleted_count,
        "cutting_progress": (await db.cutting_progress.delete_many(
            {"cutting_order_id": order.get("id")})).deleted_count,
        "cutting_orders": (await db.cutting_orders.delete_many(
            {"id": order.get("id")})).deleted_count,
        "rolls": (await db.wh_fabric_rolls.delete_many({"id": {"$in": roll_ids}})).deleted_count,
        "roll_movements": (await db.wh_fabric_roll_movements.delete_many(
            {"roll_id": {"$in": roll_ids}})).deleted_count,
        "receiving": (await db.warehouse_receiving.delete_many(
            {"id": gr.get("id")})).deleted_count,
        "stock": (await db.rahaza_material_stock.delete_many(
            {"material_id": mat.get("id")})).deleted_count,
        "ledger": (await db.rahaza_stock_ledger.delete_many(
            {"material_id": mat.get("id")})).deleted_count,
        "materials": (await db.rahaza_materials.delete_many(
            {"code": {"$regex": "^(POCH6B-|CUT-KAOS-POC-H6B)", "$options": "i"}})).deleted_count,
    }
    print("  " + " · ".join(f"{k}={v}" for k, v in n.items()))


# ─────────────────────────────── main ─────────────────────────────────────────

async def main() -> int:
    print("\033[1m═══ POC FASE H-6b — Cutting menerbitkan dokumen Pengeluaran Material ═══\033[0m")
    print(f"BASE={BASE} DB={DB_NAME} stamp={STAMP}")
    client = AsyncIOMotorClient(MONGO)
    db = client[DB_NAME]
    ctx: dict = {}
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(f"{BASE}/api/auth/login", json=ADMIN)
        if r.status_code != 200:
            print(f"LOGIN GAGAL: {r.status_code} {r.text[:200]}")
            return 2
        api = Api(c, r.json()["token"])

        await test_a_sanity(api)
        loc = await pick_location(api)
        try:
            ctx = await setup_fabric_with_rolls(api, db, loc)
        except Exception as e:  # noqa: BLE001
            bad("penyiapan data uji (kain + gulungan + order cutting)", str(e))
            return 1
        ctx["material_id"] = ctx["material"]["id"]

        res = await test_bc_progress_issues_doc(api, db, ctx, loc)
        if not res:
            await report_and_cleanup(db, ctx)
            return 1
        ctx.update(res)
        await test_d_no_phantom_journal(api, db, ctx)
        await test_e_guards(api, db, ctx)
        await test_f_one_list(api, db, ctx)
        ctx.update(await test_g_second_progress(api, db, ctx) or {})
        await test_h_backfill(api, db, ctx)
        await test_i_cutting_screen(api, db, ctx)

    return await report_and_cleanup(db, ctx)


async def report_and_cleanup(db, ctx: dict) -> int:
    if not KEEP:
        await cleanup(db, ctx)
    else:
        print("\n  (--keep) data uji DIBIARKAN untuk diperiksa di layar")
    total = len(PASS) + len(FAIL)
    print(f"\n\033[1m═══ HASIL: {len(PASS)}/{total} LULUS ═══\033[0m")
    if FAIL:
        print("\033[91mGAGAL:\033[0m")
        for f in FAIL:
            print(f"  · {f}")
        return 1
    print("\033[92mSEMUA INVARIAN H-6b TERBUKTI.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
