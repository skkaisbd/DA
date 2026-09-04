# 🛡️ ENGINEERING GUARDRAILS & BUG POSTMORTEM — CV. Dewi Aditya ERP

> **WAJIB DIBACA** sebelum memulai development baru ATAU memperbaiki bug.
> Dokumen ini merangkum **cacat produksi nyata** yang berulang di codebase ini, **akar masalah
> pada proses development** (banyak disebabkan agent sebelumnya berasumsi/halusinasi tanpa
> verifikasi ke kode yang sebenarnya), **mitigasi**, dan **pola fix standar**.
>
> Jika kamu agent/developer baru: jalankan **Checklist Wajib** (Bagian 6) untuk setiap perubahan.

Terakhir diperbarui: 2026-06-08 (setelah audit Gudang/Maklon/Marketing + P2P + RBAC).

---

## 1. Ringkasan Eksekutif

Aplikasi ini adalah ERP multi-portal besar (React 19 + FastAPI + MongoDB) dengan **250+ modul**
dan **ratusan endpoint**. Bug yang ditemukan **bukan** karena framework/infra, melainkan karena
**desync antar lapisan** yang menumpuk dari waktu ke waktu:

```
   SEED  ──tulis──►  KOLEKSI MONGO  ◄──baca──  API (FastAPI)  ──JSON──►  FRONTEND (React)
    │                     │                          │                        │
 nama koleksi        nama field                 bentuk respons            import & parsing
   SALAH               SALAH                     {items} vs []              hilang/keliru
```

Setiap "sambungan" di atas adalah titik gagal. Agent sebelumnya kerap **menebak** nama koleksi/
field/bentuk respons alih-alih **memverifikasi ke pembaca sebenarnya**, sehingga:
tabel kosong, "Rp 0", crash layar putih, 404/500, dan dashboard tidak nyambung — meskipun
"testing agent lulus". **Lulus tes ≠ benar** jika tes tidak menjalankan jalur data/render nyata.

---

## 2. Klasifikasi Akar Masalah (dengan contoh NYATA dari codebase)

### 🔴 RC-1 — Drift Nama Koleksi (Seed menulis ke koleksi yang TIDAK dibaca API)
**Gejala:** Tabel/dashboard kosong padahal "seed sukses".
**Penyebab:** Seed menulis ke koleksi lama/keliru; API membaca koleksi lain (kanonik).
**Contoh nyata yang ditemukan & diperbaiki:**
| Seed menulis ke (SALAH) | API membaca dari (BENAR) | Modul terdampak |
|---|---|---|
| `dewi_maklon_orders` | `dewi_maklon_pos` | Maklon Dashboard/PO |
| `marketing_livehost_hosts` | `marketing_livehosts` | Live Host |
| `rahaza_inventory_stock` / `rahaza_inventory_materials` | `rahaza_material_stock` / `rahaza_materials` | Stok Gudang |
| `rahaza_journals` (legacy) | `rahaza_journal_entries` | Jurnal Keuangan |
| `rahaza_budget_entries` (legacy) | `rahaza_budget_items` | Budget |

**Dampak:** Tinggi — seluruh modul tampak "mati" walau data ada di DB (di koleksi salah).
**Mitigasi:** SEBELUM menulis seed, `grep` koleksi yang benar dari **handler API yang membaca**:
```bash
# Cari endpoint pembaca, lalu koleksi yang dibacanya
grep -rn "db\.[a-z_]*\.find" routes/<file_yang_dipanggil_frontend>.py
```
**Fix pattern:** Selalu tulis ke koleksi yang dibaca API. Jika ada koleksi duplikat (legacy +
kanonik), **pilih kanonik** dan jangan tulis ke legacy.

---

### 🔴 RC-2 — Drift Nama Field / Skema (dokumen ada, tapi field yang dibaca app beda)
**Gejala:** Data muncul tapi kolom tertentu kosong / "Rp 0" / nama kosong.
**Penyebab:** Seed/dokumen memakai field A; app membaca field B.
**Contoh nyata:**
| Field di seed (SALAH/legacy) | Field yang dibaca app (BENAR) | Akibat |
|---|---|---|
| `rate` / `salary` | `base_rate` | Gaji "Rp 0" di payslip |
| `tax_id` | `npwp_number`, `tax_ptkp` | Pajak kosong |
| `company_name` (klien maklon) | `name` | Nama klien kosong di dashboard |
| (tidak ada) | `creator_code`, `name` (KOL) | **500 KeyError** di leaderboard |
| `qty` (saja) | `available_quantity`, `ownership`, `inventory_category` | Fulfillment "available" kosong |

