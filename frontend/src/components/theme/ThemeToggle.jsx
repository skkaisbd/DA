/**
 * ThemeToggle — cycle button for light / dark / classic / system.
 *
 * Cycle order: light → dark → classic → system → light
 *
 * Icons:
 *   - light   → Sun
 *   - dark    → Moon
 *   - classic → Terminal (VS-like IDE vibe)
 *   - system  → Monitor (follow OS)
 *
 * Design per guidelines: glass icon button with lucide icons. The button
 * itself stays glass in galaxy/lavender. In `.classic` theme, inherited
 * tokens automatically flatten its surface to match VS look.
 */
import { Sun, Moon, Monitor, Terminal } from 'lucide-react';
import { useTheme } from './ThemeProvider';
import { cn } from '@/lib/utils';

const THEME_META = {
  light:   { Icon: Sun,      label: 'Mode Terang' },
  dark:    { Icon: Moon,     label: 'Mode Gelap' },
  classic: { Icon: Terminal, label: 'Mode Classic (VS)' },
  system:  { Icon: Monitor,  label: 'Ikut Sistem' },
};

export function ThemeToggle({ className }) {
  const { theme, toggleTheme } = useTheme();
  const meta = THEME_META[theme] || THEME_META.system;
  const { Icon, label } = meta;

  return (
    <button
      onClick={toggleTheme}
      aria-label={`Theme: ${label} (klik untuk ganti)`}
      title={label}
      data-testid="theme-toggle-btn"
      data-theme-state={theme}
      className={cn(
        'relative inline-flex items-center justify-center',
        'h-11 w-11 min-h-[44px] min-w-[44px] rounded-full border',
        'bg-[var(--nav-pill-bg)] border-[var(--glass-border)]',
        'text-foreground/70 hover:text-foreground hover:bg-[var(--nav-pill-active)]',
        'transition-[background-color,color,transform] duration-200 ease-brand',
        'active:scale-95',
        className
      )}
    >
      <Icon className="w-4 h-4" strokeWidth={2} />
    </button>
  );
}
