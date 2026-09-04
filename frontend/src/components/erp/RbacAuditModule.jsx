/**
 * Audit RBAC — Approval & Notifikasi (Portal Sysadmin, 2026-08-07).
 *
 * Permintaan owner: "pastikan approval & notifikasi terhubung RBAC — jangan
 * sampai role A menerima notifikasi role B", plus halaman audit agar bisa
 * dipantau sendiri ke depan.
 *
 * Sumber: GET /api/admin/rbac-audit (analisis statis kode + fakta data notifikasi).
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ShieldCheck, ShieldAlert, RefreshCw, Bell, FileCheck2, Database, Info, CheckCircle2,
} from 'lucide-react';
import { toast } from 'sonner';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from './moduleAtoms';

const API = process.env.REACT_APP_BACKEND_URL || '';

const Stat = ({ label, value, tone = 'default', testId }) => (
  <div className={`rounded-lg border px-3 py-2 ${
    tone === 'bad' ? 'border-destructive/40 bg-destructive/10'
      : tone === 'good' ? 'border-emerald-500/40 bg-emerald-500/10'
        : 'border-border'}`} data-testid={testId}>
    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
    <p className="mt-1 text-2xl font-bold tabular-nums text-foreground">{value ?? '—'}</p>
  </div>
);

export default function RbacAuditModule({ token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/admin/rbac-audit`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      setData(body);
    } catch (e) {
      toast.error('Gagal memuat audit RBAC', { description: e.message });
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const ap = data?.code?.approvals;
  const nw = data?.code?.notification_writers;
  const dt = data?.data;

  return (
    <div className="space-y-6" data-testid="rbac-audit-module">
      <PageHeader
        title="Audit Approval & Notifikasi"
        subtitle="Siapa boleh memutuskan, dan siapa menerima notifikasi — diperiksa langsung dari kode & data"
        icon={ShieldCheck}
        actions={(
          <Button variant="outline" size="sm" onClick={load} disabled={loading}
                  data-testid="rbac-audit-refresh">
            <RefreshCw className={loading ? 'animate-spin' : ''} /> Periksa Ulang
          </Button>
        )}
      />

      {loading && !data ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : (
        <>
          {/* Aturan audiens */}
          <GlassCard className="p-4" hover={false}>
            <p className="flex items-start gap-2 text-xs text-muted-foreground">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <span data-testid="rbac-audit-rule">
                <span className="font-semibold text-foreground">Aturan audiens notifikasi: </span>
                {data?.audience_rule}
              </span>
            </p>
          </GlassCard>

          {/* Temuan */}
          <GlassCard className="p-4" hover={false} data-testid="rbac-audit-findings">
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
              <ShieldAlert className="h-4 w-4 text-amber-500" /> Temuan
            </h3>
            <ul className="space-y-2">
              {(data?.findings || []).map((f, i) => (
                <li key={i} className={`rounded-md border px-3 py-2 text-xs ${
                  f.level === 'warning' ? 'border-amber-500/40 bg-amber-500/10'
                    : f.level === 'ok' ? 'border-emerald-500/40 bg-emerald-500/10'
                      : 'border-border'}`}>
                  <p className="flex items-center gap-1.5 font-semibold text-foreground">
                    {f.level === 'ok' ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                      : <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />}
                    {f.title}
                  </p>
                  <p className="mt-0.5 text-muted-foreground">{f.detail}</p>
                </li>
              ))}
            </ul>
          </GlassCard>

          {/* Endpoint keputusan */}
          <GlassCard className="p-4" hover={false} data-testid="rbac-audit-approvals">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <FileCheck2 className="h-4 w-4 text-primary" /> Endpoint Keputusan (approve / reject / konfirmasi)
              </h3>
              <Badge variant={ap?.unguarded ? 'destructive' : 'secondary'} className="text-[11px]">
                {ap?.guarded}/{ap?.total} berizin
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Stat label="Total" value={ap?.total} testId="rbac-approvals-total" />
              <Stat label="Dijaga Izin" value={ap?.guarded} tone="good" testId="rbac-approvals-guarded" />
              <Stat label="Tanpa Izin" value={ap?.unguarded}
                    tone={ap?.unguarded ? 'bad' : 'good'} testId="rbac-approvals-unguarded" />
            </div>
            {(ap?.unguarded_items || []).length > 0 && (
              <div className="mt-3 overflow-x-auto rounded-lg border border-border">
                <table className="w-full min-w-max text-xs" data-testid="rbac-unguarded-table">
                  <thead className="bg-[var(--glass-bg)]">
                    <tr>
                      {['METHOD', 'ROUTE', 'FUNGSI', 'BERKAS'].map((h) => (
                        <th key={h} className="px-3 py-2 text-left font-semibold text-muted-foreground">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {ap.unguarded_items.map((r, i) => (
                      <tr key={`${r.file}-${r.line}-${i}`} className="border-t border-border">
                        <td className="px-3 py-1.5 font-mono text-foreground/70">{r.method}</td>
                        <td className="px-3 py-1.5 font-mono text-foreground">{r.route}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">{r.func}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">{r.file}:{r.line}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </GlassCard>

          {/* Penulis notifikasi */}
          <GlassCard className="p-4" hover={false} data-testid="rbac-audit-writers">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Bell className="h-4 w-4 text-primary" /> Penulis Notifikasi
              </h3>
              <Badge variant={nw?.untargeted ? 'destructive' : 'secondary'} className="text-[11px]">
                {nw?.targeted}/{nw?.total} bertarget
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Stat label="Pemanggilan" value={nw?.total} testId="rbac-writers-total" />
              <Stat label="Bertarget Penerima" value={nw?.targeted} tone="good" testId="rbac-writers-targeted" />
              <Stat label="Tanpa Target" value={nw?.untargeted}
                    tone={nw?.untargeted ? 'bad' : 'good'} testId="rbac-writers-untargeted" />
            </div>
            {(nw?.untargeted_items || []).length > 0 && (
              <ul className="mt-3 space-y-1" data-testid="rbac-untargeted-list">
                {nw.untargeted_items.map((r, i) => (
                  <li key={i} className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-[11px]">
                    <span className="font-mono text-foreground">{r.writer}</span>
                    <span className="ml-2 text-muted-foreground">{r.file}:{r.line}</span>
                    <p className="mt-0.5 truncate font-mono text-muted-foreground">{r.snippet}</p>
                  </li>
                ))}
              </ul>
            )}
          </GlassCard>

          {/* Fakta data */}
          <GlassCard className="p-4" hover={false} data-testid="rbac-audit-data">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
              <Database className="h-4 w-4 text-primary" /> Notifikasi di Database
            </h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <Stat label="Total" value={dt?.total} testId="rbac-data-total" />
              <Stat label="Personal (user_id)" value={dt?.personal_user_id} testId="rbac-data-personal" />
              <Stat label="Per Role" value={dt?.role_targeted} testId="rbac-data-role" />
              <Stat label="Daftar User" value={dt?.user_list_targeted} testId="rbac-data-userlist" />
              <Stat label="Tanpa Target" value={dt?.untargeted}
                    tone={dt?.untargeted ? 'bad' : 'good'} testId="rbac-data-untargeted" />
            </div>
            {(dt?.top_subtypes || []).length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5" data-testid="rbac-data-subtypes">
                {dt.top_subtypes.map((s) => (
                  <Badge key={s.subtype} variant="outline" className="text-[11px]">
                    {s.subtype} · {s.count}
                  </Badge>
                ))}
              </div>
            )}
          </GlassCard>
        </>
      )}
    </div>
  );
}
