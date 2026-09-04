import { useState, useEffect } from 'react';
import { Bell, Clock, CheckCircle, MessageSquare, X } from 'lucide-react';
import { toast } from 'sonner';
import { apiGet, apiPut } from '../../../lib/api';

export default function VendorReminderInbox({ token, user }) {
  const [reminders, setReminders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [responseText, setResponseText] = useState('');
  const [respondingId, setRespondingId] = useState(null);

  useEffect(() => {
    fetchReminders();
  }, []);

  const fetchReminders = async () => {
    try {
      setReminders(await apiGet('/reminders'));
    } catch (e) {}
    setLoading(false);
  };

  const sendResponse = async (reminderId) => {
    if (!responseText.trim()) { toast.error('Tulis respon terlebih dahulu'); return; }
    try {
      await apiPut(`/reminders/${reminderId}`, { response: responseText });
      setRespondingId(null);
      setResponseText('');
      fetchReminders();
    } catch (e) { toast.error('Error: ' + e.message); }
  };

  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-';
  const pending = reminders.filter(r => r.status === 'pending');
  const responded = reminders.filter(r => r.status !== 'pending');

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-foreground flex items-center gap-2"><Bell className="w-5 h-5 text-emerald-600" /> Inbox Reminder</h2>
          <p className="text-sm text-muted-foreground">Pesan dan reminder dari ERP Admin</p>
        </div>
        <div className="flex items-center gap-2">
          {pending.length > 0 && (
            <span className="px-3 py-1 bg-amber-100 text-amber-700 rounded-full text-xs font-medium">{pending.length} belum dibalas</span>
          )}
        </div>
      </div>

      {loading ? (
        <div className="text-center py-10 text-muted-foreground/70">Memuat...</div>
      ) : reminders.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground/70 bg-card rounded-xl border border-border p-8">
          <Bell className="w-12 h-12 text-muted-foreground/50 mx-auto mb-3" />
          <p className="text-lg font-medium text-muted-foreground">Belum ada reminder</p>
          <p className="text-sm text-muted-foreground/70">Reminder dari admin akan muncul di sini</p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Pending first */}
          {pending.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-amber-700 mb-2 flex items-center gap-1"><Clock className="w-4 h-4" /> Menunggu Respon ({pending.length})</h3>
              <div className="space-y-3">
                {pending.map(r => (
                  <div key={r.id} className="bg-amber-50 border border-amber-200 rounded-xl p-4 shadow-sm">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${r.priority === 'urgent' ? 'bg-red-200 text-red-800' : r.priority === 'high' ? 'bg-amber-200 text-amber-800' : 'bg-blue-200 text-blue-800'}`}>{r.priority === 'urgent' ? 'URGENT' : r.priority === 'high' ? 'HIGH' : 'Normal'}</span>
                          <span className="text-xs text-muted-foreground/70">{fmtDate(r.created_at)}</span>
                        </div>
                        <h4 className="font-semibold text-foreground mt-1">{r.subject}</h4>
                        {r.po_number && <p className="text-xs text-muted-foreground mt-0.5">PO: {r.po_number}</p>}
                        <p className="text-sm text-muted-foreground mt-1">{r.message}</p>
                        <p className="text-xs text-muted-foreground/70 mt-1">Dari: {r.created_by}</p>
                      </div>
                    </div>
                    {respondingId === r.id ? (
                      <div className="mt-3 space-y-2">
                        <textarea value={responseText} onChange={e => setResponseText(e.target.value)} className="w-full border border-amber-300 rounded-lg px-3 py-2 text-sm h-20 resize-none bg-card" placeholder="Tulis respon Anda..." />
                        <div className="flex gap-2">
                          <button onClick={() => sendResponse(r.id)} className="flex items-center gap-1.5 px-4 py-1.5 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700"><MessageSquare className="w-3.5 h-3.5" /> Kirim Respon</button>
                          <button onClick={() => { setRespondingId(null); setResponseText(''); }} className="px-4 py-1.5 text-sm text-muted-foreground border border-border rounded-lg">Batal</button>
                        </div>
                      </div>
                    ) : (
                      <button onClick={() => setRespondingId(r.id)} className="mt-3 flex items-center gap-1.5 px-4 py-1.5 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700"><MessageSquare className="w-3.5 h-3.5" /> Balas</button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* Responded */}
          {responded.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-emerald-700 mb-2 flex items-center gap-1"><CheckCircle className="w-4 h-4" /> Sudah Dibalas ({responded.length})</h3>
              <div className="space-y-3">
                {responded.map(r => (
                  <div key={r.id} className="bg-card border border-emerald-200 rounded-xl p-4 shadow-sm">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-muted-foreground/70">{fmtDate(r.created_at)}</span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-200 text-emerald-800 font-medium">Dibalas</span>
                    </div>
                    <h4 className="font-medium text-foreground/90">{r.subject}</h4>
                    <p className="text-sm text-muted-foreground mt-0.5">{r.message}</p>
                    <div className="mt-2 p-2 bg-emerald-50 rounded-lg border border-emerald-100">
                      <p className="text-sm text-emerald-700">{r.response}</p>
                      <p className="text-[10px] text-muted-foreground/70 mt-1">Dibalas: {fmtDate(r.response_date)}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}


// ─── VENDOR VARIANCE REPORT (OVERPRODUCTION/UNDERPRODUCTION) ────────────────


