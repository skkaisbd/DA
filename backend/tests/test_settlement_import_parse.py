import csv, io, sys
sys.path.insert(0, '/app/backend')
from core.settlement_import import parse_settlement_report, guess_platform

# Shopee "Penghasilan Saya" style
shopee_rows = [
    ["No. Pesanan", "Tanggal Dana Dilepaskan", "Waktu Pesanan Dibuat", "Harga Asli Produk", "Total Diskon Produk",
     "Voucher Ditanggung Penjual", "Biaya Administrasi", "Biaya Layanan", "Biaya Komisi AMS", "Pengembalian Dana ke Pembeli",
     "Ongkos Kirim Dibayar Pembeli", "Total Penghasilan", "Persentase Biaya Administrasi"],
    ["2608A1", "2026-08-15", "2026-08-02 10:00", "1.000.000", "-50.000", "-20.000", "-45.000", "-15.000", "-10.000", "0", "12.000", "860.000", "4,5%"],
    ["2608A2", "2026-08-15", "2026-08-05 12:00", "2.000.000", "-100.000", "0", "-90.000", "-30.000", "0", "-200.000", "15.000", "1.580.000", "4,5%"],
]
buf = io.StringIO(); w = csv.writer(buf, delimiter=';'); w.writerows(shopee_rows)
raw = buf.getvalue().encode('utf-8-sig')
open('/app/samples/settlement_shopee_contoh.csv', 'wb').write(raw)
r = parse_settlement_report(raw, 'settlement_shopee_contoh.csv')
print('SHOPEE', guess_platform(r['headers']))
print(r['values']); print(r['mapping']); print(r['settlement_date'], r['period_from'], r['period_to']); print('unmapped', r['unmapped_numeric_columns'])
assert r['values']['gross_sales'] == 3000000 and r['values']['refunds'] == 200000 and r['values']['net_payout'] == 2440000
assert r['values']['seller_discount'] == 170000 and r['values']['platform_commission'] == 135000
assert r['values']['affiliate_commission'] == 10000 and r['values']['platform_service_fee'] == 45000
assert 'No. Pesanan' not in r['unmapped_numeric_columns'] and 'Persentase Biaya Administrasi' not in r['unmapped_numeric_columns']

# TikTok settlement statement (xlsx)
import openpyxl
wb = openpyxl.Workbook(); ws = wb.active
ws.append(["Order/adjustment ID", "Statement ID", "Order settled time", "Order created time", "Total settlement amount",
           "Total revenue", "Seller discount", "Refund subtotal after seller discounts", "Platform commission",
           "Affiliate commission", "Transaction fee", "Shipping cost", "Adjustment amount", "Ads fee"])
ws.append(["57800001", "STM-2026-08-16-01", "2026-08-16", "2026-08-03", 4300000, 5000000, -200000, 0, -250000, -100000, -150000, 0, 0, 0])
ws.append(["57800002", "STM-2026-08-16-01", "2026-08-16", "2026-08-09", 1620000, 2000000, -50000, -100000, -100000, 0, -60000, 0, -70000, 0])
b = io.BytesIO(); wb.save(b); raw2 = b.getvalue()
open('/app/samples/settlement_tiktok_contoh.xlsx', 'wb').write(raw2)
r2 = parse_settlement_report(raw2, 'settlement_tiktok_contoh.xlsx')
print('TIKTOK', guess_platform(r2['headers']))
print(r2['values']); print(r2['mapping']); print(r2['settlement_id'], r2['settlement_date'], r2['period_from'], r2['period_to']); print('unmapped', r2['unmapped_numeric_columns'])
assert r2['values']['gross_sales'] == 7000000 and r2['values']['net_payout'] == 5920000 and r2['values']['adjustments'] == -70000
assert r2['values']['affiliate_commission'] == 100000 and r2['values']['ads_deduction'] == 0
print('OK')
