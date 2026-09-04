/**
 * WeeklyMeetingReportModule — LAPORAN RAPAT MINGGUAN (F8).
 *
 * Semua angka datang dari `GET /api/marketing/reports/weekly` — layar ini TIDAK
 * menghitung apa pun. PDF & Excel memakai sumber yang sama, jadi tidak mungkin
 * ada tiga angka berbeda untuk satu minggu.
 *
 * Bagian `catatan_data` (kejujuran data) ditampilkan MENONJOL, bukan di catatan
 * kaki: laporan yang tidak menyebut lubangnya sendiri akan dipakai seolah lengkap.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CalendarRange, ChevronLeft, ChevronRight, Download, FileText, RefreshCw,
  Info, TrendingUp, TrendingDown, Minus, Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { GlassInput } from '@/components/ui/glass';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { PageHeader } from '../moduleAtoms';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL || '';
const rp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;
const num = (n) => Number(n || 0).toLocaleString('id-ID');
const pct = (v) => (v === null || v === undefined ? '—' : `${v}%`);

const KANAL = [
  ['live', 'Live'], ['video', 'Video'], ['product_card', 'Kartu Produk'],
  ['ads', 'Iklan'], ['affiliate', 'Afiliasi'], ['campaign', 'Kampanye'],
  ['search', 'Pencarian'], ['organic', 'Organik'], ['other', 'Lainnya'],
];

/** Senin minggu itu, dihitung dari WAKTU LOKAL pemakai.
 *  `toISOString()` mengembalikan tanggal UTC — di Asia/Jakarta (UTC+7) sebelum
 *  pukul 07.00 itu masih tanggal SEBELUMNYA, jadi pada hari Senin pagi laporan
 *  yang terbuka adalah MINGGU LALU. Rapat mingguan justru dibuka Senin pagi. */
function mondayOf(d) {
  const x = new Date(d);
  if (Number.isNaN(x.getTime())) return '';
  const wd = (x.getDay() + 6) % 7;          // 0 = Senin
  x.setDate(x.getDate() - wd);
  const mm = String(x.getMonth() + 1).padStart(2, '0');
  const dd = String(x.getDate()).padStart(2, '0');
  return `${x.getFullYear()}-${mm}-${dd}`;
}

function Delta({ d }) {
  if (!d) return <span className="text-muted-foreground">—</span>;
  const p = d.persen;
  if (p === null || p === undefined) {
    return <span className="text-muted-foreground text-[11px]">— (pembanding 0)</span>;
  }
  const Icon = p > 0 ? TrendingUp : p < 0 ? TrendingDown : Minus;
  const tone = p > 0 ? 'text-emerald-500' : p < 0 ? 'text-red-500' : 'text-muted-foreground';
  return (
    <span className={`inline-flex items-center gap-1 ${tone} tabular-nums`}>
      <Icon className="w-3 h-3" />{p > 0 ? '+' : ''}{p}%
    </span>
  );
}

function Tile({ label, value, sub, tone = '', testId }) {
  return (
    <div className="rounded-[var(--radius-md)] border border-border bg-[hsl(var(--card))] p-3"
      data-testid={testId}>
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className={`text-xl font-bold tabular-nums ${tone}`}>{value}</p>
      {sub && <div className="text-[11px] text-muted-foreground mt-0.5">{sub}</div>}
    </div>
  );
}

