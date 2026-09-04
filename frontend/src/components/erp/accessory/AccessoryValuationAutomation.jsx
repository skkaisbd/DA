/**
 * AccessoryValuationAutomation — FASE 10: dua otomasi valuasi aksesoris.
 *
 * MASALAH YANG DIPECAHKAN
 * 1) Item ber-HPP 0 hanya "ketahuan" saat orang kebetulan membuka tab Valuasi, atau
 *    lewat notifikasi PER-ITEM yang terpencar (12 item = 12 notifikasi, tanpa
 *    gambaran utuh). → Panel "Alarm belum dinilai": ringkasan harian 07:30 WIB,
 *    bisa dilihat & dikirim manual dari sini.
 * 2) Rapor valuasi harus diunduh manual tiap awal bulan; kalau lupa, tutup buku
 *    berjalan tanpa lampiran. → Panel "Rapor bulanan otomatis": kirim tanggal 1
 *    pukul 06:00 WIB ke email tim keuangan (lampiran Excel + PDF), lengkap dengan
 *    daftar penerima, status SMTP, tombol kirim sekarang, dan riwayat pengiriman.
 *
 * Endpoint: /api/acc/valuation/unvalued-digest[/send] · /api/acc/valuation/report-schedule[/send-now]
 */

import { useState, useEffect, useCallback } from 'react';
import {
  BellRing, CalendarClock, Mail, Send, Loader2, CheckCircle2, AlertTriangle,
  RefreshCw, Users, Settings2, History, Info, Clock,
} from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

const API = process.env.REACT_APP_BACKEND_URL || '';

async function api(method, path, token, body) {
  const opts = { method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(`${API}${path}`, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data;
}

const fmtNum = (n) => Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 4 });
const fmtRp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 0 })}`;

function fmtDateTime(iso) {
  if (!iso) return '-';
  try {
    // Selalu tampilkan dalam WIB: jadwal job memang berjalan di Asia/Jakarta, jadi
    // memakai zona browser (mis. UTC di server QA) membuat "01 Agu 06:00" terbaca
    // "31 Jul 23:00" dan membingungkan.
    return `${new Date(iso).toLocaleString('id-ID', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
      timeZone: 'Asia/Jakarta',
    })} WIB`;
  } catch { return String(iso).slice(0, 16); }
}

const MONTHS_ID = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli',
  'Agustus', 'September', 'Oktober', 'November', 'Desember'];

function periodLabel(m) {
  if (!m) return 'Semua periode';
  const [y, mo] = String(m).split('-');
  return `${MONTHS_ID[Number(mo) - 1] || mo} ${y}`;
}

const RUN_STATUS = {
  sent: { label: 'Terkirim', cls: 'text-emerald-700 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/10' },
  partial: { label: 'Sebagian', cls: 'text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-500/10' },
  failed: { label: 'Gagal', cls: 'text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10' },
  skipped_already_sent: { label: 'Sudah pernah', cls: 'text-muted-foreground bg-muted dark:bg-slate-500/10' },
  skipped_no_smtp: { label: 'SMTP kosong', cls: 'text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-500/10' },
  no_recipients: { label: 'Tanpa penerima', cls: 'text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-500/10' },
};

function StatusPill({ status }) {
  const s = RUN_STATUS[status] || { label: status || '-', cls: 'text-muted-foreground bg-muted' };
  return <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${s.cls}`}>{s.label}</span>;
}

