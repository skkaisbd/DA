"""
POC / E2E API test — Flow Keuangan: Kas & Rekonsiliasi Bank
===========================================================
flow_id: flow-keuangan-kas-bank

Membuktikan happy-path + guardrail lintas 3 modul Portal Keuangan:
  A. Kas Kecil (Petty Cash / imprest)   : opening -> expense (kas keluar) -> replenish (kas masuk) -> close
  B. Transfer Bank antar rekening        : create (Dr bank tujuan / Cr bank sumber) -> void reversal
  C. Rekonsiliasi Rekening Bank          : session -> import-bulk -> auto-match -> match manual -> approve

Semua transaksi kas/bank memicu auto-posting Jurnal GL (status 'posted') pada
rahaza_journal_entries + mirror rahaza_journal_lines.

Menjalankan:
    python3 tests/flow_keuangan_kas_bank_test.py

Self-cleanup: SEMUA dokumen yang dibuat skrip ini dihapus di blok finally
(termasuk JE + mirror-lines by source_ref, dan reset flag is_matched pada JE seed
yang mungkin tersentuh auto-match). DB kembali PRISTINE.
"""
import os
import sys
import uuid
import requests
from datetime import date, datetime, timezone

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

TAG = "POC-KASBANK-" + uuid.uuid4().hex[:8]          # penanda unik run ini
PERIOD = date.today().strftime("%Y-%m")               # periode rekon = bulan berjalan
TODAY = date.today().isoformat()

S = requests.Session()      # admin (superadmin)
SF = requests.Session()     # finance (role 'accounting')

st = {
    "fund_ids": [],
    "transfer_ids": [],
    "session_ids": [],
    "je_ids": [],            # JE yang dibuat oleh posting kas/bank kita (dihapus saat cleanup)
    "recon_txn_ids": [],     # bank_recon_txns milik kita (reset flag match pada JE seed)
    "passes": 0,
}


def ok(msg):
    st["passes"] += 1
    print(f"PASS {msg}")


def _hdr(sess, tok):
    sess.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})


# ─────────────────────────────────────────────────────────────────────────────
def login():
    r = S.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    _hdr(S, r.json()["token"])
    r2 = SF.post(f"{BASE}/api/auth/login", json={"email": "finance@dewiaditya.id", "password": "Dewi@123"})
    r2.raise_for_status()
    _hdr(SF, r2.json()["token"])
    ok("login admin (superadmin) + finance (role 'accounting')")


