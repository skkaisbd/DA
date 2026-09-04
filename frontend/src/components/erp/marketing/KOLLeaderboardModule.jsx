import { useState, useEffect, useCallback } from 'react';
import apiFetch from '@/lib/apiFetch';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Trophy, TrendingUp, Eye, ShoppingBag, Percent, RefreshCw, Users, Star, ChevronRight, BarChart3, Table2, LayoutGrid } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { formatRupiah } from '@/lib/format';

// F10 (2026-08-13) — layar ini dulu KARTU-SAJA. Papan peringkat justru bentuk data
// yang paling butuh TABEL: rapat mingguan membandingkan kreator baris-per-baris
// (sesi · viewers · order/sesi · conversion · omzet), dan itu tidak bisa dilakukan
// dengan mata kalau setiap kreator berupa kartu. Urutan peringkat TETAP dihitung
// backend (`rank`) — layar tidak boleh mengurutkan sendiri, kalau tidak lampiran
// rapat dan layar bisa menunjuk "kreator terbaik" yang BERBEDA.
const VIEW_KEY = 'kol_leaderboard_view';
const HEADS = ['#', 'Kreator', 'Sesi', 'Viewers', 'Order', 'Order/Sesi',
  'Conv. Rate', 'Omzet', 'Omzet/Sesi', ''];

const fmt = (n, decimals = 0) => {
  if (n == null) return '-';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}jt`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}rb`;
  return n.toFixed ? n.toFixed(decimals) : n;
};

const fmtRp = (n) => n == null ? '-' : formatRupiah(n);

const RANK_COLORS = ['text-yellow-500', 'text-muted-foreground', 'text-orange-500'];
const RANK_BG    = ['bg-yellow-50 border-yellow-200', 'bg-muted border-border', 'bg-orange-50 border-orange-200'];

const SORT_OPTIONS = [
  { value: 'conversion_rate', label: 'Conversion Rate' },
  { value: 'revenue',         label: 'Total Revenue' },
  { value: 'viewers',         label: 'Total Viewers' },
  { value: 'orders_per_session', label: 'Orders/Session' },
];

const PERIOD_OPTIONS = [
  { value: 7,  label: '7 hari' },
  { value: 14, label: '14 hari' },
  { value: 30, label: '30 hari' },
  { value: 90, label: '3 bulan' },
];

function MetricBadge({ icon: Icon, label, value, colorClass }) {
  return (
    <div className="flex items-center gap-1.5">
      <Icon className={`h-3.5 w-3.5 ${colorClass}`} />
      <span className="text-xs text-muted-foreground">{label}:</span>
      <span className="text-xs font-semibold">{value}</span>
    </div>
  );
}

