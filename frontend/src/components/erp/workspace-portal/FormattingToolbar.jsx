/**
 * FormattingToolbar — cell-level formatting for the selected cell.
 *
 * Supports: bold, italic, alignment (left/center/right), text-color, bg-color,
 * and a "Reset" button to clear the cell's formatting.
 *
 * Formatting state shape (parent-owned):
 *   `{ [`${rowId}:${colKey}`]: { bold, italic, align, color, bgColor } }`
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Bold, Italic, AlignLeft, AlignCenter, AlignRight,
  ChevronDown, Palette,
} from 'lucide-react';

import { COLORS, BG_COLORS } from './utils';

export default function FormattingToolbar({ selectedCell, formatting, onFormat, readOnly }) {
  const [showTextColor, setShowTextColor] = useState(false);
  const [showBgColor, setShowBgColor] = useState(false);

  if (readOnly || !selectedCell) return null;
  const key = selectedCell ? `${selectedCell.rowId}:${selectedCell.colKey}` : null;
  const fmt = key ? (formatting[key] || {}) : {};

  const apply = (k, v) => {
    if (!key) return;
    onFormat(key, { ...fmt, [k]: v });
  };
  const toggle = (k) => apply(k, !fmt[k]);

  return (
    <div
      className="flex items-center gap-1 px-3 py-1.5 bg-card border-b text-xs"
      data-testid="formatting-toolbar"
    >
      <span className="text-muted-foreground mr-1 text-[10px]">FORMAT:</span>
      <Button variant={fmt.bold ? 'default' : 'ghost'} size="sm" className="h-6 w-6 p-0"
        onClick={() => toggle('bold')} title="Bold" data-testid="fmt-bold">
        <Bold size={12} />
      </Button>
      <Button variant={fmt.italic ? 'default' : 'ghost'} size="sm" className="h-6 w-6 p-0"
        onClick={() => toggle('italic')} title="Italic" data-testid="fmt-italic">
        <Italic size={12} />
      </Button>

      <div className="w-px h-4 bg-border mx-1" />

      <Button variant={fmt.align === 'left' ? 'default' : 'ghost'} size="sm" className="h-6 w-6 p-0"
        onClick={() => apply('align', 'left')} title="Rata Kiri" data-testid="fmt-align-left">
        <AlignLeft size={12} />
      </Button>
      <Button variant={fmt.align === 'center' ? 'default' : 'ghost'} size="sm" className="h-6 w-6 p-0"
        onClick={() => apply('align', 'center')} title="Tengah">
        <AlignCenter size={12} />
      </Button>
      <Button variant={fmt.align === 'right' ? 'default' : 'ghost'} size="sm" className="h-6 w-6 p-0"
        onClick={() => apply('align', 'right')} title="Rata Kanan">
        <AlignRight size={12} />
      </Button>

      <div className="w-px h-4 bg-border mx-1" />

      {/* Text color */}
      <div className="relative">
        <Button variant="ghost" size="sm" className="h-6 px-1.5 gap-1"
          onClick={() => { setShowTextColor((v) => !v); setShowBgColor(false); }}
          title="Warna Teks" data-testid="fmt-text-color">
          <span className="text-xs font-bold" style={{ color: fmt.color || 'currentColor' }}>A</span>
          <ChevronDown size={8} />
        </Button>
        {showTextColor && (
          <div className="absolute top-7 left-0 z-50 bg-card border rounded-lg shadow-lg p-2 flex flex-wrap gap-1 w-28">
            {COLORS.map((c) => (
              <button key={c.val}
                className={`w-5 h-5 rounded border-2 ${fmt.color === c.val ? 'border-primary' : 'border-transparent'} ${!c.val ? 'bg-muted text-[8px]' : ''}`}
                style={{ backgroundColor: c.val || undefined }}
                title={c.label}
                onClick={() => { apply('color', c.val); setShowTextColor(false); }}>
                {!c.val ? '−' : ''}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* BG color */}
      <div className="relative">
        <Button variant="ghost" size="sm" className="h-6 px-1.5 gap-1"
          onClick={() => { setShowBgColor((v) => !v); setShowTextColor(false); }}
          title="Warna Background" data-testid="fmt-bg-color">
          <Palette size={12} style={{ color: fmt.bgColor || 'currentColor' }} />
          <ChevronDown size={8} />
        </Button>
        {showBgColor && (
          <div className="absolute top-7 left-0 z-50 bg-card border rounded-lg shadow-lg p-2 flex flex-wrap gap-1 w-28">
            {BG_COLORS.map((c) => (
              <button key={c.val}
                className={`w-5 h-5 rounded border-2 ${fmt.bgColor === c.val ? 'border-primary' : 'border-transparent'} ${!c.val ? 'bg-muted text-[8px]' : ''}`}
                style={{ backgroundColor: c.val || undefined }}
                title={c.label}
                onClick={() => { apply('bgColor', c.val); setShowBgColor(false); }}>
                {!c.val ? '−' : ''}
              </button>
            ))}
          </div>
        )}
      </div>

      {key && (
        <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px] text-muted-foreground ml-1"
          onClick={() => onFormat(key, {})} title="Reset format sel ini">
          Reset
        </Button>
      )}
    </div>
  );
}
