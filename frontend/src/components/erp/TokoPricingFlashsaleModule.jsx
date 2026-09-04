import { useState, useEffect, useCallback, useMemo } from 'react';
import { Zap, Plus, Edit2, Trash2, ToggleLeft, ToggleRight, Tag, RefreshCw } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { PageHeader } from './moduleAtoms';
import { formatRupiah } from '@/lib/format';

const fmtIDR = formatRupiah;
const fmtDate = (d) => d ? new Date(d).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' }) : '-';

const STATUS_COLORS = {
  draft: 'bg-amber-500/15 text-amber-300 border-amber-400/25',
  active: 'bg-green-500/15 text-green-300 border-green-400/25',
  ended: 'bg-foreground/10 text-foreground/50 border-foreground/15',
  cancelled: 'bg-red-500/15 text-red-300 border-red-400/25',
};

const CHANNELS = ['shopee', 'tokopedia', 'tiktok_shop', 'website'];

const emptyFlashsale = {
  name: '',
  channel_code: 'shopee',
  start_at: '',
  end_at: '',
  notes: '',
  products: [],
};

const emptyProduct = { sku_code: '', name: '', original_price: 0, flashsale_price: 0, discount_pct: 0, quota: 0 };

export default function TokoPricingFlashsaleModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [flashsales, setFlashsales] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.set('status', statusFilter);
      const r = await fetch(`/api/dewi/toko/flashsales?${params}`, { headers });
      if (r.ok) setFlashsales(await r.json());
    } finally { setLoading(false); }
  }, [headers, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const save = async (form, id) => {
    setSaving(true);
    try {
      const body = {
        ...form,
        products: form.products.map(p => ({
          ...p,
          original_price: Number(p.original_price),
          flashsale_price: Number(p.flashsale_price),
          discount_pct: Number(p.discount_pct),
          quota: Number(p.quota),
        })),
      };
      const url = id ? `/api/dewi/toko/flashsales/${id}` : '/api/dewi/toko/flashsales';
      const method = id ? 'PUT' : 'POST';
      const r = await fetch(url, { method, headers, body: JSON.stringify(body) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal');
      toast.success(id ? 'Flashsale diperbarui' : 'Flashsale dibuat');
      setEditing(null);
      load();
    } catch (e) { toast.error(e.message); }
    finally { setSaving(false); }
  };

  const toggle = async (fs) => {
    const r = await fetch(`/api/dewi/toko/flashsales/${fs.id}/activate`, { method: 'POST', headers });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal'); return; }
    toast.success(d.message);
    load();
  };

  const remove = async (fs) => {
    if (!window.confirm(`Hapus flashsale "${fs.name}"?`)) return;
    const r = await fetch(`/api/dewi/toko/flashsales/${fs.id}`, { method: 'DELETE', headers });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal'); return; }
    toast.success('Dihapus');
    load();
  };

  const updateProduct = (idx, field, val) => {
    const products = [...(editing?.products || [])];
    products[idx] = { ...products[idx], [field]: val };
    // Auto-calc discount_pct
    if (field === 'flashsale_price' || field === 'original_price') {
      const op = Number(field === 'original_price' ? val : products[idx].original_price);
      const fp = Number(field === 'flashsale_price' ? val : products[idx].flashsale_price);
      if (op > 0) products[idx].discount_pct = Math.round(((op - fp) / op) * 100);
    }
    setEditing(e => ({ ...e, products }));
  };

  return (
    <div className="p-6 space-y-6" data-testid="toko-pricing-module">
      <PageHeader
        title="Harga & Flashsale"
        description="Atur harga promosi, flashsale per channel marketplace, dan diskon produk"
        icon={Zap}
        actions={
          <Button size="sm" onClick={() => setEditing({ ...emptyFlashsale, products: [] })} className="gap-1.5" data-testid="btn-new-flashsale">
            <Plus className="w-3.5 h-3.5" /> Flashsale Baru
          </Button>
        }
      />

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        {['all', 'draft', 'active', 'ended'].map(s => (
          <button key={s} onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded-full text-xs border transition-colors ${
              statusFilter === s ? 'bg-primary/15 border-primary/30 text-primary' : 'border-foreground/15 text-foreground/60 hover:border-foreground/30'
            }`}>
            {s === 'all' ? 'Semua' : s === 'draft' ? 'Draft' : s === 'active' ? 'Aktif' : 'Selesai'}
          </button>
        ))}
        <Button variant="outline" size="sm" onClick={load} className="ml-auto gap-1">
          <RefreshCw className="w-3.5 h-3.5" />
        </Button>
      </div>

      {loading ? (
        <div className="text-center py-10 text-foreground/40">Memuat...</div>
      ) : flashsales.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <Zap className="w-10 h-10 mx-auto mb-3 text-foreground/25" />
          <p className="text-foreground/50 text-sm">Belum ada flashsale</p>
          <Button size="sm" className="mt-3" onClick={() => setEditing({ ...emptyFlashsale, products: [] })}>+ Buat Flashsale</Button>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {flashsales.map(fs => (
            <GlassCard key={fs.id} className="p-4" data-testid={`flashsale-row-${fs.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold">{fs.name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_COLORS[fs.status]}`}>{fs.status}</span>
                    <span className="text-xs text-foreground/50 capitalize">{fs.channel_code}</span>
                  </div>
                  <div className="text-xs text-foreground/50 mt-1">
                    {fmtDate(fs.start_at)} &rarr; {fmtDate(fs.end_at)}
                  </div>
                  {fs.products?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {fs.products.slice(0, 4).map((p, i) => (
                        <span key={i} className="text-xs bg-foreground/5 border border-foreground/10 rounded px-2 py-0.5">
                          {p.sku_code} — {fmtIDR(p.flashsale_price)}
                          {p.discount_pct > 0 && <span className="text-red-400 ml-1">-{p.discount_pct}%</span>}
                        </span>
                      ))}
                      {fs.products.length > 4 && <span className="text-xs text-foreground/40">+{fs.products.length - 4} lagi</span>}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <Button size="sm" variant="outline" className="text-xs h-7" onClick={() => setEditing({ ...fs })} data-testid={`btn-edit-fs-${fs.id}`}>
                    <Edit2 className="w-3 h-3" />
                  </Button>
                  <Button size="sm" variant={fs.status === 'active' ? 'destructive' : 'default'} className="text-xs h-7" onClick={() => toggle(fs)} data-testid={`btn-toggle-fs-${fs.id}`}>
                    {fs.status === 'active' ? <ToggleRight className="w-3.5 h-3.5" /> : <ToggleLeft className="w-3.5 h-3.5" />}
                    {fs.status === 'active' ? 'Nonaktif' : 'Aktifkan'}
                  </Button>
                  <Button size="sm" variant="ghost" className="text-xs h-7 text-red-400 hover:text-red-300" onClick={() => remove(fs)} data-testid={`btn-delete-fs-${fs.id}`}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Edit/Create Dialog */}
      {editing && (
        <Dialog open={!!editing} onOpenChange={() => setEditing(null)}>
          <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="dialog-flashsale">
            <DialogHeader><DialogTitle>{editing.id ? 'Edit Flashsale' : 'Flashsale Baru'}</DialogTitle></DialogHeader>
            <div className="space-y-4 py-2">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <Label className="text-xs">Nama Flashsale *</Label>
                  <Input className="mt-1" placeholder="Flash Sale Lebaran 2026" value={editing.name} onChange={e => setEditing(d => ({ ...d, name: e.target.value }))} data-testid="input-fs-name" />
                </div>
                <div>
                  <Label className="text-xs">Channel</Label>
                  <Select value={editing.channel_code} onValueChange={v => setEditing(d => ({ ...d, channel_code: v }))}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>{CHANNELS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div />
                <div>
                  <Label className="text-xs">Mulai</Label>
                  <Input type="datetime-local" className="mt-1" value={editing.start_at?.slice(0, 16) || ''} onChange={e => setEditing(d => ({ ...d, start_at: e.target.value }))} data-testid="input-fs-start" />
                </div>
                <div>
                  <Label className="text-xs">Selesai</Label>
                  <Input type="datetime-local" className="mt-1" value={editing.end_at?.slice(0, 16) || ''} onChange={e => setEditing(d => ({ ...d, end_at: e.target.value }))} data-testid="input-fs-end" />
                </div>
              </div>

              {/* Products */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <Label className="text-xs">Produk Flashsale</Label>
                  <Button size="sm" variant="outline" className="text-xs h-6" onClick={() => setEditing(d => ({ ...d, products: [...(d.products || []), { ...emptyProduct }] }))}>+ Produk</Button>
                </div>
                {(editing.products || []).length === 0 ? (
                  <p className="text-xs text-foreground/40">Tambahkan produk yang akan diikutkan flashsale</p>
                ) : (
                  <div className="space-y-2">
                    {editing.products.map((p, idx) => (
                      <div key={idx} className="grid grid-cols-6 gap-2 items-center p-2 rounded-lg bg-foreground/[0.03] border border-foreground/10">
                        <Input placeholder="SKU" className="col-span-1 text-xs" value={p.sku_code} onChange={e => updateProduct(idx, 'sku_code', e.target.value.toUpperCase())} />
                        <Input placeholder="Nama" className="col-span-2 text-xs" value={p.name} onChange={e => updateProduct(idx, 'name', e.target.value)} />
                        <Input placeholder="Harga asli" type="number" className="text-xs" value={p.original_price} onChange={e => updateProduct(idx, 'original_price', e.target.value)} />
                        <Input placeholder="Harga flash" type="number" className="text-xs" value={p.flashsale_price} onChange={e => updateProduct(idx, 'flashsale_price', e.target.value)} />
                        <div className="flex items-center gap-1">
                          <span className="text-xs text-red-400 font-semibold whitespace-nowrap">-{p.discount_pct || 0}%</span>
                          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setEditing(d => ({ ...d, products: d.products.filter((_, i) => i !== idx) }))}>
                            <Trash2 className="w-3 h-3 text-red-400" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <Label className="text-xs">Catatan</Label>
                <Textarea className="mt-1" rows={2} value={editing.notes || ''} onChange={e => setEditing(d => ({ ...d, notes: e.target.value }))} />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditing(null)}>Batal</Button>
              <Button onClick={() => save(editing, editing.id)} disabled={saving || !editing.name} data-testid="btn-save-flashsale">
                {saving ? 'Menyimpan...' : editing.id ? 'Perbarui' : 'Buat Flashsale'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
