/**
 * KPICard — Compact gradient card with icon, value, label & optional sub-text.
 * Extracted from AssetManagementPortal.jsx (Phase 1 refactor)
 */
import { Card, CardContent } from '@/components/ui/card';

export function KPICard({ label, value, sub, icon: Icon, accent, testId }) {
  const accents = {
    blue: 'from-blue-500/10 to-blue-600/5 border-blue-300 dark:border-blue-500/20',
    emerald: 'from-emerald-500/10 to-emerald-600/5 border-emerald-300 dark:border-emerald-500/20',
    amber: 'from-amber-500/10 to-amber-600/5 border-amber-300 dark:border-amber-500/20',
    violet: 'from-violet-500/10 to-violet-600/5 border-violet-300 dark:border-violet-500/20',
  };
  const iconColors = {
    blue: 'text-blue-500',
    emerald: 'text-emerald-500',
    amber: 'text-amber-500',
    violet: 'text-violet-500',
  };
  return (
    <Card className={`bg-gradient-to-br ${accents[accent] || accents.blue} border`} data-testid={testId}>
      <CardContent className="pt-4 pb-3 px-4">
        <div className="flex items-start justify-between mb-1">
          <Icon size={18} className={iconColors[accent] || 'text-blue-500'} />
        </div>
        <div className="text-xl font-bold" data-testid={testId ? `${testId}-value` : undefined}>{value}</div>
        <div className="text-xs text-muted-foreground mt-0.5">{label}</div>
        {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
      </CardContent>
    </Card>
  );
}
