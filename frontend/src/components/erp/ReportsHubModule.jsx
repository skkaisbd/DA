/**
 * Pusat Laporan (Reports Hub) — DIROMBAK 2026-08-06.
 *
 * KELUHAN OWNER: "pusat laporan saya malah tidak mengerti menu ini, yang ada
 * malah direct ke portal lain." Versi lama memang HANYA katalog tautan statis:
 * tidak ada satu angka pun, semua kartu cuma melompat ke modul lain.
 *
 * SEKARANG: satu tempat untuk melihat data penting SETIAP PORTAL.
 *  · kategori dipilih satu per satu (Eksekutif, Produksi Internal DA, Maklon,
 *    Gudang, Keuangan, SDM, RnD, Marketing)
 *  · tiap kategori menampilkan KPI ringkas + tabel data relevan dari SSOT
 *  · tautan modul tetap ada, tapi sebagai TINDAK LANJUT, bukan satu-satunya isi
 *  · setiap kategori mengirim `sources` (jejak koleksi) supaya angka bisa ditelusuri
 *
 * Kontraknya generik (backend: GET /api/rahaza/reports-hub/summary?category=…)
 * sehingga menambah kategori/tabel baru TIDAK perlu mengubah komponen ini.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  FileSpreadsheet, RefreshCw, ArrowRight, Download, Database, Loader2,
  BarChart3, Factory, Layers, Package, DollarSign, Users, FlaskConical, Megaphone,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { GlassCard } from '@/components/ui/glass';
import { PageHeader } from './moduleAtoms';
import { PeriodPicker } from './PeriodPicker';
import { formatRupiah } from '@/lib/format';

const CATEGORY_ICON = {
  eksekutif: BarChart3,
  produksi_internal: Factory,
  maklon: Layers,
  gudang: Package,
  keuangan: DollarSign,
  sdm: Users,
  rnd: FlaskConical,
  marketing: Megaphone,
};

const TONE_CLASS = {
  primary: 'text-[hsl(var(--primary))]',
  success: 'text-emerald-600 dark:text-emerald-400',
  warning: 'text-amber-600 dark:text-amber-400',
  danger: 'text-destructive',
  info: 'text-sky-600 dark:text-sky-400',
};

const fmtNum = (v) => Number(v || 0).toLocaleString('id-ID');
const fmtDate = (v) => (v ? new Date(v).toLocaleDateString('id-ID') : '-');
const fmtShortIDR = (v) => {
  const n = Number(v || 0);
  if (n >= 1e9) return `Rp ${(n / 1e9).toFixed(1)}M`;
  if (n >= 1e6) return `Rp ${(n / 1e6).toFixed(1)}jt`;
  if (n >= 1e3) return `Rp ${(n / 1e3).toFixed(0)}rb`;
  return formatRupiah(n);
};

const renderCell = (val, format) => {
  if (val === null || val === undefined || val === '') return '-';
  if (format === 'date') return fmtDate(val);
  if (format === 'currency') return formatRupiah(val);
  if (format === 'number') return fmtNum(val);
  return String(val);
};

const kpiValue = (k) => {
  if (k.format === 'currency') return fmtShortIDR(k.value);
  if (k.format === 'percent') return `${Number(k.value || 0)}%`;
  if (k.format === 'number') return fmtNum(k.value);
  return String(k.value ?? '-');
};

const toCsv = (table) => {
  const head = table.columns.map((c) => c.label).join(';');
  const body = table.rows.map((r) => table.columns
    .map((c) => String(r[c.key] ?? '').replace(/;/g, ','))
    .join(';')).join('\n');
  return `${head}\n${body}`;
};

export default function ReportsHubModule({ token, onNavigate }) {
  const [categories, setCategories] = useState([]);
  const [active, setActive] = useState('eksekutif');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState({ preset: '30d', from: null, to: null });

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const range = useMemo(() => {
    let { from, to } = period || {};
    if (!from || !to) {
      const now = new Date();
      const t = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      const add = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
      const p = period?.preset || '30d';
      if (p === 'today') { from = iso(t); to = iso(t); }
      else if (p === '7d') { from = iso(add(t, -6)); to = iso(t); }
      else if (p === '30d') { from = iso(add(t, -29)); to = iso(t); }
      else if (p === '90d') { from = iso(add(t, -89)); to = iso(t); }
      else if (p === 'month') { from = iso(new Date(t.getFullYear(), t.getMonth(), 1)); to = iso(t); }
      else if (p === 'ytd') { from = `${t.getFullYear()}-01-01`; to = iso(t); }
    }
    return { from, to };
  }, [period]);

  useEffect(() => {
    let alive = true;
    fetch('/api/rahaza/reports-hub/categories', { headers })
      .then((r) => r.json())
      .then((d) => { if (alive) setCategories(d.items || []); })
      .catch(() => toast.error('Gagal memuat daftar kategori laporan'));
    return () => { alive = false; };
  }, [headers]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = `?category=${active}` +
        (range.from && range.to ? `&date_from=${range.from}&date_to=${range.to}` : '');
      const r = await fetch(`/api/rahaza/reports-hub/summary${qs}`, { headers });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      setData(d);
    } catch (e) {
      toast.error('Gagal memuat laporan', { description: e.message });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [active, headers, range.from, range.to]);

  useEffect(() => { load(); }, [load]);

  const downloadCsv = (table) => {
    try {
      const blob = new Blob([`\uFEFF${toCsv(table)}`], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${active}-${table.id}-${range.from}_${range.to}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`CSV "${table.title}" diunduh`);
    } catch (e) {
      toast.error('Gagal mengunduh CSV', { description: e.message });
    }
  };

  return (
    <div className="space-y-4" data-testid="reports-hub">
      <PageHeader
        icon={FileSpreadsheet}
        title="Pusat Laporan"
        subtitle="Data penting setiap portal dalam satu tempat — pilih kategori, lihat angkanya, lalu tindak lanjuti di modul terkait."
        testId="reports-hub-header"
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            <PeriodPicker value={period} onChange={setPeriod} compareEnabled={false}
                          testId="reports-hub-period" />
            <Button variant="outline" size="sm" onClick={load} data-testid="reports-hub-refresh">
              <RefreshCw className={loading ? 'animate-spin' : ''} /> Muat ulang
            </Button>
          </div>
        )}
      />

      {/* ── Pemilih kategori (per portal) ─────────────────────────────── */}
      <div className="flex flex-wrap gap-2" data-testid="reports-hub-categories">
        {categories.map((c) => {
          const Icon = CATEGORY_ICON[c.id] || FileSpreadsheet;
          const on = active === c.id;
          return (
            <button
              key={c.id} type="button" onClick={() => setActive(c.id)}
              data-testid={`reports-hub-cat-${c.id}`}
              aria-pressed={on}
              title={c.description}
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                on
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border bg-[var(--card-surface)] text-foreground/70 hover:border-primary/40 hover:bg-[var(--glass-bg-hover)]'
              }`}
            >
              <Icon className="h-4 w-4" />
              {c.label}
            </button>
          );
        })}
      </div>

      {loading && !data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
            {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-20 rounded-lg" />)}
          </div>
          <Skeleton className="h-64 rounded-lg" />
        </div>
      ) : !data ? (
        <GlassCard className="p-8 text-center" hover={false}>
          <p className="text-sm text-muted-foreground">Laporan tidak dapat dimuat. Coba muat ulang.</p>
        </GlassCard>
      ) : (
        <>
          {/* ── Konteks kategori ─────────────────────────────────────── */}
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-foreground" data-testid="reports-hub-active-label">
              {data.label}
            </h3>
            <Badge variant="outline" className="text-[10px]">{data.date_from} → {data.date_to}</Badge>
            <span className="text-xs text-muted-foreground">{data.description}</span>
          </div>

          {/* ── KPI ringkas (tile kecil, bukan kartu raksasa) ────────── */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6"
               data-testid="reports-hub-kpis">
            {data.kpis.map((k) => (
              <GlassCard key={k.label} className="p-3" hover={false}
                         data-testid={`hub-kpi-${k.label}`}>
                <p className="truncate text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {k.label}
                </p>
                <p className={`mt-1 truncate text-xl font-bold tabular-nums ${TONE_CLASS[k.tone] || 'text-foreground'}`}>
                  {kpiValue(k)}
                </p>
                {k.sub && <p className="mt-0.5 line-clamp-2 text-[10px] leading-tight text-muted-foreground">{k.sub}</p>}
              </GlassCard>
            ))}
          </div>

          {/* ── Tabel data relevan ───────────────────────────────────── */}
          {data.tables.map((t) => (
            <GlassCard key={t.id} className="p-4" hover={false} data-testid={`hub-table-${t.id}`}>
              <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h4 className="text-sm font-semibold text-foreground">{t.title}</h4>
                  {t.subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{t.subtitle}</p>}
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary" className="text-[11px]">{t.rows.length} baris</Badge>
                  {t.rows.length > 0 && (
                    <Button variant="outline" size="sm" onClick={() => downloadCsv(t)}
                            data-testid={`hub-csv-${t.id}`}>
                      <Download /> CSV
                    </Button>
                  )}
                  {t.module_id && onNavigate && (
                    <Button variant="ghost" size="sm" onClick={() => onNavigate(t.module_id)}
                            data-testid={`hub-open-${t.id}`}>
                      {t.module_label || 'Buka modul'} <ArrowRight />
                    </Button>
                  )}
                </div>
              </div>
              {t.rows.length === 0 ? (
                <p className="py-8 text-center text-xs text-muted-foreground" data-testid={`hub-empty-${t.id}`}>
                  {t.empty_hint || 'Belum ada data untuk periode ini.'}
                </p>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="w-full min-w-max text-xs">
                    <thead className="bg-[var(--glass-bg)]">
                      <tr>
                        <th className="px-3 py-2 text-left font-semibold text-muted-foreground">#</th>
                        {t.columns.map((c) => (
                          <th key={c.key}
                              className={`px-3 py-2 font-semibold text-muted-foreground ${
                                ['number', 'currency'].includes(c.format) ? 'text-right' : 'text-left'
                              }`}>
                            {c.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {t.rows.map((row, idx) => (
                        <tr key={idx} className="border-t border-border hover:bg-[var(--glass-bg-hover)]">
                          <td className="px-3 py-2 text-muted-foreground">{idx + 1}</td>
                          {t.columns.map((c) => (
                            <td key={c.key}
                                className={`px-3 py-2 text-foreground ${
                                  ['number', 'currency'].includes(c.format) ? 'text-right tabular-nums' : 'text-left'
                                }`}>
                              {renderCell(row[c.key], c.format)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </GlassCard>
          ))}

          {/* ── Jejak sumber ─────────────────────────────────────────── */}
          {data.sources?.length > 0 && (
            <div className="rounded-lg border border-border bg-[var(--glass-bg)] px-3 py-2"
                 data-testid="reports-hub-source-trace">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <Database className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[11px] font-semibold text-muted-foreground">Sumber data:</span>
                {data.sources.map((s) => (
                  <span key={s.collection} title={s.note || ''}
                        className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    <span className="font-mono">{s.collection}</span>
                    <span className="ml-1 font-semibold text-foreground">{fmtNum(s.count)}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {loading && (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Memuat ulang...
            </p>
          )}
        </>
      )}
    </div>
  );
}
