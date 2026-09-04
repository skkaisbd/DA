import { useState, useEffect } from 'react';
import { Plus, Search, Package } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { GlassInput } from '@/components/ui/glass';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { typeToCategory, categoryToStoredType, isKgLike } from '@/lib/itemTaxonomy';
import { readField, FIELD } from '@/lib/materialFields';  // FASE 6.6-B

/**
 * InlineMaterialPicker (Phase 7A Fase 1 — unified materials[])
 *
 * Pilih material dari master data (semua tipe) atau buat baru inline.
 * Dipakai pada editor BOM generik (satu daftar materials[]).
 *
 * Props:
 * - type: '' (semua) | 'yarn' | 'fabric' | 'accessory' | 'packaging' | 'other'  (filter awal opsional)
 * - categories: [{code,name}]  (master kategori material, untuk create dialog)
 * - token: JWT token
 * - onSelect: (material) => void
 */
const UNIT_OPTIONS = ['kg', 'gram', 'm', 'yard', 'pcs', 'lusin', 'set', 'pair', 'rol', 'karton', 'pak'];
// 3 kategori bisnis; komponen BOM = Bahan & Aksesoris.
const TYPE_OPTIONS = [
  { value: 'bahan', label: 'Bahan' },
  { value: 'aksesoris', label: 'Aksesoris' },
];

