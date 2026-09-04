/**
 * PortalShell — Thin Orchestrator Shell (Session #11 Refactor #6)
 *
 * Refactored from monolithic 1418-LOC file (Session #11) into thin shell + 7 sub-modules
 * under `./portal-shell/*`:
 *   - portalNav.js (PORTAL_NAV + PORTAL_LABEL + helpers + findModuleLabel)
 *   - NavItem.jsx (single sidebar item renderer)
 *   - RecentModulesFooter.jsx (recent modules under sidebar)
 *   - Sidebar.jsx (left sidebar with collapse/mobile drawer)
 *   - GlobalSearch.jsx (topbar search + debounced dropdown)
 *   - AccountMenu.jsx (account dropdown panel)
 *   - TopBar.jsx (header bar wrapper)
 *
 * External API (PRESERVED):
 *   - Default export `PortalShell` UNCHANGED
 *   - Re-export `findModuleLabel` from `./portal-shell/portalNav` for backward compatibility
 *   - Props: { portal, user, token, onBack, onLogout, onPortalChange, children, currentModule, onModuleChange }
 *
 * This shell only owns:
 *   - Top-level UI state (collapsed, mobileOpen, cmdkOpen, helpOpen, tourSteps, guideOpen)
 *   - Active section computation
 *   - Module suggestions memo for CommandPalette
 *   - Production-portal special wrapper (ProductionUIProvider + ProductionInputFAB + Wizard + QuickInput)
 */

import { useState, useMemo, Suspense, lazy } from 'react';
import { CommandPalette } from './CommandPalette';
// Session #11.18 EXTENDED — Lazy-load help/guide UIs since they only render when opened
const ModuleHelpDrawer = lazy(() => import('./userGuide/ModuleHelpDrawer'));
const ModuleTour = lazy(() => import('./userGuide/ModuleTour'));
const UserGuideDialog = lazy(() => import('./userGuide/UserGuideDialog'));
// Lazy-load production-specific UIs (only load on Production portal)
// FASE 5: ProductionWizardModule & QuickInputPanel diarsip (engine multi-stage lama dihapus)
// Universal Scan Portal — loaded lazily (only used when user opens it)
const UniversalScanPortal = lazy(() => import('./scanner/UniversalScanPortal'));
import { ProductionUIProvider } from '@/contexts/ProductionUIContext';
// FASE 5: ProductionInputFAB diarsip (quick-input engine lama)
import ErrorBoundary from '../ErrorBoundary';
import MobileBottomNav from './MobileBottomNav';
import {
  PORTAL_NAV, PORTAL_LABEL,
  sectionContainsModule,
  findModuleLabel as findModuleLabelImpl,
} from './portal-shell/portalNav';
import TopBar from './portal-shell/TopBar';
import Sidebar from './portal-shell/Sidebar';

// Re-export for backward compatibility (some legacy code imports findModuleLabel from PortalShell)
export function findModuleLabel(portal, moduleId) {
  return findModuleLabelImpl(portal, moduleId);
}

