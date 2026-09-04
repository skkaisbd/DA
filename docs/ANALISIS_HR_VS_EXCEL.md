# ANALISIS PORTAL HR — Kebutuhan `HR - ERP System.xlsx` vs SISTEM NYATA

> **Tanggal:** 2026-07-26 · **Metode:** probe runtime, bukan pembacaan dokumen.
> **Alat bukti:** `scripts/probe_hr_gap_excel.py` (self-cleaning, 31 assert).
> **Hasil:** **11 DIDUKUNG / 20 GAP** — semua angka di bawah dihasilkan ulang dari API,
> bukan dikutip. Artefak uji dibersihkan di `finally` dan ketiadaannya dibuktikan (0 sisa).

---

## 0. RINGKASAN EKSEKUTIF (jawaban singkat)

| Pertanyaan Anda | Jawaban |
|---|---|
| Apakah **struktur data karyawan** Excel didukung? | **YA, 36/36 kolom ada** di backend & UI (`HREmployeeModule.jsx`, 822 LOC). Simpan-baca **persis** tanpa data hilang. |
| Apakah **isian pilihan (dropdown)** cocok dengan realita perusahaan? | **TIDAK.** 17 dari 18 **Jabatan** nyata, 3 dari 6 **Divisi**, **6 dari 6 Lokasi**, tipe kontrak **"Training"**, dan **semua** istilah hubungan keluarga (Ayah/Ibu/Suami/Istri) **tidak ada di pilihan**. |
| Bisakah **25 karyawan di-import** dari Excel? | **TIDAK ADA fitur import.** Harus diketik satu per satu — 25 orang × ±36 field ≈ **900 isian manual**. |
| Apakah **perhitungan THP** sesuai sheet "Data THP"? | **TIDAK.** Diuji dengan angka Tutut Nurul Fatonah: sistem menghasilkan **Rp 3.310.000** (seharusnya bruto **Rp 3.560.000**, netto **Rp 3.534.000**). |
| Apakah **BPJS & PPh21** dipotong? | **TIDAK PERNAH** di payroll run sungguhan — meski kalkulatornya lengkap dan sudah benar. Ini **bug**, bukan fitur yang belum dibuat. |

**Kesimpulan:** *pondasinya sangat kuat* (47 modul HR, kalkulator pajak Indonesia lengkap,
absensi WebAuthn/selfie/ZKTeco, cuti, shift, rekrutmen, KPI, LMS, kasbon, ESS).
Yang bermasalah adalah **sambungan terakhir ke uang** — mesin hitung slip gaji terbelah dua,
dan yang dipakai justru versi yang tidak lengkap.

---

## 1. DATA KARYAWAN — 36 kolom Excel

### 1.1 Pemetaan kolom → field (SEMUA ADA ✅)

| Grup Excel | Kolom | Field backend | Status |
|---|---|---|---|
| **INFO DASAR** (13) | Kode Karyawan | `employee_code` | ✅ |
| | Nama Lengkap | `name` | ✅ |
| | Divisi / Departemen | `department` | ✅ (nilai bebas di API) |
| | Jabatan | `job_title` | ✅ (nilai bebas di API) |
| | Atasan (Manager) | `manager_id` + `manager_name` | ✅ (relasi, divalidasi) |
| | Lokasi Utama | `location_id` | ✅ (relasi ke `rahaza_locations`) |
| | No. Telepon | `phone` | ✅ |
| | Tipe Kontrak | `contract_type` | ✅ |
| | Tgl Mulai / Berakhir Kontrak | `contract_start_date` / `contract_end_date` | ✅ + alarm kontrak habis (`GET /expiring-contracts`) |
| | Skema Gaji | `wage_scheme` | ⚠️ lihat §3.5 |
| | Rate / Base (Rp) | `base_rate` | ⚠️ lihat §3.5 |
| **PERSONAL** (11) | Jenis Kelamin, Status Pernikahan, Tempat/Tanggal Lahir, Agama, Kewarganegaraan, Alamat KTP, Alamat Tinggal, Pendidikan, Sekolah, Jurusan | `gender`, `marital_status`, `birth_place`, `birth_date`, `religion`, `nationality`, `ktp_address`, `current_address`, `education_level`, `education_institution`, `education_major` | ✅ semua |
| **Pajak & BPJS** (5) | NIK KTP, NPWP, PTKP, No. BPJS Kesehatan, No. BPJS Ketenagakerjaan | `ktp_number`, `npwp_number`, `tax_ptkp`, `bpjs_kesehatan_number`, `bpjs_ketenagakerjaan_number` | ✅ semua |
| **Bank & Emergency** (6) | Nama Bank, No. Rekening, Atas Nama, Kontak Darurat, HP Darurat, Hubungan | `bank_name`, `bank_account_number`, `bank_account_holder`, `emergency_contact_name`, `emergency_phone`, `emergency_relation` | ✅ semua |

