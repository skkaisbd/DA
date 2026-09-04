# RBAC — KONSOLIDASI SATU TEMPAT (2026-08-06)

> Dokumen ini melengkapi `memory/RBAC_AUDIT.md` (laporan discovery lama) dengan
> **keputusan & implementasi** sesi 2026-08-06.

## Masalah yang dilaporkan owner
1. **Dua tempat mengatur akses** → bingung mana yang benar:
   * tab **Peran** → dialog "Edit Role" berisi chip permission
   * tab **Hak Akses** → **Matriks Role & Permission** (tabel raksasa)
2. Matriks terlalu besar/sulit dipakai (13+ kolom peran × 129 baris izin).
3. Izin yang dicentang **tidak mengubah kemampuan aksi** karena API masih
   memakai penjaga hardcode role.

## Keputusan owner (terkonfirmasi lewat tanya-jawab)
| # | Keputusan |
|---|---|
| 1 | Matriks **dihapus**, diganti layout master–detail per peran di modul yang sudah ada |
| 2 | Penegakan API memakai model **fallback aman** |
| 3 | Role `admin_gudang` **direset** ke akses penuh (sesi lalu dibatasi untuk uji) |
| 4 | Fitur AI **di-skip** |

## Arsitektur setelah perubahan

### Satu katalog izin (SSOT)
`backend/data/permission_catalog.py` — 129 izin, tersusun **portal → modul → izin**
dengan metadata `action` (`view` / `input` / `manage` / `approve` / `run` / `export`).
Metadata inilah yang memungkinkan pilihan cepat **Tidak ada / Lihat saja / Penuh**
dan preset **Lihat saja / Operator / Approver / Penuh** tanpa daftar hardcode di UI.

```
GET /api/permissions            -> bentuk datar (kompatibel pemakai lama)
GET /api/permissions?grouped=1  -> bentuk bersarang (dipakai UI baru)
```

### Satu jalur simpan
```
POST   /api/roles         { name, description, portals, hidden_modules, permissions }
PUT    /api/roles/{id}    { name?, description?, portals?, hidden_modules?, permissions? }
DELETE /api/roles/{id}    (ditolak bila masih dipakai pengguna)
GET    /api/roles         + portals, hidden_modules, permission_keys, user_count
GET    /api/roles/audit?role_id=...
```
**DIHAPUS** (jalur simpan kedua yang membingungkan):
`PUT /api/roles/{id}/permissions` dan `POST /api/roles/matrix/bulk`.

Kunci izin divalidasi terhadap katalog (`validate_keys`) → tidak ada izin "hantu"
yang tersimpan di DB.

### Satu mesin penegakan (`backend/routes/shared.py`)
```python
user_permissions(user)                 # izin role + izin tambahan per orang
perms_configured(user)                 # apakah owner sudah mengatur izin role ini
has_perm(user, *keys)                  # cek murni (super role & "*" lolos)
can_act(user, *keys, legacy_roles, legacy_any)   # cek + fallback aman (sync)
require_perm(request, *keys, ...)      # gerbang async -> 403 bila tidak boleh
require_perm_dep(*keys, ...)           # dependency FastAPI
```

**Model fallback aman** (urutan pemeriksaan):
1. super role (`superadmin`/`admin`/`owner`) atau izin `*` → lolos
2. role punya salah satu izin yang diminta → lolos
3. izin role **masih kosong** → pakai `legacy_roles` (atau `legacy_any=True` untuk
   endpoint yang dulu terbuka bagi semua user login) → **tidak ada fitur yang mati**
4. selain itu → 403

Konsekuensi yang **disengaja**: begitu owner mencentang minimal satu izin untuk
sebuah peran, daftar izin itulah yang berlaku (aturan legacy berhenti untuk peran
tersebut). UI memberi peringatan kuning yang eksplisit soal ini.

### Cache izin
`auth.require_auth` mengisi `_role_perms`, `_extra_permissions`, `_permissions`
dengan cache proses TTL **20 detik** + invalidasi eksplisit `bump_rbac_cache()`
yang dipanggil endpoint create/update/delete role & update user.

