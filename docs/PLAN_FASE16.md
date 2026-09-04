# Rencana Development — Perbaikan Sistem HR (Absen + Cuti + Slip Gaji) — 2026-07-26

> Fokus: lanjutkan dari titik berhenti **Modul Absen Saya di dalam Portal Saya**. Backend core sudah lolos `verify_fase15.py` **26/0**; pekerjaan utama adalah **penegakan wajib selfie+geofence**, **approval izin**, **UI HR rekap**, lalu **BUG-4 (cuti)** dan **BUG-3 (slip gaji PDF)**. Setelah HR stabil → baru AUDIT-1..4.

## 1) Objectives

1. Membuktikan end-to-end UI untuk **Absen Saya** (di SPA Portal Saya) tanpa login ulang.
2. Menegakkan kebijakan user: **selfie + lokasi WAJIB** untuk clock-in/out (tolak bila belum konfigurasi kantor / di luar radius / tanpa selfie).
3. Mengubah **Izin** agar **wajib persetujuan atasan/HR** sebelum sesi izin “berjalan” (Istirahat tetap langsung).
4. Menyediakan UI HR baru: **Rekap Istirahat & Izin** (filter + export Excel).
5. Menyelesaikan **BUG-4 Cuti** (setup cuti error + master alasan/jenis cuti salah koleksi).
6. Menyelesaikan **BUG-3 Slip Gaji PDF** (tanda tangan, breakdown pokok+tunjangan, watermark).
7. Menjaga semua verifikasi repo tetap hijau: `verify_fase15.py`, `gate.sh`, `run_all_verifications.sh`, serta panggil `testing_agent_v3` per fase.

## 2) Implementation Steps (Phases)

### Phase 1 — Core Flow POC (isolasi) : Wajib Selfie/Geofence + Storage + Approval Izin

**User stories**
1. Sebagai karyawan, saya hanya bisa clock-in jika selfie diambil dan lokasi saya berada dalam radius kantor.
2. Sebagai karyawan, jika kantor belum dikonfigurasi, saya mendapat pesan jelas “minta HR set lokasi kantor dulu”.
3. Sebagai karyawan, saya bisa ajukan izin keluar dengan alasan, tapi statusnya **menunggu persetujuan**.
4. Sebagai HR/atasan, saya bisa approve/reject izin dan sistem mencatat siapa yang memutuskan.
5. Sebagai HR, saya bisa membuka bukti selfie (URL upload) untuk audit.

**Langkah**
1. (Web best-practice singkat) cek praktik penyimpanan gambar base64 → file + validasi geofence + response error yang aman.
2. Backend: perbaiki `rahaza_auto_attendance_selfie.py`:
   - Simpan selfie via `storage.put_object()` → URL `/api/uploads/...` (clock-in & clock-out).
   - Penegakan wajib: `photo_base64` wajib, `lat/lng` wajib, office lat/lng wajib, dan `out_of_range` → **409/400 ditolak** (bukan pending).
   - Perketat `_determine_approval`: geofence `not_verified` **tidak boleh** dianggap OK.
3. Backend: desain approval izin (tanpa koleksi baru; tetap di `rahaza_attendance_events.sessions[]`):
   - Tambah field sesi izin: `approval_status` (pending/approved/rejected), `approved_by`, `approved_by_name`, `approved_at`, `rejected_reason`.
   - Endpoint baru minimal:
     - `POST /api/rahaza/attendance/permit/request` (membuat sesi izin pending; belum hitung menit).
     - `POST /api/rahaza/attendance/permit/{session_id}/approve`
     - `POST /api/rahaza/attendance/permit/{session_id}/reject`
   - Aturan: izin hanya boleh “mulai keluar” setelah approved; atau kalau disetujui, set `out_at` saat approve.
4. POC script Python tunggal (mis. `scripts/verify_absen_policy_poc.py`):
   - Setup office-location (lat/lng/radius) via endpoint existing.
   - Clock-in fail jika: tanpa selfie / tanpa lat-lng / office belum set / out_of_range.
   - Clock-in success jika in_range + selfie tersimpan (url valid).
   - Request izin → pending; approve → status berubah; sesi izin baru bisa ditutup.
5. Jalankan: `python3 scripts/verify_fase15.py` + POC baru harus PASS.

### Phase 2 — V1 App Development (UI Absen Saya + Konfigurasi Kantor + Rekap HR)

**User stories**
1. Sebagai karyawan, saya bisa melakukan absen masuk/pulang dari modul **Absen Saya** di Portal Saya tanpa pindah halaman.
2. Sebagai karyawan, saya bisa mulai **Istirahat** dan kembali kerja, dan jam bersih otomatis terhitung.
3. Sebagai karyawan, saya bisa ajukan **Izin** dengan alasan dan melihat statusnya (pending/approved/rejected).
4. Sebagai HR, saya bisa mengatur lokasi kantor dengan tombol “Pakai lokasi saya sekarang”.
5. Sebagai HR, saya bisa melihat rekap sesi istirahat/izin per tanggal/karyawan/jenis dan export Excel.

**Langkah**
1. FE: perbaiki bug tab konfigurasi di `RahazaAutoAttendanceModule.jsx` (binding `office_lat/lng` salah) + tambah tombol “Pakai lokasi saya sekarang” (navigator.geolocation).
2. FE: `PortalSayaAbsen.jsx`:
   - Pastikan flow wajib selfie+geofence: blok tombol jika belum ada izin kamera/lokasi; tampilkan error backend yang jelas.
   - Untuk izin: gunakan endpoint request/approve flow (karyawan hanya request + end jika aktif).
   - Sediakan jalur uji tanpa kamera untuk QA (upload file → base64) karena testing agent tak bisa getUserMedia.
