/**
 * AI Insights Module (Phase 8) — Production & QC Root-Cause Analysis.
 *
 * Dua kartu utama:
 *   1. Production RCA — analisis pola bottleneck / delay / underperforming line.
 *   2. QC RCA         — analisis pola kegagalan QC, top defect, worst line/model.
 *
 * Flow:
 *   - Input: filter periode (7/14/30/60/90 hari) + opsional line/model.
 *   - Button "Generate Analysis" memanggil backend, menampilkan loading state,
 *     kemudian render kartu analisa: hipotesis, confidence, reasoning, action items.
 *   - History 5 analisa terakhir per user.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Brain, Factory, Shield, Sparkles, AlertCircle, Check, TrendingUp, TrendingDown,
  RefreshCw, History, Info, Target,
} from 'lucide-react';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

const PERIOD_OPTIONS = [
  { v: 7, label: '7 hari' },
  { v: 14, label: '14 hari' },
  { v: 30, label: '30 hari' },
  { v: 60, label: '60 hari' },
  { v: 90, label: '90 hari' },
];

function Badge({ cls, children }) {
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border ${cls}`}>{children}</span>;
}

function ConfidenceBadge({ level }) {
  const cls = level === 'tinggi' ? 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-500 border-emerald-400 dark:border-emerald-500/30'
            : level === 'sedang' ? 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-500 border-amber-400 dark:border-amber-500/30'
            : 'bg-muted dark:bg-zinc-500/15 text-muted-foreground dark:text-zinc-500 border-border dark:border-zinc-500/30';
  return <Badge cls={cls}>confidence: {level}</Badge>;
}

function RiskBadge({ level }) {
  const cls = level === 'tinggi' ? 'bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-500 border-red-400 dark:border-red-500/30'
            : level === 'sedang' ? 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-500 border-amber-400 dark:border-amber-500/30'
            : 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-500 border-emerald-400 dark:border-emerald-500/30';
  return <Badge cls={cls}>risk: {level}</Badge>;
}

function AnalysisResult({ result, type }) {
  if (!result) return null;
  const a = result.analysis || {};
  const s = result.stats || {};
  return (
    <div className="space-y-4" data-testid={`rca-result-${type}`}>
      {/* Stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        {type === 'production' && (
          <>
            <div className="bg-[var(--card-surface)] border border-border rounded-lg p-2">
              <div className="text-foreground/55">WIP Events</div>
              <div className="font-bold text-foreground">{s.total_wip_events || 0}</div>
            </div>
            <div className="bg-[var(--card-surface)] border border-border rounded-lg p-2">
              <div className="text-foreground/55">Process Dianalisis</div>
              <div className="font-bold text-foreground">{s.processes_analyzed || 0}</div>
            </div>
            <div className="bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-300 dark:border-emerald-500/20 rounded-lg p-2">
              <div className="text-foreground/55">WO On-Time</div>
              <div className="font-bold text-emerald-500">{s.wo_on_time || 0}</div>
            </div>
            <div className="bg-red-100 dark:bg-red-500/10 border border-red-300 dark:border-red-500/20 rounded-lg p-2">
              <div className="text-foreground/55">WO Overdue</div>
              <div className="font-bold text-red-700 dark:text-red-500">{s.wo_overdue || 0}</div>
            </div>
          </>
        )}
        {type === 'qc' && (
          <>
            <div className="bg-[var(--card-surface)] border border-border rounded-lg p-2">
              <div className="text-foreground/55">Total Checked</div>
              <div className="font-bold text-foreground">{s.total_checked || 0}</div>
            </div>
            <div className="bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-300 dark:border-emerald-500/20 rounded-lg p-2">
              <div className="text-foreground/55">Pass</div>
              <div className="font-bold text-emerald-500">{s.total_pass || 0}</div>
            </div>
            <div className="bg-red-100 dark:bg-red-500/10 border border-red-300 dark:border-red-500/20 rounded-lg p-2">
              <div className="text-foreground/55">Fail</div>
              <div className="font-bold text-red-700 dark:text-red-500">{s.total_fail || 0}</div>
            </div>
            <div className={`border rounded-lg p-2 ${(s.fail_rate_pct || 0) >= 10 ? 'bg-red-100 dark:bg-red-500/10 border-red-400 dark:border-red-500/30' : 'bg-amber-100 dark:bg-amber-500/10 border-amber-300 dark:border-amber-500/20'}`}>
              <div className="text-foreground/55">Fail Rate</div>
              <div className={`font-bold ${(s.fail_rate_pct || 0) >= 10 ? 'text-red-700 dark:text-red-500' : 'text-amber-700 dark:text-amber-500'}`}>{s.fail_rate_pct || 0}%</div>
            </div>
          </>
        )}
      </div>

      {/* Key finding cards */}
      {type === 'production' && s.top_bottleneck_process && (
        <div className="bg-amber-100 dark:bg-amber-500/10 border border-amber-400 dark:border-amber-500/30 rounded-xl p-3 flex items-center gap-3">
          <TrendingDown size={20} className="text-amber-700 dark:text-amber-500 flex-shrink-0" />
          <div>
            <div className="text-xs text-foreground/60">Bottleneck Process Teratas</div>
            <div className="font-bold text-foreground">{s.top_bottleneck_process.process}</div>
            <div className="text-xs text-foreground/55">Gap {s.top_bottleneck_process.discrepancy} pcs (Input {s.top_bottleneck_process.input} vs Output {s.top_bottleneck_process.output})</div>
          </div>
        </div>
      )}

      {type === 'qc' && s.worst_line && (
        <div className="bg-red-100 dark:bg-red-500/10 border border-red-400 dark:border-red-500/30 rounded-xl p-3 flex items-center gap-3">
          <AlertCircle size={20} className="text-red-700 dark:text-red-500 flex-shrink-0" />
          <div>
            <div className="text-xs text-foreground/60">Line dengan Fail Rate Tertinggi</div>
            <div className="font-bold text-foreground">{s.worst_line.line}</div>
            <div className="text-xs text-foreground/55">Fail rate {s.worst_line.fail_rate}% ({s.worst_line.fail}/{s.worst_line.checked} pcs)</div>
          </div>
        </div>
      )}

      {/* Claude analysis card */}
      <div className="bg-gradient-to-br from-violet-500/10 to-fuchsia-500/10 border border-violet-300 dark:border-violet-500/20 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <span className="text-[10px] font-bold uppercase tracking-wider text-violet-500">Root Cause Hypothesis</span>
          <ConfidenceBadge level={a.confidence} />
          <RiskBadge level={a.risk_level} />
        </div>
        <div className="text-base font-semibold text-foreground mb-2 capitalize">
          {a.root_cause_hypothesis || '-'}
        </div>
        <p className="text-xs text-foreground/70 leading-relaxed mb-3">{a.reasoning}</p>
        {(type === 'production' && a.bottleneck_process) && (
          <div className="text-xs text-foreground/60 mb-1">
            <Target size={10} className="inline mr-1 text-amber-700 dark:text-amber-500" /> Bottleneck: <span className="font-mono font-bold">{a.bottleneck_process}</span>
            {a.weakest_line && <> · Line terlemah: <span className="font-mono">{a.weakest_line}</span></>}
          </div>
        )}
        {(type === 'qc' && a.primary_defect_pattern) && (
          <div className="text-xs text-foreground/60 mb-1">
            <Info size={10} className="inline mr-1 text-violet-500" /> Pola defect utama: {a.primary_defect_pattern}
          </div>
        )}
      </div>

      {/* Action items */}
      <div>
        <div className="text-[10px] font-bold uppercase tracking-wider text-foreground/70 mb-2">
          <Check size={11} className="inline mr-1 text-emerald-500" /> Rekomendasi Action
        </div>
        <ol className="space-y-1.5 text-xs">
          {(a.recommended_actions || []).map((act, i) => (
            <li key={i} className="flex gap-2 bg-[var(--card-surface)] border border-border rounded-lg p-2.5">
              <span className="font-mono font-bold text-violet-500 flex-shrink-0">{i + 1}.</span>
              <span className="text-foreground/90">{act}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="text-[10px] text-foreground/40 text-right">
        Generated {new Date(result.generated_at).toLocaleString('id-ID')} · Claude Sonnet 4.5
      </div>
    </div>
  );
}

function RCASection({ token, type, title, icon: Icon, description }) {
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const run = async () => {
    setLoading(true); setError(''); setResult(null);
    try {
      const r = await fetch(`${API}/api/analytics/ai/${type === 'production' ? 'production' : 'qc'}/rca`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ days }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `Gagal RCA ${type}`);
      setResult(d);
      toast.success(`Analisis ${title} selesai`);
    } catch (e) {
      setError(e.message);
      toast.error(e.message);
    } finally { setLoading(false); }
  };

  return (
    <div className="bg-[var(--card-surface)] border border-border rounded-2xl p-5 space-y-4" data-testid={`rca-section-${type}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${type === 'production' ? 'bg-blue-100 dark:bg-blue-500/15 text-blue-500' : 'bg-fuchsia-100 dark:bg-fuchsia-500/15 text-fuchsia-500'}`}>
            <Icon size={20} />
          </div>
          <div>
            <h3 className="font-bold text-foreground text-base">{title}</h3>
            <p className="text-xs text-foreground/60">{description}</p>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-foreground/60">Periode:</span>
        {PERIOD_OPTIONS.map(o => (
          <button key={o.v} onClick={() => setDays(o.v)}
            data-testid={`rca-period-${type}-${o.v}`}
            className={`px-2.5 py-1 rounded-md text-xs transition-colors ${days === o.v ? 'bg-violet-600 text-foreground' : 'bg-[var(--input-surface)] text-foreground/65 hover:text-foreground'}`}>
            {o.label}
          </button>
        ))}
        <button
          data-testid={`rca-run-${type}`}
          onClick={run} disabled={loading}
          className="ml-auto px-4 py-1.5 rounded-lg text-xs font-medium bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500 text-foreground disabled:opacity-50 flex items-center gap-1.5"
        >
          {loading ? <><RefreshCw size={12} className="animate-spin" /> Menganalisis...</> : <><Sparkles size={12} /> Generate Analysis</>}
        </button>
      </div>

      {loading && (
        <div className="flex flex-col items-center justify-center py-8 text-xs text-foreground/60">
          <div className="w-10 h-10 rounded-full border-2 border-violet-500 border-t-transparent animate-spin mb-3"></div>
          <p>Claude Sonnet menganalisis pola data... (5-15 detik)</p>
        </div>
      )}

      {error && !loading && (
        <div className="bg-red-100 dark:bg-red-500/10 border border-red-400 dark:border-red-500/30 rounded-lg p-3 text-xs text-red-700 dark:text-red-500">
          <AlertCircle size={12} className="inline mr-1" /> {error}
        </div>
      )}

      {result && !loading && <AnalysisResult result={result} type={type} />}

      {!loading && !result && !error && (
        <div className="text-center py-8 text-xs text-foreground/40">
          <Brain size={28} className="mx-auto mb-2 opacity-40" />
          <p>Klik <span className="font-semibold text-foreground/60">Generate Analysis</span> untuk mulai analisis {title.toLowerCase()}.</p>
        </div>
      )}
    </div>
  );
}

