/**
 * PMAlertCard — Predictive Maintenance alert row.
 * Extracted from AssetManagementPortal.jsx (Phase 1 refactor)
 */
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  AlertTriangle, Clock, Activity, TrendingUp, Gauge, BellOff,
} from 'lucide-react';
import { SEVERITY_CONFIG } from '../constants';

// KIND_CONFIG references lucide icons so we keep it co-located with the component.
const KIND_CONFIG = {
  overdue:        { Icon: AlertTriangle, label: 'Overdue', color: 'text-red-500' },
  upcoming:       { Icon: Clock, label: 'Upcoming', color: 'text-amber-500' },
  stale:          { Icon: Activity, label: 'Stale', color: 'text-violet-500' },
  high_frequency: { Icon: TrendingUp, label: 'High Frequency', color: 'text-rose-500' },
  predicted:      { Icon: Gauge, label: 'Predicted', color: 'text-blue-500' },
};

export function PMAlertCard({ alert, onAcknowledge, ackBusy }) {
  const sevCfg = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.info;
  const kindCfg = KIND_CONFIG[alert.kind] || KIND_CONFIG.predicted;
  const KIcon = kindCfg.Icon;

  return (
    <div
      data-testid={`pm-alert-${alert.kind}-${alert.asset_id}`}
      className={`rounded-lg border ${sevCfg.border} ${sevCfg.bg} p-3.5`}
    >
      <div className="flex items-start gap-3">
        <div className={`shrink-0 w-9 h-9 rounded-lg bg-background/80 dark:bg-zinc-900/60 grid place-items-center ${kindCfg.color}`}>
          <KIcon size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5 flex-wrap">
            <span className="text-sm font-semibold">{alert.asset_name}</span>
            <span className="text-[10px] font-mono text-muted-foreground">{alert.asset_number}</span>
            <Badge variant="outline" className={`text-[10px] h-4 px-1 ${sevCfg.text}`}>
              {sevCfg.label}
            </Badge>
            <Badge variant="outline" className="text-[10px] h-4 px-1 capitalize">
              {kindCfg.label}
            </Badge>
          </div>
          <p className="text-xs text-foreground/70 leading-snug">{alert.recommended_action}</p>
          <div className="flex items-center gap-3 mt-2 text-[11px] text-muted-foreground flex-wrap">
            {alert.category_name && <span>📁 {alert.category_name}</span>}
            {alert.current_assignee && <span>👤 {alert.current_assignee}</span>}
            {alert.last_maintenance_date && <span>🛠️ Last: {alert.last_maintenance_date}</span>}
            {typeof alert.days_overdue === 'number' && (
              <span className="font-semibold text-red-600">⏰ {alert.days_overdue} hari telat</span>
            )}
            {typeof alert.days_until === 'number' && (
              <span className="font-semibold text-amber-600">⏳ {alert.days_until} hari lagi</span>
            )}
            {typeof alert.months_since_maintenance === 'number' && (
              <span className="font-semibold">📅 {alert.months_since_maintenance} bulan tanpa maintenance</span>
            )}
            {typeof alert.recent_count === 'number' && (
              <span className="font-semibold text-rose-600">
                🔄 {alert.recent_count}× dalam {alert.window_days} hari
              </span>
            )}
            {alert.predicted_next_due_date && (
              <span className="font-semibold text-blue-600">
                📊 Predicted: {alert.predicted_next_due_date}
              </span>
            )}
          </div>
        </div>
        <Button
          size="sm" variant="outline"
          onClick={() => onAcknowledge(alert)}
          disabled={ackBusy}
          data-testid={`pm-ack-${alert.kind}-${alert.asset_id}`}
          className="h-7 text-xs shrink-0"
        >
          <BellOff size={12} className="mr-1" /> Snooze
        </Button>
      </div>
    </div>
  );
}
