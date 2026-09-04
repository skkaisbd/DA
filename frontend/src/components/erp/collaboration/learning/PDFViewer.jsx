/**
 * PDFViewer.jsx
 * Renders PDF via iframe + provides download link fallback.
 */

import { FileText, Download, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function PDFViewer({ url, title }) {
  if (!url) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <FileText size={48} className="mb-2 opacity-30" />
        <p>PDF belum tersedia</p>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="pdf-viewer">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm">
          <FileText size={16} />
          <span className="font-medium">{title || 'PDF Document'}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            asChild
            data-testid="pdf-open-new-tab"
          >
            <a href={url} target="_blank" rel="noopener noreferrer">
              <ExternalLink size={14} className="mr-1" />
              Open
            </a>
          </Button>
          <Button
            variant="outline"
            size="sm"
            asChild
            data-testid="pdf-download"
          >
            <a href={url} download>
              <Download size={14} className="mr-1" />
              Download
            </a>
          </Button>
        </div>
      </div>
      <div className="border rounded-lg overflow-hidden bg-muted/30" style={{ height: '500px' }}>
        <iframe
          src={url}
          title={title || 'PDF Document'}
          className="w-full h-full"
          data-testid="pdf-iframe"
        />
      </div>
    </div>
  );
}
