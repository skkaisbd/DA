import { useEffect, useState, useCallback } from 'react';
import { Search, X, Package, ClipboardCheck, Sparkles, CalendarClock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { clientApi, fmtCurrency, fmtDate, ORDER_STAGE_LABEL } from './clientApi';

const STATUS_FILTERS = [
  { id: 'all', label: 'Semua' },
  { id: 'confirmed', label: 'Konfirmasi' },
  { id: 'sewing', label: 'Produksi' },
  { id: 'qc', label: 'QC' },
  { id: 'completed', label: 'Selesai' },
  { id: 'invoiced', label: 'Invoiced' },
];

function StatusPill({ status }) {
  const tone =
    status === 'completed' || status === 'invoiced'
      ? 'bg-emerald-100 text-emerald-700'
      : status === 'cancelled'
      ? 'bg-red-100 text-red-700'
      : status === 'draft'
      ? 'bg-foreground/10 text-foreground/60'
      : 'bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))]';
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-md font-medium ${tone}`}>
      {ORDER_STAGE_LABEL[status] || status}
    </span>
  );
}

function ProgressBar({ pct }) {
  const v = Math.max(0, Math.min(100, Number(pct) || 0));
  return (
    <div className="w-full h-1.5 rounded-full bg-foreground/10 overflow-hidden">
      <div
        className="h-full rounded-full bg-[hsl(var(--primary))] transition-all"
        style={{ width: `${v}%` }}
      />
    </div>
  );
}

function OrderTimeline({ timeline }) {
  return (
    <div className="grid grid-cols-4 sm:grid-cols-8 gap-1.5" data-testid="client-order-timeline">
      {timeline.map((t, i) => (
        <div key={t.stage + i} className="flex flex-col items-center text-center gap-1.5">
          <div
            className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-semibold ${
              t.state === 'completed'
                ? 'bg-emerald-100 dark:bg-emerald-500/25 text-emerald-700 ring-1 ring-emerald-500/40'
                : t.state === 'current'
                ? 'bg-[hsl(var(--primary))]/25 text-[hsl(var(--primary))] ring-2 ring-[hsl(var(--primary))]/50'
                : t.state === 'cancelled'
                ? 'bg-red-100 text-red-700'
                : 'bg-foreground/8 text-foreground/35'
            }`}
          >
            {i + 1}
          </div>
          <span
            className={`text-[10px] uppercase tracking-wider whitespace-nowrap ${
              t.state === 'current' ? 'text-[hsl(var(--primary))] font-medium' : 'text-foreground/45'
            }`}
          >
            {ORDER_STAGE_LABEL[t.stage] || t.stage}
          </span>
        </div>
      ))}
    </div>
  );
}

