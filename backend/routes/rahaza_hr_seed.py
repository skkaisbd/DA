"""
CV. Dewi Aditya — HR Seed: Active Employees + Onboarding Template + Salary Grades

POST /api/rahaza/hr-seed/run  (admin only)

Seeds realistic demo data for HRIS testing:
- 1 default onboarding template (jika belum ada)
- 12 active karyawan dengan data lengkap (NIK, BPJS, NPWP, bank, kontrak)
- 7 salary grades (G1-G7) dengan min/mid/max range
- 3 sample LMS courses
- Default leave types (jika belum ada)
- Payroll profiles for all 12 employees
- Sample attendance data (last 7 working days)
"""
import uuid
import random
from datetime import datetime, timezone, date, timedelta
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth

router = APIRouter(prefix="/api/rahaza/hr-seed", tags=["rahaza-hr-seed"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


SALARY_GRADES = [
    {"grade_code": "G1", "grade_name": "Level 1 — Operator Dasar",     "level": 1, "min_salary":  3_500_000, "mid_salary":  4_200_000, "max_salary":  5_000_000},
    {"grade_code": "G2", "grade_name": "Level 2 — Operator Senior",    "level": 2, "min_salary":  4_500_000, "mid_salary":  5_500_000, "max_salary":  6_500_000},
    {"grade_code": "G3", "grade_name": "Level 3 — Supervisor",         "level": 3, "min_salary":  6_000_000, "mid_salary":  7_500_000, "max_salary":  9_000_000},
    {"grade_code": "G4", "grade_name": "Level 4 — Section Head",       "level": 4, "min_salary":  8_000_000, "mid_salary": 10_000_000, "max_salary": 12_000_000},
    {"grade_code": "G5", "grade_name": "Level 5 — Department Manager", "level": 5, "min_salary": 12_000_000, "mid_salary": 15_000_000, "max_salary": 20_000_000},
    {"grade_code": "G6", "grade_name": "Level 6 — Division Head",      "level": 6, "min_salary": 20_000_000, "mid_salary": 28_000_000, "max_salary": 35_000_000},
    {"grade_code": "G7", "grade_name": "Level 7 — Director / GM",      "level": 7, "min_salary": 35_000_000, "mid_salary": 50_000_000, "max_salary": 80_000_000},
]


ONBOARDING_TASKS_DEFAULT = [
    {"title": "Verifikasi & upload dokumen (KTP, NPWP, ijazah)", "category": "Documents", "day": 1, "assigned_to": "HR"},
    {"title": "Tanda tangan kontrak kerja & peraturan perusahaan", "category": "Legal", "day": 1, "assigned_to": "HR"},
    {"title": "Orientasi perusahaan (visi-misi, nilai, budaya)", "category": "Orientation", "day": 1, "assigned_to": "HR"},
    {"title": "Setup akun ERP + email + Slack", "category": "IT", "day": 2, "assigned_to": "IT"},
    {"title": "Pengenalan tim & buddy assignment", "category": "Orientation", "day": 2, "assigned_to": "Manager"},
    {"title": "Training keselamatan kerja (K3)", "category": "Training", "day": 3, "assigned_to": "HR"},
    {"title": "Training SOP spesifik divisi", "category": "Training", "day": 5, "assigned_to": "Supervisor"},
    {"title": "Pembagian seragam + ID Card + APD", "category": "Assets", "day": 1, "assigned_to": "HR"},
    {"title": "Pendaftaran BPJS Kesehatan & Ketenagakerjaan", "category": "Benefits", "day": 7, "assigned_to": "HR"},
    {"title": "Review probation + target 3 bulan", "category": "Performance", "day": 14, "assigned_to": "Manager"},
    {"title": "Evaluasi akhir probation (3 bulan)", "category": "Performance", "day": 90, "assigned_to": "Manager"},
]


EMPLOYEES_SEED = [
    {"employee_code": "DA-001", "name": "Budi Santoso",       "gender": "L", "birth_date": "1985-03-15", "birth_place": "Bandung",   "marital_status": "married", "religion": "Islam",  "ktp_number": "3273011503850001", "npwp_number": "123456789012345", "tax_ptkp": "K/2", "department": "Manajemen",  "job_title": "Direktur Operasional", "grade": "G7", "base_rate": 45_000_000, "wage_scheme": "monthly", "bank_name": "BCA",     "email": "budi@dewiaditya.id",  "phone": "081234567801"},
    {"employee_code": "DA-002", "name": "Siti Rahayu",        "gender": "P", "birth_date": "1988-07-22", "birth_place": "Jakarta",   "marital_status": "married", "religion": "Islam",  "ktp_number": "3173012207880002", "npwp_number": "123456789012346", "tax_ptkp": "K/1", "department": "HRD",        "job_title": "HR Manager",          "grade": "G5", "base_rate": 13_500_000, "wage_scheme": "monthly", "bank_name": "Mandiri", "email": "siti@dewiaditya.id",  "phone": "081234567802"},
    {"employee_code": "DA-003", "name": "Ahmad Fauzi",        "gender": "L", "birth_date": "1990-11-30", "birth_place": "Surabaya",  "marital_status": "single",  "religion": "Islam",  "ktp_number": "3273013011900003", "npwp_number": "123456789012347", "tax_ptkp": "TK/0", "department": "Produksi",  "job_title": "Production Supervisor","grade": "G3", "base_rate":  7_200_000, "wage_scheme": "monthly", "bank_name": "BRI",     "email": "ahmad@dewiaditya.id", "phone": "081234567803"},
    {"employee_code": "DA-004", "name": "Dewi Anggraini",     "gender": "P", "birth_date": "1995-04-18", "birth_place": "Yogyakarta","marital_status": "single",  "religion": "Islam",  "ktp_number": "3471011804950004", "npwp_number": "",                "tax_ptkp": "TK/0", "department": "QC",         "job_title": "QC Supervisor",       "grade": "G3", "base_rate":  6_800_000, "wage_scheme": "monthly", "bank_name": "BNI",     "email": "dewi@dewiaditya.id",  "phone": "081234567804"},
    {"employee_code": "DA-005", "name": "Rudi Hartanto",      "gender": "L", "birth_date": "1992-09-12", "birth_place": "Semarang",  "marital_status": "married", "religion": "Islam",  "ktp_number": "3374011209920005", "npwp_number": "",                "tax_ptkp": "K/0", "department": "Gudang/WMS", "job_title": "Warehouse Supervisor","grade": "G3", "base_rate":  6_500_000, "wage_scheme": "monthly", "bank_name": "BCA",     "email": "rudi@dewiaditya.id",  "phone": "081234567805"},
    {"employee_code": "DA-006", "name": "Maya Putri",         "gender": "P", "birth_date": "1998-01-25", "birth_place": "Bandung",   "marital_status": "single",  "religion": "Kristen Protestan","ktp_number": "3273012501980006", "npwp_number": "", "tax_ptkp": "TK/0", "department": "Produksi",   "job_title": "Operator CMT-Sewing", "grade": "G2", "base_rate":  5_200_000, "wage_scheme": "monthly", "bank_name": "BRI",     "email": "",                    "phone": "081234567806"},
    {"employee_code": "DA-007", "name": "Joko Prasetyo",      "gender": "L", "birth_date": "1996-06-08", "birth_place": "Malang",    "marital_status": "married", "religion": "Islam",  "ktp_number": "3573010806960007", "npwp_number": "",                "tax_ptkp": "K/1", "department": "Produksi",   "job_title": "Operator Cutting",    "grade": "G1", "base_rate":  4_500_000, "wage_scheme": "monthly", "bank_name": "BRI",     "email": "",                    "phone": "081234567807"},
    {"employee_code": "DA-008", "name": "Linda Sari",         "gender": "P", "birth_date": "2000-12-05", "birth_place": "Cirebon",   "marital_status": "single",  "religion": "Islam",  "ktp_number": "3209010512000008", "npwp_number": "",                "tax_ptkp": "TK/0", "department": "Produksi",   "job_title": "Operator QC",         "grade": "G1", "base_rate":  4_200_000, "wage_scheme": "monthly", "bank_name": "Mandiri", "email": "",                    "phone": "081234567808"},
    {"employee_code": "DA-009", "name": "Bambang Wijaya",     "gender": "L", "birth_date": "1987-02-20", "birth_place": "Solo",      "marital_status": "married", "religion": "Islam",  "ktp_number": "3374012002870009", "npwp_number": "123456789012349", "tax_ptkp": "K/2", "department": "Finance/Accounting", "job_title": "Finance Manager",  "grade": "G5", "base_rate": 14_000_000, "wage_scheme": "monthly", "bank_name": "BCA",     "email": "bambang@dewiaditya.id","phone": "081234567809"},
    {"employee_code": "DA-010", "name": "Rina Kusuma",        "gender": "P", "birth_date": "1994-08-14", "birth_place": "Bandung",   "marital_status": "married", "religion": "Islam",  "ktp_number": "3273011408940010", "npwp_number": "123456789012350", "tax_ptkp": "K/0", "department": "Administrasi","job_title": "Admin Officer",       "grade": "G2", "base_rate":  5_800_000, "wage_scheme": "monthly", "bank_name": "BCA",     "email": "rina@dewiaditya.id",  "phone": "081234567810"},
    {"employee_code": "DA-011", "name": "Hendra Wibowo",      "gender": "L", "birth_date": "1993-05-03", "birth_place": "Depok",     "marital_status": "married", "religion": "Islam",  "ktp_number": "3276010305930011", "npwp_number": "123456789012351", "tax_ptkp": "K/1", "department": "IT",         "job_title": "IT Staff",            "grade": "G2", "base_rate":  6_200_000, "wage_scheme": "monthly", "bank_name": "Mandiri", "email": "hendra@dewiaditya.id","phone": "081234567811"},
    {"employee_code": "DA-012", "name": "Fitri Aulia",        "gender": "P", "birth_date": "1997-10-27", "birth_place": "Bekasi",    "marital_status": "single",  "religion": "Islam",  "ktp_number": "3275012710970012", "npwp_number": "",                "tax_ptkp": "TK/0", "department": "Marketing",  "job_title": "Marketing Staff",     "grade": "G2", "base_rate":  5_500_000, "wage_scheme": "monthly", "bank_name": "BNI",     "email": "fitri@dewiaditya.id", "phone": "081234567812"},
]


@router.post("/run")
async def run_seed(request: Request):
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner"):
        raise HTTPException(403, "Hanya admin yang dapat run seed.")
    db = get_db()
    body = await request.json() if request.headers.get("content-length") else {}
    force = bool(body.get("force", False))

    result = {"grades": {"created": 0, "skipped": 0}, "employees": {"created": 0, "skipped": 0},
              "onboarding_template": None, "courses": {"created": 0, "skipped": 0},
              "leave_types": {"created": 0, "skipped": 0}}

    # ─── 1) Salary Grades ────────────────────────────────────────────────
    grade_id_map = {}
    for g in SALARY_GRADES:
        existing = await db.rahaza_salary_grades.find_one({"grade_code": g["grade_code"]})
        if existing and not force:
            grade_id_map[g["grade_code"]] = existing["id"]
            result["grades"]["skipped"] += 1
            continue
        if existing:
            await db.rahaza_salary_grades.delete_one({"grade_code": g["grade_code"]})
        doc = {"id": _uid(), "currency": "IDR", "is_active": True, "description": "", "created_at": _now(), "updated_at": _now(), **g}
        await db.rahaza_salary_grades.insert_one(doc)
        grade_id_map[g["grade_code"]] = doc["id"]
        result["grades"]["created"] += 1

    # ─── 2) Leave Types (UU No. 13 Tahun 2003) ──────────────────────────────
    default_lt = [
        # ── CUTI (terencana, diajukan sebelumnya) ──────────────────────────
        {"code": "ANNUAL",      "name": "Cuti Tahunan",              "quota_default": 12,
         "color": "#10b981", "unpaid": False, "request_type": "cuti",
         "requires_document": False, "max_days_without_doc": 0,
         "doc_note": "", "legal_basis": "Pasal 79 UU 13/2003"},

        {"code": "MATERNITY",   "name": "Cuti Melahirkan",           "quota_default": 90,
         "color": "#ec4899", "unpaid": False, "request_type": "cuti",
         "requires_document": True,  "max_days_without_doc": 0,
         "doc_note": "Wajib lampirkan surat keterangan dokter/bidan",
         "legal_basis": "Pasal 82 UU 13/2003"},

        {"code": "LWOP",        "name": "Cuti Tanpa Gaji (LWOP)",    "quota_default": 30,
         "color": "#64748b", "unpaid": True,  "request_type": "cuti",
         "requires_document": False, "max_days_without_doc": 0,
         "doc_note": "", "legal_basis": "Kesepakatan bersama"},

        {"code": "LONG_SERVICE","name": "Cuti Panjang (6 Tahun)",    "quota_default": 22,
         "color": "#8b5cf6", "unpaid": False, "request_type": "cuti",
         "requires_document": False, "max_days_without_doc": 0,
         "doc_note": "", "legal_basis": "Pasal 79 ayat 2c UU 13/2003"},

        # ── SAKIT (bisa diajukan setelah kejadian) ─────────────────────────
        {"code": "SICK",        "name": "Izin Sakit",                "quota_default": 14,
         "color": "#ef4444", "unpaid": False, "request_type": "sakit",
         "requires_document": True,  "max_days_without_doc": 2,
         "doc_note": "Tanpa surat dokter maks. 2 hari. Lebih dari 2 hari wajib lampirkan surat dokter.",
         "legal_basis": "Pasal 93 UU 13/2003"},

        {"code": "MENSTRUAL",   "name": "Izin Haid",                 "quota_default": 2,
         "color": "#f472b6", "unpaid": False, "request_type": "sakit",
         "requires_document": False, "max_days_without_doc": 2,
         "doc_note": "", "legal_basis": "Pasal 81 UU 13/2003"},

        # ── IZIN (mendadak/acara, bisa same-day, butuh bukti) ─────────────
        {"code": "MARRIAGE",    "name": "Izin Pernikahan Sendiri",   "quota_default": 3,
         "color": "#f59e0b", "unpaid": False, "request_type": "izin",
         "requires_document": True,  "max_days_without_doc": 0,
         "doc_note": "Lampirkan foto undangan pernikahan atau akta nikah",
         "legal_basis": "Pasal 93 ayat 4 UU 13/2003"},

        {"code": "CHILD_MARRY", "name": "Izin Menikahkan Anak",      "quota_default": 2,
         "color": "#f59e0b", "unpaid": False, "request_type": "izin",
         "requires_document": True,  "max_days_without_doc": 0,
         "doc_note": "Lampirkan foto undangan pernikahan anak",
         "legal_basis": "Pasal 93 ayat 4 UU 13/2003"},

        {"code": "CHILD_BIRTH", "name": "Izin Kelahiran Anak",       "quota_default": 2,
         "color": "#06b6d4", "unpaid": False, "request_type": "izin",
         "requires_document": True,  "max_days_without_doc": 0,
         "doc_note": "Lampirkan surat keterangan kelahiran/akta lahir",
         "legal_basis": "Pasal 93 ayat 4 UU 13/2003"},

        {"code": "CIRCUMCISION","name": "Izin Khitan/Baptis Anak",   "quota_default": 2,
         "color": "#10b981", "unpaid": False, "request_type": "izin",
         "requires_document": True,  "max_days_without_doc": 0,
         "doc_note": "Lampirkan foto undangan/surat keterangan",
         "legal_basis": "Pasal 93 ayat 4 UU 13/2003"},

        {"code": "BEREAVEMENT", "name": "Izin Duka Cita",            "quota_default": 2,
         "color": "#6b7280", "unpaid": False, "request_type": "izin",
         "requires_document": False, "max_days_without_doc": 2,
         "doc_note": "Surat keterangan kematian dapat dilampirkan",
         "legal_basis": "Pasal 93 ayat 4 UU 13/2003"},

        {"code": "PERSONAL",    "name": "Izin Pribadi",              "quota_default": 3,
         "color": "#f59e0b", "unpaid": False, "request_type": "izin",
         "requires_document": False, "max_days_without_doc": 0,
         "doc_note": "", "legal_basis": "Kebijakan perusahaan"},
    ]
    # BUG-4 (2026-07-26): seeder dulu menulis dokumen yang HANYA punya `unpaid`
    # (tanpa cermin `paid`), sedangkan form HR menulis `paid` saja — satu koleksi
    # dua bentuk. Sekarang keduanya lewat SSOT `utils/leave_types`.
    from utils.leave_types import build_leave_type_doc
    for lt in default_lt:
        existing = await db.rahaza_leave_types.find_one({"code": lt["code"]})
        if existing and not force:
            result["leave_types"]["skipped"] += 1
            continue
        if existing:
            await db.rahaza_leave_types.delete_one({"code": lt["code"]})
        await db.rahaza_leave_types.insert_one({
            "id": _uid(), **build_leave_type_doc(lt), "created_at": _now(),
        })
        result["leave_types"]["created"] += 1

    # ─── 3) Onboarding Template ──────────────────────────────────────────
    existing_tpl = await db.dewi_onboarding_templates.find_one({"is_default": True})
    if existing_tpl and not force:
        result["onboarding_template"] = "skipped"
    else:
        if existing_tpl:
            await db.dewi_onboarding_templates.delete_one({"_id": existing_tpl["_id"]})
        await db.dewi_onboarding_templates.insert_one({
            "template_id": _uid(),
            "name": "Template Standar Karyawan Baru",
            "dept": "",
            "description": "Checklist onboarding standar untuk semua karyawan baru. 11 task dalam 90 hari probation.",
            "tasks": ONBOARDING_TASKS_DEFAULT,
            "duration_days": 90,
            "is_default": True,
            "created_by": user.get("name", "Admin"),
            "created_at": _now(),
            "updated_at": _now(),
        })
        result["onboarding_template"] = "created"

    # ─── 4) LMS Sample Courses ───────────────────────────────────────────
    default_courses = [
        {"code": "K3-001", "title": "Keselamatan & Kesehatan Kerja (K3) Dasar", "duration_hours": 4,  "category": "Safety"},
        {"code": "SOP-CMT", "title": "SOP Operator CMT-Sewing",                 "duration_hours": 8,  "category": "Operational"},
        {"code": "QC-101",  "title": "Quality Control Garment 101",             "duration_hours": 6,  "category": "Operational"},
    ]
    for c in default_courses:
        existing = await db.dewi_lms_courses.find_one({"code": c["code"]})
        if existing and not force:
            result["courses"]["skipped"] += 1
            continue
        if existing:
            await db.dewi_lms_courses.delete_one({"code": c["code"]})
        await db.dewi_lms_courses.insert_one({
            "course_id": _uid(), **c,
            "description": "Course ini disediakan sebagai bagian dari onboarding standar CV. Dewi Aditya.",
            "is_active": True,
            "created_at": _now(), "updated_at": _now(),
        })
        result["courses"]["created"] += 1

    # ─── 5) Employees ────────────────────────────────────────────────────
    # Grade G3 and above are considered "senior" (PKWTT contract, no end date)
    senior_grades = {"G3", "G4", "G5", "G6", "G7"}
    for e in EMPLOYEES_SEED:
        existing = await db.rahaza_employees.find_one({"employee_code": e["employee_code"]})
        if existing and not force:
            # Reactivate if inactive
            if not existing.get("active"):
                await db.rahaza_employees.update_one(
                    {"id": existing["id"]},
                    {"$set": {"active": True, "updated_at": _now()}}
                )
            result["employees"]["skipped"] += 1
            continue
        if existing:
            await db.rahaza_employees.delete_one({"id": existing["id"]})

        doc = {
            "id": _uid(),
            "employee_code": e["employee_code"],
            "name": e["name"],
            "department": e["department"],
            "job_title": e["job_title"],
            "location_id": None,
            "phone": e["phone"],
            "email": e["email"],
            "contract_type": "PKWTT" if e["grade"] in senior_grades else "PKWT",
            "contract_start_date": (date.today() - timedelta(days=730)).isoformat(),
            "contract_end_date": None if e["grade"] in senior_grades else (date.today() + timedelta(days=180)).isoformat(),
            "wage_scheme": e["wage_scheme"],
            "base_rate": e["base_rate"],
            "joined_at": (_now() - timedelta(days=730)).isoformat(),
            "salary_grade_id": grade_id_map.get(e["grade"]),
            "gender": e["gender"], "birth_date": e["birth_date"], "birth_place": e["birth_place"],
            "marital_status": e["marital_status"], "religion": e["religion"], "nationality": "Indonesia",
            "ktp_address": f"Jl. Sample No.{e['employee_code'][-2:]}, {e['birth_place']}",
            "current_address": f"Jl. Sample No.{e['employee_code'][-2:]}, {e['birth_place']}",
            "education_level": "S1" if e["grade"] in senior_grades else "SMA/SMK",
            "education_institution": "Universitas Padjadjaran" if e["grade"] in senior_grades else "SMK Negeri 1",
            "education_major": "Manajemen" if e["grade"] in senior_grades else "Tata Busana",
            "photo_url": "",
            "ktp_number": e["ktp_number"],
            "npwp_number": e["npwp_number"],
            "tax_ptkp": e["tax_ptkp"],
            "bpjs_kesehatan_number": f"0002345{e['employee_code'][-3:]}",
            "bpjs_ketenagakerjaan_number": f"12345{e['employee_code'][-3:]}",
            "bank_name": e["bank_name"],
            "bank_account_number": f"12345{e['employee_code'][-3:]}0",
            "bank_account_holder": e["name"],
            "emergency_contact_name": "Orang Tua",
            "emergency_phone": "08111111111",
            "emergency_relation": "Orang Tua",
            "active": True,
            "employee_status": "active",
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.rahaza_employees.insert_one(doc)
        result["employees"]["created"] += 1

    # ─── 6) Payroll Profiles ─────────────────────────────────────────────
    result["payroll_profiles"] = {"created": 0, "skipped": 0}
    emps_list = await db.rahaza_employees.find({"active": True}, {"_id": 0}).to_list(500)
    for emp in emps_list:
        existing_pp = await db.rahaza_payroll_profiles.find_one({"employee_id": emp["id"], "active": True})
        if existing_pp and not force:
            result["payroll_profiles"]["skipped"] += 1
            continue
        if existing_pp:
            await db.rahaza_payroll_profiles.delete_one({"employee_id": emp["id"]})
        pp_doc = {
            "id": _uid(),
            "employee_id": emp["id"],
            "pay_scheme": emp.get("wage_scheme", "monthly"),
            "period_type": "monthly",
            "cutoff_config": {"start_day": 1},
            "base_rate": float(emp.get("base_rate", 0)),
            "overtime_rate": round(float(emp.get("base_rate", 0)) / 173, 2),  # Monthly to hourly
            "pcs_process_rates": [],
            "notes": f"Profile auto-generated saat seed untuk {emp.get('name', '')}",
            "active": True,
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.rahaza_payroll_profiles.insert_one(pp_doc)
        result["payroll_profiles"]["created"] += 1

    # ─── 7) Sample Attendance (last 7 working days) ─────────────────────
    result["attendance"] = {"created": 0, "skipped": 0}
    today = date.today()
    # Build last 7 working days (skip weekends)
    working_days = []
    d = today - timedelta(days=1)  # start from yesterday
    while len(working_days) < 7:
        if d.weekday() < 5:  # Mon-Fri
            working_days.append(d)
        d -= timedelta(days=1)

    # Attendance status weights per employee type
    for emp in emps_list:
        for work_day in working_days:
            day_str = work_day.isoformat()
            existing_att = await db.rahaza_attendance_events.find_one(
                {"employee_id": emp["id"], "date": day_str}
            )
            if existing_att and not force:
                result["attendance"]["skipped"] += 1
                continue
            if existing_att:
                await db.rahaza_attendance_events.delete_one({"employee_id": emp["id"], "date": day_str})

            # Realistic attendance distribution: 85% hadir, 5% izin, 5% sakit, 5% cuti
            rand = random.random()
            if rand < 0.85:
                status = "hadir"
                hours = round(random.uniform(7.5, 8.5), 2)
                ot = round(random.uniform(0, 1.5), 2) if random.random() < 0.2 else 0.0
            elif rand < 0.90:
                status = "izin"
                hours = 0.0
                ot = 0.0
            elif rand < 0.95:
                status = "sakit"
                hours = 0.0
                ot = 0.0
            else:
                status = "cuti"
                hours = 0.0
                ot = 0.0

            att_doc = {
                "id": _uid(),
                "employee_id": emp["id"],
                "date": day_str,
                "shift_id": None,
                "clock_in": None,
                "clock_out": None,
                "hours_worked": hours,
                "overtime_hours": ot,
                "status": status,
                "notes": "Data demo dari seed",
                "source": "supervisor",
                "updated_by": user["id"],
                "updated_by_name": user.get("name", "Admin"),
                "created_by": user["id"],
                "created_by_name": user.get("name", "Admin"),
                "created_at": _now(),
                "updated_at": _now(),
            }
            await db.rahaza_attendance_events.insert_one(att_doc)
            result["attendance"]["created"] += 1

    return {"ok": True, "summary": result}



@router.post("/seed-connected")
async def seed_connected_demo_data(request: Request):
    """
    Seed data demo yang terhubung: leave_requests, overtime_requests, leave_balances.
    Semua data menggunakan employee records yang sudah ada.
    Idempotent — skip jika sudah ada.
    """
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner"):
        raise HTTPException(403, "Admin only.")
    db = get_db()
    now = _now()
    today = now.date()
    import calendar

    result = {"leave_types_seed": 0, "leave_balances": 0, "leave_requests": 0,
              "overtime_requests": 0, "leave_carry_applied": 0}

    # Fetch employees & leave types
    employees = await db.rahaza_employees.find({"active": True}, {"_id": 0}).to_list(50)
    leave_types = await db.rahaza_leave_types.find({"active": True}, {"_id": 0}).to_list(50)
    if not employees:
        return {"ok": False, "message": "Tidak ada karyawan. Jalankan /run seed dulu."}
    if not leave_types:
        return {"ok": False, "message": "Tidak ada tipe cuti. Jalankan /run seed dulu."}

    annual_lt = next((lt for lt in leave_types if lt.get("code") == "ANNUAL"), None)
    sick_lt   = next((lt for lt in leave_types if lt.get("code") == "SICK"),   None)
    if not annual_lt:
        return {"ok": False, "message": "Leave type ANNUAL tidak ditemukan."}

    year = today.year

    # ── 1. Seed leave balances untuk semua karyawan ──────────────────────────
    for emp in employees:
        for lt in leave_types[:6]:  # top 6 types
            existing = await db.rahaza_leave_balances.find_one(
                {"employee_id": emp["id"], "leave_type_id": lt["id"], "year": year}, {"_id": 0}
            )
            if not existing:
                await db.rahaza_leave_balances.insert_one({
                    "id":           str(__import__("uuid").uuid4()),
                    "employee_id":  emp["id"],
                    "leave_type_id": lt["id"],
                    "year":         year,
                    "allocated":    int(lt.get("quota_default", 12)),
                    "used":         0,
                    "adjustments":  [],
                    "created_at":   now,
                    "updated_at":   now,
                })
                result["leave_balances"] += 1

    # ── 2. Seed leave requests (1 per 3 karyawan) ───────────────────────────
    for i, emp in enumerate(employees[:4]):
        existing = await db.rahaza_leave_requests.find_one({"employee_id": emp["id"]}, {"_id": 0, "id": 1})
        if existing:
            continue
        lt = annual_lt if i % 2 == 0 else (sick_lt or annual_lt)
        from_date = today.replace(day=max(1, today.day - 5 + i)).isoformat()
        to_date   = today.replace(day=min(calendar.monthrange(year, today.month)[1], today.day - 3 + i)).isoformat()
        doc = {
            "id":              str(__import__("uuid").uuid4()),
            "employee_id":     emp["id"],
            "leave_type_id":   lt["id"],
            "request_type":    lt.get("request_type", "cuti"),
            "from_date":       from_date,
            "to_date":         to_date,
            "duration_days":   2,
            "duration_working_days": 2,
            "holidays_in_period": [],
            "is_half_day":     False,
            "half_day_period": None,
            "reason":          "Demo request",
            "attachment_url":  "",
            "attachment_filename": "",
            "status":          "approved" if i < 2 else "pending_approval",
            "approval_level_required": 1,
            "current_approval_level": 1,
            "submitted_at":    now,
            "submitted_by":    user["id"],
            "created_by":      user["id"],
            "created_by_name": user.get("name", ""),
            "created_at":      now,
            "updated_at":      now,
        }
        await db.rahaza_leave_requests.insert_one(doc)
        result["leave_requests"] += 1

    # ── 3. Seed overtime requests ─────────────────────────────────────────
    for emp in employees[:3]:
        existing = await db.rahaza_overtime_requests.find_one({"employee_id": emp["id"]}, {"_id": 0, "id": 1})
        if existing:
            continue
        doc = {
            "id":          str(__import__("uuid").uuid4()),
            "employee_id": emp["id"],
            "date":        (today.replace(day=max(1, today.day - 2))).isoformat(),
            "start_time":  "17:00",
            "end_time":    "19:00",
            "reason":      "Penyelesaian laporan bulanan",
            "status":      "approved",
            "created_at":  now,
            "updated_at":  now,
            "created_by":  user["id"],
        }
        await db.rahaza_overtime_requests.insert_one(doc)
        result["overtime_requests"] += 1

    return {"ok": True, "summary": result}



@router.post("/seed-kpi")
async def seed_kpi_demo(request: Request):
    """
    Seed demo KPI periods + questions + submissions + results (published) untuk karyawan terhubung.
    Membuat 3 bulan data KPI (Feb, Mar, Apr 2026) agar KPI Saya terisi.
    """
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner"):
        raise HTTPException(403, "Admin only.")
    db  = get_db()
    now = _now()

    result = {"questions": 0, "periods": 0, "participants": 0, "results": 0}

    # ── 1. Seed KPI Questions (default) ──────────────────────────────────────
    q_count = await db.da_kpi_questions.count_documents({})
    if q_count == 0:
        await db.da_kpi_questions.count_documents({})
        # Trigger seed via internal function
        from routes.dewi_kpi import DEFAULT_QUESTIONS
        for q in DEFAULT_QUESTIONS:
            if not await db.da_kpi_questions.find_one({"question_id": q.get("question_id")}):
                q_doc = dict(q)
                if "question_id" not in q_doc:
                    q_doc["question_id"] = _uid()
                q_doc["created_at"] = now
                await db.da_kpi_questions.insert_one(q_doc)
                result["questions"] += 1

    # ── 2. Fetch linked employees ─────────────────────────────────────────────
    linked_emps = await db.rahaza_employees.find(
        {"user_id": {"$exists": True, "$ne": None}, "active": True},
        {"_id": 0, "id": 1, "name": 1, "employee_code": 1, "department": 1}
    ).to_list(50)

    if not linked_emps:
        return {"ok": False, "message": "Tidak ada karyawan terhubung. Run seed + auto-link dulu."}

    emp_ids = [e["id"] for e in linked_emps]

    # ── 3. Seed KPI Periods (3 bulan) ─────────────────────────────────────────
    periods_data = [
        {"month": 2, "year": 2026, "name": "KPI Februari 2026", "status": "finalized"},
        {"month": 3, "year": 2026, "name": "KPI Maret 2026",    "status": "finalized"},
        {"month": 4, "year": 2026, "name": "KPI April 2026",    "status": "finalized"},
    ]

    period_docs = {}
    for pd in periods_data:
        existing = await db.da_kpi_periods.find_one(
            {"month": pd["month"], "year": pd["year"]}, {"_id": 0, "period_id": 1}
        )
        if existing:
            period_docs[pd["month"]] = existing["period_id"]
            continue

        pid  = _uid()
        doc  = {
            "period_id":              pid,
            "name":                   pd["name"],
            "month":                  pd["month"],
            "year":                   pd["year"],
            "status":                 pd["status"],
            "participant_employee_ids": emp_ids,
            "participant_count":      len(emp_ids),
            "perform_weight":         0.40,
            "attitude_weight":        0.30,
            "absensi_weight":         0.30,
            "finalized_at":           now,
            "created_at":             now,
            "updated_at":             now,
            "created_by":             user["id"],
        }
        await db.da_kpi_periods.insert_one(doc)
        period_docs[pd["month"]] = pid
        result["periods"] += 1
        result["participants"] += len(emp_ids)

    # ── 4. Seed KPI Results (published) per employee per period ──────────────
    scores_by_emp = {
        # DA-001 Budi — high performer
        emp_ids[0] if len(emp_ids) > 0 else "x": [88, 90, 87],
        # DA-002 Siti — good
        emp_ids[1] if len(emp_ids) > 1 else "y": [82, 79, 84],
        # Others — random 70-90
    }

    for emp in linked_emps:
        eid = emp["id"]
        preset = scores_by_emp.get(eid)
        for i, (month, pid) in enumerate(sorted(period_docs.items())):
            existing = await db.da_kpi_results.find_one(
                {"period_id": pid, "employee_id": eid}, {"_id": 0, "id": 1}
            )
            if existing:
                continue

            if preset and i < len(preset):
                score = preset[i]
            else:
                score = random.randint(70, 92)

            grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D"

            res_doc = {
                "id":              _uid(),
                "result_id":       _uid(),
                "period_id":       pid,
                "employee_id":     eid,
                "employee_name":   emp.get("name", ""),
                "employee_code":   emp.get("employee_code", ""),
                "department":      emp.get("department", ""),
                "perform_score":   round(score * 0.9 + random.uniform(-3, 3), 2),
                "attitude_score":  round(score * 0.95 + random.uniform(-2, 2), 2),
                "absensi_score":   round(min(100, score + random.randint(0, 10)), 2),
                "kpi_final":       float(score),
                "grade":           grade,
                "publish_status":  "published",
                "published_at":    now,
                "created_at":      now,
                "updated_at":      now,
            }
            await db.da_kpi_results.insert_one(res_doc)
            result["results"] += 1

    return {"ok": True, "summary": result,
            "message": f"KPI seed selesai: {result['periods']} periode, {result['results']} hasil dipublish"}
