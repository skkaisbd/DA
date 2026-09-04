import React, { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import axios from 'axios';
import { CheckCircle, XCircle, Clock, ChevronRight, RefreshCw, User, Calendar, Layers, ExternalLink } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

// Map approval type → module ID untuk link-back
const DOMAIN_MODULE_MAP = {
  leave:             'hr-leave',
  overtime:          'hr-overtime',
  salary_adjustment: 'hr-salary-adjustment',
  material_return:   'prod-material-return',
  purchase_order:    'procurement-po',
  resignation:       'hr-employee',
  expense:           'hr-expense-claims',
  asset_purchase:    'fin-assets',
};

const STATUS_CONFIG = {
  pending:   { label: 'Menunggu',   color: 'text-amber-700 dark:text-amber-400',   bg: 'bg-amber-50 dark:bg-amber-400/10',   border: 'border-amber-300 dark:border-amber-400/20',   icon: Clock },
  approved:  { label: 'Disetujui',  color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-400/10', border: 'border-emerald-300 dark:border-emerald-400/20', icon: CheckCircle },
  rejected:  { label: 'Ditolak',    color: 'text-red-700 dark:text-red-400',     bg: 'bg-red-50 dark:bg-red-400/10',     border: 'border-red-300 dark:border-red-400/20',     icon: XCircle },
  cancelled: { label: 'Dibatalkan', color: 'text-muted-foreground dark:text-zinc-400',    bg: 'bg-muted dark:bg-zinc-500/10',    border: 'border-border dark:border-zinc-500/20',    icon: XCircle },
};

const TYPE_LABELS = {
  leave: 'Cuti', overtime: 'Lembur', salary_adjustment: 'Penyesuaian Gaji',
  expense: 'Expense Claim', purchase_order: 'Purchase Order',
  material_return: 'Return Material', resignation: 'Resignasi',
  asset_purchase: 'Pembelian Aset',
};

// ── Status Badge ──────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.color} ${cfg.bg} ${cfg.border}`}>
      <Icon size={11} /> {cfg.label}
    </span>
  );
}

