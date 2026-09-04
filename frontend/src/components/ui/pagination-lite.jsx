import React from 'react';

/**
 * PaginationLite — RC-UI-03 single-source pagination control (theme-tokenized).
 * Props:
 *   - page: current page (1-based)
 *   - totalPages: total number of pages
 *   - total: total number of rows (for the "Menampilkan a–b dari N" label)
 *   - pageSize: rows per page (default 10) — used for the range label
 *   - onPageChange(nextPage)
 *   - className: optional extra classes
 * Standard: default 10 rows/page. Use with client-side slice or server limit/skip.
 */
export default function PaginationLite({
  page = 1,
  totalPages = 1,
  total = 0,
  pageSize = 10,
  onPageChange,
  className = '',
}) {
  const safeTotalPages = Math.max(1, totalPages || 1);
  const current = Math.min(Math.max(1, page), safeTotalPages);
  const from = total === 0 ? 0 : (current - 1) * pageSize + 1;
  const to = Math.min(current * pageSize, total);

  const go = (p) => {
    const next = Math.min(Math.max(1, p), safeTotalPages);
    if (next !== current && typeof onPageChange === 'function') onPageChange(next);
  };

  // Hide entirely if a single page with no rows worth paginating
  if (safeTotalPages <= 1 && total <= pageSize) {
    return total > 0 ? (
      <div className={`flex items-center justify-between gap-3 px-1 py-2 text-xs text-muted-foreground ${className}`} data-testid="pagination-lite">
        <span data-testid="pagination-info">Menampilkan {from}–{to} dari {total}</span>
      </div>
    ) : null;
  }

  return (
    <div
      className={`flex flex-col sm:flex-row items-center justify-between gap-3 px-1 py-2 border-t border-border ${className}`}
      data-testid="pagination-lite"
    >
      <span className="text-xs text-muted-foreground" data-testid="pagination-info">
        Menampilkan {from}–{to} dari {total}
      </span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          data-testid="pagination-prev"
          onClick={() => go(current - 1)}
          disabled={current <= 1}
          className="h-8 px-3 rounded-md border border-border bg-card text-foreground text-xs font-medium hover:bg-muted/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          ‹ Prev
        </button>
        <span className="h-8 px-3 inline-flex items-center rounded-md bg-muted text-foreground text-xs font-medium" data-testid="pagination-page">
          Halaman {current} / {safeTotalPages}
        </span>
        <button
          type="button"
          data-testid="pagination-next"
          onClick={() => go(current + 1)}
          disabled={current >= safeTotalPages}
          className="h-8 px-3 rounded-md border border-border bg-card text-foreground text-xs font-medium hover:bg-muted/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Next ›
        </button>
      </div>
    </div>
  );
}

/** Helper hook for client-side pagination. */
export function useClientPagination(rows, pageSize = 10) {
  const [page, setPage] = React.useState(1);
  const list = Array.isArray(rows) ? rows : [];
  const totalPages = Math.max(1, Math.ceil(list.length / pageSize));
  React.useEffect(() => {
    // reset to page 1 whenever the underlying data length changes (filter/search)
    setPage(1);
  }, [list.length]);
  const safePage = Math.min(page, totalPages);
  const paged = list.slice((safePage - 1) * pageSize, safePage * pageSize);
  return { page: safePage, setPage, totalPages, total: list.length, paged, pageSize };
}
