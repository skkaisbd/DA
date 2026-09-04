import { useState, useEffect, useCallback, Suspense, useMemo, lazy } from 'react';
import './App.css';
import Login from './components/erp/Login';
import PortalSelector from './components/erp/PortalSelector';
import PortalShell from './components/erp/PortalShell';
import { MODULE_REGISTRY, DEFAULT_MODULE } from './components/erp/moduleRegistry';
import { PORTAL_NAV } from './components/erp/portal-shell/portalNav';
import { canAccessPortal } from './components/erp/portalAccess';
import { ThemeProvider, useTheme } from './components/theme/ThemeProvider';
import { Toaster } from './components/ui/sonner';
// BUG DITUTUP 2026-08-12 — `hooks/use-toast` (shadcn) dipakai 57 modul (termasuk
// Wizard Impor Data & dashboard marketing), tetapi <Toaster/> shadcn-nya TIDAK
// PERNAH dipasang di pohon React. Akibatnya SEMUA pesan sukses/gagal modul-modul
// itu hilang tanpa jejak: staf menekan "Simpan", tidak ada tanggapan apa pun di
// layar, lalu menekan lagi (dobel data) atau menyangka aplikasi menggantung.
// Sonner (dipakai modul lain) tetap dipasang — keduanya hidup berdampingan.
import { Toaster as ShadcnToaster } from './components/ui/toaster';
import { TooltipProvider } from './components/ui/tooltip';
import { clientApi } from './components/client/clientApi';
import { configureApi } from './lib/apiFetch';
import ErrorBoundary from './components/ErrorBoundary';
// Pre-Dev Health Check (2026-05-26): RC-2 fix — chunk retry + fallback
import { lazyWithRetry } from './lib/lazyWithRetry';
import { saveEffectiveAccess } from './components/erp/portalAccess';

// Session #11.18 EXTENDED — Performance optimization: lazy-load alternate portal UIs
// Sprint A.0 + Pre-Dev Health Check: wrapped with lazyWithRetry to survive network blips
// FASE 5: OperatorView & ShopFloorTV diarsip (engine multi-stage lama dihapus)
const AIChatbotWidget   = lazy(lazyWithRetry(() => import('./components/erp/AIChatbotWidget'), 'AIChatbotWidget'));
const ClientLogin       = lazy(lazyWithRetry(() => import('./components/client/ClientLogin'), 'ClientLogin'));
const ClientPortalShell = lazy(lazyWithRetry(() => import('./components/client/ClientPortalShell'), 'ClientPortalShell'));
const CreatorPortalApp  = lazy(lazyWithRetry(() => import('./components/creator/CreatorPortalApp'), 'CreatorPortalApp'));
const LiveHostPortalApp = lazy(lazyWithRetry(() => import('./components/livehost/LiveHostPortalApp'), 'LiveHostPortalApp'));
const VendorCMTPortalApp= lazy(lazyWithRetry(() => import('./components/vendor-cmt/VendorCMTEnginePortal'), 'VendorCMTEnginePortal'));
const ClientMaklonPortal= lazy(lazyWithRetry(() => import('./components/client/ClientMaklonPortal'), 'ClientMaklonPortal'));
const AbsenPage         = lazy(lazyWithRetry(() => import('./pages/AbsenPage'), 'AbsenPage'));

// Loading fallback for portal-level Suspense
const PortalLoader = () => (
  <div className="min-h-screen grid place-items-center bg-background">
    <div className="flex flex-col items-center gap-3">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[hsl(var(--primary))]" />
      <p className="text-sm text-muted-foreground">Memuat portal...</p>
    </div>
  </div>
);

// Default module untuk tiap portal
const PORTAL_DEFAULT_MODULE = {
  management: 'management-dashboard',
  sysadmin:   'mgmt-access-hub',   // IA v4 — portal baru, split dari Manajemen (admin/super_admin)
  production: 'production-dashboard',
  cutting:    'cutting-dashboard',   // FASE IA-4 — Portal Cutting (roll kain ➜ potongan)
  warehouse:  'warehouse-dashboard',
  procurement: 'proc-dashboard',   // 2026-08-06 — portal baru, split dari Gudang/Keuangan/Aksesoris
  finance:    'finance-dashboard',
  hr:         'hr-dashboard',
  maklon:     'maklon-dashboard',
  toko:       'toko-dashboard',
  rnd:        'rnd-dashboard',
  self:       'self-dashboard',
  collaboration: 'collaboration',  // NEW: Unified Communication + Workspace + Learning
  assets:     'asset-management',  // IA v4 — satu pintu (sidebar dihapus)
  accessories: 'accessories-dashboard',  // Session #11.21 — Portal Aksesoris
};

const VALID_PORTALS = Object.keys(PORTAL_DEFAULT_MODULE);

// ── ALIAS ID PORTAL (2026-08-13) ────────────────────────────────────────────
// Portal yang di layar bernama **"Marketing"** ber-id `toko` (warisan "Toko
// Online"). Akibat nyata: setiap orang — termasuk agen uji otomatis — menulis
// tautan `?portal=marketing&module=marketing-targets`, id itu tidak dikenal,
// lalu aplikasi diam-diam menampilkan portal terakhir yang tersimpah. Yang
// terlihat oleh pemakai: "modul Target & Budget hilang". Satu sesi uji penuh
// hilang karena ini. Alias memakai NAMA yang tertulis di layar sebagai jalan
// masuk yang sah; id kanoniknya tetap satu.
const PORTAL_ID_ALIASES = {
  marketing: 'toko',
  'toko-online': 'toko',
  tokoonline: 'toko',
  mgmt: 'management',
  manajemen: 'management',
  produksi: 'production',
  gudang: 'warehouse',
  keuangan: 'finance',
  pengadaan: 'procurement',
  aksesoris: 'accessories',
  sdm: 'hr',
  hris: 'hr',
  aset: 'assets',
  'manajemen-aset': 'assets',
  kolaborasi: 'collaboration',
  'portal-kolaborasi': 'collaboration',
  saya: 'self',
  'portal-saya': 'self',
  sistem: 'sysadmin',
  'administrasi-sistem': 'sysadmin',
  administrasi: 'sysadmin',
};