**Bukti A1/A2:** 1 karyawan uji dibuat dengan **seluruh 34 field non-relasi** terisi →
dibaca kembali dari API → **tidak ada satu pun nilai yang hilang atau berubah**.

**Bonus di luar Excel (sudah ada):** foto karyawan, upload dokumen (Kontrak/KTP/NPWP/Ijazah/SKCK/BPJS/KK),
tautan akun login (`link-user`), email, status aktif/non-aktif.

### 1.2 GAP — pilihan dropdown tidak mencerminkan perusahaan Anda ❌

Field-nya ada, tapi **daftar pilihannya bawaan template**, bukan milik CV. Dewi Aditya.
Akibatnya HR terpaksa memilih **"Lainnya"** → data jadi tidak bisa difilter/dilaporkan.

| Isian | Yang Anda pakai | Yang ada di sistem | Hilang |
|---|---|---|---|
| **Divisi** | Akuntansi · Gudang · HRD · Marketing · Produksi · **RND** | Produksi, QC, Gudang/WMS, HRD, Finance/Accounting, Marketing, IT, Administrasi, Manajemen, Lainnya | **Akuntansi, Gudang, RND** (3/6) |
| **Jabatan** | 18 jabatan nyata (SPV Akuntansi & Keuangan, HR Generalist, Host Live, PIC Akun, Packing, Kenek Cuting, Admin Aksesoris, Driver & Petugas Umum, …) | 12 jabatan operator pabrik generik | **17 dari 18** |
| **Tipe Kontrak** | PKWT · **Training** | PKWT, PKWTT, Magang, Tetap | **Training** |
| **Hubungan darurat** | Ayah/Ibu/Kakak/Adik Kandung · Suami · Istri | Orang Tua, Pasangan, Saudara Kandung, Anak, Teman, Lainnya | **6 dari 6** (istilahnya beda semua) |
| **Lokasi Utama** | Kantor Pusat/Ruang Admin · Kantor Pusat/Ruang HR · Gudang Lt.1/Area Gudang · Gudang Lt.1/Ruang Aksesoris · Gudang Lt.2/Area Cuting · Ruang Marketing | Zona Cutting, Zona Jahit/CMT, Area Kain (Lt.2), Gedung Gudang, … (12 lokasi **gudang/produksi**) | **6 dari 6** |

> Catatan penting: **`department` & `job_title` diterima bebas oleh API** (probe A2 lolos
> dengan `RND` + `Research & Development`). Jadi ini murni masalah **daftar pilihan di UI**,
> bukan batasan database. Perbaikannya murah.

### 1.3 GAP — tidak ada import massal ❌

Dibuktikan lewat **OpenAPI schema** (bukan tebak status code): tidak ada satu pun path
karyawan yang mengandung `import`/`bulk`/`upload`.

> ⚠️ Jebakan yang hampir menipu probe pertama: `POST /api/rahaza/employees/import`
> membalas **405**, bukan 404 — karena tertangkap route `PUT /employees/{eid}` dengan
> `eid="import"`. **405 di sini artinya route TIDAK ADA.**

Padahal engine import universal (`routes/universal_import.py`, dengan preview → commit →
**rollback**) sudah ada di sistem untuk entitas lain. Karyawan belum didaftarkan ke situ.

---

## 2. PERHITUNGAN THP — sheet "Data THP"

Diuji dengan baris nomor 1 (**Tutut Nurul Fatonah**) sebagai kasus nyata:

| Komponen Excel | Nilai Excel | Didukung? | Catatan |
|---|---:|:--:|---|
| GAJI POKOK | 2.500.000 | ✅ | `payroll_profile.base_rate` |
| TUNJANGAN JABATAN | 100.000 | ✅ | template tunjangan `fixed` |
| **INS. MAKAN @10.000** | **260.000** | ❌ | **hanya jadi Rp 10.000** — lihat BUG-HR-3 |
| TUNJANGAN KESEHATAN | – | ✅ | template tunjangan `fixed` |
| BONUS KEHADIRAN | 100.000 | ⚠️ | bisa dibuat, tapi **tidak otomatis** dari kehadiran |
| TUNJANGAN TRANSPORT | 600.000 | ✅ | template tunjangan `fixed` |
| **TOTAL BRUTO** | **3.560.000** | ❌ | **sistem: Rp 3.310.000** (selisih 250.000 = ins. makan) |
| POTONGAN TERLAMBAT | – | ❌ | **data keterlambatan tidak pernah dicatat** — BUG-HR-4 |
| POTONGAN KASBON | – | ✅ | otomatis dari kasbon berstatus `disbursed` |
| **POTONGAN BPJS KESEHATAN 1%** | **26.000** | ❌ | **tidak pernah dipotong** — BUG-HR-1 |
| **TOTAL NETTO** | **3.534.000** | ❌ | **sistem: Rp 3.310.000** |

