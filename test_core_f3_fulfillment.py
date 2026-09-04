#!/usr/bin/env python3
"""test_core_f3_fulfillment.py — CORE TEST **F3: Impor Ekspor B/C + "Batalkan impor"**.

═══════════════════════════════════════════════════════════════════════════════
APA YANG DIBUKTIKAN (dan kenapa itu yang diuji)
═══════════════════════════════════════════════════════════════════════════════
Ekspor A ("Untuk Dikirim") melahirkan pesanan. Ekspor **B** ("Dikirim/Selesai")
dan **C** ("Batal/Pengembalian") hanya KABAR SUSULAN. Tiga kelas cacat yang
mahal — dan gate ini yang menahannya:

1. **Pesanan HANTU.** Berkas fulfillment yang boleh membuat baris baru akan
   melahirkan pesanan tanpa item, tanpa uang, tanpa kreator — jumlah pesanan
   bulan itu naik tanpa ada penjualan.  → `F3-B3`
2. **Status MUNDUR.** Berkas diekspor berkali-kali dan urutan barisnya tidak
   dijamin. Baris kemarin yang menimpa hari ini membuat pesanan yang sudah
   sampai muncul lagi di daftar "belum dikirim".  → `F3-C1`
3. **"Batalkan impor" yang tidak menepati janji.** Impor ini tidak MEMBUAT baris,
   jadi rollback gaya lama ("hapus `committed_ids`") melaporkan *0 baris dihapus*
   sambil membiarkan SELURUH perubahan status di tempatnya.  → `F3-U*`

Dan satu keputusan kejujuran yang WAJIB dipertahankan (`F3-U4`): pesanan yang
berkasnya jadikan `cancelled`/`returned` sudah MELEPAS reservasi stoknya. Undo
memulihkan field susulannya, **tidak** menghidupkan statusnya, dan MENYEBUT nomor
pesanan + langkah manualnya. Menghidupkannya = menjanjikan barang yang sama ke
dua pembeli (aturan yang sama dengan `core/order_status.check_transition`).

Ditambah dua hal yang ikut diperbaiki bersama F3:
* `F3-L1` **kunci periode** juga berlaku untuk impor Ekspor B/C. Berkasnya tidak
  punya kolom tanggal pesanan, jadi periode diambil dari BULAN PESANAN TUJUAN.
  Tanpa itu, satu berkas "Dibatalkan" bisa menurunkan omzet bulan yang sudah
  dirapatkan tanpa satu pun penolakan.
* `F3-M*` **pemetaan kolom manual yang pintar**: usulan mesin (pasti/sinonim/
  mirip) tidak boleh HILANG begitu staf memperbaiki satu kolom — di jenis impor
  yang pemetaannya belum terverifikasi, usulan itu satu-satunya bantuan yang
  dimiliki staf.

Semua data uji dibuat & DIBERSIHKAN sendiri (toko `QAF3`), jadi gate ini tidak
bergantung pada data seed dan tidak meninggalkan sampah yang membuat gate lain
merah.

Pakai:  python3 /app/test_core_f3_fulfillment.py [--keep]
"""
from __future__ import annotations

import io
import csv
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

from core.marketing_import_engine import format_fingerprint  # noqa: E402

BASE = "http://localhost:8001"
API = f"{BASE}/api/marketing/data-import"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
RES: list = []

ACC_CODE = "QAF3"
ACC_NAME = "QA F3 Fulfillment (uji)"
O1, O2, O3, O4 = "F3QA-A1", "F3QA-A2", "F3QA-A3", "F3QA-A4"
SKU_A, SKU_B = "9001", "9002"
PERIOD = "2026-08"


def ok(n, d=""):
    RES.append((n, True, d)); print(f"  {G}PASS{X}  {n}" + (f" — {d}" if d else ""))


def bad(n, d=""):
    RES.append((n, False, d)); print(f"  {R}FAIL{X}  {n}" + (f" — {d}" if d else ""))


def check(n, c, d=""):
    (ok if c else bad)(n, d); return bool(c)


def db_conn():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


def login(cred) -> str | None:
    for _ in range(3):
        r = requests.post(f"{BASE}/api/auth/login", json=cred, timeout=30)
        if r.status_code == 200:
            return r.json().get("token")
        time.sleep(5)
    return None


def csv_bytes(header: list, rows: list) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for row in rows:
        w.writerow(row)
    return buf.getvalue().encode("utf-8-sig")


# ═══════════════════════════════════════════════════════════════════════════════
# BERKAS UJI — memakai LABEL kolom template resmi (yang diunduh staf dari layar)
# ═══════════════════════════════════════════════════════════════════════════════
A_HEAD = ["No. Pesanan", "Status Pesanan", "Platform Sumber", "SKU ID Platform",
          "SKU Penjual", "Jumlah", "Subtotal Setelah Diskon",
          "Order Amount (dibayar pembeli)", "Waktu Pesanan Dibuat"]
