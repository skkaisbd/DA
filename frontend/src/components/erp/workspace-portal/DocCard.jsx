/**
 * DocCard — list-item card for a Workspace document on the index page.
 *
 * Shows: name + AccessBadge + owner (if shared) + last-updated + row/col count.
 * Reveals share/delete buttons on hover.
 */
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { FileSpreadsheet, Clock, Share2, Trash2 } from 'lucide-react';

import AccessBadge from './AccessBadge';
import { fmtTime } from './utils';

export default function DocCard({ doc, onOpen, onDelete, onShare, showDelete, showShare }) {
  return (
    <Card
      className="hover:shadow-md transition-all cursor-pointer group border"
      onClick={() => onOpen(doc.id)}
      data-testid={`doc-card-${doc.id}`}
    >
      <CardContent className="p-4 flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
          <FileSpreadsheet size={20} className="text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <h3 className="font-medium text-sm truncate">{doc.name}</h3>
            <AccessBadge level={doc.access_level} />
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {!doc.is_owner && <span>oleh {doc.owner_name}</span>}
            <span className="flex items-center gap-1">
              <Clock size={11} />{fmtTime(doc.updated_at)}
            </span>
            <span>
              {doc.metadata?.row_count ?? 0} baris · {doc.metadata?.column_count ?? 0} kolom
            </span>
          </div>
        </div>
        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {showShare && (
            <Button variant="ghost" size="sm" className="h-8 w-8 p-0"
              onClick={(e) => { e.stopPropagation(); onShare(doc); }}
              data-testid={`share-doc-${doc.id}`}>
              <Share2 size={14} />
            </Button>
          )}
          {showDelete && (
            <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-destructive hover:text-destructive"
              onClick={(e) => { e.stopPropagation(); onDelete(doc.id, doc.name); }}
              data-testid={`delete-doc-${doc.id}`}>
              <Trash2 size={14} />
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
