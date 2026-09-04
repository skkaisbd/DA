import { useState, useEffect, useCallback } from 'react';
import { Video, Plus, Edit, Trash2, RefreshCw, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { API } from './utils';
import ScriptModal from './ScriptModal';

export default function ScriptsTab({ authH }) {
  const [scripts, setScripts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingScript, setEditingScript] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [categoryFilter, setCategoryFilter] = useState('all');

  const fetchScripts = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (categoryFilter !== 'all') params.append('category', categoryFilter);

      const res = await fetch(`${API}/api/marketing/livehost/scripts?${params}`, { headers: authH });
      if (res.ok) {
        const data = await res.json();
        setScripts(data);
      }
    } catch (e) {
      toast.error('Gagal memuat scripts');
    } finally {
      setLoading(false);
    }
  }, [authH, categoryFilter]);

  const fetchAccounts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/marketing/accounts?status=active`, { headers: authH });
      if (res.ok) {
        const data = await res.json();
        setAccounts(data);
      }
    } catch (e) {}
  }, [authH]);

  useEffect(() => {
    fetchScripts();
    fetchAccounts();
  }, [fetchScripts, fetchAccounts]);

  const handleDelete = async (script) => {
    if (!window.confirm(`Yakin ingin menghapus script "${script.title}"?`)) return;
    try {
      const res = await fetch(`${API}/api/marketing/livehost/scripts/${script.id}`, {
        method: 'DELETE',
        headers: authH,
      });
      if (res.ok) {
        toast.success('Script berhasil dihapus');
        fetchScripts();
      }
    } catch (e) {
      toast.error('Gagal menghapus script');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <Select value={categoryFilter} onValueChange={setCategoryFilter}>
            <SelectTrigger className="w-[160px] h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Categories</SelectItem>
              <SelectItem value="opening">Opening</SelectItem>
              <SelectItem value="demo">Demo/Product</SelectItem>
              <SelectItem value="promo">Promo</SelectItem>
              <SelectItem value="closing">Closing</SelectItem>
              <SelectItem value="faq">FAQ</SelectItem>
              <SelectItem value="objection_handling">Objection Handling</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={fetchScripts} className="h-9">
            <RefreshCw size={14} className="mr-1.5" />
            Refresh
          </Button>
        </div>
        <Button
          size="sm"
          onClick={() => {
            setEditingScript(null);
            setShowModal(true);
          }}
          className="h-9"
        >
          <Plus size={14} className="mr-1.5" />
          Add Script
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 size={28} className="animate-spin text-muted-foreground" />
        </div>
      ) : scripts.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
            <Video size={40} className="text-muted-foreground opacity-40" />
            <p className="font-medium">Belum ada script</p>
            <Button size="sm" onClick={() => setShowModal(true)}>
              <Plus size={14} className="mr-1.5" />
              Add Script
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {scripts.map((script) => (
            <Card key={script.id} className="hover:shadow-md transition-shadow">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <CardTitle className="text-sm font-semibold line-clamp-2">{script.title}</CardTitle>
                    <div className="flex items-center gap-2 mt-1.5">
                      <Badge variant="outline" className="text-xs capitalize">
                        {script.category.replace('_', ' ')}
                      </Badge>
                      <Badge variant="secondary" className="text-xs">
                        {script.language}
                      </Badge>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      onClick={() => {
                        setEditingScript(script);
                        setShowModal(true);
                      }}
                    >
                      <Edit size={12} />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-red-600"
                      onClick={() => handleDelete(script)}
                    >
                      <Trash2 size={12} />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <p className="text-xs text-muted-foreground line-clamp-4 mb-2">{script.script_text}</p>
                <div className="text-xs text-muted-foreground">
                  <strong>Scope:</strong> {script.account_name || 'Global (All Accounts)'}
                </div>
                {script.products_applicable && script.products_applicable.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {script.products_applicable.slice(0, 3).map((prod) => (
                      <Badge key={prod} variant="secondary" className="text-xs">
                        {prod}
                      </Badge>
                    ))}
                    {script.products_applicable.length > 3 && (
                      <Badge variant="secondary" className="text-xs">
                        +{script.products_applicable.length - 3}
                      </Badge>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {showModal && (
        <ScriptModal
          script={editingScript}
          accounts={accounts}
          authH={authH}
          onClose={() => {
            setShowModal(false);
            setEditingScript(null);
          }}
          onSuccess={() => {
            setShowModal(false);
            setEditingScript(null);
            fetchScripts();
          }}
        />
      )}
    </div>
  );
}
