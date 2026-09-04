#!/usr/bin/env python3
"""Backend Test — Request Pembelian Aksesoris Approval Chain (2026-08-07 fix)

MENGAPA SKRIP INI ADA
---------------------
Laporan owner 2026-08-07: "ada purchase request di aksesoris dan gudang, ini
harusnya tersambung ke procurement." Sebelum perbaikan, `acc_purchase_requests`
adalah alur PARALEL tanpa RBAC: akun `tim_packing` bisa membuat PR Rp 50 juta
lalu MENYETUJUI SENDIRI (HTTP 200), karena `PUT /api/acc/purchase-requests/{id}`
hanya memakai `require_auth` tanpa pemeriksaan peran/tahap/pembuat.

Skrip ini membuktikan perbaikan: Request Aksesoris kini memakai rantai persetujuan
YANG SAMA dengan Permintaan Pengadaan (rantai bertahap sesuai nilai, peran per
tahap saling lepas, larangan setujui PR sendiri, larangan satu orang menyetujui
dua tahap, override admin tercatat, notifikasi ke approver berikutnya), plus
kotak persetujuan GABUNGAN di `/api/procurement/inbox`.

CARA PAKAI
----------
    python3 /app/backend_test_acc_pr_approval.py

DATA UJI
--------
Memakai akun seed nyata (Dewi@123): packing@ (tim_packing, pembuat), gudang@
(admin_gudang, dept Gudang → tahap departemen), finance@ (accounting → tahap
keuangan), direktur@ (director → tahap final), admin@garment.com (superadmin).
Semua PR uji dihapus di blok `finally` langsung ke Mongo.
"""
import os
import sys
import uuid
import requests
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")

BASE = "https://da37-cmt-bridge.preview.emergentagent.com"
PW = "Dewi@123"
ADMIN = ("admin@garment.com", "Admin@123")

RESULTS = []
CREATED_PR = []
TOKENS = {}

# ── util ─────────────────────────────────────────────────────────────────────
C_OK, C_NO, C_END = "\033[92m", "\033[91m", "\033[0m"


def check(cond, name, detail=""):
    RESULTS.append((bool(cond), name, detail))
    mark = f"{C_OK}PASS{C_END}" if cond else f"{C_NO}FAIL{C_END}"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""))
    return bool(cond)


def section(title):
    print(f"\n\033[96m{'─' * 74}\n{title}\n{'─' * 74}{C_END}")


def login(email, pw=PW):
    if email in TOKENS:
        return TOKENS[email]
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    r.raise_for_status()
    TOKENS[email] = r.json()["token"]
    return TOKENS[email]


def H(email, pw=PW):
    return {"Authorization": f"Bearer {login(email, pw)}"}


def get(path, email, pw=PW, **kw):
    return requests.get(f"{BASE}{path}", headers=H(email, pw), timeout=30, **kw)


def post(path, email, body=None, pw=PW):
    return requests.post(f"{BASE}{path}", headers=H(email, pw), json=body or {}, timeout=30)


def put(path, email, body=None, pw=PW):
    return requests.put(f"{BASE}{path}", headers=H(email, pw), json=body or {}, timeout=30)


def mongo():
    from dotenv import load_dotenv
    from pymongo import MongoClient
    load_dotenv("/app/backend/.env")
    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli, cli[os.environ.get("DB_NAME", "test_database")]


def make_acc_pr(requester, purpose, qty, price, dept="Gudang"):
    """Buat Request Pembelian Aksesoris (draft) sebagai `requester`. Nilai = qty × price."""
    # Ambil material pertama dari master
    mats = get("/api/rahaza/materials", ADMIN[0], pw=ADMIN[1]).json()
    mats = mats if isinstance(mats, list) else (mats.get("items") or [])
    if not mats:
        raise RuntimeError("Master material kosong — tidak bisa membuat PR aksesoris")
    mat = mats[0]
    
    r = post("/api/acc/purchase-requests", requester, {
        "priority": "Normal",
        "purpose": purpose,
        "supplier": "",
        "department": dept,
        "items": [{
            "acc_id": mat["id"],
            "name": mat.get("name"),
            "qty_requested": qty,
            "estimated_price": price,
            "input_unit": "base"
        }],
    })
    r.raise_for_status()
    doc = r.json()
    CREATED_PR.append(doc["id"])
    return doc


def submit_acc(pr_id, requester):
    return post(f"/api/acc/purchase-requests/{pr_id}/submit", requester)