**Dampak:** Sedang–Tinggi (termasuk **500 crash** jika app meng-`dict['key']` field yang hilang).
**Mitigasi:** Baca **model Pydantic** + **endpoint create** untuk skema kanonik; jangan reka field.
**Fix pattern:**
- Di seed: gunakan field kanonik persis (lihat `…/dewi_maklon_*`, `…/marketing_*`, dst).
- Di endpoint: pakai `dict.get('key', default)` untuk field yang mungkin tidak ada (lihat fix
  `marketing_kol_ops.py` — `creator.get('creator_code', '')`).

---

### 🔴 RC-3 — Drift Bentuk Respons API (`{items:[...]}` vs Array vs `{data:{rows}}`)
**Gejala:** Tabel kosong walau endpoint mengembalikan 200 + data.
**Penyebab:** Banyak GET membungkus hasil `{"items": [...], "total": N}`, tapi sebagian komponen
React lama mengharapkan `Array` langsung atau `data.rows`.
**Contoh:** 10+ modul HR/Gudang dinormalisasi agar membaca `data.items` dengan fallback.
**Dampak:** Tinggi (tabel kosong tanpa error).
**Mitigasi/Fix pattern (frontend):** parsing defensif yang konsisten:
```js
const res = await axios.get(`${API}/...`);
const rows = Array.isArray(res.data) ? res.data
           : (res.data.items || res.data.data || res.data.rows || []);
```
Selalu **cek bentuk respons aktual** (curl endpoint) sebelum menulis parsing.

---

### 🔴 RC-4 — Import JSX/komponen hilang → crash layar putih
**Gejala:** Layar putih / ErrorBoundary saat membuka modul.
**Penyebab:** Komponen/ikon dipakai di JSX tapi tidak di-import (mis. `Tabs`, `ScanLine`).
**Dampak:** Kritis (modul tidak bisa dibuka sama sekali).
**Mitigasi:** Setelah edit komponen, lakukan smoke render (screenshot) + cek console error.
**Fix pattern:** Pastikan setiap simbol JSX punya import. Cek cepat:
```bash
# contoh: pastikan ikon lucide-react yang dipakai sudah di-import
grep -n "ScanLine\|Tabs" src/components/erp/<File>.jsx
```

---

### 🔴 RC-5 — Desync Counter SSOT (insert dokumen bernomor tanpa menaikkan counter)
**Gejala:** Aksi "create" via app **500 / duplicate key** (`E11000`).
**Penyebab:** Seed meng-insert dokumen bernomor (mis. `GR-00001`, `AP-202606-0001`) **langsung**,
padahal app meng-generate nomor via `utils/counters.next_counter()` (SSOT di koleksi `counters`).
Karena counter tidak dinaikkan, nomor berikutnya yang digenerate app **bentrok** dengan nomor seed
(ada **unique index** pada `receipt_number` / `invoice_number`).
**Contoh nyata:** `create-gr` & `ap-invoices/from-gr` 500 setelah seeding.
**Dampak:** Kritis (memblok alur P2P / pembuatan dokumen).
**Mitigasi/Fix pattern:** Setelah seeding dokumen bernomor, **sinkronkan counter** ke ≥ nomor
tertinggi yang di-seed:
```python
await db.counters.update_one({"_id": "gr_number"},
    {"$max": {"seq": 300}, "$setOnInsert": {"namespace": "generic"}}, upsert=True)
```
Alternatif: gunakan **prefix berbeda** untuk nomor seed agar tidak pernah bentrok dengan format
counter app (mis. maklon pakai `INV-MKL-2026-...` sementara seed pakai `INV-MKL-202604-...`).

---

