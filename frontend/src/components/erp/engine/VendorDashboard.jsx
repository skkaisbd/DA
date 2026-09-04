import { useState, useEffect } from 'react';
import { Clock, AlertTriangle, Package, Send, TrendingUp, Briefcase } from 'lucide-react';
import { StatCard } from './VendorShared';
import { apiGet } from '../../../lib/api';

export default function VendorDashboard({ token, user, onNavigate }) {
  const [metrics, setMetrics] = useState(null);

  useEffect(() => {
    apiGet('/vendor/dashboard').then(setMetrics).catch(console.error);
  }, []);

  const fmtDate = d => d ? new Date(d).toLocaleDateString('id-ID') : '-';

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Dashboard Vendor</h1>
        <p className="text-muted-foreground text-sm mt-1">Ikhtisar produksi — {user?.name}</p>
      </div>

      {/* Row 1: Job & Progress */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Job Produksi Aktif" value={metrics?.activeJobs || 0} icon={Briefcase} color="bg-blue-500" sub="job parent berjalan" />
        <StatCard title="Job Selesai" value={metrics?.completedJobs || 0} icon={TrendingUp} color="bg-emerald-500" sub="selesai diproduksi" />
        <StatCard title="Total Diproduksi" value={`${(metrics?.totalProduced || 0).toLocaleString('id-ID')} pcs`} icon={TrendingUp} color="bg-teal-500" sub={`${metrics?.progressPct || 0}% dari material tersedia`} />
        <StatCard title="Job Overdue" value={metrics?.overdueJobs || 0} icon={AlertTriangle} color={metrics?.overdueJobs > 0 ? "bg-red-500" : "bg-muted-foreground/50"} sub="melewati deadline" alert={metrics?.overdueJobs > 0} />
      </div>

      {/* Row 2: Material Status */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Material Diterima" value={`${(metrics?.totalReceived || 0).toLocaleString('id-ID')} pcs`} icon={Package} color="bg-emerald-500" sub="dari semua shipment" />
        <StatCard title="Material Kurang" value={`${(metrics?.totalMissing || 0).toLocaleString('id-ID')} pcs`} icon={AlertTriangle} color={metrics?.totalMissing > 0 ? "bg-amber-500" : "bg-muted-foreground/50"} sub="belum dikirim" alert={metrics?.totalMissing > 0} />
        <StatCard title="Material Cacat" value={`${(metrics?.totalDefect || 0).toLocaleString('id-ID')} pcs`} icon={AlertTriangle} color={metrics?.totalDefect > 0 ? "bg-red-400" : "bg-muted-foreground/50"} sub="dari laporan defect" alert={metrics?.totalDefect > 0} />
        <StatCard title="Shipment Masuk" value={metrics?.incomingShipments || 0} icon={Package} color="bg-amber-500" sub="menunggu konfirmasi" alert={metrics?.incomingShipments > 0} />
      </div>

      {/* Row 3: Requests & Shipments */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Permintaan Tambahan" value={metrics?.pendingAdditional || 0} icon={AlertTriangle} color={metrics?.pendingAdditional > 0 ? "bg-orange-500" : "bg-muted-foreground/50"} sub="pending persetujuan" alert={metrics?.pendingAdditional > 0} />
        <StatCard title="Permintaan Pengganti" value={metrics?.pendingReplacement || 0} icon={AlertTriangle} color={metrics?.pendingReplacement > 0 ? "bg-red-400" : "bg-muted-foreground/50"} sub="pending persetujuan" alert={metrics?.pendingReplacement > 0} />
        <StatCard title="Buyer Shipments" value={metrics?.pendingBuyerShipments || 0} icon={Send} color="bg-purple-500" sub="total pengiriman ke buyer" />
        <StatCard title="Inspeksi Pending" value={metrics?.pendingInspections || 0} icon={Package} color={metrics?.pendingInspections > 0 ? "bg-amber-600" : "bg-muted-foreground/50"} sub="shipment belum diinspeksi" alert={metrics?.pendingInspections > 0} />
      </div>

      {/* Overall progress */}
      {metrics && (
        <div className="bg-card rounded-xl border border-border p-5 shadow-sm">
          <div className="flex justify-between items-center mb-2">
            <span className="font-semibold text-foreground/90 text-sm">Progress Produksi Keseluruhan (Parent + Child Jobs)</span>
            <span className="text-sm font-bold text-blue-700">
              {(metrics.totalProduced || 0).toLocaleString('id-ID')} / {(metrics.totalAvailable || 0).toLocaleString('id-ID')} pcs ({metrics.progressPct || 0}%)
            </span>
          </div>
          <div className="w-full bg-muted rounded-full h-3">
            <div className="h-3 rounded-full transition-all bg-gradient-to-r from-emerald-400 to-emerald-600" style={{ width: `${Math.min(100, metrics.progressPct || 0)}%` }} />
          </div>
          {(metrics.totalMissing > 0 || metrics.totalDefect > 0) && (
            <div className="flex gap-4 mt-3 text-xs">
              {metrics.totalMissing > 0 && (
                <span className="px-2 py-1 bg-amber-50 border border-amber-200 rounded text-amber-700">
                  ⚠️ {metrics.totalMissing.toLocaleString('id-ID')} pcs material kurang
                </span>
              )}
              {metrics.totalDefect > 0 && (
                <span className="px-2 py-1 bg-red-50 border border-red-200 rounded text-red-700">
                  🚫 {metrics.totalDefect.toLocaleString('id-ID')} pcs material cacat
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Alerts */}
      {metrics?.alerts?.overdueJobs?.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <h3 className="font-semibold text-red-700 flex items-center gap-2 mb-3"><AlertTriangle className="w-4 h-4" /> Job Melewati Deadline ({metrics.alerts.overdueJobs.length})</h3>
          <div className="space-y-2">
            {metrics.alerts.overdueJobs.map(j => (
              <div key={j.id} className="flex items-center justify-between p-2 bg-card rounded-lg border border-red-100">
                <div>
                  <span className="font-bold text-red-800 text-sm">{j.job_number}</span>
                  <span className="text-xs text-muted-foreground ml-2">PO: {j.po_number}</span>
                </div>
                <span className="text-xs text-red-600 font-medium">Deadline: {fmtDate(j.deadline)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {metrics?.alerts?.nearDeadlineJobs?.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <h3 className="font-semibold text-amber-700 flex items-center gap-2 mb-3"><Clock className="w-4 h-4" /> Mendekati Deadline ({metrics.alerts.nearDeadlineJobs.length})</h3>
          <div className="space-y-2">
            {metrics.alerts.nearDeadlineJobs.map(j => (
              <div key={j.id} className="flex items-center justify-between p-2 bg-card rounded-lg border border-amber-100">
                <div>
                  <span className="font-bold text-amber-800 text-sm">{j.job_number}</span>
                  <span className="text-xs text-muted-foreground ml-2">PO: {j.po_number}</span>
                </div>
                <span className="text-xs text-amber-600 font-medium">Deadline: {fmtDate(j.deadline)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <button onClick={() => onNavigate('receiving')} className="py-3 bg-amber-50 border border-amber-200 text-amber-700 rounded-xl text-sm font-medium hover:bg-amber-100 transition-colors">
          📦 Penerimaan Material
        </button>
        <button onClick={() => onNavigate('production-jobs')} className="py-3 bg-blue-50 border border-blue-200 text-blue-700 rounded-xl text-sm font-medium hover:bg-blue-100 transition-colors">
          💼 Kelola Job Produksi
        </button>
        <button onClick={() => onNavigate('progress')} className="py-3 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-xl text-sm font-medium hover:bg-emerald-100 transition-colors">
          📈 Input Progress Produksi
        </button>
        <button onClick={() => onNavigate('buyer-shipments')} className="py-3 bg-purple-50 border border-purple-200 text-purple-700 rounded-xl text-sm font-medium hover:bg-purple-100 transition-colors">
          🚚 Pengiriman ke Buyer
        </button>
      </div>
    </div>
  );
}

// ─── VENDOR ACCESSORIES PANEL (lazy-loaded per shipment) ──────────────────────


