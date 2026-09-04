/**
 * CreatorIncentivePanel — **Insentif kreator per pcs + tracker periode** (sesi #34).
 *
 * Keputusan pemilik (2026-08-23):
 *  • hanya kreator **kontrak** & **continue** dapat insentif (tipe `new` tidak);
 *  • bentuknya bisa DUA-DUANYA dan dikonfigurasi per kreator:
 *      Rp per pcs terjual  dan/atau  bonus bila target pcs periode tercapai;
 *  • **pcs terjual diinput STAF MARKETING** (bukan kreator) — supaya angka yang
 *    dibayar tidak lahir dari klaim orang yang menerima uangnya;
 *  • periode **default 3 bulan**, bisa dikonfigurasi; periode habis ⇒ hitungan
 *    kembali 0, tetapi entri periode lama tetap tersimpan sebagai bukti bayar.
 */
import { useCallback, useEffect, useState } from 'react';
import { Target, Plus, Trash2, RotateCcw, Save, Loader2, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;
const rp = formatRupiah;

export default function CreatorIncentivePanel({ token, creator, onClose }) {
  const [data, setData] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [entry, setEntry] = useState({ date: new Date().toISOString().slice(0, 10), pcs: '', note: '' });
  const [busy, setBusy] = useState(false);
  const H = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const load = useCallback(async () => {
    const r = await fetch(`${API}/api/marketing/kol/creators/${creator.id}/incentive`, { headers: H });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal memuat insentif'); return; }
    setData(d);
    setCfg(d.config);
  }, [creator.id, token]); // eslint-disable-line

  useEffect(() => { load(); }, [load]);

  const saveCfg = async () => {
    setBusy(true);
    try {
      const r = await fetch(`${API}/api/marketing/kol/creators/${creator.id}/incentive`,
        { method: 'PUT', headers: H, body: JSON.stringify(cfg) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal menyimpan');
      setData(d); setCfg(d.config);
      toast.success('Konfigurasi insentif tersimpan');
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  const addEntry = async () => {
    if (!Number(entry.pcs)) { toast.error('Jumlah pcs wajib diisi'); return; }
    setBusy(true);
    try {
      const r = await fetch(`${API}/api/marketing/kol/creators/${creator.id}/incentive/entries`,
        { method: 'POST', headers: H, body: JSON.stringify({ ...entry, pcs: Number(entry.pcs) }) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal menambah entri');
      setData(d); setEntry({ ...entry, pcs: '', note: '' });
      toast.success(`+${d.entry.pcs} pcs tercatat`);
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  const delEntry = async (id) => {
    const r = await fetch(`${API}/api/marketing/kol/creators/${creator.id}/incentive/entries/${id}`,
      { method: 'DELETE', headers: H });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal menghapus'); return; }
    setData(d); toast.success('Entri dihapus');
  };

  const closePeriod = async () => {
    if (!window.confirm('Tutup periode ini dan mulai dari 0 hari ini? Entri lama tetap tersimpan.')) return;
    setBusy(true);
    try {
      const r = await fetch(`${API}/api/marketing/kol/creators/${creator.id}/incentive/close-period`,
        { method: 'POST', headers: H });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal menutup periode');
      setData(d); setCfg(d.config);
      toast.success(`Periode ditutup pada ${rp(d.closed)} — hitungan dimulai dari 0`);
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  if (!data || !cfg) {
    return (
      <div className="fixed inset-0 bg-foreground/60 z-50 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-white" />
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-foreground/60 z-50 flex items-center justify-center p-4 overflow-auto"
      data-testid="creator-incentive-panel">
      <div className="bg-[hsl(var(--card))] border border-foreground/10 rounded-2xl w-full max-w-3xl max-h-[92vh] overflow-auto">
        <div className="p-5 border-b border-foreground/10 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Target className="w-5 h-5" /> Insentif · {data.creator_name}
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Tipe <b className="uppercase">{data.creator_type}</b> · periode {data.period.period_months} bulan
              ({data.period.start} → {data.period.end})
            </p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-sm"
            data-testid="incentive-close-btn">Tutup</button>
        </div>

        {!data.eligible && (
          <div className="m-5 p-3 rounded-lg border border-amber-500/40 bg-amber-500/10 text-xs
            text-amber-700 dark:text-amber-300 flex items-start gap-2" data-testid="incentive-not-eligible">
            <AlertTriangle className="w-4 h-4 mt-0.5" /> {data.eligible_reason}
          </div>
        )}

        <div className="p-5 grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Pcs terjual (periode)" value={`${data.pcs_sold} pcs`} testId="incentive-pcs" />
          <Stat label="Target" value={data.target_pcs ? `${data.target_pcs} pcs` : '—'}
            hint={data.target_pcs ? `${data.progress_pct}% tercapai` : ''} testId="incentive-target" />
          <Stat label="Insentif per pcs" value={rp(data.per_pcs_amount)} testId="incentive-perpcs-amount" />
          <Stat label="Total insentif" value={rp(data.total_incentive)}
            hint={data.bonus_amount ? `termasuk bonus ${rp(data.bonus_amount)}` : ''}
            testId="incentive-total" />
        </div>

        <div className="px-5 pb-5 space-y-4">
          <div className="rounded-xl border border-foreground/10 p-4 space-y-3">
            <div className="text-sm font-medium">Konfigurasi</div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
              <Field label="Skema">
                <select data-testid="incentive-mode-select" value={cfg.mode}
                  onChange={(e) => setCfg({ ...cfg, mode: e.target.value })}
                  className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-2 py-1.5">
                  <option value="none">Tidak dapat insentif</option>
                  <option value="per_pcs">Rp per pcs terjual</option>
                  <option value="target_bonus">Bonus bila target tercapai</option>
                  <option value="both">Keduanya</option>
                </select>
              </Field>
              <Field label="Rp per pcs">
                <input data-testid="incentive-rate-input" type="number" min="0" value={cfg.rate_per_pcs}
                  onChange={(e) => setCfg({ ...cfg, rate_per_pcs: Number(e.target.value) })}
                  className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-2 py-1.5" />
              </Field>
              <Field label="Target pcs / periode">
                <input data-testid="incentive-targetpcs-input" type="number" min="0" value={cfg.target_pcs}
                  onChange={(e) => setCfg({ ...cfg, target_pcs: Number(e.target.value) })}
                  className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-2 py-1.5" />
              </Field>
              <Field label="Bonus target (Rp)">
                <input data-testid="incentive-bonus-input" type="number" min="0" value={cfg.bonus_amount}
                  onChange={(e) => setCfg({ ...cfg, bonus_amount: Number(e.target.value) })}
                  className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-2 py-1.5" />
              </Field>
              <Field label="Panjang periode (bulan)">
                <input data-testid="incentive-period-input" type="number" min="1" max="24"
                  value={cfg.period_months}
                  onChange={(e) => setCfg({ ...cfg, period_months: Number(e.target.value) })}
                  className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-2 py-1.5" />
              </Field>
              <Field label="Mulai periode">
                <input data-testid="incentive-start-input" type="date" value={cfg.period_start || ''}
                  onChange={(e) => setCfg({ ...cfg, period_start: e.target.value })}
                  className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-2 py-1.5" />
              </Field>
            </div>
            <div className="flex gap-2">
              <button data-testid="incentive-save-btn" disabled={busy} onClick={saveCfg}
                className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs flex items-center gap-1.5 disabled:opacity-50">
                <Save className="w-3.5 h-3.5" /> Simpan konfigurasi
              </button>
              <button data-testid="incentive-close-period-btn" disabled={busy} onClick={closePeriod}
                className="px-3 py-1.5 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-xs flex items-center gap-1.5">
                <RotateCcw className="w-3.5 h-3.5" /> Tutup periode &amp; mulai dari 0
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-foreground/10 p-4 space-y-3">
            <div className="text-sm font-medium">Tracker pcs terjual <span className="text-xs font-normal text-muted-foreground">(diinput staf marketing)</span></div>
            <div className="flex flex-wrap items-end gap-2">
              <Field label="Tanggal">
                <input data-testid="tracker-date-input" type="date" value={entry.date}
                  onChange={(e) => setEntry({ ...entry, date: e.target.value })}
                  className="bg-foreground/5 border border-foreground/10 rounded-lg px-2 py-1.5 text-sm" />
              </Field>
              <Field label="Pcs">
                <input data-testid="tracker-pcs-input" type="number" min="1" value={entry.pcs}
                  onChange={(e) => setEntry({ ...entry, pcs: e.target.value })}
                  className="w-24 bg-foreground/5 border border-foreground/10 rounded-lg px-2 py-1.5 text-sm" />
              </Field>
              <Field label="Catatan">
                <input data-testid="tracker-note-input" value={entry.note}
                  onChange={(e) => setEntry({ ...entry, note: e.target.value })}
                  placeholder="mis. live 20/08 toko A"
                  className="bg-foreground/5 border border-foreground/10 rounded-lg px-2 py-1.5 text-sm" />
              </Field>
              <button data-testid="tracker-add-btn" disabled={busy} onClick={addEntry}
                className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs flex items-center gap-1.5 disabled:opacity-50">
                <Plus className="w-3.5 h-3.5" /> Tambah
              </button>
            </div>
            <div className="max-h-56 overflow-auto">
              <table className="w-full text-xs" data-testid="tracker-table">
                <thead className="text-muted-foreground">
                  <tr><th className="text-left py-1">Tanggal</th><th className="text-right py-1">Pcs</th>
                    <th className="text-left py-1">Catatan</th><th className="text-left py-1">Diinput</th><th /></tr>
                </thead>
                <tbody>
                  {(data.entries || []).length === 0 ? (
                    <tr><td colSpan={5} className="py-3 text-center text-muted-foreground">
                      Belum ada entri pada periode ini.</td></tr>
                  ) : data.entries.map((e) => (
                    <tr key={e.id} className="border-t border-foreground/5">
                      <td className="py-1">{e.date}</td>
                      <td className="py-1 text-right">{e.pcs}</td>
                      <td className="py-1">{e.note || '—'}</td>
                      <td className="py-1 text-muted-foreground">{e.entered_by}</td>
                      <td className="py-1 text-right">
                        <button onClick={() => delEntry(e.id)} data-testid={`tracker-del-${e.id}`}
                          className="text-red-500 hover:text-red-600"><Trash2 className="w-3.5 h-3.5" /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, hint, testId }) {
  return (
    <div className="rounded-xl border border-foreground/10 p-3" data-testid={testId}>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold mt-0.5">{value}</div>
      {hint ? <div className="text-[10px] text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-[10px] uppercase tracking-wide text-muted-foreground mb-1">{label}</span>
      {children}
    </label>
  );
}