### 🔴 RC-6 — Linkage antar-dokumen putus (cocok via field yang kosong)
**Gejala:** Status tidak berubah / agregasi salah walau langkah "sukses".
**Penyebab:** Propagasi mencocokkan dokumen via field yang bisa kosong.
**Contoh nyata:** Propagasi qty **GR→PO** mencocokkan via `material_id`. Tapi PO turunan PR
(item free-form) **tidak punya** `material_id` → PO tidak pernah jadi `fully_received`; juga
`it["material_id"]` melempar **KeyError**.
**Dampak:** Tinggi (siklus P2P macet di tengah jalan).
**Mitigasi/Fix pattern:** Gunakan **kunci yang dijamin ada** sebagai primer, fallback ke sekunder:
```python
# GR item membawa po_item_id → cocokkan via po_item_id dulu, baru material_id
if pid and pid in received_by_item:   add = received_by_item[pid]
elif mid and mid in received_by_mid:  add = received_by_mid[mid]
```
Selalu pakai `.get()` saat membaca field yang mungkin tidak ada.

---

### 🔴 RC-7 — Bug semantik/kalkulasi (membandingkan satuan yang tidak setara)
**Gejala:** Status/angka "selalu salah" walau data benar.
**Contoh nyata:** **3-Way Match** selalu `over` karena membandingkan **total invoice (termasuk
PPN 11%)** vs **nilai barang diterima (tanpa PPN)** → selisih ~11% > toleransi.
**Dampak:** Sedang (mengaburkan validitas data).
**Mitigasi/Fix pattern:** Bandingkan **apple-to-apple** (pra-pajak vs pra-pajak); pisahkan basis
perhitungan dari nilai tampilan:
```python
# matching pakai subtotal pra-pajak; display tetap total termasuk pajak
value_variance = total_invoiced_subtotal - total_received_value
```

---

### 🟠 RC-8 — Nilai hardcoded (tanggal "2025", angka magic)
**Gejala:** Dashboard "bulan ini/YTD" kosong; label tahun salah (mis. `ORD/2025/...`).
**Penyebab:** Tanggal/identifier ditulis literal alih-alih dari periode dinamis.
**Mitigasi/Fix pattern:** Seed memakai periode dinamis (`PERIOD`, `_sd(mi, d)`, `_period_ym(mi)`),
**bukan** literal `"2025-..."`. Dashboard yang memfilter "current month" baru akan terisi.

---

### 🟠 RC-9 — Otorisasi tidak lengkap / tidak satu sumber kebenaran (RBAC)
**Gejala:** User role kustom tidak melihat portal apa pun, atau bisa membuka portal terlarang
lewat deep-link `?portal=...`.
**Penyebab:** Peta `PORTAL_ACCESS` backend usang (hanya superadmin/admin, id portal salah
`marketing` vs `toko`) dan **tidak sinkron** dengan peta role di frontend; deep-link tidak dijaga.
**Mitigasi/Fix pattern:**
- **Satu sumber kebenaran** role→portal: frontend `components/erp/portalAccess.js` ↔ backend
  `routes/shared.py PORTAL_ACCESS`. Keduanya harus identik (id portal sama dengan kunci `portalNav.js`).
- Jaga **semua jalur** masuk portal: login, restore-session, hashchange, pemilihan portal,
  dan **deep-link URL** (`canAccessPortal(role, portalId)`).

---

### 🔴 RC-10 — "False-positive testing" (klaim sukses tanpa verifikasi jalur nyata)
**Gejala:** Laporan "lulus", tapi aplikasi nyata crash/kosong.
**Penyebab:** Tes tidak menjalankan **render UI nyata** atau **jalur data nyata** (mis. hanya cek
status 200, bukan isi; atau memakai data mock; atau tidak login sebagai role yang relevan).
**Mitigasi:** Lihat **Definition of Done** (Bagian 7). Verifikasi harus menyentuh data + render.

---

## 3. Mengapa Ini Terjadi (Akar pada PROSES, bukan sekadar kode)

1. **Berasumsi, bukan memverifikasi.** Nama koleksi/field/bentuk respons **ditebak** dari ingatan
   model, bukan dibaca dari handler API/komponen pembaca yang sebenarnya. → RC-1, RC-2, RC-3.
2. **Tidak ada satu sumber kebenaran.** Ada koleksi & model duplikat (legacy vs kanonik), peta
   akses ganda (FE vs BE). Perubahan di satu sisi tidak diikuti sisi lain. → RC-1, RC-9.
