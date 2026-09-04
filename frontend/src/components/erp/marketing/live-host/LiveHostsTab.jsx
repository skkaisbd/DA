import { useState, useEffect, useCallback } from 'react';
import {
  Users, Plus, Edit, Trash2, RefreshCw, Search, Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { AccountBadge } from '../AccountBadge';
import { ActiveAccountBar } from '../ActiveAccountBar';
import { useActiveMarketingAccount } from '@/hooks/useActiveMarketingAccount';
import { API, fmtRp } from './utils';
import { StatusBadge, EmploymentTypeBadge } from './Badges';
import AddEditHostModal from './AddEditHostModal';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

export default function LiveHostsTab({ authH }) {
  const [hosts, setHosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [accounts, setAccounts] = useState([]);

  // Shared persistent account context (localStorage)
  const { activeAccount: activeAccountCtx, setActiveAccount: setActiveAccountCtx } = useActiveMarketingAccount();
  const filterAccountId = activeAccountCtx?.id || '';
  const setFilterAccountId = (id) => {
    const acc = accounts.find((a) => a.id === id);
    setActiveAccountCtx(acc || null);
  };

  const [showAddEditModal, setShowAddEditModal] = useState(false);
  const [editingHost, setEditingHost] = useState(null);

  const fetchHosts = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.append('status', statusFilter);
      if (searchQuery) params.append('search', searchQuery);

      const res = await fetch(`${API}/api/marketing/livehost?${params}`, { headers: authH });
      if (res.ok) {
        const data = await res.json();
        setHosts(data);
      }
    } catch (e) {
      toast.error('Gagal memuat data LiveHost');
    } finally {
      setLoading(false);
    }
  }, [authH, statusFilter, searchQuery]);

  const fetchAccounts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/marketing/accounts?status=active`, { headers: authH });
      if (res.ok) {
        const data = await res.json();
        setAccounts(data);
      }
    } catch (e) {}
  }, [authH]);

  useEffect(() => {
    fetchHosts();
    fetchAccounts();
  }, [fetchHosts, fetchAccounts]);

  const handleDelete = async (host) => {
    if (!window.confirm(`Yakin ingin menghapus LiveHost "${host.name}"?`)) return;
    try {
      const res = await fetch(`${API}/api/marketing/livehost/${host.id}`, {
        method: 'DELETE',
        headers: authH,
      });
      if (res.ok) {
        toast.success('LiveHost berhasil dihapus');
        fetchHosts();
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Gagal menghapus LiveHost');
      }
    } catch (e) {
      toast.error('Gagal menghapus LiveHost');
    }
  };

  const displayedHosts = filterAccountId
    ? hosts.filter((h) => (h.assigned_accounts || []).some((a) => a.id === filterAccountId))
    : hosts;

  const { page, setPage, totalPages, total, paged } = useClientPagination(displayedHosts, 10);
  return (
    <div className="space-y-4">
      <ActiveAccountBar
        accounts={accounts}
        activeAccount={accounts.find((a) => a.id === filterAccountId) || null}
        onAccountChange={(acc) => setFilterAccountId(acc ? acc.id : '')}
        hint="Filter LiveHost by akun:"
      />

      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="flex gap-2 w-full sm:w-auto">
          <div className="relative flex-1 sm:w-64">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Cari nama atau email..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 h-9"
              data-testid="search-livehost"
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[130px] h-9" data-testid="filter-status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua Status</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="inactive">Inactive</SelectItem>
              <SelectItem value="on_leave">On Leave</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex gap-2 w-full sm:w-auto">
          <Button variant="outline" size="sm" onClick={fetchHosts} className="h-9" data-testid="refresh-hosts">
            <RefreshCw size={14} className="mr-1.5" />
            Refresh
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setEditingHost(null);
              setShowAddEditModal(true);
            }}
            className="h-9"
            data-testid="add-livehost-btn"
          >
            <Plus size={14} className="mr-1.5" />
            Tambah LiveHost
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 size={28} className="animate-spin text-muted-foreground" />
        </div>
      ) : hosts.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
            <Users size={40} className="text-muted-foreground opacity-40" />
            <p className="font-medium">Belum ada LiveHost</p>
            <p className="text-sm text-muted-foreground">Tambahkan LiveHost pertama untuk mulai scheduling</p>
            <Button size="sm" onClick={() => setShowAddEditModal(true)}>
              <Plus size={14} className="mr-1.5" />
              Tambah LiveHost
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="livehosts-table">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Nama</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Email</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Employment</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Hourly Rate</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Assigned Accounts</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {paged.map((host) => (
                    <tr key={host.id} className="hover:bg-muted/30 transition-colors" data-testid={`host-row-${host.id}`}>
                      <td className="px-4 py-3 font-medium">{host.name}</td>
                      <td className="px-4 py-3 text-muted-foreground">{host.email}</td>
                      <td className="px-4 py-3">
                        <EmploymentTypeBadge type={host.employment_type} />
                      </td>
                      <td className="px-4 py-3 tabular-nums">{fmtRp(host.hourly_rate)}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {(host.assigned_accounts || []).length > 0 ? (
                            host.assigned_accounts.map((a) => {
                              const full = accounts.find((x) => x.id === a.id);
                              return (
                                <AccountBadge
                                  key={a.id}
                                  account={full || { account_name: a.name, platform: 'unknown' }}
                                  size="xs"
                                />
                              );
                            })
                          ) : (
                            <span className="text-xs text-muted-foreground italic">Belum di-assign</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={host.status} />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            onClick={() => {
                              setEditingHost(host);
                              setShowAddEditModal(true);
                            }}
                            data-testid={`edit-host-${host.id}`}
                          >
                            <Edit size={14} />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
                            onClick={() => handleDelete(host)}
                            data-testid={`delete-host-${host.id}`}
                          >
                            <Trash2 size={14} />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
            </div>
          </CardContent>
        </Card>
      )}

      {showAddEditModal && (
        <AddEditHostModal
          host={editingHost}
          accounts={accounts}
          authH={authH}
          onClose={() => {
            setShowAddEditModal(false);
            setEditingHost(null);
          }}
          onSuccess={() => {
            setShowAddEditModal(false);
            setEditingHost(null);
            fetchHosts();
          }}
        />
      )}
    </div>
  );
}