## Endpoint yang sudah dipindah ke gerbang terpusat
| Berkas | Penjaga | Izin | Fallback role legacy |
|---|---|---|---|
| `rahaza_inventory_shared.py` | `_require_mi_approver` | `inventory.approve`, `warehouse.approve` | manager, ppic, warehouse_manager, production_manager |
| `cutting.py` | `_require_cutting_user` | `cutting.manage`, `cutting.input`, `warehouse.manage` | spv_cuting, operator_cuting, supervisor_produksi, admin_produksi, supervisor, admin_gudang |
| `cmt_intake.py` | `_require_admin` | `cmt.view`, `cmt.intake.manage`, `production.manage` | PROD_ADMIN_ROLES |
| `cmt_belanja.py` | `_require_admin` | `cmt.view`, `cmt.belanja.manage`, `production.manage` | PROD_ADMIN_ROLES |
| `cmt_kejar.py` | `_require_admin` | `cmt.view`, `cmt.kejar.manage`, `production.manage` | PROD_ADMIN_ROLES |
| `dewi_cmt_permak.py` | `_require_admin`, `_require_admin_or_vendor` | `cmt.permak.manage`, `cmt.approve`, `cmt.view` | PROD_ADMIN_ROLES (vendor tetap lihat miliknya) |
| `doc_numbering.py` | `_require_admin` | `docnum.manage`, `settings.manage` | superadmin, owner, admin |
| `wms_opname3.py` | 2 gerbang approve | `wh.opname.approve`, `wh.opname.manage`, `warehouse.approve` | APPROVE_ROLES |
| `invoice_edit_requests.py` | `_require_approver` | `fin.approval.manage`, `finance.approve` | admin, owner |
| `hr_approval_inbox.py` | `_require_approver_role` | `hr.approve`, `hr.manage` | hr, manager, hr_manager |
| `wms_putaway.py` | `POST /place` | `wh.putaway.manage`, `warehouse.manage` | `legacy_any=True` (dulu terbuka untuk semua user login) |

Penjaga hardcode lain (±80 berkas) **belum** dipindah — tetap jalan seperti
sebelumnya. Migrasi berikutnya dilakukan bertahap per domain.

## Bukti uji (curl, 2026-08-06)
```
admin_gudang tanpa izin  : POST /api/cutting/orders        -> 400  (lolos gerbang, fallback aman)
admin_gudang tanpa izin  : GET  /api/dewi/cmt-kejar        -> 403  (sama seperti sebelumnya)
admin_gudang + hanya izin `wh.putaway.manage`:
                           POST /api/cutting/orders        -> 403  (izin berlaku)
                           POST /api/wms/putaway/place     -> 404  (lolos gerbang, data dummy)
setelah izin dikosongkan : POST /api/cutting/orders        -> 400  (kembali fallback aman)
```

## UI — satu layar: "Peran & Hak Akses"
`frontend/src/components/erp/RoleManagementModule.jsx` (master–detail):
* kiri: daftar peran + cari + ringkasan (pengguna / portal / izin / menu disembunyikan)
* kanan bertahap: **1** Identitas (+ "Salin dari peran lain") · **2** Portal ·
  **3** Hak Akses (accordion per portal, pilih cepat per modul, chip per izin, preset) ·
  **4** Menu disembunyikan (collapsible) · **5** Riwayat perubahan
* bar simpan dengan indikator "Belum disimpan", tombol **Bandingkan** (sheet selisih izin)
* `RoleMatrixModule.jsx` **dihapus**; `mgmt-role-matrix` diarahkan ke hub tab `roles`
* tab hub Kontrol Akses: **Pengguna** | **Peran & Hak Akses** (dari 3 tab jadi 2)

## Catatan operasional
* Frontend = build statis → jalankan `bash /app/scripts/rebuild_frontend.sh` setelah ubah `frontend/src`.
* Perubahan izin terasa maksimal ~20 detik (TTL cache) atau langsung setelah simpan role.
