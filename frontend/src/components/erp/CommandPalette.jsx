/**
 * CommandPalette (Cmd+K) — Enhanced with Smart Search
 * Global module search, portal switcher, and data search accessible via keyboard.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  CommandDialog, CommandInput, CommandList, CommandEmpty,
  CommandGroup, CommandItem, CommandSeparator, CommandShortcut,
} from '@/components/ui/command';
import {
  Factory, Warehouse, DollarSign, Users, BarChart3,
  Sun, Moon, Monitor, Terminal, LogOut, Package,
  FileText, User, ShoppingBag, Receipt, Building2, Search, Loader2,
} from 'lucide-react';
import { useTheme } from '@/components/theme/ThemeProvider';
import { Badge } from '@/components/ui/badge';

const PORTAL_ITEMS = [
  { id: 'management', label: 'Portal Management', icon: BarChart3 },
  { id: 'production', label: 'Portal Produksi',   icon: Factory },
  { id: 'warehouse',  label: 'Portal Gudang',     icon: Warehouse },
  { id: 'finance',    label: 'Portal Finance',    icon: DollarSign },
  { id: 'hr',         label: 'Portal HR',         icon: Users },
];

const TYPE_ICONS = {
  order: FileText,
  employee: User,
  product: ShoppingBag,
  invoice: Receipt,
  client: Building2,
};

const TYPE_LABELS = {
  order: 'Order',
  employee: 'Karyawan',
  product: 'Produk',
  invoice: 'Invoice',
  client: 'Klien',
};

/**
 * Props:
 *   open, onOpenChange, currentPortal,
 *   onSelectPortal(portalId),
 *   onSelectModule(moduleId),
 *   moduleSuggestions: [{id, label, portal, icon}],
 *   onLogout,
 *   token: JWT token for API calls
 */
