// Single source of truth for role → portal access (frontend).
// Keep in sync with backend routes/shared.py PORTAL_ACCESS.
// Portal ids match portalNav.js keys.

// Roles that can access ALL portals.
export const SUPER_ROLES = ['superadmin', 'admin', 'owner'];

// Portals available to every authenticated user regardless of role.
export const ALL_ROLE_PORTALS = ['self', 'collaboration'];

export const PORTAL_ROLES = {
  management:     ['hr_manager', 'manager_produksi', 'manager_keuangan', 'manager_hr', 'manager_marketing'],
  sysadmin:       [],   // super_admin + admin saja
  production:     ['supervisor_produksi', 'admin_produksi', 'ppic', 'operator', 'spv_cuting', 'operator_cuting', 'supervisor'],
  cutting:        ['spv_cuting', 'operator_cuting', 'supervisor_produksi', 'admin_produksi', 'admin_gudang'],
  // 2026-08-06 — Portal Pengadaan. Peran DISELARASKAN dengan penjaga backend
  // `routes/procurement_suppliers.py::_require_procurement` supaya menu yang
  // tampil tidak berujung 403.
  // 2026-08-06 — `admin_aksesoris`/`spv_aksesoris` ikut karena pintu "Request
  // Aksesoris" (pembelian) pindah ke portal ini dan dihapus dari Portal Aksesoris.
  // 2026-08-07 — approver PR wajib bisa membuka portal ini (cermin backend
  // routes/shared.py PORTAL_ACCESS). Tanpa `supervisor_produksi`/`manager`/
  // `director` dst., approver tahap departemen & final tidak bisa mencapai layar
  // "Permintaan Pengadaan" tempat kotak persetujuan berada.
  procurement:    ['admin_pengadaan', 'manager_pengadaan', 'purchasing', 'admin_gudang', 'accounting', 'staff_keuangan', 'manager_keuangan', 'manager_produksi', 'supervisor', 'admin_aksesoris', 'spv_aksesoris',
                   'supervisor_produksi', 'manager', 'dept_head', 'manager_hr', 'manager_marketing', 'spv_packing', 'spv_cuting', 'director', 'cfo', 'ceo'],
  warehouse:      ['admin_gudang', 'spv_packing', 'tim_packing', 'admin_aksesoris', 'supervisor'],
  accessories:    ['admin_aksesoris', 'admin_gudang', 'spv_aksesoris'],
  finance:        ['accounting', 'staff_keuangan', 'manager_keuangan'],
  hr:             ['hr', 'hr_manager', 'staff_hr'],
  maklon:         ['admin_maklon', 'admin_produksi', 'supervisor_produksi', 'ppic', 'accounting'],
  toko:           ['pic_toko', 'pic_marketing', 'staff_marketing', 'marketing_kol', 'cs_staff', 'manager_marketing'],
  rnd:            ['rnd_staff', 'manager_produksi', 'supervisor_produksi'],
  assets:         ['accounting', 'manager_keuangan', 'staff_keuangan', 'admin_gudang'],
  collaboration:  [],   // allRoles
  self:           [],   // allRoles
};

// Can a given role open a given portal?
// 2026-08-05 — daftar di atas kini BAWAAN. Bila owner sudah mengatur portal pada
// role (Portal Administrasi Sistem → Manajemen Role), backend mengirim daftar
// portal EFEKTIF saat login / `/auth/me` dan itulah yang dipakai. Disimpan di
// localStorage `erp_access` supaya tidak perlu panggilan ekstra tiap render.
export function readEffectiveAccess() {
  try {
    return JSON.parse(localStorage.getItem('erp_access') || 'null') || null;
  } catch { return null; }
}

export function saveEffectiveAccess({ portals, hidden_modules, is_super } = {}) {
  try {
    localStorage.setItem('erp_access', JSON.stringify({
      portals: portals || [], hidden_modules: hidden_modules || [], is_super: !!is_super,
    }));
  } catch { /* storage penuh/diblokir — jatuh ke bawaan */ }
}

/** Pintu menu yang disembunyikan untuk user aktif (kosong = tampilkan semua). */
export function hiddenModules() {
  const a = readEffectiveAccess();
  return (a && Array.isArray(a.hidden_modules)) ? a.hidden_modules : [];
}

/** Role user aktif (dibaca dari sesi tersimpan, sama pola dgn hiddenModules). */
export function currentRole() {
  try {
    return (JSON.parse(localStorage.getItem('erp_user') || 'null')?.role || '').toLowerCase();
  } catch { return ''; }
}

/**
 * Boleh tidak pintu ini DITAMPILKAN untuk user aktif?
 *
 * Sebagian pintu punya kewenangan lebih sempit daripada portalnya. Contoh nyata:
 * pintu **"Input Vendor CMT"** (mengisi data atas nama vendor CMT) berdampak
 * langsung ke TAGIHAN, jadi owner membatasinya ke admin/admin_produksi/
 * supervisor_produksi/ppic — padahal Portal Produksi juga terbuka untuk
 * `operator`, `spv_cuting`, dan `supervisor`. Tanpa penyaring ini, mereka melihat
 * pintu yang begitu diklik hanya menjawab "tidak berwenang" — menu buntu yang
 * membuat orang mengira sistemnya rusak.
 *
 * Item nav TANPA field `roles` = terbuka untuk semua yang bisa membuka portalnya
 * (perilaku lama, tidak berubah). Ini HANYA soal tampilan; penjaga sungguhan
 * tetap di backend (`core/cmt_override.OVERRIDE_ROLES`).
 */
export function navItemAllowed(item, role) {
  const roles = item?.roles;
  if (!Array.isArray(roles) || roles.length === 0) return true;
  const r = (role || currentRole() || '').toLowerCase();
  if (SUPER_ROLES.includes(r)) return true;
  return roles.map(x => String(x).toLowerCase()).includes(r);
}

export function canAccessPortal(role, portalId) {
  const r = (role || '').toLowerCase();
  if (SUPER_ROLES.includes(r)) return true;
  if (ALL_ROLE_PORTALS.includes(portalId)) return true;
  const acc = readEffectiveAccess();
  if (acc && Array.isArray(acc.portals) && acc.portals.length) {
    return acc.portals.includes(portalId);
  }
  return (PORTAL_ROLES[portalId] || []).includes(r);
}
