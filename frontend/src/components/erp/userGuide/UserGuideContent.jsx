import { useState, useMemo, useRef, useEffect } from 'react';
import {
  BookOpen, Search, ChevronRight, CheckCircle2, AlertTriangle, Lightbulb,
  Clock, Users as UsersIcon, Sparkles, ArrowRight, Target, ShieldCheck,
  PlayCircle, ListChecks, HelpCircle, MessageCircle, Wrench, Download,
  LogIn, MousePointerClick, Compass, Repeat, Filter,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  PORTAL_META, DIFFICULTY, OVERVIEW, PORTALS_GUIDE, SCENARIOS, TIPS,
} from './guideData';

const API = process.env.REACT_APP_BACKEND_URL;

/* ─────────── Reusable atoms ─────────── */

function PortalChip({ portalKey, withIcon = true }) {
  const m = PORTAL_META[portalKey];
  if (!m) return null;
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${m.classes.bg} ${m.classes.border} ${m.classes.text}`}>
      {withIcon && <Icon className="w-3 h-3" strokeWidth={2.5} />}
      {m.name}
    </span>
  );
}

function DifficultyBadge({ level }) {
  const d = DIFFICULTY[level] || DIFFICULTY.pemula;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${d.classes}`}>
      <Target className="w-3 h-3" strokeWidth={2.5} />
      {d.label}
    </span>
  );
}

function CalloutTip({ children }) {
  return (
    <div className="flex gap-2 p-3 rounded-lg bg-amber-100 dark:bg-amber-500/10 border border-amber-400 dark:border-amber-500/30 text-xs text-amber-700 dark:text-amber-300">
      <Lightbulb className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" strokeWidth={2.5} />
      <span><strong className="font-semibold">Tips:</strong> {children}</span>
    </div>
  );
}

function CalloutWarn({ children }) {
  return (
    <div className="flex gap-2 p-3 rounded-lg bg-red-100 dark:bg-red-500/10 border border-red-400 dark:border-red-500/30 text-xs text-red-700 dark:text-red-300">
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-red-500" strokeWidth={2.5} />
      <span><strong className="font-semibold">Penting:</strong> {children}</span>
    </div>
  );
}

/* ─────────── Overview Section ─────────── */

const LOGIN_ICONS = {
  login: LogIn, select: MousePointerClick, navigate: Compass, switch: Repeat,
};

