import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import { Calendar, Clock, Users, Sparkles, Loader2, Plus, Trash2, CalendarCheck, Eye, Send } from 'lucide-react';
import { IconButton } from '../IconButton';

export default function ShiftSchedulerModule({ token }) {
  const [activeTab, setActiveTab] = useState('schedules'); // schedules, templates, generate
  const [schedules, setSchedules] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [selectedSchedule, setSelectedSchedule] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  
  // Template dialog
  const [showTemplateDialog, setShowTemplateDialog] = useState(false);
  const [templateForm, setTemplateForm] = useState({
    name: '',
    start_time: '08:00',
    end_time: '16:00',
    required_skills: [],
    min_employees: 1,
    max_employees: 5
  });
  
  // Generate dialog
  const [showGenerateDialog, setShowGenerateDialog] = useState(false);
  const [generateForm, setGenerateForm] = useState({
    start_date: '',
    end_date: '',
    department: '',
    shift_templates: [],
    constraints: {
      max_hours_per_week: 48,
      min_rest_hours: 12,
      prefer_consecutive_days: true,
      balance_workload: true
    }
  });

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchSchedules = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/shift-scheduler/schedules`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSchedules(data?.data || []);
    } catch (e) {
      toast.error(`Gagal memuat jadwal: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  const fetchTemplates = useCallback(async () => {
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/shift-scheduler/templates`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setTemplates(data?.data || []);
    } catch (e) {
      toast.error(`Gagal memuat template: ${e.message}`);
    }
  }, [headers]);

  useEffect(() => {
    fetchSchedules();
    fetchTemplates();
  }, [fetchSchedules, fetchTemplates]);

  const handleCreateTemplate = async () => {
    if (!templateForm.name || !templateForm.start_time || !templateForm.end_time) {
      toast.error('Lengkapi form template');
      return;
    }

    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/shift-scheduler/templates`, {
        method: 'POST',
        headers,
        body: JSON.stringify(templateForm)
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Template shift berhasil dibuat!');
      setShowTemplateDialog(false);
      setTemplateForm({ name: '', start_time: '08:00', end_time: '16:00', required_skills: [], min_employees: 1, max_employees: 5 });
      fetchTemplates();
    } catch (e) {
      toast.error(`Gagal membuat template: ${e.message}`);
    }
  };

  const handleDeleteTemplate = async (templateId) => {
    if (!confirm('Hapus template ini?')) return;
    
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/shift-scheduler/templates/${templateId}`, {
        method: 'DELETE',
        headers
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Template dihapus');
      fetchTemplates();
    } catch (e) {
      toast.error(`Gagal hapus template: ${e.message}`);
    }
  };

  const handleGenerateSchedule = async () => {
    if (!generateForm.start_date || !generateForm.end_date || generateForm.shift_templates.length === 0) {
      toast.error('Lengkapi form generate');
      return;
    }

    setGenerating(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/shift-scheduler/generate`, {
        method: 'POST',
        headers,
        body: JSON.stringify(generateForm)
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      toast.success('Jadwal berhasil digenerate!', { icon: <Sparkles className="w-4 h-4" /> });
      setShowGenerateDialog(false);
      fetchSchedules();
      setActiveTab('schedules');
    } catch (e) {
      toast.error(`Generate gagal: ${e.message}`);
    } finally {
      setGenerating(false);
    }
  };

  const handlePublishSchedule = async (scheduleId) => {
    if (!confirm('Publish jadwal ini? Karyawan akan bisa melihat jadwal mereka.')) return;
    
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/shift-scheduler/schedules/${scheduleId}/publish`, {
        method: 'PATCH',
        headers
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Jadwal dipublish!');
      fetchSchedules();
    } catch (e) {
      toast.error(`Publish gagal: ${e.message}`);
    }
  };

  const handleViewSchedule = async (scheduleId) => {
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/shift-scheduler/schedules/${scheduleId}`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSelectedSchedule(data?.data);
    } catch (e) {
      toast.error(`Gagal load detail: ${e.message}`);
    }
  };

  return (
    <div className="space-y-6 p-6" data-testid="shift-scheduler-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <Calendar className="w-5 h-5 text-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Auto Shift Scheduler</h1>
            <p className="text-sm text-muted-foreground">Generate jadwal shift otomatis dengan AI</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => setShowGenerateDialog(true)} variant="default">
            <Sparkles className="w-4 h-4 mr-2" /> Generate Schedule
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <GlassCard className="p-1">
        <div className="flex gap-1">
          <button
            onClick={() => setActiveTab('schedules')}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'schedules' ? 'bg-[var(--glass-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Calendar className="w-4 h-4 inline-block mr-2" />
            Jadwal
          </button>
          <button
            onClick={() => setActiveTab('templates')}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'templates' ? 'bg-[var(--glass-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Clock className="w-4 h-4 inline-block mr-2" />
            Template Shift
          </button>
        </div>
      </GlassCard>

      {/* Schedules Tab */}
      {activeTab === 'schedules' && (
        <div className="space-y-4">
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
            </div>
          ) : schedules.length === 0 ? (
            <GlassCard className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <Calendar className="w-16 h-16 text-muted-foreground/40 mb-4" />
                <p className="text-sm text-muted-foreground">Belum ada jadwal. Klik "Generate Schedule" untuk membuat jadwal baru.</p>
              </div>
            </GlassCard>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {schedules.map(schedule => (
                <GlassCard key={schedule.id} className="p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <CalendarCheck className="w-4 h-4 text-indigo-500" />
                        <h3 className="text-sm font-semibold text-foreground truncate">
                          {new Date(schedule.start_date).toLocaleDateString('id-ID')} - {new Date(schedule.end_date).toLocaleDateString('id-ID')}
                        </h3>
                      </div>
                      {schedule.department && (
                        <p className="text-xs text-muted-foreground">{schedule.department}</p>
                      )}
                    </div>
                    <Badge variant={schedule.status === 'published' ? 'default' : 'secondary'}>
                      {schedule.status === 'published' ? 'Published' : 'Draft'}
                    </Badge>
                  </div>

                  {schedule.metadata && (
                    <div className="grid grid-cols-2 gap-2 mb-3">
                      <div className="text-xs">
                        <span className="text-muted-foreground">Total Shift:</span>
                        <span className="font-semibold text-foreground ml-1">{schedule.metadata.total_shifts}</span>
                      </div>
                      <div className="text-xs">
                        <span className="text-muted-foreground">Avg Hours:</span>
                        <span className="font-semibold text-foreground ml-1">{schedule.metadata.average_hours_per_employee}</span>
                      </div>
                    </div>
                  )}

                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" className="flex-1" onClick={() => handleViewSchedule(schedule.id)}>
                      <Eye className="w-3 h-3 mr-1" /> View
                    </Button>
                    {schedule.status === 'draft' && (
                      <Button size="sm" className="flex-1" onClick={() => handlePublishSchedule(schedule.id)}>
                        <Send className="w-3 h-3 mr-1" /> Publish
                      </Button>
                    )}
                  </div>
                </GlassCard>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Templates Tab */}
      {activeTab === 'templates' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <Button onClick={() => setShowTemplateDialog(true)}>
              <Plus className="w-4 h-4 mr-2" /> Template Baru
            </Button>
          </div>

          {templates.length === 0 ? (
            <GlassCard className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <Clock className="w-16 h-16 text-muted-foreground/40 mb-4" />
                <p className="text-sm text-muted-foreground">Belum ada template shift. Buat template pertama Anda.</p>
              </div>
            </GlassCard>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {templates.map(template => (
                <GlassCard key={template.id} className="p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-semibold text-foreground mb-1">{template.name}</h3>
                      <p className="text-xs text-muted-foreground">{template.start_time} - {template.end_time}</p>
                    </div>
                    <IconButton icon={Trash2} variant="ghost" size="sm" onClick={() => handleDeleteTemplate(template.id)} tooltip="Hapus" />
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">Min/Max Employees:</span>
                      <span className="font-medium text-foreground">{template.min_employees} - {template.max_employees}</span>
                    </div>
                    {template.required_skills && template.required_skills.length > 0 && (
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Required Skills:</p>
                        <div className="flex flex-wrap gap-1">
                          {template.required_skills.map((skill, i) => (
                            <Badge key={i} variant="outline" className="text-xs">{skill}</Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </GlassCard>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Create Template Dialog */}
      <Dialog open={showTemplateDialog} onOpenChange={setShowTemplateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Buat Template Shift Baru</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Nama Template *</Label>
              <Input 
                placeholder="Misal: Morning Shift, Night Shift" 
                value={templateForm.name}
                onChange={e => setTemplateForm({ ...templateForm, name: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Start Time *</Label>
                <Input 
                  type="time" 
                  value={templateForm.start_time}
                  onChange={e => setTemplateForm({ ...templateForm, start_time: e.target.value })}
                />
              </div>
              <div>
                <Label>End Time *</Label>
                <Input 
                  type="time" 
                  value={templateForm.end_time}
                  onChange={e => setTemplateForm({ ...templateForm, end_time: e.target.value })}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Min Employees</Label>
                <Input 
                  type="number" 
                  min="1"
                  value={templateForm.min_employees}
                  onChange={e => setTemplateForm({ ...templateForm, min_employees: parseInt(e.target.value) })}
                />
              </div>
              <div>
                <Label>Max Employees</Label>
                <Input 
                  type="number" 
                  min="1"
                  value={templateForm.max_employees}
                  onChange={e => setTemplateForm({ ...templateForm, max_employees: parseInt(e.target.value) })}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowTemplateDialog(false)}>Batal</Button>
            <Button onClick={handleCreateTemplate}>
              <Plus className="w-4 h-4 mr-2" /> Buat Template
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Generate Schedule Dialog */}
      <Dialog open={showGenerateDialog} onOpenChange={setShowGenerateDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Generate Jadwal Shift Otomatis</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Start Date *</Label>
                <Input 
                  type="date"
                  value={generateForm.start_date}
                  onChange={e => setGenerateForm({ ...generateForm, start_date: e.target.value })}
                />
              </div>
              <div>
                <Label>End Date *</Label>
                <Input 
                  type="date"
                  value={generateForm.end_date}
                  onChange={e => setGenerateForm({ ...generateForm, end_date: e.target.value })}
                />
              </div>
            </div>
            <div>
              <Label>Department (Optional)</Label>
              <Select value={generateForm.department} onValueChange={v => setGenerateForm({ ...generateForm, department: v })}>
                <SelectTrigger>
                  <SelectValue placeholder="Semua departemen" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Semua Departemen</SelectItem>
                  <SelectItem value="Production">Production</SelectItem>
                  <SelectItem value="Warehouse">Warehouse</SelectItem>
                  <SelectItem value="QC">QC</SelectItem>
                  <SelectItem value="Finishing">Finishing</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Shift Templates * (Pilih minimal 1)</Label>
              <div className="border border-input rounded-lg p-3 space-y-2 max-h-32 overflow-y-auto">
                {templates.map(template => (
                  <div key={template.id} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id={`template-${template.id}`}
                      checked={generateForm.shift_templates.includes(template.id)}
                      onChange={e => {
                        const newTemplates = e.target.checked
                          ? [...generateForm.shift_templates, template.id]
                          : generateForm.shift_templates.filter(t => t !== template.id);
                        setGenerateForm({ ...generateForm, shift_templates: newTemplates });
                      }}
                      className="rounded"
                    />
                    <label htmlFor={`template-${template.id}`} className="text-sm cursor-pointer">
                      {template.name} ({template.start_time} - {template.end_time})
                    </label>
                  </div>
                ))}
              </div>
            </div>
            <div className="border-t pt-4">
              <h4 className="text-sm font-semibold mb-3">Constraints</h4>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label>Balance Workload</Label>
                  <Switch 
                    checked={generateForm.constraints.balance_workload}
                    onCheckedChange={v => setGenerateForm({ 
                      ...generateForm, 
                      constraints: { ...generateForm.constraints, balance_workload: v }
                    })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <Label>Prefer Consecutive Days</Label>
                  <Switch 
                    checked={generateForm.constraints.prefer_consecutive_days}
                    onCheckedChange={v => setGenerateForm({ 
                      ...generateForm, 
                      constraints: { ...generateForm.constraints, prefer_consecutive_days: v }
                    })}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Max Hours/Week</Label>
                    <Input 
                      type="number"
                      value={generateForm.constraints.max_hours_per_week}
                      onChange={e => setGenerateForm({ 
                        ...generateForm, 
                        constraints: { ...generateForm.constraints, max_hours_per_week: parseInt(e.target.value) }
                      })}
                    />
                  </div>
                  <div>
                    <Label>Min Rest Hours</Label>
                    <Input 
                      type="number"
                      value={generateForm.constraints.min_rest_hours}
                      onChange={e => setGenerateForm({ 
                        ...generateForm, 
                        constraints: { ...generateForm.constraints, min_rest_hours: parseInt(e.target.value) }
                      })}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowGenerateDialog(false)}>Batal</Button>
            <Button onClick={handleGenerateSchedule} disabled={generating}>
              {generating ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Generating...</> : <><Sparkles className="w-4 h-4 mr-2" /> Generate</>}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* View Schedule Detail Dialog */}
      {selectedSchedule && (
        <Dialog open={!!selectedSchedule} onOpenChange={() => setSelectedSchedule(null)}>
          <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Detail Jadwal Shift</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground">Periode</p>
                  <p className="text-sm font-medium">{new Date(selectedSchedule.start_date).toLocaleDateString('id-ID')} - {new Date(selectedSchedule.end_date).toLocaleDateString('id-ID')}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Department</p>
                  <p className="text-sm font-medium">{selectedSchedule.department || 'Semua'}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Status</p>
                  <Badge>{selectedSchedule.status}</Badge>
                </div>
              </div>

              {selectedSchedule.shifts && selectedSchedule.shifts.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold mb-2">Shift Assignments ({selectedSchedule.shifts.length})</h4>
                  <div className="max-h-96 overflow-y-auto space-y-2">
                    {selectedSchedule.shifts.map(shift => (
                      <div key={shift.id} className="flex items-center justify-between p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                        <div className="flex-1">
                          <p className="text-sm font-medium">{shift.employee_name}</p>
                          <p className="text-xs text-muted-foreground">{shift.department}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-medium">{shift.shift_name}</p>
                          <p className="text-xs text-muted-foreground">{shift.date} • {shift.start_time} - {shift.end_time}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
