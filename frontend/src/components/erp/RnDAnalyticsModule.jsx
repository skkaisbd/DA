import { useState, useEffect } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Activity, RefreshCw, Palette, FlaskConical, Layers, Calculator, Ruler } from 'lucide-react';
import { toast } from '../ui/sonner';

const API = process.env.REACT_APP_BACKEND_URL || '';

const StatRow = ({ label, value, sub, highlight = false }) => (
  <div className={`flex items-center justify-between py-2.5 border-b border-foreground/5 last:border-0 ${highlight ? 'text-violet-600 dark:text-violet-400' : ''}`}>
    <span className={`text-sm ${highlight ? 'font-semibold text-foreground' : 'text-foreground/70'}`}>{label}</span>
    <div className="text-right">
      <div className={`text-sm font-semibold ${highlight ? 'text-violet-600 dark:text-violet-400' : 'text-foreground'}`}>{value}</div>
      {sub && <div className="text-xs text-foreground/40">{sub}</div>}
    </div>
  </div>
);

export default function RnDAnalyticsModule({ token }) {
  const h = { Authorization: `Bearer ${token}` };
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/dewi/rnd/analytics`, { headers: h });
      if (!res.ok) throw new Error();
      setData(await res.json());
    } catch { toast.error('Gagal memuat analytics'); }
    finally { setLoading(false); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  if (loading) return (
    <div className="flex justify-center h-48 items-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-violet-500" />
    </div>
  );

  return (
    <div className="p-6" data-testid="rnd-analytics-module">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Activity className="w-5 h-5 text-violet-500" /> RnD Analytics
          </h1>
          <p className="text-sm text-foreground/50 mt-0.5">Statistik & ringkasan aktivitas Research & Development</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} className="gap-2">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </Button>
      </div>

      {!data ? (
        <p className="text-foreground/50 text-sm">Tidak ada data.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <GlassCard className="p-5">
            <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
              <Palette className="w-4 h-4 text-violet-500" /> Style Master
            </h3>
            <StatRow label="Total Style"   value={data.styles?.total}  />
            <StatRow label="Style Aktif"   value={data.styles?.active} highlight />
          </GlassCard>

          <GlassCard className="p-5">
            <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
              <FlaskConical className="w-4 h-4 text-violet-500" /> Sample Requests
            </h3>
            <StatRow label="Total Sample"    value={data.sample_requests?.total}    />
            <StatRow label="Menunggu Approve" value={data.sample_requests?.pending}  highlight />
            <StatRow label="Disetujui"        value={data.sample_requests?.approved} />
          </GlassCard>

          <GlassCard className="p-5">
            <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
              <Layers className="w-4 h-4 text-violet-500" /> Material Research
            </h3>
            <StatRow label="Total Material"   value={data.materials?.total}  />
            <StatRow label="Material Aktif"   value={data.materials?.active} highlight />
          </GlassCard>

          <GlassCard className="p-5">
            <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
              <Calculator className="w-4 h-4 text-violet-500" /> Costing & Revisi
            </h3>
            <StatRow label="Total Revisi" value={data.revisions?.total} />
          </GlassCard>
        </div>
      )}
    </div>
  );
}
