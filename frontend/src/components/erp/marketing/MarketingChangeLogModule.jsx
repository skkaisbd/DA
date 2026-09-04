/**
 * MarketingChangeLogModule — LAYAR "SIAPA MENGUBAH APA" (F6.5).
 *
 * KENAPA LAYAR INI ADA
 * --------------------
 * `marketing_change_log` sudah menyimpan setiap perubahan angka & kewenangan
 * marketing sejak F5 — tetapi sebelum layar ini, jejak itu hanya bisa dibaca dari
 * dua sudut sempit: panel kecil di dialog Siklus (satu toko × satu bulan, 20 baris)
 * dan tab Riwayat di layar Assign (hanya pemegang toko). Pertanyaan yang paling
 * sering muncul di rapat — *"siapa mengubah angka bulan lalu, kapan, dari berapa
 * ke berapa, dan kenapa?"* — tetap tidak bisa dijawab untuk SEMUA toko sekaligus.
 * Jejak yang ada tetapi tidak bisa dicari sama saja dengan tidak ada.
 *
 * YANG WAJIB TETAP TERLIHAT (jangan dihapus saat merapikan tampilan):
 *  · nilai LAMA → BARU per field (bukan dua blob JSON yang harus dibandingkan mata);
 *  · nama & PERAN pelaku + waktu + ALASAN — tanpa alasan, "kenapa akses toko saya
 *    dicabut?" tetap tak terjawab walau riwayatnya lengkap;
 *  · pembeda **kewenangan** vs **angka** (dua pertanyaan yang berbeda);
 *  · catatan kejujuran data: staf berlingkup hanya melihat tokonya, dan itu
 *    DIKATAKAN — bukan dibiarkan tampak seperti "tidak ada perubahan".
 *
 * Semua penyaringan & paginasi dilakukan BACKEND (`/api/marketing/change-log`)
 * supaya jumlah "total" di layar tidak pernah berarti "20 baris pertama".
 */
