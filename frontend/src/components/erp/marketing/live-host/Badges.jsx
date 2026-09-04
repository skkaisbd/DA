/**
 * Shared status badges for LiveHost Management module.
 */

import { Badge } from '@/components/ui/badge';
import { CheckCircle, XCircle, AlertCircle, Calendar as CalendarIcon } from 'lucide-react';

export const StatusBadge = ({ status }) => {
  const config = {
    active: { label: 'Active', color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300' },
    inactive: { label: 'Inactive', color: 'bg-muted text-foreground dark:bg-slate-800 dark:text-foreground/70' },
    on_leave: { label: 'On Leave', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' },
  };
  const cfg = config[status] || config.inactive;
  return <Badge className={`text-xs ${cfg.color}`}>{cfg.label}</Badge>;
};

export const AttendanceBadge = ({ status }) => {
  const config = {
    scheduled: { label: 'Scheduled', color: 'bg-blue-100 text-blue-700', icon: CalendarIcon },
    on_time: { label: 'On Time', color: 'bg-emerald-100 text-emerald-700', icon: CheckCircle },
    late: { label: 'Late', color: 'bg-amber-100 text-amber-700', icon: AlertCircle },
    no_show: { label: 'No Show', color: 'bg-red-100 text-red-700', icon: XCircle },
    completed: { label: 'Completed', color: 'bg-violet-100 text-violet-700', icon: CheckCircle },
  };
  const cfg = config[status] || config.scheduled;
  const Icon = cfg.icon;
  return (
    <Badge className={`text-xs ${cfg.color} flex items-center gap-1`}>
      <Icon size={10} />
      {cfg.label}
    </Badge>
  );
};

export const EmploymentTypeBadge = ({ type }) => {
  const config = {
    full_time: { label: 'Full Time', color: 'bg-blue-100 text-blue-700' },
    part_time: { label: 'Part Time', color: 'bg-violet-100 text-violet-700' },
    freelance: { label: 'Freelance', color: 'bg-pink-100 text-pink-700' },
    contract: { label: 'Contract', color: 'bg-amber-100 text-amber-700' },
  };
  const cfg = config[type] || config.part_time;
  return <Badge className={`text-xs ${cfg.color}`}>{cfg.label}</Badge>;
};
