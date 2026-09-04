import { useState, useEffect, useCallback, useMemo } from 'react';
import { Settings, Save, RefreshCw, Lock, Eye, EyeOff } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import { PageHeader } from './moduleAtoms';

const CATEGORY_META = {
  maklon:       { label: 'Maklon & Invoice',   color: 'text-violet-600 dark:text-violet-400' },
  hpp:          { label: 'HPP & Costing',      color: 'text-amber-700 dark:text-amber-400' },
  notification: { label: 'Notifikasi (WA/TG)', color: 'text-green-700 dark:text-green-400' },
  marketplace:  { label: 'Marketplace',        color: 'text-blue-600 dark:text-blue-400' },
};

export default function MaklonSystemConfigModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('maklon');
  const [edited, setEdited] = useState({});
  const [showSecret, setShowSecret] = useState({});

  const fetchConfigs = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/dewi/system/config', { headers });
      if (r.ok) { setConfigs(await r.json()); setEdited({}); }
      else toast.error('Gagal memuat config');
    } catch (e) { toast.error('Gagal memuat config'); }
    finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { fetchConfigs(); }, [fetchConfigs]);

  const setValue = (key, value) => setEdited(p => ({ ...p, [key]: value }));

  const currentValue = (cfg) => {
    if (cfg.key in edited) return edited[cfg.key];
    return cfg.value !== undefined ? cfg.value : '';
  };

  const saveAll = async () => {
    if (Object.keys(edited).length === 0) { toast.info('Tidak ada perubahan'); return; }
    setSaving(true);
    const r = await fetch('/api/dewi/system/config/bulk', { method: 'POST', headers, body: JSON.stringify(edited) });
    setSaving(false);
    if (r.ok) {
      const d = await r.json();
      toast.success(`${d.updated} config disimpan`);
      if (d.errors?.length) toast.error(`Errors: ${d.errors.join(', ')}`);
      fetchConfigs();
    } else {
      toast.error('Gagal menyimpan');
    }
  };

  const categories = [...new Set(configs.map(c => c.category))];
  const byCategory = configs.filter(c => c.category === activeTab);

  const renderInput = (cfg) => {
    const val = currentValue(cfg);
    const isSecret = cfg.is_secret;
    const show = showSecret[cfg.key];
    if (cfg.data_type === 'boolean') {
      return (
        <Switch checked={!!val} onCheckedChange={(v) => setValue(cfg.key, v)} data-testid={`cfg-${cfg.key}`} />
      );
    }
    if (cfg.data_type === 'number') {
      return <Input type="number" step="any" value={val ?? ''} onChange={e => setValue(cfg.key, e.target.value)} data-testid={`cfg-${cfg.key}`} />;
    }
    if (isSecret) {
      return (
        <div className="flex gap-2">
          <Input type={show ? 'text' : 'password'} value={val ?? ''} onChange={e => setValue(cfg.key, e.target.value)} placeholder={cfg.value_masked || '•••••'} data-testid={`cfg-${cfg.key}`} />
          <Button size="icon" variant="ghost" className="w-9 h-9" onClick={() => setShowSecret(p => ({ ...p, [cfg.key]: !p[cfg.key] }))}>
            {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </Button>
        </div>
      );
    }
    return <Input value={val ?? ''} onChange={e => setValue(cfg.key, e.target.value)} data-testid={`cfg-${cfg.key}`} />;
  };

  return (
    <div className="p-6 space-y-6" data-testid="maklon-system-config">
      <PageHeader
        title="System Configuration"
        subtitle="Pengaturan sistem yang dapat dikonfigurasi (tax, threshold, API keys) — bukan hardcode"
        icon={Settings}
        actions={
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={fetchConfigs} className="gap-2" data-testid="cfg-refresh-btn">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </Button>
            <Button size="sm" onClick={saveAll} disabled={saving || Object.keys(edited).length === 0} className="gap-1.5" data-testid="cfg-save-btn">
              <Save className="w-3.5 h-3.5" /> Simpan{Object.keys(edited).length > 0 ? ` (${Object.keys(edited).length})` : ''}
            </Button>
          </div>
        }
      />

      {loading ? (
        <GlassCard className="p-10 text-center text-foreground/50">Memuat...</GlassCard>
      ) : (
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-4 flex-wrap">
            {categories.map(cat => {
              const meta = CATEGORY_META[cat] || { label: cat };
              return <TabsTrigger key={cat} value={cat} data-testid={`cfg-tab-${cat}`}>{meta.label}</TabsTrigger>;
            })}
          </TabsList>

          {categories.map(cat => (
            <TabsContent key={cat} value={cat}>
              <GlassCard className="p-5 space-y-4">
                {byCategory.length === 0 && activeTab === cat && (
                  <div className="text-foreground/40 text-sm py-6 text-center">Tidak ada config di kategori ini</div>
                )}
                {activeTab === cat && byCategory.map((cfg, i) => (
                  <motion.div
                    key={cfg.key}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.02 * i }}
                    className="grid grid-cols-1 md:grid-cols-[1fr_1fr] gap-4 pb-3 border-b border-foreground/5 last:border-0 last:pb-0"
                  >
                    <div>
                      <Label className="flex items-center gap-1.5">
                        {cfg.label}
                        {cfg.is_secret && <Lock className="w-3 h-3 text-amber-700 dark:text-amber-400" />}
                      </Label>
                      <div className="text-xs text-foreground/50 mt-1">{cfg.description}</div>
                      <div className="text-[10px] font-mono text-foreground/30 mt-0.5">{cfg.key}</div>
                    </div>
                    <div>
                      {renderInput(cfg)}
                      {cfg.updated_at && (
                        <div className="text-[10px] text-foreground/40 mt-1">
                          Diupdate: {(cfg.updated_at || '').slice(0, 19).replace('T', ' ')} oleh {cfg.updated_by || '-'}
                        </div>
                      )}
                    </div>
                  </motion.div>
                ))}
              </GlassCard>
            </TabsContent>
          ))}
        </Tabs>
      )}
    </div>
  );
}
