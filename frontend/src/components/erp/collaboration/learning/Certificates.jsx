/**
 * Certificates.jsx
 * Page menampilkan sertifikat yang sudah didapat student.
 */

import { useState, useEffect } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Award, Download, BookOpen, Target, Clock, Share2 } from 'lucide-react';
import { toast } from 'sonner';
import apiFetch from '@/lib/apiFetch';

export default function Certificates({ onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [certificates, setCertificates] = useState([]);
  const [stats, setStats] = useState({
    total_certificates: 0,
    total_courses_enrolled: 0,
    total_learning_hours: 0,
  });

  useEffect(() => {
    fetchCertificates();
  }, []);

  const fetchCertificates = async () => {
    try {
      setLoading(true);
      const data = await apiFetch('/lms/student/certificates');
      setCertificates(data.certificates || []);
      setStats(data.stats || {
        total_certificates: 0,
        total_courses_enrolled: 0,
        total_learning_hours: 0,
      });
    } catch (error) {
      console.error('Error fetching certificates:', error);
      toast.error('Gagal memuat sertifikat');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = (cert) => {
    // MOCKED: PDF generation not implemented yet — just show toast
    toast.info(`Sertifikat ${cert.verification_code} (PDF generation belum tersedia)`);
  };

  const handleShare = (cert) => {
    const url = `${window.location.origin}/verify/${cert.verification_code}`;
    navigator.clipboard.writeText(url).then(() => {
      toast.success('Link verifikasi disalin ke clipboard');
    }).catch(() => {
      toast.error('Gagal menyalin link');
    });
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('id-ID', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-2">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="text-sm text-muted-foreground">Loading certificates...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto" data-testid="certificates-view">
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold mb-2">🏆 Sertifikat Saya</h1>
          <p className="text-muted-foreground">
            Pencapaian Anda dari course yang telah diselesaikan
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Sertifikat</p>
                  <p className="text-2xl font-bold" data-testid="stat-certificates">{stats.total_certificates}</p>
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
                  <p className="text-sm text-muted-foreground">Total Enrolled</p>
                  <p className="text-2xl font-bold" data-testid="stat-enrolled">{stats.total_courses_enrolled}</p>
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
                  <p className="text-sm text-muted-foreground">Jam Belajar</p>
                  <p className="text-2xl font-bold" data-testid="stat-hours">{stats.total_learning_hours}h</p>
                </div>
                <div className="h-12 w-12 rounded-full bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                  <Clock className="text-purple-500" size={24} />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Certificates grid */}
        {certificates.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <Award size={64} className="mx-auto mb-3 text-muted-foreground opacity-20" />
              <p className="text-muted-foreground mb-2">Belum ada sertifikat</p>
              <p className="text-sm text-muted-foreground mb-4">
                Selesaikan course untuk mendapatkan sertifikat
              </p>
              <Button
                onClick={() => onNavigate && onNavigate('catalog')}
                data-testid="browse-catalog-btn"
              >
                Browse Course Catalog
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {certificates.map((cert) => (
              <Card
                key={cert.certificate_id}
                className="overflow-hidden"
                data-testid={`cert-card-${cert.certificate_id}`}
              >
                {/* Certificate preview area */}
                <div className="bg-gradient-to-br from-amber-500/20 via-amber-400/15 to-yellow-500/20 p-6 text-center border-b">
                  <Award className="text-amber-500 mx-auto mb-2" size={56} />
                  <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
                    Certificate of Completion
                  </p>
                  <h3 className="font-bold text-lg leading-tight">{cert.course_title}</h3>
                </div>

                <CardContent className="pt-4 space-y-3">
                  <div className="space-y-2 text-sm">
                    <div>
                      <p className="text-muted-foreground">Issued</p>
                      <p className="font-medium">{formatDate(cert.issued_date)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Verification Code</p>
                      <p className="font-mono text-xs">{cert.verification_code}</p>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => handleDownload(cert)}
                      data-testid={`cert-download-${cert.certificate_id}`}
                    >
                      <Download size={14} className="mr-1" />
                      Download
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => handleShare(cert)}
                      data-testid={`cert-share-${cert.certificate_id}`}
                    >
                      <Share2 size={14} className="mr-1" />
                      Share
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Achievement note */}
        {certificates.length > 0 && (
          <Card className="border-amber-500/40">
            <CardContent className="pt-6">
              <div className="flex items-start gap-3">
                <Target className="text-amber-500 flex-shrink-0" size={20} />
                <div className="text-sm">
                  <p className="font-medium">Terus belajar!</p>
                  <p className="text-muted-foreground">
                    Anda sudah menyelesaikan {stats.total_certificates} course. Pelajari lebih banyak topik untuk meningkatkan skill Anda.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
