#!/usr/bin/env python3
"""POC — RANTAI PERSETUJUAN PURCHASE ORDER (Portal Pengadaan).

MENGAPA BERKAS INI ADA
----------------------
`plan.md` mencatat risiko: *"Approval PO (`rahaza_po.py`) belum memakai mesin SSOT
seperti `_eval_approval` — kelas bug yang sama (role list ganda di UI/BE) bisa
terulang di PO."* Risiko itu TERBUKTI NYATA, dan lebih berbahaya daripada di PR
karena **PO adalah komitmen uang ke supplier**:

  1. `_require_approver` lama memakai daftar peran karangan sendiri:
     ("superadmin", "owner", "manager", "production_manager", "warehouse_manager").
     Dari lima itu **hanya `superadmin` yang benar-benar ada** di aplikasi ini
     (`production_manager`/`warehouse_manager` tidak pernah ada; yang nyata
     `manager_produksi`/`admin_gudang`). Dibuktikan dengan panggilan nyata:
         direktur@ (director) → 403 · finance@ (accounting) → 403 · gudang@ → 403
     Jadi persetujuan PO MATI untuk semua orang kecuali superadmin.
  2. `admin@garment.com` bisa **submit LALU approve PO YANG SAMA** (200 lalu 200)
     — tidak ada larangan menyetujui PO sendiri, tidak ada mata kedua.
  3. Satu tahap saja, tidak mengikuti nilai PO, tanpa notifikasi ke approver,
     tanpa jejak audit per tahap, dan PO tidak pernah muncul di kotak persetujuan.
  4. Penolakan boleh tanpa alasan — frontend malah mengirim otomatis
     "Tidak ada alasan", jadi pembuat PO tidak pernah tahu apa yang harus dibetulkan.
  5. `create-po` menerima `items_override` (qty & unit_cost) TANPA batas, sehingga
     PR Rp 800.000 yang sudah disetujui bisa diterbitkan menjadi **PO Rp 800.000.000**.

Skrip ini menguji SEMUANYA lewat endpoint sungguhan, dan MEMBERSIHKAN datanya
sendiri di `finally` (penanda `__POCPO__`) supaya tidak meninggalkan PO/jurnal palsu.

PAKAI
-----
    python3 /app/scripts/poc_po_approval.py
Keluar rc=0 bila semua lolos, rc=1 bila ada yang gagal.
"""
from __future__ import annotations

import os
import sys
import time

import requests

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
MARK = "__POCPO__"
G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"

PASSES: list[str] = []
FAILS: list[str] = []
_tokens: dict = {}
CREATED_PO: list[str] = []

ADMIN = ("admin@garment.com", "Admin@123")
GUDANG = ("gudang@dewiaditya.id", "Dewi@123")        # admin_gudang → tahap pengadaan
FINANCE = ("finance@dewiaditya.id", "Dewi@123")      # accounting   → tahap keuangan
DIREKTUR = ("direktur@dewiaditya.id", "Dewi@123")    # director     → tahap final
PACKING = ("packing@dewiaditya.id", "Dewi@123")      # tim_packing  → tidak berhak
HR = ("hr@dewiaditya.id", "Dewi@123")                # hr           → tidak berhak


def ok(code, msg, extra=None):
    PASSES.append(code)
    print(f"  [{G}PASS{X}] {code} {msg}" + (f"  · {extra}" if extra else ""))


def bad(code, msg, extra=None):
    FAILS.append(f"{code} {msg}")
    print(f"  [{R}FAIL{X}] {code} {msg}" + (f"  · {extra}" if extra else ""))


def login(email, pw):
    if email in _tokens:
        return _tokens[email]
    for _ in range(6):
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": pw}, timeout=30)
        if r.status_code == 200:
            _tokens[email] = r.json().get("token", "")
            return _tokens[email]
        if r.status_code == 429:      # batas 10 login/60 detik per IP
            time.sleep(12)
            continue
        raise SystemExit(f"{R}Login {email} gagal HTTP {r.status_code}: {r.text[:160]}{X}")
    raise SystemExit(f"{R}Login {email} gagal terus (rate limit){X}")


