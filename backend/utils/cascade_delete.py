from database import get_db

async def cascade_delete_po(po_id: str):
    db = get_db()
    # 1. Get PO items
    po_items = await db.po_items.find({'po_id': po_id}).to_list(10000)
    po_item_ids = [i['id'] for i in po_items]
    
    # 2. Delete vendor shipments & items
    vs_items = []
    if po_item_ids:
        vs_items = await db.vendor_shipment_items.find({'po_item_id': {'$in': po_item_ids}}).to_list(10000)
    vs_by_po = await db.vendor_shipment_items.find({'po_id': po_id}).to_list(10000)
    all_vs_items = vs_items + vs_by_po
    shipment_ids = list(set(i.get('shipment_id') for i in all_vs_items if i.get('shipment_id')))
    
    for ship_id in shipment_ids:
        # Delete inspections
        inspections = await db.vendor_material_inspections.find({'shipment_id': ship_id}).to_list(10000)
        for insp in inspections:
            await db.vendor_material_inspection_items.delete_many({'inspection_id': insp['id']})
        await db.vendor_material_inspections.delete_many({'shipment_id': ship_id})
        
        # Delete production jobs
        jobs = await db.production_jobs.find({'vendor_shipment_id': ship_id}).to_list(10000)
        for job in jobs:
            child_jobs = await db.production_jobs.find({'parent_job_id': job['id']}).to_list(10000)
            for cj in child_jobs:
                await db.production_job_items.delete_many({'job_id': cj['id']})
                await db.production_progress.delete_many({'job_id': cj['id']})
                await db.production_jobs.delete_one({'id': cj['id']})
            await db.production_job_items.delete_many({'job_id': job['id']})
            await db.production_progress.delete_many({'job_id': job['id']})
            await db.production_jobs.delete_one({'id': job['id']})
        
        await db.material_requests.delete_many({'original_shipment_id': ship_id})
        await db.vendor_shipment_items.delete_many({'shipment_id': ship_id})
        
        # Delete child shipments
        child_ships = await db.vendor_shipments.find({'parent_shipment_id': ship_id}).to_list(10000)
        for cs in child_ships:
            await db.vendor_shipment_items.delete_many({'shipment_id': cs['id']})
            await db.vendor_shipments.delete_one({'id': cs['id']})
        
        await db.vendor_shipments.delete_one({'id': ship_id})
    
    # 3. Delete buyer shipments
    buyer_ships = await db.buyer_shipments.find({'po_id': po_id}).to_list(10000)
    for bs in buyer_ships:
        await db.buyer_shipment_items.delete_many({'shipment_id': bs['id']})
        await db.buyer_shipments.delete_one({'id': bs['id']})
    
    # 4. Delete invoices
    invoices = await db.invoices.find({'po_id': po_id}).to_list(10000)
    for inv in invoices:
        await db.invoice_adjustments.delete_many({'invoice_id': inv['id']})
        await db.payments.delete_many({'invoice_id': inv['id']})
        await db.invoices.delete_one({'id': inv['id']})
    
    # 5. Delete work orders
    work_orders = await db.work_orders.find({'po_id': po_id}).to_list(10000)
    for wo in work_orders:
        await db.production_progress.delete_many({'work_order_id': wo['id']})
    await db.work_orders.delete_many({'po_id': po_id})
    
    # 6. Delete defect reports
    if po_item_ids:
        await db.material_defect_reports.delete_many({'po_item_id': {'$in': po_item_ids}})
    await db.material_defect_reports.delete_many({'po_id': po_id})
    
    # 7. Delete production returns
    returns = await db.production_returns.find({'reference_po_id': po_id}).to_list(10000)
    for ret in returns:
        await db.production_return_items.delete_many({'return_id': ret['id']})
    await db.production_returns.delete_many({'reference_po_id': po_id})
    
    # 8. Delete attachments
    await db.attachments.delete_many({'reference_id': po_id})
    
    # 9. Delete PO items then PO
    await db.po_items.delete_many({'po_id': po_id})
    await db.production_pos.delete_one({'id': po_id})
