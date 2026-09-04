#!/usr/bin/env python3
"""INV-F42 (sesi #37) — **PENCAIRAN MARKETPLACE: FORM DI FINANCE & JURNAL YANG JUJUR**.

Yang diukur SEBELUM sesi ini (bukan dugaan):
  * `backend/routes/marketing_settlements.py` lengkap sejak F9, tetapi TIDAK ADA
    satu pun layar yang bisa MENCATAT pencairan — layar Marketing sengaja
    baca-saja. Jadi uang yang masuk dari Shopee/TikTok tidak punya pintu masuk.
  * `POST`/`journal` hanya dijaga `require_auth` ⇒ siapa pun yang bisa login dan
    memegang toko itu bisa membuat jurnal keuangan.
  * Jurnal memakai peta COA GLOBAL (`cash=1-1201`, `revenue=4-1100`) padahal
    setiap akun toko SUDAH punya `coa_cash_code`/`coa_revenue_code` sendiri
    (dibuat & divalidasi di `marketing_accounts.py`). Akibatnya uang dari SEMUA
    toko jatuh ke satu rekening dan laporan per toko tidak bisa
    dipertanggungjawabkan — tanpa satu pun galat.

Yang dijaga gate ini:
 A. **KEWENANGAN** — hanya portal `finance` boleh POST/PUT/DELETE/journal/post;
    Marketing tetap boleh GET.
 B. **COA** — jurnal WAJIB memakai akun toko; toko tanpa tautan akun DITOLAK
    dengan pesan yang menyebut field-nya, BUKAN diam-diam memakai `1-1201`.
 C. **OMZET TIDAK PERNAH MASUK GL DARI JALUR MARKETING** selain pencairan
    (dijaga statis: hanya `marketing_settlements.py` yang boleh memanggil
    pembuat jurnal di antara seluruh berkas `routes/marketing_*`).
 D. **SELISIH DISEBUT** — rekonsiliasi memberi NAMA pada selisihnya.
 E. **DOBEL-JURNAL DITOLAK** dan selisih aritmetika menahan jurnal.

Skrip ini MEMBERSIHKAN artefaknya sendiri (pencairan uji, toko uji, user uji, JE uji).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

API = os.environ.get("API_BASE", "http://localhost:8001")
G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
PASS: list[str] = []
FAIL: list[str] = []
STAMP = time.strftime("%H%M%S")
TAG = f"GATE42-{STAMP}"


def ok(code, msg, detail=""):
    PASS.append(code)
    print(f"  {G}✓ {code}{X} {msg}" + (f"\n         {C}{detail}{X}" if detail else ""))


def bad(code, msg, detail=""):
    FAIL.append(code)
    print(f"  {R}✗ {code} {msg}{X}" + (f"\n         {detail}" if detail else ""))


def head(t):
    print(f"\n{C}{B}▶ {t}{X}")


def det(d):
    return json.dumps(d, ensure_ascii=False, default=str)[:300]


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {"raw": raw[:300].decode(errors="ignore")}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def login(email, password):
    st, d = call("POST", "/api/auth/login", None,
                 {"email": email, "password": password})
    return (d or {}).get("token"), st, d


def main() -> int:  # noqa: C901
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    admin, st, d = login(os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                         os.environ.get("ADMIN_PASS", "Admin@123"))
    if not admin:
        bad("SETUP", f"login admin gagal (HTTP {st})", det(d))
        return 1

    fin_email = f"gate42.fin.{STAMP}@dewiaditya.id"
    mkt_email = f"gate42.mkt.{STAMP}@dewiaditya.id"
    created_users: list[str] = []
    acc_id = ""
    sids: list[str] = []

    try:
        # ── SETUP: dua pemakai dengan kewenangan berbeda ──────────────────────
        for email, role in ((fin_email, "accounting"), (mkt_email, "pic_toko")):
            st, r = call("POST", "/api/users", admin, {
                "email": email, "password": "Gate@42x", "name": TAG, "role": role})
            if st not in (200, 201):
                bad("SETUP", f"gagal membuat user uji {role} (HTTP {st})", det(r))
                return 1
            created_users.append(email)
        fin_tok, _, _ = login(fin_email, "Gate@42x")
        mkt_tok, _, _ = login(mkt_email, "Gate@42x")
        if not (fin_tok and mkt_tok):
            bad("SETUP", "login user uji gagal")
            return 1

        # Toko uji. Endpoint create MENGISI COA otomatis, jadi untuk menguji
        # kasus "toko warisan tanpa COA" tautannya dilepas langsung di DB —
        # justru keadaan itulah yang ada di data nyata (3 dari 3 toko demo).
        st, r = call("POST", "/api/marketing/accounts", admin, {
            "account_code": f"GATE42-{STAMP}", "account_name": f"{TAG} Toko Uji",
            "platform": "shopee", "username": "gate42"})
        if st not in (200, 201):
            bad("SETUP", f"gagal membuat toko uji (HTTP {st})", det(r))
            return 1
        acc_id = (r.get("account") or r).get("id")
        db.marketing_platform_accounts.update_one(
            {"id": acc_id},
            {"$unset": {"coa_cash_code": "", "coa_revenue_code": ""}})

        base = {
            "account_id": acc_id, "platform": "shopee",
            "settlement_date": "2026-08-20",
            "period_from": "2026-08-01", "period_to": "2026-08-15",
            "gross_sales": 10_000_000, "refunds": 500_000, "seller_discount": 300_000,
            "shipping_subsidy": 100_000, "platform_commission": 600_000,
            "platform_service_fee": 200_000, "affiliate_commission": 100_000,
            "ads_deduction": 400_000, "other_deductions": 0, "adjustments": 0,
            "net_payout": 8_000_000, "notes": TAG,
        }

        # ══ A. KEWENANGAN ═════════════════════════════════════════════════════
        head("A — FORM PENCAIRAN MILIK FINANCE (Marketing hanya melihat)")

        st, r = call("POST", "/api/marketing/settlements", mkt_tok,
                     {**base, "settlement_id": f"{TAG}-X"})
        if st == 403:
            ok("A1", "peran Marketing DITOLAK saat mencatat pencairan (403)")
        else:
            bad("A1", f"peran Marketing bisa mencatat pencairan (HTTP {st}) — "
                      f"pagar peran Finance tidak ada", det(r))

        st, r = call("POST", "/api/marketing/settlements", fin_tok,
                     {**base, "settlement_id": f"{TAG}-1"})
        if st == 200 and r.get("ok"):
            sids.append(r["data"]["id"])
            ok("A2", "peran Finance bisa mencatat pencairan",
               f"selisih {r['data'].get('net_payout_diff')} · "
               f"seimbang={r['data'].get('math_verified')}")
        else:
            bad("A2", f"Finance TIDAK bisa mencatat pencairan (HTTP {st})", det(r))
            return 1
        sid = sids[0]

        st, r = call("GET", f"/api/marketing/settlements/{sid}", admin)
        if st == 200 and r.get("data", {}).get("settlement_id") == f"{TAG}-1":
            ok("A3", "layar detail punya endpoint sendiri (GET /{sid}) dan melaporkan "
                     "kesiapan COA", det(r.get("coa")))
        else:
            bad("A3", f"GET /{{sid}} tidak melayani detail (HTTP {st})", det(r))

        st, r = call("GET", "/api/marketing/settlements/reconcile", admin)
        if st == 200 and "gap" in r:
            ok("A4", "GET /reconcile TIDAK ditelan rute /{sid} (urutan deklarasi benar)")
        else:
            bad("A4", f"/reconcile tertelan rute /{{sid}} (HTTP {st})", det(r))

        # ══ B. COA MILIK TOKO ═════════════════════════════════════════════════
        head("B — JURNAL WAJIB MEMAKAI AKUN TOKO, BUKAN AKUN BAWAAN")

        st, r = call("POST", f"/api/marketing/settlements/{sid}/journal", fin_tok)
        msg = str(r.get("detail") or "")
        if st == 400 and "coa_cash_code" in msg and "coa_revenue_code" in msg:
            ok("B1", "toko tanpa tautan akun DITOLAK dan field-nya disebut namanya")
        else:
            bad("B1", f"toko tanpa COA tidak ditolak dengan jelas (HTTP {st})", det(r))

        je_before = db.rahaza_journal_entries.count_documents(
            {"source_module": "marketplace_settlement", "source_ref": f"{TAG}-1"})
        if je_before == 0:
            ok("B2", "tidak ada jurnal yang lahir dari penolakan itu "
                     "(tidak ada jurnal separuh)")
        else:
            bad("B2", f"{je_before} jurnal terbentuk padahal permintaannya ditolak")

        cash_code = "1-131"
        rev = db.rahaza_coa_accounts.find_one(
            {"type": "REVENUE", "flags.channel": "shopee", "is_group": {"$ne": True}},
            sort=[("code", 1)])
        rev_code = (rev or {}).get("code")
        if not rev_code:
            bad("SETUP", "tidak ada akun pendapatan channel shopee di bagan akun")
            return 1
        st, r = call("PUT", f"/api/marketing/accounts/{acc_id}", admin,
                     {"coa_cash_code": cash_code, "coa_revenue_code": rev_code})
        if st != 200:
            bad("SETUP", f"gagal mengisi COA toko uji (HTTP {st})", det(r))
            return 1

        st, r = call("POST", f"/api/marketing/settlements/{sid}/journal", fin_tok)
        if st != 200 or not r.get("ok"):
            bad("B3", f"jurnal gagal dibuat padahal COA toko lengkap (HTTP {st})", det(r))
            return 1
        je = db.rahaza_journal_entries.find_one({"id": r["je_id"]})
        codes = {ln["account_code"] for ln in (je or {}).get("lines", [])}
        if cash_code in codes and rev_code in codes and "1-1201" not in codes:
            ok("B4", f"jurnal memakai rekening & pendapatan MILIK TOKO "
                     f"({cash_code} / {rev_code}); akun bawaan 1-1201 tidak dipakai")
        else:
            bad("B4", "jurnal tidak memakai COA toko", det(sorted(codes)))
        if (je or {}).get("status") == "draft":
            ok("B5", "jurnal lahir DRAFT (keputusan pemilik: ada tombol Posting terpisah)")
        else:
            bad("B5", f"jurnal langsung berstatus {(je or {}).get('status')}")

        # ══ C. OMZET TIDAK PERNAH MASUK GL DARI JALUR MARKETING ═══════════════
        head("C — HANYA PENCAIRAN YANG MENJURNAL (omzet marketing tidak masuk GL)")

        rdir = ROOT / "backend" / "routes"
        offenders = []
        for f in sorted(rdir.glob("marketing_*.py")):
            if f.name == "marketing_settlements.py":
                continue
            src = f.read_text(encoding="utf-8")
            # Baris komentar/docstring dibuang dulu: audit sebelumnya di repo ini
            # pernah MERAH karena membaca komentar sebagai kode.
            code_only = "\n".join(
                ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
            if re.search(r"_create_posted_je\s*\(|post_ar_invoice\s*\(", code_only):
                offenders.append(f.name)
        if not offenders:
            ok("C1", f"0 dari {len(list(rdir.glob('marketing_*.py'))) - 1} berkas "
                     f"routes/marketing_* memanggil pembuat jurnal — hanya pencairan")
        else:
            bad("C1", "ada jalur marketing lain yang memposting ke GL",
                det(offenders))

        bad_src = db.rahaza_journal_entries.count_documents(
            {"source_module": {"$in": ["marketing_order", "marketing_orders",
                                       "marketing_sales", "marketing_revenue",
                                       "marketing_omzet"]}})
        if bad_src == 0:
            ok("C2", "0 jurnal bersumber dari pesanan/omzet marketing di buku besar")
        else:
            bad("C2", f"{bad_src} jurnal lahir dari omzet marketing — dilarang pemilik")

        # ══ D. SELISIH DISEBUT NAMANYA ════════════════════════════════════════
        head("D — REKONSILIASI MENYEBUT SELISIHNYA, TIDAK MENGNOLKANNYA")

        st, r = call("GET",
                     f"/api/marketing/settlements/reconcile?settlement_id={TAG}-1", admin)
        named = ((r.get("gap") or {}).get("named") or []) if st == 200 else []
        if st == 200 and named and all(n.get("name") and n.get("action") for n in named):
            ok("D1", f"{len(named)} selisih diberi NAMA + tindakan",
               det([n["name"] for n in named]))
        else:
            bad("D1", f"selisih rekonsiliasi tidak diberi nama (HTTP {st})", det(r))
        if st == 200 and (r.get("period") or {}).get("from") == "2026-08-01":
            ok("D2", "periode diambil dari dokumen pencairannya sendiri "
                     "(staf tidak menyalin tanggal dengan tangan)")
        else:
            bad("D2", "periode rekonsiliasi tidak mengikuti period_from pencairan",
                det(r.get("period")))
        if st == 200 and "cancelled_orders_excluded" in (r.get("gap") or {}):
            ok("D3", "pesanan batal dikecualikan dan jumlahnya DILAPORKAN")
        else:
            bad("D3", "pesanan batal tidak dilaporkan pengecualiannya")

        # ══ E. DOBEL-JURNAL & SELISIH MENAHAN JURNAL ══════════════════════════
        head("E — DOBEL-JURNAL DITOLAK; ANGKA BELUM SEIMBANG TIDAK BOLEH DIJURNAL")

        st, r = call("POST", f"/api/marketing/settlements/{sid}/journal", fin_tok)
        n_je = db.rahaza_journal_entries.count_documents(
            {"source_module": "marketplace_settlement", "source_ref": f"{TAG}-1",
             "status": {"$ne": "voided"}})
        if st == 200 and r.get("already") and n_je == 1:
            ok("E1", "tekan 'Buat jurnal' dua kali tetap 1 jurnal")
        else:
            bad("E1", f"jurnal ganda ({n_je} dokumen)", det(r))

        st, r = call("DELETE", f"/api/marketing/settlements/{sid}", fin_tok)
        if st == 400:
            ok("E2", "pencairan yang sudah dijurnal tidak bisa dihapus")
        else:
            bad("E2", f"pencairan berjurnal bisa dihapus (HTTP {st})", det(r))

        st, r = call("POST", f"/api/marketing/settlements/{sid}/post", fin_tok)
        je = db.rahaza_journal_entries.find_one({"source_ref": f"{TAG}-1"})
        mirrored = db.rahaza_journal_lines.count_documents({"source_ref": f"{TAG}-1"})
        if st == 200 and (je or {}).get("status") == "posted" and mirrored > 0:
            ok("E3", f"tombol Posting memindahkan draf ke buku besar "
                     f"({mirrored} baris cermin GL)")
        else:
            bad("E3", f"posting draf gagal (HTTP {st}, status={(je or {}).get('status')}, "
                      f"cermin={mirrored})", det(r))
        st, r = call("POST", f"/api/marketing/settlements/{sid}/post", fin_tok)
        again = db.rahaza_journal_lines.count_documents({"source_ref": f"{TAG}-1"})
        if st == 200 and r.get("already") and again == mirrored:
            ok("E4", "posting dua kali tidak menggandakan baris buku besar")
        else:
            bad("E4", f"posting kedua mengubah GL ({mirrored} → {again})", det(r))

        st, r = call("POST", "/api/marketing/settlements", fin_tok,
                     {**base, "settlement_id": f"{TAG}-2", "net_payout": 7_000_000})
        if st == 200:
            sids.append(r["data"]["id"])
            st2, r2 = call("POST",
                           f"/api/marketing/settlements/{r['data']['id']}/journal", fin_tok)
            if st2 == 400 and "seimbang" in str(r2.get("detail", "")).lower():
                ok("E5", "selisih aritmetika menahan jurnal dan memintanya diberi nama")
            else:
                bad("E5", f"angka belum seimbang tetap dijurnal (HTTP {st2})", det(r2))
        else:
            bad("E5", f"gagal membuat pencairan tak seimbang untuk diuji (HTTP {st})")

        st, r = call("POST", "/api/marketing/settlements", fin_tok,
                     {**base, "settlement_id": f"{TAG}-1"})
        if st == 409:
            ok("E6", "nomor pencairan kembar untuk toko yang sama ditolak 409")
        else:
            bad("E6", f"nomor pencairan bisa kembar (HTTP {st})", det(r))

    finally:
        # ══ BERSIH-BERSIH ═════════════════════════════════════════════════════
        jes = list(db.rahaza_journal_entries.find(
            {"source_ref": {"$regex": f"^{TAG}"}}, {"_id": 0, "id": 1}))
        db.rahaza_journal_lines.delete_many({"source_ref": {"$regex": f"^{TAG}"}})
        db.rahaza_journal_entries.delete_many({"source_ref": {"$regex": f"^{TAG}"}})
        db.marketing_settlements.delete_many({"notes": TAG})
        if acc_id:
            db.marketing_platform_accounts.delete_one({"id": acc_id})
            db.rahaza_coa_accounts.delete_many({"entity_id": acc_id})
        db.users.delete_many({"email": {"$in": created_users}})
        left = (db.marketing_settlements.count_documents({"notes": TAG})
                + db.rahaza_journal_entries.count_documents(
                    {"source_ref": {"$regex": f"^{TAG}"}}))
        if left == 0:
            ok("Z1", f"artefak uji dibersihkan ({len(jes)} JE, {len(sids)} pencairan, "
                     f"{len(created_users)} user, 1 toko)")
        else:
            bad("Z1", f"{left} artefak uji tertinggal")

    print(f"\n{B}{'─' * 70}{X}")
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian pencairan (INV-F42) terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