def call(method, path, acct, **kw):
    tok = login(*acct)
    r = requests.request(method, f"{BASE}{path}",
                         headers={"Authorization": f"Bearer {tok}",
                                  "Content-Type": "application/json"},
                         timeout=60, **kw)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, {}


# ── data pendukung ──────────────────────────────────────────────────────────
def supplier_id():
    st, rows = call("GET", "/api/procurement/suppliers?limit=5", ADMIN)
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("data") or []
    return rows[0]["id"] if rows else None


def material():
    st, rows = call("GET", "/api/rahaza/materials?limit=100", ADMIN)
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("data") or []
    for m in rows:
        if m.get("code") == "ACC-BTN-12":
            return m
    return rows[0] if rows else None


def make_po(unit_cost, qty=10, actor=ADMIN):
    """Buat PO draft langsung (bukan dari PR)."""
    sid = supplier_id()
    mat = material()
    st, po = call("POST", "/api/rahaza/purchase-orders", actor, json={
        "supplier_id": sid,
        "notes": f"PO uji POC {MARK}",
        "items": [{
            "material_id": mat["id"], "description": mat["name"],
            "uom": mat.get("unit", "pcs"), "qty_input": qty,
            "unit_cost_input": unit_cost,
        }],
    })
    if st not in (200, 201):
        raise SystemExit(f"{R}Gagal membuat PO uji (HTTP {st}): {str(po)[:250]}{X}")
    CREATED_PO.append(po["id"])
    return po


# ═══════════════════════════════════════════════════════════════════════════
def t_roles_alive():
    """Q1–Q4 — peran yang NYATA harus bisa menyetujui PO sesuai tahapnya."""
    po = make_po(unit_cost=50_000, qty=10)          # Rp 500.000 → 1 tahap
    st, r = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/submit", ADMIN)
    if st == 200 and r.get("approval_chain") == ["dept"]:
        ok("Q1", "PO Rp 500.000 → 1 tahap (ambang nilai berlaku)",
           f"chain={r.get('approval_chain')}")
    else:
        bad("Q1", "PO kecil tidak 1 tahap", f"HTTP {st} chain={r.get('approval_chain')}")

    # pembuat (admin) TIDAK boleh menyetujui PO-nya sendiri — dulu bisa (200)
    st, r = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/approve", ADMIN)
    if st == 200 and r.get("override") is True:
        ok("Q2", "admin menyetujui PO sendiri DICATAT sebagai override (bukan diam-diam)",
           f"steps override={[s.get('override') for s in r.get('approval_steps', []) if s.get('action') == 'approved']}")
    elif st == 403:
        ok("Q2", "pembuat PO tidak boleh menyetujui sendiri (403)")
    else:
        bad("Q2", "pembuat PO masih bisa menyetujui sendiri TANPA jejak override",
            f"HTTP {st} override={r.get('override')}")

    # gudang@ (admin_gudang) harus bisa menyetujui tahap pengadaan
    po2 = make_po(unit_cost=50_000, qty=10)
    call("POST", f"/api/rahaza/purchase-orders/{po2['id']}/submit", ADMIN)
    st, r = call("POST", f"/api/rahaza/purchase-orders/{po2['id']}/approve", GUDANG,
                 json={"comment": "Supplier & harga sudah dicek."})
    if st == 200 and r.get("status") == "approved":
        ok("Q3", "gudang@ (admin_gudang) BISA menyetujui PO — dulu 403 (approval PO mati)")
    else:
        bad("Q3", "gudang@ masih tidak bisa menyetujui PO", f"HTTP {st} {str(r)[:160]}")

    # yang tidak berhak tetap ditolak
    po3 = make_po(unit_cost=50_000, qty=10)
    call("POST", f"/api/rahaza/purchase-orders/{po3['id']}/submit", ADMIN)
    st, r = call("POST", f"/api/rahaza/purchase-orders/{po3['id']}/approve", PACKING)
    if st == 403:
        ok("Q4", "tim_packing TIDAK boleh menyetujui PO (403)", str(r.get("detail"))[:90])
    else:
        bad("Q4", "tim_packing bisa menyetujui PO", f"HTTP {st}")
    return po3


