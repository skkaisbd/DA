import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * PaginationFooter
 *
 * Reusable pagination control for screens that don't use DataTable but still
 * need server-side paging UX (Activity Logs, Payments, etc.).
 *
 * Props:
 *   page         : current 1-based page number
 *   perPage      : items per page
 *   total        : total item count from backend envelope
 *   onPageChange : (newPage) => void
 *   onPerPageChange : (newPerPage) => void  (optional; when omitted, selector hidden)
 *   perPageOptions  : array of allowed page sizes (default [10, 20, 50, 100])
 *   loading      : when true, disables next/prev buttons
 *   itemLabel    : human label e.g. "transaksi" / "log"
 *   testIdPrefix : optional prefix for data-testid (default 'pagination')
 */
export default function PaginationFooter({
  page,
  perPage,
  total,
  onPageChange,
  onPerPageChange,
  perPageOptions = [10, 20, 50, 100],
  loading = false,
  itemLabel = 'item',
  testIdPrefix = 'pagination',
}) {
  const totalPages = Math.max(1, Math.ceil((total || 0) / Math.max(1, perPage || 1)));
  const start = total === 0 ? 0 : (page - 1) * perPage + 1;
  const end = Math.min(page * perPage, total || 0);

  // Build a compact set of page numbers around the current page
  const pageNumbers = (() => {
    const window = 5;
    let from = Math.max(1, page - Math.floor(window / 2));
    let to = Math.min(totalPages, from + window - 1);
    from = Math.max(1, to - window + 1);
    const arr = [];
    for (let i = from; i <= to; i++) arr.push(i);
    return arr;
  })();

  const disabled = loading || total === 0;

  return (
    <div
      className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 px-4 py-3 border-t border-border/60 bg-card"
      data-testid={`${testIdPrefix}-footer`}
    >
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <span data-testid={`${testIdPrefix}-range`}>
          {total === 0
            ? `Tidak ada ${itemLabel}`
            : `${start.toLocaleString('id-ID')}–${end.toLocaleString('id-ID')} dari ${(total || 0).toLocaleString('id-ID')} ${itemLabel}`}
        </span>
        {onPerPageChange && (
          <label className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground/70">Per halaman:</span>
            <select
              value={perPage}
              onChange={(e) => onPerPageChange(Number(e.target.value))}
              className="border border-border rounded px-1.5 py-0.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={loading}
              data-testid={`${testIdPrefix}-per-page`}
            >
              {perPageOptions.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={disabled || page <= 1}
          className="p-1 rounded disabled:opacity-40 disabled:cursor-not-allowed hover:bg-muted transition-colors"
          aria-label="Halaman sebelumnya"
          data-testid={`${testIdPrefix}-prev`}
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        {pageNumbers[0] > 1 && (
          <>
            <button
              onClick={() => onPageChange(1)}
              disabled={loading}
              className="w-8 h-8 rounded text-sm hover:bg-muted text-muted-foreground"
              data-testid={`${testIdPrefix}-page-1`}
            >
              1
            </button>
            {pageNumbers[0] > 2 && <span className="px-1 text-muted-foreground/70 text-xs">…</span>}
          </>
        )}
        {pageNumbers.map((p) => (
          <button
            key={p}
            onClick={() => onPageChange(p)}
            disabled={loading}
            aria-current={page === p ? 'page' : undefined}
            className={`w-8 h-8 rounded text-sm transition-colors ${
              page === p
                ? 'bg-blue-600 text-white shadow-sm'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            data-testid={`${testIdPrefix}-page-${p}`}
          >
            {p}
          </button>
        ))}
        {pageNumbers[pageNumbers.length - 1] < totalPages && (
          <>
            {pageNumbers[pageNumbers.length - 1] < totalPages - 1 && (
              <span className="px-1 text-muted-foreground/70 text-xs">…</span>
            )}
            <button
              onClick={() => onPageChange(totalPages)}
              disabled={loading}
              className="w-8 h-8 rounded text-sm hover:bg-muted text-muted-foreground"
              data-testid={`${testIdPrefix}-page-last`}
            >
              {totalPages}
            </button>
          </>
        )}
        <button
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          disabled={disabled || page >= totalPages}
          className="p-1 rounded disabled:opacity-40 disabled:cursor-not-allowed hover:bg-muted transition-colors"
          aria-label="Halaman berikutnya"
          data-testid={`${testIdPrefix}-next`}
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
