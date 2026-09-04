/**
 * AccountAssignView — **ASSIGN TOKO (SPV)**: siapa memegang toko yang mana (F6.4 · F8).
 *
 * Kenapa layar ini ada: F6 sudah membatasi visibilitas per toko, tetapi kolom
 * `assigned_staff` sebelumnya HANYA bisa diubah lewat skrip seed. Artinya aturan
 * yang benar di kode tidak bisa dipakai di lapangan: staf baru tidak pernah bisa
 * diberi toko, dan staf yang pindah tugas tidak pernah bisa dicabut aksesnya.
 *
 * DILENGKAPI 2026-08-14 (F8) — tiga hal yang membuat layar ini bisa DIPAKAI, bukan
 * hanya ada:
 *
 *  1. **Tiga sudut pandang.** “Per Toko” menjawab *siapa pegang toko ini*;
 *     **“Per Staf”** menjawab *Rina pegang toko apa saja* (pertanyaan yang benar-benar
 *     diajukan saat rotasi shift) dan MENAMPILKAN staf yang memegang 0 toko — orang
 *     yang membuka aplikasi lalu melihat layar kosong tanpa penjelasan;
 *     **“Riwayat”** menjawab *apa yang berubah minggu ini* tanpa membuka 9 dialog.
 *  2. **Alasan WAJIB.** Tombol Simpan terkunci sampai alasan diisi. Alasan itulah
 *     satu-satunya yang menjawab “kenapa akses toko saya dicabut?” enam bulan lagi.
 *  3. **Akibat yang MENETAP di layar** (bukan toast 5 detik): staf yang dicabut
 *     langsung kehilangan akses, staf berakun NONAKTIF tidak bisa login sehingga
 *     tokonya praktis tidak dipegang siapa pun.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  RefreshCw, Loader2, Users, History, Store, Save, ShieldCheck, Info, UserPlus,
  Search, AlertTriangle, UserX, CheckCircle2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;
const ROLE_LABEL = {
  staff_marketing: 'Staf Marketing', pic_toko: 'PIC Toko',
  host_live: 'Host Live', cs_staff: 'CS',
};
const MIN_REASON = 4;      // sama dengan penjaga backend (MIN_REASON)
const TABS = [['toko', 'Per Toko'], ['staf', 'Per Staf'], ['riwayat', 'Riwayat']];

const fmtWhen = (v) => {
  if (!v) return '—';
  try {
    return new Date(v).toLocaleString('id-ID', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch { return String(v); }
};

export default function AccountAssignView({ token }) {
  const [tab, setTab] = useState('toko');
  const [rows, setRows] = useState([]);
  const [options, setOptions] = useState([]);
  const [canEdit, setCanEdit] = useState(false);
  const [notes, setNotes] = useState([]);
  const [summary, setSummary] = useState({ unassigned: 0, stale: 0 });
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [onlyUnassigned, setOnlyUnassigned] = useState(false);

  const [editTarget, setEditTarget] = useState(null);     // toko yang sedang diubah
  const [picked, setPicked] = useState([]);
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [lastEffect, setLastEffect] = useState(null);     // {message, warnings[], note}

  const [historyFor, setHistoryFor] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const [staffRows, setStaffRows] = useState([]);
  const [staffMeta, setStaffMeta] = useState({ without_account: [], ghost: [] });
  const [allHistory, setAllHistory] = useState([]);
  const [allHistoryPage, setAllHistoryPage] = useState(1);
  const [allHistoryTotal, setAllHistoryTotal] = useState(0);

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, op] = await Promise.all([
        fetch(`${API}/api/marketing/account-assign/overview`, { headers }),
        fetch(`${API}/api/marketing/account-assign/staff-options`, { headers }),
      ]);
      if (!ov.ok) throw new Error(`HTTP ${ov.status}`);
      const ovj = await ov.json();
      setRows(ovj.rows || []);
      setNotes(ovj.data_notes || []);
      setCanEdit(Boolean(ovj.can_edit));
      setSummary({ unassigned: ovj.unassigned_count || 0, stale: ovj.stale_count || 0 });
      if (op.ok) setOptions(((await op.json())?.options) || []);
    } catch (e) {
      toast.error(`Gagal memuat daftar pemegang toko: ${e.message}`);
      setRows([]);
    } finally { setLoading(false); }
  }, [headers]);

  const loadStaff = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/marketing/account-assign/by-staff`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setStaffRows(j.rows || []);
      setStaffMeta({ without_account: j.without_account || [],
        ghost: j.ghost_staff_ids || [] });
    } catch (e) { toast.error(`Gagal memuat daftar per staf: ${e.message}`); }
  }, [headers]);

  const loadAllHistory = useCallback(async (page = 1) => {
    try {
      const r = await fetch(
        `${API}/api/marketing/account-assign/history?page=${page}&page_size=10`,
        { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setAllHistory(j.rows || []);
      setAllHistoryTotal(j.pagination?.total || 0);
      setAllHistoryPage(j.pagination?.page || page);
    } catch (e) { toast.error(`Gagal memuat riwayat: ${e.message}`); }
  }, [headers]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === 'staf') loadStaff(); }, [tab, loadStaff]);
  useEffect(() => { if (tab === 'riwayat') loadAllHistory(1); }, [tab, loadAllHistory]);

  const openEdit = (acc) => {
    setEditTarget(acc);
    setPicked((acc.assigned_staff || []).map((s) => s.id));
    setReason('');
  };

  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const reasonOk = reason.trim().length >= MIN_REASON;

  const save = async () => {
    if (!editTarget || !reasonOk) return;
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/marketing/account-assign/${editTarget.id}`, {
        method: 'POST', headers,
        body: JSON.stringify({ staff_ids: picked, reason: reason.trim() }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(j?.detail || `HTTP ${res.status}`);
      // Akibat perubahan DITAHAN di layar. Peringatan seperti "akun staf ini
      // NONAKTIF" atau "toko ini sekarang tidak dipegang siapa pun" adalah
      // pekerjaan lanjutan — mustahil dikerjakan dari toast yang hilang 5 detik.
      setLastEffect({
        account: editTarget.account_name,
        message: j.message || 'Pemegang toko diperbarui',
        warnings: j.warnings || [],
        note: j.effect_note || '',
        reason: j.reason || reason.trim(),
      });
      toast.success(j.message || 'Pemegang toko diperbarui');
      setEditTarget(null);
      load();
      if (tab === 'staf') loadStaff();
      if (tab === 'riwayat') loadAllHistory(1);
    } catch (e) {
      toast.error(`Gagal menyimpan: ${e.message}`);
    } finally { setSaving(false); }
  };

  const openHistory = async (acc) => {
    setHistoryFor(acc);
    setHistoryLoading(true);
    try {
      const res = await fetch(`${API}/api/marketing/account-assign/${acc.id}/history`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setHistory(((await res.json())?.rows) || []);
    } catch (e) {
      toast.error(`Gagal memuat riwayat: ${e.message}`);
      setHistory([]);
    } finally { setHistoryLoading(false); }
  };

  /* ── daftar toko yang tampil: pencarian + filter + paginasi 10/hal ── */
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((r) => {
      if (onlyUnassigned && (r.active_count ?? r.assigned_count) > 0) return false;
      if (!q) return true;
      const hay = `${r.account_name} ${r.account_code} ${r.platform} `
        + `${(r.assigned_staff || []).map((s) => s.name).join(' ')} ${r.pic?.name || ''}`;
      return hay.toLowerCase().includes(q);
    });
  }, [rows, query, onlyUnassigned]);

  const pg = useClientPagination(filtered, 10);
  const pgStaff = useClientPagination(staffRows, 10);

  return (
    <div className="space-y-4" data-testid="account-assign-view">
      <div className="flex flex-wrap items-center gap-2">
        <div>
          <h3 className="text-sm font-bold flex items-center gap-1.5 text-foreground">
            <ShieldCheck size={14} className="text-primary" /> Pemegang Toko
          </h3>
          <p className="text-[11px] text-muted-foreground">
            Staf hanya melihat data toko yang di-assign kepadanya. Perubahan tercatat lengkap
            dengan pelaku &amp; alasannya.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {!canEdit && (
            <Badge variant="outline" className="text-[9px]" data-testid="assign-readonly-badge">
              Hanya lihat (butuh SPV/Manager)
            </Badge>
          )}
          <Button size="sm" variant="outline" className="h-8" onClick={load} disabled={loading}
            data-testid="assign-refresh">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </Button>
        </div>
      </div>

      {/* tiga sudut pandang */}
      <div className="flex flex-wrap gap-1.5" data-testid="assign-tabs">
        {TABS.map(([v, l]) => (
          <button key={v} type="button" onClick={() => setTab(v)}
            data-testid={`assign-tab-${v}`}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold border ${tab === v
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-background text-foreground border-border hover:bg-muted/50'}`}>
            {l}
          </button>
        ))}
      </div>

      {/* akibat perubahan terakhir — MENETAP */}
      {lastEffect && (
        <div className="rounded-lg border border-border bg-muted/40 p-3 space-y-1"
          data-testid="assign-effect">
          <p className="text-xs font-semibold flex items-center gap-1.5 text-foreground">
            <CheckCircle2 size={12} className="text-emerald-600 dark:text-emerald-400" />
            {lastEffect.account}: {lastEffect.message}
          </p>
          {lastEffect.reason ? (
            <p className="text-[11px] text-muted-foreground">Alasan tercatat: “{lastEffect.reason}”</p>
          ) : null}
          {lastEffect.note ? (
            <p className="text-[11px] text-muted-foreground">{lastEffect.note}</p>
          ) : null}
          {(lastEffect.warnings || []).map((w, i) => (
            <p key={i} className="text-[11px] text-amber-700 dark:text-amber-400 flex items-start gap-1"
              data-testid={`assign-effect-warning-${i}`}>
              <AlertTriangle size={11} className="mt-0.5 shrink-0" /> {w}
            </p>
          ))}
          <Button size="sm" variant="ghost" className="h-6 text-[11px] px-2"
            onClick={() => setLastEffect(null)} data-testid="assign-effect-close">Tutup</Button>
        </div>
      )}

      {(summary.unassigned > 0 || summary.stale > 0) && !loading && tab === 'toko' && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3"
          data-testid="assign-warning">
          <p className="text-xs font-semibold text-amber-700 dark:text-amber-400">
            {summary.unassigned} toko belum punya staf pemegang
            {summary.stale > 0 && ` · ${summary.stale} toko pemegangnya berakun NONAKTIF`}
          </p>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Toko tanpa staf tetap terlihat oleh SPV/Manager, tetapi tidak ada staf yang bisa
            mengisi data hariannya. Toko yang pemegangnya nonaktif TAMPAK sudah dipegang —
            padahal tidak ada yang bisa login.
          </p>
        </div>
      )}

      {/* ════════════════ PER TOKO ════════════════ */}
      {tab === 'toko' && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[220px]">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder="Cari toko, kode, platform, atau nama staf…"
                data-testid="assign-search"
                className="w-full h-9 pl-8 pr-3 rounded-md border border-border bg-background
                  text-foreground text-xs placeholder:text-muted-foreground focus:outline-none
                  focus:ring-2 focus:ring-primary" />
            </div>
            <button type="button" onClick={() => setOnlyUnassigned((v) => !v)}
              data-testid="assign-filter-unassigned"
              className={`h-9 px-3 rounded-md border text-xs font-semibold ${onlyUnassigned
                ? 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/40'
                : 'bg-background text-foreground border-border hover:bg-muted/50'}`}>
              Hanya yang belum terpegang
            </button>
            <span className="text-[11px] text-muted-foreground" data-testid="assign-count">
              {filtered.length} dari {rows.length} toko
            </span>
          </div>

          {loading ? (
            <div className="py-10 text-center text-muted-foreground text-sm">
              <Loader2 className="mx-auto animate-spin mb-2" size={18} /> Memuat pemegang toko…
            </div>
          ) : !filtered.length ? (
            <div className="py-10 text-center text-muted-foreground text-sm" data-testid="assign-empty">
              {rows.length === 0 ? 'Tidak ada toko yang bisa Anda kelola.'
                : 'Tidak ada toko yang cocok dengan pencarian/filter ini.'}
            </div>
          ) : (
            <div className="rounded-lg border border-border overflow-x-auto bg-background">
              <table className="w-full text-xs" data-testid="assign-table">
                <thead className="bg-muted/60">
                  <tr>
                    {['Toko', 'Platform', 'Status', 'PIC', 'Staf pemegang', 'Aksi'].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {pg.paged.map((r) => (
                    <tr key={r.id} className="hover:bg-muted/30" data-testid={`assign-row-${r.id}`}>
                      <td className="px-3 py-2">
                        <div className="font-semibold text-foreground flex items-center gap-1.5">
                          <Store size={12} className="text-muted-foreground" /> {r.account_name}
                        </div>
                        {r.account_code ? (
                          <div className="text-[10px] text-muted-foreground">{r.account_code}</div>
                        ) : null}
                      </td>
                      <td className="px-3 py-2 capitalize">{r.platform}</td>
                      <td className="px-3 py-2">
                        <Badge variant="outline"
                          className={`text-[9px] ${r.status === 'active'
                            ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30'
                            : 'bg-muted text-muted-foreground'}`}>
                          {r.status === 'active' ? 'Aktif' : r.status}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-muted-foreground whitespace-nowrap">
                        {r.pic?.name || '—'}
                      </td>
                      <td className="px-3 py-2">
                        {(r.assigned_staff || []).length === 0 ? (
                          <span className="text-muted-foreground">belum ada</span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {r.assigned_staff.map((s) => (
                              <Badge key={s.id} variant="outline"
                                className={`text-[9px] ${s.inactive
                                  ? 'bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30'
                                  : ''}`}
                                data-testid={`assign-staff-${r.id}-${s.id}`}>
                                {s.name}{s.role ? ` · ${ROLE_LABEL[s.role] || s.role}` : ''}
                                {s.inactive ? ' · NONAKTIF' : ''}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        <div className="flex gap-1.5">
                          <Button size="sm" variant="outline" className="h-7 text-[11px]"
                            disabled={!canEdit} onClick={() => openEdit(r)}
                            data-testid={`assign-edit-btn-${r.id}`}>
                            <UserPlus size={11} className="mr-1" /> Atur staf
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 text-[11px]"
                            onClick={() => openHistory(r)} data-testid={`assign-history-btn-${r.id}`}>
                            <History size={11} className="mr-1" /> Riwayat
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <PaginationLite page={pg.page} totalPages={pg.totalPages} total={pg.total}
                pageSize={pg.pageSize} onPageChange={pg.setPage} />
            </div>
          )}
        </>
      )}

      {/* ════════════════ PER STAF ════════════════ */}
      {tab === 'staf' && (
        <>
          {staffMeta.without_account.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3"
              data-testid="assign-staff-without-account">
              <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
                <UserX size={12} /> {staffMeta.without_account.length} staf belum memegang toko
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                {staffMeta.without_account.slice(0, 8).join(' · ')}
                {staffMeta.without_account.length > 8 ? ' …' : ''} — mereka membuka aplikasi
                dan melihat layar KOSONG sampai SPV meng-assign tokonya.
              </p>
            </div>
          )}
          {!staffRows.length ? (
            <div className="py-10 text-center text-muted-foreground text-sm" data-testid="assign-staff-empty">
              Belum ada pemakai berperan staf toko (Staf Marketing / PIC Toko / Host Live / CS).
            </div>
          ) : (
            <div className="rounded-lg border border-border overflow-x-auto bg-background">
              <table className="w-full text-xs" data-testid="assign-staff-table">
                <thead className="bg-muted/60">
                  <tr>
                    {['Staf', 'Peran', 'Akun', 'Jumlah toko', 'Toko yang dipegang'].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {pgStaff.paged.map((s) => (
                    <tr key={s.id} className="hover:bg-muted/30" data-testid={`assign-staff-row-${s.id}`}>
                      <td className="px-3 py-2">
                        <div className="font-semibold text-foreground">{s.name}</div>
                        <div className="text-[10px] text-muted-foreground">{s.email}</div>
                      </td>
                      <td className="px-3 py-2">{ROLE_LABEL[s.role] || s.role}</td>
                      <td className="px-3 py-2">
                        <Badge variant="outline" className={`text-[9px] ${s.inactive
                          ? 'bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30'
                          : 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30'}`}>
                          {s.inactive ? 'NONAKTIF' : 'Aktif'}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 font-semibold">{s.accounts_count}</td>
                      <td className="px-3 py-2">
                        {s.accounts_count === 0 ? (
                          <span className="text-amber-700 dark:text-amber-400">
                            belum memegang toko — tidak melihat data apa pun
                          </span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {s.accounts.map((a) => (
                              <Badge key={a.id} variant="outline" className="text-[9px]">
                                {a.account_name}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <PaginationLite page={pgStaff.page} totalPages={pgStaff.totalPages}
                total={pgStaff.total} pageSize={pgStaff.pageSize} onPageChange={pgStaff.setPage} />
            </div>
          )}
        </>
      )}

      {/* ════════════════ RIWAYAT (SEMUA TOKO) ════════════════ */}
      {tab === 'riwayat' && (
        <>
          {!allHistory.length ? (
            <div className="py-10 text-center text-muted-foreground text-sm"
              data-testid="assign-allhistory-empty">
              Belum ada perubahan pemegang toko yang tercatat.
            </div>
          ) : (
            <div className="rounded-lg border border-border overflow-x-auto bg-background">
              <table className="w-full text-xs" data-testid="assign-allhistory-table">
                <thead className="bg-muted/60">
                  <tr>
                    {['Waktu', 'Toko', 'Pelaku', 'Ditambah', 'Dicabut', 'Alasan'].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {allHistory.map((h) => (
                    <tr key={h.id} className="hover:bg-muted/30"
                      data-testid={`assign-allhistory-row-${h.id}`}>
                      <td className="px-3 py-2 whitespace-nowrap">{fmtWhen(h.at)}</td>
                      <td className="px-3 py-2 font-semibold text-foreground">{h.account_name}</td>
                      <td className="px-3 py-2">
                        {h.actor_name}
                        <span className="text-muted-foreground"> ({h.actor_role})</span>
                      </td>
                      <td className="px-3 py-2 text-emerald-700 dark:text-emerald-400">
                        {(h.added_names || []).join(', ') || '—'}
                      </td>
                      <td className="px-3 py-2 text-rose-700 dark:text-rose-400">
                        {(h.removed_names || []).join(', ') || '—'}
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{h.reason || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <PaginationLite page={allHistoryPage}
                totalPages={Math.max(1, Math.ceil(allHistoryTotal / 10))}
                total={allHistoryTotal} pageSize={10}
                onPageChange={(p) => loadAllHistory(p)} />
            </div>
          )}
        </>
      )}

      {notes.length > 0 && (
        <div className="rounded-lg border border-border bg-muted/40 p-3" data-testid="assign-notes">
          <p className="text-xs font-semibold mb-1 flex items-center gap-1 text-foreground">
            <Info size={12} /> Catatan
          </p>
          <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-muted-foreground">
            {notes.map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}

      {/* ── Dialog: atur staf ─────────────────────────────────────────────── */}
      <Dialog open={Boolean(editTarget)} onOpenChange={(o) => !o && setEditTarget(null)}>
        <DialogContent className="max-w-lg" data-testid="assign-dialog">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-1.5">
              <Users size={15} /> Staf pemegang {editTarget?.account_name}
            </DialogTitle>
            <DialogDescription className="text-[11px]">
              Centang staf yang bertanggung jawab atas toko ini. Staf yang tidak dicentang
              langsung kehilangan akses ke data toko ini.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
            {options.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                Belum ada pemakai berperan staf toko (Staf Marketing / PIC Toko / Host Live / CS).
                Buat dulu akunnya di Manajemen Pengguna.
              </p>
            ) : options.map((o) => {
              const off = String(o.status || 'active').toLowerCase() !== 'active';
              return (
                <label key={o.id}
                  className="flex items-start gap-2 rounded-md border border-border p-2 hover:bg-muted/40 cursor-pointer"
                  data-testid={`assign-option-${o.id}`}>
                  <Checkbox checked={picked.includes(o.id)} onCheckedChange={() => toggle(o.id)}
                    data-testid={`assign-checkbox-${o.id}`} />
                  <span className="text-xs">
                    <span className="font-semibold text-foreground">{o.name}</span>
                    <span className="text-muted-foreground"> · {ROLE_LABEL[o.role] || o.role}</span>
                    {off && (
                      <Badge variant="outline"
                        className="ml-1.5 text-[9px] bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30">
                        akun NONAKTIF
                      </Badge>
                    )}
                    <span className="block text-[10px] text-muted-foreground">
                      {o.email} · memegang {o.accounts_assigned} toko
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
          <div>
            <Label className="text-[11px]">
              Alasan perubahan <span className="text-red-500">*</span> (masuk riwayat)
            </Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="mis. rotasi shift Agustus / staf resign"
              className="h-9 mt-1 text-xs" data-testid="assign-reason-input" />
            <p className={`text-[10px] mt-1 ${reasonOk ? 'text-muted-foreground'
              : 'text-amber-700 dark:text-amber-400'}`} data-testid="assign-reason-hint">
              {reasonOk
                ? 'Alasan ini yang akan dibaca orang lain di Riwayat.'
                : `Wajib diisi (minimal ${MIN_REASON} huruf) — alasan inilah yang menjawab `
                  + '“kenapa akses toko saya dicabut?”.'}
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setEditTarget(null)}
              disabled={saving} data-testid="assign-cancel-btn">Batal</Button>
            <Button size="sm" onClick={save} disabled={saving || !reasonOk}
              data-testid="assign-save-btn">
              {saving ? <Loader2 size={13} className="mr-1.5 animate-spin" />
                : <Save size={13} className="mr-1.5" />}
              Simpan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Dialog: riwayat per toko ──────────────────────────────────────── */}
      <Dialog open={Boolean(historyFor)} onOpenChange={(o) => !o && setHistoryFor(null)}>
        <DialogContent className="max-w-2xl" data-testid="assign-history-dialog">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-1.5">
              <History size={15} /> Riwayat pemegang {historyFor?.account_name}
            </DialogTitle>
            <DialogDescription className="text-[11px]">
              Setiap perubahan menyimpan daftar LAMA &amp; BARU beserta pelakunya — supaya
              pertanyaan “siapa yang mencabut akses toko ini?” selalu bisa dijawab.
            </DialogDescription>
          </DialogHeader>
          {historyLoading ? (
            <div className="py-8 text-center text-muted-foreground text-sm">
              <Loader2 className="mx-auto animate-spin mb-2" size={18} /> Memuat riwayat…
            </div>
          ) : !history.length ? (
            <p className="text-xs text-muted-foreground py-6 text-center"
              data-testid="assign-history-empty">
              Belum ada perubahan pemegang toko ini.
            </p>
          ) : (
            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
              {history.map((h) => (
                <div key={h.id} className="rounded-md border border-border p-2.5 text-[11px]"
                  data-testid={`assign-history-row-${h.id}`}>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="text-[9px]">
                      {h.action === 'assign_staff' ? 'Perubahan' : 'Tanpa perubahan'}
                    </Badge>
                    <span className="text-muted-foreground">{fmtWhen(h.at)}</span>
                    <span className="font-semibold text-foreground">{h.actor_name}</span>
                    <span className="text-muted-foreground">({h.actor_role})</span>
                  </div>
                  <div className="mt-1 grid sm:grid-cols-2 gap-1">
                    <div><span className="text-muted-foreground">Sebelum: </span>
                      {(h.before_names || []).join(', ') || '—'}</div>
                    <div><span className="text-muted-foreground">Sesudah: </span>
                      {(h.after_names || []).join(', ') || '—'}</div>
                  </div>
                  {h.reason ? (
                    <div className="mt-1 text-muted-foreground">Alasan: {h.reason}</div>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
