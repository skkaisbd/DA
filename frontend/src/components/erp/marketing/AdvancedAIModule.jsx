import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Brain, TrendingUp, TrendingDown, DollarSign, Settings, Power, PowerOff,
  Zap, RefreshCw, Loader2, ChevronDown, ChevronUp, CheckCircle2,
  XCircle, AlertTriangle, Clock, FlaskConical, Users, BarChart3,
  Sparkles, ChevronRight, Plus, Pencil, Save, X, Info, Shield, History,
  Play, Pause, Trophy, ArrowUp, ArrowDown, Target
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;
function fmt(n) { return new Intl.NumberFormat('id-ID').format(n || 0); }
function fmtRp(n) { return `Rp ${fmt(n)}`; }
function fmtPct(n) { return `${(n || 0).toFixed(1)}%`; }

const RISK_CONFIG = {
  critical: { label: 'Kritis',  color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',       dot: 'bg-red-500',    icon: AlertTriangle },
  high:     { label: 'Tinggi',  color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300', dot: 'bg-orange-500', icon: AlertTriangle },
  medium:   { label: 'Sedang',  color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',   dot: 'bg-amber-400',  icon: Clock },
  low:      { label: 'Rendah',  color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', dot: 'bg-emerald-500', icon: CheckCircle2 }
};

const DIR_CONFIG = {
  increase: { icon: ArrowUp,   color: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-900/20' },
  decrease: { icon: ArrowDown, color: 'text-red-600',     bg: 'bg-red-50 dark:bg-red-900/20' },
  hold:     { icon: Target,    color: 'text-muted-foreground',   bg: 'bg-muted dark:bg-slate-800/50' }
};

const STATUS_CONFIG = {
  pending:  { label: 'Menunggu', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' },
  approved: { label: 'Disetujui', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' },
  applied:  { label: 'Diterapkan', color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300' },
  rejected: { label: 'Ditolak', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' }
};

const AB_STATUS = {
  draft:     { label: 'Draft',    color: 'bg-muted text-muted-foreground dark:bg-slate-800 dark:text-foreground/70' },
  running:   { label: 'Running',  color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300' },
  paused:    { label: 'Paused',   color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' },
  concluded: { label: 'Selesai',  color: 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300' }
};


// ─────────────────────────────────────────────────────────────────
// TAB 1: DYNAMIC PRICING
// ─────────────────────────────────────────────────────────────────
function DynamicPricingTab({ authH }) {
  const { toast } = useToast();
  const [settings, setSettings] = useState(null);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [running, setRunning] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [sugMeta, setSugMeta] = useState(null);
  const [sugFilter, setSugFilter] = useState('pending');
  const [sugLoading, setSugLoading] = useState(false);
  const [events, setEvents] = useState([]);
  const [showEvents, setShowEvents] = useState(false);
  const [actionLoading, setActionLoading] = useState({});
  const [showSettings, setShowSettings] = useState(false);

  // Local edit of settings
  const [draft, setDraft] = useState(null);

  const fetchSettings = useCallback(async () => {
    setSettingsLoading(true);
    try {
      const res = await axios.get(`${API}/api/marketing/advanced-ai/pricing/settings`, { headers: authH });
      if (res.data.success) { setSettings(res.data.data); setDraft(res.data.data); }
    } catch (e) { toast({ title: 'Gagal load settings', variant: 'destructive' }); }
    finally { setSettingsLoading(false); }
  }, [authH]); // eslint-disable-line

  const saveSettings = async () => {
    setSavingSettings(true);
    try {
      const res = await axios.put(`${API}/api/marketing/advanced-ai/pricing/settings`, draft, { headers: authH });
      if (res.data.success) { setSettings(res.data.data); toast({ title: 'Settings disimpan ✓' }); setShowSettings(false); }
    } catch (e) { toast({ title: 'Gagal simpan', variant: 'destructive' }); }
    finally { setSavingSettings(false); }
  };

  const toggleEnabled = async (val) => {
    const updated = { ...settings, enabled: val };
    try {
      const res = await axios.put(`${API}/api/marketing/advanced-ai/pricing/settings`, { enabled: val }, { headers: authH });
      if (res.data.success) { setSettings(updated); setDraft(updated); }
      toast({ title: val ? '✅ Dynamic Pricing AKTIF' : '⏸️ Dynamic Pricing NONAKTIF' });
    } catch (e) { toast({ title: 'Gagal toggle', variant: 'destructive' }); }
  };

  const runSuggestions = async () => {
    setRunning(true);
    try {
      const res = await axios.post(`${API}/api/marketing/advanced-ai/pricing/run`, {}, { headers: authH });
      if (res.data.success) {
        toast({ title: `✨ ${res.data.metadata?.count || 0} suggestion dibuat!` });
        fetchSuggestions();
      }
    } catch (e) {
      toast({ title: 'Run gagal', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setRunning(false); }
  };

  const fetchSuggestions = useCallback(async () => {
    setSugLoading(true);
    try {
      const params = sugFilter !== 'all' ? { status: sugFilter } : {};
      const res = await axios.get(`${API}/api/marketing/advanced-ai/pricing/suggestions`, { params, headers: authH });
      if (res.data.success) { setSuggestions(res.data.data?.suggestions || []); setSugMeta(res.data.metadata); }
    } catch (e) {}
    finally { setSugLoading(false); }
  }, [authH, sugFilter]); // eslint-disable-line

  const doAction = async (id, action, reason = null) => {
    setActionLoading(l => ({ ...l, [id + action]: true }));
    try {
      let url = `${API}/api/marketing/advanced-ai/pricing/suggestions/${id}/${action}`;
      if (reason) url += `?reason=${encodeURIComponent(reason)}`;
      const res = await axios.post(url, {}, { headers: authH });
      if (res.data.success) {
        toast({ title: `Suggestion ${action === 'approve' ? 'disetujui' : action === 'reject' ? 'ditolak' : 'diterapkan'} ✓` });
        fetchSuggestions();
      }
    } catch (e) { toast({ title: 'Gagal', description: e.response?.data?.detail, variant: 'destructive' }); }
    finally { setActionLoading(l => ({ ...l, [id + action]: false })); }
  };

  const fetchEvents = async () => {
    try {
      const res = await axios.get(`${API}/api/marketing/advanced-ai/pricing/events`, { headers: authH });
      if (res.data.success) setEvents(res.data.data?.events || []);
    } catch (e) {}
  };

  useEffect(() => { fetchSettings(); }, [fetchSettings]);
  useEffect(() => { fetchSuggestions(); }, [fetchSuggestions]);

  if (settingsLoading) return <div className="flex justify-center py-16"><Loader2 className="animate-spin text-muted-foreground" size={28} /></div>;

  const isEnabled = settings?.enabled;

  return (
    <div className="space-y-5">
      {/* Control Card */}
      <Card className={`border-2 transition-colors ${isEnabled ? 'border-emerald-400 dark:border-emerald-600' : 'border-border dark:border-slate-700'}`}>
        <CardContent className="pt-5">
          <div className="flex flex-col sm:flex-row sm:items-center gap-4">
            <div className="flex items-center gap-4 flex-1">
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${ isEnabled ? 'bg-emerald-100 dark:bg-emerald-900/30' : 'bg-muted dark:bg-slate-800' }`}>
                {isEnabled ? <Power size={22} className="text-emerald-600" /> : <PowerOff size={22} className="text-muted-foreground" />}
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h3 className="font-bold text-lg">Dynamic Pricing</h3>
                  <Switch
                    checked={isEnabled || false}
                    onCheckedChange={toggleEnabled}
                    className="data-[state=checked]:bg-emerald-500"
                    data-testid="pricing-toggle"
                  />
                  <Badge className={isEnabled ? 'bg-emerald-100 text-emerald-700' : 'bg-muted text-muted-foreground'}>
                    {isEnabled ? 'AKTIF' : 'NONAKTIF'}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground mt-0.5">
                  Mode: <span className="font-medium capitalize">{settings?.mode?.replace('_', ' ')}</span>
                  {' · '} Min margin: <span className="font-medium">{settings?.min_margin_pct_global}%</span>
                  {' · '} Max perubahan: <span className="font-medium">↑{settings?.max_price_increase_pct_per_run}% / ↓{settings?.max_price_decrease_pct_per_run}%</span>
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowSettings(true)} data-testid="pricing-settings-btn">
                <Settings size={13} className="mr-1" /> Konfigurasi
              </Button>
              <Button size="sm" onClick={runSuggestions} disabled={!isEnabled || running} data-testid="run-pricing-btn">
                {running ? <Loader2 size={13} className="mr-1 animate-spin" /> : <Zap size={13} className="mr-1" />}
                {running ? 'Menganalisis...' : 'Generate Suggestions'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Guardrails Info */}
      {isEnabled && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Min Margin', value: `${settings?.min_margin_pct_global}%`, icon: Shield, color: 'text-blue-600' },
            { label: 'Max Naik/Run', value: `+${settings?.max_price_increase_pct_per_run}%`, icon: ArrowUp, color: 'text-emerald-600' },
            { label: 'Max Turun/Run', value: `-${settings?.max_price_decrease_pct_per_run}%`, icon: ArrowDown, color: 'text-red-600' },
            { label: 'Pembulatan', value: `Rp ${fmt(settings?.rounding_rule)}`, icon: Target, color: 'text-violet-600' },
          ].map(item => (
            <div key={item.label} className="rounded-lg border p-3 bg-muted/30">
              <div className="flex items-center gap-2 mb-1">
                <item.icon size={14} className={item.color} />
                <span className="text-xs text-muted-foreground">{item.label}</span>
              </div>
              <p className={`text-lg font-bold ${item.color}`}>{item.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Suggestions Table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <CardTitle className="flex-1">Pricing Suggestions</CardTitle>
            <div className="flex items-center gap-2">
              <Select value={sugFilter} onValueChange={setSugFilter}>
                <SelectTrigger className="w-[140px] h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua</SelectItem>
                  <SelectItem value="pending">Menunggu</SelectItem>
                  <SelectItem value="approved">Disetujui</SelectItem>
                  <SelectItem value="applied">Diterapkan</SelectItem>
                  <SelectItem value="rejected">Ditolak</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="ghost" size="sm" className="h-8" onClick={fetchSuggestions}>
                <RefreshCw size={13} />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {sugLoading ? (
            <div className="flex justify-center py-12"><Loader2 className="animate-spin text-muted-foreground" size={22} /></div>
          ) : suggestions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
              <DollarSign size={32} className="opacity-30" />
              <p className="text-sm">
                {isEnabled ? 'Belum ada suggestions. Klik "Generate Suggestions" untuk memulai.' : 'Aktifkan Dynamic Pricing untuk generate suggestions.'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    {['Produk', 'Harga Saat Ini', 'Harga Saran', 'Perubahan', 'Confidence', 'Alasan Utama', 'Status', 'Aksi'].map(h => (
                      <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {suggestions.map(s => {
                    const dirCfg = DIR_CONFIG[s.direction] || DIR_CONFIG.hold;
                    const stsCfg = STATUS_CONFIG[s.status] || STATUS_CONFIG.pending;
                    const DirIcon = dirCfg.icon;
                    return (
                      <tr key={s.id} className="hover:bg-muted/30 transition-colors">
                        <td className="px-3 py-2.5 font-medium text-sm max-w-[180px] truncate" title={s.product}>{s.product}</td>
                        <td className="px-3 py-2.5 tabular-nums text-sm">{fmtRp(s.current_price_rp)}</td>
                        <td className="px-3 py-2.5">
                          <span className={`font-bold tabular-nums ${dirCfg.color}`}>{fmtRp(s.suggested_price_rp)}</span>
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${dirCfg.bg} ${dirCfg.color}`}>
                            <DirIcon size={11} />{s.direction === 'increase' ? '+' : s.direction === 'decrease' ? '-' : ''}{Math.abs(s.change_pct || 0).toFixed(1)}%
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <Badge variant="outline" className={`text-xs ${
                            s.confidence === 'high' ? 'border-emerald-400 text-emerald-600' :
                            s.confidence === 'low' ? 'border-border text-muted-foreground/60' : 'border-amber-400 text-amber-600'
                          }`}>{s.confidence}</Badge>
                        </td>
                        <td className="px-3 py-2.5 text-xs text-muted-foreground max-w-[200px]">
                          <span className="truncate block" title={s.primary_reason}>{s.primary_reason}</span>
                        </td>
                        <td className="px-3 py-2.5">
                          <Badge className={`text-xs ${stsCfg.color}`}>{stsCfg.label}</Badge>
                        </td>
                        <td className="px-3 py-2.5">
                          {s.status === 'pending' && (
                            <div className="flex items-center gap-1">
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-emerald-600 hover:bg-emerald-50"
                                onClick={() => doAction(s.id, 'approve')} disabled={actionLoading[s.id + 'approve']}>
                                {actionLoading[s.id + 'approve'] ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={13} />}
                              </Button>
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-blue-600 hover:bg-blue-50"
                                onClick={() => doAction(s.id, 'apply')} disabled={actionLoading[s.id + 'apply']}>
                                {actionLoading[s.id + 'apply'] ? <Loader2 size={11} className="animate-spin" /> : <Zap size={13} />}
                              </Button>
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-red-500 hover:bg-red-50"
                                onClick={() => doAction(s.id, 'reject')} disabled={actionLoading[s.id + 'reject']}>
                                {actionLoading[s.id + 'reject'] ? <Loader2 size={11} className="animate-spin" /> : <XCircle size={13} />}
                              </Button>
                            </div>
                          )}
                          {s.status === 'approved' && (
                            <Button size="sm" className="h-7 px-2 text-xs" onClick={() => doAction(s.id, 'apply')} disabled={actionLoading[s.id + 'apply']}>
                              {actionLoading[s.id + 'apply'] ? <Loader2 size={11} className="animate-spin" /> : 'Terapkan'}
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {sugMeta && sugMeta.total > 0 && (
            <div className="px-4 py-2 border-t">
              <span className="text-xs text-muted-foreground">{sugMeta.total} total suggestions</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Audit Log Toggle */}
      <Button
        variant="ghost" size="sm" className="text-muted-foreground"
        onClick={() => { setShowEvents(v => !v); if (!showEvents) fetchEvents(); }}
      >
        <History size={13} className="mr-1" />
        {showEvents ? 'Sembunyikan' : 'Lihat'} Audit Log
        {showEvents ? <ChevronUp size={13} className="ml-1" /> : <ChevronDown size={13} className="ml-1" />}
      </Button>
      {showEvents && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Audit Log</CardTitle></CardHeader>
          <CardContent className="p-0">
            {events.length === 0 ? <p className="text-xs text-muted-foreground text-center py-6">Belum ada event</p> : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead><tr className="border-b bg-muted/30">
                    {['Waktu', 'Event', 'Produk', 'Detail', 'Actor'].map(h => (
                      <th key={h} className="px-3 py-1.5 text-left font-semibold text-muted-foreground">{h}</th>
                    ))}
                  </tr></thead>
                  <tbody className="divide-y">
                    {events.map(ev => (
                      <tr key={ev.id} className="hover:bg-muted/20">
                        <td className="px-3 py-1.5 text-muted-foreground">{new Date(ev.created_at).toLocaleString('id-ID', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' })}</td>
                        <td className="px-3 py-1.5">
                          <Badge className={`text-xs ${
                            ev.event_type === 'apply' ? 'bg-emerald-100 text-emerald-700' :
                            ev.event_type === 'approve' ? 'bg-blue-100 text-blue-700' :
                            ev.event_type === 'reject' ? 'bg-red-100 text-red-700' : 'bg-muted text-muted-foreground'
                          }`}>{ev.event_type}</Badge>
                        </td>
                        <td className="px-3 py-1.5 font-medium">{ev.product || '—'}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">
                          {ev.event_type === 'apply' && ev.old_price_rp ? `${fmtRp(ev.old_price_rp)} → ${fmtRp(ev.new_price_rp)}` :
                           ev.reason ? `Alasan: ${ev.reason}` : `${ev.suggestions_count || ''} suggestions`}
                        </td>
                        <td className="px-3 py-1.5 text-muted-foreground">{ev.actor}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Settings Dialog */}
      <Dialog open={showSettings} onOpenChange={setShowSettings}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Settings size={18} className="text-primary" /> Konfigurasi Dynamic Pricing</DialogTitle>
            <DialogDescription>Atur guardrails dan mode operasional. Perubahan berlaku langsung.</DialogDescription>
          </DialogHeader>
          {draft && (
            <div className="space-y-4">
              {/* Mode */}
              <div>
                <Label className="text-xs font-semibold">Mode Operasional</Label>
                <Select value={draft.mode || 'suggest_only'} onValueChange={v => setDraft(d => ({ ...d, mode: v }))}>
                  <SelectTrigger className="mt-1 h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="suggest_only">Suggest Only (wajib approval manual)</SelectItem>
                    <SelectItem value="auto_apply">Auto Apply (terapkan otomatis setelah approved)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Guardrails */}
              <div className="p-3 bg-blue-50 dark:bg-blue-950/20 rounded-lg space-y-3">
                <p className="text-xs font-semibold text-blue-700 dark:text-blue-300 flex items-center gap-1"><Shield size={12} /> Guardrails Keamanan</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs">Min Margin (%)</Label>
                    <Input type="number" step="1" className="h-8 mt-0.5 text-sm" value={draft.min_margin_pct_global || ''}
                      onChange={e => setDraft(d => ({ ...d, min_margin_pct_global: Number(e.target.value) }))} />
                    <p className="text-xs text-muted-foreground mt-0.5">Margin minimum yang tidak boleh dilanggar</p>
                  </div>
                  <div>
                    <Label className="text-xs">Pembulatan Harga</Label>
                    <Select value={String(draft.rounding_rule || 500)} onValueChange={v => setDraft(d => ({ ...d, rounding_rule: Number(v) }))}>
                      <SelectTrigger className="h-8 mt-0.5 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="100">Rp 100</SelectItem>
                        <SelectItem value="500">Rp 500</SelectItem>
                        <SelectItem value="1000">Rp 1.000</SelectItem>
                        <SelectItem value="5000">Rp 5.000</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-xs">Max Kenaikan per Run (%)</Label>
                    <Input type="number" step="1" className="h-8 mt-0.5 text-sm" value={draft.max_price_increase_pct_per_run || ''}
                      onChange={e => setDraft(d => ({ ...d, max_price_increase_pct_per_run: Number(e.target.value) }))} />
                  </div>
                  <div>
                    <Label className="text-xs">Max Penurunan per Run (%)</Label>
                    <Input type="number" step="1" className="h-8 mt-0.5 text-sm" value={draft.max_price_decrease_pct_per_run || ''}
                      onChange={e => setDraft(d => ({ ...d, max_price_decrease_pct_per_run: Number(e.target.value) }))} />
                  </div>
                  <div>
                    <Label className="text-xs">Cooldown antar Run (menit)</Label>
                    <Input type="number" step="5" className="h-8 mt-0.5 text-sm" value={draft.run_cooldown_minutes || ''}
                      onChange={e => setDraft(d => ({ ...d, run_cooldown_minutes: Number(e.target.value) }))} />
                  </div>
                </div>
              </div>

              {/* Exclude SKU */}
              <div>
                <Label className="text-xs font-semibold">Exclude SKU (pisah dengan koma)</Label>
                <Input className="mt-1 h-9 text-sm" placeholder="SKU001, SKU002, ..."
                  value={(draft.exclude_skus || []).join(', ')}
                  onChange={e => setDraft(d => ({ ...d, exclude_skus: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))} />
              </div>

              <div className="flex items-center gap-2 p-3 bg-amber-50 dark:bg-amber-950/20 rounded-lg">
                <Info size={14} className="text-amber-600 shrink-0" />
                <p className="text-xs text-amber-700 dark:text-amber-300">
                  Perubahan harga tidak otomatis ke platform marketplace sampai Phase 4 (Direct API) aktif. Saat ini bersifat <strong>internal suggestion only</strong>.
                </p>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSettings(false)}>Batal</Button>
            <Button onClick={saveSettings} disabled={savingSettings}>
              {savingSettings ? <Loader2 size={13} className="mr-1 animate-spin" /> : <Save size={13} className="mr-1" />}
              Simpan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
// TAB 2: CHURN PREDICTION
// ─────────────────────────────────────────────────────────────────
function ChurnPredictionTab({ authH }) {
  const { toast } = useToast();
  const [result, setResult] = useState(null);
  const [savedScores, setSavedScores] = useState([]);
  const [scoresLoading, setScoresLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [riskFilter, setRiskFilter] = useState('all');
  const [expandedCustomer, setExpandedCustomer] = useState(null);

  const fetchSavedScores = useCallback(async () => {
    setScoresLoading(true);
    try {
      const params = riskFilter !== 'all' ? { risk: riskFilter } : {};
      const res = await axios.get(`${API}/api/marketing/advanced-ai/churn/scores`, { params, headers: authH });
      if (res.data.success) setSavedScores(res.data.data?.customers || []);
    } catch (e) {}
    finally { setScoresLoading(false); }
  }, [authH, riskFilter]); // eslint-disable-line

  const runAnalysis = async () => {
    setAnalyzing(true);
    try {
      const res = await axios.post(`${API}/api/marketing/advanced-ai/churn/run`, {}, { headers: authH });
      if (res.data.success) {
        setResult(res.data.data);
        toast({ title: `✨ Analisis selesai! ${res.data.data.customers?.length || 0} customer dianalisis.` });
        fetchSavedScores();
      }
    } catch (e) {
      toast({ title: 'Analisis gagal', description: e.response?.data?.detail, variant: 'destructive' });
    } finally { setAnalyzing(false); }
  };

  useEffect(() => { fetchSavedScores(); }, [fetchSavedScores]);

  const customers = result?.customers || savedScores;
  const summary = result?.summary;
  const filtered = riskFilter === 'all' ? customers : customers.filter(c => c.churn_risk === riskFilter);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">Deteksi customer berisiko churn menggunakan RFM scoring + AI explanation</p>
        </div>
        <Button onClick={runAnalysis} disabled={analyzing} data-testid="run-churn-btn">
          {analyzing ? <Loader2 size={13} className="mr-1 animate-spin" /> : <Sparkles size={13} className="mr-1" />}
          {analyzing ? 'Menganalisis...' : result ? 'Refresh Analisis' : 'Jalankan Analisis'}
        </Button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Object.entries(summary.segments || {}).map(([risk, count]) => {
              const cfg = RISK_CONFIG[risk];
              const Icon = cfg.icon;
              return (
                <div key={risk} className={`rounded-xl border p-4 cursor-pointer transition-all ${cfg.color} ${ riskFilter === risk ? 'ring-2 ring-offset-1 ring-current' : '' }`}
                  onClick={() => setRiskFilter(riskFilter === risk ? 'all' : risk)}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium capitalize">{cfg.label}</span>
                    <Icon size={14} />
                  </div>
                  <p className="text-3xl font-bold tabular-nums">{count}</p>
                  <p className="text-xs opacity-70">customer</p>
                </div>
              );
            })}
          </div>

          {summary.general_strategy && (
            <Card className="bg-gradient-to-r from-violet-50 to-purple-50 dark:from-violet-950/30 dark:to-purple-950/30 border-violet-200 dark:border-violet-800">
              <CardContent className="pt-4">
                <div className="flex items-start gap-3">
                  <Brain size={18} className="text-violet-600 mt-0.5 shrink-0" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-violet-900 dark:text-violet-100">{summary.general_strategy}</p>
                    {summary.quick_wins?.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {summary.quick_wins.map((w, i) => (
                          <li key={i} className="flex items-center gap-1.5 text-xs text-violet-700 dark:text-violet-300">
                            <ChevronRight size={11} /> {w}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Customer Table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-3">
            <CardTitle className="flex-1">Daftar Customer
              {riskFilter !== 'all' && (
                <Badge className={`ml-2 text-xs ${RISK_CONFIG[riskFilter]?.color}`} onClick={() => setRiskFilter('all')} style={{ cursor: 'pointer' }}>
                  {RISK_CONFIG[riskFilter]?.label} <X size={10} className="ml-1" />
                </Badge>
              )}
            </CardTitle>
            <Select value={riskFilter} onValueChange={setRiskFilter}>
              <SelectTrigger className="w-[130px] h-8 text-xs"><SelectValue placeholder="Filter risk" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua</SelectItem>
                <SelectItem value="critical">Kritis</SelectItem>
                <SelectItem value="high">Tinggi</SelectItem>
                <SelectItem value="medium">Sedang</SelectItem>
                <SelectItem value="low">Rendah</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {scoresLoading || analyzing ? (
            <div className="flex justify-center py-12"><Loader2 className="animate-spin text-muted-foreground" size={22} /></div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3 text-muted-foreground">
              <Users size={32} className="opacity-30" />
              <p className="text-sm">{customers.length === 0 ? 'Klik "Jalankan Analisis" untuk memulai' : 'Tidak ada customer di filter ini'}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    {['Customer', 'Risk', 'Recency', 'Order', 'Total Belanja', 'RFM', 'Freq/Bulan', 'Rekomendasi AI'].map(h => (
                      <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {filtered.map(c => {
                    const rCfg = RISK_CONFIG[c.churn_risk] || RISK_CONFIG.low;
                    return (
                      <React.Fragment key={c.customer}>
                        <tr
                          className="hover:bg-muted/30 transition-colors cursor-pointer"
                          onClick={() => setExpandedCustomer(expandedCustomer === c.customer ? null : c.customer)}
                        >
                          <td className="px-3 py-2.5 font-medium">{c.customer}</td>
                          <td className="px-3 py-2.5">
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${rCfg.color}`}>
                              <span className={`w-1.5 h-1.5 rounded-full ${rCfg.dot}`} />{rCfg.label}
                            </span>
                          </td>
                          <td className="px-3 py-2.5 tabular-nums text-xs">{c.recency_days}h lalu</td>
                          <td className="px-3 py-2.5 tabular-nums">{c.order_count}</td>
                          <td className="px-3 py-2.5 tabular-nums text-xs">{fmtRp(c.total_spent_rp)}</td>
                          <td className="px-3 py-2.5">
                            <div className="flex items-center gap-0.5">
                              {['R', 'F', 'M'].map((l, i) => (
                                <span key={l} className={`w-5 h-5 rounded text-xs flex items-center justify-center font-bold ${
                                  [c.r_score, c.f_score, c.m_score][i] >= 4 ? 'bg-emerald-100 text-emerald-700' :
                                  [c.r_score, c.f_score, c.m_score][i] >= 3 ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'
                                }`}>{[c.r_score, c.f_score, c.m_score][i]}</span>
                              ))}
                            </div>
                          </td>
                          <td className="px-3 py-2.5 tabular-nums text-xs">{c.freq_per_month}x</td>
                          <td className="px-3 py-2.5 text-xs text-muted-foreground max-w-[200px]">
                            {c.ai_action ? (
                              <span className="truncate block" title={c.ai_action}>{c.ai_action}</span>
                            ) : <span className="text-muted-foreground">—</span>}
                          </td>
                        </tr>
                        {/* Expanded Row */}
                        {expandedCustomer === c.customer && c.ai_template && (
                          <tr>
                            <td colSpan={8} className="px-3 py-3 bg-muted/20">
                              <div className="flex items-start gap-2">
                                <div className="p-2 rounded bg-violet-100 dark:bg-violet-900/30">
                                  <Brain size={14} className="text-violet-600" />
                                </div>
                                <div className="flex-1">
                                  <p className="text-xs font-semibold text-violet-700 dark:text-violet-300 mb-1">
                                    Template Pesan — via {c.ai_channel || 'WA'}
                                  </p>
                                  <p className="text-xs text-muted-foreground italic whitespace-pre-wrap">{c.ai_template}</p>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
// TAB 3: A/B TESTING
// ─────────────────────────────────────────────────────────────────
function ABTestingTab({ authH }) {
  const { toast } = useToast();
  const [experiments, setExperiments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showRecord, setShowRecord] = useState(null);   // experiment
  const [concluding, setConcluding] = useState({});
  const [statusLoading, setStatusLoading] = useState({});
  const [filterStatus, setFilterStatus] = useState('all');

  // Create form
  const [form, setForm] = useState({
    name: '', hypothesis: '', test_type: 'content_hook', platform: 'tiktok',
    goal_metric: 'conversion', duration_days: 7,
    variantA: '', variantB: '', variantC: ''
  });
  const [creating, setCreating] = useState(false);

  // Record results form
  const [recordData, setRecordData] = useState({});
  const [recording, setRecording] = useState(false);

  const fetchExperiments = useCallback(async () => {
    setLoading(true);
    try {
      const params = filterStatus !== 'all' ? { status: filterStatus } : {};
      const res = await axios.get(`${API}/api/marketing/advanced-ai/ab-tests`, { params, headers: authH });
      if (res.data.success) setExperiments(res.data.data?.experiments || []);
    } catch (e) {}
    finally { setLoading(false); }
  }, [authH, filterStatus]); // eslint-disable-line

  useEffect(() => { fetchExperiments(); }, [fetchExperiments]);

  const createExperiment = async () => {
    if (!form.name || !form.hypothesis) {
      toast({ title: 'Nama dan hipotesis wajib diisi', variant: 'destructive' }); return;
    }
    setCreating(true);
    const variants = [
      form.variantA && { label: 'Variant A', content: form.variantA },
      form.variantB && { label: 'Variant B', content: form.variantB },
      form.variantC && { label: 'Variant C', content: form.variantC }
    ].filter(Boolean);
    try {
      const res = await axios.post(`${API}/api/marketing/advanced-ai/ab-tests`, {
        name: form.name, hypothesis: form.hypothesis, test_type: form.test_type,
        platform: form.platform, goal_metric: form.goal_metric,
        duration_days: form.duration_days, variants
      }, { headers: authH });
      if (res.data.success) {
        toast({ title: 'Eksperimen dibuat!' });
        setShowCreate(false);
        setForm({ name: '', hypothesis: '', test_type: 'content_hook', platform: 'tiktok', goal_metric: 'conversion', duration_days: 7, variantA: '', variantB: '', variantC: '' });
        fetchExperiments();
      }
    } catch (e) { toast({ title: 'Gagal buat eksperimen', description: e.response?.data?.detail, variant: 'destructive' }); }
    finally { setCreating(false); }
  };

  const changeStatus = async (exp, newStatus) => {
    setStatusLoading(l => ({ ...l, [exp.id]: true }));
    try {
      await axios.patch(`${API}/api/marketing/advanced-ai/ab-tests/${exp.id}/status?new_status=${newStatus}`, {}, { headers: authH });
      toast({ title: `Status diubah ke ${newStatus}` });
      fetchExperiments();
    } catch (e) { toast({ title: 'Gagal', description: e.response?.data?.detail, variant: 'destructive' }); }
    finally { setStatusLoading(l => ({ ...l, [exp.id]: false })); }
  };

  const concludeExp = async (exp) => {
    setConcluding(l => ({ ...l, [exp.id]: true }));
    try {
      const res = await axios.post(`${API}/api/marketing/advanced-ai/ab-tests/${exp.id}/conclude`, {}, { headers: authH });
      if (res.data.success) {
        toast({ title: `🏆 Pemenang: ${res.data.data?.winner_label}!` });
        fetchExperiments();
      }
    } catch (e) { toast({ title: 'Conclude gagal', description: e.response?.data?.detail, variant: 'destructive' }); }
    finally { setConcluding(l => ({ ...l, [exp.id]: false })); }
  };

  const openRecord = (exp) => {
    const init = {};
    exp.variants.forEach(v => { init[v.id] = { views: v.views || 0, clicks: v.clicks || 0, orders: v.orders || 0, revenue_rp: v.revenue_rp || 0, engagement: v.engagement || 0 }; });
    setRecordData(init);
    setShowRecord(exp);
  };

  const saveRecord = async () => {
    if (!showRecord) return;
    setRecording(true);
    try {
      for (const [variantId, data] of Object.entries(recordData)) {
        await axios.post(`${API}/api/marketing/advanced-ai/ab-tests/${showRecord.id}/record`, { variant_id: variantId, ...data }, { headers: authH });
      }
      toast({ title: 'Hasil disimpan!' });
      setShowRecord(null);
      fetchExperiments();
    } catch (e) { toast({ title: 'Gagal simpan hasil', variant: 'destructive' }); }
    finally { setRecording(false); }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Eksperimen konten & creative untuk menemukan kombinasi terbaik</p>
        <Button size="sm" onClick={() => setShowCreate(true)} data-testid="create-ab-btn">
          <Plus size={13} className="mr-1" /> Buat Eksperimen
        </Button>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2">
        {['all', 'draft', 'running', 'paused', 'concluded'].map(s => (
          <button key={s}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
              filterStatus === s ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-muted/80'
            }`}
            onClick={() => setFilterStatus(s)}
          >
            {s === 'all' ? 'Semua' : AB_STATUS[s]?.label || s}
          </button>
        ))}
      </div>

      {/* Experiments List */}
      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="animate-spin text-muted-foreground" size={24} /></div>
      ) : experiments.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
            <FlaskConical size={40} className="text-muted-foreground opacity-40" />
            <p className="font-medium">Belum ada eksperimen</p>
            <p className="text-sm text-muted-foreground">Buat eksperimen pertama untuk mulai mengoptimasi konten</p>
            <Button size="sm" onClick={() => setShowCreate(true)}><Plus size={13} className="mr-1" /> Buat Sekarang</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {experiments.map(exp => {
            const stsCfg = AB_STATUS[exp.status] || AB_STATUS.draft;
            const hasConcluded = exp.status === 'concluded';
            const hasData = exp.variants?.some(v => v.views > 0);
            return (
              <Card key={exp.id} className={hasConcluded ? 'border-violet-300 dark:border-violet-700' : ''}>
                <CardHeader className="pb-2">
                  <div className="flex flex-col sm:flex-row sm:items-start gap-2">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-semibold">{exp.name}</h3>
                        <Badge className={`text-xs ${stsCfg.color}`}>{stsCfg.label}</Badge>
                        <Badge variant="outline" className="text-xs capitalize">{exp.test_type?.replace(/_/g,' ')}</Badge>
                        <Badge variant="outline" className="text-xs">{exp.platform}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mt-0.5">{exp.hypothesis}</p>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {exp.status === 'draft' && (
                        <Button size="sm" variant="outline" className="h-8" onClick={() => changeStatus(exp, 'running')} disabled={statusLoading[exp.id]}>
                          {statusLoading[exp.id] ? <Loader2 size={11} className="animate-spin" /> : <Play size={12} className="mr-1" />}
                          Start
                        </Button>
                      )}
                      {exp.status === 'running' && (
                        <>
                          <Button size="sm" variant="outline" className="h-8" onClick={() => changeStatus(exp, 'paused')} disabled={statusLoading[exp.id]}>
                            <Pause size={12} className="mr-1" /> Pause
                          </Button>
                          <Button size="sm" variant="outline" className="h-8" onClick={() => openRecord(exp)}>
                            <Pencil size={12} className="mr-1" /> Input Hasil
                          </Button>
                          {hasData && (
                            <Button size="sm" className="h-8" onClick={() => concludeExp(exp)} disabled={concluding[exp.id]}>
                              {concluding[exp.id] ? <Loader2 size={11} className="animate-spin mr-1" /> : <Trophy size={12} className="mr-1" />}
                              Tentukan Pemenang
                            </Button>
                          )}
                        </>
                      )}
                      {exp.status === 'paused' && (
                        <>
                          <Button size="sm" variant="outline" className="h-8" onClick={() => changeStatus(exp, 'running')} disabled={statusLoading[exp.id]}>
                            <Play size={12} className="mr-1" /> Resume
                          </Button>
                          <Button size="sm" variant="outline" className="h-8" onClick={() => openRecord(exp)}>
                            <Pencil size={12} className="mr-1" /> Input Hasil
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  {/* Concluded Winner */}
                  {hasConcluded && exp.winner_label && (
                    <div className="mb-3 p-3 bg-violet-50 dark:bg-violet-950/20 rounded-lg flex items-start gap-2">
                      <Trophy size={16} className="text-violet-600 mt-0.5 shrink-0" />
                      <div>
                        <p className="text-sm font-bold text-violet-700 dark:text-violet-300">
                          Pemenang: {exp.winner_label}
                          {exp.improvement_pct && <span className="text-xs font-normal ml-2">({exp.improvement_pct}% lebih baik)</span>}
                        </p>
                        <p className="text-xs text-violet-600 dark:text-violet-400 mt-0.5">{exp.winner_reason}</p>
                        {exp.recommendation && (
                          <p className="text-xs text-muted-foreground mt-1 italic">Rekomendasi: {exp.recommendation}</p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Variants Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {exp.variants?.map(v => (
                      <div key={v.id}
                        className={`rounded-lg border p-3 ${
                          hasConcluded && exp.winner_variant_id === v.id
                            ? 'border-violet-400 bg-violet-50 dark:bg-violet-950/20'
                            : 'bg-muted/20'
                        }`}
                      >
                        <div className="flex items-center gap-1.5 mb-2">
                          <span className="font-semibold text-sm">{v.label}</span>
                          {hasConcluded && exp.winner_variant_id === v.id && (
                            <Trophy size={12} className="text-violet-600" />
                          )}
                        </div>
                        {v.content && (
                          <p className="text-xs text-muted-foreground mb-2 line-clamp-2" title={v.content}>{v.content}</p>
                        )}
                        <div className="grid grid-cols-3 gap-1 text-xs">
                          <div><p className="text-muted-foreground">Views</p><p className="font-bold tabular-nums">{fmt(v.views)}</p></div>
                          <div><p className="text-muted-foreground">Clicks</p><p className="font-bold tabular-nums">{fmt(v.clicks)}</p></div>
                          <div><p className="text-muted-foreground">Orders</p><p className="font-bold tabular-nums">{fmt(v.orders)}</p></div>
                          <div><p className="text-muted-foreground">CTR</p><p className="font-bold tabular-nums">{fmtPct(v.ctr)}</p></div>
                          <div><p className="text-muted-foreground">Conv</p><p className="font-bold tabular-nums">{fmtPct(v.conversion_rate)}</p></div>
                          <div><p className="text-muted-foreground">Revenue</p><p className="font-bold tabular-nums text-xs">{fmtRp(v.revenue_rp)}</p></div>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Create Experiment Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><FlaskConical size={18} className="text-primary" /> Buat Eksperimen A/B</DialogTitle>
            <DialogDescription>Definisikan hipotesis, variants, dan goal metric.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-xs font-semibold">Nama Eksperimen *</Label>
              <Input className="mt-1 h-9" placeholder="cth: Hook Ramadan vs Generic" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            </div>
            <div>
              <Label className="text-xs font-semibold">Hipotesis *</Label>
              <Textarea className="mt-1 text-sm" rows={2} placeholder="cth: Hook yang menyebutkan nama hari raya akan meningkatkan CTR 20% vs hook generic"
                value={form.hypothesis} onChange={e => setForm(f => ({ ...f, hypothesis: e.target.value }))} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Tipe Test</Label>
                <Select value={form.test_type} onValueChange={v => setForm(f => ({ ...f, test_type: v }))}>
                  <SelectTrigger className="mt-1 h-9 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="content_hook">Content Hook</SelectItem>
                    <SelectItem value="product_title">Judul Produk</SelectItem>
                    <SelectItem value="pricing">Harga</SelectItem>
                    <SelectItem value="discount">Diskon</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Platform</Label>
                <Select value={form.platform} onValueChange={v => setForm(f => ({ ...f, platform: v }))}>
                  <SelectTrigger className="mt-1 h-9 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="tiktok">🎵 TikTok</SelectItem>
                    <SelectItem value="shopee">🛒 Shopee</SelectItem>
                    <SelectItem value="tokopedia">🟢 Tokopedia</SelectItem>
                    <SelectItem value="instagram">📸 Instagram</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Goal Metric</Label>
                <Select value={form.goal_metric} onValueChange={v => setForm(f => ({ ...f, goal_metric: v }))}>
                  <SelectTrigger className="mt-1 h-9 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="conversion">Conversion Rate</SelectItem>
                    <SelectItem value="ctr">CTR</SelectItem>
                    <SelectItem value="engagement">Engagement</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Durasi (hari)</Label>
                <Input type="number" min={1} max={30} className="mt-1 h-9 text-sm" value={form.duration_days}
                  onChange={e => setForm(f => ({ ...f, duration_days: Number(e.target.value) }))} />
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-semibold">Variants (min 2)</Label>
              {['A', 'B', 'C'].map((l, i) => (
                <div key={l}>
                  <Label className="text-xs text-muted-foreground">Variant {l}{i >= 2 ? ' (opsional)' : ' *'}</Label>
                  <Textarea rows={2} className="mt-0.5 text-sm" placeholder={`Isi konten / hook / judul variant ${l}`}
                    value={form[`variant${l}`]}
                    onChange={e => setForm(f => ({ ...f, [`variant${l}`]: e.target.value }))} />
                </div>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Batal</Button>
            <Button onClick={createExperiment} disabled={creating}>
              {creating ? <Loader2 size={13} className="mr-1 animate-spin" /> : <Plus size={13} className="mr-1" />}
              Buat Eksperimen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Record Results Dialog */}
      <Dialog open={!!showRecord} onOpenChange={() => setShowRecord(null)}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><BarChart3 size={18} className="text-primary" /> Input Hasil Eksperimen</DialogTitle>
            <DialogDescription>{showRecord?.name}</DialogDescription>
          </DialogHeader>
          {showRecord && (
            <div className="space-y-4">
              {showRecord.variants.map(v => (
                <div key={v.id} className="border rounded-lg p-3">
                  <p className="font-semibold text-sm mb-2">{v.label}</p>
                  {v.content && <p className="text-xs text-muted-foreground mb-2 italic line-clamp-2">{v.content}</p>}
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {[['views', 'Views'], ['clicks', 'Clicks'], ['orders', 'Orders'], ['revenue_rp', 'Revenue (Rp)'], ['engagement', 'Engagement']].map(([key, lbl]) => (
                      <div key={key}>
                        <Label className="text-xs">{lbl}</Label>
                        <Input type="number" min={0} className="h-8 mt-0.5 text-sm"
                          value={recordData[v.id]?.[key] ?? ''}
                          onChange={e => setRecordData(d => ({ ...d, [v.id]: { ...d[v.id], [key]: Number(e.target.value) } }))} />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowRecord(null)}>Batal</Button>
            <Button onClick={saveRecord} disabled={recording}>
              {recording ? <Loader2 size={13} className="mr-1 animate-spin" /> : <Save size={13} className="mr-1" />}
              Simpan Hasil
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
// MAIN MODULE
// ─────────────────────────────────────────────────────────────────
export default function AdvancedAIModule({ token }) {
  const [activeTab, setActiveTab] = useState('pricing');
  const authH = useMemo(() => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);
  const tabs = [
    { id: 'pricing',  label: 'Dynamic Pricing',    icon: DollarSign,   badge: null },
    { id: 'churn',    label: 'Churn Prediction',   icon: Users,        badge: null },
    { id: 'abtest',   label: 'A/B Testing',        icon: FlaskConical, badge: null }
  ];

  return (
    <div className="min-h-screen bg-background p-4 md:p-6" data-testid="advanced-ai-module">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Sparkles size={24} className="text-primary" />
          Advanced AI Features
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">Dynamic Pricing, Churn Prediction, A/B Testing</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-muted rounded-xl mb-6 overflow-x-auto">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all flex-1 justify-center whitespace-nowrap ${
              activeTab === t.id
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
            data-testid={`tab-${t.id}`}
          >
            <t.icon size={15} />{t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'pricing' && <DynamicPricingTab authH={authH} />}
      {activeTab === 'churn' && <ChurnPredictionTab authH={authH} />}
      {activeTab === 'abtest' && <ABTestingTab authH={authH} />}
    </div>
  );
}
