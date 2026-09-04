/**
 * DashboardTab — Asset Management Dashboard view
 * Extracted from AssetManagementPortal.jsx during Phase 4 refactor.
 *
 * Receives data via props from the orchestrator (no internal data fetching).
 */
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Package, Banknote, DollarSign, TrendingDown,
} from 'lucide-react';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Legend,
  Tooltip as RechartTooltip,
} from 'recharts';
import { PIE_COLORS, STATUS_CONFIG } from '../constants';
import { fmtCurrency, fmtDate } from '../utils';
import { KPICard } from '../components/KPICard';
import { StatusBadge } from '../components/StatusBadge';

export function DashboardTab({ dashData, expiringAlerts, onAssetClick }) {
  const summary = dashData?.summary || {};
  const byCat = (dashData?.by_category || []).map(c => ({ name: c.category || 'Lainnya', count: c.count }));

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <KPICard label="Total Aset" value={summary.total_assets || 0} icon={Package} accent="blue" />
        <KPICard label="Total Nilai Buku" value={fmtCurrency(summary.total_nbv)} icon={Banknote} accent="emerald" />
        <KPICard label="Harga Perolehan" value={fmtCurrency(summary.total_purchase_cost)} icon={DollarSign} accent="violet" />
        <KPICard label="Depresiasi Bulan Ini" value={fmtCurrency(summary.depreciation_this_month)} icon={TrendingDown} accent="amber"
          sub={`${summary.in_maintenance || 0} dalam pemeliharaan`} />
      </div>

      {/* Warranty & Insurance Alert Banner */}
      {((summary.warranty_expiring_soon > 0) || (summary.insurance_expiring_soon > 0)) && (
        <div className="bg-amber-100 dark:bg-amber-500/10 border border-amber-400 dark:border-amber-500/30 rounded-lg p-3 mb-4 flex items-start gap-3" data-testid="expiring-alerts-banner">
          <span className="text-2xl">⚠️</span>
          <div className="flex-1">
            <p className="text-sm font-semibold text-amber-700">Perhatian — Garansi / Asuransi Akan Habis (≤30 hari)</p>
            <div className="flex gap-4 mt-1 text-xs text-amber-700">
              {summary.warranty_expiring_soon > 0 && (
                <span>🛡️ Garansi: <strong>{summary.warranty_expiring_soon}</strong> aset</span>
              )}
              {summary.insurance_expiring_soon > 0 && (
                <span>🔒 Asuransi: <strong>{summary.insurance_expiring_soon}</strong> aset</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Expiring Assets Detail Table */}
      {expiringAlerts && (
        Object.values(expiringAlerts).some(arr => arr.length > 0)
      ) && (
        <Card className="mb-4" data-testid="expiring-alerts-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <span className="text-amber-500">⏰</span> Garansi &amp; Asuransi Akan / Sudah Expired
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              { key: 'warranty_expiring', label: '🛡️ Garansi — Akan Habis ≤30 hari', color: 'amber' },
              { key: 'warranty_expired',  label: '🛡️ Garansi — Sudah Expired', color: 'red' },
              { key: 'insurance_expiring', label: '🔒 Asuransi — Akan Habis ≤30 hari', color: 'amber' },
              { key: 'insurance_expired',  label: '🔒 Asuransi — Sudah Expired', color: 'red' },
            ].map(({ key, label, color }) => {
              const items = expiringAlerts[key] || [];
              if (!items.length) return null;
              return (
                <div key={key}>
                  <p className={`text-xs font-semibold mb-1.5 ${color === 'red' ? 'text-destructive' : 'text-amber-600 dark:text-amber-400'}`}>{label} ({items.length})</p>
                  <div className="space-y-1">
                    {items.slice(0, 5).map(a => (
                      <div key={a.id} className="flex items-center justify-between text-xs bg-muted/40 rounded px-3 py-1.5 cursor-pointer hover:bg-muted/70"
                        onClick={() => onAssetClick?.(a)}>
                        <span className="font-medium">{a.name}</span>
                        <span className="text-muted-foreground">{a.asset_number}</span>
                        <span className={color === 'red' ? 'text-destructive font-semibold' : 'text-amber-600'}>
                          {key.includes('warranty') ? fmtDate(a.warranty_expiry_date) : fmtDate(a.insurance_expiry_date)}
                        </span>
                      </div>
                    ))}
                    {items.length > 5 && <p className="text-xs text-muted-foreground pl-3">+{items.length - 5} lainnya</p>}
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* By Category Chart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Distribusi Aset per Kategori</CardTitle>
          </CardHeader>
          <CardContent className="h-52">
            {byCat.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={byCat} dataKey="count" nameKey="name" cx="50%" cy="50%" outerRadius={80}>
                    {byCat.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <RechartTooltip />
                  <Legend wrapperStyle={{ fontSize: '11px' }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                Belum ada data aset
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Assets */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Aset Terbaru</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(dashData?.recent_assets || []).map(a => (
                <div key={a.id} className="flex items-center justify-between py-2 px-3 bg-muted/40 rounded-lg">
                  <div>
                    <p className="text-sm font-medium">{a.name}</p>
                    <p className="text-xs text-muted-foreground">{a.category_name} · {a.asset_number}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold">{fmtCurrency(a.purchase_cost)}</p>
                    <StatusBadge status={a.status} configMap={STATUS_CONFIG} />
                  </div>
                </div>
              ))}
              {(!dashData?.recent_assets || dashData.recent_assets.length === 0) && (
                <p className="text-sm text-muted-foreground text-center py-4">Belum ada aset terdaftar</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
