/**
 * KPIGamificationTab — P3 Gamification
 * Leaderboard, Badge, Achievement, Gamification Summary
 * Digunakan di HRKPIModule (admin) dan KPIPortalModule (employee self-service)
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import axios from 'axios';

const B = process.env.REACT_APP_BACKEND_URL;

// ─── Badge Card ───────────────────────────────────────────────────────────────
export function BadgeChip({ badge, size = 'sm' }) {
  const sizeClass = size === 'lg' ? 'text-2xl px-4 py-2 gap-2' : 'text-sm px-2.5 py-1 gap-1.5';
  return (
    <span
      className={`inline-flex items-center rounded-full font-medium border ${sizeClass}`}
      style={{ borderColor: badge.badge_color || '#888', color: badge.badge_color || '#888', background: (badge.badge_color || '#888') + '18' }}
      title={badge.badge_desc || badge.badge_label}
    >
      <span>{badge.badge_emoji || '🏅'}</span>
      <span>{badge.badge_label}</span>
    </span>
  );
}

// ─── Podium ───────────────────────────────────────────────────────────────────
function Podium({ top3 }) {
  if (!top3 || top3.length === 0) return null;
  const [first, second, third] = [top3[0], top3[1], top3[2]];
  const podiumColors = ['#F59E0B', '#9CA3AF', '#B45309'];
  const heights = ['h-28', 'h-20', 'h-16'];
  const emojis = ['🥇', '🥈', '🥉'];
  const order = [second, first, third];  // 2-1-3 visual order
  const orderRanks = [1, 0, 2];

  return (
    <div className="flex items-end justify-center gap-4 py-6">
      {order.map((entry, idx) => {
        const realIdx = orderRanks[idx];
        if (!entry) return <div key={idx} className="w-24" />;
        return (
          <div key={idx} className="flex flex-col items-center gap-2">
            {/* Avatar */}
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center text-xl font-bold border-2"
              style={{ borderColor: podiumColors[realIdx], background: podiumColors[realIdx] + '22', color: podiumColors[realIdx] }}
            >
              {entry.employee_name?.charAt(0) || '?'}
            </div>
            <div className="text-center">
              <div className="text-xs font-semibold truncate max-w-[90px]">{entry.employee_name}</div>
              <div className="text-xs text-muted-foreground">{entry.score}</div>
            </div>
            {/* Podium block */}
            <div
              className={`w-24 ${heights[realIdx]} rounded-t-lg flex flex-col items-center justify-center`}
              style={{ background: podiumColors[realIdx] + '33', borderTop: `3px solid ${podiumColors[realIdx]}` }}
            >
              <span className="text-2xl">{emojis[realIdx]}</span>
              <span className="text-xs font-bold" style={{ color: podiumColors[realIdx] }}>#{realIdx + 1}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Leaderboard Table ────────────────────────────────────────────────────────
