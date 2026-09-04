/**
 * DataTable v2 — PT Rahaza ERP (Phase 13.1)
 *
 * Universal table untuk semua modul CRUD. Sebelumnya tiap modul re-implement
 * sendiri; sekarang konsisten lewat komponen ini.
 *
 * Features:
 *   - Search (debounce 250ms, case-insensitive across searchFields)
 *   - Filter chips (type: 'select' | 'multi' | 'date-range')
 *   - Column sort (asc/desc) — klik header toggle
 *   - Pagination (client-side default)
 *   - Row selection (multi-select) + bulkActions slot
 *   - Column visibility toggle (persist localStorage per tableId)
 *   - Density toggle (compact / default / spacious)
 *   - Export button (slot — pemanggil menyediakan exportFn)
 *   - Empty / loading / error states dengan atom EmptyState konsisten
 *   - data-testid konsisten untuk testing
 *
 * Props:
 *   tableId          — unique string untuk persist preferensi per tabel (localStorage)
 *   columns          — [{key, label, accessor?, render?, sortable?, hidden?, align?, className?, width?}]
 *   rows             — array of objects
 *   loading          — boolean
 *   error            — string | null
 *   searchFields     — array of keys utk search (default: semua string fields)
 *   filters          — [{key, label, type, options?, accessor?}]
 *   rowKey           — key unik row (default: 'id')
 *   initialSort      — {key, dir: 'asc'|'desc'}
 *   pageSizeOptions  — [10, 25, 50, 100] (default 10)
 *   pageSize         — default page size
 *   selectable       — enable row selection (default false)
 *   bulkActions      — (selectedRows, clearSelection) => ReactNode
 *   rowActions       — (row) => ReactNode (kolom terakhir per row)
 *   exportFn         — async (filteredRows) => void
 *   emptyTitle/Description/Icon
 *   onRowClick       — (row) => void
 *   toolbar          — extra toolbar actions (kanan, sebelum Export)
 */
import { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import {
  Search, X, ArrowUpDown, ArrowUp, ArrowDown, ChevronLeft, ChevronRight,
  SlidersHorizontal, Download, Rows3, Rows2, Rows4, Check, Inbox,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { ResponsiveTableWrapper } from '@/components/ui/responsive-table-wrapper';

function useDebouncedValue(value, delay = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

// Download helper — CSV fallback bila exportFn tidak disuplai
function downloadCSV(filename, columns, rows) {
  const header = columns.filter(c => !c.hidden).map(c => `"${c.label.replace(/"/g, '""')}"`).join(',');
  const body = rows.map(r => columns.filter(c => !c.hidden).map(c => {
    const v = c.accessor ? c.accessor(r) : r[c.key];
    const s = (v === null || v === undefined) ? '' : String(v);
    return `"${s.replace(/"/g, '""').replace(/\n/g, ' ')}"`;
  }).join(',')).join('\n');
  const blob = new Blob([`\uFEFF${header}\n${body}`], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

const DENSITY = {
  compact:   { cell: 'px-2.5 py-1.5 text-[11px]', height: 'h-8' },
  default:   { cell: 'px-3 py-2 text-xs',         height: 'h-10' },
  spacious:  { cell: 'px-4 py-3 text-sm',         height: 'h-12' },
};

export function DataTable({
  tableId = 'rahaza-default',
  columns,
  rows = [],
  loading = false,
  error = null,
  searchFields,
  filters = [],
  rowKey = 'id',
  initialSort,
  pageSizeOptions = [10, 25, 50, 100],
  pageSize: initialPageSize = 10,
  selectable = false,
  bulkActions,
  rowActions,
  exportFn,
  exportFilename,
  showExport = true,   // set false to hide the built-in Export button (e.g. when a registry Ekspor toolbar already provides it)
  emptyTitle = 'Belum ada data',
  emptyDescription = 'Data akan muncul di sini saat tersedia.',
  emptyIcon: EmptyIcon = Inbox,
  emptyAction, // Phase 16: optional React node for primary CTA
  emptyHelp,   // Phase 16: optional tooltip/help text beneath the CTA
  onRowClick,
  toolbar,
  className,
}) {
  // ── State ────────────────────────────────────────────────────────────────
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebouncedValue(search, 250);
  const [filterState, setFilterState] = useState({});
  const [sort, setSort] = useState(initialSort || null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [selected, setSelected] = useState(new Set());
  const [density, setDensity] = useState(() => {
    try { return localStorage.getItem(`dtv2:${tableId}:density`) || 'default'; } catch { return 'default'; }
  });
  const [hiddenCols, setHiddenCols] = useState(() => {
    try {
      const raw = localStorage.getItem(`dtv2:${tableId}:hiddenCols`);
      return raw ? new Set(JSON.parse(raw)) : new Set();
    } catch { return new Set(); }
  });
  const [colMenuOpen, setColMenuOpen] = useState(false);
  const colMenuRef = useRef(null);

  // Persist preferences
  useEffect(() => {
    try { localStorage.setItem(`dtv2:${tableId}:density`, density); } catch {/* ignore */}
  }, [density, tableId]);
  useEffect(() => {
    try { localStorage.setItem(`dtv2:${tableId}:hiddenCols`, JSON.stringify([...hiddenCols])); } catch {/* ignore */}
  }, [hiddenCols, tableId]);

  // Outside click untuk col menu
  useEffect(() => {
    const h = (e) => { if (colMenuRef.current && !colMenuRef.current.contains(e.target)) setColMenuOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  // Reset page saat filter/search berubah
  useEffect(() => { setPage(1); }, [debouncedSearch, filterState, sort, pageSize]);

  // ── Derive filtered rows ─────────────────────────────────────────────────
  const visibleColumns = columns.filter(c => !hiddenCols.has(c.key));

  const filtered = useMemo(() => {
    // Defensive: rows may briefly be non-array during async loads / error responses.
    let out = Array.isArray(rows) ? rows : [];

    // Search
    if (debouncedSearch && debouncedSearch.trim()) {
      const q = debouncedSearch.toLowerCase().trim();
      const fields = searchFields && searchFields.length ? searchFields : columns.map(c => c.key);
      out = out.filter(r => fields.some(k => {
        const v = r[k];
        if (v === null || v === undefined) return false;
        return String(v).toLowerCase().includes(q);
      }));
    }

    // Filters
    Object.entries(filterState).forEach(([k, v]) => {
      if (v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0)) return;
      const f = filters.find(ff => ff.key === k);
      if (!f) return;
      if (f.type === 'select') {
        out = out.filter(r => {
          const cell = f.accessor ? f.accessor(r) : r[k];
          return String(cell) === String(v);
        });
      } else if (f.type === 'multi') {
        const set = new Set(v.map(String));
        out = out.filter(r => {
          const cell = f.accessor ? f.accessor(r) : r[k];
          return set.has(String(cell));
        });
      } else if (f.type === 'date-range') {
        const { from, to } = v || {};
        out = out.filter(r => {
          const cell = f.accessor ? f.accessor(r) : r[k];
          if (!cell) return false;
          if (from && cell < from) return false;
          if (to && cell > to) return false;
          return true;
        });
      }
    });

    // Sort
    if (sort && sort.key) {
      const col = columns.find(c => c.key === sort.key);
      const getter = col?.accessor || ((r) => r[sort.key]);
      const dir = sort.dir === 'desc' ? -1 : 1;
      out = [...out].sort((a, b) => {
        const va = getter(a); const vb = getter(b);
        if (va == null && vb == null) return 0;
        if (va == null) return 1 * dir;
        if (vb == null) return -1 * dir;
        if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
        return String(va).localeCompare(String(vb), 'id', { numeric: true }) * dir;
      });
    }
    return out;
  }, [rows, debouncedSearch, searchFields, filterState, filters, sort, columns]);

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);
  const paged = useMemo(() => filtered.slice((safePage - 1) * pageSize, safePage * pageSize), [filtered, safePage, pageSize]);

  // ── Selection ────────────────────────────────────────────────────────────
  const allPageSelected = paged.length > 0 && paged.every(r => selected.has(r[rowKey]));
  const toggleRow = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };
  const togglePage = () => {
    setSelected(prev => {
      const next = new Set(prev);
      if (allPageSelected) paged.forEach(r => next.delete(r[rowKey]));
      else paged.forEach(r => next.add(r[rowKey]));
      return next;
    });
  };
  const clearSelection = () => setSelected(new Set());
  const selectedRows = useMemo(() => (Array.isArray(rows) ? rows : []).filter(r => selected.has(r[rowKey])), [rows, selected, rowKey]);

  // ── Sort handler ─────────────────────────────────────────────────────────
  const toggleSort = (key) => {
    const col = columns.find(c => c.key === key);
    if (!col || !col.sortable) return;
    setSort(prev => {
      if (!prev || prev.key !== key) return { key, dir: 'asc' };
      if (prev.dir === 'asc') return { key, dir: 'desc' };
      return null;
    });
  };

  // ── Export ──────────────────────────────────────────────────────────────
  const handleExport = async () => {
    if (exportFn) {
      await exportFn(filtered);
    } else {
      const name = exportFilename || `${tableId}-${new Date().toISOString().slice(0, 10)}.csv`;
      downloadCSV(name, visibleColumns, filtered);
    }
  };

  // ── Reset filters ───────────────────────────────────────────────────────
  const hasActiveFilter = debouncedSearch || Object.values(filterState).some(v =>
    v && (!Array.isArray(v) || v.length > 0) && v !== '');
  const resetAll = () => {
    setSearch('');
    setFilterState({});
    setSort(null);
    setPage(1);
  };

  const cellClass = DENSITY[density].cell;
  const rowClass  = DENSITY[density].height;

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div className={cn('rounded-[var(--radius-lg)] border border-[var(--glass-border)] bg-[var(--card-surface)] backdrop-blur-[var(--glass-blur)] overflow-hidden', className)} data-testid={`dtv2-${tableId}`}>
      {/* ── Toolbar (TD-015: stacks vertically on mobile) ──────────────── */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-2 px-3 py-2.5 border-b border-[var(--glass-border)] bg-[var(--glass-bg)]">
        {/* Search */}
        <div className="relative flex-1 sm:min-w-[180px] sm:max-w-[360px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground/40" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cari..."
            className="w-full h-9 pl-8 pr-8 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs text-foreground focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] focus-visible:outline-none"
            data-testid={`dtv2-${tableId}-search`}
            aria-label="Cari"
          />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-foreground/40 hover:text-foreground">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Filter chips */}
        {filters.map((f) => (
          <FilterChip
            key={f.key}
            filter={f}
            value={filterState[f.key]}
            onChange={(v) => setFilterState(prev => ({ ...prev, [f.key]: v }))}
            testId={`dtv2-${tableId}-filter-${f.key}`}
          />
        ))}

        {hasActiveFilter && (
          <button
            onClick={resetAll}
            className="h-9 px-2.5 rounded-lg border border-[var(--glass-border)] text-[11px] text-foreground/70 hover:text-foreground hover:bg-[var(--glass-bg-hover)] transition-colors"
            data-testid={`dtv2-${tableId}-reset`}
          >
            Reset
          </button>
        )}

        <div className="flex-1" />

        {toolbar}

        {/* Column visibility */}
        <div className="relative" ref={colMenuRef}>
          <button
            onClick={() => setColMenuOpen(o => !o)}
            className="h-9 w-9 rounded-lg border border-[var(--glass-border)] text-foreground/60 hover:text-foreground hover:bg-[var(--glass-bg-hover)] flex items-center justify-center"
            title="Kolom terlihat"
            aria-label="Kolom terlihat"
            data-testid={`dtv2-${tableId}-cols-btn`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
          </button>
          {colMenuOpen && (
            <div className="absolute top-full right-0 mt-1.5 w-[180px] rounded-lg border border-[var(--glass-border)] bg-[var(--popover-surface)] backdrop-blur-[var(--glass-blur-strong)] shadow-[var(--shadow-soft)] z-30 p-1.5">
              <p className="px-2 py-1 text-[10px] uppercase tracking-wider text-foreground/50 font-semibold">Kolom</p>
              {columns.map(c => {
                const visible = !hiddenCols.has(c.key);
                return (
                  <button
                    key={c.key}
                    onClick={() => setHiddenCols(prev => {
                      const next = new Set(prev);
                      next.has(c.key) ? next.delete(c.key) : next.add(c.key);
                      return next;
                    })}
                    className="w-full flex items-center gap-2 px-2 py-1.5 text-left text-xs text-foreground/80 hover:bg-[var(--glass-bg-hover)] rounded"
                  >
                    <div className={cn('w-3.5 h-3.5 rounded border flex items-center justify-center',
                      visible ? 'bg-[hsl(var(--primary))] border-[hsl(var(--primary))]' : 'border-[var(--glass-border)]')}>
                      {visible && <Check className="w-2.5 h-2.5 text-foreground" strokeWidth={3} />}
                    </div>
                    <span className="truncate">{c.label}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Density toggle */}
        <div className="hidden md:flex items-center rounded-lg border border-[var(--glass-border)] overflow-hidden">
          {[
            { k: 'compact',  icon: Rows4, label: 'Compact' },
            { k: 'default',  icon: Rows3, label: 'Default' },
            { k: 'spacious', icon: Rows2, label: 'Spacious' },
          ].map(({ k, icon: Icon, label }) => (
            <button
              key={k}
              onClick={() => setDensity(k)}
              className={cn('h-9 w-9 flex items-center justify-center border-l first:border-l-0 border-[var(--glass-border)] transition-colors',
                density === k ? 'bg-[hsl(var(--primary)/0.15)] text-[hsl(var(--primary))]' : 'text-foreground/50 hover:text-foreground hover:bg-[var(--glass-bg-hover)]')}
              title={`Density: ${label}`}
              aria-label={`Density ${label}`}
              data-testid={`dtv2-${tableId}-density-${k}`}
            >
              <Icon className="w-3.5 h-3.5" />
            </button>
          ))}
        </div>

        {/* Export */}
        {showExport && (
          <button
            onClick={handleExport}
            disabled={filtered.length === 0}
            className="h-9 px-3 rounded-lg border border-[var(--glass-border)] text-[11px] font-medium text-foreground/80 hover:text-foreground hover:bg-[var(--glass-bg-hover)] flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid={`dtv2-${tableId}-export`}
          >
            <Download className="w-3.5 h-3.5" />
            Export
          </button>
        )}
      </div>

      {/* ── Bulk action bar ───────────────────────────────────────── */}
      {selectable && selected.size > 0 && (
        <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--glass-border)] bg-[hsl(var(--primary)/0.08)]" data-testid={`dtv2-${tableId}-bulk-bar`}>
          <span className="text-xs font-medium text-[hsl(var(--primary))]">{selected.size} baris dipilih</span>
          <div className="flex items-center gap-2">
            {bulkActions && bulkActions(selectedRows, clearSelection)}
            <button onClick={clearSelection} className="text-[11px] text-foreground/60 hover:text-foreground">Batal</button>
          </div>
        </div>
      )}

      {/* ── Table (TD-015: ResponsiveTableWrapper for scroll-shadow + mobile) */}
      <ResponsiveTableWrapper>
        <table className="w-full min-w-max">
          <thead>
            <tr className="border-b border-[var(--glass-border)] bg-[var(--glass-bg)]">
              {selectable && (
                <th className={cn('w-8', cellClass)}>
                  <input
                    type="checkbox"
                    checked={allPageSelected}
                    onChange={togglePage}
                    className="cursor-pointer"
                    aria-label="Pilih semua di halaman ini"
                  />
                </th>
              )}
              {visibleColumns.map(c => (
                <th
                  key={c.key}
                  className={cn(
                    cellClass, 'text-left font-semibold uppercase tracking-wider text-[10px] text-foreground/50',
                    c.sortable && 'cursor-pointer select-none hover:text-foreground/80',
                    c.align === 'right' && 'text-right',
                    c.align === 'center' && 'text-center',
                    c.className,
                  )}
                  style={c.width ? { width: c.width } : undefined}
                  onClick={() => c.sortable && toggleSort(c.key)}
                  data-testid={`dtv2-${tableId}-th-${c.key}`}
                >
                  <span className="inline-flex items-center gap-1">
                    {c.label}
                    {c.sortable && (
                      sort?.key === c.key
                        ? (sort.dir === 'asc'
                            ? <ArrowUp className="w-3 h-3 text-[hsl(var(--primary))]" />
                            : <ArrowDown className="w-3 h-3 text-[hsl(var(--primary))]" />)
                        : <ArrowUpDown className="w-3 h-3 opacity-40" />
                    )}
                  </span>
                </th>
              ))}
              {rowActions && <th className={cn(cellClass, 'text-right w-24 font-semibold uppercase tracking-wider text-[10px] text-foreground/50')}>Aksi</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className={rowClass}>
                  <td colSpan={visibleColumns.length + (selectable ? 1 : 0) + (rowActions ? 1 : 0)} className={cn(cellClass)}>
                    <div className="h-4 rounded bg-[var(--glass-bg)] animate-pulse" />
                  </td>
                </tr>
              ))
            ) : error ? (
              <tr>
                <td colSpan={visibleColumns.length + (selectable ? 1 : 0) + (rowActions ? 1 : 0)} className="py-14 text-center text-xs text-[hsl(var(--destructive))]">{error}</td>
              </tr>
            ) : paged.length === 0 ? (
              <tr>
                <td colSpan={visibleColumns.length + (selectable ? 1 : 0) + (rowActions ? 1 : 0)} className="py-16 text-center">
                  <EmptyIcon className="w-10 h-10 mx-auto text-foreground/20 mb-2" strokeWidth={1.5} />
                  <p className="text-xs font-medium text-foreground/70">{emptyTitle}</p>
                  <p className="text-[11px] text-foreground/40 mt-0.5">{emptyDescription}</p>
                  {emptyAction && (
                    <div className="mt-4 flex items-center justify-center gap-2">{emptyAction}</div>
                  )}
                  {emptyHelp && (
                    <p className="text-[10px] text-foreground/35 mt-2 max-w-md mx-auto leading-relaxed">{emptyHelp}</p>
                  )}
                </td>
              </tr>
            ) : (
              paged.map((row) => (
                <tr
                  key={row[rowKey]}
                  className={cn(
                    'border-b border-[var(--glass-border)] last:border-0 transition-colors',
                    rowClass,
                    onRowClick && 'cursor-pointer hover:bg-[var(--glass-bg-hover)]',
                    selected.has(row[rowKey]) && 'bg-[hsl(var(--primary)/0.06)]',
                  )}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  data-testid={`dtv2-${tableId}-row-${row[rowKey]}`}
                >
                  {selectable && (
                    <td className={cn(cellClass)} onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected.has(row[rowKey])}
                        onChange={() => toggleRow(row[rowKey])}
                        className="cursor-pointer"
                        aria-label="Pilih baris"
                      />
                    </td>
                  )}
                  {visibleColumns.map(c => {
                    const value = c.accessor ? c.accessor(row) : row[c.key];
                    return (
                      <td
                        key={c.key}
                        className={cn(cellClass, 'text-foreground/90 whitespace-nowrap',
                          c.align === 'right' && 'text-right',
                          c.align === 'center' && 'text-center',
                          c.className,
                        )}
                      >
                        {c.render ? c.render(row, value) : (value === null || value === undefined ? '—' : value)}
                      </td>
                    );
                  })}
                  {rowActions && <td className={cn(cellClass, 'text-right')} onClick={(e) => e.stopPropagation()}>{rowActions(row)}</td>}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </ResponsiveTableWrapper>

      {/* ── Pagination footer ───────────────────────────────────── */}
      {!loading && total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-t border-[var(--glass-border)] bg-[var(--glass-bg)] text-[11px] text-foreground/60">
          <div className="flex items-center gap-2">
            <span>
              Menampilkan <b className="text-foreground/80">{((safePage - 1) * pageSize) + 1}–{Math.min(safePage * pageSize, total)}</b> dari <b className="text-foreground/80">{total}</b>
            </span>
            <span className="mx-1">·</span>
            <label className="inline-flex items-center gap-1">
              Tampil
              <select
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value))}
                className="h-7 px-1.5 rounded border border-[var(--glass-border)] bg-[var(--input-surface)] text-[11px]"
                aria-label="Jumlah per halaman"
              >
                {pageSizeOptions.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={safePage <= 1}
              className="h-7 w-7 rounded border border-[var(--glass-border)] flex items-center justify-center text-foreground/60 hover:text-foreground hover:bg-[var(--glass-bg-hover)] disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Halaman sebelumnya"
              data-testid={`dtv2-${tableId}-prev`}
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <span className="px-2 text-foreground/70">Hal <b className="text-foreground/90">{safePage}</b> / {totalPages}</span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={safePage >= totalPages}
              className="h-7 w-7 rounded border border-[var(--glass-border)] flex items-center justify-center text-foreground/60 hover:text-foreground hover:bg-[var(--glass-bg-hover)] disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Halaman berikutnya"
              data-testid={`dtv2-${tableId}-next`}
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


/* ──────────────────────────────────────────────────────────────────── */
/*  FilterChip — select / multi / date-range                            */
/* ──────────────────────────────────────────────────────────────────── */
function FilterChip({ filter, value, onChange, testId }) {
  if (filter.type === 'select') {
    return (
      <select
        value={value || ''}
        onChange={(e) => onChange(e.target.value || null)}
        className="h-9 px-2.5 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs text-foreground focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] focus-visible:outline-none"
        data-testid={testId}
        aria-label={filter.label}
      >
        <option value="">{filter.label}</option>
        {filter.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    );
  }
  if (filter.type === 'date-range') {
    const v = value || {};
    return (
      <div className="flex items-center gap-1" data-testid={testId}>
        <input
          type="date"
          value={v.from || ''}
          onChange={(e) => onChange({ ...v, from: e.target.value || null })}
          className="h-9 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs text-foreground"
          aria-label={`${filter.label} dari`}
          placeholder="Dari"
        />
        <span className="text-foreground/40 text-xs">–</span>
        <input
          type="date"
          value={v.to || ''}
          onChange={(e) => onChange({ ...v, to: e.target.value || null })}
          className="h-9 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs text-foreground"
          aria-label={`${filter.label} sampai`}
          placeholder="Sampai"
        />
      </div>
    );
  }
  // multi — untuk keringkasan, render checkbox list inline
  return null;
}
