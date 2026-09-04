/**
 * NewDocForm — small inline form used inside the "Spreadsheet Baru" dialog.
 */
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { DialogFooter } from '@/components/ui/dialog';
import { Plus, Loader2 } from 'lucide-react';

import { apicall } from './utils';

export default function NewDocForm({ token, onCreated, onClose }) {
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) { toast.error('Nama dokumen wajib diisi'); return; }
    setLoading(true);
    try {
      const doc = await apicall('POST', '/api/workspace/documents', token, { name: name.trim() });
      toast.success('Spreadsheet baru dibuat!');
      onCreated(doc);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Input
        placeholder="Nama spreadsheet..."
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && !loading && handleCreate()}
        autoFocus
        data-testid="new-doc-name-input"
      />
      <DialogFooter className="gap-2">
        <Button variant="outline" onClick={onClose}>Batal</Button>
        <Button onClick={handleCreate} disabled={loading || !name.trim()} data-testid="new-doc-submit">
          {loading ? <Loader2 size={14} className="animate-spin mr-1" /> : <Plus size={14} className="mr-1" />}
          Buat
        </Button>
      </DialogFooter>
    </>
  );
}
