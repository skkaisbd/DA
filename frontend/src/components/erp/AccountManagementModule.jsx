/**
 * AccountManagementModule.jsx — Manajemen Akun Toko (Portal Marketing)
 *
 * F0.7 (2026-08-12): layar ini sekarang MENGISI & MENAMPILKAN tautan Finance
 * per toko yang sebelumnya hanya ada di backend:
 *   · coa_revenue_code        — akun pendapatan toko (4-111…4-131)
 *   · coa_cash_code           — rekening penerima pencairan (1-131 / 1-154 …)
 *   · coa_receivable_code     — akun piutang platform (default 1-220)
 *   · ar_account_code         — akun piutang KHUSUS toko (subledger otomatis, anak 1-220)
 *   · revenue_basis           — basis omzet (produk setelah diskon / order amount)
 *   · platform_warehouse_name — nama gudang di ekspor Seller Center
 *   · platform_shop_id        — id toko di platform
 *   · pic_user_id/name        — PIC toko (boleh diisi sejak pembuatan)
 *   · needs_owner_review      — penanda BD-5 (owner wajib mengoreksi data seed)
 *
 * Aturan UI repo (plan.md): setiap daftar record = TABEL (default) + KARTU
 * (alternatif) dengan kolom informasi penuh + paginasi 10/halaman.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Store, Plus, RefreshCw, Pencil, Archive, Loader2, UserCheck, Table2, LayoutGrid,
  Search, Landmark, Wallet, Receipt, Warehouse, Hash, BadgeCheck, AlertTriangle,
  Link2, Scale, X, Star, Calculator, ClipboardCheck,
} from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput, GlassTable } from '@/components/ui/glass';
import AccountAssignView from './marketing/AccountAssignView';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue, SelectGroup, SelectLabel,
} from '@/components/ui/select';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { PageHeader, StatTile, EmptyState } from './moduleAtoms';
import { toast } from 'sonner';
// F10 (sesi #10) — master toko dipakai lintas divisi (Finance/Gudang) ⇒ bisa diunduh.
import ExportCsvButton from '@/components/ui/export-csv-button';

const API = process.env.REACT_APP_BACKEND_URL || '';

const PLATFORMS = [
  { value: 'shopee', label: 'Shopee' },
  { value: 'tiktokshop', label: 'TikTokShop' },
  { value: 'tokopedia', label: 'Tokopedia' },
];

const GROUPS = [
  { value: 'official_store', label: 'Official Store' },
  { value: 'reseller', label: 'Reseller' },
  { value: 'distributor', label: 'Distributor' },
  { value: 'other', label: 'Lainnya' },
];

const STATUSES = [
  { value: 'active', label: 'Aktif' },
  { value: 'inactive', label: 'Nonaktif' },
  { value: 'suspended', label: 'Ditangguhkan' },
];

/** Label pendek basis omzet untuk kolom tabel (label panjang dipakai di form). */
const BASIS_SHORT = {
  produk_setelah_diskon: 'Produk (stlh diskon)',
  order_amount: 'Order Amount',
};

const platformColors = {
  shopee: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
  tiktokshop: 'bg-pink-500/10 text-pink-400 border-pink-500/30',
  tokopedia: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
};

const statusColors = {
  active: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  inactive: 'bg-muted/20 text-muted-foreground border-border/40',
  suspended: 'bg-red-500/10 text-red-400 border-red-500/30',
};

const statusLabel = (s) => (STATUSES.find(x => x.value === s)?.label || s || '—');
const groupLabel = (g) => (GROUPS.find(x => x.value === g)?.label || (g || '—'));
const platformLabel = (p) => (PLATFORMS.find(x => x.value === p)?.label || p || '—');

/** Sel tabel untuk kode COA: kode (mono) + nama akun kecil di bawahnya. */
function CoaCell({ code, name, testId, fallback }) {
  if (!code) {
    return (
      <span className="text-xs italic text-amber-500/90 whitespace-nowrap" data-testid={testId}>
        belum ditautkan
      </span>
    );
  }
  return (
    <div className="min-w-[150px]" data-testid={testId}>
      <div className="font-mono text-xs text-foreground flex items-center gap-1">
        {code}
        {fallback && (
          <span
            className="text-[9px] font-semibold uppercase tracking-wide px-1 py-px rounded bg-amber-500/15 text-amber-500 border border-amber-500/30"
            title="Memakai akun penampung platform — ganti ke akun khusus toko bila sudah ada"
          >
            penampung
          </span>
        )}
      </div>
      {name && <div className="text-[11px] text-muted-foreground truncate max-w-[190px]" title={name}>{name}</div>}
    </div>
  );
}

/**
 * Skor sehat akun — SKALA 1–5 (keputusan owner 2026-08-12).
 * Skor internal 0–100 tetap dipakai mesin; yang dilihat staf adalah bintang +
 * label + rincian per pilar (kenapa skornya segitu) lewat tooltip.
 * Toko tanpa data 30 hari terakhir = "Belum ada data" — BUKAN 1, supaya toko yang
 * datanya belum masuk tidak tampak seperti toko bermasalah.
 */
