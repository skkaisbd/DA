/**
 * MarketingWebhooksModule — Phase 1/2: Webhook Events Monitor
 *
 * Monitor dan kelola event webhook dari marketplace (Tokopedia, Shopee, TikTok).
 * Mendukung reprocess event yang gagal dan manual ingest untuk testing.
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  Zap, RefreshCw, CheckCircle2, XCircle, Clock,
  AlertTriangle, Send, ChevronRight, Eye, RotateCcw,
  Filter, Search, Copy, ExternalLink, Table2, LayoutGrid,
} from 'lucide-react';
import { Badge } from '../../ui/badge';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '../../ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../ui/select';
import { Textarea } from '../../ui/textarea';
import { useToast } from '../../../hooks/use-toast';
import WebhookSecurityPanel from './WebhookSecurityPanel';

const API = process.env.REACT_APP_BACKEND_URL || '';

const PLATFORM_COLORS = {
  tokopedia: 'bg-green-100 dark:bg-green-500/15 text-green-700 dark:text-green-400 border-green-400 dark:border-green-500/30',
  shopee:    'bg-orange-100 dark:bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-400 dark:border-orange-500/30',
  tiktok:    'bg-muted dark:bg-zinc-500/15 text-foreground/80 border-border dark:border-zinc-500/30',
  manual:    'bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-400 dark:border-blue-500/30',
};

const PLATFORM_LABELS = {
  tokopedia: '🟢 Tokopedia',
  shopee:    '🟠 Shopee',
  tiktok:    '⚫ TikTok',
  manual:    '🔵 Manual',
};

function StatusBadge({ processed, error }) {
  if (error === 'duplicate') return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-muted dark:bg-zinc-500/20 text-muted-foreground">
      <Copy className="w-3 h-3" /> Duplikat
    </span>
  );
  if (error) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-400">
      <XCircle className="w-3 h-3" /> Error
    </span>
  );
  if (processed) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
      <CheckCircle2 className="w-3 h-3" /> Processed
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400">
      <Clock className="w-3 h-3" /> Pending
    </span>
  );
}

export default function MarketingWebhooksModule({ user, headers }) {
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [filterPlatform, setFilterPlatform] = useState('');
  const [filterProcessed, setFilterProcessed] = useState('');
  const [search, setSearch] = useState('');
  const [skip, setSkip] = useState(0);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [showManualIngest, setShowManualIngest] = useState(false);
  const [manualForm, setManualForm] = useState({ platform: 'tokopedia', payload: '' });
  const [manualSending, setManualSending] = useState(false);
  // F10 (2026-08-13) — tabel sudah ada, yang belum: pengalih tampilan.
  const [view, setView] = useState(() => {
    try { return localStorage.getItem('marketing_webhooks_view') || 'table'; } catch { return 'table'; }
  });
  useEffect(() => {
    try { localStorage.setItem('marketing_webhooks_view', view); } catch { /* diblokir */ }
  }, [view]);
  const { toast } = useToast();
  const authH = useMemo(() => headers || {}, [headers]);

  const LIMIT = 20;

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = { skip, limit: LIMIT };
      if (filterPlatform) params.platform = filterPlatform;
      if (filterProcessed !== '') params.processed = filterProcessed === 'true';

      const [evtRes, statsRes] = await Promise.all([
        axios.get(`${API}/api/marketing/webhooks/events`, { headers: authH, params }),
        axios.get(`${API}/api/marketing/webhooks/stats`, { headers: authH }),
      ]);
      setEvents(evtRes.data?.data || []);
      setTotal(evtRes.data?.total || 0);
      setStats(statsRes.data?.data || []);
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Gagal load data', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [skip, filterPlatform, filterProcessed, authH, toast]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleReprocess = async (eventId) => {
    try {
      await axios.post(`${API}/api/marketing/webhooks/events/${eventId}/reprocess`, {}, { headers: authH });
      toast({ title: 'Berhasil', description: 'Event di-queue untuk reprocess.' });
      fetchData();
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Gagal reprocess', variant: 'destructive' });
    }
  };

  const handleManualIngest = async () => {
    setManualSending(true);
    try {
      let parsedPayload;
      try { parsedPayload = JSON.parse(manualForm.payload); }
      catch { throw new Error('Payload bukan JSON valid.'); }
      const res = await axios.post(
        `${API}/api/marketing/webhooks/manual`,
        { platform: manualForm.platform, event_type: 'order.new', payload: parsedPayload },
        { headers: authH },
      );
      toast({ title: 'Berhasil', description: `Event diterima. ID: ${res.data.event_id}` });
      setShowManualIngest(false);
      setManualForm({ platform: 'tokopedia', payload: '' });
      fetchData();
    } catch (e) {
      toast({ title: 'Error', description: e.message || e.response?.data?.detail || 'Gagal ingest', variant: 'destructive' });
    } finally {
      setManualSending(false);
    }
  };

  const TOKOPEDIA_SAMPLE = JSON.stringify({
    message: "Push Notification Tokopedia",
    message_id: `tokped-test-${Date.now()}`,
    order: {
      order_id: Math.floor(Math.random() * 9000000 + 1000000),
      invoice_ref_num: `INV/TEST/${Date.now()}`,
      order_status: 10,
      buyer: { name: "Test Buyer" },
      total_amount: 150000,
      products: [{ product_id: "SKU-001", name: "Test Product", quantity: 1, subtotal: 150000 }],
      est_start_delivery: new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10),
    },
  }, null, 2);

  const SHOPEE_SAMPLE = JSON.stringify({
    code: "ORDER_STATUS_UPDATE",
    shop_id: 12345,
    data: {
      ordersn: `TEST${Date.now()}`,
      status: "READY_TO_SHIP",
      buyer_username: "test_buyer",
      total_amount: 200000,
      ship_by_date: new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10),
      item_list: [{ item_sku: "SKU-002", item_name: "Test Item", model_quantity_purchased: 2, model_discounted_price: 100000 }],
    },
  }, null, 2);

  const filtered = search
    ? events.filter(e =>
        (e.platform || '').includes(search.toLowerCase()) ||
        (e.event_type || '').includes(search.toLowerCase()) ||
        (e.id || '').includes(search)
      )
    : events;

  return (
    <div className="p-4 md:p-6 space-y-6 text-foreground">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Zap className="text-amber-700 dark:text-amber-400" /> Webhook Events Monitor
          </h2>
          <p className="text-sm text-muted-foreground mt-1">Monitor inbound events dari Tokopedia, Shopee, TikTok Shop</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline" size="sm"
            onClick={() => setShowManualIngest(true)}
            className="border-border text-foreground/80 hover:bg-muted"
            data-testid="btn-manual-ingest"
          >
            <Send className="w-4 h-4 mr-1" /> Test Ingest
          </Button>
          <Button
            variant="outline" size="sm"
            onClick={fetchData}
            disabled={loading}
            className="border-border text-foreground/80 hover:bg-muted"
            data-testid="btn-refresh-webhooks"
          >
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
        </div>
      </div>

      {/* Keamanan HMAC (FASE 19 / AUDIT-2) — sebelumnya ketiga receiver menerima
          tulisan TANPA auth apa pun; panel ini membuat statusnya terlihat di UI. */}
      <WebhookSecurityPanel headers={authH} />

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {stats.length === 0 ? (
          <div className="col-span-4 text-center text-muted-foreground/80 text-sm py-4">Belum ada webhook events</div>
        ) : stats.map(s => (
          <Card key={s.platform} className="bg-card border-border">
            <CardContent className="pt-4 pb-3">
              <div className="text-xs text-muted-foreground mb-1">{PLATFORM_LABELS[s.platform] || s.platform}</div>
              <div className="text-2xl font-bold">{s.total}</div>
              <div className="flex justify-between text-xs text-muted-foreground/80 mt-1">
                <span className="text-emerald-600 dark:text-emerald-400">{s.processed} OK</span>
                <span className={s.errors > 0 ? 'text-red-700 dark:text-red-400' : 'text-muted-foreground/80'}>{s.errors} err</span>
                <span>{s.success_rate}%</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/80" />
          <Input
            placeholder="Cari platform / event type / ID..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-9 bg-card border-border text-sm"
            data-testid="input-webhook-search"
          />
        </div>
        <Select value={filterPlatform} onValueChange={v => { setFilterPlatform(v === 'all' ? '' : v); setSkip(0); }}>
          <SelectTrigger className="w-36 bg-card border-border text-sm" data-testid="select-platform">
            <SelectValue placeholder="Platform" />
          </SelectTrigger>
          <SelectContent className="bg-card border-border">
            <SelectItem value="all">Semua Platform</SelectItem>
            <SelectItem value="tokopedia">Tokopedia</SelectItem>
            <SelectItem value="shopee">Shopee</SelectItem>
            <SelectItem value="tiktok">TikTok</SelectItem>
            <SelectItem value="manual">Manual</SelectItem>
          </SelectContent>
        </Select>
        <Select value={filterProcessed} onValueChange={v => { setFilterProcessed(v === 'all' ? '' : v); setSkip(0); }}>
          <SelectTrigger className="w-32 bg-card border-border text-sm">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent className="bg-card border-border">
            <SelectItem value="all">Semua Status</SelectItem>
            <SelectItem value="true">Processed</SelectItem>
            <SelectItem value="false">Pending/Error</SelectItem>
          </SelectContent>
        </Select>
        <div className="text-xs text-muted-foreground/80">{total} total events</div>
        <div className="flex rounded-md border border-border overflow-hidden ml-auto">
          <button type="button" onClick={() => setView('table')} data-testid="webhooks-view-table"
            className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
              ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
            <Table2 size={12} /> Tabel
          </button>
          <button type="button" onClick={() => setView('grid')} data-testid="webhooks-view-grid"
            className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
              ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
            <LayoutGrid size={12} /> Kartu
          </button>
        </div>
      </div>

      {/* Events Table */}
      <Card className="bg-card border-border">
        <CardContent className="p-0">
          {loading ? (
            <div className="text-center py-10 text-muted-foreground/80">Loading...</div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground/80">
              <Zap className="w-10 h-10 mx-auto mb-2 opacity-30" />
              <p>Belum ada webhook events</p>
              <p className="text-xs mt-1">Klik "Test Ingest" untuk kirim payload sample</p>
            </div>
          ) : view === 'grid' ? (
            <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3" data-testid="webhooks-grid">
              {filtered.map(evt => (
                <div key={evt.id} className="rounded-lg border border-border p-3 space-y-1.5 bg-background">
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded border ${PLATFORM_COLORS[evt.platform] || 'bg-muted-foreground/30 text-foreground/80'}`}>
                      {PLATFORM_LABELS[evt.platform] || evt.platform}
                    </span>
                    <StatusBadge processed={evt.processed} error={evt.error} />
                  </div>
                  <p className="text-[11px] font-mono text-foreground/80">{evt.event_type || '—'}</p>
                  <p className="text-[11px] text-muted-foreground">
                    Order: {evt.normalized_order?.platform_order_id || '—'}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {evt.received_at ? new Date(evt.received_at).toLocaleString('id-ID') : '—'}
                  </p>
                  <div className="flex gap-1 pt-1">
                    <Button variant="ghost" size="sm" className="h-7 px-2 text-xs"
                      onClick={() => setSelectedEvent(evt)}>
                      <Eye className="w-3.5 h-3.5 mr-1" />Detail
                    </Button>
                    {(evt.error && evt.error !== 'duplicate') && (
                      <Button variant="ghost" size="sm"
                        className="h-7 px-2 text-xs text-amber-700 dark:text-amber-400"
                        onClick={() => handleReprocess(evt.id)}>
                        <RotateCcw className="w-3.5 h-3.5 mr-1" />Ulangi
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="webhooks-table">
                <thead>
                  <tr className="border-b border-border text-muted-foreground text-xs">
                    <th className="text-left px-4 py-3">Platform</th>
                    <th className="text-left px-4 py-3">Event Type</th>
                    <th className="text-left px-4 py-3">Status</th>
                    <th className="text-left px-4 py-3">Order ID</th>
                    <th className="text-left px-4 py-3">Received</th>
                    <th className="text-right px-4 py-3">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(evt => (
                    <tr key={evt.id} className="border-b border-border/50 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-0.5 rounded border ${PLATFORM_COLORS[evt.platform] || 'bg-muted-foreground/30 text-foreground/80'}`}>
                          {PLATFORM_LABELS[evt.platform] || evt.platform}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-foreground/80 font-mono text-xs">{evt.event_type || '—'}</td>
                      <td className="px-4 py-3">
                        <StatusBadge processed={evt.processed} error={evt.error} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs font-mono">
                        {evt.normalized_order?.platform_order_id || '—'}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground/80 text-xs">
                        {evt.received_at ? new Date(evt.received_at).toLocaleString('id-ID') : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex gap-1 justify-end">
                          <Button
                            variant="ghost" size="sm"
                            className="h-7 w-7 p-0 hover:bg-muted-foreground/30"
                            onClick={() => setSelectedEvent(evt)}
                            data-testid={`btn-view-event-${evt.id}`}
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </Button>
                          {(evt.error && evt.error !== 'duplicate') && (
                            <Button
                              variant="ghost" size="sm"
                              className="h-7 w-7 p-0 hover:bg-muted-foreground/30 text-amber-700 dark:text-amber-400"
                              onClick={() => handleReprocess(evt.id)}
                              data-testid={`btn-reprocess-${evt.id}`}
                            >
                              <RotateCcw className="w-3.5 h-3.5" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline" size="sm"
          disabled={skip === 0}
          onClick={() => setSkip(Math.max(0, skip - LIMIT))}
          className="border-border text-foreground/80"
        >Prev</Button>
        <span className="text-xs text-muted-foreground/80">Halaman {Math.floor(skip / LIMIT) + 1}</span>
        <Button
          variant="outline" size="sm"
          disabled={skip + LIMIT >= total}
          onClick={() => setSkip(skip + LIMIT)}
          className="border-border text-foreground/80"
        >Next</Button>
      </div>

      {/* Event Detail Dialog */}
      <Dialog open={!!selectedEvent} onOpenChange={o => !o && setSelectedEvent(null)}>
        <DialogContent className="bg-card border-border max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-foreground">
              Event Detail — {PLATFORM_LABELS[selectedEvent?.platform] || selectedEvent?.platform}
            </DialogTitle>
          </DialogHeader>
          {selectedEvent && (
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div><span className="text-muted-foreground/80">ID:</span> <span className="font-mono text-foreground/80">{selectedEvent.id}</span></div>
                <div><span className="text-muted-foreground/80">Event:</span> <span className="text-foreground/80">{selectedEvent.event_type}</span></div>
                <div><span className="text-muted-foreground/80">Status:</span> <StatusBadge processed={selectedEvent.processed} error={selectedEvent.error} /></div>
                <div><span className="text-muted-foreground/80">Received:</span> <span className="text-foreground/80">{selectedEvent.received_at ? new Date(selectedEvent.received_at).toLocaleString('id-ID') : '—'}</span></div>
              </div>
              {selectedEvent.error && (
                <div className="bg-red-100 dark:bg-red-500/10 border border-red-400 dark:border-red-500/30 rounded p-3">
                  <p className="text-xs text-red-700 dark:text-red-400 font-medium">Error:</p>
                  <p className="text-xs text-foreground/80 mt-1">{selectedEvent.error}</p>
                </div>
              )}
              {selectedEvent.normalized_order && (
                <div>
                  <p className="text-xs text-muted-foreground/80 mb-2">Normalized Order:</p>
                  <pre className="bg-card p-3 rounded text-xs text-foreground/80 overflow-x-auto">
                    {JSON.stringify(selectedEvent.normalized_order, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Manual Ingest Dialog */}
      <Dialog open={showManualIngest} onOpenChange={setShowManualIngest}>
        <DialogContent className="bg-card border-border max-w-xl">
          <DialogHeader>
            <DialogTitle className="text-foreground">Test Ingest Webhook Payload</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Platform</label>
              <Select
                value={manualForm.platform}
                onValueChange={v => setManualForm(f => ({ ...f, platform: v }))}
              >
                <SelectTrigger className="bg-muted border-border" data-testid="select-manual-platform">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  <SelectItem value="tokopedia">Tokopedia</SelectItem>
                  <SelectItem value="shopee">Shopee</SelectItem>
                  <SelectItem value="tiktok">TikTok</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <div className="flex justify-between items-center mb-1">
                <label className="text-xs text-muted-foreground">JSON Payload</label>
                <button
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                  onClick={() => {
                    const sample = manualForm.platform === 'shopee' ? SHOPEE_SAMPLE : TOKOPEDIA_SAMPLE;
                    setManualForm(f => ({ ...f, payload: sample }));
                  }}
                >Load Sample</button>
              </div>
              <Textarea
                value={manualForm.payload}
                onChange={e => setManualForm(f => ({ ...f, payload: e.target.value }))}
                placeholder='{"order": {...}}'
                rows={8}
                className="bg-muted border-border font-mono text-xs"
                data-testid="textarea-webhook-payload"
              />
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="ghost" onClick={() => setShowManualIngest(false)}>Batal</Button>
              <Button
                onClick={handleManualIngest}
                disabled={manualSending || !manualForm.payload}
                className="bg-amber-600 hover:bg-amber-700 text-foreground"
                data-testid="btn-submit-manual-ingest"
              >
                {manualSending ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" /> : <Send className="w-4 h-4 mr-1" />}
                Send
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
