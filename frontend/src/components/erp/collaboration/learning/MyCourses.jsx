/**
 * MyCourses.jsx
 * View all enrolled courses with filter tabs
 * FIXED: Using apiFetch utility for authentication
 */

import { useState, useEffect } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { 
  BookOpen, Clock, ArrowRight, CheckCircle2, PlayCircle,
  Calendar
} from 'lucide-react';
import { toast } from 'sonner';
import apiFetch from '@/lib/apiFetch';

const STATUS_TABS = [
  { value: 'all', label: 'All Courses' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'completed', label: 'Completed' },
  { value: 'not_started', label: 'Not Started' },
];

export default function MyCourses({ onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('all');
  const [courses, setCourses] = useState([]);

  useEffect(() => {
    fetchMyCourses();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const fetchMyCourses = async () => {
    try {
      setLoading(true);
      const data = await apiFetch(`/lms/student/my-courses?status=${activeTab}`);
      setCourses(data.courses || []);
    } catch (error) {
      console.error('Error fetching my courses:', error);
      toast.error('Gagal memuat courses');
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    const badges = {
      'completed': { label: 'Completed', variant: 'default', className: 'bg-green-500' },
      'in_progress': { label: 'In Progress', variant: 'default', className: 'bg-blue-500' },
      'not_started': { label: 'Not Started', variant: 'secondary' },
    };
    
    const badge = badges[status] || badges['not_started'];
    return <Badge variant={badge.variant} className={badge.className}>{badge.label}</Badge>;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' });
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold mb-2">📚 My Courses</h1>
          <p className="text-muted-foreground">
            Manage semua courses yang sudah Anda enroll
          </p>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            {STATUS_TABS.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value}>
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value={activeTab} className="mt-6">
            {loading ? (
              <div className="text-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
                <p className="text-sm text-muted-foreground mt-2">Loading courses...</p>
              </div>
            ) : courses.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center">
                  <BookOpen size={48} className="mx-auto mb-3 text-muted-foreground opacity-20" />
                  <p className="text-muted-foreground mb-4">
                    Belum ada course {activeTab !== 'all' ? `dengan status "${activeTab}"` : ''}
                  </p>
                  <Button onClick={() => onNavigate && onNavigate('catalog')}>
                    Browse Course Catalog
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <div className="grid grid-cols-1 gap-4">
                {courses.map((course) => (
                  <Card 
                    key={course.course_id}
                    className="cursor-pointer hover:shadow-md transition-shadow"
                    onClick={() => onNavigate && onNavigate('course-detail', course.course_id)}
                  >
                    <CardContent className="pt-6">
                      <div className="flex flex-col md:flex-row md:items-start gap-4">
                        {/* Course Info */}
                        <div className="flex-1 space-y-3">
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <h3 className="font-semibold text-lg mb-1">{course.title}</h3>
                              <p className="text-sm text-muted-foreground line-clamp-2">
                                {course.description}
                              </p>
                            </div>
                            {getStatusBadge(course.enrollment_status)}
                          </div>

                          {/* Meta */}
                          <div className="flex items-center gap-4 text-xs text-muted-foreground">
                            <div className="flex items-center gap-1">
                              <Badge variant="outline">{course.category}</Badge>
                            </div>
                            <div className="flex items-center gap-1">
                              <Clock size={14} />
                              {course.duration_hours}h
                            </div>
                            <div className="flex items-center gap-1">
                              <Calendar size={14} />
                              Enrolled: {formatDate(course.enrolled_at)}
                            </div>
                          </div>

                          {/* Progress */}
                          {course.enrollment_status !== 'not_started' && (
                            <div className="space-y-2">
                              <div className="flex items-center justify-between text-sm">
                                <span className="text-muted-foreground">
                                  Progress: {course.progress_percent}%
                                </span>
                                <span className="text-muted-foreground">
                                  {course.completed_items}/{course.total_items} completed
                                </span>
                              </div>
                              <Progress value={course.progress_percent} />
                            </div>
                          )}

                          {/* Next Material */}
                          {course.next_material && (
                            <div className="pt-3 border-t">
                              <p className="text-xs text-muted-foreground mb-1">Next:</p>
                              <div className="flex items-center gap-2">
                                <PlayCircle size={16} className="text-primary" />
                                <p className="text-sm font-medium">{course.next_material.title}</p>
                              </div>
                            </div>
                          )}

                          {/* Completed Badge */}
                          {course.enrollment_status === 'completed' && (
                            <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
                              <CheckCircle2 size={16} />
                              <span className="text-sm font-medium">
                                Completed on {formatDate(course.last_accessed)}
                              </span>
                            </div>
                          )}
                        </div>

                        {/* Action Button */}
                        <div className="flex md:flex-col gap-2">
                          {course.enrollment_status === 'completed' ? (
                            <Button variant="outline">
                              View Certificate
                            </Button>
                          ) : (
                            <Button>
                              {course.enrollment_status === 'not_started' ? 'Start Learning' : 'Continue'}
                              <ArrowRight size={16} className="ml-2" />
                            </Button>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
