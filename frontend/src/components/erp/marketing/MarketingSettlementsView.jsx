/**
 * MarketingSettlementsView — **Pencairan (Settlement) Marketplace** di portal Marketing.
 *
 * Kenapa layar ini ada (diukur sesi #34): backend `/api/marketing/settlements`
 * sudah lengkap sejak F9 (input manual, verifikasi selisih, jurnal draft), tetapi
 * TIDAK ADA satu pun layar yang memanggilnya — jadi pemilik bertanya "di mana menu
 * pencairan akun marketplace?" Jawabannya: memang belum pernah ada pintunya.
 *
 * Keputusan pemilik (2026-08-23): **Marketing hanya MELIHAT**; input & jurnal tetap
 * milik Finance. Jadi layar ini sengaja tanpa tombol simpan/hapus — yang dibawanya
 * adalah ANGKA: total pencairan, potongan platform, dan selisih yang belum bernama,
 * disamakan bentuknya dengan kartu KPI sales supaya bisa dibaca sekali lihat.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Banknote, RefreshCw, AlertTriangle, CheckCircle2, Loader2, Store, Percent,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import ExportCsvButton from '@/components/ui/export-csv-button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;
const rp = formatRupiah;

function Kpi({ label, value, hint, tone = 'default', testId, icon: Icon }) {
  const tones = {
    default: 'text-foreground',
    good: 'text-emerald-600 dark:text-emerald-300',
    warn: 'text-amber-600 dark:text-amber-300',
    bad: 'text-red-600 dark:text-red-300',
  };
  return (
    <GlassCard className="p-4" data-testid={testId}>
      <div className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-foreground/50">
        {Icon ? <Icon className="w-3.5 h-3.5" /> : null}{label}
      </div>
      <div className={`mt-1 text-2xl font-semibold ${tones[tone]}`}>{value}</div>
      {hint ? <div className="mt-1 text-xs text-foreground/50">{hint}</div> : null}
    </GlassCard>
  );
}

export default function MarketingSettlementsView({ token, accounts: accountsProp }) {
  const [accounts, setAccounts] = useState(accountsProp || []);
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [accountId, setAccountId] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ page_size: '50' });
      if (accountId) qs.set('account_id', accountId);
      const r = await fetch(`${API}/api/marketing/settlements?${qs}`,
        { headers: { Authorization: `Bearer ${token}` } });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal memuat pencairan');
      setRows(d.data || []);
      setSummary(d.summary || null);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, accountId]);

  useEffect(() => { load(); }, [load]);

  // Modul bisa dibuka langsung dari nav (tanpa prop dari hub) — daftar toko
  // diambil sendiri supaya filter & nama toko tetap terbaca.
  useEffect(() => {
    if ((accountsProp || []).length) { setAccounts(accountsProp); return; }
    fetch(`${API}/api/marketing/accounts?limit=200`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json())
      // Endpoint ini menjawab ARRAY langsung (bukan {accounts: []}) — ketiga
      // bentuk ditangani supaya filter toko tidak diam-diam kosong.
      .then((d) => setAccounts(Array.isArray(d) ? d : (d?.accounts || d?.data || [])))
      .catch(() => {});
  }, [accountsProp, token]);

  const accName = (id) => (accounts.find((a) => a.id === id)?.account_name) || id || '—';

  return (
    <div className="space-y-4" data-testid="marketing-settlements-view">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Banknote className="w-5 h-5" /> Pencairan Marketplace
          </h2>
          <p className="text-xs text-foreground/60 mt-0.5">
            Uang yang benar-benar masuk rekening dari Shopee/TikTok, beserta potongan
            platformnya. <b>Marketing hanya melihat</b> — pencatatan & jurnal dikerjakan di
            <b> Portal Keuangan → Kas, Bank & Biaya → Pencairan Marketplace</b>.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select data-testid="settlement-account-filter" value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            className="h-9 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-sm">
            <option value="">Semua toko</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>{a.account_name} · {a.platform}</option>
            ))}
          </select>
          {/* Unduh memakai BARIS YANG TERLIHAT (bukan kueri ulang) — angka di
              layar dan angka di berkas tidak boleh bisa berbeda. */}
          <ExportCsvButton
            testId="settlement-export-csv"
            filename="pencairan-marketplace"
            rows={rows.map((r) => ({
              tanggal: r.settlement_date || '',
              no_pencairan: r.settlement_id,
              toko: accName(r.account_id),
              platform: r.platform,
              bruto: r.gross_sales || 0,
              potongan: r.total_deductions || 0,
              potongan_pct: r.deduction_pct || 0,
              dicairkan: r.net_payout || 0,
              status: r.math_verified ? 'seimbang' : `selisih ${r.net_payout_diff || 0}`,
              sudah_dijurnal: r.je_number ? `${r.je_number} (${r.je_status || ''})` : 'belum',
            }))}
          />
          <button data-testid="settlement-refresh" onClick={load}
            className="h-9 px-3 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-sm flex items-center gap-1.5">
            <RefreshCw className="w-4 h-4" /> Muat ulang
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi testId="settlement-kpi-net" icon={Banknote} label="Total dicairkan"
          value={rp(summary?.net_payout || 0)} tone="good"
          hint={`${rows.length} pencairan tercatat`} />
        <Kpi testId="settlement-kpi-gross" icon={Store} label="Omzet bruto terkait"
          value={rp(summary?.gross_sales || 0)} />
        <Kpi testId="settlement-kpi-ded" icon={Percent} label="Potongan platform"
          value={rp(summary?.total_deductions || 0)}
          hint={`${summary?.deduction_pct || 0}% dari bruto`} tone="warn" />
        <Kpi testId="settlement-kpi-unverified" icon={AlertTriangle} label="Belum seimbang"
          value={`${summary?.unverified_count || 0} dokumen`}
          tone={(summary?.unverified_count || 0) > 0 ? 'bad' : 'good'}
          hint="selisih belum diberi nama — belum boleh dijurnal" />
      </div>

      <GlassCard className="p-0 overflow-hidden">
        {loading ? (
          <div className="py-12 text-center text-sm text-foreground/50 flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> memuat pencairan…
          </div>
        ) : rows.length === 0 ? (
          <div className="py-12 text-center text-sm text-foreground/60 px-6" data-testid="settlement-empty">
            Belum ada pencairan tercatat{accountId ? ' untuk toko ini' : ''}.
            <div className="mt-1 text-xs text-foreground/50">
              Finance mencatat pencairan dari mutasi bank / laporan platform. Kalau angka
              di sini kosong padahal uang sudah masuk, mintakan pencatatannya ke Finance —
              layar ini tidak pernah mengarang angka.
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="settlement-table">
              <thead>
                <tr className="text-xs uppercase tracking-wide text-foreground/50 border-b border-foreground/10">
                  <th className="text-left py-2 px-3">Tanggal</th>
                  <th className="text-left py-2 px-3">No. Pencairan</th>
                  <th className="text-left py-2 px-3">Toko / Platform</th>
                  <th className="text-right py-2 px-3">Bruto</th>
                  <th className="text-right py-2 px-3">Potongan</th>
                  <th className="text-right py-2 px-3">Dicairkan</th>
                  <th className="text-left py-2 px-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-foreground/5"
                    data-testid={`settlement-row-${r.settlement_id}`}>
                    <td className="py-2 px-3">{r.settlement_date || '—'}</td>
                    <td className="py-2 px-3 font-mono text-xs">{r.settlement_id}</td>
                    <td className="py-2 px-3">
                      {accName(r.account_id)}
                      <span className="ml-1 text-xs text-foreground/50 uppercase">{r.platform}</span>
                    </td>
                    <td className="py-2 px-3 text-right">{rp(r.gross_sales || 0)}</td>
                    <td className="py-2 px-3 text-right text-amber-600 dark:text-amber-300">
                      {rp(r.total_deductions || 0)}
                      {r.deduction_pct ? (
                        <span className="text-xs text-foreground/50"> ({r.deduction_pct}%)</span>
                      ) : null}
                    </td>
                    <td className="py-2 px-3 text-right font-medium">{rp(r.net_payout || 0)}</td>
                    <td className="py-2 px-3">
                      {r.math_verified ? (
                        <Badge variant="outline" className="text-[10px] text-emerald-600">
                          <CheckCircle2 className="w-3 h-3 mr-1" /> seimbang
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-[10px] text-red-600">
                          <AlertTriangle className="w-3 h-3 mr-1" /> selisih {rp(r.net_payout_diff || 0)}
                        </Badge>
                      )}
                      {r.je_number ? (
                        <span className="ml-1 text-[10px] text-foreground/50">
                          {r.je_number} ({r.je_status})
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
