/**
 * StudyGroupDetail.jsx
 * Phase 3.8: Study Group Detail View
 * Shows group info + embedded chat (Communication Hub channel) + shared documents (Workspace folder)
 */

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { 
  ArrowLeft, Users, BookOpen, MessageSquare, FolderOpen,
  Calendar, Settings, UserPlus, Trash2
} from 'lucide-react';
import { toast } from 'sonner';
import apiFetch from '@/lib/apiFetch';

// Import Communication Hub and Workspace components
import CommunicationHubPortal from '../../CommunicationHubPortal';
import WorkspacePortal from '../../WorkspacePortal';

export default function StudyGroupDetail({ groupId, onNavigate, token, user }) {
  const [loading, setLoading] = useState(true);
  const [group, setGroup] = useState(null);
  const [activeTab, setActiveTab] = useState('chat');

  useEffect(() => {
    if (groupId) {
      fetchGroupDetail();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId]);

  const fetchGroupDetail = async () => {
    try {
      setLoading(true);
      const data = await apiFetch(`/collab/study-groups/${groupId}`);
      setGroup(data.study_group);
    } catch (error) {
      console.error('Error fetching group detail:', error);
      toast.error('Gagal memuat detail study group');
    } finally {
      setLoading(false);
    }
  };

  const handleLeaveGroup = async () => {
    if (!confirm('Yakin ingin keluar dari study group ini?')) return;

    try {
      await apiFetch(`/collab/study-groups/${groupId}/members/${user.id}`, {
        method: 'DELETE',
      });
      toast.success('Berhasil keluar dari study group');
      onNavigate('study-groups'); // Back to list
    } catch (error) {
      console.error('Error leaving group:', error);
      toast.error(error.message || 'Gagal keluar dari group');
    }
  };

  const handleDeleteGroup = async () => {
    if (!confirm('Yakin ingin menghapus study group ini? Tindakan tidak dapat dibatalkan.')) return;

    try {
      await apiFetch(`/collab/study-groups/${groupId}`, {
        method: 'DELETE',
      });
      toast.success('Study group berhasil dihapus');
      onNavigate('study-groups'); // Back to list
    } catch (error) {
      console.error('Error deleting group:', error);
      toast.error(error.message || 'Gagal menghapus group');
    }
  };

  const getInitials = (name) => {
    if (!name) return '?';
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  if (loading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!group) {
    return (
      <div className="p-6">
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <p className="text-muted-foreground">Study group tidak ditemukan</p>
            <Button 
              onClick={() => onNavigate('study-groups')} 
              className="mt-4"
              variant="outline"
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Kembali
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const isCreator = group.created_by === user.id;
  const isMember = group.members_detail?.some(m => m.id === user.id);

  return (
    <div className="space-y-4 p-6" data-testid="study-group-detail-view">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onNavigate('study-groups')}
            data-testid="back-to-groups-btn"
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h2 className="text-2xl font-bold flex items-center gap-2">
              <Users className="h-6 w-6 text-purple-600" />
              {group.name}
            </h2>
            {group.course && (
              <p className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                <BookOpen className="h-4 w-4" />
                {group.course.title}
              </p>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {isCreator && (
            <Button 
              variant="destructive" 
              size="sm"
              onClick={handleDeleteGroup}
              data-testid="delete-group-btn"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Hapus Group
            </Button>
          )}
          {!isCreator && isMember && (
            <Button 
              variant="outline" 
              size="sm"
              onClick={handleLeaveGroup}
              data-testid="leave-group-btn"
            >
              Keluar dari Group
            </Button>
          )}
        </div>
      </div>

      {/* Info Card */}
      <Card>
        <CardContent className="pt-6">
          <div className="grid md:grid-cols-3 gap-6">
            {/* Description */}
            <div className="md:col-span-2 space-y-3">
              {group.description && (
                <div>
                  <h3 className="text-sm font-semibold mb-1">Deskripsi</h3>
                  <p className="text-sm text-muted-foreground">{group.description}</p>
                </div>
              )}
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Calendar className="h-4 w-4" />
                Dibuat {new Date(group.created_at).toLocaleDateString('id-ID', { 
                  day: 'numeric', month: 'long', year: 'numeric' 
                })}
              </div>
            </div>

            {/* Members */}
            <div>
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <Users className="h-4 w-4" />
                Anggota ({group.members_detail?.length || 0})
              </h3>
              <div className="space-y-2 max-h-32 overflow-y-auto">
                {group.members_detail?.map((member) => (
                  <div 
                    key={member.id} 
                    className="flex items-center gap-2 text-sm"
                    data-testid={`member-${member.id}`}
                  >
                    <Avatar className="h-6 w-6">
                      {member.foto_url && <AvatarImage src={member.foto_url} />}
                      <AvatarFallback className="text-xs">{getInitials(member.name)}</AvatarFallback>
                    </Avatar>
                    <span className="flex-1 truncate">{member.name}</span>
                    {member.id === group.created_by && (
                      <Badge variant="secondary" className="text-xs">Pembuat</Badge>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs: Chat & Documents */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="chat" className="flex items-center gap-2" data-testid="tab-chat">
            <MessageSquare className="h-4 w-4" />
            Diskusi
          </TabsTrigger>
          <TabsTrigger value="docs" className="flex items-center gap-2" data-testid="tab-docs">
            <FolderOpen className="h-4 w-4" />
            Dokumen
          </TabsTrigger>
        </TabsList>

        {/* Chat Tab - Embed Communication Hub Channel */}
        <TabsContent value="chat" className="mt-4">
          <Card>
            <CardContent className="p-0">
              {group.channel_id ? (
                <div className="h-[600px] overflow-hidden">
                  <CommunicationHubPortal 
                    token={token} 
                    user={user}
                    initialChannelId={group.channel_id}
                    embedded={true}
                  />
                </div>
              ) : (
                <div className="p-12 text-center text-muted-foreground">
                  <MessageSquare className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>Channel diskusi belum dibuat</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Documents Tab - Embed Workspace Folder */}
        <TabsContent value="docs" className="mt-4">
          <Card>
            <CardContent className="p-0">
              {group.folder_id ? (
                <div className="h-[600px] overflow-hidden">
                  <WorkspacePortal 
                    token={token}
                    initialFolderId={group.folder_id}
                    embedded={true}
                  />
                </div>
              ) : (
                <div className="p-12 text-center text-muted-foreground">
                  <FolderOpen className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>Folder dokumen belum dibuat</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
