import { useState } from 'react';
import {
  Package, Truck, TrendingUp, Send, LogOut, X,
  Briefcase, AlertTriangle, BarChart2,
  ClipboardCheck, AlertOctagon, Bell, Hash, ClipboardList, BookOpen
} from 'lucide-react';

import VendorDashboard          from './VendorDashboard';
import VendorReceiving          from './VendorReceiving';
import VendorMaterialInspection from './VendorMaterialInspection';
import VendorMaterialRequests   from './VendorMaterialRequests';
import VendorProductionJobs     from './VendorProductionJobs';
import VendorProgress           from './VendorProgress';
import VendorDefectReports      from './VendorDefectReports';
import VendorBuyerShipments     from './VendorBuyerShipments';
import VendorSerialTracking     from './VendorSerialTracking';
import VendorVarianceReport     from './VendorVarianceReport';
import VendorReminderInbox      from './VendorReminderInbox';
import VendorProductionGuide    from './VendorProductionGuide';

// ─────────────────────────────────────────────────────────────────────────────
export default function VendorPortalApp({ user, token, onLogout }) {
  const [activeModule, setActiveModule] = useState('dashboard');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const modules = [
    { id: 'dashboard',         label: 'Dashboard',              icon: BarChart2 },
    { id: 'receiving',         label: 'Penerimaan Material',    icon: Package },
    { id: 'inspeksi',          label: 'Inspeksi Material',      icon: ClipboardCheck },
    { id: 'material-requests', label: 'Permintaan Material',    icon: ClipboardList },
    { id: 'production-jobs',   label: 'Pekerjaan Produksi',     icon: Briefcase },
    { id: 'production-guide',  label: 'Panduan Produksi',       icon: BookOpen },
    { id: 'progress',          label: 'Progress Produksi',      icon: TrendingUp },
    { id: 'buyer-shipments',   label: 'Pengiriman ke Buyer',    icon: Send },
    { id: 'serial-tracking',   label: 'Serial Tracking',        icon: Hash },
    { id: 'variance-report',   label: 'Laporan Variance',       icon: AlertTriangle },
    { id: 'reminders',         label: 'Inbox Reminder',         icon: Bell },
  ];

  const renderModule = () => {
    switch (activeModule) {
      case 'dashboard':          return <VendorDashboard token={token} user={user} onNavigate={setActiveModule} />;
      case 'receiving':          return <VendorReceiving token={token} user={user} />;
      case 'inspeksi':           return <VendorMaterialInspection user={user} />;
      case 'material-requests':  return <VendorMaterialRequests user={user} />;
      case 'production-jobs':    return <VendorProductionJobs user={user} />;
      case 'production-guide':   return <VendorProductionGuide user={user} />;
      case 'progress':           return <VendorProgress token={token} user={user} />;
      case 'defect-reports':     return <VendorDefectReports token={token} user={user} />;
      case 'buyer-shipments':    return <VendorBuyerShipments user={user} />;
      case 'serial-tracking':    return <VendorSerialTracking token={token} user={user} />;
      case 'variance-report':    return <VendorVarianceReport token={token} user={user} />;
      case 'reminders':          return <VendorReminderInbox token={token} user={user} />;
      default:                   return <VendorDashboard token={token} user={user} onNavigate={setActiveModule} />;
    }
  };

  return (
    <div className="flex h-screen bg-muted/40">
      {/* Sidebar */}
      <div className={`fixed left-0 top-0 h-full bg-emerald-900 text-white transition-all duration-300 z-40 flex flex-col ${sidebarCollapsed ? 'w-16' : 'w-64'}`}>
        <div className="flex items-center justify-between p-4 border-b border-emerald-800">
          {!sidebarCollapsed && (
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-emerald-500 rounded-lg flex items-center justify-center"><Truck className="w-5 h-5" /></div>
              <div><div className="font-bold text-sm">VENDOR PORTAL</div><div className="text-emerald-300 text-xs">Garment ERP</div></div>
            </div>
          )}
          <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} className="text-emerald-300 hover:text-white ml-auto">
            {sidebarCollapsed ? <Package className="w-5 h-5" /> : <X className="w-5 h-5" />}
          </button>
        </div>
        {!sidebarCollapsed && (
          <div className="px-4 py-3 border-b border-emerald-800">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-emerald-600 rounded-full flex items-center justify-center text-sm font-bold">{user?.name?.[0]?.toUpperCase()}</div>
              <div><div className="text-sm font-medium truncate">{user?.name}</div><div className="text-xs text-emerald-300">Vendor Portal</div></div>
            </div>
          </div>
        )}
        <nav className="flex-1 py-2 overflow-y-auto">
          {modules.map(m => {
            const Icon = m.icon;
            return (
              <button key={m.id} onClick={() => setActiveModule(m.id)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${activeModule === m.id ? 'bg-emerald-600 text-white' : 'text-emerald-200 hover:bg-emerald-800'} ${sidebarCollapsed ? 'justify-center' : ''}`}
                title={sidebarCollapsed ? m.label : ''}>
                <Icon className="w-5 h-5 flex-shrink-0" />
                {!sidebarCollapsed && <span>{m.label}</span>}
              </button>
            );
          })}
        </nav>
        <div className="border-t border-emerald-800 p-2">
          <button onClick={onLogout} className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm text-emerald-300 hover:bg-emerald-800 hover:text-white rounded ${sidebarCollapsed ? 'justify-center' : ''}`}>
            <LogOut className="w-5 h-5" />{!sidebarCollapsed && <span>Logout</span>}
          </button>
        </div>
      </div>

      <div className={`flex-1 flex flex-col min-h-0 transition-all duration-300 ${sidebarCollapsed ? 'ml-16' : 'ml-64'}`}>
        <header className="bg-card border-b border-border px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-foreground">{modules.find(m => m.id === activeModule)?.label}</h2>
            <p className="text-xs text-muted-foreground/70">{user?.name} — Vendor Portal</p>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-lg">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
            <span className="text-sm text-emerald-700 font-medium">Online</span>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-6">{renderModule()}</main>
      </div>
    </div>
  );
}
