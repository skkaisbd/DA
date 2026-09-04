import { Badge } from '@/components/ui/badge';
import { formatRupiah as fmt } from '@/lib/format';

// Baris jurnal GL pada akun bank sesi (posted, dalam periode). Sumber: rahaza_journal_entries.lines.
export function GlLinesTable({ lines, glAccountCode }) {
  if (!lines?.length) {
    return <p className="text-sm text-muted-foreground text-center py-8" data-testid="recon-gl-empty">Belum ada jurnal pada akun {glAccountCode} di periode ini.</p>;
  }
  return (
    <div className="overflow-x-auto" data-testid="recon-gl-table">
      <table className="w-full text-xs">
        <thead className="text-muted-foreground border-b">
          <tr><th className="text-left py-2 pr-2">Tanggal</th><th className="text-left pr-2">No. Jurnal</th><th className="text-left pr-2">Memo / Sumber</th>
            <th className="text-right pr-2">Masuk (Dr)</th><th className="text-right pr-2">Keluar (Cr)</th><th className="text-left">Status</th></tr>
        </thead>
        <tbody>
          {lines.map(g => (
            <tr key={g.key} className="border-b last:border-0" data-testid={`recon-gl-${g.key}`}>
              <td className="py-1.5 pr-2 whitespace-nowrap">{g.date}</td>
              <td className="pr-2 font-mono whitespace-nowrap">{g.je_number}</td>
              <td className="pr-2 max-w-[320px] truncate" title={g.memo}>{g.memo || g.description} <span className="text-muted-foreground">· {g.source_module}</span></td>
              <td className="pr-2 text-right text-green-700">{g.debit > 0 ? fmt(g.debit) : ''}</td>
              <td className="pr-2 text-right text-red-700">{g.credit > 0 ? fmt(g.credit) : ''}</td>
              <td>{g.is_matched ? <Badge className="bg-green-100 text-green-700 border-green-200 text-[10px]" variant="outline">Cocok</Badge>
                : <Badge variant="outline" className="text-[10px]">Belum di bank</Badge>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