/** Id portal kanonik dari apa pun yang ditulis di URL (id, alias, atau nama). */
function resolvePortalId(raw) {
  const key = String(raw || '').trim().toLowerCase();
  if (!key) return null;
  if (VALID_PORTALS.includes(key)) return key;
  return PORTAL_ID_ALIASES[key] || null;
}

// Session #11.14 — Find which portal "owns" a given moduleId. Used for deep-linking
// via URL hash (e.g. `/#prod-shipments` should auto-open the Production portal
// with that module loaded). For modules removed from sidebar (e.g. deprecated
// modules like `prod-shipments`, `do-management`), this scans the legacy portal
// mappings as a fallback.
//
// Returns the portalId (e.g. 'production') or null if module is unknown.
const LEGACY_MODULE_TO_PORTAL = {
  // P2 Consolidation #12 deprecated modules — kept reachable via direct URL hash
  'prod-shipments': 'production',
  'do-management': 'warehouse',
  // BACKLOG-A: id lama modul yang dikonsolidasi ke hub (redirect di moduleRegistry)
  'fin-journal-entry': 'finance',
  'fin-journal-list': 'finance',
  'hr-ai-insights': 'hr',
  'hr-attrition': 'hr',
  'hr-skill-gap': 'hr',
  'hr-coaching': 'hr',
  'ai-actions': 'hr',
  'marketing-live': 'toko',
  'marketing-live-analytics': 'toko',
  'marketing-livehost': 'toko',
  'marketing-ai-insights': 'toko',
  'marketing-advanced-ai': 'toko',
  'marketing-ai-content': 'toko',
  'marketing-ai-image': 'toko',
  'rnd-costing': 'rnd',
  'rnd-hpp': 'rnd',
  // Session #23 — id lama yang dikonsolidasi ke hub (redirect di moduleRegistry).
  // Wajib dipetakan agar deep-link hash lama tetap resolve portal → makeRedirect jalan.
  // Phase A — Warehouse stock hub (wms-stock-hub)
  'wh-stock': 'warehouse',
  'unified-inventory': 'warehouse',
  'wh-inventory-adjustments': 'warehouse',
  // FASE E1 (Known Issue §5) — monolit "Scanner Barcode" dibubarkan; id lama `wms`
  // & "Lokasi Bin" (`wh-bin`) dihapus dari nav tapi TETAP redirect di moduleRegistry
  // (makeRedirect → 'wh-structure'). Wajib dipetakan ke portal Gudang agar deep-link
  // FRESH (#wms / #wh-bin, mis. dari bookmark/notifikasi) resolve portal dulu →
  // makeRedirect menyala → mendarat di Struktur Gudang (bukan "Pilih Portal").
  'wms': 'warehouse',
  'wh-bin': 'warehouse',
  // Phase B #1 — Production execution hub (prod-exec-hub)
  'prod-exec-sewing': 'production',
  'prod-exec-finishing': 'production',
  'prod-exec-qc': 'production',
  'prod-exec-packing': 'production',
  'prod-exec-rework': 'production',
  'prod-exec-cutting': 'production',
  'prod-exec-rajut': 'production',
  'prod-exec-linking': 'production',
  'prod-exec-steam': 'production',
  'prod-exec-washer': 'production',
  'prod-exec-sontek': 'production',
  // Phase B #2 — HR expense/travel hub (hr-expense-hub)
  'hr-expense-claims': 'hr',
  'hr-travel-requests': 'hr',
  'hr-travel-settlement': 'hr',
  'hr-expense-approval': 'hr',
  'hr-per-diem-config': 'hr',
  // Phase B #3 — HR attendance hub (hr-attendance-hub)
  'hr-attendance': 'hr',
  'hr-auto-attendance': 'hr',
  'hr-attendance-approval': 'hr',
  // Phase B #4 — Finance accounting-adjust hub (fin-acctg-adjust-hub)
  'fin-accruals': 'finance',
  'fin-asset-depreciation': 'finance',
  'fin-bad-debt-writeoff': 'finance',
  'fin-asset-disposal': 'finance',
  'fin-purchase-discount': 'finance',
  // Phase B #5 — RnD design hub (rnd-design-hub)
  'rnd-styles': 'rnd',
  'rnd-variants': 'rnd',
  'rnd-techpack': 'rnd',
  'rnd-patterns': 'rnd',
  'rnd-revisions': 'rnd',
  // RC-FLOW-UX-11d (Session #26) — retur/komplain: 4 pintu legacy → redirect ke marketing-after-sales (portal `toko`)
  'marketing-complaints': 'toko',
  'marketing-returns': 'toko',
  'toko-cs': 'toko',
  'toko-returns': 'toko',
  // ACC-3 — "Peminjaman" dilepas dari nav Portal Aksesoris (pindah ke Manajemen Aset
  // sebagai `asset-loans`). Id lama WAJIB dipetakan supaya bookmark/deep-link
  // `#accessories-loans` tetap resolve portal → modul tampil dengan banner deprecation,
  // bukan mendarat di halaman "Pilih Portal" (pelajaran Known Issue §5).
  'accessories-loans': 'accessories',
  // Master Produk (Model & BOM & Size) — modul nyata `prod-models-bom` TIDAK ada di
  // portalNav (nav memakai hub `prod-master-product-hub`), begitu pula id lama yang
  // di-redirect ke sana. Tanpa pemetaan ini, deep-link `#prod-models-bom` / `#prod-bom`
  // / `#prod-models` / `#prod-sizes` / `#mgmt-products` mendarat di "Pilih Portal".
  // Ditemukan saat verifikasi ACC-2 (2026-07-25).
  'prod-models-bom': 'production',
  'prod-models': 'production',
  'prod-bom': 'production',
  'prod-sizes': 'production',
  'mgmt-products': 'production',
  // 2026-07-25 — 4 id yang TIDAK tertolong heuristik prefix di bawah
  // (`portalFromModulePrefix`) karena namanya tidak berawalan portal. Tanpa entri
  // ini deep-link-nya mendarat di "Pilih Portal". Lihat `scripts/audit_deeplink_portals.py`.
  'admin-setup-panel': 'management',
  'ai-business-dashboard': 'management',
  'procurement-requests': 'procurement',   // alias `fin-procurement-requests` (Pengadaan P2P)
  'fin-procurement-requests': 'procurement',
  'vendor-portal': 'maklon',           // vendor self-service (nav: `vendor-admin`)
  // IA v4 (FASE IA-2) — Portal Aset jadi SATU pintu (`asset-management`). Id lama
  // dilepas dari menu tapi WAJIB tetap resolve ke portal `assets` supaya bookmark
  // `#asset-dashboard` / `#asset-list` / `#asset-procurement` / `#asset-loans`
  // mendarat di tab yang benar, bukan di halaman "Pilih Portal".
  'asset-dashboard': 'assets',
  'asset-list': 'assets',
  'asset-procurement': 'assets',
  'asset-loans': 'assets',
  // 2026-08-06 — PORTAL PENGADAAN: pintu procurement dipindah bersih dari
  // Gudang/Keuangan/Aksesoris. Id lama DIPETAKAN KE PORTAL BARU supaya bookmark,
  // notifikasi, dan tautan di dokumen lama tidak mendarat di "Pilih Portal".
  'wh-purchase-orders': 'procurement',
  'wh-supplier-scorecard': 'procurement',
  'fin-3way-match': 'procurement',
  'accessories-purchase': 'procurement',
};

