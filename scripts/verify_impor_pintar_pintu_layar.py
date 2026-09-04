"""INV-F45 (sesi #40) — IMPOR PINTAR PUNYA PINTU DI LAYAR + PENCAIRAN VOID TIDAK MENGUNCI.

Dua cacat yang gate ini kunci supaya tidak lahir lagi:

1. **Langkah 1 layar Impor Data pernah KOSONG.** Daftar jenis disaring per KELOMPOK
   (`group_key === groupKey`), tetapi tidak ada satu pun tempat yang MENGISI
   `groupKey` — pemilih kelompoknya tidak pernah dirender. Hasilnya layar
   menjawab "0 dari 22 jenis data" saat dibuka, dan satu-satunya jalan adalah
   mengetik kata kunci. Deteksi otomatis (`POST /detect`) juga hidup di backend
   tapi TIDAK dipanggil dari layar mana pun — fitur tanpa pintu = fitur yang
   tidak ada.
2. **Pencairan yang jurnalnya sudah di-void tetap terkunci.** Pesan penolakannya
   menyuruh "void jurnalnya dulu di Portal Finance", tetapi pemeriksanya hanya
   melihat ADA/TIDAK `je_id` — jadi sesudah void pun pencairan salah-input tidak
   bisa diperbaiki maupun dihapus. Jalan buntu yang tidak pernah berbunyi.

Skrip ini MEMBERSIHKAN artefaknya sendiri.
"""
from __future__ import annotations

import io
import os
import re
import sys

import requests

BASE = os.environ.get("BASE") or "http://localhost:8001"
WIZ = "/app/frontend/src/components/erp/marketing/DataImportWizard.jsx"
SAMPLES = "/app/samples/marketplace_2026"

OK, FAIL = [], []


def check(code, cond, detail=""):
    if cond:
        OK.append(code)
        print(f"  \033[92m✓ {code}\033[0m {detail}")
    else:
        FAIL.append((code, detail))
        print(f"  \033[91m✗ {code}\033[0m {detail}")


def login(email, pw):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw},
                      timeout=30).json()
    return {"Authorization": f"Bearer {r.get('access_token') or r.get('token')}"}


