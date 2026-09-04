/**
 * MobileBottomNav — Portal Saya Mobile Navigation
 * Batch 4 — E-11: Mobile-first redesign Portal Saya
 *
 * Shows a bottom navigation bar on mobile (hidden on md+) with
 * the 5 most-used Portal Saya shortcuts.
 * Renders only when portal === 'self'.
 */
import { LayoutDashboard, UserCircle, Calendar, Banknote, Target, Clock } from 'lucide-react';

const PORTAL_SAYA_BOTTOM_NAV = [
  { id: 'portal-dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'portal-profile',   label: 'Profil',    icon: UserCircle },
  { id: 'portal-absen',     label: 'Absen',     icon: Clock },
  { id: 'portal-cuti',      label: 'Cuti',      icon: Calendar },
  { id: 'portal-payslip',   label: 'Slip Gaji', icon: Banknote },
  { id: 'kpi-portal',       label: 'KPI',       icon: Target },
];

export default function MobileBottomNav({ portal, currentModule, onModuleChange }) {
  if (portal !== 'self') return null;

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-50 safe-area-pb"
      data-testid="mobile-bottom-nav"
      aria-label="Navigasi Portal Saya"
    >
      {/* Blurred glass background */}
      <div className="flex items-center justify-around px-2 py-1 bg-[var(--card-surface)] backdrop-blur-[var(--glass-blur-strong)] border-t border-[var(--glass-border)] shadow-[var(--shadow-soft)]">
        {PORTAL_SAYA_BOTTOM_NAV.map(({ id, label, icon: Icon }) => {
          const active = currentModule === id;
          return (
            <button
              key={id}
              onClick={() => onModuleChange?.(id)}
              data-testid={`mobile-bottom-nav-${id}`}
              aria-label={label}
              aria-pressed={active}
              className={`
                flex flex-col items-center justify-center gap-0.5 min-w-0 flex-1 py-2 px-1 rounded-xl
                transition-colors duration-150 touch-manipulation
                ${active
                  ? 'text-[hsl(var(--primary))] bg-[hsl(var(--primary)/0.1)]'
                  : 'text-foreground/50 hover:text-foreground/70'
                }
              `}
            >
              <Icon className={`w-5 h-5 shrink-0 ${active ? 'scale-110' : ''} transition-transform duration-150`} />
              <span className={`text-[10px] font-medium truncate w-full text-center ${active ? 'text-[hsl(var(--primary))]' : ''}`}>
                {label}
              </span>
              {active && (
                <span className="absolute bottom-1 w-1 h-1 rounded-full bg-[hsl(var(--primary))]" aria-hidden="true" />
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
