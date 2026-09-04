import React, { Suspense, useState } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../ui/tabs';

/**
 * BACKLOG-A (T3.3/T3.4/T3.5/T3.6/T3.9) — Hub generik konsolidasi modul.
 * Merender modul-modul existing sebagai tab TANPA mengubah logika modulnya.
 * Deep-link tab: makeRedirect(hubId, tabKey) menyimpan sessionStorage `hub_tab_<hubId>`.
 */
const Spinner = () => (
  <div className="flex items-center justify-center h-40">
    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[hsl(var(--primary))]" />
  </div>
);

export default function HubTabs({ hubId, title, subtitle, tabs, ...rest }) {
  const [tab, setTab] = useState(() => {
    try {
      const saved = sessionStorage.getItem(`hub_tab_${hubId}`);
      if (saved && tabs.some((t) => t.key === saved)) {
        // SESI #19 — petunjuk tab dihapus TERTUNDA (1,5 detik), bukan seketika.
        // Terukur: membuka deep-link tab (mis. `#mgmt-pdf` → hub tab 'pdf') SEBELUM
        // login membuat hub ter-mount dua kali (sekali saat alur login, sekali
        // setelahnya). Mount pertama MENGHABISKAN petunjuknya, sehingga mount kedua
        // jatuh ke tab pertama — pemakai mengklik "PDF & Kop Surat" lalu mendarat di
        // "Perusahaan" tanpa tahu kenapa. Jeda singkat membuat mount ulang tetap
        // terlayani, tanpa membuat petunjuk itu menempel selamanya.
        setTimeout(() => {
          try { sessionStorage.removeItem(`hub_tab_${hubId}`); } catch (e) { /* noop */ }
        }, 1500);
        return saved;
      }
    } catch (e) { /* sessionStorage tidak tersedia */ }
    return tabs[0]?.key;
  });

  return (
    <div className="space-y-4" data-testid={`${hubId}`}>
      {title && (
        <div>
          <h2 className="text-2xl font-bold">{title}</h2>
          {subtitle && <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>}
        </div>
      )}
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="flex flex-wrap h-auto gap-1">
          {tabs.map((t) => (
            <TabsTrigger key={t.key} value={t.key} data-testid={`hub-tab-${t.key}`}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((t) => (
          <TabsContent key={t.key} value={t.key} className="mt-4">
            {tab === t.key && (
              <Suspense fallback={<Spinner />}>
                <t.Component {...rest} />
              </Suspense>
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
