/**
 * ProcurementTab — Procurement Request list + approval inbox (with role-based filter)
 * Extracted from AssetManagementPortal.jsx during Phase 4 refactor.
 */
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Search, RefreshCw, ShoppingCart, CheckCheck } from 'lucide-react';
import { PR_STATUS_CONFIG } from '../constants';
import { fmtCurrency, fmtDate } from '../utils';
import { StatusBadge } from '../components/StatusBadge';

export function ProcurementTab({
  prTab, setPrTab,
  prData, prInbox,
  prSearch, setPrSearch,
  loadPRs,
  onSelectPR,
  isAdminLike,
  inboxScope, setInboxScope,
  inboxDept, setInboxDept,
  uniqueDepartments,
}) {
  return (
    <Tabs value={prTab} onValueChange={setPrTab}>
      <TabsList>
        <TabsTrigger value="all">Semua Request</TabsTrigger>
        <TabsTrigger value="inbox">
          Inbox Approval
          {prInbox.length > 0 && (
            <Badge className="ml-1 text-[10px] h-4 px-1.5 bg-amber-500 text-foreground">{prInbox.length}</Badge>
          )}
        </TabsTrigger>
      </TabsList>

      {/* All PRs */}
      <TabsContent value="all" className="mt-3">
        <div className="flex gap-2 mb-3">
          <div className="relative flex-1 max-w-sm">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="Cari request..." className="pl-8" value={prSearch}
              onChange={e => setPrSearch(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && loadPRs()}
              data-testid="pr-search-input" />
          </div>
          <Button size="sm" onClick={loadPRs} data-testid="pr-refresh-btn"><RefreshCw size={14} /></Button>
        </div>
        <div className="space-y-2">
          {prData.map(pr => (
            <div key={pr.id}
              className="flex items-center justify-between py-3 px-4 bg-[hsl(var(--card))] rounded-xl border cursor-pointer hover:bg-muted/30 transition-colors"
              onClick={() => onSelectPR?.(pr)}
              data-testid={`pr-row-${pr.id}`}>
              <div className="flex items-start gap-3">
                <ShoppingCart size={16} className="text-muted-foreground mt-0.5" />
                <div>
                  <p className="text-sm font-medium">{pr.title}</p>
                  <p className="text-xs text-muted-foreground">{pr.request_number} · {pr.requested_by_name}</p>
                </div>
              </div>
              <div className="text-right flex items-center gap-3">
                <div>
                  <p className="text-sm font-semibold">{fmtCurrency(pr.total_estimated)}</p>
                  <p className="text-xs text-muted-foreground">{fmtDate(pr.created_at)}</p>
                </div>
                <StatusBadge status={pr.status} configMap={PR_STATUS_CONFIG} />
              </div>
            </div>
          ))}
          {prData.length === 0 && (
            <div className="text-center py-12 text-muted-foreground">
              <ShoppingCart size={32} className="mx-auto mb-2 opacity-40" />
              <p className="text-sm">Belum ada request pengadaan</p>
            </div>
          )}
        </div>
      </TabsContent>

      {/* Approval Inbox */}
      <TabsContent value="inbox" className="mt-3">
        {/* Filter Toolbar */}
        <div className="flex flex-wrap items-center gap-2 mb-3 p-3 bg-muted/30 rounded-lg border" data-testid="inbox-filter-toolbar">
          <span className="text-xs font-medium text-muted-foreground mr-1">Tampilkan:</span>
          <Select value={inboxScope} onValueChange={setInboxScope}>
            <SelectTrigger className="h-8 w-[180px] text-xs" data-testid="inbox-scope-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="relevant">📥 Untuk Saya (sesuai role)</SelectItem>
              {isAdminLike && <SelectItem value="all">🌐 Semua Pending</SelectItem>}
              <SelectItem value="mine">📤 Permintaan Saya</SelectItem>
            </SelectContent>
          </Select>
          {isAdminLike && uniqueDepartments.length > 0 && (
            <Select value={inboxDept || '__all__'} onValueChange={(v) => setInboxDept(v === '__all__' ? '' : v)}>
              <SelectTrigger className="h-8 w-[160px] text-xs" data-testid="inbox-dept-select">
                <SelectValue placeholder="Semua Departemen" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Semua Departemen</SelectItem>
                {uniqueDepartments.map(d => (
                  <SelectItem key={d} value={d}>{d}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button variant="ghost" size="sm" className="h-8 px-2 text-xs ml-auto" onClick={loadPRs} data-testid="inbox-refresh-btn">
            <RefreshCw size={12} className="mr-1" /> Muat ulang
          </Button>
        </div>

        <div className="space-y-2">
          {prInbox.map(pr => (
            <div key={pr.id}
              className={`flex items-center justify-between py-3 px-4 border rounded-xl cursor-pointer transition-colors ${
                pr.can_approve === false
                  ? 'bg-muted/30 border-border/60 hover:bg-muted/50'
                  : 'bg-amber-100 dark:bg-amber-500/5 border-amber-300 dark:border-amber-500/20 hover:bg-amber-100 dark:bg-amber-500/10'
              }`}
              onClick={() => onSelectPR?.(pr)}
              data-testid={`inbox-item-${pr.request_number}`}>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium truncate">{pr.title}</p>
                  {pr.can_approve === false && (
                    <Badge variant="outline" className="text-[10px] h-4 px-1.5">read-only</Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground truncate">
                  {pr.request_number} · {pr.requested_by_name} · {pr.department || '—'}
                </p>
              </div>
              <div className="text-right flex items-center gap-3 shrink-0">
                <span className="text-sm font-bold">{fmtCurrency(pr.total_estimated)}</span>
                <StatusBadge status={pr.status} configMap={PR_STATUS_CONFIG} />
              </div>
            </div>
          ))}
          {prInbox.length === 0 && (
            <div className="text-center py-12 text-muted-foreground">
              <CheckCheck size={32} className="mx-auto mb-2 opacity-40" />
              <p className="text-sm">
                {inboxScope === 'mine'
                  ? 'Anda belum memiliki request pending.'
                  : inboxScope === 'all'
                    ? 'Tidak ada request menunggu approval.'
                    : 'Tidak ada request yang menunggu persetujuan Anda.'}
              </p>
            </div>
          )}
        </div>
      </TabsContent>
    </Tabs>
  );
}
