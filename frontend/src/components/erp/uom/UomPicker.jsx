/**
 * UomPicker — pemilih satuan + pratinjau konversi untuk titik masuk/keluar stok.
 *
 * Dipakai di: Penerimaan Gudang (scan-in), Put-away, Opname Gudang (scan),
 * Opname Aksesoris, Pengeluaran Material (Material Issue), Pengeluaran/Penerimaan
 * Aksesoris, dan Progres Cutting.
 *
 * Aturan yang dijaga komponen ini:
 *  • Nilai default = satuan dasar material ⇒ perilaku lama TIDAK berubah.
 *  • Hanya menawarkan satuan yang server PASTI bisa konversi (kemasan material,
 *    satuan sedimensi global, dan kain m⇄kg via gramasi & lebar).
 *  • Selalu menampilkan hasil konversi ("3 box = 36 pcs") SEBELUM disimpan.
 */
import React from 'react';
import { AlertTriangle, ArrowRight } from 'lucide-react';

const SOURCE_LABEL = {
  base: 'satuan dasar',
  uom: 'kemasan master',
  global: 'konversi otomatis',
  fabric: 'via gramasi & lebar',
};

const fmtNum = (n) => {
  const v = Number(n || 0);
  return Number.isFinite(v)
    ? v.toLocaleString('id-ID', { maximumFractionDigits: 4 })
    : '0';
};

/** Faktor satuan `unit` terhadap satuan dasar. `null` bila tidak dikenal. */
export function uomFactor(opt, unit) {
  if (!opt) return null;
  const u = String(unit || '').trim().toLowerCase();
  if (!u || u === String(opt.base_unit || '').toLowerCase()) return 1;
  const row = (opt.units || []).find((x) => String(x.unit).toLowerCase() === u);
  return row ? Number(row.factor_to_base) : null;
}

/** Konversi qty ke satuan dasar. Mengembalikan `null` bila satuan tak dikenal. */
export function toBaseQty(opt, qty, unit) {
  const f = uomFactor(opt, unit);
  if (f == null) return null;
  return Math.round(Number(qty || 0) * f * 10000) / 10000;
}

/** Satuan dasar material (fallback ke `unit` yang sudah dipegang layar). */
export const baseUnitOf = (opt, fallback = '') =>
  String(opt?.base_unit || fallback || '').toLowerCase();

/**
 * Dropdown satuan. Nilai kosong = satuan dasar.
 */
export function UomSelect({
  opt, value, onChange, testId, className = '', disabled = false, fallbackUnit = '',
}) {
  const base = baseUnitOf(opt, fallbackUnit);
  const units = opt?.units?.length
    ? opt.units
    : (base ? [{ unit: base, label: `${base} (satuan dasar)`, factor_to_base: 1, source: 'base' }] : []);
  const only = units.length <= 1;
  return (
    <select
      value={String(value || base || '')}
      onChange={onChange}
      disabled={disabled || only}
      data-testid={testId}
      title={only ? 'Belum ada satuan alternatif — tambahkan kemasan di Master Material' : 'Pilih satuan hitung fisik'}
      className={`h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground
        disabled:opacity-70 disabled:cursor-not-allowed ${className}`}
    >
      {units.map((u) => (
        <option key={u.unit} value={u.unit}>{u.unit}</option>
      ))}
    </select>
  );
}

/**
 * Baris pratinjau konversi: "3 box = 36 pcs (kemasan master)".
 * Menampilkan peringatan bila satuan tidak bisa dikonversi.
 */
export function UomConversionHint({
  opt, qty, unit, className = '', testId, fallbackUnit = '',
}) {
  const base = baseUnitOf(opt, fallbackUnit);
  const u = String(unit || base || '').toLowerCase();
  const q = Number(qty || 0);
  if (!u || !q) return null;

  if (!opt) {
    return (
      <p className={`text-[11px] text-muted-foreground ${className}`} data-testid={testId}>
        {fmtNum(q)} {u}
      </p>
    );
  }
  if (u === base) {
    return (
      <p className={`text-[11px] text-muted-foreground ${className}`} data-testid={testId}>
        {fmtNum(q)} {u} — satuan dasar
      </p>
    );
  }
  const row = (opt.units || []).find((x) => String(x.unit).toLowerCase() === u);
  if (!row) {
    return (
      <p className={`text-[11px] text-amber-700 dark:text-amber-400 flex items-center gap-1 ${className}`}
        data-testid={testId}>
        <AlertTriangle className="w-3 h-3 shrink-0" />
        Satuan &lsquo;{u}&rsquo; belum punya faktor — lengkapi kemasannya di Master Material.
      </p>
    );
  }
  return (
    <p className={`text-[11px] text-emerald-700 dark:text-emerald-400 flex items-center gap-1 ${className}`}
      data-testid={testId}>
      {fmtNum(q)} {u} <ArrowRight className="w-3 h-3 shrink-0" />
      <strong>{fmtNum(q * Number(row.factor_to_base))} {base}</strong>
      <span className="text-muted-foreground">({SOURCE_LABEL[row.source] || row.source})</span>
    </p>
  );
}

/**
 * Gabungan input qty + pemilih satuan + pratinjau — untuk form baris tunggal.
 */
export default function UomPicker({
  opt, qty, unit, onQtyChange, onUnitChange, fallbackUnit = '',
  testIdPrefix = 'uom', qtyProps = {}, disabled = false, hideHint = false,
}) {
  return (
    <div className="space-y-1">
      <div className="flex gap-2">
        <input
          type="number" step="0.0001" min="0" value={qty}
          onChange={onQtyChange} disabled={disabled}
          data-testid={`${testIdPrefix}-qty`}
          className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
          {...qtyProps}
        />
        <UomSelect
          opt={opt} value={unit} onChange={onUnitChange} disabled={disabled}
          fallbackUnit={fallbackUnit} testId={`${testIdPrefix}-unit`} className="w-24 shrink-0"
        />
      </div>
      {!hideHint && (
        <UomConversionHint opt={opt} qty={qty} unit={unit} fallbackUnit={fallbackUnit}
          testId={`${testIdPrefix}-hint`} />
      )}
    </div>
  );
}
