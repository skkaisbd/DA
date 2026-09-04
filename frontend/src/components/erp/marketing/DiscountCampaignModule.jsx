import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Tag, Plus, Pencil, Trash2, RefreshCw, Loader2,
  CheckCircle2, Clock, XCircle, AlertTriangle, Filter, X, TrendingDown
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { useMarketingAccounts, getPlatformIcon } from '@/hooks/useMarketingAccounts';
import axios from 'axios';
import { MarketingAccountSelect } from './pickers/MarketingPickers';
// F10 (sesi #10) — kampanye diskon = biaya; daftarnya wajib bisa diunduh untuk rapat.
import ExportCsvButton from '@/components/ui/export-csv-button';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;

const PLATFORM_ICONS = { shopee: '🛒', tiktok: '🎵', tokopedia: '🟢', instagram: '📷', semua_platform: '🌐' };
const STATUS_CONFIG = {
  active:   { label: 'Aktif',    color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', icon: CheckCircle2 },
  upcoming: { label: 'Upcoming', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300', icon: Clock },
  expired:  { label: 'Expired',  color: 'bg-muted text-muted-foreground dark:bg-gray-800 dark:text-gray-400', icon: XCircle },
  draft:    { label: 'Draft',    color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300', icon: AlertTriangle },
};

function StatusBadge({ status }) {
  const c = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${c.color}`}>
      <Icon size={10} />{c.label}
    </span>
  );
}

const fmtRp = (n) => n ? formatRupiah(n) : '-';
function fmt(n)   { return new Intl.NumberFormat('id-ID').format(n || 0); }

function KPICard({ label, value, sub, color, bg, icon: Icon }) {
  return (
    <Card className={`${bg} border-0`}>
      <CardContent className="p-4 flex items-center gap-3">
        <div className="p-2 rounded-lg bg-background/60 dark:bg-black/20">
          <Icon size={20} className={color} />
        </div>
        <div>
          <p className="text-xl font-bold leading-tight">{value}</p>
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

const EMPTY_FORM = {
  account_id: '', account_name: '', platform: 'shopee', name: '', discount_type: 'flash_sale',
  discount_value: '', discount_unit: 'persen', min_purchase: '', max_discount: '',
  start_date: '', end_date: '', description: '', product_scope: 'semua_produk'
};

const DISCOUNT_TYPE_LABELS = {
  flash_sale: 'Flash Sale', voucher: 'Voucher / Kupon', bundling: 'Bundling Produk',
  buy_x_get_y: 'Buy X Get Y', free_shipping: 'Gratis Ongkir',
  diskon_persen: 'Diskon %', cashback: 'Cashback', giveaway: 'Giveaway',
};

export default function DiscountCampaignModule({ token }) {
  const { toast } = useToast();
  const authH = useMemo(() => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);
  const { accounts, byId: accountById } = useMarketingAccounts(token);

  const [summary, setSummary]     = useState(null);
  const [items,   setItems]       = useState([]);
  const [pagination, setPagination] = useState(null);
  const [loading, setLoading]     = useState(true);

  const [filterStatus,  setFilterStatus]  = useState('');
  const [filterPlatform,setFilterPlatform]= useState('');
  // F14 — filter per TOKO memakai account_id (SSOT), bukan mencocokkan nama toko.
  const [filterAccountId, setFilterAccountId] = useState('');
  const [filterType,    setFilterType]    = useState('');
  const [search,        setSearch]        = useState('');
  const [page,          setPage]          = useState(1);

  const [showForm,    setShowForm]    = useState(false);
  const [editTarget,  setEditTarget]  = useState(null);
  const [form,        setForm]        = useState(EMPTY_FORM);
  const [formLoading, setFormLoading] = useState(false);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/marketing/discounts/summary`, { headers: authH });
      if (res.data.success) setSummary(res.data.data);
    } catch {}
  }, [authH]);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, page_size: 20 };
      if (filterStatus)   params.status = filterStatus;
      if (filterPlatform) params.platform = filterPlatform;
      if (filterAccountId) params.account_id = filterAccountId;
      if (filterType)     params.discount_type = filterType;
      if (search)         params.search = search;
      const res = await axios.get(`${API}/api/marketing/discounts`, { params, headers: authH });
      if (res.data.success) {
        setItems(res.data.data || []);
        setPagination(res.data.pagination);
      }
    } catch { toast({ title: 'Gagal load kampanye', variant: 'destructive' }); }
    finally { setLoading(false); }
  }, [page, filterStatus, filterPlatform, filterType, filterAccountId, search, authH, toast]);

  useEffect(() => { fetchSummary(); }, [fetchSummary]);
  useEffect(() => { fetchItems(); },   [fetchItems]);

  const openCreate = () => { setEditTarget(null); setForm(EMPTY_FORM); setShowForm(true); };
  const openEdit   = (item) => {
    setEditTarget(item);
    setForm({
      account_id: item.account_id || '',
      account_name: item.account_name || '', platform: item.platform || 'shopee',
      name: item.name || '', discount_type: item.discount_type || 'flash_sale',
      discount_value: item.discount_value ?? '', discount_unit: item.discount_unit || 'persen',
      min_purchase: item.min_purchase ?? '', max_discount: item.max_discount ?? '',
      start_date: item.start_date || '', end_date: item.end_date || '',
      description: item.description || '', product_scope: item.product_scope || 'semua_produk',
    });
    setShowForm(true);
  };

  // When account_id changes, auto-fill account_name & platform from master
  const handleAccountChange = (accountId) => {
    const acc = accountById[accountId];
    setForm(f => ({
      ...f,
      account_id: accountId,
      account_name: acc?.account_name || acc?.name || '',
      platform: acc?.platform || f.platform,
    }));
  };

  const handleSave = async () => {
    if (!form.account_id || !form.name || !form.start_date || !form.end_date) {
      toast({ title: 'Wajib pilih Akun, isi Nama Kampanye, dan tanggal', variant: 'destructive' }); return;
    }
    setFormLoading(true);
    try {
      const payload = {
        ...form,
        discount_value: parseFloat(form.discount_value) || 0,
        min_purchase:   parseFloat(form.min_purchase)   || 0,
        max_discount:   parseFloat(form.max_discount)   || 0,
      };
      if (editTarget) {
        await axios.put(`${API}/api/marketing/discounts/${editTarget.id}`, payload, { headers: authH });
        toast({ title: 'Kampanye diperbarui' });
      } else {
        await axios.post(`${API}/api/marketing/discounts`, payload, { headers: authH });
        toast({ title: 'Kampanye berhasil ditambahkan' });
      }
      setShowForm(false);
      fetchSummary();
      fetchItems();
    } catch { toast({ title: 'Gagal menyimpan', variant: 'destructive' }); }
    finally { setFormLoading(false); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus kampanye ini?')) return;
    try {
      await axios.delete(`${API}/api/marketing/discounts/${id}`, { headers: authH });
      toast({ title: 'Kampanye dihapus' });
      fetchSummary();
      fetchItems();
    } catch { toast({ title: 'Gagal hapus', variant: 'destructive' }); }
  };

  const kpis = [
    { label: 'Total Kampanye', value: fmt(summary?.total),         sub: 'Semua kampanye',            color: 'text-indigo-600',  bg: 'bg-indigo-50 dark:bg-indigo-900/20',   icon: Tag },
    { label: 'Aktif Sekarang', value: fmt(summary?.active),        sub: 'Sedang berjalan',           color: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-900/20', icon: CheckCircle2 },
    { label: 'Akan Datang',    value: fmt(summary?.upcoming),       sub: 'Belum mulai',               color: 'text-blue-600',    bg: 'bg-blue-50 dark:bg-blue-900/20',       icon: Clock },
    { label: 'Habis 3 Hari',   value: fmt(summary?.expiring_soon), sub: 'Segera berakhir',           color: 'text-amber-600',   bg: 'bg-amber-50 dark:bg-amber-900/20',    icon: AlertTriangle },
  ];

  return (
    <div className="min-h-screen bg-background p-4 md:p-6" data-testid="discount-campaign-dashboard">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Discount Campaign Manager</h1>
          <p className="text-sm text-muted-foreground">Kelola semua kampanye promo multi-platform</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { fetchSummary(); fetchItems(); }}>
            <RefreshCw size={14} className="mr-1" />Refresh
          </Button>
          <Button size="sm" onClick={openCreate} data-testid="btn-add-discount">
            <Plus size={14} className="mr-1" />Buat Kampanye
          </Button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        {kpis.map(k => <KPICard key={k.label} {...k} />)}
      </div>

      {/* Expiring Soon Alert */}
      {summary?.expiring_soon > 0 && (
        <div className="mb-4 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-700 dark:text-amber-300 text-sm">
          <AlertTriangle size={16} />
          <strong>{summary.expiring_soon} kampanye</strong> akan berakhir dalam 3 hari! Perlu tindakan.
        </div>
      )}

      {/* Filters */}
      <Card className="mb-4">
        <CardContent className="p-3 flex flex-wrap gap-2 items-center">
          <Input
            className="h-8 text-xs w-48" placeholder="🔍 Cari nama kampanye..."
            value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
          />
          <Select value={filterStatus || 'all'} onValueChange={v => { setFilterStatus(v === 'all' ? '' : v); setPage(1); }}>
            <SelectTrigger className="w-32 h-8 text-xs"><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua Status</SelectItem>
              {Object.entries(STATUS_CONFIG).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <div className="w-52">
            <MarketingAccountSelect token={token} value={filterAccountId}
              onChange={(v) => { setFilterAccountId(v); setPage(1); }} label=""
              includeAll allLabel="Semua Toko" required={false}
              testId="discount-filter-account" />
          </div>
          <Select value={filterPlatform || 'all'} onValueChange={v => { setFilterPlatform(v === 'all' ? '' : v); setPage(1); }}>
            <SelectTrigger className="w-36 h-8 text-xs"><SelectValue placeholder="Platform" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua Platform</SelectItem>
              {Object.entries(PLATFORM_ICONS).map(([k, v]) => <SelectItem key={k} value={k}>{v} {k}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filterType || 'all'} onValueChange={v => { setFilterType(v === 'all' ? '' : v); setPage(1); }}>
            <SelectTrigger className="w-40 h-8 text-xs"><SelectValue placeholder="Jenis Diskon" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua Jenis</SelectItem>
              {Object.entries(DISCOUNT_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
          {(filterStatus || filterPlatform || filterType || search) && (
            <Button size="sm" variant="ghost" className="h-8 px-2" onClick={() => { setFilterStatus(''); setFilterPlatform(''); setFilterType(''); setFilterAccountId(''); setSearch(''); setPage(1); }}>
              <X size={12} className="mr-1" />Reset
            </Button>
          )}
          <ExportCsvButton
            filename="kampanye-diskon"
            testId="discount-export-csv"
            head={['Nama kampanye', 'Platform', 'Toko', 'Jenis', 'Nilai', 'Satuan',
              'Min. belanja', 'Cakupan produk', 'Mulai', 'Selesai', 'Sisa hari', 'Status']}
            rows={(items || []).map((it) => [it.name, it.platform, it.account_name,
              it.discount_type_label || it.discount_type, it.discount_value,
              it.discount_unit, it.min_purchase, it.product_scope,
              String(it.start_date || '').slice(0, 10), String(it.end_date || '').slice(0, 10),
              it.days_remaining, it.status])}
          />
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex justify-center py-16"><Loader2 size={28} className="animate-spin text-muted-foreground" /></div>
          ) : items.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <Tag size={40} className="mx-auto mb-3 opacity-30" />
              <p className="font-medium">Belum ada kampanye</p>
              <Button size="sm" className="mt-3" onClick={openCreate}><Plus size={12} className="mr-1" />Buat Kampanye</Button>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/40">
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase">Nama Kampanye</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase">Platform / Akun</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase">Jenis</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase">Nilai</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase">Periode</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase">Status</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-muted-foreground uppercase">Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item, i) => (
                      <tr key={item.id} className={`border-b last:border-0 hover:bg-muted/30 transition-colors ${i%2===0?'':'bg-muted/10'}`}>
                        <td className="px-4 py-3">
                          <div className="font-medium">{item.name}</div>
                          <div className="text-xs text-muted-foreground">{item.product_scope}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-medium">{PLATFORM_ICONS[item.platform] || '📌'} {item.platform}</div>
                          <div className="text-xs text-muted-foreground">{item.account_name}</div>
                        </td>
                        <td className="px-4 py-3 text-xs">{item.discount_type_label || DISCOUNT_TYPE_LABELS[item.discount_type] || item.discount_type}</td>
                        <td className="px-4 py-3">
                          {item.discount_value > 0 ? (
                            <span className="font-semibold text-emerald-600">
                              {item.discount_unit === 'persen' ? `${item.discount_value}%` :
                               item.discount_unit === 'nominal' ? fmtRp(item.discount_value) :
                               `${item.discount_value} unit`}
                            </span>
                          ) : <span className="text-muted-foreground">—</span>}
                          {item.min_purchase > 0 && <div className="text-xs text-muted-foreground">Min. {fmtRp(item.min_purchase)}</div>}
                        </td>
                        <td className="px-4 py-3 text-xs">
                          <div className="font-mono">{item.start_date}</div>
                          <div className="text-muted-foreground">s/d {item.end_date}</div>
                          {item.days_remaining !== null && item.days_remaining !== undefined && (
                            <div className={`text-xs font-medium mt-0.5 ${
                              item.days_remaining <= 3 ? 'text-red-500' :
                              item.days_remaining <= 7 ? 'text-amber-500' : 'text-emerald-500'
                            }`}>
                              {item.days_remaining >= 0 ? `${item.days_remaining} hari lagi` : `Berakhir ${Math.abs(item.days_remaining)} hari lalu`}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3"><StatusBadge status={item.status} /></td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-1">
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => openEdit(item)}>
                              <Pencil size={12} />
                            </Button>
                            <Button size="icon" variant="ghost" className="h-7 w-7 text-red-500 hover:text-red-600" onClick={() => handleDelete(item.id)}>
                              <Trash2 size={12} />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {pagination && pagination.total_pages > 1 && (
                <div className="flex items-center justify-between px-4 py-3 border-t">
                  <p className="text-xs text-muted-foreground">{pagination.total} kampanye</p>
                  <div className="flex gap-1">
                    <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>‹ Prev</Button>
                    <span className="px-3 py-1.5 text-xs">{page} / {pagination.total_pages}</span>
                    <Button size="sm" variant="outline" disabled={page >= pagination.total_pages} onClick={() => setPage(p => p + 1)}>Next ›</Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* FORM DIALOG */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editTarget ? 'Edit Kampanye' : 'Buat Kampanye Baru'}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 max-h-[60vh] overflow-y-auto pr-1">
            <div className="col-span-2">
              <Label>Nama Kampanye *</Label>
              <Input value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))}
                placeholder="Contoh: Flash Sale Harbolnas 12.12" className="mt-1" />
            </div>
            <div className="col-span-2">
              <Label>Akun / Toko Marketplace *</Label>
              <Select value={form.account_id || ''} onValueChange={handleAccountChange}>
                <SelectTrigger className="mt-1" data-testid="campaign-account-select">
                  <SelectValue placeholder={accounts.length === 0 ? 'Belum ada akun — buat di Manage Accounts' : 'Pilih akun...'} />
                </SelectTrigger>
                <SelectContent>
                  {accounts.length === 0 && (
                    <SelectItem value="empty" disabled>Belum ada akun aktif</SelectItem>
                  )}
                  {accounts.map(acc => (
                    <SelectItem key={acc.id} value={acc.id}>
                      {getPlatformIcon(acc.platform)} {acc.account_name} <span className="text-xs text-muted-foreground ml-1">({acc.platform})</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {form.account_id && (
                <p className="text-xs text-muted-foreground mt-1">
                  Platform: <strong>{form.platform}</strong> (otomatis dari akun terpilih)
                </p>
              )}
            </div>
            <div>
              <Label>Jenis Diskon</Label>
              <Select value={form.discount_type} onValueChange={v => setForm(f => ({...f, discount_type: v}))}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(DISCOUNT_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Satuan Nilai</Label>
              <Select value={form.discount_unit} onValueChange={v => setForm(f => ({...f, discount_unit: v}))}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="persen">Persen (%)</SelectItem>
                  <SelectItem value="nominal">Nominal (Rp)</SelectItem>
                  <SelectItem value="unit">Unit</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Nilai Diskon</Label>
              <Input type="number" min="0" value={form.discount_value} onChange={e => setForm(f => ({...f, discount_value: e.target.value}))}
                placeholder="0" className="mt-1" />
            </div>
            <div>
              <Label>Min. Pembelian (Rp)</Label>
              <Input type="number" min="0" value={form.min_purchase} onChange={e => setForm(f => ({...f, min_purchase: e.target.value}))}
                placeholder="0" className="mt-1" />
            </div>
            <div>
              <Label>Tanggal Mulai *</Label>
              <Input type="date" value={form.start_date} onChange={e => setForm(f => ({...f, start_date: e.target.value}))} className="mt-1" />
            </div>
            <div>
              <Label>Tanggal Berakhir *</Label>
              <Input type="date" value={form.end_date} onChange={e => setForm(f => ({...f, end_date: e.target.value}))} className="mt-1" />
            </div>
            <div className="col-span-2">
              <Label>Deskripsi</Label>
              <Textarea value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))}
                placeholder="Detail kampanye..." rows={2} className="mt-1" />
            </div>
          </div>
          <DialogFooter className="mt-2">
            <Button variant="outline" onClick={() => setShowForm(false)}>Batal</Button>
            <Button onClick={handleSave} disabled={formLoading}>
              {formLoading && <Loader2 size={14} className="mr-2 animate-spin" />}
              {editTarget ? 'Simpan Perubahan' : 'Buat Kampanye'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

