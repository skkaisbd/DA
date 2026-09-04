import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ShoppingCart, RefreshCw, AlertTriangle, Wallet, BellRing, CheckCircle2,
  FileText, Info, Search, History, PackageSearch, Truck,
} from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';

/**
 * Daftar Belanja Mingguan (sesi #33) — "minggu ini saya harus belanja apa?"
 *
 * Kenapa layar ini ada: sebelum sesi #33 tidak ada satu pun layar yang menjawab
 * pertanyaan itu. `Alert & Reorder` hanya bilang "kurang n" tanpa satuan beli,
 * tanpa harga, dan tanpa jembatan ke Permintaan Pengadaan ⇒ hasilnya harus
 * diketik ulang manual. Kebutuhan di sini dihitung HANYA dari ambang minimum /
 * titik pesan ulang (keputusan pemilik), stok dibaca kanonik, qty dibulatkan ke
 * atas ke satuan BELI, dan MOQ supplier nyata menaikkan qty dengan alasan yang
 * disebut. Barang tanpa harga TIDAK diam-diam dihitung Rp0.
 */

const rp = (v) => `Rp${Math.round(Number(v) || 0).toLocaleString('id-ID')}`;
const num = (v) => Number(v || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 });

const STATUS_META = {
  critical: { label: 'Kritis', cls: 'bg-red-400/10 text-red-500 border-red-300/25' },
  low: { label: 'Perlu pesan', cls: 'bg-amber-400/10 text-amber-500 border-amber-300/25' },
};