3. **Seed tidak divalidasi terhadap kontrak API.** Seed dianggap "benar" begitu tidak error,
   tanpa memanggil endpoint pembaca untuk memastikan data muncul. → RC-1, RC-2, RC-5.
4. **Tidak menghormati invarian sistem** (SSOT counter, unique index, linkage key). → RC-5, RC-6.
5. **Verifikasi dangkal.** "Status 200" / "service running" dianggap selesai, padahal tabel kosong
   atau render crash. → RC-10.

---

## 4. PRINSIP INTI (pegang ini saat coding)

1. **Verify, don't assume.** Sebelum menulis seed/parsing/integrasi, **baca pembaca sebenarnya**
   (grep handler API, model, komponen). Jangan pernah menebak nama koleksi/field.
2. **Satu sumber kebenaran.** Untuk skema, akses role, format nomor — satu definisi, dipakai semua.
3. **Seed mengikuti kontrak API, bukan sebaliknya.** Koleksi & field yang ditulis seed = persis
   yang dibaca API.
4. **Hormati invarian.** Counter SSOT, unique index, kunci linkage, dan tipe (ObjectId, datetime UTC).
5. **Defensif di batas sistem.** `.get()` untuk field opsional; parsing respons defensif di FE.
6. **Bandingkan setara.** Untuk kalkulasi (pajak/qty/nilai), pastikan basis perbandingan sama.
7. **DoD = data + render terbukti**, bukan "200 OK" atau "service up".

---

## 5. POLA FIX STANDAR (siap pakai)

**(A) Verifikasi koleksi yang dibaca endpoint sebelum seed**
```bash
# 1) endpoint apa yang dipanggil komponen frontend?
grep -oE "/api/[a-zA-Z0-9_/{}.$-]+" src/components/erp/<Modul>.jsx | sort -u
# 2) handler-nya membaca koleksi apa?
grep -rn "db\.[a-z_]*\.find\|db\.[a-z_]*\.aggregate" routes/<handler>.py
```

**(B) Probe pasca-seed (deteksi tabel kosong / 404 / 500)** — pola GET-sweep:
```bash
API=$(grep REACT_APP_BACKEND_URL frontend/.env | cut -d= -f2); TOKEN=...; 
for p in /api/.../a /api/.../b; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$API$p" -H "Authorization: Bearer $TOKEN");
  n=$(curl -s "$API$p" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d if isinstance(d,list) else d.get('items',[])))");
  echo "[$code] $p -> $n";
done
```

**(C) Parsing respons FE defensif** — lihat RC-3.

**(D) Sinkronisasi counter SSOT pasca-seed** — lihat RC-5.

**(E) Linkage by guaranteed key (`po_item_id` dulu)** — lihat RC-6.

**(F) Upsert idempoten by natural key (mis. user by email)**
```python
await db.users.update_one(
    {"email": email},
    {"$set": {"name": name, "role": role, "status": "active"},
     "$setOnInsert": {"id": _uid(), "email": email,
                      "password": hash_password("Dewi@123"), "created_at": _now()}},
    upsert=True)
```

**(G) MongoDB:** jangan kembalikan dokumen mentah (ObjectId tidak JSON-serializable). Pakai
`{"_id": 0}` saat find atau serializer model. `datetime.now(timezone.utc)`, **bukan** `utcnow()`.

---

## 6. ✅ CHECKLIST WAJIB (jalankan sesuai jenis pekerjaan)

### Saat MENULIS / MENGUBAH SEED
- [ ] Sudah `grep` koleksi **yang dibaca API** (bukan asumsi). (RC-1)
- [ ] Field dokumen = field kanonik yang dibaca app/model. (RC-2)
- [ ] Tanggal/periode **dinamis** (`_sd`, `_period_ym`), bukan literal tahun. (RC-8)
- [ ] Dokumen bernomor: **counter SSOT disinkronkan** & tidak bentrok unique index. (RC-5)
- [ ] Linkage antar dokumen memakai kunci yang dijamin ada. (RC-6)
- [ ] Idempoten (re-run seed tidak menggandakan / merusak). (RC-5, RC-F)
- [ ] **Probe GET-sweep** setelah seed → semua endkoleksi terkait non-kosong. (RC-10)