**Skor: 8 dari 12 komponen jalan — tetapi netto-nya tetap SALAH** karena 3 komponen yang gagal
semuanya menyentuh angka akhir.

---

## 3. TEMUAN KRITIS (bug uang — bukan sekadar fitur kurang)

### BUG-HR-1 🔴 — Mesin hitung slip gaji ADA DUA, yang dipakai justru yang tidak lengkap

Ada **dua fungsi dengan nama yang sama persis**:

| Berkas | Isi | Dipakai? |
|---|---|---|
| `routes/rahaza_payroll_shared.py:111` | Kasbon ✅ · **PPh21 ❌** · **BPJS ❌** · **LWOP ❌**<br>Komentarnya sendiri: *"BPJS, PPh, dll. (placeholder — disconnect from rahaza_tax for now)"* | **YA** — di-import `rahaza_payroll_runs.py:18` |
| `routes/rahaza_payroll_profiles.py:192` | **PPh21 ✅ · BPJS ✅ · LWOP ✅** · Kasbon ❌ | **TIDAK** — tidak ada satu pun pemanggil |

**Dampak berantai yang sudah dibuktikan:**
1. Potongan **BPJS Kesehatan 1%** tidak pernah muncul di slip → karyawan dibayar **lebih**, iuran tak terkumpul.
2. **PPh21** tidak pernah dipotong walau NPWP & PTKP terisi → **risiko kepatuhan pajak**.
3. `POST /payroll-runs/{id}/pay-bpjs` **selalu gagal 400** *"Tidak ada potongan BPJS di run ini"* —
   karena ia menjumlahkan `deductions[]` yang memang selalu kosong. Idem `pay-pph21`.
4. Potongan **cuti tanpa gaji (LWOP)** juga ikut hilang.

> Kalkulator pajaknya sendiri (`routes/rahaza_payroll_tax.py`) **sudah benar dan lengkap**:
> PTKP 8 status, tarif progresif UU HPP, biaya jabatan, BPJS Kesehatan 1%/4% (plafon 12 jt),
> JHT/JP/JKK/JKM. **Hanya tidak pernah dipanggil.**

### BUG-HR-2 🔴 — Rincian slip di export Excel selalu kosong (slip tidak balance)

`rahaza_payroll_runs.py` (sheet "slip gaji") membaca field **datar** yang **tidak pernah ditulis**
oleh mesin hitung: `transport_allowance`, `meal_allowance`, `base_salary`, `bpjs_kes_employee`,
`bpjs_jht_employee`, `bpjs_jp_employee`, `pph21_amount`, `kasbon_deduction`.
Mesin hitung menyimpannya sebagai **daftar**: `earnings[]`, `allowances[]`, `deductions[]`.

**Dibuktikan (G5/G6):** tunjangan transport Rp 600.000 ADA di payslip, tapi sel Excel-nya **0**.
Akibatnya kolom Penghasilan **tidak menjumlah** ke Total Bruto — slip yang dibagikan ke karyawan
terlihat salah.

> Slip **PDF** (`rahaza_payroll_payslips.py`) membaca struktur yang **benar** → PDF aman (G7 ✅).
> Jadi dua kanal cetak untuk satu slip berperilaku berbeda.

### BUG-HR-3 🟠 — Jenis perhitungan tunjangan tidak divalidasi → salah nominal DIAM-DIAM

`POST /api/rahaza/payroll-allowances` menerima `calc_type` **apa pun** (HTTP 200), tapi mesin hitung
hanya mengenal `fixed` dan `percentage_gross`; sisanya **jatuh diam-diam ke `fixed`**.

Probe: dibuat "Insentif Makan" `calc_type=per_day_attendance`, `amount=10.000`, karyawan hadir **26 hari**
→ slip menulis **Rp 10.000**, bukan Rp 260.000. **Tidak ada peringatan apa pun.**
Ini kelas bug yang sama dengan BUG-B/B2 pada FASE 12 (harga fallback diam-diam).

### BUG-HR-4 🟠 — Keterlambatan tidak pernah dicatat

Field absensi tersimpan: `clock_in, clock_out, hours_worked, overtime_hours, status, shift_id, …`
→ **tidak ada** `late_minutes` / `is_late` / grace period. Jam masuk shift **tidak pernah
dibandingkan** dengan `clock_in`. Karena itu **"POTONGAN TERLAMBAT" mustahil dihitung** —
dan Bonus Kehadiran juga tidak bisa otomatis.

### BUG-HR-5 🟡 — Skema gaji punya DUA kosakata & tidak tersambung

