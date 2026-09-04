/**
 * AddColumnDialog + ManageColumnsDialog — combined column-management dialogs.
 *
 * ManageColumnsDialog shows current columns + delete buttons; nests AddColumnDialog
 * when user clicks "Tambah Kolom".
 */
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Columns, Plus, Trash2 } from 'lucide-react';

export function AddColumnDialog({ open, onClose, onAdd }) {
  const [name, setName] = useState('');
  const [type, setType] = useState('text');

  const handleAdd = () => {
    if (!name.trim()) { toast.error('Nama kolom wajib diisi'); return; }
    const key = `${name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'col'}_${Date.now()}`;
    onAdd({ key, name: name.trim(), type, editable: true, width: 160 });
    setName(''); setType('text'); onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-sm" data-testid="add-column-dialog">
        <DialogHeader><DialogTitle>Tambah Kolom</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium mb-1 block">Nama Kolom *</label>
            <Input
              placeholder="Contoh: Jumlah, Keterangan..."
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              autoFocus
              data-testid="add-column-name"
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">Tipe Data</label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger data-testid="add-column-type"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="text">Teks</SelectItem>
                <SelectItem value="number">Angka</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={handleAdd} data-testid="add-column-submit">Tambah</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ManageColumnsDialog({ open, onClose, columns, onDelete, onAdd }) {
  const [showAdd, setShowAdd] = useState(false);
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-sm" data-testid="manage-columns-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Columns size={16} />Kelola Kolom</DialogTitle>
        </DialogHeader>
        <ScrollArea className="max-h-56">
          <div className="space-y-1 pr-1">
            {columns.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-4">Belum ada kolom</p>
            )}
            {columns.map((col, i) => (
              <div key={col.key} className="flex items-center justify-between p-2 rounded-md hover:bg-muted/30 border">
                <div>
                  <p className="text-sm font-medium">{col.name}</p>
                  <p className="text-xs text-muted-foreground capitalize">{col.type || 'text'}</p>
                </div>
                <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-destructive"
                  onClick={() => window.confirm(`Hapus kolom "${col.name}"?`) && onDelete(col.key)}
                  data-testid={`delete-col-${i}`}>
                  <Trash2 size={12} />
                </Button>
              </div>
            ))}
          </div>
        </ScrollArea>
        {showAdd
          ? <AddColumnDialog open={showAdd} onClose={() => setShowAdd(false)}
              onAdd={(col) => { onAdd(col); setShowAdd(false); }} />
          : <Button variant="outline" className="w-full" onClick={() => setShowAdd(true)} data-testid="open-add-column">
              <Plus size={14} className="mr-1" />Tambah Kolom
            </Button>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="w-full">Selesai</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
