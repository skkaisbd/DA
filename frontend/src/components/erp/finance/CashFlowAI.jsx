/**
 * AI Cash Flow Prediction — CV. Dewi Aditya ERP
 * Finance portal feature powered by Claude via EMERGENT_LLM_KEY.
 */
import { useState, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Loader2, Brain, TrendingUp, TrendingDown, Minus,
  RefreshCw, AlertCircle, ArrowRight, ChevronDown, ChevronUp,
  Banknote, Clock, BarChart3,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const API = process.env.REACT_APP_BACKEND_URL;

const fmtIDR = (n) => {
  const v = Number(n || 0);
  if (v >= 1e9) return `Rp ${(v / 1e9).toFixed(2)} M`;
  if (v >= 1e6) return `Rp ${(v / 1e6).toFixed(1)} jt`;
  if (v >= 1e3) return `Rp ${(v / 1e3).toFixed(0)} rb`;
  return `Rp ${v.toLocaleString('id-ID')}`;
};

// AR Aging mini chart
function AgingBars({ data, label }) {
  if (!data) return null;
  const keys = Object.keys(data);
  const total = Object.values(data).reduce((s, v) => s + v, 0);
  const COLORS = { current: '#22c55e', '1-30': '#eab308', '31-60': '#f97316', '61-90': '#ef4444', '90+': '#7f1d1d',
                   d30: '#eab308', d60: '#f97316', d90: '#ef4444', d90plus: '#7f1d1d' };
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-semibold text-muted-foreground">{label} — Total: {fmtIDR(total)}</p>
      {keys.map(k => {
        const v = data[k] || 0;
        if (v === 0) return null;
        const pct = total > 0 ? Math.round(v / total * 100) : 0;
        return (
          <div key={k} className="flex items-center gap-2 text-xs">
            <div className="w-16 text-muted-foreground shrink-0">{k}</div>
            <div className="flex-1 bg-muted/40 rounded-full h-2.5 overflow-hidden">
              <div className="h-2.5 rounded-full" style={{ width: `${pct}%`, backgroundColor: COLORS[k] || '#94a3b8' }} />
            </div>
            <div className="w-16 text-right font-medium">{fmtIDR(v)}</div>
          </div>
        );
      })}
    </div>
  );
}

// Render markdown-ish text with bold & bullets
function AnalysisText({ text }) {
  if (!text) return null;
  const lines = text.split('\n');
  return (
    <div className="space-y-1.5 text-sm leading-relaxed">
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-2" />;
        // Bold headers: **text**
        const bold = line.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-foreground">$1</strong>');
        // Bullets
        const isBullet = line.trim().startsWith('- ') || line.trim().startsWith('• ');
        if (isBullet) {
          return (
            <div key={i} className="flex gap-2 items-start">
              <div className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 shrink-0" />
              <span className="text-muted-foreground" dangerouslySetInnerHTML={{ __html: bold.replace(/^[-•]\s*/, '') }} />
            </div>
          );
        }
        return <p key={i} className="text-muted-foreground" dangerouslySetInnerHTML={{ __html: bold }} />;
      })}
    </div>
  );
}