A_ROWS = [
    [O1, "Perlu dikirim", "Shopee", SKU_A, "QA-SKU-A", 2, 200000, 300000,
     "05/08/2026 10:00:00"],
    [O1, "Perlu dikirim", "Shopee", SKU_B, "QA-SKU-B", 1, 100000, "",
     "05/08/2026 10:00:00"],
    [O2, "Perlu dikirim", "Shopee", SKU_A, "QA-SKU-A", 1, 150000, 150000,
     "05/08/2026 11:00:00"],
    [O3, "Perlu dikirim", "Shopee", SKU_B, "QA-SKU-B", 1, 90000, 90000,
     "05/08/2026 12:00:00"],
    [O4, "Perlu dikirim", "Shopee", SKU_A, "QA-SKU-A", 3, 300000, 300000,
     "05/08/2026 13:00:00"],
]

B_HEAD = ["No. Pesanan", "Status Pesanan", "No. Resi", "Kurir",
          "Waktu Dikirim", "Waktu Diterima"]
B1_ROWS = [
    [O1, "Dikirim", "JX000111", "J&T Express", "07/08/2026 09:00:00", ""],
    [O2, "Terkirim", "JX000222", "SPX Express", "07/08/2026 09:30:00",
     "08/08/2026 15:00:00"],
    ["F3QA-HANTU", "Dikirim", "JX000999", "JNE", "07/08/2026 09:00:00", ""],
]
B2_ROWS = [[O1, "Perlu dikirim", "", "", "", ""]]          # MUNDUR tanpa bukti
B3_ROWS = [[O1, "Dikirim", "JX000111", "J&T Express", "07/08/2026 09:00:00", ""]]

C1_HEAD = ["No. Pesanan", "Status Pesanan", "Jenis Pembatalan/Pengembalian",
           "Alasan Pembatalan", "Dibatalkan Oleh", "Nilai Refund", "Waktu Dibatalkan"]
C1_ROWS = [[O3, "Dibatalkan", "Cancel by buyer", "Pembeli berubah pikiran",
            "Pembeli", 90000, "09/08/2026 11:00:00"]]

C2_HEAD = ["No. Pesanan", "Status Pesanan", "Jenis Pembatalan/Pengembalian",
           "SKU ID Platform", "Jumlah Dikembalikan", "Waktu Dibatalkan"]
C2_ROWS = [
    [O4, "Pengembalian", "Return/Refund", SKU_A, 1, "10/08/2026 08:00:00"],
    [O2, "Pengembalian", "Return/Refund", "9999", 1, "10/08/2026 08:00:00"],   # SKU asing
]

# Berkas dengan susunan kolom BAHASA PLATFORM (untuk uji usulan pemetaan)
M_HEAD = ["Order SN", "Order Status", "Tracking ID", "Shipping Provider Name",
          "Kolom Aneh XYZ"]
M_ROWS = [[O1, "Dikirim", "JX000111", "J&T Express", "abaikan"]]


class Ctx:
    """Keadaan yang harus dibersihkan, apa pun hasil ujinya."""

    def __init__(self):
        self.account_id = ""
        self.sessions: list = []
        self.fingerprints: set = set()


def upload(AH, ctx: Ctx, source_type: str, head: list, rows: list,
           fname: str) -> tuple:
    files = {"file": (fname, csv_bytes(head, rows), "text/csv")}
    data = {"source_type": source_type, "account_id": ctx.account_id}
    r = requests.post(f"{API}/upload", headers=AH, files=files, data=data, timeout=120)
    if r.status_code == 200:
        sid = r.json()["session"]["id"]
        ctx.sessions.append(sid)
        ctx.fingerprints.add(format_fingerprint(head))
        return r, sid
    return r, ""


def commit(AH, sid: str, **body) -> requests.Response:
    return requests.post(f"{API}/sessions/{sid}/commit", headers=AH,
                         json=body or {}, timeout=180)


def order(db, ctx, ref: str) -> dict:
    """Pesanan uji dari DB — selalu dict, supaya kegagalan satu langkah tidak
    menjatuhkan seluruh gate dengan AttributeError yang menyamarkan sebabnya."""
    return db.marketing_orders.find_one(
        {"account_id": ctx.account_id, "order_id": ref}, {"_id": 0}) or {}


# Field yang disentuh berkas Ekspor B/C. Dipakai untuk membandingkan keadaan
# SEBELUM impor dengan keadaan SESUDAH "Batalkan impor" — bukti terkuat bahwa
# pemulihan benar-benar mengembalikan nilai LAMA (termasuk nilai yang kebetulan
# bukan kosong, mis. `courier='lainnya'` dan `qty_returned_total=0`), bukan
# sekadar menghapus field.
WATCH = ("status", "status_raw", "platform_status", "substatus_raw",
         "tracking_number", "courier", "courier_raw", "shipped_date",
         "delivered_date", "cancelled_date", "returned_date", "cancel_by",
         "cancel_reason", "return_type_raw", "order_refund_amount",
         "fulfillment_status", "fulfillment_import_at",
         "fulfillment_import_session_id", "qty_returned_total")
ABSENT = "<tidak ada>"


def snap(o: dict) -> dict:
    return {k: (o[k] if k in o else ABSENT) for k in WATCH}


def diff(a: dict, b: dict) -> dict:
    return {k: f"{a.get(k)!r} → {b.get(k)!r}" for k in WATCH if a.get(k) != b.get(k)}


def item_of(o: dict, sku: str) -> dict:
    return next((i for i in (o.get("items") or [])
                 if str(i.get("platform_sku_id")) == sku), {})


