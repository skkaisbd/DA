#!/usr/bin/env python3
"""verify_fase_g2_penomoran_ditegakkan.py — FASE G lanjutan (2026-08-17, sesi #18).

GATE **INV-F25** — "SETELAN PENOMORAN TIDAK BOLEH BERBOHONG."

YANG TERUKUR SEBELUM PERBAIKAN:
  · Layar Administrasi Sistem → Penomoran Dokumen menampilkan pilihan
    **Otomatis / Manual** untuk **49 jenis dokumen**, tetapi hanya **2** jalur tulis
    (PO Produksi & Roll Kain) yang benar-benar memanggil
    `core.doc_number_policy.issue_number`. Untuk 47 jenis lainnya owner bisa memindah
    ke "Manual", setelan itu TERSIMPAN, layar menampilkannya — dan dokumennya tetap
    bernomor otomatis. Setelan yang tidak ditegakkan lebih buruk daripada setelan yang
    tidak ada: ia membuat orang percaya sudah mengubah sesuatu.
  · Kasbon & Pinjaman memakai SATU field (`dewi_kasbon_requests.request_number`) dengan
    awalan berbeda (KSB/PIN), tetapi registry hanya punya satu kunci ⇒ satu kebijakan
    dipaksa untuk dua jenis dokumen.
  · Nomor kasbon yang lahir (`KSB-00001`) tidak mengikuti format yang tertulis di layar
    (`KSB-{YYYY}{MM}-{SEQ:5}`) — layar dan kenyataan berbeda.

INVARIAN:
  G1  setiap jenis dokumen ber-`policy_enforced` BENAR-BENAR lewat `issue_number`
      (statik: jalur tulisnya diperiksa, bukan dipercaya)
  G2  mode MANUAL: nomor kosong DITOLAK, pola bebas DITOLAK, pola benar DITERIMA
  G3  mode OTOMATIS: nomor ketikan DITOLAK (bukan diabaikan) & nomor yang lahir
      mengikuti FORMAT yang disetel owner
  G4  jenis dokumen yang BELUM ditegakkan: perubahan mode DITOLAK API (setelan tidak
      berbohong), sementara perubahan FORMAT tetap boleh
  G5  Kasbon & Pinjaman punya kebijakan TERPISAH (memindah satu tidak menyeret yang lain)
  G6  nomor unik: nomor manual yang sudah dipakai DITOLAK (409)
  G7  LAYAR memakai kebijakan: form kasbon membaca `/doc-number-policy` dan layar admin
      menyembunyikan pilihan mode untuk jenis yang belum ditegakkan
  G9  (SESI #19) setiap jenis dokumen berlabel jelas: ditegakkan · selalu otomatis
      (dengan ALASAN yang tampil di layar) · menunggu — tidak ada yang menggantung
  G8  (SESI #19) tiga jenis tambahan — **Surat Jalan Gudang**, **PR Pengadaan**,
      **Jurnal Umum** — ditegakkan pada DOKUMEN SUNGGUHAN: mode otomatis menolak
      nomor ketikan & nomor lahir mengikuti format owner; mode manual menolak nomor
      kosong, nomor berpola bebas, dan nomor kembar (409)

Self-cleaning: seluruh pengajuan uji (`UJI-G2 …`) dan setelan mode dikembalikan.

Pakai:  python3 scripts/verify_fase_g2_penomoran_ditegakkan.py
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(ROOT / "backend"))
from gr_common import db_handle

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

MARK = f"UJI-G2 {time.strftime('%H%M%S')}"
# SESI #27 — kunci "belum ditegakkan" untuk menguji G4 **DIPILIH OTOMATIS** dari
# registry, bukan ditulis tangan. Dua sesi berturut-turut (#19 lalu #27) gate ini
# MERAH karena alasan yang salah: kunci uji yang di-hardcode (`je_number`, lalu
# `rahaza_orders.order_number`) IKUT ditegakkan pada sesi itu, sehingga G4 menguji
# jenis yang justru sudah lulus. Penjaga yang harus disunting setiap kali produk
# maju adalah penjaga yang akan berbohong.
# Bila SUATU SAAT tidak ada lagi jenis `pending_enforce` (target Fase G), G4
# melaporkannya terang-terangan dan hanya menguji cabang "selalu otomatis" —
# bukan diam-diam lulus.
def _pick_pending():
    from data.doc_number_registry import DOC_NUMBER_REGISTRY as _R
    for e in _R:
        if e.get("pending_enforce"):
            return e["key"], e["default_format"]
    return None, None


KASBON_KEY = "dewi_kasbon_requests.request_number"
PINJAMAN_KEY = "dewi_kasbon_requests.request_number_pinjaman"
NOT_ENFORCED_KEY, NOT_ENFORCED_FORMAT = _pick_pending()
AUTO_ONLY_KEY = "rahaza_credit_notes.cn_number"          # lahir tanpa manusia

# Jalur tulis yang WAJIB memanggil issue_number untuk tiap kunci ber-policy_enforced.
WRITE_PATHS = {
    "production_pos.po_number": "backend/routes/production_pos.py",
    "production_pos.po_number_maklon": "backend/routes/production_pos.py",
    "wh_fabric_rolls.roll_no": "backend/core/fabric_roll_engine.py",
    "cmt_receipts.receipt_code": "backend/routes/dewi_cmt_packing.py",
    "dewi_maklon_invoices.invoice_number": "backend/routes/dewi_maklon_billing.py",
    "rahaza_ar_invoices.invoice_number": "backend/routes/rahaza_finance.py",
    KASBON_KEY: "backend/routes/dewi_kasbon.py",
    PINJAMAN_KEY: "backend/routes/dewi_kasbon.py",
    # SESI #19 — tiga jenis tambahan (permintaan owner)
    "wh_delivery_notes.sj_number": "backend/routes/wms_delivery_notes.py",
    "dewi_procurement_requests.request_number": "backend/routes/dewi_procurement.py",
    "rahaza_journal_entries.je_number": "backend/routes/rahaza_journals.py",
    # SESI #19 batch-2 (penomoran menyeluruh): dokumen UANG & STOK yang dibuat orang
    "rahaza_purchase_orders.po_number": "backend/routes/rahaza_po.py",
    "rahaza_material_issues.mi_number": "backend/routes/rahaza_inventory_shared.py",
    "wh_returns.return_code": "backend/routes/dewi_wh_returns.py",
    # SESI #27 batch-3 — SDM & Keuangan (dokumen yang DIKETIK orang)
    "rahaza_expense_claims.claim_number": "backend/routes/employee_expense_claims.py",
    "employee_travel_requests.trip_number": "backend/routes/employee_travel_requests.py",
    "employee_travel_settlements.settlement_number":
        "backend/routes/employee_travel_settlements.py",
    "rahaza_bank_transfers.ref_number": "backend/routes/rahaza_bank_transfers.py",
    "rahaza_orders.order_number": "backend/routes/rahaza_orders.py",
    # SESI #27 batch-3B — Produksi · Aksesoris · Marketing
    "dewi_cmt_permak.permak_number": "backend/routes/dewi_cmt_permak.py",
    "dewi_cmt_component_requests.request_code":
        "backend/routes/dewi_cmt_component_requests.py",
    "dewi_accessory_requests.request_code": "backend/routes/dewi_accessory_requests.py",
    "dewi_kreator_requests.request_code": "backend/routes/dewi_kreator_requests.py",
    "production_returns.return_number": "backend/routes/exceptions.py",
    # SESI #27 batch-3C
    "rahaza_fg_issues.issue_number": "backend/routes/rahaza_inventory_fg.py",
    "acc_purchase_requests.pr_number": "backend/routes/dewi_accessories_purchase.py",
    "dewi_maklon_samples.sample_code": "backend/routes/dewi_maklon_samples.py",
    "rahaza_fixed_assets.code": "backend/routes/rahaza_fixed_assets.py",
    "dewi_assets.asset_number": "backend/routes/asset/_helpers.py",
}

# SESI #27 — G12: seri nomor yang JALUR TULISNYA masih ada di kode tetapi SENGAJA
# tidak ditawarkan di katalog Penomoran Dokumen. Pengecualian WAJIB beralasan —
# daftar ini yang membuat "tidak ada di katalog" menjadi keputusan tertulis, bukan
# kelalaian yang tak terlihat.
EXEMPT_SERIES = {
    ("rahaza_employee_loans", "loan_number"):
        "Pintu pinjaman legacy ditutup HTTP 410 (sesi #27); pinjaman kanonik = "
        "Kasbon & Pinjaman (dewi_kasbon_requests.request_number_pinjaman). Fungsi "
        "lama disimpan sebagai rujukan migrasi, tidak dipasang di router.",
    ("production_material_returns", "ref_no"):
        "Menu 'Retur Material' (prod-material-returns) DI-DEPRECATE pemilik — "
        "material diurus lewat 'Kirim Material CMT'. Tidak ada layar yang "
        "membuatnya & koleksinya kosong, jadi menawarkan setelan nomor untuk "
        "dokumen ini akan menjadi setelan yang berbohong.",
}

# SESI #19 — FORM yang wajib membaca kebijakan (bukan sekadar backend yang menegakkan):
# form tanpa kolom nomor membuat mode MANUAL berarti "dokumen tidak bisa dibuat".
FORM_PATHS = {
    "wh_delivery_notes.sj_number":
        "frontend/src/components/erp/WMSDeliveryNotesModule.jsx",
    "dewi_procurement_requests.request_number":
        "frontend/src/components/erp/ProcurementRequestModule.jsx",
    "rahaza_journal_entries.je_number":
        "frontend/src/components/erp/RahazaJournalEntryModule.jsx",
    KASBON_KEY: "frontend/src/components/erp/KasbonStaffModule.jsx",
    # SESI #27 — Pinjaman memakai FORM YANG SAMA (satu layar, dua jenis dokumen);
    # sebelum ini ia lolos pemeriksaan hanya karena tidak terdaftar.
    PINJAMAN_KEY: "frontend/src/components/erp/KasbonStaffModule.jsx",
    "rahaza_purchase_orders.po_number":
        "frontend/src/components/erp/PurchaseOrderModule.jsx",
    "rahaza_material_issues.mi_number":
        "frontend/src/components/erp/RahazaMaterialIssueModule.jsx",
    "wh_returns.return_code":
        "frontend/src/components/erp/WHReturnsModule.jsx",
    # SESI #27 batch-3
    "rahaza_expense_claims.claim_number":
        "frontend/src/components/erp/EmployeeExpenseModule.jsx",
    "employee_travel_requests.trip_number":
        "frontend/src/components/erp/EmployeeTravelModule.jsx",
    "employee_travel_settlements.settlement_number":
        "frontend/src/components/erp/EmployeeTravelSettlementModule.jsx",
    "rahaza_bank_transfers.ref_number":
        "frontend/src/components/erp/BankTransferModule.jsx",
    # SESI #27 batch-3B
    "dewi_cmt_permak.permak_number":
        "frontend/src/components/erp/CMTPermakModule.jsx",
    "dewi_cmt_component_requests.request_code":
        "frontend/src/components/erp/CMTComponentRequestModule.jsx",
    "dewi_accessory_requests.request_code":
        "frontend/src/components/erp/AccessoryModule.jsx",
    "dewi_kreator_requests.request_code":
        "frontend/src/components/erp/KREATORRequestModule.jsx",
    "production_returns.return_number":
        "frontend/src/components/erp/engine/ProductionReturnModule.jsx",
    # SESI #27 batch-3C — jenis yang SUDAH ditegakkan sejak sesi lain tetapi formnya
    # belum pernah punya kolom nomor (mode MANUAL = dokumen tidak bisa dibuat).
    "rahaza_fg_issues.issue_number":
        "frontend/src/components/erp/RahazaFGInventoryModule.jsx",
    "acc_purchase_requests.pr_number":
        "frontend/src/components/erp/AccessoryModule.jsx",
    "dewi_maklon_samples.sample_code":
        "frontend/src/components/erp/MaklonSampleManagement.jsx",
    "rahaza_fixed_assets.code":
        "frontend/src/components/erp/FixedAssetsModule.jsx",
    "dewi_assets.asset_number":
        "frontend/src/components/erp/asset/dialogs/CreateAssetDialog.jsx",
    "cmt_receipts.receipt_code":
        "frontend/src/components/erp/WMSCMTDispatchesModule.jsx",
    "dewi_maklon_invoices.invoice_number":
        "frontend/src/components/erp/MaklonBillingModule.jsx",
    "rahaza_ar_invoices.invoice_number":
        "frontend/src/components/erp/RahazaARInvoicesModule.jsx",
    "production_pos.po_number":
        "frontend/src/components/erp/engine/ProductionPOModule.jsx",
    "production_pos.po_number_maklon":
        "frontend/src/components/erp/engine/ProductionPOModule.jsx",
}

PASS, FAIL = [], []


def ok(code, msg, extra=""):
    PASS.append(code)
    print(f"{G}  ✓ {code}{X} {msg}" + (f"\n         {C}{extra}{X}" if extra else ""))


def bad(code, msg, extra=""):
    FAIL.append(code)
    print(f"{R}  ✗ {code}{X} {msg}" + (f"\n         {extra}" if extra else ""))


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        d = e.read()
        return e.code, (json.loads(d or b"{}") if d[:1] in (b"{", b"[")
                        else {"raw": d[:300].decode(errors="ignore")})
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def det(d) -> str:
    return str((d or {}).get("detail") or (d or {}).get("raw") or d)[:400]


def set_mode(token, key, mode):
    return call("PUT", "/api/admin/doc-numbering", token,
                {"key": key, "mode": mode, "active": True})[0]


def ajukan(token, jenis, nomor=None, cicilan=1):
    body = {"type": jenis, "amount": 250000, "purpose": MARK,
            "reason": MARK, "installment_count": cicilan}
    if nomor is not None:
        body["request_number"] = nomor
    st, d = call("POST", "/api/dewi/kasbon/requests", token, body)
    return st, d, ((d or {}).get("request") or {}).get("request_number")


# ═════════════ SESI #19 — tiga jenis dokumen baru (SJ Gudang · PR · Jurnal) ════
# Dibuktikan pada DOKUMEN SUNGGUHAN lewat API, bukan dengan membaca kode: satu
# jenis bisa "memanggil issue_number" tetapi tetap salah bila formnya mengirim
# nomor pada mode otomatis atau modelnya membuang kolom nomor.
YMD = time.strftime("%Y%m%d")
SJ_TIPE = "SJ-INTERNAL"


def buat_sj(token, nomor=None):
    body = {"sj_type": SJ_TIPE, "recipient_name": MARK, "recipient_address": MARK,
            "notes": MARK, "lines": [{"description": MARK, "qty": 1, "unit": "pcs"}]}
    if nomor is not None:
        body["sj_number"] = nomor
    st, d = call("POST", "/api/wms/delivery-notes", token, body)
    return st, d, ((d or {}).get("sj") or {}).get("sj_number")


def buat_pr(token, nomor=None):
    body = {"title": MARK, "justification": MARK, "department": MARK,
            "items": [{"name": MARK, "qty": 1, "uom": "pcs", "estimated_price": 1000}]}
    if nomor is not None:
        body["request_number"] = nomor
    st, d = call("POST", "/api/procurement/requests", token, body)
    return st, d, (d or {}).get("request_number")


def buat_je(token, akun, nomor=None):
    body = {"date": time.strftime("%Y-%m-%d"), "memo": MARK, "post": False,
            "lines": [{"account_code": akun[0], "debit": 1000, "credit": 0,
                       "description": MARK},
                      {"account_code": akun[1], "debit": 0, "credit": 1000,
                       "description": MARK}]}
    if nomor is not None:
        body["je_number"] = nomor
    st, d = call("POST", "/api/rahaza/journals", token, body)
    return st, d, (d or {}).get("je_number")


def akun_jurnal(token) -> list:
    """Dua akun leaf yang sah untuk jurnal uji (tanpa mengubah data master)."""
    _st, d = call("GET", "/api/rahaza/coa/accounts", token)
    rows = d if isinstance(d, list) else (d or {}).get("items") or []
    leaf = [r.get("code") for r in rows
            if not r.get("is_group") and r.get("active") is not False and r.get("code")]
    return leaf[:2]


# ═══════ SESI #27 — batch-3: lima jenis dokumen SDM & Keuangan (G10) ═══════════
# Dibuktikan pada DOKUMEN SUNGGUHAN, sama seperti G8. Yang dijaga di sini bukan
# "kode memanggil issue_number" (itu G1) tetapi PERILAKUNYA: mode otomatis menolak
# nomor ketikan, nomor yang lahir mengikuti FORMAT owner, mode manual menolak
# kosong / pola bebas / nomor kembar.
TGL = time.strftime("%Y-%m-%d")


def buat_klaim(token, nomor=None):
    body = {"title": MARK, "notes": MARK,
            "items": [{"date": TGL, "category": "Transportasi", "amount": 10000,
                       "notes": MARK}]}
    if nomor is not None:
        body["claim_number"] = nomor
    st, d = call("POST", "/api/hr/expenses/claims", token, body)
    return (200 if st == 201 else st), d, (d or {}).get("claim_number")


def buat_dinas(token, nomor=None):
    body = {"destination": MARK, "destination_type": "luar_kota", "purpose": MARK,
            "start_date": TGL, "end_date": TGL, "cash_advance_requested": 0,
            "notes": MARK, "use_per_diem": False}
    if nomor is not None:
        body["trip_number"] = nomor
    st, d = call("POST", "/api/hr/expenses/travel", token, body)
    return (200 if st == 201 else st), d, (d or {}).get("trip_number")


def _dinas_disetujui(token):
    """Satu perjalanan dinas berstatus `approved` — bahan uji penyelesaian dinas.

    Penyelesaian dinas hanya boleh SATU per perjalanan, jadi setiap percobaan
    nomor membutuhkan perjalanan BARU (kalau tidak, penolakan yang terbaca adalah
    "settlement sudah ada", bukan penolakan NOMOR — penjaga yang mengukur hal yang
    salah lebih buruk daripada tidak ada penjaga).
    """
    st, d, _no = buat_dinas(token)
    tid = (d or {}).get("id")
    if st != 200 or not tid:
        return None
    call("POST", f"/api/hr/expenses/travel/{tid}/submit", token, {})
    call("POST", f"/api/hr/expenses/travel/{tid}/approve", token, {"note": MARK})
    return tid


def buat_penyelesaian(token, nomor=None):
    tid = _dinas_disetujui(token)
    if not tid:
        return 0, {"detail": "gagal menyiapkan perjalanan dinas uji"}, None
    body = {"actual_items": [{"date": TGL, "category": "Transportasi", "amount": 10000,
                             "notes": MARK}], "notes": MARK}
    if nomor is not None:
        body["settlement_number"] = nomor
    st, d = call("POST", f"/api/hr/expenses/travel/{tid}/settlements", token, body)
    return (200 if st == 201 else st), d, (d or {}).get("settlement_number")


def buat_order(token, nomor=None):
    _s1, models = call("GET", "/api/rahaza/models", token)
    _s2, sizes = call("GET", "/api/rahaza/sizes", token)
    models = models if isinstance(models, list) else []
    sizes = sizes if isinstance(sizes, list) else []
    if not models or not sizes:
        return 0, {"detail": "master model/size kosong"}, None
    body = {"is_internal": True, "notes": MARK,
            "items": [{"model_id": models[0]["id"], "size_id": sizes[0]["id"], "qty": 1}]}
    if nomor is not None:
        body["order_number"] = nomor
    st, d = call("POST", "/api/rahaza/orders", token, body)
    return st, d, (d or {}).get("order_number")


def buat_transfer(token, nomor=None):
    """Transfer bank — HANYA dipakai untuk jalur PENOLAKAN.

    Membuat transfer yang BERHASIL akan otomatis memposting jurnal GL
    (Dr bank tujuan / Cr bank sumber). Gate tidak boleh meninggalkan jurnal
    yatim, jadi jalur "manual dengan nomor benar" TIDAK dieksekusi di sini dan
    hal itu dinyatakan terang-terangan pada hasil G10.
    """
    body = {"from_account_code": "1-1201", "to_account_code": "1-1202",
            "amount": 1000, "memo": MARK}
    if nomor is not None:
        body["ref_number"] = nomor
    st, d = call("POST", "/api/finance/bank-transfers", token, body)
    return st, d, (((d or {}).get("transfer") or {}).get("ref_number"))


# ═══════ SESI #27 — batch-3B: Produksi · Aksesoris · Marketing (G13) ═══════════
def buat_permintaan_komponen(token, nomor=None):
    body = {"request_type": "component", "notes": MARK,
            "items": [{"component_type": "Label", "qty": 1, "unit": "pcs",
                       "notes": MARK}]}
    if nomor is not None:
        body["request_code"] = nomor
    st, d = call("POST", "/api/dewi/cmt-component-requests", token, body)
    return (200 if st == 201 else st), d, (d or {}).get("request_code")


def buat_permintaan_aksesoris(token, nomor=None):
    body = {"request_type": "internal_issuance", "divisi": MARK, "notes": MARK,
            "items": [{"material_name": MARK, "qty": 1, "unit": "pcs"}]}
    if nomor is not None:
        body["request_code"] = nomor
    st, d = call("POST", "/api/dewi/accessory-requests", token, body)
    return (200 if st == 201 else st), d, (d or {}).get("request_code")


def buat_permintaan_kreator(token, nomor=None):
    body = {"kreator_name": MARK, "kreator_type": "tiktok_video",
            "product_concept": MARK, "notes": MARK, "sample_qty": 1}
    if nomor is not None:
        body["request_code"] = nomor
    st, d = call("POST", "/api/dewi/kreator-requests", token, body)
    return (200 if st == 201 else st), d, (d or {}).get("request_code")


def buat_retur_produksi(token, nomor=None):
    """Retur produksi tanpa `po_item_id` — sengaja: dengan po_item_id, backend
    memeriksa batas `max_returnable` dari pengiriman ke buyer, dan gate tidak
    boleh menambah/mengurangi angka pengiriman sungguhan hanya untuk menguji nomor.
    """
    body = {"customer_name": MARK, "buyer_name": MARK, "notes": MARK,
            "return_reason": "Defect", "return_date": TGL,
            "items": [{"sku": MARK, "return_qty": 1, "defect_type": "Jahitan",
                       "repair_notes": MARK}]}
    if nomor is not None:
        body["return_number"] = nomor
    st, d = call("POST", "/api/production-returns", token, body)
    return (200 if st == 201 else st), d, (d or {}).get("return_number")


def _po_maklon_item(token):
    """(po_id, po_item_id) pertama yang bisa dipakai menguji nomor Permak.

    Memakai pintu yang SAMA dengan layar Permak (`/api/maklon-client/pos` +
    `/progress`) supaya kalau bentuk datanya berubah, gate ini ikut merah —
    bukan diam-diam melewati uji Permak.
    """
    _s, pos = call("GET", "/api/maklon-client/pos", token)
    rows = pos if isinstance(pos, list) else (pos or {}).get("items") or []
    for po in rows:
        pid = po.get("po_id") or po.get("id")
        if not pid:
            continue
        _s2, prog = call("GET", f"/api/maklon-client/pos/{pid}/progress", token)
        for it in ((prog or {}).get("items") or []):
            iid = it.get("po_item_id") or it.get("item_id") or it.get("id")
            if iid:
                return pid, iid
    return None, None


def buat_permak(token, po_id, po_item_id, nomor=None):
    body = {"po_id": po_id, "po_item_id": po_item_id, "qty": 1, "source": "good",
            "permak_type": "permak_sendiri", "problem_type": "jahitan",
            "cost_per_pcs": 0, "reason": MARK, "notes": MARK}
    if nomor is not None:
        body["permak_number"] = nomor
    st, d = call("POST", "/api/dewi/cmt-permak", token, body)
    no = ((d or {}).get("permak") or {}).get("permak_number") or (d or {}).get("permak_number")
    return (200 if st == 201 else st), d, no



# ═════════════════════ G1 & G7 — statik ═══════════════════════════════════════

def part_static():
    print(f"\n{B}[1] STATIK — yang ditandai 'ditegakkan' benar-benar menegakkan{X}")
    from data.doc_number_registry import DOC_NUMBER_REGISTRY
    enforced = [e["key"] for e in DOC_NUMBER_REGISTRY if e.get("policy_enforced")]
    missing = []
    for key in enforced:
        rel = WRITE_PATHS.get(key)
        if not rel:
            missing.append(f"{key} (jalur tulisnya tidak terdaftar di gate ini)")
            continue
        src = (ROOT / rel).read_text(encoding="utf-8")
        if "issue_number" not in src:
            missing.append(f"{key} → {rel} tidak memanggil issue_number")
    if enforced and not missing:
        ok("G1", f"{len(enforced)} jenis dokumen ber-'policy_enforced' benar-benar lewat "
                 "satu pintu issue_number", ", ".join(k.split(".")[-1] for k in enforced))
    else:
        bad("G1", "ada jenis dokumen yang MENGAKU ditegakkan tetapi jalur tulisnya tidak",
            "; ".join(missing) or "tidak ada jenis yang ditandai")

    # ── G9 (SESI #19): TIDAK ADA JENIS YANG STATUSNYA MENGGANTUNG ──────────────
    # Sebelum ini, 38 dari 49 jenis dokumen hanya "belum ditegakkan" tanpa keterangan:
    # pemilik tidak bisa membedakan "nanti bisa diatur" dari "memang mustahil diatur
    # karena dokumennya lahir tanpa manusia". Setiap entri sekarang WAJIB berlabel
    # tepat satu: `policy_enforced` · `auto_only` (+alasan) · `pending_enforce`.
    tanpa_label, tanpa_alasan, ganda = [], [], []
    for e in DOC_NUMBER_REGISTRY:
        label = [k for k in ("policy_enforced", "auto_only", "pending_enforce") if e.get(k)]
        if not label:
            tanpa_label.append(e["key"])
        elif len(label) > 1:
            ganda.append(f"{e['key']} ({'+'.join(label)})")
        if e.get("auto_only") and not str(e.get("alasan_otomatis") or "").strip():
            tanpa_alasan.append(e["key"])
    admin_src = (ROOT / "frontend/src/components/erp/DocNumberingModule.jsx").read_text(encoding="utf-8")
    m9 = []
    if tanpa_label:
        m9.append(f"jenis tanpa keterangan status: {tanpa_label[:6]}")
    if ganda:
        m9.append(f"jenis berlabel ganda: {ganda[:4]}")
    if tanpa_alasan:
        m9.append(f"'selalu otomatis' tanpa alasan: {tanpa_alasan[:6]}")
    if "auto_only" not in admin_src or "alasan_otomatis" not in admin_src:
        m9.append("layar admin tidak menampilkan ALASAN jenis yang selalu otomatis")
    if not m9:
        _en = sum(1 for e in DOC_NUMBER_REGISTRY if e.get("policy_enforced"))
        _ao = sum(1 for e in DOC_NUMBER_REGISTRY if e.get("auto_only"))
        _pe = sum(1 for e in DOC_NUMBER_REGISTRY if e.get("pending_enforce"))
        ok("G9", f"{len(DOC_NUMBER_REGISTRY)} jenis dokumen semuanya terklasifikasi & "
                 "layar menyebut alasannya",
           f"ditegakkan {_en} · selalu otomatis {_ao} (berlasan) · menunggu {_pe}")
    else:
        bad("G9", "status penomoran sebagian jenis masih menggantung", "; ".join(m9))

    form = (ROOT / "frontend/src/components/erp/KasbonStaffModule.jsx").read_text(encoding="utf-8")
    admin = (ROOT / "frontend/src/components/erp/DocNumberingModule.jsx").read_text(encoding="utf-8")
    shared = ROOT / "frontend/src/components/erp/docnum/DocNumberField.jsx"
    miss7 = []
    if not shared.exists():
        miss7.append("komponen bersama docnum/DocNumberField.jsx tidak ada")
    for probe in ("useDocNumberPolicy", PINJAMAN_KEY, "docNumberPayload"):
        if probe not in form:
            miss7.append(f"form kasbon tidak memakai {probe}")
    if "policy_enforced" not in admin or "docnum-mode-locked-" not in admin:
        miss7.append("layar admin tidak menyembunyikan pilihan mode untuk jenis "
                     "yang belum ditegakkan")
    # SESI #19 — setiap jenis yang ditegakkan HARUS punya kolom nomor di formnya.
    # SESI #27 — DAN daftar form itu harus LENGKAP: setiap kunci `policy_enforced`
    # wajib terdaftar di FORM_PATHS. Tanpa aturan ini, satu jenis bisa "ditegakkan"
    # tanpa satu pun layar yang bisa mengetik nomornya ⇒ owner memilih MANUAL dan
    # dokumennya menjadi MUSTAHIL dibuat (ditemukan pada 10 jenis sesi ini).
    from data.doc_number_registry import DOC_NUMBER_REGISTRY as _REG7
    tanpa_form = [e["key"] for e in _REG7
                  if e.get("policy_enforced") and e["key"] not in FORM_PATHS]
    if tanpa_form:
        miss7.append("jenis ditegakkan tanpa form ber-kolom nomor: "
                     + ", ".join(tanpa_form))
    # SESI #27 — DAN form itu harus BENAR-BENAR BISA DIBUKA dari UI. Ditemukan sesi ini:
    # `RahazaOrdersModule.jsx` (Order Penjualan) masih ada sebagai berkas dan membaca
    # kebijakan, tetapi menunya sudah dinonaktifkan (`prod-orders` → redirect ke PO
    # Internal) ⇒ "form"-nya tidak bisa dibuka siapa pun. Form yang tak terjangkau =
    # setelan MANUAL yang mustahil dipakai, persis cacat yang Fase G lawan.
    reg_src = (ROOT / "frontend/src/components/erp/moduleRegistry.js").read_text(encoding="utf-8")
    _imported_elsewhere = set()
    for _p in (ROOT / "frontend/src").rglob("*.jsx"):
        if "_archive" in str(_p):
            continue
        _txt = _p.read_text(encoding="utf-8", errors="ignore")
        # `import X from '../Foo'` MAUPUN `lazy(() => import('../Foo'))` — hub tab
        # memakai bentuk kedua (mis. hubs/HRExpenseTravelHub.jsx), jadi keduanya dihitung.
        for _m in re.finditer(r"import\(?\s*'[^']*/([A-Za-z0-9_]+)'", _txt):
            if _m.group(1) != _p.stem:
                _imported_elsewhere.add(_m.group(1))
        for _m in re.finditer(r"from\s+'[^']*/([A-Za-z0-9_]+)'", _txt):
            if _m.group(1) != _p.stem:
                _imported_elsewhere.add(_m.group(1))

    def _form_terjangkau(rel: str) -> bool:
        nama = Path(rel).stem
        alias = re.findall(rf"const\s+(\w+)\s*=\s*lazy\(\(\)\s*=>\s*import\('[^']*{nama}'\)", reg_src)
        for a in alias or [nama]:
            if re.search(rf"['\"][\w:.-]+['\"]\s*:\s*(?:withProps\(|makeModuleWithTab\(|makeRedirect\()?\s*{a}\b",
                         reg_src):
                return True
        return nama in _imported_elsewhere   # komponen anak dari modul yang dirutekan

    for key, rel in FORM_PATHS.items():
        p = ROOT / rel
        if not p.exists():
            miss7.append(f"{key}: form {rel} tidak ada")
            continue
        if not _form_terjangkau(rel):
            miss7.append(f"{key}: form {rel} TIDAK BISA DIBUKA dari UI "
                         "(tidak dirutekan di moduleRegistry & tidak dipakai komponen lain)")
            continue
        src = p.read_text(encoding="utf-8")
        # Form boleh memakai komponen bersama <DocNumberField> ATAU membaca
        # kebijakan sendiri (`/doc-number-policy`) — yang dilarang adalah form yang
        # tidak tahu-menahu soal kebijakan.
        pakai_komponen = "DocNumberField" in src and "useDocNumberPolicy" in src
        pakai_endpoint = "doc-number-policy" in src
        if not (pakai_komponen or pakai_endpoint):
            miss7.append(f"{key}: {rel} tidak membaca kebijakan penomoran")
        elif key not in src:
            miss7.append(f"{key}: {rel} membaca kebijakan tetapi bukan untuk kunci ini")
    if not miss7:
        ok("G7", "LAYAR memakai kebijakan: form kasbon membaca kebijakan & layar admin jujur",
           f"DocNumberField dipakai {len(FORM_PATHS)} form (kasbon · surat jalan gudang · PR · "
           "jurnal umum); toggle mode hanya untuk yang ditegakkan")
    else:
        bad("G7", "layar belum memakai kebijakan", "; ".join(miss7))

    # ── G12 (SESI #27): KATALOG WAJIB MEMUAT SETIAP SERI NOMOR YANG BENAR-BENAR
    # DIBUAT KODE. G9 hanya memeriksa entri yang SUDAH ada di katalog — ia tidak
    # bisa melihat seri yang tidak pernah didaftarkan. Diukur sesi ini: 5 seri
    # nomor hidup di kode tanpa satu pun baris di katalog (Retur Produksi RTN-,
    # Job Produksi, Job Cetak Barcode, Kode Supplier, dan seri WO yang bahkan
    # sudah mati) ⇒ owner tidak bisa melihat, apalagi mengatur, formatnya, dan
    # tidak ada yang menyatakan bahwa itu memang selalu otomatis.
    import re as _re
    pola_gen = _re.compile(
        r"gen_prefixed_number\(\s*db\s*,\s*['\"]([a-z_0-9]+)['\"]\s*,\s*['\"]([a-z_0-9]+)['\"]")
    target_terdaftar = set()
    for e in DOC_NUMBER_REGISTRY:
        coll = e.get("collection") or e["key"].split(".")[0]
        field = e.get("field") or e["key"].split(".", 1)[1]
        target_terdaftar.add((coll, field))
    tak_terdaftar = {}
    for berkas in (ROOT / "backend").rglob("*.py"):
        s = str(berkas)
        if any(x in s for x in ("_archive", "/tests/", "/migrations/", "/scripts/")):
            continue
        for m in pola_gen.finditer(berkas.read_text(encoding="utf-8", errors="ignore")):
            pasangan = (m.group(1), m.group(2))
            if pasangan in target_terdaftar or pasangan in EXEMPT_SERIES:
                continue
            tak_terdaftar.setdefault(pasangan, set()).add(s.replace(str(ROOT) + "/", ""))
    if not tak_terdaftar:
        ok("G12", "katalog penomoran memuat SEMUA seri nomor yang dibuat kode "
                  "(atau menyatakannya sebagai pengecualian beralasan)",
           f"{len(target_terdaftar)} target terdaftar · {len(EXEMPT_SERIES)} pengecualian "
           "beralasan: " + " · ".join(f"{c}.{f}" for c, f in EXEMPT_SERIES))
    else:
        bad("G12", "ada seri nomor yang hidup di kode tetapi tidak ada di katalog "
                   "Penomoran Dokumen (owner tak bisa melihat/mengaturnya)",
            "; ".join(f"{c}.{f} ← {', '.join(sorted(v))}"
                      for (c, f), v in sorted(tak_terdaftar.items())))


# ═════════════════════ G2..G6 — runtime ══════════════════════════════════════

def part_runtime(token, db):
    print(f"\n{B}[2] RUNTIME — mode ditegakkan pada dokumen sungguhan{X}")

    # ── G3: OTOMATIS ──
    set_mode(token, KASBON_KEY, "auto")
    st_typed, d_typed, _ = ajukan(token, "kasbon", nomor="BEBAS-999")
    st_auto, _d, no_auto = ajukan(token, "kasbon")
    _stp, pol = call("GET", f"/api/doc-number-policy?key={KASBON_KEY}", token)
    fmt_ok = bool(no_auto) and bool(re.match((pol or {}).get("pola") or "^$", no_auto or ""))
    if (st_typed == 400 and "tidak boleh diketik" in det(d_typed).lower()
            and st_auto == 200 and fmt_ok):
        ok("G3", "mode OTOMATIS menolak nomor ketikan & nomor yang lahir mengikuti FORMAT owner",
           f"ketikan HTTP {st_typed} · otomatis → {no_auto} (pola {(pol or {}).get('format')})")
    else:
        bad("G3", "mode otomatis tidak ditegakkan / nomor tidak mengikuti format",
            f"ketikan HTTP {st_typed} {det(d_typed)[:90]} · auto HTTP {st_auto} nomor={no_auto} "
            f"pola={(pol or {}).get('pola')}")

    # ── G2: MANUAL ──
    set_mode(token, KASBON_KEY, "manual")
    st_empty, d_empty, _ = ajukan(token, "kasbon")
    st_free, d_free, _ = ajukan(token, "kasbon", nomor="KASBON/BEBAS/9")
    good = f"KSB-{time.strftime('%Y%m')}-99001"
    st_good, _dg, no_good = ajukan(token, "kasbon", nomor=good)
    if (st_empty == 400 and "wajib diisi" in det(d_empty).lower()
            and st_free == 400 and "tidak mengikuti pola" in det(d_free).lower()
            and st_good == 200 and no_good == good):
        ok("G2", "mode MANUAL: kosong ditolak · pola bebas ditolak · pola benar diterima",
           f"kosong {st_empty} · bebas {st_free} · benar {st_good} → {no_good}")
    else:
        bad("G2", "mode manual tidak ditegakkan sebagaimana mestinya",
            f"kosong={st_empty} bebas={st_free} benar={st_good} nomor={no_good}")

    # ── G6: nomor kembar ──
    st_dup, d_dup, _ = ajukan(token, "kasbon", nomor=good)
    if st_dup == 409 and "sudah dipakai" in det(d_dup).lower():
        ok("G6", "nomor manual yang sudah dipakai DITOLAK (409) — nomor dokumen tetap unik",
           f"'{good}' → HTTP {st_dup}")
    else:
        bad("G6", "nomor manual kembar diterima ⇒ dua dokumen bernomor sama",
            f"HTTP {st_dup} {det(d_dup)[:120]}")

    # ── G5: Kasbon manual TIDAK menyeret Pinjaman ──
    st_pin, _dp, no_pin = ajukan(token, "pinjaman", cicilan=4)
    _stpp, polp = call("GET", f"/api/doc-number-policy?key={PINJAMAN_KEY}", token)
    if (st_pin == 200 and no_pin and no_pin.startswith("PIN-")
            and (polp or {}).get("mode") == "auto"):
        ok("G5", "Kasbon MANUAL tidak menyeret Pinjaman — dua jenis dokumen, dua kebijakan",
           f"pinjaman tetap otomatis → {no_pin}")
    else:
        bad("G5", "kebijakan kasbon & pinjaman masih tercampur",
            f"HTTP {st_pin} nomor={no_pin} mode_pinjaman={(polp or {}).get('mode')}")
    set_mode(token, KASBON_KEY, "auto")

    # ── G4: jenis yang BELUM ditegakkan ──
    # SESI #27 — kunci uji dipilih dari registry (lihat `_pick_pending`). Bila SUDAH
    # TIDAK ADA jenis yang menunggu, cabang ini dinyatakan terang-terangan dan gate
    # hanya menguji cabang "selalu otomatis" — TIDAK diam-diam lulus.
    st_mode = set_mode(token, NOT_ENFORCED_KEY, "manual") if NOT_ENFORCED_KEY else 400
    st_m, d_m = (call("PUT", "/api/admin/doc-numbering", token,
                      {"key": NOT_ENFORCED_KEY, "mode": "manual", "active": True})
                 if NOT_ENFORCED_KEY else (400, {"detail": "belum bisa diubah (tidak ada jenis menunggu)"}))
    st_fmt, _df = (call("PUT", "/api/admin/doc-numbering", token,
                        {"key": NOT_ENFORCED_KEY,
                         "format": NOT_ENFORCED_FORMAT, "active": True})
                   if NOT_ENFORCED_KEY else (200, {}))
    cfg = (db.doc_number_configs.find_one({"key": NOT_ENFORCED_KEY}, {"_id": 0}) or {}
           if NOT_ENFORCED_KEY else {})
    # SESI #19 — DUA jenis penolakan diuji terpisah supaya pesannya tidak boleh
    # tertukar: yang MENUNGGU disambungkan vs yang SELALU otomatis (lahir tanpa
    # manusia). Pesan seragam membuat pemilik menunggu sesuatu yang tidak akan datang.
    st_ao, d_ao = call("PUT", "/api/admin/doc-numbering", token,
                       {"key": AUTO_ONLY_KEY, "mode": "manual", "active": True})
    if (st_mode == 400 and st_m == 400 and "belum bisa diubah" in det(d_m).lower()
            and st_fmt == 200 and cfg.get("mode") in (None, "auto")
            and st_ao == 400 and "selalu bernomor otomatis" in det(d_ao).lower()):
        ok("G4", "penolakan mode JUJUR & terpisah: 'menunggu disambungkan' vs 'selalu "
                 "otomatis (beralasan)'; FORMAT tetap boleh diubah",
           f"jenis menunggu diuji: {NOT_ENFORCED_KEY or 'TIDAK ADA (semua sudah ditegakkan)'} "
           f"· menunggu HTTP {st_m} · selalu-otomatis HTTP {st_ao} · format HTTP {st_fmt}")
    else:
        bad("G4", "setelan mode diterima / pesannya tidak jujur",
            f"menunggu {st_m} {det(d_m)[:80]} · selalu-otomatis {st_ao} {det(d_ao)[:80]} "
            f"· format {st_fmt} · mode tersimpan={cfg.get('mode')}")


def part_runtime_baru(token, db):
    """SESI #19 — G8: tiga jenis baru ditegakkan pada dokumen SUNGGUHAN."""
    print(f"\n{B}[3] RUNTIME BARU — Surat Jalan Gudang · PR Pengadaan · Jurnal Umum{X}")
    akun = akun_jurnal(token)
    jenis = [
        ("Surat Jalan Gudang", "wh_delivery_notes.sj_number",
         lambda n=None: buat_sj(token, n),
         f"{SJ_TIPE}/{time.strftime('%Y/%m')}/9901", "KIRIM/BEBAS/9"),
        ("PR Pengadaan", "dewi_procurement_requests.request_number",
         lambda n=None: buat_pr(token, n),
         f"PR-{time.strftime('%Y%m')}-9901", "PR/BEBAS/9"),
        ("Jurnal Umum", "rahaza_journal_entries.je_number",
         lambda n=None: buat_je(token, akun, n),
         f"JE-{YMD}-9901", "JURNAL/BEBAS/9"),
    ]
    if len(akun) < 2:
        bad("G8", "tidak menemukan 2 akun leaf untuk jurnal uji — invarian tidak bisa diukur",
            f"akun terbaca: {akun}")
        return

    rusak, bukti = [], []
    for label, key, buat, nomor_benar, nomor_bebas in jenis:
        set_mode(token, key, "auto")
        st_typed, d_typed, _ = buat("BEBAS-999")
        st_auto, d_auto, no_auto = buat()
        _s, pol = call("GET", f"/api/doc-number-policy?key={key}", token)
        pola = (pol or {}).get("pola") or "^$"
        if st_typed != 400 or "tidak boleh diketik" not in det(d_typed).lower():
            rusak.append(f"{label}: mode OTOMATIS masih menerima nomor ketikan "
                         f"(HTTP {st_typed} {det(d_typed)[:70]})")
        if st_auto != 200 or not no_auto:
            rusak.append(f"{label}: pembuatan otomatis gagal (HTTP {st_auto} {det(d_auto)[:80]})")
        elif not re.match(pola, no_auto):
            rusak.append(f"{label}: nomor otomatis '{no_auto}' tidak mengikuti format owner "
                         f"({(pol or {}).get('format')})")

        set_mode(token, key, "manual")
        st_empty, d_empty, _ = buat()
        st_free, d_free, _ = buat(nomor_bebas)
        st_good, d_good, no_good = buat(nomor_benar)
        st_dup, d_dup, _ = buat(nomor_benar)
        if st_empty != 400 or "wajib diisi" not in det(d_empty).lower():
            rusak.append(f"{label}: mode MANUAL menerima nomor kosong (HTTP {st_empty})")
        if st_free != 400 or "tidak mengikuti pola" not in det(d_free).lower():
            rusak.append(f"{label}: mode MANUAL menerima nomor berpola bebas "
                         f"(HTTP {st_free} {det(d_free)[:70]})")
        if st_good != 200 or no_good != nomor_benar:
            rusak.append(f"{label}: nomor manual yang BENAR ditolak "
                         f"(HTTP {st_good} {det(d_good)[:90]})")
        if st_dup != 409:
            rusak.append(f"{label}: nomor manual kembar diterima (HTTP {st_dup} "
                         f"{det(d_dup)[:70]})")
        set_mode(token, key, "auto")
        bukti.append(f"{label}: otomatis→{no_auto} · manual→{no_good}")

    if not rusak:
        ok("G8", "3 jenis baru ditegakkan pada dokumen sungguhan: otomatis menolak ketikan, "
                 "manual menolak kosong/pola bebas/nomor kembar", " · ".join(bukti))
    else:
        bad("G8", "penomoran 3 jenis baru belum ditegakkan sebagaimana mestinya",
            "; ".join(rusak))


