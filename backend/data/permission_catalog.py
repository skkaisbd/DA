"""
permission_catalog.py — SSOT (satu sumber kebenaran) katalog izin RBAC.

MENGAPA FILE INI ADA
--------------------
Sebelumnya katalog izin ditulis inline di dalam `routes/admin.py` (endpoint
`GET /api/permissions`) dan UI punya dua tempat berbeda untuk mengaturnya
(dialog "Edit Role" + "Matriks Role & Permission"). Itu membuat owner bingung
dan mudah tidak sinkron. Sekarang:

  * katalog izin  -> HANYA di file ini
  * UI pengaturan -> HANYA `frontend/src/components/erp/RoleManagementModule.jsx`
  * jalur simpan  -> HANYA `POST/PUT /api/roles`

STRUKTUR
--------
`PERMISSION_CATALOG` = daftar portal (sesuai `routes/shared.PORTAL_ACCESS` dan
`frontend/src/components/erp/portal-shell/portalNav.js`). Tiap portal punya
modul, tiap modul punya izin dengan metadata:

  key         : kunci izin yang dipakai kode (`<domain>.<aksi>`)
  action      : jenis aksi — dipakai UI untuk pilihan cepat per modul
                ("Tidak ada" / "Lihat saja" / "Penuh") tanpa mencentang satu-satu
  description : keterangan bahasa Indonesia yang dibaca owner

ATURAN `action`
---------------
  view    : hanya melihat / membaca (masuk preset "Lihat saja")
  input   : mencatat data harian (operator) — bukan approval
  manage  : membuat/ubah/hapus (kelola penuh)
  approve : menyetujui / menolak dokumen orang lain
  run     : menjalankan proses berat (mis. payroll)
  export  : mengunduh / mencetak

JANGAN membuat katalog kedua di frontend. Frontend membaca
`GET /api/permissions?grouped=1`.
"""
from __future__ import annotations

