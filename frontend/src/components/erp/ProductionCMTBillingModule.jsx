/**
 * ProductionCMTBillingModule — pintu "Invoice" Portal Produksi / Maklon.
 *
 * FASE IA-1 (2026-07-26). Latar belakang (docs/PROPOSAL_IA_PRODUKSI.md §2):
 *   Alur uang keluar ke vendor CMT sudah jalan di backend
 *   (Terima FG dari CMT → AP matang di `dewi_cmt_payments` → posting jurnal
 *   `cmt_ap_invoice`), TAPI belum pernah ada layar yang menampilkannya.
 *
 * Modul ini: daftar tagihan + KPI + detail rincian + aksi "Posting ke Jurnal".
 *   - baca   : GET /api/production/cmt-billing[/summary|/{id}]
 *   - posting: POST /api/dewi/maklon/finance/cmt-payments/{id}/post-ap  (endpoint LAMA,
 *              idempotent — sengaja tidak dibuat handler duplikat)
 *   - scope  : Portal Produksi → internal, Portal Maklon → maklon (data terpisah).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  RefreshCw, Search, Receipt, Banknote, AlertTriangle, CheckCircle2,
  FileText, Eye, X, Landmark, Clock,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { apiGet, apiPost } from '../../lib/api';
import { BizBadge } from './engine/BusinessTypeBadge';
import StaffEntryBadge from './engine/StaffEntryBadge';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const fmtRp = (v) => `Rp ${Number(v || 0).toLocaleString('id-ID')}`;
const fmtNum = (v) => Number(v || 0).toLocaleString('id-ID');
const fmtDate = (d) => {
  if (!d) return '-';
  try { return new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return String(d); }
};

const STATUS_STYLE = {
  draft:     'bg-muted text-muted-foreground border-border',
  submitted: 'bg-sky-100 text-sky-700 border-sky-200',
  approved:  'bg-amber-100 text-amber-700 border-amber-200',
  paid:      'bg-emerald-100 text-emerald-700 border-emerald-200',
  cancelled: 'bg-red-100 text-red-700 border-red-200',
};

function StatusPill({ status }) {
  const key = (status || '').toLowerCase();
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${STATUS_STYLE[key] || STATUS_STYLE.draft}`}>
      {status || 'draft'}
    </span>
  );
}

function Kpi({ icon: Icon, label, value, sub, tone = 'default', testId }) {
  const tones = {
    default: 'bg-muted/40 text-foreground',
    success: 'bg-emerald-50 text-emerald-700',
    warning: 'bg-amber-50 text-amber-700',
    danger:  'bg-red-50 text-red-700',
    primary: 'bg-blue-50 text-blue-700',
  };
  return (
    <div className={`rounded-xl p-3 border border-border/60 ${tones[tone]}`} data-testid={testId}>
      <div className="flex items-center gap-1.5 text-xs opacity-80">
        <Icon className="w-3.5 h-3.5" /> {label}
      </div>
      <p className="text-xl font-bold mt-1 tabular-nums">{value}</p>
      {sub && <p className="text-[11px] opacity-70 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function ProductionCMTBillingModule({ portalId, userRole }) {
  const businessType = portalId === 'maklon' ? 'maklon' : portalId === 'production' ? 'internal' : null;
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  // F13 — filter per VENDOR. Backend sudah bisa memfilter `?partner_id=` dan
  // meresolusinya lewat SSOT `core.cmt_vendor_master` (jadi tagihan gaya lama
  // maupun gaya bridge ikut terbawa), tapi layar ini belum punya jalan
  // memakainya — kemampuan yang tidak bisa dijangkau sama dengan tidak ada.
  // Pilihannya diambil dari endpoint khusus supaya daftarnya tetap LENGKAP walau
  // tabelnya sedang tersaring.
  const [partnerId, setPartnerId] = useState('');
  const [vendorOpts, setVendorOpts] = useState([]);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [posting, setPosting] = useState('');
  const [payOpen, setPayOpen] = useState(false);
  const [cashAccounts, setCashAccounts] = useState([]);
  const [payForm, setPayForm] = useState({ cash_account_id: '', amount: '', payment_date: new Date().toISOString().slice(0, 10), reference_no: '' });
  const [disbursements, setDisbursements] = useState([]);
  useEffect(() => {
    apiGet('/rahaza/cash-accounts').then(d => setCashAccounts(Array.isArray(d) ? d : [])).catch(() => {});
  }, []);
  useEffect(() => {
    if (!detail?.bill?.id) { setDisbursements([]); return; }
    apiGet(`/dewi/maklon/finance/cmt-payments/${detail.bill.id}/disbursements`).then(d => setDisbursements(Array.isArray(d) ? d : [])).catch(() => {});
  }, [detail?.bill?.id, detail?.bill?.paid_amount]);
  const payCmt = async () => {
    if (!payForm.cash_account_id) { toast.error('Pilih rekening kas/bank'); return; }
    setPosting(detail.bill.id);
    try {
      const r = await apiPost(`/dewi/maklon/finance/cmt-payments/${detail.bill.id}/pay`, {
        cash_account_id: payForm.cash_account_id, amount: payForm.amount ? Number(payForm.amount) : null,
        payment_date: payForm.payment_date, reference_no: payForm.reference_no,
      });
      if (r?.post_error) toast.warning(`Pembayaran dicatat, jurnal gagal: ${r.post_error}`);
      else toast.success(`Pembayaran dicatat · Jurnal ${r?.gl_je_number || '-'} · status ${r?.payment_status}`);
      setPayOpen(false); setPayForm(f => ({ ...f, amount: '', reference_no: '' }));
      await load(); await openDetail(detail.bill.id);
    } catch (e) { toast.error(`Bayar gagal: ${e?.message || e}`); } finally { setPosting(''); }
  };
  const voidDisbursement = async (did) => {
    if (!window.confirm('Batalkan pembayaran ini? Jurnal akan di-void.')) return;
    try {
      await apiPost(`/dewi/maklon/finance/cmt-payments/${detail.bill.id}/disbursements/${did}/void`, {});
      toast.success('Pembayaran dibatalkan, jurnal di-void');
      await load(); await openDetail(detail.bill.id);
    } catch (e) { toast.error(`Void gagal: ${e?.message || e}`); }
  };

  const canPost = ['superadmin', 'admin', 'owner', 'accounting', 'staff_keuangan', 'manager_keuangan']
    .includes((userRole || '').toLowerCase());

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const qs = new URLSearchParams();
      if (businessType) qs.append('business_type', businessType);
      if (status) qs.append('status', status);
      if (search.trim()) qs.append('search', search.trim());
      if (partnerId) qs.append('partner_id', partnerId);
      const [list, sum] = await Promise.all([
        apiGet(`/production/cmt-billing?${qs}`),
        apiGet(`/production/cmt-billing/summary?${qs}`),
      ]);
      setRows(Array.isArray(list?.items) ? list.items : []);
      setSummary(sum);
    } catch (e) {
      setError(e?.message || 'Gagal memuat tagihan CMT');
      setRows([]);
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, [businessType, status, search, partnerId]);

  // Pilihan vendor DILEPAS dari filter vendor itu sendiri: kalau daftar pilihan
  // ikut menyusut saat satu vendor dipilih, pengguna harus mereset filter dulu
  // hanya untuk berpindah vendor.
  const loadVendors = useCallback(async () => {
    try {
      const qs = new URLSearchParams();
      if (businessType) qs.append('business_type', businessType);
      const res = await apiGet(`/production/cmt-billing/vendors?${qs}`);
      setVendorOpts(Array.isArray(res?.vendors) ? res.vendors : []);
    } catch {
      setVendorOpts([]);   // filter vendor sekadar tidak tersedia — layar tetap jalan
    }
  }, [businessType]);

  useEffect(() => { load(); }, [businessType, status, partnerId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadVendors(); }, [loadVendors]);

  const { page, setPage, totalPages, total, paged, pageSize } = useClientPagination(rows, 10);

  const openDetail = async (id) => {
    setDetailLoading(true);
    setDetail({ loading: true });
    try {
      const d = await apiGet(`/production/cmt-billing/${id}`);
      setDetail(d);
    } catch (e) {
      toast.error(`Gagal memuat detail: ${e?.message || e}`);
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const postToGl = async (id) => {
    setPosting(id);
    try {
      const r = await apiPost(`/dewi/maklon/finance/cmt-payments/${id}/post-ap`, {});
      toast.success(r?.already_posted
        ? `Sudah pernah diposting (${r?.je_number || '-'})`
        : `Berhasil posting jurnal ${r?.je_number || ''}`);
      await load();
      if (detail?.bill?.id === id) await openDetail(id);
    } catch (e) {
      toast.error(`Posting gagal: ${e?.message || e}`);
    } finally {
      setPosting('');
    }
  };

  const scopeLabel = businessType === 'maklon' ? 'Produksi Maklon (CMT)' : 'Produksi Internal';
  const totalOutstanding = useMemo(() => summary?.outstanding_amount || 0, [summary]);

  return (
    <div className="space-y-4" data-testid="prod-cmt-billing">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Receipt className="w-6 h-6 text-violet-600" /> Invoice — Tagihan CMT
            {businessType && <BizBadge type={businessType} />}
          </h1>
          <p className="text-muted-foreground text-sm mt-0.5">
            Tagihan jasa jahit dari vendor CMT (AP). Terbit otomatis setelah <strong>Terima FG dari CMT</strong> disetujui.
            {businessType && <span className="ml-1 font-medium text-foreground/80">Menampilkan data <strong>{scopeLabel}</strong>.</span>}
          </p>
        </div>
        <Button variant="outline" onClick={load} data-testid="cmt-billing-refresh" className="h-9">
          <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </Button>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700" data-testid="cmt-billing-error">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div><p className="font-semibold">Gagal memuat data</p><p className="text-xs mt-0.5">{error}</p></div>
        </div>
      )}

      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Kpi testId="cmt-kpi-total" icon={FileText} label="Total Tagihan" value={fmtNum(summary?.total_bills)} sub={`${fmtNum(summary?.total_pcs)} pcs`} />
        <Kpi testId="cmt-kpi-nilai" icon={Banknote} label="Nilai Tagihan" value={fmtRp(summary?.total_amount)} tone="primary" />
        <Kpi testId="cmt-kpi-outstanding" icon={Clock} label="Belum Dibayar" value={fmtRp(totalOutstanding)} tone="warning" sub={`${fmtNum(summary?.approved)} approved · ${fmtNum(summary?.draft)} draft`} />
        <Kpi testId="cmt-kpi-paid" icon={CheckCircle2} label="Sudah Dibayar" value={fmtRp(summary?.paid_amount)} tone="success" sub={`${fmtNum(summary?.paid)} tagihan`} />
        <Kpi testId="cmt-kpi-notposted" icon={Landmark} label="Belum Posting GL" value={fmtNum(summary?.not_posted)} tone={summary?.not_posted ? 'danger' : 'success'} sub="perlu jurnal AP" />
      </div>

      {/* Filter */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') load(); }}
            placeholder="Cari kode tagihan / vendor / PO…"
            className="pl-8 h-9 w-72"
            data-testid="cmt-billing-search"
          />
        </div>
        <SmartNativeSelect
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="h-9 w-44 border border-border rounded-lg px-2 text-sm"
          data-testid="cmt-billing-status-filter"
        >
          <option value="">Semua Status</option>
          <option value="draft">Draft</option>
          <option value="approved">Approved</option>
          <option value="paid">Paid</option>
          <option value="cancelled">Cancelled</option>
        </SmartNativeSelect>
        {/* Filter per vendor — angka "belum dibayar" ikut ditulis di pilihannya,
            karena pertanyaan finance sebelum membayar selalu "vendor ini berapa
            sisanya". Nilainya datang dari backend (SSOT), bukan dihitung ulang
            di browser. */}
        {vendorOpts.length > 0 && (
          <SmartNativeSelect
            value={partnerId}
            onChange={(e) => setPartnerId(e.target.value)}
            className="h-9 w-[23rem] border border-border rounded-lg px-2 text-sm"
            data-testid="cmt-billing-vendor-filter"
          >
            <option value="">Semua Vendor CMT ({vendorOpts.length})</option>
            {vendorOpts.map(v => (
              <option key={v.vendor_id || v.vendor_name} value={v.vendor_id}>
                {v.vendor_name}{v.vendor_code ? ` (${v.vendor_code})` : ''}
                {' — '}{v.bills} tagihan
                {v.outstanding > 0 ? ` · sisa ${fmtRp(v.outstanding)}` : ' · lunas'}
              </option>
            ))}
          </SmartNativeSelect>
        )}
        <Button variant="ghost" className="h-9 text-xs" onClick={load} data-testid="cmt-billing-apply">Terapkan</Button>
        {(partnerId || status || search.trim()) && (
          <Button variant="outline" className="h-9 text-xs"
            onClick={() => { setPartnerId(''); setStatus(''); setSearch(''); }}
            data-testid="cmt-billing-reset">
            <X className="mr-1 h-3.5 w-3.5" /> Reset filter
          </Button>
        )}
        <span className="ml-auto text-xs text-muted-foreground">
          {rows.length} tagihan
          {partnerId && vendorOpts.length > 0 && (
            <span className="ml-1 font-medium text-foreground" data-testid="cmt-billing-vendor-active">
              · {(vendorOpts.find(v => v.vendor_id === partnerId) || {}).vendor_name || ''}
            </span>
          )}
        </span>
      </div>

      {/* Tabel */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 border-b border-border">
              <tr>
                {['Kode', 'Vendor CMT', 'Sumber', 'Periode', 'Pcs', 'Nilai', 'Status', 'Jurnal GL', 'Aksi'].map(h => (
                  <th key={h} className="text-left px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {loading ? (
                <tr><td colSpan={9} className="text-center py-10 text-muted-foreground">
                  <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" /> Memuat tagihan…
                </td></tr>
              ) : paged.length === 0 ? (
                <tr><td colSpan={9} className="text-center py-12 text-muted-foreground" data-testid="cmt-billing-empty">
                  <Receipt className="w-10 h-10 mx-auto mb-2 opacity-25" />
                  <p className="font-medium">
                    {(partnerId || status || search.trim())
                      ? 'Tidak ada tagihan yang cocok dengan filter'
                      : 'Belum ada tagihan CMT'}
                  </p>
                  {(partnerId || status || search.trim()) ? (
                    <Button variant="outline" size="sm" className="mt-3"
                      onClick={() => { setPartnerId(''); setStatus(''); setSearch(''); }}
                      data-testid="cmt-billing-empty-reset">
                      <X className="mr-1 h-3.5 w-3.5" /> Tampilkan semua tagihan
                    </Button>
                  ) : (
                    <p className="text-xs mt-1">Tagihan terbit otomatis setelah <strong>Terima FG dari CMT</strong> disetujui.</p>
                  )}
                </td></tr>
              ) : paged.map((r) => (
                <tr key={r.id} className="hover:bg-muted/40" data-testid={`cmt-billing-row-${r.payment_code}`}>
                  <td className="px-3 py-2.5 font-mono text-xs font-semibold text-violet-700">{r.payment_code || r.id?.slice(0, 8)}</td>
                  <td className="px-3 py-2.5">
                    <span className="block">{r.cmt_name || '-'}</span>
                    {/* keputusan owner 3a — tagihan ini berdiri di atas angka yang
                        diketik STAF DA, bukan diisi vendor. Harus terlihat di layar
                        invoice supaya selisih tagihan bisa ditelusuri sumbernya. */}
                    <StaffEntryBadge
                      source={r.progress_entry_source}
                      by={r.staff_entered_by}
                      qty={r.staff_entered_progress_qty}
                      compact
                      testId={`cmt-billing-entry-badge-${r.payment_code}`}
                    />
                    {r.declaration_entered_by_staff && r.progress_entry_source !== 'staff'
                      && r.progress_entry_source !== 'mixed' && (
                      <StaffEntryBadge
                        source="staff"
                        by={r.declaration_entered_by}
                        compact
                        testId={`cmt-billing-decl-badge-${r.payment_code}`}
                      />
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground">
                    {r.po_number || (r.source_receipt_code ? `Receipt ${r.source_receipt_code}` : (r.job_ids?.length ? `${r.job_ids.length} job CMT` : '-'))}
                  </td>
                  <td className="px-3 py-2.5 text-xs">{fmtDate(r.period_from)} – {fmtDate(r.period_to)}</td>
                  <td className="px-3 py-2.5 tabular-nums">{fmtNum(r.total_pcs)}</td>
                  <td className="px-3 py-2.5 tabular-nums font-semibold">{fmtRp(r.amount)}</td>
                  <td className="px-3 py-2.5"><StatusPill status={r.status} /></td>
                  <td className="px-3 py-2.5 text-xs">
                    {r.gl_posted
                      ? <span className="inline-flex items-center gap-1 text-emerald-700 font-medium"><CheckCircle2 className="w-3.5 h-3.5" />{r.gl_je_number || 'posted'}</span>
                      : <span className="text-amber-700">Belum posting</span>}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1">
                      <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => openDetail(r.id)} data-testid={`cmt-billing-detail-${r.payment_code}`}>
                        <Eye className="w-3.5 h-3.5" />
                      </Button>
                      {!r.gl_posted && (r.status || '').toLowerCase() !== 'cancelled' && canPost && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 px-2 text-xs"
                          disabled={posting === r.id}
                          onClick={() => postToGl(r.id)}
                          data-testid={`cmt-billing-post-${r.payment_code}`}
                        >
                          {posting === r.id ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Landmark className="w-3.5 h-3.5 mr-1" />}
                          Posting
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <PaginationLite page={page} totalPages={totalPages} total={total} pageSize={pageSize} onPageChange={setPage} />
      </div>

      {/* Detail drawer */}
      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setDetail(null)}>
          <div
            className="bg-card border border-border rounded-2xl w-full max-w-3xl max-h-[85vh] overflow-y-auto shadow-xl"
            onClick={(e) => e.stopPropagation()}
            data-testid="cmt-billing-detail-dialog"
          >
            <div className="flex items-center justify-between px-5 py-3 border-b border-border sticky top-0 bg-card">
              <h3 className="font-bold text-foreground">Detail Tagihan CMT</h3>
              <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setDetail(null)} data-testid="cmt-billing-detail-close">
                <X className="w-4 h-4" />
              </Button>
            </div>

            {detailLoading || detail.loading ? (
              <div className="p-10 text-center text-muted-foreground">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" /> Memuat…
              </div>
            ) : (
              <div className="p-5 space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div><p className="text-xs text-muted-foreground">Kode</p><p className="font-semibold font-mono">{detail.bill?.payment_code}</p></div>
                  <div><p className="text-xs text-muted-foreground">Vendor CMT</p><p className="font-semibold">{detail.bill?.cmt_name || '-'}</p></div>
                  <div><p className="text-xs text-muted-foreground">Status</p><StatusPill status={detail.bill?.status} /></div>
                  <div><p className="text-xs text-muted-foreground">Nilai</p><p className="font-semibold">{fmtRp(detail.bill?.amount)}</p></div>
                  <div><p className="text-xs text-muted-foreground">Pcs</p><p className="font-semibold">{fmtNum(detail.bill?.total_pcs)}</p></div>
                  <div><p className="text-xs text-muted-foreground">Reject</p><p className="font-semibold">{fmtNum(detail.bill?.total_rejected)}</p></div>
                  <div><p className="text-xs text-muted-foreground">Penalti</p><p className="font-semibold">{fmtRp(detail.bill?.penalty)}</p></div>
                  <div><p className="text-xs text-muted-foreground">Domain</p><p className="font-semibold capitalize">{detail.bill?.business_type}</p></div>
                </div>

                {detail.bill?.variance_flagged && (
                  <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                    <AlertTriangle className="w-4 h-4 mt-0.5" />
                    <div>
                      <p className="font-semibold">Ada selisih qty pada penerimaan</p>
                      {detail.bill?.variance_reason && <p className="text-xs mt-0.5">{detail.bill.variance_reason}</p>}
                    </div>
                  </div>
                )}

                {Array.isArray(detail.bill?.breakdown) && detail.bill.breakdown.length > 0 && (
                  <div>
                    <p className="text-sm font-semibold mb-1.5">Rincian</p>
                    <div className="border border-border rounded-lg overflow-hidden">
                      <table className="w-full text-xs">
                        <thead className="bg-muted/40"><tr>
                          {['Produk / SKU', 'Qty', 'Tarif', 'Subtotal'].map(h => <th key={h} className="text-left px-3 py-2 font-semibold text-muted-foreground">{h}</th>)}
                        </tr></thead>
                        <tbody className="divide-y divide-border/50">
                          {detail.bill.breakdown.map((b, i) => (
                            <tr key={i}>
                              <td className="px-3 py-2">{b.product_name || b.sku || b.description || '-'}</td>
                              <td className="px-3 py-2 tabular-nums">{fmtNum(b.qty ?? b.qty_actual)}</td>
                              <td className="px-3 py-2 tabular-nums">{fmtRp(b.rate ?? b.cmt_rate_per_pcs)}</td>
                              <td className="px-3 py-2 tabular-nums font-medium">{fmtRp(b.subtotal ?? b.amount)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                <div>
                  <p className="text-sm font-semibold mb-1.5">Jurnal GL</p>
                  {detail.journal ? (
                    <div className="border border-border rounded-lg overflow-hidden">
                      <div className="px-3 py-2 bg-muted/40 text-xs flex items-center gap-3">
                        <span className="font-mono font-semibold">{detail.journal.je_number}</span>
                        <span className="text-muted-foreground">{fmtDate(detail.journal.je_date)}</span>
                        <span className="ml-auto uppercase text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">{detail.journal.status}</span>
                      </div>
                      <table className="w-full text-xs">
                        <thead className="bg-muted/20"><tr>
                          {['Akun', 'Keterangan', 'Debit', 'Kredit'].map(h => <th key={h} className="text-left px-3 py-2 font-semibold text-muted-foreground">{h}</th>)}
                        </tr></thead>
                        <tbody className="divide-y divide-border/50">
                          {(detail.journal.lines || []).map((l, i) => (
                            <tr key={i}>
                              <td className="px-3 py-2 font-mono">{l.account_code}</td>
                              <td className="px-3 py-2">{l.description}</td>
                              <td className="px-3 py-2 tabular-nums">{l.debit ? fmtRp(l.debit) : '-'}</td>
                              <td className="px-3 py-2 tabular-nums">{l.credit ? fmtRp(l.credit) : '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between gap-3 rounded-lg border border-dashed border-border px-3 py-3">
                      <p className="text-xs text-muted-foreground">
                        Belum ada jurnal AP untuk tagihan ini.
                        {detail.bill?.post_error && <span className="block text-red-600 mt-1">Error terakhir: {detail.bill.post_error}</span>}
                      </p>
                      {canPost && (detail.bill?.status || '').toLowerCase() !== 'cancelled' && (
                        <Button size="sm" onClick={() => postToGl(detail.bill.id)} disabled={posting === detail.bill?.id} data-testid="cmt-billing-detail-post">
                          {posting === detail.bill?.id ? <RefreshCw className="w-3.5 h-3.5 animate-spin mr-1" /> : <Landmark className="w-3.5 h-3.5 mr-1" />}
                          Posting ke Jurnal
                        </Button>
                      )}
                    </div>
                  )}
                </div>

                {canPost && (detail.bill?.status || '').toLowerCase() !== 'cancelled' && (
                  <div className="rounded-lg border border-border p-3 space-y-2" data-testid="cmt-pay-panel">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold">Pembayaran ke Vendor</p>
                      <span className="text-xs text-muted-foreground">Dibayar {fmtNum(detail.bill?.paid_amount || 0)} · Sisa {fmtNum(detail.bill?.outstanding_amount ?? 0)}</span>
                    </div>
                    {disbursements.length > 0 && (
                      <ul className="text-xs space-y-1">
                        {disbursements.map(d => (
                          <li key={d.id} className="flex items-center justify-between gap-2" data-testid={`cmt-disb-${d.id}`}>
                            <span>{d.payment_date} · {d.cash_account_name} · {fmtNum(d.amount)} {d.gl_je_number ? `· ${d.gl_je_number}` : ''}</span>
                            <Button size="sm" variant="ghost" className="h-6 px-2 text-red-600" onClick={() => voidDisbursement(d.id)} data-testid={`cmt-disb-void-${d.id}`}>Void</Button>
                          </li>
                        ))}
                      </ul>
                    )}
                    {(detail.bill?.outstanding_amount ?? 1) > 0 && !payOpen && (
                      <Button size="sm" onClick={() => setPayOpen(true)} data-testid="cmt-pay-open">Bayar Vendor</Button>
                    )}
                    {payOpen && (
                      <div className="grid grid-cols-2 gap-2">
                        <div className="col-span-2">
                          <SmartNativeSelect value={payForm.cash_account_id} onChange={e => setPayForm(f => ({ ...f, cash_account_id: e.target.value }))} data-testid="cmt-pay-cash-account">
                            <option value="">— Rekening kas/bank —</option>
                            {cashAccounts.map(a => <option key={a.id} value={a.id}>{a.name}{a.gl_account_code ? ` · ${a.gl_account_code}` : ''}</option>)}
                          </SmartNativeSelect>
                        </div>
                        <Input type="number" placeholder="Jumlah (kosong = sisa)" value={payForm.amount} onChange={e => setPayForm(f => ({ ...f, amount: e.target.value }))} data-testid="cmt-pay-amount" />
                        <Input type="date" value={payForm.payment_date} onChange={e => setPayForm(f => ({ ...f, payment_date: e.target.value }))} data-testid="cmt-pay-date" />
                        <Input placeholder="No. referensi" value={payForm.reference_no} onChange={e => setPayForm(f => ({ ...f, reference_no: e.target.value }))} data-testid="cmt-pay-ref" />
                        <div className="flex gap-2 justify-end">
                          <Button size="sm" variant="outline" onClick={() => setPayOpen(false)}>Batal</Button>
                          <Button size="sm" onClick={payCmt} disabled={posting === detail.bill?.id} data-testid="cmt-pay-submit">Catat Bayar</Button>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {detail.bill?.notes && (
                  <div>
                    <p className="text-sm font-semibold mb-1">Catatan</p>
                    <p className="text-xs text-muted-foreground">{detail.bill.notes}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
