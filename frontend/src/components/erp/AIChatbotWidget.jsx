import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { MessageCircle, X, Send, Bot, User, Loader2, RefreshCw, ChevronDown, Sparkles, BookOpen } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { IconButton } from './IconButton';

const API = process.env.REACT_APP_BACKEND_URL;
const FALLBACK_SUGGESTIONS = [
  'Apa saja fitur di portal ini?',
  'Apa arti satuan dasar dan konversi kemasan?',
  'Bagaimana cara ekspor/impor data lewat Excel?',
];

export default function AIChatbotWidget({ headers, user, portal, moduleId }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [ctx, setCtx] = useState(null);
  const [sessionId] = useState(() => `asst-${(user?.id || 'u')?.slice(0, 8)}-${new Date().toISOString().slice(0, 10)}`);
  const bottomRef = useRef(null);

  useEffect(() => { if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, open, loading]);

  const loadContext = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/assistant/context`, { headers, params: { portal: portal || undefined } });
      setCtx(data);
    } catch (e) { setCtx(null); }
  }, [headers, portal]);

  useEffect(() => { if (open) loadContext(); }, [open, loadContext]);

  const sendMessage = async (text) => {
    const msg = (text || input).trim();
    if (!msg || loading) return;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/api/assistant/ask`,
        { question: msg, portal: portal || null, module: moduleId || null, session_id: sessionId }, { headers });
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply, source: data.source, related: data.related || [] }]);
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Maaf, asisten tidak dapat merespons saat ini.', source: 'error' }]);
    } finally { setLoading(false); }
  };

  const suggestions = (ctx?.saran?.length ? ctx.saran : FALLBACK_SUGGESTIONS).slice(0, 4);

  return (
    <>
      <button
        onClick={() => setOpen(o => !o)}
        data-testid="ai-chat-toggle"
        aria-label="Asisten ERP"
        className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-primary shadow-lg flex items-center justify-center hover:scale-105 transition-transform"
      >
        <AnimatePresence mode="wait">
          {open
            ? <motion.div key="x" initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }}><X className="w-6 h-6 text-primary-foreground" /></motion.div>
            : <motion.div key="chat" initial={{ rotate: 90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: -90, opacity: 0 }}><MessageCircle className="w-6 h-6 text-primary-foreground" /></motion.div>
          }
        </AnimatePresence>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className="fixed bottom-24 right-6 z-50 w-80 sm:w-96 shadow-2xl rounded-2xl border bg-background overflow-hidden"
            data-testid="ai-chat-window"
          >
            <div className="bg-primary px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <Bot className="w-5 h-5 text-primary-foreground flex-shrink-0" />
                <div className="min-w-0">
                  <div className="font-semibold text-primary-foreground text-sm truncate" data-testid="ai-chat-title">
                    {ctx?.assistant_name || 'Asisten ERP CV. Dewi Aditya'}
                  </div>
                  {ctx?.portal_label && (
                    <div className="text-[11px] text-primary-foreground/70 truncate" data-testid="ai-chat-portal">
                      Konteks: {ctx.portal_label}
                    </div>
                  )}
                </div>
              </div>
              <div className="flex gap-1 flex-shrink-0">
                <IconButton label="Bersihkan percakapan" onClick={() => setMessages([])} className="text-primary-foreground/70 hover:text-primary-foreground p-1" data-testid="ai-chat-clear"><RefreshCw className="w-3.5 h-3.5" /></IconButton>
                <IconButton label="Tutup asisten" onClick={() => setOpen(false)} className="text-primary-foreground/70 hover:text-primary-foreground p-1" data-testid="ai-chat-close"><ChevronDown className="w-4 h-4" /></IconButton>
              </div>
            </div>

            <ScrollArea className="h-80">
              <div className="p-3 space-y-3">
                {messages.length === 0 && (
                  <div className="space-y-2" data-testid="ai-chat-welcome">
                    <div className="flex items-start gap-2">
                      <Bot className="w-6 h-6 text-primary mt-0.5 flex-shrink-0" />
                      <div className="bg-muted rounded-xl rounded-tl-sm p-3 text-sm">
                        {ctx?.ringkasan
                          ? `Halo! Saya bisa menjelaskan cara kerja ${ctx.portal_label}. ${ctx.total_fitur > 0 ? `Ada ${ctx.total_fitur} modul di sini.` : ''}`
                          : 'Halo! Tanyakan apa saja tentang cara kerja sistem ERP ini.'}
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground px-2 pt-1">Pertanyaan yang sering diajukan:</p>
                    {suggestions.map(s => (
                      <button key={s} onClick={() => sendMessage(s)} data-testid="ai-chat-suggestion"
                        className="text-xs bg-muted/50 hover:bg-muted px-3 py-1.5 rounded-lg text-left w-full transition-colors">{s}</button>
                    ))}
                  </div>
                )}

                {messages.map((msg, i) => (
                  <div key={i} className="space-y-1.5">
                    <div className={`flex items-start gap-2 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                      {msg.role === 'assistant'
                        ? <Bot className="w-6 h-6 text-primary mt-0.5 flex-shrink-0" />
                        : <User className="w-6 h-6 text-muted-foreground mt-0.5 flex-shrink-0" />}
                      <div className={`max-w-[82%] rounded-xl p-3 text-sm whitespace-pre-wrap ${
                        msg.role === 'user' ? 'bg-primary text-primary-foreground rounded-tr-sm' : 'bg-muted rounded-tl-sm'
                      }`} data-testid={msg.role === 'user' ? 'ai-chat-user-msg' : 'ai-chat-bot-msg'}>
                        {msg.content}
                      </div>
                    </div>
                    {msg.role === 'assistant' && msg.source && msg.source !== 'error' && (
                      <div className="flex items-center gap-1 pl-8 text-[11px] text-muted-foreground" data-testid="ai-chat-source">
                        {msg.source === 'ai'
                          ? <><Sparkles className="w-3 h-3" /> Dijawab AI</>
                          : <><BookOpen className="w-3 h-3" /> Panduan sistem</>}
                      </div>
                    )}
                    {msg.role === 'assistant' && msg.related?.length > 0 && (
                      <div className="pl-8 space-y-1">
                        {msg.related.slice(0, 2).map(r => (
                          <button key={r} onClick={() => sendMessage(r)} data-testid="ai-chat-related"
                            className="text-[11px] text-primary hover:underline block text-left">→ {r}</button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}

                {loading && (
                  <div className="flex items-start gap-2">
                    <Bot className="w-6 h-6 text-primary mt-0.5" />
                    <div className="bg-muted rounded-xl rounded-tl-sm p-3"><Loader2 className="w-4 h-4 animate-spin text-muted-foreground" /></div>
                  </div>
                )}
                <div ref={bottomRef} />
              </div>
            </ScrollArea>

            <div className="border-t p-3 flex gap-2">
              <Input
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                placeholder="Tanya cara kerja sistem…"
                className="text-sm"
                disabled={loading}
                data-testid="ai-chat-input"
              />
              <Button size="icon" onClick={() => sendMessage()} disabled={loading || !input.trim()} data-testid="ai-chat-send">
                <Send className="w-4 h-4" />
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
