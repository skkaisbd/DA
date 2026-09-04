/**
 * AccessoryValuationTab — FASE 8: Valuasi HPP Aksesoris.
 *
 * MASALAH YANG DIPECAHKAN
 * Harga satuan (HPP) aksesoris sudah bisa diisi & opname sudah berjurnal, tapi mutasi
 * harian (terima / keluar / scrap) tidak pernah dinilai ⇒ nilai persediaan aksesoris
 * tidak pernah cocok dengan buku besar, dan item ber-HPP 0 diam-diam membuat jurnal
 * gagal terbentuk. Tab ini menampilkan nilai persediaan, menyorot item BELUM DINILAI,
 * dan menyediakan dua aksi bernilai: koreksi HPP dan scrap (write-off).
 *
 * Sumber data: /api/acc/valuation (+ /valuation/set-cost, /api/acc/stock/scrap)
 */

import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import {
  Banknote, Coins, AlertTriangle, RefreshCw, Search, X, Trash2, Tag,
  CheckCircle2, Loader2, Package, Info, FileSpreadsheet, FileText, Download,
} from 'lucide-react';
import { EmptyState } from '../EmptyState';
import { Skeleton } from '@/components/ui/skeleton';
import AccessoryValuationLedger from './AccessoryValuationLedger';
// FASE 10: otomasi — ringkasan harian item belum dinilai + rapor bulanan via email
import AccessoryValuationAutomation from './AccessoryValuationAutomation';

const API = process.env.REACT_APP_BACKEND_URL || '';