def t_three_stage(po3):
    """Q5–Q9 — PO bernilai besar wajib 3 tahap oleh 3 ORANG BERBEDA."""
    po = make_po(unit_cost=5_000_000, qty=10)       # Rp 50.000.000 → 3 tahap
    st, r = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/submit", ADMIN)
    if st == 200 and r.get("approval_chain") == ["dept", "finance", "final"]:
        ok("Q5", "PO Rp 50 juta → 3 tahap dibekukan saat submit",
           f"chain={r.get('approval_chain')}")
    else:
        bad("Q5", "PO besar tidak 3 tahap", f"HTTP {st} chain={r.get('approval_chain')}")

    # tahap salah: finance@ saat tahap masih pengadaan
    st, _ = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/approve", FINANCE)
    if st == 403:
        ok("Q6", "approver tahap KEUANGAN ditolak saat tahap masih PENGADAAN (403)")
    else:
        bad("Q6", "tahap bisa dilompati", f"HTTP {st}")

    st, r = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/approve", GUDANG,
                 json={"comment": "Supplier sesuai daftar harga."})
    if st == 200 and r.get("next_stage") == "finance":
        ok("Q7", "tahap PENGADAAN disetujui gudang@ → lanjut tahap KEUANGAN")
    else:
        bad("Q7", "tahap pengadaan gagal", f"HTTP {st} next={r.get('next_stage')}")

    # orang yang sama tidak boleh dua tahap
    st, _ = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/approve", GUDANG)
    if st == 403:
        ok("Q8", "satu orang tidak boleh menyetujui dua tahap (403)")
    else:
        bad("Q8", "gudang@ bisa menyetujui dua tahap", f"HTTP {st}")

    st, r = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/approve", FINANCE,
                 json={"comment": "Anggaran tersedia."})
    if st == 200 and r.get("next_stage") == "final":
        ok("Q9", "tahap KEUANGAN disetujui finance@ → lanjut tahap FINAL")
    else:
        bad("Q9", "tahap keuangan gagal", f"HTTP {st} next={r.get('next_stage')}")

    st, r = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/approve", DIREKTUR,
                 json={"comment": "Disetujui direksi."})
    if st == 200 and r.get("status") == "approved":
        ok("Q10", "direktur@ (director) menutup tahap FINAL → PO approved "
                  "— dulu direktur 403 dan rantai mentok")
    else:
        bad("Q10", "direktur tidak bisa menutup tahap final", f"HTTP {st} {str(r)[:160]}")
    return po


def t_audit(po):
    """Q11 — jejak audit lengkap per tahap."""
    st, tl = call("GET", f"/api/rahaza/purchase-orders/{po['id']}/timeline", ADMIN)
    steps = [s for s in (tl.get("steps") or []) if s.get("action") == "approved"]
    complete = all(s.get("actor_id") and s.get("actor_name") and s.get("stage")
                   and s.get("timestamp") for s in steps)
    if st == 200 and len(steps) == 3 and complete:
        ok("Q11", "jejak audit 3 tahap lengkap (actor_id, nama, tahap, waktu)",
           " → ".join(s["stage"] for s in steps))
    else:
        bad("Q11", "jejak audit PO tidak lengkap",
            f"HTTP {st} langkah={len(steps)} lengkap={complete}")


