/**
 * PaginationBar - Reusable pagination component
 * 
 * Usage:
 *   <PaginationBar
 *     total={data.total}
 *     skip={skip}
 *     limit={limit}
 *     onPageChange={(newSkip) => setSkip(newSkip)}
 *   />
 */
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function PaginationBar({ total = 0, skip = 0, limit = 20, onPageChange, className = '' }) {
  if (total <= limit) return null;

  const currentPage = Math.floor(skip / limit) + 1;
  const totalPages = Math.ceil(total / limit);
  const from = skip + 1;
  const to = Math.min(skip + limit, total);

  const goTo = (page) => {
    const newSkip = (page - 1) * limit;
    onPageChange(newSkip);
  };

  // Generate page numbers to show (max 5 around current)
  const pages = [];
  const delta = 2;
  for (let i = Math.max(1, currentPage - delta); i <= Math.min(totalPages, currentPage + delta); i++) {
    pages.push(i);
  }
  if (pages[0] > 2) pages.unshift('...');
  if (pages[0] > 1) pages.unshift(1);
  if (pages[pages.length - 1] < totalPages - 1) pages.push('...');
  if (pages[pages.length - 1] < totalPages) pages.push(totalPages);

  return (
    <div className={`flex items-center justify-between text-sm ${className}`}>
      <span className="text-muted-foreground text-xs">
        {from}–{to} dari <strong>{total}</strong> data
      </span>
      <div className="flex items-center gap-1">
        <Button
          variant="outline" size="icon" className="h-7 w-7"
          disabled={currentPage === 1}
          onClick={() => goTo(currentPage - 1)}
          data-testid="pagination-prev"
        >
          <ChevronLeft className="w-4 h-4" />
        </Button>

        {pages.map((p, i) =>
          p === '...' ? (
            <span key={`ellipsis-${i}`} className="px-1 text-muted-foreground">…</span>
          ) : (
            <button
              key={p}
              onClick={() => goTo(p)}
              data-testid={`pagination-page-${p}`}
              className={`w-7 h-7 rounded text-xs font-medium transition-colors
                ${p === currentPage
                  ? 'bg-primary text-primary-foreground'
                  : 'hover:bg-muted text-foreground'}`}
            >
              {p}
            </button>
          )
        )}

        <Button
          variant="outline" size="icon" className="h-7 w-7"
          disabled={currentPage === totalPages}
          onClick={() => goTo(currentPage + 1)}
          data-testid="pagination-next"
        >
          <ChevronRight className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}
