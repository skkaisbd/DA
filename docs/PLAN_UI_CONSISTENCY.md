# Plan — UI Consistency Quick Wins

> Lanjutan task in-progress dari session sebelumnya. Tujuan: hilangkan visual inconsistencies
> (empty states tidak seragam, padding berbeda-beda, tombol style berbeda).

---

## 1) Status Saat Ini

- ✅ Komponen `EmptyState.jsx` sudah dibuat di session lalu.
- ✅ Sudah dipakai di `WMSFabricRollsModule.jsx`.
- ❌ **~50 modul** lain masih pakai empty state hardcoded (text saja tanpa icon/styling).

Contoh empty state hardcoded yang bermasalah:
```jsx
{data.length === 0 && <p className="text-gray-500">Tidak ada data</p>}
{!loading && items.length === 0 && <div>Belum ada item</div>}
```

Target seragam:
```jsx
<EmptyState
  icon={Boxes}
  title="Belum ada data stok"
  description="Stok akan muncul di sini setelah ada penerimaan barang."
  action={{ label: 'Buat Penerimaan', onClick: () => navigate('wh-receiving') }}
/>
```

---

## 2) Prioritas Rollout (10–15 modul, batch per portal)

### Batch 1 — Warehouse / WMS (5 modul)
1. `WMSModule.jsx` — Scanner barcode
2. `WMSFabricRollsModule.jsx` ✅ (sudah)
3. `WMSDeliveryNotesModule.jsx` — Surat Jalan
4. `WMSCMTDispatchesModule.jsx` — Dispatch ke CMT
5. `WMSOpnameEnhancedModule.jsx` — Opname SSOT

### Batch 2 — Production (5 modul)
6. `RahazaOrdersModule.jsx` — Order Produksi
7. `RahazaWorkOrdersModule.jsx` — Work Order
8. `RahazaBundlesModule.jsx` — Bundle traceability
9. `LineMonitoringModule.jsx` — Live monitoring
10. `BundleReworkBoard.jsx` — Papan rework

### Batch 3 — Maklon (3 modul)
11. `MaklonPOModule.jsx` — PO Maklon
12. `MaklonClientManagement.jsx` — Data klien
13. `VendorPortalModule.jsx` — Portal vendor (yang baru dibuat)

### Batch 4 — Aksesoris (2 modul, **bareng Fase 1**)
14. `AccessoryModule.jsx` (di tab tertentu yang banyak empty state)
15. `AccessoryRequestInbox.jsx`

---

## 3) Pola Standar (rule)

### a) Empty State
- **Selalu** pakai `<EmptyState />` (jangan custom `<div>` lagi).
- Wajib: `icon` (lucide), `title`, `description`.
- Opsional: `action` (tombol primary CTA).

### b) Loading State
- Pakai `<Skeleton />` dari shadcn — jangan `<div>Loading...</div>` polos.
- Untuk table: minimal 3–5 skeleton rows.

### c) Error State
- Pakai `<Alert variant="destructive">` dari shadcn + tombol Retry.

### d) Page padding
- Standar: `p-6 sm:p-8`
- Container: `max-w-7xl mx-auto` (tidak text-center)
- Section gap: `space-y-6`

### e) Card style
- Pakai `<Card>` shadcn, jangan `<div className="bg-white rounded shadow">`.

### f) Button variants
- Primary: `<Button>` (default)
- Destructive: `<Button variant="destructive">`
- Secondary: `<Button variant="secondary">`
- Ghost / outline: pakai variant yang sesuai
- **JANGAN** hardcode `className="bg-blue-500"` di button.

---

## 4) Estimasi

- Per modul rata-rata: 10–20 menit (cari empty state hardcoded → replace).
- Total 14 modul tersisa × 15 menit = **~3.5 jam**.
- Plus testing agent (frontend visual review): 30 menit.
- **Grand total estimasi:** ~4 jam.

---

## 5) Acceptance Criteria

- [ ] 14 modul target sudah pakai `<EmptyState />`.
- [ ] Tidak ada `<p className="text-gray-500">Tidak ada data</p>` atau pola serupa di modul target.
- [ ] Padding seragam (`p-6 sm:p-8`).
- [ ] Skeleton loader konsisten.
- [ ] Testing agent (frontend, visual smoke) lulus tanpa regresi.

---

## 6) Out-of-Scope (Fase Lanjutan)

- Refactor modul HR (50+ modul, skala besar — fase terpisah).
- Refactor modul Finance lengkap (15+ modul — fase terpisah).
- Refactor Marketing Toko modul (skala besar — fase terpisah).
- Theme refactor lengkap (dark/light mode polishing).

Fase ini fokus **quick wins** untuk modul yang paling sering dilihat user.
