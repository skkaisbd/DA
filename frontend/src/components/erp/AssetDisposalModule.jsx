import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, PackageMinus, Trash2 } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';
import { useToast } from '@/hooks/use-toast';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const fmt = formatRupiah;

export default function AssetDisposalModule({ token }) {
  const [activeAssets, setActiveAssets] = useState([]);
  const [disposedAssets, setDisposedAssets] = useState([]);
  const [tab, setTab] = useState('active');
  const [loading, setLoading] = useState(true);
  const [disposalTarget, setDisposalTarget] = useState(null);
  const { toast } = useToast();
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchAssets = useCallback(async () => {
    setLoading(true);
    try {
      const [activeR, disposedR] = await Promise.all([
        fetch('/api/rahaza/finance/fixed-assets?status=active', { headers }),
        fetch('/api/rahaza/finance/fixed-assets?status=disposed', { headers })
      ]);
      if (activeR.ok) setActiveAssets(await activeR.json());
      if (disposedR.ok) setDisposedAssets(await disposedR.json());
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal memuat daftar aset', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchAssets(); }, [fetchAssets]);

  const dispose = async () => {
    if (!disposalTarget) return;
    if (!disposalTarget.notes || disposalTarget.notes.trim().length < 5) {
      toast({ title: 'Error', description: 'Alasan disposal harus minimal 5 karakter', variant: 'destructive' });
      return;
    }
    try {
      const r = await fetch(`/api/rahaza/finance/fixed-assets/${disposalTarget.id}/dispose`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          disposal_date: disposalTarget.disposal_date || new Date().toISOString().split('T')[0],
          disposal_value: Number(disposalTarget.disposal_value) || 0,
          notes: disposalTarget.notes
        })
      });
      if (r.ok) {
        const result = await r.json();
        toast({
          title: 'Sukses',
          description: `Aset ${disposalTarget.name} berhasil di-dispose. Gain/Loss: ${fmt(result.gain_loss)}`
        });
        setDisposalTarget(null);
        fetchAssets();
      } else {
        const err = await r.json();
        toast({ title: 'Error', description: err.detail || 'Gagal disposal', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal disposal aset', variant: 'destructive' });
    }
  };

  const assets = tab === 'active' ? activeAssets : disposedAssets;

  const { page, setPage, totalPages, total, paged } = useClientPagination(assets, 10);
  return (
    <div className="space-y-5" data-testid="asset-disposal-page">
      <PageHeader
        icon={PackageMinus}
        eyebrow="Portal Finance · Fixed Assets"
        title="Pelepasan Aset Tetap"
        subtitle="Kelola disposal aset tetap (penjualan, penghapusan). Sistem otomatis posting jurnal gain/loss disposal."
        actions={
          <Button variant="ghost" onClick={fetchAssets} className="h-9 border border-[var(--glass-border)]" data-testid="disposal-refresh">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang
          </Button>
        }
      />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <StatTile label="Total Aset Aktif" value={activeAssets.length} />
        <StatTile label="Disposed Bulan Ini" value={disposedAssets.filter(a => {
          const d = new Date(a.disposal_date || '');
          const now = new Date();
          return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
        }).length} accent="warning" />
        <StatTile
          label="Avg Gain/Loss"
          value={disposedAssets.length > 0 ? fmt(disposedAssets.reduce((s, a) => s + (a.disposal_gain_loss || 0), 0) / disposedAssets.length) : 'Rp 0'}
        />
      </div>
      <GlassCard className="p-4">
        <div className="flex gap-2 mb-4">
          <Button
            variant={tab === 'active' ? 'default' : 'ghost'}
            onClick={() => setTab('active')}
            data-testid="disposal-tab-active"
          >
            Aset Aktif ({activeAssets.length})
          </Button>
          <Button
            variant={tab === 'disposed' ? 'default' : 'ghost'}
            onClick={() => setTab('disposed')}
            data-testid="disposal-tab-disposed"
          >
            Riwayat Disposal ({disposedAssets.length})
          </Button>
        </div>
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Memuat...</div>
        ) : assets.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            {tab === 'active' ? 'Tidak ada aset aktif' : 'Belum ada riwayat disposal'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="disposal-table">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="pb-2">Kode</th>
                  <th className="pb-2">Nama Aset</th>
                  <th className="pb-2">Kategori</th>
                  {tab === 'active' ? (
                    <>
                      <th className="pb-2 text-right">Harga Perolehan</th>
                      <th className="pb-2 text-right">NBV Saat Ini</th>
                      <th className="pb-2 text-right">Aksi</th>
                    </>
                  ) : (
                    <>
                      <th className="pb-2">Tanggal Disposal</th>
                      <th className="pb-2 text-right">NBV at Disposal</th>
                      <th className="pb-2 text-right">Disposal Value</th>
                      <th className="pb-2 text-right">Gain/Loss</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {paged.map(a => (
                  <tr key={a.id} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-border)]/30" data-testid={`disposal-row-${a.id}`}>
                    <td className="py-3 font-mono text-xs">{a.code}</td>
                    <td className="py-3">{a.name}</td>
                    <td className="py-3 capitalize">{a.category}</td>
                    {tab === 'active' ? (
                      <>
                        <td className="py-3 text-right font-mono">{fmt(a.purchase_cost)}</td>
                        <td className="py-3 text-right font-mono">{fmt(a.book_value_current)}</td>
                        <td className="py-3 text-right">
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => setDisposalTarget({ ...a, disposal_date: '', disposal_value: 0, notes: '' })}
                            data-testid={`disposal-btn-${a.id}`}
                          >
                            <Trash2 className="w-3.5 h-3.5 mr-1" />
                            Dispose
                          </Button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="py-3 text-xs">{a.disposal_date}</td>
                        <td className="py-3 text-right font-mono">{fmt(a.nbv_at_disposal)}</td>
                        <td className="py-3 text-right font-mono">{fmt(a.disposal_value)}</td>
                        <td className="py-3 text-right font-mono">
                          <span className={a.disposal_gain_loss >= 0 ? 'text-emerald-300' : 'text-red-300'}>
                            {a.disposal_gain_loss >= 0 ? '+' : ''}{fmt(a.disposal_gain_loss)}
                          </span>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
          </div>
        )}
      </GlassCard>
      {disposalTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setDisposalTarget(null)}>
          <GlassCard className="p-6 max-w-lg w-full" onClick={e => e.stopPropagation()} data-testid="disposal-dialog">
            <h2 className="text-xl font-bold text-foreground mb-4">Disposal Aset: {disposalTarget.name}</h2>
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 mb-4">
              <div className="text-sm space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Kode:</span>
                  <span className="font-mono">{disposalTarget.code}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Harga Perolehan:</span>
                  <span className="font-mono">{fmt(disposalTarget.purchase_cost)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">NBV Saat Ini:</span>
                  <span className="font-mono font-semibold text-blue-300">{fmt(disposalTarget.book_value_current)}</span>
                </div>
              </div>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs uppercase text-muted-foreground block mb-1">Tanggal Disposal</label>
                <input
                  type="date"
                  value={disposalTarget.disposal_date}
                  onChange={e => setDisposalTarget(d => ({ ...d, disposal_date: e.target.value }))}
                  className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  data-testid="disposal-date"
                />
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground block mb-1">Disposal Value (Harga Jual/Scrap)</label>
                <GlassInput
                  type="number"
                  min={0}
                  value={disposalTarget.disposal_value}
                  onChange={e => setDisposalTarget(d => ({ ...d, disposal_value: e.target.value }))}
                  data-testid="disposal-value"
                />
                <div className="text-xs text-muted-foreground mt-1">
                  Estimated Gain/Loss: <span className={Number(disposalTarget.disposal_value) - disposalTarget.book_value_current >= 0 ? 'text-emerald-300' : 'text-red-300'}>
                    {fmt(Number(disposalTarget.disposal_value) - disposalTarget.book_value_current)}
                  </span>
                </div>
              </div>
              <div>
                <label className="text-xs uppercase text-muted-foreground block mb-1">Alasan Disposal *</label>
                <textarea
                  value={disposalTarget.notes}
                  onChange={e => setDisposalTarget(d => ({ ...d, notes: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  rows={3}
                  placeholder="Contoh: Dijual karena sudah tidak produktif, rusak berat"
                  data-testid="disposal-notes"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-6 justify-end">
              <Button variant="ghost" onClick={() => setDisposalTarget(null)} className="border border-[var(--glass-border)]" data-testid="disposal-cancel">
                Batal
              </Button>
              <Button variant="destructive" onClick={dispose} data-testid="disposal-confirm">
                <Trash2 className="w-4 h-4 mr-2" />
                Konfirmasi Disposal
              </Button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
