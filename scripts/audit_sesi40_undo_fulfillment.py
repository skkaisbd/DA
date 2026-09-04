"""AUDIT SESI #40 — bagian 2: jalur UNDO `update_only` yang SUNGGUHAN (TikTok).

Ekspor A TikTok (`pesanan_tiktok.xlsx`) → Ekspor C TikTok (`retur_refund_tiktok.xlsx`)
→ status pesanan berubah → **rollback** → keadaan sebelum impor harus kembali.
Juga: alasan penolakan baris Ekspor A dilaporkan (jangan ada baris hilang senyap).
Membersihkan artefaknya sendiri.
"""
from __future__ import annotations

import io
import os
import sys

import requests
from pymongo import MongoClient

BASE = "http://localhost:8001"
SAMPLES = "/app/samples/marketplace_2026"
env = dict(l.split("=", 1) for l in open("/app/backend/.env") if "=" in l and not l.startswith("#"))
DB = MongoClient(env["MONGO_URL"].strip().strip('"'))[env["DB_NAME"].strip().strip('"')]

OK, FIND = [], []
ok = lambda c, m: (OK.append(c), print(f"  \033[92m✓ {c}\033[0m {m}"))
bad = lambda c, m: (FIND.append((c, m)), print(f"  \033[91m✗ {c}\033[0m {m}"))
head = lambda t: print(f"\n\033[96m\033[1m▶ {t}\033[0m")

tok = requests.post(f"{BASE}/api/auth/login",
                    json={"email": "admin@garment.com", "password": "Admin@123"},
                    timeout=30).json()
H = {"Authorization": f"Bearer {tok.get('access_token') or tok.get('token')}"}
api = lambda m, p, **kw: requests.request(m, f"{BASE}{p}", headers=H, timeout=300, **kw)


def upload(fname, st, acc):
    raw = open(os.path.join(SAMPLES, fname), "rb").read()
    r = api("POST", "/api/marketing/data-import/upload",
            files={"file": (fname, io.BytesIO(raw))},
            data={"source_type": st, "account_id": acc})
    return r


ACC = next((a for a in api("GET", "/api/marketing/accounts").json()
            if a.get("platform") == "tiktokshop" and "DEMO" in (a.get("account_name") or "")), None)
if not ACC:
    print("tidak ada toko TikTok DEMO"); sys.exit(2)
print("toko uji:", ACC["account_name"])
made = []

head("H — Ekspor A TikTok: alasan penolakan baris harus DISEBUT satu per satu")
r = upload("pesanan_tiktok.xlsx", "marketplace_orders", ACC["id"])
sid_a = (r.json().get("session") or {}).get("id") if r.status_code == 200 else None
if not sid_a:
    bad("H1", f"upload HTTP {r.status_code}: {r.text[:200]}"); print(FIND); sys.exit(1)
made.append(sid_a)
rc = api("POST", f"/api/marketing/data-import/sessions/{sid_a}/commit", json={})
res = rc.json() if rc.status_code == 200 else {}
if rc.status_code != 200:
    bad("H1", f"commit HTTP {rc.status_code}: {rc.text[:300]}")
else:
    ok("H1", f"commit: {res.get('inserted')} masuk · {res.get('rejected')} ditolak")
    notes = res.get("row_notes") or []
    rej = [n for n in notes if n.get("action") == "ditolak"]
    if res.get("rejected") and not rej:
        bad("H2", f"{res.get('rejected')} baris ditolak TANPA satu pun alasan di row_notes")
    else:
        ok("H2", f"{len(rej)} baris ditolak dengan alasan; contoh: "
                 f"{(rej[0].get('why') if rej else '-')}")

head("I — Ekspor C TikTok di atas pesanan itu: status berubah lewat SSOT")
snap_before = {}
r = upload("retur_refund_tiktok.xlsx", "marketplace_fulfillment", ACC["id"])
sid_c = (r.json().get("session") or {}).get("id") if r.status_code == 200 else None
if not sid_c:
    bad("I1", f"upload Ekspor C HTTP {r.status_code}: {r.text[:300]}")
