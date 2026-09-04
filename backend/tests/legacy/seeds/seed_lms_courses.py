"""
Seed Sample Courses for LMS Student Testing
Portal Kolaborasi Phase 2
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import uuid

MONGO_URL = "mongodb://localhost:27017/garment_erp"

def sid():
    return str(uuid.uuid4())

def now_utc():
    return datetime.now(timezone.utc)

SAMPLE_COURSES = [
    {
        "title": "Keselamatan Kerja & K3 2024",
        "description": "Pelatihan komprehensif tentang keselamatan kerja, penggunaan APD, prosedur darurat, dan standar K3 di industri garmen.",
        "category": "Compliance",
        "level": "Beginner",
        "duration_hours": 8,
        "instructor": "Tim HR - Safety Officer",
        "tags": ["K3", "Safety", "APD", "Compliance"],
        "pass_score": 75,
        "status": "active",
        "materials": [
            {
                "title": "Pengenalan K3 di Industri Garmen",
                "type": "video",
                "content": "https://www.youtube.com/embed/dQw4w9WgXcQ",
                "duration_minutes": 15,
                "order": 1,
                "description": "Video pengenalan tentang pentingnya K3 dan peraturan di lingkungan kerja garmen.",
            },
            {
                "title": "Penggunaan Alat Pelindung Diri (APD)",
                "type": "text",
                "content": "<h2>Jenis-jenis APD</h2><p>1. Masker debu untuk melindungi pernapasan...</p><p>2. Sarung tangan untuk melindungi tangan dari benda tajam...</p>",
                "duration_minutes": 10,
                "order": 2,
            },
            {
                "title": "Prosedur Darurat & Evakuasi",
                "type": "pdf",
                "content": "/samples/emergency-procedures.pdf",
                "duration_minutes": 20,
                "order": 3,
            },
            {
                "title": "Quiz: Keselamatan Kerja",
                "type": "quiz",
                "content": "",
                "duration_minutes": 10,
                "order": 4,
                "max_score": 100,
            },
        ]
    },
    {
        "title": "Dasar-Dasar Quality Control (QC)",
        "description": "Pelajari teknik inspeksi kualitas produk garmen, identifikasi defect, dan standar kualitas industri.",
        "category": "Technical Skills",
        "level": "Beginner",
        "duration_hours": 6,
        "instructor": "Supervisor QC",
        "tags": ["QC", "Quality", "Inspection", "Defect"],
        "pass_score": 80,
        "status": "active",
        "materials": [
            {
                "title": "Pengenalan Quality Control",
                "type": "video",
                "content": "https://www.youtube.com/embed/dQw4w9WgXcQ",
                "duration_minutes": 12,
                "order": 1,
            },
            {
                "title": "Jenis-Jenis Defect Umum",
                "type": "text",
                "content": "<h2>Defect pada Garmen</h2><ul><li>Jahitan tidak rapi</li><li>Noda pada kain</li><li>Ukuran tidak sesuai</li></ul>",
                "duration_minutes": 15,
                "order": 2,
            },
            {
                "title": "Teknik Inspeksi Visual",
                "type": "video",
                "content": "https://www.youtube.com/embed/dQw4w9WgXcQ",
                "duration_minutes": 18,
                "order": 3,
            },
            {
                "title": "Assignment: Identifikasi Defect",
                "type": "assignment",
                "content": "Upload foto produk dengan defect yang Anda temukan dan jelaskan jenis defect serta cara memperbaikinya.",
                "duration_minutes": 30,
                "order": 4,
                "max_score": 100,
            },
        ]
    },
    {
        "title": "Leadership & Team Management",
        "description": "Kembangkan kemampuan kepemimpinan, komunikasi efektif, dan manajemen tim untuk supervisor dan manager.",
        "category": "Soft Skills",
        "level": "Intermediate",
        "duration_hours": 10,
        "instructor": "HR Manager",
        "tags": ["Leadership", "Management", "Communication", "Team"],
        "pass_score": 70,
        "status": "active",
        "materials": [
            {
                "title": "Prinsip-Prinsip Kepemimpinan",
                "type": "text",
                "content": "<h2>5 Prinsip Kepemimpinan Efektif</h2><ol><li>Lead by example</li><li>Komunikasi terbuka</li><li>Empati</li><li>Decisive decision making</li><li>Continuous learning</li></ol>",
                "duration_minutes": 20,
                "order": 1,
            },
            {
                "title": "Komunikasi Efektif dalam Tim",
                "type": "video",
                "content": "https://www.youtube.com/embed/dQw4w9WgXcQ",
                "duration_minutes": 25,
                "order": 2,
            },
            {
                "title": "Mengelola Konflik & Problem Solving",
                "type": "video",
                "content": "https://www.youtube.com/embed/dQw4w9WgXcQ",
                "duration_minutes": 30,
                "order": 3,
            },
            {
                "title": "Quiz: Leadership Assessment",
                "type": "quiz",
                "content": "",
                "duration_minutes": 15,
                "order": 4,
                "max_score": 100,
            },
        ]
    },
    {
        "title": "Pengoperasian Mesin Jahit Industrial",
        "description": "Pelatihan praktis untuk operator mesin jahit: setup, maintenance, troubleshooting, dan safety procedures.",
        "category": "Technical Skills",
        "level": "Beginner",
        "duration_hours": 12,
        "instructor": "Supervisor Produksi",
        "tags": ["Sewing", "Machine", "Production", "Operator"],
        "pass_score": 75,
        "status": "active",
        "materials": [
            {
                "title": "Mengenal Mesin Jahit Industrial",
                "type": "video",
                "content": "https://www.youtube.com/embed/dQw4w9WgXcQ",
                "duration_minutes": 15,
                "order": 1,
            },
            {
                "title": "Setup & Threading",
                "type": "text",
                "content": "<h2>Langkah-langkah Threading</h2><p>1. Pastikan mesin dalam keadaan mati...</p>",
                "duration_minutes": 20,
                "order": 2,
            },
            {
                "title": "Maintenance & Troubleshooting",
                "type": "pdf",
                "content": "/samples/machine-maintenance.pdf",
                "duration_minutes": 25,
                "order": 3,
            },
            {
                "title": "Assignment: Video Praktik Jahit",
                "type": "assignment",
                "content": "Upload video Anda menjahit straight stitch dan zigzag stitch. Durasi minimum 2 menit.",
                "duration_minutes": 60,
                "order": 4,
                "max_score": 100,
            },
        ]
    },
    {
        "title": "Product Knowledge: Bahan & Tekstil",
        "description": "Pahami jenis-jenis kain, karakteristik serat, perawatan tekstil, dan penerapannya dalam produksi garmen.",
        "category": "Product Knowledge",
        "level": "Beginner",
        "duration_hours": 5,
        "instructor": "Tim RnD",
        "tags": ["Textile", "Fabric", "Material", "Product"],
        "pass_score": 70,
        "status": "active",
        "materials": [
            {
                "title": "Jenis-Jenis Serat Tekstil",
                "type": "text",
                "content": "<h2>Serat Alami vs Sintetis</h2><p>Serat alami: katun, wool, sutra...</p>",
                "duration_minutes": 15,
                "order": 1,
            },
            {
                "title": "Karakteristik Kain Umum",
                "type": "video",
                "content": "https://www.youtube.com/embed/dQw4w9WgXcQ",
                "duration_minutes": 20,
                "order": 2,
            },
            {
                "title": "Perawatan & Laundry Care",
                "type": "pdf",
                "content": "/samples/fabric-care.pdf",
                "duration_minutes": 12,
                "order": 3,
            },
            {
                "title": "Quiz: Product Knowledge",
                "type": "quiz",
                "content": "",
                "duration_minutes": 10,
                "order": 4,
                "max_score": 100,
            },
        ]
    },
]

async def seed_courses():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client.get_default_database()
    
    print("🌱 Starting LMS course seeding...")
    
    # Clear existing data (optional - comment out if you want to keep existing)
    # await db.dewi_lms_courses.delete_many({})
    # await db.dewi_lms_materials.delete_many({})
    # print("✅ Cleared existing courses and materials")
    
    for course_data in SAMPLE_COURSES:
        # Extract materials
        materials_data = course_data.pop("materials", [])
        
        # Create course
        course_id = sid()
        course = {
            "course_id": course_id,
            "title": course_data["title"],
            "description": course_data["description"],
            "category": course_data["category"],
            "thumbnail": "",
            "duration_hours": course_data["duration_hours"],
            "level": course_data["level"],
            "instructor": course_data["instructor"],
            "tags": course_data["tags"],
            "materials": [],  # Will store material_ids
            "quiz_count": sum(1 for m in materials_data if m["type"] == "quiz"),
            "status": course_data["status"],
            "enrollment_count": 0,
            "completion_count": 0,
            "pass_score": course_data["pass_score"],
            "certificate_template": "standard",
            "rating": 4.5,
            "review_count": 0,
            "created_by": "System Seed",
            "created_at": now_utc(),
            "updated_at": now_utc(),
        }
        
        await db.dewi_lms_courses.insert_one(course)
        print(f"✅ Created course: {course['title']}")
        
        # Create materials
        material_ids = []
        for mat_data in materials_data:
            material_id = sid()
            material_ids.append(material_id)
            
            material = {
                "material_id": material_id,
                "course_id": course_id,
                "title": mat_data["title"],
                "type": mat_data["type"],
                "content": mat_data.get("content", ""),
                "description": mat_data.get("description", ""),
                "duration_minutes": mat_data.get("duration_minutes", 0),
                "order": mat_data["order"],
                "max_score": mat_data.get("max_score", 0),
                "is_mandatory": True,
                "created_at": now_utc(),
            }
            
            await db.dewi_lms_materials.insert_one(material)
            print(f"  ✅ Created material: {material['title']} ({material['type']})")
        
        # Update course with material IDs
        await db.dewi_lms_courses.update_one(
            {"course_id": course_id},
            {"$set": {"materials": material_ids}}
        )
    
    total_courses = await db.dewi_lms_courses.count_documents({})
    total_materials = await db.dewi_lms_materials.count_documents({})
    
    print("\n🎉 Seeding complete!")
    print(f"📚 Total courses: {total_courses}")
    print(f"📖 Total materials: {total_materials}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(seed_courses())
