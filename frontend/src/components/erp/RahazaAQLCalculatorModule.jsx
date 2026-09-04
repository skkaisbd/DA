import { useState, useEffect, useCallback, useMemo } from 'react';
import { ClipboardCheck, Shield, AlertTriangle, CheckCircle2, Info, RefreshCw, Calculator } from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Combobox } from './Combobox';
import { IconButton } from './IconButton';

/* PT Rahaza ERP — AQL Sampling Calculator (Sprint 27)
   Form sederhana untuk menghitung sample size + Accept/Reject number
   berdasarkan ANSI/ASQ Z1.4 (Single Sampling Normal).

   Gunakan saat:
   - Final QC sebelum packing
   - Inline QC per bundle / per lot
   - Receiving inspection material dari supplier
*/

const AQL_LABELS = {
  0.65: 'AQL 0.65 — Premium / Luxury (sangat ketat)',
  1.0:  'AQL 1.0  — Export Tier-1 (ketat)',
  1.5:  'AQL 1.5  — Knit Garment Export (ketat-sedang)',
  2.5:  'AQL 2.5  — Standar Garment (paling umum)',
  4.0:  'AQL 4.0  — Lokal / Mass-market (longgar)',
  6.5:  'AQL 6.5  — Sample / Kelas C (sangat longgar)',
  10.0: 'AQL 10.0 — Inspeksi Visual Cepat (minimal)',
};

const LEVEL_DESC = {
  I:   'Level I — Longgar (track-record QC bagus)',
  II:  'Level II — Umum / Default',
  III: 'Level III — Ketat (produk kritis / new buyer)',
};

