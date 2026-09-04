/**
 * SettlementByStoreCards — kartu ringkas per toko untuk satu bulan: berapa persen omzet bruto
 * yang dipotong platform, dipecah komisi/iklan/refund, supaya Shopee vs TikTok bisa dibandingkan.
 */
import { useCallback, useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, Store, Loader2, AlertTriangle } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { toast } from 'sonner';
import { formatRupiah as rp } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;

function monthLabel(m) {
  if (!m) return '—';
  const [y, mo] = m.split('-');
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
  return `${names[parseInt(mo, 10) - 1] || mo} ${y}`;
}

function pctTone(p, avg) {
  if (p > avg + 2) return 'text-red-600 dark:text-red-300';
  if (p < avg - 2) return 'text-emerald-600 dark:text-emerald-300';
  return 'text-amber-600 dark:text-amber-300';
}

export function SettlementByStoreCards({ refreshKey, month: monthProp = '' }) {
  const [month, setMonth] = useState(monthProp);
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(true);

  // Filter bulan di daftar pencairan ikut menggerakkan kartu ini (satu periode, satu layar).
  useEffect(() => { setMonth(monthProp); }, [monthProp]);

  const load = useCallback(async (m) => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/marketing/settlements/by-account?month=${m || ''}`,
        { headers: { Authorization: `Bearer ${localStorage.getItem('erp_token')}` } });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal memuat ringkasan per toko');
      setRes(d);
      if (!m) setMonth(d.month);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(month); }, [month, load, refreshKey]);

  const months = res?.months || [];
  const idx = months.indexOf(res?.month);
  const step = (dir) => {
    const next = months[idx + dir];
    if (next) setMonth(next);
  };

  return (
    <GlassCard className="p-4 space-y-3" data-testid="fin-settlement-by-store">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium text-sm flex items-center gap-2">
          <Store className="w-4 h-4" /> Potongan per toko
          <span className="text-xs text-foreground/50">
            rata-rata {res?.average_deduction_pct ?? 0}% dari bruto
          </span>
        </h3>
        <div className="flex items-center gap-1 text-sm">
          <button data-testid="fin-settlement-by-store-prev" onClick={() => step(1)}
            disabled={idx < 0 || idx >= months.length - 1}
            className="p-1 rounded hover:bg-foreground/10 disabled:opacity-30"><ChevronLeft className="w-4 h-4" /></button>
          <input type="month" data-testid="fin-settlement-by-store-month" value={res?.month || month}
            onChange={(e) => setMonth(e.target.value)}
            className="h-8 bg-foreground/5 border border-foreground/10 rounded-lg px-2 text-xs" />
          <button data-testid="fin-settlement-by-store-next" onClick={() => step(-1)}
            disabled={idx <= 0}
            className="p-1 rounded hover:bg-foreground/10 disabled:opacity-30"><ChevronRight className="w-4 h-4" /></button>
        </div>
      </div>

      {loading ? (
        <div className="py-6 text-center text-xs text-foreground/50 flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> memuat…
        </div>
      ) : !res?.data?.length ? (
        <div className="py-6 text-center text-xs text-foreground/50" data-testid="fin-settlement-by-store-empty">
          Belum ada pencairan tercatat untuk {monthLabel(res?.month)}.
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {res.data.map((s) => (
            <div key={s.account_id} className="rounded-xl bg-foreground/5 p-3 space-y-1.5"
              data-testid={`fin-settlement-store-card-${s.account_id}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">{s.account_name}</div>
                  <div className="text-[10px] uppercase tracking-wide text-foreground/50">
                    {s.platform} · {s.count} pencairan
                  </div>
                </div>
                <div className={`text-xl font-semibold tabular-nums ${pctTone(s.deduction_pct, res.average_deduction_pct)}`}>
                  {s.deduction_pct}%
                </div>
              </div>
              <div className="h-1.5 rounded-full bg-foreground/10 overflow-hidden">
                <div className="h-full bg-amber-500" style={{ width: `${Math.min(100, s.deduction_pct)}%` }} />
              </div>
              <div className="grid grid-cols-3 gap-1 text-[10px] text-foreground/60">
                <div>komisi <b>{s.commission_pct}%</b></div>
                <div>iklan <b>{s.ads_pct}%</b></div>
                <div>refund <b>{s.refund_pct}%</b></div>
              </div>
              <div className="text-xs text-foreground/70">
                bruto {rp(s.gross_sales)} → cair <b>{rp(s.net_payout)}</b>
              </div>
              {s.unverified_count > 0 ? (
                <div className="text-[10px] text-red-600 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> {s.unverified_count} belum seimbang
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </GlassCard>
  );
}
