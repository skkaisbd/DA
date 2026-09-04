/**
 * MarketingReportsHub.jsx
 * Consolidation #8: Marketing Reports — Overview + Sales + Ads + Harian + MINGGUAN + Bulanan
 * Replaces: marketing-overview + marketing-performance + marketing-ads
 *           + marketing-daily-report + marketing-monthly-report (5 entries → 1)
 *
 * 2026-08-12 (F8) — tab **Rapat Mingguan** ditambahkan di sini, BUKAN sebagai pintu
 * menu baru: laporan rapat adalah laporan, dan aturan IA v2.1 melarang dua pintu
 * untuk satu fungsi. Deep-link `marketing-weekly-report` diarahkan ke tab ini lewat
 * `makeRedirect('marketing-reports','weekly')` yang menitipkan kunci tab di
 * sessionStorage (`hub_tab_marketing-reports`) — karena itu hub ini kini MEMBACA
 * kunci tersebut; sebelumnya deep-link tab apa pun ke hub ini selalu mendarat di
 * Overview dan pemakainya harus mencari tabnya sendiri.
 */
import React, { useState, useEffect } from 'react';
import {
  LayoutDashboard, BarChart3, MousePointer,
  CalendarCheck, Calendar, CalendarRange,
} from 'lucide-react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import MarketingOverviewDashboard  from './marketing/MarketingOverviewDashboard';
import SalesPerformanceDashboard   from './marketing/SalesPerformanceDashboard';
import AdsPerformanceDashboard     from './marketing/AdsPerformanceDashboard';
import DailyReportModule           from './marketing/DailyReportModule';
import WeeklyMeetingReportModule   from './marketing/WeeklyMeetingReportModule';
import MonthlyReportModule         from './marketing/MonthlyReportModule';

const HUB_ID = 'marketing-reports';
const TAB_KEYS = ['overview', 'sales', 'ads', 'daily', 'weekly', 'monthly'];
// Deep-link id → tab awal. `moduleId` dikirim App.js ke setiap modul, jadi tab
// yang diminta tidak bergantung pada urutan mount (pola sessionStorage lama
// terbukti mendarat di tab pertama).
const MODULE_TAB = { 'marketing-weekly-report': 'weekly' };

/** Tab yang diminta URL hash — dibaca LANGSUNG di sini, bukan hanya lewat prop.
 *
 * KENAPA DIULANG DI SINI (SESI #11): tab yang diminta tautan sebelumnya hanya
 * sampai lewat `initialTab`/sessionStorage, dan keduanya hanya terbaca **sekali
 * saat mount**. Akibatnya dua keadaan nyata gagal:
 *   1. mengubah hash sementara hub SUDAH terbuka (`#marketing-reports=weekly`
 *      ditempel di address bar) tidak memindahkan tab sama sekali — pemakai
 *      menyimpulkan tautannya rusak;
 *   2. urutan mount vs. `setCurrentModule` bergantung waktu ⇒ hasilnya kadang
 *      Overview, kadang tab yang benar (persis kebingungan yang membuat penguji
 *      sesi lalu melaporkan "tabel Laporan Harian tidak ada").
 * Membaca hash langsung membuat layar ini tidak bergantung pada urutan siapa
 * pun. `HUB_ID` dicocokkan supaya hash untuk modul LAIN tidak ikut dipakai.
 */
