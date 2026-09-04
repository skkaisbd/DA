import { useState } from 'react';
import { Edit2, Trash2 } from 'lucide-react';

const TYPE_COLORS = {
  ASSET: 'text-emerald-300 bg-emerald-400/10 border-emerald-400/25',
  LIABILITY: 'text-amber-300 bg-amber-400/10 border-amber-400/25',
  EQUITY: 'text-sky-300 bg-sky-400/10 border-sky-400/25',
  REVENUE: 'text-violet-300 bg-violet-400/10 border-violet-400/25',
  COGS: 'text-rose-300 bg-rose-400/10 border-rose-400/25',
  EXPENSE: 'text-red-300 bg-red-400/10 border-red-400/25',
  OTHER_INCOME: 'text-teal-300 bg-teal-400/10 border-teal-400/25',
  OTHER_EXPENSE: 'text-orange-300 bg-orange-400/10 border-orange-400/25',
};

export function TypeBadge({ type }) {
  const cls = TYPE_COLORS[type] || 'text-foreground/70 bg-foreground/5 border-foreground/10';
  return (
    <span className={'text-[9px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded border ' + cls}>{type}</span>
  );
}

/** Flatten a tree into [{ node, depth, hasChildren }] based on an `open` set (codes). */
export function flattenTree(nodes, openSet, depth) {
  const out = [];
  const d = depth || 0;
  for (const n of nodes) {
    const hasChildren = Array.isArray(n.children) && n.children.length > 0;
    out.push({ node: n, depth: d, hasChildren });
    if (hasChildren && openSet.has(n.code)) {
      const childRows = flattenTree(n.children, openSet, d + 1);
      for (const r of childRows) out.push(r);
    }
  }
  return out;
}

function TreeRow({ row, onToggle, onEdit, onDelete, isOpen }) {
  const { node, depth, hasChildren } = row;
  const padLeft = depth * 16 + 8;
  return (
    <div
      className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-foreground/5 group"
      style={{ paddingLeft: padLeft + 'px' }}
    >
      {hasChildren ? (
        <button
          onClick={() => onToggle(node.code)}
          className="w-4 h-4 grid place-items-center text-muted-foreground hover:text-foreground"
          data-testid={'coa-toggle-' + node.code}
        >
          {isOpen ? '▾' : '▸'}
        </button>
      ) : (
        <span className="w-4" />
      )}
      <span className="font-mono text-xs text-foreground/70 w-20">{node.code}</span>
      <span className={node.is_group ? 'text-sm font-semibold text-foreground' : 'text-sm text-foreground/85'}>
        {node.name}
      </span>
      <TypeBadge type={node.type} />
      {node.is_group && <span className="text-[9px] text-muted-foreground italic">(group)</span>}
      <div className="ml-auto flex items-center gap-1 opacity-0 group-hover:opacity-100">
        <button
          onClick={() => onEdit(node)}
          className="text-primary hover:bg-primary/10 rounded p-1"
          title="Edit"
          data-testid={'coa-edit-' + node.code}
        >
          <Edit2 className="w-3 h-3" />
        </button>
        <button
          onClick={() => onDelete(node)}
          className="text-red-300 hover:bg-red-400/10 rounded p-1"
          title="Hapus"
          data-testid={'coa-delete-' + node.code}
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

export function CoaTreeView({ tree, onEdit, onDelete }) {
  const collectDefault = () => {
    const s = new Set();
    const stack = [...tree.map(n => ({ n, d: 0 }))];
    while (stack.length) {
      const { n, d } = stack.pop();
      if (d < 2 && n.children && n.children.length > 0) {
        s.add(n.code);
        for (const c of n.children) stack.push({ n: c, d: d + 1 });
      }
    }
    return s;
  };
  const [open, setOpen] = useState(collectDefault);
  const toggle = (code) => {
    setOpen(prev => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  };
  const rows = flattenTree(tree, open, 0);
  return (
    <div className="max-h-[600px] overflow-auto">
      {rows.map((row) => (
        <TreeRow
          key={row.node.code}
          row={row}
          onToggle={toggle}
          onEdit={onEdit}
          onDelete={onDelete}
          isOpen={open.has(row.node.code)}
        />
      ))}
    </div>
  );
}
