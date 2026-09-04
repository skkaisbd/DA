import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, Plus, Edit, Trash2, RefreshCw, UserCheck, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';
import { API } from './utils';
import TrainingModal from './TrainingModal';
import AssignTrainingModal from './AssignTrainingModal';

export default function TrainingTab({ authH }) {
  const [trainings, setTrainings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingTraining, setEditingTraining] = useState(null);
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [selectedTraining, setSelectedTraining] = useState(null);

  const fetchTrainings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/marketing/livehost/training`, { headers: authH });
      if (res.ok) {
        const data = await res.json();
        setTrainings(data);
      }
    } catch (e) {
      toast.error('Gagal memuat training');
    } finally {
      setLoading(false);
    }
  }, [authH]);

  useEffect(() => {
    fetchTrainings();
  }, [fetchTrainings]);

  const handleDelete = async (training) => {
    if (!window.confirm(`Yakin ingin menghapus training "${training.title}"?`)) return;
    try {
      const res = await fetch(`${API}/api/marketing/livehost/training/${training.id}`, {
        method: 'DELETE',
        headers: authH,
      });
      if (res.ok) {
        toast.success('Training berhasil dihapus');
        fetchTrainings();
      }
    } catch (e) {
      toast.error('Gagal menghapus training');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Button variant="outline" size="sm" onClick={fetchTrainings} className="h-9">
          <RefreshCw size={14} className="mr-1.5" />
          Refresh
        </Button>
        <Button
          size="sm"
          onClick={() => {
            setEditingTraining(null);
            setShowModal(true);
          }}
          className="h-9"
        >
          <Plus size={14} className="mr-1.5" />
          Add Training
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 size={28} className="animate-spin text-muted-foreground" />
        </div>
      ) : trainings.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
            <TrendingUp size={40} className="text-muted-foreground opacity-40" />
            <p className="font-medium">Belum ada training</p>
            <Button size="sm" onClick={() => setShowModal(true)}>
              <Plus size={14} className="mr-1.5" />
              Add Training
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {trainings.map((training) => (
            <Card key={training.id} className="hover:shadow-md transition-shadow">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <CardTitle className="text-sm font-semibold line-clamp-2">{training.title}</CardTitle>
                    <div className="flex items-center gap-2 mt-1.5">
                      <Badge variant="outline" className="text-xs capitalize">
                        {training.category.replace('_', ' ')}
                      </Badge>
                      {training.is_required && (
                        <Badge variant="destructive" className="text-xs">
                          Required
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      onClick={() => {
                        setEditingTraining(training);
                        setShowModal(true);
                      }}
                    >
                      <Edit size={12} />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-red-600"
                      onClick={() => handleDelete(training)}
                    >
                      <Trash2 size={12} />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-0 space-y-2">
                <p className="text-xs text-muted-foreground line-clamp-3">{training.description}</p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-muted-foreground">Type:</span>{' '}
                    <span className="font-medium capitalize">{training.content_type}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Duration:</span>{' '}
                    <span className="font-medium">{training.duration_minutes} min</span>
                  </div>
                  {training.passing_score && (
                    <div>
                      <span className="text-muted-foreground">Pass Score:</span>{' '}
                      <span className="font-medium">{training.passing_score}%</span>
                    </div>
                  )}
                  {training.expiry_months && (
                    <div>
                      <span className="text-muted-foreground">Expiry:</span>{' '}
                      <span className="font-medium">{training.expiry_months} months</span>
                    </div>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full h-8 mt-2"
                  onClick={() => {
                    setSelectedTraining(training);
                    setShowAssignModal(true);
                  }}
                >
                  <UserCheck size={12} className="mr-1.5" />
                  Assign to Hosts
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {showModal && (
        <TrainingModal
          training={editingTraining}
          authH={authH}
          onClose={() => {
            setShowModal(false);
            setEditingTraining(null);
          }}
          onSuccess={() => {
            setShowModal(false);
            setEditingTraining(null);
            fetchTrainings();
          }}
        />
      )}

      {showAssignModal && selectedTraining && (
        <AssignTrainingModal
          training={selectedTraining}
          authH={authH}
          onClose={() => {
            setShowAssignModal(false);
            setSelectedTraining(null);
          }}
          onSuccess={() => {
            setShowAssignModal(false);
            setSelectedTraining(null);
            toast.success('Training berhasil di-assign');
          }}
        />
      )}
    </div>
  );
}
