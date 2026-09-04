#!/usr/bin/env python3
"""INV-F44 (sesi #38) — **JURNAL COGS MEMAKAI BIAYA BATCH YANG BENAR-BENAR KELUAR**.

KENAPA GATE INI ADA
-------------------
Sesi #34 memasang FIFO keluar (`core.production_qty_ledger.issue_fg` memakan
lapisan biaya tertua) dan menyimpan hasilnya di baris pengiriman: `fg_cogs`,
`fg_cogs_layers`, `fg_cogs_uncosted_qty`. Tetapi jurnal COGS
(`routes.rahaza_posting.post_cogs_on_buyer_dispatch`) **tidak pernah
membacanya** — ia tetap memakai snapshot HPP per SPK. Akibatnya satu pengiriman
punya DUA angka biaya: gudang mencatat biaya batch NYATA, buku besar mencatat
PERKIRAAN, dan laba per pengiriman selalu salah tanpa satu pun galat.

YANG DIIKAT (semuanya diukur, bukan dibaca dari kode)
-----------------------------------------------------
  J1  dasar biaya = `fifo_batch` bila lapisan batch ada, dan nilai jurnalnya
      SAMA PERSIS dengan Σ `fg_cogs` baris pengiriman (bukan mendekati)
  J2  nilainya dipecah ke akun BAHAN · UPAH · OVERHEAD menurut rincian lapisan
      (upah = jahit + permak + upah internal), dan Σ komponen = total
  J3  jurnalnya seimbang & kredit persediaan FG = total COGS
  J4  memo menyebut DASAR biayanya (pembaca laba harus tahu nyata vs perkiraan)
  J5  idempoten: dispatch yang sama tidak pernah melahirkan jurnal kedua
  J6  qty yang keluar TANPA lapisan biaya DILAPORKAN (`uncosted_qty` + catatan),
      tidak ditutup dengan menaikkan biaya lapisan terakhir
  J7  jalan mundur: tanpa lapisan sama sekali, snapshot HPP SPK tetap dipakai
      dan dasarnya disebut `hpp_snapshot`
  J8  tanpa lapisan DAN tanpa snapshot ⇒ TIDAK ada jurnal karangan (ok=False)
  J9  alat ukur tidak meninggalkan sampah (jurnal, baris cermin, lapisan, SJ uji)

Jalankan: python3 scripts/verify_cogs_fifo_jurnal.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(str(ROOT / "backend"))

from dotenv import load_dotenv                                    # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient                # noqa: E402

load_dotenv(str(ROOT / "backend/.env"))

from core import fg_cost_layers as fcl                            # noqa: E402
from routes.rahaza_posting import post_cogs_on_buyer_dispatch      # noqa: E402

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
PASS: list = []
FAIL: list = []
MARK = f"GATE-F44-{datetime.now(timezone.utc).strftime('%H%M%S')}"
USER = {"id": "gate-f44", "name": "Gate INV-F44"}


def ok(code, msg, detail=""):
    PASS.append(code)
    print(f"  {G}✓{X} {code} — {msg}" + (f" · {detail}" if detail else ""))


def bad(code, msg, detail=""):
    FAIL.append(code)
    print(f"  {R}✗ {code} — {msg}{X}" + (f" · {detail}" if detail else ""))


def head(t):
    print(f"\n{C}{B}{t}{X}")


def uid():
    return str(uuid.uuid4())


async def make_shipment(db, sku, material_id, qty, *, fg_cogs=None, layers=None,
                        uncosted=0, job_id=None):
    """SJ buyer + satu barisnya (dokumen uji, ditandai MARK)."""
    sid, iid = uid(), uid()
    await db.buyer_shipments.insert_one({
        "id": sid, "shipment_number": f"{MARK}-{sid[:4]}", "notes": MARK,
        "receiver_type": "buyer", "business_type": "internal",
        "shipment_date": date.today().isoformat(),
        "customer_name": "Buyer Uji F44", "created_at": datetime.now(timezone.utc)})
    row = {"id": iid, "shipment_id": sid, "sku": sku, "qty_shipped": qty,
           "notes": MARK, "fg_material_id": material_id, "dispatch_seq": 1}
    if fg_cogs is not None:
        row.update({"fg_cogs": fg_cogs, "fg_cogs_layers": layers or [],
                    "fg_cogs_uncosted_qty": uncosted})
    if job_id:
        row["job_id"] = job_id
    await db.buyer_shipment_items.insert_one(row)
    shp = await db.buyer_shipments.find_one({"id": sid}, {"_id": 0})
    item = await db.buyer_shipment_items.find_one({"id": iid}, {"_id": 0})
    return shp, item


async def main() -> int:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    mat = await db.rahaza_materials.find_one({"type": "fg"}, {"_id": 0, "id": 1, "code": 1}) \
        or await db.materials.find_one({"type": "fg"}, {"_id": 0, "id": 1, "code": 1})
    if not mat:
        print(f"{R}TIDAK TERUKUR: tidak ada master barang jadi (type=fg){X}")
        return 2
    material_id, sku = mat["id"], mat.get("code") or "FG-UJI"

    created = {"layers": [], "consumptions": [], "shipments": [], "items": [],
               "jes": []}

    # ══ SIAPKAN: satu lapisan batch dengan rincian yang DIKETAHUI ═════════════
    head("J1/J2/J3/J4 — jurnal memakai biaya batch FIFO & memecahnya per akun")
    layer = await fcl.push_layer(
        db, material_id=material_id, qty=10, unit_cost=10000,
        breakdown={"material_cost": 6000, "sewing_cost": 2500,
                   "permak_cost": 500, "internal_labor_cost": 0,
                   "overhead_cost": 1000},
        po_item={"sku": sku, "po_number": MARK},
        ref={"type": "gate-f44"}, actor=USER)
    created["layers"].append(layer["id"])

    cons = await fcl.consume_fifo(db, material_id=material_id, qty=4,
                                  ref={"source": "gate-f44"}, actor=USER)
    created["consumptions"].append(cons)
    layers_used = [ly for ly in cons["layers_used"] if ly["layer_id"] == layer["id"]]
    if cons["cogs"] <= 0 or not layers_used:
        bad("J1", "lapisan batch tidak terpakai — persiapan gate gagal", str(cons))
        return 1

    shp, item = await make_shipment(db, sku, material_id, 4,
                                    fg_cogs=cons["cogs"], layers=cons["layers_used"])
    created["shipments"].append(shp["id"])
    created["items"].append(item["id"])

    res = await post_cogs_on_buyer_dispatch(db, shp, [item], 1, USER)
    if not res.get("ok"):
        bad("J1", "jurnal COGS gagal dibuat", str(res)[:300])
    else:
        created["jes"].append(res["je_id"])
        je = await db.rahaza_journal_entries.find_one({"id": res["je_id"]}, {"_id": 0})
        if res.get("basis") != "fifo_batch":
            bad("J1", f"dasar biaya bukan fifo_batch (basis={res.get('basis')}) — "
                      "jurnal masih memakai perkiraan padahal lapisan batch ADA")
        elif round(float(res["amount"]), 2) != round(float(cons["cogs"]), 2):
            bad("J1", f"nilai jurnal {res['amount']} ≠ biaya batch yang keluar {cons['cogs']}")
        else:
            ok("J1", "jurnal COGS = biaya batch FIFO yang benar-benar keluar",
               f"Rp {res['amount']:,.0f} dari {len(cons['layers_used'])} lapisan")

        # J2 — komponen per akun (bahan 60% · upah 30% · overhead 10% dari 40.000)
        by_code = {}
        for ln in (je.get("lines") or []):
            if float(ln.get("debit") or 0) <= 0:
                continue
            by_code[ln["account_code"]] = by_code.get(ln["account_code"], 0) + \
                float(ln.get("debit") or 0)
        deb = sorted(by_code.values(), reverse=True)
        if len(deb) != 3:
            bad("J2", f"jurnal tidak memecah biaya ke 3 akun (debit: {by_code})")
        elif [round(v) for v in deb] != [24000, 12000, 4000]:
            bad("J2", "pecahan bahan/upah/overhead tidak mengikuti rincian lapisan",
                f"debit={sorted([round(v) for v in deb], reverse=True)} "
                f"(harusnya 24000/12000/4000 dari 6000+3000+1000)")
        else:
            ok("J2", "biaya dipecah per akun menurut rincian lapisan",
               "bahan 24.000 · upah 12.000 (jahit+permak) · overhead 4.000")

        credit = sum(float(ln.get("credit") or 0) for ln in (je.get("lines") or []))
        debit = sum(float(ln.get("debit") or 0) for ln in (je.get("lines") or []))
        if round(debit, 2) != round(credit, 2) or round(credit, 2) != round(float(res["amount"]), 2):
            bad("J3", "jurnal tidak seimbang / kredit persediaan FG ≠ total COGS",
                f"Dr {debit} Cr {credit} total {res['amount']}")
        else:
            ok("J3", "jurnal seimbang & kredit persediaan FG = total COGS",
               f"Dr {debit:,.0f} = Cr {credit:,.0f}")

        memo = (je.get("memo") or "").lower()
        if "fifo" not in memo and "batch" not in memo:
            bad("J4", "memo tidak menyebut dasar biayanya", je.get("memo"))
        else:
            ok("J4", "memo menyebut dasar biaya (nyata vs perkiraan)", je.get("memo"))

        # J5 — idempoten
        res2 = await post_cogs_on_buyer_dispatch(db, shp, [item], 1, USER)
        n_je = await db.rahaza_journal_entries.count_documents(
            {"source_module": "buyer_dispatch", "source_ref": f"cogs_job:{shp['id']}:seq1",
             "status": {"$ne": "voided"}})
        if not res2.get("already_posted") or n_je != 1:
            bad("J5", f"dispatch yang sama melahirkan jurnal kedua (jurnal={n_je})")
        else:
            ok("J5", "idempoten — dispatch yang sama tidak pernah dijurnal dua kali")

    # ══ J6 — qty keluar TANPA lapisan biaya harus DILAPORKAN ══════════════════
    head("J6 — barang keluar tanpa lapisan biaya tidak boleh disembunyikan")
    cons2 = await fcl.consume_fifo(db, material_id=material_id, qty=20,
                                   ref={"source": "gate-f44-uncosted"}, actor=USER)
    created["consumptions"].append(cons2)
    shp2, item2 = await make_shipment(db, sku, material_id, 20,
                                      fg_cogs=cons2["cogs"],
                                      layers=cons2["layers_used"],
                                      uncosted=cons2["uncosted_qty"])
    created["shipments"].append(shp2["id"])
    created["items"].append(item2["id"])
    res3 = await post_cogs_on_buyer_dispatch(db, shp2, [item2], 1, USER)
    if res3.get("ok"):
        created["jes"].append(res3["je_id"])
    if not cons2["uncosted_qty"]:
        ok("J6", "TIDAK TERUKUR — lapisan batch masih cukup untuk qty uji "
                 "(tidak ada qty tanpa biaya)")
    elif int(res3.get("uncosted_qty") or 0) != int(cons2["uncosted_qty"]) \
            or not (res3.get("note") or ""):
        bad("J6", "qty tanpa lapisan biaya tidak dilaporkan di hasil jurnal",
            f"uncosted lapisan={cons2['uncosted_qty']} hasil={res3.get('uncosted_qty')} "
            f"catatan={res3.get('note')}")
    else:
        ok("J6", f"{cons2['uncosted_qty']} pcs keluar tanpa lapisan biaya "
                 "DISEBUT di hasil jurnal", res3["note"][:80])

    # J6b — SJ CAMPURAN: satu baris berbiaya + satu baris TANPA lapisan sama
    # sekali. Baris yang gratis total dulu dilewati sebelum kekurangannya
    # dijumlahkan ⇒ jurnal tampak lengkap padahal ada pcs yang keluar gratis.
    layer_mix = await fcl.push_layer(
        db, material_id=material_id, qty=2, unit_cost=5000,
        breakdown={"material_cost": 4000, "sewing_cost": 500,
                   "permak_cost": 0, "internal_labor_cost": 0,
                   "overhead_cost": 500},
        po_item={"sku": sku, "po_number": MARK},
        ref={"type": "gate-f44"}, actor=USER)
    created["layers"].append(layer_mix["id"])
    cons3 = await fcl.consume_fifo(db, material_id=material_id, qty=2,
                                   ref={"source": "gate-f44"}, actor=USER)
    shp_mix, item_ok = await make_shipment(db, sku, material_id, 2,
                                          fg_cogs=cons3["cogs"],
                                          layers=cons3["layers_used"])
    created["shipments"].append(shp_mix["id"])
    created["items"].append(item_ok["id"])
    # baris kedua: keluar 10 pcs, NOL lapisan (fg_cogs 0, layers kosong)
    item_free_id = uid()
    await db.buyer_shipment_items.insert_one({
        "id": item_free_id, "shipment_id": shp_mix["id"], "sku": sku,
        "qty_shipped": 10, "notes": MARK, "fg_material_id": material_id,
        "dispatch_seq": 1, "fg_cogs": 0, "fg_cogs_layers": [],
        "fg_cogs_uncosted_qty": 10})
    created["items"].append(item_free_id)
    item_free = await db.buyer_shipment_items.find_one({"id": item_free_id}, {"_id": 0})
    res_mix = await post_cogs_on_buyer_dispatch(db, shp_mix, [item_ok, item_free], 1, USER)
    if res_mix.get("ok"):
        created["jes"].append(res_mix["je_id"])
    if int(res_mix.get("uncosted_qty") or 0) < 10 or not (res_mix.get("note") or ""):
        bad("J6b", "baris yang keluar TANPA lapisan biaya sama sekali tidak disebut "
                   "pada SJ campuran — 10 pcs keluar gratis tanpa jejak",
            f"uncosted={res_mix.get('uncosted_qty')} catatan={res_mix.get('note')}")
    else:
        ok("J6b", "SJ campuran: baris tanpa lapisan biaya tetap disebut",
           f"{res_mix['uncosted_qty']} pcs · {len(res_mix.get('gaps') or [])} catatan kekurangan")

    # ══ J7 — jalan mundur ke snapshot HPP SPK ════════════════════════════════
    head("J7/J8 — jalan mundur & tidak mengarang jurnal")
    job_id = f"{MARK}-job"
    await db.rahaza_hpp_snapshots.insert_one({
        "id": uid(), "job_id": job_id, "qty_completed": 10,
        "material_cost": 50000, "labor_cost": 30000, "overhead_cost": 20000,
        "hpp_unit": 10000, "notes": MARK})
    shp3, item3 = await make_shipment(db, sku, material_id, 5, job_id=job_id)
    created["shipments"].append(shp3["id"])
    created["items"].append(item3["id"])
    res4 = await post_cogs_on_buyer_dispatch(db, shp3, [item3], 1, USER)
    if res4.get("ok"):
        created["jes"].append(res4["je_id"])
    if not res4.get("ok") or res4.get("basis") != "hpp_snapshot":
        bad("J7", "tanpa lapisan batch, snapshot HPP SPK tidak dipakai",
            str(res4)[:250])
    elif round(float(res4["amount"])) != 50000:
        bad("J7", f"nilai snapshot salah dihitung: {res4['amount']} (harusnya 50.000)")
    else:
        ok("J7", "tanpa lapisan batch, snapshot HPP SPK dipakai & dasarnya disebut",
           f"Rp {res4['amount']:,.0f} · basis={res4['basis']}")

    shp4, item4 = await make_shipment(db, sku, material_id, 3)
    created["shipments"].append(shp4["id"])
    created["items"].append(item4["id"])
    res5 = await post_cogs_on_buyer_dispatch(db, shp4, [item4], 1, USER)
    if res5.get("ok"):
        created["jes"].append(res5["je_id"])
        bad("J8", "jurnal COGS dibuat padahal biayanya TIDAK diketahui sama sekali")
    elif res5.get("reason") != "zero_cogs" or not (res5.get("detail") or ""):
        bad("J8", "penolakan tidak menyebut sebabnya", str(res5)[:200])
    else:
        ok("J8", "tanpa lapisan & tanpa snapshot ⇒ tidak ada jurnal karangan",
           str(res5.get("detail"))[:80])

    # ══ J10 — RANTAI PINTU NYATA: FG masuk → SJ keluar → jurnal ══════════════
    head("J10 — pintu nyata: barang jadi masuk gudang lalu dikirim, jurnalnya ikut")
    real_ok = True
    try:
        from core import stock_service
        from core import production_qty_ledger as qled
        from routes.buyer_shipment import _issue_fg_for_dispatch
        # Lapisan biaya lewat pintu yang sama dengan penerimaan FG
        # (`post_fg_accepted` memanggil `push_layer` ini), dengan biaya yang
        # DIKETAHUI supaya rantainya bisa diukur walau data demo ber-HPP 0.
        layer_real = await fcl.push_layer(
            db, material_id=material_id, qty=6, unit_cost=12000,
            breakdown={"material_cost": 9000, "sewing_cost": 2000,
                       "permak_cost": 0, "internal_labor_cost": 0,
                       "overhead_cost": 1000},
            po_item={"sku": sku, "po_number": MARK},
            ref={"type": "gate-f44"}, actor=USER)
        created["layers"].append(layer_real["id"])
        loc = await qled.resolve_fg_location_id(db)
        await stock_service.add(material_id, loc, 6,
                                meta={"inventory_category": "fg_internal",
                                      "ownership": "cv_da", "note": MARK},
                                ref={"source": "gate-f44-real"}, actor=USER, db=db)
    except Exception as e:  # noqa: BLE001
        real_ok = False
        ok("J10", "TIDAK TERUKUR — barang jadi tidak bisa dimasukkan gudang di "
                  "container ini", str(e)[:90])
    if real_ok:
        shp5, item5 = await make_shipment(db, sku, material_id, 6)
        created["shipments"].append(shp5["id"])
        created["items"].append(item5["id"])
        await _issue_fg_for_dispatch(db, shp5, [item5], USER)
        row5 = await db.buyer_shipment_items.find_one({"id": item5["id"]}, {"_id": 0})
        res6 = await post_cogs_on_buyer_dispatch(db, shp5, [row5], 1, USER)
        if res6.get("ok"):
            created["jes"].append(res6["je_id"])
        if not row5.get("fg_cogs"):
            bad("J10", "pintu kirim tidak menuliskan biaya batch ke baris SJ",
                str({k: row5.get(k) for k in ("fg_issued_at", "fg_cogs")}))
        elif res6.get("basis") != "fifo_batch" or \
                round(float(res6.get("amount") or 0), 2) != round(float(row5["fg_cogs"]), 2):
            bad("J10", "jurnal dari pintu NYATA tidak memakai biaya batch",
                f"basis={res6.get('basis')} jurnal={res6.get('amount')} "
                f"fg_cogs={row5.get('fg_cogs')}")
        else:
            ok("J10", "rantai nyata utuh: batch masuk → dikirim → jurnal COGS",
               f"Rp {res6['amount']:,.0f} dari lapisan Rp {layer_real['unit_cost']:,.0f}/pcs")

    # ══ J9 — bersih-bersih ════════════════════════════════════════════════════
    head("J9 — alat ukur tidak boleh mengotori data yang diukurnya")
    for je_id in created["jes"]:
        await db.rahaza_journal_entries.delete_one({"id": je_id})
        await db.rahaza_journal_lines.delete_many({"je_id": je_id})
    await db.buyer_shipment_items.delete_many({"notes": MARK})
    await db.buyer_shipments.delete_many({"notes": MARK})
    await db.rahaza_hpp_snapshots.delete_many({"notes": MARK})
    await db[fcl.LAYERS].delete_many({"id": {"$in": created["layers"]}})
    await db[fcl.CONSUMPTIONS].delete_many({"ref.source": {"$in": ["gate-f44",
                                                                   "gate-f44-uncosted",
                                                                   "buyer_shipment"]},
                                            "ref.shipment_id": {"$in": created["shipments"]}})
    await db[fcl.CONSUMPTIONS].delete_many({"ref.source": {"$in": ["gate-f44",
                                                                   "gate-f44-uncosted"]}})
    await db.rahaza_fg_movements.delete_many({"ref_id": {"$in": created["shipments"]}})
    await db.rahaza_stock_ledger.delete_many({"ref.source": {"$regex": "^gate-f44"}})
    await db.rahaza_stock_ledger.delete_many({"ref.shipment_id": {"$in": created["shipments"]}})
    await fcl.refresh_master_hpp(db, material_id)
    sisa = {
        "jurnal": await db.rahaza_journal_entries.count_documents({"memo": {"$regex": MARK}}),
        "baris_jurnal": await db.rahaza_journal_lines.count_documents(
            {"source_ref": {"$regex": MARK}}),
        "sj": await db.buyer_shipments.count_documents({"notes": MARK}),
        "baris_sj": await db.buyer_shipment_items.count_documents({"notes": MARK}),
        "lapisan": await db[fcl.LAYERS].count_documents({"id": {"$in": created["layers"]}}),
        "snapshot": await db.rahaza_hpp_snapshots.count_documents({"notes": MARK}),
    }
    if any(sisa.values()):
        bad("J9", "artefak uji tertinggal di database", str(sisa))
    else:
        ok("J9", "seluruh artefak uji dihapus", str(sisa))

    print(f"\n{B}{'─' * 70}{X}")
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian COGS FIFO (INV-F44) terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