export default function PortalShell({
  portal,
  user,
  token,
  onBack,
  onLogout,
  onPortalChange,
  children,
  currentModule,
  onModuleChange,
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [cmdkOpen, setCmdkOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [tourSteps, setTourSteps] = useState(null); // null = not active
  const [guideOpen, setGuideOpen] = useState(false);

  const nav = PORTAL_NAV[portal] || PORTAL_NAV.management;
  // IA v4 — Portal "satu pintu" (mis. Manajemen Aset): sidebar & pill section
  // DISEMBUNYIKAN karena navigasi sudah 100% ditangani tab di dalam modul.
  // Dua lapis navigasi untuk satu halaman = beban kognitif tanpa manfaat.
  const singleDoor = !!nav.singleDoor;

  // ── Global module suggestions (semua portal) untuk Command Palette ──
  const moduleSuggestions = useMemo(() => {
    const out = [];
    Object.entries(PORTAL_NAV).forEach(([pid, p]) => {
      p.sections.forEach((sec) => {
        const pushItem = (item, groupLabel = null) => {
          out.push({
            // Compound id ensures uniqueness across portals (same item.id may
            // legitimately appear in multiple portal navs — e.g. ai-actions in
            // both production & HR, rnd-dashboard in both management & rnd).
            id: `${pid}::${item.id}`,
            moduleId: item.id,
            label: item.label,
            portal: PORTAL_LABEL[pid] || pid,
            portalId: pid,
            section: groupLabel ? `${sec.label} · ${groupLabel}` : sec.label,
            icon: item.icon,
          });
        };
        sec.items?.forEach((it) => pushItem(it));
        sec.groups?.forEach((g) => g.items?.forEach((it) => pushItem(it, g.label)));
      });
    });
    return out;
  }, []);

  // ── Section-based nav: top pills = sections, left sidebar = items of active section ──
  const activeSectionIndex = Math.max(
    0,
    nav.sections.findIndex((s) => sectionContainsModule(s, currentModule))
  );
  const activeSection = nav.sections[activeSectionIndex] || nav.sections[0];

  const handleSectionPillClick = (sectionLabel) => {
    const target = nav.sections.find((s) => s.label === sectionLabel);
    if (!target) return;
    // Skip isHeader items — find the first real navigable module
    const allItems = target.items || target.groups?.[0]?.items || [];
    const firstItem = allItems.find((i) => !i.isHeader) || allItems[0];
    if (!firstItem || firstItem.isHeader) return;
    onModuleChange(firstItem.id);
    setMobileOpen(false);
  };

  // Wrap content with ProductionUIProvider if in production portal
  const contentWrapper =
    portal === 'production' ? (
      <ProductionUIProvider>
        <ErrorBoundary level="portal">{children}</ErrorBoundary>
        {/* FASE 5: FAB + wizard + quick-input panel engine lama diarsip */}
      </ProductionUIProvider>
    ) : (
      <ErrorBoundary level="portal">{children}</ErrorBoundary>
    );

  return (
    <div className="flex flex-col h-screen" data-testid={`portal-shell-${portal}`}>
      {/* TOP BAR */}
      <TopBar
        portal={portal}
        nav={nav}
        activeSectionIndex={activeSectionIndex}
        user={user}
        token={token}
        onBack={onBack}
        onLogout={onLogout}
        onModuleChange={onModuleChange}
        onSectionPillClick={handleSectionPillClick}
        onOpenMobile={() => setMobileOpen(true)}
        onOpenCmdk={() => setCmdkOpen(true)}
        onOpenHelp={() => setHelpOpen(true)}
        onOpenGuide={() => setGuideOpen(true)}
        singleDoor={singleDoor}
      />

      {/* BODY — Side Nav + Main Content */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {!singleDoor && (
          <Sidebar
            portal={portal}
            nav={nav}
            activeSection={activeSection}
            currentModule={currentModule}
            collapsed={collapsed}
            setCollapsed={setCollapsed}
            mobileOpen={mobileOpen}
            setMobileOpen={setMobileOpen}
            onModuleChange={onModuleChange}
            onSectionChange={handleSectionPillClick}
          />
        )}

        {/* Main content — add pb for mobile bottom nav on 'self' portal */}
        <main className={`flex-1 overflow-y-auto${portal === 'self' ? ' pb-14 md:pb-0' : ''}`}>
          <div className="max-w-[1400px] mx-auto p-4 sm:p-6">{contentWrapper}</div>
        </main>
      </div>

      {/* Mobile Bottom Nav — Portal Saya only */}
      <MobileBottomNav portal={portal} currentModule={currentModule} onModuleChange={onModuleChange} />

      {/* Command Palette (Cmd+K) */}
      <CommandPalette
        open={cmdkOpen}
        onOpenChange={setCmdkOpen}
        currentPortal={portal}
        onSelectPortal={(pid) => {
          onPortalChange?.(pid);
        }}
        onSelectModule={(mid) => {
          onModuleChange?.(mid);
        }}
        onLogout={onLogout}
        moduleSuggestions={moduleSuggestions}
        token={token}
      />

      {/* Module Help Drawer (?) — lazy */}
      <Suspense fallback={null}>
        <ModuleHelpDrawer
          open={helpOpen}
          onOpenChange={setHelpOpen}
          moduleId={currentModule}
          onStartTour={(steps) => setTourSteps(steps)}
        />
      </Suspense>

      {/* Module Tour (interactive overlay) — lazy */}
      {tourSteps && (
        <Suspense fallback={null}>
          <ModuleTour steps={tourSteps} onClose={() => setTourSteps(null)} />
        </Suspense>
      )}

      {/* Full User Guide Dialog (📖) — lazy */}
      <Suspense fallback={null}>
        <UserGuideDialog open={guideOpen} onOpenChange={setGuideOpen} />
      </Suspense>

      {/* Universal Scan Portal — floating FAB + modal (Ctrl+Shift+S) */}
      <Suspense fallback={null}>
        <UniversalScanPortal token={token} onNavigate={onModuleChange} />
      </Suspense>
    </div>
  );
}
