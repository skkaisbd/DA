/**
 * CuttingDashboard — ringkasan Portal Cutting.
 * Menjawab 3 pertanyaan operasional: berapa yang jalan, berapa hasilnya,
 * dan seberapa efisien kain dipakai (yield pcs per satuan kain).
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Scissors, Layers, PackageCheck, RefreshCw, TrendingUp,
  Trash2, PlayCircle, FileStack, AlertCircle,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { cuttingApi, StatusPill, fmtNum, fmtDateTime } from './cuttingApi';

function KPI({ label, value, sub, icon: Icon, tone = 'primary', testid }) {
  const tones = {
    primary: 'text-[hsl(var(--primary))] bg-[hsl(var(--primary)/0.12)] border-[hsl(var(--primary)/0.25)]',
    amber: 'text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/25',
    emerald: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/25',
    sky: 'text-sky-600 dark:text-sky-400 bg-sky-500/10 border-sky-500/25',
    rose: 'text-rose-600 dark:text-rose-400 bg-rose-500/10 border-rose-500/25',
  };
  return (
    <GlassCard className="p-4" data-testid={testid}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground truncate">{label}</p>
          <p className="text-2xl font-bold text-foreground mt-1 tabular-nums">{value}</p>
          {sub && <p className="text-[11px] text-muted-foreground mt-1">{sub}</p>}
        </div>
        <div className={`w-9 h-9 rounded-xl border grid place-items-center shrink-0 ${tones[tone]}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
    </GlassCard>
  );
}

export default function CuttingDashboard({ token, onNavigate }) {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setErr('');
    try {
      setD(await cuttingApi('GET', '/dashboard', token));
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const by = d?.by_status || {};

  return (
    <div className="space-y-5" data-testid="cutting-dashboard">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-2xl bg-orange-500/12 border border-orange-500/25 grid place-items-center">
            <Scissors className="w-5 h-5 text-orange-600 dark:text-orange-400" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-foreground">Dashboard Cutting</h2>
            <p className="text-sm text-muted-foreground">
              Roll kain dipotong menjadi kain pola (potongan) — material siap jadi BOM produksi.
            </p>
          </div>
        </div>
        <button
          onClick={load}
          className="inline-flex items-center gap-2 h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] text-sm text-foreground hover:bg-[var(--nav-pill-active)] transition-colors"
          data-testid="cutting-dash-refresh"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Muat Ulang
        </button>
      </div>

      {err && (
        <div className="flex items-center gap-2 p-3 rounded-lg border border-red-300 bg-red-50 dark:bg-red-500/10 dark:border-red-500/30 text-sm text-red-700 dark:text-red-300">
          <AlertCircle className="w-4 h-4 shrink-0" /> {err}
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPI label="Total Order Cutting" value={fmtNum(d?.total_orders)} icon={FileStack}
             sub={`${by.draft || 0} draft · ${by.cancelled || 0} batal`} testid="cutting-kpi-total" />
        <KPI label="Sedang Berjalan" value={fmtNum(by.in_progress)} icon={PlayCircle} tone="amber"
             sub="Menunggu input progres" testid="cutting-kpi-running" />
        <KPI label="Potongan Dihasilkan" value={`${fmtNum(d?.produced_qty)} pcs`} icon={PackageCheck} tone="emerald"
             sub={`dari rencana ${fmtNum(d?.planned_output_qty)} pcs`} testid="cutting-kpi-produced" />
        <KPI label="Rata-rata Yield" value={fmtNum(d?.avg_yield, 2)} icon={TrendingUp} tone="sky"
             sub="pcs potongan per satuan kain" testid="cutting-kpi-yield" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <KPI label="Kain Terpakai" value={fmtNum(d?.consumed_input_qty, 2)} icon={Layers}
             sub="akumulasi seluruh order (satuan kain)" testid="cutting-kpi-consumed" />
        <KPI label="Sisa / Waste" value={fmtNum(d?.waste_qty, 2)} icon={Trash2} tone="rose"
             sub="tercatat saat input progres" testid="cutting-kpi-waste" />
        <KPI label="Master Potongan" value={fmtNum(d?.output_material_count)} icon={Scissors} tone="emerald"
             sub="item material hasil cutting" testid="cutting-kpi-panels" />
      </div>

      <GlassCard className="p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--glass-border)] flex items-center justify-between">
          <h3 className="text-sm font-semibold text-foreground">Cutting Terbaru</h3>
          <button
            onClick={() => onNavigate?.('cutting-orders')}
            className="text-xs text-[hsl(var(--primary))] hover:underline"
            data-testid="cutting-dash-goto-orders"
          >
            Lihat semua →
          </button>
        </div>
        {loading && !d ? (
          <div className="p-6 space-y-2">
            {[0, 1, 2].map((i) => <div key={i} className="h-8 rounded-lg bg-foreground/5 animate-pulse" />)}
          </div>
        ) : (d?.recent || []).length === 0 ? (
          <div className="p-10 text-center">
            <Scissors className="w-8 h-8 mx-auto text-muted-foreground/40" />
            <p className="mt-2 text-sm text-muted-foreground">Belum ada order cutting.</p>
            <button
              onClick={() => onNavigate?.('cutting-orders')}
              className="mt-3 inline-flex items-center gap-2 h-9 px-3 rounded-lg bg-[hsl(var(--primary))] text-white text-sm"
              data-testid="cutting-dash-create-first"
            >
              Buat Cutting Pertama
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="px-4 py-2 font-medium">Nomor</th>
                  <th className="px-4 py-2 font-medium">Style</th>
                  <th className="px-4 py-2 font-medium">Kain</th>
                  <th className="px-4 py-2 font-medium text-right">Hasil</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Dibuat</th>
                </tr>
              </thead>
              <tbody>
                {(d?.recent || []).map((r) => (
                  <tr key={r.id} className="border-b border-[var(--glass-border)] last:border-0 hover:bg-[var(--nav-pill-active)]/40">
                    <td className="px-4 py-2 font-mono text-xs text-foreground">{r.number}</td>
                    <td className="px-4 py-2 text-foreground">{r.style_name || '-'}</td>
                    <td className="px-4 py-2 text-muted-foreground text-xs">{r.input_material_name}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-foreground">
                      {fmtNum(r.produced_qty)} / {fmtNum(r.planned_output_qty)} pcs
                    </td>
                    <td className="px-4 py-2"><StatusPill status={r.status} /></td>
                    <td className="px-4 py-2 text-xs text-muted-foreground">{fmtDateTime(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      <GlassCard className="p-4">
        <h3 className="text-sm font-semibold text-foreground mb-2">Alur Cutting</h3>
        <ol className="text-xs text-muted-foreground space-y-1.5 list-decimal list-inside">
          <li><b className="text-foreground">Buat Cutting</b> — pilih kain dari master material Gudang + rencana pemakaian & target potongan.</li>
          <li><b className="text-foreground">Mulai</b> — sistem membuat item master <i>Potongan</i> baru (satuan pcs) untuk style/warna/size ini.</li>
          <li><b className="text-foreground">Input Progres</b> — tiap kali memotong: stok kain berkurang, stok potongan bertambah (tercatat di ledger gudang).</li>
          <li><b className="text-foreground">Selesai</b> — HPP potongan dihitung otomatis dari biaya kain terpakai.</li>
          <li>Potongan siap dipakai sebagai <b className="text-foreground">BOM produksi</b> dan dikeluarkan lewat <b className="text-foreground">Pengeluaran Material</b> / Kirim Material CMT.</li>
        </ol>
      </GlassCard>
    </div>
  );
}
