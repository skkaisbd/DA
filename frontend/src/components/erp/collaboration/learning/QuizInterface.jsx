/**
 * QuizInterface.jsx
 * Multiple-choice quiz with submit & score result
 */

import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { CheckCircle2, XCircle, RotateCw, Award, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import apiFetch from '@/lib/apiFetch';

export default function QuizInterface({ material, onComplete }) {
  const questions = material?.questions || [];
  const [answers, setAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSelect = (questionIdx, choiceIdx) => {
    if (submitted) return;
    setAnswers(prev => ({ ...prev, [questionIdx]: choiceIdx }));
  };

  const handleSubmit = async () => {
    // Validate all answered
    if (Object.keys(answers).length < questions.length) {
      toast.error(`Mohon jawab semua ${questions.length} pertanyaan terlebih dahulu`);
      return;
    }

    setSubmitting(true);
    try {
      const answerArray = questions.map((_, idx) => answers[idx]);
      const data = await apiFetch(`/lms/student/quiz/${material.material_id}/submit`, {
        method: 'POST',
        body: JSON.stringify({ answers: answerArray, time_spent_seconds: 0 })
      });
      
      setResult(data);
      setSubmitted(true);
      
      if (data.passed) {
        toast.success(`Quiz lulus! Skor: ${data.score}/100`);
      } else {
        toast.error(`Skor: ${data.score}/100 (pass: ${data.pass_score}). Silakan coba lagi.`);
      }
      
      // Notify parent to refresh course data
      if (onComplete) onComplete(data);
    } catch (error) {
      console.error('Quiz submit error:', error);
      toast.error('Gagal submit quiz');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetry = () => {
    setAnswers({});
    setSubmitted(false);
    setResult(null);
  };

  if (questions.length === 0) {
    return (
      <div className="text-center py-8">
        <AlertCircle size={48} className="mx-auto mb-3 text-muted-foreground opacity-30" />
        <p className="text-muted-foreground">Quiz belum memiliki pertanyaan</p>
      </div>
    );
  }

  // RESULT VIEW
  if (submitted && result) {
    return (
      <div className="space-y-6" data-testid="quiz-result-view">
        {/* Score header */}
        <Card className={result.passed ? 'border-green-500' : 'border-amber-500'}>
          <CardContent className="pt-6 text-center space-y-3">
            {result.passed ? (
              <Award className="text-green-500 mx-auto" size={64} />
            ) : (
              <AlertCircle className="text-amber-500 mx-auto" size={64} />
            )}
            <div>
              <p className="text-sm text-muted-foreground">Skor Anda</p>
              <p className="text-5xl font-bold" data-testid="quiz-score">{result.score}<span className="text-2xl text-muted-foreground">/100</span></p>
              <p className="text-sm text-muted-foreground mt-1">
                {result.correct_count} dari {result.total_questions} benar
              </p>
            </div>
            <Badge
              variant="default"
              className={result.passed ? 'bg-green-500' : 'bg-amber-500'}
              data-testid="quiz-pass-badge"
            >
              {result.passed ? 'LULUS' : `BELUM LULUS (Min: ${result.pass_score})`}
            </Badge>
          </CardContent>
        </Card>

        {/* Detailed results */}
        <div className="space-y-3">
          <h3 className="font-semibold">Review Jawaban</h3>
          {result.detailed_results.map((r, idx) => {
            const q = questions[idx];
            return (
              <Card key={idx} className={r.is_correct ? '' : 'border-red-300'}>
                <CardContent className="pt-4 space-y-2">
                  <div className="flex items-start gap-2">
                    {r.is_correct ? (
                      <CheckCircle2 size={20} className="text-green-500 flex-shrink-0 mt-0.5" />
                    ) : (
                      <XCircle size={20} className="text-red-500 flex-shrink-0 mt-0.5" />
                    )}
                    <p className="font-medium text-sm">{idx + 1}. {r.question}</p>
                  </div>
                  <div className="ml-7 space-y-1 text-sm">
                    {q.choices.map((choice, ci) => {
                      const isCorrectChoice = ci === r.correct_index;
                      const isUserChoice = ci === r.user_answer_index;
                      let className = 'p-2 rounded border ';
                      if (isCorrectChoice) className += 'bg-green-100 dark:bg-green-500/10 border-green-500 ';
                      else if (isUserChoice && !r.is_correct) className += 'bg-red-100 dark:bg-red-500/10 border-red-500 ';
                      else className += 'border-transparent text-muted-foreground ';
                      
                      return (
                        <div key={ci} className={className}>
                          {isCorrectChoice && '✓ '}
                          {isUserChoice && !isCorrectChoice && '✗ '}
                          {choice}
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Actions */}
        {!result.passed && (
          <Button
            onClick={handleRetry}
            variant="outline"
            className="w-full"
            data-testid="quiz-retry-btn"
          >
            <RotateCw size={16} className="mr-2" />
            Coba Lagi
          </Button>
        )}
      </div>
    );
  }

  // QUIZ FORM VIEW
  const answeredCount = Object.keys(answers).length;
  const progress = Math.round((answeredCount / questions.length) * 100);

  return (
    <div className="space-y-6" data-testid="quiz-form-view">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">{material.title}</h3>
          <p className="text-sm text-muted-foreground">
            {questions.length} pertanyaan • Pass score: {material.pass_score || 70}
          </p>
        </div>
        <Badge variant="outline" data-testid="quiz-progress-counter">
          {answeredCount}/{questions.length} dijawab
        </Badge>
      </div>

      <div className="space-y-4">
        {questions.map((q, qIdx) => (
          <Card key={qIdx} data-testid={`quiz-question-${qIdx}`}>
            <CardContent className="pt-4 space-y-3">
              <p className="font-medium">{qIdx + 1}. {q.question}</p>
              <RadioGroup
                value={answers[qIdx]?.toString() || ''}
                onValueChange={(val) => handleSelect(qIdx, parseInt(val))}
              >
                {q.choices.map((choice, cIdx) => (
                  <div key={cIdx} className="flex items-center space-x-2">
                    <RadioGroupItem
                      value={cIdx.toString()}
                      id={`q${qIdx}-c${cIdx}`}
                      data-testid={`quiz-q${qIdx}-choice-${cIdx}`}
                    />
                    <Label
                      htmlFor={`q${qIdx}-c${cIdx}`}
                      className="cursor-pointer text-sm font-normal"
                    >
                      {choice}
                    </Label>
                  </div>
                ))}
              </RadioGroup>
            </CardContent>
          </Card>
        ))}
      </div>

      <Button
        onClick={handleSubmit}
        disabled={submitting || answeredCount < questions.length}
        className="w-full"
        size="lg"
        data-testid="quiz-submit-btn"
      >
        {submitting ? 'Memproses...' : `Submit Quiz (${answeredCount}/${questions.length})`}
      </Button>
    </div>
  );
}
