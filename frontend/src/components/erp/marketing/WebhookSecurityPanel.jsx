/**
 * WebhookSecurityPanel — status keamanan HMAC webhook marketplace (FASE 19 / AUDIT-2).
 *
 * Menampilkan, per platform, apakah verifikasi tanda tangan sudah aktif beserta
 * skema base string dan header yang diterima — supaya tim integrasi bisa
 * memperbaiki sendiri tanpa membuka `.env`. TIDAK PERNAH menampilkan nilai secret
 * (backend `GET /api/marketing/webhooks/security-status` tidak mengirimkannya).
 *
 * Kenapa panel ini ada: sebelum FASE 19 ketiga receiver webhook menerima tulisan
 * TANPA auth apa pun. Setelah HMAC diwajibkan, kegagalan konfigurasi berubah jadi
 * "semua webhook 401" — dan tanpa panel ini penyebabnya tidak terlihat di UI.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { ShieldCheck, ShieldAlert, RefreshCw, ChevronDown, ChevronUp, KeyRound } from 'lucide-react';
import { Card, CardContent } from '../../ui/card';
import { Button } from '../../ui/button';
import { Badge } from '../../ui/badge';

const API = process.env.REACT_APP_BACKEND_URL || '';

const LABEL = { tokopedia: 'Tokopedia', shopee: 'Shopee', tiktok: 'TikTok Shop' };

export default function WebhookSecurityPanel({ headers }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await axios.get(`${API}/api/marketing/webhooks/security-status`, { headers });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Gagal memuat status keamanan');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const allOk = data?.all_configured;
  const platforms = data?.platforms || {};

  return (
    <Card
      className={`bg-card border ${allOk ? 'border-emerald-300 dark:border-emerald-500/40' : 'border-amber-300 dark:border-amber-500/40'}`}
      data-testid="webhook-security-panel"
    >
      <CardContent className="pt-4 pb-3 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
              allOk ? 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                    : 'bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400'}`}>
              {allOk ? <ShieldCheck className="w-5 h-5" /> : <ShieldAlert className="w-5 h-5" />}
            </div>
            <div>
              <p className="text-sm font-semibold">Keamanan Webhook (HMAC-SHA256)</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {error
                  ? error
                  : allOk
                    ? 'Semua platform memverifikasi tanda tangan — payload palsu ditolak 401.'
                    : 'Sebagian platform belum punya secret. Webhook-nya akan DITOLAK (fail-closed).'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Button size="sm" variant="ghost" onClick={load} disabled={loading}
                    data-testid="btn-refresh-webhook-security">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <Button size="sm" variant="outline" onClick={() => setOpen((v) => !v)}
                    data-testid="btn-toggle-webhook-security">
              {open ? <ChevronUp className="w-4 h-4 mr-1" /> : <ChevronDown className="w-4 h-4 mr-1" />}
              Detail
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {Object.keys(platforms).length === 0 && !loading && !error && (
            <span className="text-xs text-muted-foreground">Tidak ada platform terdaftar.</span>
          )}
          {Object.entries(platforms).map(([p, v]) => (
            <Badge
              key={p}
              variant="outline"
              data-testid={`webhook-sec-${p}`}
              className={v.configured
                ? 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-500/30'
                : 'bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-300 dark:border-amber-500/30'}
            >
              {v.configured ? <ShieldCheck className="w-3 h-3 mr-1" /> : <ShieldAlert className="w-3 h-3 mr-1" />}
              {LABEL[p] || p}: {v.configured ? 'terverifikasi' : 'secret belum diset'}
            </Badge>
          ))}
        </div>

        {open && (
          <div className="rounded-lg border border-border bg-muted/40 p-3 space-y-3 text-xs">
            {Object.entries(platforms).map(([p, v]) => (
              <div key={p} className="space-y-1">
                <div className="font-semibold text-foreground flex items-center gap-1.5">
                  <KeyRound className="w-3.5 h-3.5" /> {LABEL[p] || p}
                </div>
                <div className="grid sm:grid-cols-2 gap-x-4 gap-y-0.5 text-muted-foreground">
                  <div>Base string: <code className="text-foreground">{v.base_string_scheme}</code></div>
                  <div>Header utama: <code className="text-foreground">{v.canonical_header}</code></div>
                  <div>Header diterima: <code className="text-foreground">{(v.accepted_headers || []).join(', ')}</code></div>
                  <div>Toleransi replay: <code className="text-foreground">{v.replay_tolerance_sec}s</code></div>
                  {v.uses_shared_secret && (
                    <div className="sm:col-span-2 text-amber-600 dark:text-amber-400">
                      Memakai secret bersama (dev). Di produksi set secret per-platform.
                    </div>
                  )}
                  {p === 'shopee' && (
                    <div className="sm:col-span-2">
                      URL yang ditandatangani: <code className="text-foreground break-all">{v.webhook_url || '(belum diset)'}</code>
                    </div>
                  )}
                  {p === 'tiktok' && (
                    <div className="sm:col-span-2">
                      app_key: <code className="text-foreground">{v.app_key_set ? 'sudah diset' : '(belum diset)'}</code>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {data?.env_keys && (
              <div className="pt-2 border-t border-border text-muted-foreground">
                <div className="font-semibold text-foreground mb-1">Env yang dibaca backend</div>
                {Object.entries(data.env_keys).map(([k, arr]) => (
                  <div key={k}>· <span className="text-foreground">{k}</span>: {arr.join(' · ')}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
