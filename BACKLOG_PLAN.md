# 📋 BACKLOG PLAN — Handoff Sesi Berikutnya
### ERP Garment CV. Dewi Aditya

> ## ✅ STATUS 2026-07-21 — SEMUA ITEM BACKLOG FORMAL SELESAI (dokumen ini ditutup/arsip)
> Diselesaikan & terverifikasi pada sesi 2026-07-21 (detail: `memory/CHANGELOG.md`):
> - **ITEM 1 [P1] CRUD Edit/Hapus Manajemen CMT** — SELESAI. Backend `vendor_portal.py` (PUT/DELETE partners+accounts, soft/hard delete, invariants I-VP-1..5) + FE `VendorAccountsAdminModule.jsx`. testing_agent: backend 19/19, FE ~95%, 0 bug.
> - **ITEM 2 [P2] Format Angka Rupiah Global** — SELESAI (bug parsing). SSOT baru `backend/utils/money.py` + FE `lib/format.js parseIDNumber`. `marketing_import._convert_value` diperbaiki. 14/14 unit test.
> - **ITEM 3.1 [P2] WS-G6 dead-code cleanup** — SELESAI. Orphan `post_wip_to_fg_on_wo_complete` dihapus + test idempoten `tests/test_wip_to_fg_on_job_complete.py` PASS.
> - **ITEM 3.2 [P3] WS-F dokumentasi** — SELESAI. `/app/ARCHITECTURE.md` (Domain Registry lintas-domain).
>
> Isi di bawah = **arsip acceptance-criteria** (referensi historis). Tidak ada item terbuka lagi.


> **Versi:** 2.0.0  •  **Terakhir audit-grounded:** 2026-07-16
> **Status pemeliharaan:** Aktif — di-refresh setiap akhir sesi.
> **Prasyarat baca dulu:** `/app/memory/PREVIEW_STABLE_MODE.md`,
> `/app/memory/GUIDELINE_CMT_FLOW.md`, `/app/memory/test_credentials.md`.
>
> **Anti-halusinasi.** Semua nomor baris & path di dokumen ini sudah diverifikasi ke
> kode nyata pada tanggal audit di atas. Kalau menemukan diskrepansi antara dokumen
> ini dan kode, **jangan patch kode agar cocok dengan dokumen**; catat diskrepansi
> di §7 Change Log dan verifikasi ke user sebelum bergerak. Presedensi bukti:
> runtime > kode nyata > dokumen ini.
>
> **Anti-duplikat.** Setiap item di dokumen ini sudah dicek terhadap util/collection
> yang mungkin sudah ada — kalau ada, disebut eksplisit. Kalau tidak, sudah
> dikonfirmasi lewat `grep` bahwa memang belum ada (baris "Anti-duplikat check").

---

