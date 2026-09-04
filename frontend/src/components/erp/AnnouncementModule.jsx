/**
 * AnnouncementModule — HR CMS untuk mengelola announcement board
 * Announcement board akan tampil di Portal Selector untuk semua user
 * 
 * Features:
 * - CRUD announcements
 * - Set priority, type, dan target portals
 * - Schedule announcement (start/end date)
 * - Toggle active/inactive
 * - Preview tampilan
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Bell, Plus, Edit2, Trash2, Eye, EyeOff, Calendar, Target,
  AlertCircle, Info, CheckCircle2, AlertTriangle, Megaphone
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import { PageHeader } from './moduleAtoms';
import { EmptyState } from './EmptyState';

const API = process.env.REACT_APP_BACKEND_URL;

const ANNOUNCEMENT_TYPES = {
  info: { label: 'Info', icon: Info, color: 'bg-blue-100 text-blue-700 border-blue-300' },
  success: { label: 'Success', icon: CheckCircle2, color: 'bg-green-100 text-green-700 border-green-300' },
  warning: { label: 'Warning', icon: AlertTriangle, color: 'bg-amber-100 text-amber-700 border-amber-300' },
  urgent: { label: 'Urgent', icon: AlertCircle, color: 'bg-red-100 text-red-700 border-red-300' },
};

const PORTAL_OPTIONS = [
  { value: 'all', label: 'Semua Portal' },
  { value: 'management', label: 'Manajemen' },
  { value: 'production', label: 'Produksi' },
  { value: 'warehouse', label: 'Gudang' },
  { value: 'accessories', label: 'Aksesoris' },
  { value: 'finance', label: 'Keuangan' },
  { value: 'hr', label: 'SDM' },
  { value: 'maklon', label: 'Maklon' },
  { value: 'toko', label: 'Marketing' },
  { value: 'rnd', label: 'RnD' },
];

function TypeBadge({ type }) {
  const config = ANNOUNCEMENT_TYPES[type] || ANNOUNCEMENT_TYPES.info;
  const Icon = config.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium border ${config.color}`}>
      <Icon size={12} />
      {config.label}
    </span>
  );
}

function AnnouncementCard({ announcement, onEdit, onToggle, onDelete }) {
  const isExpired = announcement.end_date && new Date(announcement.end_date) < new Date();
  const isPending = announcement.start_date && new Date(announcement.start_date) > new Date();
  
  return (
    <GlassCard data-testid={`announcement-card-${announcement.id}`}>
      <div className="p-4 space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-foreground">{announcement.title}</h3>
              <TypeBadge type={announcement.type} />
              {!announcement.is_active && (
                <Badge variant="secondary" className="text-xs">Nonaktif</Badge>
              )}
              {isExpired && (
                <Badge variant="outline" className="text-xs text-muted-foreground">Kedaluwarsa</Badge>
              )}
              {isPending && (
                <Badge variant="outline" className="text-xs text-amber-600">Terjadwal</Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground line-clamp-2">{announcement.content}</p>
          </div>
          <div className="flex items-center gap-1">
            <Button
              size="icon"
              variant="ghost"
              onClick={() => onToggle(announcement.id)}
              className="h-8 w-8"
              data-testid={`toggle-btn-${announcement.id}`}
            >
              {announcement.is_active ? <Eye size={16} /> : <EyeOff size={16} />}
            </Button>
            <Button
              size="icon"
              variant="ghost"
              onClick={() => onEdit(announcement)}
              className="h-8 w-8"
              data-testid={`edit-btn-${announcement.id}`}
            >
              <Edit2 size={16} />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              onClick={() => onDelete(announcement.id)}
              className="h-8 w-8 text-red-600 hover:bg-red-50"
              data-testid={`delete-btn-${announcement.id}`}
            >
              <Trash2 size={16} />
            </Button>
          </div>
        </div>

        {/* Metadata */}
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <Target size={12} />
            Priority: {announcement.priority}
          </div>
          <div className="flex items-center gap-1">
            <Calendar size={12} />
            {announcement.start_date || announcement.end_date ? (
              <>
                {announcement.start_date && new Date(announcement.start_date).toLocaleDateString('id-ID')}
                {announcement.start_date && announcement.end_date && ' - '}
                {announcement.end_date && new Date(announcement.end_date).toLocaleDateString('id-ID')}
              </>
            ) : (
              'Tidak terbatas'
            )}
          </div>
        </div>

        {/* Target Portals */}
        <div className="flex flex-wrap gap-1">
          {announcement.target_portals?.map(portal => (
            <Badge key={portal} variant="outline" className="text-xs">
              {PORTAL_OPTIONS.find(p => p.value === portal)?.label || portal}
            </Badge>
          ))}
        </div>

        {/* Creator */}
        {announcement.created_by_name && (
          <p className="text-xs text-muted-foreground">
            Dibuat oleh: {announcement.created_by_name}
          </p>
        )}
      </div>
    </GlassCard>
  );
}