def t_reject_reason():
    """Q12–Q13 — penolakan wajib beralasan."""
    po = make_po(unit_cost=50_000, qty=10)
    call("POST", f"/api/rahaza/purchase-orders/{po['id']}/submit", ADMIN)
    st, r = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/reject", GUDANG,
                 json={"reason": "   "})
    if st == 400:
        ok("Q12", "tolak PO tanpa alasan ditolak 400", str(r.get("detail"))[:80])
    else:
        bad("Q12", "PO bisa ditolak tanpa alasan", f"HTTP {st}")
    st, r = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/reject", GUDANG,
                 json={"reason": "Harga di atas daftar harga supplier."})
    if st == 200 and r.get("status") == "rejected":
        ok("Q13", "tolak PO dengan alasan → status rejected + alasan tersimpan",
           r.get("rejected_reason", "")[:60])
    else:
        bad("Q13", "tolak PO dengan alasan gagal", f"HTTP {st}")


def t_inbox_and_badge():
    """Q14–Q16 — PO muncul di kotak persetujuan GABUNGAN & lencana konsisten."""
    po = make_po(unit_cost=50_000, qty=10)
    call("POST", f"/api/rahaza/purchase-orders/{po['id']}/submit", ADMIN)

    st, inbox = call("GET", "/api/procurement/inbox", GUDANG)
    items = inbox if isinstance(inbox, list) else inbox.get("items", [])
    mine = [i for i in items if i.get("id") == po["id"]]
    if st == 200 and mine:
        it = mine[0]
        shape_ok = (it.get("kind") == "po"
                    and it.get("kind_label") == "Purchase Order"
                    and it.get("api_base") == "/api/rahaza/purchase-orders"
                    and it.get("module_id") == "proc-purchase-orders"
                    and it.get("can_approve") is True
                    and it.get("chain") and it.get("stage_label"))
        if shape_ok:
            ok("Q14", "PO muncul di kotak persetujuan gabungan dengan bentuk yang benar",
               f"kind={it['kind']} tahap={it['stage_label']}")
        else:
            bad("Q14", "bentuk item PO di inbox salah",
                {k: it.get(k) for k in ("kind", "kind_label", "api_base",
                                        "module_id", "can_approve")})
    else:
        bad("Q14", "PO TIDAK muncul di kotak persetujuan", f"HTTP {st} item={len(items)}")

    # INVARIAN: semua item di inbox harus benar-benar bisa disetujui user itu
    badrows = [i.get("request_number") for i in items if i.get("can_approve") is not True]
    if not badrows:
        ok("Q15", f"semua {len(items)} item inbox benar-benar hak gudang@")
    else:
        bad("Q15", "ada item inbox yang tidak berhak disetujui user", badrows)

    # lencana harus sama dengan jumlah isi inbox
    for acct, name in ((GUDANG, "gudang@"), (FINANCE, "finance@"),
                       (DIREKTUR, "direktur@"), (HR, "hr@")):
        st1, ib = call("GET", "/api/procurement/inbox", acct)
        st2, bd = call("GET", "/api/approval-inbox/badge", acct)
        n = len(ib if isinstance(ib, list) else ib.get("items", [])) if st1 == 200 else -1
        b = bd.get("pr_pending") if st2 == 200 else -2
        if n == b or (st1 == 403 and st2 == 200 and b == 0):
            ok("Q16", f"lencana = isi kotak persetujuan untuk {name}", f"{b}")
        else:
            bad("Q16", f"lencana ≠ isi kotak persetujuan untuk {name}",
                f"inbox={n} lencana={b}")
    return po


