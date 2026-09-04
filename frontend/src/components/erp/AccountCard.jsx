import { useState } from 'react';
import { Store, TrendingUp, Package, Star, ExternalLink, MoreVertical } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { formatRupiah } from '@/lib/format';

const fmt = formatRupiah;

const platformIcons = {
  shopee: '🛍️',
  tiktokshop: '🎵',
  tokopedia: '🛒',
};

const platformColors = {
  shopee: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
  tiktokshop: 'bg-pink-500/10 text-pink-400 border-pink-500/30',
  tokopedia: 'bg-green-500/10 text-green-400 border-green-500/30',
};

const statusColors = {
  active: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  inactive: 'bg-muted/10 text-muted-foreground border-border/30',
  suspended: 'bg-red-500/10 text-red-400 border-red-500/30',
};

export function AccountCard({ account, token, onViewDetail }) {
  const [loading, setLoading] = useState(false);

  const handleViewDashboard = () => {
    if (onViewDetail) {
      onViewDetail(account);
    }
  };

  const healthColor = () => {
    const score = account.health_score;
    if (score === null || score === undefined) return 'text-muted-foreground';
    if (score >= 80) return 'text-emerald-400';
    if (score >= 60) return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <GlassCard
      className="p-4 hover:border-primary/50 transition-all cursor-pointer"
      onClick={handleViewDashboard}
      data-testid={`account-card-${account.account_code}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{platformIcons[account.platform] || '🏪'}</span>
          <div>
            <div className="font-semibold text-foreground text-sm">{account.account_name}</div>
            <div className="text-xs text-muted-foreground">{account.account_code}</div>
          </div>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
              <MoreVertical className="w-4 h-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={handleViewDashboard}>
              <ExternalLink className="w-4 h-4 mr-2" />
              Lihat Dashboard
            </DropdownMenuItem>
            <DropdownMenuItem>Edit</DropdownMenuItem>
            <DropdownMenuItem className="text-red-400">Archive</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Badges */}
      <div className="flex items-center gap-2 mb-3">
        <Badge variant="outline" className={platformColors[account.platform]}>
          {account.platform}
        </Badge>
        <Badge variant="outline" className={statusColors[account.status]}>
          {account.status}
        </Badge>
        {account.group && account.group !== 'other' && (
          <Badge variant="outline" className="text-xs">
            {account.group.replace('_', ' ')}
          </Badge>
        )}
      </div>

      {/* Health Score */}
      <div className="mb-3 p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-muted-foreground">Health Score</span>
          <span className={`text-lg font-bold ${healthColor()}`}>
            {account.health_score !== null && account.health_score !== undefined ? account.health_score : 'N/A'}
          </span>
        </div>
        <div className="h-2 bg-[var(--glass-bg-hover)] rounded-full overflow-hidden">
          <div
            className={`h-full ${healthColor()} bg-current transition-all`}
            style={{ width: `${account.health_score !== null && account.health_score !== undefined ? account.health_score : 0}%` }}
          />
        </div>
      </div>

      {/* Quick Stats (Placeholder Phase 2) */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <div className="text-muted-foreground">Revenue</div>
          <div className="font-semibold text-foreground">-</div>
        </div>
        <div>
          <div className="text-muted-foreground">Orders</div>
          <div className="font-semibold text-foreground">-</div>
        </div>
      </div>

      {/* Actions */}
      <div className="mt-3 pt-3 border-t border-[var(--glass-border)]">
        <Button
          onClick={handleViewDashboard}
          variant="outline"
          size="sm"
          className="w-full"
          data-testid={`view-dashboard-${account.account_code}`}
        >
          <ExternalLink className="w-4 h-4 mr-2" />
          Lihat Detail
        </Button>
      </div>
    </GlassCard>
  );
}
