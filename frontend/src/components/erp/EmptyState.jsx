/**
 * EmptyState - Unified empty state component
 * Consistent design untuk semua modules
 * 
 * Usage:
 *   <EmptyState 
 *     icon={Package}
 *     title="Belum ada data"
 *     description="Data akan muncul setelah Anda menambahkan item pertama"
 *     action={{ label: "Tambah Item", onClick: () => {} }}
 *   />
 */
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';

export function EmptyState({ 
  icon: Icon, 
  title, 
  description, 
  action,
  className = '' 
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex flex-col items-center justify-center py-16 px-6 ${className}`}
      data-testid="empty-state"
    >
      {/* Icon */}
      {Icon && (
        <div className="mb-6 p-4 rounded-2xl bg-primary/10 border border-primary/20">
          <Icon className="w-12 h-12 text-primary/60" strokeWidth={1.5} />
        </div>
      )}
      
      {/* Title */}
      <h3 className="text-lg font-semibold text-foreground mb-2">
        {title}
      </h3>
      
      {/* Description */}
      {description && (
        <p className="text-sm text-muted-foreground text-center max-w-md mb-6">
          {description}
        </p>
      )}
      
      {/* Action Button */}
      {action && (
        <Button 
          onClick={action.onClick}
          variant={action.variant || 'default'}
          size="sm"
          data-testid="empty-state-action"
        >
          {action.icon && <action.icon className="w-4 h-4 mr-2" />}
          {action.label}
        </Button>
      )}
    </motion.div>
  );
}

/**
 * Common empty state presets
 */
export const EmptyStatePresets = {
  noData: (entityName = 'data') => ({
    title: `Belum ada ${entityName}`,
    description: `${entityName} akan muncul di sini setelah Anda menambahkan item pertama.`
  }),
  
  noResults: {
    title: 'Tidak ada hasil',
    description: 'Coba ubah filter atau kata kunci pencarian Anda.'
  },
  
  noPermission: {
    title: 'Akses Terbatas',
    description: 'Anda tidak memiliki izin untuk melihat data ini. Hubungi administrator jika Anda memerlukan akses.'
  },
  
  error: {
    title: 'Gagal Memuat Data',
    description: 'Terjadi kesalahan saat memuat data. Silakan refresh halaman atau hubungi support.'
  }
};
