import { useState, useEffect } from 'react';
import { Hash, Search, ChevronDown, ChevronRight, X, Package } from 'lucide-react';
import { apiGet } from '../../../lib/api';

export default function VendorSerialTracking({ token, user }) {
  const [serialList, setSerialList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [expandedSN, setExpandedSN] = useState(null);
  const [traceData, setTraceData] = useState(null);

  const fetchSerials = async () => {
    setLoading(true);
    try {
      let url = `/serial-list?status=${filter}`;
      if (search) url += `&search=${encodeURIComponent(search)}`;
      setSerialList(await apiGet(url));
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchSerials(); }, [filter]);
  useEffect(() => { const t = setTimeout(fetchSerials, 400); return () => clearTimeout(t); }, [search]);

  const loadTrace = async (sn) => {
    if (expandedSN === sn) { setExpandedSN(null); setTraceData(null); return; }
    setExpandedSN(sn);
    try {
      setTraceData(await apiGet(`/serial-trace?serial=${encodeURIComponent(sn)}`));
    } catch (e) { console.error(e); }
  };

  const ongoingCount = serialList.filter(s => s.status === 'ongoing').length;
  const completedCount = serialList.filter(s => s.status === 'completed').length;

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-bold text-foreground">Serial Tracking</h2>

      <div className="grid grid-cols-3 gap-3">
        <button onClick={() => setFilter('ongoing')} className={`rounded-lg p-3 border text-center ${filter === 'ongoing' ? 'border-blue-300 bg-blue-50' : 'border-border bg-card'}`}>
          <p className="text-xl font-bold text-blue-700">{ongoingCount}</p>
          <p className="text-xs text-blue-600">Ongoing</p>
        </button>
        <button onClick={() => setFilter('completed')} className={`rounded-lg p-3 border text-center ${filter === 'completed' ? 'border-emerald-300 bg-emerald-50' : 'border-border bg-card'}`}>
          <p className="text-xl font-bold text-emerald-700">{completedCount}</p>
          <p className="text-xs text-emerald-600">Selesai</p>
        </button>
        <button onClick={() => setFilter('all')} className={`rounded-lg p-3 border text-center ${filter === 'all' ? 'border-border bg-muted/40' : 'border-border bg-card'}`}>
          <p className="text-xl font-bold text-foreground/90">{serialList.length}</p>
          <p className="text-xs text-muted-foreground">Semua</p>
        </button>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/70" />
        <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari serial number..." className="w-full pl-9 pr-4 py-2.5 border border-border rounded-lg text-sm" data-testid="vendor-serial-search" />
      </div>

      {loading ? (
        <div className="flex justify-center py-8"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div></div>
      ) : serialList.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground/70"><Hash className="w-10 h-10 mx-auto mb-2 opacity-30" /><p className="text-sm">Tidak ada serial number</p></div>
      ) : (
        <div className="space-y-2">
          {serialList.map((s, idx) => (
            <div key={`${s.serial_number}-${s.po_id}-${idx}`} className="bg-card rounded-lg border border-border overflow-hidden">
              <button onClick={() => loadTrace(s.serial_number)} className="w-full text-left p-3 flex items-center gap-3" data-testid={`vendor-serial-${idx}`}>
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${s.status === 'ongoing' ? 'bg-blue-500 animate-pulse' : s.status === 'completed' ? 'bg-emerald-500' : 'bg-amber-400'}`}></div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-foreground text-sm font-mono">{s.serial_number}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${s.status === 'ongoing' ? 'bg-blue-100 text-blue-700' : s.status === 'completed' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{s.status === 'ongoing' ? 'Ongoing' : s.status === 'completed' ? 'Selesai' : 'Menunggu'}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{s.product_name} · {s.sku} · {s.size}/{s.color}</p>
                </div>
                <div className="hidden md:flex items-center gap-4 text-center text-xs flex-shrink-0">
                  <div><p className="text-muted-foreground/70">Order</p><p className="font-bold text-foreground/90">{(s.ordered_qty || 0).toLocaleString('id-ID')}</p></div>
                  <div><p className="text-muted-foreground/70">Produksi</p><p className="font-bold text-blue-600">{(s.produced_qty || 0).toLocaleString('id-ID')}</p></div>
                  <div><p className="text-muted-foreground/70">Kirim</p><p className="font-bold text-purple-600">{(s.shipped_qty || 0).toLocaleString('id-ID')}</p></div>
                </div>
                {expandedSN === s.serial_number ? <ChevronDown className="w-4 h-4 text-muted-foreground/70" /> : <ChevronRight className="w-4 h-4 text-muted-foreground/70" />}
              </button>
              {expandedSN === s.serial_number && traceData && (
                <div className="border-t border-border/60 bg-muted/40 p-3">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
                    <div className="bg-card rounded p-2 text-center border border-border/60"><p className="text-xs text-muted-foreground/70">PO</p><p className="text-sm font-bold text-foreground/90">{s.po_number}</p></div>
                    <div className="bg-card rounded p-2 text-center border border-border/60"><p className="text-xs text-muted-foreground/70">Customer</p><p className="text-sm font-bold text-foreground/90 truncate">{s.customer_name || '-'}</p></div>
                    <div className="bg-card rounded p-2 text-center border border-border/60"><p className="text-xs text-muted-foreground/70">Status PO</p><p className="text-sm font-bold text-blue-600">{s.po_status}</p></div>
                    <div className="bg-card rounded p-2 text-center border border-border/60"><p className="text-xs text-muted-foreground/70">Sisa</p><p className="text-sm font-bold text-amber-600">{(s.remaining_qty || 0).toLocaleString('id-ID')} pcs</p></div>
                  </div>
                  {(traceData.timeline || []).length > 0 && (
                    <div className="space-y-1 max-h-40 overflow-y-auto">
                      {traceData.timeline.slice(0, 10).map((ev, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <div className="w-1.5 h-1.5 rounded-full bg-purple-400 flex-shrink-0"></div>
                          <span className="font-medium text-foreground/90">{ev.step}</span>
                          {ev.qty > 0 && <span className="bg-muted px-1 rounded">Qty: {ev.qty}</span>}
                          <span className="text-muted-foreground/70 ml-auto">{ev.date ? new Date(ev.date).toLocaleDateString('id-ID', { day: 'numeric', month: 'short' }) : '-'}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── VENDOR REMINDER INBOX ───────────────────────────────────────────────────