# ── A. KAS KECIL ─────────────────────────────────────────────────────────────
def petty_cash_flow():
    # A1. Buat dana kas kecil dgn saldo awal -> auto JE opening (Dr 1-1101 / Cr 1-1201)
    body = {"name": f"Kas Kecil {TAG}", "custodian_name": "Kasir POC",
            "opening_balance": 2_000_000, "bank_account_code": "1-1201",
            "notes": "fund POC"}
    r = S.post(f"{BASE}/api/finance/petty-cash/funds", json=body)
    assert r.status_code == 200, f"create fund {r.status_code}: {r.text}"
    fund = r.json()
    fid = fund["id"]
    st["fund_ids"].append(fid)
    assert fund["current_balance"] == 2_000_000 and fund["status"] == "active", fund
    ok(f"kas kecil: dana dibuat saldo awal 2.000.000 (fund={fid[:8]})")

    # A2. Kas keluar (expense) 137.500 -> saldo turun + auto JE (Dr 6-2200 / Cr 1-1101)
    exp_amt = 137_500
    body = {"fund_id": fid, "txn_type": "expense", "amount": exp_amt,
            "category": "utilities", "payee": "PLN",
            "memo": f"Kas Kecil Expense ATK {TAG}", "txn_date": TODAY}
    r = S.post(f"{BASE}/api/finance/petty-cash/transactions", json=body)
    assert r.status_code == 200, f"expense {r.status_code}: {r.text}"
    d = r.json()
    assert d["new_balance"] == 2_000_000 - exp_amt, d
    gp = d.get("gl_posting", {})
    assert gp.get("ok"), f"expense GL posting gagal: {gp}"
    st["je_ids"].append(gp["je_id"])
    st["expense_je_id"] = gp["je_id"]
    st["expense_amt"] = exp_amt
    ok(f"kas kecil: expense {exp_amt:,} diposting GL (JE {gp['je_number']}), saldo -> {d['new_balance']:,}")

    # A3. GUARD — expense melebihi saldo ditolak 400
    r = S.post(f"{BASE}/api/finance/petty-cash/transactions",
               json={"fund_id": fid, "txn_type": "expense", "amount": 999_999_999})
    assert r.status_code == 400, f"expected 400 saldo tidak cukup, got {r.status_code}: {r.text}"
    ok("kas kecil GUARD: expense melebihi saldo ditolak (400)")

    # A4. GUARD — txn_type 'replenish' via /transactions ditolak 400 (harus lewat /replenish)
    r = S.post(f"{BASE}/api/finance/petty-cash/transactions",
               json={"fund_id": fid, "txn_type": "replenish", "amount": 1000})
    assert r.status_code == 400, f"expected 400 replenish via txn, got {r.status_code}: {r.text}"
    ok("kas kecil GUARD: replenish via /transactions ditolak (400)")

    # A5. Kas masuk (replenish) 500.000 -> saldo naik + auto JE (Dr 1-1101 / Cr 1-1201)
    r = S.post(f"{BASE}/api/finance/petty-cash/funds/{fid}/replenish",
               json={"amount": 500_000, "bank_account_code": "1-1201", "memo": f"Top up {TAG}"})
    assert r.status_code == 200, f"replenish {r.status_code}: {r.text}"
    d = r.json()
    assert d["new_balance"] == (2_000_000 - exp_amt) + 500_000, d
    gp = d.get("gl_posting", {})
    assert gp.get("ok"), f"replenish GL gagal: {gp}"
    st["je_ids"].append(gp["je_id"])
    ok(f"kas kecil: replenish 500.000 diposting GL (JE {gp['je_number']}), saldo -> {d['new_balance']:,}")

    # A6. Detail fund menampilkan txns_count
    r = S.get(f"{BASE}/api/finance/petty-cash/funds/{fid}")
    assert r.status_code == 200 and r.json().get("txns_count", 0) >= 3, r.text
    ok(f"kas kecil: detail fund txns_count={r.json()['txns_count']}")

    # A7. List transaksi fund
    r = S.get(f"{BASE}/api/finance/petty-cash/transactions", params={"fund_id": fid})
    assert r.status_code == 200 and r.json()["total"] >= 3, r.text
    # kumpulkan semua JE dari txn fund ini utk cleanup
    ok(f"kas kecil: list transaksi total={r.json()['total']}")

    # A8. Tutup dana (sisa saldo dikembalikan ke bank -> JE return)
    r = S.post(f"{BASE}/api/finance/petty-cash/funds/{fid}/close", json={})
    assert r.status_code == 200, f"close {r.status_code}: {r.text}"
    d = r.json()
    assert d["ok"] and d["returned_balance"] == (2_000_000 - exp_amt) + 500_000, d
    if d.get("gl_posting", {}).get("je_id"):
        st["je_ids"].append(d["gl_posting"]["je_id"])
    ok(f"kas kecil: dana ditutup, sisa {d['returned_balance']:,} dikembalikan ke bank")

    # A9. GUARD — replenish dana yang sudah closed ditolak 400
    r = S.post(f"{BASE}/api/finance/petty-cash/funds/{fid}/replenish", json={"amount": 1000})
    assert r.status_code == 400, f"expected 400 replenish closed, got {r.status_code}"
    ok("kas kecil GUARD: replenish dana closed ditolak (400)")