function OverviewView() {
  return (
    <div className="space-y-6" data-testid="guide-overview">
      <div className="rounded-2xl border border-[var(--glass-border)] bg-gradient-to-br from-sky-500/10 via-emerald-500/5 to-violet-500/10 p-6">
        <div className="flex items-start gap-4">
          <div className="w-14 h-14 rounded-2xl bg-background/70 border border-border grid place-items-center shrink-0">
            <Sparkles className="w-7 h-7 text-amber-700 dark:text-amber-400" strokeWidth={2} />
          </div>
          <div>
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
              {OVERVIEW.title}
            </h2>
            <p className="text-sm text-foreground/70 mt-2 leading-relaxed">{OVERVIEW.intro}</p>
          </div>
        </div>
      </div>

      {/* Highlights grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {OVERVIEW.highlights.map((h) => {
          const Icon = h.icon;
          return (
            <div key={h.title} className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-4">
              <div className="w-9 h-9 rounded-lg bg-foreground/5 grid place-items-center mb-2">
                <Icon className="w-4 h-4 text-[hsl(var(--primary))]" strokeWidth={2.2} />
              </div>
              <p className="text-sm font-semibold text-foreground">{h.title}</p>
              <p className="text-xs text-foreground/55 mt-0.5">{h.desc}</p>
            </div>
          );
        })}
      </div>

      {/* 5 Portal cards */}
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-3">5 Portal Utama</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Object.entries(PORTAL_META).filter(([k]) => !['qc', 'shift'].includes(k)).map(([key, m]) => {
            const Icon = m.icon;
            return (
              <div key={key} className={`rounded-xl border p-4 ${m.classes.bg} ${m.classes.border}`}>
                <div className="flex items-start gap-3">
                  <div className={`w-10 h-10 rounded-xl bg-background/70 dark:bg-foreground/10 grid place-items-center shrink-0 ${m.classes.text}`}>
                    <Icon className="w-5 h-5" strokeWidth={2} />
                  </div>
                  <div>
                    <p className={`text-sm font-semibold ${m.classes.text}`}>{m.name}</p>
                    <p className="text-xs text-foreground/60 mt-0.5">{m.role}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Login & Navigation */}
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-3">Login & Navigasi</h3>
        <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-5">
          <ol className="space-y-3">
            {OVERVIEW.loginSteps.map((s, i) => {
              const Icon = LOGIN_ICONS[s.icon] || HelpCircle;
              return (
                <li key={i} className="flex items-start gap-3">
                  <div className="w-7 h-7 rounded-full bg-[hsl(var(--primary)/0.12)] border border-[hsl(var(--primary)/0.30)] grid place-items-center shrink-0 text-[11px] font-bold text-[hsl(var(--primary))]">
                    {i + 1}
                  </div>
                  <div className="flex-1 flex items-center gap-2 pt-0.5">
                    <Icon className="w-4 h-4 text-foreground/50 shrink-0" strokeWidth={2} />
                    <span className="text-sm text-foreground/80">{s.text}</span>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </div>
  );
}

/* ─────────── Portal Section (rich) ─────────── */

async function handleSopDownload(sop) {
  const token = localStorage.getItem('erp_token');
  if (!token) {
    toast.error('Sesi sudah berakhir. Silakan login ulang.');
    return;
  }
  const t = toast.loading('Mempersiapkan SOP PDF...');
  try {
    const res = await fetch(`${API}${sop.endpoint}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Download gagal (${res.status})`);
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = sop.filename || 'SOP.pdf';
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    toast.success('SOP berhasil diunduh', { id: t });
  } catch (e) {
    toast.error(e.message || 'Gagal mengunduh SOP', { id: t });
  }
}

function PortalView({ portal }) {
  const meta = PORTAL_META[portal.portalKey];
  const Icon = meta.icon;
  return (
    <div className="space-y-5" data-testid={`guide-${portal.id}`}>
      <div className={`rounded-2xl border p-5 ${meta.classes.bg} ${meta.classes.border}`}>
        <div className="flex items-start gap-4">
          <div className={`w-12 h-12 rounded-xl bg-background/70 dark:bg-foreground/10 grid place-items-center shrink-0 ${meta.classes.text}`}>
            <Icon className="w-6 h-6" strokeWidth={2} />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className={`text-xl font-bold ${meta.classes.text}`}>{portal.title}</h2>
            <p className="text-sm text-foreground/70 mt-1">{portal.summary}</p>
            <div className="mt-2 flex items-center gap-1.5 text-xs text-foreground/55">
              <UsersIcon className="w-3 h-3" />
              <span>Pengguna: {meta.role}</span>
            </div>
            {portal.sopDownload && (
              <button
                onClick={() => handleSopDownload(portal.sopDownload)}
                data-testid={`guide-sop-download-${portal.id}`}
                className={`mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold ${meta.classes.bg} ${meta.classes.border} border ${meta.classes.text} hover:opacity-80 transition`}
              >
                <Download className="w-3.5 h-3.5" />
                {portal.sopDownload.label}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Menu cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {portal.menus.map((menu, idx) => {
          const MIcon = menu.icon;
          return (
            <div
              key={idx}
              className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-4 hover:border-[hsl(var(--primary)/0.3)] transition-colors"
              data-testid={`menu-${portal.id}-${idx}`}
            >
              <div className="flex items-start gap-3 mb-2">
                <div className={`w-9 h-9 rounded-lg ${meta.classes.bg} ${meta.classes.border} border grid place-items-center shrink-0 ${meta.classes.text}`}>
                  <MIcon className="w-4 h-4" strokeWidth={2.2} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-foreground">{menu.title}</p>
                  <p className="text-[11px] text-foreground/45 mt-0.5 font-mono break-words">{menu.path}</p>
                </div>
              </div>
              <p className="text-xs text-foreground/70 leading-relaxed mb-2">{menu.description}</p>
              {menu.bullets?.length > 0 && (
                <ul className="space-y-1 mb-2">
                  {menu.bullets.map((b, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-xs text-foreground/65">
                      <CheckCircle2 className={`w-3 h-3 shrink-0 mt-0.5 ${meta.classes.text}`} strokeWidth={2.5} />
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
              )}
              {menu.tips && <CalloutTip>{menu.tips}</CalloutTip>}
              {menu.warn && <CalloutWarn>{menu.warn}</CalloutWarn>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─────────── Scenario Card (rich) ─────────── */

function ScenarioView({ scenario, onBack }) {
  return (
    <div className="space-y-5" data-testid={`scenario-detail-${scenario.id}`}>
      {onBack && (
        <button
          onClick={onBack}
          className="text-xs text-foreground/60 hover:text-foreground inline-flex items-center gap-1.5"
          data-testid="scenario-back-btn"
        >
          <ChevronRight className="w-3.5 h-3.5 rotate-180" />
          Kembali ke daftar skenario
        </button>
      )}
      {/* Header card */}
      <div className="rounded-2xl border border-[var(--glass-border)] bg-gradient-to-br from-cyan-500/10 to-indigo-500/10 p-5">
        <div className="flex items-start gap-4">
          <div className="w-14 h-14 rounded-2xl bg-cyan-100 dark:bg-cyan-500/20 border border-cyan-500/40 grid place-items-center shrink-0">
            <span className="text-lg font-black text-cyan-600 dark:text-cyan-300">{scenario.code}</span>
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground">{scenario.title}</h2>
            <p className="text-sm text-foreground/70 mt-1">{scenario.description}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <DifficultyBadge level={scenario.difficulty} />
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border border-foreground/15 bg-foreground/5 text-foreground/70">
                <Clock className="w-3 h-3" strokeWidth={2.5} />
                {scenario.estimatedTime}
              </span>
              {scenario.personas?.map((p) => (
                <PortalChip key={p} portalKey={p} />
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Pre-requisites — ALWAYS VISIBLE, very prominent */}
      <div className="rounded-2xl border-2 border-amber-400 dark:border-amber-500/30 bg-amber-100 dark:bg-amber-500/5 p-5" data-testid={`scenario-prereq-${scenario.id}`}>
        <div className="flex items-center gap-2 mb-3">
          <div className="w-9 h-9 rounded-xl bg-amber-100 dark:bg-amber-500/20 border border-amber-500/40 grid place-items-center">
            <ShieldCheck className="w-5 h-5 text-amber-600 dark:text-amber-400" strokeWidth={2.2} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-amber-700 dark:text-amber-300">Pre-Requisite</h3>
            <p className="text-[11px] text-amber-700/70 dark:text-amber-400/70">Pastikan ini sudah siap sebelum mulai skenario</p>
          </div>
        </div>
        <ul className="space-y-2 ml-1">
          {scenario.prerequisites.map((p, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-foreground/85">
              <span className="w-5 h-5 rounded-full border-2 border-amber-500/60 bg-amber-100 dark:bg-amber-500/10 grid place-items-center shrink-0 mt-0.5">
                <span className="text-[11px] font-bold text-amber-600 dark:text-amber-400">{i + 1}</span>
              </span>
              <span>{p}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Steps */}
      <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-5">
        <div className="flex items-center gap-2 mb-4">
          <PlayCircle className="w-5 h-5 text-[hsl(var(--primary))]" strokeWidth={2.2} />
          <h3 className="text-sm font-bold text-foreground">Langkah-Langkah</h3>
          <span className="text-xs text-foreground/45">({scenario.steps.length} step)</span>
        </div>
        <ol className="space-y-3">
          {scenario.steps.map((step, i) => {
            const m = PORTAL_META[step.portal] || PORTAL_META.produksi;
            const Icon = m.icon;
            const isLast = i === scenario.steps.length - 1;
            return (
              <li key={i} className="relative pl-12">
                {/* Number circle */}
                <div className={`absolute left-0 top-0 w-9 h-9 rounded-full border-2 grid place-items-center font-bold text-sm ${m.classes.bg} ${m.classes.border} ${m.classes.text}`}>
                  {i + 1}
                </div>
                {/* Connecting line */}
                {!isLast && (
                  <div className={`absolute left-[17px] top-9 w-0.5 h-full ${m.classes.dot} opacity-30`} />
                )}
                {/* Content */}
                <div className="rounded-xl border border-[var(--glass-border)] bg-foreground/[0.02] p-3 mb-3">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <PortalChip portalKey={step.portal} />
                    <span className="text-sm font-semibold text-foreground">{step.title}</span>
                  </div>
                  {step.menu && step.menu !== '—' && (
                    <p className="text-[11px] text-foreground/50 font-mono mb-1.5">📍 {step.menu}</p>
                  )}
                  {step.detail && (
                    <p className="text-xs text-foreground/75 leading-relaxed">{step.detail}</p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </div>

      {/* Expected results */}
      <div className="rounded-2xl border border-emerald-400 dark:border-emerald-500/30 bg-emerald-100 dark:bg-emerald-500/5 p-5">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-100 dark:bg-emerald-500/20 border border-emerald-500/40 grid place-items-center">
            <Target className="w-5 h-5 text-emerald-600 dark:text-emerald-400" strokeWidth={2.2} />
          </div>
          <h3 className="text-sm font-bold text-emerald-700 dark:text-emerald-300">Hasil yang Diharapkan</h3>
        </div>
        <ul className="space-y-2">
          {scenario.expectedResults.map((r, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-foreground/85">
              <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-emerald-500" strokeWidth={2.5} />
              <span>{r}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/* ─────────── Scenarios List ─────────── */

function ScenariosList({ onSelect, search }) {
  const filtered = useMemo(() => {
    if (!search) return SCENARIOS;
    const q = search.toLowerCase();
    return SCENARIOS.filter(
      (s) =>
        s.title.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q) ||
        s.code.toLowerCase().includes(q),
    );
  }, [search]);

  return (
    <div className="space-y-4" data-testid="scenarios-list">
      <div className="rounded-2xl border border-[var(--glass-border)] bg-gradient-to-br from-cyan-500/10 to-indigo-500/10 p-5">
        <div className="flex items-start gap-3">
          <PlayCircle className="w-6 h-6 text-cyan-500 shrink-0 mt-0.5" strokeWidth={2} />
          <div>
            <h2 className="text-lg font-bold text-foreground">Skenario Penggunaan</h2>
            <p className="text-sm text-foreground/70 mt-1">
              8 skenario lengkap dengan <strong>pre-requisite</strong>, langkah, & hasil yang diharapkan.
              Cocok untuk training karyawan baru atau testing fitur.
            </p>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {filtered.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelect(s)}
            className="text-left rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-4 hover:border-cyan-500/40 hover:bg-cyan-100 dark:bg-cyan-500/5 transition-colors group"
            data-testid={`scenario-card-${s.id}`}
          >
            <div className="flex items-start gap-3">
              <div className="w-11 h-11 rounded-xl bg-cyan-100 dark:bg-cyan-500/15 border border-cyan-400 dark:border-cyan-500/30 grid place-items-center shrink-0">
                <span className="text-sm font-black text-cyan-600 dark:text-cyan-300">{s.code}</span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground group-hover:text-cyan-600 dark:group-hover:text-cyan-600 dark:text-cyan-300 transition-colors">
                  {s.title}
                </p>
                <p className="text-xs text-foreground/55 mt-1 line-clamp-2">{s.description}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <DifficultyBadge level={s.difficulty} />
                  <span className="inline-flex items-center gap-1 text-[11px] text-foreground/50">
                    <Clock className="w-3 h-3" />
                    {s.estimatedTime.split(';')[0]}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-1">
                  {s.personas.map((p) => (
                    <PortalChip key={p} portalKey={p} />
                  ))}
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-foreground/30 group-hover:text-cyan-500 group-hover:translate-x-0.5 transition-all shrink-0" />
            </div>
          </button>
        ))}
      </div>
      {filtered.length === 0 && (
        <div className="text-center py-12 text-foreground/40">
          <HelpCircle className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Tidak ada skenario cocok untuk "{search}"</p>
        </div>
      )}
    </div>
  );
}

/* ─────────── Tips Section ─────────── */

const TIP_ICONS = { production: Wrench, warehouse: ListChecks, finance: CheckCircle2 };

function TipsView() {
  return (
    <div className="space-y-5" data-testid="guide-tips">
      <div className="rounded-2xl border border-[var(--glass-border)] bg-gradient-to-br from-orange-500/10 to-yellow-500/10 p-5">
        <div className="flex items-start gap-3">
          <Lightbulb className="w-6 h-6 text-orange-500 shrink-0 mt-0.5" strokeWidth={2} />
          <div>
            <h2 className="text-lg font-bold text-foreground">Tips, FAQ & Troubleshooting</h2>
            <p className="text-sm text-foreground/70 mt-1">Best practice harian, pertanyaan umum, dan solusi cepat.</p>
          </div>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-amber-500" /> Tips Sehari-hari
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {TIPS.daily.map((cat) => {
            const Icon = TIP_ICONS[cat.icon] || Lightbulb;
            return (
              <div key={cat.title} className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Icon className="w-4 h-4 text-[hsl(var(--primary))]" strokeWidth={2.2} />
                  <p className="text-sm font-semibold text-foreground">{cat.title}</p>
                </div>
                <ul className="space-y-1.5">
                  {cat.items.map((it, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-xs text-foreground/70">
                      <CheckCircle2 className="w-3 h-3 shrink-0 mt-0.5 text-emerald-500" strokeWidth={2.5} />
                      <span>{it}</span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <MessageCircle className="w-4 h-4 text-indigo-500" /> FAQ
        </h3>
        <div className="space-y-2">
          {TIPS.faq.map((f, i) => (
            <div key={i} className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-4">
              <p className="text-sm font-semibold text-[hsl(var(--primary))] mb-1">Q: {f.q}</p>
              <p className="text-xs text-foreground/75 leading-relaxed">A: {f.a}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <Wrench className="w-4 h-4 text-rose-500" /> Troubleshooting
        </h3>
        <div className="space-y-2">
          {TIPS.troubleshoot.map((t, i) => (
            <div key={i} className="rounded-xl border border-rose-300 dark:border-rose-500/20 bg-rose-100 dark:bg-rose-500/5 p-4">
              <div className="flex items-start gap-2 mb-1">
                <AlertTriangle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" strokeWidth={2.5} />
                <p className="text-sm font-semibold text-foreground">{t.issue}</p>
              </div>
              <p className="text-xs text-foreground/75 leading-relaxed pl-6">→ {t.sol}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─────────── Main Content (sidebar + content) ─────────── */

export default function UserGuideContent({ embedded = false }) {
  // tabs: 'overview', 'p-manajemen', ..., 'scenarios', 'tips'
  const [activeTab, setActiveTab] = useState('overview');
  const [activeScenario, setActiveScenario] = useState(null);
  const [search, setSearch] = useState('');
  const contentRef = useRef(null);

  // Reset scroll when tab changes
  useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = 0;
  }, [activeTab, activeScenario]);

  const TABS = [
    { id: 'overview', label: 'Selamat Datang', icon: BookOpen },
    ...PORTALS_GUIDE.map((p) => {
      const m = PORTAL_META[p.portalKey];
      return { id: p.id, label: p.title.replace('Portal ', ''), icon: m.icon, color: m.classes.text };
    }),
    { id: 'scenarios', label: 'Skenario', icon: PlayCircle, color: 'text-cyan-500' },
    { id: 'tips', label: 'Tips & FAQ', icon: Lightbulb, color: 'text-amber-500' },
  ];

  // Filter for sidebar matches when search active
  const portalSearchHits = useMemo(() => {
    if (!search) return null;
    const q = search.toLowerCase();
    const hits = new Set();
    PORTALS_GUIDE.forEach((p) => {
      if (
        p.title.toLowerCase().includes(q) ||
        p.summary.toLowerCase().includes(q) ||
        p.menus.some((m) => m.title.toLowerCase().includes(q) || m.description.toLowerCase().includes(q))
      ) {
        hits.add(p.id);
      }
    });
    return hits;
  }, [search]);

  const handleTabClick = (id) => {
    setActiveTab(id);
    setActiveScenario(null);
  };

  const renderContent = () => {
    if (activeTab === 'overview') return <OverviewView />;
    if (activeTab === 'tips') return <TipsView />;
    if (activeTab === 'scenarios') {
      if (activeScenario) {
        return (
          <ScenarioView
            scenario={activeScenario}
            onBack={() => setActiveScenario(null)}
          />
        );
      }
      return <ScenariosList onSelect={setActiveScenario} search={search} />;
    }
    const portal = PORTALS_GUIDE.find((p) => p.id === activeTab);
    if (portal) return <PortalView portal={portal} />;
    return null;
  };

  return (
    <div className={`flex flex-col lg:flex-row gap-0 ${embedded ? 'h-full' : 'min-h-[600px]'}`} data-testid="user-guide-content">
      {/* Sidebar */}
      <aside className="lg:w-64 lg:shrink-0 lg:border-r border-[var(--glass-border)] lg:max-h-[80vh] lg:overflow-y-auto">
        <div className="p-4 lg:p-5 sticky top-0 bg-[var(--glass-bg)] z-10 border-b border-[var(--glass-border)]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground/40" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Cari panduan..."
              className="w-full h-9 pl-9 pr-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              data-testid="guide-search-input"
            />
          </div>
        </div>
        <nav className="p-3 space-y-1">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            const isHit = portalSearchHits ? portalSearchHits.has(tab.id) : false;
            return (
              <button
                key={tab.id}
                onClick={() => handleTabClick(tab.id)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors text-left ${
                  isActive
                    ? 'bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--primary))] font-semibold border border-[hsl(var(--primary)/0.25)]'
                    : 'text-foreground/70 hover:bg-foreground/5 border border-transparent'
                } ${isHit && !isActive ? 'ring-1 ring-amber-500/40' : ''}`}
                data-testid={`guide-tab-${tab.id}`}
              >
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? '' : tab.color || 'text-foreground/45'}`} strokeWidth={2.2} />
                <span className="truncate">{tab.label}</span>
                {isActive && <ChevronRight className="w-3.5 h-3.5 ml-auto shrink-0" />}
              </button>
            );
          })}
        </nav>
      </aside>

      {/* Content area */}
      <div ref={contentRef} className="flex-1 p-4 lg:p-6 lg:max-h-[80vh] lg:overflow-y-auto">
        {renderContent()}
      </div>
    </div>
  );
}
