#!/usr/bin/env python3
"""scenario_owner_questions.py — UJI NYATA 3 pertanyaan owner (2026-07-31).

Semua lewat API asli (bukan tulis DB langsung). Data uji diberi prefix `UJI-`.
Sebelum menjalankan: buat snapshot backup; sesudah: restore snapshot.

Q1  Vendor CMT kirim 100 SKU-A + 100 SKU-B. DA terima 90 A (kurang 10),
    100 B (10 di antaranya reject → minta dikerjakan ulang).
    → Apakah progress vendor SKU-A jadi 90? Bagaimana mengembalikan ke 100
      kalau ternyata DA salah hitung?
Q2  5 PO × 100 pcs, tiap PO dikirim 5x partial, semua sudah diterima DA.
    → Bisakah 1 surat jalan GABUNGAN 500 pcs ke buyer, jelas per PO?
Q3  Dari sisi DA→buyer: kalau qty yang diterima buyer selisih, apakah ada
    logika penyesuaian (progress / stok / tagihan / kapasitas kirim ulang)?
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date

import requests
from pymongo import MongoClient

API = os.environ.get("API_BASE", "http://localhost:8001")
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
STAMP = time.strftime("%H%M%S")

_env = {}
for line in open("/app/backend/.env", encoding="utf-8"):
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        _env[k.strip()] = v.strip().strip('"')
mongo = MongoClient(_env.get("MONGO_URL", "mongodb://localhost:27017"))
db = mongo[_env.get("DB_NAME", "test_database")]

TOK = None
findings: list[str] = []


def call(method: str, path: str, body=None, expect=None, quiet=False):
    h = {"Content-Type": "application/json"}
    if TOK:
        h["Authorization"] = f"Bearer {TOK}"
    r = requests.request(method, f"{API}{path}", headers=h,
                         json=body if body is not None else None, timeout=180)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:300]}
    if expect and r.status_code not in expect and not quiet:
        print(f"  {R}HTTP {r.status_code}{X} {method} {path} → {str(data)[:300]}")
    return r.status_code, data


def head(t):
    print(f"\n{C}{B}{'═' * 78}\n{t}\n{'═' * 78}{X}")


def sub(t):
    print(f"\n{C}── {t}{X}")


def fg_stock(sku: str) -> float:
    mat = db.rahaza_materials.find_one({"code": sku}, {"_id": 0, "id": 1})
    if not mat:
        return -1
    rows = list(db.rahaza_material_stock.find({"material_id": mat["id"]}, {"_id": 0, "qty": 1}))
    return sum(float(x.get("qty") or 0) for x in rows)


def ledger_rows(po_id: str) -> list[dict]:
    items = list(db.po_items.find({"po_id": po_id}, {"_id": 0, "id": 1, "sku": 1, "qty": 1}))
    out = []
    for it in items:
        jis = list(db.production_job_items.find({"po_item_id": it["id"]}, {"_id": 0}))
        row = {"sku": it.get("sku"), "ordered": it.get("qty"), "produced": 0, "declared": 0,
               "accepted": 0, "reject": 0, "rework_open": 0, "repaired": 0, "scrap": 0}
        for ji in jis:
            row["produced"] += int(ji.get("produced_qty") or 0)
            row["declared"] += int(ji.get("qty_declared") or 0)
            row["accepted"] += int(ji.get("qty_accepted") or 0)
            row["reject"] += int(ji.get("qty_reject") or 0)
            row["rework_open"] += int(ji.get("qty_rework_open") or 0)
            row["repaired"] += int(ji.get("qty_repaired") or 0)
            row["scrap"] += int(ji.get("qty_scrap") or 0)
        row["selisih_kirim_vs_hasil_qc"] = row["declared"] - row["accepted"] - row["reject"]
        out.append(row)
    return out


def show_ledger(po_id: str, title: str):
    print(f"  {Y}{title}{X}")
    print(f"    {'SKU':<22}{'pesan':>6}{'produksi':>9}{'declared':>9}{'lolos':>7}"
          f"{'reject':>7}{'rework':>7}{'selisih':>8}")
    for r in ledger_rows(po_id):
        print(f"    {str(r['sku'])[:22]:<22}{r['ordered']:>6}{r['produced']:>9}{r['declared']:>9}"
              f"{r['accepted']:>7}{r['reject']:>7}{r['rework_open']:>7}"
              f"{r['selisih_kirim_vs_hasil_qc']:>8}")


def pick_vendor() -> tuple[str, str]:
    """Vendor CMT yang sah (dipakai PO yang sudah ada)."""
    po = db.production_pos.find_one({"vendor_id": {"$nin": [None, ""]}},
                                    {"_id": 0, "vendor_id": 1, "vendor_name": 1})
    return po["vendor_id"], po.get("vendor_name", "Vendor CMT")


def make_po(po_number: str, items: list, vendor_id: str) -> dict:
    st, po = call("POST", "/api/production-pos", {
        "po_number": po_number, "business_type": "maklon", "vendor_id": vendor_id,
        "customer_name": "UJI Buyer Owner", "status": "Confirmed",
        "po_date": str(date.today()), "deadline": str(date.today()),
        "items": items}, expect=[201])
    if st != 201:
        raise SystemExit(f"gagal buat PO {po_number}")
    st, qc = call("POST", f"/api/production-pos/{po['id']}/quick-complete",
                  {"skip_buyer_shipment": True}, expect=[200])
    if st != 200:
        raise SystemExit(f"gagal quick-complete {po_number}: {qc}")
    return po


def job_items_of(po_id: str) -> list[dict]:
    ids = [i["id"] for i in db.po_items.find({"po_id": po_id}, {"_id": 0, "id": 1})]
    return list(db.production_job_items.find({"po_item_id": {"$in": ids}}, {"_id": 0}))


def receive(po: dict, vendor_id: str, vendor_name: str, lines: list, note="") -> dict:
    """Buat penerimaan CMT + baris + selesaikan QC. lines: [(job_item, declared, actual, reject)]"""
    st, rc = call("POST", "/api/prod/cmt-receipts", {
        "cmt_name": vendor_name, "cmt_vendor_id": vendor_id,
        "po_id": po["id"], "po_number": po["po_number"],
        "business_type": "maklon", "notes": note}, expect=[201, 200])
    if st not in (200, 201):
        raise SystemExit(f"gagal buat penerimaan: {rc}")
    for ji, declared, actual, reject in lines:
        st, ln = call("POST", f"/api/prod/cmt-receipts/{rc['id']}/lines", {
            "sku_code": ji.get("sku", ""), "product_name": ji.get("product_name", ""),
            "size": ji.get("size", ""), "color": ji.get("color", ""),
            "qty_expected": declared, "qty_shipped_by_cmt": declared,
            "qty_actual": actual, "reject_qty": reject,
            "reject_reason": "jahitan lepas" if reject else "",
            "po_item_id": ji.get("po_item_id"), "job_item_id": ji.get("id")}, expect=[201])
    st, done = call("POST", f"/api/prod/cmt-receipts/{rc['id']}/complete-qc", {}, expect=[200])
    if st != 200:
        raise SystemExit(f"gagal complete-qc: {done}")
    return {"receipt": rc, "result": done}


# ══════════════════════════════════════════════════════════════════════════════
def q1(vendor_id, vendor_name):
    head("Q1 — VENDOR KIRIM 100 A + 100 B · DA TERIMA 90 A · B 100 (10 REJECT → REWORK)")
    po = make_po(f"UJI-Q1-{STAMP}", [
        {"product_name": "Kaos Uji A", "sku": f"UJI-A-{STAMP}", "size": "M", "color": "Navy", "qty": 100},
        {"product_name": "Kaos Uji B", "sku": f"UJI-B-{STAMP}", "size": "L", "color": "Hitam", "qty": 100},
    ], vendor_id)
    print(f"  PO {po['po_number']} dibuat, vendor {vendor_name}, produksi vendor 100 + 100")
    jis = {ji["sku"]: ji for ji in job_items_of(po["id"])}
    ja, jb = jis[f"UJI-A-{STAMP}"], jis[f"UJI-B-{STAMP}"]
    sku_a, sku_b = ja["sku"], jb["sku"]

    sub("Penerimaan: A dideklarasi 100 → fisik 90 (kurang 10) · B dideklarasi 100 → lolos 90 + reject 10")
    rc = receive(po, vendor_id, vendor_name,
                 [(ja, 100, 90, 0), (jb, 100, 90, 10)], note="UJI Q1")
    show_ledger(po["id"], "Buku kuantitas SETELAH QC:")
    print(f"    stok FG {sku_a} = {fg_stock(sku_a)} pcs · {sku_b} = {fg_stock(sku_b)} pcs")

    st, qs = call("GET", f"/api/production-pos/{po['id']}/quantity-summary", expect=[200])
    tot = (qs or {}).get("totals") or qs
    print(f"    ringkasan PO (API): {json.dumps(tot, ensure_ascii=False)[:400]}")

    st, rq = call("GET", f"/api/prod/cmt-reject-queue?po_id={po['id']}", expect=[200])
    print(f"    antrean reject: {rq.get('total')} baris, {rq.get('total_qty_undecided')} pcs belum diputuskan")

    rows = {r["sku"]: r for r in ledger_rows(po["id"])}
    ra, rb = rows[sku_a], rows[sku_b]
    print(f"\n  {B}JAWABAN Q1-a{X}")
    print(f"    · progress produksi vendor SKU A = {ra['produced']} pcs "
          f"({'TETAP 100 (tidak turun jadi 90)' if ra['produced'] == 100 else 'BERUBAH!'})")
    print(f"    · lolos QC DA SKU A = {ra['accepted']} · selisih kirim-vs-QC = "
          f"{ra['selisih_kirim_vs_hasil_qc']} pcs")
    print(f"    · SKU B: produksi {rb['produced']} · lolos {rb['accepted']} · reject {rb['reject']} "
          f"· menunggu rework {rb['rework_open']}")
    if ra["produced"] != 100:
        findings.append("Q1: produced_qty vendor BERUBAH akibat QC DA (seharusnya tetap)")
    if ra["selisih_kirim_vs_hasil_qc"] != 10:
        findings.append("Q1: selisih 10 pcs SKU A tidak terekam di buku kuantitas")

    # apakah selisih (declared - accepted - reject) ditampilkan API/laporan?
    blob = json.dumps(qs, ensure_ascii=False).lower()
    kata = [k for k in ("selisih", "short", "missing", "kurang", "declared") if k in blob]
    print(f"    · kata kunci selisih di ringkasan PO: {kata or 'TIDAK ADA'}")
    if not kata:
        findings.append("Q1: ringkasan PO tidak punya kolom/istilah 'selisih kirim vs diterima' "
                        "→ 10 pcs SKU A yang tidak sampai tidak terlihat sebagai selisih")

    sub("Rework 10 pcs SKU B → retur ke CMT (dikerjakan ulang vendor)")
    line_b = db.cmt_receipt_lines.find_one({"receipt_id": rc["receipt"]["id"], "sku_code": sku_b},
                                          {"_id": 0, "id": 1})
    st, pk = call("POST", "/api/dewi/cmt-permak/from-receipt-line", {
        "receipt_line_id": line_b["id"], "qty": 10, "permak_type": "retur_ke_cmt",
        "problem_type": "jahitan", "reason": "UJI rework"}, expect=[200, 201])
    sj = db.buyer_shipments.find_one({"rework_permak_id": (pk or {}).get("id")},
                                     {"_id": 0, "shipment_number": 1}) if pk else None
    print(f"    permak {pk.get('permak_number')} ({pk.get('permak_type')}) · "
          f"Surat Jalan REWORK: {(sj or {}).get('shipment_number', '(tidak dibuat)')}")
    show_ledger(po["id"], "Buku kuantitas setelah rework dikirim balik:")

    sub("Q1-b — KOREKSI: ternyata SKU A benar 100 terkirim, DA salah hitung")
    line_a = db.cmt_receipt_lines.find_one({"receipt_id": rc["receipt"]["id"], "sku_code": sku_a},
                                           {"_id": 0, "id": 1})
    st_edit, res_edit = call("PUT", f"/api/prod/cmt-receipts/{rc['receipt']['id']}/lines/{line_a['id']}",
                             {"qty_actual": 100}, quiet=True)
    after = {r["sku"]: r for r in ledger_rows(po["id"])}[sku_a]
    line_now = db.cmt_receipt_lines.find_one({"id": line_a["id"]}, {"_id": 0, "qty_actual": 1})
    print(f"    (1) Edit langsung qty fisik baris penerimaan yang SUDAH selesai QC → HTTP {st_edit}")
    print(f"        baris sekarang qty_actual={line_now.get('qty_actual')} · "
          f"buku kuantitas lolos={after['accepted']} · stok FG={fg_stock(sku_a)}")
    if st_edit in (200, 201) and after["accepted"] != int(line_now.get("qty_actual") or 0):
        print(f"        {R}⇒ DATA JADI TIDAK SINKRON{X}: baris bilang "
              f"{line_now.get('qty_actual')}, buku kuantitas & stok tetap {after['accepted']}")
        findings.append("Q1-b BUG: PUT baris penerimaan setelah QC selesai DITERIMA (HTTP 200) tapi "
                        "tidak memperbarui buku kuantitas & stok FG → angka bercabang (INV-14 pecah)")
    # kembalikan ke 90 supaya bisa uji jalur yang benar
    call("PUT", f"/api/prod/cmt-receipts/{rc['receipt']['id']}/lines/{line_a['id']}",
         {"qty_actual": 90}, quiet=True)

    ja_fresh = db.production_job_items.find_one({"id": ja["id"]}, {"_id": 0})
    rc2 = receive(po, vendor_id, vendor_name, [(ja_fresh, 10, 10, 0)],
                  note="UJI Q1 koreksi 10 pcs kurang hitung")
    fixed = {r["sku"]: r for r in ledger_rows(po["id"])}[sku_a]
    print(f"    (2) Jalur alternatif: buat PENERIMAAN TAMBAHAN 10 pcs "
          f"({rc2['receipt']['receipt_code']}) → lolos jadi {fixed['accepted']} · "
          f"stok FG {fg_stock(sku_a)} · selisih {fixed['selisih_kirim_vs_hasil_qc']}")
    if fixed["accepted"] == 100 and fixed["selisih_kirim_vs_hasil_qc"] == 0:
        print(f"        {G}⇒ jalur ini BENAR & konsisten{X} (tapi menambah 1 dokumen penerimaan, "
              f"declared jadi {fixed['declared']} — bukan koreksi dokumen aslinya)")
    if fixed["declared"] != 100:
        findings.append(f"Q1-b: koreksi lewat penerimaan tambahan membuat qty_declared "
                        f"jadi {fixed['declared']} (>100) — angka 'dikirim vendor' jadi dobel hitung")
    return po


def q2(vendor_id, vendor_name):
    head("Q2 — 5 PO × 100 PCS · MASING-MASING 5 KALI KIRIM PARTIAL · 1 SURAT JALAN GABUNGAN 500")
    pos, receipts, items_payload = [], [], []
    for n in range(1, 6):
        sku = f"UJI-P{n}-{STAMP}"
        po = make_po(f"UJI-Q2-{n}-{STAMP}", [
            {"product_name": f"Kemeja Uji {n}", "sku": sku, "size": "M",
             "color": "Putih", "qty": 100}], vendor_id)
        ji = job_items_of(po["id"])[0]
        for k in range(5):                      # 5 kali kirim partial @20 pcs
            r = receive(po, vendor_id, vendor_name, [(ji, 20, 20, 0)],
                        note=f"UJI partial {k + 1}/5")
            receipts.append(r["receipt"]["id"])
        rows = ledger_rows(po["id"])[0]
        print(f"  PO {po['po_number']}: 5× kirim 20 pcs → lolos QC {rows['accepted']}/100 pcs")
        pos.append(po)
        items_payload.append({"po_item_id": ji["po_item_id"], "job_item_id": ji["id"],
                              "sku": sku, "product_name": ji.get("product_name", ""),
                              "size": ji.get("size", ""), "color": ji.get("color", ""),
                              "qty_shipped": 100})

    sub("Buat SATU surat jalan buyer GABUNGAN dari 25 penerimaan / 5 PO")
    st, bs = call("POST", "/api/buyer-shipments", {
        "receiver_type": "buyer", "source_receipt_ids": receipts,
        "vendor_id": vendor_id, "shipment_date": str(date.today()),
        "notes": "UJI surat jalan gabungan 5 PO", "items": items_payload}, expect=[200, 201])
    if st not in (200, 201):
        findings.append(f"Q2 GAGAL: surat jalan gabungan ditolak → {str(bs)[:200]}")
        return None, None
    ship_id = bs.get("id") or (bs.get("shipment") or {}).get("id")
    st, det = call("GET", f"/api/buyer-shipments/{ship_id}", expect=[200])
    d = det if isinstance(det, dict) else {}
    its = d.get("items") or []
    total = sum(int(i.get("qty_shipped") or 0) for i in its)
    print(f"  {G}✓{X} Surat jalan {d.get('shipment_number')} · consolidated={d.get('consolidated')} "
          f"· jumlah PO={len(d.get('po_ids') or [])} · baris={len(its)} · TOTAL {total} pcs")
    for i in its:
        print(f"      {i.get('sku'):<22} PO {str(i.get('po_number') or '-'):<20} {i.get('qty_shipped')} pcs")
    if total != 500:
        findings.append(f"Q2: total qty surat jalan gabungan = {total}, seharusnya 500")
    if len(d.get("po_ids") or []) != 5:
        findings.append(f"Q2: po_ids di surat jalan = {len(d.get('po_ids') or [])}, seharusnya 5")

    st, var = call("GET", "/api/buyer-receipt-variance", expect=[200])
    mine = [v for v in (var or []) if str(v.get("po_number", "")).startswith(f"UJI-Q2")]
    print(f"  laporan Kirim vs Diterima: {len(mine)} baris PO terkait uji "
          f"(total kirim {sum(v['total_shipped'] for v in mine)} pcs)")
    if len(mine) != 5:
        findings.append(f"Q2: laporan variance hanya menampilkan {len(mine)}/5 PO dari surat jalan gabungan")

    sub("Uji pagar: coba kirim 1 pcs lagi di luar qty yang lolos QC (harus DITOLAK)")
    st_over, over = call("POST", "/api/buyer-shipments", {
        "receiver_type": "buyer", "source_receipt_ids": receipts, "vendor_id": vendor_id,
        "shipment_date": str(date.today()), "items": [dict(items_payload[0], qty_shipped=1)]},
        quiet=True)
    print(f"    → HTTP {st_over} {'(DITOLAK, benar)' if st_over >= 400 else '(DITERIMA — over-ship lolos!)'}"
          f" {str(over.get('detail', ''))[:150]}")
    if st_over < 400:
        findings.append("Q2 BUG: over-ship 1 pcs di atas qty lolos QC DITERIMA sistem")
    return pos, (ship_id, its)


def q3(pos, ship):
    head("Q3 — BUYER TERIMA LEBIH SEDIKIT (SELISIH): ADAKAH PENYESUAIAN OTOMATIS?")
    if not ship:
        print("  dilewati (Q2 gagal)")
        return
    ship_id, its = ship
    it = its[0]
    sku = it.get("sku")
    po_num = it.get("po_number")
    po = db.production_pos.find_one({"po_number": po_num}, {"_id": 0}) if po_num else None
    if not po:
        poi = db.po_items.find_one({"id": it.get("po_item_id")}, {"_id": 0, "po_id": 1})
        po = db.production_pos.find_one({"id": (poi or {}).get("po_id")}, {"_id": 0})

    stok_sebelum = fg_stock(sku)
    print(f"  Target: {sku} pada PO {po.get('po_number')} — dikirim {it.get('qty_shipped')} pcs")
    print(f"  stok FG SETELAH dikirim ke buyer (sebelum input qty diterima) = {stok_sebelum} pcs")
    if stok_sebelum >= 100:
        findings.append(f"Q3 BUG: stok FG {sku} masih {stok_sebelum} pcs padahal 100 pcs sudah "
                        "dikirim ke buyer — pengiriman ke buyer TIDAK mengurangi stok gudang FG "
                        "(hanya jurnal COGS)")

    sub("Admin mencatat: buyer hanya menerima 95 pcs (selisih 5)")
    st, res = call("PUT", f"/api/buyer-shipment-items/{it['id']}/received",
                   {"qty_received": 95, "reason": "UJI buyer hitung kurang 5"}, expect=[200])
    print(f"    → variance dari API = {res.get('variance')} pcs · "
          f"auto-close PO = {json.dumps(res.get('po_auto_close'), ensure_ascii=False)[:160]}")

    st, var = call("GET", f"/api/buyer-receipt-variance?po_id={po['id']}", expect=[200])
    for v in (var or []):
        print(f"    laporan: PO {v.get('po_number')} kirim {v.get('total_shipped')} · "
              f"diterima {v.get('total_received')} · selisih {v.get('total_variance')}")

    po_fresh = db.production_pos.find_one({"id": po["id"]}, {"_id": 0, "status": 1, "po_number": 1})
    st, ful = call("GET", f"/api/production-pos/{po['id']}/fulfillment", expect=[200])
    print(f"    status PO sekarang: {po_fresh.get('status')} · fulfillment: "
          f"{json.dumps(ful, ensure_ascii=False)[:220]}")

    rows = ledger_rows(po["id"])[0]
    print(f"    buku kuantitas job: produksi {rows['produced']} · lolos QC {rows['accepted']} "
          f"· reject {rows['reject']} (tidak berubah oleh selisih buyer)")
    print(f"    stok FG {sku} setelah input 95 = {fg_stock(sku)} pcs")

    sub("Apakah 5 pcs selisih membuka kapasitas kirim ulang?")
    st_re, re_ship = call("POST", "/api/buyer-shipments", {
        "receiver_type": "buyer",
        "source_receipt_ids": list(db.cmt_receipts.distinct("id", {"po_id": po["id"]})),
        "vendor_id": po.get("vendor_id"), "shipment_date": str(date.today()),
        "items": [{"po_item_id": it.get("po_item_id"), "job_item_id": it.get("job_item_id"),
                   "sku": sku, "qty_shipped": 5}]}, quiet=True)
    print(f"    kirim ulang 5 pcs → HTTP {st_re} "
          f"{'(diizinkan — kapasitas terbuka lagi)' if st_re in (200, 201) else str(re_ship.get('detail',''))[:160]}")

    sub("Adakah dokumen tindak lanjut otomatis untuk selisih (klaim / nota kredit / investigasi)?")
    cn = db.dewi_maklon_credit_notes.count_documents({"po_id": po["id"]})
    claims = [c for c in db.list_collection_names() if "claim" in c or "dispute" in c]
    print(f"    nota kredit untuk PO ini: {cn} · koleksi klaim/dispute di DB: {claims or 'TIDAK ADA'}")
    if cn == 0:
        findings.append("Q3: mencatat qty diterima 95 (selisih 5) TIDAK membuat dokumen tindak lanjut "
                        "apa pun (nota kredit/klaim/penyesuaian stok) — hanya laporan selisih + "
                        "kapasitas kirim ulang. Penutupan kurang (close-short) harus dipicu MANUAL")
    st, cs = call("POST", f"/api/production-pos/{po['id']}/close-short",
                  {"reason": "UJI tutup kurang 5 pcs", "confirm": True}, quiet=True)
    print(f"    coba close-short manual → HTTP {st}: {json.dumps(cs, ensure_ascii=False)[:260]}")


def main() -> int:
    global TOK
    st, res = call("POST", "/api/auth/login", ADMIN, expect=[200])
    TOK = res.get("token")
    if not TOK:
        print("login gagal")
        return 1
    vendor_id, vendor_name = pick_vendor()
    q1(vendor_id, vendor_name)
    pos, ship = q2(vendor_id, vendor_name)
    q3(pos, ship)

    head("RINGKASAN TEMUAN")
    if not findings:
        print(f"  {G}Tidak ada temuan — ketiga skenario berjalan sesuai harapan.{X}")
    for i, f in enumerate(findings, 1):
        print(f"  {R}{i}.{X} {f}")
    print(f"\n{Y}Data uji berprefix UJI-{STAMP}. Pulihkan DB dengan restore snapshot "
          f"'pre_uji_skenario_owner'.{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
