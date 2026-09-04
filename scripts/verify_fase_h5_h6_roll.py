#!/usr/bin/env python3
"""verify_fase_h5_h6_roll.py — FASE H-5 & H-6 (2026-08-16).

Permintaan pemilik: *"kain harus punya gulungan sejak diterima, nomornya jangan
diketik, dan cutting tidak boleh memotong kain tanpa menunjuk gulungan."*

YANG TERUKUR SEBELUM PERBAIKAN (bukan dugaan):
  · `wh_fabric_rolls` hanya bisa diisi MANUAL dari layar Roll Kain dan nomor rollnya
    WAJIB diketik (`RollIn.roll_no` required) ⇒ dua gulungan fisik bisa bernomor sama.
    Isinya 4 dokumen `DEMO-RL-000x` — data contoh, bukan kain sungguhan.
  · Penerimaan barang (GR) menambah stok kain lewat `stock_service.add` TANPA pernah
    menyentuh roll ⇒ gudang bisa punya 420 kg kain di sistem dan NOL gulungan yang
    bisa ditunjuk.
  · Sesi sebelumnya berhenti di tengah: `routes/warehouse.py` memanggil
    `fabric_rolls.*` dan `fabric_roll_engine.*` tanpa satu pun modul di-import dan
    `rolls_created` belum diinisialisasi (pyflakes: 4 undefined name) ⇒ penerimaan
    kain dengan rincian roll NameError → 500, dan backend TETAP BISA START sehingga
    kerusakannya tidak terlihat sampai alurnya dijalankan.
  · Portal Cutting mengurangi sisa roll HANYA kalau `roll_id` dikirim, dan pemilihan
    roll bersifat OPSIONAL ⇒ kain bisa dipotong tanpa satu gulungan pun berkurang:
    stok turun, roll tetap penuh, dan pertanyaan "gulungan mana yang dipakai untuk
    order buyer ini" tidak bisa dijawab saat buyer menuntut lot kain yang sama.

INVARIAN YANG DIJAGA:
  R1  jalur roll bebas nama tak terdefinisi (pyflakes) — persis bug yang menghentikan
      sesi sebelumnya; kalau import hilang lagi, gate ini MERAH sebelum user kena 500
  R2  kebijakan nomor roll = OTOMATIS dan berpola (nomor tidak diketik)
  R3  GR kain + rincian roll ⇒ gulungan terbit bernomor otomatis, stok naik, movement
      'receive' tercatat, dan baris GR menyimpan roll_ids/roll_numbers (jejak dua arah)
  R4  rincian roll ≠ qty diterima ⇒ DITOLAK, stok TIDAK bertambah, GR tetap draft
      (validasi mendahului penulisan stok — tidak ada GR setengah jadi)
  R5  material bukan-kain (pcs) diberi rincian roll ⇒ DITOLAK dengan alasan jelas
  R6  GR kain TANPA rincian ⇒ dilaporkan (`rolls_pending`) + muncul di daftar
      "Penerimaan tanpa roll" + bisa diterbitkan retroaktif; penerbitan KEDUA 409
  R7  H-6: progres cutting tanpa gulungan ⇒ DITOLAK & stok utuh; dengan gulungan ⇒
      sisa gulungan berkurang FIFO + movement 'issue'; kain tanpa gulungan ⇒ order
      ditolak dengan JALAN KELUARNYA disebut
  R8  nomor roll ketikan DITOLAK; 12 penerbitan bersamaan tetap unik
  R9  layar: Penerimaan Barang punya editor rincian gulungan, Roll Kain tidak punya
      input nomor roll + punya tab "Penerimaan tanpa roll", Cutting menandai gulungan
      WAJIB dan mematikan tombol Catat sebelum gulungan dipilih

Pakai:
    python3 scripts/verify_fase_h5_h6_roll.py
    python3 scripts/verify_fase_h5_h6_roll.py --keep     # jangan bersih-bersih
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(ROOT / "backend"))
from gr_common import db_handle  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

MARK = "VERIFY-FASE-H5"
CODE_PREFIX = "VFH5-"
ROLL_NO_RE = re.compile(r"^RL-\d{6}-\d{4}$")

RECEIVING_JSX = ROOT / "frontend/src/components/erp/ReceivingModule.jsx"
ROLLS_JSX = ROOT / "frontend/src/components/erp/WMSFabricRollsModule.jsx"
CUTTING_JSX = ROOT / "frontend/src/components/erp/cutting/CuttingOrdersModule.jsx"
EDITOR_JSX = ROOT / "frontend/src/components/erp/warehouse/RollLinesEditor.jsx"

PASS, FAIL = [], []


def ok(code, msg, extra=""):
    PASS.append(code)
    print(f"{G}  ✓ {code}{X} {msg}" + (f"\n         {C}{extra}{X}" if extra else ""))


def bad(code, msg, extra=""):
    FAIL.append(code)
    print(f"{R}  ✗ {code}{X} {msg}" + (f"\n         {extra}" if extra else ""))


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return e.code, {"raw": raw}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def detail(resp) -> str:
    d = resp.get("detail")
    return d if isinstance(d, str) else json.dumps(resp)[:300]


def onhand(db, material_id: str) -> float:
    tot = 0.0
    for s in db.rahaza_material_stock.find({"material_id": material_id}, {"_id": 0, "qty": 1}):
        tot += float(s.get("qty") or 0)
    return round(tot, 4)


# ─── data uji (lewat API sungguhan) ──────────────────────────────────────────

def any_model_id(token):
    """Model/style DARI MASTER — sejak 2026-08-21 order cutting wajib menunjuk model."""
    st, rows = call("GET", "/api/rahaza/models", token)
    rows = rows if isinstance(rows, list) else (rows or {}).get("items") or []
    live = next((m for m in rows if m.get("active") is not False), None)
    if live:
        return live["id"]
    st, d = call("POST", "/api/rahaza/models", token,
                 {"code": "MDL-GATE-H5", "name": "Model Gate H5"})
    if st not in (200, 201) or not (d or {}).get("id"):
        raise RuntimeError(f"gagal menyiapkan model master: {detail(d)}")
    return d["id"]

def material(token, suffix, unit, mtype="fabric", cost=50000.0):
    code = f"{CODE_PREFIX}{suffix}"
    st, r = call("POST", "/api/rahaza/materials", token, {
        "code": code, "name": f"Uji H5 {suffix}", "unit": unit, "type": mtype,
        "color": "Navy", "unit_cost": cost, "notes": MARK})
    if st in (200, 201):
        return (r.get("material") or r)
    st, rows = call("GET", f"/api/rahaza/materials?limit=20000&search={code}", token)
    rows = rows if isinstance(rows, list) else rows.get("items", [])
    hit = next((m for m in rows if m.get("code") == code), None)
    if not hit:
        raise RuntimeError(f"gagal menyiapkan material {code}: {detail(r)}")
    return hit


def storage_location(token):
    st, rows = call("GET", "/api/rahaza/storage-locations", token)
    rows = rows if isinstance(rows, list) else rows.get("items", [])
    if not rows:
        raise RuntimeError("tidak ada lokasi penyimpanan")
    return next((x for x in rows if "kain" in str(x.get("name", "")).lower()), rows[0])


def make_gr(token, loc, mat, qty, unit, rolls=None):
    item = {"product_name": mat["name"], "sku": mat["code"], "material_id": mat["id"],
            "expected_qty": qty, "received_qty": qty, "rejected_qty": 0, "unit": unit,
            "unit_price": 50000, "inspection_status": "passed", "lot_number": "LOT-VFH5"}
    if rolls is not None:
        item["rolls"] = rolls
    st, r = call("POST", "/api/wms/legacy/receiving", token, {
        "source_type": "supplier", "supplier_name": MARK,
        "location_id": loc["id"], "location_name": loc["name"],
        "notes": MARK, "items": [item]})
    if st not in (200, 201):
        raise RuntimeError(f"gagal buat GR: {detail(r)}")
    return r


def receive(token, gr, items=None):
    body = {"status": "received"}
    if items is not None:
        body["items"] = items
    return call("PUT", f"/api/wms/legacy/receiving/{gr['id']}", token, body)


# ─── R9: layar ───────────────────────────────────────────────────────────────

def part_static():
    print(f"\n{B}[1] LAYAR{X}")
    rec, rolls, cut = RECEIVING_JSX.read_text(), ROLLS_JSX.read_text(), CUTTING_JSX.read_text()
    editor_ok = EDITOR_JSX.exists() and "roll-lines" in EDITOR_JSX.read_text()
    rec_ok = ("RollLinesEditor" in rec and "gr-roll-lines-" in rec
              and "gr-missing-rolls-banner" in rec)
    # nomor roll TIDAK boleh punya input; harus ada kotak "otomatis" + tab backfill
    rolls_ok = ('name="roll_no"' not in rolls and "roll-no-auto" in rolls
                and "tab-missing-rolls" in rolls and "submit-issue-rolls" in rolls)
    cut_ok = ("(WAJIB)" in cut and "rollBlocking" in cut
              and "disabled={acting || rollBlocking" in cut
              and "cutting-progress-roll-picker" in cut)
    if rec_ok and editor_ok:
        ok("R9a", "Penerimaan Barang punya editor rincian gulungan + peringatan kain tanpa roll")
    else:
        bad("R9a", "editor rincian gulungan / peringatan hilang dari Penerimaan Barang",
            f"receiving={rec_ok} editor={editor_ok}")
    if rolls_ok:
        ok("R9b", "Roll Kain: tanpa input nomor roll, ada tab 'Penerimaan tanpa roll' + tombol terbitkan")
    else:
        has_input = 'name="roll_no"' in rolls
        bad("R9b", "layar Roll Kain masih meminta nomor roll / kehilangan tab backfill",
            f"input_roll_no_ada={has_input} auto={'roll-no-auto' in rolls} "
            f"tab={'tab-missing-rolls' in rolls}")
    if cut_ok:
        ok("R9c", "Cutting menandai gulungan WAJIB & mematikan tombol Catat sebelum gulungan dipilih")
    else:
        bad("R9c", "layar Cutting tidak lagi mewajibkan gulungan", f"cut_ok={cut_ok}")


def part_pyflakes():
    print(f"\n{B}[2] KODE JALUR ROLL{X}")
    files = ["routes/warehouse.py", "routes/cutting.py", "routes/wms_fabric_rolls.py",
             "core/fabric_roll_engine.py"]
    p = subprocess.run([sys.executable, "-m", "pyflakes", *files],
                       cwd=str(ROOT / "backend"), capture_output=True, text=True)
    undef = [ln for ln in (p.stdout + p.stderr).splitlines() if "undefined name" in ln]
    if undef:
        bad("R1", "ada nama tak terdefinisi di jalur roll (persis bug yang menghentikan sesi lalu)",
            "; ".join(undef))
    else:
        ok("R1", "jalur roll bebas nama tak terdefinisi", f"{len(files)} berkas diperiksa (pyflakes)")


# ─── R2..R8: runtime ─────────────────────────────────────────────────────────

def part_runtime(db, token):
    stamp = datetime.now(timezone.utc).strftime("%m%d%H%M%S")
    loc = storage_location(token)

    print(f"\n{B}[3] NOMOR GULUNGAN{X}")
    st, pol = call("GET", "/api/wms/fabric-rolls/number-policy", token)
    nxt = str(pol.get("next_number") or "")
    if st == 200 and pol.get("mode") == "auto" and ROLL_NO_RE.match(nxt):
        ok("R2", "kebijakan nomor roll = OTOMATIS dan berpola",
           f"{pol.get('format')} · berikutnya {nxt}")
    else:
        bad("R2", "kebijakan nomor roll bukan otomatis / tidak berpola", json.dumps(pol)[:200])

    print(f"\n{B}[4] GULUNGAN LAHIR DARI PENERIMAAN (H-5){X}")
    m_kain = material(token, f"KAIN-{stamp}", "kg")
    before = onhand(db, m_kain["id"])
    gr = make_gr(token, loc, m_kain, 300, "kg",
                 rolls=[{"qty": 100, "color_lot": "LOT-VFH5"} for _ in range(3)])
    st, got = receive(token, gr)
    created = got.get("rolls_created") or []
    docs = list(db.wh_fabric_rolls.find({"source_receipt_id": gr["id"]}, {"_id": 0}))
    movs = db.wh_fabric_roll_movements.count_documents(
        {"reference_id": gr["id"], "movement_type": "receive"})
    fresh = db.warehouse_receiving.find_one({"id": gr["id"]}, {"_id": 0}) or {}
    it0 = (fresh.get("items") or [{}])[0]
    stock_after = onhand(db, m_kain["id"])
    if (st == 200 and len(created) == 3 and all(ROLL_NO_RE.match(n) for n in created)
            and len(docs) == 3 and movs == 3
            and abs(stock_after - before - 300) < 0.001
            and len(it0.get("roll_numbers") or []) == 3):
        ok("R3", "GR kain menerbitkan 3 gulungan bernomor otomatis + stok naik + jejak dua arah",
           f"{', '.join(created)} · stok {before} → {stock_after} kg · {movs} movement 'receive'")
    else:
        bad("R3", "penerimaan kain tidak menerbitkan gulungan dengan benar",
            f"HTTP {st} created={created} docs={len(docs)} movements={movs} "
            f"stok {before}→{stock_after} roll_numbers={it0.get('roll_numbers')} {detail(got)[:160]}")

    print(f"\n{B}[5] RINCIAN YANG TIDAK MENJELASKAN QTY (atomicity){X}")
    m_mis = material(token, f"MIS-{stamp}", "kg")
    b2 = onhand(db, m_mis["id"])
    gr2 = make_gr(token, loc, m_mis, 100, "kg", rolls=[{"qty": 30}, {"qty": 30}, {"qty": 30}])
    st2, r2 = receive(token, gr2)
    msg2 = detail(r2)
    st_doc = (db.warehouse_receiving.find_one({"id": gr2["id"]}, {"_id": 0, "status": 1}) or {}).get("status")
    n_roll2 = db.wh_fabric_rolls.count_documents({"source_receipt_id": gr2["id"]})
    if (st2 == 400 and "selisih" in msg2.lower() and abs(onhand(db, m_mis["id"]) - b2) < 0.001
            and n_roll2 == 0 and st_doc == "draft"):
        ok("R4", "rincian tidak cocok DITOLAK sebelum stok ditulis (GR tetap draft, 0 roll yatim)",
           msg2[:160])
    else:
        bad("R4", "penolakan rincian roll tidak atomik",
            f"HTTP {st2} status={st_doc} roll={n_roll2} stok={onhand(db, m_mis['id'])} {msg2[:160]}")

    print(f"\n{B}[6] MATERIAL BUKAN-KAIN{X}")
    m_pcs = material(token, f"PCS-{stamp}", "pcs", mtype="accessory", cost=250)
    b3 = onhand(db, m_pcs["id"])
    gr3 = make_gr(token, loc, m_pcs, 400, "pcs", rolls=[{"qty": 200}, {"qty": 200}])
    st3, r3 = receive(token, gr3)
    msg3 = detail(r3)
    if st3 == 400 and "gulungan" in msg3.lower() and abs(onhand(db, m_pcs["id"]) - b3) < 0.001:
        ok("R5", "material bersatuan pcs diberi rincian roll DITOLAK", msg3[:150])
    else:
        bad("R5", "material bukan-kain menerima rincian roll", f"HTTP {st3} {msg3[:180]}")

    print(f"\n{B}[7] PENERIMAAN TANPA GULUNGAN → BACKFILL{X}")
    m_bf = material(token, f"BF-{stamp}", "kg")
    gr4 = make_gr(token, loc, m_bf, 60, "kg")            # tanpa rincian roll
    st4, r4 = receive(token, gr4)
    pending = r4.get("rolls_pending") or []
    st5, miss = call("GET", "/api/wms/fabric-rolls/missing-from-receipts?limit=200", token)
    row = next((x for x in (miss.get("items") or []) if x.get("receipt_id") == gr4["id"]), None)
    if st4 == 200 and len(pending) == 1 and row and abs(float(row["accepted_qty"]) - 60) < 0.001:
        ok("R6a", "kain tanpa gulungan dilaporkan & muncul di daftar 'Penerimaan tanpa roll'",
           f"{row['material_code']} {row['accepted_qty']} {row['unit']} dari {row['receipt_number']}")
    else:
        bad("R6a", "lubang kain-tanpa-gulungan tidak terlihat",
            f"HTTP {st4} pending={len(pending)} ada_di_daftar={bool(row)}")
    if row:
        st6, iss = call("POST", "/api/wms/fabric-rolls/issue-from-receipt", token, {
            "receipt_id": gr4["id"], "item_id": row["item_id"],
            "lines": [{"qty": 30, "color_lot": "LOT-BF"}, {"qty": 30, "color_lot": "LOT-BF"}]})
        nos = iss.get("roll_numbers") or []
        st7, again = call("POST", "/api/wms/fabric-rolls/issue-from-receipt", token, {
            "receipt_id": gr4["id"], "item_id": row["item_id"],
            "lines": [{"qty": 30}, {"qty": 30}]})
        st8, miss2 = call("GET", "/api/wms/fabric-rolls/missing-from-receipts?limit=200", token)
        gone = not any(x.get("item_id") == row["item_id"] for x in (miss2.get("items") or []))
        if (st6 == 200 and len(nos) == 2 and all(ROLL_NO_RE.match(n) for n in nos)
                and st7 == 409 and gone):
            ok("R6b", "gulungan retroaktif terbit sekali (penerbitan kedua 409) & daftar bersih",
               f"{', '.join(nos)} · ulang → HTTP {st7}")
        else:
            bad("R6b", "backfill gulungan tidak idempoten / daftar tidak bersih",
                f"terbit HTTP {st6} nos={nos} ulang HTTP {st7} hilang_dari_daftar={gone}")

    print(f"\n{B}[8] CUTTING WAJIB MENUNJUK GULUNGAN (H-6){X}")
    st9, o = call("POST", "/api/cutting/orders", token, {
        "input_material_id": m_kain["id"], "planned_input_qty": 120, "planned_output_qty": 240,
        "model_id": any_model_id(token), "location_id": loc["id"], "notes": MARK})
    if st9 not in (200, 201):
        bad("R7", "order cutting untuk kain ber-gulungan gagal dibuat", detail(o)[:200])
        return
    call("POST", f"/api/cutting/orders/{o['id']}/start", token)
    stok0 = onhand(db, m_kain["id"])
    st10, p1 = call("POST", f"/api/cutting/orders/{o['id']}/progress", token,
                    {"input_consumed": 100, "output_qty": 200})
    msg10 = detail(p1)
    if (st10 == 400 and "pilih gulungan" in msg10.lower()
            and abs(onhand(db, m_kain["id"]) - stok0) < 0.001):
        ok("R7a", "progres TANPA gulungan DITOLAK dan stok kain tidak berkurang", msg10[:170])
    else:
        bad("R7a", "kain bisa dipotong tanpa menunjuk gulungan",
            f"HTTP {st10} stok {stok0}→{onhand(db, m_kain['id'])} {msg10[:160]}")

    rolls_open = sorted(db.wh_fabric_rolls.find(
        {"material_id": m_kain["id"], "status": {"$in": ["in_stock", "partly_issued"]}},
        {"_id": 0}), key=lambda r: r["roll_no"])
    ids = [r["id"] for r in rolls_open[:2]]
    st11, p2 = call("POST", f"/api/cutting/orders/{o['id']}/progress", token,
                    {"input_consumed": 150, "output_qty": 300, "roll_ids": ids})
    cons = ((p2.get("last_progress") or {}).get("roll_consumption") or [])
    r1 = db.wh_fabric_rolls.find_one({"id": ids[0]}, {"_id": 0}) or {}
    r2d = db.wh_fabric_rolls.find_one({"id": ids[1]}, {"_id": 0}) or {}
    n_issue = db.wh_fabric_roll_movements.count_documents(
        {"roll_id": {"$in": ids}, "movement_type": "issue"})
    fifo_ok = (abs(float(r1.get("remaining_kg") or 0)) < 0.001
               and abs(float(r2d.get("remaining_kg") or 0) - 50) < 0.001)
    if (st11 == 200 and len(cons) == 2 and fifo_ok and n_issue == 2
            and abs(onhand(db, m_kain["id"]) - stok0 + 150) < 0.001):
        ok("R7b", "pemakaian dibagi FIFO: gulungan tertua habis dulu, sisanya berkurang",
           f"{r1.get('roll_no')}=0 · {r2d.get('roll_no')}=50 · {n_issue} movement 'issue'")
    else:
        bad("R7b", "sisa gulungan tidak mengikuti pemakaian",
            f"HTTP {st11} cons={len(cons)} sisa1={r1.get('remaining_kg')} "
            f"sisa2={r2d.get('remaining_kg')} issue={n_issue} {detail(p2)[:150]}")

    m_no = material(token, f"NOROLL-{stamp}", "kg")
    gr5 = make_gr(token, loc, m_no, 40, "kg")
    receive(token, gr5)
    st12, o2 = call("POST", "/api/cutting/orders", token, {
        "input_material_id": m_no["id"], "planned_input_qty": 10, "planned_output_qty": 20,
        "model_id": any_model_id(token), "location_id": loc["id"], "notes": MARK})
    msg12 = detail(o2)
    if st12 == 400 and "penerimaan" in msg12.lower() and "roll" in msg12.lower():
        ok("R7c", "kain tanpa gulungan DITOLAK dengan jalan keluarnya disebut", msg12[:190])
    else:
        bad("R7c", "kain tanpa gulungan lolos tanpa peringatan", f"HTTP {st12} {msg12[:190]}")

    print(f"\n{B}[9] NOMOR TIDAK BOLEH DIKETIK & TETAP UNIK{X}")
    payload = {"material_id": m_kain["id"], "material_code": m_kain["code"],
               "material_name": m_kain["name"], "uom": "kg", "weight_kg": 5,
               "length_m": 0, "notes": MARK}
    st13, typed = call("POST", "/api/wms/fabric-rolls", token, {**payload, "roll_no": "RL-KETIKAN-9"})
    msg13 = detail(typed)
    if st13 == 400 and "otomatis" in msg13.lower() and re.search(r"RL-\d{6}-\d{4}", msg13):
        ok("R8a", "nomor roll ketikan DITOLAK sambil menyebut nomor yang akan dipakai", msg13[:160])
    else:
        bad("R8a", "nomor roll ketikan tidak ditolak", f"HTTP {st13} {msg13[:180]}")

    with ThreadPoolExecutor(max_workers=12) as ex:
        res = list(ex.map(lambda _: call("POST", "/api/wms/fabric-rolls", token, payload), range(12)))
    nos = [r.get("roll", {}).get("roll_no") for s, r in res if s == 200]
    dup = list(db.wh_fabric_rolls.aggregate([
        {"$group": {"_id": "$roll_no", "n": {"$sum": 1}}}, {"$match": {"n": {"$gt": 1}}}]))
    if len(nos) == 12 and len(set(nos)) == 12 and not dup:
        ok("R8b", "12 penerbitan bersamaan → 12 nomor UNIK, 0 duplikat di seluruh koleksi",
           f"{sorted(nos)[0]} … {sorted(nos)[-1]}")
    else:
        bad("R8b", "nomor gulungan bisa kembar saat balapan",
            f"berhasil={len(nos)} unik={len(set(nos))} duplikat={dup[:3]}")


# ─── bersih-bersih ───────────────────────────────────────────────────────────

def clean(db) -> int:
    mats = list(db.rahaza_materials.find({"code": {"$regex": f"^{CODE_PREFIX}"}}, {"_id": 0, "id": 1}))
    ids = [m["id"] for m in mats]
    n = 0
    if ids:
        rolls = list(db.wh_fabric_rolls.find({"material_id": {"$in": ids}}, {"_id": 0, "id": 1}))
        rids = [r["id"] for r in rolls]
        if rids:
            db.wh_fabric_roll_movements.delete_many({"roll_id": {"$in": rids}})
            n += db.wh_fabric_rolls.delete_many({"id": {"$in": rids}}).deleted_count
        orders = list(db.cutting_orders.find({"input_material_id": {"$in": ids}}, {"_id": 0, "id": 1}))
        oids = [o["id"] for o in orders]
        if oids:
            # FASE H-6b (2026-08-17): laporan progres cutting kini MENERBITKAN dokumen
            # "Pengeluaran Material" (`ref_type=cutting_issue`). Kalau hanya progres &
            # ordernya yang dihapus, dokumen itu tertinggal sebagai YATIM — menunjuk order
            # cutting yang sudah tidak ada — dan menumpuk di layar Pengeluaran Material
            # setiap kali gate ini dijalankan. Dijaga oleh INV-F24 C14.
            mis = list(db.rahaza_material_issues.find(
                {"cutting_order_id": {"$in": oids}}, {"_id": 0, "id": 1}))
            if mis:
                mi_ids = [m["id"] for m in mis]
                db.rahaza_material_movements.delete_many({"ref_id": {"$in": mi_ids}})
                n += db.rahaza_material_issues.delete_many(
                    {"id": {"$in": mi_ids}}).deleted_count
            db.cutting_progress.delete_many({"cutting_order_id": {"$in": oids}})
            n += db.cutting_orders.delete_many({"id": {"$in": oids}}).deleted_count
        for coll in ("rahaza_material_stock", "rahaza_stock_ledger", "rahaza_material_movements"):
            db[coll].delete_many({"material_id": {"$in": ids}})
        # potongan hasil cutting ikut lahir dari kain uji → jangan tinggalkan master sampah
        #
        # 2026-08-19 (Sesi #28) — DULU baris ini hanya menghapus MASTER potongannya,
        # sementara BARIS STOK & KARTU STOK milik potongan itu ditinggalkan. Akibatnya
        # setiap kali gate dijalankan, `sync-audit` melaporkan 2 rujukan rusak baru
        # (D4/E1: "baris stok menunjuk material yang tidak ada") — alat ukurnya sendiri
        # yang mengotori data yang diukurnya. Terukur: 2 baris per jalannya gate.
        # Maka id potongan diambil LEBIH DAHULU, stok/kartunya dihapus, baru masternya.
        cut_ids = [m["id"] for m in db.rahaza_materials.find(
            {"source_material_id": {"$in": ids}}, {"_id": 0, "id": 1})]
        if cut_ids:
            for coll in ("rahaza_material_stock", "rahaza_stock_ledger",
                         "rahaza_material_movements"):
                db[coll].delete_many({"material_id": {"$in": cut_ids}})
        # 2026-08-23 (Sesi #33) — pola yang SAMA terulang di tempat baru: sejak
        # sesi #32 memotong kain MELAHIRKAN NILAI potongan, gate ini juga menulis
        # `rahaza_material_cost_history` untuk kain & potongannya. Baris riwayat
        # itu dulu ditinggalkan ⇒ menjadi baris YATIM di layar Riwayat Harga
        # Barang (sesi #33) yang materialnya sudah tidak ada. Dijaga INV-F38 C16.
        db.rahaza_material_cost_history.delete_many(
            {"material_id": {"$in": (cut_ids or []) + ids}})
        db.rahaza_materials.delete_many({"source_material_id": {"$in": ids}})
        n += db.rahaza_materials.delete_many({"id": {"$in": ids}}).deleted_count
    grs = list(db.warehouse_receiving.find({"supplier_name": MARK}, {"_id": 0, "id": 1}))
    if grs:
        n += db.warehouse_receiving.delete_many(
            {"id": {"$in": [g["id"] for g in grs]}}).deleted_count
    # counter nomor roll SENGAJA tidak dihapus: mengembalikannya bisa memberi nomor
    # yang pernah dipakai gulungan lain (nomor gulungan harus sekali pakai selamanya).
    return n


def main():
    print(f"{C}{B}FASE H-5 & H-6 — gulungan kain lahir saat diterima, mati saat dipotong{X}")
    db = db_handle()
    clean(db)
    part_static()
    part_pyflakes()
    st, r = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = r.get("token") if st == 200 else None
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}) — bagian runtime dilewati{X}")
        FAIL.append("LOGIN")
    else:
        try:
            part_runtime(db, token)
        finally:
            if "--keep" not in sys.argv:
                n = clean(db)
                print(f"\n{Y}  bersih-bersih: {n} dokumen uji dihapus{X}")
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian roll kain terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