export default function AccessoryValuationAutomation({ token, onChanged }) {
  const [digest, setDigest] = useState(null);
  const [sched, setSched] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [extra, setExtra] = useState('');
  const [reportMonth, setReportMonth] = useState('');
  const [openHistory, setOpenHistory] = useState(false);

  // `keepFeedback` WAJIB dipakai saat load() dipanggil dari sebuah aksi (kirim
  // digest / simpan jadwal / kirim rapor). Tanpa itu, `setErr('')` di sini
  // MENGHAPUS pesan yang baru saja di-set aksi tersebut — bug nyata: klik
  // "Kirim rapor sekarang" tanpa SMTP tidak menampilkan penjelasan apa pun.
  const load = useCallback(async (keepFeedback = false) => {
    setLoading(true);
    if (!keepFeedback) { setErr(''); setMsg(''); }
    try {
      const [d, s] = await Promise.all([
        api('GET', '/api/acc/valuation/unvalued-digest', token),
        api('GET', '/api/acc/valuation/report-schedule', token),
      ]);
      setDigest(d);
      setSched(s);
      setExtra((s.extra_emails || []).join(', '));
      setReportMonth((m) => m || s.default_month || '');
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const sendDigest = async () => {
    setBusy('digest'); setErr(''); setMsg('');
    try {
      const r = await api('POST', '/api/acc/valuation/unvalued-digest/send', token);
      setMsg(r.sent
        ? `Ringkasan ${r.items} item belum dinilai dikirim ke ${r.sent} penanggung jawab.`
        : `Tidak ada yang dikirim — ${r.skipped}`);
      await load(true);
    } catch (e) { setErr(e.message); }
    finally { setBusy(''); }
  };

  const saveSchedule = async (patch) => {
    setBusy('schedule'); setErr(''); setMsg('');
    try {
      const r = await api('PUT', '/api/acc/valuation/report-schedule', token, patch);
      setMsg(patch.enabled === false
        ? 'Rapor otomatis dimatikan. Rapor tetap bisa diunduh/kirim manual.'
        : `Pengaturan disimpan · ${r.recipients?.length || 0} penerima aktif.`);
      await load(true);
    } catch (e) { setErr(e.message); }
    finally { setBusy(''); }
  };

  const sendReport = async () => {
    setBusy('report'); setErr(''); setMsg('');
    try {
      const qs = reportMonth ? `?month=${reportMonth}` : '';
      const r = await api('POST', `/api/acc/valuation/report-schedule/send-now${qs}`, token);
      if (r.status === 'sent') setMsg(r.message);
      else if (r.status === 'skipped_no_smtp') setErr(r.message);
      else if (r.status === 'no_recipients') setErr(r.message);
      else setErr(r.message || `Status: ${r.status}`);
      await load(true);
      onChanged?.();
    } catch (e) { setErr(e.message); }
    finally { setBusy(''); }
  };

  // Skeleton HANYA saat muat pertama. Saat memuat ulang setelah aksi, panel tetap
  // tampil (kalau tidak, seluruh panel berkedip jadi skeleton dan banner hasil aksi
  // ikut hilang dari layar).
  if (loading && !digest && !sched) {
    return (
      <div className="grid lg:grid-cols-2 gap-4" data-testid="acc-val-automation-loading">
        <Skeleton className="h-56 rounded-xl" />
        <Skeleton className="h-56 rounded-xl" />
      </div>
    );
  }

  const dt = digest?.totals || {};
  const smtp = sched?.smtp || {};
  const recipients = sched?.recipients || [];
  const runs = sched?.runs || [];

  return (
    <div className="space-y-3" data-testid="acc-val-automation">
      {err && (
        <div className="text-sm text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10 border border-red-300 dark:border-red-500/20 rounded-lg px-4 py-2"
          data-testid="acc-val-auto-error">{err}</div>
      )}
      {msg && (
        <div className="text-sm text-emerald-700 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-300 dark:border-emerald-500/20 rounded-lg px-4 py-2"
          data-testid="acc-val-auto-msg">{msg}</div>
      )}

      <div className="grid lg:grid-cols-2 gap-4">
        {/* ── PANEL 1: ALARM / RINGKASAN HARIAN ─────────────────────────── */}
        <div className="bg-[var(--card-surface)] border border-border rounded-xl p-4 space-y-3"
          data-testid="acc-digest-panel">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2">
              <BellRing className="w-4 h-4 text-amber-600 dark:text-amber-400" />
              <div>
                <div className="font-semibold text-sm">Alarm item belum dinilai</div>
                <div className="text-[11px] text-muted-foreground flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {digest?.schedule_label || 'Setiap hari pukul 07:30 (Asia/Jakarta)'}
                </div>
              </div>
            </div>
            <button onClick={() => load()} className="p-1.5 border border-border rounded-lg hover:bg-foreground/5"
              title="Muat ulang" data-testid="acc-digest-refresh">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>

          {dt.items > 0 ? (
            <>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="rounded-lg bg-amber-100 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-500/20 py-2">
                  <div className="text-lg font-bold text-amber-700 dark:text-amber-400"
                    data-testid="acc-digest-count">{fmtNum(dt.items)}</div>
                  <div className="text-[11px] text-muted-foreground">item HPP 0</div>
                </div>
                <div className="rounded-lg bg-foreground/[0.03] border border-border py-2">
                  <div className="text-lg font-bold">{fmtNum(dt.items_with_stock)}</div>
                  <div className="text-[11px] text-muted-foreground">punya stok</div>
                </div>
                <div className="rounded-lg bg-foreground/[0.03] border border-border py-2">
                  <div className="text-lg font-bold">{fmtNum(dt.movements_window)}</div>
                  <div className="text-[11px] text-muted-foreground">mutasi {digest?.window_hours || 24} jam</div>
                </div>
              </div>

              <ul className="text-xs space-y-1 max-h-36 overflow-y-auto" data-testid="acc-digest-list">
                {(digest?.items || []).slice(0, 6).map((it) => (
                  <li key={it.id} className="flex items-center justify-between gap-2 border-b border-border/60 pb-1">
                    <span className="truncate">
                      <span className="font-mono text-[11px] text-muted-foreground">{it.code}</span>{' '}
                      {it.name}
                    </span>
                    <span className="shrink-0 text-muted-foreground">
                      {fmtNum(it.stock_qty)} {it.unit}
                      {it.movements_window > 0 && (
                        <span className="ml-1 px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400">
                          {it.movements_window} mutasi
                        </span>
                      )}
                    </span>
                  </li>
                ))}
                {(digest?.items || []).length > 6 && (
                  <li className="text-muted-foreground">… dan {digest.items.length - 6} item lain</li>
                )}
              </ul>
            </>
          ) : (
            <div className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-300 dark:border-emerald-500/20 rounded-lg px-3 py-2"
              data-testid="acc-digest-clean">
              <CheckCircle2 className="w-4 h-4" /> Semua aksesoris sudah punya HPP — tidak ada alarm.
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            <div className="text-[11px] text-muted-foreground">
              {digest?.last_digest
                ? `Ringkasan terakhir: ${fmtDateTime(digest.last_digest.created_at)} · ${digest.last_digest.count || 0} item`
                : 'Belum pernah mengirim ringkasan.'}
            </div>
            <button onClick={sendDigest} disabled={busy === 'digest' || !dt.items}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm bg-amber-600 text-white hover:brightness-110 disabled:opacity-50"
              data-testid="acc-digest-send">
              {busy === 'digest' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Kirim ringkasan sekarang
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground flex items-start gap-1.5">
            <Info className="w-3 h-3 mt-0.5 shrink-0" />
            Satu notifikasi berisi SEMUA item tanpa harga (bukan satu per item). Alarm per-item
            saat mutasi tetap berjalan, dibatasi 1×/24 jam per item.
          </p>
        </div>

        {/* ── PANEL 2: RAPOR BULANAN OTOMATIS ───────────────────────────── */}
        <div className="bg-[var(--card-surface)] border border-border rounded-xl p-4 space-y-3"
          data-testid="acc-report-schedule-panel">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2">
              <CalendarClock className="w-4 h-4 text-sky-600 dark:text-sky-400" />
              <div>
                <div className="font-semibold text-sm">Rapor bulanan otomatis ke keuangan</div>
                <div className="text-[11px] text-muted-foreground flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {sched?.schedule_label || 'Setiap tanggal 1 pukul 06:00 (Asia/Jakarta)'}
                  {sched?.next_run_at && ` · berikutnya ${fmtDateTime(sched.next_run_at)}`}
                </div>
              </div>
            </div>
            <button
              onClick={() => saveSchedule({ enabled: !sched?.enabled })}
              disabled={busy === 'schedule'}
              className={`px-2.5 py-1 rounded-full text-[11px] font-medium border transition ${
                sched?.enabled
                  ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-500/30'
                  : 'bg-muted text-muted-foreground border-border'}`}
              data-testid="acc-report-toggle">
              {sched?.enabled ? 'Aktif' : 'Nonaktif'}
            </button>
          </div>

          {/* Status SMTP */}
          <div className={`rounded-lg px-3 py-2 text-xs border flex items-start gap-2 ${
            smtp.configured
              ? 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-300 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-400'
              : 'bg-amber-100 dark:bg-amber-500/10 border-amber-300 dark:border-amber-500/25 text-amber-800 dark:text-amber-300'}`}
            data-testid="acc-report-smtp-status">
            {smtp.configured ? <Mail className="w-3.5 h-3.5 mt-0.5" /> : <AlertTriangle className="w-3.5 h-3.5 mt-0.5" />}
            <div>
              {smtp.configured ? (
                <>Email siap: <strong>{smtp.host}:{smtp.port}</strong> ({smtp.security}
                  {smtp.auth ? ', dengan login' : ', tanpa login'}) · pengirim {smtp.from_email || '-'}</>
              ) : (
                <>SMTP belum diisi — rapor tetap dibuat &amp; dikirim sebagai notifikasi aplikasi,
                  tapi lampiran belum bisa dikirim lewat email. Isi di{' '}
                  <a href="#maklon-notifications" className="underline font-medium">
                    Pusat Notifikasi → Pengaturan → Email (SMTP)</a>.</>
              )}
              {smtp.note && <div className="opacity-80 mt-0.5">{smtp.note}</div>}
            </div>
          </div>

          {/* Penerima */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Users className="w-3.5 h-3.5" /> Penerima ({recipients.length})
            </div>
            <div className="flex flex-wrap gap-1.5" data-testid="acc-report-recipients">
              {recipients.length === 0 && (
                <span className="text-xs text-amber-700 dark:text-amber-400">
                  Belum ada penerima — tambahkan email di bawah atau isi email pada user role keuangan.
                </span>
              )}
              {recipients.map((r) => (
                <span key={r.email}
                  className={`px-2 py-0.5 rounded-full text-[11px] border ${
                    r.source === 'role_keuangan'
                      ? 'bg-sky-100 dark:bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-300 dark:border-sky-500/30'
                      : 'bg-violet-100 dark:bg-violet-500/10 text-violet-700 dark:text-violet-400 border-violet-300 dark:border-violet-500/30'}`}
                  title={r.source === 'role_keuangan' ? `User role ${r.role}` : 'Email tambahan'}>
                  {r.email}
                </span>
              ))}
            </div>
          </div>

          {/* Email tambahan */}
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground flex items-center gap-1.5" htmlFor="acc-report-extra">
              <Settings2 className="w-3.5 h-3.5" /> Email tambahan (pisahkan dengan koma)
            </label>
            <div className="flex gap-2">
              <input id="acc-report-extra" value={extra} onChange={(e) => setExtra(e.target.value)}
                placeholder="pajak@perusahaan.id, arsip@perusahaan.id"
                className="flex-1 border border-border rounded-lg px-3 py-1.5 text-sm bg-[var(--card-surface)]"
                data-testid="acc-report-extra-emails" />
              <button onClick={() => saveSchedule({ extra_emails: extra })} disabled={busy === 'schedule'}
                className="px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-foreground/5 disabled:opacity-50"
                data-testid="acc-report-extra-save">
                {busy === 'schedule' ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Simpan'}
              </button>
            </div>
          </div>

          {/* Kirim sekarang */}
          <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-border">
            <label className="text-xs text-muted-foreground" htmlFor="acc-report-month">Periode rapor</label>
            <input id="acc-report-month" type="month" value={reportMonth}
              onChange={(e) => setReportMonth(e.target.value)}
              className="border border-border rounded-lg px-2 py-1.5 text-sm bg-[var(--card-surface)]"
              data-testid="acc-report-month" />
            <button onClick={sendReport} disabled={busy === 'report'}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm bg-sky-600 text-white hover:brightness-110 disabled:opacity-50"
              data-testid="acc-report-send-now">
              {busy === 'report' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Kirim rapor sekarang
            </button>
            <span className="text-[11px] text-muted-foreground">
              Lampiran Excel + PDF · default periode {periodLabel(sched?.default_month)}
            </span>
          </div>

          {/* Riwayat */}
          <div>
            <button onClick={() => setOpenHistory((v) => !v)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              data-testid="acc-report-history-toggle">
              <History className="w-3.5 h-3.5" />
              Riwayat pengiriman ({runs.length}) {openHistory ? '▲' : '▼'}
            </button>
            {openHistory && (
              <div className="mt-2 border border-border rounded-lg overflow-hidden" data-testid="acc-report-history">
                {runs.length === 0 ? (
                  <div className="text-xs text-muted-foreground px-3 py-3">Belum ada pengiriman.</div>
                ) : (
                  <table className="w-full text-[11px]">
                    <thead className="bg-[var(--glass-bg)] border-b border-border">
                      <tr>
                        <th className="text-left px-2 py-1.5 font-medium text-muted-foreground">Waktu</th>
                        <th className="text-left px-2 py-1.5 font-medium text-muted-foreground">Periode</th>
                        <th className="text-center px-2 py-1.5 font-medium text-muted-foreground">Status</th>
                        <th className="text-right px-2 py-1.5 font-medium text-muted-foreground">Terkirim</th>
                        <th className="text-left px-2 py-1.5 font-medium text-muted-foreground">Pemicu</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runs.slice(0, 8).map((r) => (
                        <tr key={r.id} className="border-b border-border/60">
                          <td className="px-2 py-1.5 whitespace-nowrap">{fmtDateTime(r.created_at)}</td>
                          <td className="px-2 py-1.5">{periodLabel(r.month)}</td>
                          <td className="px-2 py-1.5 text-center"><StatusPill status={r.status} /></td>
                          <td className="px-2 py-1.5 text-right">
                            {r.sent_count || 0}
                            {r.failed_count ? <span className="text-red-600 dark:text-red-400"> / {r.failed_count} gagal</span> : ''}
                            {r.total_value ? <div className="text-muted-foreground">{fmtRp(r.total_value)}</div> : null}
                          </td>
                          <td className="px-2 py-1.5 truncate max-w-[120px]" title={r.triggered_by}>{r.triggered_by}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