def part_runtime_batch3(token, db):
    """SESI #27 — G10: lima jenis SDM & Keuangan ditegakkan pada dokumen SUNGGUHAN."""
    print(f"\n{B}[4] RUNTIME BATCH-3 — Klaim Biaya · Perjalanan Dinas · Penyelesaian "
          f"Dinas · Order Penjualan · Transfer Bank{X}")
    ym = time.strftime("%Y%m")
    jenis = [
        ("Klaim Biaya", "rahaza_expense_claims.claim_number",
         lambda n=None: buat_klaim(token, n), f"EC-{ym}-9901", "KLAIM/BEBAS/9", True),
        ("Perjalanan Dinas", "employee_travel_requests.trip_number",
         lambda n=None: buat_dinas(token, n), f"TR-{ym}-9901", "DINAS/BEBAS/9", True),
        ("Penyelesaian Dinas", "employee_travel_settlements.settlement_number",
         lambda n=None: buat_penyelesaian(token, n), f"TS-{ym}-9901", "STL/BEBAS/9", True),
        # SESI #27 — "Order Penjualan" DICABUT dari uji ini: jenisnya diklasifikasi ulang
        # menjadi `auto_only` setelah terbukti layarnya sudah dinonaktifkan dari UI
        # (menu `prod-orders` diarahkan ke PO Internal). Mode MANUAL memang tidak bisa
        # disetel untuk jenis itu, jadi mengujinya di sini akan menguji hal yang salah.
        # Transfer bank: jalur "manual & benar" TIDAK dieksekusi (akan memposting GL).
        ("Transfer Bank", "rahaza_bank_transfers.ref_number",
         lambda n=None: buat_transfer(token, n), f"BT-{YMD}-9901", "TF/BEBAS/9", False),
    ]

    rusak, bukti = [], []
    for label, key, buat, nomor_benar, nomor_bebas, tulis_penuh in jenis:
        set_mode(token, key, "auto")
        st_typed, d_typed, _ = buat("BEBAS-999")
        if st_typed != 400 or "tidak boleh diketik" not in det(d_typed).lower():
            rusak.append(f"{label}: mode OTOMATIS masih menerima nomor ketikan "
                         f"(HTTP {st_typed} {det(d_typed)[:70]})")
        no_auto = None
        if tulis_penuh:
            st_auto, d_auto, no_auto = buat()
            _s, pol = call("GET", f"/api/doc-number-policy?key={key}", token)
            pola = (pol or {}).get("pola") or "^$"
            if st_auto != 200 or not no_auto:
                rusak.append(f"{label}: pembuatan otomatis gagal "
                             f"(HTTP {st_auto} {det(d_auto)[:90]})")
            elif not re.match(pola, no_auto):
                rusak.append(f"{label}: nomor otomatis '{no_auto}' tidak mengikuti format "
                             f"owner ({(pol or {}).get('format')})")

        set_mode(token, key, "manual")
        st_empty, d_empty, _ = buat()
        st_free, d_free, _ = buat(nomor_bebas)
        if st_empty != 400 or "wajib diisi" not in det(d_empty).lower():
            rusak.append(f"{label}: mode MANUAL menerima nomor kosong "
                         f"(HTTP {st_empty} {det(d_empty)[:70]})")
        if st_free != 400 or "tidak mengikuti pola" not in det(d_free).lower():
            rusak.append(f"{label}: mode MANUAL menerima nomor berpola bebas "
                         f"(HTTP {st_free} {det(d_free)[:70]})")
        no_good = "(tidak ditulis — akan memposting jurnal GL)"
        if tulis_penuh:
            st_good, d_good, no_good = buat(nomor_benar)
            st_dup, d_dup, _ = buat(nomor_benar)
            if st_good != 200 or no_good != nomor_benar:
                rusak.append(f"{label}: nomor manual yang BENAR ditolak "
                             f"(HTTP {st_good} {det(d_good)[:90]})")
            if st_dup != 409:
                rusak.append(f"{label}: nomor manual kembar diterima "
                             f"(HTTP {st_dup} {det(d_dup)[:70]})")
        set_mode(token, key, "auto")
        bukti.append(f"{label}: otomatis→{no_auto or '—'} · manual→{no_good}")

    if not rusak:
        ok("G10", "5 jenis batch-3 ditegakkan pada dokumen sungguhan (Transfer Bank: "
                  "jalur penolakan saja — menulisnya akan memposting jurnal GL)",
           " · ".join(bukti))
    else:
        bad("G10", "penomoran batch-3 belum ditegakkan sebagaimana mestinya",
            "; ".join(rusak))

    # ── G11: pintu pinjaman LEGACY benar-benar mati (bukan hanya disembunyikan) ──
    st_410, d_410 = call("POST", "/api/rahaza/hr/employee-loans/disburse", token,
                         {"employee_id": "uji", "loan_amount": 1,
                          "installment_amount": 1, "installment_count": 1})
    from data.doc_number_registry import DOC_NUMBER_REGISTRY as _R
    masih_terdaftar = [e["key"] for e in _R if e["key"].startswith("rahaza_employee_loans.")]
    pesan = det(d_410).lower()
    if st_410 == 410 and "kasbon" in pesan and not masih_terdaftar:
        ok("G11", "pintu pinjaman LEGACY mati (HTTP 410 + menyebut jalur yang benar) & "
                  "tidak lagi ditawarkan sebagai jenis dokumen yang bisa diatur",
           "POST /api/rahaza/hr/employee-loans/disburse → 410 · katalog penomoran bersih")
    else:
        bad("G11", "pinjaman legacy masih bisa menulis / masih ditawarkan di katalog",
            f"HTTP {st_410} {det(d_410)[:90]} · katalog={masih_terdaftar}")


