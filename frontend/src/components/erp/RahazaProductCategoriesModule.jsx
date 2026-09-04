/**
 * RahazaProductCategoriesModule — F2 · MASTER KATEGORI PRODUK (keputusan K-2).
 *
 * Kenapa layar ini ada: kategori dipakai untuk **filter & grouping** di katalog
 * marketing, tetapi dulu nilainya teks bebas tanpa validasi dan ada 4 kosakata
 * berbeda antar-modul. Satu master + `category_id` membuat grouping bisa dipercaya.
 *
 * Keputusan K-1A: setiap kategori punya **Prefix SKU**; kode produk dibuat
 * OTOMATIS dari prefix itu (mis. `VST-0001`). Format SKU varian tidak diubah,
 * jadi hasilnya `VST-0001-NVY-M`.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, Edit2, Ban, RotateCcw, Tags, Info, PackageSearch } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import Modal from './Modal';
import { DataTable } from './DataTableV2';
import { PageHeader } from './moduleAtoms';
import { toast } from 'sonner';

const EMPTY_FORM = { code: '', name: '', sku_prefix: '', order_seq: 500, description: '' };

export default function RahazaProductCategoriesModule({ token }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showInactive, setShowInactive] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token],
  );

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(
        `/api/rahaza/product-categories?with_usage=true&include_inactive=${showInactive}`,
        { headers },
      );
      if (r.ok) {
        const d = await r.json();
        setRows(d.categories || []);
      } else {
        toast.error('Gagal memuat kategori produk');
      }
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, showInactive]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const openCreate = () => { setEditing(null); setForm(EMPTY_FORM); setModalOpen(true); };
  const openEdit = (row) => {
    setEditing(row);
    setForm({
      code: row.code || '', name: row.name || '', sku_prefix: row.sku_prefix || '',
      order_seq: row.order_seq ?? 500, description: row.description || '',
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) { toast.error('Nama kategori wajib diisi'); return; }
    if (!editing && !form.sku_prefix.trim()) { toast.error('Prefix SKU wajib diisi'); return; }
    setSaving(true);
    try {
      const url = editing
        ? `/api/rahaza/product-categories/${editing.id}`
        : '/api/rahaza/product-categories';
      const body = editing
        ? { name: form.name, sku_prefix: form.sku_prefix, order_seq: Number(form.order_seq) || 500, description: form.description }
        : { ...form, order_seq: Number(form.order_seq) || 500 };
      const r = await fetch(url, { method: editing ? 'PUT' : 'POST', headers, body: JSON.stringify(body) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { toast.error(d.detail || `HTTP ${r.status}`); return; }
      toast.success(editing ? 'Kategori diperbarui' : 'Kategori dibuat');
      setModalOpen(false);
      fetchRows();
    } finally { setSaving(false); }
  };

  const handleDeactivate = async (row) => {
    if (!window.confirm(`Nonaktifkan kategori "${row.name}"?`)) return;
    const r = await fetch(`/api/rahaza/product-categories/${row.id}`, { method: 'DELETE', headers });
    const d = await r.json().catch(() => ({}));
    if (r.ok) { toast.success('Kategori dinonaktifkan'); fetchRows(); }
    else toast.error(d.detail || 'Gagal menonaktifkan');
  };

  const handleReactivate = async (row) => {
    const r = await fetch(`/api/rahaza/product-categories/${row.id}`, {
      method: 'PUT', headers, body: JSON.stringify({ active: true }),
    });
    if (r.ok) { toast.success('Kategori diaktifkan kembali'); fetchRows(); }
    else toast.error('Gagal mengaktifkan');
  };

  const columns = [
    {
      key: 'sku_prefix', label: 'Prefix SKU', sortable: true,
      render: (row) => (
        <span className="font-mono text-xs px-2 py-1 rounded bg-primary/10 text-primary border border-primary/30"
          data-testid={`cat-prefix-${row.code}`}>
          {row.sku_prefix || '—'}
        </span>
      ),
    },
    { key: 'name', label: 'Nama Kategori', sortable: true },
    { key: 'code', label: 'Kode', sortable: true, render: (row) => <span className="font-mono text-xs text-muted-foreground">{row.code}</span> },
    {
      key: 'usage', label: 'Dipakai',
      render: (row) => {
        const u = row.usage || {};
        const total = u.total ?? 0;
        return (
          <div className="flex items-center gap-1.5 text-xs" data-testid={`cat-usage-${row.code}`}>
            <PackageSearch className="w-3.5 h-3.5 text-muted-foreground" />
            <span className={total > 0 ? 'text-foreground' : 'text-muted-foreground'}>
              {u.models ?? 0} produk · {u.fg ?? 0} barang jadi · {u.catalog_items ?? 0} item katalog
            </span>
          </div>
        );
      },
    },
    { key: 'order_seq', label: 'Urutan', sortable: true },
    {
      key: 'created_from', label: 'Asal',
      render: (row) => {
        const map = { seed: ['Bawaan', 'text-muted-foreground'], manual: ['Manual', 'text-foreground'], migrasi: ['Hasil migrasi', 'text-amber-700 dark:text-amber-300'] };
        const [label, cls] = map[row.created_from] || ['—', 'text-muted-foreground'];
        return <span className={`text-xs ${cls}`}>{label}</span>;
      },
    },
    {
      key: 'active', label: 'Status',
      render: (row) => (
        <span className={`text-xs px-2 py-0.5 rounded-full border ${row.active === false
          ? 'bg-red-500/10 border-red-400/40 text-red-700 dark:text-red-300'
          : 'bg-emerald-500/10 border-emerald-400/40 text-emerald-700 dark:text-emerald-300'}`}>
          {row.active === false ? 'Non-aktif' : 'Aktif'}
        </span>
      ),
    },
    {
      key: 'actions', label: 'Aksi',
      render: (row) => (
        <div className="flex items-center gap-1">
          <button onClick={(e) => { e.stopPropagation(); openEdit(row); }}
            className="p-1.5 rounded hover:bg-[var(--glass-bg-hover)] text-muted-foreground hover:text-foreground"
            title="Ubah" data-testid={`cat-edit-${row.code}`}>
            <Edit2 className="w-3.5 h-3.5" />
          </button>
          {row.active === false ? (
            <button onClick={(e) => { e.stopPropagation(); handleReactivate(row); }}
              className="p-1.5 rounded hover:bg-[var(--glass-bg-hover)] text-muted-foreground hover:text-emerald-600"
              title="Aktifkan kembali" data-testid={`cat-reactivate-${row.code}`}>
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          ) : (
            <button onClick={(e) => { e.stopPropagation(); handleDeactivate(row); }}
              className="p-1.5 rounded hover:bg-red-100 dark:hover:bg-red-500/20 text-muted-foreground hover:text-red-700 dark:hover:text-red-400"
              title="Nonaktifkan (ditolak bila masih dipakai)" data-testid={`cat-deactivate-${row.code}`}>
              <Ban className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4" data-testid="rahaza-product-categories-module">
      <PageHeader
        icon={Tags}
        title="Kategori Produk"
        subtitle="Master kategori (Vest, Rok, Jacket, …). Dipakai untuk filter & grouping katalog marketing, dan sebagai prefix kode produk otomatis."
        testId="product-categories-header"
        actions={(
          <>
            <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer select-none">
              <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)}
                data-testid="cat-show-inactive" />
              Tampilkan non-aktif
            </label>
            <Button onClick={openCreate} className="gap-1.5" data-testid="cat-create-btn">
              <Plus className="w-4 h-4" /> Tambah Kategori
            </Button>
          </>
        )}
      />

      <div className="flex items-start gap-2 text-[12px] text-foreground bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-lg p-3"
        data-testid="cat-explainer">
        <Info className="w-4 h-4 shrink-0 mt-0.5 text-primary" />
        <div className="space-y-1">
          <p><b>Prefix SKU</b> membuat kategori terlihat pada kode barang. Contoh: kategori <b>Vest</b>
            berprefix <span className="font-mono">VST</span> ⇒ produk baru otomatis berkode
            <span className="font-mono"> VST-0001</span>, dan SKU variannya menjadi
            <span className="font-mono"> VST-0001-NVY-M</span>.</p>
          <p className="text-muted-foreground">Kategori yang masih dipakai produk / barang jadi / item katalog
            <b> tidak bisa dinonaktifkan</b> — pindahkan dulu produknya.</p>
        </div>
      </div>

      <GlassCard>
        <DataTable tableId="rahaza-product-categories" columns={columns} rows={rows} loading={loading}
          emptyTitle="Belum ada kategori"
          emptyDescription="Klik Tambah Kategori untuk membuat kategori produk pertama."
          rowKey="id" />
      </GlassCard>

      {modalOpen && (
        <Modal onClose={() => setModalOpen(false)}
          title={editing ? `Ubah Kategori · ${editing.name}` : 'Tambah Kategori Produk'} size="md">
          <div className="space-y-3" data-testid="cat-form">
            <div>
              <label className="text-xs text-muted-foreground">Nama Kategori <span className="text-red-700 dark:text-red-400">*</span></label>
              <GlassInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Contoh: Vest" data-testid="cat-form-name" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground">Prefix SKU <span className="text-red-700 dark:text-red-400">*</span></label>
                <GlassInput value={form.sku_prefix}
                  onChange={(e) => setForm({ ...form, sku_prefix: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '') })}
                  placeholder="VST" maxLength={6} data-testid="cat-form-prefix" />
                <p className="text-[11px] text-muted-foreground mt-1">Harus unik. Dipakai membuat kode produk otomatis.</p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Urutan tampil</label>
                <GlassInput type="number" value={form.order_seq}
                  onChange={(e) => setForm({ ...form, order_seq: e.target.value })} data-testid="cat-form-order" />
              </div>
            </div>
            {!editing && (
              <div>
                <label className="text-xs text-muted-foreground">Kode (opsional — dibuat otomatis dari nama)</label>
                <GlassInput value={form.code}
                  onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                  placeholder="VEST" data-testid="cat-form-code" />
              </div>
            )}
            <div>
              <label className="text-xs text-muted-foreground">Keterangan</label>
              <GlassInput value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Opsional" data-testid="cat-form-description" />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-[var(--glass-border)]">
              <Button variant="ghost" onClick={() => setModalOpen(false)} data-testid="cat-form-cancel">Batal</Button>
              <Button onClick={handleSave} disabled={saving} data-testid="cat-form-save">
                {saving ? 'Menyimpan…' : 'Simpan'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
