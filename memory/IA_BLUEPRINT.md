# 🗺️ IA BLUEPRINT — Information Architecture (SSOT)
**CV. Dewi Aditya ERP — Portal → Section → Item**

> **Versi:** 2.0.0 (Round-2 redesign) · **Diperbarui:** 2026-07-05
> **Sumber kebenaran** untuk struktur navigasi. Implementasi: `frontend/src/components/erp/portal-shell/portalNav.js`.
> **Dijaga gate:** `scripts/guardrails/check_nav_map.py` (INV-NAV-01) — self-test-proven (bisa MERAH).
> Perubahan IA WAJIB update file ini + lolos INV-NAV-01.

---

## 1. Prinsip (landasan teori)

| Prinsip | Aturan konkret | Sumber teori |
|---|---|---|
| **MECE / Minto** | Tidak ada section beranggota 1 item (kategori tak bisa dibagi jadi 1). | Minto Pyramid |
| **Functional cohesion** | 1 section = 1 jenis pekerjaan/flow; Master vs Transaksi vs Analitik vs Setup terpisah. | Separation of Concerns |
| **Miller's Law (7±2)** | Idealnya 3–7 item per section. | Kognisi memori kerja |
| **Information scent** | Label = prediktor isi yang stabil; badge (BARU/HUB/RESMI/AI/BETA) DILARANG. | Information Foraging (Pirolli & Card) |
| **Progressive disclosure** | Ringkasan/operasional di atas; master/setup di bawah. | Nielsen |
| **Depth ≤ 4** | Portal → Section → Group → Item. | KN_14 §5.3 |

### Aturan penamaan item
- Frasa benda, Bahasa Indonesia, Title Case. Akronim industri dipertahankan: PO, PR, AR, AP, GRN, HPP, COA, GL, TB, P&L, KPI, SOP, BOM, FPY, AQL, CMT.
- Hapus badge dekoratif & item `isHeader` semu. Tanpa jargon internal ("Hub", "Bridge", "Manage").

---

## 2. Perubahan Round-2 (before → after)

### Section 1-item yang DIELIMINASI (11 titik)
| Portal | Section/grup lama (1 item) | Item dipindah ke |
|---|---|---|
| Aksesoris | DASHBOARD, PENGADAAN, LAPORAN | digabung → 3 section kohesif |
| Produksi | PROSES INTI (5 TAHAP), grup Lokasi & Workspace | Eksekusi Lantai / Proses & Standar |
| Keuangan | grup Operasi Khusus, grup Setup & Master Data | Master & Jurnal |
| SDM | KLAIM & PERJALANAN DINAS | Penggajian & Klaim |
| Marketing | TASK MANAGEMENT, FINANCE BRIDGE, grup Marketplace | After-Sales & Pengaturan / Penjualan |

### Kompresi jumlah section
| Portal | Sebelum | Sesudah |
|---|---|---|
| Gudang | 6 | **4** |
| SDM | 7 | **5** |
| Marketing | 7 | **4** |
| Produksi | 4 | **3** |
| RnD | 3 | **2** |
| Aksesoris | 5 | **3** |
| Manajemen | 3 (campur) | 3 (bersih) |

**Invarian dijaga:** 0 moduleId dihapus (deep-link aman via `moduleRegistry.js`); `sections` array tidak dihapus; badge & 7 item `isHeader` dihapus.

---

## 3. Peta AFTER (ringkas per portal)

- **Manajemen (3):** Ringkasan Eksekutif · Strategi & Approval · Administrasi Sistem
- **Produksi (3):** Operasional Harian (Dashboard/Aksi Cepat/Order/Eksekusi Lantai) · Monitoring & Analitik (Real-time/Kualitas/Performa & AI) · Master Data (Proses & Standar/Produk & Tim)
- **Gudang (4):** Inventori & Stok · Inbound — Penerimaan · Outbound — Pengiriman · Alat & Aksesoris
- **Aksesoris (3):** Dashboard & Laporan · Inventori · Request, Pinjam & Pengadaan
- **Keuangan (3):** Dashboard & Transaksi (Ringkasan/AR/P2P) · Kas & Pembayaran · Akuntansi & Laporan (Master & Jurnal/Laporan Keuangan/Biaya, Arus Kas & Aset)
- **SDM (5):** Dashboard & Approval · Karyawan & Organisasi · Rekrutmen & Pengembangan · Kehadiran, Shift & Cuti · Penggajian & Klaim
- **RnD (2):** Desain & Sampling · Costing & Analitik
- **Portal Saya (3):** Profil & Kehadiran · Kompensasi & Kinerja · Pengembangan & Dokumen
- **Maklon (5):** Master Data · Order & Produksi · Vendor CMT · Keuangan & Analitik · Pengaturan
- **Marketing (4):** Penjualan Multi-Channel · Konten, Kampanye & Kreator · Analitik, Live & AI · After-Sales & Pengaturan
- **Kolaborasi (1×2 item):** Kolaborasi
- **Aset (1×3 item):** Aset

> Total: **12 portal, 37 section, 0 single-item** (diverifikasi INV-NAV-01).

---

## 4. Cara mengubah IA (checklist)
1. Edit `portalNav.js` (jangan hapus moduleId; jangan hapus `sections`).
2. Update peta di dokumen ini.
3. `python scripts/guardrails/check_nav_map.py` → HIJAU (0 single-item/ghost/dup).
4. `esbuild` compile + screenshot sidebar minimal 1 portal terdampak.
