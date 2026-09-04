/**
 * ProcurementSpendModule — Analisis Belanja Pengadaan
 *
 * Sumber: `/api/procurement/spend-analysis` (agregasi PO + master material).
 * Menjawab pertanyaan pembeli: uang habis ke supplier mana, kategori apa,
 * material apa, dan bagaimana trennya per bulan.
 */
import { useCallback, useEffect, useState } from 'react';
import { BarChart3, Building2, Layers, PackageSearch, RefreshCw } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { toast } from 'sonner';
import { CATEGORY_LABEL, EP, apiGet, fmtNum, fmtRp } from './procApi';

function Bars({ rows, labelKey, valueKey, subKey, testId }) {
  const max = Math.max(1, ...(rows || []).map((r) => Number(r[valueKey] || 0)));
  if (!rows?.length) {
    return <p className="text-sm text-muted-foreground py-4">Belum ada data pada periode ini.</p>;
  }
  return (
    <div className="space-y-2" data-testid={testId}>
      {rows.map((r, i) => (
        <div key={`${r[labelKey]}-${i}`} className="space-y-1">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs font-medium line-clamp-1">{r[labelKey] || '-'}</span>
            <span className="text-xs tabular-nums text-muted-foreground shrink-0">
              {fmtRp(r[valueKey])}
            </span>
          </div>
          <div className="h-2 rounded-full bg-[hsl(var(--muted)/0.6)] overflow-hidden">
            <div className="h-full rounded-full bg-[hsl(var(--primary))]"
                 style={{ width: `${Math.max(3, (Number(r[valueKey] || 0) / max) * 100)}%` }} />
          </div>
          {subKey && r[subKey] != null && (
            <div className="text-[11px] text-muted-foreground">{r[subKey]}</div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function ProcurementSpendModule({ token }) {
  const [months, setMonths] = useState(6);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      setData(await apiGet(token, EP.spend(months)));
    } catch (e) {
      setErr(e.message);
      toast.error(`Gagal memuat analisis belanja: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [token, months]);

  useEffect(() => { load(); }, [load]);

  const bySupplier = (data?.by_supplier || []).map((r) => ({
    ...r,
    label: `${r.supplier_code ? `${r.supplier_code} · ` : ''}${r.supplier_name}`,
    sub: `${r.po_count} PO`,
  }));
  const byCategory = (data?.by_category || []).map((r) => ({
    ...r,
    label: CATEGORY_LABEL[r.category] || (r.category === 'free_form' ? 'Item Bebas / Jasa' : r.category),
    sub: `${r.lines} baris PO`,
  }));
  const topMat = (data?.top_materials || []).map((r) => ({
    ...r,
    label: `${r.material_code ? `${r.material_code} · ` : ''}${r.material_name}`,
    sub: `${fmtNum(r.qty_base)} ${r.base_uom || ''}`.trim(),
  }));
  const maxMonth = Math.max(1, ...(data?.by_month || []).map((m) => m.value || 0));

  return (
    <div className="space-y-5" data-testid="proc-spend-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Analisis Belanja</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Ke mana anggaran pengadaan mengalir: supplier, kategori, material, dan tren bulanan.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SmartNativeSelect
            value={String(months)}
            onChange={(e) => setMonths(Number(e.target.value))}
            className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
            data-testid="proc-spend-months"
          >
            <option value="3">3 bulan terakhir</option>
            <option value="6">6 bulan terakhir</option>
            <option value="12">12 bulan terakhir</option>
            <option value="24">24 bulan terakhir</option>
          </SmartNativeSelect>
          <Button variant="secondary" onClick={load} data-testid="proc-spend-refresh">
            <RefreshCw className="w-4 h-4 mr-1.5" /> Muat Ulang
          </Button>
        </div>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/30 text-red-700 dark:text-red-300 text-sm">
          {err}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[hsl(var(--primary))]" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] p-4">
              <div className="text-xs text-muted-foreground mb-1">Total belanja</div>
              <div className="text-2xl font-bold tabular-nums" data-testid="proc-spend-total">
                {fmtRp(data?.total_value)}
              </div>
            </div>
            <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] p-4">
              <div className="text-xs text-muted-foreground mb-1">Jumlah PO</div>
              <div className="text-2xl font-bold tabular-nums">{data?.po_count ?? 0}</div>
            </div>
            <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] p-4">
              <div className="text-xs text-muted-foreground mb-1">Rata-rata per PO</div>
              <div className="text-2xl font-bold tabular-nums">
                {fmtRp(data?.po_count ? (data.total_value || 0) / data.po_count : 0)}
              </div>
            </div>
          </div>

          <GlassCard className="p-4">
            <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-[hsl(var(--primary))]" /> Tren Belanja Bulanan
            </h3>
            {(data?.by_month || []).length === 0 ? (
              <p className="text-sm text-muted-foreground py-4">Belum ada PO pada periode ini.</p>
            ) : (
              <div className="flex items-end gap-2 h-40" data-testid="proc-spend-monthly">
                {data.by_month.map((m) => (
                  <div key={m.month} className="flex-1 flex flex-col items-center justify-end gap-1 h-full">
                    <span className="text-[10px] tabular-nums text-muted-foreground">
                      {(m.value / 1_000_000).toFixed(1)}jt
                    </span>
                    <div
                      className="w-full rounded-t-md bg-[hsl(var(--primary)/0.8)]"
                      style={{ height: `${Math.max(4, (m.value / maxMonth) * 100)}%` }}
                      title={`${m.month}: ${fmtRp(m.value)} (${m.po_count} PO)`}
                    />
                    <span className="text-[10px] text-muted-foreground">{m.month?.slice(5)}</span>
                  </div>
                ))}
              </div>
            )}
          </GlassCard>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <GlassCard className="p-4">
              <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
                <Building2 className="w-4 h-4" /> Belanja per Supplier
              </h3>
              <Bars rows={bySupplier.slice(0, 10)} labelKey="label" valueKey="value" subKey="sub"
                    testId="proc-spend-by-supplier" />
            </GlassCard>
            <GlassCard className="p-4">
              <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
                <Layers className="w-4 h-4" /> Belanja per Kategori
              </h3>
              <Bars rows={byCategory} labelKey="label" valueKey="value" subKey="sub"
                    testId="proc-spend-by-category" />
            </GlassCard>
            <GlassCard className="p-4">
              <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
                <PackageSearch className="w-4 h-4" /> Material Terbanyak
              </h3>
              <Bars rows={topMat.slice(0, 10)} labelKey="label" valueKey="value" subKey="sub"
                    testId="proc-spend-top-materials" />
            </GlassCard>
          </div>
        </>
      )}
    </div>
  );
}