### Saat MENULIS / MENGUBAH FRONTEND
- [ ] Cek **bentuk respons aktual** via curl; parsing defensif `items/data/rows/array`. (RC-3)
- [ ] Semua simbol JSX/ikon ter-import. (RC-4)
- [ ] Setiap elemen interaktif/teks penting punya `data-testid` (kebab-case).
- [ ] Smoke render (screenshot) + console bersih dari error.
- [ ] Tidak memakai `// eslint-disable react-hooks/set-state-in-effect` (membuat build CRA gagal).
      Perbaiki dengan memindah `setState` ke async IIFE dalam `useEffect`.

### Saat INTEGRASI PIHAK KE-3 / AUTH
- [ ] Gunakan `integration_expert` SEBELUM menulis kode (LLM, payment, auth, storage, dst).
- [ ] Auth: reuse `hash_password` dari `auth.py`; field password = **`password`** (bukan `password_hash`).
- [ ] Kredensial dari `.env` saja; tidak ada nilai hardcoded.

### Saat RBAC / OTORISASI
- [ ] `portalAccess.js` (FE) ↔ `shared.py PORTAL_ACCESS` (BE) **identik** (id portal sama). (RC-9)
- [ ] Semua jalur masuk portal dijaga: login, restore, hashchange, select, **deep-link URL**.
- [ ] Tambah/ubah user uji → perbarui `/app/memory/test_credentials.md`.

### Saat MEMPERBAIKI BUG
- [ ] **Reproduksi dulu** (curl/screenshot) sebelum menebak fix.
- [ ] Telusuri rantai kegagalan penuh (seed→koleksi→API→FE) sampai akar.
- [ ] Cek apakah masuk salah satu RC-1..RC-10 di atas.
- [ ] Setelah fix: tulis/regression test di `/app/backend/tests/`, jalankan, verifikasi.

---

## 7. Definition of Done (DoD) — kapan boleh klaim "selesai"

Sebuah perubahan **belum** selesai sampai SEMUA ini terbukti:
1. **Jalur data nyata** terverifikasi: endpoint mengembalikan data benar (curl cek **isi**, bukan
   hanya status 200).
2. **Render nyata** terverifikasi: layar terbuka tanpa crash, tabel terisi, tidak ada "Rp 0" yang
   tak disengaja (screenshot / testing_agent).
3. **Regression test** ada di `/app/backend/tests/` dan **lulus** (lihat contoh di Bagian 8).
4. **Tidak ada regresi** pada flow terkait.
5. Memori diperbarui: `CHANGELOG.md`, `PRD.md`, dan bila ada kredensial → `test_credentials.md`.

> ⚠️ "Testing agent lulus" saja **tidak cukup** bila tes tidak menyentuh data+render nyata (RC-10).
> Untuk fitur kritis, drive **end-to-end** seperti pengguna (login, navigasi, aksi, verifikasi hasil).

---

## 8. Registry Bug yang Sudah Diperbaiki (rujukan + status)

| # | Bug | RC | File fix | Status | Test |
|---|---|---|---|---|---|
| 1 | Import JSX hilang (`Tabs`, `ScanLine`) → crash | RC-4 | `HREmployeeModule.jsx`, dll | FIXED | screenshot |
| 2 | Tabel HR kosong (`{items}` vs Array) | RC-3 | 10+ modul HR/Gudang | FIXED | iter.19/20 |
| 3 | Gaji "Rp 0" (`base_rate`/`npwp_number`) | RC-2 | `production_seed_full.py` | FIXED | iter.19 |
| 4 | Announcement POST 500 (`created_by` None) | RC-2 | `announcements.py` | FIXED | iter.19 |
| 5 | Maklon dashboard tulis `dewi_maklon_orders` (baca `dewi_maklon_pos`) | RC-1 | `production_seed_full.py` §51 | FIXED | iter.21, `test_iteration_21_*` |
| 6 | Nama klien maklon kosong (`company_name` vs `name`) | RC-2 | seed §34 | FIXED | iter.21 |
| 7 | Live Host kosong (`marketing_livehost_hosts` vs `marketing_livehosts`) | RC-1 | seed §36 | FIXED | iter.21 |
| 8 | KOL Leaderboard **500** (`creator_code`/`name` hilang) | RC-2 | `marketing_kol_ops.py`, seed §38 | FIXED | iter.21 |
| 9 | Stok Gudang kosong (`rahaza_inventory_*` vs `rahaza_material_*`) | RC-1 | seed §50 | FIXED | iter.21 |
| 10 | Target Bulanan "Rp 0" (`marketing_sales_data` kosong) | RC-2 | seed §52 | FIXED | iter.21 |
| 11 | Fulfillment "available" kosong (skema FG stock) | RC-2 | seed §50 (FG stock) | FIXED | iter.21 |
| 12 | `create-gr`/AP **500** duplicate key (counter desync) | RC-5 | seed §53 (sync `counters`) | FIXED | `test_p2p_full_cycle.py` |
| 13 | Qty GR→PO tidak propagate utk PO turunan PR | RC-6 | `warehouse.py`, `rahaza_po.py` | FIXED | `test_p2p_full_cycle.py` |
| 14 | 3-Way Match selalu "over" (basis PPN) | RC-7 | `rahaza_ap_from_gr.py` | FIXED | `test_p2p_full_cycle.py` |
| 15 | AP Aging kosong (status `approved` vs filter `sent`) | RC-2 | seed §53 (status `sent`) | FIXED | iter.22 |
| 16 | `PORTAL_ACCESS` usang + deep-link tak dijaga | RC-9 | `shared.py`, `portalAccess.js`, `App.js` | FIXED | `test_rbac_multiuser.py`, iter.22 |
| 17 | Tanggal hardcoded "2025" di seed | RC-8 | `production_seed_full.py` (periode dinamis) | SEBAGIAN (beberapa label lama tersisa) | — |

