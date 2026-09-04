"""
CV. Dewi Aditya — Demo Seed Endpoint (Phase 2, 3, 5)

Idempotent seeder untuk:
  - Phase 2: Cutting (requests+batches) + CMT (partners+jobs+deliveries+payments)
  - Phase 3: Maklon (clients+orders+samples+invoices+payments)
  - Phase 5: Toko Online enriched (products+orders+KOL+flashsales+returns+reviews)

Dipanggil via: POST /api/dewi/seed-demo-full  (superadmin/admin only)
"""
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException

from database import get_db
from auth import require_auth
from routes._maklon_adapter import legacy_orders_view as _lmo


router = APIRouter(prefix="/api/dewi", tags=["dewi-demo-seed"])


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _date_str(days_offset: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days_offset)).date().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 — CUTTING + CMT
# ─────────────────────────────────────────────────────────────────────────────

async def seed_phase2_cutting(db, user_name: str) -> dict:
    counts = {"requests": 0, "batches": 0}

    # Only seed if empty
    if await db.dewi_cutting_requests.count_documents({}) >= 3:
        return counts

    now = _now()
    req_seed = [
        {"id": _uid(), "request_code": "CUT-REQ-001", "product_model_name": "Rok Midi Rayon Twill", "product_category": "Rok",
         "qty_requested": 150, "colors": ["Hitam", "Navy"], "priority": "high", "status": "approved",
         "notes": "Untuk order KLN-002 deadline H+7", "requested_by": "Fitri Handayani",
         "approved_by": "Sari Dewi", "approved_at": now, "created_by": user_name,
         "created_at": now - timedelta(days=3), "updated_at": now - timedelta(days=2)},
        {"id": _uid(), "request_code": "CUT-REQ-002", "product_model_name": "Blouse Casual V-Neck", "product_category": "Blouse",
         "qty_requested": 200, "colors": ["Putih", "Abu-abu"], "priority": "normal", "status": "pending",
         "notes": "Produksi bulan ini", "requested_by": "Fitri Handayani",
         "created_by": user_name, "created_at": now - timedelta(days=1), "updated_at": now - timedelta(days=1)},
        {"id": _uid(), "request_code": "CUT-REQ-003", "product_model_name": "Dress Polos Casual", "product_category": "Dress",
         "qty_requested": 100, "colors": ["Navy"], "priority": "urgent", "status": "in_cutting",
         "notes": "Rush order resto brand A", "requested_by": "Winda Kusuma",
         "approved_by": "Sari Dewi", "approved_at": now - timedelta(days=2),
         "created_by": user_name, "created_at": now - timedelta(days=4), "updated_at": now - timedelta(hours=6)},
        {"id": _uid(), "request_code": "CUT-REQ-004", "product_model_name": "Celana Kulot Rayon", "product_category": "Celana",
         "qty_requested": 120, "colors": ["Hitam", "Navy"], "priority": "normal", "status": "cut_done",
         "notes": "Siap dipacking & assign ke CMT", "requested_by": "Fitri Handayani",
         "approved_by": "Sari Dewi", "approved_at": now - timedelta(days=7),
         "created_by": user_name, "created_at": now - timedelta(days=8), "updated_at": now - timedelta(days=1)},
        {"id": _uid(), "request_code": "CUT-REQ-005", "product_model_name": "Set Setelan Wanita", "product_category": "Set",
         "qty_requested": 80, "colors": ["Hitam", "Navy", "Putih"], "priority": "low", "status": "rejected",
         "rejected_reason": "Material rayon twill putih stok kurang, revisi warna dulu",
         "requested_by": "Winda Kusuma", "rejected_by": "Sari Dewi", "rejected_at": now - timedelta(days=5),
         "created_by": user_name, "created_at": now - timedelta(days=6), "updated_at": now - timedelta(days=5)},
    ]
    await db.dewi_cutting_requests.insert_many(req_seed)
    counts["requests"] = len(req_seed)

    # Cutting batches for approved/in_cutting/cut_done requests
    batch_seed = [
        {"id": _uid(), "batch_code": "CUT-BATCH-001",
         "request_id": req_seed[2]["id"], "request_code": "CUT-REQ-003",
         "product_model_name": "Dress Polos Casual", "product_category": "Dress",
         "total_cut_pcs": 100, "qty_per_color": [{"color": "Navy", "qty": 100}],
         "fabric_rolls_used": [{"roll_code": "ROLL-KAI-CTN-001-001", "meters_used": 180, "kg_used": 0}],
         "cutting_date": _date_str(-2), "operator_name": "Rina Wati", "spv_name": "Agus Sutrisno",
         "status": "in_cutting", "notes": "Operasi normal", "created_by": user_name,
         "created_at": now - timedelta(days=2), "updated_at": now - timedelta(hours=6)},
        {"id": _uid(), "batch_code": "CUT-BATCH-002",
         "request_id": req_seed[3]["id"], "request_code": "CUT-REQ-004",
         "product_model_name": "Celana Kulot Rayon", "product_category": "Celana",
         "total_cut_pcs": 120, "qty_per_color": [{"color": "Hitam", "qty": 70}, {"color": "Navy", "qty": 50}],
         "fabric_rolls_used": [{"roll_code": "ROLL-KAI-RAY-001-002", "meters_used": 190, "kg_used": 0}],
         "cutting_date": _date_str(-1), "operator_name": "Budi Hartono", "spv_name": "Agus Sutrisno",
         "status": "cut_done", "notes": "Siap assign ke CMT", "created_by": user_name,
         "created_at": now - timedelta(days=1), "updated_at": now - timedelta(hours=12)},
        {"id": _uid(), "batch_code": "CUT-BATCH-003",
         "request_id": req_seed[0]["id"], "request_code": "CUT-REQ-001",
         "product_model_name": "Rok Midi Rayon Twill", "product_category": "Rok",
         "total_cut_pcs": 150, "qty_per_color": [{"color": "Hitam", "qty": 90}, {"color": "Navy", "qty": 60}],
         "fabric_rolls_used": [{"roll_code": "ROLL-KAI-RAY-001-001", "meters_used": 225, "kg_used": 0}],
         "cutting_date": _date_str(-3), "operator_name": "Rina Wati", "spv_name": "Agus Sutrisno",
         "status": "assigned_to_cmt", "notes": "Sudah dikirim ke CMT Pak Heru",
         "created_by": user_name, "created_at": now - timedelta(days=3), "updated_at": now - timedelta(days=1)},
    ]
    await db.dewi_cutting_batches.insert_many(batch_seed)
    counts["batches"] = len(batch_seed)
    return counts


