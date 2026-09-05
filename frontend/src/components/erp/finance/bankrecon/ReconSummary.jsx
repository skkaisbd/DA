import { Card, CardContent } from '@/components/ui/card';
import { formatRupiah as fmt } from '@/lib/format';

// Ringkasan: saldo GL akun bank vs saldo rekening koran, dijelaskan oleh item yang belum cocok.
// Pada sesi approved, `summary` = approved_summary (snapshot saat disetujui), bukan hitungan live.
export function ReconSummary({ summary, approved }) {
  if (!summary) return null;
  const tone = approved ? 'border-slate-300 bg-slate-50' : summary.explained ? 'border-green-300 bg-green-50' : 'border-amber-300 bg-amber-50';
  return (
    <div className="space-y-2" data-testid="recon-summary">
      {approved && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground" data-testid="recon-approved-note">
          <span className="font-medium text-slate-700">Ringkasan saat disetujui</span>
          {approved.at && <span>· {String(approved.at).slice(0, 10)}</span>}
          {approved.by && <span>· oleh {approved.by}</span>}
          {approved.withUnexplained && <span className="text-amber-700 font-medium" data-testid="recon-approved-unexplained-flag">· disetujui dengan selisih {fmt(summary.unexplained)}</span>}
        </div>
      )}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          ['Saldo GL akun bank (akhir periode)', summary.gl_balance_end, 'recon-sum-gl'],
          ['Saldo rekening koran', summary.statement_closing, 'recon-sum-statement'],
          ['Mutasi bank belum cocok', `${summary.unmatched_bank_count} · masuk ${fmt(summary.unmatched_bank_in)} / keluar ${fmt(summary.unmatched_bank_out)}`, 'recon-sum-unbank'],
          ['Jurnal GL belum cocok', `${summary.unmatched_gl_count} · masuk ${fmt(summary.unmatched_gl_in)} / keluar ${fmt(summary.unmatched_gl_out)}`, 'recon-sum-ungl'],
        ].map(([label, val, tid]) => (
          <Card key={tid}><CardContent className="pt-3 pb-3">
            <p className="text-sm font-semibold" data-testid={tid}>{typeof val === 'number' ? fmt(val) : val}</p>
            <p className="text-[11px] text-muted-foreground mt-0.5">{label}</p>
          </CardContent></Card>
        ))}
      </div>
      <div className={`rounded-lg border px-4 py-2 text-xs ${tone}`} data-testid="recon-sum-explained">
        Saldo GL {fmt(summary.gl_balance_end)} + mutasi bank belum dijurnal ({fmt(summary.unmatched_bank_in - summary.unmatched_bank_out)})
        − jurnal belum tampak di bank ({fmt(summary.unmatched_gl_in - summary.unmatched_gl_out)}) = <strong>{fmt(summary.adjusted_gl_balance)}</strong>
        {' '}vs rekening koran <strong>{fmt(summary.statement_closing)}</strong> →{' '}
        {summary.explained ? <strong className="text-green-700">selisih terjelaskan</strong>
          : <strong className={approved ? 'text-slate-700' : 'text-amber-800'}>
              {approved ? 'selisih ' : 'selisih belum terjelaskan '}{fmt(summary.unexplained)}{approved ? ' (dicatat saat persetujuan)' : ''}
            </strong>}
      </div>
    </div>
  );
}
