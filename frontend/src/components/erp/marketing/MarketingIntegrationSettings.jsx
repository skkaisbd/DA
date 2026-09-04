import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Settings, CheckCircle2, XCircle, Clock, Save, Trash2, Eye, EyeOff,
  ExternalLink, RefreshCw, Loader2, AlertTriangle, Zap, Bell, Info,
  ChevronDown, ChevronUp
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useToast } from '@/hooks/use-toast';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

const PLATFORM_COLORS = {
  shopee:    { ring: 'ring-orange-400/40', bg: 'from-orange-50 to-red-50 dark:from-orange-900/20 dark:to-red-900/20', badge: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300' },
  tiktok:    { ring: 'ring-border/40',   bg: 'from-gray-50 to-slate-50 dark:from-gray-900/20 dark:to-slate-900/20',   badge: 'bg-muted text-foreground dark:bg-gray-900/30 dark:text-gray-300' },
  tokopedia: { ring: 'ring-green-400/40',  bg: 'from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20', badge: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' },
};

function StatusBadge({ connected }) {
  return connected ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
      <CheckCircle2 size={10} />Terkonfigurasi
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground dark:bg-gray-800 dark:text-gray-400">
      <XCircle size={10} />Belum Dikonfigurasi
    </span>
  );
}

function PlatformCard({ platform, meta, config, onSave, onDisconnect, onTest }) {
  const [expanded, setExpanded]    = useState(false);
  const [form,     setForm]        = useState({});
  const [showPass, setShowPass]    = useState({});
  const [testing,  setTesting]     = useState(false);
  const [saving,   setSaving]      = useState(false);
  const [testResult, setTestResult]= useState(null);
  const colors = PLATFORM_COLORS[platform] || {};

  const handleSave = async () => {
    setSaving(true);
    const res = await onSave(platform, form);
    setSaving(false);
    setForm({});
    if (res) setExpanded(false);
  };

  const handleTest = async () => {
    setTesting(true);
    const res = await onTest(platform);
    setTestResult(res);
    setTesting(false);
  };

  const connected = config?.connected;

  return (
    <Card className={`ring-2 ${colors.ring || 'ring-border/40'} overflow-hidden`}>
      {/* Card header row */}
      <div className={`bg-gradient-to-r ${colors.bg || 'from-muted/30 to-muted/10'} p-4 flex items-center justify-between`}>
        <div className="flex items-center gap-3">
          <span className="text-2xl">{meta?.icon}</span>
          <div>
            <h3 className="font-bold text-sm">{meta?.name}</h3>
            <StatusBadge connected={connected} />
          </div>
        </div>
        <button onClick={() => setExpanded(e => !e)}
          className="flex items-center gap-1.5 text-xs font-medium text-primary hover:underline">
          {expanded ? <><ChevronUp size={14} />Tutup</> : <><ChevronDown size={14} />Konfigurasi</>}
        </button>
      </div>

      {/* Expanded config form */}
      {expanded && (
        <CardContent className="p-4 space-y-4 border-t">
          {/* Info banner */}
          <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 flex gap-2 text-sm">
            <Info size={14} className="text-blue-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-blue-700 dark:text-blue-300">Placeholder — Phase 4 Ready</p>
              <p className="text-xs text-blue-600 dark:text-blue-400 mt-0.5">{meta?.note}</p>
              {meta?.docs_url && (
                <a href={meta.docs_url} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline mt-1">
                  <ExternalLink size={10} />Dokumentasi API
                </a>
              )}
            </div>
          </div>

          {/* Fields */}
          <div className="grid grid-cols-1 gap-3">
            {(meta?.fields || []).map(field => (
              <div key={field.key}>
                <Label className="text-xs">{field.label}</Label>
                <div className="relative mt-1">
                  <Input
                    type={field.type === 'password' && !showPass[field.key] ? 'password' : 'text'}
                    placeholder={field.placeholder}
                    value={form[field.key] || ''}
                    onChange={e => setForm(f => ({...f, [field.key]: e.target.value}))}
                    className="pr-8"
                  />
                  {field.type === 'password' && (
                    <button type="button"
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      onClick={() => setShowPass(s => ({...s, [field.key]: !s[field.key]}))}
                    >
                      {showPass[field.key] ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  )}
                </div>
                {connected && config?.credentials?.[`_${field.key}_masked`] && (
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Tersimpan: <code className="font-mono bg-muted px-1 rounded">{config.credentials[`_${field.key}_masked`]}</code>
                  </p>
                )}
              </div>
            ))}
          </div>

          {/* Actions */}
          <div className="flex flex-wrap gap-2 pt-2 border-t">
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Save size={14} className="mr-1" />}
              Simpan
            </Button>
            <Button size="sm" variant="outline" onClick={handleTest} disabled={testing || !connected}>
              {testing ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Zap size={14} className="mr-1" />}
              Test Koneksi
            </Button>
            {connected && (
              <Button size="sm" variant="outline" className="text-red-500 hover:text-red-600 hover:border-red-300"
                onClick={() => { onDisconnect(platform); setExpanded(false); }}>
                <Trash2 size={14} className="mr-1" />Hapus Credentials
              </Button>
            )}
          </div>

          {/* Test result */}
          {testResult && (
            <div className={`p-3 rounded-lg text-sm flex gap-2 ${
              testResult.success
                ? 'bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300'
                : 'bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300'
            }`}>
              {testResult.success ? <CheckCircle2 size={14} className="flex-shrink-0 mt-0.5" /> : <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />}
              <div>
                <p className="font-medium">{testResult.message}</p>
                {testResult.note && <p className="text-xs opacity-75 mt-0.5">{testResult.note}</p>}
              </div>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}

const DEFAULT_ALERT_SETTINGS = {
  enabled: true,
  discount_expiry_days: 3,
  alert_content_today: true,
  alert_sla_breach: true,
  alert_expiring_discount: true,
  alert_upcoming_launch: true,
};

export default function MarketingIntegrationSettings({ token }) {
  const { toast } = useToast();
  const authH = useMemo(() => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);

  const [meta,           setMeta]           = useState({});
  const [configs,        setConfigs]        = useState({});
  const [alertSettings,  setAlertSettings]  = useState(DEFAULT_ALERT_SETTINGS);
  const [loading,        setLoading]        = useState(true);
  const [savingAlerts,   setSavingAlerts]   = useState(false);
  const [alertHistory,   setAlertHistory]   = useState([]);
  const [histLoading,    setHistLoading]    = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3] = await Promise.allSettled([
        axios.get(`${API}/api/marketing/integration-settings/meta`),
        axios.get(`${API}/api/marketing/integration-settings`, { headers: authH }),
        axios.get(`${API}/api/marketing/alerts/settings`, { headers: authH }),
      ]);
      if (r1.status === 'fulfilled') setMeta(r1.value.data.platforms || {});
      if (r2.status === 'fulfilled') setConfigs(r2.value.data.data || {});
      if (r3.status === 'fulfilled') setAlertSettings(s => ({...s, ...r3.value.data.data}));
    } catch {}
    finally { setLoading(false); }
  }, [authH]);

  const fetchHistory = useCallback(async () => {
    setHistLoading(true);
    try {
      const res = await axios.get(`${API}/api/marketing/alerts/history`, { headers: authH, params: { limit: 10 } });
      if (res.data.success) setAlertHistory(res.data.data || []);
    } catch {}
    finally { setHistLoading(false); }
  }, [authH]);

  useEffect(() => { fetchAll(); fetchHistory(); }, [fetchAll, fetchHistory]);

  const handleSavePlatform = async (platform, form) => {
    try {
      const res = await axios.put(`${API}/api/marketing/integration-settings/${platform}`,
        { credentials: form }, { headers: authH });
      if (res.data.success) {
        toast({ title: `✅ ${platform} credentials tersimpan` });
        fetchAll();
        return true;
      }
    } catch { toast({ title: 'Gagal menyimpan credentials', variant: 'destructive' }); }
    return false;
  };

  const handleDisconnect = async (platform) => {
    if (!window.confirm(`Hapus credentials ${platform}?`)) return;
    try {
      await axios.delete(`${API}/api/marketing/integration-settings/${platform}`, { headers: authH });
      toast({ title: `${platform} credentials dihapus` });
      fetchAll();
    } catch { toast({ title: 'Gagal hapus credentials', variant: 'destructive' }); }
  };

  const handleTestPlatform = async (platform) => {
    try {
      const res = await axios.post(`${API}/api/marketing/integration-settings/${platform}/test`, {}, { headers: authH });
      return res.data;
    } catch (e) {
      return { success: false, message: 'Koneksi gagal', note: e.message };
    }
  };

  const saveAlertSettings = async () => {
    setSavingAlerts(true);
    try {
      await axios.put(`${API}/api/marketing/alerts/settings`, alertSettings, { headers: authH });
      toast({ title: '✅ Alert settings disimpan' });
    } catch { toast({ title: 'Gagal simpan alert settings', variant: 'destructive' }); }
    finally { setSavingAlerts(false); }
  };

  const triggerNow = async () => {
    try {
      const res = await axios.post(`${API}/api/marketing/alerts/evaluate`, {}, { headers: authH });
      toast({ title: `🔔 ${res.data.total_fired} alert dikirim` });
      fetchHistory();
    } catch { toast({ title: 'Gagal trigger alerts', variant: 'destructive' }); }
  };

  if (loading) return (
    <div className="flex justify-center items-center py-24">
      <Loader2 size={32} className="animate-spin text-muted-foreground" />
    </div>
  );

  return (
    <div className="min-h-screen bg-background p-4 md:p-6" data-testid="integration-settings-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Settings size={22} className="text-primary" />Integration Settings
          </h1>
          <p className="text-sm text-muted-foreground">Kelola API credentials platform marketplace — siap untuk Phase 4 Direct API Integration</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { fetchAll(); fetchHistory(); }}>
          <RefreshCw size={14} className="mr-1" />Refresh
        </Button>
      </div>

      {/* Phase 4 Info Banner */}
      <div className="mb-6 p-4 rounded-xl border bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border-blue-200 dark:border-blue-800">
        <div className="flex gap-3">
          <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/40 flex-shrink-0">
            <Info size={16} className="text-blue-600" />
          </div>
          <div>
            <h3 className="font-semibold text-sm text-blue-800 dark:text-blue-200">Placeholder UI — Phase 4 Direct API Integration</h3>
            <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
              Halaman ini menyimpan credentials API untuk digunakan saat Phase 4 (Direct Sync: orders, inventory, ads).
              Saat ini belum ada koneksi real ke platform — simpan credentials Anda agar siap saat Phase 4 aktif.
            </p>
          </div>
        </div>
      </div>

      {/* Platform Integration Cards */}
      <h2 className="text-base font-semibold mb-3">🔗 Platform Connections</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        {Object.entries(meta).map(([platform, m]) => (
          <PlatformCard
            key={platform}
            platform={platform}
            meta={m}
            config={configs[platform]}
            onSave={handleSavePlatform}
            onDisconnect={handleDisconnect}
            onTest={handleTestPlatform}
          />
        ))}
      </div>

      {/* Alert Engine Settings */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Bell size={14} className="text-primary" />Marketing Alert Engine
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-2 space-y-4">
            {/* Master switch */}
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Alert Engine Aktif</p>
                <p className="text-xs text-muted-foreground">Jalankan evaluasi otomatis setiap 30 menit</p>
              </div>
              <Switch
                checked={alertSettings.enabled || false}
                onCheckedChange={v => setAlertSettings(s => ({...s, enabled: v}))}
              />
            </div>

            <div className="space-y-3 pt-2 border-t">
              {[
                { key: 'alert_expiring_discount', label: 'Diskon Akan Habis',    desc: `${alertSettings.discount_expiry_days} hari sebelum expired` },
                { key: 'alert_sla_breach',        label: 'SLA Komplain Breach',  desc: 'Komplain overdue / at risk' },
                { key: 'alert_upcoming_launch',   label: 'Upcoming Launch',      desc: 'H-7, H-3, H-1 sebelum launch' },
                { key: 'alert_content_today',     label: 'Konten Terjadwal Hari Ini', desc: 'Konten scheduled belum diposting' },
              ].map(item => (
                <div key={item.key} className="flex items-center justify-between">
                  <div>
                    <p className="text-sm">{item.label}</p>
                    <p className="text-xs text-muted-foreground">{item.desc}</p>
                  </div>
                  <Switch
                    checked={alertSettings[item.key] || false}
                    onCheckedChange={v => setAlertSettings(s => ({...s, [item.key]: v}))}
                  />
                </div>
              ))}
            </div>

            <div className="flex gap-2 pt-2 border-t">
              <Button size="sm" onClick={saveAlertSettings} disabled={savingAlerts}>
                {savingAlerts ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Save size={14} className="mr-1" />}
                Simpan Settings
              </Button>
              <Button size="sm" variant="outline" onClick={triggerNow}>
                <Zap size={14} className="mr-1" />Trigger Sekarang
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Alert History */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center justify-between">
              <div className="flex items-center gap-2"><Clock size={14} className="text-primary" />Riwayat Evaluasi</div>
              <button onClick={fetchHistory} className="text-xs text-muted-foreground hover:text-primary">
                {histLoading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              </button>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-2">
            {histLoading ? (
              <div className="flex justify-center py-6"><Loader2 size={20} className="animate-spin text-muted-foreground" /></div>
            ) : alertHistory.length === 0 ? (
              <div className="text-center py-6 text-muted-foreground">
                <Clock size={24} className="mx-auto mb-2 opacity-30" />
                <p className="text-sm">Belum ada riwayat evaluasi</p>
              </div>
            ) : (
              <div className="space-y-2">
                {alertHistory.map(run => (
                  <div key={run.id} className="flex items-center justify-between text-xs py-1.5 border-b last:border-0">
                    <div>
                      <span className="font-medium">{run.fired_count} alert</span>
                      <span className="text-muted-foreground ml-1">({(run.types || []).join(', ')})</span>
                    </div>
                    <span className="text-muted-foreground">{run.ran_at ? new Date(run.ran_at).toLocaleString('id-ID', {dateStyle:'short', timeStyle:'short'}) : ''}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
