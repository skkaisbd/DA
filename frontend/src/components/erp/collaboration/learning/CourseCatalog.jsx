/**
 * CourseCatalog.jsx
 * Browse and enroll in courses
 * FIXED: Using apiFetch utility for authentication
 */

import { useState, useEffect } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { 
  Search, Filter, BookOpen, Clock, BarChart, Users,
  CheckCircle2, ArrowRight 
} from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import apiFetch from '@/lib/apiFetch';

const CATEGORIES = [
  { value: 'all', label: 'All Categories' },
  { value: 'Compliance', label: 'Compliance' },
  { value: 'Technical Skills', label: 'Technical Skills' },
  { value: 'Soft Skills', label: 'Soft Skills' },
  { value: 'Product Knowledge', label: 'Product Knowledge' },
];

const LEVELS = [
  { value: 'all', label: 'All Levels' },
  { value: 'Beginner', label: 'Beginner' },
  { value: 'Intermediate', label: 'Intermediate' },
  { value: 'Advanced', label: 'Advanced' },
];

const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest' },
  { value: 'popular', label: 'Most Popular' },
  { value: 'rating', label: 'Highest Rated' },
];

export default function CourseCatalog({ onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [courses, setCourses] = useState([]);
  const [category, setCategory] = useState('all');
  const [level, setLevel] = useState('all');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('newest');

  useEffect(() => {
    fetchCourses();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, level, search, sort]);

  const fetchCourses = async () => {
    try {
      setLoading(true);
      
      const params = new URLSearchParams();
      if (category !== 'all') params.append('category', category);
      if (level !== 'all') params.append('level', level);
      if (search) params.append('search', search);
      params.append('sort', sort);
      params.append('limit', '50');

      const data = await apiFetch(`/lms/student/catalog?${params.toString()}`);
      setCourses(data?.courses || []);
    } catch (error) {
      console.error('Error fetching courses:', error);
      toast.error('Gagal memuat course catalog');
    } finally {
      setLoading(false);
    }
  };

  const handleEnroll = async (courseId, e) => {
    e.stopPropagation();
    
    try {
      await apiFetch(`/lms/student/courses/${courseId}/enroll`, { method: 'POST' });
      toast.success('Berhasil enroll ke course!');
      fetchCourses(); // Refresh to update enrollment status
    } catch (error) {
      console.error('Error enrolling:', error);
      toast.error('Gagal enroll ke course');
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold mb-2">📚 Course Catalog</h1>
          <p className="text-muted-foreground">
            Browse dan enroll di berbagai pelatihan untuk meningkatkan skill Anda
          </p>
        </div>

        {/* Filters */}
        <Card>
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Search */}
              <div className="md:col-span-2">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
                  <Input
                    placeholder="Search courses..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="pl-9"
                  />
                </div>
              </div>

              {/* Category Filter */}
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((cat) => (
                    <SelectItem key={cat.value} value={cat.value}>
                      {cat.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Level Filter */}
              <Select value={level} onValueChange={setLevel}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LEVELS.map((lv) => (
                    <SelectItem key={lv.value} value={lv.value}>
                      {lv.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Sort */}
            <div className="flex items-center gap-2 mt-4">
              <span className="text-sm text-muted-foreground">Sort by:</span>
              <Select value={sort} onValueChange={setSort}>
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SORT_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        {loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
            <p className="text-sm text-muted-foreground mt-2">Loading courses...</p>
          </div>
        ) : courses.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <BookOpen size={48} className="mx-auto mb-3 text-muted-foreground opacity-20" />
              <p className="text-muted-foreground">No courses found</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {courses.map((course) => (
              <Card 
                key={course.course_id}
                className="cursor-pointer hover:shadow-lg transition-shadow"
                onClick={() => onNavigate && onNavigate('course-detail', course.course_id)}
              >
                <CardContent className="pt-6 space-y-4">
                  {/* Category Badge */}
                  <div className="flex items-center justify-between">
                    <Badge variant="secondary">{course.category}</Badge>
                    {course.is_enrolled && (
                      <Badge variant="default" className="bg-green-500">
                        <CheckCircle2 size={12} className="mr-1" />
                        Enrolled
                      </Badge>
                    )}
                  </div>

                  {/* Title & Description */}
                  <div>
                    <h3 className="font-semibold text-lg mb-2">{course.title}</h3>
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {course.description}
                    </p>
                  </div>

                  {/* Meta Info */}
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <Clock size={14} />
                      {course.duration_hours}h
                    </div>
                    <div className="flex items-center gap-1">
                      <BarChart size={14} />
                      {course.level}
                    </div>
                    <div className="flex items-center gap-1">
                      <Users size={14} />
                      {course.enrollment_count || 0}
                    </div>
                  </div>

                  {/* Action Button */}
                  {course.is_enrolled ? (
                    <Button className="w-full" variant="outline">
                      Continue Learning
                      <ArrowRight size={16} className="ml-2" />
                    </Button>
                  ) : (
                    <Button 
                      className="w-full"
                      onClick={(e) => handleEnroll(course.course_id, e)}
                    >
                      Enroll Now
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