export function CommandPalette({
  open, onOpenChange, currentPortal,
  onSelectPortal, onSelectModule, onLogout,
  moduleSuggestions = [],
  token,
}) {
  const { theme, setTheme } = useTheme();
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchDebounce, setSearchDebounce] = useState(null);

  // Keyboard shortcut: Cmd/Ctrl+K to toggle
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key?.toLowerCase() === 'k') {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onOpenChange]);

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      setSearchQuery('');
      setSearchResults([]);
      setIsSearching(false);
    }
  }, [open]);

  // Debounced search
  const performSearch = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setSearchResults([]);
      return;
    }

    if (!token) {
      console.warn('No token available for search');
      return;
    }

    setIsSearching(true);
    try {
      const response = await fetch(
        `${process.env.REACT_APP_BACKEND_URL}/api/search?q=${encodeURIComponent(query)}&limit=5`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setSearchResults(data?.data?.results || []);
      } else {
        console.error('Search failed:', response.status);
        setSearchResults([]);
      }
    } catch (error) {
      console.error('Search error:', error);
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  }, [token]);

  // Handle search input change with debounce
  const handleSearchChange = (value) => {
    setSearchQuery(value);

    // Clear existing debounce
    if (searchDebounce) {
      clearTimeout(searchDebounce);
    }

    // Set new debounce
    const timeout = setTimeout(() => {
      performSearch(value);
    }, 300);

    setSearchDebounce(timeout);
  };

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (searchDebounce) {
        clearTimeout(searchDebounce);
      }
    };
  }, [searchDebounce]);

  const close = () => onOpenChange(false);

  const handlePortal = (pid) => {
    onSelectPortal?.(pid);
    close();
  };

  const handleModule = (mid) => {
    onSelectModule?.(mid);
    close();
  };

  const handleTheme = (mode) => {
    setTheme(mode);
  };

  const handleDataResult = (result) => {
    if (result.url) {
      window.location.href = result.url;
    }
    close();
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput 
        placeholder="Ketik untuk mencari modul, data, atau perintah..." 
        data-testid="cmdk-input"
        value={searchQuery}
        onValueChange={handleSearchChange}
      />
      <CommandList>
        <CommandEmpty>
          {isSearching ? (
            <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Mencari...</span>
            </div>
          ) : (
            <div className="py-6 text-center text-sm">
              <Search className="w-8 h-8 mx-auto mb-2 text-muted-foreground/40" />
              <p className="text-muted-foreground">Tidak ada hasil ditemukan.</p>
              <p className="text-xs text-muted-foreground/60 mt-1">Coba kata kunci lain</p>
            </div>
          )}
        </CommandEmpty>

        {/* Search Results (Data) */}
        {searchResults.length > 0 && (
          <>
            <CommandGroup heading="Hasil Pencarian Data">
              {searchResults.slice(0, 10).map((result, idx) => {
                const Icon = TYPE_ICONS[result.type] || Package;
                return (
                  <CommandItem
                    key={`search-${idx}`}
                    onSelect={() => handleDataResult(result)}
                    data-testid={`cmdk-search-${result.type}-${idx}`}
                  >
                    <Icon className="mr-2 w-4 h-4 text-foreground/60" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate">{result.title}</span>
                        <Badge variant="outline" className="text-[10px] shrink-0">
                          {TYPE_LABELS[result.type] || result.type}
                        </Badge>
                      </div>
                      {result.subtitle && (
                        <div className="text-xs text-muted-foreground truncate">{result.subtitle}</div>
                      )}
                    </div>
                  </CommandItem>
                );
              })}
            </CommandGroup>
            <CommandSeparator />
          </>
        )}

        {/* Portal Switcher - only show if no search or short query */}
        {searchQuery.length < 2 && (
          <>
            <CommandGroup heading="Pindah Portal">
              {PORTAL_ITEMS.map(p => {
                const Icon = p.icon;
                return (
                  <CommandItem
                    key={p.id}
                    onSelect={() => handlePortal(p.id)}
                    disabled={p.id === currentPortal}
                    data-testid={`cmdk-portal-${p.id}`}
                  >
                    <Icon className="mr-2 w-4 h-4" />
                    <span>{p.label}</span>
                    {p.id === currentPortal && (
                      <CommandShortcut className="text-[hsl(var(--primary))] font-semibold">aktif</CommandShortcut>
                    )}
                  </CommandItem>
                );
              })}
            </CommandGroup>
            <CommandSeparator />
          </>
        )}

        {/* Module Navigation - filter by search query */}
        {moduleSuggestions.length > 0 && (
          <>
            <CommandGroup heading="Navigasi Menu">
              {moduleSuggestions
                .filter(m => {
                  if (searchQuery.length < 2) return true;
                  return m.label.toLowerCase().includes(searchQuery.toLowerCase());
                })
                .map((m) => {
                  const Icon = m.icon || Package;
                  // moduleId = the actual portal-nav id (used for routing & dedupe).
                  // m.id = compound id (`<portalId>::<moduleId>`) ensures unique
                  // React keys across portals (PortalShell.jsx Session #11.13 fix).
                  const targetId = m.moduleId || m.id;
                  return (
                    <CommandItem
                      key={m.id}
                      onSelect={() => handleModule(targetId)}
                      data-testid={`cmdk-module-${targetId}`}
                    >
                      <Icon className="mr-2 w-4 h-4 text-foreground/60" />
                      <span>{m.label}</span>
                      {m.portal && <CommandShortcut className="text-[10px] uppercase tracking-wider">{m.portal}</CommandShortcut>}
                    </CommandItem>
                  );
                })}
            </CommandGroup>
            <CommandSeparator />
          </>
        )}

        {/* Theme & Settings - only show if no search */}
        {searchQuery.length < 2 && (
          <>
            <CommandGroup heading="Tampilan">
              <CommandItem onSelect={() => handleTheme('light')} data-testid="cmdk-theme-light">
                <Sun className="mr-2 w-4 h-4" />
                <span>Mode Terang</span>
                {theme === 'light' && <CommandShortcut>aktif</CommandShortcut>}
              </CommandItem>
              <CommandItem onSelect={() => handleTheme('dark')} data-testid="cmdk-theme-dark">
                <Moon className="mr-2 w-4 h-4" />
                <span>Mode Gelap</span>
                {theme === 'dark' && <CommandShortcut>aktif</CommandShortcut>}
              </CommandItem>
              <CommandItem onSelect={() => handleTheme('classic')} data-testid="cmdk-theme-classic">
                <Terminal className="mr-2 w-4 h-4" />
                <span>Mode Classic (Visual Studio)</span>
                {theme === 'classic' && <CommandShortcut>aktif</CommandShortcut>}
              </CommandItem>
              <CommandItem onSelect={() => handleTheme('system')} data-testid="cmdk-theme-system">
                <Monitor className="mr-2 w-4 h-4" />
                <span>Ikut Sistem</span>
                {theme === 'system' && <CommandShortcut>aktif</CommandShortcut>}
              </CommandItem>
            </CommandGroup>
            <CommandSeparator />
            <CommandGroup heading="Akun">
              <CommandItem onSelect={() => { onLogout?.(); close(); }} data-testid="cmdk-logout">
                <LogOut className="mr-2 w-4 h-4" />
                <span>Keluar dari sistem</span>
              </CommandItem>
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
}