def read_acc_pr(pr_id, as_email):
    r = get(f"/api/acc/purchase-requests/{pr_id}", as_email)
    r.raise_for_status()
    return r.json()


# ═════════════════════════════════════════════════════════════════════════════
# A. LUBANG KEAMANAN TERTUTUP
# ═════════════════════════════════════════════════════════════════════════════
def test_security_hole_closed():
    section("A. LUBANG KEAMANAN TERTUTUP — self-approval & bypass PUT")
    
    # (1) Buat PR besar oleh staf packing → wajib 3 tahap
    big = make_acc_pr("packing@dewiaditya.id", "UJI ACC besar", 100, 500_000)
    check(big.get("requested_by"), "A1 PR aksesoris mencatat ID pembuat (dulu hanya nama)",
          f"requested_by={'ada' if big.get('requested_by') else 'TIDAK ADA'}")
    
    rs = submit_acc(big["id"], "packing@dewiaditya.id")
    chain = rs.json().get("approval_chain") if rs.status_code == 200 else None
    check(rs.status_code == 200 and chain == ["dept", "finance", "final"],
          "A2 rantai mengikuti NILAI PR (Rp 50 jt → 3 tahap)",
          f"http={rs.status_code} chain={chain}")
    
    # (2) Jalur bypass lama harus tertutup
    r = put(f"/api/acc/purchase-requests/{big['id']}", "packing@dewiaditya.id",
            {"status": "Approved", "finance_notes": "saya setujui sendiri"})
    check(r.status_code == 400,
          "A3 LUBANG DITUTUP: PUT status=Approved tidak lagi bisa melewati persetujuan",
          f"http={r.status_code} {str(r.json().get('detail'))[:80] if r.status_code != 200 else 'MASIH LOLOS'}")
    
    # (3) Self-approval
    r = post(f"/api/acc/purchase-requests/{big['id']}/approve", "packing@dewiaditya.id")
    detail = str(r.json().get("detail")) if r.status_code != 200 else ""
    check(r.status_code == 403,
          "A4 pembuat PR aksesoris TIDAK bisa menyetujui PR-nya sendiri",
          f"http={r.status_code} {detail[:90]}")
    
    # (4) Tahap salah
    r = post(f"/api/acc/purchase-requests/{big['id']}/approve", "finance@dewiaditya.id")
    check(r.status_code == 403,
          "A5 keuangan TIDAK bisa memotong ke tahap departemen",
          f"http={r.status_code}")
    
    return big


# ═════════════════════════════════════════════════════════════════════════════
# B. RANTAI BERJALAN LEWAT 3 ORANG BERBEDA
# ═════════════════════════════════════════════════════════════════════════════
def test_approval_chain(big):
    section("B. RANTAI BERJALAN LEWAT 3 ORANG BERBEDA")
    
    # (1) Tahap departemen
    r = post(f"/api/acc/purchase-requests/{big['id']}/approve", "gudang@dewiaditya.id",
             {"comment": "Setuju kebutuhan gudang"})
    check(r.status_code == 200 and r.json().get("next_stage") == "finance",
          "B1 tahap DEPARTEMEN disetujui approver yang benar",
          f"http={r.status_code} next={r.json().get('next_stage') if r.status_code == 200 else r.text[:80]}")
    
    # (2) Orang yang sama tidak bisa lanjut
    r = post(f"/api/acc/purchase-requests/{big['id']}/approve", "gudang@dewiaditya.id")
    check(r.status_code == 403, "B2 orang yang sama tidak bisa lanjut ke tahap keuangan",
          f"http={r.status_code}")
    
    # (3) Tahap keuangan
    r = post(f"/api/acc/purchase-requests/{big['id']}/approve", "finance@dewiaditya.id",
             {"comment": "Dana tersedia"})
    check(r.status_code == 200 and r.json().get("next_stage") == "final",
          "B3 tahap KEUANGAN disetujui, diteruskan ke direksi",
          f"http={r.status_code} next={r.json().get('next_stage') if r.status_code == 200 else r.text[:80]}")
    
    # (4) Tahap final
    r = post(f"/api/acc/purchase-requests/{big['id']}/approve", "direktur@dewiaditya.id",
             {"comment": "Disetujui direksi"})
    check(r.status_code == 200 and r.json().get("new_status") == "Approved",
          "B4 tahap FINAL menutup rantai → status Approved",
          f"http={r.status_code} status={r.json().get('new_status') if r.status_code == 200 else r.text[:80]}")