function tabFromHash() {
  try {
    const raw = (window.location.hash || '').replace(/^#/, '');
    if (!raw) return null;
    const parts = raw.split(/[=#/]/);
    if (parts[0] !== HUB_ID && !MODULE_TAB[parts[0]]) return null;
    const t = (parts.slice(1).join('') || '').trim();
    return TAB_KEYS.includes(t) ? t : null;
  } catch (e) { return null; }
}

export default function MarketingReportsHub({ token, onNavigate, moduleId, initialTab }) {
  const [activeTab, setActiveTab] = useState(() => {
    const fromHash = tabFromHash();
    if (fromHash) return fromHash;
    if (initialTab && TAB_KEYS.includes(initialTab)) return initialTab;
    if (MODULE_TAB[moduleId]) return MODULE_TAB[moduleId];
    try {
      const saved = sessionStorage.getItem(`hub_tab_${HUB_ID}`);
      if (saved && TAB_KEYS.includes(saved)) {
        sessionStorage.removeItem(`hub_tab_${HUB_ID}`);
        return saved;
      }
    } catch (e) { /* sessionStorage tidak tersedia */ }
    return 'overview';
  });

  // Hash BERUBAH sementara hub sudah terbuka ⇒ pindah tab (lihat `tabFromHash`).
  useEffect(() => {
    const onHash = () => { const t = tabFromHash(); if (t) setActiveTab(t); };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // Prop `initialTab` berubah (App.js membaca hash lebih dulu) ⇒ ikut pindah.
  useEffect(() => {
    if (initialTab && TAB_KEYS.includes(initialTab)) setActiveTab(initialTab);
  }, [initialTab]);

  // SESI #11 — TAB YANG AKTIF DITULIS KE URL supaya tautannya BISA DIBAGIKAN.
  // Kenapa: hub ini memuat 6 laporan di satu pintu, tetapi URL-nya selalu
  // `#marketing-reports` — jadi "kirim laporan hariannya ke saya" tidak pernah
  // bisa dijawab dengan menempel tautan; penerima selalu mendarat di Overview
  // dan harus dituntun ("klik tab ke-4"). `replaceState` dipakai (BUKAN
  // `location.hash = …`) supaya tidak memicu `hashchange` → tidak ada
  // re-mount modul yang membuang isi tabel/penyaring yang sedang dilihat.
  const selectTab = (t) => {
    setActiveTab(t);
    try {
      const want = `#${HUB_ID}=${t}`;
      if (window.location.hash !== want) window.history.replaceState(null, '', want);
    } catch (e) { /* history tidak tersedia */ }
  };

  return (
    <div className="h-full" data-testid="marketing-reports-hub">
      {/* Hub Header */}
      <div className="px-4 md:px-6 py-4 border-b bg-background">
        <h1 className="text-xl font-bold tracking-tight">Laporan &amp; Analytics Marketing</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Overview eksekutif, performa penjualan, iklan, laporan harian, rapat mingguan &amp; bulanan PIC
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={selectTab} className="h-full flex flex-col">
        <div className="px-4 md:px-6 pt-4 border-b bg-background">
          <TabsList className="h-9 flex-wrap">
            <TabsTrigger value="overview" className="gap-1.5" data-testid="tab-overview">
              <LayoutDashboard size={13} />
              Overview
            </TabsTrigger>
            <TabsTrigger value="sales" className="gap-1.5" data-testid="tab-sales-perf">
              <BarChart3 size={13} />
              Sales Performa
            </TabsTrigger>
            <TabsTrigger value="ads" className="gap-1.5" data-testid="tab-ads-perf">
              <MousePointer size={13} />
              Ads Performa
            </TabsTrigger>
            <TabsTrigger value="daily" className="gap-1.5" data-testid="tab-daily-report">
              <CalendarCheck size={13} />
              Laporan Harian
            </TabsTrigger>
            <TabsTrigger value="weekly" className="gap-1.5" data-testid="tab-weekly-report">
              <CalendarRange size={13} />
              Rapat Mingguan
            </TabsTrigger>
            <TabsTrigger value="monthly" className="gap-1.5" data-testid="tab-monthly-report">
              <Calendar size={13} />
              Laporan Bulanan
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="overview" className="flex-1 overflow-auto m-0">
          <MarketingOverviewDashboard token={token} onNavigate={onNavigate} />
        </TabsContent>
        <TabsContent value="sales" className="flex-1 overflow-auto m-0">
          <SalesPerformanceDashboard token={token} />
        </TabsContent>
        <TabsContent value="ads" className="flex-1 overflow-auto m-0">
          <AdsPerformanceDashboard token={token} />
        </TabsContent>
        <TabsContent value="daily" className="flex-1 overflow-auto m-0 p-4 md:p-6">
          <DailyReportModule token={token} />
        </TabsContent>
        <TabsContent value="weekly" className="flex-1 overflow-auto m-0 p-4 md:p-6">
          {activeTab === 'weekly' && <WeeklyMeetingReportModule token={token} />}
        </TabsContent>
        <TabsContent value="monthly" className="flex-1 overflow-auto m-0 p-4 md:p-6">
          <MonthlyReportModule token={token} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
