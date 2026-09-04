import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { Target, Sparkles, MessageSquare, FileText, Loader2, Send, Brain, TrendingUp, Award, Calendar, BookOpen } from 'lucide-react';
import { IconButton } from '../IconButton';

export default function CareerCoachModule({ token }) {
  const [activeTab, setActiveTab] = useState('dashboard'); // dashboard, chat, reports
  const [profile, setProfile] = useState(null);
  const [reports, setReports] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [selectedReport, setSelectedReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [chatting, setChatting] = useState(false);
  
  // Generate report form
  const [reportForm, setReportForm] = useState({
    focus_area: 'overall',
    specific_goals: ''
  });
  
  // Chat
  const [chatMessage, setChatMessage] = useState('');
  const [chatHistory, setChatHistory] = useState([]);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchProfile = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/career-coach/profile`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setProfile(data?.data);
    } catch (e) {
      toast.error(`Gagal memuat profil: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  const fetchReports = useCallback(async () => {
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/career-coach/reports`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setReports(data?.data || []);
    } catch (e) {
      toast.error(`Gagal memuat reports: ${e.message}`);
    }
  }, [headers]);

  const fetchConversations = useCallback(async () => {
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/career-coach/chat/history`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setConversations(data?.data || []);
    } catch (e) {
      console.error('Failed to load conversations:', e);
    }
  }, [headers]);

  useEffect(() => {
    fetchProfile();
    fetchReports();
    fetchConversations();
  }, [fetchProfile, fetchReports, fetchConversations]);

  const handleGenerateReport = async () => {
    setGenerating(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/career-coach/generate-report`, {
        method: 'POST',
        headers,
        body: JSON.stringify(reportForm)
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      toast.success('Career report berhasil digenerate!', { icon: <Sparkles className="w-4 h-4" /> });
      setSelectedReport(data?.data);
      fetchReports();
      setActiveTab('reports');
    } catch (e) {
      toast.error(`Generate report gagal: ${e.message}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleSendChat = async () => {
    if (!chatMessage.trim()) return;

    const userMessage = { role: 'user', content: chatMessage, timestamp: new Date().toISOString() };
    setChatHistory([...chatHistory, userMessage]);
    setChatMessage('');
    setChatting(true);

    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/career-coach/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message: userMessage.content,
          conversation_id: currentConversation
        })
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      
      const aiMessage = { 
        role: 'assistant', 
        content: data?.data?.message || 'No response',
        timestamp: data?.data?.timestamp
      };
      
      setChatHistory(prev => [...prev, aiMessage]);
      setCurrentConversation(data?.data?.conversation_id);
      fetchConversations();
    } catch (e) {
      toast.error(`Chat gagal: ${e.message}`);
      setChatHistory(prev => [...prev, { role: 'error', content: `Error: ${e.message}`, timestamp: new Date().toISOString() }]);
    } finally {
      setChatting(false);
    }
  };

  const loadConversation = async (convId) => {
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/career-coach/chat/history?conversation_id=${convId}`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setChatHistory(data?.data?.messages || []);
      setCurrentConversation(convId);
    } catch (e) {
      toast.error(`Gagal load conversation: ${e.message}`);
    }
  };

  const startNewChat = () => {
    setChatHistory([]);
    setCurrentConversation(null);
    setChatMessage('');
  };

  return (
    <div className="space-y-6 p-6" data-testid="career-coach-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center">
            <Target className="w-5 h-5 text-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">AI Career Coach</h1>
            <p className="text-sm text-muted-foreground">Personalized career guidance dengan AI</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <GlassCard className="p-1">
        <div className="flex gap-1">
          <button
            onClick={() => setActiveTab('dashboard')}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'dashboard' ? 'bg-[var(--glass-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Target className="w-4 h-4 inline-block mr-2" />
            Dashboard
          </button>
          <button
            onClick={() => setActiveTab('chat')}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'chat' ? 'bg-[var(--glass-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <MessageSquare className="w-4 h-4 inline-block mr-2" />
            Chat Coaching
          </button>
          <button
            onClick={() => setActiveTab('reports')}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'reports' ? 'bg-[var(--glass-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <FileText className="w-4 h-4 inline-block mr-2" />
            Reports
          </button>
        </div>
      </GlassCard>

      {/* Dashboard Tab */}
      {activeTab === 'dashboard' && (
        <div className="space-y-6">
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
            </div>
          ) : profile ? (
            <>
              {/* Profile Summary */}
              <GlassCard className="p-6">
                <div className="flex items-start gap-4">
                  <div className="w-16 h-16 rounded-full bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center text-foreground font-bold text-xl shrink-0">
                    {profile.basic_info?.name?.charAt(0)}
                  </div>
                  <div className="flex-1">
                    <h2 className="text-xl font-bold text-foreground">{profile.basic_info?.name}</h2>
                    <p className="text-sm text-muted-foreground">{profile.basic_info?.job_title} • {profile.basic_info?.department}</p>
                    <div className="flex items-center gap-3 mt-2">
                      <Badge variant="outline">{profile.basic_info?.employee_code}</Badge>
                      <span className="text-xs text-muted-foreground">Tenure: {profile.basic_info?.tenure_years} tahun</span>
                    </div>
                  </div>
                </div>
              </GlassCard>

              {/* Quick Stats */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <GlassCard className="p-5">
                  <div className="flex items-center gap-3">
                    <Award className="w-8 h-8 text-amber-500" />
                    <div>
                      <p className="text-xs text-muted-foreground">Current Skills</p>
                      <p className="text-2xl font-bold text-foreground">{profile.current_skills?.length || 0}</p>
                    </div>
                  </div>
                </GlassCard>
                <GlassCard className="p-5">
                  <div className="flex items-center gap-3">
                    <BookOpen className="w-8 h-8 text-blue-500" />
                    <div>
                      <p className="text-xs text-muted-foreground">Training Completed</p>
                      <p className="text-2xl font-bold text-foreground">{profile.training_history?.length || 0}</p>
                    </div>
                  </div>
                </GlassCard>
                <GlassCard className="p-5">
                  <div className="flex items-center gap-3">
                    <TrendingUp className="w-8 h-8 text-green-500" />
                    <div>
                      <p className="text-xs text-muted-foreground">Avg Performance</p>
                      <p className="text-2xl font-bold text-foreground">
                        {profile.performance_history?.length > 0 
                          ? (profile.performance_history.reduce((sum, p) => sum + (p.score || 0), 0) / profile.performance_history.length).toFixed(1)
                          : 'N/A'}
                      </p>
                    </div>
                  </div>
                </GlassCard>
              </div>

              {/* Generate Report Section */}
              <GlassCard className="p-6">
                <h3 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-purple-500" />
                  Generate Career Report
                </h3>
                <div className="space-y-4">
                  <div>
                    <Label>Focus Area</Label>
                    <Select value={reportForm.focus_area} onValueChange={v => setReportForm({ ...reportForm, focus_area: v })}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="overall">Keseluruhan</SelectItem>
                        <SelectItem value="career_path">Career Path</SelectItem>
                        <SelectItem value="skills">Skill Development</SelectItem>
                        <SelectItem value="learning">Learning Resources</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Specific Goals (Optional)</Label>
                    <Textarea
                      placeholder="Jelaskan tujuan karir spesifik Anda..."
                      value={reportForm.specific_goals}
                      onChange={e => setReportForm({ ...reportForm, specific_goals: e.target.value })}
                      rows={3}
                    />
                  </div>
                  <Button onClick={handleGenerateReport} disabled={generating} className="w-full">
                    {generating ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Generating...</> : <><Sparkles className="w-4 h-4 mr-2" /> Generate Career Report</>}
                  </Button>
                </div>
              </GlassCard>
            </>
          ) : (
            <GlassCard className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <Target className="w-16 h-16 text-muted-foreground/40 mb-4" />
                <p className="text-sm text-muted-foreground">Gagal memuat profil karir</p>
              </div>
            </GlassCard>
          )}
        </div>
      )}

      {/* Chat Tab */}
      {activeTab === 'chat' && (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          {/* Conversation List */}
          <div className="lg:col-span-1">
            <GlassCard className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-foreground">Conversations</h3>
                <Button size="sm" variant="outline" onClick={startNewChat}>
                  <MessageSquare className="w-3 h-3 mr-1" /> New
                </Button>
              </div>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {conversations.map(conv => (
                  <div
                    key={conv.id}
                    onClick={() => loadConversation(conv.id)}
                    className={`p-3 rounded-lg cursor-pointer transition-colors ${
                      currentConversation === conv.id ? 'bg-[var(--glass-hover)] border border-primary' : 'bg-[var(--glass)] border border-[var(--glass-border)] hover:bg-[var(--glass-hover)]'
                    }`}
                  >
                    <p className="text-xs font-medium text-foreground line-clamp-1">
                      {conv.last_message?.content?.substring(0, 30) || 'New conversation'}...
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">{conv.message_count} messages</p>
                  </div>
                ))}
              </div>
            </GlassCard>
          </div>

          {/* Chat Interface */}
          <div className="lg:col-span-3">
            <GlassCard className="p-6 flex flex-col h-[600px]">
              <div className="flex-1 overflow-y-auto space-y-4 mb-4">
                {chatHistory.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-center">
                    <Brain className="w-16 h-16 text-purple-500/40 mb-4" />
                    <h3 className="text-lg font-semibold text-foreground mb-2">Start a Conversation</h3>
                    <p className="text-sm text-muted-foreground max-w-md">
                      Tanyakan apapun tentang karir Anda. AI coach akan memberikan guidance personal berdasarkan profil dan performa Anda.
                    </p>
                  </div>
                ) : (
                  chatHistory.map((msg, i) => (
                    <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[80%] p-3 rounded-lg ${
                        msg.role === 'user' ? 'bg-primary text-primary-foreground' :
                        msg.role === 'error' ? 'bg-destructive/10 text-destructive border border-destructive/20' :
                        'bg-[var(--glass)] border border-[var(--glass-border)]'
                      }`}>
                        <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                        <p className="text-xs opacity-70 mt-1">{new Date(msg.timestamp).toLocaleTimeString('id-ID')}</p>
                      </div>
                    </div>
                  ))
                )}
                {chatting && (
                  <div className="flex justify-start">
                    <div className="bg-[var(--glass)] border border-[var(--glass-border)] p-3 rounded-lg">
                      <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                    </div>
                  </div>
                )}
              </div>

              <div className="flex gap-2">
                <Textarea
                  placeholder="Tanyakan tentang karir Anda..."
                  value={chatMessage}
                  onChange={e => setChatMessage(e.target.value)}
                  onKeyPress={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), handleSendChat())}
                  rows={2}
                  disabled={chatting}
                />
                <Button onClick={handleSendChat} disabled={chatting || !chatMessage.trim()} className="shrink-0">
                  <Send className="w-4 h-4" />
                </Button>
              </div>
            </GlassCard>
          </div>
        </div>
      )}

      {/* Reports Tab */}
      {activeTab === 'reports' && (
        <div className="space-y-4">
          {reports.length === 0 ? (
            <GlassCard className="p-12">
              <div className="flex flex-col items-center justify-center text-center">
                <FileText className="w-16 h-16 text-muted-foreground/40 mb-4" />
                <p className="text-sm text-muted-foreground">Belum ada career report. Generate report pertama Anda di Dashboard.</p>
              </div>
            </GlassCard>
          ) : (
            <div className="space-y-3">
              {reports.map(report => (
                <GlassCard key={report.id} className="p-5 cursor-pointer hover:bg-[var(--glass-hover)] transition-colors" onClick={() => setSelectedReport(report)}>
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <h3 className="text-lg font-semibold text-foreground mb-1">
                        Career Report - {report.focus_area}
                      </h3>
                      <p className="text-xs text-muted-foreground">
                        Generated: {new Date(report.generated_at).toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' })}
                      </p>
                    </div>
                    <Badge variant="outline">View</Badge>
                  </div>
                  {report.report?.summary && (
                    <p className="text-sm text-muted-foreground line-clamp-2">{report.report.summary}</p>
                  )}
                </GlassCard>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Report Detail Dialog */}
      {selectedReport && (
        <Dialog open={!!selectedReport} onOpenChange={() => setSelectedReport(null)}>
          <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Career Coaching Report</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="p-4 rounded-lg bg-gradient-to-br from-purple-500/10 to-pink-500/10 border border-purple-300 dark:border-purple-500/20">
                <div className="flex items-center gap-2 mb-2">
                  <Target className="w-5 h-5 text-purple-500" />
                  <h3 className="text-sm font-semibold text-foreground">Focus: {selectedReport.focus_area}</h3>
                </div>
                <p className="text-xs text-muted-foreground">
                  Employee: {selectedReport.employee_name} • Generated: {new Date(selectedReport.generated_at).toLocaleDateString('id-ID')}
                </p>
              </div>

              {selectedReport.report?.full_report && (
                <div className="prose prose-sm max-w-none">
                  <div className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                    {selectedReport.report.full_report}
                  </div>
                </div>
              )}

              {selectedReport.report?.sections && Object.keys(selectedReport.report.sections).length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-foreground">Report Sections:</h4>
                  {Object.entries(selectedReport.report.sections).map(([key, value]) => (
                    <div key={key} className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                      <h5 className="text-xs font-semibold text-foreground uppercase mb-2">{key}</h5>
                      <p className="text-xs text-muted-foreground leading-relaxed">{value}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
