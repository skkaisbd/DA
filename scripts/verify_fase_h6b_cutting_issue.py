#!/usr/bin/env python3
"""verify_fase_h6b_cutting_issue.py — FASE H-6b (2026-08-17).

GATE **INV-F24** — "SELURUH ARUS KELUAR GUDANG PUNYA DOKUMEN, DAN STOK HANYA
TURUN SEKALI."

YANG TERUKUR SEBELUM PERBAIKAN (sisa terakhir Fase H):
  · `POST /api/cutting/orders/{id}/progress` memotong stok kain
    (`rahaza_material_stock` + `rahaza_stock_ledger`) dan mengurangi sisa gulungan
    (`wh_fabric_rolls`), TETAPI tidak pernah menulis satu dokumen pun ke
    `rahaza_material_issues` dan tidak satu baris pun ke kartu stok
    (`rahaza_material_movements`). Dua pintu keluar lain (approve MI dan "Kirim
    Material CMT") sudah berdokumen ⇒ layar "Pengeluaran Material" memberi jawaban
    yang SALAH untuk pertanyaan "material apa saja yang keluar hari ini?".

GATE INI MENAHAN ENAM ARAH SALAH (yang semuanya mungkin terjadi diam-diam):
  C1  arus keluar tanpa dokumen DISEMBUNYIKAN (angka "belum berdokumen" bohong)
  C2  dokumen tidak terbit / isinya tidak cocok dengan progres yang dilaporkan
  C3  stok atau gulungan dipotong DUA KALI (bug paling mahal dari fitur ini)
  C4  beban hantu di buku besar (dokumen cutting ikut dijurnal Dr WIP/Cr Persediaan)
  C5  dokumen arus keluar bisa dihapus/dibatalkan/di-approve ⇒ hilang dari daftar
  C6  penyaring sumber bohong (dokumen tenggelam di daftar yang tak bisa dibaca)
  C7  lapisan rekap ternyata MENULIS (pelajaran INV-F23 S6)
  C8  dokumen kembar saat klik ganda / backfill dijalankan berulang
  C9  backend jadi tetapi LAYAR tidak menampilkannya (fitur mati diam-diam)
  C10 route literal `/material-issues/sources` tertukar dengan `/{mid}` (sesi #16)
  C11 seseorang menambahkan pemotongan stok kedua di jalur cutting

Self-cleaning: seluruh data uji (`VFH6B-*`) dihapus di akhir, sukses maupun gagal.

Pakai:  python3 scripts/verify_fase_h6b_cutting_issue.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(ROOT / "backend"))
from gr_common import db_handle

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

STAMP = time.strftime("%H%M%S")
MAT_CODE = f"VFH6B-KAIN-{STAMP}"

MI_MODULE = ROOT / "frontend/src/components/erp/RahazaMaterialIssueModule.jsx"
CUT_MODULE = ROOT / "frontend/src/components/erp/cutting/CuttingOrdersModule.jsx"
ISSUES_ROUTE = ROOT / "backend/routes/rahaza_inventory_issues.py"
CUTTING_ROUTE = ROOT / "backend/routes/cutting.py"
MATERIALS_ROUTE = ROOT / "backend/routes/rahaza_inventory_materials.py"

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
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        d = e.read()
        return e.code, (json.loads(d or b"{}") if d[:1] in (b"{", b"[")
                        else {"raw": d[:300].decode(errors="ignore")})
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def detail_of(d) -> str:
    if isinstance(d, dict):
        return str(d.get("detail") or d.get("raw") or d)[:400]
    return str(d)[:400]


def _any_model_id(token):
    """Model/style DARI MASTER — order cutting wajib menunjuk model (2026-08-21)."""
    st, rows = call("GET", "/api/rahaza/models", token)
    rows = rows if isinstance(rows, list) else (rows or {}).get("items") or []
    live = next((m for m in rows if m.get("active") is not False), None)
    if live:
        return live["id"]
    st, d = call("POST", "/api/rahaza/models", token,
                 {"code": "MDL-GATE-H6B", "name": "Model Gate H6B"})
    if st not in (200, 201) or not (d or {}).get("id"):
        raise RuntimeError(f"gagal menyiapkan model master: {detail_of(d)}")
    return d["id"]


def onhand(db, mid: str) -> float:
    return round(sum(float(s.get("qty") or 0) for s in
                     db.rahaza_material_stock.find({"material_id": mid}, {"_id": 0, "qty": 1})), 4)


# ══════════════════ C10/C11/C9 — pemeriksaan statik (murah, tanpa data) ════════

def part_static():
    print(f"\n{B}[1] STATIK — urutan route, pemotongan ganda, dan LAYAR{X}")
    src = ISSUES_ROUTE.read_text(encoding="utf-8")
    i_sources = src.find('@router.get("/material-issues/sources")')
    i_param = src.find('@router.get("/material-issues/{mid}")')
    if i_sources != -1 and i_param != -1 and i_sources < i_param:
        ok("C10", "route literal /material-issues/sources dideklarasikan SEBELUM /{mid}",
           f"baris literal={src[:i_sources].count(chr(10)) + 1} < parameter={src[:i_param].count(chr(10)) + 1}")
    else:
        bad("C10", "urutan route salah ⇒ /sources akan terbaca sebagai mid='sources' (404 senyap)",
            f"pos literal={i_sources} param={i_param}")

    cut = CUTTING_ROUTE.read_text(encoding="utf-8")
    if "issue_material_issue" not in cut and "material_issue_engine" not in cut:
        ok("C11", "jalur cutting TIDAK memanggil mesin potong-stok MI (tidak ada potong kedua)",
           "cutting hanya memakai core.cutting_material_issue (pembuat dokumen)")
    else:
        bad("C11", "jalur cutting memanggil mesin pengeluaran MI ⇒ stok berisiko dipotong dua kali",
            "hapus pemanggilan issue_material_issue/material_issue_engine dari routes/cutting.py")

    mi_src = MI_MODULE.read_text(encoding="utf-8")
    cut_src = CUT_MODULE.read_text(encoding="utf-8")
    # PELAJARAN SESI #11: penjaga TIDAK BOLEH mencari testid yang dibangun DINAMIS
    # (`mi-src-${s.key}`) — itu menuduh salah. Yang dicari: awalan testid + nama
    # field/endpoint yang memang tertulis literal di berkasnya.
    need_mi = ["mi-source-chips", "mi-src-", "source_key", "mi-cutting-panel",
               "gl_skip_reason", "/material-issues/sources"]
    need_cut = ["cutting-mi-backfill-btn", "material_issue_number", "cutting-mi-missing-panel",
                "/issue-docs/backfill", "/issue-docs/missing"]
    miss = [t for t in need_mi if t not in mi_src] + [t for t in need_cut if t not in cut_src]
    if not miss:
        ok("C9", "LAYAR benar-benar memakai fitur ini (chip sumber, panel Cutting, tombol terbitkan)",
           "RahazaMaterialIssueModule + CuttingOrdersModule")
    else:
        bad("C9", "backend jadi tetapi layar belum memakainya", f"hilang: {miss}")

    # ── C12 — `GET /materials/{mid}` (ditambahkan sesi #17) TIDAK BOLEH menelan
    # dua route literal di berkas yang sama. Kalau tertelan, dropdown satuan di
    # SELURUH layar mati diam-diam (uom-options terbaca sebagai mid="uom-options").
    msrc = MATERIALS_ROUTE.read_text(encoding="utf-8")
    i_get_one = msrc.find('@router.get("/materials/{mid}")')
    i_uom = msrc.find('@router.get("/materials/uom-options")')
    i_reorder = msrc.find('@router.get("/materials/reorder-alerts")')
    if i_get_one != -1 and i_uom != -1 and i_reorder != -1 \
            and i_get_one > i_uom and i_get_one > i_reorder:
        ok("C12", "GET /materials/{mid} dideklarasikan SESUDAH semua route literal /materials/*",
           f"reorder-alerts & uom-options menang (posisi {i_reorder}/{i_uom} < {i_get_one})")
    else:
        bad("C12", "GET /materials/{mid} akan menelan route literal /materials/* (dropdown satuan mati senyap)",
            f"pos get_one={i_get_one} uom-options={i_uom} reorder-alerts={i_reorder}")


# ══════════════════ penyiapan data uji NYATA lewat API ════════════════════════

def setup(db, token) -> dict:
    st, d = call("GET", "/api/rahaza/storage-locations", token)
    locs = d if isinstance(d, list) else (d or {}).get("items") or []
    loc = next((x for x in locs if "kain" in str(x.get("name", "")).lower()), None) or (locs[0] if locs else None)
    if not loc:
        raise RuntimeError("tidak ada storage location")

    st, d = call("POST", "/api/rahaza/materials", token, {
        "code": MAT_CODE, "name": f"Kain gate H-6b {STAMP}", "unit": "kg",
        "type": "fabric", "color": "Navy", "unit_cost": 75000, "notes": "gate INV-F24"})
    if st not in (200, 201):
        raise RuntimeError(f"gagal buat material: {detail_of(d)}")
    mat = (d or {}).get("material") or d

    st, d = call("POST", "/api/wms/legacy/receiving", token, {
        "source_type": "supplier", "supplier_name": "PT Gate H6B",
        "location_id": loc.get("id"), "location_name": loc.get("name"),
        "notes": "gate INV-F24", "items": [{
            "product_name": mat["name"], "sku": mat["code"], "material_id": mat["id"],
            "expected_qty": 120, "received_qty": 120, "rejected_qty": 0, "unit": "kg",
            "unit_price": 75000, "inspection_status": "passed", "lot_number": "LOT-F24",
            "rolls": [{"qty": 60, "color_lot": "LOT-F24", "notes": ""} for _ in range(2)]}]})
    if st not in (200, 201):
        raise RuntimeError(f"gagal buat GR: {detail_of(d)}")
    gr = d
    st, d = call("PUT", f"/api/wms/legacy/receiving/{gr['id']}", token, {"status": "received"})
    if st != 200:
        raise RuntimeError(f"gagal terima GR: {detail_of(d)}")
    rolls = sorted(db.wh_fabric_rolls.find({"source_receipt_id": gr["id"]}, {"_id": 0}),
                   key=lambda r: r["roll_no"])
    if len(rolls) != 2:
        raise RuntimeError(f"gulungan tidak terbit ({len(rolls)}) — INV-F22 rusak")

    st, d = call("POST", "/api/cutting/orders", token, {
        "input_material_id": mat["id"], "planned_input_qty": 100, "planned_output_qty": 200,
        "model_id": _any_model_id(token),
        "output_size": "L", "output_color": "Navy", "location_id": loc.get("id"),
        "notes": "gate INV-F24"})
    if st not in (200, 201):
        raise RuntimeError(f"gagal buat order cutting: {detail_of(d)}")
    order = d
    st, d = call("POST", f"/api/cutting/orders/{order['id']}/start", token)
    if st != 200:
        raise RuntimeError(f"gagal start order: {detail_of(d)}")
    return {"loc": loc, "mat": mat, "gr": gr, "rolls": rolls, "order": d}


# ══════════════════ C1..C8 — invarian runtime ═════════════════════════════════

def part_runtime(db, token, ctx) -> dict:
    print(f"\n{B}[2] RUNTIME — dokumen terbit, stok sekali, buku besar bersih{X}")
    mat, rolls, order, loc = ctx["mat"], ctx["rolls"], ctx["order"], ctx["loc"]

    # ── C1: kejujuran daftar "belum berdokumen" (tanpa menyentuh data lama) ──
    real_missing = 0
    for p in db.cutting_progress.find({}, {"_id": 0, "id": 1, "input_consumed": 1}):
        if float(p.get("input_consumed") or 0) <= 0:
            continue
        if not db.rahaza_material_issues.find_one({"cutting_progress_id": p["id"]}, {"_id": 0}):
            real_missing += 1
    st, d = call("GET", "/api/cutting/issue-docs/missing?limit=1000", token)
    reported = (d or {}).get("count")
    if st == 200 and reported == real_missing:
        ok("C1", "daftar 'progres belum berdokumen' JUJUR (tidak menyembunyikan arus keluar)",
           f"DB={real_missing} dilaporkan={reported}")
    else:
        bad("C1", "angka progres tanpa dokumen tidak sama dengan kenyataan di DB",
            f"HTTP {st} dilaporkan={reported} DB={real_missing}")

    stok0 = onhand(db, mat["id"])
    n_mi0 = db.rahaza_material_issues.count_documents({})
    st, d = call("POST", f"/api/cutting/orders/{order['id']}/progress", token,
                 {"input_consumed": 60, "output_qty": 120, "waste_qty": 2,
                  "roll_ids": [rolls[0]["id"]], "note": "gate INV-F24"})
    if st != 200:
        bad("C2", "progres cutting GAGAL dilaporkan", f"HTTP {st} {detail_of(d)}")
        return {}
    lp = (d or {}).get("last_progress") or {}
    mi_no = lp.get("material_issue_number")
    mi = db.rahaza_material_issues.find_one({"mi_number": mi_no}, {"_id": 0}) if mi_no else None
    item = ((mi or {}).get("items") or [{}])[0]
    if (mi and mi.get("source") == "cutting" and mi.get("ref_type") == "cutting_issue"
            and mi.get("status") == "issued"
            and mi.get("cutting_order_id") == order["id"]
            and item.get("material_id") == mat["id"]
            and abs(float(item.get("qty_required") or 0) - 60) < 0.001
            and abs(float(item.get("qty_issued") or 0) - 60) < 0.001
            and item.get("location_id") == loc.get("id")
            and rolls[0]["roll_no"] in (mi.get("roll_numbers") or [])
            and db.rahaza_material_issues.count_documents({}) == n_mi0 + 1):
        ok("C2", "satu progres ⇒ satu dokumen 'issued' yang isinya cocok dengan yang dilaporkan",
           f"{mi_no} · 60 kg {MAT_CODE} @ {loc.get('name')} · gulungan {mi.get('roll_numbers')}")
    else:
        bad("C2", "dokumen tidak terbit / isinya tidak cocok",
            f"mi_number={mi_no} doc={'ada' if mi else 'TIDAK ADA'} item={item}")
        return {"mi": mi}

    # ── C3: stok & gulungan turun TEPAT SEKALI ──
    stok1 = onhand(db, mat["id"])
    led = db.rahaza_stock_ledger.count_documents({"material_id": mat["id"], "op": "issue"})
    mv = db.rahaza_material_movements.count_documents(
        {"ref_type": "cutting_issue", "ref_id": mi["id"]})
    roll = db.wh_fabric_rolls.find_one({"id": rolls[0]["id"]}, {"_id": 0})
    if (abs(stok0 - stok1 - 60) < 0.001 and led == 1 and mv == 1
            and abs(float(roll.get("remaining_kg") or 0)) < 0.001):
        ok("C3", "stok, ledger, kartu stok, dan sisa gulungan masing-masing bergerak SEKALI",
           f"stok {stok0}→{stok1} · ledger={led} · kartu stok={mv} · sisa roll={roll.get('remaining_kg')}")
    else:
        bad("C3", "ada mutasi ganda / kartu stok tidak terisi",
            f"stok {stok0}→{stok1} ledger={led} kartu={mv} roll={roll.get('remaining_kg')}")

    # ── C4: buku besar bersih ──
    je = db.rahaza_journal_entries.count_documents({"source_ref": f"mi:{mi['id']}"})
    st, d = call("POST", f"/api/rahaza/material-issues/{mi['id']}/post-to-gl", token)
    msg = detail_of(d).lower()
    je_after = db.rahaza_journal_entries.count_documents({"source_ref": f"mi:{mi['id']}"})
    if je == 0 and st == 400 and je_after == 0 and "cutting" in msg and "penyesuaian stok" in msg:
        ok("C4", "dokumen cutting TIDAK dijurnal & post-to-gl ditolak dengan jalan keluarnya",
           f"HTTP {st} · jurnal {je}→{je_after}")
    else:
        bad("C4", "beban hantu mungkin masuk buku besar",
            f"jurnal {je}→{je_after} · post-to-gl HTTP {st} · {msg[:200]}")

    # ── C5: tidak bisa hilang dari daftar ──
    tries = {
        "submit": call("POST", f"/api/rahaza/material-issues/{mi['id']}/submit", token)[0],
        "approve": call("POST", f"/api/rahaza/material-issues/{mi['id']}/approve", token, {})[0],
        "confirm": call("POST", f"/api/rahaza/material-issues/{mi['id']}/confirm", token, {})[0],
        "cancel": call("POST", f"/api/rahaza/material-issues/{mi['id']}/cancel", token, {})[0],
        "delete": call("DELETE", f"/api/rahaza/material-issues/{mi['id']}", token)[0],
    }
    still = db.rahaza_material_issues.find_one({"id": mi["id"]}, {"_id": 0})
    stok2 = onhand(db, mat["id"])
    if (all(v in (400, 403) for v in tries.values()) and still
            and still.get("status") == "issued" and abs(stok2 - stok1) < 0.001):
        ok("C5", "dokumen arus keluar tidak bisa dihapus/dibatalkan/di-approve (stok tetap)",
           " · ".join(f"{k}={v}" for k, v in tries.items()))
    else:
        bad("C5", "dokumen arus keluar masih bisa dimanipulasi / stok bergerak",
            f"{tries} status={(still or {}).get('status')} stok {stok1}→{stok2}")

    # ── C6: penyaringan jujur ──
    st, d = call("GET", "/api/rahaza/material-issues?source=cutting&limit=500", token)
    cut_rows = d if isinstance(d, list) else []
    st2, d2 = call("GET", "/api/rahaza/material-issues/sources", token)
    smap = {s["key"]: s["count"] for s in ((d2 or {}).get("sources") or [])}
    st3, _ = call("GET", "/api/rahaza/material-issues?source=tidak-ada", token)
    st4, d4 = call("GET", "/api/rahaza/material-issues?limit=500", token)
    all_rows = d4 if isinstance(d4, list) else []
    if (st == 200 and st2 == 200 and st4 == 200
            and cut_rows and all(x.get("source_key") == "cutting" for x in cut_rows)
            and len(cut_rows) == smap.get("cutting") and st3 == 400
            and mi_no in {x.get("mi_number") for x in all_rows}
            and all(x.get("source_label") for x in all_rows)):
        ok("C6", "penyaring sumber jujur, sumber asing ditolak, dan dokumen tetap ada di SATU daftar",
           f"cutting={len(cut_rows)} (rekap {smap.get('cutting')}) · semua={len(all_rows)} baris berlabel")
    else:
        bad("C6", "penyaring/rekap sumber tidak bisa dipercaya",
            f"cutting_rows={len(cut_rows)} rekap={smap.get('cutting')} asing_http={st3} "
            f"ada_di_semua={mi_no in {x.get('mi_number') for x in all_rows}}")

    # ── C7: lapisan daftar/rekap READ-ONLY ──
    b_mi = db.rahaza_material_issues.count_documents({})
    b_mv = db.rahaza_material_movements.count_documents({})
    b_led = db.rahaza_stock_ledger.count_documents({})
    for _ in range(2):
        call("GET", "/api/rahaza/material-issues/sources", token)
        call("GET", "/api/rahaza/material-issues?source=cutting&limit=500", token)
        call("GET", "/api/cutting/issue-docs/missing?limit=1000", token)
    a_mi = db.rahaza_material_issues.count_documents({})
    a_mv = db.rahaza_material_movements.count_documents({})
    a_led = db.rahaza_stock_ledger.count_documents({})
    if (a_mi, a_mv, a_led) == (b_mi, b_mv, b_led):
        ok("C7", "membaca daftar/rekap/missing tidak menulis apa pun (READ-ONLY)",
           f"MI={a_mi} kartu={a_mv} ledger={a_led} (tak berubah setelah 6 panggilan)")
    else:
        bad("C7", "lapisan 'hanya menampilkan' ternyata MENULIS",
            f"MI {b_mi}→{a_mi} kartu {b_mv}→{a_mv} ledger {b_led}→{a_led}")

    # ── C8: idempotensi (indeks unik + backfill berulang) ──
    idx = [i for i in db.rahaza_material_issues.list_indexes()
           if "cutting_progress_id" in dict(i.get("key") or {})]
    uniq = bool(idx) and bool(idx[0].get("unique"))
    prog = db.cutting_progress.find_one({"cutting_order_id": order["id"]}, {"_id": 0})
    db.rahaza_material_issues.delete_one({"cutting_progress_id": prog["id"]})
    db.rahaza_material_movements.delete_many({"ref_id": mi["id"]})
    db.cutting_progress.update_one({"id": prog["id"]},
                                   {"$unset": {"material_issue_id": "", "material_issue_number": ""}})
    stok_legacy = onhand(db, mat["id"])
    st, r1 = call("POST", "/api/cutting/issue-docs/backfill", token, {"order_id": order["id"]})
    st2, r2 = call("POST", "/api/cutting/issue-docs/backfill", token, {"order_id": order["id"]})
    n_doc = db.rahaza_material_issues.count_documents({"cutting_progress_id": prog["id"]})
    new_doc = db.rahaza_material_issues.find_one({"cutting_progress_id": prog["id"]}, {"_id": 0})
    if (uniq and st == 200 and (r1 or {}).get("created") == 1 and st2 == 200
            and (r2 or {}).get("created") == 0 and n_doc == 1
            and (new_doc or {}).get("backfilled") is True
            and abs(onhand(db, mat["id"]) - stok_legacy) < 0.001):
        ok("C8", "indeks unik + backfill idempoten (jalan 2×: 1 terbit, 0 kembar, stok tak bergerak)",
           f"unique={uniq} · {(new_doc or {}).get('mi_number')} · stok tetap {stok_legacy}")
    else:
        bad("C8", "dokumen bisa kembar / backfill memotong stok lagi",
            f"unique={uniq} r1={(r1 or {}).get('created')} r2={(r2 or {}).get('created')} "
            f"n_doc={n_doc} stok {stok_legacy}→{onhand(db, mat['id'])}")
    return {"mi": mi}


def part_route_runtime(token):
    """C13 — bukti RUNTIME bahwa route literal `/materials/*` masih menang.

    Pemeriksaan statik (C12) bisa benar sementara urutan include router berubah,
    jadi invarian ini ditanyakan LANGSUNG ke server: `uom-options` harus dijawab
    oleh handler-nya sendiri ("material_ids wajib diisi"), BUKAN oleh
    `/materials/{mid}` ("Material tidak ditemukan").
    """
    st_uom, d_uom = call("GET", "/api/rahaza/materials/uom-options", token)
    st_re, _ = call("GET", "/api/rahaza/materials/reorder-alerts", token)
    msg = detail_of(d_uom).lower()
    if st_uom == 400 and "material_ids" in msg and st_re == 200:
        ok("C13", "server masih mengarahkan /materials/uom-options & /reorder-alerts ke handler-nya",
           f"uom-options HTTP {st_uom} ('{detail_of(d_uom)[:40]}') · reorder-alerts HTTP {st_re}")
    else:
        bad("C13", "route literal /materials/* tertelan /materials/{mid} (dropdown satuan mati senyap)",
            f"uom-options HTTP {st_uom} {msg[:120]} · reorder-alerts HTTP {st_re}")


def part_no_orphan_docs(db):
    """C14 — TIDAK ADA dokumen `cutting_issue` yang YATIM.

    Cacat NYATA yang ditemukan saat gate penuh dijalankan (2026-08-17): gate
    INV-F22 (`verify_fase_h5_h6_roll.py`) membuat order+progres cutting lalu
    membersihkannya — tetapi ia dibuat SEBELUM H-6b ada, jadi dokumen
    "Pengeluaran Material" yang kini lahir dari progres itu TERTINGGAL. Hasilnya
    setiap kali gate dijalankan, layar Gudang kebagian satu dokumen sampah yang
    menunjuk order cutting yang sudah tidak ada. Invarian ini membuat kebocoran
    seperti itu MERAH, bukan tak terlihat: siapa pun yang menambah alat uji baru
    di jalur cutting wajib ikut membersihkan dokumennya.
    """
    orphans = []
    for mi in db.rahaza_material_issues.find(
            {"ref_type": "cutting_issue"},
            {"_id": 0, "mi_number": 1, "cutting_order_id": 1, "cutting_progress_id": 1}):
        has_order = db.cutting_orders.count_documents({"id": mi.get("cutting_order_id")}) > 0
        has_prog = db.cutting_progress.count_documents({"id": mi.get("cutting_progress_id")}) > 0
        if not (has_order and has_prog):
            orphans.append({"mi": mi.get("mi_number"), "order": has_order, "progres": has_prog})
    total = db.rahaza_material_issues.count_documents({"ref_type": "cutting_issue"})
    if not orphans:
        ok("C14", "setiap dokumen cutting_issue masih menunjuk order + progres yang ADA",
           f"{total} dokumen diperiksa, 0 yatim")
    else:
        bad("C14", "ada dokumen arus keluar Cutting yang YATIM (order/progresnya sudah dihapus) — "
                   "sapu dengan `python3 scripts/cleanup_uji_h5_h6.py --apply`, lalu ikut "
                   "bersihkan dokumennya di alat uji yang membuatnya",
            {"contoh": orphans[:5], "total_yatim": len(orphans), "total_dokumen": total})


# ══════════════════ bersih-bersih (selalu jalan) ══════════════════════════════

def cleanup(db, ctx):
    if not ctx:
        return
    order, mat, gr = ctx.get("order") or {}, ctx.get("mat") or {}, ctx.get("gr") or {}
    roll_ids = [r["id"] for r in (ctx.get("rolls") or [])]
    mi_ids = [m["id"] for m in db.rahaza_material_issues.find(
        {"cutting_order_id": order.get("id")}, {"_id": 0, "id": 1})]
    # 2026-08-19 (Sesi #28) — id master POTONGAN diambil lebih dahulu. Dulu cleanup
    # hanya menghapus master `CUT-GATE-F24-*` tetapi MENINGGALKAN baris stok & kartu
    # stoknya, sehingga tiap kali gate ini jalan `sync-audit` melaporkan 2 rujukan
    # rusak baru (D4/E1). Alat ukur tidak boleh mengotori data yang diukurnya.
    # 2026-08-23 (Sesi #32) — MASTER POTONGAN IKUT DIHAPUS LEWAT `id`, BUKAN
    # HANYA REGEX KODE. Cacat lamanya: `stale_ids` sudah memuat id master
    # potongan (dipakai untuk membersihkan stok & kartu stok), tetapi baris
    # "master" di bawah menghapus HANYA yang kodenya berawalan
    # `VFH6B-`/`CUT-GATE-F24`. Sejak sesi #30 kode potongan diturunkan dari NAMA
    # MODEL di master (mis. `CUT-JEPIT-JEDAI-NAVY-L`) ⇒ regex tidak pernah cocok
    # ⇒ SATU master sampah menumpuk di Master Item pemilik SETIAP KALI gate ini
    # dijalankan (inilah "potongan yatim" yang dilaporkan pemilik). Dijaga
    # sekarang oleh gate INV-F37.
    cut_ids = [m["id"] for m in db.rahaza_materials.find(
        {"$or": [{"source_material_id": mat.get("id")},
                 {"cutting_order_id": order.get("id")},
                 {"code": {"$regex": "^(VFH6B-|CUT-GATE-F24)", "$options": "i"}}]},
        {"_id": 0, "id": 1})]
    if order.get("output_material_id"):
        cut_ids.append(order["output_material_id"])
    stale_ids = [i for i in ([mat.get("id")] + cut_ids) if i]
    counts = {
        "MI": db.rahaza_material_issues.delete_many({"cutting_order_id": order.get("id")}).deleted_count,
        "kartu": db.rahaza_material_movements.delete_many(
            {"$or": [{"ref_id": {"$in": mi_ids}}, {"material_id": {"$in": stale_ids}}]}).deleted_count,
        "progres": db.cutting_progress.delete_many({"cutting_order_id": order.get("id")}).deleted_count,
        "order": db.cutting_orders.delete_many({"id": order.get("id")}).deleted_count,
        "roll": db.wh_fabric_rolls.delete_many({"id": {"$in": roll_ids}}).deleted_count,
        "roll_mv": db.wh_fabric_roll_movements.delete_many({"roll_id": {"$in": roll_ids}}).deleted_count,
        "GR": db.warehouse_receiving.delete_many({"id": gr.get("id")}).deleted_count,
        "stok": db.rahaza_material_stock.delete_many({"material_id": {"$in": stale_ids}}).deleted_count,
        "ledger": db.rahaza_stock_ledger.delete_many({"material_id": {"$in": stale_ids}}).deleted_count,
        # Sesi #33 — kain dibeli & dipotong di sini, jadi riwayat harganya ikut
        # lahir. Kalau tidak dihapus, ia menjadi baris YATIM di layar Riwayat
        # Harga Barang (materialnya sudah tidak ada). Dijaga INV-F38 C16.
        "harga": db.rahaza_material_cost_history.delete_many(
            {"material_id": {"$in": stale_ids}}).deleted_count,
        "master": db.rahaza_materials.delete_many(
            {"$or": [{"id": {"$in": stale_ids}},
                     {"code": {"$regex": "^(VFH6B-|CUT-GATE-F24)", "$options": "i"}}]}).deleted_count,
    }
    print(f"\n{Y}  bersih-bersih: " + " · ".join(f"{k}={v}" for k, v in counts.items()) + X)


def main():
    print(f"{C}{B}FASE H-6b — arus keluar Cutting berdokumen, stok hanya turun sekali (INV-F24){X}")
    db = db_handle()
    part_static()
    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token") if isinstance(d, dict) else None
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}){X}")
        return 2
    ctx = {}
    try:
        part_route_runtime(token)
        ctx = setup(db, token)
        part_runtime(db, token, ctx)
    except Exception as e:  # noqa: BLE001
        bad("SETUP", "penyiapan data uji gagal", str(e))
    finally:
        cleanup(db, ctx)
    # C14 dijalankan SESUDAH bersih-bersih: justru kebocoran alat uji sendiri yang
    # paling mungkin lolos, jadi diperiksa pada keadaan akhir.
    part_no_orphan_docs(db)
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian arus keluar Cutting terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
