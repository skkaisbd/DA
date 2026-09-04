#!/usr/bin/env python3
"""Seed IDEMPOTEN — data demo RANTAI PERSETUJUAN PEMBELIAN (Portal Pengadaan).

MENGAPA BERKAS INI ADA
----------------------
Pada environment yang lahir dari `scripts/bootstrap.sh` yang segar:

    dewi_procurement_requests = 0        acc_purchase_requests = 0

Akibatnya TIGA layar inti Portal Pengadaan tampak **rusak padahal hanya kosong**:

  · **Permintaan Pengadaan** — ketiga tab ("Semua Permintaan", "Menunggu
    Persetujuan Saya", "Permintaan Saya") kosong, sehingga rantai persetujuan
    yang sudah dibangun (dept → keuangan → final) TIDAK BISA dilihat maupun
    diuji lewat layar sama sekali;
  · **Request Pembelian Aksesoris** — tabel kosong;
  · **Dashboard Pengadaan** — semua kartu KPI 0.

Ini kelas bug yang SUDAH DUA KALI menipu sesi sebelumnya:
`seed_procurement_suppliers_demo.py` lahir karena `rahaza_suppliers` = 0 membuat
Portal Pengadaan tampak kosong, dan `seed_acc_valuation_baseline.py` lahir karena
baseline yang tidak diseed menghasilkan 8 FAIL PALSU. Sesi 2026-08-07 mengkurasi
data demo persetujuan **dengan panggilan manual** sehingga hilang begitu database
dibangun ulang — berkas ini menutup lubang itu untuk selamanya.

CARA KERJANYA — LEWAT API, BUKAN TULIS LANGSUNG KE MONGO
--------------------------------------------------------
Setiap permintaan dibuat & disetujui lewat **endpoint sungguhan**
(`/submit`, `/approve`, `/create-po`). Konsekuensinya penting: `approval_steps`,
`approval_chain`, notifikasi bel, dan nomor dokumen semuanya LAHIR DARI MESIN
YANG SAMA yang dipakai pengguna. Jadi data demo ini tidak bisa "berbohong" —
kalau aturan persetujuan rusak, skrip ini GAGAL, bukan menghasilkan data palsu
yang menyembunyikan kerusakan.

SIFAT
-----
  · **IDEMPOTEN** — dikenali dari judul/keperluan yang sudah ada; dijalankan
    berkali-kali tidak menggandakan data.
  · **TIDAK menyentuh uang/stok** — hanya permintaan + persetujuan + satu PO
    berstatus draft. Tidak ada penerimaan barang, jurnal GL, atau mutasi stok,
    jadi baseline `verify_data_integrity` & valuasi aksesoris tidak berubah.
  · **BISA DIBERSIHKAN** — `--cleanup` membuang data demo ini (ditandai
    `source: "seed_demo_approval"`) tanpa menyentuh data pengguna sungguhan.

CERITA DATA YANG DIBUAT (menampilkan SETIAP tahap rantai sekaligus)
-------------------------------------------------------------------
  Permintaan Pengadaan
    1. Rp 6.000.000   → 2 tahap, MENUNGGU TAHAP DEPARTEMEN   (giliran gudang@)
    2. Rp 50.000.000  → 3 tahap, MENUNGGU TAHAP KEUANGAN     (giliran finance@)
    3. Rp 50.000.000  → 3 tahap, DISETUJUI PENUH             (siap dijadikan PO)
    4. Rp 800.000     → 1 tahap, SUDAH JADI PURCHASE ORDER   (PO menunggu
                        persetujuan pengadaan → contoh PO di kotak persetujuan)
  Request Pembelian Aksesoris
    5. Rp 30.000.000  → 3 tahap, MENUNGGU TAHAP DEPARTEMEN   (giliran gudang@)
    6. Rp 400.000     → 1 tahap, MENUNGGU TAHAP DEPARTEMEN   (giliran gudang@)

Semua dibuat oleh `packing@dewiaditya.id` (role `tim_packing`, departemen
Gudang) — akun yang **tidak berhak menyetujui apa pun**, sehingga larangan
"pembuat tidak boleh menyetujui permintaannya sendiri" ikut terlihat di layar.

PAKAI
-----
    python3 /app/scripts/seed_approval_demo.py
    python3 /app/scripts/seed_approval_demo.py --cleanup
    python3 /app/scripts/seed_approval_demo.py --print    # hanya tampilkan kondisi
"""
from __future__ import annotations

