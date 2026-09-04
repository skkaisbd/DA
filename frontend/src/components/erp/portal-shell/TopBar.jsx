/**
 * TopBar — sticky header bar of the PortalShell.
 *
 * Contains:
 *   - Mobile menu toggle
 *   - Brand button (click → back to portal selector)
 *   - Section pill nav (THE MENU)
 *   - Global search
 *   - Command palette shortcut button (⌘K hint)
 *   - Notification bell
 *   - Account dropdown
 */

import {
  Menu, ChevronLeft, Command as CommandIcon,
} from 'lucide-react';
import { NotificationBell } from '../NotificationBell';
import { ApprovalBadge } from '../ApprovalBadge';
import GlobalSearch from './GlobalSearch';
import AccountMenu from './AccountMenu';
import { PORTAL_LABEL, formatSectionLabel } from './portalNav';

export default function TopBar({
  portal,
  nav,
  activeSectionIndex,
  user,
  token,
  onBack,
  onLogout,
  onModuleChange,
  onSectionPillClick,
  onOpenMobile,
  onOpenCmdk,
  onOpenHelp,
  onOpenGuide,
  singleDoor = false,
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--glass-border)] bg-[var(--card-surface)] backdrop-blur-[var(--glass-blur-strong)]">
      <div className="flex items-center gap-3 px-3 sm:px-5 py-2.5">
        {/* Mobile menu toggle — disembunyikan pada portal satu pintu (tidak ada sidebar) */}
        <button
          className={`${singleDoor ? 'hidden' : 'md:hidden'} p-1.5 rounded-lg text-foreground/60 hover:text-foreground hover:bg-[var(--nav-pill-active)] transition-colors duration-150`}
          onClick={onOpenMobile}
          data-testid="mobile-menu-btn"
          aria-label="Buka menu"
        >
          <Menu className="w-5 h-5" />
        </button>

        {/* Brand + Portal badge (click brand → back to portal selector) */}
        <button
          onClick={onBack}
          className="flex items-center gap-2.5 shrink-0 group transition-opacity duration-150 hover:opacity-80"
          data-testid="portal-back-btn"
          aria-label="Kembali ke pilih portal"
          title="Klik untuk ganti portal"
        >
          <div className="w-9 h-9 rounded-[12px] bg-gradient-to-br from-[hsl(var(--primary)/0.20)] to-[hsl(var(--accent)/0.20)] border border-[hsl(var(--primary)/0.30)] grid place-items-center text-[hsl(var(--primary))] group-hover:scale-105 transition-transform duration-150 shadow-[var(--shadow-glow-blue)]">
            {/* CV. Dewi Aditya — fashion brand mark (SVG inline) */}
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M20.38 3.46 16 2 12 5.5 8 2 3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z" />
            </svg>
          </div>
          <div className="hidden md:flex flex-col leading-tight text-left">
            <span className="text-[10px] uppercase tracking-wider text-foreground/40 font-semibold">
              Portal
            </span>
            <span className="text-sm font-semibold text-foreground -mt-0.5">
              {PORTAL_LABEL[portal] || portal}
            </span>
          </div>
          <ChevronLeft className="hidden md:block w-3.5 h-3.5 text-foreground/30 ml-0.5 group-hover:text-foreground/60 transition-colors duration-150" />
        </button>

        {/* Section pill nav — THE MENU (sections of current portal).
            IA v4: portal satu pintu tidak menampilkan pill (hanya 1 section, 1 pintu). */}
        {!singleDoor && (
        <nav
          className="hidden md:inline-flex items-center gap-1 rounded-full border border-[var(--glass-border)] bg-[var(--nav-pill-bg)] backdrop-blur-xl p-1 overflow-x-auto max-w-[55vw]"
          data-testid="section-pill-nav"
          aria-label="Menu portal"
        >
          {nav.sections.map((s, idx) => {
            const active = idx === activeSectionIndex;
            return (
              <button
                key={s.label}
                onClick={() => onSectionPillClick(s.label)}
                className={`relative inline-flex items-center gap-2 rounded-full px-3 lg:px-4 py-1.5 text-xs lg:text-sm font-medium whitespace-nowrap
                  transition-[background-color,color,box-shadow] duration-200 ease-smooth-out
                  ${
                    active
                      ? 'bg-[var(--nav-pill-active)] text-foreground shadow-[var(--shadow-glow-blue)]'
                      : 'text-foreground/60 hover:text-foreground hover:bg-[var(--nav-pill-active)]/60'
                  }`}
                data-testid={`section-pill-${idx}`}
                aria-pressed={active}
                aria-label={`Menu ${s.label}`}
              >
                <span className={active ? 'text-[hsl(var(--primary))]' : ''}>
                  {formatSectionLabel(s.label)}
                </span>
              </button>
            );
          })}
        </nav>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Global Search */}
        <GlobalSearch token={token} onResultSelect={onModuleChange} />

        {/* ── Right side: Notif + Account dropdown ── */}
        <div className="flex items-center gap-1.5 shrink-0">
          {/* Command Palette shortcut (keyboard only hint, small) */}
          <button
            onClick={onOpenCmdk}
            className="hidden lg:inline-flex items-center gap-1.5 h-8 px-2.5 rounded-full border border-[var(--glass-border)] bg-[var(--nav-pill-bg)] text-foreground/50 hover:text-foreground hover:bg-[var(--nav-pill-active)] transition-colors duration-150"
            data-testid="topbar-cmdk-trigger"
            title="Command Palette (Ctrl/Cmd + K)"
            aria-label="Buka Command Palette"
          >
            <CommandIcon className="w-3 h-3" />
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-60">⌘K</span>
          </button>

          {/* Notification Bell */}
          <NotificationBell
            token={token}
            onNavigateModule={(moduleId) => {
              if (moduleId) onModuleChange(moduleId);
            }}
          />

          {/* Approval Inbox Badge */}
          <ApprovalBadge
            token={token}
            onNavigateModule={(moduleId) => {
              if (moduleId) onModuleChange(moduleId);
            }}
          />

          {/* Account Dropdown */}
          <AccountMenu
            user={user}
            onOpenCmdk={onOpenCmdk}
            onOpenHelp={onOpenHelp}
            onOpenGuide={onOpenGuide}
            onLogout={onLogout}
          />
        </div>
      </div>
    </header>
  );
}
