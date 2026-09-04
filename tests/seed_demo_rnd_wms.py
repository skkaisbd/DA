#!/usr/bin/env python3
"""Demo data RnD + WMS Surat Jalan Internal (BOM-driven / fitur P4) — via API asli.

Melengkapi seed_demo_produksi_maklon.py agar SEMUA portal punya data untuk
"dialami seperti user nyata":
  RnD (Portal RnD):
    - Style INTERNAL 'draft'                       (belum diajukan)
    - Style INTERNAL 'pending_owner_review'        (muncul di widget "Menunggu Review")
    - Style INTERNAL 'promoted' -> Production Model (RnD -> Master Data)
    - Style MAKLON  'draft'                        (rnd_type=maklon_product; tak bisa promote)
  WMS Surat Jalan Internal (fitur P4 'Isi dari BOM'):
    - SJ-INTERNAL 'draft'   (baris material dari BOM job internal)
    - SJ-INTERNAL 'issued'  (sudah diterbitkan ke penjahit)

Idempoten (hapus demo lama dulu). Jalankan setelah seed produksi/maklon:
  python3 /app/tests/seed_demo_rnd_wms.py
"""
import os, sys, asyncio, requests
sys.path.insert(0, "/app/backend"); os.chdir("/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from database import get_db

BASE = "http://localhost:8001/api"
RND = f"{BASE}/dewi/rnd"
WMS = f"{BASE}/wms/delivery-notes"
DEMO_STYLE_CODES = ["DA-TS01-RND", "DA-HD02-RND", "DA-PL03-RND", "MK-JKT-RND"]
DEMO_MODEL_CODE = "DA-PL03"
log = lambda m: print(f"  {m}")


def tok():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


async def cleanup(db):
    log("Cleanup demo RnD + SJ lama...")
    styles = await db.dewi_rnd_styles.find({"style_code": {"$in": DEMO_STYLE_CODES}}, {"id": 1, "promoted_to_model_id": 1}).to_list(None)
    for s in styles:
        if s.get("promoted_to_model_id"):
            await db.rahaza_models.delete_one({"id": s["promoted_to_model_id"]})
    await db.dewi_rnd_styles.delete_many({"style_code": {"$in": DEMO_STYLE_CODES}})
    await db.rahaza_models.delete_many({"rnd_style_code": {"$in": DEMO_STYLE_CODES}})
    # SJ demo (tandai via notes)
    await db.wh_delivery_notes.delete_many({"notes": {"$regex": "\\[demo-seed\\]"}})


def seed_rnd(t):
    log("RnD: buat 4 style (draft / review / promoted / maklon)...")
    H = {"Authorization": f"Bearer {t}"}

    def create(code, name, rnd_type, category, buyer=""):
        r = requests.post(f"{RND}/styles", headers=H, json={
            "style_code": code, "style_name": name, "rnd_type": rnd_type,
            "category": category, "buyer": buyer, "fabric_type": "Cotton Combed 30s",
            "season": "2026 SS", "description": f"Style demo {name}"}, timeout=20)
        r.raise_for_status()
        return r.json()

    def post(path, sid, body=None):
        r = requests.post(f"{RND}/styles/{sid}/{path}", headers=H, json=body or {}, timeout=20)
        r.raise_for_status()
        return r.json()

    # A: draft internal
    a = create("DA-TS01-RND", "Kaos Basic Dewi Aditya", "internal_product", "Kaos")
    log(f"   Style {a['style_code']} (draft) ok")
    # B: submit -> pending_owner_review
    b = create("DA-HD02-RND", "Hoodie Premium Dewi", "internal_product", "Hoodie")
    post("submit-for-review", b["id"], {"notes": "Mohon review desain hoodie premium"})
    log("   Style DA-HD02-RND (pending_owner_review — muncul di widget Menunggu Review) ok")
    # C: submit -> approve -> promote (RnD -> Production Model)
    c = create("DA-PL03-RND", "Polo Sport Dewi", "internal_product", "Polo")
    post("submit-for-review", c["id"], {"notes": "Review polo sport"})
    post("owner-approve", c["id"], {"notes": "Disetujui untuk produksi"})
    pr = post("promote-to-production", c["id"], {"model_code": DEMO_MODEL_CODE})
    log(f"   Style DA-PL03-RND (approved -> PROMOTED ke Model {pr.get('model_code')}) ok")
    # D: maklon style (draft)
    d = create("MK-JKT-RND", "Jaket Sport Bumi (Maklon)", "maklon_product", "Jaket", buyer="CV Bumi Sportwear")
    log(f"   Style {d['style_code']} (maklon_product, draft) ok")


def seed_wms_sj(t):
    log("WMS Surat Jalan Internal (P4 'Isi dari BOM')...")
    H = {"Authorization": f"Bearer {t}"}
    # ambil job internal
    jr = requests.get(f"{BASE}/production-jobs?business_type=internal", headers=H, timeout=20)
    jr.raise_for_status()
    d = jr.json()
    jobs = d if isinstance(d, list) else d.get("items", [])
    jobs = [j for j in jobs if j.get("business_type") == "internal"][:2]
    if not jobs:
        log("   (tidak ada job internal — lewati SJ)")
        return
    created = []
    for idx, job in enumerate(jobs):
        jid, jno = job["id"], job.get("job_number", "")
        bl = requests.get(f"{BASE}/production-jobs/{jid}/bom-material-lines", headers=H, timeout=20)
        if bl.status_code != 200:
            log(f"   BOM lines {jno} HTTP {bl.status_code} — skip"); continue
        lines_src = bl.json().get("lines", [])
        if not lines_src:
            log(f"   {jno} tanpa baris BOM — skip"); continue
        lines = [{"description": l["description"], "qty": l["qty"], "unit": l.get("unit", "pcs"),
                  "remarks": l.get("remarks", "")} for l in lines_src]
        payload = {
            "sj_type": "SJ-INTERNAL",
            "recipient_name": "CV Jahit Mitra CMT (Penjahit)",
            "recipient_address": "Sragen, Jawa Tengah",
            "shipper_name": "Siti (Gudang)",
            "vehicle_no": "AD 1234 XY",
            "notes": f"[demo-seed] Kirim material produksi job {jno} (dari BOM)",
            "reference_type": "wo", "reference_id": jid, "reference_no": jno,
            "lines": lines,
        }
        cr = requests.post(WMS, headers=H, json=payload, timeout=20)
        cr.raise_for_status()
        sj = cr.json()["sj"]
        created.append(sj)
        log(f"   SJ {sj['sj_number']} (SJ-INTERNAL, {len(lines)} baris BOM dari {jno}) ok")
        # SJ kedua -> issue (terbitkan)
        if idx == 1:
            ir = requests.post(f"{WMS}/{sj['id']}/issue", headers=H,
                               json={"shipper_name": "Siti (Gudang)", "vehicle_no": "AD 1234 XY", "notes": "Diterbitkan ke penjahit"}, timeout=20)
            if ir.status_code == 200:
                log(f"   SJ {sj['sj_number']} -> ISSUED ok")
            else:
                log(f"   issue {sj['sj_number']} HTTP {ir.status_code}: {ir.text[:160]}")
    return created


async def verify(db, t):
    log("Verifikasi...")
    H = {"Authorization": f"Bearer {t}"}
    n_styles = await db.dewi_rnd_styles.count_documents({"style_code": {"$in": DEMO_STYLE_CODES}})
    n_pending = await db.dewi_rnd_styles.count_documents({"status": "pending_owner_review"})
    n_promoted = await db.rahaza_models.count_documents({"rnd_style_code": DEMO_MODEL_CODE + "-RND"})
    n_sj = await db.wh_delivery_notes.count_documents({"sj_type": "SJ-INTERNAL"})
    n_sj_issued = await db.wh_delivery_notes.count_documents({"sj_type": "SJ-INTERNAL", "status": "issued"})
    log(f"   RnD styles demo={n_styles} | pending_owner_review={n_pending} | model dari promote={n_promoted}")
    log(f"   SJ-INTERNAL total={n_sj} | issued={n_sj_issued}")
    # PDF SJ internal bisa dicetak?
    sj = await db.wh_delivery_notes.find_one({"sj_type": "SJ-INTERNAL"}, {"id": 1, "sj_number": 1})
    if sj:
        r = requests.get(f"{WMS}/{sj['id']}/pdf", headers=H, timeout=25)
        ok = r.status_code == 200 and r.content[:4] == b"%PDF"
        log(f"   PDF {sj.get('sj_number')}: {'OK' if ok else 'XX (HTTP ' + str(r.status_code) + ')'}")


async def main():
    db = get_db()
    from core.helpers import now
    t = now()
    tk = tok()
    await cleanup(db)
    seed_rnd(tk)
    seed_wms_sj(tk)
    await verify(db, tk)
    print("\n==== SEED RnD + WMS Surat Jalan Internal SELESAI ====")


if __name__ == "__main__":
    asyncio.run(main())