// ── Level Timeline (horizontal steps) ────────────────────────────────────────
function LevelTimeline({ levels }) {
  return (
    <div className="flex items-start gap-0">
      {levels.map((lv, i) => {
        const isDone   = lv.status === 'approved';
        const isActive = lv.status === 'pending';
        const isRej    = lv.status === 'rejected' || lv.status === 'skipped';
        return (
          <div key={lv.level} className="flex items-center">
            <div className="flex flex-col items-center">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 ${
                isDone   ? 'bg-emerald-500 border-emerald-500 text-foreground' :
                isActive ? 'bg-amber-400 border-amber-400 text-foreground animate-pulse' :
                isRej    ? 'bg-red-500 border-red-500 text-foreground' :
                           'bg-muted border-border text-muted-foreground dark:text-zinc-400'
              }`}>
                {isDone ? '✓' : isRej ? '✗' : lv.level}
              </div>
              <span className="text-[10px] text-muted-foreground/60 dark:text-zinc-500 mt-0.5 max-w-[60px] text-center leading-tight">{lv.label}</span>
            </div>
            {i < levels.length - 1 && (
              <div className={`w-8 h-0.5 mb-4 ${
                isDone ? 'bg-emerald-500' : isRej ? 'bg-red-500' : 'bg-muted-foreground/30'
              }`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Approval Card ─────────────────────────────────────────────────────────────
function ApprovalCard({ item, onApprove, onReject, onView, isManager, onModuleChange }) {
  const [note, setNote]       = useState('');
  const [acting, setActing]   = useState(false);
  const [showNote, setShowNote] = useState(false);

  const handleAction = async (action) => {
    setActing(true);
    await (action === 'approve' ? onApprove : onReject)(item.id, note);
    setActing(false);
    setShowNote(false);
    setNote('');
  };

  return (
    <div className="bg-foreground/5 border border-foreground/10 rounded-xl p-4 hover:border-foreground/20 transition-all" data-testid={`approval-card-${item.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium px-2 py-0.5 rounded bg-muted text-foreground/80 border border-foreground/10">
              {TYPE_LABELS[item.type] || item.type}
            </span>
            <StatusBadge status={item.status} />
            {item.meta?.priority === 'urgent' && (
              <span className="text-xs font-bold text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-400/10 px-2 py-0.5 rounded border border-red-300 dark:border-red-400/20">URGENT</span>
            )}
          </div>
          <h3 className="font-semibold text-foreground mt-1.5 text-sm leading-tight">{item.subject || item.ref_code}</h3>
          <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground/60 dark:text-zinc-500">
            <span className="flex items-center gap-1"><User size={11} />{item.requester_name}</span>
            <span className="flex items-center gap-1"><Calendar size={11} />{new Date(item.created_at).toLocaleDateString('id-ID')}</span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {onModuleChange && DOMAIN_MODULE_MAP[item.type] && (
            <button
              onClick={() => onModuleChange(DOMAIN_MODULE_MAP[item.type])}
              title="Buka di Modul Terkait"
              data-testid={`approval-openmodule-${item.id}`}
              className="p-1.5 text-blue-600 dark:text-blue-400 hover:text-blue-600 dark:text-blue-300 rounded hover:bg-blue-50 dark:bg-blue-400/10"
            >
              <ExternalLink size={14} />
            </button>
          )}
          <button onClick={() => onView(item)} data-testid={`approval-view-${item.id}`} className="p-1.5 text-muted-foreground/60 dark:text-zinc-400 hover:text-foreground rounded hover:bg-foreground/5">
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {item.levels?.length > 0 && (
        <div className="mt-3 pt-3 border-t border-foreground/5">
          <p className="text-[10px] text-muted-foreground/60 mb-1.5">Alur Persetujuan</p>
          <LevelTimeline levels={item.levels} currentLevel={item.current_level} />
        </div>
      )}

      {isManager && item.status === 'pending' && (
        <div className="mt-3 pt-3 border-t border-foreground/5">
          {showNote && (
            <textarea
              value={note} onChange={e => setNote(e.target.value)}
              placeholder="Catatan (opsional)..."
              data-testid={`approval-note-${item.id}`}
              className="w-full text-xs bg-foreground/5 border border-foreground/10 rounded-lg p-2 resize-none focus:outline-none focus:border-blue-500/50 text-foreground placeholder-muted-foreground mb-2"
              rows={2}
            />
          )}
          <div className="flex gap-2">
            <button
              onClick={() => setShowNote(!showNote)} disabled={acting}
              data-testid={`approval-note-toggle-${item.id}`}
              className="text-xs text-muted-foreground/60 dark:text-zinc-400 hover:text-foreground px-2 py-1 rounded border border-foreground/10 hover:bg-foreground/5"
            >
              {showNote ? 'Tutup' : 'Catatan'}
            </button>
            <button onClick={() => handleAction('reject')} disabled={acting}
              data-testid={`approval-reject-${item.id}`}
              className="flex-1 flex items-center justify-center gap-1 text-xs font-medium text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-400/10 hover:bg-red-50 dark:bg-red-400/20 px-3 py-1.5 rounded-lg border border-red-300 dark:border-red-400/20 disabled:opacity-50">
              <XCircle size={13} /> Tolak
            </button>
            <button onClick={() => handleAction('approve')} disabled={acting}
              data-testid={`approval-approve-${item.id}`}
              className="flex-1 flex items-center justify-center gap-1 text-xs font-medium text-foreground bg-emerald-600 hover:bg-emerald-500 px-3 py-1.5 rounded-lg disabled:opacity-50">
              {acting ? <RefreshCw size={13} className="animate-spin" /> : <CheckCircle size={13} />}
              Setujui
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Detail Modal ──────────────────────────────────────────────────────────────
function DetailModal({ item, onClose, onApprove, onReject, isManager, onModuleChange }) {
  const [note, setNote]     = useState('');
  const [acting, setActing] = useState(false);
  if (!item) return null;

  const handleAction = async (action) => {
    setActing(true);
    await (action === 'approve' ? onApprove : onReject)(item.id, note);
    setActing(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/50 p-4">
      <div className="bg-card border border-foreground/10 rounded-2xl w-full max-w-lg max-h-[85vh] flex flex-col shadow-2xl" data-testid="approval-detail-modal">
        {/* Modal header */}
        <div className="flex items-center justify-between p-5 border-b border-foreground/10">
          <div>
            <h2 className="text-base font-semibold text-foreground">{item.subject}</h2>
            <p className="text-xs text-muted-foreground/60 dark:text-zinc-500 mt-0.5">{item.ref_code} • {item.chain_name}</p>
          </div>
          <div className="flex items-center gap-1">
            {onModuleChange && DOMAIN_MODULE_MAP[item.type] && (
              <button
                onClick={() => { onClose(); onModuleChange(DOMAIN_MODULE_MAP[item.type]); }}
                data-testid="approval-detail-openentity"
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-400/10 hover:bg-blue-50 dark:bg-blue-400/20 rounded-lg border border-blue-300 dark:border-blue-400/20 mr-1"
              >
                <ExternalLink size={12} /> Lihat Entitas Asli
              </button>
            )}
            <button onClick={onClose} data-testid="approval-detail-close" className="p-2 text-muted-foreground/60 dark:text-zinc-400 hover:text-foreground rounded-lg hover:bg-foreground/5">✕</button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Meta */}
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><p className="text-xs text-muted-foreground/60 dark:text-zinc-500">Tipe</p><p className="font-medium text-foreground">{TYPE_LABELS[item.type] || item.type}</p></div>
            <div><p className="text-xs text-muted-foreground/60 dark:text-zinc-500">Status</p><StatusBadge status={item.status} /></div>
            <div><p className="text-xs text-muted-foreground/60 dark:text-zinc-500">Pemohon</p><p className="font-medium text-foreground">{item.requester_name}</p></div>
            <div><p className="text-xs text-muted-foreground/60 dark:text-zinc-500">Tanggal</p><p className="font-medium text-foreground">{new Date(item.created_at).toLocaleDateString('id-ID')}</p></div>
          </div>

          {/* Level detail */}
          <div>
            <p className="text-xs text-muted-foreground/60 dark:text-zinc-500 mb-2">Alur Persetujuan ({item.current_level}/{item.max_level})</p>
            <div className="space-y-2">
              {item.levels?.map(lv => (
                <div key={lv.level} className={`flex items-center gap-3 p-2.5 rounded-lg border ${
                  lv.status === 'approved' ? 'bg-emerald-50 dark:bg-emerald-400/5 border-emerald-400/15' :
                  lv.status === 'pending'  ? 'bg-amber-50 dark:bg-amber-400/10 border-amber-300 dark:border-amber-400/20' :
                  lv.status === 'rejected' ? 'bg-red-50 dark:bg-red-400/5 border-red-400/15' :
                  'bg-foreground/5 border-foreground/5'
                }`}>
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                    lv.status === 'approved' ? 'bg-emerald-500 text-foreground' :
                    lv.status === 'pending'  ? 'bg-amber-400 text-foreground' :
                    lv.status === 'rejected' ? 'bg-red-500 text-foreground' :
                    'bg-muted-foreground/30 text-muted-foreground dark:text-zinc-400'
                  }`}>{lv.status === 'approved' ? '✓' : lv.status === 'rejected' ? '✗' : lv.level}</div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-foreground">{lv.label}</p>
                    {lv.approver_name && <p className="text-[11px] text-muted-foreground/60 dark:text-zinc-500">{lv.approver_name}</p>}
                    {lv.note && <p className="text-[11px] text-muted-foreground/60 dark:text-zinc-500 italic">&ldquo;{lv.note}&rdquo;</p>}
                  </div>
                  {lv.actioned_at && <span className="text-[10px] text-muted-foreground/60">{new Date(lv.actioned_at).toLocaleDateString('id-ID')}</span>}
                </div>
              ))}
            </div>
          </div>

          {item.meta && Object.keys(item.meta).length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground/60 dark:text-zinc-500 mb-1">Data Tambahan</p>
              <pre className="text-xs bg-foreground/5 border border-foreground/10 rounded-lg p-2 overflow-x-auto text-foreground/80">{JSON.stringify(item.meta, null, 2)}</pre>
            </div>
          )}
        </div>

        {isManager && item.status === 'pending' && (
          <div className="p-5 border-t border-foreground/10">
            <textarea
              value={note} onChange={e => setNote(e.target.value)}
              placeholder="Catatan (opsional)..."
              data-testid="approval-detail-note"
              className="w-full text-sm bg-foreground/5 border border-foreground/10 rounded-xl p-3 resize-none focus:outline-none focus:border-blue-500/50 text-foreground placeholder-muted-foreground mb-3"
              rows={2}
            />
            <div className="flex gap-2">
              <button onClick={() => handleAction('reject')} disabled={acting}
                data-testid="approval-detail-reject"
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-400/10 hover:bg-red-50 dark:bg-red-400/20 border border-red-300 dark:border-red-400/20 disabled:opacity-50">
                <XCircle size={15} /> Tolak
              </button>
              <button onClick={() => handleAction('approve')} disabled={acting}
                data-testid="approval-detail-approve"
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium text-foreground bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50">
                {acting ? <RefreshCw size={15} className="animate-spin" /> : <CheckCircle size={15} />} Setujui
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Module ───────────────────────────────────────────────────────────────
export default function MultiLevelApprovalModule({ user, onModuleChange }) {
  const [requests, setRequests]       = useState([]);
  const [myPending, setMyPending]     = useState([]);
  const [summary, setSummary]         = useState(null);
  const [chains, setChains]           = useState([]);
  const [loading, setLoading]         = useState(true);
  const [tab, setTab]                 = useState('pending');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterType, setFilterType]   = useState('');
  const [selectedItem, setSelectedItem] = useState(null);
  const token   = localStorage.getItem('erp_token');
  const headers = { Authorization: `Bearer ${token}` };
  const isManager = ['superadmin','admin','owner','manager','hr'].includes((user?.role||'').toLowerCase());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pendRes, allRes, sumRes, chainRes] = await Promise.all([
        axios.get(`${API}/api/approvals/pending`,  { headers }),
        axios.get(`${API}/api/approvals/requests`, { headers, params: { status: filterStatus || undefined, type: filterType || undefined } }),
        axios.get(`${API}/api/approvals/summary`,  { headers }),
        axios.get(`${API}/api/approvals/chains`,   { headers }),
      ]);
      setMyPending(pendRes.data?.data  || []);
      setRequests(allRes.data?.data    || []);
      setSummary(sumRes.data?.data     || null);
      setChains(chainRes.data?.data    || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [filterStatus, filterType]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  const handleApprove = async (id, note) => { await axios.post(`${API}/api/approvals/requests/${id}/approve`, { note }, { headers }); load(); };
  const handleReject  = async (id, note) => { await axios.post(`${API}/api/approvals/requests/${id}/reject`,  { note }, { headers }); load(); };

  const displayItems = tab === 'pending' ? myPending : requests;

  const SEL = 'bg-foreground/5 border border-foreground/10 text-foreground text-sm rounded-lg px-3 py-1.5 focus:outline-none [&>option]:bg-card';

  return (
    <div className="p-4 md:p-6 space-y-5" data-testid="multi-level-approval-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-base font-bold text-foreground flex items-center gap-2">
            <Layers className="text-blue-600 dark:text-blue-400" size={20} /> Approval Multi-Level
          </h1>
          <p className="text-sm text-muted-foreground/60 dark:text-zinc-500 mt-0.5">Kelola persetujuan bertingkat lintas departemen</p>
        </div>
        <button onClick={load} data-testid="approval-refresh-btn" className="p-2 text-muted-foreground/60 dark:text-zinc-500 hover:text-foreground rounded-lg hover:bg-foreground/5 border border-foreground/10">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="approval-summary">
          {[
            { key: 'my-pending',      label: 'Pending Saya',      val: summary.my_pending_count,                color: 'text-amber-700 dark:text-amber-400',   bg: 'bg-amber-50 dark:bg-amber-400/10',   border: 'border-amber-300 dark:border-amber-400/20' },
            { key: 'total-pending',   label: 'Total Pending',     val: summary.total_pending,                   color: 'text-blue-600 dark:text-blue-400',    bg: 'bg-blue-50 dark:bg-blue-400/10',    border: 'border-blue-300 dark:border-blue-400/20' },
            { key: 'approved-today',  label: 'Disetujui Hari Ini',val: summary.approved_today,                  color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-400/10', border: 'border-emerald-300 dark:border-emerald-400/20' },
            { key: 'active-chains',   label: 'Chain Aktif',       val: chains.filter(c=>c.is_active).length,    color: 'text-purple-600 dark:text-purple-400',  bg: 'bg-purple-50 dark:bg-purple-400/10',  border: 'border-purple-300 dark:border-purple-400/20' },
          ].map(s => (
            <div key={s.key} data-testid={`approval-stat-${s.key}`} className={`${s.bg} border ${s.border} rounded-xl p-3`}>
              <p className={`text-2xl font-bold ${s.color}`}>{s.val ?? 0}</p>
              <p className="text-xs text-muted-foreground/60 dark:text-zinc-500 mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-foreground/5 border border-foreground/10 rounded-xl p-1 w-fit">
        {[
          { key: 'pending', label: 'Perlu Tindakan' },
          { key: 'all',     label: 'Semua Request' },
          { key: 'chains',  label: 'Konfigurasi Chain' },
        ].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            data-testid={`approval-tab-${t.key}`}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t.key ? 'bg-blue-600 text-foreground' : 'text-muted-foreground/60 dark:text-zinc-400 hover:text-foreground hover:bg-foreground/5'
            }`}>
            {t.label}
            {t.key === 'pending' && myPending.length > 0 && (
              <span className="ml-1.5 bg-red-500 text-foreground text-[10px] rounded-full px-1.5 py-0.5">{myPending.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Filter bar */}
      {tab !== 'chains' && (
        <div className="flex gap-2 flex-wrap">
          <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} data-testid="approval-filter-status" className={SEL}>
            <option value="">Semua Status</option>
            <option value="pending">Pending</option>
            <option value="approved">Disetujui</option>
            <option value="rejected">Ditolak</option>
            <option value="cancelled">Dibatalkan</option>
          </select>
          <SmartNativeSelect value={filterType} onChange={e => setFilterType(e.target.value)} data-testid="approval-filter-type" className={SEL}>
            <option value="">Semua Tipe</option>
            {Object.entries(TYPE_LABELS).map(([k,v]) => <option key={k} value={k}>{v}</option>)}
          </SmartNativeSelect>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-muted-foreground/60 dark:text-zinc-500">
          <RefreshCw size={24} className="animate-spin text-blue-600 dark:text-blue-400" />
          <span className="ml-3">Memuat...</span>
        </div>
      ) : tab === 'chains' ? (
        <div className="space-y-3" data-testid="approval-chains-list">
          {chains.map(ch => (
            <div key={ch.id} data-testid={`approval-chain-${ch.id}`} className="bg-foreground/5 border border-foreground/10 rounded-xl p-4 hover:border-foreground/20 transition-all">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium px-2 py-0.5 rounded bg-blue-50 dark:bg-blue-400/10 text-blue-600 dark:text-blue-400 border border-blue-300 dark:border-blue-400/20">
                      {TYPE_LABELS[ch.type] || ch.type}
                    </span>
                    {!ch.is_active && <span className="text-xs text-muted-foreground/60 dark:text-zinc-500">Non-aktif</span>}
                  </div>
                  <h3 className="font-medium text-foreground mt-1">{ch.name}</h3>
                  <div className="flex items-center gap-1 mt-1.5">
                    {ch.levels?.map((lv, i) => (
                      <React.Fragment key={lv.level}>
                        <span className="text-xs px-2 py-0.5 bg-muted rounded text-foreground/80 border border-foreground/10">{lv.label}</span>
                        {i < ch.levels.length - 1 && <ChevronRight size={12} className="text-muted-foreground/60" />}
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ))}
          {chains.length === 0 && (
            <div className="text-center py-10 text-muted-foreground/60 dark:text-zinc-500">
              <Layers size={32} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">
                Belum ada chain.{' '}
                <button
                  onClick={async () => { await axios.post(`${API}/api/approvals/seed-missing-chains`, {}, { headers }); load(); }}
                  data-testid="approval-seed-chains-btn"
                  className="text-blue-600 dark:text-blue-400 hover:text-blue-600 dark:text-blue-300 underline"
                >
                  Seed default chains
                </button>
              </p>
            </div>
          )}
        </div>
      ) : displayItems.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground/60" data-testid="approval-empty-state">
          <CheckCircle size={40} className="mx-auto mb-3 opacity-30" />
          <p className="text-base font-medium text-muted-foreground/60 dark:text-zinc-400">Tidak ada approval yang perlu ditindaklanjuti</p>
          <p className="text-sm mt-1">Semua bersih ✓</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="approval-list">
          {displayItems.map(item => (
            <ApprovalCard
              key={item.id} item={item}
              onApprove={handleApprove} onReject={handleReject}
              onView={setSelectedItem} isManager={isManager}
              onModuleChange={onModuleChange}
            />
          ))}
        </div>
      )}

      {selectedItem && (
        <DetailModal
          item={selectedItem} onClose={() => setSelectedItem(null)}
          onApprove={handleApprove} onReject={handleReject}
          isManager={isManager} onModuleChange={onModuleChange}
        />
      )}
    </div>
  );
}
