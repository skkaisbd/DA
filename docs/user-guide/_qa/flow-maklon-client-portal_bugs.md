# QA / Bug Register — Flow Client Portal Maklon (`flow-maklon-client-portal`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS, 29 assertions).

## Ringkasan
- **Status:** CLEAN — **tidak ada bug** ditemukan. Happy-path 2-sisi (admin provisioning → klien
  login/ganti-pw → lihat order/upload → tracking/sample/invoice) berfungsi penuh.
- **Keamanan terbukti:** pemisahan token (`maklon-client` vs staf → `401`), isolasi antar-klien
  (`404`), gate `must_change_password` (`428`), brute-force lock, validasi upload (`415`/`400`).
- **DB:** PRISTINE setelah cleanup. Data SEED (3 klien, 6 PO, 6 sample) tidak disentuh; akun portal
  POC, sample fixture + revisi, `client_login_attempts`, dan file upload dibuang.

## Temuan
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| CP-01 | INFO | Portal klien memakai JWT **audience `maklon-client`** (12 jam) terpisah dari token staf. Verifikasi: token staf ditolak `401` di endpoint portal klien. | NOTED (by-design, aman) |
| CP-02 | INFO | Gate `must_change_password` menolak `428` untuk route non-`/auth` sampai password diganti. | NOTED (by-design) |
| CP-03 | INFO | Isolasi tenant: semua endpoint klien difilter `client_id` → akses order/sample/invoice klien lain `404`. | NOTED (by-design, aman) |
| CP-04 | INFO | Upload hanya gambar (jpeg/png/webp) ≤5MB, ≥100 byte, disimpan per-klien di `/app/uploads/client/<client_id>/`. Bukan penyimpanan objek terkelola (filesystem lokal). | NOTED |
| CP-05 | INFO | Aksi sample (approve/reject/revision) hanya untuk status `submitted`/`revision_requested`; selain itu `400`. | NOTED (by-design) |
| CP-06 | INFO | Sumber order = `dewi_maklon_pos` (SSOT); `dewi_maklon_orders` legacy deprecated dan diproyeksikan via `po_to_legacy_order`. | NOTED |

## Bukti Uji
- `python3 tests/flow_maklon_client_portal_test.py` → **=== CLIENT PORTAL MAKLON FLOW: ALL PASS (29 assertions) ===**
  lalu `CLEANUP: … SEED utuh`.
- Cakupan: provision (+guard duplikat 400), client login (+wrong-pw 401), must-change gate 428,
  change-password (+wrong-old 400), dashboard/orders/detail-timeline(8 tahap)/qc/samples, isolasi
  cross-client 404, upload 200 (+guard 415/400), sample revision→approve (+guard not-actionable 400),
  invoices/profile/badge, pemisahan token staf/klien 401.

## Catatan Peningkatan (opsional, non-blocking)
- Endpoint upload memakai filesystem lokal; untuk skala/replika pertimbangkan object storage terkelola.
- Endpoint `invoices/{id}/pdf` menghasilkan PDF on-the-fly; untuk volume tinggi bisa ditambah cache.
