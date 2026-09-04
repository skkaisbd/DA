/**
 * UnifiedApprovalHub — Phase 3.3B: Unified Approval Inbox FE
 * 
 * Aggregator dashboard yang menampilkan summary dari semua approval inbox:
 * - HR Approval Inbox (cuti, lembur, gaji, resignasi, absensi)
 * - Multi-Level Approval (multi-stage workflow)
 * - Marketing Task Approval
 * - Finance Invoice Edit Approval
 * 
 * User dapat:
 * 1. Melihat total pending approvals di satu tempat
 * 2. Quick access ke masing-masing inbox spesifik
 * 3. Melihat recent pending items lintas domain
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Layers, Inbox, CheckCircle, Clock, Users, ShoppingBag, DollarSign,
  ArrowRight, RefreshCw, AlertTriangle, Calendar, TrendingUp, Briefcase
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { motion } from 'framer-motion';
import { toast } from 'sonner';
import { PageHeader } from './moduleAtoms';
// F15-B — kelas Tailwind tidak boleh dirakit saat berjalan; lihat lib/tone.js
import { tone } from '@/lib/tone';

const API = process.env.REACT_APP_BACKEND_URL;

function StatCard({ icon: Icon, label, value, description, color, onClick, badge }) {
  const colorMap = {
    violet:  { bg: 'bg-violet-100 dark:bg-violet-500/10', text: 'text-violet-600 dark:text-violet-300', border: 'border-violet-300 dark:border-violet-400/20', icon: 'text-violet-600 dark:text-violet-400' },
    blue:    { bg: 'bg-blue-100 dark:bg-blue-500/10', text: 'text-blue-600 dark:text-blue-300', border: 'border-blue-300 dark:border-blue-400/20', icon: 'text-blue-600 dark:text-blue-400' },
    amber:   { bg: 'bg-amber-100 dark:bg-amber-500/10', text: 'text-amber-600 dark:text-amber-300', border: 'border-amber-300 dark:border-amber-400/20', icon: 'text-amber-700 dark:text-amber-400' },
    emerald: { bg: 'bg-emerald-100 dark:bg-emerald-500/10', text: 'text-emerald-600 dark:text-emerald-300', border: 'border-emerald-300 dark:border-emerald-400/20', icon: 'text-emerald-600 dark:text-emerald-400' },
    red:     { bg: 'bg-red-100 dark:bg-red-500/10', text: 'text-red-600 dark:text-red-300', border: 'border-red-300 dark:border-red-400/20', icon: 'text-red-700 dark:text-red-400' },
  };
  const c = colorMap[color] || colorMap.violet;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ scale: 1.02 }}
      transition={{ duration: 0.2 }}
    >
      <GlassCard
        className={`p-5 border ${c.border} cursor-pointer hover:${c.bg} transition-all`}
        onClick={onClick}
        data-testid={`approval-hub-${label.toLowerCase().replace(/\s+/g, '-')}`}
      >
        <div className="flex items-start justify-between mb-3">
          <div className={`w-10 h-10 rounded-lg ${c.bg} border ${c.border} flex items-center justify-center`}>
            <Icon className={`w-5 h-5 ${c.icon}`} />
          </div>
          {badge && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5">
              {badge}
            </Badge>
          )}
        </div>
        <div className={`text-3xl font-bold ${c.text} mb-1`} data-testid={`count-${label.toLowerCase().replace(/\s+/g, '-')}`}>
          {value}
        </div>
        <div className="text-sm font-medium text-foreground mb-1">{label}</div>
        {description && (
          <div className="text-xs text-foreground/50">{description}</div>
        )}
        <div className="flex items-center gap-1 text-xs text-foreground/60 mt-3">
          <span>Buka Inbox</span>
          <ArrowRight className="w-3 h-3" />
        </div>
      </GlassCard>
    </motion.div>
  );
}

function RecentItemCard({ item, onNavigate }) {
  const typeConfig = {
    hr: { icon: Users, color: 'violet', label: 'HR Approval' },
    multilevel: { icon: Layers, color: 'blue', label: 'Multi-Level' },
    marketing: { icon: ShoppingBag, color: 'amber', label: 'Marketing Task' },
    finance: { icon: DollarSign, color: 'emerald', label: 'Finance' },
  };
  const config = typeConfig[item.source] || typeConfig.hr;
  const Icon = config.icon;

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      whileHover={{ scale: 1.005 }}
      className="p-3 rounded-lg bg-foreground/[0.03] border border-foreground/[0.08] hover:bg-foreground/[0.06] hover:border-violet-400 dark:border-violet-400/30 cursor-pointer"
      onClick={() => onNavigate(item.navigateTo)}
      data-testid={`recent-item-${item.id}`}
    >
      <div className="flex items-start gap-3">
        {/* F15-B — kelas Tailwind TIDAK boleh dirakit saat berjalan
            (`bg-${config.color}-500/10` tidak pernah dibuat). Lihat `lib/tone.js`. */}
        <div className={`w-8 h-8 rounded-lg border flex items-center justify-center flex-shrink-0 ${tone(config.color).chip}`}>
          <Icon className={`w-4 h-4 ${tone(config.color).text}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs text-foreground/50">{config.label}</span>
            <span className="text-xs font-semibold text-foreground truncate">{item.title}</span>
          </div>
          <div className="text-xs text-foreground/60">
            {item.requester} • {item.date}
          </div>
        </div>
        <ArrowRight className="w-4 h-4 text-foreground/40 flex-shrink-0" />
      </div>
    </motion.div>
  );
}

export default function UnifiedApprovalHub({ token, onNavigate }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const [loading, setLoading] = useState(true);
  const [counts, setCounts] = useState({
    hr: 0,
    multilevel: 0,
    marketing: 0,
    finance: 0,
  });
  const [recentItems, setRecentItems] = useState([]);

  const fetchCounts = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch counts dari berbagai endpoint secara parallel
      const [hrRes, multilevelRes, marketingRes, financeRes] = await Promise.allSettled([
        fetch(`${API}/api/hr/inbox`, { headers }).then(r => r.ok ? r.json() : null),
        fetch(`${API}/api/approvals/pending`, { headers }).then(r => r.ok ? r.json() : null),
        fetch(`${API}/api/marketing/tasks?status=pending_approval&limit=1`, { headers }).then(r => r.ok ? r.json() : null),
        fetch(`${API}/api/invoice-edit-requests?status=Pending&limit=1`, { headers }).then(r => r.ok ? r.json() : null),
      ]);

      const newCounts = {
        hr: 0,
        multilevel: 0,
        marketing: 0,
        finance: 0,
      };

      // HR Inbox count
      if (hrRes.status === 'fulfilled' && hrRes.value) {
        const hrData = hrRes.value;
        newCounts.hr = (hrData.counts?.leave || 0) + (hrData.counts?.overtime || 0) + 
                       (hrData.counts?.salary_adjustment || 0) + (hrData.counts?.resignation || 0) + 
                       (hrData.counts?.attendance || 0);
      }

      // Multi-level Approval count
      if (multilevelRes.status === 'fulfilled' && multilevelRes.value) {
        newCounts.multilevel = Array.isArray(multilevelRes.value) ? multilevelRes.value.length : 0;
      }

      // Marketing Task Approval count
      if (marketingRes.status === 'fulfilled' && marketingRes.value) {
        const marketingData = marketingRes.value;
        newCounts.marketing = marketingData.pagination?.total || marketingData.tasks?.length || 0;
      }

      // Finance Invoice Edit Approval count
      if (financeRes.status === 'fulfilled' && financeRes.value) {
        newCounts.finance = Array.isArray(financeRes.value) ? financeRes.value.length : 0;
      }

      setCounts(newCounts);

      // Build recent items sample (kombinasi dari berbagai source)
      const recent = [];
      
      // Sample dari HR
      if (hrRes.status === 'fulfilled' && hrRes.value?.items) {
        hrRes.value.items.slice(0, 2).forEach(item => {
          recent.push({
            id: `hr-${item.id}`,
            source: 'hr',
            title: item.title || item.type,
            requester: item.requester_name,
            date: new Date(item.submitted_at).toLocaleDateString('id-ID', { day: '2-digit', month: 'short' }),
            navigateTo: 'hr-inbox',
          });
        });
      }

      // Sample dari Multi-level
      if (multilevelRes.status === 'fulfilled' && Array.isArray(multilevelRes.value)) {
        multilevelRes.value.slice(0, 2).forEach(item => {
          recent.push({
            id: `ml-${item.id}`,
            source: 'multilevel',
            title: item.subject || item.ref_code,
            requester: item.requester_name,
            date: new Date(item.created_at).toLocaleDateString('id-ID', { day: '2-digit', month: 'short' }),
            navigateTo: 'approval-multilevel',
          });
        });
      }

      // Sample dari Marketing
      if (marketingRes.status === 'fulfilled' && marketingRes.value?.tasks) {
        marketingRes.value.tasks.slice(0, 2).forEach(item => {
          recent.push({
            id: `mk-${item.id}`,
            source: 'marketing',
            title: item.title,
            requester: item.assigned_to?.slice(0, 20) || 'Staff',
            date: item.due_date ? new Date(item.due_date).toLocaleDateString('id-ID', { day: '2-digit', month: 'short' }) : '-',
            navigateTo: 'marketing-approvals',
          });
        });
      }

      // Sample dari Finance
      if (financeRes.status === 'fulfilled' && Array.isArray(financeRes.value)) {
        financeRes.value.slice(0, 2).forEach(item => {
          recent.push({
            id: `fn-${item.id}`,
            source: 'finance',
            title: `Invoice ${item.invoice_number}`,
            requester: item.requested_by_name,
            date: new Date(item.requested_at).toLocaleDateString('id-ID', { day: '2-digit', month: 'short' }),
            navigateTo: 'fin-approval',
          });
        });
      }

      setRecentItems(recent.slice(0, 6)); // Limit to 6 recent items

    } catch (error) {
      toast.error('Gagal memuat data approval');
      console.error('Error fetching approval counts:', error);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => {
    fetchCounts();
  }, [fetchCounts]);

  const totalPending = counts.hr + counts.multilevel + counts.marketing + counts.finance;

  return (
    <div className="p-6 space-y-6" data-testid="unified-approval-hub">
      <PageHeader
        title="Pusat Approval Terpadu"
        description="Dashboard agregator untuk semua approval pending — HR, Multi-Level, Marketing, dan Finance dalam satu tempat"
        icon={Layers}
        actions={
          <Button 
            size="sm" 
            onClick={fetchCounts} 
            variant="outline" 
            className="gap-2" 
            disabled={loading}
            data-testid="refresh-hub"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> 
            Refresh
          </Button>
        }
      />

      {/* Summary Total */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <GlassCard className="p-6 bg-gradient-to-br from-violet-500/10 to-blue-500/10 border-violet-300 dark:border-violet-400/20">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-violet-100 dark:bg-violet-500/20 border border-violet-400 dark:border-violet-400/30 flex items-center justify-center">
              <Inbox className="w-8 h-8 text-violet-600 dark:text-violet-300" />
            </div>
            <div>
              <div className="text-5xl font-bold text-violet-200" data-testid="total-pending-count">
                {totalPending}
              </div>
              <div className="text-sm text-foreground/70 mt-1">
                Total Approval Pending
              </div>
            </div>
            {totalPending === 0 && (
              <div className="ml-auto flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
                <CheckCircle className="w-5 h-5" />
                <span className="text-sm font-medium">Semua clear! 🎉</span>
              </div>
            )}
            {totalPending > 10 && (
              <div className="ml-auto flex items-center gap-2 text-amber-700 dark:text-amber-400">
                <AlertTriangle className="w-5 h-5" />
                <span className="text-sm font-medium">Perlu perhatian</span>
              </div>
            )}
          </div>
        </GlassCard>
      </motion.div>

      {/* Quick Access Cards */}
      <div>
        <h3 className="text-sm font-semibold text-foreground/80 mb-4 flex items-center gap-2">
          <Briefcase className="w-4 h-4" />
          Quick Access ke Inbox
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            icon={Users}
            label="HR Approval"
            value={counts.hr}
            description="Cuti, Lembur, Gaji, Resignasi, Absensi"
            color="violet"
            onClick={() => onNavigate && onNavigate('hr-inbox')}
            badge={counts.hr > 5 ? 'URGENT' : null}
          />
          <StatCard
            icon={Layers}
            label="Multi-Level Approval"
            value={counts.multilevel}
            description="Workflow bertingkat lintas departemen"
            color="blue"
            onClick={() => onNavigate && onNavigate('approval-multilevel')}
          />
          <StatCard
            icon={ShoppingBag}
            label="Marketing Task"
            value={counts.marketing}
            description="Task approval dari staff marketing"
            color="amber"
            onClick={() => onNavigate && onNavigate('marketing-approvals')}
          />
          <StatCard
            icon={DollarSign}
            label="Finance Invoice"
            value={counts.finance}
            description="Invoice edit request approval"
            color="emerald"
            onClick={() => onNavigate && onNavigate('fin-approval')}
          />
        </div>
      </div>

      {/* Recent Pending Items */}
      {recentItems.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-foreground/80 mb-4 flex items-center gap-2">
            <Clock className="w-4 h-4" />
            Recent Pending Items
          </h3>
          <GlassCard className="p-4">
            <div className="space-y-2">
              {recentItems.map(item => (
                <RecentItemCard key={item.id} item={item} onNavigate={onNavigate} />
              ))}
            </div>
          </GlassCard>
        </div>
      )}

      {/* Empty State */}
      {!loading && totalPending === 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
        >
          <GlassCard className="p-12 text-center">
            <CheckCircle className="w-16 h-16 mx-auto mb-4 text-emerald-600 dark:text-emerald-400 opacity-50" />
            <h3 className="text-lg font-semibold text-foreground mb-2">Semua Approval Selesai!</h3>
            <p className="text-sm text-foreground/60">
              Tidak ada approval pending saat ini. Semua permohonan sudah diproses. 🎉
            </p>
          </GlassCard>
        </motion.div>
      )}

      {/* Info Card */}
      <GlassCard className="p-4 bg-blue-100 dark:bg-blue-500/5 border-blue-300 dark:border-blue-400/20">
        <div className="flex items-start gap-3">
          <TrendingUp className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-foreground/80">
            <p className="font-medium mb-1">Tentang Unified Approval Hub</p>
            <p className="text-xs leading-relaxed">
              Dashboard ini mengagregasi semua approval pending dari berbagai sistem (HR, Multi-Level, Marketing, Finance). 
              Klik kartu untuk langsung masuk ke inbox spesifik dan melakukan approval/reject.
            </p>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
