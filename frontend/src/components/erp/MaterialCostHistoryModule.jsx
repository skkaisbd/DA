import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  LineChart as LineChartIcon, RefreshCw, Search, TrendingUp, TrendingDown,
  Minus, Info, ArrowRight, ShoppingCart, Scissors, Wrench,
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer,
} from 'recharts';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';

/**
 * Riwayat Harga Barang (sesi #33).
 *
 * Kenapa layar ini ada: `rahaza_material_cost_history` sudah terisi otomatis
 * setiap pembelian (dan setiap potong, sejak sesi #32) untuk SEMUA jenis
 * material, tetapi satu-satunya pembacanya adalah layar **Valuasi Aksesoris**.
 * Akibatnya tidak ada tempat untuk menjawab "kenapa HPP potongan/produk saya
 * berubah?" — padahal seluruh HPP sesi #31/#32 lahir dari angka ini.
 */

const rp = (v) => `Rp${Number(v || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 })}`;
const num = (v) => Number(v || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 });
const dt = (v) => (v ? String(v).slice(0, 10) : '—');
const dtFull = (v) => (v ? String(v).replace('T', ' ').slice(0, 16) : '—');

function SourceChip({ row }) {
  const label = row.source_label || row.source || '—';
  const isPanel = /cutting/i.test(label);
  const isManual = /manual|koreksi/i.test(label);
  const Icon = isPanel ? Scissors : isManual ? Wrench : ShoppingCart;
  const cls = isPanel
    ? 'bg-violet-400/10 text-violet-500 border-violet-300/25'
    : isManual
      ? 'bg-amber-400/10 text-amber-600 border-amber-300/25'
      : 'bg-emerald-400/10 text-emerald-600 border-emerald-300/25';
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${cls}`}>
      <Icon className="w-3 h-3" /> {label}
    </span>
  );
}

export default function MaterialCostHistoryModule({ token }) {
  const [mats, setMats] = useState([]);
  const [matSummary, setMatSummary] = useState(null);
  const [loadingMats, setLoadingMats] = useState(true);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('');
  const [onlyChanged, setOnlyChanged] = useState(true);
  const [selectedId, setSelectedId] = useState('');
  const [data, setData] = useState(null);
  const [loadingData, setLoadingData] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const headers = useMemo(() => ({
    Authorization: `Bearer ${token || localStorage.getItem('erp_token')}`,
    'Content-Type': 'application/json',
  }), [token]);

  const loadMats = useCallback(async () => {
    setLoadingMats(true);
    try {
      const p = new URLSearchParams({ only_with_history: String(onlyChanged), limit: 2000 });
      if (filterType) p.set('type', filterType);
      if (search.trim()) p.set('search', search.trim());
      const r = await fetch(`/api/rahaza/material-costs/materials?${p}`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setMats(d.items || []);
      setMatSummary(d.summary || null);
    } catch (e) {
      toast.error(`Gagal memuat daftar barang: ${e.message}`);
    } finally { setLoadingMats(false); }
  }, [headers, filterType, search, onlyChanged]);

  const loadData = useCallback(async () => {
    setLoadingData(true);
    try {
      const p = new URLSearchParams({ limit: 500 });
      if (selectedId) p.set('material_id', selectedId);
      else if (filterType) p.set('type', filterType);
      if (dateFrom) p.set('date_from', dateFrom);
      if (dateTo) p.set('date_to', dateTo);
      const r = await fetch(`/api/rahaza/material-costs/history?${p}`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      toast.error(`Gagal memuat riwayat harga: ${e.message}`);
    } finally { setLoadingData(false); }
  }, [headers, selectedId, filterType, dateFrom, dateTo]);

  useEffect(() => { loadMats(); }, [loadMats]);
  useEffect(() => { loadData(); }, [loadData]);

  const items = data?.items || [];
  const s = data?.summary || {};
  const chart = useMemo(() => [...items].reverse().map(r => ({
    t: dt(r.created_at),
    harga: Number(r.new_unit_cost || 0),
  })), [items]);

  const trend = s.change_pct == null ? null : Number(s.change_pct);
  const TrendIcon = trend == null ? Minus : trend > 0 ? TrendingUp : trend < 0 ? TrendingDown : Minus;
  const trendTone = trend == null ? 'text-muted-foreground'
    : trend > 0 ? 'text-red-500' : trend < 0 ? 'text-emerald-600 dark:text-emerald-300' : 'text-muted-foreground';

  const selected = mats.find(m => m.material_id === selectedId);

  return (
    <div className="space-y-4" data-testid="cost-history-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
            <LineChartIcon className="w-5 h-5 text-primary" /> Riwayat Harga Barang
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Setiap perubahan HPP rata-rata bergerak — dari pembelian, dari hasil cutting, dan dari
            koreksi manual. Inilah asal angka HPP potongan &amp; HPP produk.
          </p>
        </div>
        <Button variant="ghost" onClick={() => { loadMats(); loadData(); }}
          disabled={loadingMats || loadingData} data-testid="cost-history-refresh">
          <RefreshCw className={`w-4 h-4 mr-1.5 ${(loadingMats || loadingData) ? 'animate-spin' : ''}`} />
          Muat ulang
        </Button>
      </div>

      {matSummary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="cost-history-summary">
          {[
            { k: 'materials', label: 'Barang aktif', v: num(matSummary.materials), tone: 'text-foreground' },
            { k: 'with_history', label: 'Pernah berubah harga', v: num(matSummary.with_history), tone: 'text-emerald-600 dark:text-emerald-300' },
            { k: 'total_changes', label: 'Total perubahan tercatat', v: num(matSummary.total_changes), tone: 'text-primary' },
            { k: 'unvalued', label: 'Belum ada harga', v: num(matSummary.unvalued), tone: 'text-amber-600 dark:text-amber-300' },
          ].map(c => (
            <GlassCard key={c.k} className="p-3">
              <div className={`text-2xl font-bold ${c.tone}`} data-testid={`cost-stat-${c.k}`}>{c.v}</div>
              <div className="text-xs text-muted-foreground mt-0.5">{c.label}</div>
            </GlassCard>
          ))}
        </div>
      )}

      <div className="grid lg:grid-cols-[330px_1fr] gap-4 items-start">
        <GlassCard className="p-3 space-y-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <GlassInput value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Cari kode / nama barang…" className="pl-8 h-9 text-sm"
              data-testid="cost-search" />
          </div>
          <div className="flex items-center gap-2">
            <select value={filterType} onChange={e => setFilterType(e.target.value)}
              className="h-9 px-2 flex-1 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              data-testid="cost-filter-type">
              <option value="">Semua jenis</option>
              <option value="bahan">Bahan (kain/benang)</option>
              <option value="aksesoris">Aksesoris</option>
              <option value="panel">Potongan</option>
              <option value="fg">Produk Jadi</option>
            </select>
          </div>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
            <input type="checkbox" checked={onlyChanged} onChange={e => setOnlyChanged(e.target.checked)}
              data-testid="cost-only-changed" />
            Hanya yang pernah berubah harga
          </label>
          <div className="max-h-[460px] overflow-auto -mx-1 px-1" data-testid="cost-material-list">
            {loadingMats ? (
              <div className="text-center py-8 text-sm text-muted-foreground">Memuat…</div>
            ) : mats.length === 0 ? (
              <div className="text-center py-8 text-xs text-muted-foreground">
                Tidak ada barang pada filter ini.
                {onlyChanged && ' Coba lepas centang “hanya yang pernah berubah harga”.'}
              </div>
            ) : (
              <div className="space-y-1">
                <button onClick={() => setSelectedId('')}
                  className={`w-full text-left px-2 py-2 rounded-lg text-sm transition-colors ${!selectedId ? 'bg-primary/10 text-primary' : 'hover:bg-[var(--glass-bg-hover)] text-foreground'}`}
                  data-testid="cost-pick-all">
                  Semua perubahan terbaru
                </button>
                {mats.map(m => (
                  <button key={m.material_id} onClick={() => setSelectedId(m.material_id)}
                    className={`w-full text-left px-2 py-2 rounded-lg transition-colors ${selectedId === m.material_id ? 'bg-primary/10' : 'hover:bg-[var(--glass-bg-hover)]'}`}
                    data-testid={`cost-pick-${m.code}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] text-muted-foreground">{m.code}</span>
                      <Badge variant={m.changes ? 'secondary' : 'outline'} className="text-[10px] h-4 px-1.5">
                        {m.changes} kali
                      </Badge>
                    </div>
                    <div className="text-sm text-foreground line-clamp-1">{m.name}</div>
                    <div className="text-[10px] text-muted-foreground">
                      {m.type} · {m.unit_cost > 0 ? `${rp(m.unit_cost)}/${m.unit}` : 'belum ada harga'}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </GlassCard>

        <div className="space-y-4">
          <div className="flex items-end gap-2 flex-wrap">
            <div>
              <label className="text-xs text-muted-foreground">Dari tanggal</label>
              <GlassInput type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                className="h-9 text-sm mt-1" data-testid="cost-date-from" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Sampai tanggal</label>
              <GlassInput type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                className="h-9 text-sm mt-1" data-testid="cost-date-to" />
            </div>
            {(dateFrom || dateTo) && (
              <Button variant="ghost" size="sm" onClick={() => { setDateFrom(''); setDateTo(''); }}
                data-testid="cost-clear-dates">Hapus filter tanggal</Button>
            )}
          </div>

          {selectedId && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="cost-detail-summary">
              {[
                { k: 'current', label: 'Harga sekarang', v: rp(s.current_unit_cost), tone: 'text-foreground' },
                { k: 'first', label: 'Harga pertama', v: rp(s.first_unit_cost), tone: 'text-muted-foreground' },
                { k: 'min', label: 'Terendah', v: rp(s.min_unit_cost), tone: 'text-emerald-600 dark:text-emerald-300' },
                { k: 'max', label: 'Tertinggi', v: rp(s.max_unit_cost), tone: 'text-red-500' },
                { k: 'changes', label: 'Kali berubah', v: num(s.changes), tone: 'text-primary' },
              ].map(c => (
                <GlassCard key={c.k} className="p-3">
                  <div className={`text-base font-bold ${c.tone}`} data-testid={`cost-sum-${c.k}`}>{c.v}</div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">{c.label}</div>
                </GlassCard>
              ))}
            </div>
          )}

          {selectedId && s.changes > 0 && (
            <GlassCard className="p-4">
              <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <div>
                  <div className="text-sm font-semibold text-foreground">
                    {selected ? `${selected.code} · ${selected.name}` : 'Perubahan harga'}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Harga per {data?.material?.unit || selected?.unit || 'satuan'} · metode{' '}
                    {data?.material?.cost_method || 'moving_average'}
                  </div>
                </div>
                <div className={`inline-flex items-center gap-1 text-sm font-semibold ${trendTone}`}
                  data-testid="cost-trend">
                  <TrendIcon className="w-4 h-4" />
                  {trend == null ? 'perubahan dari 0' : `${trend > 0 ? '+' : ''}${trend}% sejak harga pertama`}
                </div>
              </div>
              <div style={{ width: '100%', height: 220 }} data-testid="cost-chart">
                <ResponsiveContainer>
                  <LineChart data={chart} margin={{ top: 5, right: 12, left: 4, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="t" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                    <YAxis tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                      tickFormatter={v => Number(v).toLocaleString('id-ID')} width={78} />
                    <RTooltip formatter={v => rp(v)}
                      contentStyle={{
                        background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))',
                        borderRadius: 8, fontSize: 12, color: 'hsl(var(--foreground))',
                      }} />
                    <Line type="monotone" dataKey="harga" stroke="hsl(var(--primary))" strokeWidth={2}
                      dot={{ r: 3 }} name="Harga" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </GlassCard>
          )}

          <GlassCard className="p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="cost-history-table">
                <thead className="bg-[var(--glass-bg)]">
                  <tr className="text-left text-xs text-muted-foreground">
                    <th className="px-3 py-3">Waktu</th>
                    {!selectedId && <th className="px-3 py-3">Barang</th>}
                    <th className="px-3 py-3">Sumber</th>
                    <th className="px-3 py-3 text-right">Qty masuk</th>
                    <th className="px-3 py-3 text-right">Harga masuk</th>
                    <th className="px-3 py-3 text-right">Harga lama</th>
                    <th className="px-3 py-3 text-right">Harga baru</th>
                    <th className="px-3 py-3 text-right">Perubahan</th>
                    <th className="px-3 py-3">Oleh</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingData ? (
                    <tr><td colSpan={9} className="text-center py-12 text-muted-foreground">Memuat…</td></tr>
                  ) : items.length === 0 ? (
                    <tr><td colSpan={9} className="py-12">
                      <div className="text-center max-w-xl mx-auto space-y-2" data-testid="cost-empty">
                        <Info className="w-7 h-7 mx-auto text-muted-foreground" />
                        <div className="font-medium text-foreground">Belum ada perubahan harga</div>
                        <div className="text-xs text-muted-foreground" data-testid="cost-empty-reason">
                          {data?.reason || 'Riwayat terisi sendiri setiap kali barang diterima dari pembelian.'}
                        </div>
                      </div>
                    </td></tr>
                  ) : items.map(r => (
                    <tr key={r.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)]"
                      data-testid={`cost-row-${r.id}`}>
                      <td className="px-3 py-2 text-xs text-foreground whitespace-nowrap">{dtFull(r.created_at)}</td>
                      {!selectedId && (
                        <td className="px-3 py-2">
                          <div className="font-mono text-[11px] text-muted-foreground">{r.material_code}</div>
                          <div className={r.material_missing ? 'text-[11px] text-amber-600 dark:text-amber-300' : 'text-foreground'}>
                            {r.material_name}
                          </div>
                        </td>
                      )}
                      <td className="px-3 py-2"><SourceChip row={r} /></td>
                      <td className="px-3 py-2 text-right font-mono text-xs text-foreground">{num(r.qty_in)}</td>
                      <td className="px-3 py-2 text-right font-mono text-xs text-foreground">{rp(r.unit_cost_in)}</td>
                      <td className="px-3 py-2 text-right font-mono text-xs text-muted-foreground">{rp(r.old_unit_cost)}</td>
                      <td className="px-3 py-2 text-right font-mono text-xs font-semibold text-foreground">
                        <span className="inline-flex items-center gap-1">
                          <ArrowRight className="w-3 h-3 text-muted-foreground" /> {rp(r.new_unit_cost)}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        {r.change_pct == null ? (
                          <span className="text-[11px] text-muted-foreground">harga pertama</span>
                        ) : (
                          <span className={`font-mono text-xs font-semibold ${r.change_pct > 0 ? 'text-red-500' : r.change_pct < 0 ? 'text-emerald-600 dark:text-emerald-300' : 'text-muted-foreground'}`}
                            data-testid={`cost-change-${r.id}`}>
                            {r.change_pct > 0 ? '+' : ''}{r.change_pct}%
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">
                        {r.actor_name}
                        {r.notes && <span className="block text-[10px] line-clamp-1" title={r.notes}>{r.notes}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>

          <div className="text-xs text-muted-foreground flex items-start gap-1.5">
            <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            <span>
              Harga barang TIDAK pernah diketik di modul mana pun — ia lahir dari penerimaan
              pembelian (rata-rata bergerak). Baris bertanda <em>Hasil cutting</em> adalah nilai
              potongan yang lahir saat kain dipotong (sesi #32), dan <em>Koreksi manual</em> hanya
              bisa dilakukan di layar Valuasi.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
