/**
 * FormulaBar — spreadsheet-style formula bar above the grid.
 *
 * Shows the raw value (or formula = result) of the selected cell and lets the
 * user edit it inline. Pressing Enter commits via onUpdateCell.
 */
import { useState, useEffect } from 'react';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Sigma } from 'lucide-react';

import { evaluateFormula } from './utils';

export default function FormulaBar({ selectedCell, rows, onUpdateCell, readOnly }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState('');

  useEffect(() => {
    if (!selectedCell) return;
    setVal(String(selectedCell.rawVal ?? ''));
    setEditing(false);
  }, [selectedCell]);

  if (!selectedCell) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-muted/20 border-b text-xs text-muted-foreground"
        data-testid="formula-bar">
        <Sigma size={13} className="shrink-0" />
        <span>Pilih sel untuk melihat/edit nilai</span>
      </div>
    );
  }

  const { rowId, colKey, rawVal } = selectedCell;
  const displayVal = String(rawVal ?? '');
  const isFormula = displayVal.startsWith('=');
  const computed = isFormula ? String(evaluateFormula(displayVal, rows, colKey)) : displayVal;

  const commit = () => {
    setEditing(false);
    onUpdateCell(rowId, colKey, val);
  };

  return (
    <div className="flex items-center gap-2 px-3 py-1 bg-muted/10 border-b" data-testid="formula-bar">
      <Sigma size={13} className="shrink-0 text-muted-foreground" />
      <span className="text-xs text-muted-foreground font-mono shrink-0">{colKey}</span>
      <div className="w-px h-4 bg-border shrink-0" />
      {editing && !readOnly ? (
        <Input
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') setEditing(false);
          }}
          autoFocus
          className="h-6 text-xs font-mono flex-1 border-0 bg-transparent focus-visible:ring-0 p-0"
          placeholder="Masukkan nilai atau =FORMULA(kolom)..."
        />
      ) : (
        <div
          className={`flex-1 text-xs font-mono cursor-text truncate ${isFormula ? 'text-primary' : ''}`}
          onClick={() => !readOnly && setEditing(true)}
          title={isFormula ? `Formula: ${displayVal}\nHasil: ${computed}` : displayVal}
          data-testid="formula-bar-value"
        >
          {isFormula ? (
            <span className="flex items-center gap-2">
              <span className="text-primary">{displayVal}</span>
              <span className="text-muted-foreground">= {computed}</span>
            </span>
          ) : displayVal || <span className="text-muted-foreground">Kosong — klik untuk edit</span>}
        </div>
      )}
      {isFormula && <Badge variant="secondary" className="text-[10px] shrink-0">Formula</Badge>}
    </div>
  );
}