# ── B. TRANSFER BANK ─────────────────────────────────────────────────────────
def bank_transfer_flow():
    xfer_amt = 246_800
    body = {"from_account_code": "1-1201", "from_account_name": "Bank BCA",
            "to_account_code": "1-1202", "to_account_name": "Bank Mandiri",
            "amount": xfer_amt, "transfer_date": TODAY, "memo": f"Transfer POC {TAG}"}
    r = S.post(f"{BASE}/api/finance/bank-transfers", json=body)
    assert r.status_code == 200, f"transfer {r.status_code}: {r.text}"
    d = r.json()
    tf = d["transfer"]
    tid = tf["id"]
    st["transfer_ids"].append(tid)
    assert tf["status"] == "completed" and tf["ref_number"].startswith("BT-"), tf
    gp = d.get("gl_posting", {})
    assert gp.get("ok"), f"transfer GL gagal: {gp}"
    st["je_ids"].append(gp["je_id"])
    st["transfer_je_id"] = gp["je_id"]
    st["transfer_amt"] = xfer_amt
    ok(f"transfer bank: {tf['ref_number']} {xfer_amt:,} diposting GL (JE {gp['je_number']})")

    # B2. GUARD — akun sumber == tujuan ditolak 400
    r = S.post(f"{BASE}/api/finance/bank-transfers",
               json={"from_account_code": "1-1201", "to_account_code": "1-1201", "amount": 1000})
    assert r.status_code == 400, f"expected 400 akun sama, got {r.status_code}: {r.text}"
    ok("transfer bank GUARD: akun sumber==tujuan ditolak (400)")

    # B3. Detail transfer
    r = S.get(f"{BASE}/api/finance/bank-transfers/{tid}")
    assert r.status_code == 200 and r.json()["id"] == tid, r.text
    ok("transfer bank: detail transfer diambil (200)")

    # B4. Void transfer -> reversal JE (Dr sumber / Cr tujuan)
    r = S.post(f"{BASE}/api/finance/bank-transfers/{tid}/void", json={})
    assert r.status_code == 200, f"void {r.status_code}: {r.text}"
    vd = r.json()
    assert vd.get("ok"), vd
    if vd.get("je_id"):
        st["je_ids"].append(vd["je_id"])   # void JE (source_ref void_bt:*) juga akan dibersihkan
    ok("transfer bank: void reversal JE dibuat (200)")

    # B5. GUARD — void ganda ditolak 400
    r = S.post(f"{BASE}/api/finance/bank-transfers/{tid}/void", json={})
    assert r.status_code == 400, f"expected 400 double void, got {r.status_code}"
    ok("transfer bank GUARD: void ganda ditolak (400)")


