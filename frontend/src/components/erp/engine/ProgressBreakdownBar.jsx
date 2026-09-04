/**
 * ProgressBreakdownBar — visualisasi qty-progress multi-state (canonical).
 * Dipakai di Tracking, PO-360, dan konteks Permak.
 *
 * Props:
 *   breakdown: object dari services/maklon_progress (qty_ordered, qty_dispatched,
 *              qty_good_ready, qty_rework_open, qty_scrap, qty_reject_qc, ...)
 *   compact:   boolean — sembunyikan legend numerik (untuk baris list)
 */
function fmt(n) {
  return Number(n || 0).toLocaleString('id-ID');
}

const SEGMENTS = [
  { key: 'qty_dispatched', label: 'Terkirim ke Buyer', cls: 'bg-blue-500', dot: 'bg-blue-500' },
  { key: 'qty_good_ready', label: 'Barang Jadi (siap)', cls: 'bg-emerald-500', dot: 'bg-emerald-500' },
  { key: 'qty_rework_open', label: 'Sedang Permak', cls: 'bg-amber-500', dot: 'bg-amber-500' },
  { key: 'qty_scrap', label: 'Scrap / Buang', cls: 'bg-zinc-500', dot: 'bg-zinc-500' },
];

export default function ProgressBreakdownBar({ breakdown, compact = false }) {
  const b = breakdown || {};
  const ordered = Number(b.qty_ordered || 0);

  const dispatched = Number(b.qty_dispatched || 0);
  const goodReady = Number(b.qty_good_ready || 0);
  const reworkOpen = Number(b.qty_rework_open || 0);
  const scrap = Number(b.qty_scrap || 0);
  const accounted = dispatched + goodReady + reworkOpen + scrap;
  const remaining = Math.max(0, ordered - accounted);

  const pct = (v) => (ordered > 0 ? (Number(v || 0) / ordered) * 100 : 0);

  return (
    <div className="w-full" data-testid="progress-breakdown-bar">
      {/* Segmented bar */}
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted">
        {SEGMENTS.map((s) => {
          const w = pct(b[s.key]);
          if (w <= 0) return null;
          return (
            <div
              key={s.key}
              className={s.cls}
              style={{ width: `${w}%` }}
              title={`${s.label}: ${fmt(b[s.key])} pcs`}
            />
          );
        })}
        {remaining > 0 && (
          <div
            className="bg-muted-foreground/15"
            style={{ width: `${pct(remaining)}%` }}
            title={`Belum jadi / dalam proses: ${fmt(remaining)} pcs`}
          />
        )}
      </div>

      {!compact && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Ordered: {fmt(ordered)}</span>
          {SEGMENTS.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1">
              <span className={`inline-block h-2 w-2 rounded-full ${s.dot}`} />
              {s.label}: <span className="font-medium text-foreground">{fmt(b[s.key])}</span>
            </span>
          ))}
          {remaining > 0 && (
            <span className="inline-flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/30" />
              Dalam proses: <span className="font-medium text-foreground">{fmt(remaining)}</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}
