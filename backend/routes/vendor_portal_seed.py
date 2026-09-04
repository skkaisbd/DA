"""
Vendor Portal Seed Data — Demo Setup
=====================================
Seed data untuk testing Vendor CMT Portal:
  - 1 vendor partner
  - 1 vendor user account
  - 2 vendor jobs (1 open, 1 in_progress)
  
Usage:
  python -c "from routes.vendor_portal_seed import seed_vendor_demo; import asyncio; asyncio.run(seed_vendor_demo())"
"""
import logging
import asyncio
from datetime import datetime, timezone, date
from database import get_db
from auth import hash_password
import uuid

def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)

async def seed_vendor_demo():
    """Seed 1 partner + 1 user + 2 jobs untuk testing vendor portal."""
    db = get_db()
    
    # Clear existing demo data (optional — comment jika ingin keep existing)
    # await db.vendor_partners.delete_many({'code': 'DEMO'})
    # await db.vendor_jobs.delete_many({'job_number': {'$regex': '^VJ-'}})
    # await db.users.delete_many({'email': 'vendor_demo@example.com'})
    
    logging.getLogger(__name__).info("🌱 Seeding Vendor Portal demo data...")
    
    # 1. Create demo partner
    partner_id = _uid()
    partner = {
        'id': partner_id,
        'name': 'CV. Jaya Konveksi (Demo)',
        'code': 'DEMO',
        'contact_name': 'Pak Budi',
        'contact_phone': '08123456789',
        'address': 'Jl. Garment No. 123, Sragen',
        'notes': 'Demo vendor untuk testing portal',
        'is_active': True,
        'created_at': _now(),
        'created_by': 'system_seed',
    }
    
    existing_partner = await db.vendor_partners.find_one({'code': 'DEMO'})
    if not existing_partner:
        await db.vendor_partners.insert_one(partner)
        logging.getLogger(__name__).info(f"   ✅ Partner: {partner['name']} (ID: {partner_id})")
    else:
        partner_id = existing_partner['id']
        logging.getLogger(__name__).info(f"   ⏭️  Partner sudah ada: {existing_partner['name']}")
    
    # 2. Create demo vendor user
    vendor_user = {
        'id': _uid(),
        'email': 'vendor_demo@example.com',
        'name': 'User Vendor Demo',
        'password': hash_password('Vendor@123'),  # password: Vendor@123
        'role': 'cmt_vendor',
        'cmt_vendor_id': partner_id,
        'is_active': True,
        'created_at': _now(),
        'created_by': 'system_seed',
    }
    
    existing_user = await db.users.find_one({'email': 'vendor_demo@example.com'})
    if not existing_user:
        await db.users.insert_one(vendor_user)
        logging.getLogger(__name__).info(f"   ✅ User: {vendor_user['email']} | Password: Vendor@123 | Role: cmt_vendor")
    else:
        logging.getLogger(__name__).info(f"   ⏭️  User sudah ada: {existing_user['email']}")
    
    # 3. Create 2 demo jobs
    jobs_data = [
        {
            'job_number': 'VJ-00001',
            'title': 'Jahit Kemeja Batik Pria - 500 pcs',
            'qty_target': 500,
            'qty_done': 0,
            'process': 'SEWING',
            'status': 'open',
            'due_date': '2026-06-15',
            'wo_number': 'WO-20260520-001',
            'notes': 'Kemeja batik lengan panjang, ukuran mix',
        },
        {
            'job_number': 'VJ-00002',
            'title': 'Finishing Blouse Wanita - 300 pcs',
            'qty_target': 300,
            'qty_done': 120,
            'process': 'FINISHING',
            'status': 'in_progress',
            'due_date': '2026-06-10',
            'wo_number': 'WO-20260518-002',
            'notes': 'Blouse casual, tinggal finishing works + QC',
        },
    ]
    
    for job_data in jobs_data:
        existing_job = await db.vendor_jobs.find_one({'job_number': job_data['job_number']})
        if not existing_job:
            doc = {
                'id': _uid(),
                'partner_id': partner_id,
                'partner_name': partner['name'],
                'wo_id': '',
                'created_at': _now(),
                'created_by': 'system_seed',
                **job_data,
            }
            await db.vendor_jobs.insert_one(doc)
            logging.getLogger(__name__).info(f"   ✅ Job: {doc['job_number']} - {doc['title']} ({doc['status']})")
        else:
            logging.getLogger(__name__).info(f"   ⏭️  Job sudah ada: {existing_job['job_number']}")
    
    # 4. Seed progress history untuk job VJ-00002 (in_progress)
    job_in_progress = await db.vendor_jobs.find_one({'job_number': 'VJ-00002', 'partner_id': partner_id})
    if job_in_progress:
        existing_reports_count = await db.vendor_progress_reports.count_documents({'job_id': job_in_progress['id']})
        if existing_reports_count == 0:
            progress_reports = [
                {
                    'id': _uid(),
                    'job_id': job_in_progress['id'],
                    'job_number': job_in_progress['job_number'],
                    'partner_id': partner_id,
                    'qty_done': 80,
                    'qty_reject': 5,
                    'qty_pass': 75,
                    'report_date': '2026-05-26',
                    'process_step': 'FINISHING',
                    'notes': 'Proses finishing hari 1',
                    'submitted_by': vendor_user['id'] if not existing_user else existing_user['id'],
                    'submitted_name': 'User Vendor Demo',
                    'submitted_at': _now(),
                    'source': 'vendor_self_report',
                },
                {
                    'id': _uid(),
                    'job_id': job_in_progress['id'],
                    'job_number': job_in_progress['job_number'],
                    'partner_id': partner_id,
                    'qty_done': 40,
                    'qty_reject': 2,
                    'qty_pass': 38,
                    'report_date': date.today().isoformat(),
                    'process_step': 'FINISHING',
                    'notes': 'Progress hari ini',
                    'submitted_by': vendor_user['id'] if not existing_user else existing_user['id'],
                    'submitted_name': 'User Vendor Demo',
                    'submitted_at': _now(),
                    'source': 'vendor_self_report',
                },
            ]
            
            for report in progress_reports:
                await db.vendor_progress_reports.insert_one(report)
            
            logging.getLogger(__name__).info(f"   ✅ Progress reports: {len(progress_reports)} entries seeded")
        else:
            logging.getLogger(__name__).info(f"   ⏭️  Progress reports sudah ada: {existing_reports_count} entries")
    
    logging.getLogger(__name__).info("\n✨ Vendor Portal demo data seeded successfully!")
    logging.getLogger(__name__).info("\n📋 Test Credentials:")
    logging.getLogger(__name__).info("   Email:    vendor_demo@example.com")
    logging.getLogger(__name__).info("   Password: Vendor@123")
    logging.getLogger(__name__).info("   Role:     cmt_vendor")
    logging.getLogger(__name__).info("\n🔗 Test Portal:")
    logging.getLogger(__name__).info("   Login, lalu pilih Portal Maklon → Vendor Portal")
    logging.getLogger(__name__).info("   atau langsung ke: https://da37-cmt-bridge.preview.emergentagent.com/#/erp/maklon/vendor-portal")
    

if __name__ == '__main__':
    asyncio.run(seed_vendor_demo())
