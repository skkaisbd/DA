/**
 * AccountMenu — account dropdown in topbar.
 *
 * Triggered by clicking the user avatar/name pill. Provides:
 *   - User info header
 *   - Command Palette shortcut
 *   - Help Drawer
 *   - Full User Guide Dialog
 *   - Theme toggle row
 *   - Logout button
 */

import { useState, useRef, useEffect } from 'react';
import {
  ChevronDown, Sun, LogOut, BookOpen, HelpCircle, Command as CommandIcon,
} from 'lucide-react';
import { ThemeToggle } from '@/components/theme/ThemeToggle';

// Helper component for menu items
function AccountMenuItem({ icon: Icon, label, hint, onClick, testId }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-foreground/80 hover:text-foreground hover:bg-[var(--glass-bg-hover)] transition-colors duration-150"
      data-testid={testId}
    >
      <Icon className="w-4 h-4 shrink-0 text-foreground/50" />
      <span className="flex-1 text-left">{label}</span>
      {hint && <span className="text-[10px] text-foreground/30 font-mono">{hint}</span>}
    </button>
  );
}

export default function AccountMenu({ user, onOpenCmdk, onOpenHelp, onOpenGuide, onLogout }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);

  // Close on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 pl-1.5 pr-2.5 py-1 rounded-full border border-[var(--glass-border)] bg-[var(--nav-pill-bg)] hover:bg-[var(--nav-pill-active)] transition-colors duration-150 group"
        data-testid="topbar-account-btn"
        aria-label="Menu akun"
        aria-expanded={open}
      >
        {/* Avatar */}
        <div className="w-7 h-7 rounded-full bg-[hsl(var(--primary)/0.15)] border border-[hsl(var(--primary)/0.25)] grid place-items-center text-[hsl(var(--primary))] text-xs font-bold shrink-0">
          {user?.name?.[0]?.toUpperCase() || '?'}
        </div>
        {/* Name + role (hidden on sm) */}
        <div className="hidden md:flex flex-col leading-tight text-left">
          <span className="text-xs font-medium text-foreground truncate max-w-[120px]">
            {user?.name || 'Pengguna'}
          </span>
          <span className="text-[10px] text-foreground/50 capitalize">{user?.role || ''}</span>
        </div>
        <ChevronDown
          className={`w-3.5 h-3.5 text-foreground/40 transition-transform duration-200 ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>

      {/* Dropdown panel */}
      {open && (
        <div
          className="absolute right-0 top-full mt-2 w-60 rounded-[var(--radius-lg)] border border-[var(--glass-border)] bg-[var(--popover-surface)] backdrop-blur-[var(--glass-blur-strong)] shadow-[var(--shadow-soft)] z-50 overflow-hidden"
          data-testid="account-dropdown-menu"
        >
          {/* User info header */}
          <div className="px-4 py-3 border-b border-[var(--glass-border)]">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-[hsl(var(--primary)/0.15)] border border-[hsl(var(--primary)/0.25)] grid place-items-center text-[hsl(var(--primary))] text-sm font-bold shrink-0">
                {user?.name?.[0]?.toUpperCase() || '?'}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground truncate">
                  {user?.name || 'Pengguna'}
                </p>
                <p className="text-xs text-foreground/50 capitalize">{user?.role || ''}</p>
              </div>
            </div>
          </div>

          {/* Menu items */}
          <div className="py-1.5">
            <AccountMenuItem
              icon={CommandIcon}
              label="Command Palette"
              hint="⌘K"
              onClick={() => {
                setOpen(false);
                onOpenCmdk();
              }}
              testId="account-cmdk"
            />
            <AccountMenuItem
              icon={HelpCircle}
              label="Bantuan Modul"
              onClick={() => {
                setOpen(false);
                onOpenHelp();
              }}
              testId="account-help"
            />
            <AccountMenuItem
              icon={BookOpen}
              label="Panduan Penggunaan"
              onClick={() => {
                setOpen(false);
                onOpenGuide();
              }}
              testId="account-guide"
            />
          </div>

          {/* Theme toggle row */}
          <div className="px-3 py-2 border-t border-[var(--glass-border)] flex items-center justify-between">
            <span className="text-xs text-foreground/60 flex items-center gap-2">
              <Sun className="w-3.5 h-3.5" />
              Tema tampilan
            </span>
            <ThemeToggle />
          </div>

          {/* Logout */}
          <div className="py-1.5 border-t border-[var(--glass-border)]">
            <button
              onClick={() => {
                setOpen(false);
                onLogout();
              }}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10 transition-colors duration-150"
              data-testid="topbar-logout-btn"
            >
              <LogOut className="w-4 h-4 shrink-0" />
              Keluar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