export default function WeeklyShoppingListModule({ token, onNavigate }) {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [week, setWeek] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('list');
  const [history, setHistory] = useState(null);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('');
  const [hideRequested, setHideRequested] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [dialogOpen, setDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [notes, setNotes] = useState('');
  const [neededBy, setNeededBy] = useState('');
  const [lastPR, setLastPR] = useState(null);

  const headers = useMemo(() => ({
    Authorization: `Bearer ${token || localStorage.getItem('erp_token')}`,
    'Content-Type': 'application/json',
  }), [token]);

  const goto = useCallback((moduleId, tabKey) => {
    if (tabKey) { try { sessionStorage.setItem(`hub_tab_${moduleId}`, tabKey); } catch (e) { /* noop */ } }
    if (onNavigate) { onNavigate(moduleId); return; }
    const target = tabKey ? `#${moduleId}=${tabKey}` : `#${moduleId}`;
    if (window.location.hash === target) window.location.hash = '';
    window.location.hash = target;
  }, [onNavigate]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ include_requested: String(!hideRequested) });
      if (filterType) p.set('type', filterType);
      if (search.trim()) p.set('search', search.trim());
      const r = await fetch(`/api/rahaza/shopping-list/weekly?${p}`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setRows(d.rows || []);
      setSummary(d.summary || null);
      setWeek(d.week || null);
      setSelected(new Set());
    } catch (e) {
      toast.error(`Gagal memuat daftar belanja: ${e.message}`);
    } finally { setLoading(false); }
  }, [headers, filterType, search, hideRequested]);

  const loadHistory = useCallback(async () => {
    try {
      const r = await fetch('/api/rahaza/shopping-list/history?limit=100', { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setHistory(await r.json());
    } catch (e) {
      toast.error(`Gagal memuat riwayat: ${e.message}`);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === 'history' && !history) loadHistory(); }, [tab, history, loadHistory]);

  const selectable = useMemo(() => rows.filter(r => !r.already_requested), [rows]);
  const chosen = useMemo(() => rows.filter(r => selected.has(r.material_id)), [rows, selected]);
  const chosenTotal = useMemo(
    () => chosen.reduce((s, r) => s + (r.valued ? Number(r.est_total || 0) : 0), 0), [chosen]);

  const toggle = (id) => setSelected(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const toggleAll = () => setSelected(prev =>
    prev.size === selectable.length ? new Set() : new Set(selectable.map(r => r.material_id)));

  const createPR = async () => {
    if (!chosen.length) return;
    setCreating(true);
    try {
      const r = await fetch('/api/rahaza/shopping-list/create-pr', {
        method: 'POST', headers,
        body: JSON.stringify({
          material_ids: chosen.map(c => c.material_id),
          notes: notes.trim() || undefined,
          needed_by: neededBy || undefined,
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      setLastPR({ ...(d.request || {}), skipped: d.skipped || [] });
      setDialogOpen(false);
      setNotes(''); setNeededBy('');
      toast.success(d.pesan || `Permintaan Pengadaan ${d.request?.request_number} dibuat.`);
      setHistory(null);
      load();
    } catch (e) {
      toast.error(`Gagal membuat PR: ${e.message}`);
    } finally { setCreating(false); }
  };

  const cards = summary ? [
    { k: 'need_buy', label: 'Perlu dibeli minggu ini', v: num(summary.need_buy),
      sub: `${summary.critical || 0} kritis · ${summary.with_supplier || 0} punya supplier`,
      tone: 'text-primary', icon: ShoppingCart },
    { k: 'value', label: 'Perkiraan nilai belanja', v: rp(summary.est_total_value),
      sub: 'dari harga supplier / HPP pembelian', tone: 'text-emerald-600 dark:text-emerald-300',
      icon: Wallet },
    { k: 'unvalued', label: 'Belum berharga', v: num(summary.unvalued_count),
      sub: 'tidak dihitung ke perkiraan total', tone: 'text-amber-600 dark:text-amber-300',
      icon: Info },
    { k: 'no_threshold', label: 'Belum berambang', v: num(summary.without_threshold),
      sub: `dari ${num(summary.total_materials)} barang aktif`, tone: 'text-red-500', icon: BellRing },
  ] : [];

  return (
    <div className="space-y-4" data-testid="shopping-list-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
            <ShoppingCart className="w-5 h-5 text-primary" /> Daftar Belanja Mingguan
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5" data-testid="shopping-week-label">
            {week ? `Minggu ${week.iso} · ${week.label}` : 'Menghitung…'} — kebutuhan dihitung dari
            ambang minimum / titik pesan ulang, stok dibaca lintas semua lokasi.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={load} disabled={loading} data-testid="shopping-refresh">
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Muat ulang
          </Button>
          <Button onClick={() => setDialogOpen(true)} disabled={!chosen.length}
            data-testid="shopping-create-pr">
            <FileText className="w-4 h-4 mr-1.5" />
            Buat PR Pengadaan{chosen.length ? ` (${chosen.length})` : ''}
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-1 border-b border-[var(--glass-border)]">
        {[['list', 'Perlu Dibeli', ShoppingCart], ['history', 'PR dari layar ini', History]].map(
          ([key, label, Icon]) => (
            <button key={key} onClick={() => setTab(key)}
              className={`px-3 py-2 text-sm font-medium inline-flex items-center gap-1.5 border-b-2 -mb-px transition-colors ${
                tab === key ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
              data-testid={`shopping-tab-${key}`}>
              <Icon className="w-3.5 h-3.5" /> {label}
            </button>
          ))}
      </div>

      {tab === 'list' && (
        <>
          {summary && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="shopping-summary">
              {cards.map(c => (
                <GlassCard key={c.k} className="p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className={`text-2xl font-bold ${c.tone}`} data-testid={`shopping-stat-${c.k}`}>{c.v}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">{c.label}</div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">{c.sub}</div>
                    </div>
                    <c.icon className="w-4 h-4 text-muted-foreground shrink-0" />
                  </div>
                </GlassCard>
              ))}
            </div>
          )}

          {summary && summary.without_threshold > 0 && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-300/40 bg-amber-50 dark:bg-amber-400/10 px-4 py-3"
              data-testid="shopping-threshold-notice">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <div className="text-sm text-amber-700 dark:text-amber-300">
                {summary.without_threshold_note}
                <button onClick={() => goto('wh-master', 'thresholds')}
                  className="ml-1 underline font-medium" data-testid="shopping-goto-thresholds">
                  Isi Ambang Massal sekarang
                </button>
              </div>
            </div>
          )}

          {lastPR && (
            <div className="flex items-start gap-2 rounded-lg border border-emerald-300/40 bg-emerald-50 dark:bg-emerald-400/10 px-4 py-3"
              data-testid="shopping-pr-result">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <div className="text-sm text-emerald-700 dark:text-emerald-300">
                <strong>{lastPR.request_number}</strong> dibuat sebagai draft ·{' '}
                {(lastPR.items || []).length} barang · {rp(lastPR.total_estimated)}.{' '}
                <button onClick={() => goto('proc-requests')} className="underline font-medium"
                  data-testid="shopping-open-pr">Buka Permintaan Pengadaan</button>
                {!!(lastPR.skipped || []).length && (
                  <div className="text-xs mt-1">
                    {lastPR.skipped.length} barang dilewati: {lastPR.skipped.map(s => `${s.code || s.material_id} (${s.reason})`).join('; ')}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative flex-1 min-w-[180px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <GlassInput value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Cari kode / nama barang…" className="pl-8 h-9 text-sm"
                data-testid="shopping-search" />
            </div>
            <select value={filterType} onChange={e => setFilterType(e.target.value)}
              className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              data-testid="shopping-filter-type">
              <option value="">Semua jenis</option>
              <option value="bahan">Bahan (kain/benang)</option>
              <option value="aksesoris">Aksesoris</option>
              <option value="fg">Produk Jadi</option>
            </select>
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
              <input type="checkbox" checked={hideRequested}
                onChange={e => setHideRequested(e.target.checked)}
                data-testid="shopping-hide-requested" />
              Sembunyikan yang sudah ber-PR
            </label>
            {!!selectable.length && (
              <Button variant="outline" size="sm" onClick={toggleAll} data-testid="shopping-select-all">
                {selected.size === selectable.length ? 'Batalkan semua' : `Pilih semua (${selectable.length})`}
              </Button>
            )}
          </div>

          <GlassCard className="p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="shopping-table">
                <thead className="bg-[var(--glass-bg)]">
                  <tr className="text-left text-xs text-muted-foreground">
                    <th className="px-3 py-3 w-8"></th>
                    <th className="px-3 py-3">Barang</th>
                    <th className="px-3 py-3 text-right">Stok</th>
                    <th className="px-3 py-3 text-right">Ambang</th>
                    <th className="px-3 py-3 text-right">Kurang</th>
                    <th className="px-3 py-3 text-right">Qty beli</th>
                    <th className="px-3 py-3 text-right">Harga</th>
                    <th className="px-3 py-3 text-right">Perkiraan total</th>
                    <th className="px-3 py-3">Supplier</th>
                    <th className="px-3 py-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={10} className="text-center py-12 text-muted-foreground">Memuat…</td></tr>
                  ) : rows.length === 0 ? (
                    <tr><td colSpan={10} className="py-12">
                      <div className="text-center max-w-lg mx-auto space-y-2" data-testid="shopping-empty">
                        <PackageSearch className="w-8 h-8 mx-auto text-muted-foreground" />
                        {summary && summary.with_threshold === 0 ? (
                          <>
                            <div className="font-medium text-foreground">Belum ada satu pun ambang stok yang diisi</div>
                            <div className="text-xs text-muted-foreground">
                              Selama ambang minimum kosong, sistem tidak bisa tahu barang apa yang
                              perlu dibeli. Isi ambangnya massal dulu — bisa dari lot pembelian nyata,
                              persen stok, atau angka yang Anda tentukan.
                            </div>
                            <Button size="sm" className="mt-1" onClick={() => goto('wh-master', 'thresholds')}
                              data-testid="shopping-empty-cta">Isi Ambang Massal</Button>
                          </>
                        ) : (
                          <>
                            <div className="font-medium text-foreground">Tidak ada yang perlu dibeli minggu ini</div>
                            <div className="text-xs text-muted-foreground">
                              Semua barang yang sudah punya ambang stoknya masih di atas ambang.
                              {summary && summary.without_threshold > 0
                                && ` Catatan: ${summary.without_threshold} barang belum berambang, jadi daftar ini belum lengkap.`}
                            </div>
                          </>
                        )}
                      </div>
                    </td></tr>
                  ) : rows.map(r => {
                    const meta = STATUS_META[r.stock_status] || STATUS_META.low;
                    const isSel = selected.has(r.material_id);
                    return (
                      <tr key={r.material_id}
                        className={`border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] ${isSel ? 'bg-primary/5' : ''} ${r.already_requested ? 'opacity-70' : ''}`}
                        data-testid={`shopping-row-${r.code}`}>
                        <td className="px-3 py-2">
                          <input type="checkbox" checked={isSel} disabled={r.already_requested}
                            onChange={() => toggle(r.material_id)}
                            data-testid={`shopping-check-${r.code}`} />
                        </td>
                        <td className="px-3 py-2">
                          <div className="font-mono text-xs text-foreground">{r.code}</div>
                          <div className="text-foreground">{r.name}</div>
                          <div className="text-[10px] text-muted-foreground">{r.type} · {r.base_uom}</div>
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs whitespace-nowrap text-foreground">
                          {num(r.onhand)} {r.base_uom}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs whitespace-nowrap text-foreground">
                          {num(r.alert_at)}
                          <span className="block text-[10px] text-muted-foreground font-sans"
                            title={r.threshold_basis_note || ''}>
                            {r.threshold_basis ? `dasar: ${r.threshold_basis}` : r.threshold_source}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs text-red-500 whitespace-nowrap">
                          {num(r.shortage)}
                        </td>
                        <td className="px-3 py-2 text-right whitespace-nowrap" data-testid={`shopping-qty-${r.code}`}>
                          <span className="font-mono text-xs font-semibold text-foreground">
                            {num(r.qty_buy)} {r.purchase_uom}
                          </span>
                          {r.purchase_factor !== 1 && (
                            <span className="block text-[10px] text-muted-foreground">= {num(r.qty_buy_base)} {r.base_uom}</span>
                          )}
                          {r.qty_note && (
                            <span className="block text-[10px] text-amber-600 dark:text-amber-300">{r.qty_note}</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          {r.valued ? (
                            <>
                              <span className="font-mono text-xs text-foreground">{rp(r.price_per_purchase_uom)}</span>
                              <span className="block text-[10px] text-muted-foreground">/{r.purchase_uom} · {r.price_source === 'supplier_price_list' ? 'harga supplier' : 'HPP pembelian'}</span>
                            </>
                          ) : (
                            <span className="text-[11px] text-amber-600 dark:text-amber-300">belum ada harga</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs font-semibold text-foreground whitespace-nowrap"
                          data-testid={`shopping-total-${r.code}`}>
                          {r.valued ? rp(r.est_total) : '—'}
                        </td>
                        <td className="px-3 py-2 text-xs">
                          {r.supplier ? (
                            <>
                              <span className="text-foreground inline-flex items-center gap-1">
                                <Truck className="w-3 h-3" /> {r.supplier.name}
                              </span>
                              <span className="block text-[10px] text-muted-foreground">
                                {rp(r.supplier.price)}/{r.supplier.uom}
                                {r.supplier.moq > 0 ? ` · MOQ ${num(r.supplier.moq)}` : ''}
                                {r.supplier.lead_time_days ? ` · ${r.supplier.lead_time_days} hari` : ''}
                              </span>
                            </>
                          ) : (
                            <span className="text-[11px] text-muted-foreground">belum ada daftar harga</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {r.already_requested ? (
                            <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-sky-400/10 text-sky-600 border-sky-300/25"
                              data-testid={`shopping-pr-flag-${r.code}`}
                              title={`Dibuat ${String((r.pr || {}).created_at || '').slice(0, 10)}`}>
                              <CheckCircle2 className="w-3 h-3" /> {(r.pr || {}).number || 'sudah diminta'}
                            </span>
                          ) : (
                            <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${meta.cls}`}>
                              <AlertTriangle className="w-3 h-3" /> {meta.label}
                            </span>
                          )}
                          {!r.valued && (
                            <span className="block text-[10px] text-amber-600 dark:text-amber-300 mt-0.5">belum berharga</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </GlassCard>

          {summary && rows.length > 0 && (
            <div className="text-xs text-muted-foreground flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>
                {summary.unvalued_note} Qty beli dibulatkan KE ATAS ke satuan beli, dan dinaikkan
                ke MOQ supplier bila ada — alasannya tertulis di baris masing-masing.
                {summary.already_requested_count > 0
                  && ` ${summary.already_requested_count} barang sudah punya PR/PO minggu ini dan tidak dihitung lagi (anti dobel belanja).`}
              </span>
            </div>
          )}
        </>
      )}

      {tab === 'history' && (
        <GlassCard className="p-0 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--glass-border)]">
            <div>
              <div className="text-sm font-semibold text-foreground">Permintaan Pengadaan dari layar ini</div>
              <div className="text-xs text-muted-foreground">
                {history?.summary
                  ? `${history.summary.requests} PR · total ${rp(history.summary.total_value)}`
                  : 'Memuat…'}
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={() => { setHistory(null); loadHistory(); }}
              data-testid="shopping-history-refresh">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Muat ulang
            </Button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="shopping-history-table">
              <thead className="bg-[var(--glass-bg)]">
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="px-3 py-3">Nomor PR</th>
                  <th className="px-3 py-3">Minggu</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3 text-right">Baris</th>
                  <th className="px-3 py-3 text-right">Perkiraan nilai</th>
                  <th className="px-3 py-3">Diminta oleh</th>
                  <th className="px-3 py-3">Barang</th>
                </tr>
              </thead>
              <tbody>
                {!history ? (
                  <tr><td colSpan={7} className="text-center py-10 text-muted-foreground">Memuat…</td></tr>
                ) : (history.items || []).length === 0 ? (
                  <tr><td colSpan={7} className="text-center py-10 text-muted-foreground">
                    Belum ada PR yang dibuat dari Daftar Belanja Mingguan.
                  </td></tr>
                ) : history.items.map(h => (
                  <tr key={h.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)]"
                    data-testid={`shopping-history-row-${h.number}`}>
                    <td className="px-3 py-2 font-mono text-xs text-foreground">{h.number}</td>
                    <td className="px-3 py-2 text-xs text-foreground">{h.week}</td>
                    <td className="px-3 py-2"><Badge variant="secondary" className="text-[10px]">{h.status}</Badge></td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-foreground">{h.lines}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-foreground">{rp(h.total_estimated)}</td>
                    <td className="px-3 py-2 text-xs text-foreground">{h.requested_by_name || '—'}</td>
                    <td className="px-3 py-2 text-[11px] text-muted-foreground">
                      {(h.materials || []).map(m => `${m.code || ''} ${num(m.qty)} ${m.uom}`).join(' · ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl" data-testid="shopping-pr-dialog">
          <DialogHeader>
            <DialogTitle>Buat Permintaan Pengadaan · {chosen.length} barang</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="max-h-64 overflow-auto rounded-lg border border-[var(--glass-border)]">
              <table className="w-full text-sm">
                <thead className="bg-[var(--glass-bg)] sticky top-0">
                  <tr className="text-left text-xs text-muted-foreground">
                    <th className="px-3 py-2">Barang</th>
                    <th className="px-3 py-2 text-right">Qty</th>
                    <th className="px-3 py-2 text-right">Harga</th>
                    <th className="px-3 py-2 text-right">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {chosen.map(c => (
                    <tr key={c.material_id} className="border-t border-[var(--glass-border)]">
                      <td className="px-3 py-2 text-foreground">
                        <span className="font-mono text-xs">{c.code}</span> {c.name}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-xs text-foreground">{num(c.qty_buy)} {c.purchase_uom}</td>
                      <td className="px-3 py-2 text-right font-mono text-xs text-foreground">{c.valued ? rp(c.price_per_purchase_uom) : '—'}</td>
                      <td className="px-3 py-2 text-right font-mono text-xs text-foreground">{c.valued ? rp(c.est_total) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Perkiraan nilai PR</span>
              <span className="font-bold text-foreground" data-testid="shopping-dialog-total">{rp(chosenTotal)}</span>
            </div>
            {chosen.some(c => !c.valued) && (
              <div className="text-xs text-amber-600 dark:text-amber-300">
                Ada barang tanpa harga — barisnya tetap masuk PR dengan harga 0 supaya bagian
                pengadaan mengisi harga penawaran, tetapi tidak dihitung ke perkiraan nilai.
              </div>
            )}
            <div className="grid md:grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground">Dibutuhkan sebelum (opsional)</label>
                <GlassInput type="date" value={neededBy} onChange={e => setNeededBy(e.target.value)}
                  className="h-9 text-sm mt-1" data-testid="shopping-needed-by" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Catatan (opsional)</label>
                <GlassInput value={notes} onChange={e => setNotes(e.target.value)}
                  placeholder="mis. dipakai untuk order cutting minggu depan"
                  className="h-9 text-sm mt-1" data-testid="shopping-notes" />
              </div>
            </div>
            <div className="text-xs text-muted-foreground">
              PR dibuat berstatus <strong>draft</strong> — belum dikirim ke persetujuan. Kirimnya
              dari Portal Pengadaan → Permintaan Pengadaan.
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDialogOpen(false)} disabled={creating}>Batal</Button>
            <Button onClick={createPR} disabled={creating || !chosen.length}
              data-testid="shopping-pr-confirm">
              {creating ? 'Membuat…' : `Buat PR (${chosen.length} barang)`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
