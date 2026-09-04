/**
 * SkuMappingPanel.jsx — F1.4 PEMETAAN SKU PLATFORM → ITEM KATALOG
 *
 * Ekspor Seller Center memakai `SKU ID` platform (angka panjang) yang tidak sama
 * dengan SKU internal. Tanpa pemetaan, omzet TETAP masuk (tidak boleh hilang)
 * tetapi tidak bisa dihubungkan ke HPP & stok ⇒ marjin tidak bisa dihitung.
 *
 * Layar ini TABEL (bukan kartu), punya usulan otomatis (kemiripan nama ≥0,7) dan
 * aksi massal "pakai semua usulan" — tetapi setiap pemetaan tetap harus
 * dikonfirmasi manusia sebelum disimpan.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link2, Loader2, Save, RefreshCw, Wand2, CheckCircle2, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL || '';
const fmtRp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;

export default function SkuMappingPanel({ sessionId, token, onDone }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState(null);
  const [picks, setPicks] = useState({});      // platform_sku_id → catalog_item_id

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/marketing/data-import/sessions/${sessionId}/sku-map`,
        { headers });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || 'Gagal memuat daftar SKU');
      setData(body);
      setPicks({});
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [sessionId, headers]);

  useEffect(() => { load(); }, [load]);

  const unmapped = data?.unmapped || [];
  const catalogItems = data?.catalog_items || [];
  const pickedCount = Object.values(picks).filter(Boolean).length;

  const useAllSuggestions = () => {
    // Kenapa dibedakan: "tidak ada usulan" punya DUA sebab yang tindak lanjutnya
    // beda jauh — (a) katalog toko masih kosong (harus isi katalog dulu) atau
    // (b) katalog ada tapi tidak ada nama yang cukup mirip (harus pilih manual).
    // Satu pesan untuk keduanya membuat staf menekan tombol berulang kali.
    if (!catalogItems.length) {
      toast.warning(
        'Katalog toko ini masih kosong, jadi belum ada item yang bisa diusulkan. '
        + 'Tambahkan item di Manajemen Katalog (atau impor "Item Katalog Toko") lebih dulu — '
        + 'omzet impor ini tetap aman, hanya belum bisa dihitung HPP/marjinnya.',
        { duration: 9000 },
      );
      return;
    }
    const next = { ...picks };
    let n = 0;
    unmapped.forEach(u => {
      if (u.suggestion?.catalog_item_id && !next[u.platform_sku_id]) {
        next[u.platform_sku_id] = u.suggestion.catalog_item_id;
        n += 1;
      }
    });
    setPicks(next);
    if (n) {
      toast.info(`${n} usulan dipakai — periksa lalu simpan`);
    } else {
      toast.info(`Tidak ada nama produk yang cukup mirip dari ${catalogItems.length} item katalog — `
        + 'pilih manual di kolom "Item Katalog".', { duration: 8000 });
    }
  };

  const save = async () => {
    const payload = Object.entries(picks)
      .filter(([, v]) => v)
      .map(([platform_sku_id, catalog_item_id]) => ({ platform_sku_id, catalog_item_id }));
    if (!payload.length) {
      toast.info('Belum ada SKU yang dipetakan');
      return;
    }
    setSaving(true);
    try {
      const r = await fetch(`${API}/api/marketing/data-import/sessions/${sessionId}/sku-map`, {
        method: 'POST', headers, body: JSON.stringify(payload),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || 'Gagal menyimpan pemetaan');
      toast.success(body.message || 'Pemetaan tersimpan', { duration: 6000 });
      await load();
      if (onDone) onDone(body);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="bg-[hsl(var(--card))]" data-testid="sku-mapping-panel">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Link2 className="w-4 h-4 text-primary" /> Pemetaan SKU Platform → Item Katalog
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Omzet sudah masuk. Pemetaan ini menghubungkan SKU platform ke item katalog supaya
          HPP, marjin, dan stok bisa dihitung — dan impor berikutnya tertaut otomatis.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? (
          <div className="space-y-2">{[1, 2, 3].map(i => <Skeleton key={i} className="h-10" />)}</div>
        ) : unmapped.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400"
            data-testid="sku-mapping-clear">
            <CheckCircle2 className="w-4 h-4" /> Semua SKU pada impor ini sudah tertaut item katalog.
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="bg-amber-500/10 text-amber-500 border-amber-500/30">
                <AlertTriangle size={11} className="mr-1" /> {unmapped.length} SKU belum tertaut
              </Badge>
              <span className="text-xs text-muted-foreground">
                {catalogItems.length} item katalog tersedia · sumber data: {data?.source === 'committed' ? 'pesanan tersimpan' : 'pratinjau'}
              </span>
              <div className="ml-auto flex gap-2">
                <Button size="sm" variant="outline" onClick={load} data-testid="sku-map-reload">
                  <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Muat Ulang
                </Button>
                <Button size="sm" variant="outline" onClick={useAllSuggestions}
                  data-testid="sku-map-use-suggestions">
                  <Wand2 className="w-3.5 h-3.5 mr-1.5" /> Pakai Semua Usulan
                </Button>
                <Button size="sm" onClick={save} disabled={saving || !pickedCount}
                  data-testid="sku-map-save">
                  {saving ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                    : <Save className="w-3.5 h-3.5 mr-1.5" />}
                  Simpan {pickedCount || ''} Pemetaan
                </Button>
              </div>
            </div>

            <div className="rounded-[var(--radius-sm)] border border-border overflow-x-auto max-h-[420px] overflow-y-auto">
              <table className="w-full text-xs" data-testid="sku-map-table">
                <thead className="bg-muted/60 sticky top-0">
                  <tr>
                    <th className="px-2 py-2 text-left font-semibold">SKU Platform</th>
                    <th className="px-2 py-2 text-left font-semibold">Nama Produk di Platform</th>
                    <th className="px-2 py-2 text-left font-semibold">Variasi</th>
                    <th className="px-2 py-2 text-right font-semibold">Baris</th>
                    <th className="px-2 py-2 text-right font-semibold">Pcs</th>
                    <th className="px-2 py-2 text-right font-semibold">Omzet</th>
                    <th className="px-2 py-2 text-left font-semibold min-w-[260px]">Item Katalog</th>
                  </tr>
                </thead>
                <tbody>
                  {unmapped.map(u => (
                    <tr key={u.platform_sku_id} className="border-t border-border"
                      data-testid={`sku-map-row-${u.platform_sku_id}`}>
                      <td className="px-2 py-1.5 font-mono">{u.platform_sku_id}</td>
                      <td className="px-2 py-1.5 max-w-[240px] truncate" title={u.product_name_raw}>
                        {u.product_name_raw || '—'}
                      </td>
                      <td className="px-2 py-1.5 text-muted-foreground">{u.variation_raw || '—'}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{u.rows}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{u.pcs}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{fmtRp(u.revenue)}</td>
                      <td className="px-2 py-1.5">
                        <Select value={picks[u.platform_sku_id] || undefined}
                          onValueChange={v => setPicks(p => ({ ...p, [u.platform_sku_id]: v }))}>
                          <SelectTrigger className="h-8 text-xs"
                            data-testid={`sku-map-select-${u.platform_sku_id}`}>
                            <SelectValue placeholder={u.suggestion
                              ? `Usulan: ${u.suggestion.name}`
                              : 'Pilih item katalog...'} />
                          </SelectTrigger>
                          <SelectContent className="max-h-72">
                            {catalogItems.map(ci => (
                              <SelectItem key={ci.id} value={ci.id} className="text-xs">
                                {ci.sku ? `${ci.sku} · ` : ''}{ci.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {u.suggestion && !picks[u.platform_sku_id] && (
                          <button type="button"
                            className="mt-1 text-[10px] text-primary hover:underline"
                            onClick={() => setPicks(p => ({
                              ...p, [u.platform_sku_id]: u.suggestion.catalog_item_id }))}
                            data-testid={`sku-map-apply-suggestion-${u.platform_sku_id}`}>
                            pakai usulan: {u.suggestion.name} ({Math.round(u.suggestion.score * 100)}% mirip)
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {catalogItems.length === 0 && (
              <p className="text-xs text-amber-500 flex items-start gap-1"
                data-testid="sku-map-empty-catalog">
                <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                Katalog toko ini masih kosong — tambahkan item di <b className="mx-1">Manajemen Katalog</b>
                lebih dulu, lalu kembali ke layar ini.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
