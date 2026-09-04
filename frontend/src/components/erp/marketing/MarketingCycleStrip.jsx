import { useEffect, useState, useMemo } from 'react';
import { Target, Wallet, TrendingUp, AlertTriangle, Info } from 'lucide-react';
import { GlassPanel } from '@/components/ui/glass';
import { formatRupiah } from '@/lib/format';

// FASE D (2026-08-16) — angka RESMI satu bulan kerja marketing, diambil apa adanya
// dari SSOT `core/marketing_cycle.py` lewat `GET /api/marketing/cycle/overview`.
//
// Kenapa tidak dihitung di layar ini: target, omzet, anggaran, dan ROI dipakai
// bersama oleh Portal Marketing, Portal Manajemen, dan lampiran ekspor. Begitu
// browser ikut menjumlah, tiga tempat itu bisa menampilkan tiga angka untuk satu
// pertanyaan yang sama — dan yang salah tidak akan pernah kelihatan salah.
// Semua penjumlahan, peringkat, dan persentase di bawah datang dari `totals`.

const API_BASE = process.env.REACT_APP_BACKEND_URL;

const compact = (n) => {
  const v = Number(n || 0);
  if (v >= 1_000_000_000) return `Rp ${(v / 1_000_000_000).toFixed(1)}M`;
  if (v >= 1_000_000) return `Rp ${(v / 1_000_000).toFixed(1)}jt`;
  if (v >= 1_000) return `Rp ${(v / 1_000).toFixed(0)}rb`;
  return formatRupiah(v);
};

const monthLabel = (period) => {
  if (!period) return '';
  const [y, m] = period.split('-');
  const names = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli',
    'Agustus', 'September', 'Oktober', 'November', 'Desember'];
  return `${names[Number(m) - 1] || m} ${y}`;
};

function Stat({ testId, icon: Icon, label, value, foot, tone = 'default' }) {
  const tones = {
    default: 'text-foreground',
    warn: 'text-amber-600 dark:text-amber-400',
    bad: 'text-red-600 dark:text-red-400',
    good: 'text-emerald-600 dark:text-emerald-400',
  };
  return (
    <GlassPanel className="p-5" data-testid={testId}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs uppercase text-muted-foreground tracking-wider">{label}</div>
        <Icon className="w-4 h-4 text-primary" />
      </div>
      <div className={`text-2xl font-bold tabular-nums ${tones[tone]}`}>{value}</div>
      <div className="text-xs text-muted-foreground mt-1">{foot}</div>
    </GlassPanel>
  );
}

export function MarketingCycleStrip({ token, period }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  useEffect(() => {
    if (!period) return;
    let alive = true;
    setErr('');
    fetch(`${API_BASE}/api/marketing/cycle/overview?period=${period}`, { headers })
      .then(async (r) => {
        if (!r.ok) throw new Error(`gagal memuat siklus (HTTP ${r.status})`);
        return r.json();
      })
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setErr(e.message); });
    return () => { alive = false; };
  }, [period, headers]);

  if (err) {
    return (
      <GlassPanel className="p-4 text-sm text-red-600 dark:text-red-400"
        data-testid="cycle-strip-error">
        Angka siklus bulan {monthLabel(period)} tidak bisa dimuat: {err}
      </GlassPanel>
    );
  }
  if (!data) {
    return <GlassPanel className="p-5 text-sm text-muted-foreground"
      data-testid="cycle-strip-loading">Memuat angka siklus bulan {monthLabel(period)}…</GlassPanel>;
  }

  const t = data.totals || {};
  const revTone = t.revenue_pct >= t.pace_pct ? 'good' : (t.revenue_pct >= t.pace_pct * 0.7 ? 'warn' : 'bad');
  const budgetTone = t.total_used_pct >= 100 ? 'bad' : (t.total_used_pct >= 80 ? 'warn' : 'default');
  const attention = data.attention || [];

  return (
    <div className="space-y-3" data-testid="marketing-cycle-strip">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-base font-semibold text-foreground">
          Siklus {monthLabel(period)} — angka resmi
        </h3>
        <span className="text-xs text-muted-foreground" data-testid="cycle-strip-progress">
          hari ke-{data.progress?.days_elapsed} dari {data.progress?.days_total} ·
          {' '}{t.accounts} toko · {t.accounts_with_target} bertarget
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Stat testId="cycle-target" icon={Target} label="Target vs Omzet"
          value={`${(t.revenue_pct ?? 0).toFixed(1)}%`} tone={revTone}
          foot={`${compact(t.revenue)} dari ${compact(t.target_revenue)} · laju bulan ${(t.pace_pct ?? 0).toFixed(0)}%`} />
        <Stat testId="cycle-budget" icon={Wallet} label="Anggaran Terpakai"
          value={`${(t.total_used_pct ?? 0).toFixed(1)}%`} tone={budgetTone}
          foot={`${compact(t.total_spend)} dari ${compact(t.total_plan)} · sisa ${compact(t.total_remaining)}`} />
        <Stat testId="cycle-roas" icon={TrendingUp} label="ROAS · ROI"
          value={`${(t.roas ?? 0).toFixed(2)}×`}
          tone={t.roi_reliable ? (t.roi_pct >= 0 ? 'good' : 'bad') : 'warn'}
          foot={t.roi_reliable
            ? `ROI ${(t.roi_pct ?? 0).toFixed(1)}% · laba kotor ${compact(t.gross_profit)}`
            : `ROI belum bisa dipercaya — HPP baru ${(t.hpp_coverage_pct ?? 0).toFixed(0)}% unit`} />
        <Stat testId="cycle-attention" icon={AlertTriangle} label="Perlu Perhatian"
          value={`${t.flags_red ?? 0} merah`}
          tone={(t.flags_red ?? 0) > 0 ? 'bad' : ((t.flags_yellow ?? 0) > 0 ? 'warn' : 'good')}
          foot={`${t.flags_yellow ?? 0} kuning · ${attention.length} toko ditandai`} />
      </div>

      {attention.length > 0 && (
        <GlassPanel className="p-3" data-testid="cycle-attention-list">
          <div className="text-xs text-muted-foreground mb-2">
            Toko yang ditandai (peringkat dari backend, bukan urutan layar):
          </div>
          <div className="flex flex-wrap gap-2">
            {attention.slice(0, 6).map(a => (
              <span key={a.account_id}
                data-testid={`cycle-attention-${a.account_code || a.account_id}`}
                className="text-xs px-2 py-1 rounded-full border border-[var(--glass-border)] bg-[var(--glass-bg)] text-foreground">
                {a.account_name}
                <span className="text-muted-foreground"> · {a.flags.length} tanda</span>
              </span>
            ))}
          </div>
        </GlassPanel>
      )}

      <div className="flex items-start gap-2 text-xs text-muted-foreground">
        <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
        <span data-testid="cycle-strip-note">
          {data.label} Angka di atas adalah <b>rekap turunan sebulan penuh</b> (menghormati
          koreksi SPV), sedangkan kartu di bawah menjumlah <b>input harian pada rentang tanggal
          yang dipilih</b> — kalau rentangnya bukan satu bulan penuh, keduanya memang berbeda.
        </span>
      </div>
    </div>
  );
}

export default MarketingCycleStrip;
