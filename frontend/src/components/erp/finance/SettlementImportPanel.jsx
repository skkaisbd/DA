/**
 * SettlementImportPanel — hasil baca laporan pencairan (Shopee/TikTok) yang MENGISI form,
 * bukan menyimpan. Setiap kolom angka bisa DIARAHKAN ke field tujuan (atau diabaikan);
 * saat pencairan disimpan, pemetaan ini diingat per toko + sidik format header, sehingga
 * impor berikutnya dengan format sama tidak perlu diperiksa ulang (aturan BD-2: pemetaan
 * terlihat & dikonfirmasi manusia, bukan ditebak diam-diam).
 */
import { FileSpreadsheet, X, AlertTriangle, BookmarkCheck, Wand2 } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Badge } from '@/components/ui/badge';
import { formatRupiah as rp } from '@/lib/format';

export const FIELD_LABELS = {
  gross_sales: 'Omzet bruto', refunds: 'Refund / retur', seller_discount: 'Diskon penjual',
  shipping_subsidy: 'Subsidi ongkir', platform_commission: 'Komisi platform',
  platform_service_fee: 'Fee layanan', affiliate_commission: 'Komisi afiliasi',
  ads_deduction: 'Potongan iklan', other_deductions: 'Potongan lain',
  adjustments: 'Penyesuaian', net_payout: 'Nominal dicairkan',
};

// Sama persis dengan `compute_values` di backend/core/settlement_import.py.
export function computeValues(mapping, columnTotals) {
  const out = {};
  Object.keys(FIELD_LABELS).forEach((f) => {
    const total = (mapping[f] || []).reduce((t, c) => t + (parseFloat(columnTotals[c]) || 0), 0);
    out[f] = Math.round((f === 'adjustments' ? total : Math.abs(total)) * 100) / 100;
  });
  return out;
}

function fieldOf(mapping, col) {
  return Object.keys(mapping).find((f) => (mapping[f] || []).includes(col)) || '';
}

export function SettlementImportPanel({ result, onClose, onMappingChange }) {
  if (!result) return null;
  const mapping = result.mapping || {};
  const cols = result.numeric_columns || [];
  const unmapped = cols.filter((c) => !fieldOf(mapping, c));
  const saved = result.mapping_source === 'saved';

  const retarget = (col, field) => {
    const next = {};
    Object.entries(mapping).forEach(([f, cs]) => {
      const rest = cs.filter((c) => c !== col);
      if (rest.length) next[f] = rest;
    });
    if (field) next[field] = [...(next[field] || []), col];
    onMappingChange?.(next);
  };

  return (
    <GlassCard className="p-4 space-y-2" data-testid="fin-settlement-import-panel">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium text-sm flex items-center gap-2 flex-wrap">
          <FileSpreadsheet className="w-4 h-4" /> Hasil baca “{result.filename}”
          <span className="text-xs text-foreground/50">
            {result.row_count} baris · {result.platform_guess || 'platform tidak terdeteksi'}
          </span>
          {saved ? (
            <Badge variant="outline" className="text-[10px] text-emerald-600 border-emerald-500/40"
              data-testid="fin-settlement-import-saved-badge">
              <BookmarkCheck className="w-3 h-3 mr-1" /> pemetaan tersimpan ✓
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-500/40"
              data-testid="fin-settlement-import-auto-badge">
              <Wand2 className="w-3 h-3 mr-1" /> tebakan otomatis — periksa
            </Badge>
          )}
        </h3>
        <button data-testid="fin-settlement-import-close" onClick={onClose}
          className="p-1 rounded hover:bg-foreground/10"><X className="w-4 h-4" /></button>
      </div>
      <p className="text-xs text-foreground/60">
        {saved
          ? 'Format laporan ini sudah pernah dikonfirmasi untuk toko ini — kolom dipetakan sesuai pilihan sebelumnya. Anda tetap bisa mengubahnya.'
          : 'Arahkan tiap kolom angka ke field tujuan. Saat pencairan disimpan, pemetaan ini diingat untuk toko & format laporan yang sama.'}
        {' '}Tidak ada yang tersimpan sebelum Anda menekan Simpan.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-xs" data-testid="fin-settlement-import-mapping">
          <thead>
            <tr className="text-foreground/50 uppercase tracking-wide border-b border-foreground/10">
              <th className="text-left py-1.5 pr-2">Kolom di laporan</th>
              <th className="text-right py-1.5 px-2">Total</th>
              <th className="text-left py-1.5 pl-2">Masuk ke field</th>
            </tr>
          </thead>
          <tbody>
            {cols.map((c) => {
              const f = fieldOf(mapping, c);
              return (
                <tr key={c} className={`border-b border-foreground/5 ${f ? '' : 'bg-amber-500/5'}`}
                  data-testid={`fin-settlement-import-col-${c.replace(/[^a-zA-Z0-9]+/g, '-')}`}>
                  <td className="py-1.5 pr-2">{c}</td>
                  <td className="py-1.5 px-2 text-right tabular-nums">{rp(result.column_totals?.[c] || 0)}</td>
                  <td className="py-1.5 pl-2">
                    <select value={f} onChange={(e) => retarget(c, e.target.value)}
                      data-testid={`fin-settlement-import-target-${c.replace(/[^a-zA-Z0-9]+/g, '-')}`}
                      className={`h-7 rounded-md border px-1.5 text-xs bg-foreground/5 ${f ? 'border-foreground/10' : 'border-amber-500/50 text-amber-700 dark:text-amber-300'}`}>
                      <option value="">— abaikan —</option>
                      {Object.entries(FIELD_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                    </select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {unmapped.length > 0 ? (
        <div className="text-xs rounded-lg bg-amber-500/10 text-amber-800 dark:text-amber-200 px-3 py-2 flex items-center gap-1.5"
          data-testid="fin-settlement-import-unmapped">
          <AlertTriangle className="w-3.5 h-3.5" /> {unmapped.length} kolom angka diabaikan: {unmapped.join(', ')} — pastikan tidak ada potongan yang terlewat.
        </div>
      ) : null}
    </GlassCard>
  );
}
