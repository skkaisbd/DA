import { useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Loader2, Upload } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const API = process.env.REACT_APP_BACKEND_URL;

// Impor mutasi rekening koran: file CSV, tempel teks, atau input manual satu baris.
export function ImportPanel({ sessionId, headers, onDone }) {
  const { toast } = useToast();
  const [tab, setTab] = useState('file');
  const [busy, setBusy] = useState(false);
  const [bulkText, setBulkText] = useState('');
  const [form, setForm] = useState({ txn_date: '', description: '', reference: '', amount: '', direction: 'in' });
  const base = `${API}/api/finance/bank-recon/sessions/${sessionId}`;
  const fail = (e) => toast({ title: 'Gagal', description: e?.response?.data?.detail || e.message, variant: 'destructive' });

  const uploadCsv = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      const { data } = await axios.post(`${base}/import-csv`, fd, { headers: { ...headers, 'Content-Type': 'multipart/form-data' } });
      toast({ title: 'Impor CSV', description: data.message }); onDone();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const importBulk = async () => {
    const transactions = bulkText.split('\n').map(l => l.trim()).filter(Boolean).map(l => {
      const p = l.split(',').map(x => x.trim());
      return { txn_date: p[0], description: p[1] || '', amount: parseFloat(p[2]) || 0,
        direction: (p[3] || 'in').toLowerCase().startsWith('k') || (p[3] || '').toLowerCase() === 'out' ? 'out' : 'in', reference: p[4] || '' };
    });
    if (!transactions.length) return;
    setBusy(true);
    try {
      const { data } = await axios.post(`${base}/import-bulk`, { transactions }, { headers });
      toast({ title: 'Impor', description: data.message }); setBulkText(''); onDone();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const addOne = async () => {
    setBusy(true);
    try {
      await axios.post(`${base}/transactions`, { ...form, amount: parseFloat(form.amount) || 0 }, { headers });
      toast({ title: 'Mutasi ditambahkan' }); setForm({ txn_date: '', description: '', reference: '', amount: '', direction: 'in' }); onDone();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const inputCls = 'border rounded-lg px-3 py-2 text-sm w-full';
  return (
    <div className="border rounded-lg p-4 space-y-3 bg-muted/30" data-testid="recon-import-panel">
      <div className="flex gap-2 text-xs">
        {[['file', 'Unggah CSV'], ['paste', 'Tempel Teks'], ['manual', 'Input Manual']].map(([k, l]) => (
          <button key={k} data-testid={`recon-import-tab-${k}`} onClick={() => setTab(k)}
            className={`px-3 py-1.5 rounded-full border ${tab === k ? 'bg-primary text-primary-foreground' : 'bg-background'}`}>{l}</button>
        ))}
      </div>
      {tab === 'file' && (
        <label className="flex flex-col items-center justify-center border-2 border-dashed rounded-lg p-6 cursor-pointer hover:bg-background">
          <Upload className="w-6 h-6 text-muted-foreground mb-1" />
          <span className="text-xs text-muted-foreground">Kolom: Tanggal · Keterangan · Debit/Kredit (atau Nominal ±) · Referensi. Debit/Keluar = uang keluar.</span>
          <input type="file" accept=".csv,text/csv" className="hidden" data-testid="recon-csv-input" onChange={e => uploadCsv(e.target.files?.[0])} />
          {busy && <Loader2 className="w-4 h-4 animate-spin mt-2" />}
        </label>
      )}
      {tab === 'paste' && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">Per baris: tanggal, keterangan, nominal, masuk/keluar, referensi</p>
          <textarea data-testid="recon-bulk-text" rows={4} className={inputCls + ' font-mono'} value={bulkText} onChange={e => setBulkText(e.target.value)}
            placeholder={'2026-09-01, Pencairan Shopee, 5000000, masuk, TRF001\n2026-09-03, Biaya admin, 6500, keluar'} />
          <Button size="sm" data-testid="recon-bulk-submit" onClick={importBulk} disabled={busy}>Impor</Button>
        </div>
      )}
      {tab === 'manual' && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 items-end">
          <input type="date" data-testid="recon-txn-date" className={inputCls} value={form.txn_date} onChange={e => setForm(f => ({ ...f, txn_date: e.target.value }))} />
          <input data-testid="recon-txn-desc" className={inputCls} placeholder="Keterangan" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          <input type="number" data-testid="recon-txn-amount" className={inputCls} placeholder="Nominal" value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))} />
          <select data-testid="recon-txn-direction" className={inputCls + ' bg-background'} value={form.direction} onChange={e => setForm(f => ({ ...f, direction: e.target.value }))}>
            <option value="in">Masuk (kredit rekening)</option>
            <option value="out">Keluar (debit rekening)</option>
          </select>
          <Button size="sm" data-testid="recon-txn-submit" onClick={addOne} disabled={busy || !form.txn_date || !form.amount}>Tambah</Button>
        </div>
      )}
    </div>
  );
}
