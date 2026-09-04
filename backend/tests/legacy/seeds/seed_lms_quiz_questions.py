"""
Seed Quiz Questions ke Materials yang ber-type 'quiz'
Tambahkan field 'questions' ke setiap quiz material agar bisa di-render di UI.
"""
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient


# Quiz questions per course title (match by course title for clarity)
QUIZ_BANK = {
    "Keselamatan Kerja & K3 2024": [
        {
            "question": "Apa kepanjangan dari APD?",
            "choices": [
                "Alat Pengaman Diri",
                "Alat Pelindung Diri",
                "Aparatur Pelindung Darurat",
                "Asisten Pengawas Divisi"
            ],
            "correct_index": 1,
        },
        {
            "question": "Yang termasuk APD wajib di area produksi garmen adalah:",
            "choices": [
                "Masker, sarung tangan, dan sepatu safety",
                "Topi dan dasi",
                "Hanya sarung tangan",
                "Tidak perlu APD"
            ],
            "correct_index": 0,
        },
        {
            "question": "Saat terjadi kebakaran, langkah pertama yang harus dilakukan?",
            "choices": [
                "Lari secepat mungkin",
                "Mengambil barang berharga",
                "Tenang dan ikuti prosedur evakuasi",
                "Berteriak panik"
            ],
            "correct_index": 2,
        },
        {
            "question": "Berapa lama briefing K3 harian sebaiknya dilakukan?",
            "choices": [
                "5-10 menit",
                "30-45 menit",
                "Tidak perlu briefing",
                "Lebih dari 1 jam"
            ],
            "correct_index": 0,
        },
        {
            "question": "Jika menemukan kondisi tidak aman di area kerja, sebaiknya:",
            "choices": [
                "Diabaikan saja",
                "Segera laporkan ke supervisor",
                "Diperbaiki sendiri tanpa izin",
                "Menunggu sampai ada kecelakaan"
            ],
            "correct_index": 1,
        },
    ],
    "Dasar-Dasar Quality Control (QC)": [
        {
            "question": "Apa fungsi utama Quality Control?",
            "choices": [
                "Menambah jumlah produksi",
                "Memastikan produk memenuhi standar kualitas",
                "Mengurangi tenaga kerja",
                "Mempercepat produksi tanpa pemeriksaan"
            ],
            "correct_index": 1,
        },
        {
            "question": "Defect kategori 'Critical' biasanya berarti:",
            "choices": [
                "Bisa diabaikan",
                "Mempengaruhi keamanan/fungsi utama produk",
                "Hanya masalah warna",
                "Defect kecil yang tidak terlihat"
            ],
            "correct_index": 1,
        },
        {
            "question": "AQL singkatan dari?",
            "choices": [
                "Average Quality Level",
                "Acceptable Quality Level",
                "Approved Quality List",
                "Automated Quality Logic"
            ],
            "correct_index": 1,
        },
        {
            "question": "Inspeksi inline dilakukan pada tahap?",
            "choices": [
                "Sebelum produksi",
                "Setelah pengiriman",
                "Selama proses produksi",
                "Hanya saat keluhan customer"
            ],
            "correct_index": 2,
        },
        {
            "question": "Tools standar untuk mengukur tegangan jahitan adalah:",
            "choices": [
                "Mistar",
                "Tension gauge",
                "Stopwatch",
                "Termometer"
            ],
            "correct_index": 1,
        },
    ],
    "Leadership & Team Management": [
        {
            "question": "Gaya kepemimpinan yang mendelegasikan tugas dengan otonomi tinggi disebut?",
            "choices": [
                "Autocratic",
                "Democratic",
                "Laissez-faire",
                "Transactional"
            ],
            "correct_index": 2,
        },
        {
            "question": "Komunikasi efektif dalam tim membutuhkan:",
            "choices": [
                "Hanya berbicara",
                "Mendengarkan aktif dan feedback dua arah",
                "Menghindari pertanyaan",
                "Email saja"
            ],
            "correct_index": 1,
        },
        {
            "question": "Saat ada konflik tim, leader sebaiknya:",
            "choices": [
                "Mengabaikan",
                "Memihak salah satu",
                "Memfasilitasi dialog dan mencari solusi win-win",
                "Memecat semua yang konflik"
            ],
            "correct_index": 2,
        },
        {
            "question": "SMART goals adalah singkatan dari:",
            "choices": [
                "Strict, Measured, Active, Reviewed, Tested",
                "Specific, Measurable, Achievable, Relevant, Time-bound",
                "Simple, Modern, Affordable, Real, Tactical",
                "Strategic, Manageable, Aligned, Robust, Trusted"
            ],
            "correct_index": 1,
        },
        {
            "question": "Cara terbaik memotivasi tim adalah:",
            "choices": [
                "Hukuman keras saja",
                "Pengakuan, pengembangan, dan target yang jelas",
                "Uang berlebihan tanpa target",
                "Tidak peduli motivasi"
            ],
            "correct_index": 1,
        },
    ],
    "Pengoperasian Mesin Jahit Industrial": [
        {
            "question": "Sebelum menjalankan mesin jahit industrial, hal pertama yang harus dilakukan?",
            "choices": [
                "Langsung pakai",
                "Cek kebersihan, oli, dan tegangan benang",
                "Mengangkat mesin",
                "Membuka casing mesin"
            ],
            "correct_index": 1,
        },
        {
            "question": "Pelumasan mesin jahit industrial idealnya dilakukan:",
            "choices": [
                "Sebulan sekali",
                "Setiap hari sebelum dipakai",
                "Tidak perlu",
                "Setahun sekali"
            ],
            "correct_index": 1,
        },
        {
            "question": "Penyebab umum benang sering putus saat menjahit?",
            "choices": [
                "Mesin baru",
                "Tegangan benang terlalu tinggi atau jarum tumpul",
                "Operator lelah",
                "Tidak ada listrik"
            ],
            "correct_index": 1,
        },
        {
            "question": "Jarum mesin jahit harus diganti:",
            "choices": [
                "Setelah tumpul atau bengkok",
                "Setiap 5 tahun",
                "Tidak pernah",
                "Hanya saat patah"
            ],
            "correct_index": 0,
        },
        {
            "question": "Posisi tangan operator yang benar saat menjahit:",
            "choices": [
                "Di atas jarum langsung",
                "Memandu kain dengan tangan di samping presser foot, bukan di bawah jarum",
                "Memegang jarum",
                "Tidak menyentuh kain"
            ],
            "correct_index": 1,
        },
    ],
    "Product Knowledge: Bahan & Tekstil": [
        {
            "question": "Serat alami yang berasal dari tumbuhan adalah:",
            "choices": [
                "Wool",
                "Sutra",
                "Katun",
                "Polyester"
            ],
            "correct_index": 2,
        },
        {
            "question": "Polyester termasuk jenis serat:",
            "choices": [
                "Alami",
                "Sintetis",
                "Mineral",
                "Hewani"
            ],
            "correct_index": 1,
        },
        {
            "question": "Kain dengan ketahanan tinggi terhadap kusut umumnya?",
            "choices": [
                "Katun murni",
                "Polyester atau blended polyester",
                "Linen murni",
                "Wool ringan"
            ],
            "correct_index": 1,
        },
        {
            "question": "Simbol setrika dengan satu titik artinya?",
            "choices": [
                "Suhu tinggi",
                "Suhu rendah",
                "Tidak boleh disetrika",
                "Setrika uap"
            ],
            "correct_index": 1,
        },
        {
            "question": "Manfaat utama kain blended (campuran serat alami + sintetis):",
            "choices": [
                "Lebih murah tanpa keunggulan",
                "Gabungan kenyamanan + ketahanan",
                "Selalu hanya untuk pakaian formal",
                "Tidak ada manfaat"
            ],
            "correct_index": 1,
        },
    ],
}