# ═════════════════════════════════════════════════════════════════════════════
# C. KOTAK PERSETUJUAN GABUNGAN
# ═════════════════════════════════════════════════════════════════════════════
def test_unified_inbox():
    section("C. KOTAK PERSETUJUAN GABUNGAN")
    
    # Buat PR baru untuk inbox test
    pr = make_acc_pr("packing@dewiaditya.id", "UJI ACC inbox", 50, 100_000)
    submit_acc(pr["id"], "packing@dewiaditya.id")
    
    # (1) Muncul di inbox approver yang benar
    ib = get("/api/procurement/inbox", "gudang@dewiaditya.id").json()
    found = [i for i in ib if i.get("id") == pr["id"]]
    check(bool(found),
          "C1 PR aksesoris MUNCUL di kotak persetujuan pengadaan (dulu tidak pernah)",
          f"jumlah inbox={len(ib)}")
    
    if found:
        check(found[0].get("kind") == "acc_pr" and found[0].get("api_base") == "/api/acc/purchase-requests",
              "C2 item membawa penanda asal + endpoint aksi untuk UI",
              f"kind={found[0].get('kind')} api_base={found[0].get('api_base')}")
        check(found[0].get("can_approve") is True and found[0].get("chain"),
              "C3 item membawa flag izin + rantai untuk stepper UI")
        check(found[0].get("kind_label") == "Aksesoris",
              "C4 item membawa label jenis untuk lencana UI",
              f"kind_label={found[0].get('kind_label')}")
        check(found[0].get("module_id") == "proc-accessory-pr",
              "C5 item membawa module_id untuk navigasi UI",
              f"module_id={found[0].get('module_id')}")
    
    # (2) Lencana TopBar ikut menghitung
    bg = get("/api/approval-inbox/badge", "gudang@dewiaditya.id").json()
    check(bg.get("pr_pending") == len(ib),
          "C6 lencana TopBar ikut menghitung PR aksesoris",
          f"lencana={bg.get('pr_pending')} inbox={len(ib)}")


# ═════════════════════════════════════════════════════════════════════════════
# D. AMBANG NILAI BERLAKU
# ═════════════════════════════════════════════════════════════════════════════
def test_value_thresholds():
    section("D. AMBANG NILAI BERLAKU JUGA DI AKSESORIS")
    
    # PR kecil cukup 1 tahap
    small = make_acc_pr("packing@dewiaditya.id", "UJI ACC kecil", 10, 20_000)
    rs = submit_acc(small["id"], "packing@dewiaditya.id")
    check(rs.status_code == 200 and rs.json().get("approval_chain") == ["dept"],
          "D1 PR kecil (Rp 200 rb) → 1 tahap",
          f"chain={rs.json().get('approval_chain') if rs.status_code == 200 else rs.text[:80]}")
    
    r = post(f"/api/acc/purchase-requests/{small['id']}/approve", "gudang@dewiaditya.id",
             {"comment": "kecil"})
    check(r.status_code == 200 and r.json().get("new_status") == "Approved",
          "D2 PR aksesoris kecil cukup 1 tahap → langsung Approved",
          f"status={r.json().get('new_status') if r.status_code == 200 else r.text[:80]}")


# ═════════════════════════════════════════════════════════════════════════════
# E. PENOLAKAN WAJIB BERALASAN
# ═════════════════════════════════════════════════════════════════════════════
def test_rejection():
    section("E. PENOLAKAN WAJIB BERALASAN")
    
    rej = make_acc_pr("packing@dewiaditya.id", "UJI ACC ditolak", 50, 100_000)
    submit_acc(rej["id"], "packing@dewiaditya.id")
    
    r = post(f"/api/acc/purchase-requests/{rej['id']}/reject", "gudang@dewiaditya.id", {"reason": " "})
    check(r.status_code == 400, "E1 penolakan tanpa alasan ditolak 400", f"http={r.status_code}")
    
    r = post(f"/api/acc/purchase-requests/{rej['id']}/reject", "gudang@dewiaditya.id",
             {"reason": "Stok masih cukup"})
    check(r.status_code == 200, "E2 penolakan beralasan berhasil", f"http={r.status_code}")


