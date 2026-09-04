# Plan — SSOT Badges & Button Standardization

> Tujuan: rapikan/hilangkan badge `SSOT` di sidebar yang membingungkan user awam,
> dan standarkan warna/style tombol di seluruh aplikasi.

---

## 1) Latar Belakang

### Masalah 1: Badge `SSOT` di Sidebar
Badge `SSOT` (Single Source of Truth) muncul di banyak menu sidebar, contoh:
- `wh-master` → "Master Item (Material & FG) [SSOT]"
- `wh-delivery-notes` → "Surat Jalan Customer [SSOT]"
- `fin-ar-360` → "AR 360° [SSOT]"
- `wh-accessory-ops` → "Master & Stok [SSOT]"

**Masalah:** User awam tidak tahu apa itu SSOT. Kelihatan seperti acronym teknis internal.

### Masalah 2: Tombol Style Tidak Konsisten
Di beberapa modul ada hard-coded class:
```jsx
<button className="bg-blue-500 text-white px-4 py-2 rounded">Simpan</button>
<button className="bg-green-600 hover:bg-green-700 text-white">Approve</button>
```
Seharusnya pakai shadcn variants:
```jsx
<Button>Simpan</Button>
<Button variant="default">Approve</Button>
```

---

## 2) Strategi

### a) Badge SSOT — 3 opsi (perlu konfirmasi user)

**Opsi 1: HAPUS total**
- Hilangkan `badge: 'SSOT'` di semua entry `portalNav.js`.
- Status SSOT tetap berlaku di backend (dokumentasi/dev only), tapi tidak diekspos ke UI user.

**Opsi 2: GANTI dengan label yang user-friendly**
- Misal: `SSOT` → `RESMI` atau `MASTER` atau `UTAMA`.
- Tetap kasih sinyal "ini sumber utama" tanpa jargon teknis.

**Opsi 3: BIARKAN tapi tambah tooltip**
- Tetap `SSOT`, tambah `<Tooltip>` dengan penjelasan: "Single Source of Truth — Data resmi/utama."
- Implementasi: edit komponen `NavItem.jsx` untuk render tooltip kalau ada badge.

**Rekomendasi:** **Opsi 2** (`MASTER` atau `RESMI`) — paling user-friendly tanpa kehilangan makna.

### b) Button Standardization — Audit & Refactor

#### Step 1: Audit
Grep cari semua tombol dengan className hardcoded di `/app/frontend/src/components/erp/`:
```bash
grep -rn 'className="bg-\(red\|blue\|green\|yellow\)-' /app/frontend/src/components/erp/ | grep -i 'button\|btn'
```

#### Step 2: Replace pattern
| Hardcoded | Replace dengan |
|-----------|----------------|
| `bg-blue-500/600` (primary action) | `<Button>` (default variant) |
| `bg-green-500/600` (success/approve) | `<Button>` atau warna semantic `success` |
| `bg-red-500/600` (destructive/delete) | `<Button variant="destructive">` |
| `bg-gray-100/200` (secondary) | `<Button variant="secondary">` |
| `border` only (outline) | `<Button variant="outline">` |
| Plain text link | `<Button variant="link">` atau `<Button variant="ghost">` |

#### Step 3: Validasi
- Pastikan tidak ada regresi (button masih functional, color dark/light mode OK).

---

## 3) Lokasi Target

### Badge SSOT (cek `portalNav.js`)
```bash
grep -n "badge: 'SSOT'" /app/frontend/src/components/erp/portal-shell/portalNav.js
```
Sekitar **~10 entry** yang punya badge SSOT.

### Button audit (modul prioritas)
Fokus dulu pada modul yang sering dipakai:
1. `AccessoryModule.jsx`
2. `AccessoryRequestInbox.jsx`
3. `WMSModule.jsx`
4. `VendorPortalModule.jsx`
5. `MaklonPOModule.jsx`

---

## 4) Acceptance Criteria

### Badge SSOT
- [ ] Konfirmasi user: pilih Opsi 1/2/3.
- [ ] Implementasi sesuai pilihan.
- [ ] Tidak ada regresi di sidebar (badge masih render kalau ada, label tetap rapi).

### Button
- [ ] Modul prioritas (5 modul) tidak ada lagi hardcoded `bg-{color}-{tone}` di button.
- [ ] Semua tombol pakai shadcn `<Button>` dengan variant yang sesuai.
- [ ] Dark mode & light mode visual OK.

---

## 5) Estimasi

| Task | Estimasi |
|------|----------|
| Audit & konfirmasi opsi badge SSOT dengan user | 10 menit |
| Implementasi pilihan badge | 20 menit |
| Audit hardcoded button di 5 modul prioritas | 30 menit |
| Refactor button per modul (rata 15 menit) | 75 menit |
| Testing visual (screenshot) | 20 menit |
| **Total** | **~2.5 jam** |

---

## 6) Out-of-Scope

- Refactor button di seluruh app (50+ modul) — fase besar terpisah.
- Theme/color system overhaul.
- Padding global refactor (sebagian sudah di-handle di PLAN_UI_CONSISTENCY).