# ── C. REKONSILIASI BANK ─────────────────────────────────────────────────────
def bank_recon_flow():
    acct_no = f"ACC-{TAG}"
    # C1. Buat sesi rekonsiliasi periode berjalan
    body = {"period": PERIOD, "bank_name": "Bank BCA", "account_no": acct_no,
            "account_name": "CV Dewi Aditya - Operasional",
            "opening_balance": 10_000_000, "closing_balance": 10_384_300,
            "notes": f"rekon POC {TAG}"}
    r = S.post(f"{BASE}/api/finance/bank-recon/sessions", json=body)
    assert r.status_code == 200, f"create session {r.status_code}: {r.text}"
    sess = r.json()
    sid = sess["id"]
    st["session_ids"].append(sid)
    assert sess["status"] == "draft", sess
    ok(f"rekon: sesi dibuat periode {PERIOD} status=draft (session={sid[:8]})")

    # C2. GUARD — duplikat periode+akun ditolak 409
    r = S.post(f"{BASE}/api/finance/bank-recon/sessions", json=body)
    assert r.status_code == 409, f"expected 409 duplikat, got {r.status_code}: {r.text}"
    ok("rekon GUARD: sesi duplikat periode+akun ditolak (409)")

    # C3. GUARD — format periode salah ditolak 400
    r = S.post(f"{BASE}/api/finance/bank-recon/sessions",
               json={"period": "2026-13", "bank_name": "Bank X", "account_no": "ZZ"})
    assert r.status_code == 400, f"expected 400 periode salah, got {r.status_code}: {r.text}"
    ok("rekon GUARD: format periode salah (2026-13) ditolak (400)")

    # C4. Import mutasi rekening koran (import-bulk) — 2 mutasi cocok nominal JE kas/transfer kita
    txns = [
        {"txn_date": TODAY, "description": f"Kas Kecil Expense ATK {TAG}",
         "reference": "MUT-001", "amount": st["expense_amt"], "type": "debit"},
        {"txn_date": TODAY, "description": f"Transfer POC {TAG}",
         "reference": "MUT-002", "amount": st["transfer_amt"], "type": "credit"},
    ]
    r = S.post(f"{BASE}/api/finance/bank-recon/sessions/{sid}/import-bulk", json={"transactions": txns})
    assert r.status_code == 200 and r.json()["imported"] == 2, r.text
    ok("rekon: 2 mutasi bank diimpor (import-bulk)")

    # rekam id txns utk cleanup + verifikasi status in_progress & unmatched=2
    r = S.get(f"{BASE}/api/finance/bank-recon/sessions/{sid}/transactions")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    st["recon_txn_ids"] += [t["id"] for t in items]
    r = S.get(f"{BASE}/api/finance/bank-recon/sessions/{sid}")
    sess = r.json()
    assert sess["status"] == "in_progress" and sess["unmatched_count"] == 2, sess
    ok(f"rekon: sesi in_progress, unmatched={sess['unmatched_count']}")

    # C5. GUARD — approve saat unmatched>0 ditolak 400
    r = S.post(f"{BASE}/api/finance/bank-recon/sessions/{sid}/approve", json={})
    assert r.status_code == 400, f"expected 400 approve unmatched, got {r.status_code}: {r.text}"
    ok("rekon GUARD: approve saat unmatched>0 ditolak (400)")

    # C6. GL entries lookup periode
    r = S.get(f"{BASE}/api/finance/bank-recon/gl-entries", params={"period": PERIOD})
    assert r.status_code == 200 and r.json()["total"] >= 2, r.text
    ok(f"rekon: GL entries periode {PERIOD} ditemukan total={r.json()['total']}")

    # C7. Auto-match heuristik (nominal+tanggal+deskripsi) — buktikan endpoint bekerja
    r = S.post(f"{BASE}/api/finance/bank-recon/sessions/{sid}/auto-match", json={})
    assert r.status_code == 200, f"auto-match {r.status_code}: {r.text}"
    am = r.json()
    assert am["matched"] >= 1, f"auto-match diharapkan >=1 match, got {am}"
    ok(f"rekon: auto-match mencocokkan {am['matched']}/{am['attempted']} mutasi")

    # C8. Match manual utk sisa unmatched (deterministik -> unmatched=0)
    r = S.get(f"{BASE}/api/finance/bank-recon/sessions/{sid}/transactions", params={"matched": "false"})
    remaining = r.json()["items"]
    for t in remaining:
        rm = S.post(f"{BASE}/api/finance/bank-recon/sessions/{sid}/match",
                    json={"txn_id": t["id"], "gl_entry_id": st["expense_je_id"], "gl_ref": "manual-POC"})
        assert rm.status_code == 200, f"match {rm.status_code}: {rm.text}"
    r = S.get(f"{BASE}/api/finance/bank-recon/sessions/{sid}")
    sess = r.json()
    assert sess["unmatched_count"] == 0, f"unmatched harus 0: {sess}"
    ok(f"rekon: match manual selesai, unmatched=0 (matched={sess['matched_count']})")

    # C9. Unmatch -> unmatched naik -> approve ditolak -> rematch
    tid0 = st["recon_txn_ids"][0]
    r = S.post(f"{BASE}/api/finance/bank-recon/sessions/{sid}/unmatch", json={"txn_id": tid0})
    assert r.status_code == 200, r.text
    r = S.post(f"{BASE}/api/finance/bank-recon/sessions/{sid}/approve", json={})
    assert r.status_code == 400, f"expected 400 approve after unmatch, got {r.status_code}"
    S.post(f"{BASE}/api/finance/bank-recon/sessions/{sid}/match",
           json={"txn_id": tid0, "gl_entry_id": st["expense_je_id"], "gl_ref": "rematch-POC"})
    ok("rekon: unmatch -> approve ditolak (400) -> rematch (guard konsistensi)")

    # C10. Approve sesi (unmatched=0) -> status approved
    r = S.post(f"{BASE}/api/finance/bank-recon/sessions/{sid}/approve", json={})
    assert r.status_code == 200, f"approve {r.status_code}: {r.text}"
    assert r.json()["status"] == "approved", r.json()
    ok("rekon: sesi di-APPROVE (status=approved)")

    # C11. GUARD — sesi approved terkunci: tambah txn / approve ulang ditolak
    r = S.post(f"{BASE}/api/finance/bank-recon/sessions/{sid}/transactions",
               json={"txn_date": TODAY, "amount": 1000, "type": "debit"})
    assert r.status_code == 400, f"expected 400 add txn on approved, got {r.status_code}"
    r = S.post(f"{BASE}/api/finance/bank-recon/sessions/{sid}/approve", json={})
    assert r.status_code == 400, f"expected 400 approve twice, got {r.status_code}"
    ok("rekon GUARD: sesi approved terkunci (tambah txn & approve-ulang ditolak 400)")

    # C12. Summary dashboard
    r = S.get(f"{BASE}/api/finance/bank-recon/summary")
    assert r.status_code == 200 and r.json()["approved"] >= 1, r.text
    ok(f"rekon: summary dashboard approved={r.json()['approved']}")


