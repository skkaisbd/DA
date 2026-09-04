/**
 * AssignmentSubmit.jsx
 * Form untuk submit assignment (text / link).
 * File upload disabled untuk MVP karena belum ada storage upload endpoint.
 */

import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { ClipboardList, CheckCircle2, Send, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import apiFetch from '@/lib/apiFetch';

export default function AssignmentSubmit({ material, existingSubmission, onSubmitted }) {
  const [submissionType, setSubmissionType] = useState(existingSubmission?.submission_type || 'text');
  const [textContent, setTextContent] = useState(existingSubmission?.text_content || '');
  const [linkUrl, setLinkUrl] = useState(existingSubmission?.link_url || '');
  const [submitting, setSubmitting] = useState(false);

  const isGraded = existingSubmission?.grade !== null && existingSubmission?.grade !== undefined;
  const isSubmitted = !!existingSubmission;

  const handleSubmit = async () => {
    // Validate
    if (submissionType === 'text' && !textContent.trim()) {
      toast.error('Mohon isi jawaban teks');
      return;
    }
    if (submissionType === 'link' && !linkUrl.trim()) {
      toast.error('Mohon isi URL link');
      return;
    }

    setSubmitting(true);
    try {
      await apiFetch(`/lms/student/assignments/${material.material_id}/submit`, {
        method: 'POST',
        body: JSON.stringify({
          submission_type: submissionType,
          text_content: submissionType === 'text' ? textContent : null,
          link_url: submissionType === 'link' ? linkUrl : null,
        })
      });
      toast.success(isSubmitted ? 'Tugas berhasil di-update' : 'Tugas berhasil di-submit');
      if (onSubmitted) onSubmitted();
    } catch (error) {
      console.error('Assignment submit error:', error);
      toast.error('Gagal submit assignment');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="assignment-submit-view">
      {/* Header */}
      <Card>
        <CardContent className="pt-6 space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <h3 className="font-semibold flex items-center gap-2">
                <ClipboardList size={18} />
                {material.title}
              </h3>
              {material.description && (
                <p className="text-sm text-muted-foreground mt-1">{material.description}</p>
              )}
              {material.content && (
                <div className="text-sm mt-2 p-3 bg-muted/30 rounded">
                  {material.content}
                </div>
              )}
            </div>
            {isGraded ? (
              <Badge className="bg-green-500">
                Graded: {existingSubmission.grade}/{existingSubmission.max_grade || 100}
              </Badge>
            ) : isSubmitted ? (
              <Badge variant="secondary">Submitted</Badge>
            ) : (
              <Badge variant="outline">Not submitted</Badge>
            )}
          </div>
          {isGraded && existingSubmission?.feedback && (
            <div className="text-sm border-l-4 border-green-500 pl-3 py-1 bg-muted/30">
              <p className="font-medium">Feedback Instruktur:</p>
              <p className="text-muted-foreground">{existingSubmission.feedback}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Submission form */}
      <Card>
        <CardContent className="pt-6 space-y-4">
          <Tabs value={submissionType} onValueChange={setSubmissionType}>
            <TabsList>
              <TabsTrigger value="text" data-testid="submission-tab-text">Teks</TabsTrigger>
              <TabsTrigger value="link" data-testid="submission-tab-link">Link</TabsTrigger>
            </TabsList>

            <TabsContent value="text" className="space-y-2">
              <Label htmlFor="assignment-text">Jawaban</Label>
              <Textarea
                id="assignment-text"
                value={textContent}
                onChange={(e) => setTextContent(e.target.value)}
                placeholder="Tulis jawaban Anda di sini..."
                rows={8}
                disabled={isGraded}
                data-testid="assignment-text-input"
              />
              <p className="text-xs text-muted-foreground">
                {textContent.length} karakter
              </p>
            </TabsContent>

            <TabsContent value="link" className="space-y-2">
              <Label htmlFor="assignment-link">URL Submission</Label>
              <Input
                id="assignment-link"
                type="url"
                value={linkUrl}
                onChange={(e) => setLinkUrl(e.target.value)}
                placeholder="https://docs.google.com/..."
                disabled={isGraded}
                data-testid="assignment-link-input"
              />
              {linkUrl && (
                <a
                  href={linkUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                >
                  <ExternalLink size={12} />
                  Preview link
                </a>
              )}
            </TabsContent>
          </Tabs>

          {!isGraded && (
            <Button
              onClick={handleSubmit}
              disabled={submitting}
              className="w-full"
              data-testid="assignment-submit-btn"
            >
              {submitting ? (
                'Mengirim...'
              ) : isSubmitted ? (
                <>
                  <Send size={16} className="mr-2" />
                  Update Submission
                </>
              ) : (
                <>
                  <Send size={16} className="mr-2" />
                  Submit Assignment
                </>
              )}
            </Button>
          )}

          {isGraded && (
            <div className="flex items-center gap-2 text-sm text-green-600">
              <CheckCircle2 size={16} />
              <span>Assignment sudah di-grade. Tidak bisa di-edit.</span>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