else:
    made.append(sid_c)
    pl = api("GET", f"/api/marketing/data-import/sessions/{sid_c}/plan").json()
    ok("I1", f"pratinjau Ekspor C: {pl.get('counts')}")
    # potret keadaan pesanan yang akan disentuh
    refs = [row.get("ref") or row.get("order_id") for row in (pl.get("rows") or [])]
    for o in DB.marketing_orders.find({"account_id": ACC["id"]},
                                      {"_id": 0, "order_id": 1, "status": 1,
                                       "qty_returned_total": 1, "refund_amount": 1}):
        snap_before[o["order_id"]] = o
    rc = api("POST", f"/api/marketing/data-import/sessions/{sid_c}/commit", json={})
    if rc.status_code != 200:
        bad("I2", f"commit Ekspor C HTTP {rc.status_code}: {rc.text[:300]}")
    else:
        rj = rc.json()
        ok("I2", f"commit Ekspor C: {rj.get('updated')} diperbarui · {rj.get('rejected')} "
                 f"ditolak · undo={rj.get('undo_count')}")
        if not rj.get("updated"):
            bad("I3", f"0 pesanan diperbarui — jalur update_only tidak pernah teruji. "
                      f"row_notes contoh: {(rj.get('row_notes') or [{}])[0]}")
        else:
            changed = 0
            for o in DB.marketing_orders.find({"account_id": ACC["id"]},
                                              {"_id": 0, "order_id": 1, "status": 1}):
                b = snap_before.get(o["order_id"])
                if b and b.get("status") != o.get("status"):
                    changed += 1
            ok("I3", f"{rj.get('updated')} baris diperbarui · {changed} pesanan berubah status")
            if rj.get("updated") and not rj.get("undo_count"):
                bad("I4", "diperbarui tanpa jejak UNDO")
            else:
                ok("I4", f"jejak UNDO {rj.get('undo_count')} baris tersimpan")

            head("J — ROLLBACK Ekspor C: keadaan sebelum impor harus kembali")
            rb = api("POST", f"/api/marketing/data-import/sessions/{sid_c}/rollback")
            if rb.status_code != 200:
                bad("J1", f"rollback HTTP {rb.status_code}: {rb.text[:300]}")
            else:
                rest = rb.json().get("restore") or {}
                ok("J1", f"restore={rest.get('restored')} hanya_field={rest.get('fields_only')} "
                         f"hilang={rest.get('missing')}")
                mismatch, leftover_fields = [], []
                for o in DB.marketing_orders.find({"account_id": ACC["id"]}, {"_id": 0}):
                    b = snap_before.get(o["order_id"])
                    if not b:
                        continue
                    if b.get("status") != o.get("status"):
                        mismatch.append((o["order_id"], b.get("status"), o.get("status")))
                    for f in ("refund_amount", "qty_returned_total"):
                        if (b.get(f) in (None, "")) and o.get(f) not in (None, ""):
                            leftover_fields.append((o["order_id"], f, o.get(f)))
                if mismatch and rest.get("fields_only"):
                    ok("J2", f"{len(mismatch)} pesanan status TETAP — dan laporan MENYEBUTNYA "
                             f"sebagai 'hanya field' ({rest.get('fields_only')}): {mismatch[:3]}")
                elif mismatch:
                    bad("J2", f"status tidak kembali & tidak dilaporkan: {mismatch[:5]}")
                else:
                    ok("J2", "semua status kembali ke keadaan sebelum impor")
                if leftover_fields:
                    bad("J3", f"kolom yang lahir dari berkas masih tertinggal: {leftover_fields[:5]}")
                else:
                    ok("J3", "kolom yang lahir dari berkas benar-benar hilang lagi")
                pend = DB.marketing_data_import_undo.count_documents(
                    {"session_id": sid_c, "restored_at": None})
                (ok if pend == 0 else bad)("J4", f"jejak UNDO menggantung = {pend}")

# ══════════════════════════════════════════════════════════════════════════════
# L — Ekspor B/C SINTETIS yang benar-benar menyentuh pesanan yang baru diimpor.
#     Berkas asli pemilik memuat nomor pesanan dari periode lain, jadi jalur
#     `update_only` (yang diperbaiki sesi #38/#39) tidak pernah teruji olehnya.
# ══════════════════════════════════════════════════════════════════════════════
import csv

head("L — Ekspor B/C SINTETIS: status maju, status terminal, dan status MUNDUR")
dist = {}
for o in DB.marketing_orders.find({"_import_session_id": sid_a}, {"_id": 0, "status": 1}):
    dist[o.get("status")] = dist.get(o.get("status"), 0) + 1
