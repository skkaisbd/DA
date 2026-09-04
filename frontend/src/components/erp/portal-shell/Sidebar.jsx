/**
 * Sidebar — left navigation panel showing items of active section.
 *
 * Owns:
 *   - collapse toggle (button at top of sidebar)
 *   - mobile drawer dismiss button
 *   - mobile section dropdown
 *   - section flat-items OR grouped items rendering
 *   - sidebar footer (RecentModulesFooter + breadcrumb + TV link)
 */

import { Menu, X, Tv2 } from 'lucide-react';
import NavItem from './NavItem';
import { hiddenModules, navItemAllowed, currentRole } from '../portalAccess';
import RecentModulesFooter from './RecentModulesFooter';
import { formatSectionLabel, findModuleLabel } from './portalNav';

export default function Sidebar({
  portal,
  nav,
  activeSection,
  currentModule,
  collapsed,
  setCollapsed,
  mobileOpen,
  setMobileOpen,
  onModuleChange,
  onSectionChange,
}) {
  // 2026-08-05 (RBAC visibilitas menu) — pintu yang disembunyikan owner untuk
  // role/user ini tidak dirender. Kosong = tampilkan semua (perilaku lama).
  const _hidden = hiddenModules();
  // 2026-08-08 — sebagian pintu lebih sempit kewenangannya daripada portalnya
  // (mis. "Input Vendor CMT" berdampak ke tagihan). Pintu yang tidak berwenang
  // TIDAK dirender supaya tidak jadi menu buntu "tidak berwenang".
  const _role = currentRole();
  const visible = (list) => (list || []).filter(
    (it) => !_hidden.includes(it.id) && navItemAllowed(it, _role));

  return (
    <>
      <aside
        className={`${collapsed ? 'md:w-[72px]' : 'md:w-[240px]'}
          fixed md:static inset-y-0 left-0 z-30 w-[260px]
          transition-[width,transform] duration-300 ease-smooth-out
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}
        data-testid="portal-sidebar"
      >
        <div className="h-full flex flex-col bg-[var(--card-surface)] backdrop-blur-[var(--glass-blur-strong)] border-r border-[var(--glass-border)]">
          {/* Sidebar header: active section name + collapse toggle */}
          <div className="px-3 py-3 flex items-center justify-between border-b border-[var(--glass-border)]">
            {!collapsed && (
              <div className="flex items-center gap-2 min-w-0 px-1">
                <div className="w-1 h-4 rounded-full bg-[hsl(var(--primary))] shrink-0" />
                <span
                  className="text-[11px] font-semibold tracking-wider text-foreground/70 uppercase truncate"
                  data-testid="sidebar-active-section"
                >
                  {formatSectionLabel(activeSection?.label || '')}
                </span>
              </div>
            )}
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="hidden md:grid place-items-center h-7 w-7 rounded-lg text-foreground/50 hover:text-foreground hover:bg-[var(--nav-pill-active)] transition-colors duration-150"
              data-testid="sidebar-toggle-btn"
              aria-label={collapsed ? 'Perluas menu' : 'Ciutkan menu'}
            >
              <Menu className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setMobileOpen(false)}
              className="md:hidden grid place-items-center h-7 w-7 rounded-lg text-foreground/50 hover:text-foreground hover:bg-[var(--nav-pill-active)]"
              aria-label="Tutup menu"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Mobile: show section dropdown at top of sidebar */}
          {mobileOpen && (
            <div className="md:hidden p-2 border-b border-[var(--glass-border)]">
              <select
                value={activeSection?.label || ''}
                onChange={(e) => onSectionChange(e.target.value)}
                className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs text-foreground"
                data-testid="mobile-section-select"
              >
                {nav.sections.map((s) => (
                  <option key={s.label} value={s.label}>
                    {formatSectionLabel(s.label)}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Items (flat list OR grouped) of active section */}
          <nav className="flex-1 overflow-y-auto py-2 px-2" data-testid="sidebar-items">
            {activeSection?.groups?.length ? (
              <div className="space-y-3">
                {activeSection.groups.map((g) => (
                  <div key={g.label}>
                    {!collapsed && (
                      <div
                        className="px-3 pt-2 pb-1.5 flex items-center gap-1.5"
                        data-testid={`sidebar-group-header-${g.label}`}
                      >
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-foreground/40">
                          {g.label}
                        </span>
                        <div className="flex-1 h-px bg-[var(--glass-border)]" aria-hidden="true" />
                      </div>
                    )}
                    {collapsed && (
                      <div className="mx-2 my-1 h-px bg-[var(--glass-border)]" aria-hidden="true" />
                    )}
                    <div className="space-y-0.5">
                      {visible(g.items).map((item) => (
                        <NavItem
                          key={item.id}
                          item={item}
                          isActive={currentModule === item.id}
                          collapsed={collapsed}
                          onModuleChange={onModuleChange}
                          setMobileOpen={setMobileOpen}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-0.5">
                {visible(activeSection?.items).map((item) => (
                  <NavItem
                    key={item.id}
                    item={item}
                    isActive={currentModule === item.id}
                    collapsed={collapsed}
                    onModuleChange={onModuleChange}
                    setMobileOpen={setMobileOpen}
                  />
                ))}
                {visible(activeSection?.items).length === 0 && (
                  <div className="px-3 py-6 text-center text-xs text-foreground/40">
                    Belum ada item di menu ini.
                  </div>
                )}
              </div>
            )}
          </nav>

          {/* Sidebar footer: Recent modules + TV link + breadcrumb */}
          {!collapsed && (
            <div className="px-3 py-2 border-t border-[var(--glass-border)] space-y-1">
              <RecentModulesFooter
                portal={portal}
                currentModule={currentModule}
                onModuleChange={onModuleChange}
              />
              <p
                className="text-[10px] text-foreground/40 truncate"
                data-testid="topbar-module-title"
              >
                {findModuleLabel(portal, currentModule)}
              </p>
              {/* Phase 1.5: TV link moved from sidebar section to footer */}
              <a
                href="/tv"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-[10px] text-foreground/40 hover:text-foreground/70 transition-colors duration-150 group"
                data-testid="sidebar-tv-link"
              >
                <Tv2 className="w-3 h-3 group-hover:text-[hsl(var(--primary))]" />
                <span>Mode TV Lantai Produksi</span>
              </a>
            </div>
          )}
        </div>
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-[var(--overlay-bg)] z-20 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}
    </>
  );
}
