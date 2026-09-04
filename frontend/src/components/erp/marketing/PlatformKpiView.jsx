/**
 * PlatformKpiView — **KPI PLATFORM HARIAN** hasil impor ekspor Seller Center (F7.2).
 *
 * Kenapa layar ini ada: sejak F7.2 staf bisa mengunggah ekspor Shopee (statistik
 * toko, Live, Video). Tanpa layar pembaca, angkanya masuk database dan tidak pernah
 * terlihat — persis keluhan yang membuat mesin impor lama dibongkar.
 *
 * Dua aturan angka ditampilkan APA ADANYA di layar, bukan disembunyikan:
 *   1. angka di sini KPI platform (definisi Shopee), BUKAN omzet pesanan;
 *   2. kanal “Toko” sudah mencakup Live + Video — ketiganya tidak boleh dijumlah.
 */
import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Loader2, Info, Store, Video, Radio, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GlassCard } from '@/components/ui/glass';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';
import { MarketingAccountSelect } from './pickers/MarketingPickers';

const API = process.env.REACT_APP_BACKEND_URL;
const fmtRp = formatRupiah;
const fmtNum = (n) => new Intl.NumberFormat('id-ID').format(Math.round(n || 0));
const CH_ICON = { shop: Store, live: Radio, video: Video };
const SOURCE_LABEL = {
  shopee_shop_stats: 'Statistik Toko',
  shopee_live_1d: 'Live harian',
  shopee_live_overview: 'Live ringkas',
  shopee_video_overview: 'Video ringkas',
};
const HEADS = ['Tanggal', 'Kanal', 'Sumber', 'GMV (dibuat)', 'GMV (siap kirim)', 'Pesanan',
  'Pengunjung', 'Penonton', 'Ditonton', 'Suka', 'Komentar', 'Share', 'Follower baru',
  'Sesi live', 'Menit live', 'AOV'];