async def seed_phase2_cmt(db, user_name: str) -> dict:
    counts = {"partners": 0, "jobs": 0, "deliveries": 0, "payments": 0}

    if await db.dewi_cmt_partners.count_documents({}) >= 3:
        return counts

    now = _now()
    partner_seed = [
        {"id": _uid(), "code": "CMT-001", "name": "CMT Pak Heru", "owner_name": "Heru Pranoto",
         "phone": "081234567001", "address": "Jl. Mawar No. 12, Sragen", "city": "Sragen",
         "specialization": ["Jahit rok", "Jahit celana"], "rate_per_pcs": 8500,
         "capacity_per_week": 500, "bank_name": "BCA", "bank_account": "1234567890",
         "bank_holder": "Heru Pranoto", "rating": 4.5, "status": "active",
         "penalty_per_day": 1000, "notes": "Partner utama sejak 2023",
         "created_by": user_name, "created_at": now - timedelta(days=180), "updated_at": now},
        {"id": _uid(), "code": "CMT-002", "name": "CMT Bu Warsini", "owner_name": "Warsini",
         "phone": "081234567002", "address": "Jl. Melati No. 7, Sragen", "city": "Sragen",
         "specialization": ["Jahit blouse", "Jahit dress"], "rate_per_pcs": 9000,
         "capacity_per_week": 400, "bank_name": "Mandiri", "bank_account": "2345678901",
         "bank_holder": "Warsini", "rating": 4.7, "status": "active",
         "penalty_per_day": 1500, "notes": "Kualitas detail bagus",
         "created_by": user_name, "created_at": now - timedelta(days=150), "updated_at": now},
        {"id": _uid(), "code": "CMT-003", "name": "CMT Mas Joko", "owner_name": "Joko Santoso",
         "phone": "081234567003", "address": "Jl. Kenanga No. 3, Karanganyar", "city": "Karanganyar",
         "specialization": ["Jahit set", "Jahit baju anak"], "rate_per_pcs": 7500,
         "capacity_per_week": 600, "bank_name": "BRI", "bank_account": "3456789012",
         "bank_holder": "Joko Santoso", "rating": 4.2, "status": "active",
         "penalty_per_day": 1000, "notes": "Harga kompetitif",
         "created_by": user_name, "created_at": now - timedelta(days=120), "updated_at": now},
        {"id": _uid(), "code": "CMT-004", "name": "CMT Bu Sri", "owner_name": "Sri Mulyani",
         "phone": "081234567004", "address": "Jl. Anggrek No. 5, Sragen", "city": "Sragen",
         "specialization": ["Jahit hijab", "Finishing"], "rate_per_pcs": 5500,
         "capacity_per_week": 800, "bank_name": "BCA", "bank_account": "4567890123",
         "bank_holder": "Sri Mulyani", "rating": 4.0, "status": "inactive",
         "penalty_per_day": 500, "notes": "Sementara libur (cuti melahirkan)",
         "created_by": user_name, "created_at": now - timedelta(days=100), "updated_at": now - timedelta(days=10)},
    ]
    await db.dewi_cmt_partners.insert_many(partner_seed)
    counts["partners"] = len(partner_seed)

    # Get some cutting batch references
    batch = await db.dewi_cutting_batches.find_one({"status": "assigned_to_cmt"})
    batch_id = batch["id"] if batch else ""
    batch_code = batch["batch_code"] if batch else ""

    job_seed = [
        {"id": _uid(), "job_code": "CMT-JOB-001",
         "cmt_partner_id": partner_seed[0]["id"], "cmt_name": "CMT Pak Heru",
         "product_model_name": "Rok Midi Rayon Twill", "product_category": "Rok",
         "qty_total": 150, "qty_per_color": [{"color": "Hitam", "qty": 90}, {"color": "Navy", "qty": 60}],
         "sewing_rate_per_pcs": 8500, "penalty_per_day": 1000,
         "cutting_batch_id": batch_id, "batch_code": batch_code,
         "assign_date": _date_str(-3), "deadline_date": _date_str(4),
         "status": "in_progress", "qty_received": 0, "qc_pass_qty": 0, "qc_reject_qty": 0,
         "created_by": user_name, "created_at": now - timedelta(days=3), "updated_at": now - timedelta(days=1)},
        {"id": _uid(), "job_code": "CMT-JOB-002",
         "cmt_partner_id": partner_seed[1]["id"], "cmt_name": "CMT Bu Warsini",
         "product_model_name": "Blouse Casual V-Neck", "product_category": "Blouse",
         "qty_total": 200, "qty_per_color": [{"color": "Putih", "qty": 120}, {"color": "Abu-abu", "qty": 80}],
         "sewing_rate_per_pcs": 9000, "penalty_per_day": 1500,
         "assign_date": _date_str(-10), "deadline_date": _date_str(-2),
         "status": "completed", "qty_received": 200, "qc_pass_qty": 195, "qc_reject_qty": 5,
         "delivery_date_actual": _date_str(-3),
         "created_by": user_name, "created_at": now - timedelta(days=10), "updated_at": now - timedelta(days=2)},
        {"id": _uid(), "job_code": "CMT-JOB-003",
         "cmt_partner_id": partner_seed[2]["id"], "cmt_name": "CMT Mas Joko",
         "product_model_name": "Set Setelan Wanita", "product_category": "Set",
         "qty_total": 100, "qty_per_color": [{"color": "Hitam", "qty": 50}, {"color": "Navy", "qty": 50}],
         "sewing_rate_per_pcs": 12000, "penalty_per_day": 1000,
         "assign_date": _date_str(-5), "deadline_date": _date_str(5),
         "status": "assigned", "qty_received": 0, "qc_pass_qty": 0, "qc_reject_qty": 0,
         "created_by": user_name, "created_at": now - timedelta(days=5), "updated_at": now - timedelta(days=5)},
        {"id": _uid(), "job_code": "CMT-JOB-004",
         "cmt_partner_id": partner_seed[0]["id"], "cmt_name": "CMT Pak Heru",
         "product_model_name": "Celana Kulot Rayon", "product_category": "Celana",
         "qty_total": 80, "qty_per_color": [{"color": "Hitam", "qty": 80}],
         "sewing_rate_per_pcs": 8500, "penalty_per_day": 1000,
         "assign_date": _date_str(-20), "deadline_date": _date_str(-10),
         "status": "completed", "qty_received": 80, "qc_pass_qty": 80, "qc_reject_qty": 0,
         "delivery_date_actual": _date_str(-11),
         "created_by": user_name, "created_at": now - timedelta(days=20), "updated_at": now - timedelta(days=10)},
    ]
    await db.dewi_cmt_jobs.insert_many(job_seed)
    counts["jobs"] = len(job_seed)

    # Deliveries (for completed jobs)
    delivery_seed = [
        {"id": _uid(), "delivery_code": "CMT-DLV-001", "job_id": job_seed[1]["id"],
         "job_code": "CMT-JOB-002", "cmt_partner_id": partner_seed[1]["id"], "cmt_name": "CMT Bu Warsini",
         "qty_delivered": 200, "qty_per_color": [{"color": "Putih", "qty": 120}, {"color": "Abu-abu", "qty": 80}],
         "delivery_date": _date_str(-3), "received_date": _date_str(-3),
         "qty_received": 200, "qc_pass_qty": 195, "qc_reject_qty": 5,
         "status": "received", "notes": "5 pcs jahitan kurang rapi",
         "created_by": user_name, "created_at": now - timedelta(days=3), "updated_at": now - timedelta(days=3)},
        {"id": _uid(), "delivery_code": "CMT-DLV-002", "job_id": job_seed[3]["id"],
         "job_code": "CMT-JOB-004", "cmt_partner_id": partner_seed[0]["id"], "cmt_name": "CMT Pak Heru",
         "qty_delivered": 80, "qty_per_color": [{"color": "Hitam", "qty": 80}],
         "delivery_date": _date_str(-11), "received_date": _date_str(-11),
         "qty_received": 80, "qc_pass_qty": 80, "qc_reject_qty": 0,
         "status": "received", "notes": "Tepat waktu, kualitas bagus",
         "created_by": user_name, "created_at": now - timedelta(days=11), "updated_at": now - timedelta(days=11)},
    ]
    await db.dewi_cmt_deliveries.insert_many(delivery_seed)
    counts["deliveries"] = len(delivery_seed)

    # Payments (for completed jobs)
    payment_seed = [
        {"id": _uid(), "payment_code": "CMT-PAY-001",
         "cmt_partner_id": partner_seed[1]["id"], "cmt_name": "CMT Bu Warsini",
         "job_ids": [job_seed[1]["id"]], "period_from": _date_str(-15), "period_to": _date_str(-1),
         "subtotal": 195 * 9000, "total_penalty": 0, "total_pcs": 195,
         "total_amount": 195 * 9000, "payment_method": "transfer",
         "status": "paid", "payment_date": _date_str(-1),
         "notes": "Lunas batch Blouse Casual V-Neck",
         "created_by": user_name, "created_at": now - timedelta(days=2), "updated_at": now - timedelta(days=1)},
        {"id": _uid(), "payment_code": "CMT-PAY-002",
         "cmt_partner_id": partner_seed[0]["id"], "cmt_name": "CMT Pak Heru",
         "job_ids": [job_seed[3]["id"]], "period_from": _date_str(-20), "period_to": _date_str(-10),
         "subtotal": 80 * 8500, "total_penalty": 0, "total_pcs": 80,
         "total_amount": 80 * 8500, "payment_method": "transfer",
         "status": "approved", "notes": "Menunggu transfer dari Finance",
         "created_by": user_name, "created_at": now - timedelta(days=9), "updated_at": now - timedelta(days=8)},
    ]
    await db.dewi_cmt_payments.insert_many(payment_seed)
    counts["payments"] = len(payment_seed)

    return counts


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 — MAKLON
# ─────────────────────────────────────────────────────────────────────────────

