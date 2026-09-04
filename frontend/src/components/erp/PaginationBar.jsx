/**
 * PaginationBar — reusable pagination component
 * Digunakan di: Task Management, KOL Creators, KOL Requests, Catalog Items
 */
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';

export default function PaginationBar({ pagination, onPageChange, className = '' }) {
  if (!pagination || pagination.total_pages <= 1) return null;

  const { page, total_pages, total, limit } = pagination;
  const start = (page - 1) * limit + 1;
  const end = Math.min(page * limit, total);

  // Generate page numbers to show (max 5 around current)
  const getPageNumbers = () => {
    const pages = [];
    const delta = 2;
    const left = Math.max(2, page - delta);
    const right = Math.min(total_pages - 1, page + delta);

    pages.push(1);
    if (left > 2) pages.push('...');
    for (let i = left; i <= right; i++) pages.push(i);
    if (right < total_pages - 1) pages.push('...');
    if (total_pages > 1) pages.push(total_pages);

    return pages;
  };

  return (
    <div className={`flex items-center justify-between px-1 py-2 ${className}`}>
      {/* Info */}
      <span className="text-xs text-muted-foreground">
        Menampilkan <strong>{start}–{end}</strong> dari <strong>{total}</strong>
      </span>

      {/* Controls */}
      <div className="flex items-center gap-1">
        {/* First */}
        <button
          onClick={() => onPageChange(1)}
          disabled={page === 1}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          title="Halaman pertama"
        >
          <ChevronsLeft className="w-3.5 h-3.5" />
        </button>

        {/* Prev */}
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page === 1}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          title="Halaman sebelumnya"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>

        {/* Page numbers */}
        {getPageNumbers().map((p, i) =>
          p === '...' ? (
            <span key={`ellipsis-${i}`} className="w-8 h-8 flex items-center justify-center text-xs text-muted-foreground">…</span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p)}
              className={`w-8 h-8 rounded-lg text-xs font-medium transition-colors ${
                p === page
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              {p}
            </button>
          )
        )}

        {/* Next */}
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page === total_pages}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          title="Halaman berikutnya"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>

        {/* Last */}
        <button
          onClick={() => onPageChange(total_pages)}
          disabled={page === total_pages}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          title="Halaman terakhir"
        >
          <ChevronsRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