export default function RahazaAQLCalculatorModule({ token }) {
  const [lotSize, setLotSize] = useState(500);
  const [aql, setAql] = useState(2.5);
  const [level, setLevel] = useState('II');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [defectInput, setDefectInput] = useState('');
  const [reference, setReference] = useState(null);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  // Load reference table once
  useEffect(() => {
    fetch('/api/rahaza/aql/reference', { headers })
      .then(r => r.ok ? r.json() : null)
      .then(setReference)
      .catch(() => {});
  }, [headers]);

  const calculate = useCallback(async () => {
    if (!lotSize || lotSize < 2) return;
    setLoading(true);
    try {
      const r = await fetch('/api/rahaza/aql/calculate', {
        method: 'POST', headers,
        body: JSON.stringify({ lot_size: parseInt(lotSize), aql: parseFloat(aql), inspection_level: level }),
      });
      if (r.ok) {
        setResult(await r.json());
      } else {
        const err = await r.json().catch(() => ({}));
        setResult({ error: err.detail || 'Gagal hitung' });
      }
    } catch (e) {
      setResult({ error: e.message });
    } finally {
      setLoading(false);
    }
  }, [lotSize, aql, level, headers]);

  useEffect(() => { calculate(); }, [calculate]);

  // Decision based on user input defect count
  const decision = result && !result.error && defectInput !== '' ? (() => {
    const d = parseInt(defectInput);
    if (isNaN(d) || d < 0) return null;
    if (d <= result.accept_number) return { type: 'accept', text: 'LULUS — terima batch' };
    if (d >= result.reject_number) return { type: 'reject', text: 'GAGAL — rework / re-inspect 100%' };
    return { type: 'resample', text: 'BORDERLINE — re-sample 1 kali' };
  })() : null;

  return (
    <div className="space-y-5" data-testid="aql-calculator-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Shield className="w-6 h-6 text-primary" /> AQL Sampling Calculator
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Hitung sample size & Accept/Reject berdasarkan ANSI/ASQ Z1.4 — untuk inline & final QC
          </p>
        </div>
        <IconButton label="Hitung ulang" onClick={calculate} data-testid="aql-recalculate">
          <RefreshCw className={`w-4 h-4 text-muted-foreground ${loading ? 'animate-spin' : ''}`} />
        </IconButton>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Input form */}
        <GlassCard hover={false} className="p-5">
          <div className="flex items-center gap-2 mb-4">
            <Calculator className="w-4 h-4 text-primary" />
            <h2 className="font-semibold text-foreground">Input Sampling Plan</h2>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1.5">
                Ukuran Batch / Lot Size <span className="text-muted-foreground">(jumlah pcs total)</span>
              </label>
              <GlassInput
                type="number"
                min={2}
                value={lotSize}
                onChange={e => setLotSize(e.target.value)}
                placeholder="Contoh: 500"
                data-testid="aql-lot-size"
              />
              <p className="text-[11px] text-muted-foreground mt-1">Jumlah total pcs dalam Work Order / batch yang akan diinspeksi.</p>
            </div>

            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1.5">
                AQL Level <span className="text-muted-foreground">(Acceptable Quality Limit)</span>
              </label>
              <Combobox
                value={String(aql)}
                onChange={(v) => setAql(parseFloat(v))}
                options={Object.entries(AQL_LABELS).map(([v, label]) => ({
                  value: v,
                  label,
                }))}
                placeholder="Pilih AQL..."
                data-testid="aql-level"
              />
              <p className="text-[11px] text-muted-foreground mt-1">Default standar garment: <b>AQL 2.5</b>. Pakai 1.5 untuk export tier-1, 4.0 untuk lokal.</p>
            </div>

            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1.5">
                Inspection Level
              </label>
              <Combobox
                value={level}
                onChange={setLevel}
                options={Object.entries(LEVEL_DESC).map(([v, label]) => ({
                  value: v,
                  label,
                }))}
                placeholder="Pilih level..."
                data-testid="aql-inspection-level"
              />
            </div>
          </div>
        </GlassCard>

        {/* Result */}
        <GlassCard hover={false} className="p-5" data-testid="aql-result-card">
          <h2 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Hasil Sampling Plan
          </h2>
          {!result ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Isi input untuk melihat hasil...</p>
          ) : result.error ? (
            <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30">
              <p className="text-sm text-red-400">{result.error}</p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <div className="text-center p-4 rounded-xl bg-primary/10 border border-primary/30" data-testid="aql-sample-size">
                  <p className="text-[10px] uppercase tracking-wider text-primary mb-1">Sample Size</p>
                  <p className="text-3xl font-bold text-primary">{result.sample_size}</p>
                  <p className="text-[10px] text-muted-foreground mt-1">pcs di-cek</p>
                </div>
                <div className="text-center p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30" data-testid="aql-accept-number">
                  <p className="text-[10px] uppercase tracking-wider text-emerald-400 mb-1">Accept (Ac)</p>
                  <p className="text-3xl font-bold text-emerald-400">≤ {result.accept_number}</p>
                  <p className="text-[10px] text-muted-foreground mt-1">defect → LULUS</p>
                </div>
                <div className="text-center p-4 rounded-xl bg-red-500/10 border border-red-500/30" data-testid="aql-reject-number">
                  <p className="text-[10px] uppercase tracking-wider text-red-400 mb-1">Reject (Re)</p>
                  <p className="text-3xl font-bold text-red-400">≥ {result.reject_number}</p>
                  <p className="text-[10px] text-muted-foreground mt-1">defect → GAGAL</p>
                </div>
              </div>

              <div className="text-xs text-muted-foreground p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                <p>Code letter: <b className="text-foreground font-mono">{result.code_letter}</b>
                  {result.code_letter !== result.final_code_letter && <> → <b className="text-amber-400 font-mono">{result.final_code_letter}</b> (digeser per master table)</>}
                </p>
                <p className="mt-1">{result.decision_rule}</p>
              </div>

              {/* Live decision tester */}
              <GlassPanel className="p-4">
                <p className="text-xs font-semibold text-foreground/70 mb-2">Cek hasil inspeksi langsung</p>
                <div className="flex items-center gap-3">
                  <GlassInput
                    type="number"
                    min={0}
                    placeholder="Jumlah defect ditemukan"
                    value={defectInput}
                    onChange={e => setDefectInput(e.target.value)}
                    className="flex-1"
                    data-testid="aql-defect-input"
                  />
                </div>
                {decision && (
                  <div
                    className={`mt-3 p-3 rounded-xl border ${
                      decision.type === 'accept'
                        ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                        : decision.type === 'reject'
                        ? 'bg-red-500/10 border-red-500/30 text-red-400'
                        : 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                    }`}
                    data-testid="aql-decision"
                  >
                    <div className="flex items-center gap-2 font-semibold">
                      {decision.type === 'accept' && <CheckCircle2 className="w-4 h-4" />}
                      {decision.type === 'reject' && <AlertTriangle className="w-4 h-4" />}
                      {decision.type === 'resample' && <Info className="w-4 h-4" />}
                      {decision.text}
                    </div>
                  </div>
                )}
              </GlassPanel>

              {(result.notes || []).length > 0 && (
                <div className="text-[11px] text-muted-foreground space-y-1 pt-2 border-t border-[var(--glass-border)]">
                  {result.notes.map((n, i) => (
                    <p key={i} className="flex items-start gap-1.5">
                      <Info className="w-3 h-3 mt-0.5 shrink-0" /> {n}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
        </GlassCard>
      </div>

      {/* Reference table */}
      {reference && (
        <GlassCard hover={false} className="p-5">
          <h2 className="font-semibold text-foreground mb-3 flex items-center gap-2">
            <ClipboardCheck className="w-4 h-4 text-primary" /> Referensi AQL Level
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {Object.entries(reference.aql_meaning || {}).map(([v, desc]) => (
              <div key={v} className="flex items-start gap-3 p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                <span className="text-sm font-bold font-mono text-primary min-w-[3rem]">AQL {v}</span>
                <span className="text-xs text-muted-foreground">{desc}</span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground mt-3 italic">
            Sumber: ANSI/ASQ Z1.4 (formerly MIL-STD-105E) — Single Sampling Plan, Normal Inspection.
          </p>
        </GlassCard>
      )}
    </div>
  );
}