**Tes regresi tersedia:** `/app/backend/tests/`
- `test_iteration_21_warehouse_maklon_marketing.py` (Gudang/Maklon/Marketing)
- `test_p2p_full_cycle.py` (siklus penuh PR→PO→GR→AP→bayar→3-way)
- `test_p2p_create_po.py` (PR→PO)
- `test_rbac_multiuser.py` (separasi role/portal)
Jalankan: `REACT_APP_BACKEND_URL=<url> python -m pytest tests/<file> -q`
> Catatan: endpoint `/api/auth/login` di-rate-limit ~10 req/60s per IP — beri jeda antar batch tes.

---

## 9. Daftar "Known Pitfalls" Spesifik Codebase Ini

- **Koleksi kanonik (HATI-HATI nama):** `rahaza_journal_entries` (BUKAN `rahaza_journals`),
  `rahaza_budget_items` (BUKAN `rahaza_budget_entries`), `dewi_maklon_pos` (BUKAN `_orders`),
  `marketing_livehosts` (BUKAN `marketing_livehost_hosts`), `rahaza_material_stock`/`rahaza_materials`
  (BUKAN `rahaza_inventory_*`).
- **Bentuk respons:** banyak GET → `{"items":[...], "total":N}`. Selalu parsing defensif.
- **WMS legacy bridge:** `warehouse.py` diarsipkan; rute aktif lewat `wms_legacy.py`
  (`/api/wms/legacy/*`) yang membaca `warehouse_locations/stock/receiving/putaway`.
- **Counter SSOT:** `utils/counters.next_counter()` + koleksi `counters`. Sinkronkan setelah seed
  dokumen bernomor (GR `gr_number`/generic, AP `ap_invoice_{yymm}`/rahaza, PO `po_number_{tgl}`/rahaza).
- **Auth:** field hash bernama **`password`**; gunakan `hash_password` dari `auth.py`. Login &
  `/auth/me` mengembalikan `portals` dari `get_user_portals`.
- **Lint React:** JANGAN pakai `// eslint-disable react-hooks/set-state-in-effect` (mematahkan build CRA).
- **Env/Infra:** backend di `0.0.0.0:8001`, semua rute backend ber-prefix `/api`; FE pakai
  `REACT_APP_BACKEND_URL`; jangan ubah `.env` protected keys.

---

## 10. Cara Pakai Dokumen Ini

1. **Mulai task baru / fix bug** → baca Bagian 2 (cari RC yang cocok) + jalankan Checklist (Bagian 6).
2. **Sebelum klaim selesai** → penuhi DoD (Bagian 7) + perbarui CHANGELOG/PRD/test_credentials.
3. **Menemukan bug baru berpola** → tambahkan ke Registry (Bagian 8) & (bila perlu) RC baru di Bagian 2.

