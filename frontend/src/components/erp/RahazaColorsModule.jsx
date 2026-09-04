import { useState, useEffect, useCallback, useMemo } from 'react';
import { Plus, Edit2, Trash2, Palette } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import Modal from './Modal';
import { toast } from 'sonner';

const DEFAULT_FORM = { code: '', name: '', hex: '#3B82F6', order_seq: 50, active: true };

/* Master Warna (DINAMIS) — Fase 2 Master Product Refactor.
   Palet techpack ter-seed otomatis; user bisa tambah/edit/hapus.
   `code` (singkatan) dipakai di SKU varian: KODE-WARNA-SIZE. */
export function RahazaColorsModule({ token }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/rahaza/colors?include_inactive=true', { headers });
      if (r.ok) setRows(await r.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const openCreate = () => { setEditing(null); setForm(DEFAULT_FORM); setModalOpen(true); };
  const openEdit = (row) => {
    setEditing(row);
    setForm({
      code: row.code || '', name: row.name || '', hex: row.hex || '#CCCCCC',
      order_seq: row.order_seq ?? 50, active: row.active !== false,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.name) { toast.error('Nama warna wajib diisi'); return; }
    setSaving(true);
    try {
      const url = editing ? `/api/rahaza/colors/${editing.id}` : '/api/rahaza/colors';
      const method = editing ? 'PUT' : 'POST';
      const r = await fetch(url, { method, headers, body: JSON.stringify(form) });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        toast.error(err.detail || `Gagal (HTTP ${r.status})`);
        return;
      }
      toast.success(editing ? 'Warna diperbarui' : 'Warna ditambahkan');
      setModalOpen(false);
      fetchRows();
    } finally { setSaving(false); }
  };

  const handleDelete = async (row) => {
    if (!window.confirm(`Nonaktifkan warna ${row.name} (${row.code})?`)) return;
    const r = await fetch(`/api/rahaza/colors/${row.id}`, { method: 'DELETE', headers });
    if (r.ok) { toast.success('Warna dinonaktifkan'); fetchRows(); }
    else {
      const err = await r.json().catch(() => ({}));
      toast.error(err.detail || 'Gagal menonaktifkan');
    }
  };

  return (
    <div className="space-y-4" data-testid="rahaza-colors-module">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Palette className="w-4 h-4 text-primary" /> Master Warna
          </h2>
          <p className="text-muted-foreground text-sm mt-1">
            Palet warna (gaya techpack). Kode singkatan dipakai di SKU varian:
            <span className="font-mono text-foreground"> KODE-WARNA-SIZE</span>.
          </p>
        </div>
        <Button onClick={openCreate} className="gap-1.5" data-testid="color-create-btn">
          <Plus className="w-4 h-4" /> Tambah Warna
        </Button>
      </div>

      <GlassCard className="p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">Warna</TableHead>
                <TableHead>Kode</TableHead>
                <TableHead>Nama</TableHead>
                <TableHead>Hex</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">Memuat...</TableCell></TableRow>
              ) : rows.length === 0 ? (
                <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">Belum ada warna.</TableCell></TableRow>
              ) : rows.map(row => (
                <TableRow key={row.id} data-testid={`color-row-${row.code}`} className={row.active === false ? 'opacity-50' : ''}>
                  <TableCell>
                    <span
                      className="inline-block w-7 h-7 rounded-md border border-[var(--glass-border)]"
                      style={{ backgroundColor: row.hex || '#ccc' }}
                      title={row.hex}
                    />
                  </TableCell>
                  <TableCell className="font-mono font-semibold text-foreground">{row.code}</TableCell>
                  <TableCell className="text-foreground">{row.name}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{row.hex}</TableCell>
                  <TableCell>
                    {row.active === false
                      ? <Badge variant="outline" className="text-muted-foreground">Nonaktif</Badge>
                      : <Badge variant="default">Aktif</Badge>}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex items-center gap-1">
                      <button
                        onClick={() => openEdit(row)}
                        className="p-1.5 rounded hover:bg-[var(--glass-bg-hover)] text-muted-foreground hover:text-foreground"
                        title="Edit" data-testid={`color-edit-${row.code}`}
                      ><Edit2 className="w-3.5 h-3.5" /></button>
                      {row.active !== false && (
                        <button
                          onClick={() => handleDelete(row)}
                          className="p-1.5 rounded hover:bg-red-500/15 text-muted-foreground hover:text-red-400"
                          title="Nonaktifkan" data-testid={`color-delete-${row.code}`}
                        ><Trash2 className="w-3.5 h-3.5" /></button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </GlassCard>

      {modalOpen && (
        <Modal onClose={() => setModalOpen(false)} title={editing ? 'Edit Warna' : 'Tambah Warna'} size="sm">
          <div className="space-y-3" data-testid="color-form">
            <div>
              <label className="text-xs text-muted-foreground">Nama Warna <span className="text-red-400">*</span></label>
              <GlassInput value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="cth: Merah Marun" data-testid="color-form-name" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground">Kode (singkatan) <span className="text-red-400">*</span></label>
                <GlassInput value={form.code} onChange={e => setForm({ ...form, code: e.target.value.toUpperCase() })}
                  placeholder="cth: MRN" maxLength={6} data-testid="color-form-code" />
                <p className="text-[10px] text-muted-foreground mt-1">Dipakai di SKU. Kosongkan = auto 3 huruf.</p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Warna (hex)</label>
                <div className="flex items-center gap-2 mt-0.5">
                  <input
                    type="color"
                    value={form.hex}
                    onChange={e => setForm({ ...form, hex: e.target.value })}
                    className="w-10 h-9 rounded-md border border-[var(--glass-border)] bg-transparent cursor-pointer p-0.5"
                    data-testid="color-form-hex-picker"
                  />
                  <GlassInput value={form.hex} onChange={e => setForm({ ...form, hex: e.target.value })}
                    placeholder="#RRGGBB" data-testid="color-form-hex" />
                </div>
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Urutan</label>
              <GlassInput type="number" value={form.order_seq}
                onChange={e => setForm({ ...form, order_seq: parseInt(e.target.value) || 50 })}
                data-testid="color-form-order" />
            </div>
            {editing && (
              <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                <input type="checkbox" checked={form.active}
                  onChange={e => setForm({ ...form, active: e.target.checked })}
                  data-testid="color-form-active" />
                Aktif
              </label>
            )}
            <div className="flex justify-end gap-2 pt-2 border-t border-[var(--glass-border)]">
              <Button variant="ghost" onClick={() => setModalOpen(false)} data-testid="color-form-cancel">Batal</Button>
              <Button onClick={handleSave} disabled={saving} data-testid="color-form-save">
                {saving ? 'Menyimpan...' : 'Simpan'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

export default RahazaColorsModule;
