# QA / Bug Register — Flow KPI/OKR (`flow-sdm-kpi-okr`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS, 30 assertions).

## Ringkasan
- **Status:** CLEAN — **tidak ada bug** ditemukan. Happy-path KPI (periode→penilaian→review→publish) +
  OKR (objective/key-results/dashboard) berfungsi penuh.
- **Perhitungan terverifikasi:** KPI Final = Perform×0.6 + Attitude×0.2 + Absensi×0.2 → 94 (Grade A);
  OKR progress = rata-rata KR.
- **RBAC & guardrail terbukti:** non-HR/non-manajemen `403`; status machine periode, skor 1–5,
  calculate tanpa peserta, publish completion<80% warning.
- **DB:** PRISTINE setelah cleanup. SEED (1 periode, 10 soal, 40 karyawan) tidak disentuh.

## Temuan
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| KO-01 | INFO | KPI Final hanya dihitung bila Perform+Attitude+Absensi lengkap; jika tidak, `kpi_final=null` (peserta belum "final"). Publish memakai completion≥80% (dapat di-`force`). | NOTED (by-design) |
| KO-02 | INFO | Absensi otomatis 100 bila tidak ada absen tercatat pada hari kerja periode. | NOTED (by-design) |
| KO-03 | INFO | Attitude 360 anonim untuk `peer` & `staff_to_supervisor` (mendorong objektivitas). | NOTED (by-design) |
| KO-04 | INFO | Usul kenaikan gaji Grade A/B hanya dibuat bila ada profil payroll `base_rate>0`; idempoten per `kpi_period_id`. | NOTED (by-design) |
| KO-05 | INFO | `admin@garment.com` terhubung ke employee (via email/user_id) sehingga bisa mengisi submissions — guard uji memakai validasi skor 1–5 (400), bukan not-linked (409). | NOTED |
| KO-06 | INFO | Modul HRIS `HRPerformanceModule` (cycles/reviews) adalah fitur terpisah dari sistem `dewi/kpi` 360 yang didokumentasikan di sini. | NOTED |

## Bukti Uji
- `python3 tests/flow_sdm_kpi_okr_test.py` → **=== KPI/OKR FLOW: ALL PASS (30 assertions) ===**
  lalu `CLEANUP: … SEED utuh`.
- Cakupan: periode create/open (+guard nama 400/transisi 400), RBAC non-HR 403, bank soal seed +
  eval_type invalid 400, Perform items+bulk, submissions skor 1–5 400, calculate (KPI 94 grade A) +
  guard no-participant 400, results, publish completion<80 warning + force finalize, OKR
  objective+KR (progress 70→45→85, health) + dashboard + RBAC 403.

## Catatan Peningkatan (opsional, non-blocking)
- Cakupan `data-testid` pada modul KPI admin (`hr-kpi`) masih minim; bisa diperkaya untuk E2E UI granular.
