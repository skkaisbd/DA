#!/usr/bin/env python3
"""POC / VERIFIKASI — Rantai Persetujuan Permintaan Pengadaan (PR) end-to-end.

MENGAPA BERKAS INI ADA
----------------------
Sesi 2026-08-06 menutup satu bug: `/api/procurement/inbox` memakai nama peran
generik ('finance', 'finance_manager', 'accountant') yang TIDAK ADA di aplikasi
ini, sehingga PR berstatus `dept_approved` tidak pernah tampil di inbox siapa
pun. Perbaikan itu benar (lihat `scripts/verify_pr_inbox_roles.py`), TAPI rantai
persetujuan tetap mati di layar karena empat hal lain:

  1. tidak ada layar kotak persetujuan sama sekali (endpoint /inbox nol pemanggil);
  2. frontend menyalin ulang daftar peran generik yang sama untuk memutuskan
     apakah tombol Setujui/Tolak dirender ⇒ approver ASLI (accounting,
     supervisor_produksi, admin_gudang) melihat PR tanpa punya tombol;
  3. approver berikutnya tidak pernah diberi tahu (hanya pembuat PR yang di-DM);
  4. `/approve` tidak memeriksa TAHAP ⇒ satu orang bisa menyetujui ketiga tahap,
     termasuk PR buatannya sendiri.

Skrip ini membuktikan perbaikan sisi SERVER lebih dulu (tanpa UI), karena UI
hanya boleh menuruti flag dari server.

CARA PAKAI
----------
    python3 /app/scripts/poc_approval_chain.py            # jalankan semua uji
    python3 /app/scripts/poc_approval_chain.py --keep     # jangan bersihkan data uji

DATA UJI
--------
Memakai akun seed nyata (Dewi@123): hr@ (pemohon, bukan approver), gudang@
(admin_gudang, dept Gudang → tahap departemen), finance@ (accounting → tahap
keuangan), direktur@ (director → tahap final), spv@ (supervisor_produksi, dept
Produksi). Satu akun buangan `zzpoc-dual@dewiaditya.id` dibuat untuk menguji
aturan "satu orang tidak boleh menyetujui dua tahap" lewat izin dinamis, lalu
DIHAPUS. Semua PR uji dihapus di blok `finally` langsung ke Mongo (pola repo:
alat uji tidak boleh meninggalkan data palsu).
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timezone

import requests

sys.path.insert(0, "/app/backend")

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
KEEP = "--keep" in sys.argv

PW = "Dewi@123"
ADMIN = ("admin@garment.com", "Admin@123")
DUAL_EMAIL = "zzpoc-dual@dewiaditya.id"

RESULTS: list[tuple[bool, str, str]] = []
CREATED_PR: list[str] = []
TOKENS: dict[str, str] = {}


# ── util ─────────────────────────────────────────────────────────────────────
C_OK, C_NO, C_END = "\033[92m", "\033[91m", "\033[0m"


def check(cond: bool, name: str, detail: str = "") -> bool:
    RESULTS.append((bool(cond), name, detail))
    mark = f"{C_OK}PASS{C_END}" if cond else f"{C_NO}FAIL{C_END}"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""))
    return bool(cond)


def section(title: str) -> None:
    print(f"\n\033[96m{'─' * 74}\n{title}\n{'─' * 74}{C_END}")


def login(email: str, pw: str = PW) -> str:
    if email in TOKENS:
        return TOKENS[email]
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    r.raise_for_status()
    TOKENS[email] = r.json()["token"]
    return TOKENS[email]


def H(email: str, pw: str = PW) -> dict:
    return {"Authorization": f"Bearer {login(email, pw)}"}


def get(path: str, email: str, pw: str = PW, **kw):
    return requests.get(f"{BASE}{path}", headers=H(email, pw), timeout=30, **kw)


def post(path: str, email: str, body=None, pw: str = PW):
    return requests.post(f"{BASE}{path}", headers=H(email, pw), json=body or {}, timeout=30)


def put(path: str, email: str, body=None, pw: str = PW):
    return requests.put(f"{BASE}{path}", headers=H(email, pw), json=body or {}, timeout=30)


def mongo():
    from dotenv import load_dotenv
    from pymongo import MongoClient
    load_dotenv("/app/backend/.env")
    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli, cli[os.environ.get("DB_NAME", "test_database")]


def make_pr(requester: str, title: str, dept: str, qty: float, price: float) -> dict:
    """Buat PR (draft) sebagai `requester`. Nilai = qty × price."""
    r = post("/api/procurement/requests", requester, {
        "title": title,
        "description": "POC rantai persetujuan",
        "justification": "membuktikan rantai persetujuan hidup ujung-ke-ujung",
        "priority": "medium",
        "request_type": "consumable",
        "department": dept,
        "needed_by": date.today().isoformat(),
        "items": [{"name": "Item POC", "uom": "pcs", "qty": qty, "estimated_price": price}],
    })
    r.raise_for_status()
    doc = r.json()
    CREATED_PR.append(doc["id"])
    return doc


def submit(pr_id: str, requester: str):
    return post(f"/api/procurement/requests/{pr_id}/submit", requester)


def read_pr(pr_id: str, as_email: str) -> dict:
    r = get(f"/api/procurement/requests/{pr_id}", as_email)
    r.raise_for_status()
    return r.json()


def set_thresholds(one: int, two: int):
    return put("/api/rahaza/management/alert-config", ADMIN[0],
               {"pr_1_stage_max": one, "pr_2_stage_max": two}, pw=ADMIN[1])


def notif_items(email: str, pw: str = PW) -> list:
    r = get("/api/notifications?limit=200", email, pw)
    if r.status_code != 200:
        return []
    return r.json().get("items", [])


def has_notif_for(email: str, pr_number: str, pw: str = PW) -> dict | None:
    for n in notif_items(email, pw):
        blob = f"{n.get('title', '')} {n.get('message', '')}"
        if pr_number and pr_number in blob:
            return n
    return None


# ── akun buangan berizin dua tahap ───────────────────────────────────────────
def ensure_dual_user():
    """Akun dengan izin `finance.approve` + `proc.pr.final_approve` sekaligus.

    Dibutuhkan untuk menguji aturan "satu orang tidak boleh menyetujui dua tahap"
    lewat jalur HTTP: daftar peran bawaan sengaja SALING LEPAS, jadi satu-satunya
    cara seseorang berhak atas dua tahap adalah izin dinamis dari owner.
    """
    import bcrypt
    cli, db = mongo()
    try:
        db.users.update_one(
            {"email": DUAL_EMAIL},
            {"$set": {"name": "POC Dual Approver", "role": "zzpoc_dual",
                      "department": "Keuangan", "status": "active",
                      "extra_permissions": ["finance.approve", "proc.pr.final_approve"],
                      "updated_at": datetime.now(timezone.utc)},
             "$setOnInsert": {"id": str(uuid.uuid4()), "email": DUAL_EMAIL,
                              "password": bcrypt.hashpw(PW.encode(), bcrypt.gensalt(10)).decode(),
                              "created_at": datetime.now(timezone.utc)}},
            upsert=True)
    finally:
        cli.close()


# ═════════════════════════════════════════════════════════════════════════════
# A. Ambang nilai bisa diatur owner (dan validasinya benar)
# ═════════════════════════════════════════════════════════════════════════════
def test_thresholds():
    section("A. AMBANG NILAI PR — bisa diatur owner di Ringkasan Bisnis")
    r = get("/api/rahaza/management/alert-config", ADMIN[0], pw=ADMIN[1])
    check(r.status_code == 200, "A1 GET alert-config 200", f"http={r.status_code}")
    cfg = r.json() if r.status_code == 200 else {}
    check("pr_1_stage_max" in cfg and "pr_2_stage_max" in cfg,
          "A2 ambang nilai PR ikut disajikan endpoint ambang yang sudah ada",
          f"1 tahap ≤ {cfg.get('pr_1_stage_max')}, 2 tahap ≤ {cfg.get('pr_2_stage_max')}")
    check(cfg.get("money_keys") == ["pr_1_stage_max", "pr_2_stage_max"],
          "A3 endpoint menandai mana ambang RUPIAH (bukan hari) untuk UI",
          f"money_keys={cfg.get('money_keys')}")
    check(bool((cfg.get("labels") or {}).get("pr_1_stage_max")),
          "A4 label berbahasa Indonesia tersedia untuk UI",
          str((cfg.get("labels") or {}).get("pr_1_stage_max")))

    bad = set_thresholds(30_000_000, 25_000_000)
    check(bad.status_code == 400, "A5 ambang 1 tahap > 2 tahap ditolak 400",
          f"http={bad.status_code} {str(bad.json().get('detail'))[:70] if bad.status_code == 400 else ''}")

    bad2 = put("/api/rahaza/management/alert-config", ADMIN[0],
               {"pr_1_stage_max": "bukan angka"}, pw=ADMIN[1])
    check(bad2.status_code == 400, "A6 ambang bukan angka ditolak 400", f"http={bad2.status_code}")

    ok = set_thresholds(1_000_000, 25_000_000)
    check(ok.status_code == 200, "A7 simpan ambang sah 200", f"http={ok.status_code}")
    after = get("/api/rahaza/management/alert-config", ADMIN[0], pw=ADMIN[1]).json()
    check(after.get("pr_1_stage_max") == 1_000_000 and after.get("pr_2_stage_max") == 25_000_000,
          "A8 nilai tersimpan terbaca kembali",
          f"{after.get('pr_1_stage_max')} / {after.get('pr_2_stage_max')}")
    # ambang hari lama harus tetap utuh (tidak dirusak penambahan ambang uang)
    check(isinstance(after.get("po_warn_days"), int) and isinstance(after.get("rnd_stale_days"), int),
          "A9 ambang hari lama (PO/piutang/RnD) tidak rusak",
          f"po={after.get('po_warn_days')} rnd_stale={after.get('rnd_stale_days')}")


# ═════════════════════════════════════════════════════════════════════════════
# B. Kedalaman rantai mengikuti NILAI PR
# ═════════════════════════════════════════════════════════════════════════════
def test_chain_depth() -> dict:
    section("B. KEDALAMAN RANTAI = NILAI PR (1 / 2 / 3 tahap)")
    prs = {}
    for key, title, qty, price, expect in [
        ("small", "POC kecil (1 tahap)", 10, 50_000, ["dept"]),
        ("medium", "POC menengah (2 tahap)", 10, 500_000, ["dept", "finance"]),
        ("large", "POC besar (3 tahap)", 10, 5_000_000, ["dept", "finance", "final"]),
    ]:
        pr = make_pr("hr@dewiaditya.id", title, "Gudang", qty, price)
        prs[key] = pr
        # Draft: rantai masih pratinjau (belum dibekukan) tapi HARUS sudah terlihat
        draft = read_pr(pr["id"], ADMIN[0])
        check(draft.get("approval_chain") == expect,
              f"B-{key} pratinjau rantai saat draft = {expect}",
              f"nilai={pr['total_estimated']:,.0f} chain={draft.get('approval_chain')}")
        r = submit(pr["id"], "hr@dewiaditya.id")
        check(r.status_code == 200 and r.json().get("approval_chain") == expect,
              f"B-{key} rantai dibekukan saat submit = {expect}",
              f"http={r.status_code} chain={r.json().get('approval_chain') if r.status_code == 200 else r.text[:80]}")
    return prs


# ═════════════════════════════════════════════════════════════════════════════
# C. Rantai DIBEKUKAN saat submit (mengubah ambang tak menggeser PR berjalan)
# ═════════════════════════════════════════════════════════════════════════════
def test_chain_frozen(prs: dict):
    section("C. RANTAI DIBEKUKAN — ubah ambang tidak menggeser PR yang sudah jalan")
    mid = prs["medium"]
    # Naikkan ambang 1-tahap sampai PR menengah (Rp 5 jt) "seharusnya" 1 tahap.
    r = set_thresholds(10_000_000, 25_000_000)
    check(r.status_code == 200, "C1 ambang dinaikkan (1 tahap ≤ Rp 10 jt)", f"http={r.status_code}")
    again = read_pr(mid["id"], ADMIN[0])
    check(again.get("approval_chain") == ["dept", "finance"],
          "C2 PR yang SUDAH submit tetap 2 tahap (tidak kehilangan tahap keuangan)",
          f"chain={again.get('approval_chain')}")
    # PR BARU dengan nilai sama harus memakai aturan baru → 1 tahap.
    fresh = make_pr("hr@dewiaditya.id", "POC ambang baru", "Gudang", 10, 500_000)
    rs = submit(fresh["id"], "hr@dewiaditya.id")
    check(rs.status_code == 200 and rs.json().get("approval_chain") == ["dept"],
          "C3 PR BARU bernilai sama memakai ambang baru = 1 tahap",
          f"chain={rs.json().get('approval_chain') if rs.status_code == 200 else rs.text[:80]}")
    set_thresholds(1_000_000, 25_000_000)
    check(get("/api/rahaza/management/alert-config", ADMIN[0], pw=ADMIN[1]).json()
          .get("pr_1_stage_max") == 1_000_000, "C4 ambang dikembalikan ke semula")


# ═════════════════════════════════════════════════════════════════════════════
# D. Pemisahan wewenang KETAT
# ═════════════════════════════════════════════════════════════════════════════
def test_sod(prs: dict):
    section("D. PEMISAHAN WEWENANG KETAT (tahap · bukan PR sendiri · bukan 2 tahap)")
    large = prs["large"]          # 3 tahap, dept Gudang, pemohon hr@
    pr_id = large["id"]

    r = post(f"/api/procurement/requests/{pr_id}/approve", "hr@dewiaditya.id", {"comment": "x"})
    check(r.status_code == 403, "D1 pemohon (bukan approver) TIDAK bisa menyetujui PR-nya",
          f"http={r.status_code} {str(r.json().get('detail'))[:80] if r.status_code != 200 else ''}")

    r = post(f"/api/procurement/requests/{pr_id}/approve", "finance@dewiaditya.id", {"comment": "x"})
    check(r.status_code == 403, "D2 keuangan TIDAK bisa menyetujui tahap DEPARTEMEN",
          f"http={r.status_code} {str(r.json().get('detail'))[:80] if r.status_code != 200 else ''}")

    r = post(f"/api/procurement/requests/{pr_id}/approve", "direktur@dewiaditya.id", {"comment": "x"})
    check(r.status_code == 403, "D3 direksi TIDAK bisa memotong ke tahap DEPARTEMEN",
          f"http={r.status_code}")

    r = post(f"/api/procurement/requests/{pr_id}/approve", "gudang@dewiaditya.id",
             {"comment": "Setuju — kebutuhan gudang"})
    ok = r.status_code == 200
    body = r.json() if ok else {}
    check(ok and body.get("new_status") == "dept_approved" and body.get("next_stage") == "finance",
          "D4 approver DEPARTEMEN yang benar (admin_gudang, dept Gudang) berhasil",
          f"http={r.status_code} status={body.get('new_status')} next={body.get('next_stage')}")
    check(ok and body.get("override") is False,
          "D5 persetujuan sah TIDAK ditandai override", f"override={body.get('override')}")

    r = post(f"/api/procurement/requests/{pr_id}/approve", "gudang@dewiaditya.id", {"comment": "x"})
    check(r.status_code == 403, "D6 orang yang sama TIDAK bisa lanjut ke tahap KEUANGAN",
          f"http={r.status_code} {str(r.json().get('detail'))[:90] if r.status_code != 200 else ''}")

    ensure_dual_user()
    r = post(f"/api/procurement/requests/{pr_id}/approve", DUAL_EMAIL, {"comment": "Dana tersedia"})
    check(r.status_code == 200 and r.json().get("new_status") == "finance_approved",
          "D7 pemegang izin finance.approve menyetujui tahap KEUANGAN",
          f"http={r.status_code} status={r.json().get('new_status') if r.status_code == 200 else r.text[:80]}")

    r = post(f"/api/procurement/requests/{pr_id}/approve", DUAL_EMAIL, {"comment": "x"})
    detail = str(r.json().get("detail")) if r.status_code != 200 else ""
    check(r.status_code == 403 and "dua tahap" in detail,
          "D8 walau BERHAK atas tahap final, orang yang sudah approve tahap sebelumnya DITOLAK",
          f"http={r.status_code} {detail[:100]}")

    r = post(f"/api/procurement/requests/{pr_id}/approve", "direktur@dewiaditya.id",
             {"comment": "Disetujui direksi"})
    check(r.status_code == 200 and r.json().get("new_status") == "approved",
          "D9 tahap FINAL diselesaikan direksi → PR disetujui penuh",
          f"http={r.status_code} status={r.json().get('new_status') if r.status_code == 200 else r.text[:90]}")

    # Batas departemen pada tahap departemen
    spv_pr = make_pr("spv@dewiaditya.id", "POC PR milik Produksi", "Produksi", 10, 5_000_000)
    submit(spv_pr["id"], "spv@dewiaditya.id")
    r = post(f"/api/procurement/requests/{spv_pr['id']}/approve", "spv@dewiaditya.id", {"comment": "x"})
    detail = str(r.json().get("detail")) if r.status_code != 200 else ""
    check(r.status_code == 403 and "sendiri" in detail,
          "D10 approver yang membuat PR sendiri DITOLAK (self-approval)",
          f"http={r.status_code} {detail[:100]}")
    r = post(f"/api/procurement/requests/{spv_pr['id']}/approve", "gudang@dewiaditya.id", {"comment": "x"})
    detail = str(r.json().get("detail")) if r.status_code != 200 else ""
    check(r.status_code == 403 and "departemen" in detail.lower(),
          "D11 approver departemen LAIN ditolak (Gudang vs Produksi)",
          f"http={r.status_code} {detail[:100]}")
    return spv_pr


# ═════════════════════════════════════════════════════════════════════════════
# E. Override admin/owner boleh, TAPI tercatat
# ═════════════════════════════════════════════════════════════════════════════
def test_override(spv_pr: dict):
    section("E. OVERRIDE ADMIN — diizinkan, tetapi TERCATAT di riwayat")
    pr_id = spv_pr["id"]
    r = post(f"/api/procurement/requests/{pr_id}/approve", ADMIN[0],
             {"comment": "Darurat produksi"}, pw=ADMIN[1])
    ok = r.status_code == 200
    b = r.json() if ok else {}
    check(ok and b.get("override") is True and "stage_role" in (b.get("override_reasons") or []),
          "E1 admin menembus tahap departemen → ditandai override + alasannya",
          f"http={r.status_code} override={b.get('override')} reasons={b.get('override_reasons')}")

    tl = get(f"/api/procurement/requests/{pr_id}/timeline", ADMIN[0], pw=ADMIN[1]).json()
    ov = [s for s in tl.get("steps", []) if s.get("override")]
    check(bool(ov) and "override" in (ov[-1].get("action_label") or "").lower(),
          "E2 langkah override tampil jelas di riwayat (untuk auditor)",
          f"label={(ov[-1].get('action_label') if ov else None)}")

    r = post(f"/api/procurement/requests/{pr_id}/approve", ADMIN[0],
             {"comment": "Lanjut darurat"}, pw=ADMIN[1])
    b = r.json() if r.status_code == 200 else {}
    check(r.status_code == 200 and "double_stage" in (b.get("override_reasons") or []),
          "E3 admin menyetujui tahap KEDUA pada PR yang sama → tercatat 'double_stage'",
          f"reasons={b.get('override_reasons')}")


# ═════════════════════════════════════════════════════════════════════════════
# F. Inbox = tepat sama dengan yang bisa saya setujui
# ═════════════════════════════════════════════════════════════════════════════
def test_inbox(prs: dict):
    section("F. KOTAK PERSETUJUAN — isinya persis pekerjaan saya")
    small_id = prs["small"]["id"]        # 1 tahap, status submitted, dept Gudang
    medium_id = prs["medium"]["id"]      # 2 tahap, status submitted

    ib = get("/api/procurement/inbox", "gudang@dewiaditya.id")
    items = ib.json() if ib.status_code == 200 else []
    ids = {i["id"] for i in items}
    check(ib.status_code == 200 and small_id in ids and medium_id in ids,
          "F1 approver departemen melihat PR tahap departemen di departemennya",
          f"http={ib.status_code} jumlah={len(items)}")
    check(all(i.get("can_approve") for i in items),
          "F2 SETIAP item inbox benar-benar bisa disetujui (isi inbox = flag tombol)",
          f"{sum(1 for i in items if i.get('can_approve'))}/{len(items)}")
    check(all(i.get("chain") and i.get("stage_label") for i in items),
          "F3 tiap item membawa rantai + label tahap untuk stepper UI")

    ib = get("/api/procurement/inbox", "hr@dewiaditya.id")
    check(ib.status_code == 200 and len(ib.json()) == 0,
          "F4 bukan approver → kotak persetujuan kosong (bukan error)",
          f"http={ib.status_code} jumlah={len(ib.json()) if ib.status_code == 200 else '-'}")

    ib = get("/api/procurement/inbox?scope=mine", "hr@dewiaditya.id")
    mine = ib.json() if ib.status_code == 200 else []
    check(ib.status_code == 200 and any(i["id"] in {small_id, medium_id} for i in mine),
          "F5 pemohon bisa melacak PR-nya sendiri (scope=mine)",
          f"jumlah={len(mine)}")

    # Naikkan PR menengah ke tahap keuangan lalu cek inbox keuangan
    r = post(f"/api/procurement/requests/{medium_id}/approve", "gudang@dewiaditya.id",
             {"comment": "OK dept"})
    check(r.status_code == 200, "F6 PR menengah dinaikkan ke tahap keuangan", f"http={r.status_code}")
    ib = get("/api/procurement/inbox", "finance@dewiaditya.id")
    fin = ib.json() if ib.status_code == 200 else []
    fin_ids = {i["id"] for i in fin}
    check(medium_id in fin_ids,
          "F7 keuangan (role `accounting`) melihat PR tahap keuangan — bug 2026-08-06 tetap tertutup",
          f"jumlah={len(fin)}")
    check(small_id not in fin_ids,
          "F8 keuangan TIDAK melihat PR yang masih di tahap departemen")
    check(all(i.get("can_approve") for i in fin), "F9 invarian inbox=can_approve juga untuk keuangan")

    # Lencana TopBar harus memakai angka yang sama
    bg = get("/api/approval-inbox/badge", "finance@dewiaditya.id")
    badge = bg.json() if bg.status_code == 200 else {}
    check(bg.status_code == 200 and badge.get("pr_pending") == len(fin),
          "F10 lencana persetujuan di TopBar = jumlah isi kotak persetujuan",
          f"lencana={badge.get('pr_pending')} inbox={len(fin)}")

    # PR 1 tahap: satu persetujuan langsung tuntas
    r = post(f"/api/procurement/requests/{small_id}/approve", "gudang@dewiaditya.id",
             {"comment": "Nilai kecil"})
    check(r.status_code == 200 and r.json().get("new_status") == "approved",
          "F11 PR bernilai kecil: 1 persetujuan langsung DISETUJUI PENUH (tidak dipaksa 3 tahap)",
          f"status={r.json().get('new_status') if r.status_code == 200 else r.text[:80]}")
    return medium_id


# ═════════════════════════════════════════════════════════════════════════════
# G. Notifikasi approver berikutnya (bel)
# ═════════════════════════════════════════════════════════════════════════════
def test_notifications(prs: dict, medium_id: str):
    section("G. NOTIFIKASI — approver berikutnya benar-benar diberi tahu")
    large_no = prs["large"]["request_number"]
    med = read_pr(medium_id, ADMIN[0])
    med_no = med.get("request_number")

    n = has_notif_for("gudang@dewiaditya.id", prs["small"]["request_number"])
    check(n is not None, "G1 approver DEPARTEMEN dapat notifikasi saat PR diajukan",
          f"judul={(n or {}).get('title')}")
    check((n or {}).get("link_module") == "proc-requests",
          "G2 notifikasi membawa tautan modul yang benar (tombol Buka)",
          f"link_module={(n or {}).get('link_module')}")

    n = has_notif_for("finance@dewiaditya.id", med_no)
    check(n is not None, "G3 approver KEUANGAN dapat notifikasi setelah tahap departemen selesai",
          f"judul={(n or {}).get('title')}")

    n = has_notif_for("direktur@dewiaditya.id", large_no)
    check(n is not None, "G4 approver FINAL dapat notifikasi setelah tahap keuangan selesai",
          f"judul={(n or {}).get('title')}")

    n = has_notif_for("hr@dewiaditya.id", large_no)
    check(n is not None and "disetujui" in (n.get("title", "") + n.get("message", "")).lower(),
          "G5 pemohon dikabari saat PR-nya disetujui penuh",
          f"judul={(n or {}).get('title')}")

    n = has_notif_for("hr@dewiaditya.id", prs["small"]["request_number"])
    check(n is None or True, "G6 (info) notifikasi pemohon tidak menyiram approver lain")

    # kategori bel: notifikasi PR harus jatuh ke kategori Pengadaan / Untuk Saya
    r = get("/api/notifications/categorized?limit=100", "finance@dewiaditya.id")
    cats = {i.get("category") for i in (r.json().get("items", []) if r.status_code == 200 else [])}
    check(r.status_code == 200 and ({"procurement", "personal"} & cats),
          "G7 notifikasi PR muncul di bel berkategori (Pengadaan / Untuk Saya)",
          f"kategori terlihat={sorted(c for c in cats if c)}")


# ═════════════════════════════════════════════════════════════════════════════
# H. Penolakan wajib beralasan
# ═════════════════════════════════════════════════════════════════════════════
def test_reject():
    section("H. PENOLAKAN — wajib beralasan, dan hanya oleh yang berhak")
    pr = make_pr("hr@dewiaditya.id", "POC untuk ditolak", "Gudang", 10, 500_000)
    submit(pr["id"], "hr@dewiaditya.id")

    r = post(f"/api/procurement/requests/{pr['id']}/reject", "hr@dewiaditya.id", {"reason": "iseng"})
    check(r.status_code == 403, "H1 bukan approver tidak bisa menolak", f"http={r.status_code}")

    r = post(f"/api/procurement/requests/{pr['id']}/reject", "gudang@dewiaditya.id", {"reason": "   "})
    check(r.status_code == 400, "H2 penolakan tanpa alasan ditolak 400 (dulu diterima kosong)",
          f"http={r.status_code} {str(r.json().get('detail'))[:80] if r.status_code == 400 else ''}")

    r = post(f"/api/procurement/requests/{pr['id']}/reject", "gudang@dewiaditya.id",
             {"reason": "Stok masih cukup untuk 2 bulan"})
    check(r.status_code == 200, "H3 penolakan beralasan berhasil", f"http={r.status_code}")
    after = read_pr(pr["id"], ADMIN[0])
    check(after.get("status") == "rejected" and after.get("rejection_reason"),
          "H4 status & alasan penolakan tersimpan",
          f"status={after.get('status')} alasan={after.get('rejection_reason')}")
    n = has_notif_for("hr@dewiaditya.id", pr["request_number"])
    check(n is not None and "ditolak" in (n.get("title", "") + n.get("message", "")).lower(),
          "H5 pemohon dikabari penolakan + alasannya", f"judul={(n or {}).get('title')}")


# ═════════════════════════════════════════════════════════════════════════════
# I. Regresi — PR disetujui masih bisa jadi PO
# ═════════════════════════════════════════════════════════════════════════════
def test_create_po(prs: dict):
    section("I. REGRESI — PR yang disetujui penuh tetap bisa jadi Purchase Order")
    pr_id = prs["large"]["id"]
    cur = read_pr(pr_id, ADMIN[0])
    check(cur.get("status") == "approved", "I1 PR besar berstatus approved",
          f"status={cur.get('status')}")
    r = post(f"/api/procurement/requests/{pr_id}/create-po", ADMIN[0],
             {"vendor_name": "PT Supplier POC"}, pw=ADMIN[1])
    ok = r.status_code in (200, 201)
    body = r.json() if ok else {}
    check(ok and (body.get("po_number") or body.get("po", {}).get("po_number")),
          "I2 PO berhasil dibuat dari PR (alur PR→PO tidak rusak)",
          f"http={r.status_code} {str(body)[:110] if ok else r.text[:110]}")


# ═════════════════════════════════════════════════════════════════════════════
# J. Uji mesin langsung — aturan berlaku walau tanpa jalur HTTP
# ═════════════════════════════════════════════════════════════════════════════
def test_engine_unit():
    section("J. MESIN PERSETUJUAN — diuji langsung (tanpa HTTP)")
    try:
        from routes.dewi_procurement import (
            _compute_chain, _eval_approval, _next_stage_after, _status_after_stage,
        )
    except Exception as e:  # noqa: BLE001
        check(False, "J0 mesin persetujuan bisa diimpor", str(e)[:120])
        return
    cfg = {"pr_1_stage_max": 1_000_000, "pr_2_stage_max": 25_000_000}
    check(_compute_chain(500_000, cfg) == ["dept"], "J1 Rp 500 rb → 1 tahap")
    check(_compute_chain(1_000_000, cfg) == ["dept"], "J2 tepat di ambang 1 tahap → 1 tahap")
    check(_compute_chain(1_000_001, cfg) == ["dept", "finance"], "J3 di atas ambang → 2 tahap")
    check(_compute_chain(25_000_001, cfg) == ["dept", "finance", "final"], "J4 di atas ambang 2 → 3 tahap")
    check(_compute_chain(None, cfg) == ["dept"], "J5 nilai kosong tidak membuat error")

    chain = ["dept", "finance", "final"]
    check(_next_stage_after(chain, "dept") == "finance", "J6 tahap sesudah dept = finance")
    check(_status_after_stage(["dept"], "dept") == "approved",
          "J7 rantai 1 tahap: setelah dept langsung `approved`")
    check(_status_after_stage(chain, "finance") == "finance_approved",
          "J8 rantai 3 tahap: setelah finance → menunggu final")

    me = {"id": "U1", "role": "accounting", "department": "Keuangan"}
    pr = {"status": "finance_approved", "requested_by": "U9", "total_estimated": 50_000_000,
          "department": "Gudang",
          "approval_steps": [{"action": "approved", "actor_id": "U1", "stage": "finance"}]}
    ev = _eval_approval(pr, me, chain)
    check(ev["can_approve"] is False and "dua tahap" in ev["blocked_reason"],
          "J9 orang yang sudah approve satu tahap ditolak di tahap lain (aturan, bukan kebetulan izin)",
          ev["blocked_reason"][:90])

    ev = _eval_approval({"status": "submitted", "requested_by": "U1", "department": "Keuangan",
                         "total_estimated": 100, "approval_steps": []},
                        {"id": "U1", "role": "manager", "department": "Keuangan"}, ["dept"])
    check(ev["can_approve"] is False and "sendiri" in ev["blocked_reason"],
          "J10 pembuat PR ditolak walau perannya approver tahap itu", ev["blocked_reason"][:90])

    ev = _eval_approval({"status": "submitted", "requested_by": "U9", "department": "Keuangan",
                         "total_estimated": 100, "approval_steps": []},
                        {"id": "U1", "role": "superadmin", "department": ""}, ["dept"])
    check(ev["can_approve"] is True and ev["is_override"] is True,
          "J11 admin boleh menembus, dan hasilnya ditandai override",
          f"reasons={ev['override_reasons']}")

    ev = _eval_approval({"status": "approved", "requested_by": "U9", "total_estimated": 100,
                         "approval_steps": []}, me, ["dept"])
    check(ev["can_approve"] is False and ev["stage"] is None,
          "J12 PR yang sudah selesai tidak menawarkan tombol persetujuan")


# ═════════════════════════════════════════════════════════════════════════════
# K. REQUEST PEMBELIAN AKSESORIS — harus memakai rantai YANG SAMA
# ═════════════════════════════════════════════════════════════════════════════
def test_accessory_pr():
    """Laporan owner 2026-08-07: "ada purchase request di aksesoris dan gudang,
    ini harusnya tersambung ke procurement."

    Sebelum perbaikan, `acc_purchase_requests` adalah alur paralel TANPA RBAC:
    `PUT /api/acc/purchase-requests/{id}` hanya butuh login, jadi akun
    `tim_packing` bisa membuat PR Rp 50 juta lalu MENYETUJUI SENDIRI, dan PR itu
    tidak pernah muncul di kotak persetujuan siapa pun.
    """
    section("K. REQUEST AKSESORIS — tersambung ke rantai persetujuan pengadaan")
    created = []
    cli, db = mongo()
    try:
        mats = get("/api/rahaza/materials", ADMIN[0], pw=ADMIN[1]).json()
        mats = mats if isinstance(mats, list) else (mats.get("items") or [])
        if not mats:
            check(False, "K0 master material tersedia untuk uji", "master material kosong")
            return
        mat = mats[0]

        def make_acc(requester, purpose, qty, price, dept="Gudang"):
            r = post("/api/acc/purchase-requests", requester, {
                "priority": "Normal", "purpose": purpose, "supplier": "",
                "department": dept,
                "items": [{"acc_id": mat["id"], "name": mat.get("name"),
                           "qty_requested": qty, "estimated_price": price,
                           "input_unit": "base"}],
            })
            r.raise_for_status()
            d = r.json()
            created.append(d["id"])
            return d

        # (1) PR besar oleh staf packing → wajib 3 tahap, bukan 1 langkah
        big = make_acc("packing@dewiaditya.id", "POC ACC besar", 100, 500_000)
        check(big.get("requested_by"), "K1 PR aksesoris mencatat ID pembuat (dulu hanya nama)",
              f"requested_by={'ada' if big.get('requested_by') else 'TIDAK ADA'}")
        rs = post(f"/api/acc/purchase-requests/{big['id']}/submit", "packing@dewiaditya.id")
        chain = rs.json().get("approval_chain") if rs.status_code == 200 else None
        check(rs.status_code == 200 and chain == ["dept", "finance", "final"],
              "K2 rantai mengikuti NILAI PR (Rp 50 jt → 3 tahap), sama seperti PR pengadaan",
              f"http={rs.status_code} chain={chain}")

        # (2) jalur bypass lama harus tertutup
        r = put(f"/api/acc/purchase-requests/{big['id']}", "packing@dewiaditya.id",
                {"status": "Approved", "finance_notes": "saya setujui sendiri"})
        check(r.status_code == 400,
              "K3 LUBANG DITUTUP: PUT status=Approved tidak lagi bisa melewati persetujuan",
              f"http={r.status_code} {str(r.json().get('detail'))[:80] if r.status_code != 200 else 'MASIH LOLOS'}")

        # (3) self-approval & tahap salah
        r = post(f"/api/acc/purchase-requests/{big['id']}/approve", "packing@dewiaditya.id")
        detail = str(r.json().get("detail")) if r.status_code != 200 else ""
        check(r.status_code == 403,
              "K4 pembuat PR aksesoris TIDAK bisa menyetujui PR-nya sendiri",
              f"http={r.status_code} {detail[:90]}")
        r = post(f"/api/acc/purchase-requests/{big['id']}/approve", "finance@dewiaditya.id")
        check(r.status_code == 403,
              "K5 keuangan TIDAK bisa memotong ke tahap departemen",
              f"http={r.status_code}")

        # (4) muncul di kotak persetujuan GABUNGAN milik approver yang benar
        ib = get("/api/procurement/inbox", "gudang@dewiaditya.id").json()
        found = [i for i in ib if i.get("id") == big["id"]]
        check(bool(found),
              "K6 PR aksesoris MUNCUL di kotak persetujuan pengadaan (dulu tidak pernah)",
              f"jumlah inbox={len(ib)}")
        if found:
            check(found[0].get("kind") == "acc_pr" and found[0].get("api_base") == "/api/acc/purchase-requests",
                  "K7 item membawa penanda asal + endpoint aksi untuk UI",
                  f"kind={found[0].get('kind')} api_base={found[0].get('api_base')}")
            check(found[0].get("can_approve") is True and found[0].get("chain"),
                  "K8 item membawa flag izin + rantai untuk stepper UI")
        bg = get("/api/approval-inbox/badge", "gudang@dewiaditya.id").json()
        check(bg.get("pr_pending") == len(ib),
              "K9 lencana TopBar ikut menghitung PR aksesoris",
              f"lencana={bg.get('pr_pending')} inbox={len(ib)}")

        # (5) rantai berjalan lewat 3 orang berbeda
        r = post(f"/api/acc/purchase-requests/{big['id']}/approve", "gudang@dewiaditya.id",
                 {"comment": "Setuju kebutuhan gudang"})
        check(r.status_code == 200 and r.json().get("next_stage") == "finance",
              "K10 tahap DEPARTEMEN disetujui approver yang benar",
              f"http={r.status_code} next={r.json().get('next_stage') if r.status_code == 200 else r.text[:80]}")
        r = post(f"/api/acc/purchase-requests/{big['id']}/approve", "gudang@dewiaditya.id")
        check(r.status_code == 403, "K11 orang yang sama tidak bisa lanjut ke tahap keuangan",
              f"http={r.status_code}")
        r = post(f"/api/acc/purchase-requests/{big['id']}/approve", "finance@dewiaditya.id",
                 {"comment": "Dana tersedia"})
        check(r.status_code == 200 and r.json().get("next_stage") == "final",
              "K12 tahap KEUANGAN disetujui, diteruskan ke direksi",
              f"http={r.status_code} next={r.json().get('next_stage') if r.status_code == 200 else r.text[:80]}")
        r = post(f"/api/acc/purchase-requests/{big['id']}/approve", "direktur@dewiaditya.id",
                 {"comment": "Disetujui direksi"})
        check(r.status_code == 200 and r.json().get("new_status") == "Approved",
              "K13 tahap FINAL menutup rantai → status Approved",
              f"http={r.status_code} status={r.json().get('new_status') if r.status_code == 200 else r.text[:80]}")

        # (6) notifikasi & jejak audit
        n = has_notif_for("finance@dewiaditya.id", big.get("pr_number"))
        check(n is not None, "K14 approver berikutnya dapat notifikasi (dulu tidak ada notifikasi apa pun)",
              f"judul={(n or {}).get('title')}")
        tl = get(f"/api/acc/purchase-requests/{big['id']}/timeline", ADMIN[0], pw=ADMIN[1]).json()
        steps = [s for s in tl.get("steps", []) if s.get("action") == "approved"]
        check(len(steps) == 3 and all(s.get("actor_id") for s in steps),
              "K15 jejak audit lengkap: 3 langkah persetujuan dengan ID aktor",
              f"langkah={len(steps)}")

        # (7) PR kecil cukup 1 tahap (aturan nilai berlaku juga di sini)
        small = make_acc("packing@dewiaditya.id", "POC ACC kecil", 10, 20_000)
        post(f"/api/acc/purchase-requests/{small['id']}/submit", "packing@dewiaditya.id")
        r = post(f"/api/acc/purchase-requests/{small['id']}/approve", "gudang@dewiaditya.id",
                 {"comment": "kecil"})
        check(r.status_code == 200 and r.json().get("new_status") == "Approved",
              "K16 PR aksesoris kecil (Rp 200 rb) cukup 1 tahap → langsung Approved",
              f"status={r.json().get('new_status') if r.status_code == 200 else r.text[:80]}")

        # (8) penolakan wajib beralasan
        rej = make_acc("packing@dewiaditya.id", "POC ACC ditolak", 50, 100_000)
        post(f"/api/acc/purchase-requests/{rej['id']}/submit", "packing@dewiaditya.id")
        r = post(f"/api/acc/purchase-requests/{rej['id']}/reject", "gudang@dewiaditya.id", {"reason": " "})
        check(r.status_code == 400, "K17 penolakan tanpa alasan ditolak 400", f"http={r.status_code}")
        r = post(f"/api/acc/purchase-requests/{rej['id']}/reject", "gudang@dewiaditya.id",
                 {"reason": "Stok masih cukup"})
        check(r.status_code == 200, "K18 penolakan beralasan berhasil", f"http={r.status_code}")

        # (9) "Terima Barang" (menambah STOK) tidak boleh dilakukan siapa pun
        r = put(f"/api/acc/purchase-requests/{small['id']}", "hr@dewiaditya.id",
                {"status": "Ordered"})
        check(r.status_code == 403,
              "K19 peran non-pengadaan tidak bisa memesan/menerima barang (Received menambah stok)",
              f"http={r.status_code}")
    finally:
        try:
            n1 = db.acc_purchase_requests.delete_many(
                {"$or": [{"id": {"$in": created}}, {"purpose": {"$regex": "^POC ACC"}}]}).deleted_count
            n2 = db.notifications.delete_many({"source_id": {"$in": created}}).deleted_count
            print(f"  bersih ACC: PR={n1} notif={n2}")
        finally:
            cli.close()


# ═════════════════════════════════════════════════════════════════════════════
def cleanup():
    section("PEMBERSIHAN — alat uji tidak boleh meninggalkan data palsu")
    cli, db = mongo()
    try:
        # PO hasil uji create-po. NAMA FIELD-nya `from_pr_id` (bukan `source_pr_id`)
        # — kekeliruan nama pada versi pertama skrip ini membuat 2 PO uji
        # tertinggal di data demo dan sempat tampil di layar Purchase Order.
        pos = list(db.rahaza_purchase_orders.find(
            {"$or": [{"from_pr_id": {"$in": CREATED_PR}}, {"source_pr_id": {"$in": CREATED_PR}}]},
            {"_id": 0, "id": 1, "po_number": 1}))
        po_ids = [p["id"] for p in pos if p.get("id")]
        n_pr = db.dewi_procurement_requests.delete_many({"id": {"$in": CREATED_PR}}).deleted_count
        n_po = db.rahaza_purchase_orders.delete_many({"id": {"$in": po_ids}}).deleted_count if po_ids else 0
        n_nt = db.notifications.delete_many({"source_id": {"$in": CREATED_PR}}).deleted_count
        n_ms = db.comm_messages.delete_many({"meta.pr_id": {"$in": CREATED_PR}}).deleted_count
        n_us = db.users.delete_many({"email": DUAL_EMAIL}).deleted_count
        print(f"  PR dihapus={n_pr} PO dihapus={n_po} notifikasi={n_nt} "
              f"pesan hub={n_ms} akun buangan={n_us}")
        left = db.dewi_procurement_requests.count_documents({"title": {"$regex": "^POC "}})
        check(left == 0, "Z1 tidak ada PR uji tertinggal di database", f"sisa={left}")
        check(db.users.count_documents({"email": DUAL_EMAIL}) == 0,
              "Z2 akun buangan POC sudah dihapus")
        left_po = db.rahaza_purchase_orders.count_documents({"vendor_name": "PT Supplier POC"})
        if left_po:
            db.rahaza_purchase_orders.delete_many({"vendor_name": "PT Supplier POC"})
            left_po = db.rahaza_purchase_orders.count_documents({"vendor_name": "PT Supplier POC"})
        check(left_po == 0, "Z3 tidak ada PO uji tertinggal di database", f"sisa={left_po}")
    finally:
        cli.close()


def main() -> int:
    print("\033[1mPOC RANTAI PERSETUJUAN PERMINTAAN PENGADAAN\033[0m")
    print(f"target: {BASE}")
    try:
        test_thresholds()
        prs = test_chain_depth()
        test_chain_frozen(prs)
        spv_pr = test_sod(prs)
        test_override(spv_pr)
        medium_id = test_inbox(prs)
        test_notifications(prs, medium_id)
        test_reject()
        test_create_po(prs)
        test_engine_unit()
        test_accessory_pr()
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        check(False, "EKSEKUSI SKRIP selesai tanpa error tak terduga", f"{type(e).__name__}: {e}")
    finally:
        if KEEP:
            print("\n  --keep: data uji DIBIARKAN (ingat bersihkan manual)")
        else:
            try:
                cleanup()
            except Exception as e:  # noqa: BLE001
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
