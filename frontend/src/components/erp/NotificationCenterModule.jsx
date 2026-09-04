import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Bell, RefreshCw, Send, Trash2, RotateCw, AlertTriangle, Mail,
  MessageCircle, Clock, CheckCircle2, XCircle, Search, Calendar,
  PlayCircle, History, Settings, Zap, Wifi, WifiOff, TestTube, ChevronDown
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { PageHeader } from './moduleAtoms';
import { motion } from 'framer-motion';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const CHANNEL_ICON = { whatsapp: MessageCircle, email: Mail };
const STATUS_TONE = {
  queued:  'bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-400/25',
  sent:    'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-400/25',
  failed:  'bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-300 border-red-400/25',
};
const EVENT_LABEL = {
  sample_submitted:  'Sample Siap Approval',
  invoice_issued:    'Invoice Baru',
  invoice_overdue:   'Invoice Lewat Tempo',
  revision_requested:'Revisi Diminta',
  stage_change:      'Update Tahap Produksi',
  manual:            'Manual',
};

// ─── PROVIDER CONFIG FORM ─────────────────────────────────────────────────────
function ProviderConfigTab({ headers }) {
  const [cfg, setCfg] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [waOpen, setWaOpen] = useState(true);
  const [emailOpen, setEmailOpen] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/dewi/notifications/provider-config', { headers });
      if (r.ok) setCfg(await r.json());
    } finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      const r = await fetch('/api/dewi/notifications/provider-config', {
        method: 'PUT', headers,
        body: JSON.stringify(cfg),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal');
      toast.success('Konfigurasi provider disimpan');
      load();
    } catch (err) { toast.error(err.message); }
    finally { setSaving(false); }
  };

  const testSend = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await fetch('/api/dewi/notifications/provider-config/test', { method: 'POST', headers });
      const d = await r.json();
      setTestResult(d);
      if (d.whatsapp?.success || d.email?.success) toast.success('Test berhasil!');
      else toast.warning('Test gagal — lihat detail di bawah');
    } catch (err) { toast.error(err.message); }
    finally { setTesting(false); }
  };

  const F = ({ label, field, type='text', placeholder='' }) => (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <Input
        type={type}
        value={cfg[field] || ''}
        onChange={e => setCfg(p => ({...p, [field]: e.target.value}))}
        placeholder={placeholder}
        className="h-8 text-xs"
      />
    </div>
  );

  const Toggle = ({ label, field }) => (
    <div className="flex items-center justify-between">
      <Label className="text-xs cursor-pointer">{label}</Label>
      <button
        onClick={() => setCfg(p => ({...p, [field]: !p[field]}))}
        className={`relative w-8 h-4 rounded-full transition-colors ${
          cfg[field] ? 'bg-primary' : 'bg-foreground/[0.15]'
        }`}
      >
        <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${
          cfg[field] ? 'left-4.5' : 'left-0.5'
        }`} />
      </button>
    </div>
  );

  if (loading) return <div className="text-center py-8 text-foreground/40 text-sm">Memuat...</div>;

  return (
    <div className="space-y-5 max-w-xl">
      {/* Status banner */}
      <div className="grid grid-cols-2 gap-3">
        <div className={`rounded-xl border p-3 flex items-center gap-2.5 ${
          cfg.whatsapp_configured
            ? 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-500/25'
            : 'bg-foreground/[0.03] border-foreground/10'
        }`}>
          {cfg.whatsapp_configured
            ? <Wifi className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            : <WifiOff className="w-4 h-4 text-foreground/30" />}
          <div>
            <div className="text-xs font-semibold">
              {cfg.whatsapp_configured ? <span className="text-emerald-600 dark:text-emerald-300">WhatsApp Terkonfigurasi</span> : 'WhatsApp Belum Diatur'}
            </div>
            <div className="text-[10px] text-foreground/40">Fonnte API</div>
          </div>
        </div>
        <div className={`rounded-xl border p-3 flex items-center gap-2.5 ${
          cfg.email_configured
            ? 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-500/25'
            : 'bg-foreground/[0.03] border-foreground/10'
        }`}>
          {cfg.email_configured
            ? <Wifi className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            : <WifiOff className="w-4 h-4 text-foreground/30" />}
          <div>
            <div className="text-xs font-semibold">
              {cfg.email_configured ? <span className="text-emerald-600 dark:text-emerald-300">Email Terkonfigurasi</span> : 'Email Belum Diatur'}
            </div>
            <div className="text-[10px] text-foreground/40">SMTP</div>
          </div>
        </div>
      </div>

      {/* WhatsApp */}
      <GlassCard className="p-4 space-y-3">
        <button
          className="w-full flex items-center justify-between"
          onClick={() => setWaOpen(p => !p)}
        >
          <div className="flex items-center gap-2">
            <MessageCircle className="w-4 h-4 text-green-700 dark:text-green-400" />
            <span className="text-sm font-semibold">WhatsApp — Fonnte</span>
          </div>
          <ChevronDown className={`w-4 h-4 text-foreground/40 transition-transform ${
            waOpen ? 'rotate-180' : ''
          }`} />
        </button>
        {waOpen && (
          <div className="space-y-3 pt-1">
            <div className="text-xs text-foreground/50 bg-foreground/5 p-2 rounded">
              Daftar di <a href="https://fonnte.com" target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 underline">fonnte.com</a> untuk mendapatkan API key WhatsApp Business.
            </div>
            <Toggle label="Aktifkan WhatsApp" field="whatsapp_enabled" />
            <F label="API Key Fonnte" field="whatsapp_api_key" type="password" placeholder="Masukkan API key..." />
            <div className="grid grid-cols-2 gap-2">
              <F label="Kode Negara" field="whatsapp_country_code" placeholder="62" />
              <F label="Nomor Test" field="whatsapp_test_phone" placeholder="628xxxxxxxxx" />
            </div>
            <F label="Nama Pengirim" field="whatsapp_sender_name" placeholder="CV. Dewi Aditya" />
          </div>
        )}
      </GlassCard>

      {/* Email */}
      <GlassCard className="p-4 space-y-3">
        <button
          className="w-full flex items-center justify-between"
          onClick={() => setEmailOpen(p => !p)}
        >
          <div className="flex items-center gap-2">
            <Mail className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <span className="text-sm font-semibold">Email — SMTP</span>
          </div>
          <ChevronDown className={`w-4 h-4 text-foreground/40 transition-transform ${
            emailOpen ? 'rotate-180' : ''
          }`} />
        </button>
        {emailOpen && (
          <div className="space-y-3 pt-1">
            <div className="text-xs text-foreground/50 bg-foreground/5 p-2 rounded">
              Gunakan Gmail (smtp.gmail.com:587) atau SMTP provider lain. Untuk Gmail, aktifkan "App Password".
            </div>
            <Toggle label="Aktifkan Email" field="email_enabled" />
            <div className="grid grid-cols-2 gap-2">
              <F label="SMTP Host" field="smtp_host" placeholder="smtp.gmail.com" />
              <F label="Port" field="smtp_port" placeholder="587" />
            </div>
            {/* FASE 10 — mode keamanan eksplisit. Sebelumnya pengirim SELALU memaksa
                STARTTLS + login, sehingga relay internal (tanpa TLS / tanpa auth)
                tidak pernah bisa dipakai walau host & port sudah benar. */}
            <div className="space-y-1.5">
              <Label className="text-xs">Keamanan Koneksi</Label>
              <select
                value={cfg.smtp_security || 'starttls'}
                onChange={e => setCfg(p => ({ ...p, smtp_security: e.target.value }))}
                className="w-full h-8 text-xs rounded-md border border-border bg-[var(--card-surface)] px-2"
                data-testid="smtp-security-select"
              >
                <option value="starttls">STARTTLS — port 587 (umum: Gmail, Zoho, Outlook)</option>
                <option value="ssl">SSL/TLS — port 465</option>
                <option value="none">Tanpa enkripsi — relay/SMTP internal</option>
              </select>
              <div className="text-[11px] text-foreground/50">
                Username &amp; password boleh dikosongkan bila server mengizinkan relay tanpa autentikasi.
              </div>
            </div>
            <F label="Username (Email)" field="smtp_user" placeholder="demo@gmail.com" />
            <F label="Password / App Password" field="smtp_password" type="password" placeholder="*****" />
            <F label="From Email" field="smtp_from_email" placeholder="noreply@demo-erp.id" />
            <F label="From Name" field="smtp_from_name" placeholder="CV. Dewi Aditya" />
            <F label="Email Test" field="smtp_test_email" placeholder="test@email.com" />
          </div>
        )}
      </GlassCard>

      {/* FASE 10 — Rapor valuasi aksesoris otomatis (tanggal 1, 06:00 WIB) */}
      <GlassCard className="p-4 space-y-3">
        <div className="text-sm font-semibold flex items-center gap-2">
          <Mail className="w-4 h-4 text-sky-600 dark:text-sky-400" /> Rapor Valuasi Aksesoris Bulanan
        </div>
        <div className="text-xs text-foreground/50 bg-foreground/5 p-2 rounded">
          Setiap tanggal 1 pukul 06:00 WIB sistem mengirim rapor valuasi persediaan aksesoris
          periode bulan lalu (lampiran Excel + PDF) ke seluruh user ber-role keuangan.
          Detail penerima, riwayat kirim, dan tombol “kirim sekarang” ada di
          <strong> Aksesoris → Valuasi HPP</strong>.
        </div>
        <Toggle label="Kirim rapor otomatis setiap awal bulan" field="valuation_report_enabled" />
        <div className="space-y-1.5">
          <Label className="text-xs">Email tambahan (pisahkan dengan koma)</Label>
          <Input
            value={Array.isArray(cfg.valuation_report_extra_emails)
              ? cfg.valuation_report_extra_emails.join(', ')
              : (cfg.valuation_report_extra_emails || '')}
            onChange={e => setCfg(p => ({ ...p, valuation_report_extra_emails: e.target.value }))}
            placeholder="pajak@perusahaan.id, arsip@perusahaan.id"
            className="h-8 text-xs"
            data-testid="valuation-report-extra-emails"
          />
        </div>
      </GlassCard>

      {/* Event Subscriptions */}
      <GlassCard className="p-4 space-y-3">
        <div className="text-sm font-semibold flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-700 dark:text-amber-400" /> Auto-Notify Events
        </div>
        <div className="space-y-2">
          <Toggle label="Notifikasi saat stage maklon berubah" field="notify_on_stage_change" />
          <Toggle label="Notifikasi saat invoice diterbitkan" field="notify_on_invoice_issued" />
          <Toggle label="Notifikasi saat invoice overdue" field="notify_on_invoice_overdue" />
          <Toggle label="Notifikasi saat sample diupdate" field="notify_on_sample_update" />
        </div>
      </GlassCard>

      {/* Test result */}
      {testResult && (
        <motion.div initial={{ opacity:0,y:4 }} animate={{ opacity:1,y:0 }} className="space-y-2">
          {['whatsapp','email'].map(ch => (
            <div key={ch} className={`flex items-start gap-2 text-xs p-2.5 rounded-lg border ${
              testResult[ch]?.success
                ? 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-500/25 text-emerald-600 dark:text-emerald-300'
                : 'bg-red-100 dark:bg-red-500/10 border-red-500/25 text-red-600 dark:text-red-300'
            }`}>
              {testResult[ch]?.success
                ? <CheckCircle2 className="w-3.5 h-3.5 mt-0.5" />
                : <XCircle className="w-3.5 h-3.5 mt-0.5" />}
              <div>
                <div className="font-semibold capitalize">{ch}: {testResult[ch]?.success ? 'Berhasil' : 'Gagal'}</div>
                {testResult[ch]?.error && <div className="opacity-80">{testResult[ch].error}</div>}
              </div>
            </div>
          ))}
        </motion.div>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        <Button onClick={save} disabled={saving} className="flex-1">
          {saving ? 'Menyimpan...' : 'Simpan Konfigurasi'}
        </Button>
        <Button variant="outline" onClick={testSend} disabled={testing} className="gap-1.5">
          <TestTube className="w-3.5 h-3.5" />
          {testing ? 'Testing...' : 'Test Kirim'}
        </Button>
      </div>
    </div>
  );
}

// ─── MAIN MODULE ──────────────────────────────────────────────────────────────
export default function NotificationCenterModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterChannel, setFilterChannel] = useState('all');
  const [filterEvent, setFilterEvent] = useState('all');
  const [search, setSearch] = useState('');
  const [tab, setTab] = useState('notifications');
  const [scheduler, setScheduler] = useState(null);
  const [runs, setRuns] = useState([]);
  const [runningJob, setRunningJob] = useState(null);
  const [bulkSending, setBulkSending] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterStatus !== 'all') params.set('status', filterStatus);
      if (filterChannel !== 'all') params.set('channel', filterChannel);
      if (filterEvent !== 'all') params.set('event_type', filterEvent);
      const [r1, r2] = await Promise.all([
        fetch(`/api/dewi/notifications?${params}`, { headers }),
        fetch('/api/dewi/notifications/summary', { headers }),
      ]);
      if (r1.ok) setItems(await r1.json());
      if (r2.ok) setSummary(await r2.json());
    } finally { setLoading(false); }
  }, [filterStatus, filterChannel, filterEvent, headers]);

  useEffect(() => { load(); }, [load]);

  const loadScheduler = useCallback(async () => {
    try {
      const [r1, r2] = await Promise.all([
        fetch('/api/dewi/scheduler/jobs', { headers }),
        fetch('/api/dewi/scheduler/runs?limit=20', { headers }),
      ]);
      if (r1.ok) setScheduler(await r1.json());
      if (r2.ok) setRuns(await r2.json());
    } catch {}
  }, [headers]);

  useEffect(() => { if (tab === 'scheduler') loadScheduler(); }, [tab, loadScheduler]);

  const runJob = async (jobId) => {
    setRunningJob(jobId);
    try {
      const r = await fetch(`/api/dewi/scheduler/jobs/${jobId}/run-now`, { method: 'POST', headers });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal');
      toast.success(`${jobId} selesai. ${d.result?.notifs_queued ?? 0} notif baru.`);
      loadScheduler(); load();
    } catch (e) { toast.error(e.message); }
    finally { setRunningJob(null); }
  };

  const markSent = async (id) => {
    const r = await fetch(`/api/dewi/notifications/${id}/send`, { method: 'POST', headers });
    const d = await r.json();
    if (r.ok) {
      toast.success(d.real ? 'Dikirim via provider nyata!' : 'Ditandai terkirim (MOCK)');
      load();
    } else toast.error('Gagal');
  };

  const retry = async (id) => {
    const r = await fetch(`/api/dewi/notifications/${id}/retry`, { method: 'POST', headers });
    if (r.ok) { toast.success('Diqueue ulang'); load(); }
  };

  const remove = async (id) => {
    if (!window.confirm('Hapus notifikasi ini?')) return;
    const r = await fetch(`/api/dewi/notifications/${id}`, { method: 'DELETE', headers });
    if (r.ok) { toast.success('Dihapus'); load(); }
  };

  const bulkSend = async () => {
    setBulkSending(true);
    try {
      const r = await fetch('/api/dewi/notifications/bulk-send', { method: 'POST', headers });
      const d = await r.json();
      if (r.ok) {
        toast.success(`Bulk send: ${d.sent} terkirim, ${d.failed} gagal, ${d.skipped} skip`);
        load();
      }
    } catch (e) { toast.error(e.message); }
    finally { setBulkSending(false); }
  };

  const scanOverdue = async () => {
    const r = await fetch('/api/dewi/notifications/scan-overdue', { method: 'POST', headers });
    if (r.ok) {
      const d = await r.json();
      toast.success(`Scan selesai: ${d.queued} notif baru dari ${d.invoices_checked} invoice.`);
      load();
    }
  };

  const filtered = useMemo(() => items.filter(n => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (n.recipient||'').toLowerCase().includes(q) ||
           (n.body||'').toLowerCase().includes(q) ||
           (n.subject||'').toLowerCase().includes(q);
  }), [items, search]);

  const queuedCount = useMemo(() => items.filter(n => n.status === 'queued').length, [items]);

  const TABS = [
    { id: 'notifications', label: 'Notifikasi', icon: Bell },
    { id: 'config',        label: 'Konfigurasi Provider', icon: Settings },
    { id: 'scheduler',    label: 'Cron Scheduler', icon: Calendar },
  ];

  const { page, setPage, totalPages, total, paged } = useClientPagination(runs, 10);
  return (
    <div className="p-6 space-y-6" data-testid="notification-center">
      <PageHeader
        title="Notification Center"
        subtitle="Notifikasi otomatis ke klien (WhatsApp & Email) saat stage berubah, invoice terbit, dsb."
        icon={Bell}
        actions={
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={scanOverdue} className="gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" /> Scan Overdue
            </Button>
            {queuedCount > 0 && (
              <Button size="sm" variant="outline" onClick={bulkSend} disabled={bulkSending} className="gap-1.5">
                <Send className="w-3.5 h-3.5" />{bulkSending ? 'Sending...' : `Send All (${queuedCount})`}
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={load} className="gap-1.5">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </Button>
          </div>
        }
      />

      {/* Provider status banner */}
      {summary && (
        <div className={`rounded-xl border p-3 text-xs flex items-start gap-2 ${
          summary.whatsapp_configured || summary.email_configured
            ? 'border-emerald-400 dark:border-emerald-400/30 bg-emerald-50 dark:bg-emerald-400/5'
            : 'border-amber-400 dark:border-amber-400/30 bg-amber-50 dark:bg-amber-400/5'
        }`}>
          {summary.whatsapp_configured || summary.email_configured
            ? <Wifi className="w-4 h-4 text-emerald-600 dark:text-emerald-400 mt-0.5" />
            : <WifiOff className="w-4 h-4 text-amber-700 dark:text-amber-400 mt-0.5" />}
          <div className="flex-1">
            {summary.whatsapp_configured || summary.email_configured ? (
              <span className="text-emerald-200 font-medium">
                Provider aktif: {summary.whatsapp_configured ? 'WhatsApp (Fonnte) ' : ''}{summary.email_configured ? 'Email (SMTP)' : ''}
              </span>
            ) : (
              <div>
                <span className="font-medium text-amber-200">MODE MOCK aktif. </span>
                <span className="text-foreground/65">Notifikasi dicatat ke DB tapi belum dikirim nyata. </span>
                <button onClick={() => setTab('config')} className="text-amber-600 dark:text-amber-300 hover:text-amber-200 underline underline-offset-2 transition">
                  Klik di sini untuk konfigurasi provider &rarr;
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-foreground/10 flex gap-1">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            data-testid={`notif-tab-${t.id}`}
            className={`px-4 py-2 text-sm border-b-2 transition flex items-center gap-1.5 ${
              tab === t.id
                ? 'border-[hsl(var(--primary))] text-[hsl(var(--primary))] font-medium'
                : 'border-transparent text-foreground/60 hover:text-foreground'
            }`}>
            <t.icon className="w-3.5 h-3.5" />{t.label}
          </button>
        ))}
      </div>

      {tab === 'config' ? (
        <ProviderConfigTab headers={headers} />
      ) : tab === 'scheduler' ? (
        <div className="space-y-5">
          <div className={`rounded-xl border p-3 text-xs flex items-center gap-2 ${
            scheduler?.scheduler_running ? 'border-emerald-400 dark:border-emerald-400/30 bg-emerald-50 dark:bg-emerald-400/5 text-emerald-200' : 'border-red-400 dark:border-red-400/30 bg-red-50 dark:bg-red-400/5 text-red-200'
          }`}>
            <div className={`w-2 h-2 rounded-full ${scheduler?.scheduler_running ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'}`} />
            <span className="font-medium">{scheduler?.scheduler_running ? 'Scheduler aktif' : 'Scheduler nonaktif'}</span>
            {scheduler?.timezone && <span className="text-foreground/55">· {scheduler.timezone}</span>}
          </div>
          {scheduler?.jobs?.map(j => (
            <GlassCard key={j.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <code className="text-xs font-mono text-violet-600 dark:text-violet-300">{j.id}</code>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      j.enabled ? 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-300' : 'bg-foreground/10 text-foreground/55'
                    }`}>{j.enabled ? 'enabled' : 'disabled'}</span>
                  </div>
                  <p className="text-sm text-foreground/85">{j.description}</p>
                  <div className="text-xs text-foreground/55 mt-1 flex gap-3">
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{j.cron_label}</span>
                    {j.next_run_at && <span>Berikutnya: {new Date(j.next_run_at).toLocaleString('id-ID')}</span>}
                  </div>
                </div>
                <Button size="sm" variant="outline" disabled={runningJob === j.id || !j.enabled}
                  onClick={() => runJob(j.id)} className="gap-1.5">
                  <PlayCircle className="w-3.5 h-3.5" />
                  {runningJob === j.id ? 'Running...' : 'Run Now'}
                </Button>
              </div>
            </GlassCard>
          ))}
          {runs.length > 0 && (
            <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
              <table className="w-full text-xs">
                <thead className="bg-foreground/5 text-foreground/55">
                  <tr>
                    {['Job','Mulai','Status','Dur (ms)','Diperiksa','Notif'].map(h => (
                      <th key={h} className="text-left font-medium px-3 py-2">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {paged.map((r, i) => (
                    <tr key={i} className="border-t border-foreground/5">
                      <td className="px-3 py-2 font-mono text-violet-600 dark:text-violet-300">{r.job_id}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{new Date(r.started_at).toLocaleString('id-ID')}</td>
                      <td className="px-3 py-2">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                          r.status==='success' ? 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-300'
                          : r.status==='failed' ? 'bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-300'
                          : 'bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-300'
                        }`}>{r.status}</span>
                      </td>
                      <td className="px-3 py-2 text-right">{r.duration_ms ?? '-'}</td>
                      <td className="px-3 py-2 text-right">{r.invoices_checked ?? '-'}</td>
                      <td className="px-3 py-2 text-right">{r.notifs_queued ?? '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
            </div>
          )}
        </div>
      ) : (
        <>
          {/* Stats */}
          {summary && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <GlassCard className="p-3"><div className="text-[10px] uppercase text-foreground/45">Total</div><div className="text-2xl font-bold tabular-nums">{summary.total}</div></GlassCard>
              <GlassCard className="p-3 border-amber-300 dark:border-amber-400/20"><div className="text-[10px] uppercase text-amber-700 dark:text-amber-400 flex items-center gap-1"><Clock className="w-3 h-3" /> Queued</div><div className="text-2xl font-bold tabular-nums text-amber-600 dark:text-amber-300">{summary.by_status.queued}</div></GlassCard>
              <GlassCard className="p-3 border-emerald-300 dark:border-emerald-400/20"><div className="text-[10px] uppercase text-emerald-600 dark:text-emerald-400 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Sent</div><div className="text-2xl font-bold tabular-nums text-emerald-600 dark:text-emerald-300">{summary.by_status.sent}</div></GlassCard>
              <GlassCard className="p-3"><div className="text-[10px] uppercase text-foreground/45 flex items-center gap-1"><MessageCircle className="w-3 h-3" /> WhatsApp</div><div className="text-2xl font-bold tabular-nums">{summary.by_channel.whatsapp}</div></GlassCard>
              <GlassCard className="p-3"><div className="text-[10px] uppercase text-foreground/45 flex items-center gap-1"><Mail className="w-3 h-3" /> Email</div><div className="text-2xl font-bold tabular-nums">{summary.by_channel.email}</div></GlassCard>
            </div>
          )}
          {/* Filters */}
          <div className="flex flex-wrap gap-2 items-center">
            <div className="flex gap-1.5">
              {['all','queued','sent','failed'].map(s => (
                <Button key={s} size="sm" variant={filterStatus===s?'default':'outline'}
                  onClick={() => setFilterStatus(s)} data-testid={`notif-filter-status-${s}`}>
                  {s==='all'?'Semua':s}
                </Button>
              ))}
            </div>
            <div className="flex gap-1.5">
              {['all','whatsapp','email'].map(c => (
                <Button key={c} size="sm" variant={filterChannel===c?'default':'outline'}
                  onClick={() => setFilterChannel(c)}>
                  {c==='all'?'All':c}
                </Button>
              ))}
            </div>
            <div className="flex gap-1.5">
              {['all','stage_change','invoice_issued','invoice_overdue','manual'].map(e => (
                <Button key={e} size="sm" variant={filterEvent===e?'default':'outline'}
                  onClick={() => setFilterEvent(e)} className="text-[10px]">
                  {e==='all'?'All Events':EVENT_LABEL[e]||e}
                </Button>
              ))}
            </div>
            <div className="relative flex-1 min-w-[180px] max-w-xs">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-foreground/40" />
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Cari recipient/body..."
                className="w-full rounded-lg border border-foreground/10 bg-foreground/5 pl-8 pr-3 py-1.5 text-sm focus:outline-none" />
            </div>
          </div>

          {/* List */}
          {loading ? (
            <div className="text-center py-10 text-foreground/40 text-sm">Memuat...</div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12 rounded-xl border border-dashed border-foreground/10">
              <Bell className="w-8 h-8 mx-auto text-foreground/30 mb-2" />
              <p className="text-sm text-foreground/50">Belum ada notifikasi.</p>
            </div>
          ) : (
            <div className="space-y-2" data-testid="notif-list">
              {filtered.map(n => {
                const Icon = CHANNEL_ICON[n.channel] || Bell;
                return (
                  <GlassCard key={n.id} className="p-3" data-testid={`notif-row-${n.id}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <Icon className="w-4 h-4 text-foreground/55" />
                          <span className="text-sm font-medium text-foreground truncate">{n.recipient}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${STATUS_TONE[n.status]||'bg-foreground/10'}`}>{n.status}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-300 border border-violet-400/25">{EVENT_LABEL[n.event_type]||n.event_type}</span>
                          {n.sent_real && <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-300">REAL</span>}
                          {n.sent_mock && <span className="text-[10px] px-1.5 py-0.5 rounded bg-foreground/10 text-foreground/55">MOCK</span>}
                        </div>
                        {n.subject && <div className="text-xs text-foreground/65 font-medium mb-0.5">{n.subject}</div>}
                        <p className="text-xs text-foreground/65 line-clamp-2">{n.body}</p>
                        <div className="text-[10px] text-foreground/40 mt-1">
                          {new Date(n.created_at).toLocaleString('id-ID')}
                          {n.sent_at && ` · sent ${new Date(n.sent_at).toLocaleString('id-ID')}`}
                        </div>
                      </div>
                      <div className="flex gap-1 shrink-0">
                        {n.status === 'queued' && (
                          <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => markSent(n.id)}>
                            <Send className="w-3 h-3" /> Send
                          </Button>
                        )}
                        {n.status === 'failed' && (
                          <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => retry(n.id)}>
                            <RotateCw className="w-3 h-3" /> Retry
                          </Button>
                        )}
                        <Button size="icon" variant="ghost" className="w-7 h-7 text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/15" onClick={() => remove(n.id)}>
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </div>
                  </GlassCard>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