function KOLDetailModal({ kolId, kolName, days, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch(`/marketing/kol-leaderboard/${kolId}/detail?days=${days}`)
      .then(d => setDetail(d.data))
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [kolId, days]);

  return (
    <div className="fixed inset-0 bg-foreground/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-background rounded-xl shadow-2xl w-full max-w-lg max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold flex items-center gap-2">
              <Star className="h-5 w-5 text-yellow-500" />
              {kolName}
            </h3>
            <Button size="sm" variant="ghost" onClick={onClose}>✕</Button>
          </div>
          {loading && <div className="text-center py-8 text-sm text-muted-foreground">Memuat detail...</div>}
          {!loading && !detail && <div className="text-center py-8 text-sm text-muted-foreground">Data tidak tersedia</div>}
          {!loading && detail && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                {[
                  { icon: TrendingUp, label: 'Total Revenue', value: fmtRp(detail.metrics?.total_revenue), color: 'text-green-500' },
                  { icon: Eye,        label: 'Total Viewers', value: fmt(detail.metrics?.total_viewers), color: 'text-blue-500' },
                  { icon: ShoppingBag,label: 'Total Orders',  value: fmt(detail.metrics?.total_orders), color: 'text-purple-500' },
                  { icon: Percent,    label: 'Conv. Rate',    value: `${(detail.metrics?.conversion_rate || 0).toFixed(2)}%`, color: 'text-orange-500' },
                  { icon: BarChart3,  label: 'Sessions',      value: fmt(detail.metrics?.session_count), color: 'text-teal-500' },
                  { icon: ShoppingBag,label: 'Orders/Session',value: (detail.metrics?.orders_per_session || 0).toFixed(1), color: 'text-pink-500' },
                ].map((m, i) => (
                  <Card key={i} className="border border-border">
                    <CardContent className="p-3 flex items-center gap-2">
                      <m.icon className={`h-5 w-5 ${m.color}`} />
                      <div>
                        <p className="text-[11px] text-muted-foreground">{m.label}</p>
                        <p className="text-sm font-bold">{m.value}</p>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">Sesi Terakhir ({detail.sessions?.length || 0})</p>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {(detail.sessions || []).slice(0, 10).map((s, i) => (
                    <div key={i} className="flex items-center justify-between text-xs py-1.5 border-b border-border last:border-0">
                      <span className="text-muted-foreground">{s.session_date ? new Date(s.session_date).toLocaleDateString('id-ID') : '-'}</span>
                      <div className="flex items-center gap-3">
                        <span className="flex items-center gap-1"><Eye className="h-3 w-3" />{fmt(s.viewers)}</span>
                        <span className="flex items-center gap-1"><ShoppingBag className="h-3 w-3" />{fmt(s.orders)}</span>
                        <span className="font-medium text-green-600">{fmtRp(s.revenue)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function KOLLeaderboardModule() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [sortBy, setSortBy] = useState('conversion_rate');
  const [selectedKOL, setSelectedKOL] = useState(null);
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(VIEW_KEY) || 'table'; } catch { return 'table'; }
  });

  useEffect(() => {
    try { localStorage.setItem(VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);

  const loadLeaderboard = useCallback(async () => {
    setLoading(true);
    try {
      const result = await apiFetch(`/marketing/kol-leaderboard/?days=${days}&sort_by=${sortBy}`);
      setData(result);
    } catch (err) {
      toast({ title: 'Gagal memuat leaderboard', variant: 'destructive' });
      setData({ data: [], metadata: {} });
    } finally {
      setLoading(false);
    }
  }, [days, sortBy, toast]);

  useEffect(() => { loadLeaderboard(); }, [loadLeaderboard]);

  const items = data?.data || [];
  const meta = data?.metadata || {};
  const overall = meta?.overall_stats || {};

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-yellow-400 to-orange-500 flex items-center justify-center">
              <Trophy className="h-4 w-4 text-foreground" />
            </div>
            KOL Leaderboard
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">Performa multi-metric KOL — viewers, orders/session, conversion rate</p>
        </div>
        <Button size="sm" variant="outline" onClick={loadLeaderboard} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Periode:</span>
          <Select value={String(days)} onValueChange={v => setDays(Number(v))}>
            <SelectTrigger className="w-28 h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PERIOD_OPTIONS.map(o => (
                <SelectItem key={o.value} value={String(o.value)}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Urut by:</span>
          <Select value={sortBy} onValueChange={setSortBy}>
            <SelectTrigger className="w-44 h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SORT_OPTIONS.map(o => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex rounded-md border border-border overflow-hidden ml-auto">
          <button type="button" onClick={() => setView('table')} data-testid="kol-view-table"
            className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
              ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
            <Table2 size={12} /> Tabel
          </button>
          <button type="button" onClick={() => setView('grid')} data-testid="kol-view-grid"
            className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
              ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
            <LayoutGrid size={12} /> Kartu
          </button>
        </div>
      </div>

      {/* Overall Stats */}
      {overall && Object.keys(overall).length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { icon: TrendingUp, label: 'Total Revenue',   value: fmtRp(overall.total_revenue),       color: 'text-green-500',  bg: 'bg-green-50' },
            { icon: Eye,        label: 'Total Viewers',   value: fmt(overall.total_viewers),           color: 'text-blue-500',   bg: 'bg-blue-50' },
            { icon: ShoppingBag,label: 'Total Orders',    value: fmt(overall.total_orders),            color: 'text-purple-500', bg: 'bg-purple-50' },
            { icon: Percent,    label: 'Avg Conv. Rate',  value: `${(overall.avg_conversion_rate || 0).toFixed(2)}%`, color: 'text-orange-500', bg: 'bg-orange-50' },
          ].map((m, i) => (
            <Card key={i} className="border border-border">
              <CardContent className="p-3 flex items-center gap-3">
                <div className={`h-9 w-9 rounded-lg ${m.bg} flex items-center justify-center flex-shrink-0`}>
                  <m.icon className={`h-4 w-4 ${m.color}`} />
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] text-muted-foreground truncate">{m.label}</p>
                  <p className="text-sm font-bold truncate">{m.value}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Leaderboard Table */}
      <Card className="border border-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <Users className="h-4 w-4" />
            Ranking KOL ({items.length} kreator · {meta.period_days} hari)
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="text-center py-12 text-sm text-muted-foreground"><RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />Memuat data...</div>
          ) : items.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Trophy className="h-10 w-10 mx-auto mb-2 opacity-20" />
              <p className="text-sm">Belum ada data live session</p>
              <p className="text-xs mt-1">Input data sesi live di modul Live Session</p>
            </div>
          ) : view === 'table' ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs" data-testid="kol-table">
                <thead className="bg-muted/60">
                  <tr>{HEADS.map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                  ))}</tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {items.map((kol, i) => (
                    <tr key={kol.kol_id || i}
                      className={`hover:bg-muted/40 cursor-pointer ${i < 3 ? `${RANK_BG[i]} dark:bg-opacity-10` : ''}`}
                      onClick={() => setSelectedKOL(kol)}
                      data-testid={`kol-trow-${i}`}>
                      <td className={`px-3 py-2 font-bold ${i < 3 ? RANK_COLORS[i] : 'text-muted-foreground'}`}>
                        {i < 3 ? ['🥇', '🥈', '🥉'][i] : kol.rank}
                      </td>
                      <td className="px-3 py-2 font-medium text-foreground">{kol.kol_name || kol.kol_id}</td>
                      <td className="px-3 py-2">{fmt(kol.session_count)}</td>
                      <td className="px-3 py-2">{fmt(kol.total_viewers)}</td>
                      <td className="px-3 py-2">{fmt(kol.total_orders)}</td>
                      <td className="px-3 py-2">{(kol.orders_per_session || 0).toFixed(1)}</td>
                      <td className="px-3 py-2">
                        <span className={(kol.conversion_rate || 0) >= 1 ? 'text-emerald-600' : 'text-amber-600'}>
                          {(kol.conversion_rate || 0).toFixed(2)}%
                        </span>
                      </td>
                      <td className="px-3 py-2 font-semibold whitespace-nowrap">{fmtRp(kol.total_revenue)}</td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {fmtRp(kol.session_count ? (kol.total_revenue || 0) / kol.session_count : 0)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <ChevronRight className="h-4 w-4 text-muted-foreground inline" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="divide-y divide-border" data-testid="kol-grid">
              {items.map((kol, i) => (
                <button
                  key={kol.kol_id || i}
                  className={`w-full text-left px-4 py-3 hover:bg-muted/50 transition-colors flex items-center gap-4 ${
                    i < 3 ? `${RANK_BG[i]} dark:bg-opacity-10` : ''
                  }`}
                  onClick={() => setSelectedKOL(kol)}
                  data-testid={`kol-row-${i}`}
                >
                  {/* Rank */}
                  <div className={`w-8 text-center font-bold text-sm ${i < 3 ? RANK_COLORS[i] : 'text-muted-foreground'}`}>
                    {i < 3 ? (['🥇','🥈','🥉'][i]) : kol.rank}
                  </div>

                  {/* Name */}
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm truncate">{kol.kol_name || kol.kol_id}</p>
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
                      <MetricBadge icon={TrendingUp} label="Rev" value={fmtRp(kol.total_revenue)} colorClass="text-green-500" />
                      <MetricBadge icon={Eye}         label="Views" value={fmt(kol.total_viewers)} colorClass="text-blue-500" />
                      <MetricBadge icon={ShoppingBag} label="O/S"  value={(kol.orders_per_session || 0).toFixed(1)} colorClass="text-purple-500" />
                      <MetricBadge icon={Percent}     label="CR"   value={`${(kol.conversion_rate || 0).toFixed(2)}%`} colorClass="text-orange-500" />
                    </div>
                  </div>

                  <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Detail Modal */}
      {selectedKOL && (
        <KOLDetailModal
          kolId={selectedKOL.kol_id}
          kolName={selectedKOL.kol_name || selectedKOL.kol_id}
          days={days}
          onClose={() => setSelectedKOL(null)}
        />
      )}
    </div>
  );
}