import { useState, useEffect, useCallback } from 'react';
import {
  History, RefreshCw, Loader2, Search, Download, ShieldCheck, Sigma,
  Info, Users, Store, Filter, X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { GlassCard } from '@/components/ui/glass';
import { Badge } from '@/components/ui/badge';
import PaginationLite from '@/components/ui/pagination-lite';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';
import { downloadCsv } from '@/lib/csv';
import { MarketingAccountSelect } from './pickers/MarketingPickers';
import NoStoreScopeNotice from './NoStoreScopeNotice';

const API = process.env.REACT_APP_BACKEND_URL;
const fmtNum = (n) => new Intl.NumberFormat('id-ID').format(Math.round(n || 0));

const KIND_STYLE = {
  kewenangan: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30',
  angka: 'bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/30',
};

/* Nilai bisa berupa angka uang, daftar nama, boolean, atau kosong. Menampilkan
   "null" apa adanya membuat pembacanya menebak; "belum ada" menjawabnya. */
function Val({ v, money }) {
  if (v === null || v === undefined || v === '') {
    return <span className="text-muted-foreground italic">belum ada</span>;
  }
  if (Array.isArray(v)) {
    return v.length
      ? <span>{v.join(', ')}</span>
      : <span className="text-muted-foreground italic">kosong</span>;
  }
  if (typeof v === 'boolean') return <span>{v ? 'ya' : 'tidak'}</span>;
  if (money && typeof v === 'number') return <span>{formatRupiah(v)}</span>;
  if (typeof v === 'number') return <span>{fmtNum(v)}</span>;
  return <span>{String(v)}</span>;
}

export default function MarketingChangeLogModule({ token, scope = 'marketing' }) {
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, page_size: 20, total_pages: 1 });
  const [filters, setFilters] = useState({ entities: [], actions: [], actors: [] });
  const [notes, setNotes] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  // filter state
  const [accountId, setAccountId] = useState('');
  const [entity, setEntity] = useState('');
  const [action, setAction] = useState('');
  const [actorId, setActorId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [q, setQ] = useState('');
  const [onlyPerm, setOnlyPerm] = useState(false);
  const [page, setPage] = useState(1);

  const params = useCallback((extra = {}) => {
    const p = new URLSearchParams({ page: String(page), page_size: '20', ...extra });
    if (accountId) p.set('account_id', accountId);
    if (entity) p.set('entity', entity);
    if (action) p.set('action', action);
    if (actorId) p.set('actor_id', actorId);
    if (dateFrom) p.set('date_from', dateFrom);
    if (dateTo) p.set('date_to', dateTo);
    if (q.trim()) p.set('q', q.trim());
    if (onlyPerm) p.set('only_permissions', 'true');
    return p;
  }, [page, accountId, entity, action, actorId, dateFrom, dateTo, q, onlyPerm]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/marketing/change-log?${params()}`,
        { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      setRows(j.rows || []);
      setMeta({ total: j.total || 0, page: j.page || 1, page_size: j.page_size || 20,
        total_pages: j.total_pages || 1 });
      setFilters(j.filters || { entities: [], actions: [], actors: [] });
      setNotes(j.data_notes || []);
    } catch (e) {
      toast.error(`Gagal memuat jejak perubahan: ${e.message}`);
      setRows([]);
    } finally { setLoading(false); }
  }, [params, token]);

  const loadStats = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/marketing/change-log/stats?days=30`,
        { headers: { Authorization: `Bearer ${token}` } });
      setStats(res.ok ? await res.json() : null);
    } catch { setStats(null); }
  }, [token]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadStats(); }, [loadStats]);
  // Ganti filter ⇒ balik ke halaman 1 (kalau tidak, "tidak ada data" bisa muncul
  // hanya karena halaman 3 dari hasil baru tidak ada).
  useEffect(() => { setPage(1); },
    [accountId, entity, action, actorId, dateFrom, dateTo, q, onlyPerm]);

  const resetFilters = () => {
    setAccountId(''); setEntity(''); setAction(''); setActorId('');
    setDateFrom(''); setDateTo(''); setQ(''); setOnlyPerm(false); setPage(1);
  };
  const hasFilter = Boolean(accountId || entity || action || actorId || dateFrom
    || dateTo || q.trim() || onlyPerm);

  /* Unduh CSV — bahan audit. Mengambil ulang dengan page_size besar supaya
     berkasnya memuat SELURUH hasil filter, bukan hanya halaman yang terlihat.
     Batasnya disebut apa adanya di toast (bukan dipotong diam-diam). */
  const exportCsv = async () => {
    try {
      const res = await fetch(`${API}/api/marketing/change-log?${params({ page: '1', page_size: '500' })}`,
        { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      const head = ['Waktu', 'Toko', 'Kode toko', 'Jenis', 'Yang diubah', 'Aksi',
        'Periode', 'Pelaku', 'Peran', 'Alasan', 'Field', 'Nilai lama', 'Nilai baru'];
      const lines = [];
      (j.rows || []).forEach((r) => {
        const base = [r.at, r.account_name, r.account_code, r.kind, r.entity_label,
          r.action_label, r.period, r.actor_name, r.actor_role, r.reason];
        if (!r.changes?.length) lines.push([...base, '', '', '']);
        r.changes?.forEach((c) => lines.push([...base, c.field_label,
          Array.isArray(c.before) ? c.before.join('|') : c.before,
          Array.isArray(c.after) ? c.after.join('|') : c.after]));
      });
      downloadCsv('jejak-perubahan-marketing', head, lines);
      toast.success(`CSV terunduh — ${j.rows?.length || 0} perubahan`
        + (j.total > (j.rows?.length || 0) ? ` dari ${j.total} (batas 500 baris per unduhan)` : ''));
    } catch (e) {
      toast.error(`Gagal mengunduh CSV: ${e.message}`);
    }
  };

  return (
    <div className="space-y-4" data-testid="marketing-changelog">
      {/* ── Judul ────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2 text-foreground">
            <History size={18} className="text-primary" /> Jejak Perubahan Marketing
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Siapa mengubah apa — target, rencana anggaran, kunci periode, dan
            kewenangan toko. Hanya bisa dibaca{scope === 'management' ? ' (Portal Manajemen)' : ''}.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" className="h-9" onClick={exportCsv}
            disabled={!rows.length} data-testid="changelog-export-csv">
            <Download size={13} className="mr-1.5" /> CSV
          </Button>
          <Button size="sm" variant="outline" className="h-9" onClick={() => { load(); loadStats(); }}
            disabled={loading} data-testid="changelog-refresh">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </Button>
        </div>
      </div>

      <NoStoreScopeNotice token={token} what="Jejak & angka di layar ini" />

      {/* ── Kartu ringkas 30 hari ────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3" data-testid="changelog-stats">
        <GlassCard className="p-3">
          <p className="text-[11px] text-muted-foreground">Perubahan 30 hari</p>
          <p className="text-base font-bold">{fmtNum(stats?.total)}</p>
          <p className="text-[10px] text-muted-foreground">total baris jejak</p>
        </GlassCard>
        <GlassCard className="p-3">
          <p className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Sigma size={11} /> Perubahan angka
          </p>
          <p className="text-base font-bold">{fmtNum(stats?.number_changes)}</p>
          <p className="text-[10px] text-muted-foreground">target · anggaran · kunci periode</p>
        </GlassCard>
        <GlassCard className="p-3">
          <p className="text-[11px] text-muted-foreground flex items-center gap-1">
            <ShieldCheck size={11} /> Perubahan kewenangan
          </p>
          <p className="text-base font-bold">{fmtNum(stats?.permission_changes)}</p>
          <p className="text-[10px] text-muted-foreground">siapa pemegang toko</p>
        </GlassCard>
        <GlassCard className="p-3">
          <p className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Users size={11} /> Pelaku
          </p>
          <p className="text-base font-bold">{fmtNum(stats?.actors)}</p>
          <p className="text-[10px] text-muted-foreground">orang yang mengubah</p>
        </GlassCard>
        <GlassCard className="p-3">
          <p className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Store size={11} /> Toko tersentuh
          </p>
          <p className="text-base font-bold">{fmtNum(stats?.accounts_touched)}</p>
          <p className="text-[10px] text-muted-foreground">
            {fmtNum(stats?.without_reason)} tanpa alasan
          </p>
        </GlassCard>
      </div>

      {/* ── Penyaring ────────────────────────────────────────────────────── */}
      <div className="rounded-lg border border-border bg-background p-3 space-y-3"
        data-testid="changelog-filters">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="md:col-span-1">
            <MarketingAccountSelect token={token} value={accountId}
              onChange={setAccountId} required={false} includeAll allLabel="Semua toko"
              label="Toko" testId="changelog-account-select" />
          </div>
          <div>
            <Label className="text-xs">Yang diubah</Label>
            <select className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-xs"
              value={entity} onChange={(e) => setEntity(e.target.value)}
              data-testid="changelog-entity-select">
              <option value="">Semua jenis</option>
              {filters.entities.map((e) => (
                <option key={e.value} value={e.value}>{e.label}</option>
              ))}
            </select>
          </div>
          <div>
            <Label className="text-xs">Aksi</Label>
            <select className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-xs"
              value={action} onChange={(e) => setAction(e.target.value)}
              data-testid="changelog-action-select">
              <option value="">Semua aksi</option>
              {filters.actions.map((a) => (
                <option key={a.value} value={a.value}>{a.label}</option>
              ))}
            </select>
          </div>
          <div>
            <Label className="text-xs">Pelaku</Label>
            <select className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-xs"
              value={actorId} onChange={(e) => setActorId(e.target.value)}
              data-testid="changelog-actor-select">
              <option value="">Semua orang</option>
              {filters.actors.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}{a.role ? ` (${a.role})` : ''} — {a.count}×
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label className="text-xs">Dari tanggal</Label>
            <Input type="date" className="mt-1 h-9" value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              data-testid="changelog-date-from" />
          </div>
          <div>
            <Label className="text-xs">Sampai tanggal</Label>
            <Input type="date" className="mt-1 h-9" value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              data-testid="changelog-date-to" />
          </div>
          <div className="xl:col-span-2">
            <Label className="text-xs">Cari (alasan · pelaku · jenis)</Label>
            <div className="relative mt-1">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input className="h-9 pl-8" placeholder="mis. rotasi shift"
                value={q} onChange={(e) => setQ(e.target.value)}
                data-testid="changelog-search" />
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs cursor-pointer">
            <input type="checkbox" checked={onlyPerm}
              onChange={(e) => setOnlyPerm(e.target.checked)}
              data-testid="changelog-only-permissions" />
            Hanya perubahan <b>kewenangan</b> (siapa pemegang toko)
          </label>
          {hasFilter && (
            <Button size="sm" variant="ghost" className="h-7 text-[11px]"
              onClick={resetFilters} data-testid="changelog-reset">
              <X size={11} className="mr-1" /> Bersihkan filter
            </Button>
          )}
          <span className="text-[11px] text-muted-foreground ml-auto flex items-center gap-1">
            <Filter size={11} /> {fmtNum(meta.total)} perubahan cocok
          </span>
        </div>
      </div>

      {/* ── Tabel ────────────────────────────────────────────────────────── */}
      {loading ? (
        <div className="py-10 text-center text-muted-foreground text-sm">
          <Loader2 className="mx-auto animate-spin mb-2" size={18} /> Membaca jejak perubahan…
        </div>
      ) : !rows.length ? (
        <div className="py-10 text-center text-muted-foreground text-sm" data-testid="changelog-empty">
          {hasFilter
            ? 'Tidak ada perubahan yang cocok dengan filter ini — longgarkan filternya.'
            : 'Belum ada perubahan tercatat. Jejak lahir saat target, anggaran, kunci periode, atau pemegang toko diubah.'}
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-x-auto bg-background">
          <table className="w-full text-xs" data-testid="changelog-table">
            <thead className="bg-muted/60">
              <tr>
                {['Waktu', 'Toko', 'Jenis', 'Yang diubah', 'Nilai lama → baru',
                  'Pelaku', 'Alasan'].map((h) => (
                    <th key={h} className="px-2.5 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                  ))}
              </tr>
            </thead>
            <tbody className="divide-y [&_td]:align-top">
              {rows.map((r) => (
                <tr key={r.id} className="hover:bg-muted/30" data-testid={`changelog-row-${r.id}`}>
                  <td className="px-2.5 py-2 whitespace-nowrap">
                    {String(r.at || '').slice(0, 10)}
                    <div className="text-[10px] text-muted-foreground">
                      {String(r.at || '').slice(11, 16)} · {r.period || 'tanpa periode'}
                    </div>
                  </td>
                  <td className="px-2.5 py-2">
                    <div className="font-semibold text-foreground">{r.account_name}</div>
                    {r.account_code ? (
                      <div className="text-[10px] text-muted-foreground">{r.account_code}</div>
                    ) : null}
                  </td>
                  <td className="px-2.5 py-2">
                    <Badge variant="outline" className={`text-[9px] ${KIND_STYLE[r.kind] || ''}`}>
                      {r.kind}
                    </Badge>
                  </td>
                  <td className="px-2.5 py-2">
                    <div className="font-medium">{r.action_label}</div>
                    <div className="text-[10px] text-muted-foreground">{r.entity_label}</div>
                  </td>
                  <td className="px-2.5 py-2 min-w-[260px]">
                    {r.changes?.length ? (
                      <ul className="space-y-0.5">
                        {r.changes.map((c, i) => (
                          <li key={i} className="text-[11px]">
                            <span className="text-muted-foreground">{c.field_label}: </span>
                            <Val v={c.before} money={c.is_money} />
                            <span className="text-muted-foreground"> → </span>
                            <b><Val v={c.after} money={c.is_money} /></b>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <span className="text-muted-foreground italic text-[11px]">
                        tidak ada nilai yang berubah
                      </span>
                    )}
                  </td>
                  <td className="px-2.5 py-2 whitespace-nowrap">
                    {r.actor_name}
                    {r.actor_role ? (
                      <div className="text-[10px] text-muted-foreground">{r.actor_role}</div>
                    ) : null}
                  </td>
                  <td className="px-2.5 py-2 max-w-[240px]">
                    {r.reason
                      ? <span>{r.reason}</span>
                      : <span className="text-muted-foreground italic">tidak diisi</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-2 py-1">
            <PaginationLite page={meta.page} totalPages={meta.total_pages}
              total={meta.total} pageSize={meta.page_size} onPageChange={setPage} />
          </div>
        </div>
      )}

      {/* ── Catatan kejujuran data ───────────────────────────────────────── */}
      {notes.length > 0 && (
        <div className="rounded-lg border border-border bg-muted/40 p-3" data-testid="changelog-notes">
          <p className="text-xs font-semibold mb-1 flex items-center gap-1 text-foreground">
            <Info size={12} /> Catatan kejujuran data
          </p>
          <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-muted-foreground">
            {notes.map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
