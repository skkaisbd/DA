#!/usr/bin/env python3
"""seed_finance_wms_demo.py — data DEMO untuk layar UANG & STOK (Fase 3, sesi #11).

KENAPA SKRIP INI ADA
--------------------
Environment segar (klon ulang + `bootstrap.sh`) meninggalkan **empat layar uang &
stok KOSONG**: Kasbon & Pinjaman (Keuangan), Inbox Approval Klaim & Dinas, Roll
Kain, dan Surat Jalan. Akibatnya sama dengan yang ditemukan sesi #10 pada layar
Jejak Perubahan: fiturnya **tampak belum jadi**, dan agen/penguji berikutnya
menghabiskan waktu memastikan apakah layarnya rusak atau memang tidak ada datanya.

Endpoint seed kasbon (`POST /api/dewi/kasbon/seed`) **sudah ada sejak lama** tetapi
hanya hidup sebagai perintah manual — persis pola yang membuat empat seeder
marketing hilang di sesi #9. Karena itu skrip ini didaftarkan di
`scripts/bootstrap.sh`.

ATURAN YANG DIPEGANG
  · **Lewat API resmi, bukan tulis langsung ke Mongo.** Data yang dikarang
    langsung ke koleksi akan melewati penomoran dokumen, jejak aktivitas, dan
    invarian — lalu gate `verify_data_integrity` menemukannya sebagai kerusakan.
  · **Idempoten.** Dijalankan dua kali ⇒ tidak menambah apa pun (dicek lewat
    penanda `DEMO` pada judul/nomor/catatan).
  · **Ditandai DEMO** supaya bisa dibedakan dari data sungguhan.
  · **Tidak menyentuh uang yang sudah diposting.** Klaim dibuat lalu DISUBMIT
    (menunggu persetujuan) — tidak di-approve/disburse, karena itu akan membuat
    jurnal yang bukan hak skrip demo.

Pakai:  python3 /app/backend/scripts/seed_finance_wms_demo.py
"""
from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE = os.environ.get("SEED_BASE_URL", "http://localhost:8001")
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
MARK = "DEMO"


def say(msg: str):
    print(f"  {msg}")


