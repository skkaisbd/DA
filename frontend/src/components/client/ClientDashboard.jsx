import { useEffect, useState } from 'react';
import {
  ShoppingBag,
  Sparkles,
  Receipt,
  AlertTriangle,
  TrendingUp,
  Package,
  ArrowRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { clientApi, fmtCurrency, fmtDate, ORDER_STAGE_LABEL, SAMPLE_STATUS_LABEL } from './clientApi';

function StatCard({ icon: Icon, label, value, sub, accent, testId }) {
  return (
    <div
      className="rounded-2xl border border-foreground/10 bg-foreground/[0.03] p-5"
      data-testid={testId}
    >
      <div className="flex items-start justify-between mb-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${accent}`}>
          <Icon size={18} />
        </div>
      </div>
      <div className="text-3xl font-bold text-foreground tabular-nums leading-none">
        {value}
      </div>
      <div className="text-xs text-foreground/55 mt-1.5 uppercase tracking-wider">{label}</div>
      {sub && <div className="text-xs text-foreground/45 mt-1">{sub}</div>}
    </div>
  );
}

export default function ClientDashboard({ token, onNavigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancel = false;
    (async () => {
      setLoading(true);
      try {
        const d = await clientApi.request('/dashboard', { token });
        if (!cancel) setData(d);
      } catch (e) {
        // ignore
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => {
      cancel = true;
    };
  }, [token]);

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse" data-testid="client-dashboard-loading">
        <div className="h-7 w-56 bg-foreground/10 rounded" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 rounded-2xl bg-foreground/[0.05]" />
          ))}
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-12 text-foreground/50">
        Tidak dapat memuat dashboard.
      </div>
    );
  }

  return (
    <div className="space-y-7" data-testid="client-dashboard">
      <div>
        <div className="text-xs uppercase tracking-[0.18em] text-foreground/45 mb-1">
          Selamat Datang
        </div>
        <h1 className="text-3xl font-bold text-foreground" data-testid="client-dashboard-title">
          Dashboard Klien
        </h1>
        <p className="text-sm text-foreground/55 mt-1">
          Pantau order, sample, dan invoice Anda secara real-time.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={ShoppingBag}
          label="Total Order"
          value={data.orders.total}
          sub={`${data.orders.active} aktif · ${data.orders.completed} selesai`}
          accent="bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))]"
          testId="client-stat-orders"
        />
        <StatCard
          icon={Sparkles}
          label="Menunggu Approval"
          value={data.samples.pending_approval}
          sub="Sample butuh keputusan Anda"
          accent="bg-amber-500/15 text-amber-400"
          testId="client-stat-samples"
        />
        <StatCard
          icon={Receipt}
          label="Tagihan Belum Lunas"
          value={data.invoices.outstanding_count}
          sub={fmtCurrency(data.invoices.outstanding_amount)}
          accent="bg-emerald-500/15 text-emerald-400"
          testId="client-stat-outstanding"
        />
        <StatCard
          icon={AlertTriangle}
          label="Lewat Jatuh Tempo"
          value={data.invoices.overdue_count}
          sub={data.invoices.overdue_count > 0 ? 'Mohon segera dilunasi' : 'Aman'}
          accent={
            data.invoices.overdue_count > 0
              ? 'bg-red-500/15 text-red-400'
              : 'bg-foreground/10 text-foreground/50'
          }
          testId="client-stat-overdue"
        />
      </div>

      {/* Pending samples spotlight */}
      {data.pending_samples?.length > 0 && (
        <section
          className="rounded-2xl border border-amber-400/25 bg-amber-400/5 p-5"
          data-testid="client-pending-samples-section"
        >
          <div className="flex items-start gap-3 mb-4">
            <div className="w-9 h-9 rounded-xl bg-amber-500/15 text-amber-400 flex items-center justify-center">
              <Sparkles size={18} />
            </div>
            <div className="flex-1">
              <h2 className="font-semibold text-foreground">
                {data.samples.pending_approval} Sample Butuh Keputusan Anda
              </h2>
              <p className="text-xs text-foreground/55 mt-0.5">
                Tinjau & berikan approval untuk melanjutkan produksi.
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onNavigate('samples')}
              className="gap-1.5"
              data-testid="client-pending-samples-cta"
            >
              Lihat Semua <ArrowRight size={13} />
            </Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {data.pending_samples.slice(0, 4).map((s) => (
              <button
                key={s.id}
                onClick={() => onNavigate('samples')}
                className="text-left rounded-xl border border-foreground/10 bg-foreground/[0.03] p-3.5 hover:bg-foreground/[0.06] transition"
                data-testid={`client-pending-sample-${s.id}`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-xs font-mono text-foreground/55">
                    {s.sample_code}
                  </span>
                  <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300">
                    {SAMPLE_STATUS_LABEL[s.status] || s.status}
                  </span>
                </div>
                <div className="text-sm font-medium text-foreground line-clamp-1">
                  {s.product_name}
                </div>
                <div className="text-xs text-foreground/50 mt-0.5">
                  {s.fabric_used || '-'} · Ukuran {s.target_size || '-'}
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Recent orders */}
      <section data-testid="client-recent-orders-section">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-foreground">Order Terbaru</h2>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onNavigate('orders')}
            className="gap-1.5 text-foreground/65"
          >
            Semua Order <ArrowRight size={13} />
          </Button>
        </div>
        {data.recent_orders?.length > 0 ? (
          <div className="rounded-2xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
            <table className="w-full text-sm">
              <thead className="bg-foreground/[0.04] text-foreground/55">
                <tr>
                  <th className="text-left font-medium px-4 py-3">Kode Order</th>
                  <th className="text-left font-medium px-4 py-3">Produk</th>
                  <th className="text-right font-medium px-4 py-3">Qty</th>
                  <th className="text-right font-medium px-4 py-3">Nilai</th>
                  <th className="text-left font-medium px-4 py-3">Status</th>
                  <th className="text-left font-medium px-4 py-3">Deadline</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_orders.map((o) => (
                  <tr
                    key={o.id}
                    className="border-t border-foreground/5 hover:bg-foreground/[0.03] cursor-pointer transition"
                    onClick={() => onNavigate('orders')}
                    data-testid={`client-recent-order-${o.id}`}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-foreground/75">
                      {o.order_code}
                    </td>
                    <td className="px-4 py-3 text-foreground line-clamp-1">
                      {o.product_name}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {o.qty_ordered}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-foreground/75">
                      {fmtCurrency(o.total_value)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-1 rounded-md bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))]">
                        {ORDER_STAGE_LABEL[o.status] || o.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground/65 whitespace-nowrap">
                      {fmtDate(o.deadline_date)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-foreground/10 p-10 text-center">
            <Package size={28} className="mx-auto text-foreground/30 mb-2" />
            <p className="text-sm text-foreground/50">
              Belum ada order. Silakan hubungi tim CV. Dewi Aditya untuk memulai.
            </p>
          </div>
        )}
      </section>

      {/* Quick actions footer */}
      <div className="rounded-2xl border border-foreground/10 bg-gradient-to-br from-[hsl(var(--primary))]/8 via-transparent to-transparent p-5 flex items-center gap-4">
        <div className="w-10 h-10 rounded-xl bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))] flex items-center justify-center">
          <TrendingUp size={18} />
        </div>
        <div className="flex-1 text-sm">
          <div className="font-medium text-foreground">
            Punya pertanyaan tentang order Anda?
          </div>
          <div className="text-foreground/55 text-xs mt-0.5">
            Tim Maklon CV. Dewi Aditya siap membantu via WhatsApp atau email.
          </div>
        </div>
        <Button size="sm" variant="outline" onClick={() => onNavigate('profile')}>
          Lihat Kontak
        </Button>
      </div>
    </div>
  );
}
