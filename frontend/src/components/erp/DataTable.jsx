/**
 * DataTable v1 — LEGACY backward-compatible facade (Session #11.13 TD-013)
 * =========================================================================
 *
 * For consumers that need the legacy v1 behaviour exactly (e.g. `expandedRow`
 * inline row expansion, server-side `onSearch` callback), this file
 * transparently keeps the v1 implementation. For consumers that don't use
 * those legacy-specific features, we delegate to DataTable v2 so they
 * automatically gain v2 features (sort, filter, density, column visibility,
 * export, page-size selector, etc.).
 *
 *   v1 → v2 delegation rules:
 *     • If `expandedRow` is provided → keep v1 implementation (v2 has no
 *       equivalent of inline-expanded rows).
 *     • If `onSearch` is provided (server-side search) → keep v1.
 *     • Otherwise → delegate to v2 with prop translation.
 *
 *   Migration recommendation for new code:
 *     `import { DataTable } from './DataTableV2';`
 *     and pass v2 props directly.
 *
 *   v1 prop          →  v2 prop
 *   ──────────────────────────────────────────
 *   data             →  rows
 *   searchKeys       →  searchFields
 *   exportData       →  exportFn (wrapped to drop the rows arg)
 *   title            →  (ignored)
 *   actions          →  toolbar
 *
 *   columns[].render(value, row)  →  columns[].render(row, value)
 *     (v2 swaps arg order — wrapper auto-adapts)
 */
import React, { useMemo, useRef, useState } from 'react';
import { Search, ChevronLeft, ChevronRight, Download } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { DataTable as DataTableV2 } from './DataTableV2';

/* ───────────────── v1 → v2 column adapter ───────────────── */

function _adaptColumnsV1ToV2(v1Columns) {
  if (!Array.isArray(v1Columns)) return [];
  return v1Columns.map((c) => {
    if (!c) return c;
    const adapted = { ...c };
    if (typeof c.render === 'function') {
      adapted.render = (row, value) => c.render(value, row);
    }
    return adapted;
  });
}

/* ───────────────── v1 native impl (for legacy escape hatch) ───────────────── */

function DataTableV1Native({ columns, data, searchKeys = [], onSearch, actions, exportData, expandedRow }) {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const safeData = Array.isArray(data) ? data : [];
  const filtered = search
    ? safeData.filter((row) =>
        searchKeys.some((key) =>
          String(row[key] || '').toLowerCase().includes(search.toLowerCase()),
        ),
      )
    : safeData;

  const totalPages = Math.ceil(filtered.length / pageSize);
  const paginated = filtered.slice((page - 1) * pageSize, page * pageSize);

  const handleSearch = (val) => {
    setSearch(val);
    setPage(1);
    if (onSearch) onSearch(val);
  };

  return (
    <GlassCard hover={false} className="overflow-hidden">
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-4 border-b border-[var(--glass-border)]">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
          <input
            type="text"
            placeholder="Cari..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-[var(--glass-border)] bg-[var(--input-surface)] rounded-lg text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            aria-label="Cari"
          />
        </div>
        <div className="flex items-center gap-2">
          {exportData && (
            <button
              onClick={exportData}
              className="flex items-center gap-2 px-3 py-2 text-sm border border-[var(--glass-border)] rounded-lg hover:bg-[var(--glass-bg-hover)] text-muted-foreground transition-colors"
            >
              <Download className="w-4 h-4" /> Export
            </button>
          )}
          {actions}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="bg-[var(--glass-bg)]">
              {columns.map((col) => (
                <th key={col.key} className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--glass-border)]">
            {paginated.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="text-center py-12 text-muted-foreground text-sm">
                  Tidak ada data
                </td>
              </tr>
            ) : (
              paginated.map((row, i) => (
                <React.Fragment key={row.id || i}>
                  <tr className="hover:bg-[var(--glass-bg-hover)] transition-colors">
                    {columns.map((col) => (
                      <td key={col.key} className="px-4 py-3 text-sm text-foreground">
                        {col.render ? col.render(row[col.key], row) : (row[col.key] ?? '-')}
                      </td>
                    ))}
                  </tr>
                  {expandedRow && expandedRow(row) && (
                    <tr>
                      <td colSpan={columns.length} className="p-0 border-b border-[var(--glass-border)]">
                        {expandedRow(row)}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--glass-border)]">
          <span className="text-sm text-muted-foreground">
            {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filtered.length)} dari {filtered.length}
          </span>
          <div className="flex items-center gap-1">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="p-1 rounded disabled:opacity-40 hover:bg-[var(--glass-bg-hover)] transition-colors">
              <ChevronLeft className="w-4 h-4 text-foreground" />
            </button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const p = i + 1;
              return (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={`w-8 h-8 rounded text-sm transition-colors ${
                    page === p
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-[var(--glass-bg-hover)] text-muted-foreground'
                  }`}
                >
                  {p}
                </button>
              );
            })}
            <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="p-1 rounded disabled:opacity-40 hover:bg-[var(--glass-bg-hover)] transition-colors">
              <ChevronRight className="w-4 h-4 text-foreground" />
            </button>
          </div>
        </div>
      )}
    </GlassCard>
  );
}

/* ───────────────── Facade ───────────────── */

export default function DataTable(props) {
  // Decide which implementation to use
  const needsLegacy = !!props.expandedRow || !!props.onSearch;
  
  // Early return for legacy path (no hooks after this point)
  if (needsLegacy) {
    return <DataTableV1Native {...props} />;
  }

  // v2 delegation path - this is a separate component to avoid hooks violations
  return <DataTableV2Adapter {...props} />;
}

// Separate component for v2 delegation to avoid React Hooks violations
function DataTableV2Adapter(props) {
  const {
    columns,
    data,
    searchKeys = [],
    title,
    actions,
    exportData,
    tableId,
    selectable,
    bulkActions,
    rowActions,
    emptyTitle,
    emptyDescription,
    onRowClick,
    className,
    filters,
    initialSort,
    pageSizeOptions,
    pageSize,
    loading,
    error,
    showExport,
  } = props;

  const adaptedColumns = useMemo(() => _adaptColumnsV1ToV2(columns), [columns]);

  const exportFn = useMemo(() => {
    if (typeof exportData !== 'function') return undefined;
    return async () => exportData();
  }, [exportData]);

  const fallbackIdRef = useRef(null);
  if (!fallbackIdRef.current) {
    fallbackIdRef.current = `legacy-dt-${title || (columns && columns.length) || 'x'}-${Math.random().toString(36).slice(2, 8)}`;
  }
  const finalTableId =
    tableId ||
    `legacy-${(title || '').toLowerCase().replace(/\s+/g, '-') || fallbackIdRef.current}`;

  return (
    <DataTableV2
      tableId={finalTableId}
      columns={adaptedColumns}
      rows={Array.isArray(data) ? data : []}
      searchFields={Array.isArray(searchKeys) && searchKeys.length ? searchKeys : undefined}
      filters={filters}
      initialSort={initialSort}
      pageSizeOptions={pageSizeOptions}
      pageSize={pageSize || 10}
      selectable={selectable}
      bulkActions={bulkActions}
      rowActions={rowActions}
      exportFn={exportFn}
      showExport={showExport !== false}
      emptyTitle={emptyTitle || 'Tidak ada data'}
      emptyDescription={emptyDescription || 'Data akan muncul di sini saat tersedia.'}
      toolbar={actions}
      onRowClick={onRowClick}
      className={className}
      loading={loading}
      error={error}
    />
  );
}
