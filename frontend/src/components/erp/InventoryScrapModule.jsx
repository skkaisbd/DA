import { useState, useEffect, useCallback, useMemo } from 'react';
import { RefreshCw, PackageMinus, Plus, AlertTriangle } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';
import { useToast } from '@/hooks/use-toast';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const fmt = formatRupiah;

export default function InventoryScrapModule({ token }) {
  const [movements, setMovements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [adjustForm, setAdjustForm] = useState(null);
  const [materials, setMaterials] = useState([]);
  const [stockInfo, setStockInfo] = useState(null);
  const { toast } = useToast();
  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token]
  );

  const fetchMovements = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/rahaza/material-movements?type=adjust', { headers });
      if (r.ok) setMovements(await r.json());
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal memuat riwayat adjustment', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [headers, toast]);

  useEffect(() => {
    (async () => {
      try {
        const [mvR, matR] = await Promise.all([
          fetch('/api/rahaza/material-movements?type=adjust', { headers }),
          fetch('/api/rahaza/materials', { headers }),
        ]);
        if (mvR.ok) setMovements(await mvR.json());
        if (matR.ok) setMaterials(await matR.json());
      } catch (e) {
        // Silent fail on initial load
      } finally {
        setLoading(false);
      }
    })();
  }, [headers]);

  const checkStock = async (materialId, locationId) => {
    try {
      const r = await fetch(`/api/rahaza/material-stock?material_id=${materialId}&location_id=${locationId}`, { headers });
      if (r.ok) {
        const stocks = await r.json();
        setStockInfo(stocks[0] || null);
      }
    } catch (e) {
      // Silent fail
    }
  };

  const adjust = async () => {
    if (!adjustForm) return;
    if (!adjustForm.material_id || !adjustForm.location_id || !adjustForm.qty || !adjustForm.reason) {
      toast({ title: 'Error', description: 'Semua field wajib diisi', variant: 'destructive' });
      return;
    }
    if (adjustForm.reason.trim().length < 5) {
      toast({ title: 'Error', description: 'Alasan harus minimal 5 karakter untuk audit trail', variant: 'destructive' });
      return;
    }
    const delta = Number(adjustForm.qty);
    if (delta === 0) {
      toast({ title: 'Error', description: 'Qty adjustment tidak boleh 0', variant: 'destructive' });
      return;
    }
    // Check stock availability for negative adjustment
    if (delta < 0 && stockInfo && Math.abs(delta) > stockInfo.qty) {
      toast({ title: 'Error', description: `Stok tidak cukup. Tersedia: ${stockInfo.qty}`, variant: 'destructive' });
      return;
    }
    try {
      const r = await fetch('/api/rahaza/material-adjust', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          material_id: adjustForm.material_id,
          location_id: adjustForm.location_id,
          qty: delta,
          reason: adjustForm.reason
        })
      });
      if (r.ok) {
        toast({ title: 'Sukses', description: 'Adjustment berhasil dicatat' });
        setAdjustForm(null);
        setStockInfo(null);
        fetchMovements();
      } else {
        const err = await r.json();
        toast({ title: 'Error', description: err.detail || 'Gagal adjustment', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal adjustment', variant: 'destructive' });
    }
  };

  const totalScrapThisMonth = movements.filter(m => {
    const d = new Date(m.created_at || '');
    const now = new Date();
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear() && Number(m.qty) < 0;
  }).length;
  const { page, setPage, totalPages, total, paged } = useClientPagination(movements, 10);

  return (
    <div className="space-y-5" data-testid="inventory-scrap-page">
      <PageHeader
        icon={PackageMinus}
        eyebrow="Portal Warehouse · Inventory"
        title="Penyesuaian Stok (Adjustment)"
        subtitle="Catat adjustment stok untuk scrap, damage, theft, atau stock count correction. Sistem otomatis posting GL."
        actions={
          <>
            <Button variant="ghost" onClick={fetchMovements} className="h-9 border border-[var(--glass-border)]" data-testid="adj-refresh">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang
            </Button>
            <Button onClick={() => setAdjustForm({ material_id: '', location_id: '', qty: 0, reason: '', adjustment_type: 'scrap' })} className="h-9" data-testid="adj-add">
              <Plus className="w-3.5 h-3.5 mr-1.5" />Buat Adjustment
            </Button>
          </>
        }
      />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <StatTile label="Total Adjustment Bulan Ini" value={movements.filter(m => {
          const d = new Date(m.created_at || '');
          const now = new Date();
          return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
        }).length} />
        <StatTile label="Scrap/Reduction Bulan Ini" value={totalScrapThisMonth} accent="destructive" />
      </div>
      <GlassCard className="p-4">
        <h3 className="text-lg font-semibold text-foreground mb-4">Riwayat Adjustment</h3>
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Memuat...</div>
        ) : movements.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">Belum ada riwayat adjustment</div>
        ) : (
          <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="adj-table">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="pb-2">Tanggal</th>
                  <th className="pb-2">Material</th>
                  <th className="pb-2">Lokasi</th>
                  <th className="pb-2 text-right">Qty Adjustment</th>
                  <th className="pb-2">Alasan</th>
                  <th className="pb-2">Oleh</th>
                </tr>
              </thead>
              <tbody>
                {paged.map(m => (
                  <tr key={m.id} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-border)]/30" data-testid={`adj-row-${m.id}`}>
                    <td className="py-3 text-xs">{new Date(m.created_at).toLocaleString('id-ID')}</td>
                    <td className="py-3">
                      <div className="text-xs font-mono text-muted-foreground">{m.material_code}</div>
                      <div>{m.material_name}</div>
                    </td>
                    <td className="py-3 text-xs">{m.location_name}</td>
                    <td className="py-3 text-right font-mono">
                      <span className={Number(m.qty) < 0 ? 'text-red-300' : 'text-emerald-300'}>
                        {Number(m.qty) > 0 ? '+' : ''}{m.qty}
                      </span>
                    </td>
                    <td className="py-3 text-xs text-muted-foreground max-w-xs truncate">{m.notes}</td>
                    <td className="py-3 text-xs">{m.created_by_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
          </>
        )}
      </GlassCard>
      {adjustForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => { setAdjustForm(null); setStockInfo(null); }}>
          <GlassCard className="p-6 max-w-lg w-full" onClick={e => e.stopPropagation()} data-testid="adj-form">
            <h2 className="text-xl font-bold text-foreground mb-4">Buat Adjustment Stok</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs uppercase text-muted-foreground">Material ID</label>
                <GlassInput
                  value={adjustForm.material_id}
                  onChange={e => {
                    setAdjustForm(f => ({ ...f, material_id: e.target.value }));
                    if (e.target.value && adjustForm.location_id) checkStock(e.target.value, adjustForm.location_id);
                  }}
                  placeholder="UUID material"
                  data-testid="adj-material-id"
                />
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground">Location ID</label>
                <GlassInput
                  value={adjustForm.location_id}
                  onChange={e => {
                    setAdjustForm(f => ({ ...f, location_id: e.target.value }));
                    if (adjustForm.material_id && e.target.value) checkStock(adjustForm.material_id, e.target.value);
                  }}
                  placeholder="UUID lokasi"
                  data-testid="adj-location-id"
                />
              </div>
              {stockInfo && (
                <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Stok Saat Ini:</span>
                    <span className="font-mono font-semibold">{stockInfo.qty} {stockInfo.unit}</span>
                  </div>
                  {stockInfo.below_min && (
                    <div className="flex items-center gap-1 mt-1 text-yellow-300 text-xs">
                      <AlertTriangle className="w-3 h-3" />
                      <span>Stok di bawah minimum</span>
                    </div>
                  )}
                </div>
              )}
              <div>
                <label className="text-xs uppercase text-muted-foreground">Tipe Adjustment</label>
                <select
                  value={adjustForm.adjustment_type}
                  onChange={e => setAdjustForm(f => ({ ...f, adjustment_type: e.target.value }))}
                  className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  data-testid="adj-type"
                >
                  <option value="scrap">Scrap / Rusak (negatif)</option>
                  <option value="theft">Hilang / Theft (negatif)</option>
                  <option value="found">Ditemukan / Tambahan (positif)</option>
                  <option value="correction">Stock Count Correction</option>
                </select>
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground">Qty Adjustment</label>
                <GlassInput
                  type="number"
                  value={adjustForm.qty}
                  onChange={e => setAdjustForm(f => ({ ...f, qty: e.target.value }))}
                  placeholder="Gunakan negatif untuk pengurangan (misal: -50)"
                  data-testid="adj-qty"
                />
                <div className="text-xs text-muted-foreground mt-1">
                  Negatif (-) untuk scrap/hilang, Positif (+) untuk tambahan/koreksi
                </div>
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground">Alasan <span className="text-red-400">*</span></label>
                <textarea
                  value={adjustForm.reason}
                  onChange={e => setAdjustForm(f => ({ ...f, reason: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  rows={3}
                  placeholder="Contoh: Rusak/cacat saat produksi, hilang saat inventory count"
                  data-testid="adj-reason"
                />
                <div className="text-xs text-muted-foreground mt-1">
                  Min. 5 karakter untuk audit trail
                </div>
              </div>
            </div>
            <div className="flex gap-2 mt-6 justify-end">
              <Button variant="ghost" onClick={() => { setAdjustForm(null); setStockInfo(null); }} className="border border-[var(--glass-border)]" data-testid="adj-cancel">
                Batal
              </Button>
              <Button onClick={adjust} data-testid="adj-confirm">
                Simpan Adjustment
              </Button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
