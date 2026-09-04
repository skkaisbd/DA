/**
 * GlobalSearch — topbar search input + debounced dropdown of /api/global-search results.
 *
 * Clicking a result calls `onResultSelect(result.module)` which is wired up to
 * `onModuleChange` in PortalShell.
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { Search, X } from 'lucide-react';

export default function GlobalSearch({ token, onResultSelect }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchRef = useRef(null);
  const searchTimeout = useRef(null);

  // Close on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setSearchOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleSearchInput = useCallback(
    (q) => {
      setSearchQuery(q);
      if (!q.trim()) {
        setSearchResults([]);
        setSearchOpen(false);
        return;
      }
      setSearchOpen(true);
      clearTimeout(searchTimeout.current);
      searchTimeout.current = setTimeout(async () => {
        setSearchLoading(true);
        try {
          const res = await fetch(`/api/global-search?q=${encodeURIComponent(q)}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          const data = await res.json();
          setSearchResults(data.results || []);
        } catch (e) {
          setSearchResults([]);
        } finally {
          setSearchLoading(false);
        }
      }, 300);
    },
    [token]
  );

  const handleSelect = (result) => {
    onResultSelect(result.module);
    setSearchQuery('');
    setSearchResults([]);
    setSearchOpen(false);
  };

  const handleClear = () => {
    setSearchQuery('');
    setSearchResults([]);
    setSearchOpen(false);
  };

  return (
    <div ref={searchRef} className="relative hidden sm:block w-56 lg:w-72">
      <div className="flex items-center gap-2 border border-[var(--glass-border)] rounded-full px-3 py-1.5 bg-[var(--nav-pill-bg)] backdrop-blur-xl focus-within:border-[hsl(var(--primary)/0.4)] transition-colors duration-150">
        <Search className="w-3.5 h-3.5 text-foreground/40 shrink-0" />
        <input
          type="text"
          placeholder="Cari order, WO, SKU..."
          className="flex-1 bg-transparent text-xs text-foreground placeholder:text-foreground/40 focus:outline-none"
          value={searchQuery}
          onChange={(e) => handleSearchInput(e.target.value)}
          onFocus={() => searchQuery && setSearchOpen(true)}
          data-testid="topbar-global-search-input"
        />
        {searchQuery && (
          <button onClick={handleClear} data-testid="search-clear-btn" aria-label="Bersihkan pencarian">
            <X className="w-3.5 h-3.5 text-foreground/40 hover:text-foreground/70" />
          </button>
        )}
      </div>

      {searchOpen && (
        <div className="absolute top-full mt-1.5 left-0 right-0 rounded-[var(--radius-md)] border border-[var(--glass-border)] bg-[var(--popover-surface)] backdrop-blur-[var(--glass-blur-strong)] shadow-[var(--shadow-soft)] z-50 overflow-hidden">
          {searchLoading ? (
            <div className="px-4 py-3 text-xs text-foreground/50 text-center">Mencari...</div>
          ) : searchResults.length === 0 ? (
            <div className="px-4 py-3 text-xs text-foreground/40 text-center">
              Tidak ada hasil untuk "{searchQuery}"
            </div>
          ) : (
            <div className="max-h-80 overflow-y-auto">
              {searchResults.map((r, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSelect(r)}
                  className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-[var(--glass-bg-hover)] text-left transition-colors duration-150 border-b border-[var(--glass-border)] last:border-0"
                  data-testid={`search-result-${idx}`}
                >
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold shrink-0 bg-[var(--nav-pill-active)] text-foreground/70 uppercase">
                    {r.type}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-foreground truncate">{r.label}</p>
                    {r.sub && <p className="text-[10px] text-foreground/50 truncate">{r.sub}</p>}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