# ── D. RBAC — role 'accounting' (finance@dewiaditya.id) ──────────────────────
def rbac_finance_role():
    # D1. create fund sebagai accounting -> 200 (RC-FLOW-kasbank-1 fix)
    r = SF.post(f"{BASE}/api/finance/petty-cash/funds",
                json={"name": f"Kas Kecil RBAC {TAG}", "opening_balance": 100_000})
    assert r.status_code == 200, f"accounting create fund harus 200, got {r.status_code}: {r.text}"
    fid = r.json()["id"]
    st["fund_ids"].append(fid)
    # opening JE fund ini juga dihapus via source_ref pctxn:* (dikumpulkan di cleanup)
    ok("RBAC: role 'accounting' BISA membuat dana kas kecil (200) — RC-FLOW-kasbank-1")

    # D2. create bank transfer sebagai accounting -> 200
    r = SF.post(f"{BASE}/api/finance/bank-transfers",
                json={"from_account_code": "1-1201", "to_account_code": "1-1202", "amount": 50_000,
                      "memo": f"RBAC transfer {TAG}"})
    assert r.status_code == 200, f"accounting create transfer harus 200, got {r.status_code}: {r.text}"
    tid = r.json()["transfer"]["id"]
    st["transfer_ids"].append(tid)
    if r.json().get("gl_posting", {}).get("je_id"):
        st["je_ids"].append(r.json()["gl_posting"]["je_id"])
    ok("RBAC: role 'accounting' BISA membuat transfer bank (200) — RC-FLOW-kasbank-1")


# ── CLEANUP (DB pristine) ────────────────────────────────────────────────────
def cleanup():
    try:
        from pymongo import MongoClient
    except Exception as e:  # pragma: no cover
        print(f"WARN cleanup skip (pymongo tak tersedia): {e}")
        return
    cli = MongoClient(MONGO_URL)
    db = cli[DB_NAME]

    # kumpulkan source_ref JE dari SEMUA txn kas kecil pada fund kita
    pc_refs = []
    if st["fund_ids"]:
        for t in db.rahaza_petty_cash_txns.find({"fund_id": {"$in": st["fund_ids"]}}, {"id": 1}):
            pc_refs.append(f"pctxn:{t['id']}")
    # source_ref transfer (normal + void)
    bt_refs = []
    for tid in st["transfer_ids"]:
        bt_refs += [f"bt:{tid}", f"void_bt:{tid}"]

    all_refs = pc_refs + bt_refs
    # 1. reset flag match pada JE (seed) yang tersentuh auto-match (matched_txn_id = txn rekon kita)
    if st["recon_txn_ids"]:
        db.rahaza_journal_entries.update_many(
            {"matched_txn_id": {"$in": st["recon_txn_ids"]}},
            {"$unset": {"is_matched": "", "matched_txn_id": ""}},
        )
    # 2. hapus JE + mirror lines milik kita (by source_ref) + by je_id yang tercatat
    if all_refs:
        db.rahaza_journal_entries.delete_many({"source_ref": {"$in": all_refs}})
        db.rahaza_journal_lines.delete_many({"source_ref": {"$in": all_refs}})
    if st["je_ids"]:
        db.rahaza_journal_entries.delete_many({"id": {"$in": st["je_ids"]}})
        db.rahaza_journal_lines.delete_many({"je_id": {"$in": st["je_ids"]}})
    # 3. hapus dokumen domain kas/bank/rekon milik kita
    if st["fund_ids"]:
        db.rahaza_petty_cash_txns.delete_many({"fund_id": {"$in": st["fund_ids"]}})
        db.rahaza_petty_cash_funds.delete_many({"id": {"$in": st["fund_ids"]}})
    if st["transfer_ids"]:
        db.rahaza_bank_transfers.delete_many({"id": {"$in": st["transfer_ids"]}})
    if st["session_ids"]:
        db.bank_recon_txns.delete_many({"session_id": {"$in": st["session_ids"]}})
        db.bank_recon_sessions.delete_many({"id": {"$in": st["session_ids"]}})
    cli.close()
    print("CLEANUP: dokumen POC dihapus (funds/txns/transfers/sessions/JE/lines) — DB pristine.")


def main():
    try:
        login()
        petty_cash_flow()
        bank_transfer_flow()
        bank_recon_flow()
        rbac_finance_role()
        print(f"\n=== KAS & REKONSILIASI BANK FLOW: ALL PASS ({st['passes']} assertions) ===")
    finally:
        cleanup()


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        sys.exit(2)
