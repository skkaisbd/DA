/**
 * OnwardCTA — RC-FLOW-UX-CORE atom.
 *
 * A consistent "next step" bar that turns a result/detail view into the start of the
 * next flow. Uses the app-wide `onNavigate(moduleId, params)` prop (passed to every
 * module by App.js and forwarded through hubs), so a single click can jump — even
 * across portals (Marketing→Gudang, SDM→Keuangan, …).
 *
 * Usage:
 *   <OnwardCTA
 *     onNavigate={onNavigate}
 *     title="Lanjutkan Alur"
 *     actions={[
 *       { module: 'wh-receiving', label: 'Buat Penerimaan (GRN)', icon: PackageCheck, primary: true },
 *       { module: 'fin-ap-invoices', label: 'Catat Tagihan (AP)', hint: 'Butuh akses Keuangan' },
 *     ]}
 *   />
 *
 * Each action: { module, label, params?, icon?, primary?, hint?, testId? }.
 * Renders nothing when onNavigate is missing or no valid actions are provided.
 */
import React from 'react';
import { ArrowRight, Route } from 'lucide-react';
import { cn } from '@/lib/utils';

export function OnwardCTA({
  onNavigate,
  actions = [],
  title = 'Langkah Berikutnya',
  className,
  testId = 'onward-cta',
}) {
  const list = (actions || []).filter((a) => a && a.module && a.label);
  if (typeof onNavigate !== 'function' || list.length === 0) return null;

  return (
    <div
      data-testid={testId}
      className={cn(
        'relative rounded-[var(--radius-lg)] border px-4 py-3',
        'bg-[var(--card-surface)] border-[var(--glass-border)] backdrop-blur-[var(--glass-blur)]',
        'flex items-center justify-between gap-3 flex-wrap',
        className
      )}
    >
      <div className="flex items-center gap-2 min-w-0">
        <div className="grid place-items-center w-7 h-7 rounded-[9px] bg-[hsl(var(--primary)/0.12)] border border-[hsl(var(--primary)/0.22)] shrink-0">
          <Route className="w-3.5 h-3.5 text-[hsl(var(--primary))]" strokeWidth={2} />
        </div>
        <span className="text-[10px] uppercase tracking-[0.16em] text-foreground/50 font-semibold">
          {title}
        </span>
      </div>

      <div className="flex items-center gap-2 flex-wrap justify-end">
        {list.map((a, i) => {
          const Icon = a.icon;
          return (
            <button
              key={`${a.module}-${i}`}
              type="button"
              data-testid={a.testId || `onward-${a.module}`}
              title={a.hint || a.label}
              onClick={() => onNavigate(a.module, a.params || {})}
              className={cn(
                'group inline-flex items-center gap-2 rounded-[12px] px-3.5 py-2 text-sm font-medium transition-all',
                a.primary
                  ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:brightness-110 shadow-[var(--shadow-card)]'
                  : 'bg-[hsl(var(--primary)/0.10)] text-[hsl(var(--primary))] border border-[hsl(var(--primary)/0.22)] hover:bg-[hsl(var(--primary)/0.18)]'
              )}
            >
              {Icon ? <Icon className="w-4 h-4 shrink-0" strokeWidth={2} /> : null}
              <span className="truncate max-w-[220px]">{a.label}</span>
              <ArrowRight className="w-4 h-4 shrink-0 transition-transform group-hover:translate-x-0.5" />
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default OnwardCTA;
