import { useState, useEffect } from 'react';
import { GlassCard } from '@/components/ui/glass';
import {
  Palette, Package, FlaskConical, Calculator, GitBranch,
  Plus, Search, Filter, Download, TrendingUp
} from 'lucide-react';
import { toast } from '../ui/sonner';
import RnDStylesTab from './RnDStylesTab';
import RnDSamplesTab from './RnDSamplesTab';
import RnDMaterialsTab from './RnDMaterialsTab';
import RnDCostingTab from './RnDCostingTab';
import RnDRevisionsTab from './RnDRevisionsTab';

const API = process.env.REACT_APP_BACKEND_URL || '';

const TABS = [
  { id: 'styles', label: 'Master Style & Tech Pack', icon: Palette },
  { id: 'samples', label: 'Sample Requests', icon: Package },
  { id: 'materials', label: 'Material Research', icon: FlaskConical },
  { id: 'costing', label: 'Sample Costing', icon: Calculator },
  { id: 'revisions', label: 'Design Revisions', icon: GitBranch },
];

export default function RnDModule({ token, user }) {
  const [activeTab, setActiveTab] = useState('styles');
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(false);

  const headers = { Authorization: `Bearer ${token}` };

  useEffect(() => {
    fetchAnalytics();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/dewi/rnd/analytics`, { headers });
      if (res.ok) {
        const data = await res.json();
        setAnalytics(data);
      }
    } catch (e) {
      console.error('Failed to fetch analytics', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-6" data-testid="rnd-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">RnD & Style Master</h1>
          <p className="text-muted-foreground mt-1">
            Kelola style, sample, material research, costing, dan revisi desain
          </p>
        </div>
      </div>

      {/* Analytics Cards */}
      {analytics && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <GlassCard className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg" style={{ backgroundColor: 'hsl(var(--primary)/0.1)' }}>
                <Palette className="w-5 h-5" style={{ color: 'hsl(var(--primary))' }} />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Total Styles</p>
                <p className="text-2xl font-bold">{analytics.styles?.total || 0}</p>
              </div>
            </div>
          </GlassCard>
          
          <GlassCard className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg" style={{ backgroundColor: 'hsl(268 83% 58% / 0.1)' }}>
                <Package className="w-5 h-5" style={{ color: 'hsl(268 83% 58%)' }} />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Pending Samples</p>
                <p className="text-2xl font-bold">{analytics.sample_requests?.pending || 0}</p>
              </div>
            </div>
          </GlassCard>
          
          <GlassCard className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg" style={{ backgroundColor: 'hsl(142 71% 45% / 0.1)' }}>
                <Package className="w-5 h-5" style={{ color: 'hsl(142 71% 45%)' }} />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Approved Samples</p>
                <p className="text-2xl font-bold">{analytics.sample_requests?.approved || 0}</p>
              </div>
            </div>
          </GlassCard>
          
          <GlassCard className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg" style={{ backgroundColor: 'hsl(24 95% 53% / 0.1)' }}>
                <FlaskConical className="w-5 h-5" style={{ color: 'hsl(24 95% 53%)' }} />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Materials</p>
                <p className="text-2xl font-bold">{analytics.materials?.total || 0}</p>
              </div>
            </div>
          </GlassCard>
          
          <GlassCard className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg" style={{ backgroundColor: 'hsl(43 96% 56% / 0.1)' }}>
                <GitBranch className="w-5 h-5" style={{ color: 'hsl(43 96% 56%)' }} />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Total Revisions</p>
                <p className="text-2xl font-bold">{analytics.revisions?.total || 0}</p>
              </div>
            </div>
          </GlassCard>
        </div>
      )}

      {/* Tabs */}
      <GlassCard className="p-1">
        <div className="flex items-center gap-2 overflow-x-auto">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${
                  isActive
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                }`}
                data-testid={`rnd-tab-${tab.id}`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </GlassCard>

      {/* Tab Content */}
      <div>
        {activeTab === 'styles' && <RnDStylesTab token={token} user={user} />}
        {activeTab === 'samples' && <RnDSamplesTab token={token} />}
        {activeTab === 'materials' && <RnDMaterialsTab token={token} />}
        {activeTab === 'costing' && <RnDCostingTab token={token} />}
        {activeTab === 'revisions' && <RnDRevisionsTab token={token} />}
      </div>
    </div>
  );
}