def t_pr_value_guard():
    """Q17–Q18 — PO tidak boleh diam-diam lebih mahal dari PR yang disetujui."""
    mat = material()
    # PR kecil Rp 500.000 → 1 tahap → disetujui penuh
    st, pr = call("POST", "/api/procurement/requests", PACKING, json={
        "title": f"Uji batas nilai PO {MARK}",
        "description": f"POC {MARK}", "department": "Gudang",
        "items": [{"name": "Kancing uji", "uom": "pcs", "qty": 10,
                   "estimated_price": 50_000, "material_id": mat["id"]}],
    })
    if st not in (200, 201):
        bad("Q17", "gagal membuat PR uji", f"HTTP {st}")
        return
    call("POST", f"/api/procurement/requests/{pr['id']}/submit", PACKING)
    call("POST", f"/api/procurement/requests/{pr['id']}/approve", GUDANG,
         json={"comment": "ok"})

    sid = supplier_id()
    # PO diterbitkan 100x lebih mahal lewat items_override
    item_id = (pr.get("items") or [{}])[0].get("id")
    st, po = call("POST", f"/api/procurement/requests/{pr['id']}/create-po", ADMIN, json={
        "supplier_id": sid, "notes": f"PO membengkak {MARK}",
        "items_override": [{"item_id": item_id, "qty": 10, "unit_cost": 5_000_000}],
    })
    if st in (200, 201):
        CREATED_PO.append(po["id"])
        if po.get("exceeds_pr_value") is True and po.get("pr_approved_value") == 500000.0:
            ok("Q17", "PO yang MELEBIHI nilai PR ditandai `exceeds_pr_value`",
               f"PR Rp {po['pr_approved_value']:,.0f} → PO Rp {po['total_value']:,.0f}")
        else:
            bad("Q17", "PO lebih mahal dari PR TIDAK ditandai",
                f"exceeds={po.get('exceeds_pr_value')} pr={po.get('pr_approved_value')}")
        st2, r = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/submit", ADMIN)
        if st2 == 200 and r.get("approval_chain") == ["dept", "finance", "final"]:
            ok("Q18", "PO membengkak DIPAKSA lewat rantai PENUH 3 tahap "
                      "(bukan 1 tahap seperti PO normal dari PR)",
               f"chain={r.get('approval_chain')}")
        else:
            bad("Q18", "PO membengkak tidak dipaksa rantai penuh",
                f"HTTP {st2} chain={r.get('approval_chain')}")
    else:
        bad("Q17", "gagal membuat PO dari PR", f"HTTP {st} {str(po)[:160]}")

    # PO normal (nilai sama dengan PR) cukup 1 tahap konfirmasi
    st, pr2 = call("POST", "/api/procurement/requests", PACKING, json={
        "title": f"Uji PO normal dari PR {MARK}",
        "description": f"POC {MARK}", "department": "Gudang",
        "items": [{"name": "Kancing uji 2", "uom": "pcs", "qty": 10,
                   "estimated_price": 50_000, "material_id": mat["id"]}],
    })
    call("POST", f"/api/procurement/requests/{pr2['id']}/submit", PACKING)
    call("POST", f"/api/procurement/requests/{pr2['id']}/approve", GUDANG, json={"comment": "ok"})
    st, po2 = call("POST", f"/api/procurement/requests/{pr2['id']}/create-po", ADMIN,
                   json={"supplier_id": sid, "notes": f"PO normal {MARK}"})
    if st in (200, 201):
        CREATED_PO.append(po2["id"])
        st2, r = call("POST", f"/api/rahaza/purchase-orders/{po2['id']}/submit", ADMIN)
        if st2 == 200 and r.get("approval_chain") == ["dept"]:
            ok("Q19", "PO dari PR yang TIDAK membengkak cukup 1 tahap konfirmasi "
                      "(kebutuhannya sudah lewat rantai penuh di PR)")
        else:
            bad("Q19", "PO normal dari PR tidak 1 tahap",
                f"HTTP {st2} chain={r.get('approval_chain')}")


