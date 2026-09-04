/**
 * LearningHome.jsx
 * Student Learning Dashboard - Home view
 * FIXED: Using apiFetch utility for authentication
 */

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { 
  GraduationCap, BookOpen, Award, TrendingUp, Clock, 
  ArrowRight, Calendar, Target, Flame 
} from 'lucide-react';
import { toast } from 'sonner';
import apiFetch from '@/lib/apiFetch';
import ActivityFeed from './ActivityFeed';

export default function LearningHome({ onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [activeCourses, setActiveCourses] = useState([]);
  const [stats, setStats] = useState({
    totalEnrolled: 0,
    completed: 0,
    inProgress: 0,
    certificates: 0,
    learningHours: 0,
  });

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      
      // Fetch my courses (in progress only) using apiFetch
      const data = await apiFetch('/lms/student/my-courses?status=in_progress');
      setActiveCourses(data.courses || []);
      
      // Fetch certificates for stats
      const certData = await apiFetch('/lms/student/certificates');
      setStats({
        totalEnrolled: certData.stats?.total_courses_enrolled || 0,
        completed: certData.stats?.total_certificates || 0,
        inProgress: data.courses?.length || 0,
        certificates: certData.stats?.total_certificates || 0,
        learningHours: certData.stats?.total_learning_hours || 0,
      });
      
    } catch (error) {
      console.error('Error fetching dashboard:', error);
      toast.error('Gagal memuat dashboard');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-2">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="text-sm text-muted-foreground">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold mb-2">🏠 Learning Home</h1>
          <p className="text-muted-foreground">
            Selamat datang di portal pembelajaran Anda!
          </p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">In Progress</p>
                  <p className="text-2xl font-bold">{stats.inProgress}</p>
                </div>
                <div className="h-12 w-12 rounded-full bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                  <BookOpen className="text-blue-500" size={24} />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Completed</p>
                  <p className="text-2xl font-bold">{stats.completed}</p>
                </div>
                <div className="h-12 w-12 rounded-full bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                  <Target className="text-green-500" size={24} />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Certificates</p>
                  <p className="text-2xl font-bold">{stats.certificates}</p>
                </div>
                <div className="h-12 w-12 rounded-full bg-amber-100 dark:bg-amber-500/10 flex items-center justify-center">
                  <Award className="text-amber-500" size={24} />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Learning Hours</p>
                  <p className="text-2xl font-bold">{stats.learningHours}</p>
                </div>
                <div className="h-12 w-12 rounded-full bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                  <Clock className="text-purple-500" size={24} />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Active Courses */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Flame className="text-orange-500" size={20} />
                Courses In Progress
              </CardTitle>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => onNavigate && onNavigate('my-courses')}
              >
                View All
                <ArrowRight size={16} className="ml-1" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {activeCourses.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <BookOpen size={48} className="mx-auto mb-3 opacity-20" />
                <p>Belum ada course yang sedang berjalan</p>
                <Button 
                  className="mt-4"
                  onClick={() => onNavigate && onNavigate('catalog')}
                >
                  Browse Course Catalog
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                {activeCourses.slice(0, 3).map((course) => (
                  <div 
                    key={course.course_id}
                    className="border rounded-lg p-4 hover:bg-muted/50 transition-colors cursor-pointer"
                    onClick={() => onNavigate && onNavigate('course-detail', course.course_id)}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1">
                        <h3 className="font-semibold">{course.title}</h3>
                        <p className="text-sm text-muted-foreground line-clamp-1">
                          {course.description}
                        </p>
                      </div>
                      <Badge variant="secondary">{course.category}</Badge>
                    </div>
                    
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
                    
                    {course.next_material && (
                      <div className="mt-3 pt-3 border-t">
                        <p className="text-xs text-muted-foreground mb-1">Next:</p>
                        <p className="text-sm font-medium">
                          {course.next_material.title}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="cursor-pointer hover:bg-muted/50 transition-colors" onClick={() => onNavigate && onNavigate('catalog')}>
            <CardContent className="pt-6">
              <div className="text-center space-y-2">
                <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto">
                  <BookOpen className="text-primary" size={32} />
                </div>
                <h3 className="font-semibold">Browse Courses</h3>
                <p className="text-sm text-muted-foreground">
                  Explore course catalog
                </p>
              </div>
            </CardContent>
          </Card>

          <Card className="cursor-pointer hover:bg-muted/50 transition-colors" onClick={() => onNavigate && onNavigate('my-courses')}>
            <CardContent className="pt-6">
              <div className="text-center space-y-2">
                <div className="h-16 w-16 rounded-full bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center mx-auto">
                  <GraduationCap className="text-blue-500" size={32} />
                </div>
                <h3 className="font-semibold">My Courses</h3>
                <p className="text-sm text-muted-foreground">
                  View all enrolled courses
                </p>
              </div>
            </CardContent>
          </Card>

          <Card className="cursor-pointer hover:bg-muted/50 transition-colors" onClick={() => onNavigate && onNavigate('certificates')}>
            <CardContent className="pt-6">
              <div className="text-center space-y-2">
                <div className="h-16 w-16 rounded-full bg-amber-100 dark:bg-amber-500/10 flex items-center justify-center mx-auto">
                  <Award className="text-amber-500" size={32} />
                </div>
                <h3 className="font-semibold">Certificates</h3>
                <p className="text-sm text-muted-foreground">
                  View earned certificates
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Activity Feed - Phase 3.5 */}
        <ActivityFeed onNavigate={onNavigate} />
      </div>
    </div>
  );
}