export default function CashFlowAIModule({ token }) {
  const { toast } = useToast();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showContext, setShowContext] = useState(false);
  const headers = { Authorization: `Bearer ${token}` };

  const fetchPrediction = useCallback(async () => {
    setLoading(true);
    setResult(null);
    try {
      const { data } = await axios.get(`${API}/api/finance/ai-cashflow`, { headers });
      setResult(data);
    } catch (e) {
      const msg = e.response?.data?.detail || 'Gagal mengambil prediksi AI.';
      toast({ title: msg, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const ctx = result?.context;
  const netFlow = ctx ? ctx.cash_in_60 - ctx.cash_out_60 : null;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Brain className="w-5 h-5 text-primary" />
            AI Cash Flow Prediction
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Prediksi arus kas 30/60/90 hari berbasis AR aging + AP aging + riwayat kas — dianalisis AI (GPT-4o)
          </p>
        </div>
        <Button
          data-testid="btn-run-ai-cashflow"
          onClick={fetchPrediction}
          disabled={loading}
          className="shrink-0"
        >
          {loading
            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Menganalisis...</>
            : <><Brain className="w-4 h-4 mr-2" /> {result ? 'Refresh Prediksi' : 'Jalankan Prediksi AI'}</>}
        </Button>
      </div>

      {/* Context cards — always show if result available */}
      {ctx && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card className="bg-blue-50/50 border-blue-200">
            <CardContent className="pt-3 pb-2">
              <p className="text-xs text-muted-foreground">Total AR Outstanding</p>
              <p className="text-base font-bold text-blue-700">{fmtIDR(ctx.total_ar)}</p>
              <p className="text-xs text-red-600">{fmtIDR(ctx.overdue_ar)} overdue</p>
            </CardContent>
          </Card>
          <Card className="bg-amber-50/50 border-amber-200">
            <CardContent className="pt-3 pb-2">
              <p className="text-xs text-muted-foreground">Total AP Outstanding</p>
              <p className="text-base font-bold text-amber-700">{fmtIDR(ctx.total_ap)}</p>
              <p className="text-xs text-muted-foreground">Hutang belum bayar</p>
            </CardContent>
          </Card>
          <Card className={`${netFlow >= 0 ? 'bg-emerald-50/50 border-emerald-200' : 'bg-red-50/50 border-red-200'}`}>
            <CardContent className="pt-3 pb-2">
              <p className="text-xs text-muted-foreground">Net Cash 60 Hari</p>
              <p className={`text-base font-bold flex items-center gap-1 ${netFlow >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                {netFlow >= 0
                  ? <TrendingUp className="w-4 h-4 shrink-0" />
                  : <TrendingDown className="w-4 h-4 shrink-0" />}
                {fmtIDR(Math.abs(netFlow))}
              </p>
              <p className="text-xs text-muted-foreground">{netFlow >= 0 ? 'Surplus' : 'Defisit'}</p>
            </CardContent>
          </Card>
          <Card className="bg-purple-50/50 border-purple-200">
            <CardContent className="pt-3 pb-2">
              <p className="text-xs text-muted-foreground">Order Produksi Aktif</p>
              <p className="text-base font-bold text-purple-700">{ctx.active_orders}</p>
              <p className="text-xs text-muted-foreground">Komitmen kas tersisa</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Empty state */}
      {!result && !loading && (
        <Card className="border-dashed border-2 border-primary/20">
          <CardContent className="py-12 text-center">
            <Brain className="w-12 h-12 text-primary/30 mx-auto mb-3" />
            <p className="font-medium text-muted-foreground">Klik "Jalankan Prediksi AI" untuk memulai</p>
            <p className="text-xs text-muted-foreground mt-1">
              AI akan menganalisis AR aging, AP aging, dan arus kas 60 hari terakhir
            </p>
          </CardContent>
        </Card>
      )}

      {/* Loading state */}
      {loading && (
        <Card className="border-primary/20">
          <CardContent className="py-12 text-center">
            <div className="flex flex-col items-center gap-3">
              <div className="relative">
                <Brain className="w-12 h-12 text-primary/40" />
                <Loader2 className="w-6 h-6 text-primary animate-spin absolute -bottom-1 -right-1" />
              </div>
              <p className="font-medium">AI sedang menganalisis data keuangan...</p>
              <p className="text-xs text-muted-foreground">Biasanya 10-20 detik</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* AI Analysis result */}
      {result?.analysis && (
        <Card className="border-primary/20 bg-primary/2" data-testid="ai-cashflow-result">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm flex items-center gap-2">
                <Brain className="w-4 h-4 text-primary" />
                Analisis AI — {new Date().toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' })}
              </CardTitle>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">Claude AI</Badge>
                <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={fetchPrediction} disabled={loading}>
                  <RefreshCw className="w-3 h-3 mr-1" /> Refresh
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="prose prose-sm max-w-none">
              <AnalysisText text={result.analysis} />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Aging details toggle */}
      {ctx && (
        <Card>
          <CardHeader className="pb-2 cursor-pointer" onClick={() => setShowContext(v => !v)}>
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-muted-foreground" />
                Detail Data — AR & AP Aging
              </CardTitle>
              {showContext ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
            </div>
          </CardHeader>
          {showContext && (
            <CardContent className="space-y-4">
              <AgingBars data={ctx.ar_aging} label="AR Aging (Piutang)" />
              <div className="border-t pt-4">
                <AgingBars data={ctx.ap_aging} label="AP Aging (Hutang)" />
              </div>
              <div className="border-t pt-4 grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-xs font-semibold text-muted-foreground mb-2">AR Jatuh Tempo 30 Hari ke Depan</p>
                  {ctx.upcoming_ar?.length > 0 ? ctx.upcoming_ar.map((inv, i) => (
                    <div key={i} className="flex justify-between text-xs py-1 border-b border-dashed last:border-0">
                      <span className="text-muted-foreground truncate">{inv.buyer_name || 'Buyer'}</span>
                      <span className="font-medium ml-2 shrink-0">{fmtIDR(inv.balance)}</span>
                    </div>
                  )) : <p className="text-xs text-muted-foreground">Tidak ada</p>}
                </div>
                <div>
                  <p className="text-xs font-semibold text-muted-foreground mb-2">AP Jatuh Tempo 30 Hari ke Depan</p>
                  {ctx.upcoming_ap?.length > 0 ? ctx.upcoming_ap.map((inv, i) => (
                    <div key={i} className="flex justify-between text-xs py-1 border-b border-dashed last:border-0">
                      <span className="text-muted-foreground truncate">{inv.vendor_name || 'Vendor'}</span>
                      <span className="font-medium ml-2 shrink-0">{fmtIDR(inv.balance)}</span>
                    </div>
                  )) : <p className="text-xs text-muted-foreground">Tidak ada</p>}
                </div>
              </div>
            </CardContent>
          )}
        </Card>
      )}
    </div>
  );
}