// Peta PREFIX id modul → portal. Dipakai sebagai LAPIS TERAKHIR saat modul ada di
// MODULE_REGISTRY tapi tidak ditemukan di PORTAL_NAV maupun LEGACY_MODULE_TO_PORTAL.
//
// KENAPA ADA (bug berulang): setiap kali modul dikonsolidasi ke hub / dilepas dari
// sidebar tapi id-nya dipertahankan "untuk deep-link", orang lupa menambahkannya ke
// LEGACY_MODULE_TO_PORTAL ⇒ `https://app/#<id>` mendarat di halaman "Pilih Portal"
// (dead-end) padahal modulnya hidup. Audit 2026-07-25: **121 dari 356 id** terdampak
// (mis. `#hr-performance`). Heuristik prefix menutup 117 di antaranya sekaligus, dan
// otomatis menutup kasus-kasus BARU di masa depan. Alat ukur ulang:
// `python scripts/audit_deeplink_portals.py`.
//
// AMAN karena hanya dipakai SETELAH pencarian nav gagal (tak bisa menimpa lokasi
// nav yang sebenarnya) dan hasilnya tetap lewat guard `canAccessPortal`.
const MODULE_PREFIX_TO_PORTAL = [
  ['management-', 'management'], ['mgmt-', 'management'],
  ['proc-', 'procurement'],
  ['prod-', 'production'], ['production-', 'production'],
  ['cutting-', 'cutting'],
  ['wh-', 'warehouse'], ['wms-', 'warehouse'], ['warehouse-', 'warehouse'],
  ['accessories-', 'accessories'], ['acc-', 'accessories'],
  ['fin-', 'finance'], ['finance-', 'finance'],
  ['hr-', 'hr'], ['payroll-', 'hr'],
  ['rnd-', 'rnd'],
  ['maklon-', 'maklon'], ['cmt-', 'maklon'],
  ['marketing-', 'toko'], ['toko-', 'toko'],
  ['asset-', 'assets'],
  ['collab', 'collaboration'],
  ['self-', 'self'], ['portal-saya', 'self'], ['my-', 'self'],
];

function portalFromModulePrefix(moduleId) {
  if (!moduleId) return null;
  for (const [prefix, portalId] of MODULE_PREFIX_TO_PORTAL) {
    if (moduleId.startsWith(prefix)) return portalId;
  }
  return null;
}

function findPortalForModule(moduleId, roleHint = null) {
  if (!moduleId) return null;
  // 1) Check legacy fallback (deprecated modules removed from sidebar)
  if (LEGACY_MODULE_TO_PORTAL[moduleId]) {
    return LEGACY_MODULE_TO_PORTAL[moduleId];
  }
  // 2) Scan active portal nav sections (supports flat items + nested groups)
  //
  // FASE H-2 (2026-08-16) — KENAPA SEMUA PEMILIK DIKUMPULKAN, BUKAN YANG PERTAMA
  // Satu modul kini bisa punya pintu di BEBERAPA portal (shortcut lintas portal
  // yang disengaja: 'Pengeluaran Material' ada di Gudang DAN Produksi, karena
  // supervisor produksi berhak membuatnya tetapi tidak punya akses Portal Gudang).
  // Mengembalikan portal PERTAMA yang ditemukan membuat urutan deklarasi
  // PORTAL_NAV menentukan takdir tautan: `?module=wh-material-issue` bagi admin
  // gudang mendarat di Portal Produksi yang tidak ia punyai ⇒ dibuang ke "Pilih
  // Portal" tanpa satu pun pesan, dan pemakai menyimpulkan menunya hilang.
  const owners = [];
  for (const [portalId, nav] of Object.entries(PORTAL_NAV || {})) {
    if (!nav || !Array.isArray(nav.sections)) continue;
    for (const section of nav.sections) {
      const items = section.items || [];
      const groups = section.groups || [];
      const inFlat = items.some((it) => it.id === moduleId);
      const inGroup = groups.some((g) => (g.items || []).some((it) => it.id === moduleId));
      if (inFlat || inGroup) { owners.push(portalId); break; }
    }
  }
  if (owners.length > 0) {
    if (owners.length === 1) return owners[0];
    let role = roleHint;
    if (!role) {
      try { role = JSON.parse(localStorage.getItem('erp_user') || '{}')?.role || null; }
      catch (e) { role = null; }
    }
    if (role) {
      // Tetap di portal yang sedang/terakhir dipakai bila pintunya memang ada di
      // sana — perpindahan portal yang tidak diminta terasa seperti tersesat.
      const current = localStorage.getItem('erp_portal');
      if (current && owners.includes(current) && canAccessPortal(role, current)) return current;
      const allowed = owners.find((p) => canAccessPortal(role, p));
      if (allowed) return allowed;
    }
    return owners[0];
  }
  // 3) Lapis terakhir: tebak dari PREFIX id (lihat MODULE_PREFIX_TO_PORTAL).
  //    Menghilangkan dead-end "Pilih Portal" untuk modul yang hidup di registry
  //    tapi tidak (lagi) tercantum di sidebar.
  return portalFromModulePrefix(moduleId);
}

