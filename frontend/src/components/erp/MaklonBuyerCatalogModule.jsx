/**
 * MaklonBuyerCatalogModule — Phase M1
 * Master Artikel Buyer untuk Portal Maklon.
 *
 * Fitur:
 *  - List + filter by client, status, search
 *  - Create/Edit dialog (artikel_code, buyer_ref_code, product_name, price defaults, color/size options)
 *  - Toggle active/inactive
 *  - Soft-delete (discontinue)
 *
 * Catatan: pakai pattern style yang sama dengan MaklonClientManagement (Glass UI + Shadcn).
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  BookOpen,
  Plus,
  Edit2,
  RefreshCw,
  Search,
  Tag,
  Layers,
  Boxes,
  Ban,
  CheckCircle2,
  X,
  AlertCircle,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import { PageHeader } from './moduleAtoms';
import { EmptyState } from './EmptyState';
import MaklonBuyerCatalogDetailDialog from './MaklonBuyerCatalogDetailDialog';
import ProductionGuideDialog from './ProductionGuideDialog';
import { formatRupiah } from '@/lib/format';

const CATEGORIES = [
  'Dress',
  'Blouse',
  'Rok',
  'Celana',
  'Set/Setelan',
  'Baju Anak',
  'Hijab',
  'Aksesoris',
  'Lainnya',
];

const fmtRp = formatRupiah;

export default function MaklonBuyerCatalogModule({ token }) {
  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token]
  );

  const [items, setItems] = useState([]);
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filterClient, setFilterClient] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [search, setSearch] = useState('');
  const [dialog, setDialog] = useState(null); // null | { data?: row }
  const [detailCatalog, setDetailCatalog] = useState(null); // null | catalog row untuk detail dialog (M2)
  const [sopCatalog, setSopCatalog] = useState(null); // null | catalog row untuk editor Panduan Produksi (SOP)

  const fetchClients = useCallback(async () => {
    try {
      const r = await fetch('/api/dewi/maklon/clients', { headers });
      if (r.ok) setClients(await r.json());
    } catch (_e) {
      // silent
    }
  }, [headers]);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (filterClient !== 'all') qs.append('client_id', filterClient);
      if (filterStatus !== 'all') qs.append('status', filterStatus);
      if (search.trim()) qs.append('search', search.trim());
      const r = await fetch(`/api/dewi/maklon/buyer-catalog?${qs.toString()}`, { headers });
      if (r.ok) setItems(await r.json());
      else toast.error('Gagal memuat Buyer Catalog');
    } catch (_e) {
      toast.error('Gagal memuat Buyer Catalog');
    } finally {
      setLoading(false);
    }
  }, [headers, filterClient, filterStatus, search]);

  useEffect(() => {
    fetchClients();
  }, [fetchClients]);
  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const toggleItem = async (row) => {
    const r = await fetch(`/api/dewi/maklon/buyer-catalog/${row.id}/toggle`, {
      method: 'PUT',
      headers,
    });
    if (r.ok) {
      const d = await r.json();
      toast.success(`Status diubah → ${d.status}`);
      fetchItems();
    } else toast.error('Gagal mengubah status');
  };

  const discontinueItem = async (row) => {
    if (!window.confirm(`Set artikel "${row.artikel_code}" sebagai discontinued?`)) return;
    const r = await fetch(`/api/dewi/maklon/buyer-catalog/${row.id}`, {
      method: 'DELETE',
      headers,
    });
    if (r.ok) {
      toast.success('Artikel di-discontinue');
      fetchItems();
    } else toast.error('Gagal melakukan discontinue');
  };

  const stats = useMemo(
    () => ({
      total: items.length,
      active: items.filter((x) => x.status === 'active').length,
      inactive: items.filter((x) => x.status === 'inactive').length,
      discontinued: items.filter((x) => x.status === 'discontinued').length,
    }),
    [items]
  );

  return (
    <div className="p-6 space-y-6" data-testid="maklon-buyer-catalog-module">
      <PageHeader
        title="Buyer Catalog"
        description="Master artikel buyer Maklon — spesifikasi & harga default langsung dari klien"
        icon={BookOpen}
        actions={
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={fetchItems}
              variant="outline"
              className="gap-2"
              data-testid="buyer-catalog-refresh-btn"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </Button>
            <Button
              size="sm"
              onClick={() => setDialog({})}
              className="gap-1.5"
              data-testid="buyer-catalog-add-btn"
            >
              <Plus className="w-3.5 h-3.5" /> Tambah Artikel
            </Button>
          </div>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total', value: stats.total, icon: Layers, color: 'text-blue-400 bg-blue-500/10 border-blue-400/20' },
          { label: 'Aktif', value: stats.active, icon: CheckCircle2, color: 'text-green-400 bg-green-500/10 border-green-400/20' },
          { label: 'Non-Aktif', value: stats.inactive, icon: Ban, color: 'text-orange-400 bg-orange-500/10 border-orange-400/20' },
          { label: 'Discontinued', value: stats.discontinued, icon: AlertCircle, color: 'text-red-400 bg-red-500/10 border-red-400/20' },
        ].map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.04 * i }}
          >
            <GlassCard className={`p-4 border ${s.color.split(' ')[2]}`}>
              <div className={`w-8 h-8 rounded-lg border ${s.color} flex items-center justify-center mb-2`}>
                <s.icon className={`w-4 h-4 ${s.color.split(' ')[0]}`} />
              </div>
              <div className="text-2xl font-bold text-foreground" data-testid={`stat-${s.label.toLowerCase()}`}>
                {s.value}
              </div>
              <div className="text-xs text-foreground/50">{s.label}</div>
            </GlassCard>
          </motion.div>
        ))}
      </div>

      {/* Filters */}
      <GlassCard className="p-3">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="md:col-span-2">
            <Label className="text-xs mb-1 block">Cari Artikel / Ref / Nama</Label>
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground/40" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Misal: ZARA-W24, Dress Linen, BT-..."
                className="pl-8 h-9"
                data-testid="buyer-catalog-search-input"
              />
            </div>
          </div>
          <div>
            <Label className="text-xs mb-1 block">Buyer</Label>
            <Select value={filterClient} onValueChange={setFilterClient}>
              <SelectTrigger className="h-9" data-testid="buyer-catalog-filter-client">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Buyer</SelectItem>
                {clients.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs mb-1 block">Status</Label>
            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger className="h-9" data-testid="buyer-catalog-filter-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua</SelectItem>
                <SelectItem value="active">Aktif</SelectItem>
                <SelectItem value="inactive">Non-Aktif</SelectItem>
                <SelectItem value="discontinued">Discontinued</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </GlassCard>

      {/* Items List */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {loading ? (
          <div className="col-span-2 text-center py-10 text-foreground/40 text-sm">Memuat...</div>
        ) : items.length === 0 ? (
          <div className="col-span-2">
            <EmptyState
              icon={BookOpen}
              title="Belum ada artikel buyer"
              description="Buat entry pertama untuk menyimpan spesifikasi & harga default dari klien Maklon."
              action={
                <Button onClick={() => setDialog({})} className="gap-1.5">
                  <Plus className="w-3.5 h-3.5" /> Tambah Artikel
                </Button>
              }
            />
          </div>
        ) : (
          items.map((it) => (
            <GlassCard
              key={it.id}
              className={`p-4 border transition-all ${
                it.status === 'active'
                  ? 'border-border/60 hover:border-border'
                  : 'border-border/40 opacity-60'
              }`}
              data-testid={`buyer-catalog-row-${it.id}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="font-semibold text-foreground truncate">{it.product_name}</span>
                    {it.status === 'inactive' && (
                      <span className="text-[10px] bg-orange-500/15 text-orange-400 px-1.5 py-0.5 rounded border border-orange-400/25">
                        Non-Aktif
                      </span>
                    )}
                    {it.status === 'discontinued' && (
                      <span className="text-[10px] bg-red-500/15 text-red-400 px-1.5 py-0.5 rounded border border-red-400/25">
                        Discontinued
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mb-1 text-xs flex-wrap">
                    <span className="bg-violet-500/15 text-violet-300 px-1.5 py-0.5 rounded font-mono border border-violet-400/25">
                      {it.artikel_code}
                    </span>
                    {it.buyer_ref_code && (
                      <span className="bg-foreground/5 text-foreground/65 px-1.5 py-0.5 rounded font-mono">
                        ↳ {it.buyer_ref_code}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-foreground/55 mb-2">
                    <Tag className="w-3 h-3 inline mr-1" /> {it.client_name} · {it.category || 'Uncategorized'}
                  </div>
                  <div className="flex items-center gap-2 text-xs flex-wrap">
                    <span className="text-foreground/60">
                      CMT: <strong className="text-amber-400">{fmtRp(it.default_cmt_price)}</strong>
                    </span>
                    {it.default_selling_price > 0 && (
                      <>
                        <span className="text-foreground/30">•</span>
                        <span className="text-foreground/60">
                          Jual: <strong className="text-emerald-400">{fmtRp(it.default_selling_price)}</strong>
                        </span>
                      </>
                    )}
                  </div>
                  {(it.color_options?.length > 0 || it.size_options?.length > 0) && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {(it.color_options || []).slice(0, 4).map((c) => (
                        <span
                          key={c}
                          className="text-[10px] bg-blue-500/10 text-blue-300 px-1.5 py-0.5 rounded border border-blue-400/20"
                        >
                          {c}
                        </span>
                      ))}
                      {(it.size_options || []).slice(0, 6).map((s) => (
                        <span
                          key={s}
                          className="text-[10px] bg-muted/40 text-foreground/75 px-1.5 py-0.5 rounded border border-border/60"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                  {it.variants?.length > 0 && (
                    <div className="mt-1.5 text-[10px] text-violet-300 flex items-center gap-1">
                      <Boxes className="w-3 h-3" /> {it.variants.length} varian SKU
                    </div>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-xs h-7 border-violet-400/30 text-violet-300 hover:bg-violet-500/10"
                      onClick={() => setDetailCatalog(it)}
                      data-testid={`buyer-catalog-detail-${it.id}`}
                      title="Detail + Price History + BOM Templates"
                    >
                      Detail
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="w-7 h-7"
                      onClick={() => setDialog({ data: it })}
                      data-testid={`buyer-catalog-edit-${it.id}`}
                      title="Edit"
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="w-7 h-7 text-primary/70 hover:text-primary"
                      onClick={() => setSopCatalog(it)}
                      data-testid={`buyer-catalog-sop-${it.id}`}
                      title="Panduan Produksi (SOP)"
                    >
                      <BookOpen className="w-3.5 h-3.5" />
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-xs h-7"
                      onClick={() => toggleItem(it)}
                      data-testid={`buyer-catalog-toggle-${it.id}`}
                      disabled={it.status === 'discontinued'}
                    >
                      {it.status === 'active' ? 'Nonaktifkan' : 'Aktifkan'}
                    </Button>
                  </div>
                  {it.status !== 'discontinued' && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-xs h-7 text-red-400 hover:bg-red-500/10"
                      onClick={() => discontinueItem(it)}
                      data-testid={`buyer-catalog-discontinue-${it.id}`}
                    >
                      Discontinue
                    </Button>
                  )}
                  {it.total_qty_produced > 0 && (
                    <div className="text-[10px] text-foreground/40 mt-1">
                      {it.total_qty_produced.toLocaleString('id-ID')} pcs prod.
                    </div>
                  )}
                </div>
              </div>
            </GlassCard>
          ))
        )}
      </div>

      {/* Dialog */}
      {dialog !== null && (
        <BuyerCatalogDialog
          data={dialog?.data || null}
          clients={clients}
          headers={headers}
          onClose={() => setDialog(null)}
          onSuccess={() => {
            setDialog(null);
            fetchItems();
          }}
        />
      )}

      {/* Phase M2: Detail Dialog (Price History + BOM Templates) */}
      {detailCatalog && (
        <MaklonBuyerCatalogDetailDialog
          catalog={detailCatalog}
          headers={headers}
          onClose={() => setDetailCatalog(null)}
        />
      )}

      {/* Panduan Produksi (SOP) — dibaca Vendor CMT */}
      {sopCatalog && (
        <ProductionGuideDialog
          entity={sopCatalog}
          token={token}
          title={`Panduan Produksi · ${sopCatalog.artikel_code || ''} — ${sopCatalog.product_name || ''}`}
          endpoints={{
            sop: `/api/dewi/maklon/buyer-catalog/${sopCatalog.id}/sop`,
            sopImage: `/api/dewi/maklon/buyer-catalog/${sopCatalog.id}/sop-image`,
          }}
          onClose={() => setSopCatalog(null)}
          onUpdated={fetchItems}
        />
      )}
    </div>
  );
}

// ─── Dialog Create/Edit ──────────────────────────────────────────────────────
function BuyerCatalogDialog({ data, clients, headers, onClose, onSuccess }) {
  const isEdit = !!data;
  const [form, setForm] = useState({
    client_id: data?.client_id || '',
    artikel_code: data?.artikel_code || '',
    buyer_ref_code: data?.buyer_ref_code || '',
    product_name: data?.product_name || '',
    category: data?.category || '',
    season: data?.season || '',
    gender: data?.gender || '',
    default_cmt_price: data?.default_cmt_price ?? 0,
    default_selling_price: data?.default_selling_price ?? 0,
    color_options: Array.isArray(data?.color_options) ? data.color_options : [],
    size_options: Array.isArray(data?.size_options) ? data.size_options : [],
    description: data?.description || '',
    hero_image_url: data?.hero_image_url || '',
    status: data?.status || 'active',
  });
  const [saving, setSaving] = useState(false);

  // Fase 3: palet warna standar + master size untuk input varian/SKU yang jelas
  const [palette, setPalette] = useState([]);
  const [sizeMaster, setSizeMaster] = useState([]);
  const [customColor, setCustomColor] = useState('');
  const [customSize, setCustomSize] = useState('');
  const [autoGen, setAutoGen] = useState(!isEdit);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [cRes, sRes] = await Promise.all([
          fetch('/api/rahaza/colors', { headers }).then((r) => (r.ok ? r.json() : [])),
          fetch('/api/rahaza/sizes', { headers }).then((r) => (r.ok ? r.json() : [])),
        ]);
        if (!alive) return;
        setPalette((cRes || []).filter((c) => c.active !== false));
        setSizeMaster((sRes || []).filter((s) => s.active !== false));
      } catch (_e) {
        /* silent */
      }
    })();
    return () => { alive = false; };
  }, [headers]);

  const colorCodeFor = (name) => {
    const p = palette.find((c) => (c.name || '').toLowerCase() === String(name).trim().toLowerCase());
    if (p) return p.code;
    const alnum = String(name).replace(/[^A-Za-z0-9]/g, '').toUpperCase();
    return alnum.slice(0, 3) || 'X';
  };
  const sizeCodeFor = (s) => String(s).replace(/[^A-Za-z0-9]/g, '').toUpperCase();

  const toggleColor = (name) =>
    setForm((f) => ({
      ...f,
      color_options: f.color_options.includes(name)
        ? f.color_options.filter((x) => x !== name)
        : [...f.color_options, name],
    }));
  const toggleSize = (code) =>
    setForm((f) => ({
      ...f,
      size_options: f.size_options.includes(code)
        ? f.size_options.filter((x) => x !== code)
        : [...f.size_options, code],
    }));
  const addCustomColor = () => {
    const v = customColor.trim();
    if (v && !form.color_options.includes(v)) toggleColor(v);
    setCustomColor('');
  };
  const addCustomSize = () => {
    const v = customSize.trim().toUpperCase();
    if (v && !form.size_options.includes(v)) toggleSize(v);
    setCustomSize('');
  };

  const skuCount = form.color_options.length * form.size_options.length;
  const exampleSku =
    form.artikel_code && form.color_options[0] && form.size_options[0]
      ? [form.artikel_code.trim().toUpperCase(), colorCodeFor(form.color_options[0]), sizeCodeFor(form.size_options[0])].join('-')
      : null;

  const save = async () => {
    if (!form.client_id) {
      toast.error('Pilih buyer terlebih dahulu');
      return;
    }
    if (!form.artikel_code.trim()) {
      toast.error('Kode artikel wajib diisi');
      return;
    }
    if (!form.product_name.trim()) {
      toast.error('Nama produk wajib diisi');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        artikel_code: form.artikel_code.trim(),
        buyer_ref_code: form.buyer_ref_code.trim(),
        product_name: form.product_name.trim(),
        default_cmt_price: Number(form.default_cmt_price) || 0,
        default_selling_price: Number(form.default_selling_price) || 0,
        color_options: form.color_options,
        size_options: form.size_options,
      };
      // On edit, client_id can't change (avoid composite-unique collision); strip it.
      if (isEdit) delete payload.client_id;

      const url = isEdit
        ? `/api/dewi/maklon/buyer-catalog/${data.id}`
        : '/api/dewi/maklon/buyer-catalog';
      const r = await fetch(url, {
        method: isEdit ? 'PUT' : 'POST',
        headers,
        body: JSON.stringify(payload),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || 'Gagal menyimpan');
      }
      const saved = await r.json().catch(() => ({}));
      const catalogId = isEdit ? data.id : (saved.id || saved.item?.id);

      // Fase 3: langsung generate varian SKU bila diminta & opsi lengkap
      if (autoGen && catalogId && form.color_options.length && form.size_options.length) {
        try {
          const gr = await fetch(`/api/dewi/maklon/buyer-catalog/${catalogId}/variants/generate`, {
            method: 'POST',
            headers,
          });
          const gd = await gr.json().catch(() => ({}));
          toast.success(
            gr.ok
              ? `${isEdit ? 'Artikel diperbarui' : 'Artikel dibuat'} · ${gd.total || 0} varian SKU siap`
              : (isEdit ? 'Artikel berhasil diperbarui' : 'Artikel berhasil dibuat')
          );
        } catch (_e) {
          toast.success(isEdit ? 'Artikel berhasil diperbarui' : 'Artikel berhasil dibuat');
        }
      } else {
        toast.success(isEdit ? 'Artikel berhasil diperbarui' : 'Artikel berhasil dibuat');
      }
      onSuccess();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="buyer-catalog-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-violet-400" />
            {isEdit ? 'Edit Buyer Catalog' : 'Tambah Artikel Buyer'}
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
          <div>
            <Label className="text-xs">Buyer (Klien) *</Label>
            <Select
              value={form.client_id}
              onValueChange={(v) => setForm({ ...form, client_id: v })}
              disabled={isEdit}
            >
              <SelectTrigger className="h-9" data-testid="bc-form-client">
                <SelectValue placeholder="Pilih buyer" />
              </SelectTrigger>
              <SelectContent>
                {clients.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name} ({c.code})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {isEdit && (
              <p className="text-[10px] text-foreground/40 mt-1">
                Buyer tidak bisa diubah setelah artikel dibuat.
              </p>
            )}
          </div>
          <div>
            <Label className="text-xs">Status</Label>
            <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
              <SelectTrigger className="h-9" data-testid="bc-form-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Aktif</SelectItem>
                <SelectItem value="inactive">Non-Aktif</SelectItem>
                <SelectItem value="discontinued">Discontinued</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs">Kode Artikel (Internal) *</Label>
            <Input
              value={form.artikel_code}
              onChange={(e) => setForm({ ...form, artikel_code: e.target.value })}
              placeholder="MAK-ZARA-001"
              className="h-9 font-mono"
              data-testid="bc-form-artikel-code"
            />
          </div>
          <div>
            <Label className="text-xs">Kode Buyer (Referensi)</Label>
            <Input
              value={form.buyer_ref_code}
              onChange={(e) => setForm({ ...form, buyer_ref_code: e.target.value })}
              placeholder="Z-W24-001"
              className="h-9 font-mono"
              data-testid="bc-form-buyer-ref"
            />
          </div>

          <div className="md:col-span-2">
            <Label className="text-xs">Nama Produk *</Label>
            <Input
              value={form.product_name}
              onChange={(e) => setForm({ ...form, product_name: e.target.value })}
              placeholder="Dress Linen Premium"
              className="h-9"
              data-testid="bc-form-product-name"
            />
          </div>

          <div>
            <Label className="text-xs">Kategori</Label>
            <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
              <SelectTrigger className="h-9" data-testid="bc-form-category">
                <SelectValue placeholder="Pilih kategori" />
              </SelectTrigger>
              <SelectContent>
                {CATEGORIES.map((c) => (
                  <SelectItem key={c} value={c}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Season</Label>
              <Input
                value={form.season}
                onChange={(e) => setForm({ ...form, season: e.target.value })}
                placeholder="SS24, FW24..."
                className="h-9"
              />
            </div>
            <div>
              <Label className="text-xs">Gender</Label>
              <Input
                value={form.gender}
                onChange={(e) => setForm({ ...form, gender: e.target.value })}
                placeholder="Women / Men / Unisex"
                className="h-9"
              />
            </div>
          </div>

          <div>
            <Label className="text-xs">Harga CMT Default (Rp) *</Label>
            <Input
              type="number"
              min={0}
              value={form.default_cmt_price}
              onChange={(e) => setForm({ ...form, default_cmt_price: e.target.value })}
              className="h-9"
              data-testid="bc-form-default-cmt-price"
            />
            <p className="text-[10px] text-foreground/40 mt-1">Bisa di-override saat buat PO.</p>
          </div>
          <div>
            <Label className="text-xs">Harga Jual Default (Rp)</Label>
            <Input
              type="number"
              min={0}
              value={form.default_selling_price}
              onChange={(e) => setForm({ ...form, default_selling_price: e.target.value })}
              className="h-9"
              data-testid="bc-form-default-selling-price"
            />
          </div>

          <div className="md:col-span-2 space-y-3 rounded-lg border border-border/60 bg-foreground/[0.02] p-3">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground/85">
              <Boxes className="w-3.5 h-3.5 text-violet-400" /> Varian &amp; SKU
            </div>

            {/* Opsi Warna — dari palet standar (kode konsisten utk SKU) */}
            <div>
              <Label className="text-xs mb-1 block">Opsi Warna (pilih dari palet standar)</Label>
              <div className="flex flex-wrap gap-1.5" data-testid="bc-form-color-palette">
                {palette.map((c) => {
                  const sel = form.color_options.includes(c.name);
                  return (
                    <button
                      type="button"
                      key={c.id}
                      onClick={() => toggleColor(c.name)}
                      data-testid={`bc-color-chip-${c.code}`}
                      className={`flex items-center gap-1.5 px-2 py-1 rounded-full border text-xs transition-colors ${
                        sel
                          ? 'bg-violet-500/15 border-violet-400/40 text-foreground'
                          : 'border-border/60 text-foreground/65 hover:bg-foreground/5'
                      }`}
                    >
                      <span className="w-3 h-3 rounded-full border border-border/60" style={{ backgroundColor: c.hex }} />
                      {c.name}
                      <span className="text-[9px] text-foreground/40 font-mono">{c.code}</span>
                    </button>
                  );
                })}
              </div>
              {form.color_options.filter((n) => !palette.some((p) => p.name === n)).length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {form.color_options
                    .filter((n) => !palette.some((p) => p.name === n))
                    .map((n) => (
                      <span
                        key={n}
                        className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-400/30 text-amber-300 text-[11px]"
                      >
                        {n}
                        <button type="button" onClick={() => toggleColor(n)}>
                          <X className="w-2.5 h-2.5" />
                        </button>
                      </span>
                    ))}
                </div>
              )}
              <div className="flex items-center gap-1.5 mt-1.5">
                <Input
                  value={customColor}
                  onChange={(e) => setCustomColor(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      addCustomColor();
                    }
                  }}
                  placeholder="Warna lain (opsional)"
                  className="h-8 text-xs w-44"
                  data-testid="bc-form-color-custom"
                />
                <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={addCustomColor}>
                  + Tambah
                </Button>
              </div>
            </div>

            {/* Opsi Ukuran — dari master size */}
            <div>
              <Label className="text-xs mb-1 block">Opsi Ukuran (dari master size)</Label>
              <div className="flex flex-wrap gap-1.5" data-testid="bc-form-size-palette">
                {sizeMaster.map((s) => {
                  const sel = form.size_options.includes(s.code);
                  return (
                    <button
                      type="button"
                      key={s.id}
                      onClick={() => toggleSize(s.code)}
                      data-testid={`bc-size-chip-${s.code}`}
                      className={`px-2.5 py-1 rounded-md border text-xs font-mono transition-colors ${
                        sel
                          ? 'bg-violet-500/15 border-violet-400/40 text-foreground'
                          : 'border-border/60 text-foreground/65 hover:bg-foreground/5'
                      }`}
                    >
                      {s.code}
                    </button>
                  );
                })}
                {form.size_options
                  .filter((c) => !sizeMaster.some((s) => s.code === c))
                  .map((c) => (
                    <span
                      key={c}
                      className="flex items-center gap-1 px-2 py-1 rounded-md bg-amber-500/10 border border-amber-400/30 text-amber-300 text-xs font-mono"
                    >
                      {c}
                      <button type="button" onClick={() => toggleSize(c)}>
                        <X className="w-2.5 h-2.5" />
                      </button>
                    </span>
                  ))}
              </div>
              <div className="flex items-center gap-1.5 mt-1.5">
                <Input
                  value={customSize}
                  onChange={(e) => setCustomSize(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      addCustomSize();
                    }
                  }}
                  placeholder="Size lain (opsional)"
                  className="h-8 text-xs w-32"
                  data-testid="bc-form-size-custom"
                />
                <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={addCustomSize}>
                  + Tambah
                </Button>
              </div>
            </div>

            {/* SKU preview */}
            <div
              className="rounded-md bg-violet-500/[0.06] border border-violet-400/20 p-2.5 text-xs"
              data-testid="bc-form-sku-preview"
            >
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="text-foreground/75">
                  Akan terbentuk <strong className="text-violet-300">{skuCount}</strong> varian SKU
                  <span className="text-foreground/45"> (Warna × Ukuran)</span>.
                </div>
                {exampleSku && (
                  <div className="text-foreground/60">
                    Contoh SKU: <span className="font-mono text-violet-300">{exampleSku}</span>
                  </div>
                )}
              </div>
              <div className="text-[10px] text-foreground/45 mt-1">
                Format SKU: <span className="font-mono">KODEARTIKEL-KODEWARNA-SIZE</span>. Kode referensi buyer per
                varian bisa diisi nanti di tab <strong>Varian</strong>.
              </div>
              <label className="flex items-center gap-2 mt-2 cursor-pointer text-foreground/75">
                <input
                  type="checkbox"
                  checked={autoGen}
                  onChange={(e) => setAutoGen(e.target.checked)}
                  className="accent-violet-500"
                  data-testid="bc-form-autogen"
                />
                Langsung buat varian SKU setelah simpan
              </label>
            </div>
          </div>

          <div className="md:col-span-2">
            <Label className="text-xs">Foto Hero (URL)</Label>
            <Input
              value={form.hero_image_url}
              onChange={(e) => setForm({ ...form, hero_image_url: e.target.value })}
              placeholder="https://..."
              className="h-9"
            />
          </div>
          <div className="md:col-span-2">
            <Label className="text-xs">Deskripsi / Spek dari Buyer</Label>
            <Textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Material, finishing, packaging, dll dari buyer"
              rows={3}
              data-testid="bc-form-description"
            />
          </div>
        </div>

        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose} disabled={saving} data-testid="bc-form-cancel">
            <X className="w-3.5 h-3.5 mr-1" /> Batal
          </Button>
          <Button onClick={save} disabled={saving} data-testid="bc-form-save">
            {saving ? 'Menyimpan...' : isEdit ? 'Simpan Perubahan' : 'Buat Artikel'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
