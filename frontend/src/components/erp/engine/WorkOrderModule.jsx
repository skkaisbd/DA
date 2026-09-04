
import { useState, useEffect, useMemo, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import {
  RefreshCw, ChevronDown, ChevronRight, Factory, Package,
  AlertTriangle, CheckCircle, TrendingUp, BarChart2, Search,
  X, Layers, Hash, Tag, Filter
} from 'lucide-react';
import { apiGet } from '../../../lib/api';
import { BizBadge } from './BusinessTypeBadge';

// ─── Helpers ─────────────────────────────────────────────────────────────────────
const n = v => (Number(v) || 0).toLocaleString('id-ID');

function getStatus(produced, ordered) {
  if (!ordered || ordered === 0) return 'no-data';
  if (produced === 0) return 'not-started';
  if (produced >= ordered) return 'completed';
  return 'ongoing';
}

const STATUS_CONFIG = {
  'not-started': { label: 'Belum Mulai',  bg: 'bg-muted',   text: 'text-muted-foreground',   bar: 'bg-muted-foreground/30',   dot: 'bg-muted-foreground/50'   },
  'ongoing':     { label: 'Sedang Jalan', bg: 'bg-amber-50',    text: 'text-amber-700',   bar: 'bg-amber-500',   dot: 'bg-amber-500'   },
  'completed':   { label: 'Selesai',      bg: 'bg-emerald-50',  text: 'text-emerald-700', bar: 'bg-emerald-500', dot: 'bg-emerald-500' },
  'no-data':     { label: '-',            bg: 'bg-muted/40',    text: 'text-muted-foreground',   bar: 'bg-muted',   dot: 'bg-muted-foreground/30'   },
};

function StatusBadge({ produced, ordered }) {
  const s = getStatus(produced, ordered);
  const c = STATUS_CONFIG[s];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${c.bg} ${c.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  );
}

function ProgressBar({ produced, ordered, compact = false }) {
  const pct = ordered > 0 ? Math.min(100, Math.round((produced / ordered) * 100)) : 0;
  const s = getStatus(produced, ordered);
  const bar = STATUS_CONFIG[s].bar;
  if (compact) {
    return (
      <div className="flex items-center gap-1.5 min-w-0">
        <div className="flex-1 bg-muted rounded-full h-1.5 overflow-hidden min-w-[40px]">
          <div className={`h-1.5 rounded-full transition-all ${bar}`} style={{ width: `${pct}%` }} />
        </div>
        <span className="text-xs font-bold text-muted-foreground w-8 text-right flex-shrink-0">{pct}%</span>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{n(produced)} / {n(ordered)} pcs</span>
        <span className="font-bold text-foreground/90">{pct}%</span>
      </div>
      <div className="bg-muted rounded-full h-2 overflow-hidden">
        <div className={`h-2 rounded-full transition-all duration-500 ${bar}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function MetricBadge({ label, value, color = 'slate', highlight = false }) {
  const colors = {
    slate:   'bg-muted/40 border-border text-foreground/90',
    blue:    'bg-blue-50 border-blue-200 text-blue-700',
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-700',
    amber:   'bg-amber-50 border-amber-200 text-amber-700',
    red:     'bg-red-50 border-red-200 text-red-700',
  };
  return (
    <div className={`rounded-lg px-2.5 py-1.5 border text-center ${colors[color]} ${highlight ? 'ring-2 ring-offset-1 ring-current' : ''}`}>
      <div className="text-[10px] font-medium opacity-75 leading-tight">{label}</div>
      <div className="text-sm font-bold leading-tight mt-0.5">{n(value)}</div>
    </div>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────────
export default function WorkOrderModule({ token, userRole, portalId }) {
  // FASE IA-1 — pemisahan data per proses bisnis: Portal Produksi = internal,
  // Portal Maklon = maklon. Sebelum ini modul menarik SEMUA PO sehingga Portal
  // Produksi ikut menampilkan PO Maklon.
  const businessType = portalId === 'maklon' ? 'maklon' : portalId === 'production' ? 'internal' : null;
  const [data, setData] = useState({ hierarchy: [], flat: [], invalid_records: [] });
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({ vendors: {}, pos: {}, serials: {} });
  const [filterVendor, setFilterVendor] = useState('');
  const [vendors, setVendors] = useState([]);

  // Search state
  const [searchText, setSearchText] = useState('');
  const [searchField, setSearchField] = useState('all'); // all | po | vendor | serial | sku
  const [showFilterPanel, setShowFilterPanel] = useState(false);
  const [filterStatus, setFilterStatus] = useState('all'); // all | not-started | ongoing | completed

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const btq = businessType ? `?business_type=${businessType}` : '';
      const [dData, vData] = await Promise.all([
        apiGet(`/distribusi-kerja${btq}`),
        apiGet('/garments'),
      ]);
      setData(dData && dData.hierarchy ? dData : { hierarchy: [], flat: Array.isArray(dData) ? dData : [], invalid_records: dData?.invalid_records || [] });
      setVendors(Array.isArray(vData) ? vData.filter(v => v.status === 'active') : []);
    } catch (e) {
      console.error(e);
      setData({ hierarchy: [], flat: [] });
    } finally {
      setLoading(false);
    }
  }, [businessType]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const toggle = (level, key) => {
    setExpanded(prev => ({ ...prev, [level]: { ...prev[level], [key]: !prev[level][key] } }));
  };

  const expandAll = () => {
    const vendors = {}; const pos = {}; const serials = {};
    (data.hierarchy || []).forEach(v => {
      vendors[v.vendor_id] = true;
      (v.pos || []).forEach(p => {
        const pk = `${v.vendor_id}-${p.po_id}`;
        pos[pk] = true;
        (p.serials || []).forEach(s => { serials[`${pk}-${s.serial_number || '_'}`] = true; });
      });
    });
    setExpanded({ vendors, pos, serials });
  };

  const collapseAll = () => setExpanded({ vendors: {}, pos: {}, serials: {} });

  // ── Search & Filter Logic ────────────────────────────────────────────────────
  const filteredHierarchy = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    let hierarchy = data.hierarchy || [];

    // Filter by vendor dropdown
    if (filterVendor) hierarchy = hierarchy.filter(v => v.vendor_id === filterVendor);

    if (!q && filterStatus === 'all') return hierarchy;

    // Deep filter: keep only vendors/POs/serials/skus that match
    return hierarchy.map(vendor => {
      const vendorMatch = (searchField === 'all' || searchField === 'vendor')
        && vendor.vendor_name?.toLowerCase().includes(q);

      const filteredPos = (vendor.pos || []).map(po => {
        const poMatch = (searchField === 'all' || searchField === 'po')
          && po.po_number?.toLowerCase().includes(q);

        const filteredSerials = (po.serials || []).map(serial => {
          const snMatch = (searchField === 'all' || searchField === 'serial')
            && serial.serial_number?.toLowerCase().includes(q);

          const filteredSkus = (serial.skus || []).filter(sku => {
            const skuMatch = (searchField === 'all' || searchField === 'sku')
              && (sku.sku?.toLowerCase().includes(q) || sku.product_name?.toLowerCase().includes(q));
            const matchQ = !q || vendorMatch || poMatch || snMatch || skuMatch;
            const matchStatus = filterStatus === 'all' || getStatus(sku.produced_qty, sku.ordered_qty) === filterStatus;
            return matchQ && matchStatus;
          });
          if (!filteredSkus.length && !(!q)) return null;
          return { ...serial, skus: filteredSkus };
        }).filter(Boolean);

        if (!filteredSerials.length && !(!q)) return null;
        return { ...po, serials: filteredSerials };
      }).filter(Boolean);

      if (!filteredPos.length && !(!q)) return null;
      return { ...vendor, pos: filteredPos };
    }).filter(Boolean);
  }, [data.hierarchy, filterVendor, searchText, searchField, filterStatus]);

  // Auto-expand when searching
  useEffect(() => {
    if (searchText) {
      const v = {}; const p = {}; const s = {};
      filteredHierarchy.forEach(vendor => {
        v[vendor.vendor_id] = true;
        (vendor.pos || []).forEach(po => {
          const pk = `${vendor.vendor_id}-${po.po_id}`;
          p[pk] = true;
          (po.serials || []).forEach(sn => { s[`${pk}-${sn.serial_number || '_'}`] = true; });
        });
      });
      setExpanded({ vendors: v, pos: p, serials: s });
    }
  }, [searchText, filteredHierarchy]);

  // ── Global Summary ────────────────────────────────────────────────────────────
  const totalOrdered  = filteredHierarchy.reduce((s, v) => s + (v.total_ordered || 0), 0);
  const totalReceived = filteredHierarchy.reduce((s, v) => s + (v.total_received || 0), 0);
  const totalProduced = filteredHierarchy.reduce((s, v) => s + (v.total_produced || 0), 0);
  const totalShipped  = filteredHierarchy.reduce((s, v) => s + (v.total_shipped_to_buyer || 0), 0);
  const totalMissing  = filteredHierarchy.reduce((s, v) => s + (v.total_missing || 0), 0);
  const globalPct     = totalOrdered > 0 ? Math.round((totalProduced / totalOrdered) * 100) : 0;

  // ── Flat SKU stats ─────────────────────────────────────────────────────────
  const allSkus = (data.flat || []);
  const statNotStarted = allSkus.filter(s => getStatus(s.produced_qty, s.ordered_qty) === 'not-started').length;
  const statOngoing    = allSkus.filter(s => getStatus(s.produced_qty, s.ordered_qty) === 'ongoing').length;
  const statCompleted  = allSkus.filter(s => getStatus(s.produced_qty, s.ordered_qty) === 'completed').length;

  if (loading) return (
    <div className="flex items-center justify-center py-20">
      <div className="text-center">
        <RefreshCw className="w-8 h-8 text-blue-500 animate-spin mx-auto mb-3" />
        <p className="text-muted-foreground text-sm">Memuat data distribusi kerja...</p>
      </div>
    </div>
  );

  return (
    <div className="space-y-5">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Factory className="w-6 h-6 text-indigo-600" /> Production Jobs
            {businessType && <BizBadge type={businessType} />}
          </h1>
          <p className="text-muted-foreground text-sm mt-0.5">
            Hierarki produksi: Vendor → PO → Serial Number → SKU
            {businessType && (
              <span className="ml-1 font-medium text-foreground/80">
                — data <strong>{businessType === 'maklon' ? 'Produksi Maklon (CMT)' : 'Produksi Internal'}</strong> saja.
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={expandAll} className="text-xs text-blue-600 hover:underline px-2 py-1">Expand Semua</button>
          <button onClick={collapseAll} className="text-xs text-muted-foreground hover:underline px-2 py-1">Collapse</button>
          <button onClick={fetchData} className="flex items-center gap-1.5 px-3 py-2 border border-border rounded-lg text-sm hover:bg-muted/60 text-muted-foreground">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>
      </div>

      {/* ── Global Progress Banner ───────────────────────────────────────────── */}
      <div className="bg-gradient-to-r from-indigo-600 to-blue-600 rounded-2xl p-4 text-white">
        <div className="flex items-center justify-between mb-2">
          <span className="font-semibold text-sm opacity-90">Progress Global Produksi</span>
          <span className="text-2xl font-extrabold">{globalPct}%</span>
        </div>
        <div className="bg-card/20 rounded-full h-2.5 overflow-hidden">
          <div className="bg-card h-2.5 rounded-full transition-all duration-700" style={{ width: `${globalPct}%` }} />
        </div>
        <div className="flex items-center gap-4 mt-2 text-xs opacity-80">
          <span>{n(totalProduced)} diproduksi dari {n(totalOrdered)} dipesan</span>
          <span>·</span>
          <span>{n(totalShipped)} dikirim ke buyer</span>
        </div>
      </div>

      {/* ── Summary Cards ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MetricBadge label="Total Dipesan"   value={totalOrdered}  color="slate" />
        <MetricBadge label="Total Diterima"  value={totalReceived} color="blue" />
        <MetricBadge label="Total Diproduksi" value={totalProduced} color="emerald" />
        <MetricBadge label="Dikirim ke Buyer" value={totalShipped} color="emerald" />
        <MetricBadge label="Total Missing"   value={totalMissing}  color={totalMissing > 0 ? 'amber' : 'slate'} />
      </div>

      {/* ── Status Quick Stats (per baris SKU, dipakai sebagai filter) ────── */}
      <div className="text-[11px] text-muted-foreground -mb-2" data-testid="wo-status-stats-caption">
        Status per baris SKU ({allSkus.length} SKU) — klik untuk memfilter
      </div>
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'SKU Belum Mulai', value: statNotStarted, color: 'bg-muted text-foreground/90', key: 'not-started', dot: 'bg-muted-foreground/50' },
          { label: 'SKU Sedang Jalan', value: statOngoing, color: 'bg-amber-50 text-amber-700', key: 'ongoing', dot: 'bg-amber-500' },
          { label: 'SKU Selesai', value: statCompleted, color: 'bg-emerald-50 text-emerald-700', key: 'completed', dot: 'bg-emerald-500' },
        ].map(s => (
          <button key={s.key}
            onClick={() => setFilterStatus(prev => prev === s.key ? 'all' : s.key)}
            className={`flex items-center gap-3 rounded-xl p-3 border-2 transition-all ${s.color} ${filterStatus === s.key ? 'border-current shadow-sm' : 'border-transparent'}`}>
            <span className={`w-3 h-3 rounded-full flex-shrink-0 ${s.dot}`} />
            <div className="text-left">
              <div className="text-xs font-medium">{s.label}</div>
              <div className="text-xl font-extrabold leading-tight">{s.value}</div>
            </div>
          </button>
        ))}
      </div>

      {/* ── Search & Filter Bar ──────────────────────────────────────────────── */}
      <div className="bg-card border border-border rounded-xl p-3 shadow-sm">
        <div className="flex gap-2 flex-wrap">
          {/* Search input */}
          <div className="flex-1 min-w-[200px] relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/70 pointer-events-none" />
            <input
              type="text"
              placeholder={`Cari ${searchField === 'all' ? 'PO, vendor, serial, atau SKU' : searchField === 'po' ? 'nomor PO' : searchField === 'vendor' ? 'nama vendor' : searchField === 'serial' ? 'serial number' : 'kode SKU'}...`}
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              className="w-full pl-9 pr-9 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
            />
            {searchText && (
              <button onClick={() => setSearchText('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground/70 hover:text-muted-foreground">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Search field selector */}
          <div className="flex items-center gap-1 bg-muted/40 rounded-lg p-1 flex-shrink-0">
            {[
              { key: 'all', label: 'Semua', icon: Layers },
              { key: 'po', label: 'PO', icon: BarChart2 },
              { key: 'vendor', label: 'Vendor', icon: Factory },
              { key: 'serial', label: 'Serial', icon: Hash },
              { key: 'sku', label: 'SKU', icon: Tag },
            ].map(f => {
              const Icon = f.icon;
              return (
                <button
                  key={f.key}
                  onClick={() => setSearchField(f.key)}
                  className={`flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all ${
                    searchField === f.key ? 'bg-card shadow text-indigo-700' : 'text-muted-foreground hover:text-foreground/90'
                  }`}
                >
                  <Icon className="w-3 h-3" />
                  {f.label}
                </button>
              );
            })}
          </div>

          {/* Vendor filter */}
          <SmartNativeSelect
            value={filterVendor}
            onChange={e => setFilterVendor(e.target.value)}
            className="border border-border rounded-lg px-3 py-2 text-sm bg-card text-foreground/90 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          >
            <option value="">Semua Vendor</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.garment_name}</option>)}
          </SmartNativeSelect>

          {/* Active filters */}
          {(searchText || filterVendor || filterStatus !== 'all') && (
            <button
              onClick={() => { setSearchText(''); setFilterVendor(''); setFilterStatus('all'); }}
              className="flex items-center gap-1 px-3 py-2 text-xs text-red-600 bg-red-50 rounded-lg hover:bg-red-100 font-medium"
            >
              <X className="w-3 h-3" /> Reset Filter
            </button>
          )}
        </div>
        {/* Result count */}
        {(searchText || filterStatus !== 'all') && (
          <p className="text-xs text-muted-foreground/70 mt-2">
            Menampilkan {filteredHierarchy.length} vendor, {filteredHierarchy.reduce((s, v) => s + (v.pos?.length || 0), 0)} PO
          </p>
        )}
      </div>

      {/* ── Hierarchical Tree ────────────────────────────────────────────────── */}
      {filteredHierarchy.length === 0 ? (
        <div className="text-center py-16 bg-card rounded-2xl border border-border">
          {searchText || filterStatus !== 'all' ? (
            <>
              <Search className="w-12 h-12 mx-auto mb-3 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">Tidak ada data yang cocok dengan pencarian.</p>
              <button onClick={() => { setSearchText(''); setFilterStatus('all'); }} className="text-xs text-blue-600 hover:underline mt-2">Reset pencarian</button>
            </>
          ) : (
            <>
              <Factory className="w-12 h-12 mx-auto mb-3 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">Belum ada data distribusi kerja.</p>
              <p className="text-xs text-muted-foreground/70 mt-1">Data muncul setelah vendor shipment dibuat dan diterima vendor.</p>
            </>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filteredHierarchy.map(vendor => {
            const vendorExpanded = expanded.vendors[vendor.vendor_id];
            const vStatus = getStatus(vendor.total_produced, vendor.total_ordered);
            const vConfig = STATUS_CONFIG[vStatus];

            return (
              <div key={vendor.vendor_id} className="border border-border rounded-2xl overflow-hidden shadow-sm bg-card">

                {/* ── LEVEL 1: Vendor ─────────────────────────────────────── */}
                <div
                  className="flex items-center gap-3 px-4 py-3.5 bg-gradient-to-r from-indigo-50 via-blue-50 to-muted/40 cursor-pointer hover:from-indigo-100 transition-colors select-none"
                  onClick={() => toggle('vendors', vendor.vendor_id)}
                >
                  <div className="flex-shrink-0 w-5">
                    {vendorExpanded
                      ? <ChevronDown className="w-4 h-4 text-indigo-600" />
                      : <ChevronRight className="w-4 h-4 text-indigo-600" />}
                  </div>
                  <div className="w-9 h-9 bg-indigo-600 rounded-xl flex items-center justify-center flex-shrink-0 shadow-sm">
                    <Factory className="w-4.5 h-4.5 text-white" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-bold text-foreground text-sm">{vendor.vendor_name}</p>
                      <StatusBadge produced={vendor.total_produced} ordered={vendor.total_ordered} />
                      <span className="text-xs text-muted-foreground/70">{vendor.pos?.length || 0} PO</span>
                    </div>
                    <div className="mt-1 w-48 hidden md:block">
                      <ProgressBar produced={vendor.total_produced} ordered={vendor.total_ordered} compact />
                    </div>
                  </div>
                  <div className="hidden md:flex items-center gap-2 flex-shrink-0">
                    <MetricBadge label="Dipesan" value={vendor.total_ordered} color="slate" />
                    <MetricBadge label="Diproduksi" value={vendor.total_produced} color="emerald" />
                    <MetricBadge label="Dikirim" value={vendor.total_shipped} color="emerald" />
                    {vendor.total_missing > 0 && <MetricBadge label="Missing" value={vendor.total_missing} color="amber" />}
                  </div>
                </div>

                {/* ── LEVEL 2: POs ─────────────────────────────────────────── */}
                {vendorExpanded && (
                  <div className="border-t border-border">
                    {(vendor.pos || []).map(po => {
                      const poKey = `${vendor.vendor_id}-${po.po_id}`;
                      const poExpanded = expanded.pos[poKey];
                      const poStatus = getStatus(po.total_produced, po.total_ordered);
                      const isOverdue = po.deadline && new Date(po.deadline) < new Date() && poStatus !== 'completed';

                      return (
                        <div key={po.po_id} className="border-b border-border/60 last:border-0">
                          <div
                            className="flex items-center gap-3 px-5 py-3 bg-card hover:bg-muted/60/80 cursor-pointer transition-colors select-none"
                            onClick={() => toggle('pos', poKey)}
                          >
                            <div className="flex-shrink-0 w-4 ml-3">
                              {poExpanded
                                ? <ChevronDown className="w-3.5 h-3.5 text-blue-400" />
                                : <ChevronRight className="w-3.5 h-3.5 text-blue-400" />}
                            </div>
                            <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                              <BarChart2 className="w-4 h-4 text-blue-600" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-semibold text-sm text-blue-700">{po.po_number}</span>
                                <StatusBadge produced={po.total_produced} ordered={po.total_ordered} />
                                {po.po_date && (
                                  <span className="text-xs text-muted-foreground/70">{new Date(po.po_date).toLocaleDateString('id-ID')}</span>
                                )}
                                {isOverdue && (
                                  <span className="flex items-center gap-1 text-xs text-red-600 font-medium">
                                    <AlertTriangle className="w-3 h-3" /> Terlambat
                                  </span>
                                )}
                                <span className="text-xs text-muted-foreground/70">{po.customer_name}</span>
                              </div>
                              <div className="mt-1 w-40 hidden md:block">
                                <ProgressBar produced={po.total_produced} ordered={po.total_ordered} compact />
                              </div>
                            </div>
                            <div className="hidden md:flex items-center gap-2 flex-shrink-0 text-xs">
                              <div className="text-right text-muted-foreground/70">
                                <div>{po.serials?.length || 0} serial</div>
                                {po.deadline && <div className={isOverdue ? 'text-red-600 font-medium' : ''}>{new Date(po.deadline).toLocaleDateString('id-ID', { day:'2-digit', month:'short' })}</div>}
                              </div>
                              <MetricBadge label="Dipesan" value={po.total_ordered} color="slate" />
                              <MetricBadge label="Diproduksi" value={po.total_produced} color="emerald" />
                              <MetricBadge label="Dikirim" value={po.total_shipped} color="emerald" />
                            </div>
                          </div>

                          {/* ── LEVEL 3: Serial Numbers ──────────────────── */}
                          {poExpanded && (
                            <div className="bg-muted/40/60 border-t border-border/60">
                              {(po.serials || []).map(serial => {
                                const snKey = `${poKey}-${serial.serial_number || '_'}`;
                                const snExpanded = expanded.serials[snKey];
                                const sn = serial.serial_number || '(No Serial)';
                                const snStatus = getStatus(serial.total_produced, serial.total_ordered);

                                return (
                                  <div key={snKey} className="border-b border-border/60/80 last:border-0">
                                    <div
                                      className="flex items-center gap-3 pl-14 pr-4 py-2.5 hover:bg-amber-50/40 cursor-pointer transition-colors select-none"
                                      onClick={() => toggle('serials', snKey)}
                                    >
                                      <div className="flex-shrink-0 w-4">
                                        {snExpanded
                                          ? <ChevronDown className="w-3 h-3 text-amber-500" />
                                          : <ChevronRight className="w-3 h-3 text-amber-500" />}
                                      </div>
                                      <div className="w-7 h-7 bg-amber-100 border border-amber-200 rounded-lg flex items-center justify-center flex-shrink-0">
                                        <span className="text-[9px] font-extrabold text-amber-700">SN</span>
                                      </div>
                                      <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                          <span className="font-semibold text-sm text-amber-800 font-mono">{sn}</span>
                                          <StatusBadge produced={serial.total_produced} ordered={serial.total_ordered} />
                                          <span className="text-xs text-muted-foreground/70">{serial.skus?.length || 0} SKU</span>
                                        </div>
                                      </div>
                                      <div className="hidden md:flex items-center gap-2 flex-shrink-0">
                                        <div className="w-32">
                                          <ProgressBar produced={serial.total_produced} ordered={serial.total_ordered} compact />
                                        </div>
                                        <MetricBadge label="Dipesan" value={serial.total_ordered} color="slate" />
                                        <MetricBadge label="Diproduksi" value={serial.total_produced} color="emerald" />
                                      </div>
                                    </div>

                                    {/* ── LEVEL 4: SKU Items ─────────────── */}
                                    {snExpanded && (
                                      <div className="bg-card border-t border-border/60">
                                        <div className="pl-20 pr-4 pb-3 pt-1 overflow-x-auto">
                                          <table className="w-full text-xs min-w-[700px]">
                                            <thead>
                                              <tr className="border-b-2 border-border">
                                                <th className="text-left py-2 pr-3 text-muted-foreground font-semibold">SKU / Produk</th>
                                                <th className="text-right py-2 px-2 text-muted-foreground font-semibold whitespace-nowrap">
                                                  <span title="Qty yang dipesan dalam PO">Dipesan</span>
                                                </th>
                                                <th className="text-right py-2 px-2 text-blue-500 font-semibold whitespace-nowrap">
                                                  <span title="Qty yang diterima dari kiriman ERP">Diterima</span>
                                                </th>
                                                <th className="text-right py-2 px-2 text-amber-500 font-semibold whitespace-nowrap">Missing</th>
                                                <th className="text-right py-2 px-2 text-red-500 font-semibold whitespace-nowrap">Cacat</th>
                                                <th className="text-right py-2 px-2 text-emerald-600 font-semibold whitespace-nowrap">
                                                  <span title="Total sudah diproduksi (parent + child jobs)">Diproduksi</span>
                                                </th>
                                                <th className="text-right py-2 px-2 text-muted-foreground font-semibold whitespace-nowrap">Sisa Prod.</th>
                                                <th className="text-right py-2 px-2 text-teal-600 font-semibold whitespace-nowrap">Dikirim</th>
                                                <th className="py-2 px-2 text-muted-foreground font-semibold whitespace-nowrap w-32">Status / Progress</th>
                                              </tr>
                                            </thead>
                                            <tbody className="divide-y divide-border/40">
                                              {(serial.skus || []).map(sku => {
                                                const skuStatus = getStatus(sku.produced_qty, sku.ordered_qty);
                                                const cfg = STATUS_CONFIG[skuStatus];
                                                return (
                                                  <tr key={sku.id} className={`hover:bg-muted/60 transition-colors ${cfg.bg}`}>
                                                    <td className="py-2 pr-3">
                                                      <div className="flex flex-col gap-0.5">
                                                        <span className="font-bold text-foreground font-mono">{sku.sku || sku.product_name}</span>
                                                        {sku.sku && sku.product_name && sku.sku !== sku.product_name && (
                                                          <span className="text-muted-foreground/70 leading-tight">{sku.product_name}</span>
                                                        )}
                                                        {(sku.size || sku.color) && (
                                                          <span className="text-muted-foreground/70 leading-tight">{[sku.size, sku.color].filter(Boolean).join(' / ')}</span>
                                                        )}
                                                        {sku.shipment_type && sku.shipment_type !== 'NORMAL' && (
                                                          <span className={`inline-block w-fit px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                                            sku.shipment_type === 'ADDITIONAL' ? 'bg-orange-100 text-orange-700' : 'bg-purple-100 text-purple-700'
                                                          }`}>
                                                            {sku.shipment_type}
                                                          </span>
                                                        )}
                                                        {sku.inspection_status && (
                                                          <span className={`inline-block w-fit px-1.5 py-0.5 rounded text-[10px] font-medium ${
                                                            sku.inspection_status === 'Inspected' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
                                                          }`}>
                                                            {sku.inspection_status === 'Inspected' ? '✓ Inspected' : '⏳ Pending'}
                                                          </span>
                                                        )}
                                                      </div>
                                                    </td>
                                                    {/* Ordered */}
                                                    <td className="py-2 px-2 text-right">
                                                      <span className="font-semibold text-foreground/90 text-sm">{n(sku.ordered_qty)}</span>
                                                    </td>
                                                    {/* Received */}
                                                    <td className="py-2 px-2 text-right">
                                                      <span className="font-medium text-blue-700">{n(sku.received_qty)}</span>
                                                    </td>
                                                    {/* Missing */}
                                                    <td className="py-2 px-2 text-right">
                                                      <span className={`font-medium ${(sku.missing_qty || 0) > 0 ? 'text-amber-600 font-bold' : 'text-muted-foreground/50'}`}>
                                                        {n(sku.missing_qty)}
                                                        {(sku.missing_qty || 0) > 0 && <AlertTriangle className="inline w-3 h-3 ml-0.5" />}
                                                      </span>
                                                    </td>
                                                    {/* Defect */}
                                                    <td className="py-2 px-2 text-right">
                                                      <span className={`font-medium ${(sku.defect_qty || 0) > 0 ? 'text-red-600 font-bold' : 'text-muted-foreground/50'}`}>
                                                        {n(sku.defect_qty)}
                                                      </span>
                                                    </td>
                                                    {/* Produced */}
                                                    <td className="py-2 px-2 text-right">
                                                      <span className="font-bold text-emerald-700 text-sm">{n(sku.produced_qty)}</span>
                                                    </td>
                                                    {/* Remaining Production */}
                                                    <td className="py-2 px-2 text-right">
                                                      <span className={`font-medium ${(sku.remaining_production || 0) > 0 ? 'text-orange-600' : 'text-muted-foreground/50'}`}>
                                                        {n(sku.remaining_production)}
                                                      </span>
                                                    </td>
                                                    {/* Shipped */}
                                                    <td className="py-2 px-2 text-right">
                                                      <span className="font-medium text-teal-700">{n(sku.shipped_to_buyer)}</span>
                                                    </td>
                                                    {/* Status + Progress */}
                                                    <td className="py-2 px-2 w-32">
                                                      <div className="space-y-1">
                                                        <StatusBadge produced={sku.produced_qty} ordered={sku.ordered_qty} />
                                                        <ProgressBar produced={sku.produced_qty} ordered={sku.ordered_qty} compact />
                                                      </div>
                                                    </td>
                                                  </tr>
                                                );
                                              })}
                                            </tbody>
                                            {/* Row totals */}
                                            {(serial.skus || []).length > 1 && (
                                              <tfoot>
                                                <tr className="border-t-2 border-border bg-muted/40/80">
                                                  <td className="py-2 pr-3 font-bold text-muted-foreground">Sub-total Serial</td>
                                                  <td className="py-2 px-2 text-right font-bold text-foreground/90">{n(serial.total_ordered)}</td>
                                                  <td className="py-2 px-2 text-right font-bold text-blue-700">{n(serial.total_received)}</td>
                                                  <td colSpan={2} className="py-2 px-2 text-center text-muted-foreground/70">—</td>
                                                  <td className="py-2 px-2 text-right font-bold text-emerald-700">{n(serial.total_produced)}</td>
                                                  <td className="py-2 px-2 text-right font-bold text-orange-600">{n(Math.max(0, serial.total_ordered - serial.total_produced))}</td>
                                                  <td className="py-2 px-2 text-right font-bold text-teal-700">{n(serial.total_shipped)}</td>
                                                  <td className="py-2 px-2">
                                                    <ProgressBar produced={serial.total_produced} ordered={serial.total_ordered} compact />
                                                  </td>
                                                </tr>
                                              </tfoot>
                                            )}
                                          </table>
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── Invalid Records ──────────────────────────────────────────────────── */}
      {(data.invalid_records || []).length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mt-4">
          <p className="font-semibold text-red-700 text-sm flex items-center gap-2 mb-2">
            <AlertTriangle className="w-4 h-4" />
            Record Tidak Valid ({data.invalid_records.length}) — Tidak dapat di-mapping ke PO
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-red-100">
                <tr>
                  <th className="text-left px-3 py-1.5 text-red-700">Shipment</th>
                  <th className="text-left px-3 py-1.5 text-red-700">Tipe</th>
                  <th className="text-left px-3 py-1.5 text-red-700">Vendor</th>
                  <th className="text-left px-3 py-1.5 text-red-700">SKU</th>
                  <th className="text-left px-3 py-1.5 text-red-700">Produk</th>
                  <th className="text-left px-3 py-1.5 text-red-700">Error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-red-100">
                {data.invalid_records.map((r, i) => (
                  <tr key={i} className="hover:bg-red-100/50">
                    <td className="px-3 py-1.5 font-mono">{r.shipment_number || '-'}</td>
                    <td className="px-3 py-1.5">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        r.shipment_type === 'ADDITIONAL' ? 'bg-orange-100 text-orange-700' : 'bg-purple-100 text-purple-700'
                      }`}>{r.shipment_type}</span>
                    </td>
                    <td className="px-3 py-1.5">{r.vendor_name || '-'}</td>
                    <td className="px-3 py-1.5 font-mono">{r.sku || '-'}</td>
                    <td className="px-3 py-1.5">{r.product_name || '-'}</td>
                    <td className="px-3 py-1.5 text-red-600">{r.error}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