function LeaderboardTable({ entries }) {
  if (!entries || entries.length === 0) return (
    <div className="text-center py-10 text-muted-foreground text-sm">Belum ada data leaderboard.</div>
  );
  return (
    <div className="space-y-2 mt-2">
      {entries.map((e) => (
        <div
          key={e.employee_id}
          className={`flex items-center gap-3 p-3 rounded-xl border transition-colors ${
            e.rank <= 3 ? 'bg-[var(--glass-bg)] border-[var(--glass-border)]' : 'bg-transparent border-transparent hover:bg-[var(--glass-bg)]'
          }`}
        >
          {/* Rank */}
          <div className="w-8 text-center">
            {e.rank === 1 ? '🥇' : e.rank === 2 ? '🥈' : e.rank === 3 ? '🥉' : (
              <span className="text-sm font-bold text-muted-foreground">#{e.rank}</span>
            )}
          </div>
          {/* Avatar */}
          <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm shrink-0">
            {e.employee_name?.charAt(0) || '?'}
          </div>
          {/* Info */}
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold truncate">{e.employee_name}</div>
            <div className="text-xs text-muted-foreground">{e.employee_code} {e.department && `· ${e.department}`}</div>
          </div>
          {/* Badges */}
          {e.badges && e.badges.length > 0 && (
            <div className="flex gap-1 flex-wrap justify-end max-w-[140px]">
              {e.badges.slice(0, 3).map((b, i) => (
                <span key={i} title={b.badge_label} className="text-base">{b.badge_emoji}</span>
              ))}
              {e.badges.length > 3 && <span className="text-xs text-muted-foreground">+{e.badges.length - 3}</span>}
            </div>
          )}
          {/* Score */}
          <div className="text-right shrink-0">
            <div className="text-base font-bold text-primary">{e.score}</div>
            <div className={`text-xs font-medium ${e.delta === null || e.delta === undefined ? 'text-muted-foreground' : e.delta >= 0 ? 'text-emerald-500' : 'text-red-700 dark:text-red-500'}`}>
              {e.delta === null || e.delta === undefined ? '—' : e.delta >= 0 ? `▲ ${e.delta}` : `▼ ${Math.abs(e.delta)}`}
            </div>
          </div>
          {/* Grade */}
          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
            e.grade === 'A' ? 'bg-emerald-100 text-emerald-700' :
            e.grade === 'B' ? 'bg-blue-100 text-blue-700' :
            e.grade === 'C' ? 'bg-yellow-100 text-yellow-700' :
            'bg-red-100 text-red-700'
          }`}>
            {e.grade || '-'}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Achievement Panel ────────────────────────────────────────────────────────
function AchievementPanel({ employeeId, token }) {
  const [data, setData] = useState(null);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  useEffect(() => {
    if (!employeeId) return;
    axios.get(`${B}/api/dewi/kpi/achievements/${employeeId}`, { headers })
      .then(r => setData(r.data))
      .catch(console.error);
  }, [employeeId, headers]);

  if (!data) return <div className="py-4 text-center text-sm text-muted-foreground">Memuat pencapaian...</div>;

  if (data.total === 0) return (
    <div className="text-center py-8 text-muted-foreground text-sm">
      <div className="text-4xl mb-2">🏅</div>
      Belum ada badge yang diraih. Ikuti KPI untuk mendapatkan achievement!
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Summary chips */}
      <div className="flex flex-wrap gap-2">
        {data.summary.map(s => (
          <BadgeChip key={s.badge_type} badge={s} size="lg" />
        ))}
      </div>
      {/* Badge list */}
      <div className="space-y-2">
        {data.badges.map((b, i) => (
          <div key={i} className="flex items-center gap-3 p-3 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)]">
            <span className="text-2xl">{b.badge_emoji}</span>
            <div className="flex-1">
              <div className="font-semibold text-sm">{b.badge_label}</div>
              <div className="text-xs text-muted-foreground">{b.badge_desc}</div>
            </div>
            <div className="text-xs text-muted-foreground">
              {b.earned_at ? new Date(b.earned_at).toLocaleDateString('id-ID', { day:'numeric', month:'short', year:'numeric' }) : ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── HR Gamification Summary ──────────────────────────────────────────────────
function GamificationSummaryPanel({ token }) {
  const [data, setData] = useState(null);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  useEffect(() => {
    axios.get(`${B}/api/dewi/kpi/gamification/summary`, { headers })
      .then(r => setData(r.data))
      .catch(console.error);
  }, [headers]);

  if (!data) return <div className="py-4 text-center text-sm text-muted-foreground animate-pulse">Memuat ringkasan...</div>;

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Total Badge', value: data.total_badges_awarded, emoji: '🏅' },
          { label: 'Tipe Badge', value: data.badge_types_available, emoji: '🎨' },
          { label: 'Top Earner', value: data.top_earners?.[0]?.employee_name?.split(' ')[0] || '-', emoji: '🏆' },
          { label: 'Badge Terbanyak', value: data.top_earners?.[0]?.badge_count || 0, emoji: '⭐' },
        ].map((s, i) => (
          <div key={i} className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-xl p-4 text-center">
            <div className="text-2xl mb-1">{s.emoji}</div>
            <div className="text-xl font-bold">{s.value}</div>
            <div className="text-xs text-muted-foreground">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Badge Distribution */}
        <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-xl p-5">
          <h3 className="font-semibold mb-3 text-sm">Distribusi Badge</h3>
          {data.badge_distribution.length === 0 ? (
            <p className="text-xs text-muted-foreground">Belum ada badge.</p>
          ) : (
            <div className="space-y-2">
              {data.badge_distribution.map(b => (
                <div key={b.badge_type} className="flex items-center gap-3">
                  <span className="text-lg w-7 text-center">{b.badge_emoji}</span>
                  <div className="flex-1">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-medium">{b.badge_label}</span>
                      <span className="text-muted-foreground">{b.count}</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${Math.min(100, (b.count / (data.total_badges_awarded || 1)) * 100)}%`,
                          background: b.badge_color || '#888'
                        }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Top Earners */}
        <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-xl p-5">
          <h3 className="font-semibold mb-3 text-sm">Top Badge Earners</h3>
          {data.top_earners.length === 0 ? (
            <p className="text-xs text-muted-foreground">Belum ada data.</p>
          ) : (
            <div className="space-y-2">
              {data.top_earners.map((e, i) => (
                <div key={i} className="flex items-center gap-3">
                  <span className="text-lg">{i === 0 ? '🏆' : i === 1 ? '🥈' : i === 2 ? '🥉' : '🎖️'}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{e.employee_name}</div>
                    <div className="text-xs text-muted-foreground">{e.employee_code}</div>
                  </div>
                  <div className="text-sm font-bold text-primary">{e.badge_count} badge</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent Badges */}
      {data.recent_badges.length > 0 && (
        <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-xl p-5">
          <h3 className="font-semibold mb-3 text-sm">Badge Terbaru</h3>
          <div className="space-y-2">
            {data.recent_badges.slice(0, 6).map((b, i) => (
              <div key={i} className="flex items-center gap-3 text-sm">
                <span className="text-base">{b.badge_emoji}</span>
                <span className="font-medium">{b.employee_name}</span>
                <span className="text-muted-foreground">mendapatkan</span>
                <BadgeChip badge={b} />
                <span className="ml-auto text-xs text-muted-foreground">
                  {b.earned_at ? new Date(b.earned_at).toLocaleDateString('id-ID', { day:'numeric', month:'short' }) : ''}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main: KPIGamificationTab ─────────────────────────────────────────────────
export default function KPIGamificationTab({ token, periods = [], isHR = true }) {
  const [activeTab, setActiveTab] = useState('leaderboard');
  const [selectedPeriodId, setSelectedPeriodId] = useState('overall');
  const [leaderboard, setLeaderboard] = useState([]);
  const [loading, setLoading] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [seedMsg, setSeedMsg] = useState(null);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const finishedPeriods = periods.filter(p => ['finalized', 'closed'].includes(p.status));

  const loadLeaderboard = useCallback(async () => {
    setLoading(true);
    try {
      if (selectedPeriodId === 'overall') {
        const r = await axios.get(`${B}/api/dewi/kpi/leaderboard`, { headers });
        const data = r.data.leaderboard || [];
        setLeaderboard(data.map(e => ({ ...e, score: e.avg_score, delta: null, grade: null, badges: [] })));
      } else {
        const r = await axios.get(`${B}/api/dewi/kpi/leaderboard/${selectedPeriodId}`, { headers });
        setLeaderboard(r.data.leaderboard || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [selectedPeriodId, headers]);

  useEffect(() => { loadLeaderboard(); }, [loadLeaderboard]);

  const seedDemo = async () => {
    setSeeding(true); setSeedMsg(null);
    try {
      const r = await axios.post(`${B}/api/dewi/kpi/gamification/seed-demo`, {}, { headers });
      setSeedMsg({ type: 'success', text: r.data.message });
      await loadLeaderboard();
    } catch (e) {
      setSeedMsg({ type: 'error', text: e.response?.data?.detail || 'Gagal seed demo' });
    } finally { setSeeding(false); }
  };

  return (
    <div className="space-y-5">
      {/* Sub-tabs */}
      <div className="flex gap-1 bg-muted/40 p-1 rounded-xl w-fit flex-wrap">
        {[
          { id: 'leaderboard', label: '🏆 Leaderboard' },
          { id: 'summary', label: '📊 Ringkasan', hide: !isHR },
          { id: 'badges', label: '🏅 Badge Catalog' },
        ].filter(t => !t.hide).map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === t.id ? 'bg-white shadow text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Seed demo button (HR only, when no data) */}
      {isHR && (
        <div className="flex items-center gap-3">
          <button
            onClick={seedDemo}
            disabled={seeding}
            className="px-4 py-2 rounded-lg bg-violet-500 text-foreground text-xs font-medium hover:bg-violet-600 disabled:opacity-50 transition-colors"
          >
            {seeding ? 'Menyiapkan data...' : '🌱 Seed Demo Data KPI'}
          </button>
          <span className="text-xs text-muted-foreground">Buat periode demo + hasil KPI + badge otomatis</span>
          {seedMsg && (
            <span className={`text-xs font-medium ${seedMsg.type === 'success' ? 'text-emerald-600' : 'text-red-700 dark:text-red-500'}`}>
              {seedMsg.text}
            </span>
          )}
        </div>
      )}

      {/* Leaderboard Tab */}
      {activeTab === 'leaderboard' && (
        <div className="space-y-4">
          {/* Period selector */}
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium">Periode:</label>
            <SmartNativeSelect
              value={selectedPeriodId}
              onChange={e => setSelectedPeriodId(e.target.value)}
              className="border rounded-lg px-3 py-1.5 text-sm bg-background"
            >
              <option value="overall">All-Time (Rata-rata)</option>
              {finishedPeriods.map(p => (
                <option key={p.period_id || p.id} value={p.period_id || p.id}>
                  {p.title || p.name}
                </option>
              ))}
            </SmartNativeSelect>
            <button onClick={loadLeaderboard} className="text-xs text-primary underline underline-offset-2">Refresh</button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : leaderboard.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <div className="text-5xl mb-3">🏆</div>
              <p className="text-sm">Belum ada data leaderboard.</p>
              {isHR && <p className="text-xs mt-1">Klik <strong>Seed Demo Data KPI</strong> untuk mencoba fitur ini.</p>}
            </div>
          ) : (
            <>
              <Podium top3={leaderboard.slice(0, 3)} />
              <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-xl p-4">
                <h3 className="text-sm font-semibold mb-3">Ranking Lengkap</h3>
                <LeaderboardTable entries={leaderboard} />
              </div>
            </>
          )}
        </div>
      )}

      {/* Summary Tab (HR only) */}
      {activeTab === 'summary' && isHR && <GamificationSummaryPanel token={token} />}

      {/* Badge Catalog Tab */}
      {activeTab === 'badges' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Object.entries({
            "gold_medal":     { label: "Juara 1",          emoji: "🥇", color: "#F59E0B", desc: "Ranking #1 pada periode KPI" },
            "silver_medal":   { label: "Juara 2",          emoji: "🥈", color: "#9CA3AF", desc: "Ranking #2 pada periode KPI" },
            "bronze_medal":   { label: "Juara 3",          emoji: "🥉", color: "#B45309", desc: "Ranking #3 pada periode KPI" },
            "perfect_score":  { label: "Nilai Sempurna",   emoji: "⭐", color: "#7C3AED", desc: "KPI Final ≥ 95" },
            "grade_a":        { label: "Grade A",          emoji: "💎", color: "#0EA5E9", desc: "KPI Grade A (91–100)" },
            "most_improved":  { label: "Paling Meningkat", emoji: "📈", color: "#10B981", desc: "Peningkatan skor terbesar dari periode sebelumnya" },
            "consistent_top": { label: "Konsisten Terbaik","emoji": "🔥", color: "#EF4444", desc: "Masuk Top 3 pada 3+ periode berturut-turut" },
            "goal_crusher":   { label: "Goal Achiever",    emoji: "🎯", color: "#8B5CF6", desc: "Semua target KPI tercapai" },
            "top_performer":  { label: "Top Performer",    emoji: "💪", color: "#F97316", desc: "KPI Final ≥ 90" },
          }).map(([key, def]) => (
            <div
              key={key}
              className="rounded-xl border p-5 flex items-start gap-4 transition-transform hover:scale-[1.02]"
              style={{ borderColor: def.color + '44', background: def.color + '10' }}
            >
              <span className="text-4xl">{def.emoji}</span>
              <div>
                <div className="font-semibold text-sm" style={{ color: def.color }}>{def.label}</div>
                <div className="text-xs text-muted-foreground mt-0.5">{def.desc}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
