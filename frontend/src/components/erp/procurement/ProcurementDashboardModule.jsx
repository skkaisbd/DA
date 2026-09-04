/**
 * ProcurementDashboardModule — Dashboard Portal Pengadaan
 *
 * Membaca `/api/procurement/overview` + `/pipeline` yang meng-agregat SELURUH
 * koleksi siklus pengadaan (PR, PO, GR, inspeksi QC, AP, master supplier,
 * price list, PR aksesoris) — bukan satu koleksi saja.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle, ArrowRight, BadgeCheck, Banknote, Boxes, Building2,
  CalendarClock, CheckCircle2, ClipboardList, FileText, PackageCheck,
  RefreshCw, ShieldAlert, ShoppingCart, Tag, TrendingUp, Truck,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { EP, apiGet, fmtDate, fmtRp } from './procApi';

function Kpi({ icon: Icon, label, value, sub, tone = 'default', onClick, testId }) {
  const TONE = {
    default: 'text-foreground',
    info: 'text-blue-600 dark:text-blue-400',
    warn: 'text-amber-700 dark:text-amber-400',
    danger: 'text-red-700 dark:text-red-400',
    ok: 'text-emerald-600 dark:text-emerald-400',
  };
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      data-testid={testId}
      className={`text-left w-full rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] p-4 transition-colors ${onClick ? 'hover:bg-[var(--glass-bg-hover)] cursor-pointer' : 'cursor-default'}`}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.12)] border border-[hsl(var(--primary)/0.25)]">
          <Icon className="w-3.5 h-3.5 text-[hsl(var(--primary))]" />
        </span>
        <span className="text-xs text-muted-foreground line-clamp-1">{label}</span>
      </div>
      <div className={`text-2xl font-bold tabular-nums ${TONE[tone]}`}>{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground mt-0.5 line-clamp-1">{sub}</div>}
    </button>
  );
}

function FunnelBar({ title, rows, icon: Icon }) {
  const total = (rows || []).reduce((s, r) => s + (r.count || 0), 0);
  return (
    <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-[hsl(var(--primary))]" />
          <h4 className="text-sm font-semibold">{title}</h4>
        </div>
        <span className="text-xs text-muted-foreground tabular-nums">{total} dok</span>
      </div>
      {(rows || []).length === 0 ? (
        <p className="text-xs text-muted-foreground py-2">Belum ada dokumen pada periode ini.</p>
      ) : (
        <div className="space-y-1.5">
          {rows.map((r) => (
            <div key={r.status} className="flex items-center gap-2">
              <span className="text-[11px] w-36 shrink-0 text-muted-foreground line-clamp-1">{r.status}</span>
              <div className="flex-1 h-2 rounded-full bg-[hsl(var(--muted)/0.6)] overflow-hidden">
                <div
                  className="h-full rounded-full bg-[hsl(var(--primary))]"
                  style={{ width: `${total ? Math.max(4, (r.count / total) * 100) : 0}%` }}
                />
              </div>
              <span className="text-[11px] tabular-nums w-8 text-right">{r.count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ProcurementDashboardModule({ token, onNavigate }) {
  const [ov, setOv] = useState(null);
  const [pipe, setPipe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const [o, p] = await Promise.all([
        apiGet(token, EP.overview),
        apiGet(token, EP.pipeline),
      ]);
      setOv(o);
      setPipe(p);
    } catch (e) {
      setErr(e.message);
      toast.error(`Gagal memuat dashboard pengadaan: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64" data-testid="proc-dashboard-loading">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[hsl(var(--primary))]" />
      </div>
    );
  }

  const k = ov?.kpi || {};
  const alerts = ov?.alerts || {};

  return (
    <div className="space-y-5" data-testid="proc-dashboard-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Dashboard Pengadaan</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Ringkasan siklus pengadaan: permintaan, pesanan, penerimaan, dan faktur supplier.
          </p>
        </div>
        <Button variant="secondary" onClick={load} data-testid="proc-dashboard-refresh">
          <RefreshCw className="w-4 h-4 mr-1.5" /> Muat Ulang
        </Button>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/30 text-red-700 dark:text-red-300 text-sm">
          {err}
        </div>
      )}

      {/* KPI utama */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi icon={ClipboardList} label="Permintaan menunggu" value={k.pr_pending ?? 0}
             sub={`${k.pr_total ?? 0} total permintaan`} tone="warn"
             onClick={() => onNavigate?.('proc-requests')} testId="proc-kpi-pr-pending" />
        <Kpi icon={ShoppingCart} label="PO berjalan" value={k.po_open ?? 0}
             sub={`Nilai ${fmtRp(k.open_po_value)}`} tone="info"
             onClick={() => onNavigate?.('proc-purchase-orders')} testId="proc-kpi-po-open" />
        <Kpi icon={Truck} label="Penerimaan diterima" value={k.gr_received ?? 0}
             sub={`${k.gr_draft ?? 0} draft menunggu`} tone="ok"
             testId="proc-kpi-gr" />
        <Kpi icon={Banknote} label="Hutang supplier" value={fmtRp(k.ap_outstanding)}
             sub={`${k.ap_unpaid ?? 0} faktur belum lunas`} tone="danger"
             onClick={() => onNavigate?.('proc-ap-invoices')} testId="proc-kpi-ap" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi icon={Building2} label="Supplier aktif" value={k.suppliers_active ?? 0}
             sub={`${k.suppliers_total ?? 0} total di master`}
             onClick={() => onNavigate?.('proc-suppliers')} testId="proc-kpi-suppliers" />
        <Kpi icon={Tag} label="Baris daftar harga" value={k.price_list_rows ?? 0}
             sub="Harga per satuan beli"
             onClick={() => onNavigate?.('proc-suppliers')} testId="proc-kpi-price-rows" />
        <Kpi icon={TrendingUp} label="Belanja bulan ini" value={fmtRp(k.po_value_this_month)}
             sub={`${k.po_completed ?? 0} PO selesai`}
             onClick={() => onNavigate?.('proc-analytics')} testId="proc-kpi-spend-month" />
        <Kpi icon={PackageCheck} label="Request aksesoris" value={k.accessory_pr_total ?? 0}
             sub={`${k.accessory_pr_awaiting_approval ?? 0} menunggu persetujuan · ${k.accessory_pr_pending ?? 0} berjalan`}
             onClick={() => onNavigate?.('proc-accessory-pr')} testId="proc-kpi-acc-pr" />
      </div>

      {/* Antrean kerja + peringatan */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <GlassCard className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <ShieldAlert className="w-4 h-4 text-red-600 dark:text-red-400" />
            <h3 className="font-semibold text-sm">PO melewati tanggal terima</h3>
            <span className="ml-auto text-xs text-muted-foreground tabular-nums">
              {(alerts.po_overdue || []).length}
            </span>
          </div>
          {(alerts.po_overdue || []).length === 0 ? (
            <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400 py-3">
              <CheckCircle2 className="w-4 h-4" /> Tidak ada PO yang telat.
            </div>
          ) : (
            <div className="space-y-2" data-testid="proc-alert-overdue">
              {(alerts.po_overdue || []).slice(0, 6).map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => onNavigate?.('proc-purchase-orders')}
                  className="w-full text-left flex items-center gap-3 p-2 rounded-lg border border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)]"
                >
                  <span className="font-mono text-xs">{p.po_number}</span>
                  <span className="text-xs text-muted-foreground line-clamp-1 flex-1">{p.vendor_name}</span>
                  <span className="text-xs text-red-600 dark:text-red-400">{fmtDate(p.expected_delivery_date)}</span>
                  <ArrowRight className="w-3.5 h-3.5 text-muted-foreground" />
                </button>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <CalendarClock className="w-4 h-4 text-amber-600 dark:text-amber-400" />
            <h3 className="font-semibold text-sm">Jatuh tempo 7 hari</h3>
            <span className="ml-auto text-xs text-muted-foreground tabular-nums">
              {(alerts.po_due_soon || []).length}
            </span>
          </div>
          {(alerts.po_due_soon || []).length === 0 ? (
            <p className="text-sm text-muted-foreground py-3">Tidak ada PO jatuh tempo minggu ini.</p>
          ) : (
            <div className="space-y-2" data-testid="proc-alert-due-soon">
              {(alerts.po_due_soon || []).slice(0, 6).map((p) => (
                <div key={p.id} className="flex items-center gap-3 p-2 rounded-lg border border-[var(--glass-border)]">
                  <span className="font-mono text-xs">{p.po_number}</span>
                  <span className="text-xs text-muted-foreground line-clamp-1 flex-1">{p.vendor_name}</span>
                  <span className="text-xs text-amber-700 dark:text-amber-400">{fmtDate(p.expected_delivery_date)}</span>
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      </div>

      {(alerts.po_without_supplier_master || 0) > 0 && (
        <div className="flex items-start gap-3 p-4 rounded-xl border border-amber-300 dark:border-amber-400/30 bg-amber-50 dark:bg-amber-400/10"
             data-testid="proc-alert-unlinked-supplier">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">
              {alerts.po_without_supplier_master} PO belum tertaut Master Supplier
            </p>
            <p className="text-xs text-amber-700 dark:text-amber-400/80 mt-0.5">
              PO lama masih memakai nama supplier teks bebas. Jalankan tarik data di Master Supplier
              supaya penilaian supplier tidak terpecah oleh perbedaan ejaan.
            </p>
          </div>
          <Button size="sm" variant="secondary" onClick={() => onNavigate?.('proc-suppliers')}
                  data-testid="proc-alert-goto-suppliers">
            Buka Master Supplier
          </Button>
        </div>
      )}

      {/* Funnel P2P */}
      <div>
        <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
          <BadgeCheck className="w-4 h-4 text-[hsl(var(--primary))]" />
          Alur Pengadaan 90 Hari
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          <FunnelBar title="Permintaan" rows={pipe?.requests} icon={ClipboardList} />
          <FunnelBar title="Purchase Order" rows={pipe?.purchase_orders} icon={ShoppingCart} />
          <FunnelBar title="Penerimaan" rows={pipe?.goods_receipts} icon={Truck} />
          <FunnelBar title="Faktur Supplier" rows={pipe?.ap_invoices} icon={FileText} />
        </div>
      </div>

      {/* Aktivitas terbaru */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <GlassCard className="p-4">
          <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
            <ClipboardList className="w-4 h-4" /> Permintaan Terbaru
          </h3>
          {(ov?.recent?.requests || []).length === 0 ? (
            <p className="text-sm text-muted-foreground py-3">Belum ada permintaan pengadaan.</p>
          ) : (
            <table className="w-full text-sm" data-testid="proc-recent-pr">
              <tbody>
                {ov.recent.requests.map((r) => (
                  <tr key={r.id} className="border-b border-[var(--glass-border)] last:border-0">
                    <td className="py-2 font-mono text-xs w-32">{r.request_number}</td>
                    <td className="py-2 text-xs line-clamp-1">{r.title}</td>
                    <td className="py-2 text-xs text-right tabular-nums">{fmtRp(r.total_estimated)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </GlassCard>

        <GlassCard className="p-4">
          <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
            <Boxes className="w-4 h-4" /> Purchase Order Terbaru
          </h3>
          {(ov?.recent?.purchase_orders || []).length === 0 ? (
            <p className="text-sm text-muted-foreground py-3">Belum ada purchase order.</p>
          ) : (
            <table className="w-full text-sm" data-testid="proc-recent-po">
              <tbody>
                {ov.recent.purchase_orders.map((p) => (
                  <tr key={p.id} className="border-b border-[var(--glass-border)] last:border-0">
                    <td className="py-2 font-mono text-xs w-36">{p.po_number}</td>
                    <td className="py-2 text-xs line-clamp-1">{p.vendor_name}</td>
                    <td className="py-2 text-xs text-right tabular-nums">{fmtRp(p.total_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </GlassCard>
      </div>
    </div>
  );
}
