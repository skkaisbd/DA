import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  Brain, RefreshCw, Loader2, TrendingDown, Search, AlertTriangle,
  FileText, Sparkles, BarChart3, MessageSquare, CheckSquare, Save,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const API = process.env.REACT_APP_BACKEND_URL;

export default function RahazaAIModule({ headers }) {
  const { toast } = useToast();
  const [tab, setTab] = useState('summary');
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryDate, setSummaryDate] = useState(() => new Date().toISOString().slice(0, 10));

  const [rcQuestion, setRcQuestion] = useState('');
  const [rcAnswer, setRcAnswer] = useState(null);
  const [rcLoading, setRcLoading] = useState(false);

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);

  const [delays, setDelays] = useState(null);
  const [delaysLoading, setDelaysLoading] = useState(false);

  // Save-as-Task dialog
  const [taskDialog, setTaskDialog] = useState(null);
  const [savingTask, setSavingTask] = useState(false);

  const openSaveTask = (source, title, description, source_ref = '') => {
    setTaskDialog({
      source, source_ref,
      title: title.slice(0, 200),
      description: description || '',
      priority: 'medium',
      due_date: '',
    });
  };

  const submitTask = async () => {
    if (!taskDialog?.title?.trim()) { toast({ title: 'Judul wajib diisi', variant: 'destructive' }); return; }
    setSavingTask(true);
    try {
      await axios.post(`${API}/api/dewi/ai-actions`, taskDialog, { headers });
      toast({ title: 'Tersimpan sebagai Task', description: 'Buka menu "AI Action Items" untuk tracking.' });
      setTaskDialog(null);
    } catch (e) {
      toast({ title: 'Gagal simpan task', variant: 'destructive' });
    } finally { setSavingTask(false); }
  };

  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const { data } = await axios.get(`${API}/api/rahaza/ai/daily-summary`, { headers, params: { date: summaryDate } });
      setSummary(data);
    } catch (e) {
      toast({ title: 'Gagal memuat ringkasan AI', variant: 'destructive' });
    } finally { setSummaryLoading(false); }
  }, [headers, summaryDate, toast]);

  const loadDelays = useCallback(async () => {
    setDelaysLoading(true);
    try {
      const { data } = await axios.get(`${API}/api/rahaza/ai/predictive-delay`, { headers });
      setDelays(data);
    } catch (e) {} finally { setDelaysLoading(false); }
  }, [headers]);

  const handleRootCause = async () => {
    if (!rcQuestion.trim()) return;
    setRcLoading(true);
    try {
      const { data } = await axios.post(`${API}/api/rahaza/ai/root-cause`, { question: rcQuestion }, { headers });
      setRcAnswer(data);
    } catch (e) {
      toast({ title: 'Gagal', variant: 'destructive' });
    } finally { setRcLoading(false); }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    try {
      const { data } = await axios.post(`${API}/api/rahaza/ai/smart-search`, { query: searchQuery }, { headers });
      setSearchResults(data);
    } catch (e) {
      toast({ title: 'Gagal', variant: 'destructive' });
    } finally { setSearchLoading(false); }
  };

  useEffect(() => {
    if (tab === 'summary') loadSummary();
    if (tab === 'delay') loadDelays();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, loadSummary, loadDelays]);

  const RISK_COLORS = { high: 'text-red-600 bg-red-50', medium: 'text-yellow-600 bg-yellow-50', low: 'text-green-600 bg-green-50' };

  return (
    <div className="p-6 space-y-5">
      <div>
        <h2 className="text-xl font-semibold flex items-center gap-2"><Brain className="w-5 h-5 text-purple-500" /> AI Insights</h2>
        <p className="text-sm text-muted-foreground">Ringkasan harian, analisis akar masalah, dan prediksi delay berbasis data</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="summary"><Sparkles className="w-4 h-4 mr-1" /> Ringkasan Harian</TabsTrigger>
          <TabsTrigger value="rootcause"><BarChart3 className="w-4 h-4 mr-1" /> Root Cause</TabsTrigger>
          <TabsTrigger value="search"><Search className="w-4 h-4 mr-1" /> Smart Search</TabsTrigger>
          <TabsTrigger value="delay"><AlertTriangle className="w-4 h-4 mr-1" /> Prediksi Delay</TabsTrigger>
        </TabsList>

        {/* Daily Summary */}
        <TabsContent value="summary" className="mt-4 space-y-4">
          <div className="flex items-center gap-3">
            <input type="date" value={summaryDate} onChange={e => setSummaryDate(e.target.value)} className="border rounded px-2 py-1 text-sm bg-background" />
            <Button onClick={loadSummary} disabled={summaryLoading} size="sm">
              {summaryLoading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <RefreshCw className="w-4 h-4 mr-1" />} Generate
            </Button>
          </div>
          {summary && (
            <>
              <Card className="border-purple-200">
                <CardContent className="pt-4">
                  <div className="flex items-start gap-3">
                    <Sparkles className="w-5 h-5 text-purple-500 mt-0.5 flex-shrink-0" />
                    <p className="text-sm leading-relaxed flex-1">{summary.summary}</p>
                  </div>
                  <div className="flex items-center justify-between mt-3">
                    <p className="text-xs text-muted-foreground">Dihasilkan: {summary.generated_at?.slice(0, 16).replace('T', ' ')}</p>
                    <Button size="sm" variant="outline" onClick={() => openSaveTask('daily-summary', `Follow-up Ringkasan ${summaryDate}`, summary.summary, summaryDate)} data-testid="save-summary-task">
                      <CheckSquare className="w-3.5 h-3.5 mr-1" /> Simpan sbg Task
                    </Button>
                  </div>
                </CardContent>
              </Card>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: 'Output', value: `${summary.context?.total_output_pcs || 0} pcs` },
                  { label: 'Target', value: `${summary.context?.target_output_pcs || 0} pcs` },
                  { label: 'Efisiensi', value: `${summary.context?.efisiensi_pct || 0}%` },
                  { label: 'QC Fail Rate', value: `${summary.context?.fail_rate_pct || 0}%` },
                ].map(s => (
                  <Card key={s.label}><CardContent className="pt-3 pb-3">
                    <p className="text-xs text-muted-foreground">{s.label}</p>
                    <p className="text-lg font-bold">{s.value}</p>
                  </CardContent></Card>
                ))}
              </div>
            </>
          )}
          {!summary && !summaryLoading && (
            <div className="text-center py-8 text-muted-foreground">
              <Sparkles className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p>Klik Generate untuk membuat ringkasan harian AI</p>
            </div>
          )}
        </TabsContent>

        {/* Root Cause */}
        <TabsContent value="rootcause" className="mt-4 space-y-3">
          <p className="text-sm text-muted-foreground">Tanyakan analisis akar masalah produksi. AI akan menggunakan data real dari sistem.</p>
          <Textarea
            value={rcQuestion}
            onChange={e => setRcQuestion(e.target.value)}
            placeholder="Contoh: Kenapa QC fail rate tinggi di line A minggu ini?"
            rows={3}
          />
          <div className="flex gap-2">
            {[
              'Kenapa QC fail rate tinggi?',
              'Apa penyebab downtime terbanyak?',
              'Mengapa output turun minggu ini?',
            ].map(s => (
              <button key={s} onClick={() => setRcQuestion(s)} className="text-xs border rounded-full px-3 py-1 hover:bg-muted transition-colors">{s}</button>
            ))}
          </div>
          <Button onClick={handleRootCause} disabled={rcLoading || !rcQuestion.trim()}>
            {rcLoading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Brain className="w-4 h-4 mr-1" />} Analisis
          </Button>
          {rcAnswer && (
            <Card className="border-blue-200">
              <CardContent className="pt-4">
                <p className="text-xs font-medium text-muted-foreground mb-2">Pertanyaan: {rcAnswer.question}</p>
                <p className="text-sm whitespace-pre-wrap">{rcAnswer.analysis}</p>
                <div className="flex items-center justify-between mt-3">
                  <p className="text-xs text-muted-foreground">Periode data: {rcAnswer.data_period}</p>
                  <Button size="sm" variant="outline" onClick={() => openSaveTask('root-cause', `RCA: ${rcAnswer.question.slice(0, 80)}`, rcAnswer.analysis, rcAnswer.data_period)} data-testid="save-rca-task">
                    <CheckSquare className="w-3.5 h-3.5 mr-1" /> Simpan sbg Task
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Smart Search */}
        <TabsContent value="search" className="mt-4 space-y-3">
          <p className="text-sm text-muted-foreground">Cari WO, order, atau karyawan menggunakan kata-kata natural.</p>
          <div className="flex gap-2">
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="Contoh: WO terlambat, order PT Matahari, operator rajut"
              className="flex-1 border rounded px-3 py-2 text-sm bg-background"
            />
            <Button onClick={handleSearch} disabled={searchLoading}>
              {searchLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            </Button>
          </div>
          {searchResults && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">{searchResults.count} hasil untuk "{searchResults.query}"</p>
              {searchResults.results?.map((r, i) => (
                <Card key={i}><CardContent className="pt-3 pb-3">
                  <div className="flex items-center gap-3">
                    <Badge variant="outline" className="text-xs">{r.type}</Badge>
                    <span className="font-medium text-sm">{r.label}</span>
                    {r.customer && <span className="text-xs text-muted-foreground">{r.customer}</span>}
                    {r.status && <Badge variant="secondary" className="text-xs">{r.status}</Badge>}
                    {r.code && <span className="text-xs text-muted-foreground">{r.code}</span>}
                  </div>
                </CardContent></Card>
              ))}
              {!searchResults.results?.length && <p className="text-sm text-muted-foreground">Tidak ada hasil ditemukan.</p>}
            </div>
          )}
        </TabsContent>

        {/* Predictive Delay */}
        <TabsContent value="delay" className="mt-4 space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">WO dengan risiko keterlambatan berdasarkan output historis vs due date.</p>
            <Button variant="outline" size="sm" onClick={loadDelays} disabled={delaysLoading}>
              {delaysLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            </Button>
          </div>
          {delays && (
            <div className="grid grid-cols-2 gap-3 mb-3">
              <Card><CardContent className="pt-3 pb-3"><p className="text-xs text-muted-foreground">WO Dianalisis</p><p className="text-xl font-bold">{delays.total}</p></CardContent></Card>
              <Card><CardContent className="pt-3 pb-3"><p className="text-xs text-muted-foreground">Risiko Tinggi</p><p className="text-xl font-bold text-red-600">{delays.high_risk}</p></CardContent></Card>
            </div>
          )}
          {delaysLoading ? <div className="text-center py-8 text-muted-foreground">Memuat...</div> : (
            <div className="space-y-3">
              {(delays?.data || []).map(wo => (
                <Card key={wo.wo_id}>
                  <CardContent className="pt-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm">{wo.wo_number}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${RISK_COLORS[wo.risk_level] || ''}`}>{wo.risk_level} risk</span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">{wo.message}</p>
                      </div>
                      <div className="text-right text-xs text-muted-foreground">
                        <p>Due: {wo.due_date?.slice(0, 10)}</p>
                        <p>Sisa: {wo.days_left} hari</p>
                        <p className="text-red-600 font-medium">{wo.prob_delay_pct}% prob. delay</p>
                      </div>
                    </div>
                    {(wo.risk_level === 'high' || wo.risk_level === 'medium') && (
                      <div className="mt-2 pt-2 border-t border-border/50 flex justify-end">
                        <Button size="sm" variant="outline" className="h-7 text-xs"
                          onClick={() => openSaveTask('predictive-delay', `Cegah delay WO ${wo.wo_number}`, wo.message + `\n\nProb delay: ${wo.prob_delay_pct}%, due ${wo.due_date}, sisa ${wo.days_left} hari, butuh ${wo.days_needed} hari lagi.`, wo.wo_id)}
                          data-testid={`save-delay-task-${wo.wo_id}`}>
                          <CheckSquare className="w-3 h-3 mr-1" /> Simpan sbg Task
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
              {(delays?.data || []).length === 0 && !delaysLoading && (
                <div className="text-center py-8 text-muted-foreground">
                  <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  <p>Tidak ada WO aktif dengan prediksi delay.</p>
                </div>
              )}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Save as Task dialog */}
      {taskDialog && (
        <Dialog open onOpenChange={() => setTaskDialog(null)}>
          <DialogContent className="max-w-md">
            <DialogHeader><DialogTitle>Simpan sebagai Task</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div className="space-y-1">
                <Label>Judul</Label>
                <input value={taskDialog.title}
                  onChange={e => setTaskDialog(t => ({ ...t, title: e.target.value }))}
                  className="w-full border rounded px-3 py-2 text-sm bg-background"
                  data-testid="save-task-title" />
              </div>
              <div className="space-y-1">
                <Label>Rekomendasi AI</Label>
                <Textarea value={taskDialog.description} rows={5}
                  onChange={e => setTaskDialog(t => ({ ...t, description: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Prioritas</Label>
                  <Select value={taskDialog.priority} onValueChange={v => setTaskDialog(t => ({ ...t, priority: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Rendah</SelectItem>
                      <SelectItem value="medium">Sedang</SelectItem>
                      <SelectItem value="high">Tinggi</SelectItem>
                      <SelectItem value="critical">Kritis</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label>Due Date</Label>
                  <input type="date" value={taskDialog.due_date}
                    onChange={e => setTaskDialog(t => ({ ...t, due_date: e.target.value }))}
                    className="w-full border rounded px-3 py-2 text-sm bg-background" />
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setTaskDialog(null)}>Batal</Button>
              <Button onClick={submitTask} disabled={savingTask} data-testid="confirm-save-task">
                {savingTask ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
                Simpan Task
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
