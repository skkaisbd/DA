/**
 * Asset Management Portal — CV. Dewi Aditya ERP
 * Manajemen aset perusahaan + Procurement Request (Request Pengadaan)
 * Terintegrasi dengan Finance (journal entries otomatis)
 *
 * Phase 4 refactor (2026-05-23):
 * - All 7 tabs extracted to ./asset/tabs/*
 * - This file is now a slim orchestrator (state + data loaders + composition).
 */
import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import AssetScannerModal from './AssetScannerModal';
import {
  Package, Plus, RefreshCw,
  ShoppingCart, TrendingDown,
  Upload, Scan,
  Gauge, ShieldAlert, RotateCcw,
} from 'lucide-react';

// Phase 1-3 refactor — extracted helpers/dialogs/drawers/sections
import { apicall } from './asset/utils';
import { EditCategoryDialog } from './asset/dialogs/EditCategoryDialog';
import { TransferAssetDialog } from './asset/dialogs/TransferAssetDialog';
import { DisposalRequestDialog } from './asset/dialogs/DisposalRequestDialog';
import { BulkImportDialog } from './asset/dialogs/BulkImportDialog';
import { CreateAssetDialog } from './asset/dialogs/CreateAssetDialog';
import { CreatePRDialog } from './asset/dialogs/CreatePRDialog';
import { DisposalApprovalInbox } from './asset/sections/DisposalApprovalInbox';
import { AssetDetailDrawer } from './asset/drawers/AssetDetailDrawer';
import { PRDetailDrawer } from './asset/drawers/PRDetailDrawer';

// Phase 4 refactor — extracted tabs
import { DashboardTab } from './asset/tabs/DashboardTab';
import { AssetsTab } from './asset/tabs/AssetsTab';
import { CategoriesTab } from './asset/tabs/CategoriesTab';
import { ProcurementTab } from './asset/tabs/ProcurementTab';
import { UtilizationReportTab } from './asset/tabs/UtilizationReportTab';
import { PredictiveMaintenanceTab } from './asset/tabs/PredictiveMaintenanceTab';
// ACC-3 — Peminjaman Alat & Aset (relokasi dari Portal Aksesoris)
import { LoansTab } from './asset/tabs/LoansTab';