import os
import sys

import requests

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
CLEANUP = "--cleanup" in sys.argv
PRINT_ONLY = "--print" in sys.argv

G, R, Y, C, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[0m"

# Penanda supaya data demo bisa dibersihkan tanpa menyentuh data sungguhan.
MARK = "seed_demo_approval"

REQUESTER = ("packing@dewiaditya.id", "Dewi@123")   # tim_packing · dept Gudang
DEPT_APPROVER = ("gudang@dewiaditya.id", "Dewi@123")  # admin_gudang · dept Gudang
FIN_APPROVER = ("finance@dewiaditya.id", "Dewi@123")  # accounting
FINAL_APPROVER = ("direktur@dewiaditya.id", "Dewi@123")  # director
ADMIN = ("admin@garment.com", "Admin@123")

_tokens: dict = {}


def ok(m):
    print(f"  {G}✓{X} {m}")


def warn(m):
    print(f"  {Y}!{X} {m}")


def bad(m):
    print(f"  {R}✗{X} {m}")


def login(email: str, pw: str) -> str:
    """Login sekali per akun. Backend membatasi 10 login / 60 detik per IP, jadi
    token WAJIB dipakai ulang — dulu ini sumber kegagalan skrip yang panjang."""
    if email in _tokens:
        return _tokens[email]
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"{R}Login {email} gagal HTTP {r.status_code}: "
                         f"{r.text[:200]}{X}")
    tok = r.json().get("token", "")
    if not tok:
        raise SystemExit(f"{R}Login {email} tidak mengembalikan token{X}")
    _tokens[email] = tok
    return tok


def H(acct) -> dict:
    return {"Authorization": f"Bearer {login(*acct)}"}


def api(method: str, path: str, acct, **kw):
    return requests.request(method, f"{BASE}{path}", headers=H(acct), timeout=60, **kw)


def must(r, what: str, expect=(200, 201)):
    if r.status_code not in expect:
        raise SystemExit(f"{R}{what} GAGAL HTTP {r.status_code}: {r.text[:300]}{X}")
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {}


# ── master data yang dibutuhkan ─────────────────────────────────────────────
def material_map() -> dict:
    rows = must(api("GET", "/api/rahaza/materials?limit=100", ADMIN), "ambil master material")
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("data") or []
    return {r.get("code"): r for r in rows if r.get("code")}


def first_supplier_id():
    rows = must(api("GET", "/api/procurement/suppliers?limit=5", ADMIN), "ambil master supplier")
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("data") or rows.get("suppliers") or []
    return (rows[0].get("id") if rows else None), (rows[0].get("name") if rows else "")


# ── Permintaan Pengadaan (dewi_procurement_requests) ────────────────────────
def existing_pr_titles() -> dict:
    rows = must(api("GET", "/api/procurement/requests?limit=100", ADMIN), "ambil daftar PR")
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("data") or rows.get("requests") or []
    return {(r.get("title") or "").strip(): r for r in rows}


def make_pr(title: str, desc: str, items: list, *, department="Gudang",
            priority="medium", request_type="asset") -> dict:
    body = {
        "title": title,
        "description": f"{desc} [{MARK}]",
        "justification": desc,
        "department": department,
        "priority": priority,
        "request_type": request_type,
        "items": items,
    }
    return must(api("POST", "/api/procurement/requests", REQUESTER, json=body),
                f"buat PR '{title}'")


def submit_pr(pr_id: str, title: str) -> dict:
    return must(api("POST", f"/api/procurement/requests/{pr_id}/submit", REQUESTER, json={}),
                f"submit PR '{title}'")


def approve_pr(pr_id: str, acct, comment: str, title: str) -> dict:
    return must(api("POST", f"/api/procurement/requests/{pr_id}/approve", acct,
                    json={"comment": comment}), f"approve PR '{title}' oleh {acct[0]}")


# ── Request Pembelian Aksesoris (acc_purchase_requests) ─────────────────────
def existing_acc_purposes() -> dict:
    rows = must(api("GET", "/api/acc/purchase-requests", ADMIN), "ambil daftar PR aksesoris")
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("data") or []
    return {(r.get("purpose") or "").strip(): r for r in rows}


