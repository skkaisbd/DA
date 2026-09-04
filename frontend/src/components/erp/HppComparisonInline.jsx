import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { formatRupiah } from '@/lib/format';

/**
 * Component untuk display perbandingan HPP:
 * Estimasi | Aktual | Delta (+/-%) dengan color-coded
 */
export function HppComparisonInline({ estimated, actual, className = "" }) {
  const delta = actual - estimated;
  const deltaPct = estimated > 0 ? (delta / estimated) * 100 : 0;
  
  const isOverBudget = delta > 0;
  const isOnTarget = Math.abs(deltaPct) < 1;
  
  const deltaColor = isOnTarget 
    ? "text-sky-400 border-sky-500/20 bg-sky-500/10" 
    : isOverBudget 
      ? "text-rose-400 border-rose-500/20 bg-rose-500/10"
      : "text-emerald-400 border-emerald-500/20 bg-emerald-500/10";
  
  const DeltaIcon = isOnTarget ? Minus : isOverBudget ? TrendingUp : TrendingDown;
  
  const fmt = formatRupiah;
  
  return (
    <div className={`flex flex-wrap items-center gap-2 text-sm ${className}`}>
      <span className="text-muted-foreground" data-testid="hpp-comparison-estimated">
        Estimasi: <span className="font-mono">{fmt(estimated)}</span>
      </span>
      <span className="text-foreground/70">|</span>
      <span className="text-foreground" data-testid="hpp-comparison-actual">
        Aktual: <span className="font-mono font-semibold">{fmt(actual)}</span>
      </span>
      <span className="text-foreground/70">|</span>
      <span 
        className={`inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-xs ${deltaColor}`}
        data-testid="hpp-comparison-delta"
      >
        <DeltaIcon className="w-3 h-3 mr-1" />
        {deltaPct >= 0 ? '+' : ''}{deltaPct.toFixed(1)}%
      </span>
    </div>
  );
}