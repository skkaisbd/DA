/**
 * MaterialDefectReportsModule — Admin view laporan defect material (FASE 5)
 * Engine SOMMERVILLE: /api/material-defect-reports (list + resolve).
 */
import { useState, useEffect, useCallback } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { apiGet } from '../../../lib/api';
import StatusBadge from './StatusBadge';

export default function MaterialDefectReportsModule({ hasPerm = () => false }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [filter, setFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const data = await apiGet('/material-defect-reports');
      setRows(Array.isArray(data) ? data : (data?.items || []));
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const shown = rows.filter(r => !filter || (r.status || '') === filter);

  return (
    <div data-testid="defect-reports-module" className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500" /> Laporan Defect Material
          </h2>
          <p className="text-xs text-muted-foreground">Laporan defect/kekurangan material dari vendor CMT & produksi internal</p>
        </div>
        <div className="flex items-center gap-2">
          <select data-testid="defect-filter-status" className="border border-border rounded-lg px-2 py-1.5 text-sm" value={filter} onChange={e => setFilter(e.target.value)}>
            <option value="">Semua Status</option>
            <option value="open">Open</option>
            <option value="resolved">Resolved</option>
          </select>
          <button onClick={load} className="p-2 rounded-lg border border-border hover:bg-muted/60" title="Refresh">
            <RefreshCw className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
      </div>

      {err && <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{err}</div>}

      <div className="bg-card rounded-xl border border-border overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground border-b border-border bg-muted/40">
              <th className="px-3 py-2">Tanggal</th>
              <th className="px-3 py-2">No. Laporan</th>
              <th className="px-3 py-2">PO / Shipment</th>
              <th className="px-3 py-2">Vendor</th>
              <th className="px-3 py-2">Material</th>
              <th className="px-3 py-2">Qty Defect</th>
              <th className="px-3 py-2">Keterangan</th>
              <th className="px-3 py-2">Status</th>
              
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={8} className="px-3 py-6 text-center text-muted-foreground">Memuat…</td></tr>}
            {!loading && shown.length === 0 && <tr><td colSpan={8} className="px-3 py-6 text-center text-muted-foreground italic">Tidak ada laporan defect.</td></tr>}
            {shown.map(r => (
              <tr key={r.id} data-testid={`defect-row-${r.id}`} className="border-b border-border/60 hover:bg-muted/40">
                <td className="px-3 py-2 text-xs">{(r.created_at || '').slice(0, 10)}</td>
                <td className="px-3 py-2 font-mono text-xs">{r.report_number || r.id?.slice(0, 8)}</td>
                <td className="px-3 py-2 text-xs">{r.po_number || r.shipment_number || '—'}</td>
                <td className="px-3 py-2 text-xs">{r.vendor_name || '—'}</td>
                <td className="px-3 py-2 text-xs">{r.material_name || r.item_name || '—'}</td>
                <td className="px-3 py-2 font-semibold">{r.qty_defect ?? r.qty ?? '—'}</td>
                <td className="px-3 py-2 text-xs max-w-[240px] truncate" title={r.description || r.notes}>{r.description || r.notes || '—'}</td>
                <td className="px-3 py-2"><StatusBadge status={r.status || 'open'} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