def notes_of(resp: requests.Response) -> list:
    return (resp.json() or {}).get("row_notes") or []


def note_for(resp: requests.Response, ref: str) -> dict:
    """Catatan baris yang menyebut satu nomor pesanan (dicari lewat teks alasan)."""
    for n in notes_of(resp):
        if ref in " ".join(str(w) for w in (n.get("why") or [])):
            return n
    return {}


def cleanup(db, ctx: Ctx) -> None:
    aid = ctx.account_id
    if aid:
        db.marketing_orders.delete_many({"account_id": aid})
        db.marketing_sales_data.delete_many({"account_id": aid})
        db.marketing_period_locks.delete_many({"account_id": aid})
        db.marketing_change_log.delete_many({"account_id": aid})
        db.marketing_platform_accounts.delete_many({"id": aid})
        db.rahaza_coa_accounts.delete_many({"flags.subledger_entity_id": aid})
    if ctx.sessions:
        for s in db.marketing_data_import_sessions.find(
                {"id": {"$in": ctx.sessions}}, {"_id": 0, "file_path": 1}):
            p = s.get("file_path")
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        db.marketing_data_import_undo.delete_many({"session_id": {"$in": ctx.sessions}})
        db.marketing_data_import_sessions.delete_many({"id": {"$in": ctx.sessions}})
    if ctx.fingerprints:
        db.marketing_data_import_formats.delete_many(
            {"fingerprint": {"$in": sorted(ctx.fingerprints)}})


