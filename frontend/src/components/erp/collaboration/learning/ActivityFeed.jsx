/**
 * ActivityFeed.jsx
 * Phase 3.5 — Unified activity stream for Portal Kolaborasi.
 * Shows recent events: course enrollments, material completions, assignment submissions,
 * document updates.
 */
import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { formatDistanceToNow } from 'date-fns';
import { id as localeId } from 'date-fns/locale';
import apiFetch from '@/lib/apiFetch';

function timeAgo(ts) {
  if (!ts) return '';
  try {
    return formatDistanceToNow(new Date(ts), { addSuffix: true, locale: localeId });
  } catch {
    return '';
  }
}

const TYPE_COLORS = {
  course_enroll:         'bg-green-100 text-green-700',
  material_complete_video:   'bg-blue-100 text-blue-700',
  material_complete_text:    'bg-indigo-100 text-indigo-700',
  material_complete_pdf:     'bg-amber-100 text-amber-700',
  material_complete_quiz:    'bg-yellow-100 text-yellow-700',
  material_complete_assignment: 'bg-orange-100 text-orange-700',
  assignment_submit:     'bg-orange-100 text-orange-700',
  document_update:       'bg-muted text-foreground',
  message:               'bg-purple-100 text-purple-700',
};

const TYPE_LABELS = {
  course_enroll:         'Enroll',
  material_complete_video:   'Video',
  material_complete_text:    'Teks',
  material_complete_pdf:     'PDF',
  material_complete_quiz:    'Quiz',
  material_complete_assignment: 'Tugas',
  assignment_submit:     'Tugas',
  document_update:       'Dokumen',
  message:               'Pesan',
};

export default function ActivityFeed({ onNavigate }) {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);

  const fetchFeed = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch(`/collab/activity-feed?limit=20&days=${days}`);
      setActivities(data.activities || []);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { fetchFeed(); }, [fetchFeed]);

  const handleActivityClick = (activity) => {
    if (!onNavigate) return;
    if (activity.subject_type === 'course') {
      onNavigate('course-detail', activity.subject_id);
    } else if (activity.subject_type === 'document') {
      onNavigate('workspace');
    }
  };

  return (
    <Card className="h-full" data-testid="activity-feed">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            ⚡ Aktivitas Terkini
          </CardTitle>
          <div className="flex gap-1">
            {[3, 7, 14].map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`text-xs px-2 py-0.5 rounded transition-colors ${
                  days === d
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent'
                }`}
              >
                {d}h
              </button>
            ))}
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-0">
        {loading ? (
          <div className="space-y-3">
            {[1,2,3].map(i => (
              <div key={i} className="flex gap-3 animate-pulse">
                <div className="w-8 h-8 bg-muted rounded-full flex-shrink-0" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 bg-muted rounded w-3/4" />
                  <div className="h-2.5 bg-muted rounded w-1/2" />
                </div>
              </div>
            ))}
          </div>
        ) : activities.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <div className="text-3xl mb-2">📊</div>
            <p className="text-sm">Belum ada aktivitas dalam {days} hari terakhir</p>
          </div>
        ) : (
          <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
            {activities.map((activity) => (
              <div
                key={activity.id}
                className="flex gap-3 cursor-pointer hover:bg-accent/50 p-2 rounded-lg transition-colors group"
                onClick={() => handleActivityClick(activity)}
                data-testid={`activity-item-${activity.type}`}
              >
                {/* Icon */}
                <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center flex-shrink-0 text-base">
                  {activity.icon}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <p className="text-xs leading-relaxed">
                    <span className="font-medium">{activity.actor_name}</span>
                    {' '}
                    <span className="text-muted-foreground">{activity.action}</span>
                    {' '}
                    <span className="font-medium truncate">{activity.subject}</span>
                  </p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${TYPE_COLORS[activity.type] || 'bg-muted text-foreground'}`}>
                      {TYPE_LABELS[activity.type] || activity.type}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {timeAgo(activity.timestamp)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Refresh */}
        <Button
          variant="ghost"
          size="sm"
          className="w-full mt-2 text-xs text-muted-foreground h-7"
          onClick={fetchFeed}
        >
          ↻ Perbarui feed
        </Button>
      </CardContent>
    </Card>
  );
}