print("      sebaran status hasil Ekspor A:", dist)
# pilih pesanan yang BELUM terminal supaya status benar-benar bisa maju
orders = list(DB.marketing_orders.find(
    {"_import_session_id": sid_a,
     "status": {"$nin": ["cancelled", "returned", "completed"]}}, {"_id": 0}).limit(6))
if len(orders) < 6:
    orders += list(DB.marketing_orders.find(
        {"_import_session_id": sid_a, "status": "completed"}, {"_id": 0}
    ).limit(6 - len(orders)))
if len(orders) < 6:
    bad("L0", f"hanya {len(orders)} pesanan tersedia untuk uji")
else:
    before = {o["order_id"]: dict(o) for o in orders}
    path = "/tmp/audit40_fulfillment.csv"
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["No. Pesanan", "Status Pesanan", "No. Resi", "Kurir",
                    "Waktu Dikirim", "Waktu Dibatalkan", "Alasan Pembatalan",
                    "Nilai Refund"])
        for i, o in enumerate(orders[:6]):
            oid = o["order_id"]
            if i < 3:
                w.writerow([oid, "Dikirim", f"AUD40{i:04d}", "JNE Express",
                            "2026-08-20 10:00:00", "", "", ""])
            elif i < 5:
                w.writerow([oid, "Selesai", f"AUD40{i:04d}", "SiCepat",
                            "2026-08-20 10:00:00", "", "", ""])
            else:
                w.writerow([oid, "Dibatalkan", "", "", "",
                            "2026-08-21 09:00:00", "Pembeli membatalkan", "150000"])
        # baris MUNDUR tanpa bukti batal → harus DITOLAK
        w.writerow([orders[0]["order_id"] + "-TIDAKADA", "Selesai", "", "", "", "", "", ""])
    raw = open(path, "rb").read()
    r = api("POST", "/api/marketing/data-import/upload",
            files={"file": ("audit40_fulfillment.csv", io.BytesIO(raw))},
            data={"source_type": "marketplace_fulfillment", "account_id": ACC["id"]})
    sid_l = (r.json().get("session") or {}).get("id") if r.status_code == 200 else None
    if not sid_l:
        bad("L1", f"upload sintetis HTTP {r.status_code}: {r.text[:300]}")
    else:
        made.append(sid_l)
        rep = (r.json().get("session") or {}).get("mapping_report") or {}
        (ok if rep.get("ready") else bad)("L1", f"pemetaan ready={rep.get('ready')} "
                                                f"missing={rep.get('missing_required')}")
        pl = api("GET", f"/api/marketing/data-import/sessions/{sid_l}/plan").json()
        pc = pl.get("counts") or {}
        rc = api("POST", f"/api/marketing/data-import/sessions/{sid_l}/commit", json={})
        if rc.status_code == 200:
            rj0 = rc.json()
            if (pc.get("diperbarui"), pc.get("ditolak")) != (rj0.get("updated"),
                                                             rj0.get("rejected")):
                bad("L2b", f"pratinjau {pc} ≠ hasil commit "
                           f"(diperbarui={rj0.get('updated')} ditolak={rj0.get('rejected')}) "
                           f"— layar menjanjikan angka yang berbeda dari yang terjadi")
            else:
                ok("L2b", f"pratinjau = hasil commit ({pc.get('diperbarui')} diperbarui · "
                          f"{pc.get('ditolak')} ditolak)")
        if rc.status_code != 200:
            bad("L2", f"commit HTTP {rc.status_code}: {rc.text[:300]}")
        else:
            rj = rc.json()
            ok("L2", f"commit: {rj.get('updated')} diperbarui · {rj.get('rejected')} ditolak "
                     f"· undo={rj.get('undo_count')}")
            if rj.get("inserted"):
                bad("L3", f"update_only MEMBUAT {rj.get('inserted')} baris baru")
            else:
                ok("L3", "tidak membuat baris baru")
            notes = rj.get("row_notes") or []
            for n in notes:
                print(f"      · baris {n.get('row')}: {n.get('action')} — {n.get('why')}")
            if rj.get("rejected") != 1:
                bad("L4", f"baris dengan nomor pesanan tak dikenal seharusnya 1 ditolak, "
                          f"dapat {rj.get('rejected')} (lihat rincian di atas)")
            else:
                ok("L4", "nomor pesanan tak dikenal ditolak dengan alasan")
            after = {o["order_id"]: o for o in DB.marketing_orders.find(
                {"_import_session_id": sid_a}, {"_id": 0})}
            moved = [(k, before[k].get("status"), after[k].get("status"))
                     for k in before if after.get(k, {}).get("status") != before[k].get("status")]
            print("      status awal:", [(k, before[k].get("status")) for k in list(before)[:6]])
            if not moved:
                bad("L5", "tidak ada satu pun status yang benar-benar berubah di DB")
            else:
                ok("L5", f"{len(moved)} status berubah di DB: {moved[:3]}")
            trk = [k for k in before if (after.get(k) or {}).get("tracking_number", "").startswith("AUD40")]
            (ok if trk else bad)("L6", f"{len(trk)} pesanan menerima No. Resi dari berkas")
            if rj.get("undo_count") != rj.get("updated"):
                bad("L7", f"jejak UNDO {rj.get('undo_count')} ≠ baris diperbarui "
                          f"{rj.get('updated')}")
            else:
                ok("L7", f"jejak UNDO = jumlah baris diperbarui ({rj.get('undo_count')})")

            head("M — ROLLBACK Ekspor B/C sintetis")
            rb = api("POST", f"/api/marketing/data-import/sessions/{sid_l}/rollback")
            if rb.status_code != 200:
                bad("M1", f"rollback HTTP {rb.status_code}: {rb.text[:300]}")
            else:
                rest = rb.json().get("restore") or {}
                ok("M1", f"restore={rest.get('restored')} hanya_field={rest.get('fields_only')} "
                         f"hilang={rest.get('missing')}")
                aft = {o["order_id"]: o for o in DB.marketing_orders.find(
                    {"_import_session_id": sid_a}, {"_id": 0})}
                bad_status, leftover = [], []
                for k, b in before.items():
                    a2 = aft.get(k) or {}
                    if (b.get("status") or "") != (a2.get("status") or ""):
                        bad_status.append((k, b.get("status"), a2.get("status")))
                    for f in ("tracking_number", "courier", "cancel_reason",
                              "refund_amount", "shipped_at", "cancelled_at"):
                        if b.get(f) in (None, "") and a2.get(f) not in (None, ""):
                            leftover.append((k, f, a2.get(f)))
                terminal = [x for x in bad_status if x[2] in ("cancelled", "returned",
                                                              "Dibatalkan", "Diretur")]
                if bad_status and len(terminal) == len(bad_status) and rest.get("fields_only"):
                    ok("M2", f"status yang TIDAK kembali hanyalah yang terminal, dan laporan "
                             f"menyebutnya ({rest.get('fields_only')} 'hanya field'): {bad_status}")
                elif bad_status:
                    bad("M2", f"status tidak kembali & bukan kasus terminal / tidak dilaporkan: "
                              f"{bad_status}")
                else:
                    ok("M2", "semua status kembali seperti sebelum impor")
                keep_ok = [x for x in leftover
                           if x[0] in [t[0] for t in terminal]
                           and x[1] in ("cancelled_at", "cancel_reason", "refund_amount",
                                        "status_raw")]
                stray = [x for x in leftover if x not in keep_ok]
                if stray:
                    bad("M3", f"kolom dari berkas masih tertinggal pada pesanan NON-terminal: "
                              f"{stray[:6]}")
                else:
                    ok("M3", "kolom dari berkas dibersihkan (kecuali penjelas status terminal)")
                pend = DB.marketing_data_import_undo.count_documents(
                    {"session_id": sid_l, "restored_at": None})
                (ok if pend == 0 else bad)("M4", f"jejak UNDO menggantung = {pend}")

head("K — bersih-bersih")
for sid in made:
    s = DB.marketing_data_import_sessions.find_one({"id": sid}, {"_id": 0, "status": 1})
    if s and s.get("status") == "committed":
        api("POST", f"/api/marketing/data-import/sessions/{sid}/rollback")
    DB.marketing_data_import_sessions.delete_one({"id": sid})
    DB.marketing_data_import_undo.delete_many({"session_id": sid})
left = DB.marketing_orders.count_documents({"_import_session_id": {"$in": made}})
(ok if left == 0 else bad)("K1", f"sisa pesanan artefak = {left}")

print("\n" + "=" * 78)
print(f"HASIL: {len(OK)} OK · {len(FIND)} TEMUAN")
for c, m in FIND:
    print(f"  TEMUAN {c}: {m}")