def make_acc_pr(purpose: str, items: list, *, department="Gudang",
                priority="Normal", supplier="") -> dict:
    body = {
        "purpose": purpose,
        "priority": priority,
        "supplier": supplier,
        "department": department,
        "notes": f"Data demo rantai persetujuan [{MARK}]",
        "items": items,
    }
    return must(api("POST", "/api/acc/purchase-requests", REQUESTER, json=body),
                f"buat PR aksesoris '{purpose}'")


def submit_acc(pr_id: str, purpose: str) -> dict:
    return must(api("POST", f"/api/acc/purchase-requests/{pr_id}/submit", REQUESTER, json={}),
                f"submit PR aksesoris '{purpose}'")


def approve_acc(pr_id: str, acct, comment: str, purpose: str) -> dict:
    return must(api("POST", f"/api/acc/purchase-requests/{pr_id}/approve", acct,
                    json={"comment": comment}),
                f"approve PR aksesoris '{purpose}' oleh {acct[0]}")


# ── SKENARIO ────────────────────────────────────────────────────────────────
def build(mats: dict):
    have_pr = existing_pr_titles()
    have_acc = existing_acc_purposes()
    created = []

    def mat(code):
        m = mats.get(code)
        if not m:
            raise SystemExit(f"{R}Material {code} tidak ada di master — "
                             f"jalankan bootstrap/seed master dulu.{X}")
        return m

    # ── 1. PR Rp 6.000.000 → 2 tahap, menunggu TAHAP DEPARTEMEN ─────────────
    t1 = "Rak besi gudang aksesoris 5 tingkat"
    if t1 in have_pr:
        ok(f"PR '{t1}' sudah ada — dilewati")
    else:
        pr = make_pr(t1, "Aksesoris menumpuk di lantai karena rak lama penuh; "
                         "risiko barang tertukar antar order.",
                     [{"name": "Rak besi 5 tingkat 200x100cm", "uom": "pcs",
                       "qty": 4, "estimated_price": 1_500_000}])
        r = submit_pr(pr["id"], t1)
        ok(f"{pr['request_number']} Rp 6.000.000 → {len(r.get('approval_chain', []))} tahap, "
           f"menunggu {r.get('stage_label') or r.get('stage')}")
        created.append(pr["request_number"])

    # ── 2. PR Rp 50.000.000 → 3 tahap, menunggu TAHAP KEUANGAN ──────────────
    t2 = "Mesin jahit industri tambahan"
    if t2 in have_pr:
        ok(f"PR '{t2}' sudah ada — dilewati")
    else:
        pr = make_pr(t2, "Kapasitas jahit tidak cukup untuk order ekspor kuartal ini.",
                     [{"name": "Mesin jahit jarum 1 high speed", "uom": "pcs",
                       "qty": 10, "estimated_price": 5_000_000}], priority="high")
        submit_pr(pr["id"], t2)
        r = approve_pr(pr["id"], DEPT_APPROVER,
                       "Setuju, kapasitas jahit memang kurang.", t2)
        ok(f"{pr['request_number']} Rp 50.000.000 → tahap departemen disetujui, "
           f"sekarang menunggu {r.get('next_stage_label') or r.get('next_stage')}")
        created.append(pr["request_number"])

    # ── 3. PR Rp 50.000.000 → 3 tahap, DISETUJUI PENUH (siap jadi PO) ───────
    t3 = "Meja potong kain 3 x 1,5 meter"
    if t3 in have_pr:
        ok(f"PR '{t3}' sudah ada — dilewati")
    else:
        pr = make_pr(t3, "Meja potong lama melengkung sehingga hasil potong tidak presisi.",
                     [{"name": "Meja potong kain 300x150cm rangka besi", "uom": "pcs",
                       "qty": 5, "estimated_price": 10_000_000}])
        submit_pr(pr["id"], t3)
        approve_pr(pr["id"], DEPT_APPROVER, "Setuju, meja lama sudah tidak layak.", t3)
        approve_pr(pr["id"], FIN_APPROVER, "Anggaran belanja modal masih tersedia.", t3)
        r = approve_pr(pr["id"], FINAL_APPROVER, "Disetujui, lanjutkan pengadaan.", t3)
        ok(f"{pr['request_number']} Rp 50.000.000 → status "
           f"{r.get('new_status')} (3 tahap selesai, siap dijadikan PO)")
        created.append(pr["request_number"])

    # ── 4. PR Rp 800.000 → 1 tahap, SUDAH JADI PURCHASE ORDER ───────────────
    t4 = "Trolley barang kapasitas 300 kg"
    if t4 in have_pr:
        ok(f"PR '{t4}' sudah ada — dilewati")
    else:
        pr = make_pr(t4, "Pemindahan bal kain masih diangkat manual, berisiko cedera.",
                     [{"name": "Trolley besi 300 kg roda karet", "uom": "pcs",
                       "qty": 2, "estimated_price": 400_000}], request_type="asset")
        submit_pr(pr["id"], t4)
        approve_pr(pr["id"], DEPT_APPROVER, "Setuju, kebutuhan mendasar gudang.", t4)
        sup_id, sup_name = first_supplier_id()
        if not sup_id:
            warn("Master supplier kosong — PR ini dibiarkan 'approved' tanpa PO. "
                 "Jalankan scripts/seed_procurement_suppliers_demo.py lebih dulu.")
        else:
            po = must(api("POST", f"/api/procurement/requests/{pr['id']}/create-po", ADMIN,
                          json={"supplier_id": sup_id,
                                "notes": f"PO dari PR demo [{MARK}]"}),
                      f"buat PO dari PR '{t4}'")
            po_id = po.get("id")
            po_no = po.get("po_number") or "?"
            # 2026-08-07 — PO sekarang punya rantai persetujuannya sendiri.
            # Diajukan lalu DIBIARKAN MENUNGGU supaya owner melihat contoh
            # "Purchase Order menunggu persetujuan" di kotak persetujuan
            # gabungan (dulu PO tidak pernah muncul di sana sama sekali).
            r = must(api("POST", f"/api/rahaza/purchase-orders/{po_id}/submit", ADMIN, json={}),
                     f"ajukan PO {po_no}")
            ok(f"{pr['request_number']} Rp 800.000 → PO {po_no} ({sup_name}) "
               f"— diajukan, menunggu {r.get('stage_label') or 'persetujuan'}")
        created.append(pr["request_number"])

    # ── 5. PR Aksesoris Rp 30.000.000 → 3 tahap, menunggu DEPARTEMEN ────────
    p5 = "Kancing plastik habis untuk order WO-2026-08"
    if p5 in have_acc:
        ok(f"PR aksesoris '{p5}' sudah ada — dilewati")
    else:
        m = mat("ACC-BTN-12")
        acc = make_acc_pr(p5, [{"acc_id": m["id"], "acc_code": m["code"],
                                "acc_name": m["name"], "qty_requested": 60_000,
                                "estimated_price": 500, "input_unit": "base",
                                "unit": m.get("unit", "pcs")}],
                          priority="Urgent", supplier="PT Benang Jaya Abadi")
        r = submit_acc(acc["id"], p5)
        ok(f"{acc['pr_number']} Rp 30.000.000 → {r.get('total_stages')} tahap, "
           f"menunggu {r.get('stage_label')}")
        created.append(acc["pr_number"])

    # ── 6. PR Aksesoris Rp 400.000 → 1 tahap, menunggu DEPARTEMEN ───────────
    p6 = "Label woven stok kritis"
    if p6 in have_acc:
        ok(f"PR aksesoris '{p6}' sudah ada — dilewati")
    else:
        m = mat("ACC-DA-LBL")
        acc = make_acc_pr(p6, [{"acc_id": m["id"], "acc_code": m["code"],
                                "acc_name": m["name"], "qty_requested": 2_000,
                                "estimated_price": 200, "input_unit": "base",
                                "unit": m.get("unit", "pcs")}])
        r = submit_acc(acc["id"], p6)
        ok(f"{acc['pr_number']} Rp 400.000 → {r.get('total_stages')} tahap, "
           f"menunggu {r.get('stage_label')}")
        created.append(acc["pr_number"])

    return created


