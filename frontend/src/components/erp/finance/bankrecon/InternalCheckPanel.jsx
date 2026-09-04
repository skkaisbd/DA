import { Badge } from '@/components/ui/badge';
import { formatRupiah as fmt } from '@/lib/format';

const STATUS = {
  ok: ['OK', 'bg-green-100 text-green-700 border-green-200'],
  no_gl: ['Belum ke GL', 'bg-red-100 text-red-700 border-red-200'],
  gl_missing: ['Jurnal hilang', 'bg-red-100 text-red-700 border-red-200'],
  gl_voided: ['Jurnal void', 'bg-amber-100 text-amber-800 border-amber-200'],
  gl_outside_period: ['Beda periode', 'bg-amber-100 text-amber-800 border-amber-200'],
  amount_mismatch: ['Nominal beda', 'bg-red-100 text-red-700 border-red-200'],
};

// H-05: mutasi kas internal (rahaza_cash_movements) harus 1:1 dengan jurnal GL akun bank.
export function InternalCheckPanel({ check }) {
  if (!check) return null;
  const diff = Math.round((check.card_balance - check.gl_balance_now) * 100) / 100;
  return (
    <div className="space-y-3" data-testid="recon-internal-check">
      <div className={`rounded-lg border px-4 py-2 text-xs ${Math.abs(diff) < 0.01 ? 'border-green-300 bg-green-50' : 'border-amber-300 bg-amber-50'}`} data-testid="recon-ic-balance">
        Saldo kartu kas <strong>{fmt(check.card_balance)}</strong> vs saldo GL akun bank saat ini <strong>{fmt(check.gl_balance_now)}</strong>
        {Math.abs(diff) < 0.01 ? <span className="text-green-700"> · sinkron</span> : <span className="text-amber-800"> · selisih {fmt(diff)}</span>}
        {' '}· {check.issues.length} mutasi bermasalah · {check.gl_without_movement.length} jurnal bank tanpa mutasi kas
      </div>
      <table className="w-full text-xs">
        <thead className="text-muted-foreground border-b">
          <tr><th className="text-left py-2 pr-2">Tanggal</th><th className="text-left pr-2">Mutasi kas</th><th className="text-right pr-2">Nominal</th><th className="text-left pr-2">Jurnal</th><th className="text-left">Cek</th></tr>
        </thead>
        <tbody>
          {check.movements.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-muted-foreground">Tidak ada mutasi kas internal di periode ini.</td></tr>}
          {check.movements.map(m => {
            const [label, cls] = STATUS[m.status] || STATUS.ok;
            return (
              <tr key={m.id} className="border-b last:border-0" data-testid={`recon-ic-${m.id}`}>
                <td className="py-1.5 pr-2 whitespace-nowrap">{m.date}</td>
                <td className="pr-2">{m.ref_label || m.category} <span className="text-muted-foreground">· {m.source_module}</span></td>
                <td className={`pr-2 text-right ${m.direction === 'in' ? 'text-green-700' : 'text-red-700'}`}>{m.direction === 'in' ? '+' : '−'}{fmt(m.amount)}</td>
                <td className="pr-2 font-mono">{m.gl_je_number || '—'}</td>
                <td><Badge variant="outline" className={`text-[10px] ${cls}`} title={m.note}>{label}</Badge>{m.note && m.status !== 'ok' && <span className="text-muted-foreground ml-1">{m.note}</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {check.gl_without_movement.length > 0 && (
        <div className="text-xs text-muted-foreground" data-testid="recon-ic-gl-only">
          Jurnal bank tanpa mutasi kas (mis. pencairan marketplace, penyesuaian lama): {check.gl_without_movement.map(g => g.je_number).join(', ')}
        </div>
      )}
    </div>
  );
}
