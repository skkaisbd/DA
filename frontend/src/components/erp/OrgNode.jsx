import { useState } from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';

const TYPE_CONFIG = {
  company:    { label: 'Perusahaan',  color: '#6366f1', bg: '#6366f115' },
  division:   { label: 'Divisi',      color: '#8b5cf6', bg: '#8b5cf615' },
  department: { label: 'Departemen',  color: '#ec4899', bg: '#ec489915' },
  section:    { label: 'Seksi',       color: '#f59e0b', bg: '#f59e0b15' },
  team:       { label: 'Tim',         color: '#10b981', bg: '#10b98115' },
};

function TypeBadge({ type }) {
  const c = TYPE_CONFIG[type] || { label: type, color: '#64748b', bg: '#64748b15' };
  return (
    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: c.bg, color: c.color }}>{c.label}</span>
  );
}

// Flatten tree to avoid Babel recursion issues
function flattenTree(node, depth = 0, result = []) {
  if (!node) return result;
  result.push({ ...node, depth, hasChildren: !!(node.children && node.children.length > 0) });
  if (node.children && node.children.length > 0) {
    node.children.forEach(child => flattenTree(child, depth + 1, result));
  }
  return result;
}

// Non-recursive tree renderer
export function OrgNode({ node }) {
  const [expandedIds, setExpandedIds] = useState(new Set());
  const flatNodes = flattenTree(node);

  // Auto-expand first 2 levels
  if (expandedIds.size === 0) {
    const autoExpand = new Set();
    flatNodes.forEach(n => {
      if (n.depth < 2 && n.hasChildren) {
        autoExpand.add(n.unit_id);
      }
    });
    if (autoExpand.size > 0) {
      setExpandedIds(autoExpand);
    }
  }

  const toggleExpand = (id) => {
    const newSet = new Set(expandedIds);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setExpandedIds(newSet);
  };

  // Build visibility map
  const visibleNodes = [];
  const parentVisible = new Map();
  flatNodes.forEach(n => {
    if (n.depth === 0) {
      parentVisible.set(n.unit_id, true);
      visibleNodes.push(n);
    } else {
      // Check if parent is expanded
      const parent = flatNodes.find(p => p.children && p.children.some(c => c.unit_id === n.unit_id));
      if (parent && parentVisible.get(parent.unit_id) && expandedIds.has(parent.unit_id)) {
        parentVisible.set(n.unit_id, true);
        visibleNodes.push(n);
      }
    }
  });

  return (
    <div>
      {visibleNodes.map(n => {
        const cfg = TYPE_CONFIG[n.type] || TYPE_CONFIG.department;
        const expanded = expandedIds.has(n.unit_id);
        const gapPct = n.headcount_target > 0 ? Math.abs(n.headcount_target - n.headcount_actual) : 0;
        const isUnder = n.headcount_actual < (n.headcount_target || 0);

        return (
          <div key={n.unit_id} className={`${n.depth > 0 ? 'ml-6 border-l-2 border-[var(--glass-border)] pl-4' : ''}`}>
            <div className="mb-2">
              <div className="p-3 rounded-xl border transition-all hover:border-[hsl(var(--primary)/0.3)]"
                style={{ borderColor: `${cfg.color}30`, background: `${cfg.color}08` }}
                data-testid={`org-node-${n.unit_id}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    {n.hasChildren && (
                      <button onClick={() => toggleExpand(n.unit_id)} className="w-5 h-5 flex items-center justify-center rounded text-muted-foreground hover:text-foreground shrink-0">
                        {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                      </button>
                    )}
                    {!n.hasChildren && <div className="w-5 h-5 flex items-center justify-center shrink-0"><div className="w-1.5 h-1.5 rounded-full" style={{ background: cfg.color }} /></div>}
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-semibold text-sm text-foreground truncate">{n.name}</p>
                        <TypeBadge type={n.type} />
                        {n.code && <span className="text-xs text-muted-foreground hidden sm:inline">[{n.code}]</span>}
                      </div>
                      {n.head_employee_name && (
                        <p className="text-xs text-muted-foreground truncate">{n.head_employee_name}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-2">
                    {n.headcount_target > 0 && (
                      <div className="text-right">
                        <div className="flex items-center gap-1 text-xs">
                          <span className="font-semibold" style={{ color: cfg.color }}>{n.headcount_actual}</span>
                          <span className="text-muted-foreground">/{n.headcount_target}</span>
                          {gapPct > 0 && (
                            <span className={`text-xs font-medium ${isUnder ? 'text-amber-400' : 'text-emerald-400'}`}>
                              {isUnder ? `-${gapPct}` : `+${Math.abs(gapPct)}`}
                            </span>
                          )}
                        </div>
                        <p className="text-[10px] text-muted-foreground">Aktual/Target</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
