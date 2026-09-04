/**
 * WarehouseMasterHub.jsx
 * Consolidation #3: Master Item — Material + FG dalam 1 tab-based hub
 * Replaces: wh-materials + wh-fg (2 sidebar entries → 1)
 * Effort: 6h | Risk: Low
 */
import React, { useState, useEffect } from 'react';
import { Scale, Archive, RefreshCw, Loader2, BellRing } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import RahazaMaterialsModule from './RahazaMaterialsModule';
import RahazaFGInventoryModule from './RahazaFGInventoryModule';
import StockThresholdsModule from './StockThresholdsModule';

export default function WarehouseMasterHub({ token }) {
  const [activeTab, setActiveTab]       = useState(() => {
    // Deep-link tab (`#wh-master=thresholds`) lewat kontrak `hub_tab_<id>` yang
    // sudah dipakai hub lain — dipakai tautan dari layar Alert & Reorder.
    try {
      const t = sessionStorage.getItem('hub_tab_wh-master');
      if (t) {
        sessionStorage.removeItem('hub_tab_wh-master');
        if (['material', 'fg', 'thresholds'].includes(t)) return t;
      }
    } catch (e) { /* noop */ }
    return 'material';
  });
  const [matCount, setMatCount]         = useState(null);
  const [fgCount,  setFgCount]          = useState(null);
  const [thCount,  setThCount]          = useState(null);   // material yg SUDAH punya ambang

  // Fetch summary counts for badge.
  // FASE IA-5: dulu badge "Bahan & Aksesoris" memakai `?limit=1` TANPA `page` —
  // endpoint mengabaikan `limit` pada mode non-paginasi lalu mengembalikan array,
  // sehingga badge menampilkan panjang array (mentok 500), bukan jumlah sebenarnya.
  // Badge "Produk Jadi" bahkan menghitung /fg-issues (TRANSAKSI pengeluaran FG),
  // jadi selalu 0 pada database bersih meski master FG berisi ratusan item.
  // Keduanya kini memakai paginasi (`page=1&limit=1`) dan membaca field `total`.
  useEffect(() => {
    const h = { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` };
    fetch('/api/rahaza/materials?exclude_type=fg&page=1&limit=1', { headers: h })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return;
        const total = d?.pagination?.total ?? d?.total ?? (Array.isArray(d) ? d.length : null);
        if (total !== null) setMatCount(total);
      })
      .catch(() => {});

    fetch('/api/rahaza/materials?type=fg&page=1&limit=1', { headers: h })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return;
        const total = d?.pagination?.total ?? d?.total ?? (Array.isArray(d) ? d.length : null);
        if (total !== null) setFgCount(total);
      })
      .catch(() => {});

    fetch('/api/rahaza/stock-thresholds/summary', { headers: h })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setThCount(d.with_threshold ?? null); })
      .catch(() => {});
  }, [token]);

  return (
    <div className="h-full" data-testid="warehouse-master-hub">
      {/* Hub Header */}
      <div className="px-4 md:px-6 py-4 border-b bg-background">
        <h1 className="text-xl font-bold tracking-tight">Master Item</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Master data Bahan, Aksesoris, dan Produk Jadi dalam satu tampilan terpadu
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
        <div className="px-4 md:px-6 pt-4 border-b bg-background">
          <TabsList className="h-9">
            <TabsTrigger value="material" className="gap-1.5" data-testid="tab-material">
              <Scale size={13} />
              Bahan &amp; Aksesoris
              {matCount !== null && (
                <Badge variant="secondary" className="ml-1 h-4 min-w-4 px-1 text-[10px]">
                  {matCount}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="fg" className="gap-1.5" data-testid="tab-fg">
              <Archive size={13} />
              Produk Jadi
              {fgCount !== null && (
                <Badge variant="secondary" className="ml-1 h-4 min-w-4 px-1 text-[10px]">
                  {fgCount}
                </Badge>
              )}
            </TabsTrigger>
            {/* W3 — pintu untuk MENGISI ambang stok. Alert & Reorder tidak akan
                pernah berbunyi selama tab ini tidak pernah dibuka pemilik. */}
            <TabsTrigger value="thresholds" className="gap-1.5" data-testid="tab-thresholds">
              <BellRing size={13} />
              Ambang Stok
              {thCount !== null && (
                <Badge variant={thCount === 0 ? 'destructive' : 'secondary'}
                  className="ml-1 h-4 min-w-4 px-1 text-[10px]">
                  {thCount}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="material" className="flex-1 overflow-auto m-0">
          <RahazaMaterialsModule token={token} />
        </TabsContent>
        <TabsContent value="fg" className="flex-1 overflow-auto m-0">
          <RahazaFGInventoryModule token={token} />
        </TabsContent>
        <TabsContent value="thresholds" className="flex-1 overflow-auto m-0 p-4 md:p-6">
          <StockThresholdsModule token={token} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
