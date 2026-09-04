/**
 * ImportPlanPanel — **"Apa yang akan berubah kalau saya tekan Simpan?"** (Fase 4)
 *
 * KENAPA LAYAR INI ADA
 * --------------------
 * Pratinjau impor sebelumnya bisa menjawab tiga hal: berapa baris terbaca, berapa
 * yang valid/peringatan/galat, dan berapa banyak yang SUDAH ADA (angka agregat +
 * 5 contoh). Yang tidak bisa dijawab justru pertanyaan yang menentukan pilihan
 * staf di layar itu:
 *
 *   · "kalau saya pilih **Perbarui yang lama**, nilai APA yang berubah — dari
 *      berapa menjadi berapa?"
 *   · "baris mana yang akan **dilewati**, mana yang **ditolak**, dan kenapa?"
 *
 * Itu bukan soal kenyamanan. Mode "Perbarui yang lama" bisa mengubah **status
 * pesanan** (`paid → cancelled`); perubahan itu MELEPAS reservasi stok dan
 * menurunkan omzet bulan yang mungkin sudah dirapatkan. Sebelum ini satu-satunya
 * cara melihat akibatnya adalah "commit dulu, kalau salah tekan Batalkan impor" —
 * memakai data sungguhan sebagai kelinci percobaan.
 *
 * ATURAN YANG DIPEGANG LAYAR INI
 *  1. **Angka di sini = angka hasil.** Isinya datang dari `GET …/plan` yang
 *     memakai fungsi keputusan yang SAMA dengan commit; penjaga `INV-IMPORPLAN`
 *     membandingkan keempat angkanya dengan hasil commit sungguhan.
 *  2. **Penghalang ditampilkan MENETAP, bukan toast.** Kalau seluruh commit akan
 *     ditolak (periode terkunci / periode iklan bertindih / omzet rincian live
 *     melebihi), panel merah muncul di sini dan tombol Simpan dimatikan —
 *     dengan pesan yang sama persis dengan penolakan commit.
 *  3. **Bisa diunduh.** Rencana bisa dibawa ke rapat/WhatsApp sebelum disimpan.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Loader2, Download, Search, ShieldAlert, ArrowRight, ChevronLeft, ChevronRight,
  AlertTriangle,
} from 'lucide-react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';

const API = process.env.REACT_APP_BACKEND_URL;
const BASE = `${API}/api/marketing/data-import`;
const PAGE_SIZE = 25;

/* Kosakata aksi = kosakata `row_notes` commit, jadi angka pratinjau dan angka
   hasil bisa dibandingkan tanpa penerjemah. Warnanya mengikuti AKIBAT: hijau =
   data baru masuk · biru = data lama berubah · abu = tidak terjadi apa-apa ·
   merah = tidak masuk sama sekali. */
