import { useState, useEffect } from 'react';
export function StatCard({ title, value, icon: Icon, color, sub, alert }) {
  return (
    <div className={`bg-card rounded-xl border p-5 shadow-sm ${alert ? 'border-red-300 bg-red-50/40' : 'border-border'}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className={`text-2xl font-bold mt-1 ${alert ? 'text-red-700' : 'text-foreground'}`}>{value}</p>
          {sub && <p className="text-xs text-muted-foreground/70 mt-1">{sub}</p>}
        </div>
        <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${color}`}>
          <Icon className="w-6 h-6 text-white" />
        </div>
      </div>
    </div>
  );
}

export function MiniBar({ pct }) {
  const color = pct >= 100 ? 'bg-emerald-500' : pct >= 60 ? 'bg-blue-500' : pct >= 30 ? 'bg-amber-500' : 'bg-red-400';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-muted rounded-full h-2">
        <div className={`h-2 rounded-full transition-all ${color}`} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <span className="text-xs font-bold text-foreground/90 w-9 text-right">{pct}%</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

