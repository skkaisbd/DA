/**
 * AccountBulkReviewModule.jsx — KOREKSI MASSAL DATA TOKO (BD-5)
 *
 * Kenapa layar ini ada: 9 toko nyata dibuat dari bagan akun (COA) sehingga nama,
 * username, PIC, dan rekening pencairannya masih perlu dikoreksi owner. Mengedit
 * satu-satu lewat dialog = 9 kali buka-tutup. Layar ini menaruh semuanya dalam
 * SATU tabel yang bisa diisi langsung, lalu disimpan sekali.
 *
 * Aturan: tidak ada data yang dikarang. Kolom yang belum diisi tetap kosong dan
 * tandanya "perlu ditinjau" hanya hilang kalau owner sendiri yang mencentangnya.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ClipboardCheck, RefreshCw, Save, Loader2, UserCheck, Wallet, AlertTriangle,
  CheckCircle2, Store,
} from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput, GlassTable } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { PageHeader, StatTile, EmptyState } from '../moduleAtoms';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL || '';

export default function AccountBulkReviewModule({ token }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [users, setUsers] = useState([]);
  const [coa, setCoa] = useState({});
  const [draft, setDraft] = useState({});      // id → perubahan
  const [onlyReview, setOnlyReview] = useState(true);

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token],
  );

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [ra, ru, rc] = await Promise.all([
        fetch(`${API}/api/marketing/accounts`, { headers }),
        fetch(`${API}/api/auth/users?limit=200`, { headers }),
        fetch(`${API}/api/marketing/accounts/coa-options`, { headers }),
      ]);
      const accs = ra.ok ? await ra.json() : [];
      setAccounts(Array.isArray(accs) ? accs : []);
      if (ru.ok) {
        const u = await ru.json();
        setUsers(Array.isArray(u) ? u : (u.items || u.users || []));
      }
      if (rc.ok) setCoa(await rc.json());
      setDraft({});
    } catch (e) {
      toast.error('Gagal memuat data toko');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const coaName = useMemo(() => {
    const m = {};
    [...(coa.revenue || []), ...(coa.cash || []), ...(coa.receivable || [])]
      .forEach(o => { m[o.code] = o.name; });
    return m;
  }, [coa]);

  const rows = useMemo(() => (
    onlyReview ? accounts.filter(a => a.needs_owner_review) : accounts
  ), [accounts, onlyReview]);

  const val = (acc, field) => {
    const d = draft[acc.id] || {};
    return field in d ? d[field] : (acc[field] ?? '');
  };
  const setVal = (acc, field, value) => {
    setDraft(prev => ({ ...prev, [acc.id]: { ...(prev[acc.id] || {}), [field]: value } }));
  };
  const dirtyIds = Object.keys(draft).filter(id => Object.keys(draft[id] || {}).length > 0);

  const saveAll = async () => {
    if (!dirtyIds.length) {
      toast.info('Belum ada perubahan untuk disimpan');
      return;
    }
    setSaving(true);
    let okCount = 0;
    const failed = [];
    for (const id of dirtyIds) {
      const acc = accounts.find(a => a.id === id);
      const patch = { ...draft[id] };
      if (patch.pic_user_id === 'none') patch.pic_user_id = null;
      try {
        const res = await fetch(`${API}/api/marketing/accounts/${id}`, {
          method: 'PUT', headers, body: JSON.stringify(patch),
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.detail || 'gagal');
        okCount += 1;
      } catch (e) {
        failed.push(`${acc?.account_code || id}: ${e.message}`);
      }
    }
    setSaving(false);
    if (okCount) toast.success(`${okCount} toko tersimpan`);
    if (failed.length) toast.error(`Gagal: ${failed.join(' · ')}`, { duration: 8000 });
    fetchAll();
  };

  const markAllReviewed = () => {
    setDraft(prev => {
      const next = { ...prev };
      rows.forEach(a => {
        next[a.id] = { ...(next[a.id] || {}), needs_owner_review: false };
      });
      return next;
    });
    toast.info('Semua baris ditandai sudah ditinjau — tekan "Simpan Semua" untuk menyimpan');
  };

  const stats = useMemo(() => ({
    total: accounts.length,
    review: accounts.filter(a => a.needs_owner_review).length,
    noPic: accounts.filter(a => !a.pic_user_name).length,
    noUser: accounts.filter(a => !a.username).length,
  }), [accounts]);

  return (
    <div className="space-y-5" data-testid="account-bulk-review-module">
      <PageHeader
        icon={ClipboardCheck}
        eyebrow="Portal Marketing · Master Toko"
        title="Koreksi Data Toko (Massal)"
        subtitle="Isi nama final, username platform, PIC, dan rekening pencairan 9 toko dalam satu tabel — lalu tandai sudah ditinjau"
        actions={
          <div className="flex items-center gap-2">
            <Button onClick={fetchAll} variant="outline" size="sm" data-testid="bulk-refresh-btn">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Muat Ulang
            </Button>
            <Button onClick={markAllReviewed} variant="outline" size="sm" data-testid="bulk-mark-all-btn">
              <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" /> Tandai Semua Ditinjau
            </Button>
            <Button onClick={saveAll} size="sm" disabled={saving || !dirtyIds.length}
              data-testid="bulk-save-btn">
              {saving ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                : <Save className="w-3.5 h-3.5 mr-1.5" />}
              Simpan Semua{dirtyIds.length ? ` (${dirtyIds.length})` : ''}
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Total Toko" value={stats.total} testId="bulk-stat-total" />
        <StatTile label="Perlu Ditinjau" value={stats.review}
          accent={stats.review ? 'warning' : 'success'} testId="bulk-stat-review" />
        <StatTile label="Tanpa PIC" value={stats.noPic}
          accent={stats.noPic ? 'warning' : 'success'} testId="bulk-stat-nopic" />
        <StatTile label="Tanpa Username" value={stats.noUser}
          accent={stats.noUser ? 'warning' : 'success'} testId="bulk-stat-nouser" />
      </div>

      <GlassPanel className="p-4">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2 cursor-pointer">
            <Checkbox checked={onlyReview} onCheckedChange={v => setOnlyReview(!!v)}
              data-testid="bulk-filter-review" />
            <span>Tampilkan hanya toko yang <b>perlu ditinjau</b></span>
          </label>
          <span className="text-muted-foreground">
            Menampilkan <b className="text-foreground">{rows.length}</b> dari {accounts.length} toko
          </span>
          {dirtyIds.length > 0 && (
            <Badge variant="outline" className="bg-amber-500/10 text-amber-500 border-amber-500/30">
              <AlertTriangle size={11} className="mr-1" /> {dirtyIds.length} baris belum disimpan
            </Badge>
          )}
        </div>
      </GlassPanel>

      {loading ? (
        <div className="space-y-2">{[1, 2, 3, 4, 5].map(i => <Skeleton key={i} className="h-14" />)}</div>
      ) : rows.length === 0 ? (
        <GlassCard className="p-4">
          <EmptyState
            icon={Store}
            title={stats.review === 0 ? 'Semua toko sudah ditinjau' : 'Tidak ada toko pada filter ini'}
            description={stats.review === 0
              ? 'Data master toko sudah dikoreksi owner. Perubahan lanjutan bisa dilakukan di Kelola Akun.'
              : 'Hilangkan centang filter untuk melihat seluruh toko.'}
            testId="bulk-empty"
          />
        </GlassCard>
      ) : (
        <GlassTable data-testid="bulk-review-table-wrap">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="bulk-review-table">
              <thead>
                <tr className="border-b border-[var(--glass-border)] bg-muted/40">
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Kode</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Platform</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider min-w-[210px]">Nama Toko (final)</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider min-w-[170px]">Username Platform</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider min-w-[190px]">PIC</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider min-w-[230px]">Rekening Pencairan</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Akun Pendapatan</th>
                  <th className="px-3 py-2.5 text-center text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Sudah Ditinjau</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((acc, i) => {
                  const reviewed = val(acc, 'needs_owner_review') === false
                    || (!('needs_owner_review' in (draft[acc.id] || {})) && !acc.needs_owner_review);
                  return (
                    <tr key={acc.id}
                      className={`border-b border-[var(--glass-border)] last:border-0 ${i % 2 ? 'bg-muted/10' : ''}`}
                      data-testid={`bulk-row-${acc.account_code}`}>
                      <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">{acc.account_code}</td>
                      <td className="px-3 py-2 text-xs">{acc.platform}</td>
                      <td className="px-3 py-2">
                        <GlassInput className="h-9" value={val(acc, 'account_name')}
                          onChange={e => setVal(acc, 'account_name', e.target.value)}
                          data-testid={`bulk-name-${acc.account_code}`} />
                      </td>
                      <td className="px-3 py-2">
                        <GlassInput className="h-9" placeholder="username di platform"
                          value={val(acc, 'username')}
                          onChange={e => setVal(acc, 'username', e.target.value)}
                          data-testid={`bulk-username-${acc.account_code}`} />
                      </td>
                      <td className="px-3 py-2">
                        <Select value={val(acc, 'pic_user_id') || 'none'}
                          onValueChange={v => setVal(acc, 'pic_user_id', v)}>
                          <SelectTrigger className="h-9" data-testid={`bulk-pic-${acc.account_code}`}>
                            <SelectValue placeholder="Pilih PIC..." />
                          </SelectTrigger>
                          <SelectContent className="max-h-72">
                            <SelectItem value="none">— Tidak ada PIC —</SelectItem>
                            {users.map(u => (
                              <SelectItem key={u.id} value={u.id}>
                                {u.name || u.email}
                                <span className="text-muted-foreground text-xs ml-1">({u.role})</span>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {acc.pic_user_name && !(draft[acc.id] || {}).pic_user_id && (
                          <p className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
                            <UserCheck size={10} className="text-primary" />{acc.pic_user_name}
                          </p>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <Select value={val(acc, 'coa_cash_code') || undefined}
                          onValueChange={v => setVal(acc, 'coa_cash_code', v)}>
                          <SelectTrigger className="h-9" data-testid={`bulk-cash-${acc.account_code}`}>
                            <SelectValue placeholder="Pilih rekening..." />
                          </SelectTrigger>
                          <SelectContent className="max-h-72">
                            {(coa.cash || []).map(o => (
                              <SelectItem key={o.code} value={o.code}>{o.code} · {o.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <p className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
                          <Wallet size={10} className="text-primary" />
                          {coaName[val(acc, 'coa_cash_code')] || 'belum dipilih'}
                        </p>
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-mono text-xs">{acc.coa_revenue_code || '—'}</div>
                        <div className="text-[10px] text-muted-foreground max-w-[170px] truncate"
                          title={coaName[acc.coa_revenue_code] || ''}>
                          {coaName[acc.coa_revenue_code] || ''}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <Checkbox
                          checked={reviewed}
                          onCheckedChange={v => setVal(acc, 'needs_owner_review', !v)}
                          data-testid={`bulk-reviewed-${acc.account_code}`}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </GlassTable>
      )}

      <GlassPanel className="p-4 text-xs text-muted-foreground">
        <p className="flex items-start gap-2">
          <AlertTriangle size={13} className="text-amber-500 mt-0.5 shrink-0" />
          <span>
            Nama, username, PIC, dan rekening pencairan <b>tidak diisi otomatis oleh sistem</b> —
            hanya owner yang tahu datanya. Akun pendapatan (kolom terakhir) sudah tertaut dari
            bagan akun; ubah lewat <b>Kelola Akun</b> bila perlu.
          </span>
        </p>
      </GlassPanel>
    </div>
  );
}