# ── LAPORAN KONDISI ─────────────────────────────────────────────────────────
def report():
    print(f"\n{C}KONDISI SEKARANG{X}")
    for acct, label in ((DEPT_APPROVER, "gudang@ (tahap departemen)"),
                        (FIN_APPROVER, "finance@ (tahap keuangan)"),
                        (FINAL_APPROVER, "direktur@ (tahap final)"),
                        (ADMIN, "admin (boleh override semua tahap)")):
        try:
            inbox = must(api("GET", "/api/procurement/inbox", acct), "inbox")
            items = inbox if isinstance(inbox, list) else inbox.get("items", [])
            badge = must(api("GET", "/api/approval-inbox/badge", acct), "badge")
            kinds: dict = {}
            for i in items:
                kinds[i.get("kind_label") or i.get("kind") or "?"] = \
                    kinds.get(i.get("kind_label") or i.get("kind") or "?", 0) + 1
            detail = ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())) or "-"
            flag = "" if badge.get("pr_pending") == len(items) else \
                f"  {R}(lencana {badge.get('pr_pending')} ≠ inbox {len(items)}){X}"
            print(f"  {label:38s} kotak persetujuan = {len(items):2d}  ({detail}){flag}")
        except SystemExit as e:
            bad(f"{label}: {e}")
    ov = must(api("GET", "/api/procurement/overview", ADMIN), "overview")
    k = ov.get("kpi", {})
    print(f"\n  Dashboard Pengadaan → Permintaan: {k.get('pr_total')} "
          f"(menunggu {k.get('pr_pending')}, disetujui {k.get('pr_approved')})"
          f" · Request aksesoris: {k.get('accessory_pr_total')} "
          f"(menunggu persetujuan {k.get('accessory_pr_awaiting_approval')})")