3. FE: buat modul HR baru “Rekap Istirahat & Izin” (gunakan endpoint `/api/rahaza/attendance/sessions` + endpoint export yang dibuat di backend).
4. Backend: endpoint export Excel untuk rekap sesi (minimal XLSX; PDF opsional belakangan).
5. Smoke test manual (tanpa testing agent): login hr & karyawan; cek modul portal-absen berjalan.
6. Jalankan `testing_agent_v3` + `scripts/gate.sh` untuk memastikan tidak ada regresi.

### Phase 3 — BUG-4: Cuti (setup cuti error + master alasan/jenis cuti)

**User stories**
1. Sebagai HR, saya bisa membuat jenis cuti dan alasan cuti tanpa error koleksi.
2. Sebagai karyawan, saya bisa mengajukan cuti menggunakan master jenis/alasan yang benar.
3. Sebagai HR, saya bisa menyetujui/menolak cuti dan status tercatat.
4. Sebagai HR, data cuti tampil konsisten di hub cuti (tanpa data hilang/duplikat).
5. Sebagai admin, migrasi/perbaikan data lama tidak merusak data demo.

**Langkah**
1. Repro BUG-4 dari UI + catat endpoint/collection yang salah.
2. Audit SSOT cuti: pastikan semua modul cuti mengarah ke koleksi kanonik (tentukan dari codebase; perbaiki wiring FE↔BE bila ada mismatch).
3. Implement fix + migrasi/backfill ringan bila diperlukan.
4. Tambah verifikasi skrip kecil `verify_leave_setup.py` untuk memastikan create/read jenis+alasan+request berjalan.
5. `testing_agent_v3` + `run_all_verifications.sh`.

### Phase 4 — BUG-3: Slip Gaji PDF (signature + breakdown + watermark)

**User stories**
1. Sebagai karyawan, saya dapat mengunduh slip gaji PDF yang rapi dan mudah dipahami.
2. Sebagai HR, saya bisa memastikan slip gaji menampilkan breakdown pokok+tunjangan+potongan.
3. Sebagai HR, slip gaji memiliki watermark “CV Dewi Aditya” dan area tanda tangan.
4. Sebagai HR, format PDF konsisten untuk semua karyawan (tidak error untuk data kosong).
5. Sebagai auditor, slip gaji menyertakan periode dan identitas karyawan dengan jelas.

**Langkah**
1. Temukan generator slip gaji saat ini (route/service) + buat baseline snapshot PDF.
2. Implement watermark + signature block (tanpa integrasi eksternal baru; gunakan library PDF existing di requirements).
3. Pastikan breakdown sesuai field payroll yang sudah ada.
4. Tambahkan verifikasi skrip `verify_payslip_pdf.py` (cek PDF terbentuk, ukuran >0, mengandung teks kunci).
5. `testing_agent_v3`.

### Phase 5 — AUDIT-1..4 (setelah HR stabil)

**User stories**
1. Sebagai maintainer, saya bisa melihat daftar collection duplikat/yatim beserta pembaca/penulisnya.
2. Sebagai maintainer, saya bisa melihat endpoint yang error/unused untuk dipangkas bertahap.
3. Sebagai maintainer, saya bisa menemukan form tanpa backend dan backend tanpa form.
4. Sebagai maintainer, saya bisa mengeksekusi perbaikan audit tanpa merusak modul HR.
5. Sebagai maintainer, semua perbaikan punya skrip verifikasi untuk mencegah regresi.

**Langkah**
1. Jalankan script audit yang sudah ada (`scripts/audit_duplication.py`, `audit_endpoint_sweep.py`, `tab_audit.py`) → rangkum temuan.
2. Prioritaskan temuan yang menyebabkan 500/UX broken.
3. Fix bertahap + verifikasi per batch.
4. `run_all_verifications.sh` + `gate.sh`.

## 3) Next Actions (immediate)

1. Tambah/ubah backend: simpan selfie ke storage + enforce wajib selfie+geofence + error messaging.
2. Implement backend approval izin (request/approve/reject) + update `attendance/sessions` agar hanya menghitung izin yang approved.
3. Buat POC script `verify_absen_policy_poc.py` dan pastikan PASS.
4. Fix FE `RahazaAutoAttendanceModule.jsx` binding lat/lng + tombol “Pakai lokasi saya sekarang”.
5. Buat UI HR “Rekap Istirahat & Izin” + export.
6. Jalankan `testing_agent_v3` (Phase 2 checkpoint).

## 4) Success Criteria

- **POC PASS**: script POC membuktikan (a) selfie & geofence wajib (reject jika tidak memenuhi), (b) file selfie tersimpan dan URL bisa diakses, (c) izin pending→approve/reject berfungsi.
- **UI Absen Saya**: tombol Absen/Istirahat/Izin berjalan di SPA Portal Saya, tanpa redirect `/absen` dan tanpa login ulang.
- **Approval Izin**: izin tidak mengurangi jam kerja sebelum disetujui; audit trail approver tercatat.
- **Konfigurasi kantor**: HR bisa set lat/lng/radius dengan UI yang benar + “pakai lokasi saya sekarang”.
- **Rekap HR**: modul rekap bisa filter + export Excel.
- **Regresi nol**: `verify_fase15.py`, `gate.sh`, `run_all_verifications.sh` tetap hijau; `testing_agent_v3` dijalankan dan tidak ada bug kritikal.
