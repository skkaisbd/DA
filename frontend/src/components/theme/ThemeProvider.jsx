/**
 * ThemeProvider — tri-theme (light / dark / classic) + system follow
 * untuk PT Rahaza ERP.
 *
 * Modes:
 *   - 'light'   → Lavender Clean
 *   - 'dark'    → Galaxy Glass
 *   - 'classic' → Visual Studio (IDE light gray + colorful icons)
 *   - 'system'  → follow OS prefers-color-scheme (resolves to light|dark)
 *
 * Applies class `light` | `dark` | `classic` ke <html> element.
 * Shadcn & Tailwind darkMode: 'class' config tetap compatible.
 */
import { createContext, useContext, useEffect, useState, useCallback } from 'react';

const ThemeContext = createContext({
  theme: 'system',         // user preference: 'light' | 'dark' | 'classic' | 'system'
  resolvedTheme: 'dark',   // actual applied: 'light' | 'dark' | 'classic'
  setTheme: () => {},
  toggleTheme: () => {},
  forceTheme: () => {},
});

const STORAGE_KEY = 'rahaza-theme';
const VALID_THEMES = ['light', 'dark', 'classic', 'system'];

function getSystemTheme() {
  // Keputusan owner 2026-07-27: LIGHT MODE adalah default resmi aplikasi.
  // Preferensi OS TIDAK lagi dipakai untuk memilih dark otomatis, karena
  // perbaikan keterbacaan (kontras kartu/tabel) difokuskan pada light mode.
  // User tetap bisa memilih dark/classic secara manual lewat pengalih tema.
  return 'light';
}

function applyTheme(resolved) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  // Clear all theme classes before applying new one
  root.classList.remove('light', 'dark', 'classic');
  root.classList.add(resolved);
  root.setAttribute('data-theme', resolved);
}

export function ThemeProvider({ children, defaultTheme = 'system' }) {
  const [theme, setThemeState] = useState(() => {
    if (typeof window === 'undefined') return defaultTheme;
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && VALID_THEMES.includes(stored)) return stored;
      return defaultTheme;
    } catch {
      return defaultTheme;
    }
  });

  const [resolvedTheme, setResolvedTheme] = useState(() =>
    theme === 'system' ? getSystemTheme() : theme
  );

  // Apply theme on mount + when theme changes
  useEffect(() => {
    const resolved = theme === 'system' ? getSystemTheme() : theme;
    setResolvedTheme(resolved);
    applyTheme(resolved);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  // Listen to system preference changes (only when theme === 'system')
  useEffect(() => {
    if (theme !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: light)');
    const handler = () => {
      const resolved = getSystemTheme();
      setResolvedTheme(resolved);
      applyTheme(resolved);
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [theme]);

  const setTheme = useCallback((next) => {
    if (!VALID_THEMES.includes(next)) return;
    setThemeState(next);
  }, []);

  // [PORTAL LIGHT DEFAULT] Apply a theme to <html> WITHOUT persisting the user's
  // global preference. Passing a falsy value restores the stored preference.
  // Used to force LIGHT mode on Maklon + external portals (vendor/client/creator/livehost).
  const forceTheme = useCallback((t) => {
    if (t && ['light', 'dark', 'classic'].includes(t)) {
      applyTheme(t);
      setResolvedTheme(t);
    } else {
      const resolved = theme === 'system' ? getSystemTheme() : theme;
      applyTheme(resolved);
      setResolvedTheme(resolved);
    }
  }, [theme]);

  const toggleTheme = useCallback(() => {
    // cycle: light → dark → classic → system → light
    setThemeState((curr) => {
      switch (curr) {
        case 'light':   return 'dark';
        case 'dark':    return 'classic';
        case 'classic': return 'system';
        case 'system':
        default:        return 'light';
      }
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme, toggleTheme, forceTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