export default function WeeklyMeetingReportModule({ token }) {
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()));
  const [accountId, setAccountId] = useState('');
  const [accounts, setAccounts] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/api/marketing/accounts?status=active`, { headers });
        const b = await r.json().catch(() => ({}));
        setAccounts(Array.isArray(b) ? b : (b.accounts || b.data || []));
      } catch { setAccounts([]); }
    })();
  }, [headers]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ week_start: weekStart });
      if (accountId) qs.set('account_id', accountId);
      const r = await fetch(`${API}/api/marketing/reports/weekly?${qs}`, { headers });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(b.detail || 'Gagal memuat laporan mingguan');
      setData(b);
    } catch (e) {
      toast.error(e.message, { duration: 9000 });
      setData(null);
    } finally { setLoading(false); }
  }, [headers, weekStart, accountId]);

  useEffect(() => { load(); }, [load]);

  const shift = (days) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + days);
    setWeekStart(mondayOf(d));
  };

  const download = async (fmt) => {
    setBusy(fmt);
    try {
      const qs = new URLSearchParams({ week_start: weekStart });
      if (accountId) qs.set('account_id', accountId);
      const r = await fetch(`${API}/api/marketing/reports/weekly/export-${fmt}?${qs}`, { headers });
      if (!r.ok) {
        const b = await r.json().catch(() => ({}));
        throw new Error(b.detail || `Gagal mengunduh ${fmt.toUpperCase()}`);
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `laporan-rapat-mingguan-${data?.periode?.minggu || weekStart}.${fmt === 'pdf' ? 'pdf' : 'xlsx'}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`${fmt.toUpperCase()} diunduh`);
    } catch (e) {
      toast.error(e.message, { duration: 9000 });
    } finally { setBusy(''); }
  };

  const g = data?.gabungan || {};
  const per = data?.per_toko || [];

  return (
    <div className="space-y-5" data-testid="weekly-report-module">
      <PageHeader
        eyebrow="PORTAL MARKETING · LAPORAN"
        title="Laporan Rapat Mingguan"
        subtitle="Per toko & gabungan — siap dibacakan, dicetak, dan diarsipkan"
        icon={CalendarRange}
        actions={(
          <>
            <Button variant="outline" size="sm" onClick={load} data-testid="weekly-refresh">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Muat Ulang
            </Button>
            <Button variant="outline" size="sm" onClick={() => download('excel')}
              disabled={busy === 'excel'} data-testid="weekly-export-excel">
              {busy === 'excel' ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                : <Download className="w-3.5 h-3.5 mr-1.5" />} Excel
            </Button>
            <Button size="sm" onClick={() => download('pdf')}
              disabled={busy === 'pdf'} data-testid="weekly-export-pdf">
              {busy === 'pdf' ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                : <FileText className="w-3.5 h-3.5 mr-1.5" />} PDF
            </Button>
          </>
        )}
      />

      <div className="rounded-[var(--radius-md)] border border-border bg-[hsl(var(--card))] p-3
        flex flex-wrap items-end gap-3">
        <Button variant="outline" size="sm" onClick={() => shift(-7)} data-testid="weekly-prev">
          <ChevronLeft className="w-3.5 h-3.5" /> Minggu lalu
        </Button>
        <div>
          <Label className="text-xs">Minggu (tanggal apa pun di minggu itu)</Label>
          <GlassInput type="date" value={weekStart} data-testid="weekly-date"
            onChange={(e) => e.target.value && setWeekStart(mondayOf(e.target.value))} />
        </div>
        <Button variant="outline" size="sm" onClick={() => shift(7)} data-testid="weekly-next">
          Minggu depan <ChevronRight className="w-3.5 h-3.5" />
        </Button>
        <div className="min-w-[220px]">
          <Label className="text-xs">Lingkup</Label>
          <Select value={accountId || '__all__'}
            onValueChange={(v) => setAccountId(v === '__all__' ? '' : v)}>
            <SelectTrigger data-testid="weekly-account" className="h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Semua Toko + Gabungan</SelectItem>
              {accounts.map((a) => (
                <SelectItem key={a.id} value={a.id}>{a.account_name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {data?.periode && (
          <div className="ml-auto text-right">
            <p className="text-sm font-bold" data-testid="weekly-period-label">
              {data.periode.minggu} · {data.periode.label}
            </p>
            <p className="text-[11px] text-muted-foreground">
              {data.periode.dasar_minggu} · pembanding: {data.periode.minggu_sebelumnya?.label}
            </p>
          </div>
        )}
      </div>

      {loading ? (
        <div className="space-y-2">{[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : !data ? null : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
            <Tile label="Omzet gabungan" value={rp(g.omzet)} testId="weekly-tile-omzet"
              sub={<>vs minggu lalu <Delta d={g.vs_minggu_lalu?.omzet} /></>} />
            {/* SESI #9 — omzet setelah retur, berdampingan dengan bruto */}
            <Tile label="Setelah retur" value={rp(g.omzet_setelah_retur)}
              testId="weekly-tile-setelah-retur"
              sub={(g.retur || 0) > 0
                ? <>retur {num(g.retur)} pesanan · {rp(g.nilai_retur)}</>
                : 'tidak ada retur minggu ini'} />
            <Tile label="Pesanan" value={num(g.pesanan)} sub={`${num(g.pcs)} pcs`}
              testId="weekly-tile-pesanan" />
            <Tile label="AOV" value={rp(g.aov)} testId="weekly-tile-aov" />
            <Tile label="Target prorata" value={rp(g.target_prorata)}
              sub={`capai ${pct(g.pencapaian_target_persen)}`} testId="weekly-tile-target" />
            <Tile label="Belanja iklan" value={rp(g.iklan_spend)}
              sub={`ROAS ${g.roas ?? '—'}`} testId="weekly-tile-iklan" />
            <Tile label="Belum dikirim" value={num(g.belum_dikirim)} tone="text-amber-500"
              sub={rp(g.nilai_belum_dikirim)} testId="weekly-tile-belum-kirim" />
          </div>

          {(data.catatan_data || []).length > 0 && (
            <div className="rounded-[var(--radius-md)] border border-amber-500/40 bg-amber-500/5 p-3"
              data-testid="weekly-data-notes">
              <p className="text-xs font-semibold mb-1.5 flex items-center gap-1.5">
                <Info className="w-4 h-4 text-amber-500" />
                Catatan kejujuran data — wajib dibaca sebelum menyimpulkan
              </p>
              <ol className="list-decimal ml-5 space-y-1">
                {data.catatan_data.map((n, i) => (
                  <li key={i} className="text-xs">{n}</li>
                ))}
              </ol>
            </div>
          )}

          <div className="rounded-[var(--radius-md)] border border-border bg-[hsl(var(--card))] overflow-x-auto">
            <table className="w-full text-xs" data-testid="weekly-table">
              <thead className="bg-muted/60"><tr>
                {['Kode', 'Toko', 'Omzet', 'Retur', 'Setelah retur', 'vs Mg lalu', 'Pesanan', 'Pcs', 'AOV',
                  'Target prorata', 'Capai', 'Live', 'Video', 'Kartu Produk',
                  'Pemenuhan', 'Batal', 'Belum kirim', 'Iklan', 'ROAS', 'Hari berdata',
                  'Sumber angka'].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-semibold whitespace-nowrap">{h}</th>))}
              </tr></thead>
              <tbody>
                {per.map((s) => (
                  <tr key={s.account_id} className="border-t border-border hover:bg-muted/30"
                    data-testid={`weekly-row-${s.account_code}`}>
                    <td className="px-3 py-2 font-mono">{s.account_code}</td>
                    <td className="px-3 py-2 font-medium">{s.account_name}</td>
                    <td className="px-3 py-2 tabular-nums font-semibold">{rp(s.omzet)}</td>
                    <td className="px-3 py-2 tabular-nums"
                      data-testid={`weekly-retur-${s.account_code}`}>
                      {(s.nilai_retur || 0) > 0
                        ? <span className="text-amber-600 dark:text-amber-400">
                          {rp(s.nilai_retur)} <span className="text-[10px] text-muted-foreground">· {num(s.pesanan_mentah?.retur)} pesanan</span>
                        </span>
                        : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-3 py-2 tabular-nums font-semibold">{rp(s.omzet_setelah_retur)}</td>
                    <td className="px-3 py-2"><Delta d={s.vs_minggu_lalu?.omzet} /></td>
                    <td className="px-3 py-2 tabular-nums">{num(s.pesanan)}</td>
                    <td className="px-3 py-2 tabular-nums">{num(s.pcs)}</td>
                    <td className="px-3 py-2 tabular-nums">{rp(s.aov)}</td>
                    <td className="px-3 py-2 tabular-nums">
                      {s.target?.lengkap ? rp(s.target.revenue)
                        : <span className="text-muted-foreground">belum ada target</span>}
                    </td>
                    <td className="px-3 py-2 tabular-nums">{pct(s.pencapaian_target_persen)}</td>
                    <td className="px-3 py-2 tabular-nums">{rp(s.kanal?.live)}</td>
                    <td className="px-3 py-2 tabular-nums">{rp(s.kanal?.video)}</td>
                    <td className="px-3 py-2 tabular-nums">{rp(s.kanal?.product_card)}</td>
                    <td className="px-3 py-2 tabular-nums">{pct(s.pemenuhan?.fulfillment_rate)}</td>
                    <td className="px-3 py-2 tabular-nums">{num(s.pesanan_mentah?.batal)}</td>
                    <td className="px-3 py-2 tabular-nums">{num(s.pesanan_mentah?.belum_dikirim)}</td>
                    <td className="px-3 py-2 tabular-nums">
                      {s.iklan?.terisi ? rp(s.iklan.spend)
                        : <span className="text-muted-foreground">belum diimpor</span>}
                    </td>
                    <td className="px-3 py-2 tabular-nums">{s.iklan?.roas ?? '—'}</td>
                    <td className="px-3 py-2 tabular-nums">{s.hari_berdata}/7</td>
                    <td className="px-3 py-2">
                      {(s.sumber_angka || []).length === 0
                        ? <span className="text-muted-foreground">—</span>
                        : (s.sumber_angka || []).map((src) => (
                          <Badge key={src} variant="outline" className="text-[10px] mr-1">
                            {src === 'orders_auto' ? 'turunan pesanan'
                              : src === 'manual_override' ? 'diganti SPV'
                                : src === 'import' ? 'impor rekap' : src}
                          </Badge>
                        ))}
                    </td>
                  </tr>
                ))}
                <tr className="border-t-2 border-border bg-muted/40 font-semibold">
                  <td className="px-3 py-2" colSpan={2}>GABUNGAN ({g.toko_berdata}/{g.toko} toko berdata)</td>
                  <td className="px-3 py-2 tabular-nums">{rp(g.omzet)}</td>
                  <td className="px-3 py-2 tabular-nums">
                    {(g.nilai_retur || 0) > 0 ? rp(g.nilai_retur) : '—'}
                  </td>
                  <td className="px-3 py-2 tabular-nums">{rp(g.omzet_setelah_retur)}</td>
                  <td className="px-3 py-2"><Delta d={g.vs_minggu_lalu?.omzet} /></td>
                  <td className="px-3 py-2 tabular-nums">{num(g.pesanan)}</td>
                  <td className="px-3 py-2 tabular-nums">{num(g.pcs)}</td>
                  <td className="px-3 py-2 tabular-nums">{rp(g.aov)}</td>
                  <td className="px-3 py-2 tabular-nums">{rp(g.target_prorata)}</td>
                  <td className="px-3 py-2 tabular-nums">{pct(g.pencapaian_target_persen)}</td>
                  <td className="px-3 py-2 tabular-nums">{rp(g.kanal?.live)}</td>
                  <td className="px-3 py-2 tabular-nums">{rp(g.kanal?.video)}</td>
                  <td className="px-3 py-2 tabular-nums">{rp(g.kanal?.product_card)}</td>
                  <td className="px-3 py-2">—</td>
                  <td className="px-3 py-2 tabular-nums">{num(g.batal)}</td>
                  <td className="px-3 py-2 tabular-nums">{num(g.belum_dikirim)}</td>
                  <td className="px-3 py-2 tabular-nums">{rp(g.iklan_spend)}</td>
                  <td className="px-3 py-2 tabular-nums">{g.roas ?? '—'}</td>
                  <td className="px-3 py-2">—</td>
                  <td className="px-3 py-2">—</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="rounded-[var(--radius-md)] border border-border bg-[hsl(var(--card))] p-3">
            <p className="text-xs font-semibold mb-2">Pecahan omzet per kanal (gabungan)</p>
            <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5" data-testid="weekly-kanal">
              {KANAL.map(([k, label]) => (
                <div key={k} className="rounded-[var(--radius-sm)] border border-border p-2">
                  <p className="text-[11px] text-muted-foreground">{label}</p>
                  <p className="text-sm font-semibold tabular-nums">{rp(g.kanal?.[k])}</p>
                  <p className="text-[10px] text-muted-foreground">{g.kanal_persen?.[k] ?? 0}%</p>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