export default function PlatformKpiView({ token, onNavigate }) {
  const today = new Date();
  const first = new Date(today.getFullYear(), today.getMonth(), 1);
  const [accountId, setAccountId] = useState('');
  const [from, setFrom] = useState(first.toISOString().slice(0, 10));
  const [to, setTo] = useState(today.toISOString().slice(0, 10));
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ date_from: from, date_to: to });
      if (accountId) qs.set('account_id', accountId);
      const h = { headers: { Authorization: `Bearer ${token}` } };
      const [s, r] = await Promise.all([
        fetch(`${API}/api/marketing/platform-kpi/summary?${qs}`, h),
        fetch(`${API}/api/marketing/platform-kpi?${qs}&limit=400`, h),
      ]);
      if (!s.ok) throw new Error(`HTTP ${s.status}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setSummary(await s.json());
      setRows(((await r.json())?.rows) || []);
    } catch (e) {
      toast.error(`Gagal memuat KPI platform: ${e.message}`);
      setSummary(null); setRows([]);
    } finally { setLoading(false); }
  }, [accountId, from, to, token]);

  useEffect(() => { load(); }, [load]);

  const channels = summary?.channels || [];

  return (
    <div className="space-y-4" data-testid="platform-kpi-view">
      <div className="flex flex-wrap items-end gap-2">
        <MarketingAccountSelect token={token} value={accountId} onChange={setAccountId}
          includeAll allLabel="Semua Toko" required={false} label="Toko"
          testId="kpi-account-select" className="min-w-[220px]" />
        <div>
          <label className="text-[11px] text-muted-foreground block">Dari</label>
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)}
            data-testid="kpi-date-from"
            className="h-9 rounded-md border border-border bg-background text-foreground px-2 text-xs" />
        </div>
        <div>
          <label className="text-[11px] text-muted-foreground block">Sampai</label>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)}
            data-testid="kpi-date-to"
            className="h-9 rounded-md border border-border bg-background text-foreground px-2 text-xs" />
        </div>
        <Button size="sm" variant="outline" className="h-9 ml-auto" onClick={load}
          disabled={loading} data-testid="kpi-refresh">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </Button>
        <Button size="sm" className="h-9" data-testid="kpi-goto-import"
          onClick={() => (onNavigate ? onNavigate('marketing-import')
            : toast.info('Buka menu Impor Data untuk mengunggah ekspor Seller Center'))}>
          <Upload size={13} className="mr-1.5" /> Impor Ekspor Shopee
        </Button>
      </div>

      {loading ? (
        <div className="py-10 text-center text-muted-foreground text-sm">
          <Loader2 className="mx-auto animate-spin mb-2" size={18} /> Memuat KPI platform…
        </div>
      ) : !channels.length ? (
        <div className="py-10 text-center" data-testid="kpi-empty">
          <p className="text-sm font-semibold text-foreground">Belum ada KPI platform pada rentang ini.</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-xl mx-auto">
            Unduh dari Seller Center lalu unggah di menu <b>Impor Data</b>:
            <br />· <b>Statistik Toko</b> (.xlsx) → jenis “KPI Toko Shopee”
            <br />· <b>Live / Video</b> (.csv) → jenis “KPI Konten Shopee”
          </p>
          <Button size="sm" className="mt-3" data-testid="kpi-empty-import"
            onClick={() => onNavigate && onNavigate('marketing-import')}>
            <Upload size={13} className="mr-1.5" /> Buka Impor Data
          </Button>
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="kpi-channels">
            {channels.map((c) => {
              const Icon = CH_ICON[c.channel] || Store;
              return (
                <GlassCard key={c.channel} className="p-3" data-testid={`kpi-channel-${c.channel}`}>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold flex items-center gap-1.5 text-foreground">
                      <Icon size={13} className="text-primary" /> {c.label}
                    </p>
                    <Badge variant="outline" className="text-[9px]">{fmtNum(c.days)} hari</Badge>
                  </div>
                  <div className="space-y-1 text-[11px]">
                    <div className="flex justify-between"><span className="text-muted-foreground">GMV (pesanan dibuat)</span>
                      <span className="font-semibold">{fmtRp(c.gmv_created)}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">Pesanan</span>
                      <span>{fmtNum(c.orders_created)}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">AOV</span>
                      <span>{fmtRp(c.aov)}</span></div>
                    {c.channel === 'shop' ? (
                      <>
                        <div className="flex justify-between"><span className="text-muted-foreground">Pengunjung</span>
                          <span>{fmtNum(c.visitors)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Konversi</span>
                          <span>{Number(c.conversion_rate || 0).toFixed(2)}%</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Dari Live / Video</span>
                          <span>{fmtRp(c.gmv_live)} / {fmtRp(c.gmv_video)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Dari Iklan</span>
                          <span>{fmtRp(c.gmv_ads)}</span></div>
                      </>
                    ) : (
                      <>
                        <div className="flex justify-between"><span className="text-muted-foreground">Penonton / ditonton</span>
                          <span>{fmtNum(c.viewers)} / {fmtNum(c.views)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Engagement</span>
                          <span>{fmtNum(c.engagement)} · {Number(c.engagement_rate || 0).toFixed(2)}%</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Follower baru</span>
                          <span>{fmtNum(c.new_followers)}</span></div>
                        {c.channel === 'live' && (
                          <div className="flex justify-between"><span className="text-muted-foreground">Sesi · menit live</span>
                            <span>{fmtNum(c.live_sessions)} · {fmtNum(c.live_minutes)}</span></div>
                        )}
                      </>
                    )}
                  </div>
                </GlassCard>
              );
            })}
          </div>

          <div className="rounded-lg border border-border overflow-x-auto bg-background">
            <table className="w-full text-xs" data-testid="kpi-table">
              <thead className="bg-muted/60"><tr>{HEADS.map((h) => (
                <th key={h} className="px-2.5 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
              ))}</tr></thead>
              <tbody className="divide-y">
                {rows.map((r) => (
                  <tr key={`${r.date}-${r.channel}`} className="hover:bg-muted/30"
                    data-testid={`kpi-row-${r.date}-${r.channel}`}>
                    <td className="px-2.5 py-2 whitespace-nowrap font-medium">{r.date}</td>
                    <td className="px-2.5 py-2">
                      <Badge variant="outline" className="text-[9px] capitalize">{r.channel}</Badge>
                    </td>
                    <td className="px-2.5 py-2 text-muted-foreground whitespace-nowrap">
                      {SOURCE_LABEL[r.source] || r.source}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap font-semibold">{fmtRp(r.gmv_created)}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{fmtRp(r.gmv_ready)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.orders_created)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.visitors)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.viewers)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.views)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.likes)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.comments)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.shares)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.new_followers)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.live_sessions)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.live_minutes)}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{fmtRp(r.aov)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {(summary?.data_notes || []).length > 0 && (
        <div className="rounded-lg border border-border bg-muted/40 p-3" data-testid="kpi-notes">
          <p className="text-xs font-semibold mb-1 flex items-center gap-1 text-foreground">
            <Info size={12} /> Catatan kejujuran data
          </p>
          <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-muted-foreground">
            {(summary.data_notes || []).map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
