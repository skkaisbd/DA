import { useState, useEffect, useCallback } from 'react';
import { Play, RefreshCw, Calculator, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import { GlassCard, GlassPanel } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';
import { useToast } from '@/hooks/use-toast';
import { formatRupiah } from '@/lib/format';

const fmt = formatRupiah;

export default function AssetDepreciationModule({ token }) {
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [assets, setAssets] = useState([]);
  const [selectedAssets, setSelectedAssets] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const { toast } = useToast();
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchAssets = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/rahaza/finance/fixed-assets?status=active', { headers });
      if (r.ok) {
        const data = await r.json();
        setAssets(data.filter(a => a.depreciation_method && !['none', 'manual'].includes(a.depreciation_method)));
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal memuat daftar aset', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchAssets(); }, [fetchAssets]);

  const runBatchDepreciation = async () => {
    if (selectedAssets.length === 0 && !window.confirm('Tidak ada aset yang dipilih. Jalankan untuk SEMUA aset aktif?')) return;
    setRunning(true);
    setResult(null);
    try {
      const r = await fetch('/api/rahaza/finance/fixed-assets/run-batch-depreciation', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          period,
          asset_ids: selectedAssets.length > 0 ? selectedAssets : [],
          auto_post: true
        })
      });
      if (r.ok) {
        const data = await r.json();
        setResult(data);
        toast({ title: 'Sukses', description: `Batch depreciation selesai: ${data.posted_count} aset berhasil diposting` });
      } else {
        const err = await r.json();
        toast({ title: 'Error', description: err.detail || 'Batch depreciation gagal', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal menjalankan batch depreciation', variant: 'destructive' });
    } finally {
      setRunning(false);
    }
  };

  const toggleAsset = (id) => {
    setSelectedAssets(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const selectAll = () => {
    setSelectedAssets(assets.map(a => a.id));
  };

  const clearSelection = () => {
    setSelectedAssets([]);
  };

  return (
    <div className="space-y-5" data-testid="asset-depreciation-page">
      <PageHeader
        icon={Calculator}
        eyebrow="Portal Finance · Fixed Assets"
        title="Depresiasi Aset (Batch)"
        subtitle="Jalankan batch depreciation untuk periode tertentu. Sistem akan otomatis posting jurnal depresiasi."
        actions={
          <Button variant="ghost" onClick={fetchAssets} className="h-9 border border-[var(--glass-border)]" data-testid="depr-refresh">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang
          </Button>
        }
      />
      {result && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <StatTile label="Aset Diproses" value={result.assets_processed} />
          <StatTile label="Berhasil Posted" value={result.posted_count} accent="success" />
          <StatTile label="Total Depresiasi" value={fmt(result.total_depreciation)} accent="primary" />
          <StatTile
            label="Success Rate"
            value={`${result.assets_processed > 0 ? Math.round((result.posted_count / result.assets_processed) * 100) : 0}%`}
            accent={result.posted_count === result.assets_processed ? 'success' : 'warning'}
          />
        </div>
      )}
      <GlassCard className="p-6">
        <div className="space-y-4">
          <div className="flex gap-4 items-end">
            <div className="flex-1">
              <label className="text-sm font-medium text-foreground mb-2 block">Periode Depresiasi</label>
              <input
                type="month"
                value={period}
                onChange={e => setPeriod(e.target.value)}
                className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                data-testid="depr-period"
              />
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={selectAll} size="sm" data-testid="depr-select-all">
                Pilih Semua
              </Button>
              <Button variant="outline" onClick={clearSelection} size="sm" data-testid="depr-clear-all">
                Clear
              </Button>
            </div>
          </div>
          <div className="flex items-center justify-between p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
            <div>
              <div className="text-sm font-medium text-foreground">
                {selectedAssets.length === 0
                  ? 'Semua aset aktif akan diproses'
                  : `${selectedAssets.length} aset dipilih`}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Auto-post jurnal depresiasi aktif
              </div>
            </div>
            <Button
              onClick={runBatchDepreciation}
              disabled={running || loading}
              className="h-10"
              data-testid="depr-run-batch"
            >
              <Play className="w-4 h-4 mr-2" />
              {running ? 'Memproses...' : 'Run Batch Depreciation'}
            </Button>
          </div>
        </div>
      </GlassCard>
      <GlassCard className="p-4">
        <h3 className="text-lg font-semibold text-foreground mb-4">Daftar Aset Aktif ({assets.length})</h3>
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Memuat aset...</div>
        ) : assets.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">Tidak ada aset aktif yang perlu depresiasi</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="depr-asset-table">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="pb-2 w-12">
                    <input
                      type="checkbox"
                      checked={selectedAssets.length === assets.length}
                      onChange={e => e.target.checked ? selectAll() : clearSelection()}
                      className="w-4 h-4"
                    />
                  </th>
                  <th className="pb-2">Kode</th>
                  <th className="pb-2">Nama Aset</th>
                  <th className="pb-2">Kategori</th>
                  <th className="pb-2">Metode</th>
                  <th className="pb-2 text-right">Harga Perolehan</th>
                  <th className="pb-2 text-right">NBV Saat Ini</th>
                </tr>
              </thead>
              <tbody>
                {assets.map(a => (
                  <tr
                    key={a.id}
                    className={`border-b border-[var(--glass-border)] hover:bg-[var(--glass-border)]/30 cursor-pointer ${selectedAssets.includes(a.id) ? 'bg-primary/10' : ''}`}
                    onClick={() => toggleAsset(a.id)}
                    data-testid={`depr-asset-row-${a.id}`}
                  >
                    <td className="py-3">
                      <input
                        type="checkbox"
                        checked={selectedAssets.includes(a.id)}
                        onChange={() => toggleAsset(a.id)}
                        className="w-4 h-4"
                        onClick={e => e.stopPropagation()}
                      />
                    </td>
                    <td className="py-3 font-mono text-xs">{a.code}</td>
                    <td className="py-3">{a.name}</td>
                    <td className="py-3 capitalize">{a.category}</td>
                    <td className="py-3 text-xs">
                      <span className="px-2 py-1 rounded bg-blue-500/20 text-blue-300">
                        {a.depreciation_method === 'straight_line' ? 'Garis Lurus' : 'Double Declining'}
                      </span>
                    </td>
                    <td className="py-3 text-right font-mono">{fmt(a.purchase_cost)}</td>
                    <td className="py-3 text-right font-mono">{fmt(a.book_value_current)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
      {result && result.results && result.results.length > 0 && (
        <GlassCard className="p-4">
          <h3 className="text-lg font-semibold text-foreground mb-4">Hasil Batch Depreciation</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="depr-result-table">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="pb-2">Status</th>
                  <th className="pb-2">Kode Aset</th>
                  <th className="pb-2">Nama Aset</th>
                  <th className="pb-2 text-right">Depresiasi</th>
                  <th className="pb-2">JE Number</th>
                  <th className="pb-2">Keterangan</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((r, idx) => (
                  <tr key={idx} className="border-b border-[var(--glass-border)]">
                    <td className="py-3">
                      {r.status === 'posted' && <CheckCircle className="w-4 h-4 text-emerald-300" />}
                      {r.status === 'error' && <XCircle className="w-4 h-4 text-red-300" />}
                      {r.status === 'skipped' && <AlertCircle className="w-4 h-4 text-yellow-300" />}
                      {r.status === 'already_posted' && <CheckCircle className="w-4 h-4 text-muted-foreground" />}
                    </td>
                    <td className="py-3 font-mono text-xs">{r.asset_code}</td>
                    <td className="py-3">{r.asset_name}</td>
                    <td className="py-3 text-right font-mono">{fmt(r.depr_amount)}</td>
                    <td className="py-3 font-mono text-xs">{r.je_number || '-'}</td>
                    <td className="py-3 text-xs text-muted-foreground">{r.reason || 'OK'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      )}
    </div>
  );
}