def part_runtime_batch3b(token, db):
    """SESI #27 — G13: batch-3B ditegakkan pada dokumen SUNGGUHAN."""
    print(f"\n{B}[5] RUNTIME BATCH-3B — Permintaan Komponen · Permintaan Aksesoris · "
          f"Permintaan Kreator · Retur Produksi · Permak{X}")
    ymd2 = time.strftime("%y%m%d")
    po_id, po_item_id = _po_maklon_item(token)
    jenis = [
        ("Permintaan Komponen", "dewi_cmt_component_requests.request_code",
         lambda n=None: buat_permintaan_komponen(token, n),
         f"REQ-CMP-{ymd2}-901", "KOMPONEN/BEBAS/9"),
        ("Permintaan Aksesoris", "dewi_accessory_requests.request_code",
         lambda n=None: buat_permintaan_aksesoris(token, n),
         f"INT-REQ-{ymd2}-901", "AKSESORIS/BEBAS/9"),
        ("Permintaan Kreator", "dewi_kreator_requests.request_code",
         lambda n=None: buat_permintaan_kreator(token, n),
         f"REQ-KR-{ymd2}-901", "KREATOR/BEBAS/9"),
        ("Retur Produksi", "production_returns.return_number",
         lambda n=None: buat_retur_produksi(token, n),
         "RTN-9901", "RETUR/BEBAS/9"),
    ]
    if po_id and po_item_id:
        jenis.append(("Permak", "dewi_cmt_permak.permak_number",
                      lambda n=None: buat_permak(token, po_id, po_item_id, n),
                      f"PMK/{time.strftime('%Y/%m')}/9901", "PERMAK/BEBAS/9"))

    rusak, bukti = [], []
    if not (po_id and po_item_id):
        # TIDAK boleh "lewat dengan sopan": invarian yang tidak terukur harus MERAH,
        # kalau tidak, Permak akan tampak lulus padahal tak pernah diuji.
        rusak.append("Permak: tidak menemukan PO maklon beritem lewat "
                     "/api/maklon-client/pos → /progress — invarian nomor Permak "
                     "TIDAK TERUKUR (bukan lulus)")
    for label, key, buat, nomor_benar, nomor_bebas in jenis:
        set_mode(token, key, "auto")
        st_typed, d_typed, _ = buat("BEBAS-999")
        st_auto, d_auto, no_auto = buat()
        _s, pol = call("GET", f"/api/doc-number-policy?key={key}", token)
        pola = (pol or {}).get("pola") or "^$"
        if st_typed != 400 or "tidak boleh diketik" not in det(d_typed).lower():
            rusak.append(f"{label}: mode OTOMATIS masih menerima nomor ketikan "
                         f"(HTTP {st_typed} {det(d_typed)[:70]})")
        if st_auto != 200 or not no_auto:
            rusak.append(f"{label}: pembuatan otomatis gagal "
                         f"(HTTP {st_auto} {det(d_auto)[:90]})")
        elif not re.match(pola, no_auto):
            rusak.append(f"{label}: nomor otomatis '{no_auto}' tidak mengikuti format owner "
                         f"({(pol or {}).get('format')})")

        set_mode(token, key, "manual")
        st_empty, d_empty, _ = buat()
        st_free, d_free, _ = buat(nomor_bebas)
        st_good, d_good, no_good = buat(nomor_benar)
        st_dup, d_dup, _ = buat(nomor_benar)
        if st_empty != 400 or "wajib diisi" not in det(d_empty).lower():
            rusak.append(f"{label}: mode MANUAL menerima nomor kosong (HTTP {st_empty})")
        if st_free != 400 or "tidak mengikuti pola" not in det(d_free).lower():
            rusak.append(f"{label}: mode MANUAL menerima nomor berpola bebas "
                         f"(HTTP {st_free} {det(d_free)[:70]})")
        if st_good != 200 or no_good != nomor_benar:
            rusak.append(f"{label}: nomor manual yang BENAR ditolak "
                         f"(HTTP {st_good} {det(d_good)[:90]})")
        if st_dup != 409:
            rusak.append(f"{label}: nomor manual kembar diterima (HTTP {st_dup} "
                         f"{det(d_dup)[:70]})")
        set_mode(token, key, "auto")
        bukti.append(f"{label}: otomatis→{no_auto} · manual→{no_good}")

    if not rusak:
        ok("G13", f"{len(jenis)} jenis batch-3B ditegakkan pada dokumen sungguhan "
                  "(sebelumnya 3 di antaranya menerima nomor ketikan TANPA pemeriksaan "
                  "pola maupun nomor kembar)", " · ".join(bukti))
    else:
        bad("G13", "penomoran batch-3B belum ditegakkan sebagaimana mestinya",
            "; ".join(rusak))