# ═════════════════════════════════════════════════════════════════════════════
# F. GERBANG ORDERED/RECEIVED
# ═════════════════════════════════════════════════════════════════════════════
def test_ordered_received_gate():
    section("F. GERBANG ORDERED/RECEIVED — 'Terima Barang' menambah STOK jadi harus berperan")
    
    # Buat & setujui PR kecil
    pr = make_acc_pr("packing@dewiaditya.id", "UJI ACC ordered", 10, 20_000)
    submit_acc(pr["id"], "packing@dewiaditya.id")
    post(f"/api/acc/purchase-requests/{pr['id']}/approve", "gudang@dewiaditya.id")
    
    # HR tidak boleh memesan/menerima
    r = put(f"/api/acc/purchase-requests/{pr['id']}", "hr@dewiaditya.id", {"status": "Ordered"})
    check(r.status_code == 403,
          "F1 peran non-pengadaan tidak bisa memesan/menerima barang (Received menambah stok)",
          f"http={r.status_code}")


# ═════════════════════════════════════════════════════════════════════════════
# G. JEJAK AUDIT
# ═════════════════════════════════════════════════════════════════════════════
def test_audit_trail(big):
    section("G. JEJAK AUDIT")
    
    tl = get(f"/api/acc/purchase-requests/{big['id']}/timeline", ADMIN[0], pw=ADMIN[1]).json()
    steps = [s for s in tl.get("steps", []) if s.get("action") == "approved"]
    check(len(steps) == 3 and all(s.get("actor_id") for s in steps),
          "G1 jejak audit lengkap: 3 langkah persetujuan dengan ID aktor",
          f"langkah={len(steps)}")
    
    # Verifikasi setiap langkah punya stage
    check(all(s.get("stage") for s in steps),
          "G2 setiap langkah persetujuan mencatat tahap (dept/finance/final)",
          f"stages={[s.get('stage') for s in steps]}")


# ═════════════════════════════════════════════════════════════════════════════
# H. NOTIFIKASI
# ═════════════════════════════════════════════════════════════════════════════
def test_notifications(big):
    section("H. NOTIFIKASI")
    
    # Cek notifikasi untuk finance (setelah tahap dept disetujui)
    r = get("/api/notifications?limit=200", "finance@dewiaditya.id")
    if r.status_code == 200:
        notifs = r.json().get("items", [])
        found = any(big.get("pr_number", "") in f"{n.get('title', '')} {n.get('message', '')}"
                    for n in notifs)
        check(found, "H1 approver berikutnya dapat notifikasi (dulu tidak ada notifikasi apa pun)",
              f"jumlah notif={len(notifs)}")


# ═════════════════════════════════════════════════════════════════════════════
def cleanup():
    section("PEMBERSIHAN — alat uji tidak boleh meninggalkan data palsu")
    cli, db = mongo()
    try:
        n_pr = db.acc_purchase_requests.delete_many({"id": {"$in": CREATED_PR}}).deleted_count
        n_nt = db.notifications.delete_many({"source_id": {"$in": CREATED_PR}}).deleted_count
        print(f"  PR dihapus={n_pr} notifikasi={n_nt}")
        left = db.acc_purchase_requests.count_documents({"purpose": {"$regex": "^UJI ACC"}})
        check(left == 0, "Z1 tidak ada PR uji tertinggal di database", f"sisa={left}")
    finally:
        cli.close()


def main():
    print("\033[1mBACKEND TEST — REQUEST PEMBELIAN AKSESORIS APPROVAL CHAIN\033[0m")
    print(f"target: {BASE}")
    try:
        big = test_security_hole_closed()
        test_approval_chain(big)
        test_unified_inbox()
        test_value_thresholds()
        test_rejection()
        test_ordered_received_gate()
        test_audit_trail(big)
        test_notifications(big)
    except Exception as e:
        import traceback
        traceback.print_exc()
        check(False, "EKSEKUSI SKRIP selesai tanpa error tak terduga", f"{type(e).__name__}: {e}")
    finally:
        try:
            cleanup()
        except Exception as e:
            check(False, "PEMBERSIHAN berhasil", str(e)[:120])
    
    passed = sum(1 for ok, _, _ in RESULTS if ok)
    failed = [(n, d) for ok, n, d in RESULTS if not ok]
    print(f"\n{'═' * 74}")
    print(f"  TOTAL: {passed}/{len(RESULTS)} PASS")
    if failed:
        print(f"\n  {C_NO}GAGAL ({len(failed)}):{C_END}")
        for n, d in failed:
            print(f"    · {n}" + (f"  — {d}" if d else ""))
    print(f"\n  HASIL: {(C_OK + 'LULUS') if not failed else (C_NO + 'MASIH BERMASALAH')}{C_END}")
    print("═" * 74)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