function HealthStars({ score, grade, label, breakdown, testId }) {
  const has = grade !== null && grade !== undefined;
  const detail = breakdown && Object.keys(breakdown).length
    ? Object.values(breakdown).map(b => `\u2022 ${b.label}: ${b.score}/${b.max}`).join('\n')
    : 'Belum ada data penjualan 30 hari terakhir';
  const title = has
    ? `${label} — skor ${score}/100\n${detail}`
    : 'Belum ada data penjualan 30 hari terakhir — impor pesanan atau isi rekap harian dulu';
  return (
    <div className="min-w-[110px]" data-testid={testId} title={title}>
      <div className="flex items-center gap-0.5">
        {[1, 2, 3, 4, 5].map(i => (
          <Star key={i} size={12}
            className={has && i <= grade ? 'fill-amber-400 text-amber-400' : 'text-muted-foreground/35'} />
        ))}
        {has && <span className="ml-1 text-xs font-bold tabular-nums">{grade}</span>}
      </div>
      <div className="text-[10px] text-muted-foreground truncate">
        {has ? label : 'Belum ada data'}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// FORM BUAT / EDIT AKUN
// ════════════════════════════════════════════════════════════════════════════
function AccountFormDialog({ open, onOpenChange, account, onSaved, token, coa, users }) {
  const isEdit = !!account;
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    account_code: '',
    account_name: '',
    platform: 'shopee',
    username: '',
    group: 'other',
    status: 'active',
    has_api_integration: false,
    pic_user_id: '',
    coa_revenue_code: '',
    coa_cash_code: '',
    coa_receivable_code: '',
    revenue_basis: 'produk_setelah_diskon',
    platform_warehouse_name: '',
    platform_shop_id: '',
  });

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token],
  );

  const channelOf = (platform) => (coa.platform_channel_map || {})[platform] || '';
  const fallbackRevenue = (platform) => (coa.fallback_revenue_by_platform || {})[platform] || '';

  useEffect(() => {
    if (!open) return;
    if (account) {
      setForm({
        account_code: account.account_code || '',
        account_name: account.account_name || '',
        platform: account.platform || 'shopee',
        username: account.username || '',
        group: account.group || 'other',
        status: account.status || 'active',
        has_api_integration: !!account?.credentials?.has_api_integration,
        pic_user_id: account.pic_user_id || '',
        // Akun lama yang belum ditautkan → sarankan akun penampung platform-nya
        coa_revenue_code: account.coa_revenue_code || fallbackRevenue(account.platform) || '',
        coa_cash_code: account.coa_cash_code || coa.default_cash || '',
        coa_receivable_code: account.coa_receivable_code || coa.default_receivable || '',
        revenue_basis: account.revenue_basis || 'produk_setelah_diskon',
        platform_warehouse_name: account.platform_warehouse_name || '',
        platform_shop_id: account.platform_shop_id || '',
      });
    } else {
      setForm({
        account_code: '',
        account_name: '',
        platform: 'shopee',
        username: '',
        group: 'other',
        status: 'active',
        has_api_integration: false,
        pic_user_id: '',
        coa_revenue_code: fallbackRevenue('shopee') || '',
        coa_cash_code: coa.default_cash || '',
        coa_receivable_code: coa.default_receivable || '',
        revenue_basis: 'produk_setelah_diskon',
        platform_warehouse_name: '',
        platform_shop_id: '',
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, account, coa]);

  /** Ganti platform saat buat baru → sarankan akun pendapatan platform tsb. */
  const handlePlatformChange = (v) => {
    setForm(f => {
      const wasSuggested = !f.coa_revenue_code || f.coa_revenue_code === fallbackRevenue(f.platform);
      return {
        ...f,
        platform: v,
        coa_revenue_code: wasSuggested ? (fallbackRevenue(v) || '') : f.coa_revenue_code,
      };
    });
  };

  const revenueOptions = coa.revenue || [];
  const cashOptions = coa.cash || [];
  const recvOptions = coa.receivable || [];
  const basisOptions = coa.revenue_basis_options || [
    { value: 'produk_setelah_diskon', label: 'Omzet produk (setelah diskon penjual)' },
    { value: 'order_amount', label: 'Order Amount (dibayar pembeli)' },
  ];
  const ch = channelOf(form.platform);
  const revRecommended = revenueOptions.filter(o => ch && o.channel === ch);
  const revOthers = revenueOptions.filter(o => !ch || o.channel !== ch);
  const selectedRevName = (revenueOptions.find(o => o.code === form.coa_revenue_code) || {}).name || '';
  const revenueIsCatchAll = /lain[\s-]*lain/i.test(selectedRevName);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.account_name.trim()) {
      toast.error('Nama akun wajib diisi');
      return;
    }
    if (!isEdit && !form.account_code.trim()) {
      toast.error('Kode akun wajib diisi');
      return;
    }
    if (!form.coa_revenue_code) {
      toast.error('Akun Pendapatan wajib dipilih — supaya omzet toko punya alamat jurnal');
      return;
    }
    if (!form.coa_cash_code) {
      toast.error('Rekening Pencairan wajib dipilih — supaya pencairan platform punya alamat jurnal');
      return;
    }

    setSubmitting(true);
    try {
      const shared = {
        account_name: form.account_name.trim(),
        username: form.username.trim() || null,
        group: form.group,
        has_api_integration: form.has_api_integration,
        pic_user_id: form.pic_user_id || null,
        coa_revenue_code: form.coa_revenue_code,
        coa_cash_code: form.coa_cash_code,
        coa_receivable_code: form.coa_receivable_code || null,
        revenue_basis: form.revenue_basis,
        platform_warehouse_name: form.platform_warehouse_name.trim(),
        platform_shop_id: form.platform_shop_id.trim(),
      };
      let res;
      if (isEdit) {
        res = await fetch(`${API}/api/marketing/accounts/${account.id}`, {
          method: 'PUT',
          headers,
          body: JSON.stringify({ ...shared, status: form.status }),
        });
      } else {
        res = await fetch(`${API}/api/marketing/accounts`, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            ...shared,
            account_code: form.account_code.trim().toUpperCase(),
            platform: form.platform,
          }),
        });
      }

      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || 'Gagal menyimpan akun');

      const saved = body.account || {};
      if (!isEdit && saved.ar_account_code) {
        toast.success(
          `Akun dibuat · akun COA piutang toko otomatis: ${saved.ar_account_code}`,
          { duration: 6000 },
        );
      } else {
        toast.success(isEdit ? 'Perubahan akun tersimpan' : 'Akun berhasil dibuat');
      }
      onOpenChange(false);
      if (onSaved) onSaved();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[92vh] overflow-y-auto" data-testid="account-form-dialog">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit Akun — ${account?.account_name || ''}` : 'Tambah Akun Toko Baru'}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Perbarui identitas toko, PIC, dan tautan Finance (akun pendapatan · rekening pencairan · piutang).'
              : 'Daftarkan toko marketplace. Akun COA piutang khusus toko ini dibuat otomatis (anak 1-220).'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* ── Identitas toko ─────────────────────────────────────────── */}
          <div className="space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Store size={12} className="text-primary" /> Identitas Toko
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {!isEdit && (
                <div>
                  <Label htmlFor="acc-code">Kode Akun <span className="text-red-400">*</span></Label>
                  <GlassInput
                    id="acc-code"
                    value={form.account_code}
                    onChange={e => setForm(f => ({ ...f, account_code: e.target.value.toUpperCase() }))}
                    placeholder="TIKTOK-OUTFIT"
                    data-testid="acc-code-input"
                    required
                  />
                  <p className="text-xs text-muted-foreground mt-1">Kode unik (otomatis huruf besar)</p>
                </div>
              )}
              <div>
                <Label htmlFor="acc-name">Nama Akun <span className="text-red-400">*</span></Label>
                <GlassInput
                  id="acc-name"
                  value={form.account_name}
                  onChange={e => setForm(f => ({ ...f, account_name: e.target.value }))}
                  placeholder="TikTok Outfit Boutique"
                  data-testid="acc-name-input"
                  required
                />
              </div>
              {!isEdit && (
                <div>
                  <Label>Platform <span className="text-red-400">*</span></Label>
                  <Select value={form.platform} onValueChange={handlePlatformChange}>
                    <SelectTrigger data-testid="acc-platform-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {PLATFORMS.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div>
                <Label>Grup</Label>
                <Select value={form.group} onValueChange={v => setForm(f => ({ ...f, group: v }))}>
                  <SelectTrigger data-testid="acc-group-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {GROUPS.map(g => <SelectItem key={g.value} value={g.value}>{g.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="acc-username">Username Platform</Label>
                <GlassInput
                  id="acc-username"
                  value={form.username}
                  onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                  placeholder="outfit.boutique"
                  data-testid="acc-username-input"
                />
              </div>
              {isEdit && (
                <div>
                  <Label>Status</Label>
                  <Select value={form.status} onValueChange={v => setForm(f => ({ ...f, status: v }))}>
                    <SelectTrigger data-testid="acc-status-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {STATUSES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div>
                <Label className="flex items-center gap-1.5">
                  <UserCheck size={13} className="text-primary" /> PIC (Penanggung Jawab)
                </Label>
                <Select
                  value={form.pic_user_id || 'none'}
                  onValueChange={v => setForm(f => ({ ...f, pic_user_id: v === 'none' ? '' : v }))}
                >
                  <SelectTrigger data-testid="acc-pic-select"><SelectValue placeholder="Pilih PIC..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">— Tidak ada PIC —</SelectItem>
                    {users.map(u => (
                      <SelectItem key={u.id} value={u.id}>
                        {u.name || u.email}
                        <span className="text-muted-foreground text-xs ml-1">({u.role})</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">
                  Task otomatis (input sales, health alert) di-assign ke PIC ini.
                </p>
              </div>
            </div>
          </div>

          {/* ── Tautan Finance (F0.7) ──────────────────────────────────── */}
          <div className="space-y-3 rounded-[var(--radius-md)] border border-[var(--glass-border)] bg-[var(--card-surface)] p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Landmark size={12} className="text-primary" /> Tautan Finance — alamat jurnal toko
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="flex items-center gap-1.5">
                  <Receipt size={13} className="text-primary" />
                  Akun Pendapatan <span className="text-red-400">*</span>
                </Label>
                <Select
                  value={form.coa_revenue_code || undefined}
                  onValueChange={v => setForm(f => ({ ...f, coa_revenue_code: v }))}
                >
                  <SelectTrigger data-testid="acc-coa-revenue-select">
                    <SelectValue placeholder="Pilih akun pendapatan..." />
                  </SelectTrigger>
                  <SelectContent className="max-h-72">
                    {revRecommended.length > 0 && (
                      <SelectGroup>
                        <SelectLabel>Disarankan untuk {platformLabel(form.platform)}</SelectLabel>
                        {revRecommended.map(o => (
                          <SelectItem key={o.code} value={o.code}>{o.code} · {o.name}</SelectItem>
                        ))}
                      </SelectGroup>
                    )}
                    {revOthers.length > 0 && (
                      <SelectGroup>
                        <SelectLabel>Akun penjualan lain</SelectLabel>
                        {revOthers.map(o => (
                          <SelectItem key={o.code} value={o.code}>{o.code} · {o.name}</SelectItem>
                        ))}
                      </SelectGroup>
                    )}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">
                  Omzet toko ini dibukukan ke akun tersebut (mis. 4-122 TikTok Outfit Boutique).
                </p>
                {revenueIsCatchAll && (
                  <p className="text-xs text-amber-500 mt-1 flex items-start gap-1" data-testid="acc-coa-revenue-catchall-hint">
                    <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                    <span>
                      Ini <b>akun penampung</b> bersama, bukan akun khusus toko ini.
                      Ganti bila akun toko sudah dibuat di Portal Keuangan → COA.
                    </span>
                  </p>
                )}
              </div>

              <div>
                <Label className="flex items-center gap-1.5">
                  <Wallet size={13} className="text-primary" />
                  Rekening Pencairan <span className="text-red-400">*</span>
                </Label>
                <Select
                  value={form.coa_cash_code || undefined}
                  onValueChange={v => setForm(f => ({ ...f, coa_cash_code: v }))}
                >
                  <SelectTrigger data-testid="acc-coa-cash-select">
                    <SelectValue placeholder="Pilih rekening kas/bank..." />
                  </SelectTrigger>
                  <SelectContent className="max-h-72">
                    {cashOptions.map(o => (
                      <SelectItem key={o.code} value={o.code}>{o.code} · {o.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">
                  Rekening/e-wallet penerima pencairan platform (mis. 1-154 ShopeePay).
                </p>
              </div>

              <div>
                <Label className="flex items-center gap-1.5">
                  <Link2 size={13} className="text-primary" /> Akun Piutang Platform
                </Label>
                <Select
                  value={form.coa_receivable_code || undefined}
                  onValueChange={v => setForm(f => ({ ...f, coa_receivable_code: v }))}
                >
                  <SelectTrigger data-testid="acc-coa-receivable-select">
                    <SelectValue placeholder="Pilih akun piutang..." />
                  </SelectTrigger>
                  <SelectContent className="max-h-72">
                    {recvOptions.map(o => (
                      <SelectItem key={o.code} value={o.code}>{o.code} · {o.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">
                  Default {coa.default_receivable || '1-220'} — dana yang belum cair dari platform.
                </p>
              </div>

              <div>
                <Label className="flex items-center gap-1.5">
                  <Scale size={13} className="text-primary" /> Basis Omzet
                </Label>
                <Select
                  value={form.revenue_basis}
                  onValueChange={v => setForm(f => ({ ...f, revenue_basis: v }))}
                >
                  <SelectTrigger data-testid="acc-revenue-basis-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {basisOptions.map(o => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">
                  Menentukan angka mana yang dihitung sebagai omzet toko saat impor pesanan.
                </p>
              </div>
            </div>

            {isEdit && (
              <div className="text-xs text-muted-foreground border-t border-[var(--glass-border)] pt-2">
                Akun piutang khusus toko (otomatis):{' '}
                {account?.ar_account_code
                  ? <span className="font-mono text-foreground">{account.ar_account_code}</span>
                  : <span className="italic text-amber-500/90">belum terbentuk</span>}
              </div>
            )}
          </div>

          {/* ── Data platform ──────────────────────────────────────────── */}
          <div className="space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Warehouse size={12} className="text-primary" /> Data Platform (untuk impor Seller Center)
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label htmlFor="acc-warehouse">Nama Gudang di Platform</Label>
                <GlassInput
                  id="acc-warehouse"
                  value={form.platform_warehouse_name}
                  onChange={e => setForm(f => ({ ...f, platform_warehouse_name: e.target.value }))}
                  placeholder="Outfit Boutique"
                  data-testid="acc-warehouse-input"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Persis seperti di kolom &quot;Warehouse Name&quot; pada ekspor pesanan.
                </p>
              </div>
              <div>
                <Label htmlFor="acc-shopid" className="flex items-center gap-1.5">
                  <Hash size={13} className="text-primary" /> Shop ID Platform
                </Label>
                <GlassInput
                  id="acc-shopid"
                  value={form.platform_shop_id}
                  onChange={e => setForm(f => ({ ...f, platform_shop_id: e.target.value }))}
                  placeholder="7495123456789"
                  data-testid="acc-shopid-input"
                />
              </div>
            </div>
            <div className="flex items-center justify-between rounded-[var(--radius-sm)] border border-[var(--glass-border)] px-3 py-2">
              <div>
                <p className="text-sm text-foreground">Integrasi API platform</p>
                <p className="text-xs text-muted-foreground">Aktifkan bila toko ini sudah tersambung API resmi.</p>
              </div>
              <Switch
                checked={form.has_api_integration}
                onCheckedChange={v => setForm(f => ({ ...f, has_api_integration: v }))}
                data-testid="acc-api-switch"
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
              Batal
            </Button>
            <Button type="submit" disabled={submitting} data-testid="acc-submit-btn">
              {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {isEdit ? 'Simpan Perubahan' : 'Buat Akun'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// MODUL UTAMA
// ════════════════════════════════════════════════════════════════════════════
function AccountManagementBase({ token, onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [accounts, setAccounts] = useState([]);
  const [coa, setCoa] = useState({});
  const [users, setUsers] = useState([]);
  const [filter, setFilter] = useState({ platform: 'all', status: 'all', group: 'all' });
  const [search, setSearch] = useState('');
  const [onlyReview, setOnlyReview] = useState(false);
  const [onlyNoPic, setOnlyNoPic] = useState(false);
  const [viewMode, setViewMode] = useState('table');   // 'table' (default) | 'cards'
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editAccount, setEditAccount] = useState(null);
  const [archiveTarget, setArchiveTarget] = useState(null);
  const [reviewingId, setReviewingId] = useState(null);
  const [scoring, setScoring] = useState(false);

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token],
  );

  const fetchAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter.platform !== 'all') params.append('platform', filter.platform);
      if (filter.status !== 'all') params.append('status', filter.status);
      if (filter.group !== 'all') params.append('group', filter.group);
      const res = await fetch(`${API}/api/marketing/accounts?${params.toString()}`, { headers });
      if (!res.ok) throw new Error('Gagal memuat akun');
      const data = await res.json();
      setAccounts(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error(e.message || 'Gagal memuat akun');
    } finally {
      setLoading(false);
    }
  }, [filter, headers]);

  /** Opsi COA + daftar user (dropdown form) — sekali saja saat modul dibuka. */
  const fetchRefs = useCallback(async () => {
    try {
      const [rc, ru] = await Promise.all([
        fetch(`${API}/api/marketing/accounts/coa-options`, { headers }),
        fetch(`${API}/api/auth/users?limit=200`, { headers }),
      ]);
      if (rc.ok) setCoa(await rc.json());
      if (ru.ok) {
        const u = await ru.json();
        setUsers(Array.isArray(u) ? u : (u.items || u.users || []));
      }
    } catch {
      toast.error('Gagal memuat daftar akun COA / pengguna');
    }
  }, [headers]);

  useEffect(() => { fetchAccounts(); }, [fetchAccounts]);
  useEffect(() => { fetchRefs(); }, [fetchRefs]);

  /** code → nama akun COA (untuk kolom tabel & kartu). */
  const coaNameMap = useMemo(() => {
    const m = {};
    [...(coa.revenue || []), ...(coa.cash || []), ...(coa.receivable || [])]
      .forEach(o => { m[o.code] = o.name; });
    return m;
  }, [coa]);

  /**
   * Akun "penampung" = akun pendapatan bersama (mis. 4-114 Shopee Lain-lain),
   * BUKAN akun milik toko itu sendiri. 4-131 Tokopedia dipakai sebagai default
   * platform tetapi memang akun toko tersebut ⇒ jangan diberi label penampung.
   */
  const isCatchAll = useCallback(
    (code) => /lain[\s-]*lain/i.test(coaNameMap[code] || ''),
    [coaNameMap],
  );
  const basisLabel = useCallback((v) => {
    if (!v) return '—';
    return BASIS_SHORT[v] || v;
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return accounts.filter(a => {
      if (onlyReview && !a.needs_owner_review) return false;
      if (onlyNoPic && a.pic_user_name) return false;
      if (!q) return true;
      return [
        a.account_code, a.account_name, a.username, a.pic_user_name,
        a.coa_revenue_code, a.coa_cash_code, a.coa_receivable_code, a.ar_account_code,
        a.platform_warehouse_name, a.platform_shop_id,
      ].some(v => (v || '').toString().toLowerCase().includes(q));
    });
  }, [accounts, search, onlyReview, onlyNoPic]);

  const { page, setPage, totalPages, total, paged, pageSize } = useClientPagination(filtered, 10);

  const stats = useMemo(() => ({
    total: accounts.length,
    active: accounts.filter(a => a.status === 'active').length,
    noPic: accounts.filter(a => !a.pic_user_name).length,
    review: accounts.filter(a => a.needs_owner_review).length,
    noCoa: accounts.filter(a => !a.coa_revenue_code).length,
  }), [accounts]);

  const handleEdit = (acc) => { setEditAccount(acc); setDialogOpen(true); };
  const handleCreate = () => { setEditAccount(null); setDialogOpen(true); };

  const handleArchive = async () => {
    if (!archiveTarget) return;
    try {
      const res = await fetch(`${API}/api/marketing/accounts/${archiveTarget.id}`, {
        method: 'DELETE', headers,
      });
      if (!res.ok) throw new Error('Gagal mengarsipkan akun');
      toast.success('Akun diarsipkan (status nonaktif)');
      setArchiveTarget(null);
      fetchAccounts();
    } catch (e) {
      toast.error(e.message);
    }
  };

  /** BD-5 — owner sudah mengoreksi nama/PIC/rekening toko hasil seed. */
  const markReviewed = async (acc) => {
    setReviewingId(acc.id);
    try {
      const res = await fetch(`${API}/api/marketing/accounts/${acc.id}`, {
        method: 'PUT', headers, body: JSON.stringify({ needs_owner_review: false }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || 'Gagal menandai akun');
      toast.success(`${acc.account_name} ditandai sudah ditinjau`);
      fetchAccounts();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setReviewingId(null);
    }
  };

  /** Skor sehat 1–5 dihitung dari data 30 hari terakhir seluruh toko. */
  const recomputeHealth = async () => {
    setScoring(true);
    try {
      const res = await fetch(`${API}/api/marketing/accounts/health/recompute-all`, {
        method: 'POST', headers,
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || 'Gagal menghitung skor');
      toast.success(body.message || 'Skor sehat diperbarui', { duration: 6000 });
      fetchAccounts();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setScoring(false);
    }
  };

  const resetFilters = () => {
    setFilter({ platform: 'all', status: 'all', group: 'all' });
    setSearch('');
    setOnlyReview(false);
    setOnlyNoPic(false);
  };

  const activeFilterCount =
    (filter.platform !== 'all' ? 1 : 0) + (filter.status !== 'all' ? 1 : 0) +
    (filter.group !== 'all' ? 1 : 0) + (search ? 1 : 0) + (onlyReview ? 1 : 0) + (onlyNoPic ? 1 : 0);

  // ── Baris tabel ───────────────────────────────────────────────────────────
  const renderRow = (acc, i) => (
    <tr
      key={acc.id}
      className={`border-b border-[var(--glass-border)] last:border-0 hover:bg-muted/30 transition-colors ${i % 2 === 0 ? '' : 'bg-muted/10'}`}
      data-testid={`acc-row-${acc.account_code}`}
    >
      <td className="px-3 py-2.5 align-top">
        <div className="font-mono text-xs text-foreground whitespace-nowrap">{acc.account_code}</div>
        <div className="flex flex-wrap gap-1 mt-1">
          {acc.is_demo && (
            <span className="text-[9px] uppercase font-semibold px-1 py-px rounded bg-muted/30 text-muted-foreground border border-border/40">demo</span>
          )}
          {acc.needs_owner_review && (
            <span
              className="text-[9px] uppercase font-semibold px-1 py-px rounded bg-amber-500/15 text-amber-500 border border-amber-500/30"
              title="Data hasil seed — owner perlu mengoreksi nama/PIC/rekening (BD-5)"
              data-testid={`acc-review-badge-${acc.account_code}`}
            >
              perlu ditinjau
            </span>
          )}
        </div>
      </td>
      <td className="px-3 py-2.5 align-top">
        <div className="font-medium text-sm text-foreground max-w-[190px] truncate" title={acc.account_name}>
          {acc.account_name}
        </div>
      </td>
      <td className="px-3 py-2.5 align-top">
        <Badge variant="outline" className={platformColors[acc.platform]}>{platformLabel(acc.platform)}</Badge>
      </td>
      <td className="px-3 py-2.5 align-top text-xs text-muted-foreground whitespace-nowrap">{groupLabel(acc.group)}</td>
      <td className="px-3 py-2.5 align-top text-xs font-mono text-muted-foreground">{acc.username || '—'}</td>
      <td className="px-3 py-2.5 align-top">
        <Badge variant="outline" className={statusColors[acc.status]}>{statusLabel(acc.status)}</Badge>
      </td>
      <td className="px-3 py-2.5 align-top text-xs">
        {acc.pic_user_name
          ? <span className="text-foreground flex items-center gap-1"><UserCheck size={11} className="text-primary shrink-0" />{acc.pic_user_name}</span>
          : <span className="italic text-amber-500/90">belum ada PIC</span>}
      </td>
      <td className="px-3 py-2.5 align-top">
        <CoaCell
          code={acc.coa_revenue_code}
          name={coaNameMap[acc.coa_revenue_code]}
          fallback={isCatchAll(acc.coa_revenue_code)}
          testId={`acc-coa-rev-${acc.account_code}`}
        />
      </td>
      <td className="px-3 py-2.5 align-top">
        <CoaCell code={acc.coa_cash_code} name={coaNameMap[acc.coa_cash_code]} testId={`acc-coa-cash-${acc.account_code}`} />
      </td>
      <td className="px-3 py-2.5 align-top">
        <CoaCell code={acc.coa_receivable_code} name={coaNameMap[acc.coa_receivable_code]} testId={`acc-coa-recv-${acc.account_code}`} />
      </td>
      <td className="px-3 py-2.5 align-top">
        {acc.ar_account_code
          ? <span className="font-mono text-xs text-foreground whitespace-nowrap" data-testid={`acc-ar-${acc.account_code}`}>{acc.ar_account_code}</span>
          : <span className="text-xs italic text-amber-500/90">belum terbentuk</span>}
      </td>
      <td className="px-3 py-2.5 align-top text-xs text-foreground whitespace-nowrap">{basisLabel(acc.revenue_basis)}</td>
      <td className="px-3 py-2.5 align-top text-xs text-muted-foreground">{acc.platform_warehouse_name || '—'}</td>
      <td className="px-3 py-2.5 align-top text-xs font-mono text-muted-foreground">{acc.platform_shop_id || '—'}</td>
      <td className="px-3 py-2.5 align-top"><HealthStars score={acc.health_score} grade={acc.health_grade} label={acc.health_label}
          breakdown={acc.health_breakdown} testId={`acc-health-${acc.account_code}`} /></td>
      <td className="px-3 py-2.5 align-top sticky right-0 bg-[hsl(var(--card))] border-l border-[var(--glass-border)]">
        <div className="flex items-center justify-end gap-1">
          {acc.needs_owner_review && (
            <Button
              size="icon" variant="ghost" className="h-7 w-7 text-emerald-500 hover:bg-emerald-500/10"
              title="Tandai sudah ditinjau owner"
              onClick={() => markReviewed(acc)}
              disabled={reviewingId === acc.id}
              data-testid={`mark-reviewed-${acc.account_code}`}
            >
              {reviewingId === acc.id ? <Loader2 size={12} className="animate-spin" /> : <BadgeCheck size={13} />}
            </Button>
          )}
          <Button
            size="icon" variant="ghost" className="h-7 w-7"
            title="Edit akun" onClick={() => handleEdit(acc)}
            data-testid={`edit-acc-${acc.account_code}`}
          >
            <Pencil size={12} />
          </Button>
          <Button
            size="icon" variant="ghost" className="h-7 w-7 text-red-400 hover:bg-red-500/10"
            title="Arsipkan akun" onClick={() => setArchiveTarget(acc)}
            data-testid={`archive-acc-${acc.account_code}`}
          >
            <Archive size={12} />
          </Button>
        </div>
      </td>
    </tr>
  );

  // ── Kartu ─────────────────────────────────────────────────────────────────
  const renderCard = (acc) => (
    <GlassCard key={acc.id} className="p-4" data-testid={`acc-card-${acc.account_code}`}>
      <div className="flex items-start justify-between mb-3 gap-2">
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-foreground text-sm truncate" title={acc.account_name}>{acc.account_name}</div>
          <div className="text-xs text-muted-foreground font-mono">{acc.account_code}</div>
        </div>
        <HealthStars score={acc.health_score} grade={acc.health_grade} label={acc.health_label}
          breakdown={acc.health_breakdown} />
      </div>

      <div className="flex flex-wrap items-center gap-1.5 mb-3">
        <Badge variant="outline" className={platformColors[acc.platform]}>{platformLabel(acc.platform)}</Badge>
        <Badge variant="outline" className={statusColors[acc.status]}>{statusLabel(acc.status)}</Badge>
        <Badge variant="outline" className="text-xs">{groupLabel(acc.group)}</Badge>
        {acc.is_demo && <Badge variant="outline" className="text-xs text-muted-foreground">demo</Badge>}
        {acc.needs_owner_review && (
          <Badge variant="outline" className="text-xs bg-amber-500/10 text-amber-500 border-amber-500/30">
            perlu ditinjau
          </Badge>
        )}
      </div>

      <dl className="space-y-1.5 text-xs">
        <div className="flex items-start gap-2">
          <dt className="w-[104px] shrink-0 text-muted-foreground">Username</dt>
          <dd className="font-mono text-foreground truncate">{acc.username || '—'}</dd>
        </div>
        <div className="flex items-start gap-2">
          <dt className="w-[104px] shrink-0 text-muted-foreground">PIC</dt>
          <dd className={acc.pic_user_name ? 'text-foreground' : 'italic text-amber-500/90'}>
            {acc.pic_user_name || 'belum ada PIC'}
          </dd>
        </div>
        <div className="flex items-start gap-2">
          <dt className="w-[104px] shrink-0 text-muted-foreground">Pendapatan</dt>
          <dd className="min-w-0">
            <CoaCell
              code={acc.coa_revenue_code}
              name={coaNameMap[acc.coa_revenue_code]}
              fallback={isCatchAll(acc.coa_revenue_code)}
            />
          </dd>
        </div>
        <div className="flex items-start gap-2">
          <dt className="w-[104px] shrink-0 text-muted-foreground">Pencairan</dt>
          <dd className="min-w-0"><CoaCell code={acc.coa_cash_code} name={coaNameMap[acc.coa_cash_code]} /></dd>
        </div>
        <div className="flex items-start gap-2">
          <dt className="w-[104px] shrink-0 text-muted-foreground">Piutang</dt>
          <dd className="min-w-0"><CoaCell code={acc.coa_receivable_code} name={coaNameMap[acc.coa_receivable_code]} /></dd>
        </div>
        <div className="flex items-start gap-2">
          <dt className="w-[104px] shrink-0 text-muted-foreground">Piutang toko</dt>
          <dd className="font-mono text-foreground truncate">{acc.ar_account_code || '—'}</dd>
        </div>
        <div className="flex items-start gap-2">
          <dt className="w-[104px] shrink-0 text-muted-foreground">Basis omzet</dt>
          <dd className="text-foreground">{basisLabel(acc.revenue_basis)}</dd>
        </div>
        <div className="flex items-start gap-2">
          <dt className="w-[104px] shrink-0 text-muted-foreground">Gudang platform</dt>
          <dd className="text-foreground truncate">{acc.platform_warehouse_name || '—'}</dd>
        </div>
        <div className="flex items-start gap-2">
          <dt className="w-[104px] shrink-0 text-muted-foreground">Shop ID</dt>
          <dd className="font-mono text-foreground truncate">{acc.platform_shop_id || '—'}</dd>
        </div>
      </dl>

      <div className="flex items-center gap-2 pt-3 mt-3 border-t border-[var(--glass-border)]">
        <Button size="sm" variant="outline" className="flex-1" onClick={() => handleEdit(acc)} data-testid={`edit-acc-card-${acc.account_code}`}>
          <Pencil className="w-3 h-3 mr-1" /> Edit
        </Button>
        {acc.needs_owner_review && (
          <Button
            size="sm" variant="outline" className="text-emerald-500 hover:bg-emerald-500/10"
            onClick={() => markReviewed(acc)} disabled={reviewingId === acc.id}
            data-testid={`mark-reviewed-card-${acc.account_code}`}
          >
            {reviewingId === acc.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <BadgeCheck className="w-3 h-3" />}
          </Button>
        )}
        <Button
          size="sm" variant="outline" className="text-red-400 hover:bg-red-500/10"
          onClick={() => setArchiveTarget(acc)} data-testid={`archive-acc-card-${acc.account_code}`}
        >
          <Archive className="w-3 h-3" />
        </Button>
      </div>
    </GlassCard>
  );

  return (
    <div className="space-y-5" data-testid="account-management-module">
      <PageHeader
        icon={Store}
        eyebrow="Portal Marketing · Master Toko"
        title="Manajemen Akun Toko"
        subtitle="Kelola toko Shopee · TikTokShop · Tokopedia beserta PIC dan tautan Finance (pendapatan, pencairan, piutang)"
        actions={
          <div className="flex items-center gap-2">
            <Button onClick={fetchAccounts} variant="outline" size="sm" data-testid="refresh-accounts-btn">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Muat Ulang
            </Button>
            <Button onClick={recomputeHealth} variant="outline" size="sm" disabled={scoring}
              data-testid="recompute-health-btn">
              {scoring ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                : <Calculator className="w-3.5 h-3.5 mr-1.5" />} Hitung Ulang Skor
            </Button>
            <Button
              onClick={() => (onNavigate ? onNavigate('marketing-account-review')
                : (window.location.hash = 'marketing-account-review'))}
              variant="outline" size="sm" data-testid="open-bulk-review-btn">
              <ClipboardCheck className="w-3.5 h-3.5 mr-1.5" /> Koreksi Data Toko
            </Button>
            <Button onClick={handleCreate} size="sm" data-testid="create-account-btn">
              <Plus className="w-3.5 h-3.5 mr-1.5" /> Tambah Akun
            </Button>
          </div>
        }
      />

      {/* Ringkasan */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatTile label="Total Toko" value={stats.total} testId="stat-total-accounts" />
        <StatTile
          label="Aktif" value={stats.active} accent="success" testId="stat-active-accounts"
          onClick={() => setFilter(f => ({ ...f, status: 'active' }))} hint="Filter status aktif"
        />
        <StatTile
          label="Tanpa PIC" value={stats.noPic} accent={stats.noPic ? 'warning' : 'default'} testId="stat-nopic-accounts"
          onClick={() => { setOnlyNoPic(v => !v); setOnlyReview(false); }} hint="Toko tanpa penanggung jawab"
        />
        <StatTile
          label="Perlu Ditinjau" value={stats.review} accent={stats.review ? 'warning' : 'default'} testId="stat-review-accounts"
          onClick={() => { setOnlyReview(v => !v); setOnlyNoPic(false); }} hint="Data seed belum dikoreksi owner"
        />
        <StatTile
          label="Tanpa Akun Pendapatan" value={stats.noCoa}
          accent={stats.noCoa ? 'danger' : 'success'} testId="stat-nocoa-accounts"
        />
      </div>

      {/* Filter + pengalih tampilan */}
      <GlassPanel className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex rounded-md border border-[var(--glass-border)] overflow-hidden self-end">
            <button
              type="button" onClick={() => setViewMode('table')} data-testid="view-mode-table-btn"
              className={`px-3 py-2 text-xs font-medium inline-flex items-center gap-1.5 transition-colors ${viewMode === 'table' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted/40'}`}
            >
              <Table2 size={13} /> Tabel
            </button>
            <button
              type="button" onClick={() => setViewMode('cards')} data-testid="view-mode-cards-btn"
              className={`px-3 py-2 text-xs font-medium inline-flex items-center gap-1.5 transition-colors ${viewMode === 'cards' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted/40'}`}
            >
              <LayoutGrid size={13} /> Kartu
            </button>
          </div>

          <ExportCsvButton
            filename="master-toko-marketing"
            testId="accounts-export-csv"
            className="h-9 self-end"
            head={['Kode', 'Nama akun', 'Platform', 'Grup', 'Username', 'Status', 'PIC',
              'Shop ID', 'Kode COA piutang', 'Gudang']}
            rows={(filtered || []).map((a) => [a.account_code, a.account_name, a.platform,
              a.group_name || a.account_group || '', a.username, a.status,
              a.pic_name || a.pic_id || '', a.shop_id || '',
              a.ar_coa_code || a.coa_code || '', a.warehouse_code || a.warehouse_id || ''])}
          />

          <div className="flex-1 min-w-[200px]">
            <Label className="text-xs">Cari</Label>
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <GlassInput
                className="pl-8"
                placeholder="Kode, nama, username, kode COA, gudang, shop id..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                data-testid="acc-search-input"
              />
            </div>
          </div>

          <div className="min-w-[150px]">
            <Label className="text-xs">Platform</Label>
            <Select value={filter.platform} onValueChange={v => setFilter(f => ({ ...f, platform: v }))}>
              <SelectTrigger data-testid="filter-platform"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Platform</SelectItem>
                {PLATFORMS.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="min-w-[150px]">
            <Label className="text-xs">Status</Label>
            <Select value={filter.status} onValueChange={v => setFilter(f => ({ ...f, status: v }))}>
              <SelectTrigger data-testid="filter-status"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Status</SelectItem>
                {STATUSES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="min-w-[150px]">
            <Label className="text-xs">Grup</Label>
            <Select value={filter.group} onValueChange={v => setFilter(f => ({ ...f, group: v }))}>
              <SelectTrigger data-testid="filter-group"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Grup</SelectItem>
                {GROUPS.map(g => <SelectItem key={g.value} value={g.value}>{g.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          {activeFilterCount > 0 && (
            <Button variant="outline" size="sm" onClick={resetFilters} data-testid="reset-filters-btn">
              <X className="w-3.5 h-3.5 mr-1" /> Bersihkan ({activeFilterCount})
            </Button>
          )}

          <div className="flex items-center text-sm text-muted-foreground ml-auto">
            Tampil: <span className="text-foreground font-semibold mx-1">{filtered.length}</span>
            dari {accounts.length} toko
          </div>
        </div>

        {(onlyReview || onlyNoPic) && (
          <div className="flex flex-wrap gap-2 mt-3">
            {onlyReview && (
              <Badge variant="outline" className="bg-amber-500/10 text-amber-500 border-amber-500/30 cursor-pointer" onClick={() => setOnlyReview(false)}>
                <AlertTriangle size={11} className="mr-1" /> Hanya &quot;perlu ditinjau&quot; · klik untuk hapus
              </Badge>
            )}
            {onlyNoPic && (
              <Badge variant="outline" className="bg-amber-500/10 text-amber-500 border-amber-500/30 cursor-pointer" onClick={() => setOnlyNoPic(false)}>
                <UserCheck size={11} className="mr-1" /> Hanya tanpa PIC · klik untuk hapus
              </Badge>
            )}
          </div>
        )}
      </GlassPanel>

      {/* Daftar */}
      {loading ? (
        <div className="space-y-2" data-testid="accounts-loading">
          {[1, 2, 3, 4, 5, 6].map(i => <Skeleton key={i} className="h-12" />)}
        </div>
      ) : filtered.length === 0 ? (
        <GlassCard className="p-4">
          <EmptyState
            icon={Store}
            title={accounts.length === 0 ? 'Belum ada akun toko' : 'Tidak ada akun yang cocok dengan filter'}
            description={accounts.length === 0
              ? 'Tambahkan toko marketplace pertama beserta tautan Finance-nya.'
              : 'Ubah kata pencarian atau bersihkan filter untuk melihat toko lain.'}
            testId="accounts-empty-state"
            action={accounts.length === 0 ? (
              <Button size="sm" onClick={handleCreate} data-testid="create-first-account-btn">
                <Plus className="w-4 h-4 mr-2" /> Tambah Akun Pertama
              </Button>
            ) : (
              <Button size="sm" variant="outline" onClick={resetFilters}>Bersihkan Filter</Button>
            )}
          />
        </GlassCard>
      ) : viewMode === 'table' ? (
        <GlassTable data-testid="accounts-table-wrap">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="accounts-table">
              <thead>
                <tr className="border-b border-[var(--glass-border)] bg-muted/40">
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Kode</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Nama Akun</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Platform</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Grup</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Username</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Status</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">PIC</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Akun Pendapatan</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Rekening Pencairan</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Piutang Platform</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Piutang Toko (otomatis)</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Basis Omzet</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Gudang Platform</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Shop ID</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">Skor</th>
                  <th className="px-3 py-2.5 text-right text-[10px] font-semibold text-muted-foreground uppercase tracking-wider sticky right-0 bg-[hsl(var(--card))] border-l border-[var(--glass-border)]">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((acc, i) => renderRow(acc, i))}
              </tbody>
            </table>
          </div>
          <PaginationLite
            page={page} totalPages={totalPages} total={total} pageSize={pageSize}
            onPageChange={setPage} className="px-3"
          />
        </GlassTable>
      ) : (
        <div data-testid="accounts-cards">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {paged.map(acc => renderCard(acc))}
          </div>
          <PaginationLite
            page={page} totalPages={totalPages} total={total} pageSize={pageSize}
            onPageChange={setPage} className="mt-3"
          />
        </div>
      )}

      <AccountFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        account={editAccount}
        onSaved={fetchAccounts}
        token={token}
        coa={coa}
        users={users}
      />

      <AlertDialog open={!!archiveTarget} onOpenChange={(o) => !o && setArchiveTarget(null)}>
        <AlertDialogContent data-testid="archive-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Arsipkan Akun?</AlertDialogTitle>
            <AlertDialogDescription>
              Akun <b>{archiveTarget?.account_name}</b> akan berstatus nonaktif.
              Data akun, riwayat penjualan, dan tautan COA tidak dihapus.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Batal</AlertDialogCancel>
            <AlertDialogAction onClick={handleArchive} className="bg-red-500 hover:bg-red-600" data-testid="confirm-archive-btn">
              Arsipkan
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}


// ════════════════════════════════════════════════════════════════════════════
// F6.4 (2026-08-13) — SATU PINTU, DUA TAMPILAN
// "Daftar Toko" (yang sudah ada) + "Assign Staf" (menetapkan pemegang toko).
// Dibungkus di sini, BUKAN sebagai menu baru: menu terpisah untuk hal yang
// dikerjakan di layar yang sama melahirkan pintu kembar (dan guardrail navigasi
// `check_nav_map` memang menolaknya).
// ════════════════════════════════════════════════════════════════════════════
export default function AccountManagementModule(props) {
  const [tab, setTab] = useState('daftar');
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5 px-4 pt-4 lg:px-6" data-testid="accounts-tabs">
        {[['daftar', 'Daftar Toko'], ['assign', 'Assign Staf']].map(([v, l]) => (
          <button key={v} type="button" onClick={() => setTab(v)}
            data-testid={`accounts-tab-${v}`}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold border ${tab === v
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-background text-foreground border-border hover:bg-muted/50'}`}>
            {l}
          </button>
        ))}
      </div>
      {tab === 'daftar' ? (
        <AccountManagementBase {...props} />
      ) : (
        <div className="px-4 pb-6 lg:px-6">
          <AccountAssignView token={props.token} />
        </div>
      )}
    </div>
  );
}
