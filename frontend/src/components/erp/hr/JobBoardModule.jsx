import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { Briefcase, Plus, Search, Send, Loader2, MapPin, DollarSign, Calendar, Award, TrendingUp, FileText } from 'lucide-react';
import { IconButton } from '../IconButton';

const MATCH_COLOR = { 
  'Strongly Recommended': '#10b981',
  'Recommended': '#3b82f6',
  'Consider': '#f59e0b',
  'Not Recommended': '#ef4444'
};

export default function JobBoardModule({ token }) {
  const [activeTab, setActiveTab] = useState('browse'); // browse, my-applications, post, career-paths
  const [jobs, setJobs] = useState([]);
  const [myApplications, setMyApplications] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [loading, setLoading] = useState(false);
  const [userRole, setUserRole] = useState('');
  
  // Post job dialog
  const [showPostDialog, setShowPostDialog] = useState(false);
  const [jobForm, setJobForm] = useState({
    title: '',
    department: '',
    location: '',
    job_type: 'full-time',
    level: 'mid',
    description: '',
    responsibilities: [],
    required_skills: [],
    preferred_skills: [],
    salary_range_min: null,
    salary_range_max: null,
    deadline: ''
  });
  
  // Apply dialog
  const [showApplyDialog, setShowApplyDialog] = useState(false);
  const [applyForm, setApplyForm] = useState({
    job_id: '',
    cover_letter: '',
    additional_info: '',
    resume_url: ''
  });

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/job-board/jobs?status=open`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setJobs(data?.data || []);
    } catch (e) {
      toast.error(`Gagal memuat jobs: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  const fetchMyApplications = useCallback(async () => {
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/job-board/applications/my`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setMyApplications(data?.data || []);
    } catch (e) {
      toast.error(`Gagal memuat aplikasi: ${e.message}`);
    }
  }, [headers]);

  useEffect(() => {
    fetchJobs();
    fetchMyApplications();
    // Get user role from token (simplified - could decode JWT)
    setUserRole('user'); // Default
  }, [fetchJobs, fetchMyApplications]);

  const handleViewJob = async (jobId) => {
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/job-board/jobs/${jobId}`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSelectedJob(data?.data);
    } catch (e) {
      toast.error(`Gagal load detail: ${e.message}`);
    }
  };

  const handlePostJob = async () => {
    if (!jobForm.title || !jobForm.department || !jobForm.description) {
      toast.error('Lengkapi form job posting');
      return;
    }

    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/job-board/jobs`, {
        method: 'POST',
        headers,
        body: JSON.stringify(jobForm)
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Job berhasil diposting!');
      setShowPostDialog(false);
      setJobForm({
        title: '', department: '', location: '', job_type: 'full-time', level: 'mid',
        description: '', responsibilities: [], required_skills: [], preferred_skills: [],
        salary_range_min: null, salary_range_max: null, deadline: ''
      });
      fetchJobs();
    } catch (e) {
      toast.error(`Post job gagal: ${e.message}`);
    }
  };

  const handleApply = async () => {
    if (!applyForm.cover_letter) {
      toast.error('Cover letter harus diisi');
      return;
    }

    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/job-board/applications`, {
        method: 'POST',
        headers,
        body: JSON.stringify(applyForm)
      });
      if (!r.ok) {
        const errorData = await r.json();
        throw new Error(errorData.detail || `HTTP ${r.status}`);
      }
      toast.success('Aplikasi berhasil dikirim!');
      setShowApplyDialog(false);
      setApplyForm({ job_id: '', cover_letter: '', additional_info: '', resume_url: '' });
      fetchMyApplications();
      setSelectedJob(null);
    } catch (e) {
      toast.error(`Aplikasi gagal: ${e.message}`);
    }
  };

  const openApplyDialog = (job) => {
    setApplyForm({ ...applyForm, job_id: job.id });
    setShowApplyDialog(true);
  };

  return (
    <div className="space-y-6 p-6" data-testid="job-board-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center">
            <Briefcase className="w-5 h-5 text-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Internal Job Board</h1>
            <p className="text-sm text-muted-foreground">Peluang karir internal & pengembangan</p>
          </div>
        </div>
        {(userRole === 'hr' || userRole === 'manager') && (
          <Button onClick={() => setShowPostDialog(true)}>
            <Plus className="w-4 h-4 mr-2" /> Post Job
          </Button>
        )}
      </div>

      {/* Tabs */}
      <GlassCard className="p-1">
        <div className="flex gap-1">
          <button
            onClick={() => setActiveTab('browse')}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'browse' ? 'bg-[var(--glass-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Search className="w-4 h-4 inline-block mr-2" />
            Browse Jobs
          </button>
          <button
            onClick={() => setActiveTab('my-applications')}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'my-applications' ? 'bg-[var(--glass-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <FileText className="w-4 h-4 inline-block mr-2" />
            My Applications
          </button>
          <button
            onClick={() => setActiveTab('career-paths')}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'career-paths' ? 'bg-[var(--glass-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <TrendingUp className="w-4 h-4 inline-block mr-2" />
            Career Paths
          </button>
        </div>
      </GlassCard>

      {/* Browse Jobs Tab */}
      {activeTab === 'browse' && (
        <div className="space-y-4">
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
            </div>
          ) : jobs.length === 0 ? (
            <GlassCard className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <Briefcase className="w-16 h-16 text-muted-foreground/40 mb-4" />
                <p className="text-sm text-muted-foreground">Belum ada lowongan tersedia saat ini.</p>
              </div>
            </GlassCard>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {jobs.map(job => (
                <GlassCard key={job.id} className="p-5 hover:bg-[var(--glass-hover)] transition-colors cursor-pointer" onClick={() => handleViewJob(job.id)}>
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1 min-w-0">
                      <h3 className="text-lg font-semibold text-foreground mb-1">{job.title}</h3>
                      <p className="text-sm text-muted-foreground">{job.department}</p>
                    </div>
                    <Badge variant={job.status === 'open' ? 'default' : 'secondary'}>{job.level}</Badge>
                  </div>

                  <div className="space-y-2 mb-4">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <MapPin className="w-3 h-3" />
                      <span>{job.location}</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Calendar className="w-3 h-3" />
                      <span>Deadline: {new Date(job.deadline).toLocaleDateString('id-ID')}</span>
                    </div>
                    {job.salary_range_min && job.salary_range_max && (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <DollarSign className="w-3 h-3" />
                        <span>Rp {job.salary_range_min.toLocaleString()} - Rp {job.salary_range_max.toLocaleString()}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">{job.application_count || 0} aplikasi</span>
                    <Button size="sm" onClick={(e) => { e.stopPropagation(); openApplyDialog(job); }}>
                      <Send className="w-3 h-3 mr-1" /> Apply
                    </Button>
                  </div>
                </GlassCard>
              ))}
            </div>
          )}
        </div>
      )}

      {/* My Applications Tab */}
      {activeTab === 'my-applications' && (
        <div className="space-y-4">
          {myApplications.length === 0 ? (
            <GlassCard className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <FileText className="w-16 h-16 text-muted-foreground/40 mb-4" />
                <p className="text-sm text-muted-foreground">Anda belum pernah melamar pekerjaan.</p>
              </div>
            </GlassCard>
          ) : (
            <div className="space-y-3">
              {myApplications.map(app => (
                <GlassCard key={app.id} className="p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1 min-w-0">
                      <h3 className="text-lg font-semibold text-foreground mb-1">{app.job_title}</h3>
                      <p className="text-sm text-muted-foreground">Applied: {new Date(app.applied_at).toLocaleDateString('id-ID')}</p>
                    </div>
                    <Badge variant={
                      app.status === 'accepted' ? 'default' :
                      app.status === 'rejected' ? 'destructive' :
                      app.status === 'shortlisted' ? 'secondary' : 'outline'
                    }>
                      {app.status}
                    </Badge>
                  </div>

                  {app.cover_letter && (
                    <div className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] mb-3">
                      <p className="text-xs text-muted-foreground line-clamp-2">{app.cover_letter}</p>
                    </div>
                  )}
                </GlassCard>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Career Paths Tab */}
      {activeTab === 'career-paths' && (
        <GlassCard className="p-8">
          <div className="text-center">
            <TrendingUp className="w-16 h-16 text-indigo-500 mx-auto mb-4" />
            <h2 className="text-xl font-bold text-foreground mb-2">Career Path Visualization</h2>
            <p className="text-sm text-muted-foreground mb-6">Eksplorasi jalur karir yang tersedia di perusahaan</p>
            <p className="text-xs text-muted-foreground">Feature coming soon: Interactive career path tree & role progression visualization</p>
          </div>
        </GlassCard>
      )}

      {/* Job Detail Dialog */}
      {selectedJob && (
        <Dialog open={!!selectedJob} onOpenChange={() => setSelectedJob(null)}>
          <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{selectedJob.title}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              {/* Basic Info */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground">Department</p>
                  <p className="text-sm font-medium">{selectedJob.department}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Location</p>
                  <p className="text-sm font-medium">{selectedJob.location}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Level</p>
                  <Badge>{selectedJob.level}</Badge>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Type</p>
                  <Badge variant="outline">{selectedJob.job_type}</Badge>
                </div>
              </div>

              {/* Skill Match */}
              {selectedJob.skill_match && (
                <div className="p-4 rounded-xl" style={{ background: `${MATCH_COLOR[selectedJob.skill_match.recommendation]}15`, border: `1px solid ${MATCH_COLOR[selectedJob.skill_match.recommendation]}35` }}>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-sm font-semibold text-foreground">Your Match Score</h4>
                    <div className="text-2xl font-bold" style={{ color: MATCH_COLOR[selectedJob.skill_match.recommendation] }}>
                      {selectedJob.skill_match.overall_score}%
                    </div>
                  </div>
                  <Badge style={{ background: MATCH_COLOR[selectedJob.skill_match.recommendation] }}>
                    {selectedJob.skill_match.recommendation}
                  </Badge>
                  
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-muted-foreground">Required Skills Match:</span>
                      <span className="font-medium ml-1">{selectedJob.skill_match.required_match}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Preferred Skills Match:</span>
                      <span className="font-medium ml-1">{selectedJob.skill_match.preferred_match}</span>
                    </div>
                  </div>

                  {selectedJob.skill_match.missing_required && selectedJob.skill_match.missing_required.length > 0 && (
                    <div className="mt-3">
                      <p className="text-xs text-muted-foreground mb-1">Missing Required Skills:</p>
                      <div className="flex flex-wrap gap-1">
                        {selectedJob.skill_match.missing_required.map((skill, i) => (
                          <Badge key={i} variant="destructive" className="text-xs">{skill}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Description */}
              <div>
                <h4 className="text-sm font-semibold text-foreground mb-2">Description</h4>
                <p className="text-sm text-muted-foreground leading-relaxed">{selectedJob.description}</p>
              </div>

              {/* Responsibilities */}
              {selectedJob.responsibilities && selectedJob.responsibilities.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-2">Responsibilities</h4>
                  <ul className="space-y-1">
                    {selectedJob.responsibilities.map((resp, i) => (
                      <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                        <span className="text-blue-500 mt-1">•</span>{resp}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Skills */}
              <div>
                <h4 className="text-sm font-semibold text-foreground mb-2">Required Skills</h4>
                <div className="flex flex-wrap gap-2">
                  {selectedJob.required_skills?.map((skill, i) => (
                    <Badge key={i} variant="default">{skill}</Badge>
                  ))}
                </div>
              </div>

              {selectedJob.preferred_skills && selectedJob.preferred_skills.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-2">Preferred Skills</h4>
                  <div className="flex flex-wrap gap-2">
                    {selectedJob.preferred_skills.map((skill, i) => (
                      <Badge key={i} variant="outline">{skill}</Badge>
                    ))}
                  </div>
                </div>
              )}

              <Button onClick={() => openApplyDialog(selectedJob)} className="w-full">
                <Send className="w-4 h-4 mr-2" /> Apply for this Position
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Post Job Dialog */}
      <Dialog open={showPostDialog} onOpenChange={setShowPostDialog}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Post New Job</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Job Title *</Label>
                <Input value={jobForm.title} onChange={e => setJobForm({ ...jobForm, title: e.target.value })} placeholder="Senior Developer" />
              </div>
              <div>
                <Label>Department *</Label>
                <Input value={jobForm.department} onChange={e => setJobForm({ ...jobForm, department: e.target.value })} placeholder="Engineering" />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <Label>Location</Label>
                <Input value={jobForm.location} onChange={e => setJobForm({ ...jobForm, location: e.target.value })} placeholder="Jakarta" />
              </div>
              <div>
                <Label>Job Type</Label>
                <Select value={jobForm.job_type} onValueChange={v => setJobForm({ ...jobForm, job_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="full-time">Full-time</SelectItem>
                    <SelectItem value="part-time">Part-time</SelectItem>
                    <SelectItem value="contract">Contract</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Level</Label>
                <Select value={jobForm.level} onValueChange={v => setJobForm({ ...jobForm, level: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="junior">Junior</SelectItem>
                    <SelectItem value="mid">Mid</SelectItem>
                    <SelectItem value="senior">Senior</SelectItem>
                    <SelectItem value="lead">Lead</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label>Description *</Label>
              <Textarea value={jobForm.description} onChange={e => setJobForm({ ...jobForm, description: e.target.value })} rows={3} />
            </div>

            <div>
              <Label>Deadline</Label>
              <Input type="date" value={jobForm.deadline} onChange={e => setJobForm({ ...jobForm, deadline: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPostDialog(false)}>Cancel</Button>
            <Button onClick={handlePostJob}><Plus className="w-4 h-4 mr-2" /> Post Job</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Apply Dialog */}
      <Dialog open={showApplyDialog} onOpenChange={setShowApplyDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Apply for Position</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Cover Letter *</Label>
              <Textarea
                value={applyForm.cover_letter}
                onChange={e => setApplyForm({ ...applyForm, cover_letter: e.target.value })}
                placeholder="Jelaskan mengapa Anda cocok untuk posisi ini..."
                rows={5}
              />
            </div>
            <div>
              <Label>Additional Info (Optional)</Label>
              <Textarea
                value={applyForm.additional_info}
                onChange={e => setApplyForm({ ...applyForm, additional_info: e.target.value })}
                rows={2}
              />
            </div>
            <div>
              <Label>Resume URL (Optional)</Label>
              <Input
                value={applyForm.resume_url}
                onChange={e => setApplyForm({ ...applyForm, resume_url: e.target.value })}
                placeholder="https://..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowApplyDialog(false)}>Cancel</Button>
            <Button onClick={handleApply}><Send className="w-4 h-4 mr-2" /> Submit Application</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
