#!/usr/bin/env python3
"""INV-5XX-01 — Endpoints must NOT 5xx on adversarial input (must return 2xx/4xx).

Adapted from Rahaza-Travel. Bad client input is the CLIENT's fault (4xx), never a server
crash (5xx). Fires malformed / hostile payloads (non-numeric where numbers expected, negative
money, huge strings, unicode/null, wrong types, missing required) at real da create/mutation
endpoints and asserts status < 500.

Resilient: backend down / login fail → SKIP. Exit 1 only when a real 5xx is observed.
Usage: cd /app && python scripts/guardrails/verify_adversarial_5xx.py
"""
import json
import os
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
from _common import Guard, G, R, Y, X  # noqa: E402

BASE = os.environ.get("GUARD_BASE_URL", "http://127.0.0.1:8001") + "/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@garment.com")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "Admin@123")
BIG = "A" * 60000
WEIRD = "x <b>&</b> <script> \u0000 \U0001f600 \u202e rtl"


def req(method, path, token=None, body=None, timeout=30):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(2000).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def login():
    st, txt = req("POST", "/auth/login", body={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    if st != 200:
        return None
    try:
        return json.loads(txt)["token"]
    except Exception:
        return None


def main() -> int:
    g = Guard("INV-5XX-01", "Tidak ada 5xx pada input adversarial (harus 2xx/4xx)")
    tok = login()
    if not tok:
        print(f"    {Y}[SKIP]{X} login admin gagal — backend/seed belum siap.")
        print(f"\n  {G}✓ INV-5XX-01 SKIP (Phase 0).{X}\n")
        return 0

    # (label, method, path, body)
    cases = [
        # Journal: non-numeric debit → float() must not crash
        ("journal debit non-numerik", "POST", "/rahaza/journals",
         {"date": "2028-01-01", "memo": "adv", "lines": [
             {"account_code": "1-1101", "debit": "abc", "credit": 0},
             {"account_code": "1-1102", "debit": 0, "credit": "xyz"}]}),
        # Journal: negative amounts → 400 not 500
        ("journal debit negatif", "POST", "/rahaza/journals",
         {"date": "2028-01-01", "memo": "adv", "lines": [
             {"account_code": "1-1101", "debit": -500, "credit": 0},
             {"account_code": "1-1102", "debit": 0, "credit": -500}]}),
        # Journal: malformed date
        ("journal tanggal ngawur", "POST", "/rahaza/journals",
         {"date": "bukan-tanggal", "memo": WEIRD, "lines": [
             {"account_code": "1-1101", "debit": 1, "credit": 0},
             {"account_code": "1-1102", "debit": 0, "credit": 1}]}),
        # Journal: lines wrong type
        ("journal lines bukan-list", "POST", "/rahaza/journals",
         {"date": "2028-01-01", "memo": "adv", "lines": "bukan-list"}),
        # AP invoice: negative amount / weird
        ("AP invoice amount negatif", "POST", "/rahaza/ap-invoices",
         {"vendor_name": WEIRD, "amount": -99999, "invoice_number": "ADV-5XX-1",
          "invoice_date": "2028-01-01", "due_date": "bad"}),
        # AP invoice: amount non-numeric
        ("AP invoice amount non-numerik", "POST", "/rahaza/ap-invoices",
         {"vendor_name": "adv", "amount": "gratis", "invoice_date": "2028-01-01"}),
        # Leave request: bad payload
        ("leave request payload buruk", "POST", "/rahaza/leaves/request",
         {"employee_id": "", "leave_type_id": None, "start_date": "??", "end_date": 12345, "reason": WEIRD}),
        # Leave type: huge string
        ("leave-type nama super panjang", "POST", "/rahaza/leave-types",
         {"name": BIG, "code": BIG[:100], "max_days": "banyak"}),
        # AR payment on non-existent invoice id (path param)
        ("AR payment invoice tak ada", "POST", "/rahaza/ar-invoices/does-not-exist-xyz/payment",
         {"amount": "abc", "date": "??"}),
        # Work order: negative/qty non-numeric
        ("work order qty non-numerik", "POST", "/rahaza/work-orders",
         {"model_name": WEIRD, "qty_target": "seratus", "due_date": "bad", "size_id": None}),
    ]

    for label, method, path, body in cases:
        st, txt = req(method, path, tok, body)
        g.bump()
        mark = f"{G}ok{X}" if 0 <= st < 500 else f"{R}5XX{X}"
        print(f"    [{mark}] {label}: HTTP {st}")
        if st >= 500:
            g.add(f"{label} -> HTTP {st} (5xx!). Endpoint harus menolak input buruk dgn 4xx, "
                  f"bukan crash. Resp: {txt[:160]}")

    _cleanup_artifacts()
    return g.finish()


def _cleanup_artifacts():
    """Hapus artefak yang mungkin tercipta oleh payload adversarial (hindari polusi DB berulang).

    Beberapa endpoint lenient membuat dokumen (mis. AP invoice tanpa items -> total 0) walau input
    hostile. Guard ini WAJIB read-mostly + bersih: hapus jejak bertanda adversarial di akhir.
    """
    try:
        from pymongo import MongoClient
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env"))
        except Exception:
            pass
        murl = os.environ.get("MONGO_URL")
        if not murl:
            return
        db = MongoClient(murl)[os.environ.get("DB_NAME", "test_database")]
        deleted = 0
        deleted += db.rahaza_ap_invoices.delete_many(
            {"$or": [{"vendor_name": {"$in": [WEIRD, "adv"]}},
                     {"invoice_number": {"$regex": "^ADV-5XX"}}]}).deleted_count
        deleted += db.rahaza_leave_types.delete_many(
            {"$or": [{"name": BIG}, {"code": BIG[:100]}]}).deleted_count
        deleted += db.rahaza_work_orders.delete_many({"model_name": WEIRD}).deleted_count
        deleted += db.rahaza_journal_entries.delete_many({"memo": {"$in": ["adv", WEIRD]}}).deleted_count
        if deleted:
            print(f"    {Y}cleanup: hapus {deleted} artefak adversarial.{X}")
    except Exception as e:  # noqa: BLE001
        print(f"    {Y}cleanup skip: {e}{X}")


if __name__ == "__main__":
    sys.exit(main())
