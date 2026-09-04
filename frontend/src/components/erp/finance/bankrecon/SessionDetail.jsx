import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2, ArrowLeft, Sparkles, Upload, CheckCircle2, RefreshCw } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { formatRupiah as fmt } from '@/lib/format';
import { STATUS_CFG } from './SessionList';
import { ReconSummary } from './ReconSummary';
import { ImportPanel } from './ImportPanel';
import { BankTxnRow } from './BankTxnRow';
import { GlLinesTable } from './GlLinesTable';
import { InternalCheckPanel } from './InternalCheckPanel';

const API = process.env.REACT_APP_BACKEND_URL;

export function SessionDetail({ sessionId, headers, onBack }) {
  const { toast } = useToast();
  const [session, setSession] = useState(null);
  const [txns, setTxns] = useState([]);
  const [check, setCheck] = useState(null);
  const [filter, setFilter] = useState('all');
  const [showImport, setShowImport] = useState(false);
  const [busy, setBusy] = useState(false);
  const [closing, setClosing] = useState('');
  const base = `${API}/api/finance/bank-recon/sessions/${sessionId}`;
  const fail = useCallback((e) => toast({ title: 'Gagal', description: e?.response?.data?.detail || e.message, variant: 'destructive' }), [toast]);

  const load = useCallback(async () => {
    try {
      const [s, t, c] = await Promise.all([
        axios.get(base, { headers }),
        axios.get(`${base}/transactions`, { headers, params: { limit: 500 } }),
        axios.get(`${base}/internal-check`, { headers }),
      ]);
      setSession(s.data); setTxns(t.data.items || []); setCheck(c.data);
      setClosing(String(s.data.closing_balance ?? ''));
    } catch (e) { fail(e); }
  }, [base, headers, fail]);

  useEffect(() => { load(); }, [load]);

  const act = async (fn, okTitle) => {
    setBusy(true);
    try { const r = await fn(); if (okTitle) toast({ title: okTitle, description: r?.data?.message || r?.data?.warning }); await load(); }
    catch (e) { fail(e); } finally { setBusy(false); }
  };
  const autoMatch = () => act(() => axios.post(`${base}/auto-match`, {}, { headers }), 'Auto-match');
  const approve = () => act(() => axios.post(`${base}/approve`, {}, { headers }), 'Sesi disetujui');
  const saveClosing = () => act(() => axios.put(base, { closing_balance: parseFloat(closing) || 0 }, { headers }), 'Saldo akhir disimpan');
  const onMatch = (txn, g) => act(() => axios.post(`${base}/match`, { txn_id: txn.id, target_key: g.key }, { headers }), 'Dicocokkan');
  const onUnmatch = (txn) => act(() => axios.post(`${base}/unmatch`, { txn_id: txn.id }, { headers }), 'Tautan dilepas');
  const onAdjust = (txn, type) => act(() => axios.post(`${base}/transactions/${txn.id}/adjust`, { adjustment_type: type }, { headers }), 'Penyesuaian dijurnal');
  const onDelete = (txn) => window.confirm('Hapus mutasi ini?') && act(() => axios.delete(`${base}/transactions/${txn.id}`, { headers }), 'Mutasi dihapus');
  const onLinkSettlement = () => act(() => Promise.resolve({}), 'Pencairan ditautkan');

  if (!session) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin" /></div>;
  const readOnly = session.status === 'approved';
  const st = STATUS_CFG[session.status] || STATUS_CFG.draft;
  const shown = txns.filter(t => filter === 'all' ? true : filter === 'matched' ? t.is_matched : !t.is_matched);

  return (
    <div className="space-y-4" data-testid="recon-session-detail">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" data-testid="recon-back" onClick={onBack}><ArrowLeft className="w-4 h-4" /></Button>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold">{session.period} · {session.account_name}</h3>
              <span className="font-mono text-xs text-muted-foreground">GL {session.gl_account_code}</span>
              <Badge variant="outline" className={`text-[10px] ${st.color}`}>{st.label}</Badge>
            </div>
            <p className="text-xs text-muted-foreground">{session.total_bank_txns} mutasi · {session.matched_count} cocok · {session.unmatched_count} belum</p>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button size="sm" variant="outline" data-testid="recon-refresh" onClick={load}><RefreshCw className="w-4 h-4" /></Button>
          {!readOnly && <>
            <Button size="sm" variant="outline" data-testid="recon-import-toggle" onClick={() => setShowImport(v => !v)}><Upload className="w-4 h-4 mr-1" /> Impor Mutasi</Button>
            <Button size="sm" data-testid="recon-auto-match" onClick={autoMatch} disabled={busy}>
              {busy ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Sparkles className="w-4 h-4 mr-1" />} Auto-match
            </Button>
            <Button size="sm" variant="outline" className="border-green-300 text-green-700" data-testid="recon-approve"
              onClick={approve} disabled={busy || session.unmatched_count > 0 || !session.total_bank_txns}>
              <CheckCircle2 className="w-4 h-4 mr-1" /> Setujui
            </Button>
          </>}
        </div>
      </div>

      {!readOnly && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">Saldo akhir rekening koran:</span>
          <input type="number" data-testid="recon-closing-input" className="border rounded px-2 py-1 w-44" value={closing} onChange={e => setClosing(e.target.value)} />
          <Button size="sm" variant="outline" data-testid="recon-closing-save" onClick={saveClosing} disabled={busy}>Simpan</Button>
        </div>
      )}
      <ReconSummary summary={session.summary} />
      {showImport && !readOnly && <ImportPanel sessionId={sessionId} headers={headers} onDone={() => { setShowImport(false); load(); }} />}

      <Tabs defaultValue="bank">
        <TabsList>
          <TabsTrigger value="bank" data-testid="recon-tab-bank">Mutasi Bank ({txns.length})</TabsTrigger>
          <TabsTrigger value="gl" data-testid="recon-tab-gl">Jurnal GL Akun Bank ({session.gl_lines?.length || 0})</TabsTrigger>
          <TabsTrigger value="internal" data-testid="recon-tab-internal">Kas Internal vs GL {check?.issues?.length ? `(${check.issues.length} !)` : ''}</TabsTrigger>
        </TabsList>
        <TabsContent value="bank" className="space-y-2">
          <div className="flex gap-1 text-xs">
            {[['all', 'Semua'], ['unmatched', 'Belum cocok'], ['matched', 'Cocok']].map(([k, l]) => (
              <button key={k} data-testid={`recon-filter-${k}`} onClick={() => setFilter(k)}
                className={`px-3 py-1 rounded-full border ${filter === k ? 'bg-primary text-primary-foreground' : ''}`}>{l}</button>
            ))}
          </div>
          {shown.length === 0 && <p className="text-sm text-muted-foreground text-center py-8" data-testid="recon-txn-empty">Belum ada mutasi. Impor rekening koran (CSV) atau tambah manual.</p>}
          {shown.map(t => (
            <BankTxnRow key={t.id} sessionId={sessionId} txn={t} headers={headers} readOnly={readOnly}
              onMatch={onMatch} onUnmatch={onUnmatch} onAdjust={onAdjust} onDelete={onDelete} onLinkSettlement={onLinkSettlement} />
          ))}
          {txns.length > 0 && (
            <p className="text-xs text-muted-foreground text-right">Total masuk {fmt(session.in_total || 0)} · keluar {fmt(session.out_total || 0)}</p>
          )}
        </TabsContent>
        <TabsContent value="gl"><GlLinesTable lines={session.gl_lines} glAccountCode={session.gl_account_code} /></TabsContent>
        <TabsContent value="internal"><InternalCheckPanel check={check} /></TabsContent>
      </Tabs>
    </div>
  );
}
