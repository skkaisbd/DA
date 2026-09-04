import { Download, FileSpreadsheet, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { useState } from 'react';

/**
 * Grouped export buttons (CSV, Excel, PDF)
 */
export function ExportButtonGroup({ 
  onExportCSV, 
  onExportExcel, 
  onExportPDF, 
  disabled = false,
  className = "" 
}) {
  const [loading, setLoading] = useState({ csv: false, excel: false, pdf: false });
  
  const handleExport = async (type, handler) => {
    if (!handler) {
      toast.error(`Export ${type.toUpperCase()} belum tersedia`);
      return;
    }
    
    setLoading(prev => ({ ...prev, [type]: true }));
    toast.info(`Menyiapkan export ${type.toUpperCase()}...`);
    
    try {
      await handler();
      toast.success(`Export ${type.toUpperCase()} siap diunduh`);
    } catch (error) {
      toast.error(`Gagal export ${type.toUpperCase()}: ${error.message}`);
    } finally {
      setLoading(prev => ({ ...prev, [type]: false }));
    }
  };
  
  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => handleExport('csv', onExportCSV)}
        disabled={disabled || loading.csv}
        data-testid="report-export-csv-button"
        className="gap-1.5"
      >
        <Download className="w-3.5 h-3.5" />
        {loading.csv ? 'Export...' : 'CSV'}
      </Button>
      
      {onExportExcel && (
        <Button
          variant="secondary"
          size="sm"
          onClick={() => handleExport('excel', onExportExcel)}
          disabled={disabled || loading.excel}
          data-testid="report-export-excel-button"
          className="gap-1.5"
        >
          <FileSpreadsheet className="w-3.5 h-3.5" />
          {loading.excel ? 'Export...' : 'Excel'}
        </Button>
      )}
      
      {onExportPDF && (
        <Button
          variant="default"
          size="sm"
          onClick={() => handleExport('pdf', onExportPDF)}
          disabled={disabled || loading.pdf}
          data-testid="report-export-pdf-button"
          className="gap-1.5"
        >
          <FileText className="w-3.5 h-3.5" />
          {loading.pdf ? 'Export...' : 'PDF'}
        </Button>
      )}
    </div>
  );
}