def cleanup(db, token):
    n = db.dewi_kasbon_requests.delete_many({"purpose": MARK}).deleted_count
    n += db.dewi_kasbon_requests.delete_many({"reason": MARK}).deleted_count
    set_mode(token, KASBON_KEY, "auto")
    db.counters.delete_many({"_id": {"$regex": r"^autonum:dewi_kasbon_requests:request_number:"}})
    # SESI #19 — dokumen uji tiga jenis baru + counter-nya (counter disemai ulang dari
    # nomor tertinggi yang MASIH ada, jadi menghapusnya tidak menimbulkan nomor kembar).
    baru = db.wh_delivery_notes.delete_many({"notes": MARK}).deleted_count
    baru += db.dewi_procurement_requests.delete_many({"title": MARK}).deleted_count
    je_uji = [j.get("je_number") for j in db.rahaza_journal_entries.find({"memo": MARK}, {"je_number": 1})]
    baru += db.rahaza_journal_entries.delete_many({"memo": MARK}).deleted_count
    if je_uji:
        db.rahaza_journal_lines.delete_many({"je_number": {"$in": je_uji}})
    for coll, field in (("wh_delivery_notes", "sj_number"),
                        ("dewi_procurement_requests", "request_number"),
                        ("rahaza_journal_entries", "je_number")):
        db.counters.delete_many({"_id": {"$regex": rf"^autonum:{coll}:{field}:"}})
    for key in ("wh_delivery_notes.sj_number", "dewi_procurement_requests.request_number",
                "rahaza_journal_entries.je_number"):
        set_mode(token, key, "auto")

    # SESI #27 — dokumen uji batch-3. Semua ditandai MARK pada judul/keterangan.
    b3 = 0
    b3 += db.rahaza_expense_claims.delete_many({"title": MARK}).deleted_count
    b3 += db.employee_travel_settlements.delete_many({"notes": MARK}).deleted_count
    b3 += db.employee_travel_requests.delete_many({"destination": MARK}).deleted_count
    b3 += db.rahaza_orders.delete_many({"notes": MARK}).deleted_count
    for coll, field in (("rahaza_expense_claims", "claim_number"),
                        ("employee_travel_requests", "trip_number"),
                        ("employee_travel_settlements", "settlement_number"),
                        ("rahaza_orders", "order_number"),
                        ("rahaza_bank_transfers", "ref_number")):
        db.counters.delete_many({"_id": {"$regex": rf"^autonum:{coll}:{field}:"}})
    for key in ("rahaza_expense_claims.claim_number",
                "employee_travel_requests.trip_number",
                "employee_travel_settlements.settlement_number",
                "rahaza_orders.order_number",
                "rahaza_bank_transfers.ref_number"):
        set_mode(token, key, "auto")

    # SESI #27 — dokumen uji batch-3B (Produksi · Aksesoris · Marketing)
    b3 += db.dewi_cmt_component_requests.delete_many({"notes": MARK}).deleted_count
    b3 += db.dewi_accessory_requests.delete_many({"notes": MARK}).deleted_count
    b3 += db.dewi_kreator_requests.delete_many({"kreator_name": MARK}).deleted_count
    b3 += db.production_returns.delete_many({"customer_name": MARK}).deleted_count
    db.production_return_items.delete_many({"sku": MARK})
    permak_uji = [p.get("id") for p in db.dewi_cmt_permak.find({"reason": MARK}, {"id": 1})]
    b3 += db.dewi_cmt_permak.delete_many({"reason": MARK}).deleted_count
    if permak_uji:
        db.dewi_cmt_reworks.delete_many({"permak_id": {"$in": permak_uji}})
    for coll, field in (("dewi_cmt_component_requests", "request_code"),
                        ("dewi_accessory_requests", "request_code"),
                        ("dewi_kreator_requests", "request_code"),
                        ("production_returns", "return_number"),
                        ("dewi_cmt_permak", "permak_number")):
        db.counters.delete_many({"_id": {"$regex": rf"^autonum:{coll}:{field}:"}})
    for key in ("dewi_cmt_component_requests.request_code",
                "dewi_accessory_requests.request_code",
                "dewi_kreator_requests.request_code",
                "production_returns.return_number",
                "dewi_cmt_permak.permak_number"):
        set_mode(token, key, "auto")

    print(f"\n{Y}  bersih-bersih: {n} pengajuan kasbon + {baru} dokumen uji (SJ/PR/JE) + "
          f"{b3} dokumen uji batch-3 dihapus · semua mode dikembalikan ke otomatis{X}")


def main():
    print(f"{C}{B}FASE G (lanjutan) — setelan penomoran tidak boleh berbohong (INV-F25){X}")
    db = db_handle()
    part_static()
    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}){X}")
        return 2
    try:
        part_runtime(token, db)
        part_runtime_baru(token, db)
        part_runtime_batch3(token, db)
        part_runtime_batch3b(token, db)
    except Exception as e:  # noqa: BLE001
        bad("RUNTIME", "invarian runtime gagal dijalankan", str(e))
    finally:
        cleanup(db, token)
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian penomoran dokumen terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