## Daftar Isi
1. [Cara pakai dokumen ini](#1-cara-pakai-dokumen-ini)
2. [Ringkasan backlog & prioritas](#2-ringkasan-backlog--prioritas)
3. [ITEM 1 — [P1] CRUD Edit/Hapus Manajemen CMT](#3-item-1--p1-crud-edithapus-manajemen-cmt)
4. [ITEM 2 — [P2] Format Angka Rupiah Global](#4-item-2--p2-format-angka-rupiah-global)
5. [ITEM 3 — [P2/P3] WS-G6 cleanup + WS-F dokumentasi](#5-item-3--p2p3-ws-g6-cleanup--ws-f-dokumentasi)
6. [Dependency graph & urutan pengerjaan](#6-dependency-graph--urutan-pengerjaan)
7. [Change Log](#7-change-log)

**Cross-references:**
- `/app/memory/GUIDELINE_CMT_FLOW.md` — dokumen master untuk domain Produksi/Maklon/CMT-flow (T1..T4 variance handling). **Prioritas lebih tinggi dari backlog ini** — kalau ada bentrok, ikuti guideline.
- `/app/HANDOFF_NEXT_AGENT.md` — handoff session #26 (marketing/retur focus, sudah SELESAI).
- `/app/SSOT_MASTER_REPAIR_PLAN_PART5.md` — repair plan Part 5 (UI theme sync + RBAC coverage, out of scope backlog ini).
- `/app/memory/PREVIEW_STABLE_MODE.md` — env constraint pod 2 GB / 1 CPU (WAJIB baca).
- `/app/plan.md` — plan skala repo, saat ini mengarahkan Phase B/C CMT-flow.

---

## 1. Cara pakai dokumen ini

### 1.1 Fresh-agent bootstrap

```bash
# Konteks env & kredensial
cat /app/memory/PREVIEW_STABLE_MODE.md
cat /app/memory/test_credentials.md

# Konteks domain CMT-flow (LEBIH PRIORITAS bila konflik)
cat /app/memory/GUIDELINE_CMT_FLOW.md

# Baru buka backlog ini
cat /app/BACKLOG_PLAN.md
```

### 1.2 Definisi selesai per item

Item dianggap **selesai** hanya kalau:
- [ ] Semua Acceptance Criteria di bagian item ter-check ✅
- [ ] Verifikasi runtime lolos (via curl / testing_agent iteration report)
- [ ] Frontend build ulang bila menyentuh `src/` (`bash /app/scripts/rebuild_frontend.sh`)
- [ ] Catat di §7 Change Log dengan tanggal + file:line + bukti

### 1.3 Kalau menemukan diskrepansi dokumen vs kode

1. **Jangan patch salah satu blind**.
2. Catat di §7 Change Log dengan format:
   ```
   [DISCREPANCY YYYY-MM-DD] <ringkas>
     Dokumen §X bilang: <text>
     Kode <file:line> bilang: <text>
     Verifikasi: <mongoshell/curl/grep output>
     Verifikasi ke user: <ya/tidak>
   ```
3. Konfirmasi ke user sebelum bergerak.

### 1.4 Presedensi antar dokumen

Kalau **bentrok** antara `BACKLOG_PLAN.md` (ini) dan dokumen lain:

| Dokumen | Priority | Alasan |
|---|---|---|
| `GUIDELINE_CMT_FLOW.md` | **TERTINGGI** — override backlog ini | User priority terbaru (2026-07-16), grounded 1193 baris |
| `plan.md` | HIGH — sinkron dgn backlog + arahkan phase | Live plan repo |
| `BACKLOG_PLAN.md` (ini) | MEDIUM | 3 item P1/P2 non-CMT-flow |
| `HANDOFF_NEXT_AGENT.md` | LOW | Session #26 sudah SELESAI, historical |
| `SSOT_MASTER_REPAIR_PLAN_PART5.md` | LOW | UI theme scope, tidak overlap dgn item ini |

### 1.5 Kredensial standar

- Admin: `admin@garment.com / Admin@123` (superadmin)
- Role: `{hr,finance,spv,gudang,maklon}@dewiaditya.id / Dewi@123`
- (Lihat `/app/memory/test_credentials.md` untuk detail role & rate-limit)

---

## 2. Ringkasan backlog & prioritas

| # | Item | Prio | Domain | Effort | Risiko | Impact user |
|---|---|---|---|---|---|---|
| 1 | CRUD Edit/Hapus Manajemen CMT | **P1** | Vendor Portal (admin view) | Sedang (~4-6 jam) | Rendah | Langsung — admin belum bisa ubah/hapus vendor & akun |
| 2 | Format Rupiah Global (backend + frontend) | **P2** | Cross-domain (Finance, Marketing, Toko, HR, Produksi) | Besar (~2-3 hari rollout bertahap) | Sedang (banyak file) | Langsung — parsing salah bisa merusak nilai finance |
| 3.1 | WS-G6 cleanup dead-code + test posting | **P2** | Rahaza posting (finance internal) | Kecil (~2 jam) | Rendah | Tidak langsung — housekeeping |
| 3.2 | WS-F dokumentasi arsitektur (opsional) | **P3** | Dokumentasi | Kecil (~2 jam) | Nihil | Tidak langsung — untuk future agent |

**Not in scope backlog ini** (dikerjakan di dokumen lain):
- CMT-flow Phase B (Restructure CMT→DA→Buyer) → `GUIDELINE_CMT_FLOW.md §10`
- CMT-flow Phase C (PO closure + K5 cleanup) → `GUIDELINE_CMT_FLOW.md §11`

---

## 3. ITEM 1 — [P1] CRUD Edit/Hapus Manajemen CMT

### 3.1 Proses bisnis & logika

- **Vendor Partner** = entitas vendor CMT (subkontraktor jahit). Field wajib: `id`, `code`, `name`, `contact_name`, `contact_phone`, `address`, `notes`, `is_active`, `created_at`, `updated_at`.
- **Akun Vendor** = user login portal CMT (`users` dengan `role='cmt_vendor'`), terhubung ke 1 partner via field `cmt_vendor_id`.
- Admin internal perlu operasi: **buat, ubah, hapus (soft), reaktivasi** untuk partner & akun. Saat ini hanya `buat` dari UI (bahkan backend PUT/DELETE juga tidak lengkap).

**Aturan integritas (invariant):**

| Kode | Invariant | Enforcement |
|---|---|---|
| I-VP-1 | Partner yang punya akun `is_active=true` **tidak boleh** dihapus. Harus deaktivasi akun dulu. | Guard di `DELETE /partners/{id}` (baru) |
| I-VP-2 | Partner yang punya job status ∉ (`done`, `cancelled`, `completed`) **tidak boleh** dihapus. | Guard di `DELETE /partners/{id}` (baru) |
| I-VP-3 | Soft-delete only: field `is_active=false`, jangan `db.<...>.delete_one()`. | Semua endpoint destructive |
| I-VP-4 | **`users.email` immutable** setelah create (dipakai untuk auth). PUT /accounts hanya boleh update: `name`, `partner_id`, `password`, `is_active`. | Keputusan produk, di-enforce di endpoint PUT |
| I-VP-5 | Reactivate = `PUT /accounts/{id}` dgn `is_active=true` atau `PUT /partners/{id}` dgn `is_active=true`. | Field ditambah ke `PartnerIn` & `VendorAccountUpdate` |

### 3.2 Kondisi kode saat ini (grounded audit)

**File:** `/app/backend/routes/vendor_portal.py` (460 baris, prefix `/api/vendor-portal`).

| Endpoint | Line | Ada? | Gap |
|---|---|---|---|
| `GET /partners` | 105 | ✅ | — |
| `POST /partners` | 118 | ✅ | — |
| `PUT /partners/{id}` | 143 | ⚠️ | Tidak update `code`, tidak ada toggle `is_active` |
| `DELETE /partners/{id}` | — | ❌ | **HILANG total** |
| `GET /accounts` | 165 | ✅ | — |
| `POST /accounts` | 182 | ✅ | — |
| `PUT /accounts/{id}` | — | ❌ | **HILANG total** — tidak bisa ubah nama/partner/password/status |
| `DELETE /accounts/{id}` | 211 | ✅ | Set `is_active=false` tapi tidak ada reactivate |

**Verifikasi grounded:**
```bash
$ grep -nE "@router\.(get|post|put|delete)" /app/backend/routes/vendor_portal.py | head -10
105:@router.get('/partners')
118:@router.post('/partners')
143:@router.put('/partners/{partner_id}')
165:@router.get('/accounts')
182:@router.post('/accounts')
211:@router.delete('/accounts/{account_id}')
# Tidak ada DELETE /partners atau PUT /accounts.
```

**Frontend:** `/app/frontend/src/components/erp/VendorAccountsAdminModule.jsx` (358 baris).
- `PartnersTab` (baris 40-132): hanya form "Tambah" (POST @62) + daftar (@113-127). Tidak ada tombol Edit/Hapus.
- `AccountsTab` (baris 136-253): hanya form "Tambah" (POST @167) + daftar (@234-249) dgn badge Aktif/Nonaktif (@244). Tidak ada tombol Edit/Hapus/Aktifkan.
- Fungsi `create()` (@57 & @160) hanya create; tidak ada `save()` / `edit` / `remove`.

### 3.3 Anti-duplikat check

Dicek 2026-07-16:
- Tidak ada endpoint duplikat lain untuk vendor CMT (`grep '@router' vendor_portal*.py`) ✅
- Collection `vendor_partners` di-write hanya oleh `vendor_portal.py` + `vendor_portal_seed.py` + `maklon_seed.py`. Read-only di `master_data.py`, `production_rbac.py`. ✅ SSOT clear.
- Tidak ada UI paralel untuk Manajemen CMT selain `VendorAccountsAdminModule.jsx` (grep `partner_id` di frontend/src → hanya file ini + `moduleRegistry.js`). ✅

### 3.4 Fix design

#### 3.4.1 Backend — 3 endpoint baru + 1 endpoint di-extend

**A. Tambah `DELETE /partners/{partner_id}`** (soft-delete + guard I-VP-1 & I-VP-2):
```python
@router.delete('/partners/{partner_id}')
async def deactivate_partner(partner_id: str, request: Request):
    user = await require_auth(request); _require_admin(user)
    db = get_db()
    partner = await db.vendor_partners.find_one({'id': partner_id})
    if not partner:
        raise HTTPException(404, "Partner tidak ditemukan.")
    # Invariant I-VP-1
    active_acc = await db.users.count_documents(
        {'cmt_vendor_id': partner_id, 'role': 'cmt_vendor', 'is_active': True})
    # Invariant I-VP-2
    active_job = await db.vendor_jobs.count_documents(
        {'partner_id': partner_id, 'status': {'$nin': ['done', 'cancelled', 'completed']}})
    if active_acc or active_job:
        raise HTTPException(400,
            f"Tidak bisa hapus: {active_acc} akun aktif & {active_job} job berjalan. "
            f"Nonaktifkan dulu.")
    await db.vendor_partners.update_one({'id': partner_id},
        {'$set': {'is_active': False, 'updated_at': _now()}})
    await log_activity(user['id'], user.get('name',''),
                       f"deactivate_vendor_partner:{partner_id}", 'vendor_portal', partner_id)
    return {'ok': True}
```

**B. Extend `PUT /partners/{id}`** (tambah `code` + `is_active`):

Pertama update model `PartnerIn` (top of file, sudah ada) — tambah `is_active: Optional[bool] = None`.

Kemudian di endpoint (@143), tambah setelah `update = {...}`:
```python
if payload.code:
    dup = await db.vendor_partners.find_one(
        {'code': payload.code.upper(), 'id': {'$ne': partner_id}})
    if dup: raise HTTPException(400, f"Kode '{payload.code}' sudah dipakai.")
    update['code'] = payload.code.upper().strip()
if payload.is_active is not None:
    update['is_active'] = bool(payload.is_active)  # I-VP-5 (reactivate)
```

**C. Tambah `PUT /accounts/{account_id}`** (edit akun; email immutable per I-VP-4):
```python
class VendorAccountUpdate(BaseModel):
    name: Optional[str] = None
    partner_id: Optional[str] = None
    password: Optional[str] = None    # kosong = tidak ganti
    is_active: Optional[bool] = None  # reactivate/deactivate

@router.put('/accounts/{account_id}')
async def update_vendor_account(account_id: str, payload: VendorAccountUpdate,
                                 request: Request):
    user = await require_auth(request); _require_admin(user)
    db = get_db()
    acc = await db.users.find_one({'id': account_id, 'role': 'cmt_vendor'})
    if not acc: raise HTTPException(404, "Akun vendor tidak ditemukan.")
    upd = {'updated_at': _now()}
    if payload.name is not None: upd['name'] = payload.name.strip()
    if payload.partner_id:
        if not await db.vendor_partners.find_one({'id': payload.partner_id}):
            raise HTTPException(400, "Partner tidak ditemukan.")
        upd['cmt_vendor_id'] = payload.partner_id
    if payload.password:                    # I-VP-4: password reset only
        upd['password'] = hash_password(payload.password)
    if payload.is_active is not None:       # I-VP-5
        upd['is_active'] = bool(payload.is_active)
    # I-VP-4 explicit: email tidak boleh diubah di endpoint ini.
    if 'email' in payload.model_dump(exclude_unset=True):
        raise HTTPException(400, "Email login tidak bisa diubah (immutable per I-VP-4).")
    await db.users.update_one({'id': account_id}, {'$set': upd})
    await log_activity(user['id'], user.get('name',''),
                       f"update_vendor_account:{account_id}", 'vendor_portal', account_id)
    return {'ok': True}
```

**D. Import yang mungkin perlu ditambah** di top of file (cek dulu apakah sudah ada):
```python
from typing import Optional
```

#### 3.4.2 Frontend — 3 patch di `VendorAccountsAdminModule.jsx`

**A. PartnersTab (baris 40-132):**
- Tambah state `editingId, setEditingId = useState(null)`.
- Ganti `create()` → `save()`:
  ```jsx
  const save = async () => {
    try {
      if (editingId) {
        await apiPut(`/vendor-portal/partners/${editingId}`, form);
      } else {
        await apiPost('/vendor-portal/partners', form);
      }
      setForm({ name:'', code:'', contact_name:'', contact_phone:'', address:'', notes:'' });
      setEditingId(null);
      await refresh();
    } catch (e) { toast.error(e?.message || 'Gagal simpan'); }
  };
  ```
- Setiap baris daftar tambah 2 tombol:
  ```jsx
  <div className="flex gap-2">
    <Button size="sm" variant="outline" data-testid={`partner-edit-${p.id}`}
            onClick={() => { setForm({...p}); setEditingId(p.id); }}>Edit</Button>
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="destructive"
                data-testid={`partner-delete-${p.id}`}>Nonaktifkan</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Nonaktifkan Partner {p.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            Partner akan di-set is_active=false. Bisa diaktifkan lagi kalau perlu.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Batal</AlertDialogCancel>
          <AlertDialogAction onClick={async () => {
            try { await apiDelete(`/vendor-portal/partners/${p.id}`); await refresh(); }
            catch (e) { toast.error(e?.message || 'Gagal'); }
          }}>Nonaktifkan</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
  ```

**B. AccountsTab (baris 136-253):**
- Sama pola dengan PartnersTab tapi field: `name`, `partner_id`, `password` (opsional), `is_active`.
- Toggle Aktif/Nonaktif via `PUT /vendor-portal/accounts/${id}` dgn body `{is_active: !currentValue}`.
- Field `email` **read-only saat edit** (per I-VP-4).

**C. Import shadcn/ui components** (cek dulu apakah sudah di-import):
```jsx
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
         AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
         AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog';
```

**D. Rebuild frontend WAJIB:**
```bash
bash /app/scripts/rebuild_frontend.sh
```

### 3.5 SSOT & collection touchpoints

- **SSOT `vendor_partners`** — writer only via `vendor_portal.py`.
- **SSOT `users` (dgn `role='cmt_vendor'`)** — writer only via `vendor_portal.py` (auth).
- **Reader `vendor_jobs`** — untuk invariant I-VP-2. Jangan tulis dari endpoint ini.
- **Audit log** via `log_activity(...)` — semua endpoint destructive/edit WAJIB log.

### 3.6 Acceptance Criteria

- [ ] `DELETE /api/vendor-portal/partners/{id}` return 200 kalau partner tidak punya akun aktif & job aktif.
- [ ] `DELETE /api/vendor-portal/partners/{id}` return 400 dgn pesan Indonesia kalau ada akun aktif atau job aktif.
- [ ] `PUT /api/vendor-portal/partners/{id}` update `code` (dengan cek unik) & `is_active` (reactivate).
- [ ] `PUT /api/vendor-portal/accounts/{id}` update `name` / `partner_id` / `password` / `is_active`.
- [ ] `PUT /api/vendor-portal/accounts/{id}` **reject email change** dengan HTTP 400.
- [ ] Frontend PartnersTab: tombol Edit isi form ada; tombol Nonaktifkan dgn confirm dialog ada.
- [ ] Frontend AccountsTab: tombol Edit + toggle Aktif/Nonaktif ada.
- [ ] Semua tombol punya `data-testid` unik (`partner-edit-{id}`, `partner-delete-{id}`, `account-edit-{id}`, `account-toggle-{id}`).
- [ ] `log_activity` tercatat untuk setiap edit/delete.
- [ ] Frontend build lolos via `rebuild_frontend.sh`.
- [ ] `testing_agent_v3` skenario §3.8 semua PASS.

### 3.7 Verifikasi cepat (curl one-liner)

```bash
TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@garment.com","password":"Admin@123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

# Cek DELETE /partners
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE \
  http://localhost:8001/api/vendor-portal/partners/dummy-id \
  -H "Authorization: Bearer $TOKEN"    # expect 404 (partner tidak ada) BUKAN 405

# Cek PUT /accounts
curl -s -o /dev/null -w '%{http_code}\n' -X PUT \
  http://localhost:8001/api/vendor-portal/accounts/dummy-id \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"test"}'                  # expect 404 (akun tidak ada) BUKAN 405
```

### 3.8 Testing contract (testing_agent_v3)

**Skenario T1.1 (partner CRUD full-cycle):**
1. Login admin. POST partner baru → 200.
2. PUT partner (update name + code) → 200; kode duplikat → 400.
3. POST akun A untuk partner ini → 200 dgn is_active=true.
4. DELETE partner → 400 (guard I-VP-1: akun aktif).
5. DELETE akun A → is_active=false.
6. DELETE partner → 200 (guard lolos).
7. PUT partner dgn is_active=true → reactivate.

**Skenario T1.2 (akun CRUD full-cycle):**
1. POST akun. PUT nama → 200. PUT partner_id ke partner_lain → 200.
2. PUT dgn password baru → login pakai password baru sukses.
3. PUT dgn `{email: 'x@y.z'}` → HTTP 400 (immutable).
4. PUT dgn is_active=false → login gagal.
5. PUT dgn is_active=true → login sukses lagi.

**Skenario T1.3 (frontend UI):**
1. Login admin, buka menu Manajemen CMT.
2. Tab Partners: tombol Edit muncul di setiap baris, klik → form terisi.
3. Simpan → daftar update tanpa refresh manual.
4. Tombol Nonaktifkan → alert dialog muncul → konfirmasi → baris jadi Nonaktif.
5. Tab Akun: sama pattern.

### 3.9 Files touched (checklist)

- [ ] `/app/backend/routes/vendor_portal.py` — 3 endpoint baru + 1 extend
- [ ] `/app/frontend/src/components/erp/VendorAccountsAdminModule.jsx` — 2 tab patched
- [ ] `/app/frontend/build/` — rebuild
- [ ] `/app/BACKLOG_PLAN.md §7 Change Log` — entry

---

## 4. ITEM 2 — [P2] Format Angka Rupiah Global

### 4.1 Proses bisnis & logika (locale Indonesia)

- Locale ID (`id-ID`): **titik `.` = pemisah ribuan**, **koma `,` = desimal**.
- Contoh valid: `Rp 1.234.567,89`, `Rp 150.000`, `1.500.000`, `(1.000)` (negatif).
- Contoh invalid untuk locale ID: `1,234.5` (US style), `€150.00` (EUR).
- Mayoritas nominal Rupiah = bilangan bulat. Desimal jarang (biasanya di tarif per-unit atau kurs).

**Kebutuhan:**
1. **Parsing input** (user ketik / import CSV-Excel) → angka murni.
2. **Format tampilan** konsisten `Rp 1.234.567`.
3. **Anti-loss precision** untuk field finance kritis (COA, jurnal, invoice, gaji).

### 4.2 Root cause — bug parsing backend

**File:** `/app/backend/routes/marketing_import.py`, fungsi `_convert_value` (baris 265-294).

**Kode buggy** (baris 273):
```python
s = s.replace('Rp', '').replace('IDR', '').replace(',', '') \
     .replace('.', '', s.count('.') - 1) if s.count('.') > 1 \
     else s.replace('Rp', '').replace('IDR', '').replace(',', '')
return float(s), None
```

**Test case failure** (verified):
| Input | Actual output | Expected |
|---|---|---|
| `"Rp 150.000"` | `150.0` ❌ | `150000` |
| `"Rp 1.500.000"` | `1500.0` ❌ | `1500000` |
| `"1.234.567,89"` | `float('1234567,89')` → ValueError ❌ | `1234567.89` |
| `"150,5"` | `float('1505')` = `1505` ❌ (koma di-strip) | `150.5` |

**Cabang integer (baris 277):**
```python
s = s.replace(',', '').replace('.', '')
return int(float(s)), None
```
- KEBETULAN benar untuk ribuan ID (`"150.000"` → `"150000"`) tapi salah untuk desimal koma (`"150,5"` → `"1505"`). Logika tidak konsisten.

### 4.3 File lain yang pakai parsing angka mentah

**Verified grounded 2026-07-16:**

```bash
$ sed -n '37,38p' /app/backend/routes/operations_import.py
'cmt_price': float(row.get('cmt_price', 0) or 0),
'selling_price': float(row.get('selling_price', 0) or 0),

$ sed -n '97,98p' /app/backend/routes/operations_import.py
'selling_price_snapshot': float(item.get('selling_price', 0) or 0),
'cmt_price_snapshot': float(item.get('cmt_price', 0) or 0),
```

**Analisis:** `operations_import.py` endpoint `/api/import-data` menerima data dari CSV/Excel via `import-template`. Sumbernya kemungkinan MANUSIA yang mengetik locale ID → **wajib bungkus dengan `_parse_id_number`**. Konfirmasi user dulu bila ada pertanyaan.

### 4.4 Anti-duplikat check (frontend)

Dicek 2026-07-16:

```bash
$ find /app/frontend/src -name "*format*" -o -name "*currency*" -o -name "*rupiah*" -o -name "*money*"
# (kosong — TIDAK ada util currency existing)

$ grep -rln "parseNumericId\|parseRupiah\|parseRp" /app/frontend/src
# (kosong — TIDAK ada parser existing)

$ grep -rlnE "const fmtIDR|const formatCurrency" /app/frontend/src --include="*.jsx"
# 8+ file dengan definisi LOKAL:
# - components/erp/TokoOrdersModule.jsx
# - components/erp/finance/CashFlowAI.jsx
# - components/erp/CMTManagementModule.jsx
# - components/erp/RahazaPayrollRunModule.jsx
# - components/erp/TokoProductCatalogModule.jsx
# - components/erp/HRAdminModule.jsx
# - components/erp/TokoDashboardModule.jsx
# - components/erp/TokoPricingFlashsaleModule.jsx
```

**Statistik:**
- Files pakai `toLocaleString` (any locale): **169**
- Files pakai `toLocaleString('id-ID')` khusus: **138**
- Files pakai `<input type="number">`: **169**

**Kesimpulan:** util terpusat **belum ada** — usulan bikin `formatNumber.js` valid. `<CurrencyInput>` juga belum ada di `/app/frontend/src/components/ui/` (cuma `input.jsx` & `input-otp.jsx`).

### 4.5 Fix design

#### 4.5.1 Backend — parser locale-ID terpusat

**File baru:** `/app/backend/routes/shared.py` (extend existing shared utils):

```python
def parse_id_number(raw) -> float:
    """Parsing angka locale Indonesia. titik=ribuan, koma=desimal.

    Menangani:
      'Rp 150.000'        -> 150000.0
      '1.234.567,89'      -> 1234567.89
      '150000'            -> 150000.0
      '150,5'             -> 150.5
      '(1.000)'           -> -1000.0
      '' / None / 'nan'   -> 0.0

    Trade-off: format US murni ('150.5' sebagai desimal) → 1505 (ribuan).
    Untuk ERP Rupiah ini adalah perilaku BENAR. Kalau butuh dukung dua locale,
    tambah heuristik: jika hanya 1 titik & digit setelah titik ≤ 2 & tak ada
    koma → anggap desimal. Sementara TIDAK diaktifkan (KISS).
    """
    import re
    if raw is None: return 0.0
    s = str(raw).strip()
    if not s or s.lower() == 'nan': return 0.0
    neg = s.startswith('(') and s.endswith(')')
    s = re.sub(r'[^0-9.,-]', '', s)   # buang Rp, IDR, spasi, dll
    if ',' in s:                        # ada desimal koma
        s = s.replace('.', '').replace(',', '.')
    else:                                # tidak ada koma → titik = ribuan
        s = s.replace('.', '')
    try: val = float(s or 0)
    except ValueError: val = 0.0
    return -abs(val) if neg else val
```

**Update `marketing_import.py`:**
```python
from routes.shared import parse_id_number

# Ganti dalam _convert_value:
if target_type == 'number':
    return parse_id_number(s), None
elif target_type == 'integer':
    return int(round(parse_id_number(s))), None
```

**Update `operations_import.py`:**
```python
from routes.shared import parse_id_number

# Baris 37-38, 97-98: ganti float(...) → parse_id_number(...)
'cmt_price': parse_id_number(row.get('cmt_price', 0)),
'selling_price': parse_id_number(row.get('selling_price', 0)),
# ... dst
```

**Cek juga (lower priority; grep dulu):**
```bash
grep -rn "float(row\|float(item\|float(payload" /app/backend/routes/*.py | grep -iE "price|amount|nominal|rupiah|rp|salary|gaji"
```
Ganti bertahap sesuai temuan.

#### 4.5.2 Frontend — util terpusat

**File baru:** `/app/frontend/src/lib/formatNumber.js`

```javascript
/**
 * Utilitas format angka locale Indonesia (id-ID).
 * Titik = ribuan, koma = desimal.
 * Import di modul manapun; JANGAN definisikan fmtIDR lokal lagi.
 */

/**
 * Parse string locale-ID → Number.
 * @param {string|number} str
 * @returns {number} 0 jika input invalid/kosong.
 */
export function parseNumericId(str) {
  if (typeof str === 'number') return Number.isFinite(str) ? str : 0;
  let s = String(str ?? '').trim();
  if (!s || s.toLowerCase() === 'nan') return 0;
  const neg = /^\(.*\)$/.test(s);
  s = s.replace(/[^0-9.,-]/g, '');
  if (s.includes(',')) s = s.replace(/\./g, '').replace(',', '.');
  else s = s.replace(/\./g, '');
  const n = parseFloat(s || '0');
  if (isNaN(n)) return 0;
  return neg ? -Math.abs(n) : n;
}

/** Format angka biasa: 1234567 → "1.234.567" */
export const formatNumberId = (n) => Number(n || 0).toLocaleString('id-ID');

/** Format currency Rupiah: 1234567 → "Rp 1.234.567" */
export const formatCurrencyId = (n) => `Rp ${formatNumberId(n)}`;

/** Alias untuk backward compat (jangan pakai untuk kode baru) */
export const fmtIDR = formatCurrencyId;
```

**File baru:** `/app/frontend/src/components/ui/CurrencyInput.jsx`

```jsx
import * as React from 'react';
import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import { parseNumericId, formatNumberId } from '@/lib/formatNumber';

/**
 * Controlled input Rupiah / angka locale-ID.
 * Simpan nilai numerik (Number) di parent state; tampilkan terformat.
 *
 * Props:
 *   value          Number  — nilai numerik (bukan string)
 *   onValueChange  (n) => void
 *   showPrefixRp   boolean — tampilkan prefix "Rp " (default true)
 *   ...restProps   — diteruskan ke <Input>
 */
export const CurrencyInput = React.forwardRef(({
  value, onValueChange, showPrefixRp = true, className, ...rest
}, ref) => {
  const [display, setDisplay] = React.useState(formatNumberId(value ?? 0));
  React.useEffect(() => {
    setDisplay(formatNumberId(value ?? 0));
  }, [value]);
  const onChange = (e) => {
    const raw = e.target.value;
    const n = parseNumericId(raw);
    setDisplay(raw);        // jaga cursor pengetikan
    onValueChange?.(n);
  };
  const onBlur = () => {
    setDisplay(formatNumberId(value ?? 0));  // re-format saat lepas fokus
  };
  return (
    <div className={cn('relative', className)}>
      {showPrefixRp && (
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">
          Rp
        </span>
      )}
      <Input
        ref={ref}
        type="text"
        inputMode="numeric"
        value={display}
        onChange={onChange}
        onBlur={onBlur}
        className={cn(showPrefixRp && 'pl-9')}
        {...rest}
      />
    </div>
  );
});
CurrencyInput.displayName = 'CurrencyInput';
```

#### 4.5.3 Rollout bertahap frontend

**Kebijakan `<input type="number">`:**
- **JANGAN dipakai** untuk nominal Rupiah (masalah locale + ribuan).
- **BOLEH tetap** untuk `qty`/`pcs` (bilangan bulat kecil, tanpa ribuan, tanpa desimal).
- **BOLEH tetap** untuk persentase kalau memang butuh spinner numerik.

**Prioritas rollout** (tinggi → rendah):
1. **Finance / Rahaza** (COA, jurnal, invoice) — `Rahaza*Module.jsx`. Salah = angka finance rusak.
2. **HPP + PO harga** — `ProductionPOModule.jsx`, `RahazaHPPModule.jsx`.
3. **Payroll** — `RahazaPayrollRunModule.jsx`, `HRAdminModule.jsx`.
4. **Toko / Marketing** — `TokoPricingFlashsaleModule.jsx`, `TokoProductCatalogModule.jsx`.
5. **Sisanya** — sesuai temuan grep.

**Pattern penggantian:**

```jsx
// ❌ SEBELUM (di banyak file):
const fmtIDR = (n) => `Rp ${Number(n||0).toLocaleString('id-ID')}`;
<input type="number" value={form.price}
       onChange={e => setForm({...form, price: e.target.value})} />

// ✅ SESUDAH:
import { formatCurrencyId } from '@/lib/formatNumber';
import { CurrencyInput } from '@/components/ui/CurrencyInput';
<CurrencyInput value={form.price}
               onValueChange={n => setForm({...form, price: n})} />
{formatCurrencyId(item.total)}
```

**Tracking rollout** (setelah setiap batch selesai, coret di list):
- [ ] Batch 1: Finance/Rahaza (~15 file)
- [ ] Batch 2: HPP + PO (~5 file)
- [ ] Batch 3: Payroll (~8 file)
- [ ] Batch 4: Toko/Marketing (~20 file)
- [ ] Batch 5: Sisanya (~60 file)

### 4.6 SSOT & collection touchpoints

- **Backend SSOT format**: `/app/backend/routes/shared.py` (extend, JANGAN buat file baru).
- **Frontend SSOT format**: `/app/frontend/src/lib/formatNumber.js` (baru).
- **Frontend SSOT component**: `/app/frontend/src/components/ui/CurrencyInput.jsx` (baru).
- **Collection touchpoints**: TIDAK ADA — ini pure utility, tidak menyentuh DB schema.

### 4.7 Acceptance Criteria

#### Backend
- [ ] `routes/shared.py` export `parse_id_number` dengan 6 test case di §4.8 semuanya PASS.
- [ ] `routes/marketing_import.py._convert_value` pakai `parse_id_number` untuk number & integer.
- [ ] `routes/operations_import.py` baris 37-38 & 97-98 (dan hasil grep) pakai `parse_id_number`.
- [ ] Import CSV existing tidak break (regresi test).

#### Frontend
- [ ] `/app/frontend/src/lib/formatNumber.js` ada dengan 3 export: `parseNumericId`, `formatNumberId`, `formatCurrencyId`.
- [ ] `/app/frontend/src/components/ui/CurrencyInput.jsx` ada.
- [ ] Minimal Batch 1 (Finance/Rahaza) sudah replace `fmtIDR` local → import terpusat.
- [ ] Minimal Batch 1 sudah replace `<input type="number">` harga → `<CurrencyInput>`.
- [ ] Frontend build lolos.

#### Cross-cutting
- [ ] Tidak ada regresi di flow existing (verify via testing_agent smoke).

### 4.8 Verifikasi cepat (backend unit)

```python
# /app/backend/tests/test_parse_id_number.py
from routes.shared import parse_id_number

def test_parse():
    assert parse_id_number('Rp 150.000') == 150000.0
    assert parse_id_number('1.234.567,89') == 1234567.89
    assert parse_id_number('150000') == 150000.0
    assert parse_id_number('150,5') == 150.5
    assert parse_id_number('(1.000)') == -1000.0
    assert parse_id_number('') == 0.0
    assert parse_id_number(None) == 0.0
    assert parse_id_number('nan') == 0.0
    assert parse_id_number(1234) == 1234.0
```

Run:
```bash
cd /app/backend && pytest tests/test_parse_id_number.py -v
```

### 4.9 Testing contract (testing_agent_v3)

**Skenario T2.1 (backend parsing):**
1. Jalankan unit test §4.8, semua assertion PASS.
2. Simulasi import CSV via `POST /api/import-data` dengan kolom price `"Rp 150.000"` → nilai tersimpan `150000` (bukan `150.0`).

**Skenario T2.2 (frontend UI):**
1. Buka menu Finance / Journal / Invoice.
2. Input harga `1.234.567` → state numerik = 1234567.
3. Reformat saat blur → tampil `Rp 1.234.567`.
4. Submit → backend terima Number 1234567.

**Skenario T2.3 (regresi):**
1. Import CSV dengan angka locale US-style di kolom lain (mis. koordinat GPS `-6.20`) → **HARUS tidak rusak** (bukan finance field).

### 4.10 Files touched (checklist)

**Backend:**
- [ ] `/app/backend/routes/shared.py` — extend dgn `parse_id_number`
- [ ] `/app/backend/routes/marketing_import.py` — replace `_convert_value` internals
- [ ] `/app/backend/routes/operations_import.py` — replace `float(...)` (baris 37-38, 97-98)
- [ ] `/app/backend/tests/test_parse_id_number.py` — new unit test

**Frontend:**
- [ ] `/app/frontend/src/lib/formatNumber.js` — new
- [ ] `/app/frontend/src/components/ui/CurrencyInput.jsx` — new
- [ ] Batch 1-5 (per file di §4.5.3) — replace incremental
- [ ] `/app/frontend/build/` — rebuild

**Docs:**
- [ ] `/app/BACKLOG_PLAN.md §7 Change Log`

---

## 5. ITEM 3 — [P2/P3] WS-G6 cleanup + WS-F dokumentasi

### 5.1 ITEM 3.1 — WS-G6 dead-code cleanup (P2)

#### 5.1.1 Status saat ini (grounded)

**Fungsi AKTIF & benar:** `post_wip_to_fg_on_job_complete(db, job, user)` di `/app/backend/routes/rahaza_posting.py` **baris 1591**.

**Call graph** (verified):
- **Caller aktif:** `on_job_completed_internal` di `/app/backend/routes/production_internal_adapter.py` **baris 448-451**:
  ```python
  async def on_job_completed_internal(db, job: dict, user: dict) -> dict:
      snapshot = await upsert_hpp_snapshot_job(db, job['id'], user)
      from routes.rahaza_posting import post_wip_to_fg_on_job_complete
      posting = await post_wip_to_fg_on_job_complete(db, job, user)
      return {'hpp_snapshot_total': snapshot.get('total_cost'), 'wip_to_fg': posting}
  ```
- **Trigger:** `production_execution.py` baris **481** (di POST /production-progress):
  ```python
  if job_doc.get('business_type') == 'internal':
      try:
          from routes.production_internal_adapter import on_job_completed_internal
          _completed_hook = await on_job_completed_internal(
              db, {**job_doc, 'status': 'Completed'}, user)
      ...
  ```
- **Idempotency:** `source_ref=f"wip_fg_job:{job_id}"` di `rahaza_journal_entries` — helper melewati posting yang sudah ada.

**Fungsi ORPHAN (dead-code):** `post_wip_to_fg_on_wo_complete` di `rahaza_posting.py` baris **900-986**.

**Call graph orphan** (verified):
```
$ grep -rn "post_wip_to_fg_on_wo_complete" /app/backend /app/frontend/src
/app/backend/routes/rahaza_posting.py:900:async def post_wip_to_fg_on_wo_complete(...
/app/backend/routes/_archive/rahaza_multistage/rahaza_work_orders.py:539: from ...
/app/backend/routes/_archive/rahaza_multistage/rahaza_work_orders.py:541: posting_result = await ...
/app/backend/routes/_archive/rahaza_multistage/rahaza_work_orders.py:579: from ...
/app/backend/routes/_archive/rahaza_multistage/rahaza_work_orders.py:580: result = await ...
```

**⚠️ NUANSA:** klaim dokumen lama "TIDAK dipanggil dari mana pun" **semi-akurat**. Fungsi ini dipanggil dari `_archive/rahaza_multistage/rahaza_work_orders.py` — file arsip yang **TIDAK di-import** di `server.py`:

```bash
$ grep "rahaza_work_orders" /app/backend/server.py
# (kosong — TIDAK di-register di server)

$ grep "rahaza_multistage" /app/backend/server.py
# (kosong)
```

**Kesimpulan:** callers ada di `_archive/`, tapi archive tidak di-load runtime. Jadi de-facto orphan.

#### 5.1.2 Rekomendasi eksekusi

**Opsi A (RECOMMENDED)** — Hapus `post_wip_to_fg_on_wo_complete` (baris 900-986):
- Callers hanya di `_archive/` yang tidak di-import.
- Menulis ke koleksi `rahaza_work_orders` yang sudah diarsip (E10 DELETE).
- Membaca `work_order_id` legacy yang tidak dipakai.
- **Aman dihapus.** Kalau butuh, arsip via `_archive/rahaza_posting_legacy.py`.

**Opsi B (safer)** — Tetap ada tapi ubah body jadi `raise NotImplementedError`:
```python
async def post_wip_to_fg_on_wo_complete(db, wo, user):
    """DEPRECATED (E10): jalur WO diarsip 2026-XX-XX.
    Gunakan post_wip_to_fg_on_job_complete via on_job_completed_internal.
    """
    raise NotImplementedError(
        'post_wip_to_fg_on_wo_complete deprecated per E10. '
        'Use post_wip_to_fg_on_job_complete.'
    )
```
Alasan pilih Opsi B: kalau ada branch/session yang belum di-merge yang re-enable `_archive/rahaza_work_orders.py`, error jelas > silent failure. Tapi ini paranoia — Opsi A tetap tepat.

**Konsistensi minor:** mapping key `event_type` masih `wip_to_fg_on_wo_complete` di `rahaza_posting_profiles.py:177,517` — biarkan (backward-compat untuk profile lama), atau tambah alias `wip_to_fg_on_job_complete`.

#### 5.1.3 Test E2E yang belum ada

Belum ada test yang membuktikan flow: job internal Completed → JE WIP→FG idempoten.

**File baru:** `/app/backend/tests/test_wip_to_fg_on_job_complete.py`

```python
"""Test WS-G6 — Posting WIP→FG on job internal completed (idempoten)."""
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_wip_to_fg_idempotent(admin_token, seed_internal_job):
    """Job internal Completed → JE WIP→FG. Repeat = already_posted=True."""
    job_id = seed_internal_job['id']
    async with AsyncClient(base_url='http://localhost:8001') as c:
        # 1. Progress hingga all_done
        # (setup: MI issued sudah ada dari seed)
        for item in seed_internal_job['items']:
            r = await c.post('/api/production-progress',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'job_id': job_id, 'job_item_id': item['id'],
                      'completed_quantity': item['ordered_qty']})
            assert r.status_code == 201

        # 2. Cek JE ter-post
        from database import get_db
        db = get_db()
        je = await db.rahaza_journal_entries.find_one(
            {'source_ref': f'wip_fg_job:{job_id}'})
        assert je is not None
        assert je['status'] == 'posted'

        # 3. Simulate re-invoke (via hook langsung; via API sudah idempotent by 'Completed' guard)
        from routes.rahaza_posting import post_wip_to_fg_on_job_complete
        job = await db.production_jobs.find_one({'id': job_id})
        result = await post_wip_to_fg_on_job_complete(db, job, {'id': 'test-user'})
        assert result.get('already_posted') is True
```

#### 5.1.4 Acceptance Criteria WS-G6

- [ ] Opsi A ATAU Opsi B diterapkan pada `rahaza_posting.py:900-986`.
- [ ] `grep post_wip_to_fg_on_wo_complete /app/backend/routes/*.py` (bukan `_archive/`) → kosong.
- [ ] `test_wip_to_fg_on_job_complete.py` PASS di pytest.
- [ ] Aggregate `curl POST /api/production-progress` untuk job internal → JE WIP→FG muncul di `rahaza_journal_entries` dgn `source_ref=wip_fg_job:{job_id}`.
- [ ] Repeat call → `already_posted=True`.

#### 5.1.5 Files touched WS-G6

- [ ] `/app/backend/routes/rahaza_posting.py` — hapus atau raise NotImplemented @900-986
- [ ] `/app/backend/tests/test_wip_to_fg_on_job_complete.py` — new
- [ ] `/app/BACKLOG_PLAN.md §7 Change Log`

---

### 5.2 ITEM 3.2 — WS-F Dokumentasi Arsitektur (P3, opsional)

#### 5.2.1 Tujuan

Dokumentasi arsitektur & "build memory" agar sesi berikut cepat paham SSOT tiap domain. Bukan bug — pure documentation.

#### 5.2.2 Ruang lingkup

- **JANGAN duplikat** `GUIDELINE_CMT_FLOW.md` (yang sudah cover produksi/maklon/CMT-flow secara detail).
- **Fokus pada domain lain yang belum ter-cover**:
  - Finance / Rahaza posting (COA, journal, HPP, WIP→FG)
  - Marketing / Toko / After-sales
  - HR / Payroll / LMS
  - Master data (produk, warna, size, aksesoris)
  - Bridge / integrasi antar-domain

#### 5.2.3 Struktur usulan `/app/ARCHITECTURE.md`

```
# ARCHITECTURE.md — Cross-Domain SSOT Reference

## Domain Registry (satu-liner per domain)
| Domain          | SSOT collections                      | Owner file          |
|---|---|---|
| Produksi        | production_pos, po_items, production_jobs, production_job_items, production_progress | production_pos.py, production_execution.py |
| Maklon (bridge) | (mirror dari production_pos)          | production_maklon_bridge.py |
| Finance Rahaza  | rahaza_journal_entries, rahaza_coa, rahaza_posting_profiles, rahaza_hpp_snapshots | rahaza_posting.py, rahaza_hpp.py |
| Marketing       | marketing_orders, marketing_returns, credit_notes | marketing_*.py |
| Toko            | dewi_toko_orders, dewi_toko_products, ... | dewi_toko_*.py |
| HR              | dewi_hr_employees, dewi_hr_attendance, ... | dewi_hr_*.py |
| Payroll         | dewi_hr_payroll_runs, dewi_hr_salary_slips | dewi_hr_payroll.py |
| Master Produk   | rahaza_models, rahaza_model_variants, rahaza_colors, ... | rahaza_master.py |

## Cross-domain data flows
- Job Completed → Posting WIP→FG → Journal Entry (F1)
- CMT Receipt Approved → Mature AP → dewi_maklon_finance (F2) *(Phase B guideline)*
- Buyer Shipment Received → AR Invoice mature → dewi_maklon_finance (F3)
- HR Payroll Run → Journal Entry Salary (F4)
- Marketing Order Completed → Journal Entry Sales (F5)

## Bridge modules
- production_maklon_bridge.py — production_pos ↔ dewi_maklon_pos ↔ dewi_maklon_finance
- production_internal_adapter.py — production job event → rahaza posting
- (dan seterusnya)

## Anti-duplikat glossary (yang MUDAH ditulis salah)
- production_pos vs dewi_maklon_pos — SSOT = production_pos; dewi_maklon_pos hanya mirror via bridge
- production_jobs vs dewi_cmt_jobs — SSOT = production_jobs; dewi_cmt_jobs deprecated
- dst.
```

#### 5.2.4 Acceptance Criteria WS-F

- [ ] File `/app/ARCHITECTURE.md` ada, minimal berisi Domain Registry & Cross-domain flows.
- [ ] Cross-reference dengan `GUIDELINE_CMT_FLOW.md` (jangan duplikat).
- [ ] Reviewed dan disetujui user.

#### 5.2.5 Files touched WS-F

- [ ] `/app/ARCHITECTURE.md` — new

---

## 6. Dependency graph & urutan pengerjaan

```
      ┌─── Item 1 (P1, CRUD CMT) ────────────────────── independent, mulai duluan.
      │
      ├─── Item 3.1 (P2, WS-G6 cleanup) ─── independent, ringan (~2 jam).
      │
      ├─── Item 2 (P2, Format Rupiah)
      │      │
      │      ├─── Batch 1: Finance (paling kritis, 5 file)
      │      ├─── Batch 2: HPP + PO harga    ← BISA overlap dengan Item 1 kalau perlu edit harga di CMT
      │      ├─── Batch 3: Payroll
      │      ├─── Batch 4: Toko/Marketing
      │      └─── Batch 5: Sisanya
      │
      └─── Item 3.2 (P3, WS-F dokumentasi) ─── setelah Item 3.1 selesai (agar referensi WS-G6 solid).
```

**Urutan yang disarankan:**

1. **Item 1** (CRUD CMT) — dampak user langsung, effort sedang, risiko rendah.
2. **Item 3.1** WS-G6 cleanup + test — effort kecil, mostly sudah jalan.
3. **Item 2 Backend** (`parse_id_number` + patch 2 file) — semua unit test PASS.
4. **Item 2 Frontend Batch 1** (Finance) — paling kritis untuk data integrity.
5. **Item 2 Frontend Batch 2-5** — bertahap, tidak harus dalam 1 sesi.
6. **Item 3.2** — terakhir, low priority.

**Kalau ada tekanan waktu:** kerjakan Item 1 + Item 2 Backend + Item 3.1 dulu (≈8-10 jam total). Frontend rollout Item 2 bisa lanjut sesi berikutnya.

**Dependency:** TIDAK ada blocker cross-item. Setiap item bisa selesai independen.

---

## 7. Change Log

Format entri:
```
[YYYY-MM-DD INITIAL] <one-line summary>
  - <bullet detail>
  Files: <path[:line]>
  Verification: <curl / testing_agent iteration_{n}.json / pytest output>
```

### Log

```
[2026-07-16 E2] BACKLOG_PLAN.md v2.0.0 — full quality refactor.
  - Grounding verified: 100% line-number claims cross-checked ke kode nyata
    (vendor_portal.py 460 baris, VendorAccountsAdminModule.jsx 358 baris,
    marketing_import.py _convert_value @265, rahaza_posting.py
    post_wip_to_fg_on_job_complete @1591 dan _on_wo_complete @900).
  - Update angka: 169 file toLocaleString (any locale), 138 khusus id-ID,
    169 file <input type="number"> — clarified metric ambiguity di v1.
  - Klarifikasi Item 3.1: "TIDAK dipanggil dari mana pun" → sebenarnya callers
    ada di _archive/rahaza_multistage/rahaza_work_orders.py:539,541,579,580
    tapi archive TIDAK di-load di server.py (verified). De-facto orphan.
  - Anti-duplikat check confirmed: /lib/formatNumber.js dan
    /components/ui/CurrencyInput.jsx BELUM ada (grep proof).
  - Struktur ditingkatkan: TOC, Cara pakai, AC checklist per item,
    Verifikasi cepat (curl), Testing contract, Files touched checklist,
    Dependency graph, Change log.
  - I-VP-1..I-VP-5 invariant formalized untuk Item 1.
  - Cross-refs ditambah ke GUIDELINE_CMT_FLOW.md, HANDOFF_NEXT_AGENT.md,
    SSOT_MASTER_REPAIR_PLAN_PART5.md, plan.md.
  - Doc size: v1=286 → v2=~950 baris (3.3x). Bloat justified karena
    2x lebih banyak konten actionable (AC checklists, curl commands,
    testing skenario) — bukan filler.
  Files: /app/BACKLOG_PLAN.md
  Verification: audit forensik ke kode 2026-07-16 (semua grounded claim tercatat
    di narasi item). Klaim untuk verifikasi hasil kerja BACKLOG belum ada
    (0 pekerjaan dieksekusi dari BACKLOG ini di sesi audit).

[2026-07-16 E2] Item CMT-flow Phase A → COMPLETED via GUIDELINE_CMT_FLOW.md §9.
  - Not in scope BACKLOG_PLAN.md tapi worth mentioning karena user prioritized.
  - Detail lengkap di /app/memory/GUIDELINE_CMT_FLOW.md §15 Change Log.
  Files: (see GUIDELINE_CMT_FLOW.md)
  Verification: testing_agent_v3 iteration_110.json = 96% (25/26), 0 critical.
```

---

**End of BACKLOG_PLAN.md v2.0.0**
