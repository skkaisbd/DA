#!/usr/bin/env python3
"""
POC — Master Product: SOP Produksi + Foto + Video (internal) & CMT read-only guide.

Membuktikan (live API):
  1. Upload foto produk model (multipart) + limit ke 8 + file serving /api/files
  2. Upload foto langkah SOP (/models/{id}/sop-image) -> storage_path
  3. Simpan Panduan Produksi (/models/{id}/sop): sop_steps[], reference_videos[], reference_images[]
     + pembersihan (langkah kosong dibuang, seq di-assign)
  4. GET /models mengembalikan field baru
  5. Vendor CMT: buat partner+akun+job(model_id) -> login vendor -> production-guide
     berisi SOP+foto+video; SCOPING: vendor lain tidak bisa akses job bukan miliknya
  6. Legacy cleanup: koleksi products/product_variants/rahaza_styles tidak ada

Run: python3 /app/tests/poc_master_product_sop.py
"""
import io
import os
import sys
import uuid
import requests
from PIL import Image
from pymongo import MongoClient

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

_p = _f = 0
def check(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1; print(f"  ✅ {name}")
    else:
        _f += 1; print(f"  ❌ {name}  {detail}")

def png_bytes(color=(120, 80, 200)):
    buf = io.BytesIO(); Image.new("RGB", (40, 40), color).save(buf, "PNG"); return buf.getvalue()

def login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status(); return r.json()["token"]

def main():
    print("=" * 70); print(" POC — Master Product SOP + Foto + Video + CMT guide"); print("=" * 70)
    tok = login(**ADMIN)
    H = {"Authorization": f"Bearer {tok}"}
    HJ = {**H, "Content-Type": "application/json"}
    db = MongoClient(MONGO_URL)[DB_NAME]

    models = requests.get(f"{BASE}/api/rahaza/models", headers=H, timeout=15).json()
    if not models:
        print("‼️  Tidak ada model. Jalankan seed-sample."); sys.exit(1)
    mid = models[0]["id"]; mcode = models[0]["code"]
    print(f"\nModel: {mcode} ({mid[:8]})")

    # ── T1: upload foto produk ───────────────────────────────────────────────
    print("\n[T1] Upload foto produk (multipart) + file serving")
    r = requests.post(f"{BASE}/api/rahaza/models/{mid}/images", headers=H,
                      files={"file": ("foto1.png", png_bytes(), "image/png")}, timeout=20)
    check("upload foto HTTP 200", r.status_code == 200, f"{r.status_code}: {r.text[:150]}")
    paths = r.json().get("image_paths", []) if r.status_code == 200 else []
    check("image_paths bertambah", len(paths) >= 1, str(len(paths)))
    if paths:
        fr = requests.get(f"{BASE}/api/files/{paths[-1]}?auth={tok}", timeout=15)
        check("file serving 200 + image", fr.status_code == 200 and fr.headers.get("content-type", "").startswith("image/"),
              f"{fr.status_code} {fr.headers.get('content-type')}")

    # ── T2: upload SOP step image ────────────────────────────────────────────
    print("\n[T2] Upload foto langkah SOP")
    r = requests.post(f"{BASE}/api/rahaza/models/{mid}/sop-image", headers=H,
                      files={"file": ("step.png", png_bytes((30, 160, 120)), "image/png")}, timeout=20)
    check("sop-image HTTP 200", r.status_code == 200, f"{r.status_code}: {r.text[:150]}")
    step_img = r.json().get("storage_path", "") if r.status_code == 200 else ""
    check("storage_path returned", bool(step_img), step_img)

    # ── T3: save SOP ─────────────────────────────────────────────────────────
    print("\n[T3] Simpan Panduan Produksi (sop_steps + video + ref images)")
    body = {
        "sop_steps": [
            {"title": "Potong kain", "description": "Potong sesuai pola ukuran.", "image_path": step_img},
            {"title": "Jahit body", "description": "Gabungkan panel depan-belakang."},
            {"title": "", "description": "", "image_path": ""},  # kosong -> harus dibuang
            {"title": "Finishing & QC", "description": "Buang benang, cek jahitan."},
        ],
        "reference_videos": [
            {"url": "https://youtu.be/dQw4w9WgXcQ", "title": "Tutorial jahit body"},
            {"url": "", "title": "kosong"},  # dibuang
        ],
        "reference_images": [
            {"url": "https://example.com/techpack.jpg", "caption": "Tech pack"},
        ],
    }
    r = requests.put(f"{BASE}/api/rahaza/models/{mid}/sop", headers=HJ, json=body, timeout=15)
    check("save SOP HTTP 200", r.status_code == 200, f"{r.status_code}: {r.text[:150]}")
    md = r.json() if r.status_code == 200 else {}
    check("sop_steps bersih == 3 (kosong dibuang)", len(md.get("sop_steps", [])) == 3, str(len(md.get("sop_steps", []))))
    check("seq di-assign (1,2,3)", [s.get("seq") for s in md.get("sop_steps", [])] == [1, 2, 3], str([s.get("seq") for s in md.get("sop_steps", [])]))
    check("step image_path tersimpan", md.get("sop_steps", [{}])[0].get("image_path") == step_img)
    check("reference_videos bersih == 1", len(md.get("reference_videos", [])) == 1, str(md.get("reference_videos")))
    check("reference_images == 1", len(md.get("reference_images", [])) == 1)

    # ── T4: GET models field baru ────────────────────────────────────────────
    print("\n[T4] GET /models memuat field baru")
    g = requests.get(f"{BASE}/api/rahaza/models", headers=H, timeout=15).json()
    gm = next((x for x in g if x["id"] == mid), {})
    check("model punya sop_steps", len(gm.get("sop_steps", [])) == 3)
    check("model punya reference_videos", len(gm.get("reference_videos", [])) == 1)

    # ── T5: CMT vendor guide + scoping ───────────────────────────────────────
    print("\n[T5] Vendor CMT production-guide (scoped)")
    sfx = uuid.uuid4().hex[:6]
    pA = requests.post(f"{BASE}/api/vendor-portal/partners", headers=HJ,
                       json={"name": f"Vendor A {sfx}", "code": f"VA{sfx}"}, timeout=15).json()
    pB = requests.post(f"{BASE}/api/vendor-portal/partners", headers=HJ,
                       json={"name": f"Vendor B {sfx}", "code": f"VB{sfx}"}, timeout=15).json()
    pAid, pBid = pA.get("id"), pB.get("id")
    accA = requests.post(f"{BASE}/api/vendor-portal/accounts", headers=HJ,
                         json={"email": f"va{sfx}@cmt.test", "name": "VA User", "password": "Vendor@123", "partner_id": pAid}, timeout=15)
    accB = requests.post(f"{BASE}/api/vendor-portal/accounts", headers=HJ,
                         json={"email": f"vb{sfx}@cmt.test", "name": "VB User", "password": "Vendor@123", "partner_id": pBid}, timeout=15)
    check("vendor accounts created", accA.status_code == 200 and accB.status_code == 200,
          f"A {accA.status_code} B {accB.status_code}: {accA.text[:100]}")
    job = requests.post(f"{BASE}/api/vendor-portal/jobs", headers=HJ,
                        json={"title": "Jahit " + mcode, "partner_id": pAid, "model_id": mid, "qty_target": 100, "process": "SEWING"}, timeout=15)
    check("job w/ model_id HTTP 200", job.status_code == 200, f"{job.status_code}: {job.text[:150]}")
    jobd = job.json() if job.status_code == 200 else {}
    jid = jobd.get("id")
    check("job carries model_code", jobd.get("model_code") == mcode, str(jobd.get("model_code")))

    tokA = login(f"va{sfx}@cmt.test", "Vendor@123")
    HA = {"Authorization": f"Bearer {tokA}"}
    gr = requests.get(f"{BASE}/api/vendor-portal/my-jobs/{jid}/production-guide", headers=HA, timeout=15)
    check("vendor A guide HTTP 200", gr.status_code == 200, f"{gr.status_code}: {gr.text[:150]}")
    gd = gr.json() if gr.status_code == 200 else {}
    check("guide has_model True", gd.get("has_model") is True, str(gd.get("has_model")))
    check("guide sop_steps == 3", len((gd.get("model") or {}).get("sop_steps", [])) == 3)
    check("guide foto >= 1", len((gd.get("model") or {}).get("image_paths", [])) >= 1)
    check("guide videos == 1", len((gd.get("model") or {}).get("reference_videos", [])) == 1)

    tokB = login(f"vb{sfx}@cmt.test", "Vendor@123")
    HB = {"Authorization": f"Bearer {tokB}"}
    gr2 = requests.get(f"{BASE}/api/vendor-portal/my-jobs/{jid}/production-guide", headers=HB, timeout=15)
    check("SCOPING: vendor B blocked (404)", gr2.status_code == 404, f"got {gr2.status_code}")

    # ── T6: legacy cleanup ───────────────────────────────────────────────────
    print("\n[T6] Legacy collections dibersihkan")
    cols = db.list_collection_names()
    for legacy in ("products", "product_variants", "rahaza_styles"):
        check(f"'{legacy}' tidak ada", legacy not in cols, "masih ada")

    print("\n" + "=" * 70); print(f" RESULT: {_p} passed / {_f} failed"); print("=" * 70)
    sys.exit(0 if _f == 0 else 1)

if __name__ == "__main__":
    main()