async def main():
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'garment_erp')
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    print(f"Connecting to DB: {db_name}")
    
    # Get all quiz materials
    quiz_materials = await db.dewi_lms_materials.find({"type": "quiz"}).to_list(50)
    print(f"Found {len(quiz_materials)} quiz materials")
    
    updated = 0
    for quiz in quiz_materials:
        course_id = quiz["course_id"]
        course = await db.dewi_lms_courses.find_one({"course_id": course_id})
        if not course:
            print(f"  ! Course not found for quiz {quiz['material_id']}")
            continue
        
        course_title = course.get("title", "")
        questions = QUIZ_BANK.get(course_title)
        if not questions:
            print(f"  ! No quiz bank for '{course_title}'")
            continue
        
        await db.dewi_lms_materials.update_one(
            {"material_id": quiz["material_id"]},
            {"$set": {
                "questions": questions,
                "pass_score": 70,
            }}
        )
        updated += 1
        print(f"  ✓ Updated quiz '{quiz['title']}' with {len(questions)} questions")
    
    print(f"\nTotal updated: {updated}/{len(quiz_materials)}")
    
    # Also ensure we have at least 1 assignment material per course
    print("\n=== Adding sample assignment material per course ===")
    courses = await db.dewi_lms_courses.find({"status": "active"}).to_list(20)
    for course in courses:
        course_id = course["course_id"]
        # Check if assignment exists
        existing_assign = await db.dewi_lms_materials.find_one({
            "course_id": course_id,
            "type": "assignment"
        })
        if existing_assign:
            print(f"  - Assignment exists for '{course.get('title')}'")
            continue
        
        # Add an assignment material at end
        import uuid
        from datetime import datetime, timezone
        
        # Find max order
        materials = await db.dewi_lms_materials.find({"course_id": course_id}).to_list(50)
        max_order = max([m.get("order", 0) for m in materials], default=0)
        
        assignment = {
            "material_id": str(uuid.uuid4()),
            "course_id": course_id,
            "title": f"Tugas Akhir: {course.get('title')}",
            "type": "assignment",
            "content": f"Tuliskan ringkasan 200 kata tentang materi '{course.get('title')}' dan bagaimana Anda akan menerapkannya di pekerjaan sehari-hari.",
            "description": "Submit tugas dalam bentuk text, link Google Doc, atau upload file (PDF/DOCX).",
            "duration_minutes": 30,
            "order": max_order + 1,
            "max_score": 100,
            "is_mandatory": True,
            "created_at": datetime.now(timezone.utc),
        }
        await db.dewi_lms_materials.insert_one(assignment)
        
        # Update course materials list
        await db.dewi_lms_courses.update_one(
            {"course_id": course_id},
            {"$push": {"materials": assignment["material_id"]}}
        )
        print(f"  ✓ Added assignment to '{course.get('title')}'")
    
    print("\nDone!")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
