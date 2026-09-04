# ruff: noqa: F401
"""
operations_excel.py — Excel Export Endpoint
Endpoint: /api/export-excel

Refactored: Session #11.19 Phase 3.2.6 (split from operations_export.py 1277 LOC)
Supports: production-pos, vendor-shipments, buyer-shipments, invoices, accessories (deprecated), production-report
"""
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from database import get_db
from auth import require_auth
from datetime import datetime
from io import BytesIO
from utils.waktu import now_wib

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["operations-excel"])


@router.get("/export-excel")
async def export_excel(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    export_type = sp.get('type', '')
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        if export_type == 'production-pos':
            ws.title = "Production POs"
            headers = ['No', 'PO Number', 'Customer', 'Vendor', 'PO Date', 'Deadline', 'Status', 'Serial', 'SKU', 'Product', 'Size', 'Color', 'Qty', 'Selling Price', 'CMT Price']
            ws.append(headers)
            pos = await db.production_pos.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)
            row_num = 1
            for po in pos:
                items = await db.po_items.find({'po_id': po['id']}).to_list(500)
                for item in items:
                    ws.append([row_num, po.get('po_number'), po.get('customer_name'), po.get('vendor_name'),
                               str(po.get('po_date', ''))[:10], str(po.get('deadline', ''))[:10], po.get('status'),
                               item.get('serial_number', ''), item.get('sku', ''), item.get('product_name', ''),
                               item.get('size', ''), item.get('color', ''), item.get('qty', 0),
                               item.get('selling_price_snapshot', 0), item.get('cmt_price_snapshot', 0)])
                    row_num += 1
        elif export_type == 'vendor-shipments':
            ws.title = "Vendor Shipments"
            headers = ['No', 'Shipment Number', 'Vendor', 'Type', 'Date', 'Status', 'Inspection', 'SKU', 'Product', 'Size', 'Color', 'Qty Sent', 'Ordered Qty']
            ws.append(headers)
            ships = await db.vendor_shipments.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)
            row_num = 1
            for s in ships:
                items = await db.vendor_shipment_items.find({'shipment_id': s['id']}).to_list(500)
                for item in items:
                    ws.append([row_num, s.get('shipment_number'), s.get('vendor_name'), s.get('shipment_type', 'NORMAL'),
                               str(s.get('shipment_date', ''))[:10], s.get('status'), s.get('inspection_status', 'Pending'),
                               item.get('sku', ''), item.get('product_name', ''), item.get('size', ''), item.get('color', ''),
                               item.get('qty_sent', 0), item.get('ordered_qty', 0)])
                    row_num += 1
        elif export_type == 'buyer-shipments':
            ws.title = "Buyer Shipments"
            headers = ['No', 'Shipment Number', 'PO Number', 'Customer', 'Vendor', 'Dispatch #', 'Dispatch Date', 'SKU', 'Product', 'Serial', 'Size', 'Color', 'Ordered Qty', 'Shipped Qty']
            ws.append(headers)
            ships = await db.buyer_shipments.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)
            row_num = 1
            for s in ships:
                items = await db.buyer_shipment_items.find({'shipment_id': s['id']}).sort([('dispatch_seq', 1)]).to_list(500)
                for item in items:
                    ws.append([row_num, s.get('shipment_number'), s.get('po_number'), s.get('customer_name'),
                               s.get('vendor_name'), item.get('dispatch_seq', 1), str(item.get('dispatch_date', ''))[:10],
                               item.get('sku', ''), item.get('product_name', ''), item.get('serial_number', ''),
                               item.get('size', ''), item.get('color', ''), item.get('ordered_qty', 0), item.get('qty_shipped', 0)])
                    row_num += 1
        elif export_type == 'invoices':
            ws.title = "Invoices"
            headers = ['No', 'Invoice Number', 'Category', 'PO Number', 'Vendor/Customer', 'Total Amount', 'Total Paid', 'Remaining', 'Status', 'Created']
            ws.append(headers)
            # FORENSIC_12 GAP-01: legacy `invoices` dropped. Read from SSOT: rahaza_ar_invoices + rahaza_ap_invoices.
            ar_invs = await db.rahaza_ar_invoices.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)
            ap_invs = await db.rahaza_ap_invoices.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)
            invs = ar_invs + ap_invs
            for idx, inv in enumerate(invs, 1):
                ws.append([idx, inv.get('invoice_number'), inv.get('invoice_category', inv.get('type', '')),
                           inv.get('po_number', inv.get('order_number', '')), inv.get('vendor_or_customer_name', inv.get('customer_name', inv.get('vendor_name', ''))),
                           inv.get('total_amount', inv.get('total', 0)), inv.get('total_paid', inv.get('paid_amount', 0)),
                           inv.get('remaining_balance', inv.get('total_amount', inv.get('total', 0)) - inv.get('total_paid', inv.get('paid_amount', 0))),
                           inv.get('status'), str(inv.get('created_at', ''))[:10]])
        elif export_type == 'accessories':
            # DEPRECATED Sprint A.0 — accessories collection dropped, redirect to rahaza_materials
            logger.warning("[DEPRECATED-NOOP] export accessories — use /api/acc/items")
            ws.title = "Accessories (Deprecated)"
            ws.append(["DEPRECATED", "Use /api/acc/items endpoint with type='accessory'"])
            ws.append(["This export uses a dropped collection — no data available."])
        elif export_type == 'production-report':
            ws.title = "Production Report"
            headers = ['No', 'Date', 'PO Number', 'Serial', 'Product Code', 'Product Name', 'Size', 'SKU', 'Color',
                       'Output Qty', 'Selling Price', 'CMT Price', 'Total Sales', 'Total CMT', 'Vendor', 'Notes',
                       'Qty Produced', 'Qty Not Produced', 'Qty Shipped']
            ws.append(headers)
            pos = await db.production_pos.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)
            row_num = 1
            for po in pos:
                items = await db.po_items.find({'po_id': po['id']}).to_list(500)
                for item in items:
                    ji_list = await db.production_job_items.find({'po_item_id': item['id']}).to_list(500)
                    produced = sum(j.get('produced_qty', 0) for j in ji_list)
                    bi_list = await db.buyer_shipment_items.find({'po_item_id': item['id']}).to_list(500)
                    shipped = sum(b.get('qty_shipped', 0) for b in bi_list)
                    qty = item.get('qty', 0)
                    sp_price = item.get('selling_price_snapshot', 0)
                    cmt = item.get('cmt_price_snapshot', 0)
                    ws.append([row_num, str(po.get('po_date', po.get('created_at', '')))[:10],
                               po.get('po_number'), item.get('serial_number', ''), item.get('sku', ''),
                               item.get('product_name', ''), item.get('size', ''), item.get('sku', ''),
                               item.get('color', ''), qty, sp_price, cmt, qty * sp_price, qty * cmt,
                               po.get('vendor_name', ''), po.get('notes', ''),
                               produced, max(0, qty - produced), shipped])
                    row_num += 1
        else:
            return JSONResponse({'error': f'Unknown export type: {export_type}', 'available_types': [
                'production-pos', 'vendor-shipments', 'buyer-shipments', 'invoices', 'accessories', 'production-report']}, status_code=400)
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        filename = f"{export_type}_{now_wib().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f"attachment; filename={filename}"})
    except Exception as e:
        logger.error(f"Export error: {e}")
        raise HTTPException(500, f"Export failed: {str(e)}")
