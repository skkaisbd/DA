import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Loader2, Bell, BellOff, Check } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const API = process.env.REACT_APP_BACKEND_URL;

export default function PortalSayaNotifikasi({ user, headers }) {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      // Phase 3.3C: Use unified SSOT endpoint
      const [listRes, statsRes] = await Promise.all([
        axios.get(`${API}/api/notifications/unified?limit=50`, { headers }),
        axios.get(`${API}/api/notifications/unified/stats`, { headers }),
      ]);
      
      setData({
        items: listRes.data.items || [],
        unread: statsRes.data.total_unread || 0,
      });
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const markRead = async (id) => {
    try {
      // Phase 3.3C: Use unified endpoint
      await axios.post(`${API}/api/notifications/unified/${id}/mark-read`, {}, { headers });
      setData(prev => ({
        ...prev,
        items: prev.items.map(n => n.id === id ? { ...n, read: true } : n),
        unread: Math.max(0, (prev.unread || 0) - 1),
      }));
    } catch (e) {
      toast({ title: 'Gagal menandai.', variant: 'destructive' });
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center py-24"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>
  );

  const items = data?.items || [];

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <Bell className="w-5 h-5" /> Notifikasi Saya
        </h2>
        {data?.unread > 0 && (
          <Badge className="bg-red-100 text-red-700 border-red-200">{data.unread} Belum Dibaca</Badge>
        )}
      </div>

      {items.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <BellOff className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>Tidak ada notifikasi saat ini.</p>
        </div>
      )}

      <div className="space-y-2">
        {items.map(n => (
          <Card
            key={n.id}
            data-testid={`notif-${n.id}`}
            className={`transition-all ${!n.read ? 'border-primary/30 bg-primary/5' : 'opacity-70'}`}
          >
            <CardContent className="pt-4 pb-3 flex items-start gap-3">
              <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${!n.read ? 'bg-primary' : 'bg-muted'}`} />
              <div className="flex-1 min-w-0">
                <p className={`text-sm ${!n.read ? 'font-semibold' : 'font-medium'}`}>{n.title || n.message}</p>
                {n.body && <p className="text-xs text-muted-foreground mt-0.5">{n.body}</p>}
                <p className="text-xs text-muted-foreground mt-1">{n.created_at?.slice(0, 16).replace('T', ' ')}</p>
              </div>
              {!n.read && (
                <Button
                  data-testid={`btn-read-${n.id}`}
                  variant="ghost" size="icon" className="h-7 w-7 text-primary"
                  onClick={() => markRead(n.id)}
                >
                  <Check className="w-4 h-4" />
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
