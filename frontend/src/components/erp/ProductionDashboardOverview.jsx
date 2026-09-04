/**
 * Dashboard Produksi — mengikuti alur nyata pabrik (2026).
 *
 * Jahit dikerjakan vendor CMT dan Cutting punya portal sendiri, jadi WIP per
 * proses internal (Cutting→Sewing→Finishing→QC→Packing) sudah tidak berarti —
 * angkanya selalu nol. Dashboard sekarang memetakan rantai yang benar:
 *   Rencana PO → Cutting → Di Vendor CMT → Terima & QC → Permak → Serah Terima FG
 * Sumber angka: GET /api/prod/dashboard (satu panggilan).
 */
import { useEffect, useState, useCallback } from 'react';
import {
  RefreshCw, Factory, Scissors, Truck, ClipboardCheck, Wrench, PackageCheck,
  AlertTriangle, ChevronRight, Clock, Percent, Boxes,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { StatCard, ChartCard, HeroCrystalCard } from './dashboardAtoms';
import NextActionWidget from './NextActionWidget';
import SetupWizard from './SetupWizard';

const API = process.env.REACT_APP_BACKEND_URL || '';
const n = (v) => Number(v || 0).toLocaleString('id-ID');

const STAGE_ICON = {
  rencana: Factory, cutting: Scissors, vendor: Truck,
  qc: ClipboardCheck, permak: Wrench, kirim: PackageCheck,
};

export default function ProductionDashboardOverview({ token, onNavigate, businessType = 'internal' }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [updatedAt, setUpdatedAt] = useState('');
  const [wizardOpen, setWizardOpen] = useState(false);
  const [naeNonce, setNaeNonce] = useState(0);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/prod/dashboard?business_type=${businessType}&days=${days}`,
        { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        setData(await res.json());
        setUpdatedAt(new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }));
      }
    } finally { setLoading(false); }
  }, [token, days, businessType]);

  useEffect(() => { const t = setTimeout(fetchData, 0); return () => clearTimeout(t); }, [fetchData]);
  useEffect(() => { const t = setInterval(fetchData, 60000); return () => clearInterval(t); }, [fetchData]);

  const s = data?.ringkasan || {};
  const pipeline = data?.pipeline || [];
  const maxStage = Math.max(1, ...pipeline.map(p => p.qty || 0));
  const cut = data?.cutting || {};
  const vendor = data?.vendor || {};
  const qc = data?.qc || {};

  return (
    <div className="space-y-5" data-testid="production-dashboard-overview">
      <HeroCrystalCard
        testId="prod-hero"
        eyebrow={businessType === 'internal' ? 'Portal Produksi' : 'Portal Maklon'}
        title="Alur Produksi Berjalan"
        description="Cutting dikerjakan sendiri, jahit oleh vendor CMT. Angka di bawah mengikuti perjalanan barang: rencana → potong → vendor → periksa → serah terima."
      >
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1 p-1 rounded-lg bg-foreground/5" data-testid="prod-period-switch">
            {[7, 30, 90].map(d => (
              <button key={d} onClick={() => setDays(d)} data-testid={`prod-period-${d}`}
                className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                  days === d ? 'bg-background shadow-sm font-medium' : 'text-foreground/60 hover:text-foreground'}`}>
                {d} hari
              </button>
            ))}
          </div>
          <Button onClick={fetchData} className="h-9 bg-[hsl(var(--primary))] hover:brightness-110" data-testid="prod-dash-refresh">
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
            {loading ? 'Memuat...' : 'Refresh'}
          </Button>
          {updatedAt && <span className="text-xs text-foreground/50">Diperbarui: {updatedAt}</span>}
        </div>
      </HeroCrystalCard>

      <NextActionWidget
        key={naeNonce}
        token={token}
        portal="production"
        onNavigate={(m) => onNavigate && onNavigate(m)}
        onOpenSetupWizard={() => setWizardOpen(true)}
        maxCards={5}
      />

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <StatCard testId="kpi-po-aktif" icon={Factory} label="PO Berjalan"
          value={n(s.po_aktif)} sub={`${n(s.qty_aktif)} pcs direncanakan`} accent="primary" />
        <StatCard testId="kpi-di-vendor" icon={Truck} label="Di Vendor CMT"
          value={n(s.di_vendor)} sub="pcs dikirim, belum kembali"
          accent={s.di_vendor > 0 ? 'warning' : 'success'}
          onClick={onNavigate ? () => onNavigate('prod-shipments-vendor') : undefined} />
        <StatCard testId="kpi-menunggu-qc" icon={ClipboardCheck} label="Menunggu Periksa"
          value={n(s.menunggu_qc)} sub="pcs belum di-approve"
          accent={s.menunggu_qc > 0 ? 'warning' : 'success'}
          onClick={onNavigate ? () => onNavigate('da-cmt-receive') : undefined} />
        <StatCard testId="kpi-cacat" icon={Percent} label="Tingkat Cacat"
          value={`${s.tingkat_cacat ?? 0}%`} sub={`${n(qc.qty_ditolak)} dari ${n((qc.qty_diterima || 0) + (qc.qty_ditolak || 0))} pcs`}
          accent={(s.tingkat_cacat || 0) > 5 ? 'warning' : 'success'} />
        <StatCard testId="kpi-keluar" icon={PackageCheck} label={data?.handover?.label || 'Barang Keluar'}
          value={n(s.keluar_periode)} sub={`pcs dalam ${days} hari`} accent="success"
          onClick={onNavigate ? () => onNavigate('prod-shipments-buyer') : undefined} />
      </div>

      <ChartCard
        title="Perjalanan Barang"
        subtitle="Setiap tahap menampilkan jumlah barang yang SEDANG berada di sana. Klik untuk membuka modulnya."
        testId="prod-pipeline-card"
      >
        {pipeline.every(p => !p.qty && !p.count) ? (
          <div className="text-center py-10 text-foreground/40 text-sm" data-testid="prod-pipeline-empty">
            {loading ? 'Memuat data…' : 'Belum ada PO berjalan. Mulai dari “PO Internal” untuk membuat perintah produksi.'}
          </div>
        ) : (
          <div className="flex flex-wrap items-stretch gap-1">
            {pipeline.map((p, i) => {
              const Icon = STAGE_ICON[p.stage] || Boxes;
              const pct = Math.round(((p.qty || 0) / maxStage) * 100);
              const aktif = (p.qty || 0) > 0 || (p.count || 0) > 0;
              return (
                <div key={p.stage} className="flex items-stretch flex-1 min-w-[140px]">
                  <button
                    onClick={() => onNavigate && p.module && onNavigate(p.module)}
                    data-testid={`prod-stage-${p.stage}`}
                    className={`flex-1 text-left rounded-xl border p-3 transition-colors ${
                      aktif ? 'border-[hsl(var(--primary)/0.35)] bg-[hsl(var(--primary)/0.05)] hover:bg-[hsl(var(--primary)/0.1)]'
                            : 'border-[var(--glass-border)] hover:bg-foreground/[0.03]'}`}
                  >
                    <div className="flex items-center gap-1.5 mb-2">
                      <Icon className={`w-3.5 h-3.5 ${aktif ? 'text-[hsl(var(--primary))]' : 'text-foreground/40'}`} />
                      <span className="text-[11px] font-semibold text-foreground/70 truncate">{p.label}</span>
                    </div>
                    <div className="text-2xl font-bold tabular-nums leading-none">{n(p.qty)}</div>
                    <div className="text-[11px] text-foreground/50 mt-1">{n(p.count)} dokumen</div>
                    <div className="h-1.5 rounded-full bg-[var(--glass-bg)] mt-2 overflow-hidden">
                      <div className="h-full bg-[hsl(var(--primary))] transition-[width] duration-500"
                        style={{ width: `${pct}%` }} />
                    </div>
                  </button>
                  {i < pipeline.length - 1 && (
                    <ChevronRight className="w-4 h-4 text-foreground/25 self-center shrink-0 mx-0.5" />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </ChartCard>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard title="Cutting" subtitle="Kain → potongan siap jahit" testId="prod-cutting-card">
          <div className="grid grid-cols-2 gap-2 mb-3">
            {[['Order berjalan', cut.in_progress], ['Order selesai', cut.completed],
              ['Pcs sedang dipotong', cut.qty_dalam_proses], ['Pcs potongan jadi', cut.qty_potongan_jadi]].map(([l, v]) => (
              <div key={l} className="rounded-lg bg-foreground/[0.03] p-2.5">
                <div className="text-[11px] text-foreground/55">{l}</div>
                <div className="text-lg font-bold tabular-nums">{n(v)}</div>
              </div>
            ))}
          </div>
          <div className="text-xs text-foreground/60 space-y-1 pt-2 border-t border-[var(--glass-border)]">
            <div className="flex justify-between"><span>Kain terpakai</span><b className="text-foreground">{n(cut.kain_terpakai)}</b></div>
            <div className="flex justify-between"><span>Rendemen (pcs / satuan kain)</span><b className="text-foreground">{cut.rendemen ?? 0}</b></div>
            <div className="flex justify-between"><span>Jenis potongan aktif</span><b className="text-foreground">{n(cut.panel_aktif)}</b></div>
          </div>
          <Button variant="ghost" className="w-full mt-3 h-8 text-xs border border-[var(--glass-border)]"
            onClick={() => onNavigate && onNavigate('cutting-orders')} data-testid="prod-goto-cutting">
            Buka Order Cutting
          </Button>
        </ChartCard>

        <ChartCard title="Beban Vendor CMT" subtitle="Barang yang masih dipegang penjahit" testId="prod-vendor-card">
          {(vendor.per_vendor || []).length === 0 ? (
            <div className="text-center py-8 text-foreground/40 text-sm">Belum ada pengiriman ke vendor.</div>
          ) : (
            <div className="space-y-2.5">
              {vendor.per_vendor.map(v => {
                const pct = v.qty_kirim > 0 ? Math.round((v.qty_kembali / v.qty_kirim) * 100) : 0;
                return (
                  <div key={v.vendor} data-testid={`prod-vendor-row-${v.vendor}`}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-medium truncate">{v.vendor}</span>
                      <span className="tabular-nums text-foreground/60">
                        {n(v.qty_kembali)}/{n(v.qty_kirim)} kembali · <b className="text-foreground">{n(v.outstanding)}</b> di vendor
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-[var(--glass-bg)] overflow-hidden">
                      <div className="h-full bg-[hsl(var(--success))] transition-[width] duration-500" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
              <div className="flex justify-between text-xs pt-2 mt-1 border-t border-[var(--glass-border)]">
                <span className="text-foreground/60">Total masih di vendor</span>
                <b>{n(vendor.outstanding)} pcs</b>
              </div>
            </div>
          )}
        </ChartCard>

        <ChartCard title="Terima & Mutu" subtitle="Hasil jahit yang kembali dari vendor" testId="prod-qc-card">
          <div className="grid grid-cols-2 gap-2 mb-3">
            {[['Menunggu hitung', qc.draft], ['Menunggu approval', qc.submitted],
              ['Pcs lolos', qc.qty_diterima], ['Pcs ditolak', qc.qty_ditolak]].map(([l, v]) => (
              <div key={l} className="rounded-lg bg-foreground/[0.03] p-2.5">
                <div className="text-[11px] text-foreground/55">{l}</div>
                <div className="text-lg font-bold tabular-nums">{n(v)}</div>
              </div>
            ))}
          </div>
          <div className="text-xs text-foreground/60 space-y-1 pt-2 border-t border-[var(--glass-border)]">
            <div className="flex justify-between"><span>Masuk hari ini</span><b className="text-foreground">{n(qc.pcs_hari_ini)} pcs</b></div>
            <div className="flex justify-between"><span>Permak terbuka</span><b className="text-foreground">{n(data?.permak?.terbuka)} ({n(data?.permak?.qty_terbuka)} pcs)</b></div>
            <div className="flex justify-between"><span>Vendor aktif</span><b className="text-foreground">{n(qc.vendor_aktif)}</b></div>
          </div>
          <Button variant="ghost" className="w-full mt-3 h-8 text-xs border border-[var(--glass-border)]"
            onClick={() => onNavigate && onNavigate('da-cmt-receive')} data-testid="prod-goto-receive">
            Buka Terima FG dari CMT
          </Button>
        </ChartCard>
      </div>

      <ChartCard
        title="PO Paling Lama Tidak Bergerak"
        subtitle="Urut dari yang statusnya paling lama tidak berubah — inilah hambatan alur yang perlu didorong."
        testId="prod-aging-card"
      >
        {(data?.aging || []).length === 0 ? (
          <div className="text-center py-8 text-foreground/40 text-sm">
            {loading ? 'Memuat data…' : 'Tidak ada PO berjalan.'}
          </div>
        ) : (
          <div className="space-y-1.5">
            {data.aging.map(a => (
              <button key={a.po_id} onClick={() => onNavigate && onNavigate(businessType === 'internal' ? 'prod-pos-internal' : 'maklon-pos-engine')}
                data-testid={`prod-aging-${a.po_number}`}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left hover:bg-foreground/[0.04] transition-colors">
                <Clock className={`w-4 h-4 shrink-0 ${a.hari_diam >= 7 ? 'text-[hsl(var(--warning))]' : 'text-foreground/35'}`} />
                <span className="font-mono text-xs font-semibold w-32 truncate">{a.po_number}</span>
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-foreground/[0.06] shrink-0">{a.status}</span>
                <span className="text-xs text-foreground/55 truncate flex-1">{a.customer}</span>
                <span className="text-xs tabular-nums text-foreground/60">{n(a.qty)} pcs</span>
                <span className={`text-xs tabular-nums font-semibold w-20 text-right ${a.hari_diam >= 7 ? 'text-[hsl(var(--warning))]' : 'text-foreground/60'}`}>
                  {a.hari_diam} hari
                </span>
              </button>
            ))}
            {(data.aging || []).some(a => a.hari_diam >= 7) && (
              <p className="flex items-center gap-1.5 text-[11px] text-[hsl(var(--warning))] pt-2 mt-1 border-t border-[var(--glass-border)]">
                <AlertTriangle className="w-3 h-3" />
                PO yang diam ≥ 7 hari biasanya menunggu tindakan: kirim material, tagih vendor, atau approve penerimaan.
              </p>
            )}
          </div>
        )}
      </ChartCard>

      <SetupWizard
        open={wizardOpen}
        token={token}
        onClose={() => setWizardOpen(false)}
        onNavigate={(m) => onNavigate && onNavigate(m)}
        onComplete={() => { setNaeNonce((v) => v + 1); fetchData(); }}
      />
    </div>
  );
}
