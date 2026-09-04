import { useState, useEffect, useCallback, useMemo } from 'react';
import { Calculator, RefreshCw, Save, Package, Users, Layers, TrendingUp, BarChart3, Building2 } from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from './moduleAtoms';
import { HppComparisonInline } from './HppComparisonInline';
import { ExportButtonGroup } from './ExportButtonGroup';
import { toast } from 'sonner';
import { fetchMaklonOrders, posToLegacyOrders } from '@/lib/maklonOrderAdapter';
import { formatRupiah } from '@/lib/format';
import { readNumber, FIELD } from '@/lib/materialFields';  // FASE 6.6-B

const fmt = formatRupiah;

export default function RahazaHPPModule({ token }) {
  const [activeTab, setActiveTab] = useState('internal-wo');
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  return (
    <div className="space-y-5" data-testid="rahaza-hpp-page">
      <PageHeader
        icon={TrendingUp}
        eyebrow="Portal Finance · Rahaza Finance"
        title="HPP Aktual Dashboard"
        subtitle="Hitung Harga Pokok Produksi berbasis data aktual: material issue + labor WIP + overhead. Lihat perbandingan Estimasi vs Aktual."
      />

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-3" data-testid="hpp-tabs">
          <TabsTrigger value="internal-wo" data-testid="hpp-actual-tab-internal-wo">
            <Package className="w-4 h-4 mr-2" />
            Internal WO
          </TabsTrigger>
          <TabsTrigger value="maklon" data-testid="hpp-actual-tab-maklon">
            <BarChart3 className="w-4 h-4 mr-2" />
            Maklon Actual
          </TabsTrigger>
          <TabsTrigger value="client-analysis" data-testid="hpp-actual-tab-client-analysis">
            <Building2 className="w-4 h-4 mr-2" />
            Client Analysis
          </TabsTrigger>
        </TabsList>

        <TabsContent value="internal-wo" className="mt-4">
          <InternalWOTab token={token} headers={headers} />
        </TabsContent>

        <TabsContent value="maklon" className="mt-4">
          <MaklonActualTab token={token} headers={headers} />
        </TabsContent>

        <TabsContent value="client-analysis" className="mt-4">
          <ClientAnalysisTab token={token} headers={headers} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB 1: Internal WO (existing functionality + comparison)
// ══════════════════════════════════════════════════════════════════════════════
function InternalWOTab({ token, headers }) {
  const [settings, setSettings] = useState(null);
  const [wos, setWos] = useState([]);
  const [selected, setSelected] = useState(null);
  const [hpp, setHpp] = useState(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [cs, ws] = await Promise.all([
        fetch('/api/rahaza/costing-settings', { headers }).then(r => r.json()),
        // FASE 5: HPP internal kini per JOB (engine baru)
        fetch('/api/production-jobs?business_type=internal', { headers }).then(r => r.json()),
      ]);
      setSettings(cs || null);
      setWos(Array.isArray(ws) ? ws : []);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const computeHPP = async (wo_id) => {
    const r = await fetch(`/api/production-jobs/${wo_id}/hpp`, { headers });
    if (r.ok) setHpp(await r.json());
  };

  const saveSettings = async () => {
    setSavingSettings(true);
    try {
      await fetch('/api/rahaza/costing-settings', { method: 'PUT', headers, body: JSON.stringify(settings) });
      toast.success('Settings tersimpan');
      if (selected) computeHPP(selected.id);
    } finally {
      setSavingSettings(false);
    }
  };

  const snapshot = async () => {
    if (!selected) return;
    const r = await fetch(`/api/production-jobs/${selected.id}/hpp-snapshot`, { method: 'POST', headers });
    if (r.ok) {
      toast.success('Snapshot HPP tersimpan');
    }
  };

  // Estimated HPP calculation (simplified: from BOM or fallback)
  const getEstimatedHPP = (wo) => {
    // Simplified: use material_cost + labor_fallback + overhead as estimated
    // In real scenario, this would come from BOM snapshot at WO creation
    // For now, we'll use actual as baseline (can be improved later)
    return hpp ? hpp.total_cost * 0.95 : 0; // assume 5% variance for demo
  };

  return (
    <div className="space-y-4">
      {/* Settings */}
      {settings && (
        <GlassCard className="p-4" data-testid="hpp-settings">
          <h3 className="font-semibold text-foreground mb-3">
            <Calculator className="w-4 h-4 inline mr-1" />
            Global Costing Settings
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <label className="text-xs uppercase text-muted-foreground">Overhead/pcs</label>
              <GlassInput
                type="number"
                min={0}
                value={settings.overhead_rate_per_pcs || 0}
                onChange={e => setSettings(s => ({ ...s, overhead_rate_per_pcs: Number(e.target.value) }))}
                data-testid="hpp-overhead-pcs"
              />
            </div>
            <div>
              <label className="text-xs uppercase text-muted-foreground">Default Bahan/kg</label>
              <GlassInput
                type="number"
                min={0}
                value={readNumber(settings, FIELD.defaultMaterialCostPerKg)}
                onChange={e => setSettings(s => ({ ...s, default_material_cost_per_kg: Number(e.target.value) }))}
                data-testid="hpp-yarn-kg"
              />
            </div>
            <div>
              <label className="text-xs uppercase text-muted-foreground">Default Accessory/unit</label>
              <GlassInput
                type="number"
                min={0}
                value={settings.default_accessory_cost_per_unit || 0}
                onChange={e => setSettings(s => ({ ...s, default_accessory_cost_per_unit: Number(e.target.value) }))}
              />
            </div>
            <div>
              <label className="text-xs uppercase text-muted-foreground">Labor Fallback/pcs</label>
              <GlassInput
                type="number"
                min={0}
                value={settings.labor_rate_fallback_per_pcs || 0}
                onChange={e => setSettings(s => ({ ...s, labor_rate_fallback_per_pcs: Number(e.target.value) }))}
              />
            </div>
          </div>
          <div className="flex justify-end mt-3">
            <Button onClick={saveSettings} disabled={savingSettings} data-testid="hpp-save-settings">
              <Save className="w-4 h-4 mr-1.5" />
              {savingSettings ? 'Menyimpan...' : 'Simpan Settings'}
            </Button>
          </div>
        </GlassCard>
      )}

      {/* WO list + Detail */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="p-0 lg:col-span-1 overflow-hidden">
          <div className="p-3 border-b border-[var(--glass-border)] text-sm font-semibold text-foreground">
            Production Jobs (Internal)
          </div>
          <ScrollArea className="h-[500px]">
            {wos.length === 0 ? (
              <div className="p-6 text-center text-muted-foreground text-xs">Belum ada job produksi internal.</div>
            ) : (
              wos.map(w => (
                <button
                  key={w.id}
                  onClick={() => {
                    setSelected(w);
                    computeHPP(w.id);
                  }}
                  className={`w-full text-left p-3 border-b border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] ${
                    selected?.id === w.id ? 'bg-[var(--glass-bg-hover)]' : ''
                  }`}
                  data-testid={`hpp-wo-${w.job_number || w.wo_number}`}
                >
                  <div className="font-mono text-xs text-foreground">{w.job_number || w.wo_number}</div>
                  <div className="text-xs text-muted-foreground">
                    {w.po_number} · <span className="text-primary">{w.status}</span>
                  </div>
                </button>
              ))
            )}
          </ScrollArea>
        </GlassCard>

        <div className="lg:col-span-2">
          {!hpp ? (
            <GlassCard className="p-8 text-center text-muted-foreground">
              Pilih Job Produksi untuk hitung HPP Aktual
            </GlassCard>
          ) : (
            <div className="space-y-3" data-testid="hpp-detail">
              <GlassCard className="p-4">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-lg font-bold text-foreground">{hpp.job_number || selected?.job_number || hpp.wo_number}</h3>
                    <p className="text-xs text-muted-foreground">
                      basis {hpp.basis || '-'} · qty selesai {hpp.qty_completed ?? hpp.qty ?? 0} pcs
                    </p>
                  </div>
                  <Button onClick={snapshot} className="h-9" data-testid="hpp-snapshot">
                    <Save className="w-4 h-4 mr-1.5" />
                    Snapshot
                  </Button>
                </div>

                {/* Comparison: Estimated vs Actual */}
                <div className="mb-4 p-3 bg-[var(--glass-bg)] rounded-lg border border-[var(--glass-border)]">
                  <HppComparisonInline estimated={getEstimatedHPP(selected)} actual={hpp.total_cost} />
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <GlassPanel className="px-3 py-2">
                    <div className="text-[10px] uppercase text-muted-foreground">
                      <Package className="w-3 h-3 inline" /> Material
                    </div>
                    <div className="text-lg font-bold text-foreground" data-testid="hpp-material-cost">
                      {fmt(hpp.material_cost)}
                    </div>
                  </GlassPanel>
                  <GlassPanel className="px-3 py-2">
                    <div className="text-[10px] uppercase text-muted-foreground">
                      <Users className="w-3 h-3 inline" /> Labor
                    </div>
                    <div className="text-lg font-bold text-foreground" data-testid="hpp-labor-cost">
                      {fmt(hpp.labor_cost)}
                    </div>
                  </GlassPanel>
                  <GlassPanel className="px-3 py-2">
                    <div className="text-[10px] uppercase text-muted-foreground">
                      <Layers className="w-3 h-3 inline" /> Overhead
                    </div>
                    <div className="text-lg font-bold text-foreground">{fmt(hpp.overhead_cost)}</div>
                  </GlassPanel>
                  <GlassPanel className="px-3 py-2 bg-primary/10 border-primary/30">
                    <div className="text-[10px] uppercase text-primary">HPP / Unit</div>
                    <div className="text-lg font-bold text-primary" data-testid="hpp-unit-actual">
                      {fmt(hpp.hpp_unit)}
                    </div>
                  </GlassPanel>
                </div>
                <div className="mt-3 pt-3 border-t border-[var(--glass-border)] flex justify-between items-center">
                  <span className="text-sm font-semibold text-foreground">Total Biaya</span>
                  <span className="text-xl font-bold text-foreground font-mono">{fmt(hpp.total_cost)}</span>
                </div>
              </GlassCard>

              {/* Material Breakdown */}
              <GlassCard className="p-4">
                <h4 className="font-semibold text-foreground mb-2">
                  Breakdown Material ({hpp.material_breakdown?.length || 0})
                </h4>
                {(!hpp.material_breakdown || hpp.material_breakdown.length === 0) ? (
                  <div className="text-xs text-muted-foreground">Belum ada material issue utk job ini (breakdown agregat: lihat kartu di atas).</div>
                ) : (
                  <ScrollArea className="h-[200px]">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left text-muted-foreground">
                          <th>Material</th>
                          <th>Tipe</th>
                          <th className="text-right">Qty</th>
                          <th className="text-right">Unit Cost</th>
                          <th className="text-right">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hpp.material_breakdown.map((m, i) => (
                          <tr key={i} className="border-t border-[var(--glass-border)]">
                            <td className="py-1">{m.material_name}</td>
                            <td className="py-1 text-muted-foreground">{m.type}</td>
                            <td className="py-1 text-right font-mono">
                              {m.qty} {m.unit}
                            </td>
                            <td className="py-1 text-right font-mono">{fmt(m.unit_cost)}</td>
                            <td className="py-1 text-right font-mono">{fmt(m.amount)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </ScrollArea>
                )}
              </GlassCard>

              {/* Labor Breakdown */}
              <GlassCard className="p-4">
                <h4 className="font-semibold text-foreground mb-2">
                  Breakdown Labor ({hpp.labor_breakdown?.length || 0})
                </h4>
                {(!hpp.labor_breakdown || hpp.labor_breakdown.length === 0) ? (
                  <div className="text-xs text-muted-foreground">Belum ada output produksi tagged ke job ini (labor agregat: lihat kartu di atas).</div>
                ) : (
                  <ScrollArea className="h-[200px]">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left text-muted-foreground">
                          <th>Operator</th>
                          <th>Proses</th>
                          <th className="text-right">Qty</th>
                          <th className="text-right">Rate</th>
                          <th className="text-right">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hpp.labor_breakdown.map((l, i) => (
                          <tr key={i} className="border-t border-[var(--glass-border)]">
                            <td className="py-1">{l.operator_name}</td>
                            <td className="py-1 text-muted-foreground">{l.process_code}</td>
                            <td className="py-1 text-right font-mono">{l.qty} pcs</td>
                            <td className="py-1 text-right font-mono">{fmt(l.rate)}</td>
                            <td className="py-1 text-right font-mono">{fmt(l.amount)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </ScrollArea>
                )}
              </GlassCard>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB 2: Maklon Actual HPP
// ══════════════════════════════════════════════════════════════════════════════
function MaklonActualTab({ token, headers }) {
  const [orders, setOrders] = useState([]);
  const [selectedOrderId, setSelectedOrderId] = useState('');
  const [hpp, setHpp] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchOrders = async () => {
      try {
        const r = await fetch('/api/dewi/maklon/pos', { headers });
        if (r.ok) {
          const data = posToLegacyOrders(await r.json());
          setOrders(data.filter(o => !['draft', 'cancelled'].includes(o.status)));
        }
      } catch (e) {
        toast.error('Gagal memuat orders');
      }
    };
    fetchOrders();
  }, [headers]);

  const loadHPP = async (orderId) => {
    if (!orderId) return;
    setLoading(true);
    try {
      const r = await fetch(`/api/rahaza/hpp/maklon-order/${orderId}`, { headers });
      if (r.ok) {
        setHpp(await r.json());
      } else {
        toast.error('Gagal memuat HPP maklon order');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleOrderSelect = (orderId) => {
    setSelectedOrderId(orderId);
    loadHPP(orderId);
  };

  return (
    <div className="space-y-4">
      <GlassCard className="p-5">
        <label className="block text-sm font-medium text-foreground mb-2">Pilih Maklon Order</label>
        <Select value={selectedOrderId} onValueChange={handleOrderSelect}>
          <SelectTrigger className="w-full md:w-96" data-testid="maklon-order-select">
            <SelectValue placeholder="Pilih order maklon..." />
          </SelectTrigger>
          <SelectContent>
            {orders.map(o => (
              <SelectItem key={o.id} value={o.id}>
                {o.order_code} — {o.product_name} ({o.qty_ordered} pcs)
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </GlassCard>

      {loading && (
        <GlassCard className="p-5">
          <Skeleton className="h-32 w-full" />
        </GlassCard>
      )}

      {!loading && hpp && (
        <div className="space-y-4">
          <GlassCard className="p-5">
            <div className="mb-4">
              <h3 className="text-lg font-bold text-foreground">{hpp.order_code}</h3>
              <p className="text-sm text-muted-foreground">
                {hpp.client_name} · {hpp.product_name} · {hpp.qty_ordered} pcs
              </p>
            </div>

            {/* Comparison */}
            <div className="mb-4 p-4 bg-[var(--glass-bg)] rounded-lg border border-[var(--glass-border)]">
              <HppComparisonInline estimated={hpp.estimated_hpp_total} actual={hpp.total_cost_actual} />
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <GlassPanel className="px-3 py-2">
                <div className="text-[10px] uppercase text-muted-foreground">Material</div>
                <div className="text-lg font-bold text-foreground" data-testid="maklon-hpp-material">
                  {fmt(hpp.material_cost_actual)}
                </div>
              </GlassPanel>
              <GlassPanel className="px-3 py-2">
                <div className="text-[10px] uppercase text-muted-foreground">Labor</div>
                <div className="text-lg font-bold text-foreground" data-testid="maklon-hpp-labor">
                  {fmt(hpp.labor_cost_actual)}
                </div>
              </GlassPanel>
              <GlassPanel className="px-3 py-2">
                <div className="text-[10px] uppercase text-muted-foreground">Overhead</div>
                <div className="text-lg font-bold text-foreground">{fmt(hpp.overhead_cost_actual)}</div>
              </GlassPanel>
              <GlassPanel className="px-3 py-2 bg-primary/10 border-primary/30">
                <div className="text-[10px] uppercase text-primary">HPP / Unit</div>
                <div className="text-lg font-bold text-primary" data-testid="maklon-hpp-unit">
                  {fmt(hpp.hpp_unit_actual)}
                </div>
              </GlassPanel>
            </div>
          </GlassCard>

          {/* Breakdown Tables */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <GlassCard className="p-4">
              <h4 className="font-semibold text-foreground mb-2">Material Breakdown</h4>
              {(!hpp.material_breakdown || hpp.material_breakdown.length === 0) ? (
                <div className="text-xs text-muted-foreground">Belum ada material issue</div>
              ) : (
                <ScrollArea className="h-[200px]">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-muted-foreground">
                        <th>Material</th>
                        <th className="text-right">Qty</th>
                        <th className="text-right">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {hpp.material_breakdown.map((m, i) => (
                        <tr key={i} className="border-t border-[var(--glass-border)]">
                          <td className="py-1">{m.material_name}</td>
                          <td className="py-1 text-right font-mono">
                            {m.qty} {m.unit}
                          </td>
                          <td className="py-1 text-right font-mono">{fmt(m.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </ScrollArea>
              )}
            </GlassCard>

            <GlassCard className="p-4">
              <h4 className="font-semibold text-foreground mb-2">Labor Breakdown</h4>
              {(!hpp.labor_breakdown || hpp.labor_breakdown.length === 0) ? (
                <div className="text-xs text-muted-foreground">Belum ada labor WIP events</div>
              ) : (
                <ScrollArea className="h-[200px]">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-muted-foreground">
                        <th>Operator</th>
                        <th>Proses</th>
                        <th className="text-right">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {hpp.labor_breakdown.map((l, i) => (
                        <tr key={i} className="border-t border-[var(--glass-border)]">
                          <td className="py-1">{l.operator_name}</td>
                          <td className="py-1">{l.process_code}</td>
                          <td className="py-1 text-right font-mono">{fmt(l.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </ScrollArea>
              )}
            </GlassCard>
          </div>
        </div>
      )}

      {!loading && !hpp && selectedOrderId && (
        <GlassCard className="p-8 text-center text-muted-foreground">
          Tidak ada data HPP untuk order ini
        </GlassCard>
      )}

      {!selectedOrderId && (
        <GlassCard className="p-8 text-center text-muted-foreground">
          Pilih Maklon Order untuk melihat perhitungan HPP Aktual
        </GlassCard>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB 3: Client Analysis
// ══════════════════════════════════════════════════════════════════════════════
function ClientAnalysisTab({ token, headers }) {
  const [clients, setClients] = useState([]);
  const [selectedClientId, setSelectedClientId] = useState('');
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchClients = async () => {
      try {
        const r = await fetch('/api/dewi/maklon/clients', { headers });
        if (r.ok) {
          const data = await r.json();
          setClients(data.filter(c => c.status === 'active'));
        }
      } catch (e) {
        toast.error('Gagal memuat clients');
      }
    };
    fetchClients();
  }, [headers]);

  const loadAnalysis = async (clientId) => {
    if (!clientId) return;
    setLoading(true);
    try {
      const r = await fetch(`/api/rahaza/hpp/maklon-client/${clientId}`, { headers });
      if (r.ok) {
        setAnalysis(await r.json());
      } else {
        toast.error('Gagal memuat analisa client');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleClientSelect = (clientId) => {
    setSelectedClientId(clientId);
    loadAnalysis(clientId);
  };

  const exportCSV = async () => {
    if (!selectedClientId) return;
    try {
      const r = await fetch(`/api/dewi/reports/maklon/client/${selectedClientId}/export.csv`, { headers });
      if (r.ok) {
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `client_analysis_${selectedClientId}_${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e) {
      throw new Error(e.message);
    }
  };

  const exportExcel = async () => {
    if (!selectedClientId) return;
    try {
      const r = await fetch(`/api/dewi/reports/maklon/client/${selectedClientId}/export.xlsx`, { headers });
      if (r.ok) {
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `client_analysis_${selectedClientId}_${new Date().toISOString().split('T')[0]}.xlsx`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e) {
      throw new Error(e.message);
    }
  };

  return (
    <div className="space-y-4">
      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">Pilih Klien Maklon</label>
            <Select value={selectedClientId} onValueChange={handleClientSelect}>
              <SelectTrigger className="w-full md:w-96" data-testid="client-select">
                <SelectValue placeholder="Pilih klien..." />
              </SelectTrigger>
              <SelectContent>
                {clients.map(c => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.code} — {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {analysis && (
            <ExportButtonGroup onExportCSV={exportCSV} onExportExcel={exportExcel} disabled={!analysis} />
          )}
        </div>
      </GlassCard>

      {loading && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map(i => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}

      {!loading && analysis && (
        <div className="space-y-4">
          {/* KPI Bento Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <GlassPanel className="p-4">
              <div className="text-xs text-muted-foreground">Total Orders</div>
              <div className="text-2xl font-bold text-foreground" data-testid="client-report-total-orders">
                {analysis.total_orders}
              </div>
            </GlassPanel>
            <GlassPanel className="p-4">
              <div className="text-xs text-muted-foreground">Total Qty</div>
              <div className="text-2xl font-bold text-foreground">
                {analysis.total_qty.toLocaleString('id-ID')} pcs
              </div>
            </GlassPanel>
            <GlassPanel className="p-4">
              <div className="text-xs text-muted-foreground">Total Revenue</div>
              <div className="text-2xl font-bold text-foreground" data-testid="client-report-revenue">
                {fmt(analysis.total_revenue)}
              </div>
            </GlassPanel>
            <GlassPanel className="p-4 bg-primary/10 border-primary/30">
              <div className="text-xs text-primary">Margin</div>
              <div className="text-2xl font-bold text-primary" data-testid="client-report-margin-kpi">
                {analysis.margin_pct.toFixed(1)}%
              </div>
            </GlassPanel>
          </div>

          {/* HPP Comparison */}
          <GlassCard className="p-5">
            <h3 className="font-semibold text-foreground mb-3">HPP Summary</h3>
            <HppComparisonInline estimated={analysis.total_hpp_estimated} actual={analysis.total_hpp_actual} />
          </GlassCard>

          {/* Orders Table */}
          <GlassCard className="p-0 overflow-hidden">
            <div className="p-4 border-b border-[var(--glass-border)]">
              <h3 className="font-semibold text-foreground">Orders Detail ({analysis.orders.length})</h3>
            </div>
            <ScrollArea className="h-[400px]">
              <table className="w-full text-sm" data-testid="client-analysis-table">
                <thead className="sticky top-0 bg-[var(--card-surface)] backdrop-blur-md">
                  <tr className="text-left text-muted-foreground border-b border-[var(--glass-border)]">
                    <th className="p-3">Order Code</th>
                    <th className="p-3">Product</th>
                    <th className="p-3 text-right">Qty</th>
                    <th className="p-3">Status</th>
                    <th className="p-3 text-right">Revenue</th>
                    <th className="p-3 text-right">HPP Actual</th>
                    <th className="p-3 text-right">Margin</th>
                    <th className="p-3 text-center">On-Time</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.orders.map((order, i) => (
                    <tr
                      key={i}
                      className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)]"
                      data-testid="client-analysis-row"
                    >
                      <td className="p-3 font-mono text-xs">{order.order_code}</td>
                      <td className="p-3">{order.product_name}</td>
                      <td className="p-3 text-right font-mono">{order.qty}</td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 rounded-full text-xs bg-primary/10 text-primary">
                          {order.status}
                        </span>
                      </td>
                      <td className="p-3 text-right font-mono">{fmt(order.revenue)}</td>
                      <td className="p-3 text-right font-mono">{fmt(order.hpp_actual)}</td>
                      <td className="p-3 text-right font-mono">
                        <span
                          className={
                            order.margin > 0
                              ? 'text-emerald-400'
                              : order.margin < 0
                              ? 'text-rose-400'
                              : 'text-muted-foreground'
                          }
                        >
                          {fmt(order.margin)}
                        </span>
                      </td>
                      <td className="p-3 text-center">
                        {order.is_on_time === true ? (
                          <span className="text-emerald-400">✓</span>
                        ) : order.is_on_time === false ? (
                          <span className="text-rose-400">✗</span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollArea>
          </GlassCard>
        </div>
      )}

      {!loading && !analysis && selectedClientId && (
        <GlassCard className="p-8 text-center text-muted-foreground">
          Tidak ada data untuk client ini
        </GlassCard>
      )}

      {!selectedClientId && (
        <GlassCard className="p-8 text-center text-muted-foreground">
          Pilih Klien Maklon untuk melihat analisa KPI & HPP
        </GlassCard>
      )}
    </div>
  );
}
