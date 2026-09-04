/**
 * CollaborationPortal.jsx
 * Unified portal for Communication, Workspace, and Learning
 * 
 * Refactored: Consistent with other portals (single sidebar menu, no tab system)
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { 
  MessageSquare, FileText, GraduationCap, ArrowLeft, 
  User, BookOpen, Award, Users, Home, Library
} from 'lucide-react';

// Portal components
import CommunicationHubPortal from './CommunicationHubPortal';
import WorkspacePortal from './WorkspacePortal';
import LearningHome from './collaboration/learning/LearningHome';
import CourseCatalog from './collaboration/learning/CourseCatalog';
import MyCourses from './collaboration/learning/MyCourses';
import CourseDetail from './collaboration/learning/CourseDetail';
import Certificates from './collaboration/learning/Certificates';
import StudyGroups from './collaboration/learning/StudyGroups';
import StudyGroupDetail from './collaboration/learning/StudyGroupDetail';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

// Menu items configuration
const MENU_ITEMS = [
  {
    id: 'communication-hub',
    label: 'Communication Hub',
    icon: MessageSquare,
    description: 'Channels & Direct Messages',
  },
  {
    id: 'workspace',
    label: 'My Workspace',
    icon: FileText,
    description: 'Documents & Spreadsheets',
  },
  {
    id: 'learning-home',
    label: 'Learning Home',
    icon: Home,
    description: 'Dashboard pembelajaran',
  },
  {
    id: 'course-catalog',
    label: 'Course Catalog',
    icon: Library,
    description: 'Jelajahi courses',
  },
  {
    id: 'my-courses',
    label: 'My Courses',
    icon: BookOpen,
    description: 'Courses yang diikuti',
  },
  {
    id: 'study-groups',
    label: 'Study Groups',
    icon: Users,
    description: 'Kolaborasi belajar',
  },
  {
    id: 'certificates',
    label: 'Certificates',
    icon: Award,
    description: 'Sertifikat saya',
  },
];

export default function CollaborationPortal({ user, token, onLogout, onBack }) {
  const [activeView, setActiveView] = useState('workspace'); // Default workspace
  
  // Course detail state
  const [selectedCourseId, setSelectedCourseId] = useState(null);
  const [selectedGroupId, setSelectedGroupId] = useState(null);

  // Navigation handlers
  const handleNavigate = (view, options = {}) => {
    setActiveView(view);
    if (options.courseId) setSelectedCourseId(options.courseId);
    if (options.groupId) setSelectedGroupId(options.groupId);
  };

  // Render active content
  const renderContent = () => {
    switch (activeView) {
      case 'communication-hub':
        return <CommunicationHubPortal token={token} user={user} />;
      
      case 'workspace':
        return <WorkspacePortal token={token} user={user} />;
      
      case 'learning-home':
        return <LearningHome onNavigate={handleNavigate} />;
      
      case 'course-catalog':
        return <CourseCatalog onNavigate={handleNavigate} />;
      
      case 'my-courses':
        return <MyCourses onNavigate={handleNavigate} />;
      
      case 'course-detail':
        return (
          <CourseDetail
            courseId={selectedCourseId}
            onBack={() => setActiveView('my-courses')}
          />
        );
      
      case 'study-groups':
        return <StudyGroups onNavigate={handleNavigate} />;
      
      case 'study-group-detail':
        return (
          <StudyGroupDetail
            groupId={selectedGroupId}
            onNavigate={handleNavigate}
            token={token}
            user={user}
          />
        );
      
      case 'certificates':
        return <Certificates onNavigate={handleNavigate} />;
      
      default:
        return <WorkspacePortal token={token} user={user} />;
    }
  };

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-64 border-r bg-card flex flex-col shrink-0">
          {/* Sidebar Header */}
          <div className="p-4 border-b">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <MessageSquare size={18} className="text-primary" />
              </div>
              <h2 className="font-semibold text-sm">Portal Kolaborasi</h2>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Komunikasi, Workspace & Learning
            </p>
          </div>

          {/* Menu Items */}
          <ScrollArea className="flex-1 px-2 py-3">
            <div className="space-y-1">
              {MENU_ITEMS.map((item) => {
                const Icon = item.icon;
                const isActive = activeView === item.id;
                
                return (
                  <button
                    key={item.id}
                    onClick={() => handleNavigate(item.id)}
                    className={`w-full flex items-start gap-3 px-3 py-2.5 rounded-lg transition-colors text-left ${
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-accent text-foreground'
                    }`}
                    data-testid={`menu-${item.id}`}
                  >
                    <Icon size={18} className="shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{item.label}</p>
                      <p className={`text-xs truncate ${
                        isActive ? 'text-primary-foreground/80' : 'text-muted-foreground'
                      }`}>
                        {item.description}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          </ScrollArea>

          {/* User Info */}
          <div className="p-3 border-t">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
                <User size={16} className="text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium truncate">{user?.name}</p>
                <p className="text-[10px] text-muted-foreground truncate">{user?.email}</p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={onLogout}
              className="w-full text-xs"
            >
              Logout
            </Button>
          </div>
        </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden bg-background">
        {/* Simple Tab Header */}
        <div className="h-12 border-b bg-background px-4 flex items-center gap-3 shrink-0">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onBack}
            title="Kembali ke Portal Selector"
            data-testid="back-to-portals-btn"
          >
            <ArrowLeft size={16} />
          </Button>
          <h1 className="font-medium text-sm text-foreground">
            {MENU_ITEMS.find(m => m.id === activeView)?.label || 'Portal Kolaborasi'}
          </h1>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-hidden">
          {renderContent()}
        </div>
      </div>
    </div>
  );
}
