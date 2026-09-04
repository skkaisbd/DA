/**
 * Ringkasan Bisnis (Management Overview) — dipisah per DOMAIN + jejak sumber.
 *
 * 2026-08-06 — DIPERBAIKI TOTAL.
 * Versi lama membaca endpoint yang mengagregasi koleksi pra-migrasi
 * (`rahaza_orders`, `rahaza_work_orders`, `rahaza_wip_events`,
 * `rahaza_ap_invoices`, `rahaza_cash_accounts`) yang isinya 0–2 dokumen ⇒ semua
 * KPI nol/salah. Backend `routes/rahaza_reports.py` sekarang membaca SSOT
 * (production_pos / po_items / production_jobs / production_job_items /
 * production_progress / cmt_receipts / buyer_shipments / rahaza_ar_invoices)
 * dan setiap respons mengirim `sources` → dirender <SourceTrace/>.
 *
 * Keputusan owner: **domain dipisah tegas** — Produksi Internal DA vs Maklon.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  RefreshCw, Users, Factory, DollarSign, AlertTriangle,
  Package, Activity, ClipboardList, Database, BellRing, CalendarClock,
  SlidersHorizontal, Loader2, Check,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  StatCard, ChartCard, GlassTooltip, HeroCrystalCard, DonutProgress, CHART_PALETTE,
} from './dashboardAtoms';
import { PeriodPicker } from './PeriodPicker';
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area,
} from 'recharts';
import { formatRupiah } from '@/lib/format';

const fmtNum = (n) => Number(n || 0).toLocaleString('id-ID');
const fmtShortIDR = (n) => {
  const v = Number(n || 0);
  if (v >= 1e9) return `Rp ${(v / 1e9).toFixed(1)}M`;
  if (v >= 1e6) return `Rp ${(v / 1e6).toFixed(1)}jt`;
  if (v >= 1e3) return `Rp ${(v / 1e3).toFixed(0)}rb`;
  return formatRupiah(v);
};

const DOMAINS = [
  { id: 'all', label: 'Gabungan' },
  { id: 'internal', label: 'Internal DA' },
  { id: 'maklon', label: 'Maklon' },
];

/** Jejak koleksi SSOT yang dipakai — menjawab "angka ini dari mana?". */
function SourceTrace({ rows, domainLabel }) {
  if (!rows?.length) return null;
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--glass-border)] bg-[var(--card-surface)] px-3 py-2"
         data-testid="overview-source-trace">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Database className="h-3.5 w-3.5 text-foreground/40" />
        <span className="text-[11px] font-semibold text-foreground/60">Sumber data:</span>
        {domainLabel && <Badge variant="outline" className="text-[10px]">{domainLabel}</Badge>}
        {rows.map((s) => (
          <span key={s.collection} title={s.note || ''}
                className="rounded border border-[var(--glass-border)] px-1.5 py-0.5 text-[10px] text-foreground/60">
            <span className="font-mono">{s.collection}</span>
            <span className="ml-1 font-semibold text-foreground">{fmtNum(s.count)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ManagementOverviewModule({ token }) {
  const [domain, setDomain] = useState('all');
  const [data, setData] = useState(null);
  const [daily, setDaily] = useState([]);
  const [topModels, setTopModels] = useState([]);
  const [topCustomers, setTopCustomers] = useState([]);
  const [onTime, setOnTime] = useState(null);
  const [alerts, setAlerts] = useState(null);   // peringatan otomatis (PO deadline & piutang)
  const [alertCfg, setAlertCfg] = useState(null);   // ambang hari (bisa diatur owner)
  const [cfgDraft, setCfgDraft] = useState({
    po_warn_days: '', ar_warn_days: '', rnd_attention_days: '', rnd_stale_days: '',
    // 2026-08-07 — ambang NILAI (Rp) yang menentukan berapa tahap persetujuan
    // yang wajib dilalui sebuah Permintaan Pengadaan (PR).
    pr_1_stage_max: '', pr_2_stage_max: '',
  });
  const [savingCfg, setSavingCfg] = useState(false);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [period, setPeriod] = useState({ preset: '30d', from: null, to: null });

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const dateRange = useMemo(() => {
    let { from, to } = period || {};
    if (!from || !to) {
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      const add = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
      const preset = period?.preset || '30d';
      if (preset === 'today') { from = iso(today); to = iso(today); }
      else if (preset === '7d') { from = iso(add(today, -6)); to = iso(today); }
      else if (preset === '30d') { from = iso(add(today, -29)); to = iso(today); }
      else if (preset === '90d') { from = iso(add(today, -89)); to = iso(today); }
      else if (preset === 'month') { from = iso(new Date(today.getFullYear(), today.getMonth(), 1)); to = iso(today); }
      else if (preset === 'ytd') { from = `${today.getFullYear()}-01-01`; to = iso(today); }
    }
    return { from, to };
  }, [period]);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const qs = `?domain=${domain}` +
        (dateRange.from && dateRange.to ? `&date_from=${dateRange.from}&date_to=${dateRange.to}` : '');
      const [ov, dl, tm, tc, ot, al, cfg] = await Promise.all([
        fetch(`/api/rahaza/management/overview${qs}`, { headers }).then(r => r.json()),
        fetch(`/api/rahaza/management/daily-output${qs}`, { headers }).then(r => r.json()),
        fetch(`/api/rahaza/management/top-models?domain=${domain}&limit=5`, { headers }).then(r => r.json()),
        fetch(`/api/rahaza/management/top-customers?domain=${domain}&limit=5`, { headers }).then(r => r.json()),
        fetch(`/api/rahaza/management/on-time-delivery?domain=${domain}&days=90`, { headers }).then(r => r.json()),
        fetch('/api/rahaza/management/alerts', { headers }).then(r => r.json()),
        fetch('/api/rahaza/management/alert-config', { headers }).then(r => r.json()),
      ]);
      setData(ov);
      setDaily(dl.timeline || []);
      setTopModels(tm.items || []);
      setTopCustomers(tc.items || []);
      setOnTime(ot);
      setAlerts(al);
      setAlertCfg(cfg);
      setCfgDraft({
        po_warn_days: String(cfg?.po_warn_days ?? 3),
        ar_warn_days: String(cfg?.ar_warn_days ?? 3),
        rnd_attention_days: String(cfg?.rnd_attention_days ?? 3),
        rnd_stale_days: String(cfg?.rnd_stale_days ?? 7),
        pr_1_stage_max: String(cfg?.pr_1_stage_max ?? 1000000),
        pr_2_stage_max: String(cfg?.pr_2_stage_max ?? 25000000),
      });
      setLastUpdate(new Date());
    } finally { setLoading(false); }
  }, [headers, domain, dateRange.from, dateRange.to]);

  const saveAlertConfig = async () => {
    setSavingCfg(true);
    try {
      const res = await fetch('/api/rahaza/management/alert-config', {
        method: 'PUT',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          po_warn_days: Number(cfgDraft.po_warn_days),
          ar_warn_days: Number(cfgDraft.ar_warn_days),
          rnd_attention_days: Number(cfgDraft.rnd_attention_days),
          rnd_stale_days: Number(cfgDraft.rnd_stale_days),
          pr_1_stage_max: Number(cfgDraft.pr_1_stage_max),
          pr_2_stage_max: Number(cfgDraft.pr_2_stage_max),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      setAlertCfg(body);
      toast.success('Ambang disimpan', {
        description: `PO ${body.po_warn_days} hari · Piutang ${body.ar_warn_days} hari · `
          + `RnD kuning ${body.rnd_attention_days} hari / merah ${body.rnd_stale_days} hari · `
          + `PR 1 tahap ≤ ${fmtShortIDR(body.pr_1_stage_max)} · 2 tahap ≤ ${fmtShortIDR(body.pr_2_stage_max)}`,
      });
      const al = await fetch('/api/rahaza/management/alerts', { headers }).then(r => r.json());
      setAlerts(al);
    } catch (e) {
      toast.error('Gagal menyimpan ambang', { description: e.message });
    } finally {
      setSavingCfg(false);
    }
  };

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, 60000);
    return () => clearInterval(t);
  }, [fetchAll]);

  const prod = data?.production || {};
  const ord = data?.orders || {};
  const fin = data?.finance || {};

  if (loading && !data) {
    return (
      <div className="space-y-5">
        <div className="h-32 animate-pulse rounded-[var(--radius-xl)] border border-[var(--glass-border)] bg-[var(--card-surface)]" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-[var(--radius-lg)] border border-[var(--glass-border)] bg-[var(--card-surface)]" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="management-overview-page">
      <HeroCrystalCard
        testId="mgmt-hero"
        eyebrow="Ringkasan Bisnis"
        title={data?.domain_label || 'Ringkasan Bisnis'}
        description="Angka diambil langsung dari dokumen kerja nyata: PO, job produksi, penerimaan dari CMT, pengiriman, dan invoice. Setiap kartu bisa ditelusuri lewat jejak sumber di bawah."
        actions={
          <PeriodPicker value={period} onChange={setPeriod} compareEnabled={false}
                        testId="mgmt-overview-period" />
        }
      >
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex overflow-hidden rounded-lg border border-[var(--glass-border)]"
               role="group" aria-label="Pilih domain bisnis" data-testid="overview-domain-switch">
            {DOMAINS.map((d) => (
              <button
                key={d.id} type="button" onClick={() => setDomain(d.id)}
                data-testid={`overview-domain-${d.id}`}
                aria-pressed={domain === d.id}
                className={`px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                  domain === d.id
                    ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]'
                    : 'bg-transparent text-foreground/60 hover:bg-[var(--glass-bg-hover)]'
                }`}
              >{d.label}</button>
            ))}
          </div>
          <Button onClick={fetchAll} className="h-9 bg-[hsl(var(--primary))] hover:brightness-110"
                  data-testid="overview-refresh">
            <RefreshCw className={`mr-1.5 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            {loading ? 'Memuat...' : 'Refresh'}
          </Button>
          {lastUpdate && (
            <span className="text-xs text-foreground/50">
              Diperbarui {lastUpdate.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })}
              {' '}· Periode {data?.date_from}→{data?.date_to}
            </span>
          )}
        </div>
      </HeroCrystalCard>

      {/* ── KPI ─────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          testId="kpi-output"
          icon={Factory}
          label="Output Periode"
          value={fmtNum(prod.output_period)}
          sub={`pcs · progres ${fmtNum(prod.output_progress_period)} + terima CMT ${fmtNum(prod.output_received_period)}`}
          accent="primary"
        />
        <StatCard
          testId="kpi-quality"
          icon={Activity}
          label="Diterima / Diproduksi"
          value={`${prod.accept_rate_pct || 0}%`}
          sub={`${fmtNum(prod.qty_accepted)} diterima · ${fmtNum(prod.qty_reject)} reject · ${fmtNum(prod.qty_rework_open)} rework`}
          accent="success"
        />
        <StatCard
          testId="kpi-orders"
          icon={ClipboardList}
          label="PO Berjalan"
          value={fmtNum(ord.running)}
          sub={`dari ${fmtNum(ord.total)} PO · ${fmtNum(ord.qty_ordered)} pcs dipesan`}
          accent="info"
        />
        <StatCard
          testId="kpi-ar"
          icon={DollarSign}
          label="Piutang Belum Tertagih"
          value={fmtShortIDR(fin.ar_outstanding)}
          sub={`${fmtNum(fin.ar_invoices)} invoice · ${fmtNum(fin.ar_overdue_count)} jatuh tempo`}
          accent="mint"
        />
      </div>

      {/* ── Peringatan otomatis + ambang yang bisa diatur ───────────────── */}
      <ChartCard testId="card-alerts" title="Peringatan Perlu Tindakan"
                 subtitle={`Dikirim otomatis ke manajemen setiap pagi 07:00 — PO ${alertCfg?.po_warn_days ?? 3} hari & piutang ${alertCfg?.ar_warn_days ?? 3} hari sebelum tenggat (juga saat sudah lewat)`}>
        <div className="space-y-3">
          {/* Pengaturan ambang hari */}
          <div className="flex flex-wrap items-end gap-3 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2"
               data-testid="alert-threshold-form">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-foreground/60">
              <SlidersHorizontal className="h-3.5 w-3.5" /> Ambang Peringatan
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-foreground/60" htmlFor="po-warn-days">
                PO — hari sebelum tenggat
              </label>
              <Input id="po-warn-days" type="number" min="0" max="60" className="h-8 w-24"
                     value={cfgDraft.po_warn_days} data-testid="alert-po-days-input"
                     onChange={(e) => setCfgDraft((p) => ({ ...p, po_warn_days: e.target.value }))} />
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-foreground/60" htmlFor="ar-warn-days">
                Piutang — hari sebelum jatuh tempo
              </label>
              <Input id="ar-warn-days" type="number" min="0" max="60" className="h-8 w-24"
                     value={cfgDraft.ar_warn_days} data-testid="alert-ar-days-input"
                     onChange={(e) => setCfgDraft((p) => ({ ...p, ar_warn_days: e.target.value }))} />
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-foreground/60" htmlFor="rnd-attention-days">
                RnD — kuning setelah (hari)
              </label>
              <Input id="rnd-attention-days" type="number" min="0" max="60" className="h-8 w-24"
                     value={cfgDraft.rnd_attention_days} data-testid="alert-rnd-attention-input"
                     onChange={(e) => setCfgDraft((p) => ({ ...p, rnd_attention_days: e.target.value }))} />
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-foreground/60" htmlFor="rnd-stale-days">
                RnD — merah / terlambat (hari)
              </label>
              <Input id="rnd-stale-days" type="number" min="0" max="60" className="h-8 w-24"
                     value={cfgDraft.rnd_stale_days} data-testid="alert-rnd-stale-input"
                     onChange={(e) => setCfgDraft((p) => ({ ...p, rnd_stale_days: e.target.value }))} />
            </div>
            <Button size="sm" className="h-8" onClick={saveAlertConfig} disabled={savingCfg}
                    data-testid="alert-threshold-save">
              {savingCfg ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                : <Check className="mr-1 h-3.5 w-3.5" />}
              Simpan
            </Button>
            <span className="text-[11px] text-foreground/50">
              Bawaan PO/piutang {alertCfg?.defaults?.po_warn_days ?? 3} hari · RnD {alertCfg?.defaults?.rnd_attention_days ?? 3}/{alertCfg?.defaults?.rnd_stale_days ?? 7} hari ·
              berlaku untuk penjadwal harian, kokpit RnD &amp; layar ini
              {alertCfg?.updated_by ? ` · terakhir diubah ${alertCfg.updated_by}` : ''}
            </span>
          </div>

          {/* ── Ambang NILAI persetujuan Permintaan Pengadaan (PR) ─────────────
              Permintaan owner 2026-08-07: "PR bernilai kecil jangan dipaksa lewat
              3 tahap." Ambang ini menentukan berapa tahap yang wajib dilalui,
              dan DIBEKUKAN pada tiap PR saat diajukan — mengubahnya di sini
              hanya memengaruhi PR BARU, tidak menggeser PR yang sudah berjalan. */}
          <div className="flex flex-wrap items-end gap-3 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2"
               data-testid="pr-chain-threshold-form">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-foreground/60">
              <SlidersHorizontal className="h-3.5 w-3.5" /> Ambang Persetujuan PR
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-foreground/60" htmlFor="pr-1-stage-max">
                Cukup 1 tahap bila nilai ≤ (Rp)
              </label>
              <Input id="pr-1-stage-max" type="number" min="0" step="100000" className="h-8 w-40"
                     value={cfgDraft.pr_1_stage_max} data-testid="pr-1-stage-max-input"
                     onChange={(e) => setCfgDraft((p) => ({ ...p, pr_1_stage_max: e.target.value }))} />
              <span className="mt-0.5 block text-[10px] text-foreground/50">
                = {fmtShortIDR(Number(cfgDraft.pr_1_stage_max) || 0)} · hanya Persetujuan Departemen
              </span>
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-foreground/60" htmlFor="pr-2-stage-max">
                Cukup 2 tahap bila nilai ≤ (Rp)
              </label>
              <Input id="pr-2-stage-max" type="number" min="0" step="1000000" className="h-8 w-40"
                     value={cfgDraft.pr_2_stage_max} data-testid="pr-2-stage-max-input"
                     onChange={(e) => setCfgDraft((p) => ({ ...p, pr_2_stage_max: e.target.value }))} />
              <span className="mt-0.5 block text-[10px] text-foreground/50">
                = {fmtShortIDR(Number(cfgDraft.pr_2_stage_max) || 0)} · Departemen + Keuangan
              </span>
            </div>
            <Button size="sm" className="h-8" onClick={saveAlertConfig} disabled={savingCfg}
                    data-testid="pr-chain-threshold-save">
              {savingCfg ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                : <Check className="mr-1 h-3.5 w-3.5" />}
              Simpan
            </Button>
            <span className="max-w-md text-[11px] text-foreground/50">
              Di atas {fmtShortIDR(Number(cfgDraft.pr_2_stage_max) || 0)} → 3 tahap
              (Departemen + Keuangan + Final/Direksi). Ambang dibekukan saat PR diajukan,
              jadi perubahan di sini hanya berlaku untuk PR baru.
              {alertCfg?.updated_by ? ` · terakhir diubah ${alertCfg.updated_by}` : ''}
            </span>
          </div>

          {alerts?.po_alerts?.length > 0 && (
              <div>
                <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-foreground/50">
                  <CalendarClock className="h-3.5 w-3.5" /> PO ({alerts.po_count})
                </p>
                <ul className="space-y-1.5" data-testid="alert-po-list">
                  {alerts.po_alerts.slice(0, 5).map((a) => (
                    <li key={a.po_id}
                        className={`flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs ${
                          a.days_left < 0
                            ? 'border-destructive/40 bg-destructive/10'
                            : 'border-amber-500/40 bg-amber-500/10'}`}>
                      <span className="font-medium text-foreground">
                        {a.po_number} <span className="font-normal text-foreground/60">· {a.domain} · {a.customer}</span>
                      </span>
                      <span className="text-foreground/70">
                        {a.days_left < 0 ? `lewat ${Math.abs(a.days_left)} hari` : `sisa ${a.days_left} hari`}
                        {' · '}kurang {fmtNum(a.qty_short)} pcs
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {alerts?.ar_alerts?.length > 0 && (
              <div>
                <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-foreground/50">
                  <BellRing className="h-3.5 w-3.5" /> Piutang ({alerts.ar_count})
                </p>
                <ul className="space-y-1.5" data-testid="alert-ar-list">
                  {alerts.ar_alerts.slice(0, 5).map((a) => (
                    <li key={a.invoice_id}
                        className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">
                      <span className="font-medium text-foreground">
                        {a.invoice_number} <span className="font-normal text-foreground/60">· {a.customer}</span>
                      </span>
                      <span className="text-foreground/70">
                        {fmtShortIDR(a.outstanding)} ·
                        {a.days_left < 0 ? ` lewat ${Math.abs(a.days_left)} hari` : ` sisa ${a.days_left} hari`}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {!alerts?.po_count && !alerts?.ar_count && (
              <p className="py-4 text-center text-xs text-foreground/50" data-testid="alert-empty">
                Tidak ada PO atau piutang yang mendekati tenggat pada ambang saat ini.
              </p>
            )}
        </div>
      </ChartCard>

      {/* ── Tahapan PO ──────────────────────────────────────────────────── */}
      <ChartCard testId="card-po-funnel" title="Tahapan PO"
                 subtitle="Sebaran PO menurut status di alur kerja (SSOT production_pos)">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {[
            ['Draft', ord.draft, 'Belum dikonfirmasi'],
            ['Dikonfirmasi', ord.confirmed, 'Siap didistribusi'],
            ['Berjalan', ord.running, 'Sedang diproduksi'],
            ['Selesai', ord.done, 'Completed / Closed'],
            ['Dibatalkan', ord.cancelled, 'Cancelled'],
          ].map(([label, val, hint]) => (
            <div key={label} className="rounded-[var(--radius-md)] border border-[var(--glass-border)] px-3 py-2"
                 data-testid={`po-bucket-${label}`}>
              <p className="text-2xl font-bold tabular-nums text-foreground">{fmtNum(val)}</p>
              <p className="text-xs font-medium text-foreground/70">{label}</p>
              <p className="mt-0.5 text-[10px] text-foreground/40">{hint}</p>
            </div>
          ))}
        </div>
      </ChartCard>

      {/* ── Output harian + ketepatan kirim ─────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ChartCard
          testId="chart-daily-output"
          title="Output per Hari"
          subtitle="Internal = catatan progres produksi · Maklon = penerimaan barang dari CMT"
          className="lg:col-span-2"
        >
          {daily.every((d) => !d.total) ? (
            <div className="py-12 text-center text-xs text-foreground/40" data-testid="daily-output-empty">
              Belum ada output pada periode ini. Output tercatat saat progres produksi diinput
              atau saat barang dari CMT diterima &amp; di-QC.
            </div>
          ) : (
            <div style={{ width: '100%', height: 240 }}>
              <ResponsiveContainer>
                <AreaChart data={daily} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                  <defs>
                    <linearGradient id="outInternal" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={CHART_PALETTE[0]} stopOpacity={0.5} />
                      <stop offset="100%" stopColor={CHART_PALETTE[0]} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="outMaklon" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={CHART_PALETTE[1]} stopOpacity={0.5} />
                      <stop offset="100%" stopColor={CHART_PALETTE[1]} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 4" stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="date" stroke="var(--chart-grid)"
                         tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                         tickFormatter={(v) => (v ? v.slice(5).replace('-', '/') : '')} />
                  <YAxis width={40} stroke="var(--chart-grid)"
                         tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                  <Tooltip content={<GlassTooltip formatter={(v) => `${fmtNum(v)} pcs`} />}
                           cursor={{ fill: 'var(--glass-bg-hover)' }} />
                  <Area type="monotone" dataKey="internal" name="Internal DA" stackId="1"
                        stroke={CHART_PALETTE[0]} strokeWidth={2} fill="url(#outInternal)" />
                  <Area type="monotone" dataKey="maklon" name="Maklon" stackId="1"
                        stroke={CHART_PALETTE[1]} strokeWidth={2} fill="url(#outMaklon)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </ChartCard>

        <ChartCard testId="card-on-time" title="Ketepatan Kirim ke Buyer"
                   subtitle="Dispatch terakhir vs deadline PO (90 hari)">
          <div className="flex flex-col items-center justify-center py-4">
            <DonutProgress
              value={onTime?.rate_pct || 0}
              size={160}
              stroke={14}
              label="Tepat Waktu"
              sub={`${onTime?.on_time || 0} / ${onTime?.total_po || 0} PO`}
              accent={(onTime?.rate_pct || 0) >= 85 ? 'success'
                : (onTime?.rate_pct || 0) >= 60 ? 'primary' : 'warning'}
            />
            <p className="mt-3 px-2 text-center text-[10px] leading-relaxed text-foreground/45">
              {onTime?.total_po
                ? onTime?.measurable_note
                : 'Belum ada PO yang punya deadline sekaligus sudah dikirim ke buyer — belum bisa dinilai.'}
            </p>
          </div>
        </ChartCard>
      </div>

      {/* ── Gudang + Top produk + Top pelanggan ─────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ChartCard testId="card-low-stock" title="Peringatan Gudang"
                   subtitle="Material di bawah stok minimum">
          <div className="flex items-center justify-between gap-4 py-2">
            <div>
              <p className="text-5xl font-bold leading-none tracking-tight text-[hsl(var(--warning))]">
                {fmtNum(data?.warehouse?.low_stock_materials)}
              </p>
              <p className="mt-2 text-xs text-foreground/50">
                dari {fmtNum(data?.warehouse?.materials_tracked)} material aktif
              </p>
            </div>
            {(data?.warehouse?.low_stock_materials || 0) > 0 ? (
              <div className="grid h-14 w-14 place-items-center rounded-2xl border border-[hsl(var(--warning)/0.25)] bg-[hsl(var(--warning)/0.15)]">
                <AlertTriangle className="h-6 w-6 text-[hsl(var(--warning))]" />
              </div>
            ) : (
              <div className="grid h-14 w-14 place-items-center rounded-2xl border border-[hsl(var(--success)/0.25)] bg-[hsl(var(--success)/0.15)]">
                <Package className="h-6 w-6 text-[hsl(var(--success))]" />
              </div>
            )}
          </div>
          <div className="mt-2 flex items-center gap-2 border-t border-[var(--glass-border)] pt-2 text-xs text-foreground/50">
            <Users className="h-3.5 w-3.5" />
            {fmtNum(data?.hr?.employees_active)} karyawan aktif
          </div>
        </ChartCard>

        <ChartCard testId="card-top-models" title="Top 5 Produk"
                   subtitle="Qty dipesan (PO) vs qty sudah diterima">
          {topModels.length === 0 ? (
            <div className="py-8 text-center text-xs text-foreground/40">Belum ada item PO.</div>
          ) : (
            <div className="space-y-2.5">
              {topModels.map((m, idx) => {
                const maxQty = topModels[0]?.qty || 1;
                return (
                  <div key={`${m.sku}-${idx}`} className="flex items-center gap-3"
                       data-testid={`top-model-${idx}`}>
                    <div className="w-6 text-center text-xs font-bold text-foreground/40">#{idx + 1}</div>
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex items-center justify-between gap-2">
                        <p className="truncate text-xs text-foreground">{m.name || m.sku}</p>
                        <span className="shrink-0 font-mono text-xs tabular-nums text-foreground">
                          {fmtNum(m.accepted)}/{fmtNum(m.qty)}
                        </span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-[var(--glass-bg)]">
                        <div className="h-full rounded-full bg-[hsl(var(--primary))] transition-[width] duration-500"
                             style={{ width: `${(m.qty / maxQty) * 100}%` }} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ChartCard>

        <ChartCard testId="card-top-customers" title="Top 5 Pelanggan / Klien"
                   subtitle="Volume PO (+ nilai order untuk maklon)">
          {topCustomers.length === 0 ? (
            <div className="py-8 text-center text-xs text-foreground/40">Belum ada PO.</div>
          ) : (
            <div className="space-y-2.5">
              {topCustomers.map((c, idx) => (
                <div key={`${c.name}-${idx}`} className="flex items-center gap-3"
                     data-testid={`top-customer-${idx}`}>
                  <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-[hsl(var(--primary)/0.20)] bg-[hsl(var(--primary)/0.12)] text-xs font-bold text-[hsl(var(--primary))]">
                    {(c.name || '?')[0]?.toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-foreground">{c.name}</p>
                    <p className="text-[10px] text-foreground/50">
                      {fmtNum(c.orders)} PO{c.total_value ? ` · ${fmtShortIDR(c.total_value)}` : ''}
                    </p>
                  </div>
                  <span className="font-mono text-xs tabular-nums text-foreground">{fmtNum(c.total_qty)} pcs</span>
                </div>
              ))}
            </div>
          )}
        </ChartCard>
      </div>

      <SourceTrace rows={data?.sources} domainLabel={data?.domain_label} />
    </div>
  );
}
