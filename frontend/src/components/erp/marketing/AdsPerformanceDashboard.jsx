import React, { useState, useEffect, useCallback } from 'react';
import {
  TrendingUp, DollarSign, Target, MousePointer, Eye, RefreshCw, Loader2,
  Brain, Sparkles, ChevronRight, Pause, ArrowUp, Minus, Zap, BarChart3,
  Plus, Pencil, Trash2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { useActiveMarketingAccount } from '@/hooks/useActiveMarketingAccount';
import { ActiveAccountBar } from './ActiveAccountBar';
import { useMarketingAccounts } from '@/hooks/useMarketingAccounts';
import axios from 'axios';
import AdsEntryDialog from './AdsEntryDialog';

const API = process.env.REACT_APP_BACKEND_URL;

function fmt(n) { return new Intl.NumberFormat('id-ID').format(n || 0); }
function fmtRp(n) { return `Rp ${fmt(n)}`; }

const PLATFORM_ICONS = { meta: '📘', tiktok: '🎵', google: '🔍' };

const REC_TYPE_CONFIG = {
  pause:            { label: 'Pause',          color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',       icon: Pause },
  scale_up:         { label: 'Scale Up',        color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', icon: ArrowUp },
  optimize:         { label: 'Optimize',        color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',   icon: Zap },
  budget_shift:     { label: 'Budget Shift',    color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',      icon: BarChart3 },
  creative_refresh: { label: 'Creative Refresh',color: 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300', icon: Sparkles },
};

const PRIORITY_CONFIG = {
  urgent: { dot: 'bg-red-500', label: 'Urgent' },
  high:   { dot: 'bg-orange-500', label: 'High' },
  medium: { dot: 'bg-amber-400', label: 'Medium' },
  low:    { dot: 'bg-muted', label: 'Low' },
};

export default function AdsPerformanceDashboard({ token }) {
  const { toast } = useToast();
  const { activeAccount, setActiveAccount } = useActiveMarketingAccount();
  const { accounts: masterAccounts } = useMarketingAccounts(token);
  const [summary, setSummary] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [loading, setLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [aiRecs, setAiRecs] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('campaigns');
  // F16 — dialog input/ubah biaya iklan
  const [adsDialogOpen, setAdsDialogOpen] = useState(false);
  const [adsEditing, setAdsEditing] = useState(null);

  const [platformFilter, setPlatformFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  
  const authH = { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` };
  
  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      // F14 — ringkasan iklan dilingkupi toko yang sama dengan tabelnya.
      const res = await axios.get(`${API}/api/marketing/ads/summary`, {
        headers: authH,
        params: activeAccount?.id ? { account_id: activeAccount.id } : {},
      });
      if (res.data.success) {
        setSummary(res.data.data);
      }
    } catch (e) {
      toast({ title: 'Gagal load ads summary', variant: 'destructive' });
    } finally {
      setSummaryLoading(false);
    }
  }, [token, activeAccount]); // eslint-disable-line

  const fetchCampaigns = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, page_size: 20 };
      if (platformFilter) params.platform = platformFilter;
      if (statusFilter) params.status = statusFilter;
      if (activeAccount?.id) params.account_id = activeAccount.id;
      const res = await axios.get(`${API}/api/marketing/ads/campaigns`, { params, headers: authH });
      if (res.data.success) {
        setCampaigns(res.data.data.campaigns || []);
        setPagination(res.data.pagination);
      }
    } catch (e) {
      toast({ title: 'Gagal load campaigns', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [page, platformFilter, statusFilter, token, activeAccount]); // eslint-disable-line
  
  useEffect(() => { fetchSummary(); }, [fetchSummary]);
  useEffect(() => { fetchCampaigns(); }, [fetchCampaigns]);

  const runAiRecommendations = async () => {
    setAiLoading(true);
    setActiveTab('ai');
    try {
      const res = await axios.post(`${API}/api/marketing/ads/ai-recommendations`, {}, { headers: authH });
      if (res.data.success) setAiRecs(res.data.data);
    } catch (e) {
      toast({ title: 'AI Recommendations gagal', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setAiLoading(false);
    }
  };
  
  const kpis = [
    { label: 'Total Spend', value: fmtRp(summary?.total_spend), sub: `${summary?.total_campaigns || 0} campaigns`, color: 'text-red-600', bg: 'bg-red-50 dark:bg-red-900/20', icon: DollarSign },
    { label: 'Total Revenue', value: fmtRp(summary?.total_revenue), sub: `ROAS: ${summary?.overall_roas || 0}x`, color: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-900/20', icon: TrendingUp },
    { label: 'Conversions', value: fmt(summary?.total_conversions), sub: `CPA: ${fmtRp(summary?.overall_cpa)}`, color: 'text-amber-600', bg: 'bg-amber-50 dark:bg-amber-900/20', icon: Target },
    { label: 'CTR', value: `${summary?.overall_ctr || 0}%`, sub: 'Click-through Rate', color: 'text-blue-600', bg: 'bg-blue-50 dark:bg-blue-900/20', icon: MousePointer },
  ];
  
  return (
    <div className="min-h-screen bg-background p-4 md:p-6" data-testid="ads-dashboard">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Ads Performance</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Monitor campaign iklan dari Meta, TikTok, Google</p>
        </div>
        <div className="flex gap-2">
          {/* F16 — biaya iklan kini bisa DIINPUT dari layar. Sebelumnya backend
              hanya punya endpoint GET, sehingga semua angka ROAS/CPA berasal dari
              data demo yang tidak bisa diperbarui. */}
          <Button size="sm" data-testid="ads-add-btn"
            onClick={() => { setAdsEditing(null); setAdsDialogOpen(true); }}>
            <Plus size={13} className="mr-1" /> Input Biaya Iklan
          </Button>
          <Button size="sm" variant="outline" onClick={runAiRecommendations} disabled={aiLoading} data-testid="ai-recs-btn">
            {aiLoading ? <Loader2 size={13} className="mr-1 animate-spin" /> : <Brain size={13} className="mr-1" />}
            AI Rekomendasi
          </Button>
          <Button variant="outline" size="sm" onClick={() => { fetchSummary(); fetchCampaigns(); }}>
            <RefreshCw size={13} className="mr-1" /> Refresh
          </Button>
        </div>
      </div>
      
      <div className="mb-4">
        <ActiveAccountBar accounts={masterAccounts} activeAccount={activeAccount} onAccountChange={setActiveAccount} hint="Context akun untuk ads:" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        {kpis.map(k => (
          <div key={k.label} className={`rounded-xl border p-4 ${k.bg}`}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-muted-foreground font-medium">{k.label}</span>
              <k.icon size={15} className={k.color} />
            </div>
            <p className={`text-2xl font-bold tabular-nums ${k.color}`}>{summaryLoading ? '...' : (k.value || '0')}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{summaryLoading ? '' : k.sub}</p>
          </div>
        ))}
      </div>
      
      {summary?.by_platform && Object.keys(summary.by_platform).length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {Object.entries(summary.by_platform).map(([platform, data]) => (
            <Card key={platform}>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <span className="text-2xl">{PLATFORM_ICONS[platform]}</span>
                  <span className="capitalize">{platform}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Spend:</span>
                  <span className="font-bold">{fmtRp(data.spend)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Revenue:</span>
                  <span className="font-bold text-emerald-600">{fmtRp(data.revenue)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">ROAS:</span>
                  <span className="font-bold">{data.roas}x</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Campaigns:</span>
                  <span className="font-bold">{data.campaigns}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      
      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-muted rounded-lg mb-6 overflow-x-auto">
        {[
          { id: 'campaigns', label: 'Campaigns', icon: BarChart3 },
          { id: 'ai', label: 'AI Rekomendasi', icon: Brain }
        ].map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all flex-1 justify-center whitespace-nowrap ${
              activeTab === t.id ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
            }`}
          ><t.icon size={14} />{t.label}</button>
        ))}
      </div>

      {/* Tab: Campaigns */}
      {activeTab === 'campaigns' && (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <CardTitle className="flex-1">Campaigns</CardTitle>
            <div className="flex items-center gap-2">
              <Select value={platformFilter || 'all'} onValueChange={v => { setPlatformFilter(v === 'all' ? '' : v); setPage(1); }}>
                <SelectTrigger className="w-[130px] h-9 text-xs">
                  <SelectValue placeholder="Platform" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Platform</SelectItem>
                  <SelectItem value="meta">📘 Meta</SelectItem>
                  <SelectItem value="tiktok">🎵 TikTok</SelectItem>
                  <SelectItem value="google">🔍 Google</SelectItem>
                </SelectContent>
              </Select>
              <Select value={statusFilter || 'all'} onValueChange={v => { setStatusFilter(v === 'all' ? '' : v); setPage(1); }}>
                <SelectTrigger className="w-[120px] h-9 text-xs">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Status</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="paused">Paused</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <Loader2 className="animate-spin text-muted-foreground" size={24} />
            </div>
          ) : campaigns.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
              <Eye size={32} className="opacity-30 mb-2" />
              <p className="text-sm">Tidak ada campaign</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    {['Campaign', 'Toko', 'Platform', 'Spend', 'Revenue', 'ROAS', 'CPA', 'CTR', 'Conversions', 'Status', ''].map(h => (
                      <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {campaigns.map(c => (
                    <tr key={c.id} className="hover:bg-muted/30 transition-colors">
                      <td className="px-3 py-2 font-medium max-w-[200px] truncate" title={c.campaign_name}>{c.campaign_name}</td>
                      <td className="px-3 py-2 text-xs text-muted-foreground max-w-[140px] truncate" title={c.account_name}>{c.account_name || '—'}</td>
                      <td className="px-3 py-2 text-xs">
                        {PLATFORM_ICONS[c.platform]} <span className="capitalize">{c.platform}</span>
                      </td>
                      <td className="px-3 py-2 tabular-nums text-xs">{fmtRp(c.spend)}</td>
                      <td className="px-3 py-2 tabular-nums text-xs text-emerald-600 font-semibold">{fmtRp(c.revenue)}</td>
                      <td className="px-3 py-2 tabular-nums font-bold">{c.roas}x</td>
                      <td className="px-3 py-2 tabular-nums text-xs">{fmtRp(c.cpa)}</td>
                      <td className="px-3 py-2 tabular-nums text-xs">{c.ctr}%</td>
                      <td className="px-3 py-2 tabular-nums">{fmt(c.conversions)}</td>
                      <td className="px-3 py-2">
                        <Badge variant={c.status === 'active' ? 'default' : 'secondary'} className="text-xs">
                          {c.status}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        <Button size="sm" variant="ghost" className="h-7 px-2"
                          data-testid={`ads-edit-${c.id}`}
                          onClick={() => { setAdsEditing(c); setAdsDialogOpen(true); }}>
                          <Pencil size={13} />
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 px-2 text-red-600"
                          data-testid={`ads-delete-${c.id}`}
                          onClick={async () => {
                            if (!window.confirm(`Hapus data iklan "${c.campaign_name}"?`)) return;
                            try {
                              await axios.delete(`${API}/api/marketing/ads/campaigns/${c.id}`, { headers: authH });
                              toast({ title: 'Data iklan dihapus' });
                              fetchCampaigns(); fetchSummary();
                            } catch (e) {
                              toast({ title: 'Gagal menghapus', description: e.response?.data?.detail, variant: 'destructive' });
                            }
                          }}>
                          <Trash2 size={13} />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {pagination && pagination.total_pages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t">
              <span className="text-xs text-muted-foreground">{pagination.total} campaigns</span>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" className="h-7" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Sebelumnya</Button>
                <span className="text-xs">{page} / {pagination.total_pages}</span>
                <Button size="sm" variant="outline" className="h-7" disabled={page >= pagination.total_pages} onClick={() => setPage(p => p + 1)}>Berikutnya</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
      )}

      {/* Tab: AI Recommendations */}
      {activeTab === 'ai' && (
        <div className="space-y-4">
          {aiLoading && (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <Loader2 className="animate-spin text-primary" size={32} />
              <p className="text-sm text-muted-foreground">AI sedang menganalisis campaign...</p>
            </div>
          )}
          {!aiRecs && !aiLoading && (
            <Card className="border-dashed">
              <CardContent className="flex flex-col items-center justify-center py-12 gap-4">
                <Brain size={40} className="text-muted-foreground opacity-40" />
                <div className="text-center">
                  <p className="font-medium">AI Campaign Optimizer</p>
                  <p className="text-sm text-muted-foreground mt-1">AI akan menganalisis ROAS, CTR, CPA semua campaign dan memberikan rekomendasi konkret</p>
                </div>
                <Button onClick={runAiRecommendations}><Sparkles size={14} className="mr-2" /> Analisis Campaign</Button>
              </CardContent>
            </Card>
          )}
          {aiRecs && !aiLoading && (
            <div className="space-y-4">
              {/* Summary */}
              <Card className="bg-gradient-to-r from-indigo-50 to-blue-50 dark:from-indigo-950/30 dark:to-blue-950/30 border-indigo-200 dark:border-indigo-800">
                <CardContent className="pt-4">
                  <div className="flex items-start gap-3">
                    <Brain size={20} className="text-indigo-600 mt-0.5 shrink-0" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-indigo-900 dark:text-indigo-100">{aiRecs.summary}</p>
                      <div className="flex flex-wrap gap-3 mt-2 text-xs">
                        {aiRecs.best_platform && <span className="text-emerald-600 font-medium">✅ Best: {aiRecs.best_platform}</span>}
                        {aiRecs.worst_platform && <span className="text-red-600 font-medium">⚠️ Worst: {aiRecs.worst_platform}</span>}
                        {aiRecs.overall_roas && <span className="text-muted-foreground">Overall ROAS: {aiRecs.overall_roas}x</span>}
                      </div>
                      {aiRecs.budget_advice && (
                        <p className="text-xs text-indigo-700 dark:text-indigo-300 mt-1.5 italic">{aiRecs.budget_advice}</p>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Recommendation Cards */}
              <div className="space-y-3">
                {(aiRecs.recommendations || []).map((rec, i) => {
                  const rType = REC_TYPE_CONFIG[rec.type] || REC_TYPE_CONFIG.optimize;
                  const pCfg = PRIORITY_CONFIG[rec.priority] || PRIORITY_CONFIG.medium;
                  const RIcon = rType.icon;
                  return (
                    <Card key={i} className="transition-all hover:shadow-md">
                      <CardContent className="pt-4">
                        <div className="flex items-start gap-3">
                          <div className={`px-2 py-1 rounded-md text-xs font-medium shrink-0 ${rType.color}`}>
                            <RIcon size={12} className="inline mr-1" />{rType.label}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex flex-wrap items-center gap-2 mb-1">
                              <span className="font-semibold text-sm">{rec.campaign}</span>
                              {rec.platform && <Badge variant="outline" className="text-xs">{PLATFORM_ICONS[rec.platform]} {rec.platform}</Badge>}
                              <span className={`inline-flex items-center gap-1 text-xs font-medium`}>
                                <span className={`w-1.5 h-1.5 rounded-full ${pCfg.dot}`} />{pCfg.label}
                              </span>
                            </div>
                            <p className="text-sm font-medium text-foreground">{rec.action}</p>
                            <p className="text-xs text-muted-foreground mt-0.5">{rec.reason}</p>
                            {rec.expected_impact && (
                              <p className="text-xs text-primary mt-1.5 flex items-center gap-1">
                                <ChevronRight size={11} /> {rec.expected_impact}
                              </p>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
              <Button variant="outline" size="sm" onClick={runAiRecommendations}>
                <RefreshCw size={13} className="mr-1" /> Refresh Rekomendasi
              </Button>
            </div>
          )}
        </div>
      )}
      <AdsEntryDialog
        open={adsDialogOpen}
        entry={adsEditing}
        token={token}
        onClose={() => { setAdsDialogOpen(false); setAdsEditing(null); }}
        onSaved={() => { fetchCampaigns(); fetchSummary(); }}
      />
    </div>
  );
}

