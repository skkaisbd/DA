
import { Factory, Handshake } from 'lucide-react';

/**
 * Identifier visual untuk membedakan data proses bisnis:
 * - Internal  : produksi milik sendiri (business_type != 'maklon' / legacy null)
 * - Maklon    : produksi jasa (CMT) untuk buyer eksternal (business_type == 'maklon')
 *
 * Dipakai di list yang menggabungkan data internal + maklon (mis. Shipment portal produksi).
 */
export function BizBadge({ type, size = 'sm', className = '' }) {
  const isMaklon = type === 'maklon';
  const Icon = isMaklon ? Handshake : Factory;
  const pad = size === 'xs' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-xs';
  const tone = isMaklon
    ? 'bg-purple-100 text-purple-700 border-purple-200'
    : 'bg-sky-100 text-sky-700 border-sky-200';
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border font-semibold ${pad} ${tone} ${className}`}
      data-testid={`biz-badge-${isMaklon ? 'maklon' : 'internal'}`}
      title={isMaklon ? 'Produksi Maklon (CMT)' : 'Produksi Internal'}
    >
      <Icon className="w-3 h-3" />
      {isMaklon ? 'Maklon' : 'Internal'}
    </span>
  );
}

/**
 * Segmented filter Semua / Internal / Maklon (client-side).
 * value: 'all' | 'internal' | 'maklon'
 */
export function BizFilter({ value = 'all', onChange, counts = null, className = '' }) {
  const opts = [
    { v: 'all', l: 'Semua' },
    { v: 'internal', l: 'Internal' },
    { v: 'maklon', l: 'Maklon' },
  ];
  return (
    <div
      className={`inline-flex items-center rounded-lg border border-border bg-muted/40 p-0.5 ${className}`}
      data-testid="biz-filter"
      role="tablist"
      aria-label="Filter proses bisnis"
    >
      {opts.map(o => {
        const active = value === o.v;
        const count = counts ? counts[o.v] : null;
        return (
          <button
            key={o.v}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.v)}
            data-testid={`biz-filter-${o.v}`}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400
              ${active ? 'bg-card text-blue-700 shadow-sm' : 'text-muted-foreground hover:text-foreground/90'}`}
          >
            {o.l}
            {count != null && (
              <span className={`ml-1.5 px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${active ? 'bg-blue-100 text-blue-700' : 'bg-muted text-muted-foreground'}`}>
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Helper cocokkan business_type sebuah row terhadap nilai filter. */
export function matchBiz(rowType, filter) {
  if (filter === 'all') return true;
  if (filter === 'maklon') return rowType === 'maklon';
  return rowType !== 'maklon'; // internal + legacy/null
}
