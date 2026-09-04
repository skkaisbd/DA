/**
 * ExportCsvButton — tombol "unduh yang terlihat" yang seragam di semua layar daftar.
 *
 * KENAPA KOMPONEN INI ADA (F10, sesi #10): lihat `lib/csv.js`. Tombol ini hanya
 * membungkus `downloadCsv` + memberi umpan balik jujur (berapa baris yang terunduh)
 * dan MATI ketika tidak ada baris — tombol yang bisa diklik lalu menghasilkan
 * berkas kosong membuat staf mengira datanya hilang.
 *
 * Pemakaian:
 *   <ExportCsvButton filename="pesanan-marketplace" head={HEAD}
 *     rows={rowsTerlihat.map(toRow)} testId="orders-export-csv" />
 */
import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { downloadCsv } from '@/lib/csv';

export default function ExportCsvButton({
  filename, head, rows, testId = 'export-csv', label = 'CSV',
  size = 'sm', variant = 'outline', className = 'h-8',
  note = '',
}) {
  const list = rows || [];
  return (
    <Button size={size} variant={variant} className={className}
      disabled={!list.length}
      data-testid={testId}
      title={list.length ? `Unduh ${list.length} baris yang sedang terlihat` : 'Belum ada baris untuk diunduh'}
      onClick={() => {
        const n = downloadCsv(filename, head, list);
        toast.success(`CSV terunduh — ${n} baris${note ? ` · ${note}` : ''}`);
      }}>
      <Download size={12} className="mr-1" /> {label}
    </Button>
  );
}
