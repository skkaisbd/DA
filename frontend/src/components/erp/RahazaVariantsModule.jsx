import { useState, useEffect, useCallback, useMemo } from 'react';
import { Plus, Trash2, Boxes, Wand2, Package } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';

/* Varian Produk (Fase 2) — kombinasi Warna × Size dengan SKU unik otomatis.
   SKU = KODE-WARNA-SIZE. Generate matriks dari warna & size terpilih. */
export function RahazaVariantsModule({ token }) {
  const [models, setModels] = useState([]);
  const [colors, setColors] = useState([]);
  const [sizes, setSizes] = useState([]);
  const [selectedModelId, setSelectedModelId] = useState('');
  const [variants, setVariants] = useState([]);
  const [loading, setLoading] = useState(false);

  // Generate dialog state
  const [genOpen, setGenOpen] = useState(false);
  const [genColorIds, setGenColorIds] = useState([]);
  const [genSizeIds, setGenSizeIds] = useState([]);
  const [generating, setGenerating] = useState(false);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const loadBase = useCallback(async () => {
    const h = { Authorization: `Bearer ${token}` };
    const [mRes, cRes, sRes] = await Promise.all([
      fetch('/api/rahaza/models', { headers: h }).then(r => r.ok ? r.json() : []),
      fetch('/api/rahaza/colors', { headers: h }).then(r => r.ok ? r.json() : []),
      fetch('/api/rahaza/sizes', { headers: h }).then(r => r.ok ? r.json() : []),
    ]);
    const activeModels = (mRes || []).filter(m => m.active !== false);
    setModels(activeModels);
    setColors((cRes || []).filter(c => c.active !== false));
    setSizes((sRes || []).filter(s => s.active !== false));
    if (!selectedModelId && activeModels.length) setSelectedModelId(activeModels[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const loadVariants = useCallback(async () => {
    if (!selectedModelId) { setVariants([]); return; }
    setLoading(true);
    try {
      const r = await fetch(`/api/rahaza/models/${selectedModelId}/variants`, { headers });
      if (r.ok) {
        const data = await r.json();
        setVariants(data.variants || []);
      } else setVariants([]);
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModelId, token]);

  useEffect(() => { loadBase(); }, [loadBase]);
  useEffect(() => { loadVariants(); }, [loadVariants]);

  const openGenerate = () => {
    setGenColorIds([]);
    setGenSizeIds(sizes.map(s => s.id)); // default: semua size
    setGenOpen(true);
  };

  const toggleColor = (id) => setGenColorIds(ids => ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id]);
  const toggleSize = (id) => setGenSizeIds(ids => ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id]);

  const runGenerate = async () => {
    if (!genColorIds.length) { toast.error('Pilih minimal 1 warna'); return; }
    if (!genSizeIds.length) { toast.error('Pilih minimal 1 size'); return; }
    setGenerating(true);
    try {
      const r = await fetch(`/api/rahaza/models/${selectedModelId}/variants/generate`, {
        method: 'POST', headers,
        body: JSON.stringify({ color_ids: genColorIds, size_ids: genSizeIds }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        toast.error(err.detail || `Gagal generate (HTTP ${r.status})`);
        return;
      }
      const data = await r.json();
      toast.success(`Varian dibuat: ${data.created_count} · Dilewati (sudah ada): ${data.skipped_count}`);
      setGenOpen(false);
      loadVariants();
    } finally { setGenerating(false); }
  };

  const handleDelete = async (v) => {
    if (!window.confirm(`Hapus varian ${v.sku}?`)) return;
    const r = await fetch(`/api/rahaza/variants/${v.id}`, { method: 'DELETE', headers });
    if (r.ok) { toast.success('Varian dihapus'); loadVariants(); }
    else toast.error('Gagal menghapus varian');
  };

  const selectedModel = models.find(m => m.id === selectedModelId);

  return (
    <div className="space-y-4" data-testid="rahaza-variants-module">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Boxes className="w-4 h-4 text-primary" /> Varian Produk (SKU)
          </h2>
          <p className="text-muted-foreground text-sm mt-1">
            Varian = Warna × Size dengan SKU unik otomatis
            (<span className="font-mono text-foreground">KODE-WARNA-SIZE</span>).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={selectedModelId} onValueChange={setSelectedModelId} data-testid="variant-model-selector">
            <SelectTrigger className="w-[240px]">
              <SelectValue placeholder="— Pilih Model —" />
            </SelectTrigger>
            <SelectContent>
              {models.map(m => (
                <SelectItem key={m.id} value={m.id}>{m.code} · {m.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button onClick={openGenerate} disabled={!selectedModelId} className="gap-1.5" data-testid="variant-generate-btn">
            <Wand2 className="w-4 h-4" /> Generate Varian
          </Button>
        </div>
      </div>

      {!selectedModelId ? (
        <GlassCard className="p-12 text-center text-muted-foreground">
          <Package className="w-10 h-10 mx-auto mb-3 text-foreground/30" />
          Pilih model untuk mengelola varian.
        </GlassCard>
      ) : (
        <GlassCard className="p-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--glass-border)] bg-[var(--glass-bg)] flex items-center justify-between">
            <div className="text-sm">
              <span className="font-semibold text-foreground">{selectedModel?.code}</span>
              <span className="text-muted-foreground"> · {selectedModel?.name}</span>
            </div>
            <Badge variant="outline">{variants.length} varian</Badge>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>SKU</TableHead>
                  <TableHead className="w-16">Warna</TableHead>
                  <TableHead>Nama Warna</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead className="text-right">Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground">Memuat...</TableCell></TableRow>
                ) : variants.length === 0 ? (
                  <TableRow><TableCell colSpan={5} className="text-center py-10 text-muted-foreground">
                    Belum ada varian. Klik <b>Generate Varian</b> untuk membuat matriks Warna × Size.
                  </TableCell></TableRow>
                ) : variants.map(v => (
                  <TableRow key={v.id} data-testid={`variant-row-${v.sku}`}>
                    <TableCell className="font-mono font-semibold text-foreground">{v.sku}</TableCell>
                    <TableCell>
                      <span className="inline-block w-6 h-6 rounded-md border border-[var(--glass-border)]"
                        style={{ backgroundColor: v.color_hex || '#ccc' }} title={v.color_hex} />
                    </TableCell>
                    <TableCell className="text-foreground">{v.color_name} <span className="text-muted-foreground text-xs">({v.color_code})</span></TableCell>
                    <TableCell><Badge variant="secondary">{v.size_code}</Badge></TableCell>
                    <TableCell className="text-right">
                      <button
                        onClick={() => handleDelete(v)}
                        className="p-1.5 rounded hover:bg-red-500/15 text-muted-foreground hover:text-red-400"
                        title="Hapus varian" data-testid={`variant-delete-${v.sku}`}
                      ><Trash2 className="w-3.5 h-3.5" /></button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </GlassCard>
      )}

      {/* Generate Dialog */}
      <Dialog open={genOpen} onOpenChange={setGenOpen}>
        <DialogContent className="sm:max-w-[600px]" data-testid="variant-generate-dialog">
          <DialogHeader>
            <DialogTitle>Generate Varian · {selectedModel?.code}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-foreground">Pilih Warna</span>
                <button className="text-xs text-primary hover:underline"
                  onClick={() => setGenColorIds(genColorIds.length === colors.length ? [] : colors.map(c => c.id))}
                  data-testid="variant-gen-toggle-all-colors">
                  {genColorIds.length === colors.length ? 'Kosongkan' : 'Pilih Semua'}
                </button>
              </div>
              <div className="grid grid-cols-3 gap-2 max-h-48 overflow-y-auto">
                {colors.map(c => {
                  const checked = genColorIds.includes(c.id);
                  return (
                    <label key={c.id}
                      className={`flex items-center gap-2 border rounded-lg px-2.5 py-2 cursor-pointer text-sm transition-colors ${
                        checked ? 'bg-primary/10 border-primary/40 text-foreground' : 'bg-[var(--glass-bg)] border-[var(--glass-border)] text-foreground/70 hover:bg-[var(--glass-bg-hover)]'
                      }`}
                      data-testid={`variant-gen-color-${c.code}`}>
                      <input type="checkbox" checked={checked} onChange={() => toggleColor(c.id)} />
                      <span className="inline-block w-4 h-4 rounded border border-[var(--glass-border)]" style={{ backgroundColor: c.hex }} />
                      <span className="truncate">{c.name}</span>
                    </label>
                  );
                })}
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-foreground">Pilih Size</span>
                <button className="text-xs text-primary hover:underline"
                  onClick={() => setGenSizeIds(genSizeIds.length === sizes.length ? [] : sizes.map(s => s.id))}
                  data-testid="variant-gen-toggle-all-sizes">
                  {genSizeIds.length === sizes.length ? 'Kosongkan' : 'Pilih Semua'}
                </button>
              </div>
              <div className="grid grid-cols-5 gap-2">
                {sizes.map(s => {
                  const checked = genSizeIds.includes(s.id);
                  return (
                    <label key={s.id}
                      className={`flex items-center justify-center gap-1.5 border rounded-lg px-2 py-2 cursor-pointer text-sm font-mono transition-colors ${
                        checked ? 'bg-primary/10 border-primary/40 text-foreground' : 'bg-[var(--glass-bg)] border-[var(--glass-border)] text-foreground/70 hover:bg-[var(--glass-bg-hover)]'
                      }`}
                      data-testid={`variant-gen-size-${s.code}`}>
                      <input type="checkbox" checked={checked} onChange={() => toggleSize(s.id)} />
                      {s.code}
                    </label>
                  );
                })}
              </div>
            </div>
            <div className="text-xs text-muted-foreground bg-[var(--glass-bg)] rounded-lg p-2.5 border border-[var(--glass-border)]">
              Akan dibuat <b className="text-foreground">{genColorIds.length * genSizeIds.length}</b> kombinasi SKU.
              Kombinasi yang sudah ada akan dilewati otomatis.
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setGenOpen(false)}>Batal</Button>
            <Button onClick={runGenerate} disabled={generating} className="gap-1.5" data-testid="variant-gen-run-btn">
              <Plus className="w-4 h-4" /> {generating ? 'Membuat...' : 'Generate'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default RahazaVariantsModule;
