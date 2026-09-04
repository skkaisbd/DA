# QA / Catatan Bug — Alur Portal Saya (Self-Service HR) (`flow-portal-saya`)

> Materi training (`docs/user-guide/portal-saya/flow-portal-saya.md`) sengaja **bebas**
> tag bug. Seluruh temuan/observasi dicatat **di sini** (terpisah dari materi pelatihan).

Tanggal: 2026-07 · Status flow: **Done** (POC ALL PASS + audit testid LULUS + E2E UI PASS + validator 10/10).

---

## Ringkasan

Alur Portal Saya (Self-Service HR) — profil, dashboard, kehadiran pribadi, cuti, slip gaji —
**tidak menemukan bug blocker**. Seluruh happy-path (19 pemeriksaan) dan 5 guardrail lulus
pada POC backend (`tests/flow_portal_saya_test.py`, exit 0, ALL PASS) dengan self-cleanup
sehingga DB kembali **pristine**. E2E UI diverifikasi dengan data nyata (slip gaji Rp
4.100.000 + dashboard: sisa cuti 10 hari, take home 4.1jt, 3 hadir bulan ini). Tiga catatan
observasi bersifat non-blok didokumentasikan di bawah.

---

## PSY-OBS-001 — [LOW] Auditor `data-testid` A4 (WARN) karena parsing arrow-function

- **Alat:** `python3 scripts/docgen/audit_testids.py --module-id portal-payslip portal-cuti portal-dashboard`
  → **LULUS (0 FAIL)**; A1/A2/A3 PASS. A4 (WARN) melaporkan 17 elemen "tanpa testid"
  (`PortalSayaCuti.jsx` 16, `PortalSayaDashboard.jsx` 1).
- **Analisis:** false-positive heuristik parsing (karakter `>` pada `=>` dianggap penutup
  tag). Terdapat 12 `data-testid` statik unik dan anchor kritikal (mis. `portal-cuti`) tersedia
  untuk seleksi E2E.
- **Status:** WARN diterima (konsisten dengan flow sebelumnya), tidak memblok.

---

## PSY-OBS-002 — [LOW] Role `operator` di-intercept ke Operator View

- **Konteks:** `App.js` mengarahkan role `operator` ke halaman **Operator View** (`/operator`,
  terminal input produksi) sebelum Portal Selector. Akibatnya user role `operator` tidak
  mencapai Portal Saya lewat selector standar.
- **Dampak (uji):** Untuk verifikasi E2E UI, digunakan akun karyawan dengan role non-operator
  (mis. `staff_hr`). Portal `self` (Portal Saya) terbuka untuk **semua** role via
  `ALL_ROLE_PORTALS` (`portalAccess.js`), sehingga data self-service tetap tampil sesuai
  tautan employee. Data self-service bergantung pada **tautan employee**, bukan role.
- **Status:** by-design (LOW), tidak memblok. Operator tetap dapat mengakses data pribadinya
  bila diarahkan ke modul Portal Saya melalui navigasi in-app yang sesuai.

---

## PSY-OBS-003 — [LOW] Kode status akun-belum-tertaut tidak seragam (409 vs 404)

- **Konteks:** Endpoint self-service memakai kode berbeda saat akun belum ditautkan ke
  karyawan: keluarga `/api/portal/*` dan `/api/portal-saya/me/payslips` mengembalikan **409**,
  sedangkan `/api/portal-saya/me/leaves` & `/me/leave-balance` mengembalikan **404**, dan
  `/api/rahaza/self/attendance` mengembalikan **409**.
- **Analisis:** perbedaan bawaan implementasi antar router; semantik sama ("akun belum
  terhubung ke data karyawan"). POC memverifikasi 409 pada `/api/portal/leave` (jalur utama).
- **Rekomendasi (opsional, bukan blocker):** seragamkan ke 409 (Conflict) di masa depan untuk
  konsistensi kontrak. Tidak diubah pada sesi ini untuk menjaga cakupan minimal.
- **Status:** observasi (LOW), tidak memblok.

---

## Cleanup DB

Fixture uji (POC self-cleanup) + fixture screenshot dihapus dari koleksi:
`rahaza_employees`, `rahaza_leave_types`, `rahaza_leave_requests`, `rahaza_leave_balances`,
`rahaza_payslips`, `rahaza_attendance_events`, serta user uji (`users`). Pola yang
dibersihkan: user `e2e.portalsaya.*` & `e2e.screenshot.portal@dewiaditya.id`, employee code
`E2E-*`/`DA-0007`, dan seluruh dokumen bertaut `employee_id` uji. DB dikonfirmasi **pristine**
(seluruh koleksi rahaza_* di atas = 0, users = 1 [hanya superadmin]) setelah alur selesai.