def main() -> int:
    src = open(WIZ, encoding="utf-8").read()

    print("\n\033[1mA — PINTU DI LAYAR (langkah 1 tidak boleh kosong lagi)\033[0m")
    check("F45-1", "/source-groups" in src,
          "layar memanggil GET /source-groups (pemilih kelompok)")
    check("F45-2", re.search(r"axios\.post\(`\$\{BASE\}/detect`", src) is not None,
          "layar memanggil POST /detect (usulan jenis dari isi berkas)")
    check("F45-3", "setGroupKey(" in src,
          "`groupKey` benar-benar diisi dari layar (bukan selalu kosong)")
    for tid in ("import-group-", "import-detect-panel", "import-detect-result",
                "import-detect-use-", "import-group-back", "import-toggle-deprecated"):
        check(f"F45-4:{tid}", tid in src, f"data-testid `{tid}` ada di layar")
    # state yang dideklarasikan tapi tidak pernah dipakai = fitur hilang senyap
    for name in ("groups", "detectRes", "showDeprecated"):
        used = len(re.findall(rf"\b{name}\b", src))
        check(f"F45-5:{name}", used >= 3, f"`{name}` dipakai {used}× (bukan state mati)")

    admin = login("admin@garment.com", "Admin@123")
    fin = login("finance@dewiaditya.id", "Dewi@123")

    print("\n\033[1mB — KONTRAK BACKEND: setiap jenis punya kelompok yang benar-benar ada\033[0m")
    g = requests.get(f"{BASE}/api/marketing/data-import/source-groups",
                     headers=admin, timeout=60).json()
    t = requests.get(f"{BASE}/api/marketing/data-import/source-types",
                     headers=admin, timeout=60).json()
    groups = g.get("groups") or []
    types = t.get("source_types") or []
    gkeys = {x.get("key") for x in groups}
    check("F45-6", len(groups) >= 5 and len(types) >= 10,
          f"{len(groups)} kelompok · {len(types)} jenis data")
    orphan = [x.get("key") for x in types if x.get("group_key") not in gkeys]
    check("F45-7", not orphan,
          "semua jenis punya `group_key` yang ada di daftar kelompok"
          if not orphan else f"jenis tanpa kelompok: {orphan}")
    empty = [x.get("key") for x in groups
             if not [y for y in types if y.get("group_key") == x.get("key")]]
    check("F45-8", not empty,
          "tidak ada kelompok kosong (kartu yang diklik selalu berisi)"
          if not empty else f"kelompok kosong: {empty}")

    print("\n\033[1mC — DETEKSI: usulan berperingkat + jumlah baris yang JUJUR\033[0m")
    with open(os.path.join(SAMPLES, "order_pesanan_shopee.xlsx"), "rb") as fh:
        raw = fh.read()
    d = requests.post(f"{BASE}/api/marketing/data-import/detect", headers=admin,
                      files={"file": ("order_pesanan_shopee.xlsx", io.BytesIO(raw))},
                      timeout=180).json()
    best = d.get("best") or {}
    check("F45-9", best.get("source_type") == "marketplace_orders" and d.get("row_count") > 0,
          f"ekspor pesanan Shopee → usulan {best.get('source_type')} "
          f"({d.get('row_count')} baris, platform {(d.get('platform') or {}).get('platform')})")
    check("F45-10", (best.get("required_hit") == best.get("required_total")
                     and best.get("mapped_columns") > 0),
          f"usulan membawa BUKTI: {best.get('mapped_columns')}/{best.get('total_columns')} "
          f"kolom cocok · wajib {best.get('required_hit')}/{best.get('required_total')}")
    with open(os.path.join(SAMPLES, "retur_refund_shopee.xls"), "rb") as fh:
        raw0 = fh.read()
    d0 = requests.post(f"{BASE}/api/marketing/data-import/detect", headers=admin,
                       files={"file": ("retur_refund_shopee.xls", io.BytesIO(raw0))},
                       timeout=180).json()
    check("F45-11", d0.get("row_count") == 0 and len(d0.get("headers") or []) > 0,
          "berkas tanpa baris data dilaporkan `row_count=0` (layar memperingatkan "
          "SEBELUM unggah), bukan diam-diam dianggap siap")

    print("\n\033[1mD — PENCAIRAN: jurnal POSTED mengunci, jurnal VOID melepas\033[0m")
    acc = next((a for a in requests.get(f"{BASE}/api/marketing/accounts", headers=admin,
                                        timeout=60).json()
                if (a.get("coa_cash_code") or "").strip()
                and (a.get("coa_revenue_code") or "").strip()), None)
    if not acc:
        check("F45-12", False, "tidak ada toko dengan tautan COA — tidak bisa diukur")
        return 1
    body = {"account_id": acc["id"], "platform": acc.get("platform"),
            "settlement_id": "SET-INVF45", "settlement_date": "2026-08-20",
            "period_from": "2026-08-01", "period_to": "2026-08-15",
            "gross_sales": 10_000_000, "platform_commission": 1_000_000,
            "net_payout": 9_000_000}
    r = requests.post(f"{BASE}/api/marketing/settlements", headers=fin, json=body, timeout=60)
    if r.status_code == 409:                      # sisa run sebelumnya
        rows = requests.get(f"{BASE}/api/marketing/settlements", headers=fin,
                            timeout=60).json()
        old = next((x for x in (rows.get("data") or rows.get("items") or [])
                    if x.get("settlement_id") == "SET-INVF45"), None)
        if old:
            requests.delete(f"{BASE}/api/marketing/settlements/{old['id']}",
                            headers=fin, timeout=60)
        r = requests.post(f"{BASE}/api/marketing/settlements", headers=fin, json=body,
                          timeout=60)
    if r.status_code != 200:
        check("F45-12", False, f"tidak bisa membuat pencairan uji: {r.status_code} "
                               f"{r.text[:200]}")
        return 1
    sid = r.json()["data"]["id"]
    je = requests.post(f"{BASE}/api/marketing/settlements/{sid}/journal", headers=fin,
                       timeout=60)
    check("F45-12", je.status_code == 200, f"jurnal draft terbit ({je.status_code})")
    je_id = (je.json() or {}).get("je_id")
    posted = requests.post(f"{BASE}/api/marketing/settlements/{sid}/post", headers=fin,
                           timeout=60)
    check("F45-13", posted.status_code == 200, f"jurnal diposting ({posted.status_code})")

    dele = requests.delete(f"{BASE}/api/marketing/settlements/{sid}", headers=fin, timeout=60)
    check("F45-14", dele.status_code == 400,
          f"selama jurnalnya HIDUP, pencairan tidak bisa dihapus ({dele.status_code})")
    upd = requests.put(f"{BASE}/api/marketing/settlements/{sid}", headers=fin, json=body,
                       timeout=60)
    check("F45-15", upd.status_code == 400,
          f"selama jurnalnya HIDUP, angkanya tidak bisa diubah ({upd.status_code})")

    void = requests.post(f"{BASE}/api/rahaza/journals/{je_id}/void", headers=fin,
                         json={"reason": "gate INV-F45"}, timeout=60)
    check("F45-16", void.status_code == 200, f"jurnal di-void ({void.status_code})")
    upd2 = requests.put(f"{BASE}/api/marketing/settlements/{sid}",
                        headers=fin, json={**body, "net_payout": 9_100_000}, timeout=60)
    check("F45-17", upd2.status_code == 200,
          f"sesudah void, angka pencairan BISA diperbaiki ({upd2.status_code})")
    if upd2.status_code == 200:
        det = requests.get(f"{BASE}/api/marketing/settlements/{sid}", headers=fin,
                           timeout=60).json()
        check("F45-18", not (det.get("data") or {}).get("je_id")
              and (det.get("can") or {}).get("edit") is True,
              "tautan jurnal yang sudah void DILEPAS & tombol sunting hidup lagi")
    dele2 = requests.delete(f"{BASE}/api/marketing/settlements/{sid}", headers=fin, timeout=60)
    check("F45-19", dele2.status_code == 200,
          f"sesudah void, pencairan salah-input bisa dihapus ({dele2.status_code})")
    if dele2.status_code != 200:
        requests.delete(f"{BASE}/api/marketing/settlements/{sid}", headers=fin, timeout=60)

    # Artefak terakhir: jurnal yang sudah di-void. Void MENGELUARKAN nilainya dari
    # buku besar (`_unmirror_lines`), tetapi dokumennya tetap ada — kalau dibiarkan,
    # setiap kali gate ini jalan daftar jurnal bertambah satu baris uji.
    if je_id:
        from pymongo import MongoClient
        env = dict(l.split("=", 1) for l in open("/app/backend/.env") if "=" in l)
        db = MongoClient(env["MONGO_URL"].strip().strip('"'))[
            env["DB_NAME"].strip().strip('"')]
        db.rahaza_journal_entries.delete_many({"source_ref": "SET-INVF45"})
        left = db.rahaza_journal_entries.count_documents({"source_ref": "SET-INVF45"})
        check("F45-20", left == 0, "artefak jurnal uji dibersihkan")

    print("\n" + "─" * 70)
    if FAIL:
        print(f"\033[91m\033[1mGAGAL: {len(FAIL)}\033[0m — {[c for c, _ in FAIL]}")
        return 1
    print(f"\033[92m\033[1mVERDICT HIJAU — {len(OK)} invarian INV-F45 terjaga\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
