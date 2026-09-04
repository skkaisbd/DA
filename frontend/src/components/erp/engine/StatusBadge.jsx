const statusColors = {
  // General
  active: 'bg-emerald-100 text-emerald-700',
  inactive: 'bg-muted text-muted-foreground',
  // PO Status
  Draft: 'bg-muted text-foreground/90',
  Confirmed: 'bg-indigo-100 text-indigo-700',
  Distributed: 'bg-blue-100 text-blue-700',
  'In Production': 'bg-amber-100 text-amber-700',
  'Production Complete': 'bg-teal-100 text-teal-700',
  'Ready to Close': 'bg-violet-100 text-violet-700',
  Completed: 'bg-emerald-100 text-emerald-700',
  'Closed Short': 'bg-orange-100 text-orange-700',
  Closed: 'bg-muted text-muted-foreground',
  // Work Order Status
  Waiting: 'bg-muted text-muted-foreground',
  'In Progress': 'bg-blue-100 text-blue-700',
  // Invoice Status
  Unpaid: 'bg-red-100 text-red-700',
  Partial: 'bg-amber-100 text-amber-700',
  Paid: 'bg-emerald-100 text-emerald-700',
};

export default function StatusBadge({ status }) {
  const color = statusColors[status] || 'bg-muted text-foreground/90';
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}
