import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import { MessageSquare, Send, Users, Star, Loader2, ThumbsUp, Eye, EyeOff } from 'lucide-react';
import { IconButton } from '../IconButton';

const CATEGORY_LABEL = {
  teamwork: 'Teamwork',
  communication: 'Komunikasi',
  quality: 'Kualitas Kerja',
  leadership: 'Kepemimpinan',
  general: 'Umum',
};

const CATEGORY_COLOR = {
  teamwork: '#10b981',
  communication: '#3b82f6',
  quality: '#f59e0b',
  leadership: '#ef4444',
  general: '#64748b',
};

export default function PeerFeedbackModule({ token }) {
  const [activeTab, setActiveTab] = useState('received');
  const [receivedFeedback, setReceivedFeedback] = useState([]);
  const [givenFeedback, setGivenFeedback] = useState([]);
  const [peers, setPeers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [showSendDialog, setShowSendDialog] = useState(false);
  const [formData, setFormData] = useState({ to_employee_id: '', rating: 5, category: 'general', message: '', is_anonymous: false });
  const [avgRating, setAvgRating] = useState(0);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchReceived = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/peer-feedback/received`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setReceivedFeedback(data?.data || []);
      setAvgRating(data?.metadata?.avg_rating || 0);
    } catch (e) {
      toast.error(`Gagal memuat feedback: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  const fetchGiven = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/peer-feedback/given`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setGivenFeedback(data?.data || []);
    } catch (e) {
      toast.error(`Gagal memuat feedback: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  const fetchPeers = useCallback(async () => {
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/peers`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setPeers(data?.data || []);
    } catch (e) {
      console.error('Peers fetch failed:', e);
    }
  }, [headers]);

  useEffect(() => {
    fetchReceived();
    fetchGiven();
    fetchPeers();
  }, [fetchReceived, fetchGiven, fetchPeers]);

  const handleSend = async () => {
    if (!formData.to_employee_id || !formData.message.trim()) {
      toast.error('Pilih penerima dan tulis pesan');
      return;
    }
    setSending(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/peer-feedback`, {
        method: 'POST',
        headers,
        body: JSON.stringify(formData),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Feedback berhasil dikirim!');
      setShowSendDialog(false);
      setFormData({ to_employee_id: '', rating: 5, category: 'general', message: '', is_anonymous: false });
      fetchGiven();
      fetchReceived();
    } catch (e) {
      toast.error(`Gagal mengirim feedback: ${e.message}`);
    } finally {
      setSending(false);
    }
  };

  const renderStars = (rating) => {
    return Array.from({ length: 5 }).map((_, i) => (
      <Star key={i} className={`w-4 h-4 ${i < rating ? 'fill-amber-500 text-amber-500' : 'text-foreground/80'}`} />
    ));
  };

  return (
    <div className="space-y-6 p-6" data-testid="peer-feedback-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center">
            <MessageSquare className="w-5 h-5 text-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Peer Feedback</h1>
            <p className="text-sm text-muted-foreground">Berikan dan terima feedback dari rekan kerja</p>
          </div>
        </div>
        <Button onClick={() => setShowSendDialog(true)}>
          <Send className="w-4 h-4 mr-2" /> Kirim Feedback
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <GlassCard className="p-5 flex items-start gap-4">
          <div className="w-12 h-12 rounded-2xl flex items-center justify-center shrink-0" style={{ background: '#8b5cf620', border: '1px solid #8b5cf635' }}>
            <ThumbsUp className="w-6 h-6 text-purple-500" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground mb-0.5">Feedback Diterima</p>
            <p className="text-2xl font-bold text-foreground leading-none">{receivedFeedback.length}</p>
          </div>
        </GlassCard>
        <GlassCard className="p-5 flex items-start gap-4">
          <div className="w-12 h-12 rounded-2xl flex items-center justify-center shrink-0" style={{ background: '#f59e0b20', border: '1px solid #f59e0b35' }}>
            <Star className="w-6 h-6 text-amber-500" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground mb-0.5">Rata-rata Rating</p>
            <p className="text-2xl font-bold text-foreground leading-none">{avgRating.toFixed(1)}</p>
          </div>
        </GlassCard>
        <GlassCard className="p-5 flex items-start gap-4">
          <div className="w-12 h-12 rounded-2xl flex items-center justify-center shrink-0" style={{ background: '#3b82f620', border: '1px solid #3b82f635' }}>
            <Send className="w-6 h-6 text-blue-500" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground mb-0.5">Feedback Diberikan</p>
            <p className="text-2xl font-bold text-foreground leading-none">{givenFeedback.length}</p>
          </div>
        </GlassCard>
      </div>

      {/* Tabs */}
      <GlassCard className="p-1">
        <div className="flex gap-1">
          <button
            onClick={() => setActiveTab('received')}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'received' ? 'bg-[var(--glass-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Feedback Diterima
          </button>
          <button
            onClick={() => setActiveTab('given')}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'given' ? 'bg-[var(--glass-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Feedback Diberikan
          </button>
        </div>
      </GlassCard>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : activeTab === 'received' ? (
        <GlassCard className="p-6">
          {receivedFeedback.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-center">
              <MessageSquare className="w-12 h-12 text-muted-foreground/40 mb-2" />
              <p className="text-sm text-muted-foreground">Belum ada feedback yang diterima</p>
            </div>
          ) : (
            <div className="space-y-4">
              {receivedFeedback.map(fb => {
                const catColor = CATEGORY_COLOR[fb.category] || CATEGORY_COLOR.general;
                return (
                  <div key={fb.id} className="p-4 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-2">
                        {fb.is_anonymous ? <EyeOff className="w-4 h-4 text-muted-foreground" /> : <Users className="w-4 h-4 text-blue-500" />}
                        <span className="text-sm font-semibold text-foreground">{fb.from_employee_name}</span>
                      </div>
                      <Badge variant="outline" style={{ borderColor: catColor, color: catColor }}>
                        {CATEGORY_LABEL[fb.category]}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-1 mb-2">{renderStars(fb.rating)}</div>
                    <p className="text-sm text-muted-foreground leading-relaxed mb-2">{fb.message}</p>
                    <p className="text-xs text-muted-foreground">{new Date(fb.created_at).toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' })}</p>
                  </div>
                );
              })}
            </div>
          )}
        </GlassCard>
      ) : (
        <GlassCard className="p-6">
          {givenFeedback.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-center">
              <Send className="w-12 h-12 text-muted-foreground/40 mb-2" />
              <p className="text-sm text-muted-foreground">Belum ada feedback yang diberikan</p>
            </div>
          ) : (
            <div className="space-y-4">
              {givenFeedback.map(fb => {
                const catColor = CATEGORY_COLOR[fb.category] || CATEGORY_COLOR.general;
                return (
                  <div key={fb.id} className="p-4 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Send className="w-4 h-4 text-green-500" />
                        <span className="text-sm font-semibold text-foreground">Untuk: {fb.to_employee_name}</span>
                      </div>
                      <Badge variant="outline" style={{ borderColor: catColor, color: catColor }}>
                        {CATEGORY_LABEL[fb.category]}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-1 mb-2">{renderStars(fb.rating)}</div>
                    <p className="text-sm text-muted-foreground leading-relaxed mb-2">{fb.message}</p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{new Date(fb.created_at).toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' })}</span>
                      {fb.is_anonymous && <Badge variant="secondary" className="text-xs">Anonim</Badge>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </GlassCard>
      )}

      {/* Send Dialog */}
      <Dialog open={showSendDialog} onOpenChange={setShowSendDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Kirim Peer Feedback</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Kepada *</Label>
              <Select value={formData.to_employee_id} onValueChange={v => setFormData({ ...formData, to_employee_id: v })}>
                <SelectTrigger>
                  <SelectValue placeholder="Pilih rekan kerja..." />
                </SelectTrigger>
                <SelectContent>
                  {peers.map(p => (
                    <SelectItem key={p.id || p.employee_code} value={p.id || p.employee_code}>
                      {p.name} - {p.department} ({p.job_title})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Rating *</Label>
              <div className="flex items-center gap-2">
                {[1, 2, 3, 4, 5].map(r => (
                  <button
                    key={r}
                    onClick={() => setFormData({ ...formData, rating: r })}
                    className="focus:outline-none"
                  >
                    <Star className={`w-8 h-8 transition-colors ${r <= formData.rating ? 'fill-amber-500 text-amber-500' : 'text-foreground/80 hover:text-amber-600 dark:text-amber-300'}`} />
                  </button>
                ))}
              </div>
            </div>
            <div>
              <Label>Kategori</Label>
              <Select value={formData.category} onValueChange={v => setFormData({ ...formData, category: v })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(CATEGORY_LABEL).map(([k, v]) => (
                    <SelectItem key={k} value={k}>{v}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Pesan Feedback *</Label>
              <Textarea
                placeholder="Tulis feedback yang konstruktif dan membangun..."
                value={formData.message}
                onChange={e => setFormData({ ...formData, message: e.target.value })}
                rows={4}
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={formData.is_anonymous} onCheckedChange={v => setFormData({ ...formData, is_anonymous: v })} />
              <Label className="cursor-pointer">Kirim sebagai anonim</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSendDialog(false)}>Batal</Button>
            <Button onClick={handleSend} disabled={sending}>
              {sending ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Mengirim...</> : <><Send className="w-4 h-4 mr-2" /> Kirim</>}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
