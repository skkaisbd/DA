import { ArrowRight, Pause, X } from 'lucide-react';

/* ─────────────────────────────────────────────────────────
 * SVG diagram alur Work Order: Draft → Released → In Progress → Completed
 * (+ branch ke Cancelled). Pakai HTML+CSS supaya responsive.
 * ───────────────────────────────────────────────────────── */
export function WOFlowDiagram() {
  const stages = [
    { label: 'Draft', desc: 'WO baru dibuat (manual / dari Order)', color: 'bg-muted dark:bg-slate-500/15 border-border/40 text-muted-foreground' },
    { label: 'Released', desc: 'Material auto-reserve. Lini siap.', color: 'bg-blue-100 dark:bg-blue-500/15 border-blue-500/40 text-blue-600' },
    { label: 'In Progress', desc: 'Operator produksi aktif. Update qty harian.', color: 'bg-amber-100 dark:bg-amber-500/15 border-amber-500/40 text-amber-600' },
    { label: 'Completed', desc: 'Semua qty pass QC. WO ditutup.', color: 'bg-emerald-100 dark:bg-emerald-500/15 border-emerald-500/40 text-emerald-600' },
  ];
  return (
    <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-4">
      <p className="text-sm font-semibold text-foreground mb-3">Alur Status Work Order</p>
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
        {stages.map((s, i) => (
          <div key={s.label} className="flex flex-col sm:flex-row sm:items-center gap-2 flex-1">
            <div className={`flex-1 rounded-lg border p-3 ${s.color}`}>
              <p className="text-xs font-bold uppercase tracking-wide">{s.label}</p>
              <p className="text-[11px] text-foreground/65 mt-1 leading-snug">{s.desc}</p>
            </div>
            {i < stages.length - 1 && (
              <ArrowRight className="w-4 h-4 text-foreground/35 mx-auto sm:mx-0 rotate-90 sm:rotate-0 shrink-0" />
            )}
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2 text-[11px] text-foreground/50">
        <X className="w-3.5 h-3.5 text-red-500" />
        <span>Cancelled — bisa dari status manapun. WO tidak bisa dilanjutkan, harus buat WO baru.</span>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
 * OEE Formula visual: A × P × Q
 * ───────────────────────────────────────────────────────── */
export function OEEFormulaDiagram() {
  const components = [
    { label: 'Availability', value: '85%', formula: 'Runtime / Planned Time', desc: 'Berapa lama mesin aktif vs jadwal', color: 'bg-blue-100 dark:bg-blue-500/15 border-blue-500/40 text-blue-600' },
    { label: 'Performance', value: '95%', formula: 'Actual Output / Target', desc: 'Kecepatan produksi vs target', color: 'bg-amber-100 dark:bg-amber-500/15 border-amber-500/40 text-amber-600' },
    { label: 'Quality', value: '99%', formula: 'Pass / Total Inspected', desc: 'Tingkat lulus QC', color: 'bg-emerald-100 dark:bg-emerald-500/15 border-emerald-500/40 text-emerald-600' },
  ];
  return (
    <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-4">
      <p className="text-sm font-semibold text-foreground mb-3">Formula OEE</p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-3">
        {components.map((c) => (
          <div key={c.label} className={`rounded-lg border p-3 ${c.color}`}>
            <p className="text-[10px] font-bold uppercase tracking-wide opacity-75">{c.label}</p>
            <p className="text-lg font-black mt-0.5">{c.value}</p>
            <p className="text-[11px] text-foreground/65 mt-1 leading-snug">{c.desc}</p>
            <p className="text-[10px] mt-1 font-mono text-foreground/50">{c.formula}</p>
          </div>
        ))}
      </div>
      <div className="rounded-lg bg-violet-100 dark:bg-violet-500/10 border border-violet-400 dark:border-violet-500/30 p-3 text-center">
        <p className="text-xs text-foreground/70">
          <span className="font-bold text-violet-600">OEE</span> = A × P × Q ={' '}
          <span className="font-bold text-violet-600">85% × 95% × 99% = 79.9%</span>
        </p>
        <p className="text-[10px] text-foreground/50 mt-1">Target World-Class: ≥ 85% · Average industri: 60%</p>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
 * Material Flow: PO → Receiving → Stock → Reserved → Issued → Production
 * ───────────────────────────────────────────────────────── */
export function MaterialFlowDiagram() {
  const steps = [
    { label: 'PO', desc: 'Purchase Order ke supplier', tag: 'Gudang' },
    { label: 'Receiving', desc: 'Goods Receipt — barang datang', tag: 'Gudang' },
    { label: 'Stock', desc: 'Tersimpan di gudang per lokasi', tag: 'Gudang' },
    { label: 'Reserved', desc: 'Auto saat WO Release', tag: 'Sistem' },
    { label: 'Issued', desc: 'Bulk MI keluarkan ke lantai', tag: 'Produksi' },
    { label: 'Production', desc: 'Material dipakai produksi', tag: 'Produksi' },
  ];
  return (
    <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-4">
      <p className="text-sm font-semibold text-foreground mb-3">Alur Material End-to-End</p>
      <div className="space-y-2">
        {steps.map((s, i) => (
          <div key={s.label} className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-full bg-[hsl(var(--primary)/0.15)] border border-[hsl(var(--primary)/0.30)] grid place-items-center shrink-0 text-xs font-bold text-[hsl(var(--primary))]">
              {i + 1}
            </div>
            <div className="flex-1 rounded-lg border border-[var(--glass-border)] bg-foreground/[0.02] p-2.5">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-foreground">{s.label}</p>
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-foreground/5 text-foreground/50 font-medium">{s.tag}</span>
              </div>
              <p className="text-[11px] text-foreground/60 mt-0.5">{s.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export const DIAGRAMS = {
  'wo-flow': WOFlowDiagram,
  'oee-formula': OEEFormulaDiagram,
  'material-flow': MaterialFlowDiagram,
};