# ── CLEANUP ─────────────────────────────────────────────────────────────────
async def cleanup():
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    dbname = os.environ.get("DB_NAME", "test_database")
    cli = AsyncIOMotorClient(mongo)
    db = cli[dbname]

    prs = await db.dewi_procurement_requests.find(
        {"description": {"$regex": MARK}}, {"_id": 0, "id": 1, "request_number": 1,
                                            "linked_po_id": 1}).to_list(500)
    pr_ids = [p["id"] for p in prs]
    po_ids = [p["linked_po_id"] for p in prs if p.get("linked_po_id")]
    accs = await db.acc_purchase_requests.find(
        {"notes": {"$regex": MARK}}, {"_id": 0, "id": 1, "pr_number": 1}).to_list(500)
    acc_ids = [a["id"] for a in accs]

    n_pr = (await db.dewi_procurement_requests.delete_many({"id": {"$in": pr_ids}})).deleted_count
    n_acc = (await db.acc_purchase_requests.delete_many({"id": {"$in": acc_ids}})).deleted_count
    n_po = (await db.rahaza_purchase_orders.delete_many(
        {"id": {"$in": po_ids}})).deleted_count if po_ids else 0
    n_notif = (await db.notifications.delete_many(
        {"source_id": {"$in": pr_ids + acc_ids}})).deleted_count
    # Pesan Communication Hub yang lahir dari PR demo.
    n_msg = (await db.comm_messages.delete_many(
        {"body": {"$regex": "|".join([p["request_number"] for p in prs]) or "___none___"}}
    )).deleted_count if prs else 0

    ok(f"dibuang: {n_pr} Permintaan Pengadaan · {n_acc} Request Aksesoris · "
       f"{n_po} Purchase Order · {n_notif} notifikasi · {n_msg} pesan hub")
    cli.close()


def main():
    print(f"{C}{'=' * 74}\n  SEED DEMO — RANTAI PERSETUJUAN PEMBELIAN (Portal Pengadaan)\n{'=' * 74}{X}")
    try:
        requests.get(f"{BASE}/api/health", timeout=10)
    except Exception:  # noqa: BLE001
        raise SystemExit(f"{R}Backend tidak bisa dihubungi di {BASE}{X}")

    if CLEANUP:
        import asyncio
        asyncio.run(cleanup())
        return 0
    if PRINT_ONLY:
        report()
        return 0

    mats = material_map()
    if not mats:
        raise SystemExit(f"{R}Master material kosong — jalankan bootstrap dulu.{X}")
    created = build(mats)
    print(f"\n  {'dibuat: ' + ', '.join(created) if created else 'tidak ada yang baru (idempoten)'}")
    report()
    print(f"\n{G}SELESAI.{X} Bersihkan dengan: python3 scripts/seed_approval_demo.py --cleanup\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