# (key, action, description)
PERMISSION_CATALOG: list[dict] = [
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "sysadmin",
        "portal_label": "Administrasi Sistem",
        "modules": [
            {
                "id": "users", "label": "Pengguna & Peran",
                "perms": [
                    ("users.view", "view", "Lihat daftar pengguna"),
                    ("users.manage", "manage", "Buat / ubah / hapus pengguna"),
                    ("roles.manage", "manage", "Kelola peran & hak akses (layar ini)"),
                ],
            },
            {
                "id": "audit", "label": "Log & Jejak Audit",
                "perms": [
                    ("activity.view", "view", "Lihat log aktivitas pengguna"),
                    ("audit.view", "view", "Lihat jejak audit perubahan data"),
                ],
            },
            {
                "id": "sysconfig", "label": "Pengaturan Sistem",
                "perms": [
                    ("settings.manage", "manage", "Kelola profil & pengaturan perusahaan"),
                    ("pdf.manage", "manage", "Kelola template / kop dokumen PDF"),
                    ("docnum.manage", "manage", "Kelola format penomoran dokumen & SKU"),
                    ("notifications.view", "view", "Lihat notifikasi sistem"),
                    ("backup.manage", "manage", "Backup & restore basis data"),
                ],
            },
            {
                "id": "sysadmin_portal", "label": "Akses Portal Administrasi",
                "perms": [
                    ("sysadmin.view", "view", "Buka Portal Administrasi Sistem"),
                    ("sysadmin.manage", "manage", "Ubah data di Portal Administrasi Sistem"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "management",
        "portal_label": "Manajemen",
        "modules": [
            {
                "id": "dashboard", "label": "Dashboard & Laporan",
                "perms": [
                    ("dashboard.view", "view", "Lihat dashboard ringkasan"),
                    ("report.view", "view", "Lihat laporan manajemen"),
                    ("report.export", "export", "Unduh / cetak laporan"),
                ],
            },
            {
                "id": "products", "label": "Master Produk",
                "perms": [
                    ("products.view", "view", "Lihat data produk"),
                    ("products.create", "manage", "Tambah produk baru"),
                    ("products.edit", "manage", "Ubah data produk"),
                    ("products.delete", "manage", "Hapus produk"),
                ],
            },
            {
                "id": "customers", "label": "Pelanggan & Buyer",
                "perms": [
                    ("customers.view", "view", "Lihat data pelanggan / buyer"),
                    ("customers.manage", "manage", "Kelola pelanggan / buyer"),
                ],
            },
            {
                "id": "purchasing", "label": "Pengadaan (PO Pembelian)",
                "perms": [
                    ("po.view", "view", "Lihat PO pembelian"),
                    ("po.create", "manage", "Buat PO pembelian"),
                    ("po.edit", "manage", "Ubah PO pembelian"),
                    ("po.delete", "manage", "Hapus PO pembelian"),
                    ("purchasing.manage", "manage", "Kelola seluruh proses pengadaan"),
                    ("purchasing.approve", "approve", "Setujui / tolak PO pembelian"),
                ],
            },
            {
                "id": "management_portal", "label": "Akses Portal Manajemen",
                "perms": [
                    ("management.view", "view", "Buka Portal Manajemen"),
                    ("management.manage", "manage", "Ubah data di Portal Manajemen"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "production",
        "portal_label": "Produksi",
        "modules": [
            {
                "id": "prod_dashboard", "label": "Dashboard Produksi",
                "perms": [
                    ("prod.dashboard.view", "view", "Lihat dashboard produksi"),
                    ("prod.wip.view", "view", "Lihat WIP (barang dalam proses)"),
                ],
            },
            {
                "id": "prod_master", "label": "Master Produksi",
                "perms": [
                    ("prod.master.manage", "manage", "Kelola master mesin, shift & line"),
                ],
            },
            {
                "id": "prod_line", "label": "Line & Output Harian",
                "perms": [
                    ("prod.line.view", "view", "Lihat papan line produksi"),
                    ("prod.line.manage", "manage", "Kelola line & penugasan"),
                    ("prod.process.input", "input", "Catat output per proses"),
                    ("operator.view", "view", "Buka Layar Operator"),
                    ("operator.input", "input", "Input output line (operator)"),
                ],
            },
            {
                "id": "orders", "label": "Order & Work Order",
                "perms": [
                    ("orders.view", "view", "Lihat order produksi"),
                    ("orders.manage", "manage", "Kelola order produksi"),
                    ("wo.view", "view", "Lihat Work Order"),
                    ("wo.manage", "manage", "Kelola Work Order"),
                    ("bom.view", "view", "Lihat BOM"),
                    ("bom.manage", "manage", "Kelola BOM"),
                ],
            },
            {
                "id": "cmt", "label": "CMT (Vendor Jahit)",
                "perms": [
                    ("cmt.view", "view", "Lihat data & progres vendor CMT"),
                    ("cmt.intake.manage", "manage", "Kelola penerimaan (intake) hasil CMT"),
                    ("cmt.belanja.manage", "manage", "Kelola belanja / biaya CMT"),
                    ("cmt.kejar.manage", "manage", "Kelola program kejar target CMT"),
                    ("cmt.permak.manage", "manage", "Kelola permak / rework CMT"),
                    ("cmt.approve", "approve", "Setujui dokumen CMT (permak, retur)"),
                ],
            },
            {
                "id": "shipment", "label": "Pengiriman & Surat Jalan",
                "perms": [
                    ("shipment.view", "view", "Lihat surat jalan / pengiriman"),
                    ("shipment.create", "manage", "Buat surat jalan"),
                    ("shipment.update", "manage", "Ubah surat jalan"),
                    ("shipment.delete", "manage", "Hapus surat jalan"),
                    ("shipment.manage", "manage", "Kelola seluruh pengiriman"),
                    ("shipment.dispatch", "approve", "Kirim (dispatch) & tandai diterima"),
                    ("vendor_shipment.create", "manage", "Buat surat jalan ke vendor"),
                    ("vendor_shipment.update", "manage", "Ubah surat jalan vendor"),
                    ("vendor_shipment.delete", "manage", "Hapus surat jalan vendor"),
                ],
            },
            {
                "id": "production_portal", "label": "Akses Portal Produksi",
                "perms": [
                    ("production.view", "view", "Buka Portal Produksi"),
                    ("production.manage", "manage", "Ubah data di Portal Produksi"),
                    ("production.approve", "approve", "Setujui dokumen produksi"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "cutting",
        "portal_label": "Cutting",
        "modules": [
            {
                "id": "cutting_ops", "label": "Perintah & Hasil Cutting",
                "perms": [
                    ("cutting.view", "view", "Lihat perintah & hasil cutting"),
                    ("cutting.input", "input", "Catat hasil / bundling cutting"),
                    ("cutting.manage", "manage", "Kelola perintah cutting & alokasi kain"),
                    ("cutting.approve", "approve", "Setujui selisih / penutupan cutting"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "warehouse",
        "portal_label": "Gudang",
        "modules": [
            {
                "id": "wh_receiving", "label": "Penerimaan Barang",
                "perms": [
                    ("wh.receiving.view", "view", "Lihat penerimaan barang"),
                    ("wh.receiving.manage", "manage", "Kelola penerimaan barang & QC masuk"),
                ],
            },
            {
                "id": "wh_storage", "label": "Put-away, Bin & Opname",
                "perms": [
                    ("wh.putaway.manage", "manage", "Kelola put-away (penempatan barang)"),
                    ("wh.bin.manage", "manage", "Kelola lokasi / bin gudang"),
                    ("wh.opname.manage", "manage", "Kelola stock opname"),
                    ("wh.opname.approve", "approve", "Setujui hasil opname & penyesuaian stok"),
                ],
            },
            {
                "id": "inv_material", "label": "Material & Stok",
                "perms": [
                    ("inv.material.view", "view", "Lihat master material"),
                    ("inv.material.manage", "manage", "Kelola master material & satuan"),
                    ("inv.stock.view", "view", "Lihat stok & pergerakan barang"),
                    ("inv.stock.manage", "manage", "Sesuaikan stok & pergerakan barang"),
                ],
            },
            {
                "id": "inv_issue", "label": "Pengeluaran Material (MI)",
                "perms": [
                    ("inv.material_issue.manage", "manage", "Buat pengeluaran material ke WO"),
                    ("inventory.approve", "approve", "Setujui pengeluaran material (MI)"),
                    ("inventory.manage", "manage", "Kelola seluruh proses inventori"),
                ],
            },
            {
                "id": "warehouse_portal", "label": "Akses Portal Gudang",
                "perms": [
                    ("warehouse.view", "view", "Buka Portal Gudang"),
                    ("warehouse.manage", "manage", "Ubah data di Portal Gudang"),
                    ("warehouse.approve", "approve", "Setujui dokumen gudang"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    # 2026-08-06 — PORTAL PENGADAAN. Sebelumnya izin pembelian menempel di
    # `warehouse_portal` / `finance` sehingga pemberian akses "beli barang"
    # memaksa membuka seluruh Portal Gudang/Keuangan. Sekarang berdiri sendiri.
    {
        "portal": "procurement",
        "portal_label": "Pengadaan",
        "modules": [
            {
                "id": "proc_supplier", "label": "Master Supplier & Daftar Harga",
                "perms": [
                    ("proc.supplier.view", "view", "Lihat master supplier & daftar harga"),
                    ("proc.supplier.manage", "manage", "Kelola master supplier, daftar harga & aktivasi"),
                ],
            },
            {
                "id": "proc_pr", "label": "Permintaan Pengadaan (PR)",
                "perms": [
                    ("proc.pr.view", "view", "Lihat permintaan pengadaan"),
                    ("proc.pr.manage", "manage", "Buat & ubah permintaan pengadaan"),
                    ("proc.pr.approve", "approve", "Setujui permintaan pengadaan (tahap departemen)"),
                    # 2026-08-07 — tahap FINAL dipisah izinnya supaya "satu orang
                    # tidak boleh menyetujui dua tahap" bisa ditegakkan: izin
                    # tahap keuangan (`finance.approve`) TIDAK boleh sekaligus
                    # membuka tahap final.
                    ("proc.pr.final_approve", "approve",
                     "Persetujuan FINAL permintaan pengadaan bernilai besar (direksi)"),
                ],
            },
            {
                "id": "proc_po", "label": "Purchase Order",
                "perms": [
                    ("proc.po.view", "view", "Lihat purchase order"),
                    ("proc.po.manage", "manage", "Buat & ubah purchase order"),
                    ("proc.po.approve", "approve", "Setujui purchase order"),
                ],
            },
            {
                "id": "proc_match", "label": "Rekonsiliasi 3-Arah & Faktur Supplier",
                "perms": [
                    ("proc.match.view", "view", "Lihat rekonsiliasi PO–Penerimaan–Faktur"),
                    ("proc.match.manage", "manage", "Proses rekonsiliasi & faktur supplier"),
                    ("proc.match.approve", "approve", "Setujui faktur supplier untuk dibayar"),
                ],
            },
            {
                "id": "procurement_portal", "label": "Akses Portal Pengadaan",
                "perms": [
                    ("purchasing.view", "view", "Buka Portal Pengadaan"),
                    ("purchasing.manage", "manage", "Ubah data di Portal Pengadaan"),
                    ("purchasing.approve", "approve", "Setujui dokumen pengadaan"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "accessories",
        "portal_label": "Aksesoris",
        "modules": [
            {
                "id": "acc_ops", "label": "Stok & Permintaan Aksesoris",
                "perms": [
                    ("accessories.view", "view", "Lihat stok & permintaan aksesoris"),
                    ("wh.accessory.manage", "manage", "Kelola stok, opname & pinjam aksesoris"),
                    ("accessories.approve", "approve", "Setujui permintaan / pengeluaran aksesoris"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "finance",
        "portal_label": "Keuangan",
        "modules": [
            {
                "id": "fin_ar_ap", "label": "Piutang (AR) & Hutang (AP)",
                "perms": [
                    ("fin.ar.view", "view", "Lihat piutang (AR)"),
                    ("fin.ar.manage", "manage", "Kelola piutang (AR)"),
                    ("fin.ap.view", "view", "Lihat hutang (AP)"),
                    ("fin.ap.manage", "manage", "Kelola hutang (AP)"),
                ],
            },
            {
                "id": "fin_invoice", "label": "Invoice & Pembayaran",
                "perms": [
                    ("fin.invoice.view", "view", "Lihat invoice"),
                    ("fin.invoice.manage", "manage", "Kelola invoice"),
                    ("fin.approval.manage", "approve", "Setujui permintaan ubah invoice"),
                    ("fin.payment.view", "view", "Lihat pembayaran"),
                    ("fin.payment.manage", "manage", "Kelola pembayaran"),
                ],
            },
            {
                "id": "fin_cash", "label": "Kas, Bank & Biaya",
                "perms": [
                    ("fin.cash.view", "view", "Lihat kas & bank"),
                    ("fin.cash.manage", "manage", "Kelola kas & bank"),
                    ("fin.expense.view", "view", "Lihat pengeluaran / biaya"),
                    ("fin.expense.manage", "manage", "Kelola pengeluaran / biaya"),
                    ("fin.costcenter.manage", "manage", "Kelola cost center"),
                ],
            },
            {
                "id": "fin_book", "label": "Jurnal, Periode & HPP",
                "perms": [
                    ("fin.recap.view", "view", "Lihat rekap keuangan"),
                    ("hpp.view", "view", "Lihat HPP / costing"),
                    ("hpp.manage", "manage", "Kelola HPP & parameter costing"),
                    ("finance.manage", "manage", "Kelola jurnal, COA & periode"),
                    ("finance.approve", "approve", "Setujui posting jurnal & tutup periode"),
                ],
            },
            {
                "id": "finance_portal", "label": "Akses Portal Keuangan",
                "perms": [
                    ("finance.view", "view", "Buka Portal Keuangan"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "hr",
        "portal_label": "SDM / HRIS",
        "modules": [
            {
                "id": "hr_core", "label": "Karyawan & Absensi",
                "perms": [
                    ("hr.dashboard.view", "view", "Lihat dashboard SDM"),
                    ("hr.employee.view", "view", "Lihat data karyawan"),
                    ("hr.employee.manage", "manage", "Kelola data karyawan"),
                    ("hr.attendance.manage", "manage", "Kelola absensi, shift & izin"),
                    ("hr.approve", "approve", "Setujui izin, cuti, lembur & klaim"),
                ],
            },
            {
                "id": "hr_payroll", "label": "Payroll & Gaji",
                "perms": [
                    ("hr.payroll.view", "view", "Lihat payroll & slip gaji"),
                    ("hr.payroll.run", "run", "Jalankan payroll (borongan/mingguan/bulanan)"),
                    ("payroll.manage", "manage", "Kelola pengaturan payroll"),
                    ("salary.manage", "manage", "Kelola struktur & penyesuaian gaji"),
                ],
            },
            {
                "id": "hr_portal", "label": "Akses Portal SDM",
                "perms": [
                    ("hr.view", "view", "Buka Portal SDM / HRIS"),
                    ("hr.manage", "manage", "Ubah data di Portal SDM / HRIS"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "maklon",
        "portal_label": "Maklon",
        "modules": [
            {
                "id": "maklon_ops", "label": "Order, Quote & Klien Maklon",
                "perms": [
                    ("maklon.view", "view", "Lihat order & klien maklon"),
                    ("maklon.manage", "manage", "Kelola order, quote & penagihan maklon"),
                    ("maklon.approve", "approve", "Setujui quote / penagihan maklon"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "toko",
        "portal_label": "Marketing / Toko",
        "modules": [
            {
                "id": "toko_ops", "label": "Penjualan, Konten & KOL",
                "perms": [
                    ("toko.view", "view", "Lihat data marketing & penjualan"),
                    ("toko.manage", "manage", "Kelola katalog, konten, KOL & target"),
                    ("toko.approve", "approve", "Setujui diskon, retur & komplain"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "rnd",
        "portal_label": "RnD & Desain",
        "modules": [
            {
                "id": "rnd_ops", "label": "Sample, Tech Pack & Costing",
                "perms": [
                    ("rnd.view", "view", "Lihat sample, tech pack & costing"),
                    ("rnd.manage", "manage", "Kelola riset material, tech pack & costing"),
                    ("rnd.approve", "approve", "Setujui sample & HPP sample"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "assets",
        "portal_label": "Manajemen Aset",
        "modules": [
            {
                "id": "assets_ops", "label": "Aset & Penyusutan",
                "perms": [
                    ("assets.view", "view", "Lihat daftar aset"),
                    ("assets.manage", "manage", "Kelola aset, penyusutan & pelepasan"),
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "portal": "collaboration",
        "portal_label": "Kolaborasi & Portal Saya",
        "modules": [
            {
                "id": "collab_ops", "label": "Kolaborasi, Tugas & LMS",
                "perms": [
                    ("collaboration.view", "view", "Buka Portal Kolaborasi"),
                    ("collaboration.manage", "manage", "Kelola pengumuman, tugas & materi"),
                    ("self.view", "view", "Buka Portal Saya"),
                ],
            },
        ],
    },
]

# Aksi yang dianggap "hanya melihat" untuk preset cepat di UI.
VIEW_ACTIONS = ("view",)


def grouped_permissions() -> list[dict]:
    """Katalog bentuk bersarang (portal -> modul -> izin) untuk UI baru."""
    out: list[dict] = []
    for grp in PERMISSION_CATALOG:
        modules = []
        for mod in grp["modules"]:
            modules.append({
                "id": mod["id"],
                "label": mod["label"],
                "permissions": [
                    {
                        "key": key,
                        "action": action,
                        "description": desc,
                        "module": mod["label"],
                        "module_id": mod["id"],
                        "portal": grp["portal"],
                        "portal_label": grp["portal_label"],
                    }
                    for (key, action, desc) in mod["perms"]
                ],
            })
        out.append({
            "portal": grp["portal"],
            "portal_label": grp["portal_label"],
            "modules": modules,
        })
    return out


def flat_permissions() -> list[dict]:
    """Katalog bentuk datar — kompatibel dengan pemakai `GET /api/permissions` lama.

    Bentuk lama: {key, module, description}. Kita tetap kirim ketiganya, plus
    metadata tambahan (`action`, `portal`, `portal_label`) yang aman diabaikan.
    """
    rows: list[dict] = []
    seen: set[str] = set()
    for grp in grouped_permissions():
        for mod in grp["modules"]:
            for p in mod["permissions"]:
                if p["key"] in seen:
                    continue
                seen.add(p["key"])
                rows.append(p)
    return rows


def all_permission_keys() -> set[str]:
    return {p["key"] for p in flat_permissions()}


def validate_keys(keys) -> list[str]:
    """Saring kunci izin agar hanya yang ada di katalog yang tersimpan.

    `*` (super) tetap diizinkan supaya owner bisa memberi akses penuh.
    """
    valid = all_permission_keys()
    out: list[str] = []
    for k in keys or []:
        k = str(k).strip()
        if not k:
            continue
        if k == "*" or k in valid:
            if k not in out:
                out.append(k)
    return out
