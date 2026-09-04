/**
 * Composer — message-input area with:
 *  - File upload (channels only, max 10 MB)
 *  - Rich-text formatting toolbar (bold/italic/code/strike/list)
 *  - Textarea with Enter-to-send / Shift-Enter for newline
 *  - @mention autocomplete popup
 *  - Send button
 *  - Reply preview banner above (when replyTo is set)
 *
 * Owns local UI state: inputText, mentionState, uploadingFile.
 * Communicates with parent via onSend(content, replyTo) and onTyping().
 */
import { useState, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Paperclip, Send, Reply, X } from 'lucide-react';

import { API, apicall } from './utils';

export default function Composer({
  activeView,
  channelMembers,
  replyTo,
  onClearReply,
  token,
  onMessageSent,
  onTyping,
}) {
  const [inputText, setInputText] = useState('');
  const [mentionState, setMentionState] = useState({ active: false, query: '', start: 0 });
  const [uploadingFile, setUploadingFile] = useState(false);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);
  const mentionRef = useRef(null);

  // — File upload (channel only, ≤ 10 MB) —
  const handleFileUpload = useCallback(async (e) => {
    const file = e.target.files?.[0];
    if (!file || !activeView) return;

    if (file.size > 10 * 1024 * 1024) {
      toast.error('Ukuran file maksimal 10 MB');
      return;
    }
    if (activeView.type !== 'channel') {
      toast.error('File attachment hanya support untuk channel saat ini');
      return;
    }

    setUploadingFile(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API}/api/comm/channels/${activeView.id}/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!res.ok) throw new Error('Upload gagal');
      const uploadData = await res.json();

      const body = {
        content: `📎 ${uploadData.file_name}`,
        attachments: [{
          file_url: uploadData.file_url,
          file_name: uploadData.file_name,
          file_size: uploadData.file_size,
          content_type: uploadData.content_type,
        }],
      };
      const msg = await apicall('POST', `/api/comm/channels/${activeView.id}/messages`, token, body);
      if (msg.id) {
        onMessageSent(msg);
        toast.success(`File ${uploadData.file_name} berhasil dikirim`);
      }
    } catch {
      toast.error('Gagal upload file');
    } finally {
      setUploadingFile(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [activeView, token, onMessageSent]);

  // — Send text message —
  const sendMessage = useCallback(async () => {
    const content = inputText.trim();
    if (!content || !activeView) return;
    setInputText('');
    onClearReply?.();
    const body = {
      content,
      reply_to_id: replyTo?.id || null,
      reply_to_preview: replyTo ? `${replyTo.sender_name}: ${replyTo.content?.slice(0, 80)}` : null,
    };
    const path = activeView.type === 'channel'
      ? `/api/comm/channels/${activeView.id}/messages`
      : `/api/comm/conversations/${activeView.otherUserId}/messages`;
    try {
      const msg = await apicall('POST', path, token, body);
      if (msg.id) onMessageSent(msg);
    } catch {
      toast.error('Gagal mengirim pesan');
    }
  }, [inputText, activeView, token, replyTo, onClearReply, onMessageSent]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
    onTyping?.();
  };

  // — Rich-text formatting toolbar —
  const applyFormat = useCallback((type) => {
    const el = inputRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const sel = inputText.slice(start, end);
    let newText = inputText;
    let newCursor = end;
    if (type === 'bold') {
      const wrapped = `**${sel || 'teks'}**`;
      newText = inputText.slice(0, start) + wrapped + inputText.slice(end);
      newCursor = start + (sel ? wrapped.length : 2);
    } else if (type === 'italic') {
      const wrapped = `_${sel || 'teks'}_`;
      newText = inputText.slice(0, start) + wrapped + inputText.slice(end);
      newCursor = start + (sel ? wrapped.length : 1);
    } else if (type === 'code') {
      const wrapped = `\`${sel || 'kode'}\``;
      newText = inputText.slice(0, start) + wrapped + inputText.slice(end);
      newCursor = start + (sel ? wrapped.length : 1);
    } else if (type === 'list') {
      const prefix = (inputText.endsWith('\n') || inputText === '') ? '- ' : '\n- ';
      newText = inputText.slice(0, end) + prefix + inputText.slice(end);
      newCursor = end + prefix.length;
    } else if (type === 'strike') {
      const wrapped = `~~${sel || 'teks'}~~`;
      newText = inputText.slice(0, start) + wrapped + inputText.slice(end);
      newCursor = start + (sel ? wrapped.length : 2);
    }
    setInputText(newText);
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(newCursor, newCursor); });
  }, [inputText]);

  // — @mention detection —
  const onInputChange = (e) => {
    const val = e.target.value;
    setInputText(val);
    const cursor = e.target.selectionStart;
    const textBefore = val.slice(0, cursor);
    const atMatch = textBefore.match(/@([\w\s]*)$/);
    if (atMatch) {
      setMentionState({ active: true, query: atMatch[1], start: textBefore.lastIndexOf('@') });
    } else {
      setMentionState({ active: false, query: '', start: 0 });
    }
  };

  const insertMention = (m) => {
    const before = inputText.slice(0, mentionState.start);
    const after = inputText.slice(mentionState.start + 1 + mentionState.query.length);
    setInputText(before + '@' + m.name + ' ' + after);
    setMentionState({ active: false, query: '', start: 0 });
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  if (!activeView) return null;

  const FORMAT_BUTTONS = [
    { type: 'bold',   label: 'B',  title: 'Bold (**teks**)' },
    { type: 'italic', label: 'I',  title: 'Italic (_teks_)', italic: true },
    { type: 'code',   label: '<>', title: 'Code (`kode`)' },
    { type: 'strike', label: 'S',  title: 'Strikethrough (~~teks~~)', strike: true },
    { type: 'list',   label: '≡',  title: 'Bullet list' },
  ];

  return (
    <>
      {/* Reply preview banner */}
      {replyTo && (
        <div className="mx-4 mb-0 px-3 py-2 bg-muted/50 rounded-t-lg border-l-4 border-primary/60 flex items-center gap-2">
          <Reply size={14} className="text-muted-foreground" />
          <div className="flex-1 min-w-0">
            <span className="text-xs font-medium">{replyTo.sender_name}</span>
            <p className="text-xs text-muted-foreground truncate">{replyTo.content}</p>
          </div>
          <button onClick={onClearReply} className="text-muted-foreground hover:text-foreground">
            <X size={14} />
          </button>
        </div>
      )}

      <div className={`px-4 py-3 bg-[hsl(var(--card))] border-t shrink-0 ${replyTo ? 'rounded-b-none' : ''}`}>
        <div className="flex items-end gap-2 bg-muted/40 rounded-xl border px-3 py-2 relative">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            className="hidden"
            accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.zip"
          />
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 shrink-0"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadingFile || activeView.type !== 'channel'}
            title="Upload file (channel only)"
            data-testid="upload-file-btn"
          >
            <Paperclip size={16} className={uploadingFile ? 'animate-pulse' : ''} />
          </Button>

          {/* Format toolbar */}
          <div className="flex items-center gap-0.5 border-r pr-2 mr-1">
            {FORMAT_BUTTONS.map((btn) => (
              <button
                key={btn.type}
                className="w-6 h-6 flex items-center justify-center text-xs text-muted-foreground hover:text-foreground hover:bg-muted rounded transition-colors"
                title={btn.title}
                onMouseDown={(e) => { e.preventDefault(); applyFormat(btn.type); }}
              >
                <span className={`font-${btn.type === 'bold' ? 'bold' : 'normal'} ${btn.italic ? 'italic' : ''} ${btn.strike ? 'line-through' : ''}`}>
                  {btn.label}
                </span>
              </button>
            ))}
          </div>

          <textarea
            ref={inputRef}
            className="flex-1 bg-transparent resize-none outline-none text-sm min-h-[36px] max-h-32 placeholder:text-muted-foreground"
            placeholder={`Pesan ke ${activeView.type === 'channel' ? '#' + activeView.name : activeView.name}... (@ untuk mention)`}
            value={inputText}
            onChange={onInputChange}
            onKeyDown={handleKeyDown}
            rows={1}
            data-testid="message-input"
          />

          {/* @Mention popup */}
          {mentionState.active && channelMembers.length > 0 && (() => {
            const filtered = channelMembers
              .filter((m) => !m.is_self && m.name.toLowerCase().includes(mentionState.query.toLowerCase()))
              .slice(0, 6);
            if (!filtered.length) return null;
            return (
              <div
                ref={mentionRef}
                className="absolute bottom-full mb-1 left-0 right-0 bg-card border rounded-lg shadow-lg z-50 overflow-hidden"
                style={{ maxHeight: '200px', overflowY: 'auto' }}
              >
                <div className="px-3 py-1.5 bg-muted/50 text-xs text-muted-foreground font-semibold">@ Mention</div>
                {filtered.map((m) => (
                  <div
                    key={m.id}
                    className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-accent transition-colors"
                    onMouseDown={(e) => { e.preventDefault(); insertMention(m); }}
                  >
                    <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center text-xs font-bold flex-shrink-0">
                      {m.name[0]?.toUpperCase()}
                    </div>
                    <div>
                      <p className="text-xs font-medium">{m.name}</p>
                      <p className="text-[10px] text-muted-foreground">{m.position || m.role || ''}</p>
                    </div>
                  </div>
                ))}
              </div>
            );
          })()}

          <Button
            size="sm"
            className="rounded-lg h-8 px-3 shrink-0"
            onClick={sendMessage}
            disabled={!inputText.trim()}
            data-testid="send-message-btn"
          >
            <Send size={14} />
          </Button>
        </div>
        <p className="text-[10px] text-muted-foreground mt-1 ml-1">
          {uploadingFile ? '⏳ Uploading file...' : 'Enter kirim · Shift+Enter baris baru · 📎 Max 10MB'}
        </p>
      </div>
    </>
  );
}
