"""core.stock_rbac — SSOT daftar role untuk operasi stok sensitif.

Dipindah dari `routes/wms_quarantine.py` (FASE 8) supaya dipakai bersama oleh:
  * karantina QC (lepas / retur / scrap)
  * scrap aksesoris (write-off nilai persediaan)
  * operasi stok lain yang butuh gate serupa

KENAPA SSOT INI PENTING (bug nyata yang pernah terjadi — FASE 6.5 temuan #2):
daftar role sempat diisi nama TEBAKAN (`gudang`, `staff_gudang`, `warehouse`,
`warehouse_manager`, `manajer`, `keuangan`) yang TIDAK ADA di master role (koleksi
`roles`, 21 entri). Karena `auth.check_role` mencocokkan role secara EXACT, role gudang
NYATA (`spv_packing`, `tim_packing`, `admin_aksesoris`) justru selalu 403.
Saat menambah role baru ke portal, WAJIB cek daftar di bawah.

Kebijakan:
  * DISPOSE_ROLES — operasional gudang (lepas/retur/terima/keluarkan).
  * SCRAP_ROLES   — LEBIH KETAT: scrap = write-off nilai persediaan ⇒ hanya penanggung
    jawab (admin gudang, supervisor, keuangan, owner). Tim packing TIDAK boleh.
  * `superadmin` selalu lolos lewat `auth.check_role`.
"""
from __future__ import annotations

# Role yang boleh melepas / meretur / memindahkan barang (operasional gudang)
DISPOSE_ROLES = [
    # role NYATA (ada di master `roles` + PORTAL_ACCESS['warehouse'])
    "admin_gudang", "spv_packing", "tim_packing", "admin_aksesoris",
    "supervisor", "supervisor_produksi", "owner", "admin",
    # alias/legacy — dipertahankan bila instalasi lain memakai nama ini
    "gudang", "staff_gudang", "warehouse", "warehouse_manager", "manajer", "manager",
]

# Role yang boleh SCRAP / write-off nilai persediaan — LEBIH KETAT.
# Sengaja TIDAK memasukkan tim_packing / spv_packing / admin_aksesoris.
SCRAP_ROLES = [
    # role NYATA
    "admin_gudang", "supervisor", "supervisor_produksi", "accounting",
    "manager_keuangan", "owner", "admin",
    # alias/legacy
    "warehouse_manager", "manajer", "manager", "finance", "keuangan", "staff_keuangan",
]

SCRAP_FORBIDDEN_MSG = (
    "Scrap = write-off nilai persediaan. Hanya Admin Gudang, Supervisor, Keuangan, "
    "atau Owner yang boleh melakukannya. Silakan ajukan ke atasan Anda."
)