async def seed_phase3_maklon(db, user_name: str) -> dict:
    counts = {"clients": 0, "orders": 0, "samples": 0, "invoices": 0, "payments": 0}

    if await db.dewi_maklon_clients.count_documents({}) >= 3:
        return counts

    now = _now()
    client_seed = [
        {"id": _uid(), "code": "CLT001", "name": "Brand Aisha Fashion",
         "pic_name": "Ibu Aisha Rahmawati", "pic_phone": "081234500001",
         "pic_email": "aisha@brandaisha.id", "address": "Jl. Sudirman No. 45", "city": "Jakarta",
         "contract_type": "per_order", "standard_rate_per_pcs": 75000,
         "payment_terms": "net_30", "product_specialization": ["Dress", "Gamis", "Tunik"],
         "quality_standard": "premium", "status": "active", "rating": 4.8,
         "notes": "Klien tetap sejak 2024, volume stabil",
         "created_at": now - timedelta(days=200), "updated_at": now, "created_by": user_name},
        {"id": _uid(), "code": "CLT002", "name": "Sahara Hijab House",
         "pic_name": "Pak Hendra Permana", "pic_phone": "081234500002",
         "pic_email": "hendra@saharahijab.com", "address": "Jl. Ahmad Yani No. 22", "city": "Surabaya",
         "contract_type": "monthly_retainer", "standard_rate_per_pcs": 45000,
         "payment_terms": "net_14", "product_specialization": ["Hijab", "Ciput", "Inner"],
         "quality_standard": "standard", "status": "active", "rating": 4.5,
         "notes": "Retainer Rp 50jt/bulan untuk 1000 pcs",
         "created_at": now - timedelta(days=150), "updated_at": now, "created_by": user_name},
        {"id": _uid(), "code": "CLT003", "name": "Zelly Kids Collection",
         "pic_name": "Ibu Zelly Anggraini", "pic_phone": "081234500003",
         "pic_email": "zelly@zellykids.id", "address": "Jl. Dipatiukur No. 10", "city": "Bandung",
         "contract_type": "per_order", "standard_rate_per_pcs": 55000,
         "payment_terms": "net_30", "product_specialization": ["Baju Anak", "Set Anak", "Dress Anak"],
         "quality_standard": "premium", "status": "active", "rating": 4.7,
         "notes": "Spesialis baju anak motif custom",
         "created_at": now - timedelta(days=90), "updated_at": now, "created_by": user_name},
        {"id": _uid(), "code": "CLT004", "name": "Urban Style Jakarta",
         "pic_name": "Mas Raka Pratama", "pic_phone": "081234500004",
         "pic_email": "raka@urbanstyle.co", "address": "Jl. Thamrin No. 88", "city": "Jakarta",
         "contract_type": "per_order", "standard_rate_per_pcs": 85000,
         "payment_terms": "net_14", "product_specialization": ["Blouse", "Rok Office", "Celana Kerja"],
         "quality_standard": "premium", "status": "active", "rating": 4.3,
         "notes": "Brand office-wear wanita, kualitas ketat",
         "created_at": now - timedelta(days=60), "updated_at": now, "created_by": user_name},
        {"id": _uid(), "code": "CLT005", "name": "Batik Nusantara Pratama",
         "pic_name": "Pak Bambang Sutopo", "pic_phone": "081234500005",
         "pic_email": "bambang@batiknusantara.id", "address": "Jl. Slamet Riyadi No. 66", "city": "Solo",
         "contract_type": "per_order", "standard_rate_per_pcs": 95000,
         "payment_terms": "net_60", "product_specialization": ["Dress Batik", "Blouse Batik", "Tunik Batik"],
         "quality_standard": "luxury", "status": "active", "rating": 4.6,
         "notes": "Butuh motif batik premium, batch kecil",
         "created_at": now - timedelta(days=45), "updated_at": now, "created_by": user_name},
    ]
    await db.dewi_maklon_clients.insert_many(client_seed)
    counts["clients"] = len(client_seed)

    # Orders
    order_seed = []
    order_specs = [
        # (client_idx, product_name, category, qty, price, status, progress, days_ago)
        (0, "Dress Aisha Premium", "Dress", 200, 85000, "completed", 100, 20),
        (0, "Gamis Aisha Syari", "Gamis", 150, 95000, "invoiced", 100, 35),
        (0, "Tunik Lebaran 2026", "Tunik", 300, 70000, "sewing", 65, 10),
        (1, "Hijab Segi4 Premium", "Hijab", 500, 35000, "packing", 90, 15),
        (1, "Inner Ciput Basic", "Ciput", 1000, 12000, "confirmed", 10, 2),
        (2, "Set Baju Anak Motif", "Anak", 120, 65000, "sewing", 55, 8),
        (2, "Dress Anak Batik", "Dress", 80, 75000, "qc", 85, 12),
        (3, "Blouse Office Eleganza", "Blouse", 180, 90000, "cutting", 30, 5),
        (3, "Rok Kerja Premium", "Rok", 220, 80000, "material_ready", 20, 3),
        (4, "Dress Batik Parang", "Dress", 100, 110000, "draft", 0, 1),
    ]
    for i, (c_idx, pname, pcat, qty, price, status, prog, days) in enumerate(order_specs, 1):
        client = client_seed[c_idx]
        order_seed.append({
            "id": _uid(),
            "order_code": f"MKL-2026-{str(i).zfill(3)}",
            "client_id": client["id"], "client_name": client["name"],
            "product_name": pname, "product_category": pcat,
            "qty_ordered": qty, "qty_per_size": [{"size": "M", "qty": qty // 3}, {"size": "L", "qty": qty // 3}, {"size": "XL", "qty": qty - 2 * (qty // 3)}],
            "colors": ["Hitam", "Navy"] if c_idx != 4 else ["Coklat Parang", "Biru Parang"],
            "price_per_pcs": price, "total_value": price * qty,
            "order_date": _date_str(-days - 2), "deadline_date": _date_str(30 - days),
            "status": status, "progress_percentage": prog,
            "fabric_provided_by": "cv_dewi" if status != "draft" else "client",
            "material_notes": "", "wo_ids": [], "cmt_job_ids": [],
            "delivery_method": "delivery", "delivery_address": client["address"],
            "revision_count": 0, "notes": "",
            "created_at": now - timedelta(days=days + 2), "updated_at": now - timedelta(days=1),
            "created_by": user_name, "confirmed_by": None if status == "draft" else user_name,
        })
    # P1.B SSOT: insert legacy-shape orders via _lmo adapter (translated to dewi_maklon_pos shape)
    for legacy_order in order_seed:
        await _lmo(db).insert_one(legacy_order)
    counts["orders"] = len(order_seed)

    # Samples (for orders in-progress or new)
    sample_seed = [
        {"id": _uid(), "sample_code": "SMPL-MKL-001",
         "client_id": client_seed[0]["id"], "client_name": client_seed[0]["name"],
         "order_id": order_seed[2]["id"], "order_code": order_seed[2]["order_code"],
         "product_name": "Tunik Lebaran 2026", "qty": 2, "size": "M",
         "status": "approved", "revision_count": 1,
         "sample_photos": [], "feedback_notes": "Approved dengan revisi detail kancing",
         "submitted_at": now - timedelta(days=7), "approved_at": now - timedelta(days=5),
         "created_at": now - timedelta(days=8), "updated_at": now - timedelta(days=5),
         "created_by": user_name},
        {"id": _uid(), "sample_code": "SMPL-MKL-002",
         "client_id": client_seed[2]["id"], "client_name": client_seed[2]["name"],
         "order_id": order_seed[5]["id"], "order_code": order_seed[5]["order_code"],
         "product_name": "Set Baju Anak Motif", "qty": 3, "size": "S",
         "status": "in_review", "revision_count": 0,
         "sample_photos": [], "feedback_notes": "Menunggu review klien",
         "submitted_at": now - timedelta(days=2),
         "created_at": now - timedelta(days=3), "updated_at": now - timedelta(days=2),
         "created_by": user_name},
        {"id": _uid(), "sample_code": "SMPL-MKL-003",
         "client_id": client_seed[3]["id"], "client_name": client_seed[3]["name"],
         "order_id": order_seed[7]["id"], "order_code": order_seed[7]["order_code"],
         "product_name": "Blouse Office Eleganza", "qty": 2, "size": "M",
         "status": "revision_requested", "revision_count": 1,
         "sample_photos": [], "feedback_notes": "Lengan terlalu longgar, revisi pola -1cm",
         "submitted_at": now - timedelta(days=4),
         "created_at": now - timedelta(days=5), "updated_at": now - timedelta(days=3),
         "created_by": user_name},
        {"id": _uid(), "sample_code": "SMPL-MKL-004",
         "client_id": client_seed[4]["id"], "client_name": client_seed[4]["name"],
         "order_id": order_seed[9]["id"], "order_code": order_seed[9]["order_code"],
         "product_name": "Dress Batik Parang", "qty": 1, "size": "M",
         "status": "draft", "revision_count": 0,
         "sample_photos": [], "feedback_notes": "Persiapan pembuatan sample",
         "created_at": now - timedelta(days=1), "updated_at": now - timedelta(days=1),
         "created_by": user_name},
    ]
    await db.dewi_maklon_samples.insert_many(sample_seed)
    counts["samples"] = len(sample_seed)

    # Invoices (for completed/invoiced orders)
    invoice_seed = []
    inv_targets = [(o, i) for i, o in enumerate(order_seed) if o["status"] in ("completed", "invoiced", "packing")]
    for idx, (order, _) in enumerate(inv_targets[:3], 1):
        subtotal = order["total_value"]
        ppn = subtotal * 0.11
        total = subtotal + ppn
        invoice_seed.append({
            "id": _uid(),
            "invoice_code": f"INV-MKL-2026-{str(idx).zfill(3)}",
            "invoice_number": f"INV-MKL-2026-{str(idx).zfill(3)}",
            "order_id": order["id"], "order_code": order["order_code"],
            "client_id": order["client_id"], "client_name": order["client_name"],
            "line_items": [{"description": order["product_name"], "qty": order["qty_ordered"],
                            "price": order["price_per_pcs"], "subtotal": subtotal}],
            "subtotal": subtotal, "ppn": ppn, "discount": 0, "total_amount": total,
            "amount_paid": total if idx == 2 else 0,
            "status": "paid" if idx == 2 else ("sent" if idx == 1 else "draft"),
            "invoice_date": _date_str(-30 + idx * 5),
            "due_date": _date_str(-30 + idx * 5 + 30),
            "paid_date": _date_str(-5) if idx == 2 else None,
            "notes": "Pembayaran sesuai termin",
            "created_at": now - timedelta(days=30 - idx * 5),
            "updated_at": now - timedelta(days=5 if idx == 2 else 10),
            "created_by": user_name,
        })
    if invoice_seed:
        await db.dewi_maklon_invoices.insert_many(invoice_seed)
    counts["invoices"] = len(invoice_seed)

    # Payments (for paid invoice)
    paid_inv = next((inv for inv in invoice_seed if inv["status"] == "paid"), None)
    if paid_inv:
        payment_seed = [{
            "id": _uid(),
            "payment_code": "PAY-MKL-2026-001",
            "invoice_id": paid_inv["id"], "invoice_code": paid_inv["invoice_code"],
            "client_id": paid_inv["client_id"], "client_name": paid_inv["client_name"],
            "amount": paid_inv["total_amount"],
            "payment_method": "transfer",
            "payment_date": _date_str(-5),
            "reference_number": "TRF-20260426-BCA",
            "status": "verified",
            "notes": "Lunas via BCA",
            "created_at": now - timedelta(days=5), "updated_at": now - timedelta(days=5),
            "created_by": user_name,
        }]
        await db.dewi_maklon_payments.insert_many(payment_seed)
        counts["payments"] = 1

    return counts


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5 — TOKO ONLINE (enriched)
# ─────────────────────────────────────────────────────────────────────────────

async def seed_phase5_toko(db, user_name: str) -> dict:
    """Phase 5 Toko Online seeder.

    ⚠️ DEPRECATED (P1.D Phase C cutover, 2026-05-23):
       All toko legacy endpoints (/api/dewi/toko/products|orders|channels|returns|reviews)
       have been REMOVED. Only `flashsales` + `pack-batches` are preserved.
       Marketing SSOT endpoints (/api/marketing/*) are the source of truth.

       The legacy `dewi_toko_*` collections (products, orders, returns, reviews,
       channels, channel_syncs) have been DROPPED. Writing demo data here would
       only resurrect dropped collections without any UI to consume them.

       To seed marketing-domain demo data instead, use:
         /api/marketing/catalogs    (for products)
         /api/marketing/orders      (for orders)
         /api/marketing/reviews     (for reviews)

       This seeder is intentionally a NO-OP to keep the API stable.
       Re-enable by writing a separate `seed_phase5_marketing(db)` helper.
    """
    return {
        "products": 0, "orders": 0, "flashsales": 0,
        "creators": 0, "deals": 0, "samples": 0,
        "returns": 0, "reviews": 0,
        "_status": "deprecated_no_op",
        "_note": "Phase C cutover removed legacy /api/dewi/toko/* endpoints. Use /api/marketing/* SSOT.",
    }


async def _seed_phase5_toko_LEGACY(db, user_name: str) -> dict:
    """LEGACY implementation kept for reference. Renamed to avoid being invoked."""
    counts = {"products": 0, "orders": 0, "flashsales": 0,
              "creators": 0, "deals": 0, "samples": 0,
              "returns": 0, "reviews": 0}

    # Seed only if existing data tipis
    current_products = await db.dewi_toko_products.count_documents({})
    current_orders = await db.dewi_toko_orders.count_documents({})

    now = _now()

    # --- PRODUCTS (enrich if less than 8) ---
    if current_products < 8:
        product_specs = [
            ("DEWI-ROK-001", "Rok Midi Rayon Twill Premium", "Rok", 125000, 75000, 45, "active"),
            ("DEWI-BLS-002", "Blouse Casual V-Neck", "Blouse", 145000, 90000, 60, "active"),
            ("DEWI-DRS-003", "Dress Polos Casual Wanita", "Dress", 165000, 105000, 38, "active"),
            ("DEWI-CLN-004", "Celana Kulot Rayon", "Celana", 135000, 82000, 52, "active"),
            ("DEWI-SET-005", "Set Setelan Wanita Formal", "Set", 285000, 180000, 22, "active"),
            ("DEWI-KDS-006", "Baju Anak Motif Lucu 1-7Th", "Anak", 95000, 60000, 70, "active"),
            ("DEWI-HJB-007", "Hijab Segi4 Voal Premium", "Hijab", 55000, 32000, 120, "active"),
            ("DEWI-GMS-008", "Gamis Syari Premium", "Gamis", 225000, 145000, 28, "active"),
            ("DEWI-TNK-009", "Tunik Lebaran Elegant", "Tunik", 175000, 110000, 40, "active"),
            ("DEWI-BTK-010", "Dress Batik Parang Premium", "Dress", 265000, 165000, 15, "draft"),
        ]
        products_to_insert = []
        # Batch prefetch existing SKUs
        target_skus = [spec[0] for spec in product_specs]
        existing_skus = set()
        async for d in db.dewi_toko_products.find(
            {"sku_code": {"$in": target_skus}}, {"_id": 0, "sku_code": 1}
        ):
            existing_skus.add(d["sku_code"])
        for sku, name, cat, price, cost, stock, status in product_specs:
            if sku in existing_skus:
                continue
            products_to_insert.append({
                "id": _uid(), "sku_code": sku, "name": name, "description": f"{name} — produk unggulan CV. Dewi Aditya",
                "category": cat, "base_price": price, "cost_price": cost,
                "channel_prices": [
                    {"channel": "shopee", "price": price, "active": True},
                    {"channel": "tokopedia", "price": price + 5000, "active": True},
                    {"channel": "tiktok_shop", "price": price - 5000, "active": True},
                    {"channel": "website", "price": price, "active": True},
                ],
                "variants": [
                    {"id": _uid(), "name": "Hitam M", "size": "M", "color": "Hitam", "sku_suffix": "-HTM-M", "stock": stock // 3},
                    {"id": _uid(), "name": "Navy L", "size": "L", "color": "Navy", "sku_suffix": "-NVY-L", "stock": stock // 3},
                    {"id": _uid(), "name": "Putih M", "size": "M", "color": "Putih", "sku_suffix": "-PTH-M", "stock": stock - 2 * (stock // 3)},
                ],
                "photos": [], "stock_total": stock, "stock_reserved": 0, "sales_count_total": 0,
                "weight_grams": 300, "status": status, "tags": [cat.lower(), "dewi-aditya"],
                "created_at": now - timedelta(days=30), "updated_at": now - timedelta(days=1),
                "created_by": user_name,
            })
        if products_to_insert:
            await db.dewi_toko_products.insert_many(products_to_insert)
            counts["products"] = len(products_to_insert)

    # --- ORDERS (enrich if less than 15) ---
    if current_orders < 15:
        # Get available SKUs
        skus = await db.dewi_toko_products.find({}, {"sku_code": 1, "name": 1, "base_price": 1, "_id": 0}).to_list(length=20)
        if not skus:
            skus = [{"sku_code": "TEST-SKU", "name": "Test", "base_price": 100000}]

        channels = ["shopee", "tokopedia", "tiktok_shop", "website", "manual"]
        statuses = ["new", "packed", "shipped", "delivered", "closed"]
        customer_names = ["Siti Aisyah", "Rina Hartati", "Dewi Kusuma", "Ayu Lestari",
                          "Fitri Nurhayati", "Mega Wulandari", "Nurul Hidayah", "Ratna Sari",
                          "Indah Permata", "Dian Arista", "Yuni Astuti", "Sri Rahayu",
                          "Rika Pratiwi", "Wulan Anggraini", "Tuti Handayani"]
        cities = ["Jakarta", "Surabaya", "Bandung", "Solo", "Yogyakarta", "Semarang", "Malang", "Medan"]
        couriers = ["JNE", "J&T", "SiCepat", "AnterAja", "Gosend"]

        next_seq = current_orders + 1
        orders_to_insert = []
        for i in range(20):
            sku = skus[i % len(skus)]
            qty = (i % 3) + 1
            price = sku.get("base_price", 100000)
            total = qty * price
            status = statuses[i % len(statuses)]
            days = 30 - i
            channel = channels[i % len(channels)]
            orders_to_insert.append({
                "id": _uid(),
                "order_number": f"ORD-20260501-{str(next_seq + i).zfill(3)}",
                "order_ref": f"{channel.upper()}-{str(10000 + i)}" if channel != "manual" else None,
                "channel_code": channel,
                "customer_name": customer_names[i % len(customer_names)],
                "customer_address": f"Jl. Contoh No. {i + 1}",
                "customer_city": cities[i % len(cities)],
                "customer_phone": f"0812345{str(70000 + i)}",
                "items": [{"sku_code": sku["sku_code"], "product_name": sku["name"],
                           "qty": qty, "price": price}],
                "total_amount": total,
                "fee_amount": total * 0.05 if channel in ("shopee", "tokopedia", "tiktok_shop") else 0,
                "courier": couriers[i % len(couriers)] if status != "new" else None,
                "tracking_number": f"TRK{10000000 + i}" if status in ("shipped", "delivered", "closed") else None,
                "notes": "",
                "status": status,
                "packed_at": now - timedelta(days=days - 1) if status != "new" else None,
                "shipped_at": now - timedelta(days=days - 2) if status in ("shipped", "delivered", "closed") else None,
                "delivered_at": now - timedelta(days=days - 4) if status in ("delivered", "closed") else None,
                "created_at": now - timedelta(days=days),
                "updated_at": now - timedelta(days=max(1, days - 5)),
                "created_by": user_name,
            })
        if orders_to_insert:
            await db.dewi_toko_orders.insert_many(orders_to_insert)
            counts["orders"] = len(orders_to_insert)

    # --- FLASHSALES (if less than 2) ---
    if await db.dewi_toko_flashsales.count_documents({}) < 2:
        skus_for_fs = await db.dewi_toko_products.find({}, {"sku_code": 1, "base_price": 1, "_id": 0}).limit(5).to_list(length=5)
        flashsale_seed = [
            {"id": _uid(), "flashsale_code": "FS-2026-001", "name": "Flashsale Lebaran Super Hemat",
             "channel_code": "shopee", "start_date": _date_str(-2), "end_date": _date_str(5),
             "items": [{"sku_code": s["sku_code"], "discount_pct": 25,
                        "flashsale_price": int(s.get("base_price", 100000) * 0.75)} for s in skus_for_fs[:3]],
             "status": "active", "total_items": 3,
             "created_at": now - timedelta(days=3), "updated_at": now - timedelta(days=2),
             "created_by": user_name},
            {"id": _uid(), "flashsale_code": "FS-2026-002", "name": "TikTok Shop 5.5 Megasale",
             "channel_code": "tiktok_shop", "start_date": _date_str(4), "end_date": _date_str(6),
             "items": [{"sku_code": s["sku_code"], "discount_pct": 30,
                        "flashsale_price": int(s.get("base_price", 100000) * 0.70)} for s in skus_for_fs[:2]],
             "status": "scheduled", "total_items": 2,
             "created_at": now - timedelta(days=1), "updated_at": now - timedelta(days=1),
             "created_by": user_name},
            {"id": _uid(), "flashsale_code": "FS-2026-003", "name": "Tokopedia Weekend Deal",
             "channel_code": "tokopedia", "start_date": _date_str(-20), "end_date": _date_str(-14),
             "items": [{"sku_code": s["sku_code"], "discount_pct": 15,
                        "flashsale_price": int(s.get("base_price", 100000) * 0.85)} for s in skus_for_fs[:4]],
             "status": "ended", "total_items": 4,
             "created_at": now - timedelta(days=22), "updated_at": now - timedelta(days=14),
             "created_by": user_name},
        ]
        await db.dewi_toko_flashsales.insert_many(flashsale_seed)
        counts["flashsales"] = len(flashsale_seed)

    # --- KOL CREATORS / DEALS / SAMPLES --- REMOVED (Session #11.16 Phase C + FORENSIC_12 GAP-01)
    # Collections dewi_kol_creators, dewi_kol_deals, dewi_kol_samples were DROPPED.
    # SSOT is now: marketing_kol_creators (via /api/marketing/kol/creators).
    # Seeding ke collections yang sudah di-drop akan me-recreate mereka — DILARANG.
    # Ref: FORENSIC_04 Cluster 6, FORENSIC_12 GAP-01.

    # --- RETURNS (if less than 2) ---
    if await db.dewi_toko_returns.count_documents({}) < 2:
        orders_for_return = await db.dewi_toko_orders.find(
            {"status": {"$in": ["delivered", "closed"]}},
            {"id": 1, "order_number": 1, "customer_name": 1, "channel_code": 1, "total_amount": 1, "_id": 0}
        ).limit(3).to_list(length=3)
        if orders_for_return:
            return_types = ["customer_refund", "expedition_return", "customer_refund"]
            return_statuses = ["new", "investigating", "resolved"]
            decisions = ["pending", "pending", "refund"]
            reasons = ["Ukuran tidak sesuai (M kekecilan)", "Retur ekspedisi karena alamat salah", "Produk cacat jahitan"]
            existing_count = await db.dewi_toko_returns.count_documents({})
            return_seed = []
            for i, o in enumerate(orders_for_return):
                return_seed.append({
                    "id": _uid(),
                    "return_code": f"RET-20260501-{str(existing_count + i + 1).zfill(3)}",
                    "order_id": o["id"], "order_number": o.get("order_number"),
                    "customer_name": o.get("customer_name"), "channel_code": o.get("channel_code"),
                    "return_type": return_types[i % 3],
                    "reason": reasons[i % 3],
                    "evidence_notes": "Foto disertakan di ticket",
                    "estimated_value": o.get("total_amount", 0),
                    "status": return_statuses[i % 3],
                    "decision": decisions[i % 3],
                    "decision_notes": "Refund via transfer" if decisions[i % 3] == "refund" else None,
                    "decision_at": (now - timedelta(days=1)).isoformat() if decisions[i % 3] == "refund" else None,
                    "created_at": now - timedelta(days=3 + i),
                    "updated_at": now - timedelta(days=1),
                    "created_by": user_name,
                })
            await db.dewi_toko_returns.insert_many(return_seed)
            counts["returns"] = len(return_seed)

    # --- REVIEWS (if less than 3) ---
    if await db.dewi_toko_reviews.count_documents({}) < 3:
        skus_for_rev = await db.dewi_toko_products.find({}, {"sku_code": 1, "name": 1, "_id": 0}).limit(5).to_list(length=5)
        review_seed = [
            {"id": _uid(), "channel_code": "shopee", "order_ref": "SHOPEE-10010",
             "customer_name": "Sari Ayu", "rating": 5,
             "review_text": "Bahannya adem, jahitan rapi, recommended!",
             "sku_code": skus_for_rev[0]["sku_code"] if skus_for_rev else None,
             "status": "unread", "response_text": None,
             "created_at": now - timedelta(days=2), "updated_at": now - timedelta(days=2),
             "created_by": user_name},
            {"id": _uid(), "channel_code": "tokopedia", "order_ref": "TOKPED-10011",
             "customer_name": "Rina Wijaya", "rating": 4,
             "review_text": "Overall bagus, packaging agak penyok sedikit",
             "sku_code": skus_for_rev[1]["sku_code"] if len(skus_for_rev) > 1 else None,
             "status": "responded", "response_text": "Terima kasih reviewnya kak, kami tingkatkan packaging",
             "responded_at": (now - timedelta(days=1)).isoformat(),
             "created_at": now - timedelta(days=3), "updated_at": now - timedelta(days=1),
             "created_by": user_name},
            {"id": _uid(), "channel_code": "tiktok_shop", "order_ref": "TIKTOK-10012",
             "customer_name": "Dewi Anggraini", "rating": 2,
             "review_text": "Warnanya beda dari foto, agak kecewa",
             "sku_code": skus_for_rev[2]["sku_code"] if len(skus_for_rev) > 2 else None,
             "status": "flagged", "response_text": None,
             "created_at": now - timedelta(days=4), "updated_at": now - timedelta(days=2),
             "created_by": user_name},
            {"id": _uid(), "channel_code": "shopee", "order_ref": "SHOPEE-10013",
             "customer_name": "Nina Putri", "rating": 5,
             "review_text": "Fast shipping, produk sesuai ekspektasi!",
             "sku_code": skus_for_rev[3]["sku_code"] if len(skus_for_rev) > 3 else None,
             "status": "responded", "response_text": "Terima kasih kak, ditunggu order berikutnya!",
             "responded_at": (now - timedelta(hours=12)).isoformat(),
             "created_at": now - timedelta(days=1), "updated_at": now - timedelta(hours=12),
             "created_by": user_name},
        ]
        await db.dewi_toko_reviews.insert_many(review_seed)
        counts["reviews"] = len(review_seed)

    return counts


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/seed-demo-full")
async def seed_demo_full(request: Request):
    """Seed demo data comprehensive untuk Phase 2, 3, 5 (idempotent)."""
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin"):
        raise HTTPException(403, "Hanya superadmin/admin yang bisa seed demo data")

    db = get_db()
    user_name = user.get("name", "System")

    results = {
        "phase_2_cutting": await seed_phase2_cutting(db, user_name),
        "phase_2_cmt": await seed_phase2_cmt(db, user_name),
        "phase_3_maklon": await seed_phase3_maklon(db, user_name),
        "phase_5_toko": await seed_phase5_toko(db, user_name),
    }
    return {"ok": True, "message": "Demo seed Phase 2-3-5 completed", "results": results}
