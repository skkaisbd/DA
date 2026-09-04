# QA — Alur Penjualan Multi-Channel (Toko)

## Ringkasan
- **Dokumen:** [`toko/flow-toko-penjualan.md`](../toko/flow-toko-penjualan.md)
- **Skrip uji backend:** `tests/flow_toko_penjualan_test.py` — Akun -> Sales -> AR batch **ALL PASS** (1 invoice ter-generate).
- **Uji UI E2E (iteration_79):** Kelola Akun -> Input Sales -> Generate AR Invoice **PASS 100%**.
- **Modul tersentuh:** `marketing-accounts`, `marketing-sales`, `marketing-ar-bridge`.

## Temuan
| ID | Severity | Status | Ringkas |
|---|---|---|---|
| — | — | ✅ CLEAN | Tidak ada bug fungsional/testabilitas. Ketiga modul sudah punya `data-testid` lengkap di jalur utama (create-account-btn, acc-*; input-sales-btn, sd-*; date-from/to, generate-btn, invoice-item-{no}). |

### Observasi (bukan bug)
- `generate-ar-batch` bersifat idempotent per rentang tanggal + akun; menjalankan ulang untuk periode sama tidak menggandakan invoice.
