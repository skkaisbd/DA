/**
 * AccessoryValuationLedger — FASE 8 (bagian dari tab "Valuasi HPP").
 *
 * Dua tabel pendukung:
 *   • Mutasi Bernilai — kartu stok aksesoris beserta HPP, nilai, dan nomor jurnal.
 *     Kolom "Jurnal" menjawab pertanyaan paling sering: "kenapa nilai persediaan
 *     tidak sama dengan buku besar?" — baris tanpa jurnal langsung terlihat.
 *   • Riwayat HPP — jejak perubahan harga satuan (rata-rata bergerak vs koreksi manual).
 *
 * Sumber data: /api/acc/valuation/movements · /api/acc/valuation/cost-history
 */

import { useState, useEffect, useCallback } from 'react';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { History, ArrowDownCircle, ArrowUpCircle, Trash2, RefreshCw, Receipt } from 'lucide-react';
import { EmptyState } from '../EmptyState';
import { Skeleton } from '@/components/ui/skeleton';

const API = process.env.REACT_APP_BACKEND_URL || '';

async function api(method, path, token) {
  const r = await fetch(`${API}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data;
}

const fmtNum = (n) => Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 4 });
const fmtRp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 })}`;
const fmtDate = (iso) => {
  if (!iso) return '-';
  try {
    return new Date(iso).toLocaleDateString('id-ID', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch { return String(iso).slice(0, 16); }
};

const MV_META = {
  receive: { label: 'Terima', icon: ArrowDownCircle, tone: 'text-emerald-600 dark:text-emerald-400' },
  issue: { label: 'Keluar', icon: ArrowUpCircle, tone: 'text-amber-700 dark:text-amber-400' },
  scrap: { label: 'Scrap', icon: Trash2, tone: 'text-red-700 dark:text-red-400' },
  opname_adjust: { label: 'Opname', icon: History, tone: 'text-sky-600 dark:text-sky-400' },
  adjust: { label: 'Penyesuaian', icon: History, tone: 'text-sky-600 dark:text-sky-400' },
};

const SOURCE_LABEL = { receive: 'Rata-rata bergerak', manual: 'Koreksi manual' };

export default function AccessoryValuationLedger({ token, refreshKey = 0 }) {
  const [view, setView] = useState('movements');
  const [movements, setMovements] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const [mv, ch] = await Promise.all([
        api('GET', '/api/acc/valuation/movements?limit=200', token).catch(() => []),
        api('GET', '/api/acc/valuation/cost-history?limit=200', token).catch(() => []),
      ]);
      setMovements(Array.isArray(mv) ? mv : []);
      setHistory(Array.isArray(ch) ? ch : []);
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const mvPg = useClientPagination(movements, 10);
  const chPg = useClientPagination(history, 10);

  return (
    <div className="space-y-3" data-testid="acc-valuation-ledger">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1 border border-border rounded-lg p-1 bg-[var(--card-surface)]">
          {[
            { k: 'movements', label: 'Mutasi Bernilai', count: movements.length },
            { k: 'history', label: 'Riwayat HPP', count: history.length },
          ].map((t) => (
            <button key={t.k} onClick={() => setView(t.k)}
              data-testid={`acc-val-view-${t.k}`}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${view === t.k
                ? 'bg-primary text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
              {t.label} ({t.count})
            </button>
          ))}
        </div>
        <button onClick={load} className="flex items-center gap-2 px-3 py-1.5 border border-border rounded-lg text-xs hover:bg-foreground/5"
          data-testid="acc-val-ledger-refresh">
          <RefreshCw className="w-3.5 h-3.5" /> Muat ulang
        </button>
      </div>

      {err && <div className="text-sm text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10 rounded-lg px-4 py-2">{err}</div>}

      {loading ? (
        <div className="space-y-2">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-10 rounded-lg" />)}</div>
      ) : view === 'movements' ? (
        <div className="bg-[var(--card-surface)] rounded-xl border border-border overflow-x-auto">
          <table className="w-full text-sm min-w-[860px]">
            <thead className="bg-[var(--glass-bg)] border-b border-border">
              <tr>
                <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Waktu</th>
                <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Aksesoris</th>
                <th className="text-center px-4 py-2.5 text-muted-foreground font-medium">Jenis</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">Qty</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">HPP</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">Nilai</th>
                <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Jurnal</th>
              </tr>
            </thead>
            <tbody>
              {movements.length === 0 ? (
                <tr><td colSpan="7">
                  <EmptyState icon={Receipt} title="Belum ada mutasi bernilai"
                    description="Mutasi akan muncul setelah ada penerimaan, pengeluaran, atau scrap aksesoris." />
                </td></tr>
              ) : mvPg.paged.map((m) => {
                const meta = MV_META[m.movement_type] || { label: m.movement_type, icon: History, tone: 'text-muted-foreground' };
                const Icon = meta.icon;
                return (
                  <tr key={m.id} className="border-b border-border hover:bg-foreground/[0.02]" data-testid={`acc-val-mv-${m.id}`}>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{fmtDate(m.created_at)}</td>
                    <td className="px-4 py-2.5">
                      <div className="font-medium">{m.material_name}</div>
                      <div className="text-xs text-muted-foreground font-mono">{m.material_code}</div>
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      <span className={`inline-flex items-center gap-1 text-xs font-medium ${meta.tone}`}>
                        <Icon className="w-3.5 h-3.5" /> {meta.label}
                      </span>
                      {m.adjustment_reason && <div className="text-[10px] text-muted-foreground">{m.adjustment_reason}</div>}
                    </td>
                    <td className={`px-4 py-2.5 text-right font-medium ${m.qty_signed < 0 ? 'text-amber-700 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                      {m.qty_signed > 0 ? '+' : ''}{fmtNum(m.qty_signed)} <span className="text-xs text-muted-foreground">{m.unit}</span>
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs">
                      {m.unit_cost > 0 ? fmtRp(m.unit_cost)
                        : <span className="text-amber-700 dark:text-amber-400">belum dinilai</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs">{m.value > 0 ? fmtRp(m.value) : '-'}</td>
                    <td className="px-4 py-2.5 text-xs">
                      {m.je_number ? (
                        <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-mono">{m.je_number}</span>
                      ) : (
                        <span className="text-muted-foreground" title={m.post_error || 'Tidak ada jurnal untuk mutasi ini'}>
                          {m.post_error ? '⚠ gagal' : '—'}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <PaginationLite page={mvPg.page} totalPages={mvPg.totalPages} total={mvPg.total}
            pageSize={mvPg.pageSize} onPageChange={mvPg.setPage} />
        </div>
      ) : (
        <div className="bg-[var(--card-surface)] rounded-xl border border-border overflow-x-auto">
          <table className="w-full text-sm min-w-[760px]">
            <thead className="bg-[var(--glass-bg)] border-b border-border">
              <tr>
                <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Waktu</th>
                <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Metode</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">Stok sebelum</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">Qty masuk</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">HPP lama</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">HPP baru</th>
                <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">Oleh</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr><td colSpan="7">
                  <EmptyState icon={History} title="Belum ada perubahan HPP"
                    description="Riwayat terisi saat penerimaan membawa harga beli atau HPP dikoreksi manual." />
                </td></tr>
              ) : chPg.paged.map((h) => (
                <tr key={h.id} className="border-b border-border hover:bg-foreground/[0.02]" data-testid={`acc-cost-hist-${h.id}`}>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">{fmtDate(h.created_at)}</td>
                  <td className="px-4 py-2.5 text-xs">{SOURCE_LABEL[h.source] || h.method || h.source}</td>
                  <td className="px-4 py-2.5 text-right text-xs">{fmtNum(h.qty_before)}</td>
                  <td className="px-4 py-2.5 text-right text-xs">{h.qty_in ? fmtNum(h.qty_in) : '-'}</td>
                  <td className="px-4 py-2.5 text-right text-xs text-muted-foreground">{fmtRp(h.old_unit_cost)}</td>
                  <td className="px-4 py-2.5 text-right text-xs font-medium">{fmtRp(h.new_unit_cost)}</td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">{h.actor?.name || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <PaginationLite page={chPg.page} totalPages={chPg.totalPages} total={chPg.total}
            pageSize={chPg.pageSize} onPageChange={chPg.setPage} />
        </div>
      )}
    </div>
  );
}
