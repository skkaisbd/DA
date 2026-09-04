import { useState } from 'react';
import { Plus, CheckCircle2, Circle, MoreVertical, Power, PowerOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { toast } from 'sonner';
import { readNumber, FIELD } from '@/lib/materialFields';  // FASE 6.6-B

/**
 * VersionRail
 * 
 * Panel samping untuk menampilkan daftar versi BOM dan aksi version management.
 * 
 * Props:
 * - versions: array of BOM versions
 * - activeVersionId: currently active version ID
 * - selectedVersionId: currently selected version ID for viewing
 * - onSelectVersion: (versionId) => void
 * - onCreateVersion: () => void
 * - onActivateVersion: (versionId) => void
 * - token: JWT token
 * - loading: boolean
 */
export const VersionRail = ({
  versions = [],
  activeVersionId,
  selectedVersionId,
  onSelectVersion,
  onCreateVersion,
  onActivateVersion,
  loading = false
}) => {
  const [confirmActivate, setConfirmActivate] = useState(null);

  const handleActivate = (version) => {
    setConfirmActivate(version);
  };

  const confirmActivateVersion = async () => {
    if (confirmActivate && onActivateVersion) {
      await onActivateVersion(confirmActivate.id);
      setConfirmActivate(null);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch {
      return '—';
    }
  };

  return (
    <>
      <GlassPanel className="p-0 h-full flex flex-col" data-testid="version-rail">
        <div className="p-4 border-b border-[var(--glass-border)]">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-foreground">Versi BOM</h3>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 px-2"
                    onClick={onCreateVersion}
                    data-testid="version-rail-create-version-button"
                  >
                    <Plus className="w-4 h-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Buat versi baru</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          <p className="text-xs text-muted-foreground">
            {versions.length} versi tersimpan
          </p>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-3 space-y-2">
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
              </div>
            ) : versions.length === 0 ? (
              <div className="text-center py-8 text-xs text-muted-foreground">
                <Circle className="w-8 h-8 mx-auto mb-2 opacity-30" />
                Belum ada versi BOM
              </div>
            ) : (
              versions.map(version => {
                const isActive = version.id === activeVersionId || version.is_active;
                const isSelected = version.id === selectedVersionId;
                return (
                  <div
                    key={version.id}
                    className={`p-3 rounded-lg border transition-colors cursor-pointer ${
                      isSelected
                        ? 'bg-primary/10 border-primary/40'
                        : 'bg-[var(--glass-bg)] border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)]'
                    }`}
                    onClick={() => onSelectVersion(version.id)}
                    data-testid={`version-item-${version.version}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-mono font-semibold text-foreground">
                            v{version.version}
                          </span>
                          {isActive && (
                            <Badge
                              variant="default"
                              className="text-[10px] px-1.5 py-0 h-5"
                              data-testid={`version-${version.version}-active-badge`}
                            >
                              <CheckCircle2 className="w-3 h-3 mr-1" />
                              Aktif
                            </Badge>
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground space-y-0.5">
                          <div>{formatDate(version.updated_at)}</div>
                          <div className="font-mono">
                            {readNumber(version, FIELD.bulkLineCount)} bahan · {version.accessory_count || 0} aksesoris
                          </div>
                          {readNumber(version, FIELD.totalMaterialKgPerPcs) > 0 && (
                            <div className="font-mono text-primary">
                              {readNumber(version, FIELD.totalMaterialKgPerPcs).toFixed(3)} kg/pcs
                            </div>
                          )}
                        </div>
                      </div>
                      {!isActive && (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 w-7 p-0"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleActivate(version);
                                }}
                                data-testid={`version-${version.version}-activate-button`}
                              >
                                <Power className="w-3.5 h-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Aktifkan versi ini</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                    </div>
                    {version.notes && (
                      <div className="mt-2 text-xs text-muted-foreground truncate">
                        {version.notes}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </ScrollArea>
      </GlassPanel>

      <AlertDialog open={!!confirmActivate} onOpenChange={() => setConfirmActivate(null)}>
        <AlertDialogContent data-testid="version-activate-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Aktifkan Versi BOM</AlertDialogTitle>
            <AlertDialogDescription>
              Anda akan mengaktifkan <span className="font-semibold text-foreground">versi {confirmActivate?.version}</span>.
              Versi yang sedang aktif akan dinonaktifkan secara otomatis.
              <br /><br />
              Versi aktif akan digunakan untuk perhitungan material pada Work Order.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Batal</AlertDialogCancel>
            <AlertDialogAction onClick={confirmActivateVersion} data-testid="version-activate-confirm-button">
              Aktifkan
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};
