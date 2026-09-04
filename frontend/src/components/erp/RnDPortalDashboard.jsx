/**
 * Ringkasan & Approval RnD — DIROMBAK 2026-08-06.
 *
 * KELUHAN OWNER: "ringkasan rnd juga tidak jelas, hanya cards yang besar sangat
 * buruk secara ui ux dan fungsionalitasnya tidak ada padahal ini step lifecycle
 * crusial yang butuh approve koordinasi antara staff rnd dengan manajement."
 *
 * Dulu: 3 baris × 4 kartu gradien raksasa, murni angka, tanpa satu pun aksi.
 * Sekarang: LAYAR KEPUTUSAN.
 *   1. Antrean Keputusan — style / permintaan sample / tech pack yang menunggu,
 *      dengan umur tunggu (SLA) + tombol Setujui / Tolak (alasan wajib untuk style).
 *   2. Tahapan Lifecycle — posisi antrean Draft → Menunggu → Disetujui → Naik Produksi.
 *   3. Ringkasan angka dalam tile kecil (bukan kartu raksasa).
 *
 * Endpoint approval-nya sudah ada sejak lama tapi tidak pernah dipakai UI:
 *   POST /api/dewi/rnd/styles/{id}/owner-approve · /owner-reject
 *   POST /api/dewi/rnd/sample-requests/{id}/approve · /reject
 *   POST /api/dewi/rnd/tech-packs/{id}/approve
 * Daftar antrean: GET /api/dewi/rnd/approvals/pending
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  FlaskConical, RefreshCw, CheckCircle2, XCircle, Clock, ArrowRight,
  Palette, Layers, Calculator, Ruler, Activity, Database, Loader2, Inbox,
  Eye, History, ImageOff, Paperclip, ThumbsUp, ThumbsDown, GitCompare,
  ListTree, Mail, Send,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { GlassCard } from '@/components/ui/glass';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { PageHeader } from './moduleAtoms';
import RnDRevisionCompare, { authImageUrl } from './RnDRevisionCompare';

const API = process.env.REACT_APP_BACKEND_URL || '';

const KIND_STYLE = {
  style: { icon: Palette, cls: 'bg-violet-500/15 text-violet-600 dark:text-violet-400 border-violet-500/30' },
  sample: { icon: FlaskConical, cls: 'bg-sky-500/15 text-sky-600 dark:text-sky-400 border-sky-500/30' },
  tech_pack: { icon: Ruler, cls: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30' },
};

const SLA_STYLE = {
  baru: 'bg-muted text-muted-foreground border-border',
  'perlu perhatian': 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
  terlambat: 'bg-destructive/15 text-destructive border-destructive/30',
};

// Warna tahap lifecycle (7 langkah) — dipakai tabel "Posisi Tiap Style".
const STAGE_CLS = {
  draft: 'bg-muted text-muted-foreground border-border',
  pending_owner_review: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
  approved_for_launch: 'bg-sky-500/15 text-sky-600 dark:text-sky-400 border-sky-500/30',
  techpack: 'bg-violet-500/15 text-violet-600 dark:text-violet-400 border-violet-500/30',
  pattern: 'bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border-indigo-500/30',
  sample: 'bg-teal-500/15 text-teal-600 dark:text-teal-400 border-teal-500/30',
  promoted: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
};

const fmtNum = (v) => Number(v || 0).toLocaleString('id-ID');

export default function RnDPortalDashboard({ token, onNavigate }) {
  const [pending, setPending] = useState(null);
  const [history, setHistory] = useState(null);
  const [lifecycle, setLifecycle] = useState(null);
  const [weekly, setWeekly] = useState(null);
  const [sending, setSending] = useState(false);
  const [detail, setDetail] = useState(null);   // item yang dibuka detailnya
  const [kpi, setKpi] = useState({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [decision, setDecision] = useState(null); // {item, action}
  const [notes, setNotes] = useState('');
  const [compareStyleId, setCompareStyleId] = useState(null);

  const headers = useMemo(() => ({
    'Content-Type': 'application/json', Authorization: `Bearer ${token}`,
  }), [token]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, d, h, lc, wk] = await Promise.all([
        fetch(`${API}/api/dewi/rnd/approvals/pending`, { headers }).then((r) => r.json()),
        fetch(`${API}/api/dewi/rnd/dashboard`, { headers }).then((r) => r.json()),
        fetch(`${API}/api/dewi/rnd/approvals/history?limit=50`, { headers }).then((r) => r.json()),
        fetch(`${API}/api/dewi/rnd/lifecycle`, { headers }).then((r) => r.json()),
        fetch(`${API}/api/dewi/rnd/reports/weekly-decisions`, { headers }).then((r) => r.json()),
      ]);
      setPending(p);
      setHistory(h);
      setLifecycle(lc);
      setWeekly(wk);
      setKpi(d?.kpi || {});
    } catch (e) {
      toast.error('Gagal memuat data RnD', { description: e.message });
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const sendWeeklyReport = async () => {
    setSending(true);
    try {
      const r = await fetch(`${API}/api/dewi/rnd/reports/weekly-decisions/send`, {
        method: 'POST', headers, body: JSON.stringify({}),
      });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(b.detail || `HTTP ${r.status}`);
      toast.success(`Rapor ${b.week_key} dikirim ke ${b.recipients} penerima`, {
        description: `${b.counts?.approved || 0} disetujui · ${b.counts?.rejected || 0} ditolak · `
          + `${b.counts?.stale || 0} menunggu terlalu lama`,
      });
      setWeekly(b);
    } catch (e) {
      toast.error('Gagal mengirim rapor', { description: e.message });
    } finally {
      setSending(false);
    }
  };

  const submitDecision = async () => {
    if (!decision) return;
    const { item, action } = decision;
    const url = action === 'approve' ? item.approve_url : item.reject_url;
    if (!url) { toast.error('Aksi ini belum tersedia untuk jenis dokumen tersebut.'); return; }
    if (action === 'reject' && item.reject_requires_notes && !notes.trim()) {
      toast.error('Alasan penolakan wajib diisi.');
      return;
    }
    setBusy(item.id);
    try {
      const r = await fetch(`${API}${url}`, {
        method: 'POST', headers, body: JSON.stringify({ notes: notes.trim() }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
      toast.success(
        action === 'approve' ? `${item.kind_label} "${item.title}" disetujui`
          : `${item.kind_label} "${item.title}" ditolak`,
        { description: item.next_step },
      );
      setDecision(null);
      setNotes('');
      setDetail(null);
      await load();
    } catch (e) {
      toast.error('Keputusan gagal disimpan', { description: e.message });
    } finally {
      setBusy('');
    }
  };

  const items = pending?.items || [];

  return (
    <div className="space-y-4" data-testid="rnd-approval-cockpit">
      <PageHeader
        icon={FlaskConical}
        title="Ringkasan & Approval RnD"
        subtitle="Layar keputusan: apa yang menunggu persetujuan manajemen, sudah menunggu berapa lama, dan apa langkah berikutnya."
        testId="rnd-cockpit-header"
        actions={(
          <Button variant="outline" size="sm" onClick={load} data-testid="rnd-refresh">
            <RefreshCw className={loading ? 'animate-spin' : ''} /> Muat ulang
          </Button>
        )}
      />

      {/* ── 1. Antrean keputusan ─────────────────────────────────────────── */}
      <GlassCard className="p-4" hover={false}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Inbox className="h-4 w-4 text-primary" /> Antrean Keputusan
            </h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Bola ada di manajemen. Setujui atau tolak langsung dari sini.
            </p>
            {pending?.thresholds && (
              <p className="mt-1 text-[11px] text-muted-foreground" data-testid="rnd-sla-threshold-note">
                Ambang aktif: kuning ≥ {pending.thresholds.attention_days} hari · merah ≥{' '}
                {pending.thresholds.stale_days} hari — diatur owner di Portal Manajemen →
                Ringkasan Bisnis → Ambang Peringatan.
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={items.length ? 'default' : 'secondary'} className="text-[11px]"
                   data-testid="rnd-pending-count">
              {items.length} menunggu
            </Badge>
            {pending?.overdue > 0 && (
              <Badge variant="outline" className="border-destructive/40 text-[11px] text-destructive"
                     data-testid="rnd-overdue-count">
                {pending.overdue} terlambat (&ge;{pending?.thresholds?.stale_days ?? 7} hari)
              </Badge>
            )}
          </div>
        </div>

        {loading && !pending ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-16 rounded-lg" />)}
          </div>
        ) : items.length === 0 ? (
          <div className="py-10 text-center" data-testid="rnd-pending-empty">
            <CheckCircle2 className="mx-auto mb-2 h-8 w-8 text-emerald-600 dark:text-emerald-400" />
            <p className="text-sm font-medium text-foreground">Tidak ada yang menunggu keputusan</p>
            <p className="mx-auto mt-1 max-w-md text-xs text-muted-foreground">
              Item muncul di sini ketika staf RnD mengirim style untuk direview
              (status <span className="font-mono">pending_owner_review</span>), mengajukan
              permintaan sample, atau menyiapkan tech pack.
            </p>
          </div>
        ) : (
          <ul className="space-y-2" data-testid="rnd-pending-list">
            {items.map((it) => {
              const K = KIND_STYLE[it.kind] || KIND_STYLE.style;
              const Icon = K.icon;
              return (
                <li key={`${it.kind}-${it.id}`}
                    className="rounded-lg border border-border p-3"
                    data-testid={`rnd-pending-${it.kind}-${it.id}`}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex flex-wrap items-center gap-2">
                        <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium ${K.cls}`}>
                          <Icon className="h-3 w-3" /> {it.kind_label}
                        </span>
                        <span className="font-mono text-[11px] text-muted-foreground">{it.code}</span>
                        <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] ${SLA_STYLE[it.sla]}`}>
                          <Clock className="h-3 w-3" /> menunggu {it.age_days} hari · {it.sla}
                        </span>
                      </div>
                      <p className="truncate text-sm font-semibold text-foreground">{it.title}</p>
                      <p className="truncate text-xs text-muted-foreground">{it.subtitle}</p>
                      <p className="mt-1 text-[11px] text-muted-foreground/80">
                        Diajukan oleh <span className="font-medium text-foreground/80">{it.requested_by}</span>
                        {' · '}{it.next_step}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Button variant="ghost" size="sm" onClick={() => setDetail(it)}
                              data-testid={`rnd-detail-${it.id}`}>
                        <Eye /> Detail
                        {it.images?.length > 0 && (
                          <span className="ml-1 rounded bg-foreground/10 px-1 text-[10px]">
                            {it.images.length} foto
                          </span>
                        )}
                      </Button>
                      {it.reject_url && (
                        <Button variant="outline" size="sm" disabled={busy === it.id}
                                onClick={() => { setDecision({ item: it, action: 'reject' }); setNotes(''); }}
                                data-testid={`rnd-reject-${it.id}`}
                                className="border-destructive/40 text-destructive hover:bg-destructive/10">
                          <XCircle /> Tolak
                        </Button>
                      )}
                      <Button size="sm" disabled={busy === it.id}
                              onClick={() => { setDecision({ item: it, action: 'approve' }); setNotes(''); }}
                              data-testid={`rnd-approve-${it.id}`}>
                        {busy === it.id ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Setujui
                      </Button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </GlassCard>

      {/* ── 2. Tahapan lifecycle (7 langkah) ─────────────────────────────── */}
      <GlassCard className="p-4" hover={false}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-foreground">Tahapan Lifecycle Style</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Draft → Menunggu Keputusan → Disetujui → Tech Pack → Pola &amp; Marking → Sample → Naik Produksi.
              Satu style menempati satu tahap terjauh yang sudah dicapai.
            </p>
          </div>
          {lifecycle?.totals && (
            <div className="flex flex-wrap items-center gap-1.5" data-testid="rnd-lifecycle-totals">
              <Badge variant="outline" className="text-[11px]">
                {fmtNum(lifecycle.totals.tech_packs)} tech pack ({fmtNum(lifecycle.totals.tech_packs_approved)} disetujui)
              </Badge>
              <Badge variant="outline" className="text-[11px]">
                {fmtNum(lifecycle.totals.samples)} sample · {fmtNum(lifecycle.totals.sample_pics)} PIC
              </Badge>
              <Badge variant="outline" className="text-[11px]">
                {fmtNum(lifecycle.totals.patterns)} pola
              </Badge>
            </div>
          )}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7" data-testid="rnd-funnel">
          {(lifecycle?.stages || pending?.funnel || []).map((f, idx) => (
            <div key={f.key} className="rounded-lg border border-border px-3 py-2"
                 data-testid={`rnd-funnel-${f.key}`}>
              <div className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {idx > 0 && <ArrowRight className="h-3 w-3 opacity-50" />} {f.stage}
              </div>
              <p className="mt-1 text-2xl font-bold tabular-nums text-foreground">{fmtNum(f.count)}</p>
              <p className="text-[10px] text-muted-foreground">{f.hint}</p>
            </div>
          ))}
        </div>
      </GlassCard>

      {/* ── 2b. Posisi tiap style (granular: tech pack, pola, sample + PIC) ── */}
      <GlassCard className="p-4" hover={false} data-testid="rnd-lifecycle-card">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <ListTree className="h-4 w-4 text-primary" /> Posisi Tiap Style
            </h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Terlihat style mana tersendat di tahap apa — termasuk versi tech pack dan siapa pembuat sample-nya.
            </p>
          </div>
          <Badge variant="secondary" className="text-[11px]" data-testid="rnd-lifecycle-count">
            {fmtNum(lifecycle?.total_styles)} style
          </Badge>
        </div>
        {!lifecycle ? (
          <Skeleton className="h-28 rounded-lg" />
        ) : (lifecycle.styles || []).length === 0 ? (
          <p className="py-8 text-center text-xs text-muted-foreground" data-testid="rnd-lifecycle-empty">
            Belum ada style RnD. Setelah staf RnD membuat style, posisinya muncul di sini.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-max text-xs" data-testid="rnd-lifecycle-table">
              <thead className="bg-[var(--glass-bg)]">
                <tr>
                  {['STYLE', 'TAHAP SEKARANG', 'VARIAN', 'FOTO', 'TECH PACK', 'POLA',
                    'SAMPLE (PIC)', 'HPP', 'LANGKAH BERIKUTNYA'].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-muted-foreground">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {lifecycle.styles.map((r) => (
                  <tr key={r.id} className="border-t border-border hover:bg-[var(--glass-bg-hover)]"
                      data-testid={`rnd-lifecycle-row-${r.id}`}>
                    <td className="px-3 py-2">
                      <span className="font-mono text-foreground/80">{r.style_code}</span>
                      <span className="ml-2 text-muted-foreground">{r.style_name}</span>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium ${
                        STAGE_CLS[r.stage] || STAGE_CLS.draft}`}>
                        {r.stage_label}
                      </span>
                      {r.waiting_days > 0 && (
                        <span className="ml-1 text-[10px] text-muted-foreground">{r.waiting_days} hari</span>
                      )}
                    </td>
                    <td className="px-3 py-2 tabular-nums text-muted-foreground">{fmtNum(r.variants)}</td>
                    <td className="px-3 py-2 tabular-nums text-muted-foreground">{fmtNum(r.photos)}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {r.techpack?.count
                        ? `${r.techpack.version || '-'} · ${r.techpack.status || 'draft'}`
                        : <span className="text-amber-600 dark:text-amber-400">belum ada</span>}
                    </td>
                    <td className="px-3 py-2 tabular-nums text-muted-foreground">{fmtNum(r.patterns)}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {r.sample?.count ? (
                        <>
                          <span className="font-mono">{r.sample.code || '-'}</span>
                          <span className="ml-1">· {r.sample.status || '-'}</span>
                          <span className="ml-1 text-foreground/70">
                            · PIC {r.sample.pic || '(belum ditentukan)'}
                          </span>
                        </>
                      ) : <span className="text-amber-600 dark:text-amber-400">belum ada</span>}
                    </td>
                    <td className="px-3 py-2 tabular-nums text-muted-foreground">{fmtNum(r.hpp)}</td>
                    <td className="max-w-[260px] px-3 py-2 text-muted-foreground">{r.next_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      {/* ── 2c. Rapor keputusan mingguan ─────────────────────────────────── */}
      <GlassCard className="p-4" hover={false} data-testid="rnd-weekly-card">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Mail className="h-4 w-4 text-primary" /> Rapor Keputusan Mingguan
            </h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Dikirim otomatis setiap <span className="font-medium text-foreground/80">Senin 08:00 WIB</span> sebagai
              notifikasi ke manajemen: style disetujui, ditolak, dan yang menunggu terlalu lama
              (&gt;{weekly?.stale_days ?? 7} hari).
            </p>
          </div>
          <Button size="sm" variant="outline" onClick={sendWeeklyReport} disabled={sending || !weekly}
                  data-testid="rnd-weekly-send">
            {sending ? <Loader2 className="animate-spin" /> : <Send />} Kirim sekarang
          </Button>
        </div>
        {!weekly ? (
          <Skeleton className="h-20 rounded-lg" />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="rnd-weekly-counts">
              {[
                ['Disetujui', weekly.counts?.approved, 'emerald'],
                ['Ditolak', weekly.counts?.rejected, 'destructive'],
                ['Masih Menunggu', weekly.counts?.pending, 'muted'],
                ['Menunggu Terlalu Lama', weekly.counts?.stale, 'amber'],
              ].map(([label, val]) => (
                <div key={label} className="rounded-lg border border-border px-3 py-2"
                     data-testid={`rnd-weekly-${label}`}>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
                  <p className="mt-1 text-xl font-bold tabular-nums text-foreground">{fmtNum(val)}</p>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Periode rapor: {weekly.period_from} → {weekly.period_to} · pekan {weekly.week_key}
            </p>
            {(weekly.stale || []).length > 0 && (
              <ul className="mt-2 space-y-1" data-testid="rnd-weekly-stale-list">
                {weekly.stale.slice(0, 5).map((r) => (
                  <li key={r.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs">
                    <span className="font-medium text-foreground">
                      <span className="font-mono">{r.style_code}</span>
                      <span className="ml-2 font-normal text-muted-foreground">{r.style_name}</span>
                    </span>
                    <span className="text-muted-foreground">
                      menunggu {r.age_days} hari · diajukan {r.requested_by}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </GlassCard>

      {/* ── 3. Ringkasan angka (tile kecil) ──────────────────────────────── */}
      <GlassCard className="p-4" hover={false}>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-foreground">Ringkasan RnD</h3>
          {onNavigate && (
            <Button variant="ghost" size="sm" onClick={() => onNavigate('rnd-styles')}
                    data-testid="rnd-open-styles">
              Buka Style RnD <ArrowRight />
            </Button>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6" data-testid="rnd-kpis">
          {[
            ['Total Style', kpi.total_styles, Palette],
            ['Style Aktif', kpi.active_styles, CheckCircle2],
            ['Varian', kpi.total_variants, Layers],
            ['Sample', kpi.total_samples, FlaskConical],
            ['Sample Disetujui', kpi.approved_samples, CheckCircle2],
            ['Revisi', kpi.total_revisions, Activity],
            ['Pola', kpi.total_patterns, Ruler],
            ['HPP Tersimpan', kpi.total_hpp, Calculator],
          ].map(([label, val, Icon]) => (
            <div key={label} className="rounded-lg border border-border px-3 py-2"
                 data-testid={`rnd-kpi-${label}`}>
              <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                <Icon className="h-3 w-3" /> {label}
              </div>
              <p className="mt-1 text-xl font-bold tabular-nums text-foreground">{fmtNum(val)}</p>
            </div>
          ))}
        </div>
      </GlassCard>

      {/* ── 4. Riwayat keputusan ─────────────────────────────────────────── */}
      <GlassCard className="p-4" hover={false} data-testid="rnd-history-card">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <History className="h-4 w-4 text-primary" /> Riwayat Keputusan
            </h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Siapa menyetujui atau menolak, kapan, dan apa alasannya.
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <Badge variant="outline" className="border-emerald-500/40 text-[11px] text-emerald-600 dark:text-emerald-400">
              {history?.approved || 0} disetujui
            </Badge>
            <Badge variant="outline" className="border-destructive/40 text-[11px] text-destructive">
              {history?.rejected || 0} ditolak
            </Badge>
          </div>
        </div>
        {!history ? (
          <Skeleton className="h-24 rounded-lg" />
        ) : (history.items || []).length === 0 ? (
          <p className="py-8 text-center text-xs text-muted-foreground" data-testid="rnd-history-empty">
            Belum ada keputusan tercatat. Setiap persetujuan/penolakan dari layar ini akan muncul di sini
            beserta nama pemutus dan alasannya.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-max text-xs" data-testid="rnd-history-table">
              <thead className="bg-[var(--glass-bg)]">
                <tr>
                  {['JENIS', 'KODE', 'JUDUL', 'HASIL', 'DIPUTUSKAN OLEH', 'TANGGAL', 'ALASAN / CATATAN'].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-muted-foreground">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.items.map((r) => (
                  <tr key={`${r.kind}-${r.id}`} className="border-t border-border hover:bg-[var(--glass-bg-hover)]"
                      data-testid={`rnd-history-${r.id}`}>
                    <td className="px-3 py-2 text-muted-foreground">{r.kind_label}</td>
                    <td className="px-3 py-2 font-mono text-foreground/80">{r.code}</td>
                    <td className="max-w-[220px] truncate px-3 py-2 text-foreground">{r.title}</td>
                    <td className="px-3 py-2">
                      <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium ${
                        r.result === 'approved'
                          ? 'border-emerald-500/30 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                          : 'border-destructive/30 bg-destructive/15 text-destructive'}`}>
                        {r.result === 'approved' ? <ThumbsUp className="h-3 w-3" /> : <ThumbsDown className="h-3 w-3" />}
                        {r.result === 'approved' ? 'Disetujui' : 'Ditolak'}
                      </span>
                      {r.promoted && (
                        <span className="ml-1 rounded border border-border px-1 text-[10px] text-muted-foreground">
                          naik produksi
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-foreground/80">{r.decided_by || '-'}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {r.decided_at ? new Date(r.decided_at).toLocaleString('id-ID') : '-'}
                    </td>
                    <td className="max-w-[280px] px-3 py-2 text-muted-foreground">{r.notes || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      {/* ── Jejak sumber ─────────────────────────────────────────────────── */}
      {pending?.sources?.length > 0 && (
        <div className="rounded-lg border border-border bg-[var(--glass-bg)] px-3 py-2"
             data-testid="rnd-source-trace">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <Database className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-[11px] font-semibold text-muted-foreground">Sumber data:</span>
            {pending.sources.map((s) => (
              <span key={s.collection} title={s.note || ''}
                    className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">
                <span className="font-mono">{s.collection}</span>
                <span className="ml-1 font-semibold text-foreground">{fmtNum(s.count)}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── Dialog detail item (spesifikasi + foto) ───────────────────────── */}
      <Dialog open={!!detail} onOpenChange={(v) => { if (!v) setDetail(null); }}>
        <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-2xl" data-testid="rnd-detail-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {detail?.title}
              <span className="font-mono text-xs font-normal text-muted-foreground">{detail?.code}</span>
            </DialogTitle>
            <DialogDescription>
              {detail?.kind_label} · diajukan oleh {detail?.requested_by} · menunggu {detail?.age_days} hari
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
              {Object.entries(detail?.detail || {}).map(([k, v]) => (
                <div key={k} className="rounded-md border border-border px-3 py-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{k}</p>
                  <p className="mt-0.5 break-words text-xs text-foreground">
                    {v === null || v === undefined || v === '' ? '-'
                      : (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v)
                        ? new Date(v).toLocaleString('id-ID') : String(v))}
                  </p>
                </div>
              ))}
            </div>

            <div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-semibold text-foreground">
                  Foto / Gambar Desain ({detail?.images?.length || 0})
                </p>
                {detail?.kind === 'style' && (
                  <Button variant="outline" size="sm" data-testid="rnd-detail-compare"
                          onClick={() => setCompareStyleId(detail.id)}>
                    <GitCompare /> Bandingkan Revisi
                    {detail?.revisions_count > 0 && (
                      <span className="ml-1 rounded bg-foreground/10 px-1 text-[10px]">
                        {detail.revisions_count}
                      </span>
                    )}
                  </Button>
                )}
              </div>
              {(detail?.images || []).length === 0 ? (
                <div className="flex items-center gap-2 rounded-md border border-dashed border-border px-3 py-4 text-xs text-muted-foreground"
                     data-testid="rnd-detail-no-image">
                  <ImageOff className="h-4 w-4" />
                  Belum ada gambar dilampirkan pada dokumen ini. Staf RnD dapat menambahkannya di modul RnD.
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" data-testid="rnd-detail-images">
                  {detail.images.map((img, i) => (
                    <a key={i} href={authImageUrl(img.url, token)} target="_blank" rel="noreferrer"
                       className="group overflow-hidden rounded-lg border border-border"
                       title={img.caption || 'Buka gambar'}>
                      <img src={authImageUrl(img.url, token)} alt={img.caption || `Gambar ${i + 1}`}
                           loading="lazy"
                           className="h-32 w-full object-cover transition-transform duration-200 group-hover:scale-105" />
                      {img.caption && (
                        <p className="truncate px-2 py-1 text-[10px] text-muted-foreground">{img.caption}</p>
                      )}
                    </a>
                  ))}
                </div>
              )}
            </div>

            {detail?.attachment_url && (
              <a href={authImageUrl(detail.attachment_url, token)} target="_blank" rel="noreferrer"
                 className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-xs text-foreground hover:bg-[var(--glass-bg-hover)]"
                 data-testid="rnd-detail-attachment">
                <Paperclip className="h-3.5 w-3.5" />
                {detail.attachment_name || 'Buka lampiran / tech pack'}
              </a>
            )}

            <p className="rounded-md bg-[var(--glass-bg)] px-3 py-2 text-xs text-muted-foreground">
              Langkah berikutnya: {detail?.next_step}
            </p>
          </div>

          <DialogFooter>
            {detail?.reject_url && (
              <Button variant="outline" data-testid="rnd-detail-reject"
                      className="border-destructive/40 text-destructive hover:bg-destructive/10"
                      onClick={() => { setDecision({ item: detail, action: 'reject' }); setNotes(''); }}>
                <XCircle /> Tolak
              </Button>
            )}
            <Button data-testid="rnd-detail-approve"
                    onClick={() => { setDecision({ item: detail, action: 'approve' }); setNotes(''); }}>
              <CheckCircle2 /> Setujui
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Dialog keputusan ─────────────────────────────────────────────── */}
      <Dialog open={!!decision} onOpenChange={(v) => { if (!v) { setDecision(null); setNotes(''); } }}>
        <DialogContent data-testid="rnd-decision-dialog">
          <DialogHeader>
            <DialogTitle>
              {decision?.action === 'approve' ? 'Setujui' : 'Tolak'} {decision?.item?.kind_label}
            </DialogTitle>
            <DialogDescription>
              {decision?.item?.code} — {decision?.item?.title}
              {decision?.action === 'approve' && decision?.item?.next_step
                ? ` · ${decision.item.next_step}` : ''}
            </DialogDescription>
          </DialogHeader>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="rnd-notes">
              {decision?.action === 'reject'
                ? `Alasan penolakan${decision?.item?.reject_requires_notes ? ' (wajib)' : ' (opsional)'}`
                : 'Catatan persetujuan (opsional)'}
            </label>
            <Textarea id="rnd-notes" value={notes} rows={3} data-testid="rnd-decision-notes"
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder={decision?.action === 'reject'
                        ? 'cth. proporsi lengan perlu diperbaiki, bahan terlalu tebal untuk musim ini'
                        : 'cth. lanjutkan ke pembuatan sample'} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setDecision(null); setNotes(''); }}
                    data-testid="rnd-decision-cancel">Batal</Button>
            <Button onClick={submitDecision} disabled={!!busy}
                    data-testid="rnd-decision-submit"
                    className={decision?.action === 'reject'
                      ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90' : ''}>
              {busy ? <Loader2 className="animate-spin" /> : (
                decision?.action === 'approve' ? <CheckCircle2 /> : <XCircle />)}
              {decision?.action === 'approve' ? 'Setujui' : 'Tolak'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {/* ── Pembanding revisi style (dibuka dari dialog detail) ──────────── */}
      {compareStyleId && (
        <RnDRevisionCompare
          token={token}
          styleId={compareStyleId}
          onClose={() => setCompareStyleId(null)}
        />
      )}
    </div>
  );
}