def t_flags_and_gr():
    """Q20–Q22 — flag izin untuk UI + GR tetap butuh PO approved."""
    po = make_po(unit_cost=50_000, qty=10)
    call("POST", f"/api/rahaza/purchase-orders/{po['id']}/submit", ADMIN)

    st, rows = call("GET", "/api/rahaza/purchase-orders", PACKING)
    rows = rows if isinstance(rows, list) else rows.get("items", [])
    mine = [r for r in rows if r.get("id") == po["id"]]
    if mine and mine[0].get("can_approve") is False and mine[0].get("blocked_reason"):
        ok("Q20", "daftar PO membawa flag server untuk yang TIDAK berhak "
                  "(can_approve=false + alasan)",
           mine[0]["blocked_reason"][:80])
    else:
        bad("Q20", "daftar PO tidak membawa flag/alasan untuk tim_packing",
            f"ada={bool(mine)} can_approve={mine[0].get('can_approve') if mine else None}")

    st, d = call("GET", f"/api/rahaza/purchase-orders/{po['id']}", GUDANG)
    if st == 200 and d.get("can_approve") is True and d.get("stage_label"):
        ok("Q21", "detail PO membawa can_approve + label tahap untuk yang berhak",
           d["stage_label"])
    else:
        bad("Q21", "detail PO tidak membawa flag untuk gudang@",
            f"HTTP {st} can_approve={d.get('can_approve')}")

    st, r = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/create-gr", ADMIN, json={})
    if st == 400:
        ok("Q22", "GR tidak bisa dibuat dari PO yang belum disetujui (400)")
    else:
        bad("Q22", "GR bisa dibuat dari PO yang belum disetujui", f"HTTP {st}")


def cleanup():
    print(f"\n{C}PEMBERSIHAN — alat uji tidak boleh meninggalkan data palsu{X}")
    try:
        import asyncio

        from motor.motor_asyncio import AsyncIOMotorClient

        async def _c():
            cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db = cli[os.environ.get("DB_NAME", "test_database")]
            npo = (await db.rahaza_purchase_orders.delete_many(
                {"$or": [{"id": {"$in": CREATED_PO}}, {"notes": {"$regex": MARK}}]})).deleted_count
            npr = (await db.dewi_procurement_requests.delete_many(
                {"description": {"$regex": MARK}})).deleted_count
            nn = (await db.notifications.delete_many(
                {"source_id": {"$in": CREATED_PO}})).deleted_count
            ngr = (await db.warehouse_receiving.delete_many(
                {"po_id": {"$in": CREATED_PO}})).deleted_count
            print(f"  PO dihapus={npo} PR dihapus={npr} notifikasi={nn} GR={ngr}")
            left = await db.rahaza_purchase_orders.count_documents({"notes": {"$regex": MARK}})
            if left == 0:
                ok("Z1", "tidak ada PO uji tertinggal di database")
            else:
                bad("Z1", "masih ada PO uji tertinggal", f"sisa={left}")
            leftpr = await db.dewi_procurement_requests.count_documents(
                {"description": {"$regex": MARK}})
            if leftpr == 0:
                ok("Z2", "tidak ada PR uji tertinggal di database")
            else:
                bad("Z2", "masih ada PR uji tertinggal", f"sisa={leftpr}")
            cli.close()

        asyncio.run(_c())
    except Exception as e:  # noqa: BLE001
        bad("Z1", "pembersihan gagal", str(e)[:160])


def main():
    print(f"{C}{B}{'=' * 76}\n  POC — RANTAI PERSETUJUAN PURCHASE ORDER\n{'=' * 76}{X}")
    try:
        requests.get(f"{BASE}/api/health", timeout=10)
    except Exception:  # noqa: BLE001
        raise SystemExit(f"{R}Backend tidak bisa dihubungi di {BASE}{X}")
    try:
        po3 = t_roles_alive()
        po = t_three_stage(po3)
        t_audit(po)
        t_reject_reason()
        t_inbox_and_badge()
        t_pr_value_guard()
        t_flags_and_gr()
        ok("Q0", "EKSEKUSI SKRIP selesai tanpa error tak terduga")
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        bad("Q0", "EKSEKUSI SKRIP gagal", f"{type(e).__name__}: {e}")
    finally:
        cleanup()

    total = len(PASSES) + len(FAILS)
    print(f"\n{'=' * 76}\n  TOTAL: {len(PASSES)}/{total} PASS")
    if FAILS:
        print(f"\n  {R}GAGAL ({len(FAILS)}):{X}")
        for f in FAILS:
            print(f"    · {f}")
        print(f"\n  HASIL: {R}MASIH BERMASALAH{X}\n{'=' * 76}")
        return 1
    print(f"\n  HASIL: {G}LULUS{X}\n{'=' * 76}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
