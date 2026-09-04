/**
 * CreatorWeeklyReportPanel — RAPOR KREATOR MINGGUAN (sesi #35).
 *
 * Kenapa ada: insentif dihitung per periode 3 bulan dan performa dibaca per bulan.
 * Keduanya benar untuk MEMBAYAR, tetapi terlambat untuk MENGARAHKAN — kreator baru
 * tahu dia tertinggal saat periodenya hampir habis. Rapor 7 hari bergulir menjawab
 * "pekan ini saya menghasilkan apa, target periode saya sejauh mana".
 *
 * Aturan yang kelihatan di layar:
 *   · GMV (angka platform) & omzet pesanan berdampingan, TIDAK dijumlah.
 *   · Nominal insentif dibaca dari layar Insentif (satu sumber), bukan dihitung ulang.
 *   · Pengiriman idempoten per (kreator, pekan) — tombol berubah jadi "Kirim ulang".
 *   · Kalau SMTP belum diisi, rapor tetap tersimpan & bisa dibaca kreator di portalnya.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Loader2, RefreshCw, Send, Info, Mail, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { GlassCard } from '@/components/ui/glass';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;
const fmtNum = (n) => new Intl.NumberFormat('id-ID').format(Math.round(n || 0));
const rp = formatRupiah;

const STATUS_LABEL = {
  sent: 'Terkirim', failed: 'Gagal kirim', no_email: 'Belum punya email',
  skipped_no_smtp: 'SMTP belum diisi', already_sent: 'Sudah dikirim',
};

export default function CreatorWeeklyReportPanel({ token }) {
  const authH = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);
  const [weekEnd, setWeekEnd] = useState(new Date().toISOString().slice(0, 10));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState('');

  const todayStr = new Date().toISOString().slice(0, 10);
  // Atribut `max` hanya membatasi picker, bukan tanggal yang DIKETIK — pekan masa
  // depan selalu bernilai 0 dan terbaca sebagai "kreator tidak bekerja".
  const setWeek = (v) => setWeekEnd(v && v > todayStr ? todayStr : (v || todayStr));

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(
        `${API}/api/marketing/kol/weekly-report?week_end=${weekEnd}`, { headers: authH });
      setData(res.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Gagal memuat rapor mingguan');
      setData(null);
    } finally { setLoading(false); }
  }, [weekEnd, authH]);

  useEffect(() => { load(); }, [load]);

  const send = async (creatorId, force) => {
    setSending(creatorId || 'all');
    try {
      const res = await axios.post(`${API}/api/marketing/kol/weekly-report/send`,
        { week_end: weekEnd, creator_ids: creatorId ? [creatorId] : [], force: !!force },
        { headers: authH });
      const s = res.data.summary || {};
      toast.success(`Rapor: ${s.sent || 0} terkirim · ${s.skipped_no_smtp || 0} tanpa SMTP `
        + `· ${s.no_email || 0} tanpa email · ${s.failed || 0} gagal`);
      if (!res.data.smtp_configured) {
        toast.info('SMTP belum dikonfigurasi — rapor tersimpan & bisa dibaca kreator di portalnya.');
      }
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Gagal mengirim rapor');
    } finally { setSending(''); }
  };

  const t = data?.totals || {};
  const rows = data?.rows || [];
  const period = data?.period || {};

  return (
    <div className="space-y-4" data-testid="creator-weekly-report-panel">
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label className="text-[11px] text-muted-foreground block">Pekan berakhir</label>
          <input type="date" value={weekEnd} max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => setWeek(e.target.value)}
            data-testid="weekly-week-end"
            className="h-8 rounded-md border border-border bg-background text-foreground px-2 text-xs" />
        </div>
        <p className="text-[11px] text-muted-foreground pb-1.5">
          7 hari bergulir: <span className="font-semibold text-foreground">
            {period.start || '—'} s/d {period.end || '—'}</span>
        </p>
        <div className="ml-auto flex gap-2">
          <Button size="sm" variant="outline" className="h-8" onClick={load} disabled={loading}
            data-testid="weekly-refresh">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </Button>
          <Button size="sm" className="h-8" onClick={() => send(null, false)}
            disabled={!!sending || !rows.length} data-testid="weekly-send-all">
            {sending === 'all' ? <Loader2 size={13} className="animate-spin mr-1" />
              : <Send size={13} className="mr-1" />} Kirim semua
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3" data-testid="weekly-kpi">
        <GlassCard className="p-3"><p className="text-[11px] text-muted-foreground">Kreator</p>
          <p className="text-base font-bold">{fmtNum(t.creators)}</p>
          <p className="text-[10px] text-muted-foreground">{fmtNum(t.creators_active)} aktif berkonten</p></GlassCard>
        <GlassCard className="p-3"><p className="text-[11px] text-muted-foreground">Konten pekan ini</p>
          <p className="text-base font-bold">{fmtNum(t.contents)}</p>
          <p className="text-[10px] text-muted-foreground">{fmtNum(t.posted)} tayang</p></GlassCard>
        <GlassCard className="p-3"><p className="text-[11px] text-muted-foreground">Views</p>
          <p className="text-base font-bold">{fmtNum(t.views)}</p></GlassCard>
        <GlassCard className="p-3"><p className="text-[11px] text-muted-foreground">GMV (KPI platform)</p>
          <p className="text-base font-bold">{rp(t.gmv_kpi)}</p></GlassCard>
        <GlassCard className="p-3"><p className="text-[11px] text-muted-foreground">Omzet pesanan</p>
          <p className="text-base font-bold">{rp(t.order_revenue)}</p></GlassCard>
        <GlassCard className="p-3"><p className="text-[11px] text-muted-foreground">Insentif periode</p>
          <p className="text-base font-bold">{rp(t.incentive_total)}</p>
          <p className="text-[10px] text-muted-foreground">{fmtNum(t.pcs_week)} pcs pekan ini</p></GlassCard>
      </div>

      {loading ? (
        <div className="py-10 text-center text-muted-foreground text-sm">
          <Loader2 className="mx-auto animate-spin mb-2" size={18} /> Menyusun rapor mingguan…
        </div>
      ) : !rows.length ? (
        <div className="py-10 text-center text-muted-foreground text-sm" data-testid="weekly-empty">
          Belum ada kreator yang bisa dilaporkan.
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-x-auto bg-background">
          <table className="w-full text-xs" data-testid="weekly-table">
            <thead className="bg-muted/60"><tr>
              {['Kreator', 'Tipe', 'Konten', 'Views', 'Engagement', 'Order (KPI)', 'GMV (KPI)',
                'Omzet pesanan', 'Pcs pekan', 'Target periode', 'Insentif', 'Status kirim', ''].map((h, i) => (
                  <th key={`${h}-${i}`} className="px-2.5 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                ))}
            </tr></thead>
            <tbody className="divide-y">
              {rows.map((r) => {
                const last = r.last_sent;
                return (
                  <tr key={r.creator_id} className="hover:bg-muted/30"
                    data-testid={`weekly-row-${r.creator_id}`}>
                    <td className="px-2.5 py-2">
                      <div className="font-semibold text-foreground">{r.creator_name}</div>
                      <div className="text-[10px] text-muted-foreground">
                        {r.creator_code}{r.domicile ? ` · ${r.domicile}` : ''}
                      </div>
                      {!r.login_email && (
                        <div className="text-[10px] text-amber-600 inline-flex items-center gap-0.5">
                          <AlertTriangle size={9} /> belum ada email portal
                        </div>
                      )}
                    </td>
                    <td className="px-2.5 py-2">
                      <Badge variant="outline" className="text-[9px]">{r.creator_type}</Badge>
                    </td>
                    <td className="px-2.5 py-2">{fmtNum(r.contents)} / {fmtNum(r.posted)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.views)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.engagement)} · {Number(r.engagement_rate || 0).toFixed(2)}%</td>
                    <td className="px-2.5 py-2">{fmtNum(r.orders_kpi)}</td>
                    <td className="px-2.5 py-2 font-semibold whitespace-nowrap">{rp(r.gmv_kpi)}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{rp(r.order_revenue)}</td>
                    <td className="px-2.5 py-2">{fmtNum(r.pcs_week)}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">
                      {r.target_pcs ? `${fmtNum(r.pcs_period)} / ${fmtNum(r.target_pcs)} (${r.target_progress_pct}%)`
                        : <span className="text-muted-foreground">tanpa target</span>}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap">
                      {r.incentive_eligible ? rp(r.incentive_total)
                        : <span className="text-muted-foreground">tipe new</span>}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap">
                      {last ? (
                        <span className={last.status === 'sent' ? 'text-emerald-600' : 'text-amber-600'}
                          title={last.error || ''}>
                          {STATUS_LABEL[last.status] || last.status}
                        </span>
                      ) : <span className="text-muted-foreground">belum dikirim</span>}
                    </td>
                    <td className="px-2.5 py-2">
                      <Button size="sm" variant="outline" className="h-6 px-2 text-[10px]"
                        onClick={() => send(r.creator_id, !!last)}
                        disabled={sending === r.creator_id}
                        data-testid={`weekly-send-${r.creator_id}`}>
                        {sending === r.creator_id
                          ? <Loader2 size={10} className="animate-spin mr-1" />
                          : <Mail size={10} className="mr-1" />}
                        {last ? 'Kirim ulang' : 'Kirim'}
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {(data?.data_notes || []).length > 0 && (
        <div className="rounded-lg border border-border bg-muted/40 p-3" data-testid="weekly-notes">
          <p className="text-xs font-semibold mb-1 flex items-center gap-1 text-foreground">
            <Info size={12} /> Catatan kejujuran data
          </p>
          <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-muted-foreground">
            {data.data_notes.map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