`rahaza_employees.wage_scheme` = `borongan_pcs | borongan_jam | mingguan | bulanan`
sedangkan `rahaza_payroll_profiles.pay_scheme` = `pcs | hourly | weekly | monthly`.
Peta konversinya **hanya ada di seeder** (`rahaza_admin_helpers.py:193`).
Saat HR menambah karyawan lewat UI, **payroll profile tidak dibuat otomatis** →
`base_rate` harus diketik **dua kali** di dua modul, dan bisa berbeda tanpa peringatan.
Karyawan yang belum punya profile **diam-diam dilewati** saat payroll run.

---

## 4. YANG SUDAH BAIK (jangan dibongkar)

* **47 modul HR** aktif: dashboard, karyawan, kontrak, absensi (manual + WebAuthn + selfie + ZKTeco),
  approval absensi, lembur, cuti + saldo cuti, shift & penjadwalan, serah-terima shift,
  payroll (profil/tunjangan/run/slip), kasbon & pinjaman, reimbursement + perjalanan dinas + per-diem,
  rekrutmen/ATS + job board + onboarding, KPI, penilaian 360°, LMS, org chart, aset karyawan,
  pengumuman, inbox approval, laporan HR, plus AI (skill gap, coaching, attrition, resume screening).
* **Master karyawan lengkap 36 kolom** + dokumen + foto + alarm kontrak habis.
* **Kalkulator pajak Indonesia lengkap & benar** (tinggal disambungkan).
* **Slip PDF** rapi, ber-watermark RAHASIA, RBAC ketat (karyawan tak bisa unduh slip orang lain).
* **Portal Saya (ESS)**: karyawan lihat slip, ajukan cuti/lembur, sertifikat training.
* **Laporan HR**: rekap absensi, lembur, payroll, turnover — JSON **dan** Excel (semuanya HTTP 200).
* **Jurnal otomatis** payroll ke GL + pembayaran BPJS/PPh21 (mekanismenya ada, tinggal angkanya).

---

## 5. USULAN PERBAIKAN BERTAHAP

### FASE HR-1 — "Angka gaji harus benar" (paling mendesak) 🔴
1. **Satukan mesin hitung slip** jadi SATU SSOT: kasbon + PPh21 + BPJS + LWOP dalam satu fungsi;
   hapus versi kembar; pasang **sentinel AST** agar tidak pernah terbelah lagi.
2. **Perbaiki export Excel slip** supaya membaca `earnings[]/allowances[]/deductions[]`
   (sumber yang sama dengan PDF) → dua kanal cetak dijamin identik.
3. **Validasi `calc_type`** — tolak nilai tak dikenal (HTTP 400), jangan diam-diam jadi `fixed`.
4. **Tambah `calc_type: per_day_attendance`** (Rp × hari hadir) untuk INS. MAKAN.
5. Uji akhir: slip Tutut **harus persis** bruto **3.560.000** / netto **3.534.000**.

### FASE HR-2 — "Data perusahaan Anda, bukan template" 🟠
6. Ganti daftar **Divisi / Jabatan / Tipe Kontrak / Hubungan** dengan istilah nyata Anda
   (+ opsi ketik bebas agar tidak mentok lagi).
7. Seed **6 lokasi kerja** nyata (Kantor Pusat/Ruang Admin, Ruang HR, Gudang Lt.1 & Lt.2, Ruang Marketing).
8. **Import massal karyawan dari Excel** — pakai engine `universal_import` yang sudah ada
   (pratinjau → validasi NIK/kode ganda → commit → **rollback**). Target: 25 baris sekali jalan.

### FASE HR-3 — "Absensi menghidupkan gaji" 🟠
9. Catat **keterlambatan** (`late_minutes`) dengan membandingkan `clock_in` vs jam masuk shift + grace period.
10. **Potongan terlambat** & **bonus kehadiran otomatis** berbasis aturan yang bisa diatur HR.
11. Satukan `wage_scheme` ↔ `pay_scheme`, dan **buat payroll profile otomatis** saat karyawan dibuat;
    beri peringatan jelas untuk karyawan yang belum punya profil sebelum run.

### FASE HR-4 — "Cocokkan dengan format kerja Anda" 🟡
12. Laporan **rekap THP** dengan kolom **persis** sheet "Data THP" (Excel & PDF), lengkap baris total.
13. Kartu **profil karyawan 1 halaman** (cetak) sesuai grup INFO DASAR / PERSONAL / Pajak & BPJS / Bank & Emergency.

---

## 6. CARA MENGULANG BUKTI INI

```bash
python3 /app/scripts/probe_hr_gap_excel.py     # 31 assert · self-cleaning · 0 artefak tersisa
```

Keluaran saat laporan ini dibuat: **11 DIDUKUNG / 20 GAP**, pembersihan **34 dokumen**, **sisa 0**.
