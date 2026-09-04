/**
 * AdminSetupPanelModule — Phase 7F
 * One-click setup COA, Posting Profiles, EEM Categories untuk deployment baru
 */
import React, { useState, useEffect } from 'react';
import { Database, CheckCircle2, AlertCircle, Loader2, RefreshCw, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

// Auth: gunakan JWT Bearer (standar aplikasi, sama seperti 224 modul lain).
// Sebelumnya modul ini keliru pakai `credentials: 'include'` (cookie) tanpa
// Authorization header → endpoint `_require_super` menolak 401 → "Gagal fetch status".
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('erp_token')}` });

export default function AdminSetupPanelModule() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [seedLoading, setSeedLoading] = useState({
    coa: false,
    posting_profiles: false,
    all: false,
  });

  useEffect(() => {
    fetchStatus();
  }, []);

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/rahaza/admin/accounting-status`, {
        headers: authHeaders(),
      });
      const data = await res.json();
      if (res.ok) {
        setStatus(data);
      } else {
        toast.error('Gagal fetch status');
      }
    } catch (err) {
      console.error('Fetch status error:', err);
      toast.error('Terjadi kesalahan saat fetch status');
    } finally {
      setLoading(false);
    }
  };

  const handleSeedCOA = async () => {
    setSeedLoading((prev) => ({ ...prev, coa: true }));
    try {
      const res = await fetch(`${API_BASE}/api/rahaza/admin/seed-coa`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const data = await res.json();
      if (data.ok) {
        toast.success(`COA seeded: ${data.count_before} → ${data.count_after} accounts`);
        await fetchStatus();
      } else {
        toast.error(data.error || 'Seed COA failed');
      }
    } catch (err) {
      console.error('Seed COA error:', err);
      toast.error('Terjadi kesalahan');
    } finally {
      setSeedLoading((prev) => ({ ...prev, coa: false }));
    }
  };

  const handleSeedPostingProfiles = async () => {
    setSeedLoading((prev) => ({ ...prev, posting_profiles: true }));
    try {
      const res = await fetch(`${API_BASE}/api/rahaza/admin/seed-posting-profiles`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const data = await res.json();
      if (data.ok) {
        toast.success(`Posting Profiles seeded: ${data.count_before} → ${data.count_after} profiles`);
        await fetchStatus();
      } else {
        toast.error(data.error || 'Seed Posting Profiles failed');
      }
    } catch (err) {
      console.error('Seed Posting Profiles error:', err);
      toast.error('Terjadi kesalahan');
    } finally {
      setSeedLoading((prev) => ({ ...prev, posting_profiles: false }));
    }
  };

  const handleSeedAll = async () => {
    setSeedLoading((prev) => ({ ...prev, all: true }));
    try {
      const res = await fetch(`${API_BASE}/api/rahaza/admin/seed-all-accounting`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const data = await res.json();
      if (data.ok) {
        let msg = 'Semua seed berhasil: ';
        const details = data.details || {};
        if (details.coa?.ok) msg += `COA (${details.coa.count_after}) `;
        if (details.posting_profiles?.ok) msg += `Profiles (${details.posting_profiles.count_after}) `;
        toast.success(msg);
        await fetchStatus();
      } else {
        toast.error('Seed all failed');
      }
    } catch (err) {
      console.error('Seed all error:', err);
      toast.error('Terjadi kesalahan');
    } finally {
      setSeedLoading((prev) => ({ ...prev, all: false }));
    }
  };

  const StatusBadge = ({ status }) => {
    if (status === 'ready') {
      return <Badge className="bg-success/15 text-success hover:bg-success/20">Ready</Badge>;
    }
    return <Badge variant="outline" className="text-muted-foreground">Empty</Badge>;
  };

  if (loading && !status) {
    return (
      <div className="h-screen flex items-center justify-center" data-testid="admin-setup-loading">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="h-screen overflow-auto bg-background p-4 md:p-6" data-testid="admin-setup-panel-module">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight" data-testid="module-title">
              Admin Setup Panel
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Setup COA, Posting Profiles, dan master data accounting untuk deployment baru
            </p>
          </div>
          <div className="flex gap-2">
            <Badge variant="outline" className="text-xs">Phase 7F</Badge>
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={fetchStatus}
              data-testid="refresh-status-btn"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Quick Actions */}
        <Card className="border-border/50 shadow-sm bg-primary/5">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Zap className="h-5 w-5 text-primary" />
              Quick Setup
            </CardTitle>
            <CardDescription>
              One-click setup untuk deployment baru (idempotent — aman dijalankan berulang kali)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button 
              onClick={handleSeedAll} 
              disabled={seedLoading.all}
              size="lg"
              className="w-full"
              data-testid="seed-all-btn"
            >
              {seedLoading.all ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  Setup Semua Sedang Berjalan...
                </>
              ) : (
                <>
                  <Database className="mr-2 h-5 w-5" />
                  Setup Semua (COA + Posting Profiles + EEM)
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* COA */}
          <Card className="border-border/50 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base flex items-center justify-between">
                <span>Chart of Accounts (COA)</span>
                {status && <StatusBadge status={status.coa?.status} />}
              </CardTitle>
              <CardDescription>
                {status?.coa?.count || 0} accounts
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button 
                onClick={handleSeedCOA} 
                disabled={seedLoading.coa}
                variant="outline"
                className="w-full"
                data-testid="seed-coa-btn"
              >
                {seedLoading.coa ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Seeding...
                  </>
                ) : (
                  <>
                    <Database className="mr-2 h-4 w-4" />
                    Seed COA
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Posting Profiles */}
          <Card className="border-border/50 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base flex items-center justify-between">
                <span>Posting Profiles</span>
                {status && <StatusBadge status={status.posting_profiles?.status} />}
              </CardTitle>
              <CardDescription>
                {status?.posting_profiles?.count || 0} profiles
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button 
                onClick={handleSeedPostingProfiles} 
                disabled={seedLoading.posting_profiles}
                variant="outline"
                className="w-full"
                data-testid="seed-posting-profiles-btn"
              >
                {seedLoading.posting_profiles ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Seeding...
                  </>
                ) : (
                  <>
                    <Database className="mr-2 h-4 w-4" />
                    Seed Posting Profiles
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* EEM Categories */}
          <Card className="border-border/50 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base flex items-center justify-between">
                <span>Employee Expense Categories</span>
                {status && <StatusBadge status={status.eem_categories?.status} />}
              </CardTitle>
              <CardDescription>
                {status?.eem_categories?.count || 0} categories
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-muted-foreground">
                Otomatis ter-seed saat seed all
              </div>
            </CardContent>
          </Card>

          {/* EEM GL Mapping */}
          <Card className="border-border/50 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base flex items-center justify-between">
                <span>EEM GL Mapping</span>
                {status && <StatusBadge status={status.eem_gl_mapping?.status} />}
              </CardTitle>
              <CardDescription>
                {status?.eem_gl_mapping?.count || 0} mappings
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-muted-foreground">
                Setup manual via EEM GL Mapping module
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Info */}
        <Card className="border-border/50 bg-muted/20">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              Informasi
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground space-y-2">
            <p>• <strong>COA</strong>: 88 akun standar (1-xxxx aset, 2-xxxx liabilitas, 3-xxxx ekuitas, 4-xxxx revenue, 5-xxxx income lain, 6-xxxx expense)</p>
            <p>• <strong>Posting Profiles</strong>: 18+ event types (ar_invoice, ap_invoice, payroll_run, inventory_*, expense, wip_to_fg, bank_transfer, dll)</p>
            <p>• <strong>Idempotent</strong>: Aman dijalankan berulang kali tanpa duplikasi data</p>
            <p>• <strong>Auto-seed on startup</strong>: Deployment baru otomatis seed COA & Posting Profiles jika masih kosong</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