function OrderDrawer({ open, onClose, order, token }) {
  const [detail, setDetail] = useState(null);
  const [qcRecords, setQcRecords] = useState([]);
  const [samples, setSamples] = useState([]);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('overview');

  useEffect(() => {
    if (!open || !order) return;
    let cancel = false;
    (async () => {
      setLoading(true);
      try {
        const [d, qc, smp] = await Promise.all([
          clientApi.request(`/orders/${order.id}`, { token }),
          clientApi.request(`/orders/${order.id}/qc`, { token }),
          clientApi.request(`/orders/${order.id}/samples`, { token }),
        ]);
        if (!cancel) {
          setDetail(d);
          setQcRecords(qc);
          setSamples(smp);
        }
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => {
      cancel = true;
    };
  }, [open, order, token]);

  if (!open || !order) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      data-testid="client-order-drawer"
    >
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        aria-label="Close drawer"
      />
      <div className="relative w-full md:max-w-2xl bg-[hsl(var(--background))] border-l border-foreground/10 overflow-y-auto">
        <div className="sticky top-0 z-10 bg-[hsl(var(--background))]/95 backdrop-blur border-b border-foreground/10 px-6 py-4 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-foreground/45">
              Detail Order
            </div>
            <div className="text-base font-semibold text-foreground font-mono">
              {order.order_code}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-foreground/5"
            data-testid="client-order-drawer-close"
          >
            <X size={18} />
          </button>
        </div>

        {loading || !detail ? (
          <div className="p-10 text-center text-foreground/50">Memuat detail...</div>
        ) : (
          <div className="p-6 space-y-6">
            <div>
              <div className="text-xs uppercase tracking-wider text-foreground/45 mb-1">
                {detail.product_category}
              </div>
              <h2 className="text-xl font-bold text-foreground">{detail.product_name}</h2>
              <div className="mt-2 flex items-center gap-2 flex-wrap">
                <StatusPill status={detail.status} />
                <span className="text-xs text-foreground/55">
                  Progress {detail.progress_percentage || 0}%
                </span>
              </div>
              <div className="mt-3">
                <ProgressBar pct={detail.progress_percentage} />
              </div>
            </div>

            {detail.timeline && (
              <div className="rounded-xl border border-foreground/10 bg-foreground/[0.03] p-4">
                <div className="text-[11px] uppercase tracking-wider text-foreground/50 mb-3">
                  Timeline Produksi
                </div>
                <OrderTimeline timeline={detail.timeline} />
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-xl border border-foreground/10 p-3">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45">
                  Qty Order
                </div>
                <div className="text-lg font-semibold tabular-nums text-foreground">
                  {detail.qty_ordered} pcs
                </div>
              </div>
              <div className="rounded-xl border border-foreground/10 p-3">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45">
                  Total Nilai
                </div>
                <div className="text-lg font-semibold tabular-nums text-foreground">
                  {fmtCurrency(detail.total_value)}
                </div>
              </div>
              <div className="rounded-xl border border-foreground/10 p-3">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45">
                  Tanggal Order
                </div>
                <div className="text-sm font-medium text-foreground">
                  {fmtDate(detail.order_date)}
                </div>
              </div>
              <div className="rounded-xl border border-foreground/10 p-3">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45">
                  Deadline
                </div>
                <div className="text-sm font-medium text-foreground flex items-center gap-1.5">
                  <CalendarClock size={13} className="text-foreground/45" />
                  {fmtDate(detail.deadline_date)}
                </div>
              </div>
            </div>

            {/* Tabs */}
            <div className="border-b border-foreground/10 flex gap-1">
              {[
                { id: 'overview', label: 'Detail Order' },
                { id: 'samples', label: `Samples (${samples.length})` },
                { id: 'qc', label: `QC Reports (${qcRecords.length})` },
              ].map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  data-testid={`client-order-tab-${t.id}`}
                  className={`px-3 py-2 text-sm border-b-2 transition ${
                    tab === t.id
                      ? 'border-[hsl(var(--primary))] text-[hsl(var(--primary))] font-medium'
                      : 'border-transparent text-foreground/60 hover:text-foreground'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {tab === 'overview' && (
              <div className="space-y-3 text-sm" data-testid="client-order-tab-overview-content">
                <div>
                  <span className="text-foreground/55">Material disediakan oleh: </span>
                  <span className="font-medium text-foreground">
                    {detail.fabric_provided_by === 'client' ? 'Klien' : 'CV. Dewi Aditya'}
                  </span>
                </div>
                {detail.colors?.length > 0 && (
                  <div>
                    <span className="text-foreground/55">Warna: </span>
                    {detail.colors.map((c) => (
                      <span
                        key={c}
                        className="inline-block mr-1.5 px-2 py-0.5 text-xs rounded-md bg-foreground/10 text-foreground"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                )}
                {detail.material_notes && (
                  <div>
                    <div className="text-foreground/55 text-xs uppercase tracking-wider mb-1">
                      Catatan Material
                    </div>
                    <div className="text-foreground/85">{detail.material_notes}</div>
                  </div>
                )}
                {detail.notes && (
                  <div>
                    <div className="text-foreground/55 text-xs uppercase tracking-wider mb-1">
                      Catatan
                    </div>
                    <div className="text-foreground/85">{detail.notes}</div>
                  </div>
                )}
              </div>
            )}

            {tab === 'samples' && (
              <div className="space-y-2" data-testid="client-order-tab-samples-content">
                {samples.length === 0 ? (
                  <div className="text-sm text-foreground/50 py-4 text-center">
                    Belum ada sample untuk order ini.
                  </div>
                ) : (
                  samples.map((s) => (
                    <div
                      key={s.id}
                      className="rounded-xl border border-foreground/10 p-3 flex items-center justify-between gap-3"
                    >
                      <div>
                        <div className="font-mono text-xs text-foreground/55">{s.sample_code}</div>
                        <div className="text-sm font-medium text-foreground">{s.product_name}</div>
                        <div className="text-xs text-foreground/50 mt-0.5">
                          {s.fabric_used} · {s.color_used} · Ukuran {s.target_size}
                        </div>
                      </div>
                      <span className="text-[11px] px-2 py-1 rounded-md bg-foreground/10 text-foreground/85">
                        {s.status}
                      </span>
                    </div>
                  ))
                )}
              </div>
            )}

            {tab === 'qc' && (
              <div className="space-y-2" data-testid="client-order-tab-qc-content">
                {qcRecords.length === 0 ? (
                  <div className="text-sm text-foreground/50 py-4 text-center">
                    Belum ada laporan QC.
                  </div>
                ) : (
                  qcRecords.map((q) => (
                    <div key={q.id} className="rounded-xl border border-foreground/10 p-3">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <ClipboardCheck size={15} className="text-emerald-600 dark:text-emerald-400" />
                          <span className="text-sm font-medium text-foreground capitalize">
                            {q.stage}
                          </span>
                        </div>
                        <span className="text-[11px] px-2 py-1 rounded-md bg-foreground/10 text-foreground/85">
                          {q.result}
                        </span>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-xs">
                        <div>
                          <span className="text-foreground/45">Diperiksa: </span>
                          <span className="font-medium tabular-nums">{q.qty_inspected}</span>
                        </div>
                        <div>
                          <span className="text-foreground/45">Lulus: </span>
                          <span className="font-medium tabular-nums text-emerald-700">{q.qty_passed}</span>
                        </div>
                        <div>
                          <span className="text-foreground/45">Reject: </span>
                          <span className="font-medium tabular-nums text-red-700">{q.qty_rejected}</span>
                        </div>
                      </div>
                      {q.defects?.length > 0 && (
                        <div className="mt-2 text-xs">
                          <div className="text-foreground/45 uppercase tracking-wider mb-1">Defect</div>
                          <ul className="space-y-0.5 text-foreground/80">
                            {q.defects.map((d, i) => (
                              <li key={i}>
                                · {d.description} ({d.qty_affected} pcs)
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ClientOrders({ token }) {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [active, setActive] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const path = filter === 'all' ? '/orders' : `/orders?status=${filter}`;
      const data = await clientApi.request(path, { token });
      setOrders(data);
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [filter, token]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = orders.filter((o) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      o.order_code?.toLowerCase().includes(q) ||
      o.product_name?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6" data-testid="client-orders">
      <div>
        <div className="text-xs uppercase tracking-[0.18em] text-foreground/45 mb-1">
          Order Saya
        </div>
        <h1 className="text-3xl font-bold text-foreground">Riwayat Order Maklon</h1>
      </div>

      {/* Filter & search */}
      <div className="flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              data-testid={`client-orders-filter-${f.id}`}
              className={`px-3 py-1.5 text-xs rounded-full whitespace-nowrap transition ${
                filter === f.id
                  ? 'bg-[hsl(var(--primary))] text-foreground font-medium'
                  : 'bg-foreground/5 text-foreground/65 hover:bg-foreground/10'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="relative w-full md:w-64">
          <Search
            size={15}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-foreground/40"
          />
          <input
            type="text"
            placeholder="Cari kode atau produk..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl border border-foreground/10 bg-foreground/[0.04] pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-[hsl(var(--primary))]/60"
            data-testid="client-orders-search"
          />
        </div>
      </div>

      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 rounded-xl bg-foreground/[0.05]" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-foreground/10 p-12 text-center">
          <Package size={32} className="mx-auto text-foreground/30 mb-2" />
          <p className="text-sm text-foreground/50">
            Tidak ada order ditemukan untuk filter ini.
          </p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="client-orders-list">
          {filtered.map((o) => (
            <button
              key={o.id}
              onClick={() => setActive(o)}
              data-testid={`client-order-row-${o.id}`}
              className="w-full text-left rounded-2xl border border-foreground/10 bg-foreground/[0.03] p-4 hover:border-[hsl(var(--primary))]/40 hover:bg-foreground/[0.05] transition"
            >
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-xs text-foreground/55">{o.order_code}</span>
                    <StatusPill status={o.status} />
                  </div>
                  <div className="text-base font-medium text-foreground truncate">
                    {o.product_name}
                  </div>
                  <div className="text-xs text-foreground/50 mt-0.5">
                    {o.qty_ordered} pcs · {o.product_category}
                  </div>
                </div>
                <div className="md:text-right">
                  <div className="text-lg font-semibold tabular-nums text-foreground">
                    {fmtCurrency(o.total_value)}
                  </div>
                  <div className="text-xs text-foreground/50 flex items-center gap-1 md:justify-end mt-0.5">
                    <CalendarClock size={11} />
                    Deadline {fmtDate(o.deadline_date)}
                  </div>
                </div>
              </div>
              <div className="mt-3 flex items-center gap-3">
                <div className="flex-1">
                  <ProgressBar pct={o.progress_percentage} />
                </div>
                <span className="text-xs tabular-nums text-foreground/55 w-10 text-right">
                  {o.progress_percentage || 0}%
                </span>
              </div>
            </button>
          ))}
        </div>
      )}

      <OrderDrawer
        open={Boolean(active)}
        order={active}
        token={token}
        onClose={() => setActive(null)}
      />
    </div>
  );
}
