import { useState, useEffect, useCallback, useMemo } from 'react';
import { ShoppingBag, Package, AlertTriangle, TrendingUp, Store, Zap, RefreshCw, Shirt, ArrowRight, Clock } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader } from './moduleAtoms';
import { formatRupiah } from '@/lib/format';

const CHANNEL_COLORS = {
  shopee: { bg: 'bg-orange-500/15', border: 'border-orange-400/25', text: 'text-orange-300' },
  tokopedia: { bg: 'bg-emerald-500/15', border: 'border-emerald-400/25', text: 'text-emerald-300' },
  tiktok_shop: { bg: 'bg-pink-500/15', border: 'border-pink-400/25', text: 'text-pink-300' },
  website: { bg: 'bg-sky-500/15', border: 'border-sky-400/25', text: 'text-sky-300' },
};

const fmtIDR = formatRupiah;
const fmtDate = (d) => (d ? new Date(d).toLocaleString('id-ID') : 'Belum pernah');

export default function TokoDashboardModule({ token, onNavigate }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // P1.D Phase B Cutover — now uses marketing namespace endpoint
      const r = await fetch('/api/marketing/dashboard/toko-overview', { headers });
      if (r.ok) setData(await r.json());
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="p-6 space-y-6" data-testid="toko-dashboard-v2">
      <PageHeader
        title="Dashboard Toko Online"
        description="Katalog produk, sync channel & penjualan marketplace — CV. Dewi Aditya"
        icon={ShoppingBag}
        actions={
          <Button size="sm" variant="outline" onClick={load} className="gap-1.5">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </Button>
        }
      />

      {data?.mock_mode && (
        <div className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-3 text-xs flex items-start gap-2" data-testid="toko-mock-banner">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <span className="font-medium text-amber-200">MODE MOCK aktif.</span>{' '}
            <span className="text-foreground/65">
              Channel Manager beroperasi dalam mode simulasi. Konfigurasi kredensial asli (Shopee Partner API / Tokopedia / TikTok Shop) untuk mengaktifkan sinkronisasi real.
            </span>
          </div>
        </div>
      )}

      {loading && !data ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 animate-pulse">
          {[1, 2, 3, 4].map((i) => <div key={i} className="h-28 rounded-2xl bg-foreground/[0.05]" />)}
        </div>
      ) : data ? (
        <>
          {/* Product stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <GlassCard className="p-4" data-testid="toko-stat-total-products">
              <div className="w-10 h-10 rounded-xl bg-pink-500/15 border border-pink-400/25 flex items-center justify-center mb-3">
                <Shirt className="w-5 h-5 text-pink-400" />
              </div>
              <div className="text-3xl font-bold tabular-nums">{data.products.total}</div>
              <div className="text-xs uppercase tracking-wider text-foreground/55 mt-1">Total Produk</div>
              <div className="text-xs text-foreground/45 mt-0.5">{data.products.active} aktif · {data.products.draft} draft</div>
            </GlassCard>
            <GlassCard className="p-4" data-testid="toko-stat-inventory-value">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/15 border border-emerald-400/25 flex items-center justify-center mb-3">
                <TrendingUp className="w-5 h-5 text-emerald-400" />
              </div>
              <div className="text-2xl font-bold tabular-nums">{fmtIDR(data.products.inventory_value)}</div>
              <div className="text-xs uppercase tracking-wider text-foreground/55 mt-1">Nilai Inventori</div>
              <div className="text-xs text-foreground/45 mt-0.5">Base price × stok</div>
            </GlassCard>
            <GlassCard className={`p-4 ${data.products.low_stock > 0 ? 'border-red-400/30' : ''}`} data-testid="toko-stat-low-stock">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-3 ${data.products.low_stock > 0 ? 'bg-red-500/15 border border-red-400/25' : 'bg-foreground/10 border border-foreground/15'}`}>
                <AlertTriangle className={`w-5 h-5 ${data.products.low_stock > 0 ? 'text-red-400' : 'text-foreground/55'}`} />
              </div>
              <div className={`text-3xl font-bold tabular-nums ${data.products.low_stock > 0 ? 'text-red-300' : ''}`}>
                {data.products.low_stock}
              </div>
              <div className="text-xs uppercase tracking-wider text-foreground/55 mt-1">Low Stock</div>
              <div className="text-xs text-foreground/45 mt-0.5">Stok {'<'} 10 pcs</div>
            </GlassCard>
            <GlassCard className="p-4" data-testid="toko-stat-channels-enabled">
              <div className="w-10 h-10 rounded-xl bg-violet-500/15 border border-violet-400/25 flex items-center justify-center mb-3">
                <Store className="w-5 h-5 text-violet-400" />
              </div>
              <div className="text-3xl font-bold tabular-nums">
                {data.channels.enabled}
                <span className="text-lg text-foreground/45 font-normal"> / {data.channels.total}</span>
              </div>
              <div className="text-xs uppercase tracking-wider text-foreground/55 mt-1">Channel Aktif</div>
              <div className="text-xs text-foreground/45 mt-0.5">Marketplace terintegrasi</div>
            </GlassCard>
          </div>

          {/* Channel cards */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-semibold">Status Channel</h3>
              {onNavigate && (
                <Button size="sm" variant="ghost" onClick={() => onNavigate('toko-channels')} className="gap-1.5">
                  Kelola Channel <ArrowRight className="w-3.5 h-3.5" />
                </Button>
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="toko-channel-cards">
              {data.channels.cards.map((c) => {
                const tone = CHANNEL_COLORS[c.code] || CHANNEL_COLORS.website;
                return (
                  <GlassCard
                    key={c.code}
                    className={`p-4 ${c.enabled ? tone.border : 'opacity-70'}`}
                    data-testid={`toko-channel-card-${c.code}`}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className={`w-9 h-9 rounded-lg ${tone.bg} flex items-center justify-center`}>
                        <Store className={`w-4 h-4 ${tone.text}`} />
                      </div>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${c.enabled ? 'bg-emerald-500/15 text-emerald-300' : 'bg-foreground/10 text-foreground/55'}`}>
                        {c.enabled ? 'AKTIF' : 'OFF'}
                      </span>
                    </div>
                    <div className="text-sm font-medium">{c.name}</div>
                    <div className="text-xs text-foreground/45 mt-1 flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {fmtDate(c.last_sync_at)}
                    </div>
                    {c.enabled && c.last_sync_counts && (
                      <div className="mt-2 pt-2 border-t border-foreground/10 text-xs space-y-0.5">
                        <div className="flex justify-between">
                          <span className="text-foreground/55">Produk</span>
                          <span className="tabular-nums font-medium">{c.last_sync_counts.products ?? 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-foreground/55">Order</span>
                          <span className="tabular-nums font-medium">{c.last_sync_counts.orders ?? 0}</span>
                        </div>
                      </div>
                    )}
                  </GlassCard>
                );
              })}
            </div>
          </div>

          {/* Top products + recent syncs */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-semibold flex items-center gap-2"><Zap className="w-4 h-4 text-amber-400" /> Top 5 Produk</h3>
                {onNavigate && (
                  <Button size="sm" variant="ghost" onClick={() => onNavigate('toko-products')} className="gap-1.5">
                    Semua Produk <ArrowRight className="w-3.5 h-3.5" />
                  </Button>
                )}
              </div>
              {data.top_products.length === 0 ? (
                <GlassCard className="p-6 text-center text-sm text-foreground/50">
                  <Package className="w-8 h-8 mx-auto text-foreground/30 mb-2" />
                  Belum ada produk. Buat katalog dari menu "Produk Marketplace".
                </GlassCard>
              ) : (
                <div className="space-y-2">
                  {data.top_products.map((p) => (
                    <GlassCard key={p.id} className="p-3" data-testid={`toko-top-product-${p.id}`}>
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="font-mono text-[11px] text-foreground/55">{p.sku || p.sku_code}</div>
                          <div className="text-sm font-medium truncate">{p.name}</div>
                          <div className="text-xs text-foreground/55">{p.category || '-'} · Stok {p.stock_quantity ?? p.stock_total ?? 0}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-semibold tabular-nums">{fmtIDR(p.price ?? p.base_price)}</div>
                          <div className="text-xs text-foreground/55">{p.sales_count_total ?? 0} terjual</div>
                        </div>
                      </div>
                    </GlassCard>
                  ))}
                </div>
              )}
            </div>

            <div>
              <h3 className="text-base font-semibold mb-3 flex items-center gap-2"><RefreshCw className="w-4 h-4 text-foreground/55" /> Sync Terbaru</h3>
              {data.recent_syncs.length === 0 ? (
                <GlassCard className="p-6 text-center text-sm text-foreground/50">
                  Belum ada aktivitas sinkronisasi.
                </GlassCard>
              ) : (
                <div className="space-y-2" data-testid="toko-recent-syncs">
                  {data.recent_syncs.map((s) => (
                    <GlassCard key={s.id} className="p-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-medium capitalize">{s.channel_code.replace('_', ' ')}</div>
                          <div className="text-xs text-foreground/55">{fmtDate(s.started_at)}</div>
                        </div>
                        <div className="text-right">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded ${s.status === 'success' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'}`}>
                            {s.status}
                          </span>
                          {s.counts && (
                            <div className="text-xs text-foreground/55 mt-0.5 tabular-nums">
                              {s.counts.products || 0} prd · {s.counts.orders || 0} ord
                            </div>
                          )}
                        </div>
                      </div>
                    </GlassCard>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      ) : (
        <div className="text-center py-10 text-foreground/50">Gagal memuat data.</div>
      )}
    </div>
  );
}