// Parse moduleId + tab opsional dari URL hash.
//
// SESI #11 — KENAPA `tab` SEKARANG DIBACA DI SINI
// ----------------------------------------------
// Sebelumnya hash hanya membawa **modul**. Untuk modul yang berupa HUB (satu pintu,
// banyak tab), tautan `#marketing-reports` selalu mendarat di tab PERTAMA
// (Overview) — jadi "Laporan Harian" hanya bisa dicapai kalau pemakai tahu harus
// mengklik tab yang mana. Akibat nyata yang terukur: penguji layar sesi lalu
// menyimpulkan **"tabel Laporan Harian tidak ada"** padahal ia ada; dan setiap
// tautan yang dikirim lewat WhatsApp ("cek laporan harian ya") selalu membuka
// layar yang salah. Ini cacat NAVIGASI, bukan cacat layarnya.
//
// Bentuk yang diterima (ketiganya sah, supaya tautan lama tidak mati):
//   `#marketing-reports`        → hub, tab bawaannya
//   `#marketing-reports=daily`  → hub, tab `daily`
//   `#marketing-reports#daily`  → sama (bentuk yang paling gampang ditulis tangan)
//   `#marketing-reports/daily`  → sama
// Tab diteruskan DUA cara supaya semua jenis hub ikut terlayani tanpa disentuh:
//   1. prop `initialTab` (hub yang menerimanya, mis. MarketingReportsHub), dan
//   2. sessionStorage `hub_tab_<moduleId>` — kontrak yang sudah dipakai
//      `makeRedirect()` & `HubTabs.jsx`.
function parseModuleHashParts() {
  if (typeof window === 'undefined') return { moduleId: null, tab: null };
  const raw = window.location.hash || '';
  if (!raw) return { moduleId: null, tab: null };
  const hash = raw.replace(/^#/, '');
  const parts = hash.split(/[=#/]/);
  const moduleId = (parts[0] || '').trim();
  const tab = (parts.slice(1).join('') || '').trim();
  return { moduleId: moduleId || null, tab: tab || null };
}

// SESI #32 — ALAMAT HALAMAN WAJIB MENGIKUTI LAYAR YANG SEDANG DIBUKA.
//
// Temuan penguji independen (iterasi #89) yang membuatnya lahir: sesudah tombol
// "Tetapkan harga jual" di layar **HPP per Potong** memindahkan pemakai ke layar
// **Katalog Marketing**, alamat halaman TETAP `#fin-hpp-produk`. Tiga akibat nyata:
//   1. menekan F5 melempar pemakai kembali ke layar SEBELUMNYA (terasa seperti
//      tombolnya tidak bekerja / navigasi "loncat sendiri");
//   2. tautan yang di-copy-paste (WhatsApp ke pemilik) membuka layar yang SALAH;
//   3. penguji menyimpulkan "navigasi hash rusak" padahal yang rusak hanya
//      alamatnya — dan karena itu 4 pengujian penting tidak pernah dijalankan.
// Aman dipanggil kapan saja: pendengar `hashchange` di bawah IDEMPOTEN (ia hanya
// menyetel portal+modul yang sama), dan `moduleId` selalu diverifikasi ke
// MODULE_REGISTRY oleh pemanggilnya.
function syncModuleHash(moduleId, tab) {
  if (typeof window === 'undefined') return;
  try {
    if (!moduleId) {
      // Kembali ke pemilih portal / keluar: alamat dibersihkan TANPA memicu
      // hashchange (replaceState) supaya tidak ada modul yang dibuka ulang.
      if (window.location.hash) {
        window.history.replaceState(null, '',
          window.location.pathname + window.location.search);
      }
      return;
    }
    const wanted = tab ? `${moduleId}=${tab}` : moduleId;
    if ((window.location.hash || '').replace(/^#/, '') !== wanted) {
      window.location.hash = wanted;
    }
  } catch (e) { /* noop — navigasi tidak boleh gagal hanya karena alamat URL */ }
}

// Titipkan tab yang diminta hash memakai kontrak yang SUDAH ada (`hub_tab_<id>`),
// supaya hub generik (`HubTabs`) maupun hub yang membaca kuncinya sendiri
// (`MarketingReportsHub`, `MarketingAfterSalesHub`, `CatalogManagementModule`)
// sama-sama terlayani tanpa disentuh satu per satu. WAJIB dipanggil SEBELUM
// `setCurrentModule` supaya hub sudah bisa membacanya saat mount pertama.
function stashHashTab(moduleId, tab) {
  if (!moduleId || !tab) return;
  try { sessionStorage.setItem(`hub_tab_${moduleId}`, tab); } catch (e) { /* noop */ }
}

const ModuleSpinner = () => (
  <div className="flex items-center justify-center h-64">
    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[hsl(var(--primary))]" />
  </div>
);

// Deteksi apakah URL saat ini /operator
const isOperatorRoute = () => {
  if (typeof window === 'undefined') return false;
  return window.location.pathname.startsWith('/operator');
};

// Deteksi apakah URL saat ini /tv
const isTVRoute = () => {
  if (typeof window === 'undefined') return false;
  return window.location.pathname.startsWith('/tv');
};

// Deteksi apakah URL saat ini /client (Portal Klien Maklon)
const isClientRoute = () => {
  if (typeof window === 'undefined') return false;
  return window.location.pathname.startsWith('/client');
};

// Deteksi apakah URL saat ini /creator (Portal Creator KOL)
const isCreatorRoute = () => {
  if (typeof window === 'undefined') return false;
  return window.location.pathname.startsWith('/creator');
};

// Deteksi apakah URL saat ini /livehost (Portal LiveHost - Phase 4)
const isLiveHostRoute = () => {
  if (typeof window === 'undefined') return false;
  return window.location.pathname.startsWith('/livehost');
};

// Deteksi apakah URL saat ini /absen (Portal Absen Mandiri)
const isAbsenRoute = () => {
  if (typeof window === 'undefined') return false;
  return window.location.pathname.startsWith('/absen');
};

// Deteksi apakah URL saat ini /vendor-cmt (Portal Vendor CMT)
const isVendorCMTRoute = () => {
  if (typeof window === 'undefined') return false;
  return window.location.pathname.startsWith('/vendor-cmt');
};

// FASE 5: Deteksi /klien-maklon (Tracking read-only klien maklon)
const isKlienMaklonRoute = () => {
  if (typeof window === 'undefined') return false;
  return window.location.pathname.startsWith('/klien-maklon');
};

function ClientPortalApp() {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [bootstrapped, setBootstrapped] = useState(false);

  useEffect(() => {
    const sess = clientApi.loadSession();
    if (sess) {
      setToken(sess.token);
      setUser(sess.user);
    }
    setBootstrapped(true);
  }, []);

  const handleLogin = useCallback((tokenData, userData) => {
    setToken(tokenData);
    setUser(userData);
  }, []);

  const handleLogout = useCallback(() => {
    clientApi.clearSession();
    setToken(null);
    setUser(null);
  }, []);

  if (!bootstrapped) {
    return (
      <div className="flex items-center justify-center h-screen bg-[hsl(var(--background))]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[hsl(var(--primary))]"></div>
      </div>
    );
  }

  if (!token || !user) {
    return (
      <Suspense fallback={<PortalLoader />}>
        <ClientLogin onLogin={handleLogin} />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<PortalLoader />}>
      <ClientPortalShell token={token} user={user} onLogout={handleLogout} />
    </Suspense>
  );
}

function App() {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedPortal, setSelectedPortal] = useState(null);
  const [currentModule, setCurrentModule] = useState('management-dashboard');
  // 2026-08-06 — Kenapa ada: deep-link ke portal yang TIDAK boleh diakses dulu
  // gagal dalam DIAM (pengguna mendarat di "Pilih Portal" tanpa tahu sebabnya,
  // lalu menyangka tautan/notifikasinya rusak). Sekarang alasannya dijelaskan.
  const [deniedNotice, setDeniedNotice] = useState(null);
  // SESI #11 — tab yang diminta URL hash (`#hub-id=tab`). Disimpan BESERTA modul
  // tujuannya: tanpa itu, tab dari tautan lama ikut terbawa ke modul lain yang
  // dibuka lewat sidebar (hub yang tidak memvalidasi kunci tab bisa mendarat di
  // tab yang salah). Lihat `parseModuleHashParts()` untuk alasan fiturnya.
  const [hashTarget, setHashTarget] = useState(() => parseModuleHashParts());
  const [operatorRoute, setOperatorRoute] = useState(isOperatorRoute());
  const [tvRoute, setTVRoute] = useState(isTVRoute());
  const [clientRoute, setClientRoute] = useState(isClientRoute());
  const [creatorRoute, setCreatorRoute] = useState(isCreatorRoute());
  const [liveHostRoute, setLiveHostRoute] = useState(isLiveHostRoute());
  const [absenRoute, setAbsenRoute] = useState(isAbsenRoute());
  const [vendorCMTRoute, setVendorCMTRoute] = useState(isVendorCMTRoute());
  const [klienMaklonRoute, setKlienMaklonRoute] = useState(isKlienMaklonRoute());

  // [PORTAL LIGHT DEFAULT] Maklon portal + external-facing portals default to LIGHT mode.
  // Internal ERP portals keep the user's global theme preference (light/dark/classic/system).
  const { theme, forceTheme } = useTheme();
  useEffect(() => {
    const role = (user?.role || '').toLowerCase();
    const forceLight = (
      vendorCMTRoute || klienMaklonRoute || clientRoute || creatorRoute || liveHostRoute ||
      role === 'cmt_vendor' || role === 'klien_maklon' ||
      selectedPortal === 'maklon'
    );
    forceTheme(forceLight ? 'light' : null);
  }, [vendorCMTRoute, klienMaklonRoute, clientRoute, creatorRoute, liveHostRoute,
      selectedPortal, user, theme, forceTheme]);

  // Sync operatorRoute on popstate / navigation
  useEffect(() => {
    const onPop = () => {
      setOperatorRoute(isOperatorRoute());
      setTVRoute(isTVRoute());
      setClientRoute(isClientRoute());
      setCreatorRoute(isCreatorRoute());
      setLiveHostRoute(isLiveHostRoute());
      setAbsenRoute(isAbsenRoute());
      setVendorCMTRoute(isVendorCMTRoute());
      setKlienMaklonRoute(isKlienMaklonRoute());
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  // Restore session
  useEffect(() => {
    const savedToken = localStorage.getItem('erp_token');
    const savedUser = localStorage.getItem('erp_user');
    const savedPortal = localStorage.getItem('erp_portal');
    if (savedToken && savedUser) {
      try {
        setToken(savedToken);
        const parsed = JSON.parse(savedUser);
        setUser(parsed);
        if (savedPortal && VALID_PORTALS.includes(savedPortal) && canAccessPortal(parsed?.role, savedPortal)) {
          setSelectedPortal(savedPortal);
          setCurrentModule(PORTAL_DEFAULT_MODULE[savedPortal]);
        }
        
        // EEM Phase B — URL query parameter deep-link support (?portal=X&module=Y)
        // Priority: URL params > hash > localStorage
        const params = new URLSearchParams(window.location.search);
        const urlPortal = resolvePortalId(params.get('portal'));
        const urlModule = params.get('module');

        if (urlPortal && urlModule && VALID_PORTALS.includes(urlPortal) && MODULE_REGISTRY[urlModule] && canAccessPortal(parsed?.role, urlPortal)) {
          setSelectedPortal(urlPortal);
          setCurrentModule(urlModule);
          localStorage.setItem('erp_portal', urlPortal);
        } else if (urlPortal && urlModule && VALID_PORTALS.includes(urlPortal) && !canAccessPortal(parsed?.role, urlPortal)) {
          setDeniedNotice({ portalId: urlPortal, moduleId: urlModule });
        } else if (urlModule && MODULE_REGISTRY[urlModule]) {
          // 2026-08-13 — `?portal=` TIDAK DIKENAL tetapi `?module=` sah.
          // Dulu keadaan ini jatuh diam-diam ke portal terakhir yang tersimpan,
          // jadi tautan `?portal=marketing&module=marketing-targets` mendarat di
          // Portal Manajemen tanpa satu pun pesan — pemakai menyimpulkan modulnya
          // hilang. Sekarang portal ditentukan dari MODUL yang diminta (niat yang
          // jelas), dan hanya ditolak kalau perannya memang tidak berhak.
          const ownerPortal = findPortalForModule(urlModule);
          if (ownerPortal && VALID_PORTALS.includes(ownerPortal) && canAccessPortal(parsed?.role, ownerPortal)) {
            setSelectedPortal(ownerPortal);
            setCurrentModule(urlModule);
            localStorage.setItem('erp_portal', ownerPortal);
          } else if (ownerPortal && VALID_PORTALS.includes(ownerPortal)) {
            setDeniedNotice({ portalId: ownerPortal, moduleId: urlModule });
          }
        } else {
          // Session #11.14 — Deep-link via URL hash (#module-id). If a hash is
          // present and resolves to a known module, override the portal+module.
          // SESI #11 — hash boleh membawa tab hub (`#marketing-reports=daily`).
          const { moduleId: hashModuleId, tab: hashTabWanted } = parseModuleHashParts();
          if (hashModuleId && MODULE_REGISTRY[hashModuleId]) {
            const portalForHash = findPortalForModule(hashModuleId);
            if (portalForHash && VALID_PORTALS.includes(portalForHash) && canAccessPortal(parsed?.role, portalForHash)) {
              stashHashTab(hashModuleId, hashTabWanted);
              setSelectedPortal(portalForHash);
              setCurrentModule(hashModuleId);
              localStorage.setItem('erp_portal', portalForHash);
            } else if (portalForHash && VALID_PORTALS.includes(portalForHash)) {
              setDeniedNotice({ portalId: portalForHash, moduleId: hashModuleId });
            }
          }
        }
      } catch (e) {
        localStorage.removeItem('erp_token');
        localStorage.removeItem('erp_user');
        localStorage.removeItem('erp_portal');
      }
    }
    setLoading(false);
  }, []);

  // Session #11.14 — Listen to hashchange events for in-app deep-link navigation
  // (e.g. user pastes a URL with `#prod-shipments` while already logged in).
  useEffect(() => {
    const onHashChange = () => {
      const { moduleId: hashModuleId, tab: hashTabWanted } = parseModuleHashParts();
      if (!hashModuleId || !MODULE_REGISTRY[hashModuleId]) return;
      const portalForHash = findPortalForModule(hashModuleId);
      if (portalForHash && VALID_PORTALS.includes(portalForHash) && canAccessPortal(user?.role, portalForHash)) {
        stashHashTab(hashModuleId, hashTabWanted);
        setHashTarget({ moduleId: hashModuleId, tab: hashTabWanted });
        setSelectedPortal(portalForHash);
        setCurrentModule(hashModuleId);
        localStorage.setItem('erp_portal', portalForHash);
      } else if (portalForHash && VALID_PORTALS.includes(portalForHash)) {
        setDeniedNotice({ portalId: portalForHash, moduleId: hashModuleId });
      }
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, [user]);

  // Configure apiFetch wrapper with 401 auto-logout handler (runs once on mount)
  useEffect(() => {
    configureApi({
      onUnauthorized: () => {
        // Clear session storage and trigger re-render to Login
        localStorage.removeItem('erp_token');
        localStorage.removeItem('erp_user');
        localStorage.removeItem('erp_portal');
        setToken(null);
        setUser(null);
        setSelectedPortal(null);
      },
    });
  }, []);

  const handleLogin = useCallback((tokenData, userData) => {
    setToken(tokenData);
    setUser(userData);
    localStorage.setItem('erp_token', tokenData);
    localStorage.setItem('erp_user', JSON.stringify(userData));
    // 2026-08-05 (RBAC) — simpan akses efektif dari server (portal yang boleh
    // dibuka + pintu menu yang disembunyikan) supaya UI menyaringnya tanpa
    // panggilan tambahan. Kosong = pakai bawaan portalAccess.js.
    saveEffectiveAccess({
      portals: userData.portals || userData._portals || [],
      hidden_modules: userData.hidden_modules || [],
      is_super: !!userData.is_super,
    });
    
    // Role operator → redirect ke Operator View
    if ((userData.role || '').toLowerCase() === 'operator') {
      window.history.pushState({}, '', '/operator');
      setOperatorRoute(true);
      return;
    }

    // Role cmt_vendor → portal vendor ter-scope (bukan Portal Maklon penuh).
    if ((userData.role || '').toLowerCase() === 'cmt_vendor') {
      setSelectedPortal(null);
      return;
    }
    
    // EEM Phase B — Check URL query params after login for direct navigation
    const params = new URLSearchParams(window.location.search);
    const urlPortal = resolvePortalId(params.get('portal'));
    const urlModule = params.get('module');

    if (urlPortal && urlModule && VALID_PORTALS.includes(urlPortal) && MODULE_REGISTRY[urlModule] && canAccessPortal(userData?.role, urlPortal)) {
      // Direct navigation via URL params (role-guarded)
      setSelectedPortal(urlPortal);
      setCurrentModule(urlModule);
      localStorage.setItem('erp_portal', urlPortal);
      return;
    }
    // `?portal=` tak dikenal tapi `?module=` sah ⇒ portal ditentukan dari modulnya
    // (lihat catatan PORTAL_ID_ALIASES). Jangan pernah mendarat di portal lain
    // tanpa penjelasan: itu terbaca sebagai "modulnya hilang".
    if (urlModule && MODULE_REGISTRY[urlModule]) {
      const ownerPortal = findPortalForModule(urlModule);
      if (ownerPortal && VALID_PORTALS.includes(ownerPortal) && canAccessPortal(userData?.role, ownerPortal)) {
        setSelectedPortal(ownerPortal);
        setCurrentModule(urlModule);
        localStorage.setItem('erp_portal', ownerPortal);
        return;
      }
    }

    // FASE 6 fix — deep-link `#module-id` HARUS tetap dihormati setelah login.
    // Sebelumnya hanya jalur restore-session (token sudah ada di localStorage) yang
    // membaca hash, sedangkan jalur login BARU langsung jatuh ke "Pilih Portal".
    // Akibatnya semua bookmark/notifikasi berbentuk `https://app/#<module>` kehilangan
    // tujuannya begitu user harus login dulu (mis. `#wh-quarantine`).
    const { moduleId: hashModuleId, tab: hashTabWanted } = parseModuleHashParts();
    if (hashModuleId && MODULE_REGISTRY[hashModuleId]) {
      const portalForHash = findPortalForModule(hashModuleId);
      if (portalForHash && VALID_PORTALS.includes(portalForHash) && canAccessPortal(userData?.role, portalForHash)) {
        stashHashTab(hashModuleId, hashTabWanted);
        setSelectedPortal(portalForHash);
        setCurrentModule(hashModuleId);
        localStorage.setItem('erp_portal', portalForHash);
        return;
      }
    }

    // Default: back to portal selector
    setSelectedPortal(null);
    setCurrentModule('management-dashboard');
  }, []);

  const handleLogout = useCallback(() => {
    setToken(null);
    setUser(null);
    setSelectedPortal(null);
    setCurrentModule('management-dashboard');
    localStorage.removeItem('erp_token');
    localStorage.removeItem('erp_user');
    localStorage.removeItem('erp_portal');
    syncModuleHash(null);
    if (isOperatorRoute()) {
      window.history.pushState({}, '', '/');
      setOperatorRoute(false);
    }
  }, []);

  const handleSelectPortal = useCallback((portalId) => {
    if (!VALID_PORTALS.includes(portalId)) return;
    if (!canAccessPortal(user?.role, portalId)) return;
    setSelectedPortal(portalId);
    setCurrentModule(PORTAL_DEFAULT_MODULE[portalId]);
    syncModuleHash(PORTAL_DEFAULT_MODULE[portalId]);
    localStorage.setItem('erp_portal', portalId);
  }, [user]);

  // Hybrid-nav support: switch portal dari pill-nav tanpa balik ke selector
  const handlePortalChange = useCallback((portalId) => {
    if (!VALID_PORTALS.includes(portalId)) return;
    if (!canAccessPortal(user?.role, portalId)) return;
    setSelectedPortal(portalId);
    setCurrentModule(PORTAL_DEFAULT_MODULE[portalId]);
    syncModuleHash(PORTAL_DEFAULT_MODULE[portalId]);
    localStorage.setItem('erp_portal', portalId);
  }, [user]);

  const handleBackToPortals = useCallback(() => {
    setSelectedPortal(null);
    setCurrentModule('management-dashboard');
    syncModuleHash(null);
    localStorage.removeItem('erp_portal');
  }, []);

  const [navParams, setNavParams] = useState({});

  // RC-FLOW-UX-CORE — single onward-navigation entrypoint passed to EVERY module
  // (and forwarded through hubs → HubTabs). Enables "CTA onward" buttons across flows.
  // Capabilities:
  //   • cross-portal switch: if the target module lives in a different (accessible)
  //     portal, switch selectedPortal so sidebar/context match (Marketing→Gudang, SDM→Keuangan…).
  //   • hub-tab deep target: pass { tab: '<key>' } to open a specific tab of a hub
  //     (mirrors makeRedirect's sessionStorage `hub_tab_<hubId>` contract).
  //   • deep-link params forwarded to the target module via `deepLinkParams` prop.
  const handleNavigate = useCallback((moduleId, params = {}) => {
    if (!moduleId || !MODULE_REGISTRY[moduleId]) return;
    const safeParams = params || {};
    // hub-tab deep target (open a specific tab of a generic hub)
    if (safeParams.tab) {
      try { sessionStorage.setItem(`hub_tab_${moduleId}`, safeParams.tab); } catch (e) { /* noop */ }
    }
    // cross-portal onward navigation — switch portal when target is elsewhere & accessible
    const targetPortal = findPortalForModule(moduleId);
    if (
      targetPortal &&
      VALID_PORTALS.includes(targetPortal) &&
      canAccessPortal(user?.role, targetPortal) &&
      targetPortal !== selectedPortal
    ) {
      setSelectedPortal(targetPortal);
      localStorage.setItem('erp_portal', targetPortal);
    }
    setCurrentModule(moduleId);
    setNavParams(safeParams);
    // SESI #32 — alamat halaman ikut berpindah (lihat `syncModuleHash`).
    syncModuleHash(moduleId, safeParams.tab);
    // fresh page context — scroll to top
    try { window.scrollTo({ top: 0, behavior: 'smooth' }); } catch (e) { /* noop */ }
  }, [user, selectedPortal]);

  // SESI #32 — satu pintu perpindahan modul dari SIDEBAR/shell: sebelumnya
  // `onModuleChange={setCurrentModule}` mengubah layar tanpa mengubah alamat,
  // jadi F5 selalu mengembalikan pemakai ke modul yang dibuka paling awal.
  const handleModuleChange = useCallback((moduleId) => {
    if (!moduleId || !MODULE_REGISTRY[moduleId]) return;
    setCurrentModule(moduleId);
    syncModuleHash(moduleId);
  }, []);

  // ── Memoize headers to prevent infinite re-render in child components ──
  // MUST be before any conditional returns (Rules of Hooks)
  const headers = useMemo(() => (token ? { Authorization: `Bearer ${token}` } : {}), [token]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-[hsl(var(--background))]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[hsl(var(--primary))]"></div>
      </div>
    );
  }

  // FASE 5: TV Mode (ShopFloorTV, engine lama) diarsip — redirect ke root.
  if (tvRoute) {
    if (typeof window !== 'undefined') window.location.replace('/');
    return null;
  }

  // Absen Mandiri Portal — dedicated attendance page
  if (absenRoute) {
    return (
      <Suspense fallback={<PortalLoader />}>
        <AbsenPage />
      </Suspense>
    );
  }

  // Vendor CMT Portal — separate app for CMT vendors
  if (vendorCMTRoute) {
    return (
      <Suspense fallback={<PortalLoader />}>
        <VendorCMTPortalApp />
      </Suspense>
    );
  }

  // FASE 5: Tracking read-only klien maklon
  if (klienMaklonRoute) {
    return (
      <Suspense fallback={<PortalLoader />}>
        <ClientMaklonPortal />
      </Suspense>
    );
  }

  // Client Portal (Phase 4) — separate app, separate auth, separate token storage
  if (clientRoute) {
    return <ClientPortalApp />;
  }

  // Creator Portal (Phase 5) — separate app for KOL creators
  if (creatorRoute) {
    return (
      <Suspense fallback={<PortalLoader />}>
        <CreatorPortalApp />
      </Suspense>
    );
  }

  // LiveHost Portal (Phase 4 / Session 28) — separate app for live streaming hosts
  if (liveHostRoute) {
    return (
      <Suspense fallback={<PortalLoader />}>
        <LiveHostPortalApp />
      </Suspense>
    );
  }

  if (!token || !user) return <Login onLogin={handleLogin} />;

  // Vendor CMT role → portal vendor ter-scope (hanya job/shipment miliknya).
  // Mencegah kebocoran data: vendor TIDAK boleh melihat seluruh Portal Maklon.
  if ((user.role || '').toLowerCase() === 'cmt_vendor') {
    return (
      <Suspense fallback={<PortalLoader />}>
        <VendorCMTPortalApp />
      </Suspense>
    );
  }

  // Operator View (mobile) on /operator URL OR if user role is operator
  // FASE 5: OperatorView (engine multi-stage lama) diarsip — portal operator dinonaktifkan.
  if (operatorRoute || (user.role || '').toLowerCase() === 'operator') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))] px-4">
        <div className="max-w-md text-center space-y-4">
          <h1 className="text-xl font-bold text-[hsl(var(--foreground))]">Portal Operator sudah dinonaktifkan</h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            Input produksi kini dicatat oleh admin/supervisor melalui menu
            &quot;Input Progress&quot; di Portal Produksi (dengan pilihan operator borongan).
          </p>
          <button data-testid="operator-gone-logout" onClick={handleLogout}
            className="px-4 py-2 rounded-lg bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] text-sm font-semibold">
            Kembali ke Login
          </button>
        </div>
      </div>
    );
  }

  if (!selectedPortal) {
    return (
      <PortalSelector
        user={user}
        onSelectPortal={handleSelectPortal}
        onLogout={handleLogout}
        deniedNotice={deniedNotice}
        onDismissDenied={() => setDeniedNotice(null)}
      />
    );
  }

  const userPerms = user?.permissions || [];
  const hasPerm = (key) => {
    const role = (user?.role || '').toLowerCase();
    if (['superadmin', 'admin', 'owner'].includes(role)) return true;
    return userPerms.includes(key) || userPerms.includes(key.split('.')[0] + '.*') || userPerms.includes('*');
  };

  const ModuleComponent = MODULE_REGISTRY[currentModule] || DEFAULT_MODULE;

  // Special handling for Portal Kolaborasi - render full screen without PortalShell wrapper
  if (selectedPortal === 'collaboration') {
    return (
      <>
        <Suspense fallback={<ModuleSpinner />}>
          <ModuleComponent
            token={token}
            user={user}
            headers={headers}
            userRole={user?.role}
            hasPerm={hasPerm}
            onNavigate={handleNavigate}
            onLogout={handleLogout}
            onBack={handleBackToPortals}
            moduleId={currentModule}
            deepLinkParams={navParams}
            initialTab={navParams?.tab || (hashTarget?.moduleId === currentModule ? hashTarget?.tab : null) || undefined}
          />
        </Suspense>
        {/* Global AI Chatbot Widget */}
        <Suspense fallback={null}>
          <AIChatbotWidget headers={headers} user={user} portal={selectedPortal} moduleId={currentModule} />
        </Suspense>
      </>
    );
  }

  // Standard portal rendering with PortalShell
  return (
    <>
      <PortalShell
        portal={selectedPortal}
        user={user}
        token={token}
        onBack={handleBackToPortals}
        onLogout={handleLogout}
        onPortalChange={handlePortalChange}
        currentModule={currentModule}
        onModuleChange={handleModuleChange}
      >
        <Suspense fallback={<ModuleSpinner />}>
          <ModuleComponent
            token={token}
            user={user}
            headers={headers}
            userRole={user?.role}
            hasPerm={hasPerm}
            onNavigate={handleNavigate}
            moduleId={currentModule}
            portalId={selectedPortal}
            deepLinkParams={navParams}
            initialTab={navParams?.tab || (hashTarget?.moduleId === currentModule ? hashTarget?.tab : null) || undefined}
            onModuleChange={handleModuleChange}
          />
        </Suspense>
      </PortalShell>
      {/* Global AI Chatbot Widget — available on all portals */}
      <Suspense fallback={null}>
        <AIChatbotWidget headers={headers} user={user} portal={selectedPortal} moduleId={currentModule} />
      </Suspense>
    </>
  );
}

export default function AppWithTheme() {
  return (
    <ErrorBoundary level="root">
      <ThemeProvider defaultTheme="light">
        <TooltipProvider delayDuration={250}>
          {/* Ambient decorative layers — pointer-events none, behind everything */}
          <div className="starfield" aria-hidden="true" />
          <div className="noise-overlay fixed inset-0 pointer-events-none" aria-hidden="true" />
          <App />
          <Toaster position="top-right" richColors closeButton />
          <ShadcnToaster />
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
