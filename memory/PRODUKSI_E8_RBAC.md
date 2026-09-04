# E8 — RBAC : Role SOMMERVILLE vs Role DA (AS-IS vs TO-BE)
> Handoff §E8. GROUNDED: `backend/auth.py` (DA), `/tmp/sommerville/backend/auth.py` + `check_role`
> (SOMMERVILLE). STATUS: ANALISIS.

## 0. TEMUAN INTI
> **SCOPE (LOCKED, arahan user)**: modul **akun/user/auth/role SOMMERVILLE = SKIP** (pakai DA `auth.py`).
> Yang diadopsi terkait RBAC hanya **pemetaan role untuk portal VENDOR (CMT)** yang diadopsi. Karena
> SOMMERVILLE auth tidak diport, RBAC-1 otomatis condong ke **Opsi B** (pertahankan model DA).
- **SOMMERVILLE = 4 role** (`superadmin/admin/vendor/buyer`) + koleksi `roles`/`role_permissions`/`permissions`.
  Endpoint produksi pakai `check_role(user, ['admin'])` / `['vendor']` / `['buyer']`.
- **DA = portal-based RBAC**: 21 custom role di `roles` + built-in `superadmin/admin/vendor/cmt_vendor/buyer`.
  **`role_permissions` KOSONG** → custom role LULUS akses HANYA via **daftar role-string hardcode per-endpoint**
  (`check_role(user, [<allowed>])`); superadmin/admin bypass (`auth.py:95-107`).
- ⚠️ **Konsekuensi porting**: endpoint SOMMERVILLE (`['admin']`/`['vendor']`/`['buyer']`) bila dipasang di DA
  **AKAN 403** untuk role DA (admin_produksi/cmt_vendor/klien_maklon) kecuali daftar allowed_roles di-remap.
  (Sudah terbukti 2 bug nyata Sesi #24: expense `finance`→`accounting`; WO `_require_admin`→tambah role produksi.)

## 1. DA ROLES (default seed `auth.py:160-190`)
| Portal | Role DA |
|---|---|
| Produksi | supervisor_produksi, admin_produksi, operator, spv_cuting, operator_cuting, rnd_staff |
| Gudang | admin_gudang, spv_packing, tim_packing, admin_aksesoris |
| SDM | hr, hr_manager |
| Keuangan | accounting, staff_keuangan |
| Maklon | admin_maklon, klien_maklon (view only) |
| Toko/Marketing | pic_toko, marketing_kol, cs_staff |
| Legacy | owner, supervisor |
| Built-in | superadmin, admin, vendor, **cmt_vendor** (link `cmt_vendor_id`), buyer |
Akun uji: admin@garment.com(superadmin); hr/finance(accounting)/spv(supervisor_produksi)/gudang(admin_gudang)/maklon(admin_maklon)@dewiaditya.id.

## 2. PEMETAAN ROLE SOMMERVILLE → DA (untuk port produksi)
| SOMMERVILLE | Peran di flow | DA — PRODUKSI internal | DA — MAKLON |
|---|---|---|---|
| `admin` | buat PO, kirim material, invoice, kelola job | `admin_produksi` / `supervisor_produksi` (+admin/superadmin) | `admin_maklon` |
| `vendor` | terima material, inspeksi, catat progress, kirim FG, variance | operator/lini internal **ATAU** `cmt_vendor` (bila outsource jahit) | `cmt_vendor` (subcontract) |
| `buyer` | terima FG, retur | customer marketplace (via Marketing/`pic_toko`; retur → after-sales R3) | `klien_maklon` (view/terima) |
| `superadmin` | full | `superadmin` | `superadmin` |

## 3. PERBEDAAN MODEL
| Aspek | SOMMERVILLE | DA |
|---|---|---|
| Jumlah role | 4 | 21 custom + 5 built-in |
| Mekanisme | permission-based (`role_permissions` terisi) | **role-string hardcode** per endpoint (`role_permissions` KOSONG) |
| Portal | switch by role (App.js) | portal shell + deep-link guard (`LEGACY_MODULE_TO_PORTAL`) |
| Vendor login | role `vendor` | `cmt_vendor` (+`cmt_vendor_id`) / `klien_maklon` |

## 4. TO-BE (saat port endpoint SOMMERVILLE)
1. **Remap `check_role`** setiap endpoint yang diport:
   - Produksi: `['admin']` → `['admin','superadmin','admin_produksi','supervisor_produksi']`.
   - Vendor step: `['vendor']` → `['cmt_vendor','operator','admin_produksi','supervisor_produksi']` (sesuai siapa yg catat progress).
   - Maklon: gunakan `['admin_maklon',...]` + `cmt_vendor` utk subcontract; `klien_maklon` view.
2. **Konsistensi portal**: modul baru daftarkan di `moduleRegistry.js` + `portalNav.js` + (bila konsolidasi)
   `LEGACY_MODULE_TO_PORTAL` (App.js) — sesuai pola DA.
3. **cmt_vendor**: pertahankan linking `cmt_vendor_id`; owner `business_type` (D4/E4) menegaskan internal vs maklon.

## 5. DECISION POINTS
### ⚠️ RBAC-1 (PERLU KEPUTUSAN) — permission model
- **Opsi A** — Isi `role_permissions` (permission-based, seperti SOMMERVILLE) → `check_role(perm_key=...)`
  jadi sumber kebenaran. Lebih bersih & scalable, tapi butuh definisi permission menyeluruh.
- **Opsi B** — Tetap **role-string hardcode** per endpoint (status quo DA). Cepat, tapi rawan bug 403
  (harus ingat remap tiap endpoint baru).
- **Rekomendasi**: **B untuk sekarang** (konsisten dgn DA, cepat); pertimbangkan A sebagai perapihan lanjutan.
  Apa pun pilihannya: **saat port endpoint SOMMERVILLE, WAJIB remap allowed_roles** (lihat §4.1).

### RBAC-2 (checklist port)
Buat daftar endpoint SOMMERVILLE yang diport + role DA yang diizinkan (audit sebelum go-live) supaya
tak ada 403 tersembunyi. Uji tiap role via `curl` (murah, tanpa build FE).

## 6. INVARIAN
- superadmin/admin selalu lolos (bypass).
- Klien maklon = VIEW ONLY (jangan beri write PO/job).
- cmt_vendor hanya akses job/shipment miliknya (filter `vendor_id`/`cmt_vendor_id`).

---
*E8 selesai. Lanjut E9 (Aksesoris).*
