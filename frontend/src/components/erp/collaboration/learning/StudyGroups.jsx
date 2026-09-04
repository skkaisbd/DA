/**
 * StudyGroups.jsx
 * Phase 3.8: Study Groups - Social Learning Component
 * List study groups + create new group + navigate to detail
 */

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { 
  Users, Plus, MessageSquare, FolderOpen, Calendar,
  TrendingUp, BookOpen, ArrowRight
} from 'lucide-react';
import { toast } from 'sonner';
import apiFetch from '@/lib/apiFetch';

export default function StudyGroups({ onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [groups, setGroups] = useState([]);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [courses, setCourses] = useState([]);
  
  // Form state
  const [formData, setFormData] = useState({
    name: '',
    course_id: '',
    description: '',
  });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchStudyGroups();
    fetchEnrolledCourses();
  }, []);

  const fetchStudyGroups = async () => {
    try {
      setLoading(true);
      const data = await apiFetch('/collab/study-groups');
      setGroups(data.study_groups || []);
    } catch (error) {
      console.error('Error fetching study groups:', error);
      toast.error('Gagal memuat study groups');
    } finally {
      setLoading(false);
    }
  };

  const fetchEnrolledCourses = async () => {
    try {
      const data = await apiFetch('/lms/student/my-courses?status=all');
      setCourses(data.courses || []);
    } catch (error) {
      console.error('Error fetching courses:', error);
    }
  };

  const handleCreateGroup = async () => {
    if (!formData.name.trim()) {
      toast.error('Nama study group wajib diisi');
      return;
    }
    if (!formData.course_id) {
      toast.error('Pilih course terlebih dahulu');
      return;
    }

    try {
      setSubmitting(true);
      const payload = {
        name: formData.name.trim(),
        course_id: formData.course_id,
        description: formData.description.trim(),
        member_ids: [], // Initial empty, creator will be added automatically
      };

      const data = await apiFetch('/collab/study-groups', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      toast.success(`Study group "${data.study_group.name}" berhasil dibuat!`);
      setCreateDialogOpen(false);
      resetForm();
      fetchStudyGroups(); // Refresh list
    } catch (error) {
      console.error('Error creating study group:', error);
      toast.error(error.message || 'Gagal membuat study group');
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      course_id: '',
      description: '',
    });
  };

  const formatRelativeTime = (isoDate) => {
    if (!isoDate) return 'Tidak ada aktivitas';
    const date = new Date(isoDate);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Baru saja';
    if (diffMins < 60) return `${diffMins} menit lalu`;
    if (diffHours < 24) return `${diffHours} jam lalu`;
    if (diffDays < 7) return `${diffDays} hari lalu`;
    return date.toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' });
  };

  if (loading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6" data-testid="study-groups-view">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Users className="h-6 w-6 text-purple-600" />
            Study Groups
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Kolaborasi belajar bersama teman-teman di course yang sama
          </p>
        </div>
        <Button 
          onClick={() => setCreateDialogOpen(true)}
          className="flex items-center gap-2"
          data-testid="create-study-group-btn"
        >
          <Plus className="h-4 w-4" />
          Buat Study Group
        </Button>
      </div>

      {/* Empty State */}
      {groups.length === 0 && (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Users className="h-16 w-16 text-muted-foreground/50 mb-4" />
            <h3 className="text-lg font-semibold mb-2">Belum ada Study Group</h3>
            <p className="text-sm text-muted-foreground text-center max-w-md mb-4">
              Buat study group untuk belajar bersama teman-teman di course yang sama.
              Study group dilengkapi dengan channel diskusi dan folder dokumen bersama.
            </p>
            <Button onClick={() => setCreateDialogOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Buat Study Group Pertama
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Study Groups Grid */}
      {groups.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3" data-testid="study-groups-grid">
          {groups.map((group) => (
            <Card 
              key={group.id} 
              className="hover:shadow-lg transition-shadow cursor-pointer group"
              onClick={() => onNavigate('study-group-detail', { groupId: group.id })}
              data-testid={`study-group-card-${group.id}`}
            >
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <CardTitle className="text-lg flex items-center gap-2 group-hover:text-purple-600 transition-colors">
                      <Users className="h-5 w-5" />
                      {group.name}
                    </CardTitle>
                    {group.course && (
                      <CardDescription className="flex items-center gap-1 mt-1">
                        <BookOpen className="h-3 w-3" />
                        {group.course.title}
                      </CardDescription>
                    )}
                  </div>
                </div>
              </CardHeader>

              <CardContent className="space-y-3">
                {/* Description */}
                {group.description && (
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {group.description}
                  </p>
                )}

                {/* Stats */}
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="flex items-center gap-2 p-2 bg-muted/30 rounded">
                    <Users className="h-4 w-4 text-purple-600" />
                    <span className="font-medium">{group.member_count || 0} Anggota</span>
                  </div>
                  {group.last_activity_at && (
                    <div className="flex items-center gap-2 p-2 bg-muted/30 rounded">
                      <TrendingUp className="h-4 w-4 text-green-600" />
                      <span className="font-medium">Aktif</span>
                    </div>
                  )}
                </div>

                {/* Last Activity */}
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Calendar className="h-3 w-3" />
                  {formatRelativeTime(group.last_activity_at || group.created_at)}
                </div>

                {/* Action Button */}
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="w-full group-hover:bg-purple-600 group-hover:text-foreground transition-colors"
                  onClick={(e) => {
                    e.stopPropagation();
                    onNavigate('study-group-detail', { groupId: group.id });
                  }}
                >
                  Buka Group
                  <ArrowRight className="h-4 w-4 ml-2" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="sm:max-w-md" data-testid="create-study-group-dialog">
          <DialogHeader>
            <DialogTitle>Buat Study Group Baru</DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Name */}
            <div className="space-y-2">
              <Label htmlFor="group-name">Nama Study Group</Label>
              <Input
                id="group-name"
                data-testid="group-name-input"
                placeholder="e.g. Safety Training Kelompok A"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </div>

            {/* Course Selection */}
            <div className="space-y-2">
              <Label htmlFor="course-select">Course</Label>
              <Select
                value={formData.course_id}
                onValueChange={(value) => setFormData({ ...formData, course_id: value })}
              >
                <SelectTrigger id="course-select" data-testid="course-select">
                  <SelectValue placeholder="Pilih course" />
                </SelectTrigger>
                <SelectContent>
                  {courses.map((course) => (
                    <SelectItem key={course.course_id} value={course.course_id}>
                      {course.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Hanya bisa menambahkan member yang terdaftar di course ini
              </p>
            </div>

            {/* Description */}
            <div className="space-y-2">
              <Label htmlFor="group-desc">Deskripsi (opsional)</Label>
              <Textarea
                id="group-desc"
                data-testid="group-description-input"
                placeholder="Jelaskan tujuan study group ini..."
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                rows={3}
              />
            </div>

            {/* Info Box */}
            <div className="bg-purple-50 dark:bg-purple-950/20 border border-purple-200 dark:border-purple-800 rounded-lg p-3 space-y-2">
              <p className="text-xs font-medium text-purple-900 dark:text-purple-100">
                Yang akan dibuat otomatis:
              </p>
              <div className="space-y-1 text-xs text-purple-700 dark:text-purple-300">
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-3 w-3" />
                  Channel diskusi private untuk anggota
                </div>
                <div className="flex items-center gap-2">
                  <FolderOpen className="h-3 w-3" />
                  Folder workspace untuk berbagi dokumen
                </div>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button 
              variant="outline" 
              onClick={() => {
                setCreateDialogOpen(false);
                resetForm();
              }}
            >
              Batal
            </Button>
            <Button 
              onClick={handleCreateGroup}
              disabled={submitting}
              data-testid="submit-create-group-btn"
            >
              {submitting ? 'Membuat...' : 'Buat Study Group'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
