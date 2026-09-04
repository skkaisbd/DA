#!/usr/bin/env python3
"""Seed IDEMPOTEN — Master Supplier demo + daftar harga (Portal Pengadaan).

MENGAPA BERKAS INI ADA
----------------------
`scripts/bootstrap.sh` menyeed produksi, HR, maklon, marketing, dan aksesoris,
tetapi TIDAK PERNAH menyeed Master Supplier. Akibatnya pada environment yang
lahir dari bootstrap segar (`rahaza_suppliers` = 0 dokumen):

  · layar **Master Supplier**, **Penilaian Supplier**, dan **Analisis Belanja**
    semuanya kosong ("Belum ada data") — portal terlihat rusak padahal hanya
    tidak berisi;
  · alur **PR disetujui → Buat Purchase Order** MENTOK di UI: dialog "Buat
    Purchase Order" mewajibkan supplier dipilih dari master dan hanya bisa
    menampilkan pesan "Master Supplier masih kosong". Jadi langkah terakhir
    rantai pengadaan tidak bisa diselesaikan lewat layar.

Skrip ini menutup lubang data itu. Sifatnya:
  · IDEMPOTEN — supplier yang namanya sudah ada dilewati (backend menolak nama
    serupa lewat `name_key`, dan skrip ini memeriksa lebih dulu);
  · TIDAK menyentuh uang — hanya master supplier + daftar harga. Tidak membuat
    PO, penerimaan, jurnal, atau stok, jadi baseline gate (`verify_data_integrity`,
    baseline valuasi aksesoris, Buku Besar) tidak berubah;
  · daftar harga dipasang HANYA untuk material yang benar-benar ada di master
    (`rahaza_materials`), memakai satuan dasarnya, supaya konversi UOM sah.

Pakai:
    python3 /app/scripts/seed_procurement_suppliers_demo.py
    python3 /app/scripts/seed_procurement_suppliers_demo.py --cleanup   # buang data demo ini
"""
from __future__ import annotations

import os
import sys

import requests

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
CLEANUP = "--cleanup" in sys.argv

# Ditandai `source: "seed_demo"` supaya bisa dibersihkan tanpa menyentuh
# supplier yang diinput pengguna sungguhan.
SUPPLIERS = [
    {
        "code": "SUP-0001", "name": "PT Benang Jaya Abadi",
        "npwp": "01.234.567.8-091.000", "tax_type": "ppn",
        "address": "Jl. Industri Raya No. 12", "city": "Bandung", "province": "Jawa Barat",
        "postal_code": "40285", "phone": "022-7301234", "email": "sales@benangjaya.co.id",
        "payment_terms": "net30", "currency": "IDR", "lead_time_days": 7,
        "min_order_value": 5_000_000,
        "contacts": [{"name": "Hendra Susanto", "role": "Sales Manager",
                      "phone": "081234000101", "email": "hendra@benangjaya.co.id"}],
        "bank_accounts": [{"bank_name": "BCA", "account_number": "1234567890",
                           "account_name": "PT Benang Jaya Abadi"}],
        "notes": "Supplier utama benang & kain katun.",
        "categories": ["fabric", "yarn"],
    },
    {
        "code": "SUP-0002", "name": "CV Aksesoris Nusantara",
        "npwp": "02.345.678.9-012.000", "tax_type": "ppn",
        "address": "Jl. Pasar Baru No. 88", "city": "Jakarta Pusat", "province": "DKI Jakarta",
        "postal_code": "10710", "phone": "021-3451122", "email": "order@aksesorisnusantara.id",
        "payment_terms": "net14", "currency": "IDR", "lead_time_days": 3,
        "min_order_value": 1_000_000,
        "contacts": [{"name": "Rina Marlina", "role": "Admin Penjualan",
                      "phone": "081234000202", "email": "rina@aksesorisnusantara.id"}],
        "bank_accounts": [{"bank_name": "Mandiri", "account_number": "1440001234567",
                           "account_name": "CV Aksesoris Nusantara"}],
        "notes": "Kancing, label, hangtag, benang jahit.",
        "categories": ["accessory"],
    },
    {
        "code": "SUP-0003", "name": "PT Kain Sejahtera",
        "npwp": "03.456.789.0-123.000", "tax_type": "ppn",
        "address": "Kawasan Industri Blok C5", "city": "Tangerang", "province": "Banten",
        "postal_code": "15138", "phone": "021-5567788", "email": "cs@kainsejahtera.com",
        "payment_terms": "net45", "currency": "IDR", "lead_time_days": 14,
        "min_order_value": 10_000_000,
        "contacts": [{"name": "Bambang Prasetyo", "role": "Account Executive",
                      "phone": "081234000303", "email": "bambang@kainsejahtera.com"}],
        "bank_accounts": [{"bank_name": "BNI", "account_number": "0987654321",
                           "account_name": "PT Kain Sejahtera"}],
        "notes": "Kain jadi (jersey, fleece) — lead time lebih panjang, harga lebih murah.",
        "categories": ["fabric"],
    },
    {
        "code": "SUP-0004", "name": "UD Plastik Kemasan",
        "npwp": "", "tax_type": "non_ppn",
        "address": "Jl. Kemasan No. 5", "city": "Surabaya", "province": "Jawa Timur",
        "postal_code": "60175", "phone": "031-8801122", "email": "udplastikkemasan@gmail.com",
        "payment_terms": "cod", "currency": "IDR", "lead_time_days": 2,
        "min_order_value": 0,
        "contacts": [{"name": "Slamet Riyadi", "role": "Pemilik",
                      "phone": "081234000404", "email": ""}],
        "bank_accounts": [{"bank_name": "BRI", "account_number": "334455667788",
                           "account_name": "Slamet Riyadi"}],
        "notes": "Polybag & kardus. Non-PPN, bayar di tempat.",
        "categories": ["packaging"],
    },
]