// ── Main Portal Component ───────────────────────────────────────────────────
export default function AssetManagementPortal({ token, user, defaultTab }) {
  // Fix menu-duplikat: 3 menu sidebar (dashboard/daftar/pengadaan) kini membuka tab berbeda
  const [mainTab, setMainTab] = useState(defaultTab || 'dashboard');
  const [dashData, setDashData] = useState(null);
  const [expiringAlerts, setExpiringAlerts] = useState(null);
  const [assets, setAssets] = useState([]);
  const [assetPagination, setAssetPagination] = useState({ total: 0, page: 1, total_pages: 1 });
  const [categories, setCategories] = useState([]);
  const [prData, setPrData] = useState([]);
  const [prInbox, setPrInbox] = useState([]);
  const [prTab, setPrTab] = useState('all');
  const [inboxScope, setInboxScope] = useState('relevant'); // relevant | all | mine
  const [inboxDept, setInboxDept] = useState(''); // optional dept filter (admin only)
  const [selectedAsset, setSelectedAsset] = useState(null);
  const [selectedPR, setSelectedPR] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [showCreateAsset, setShowCreateAsset] = useState(false);
  const [showCreatePR, setShowCreatePR] = useState(false);
  const [showEditCategory, setShowEditCategory] = useState(false);
  const [showAssetScanner, setShowAssetScanner] = useState(false);
  const [showTransferAsset, setShowTransferAsset] = useState(false);
  const [assetToTransfer, setAssetToTransfer] = useState(null);
  const [showBulkImport, setShowBulkImport] = useState(false);
  const [showDisposalRequest, setShowDisposalRequest] = useState(false);
  const [assetForDisposal, setAssetForDisposal] = useState(null);
  const [assetSearch, setAssetSearch] = useState('');
  const [assetStatus, setAssetStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const [prSearch, setPrSearch] = useState('');

  // Load dashboard
  const loadDashboard = useCallback(async () => {
    try {
      const d = await apicall('GET', '/api/assets/dashboard', token);
      setDashData(d);
    } catch {}
  }, [token]);

  // Load expiring alerts (warranty + insurance)
  const loadExpiringAlerts = useCallback(async () => {
    try {
      const d = await apicall('GET', '/api/assets/expiring-alerts?days=30', token);
      setExpiringAlerts(d);
    } catch {}
  }, [token]);

  // Load assets
  const loadAssets = useCallback(async (page = 1) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page, limit: 20 });
      if (assetSearch) params.set('search', assetSearch);
      if (assetStatus) params.set('status', assetStatus);
      const d = await apicall('GET', `/api/assets?${params}`, token);
      if (d.items) {
        setAssets(d.items);
        setAssetPagination(d.pagination);
      }
    } catch {}
    finally { setLoading(false); }
  }, [token, assetSearch, assetStatus]);

  // Load categories
  const loadCategories = useCallback(async () => {
    try {
      const d = await apicall('GET', '/api/assets/categories', token);
      if (Array.isArray(d)) setCategories(d);
    } catch (e) {
      console.warn('loadCategories error:', e.message);
    }
  }, [token]);

  // Load PRs
  const loadPRs = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: 50 });
      if (prSearch) params.set('search', prSearch);
      const inboxParams = new URLSearchParams({ scope: inboxScope });
      if (inboxDept) inboxParams.set('department', inboxDept);
      const [all, inbox] = await Promise.all([
        apicall('GET', `/api/procurement/requests?${params}`, token),
        apicall('GET', `/api/procurement/inbox?${inboxParams}`, token),
      ]);
      if (all.items) setPrData(all.items);
      if (Array.isArray(inbox)) setPrInbox(inbox);
    } catch (e) {
      console.warn('loadPRs error:', e.message);
    }
  }, [token, prSearch, inboxScope, inboxDept]);

  useEffect(() => { loadDashboard(); loadCategories(); loadExpiringAlerts(); }, [loadDashboard, loadCategories, loadExpiringAlerts]);
  useEffect(() => { if (mainTab === 'assets') loadAssets(); }, [mainTab, loadAssets]);
  useEffect(() => { if (mainTab === 'procurement') loadPRs(); }, [mainTab, loadPRs]);

  const userRole = (user?.role || '').toLowerCase();
  const isAdminLike = userRole === 'admin' || userRole === 'superadmin';
  // Daftar departemen unik (untuk filter admin) — dari prInbox + prData
  const uniqueDepartments = Array.from(new Set(
    [...(prData || []), ...(prInbox || [])]
      .map(p => (p.department || '').trim())
      .filter(Boolean)
  )).sort();

  return (
    <div className="p-4 space-y-4" data-testid="asset-mgmt-portal">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Package size={20} className="text-primary" />
            Manajemen Aset
          </h1>
          <p className="text-sm text-muted-foreground">Aset perusahaan, depresiasi, dan pengadaan</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" size="sm" onClick={() => { loadDashboard(); loadAssets(); loadPRs(); loadExpiringAlerts(); }}>
            <RefreshCw size={14} className="mr-1" /> Refresh
          </Button>
          <Button size="sm" variant="outline" onClick={() => setShowAssetScanner(true)} data-testid="scan-asset-btn">
            <Scan size={14} className="mr-1" /> Scan Asset
          </Button>
          <Button size="sm" onClick={() => setShowCreateAsset(true)} data-testid="add-asset-btn">
            <Plus size={14} className="mr-1" /> Aset Baru
          </Button>
          <Button size="sm" variant="outline" onClick={() => setShowBulkImport(true)} data-testid="bulk-import-btn">
            <Upload size={14} className="mr-1" /> Import CSV/Excel
          </Button>
          <Button size="sm" variant="outline" onClick={() => setShowCreatePR(true)} data-testid="add-pr-btn">
            <ShoppingCart size={14} className="mr-1" /> Request Pengadaan
          </Button>
          <Button size="sm" variant="outline" onClick={async () => {
            const period = new Date().toISOString().slice(0, 7);
            if (!window.confirm(`Posting depresiasi massal untuk periode ${period}?`)) return;
            try {
              const d = await apicall('POST', `/api/assets/batch-depreciate/${period}`, token, {});
              toast.success(`Depresiasi massal: ${d.total_posted} aset diposting, ${d.total_skipped} dilewati`);
              loadDashboard();
            } catch { toast.error('Gagal batch depresiasi'); }
          }} data-testid="batch-depr-btn">
            <TrendingDown size={14} className="mr-1" /> Depresiasi Massal
          </Button>
        </div>
      </div>

      <Tabs value={mainTab} onValueChange={setMainTab}>
        <TabsList>
          <TabsTrigger value="dashboard" data-testid="tab-dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="assets" data-testid="tab-assets">Aset</TabsTrigger>
          <TabsTrigger value="categories" data-testid="tab-categories">Kategori</TabsTrigger>
          <TabsTrigger value="procurement" data-testid="tab-procurement">
            Pengadaan
            {prInbox.length > 0 && (
              <Badge className="ml-1.5 text-[10px] h-4 px-1.5 bg-amber-500 text-foreground">{prInbox.length}</Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="disposal-requests" data-testid="tab-disposal">
            ⚠️ Disposal
          </TabsTrigger>
          <TabsTrigger value="utilization" data-testid="tab-utilization">
            <Gauge size={13} className="mr-1" /> Utilization
          </TabsTrigger>
          <TabsTrigger value="pm-alerts" data-testid="tab-pm-alerts">
            <ShieldAlert size={13} className="mr-1" /> Maintenance Alerts
          </TabsTrigger>
          <TabsTrigger value="loans" data-testid="tab-loans">
            <RotateCcw size={13} className="mr-1" /> Peminjaman
          </TabsTrigger>
        </TabsList>

        {/* DASHBOARD TAB */}
        <TabsContent value="dashboard" className="mt-4">
          <DashboardTab
            dashData={dashData}
            expiringAlerts={expiringAlerts}
            onAssetClick={(a) => setSelectedAsset(a)}
          />
        </TabsContent>

        {/* ASSETS TAB */}
        <TabsContent value="assets" className="mt-4">
          <AssetsTab
            assetSearch={assetSearch} setAssetSearch={setAssetSearch}
            assetStatus={assetStatus} setAssetStatus={setAssetStatus}
            assets={assets} loading={loading} assetPagination={assetPagination}
            loadAssets={loadAssets}
            onAssetClick={(a) => setSelectedAsset(a)}
          />
        </TabsContent>

        {/* CATEGORIES TAB */}
        <TabsContent value="categories" className="mt-4">
          <CategoriesTab
            categories={categories}
            onEditCategory={(c) => { setSelectedCategory(c); setShowEditCategory(true); }}
          />
        </TabsContent>

        {/* PROCUREMENT TAB */}
        <TabsContent value="procurement" className="mt-4">
          <ProcurementTab
            prTab={prTab} setPrTab={setPrTab}
            prData={prData} prInbox={prInbox}
            prSearch={prSearch} setPrSearch={setPrSearch}
            loadPRs={loadPRs}
            onSelectPR={(pr) => setSelectedPR(pr)}
            isAdminLike={isAdminLike}
            inboxScope={inboxScope} setInboxScope={setInboxScope}
            inboxDept={inboxDept} setInboxDept={setInboxDept}
            uniqueDepartments={uniqueDepartments}
          />
        </TabsContent>

        {/* ── DISPOSAL REQUESTS TAB ─────────────────────────────────────── */}
        <TabsContent value="disposal-requests" className="mt-4" data-testid="disposal-requests-tab">
          <DisposalApprovalInbox
            token={token}
            userRole={user?.role}
            onRefresh={() => { loadAssets(); loadDashboard(); }}
          />
        </TabsContent>

        {/* ── UTILIZATION REPORT TAB (Session 28) ───────────────────────── */}
        <TabsContent value="utilization" className="mt-4">
          <UtilizationReportTab token={token} categories={categories} />
        </TabsContent>

        {/* ── PREDICTIVE MAINTENANCE ALERTS TAB (Session 28) ────────────── */}
        <TabsContent value="pm-alerts" className="mt-4">
          <PredictiveMaintenanceTab token={token} categories={categories} />
        </TabsContent>

        {/* ── PEMINJAMAN ALAT & ASET TAB (ACC-3) ────────────────────────── */}
        <TabsContent value="loans" className="mt-4">
          <LoansTab token={token} />
        </TabsContent>
      </Tabs>

      {/* Modals & Drawers */}
      <CreateAssetDialog
        open={showCreateAsset}
        onClose={() => setShowCreateAsset(false)}
        token={token}
        categories={categories}
        onCreated={() => { loadAssets(); loadDashboard(); }}
      />
      <BulkImportDialog
        open={showBulkImport}
        onClose={() => setShowBulkImport(false)}
        token={token}
        categories={categories}
        onImported={() => { loadAssets(); loadDashboard(); loadExpiringAlerts(); }}
      />
      <DisposalRequestDialog
        open={showDisposalRequest}
        onClose={() => { setShowDisposalRequest(false); setAssetForDisposal(null); }}
        token={token}
        asset={assetForDisposal}
        onRequested={() => { loadAssets(); loadDashboard(); setSelectedAsset(null); }}
      />
      <AssetDetailDrawer
        asset={selectedAsset}
        token={token}
        open={!!selectedAsset}
        onClose={() => setSelectedAsset(null)}
        onRefresh={() => { loadAssets(); loadDashboard(); }}
        onTransferClick={(asset) => { setAssetToTransfer(asset); setShowTransferAsset(true); }}
        onRequestDisposalClick={(asset) => { setAssetForDisposal(asset); setShowDisposalRequest(true); }}
      />
      <CreatePRDialog
        open={showCreatePR}
        onClose={() => setShowCreatePR(false)}
        token={token}
        onCreated={() => loadPRs()}
      />
      <PRDetailDrawer
        pr={selectedPR}
        token={token}
        open={!!selectedPR}
        onClose={() => setSelectedPR(null)}
        onRefresh={loadPRs}
        currentUser={user}
      />
      <EditCategoryDialog
        open={showEditCategory}
        onClose={() => { setShowEditCategory(false); setSelectedCategory(null); }}
        token={token}
        category={selectedCategory}
        onUpdated={() => { loadCategories(); }}
      />
      {showAssetScanner && (
        <AssetScannerModal
          token={token}
          onScanned={(asset, details) => {
            setShowAssetScanner(false);
            toast.success(`Asset ${asset.asset_number} berhasil di-scan!`, {
              description: `Lokasi: ${details.location || asset.location || '-'}`,
            });
            loadAssets();
            loadDashboard();
          }}
          onClose={() => setShowAssetScanner(false)}
        />
      )}
      <TransferAssetDialog
        open={showTransferAsset}
        onClose={() => { setShowTransferAsset(false); setAssetToTransfer(null); }}
        token={token}
        asset={assetToTransfer}
        onTransferred={() => { loadAssets(); loadDashboard(); }}
      />
    </div>
  );
}