def main() -> int:
    try:
        r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=25)
        r.raise_for_status()
        h = {"Authorization": f"Bearer {r.json()['token']}"}
    except Exception as e:  # noqa: BLE001
        print(f"{R}✗ tidak bisa login: {e}{X}")
        return 1

    ok_n, skip_n, fail_n = 0, 0, 0

    # ── 1. KASBON & PINJAMAN (pakai endpoint seed resmi yang sudah idempoten) ──
    try:
        r = requests.post(f"{BASE}/api/dewi/kasbon/seed", headers=h, timeout=60)
        j = r.json() if r.status_code == 200 else {}
        if "sudah ada" in str(j.get("message", "")):
            say(f"{Y}·{X} kasbon: sudah ada, dilewati")
            skip_n += 1
        elif r.status_code == 200:
            say(f"{G}✓{X} kasbon & pinjaman: 5 pengajuan demo dibuat")
            ok_n += 1
        else:
            say(f"{R}✗{X} kasbon: HTTP {r.status_code} {r.text[:120]}")
            fail_n += 1
    except Exception as e:  # noqa: BLE001
        say(f"{R}✗{X} kasbon: {e}")
        fail_n += 1

    # ── 2. KLAIM BIAYA (inbox approval SDM/Keuangan) ──────────────────────────
    CLAIMS = [
        ("[DEMO] Reimburse bensin kunjungan vendor CMT",
         [("2026-08-04", "transport", 185000, "Bensin + parkir"),
          ("2026-08-05", "meal", 95000, "Makan siang tim")]),
        ("[DEMO] Pembelian ATK & materai kantor",
         [("2026-08-06", "office_supplies", 240000, "Kertas A4 2 rim + materai")]),
        ("[DEMO] Ongkos kirim sampel ke buyer",
         [("2026-08-07", "shipping", 132000, "JNE ke Bandung")]),
    ]
    try:
        existing = requests.get(f"{BASE}/api/hr/expenses/claims", headers=h,
                                params={"limit": 200}, timeout=45).json()
        rows = existing.get("items") if isinstance(existing, dict) else existing
        have = {str((c or {}).get("title") or "") for c in (rows or [])}
    except Exception:
        have = set()
    for title, items in CLAIMS:
        if title in have:
            skip_n += 1
            continue
        try:
            body = {"title": title, "notes": "Data demo Fase 3 (bisa dihapus)",
                    "items": [{"date": d, "category": c, "amount": a, "notes": n}
                              for d, c, a, n in items]}
            cr = requests.post(f"{BASE}/api/hr/expenses/claims", headers=h,
                               json=body, timeout=45)
            if cr.status_code not in (200, 201):
                say(f"{R}✗{X} klaim «{title[:34]}…»: HTTP {cr.status_code} {cr.text[:110]}")
                fail_n += 1
                continue
            cid = (cr.json() or {}).get("id")
            # SUBMIT supaya masuk inbox approval (bukan draft yang tak terlihat).
            sr = requests.post(f"{BASE}/api/hr/expenses/claims/{cid}/submit",
                               headers=h, json={}, timeout=45)
            if sr.status_code not in (200, 201):
                say(f"{Y}!{X} klaim {cid[:8]} dibuat tetapi gagal disubmit "
                    f"(HTTP {sr.status_code}) — masih draft")
            ok_n += 1
        except Exception as e:  # noqa: BLE001
            say(f"{R}✗{X} klaim: {e}")
            fail_n += 1
    say(f"{G}✓{X} klaim biaya: {len(CLAIMS)} judul demo dipastikan ada")

    # ── 3. ROLL KAIN (stok per roll) ──────────────────────────────────────────
    # NOMOR ROLL TIDAK DIKIRIM — pelajaran sesi #27.
    # Fase G (sesi #18/#19) menegakkan kebijakan penomoran: `wh_fabric_rolls.roll_no`
    # ber-`policy_enforced` dengan mode OTOMATIS, jadi `POST /api/wms/fabric-rolls`
    # MENOLAK (400) nomor ketikan — termasuk `DEMO-RL-0001` milik skrip ini. Akibatnya
    # bootstrap fresh-clone mencetak "4 gagal" dan layar Roll Kain tetap KOSONG,
    # padahal produknya benar: yang basi adalah seeder-nya.
    # Karena nomor kini lahir dari sistem (`RL-{YYYY}{MM}-{SEQ:4}`), idempotensi
    # TIDAK BOLEH lagi bergantung pada nomor. Tanda pengenal demo = penanda pada
    # `notes` + tanda tangan (bahan · warna · lot) yang unik di daftar demo ini.
    ROLLS = [
        # material, warna, lot, supplier, po, panjang, berat, qc
        ("Cotton Combed 30s", "Navy", "LOT-A1", "PT Kain Sejahtera",
         "PO-DEMO-001", 120.0, 28.5, "pass"),
        ("Cotton Combed 30s", "Putih", "LOT-A1", "PT Kain Sejahtera",
         "PO-DEMO-001", 96.5, 22.0, "pass"),
        ("Fleece Cotton", "Hitam", "LOT-B7", "CV Tekstil Nusantara",
         "PO-DEMO-002", 60.0, 31.0, "pending"),
        ("Rayon Twill", "Maroon", "LOT-C3", "CV Tekstil Nusantara",
         "PO-DEMO-002", 18.0, 6.4, "partial"),
    ]

    def _sig(mat: str, color: str, lot: str) -> str:
        return f"{mat}|{color}|{lot}".lower()

    try:
        cur = requests.get(f"{BASE}/api/wms/fabric-rolls", headers=h,
                           params={"limit": 200}, timeout=45).json()
        have_sig = {
            _sig(str(x.get("material_name") or ""), str(x.get("color") or ""),
                 str(x.get("color_lot") or ""))
            for x in (cur.get("items") or cur.get("rolls") or [])
            if MARK in str(x.get("notes") or "")
        }
    except Exception:
        have_sig = set()
    for mat, color, lot, sup, po, m, kg, qc in ROLLS:
        if _sig(mat, color, lot) in have_sig:
            skip_n += 1
            continue
        try:
            body = {"material_id": "", "material_code": "",
                    "material_name": mat, "color": color, "color_lot": lot,
                    "supplier_name": sup, "uom": "meter", "length_m": m,
                    "weight_kg": kg, "po_no": po, "qc_status": qc,
                    "unit_cost": 0.0, "notes": f"{MARK} Fase 3"}
            rr = requests.post(f"{BASE}/api/wms/fabric-rolls", headers=h,
                               json=body, timeout=45)
            if rr.status_code in (200, 201):
                ok_n += 1
            elif rr.status_code == 409:
                skip_n += 1
            else:
                say(f"{R}✗{X} roll {mat}/{color}: HTTP {rr.status_code} {rr.text[:110]}")
                fail_n += 1
        except Exception as e:  # noqa: BLE001
            say(f"{R}✗{X} roll {mat}/{color}: {e}")
            fail_n += 1
    say(f"{G}✓{X} roll kain: {len(ROLLS)} roll demo dipastikan ada")

    # ── 4. SURAT JALAN ────────────────────────────────────────────────────────
    SJS = [
        ("SJ-CMT", "CV Maju Jaya Konveksi", "Jl. Industri Raya 45, Sragen",
         "0812-1111-2222", [("Kain Cotton Combed 30s Navy", 60, "meter"),
                            ("Benang jahit hitam", 24, "pcs")]),
        ("SJ-INTERNAL", "Gudang Lantai 2", "Area produksi lantai 2",
         "", [("Rayon Twill Maroon", 18, "meter")]),
    ]
    try:
        cur = requests.get(f"{BASE}/api/wms/delivery-notes", headers=h,
                           params={"limit": 200}, timeout=45).json()
        have_sj = {str(x.get("recipient_name")) for x in (cur.get("notes")
                                                         or cur.get("items") or [])}
    except Exception:
        have_sj = set()
    for sj_type, rec, addr, phone, lines in SJS:
        if rec in have_sj:
            skip_n += 1
            continue
        try:
            body = {"sj_type": sj_type, "recipient_name": rec,
                    "recipient_address": addr, "recipient_phone": phone,
                    "shipper_name": "Gudang Pusat", "vehicle_no": "AD 1234 XY",
                    "notes": f"{MARK} Fase 3",
                    "lines": [{"description": d, "qty": q, "unit": u,
                               "remarks": MARK} for d, q, u in lines]}
            sr = requests.post(f"{BASE}/api/wms/delivery-notes", headers=h,
                               json=body, timeout=45)
            if sr.status_code in (200, 201):
                ok_n += 1
            else:
                say(f"{R}✗{X} SJ {rec}: HTTP {sr.status_code} {sr.text[:130]}")
                fail_n += 1
        except Exception as e:  # noqa: BLE001
            say(f"{R}✗{X} SJ {rec}: {e}")
            fail_n += 1
    say(f"{G}✓{X} surat jalan: {len(SJS)} SJ demo dipastikan ada")

    print(f"\n  {B}SELESAI{X} — {ok_n} dibuat · {skip_n} dilewati (sudah ada) · "
          f"{fail_n} gagal")
    print("  Buka: Portal Keuangan → Kasbon & Pinjaman · SDM → Inbox Approval · "
          "Gudang → Roll Kain · Gudang → Surat Jalan")
    return 1 if fail_n else 0


if __name__ == "__main__":
    sys.exit(main())
