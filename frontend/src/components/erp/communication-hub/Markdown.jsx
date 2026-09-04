/**
 * Tiny custom Markdown renderer for chat messages.
 * Supports inline: **bold**, _italic_, `code`, ~~strike~~, and `- bullet lists`.
 * Returns a React fragment.
 */
import React from 'react';

export default function Markdown({ text }) {
  return renderMarkdown(text);
}

export function renderMarkdown(text) {
  if (!text) return null;
  const lines = text.split('\n');
  const elements = [];
  let listItems = [];

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} className="list-disc list-inside my-0.5 space-y-0">
          {listItems.map((item, i) => (
            <li key={i} className="text-sm">{renderInline(item)}</li>
          ))}
        </ul>
      );
      listItems = [];
    }
  };

  const renderInline = (str) => {
    const parts = [];
    const regex = /(\*\*(.+?)\*\*|_(.+?)_|`(.+?)`|~~(.+?)~~)/g;
    let last = 0;
    let m;
    while ((m = regex.exec(str)) !== null) {
      if (m.index > last) parts.push(str.slice(last, m.index));
      if (m[2] !== undefined) parts.push(<strong key={m.index}>{m[2]}</strong>);
      else if (m[3] !== undefined) parts.push(<em key={m.index}>{m[3]}</em>);
      else if (m[4] !== undefined) parts.push(<code key={m.index} className="bg-muted px-1 rounded text-xs font-mono">{m[4]}</code>);
      else if (m[5] !== undefined) parts.push(<del key={m.index}>{m[5]}</del>);
      last = m.index + m[0].length;
    }
    if (last < str.length) parts.push(str.slice(last));
    return parts.length > 0 ? parts : str;
  };

  lines.forEach((line, idx) => {
    const listMatch = line.match(/^[-*]\s+(.*)/);
    if (listMatch) {
      listItems.push(listMatch[1]);
    } else {
      flushList();
      if (line === '') {
        elements.push(<br key={`br-${idx}`} />);
      } else {
        elements.push(<span key={`line-${idx}`} className="block">{renderInline(line)}</span>);
      }
    }
  });
  flushList();
  return <>{elements}</>;
}
