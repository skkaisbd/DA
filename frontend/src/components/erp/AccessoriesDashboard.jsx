/**
 * AccessoriesDashboard — Portal Aksesoris MVP
 * Session #11.21 — Dedicated Accessories Portal
 *
 * KPI cards + quick view panels
 * Endpoint: GET /api/acc/dashboard
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Package, AlertTriangle, Clock, PackageCheck, ShoppingCart,
  TrendingDown, RefreshCw, ChevronRight, CheckCircle,
  Table2, LayoutGrid, ArrowUpDown, Search,
} from 'lucide-react';
// F15-B — nama warna boleh dinamis, KELASNYA tidak. `bg-${color}-500/5` tidak
// pernah dibuat Tailwind (ia membaca teks, bukan menjalankan JS). Terukur:
// kartu KPI "Perlu Diserahkan" (teal) memang tanpa latar & tanpa garis di
// bundel hasil build. Lihat `lib/tone.js`.
import { tone } from '@/lib/tone';
import ExportCsvButton from '@/components/ui/export-csv-button';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const ACC_VIEW_KEY = 'acc_stock_view';
const CSV_HEAD = ['Kode', 'Nama', 'Kategori', 'Satuan', 'Stok', 'Min. stok',
  'Status stok', 'HPP satuan', 'Nilai stok', 'Sudah dinilai', 'Metode biaya'];

const API = process.env.REACT_APP_BACKEND_URL || '';

function fmtDate(iso) {
  if (!iso) return '-';
  try { return new Date(iso).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return iso?.slice(0, 10) || '-'; }
}

function fmtNum(n) { return Number(n || 0).toLocaleString('id-ID'); }
const fmtRp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;

function KPICard({ label, value, icon: Icon, color, subtext }) {
  const t = tone(color);
  return (
    <div
      className={`border rounded-xl p-4 flex flex-col gap-2 ${t.surface}`}
      data-testid={`acc-kpi-${label.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <div className="flex items-center gap-2">
        <div className={`w-8 h-8 rounded-lg border flex items-center justify-center ${t.chip}`}>
          <Icon className={`w-4 h-4 ${t.text}`} />
        </div>
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      <div className={`text-3xl font-bold ${t.text}`}>{fmtNum(value)}</div>
      {subtext && <p className="text-xs text-muted-foreground">{subtext}</p>}
    </div>
  );
}

function Skeleton({ className = '' }) {
  return <div className={`animate-pulse bg-foreground/5 rounded-lg ${className}`} />;
}

export default function AccessoriesDashboard({ token }) {
  const [dash, setDash]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState('');

  // ── F13-B (sesi #12) — DAFTAR STOK, bukan cuma angka ringkas ─────────────
  // Layar ini dulu hanya KPI + dua panel ringkas. Nilainya nyata (stok
  // aksesoris bernilai puluhan juta) tetapi tidak ada satu pun daftar yang bisa
  // diurutkan atau diunduh. Dua pertanyaan yang paling sering ditanya karena
  // itu tidak terjawab: "aksesoris mana yang nilainya paling besar?" dan
  // "item mana yang BELUM DINILAI?" — item tak bernilai membuat nilai stok
  // total lebih rendah dari kenyataan, dan itu masuk ke laporan keuangan.
  const [stock, setStock]     = useState([]);
  const [stockErr, setStockErr] = useState('');
  const [search, setSearch]   = useState('');
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(ACC_VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  useEffect(() => {
    try { localStorage.setItem(ACC_VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);
  const [sort, setSort] = useState({ key: 'stock_value', dir: 'desc' });

  const loadDash = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const r = await fetch(`${API}/api/acc/dashboard`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setDash(data);
    } catch (e) {
      setError(e.message || 'Gagal memuat dashboard');
    } finally {
      setLoading(false);
    }
  }, [token]);

  const loadStock = useCallback(async () => {
    if (!token) return;
    setStockErr('');
    try {
      const r = await fetch(`${API}/api/acc/stock`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setStock(Array.isArray(d) ? d : (d.items || []));
    } catch (e) {
      setStock([]);
      setStockErr(e.message || 'Gagal memuat daftar stok');
    }
  }, [token]);

  useEffect(() => { loadDash(); }, [loadDash]);
  useEffect(() => { loadStock(); }, [loadStock]);

  const stockStatus = (it) => {
    const q = Number(it.stock_qty || 0), min = Number(it.min_stock || 0);
    if (q <= 0) return 'Habis';
    if (min > 0 && q <= min) return 'Hampir habis';
    return 'Aman';
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return stock;
    return stock.filter((it) =>
      String(it.code || '').toLowerCase().includes(q)
      || String(it.name || '').toLowerCase().includes(q)
      || String(it.category || '').toLowerCase().includes(q));
  }, [stock, search]);

  const rows = useMemo(() => {
    const list = [...filtered];
    const { key, dir } = sort;
    list.sort((a, b) => {
      const av = a?.[key], bv = b?.[key];
      const num = typeof av === 'number' || typeof bv === 'number';
      const cmp = num ? (Number(av || 0) - Number(bv || 0))
        : String(av ?? '').localeCompare(String(bv ?? ''), 'id');
      return dir === 'asc' ? cmp : -cmp;
    });
    return list;
  }, [filtered, sort]);
  const { page, setPage, totalPages, total, paged, pageSize } = useClientPagination(rows, 12);
  const toggleSort = (key) => setSort((s) => (
    s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }));
  const csvRows = rows.map((it) => [
    it.code, it.name, it.category || '', it.unit || '',
    it.stock_qty ?? 0, it.min_stock ?? 0, stockStatus(it),
    it.unit_cost ?? 0, it.stock_value ?? 0,
    it.valued ? 'ya' : 'BELUM', it.cost_method || '',
  ]);
  const unvalued = rows.filter((it) => !it.valued).length;

  return (
    <div className="space-y-6" data-testid="accessories-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Dashboard Aksesoris</h2>
          <p className="text-muted-foreground text-sm mt-1">Ringkasan stok, request, dan peminjaman aksesoris produksi</p>
        </div>
        <button
          onClick={loadDash}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground px-3 py-1.5 rounded-lg border border-foreground/10 hover:bg-foreground/5 transition-colors"
          data-testid="acc-dash-refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-100 dark:bg-red-500/10 border border-red-300 dark:border-red-500/20 rounded-xl p-4 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {/* KPI Cards */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : dash ? (
        <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard
            label="Total Item"
            value={dash.total_items ?? 0}
            icon={Package}
            color="violet"
            subtext="Item aksesoris aktif"
          />
          <KPICard
            label="Stok Rendah"
            value={(dash.out_of_stock ?? 0) + (dash.low_stock ?? 0)}
            icon={AlertTriangle}
            color="amber"
            subtext={`${dash.out_of_stock ?? 0} habis · ${dash.low_stock ?? 0} hampir habis`}
          />
          <KPICard
            label="Request Pending"
            value={dash.pending_requests ?? 0}
            icon={Clock}
            color="sky"
            subtext="Menunggu persetujuan"
          />
          <KPICard
            label="Perlu Diserahkan"
            value={dash.ready_to_deliver ?? 0}
            icon={PackageCheck}
            color="teal"
            subtext={`Sudah disetujui · PR pending: ${dash.pending_pr ?? 0}`}
          />
        </div>
      ) : null}

      {/* Active Opname Alert */}
      {dash?.active_opname && (
        <div className="bg-sky-100 dark:bg-sky-500/10 border border-sky-300 dark:border-sky-500/20 rounded-xl p-4 flex items-center gap-3">
          <CheckCircle className="w-5 h-5 text-sky-600 dark:text-sky-400 shrink-0" />
          <div>
            <p className="text-sm font-medium text-sky-600 dark:text-sky-300">Sesi Opname Sedang Berjalan</p>
            <p className="text-xs text-muted-foreground">No. sesi: {dash.active_opname}</p>
          </div>
        </div>
      )}

      {/* ── DAFTAR STOK AKSESORIS (F13-B) ──────────────────────────────────
          Nilai stok adalah angka yang masuk laporan keuangan. Kalau ia hanya
          bisa dilihat sebagai ringkasan, "kenapa nilainya segini" tidak pernah
          bisa ditelusuri ke item-nya. */}
      <div className="rounded-xl border border-border bg-card">
        <div className="flex flex-wrap items-center gap-2 p-3 border-b border-border">
          <h3 className="text-sm font-semibold flex items-center gap-2 mr-auto">
            <Package className="w-4 h-4 text-muted-foreground" />
            Daftar Stok Aksesoris
            <span className="text-xs font-normal text-muted-foreground">
              {rows.length} item · nilai {fmtRp(rows.reduce((s, i) => s + Number(i.stock_value || 0), 0))}
            </span>
          </h3>
          <div className="relative min-w-[180px]">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Cari kode / nama / kategori..."
              data-testid="acc-stock-search"
              className="h-8 w-full pl-8 pr-2 rounded-lg border border-border bg-background text-xs" />
          </div>
          <div className="inline-flex rounded-lg border border-border overflow-hidden">
            <button type="button" onClick={() => setView('table')} data-testid="acc-view-table"
              className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
                ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
              <Table2 size={12} /> Tabel
            </button>
            <button type="button" onClick={() => setView('grid')} data-testid="acc-view-grid"
              className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
                ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
              <LayoutGrid size={12} /> Kartu
            </button>
          </div>
          <ExportCsvButton filename="stok-aksesoris" testId="acc-export-csv"
            head={CSV_HEAD} rows={csvRows}
            note={unvalued ? `${unvalued} item BELUM dinilai` : 'semua item sudah dinilai'} />
        </div>

        {/* Item yang belum dinilai DIAKUI di layar: nilai stok total pasti
            lebih rendah dari kenyataan selama angka ini > 0. */}
        {unvalued > 0 && (
          <div className="mx-3 mt-3 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 dark:border-amber-700 dark:bg-amber-900/25"
               data-testid="acc-unvalued-banner">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
            <p className="text-xs text-amber-900 dark:text-amber-200">
              <b>{unvalued} item belum punya nilai (HPP).</b> Selama itu belum diisi,
              total nilai stok di atas LEBIH RENDAH dari kenyataan — dan angka itu
              ikut ke laporan keuangan. Urutkan kolom <b>Sudah dinilai</b> untuk melihatnya.
            </p>
          </div>
        )}

        {stockErr ? (
          <p className="p-6 text-center text-sm text-muted-foreground">{stockErr}</p>
        ) : rows.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted-foreground">
            {search ? 'Tidak ada item yang cocok dengan pencarian' : 'Belum ada item aksesoris'}
          </p>
        ) : view === 'table' ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs" data-testid="acc-table">
                <thead className="bg-muted/50">
                  <tr className="text-left">
                    {[['code', 'Kode'], ['name', 'Nama'], ['category', 'Kategori'],
                      ['unit', 'Satuan'], ['stock_qty', 'Stok'], ['min_stock', 'Min. stok'],
                      ['unit_cost', 'HPP satuan'], ['stock_value', 'Nilai stok'],
                      ['valued', 'Sudah dinilai'], ['cost_method', 'Metode biaya']].map(([k, label]) => (
                      <th key={k} className="px-2.5 py-2 font-semibold whitespace-nowrap">
                        <button type="button" onClick={() => toggleSort(k)}
                          data-testid={`acc-sort-${k}`}
                          className="inline-flex items-center gap-1 hover:text-primary">
                          {label}
                          <ArrowUpDown size={10}
                            className={sort.key === k ? 'text-primary' : 'opacity-30'} />
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {paged.map((it) => {
                    const st = stockStatus(it);
                    return (
                      <tr key={it.id} className="border-t border-border hover:bg-muted/40"
                          data-testid={`acc-stock-row-${it.code}`}>
                        <td className="px-2.5 py-2 font-mono whitespace-nowrap">{it.code}</td>
                        <td className="px-2.5 py-2">{it.name}</td>
                        <td className="px-2.5 py-2 text-muted-foreground">{it.category || '—'}</td>
                        <td className="px-2.5 py-2">{it.unit || '—'}</td>
                        <td className={`px-2.5 py-2 text-right font-semibold ${st === 'Habis'
                          ? 'text-red-600 dark:text-red-400' : st === 'Hampir habis'
                            ? 'text-amber-700 dark:text-amber-400' : ''}`}>
                          {fmtNum(it.stock_qty)}
                        </td>
                        <td className="px-2.5 py-2 text-right text-muted-foreground">{fmtNum(it.min_stock)}</td>
                        <td className="px-2.5 py-2 text-right whitespace-nowrap">{fmtRp(it.unit_cost)}</td>
                        <td className="px-2.5 py-2 text-right font-semibold whitespace-nowrap">{fmtRp(it.stock_value)}</td>
                        <td className="px-2.5 py-2">
                          {it.valued ? (
                            <span className="text-emerald-600 dark:text-emerald-400">ya</span>
                          ) : (
                            <span className="inline-flex items-center gap-1 rounded border border-amber-400 bg-amber-100 px-1.5 py-0.5 font-medium text-amber-900 dark:border-amber-600 dark:bg-amber-900/40 dark:text-amber-200">
                              BELUM
                            </span>
                          )}
                        </td>
                        <td className="px-2.5 py-2 text-muted-foreground">{it.cost_method || '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <PaginationLite page={page} totalPages={totalPages} total={total}
              pageSize={pageSize} onPageChange={setPage} className="px-3" />
          </>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 p-3">
              {paged.map((it) => (
                <div key={it.id} className="rounded-lg border border-border bg-background p-3"
                     data-testid={`acc-stock-card-${it.code}`}>
                  <p className="text-sm font-medium truncate" title={it.name}>{it.name}</p>
                  <p className="text-xs font-mono text-muted-foreground">{it.code}</p>
                  <div className="mt-2 flex items-end justify-between">
                    <div>
                      <p className="text-xs text-muted-foreground">Stok</p>
                      <p className="text-sm font-semibold">{fmtNum(it.stock_qty)} {it.unit}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground">Nilai</p>
                      <p className="text-sm font-semibold">{fmtRp(it.stock_value)}</p>
                    </div>
                  </div>
                  {!it.valued && (
                    <p className="mt-1.5 text-[11px] text-amber-700 dark:text-amber-400">belum dinilai</p>
                  )}
                </div>
              ))}
            </div>
            <PaginationLite page={page} totalPages={totalPages} total={total}
              pageSize={pageSize} onPageChange={setPage} className="px-3" />
          </>
        )}
      </div>

      {/* Two-Column Panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Low Stock Items */}
        <div className="bg-amber-100 dark:bg-amber-500/5 border border-amber-300 dark:border-amber-500/20 rounded-xl p-5" data-testid="acc-low-stock-panel">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <TrendingDown className="w-4 h-4 text-amber-700 dark:text-amber-400" />
              <span>Item Stok Rendah / Habis</span>
            </h3>
            {dash?.low_stock_items?.length > 0 && (
              <span className="text-xs text-amber-700 dark:text-amber-400">{dash.low_stock_items.length} item</span>
            )}
          </div>

          {loading ? (
            <div className="space-y-2">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-10" />)}</div>
          ) : (dash?.low_stock_items?.length ?? 0) === 0 ? (
            <div className="text-center py-8">
              <CheckCircle className="w-8 h-8 text-emerald-600 dark:text-emerald-400 mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">Semua item stok aman</p>
            </div>
          ) : (
            <div className="space-y-2">
              {dash.low_stock_items.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-2.5 rounded-lg bg-amber-100 dark:bg-amber-500/5 border border-amber-500/15"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{item.name}</p>
                    <p className="text-xs text-muted-foreground">{item.code}</p>
                  </div>
                  <div className="text-right shrink-0 ml-3">
                    <p className="text-sm text-amber-700 dark:text-amber-400 font-semibold">
                      {fmtNum(item.stock_qty)} {item.unit}
                    </p>
                    <p className="text-xs text-muted-foreground">min: {fmtNum(item.min_stock)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* PR Pending */}
        <div className="bg-sky-100 dark:bg-sky-500/5 border border-sky-300 dark:border-sky-500/20 rounded-xl p-5" data-testid="acc-pr-panel">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <ShoppingCart className="w-4 h-4 text-sky-600 dark:text-sky-400" />
              <span>Ringkasan Pengadaan</span>
            </h3>
          </div>

          <div className="space-y-3">
            <div className="flex justify-between items-center p-3 rounded-lg border border-foreground/10 bg-foreground/[0.02]">
              <span className="text-sm text-muted-foreground">PR Pending Persetujuan</span>
              <span className="text-sm font-semibold text-sky-600 dark:text-sky-400">{fmtNum(dash?.pending_pr ?? 0)}</span>
            </div>
            <div className="flex justify-between items-center p-3 rounded-lg border border-foreground/10 bg-foreground/[0.02]">
              <span className="text-sm text-muted-foreground">Sudah Disetujui, Belum Diserahkan</span>
              <span className="text-sm font-semibold text-teal-600 dark:text-teal-400">{fmtNum(dash?.ready_to_deliver ?? 0)}</span>
            </div>
            <div className="flex justify-between items-center p-3 rounded-lg border border-foreground/10 bg-foreground/[0.02]">
              <span className="text-sm text-muted-foreground">Request Internal Pending</span>
              <span className="text-sm font-semibold text-amber-700 dark:text-amber-400">{fmtNum(dash?.pending_requests ?? 0)}</span>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-foreground/10">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <ChevronRight className="w-3.5 h-3.5" />
              <span>Gunakan menu sidebar untuk aksi lanjutan</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
