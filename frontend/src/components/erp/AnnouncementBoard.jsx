/**
 * AnnouncementBoard — Komponen announcement yang tampil di Portal Selector
 * Menampilkan announcements aktif dari backend
 */
import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Info, CheckCircle2, AlertTriangle, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';

const API = process.env.REACT_APP_BACKEND_URL;

const ANNOUNCEMENT_TYPES = {
  info: { icon: Info, colorClass: 'bg-blue-50 border-blue-200 text-blue-800' },
  success: { icon: CheckCircle2, colorClass: 'bg-green-50 border-green-200 text-green-800' },
  warning: { icon: AlertTriangle, colorClass: 'bg-amber-50 border-amber-200 text-amber-800' },
  urgent: { icon: AlertCircle, colorClass: 'bg-red-50 border-red-200 text-red-800' },
};

function AnnouncementItem({ announcement, onDismiss }) {
  const [expanded, setExpanded] = useState(false);
  const config = ANNOUNCEMENT_TYPES[announcement.type] || ANNOUNCEMENT_TYPES.info;
  const Icon = config.icon;

  // Truncate content if too long (show first 120 chars)
  const shortContent = announcement.content.length > 120
    ? announcement.content.substring(0, 120) + '...'
    : announcement.content;
  const hasMore = announcement.content.length > 120;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: 100 }}
      transition={{ duration: 0.3 }}
      className="relative"
    >
      <div className={`border rounded-lg p-4 ${config.colorClass}`}>
        <div className="flex items-start gap-3">
          <Icon size={20} className="flex-shrink-0 mt-0.5" />
          
          <div className="flex-1 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <h4 className="font-semibold text-sm leading-tight">{announcement.title}</h4>
              <button
                onClick={() => onDismiss(announcement.id)}
                className="flex-shrink-0 text-current opacity-60 hover:opacity-100 transition"
                aria-label="Dismiss"
              >
                <X size={16} />
              </button>
            </div>

            <p className="text-sm leading-relaxed opacity-90">
              {expanded ? announcement.content : shortContent}
            </p>

            {hasMore && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="text-xs font-medium flex items-center gap-1 hover:underline"
              >
                {expanded ? (
                  <>
                    Tampilkan lebih sedikit <ChevronUp size={14} />
                  </>
                ) : (
                  <>
                    Selengkapnya <ChevronDown size={14} />
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export default function AnnouncementBoard() {
  const [announcements, setAnnouncements] = useState([]);
  const [dismissedIds, setDismissedIds] = useState(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAnnouncements = async () => {
      const token = localStorage.getItem('erp_token');
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const res = await fetch(`${API}/api/announcements/active`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error('Failed to fetch');
        const data = await res.json();
        
        // Sort by priority (highest first)
        const sorted = data.sort((a, b) => b.priority - a.priority);
        setAnnouncements(sorted);
      } catch (error) {
        console.error('Error fetching announcements:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchAnnouncements();
  }, []);

  const handleDismiss = (id) => {
    setDismissedIds(prev => new Set([...prev, id]));
  };

  // Filter announcements yang belum di-dismiss
  const visibleAnnouncements = announcements.filter(a => !dismissedIds.has(a.id));

  if (loading) {
    return null; // Don't show loading spinner, just wait silently
  }

  if (visibleAnnouncements.length === 0) {
    return null; // No announcements to show
  }

  return (
    <div className="w-full max-w-3xl mx-auto mb-8">
      <div className="space-y-3">
        <AnimatePresence mode="popLayout">
          {visibleAnnouncements.map(announcement => (
            <AnnouncementItem
              key={announcement.id}
              announcement={announcement}
              onDismiss={handleDismiss}
            />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