function AnnouncementFormDialog({ open, onClose, announcement, onSuccess }) {
  const isEdit = !!announcement;
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    title: '',
    content: '',
    type: 'info',
    priority: 0,
    target_portals: ['all'],
    is_active: true,
    start_date: '',
    end_date: '',
  });

  useEffect(() => {
    if (announcement) {
      setForm({
        title: announcement.title || '',
        content: announcement.content || '',
        type: announcement.type || 'info',
        priority: announcement.priority || 0,
        target_portals: announcement.target_portals || ['all'],
        is_active: announcement.is_active ?? true,
        start_date: announcement.start_date ? new Date(announcement.start_date).toISOString().split('T')[0] : '',
        end_date: announcement.end_date ? new Date(announcement.end_date).toISOString().split('T')[0] : '',
      });
    } else {
      setForm({
        title: '',
        content: '',
        type: 'info',
        priority: 0,
        target_portals: ['all'],
        is_active: true,
        start_date: '',
        end_date: '',
      });
    }
  }, [announcement, open]);

  const handleSubmit = async () => {
    if (!form.title.trim() || !form.content.trim()) {
      toast.error('Judul dan konten harus diisi');
      return;
    }

    setLoading(true);
    const token = localStorage.getItem('erp_token');
    const payload = {
      ...form,
      start_date: form.start_date ? new Date(form.start_date).toISOString() : null,
      end_date: form.end_date ? new Date(form.end_date).toISOString() : null,
    };

    try {
      const url = isEdit
        ? `${API}/api/announcements/${announcement.id}`
        : `${API}/api/announcements/`;
      const method = isEdit ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Request failed');
      }

      toast.success(isEdit ? 'Announcement berhasil diupdate' : 'Announcement berhasil dibuat');
      onSuccess();
      onClose();
    } catch (error) {
      console.error('Error saving announcement:', error);
      toast.error(error.message || 'Gagal menyimpan announcement');
    } finally {
      setLoading(false);
    }
  };

  const togglePortal = (portal) => {
    if (portal === 'all') {
      setForm(prev => ({ ...prev, target_portals: ['all'] }));
    } else {
      setForm(prev => {
        const current = prev.target_portals.filter(p => p !== 'all');
        const updated = current.includes(portal)
          ? current.filter(p => p !== portal)
          : [...current, portal];
        return { ...prev, target_portals: updated.length > 0 ? updated : ['all'] };
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Announcement' : 'Buat Announcement Baru'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Title */}
          <div>
            <Label>Judul Announcement</Label>
            <Input
              value={form.title}
              onChange={e => setForm(prev => ({ ...prev, title: e.target.value }))}
              placeholder="Contoh: Libur Nasional 17 Agustus"
              data-testid="announcement-title-input"
            />
          </div>

          {/* Content */}
          <div>
            <Label>Konten</Label>
            <Textarea
              value={form.content}
              onChange={e => setForm(prev => ({ ...prev, content: e.target.value }))}
              placeholder="Deskripsi lengkap announcement..."
              rows={4}
              data-testid="announcement-content-input"
            />
          </div>

          {/* Type & Priority */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Tipe</Label>
              <Select value={form.type} onValueChange={type => setForm(prev => ({ ...prev, type }))}>
                <SelectTrigger data-testid="announcement-type-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(ANNOUNCEMENT_TYPES).map(([key, config]) => (
                    <SelectItem key={key} value={key}>
                      <div className="flex items-center gap-2">
                        <config.icon size={14} />
                        {config.label}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>Priority (0-10)</Label>
              <Input
                type="number"
                min={0}
                max={10}
                value={form.priority}
                onChange={e => setForm(prev => ({ ...prev, priority: parseInt(e.target.value) || 0 }))}
                data-testid="announcement-priority-input"
              />
            </div>
          </div>

          {/* Date Range */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Tanggal Mulai (Opsional)</Label>
              <Input
                type="date"
                value={form.start_date}
                onChange={e => setForm(prev => ({ ...prev, start_date: e.target.value }))}
                data-testid="announcement-start-date"
              />
            </div>
            <div>
              <Label>Tanggal Berakhir (Opsional)</Label>
              <Input
                type="date"
                value={form.end_date}
                onChange={e => setForm(prev => ({ ...prev, end_date: e.target.value }))}
                data-testid="announcement-end-date"
              />
            </div>
          </div>

          {/* Target Portals */}
          <div>
            <Label>Target Portal</Label>
            <div className="flex flex-wrap gap-2 mt-2">
              {PORTAL_OPTIONS.map(portal => (
                <Button
                  key={portal.value}
                  type="button"
                  size="sm"
                  variant={form.target_portals.includes(portal.value) ? 'default' : 'outline'}
                  onClick={() => togglePortal(portal.value)}
                  data-testid={`portal-toggle-${portal.value}`}
                >
                  {portal.label}
                </Button>
              ))}
            </div>
          </div>

          {/* Active Status */}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="is-active"
              checked={form.is_active}
              onChange={e => setForm(prev => ({ ...prev, is_active: e.target.checked }))}
              className="rounded"
              data-testid="announcement-active-checkbox"
            />
            <Label htmlFor="is-active" className="cursor-pointer">Aktif (tampilkan di Portal Selector)</Label>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            Batal
          </Button>
          <Button onClick={handleSubmit} disabled={loading} data-testid="announcement-save-btn">
            {loading ? 'Menyimpan...' : (isEdit ? 'Update' : 'Buat')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function AnnouncementModule() {
  const [announcements, setAnnouncements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingAnnouncement, setEditingAnnouncement] = useState(null);
  const [filter, setFilter] = useState('all'); // all | active | inactive

  const fetchAnnouncements = useCallback(async () => {
    setLoading(true);
    const token = localStorage.getItem('erp_token');
    try {
      const res = await fetch(`${API}/api/announcements/all`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed to fetch');
      const data = await res.json();
      setAnnouncements(data);
    } catch (error) {
      console.error('Error fetching announcements:', error);
      toast.error('Gagal memuat announcements');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAnnouncements();
  }, [fetchAnnouncements]);

  const handleToggleStatus = async (id) => {
    const token = localStorage.getItem('erp_token');
    try {
      const res = await fetch(`${API}/api/announcements/${id}/toggle`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed to toggle');
      toast.success('Status berhasil diubah');
      fetchAnnouncements();
    } catch (error) {
      console.error('Error toggling status:', error);
      toast.error('Gagal mengubah status');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Yakin ingin menghapus announcement ini?')) return;
    
    const token = localStorage.getItem('erp_token');
    try {
      const res = await fetch(`${API}/api/announcements/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed to delete');
      toast.success('Announcement berhasil dihapus');
      fetchAnnouncements();
    } catch (error) {
      console.error('Error deleting announcement:', error);
      toast.error('Gagal menghapus announcement');
    }
  };

  const handleEdit = (announcement) => {
    setEditingAnnouncement(announcement);
    setShowDialog(true);
  };

  const handleCloseDialog = () => {
    setShowDialog(false);
    setEditingAnnouncement(null);
  };

  const filteredAnnouncements = announcements.filter(a => {
    if (filter === 'active') return a.is_active;
    if (filter === 'inactive') return !a.is_active;
    return true;
  });

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Megaphone}
        title="Announcement Management"
        description="Kelola pengumuman yang tampil di Portal Selector untuk seluruh user"
        actions={
          <Button onClick={() => { setEditingAnnouncement(null); setShowDialog(true); }} data-testid="create-announcement-btn">
            <Plus size={16} className="mr-2" />
            Buat Announcement
          </Button>
        }
      />

      {/* Filter */}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant={filter === 'all' ? 'default' : 'outline'}
          onClick={() => setFilter('all')}
        >
          Semua
        </Button>
        <Button
          size="sm"
          variant={filter === 'active' ? 'default' : 'outline'}
          onClick={() => setFilter('active')}
        >
          Aktif
        </Button>
        <Button
          size="sm"
          variant={filter === 'inactive' ? 'default' : 'outline'}
          onClick={() => setFilter('inactive')}
        >
          Nonaktif
        </Button>
      </div>

      {/* List */}
      {loading ? (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto" />
          <p className="text-sm text-muted-foreground mt-4">Memuat announcements...</p>
        </div>
      ) : filteredAnnouncements.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="Belum ada announcement"
          description="Buat announcement pertama Anda untuk ditampilkan di Portal Selector"
          action={
            <Button onClick={() => { setEditingAnnouncement(null); setShowDialog(true); }}>
              <Plus size={16} className="mr-2" />
              Buat Announcement
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4">
          <AnimatePresence mode="popLayout">
            {filteredAnnouncements.map(announcement => (
              <motion.div
                key={announcement.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ duration: 0.2 }}
              >
                <AnnouncementCard
                  announcement={announcement}
                  onEdit={handleEdit}
                  onToggle={handleToggleStatus}
                  onDelete={handleDelete}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Dialog */}
      <AnnouncementFormDialog
        open={showDialog}
        onClose={handleCloseDialog}
        announcement={editingAnnouncement}
        onSuccess={fetchAnnouncements}
      />
    </div>
  );
}