async function api(method, path, token, body) {
  const opts = { method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(`${API}${path}`, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const e = new Error(data.detail || `HTTP ${r.status}`);
    e.status = r.status;
    throw e;
  }
  return data;
}

const fmtNum = (n) => Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 4 });
const fmtRp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 })}`;

const METHOD_LABEL = { moving_average: 'Rata-rata bergerak', manual: 'Manual' };

function Stat({ icon: Icon, label, value, hint, tone = 'violet' }) {
  const tones = {
    violet: 'text-violet-600 dark:text-violet-400 bg-violet-500/5 border-violet-500/20',
    emerald: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/5 border-emerald-500/20',
    amber: 'text-amber-700 dark:text-amber-400 bg-amber-500/5 border-amber-500/20',
    sky: 'text-sky-600 dark:text-sky-400 bg-sky-500/5 border-sky-500/20',
  };
  return (
    <div className={`rounded-xl border p-3 ${tones[tone]}`}>
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-4 h-4" />
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      <div className="text-xl font-bold">{value}</div>
      {hint && <div className="text-[11px] text-muted-foreground mt-0.5">{hint}</div>}
    </div>
  );
}

export default function AccessoryValuationTab({ token, onRefreshDash }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('');
  const [saving, setSaving] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [downloading, setDownloading] = useState('');
  const [costForm, setCostForm] = useState(null);   // {id, name, unit_cost, stock_qty}
  const [scrapForm, setScrapForm] = useState(null); // {id, name, unit, stock_qty, unit_cost}

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const d = await api('GET', '/api/acc/valuation', token);
      setData(d);
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const items = data?.items || [];
  const totals = data?.totals || {};
  const filtered = items.filter((it) => {
    if (filter === 'unvalued' && it.valued) return false;
    if (filter === 'instock' && !(it.stock_qty > 0)) return false;
    if (!search) return true;
    const q = search.toLowerCase();
    return (it.name || '').toLowerCase().includes(q) || (it.code || '').toLowerCase().includes(q);
  });
  const pg = useClientPagination(filtered, 10);

  // Rapor valuasi untuk lampiran laporan keuangan (Excel utk diolah, PDF utk ditandatangani).
  const downloadReport = async (fmt) => {
    setDownloading(fmt); setErr(''); setMsg('');
    try {
      const qs = new URLSearchParams({ format: fmt });
      if (month) qs.set('month', month);
      const r = await fetch(`${API}/api/acc/valuation/export?${qs}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || `HTTP ${r.status}`);
      }
      const blob = await r.blob();
      const cd = r.headers.get('Content-Disposition') || '';
      const guess = (cd.match(/filename="?([^";]+)"?/) || [])[1];
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = guess || `valuasi-aksesoris-${month || 'semua'}.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setMsg(`Rapor ${fmt.toUpperCase()} periode ${month || 'semua'} berhasil diunduh.`);
    } catch (e) { setErr(e.message); }
    finally { setDownloading(''); }
  };

  const saveCost = async () => {
    const val = parseFloat(costForm.unit_cost);
    if (!(val >= 0)) { setErr('Harga satuan harus angka ≥ 0'); return; }
    setSaving(true); setErr(''); setMsg('');
    try {
      const res = await api('POST', '/api/acc/valuation/set-cost', token, {
        acc_id: costForm.id, unit_cost: val, notes: costForm.notes || '',
      });
      setMsg(`HPP ${costForm.name} diperbarui: ${fmtRp(res.old_unit_cost)} → ${fmtRp(res.new_unit_cost)} · nilai stok ${fmtRp(res.stock_value)}`);
      setCostForm(null);
      setRefreshKey((k) => k + 1);
      await load();
      onRefreshDash?.();
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  const doScrap = async () => {
    const qty = parseFloat(scrapForm.qty);
    if (!qty || qty <= 0) { setErr('Qty scrap harus lebih dari 0'); return; }
    if (!(scrapForm.reason || '').trim()) { setErr('Alasan scrap wajib diisi (untuk jejak audit & jurnal)'); return; }
    setSaving(true); setErr(''); setMsg('');
    try {
      const res = await api('POST', '/api/acc/stock/scrap', token, {
        acc_id: scrapForm.id, qty, reason: scrapForm.reason, notes: scrapForm.notes || '',
      });
      setMsg(
        `Scrap ${fmtNum(res.qty_scrapped)} ${scrapForm.unit} · nilai ${fmtRp(res.value)} · `
        + (res.je?.posted ? `jurnal ${res.je.je_number} di-posting` : `tanpa jurnal (${res.je?.error || 'HPP 0'})`),
      );
      setScrapForm(null);
      setRefreshKey((k) => k + 1);
      await load();
      onRefreshDash?.();
    } catch (e) { setErr(e.message); }
    finally { setSaving(false); }
  };

  // Skeleton HANYA pada muat pertama (saat `data` masih kosong). Kalau tidak,
  // setiap refresh setelah aksi akan meng-UNMOUNT seluruh isi tab — termasuk
  // panel otomasi anak — sehingga pesan hasil aksi (mis. "SMTP belum diisi")
  // ikut hilang sebelum sempat terbaca user. Ini bug nyata yang ketemu saat uji UI.
  if (loading && !data) {
    return (
      <div className="space-y-4" data-testid="acc-valuation-loading">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
        <Skeleton className="h-48 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="acc-valuation-tab">
      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat icon={Banknote} label="Nilai Persediaan" value={fmtRp(totals.total_value)}
          hint={`${fmtNum(totals.total_qty)} unit · ${totals.total_items || 0} item`} tone="emerald" />
        <Stat icon={CheckCircle2} label="Item Bernilai" value={fmtNum(totals.valued_items)}
          hint="Punya harga satuan (HPP)" tone="sky" />
        <Stat icon={AlertTriangle} label="Belum Dinilai" value={fmtNum(totals.unvalued_items)}
          hint={totals.unvalued_items ? `${fmtNum(totals.unvalued_qty)} unit tanpa nilai` : 'Semua item sudah dinilai'}
          tone={totals.unvalued_items ? 'amber' : 'emerald'} />
        <Stat icon={Coins} label="HPP Rata-rata" value={fmtRp(totals.avg_unit_cost)}
          hint={METHOD_LABEL[data?.cost_method] || data?.cost_method} />
      </div>

      {err && <div className="text-sm text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10 border border-red-300 dark:border-red-500/20 rounded-lg px-4 py-2" data-testid="acc-val-error">{err}</div>}
      {msg && <div className="text-sm text-emerald-700 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-300 dark:border-emerald-500/20 rounded-lg px-4 py-2" data-testid="acc-val-msg">{msg}</div>}

      {/* Peringatan item belum dinilai */}
      {totals.unvalued_items > 0 && (
        <div className="bg-amber-100 dark:bg-amber-500/5 border border-amber-300 dark:border-amber-500/20 rounded-xl p-4"
          data-testid="acc-val-unvalued-banner">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="w-4 h-4 text-amber-700 dark:text-amber-400" />
            <span className="text-sm font-medium text-amber-700 dark:text-amber-400">
              {totals.unvalued_items} item belum punya harga satuan
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Selama HPP masih 0, setiap penerimaan / pengeluaran / selisih opname item tersebut
            TIDAK akan menghasilkan jurnal keuangan — nilai persediaan jadi tidak sinkron dengan buku besar.
            Isi harga satuan lewat tombol “Set HPP” di tabel bawah.
          </p>
          <button onClick={() => { setFilter('unvalued'); pg.setPage(1); }}
            className="mt-2 text-xs px-3 py-1.5 rounded-lg border border-amber-400 dark:border-amber-500/30 hover:bg-amber-200/40 dark:hover:bg-amber-500/10"
            data-testid="acc-val-filter-unvalued">
            Tampilkan item belum dinilai
          </button>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 border border-border rounded-lg px-3 py-2 bg-[var(--card-surface)] flex-1 min-w-48">
          <Search className="w-4 h-4 text-muted-foreground" />
          <input value={search} onChange={(e) => { setSearch(e.target.value); pg.setPage(1); }}
            placeholder="Cari aksesoris..." className="flex-1 bg-transparent text-sm focus:outline-none"
            data-testid="acc-val-search" />
          {search && <button onClick={() => setSearch('')}><X className="w-4 h-4 text-muted-foreground" /></button>}
        </div>
        <SmartNativeSelect value={filter} onChange={(e) => { setFilter(e.target.value); pg.setPage(1); }}
          className="border border-border rounded-lg px-3 py-2 bg-[var(--card-surface)] text-sm"
          data-testid="acc-val-filter">
          <option value="">Semua item</option>
          <option value="instock">Hanya berstok</option>
          <option value="unvalued">Belum dinilai</option>
        </SmartNativeSelect>
        <button onClick={load} className="p-2 border border-border rounded-lg hover:bg-foreground/5" data-testid="acc-val-refresh">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Rapor bulanan — lampiran laporan keuangan */}
      <div className="flex flex-wrap items-center gap-3 bg-[var(--card-surface)] border border-border rounded-xl px-4 py-3">
        <div className="flex items-center gap-2 text-sm">
          <Download className="w-4 h-4 text-muted-foreground" />
          <span className="font-medium">Rapor valuasi</span>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground" htmlFor="acc-val-month">Periode mutasi</label>
          <input id="acc-val-month" type="month" value={month} onChange={e => setMonth(e.target.value)}
            className="border border-border rounded-lg px-3 py-1.5 text-sm bg-[var(--card-surface)]"
            data-testid="acc-val-month" />
        </div>
        <button onClick={() => downloadReport('xlsx')} disabled={!!downloading}
          className="inline-flex items-center gap-2 px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-foreground/5 disabled:opacity-50"
          data-testid="acc-val-export-xlsx">
          {downloading === 'xlsx' ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileSpreadsheet className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />}
          Excel
        </button>
        <button onClick={() => downloadReport('pdf')} disabled={!!downloading}
          className="inline-flex items-center gap-2 px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-foreground/5 disabled:opacity-50"
          data-testid="acc-val-export-pdf">
          {downloading === 'pdf' ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4 text-red-700 dark:text-red-400" />}
          PDF
        </button>
        <span className="text-xs text-muted-foreground">
          Nilai persediaan = posisi terkini; periode hanya memfilter tabel mutasi.
        </span>
      </div>

      {/* FASE 10 — otomasi: ringkasan harian "belum dinilai" + rapor bulanan ke email keuangan */}
      <AccessoryValuationAutomation token={token} onChanged={load} />

      {/* Tabel valuasi */}
      <div className="bg-[var(--card-surface)] rounded-xl border border-border overflow-x-auto">
        <table className="w-full text-sm min-w-[840px]">
          <thead className="bg-[var(--glass-bg)] border-b border-border">
            <tr>
              <th className="text-left px-4 py-3 text-muted-foreground font-medium">Kode</th>
              <th className="text-left px-4 py-3 text-muted-foreground font-medium">Nama</th>
              <th className="text-left px-4 py-3 text-muted-foreground font-medium">Kategori</th>
              <th className="text-right px-4 py-3 text-muted-foreground font-medium">Stok</th>
              <th className="text-right px-4 py-3 text-muted-foreground font-medium">HPP</th>
              <th className="text-right px-4 py-3 text-muted-foreground font-medium">Nilai Stok</th>
              <th className="text-left px-4 py-3 text-muted-foreground font-medium">Metode</th>
              <th className="text-right px-4 py-3 text-muted-foreground font-medium">Aksi</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan="8">
                <EmptyState icon={Package} title="Tidak ada item"
                  description="Sesuaikan pencarian atau filter untuk melihat item aksesoris." />
              </td></tr>
            ) : pg.paged.map((it) => (
              <tr key={it.id} className="border-b border-border hover:bg-foreground/[0.02]" data-testid={`acc-val-row-${it.id}`}>
                <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{it.code}</td>
                <td className="px-4 py-3 font-medium">{it.name}</td>
                <td className="px-4 py-3 text-muted-foreground text-xs">{it.category}</td>
                <td className="px-4 py-3 text-right">{fmtNum(it.stock_qty)} <span className="text-xs text-muted-foreground">{it.unit}</span></td>
                <td className="px-4 py-3 text-right text-xs">
                  {it.valued ? fmtRp(it.unit_cost)
                    : <span className="text-amber-700 dark:text-amber-400" title="Belum dinilai — jurnal persediaan tidak akan terbentuk">belum diisi</span>}
                </td>
                <td className="px-4 py-3 text-right font-medium">{it.stock_value > 0 ? fmtRp(it.stock_value) : '-'}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground">{METHOD_LABEL[it.cost_method] || '-'}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1">
                    <button onClick={() => { setErr(''); setCostForm({ id: it.id, name: it.name, unit_cost: it.unit_cost || '', notes: '' }); }}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs border border-border hover:bg-foreground/5"
                      title="Set / koreksi harga satuan" data-testid={`acc-set-cost-${it.id}`}>
                      <Tag className="w-3.5 h-3.5" /> Set HPP
                    </button>
                    <button onClick={() => { setErr(''); setScrapForm({ id: it.id, name: it.name, unit: it.unit, stock_qty: it.stock_qty, unit_cost: it.unit_cost, qty: '', reason: '', notes: '' }); }}
                      disabled={!(it.stock_qty > 0)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs border border-border hover:bg-red-100 dark:hover:bg-red-500/10 disabled:opacity-40"
                      title={it.stock_qty > 0 ? 'Scrap / write-off' : 'Stok kosong'} data-testid={`acc-scrap-${it.id}`}>
                      <Trash2 className="w-3.5 h-3.5 text-red-700 dark:text-red-400" /> Scrap
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <PaginationLite page={pg.page} totalPages={pg.totalPages} total={pg.total}
          pageSize={pg.pageSize} onPageChange={pg.setPage} />
      </div>

      {/* Rekap per kategori */}
      {(data?.by_category || []).length > 0 && (
        <div className="bg-[var(--card-surface)] border border-border rounded-xl p-4">
          <div className="text-sm font-medium mb-3">Nilai persediaan per kategori</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {data.by_category.map((c) => (
              <div key={c.category} className="rounded-lg border border-border px-3 py-2" data-testid={`acc-val-cat-${c.category}`}>
                <div className="text-xs text-muted-foreground">{c.category}</div>
                <div className="text-lg font-bold">{fmtRp(c.value)}</div>
                <div className="text-[11px] text-muted-foreground">
                  {c.items} item · {fmtNum(c.qty)} unit
                  {c.unvalued_items ? ` · ${c.unvalued_items} belum dinilai` : ''}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Kartu stok bernilai + riwayat HPP */}
      <AccessoryValuationLedger token={token} refreshKey={refreshKey} />

      {/* Modal Set HPP */}
      {costForm && (
        <div className="fixed inset-0 bg-foreground/40 z-50 flex items-center justify-center p-4" onClick={() => setCostForm(null)}>
          <div className="bg-[var(--card-surface)] rounded-2xl shadow-xl w-full max-w-sm p-6" onClick={(e) => e.stopPropagation()}
            data-testid="acc-set-cost-modal">
            <h3 className="text-lg font-bold mb-1">Set Harga Satuan (HPP)</h3>
            <p className="text-sm text-muted-foreground mb-4">{costForm.name}</p>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Harga satuan (Rp) *</label>
                <input type="number" min="0" step="0.01" value={costForm.unit_cost}
                  onChange={(e) => setCostForm({ ...costForm, unit_cost: e.target.value })}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]"
                  placeholder="0" data-testid="acc-set-cost-input" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Catatan (opsional)</label>
                <input value={costForm.notes} onChange={(e) => setCostForm({ ...costForm, notes: e.target.value })}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]"
                  placeholder="mis. hasil audit harga beli terakhir" data-testid="acc-set-cost-notes" />
              </div>
              <div className="flex items-start gap-2 text-[11px] text-muted-foreground">
                <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                Koreksi manual hanya mengubah HPP ke depan (nilai stok & jurnal berikutnya). Jurnal yang sudah terbentuk tidak diubah.
              </div>
              {err && <div className="text-xs text-red-700 dark:text-red-400">{err}</div>}
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setCostForm(null)} className="flex-1 py-2 border border-border rounded-lg text-sm hover:bg-foreground/5">Batal</button>
              <button onClick={saveCost} disabled={saving}
                className="flex-1 py-2 bg-primary text-foreground rounded-lg text-sm hover:brightness-110 disabled:opacity-50 inline-flex items-center justify-center gap-2"
                data-testid="acc-set-cost-save">
                {saving && <Loader2 className="w-4 h-4 animate-spin" />} Simpan
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Scrap */}
      {scrapForm && (
        <div className="fixed inset-0 bg-foreground/40 z-50 flex items-center justify-center p-4" onClick={() => setScrapForm(null)}>
          <div className="bg-[var(--card-surface)] rounded-2xl shadow-xl w-full max-w-sm p-6" onClick={(e) => e.stopPropagation()}
            data-testid="acc-scrap-modal">
            <h3 className="text-lg font-bold mb-1">Scrap / Susut Aksesoris</h3>
            <p className="text-sm text-muted-foreground mb-4">
              {scrapForm.name} · stok {fmtNum(scrapForm.stock_qty)} {scrapForm.unit}
            </p>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Jumlah di-scrap ({scrapForm.unit}) *</label>
                <input type="number" min="0.01" step="0.01" value={scrapForm.qty}
                  onChange={(e) => setScrapForm({ ...scrapForm, qty: e.target.value })}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]"
                  placeholder="0" data-testid="acc-scrap-qty" />
                {scrapForm.qty > 0 && scrapForm.unit_cost > 0 && (
                  <small className="text-xs text-muted-foreground">
                    Nilai write-off ≈ {fmtRp(parseFloat(scrapForm.qty || 0) * scrapForm.unit_cost)}
                  </small>
                )}
              </div>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Alasan *</label>
                <SmartNativeSelect value={scrapForm.reason}
                  onChange={(e) => setScrapForm({ ...scrapForm, reason: e.target.value })}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]"
                  data-testid="acc-scrap-reason">
                  <option value="">— pilih alasan —</option>
                  <option value="Rusak">Rusak</option>
                  <option value="Hilang">Hilang</option>
                  <option value="Kadaluarsa">Kadaluarsa</option>
                  <option value="Cacat produksi">Cacat produksi</option>
                  <option value="Lain-lain">Lain-lain</option>
                </SmartNativeSelect>
              </div>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Catatan</label>
                <input value={scrapForm.notes} onChange={(e) => setScrapForm({ ...scrapForm, notes: e.target.value })}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-[var(--card-surface)]"
                  placeholder="Keterangan tambahan..." data-testid="acc-scrap-notes" />
              </div>
              <div className="flex items-start gap-2 text-[11px] text-muted-foreground">
                <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                Scrap = write-off nilai persediaan: jurnal Beban Scrap (Dr) / Persediaan (Cr) dibuat otomatis bila HPP sudah terisi.
              </div>
              {err && <div className="text-xs text-red-700 dark:text-red-400">{err}</div>}
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setScrapForm(null)} className="flex-1 py-2 border border-border rounded-lg text-sm hover:bg-foreground/5">Batal</button>
              <button onClick={doScrap} disabled={saving}
                className="flex-1 py-2 bg-red-600 text-white rounded-lg text-sm hover:brightness-110 disabled:opacity-50 inline-flex items-center justify-center gap-2"
                data-testid="acc-scrap-confirm">
                {saving && <Loader2 className="w-4 h-4 animate-spin" />} Scrap
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
