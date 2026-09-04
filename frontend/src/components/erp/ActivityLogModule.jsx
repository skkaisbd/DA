
import { useState, useEffect } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { RefreshCw, Filter, Activity, Search as SearchIcon, Calendar } from 'lucide-react';

const ACTION_COLORS = {
  Create: 'bg-emerald-100 text-emerald-700',
  Update: 'bg-primary/15 text-primary',
  Delete: 'bg-red-100 text-red-700',
  Login: 'bg-purple-100 text-purple-700',
  'Auto Generate': 'bg-amber-100 text-amber-700',
};

const MODULE_ICONS = {
  'Production PO': '📋',
  'Work Order': '🏭',
  'Production Progress': '📈',
  'Garments': '👔',
  'Products': '📦',
  'Invoice': '🧾',
  'Payment': '💰',
  'User Management': '👤',
  'Auth': '🔐',
};

export default function ActivityLogModule({ token }) {
  const [logs, setLogs] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterModule, setFilterModule] = useState('');
  const [filterUser, setFilterUser] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [searchText, setSearchText] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const modules = [...new Set(logs.map(l => l.module))];
  const actions = [...new Set(logs.map(l => l.action))];

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchLogs(); fetchUsers(); /* eslint-disable-next-line */ }, []);

  const fetchLogs = async () => {
    setLoading(true);
    const params = new URLSearchParams({ limit: '500' });
    if (filterModule) params.append('module', filterModule);
    if (filterUser) params.append('user_id', filterUser);
    const url = `/api/activity-logs?${params}`;
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    const data = await res.json();
    setLogs(Array.isArray(data) ? data : []);
    setLoading(false);
  };

  const fetchUsers = async () => {
    const res = await fetch('/api/users', { headers: { Authorization: `Bearer ${token}` } });
    const data = await res.json();
    setUsers(Array.isArray(data) ? data : []);
  };

  // Client-side filters on top of server-side
  const filtered = logs.filter(l => {
    if (filterAction && l.action !== filterAction) return false;
    if (searchText) {
      const q = searchText.toLowerCase();
      if (!(`${l.details || ''} ${l.user_name || ''} ${l.module || ''}`.toLowerCase().includes(q))) return false;
    }
    if (dateFrom && new Date(l.timestamp) < new Date(dateFrom)) return false;
    if (dateTo && new Date(l.timestamp) > new Date(dateTo + 'T23:59:59')) return false;
    return true;
  });

  const formatDateTime = (d) => {
    if (!d) return '-';
    return new Date(d).toLocaleString('id-ID', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Log Aktivitas</h1>
          <p className="text-muted-foreground text-sm mt-1">Rekam jejak semua aktivitas sistem</p>
        </div>
        <button onClick={fetchLogs} className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg text-sm hover:bg-[var(--glass-bg)]">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Filter */}
      <div className="flex flex-wrap gap-2 items-center">
        <Filter className="w-4 h-4 text-muted-foreground" />
        <button onClick={() => setFilterModule('')}
          className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${!filterModule ? 'bg-primary text-foreground border-blue-600' : 'border-border text-muted-foreground hover:bg-[var(--glass-bg)]'}`}>
          Semua Modul
        </button>
        {modules.map(m => (
          <button key={m} onClick={() => setFilterModule(m)}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
              filterModule === m ? 'bg-primary text-foreground border-blue-600' : 'border-border text-muted-foreground hover:bg-[var(--glass-bg)]'
            }`}>
            {MODULE_ICONS[m] || '📌'} {m}
          </button>
        ))}
      </div>

      {/* User Filter */}
      <div className="bg-[var(--card-surface)] p-3 rounded-lg border border-border space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <label className="text-sm font-medium text-foreground whitespace-nowrap">Filter User:</label>
          <SmartNativeSelect value={filterUser} onChange={(e) => { setFilterUser(e.target.value); }}
            className="flex-1 min-w-[180px] px-3 py-2 border border-border rounded-lg text-sm">
            <option value="">Semua User</option>
            {users.map(u => <option key={u.id} value={u.id}>{`${u.name} - ${u.email}`}</option>)}
          </SmartNativeSelect>
          <SmartNativeSelect value={filterAction} onChange={(e) => setFilterAction(e.target.value)}
            className="px-3 py-2 border border-border rounded-lg text-sm">
            <option value="">Semua Action</option>
            {actions.map(a => <option key={a} value={a}>{a}</option>)}
          </SmartNativeSelect>
          <button onClick={fetchLogs} className="px-4 py-2 bg-primary text-foreground rounded-lg text-sm hover:brightness-110 whitespace-nowrap">
            Terapkan Filter
          </button>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[220px]">
            <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input type="text" placeholder="Search details, user, module..." value={searchText} onChange={e => setSearchText(e.target.value)}
              className="w-full pl-9 pr-3 py-2 border border-border rounded-lg text-sm" data-testid="activity-log-search" />
          </div>
          <Calendar className="w-4 h-4 text-muted-foreground" />
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="px-3 py-2 border border-border rounded-lg text-sm" />
          <span className="text-xs text-muted-foreground">to</span>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="px-3 py-2 border border-border rounded-lg text-sm" />
          {(searchText || dateFrom || dateTo || filterAction) && (
            <button onClick={() => { setSearchText(''); setDateFrom(''); setDateTo(''); setFilterAction(''); }} className="text-xs text-primary hover:underline">
              Clear filters
            </button>
          )}
        </div>
      </div>


      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { action: 'Create', label: 'Dibuat', color: 'border-l-emerald-500' },
          { action: 'Update', label: 'Diubah', color: 'border-l-blue-500' },
          { action: 'Delete', label: 'Dihapus', color: 'border-l-red-500' },
          { action: 'Login', label: 'Login', color: 'border-l-purple-500' },
        ].map(s => (
          <div key={s.action} className={`bg-[var(--card-surface)] rounded-xl border border-border border-l-4 ${s.color} p-4 shadow-sm`}>
            <p className="text-xs text-muted-foreground">{s.label}</p>
            <p className="text-2xl font-bold text-foreground mt-1">
              {logs.filter(l => l.action === s.action).length}
            </p>
          </div>
        ))}
      </div>

      {/* Log List */}
      <div className="bg-[var(--card-surface)] rounded-xl border border-border shadow-sm">
        <div className="px-5 py-4 border-b border-border">
          <h3 className="font-semibold text-foreground">
            <Activity className="w-4 h-4 inline mr-2 text-primary" />
            Aktivitas Terbaru ({filtered.length})
          </h3>
        </div>
        <div className="divide-y divide-border max-h-[600px] overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">Belum ada aktivitas</div>
          ) : (
            filtered.map(log => (
              <div key={log.id} className="flex items-start gap-4 px-5 py-4 hover:bg-[var(--glass-bg)]">
                <div className="w-9 h-9 rounded-full bg-primary/15 flex items-center justify-center text-sm flex-shrink-0">
                  {MODULE_ICONS[log.module] || <Activity className="w-4 h-4 text-primary" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm text-foreground">{log.user_name}</span>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ACTION_COLORS[log.action] || 'bg-secondary text-muted-foreground'}`}>
                      {log.action}
                    </span>
                    <span className="text-xs text-muted-foreground bg-secondary px-2 py-0.5 rounded">{log.module}</span>
                  </div>
                  <p className="text-sm text-muted-foreground mt-0.5">{log.details}</p>
                </div>
                <div className="text-xs text-muted-foreground whitespace-nowrap flex-shrink-0">
                  {formatDateTime(log.timestamp)}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