const ACTIONS = [
  { key: 'baru', label: 'baru', help: 'akan DIBUAT sebagai baris baru',
    cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300' },
  { key: 'diperbarui', label: 'diperbarui', help: 'baris yang sudah ada akan BERUBAH',
    cls: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300' },
  { key: 'sebagian', label: 'sebagian', help: 'hanya sebagian field yang boleh ditimpa',
    cls: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300' },
  { key: 'dilewati', label: 'dilewati', help: 'dibiarkan apa adanya (tidak ada perubahan)',
    cls: 'bg-muted text-muted-foreground' },
  { key: 'ditolak', label: 'ditolak', help: 'TIDAK masuk — alasannya disebut per baris',
    cls: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300' },
];
const ACTION_CLS = Object.fromEntries(ACTIONS.map((a) => [a.key, a.cls]));

export default function ImportPlanPanel({
  sessionId, authH, onDuplicate, skipWarnings = false, onPlan, onDownload,
}) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [only, setOnly] = useState('');
  const [q, setQ] = useState('');
  const [qLive, setQLive] = useState('');
  const [page, setPage] = useState(1);

  // Pencarian di-tunda 400 ms: satu permintaan per kata, bukan per ketikan.
  useEffect(() => {
    const t = setTimeout(() => { setQ(qLive); setPage(1); }, 400);
    return () => clearTimeout(t);
  }, [qLive]);

  const load = useCallback(async () => {
    if (!sessionId) return;
    setBusy(true);
    setErr('');
    try {
      const r = await axios.get(`${BASE}/sessions/${sessionId}/plan`, {
        headers: authH,
        params: {
          on_duplicate: onDuplicate, skip_warnings: skipWarnings,
          only: only || undefined, q: q || undefined,
          page, page_size: PAGE_SIZE,
        },
      });
      setData(r.data);
      if (onPlan) onPlan(r.data);
    } catch (e) {
      setErr(e.response?.data?.detail || e.message);
      setData(null);
      if (onPlan) onPlan(null);
    } finally { setBusy(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, onDuplicate, skipWarnings, only, q, page]);

  useEffect(() => { load(); }, [load]);

  const counts = data?.counts || {};
  const rows = data?.rows || [];
  const total = data?.pagination?.total || 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const blockers = data?.blockers || [];
  const warnings = data?.warnings || [];

  const changed = useMemo(
    () => (counts.baru || 0) + (counts.diperbarui || 0) + (counts.sebagian || 0),
    [counts]);

  return (
    <div className="rounded-[var(--radius-md)] border border-border" data-testid="import-plan">
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b border-border bg-muted/40">
        <div>
          <p className="text-xs font-semibold">Apa yang akan berubah kalau Simpan ditekan</p>
          <p className="text-[11px] text-muted-foreground">
            Dihitung dengan aturan yang sama seperti penyimpanan — bukan perkiraan.
            {data?.mode_forced && (
              <> Jenis data ini <b>selalu</b> memperbarui baris lama (snapshot
              platform), jadi mode yang dipakai <b>Perbarui yang lama</b>.</>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input value={qLive} onChange={(e) => setQLive(e.target.value)}
              placeholder="cari acuan / field / alasan"
              className="h-7 pl-7 w-52 text-[11px]" data-testid="import-plan-search" />
          </div>
          <Button size="sm" variant="outline" className="h-7 text-[11px]"
            disabled={!total}
            onClick={() => onDownload && onDownload(
              `sessions/${sessionId}/plan.csv`, `rencana-impor.csv`,
              { on_duplicate: data?.mode || onDuplicate,
                skip_warnings: skipWarnings, only: only || undefined })}
            data-testid="import-plan-csv">
            <Download className="w-3 h-3 mr-1" /> Unduh rencana (CSV)
          </Button>
        </div>
      </div>

      {/* PENGHALANG SELURUH COMMIT — menetap, bukan toast. */}
      {blockers.length > 0 && (
        <div className="m-3 rounded-[var(--radius-md)] border border-red-500/50 bg-red-500/10 p-3"
          data-testid="import-plan-blockers">
          <p className="text-xs font-semibold text-red-700 dark:text-red-300 flex items-center gap-1.5">
            <ShieldAlert className="w-4 h-4" />
            Simpan akan DITOLAK — {blockers.length} penghalang
          </p>
          <ul className="mt-1.5 space-y-1">
            {blockers.map((b, i) => (
              <li key={b.code || i} className="text-[11px] leading-relaxed">• {b.message}</li>
            ))}
          </ul>
        </div>
      )}

      {/* F12 — BUKTI "berkas ini mungkin milik toko lain" yang TIDAK mematikan
          tombol Simpan (sebagian baris / impor terdahulu yang mungkin salah).
          MENETAP, bukan toast: keputusannya diambil di layar ini, jadi buktinya
          harus tetap terbaca saat staf menimbang — dan tetap ada kalau ia
          menggulir bolak-balik. */}
      {warnings.length > 0 && (
        <div className="m-3 rounded-[var(--radius-md)] border border-amber-500/50 bg-amber-500/10 p-3"
          data-testid="import-plan-warnings">
          <p className="text-xs font-semibold text-amber-700 dark:text-amber-300 flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4" />
            Periksa dulu sebelum Simpan — {warnings.length} temuan
          </p>
          <ul className="mt-1.5 space-y-1">
            {warnings.map((w, i) => (
              <li key={w.code || i} className="text-[11px] leading-relaxed">• {w.message}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Chip jumlah = penyaring. Angka yang tidak bisa diklik memaksa staf
          menggulir mencari barisnya sendiri. */}
      <div className="flex flex-wrap items-center gap-1.5 px-3 py-2 border-b border-border">
        <button type="button" onClick={() => { setOnly(''); setPage(1); }}
          className={`px-2 py-0.5 rounded-full text-[11px] border ${
            only ? 'border-border text-muted-foreground' : 'border-primary text-primary font-semibold'}`}
          data-testid="import-plan-filter-all">
          semua {counts.total || 0}
        </button>
        {ACTIONS.map((a) => (
          <button key={a.key} type="button" title={a.help}
            disabled={!counts[a.key]}
            onClick={() => { setOnly(a.key); setPage(1); }}
            className={`px-2 py-0.5 rounded-full text-[11px] ${a.cls}
              ${only === a.key ? 'ring-2 ring-primary/60' : ''}
              ${!counts[a.key] ? 'opacity-40' : ''}`}
            data-testid={`import-plan-filter-${a.key}`}>
            {counts[a.key] || 0} {a.label}
          </button>
        ))}
        <span className="text-[11px] text-muted-foreground ml-auto" data-testid="import-plan-count">
          {changed} baris menyentuh data · {counts.dilewati || 0} tidak diapa-apakan
          {' '}· {counts.ditolak || 0} tidak masuk
        </span>
      </div>

      {err && (
        <p className="px-3 py-3 text-[11px] text-red-600 dark:text-red-400"
          data-testid="import-plan-error">
          Gagal menghitung rencana: {err}
        </p>
      )}

      {busy && !rows.length ? (
        <div className="py-8 flex justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : !rows.length && !err ? (
        <p className="px-3 py-6 text-center text-[11px] text-muted-foreground"
          data-testid="import-plan-empty">
          {counts.total
            ? 'Tidak ada baris yang cocok dengan penyaring/pencarian ini.'
            : 'Belum ada baris untuk direncanakan.'}
        </p>
      ) : (
        <div className="overflow-x-auto max-h-[380px]">
          <table className="w-full text-[11px]" data-testid="import-plan-table">
            <thead className="bg-muted/60 sticky top-0">
              <tr>
                <th className="px-2 py-1.5 text-left font-semibold">Baris</th>
                <th className="px-2 py-1.5 text-left font-semibold">Akan</th>
                <th className="px-2 py-1.5 text-left font-semibold">Acuan</th>
                <th className="px-2 py-1.5 text-left font-semibold">Yang berubah (lama → baru)</th>
                <th className="px-2 py-1.5 text-left font-semibold">Alasan / catatan</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((r) => (
                <tr key={`${r.row}-${r.action}`} className="align-top hover:bg-muted/30"
                  data-testid={`import-plan-row-${r.row}`}>
                  <td className="px-2 py-1.5 text-muted-foreground">{r.row}</td>
                  <td className="px-2 py-1.5">
                    <Badge className={`text-[10px] ${ACTION_CLS[r.action] || ''}`}>
                      {r.action}
                    </Badge>
                  </td>
                  <td className="px-2 py-1.5 font-mono">{r.ref || '—'}</td>
                  <td className="px-2 py-1.5">
                    {(r.changes || []).length === 0 ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      <div className="space-y-0.5">
                        {r.changes.map((c) => (
                          <div key={c.field} className="flex items-center gap-1 flex-wrap">
                            <span className="text-muted-foreground">{c.label}:</span>
                            <span className="line-through opacity-70">{c.before}</span>
                            <ArrowRight className="w-3 h-3 text-primary" />
                            <span className="font-semibold">{c.after}</span>
                          </div>
                        ))}
                        {r.changes_hidden > 0 && (
                          <div className="text-muted-foreground">
                            +{r.changes_hidden} field lain (lihat CSV)
                          </div>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-muted-foreground max-w-[26rem]">
                    {(r.why || []).join(' · ') || '—'}
                    {r.status_now ? (
                      <div className="text-[10px] opacity-70">
                        status sekarang: {r.status_now}
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-between px-3 py-1.5 border-t border-border">
          <span className="text-[11px] text-muted-foreground">
            Halaman {page} dari {pages} · {total} baris
          </span>
          <div className="flex items-center gap-1">
            <Button size="sm" variant="outline" className="h-6 px-2"
              disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
              data-testid="import-plan-prev">
              <ChevronLeft className="w-3 h-3" />
            </Button>
            <Button size="sm" variant="outline" className="h-6 px-2"
              disabled={page >= pages} onClick={() => setPage((p) => p + 1)}
              data-testid="import-plan-next">
              <ChevronRight className="w-3 h-3" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
