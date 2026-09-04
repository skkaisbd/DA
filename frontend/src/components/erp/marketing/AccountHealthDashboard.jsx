import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  TrendingUp, TrendingDown, Minus, AlertCircle, CheckCircle2,
  Activity, RefreshCw, Loader2, Upload, Camera, X,
  Save, Pencil, Info
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { useMarketingAccounts, getPlatformIcon } from '@/hooks/useMarketingAccounts';
import { useActiveMarketingAccount } from '@/hooks/useActiveMarketingAccount';
import { ActiveAccountBar } from './ActiveAccountBar';
import axios from 'axios';
// F10 (sesi #10) — timeline kesehatan akun dipakai rapat mingguan ⇒ wajib bisa diunduh.
import ExportCsvButton from '@/components/ui/export-csv-button';

const API = process.env.REACT_APP_BACKEND_URL;

const PLATFORM_ICONS = { shopee: '🛒', tiktok: '🎵', tokopedia: '🟢' };

function StatusBadge({ status }) {
  const configs = {
    healthy:  { label: 'Sehat', color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', icon: CheckCircle2 },
    warning:  { label: 'Perlu Perhatian', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300', icon: AlertCircle },
    critical: { label: 'Kritis', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300', icon: AlertCircle }
  };
  const cfg = configs[status] || configs.healthy;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
      <Icon size={11} />{cfg.label}
    </span>
  );
}

function TrendIndicator({ current, previous }) {
  if (!previous) return <Minus size={14} className="text-muted-foreground" />;
  const diff = current - previous;
  if (Math.abs(diff) < 0.5) return <Minus size={14} className="text-muted-foreground" />;
  return diff > 0 ? <TrendingUp size={14} className="text-emerald-600" /> : <TrendingDown size={14} className="text-red-600" />;
}

// ── OCR Screenshot Modal ──────────────────────────────────────────────
function OCRModal({ open, onClose, onSaved, token }) {
  const { toast } = useToast();
  const fileRef = useRef();
  const [step, setStep] = useState('upload');   // upload | review | saving
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [extracted, setExtracted] = useState(null);
  const [loading, setLoading] = useState(false);
  const [editData, setEditData] = useState({});
  const [selectedAccountId, setSelectedAccountId] = useState('');

  const authH = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }),
    [token]
  );
  const { accounts: masterAccounts, byId: accountById } = useMarketingAccounts(token);

  const selectedAccount = selectedAccountId ? accountById[selectedAccountId] : null;
  const platform = selectedAccount?.platform || 'shopee';
  const accountName = selectedAccount?.account_name || '';

  const reset = () => {
    setStep('upload'); setFile(null); setPreview(null);
    setExtracted(null); setEditData({}); setLoading(false);
    setSelectedAccountId('');
  };

  const handleClose = () => { reset(); onClose(); };

  const handleFile = (f) => {
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const runOCR = async () => {
    if (!file) return;
    if (!selectedAccountId) {
      toast({ title: 'Pilih akun dulu', description: 'Wajib pilih akun dari master sebelum upload screenshot.', variant: 'destructive' });
      return;
    }
    setLoading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('platform', platform);
      form.append('account_name', accountName);
      form.append('account_id', selectedAccountId);  // FK to master
      const res = await axios.post(`${API}/api/marketing/health/ocr-screenshot`, form, {
        headers: { ...authH, 'Content-Type': 'multipart/form-data' }
      });
      if (res.data.success) {
        setExtracted(res.data.data.extracted);
        // Inject account_id into edit data so save preserves link to master
        setEditData({ ...res.data.data.preview, account_id: selectedAccountId, account_name: accountName, platform });
        setStep('review');
        toast({ title: 'OCR berhasil!', description: 'Periksa hasil ekstraksi sebelum menyimpan.' });
      }
    } catch (e) {
      toast({ title: 'OCR gagal', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setStep('saving');
    try {
      await axios.post(`${API}/api/marketing/health/manual-snapshot`, editData, { headers: authH });
      toast({ title: 'Snapshot disimpan!', description: `Akun ${editData.account_name} berhasil ditambahkan.` });
      onSaved();
      handleClose();
    } catch (e) {
      toast({ title: 'Gagal simpan', description: e.response?.data?.detail, variant: 'destructive' });
      setStep('review');
    }
  };

  const numField = (key, label, unit = '') => (
    <div key={key}>
      <Label className="text-xs">{label}{unit && <span className="text-muted-foreground ml-1">({unit})</span>}</Label>
      <Input
        type="number" step="0.01" className="h-8 text-sm mt-0.5"
        value={editData[key] ?? ''}
        onChange={e => setEditData(d => ({ ...d, [key]: e.target.value === '' ? null : Number(e.target.value) }))}
      />
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Camera size={18} className="text-primary" />
            Import Screenshot Kesehatan Akun
          </DialogTitle>
          <DialogDescription>Upload screenshot dari Shopee/TikTok Seller Center. AI akan mengekstrak semua metric otomatis.</DialogDescription>
        </DialogHeader>

        {step === 'upload' && (
          <div className="space-y-4">
            {/* Master Account Selector */}
            <div>
              <Label className="text-xs">Pilih Akun dari Master *</Label>
              <Select value={selectedAccountId || ''} onValueChange={setSelectedAccountId}>
                <SelectTrigger className="h-9 mt-0.5" data-testid="health-ocr-account-select">
                  <SelectValue placeholder={masterAccounts.length === 0 ? 'Belum ada akun — buat di Manage Accounts' : 'Pilih akun...'} />
                </SelectTrigger>
                <SelectContent>
                  {masterAccounts.length === 0 && (
                    <SelectItem value="empty" disabled>Belum ada akun aktif</SelectItem>
                  )}
                  {masterAccounts.map(acc => (
                    <SelectItem key={acc.id} value={acc.id}>
                      {getPlatformIcon(acc.platform)} {acc.account_name} <span className="text-xs text-muted-foreground ml-1">({acc.platform})</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedAccount && (
                <p className="text-[11px] text-muted-foreground mt-1">
                  Platform: <strong>{platform}</strong> • Snapshot akan link ke akun ini sehingga health score otomatis terupdate.
                </p>
              )}
            </div>

            {/* Drop Zone */}
            <div
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                file ? 'border-primary bg-primary/5' : 'border-muted-foreground/30 hover:border-primary/50 hover:bg-muted/30'
              }`}
              onClick={() => fileRef.current?.click()}
              onDrop={handleDrop}
              onDragOver={e => e.preventDefault()}
              data-testid="ocr-dropzone"
            >
              {preview ? (
                <div className="relative inline-block">
                  <img src={preview} alt="preview" className="max-h-48 rounded-lg object-contain mx-auto" />
                  <button
                    className="absolute -top-2 -right-2 w-6 h-6 bg-destructive rounded-full flex items-center justify-center"
                    onClick={e => { e.stopPropagation(); setFile(null); setPreview(null); }}
                  >
                    <X size={12} className="text-foreground" />
                  </button>
                </div>
              ) : (
                <>
                  <Upload size={32} className="text-muted-foreground mx-auto mb-3" />
                  <p className="text-sm font-medium">Drag & drop screenshot atau klik untuk pilih</p>
                  <p className="text-xs text-muted-foreground mt-1">PNG, JPG, WEBP — maks 10MB</p>
                </>
              )}
              <input ref={fileRef} type="file" accept="image/*" className="hidden"
                onChange={e => handleFile(e.target.files[0])} />
            </div>

            <div className="flex items-start gap-2 p-3 bg-muted/50 rounded-lg">
              <Info size={14} className="text-muted-foreground mt-0.5 shrink-0" />
              <p className="text-xs text-muted-foreground">
                Screenshot dapat dari halaman <strong>Dashboard Kesehatan Toko</strong> di Shopee Seller Center atau
                halaman <strong>Kesehatan Akun</strong> di TikTok Seller Center.
                AI (Claude) akan membaca semua angka yang terlihat.
              </p>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={handleClose}>Batal</Button>
              <Button onClick={runOCR} disabled={!file || !selectedAccountId || loading} data-testid="run-ocr-btn">
                {loading ? <Loader2 size={14} className="mr-2 animate-spin" /> : <Camera size={14} className="mr-2" />}
                {loading ? 'Menganalisis...' : 'Analisis dengan AI'}
              </Button>
            </DialogFooter>
          </div>
        )}

        {step === 'review' && editData && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg">
              <CheckCircle2 size={16} className="text-emerald-600" />
              <p className="text-sm text-emerald-700 dark:text-emerald-300 font-medium">
                OCR berhasil! Periksa dan edit jika ada yang tidak tepat.
              </p>
            </div>

            {extracted?.extraction_notes && (
              <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
                <Info size={14} className="text-amber-600 mt-0.5 shrink-0" />
                <p className="text-xs text-amber-700 dark:text-amber-300">{extracted.extraction_notes}</p>
              </div>
            )}

            {/* Editable Fields */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Platform</Label>
                <Select value={editData.platform || 'shopee'} onValueChange={v => setEditData(d => ({ ...d, platform: v }))}>
                  <SelectTrigger className="h-8 mt-0.5 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="shopee">🛒 Shopee</SelectItem>
                    <SelectItem value="tiktok">🎵 TikTok</SelectItem>
                    <SelectItem value="tokopedia">🟢 Tokopedia</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Nama Akun</Label>
                <Input
                  className="h-8 mt-0.5 text-sm"
                  value={editData.account_name || ''}
                  onChange={e => setEditData(d => ({ ...d, account_name: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {numField('ses_score', 'SES Score')}
              {numField('rating_score', 'Rating Produk')}
              {numField('response_rate', 'Response Rate', '%')}
              {numField('response_time_hours', 'Response Time', 'jam')}
              {numField('late_shipment_rate', 'Late Shipment', '%')}
              {numField('cancellation_rate', 'Cancellation Rate', '%')}
              {numField('order_defect_rate', 'Order Defect Rate', '%')}
              {numField('return_rate', 'Return Rate', '%')}
              {numField('total_reviews', 'Total Reviews')}
            </div>

            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={() => setStep('upload')}>
                <Camera size={14} className="mr-2" /> Upload Ulang
              </Button>
              <Button onClick={handleSave} disabled={!editData.account_name} data-testid="save-snapshot-btn">
                <Save size={14} className="mr-2" /> Simpan Snapshot
              </Button>
            </DialogFooter>
          </div>
        )}

        {step === 'saving' && (
          <div className="flex flex-col items-center justify-center py-12 gap-3">
            <Loader2 className="animate-spin text-primary" size={32} />
            <p className="text-sm text-muted-foreground">Menyimpan snapshot...</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ── Main Component ────────────────────────────────────────────────────
export default function AccountHealthDashboard({ token }) {
  const { toast } = useToast();
  const { activeAccount, setActiveAccount } = useActiveMarketingAccount();
  const { accounts: masterAccounts } = useMarketingAccounts(token);
  const [summary, setSummary] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [loading, setLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [showOCR, setShowOCR] = useState(false);

  const [platformFilter, setPlatformFilter] = useState('');
  const [accountFilter, setAccountFilter] = useState('');
  const [accounts, setAccounts] = useState([]);
  const [days, setDays] = useState(90);

  const authH = { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` };

  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const res = await axios.get(`${API}/api/marketing/health/summary`, { headers: authH });
      if (res.data.success) setSummary(res.data.data);
    } catch (e) {
      toast({ title: 'Gagal load summary', variant: 'destructive' });
    } finally {
      setSummaryLoading(false);
    }
  }, [token]); // eslint-disable-line

  const fetchTimeline = useCallback(async () => {
    setLoading(true);
    try {
      const params = { days };
      if (platformFilter) params.platform = platformFilter;
      if (accountFilter) params.account = accountFilter;
      const res = await axios.get(`${API}/api/marketing/health/timeline`, { params, headers: authH });
      if (res.data.success) setTimeline(res.data.data.snapshots || []);
    } catch (e) {
      toast({ title: 'Gagal load timeline', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [days, platformFilter, accountFilter, token]); // eslint-disable-line

  const fetchAccounts = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/marketing/health/accounts`, { headers: authH });
      if (res.data.success) setAccounts(res.data.data.accounts || []);
    } catch (e) {}
  }, [token]); // eslint-disable-line

  const onSaved = () => { fetchSummary(); fetchTimeline(); fetchAccounts(); };

  useEffect(() => { fetchSummary(); fetchAccounts(); }, [fetchSummary, fetchAccounts]);
  useEffect(() => { fetchTimeline(); }, [fetchTimeline]);

  const kpis = [
    { label: 'Total Akun',        value: summary?.total_accounts || 0, color: 'text-indigo-600',  bg: 'bg-indigo-50 dark:bg-indigo-900/20',   icon: Activity },
    { label: 'Sehat',             value: summary?.healthy || 0,         color: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-900/20', icon: CheckCircle2 },
    { label: 'Perlu Perhatian',   value: summary?.warning || 0,         color: 'text-amber-600',   bg: 'bg-amber-50 dark:bg-amber-900/20',    icon: AlertCircle },
    { label: 'Kritis',            value: summary?.critical || 0,        color: 'text-red-600',     bg: 'bg-red-50 dark:bg-red-900/20',        icon: AlertCircle },
  ];

  return (
    <div className="min-h-screen bg-background p-4 md:p-6" data-testid="health-dashboard">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Kesehatan Akun Marketplace</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Monitor SES score, late shipment, cancellation rate</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="default" size="sm" onClick={() => setShowOCR(true)} data-testid="import-screenshot-btn">
            <Camera size={13} className="mr-1" /> Import Screenshot
          </Button>
          <Button variant="outline" size="sm" onClick={() => { fetchSummary(); fetchTimeline(); }}>
            <RefreshCw size={13} className="mr-1" /> Refresh
          </Button>
        </div>
      </div>

      {/* Active Account Bar */}
      <div className="mb-4">
        <ActiveAccountBar
          accounts={masterAccounts}
          activeAccount={activeAccount}
          onAccountChange={(acc) => {
            setActiveAccount(acc);
            setAccountFilter(acc ? acc.account_name : '');
          }}
          hint="Filter health data by akun:"
        />
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        {kpis.map(k => (
          <div key={k.label} className={`rounded-xl border p-4 ${k.bg}`}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-muted-foreground font-medium">{k.label}</span>
              <k.icon size={15} className={k.color} />
            </div>
            <p className={`text-3xl font-bold tabular-nums ${k.color}`}>{summaryLoading ? '...' : k.value}</p>
          </div>
        ))}
      </div>

      {/* Timeline Table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <CardTitle className="flex-1">Timeline Kesehatan</CardTitle>
            <div className="flex items-center gap-2">
              <Select value={platformFilter || 'all'} onValueChange={v => setPlatformFilter(v === 'all' ? '' : v)}>
                <SelectTrigger className="w-[130px] h-9 text-xs"><SelectValue placeholder="Platform" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Platform</SelectItem>
                  <SelectItem value="shopee">🛒 Shopee</SelectItem>
                  <SelectItem value="tiktok">🎵 TikTok</SelectItem>
                  <SelectItem value="tokopedia">🟢 Tokopedia</SelectItem>
                </SelectContent>
              </Select>
              <Select value={accountFilter || 'all'} onValueChange={v => setAccountFilter(v === 'all' ? '' : v)}>
                <SelectTrigger className="w-[160px] h-9 text-xs"><SelectValue placeholder="Akun" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Akun</SelectItem>
                  {accounts.map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={String(days)} onValueChange={v => setDays(Number(v))}>
                <SelectTrigger className="w-[100px] h-9 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="30">30 hari</SelectItem>
                  <SelectItem value="60">60 hari</SelectItem>
                  <SelectItem value="90">90 hari</SelectItem>
                </SelectContent>
              </Select>
              <ExportCsvButton
                filename="kesehatan-akun-toko"
                testId="health-export-csv"
                className="h-9"
                head={['Tanggal', 'Akun', 'Platform', 'SES Score', 'Late Ship %',
                  'Cancel %', 'Response Rate %', 'Status']}
                rows={(timeline || []).map((t) => [
                  String(t.snapshot_date || '').slice(0, 10), t.account_name, t.platform,
                  t.ses_score, t.late_shipment_rate, t.cancellation_rate,
                  t.response_rate, t.status])}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center h-48"><Loader2 className="animate-spin text-muted-foreground" size={24} /></div>
          ) : timeline.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-muted-foreground gap-3">
              <Activity size={32} className="opacity-30" />
              <p className="text-sm">Tidak ada data kesehatan</p>
              <Button size="sm" variant="outline" onClick={() => setShowOCR(true)}>
                <Camera size={13} className="mr-1" /> Import Screenshot Pertama
              </Button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    {['Tanggal', 'Akun', 'Platform', 'SES Score', 'Late Ship %', 'Cancel %', 'Response Rate', 'Status'].map(h => (
                      <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {timeline.map((snap, i) => {
                    const prev = timeline[i + 1];
                    return (
                      <tr key={snap.id} className="hover:bg-muted/30 transition-colors">
                        <td className="px-3 py-2 text-xs text-muted-foreground">
                          {new Date(snap.snapshot_date).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: '2-digit' })}
                        </td>
                        <td className="px-3 py-2 font-medium text-xs">
                          {snap.account_name}
                          {snap.source === 'manual' && <Badge variant="outline" className="ml-1 text-xs py-0">Manual</Badge>}
                        </td>
                        <td className="px-3 py-2 text-xs">
                          {PLATFORM_ICONS[snap.platform]} <span className="capitalize">{snap.platform}</span>
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-1">
                            <span className="font-bold tabular-nums">{snap.ses_score ?? '—'}</span>
                            <TrendIndicator current={snap.ses_score} previous={prev?.ses_score} />
                          </div>
                        </td>
                        <td className="px-3 py-2 tabular-nums text-xs">{snap.late_shipment_rate != null ? `${snap.late_shipment_rate}%` : '—'}</td>
                        <td className="px-3 py-2 tabular-nums text-xs">{snap.cancellation_rate != null ? `${snap.cancellation_rate}%` : '—'}</td>
                        <td className="px-3 py-2 tabular-nums text-xs">{snap.response_rate != null ? `${snap.response_rate}%` : '—'}</td>
                        <td className="px-3 py-2"><StatusBadge status={snap.status} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* OCR Modal */}
      <OCRModal
        open={showOCR}
        onClose={() => setShowOCR(false)}
        onSaved={onSaved}
        token={token}
      />
    </div>
  );
}
