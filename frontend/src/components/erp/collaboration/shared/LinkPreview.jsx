/**
 * LinkPreview.jsx
 * Phase 3.7 — Preview cards for internal deep links in chat messages.
 * Patterns recognized:
 *   [[course:{id}:{title}]]   → Course preview card
 *   [[doc:{id}:{title}]]      → Document preview card
 *   [[channel:{id}:{name}]]   → Channel link
 * Also detects plain URLs and shows a minimal preview.
 */
import { useState, useEffect } from 'react';
import { ExternalLink, BookOpen, FileText, Hash } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

// Patterns for deep links
const DEEP_LINK_REGEX = /\[\[(course|doc|channel):([^:]+):([^\]]+)\]\]/g;

export function parseDeepLinks(content) {
  const links = [];
  let match;
  const regex = new RegExp(DEEP_LINK_REGEX.source, 'g');
  while ((match = regex.exec(content)) !== null) {
    links.push({
      type: match[1],
      id: match[2],
      title: match[3],
      raw: match[0],
    });
  }
  return links;
}

export function renderContentWithLinks(content, onNavigate) {
  if (!content) return content;
  // Split content by deep link patterns and render each part
  const parts = content.split(/\[\[(?:course|doc|channel):[^\]]+\]\]/);
  const links = parseDeepLinks(content);

  const result = [];
  parts.forEach((part, i) => {
    if (part) result.push(<span key={`text-${i}`}>{part}</span>);
    if (links[i]) {
      const link = links[i];
      result.push(
        <InlineLinkTag key={`link-${i}`} link={link} onNavigate={onNavigate} />
      );
    }
  });
  return result;
}

function InlineLinkTag({ link, onNavigate }) {
  const icons = { course: '📚', doc: '📄', channel: '#' };
  const colors = {
    course: 'bg-green-100 text-green-700 hover:bg-green-200',
    doc:    'bg-amber-100 text-amber-700 hover:bg-amber-200',
    channel:'bg-blue-100 text-blue-700 hover:bg-blue-200',
  };
  return (
    <button
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium mx-1 transition-colors ${colors[link.type] || 'bg-muted text-foreground'}`}
      onClick={() => onNavigate && onNavigate(link.type, link.id)}
    >
      <span>{icons[link.type] || '🔗'}</span>
      <span>{link.title}</span>
    </button>
  );
}

// Preview card rendered below message content
export default function LinkPreviewCard({ link, onNavigate, token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!link?.id || !token) { setLoading(false); return; }
    // FASE 20 — dulu '/api/collab/link-preview'. Router pencarian universal
    // memakai prefix '/api/collab/search', jadi path benarnya ada di bawahnya;
    // sebelum ini setiap pratinjau tautan gagal (404 senyap).
    const url = `${BACKEND_URL}/api/collab/search/link-preview?type=${link.type}&id=${encodeURIComponent(link.id)}`;
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [link, token]);

  if (loading) return (
    <div className="mt-1 h-12 bg-muted/50 rounded-lg animate-pulse" />
  );

  if (!data) return null;

  const iconMap = {
    course:  { icon: '📚', bg: 'bg-green-50 border-green-200',  text: 'text-green-700' },
    doc:     { icon: '📄', bg: 'bg-amber-50 border-amber-200',  text: 'text-amber-700' },
    channel: { icon: '#',    bg: 'bg-blue-50 border-blue-200',    text: 'text-blue-700' },
  };
  const cfg = iconMap[link.type] || iconMap.doc;

  return (
    <div
      className={`mt-1.5 flex items-center gap-3 p-2.5 rounded-lg border cursor-pointer hover:bg-accent/50 transition-colors ${cfg.bg}`}
      onClick={() => onNavigate && onNavigate(link.type, link.id)}
      data-testid={`link-preview-${link.type}`}
    >
      <div className={`text-xl flex-shrink-0`}>{cfg.icon}</div>
      <div className="flex-1 min-w-0">
        <p className={`text-xs font-semibold truncate ${cfg.text}`}>{data.title || link.title}</p>
        {data.subtitle && <p className="text-[10px] text-muted-foreground truncate">{data.subtitle}</p>}
      </div>
      <span className="text-xs text-muted-foreground flex-shrink-0">→</span>
    </div>
  );
}