function HistorySection({ token }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/analytics/ai/history?limit=10`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.ok) setItems(await r.json());
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="bg-[var(--card-surface)] border border-border rounded-2xl p-5">
      <div className="flex items-center gap-2 mb-3">
        <History size={14} className="text-violet-500" />
        <h3 className="text-sm font-semibold">Riwayat Analisis Anda ({items.length})</h3>
        <button onClick={load} className="ml-auto text-xs text-foreground/60 hover:text-foreground">
          <RefreshCw size={11} className={`inline ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
      {items.length === 0 && !loading && (
        <p className="text-xs text-foreground/50 italic text-center py-4">Belum ada analisis.</p>
      )}
      <div className="space-y-2">
        {items.map(h => (
          <div key={h.id} data-testid="rca-history-row" className="flex items-center gap-3 bg-[var(--input-surface)] rounded-lg p-2.5 text-xs">
            <div className={`w-6 h-6 rounded flex-shrink-0 flex items-center justify-center ${h.type === 'production' ? 'bg-blue-100 dark:bg-blue-500/15 text-blue-500' : 'bg-fuchsia-100 dark:bg-fuchsia-500/15 text-fuchsia-500'}`}>
              {h.type === 'production' ? <Factory size={12} /> : <Shield size={12} />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-medium text-foreground">
                RCA {h.type === 'production' ? 'Produksi' : 'QC'} · {h.filters?.days} hari
              </div>
              <div className="text-[10px] text-foreground/55 truncate">
                {h.result?.analysis?.root_cause_hypothesis}
              </div>
            </div>
            <div className="text-[10px] text-foreground/40 whitespace-nowrap">
              {h.created_at ? new Date(h.created_at).toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' }) : ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AIInsightsModule({ token }) {
  return (
    <div className="space-y-5" data-testid="ai-insights-module">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center flex-shrink-0">
          <Brain size={20} className="text-foreground" />
        </div>
        <div>
          <h2 className="text-lg font-bold text-foreground">AI Insights & Root-Cause Analysis</h2>
          <p className="text-xs text-foreground/60">Analisis pola produksi dan QC dengan Claude Sonnet 4.5 — dapatkan rekomendasi actionable dalam hitungan detik.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <RCASection
          token={token}
          type="production"
          title="Production RCA"
          icon={Factory}
          description="Deteksi bottleneck proses, line underperforming, pola WO delay."
        />
        <RCASection
          token={token}
          type="qc"
          title="QC Failure RCA"
          icon={Shield}
          description="Pola failure rate per line/model, worst offender, primary defect pattern."
        />
      </div>

      <HistorySection token={token} />
    </div>
  );
}