> Tujuan akhir: setiap "sambungan" (seed↔koleksi↔API↔FE↔akses) **diverifikasi**, bukan diasumsikan.

---

## 11. Ekosistem Guardrails 3-Lapis (v1.0.0 — 2026-07-05)

SOP lengkap: **`memory/BUGHUNT_SOP.md`** · Kontrak kualitas AI: **`memory/AI_QUALITY_CONTRACT.md`**
Runner tunggal: `bash scripts/guard.sh bughunt` (preflight + gate + meta). Detail: `test_reports/guardrails/*.json`.

- **PRA-dev (statik):** `preflight/verify_fe_be_contract.py` (INV-CONTRACT-01), `guardrails/verify_static_antipatterns.py` (INV-STATIC-01), `guardrails/verify_auth_coverage.py` (INV-AUTH-01).
- **POST-dev (runtime):** `verify_data_integrity.py`, `verify_state_machine.py`, `verify_concurrency.py` (CC1 live + CC2 regresi statik), `guardrails/verify_adversarial_5xx.py`, `guardrails/verify_rbac_idor.py` (INV-RBAC-01).
- **META:** `meta/mutation_test.py` (fault-injection → gate harus KILL), `meta/effort_gate.py` (minimal working quality AI).

Prinsip kalibrasi: **turunkan false-positive dulu, baru naikkan tingkat blok** — gate berisik melatih orang mengabaikan merah.

## 12. Temuan TERBUKA dari sapuan guardrail v1 (belum diperbaiki — kebijakan deteksi & lapor)

> Fix yang SUDAH dikerjakan: (1) **RC-5 systemic** — 10 titik penomoran `count_documents()+1`
> pada koleksi unique-indexed diganti `gen_prefixed_number` (atomic), dikunci regresi CC2.
> (2) **BUG-RBAC-1 DITUTUP** — read-guard otorisasi ditegakkan via `shared.require_portal` /
> `require_portal_dep()` (SSOT `check_portal_access`) sebagai router-level dependency pada
> rahaza_journals, rahaza_finance, rahaza_coa, rahaza_payroll_runs + auth pada `/api/financial-recap`.
> INV-RBAC-01 kini **BLOCKING** di `gate.sh` (verifikasi: operator→403, unauth→401, superadmin→200).

Temuan berikut DILAPORKAN untuk triase (bukan auto-fix; butuh keputusan produk/keamanan):

| ID | Kelas | Status | Detail | Bukti |
|---|---|---|---|---|
| **BUG-RBAC-1** | Broken access control (OWASP #1) | ✅ **FIXED** | Role `operator` kini **403** pada `/rahaza/journals`, `/ar-invoices`, `/ap-invoices`, `/payroll-runs`, `/coa/accounts`; `/financial-recap` kini butuh auth. Ditegakkan via `require_portal` (SSOT `check_portal_access`). | `test_reports/guardrails/INV-RBAC-01.json` (0 HIGH) |
| **BUG-AUTH-1** | Endpoint tanpa auth | ⚠️ terbuka | `routes/wms_legacy.py` (~20 endpoint) & ~11 endpoint referensi marketing/procurement (`/types`, `/reasons`, `/categories`) dapat diakses **tanpa token** (kini diklasifikasi MED/advisory — bukan data sensitif). | `test_reports/guardrails/INV-AUTH-01.json`, `INV-RBAC-01.json` (MED) |
| **BUG-DUP-1** | Duplicate route | ⚠️ terbuka | 7 pasangan `(METHOD, path)` didefinisikan >1x → hanya definisi TERAKHIR aktif. | `test_reports/guardrails/INV-CONTRACT-01.json` |
| **BUG-5XX-2** | Adversarial surface | ⚠️ terbuka | ~249 titik koersi numerik input klien (`float(body…)`) tanpa guard eksplisit (subset berisiko 500). | `test_reports/guardrails/INV-STATIC-01.json` (SA-5XX) |

**Rekomendasi urutan perbaikan berikutnya:** BUG-AUTH-1 (beri auth wms_legacy) → BUG-DUP-1 → BUG-5XX-2 (audit per-endpoint).
Perluasan RBAC ke sub-router finance lain (rahaza_ar_360, rahaza_bank_recon, rahaza_hpp, dst) = pekerjaan lanjutan memakai pola `require_portal_dep` yang sama.
