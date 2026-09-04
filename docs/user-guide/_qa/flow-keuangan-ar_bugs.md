# QA — Alur AR/Piutang (Keuangan)

## Ringkasan
- **Dokumen:** [`keuangan/flow-keuangan-ar.md`](../keuangan/flow-keuangan-ar.md)
- **Skrip uji backend:** `tests/flow_keuangan_ar_test.py` — Invoice -> Send(JE) -> Payment(JE) **ALL PASS** (status paid, balance 0).
- **Uji UI E2E (iteration_80):** Buat Invoice -> Kirim -> Lunas **PASS 100%**.
- **Modul tersentuh:** `fin-ar-invoices`.

## Temuan
| ID | Severity | Status | Ringkas |
|---|---|---|---|
| AR-01 | MEDIUM | ✅ FIXED | Input baris item invoice (deskripsi/qty/harga) tidak punya testid → sulit diisi otomasi. Ditambah `ar-item-desc-{i}`, `ar-item-qty-{i}`, `ar-item-price-{i}`, dan `ar-add-item-btn`. |
| AR-02 | LOW | ✅ FIXED | Select rekening pada modal pembayaran tidak punya testid. Ditambah `ar-pay-account`. |

### Observasi (bukan bug)
- `send` & `payment` auto-post ke GL (idempotent via source_ref). Jika invoice belum ter-post saat payment, backend memastikan invoice ter-post lebih dulu.
- Tombol **Lunas** (`ar-quick-pay-{id}`) = pelunasan penuh 1-klik; **Bayar** (`ar-pay-form-{id}`) membuka modal untuk pembayaran parsial.
