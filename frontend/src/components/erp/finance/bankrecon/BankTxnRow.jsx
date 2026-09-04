import { useState, useEffect } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Link2, Unlink, Trash2, Wand2, Banknote } from 'lucide-react';
import { formatRupiah as fmt } from '@/lib/format';
import { SettlementLinkPicker } from '../SettlementLinkPicker';

const API = process.env.REACT_APP_BACKEND_URL;

function CandidatePicker({ sessionId, txn, headers, onPick }) {
  const [items, setItems] = useState(null);
  useEffect(() => {
    axios.get(`${API}/api/finance/bank-recon/sessions/${sessionId}/transactions/${txn.id}/candidates`, { headers })
      .then(r => setItems(r.data.items || [])).catch(() => setItems([]));
  }, [sessionId, txn.id, headers]);
  if (items === null) return <p className="text-xs text-muted-foreground">Memuat kandidat…</p>;
  if (!items.length) return <p className="text-xs text-muted-foreground" data-testid="recon-no-candidates">Tidak ada baris jurnal akun bank dengan arah yang sama di periode ini.</p>;
  return (
    <div className="max-h-56 overflow-y-auto space-y-1" data-testid="recon-candidates">
      {items.map(g => (
        <button key={g.key} data-testid={`recon-cand-${g.key}`} onClick={() => onPick(g)}
          className={`w-full text-left p-2 rounded border text-xs hover:bg-primary/10 ${g.within_rule ? 'border-green-300' : ''}`}>
          <div className="flex justify-between gap-2">
            <span className="truncate">{g.date} · <span className="font-mono">{g.je_number}</span> · {g.memo || g.description}</span>
            <span className="font-medium whitespace-nowrap">{fmt(g.amount)}</span>
          </div>
          <div className="text-muted-foreground">
            Δ {fmt(Math.abs(g.amount_diff))} · {g.days_apart ?? '?'} hari {g.within_rule && <span className="text-green-700">· sesuai aturan</span>}
          </div>
        </button>
      ))}
    </div>
  );
}

// Satu baris mutasi bank + aksi: cocokkan manual, tautkan pencairan, buat penyesuaian, lepas, hapus.
export function BankTxnRow({ sessionId, txn, headers, readOnly, onMatch, onUnmatch, onAdjust, onDelete, onLinkSettlement }) {
  const [open, setOpen] = useState(null); // 'gl' | 'settlement' | 'adjust'
  const isIn = (txn.direction || (txn.type === 'debit' ? 'in' : 'out')) === 'in';
  return (
    <div className={`border rounded-lg p-3 ${txn.is_matched ? 'bg-green-50/40 border-green-200' : ''}`} data-testid={`recon-txn-${txn.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm">
            <span className={`w-2 h-2 rounded-full ${isIn ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-muted-foreground text-xs">{txn.txn_date}</span>
            <span className="truncate">{txn.description || '—'}</span>
            {txn.reference && <span className="text-xs text-muted-foreground">#{txn.reference}</span>}
          </div>
          {txn.is_matched && (
            <p className="text-xs text-green-700 mt-1" data-testid={`recon-txn-matchref-${txn.id}`}>
              ✓ {txn.match_ref} {txn.auto_matched ? '· otomatis' : ''} {Math.abs(txn.amount_diff || 0) > 0.01 ? `· selisih ${fmt(Math.abs(txn.amount_diff))}` : ''}
            </p>
          )}
        </div>
        <div className="text-right">
          <p className={`font-semibold text-sm ${isIn ? 'text-green-700' : 'text-red-700'}`}>{isIn ? '+' : '−'}{fmt(txn.amount)}</p>
          <Badge variant="outline" className="text-[10px]">{isIn ? 'Masuk' : 'Keluar'}</Badge>
        </div>
      </div>
      {!readOnly && (
        <div className="flex flex-wrap gap-1 mt-2">
          {txn.is_matched ? (
            <Button size="sm" variant="outline" data-testid={`recon-unmatch-${txn.id}`} onClick={() => onUnmatch(txn)}>
              <Unlink className="w-3 h-3 mr-1" /> Lepas
            </Button>
          ) : (
            <>
              <Button size="sm" variant="outline" data-testid={`recon-match-open-${txn.id}`} onClick={() => setOpen(open === 'gl' ? null : 'gl')}>
                <Link2 className="w-3 h-3 mr-1" /> Cocokkan ke jurnal
              </Button>
              {isIn && (
                <Button size="sm" variant="outline" data-testid={`recon-settle-open-${txn.id}`} onClick={() => setOpen(open === 'settlement' ? null : 'settlement')}>
                  <Banknote className="w-3 h-3 mr-1" /> Pencairan marketplace
                </Button>
              )}
              <Button size="sm" variant="outline" data-testid={`recon-adjust-open-${txn.id}`} onClick={() => setOpen(open === 'adjust' ? null : 'adjust')}>
                <Wand2 className="w-3 h-3 mr-1" /> Penyesuaian
              </Button>
              <Button size="sm" variant="ghost" data-testid={`recon-txn-delete-${txn.id}`} onClick={() => onDelete(txn)}>
                <Trash2 className="w-3 h-3 text-red-500" />
              </Button>
            </>
          )}
        </div>
      )}
      {open === 'gl' && !txn.is_matched && (
        <div className="mt-2 pl-3 border-l-2 border-primary/30">
          <CandidatePicker sessionId={sessionId} txn={txn} headers={headers} onPick={(g) => { setOpen(null); onMatch(txn, g); }} />
        </div>
      )}
      {open === 'settlement' && !txn.is_matched && (
        <div className="mt-2 pl-3 border-l-2 border-primary/30">
          <SettlementLinkPicker sessionId={sessionId} txn={txn} headers={headers} onLink={(...a) => { setOpen(null); onLinkSettlement(...a); }} />
        </div>
      )}
      {open === 'adjust' && !txn.is_matched && (
        <div className="mt-2 pl-3 border-l-2 border-primary/30 flex flex-wrap gap-1 text-xs">
          <span className="text-muted-foreground self-center mr-1">Jurnal ke akun bank sesi ini:</span>
          {isIn
            ? <Button size="sm" data-testid={`recon-adjust-interest-${txn.id}`} onClick={() => onAdjust(txn, 'interest_income')}>Bunga bank</Button>
            : <>
                <Button size="sm" data-testid={`recon-adjust-charge-${txn.id}`} onClick={() => onAdjust(txn, 'bank_charge')}>Biaya admin bank</Button>
                <Button size="sm" variant="outline" data-testid={`recon-adjust-fee-${txn.id}`} onClick={() => onAdjust(txn, 'service_fee')}>Biaya layanan</Button>
              </>}
        </div>
      )}
    </div>
  );
}
