const statusColors = {
  // General
  active: 'bg-emerald-400/15 text-emerald-300 dark:text-emerald-300 border border-emerald-300/20',
  inactive: 'bg-secondary text-muted-foreground border border-border',
  // PO Status
  Draft: 'bg-secondary text-muted-foreground border border-border',
  Confirmed: 'bg-sky-400/15 text-sky-400 border border-sky-300/20',
  Distributed: 'bg-blue-400/15 text-blue-400 border border-blue-300/20',
  'In Production': 'bg-amber-400/15 text-amber-400 border border-amber-300/20',
  'Production Complete': 'bg-teal-400/15 text-teal-400 border border-teal-300/20',
  Completed: 'bg-emerald-400/15 text-emerald-300 border border-emerald-300/20',
  Closed: 'bg-secondary text-muted-foreground border border-border',
  // Work Order Status
  Waiting: 'bg-secondary text-muted-foreground border border-border',
  'In Progress': 'bg-sky-400/15 text-sky-400 border border-sky-300/20',
  // Invoice Status
  Unpaid: 'bg-red-400/15 text-red-400 border border-red-300/20',
  Partial: 'bg-amber-400/15 text-amber-400 border border-amber-300/20',
  Paid: 'bg-emerald-400/15 text-emerald-300 border border-emerald-300/20',
  // Variance
  'Variance Review': 'bg-purple-400/15 text-purple-400 border border-purple-300/20',
  'Return Review': 'bg-orange-400/15 text-orange-400 border border-orange-300/20',
  'Ready to Close': 'bg-teal-400/15 text-teal-400 border border-teal-300/20',
};

export default function StatusBadge({ status }) {
  const color = statusColors[status] || 'bg-secondary text-muted-foreground border border-border';
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}
