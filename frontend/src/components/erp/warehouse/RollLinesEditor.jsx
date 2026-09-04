/**
 * RollLinesEditor — pengisi RINCIAN GULUNGAN saat kain masuk (FASE H-5).
 *
 * Aturan yang ditegakkan di layar (sama dengan backend, supaya penolakan tidak
 * datang sebagai kejutan setelah tombol simpan ditekan):
 *   · nomor roll TIDAK diketik — diterbitkan otomatis (RL-YYYYMM-####)
 *   · total berat/panjang seluruh gulungan HARUS sama dengan qty yang diterima,
 *     karena angka yang dipakai orang saat mencari kain adalah gulungannya,
 *     sementara laporan memakai stoknya. Dua angka berbeda = gudang berdebat
 *     dengan dirinya sendiri.
 *   · maksimum 200 gulungan per baris penerimaan
 */
import { Trash2, Plus, Layers, CheckCircle2, AlertTriangle, Wand2 } from 'lucide-react';
import { useState } from 'react';
import {
  rollLine, rollLinesState, splitEvenly, fmtQty, rollUomOf, num,
} from './rollLines';

export default function RollLinesEditor({
  lines = [],
  accepted = 0,
  unit = '',
  onChange,
  testPrefix = 'roll-lines',
  nextNumberHint = '',
  disabled = false,
  title = 'Rincian Gulungan',
  subtitle = '',
}) {
  const [bulk, setBulk] = useState('');
  const uom = rollUomOf(unit) || unit || '';
  const st = rollLinesState(lines, accepted);

  const set = (next) => !disabled && onChange?.(next);
  const update = (i, field, val) => set(lines.map((l, idx) => (idx === i ? { ...l, [field]: val } : l)));
  const add = () => set([...lines, rollLine('')]);
  const remove = (i) => set(lines.filter((_, idx) => idx !== i));
  const doSplit = () => {
    const n = Math.max(1, Math.floor(num(bulk) || 1));
    set(splitEvenly(accepted, n));
  };

  const badge = {
    empty: {
      cls: 'bg-amber-50 dark:bg-amber-400/10 text-amber-800 dark:text-amber-300 border-amber-300 dark:border-amber-400/30',
      icon: AlertTriangle,
      text: 'Belum ada gulungan — kain ini akan masuk daftar "Penerimaan tanpa roll"',
    },
    match: {
      cls: 'bg-emerald-50 dark:bg-emerald-400/10 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-400/30',
      icon: CheckCircle2,
      text: `Cocok — ${st.count} gulungan = ${fmtQty(st.total)} ${uom}`,
    },
    over: {
      cls: 'bg-red-50 dark:bg-red-400/10 text-red-700 dark:text-red-300 border-red-300 dark:border-red-400/30',
      icon: AlertTriangle,
      text: `Kelebihan ${fmtQty(Math.abs(st.diff), 3)} ${uom} — total gulungan ${fmtQty(st.total)} vs diterima ${fmtQty(accepted)}`,
    },
    under: {
      cls: 'bg-red-50 dark:bg-red-400/10 text-red-700 dark:text-red-300 border-red-300 dark:border-red-400/30',
      icon: AlertTriangle,
      text: st.hasZero
        ? 'Ada gulungan yang berat/panjangnya masih 0 — isi angkanya'
        : `Kurang ${fmtQty(Math.abs(st.diff), 3)} ${uom} — total gulungan ${fmtQty(st.total)} vs diterima ${fmtQty(accepted)}`,
    },
  }[st.state];
  const BadgeIcon = badge.icon;

  return (
    <div className="rounded-xl border border-violet-300 dark:border-violet-400/30 bg-violet-50/70 dark:bg-violet-400/5 p-3 space-y-2.5"
      data-testid={`${testPrefix}-panel`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-start gap-2">
          <Layers className="w-4 h-4 mt-0.5 text-violet-600 dark:text-violet-300 shrink-0" />
          <div>
            <p className="text-xs font-semibold text-violet-800 dark:text-violet-200">
              {title} <span className="font-normal text-violet-700/80 dark:text-violet-300/80">· nomor roll otomatis{nextNumberHint ? ` (berikutnya ${nextNumberHint})` : ''}</span>
            </p>
            <p className="text-[11px] text-violet-700/80 dark:text-violet-300/70">
              {subtitle || `Isi berat/panjang tiap gulungan. Totalnya harus sama dengan qty diterima (${fmtQty(accepted)} ${uom}).`}
            </p>
          </div>
        </div>
        {!disabled && (
          <div className="flex items-center gap-1.5">
            <input
              type="number" min="1" max="200" value={bulk}
              onChange={(e) => setBulk(e.target.value)}
              placeholder="jml roll"
              className="h-8 w-24 px-2 rounded-lg border border-violet-300 dark:border-violet-400/30 bg-[var(--input-surface)] text-xs text-foreground"
              data-testid={`${testPrefix}-bulk-count`}
            />
            <button type="button" onClick={doSplit}
              className="h-8 px-2.5 rounded-lg bg-violet-600 text-white text-xs font-medium hover:brightness-110 inline-flex items-center gap-1"
              data-testid={`${testPrefix}-split`}>
              <Wand2 className="w-3.5 h-3.5" /> Bagi rata
            </button>
          </div>
        )}
      </div>

      {lines.length > 0 && (
        <div className="rounded-lg border border-violet-200 dark:border-violet-400/20 overflow-hidden bg-[var(--card-surface)]">
          <table className="w-full text-xs" data-testid={`${testPrefix}-table`}>
            <thead className="bg-violet-100/70 dark:bg-violet-400/10">
              <tr className="text-left text-violet-900 dark:text-violet-200">
                <th className="px-2 py-1.5 font-semibold w-10">#</th>
                <th className="px-2 py-1.5 font-semibold">Nomor roll</th>
                <th className="px-2 py-1.5 font-semibold w-32">{uom === 'kg' ? 'Berat (kg)' : `Panjang (${uom || 'm'})`}</th>
                <th className="px-2 py-1.5 font-semibold w-32">Lot warna</th>
                <th className="px-2 py-1.5 font-semibold">Catatan</th>
                {!disabled && <th className="px-2 py-1.5 w-8" />}
              </tr>
            </thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={i} className="border-t border-violet-200/60 dark:border-violet-400/15"
                  data-testid={`${testPrefix}-row-${i}`}>
                  <td className="px-2 py-1 text-muted-foreground">{i + 1}</td>
                  <td className="px-2 py-1 font-mono text-[11px] text-muted-foreground">
                    {l.roll_no || 'otomatis'}
                  </td>
                  <td className="px-2 py-1">
                    <input
                      type="number" step="0.001" min="0" value={l.qty}
                      disabled={disabled}
                      onChange={(e) => update(i, 'qty', e.target.value)}
                      className={`h-8 w-full px-2 rounded-lg border bg-[var(--input-surface)] text-xs text-foreground tabular-nums ${
                        num(l.qty) > 0 ? 'border-violet-300 dark:border-violet-400/30' : 'border-red-400 dark:border-red-400/50'}`}
                      data-testid={`${testPrefix}-qty-${i}`}
                    />
                  </td>
                  <td className="px-2 py-1">
                    <input
                      value={l.color_lot || ''} disabled={disabled}
                      onChange={(e) => update(i, 'color_lot', e.target.value)}
                      placeholder="LOT-A"
                      className="h-8 w-full px-2 rounded-lg border border-violet-300 dark:border-violet-400/30 bg-[var(--input-surface)] text-xs text-foreground"
                      data-testid={`${testPrefix}-lot-${i}`}
                    />
                  </td>
                  <td className="px-2 py-1">
                    <input
                      value={l.notes || ''} disabled={disabled}
                      onChange={(e) => update(i, 'notes', e.target.value)}
                      placeholder="mis. ujung basah"
                      className="h-8 w-full px-2 rounded-lg border border-violet-300 dark:border-violet-400/30 bg-[var(--input-surface)] text-xs text-foreground"
                      data-testid={`${testPrefix}-notes-${i}`}
                    />
                  </td>
                  {!disabled && (
                    <td className="px-2 py-1 text-right">
                      <button type="button" onClick={() => remove(i)}
                        className="text-red-600 hover:text-red-500"
                        aria-label={`Hapus gulungan ${i + 1}`}
                        data-testid={`${testPrefix}-remove-${i}`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        {!disabled ? (
          <button type="button" onClick={add}
            className="h-8 px-2.5 rounded-lg border border-violet-300 dark:border-violet-400/30 text-xs font-medium text-violet-800 dark:text-violet-200 hover:bg-violet-100 dark:hover:bg-violet-400/10 inline-flex items-center gap-1"
            data-testid={`${testPrefix}-add`}>
            <Plus className="w-3.5 h-3.5" /> Tambah gulungan
          </button>
        ) : <span />}
        <div className={`inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full border ${badge.cls}`}
          data-testid={`${testPrefix}-status`}>
          <BadgeIcon className="w-3.5 h-3.5" /> {badge.text}
        </div>
      </div>
    </div>
  );
}
