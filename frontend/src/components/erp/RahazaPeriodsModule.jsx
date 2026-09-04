import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, CalendarRange, Lock, LockOpen, ShieldCheck, AlertTriangle } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader } from './moduleAtoms';

const STATUS_COLORS = {
  open: 'text-emerald-300 bg-emerald-400/10 border-emerald-400/25',
  closed: 'text-amber-300 bg-amber-400/10 border-amber-400/25',
  locked: 'text-red-300 bg-red-400/10 border-red-400/25',
};

function StatusBadge({ status }) {
  const cls = STATUS_COLORS[status] || 'text-foreground/70 bg-foreground/5 border-foreground/10';
  return <span className={`text-[9px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded border ${cls}`}>{status}</span>;
}

export default function RahazaPeriodsModule({ token }) {
  const [periods, setPeriods] = useState([]);
  const [loading, setLoading] = useState(true);
  const [year, setYear] = useState(new Date().getFullYear());
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`/api/rahaza/periods?year=${year}`, { headers });
      if (r.ok) setPeriods(await r.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, year]);
  useEffect(() => { fetchData(); }, [fetchData]);

  const ensureYear = async () => {
    const r = await fetch('/api/rahaza/periods/ensure-year', { method: 'POST', headers, body: JSON.stringify({ year }) });
    if (r.ok) { fetchData(); } else { const e = await r.json(); alert(e.detail || 'Error'); }
  };

  const act = async (code, action) => {
    const verb = { close: 'tutup', reopen: 'buka kembali', lock: 'kunci final' }[action];
    if (!window.confirm(`${verb.charAt(0).toUpperCase() + verb.slice(1)} periode ${code}?`)) return;
    const r = await fetch(`/api/rahaza/periods/${code}/${action}`, { method: 'POST', headers });
    if (r.ok) { fetchData(); }
    else { const e = await r.json(); alert(e.detail || 'Error'); }
  };

  return (
    <div className="space-y-5" data-testid="rahaza-periods-page">
      <PageHeader
        icon={CalendarRange}
        eyebrow="Portal Finance · Accounting Core"
        title="Periode Akuntansi (Fiscal Periods)"
        subtitle="Kelola periode bulanan: Open (default), Closed (stop posting), Locked (final audit, irreversible). Periode closed/locked memblokir posting jurnal di tanggal tersebut."
        actions={
          <>
            <Button variant="ghost" onClick={fetchData} className="h-9 border border-[var(--glass-border)]" data-testid="pr-refresh"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang</Button>
            <Button onClick={ensureYear} className="h-9" data-testid="pr-ensure">Generate {year}</Button>
          </>
        }
      />

      <GlassCard className="p-4">
        <div className="flex items-center gap-3 mb-4">
          <span className="text-xs text-muted-foreground">Tahun:</span>
          <GlassInput type="number" value={year} onChange={e => setYear(Number(e.target.value) || year)} className="h-8 w-24" data-testid="pr-year" />
        </div>
        {loading ? (
          <div className="py-10 text-center text-muted-foreground">Memuat…</div>
        ) : periods.length === 0 ? (
          <div className="py-10 text-center space-y-3">
            <div className="text-muted-foreground">Tahun {year} belum di-generate.</div>
            <Button onClick={ensureYear} data-testid="pr-ensure-empty">Generate Periode {year}</Button>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {periods.map(p => (
              <GlassCard key={p.period_code} className="p-4" hover={false} data-testid={`pr-card-${p.period_code}`}>
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-xs font-mono text-muted-foreground">{p.period_code}</div>
                    <div className="font-semibold text-foreground">{p.period_label}</div>
                  </div>
                  <StatusBadge status={p.status} />
                </div>
                {p.closed_at && (
                  <div className="text-[10px] text-muted-foreground mt-2">
                    Closed: {new Date(p.closed_at).toLocaleDateString('id-ID')} · {p.closed_by_name || '-'}
                  </div>
                )}
                {p.locked_at && (
                  <div className="text-[10px] text-red-300 mt-1">
                    Locked: {new Date(p.locked_at).toLocaleDateString('id-ID')} · {p.locked_by_name || '-'}
                  </div>
                )}
                <div className="flex gap-1 mt-3 flex-wrap">
                  {p.status === 'open' && (
                    <Button variant="ghost" onClick={() => act(p.period_code, 'close')} className="h-7 text-[11px] border border-[var(--glass-border)]" data-testid={`pr-close-${p.period_code}`}>
                      <Lock className="w-3 h-3 mr-1" />Close
                    </Button>
                  )}
                  {p.status === 'closed' && (
                    <>
                      <Button variant="ghost" onClick={() => act(p.period_code, 'reopen')} className="h-7 text-[11px] border border-[var(--glass-border)]" data-testid={`pr-reopen-${p.period_code}`}>
                        <LockOpen className="w-3 h-3 mr-1" />Reopen
                      </Button>
                      <Button variant="ghost" onClick={() => act(p.period_code, 'lock')} className="h-7 text-[11px] border border-red-400/25 text-red-300" data-testid={`pr-lock-${p.period_code}`}>
                        <ShieldCheck className="w-3 h-3 mr-1" />Lock Final
                      </Button>
                    </>
                  )}
                  {p.status === 'locked' && (
                    <div className="text-[10px] text-red-300 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" />Terkunci permanen
                    </div>
                  )}
                </div>
              </GlassCard>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