export const InlineMaterialPicker = ({ type = '', categories = [], token, onSelect, children }) => {
  const [open, setOpen] = useState(false);
  const [materials, setMaterials] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newMaterial, setNewMaterial] = useState({
    code: '', name: '',
    type: type || 'fabric',
    unit: isKgLike(type || 'fabric') ? 'kg' : 'pcs',
    category: '', category_name: '',
    composition: '', color: '', notes: '',
  });
  const [saving, setSaving] = useState(false);

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  useEffect(() => {
    if (open) loadMaterials();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => { loadMaterials(); }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery]);

  const loadMaterials = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (type) params.set('type', type);
      if (searchQuery) params.set('search', searchQuery);
      const res = await fetch(`/api/rahaza/materials?${params.toString()}`, { headers });
      if (res.ok) {
        const data = await res.json();
        const items = Array.isArray(data) ? data : (data.items || []);
        setMaterials(items);
      }
    } catch (err) {
      console.error('Error loading materials:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectMaterial = (material) => {
    if (onSelect) onSelect(material);
    setOpen(false);
  };

  const handleCreateMaterial = async () => {
    if (!newMaterial.code || !newMaterial.name) {
      toast.error('Kode dan Nama material wajib diisi');
      return;
    }
    setSaving(true);
    try {
      const res = await fetch('/api/rahaza/materials', {
        method: 'POST', headers, body: JSON.stringify(newMaterial),
      });
      if (!res.ok) {
        const error = await res.text();
        throw new Error(error || 'Gagal membuat material');
      }
      const created = await res.json();
      toast.success(`Material ${created.code} berhasil dibuat`);
      setCreateDialogOpen(false);
      setNewMaterial({
        code: '', name: '', type: type || 'fabric',
        unit: isKgLike(type || 'fabric') ? 'kg' : 'pcs',
        category: '', category_name: '', composition: '', color: '', notes: '',
      });
      handleSelectMaterial(created);
      loadMaterials();
    } catch (err) {
      toast.error(err.message || 'Gagal membuat material');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild data-testid="inline-material-picker-trigger">
          {children || (
            <Button variant="outline" size="sm" className="w-full justify-start">
              <Search className="w-4 h-4 mr-2" />
              Pilih dari master data
            </Button>
          )}
        </PopoverTrigger>
        <PopoverContent className="w-[420px] p-0" align="start">
          <Command shouldFilter={false}>
            <CommandInput
              placeholder="Cari material (kode / nama)..."
              value={searchQuery}
              onValueChange={setSearchQuery}
              data-testid="inline-material-picker-search-input"
            />
            <CommandList>
              <CommandEmpty>
                {loading ? 'Memuat...' : 'Tidak ada material ditemukan.'}
              </CommandEmpty>
              <CommandGroup>
                {materials.map(mat => (
                  <CommandItem
                    key={mat.id}
                    value={`${mat.code} ${mat.name}`}
                    onSelect={() => handleSelectMaterial(mat)}
                    className="cursor-pointer"
                    data-testid={`material-option-${mat.code}`}
                  >
                    <Package className="w-4 h-4 mr-2 text-muted-foreground shrink-0" />
                    <div className="flex flex-col min-w-0">
                      <span className="font-medium truncate">{mat.code} · {mat.name}</span>
                      <span className="text-xs text-muted-foreground truncate">
                        {mat.category_name || mat.type}
                        {mat.unit ? ` · ${mat.unit}` : ''}
                        {readField(mat, FIELD.composition) ? ` · ${readField(mat, FIELD.composition)}` : ''}
                      </span>
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
            <div className="border-t border-border p-2">
              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-start text-primary"
                onClick={() => { setCreateDialogOpen(true); setOpen(false); }}
                data-testid="inline-material-picker-create-new-button"
              >
                <Plus className="w-4 h-4 mr-2" />
                Buat material baru
              </Button>
            </div>
          </Command>
        </PopoverContent>
      </Popover>

      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="sm:max-w-[520px]" data-testid="inline-material-create-dialog">
          <DialogHeader>
            <DialogTitle>Buat Material Baru</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="mat-code">Kode Material *</Label>
                <GlassInput
                  id="mat-code"
                  placeholder="BHN-001"
                  value={newMaterial.code}
                  onChange={e => setNewMaterial({ ...newMaterial, code: e.target.value.toUpperCase() })}
                  data-testid="inline-material-create-code"
                />
              </div>
              <div>
                <Label htmlFor="mat-type">Jenis</Label>
                <Select
                  value={typeToCategory(newMaterial.type)}
                  onValueChange={val => { const st = categoryToStoredType(val); setNewMaterial({
                    ...newMaterial,
                    type: st,
                    unit: isKgLike(st) ? 'kg' : (newMaterial.unit || 'pcs'),
                  }); }}
                >
                  <SelectTrigger data-testid="inline-material-create-type"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {TYPE_OPTIONS.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label htmlFor="mat-name">Nama Material *</Label>
              <GlassInput
                id="mat-name"
                placeholder="Kain Katun 30s"
                value={newMaterial.name}
                onChange={e => setNewMaterial({ ...newMaterial, name: e.target.value })}
                data-testid="inline-material-create-name"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="mat-category">Kategori</Label>
                <Select
                  value={newMaterial.category || '__none__'}
                  onValueChange={val => {
                    const cat = categories.find(c => c.code === val);
                    setNewMaterial({
                      ...newMaterial,
                      category: val === '__none__' ? '' : val,
                      category_name: cat ? cat.name : '',
                    });
                  }}
                >
                  <SelectTrigger data-testid="inline-material-create-category"><SelectValue placeholder="— Pilih —" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">— Tidak ada —</SelectItem>
                    {categories.map(c => <SelectItem key={c.code} value={c.code}>{c.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="mat-unit">Unit</Label>
                <Select
                  value={newMaterial.unit}
                  onValueChange={val => setNewMaterial({ ...newMaterial, unit: val })}
                >
                  <SelectTrigger data-testid="inline-material-create-unit"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {UNIT_OPTIONS.map(u => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {isKgLike(newMaterial.type) && (
              <div>
                <Label htmlFor="mat-yarn-type">Jenis / Komposisi</Label>
                <GlassInput
                  id="mat-yarn-type"
                  placeholder="Katun / 100%"
                  value={newMaterial.composition}
                  onChange={e => setNewMaterial({ ...newMaterial, composition: e.target.value })}
                  data-testid="inline-material-create-yarn-type"
                />
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="mat-color">Warna (opsional)</Label>
                <GlassInput
                  id="mat-color"
                  placeholder="Merah, Biru, dll"
                  value={newMaterial.color}
                  onChange={e => setNewMaterial({ ...newMaterial, color: e.target.value })}
                  data-testid="inline-material-create-color"
                />
              </div>
              <div>
                <Label htmlFor="mat-notes">Catatan (opsional)</Label>
                <GlassInput
                  id="mat-notes"
                  placeholder="Catatan tambahan"
                  value={newMaterial.notes}
                  onChange={e => setNewMaterial({ ...newMaterial, notes: e.target.value })}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setCreateDialogOpen(false)} disabled={saving}>
              Batal
            </Button>
            <Button
              onClick={handleCreateMaterial}
              disabled={saving}
              data-testid="inline-material-create-form-submit-button"
            >
              {saving ? 'Menyimpan...' : 'Buat Material'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};