def main() -> int:  # noqa: C901,PLR0915
    keep = "--keep" in sys.argv
    print(f"{B}{'=' * 88}\nCORE TEST F3 — Impor Ekspor B/C (hanya memperbarui) + "
          f"Batalkan impor\n{'=' * 88}{X}")
    db = db_conn()
    at = login(ADMIN)
    if not at:
        print("login admin gagal — backend hidup?")
        return 2
    AH = {"Authorization": f"Bearer {at}"}
    JH = {**AH, "Content-Type": "application/json"}
    ctx = Ctx()

    try:
        # ── 0. KONTRAK LAYAR: jenis impornya ADA & membawa peringatannya ──────
        print(f"\n{Y}[F3-0] KATALOG JENIS IMPOR & TEMPLATE{X}")
        r = requests.get(f"{API}/source-types", headers=AH, timeout=60)
        types = {t["key"]: t for t in ((r.json() or {}).get("source_types") or [])}
        ff = types.get("marketplace_fulfillment") or {}
        check("F3-0a jenis 'marketplace_fulfillment' ada di katalog", bool(ff),
              f"{len(types)} jenis")
        check("F3-0b layar diberi tahu jenis ini HANYA MEMPERBARUI",
              ff.get("update_only") is True, f"update_only={ff.get('update_only')}")
        check("F3-0c peringatan 'pemetaan belum diverifikasi' dibawa ke layar",
              bool(ff.get("mapping_unverified")),
              (ff.get("mapping_unverified") or "")[:60] + "…")
        check("F3-0d petunjuk unduh berkas di Seller Center dibawa ke layar",
              bool(ff.get("export_hint")), (ff.get("export_hint") or "")[:60])
        r = requests.get(f"{API}/template/marketplace_fulfillment?fmt=csv",
                         headers=AH, timeout=60)
        head_line = r.content.decode("utf-8-sig", "replace").splitlines()[0] if r.ok else ""
        check("F3-0e template CSV bisa diunduh & berisi kolom kunci",
              r.status_code == 200 and "No. Pesanan" in head_line
              and "No. Resi" in head_line, head_line[:70])

        # ── 1. TOKO UJI + PESANAN DASAR (lewat impor Ekspor A yang sesungguhnya)
        print(f"\n{Y}[F3-A] PESANAN DASAR DARI EKSPOR A{X}")
        db.marketing_platform_accounts.delete_many({"account_code": ACC_CODE})
        r = requests.post(f"{BASE}/api/marketing/accounts", headers=JH, timeout=90,
                          json={"account_code": ACC_CODE, "account_name": ACC_NAME,
                                "platform": "shopee", "group": "other"})
        if r.status_code not in (200, 201):
            bad("F3-A0 toko uji dibuat", f"HTTP {r.status_code} {r.text[:160]}")
            return 1
        body = r.json()
        ctx.account_id = (body.get("account") or body).get("id") or body.get("id")
        ok("F3-A0 toko uji dibuat", f"{ACC_NAME} · id={ctx.account_id[:8]}")

        r, sid_a = upload(AH, ctx, "marketplace_orders", A_HEAD, A_ROWS, "qa_ekspor_a.csv")
        if not sid_a:
            bad("F3-A1 unggah Ekspor A", f"HTTP {r.status_code} {r.text[:200]}")
            return 1
        rc = commit(AH, sid_a)
        j = rc.json() if rc.ok else {}
        check("F3-A1 Ekspor A masuk: 4 pesanan (5 baris dikelompokkan)",
              rc.status_code == 200 and j.get("inserted") == 4,
              f"HTTP {rc.status_code} inserted={j.get('inserted')} {str(rc.text)[:120]}")
        o1 = order(db, ctx, O1)
        check("F3-A2 pesanan A1 punya 2 item & status 'paid'",
              bool(o1) and len(o1.get("items") or []) == 2 and o1.get("status") == "paid",
              f"status={(o1 or {}).get('status')} items={len((o1 or {}).get('items') or [])}")

        # ── 2. EKSPOR B — maju + PESANAN HANTU ditolak ────────────────────────
        print(f"\n{Y}[F3-B] EKSPOR B (dikirim/selesai){X}")
        before = {ref: snap(order(db, ctx, ref)) for ref in (O1, O2, O3, O4)}
        r, sid_b1 = upload(AH, ctx, "marketplace_fulfillment", B_HEAD, B1_ROWS,
                           "qa_ekspor_b.csv")
        if not sid_b1:
            bad("F3-B0 unggah Ekspor B", f"HTTP {r.status_code} {r.text[:200]}")
            return 1
        sess = (r.json() or {}).get("session") or {}
        check("F3-B0 kolom Ekspor B terpetakan otomatis (siap commit)",
              (sess.get("mapping_report") or {}).get("ready") is True,
              f"metode={(sess.get('mapping_report') or {}).get('methods')}")
        rb1 = commit(AH, sid_b1)
        jb1 = rb1.json() if rb1.ok else {}
        check("F3-B1 2 pesanan diperbarui, 1 ditolak, 0 baris baru",
              rb1.status_code == 200 and jb1.get("updated") == 2
              and jb1.get("rejected") == 1 and jb1.get("inserted") == 0,
              f"upd={jb1.get('updated')} rej={jb1.get('rejected')} "
              f"ins={jb1.get('inserted')}")
        hantu = note_for(rb1, "F3QA-HANTU")
        check("F3-B3 pesanan HANTU ditolak dengan jalan keluarnya",
              hantu.get("action") == "ditolak"
              and "belum" in " ".join(hantu.get("why") or []).lower()
              and "Pesanan Marketplace" in " ".join(hantu.get("why") or []),
              " ".join(hantu.get("why") or [])[:110])
        check("F3-B3b berkas fulfillment TIDAK melahirkan pesanan baru",
              db.marketing_orders.count_documents(
                  {"account_id": ctx.account_id}) == 4,
              f"{db.marketing_orders.count_documents({'account_id': ctx.account_id})} pesanan")
        o1 = order(db, ctx, O1)
        o2 = order(db, ctx, O2)
        check("F3-B4 status A1 → 'shipped' + resi & kurir tersimpan",
              o1.get("status") == "shipped" and o1.get("tracking_number") == "JX000111"
              and o1.get("courier") == "jnt",
              f"{o1.get('status')} resi={o1.get('tracking_number')} "
              f"kurir={o1.get('courier')}")
        sd = o1.get("shipped_date")
        check("F3-B5 tanggal kirim dipakai dari BERKAS (bukan jam impor)",
              isinstance(sd, datetime) and sd.strftime("%Y-%m-%d") == "2026-08-07",
              f"shipped_date={sd}")
        hist = [h for h in (o1.get("status_history") or [])
                if str(h.get("source") or "").startswith("import:")]
        check("F3-B6 perubahan status lewat SSOT (jejak status_history ada)",
              len(hist) >= 1 and hist[-1].get("to") == "shipped",
              f"{len(hist)} jejak impor · terakhir={hist[-1] if hist else None}")
        check("F3-B7 penanda 'pesanan ini sudah terlihat di Ekspor B' dipasang",
              bool(o1.get("fulfillment_import_at"))
              and o1.get("fulfillment_import_session_id") == sid_b1,
              f"at={o1.get('fulfillment_import_at')}")
        check("F3-B8 A2 → 'delivered' + tanggal terima dari berkas",
              o2.get("status") == "delivered"
              and isinstance(o2.get("delivered_date"), datetime)
              and o2["delivered_date"].strftime("%Y-%m-%d") == "2026-08-08",
              f"{o2.get('status')} delivered={o2.get('delivered_date')}")
        undo_n = db.marketing_data_import_undo.count_documents({"session_id": sid_b1})
        check("F3-B9 jejak pemulihan ditulis 1 per pesanan yang diubah",
              undo_n == 2, f"{undo_n} jejak")

        # ── 3. STATUS MUNDUR tanpa bukti ⇒ DITOLAK ────────────────────────────
        print(f"\n{Y}[F3-C] STATUS TIDAK BOLEH MUNDUR TANPA BUKTI{X}")
        r, sid_b2 = upload(AH, ctx, "marketplace_fulfillment", B_HEAD, B2_ROWS,
                           "qa_ekspor_b_mundur.csv")
        rb2 = commit(AH, sid_b2) if sid_b2 else r
        jb2 = rb2.json() if rb2.ok else {}
        why = " ".join((notes_of(rb2)[0].get("why") or []) if notes_of(rb2) else [])
        check("F3-C1 baris yang MEMUNDURKAN status ditolak + alasannya jelas",
              jb2.get("rejected") == 1 and jb2.get("updated") == 0
              and "memundurkan" in why.lower(), why[:120])
        o1 = order(db, ctx, O1)
        check("F3-C2 status A1 TETAP 'shipped' sesudah baris ditolak",
              o1.get("status") == "shipped", f"status={o1.get('status')}")

        # ── 4. EKSPOR C — batal (mundur DENGAN bukti) ─────────────────────────
        print(f"\n{Y}[F3-D] EKSPOR C (batal / retur){X}")
        # A3 dibuat seolah SUDAH masuk antrean gudang. Ini bukan hiasan: hanya
        # dalam keadaan itulah `apply_status` menarik pesanan keluar dari antrean
        # (`fulfillment_status='cancelled'`), sehingga bisa dibuktikan bahwa
        # "Batalkan impor" TIDAK mengembalikannya ke antrean.
        db.marketing_orders.update_one(
            {"account_id": ctx.account_id, "order_id": O3},
            {"$set": {"fulfillment_status": "pending_fulfillment"}})
        before[O3] = snap(order(db, ctx, O3))
        r, sid_c1 = upload(AH, ctx, "marketplace_fulfillment", C1_HEAD, C1_ROWS,
                           "qa_ekspor_c_batal.csv")
        rc1 = commit(AH, sid_c1) if sid_c1 else r
        jc1 = rc1.json() if rc1.ok else {}
        check("F3-D1 pembatalan diterima (mundur DENGAN bukti batal)",
              jc1.get("updated") == 1 and jc1.get("rejected") == 0,
              f"upd={jc1.get('updated')} rej={jc1.get('rejected')} {str(rc1.text)[:100]}")
        o3 = order(db, ctx, O3)
        check("F3-D2 A3 → 'cancelled' + tanggal batal & alasan dari berkas",
              o3.get("status") == "cancelled"
              and isinstance(o3.get("cancelled_date"), datetime)
              and o3.get("cancel_reason") == "Pembeli berubah pikiran"
              and float(o3.get("order_refund_amount") or 0) == 90000.0,
              f"{o3.get('status')} refund={o3.get('order_refund_amount')}")
        from core import order_status as _os  # noqa: PLC0415
        leaked = db.marketing_orders.count_documents(
            {**_os.leak_query(), "account_id": ctx.account_id})
        check("F3-D3 pesanan batal TIDAK lagi menggenggam reservasi stok (KT-11)",
              leaked == 0, f"{leaked} pesanan bocor")
        check("F3-D3b pesanan batal ditarik keluar dari antrean gudang",
              o3.get("fulfillment_status") == "cancelled",
              f"fulfillment_status={o3.get('fulfillment_status')}")

        r, sid_c2 = upload(AH, ctx, "marketplace_fulfillment", C2_HEAD, C2_ROWS,
                           "qa_ekspor_c_retur.csv")
        rc2 = commit(AH, sid_c2) if sid_c2 else r
        jc2 = rc2.json() if rc2.ok else {}
        check("F3-D4 retur per SKU diterima, SKU asing ditolak",
              jc2.get("updated") == 1 and jc2.get("rejected") == 1,
              f"upd={jc2.get('updated')} rej={jc2.get('rejected')}")
        asing = note_for(rc2, "9999")
        check("F3-D5 SKU yang tidak ada di pesanan ditolak (bukan dikarang)",
              asing.get("action") == "ditolak"
              and "tidak ada di pesanan" in " ".join(asing.get("why") or []),
              " ".join(asing.get("why") or [])[:110])
        o4 = order(db, ctx, O4)
        it_a = next((i for i in (o4.get("items") or [])
                     if str(i.get("platform_sku_id")) == SKU_A), {})
        check("F3-D6 A4 → 'returned' + qty retur per SKU & totalnya tersimpan",
              o4.get("status") == "returned" and int(it_a.get("qty_returned") or 0) == 1
              and int(o4.get("qty_returned_total") or 0) == 1,
              f"{o4.get('status')} qty_ret={it_a.get('qty_returned')} "
              f"total={o4.get('qty_returned_total')}")

        # ── 5. "BATALKAN IMPOR" YANG MENEPATI JANJINYA ────────────────────────
        print(f"\n{Y}[F3-U] BATALKAN IMPOR (pemulihan keadaan){X}")
        ru = requests.post(f"{API}/sessions/{sid_b1}/rollback", headers=JH, timeout=180)
        ju = ru.json() if ru.ok else {}
        rest = ju.get("restore") or {}
        check("F3-U1 pembatalan Ekspor B memulihkan 2 pesanan (0 baris dihapus)",
              ru.status_code == 200 and ju.get("deleted") == 0
              and rest.get("restored") == 2 and rest.get("status_restored") == 2,
              f"deleted={ju.get('deleted')} restore={ {k: v for k, v in rest.items() if k != 'notes'} }")
        o1 = order(db, ctx, O1)
        o2 = order(db, ctx, O2)
        check("F3-U2 status A1 kembali 'paid' & A2 kembali 'paid'",
              o1.get("status") == "paid" and o2.get("status") == "paid",
              f"A1={o1.get('status')} A2={o2.get('status')}")
        d1, d2 = diff(before[O1], snap(o1)), diff(before[O2], snap(o2))
        check("F3-U3 keadaan A1 & A2 PERSIS seperti sebelum impor "
              "(19 field dibandingkan, termasuk nilai lama yang bukan kosong)",
              not d1 and not d2, f"A1 beda={d1} · A2 beda={d2}")
        check("F3-U3c resi & penanda impor benar-benar hilang (bukan disimpan diam-diam)",
              "tracking_number" not in o1 and "fulfillment_import_at" not in o1
              and "fulfillment_import_session_id" not in o1
              and o1.get("courier") == before[O1]["courier"],
              f"courier={o1.get('courier')!r} (sebelum={before[O1]['courier']!r})")
        hist_undo = [h for h in (o1.get("status_history") or [])
                     if str(h.get("source") or "").startswith("undo-import:")]
        check("F3-U3b pemulihan status ikut meninggalkan jejak (bukan diam-diam)",
              len(hist_undo) == 1 and hist_undo[0].get("to") == "paid",
              f"{hist_undo[:1]}")

        ru2 = requests.post(f"{API}/sessions/{sid_c1}/rollback", headers=JH, timeout=180)
        ju2 = ru2.json() if ru2.ok else {}
        rest2 = ju2.get("restore") or {}
        note3 = next((n for n in (rest2.get("notes") or []) if n.get("order") == O3), {})
        o3 = order(db, ctx, O3)
        check("F3-U4 pesanan batal: field susulan dipulihkan, status TETAP batal (jujur)",
              rest2.get("fields_only") == 1 and rest2.get("status_restored") == 0
              and o3.get("status") == "cancelled"
              and "cancel_reason" not in o3 and "order_refund_amount" not in o3
              and "cancel_by" not in o3 and "fulfillment_import_at" not in o3,
              f"fields_only={rest2.get('fields_only')} status={o3.get('status')} "
              f"sisa={[k for k in ('cancel_reason', 'order_refund_amount', 'cancel_by') if k in o3]}")
        check("F3-U4b yang MENERANGKAN pembatalan tetap tinggal — tidak ada "
              "'pembatalan tanpa tanggal', dan pesanan batal TIDAK dikembalikan "
              "ke antrean gudang",
              isinstance(o3.get("cancelled_date"), datetime)
              and o3.get("fulfillment_status") == "cancelled"
              and before[O3]["fulfillment_status"] == "pending_fulfillment"
              and o3.get("status_raw") == "Dibatalkan"
              and o3.get("platform_status") == "Dibatalkan",
              f"tanggal={o3.get('cancelled_date')} "
              f"fulfillment={o3.get('fulfillment_status')} "
              f"(sebelum impor={before[O3]['fulfillment_status']}) "
              f"raw={o3.get('status_raw')!r} platform={o3.get('platform_status')!r}")
        check("F3-U5 laporan MENYEBUT nomor pesanan + langkah manualnya",
              note3.get("result") == "sebagian"
              and "pesanan BARU" in (note3.get("why") or "")
              and "cancelled" in (note3.get("why") or ""),
              (note3.get("why") or "")[:130])
        check("F3-U5b pesan ringkas pembatalan tidak mengaku berhasil seluruhnya",
              "HANYA field" in (ju2.get("message") or ""),
              (ju2.get("message") or "")[:120])

        ru3 = requests.post(f"{API}/sessions/{sid_c2}/rollback", headers=JH, timeout=180)
        rest3 = (ru3.json() or {}).get("restore") or {}
        o4 = order(db, ctx, O4)
        it_a = item_of(o4, SKU_A)
        check("F3-U6 qty retur per SKU dipulihkan ke nilai LAMA "
              "(tanpa menyentuh baris reservasi item)",
              rest3.get("fields_only") == 1
              and "qty_returned" not in it_a
              and o4.get("qty_returned_total") == before[O4]["qty_returned_total"]
              and "reserved_rows" not in it_a,
              f"item={it_a} total={o4.get('qty_returned_total')!r} "
              f"(sebelum={before[O4]['qty_returned_total']!r})")
        # SESI #20 — asersi ini DIPERBARUI beserta alasannya.
        # DULU: `fulfillment_status` diharapkan TIDAK berubah, karena impor menulis
        # istilah mati `'unallocated'` — istilah yang `core/order_status.apply_status`
        # juga tidak kenal (ia hanya memindahkan `pending_fulfillment` +
        # FULFILLMENT_RELEASABLE ke `cancelled`). Jadi pesanan yang DIRETUR tetap
        # duduk di antrean gudang; tidak ada yang sadar karena antrean gudang pun
        # tidak mengenal `'unallocated'` ⇒ dua cacat saling menutupi.
        # SEKARANG: kosakata status punya satu sumber (`core/fulfillment_status`),
        # `'unallocated'` diakui sebagai antrean, sehingga pesanan diretur WAJIB
        # keluar dari antrean — sama seperti pesanan dibatalkan pada asersi F3-U4b
        # di atas (RESERVATION_RELEASING_STATUSES = {cancelled, returned}).
        check("F3-U6c A4 tetap 'returned' + keterangan returnya, dan TIDAK "
              "nongkrong di antrean gudang",
              o4.get("status") == "returned"
              and o4.get("status_raw") == "Pengembalian"
              and o4.get("fulfillment_status") == "cancelled"
              and "return_type_raw" not in o4,
              f"{o4.get('status')} raw={o4.get('status_raw')!r} "
              f"fulfillment={o4.get('fulfillment_status')} "
              f"(sebelum impor={before[O4]['fulfillment_status']})")
        leaked = db.marketing_orders.count_documents(
            {**_os.leak_query(), "account_id": ctx.account_id})
        check("F3-U6b sesudah pemulihan, tidak ada pesanan terminal yang "
              "menggenggam reservasi", leaked == 0, f"{leaked} bocor")

        again = requests.post(f"{API}/sessions/{sid_b1}/rollback", headers=JH, timeout=90)
        check("F3-U7 membatalkan dua kali ditolak dengan alasan yang BENAR "
              "(bukan 'belum di-commit')",
              again.status_code == 400 and "sudah dibatalkan" in (again.text or "").lower(),
              f"HTTP {again.status_code} {again.text[:110]}")
        pending = db.marketing_data_import_undo.count_documents(
            {"session_id": {"$in": [sid_b1, sid_c1, sid_c2]}, "restored_at": None})
        check("F3-U8 seluruh jejak pemulihan ditandai SUDAH dipakai",
              pending == 0, f"{pending} jejak masih menganggur")
        rr = requests.get(f"{API}/sessions/{sid_c1}/undo-report", headers=AH, timeout=60)
        jr = rr.json() if rr.ok else {}
        check("F3-U9 laporan pemulihan bisa dibaca lagi dari Riwayat Impor",
              rr.status_code == 200 and jr.get("update_only") is True
              and jr.get("undo_pending") == 0 and jr.get("restore_fields_only") == 1
              and len(jr.get("restore_notes") or []) == 1,
              f"pending={jr.get('undo_pending')} notes={len(jr.get('restore_notes') or [])}")

        # ── 6. KUNCI PERIODE juga berlaku untuk Ekspor B/C ────────────────────
        print(f"\n{Y}[F3-L] KUNCI PERIODE PADA IMPOR EKSPOR B/C{X}")
        rl = requests.post(f"{BASE}/api/marketing/periods/lock", headers=JH, timeout=90,
                           json={"account_id": ctx.account_id, "period": PERIOD,
                                 "action": "close", "reason": "uji F3"})
        if rl.status_code != 200:
            bad("F3-L0 periode bisa ditutup", f"HTTP {rl.status_code} {rl.text[:140]}")
        else:
            ok("F3-L0 periode ditutup", f"{PERIOD} · {ACC_NAME}")
            r, sid_b3 = upload(AH, ctx, "marketplace_fulfillment", B_HEAD, B3_ROWS,
                               "qa_ekspor_b_terkunci.csv")
            rb3 = commit(AH, sid_b3) if sid_b3 else r
            check("F3-L1 commit Ekspor B ke bulan TERTUTUP ⇒ 423 + menyebut bulannya",
                  rb3.status_code == 423 and PERIOD in (rb3.text or ""),
                  f"HTTP {rb3.status_code} {str(rb3.text)[:130]}")
            o1 = order(db, ctx, O1)
            check("F3-L2 tidak ada perubahan separuh jalan (status tetap 'paid')",
                  o1.get("status") == "paid", f"status={o1.get('status')}")
            requests.post(f"{BASE}/api/marketing/periods/lock", headers=JH, timeout=90,
                          json={"account_id": ctx.account_id, "period": PERIOD,
                                "action": "open", "reason": "uji F3 selesai"})

        # ── 7. PEMETAAN MANUAL YANG PINTAR (BD-1 tanpa berkas contoh) ─────────
        print(f"\n{Y}[F3-M] USULAN PEMETAAN & KOREKSI MANUAL{X}")
        r, sid_m = upload(AH, ctx, "marketplace_fulfillment", M_HEAD, M_ROWS,
                          "qa_header_platform.csv")
        if not sid_m:
            bad("F3-M0 unggah berkas berkolom bahasa platform",
                f"HTTP {r.status_code} {r.text[:160]}")
        else:
            sess = (r.json() or {}).get("session") or {}
            mp = {m["column"]: m for m in (sess.get("mapping") or [])}
            rep = sess.get("mapping_report") or {}
            check("F3-M1 kolom bahasa platform dikenali otomatis (sinonim)",
                  mp.get("Order SN", {}).get("field") == "order_id"
                  and mp.get("Order Status", {}).get("field") == "status"
                  and mp.get("Tracking ID", {}).get("field") == "tracking_number",
                  f"metode={ {k: v.get('method') for k, v in mp.items()} }")
            check("F3-M2 kolom yang tidak dikenal TIDAK ditebak diam-diam",
                  not mp.get("Kolom Aneh XYZ", {}).get("field"),
                  f"field={mp.get('Kolom Aneh XYZ', {}).get('field')} "
                  f"metode={mp.get('Kolom Aneh XYZ', {}).get('method')}")
            check("F3-M3 pemetaan sudah 'siap' karena kolom wajib lengkap",
                  rep.get("ready") is True, f"missing={rep.get('missing_required')}")
            # staf mengoreksi SATU kolom → dasar keputusan kolom lain harus TETAP
            payload = [{"column": m["column"],
                        "field": (None if m["column"] == "Tracking ID" else m.get("field"))}
                       for m in (sess.get("mapping") or [])]
            rm = requests.put(f"{API}/sessions/{sid_m}/mapping", headers=JH, timeout=90,
                              json={"mapping": payload})
            mp2 = {m["column"]: m for m in ((rm.json() or {}).get("mapping") or [])}
            check("F3-M4 koreksi satu kolom TIDAK menghapus dasar keputusan kolom lain",
                  rm.status_code == 200
                  and mp2.get("Order SN", {}).get("method") == "synonym"
                  and mp2.get("Order Status", {}).get("method") == "synonym",
                  f"metode={ {k: v.get('method') for k, v in mp2.items()} }")
            check("F3-M5 kolom yang dilepas staf ditandai tidak dipakai",
                  mp2.get("Tracking ID", {}).get("field") in (None, "")
                  and mp2.get("Tracking ID", {}).get("method") == "none",
                  f"{mp2.get('Tracking ID')}")
            rbadf = requests.put(f"{API}/sessions/{sid_m}/mapping", headers=JH, timeout=90,
                                 json={"mapping": [{"column": "Order SN",
                                                    "field": "tidak_ada_field"}]})
            check("F3-M6 field ngawur ditolak (400), bukan diterima diam-diam",
                  rbadf.status_code == 400, f"HTTP {rbadf.status_code}")
            rdup = requests.put(f"{API}/sessions/{sid_m}/mapping", headers=JH, timeout=90,
                                json={"mapping": [{"column": "Order SN", "field": "order_id"},
                                                  {"column": "Order Status", "field": "order_id"}]})
            check("F3-M7 dua kolom ke satu field ditolak (400)",
                  rdup.status_code == 400, f"HTTP {rdup.status_code}")
            # ── F3.E — DATA YANG DIPAKAI LAYAR "PEMETAAN KOLOM" ───────────────
            # Tiga penjaga di bawah menjaga hal yang sama: layar pemetaan tidak
            # boleh berubah menjadi "percaya saja". Semuanya soal DATA yang harus
            # ada di respons — kalau hilang, layarnya masih tampil rapi tetapi
            # kehilangan satu-satunya bantuan yang dipunyai staf.
            check("F3-M8 kolom yang dilepas TETAP menyimpan usulan mesin "
                  "(sekali klik bisa dikembalikan)",
                  any(c.get("field") == "tracking_number"
                      for c in (mp2.get("Tracking ID", {}).get("candidates") or [])),
                  f"candidates={mp2.get('Tracking ID', {}).get('candidates')}")
            prev_rows = (r.json() or {}).get("preview") or []
            first_orig = (prev_rows[0] or {}).get("original") if prev_rows else {}
            check("F3-M9 pratinjau membawa isi asli per kolom (kolom 'Contoh isi' "
                  "layar pemetaan tidak kosong)",
                  bool(first_orig) and "Order SN" in (first_orig or {})
                  and str((first_orig or {}).get("Order SN") or "").strip() != "",
                  f"contoh={ {k: first_orig.get(k) for k in list(first_orig or {})[:3]} }")
            # field WAJIB dilepas ⇒ laporan menyebut yang hilang, DAN masih ada
            # kolom berkas yang mengusulkan field itu (bahan tombol "pakai kolom X")
            rreq = requests.put(f"{API}/sessions/{sid_m}/mapping", headers=JH, timeout=90,
                                json={"mapping": [
                                    {"column": m["column"],
                                     "field": (None if m["column"] == "Order Status"
                                               else m.get("field"))}
                                    for m in (mp2.values() if mp2 else [])]})
            mp3 = {m["column"]: m for m in ((rreq.json() or {}).get("mapping") or [])}
            rep3 = (rreq.json() or {}).get("mapping_report") or {}
            check("F3-M10 field WAJIB yang dilepas: laporan menyebutnya DAN masih "
                  "ada kolom yang mengusulkannya (usulan sekali klik)",
                  rreq.status_code == 200
                  and rep3.get("ready") is False
                  and any("Status" in s for s in (rep3.get("missing_required") or []))
                  and any(c.get("field") == "status"
                          for c in (mp3.get("Order Status", {}).get("candidates") or [])),
                  f"missing={rep3.get('missing_required')} "
                  f"candidates={mp3.get('Order Status', {}).get('candidates')}")
            # dikembalikan supaya sesi tidak ditinggal dalam keadaan tak siap
            requests.put(f"{API}/sessions/{sid_m}/mapping", headers=JH, timeout=90,
                         json={"mapping": [{"column": m["column"],
                                            "field": (m.get("field") or (
                                                "status" if m["column"] == "Order Status"
                                                else None))}
                                           for m in mp3.values()]})


    finally:
        if keep:
            print(f"\n{Y}--keep: data uji DIBIARKAN (toko {ACC_CODE}, "
                  f"{len(ctx.sessions)} sesi){X}")
        else:
            cleanup(db, ctx)
            print(f"\n{Y}data uji dibersihkan (toko {ACC_CODE} & {len(ctx.sessions)} "
                  f"sesi impor){X}")

    passed = sum(1 for _, c, _ in RES if c)
    failed = len(RES) - passed
    print(f"\n{B}{'=' * 88}{X}")
    print(f"  {G}{passed} PASS{X} · {(R + str(failed) + ' GAGAL' + X) if failed else '0 GAGAL'}"
          f" — total {len(RES)}")
    if failed:
        for n, c, d in RES:
            if not c:
                print(f"    {R}✗{X} {n} — {d}")
    print(f"{B}{'=' * 88}{X}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