# (kode supplier, jumlah material yang diberi harga, faktor harga terhadap HPP)
PRICE_PLAN = [("SUP-0001", 3, 1.00), ("SUP-0002", 3, 0.95), ("SUP-0003", 2, 1.08)]


def login() -> dict:
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def cleanup() -> int:
    from dotenv import load_dotenv
    from pymongo import MongoClient
    load_dotenv("/app/backend/.env")
    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = cli[os.environ.get("DB_NAME", "test_database")]
    codes = [s["code"] for s in SUPPLIERS]
    ids = [s["id"] for s in db.rahaza_suppliers.find(
        {"code": {"$in": codes}, "source": "seed_demo"}, {"_id": 0, "id": 1})]
    n_pl = db.rahaza_supplier_price_lists.delete_many({"supplier_id": {"$in": ids}}).deleted_count
    n_s = db.rahaza_suppliers.delete_many(
        {"code": {"$in": codes}, "source": "seed_demo"}).deleted_count
    cli.close()
    print(f"  dibersihkan: supplier={n_s} baris harga={n_pl}")
    return 0


def main() -> int:
    if CLEANUP:
        return cleanup()

    h = login()
    existing = requests.get(f"{BASE}/api/procurement/suppliers?limit=200", headers=h,
                            timeout=30).json()
    have = {(s.get("code") or "").upper() for s in (existing.get("items") or [])}
    have_names = {(s.get("name") or "").strip().lower() for s in (existing.get("items") or [])}

    created = {}
    for s in SUPPLIERS:
        if s["code"].upper() in have or s["name"].strip().lower() in have_names:
            print(f"  · {s['code']} {s['name']} sudah ada — dilewati")
            continue
        r = requests.post(f"{BASE}/api/procurement/suppliers", headers=h, json=s, timeout=30)
        if r.status_code not in (200, 201):
            print(f"  ! gagal {s['code']}: {r.status_code} {r.text[:140]}")
            continue
        d = r.json()
        created[s["code"]] = d["id"]
        print(f"  + {d.get('code')} {d.get('name')}")

    # Tandai sebagai data seed supaya --cleanup bisa membedakannya dari input asli.
    if created:
        from dotenv import load_dotenv
        from pymongo import MongoClient
        load_dotenv("/app/backend/.env")
        cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[os.environ.get("DB_NAME", "test_database")]
        db.rahaza_suppliers.update_many({"id": {"$in": list(created.values())}},
                                        {"$set": {"source": "seed_demo"}})
        cli.close()

    # Peta kode → id untuk SEMUA supplier (termasuk yang sudah ada sebelumnya).
    allsup = requests.get(f"{BASE}/api/procurement/suppliers?limit=200", headers=h,
                          timeout=30).json().get("items") or []
    by_code = {(s.get("code") or "").upper(): s["id"] for s in allsup}

    # Daftar harga — hanya untuk material yang benar-benar ada di master.
    mats = requests.get(f"{BASE}/api/rahaza/materials", headers=h, timeout=30).json()
    mats = mats if isinstance(mats, list) else (mats.get("items") or [])
    mats = [m for m in mats if m.get("active") is not False and m.get("id")]
    if not mats:
        print("  ! master material kosong — daftar harga dilewati")
        return 0

    n_price = 0
    for code, count, mult in PRICE_PLAN:
        sid = by_code.get(code)
        if not sid:
            continue
        cur = requests.get(f"{BASE}/api/procurement/suppliers/{sid}", headers=h,
                           timeout=30).json().get("price_list") or []
        if cur:
            print(f"  · daftar harga {code} sudah ada ({len(cur)} baris) — dilewati")
            continue
        for m in mats[:count]:
            base_price = float(m.get("standard_cost") or m.get("unit_cost") or 0) or 10_000.0
            body = {"material_id": m["id"], "uom": m.get("base_uom") or m.get("unit") or "pcs",
                    "price": round(base_price * mult, 2), "moq": 10,
                    "lead_time_days": 7, "currency": "IDR",
                    "notes": "Harga demo hasil seeding."}
            r = requests.post(f"{BASE}/api/procurement/suppliers/{sid}/price-list",
                              headers=h, json=body, timeout=30)
            if r.status_code in (200, 201):
                n_price += 1
            else:
                print(f"    ! harga {code}/{m.get('code')}: {r.status_code} {r.text[:120]}")
    print(f"  daftar harga dibuat: {n_price} baris")

    total = (requests.get(f"{BASE}/api/procurement/suppliers?limit=1", headers=h, timeout=30)
             .json().get("pagination", {}).get("total"))
    print(f"SELESAI — master supplier sekarang: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
