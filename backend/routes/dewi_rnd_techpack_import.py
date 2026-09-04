"""
RnD Tech Pack — Excel Importer (DA "Data Techpack Ringkasan Produk V5").

Endpoints (shared prefix /api/dewi/rnd):
  POST /techpack/import/preview   (multipart: file)  → parse only, no DB writes
  POST /techpack/import/commit    (multipart: file)  → upsert styles + variants + tech packs

Idempotent by style_code (derived from SKU or product name). Re-importing updates
existing styles/tech packs and replaces prior excel-imported variants (source='excel_import').
Colors are resolved to the shared rahaza_colors master (unique codes) so the canonical
Variant/SKU SSOT stays consistent when the style is later promoted to production.
"""
from fastapi import UploadFile, File, Depends, HTTPException

from routes.dewi_rnd_shared import router, now_utc, sid, serialize
from database import get_db
from auth import require_auth
from utils.techpack_excel import parse_techpack_v5
from utils.variant_ssot import ensure_color
# F3/C3 (2026-08-07): importir menulis LANGSUNG ke DB (tidak lewat endpoint tech-packs),
# jadi normalisasinya harus dipanggil di sini juga — kalau tidak, tech pack hasil impor
# menyimpan `size_columns` sebagai daftar STRING dan `measurements.values` berkunci NAMA
# kolom, yaitu bentuk yang justru membuat nilai ukuran yatim saat kolom diganti nama.
from utils.rnd_techpack import normalize_size_columns, normalize_measurements


def _parse_or_400(content: bytes) -> dict:
    if not content:
        raise HTTPException(400, "File kosong / tidak terbaca.")
    try:
        return parse_techpack_v5(content)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Gagal membaca Excel Techpack: {e}")


@router.post("/techpack/import/preview")
async def techpack_import_preview(file: UploadFile = File(...), user: dict = Depends(require_auth)):
    """Parse Excel V5 dan kembalikan hasil (tanpa menyimpan) untuk direview user."""
    content = await file.read()
    res = _parse_or_400(content)
    return {
        "sheet": res["sheet"],
        "total": res["total"],
        "errors": res["errors"],
        "products": res["products"],
    }


@router.post("/techpack/import/commit")
async def techpack_import_commit(file: UploadFile = File(...), user: dict = Depends(require_auth)):
    """Parse + simpan: upsert Style + Varian (per warna) + Tech Pack (latest) per produk."""
    db = get_db()
    content = await file.read()
    res = _parse_or_400(content)

    summary = {
        "products": res["total"],
        "styles_created": 0,
        "styles_updated": 0,
        "variants": 0,
        "techpacks": 0,
        "colors_resolved": 0,
        "errors": list(res["errors"]),
        "items": [],
    }

    for p in res["products"]:
        try:
            fabric_type = ", ".join(f["name"] for f in p["fabrics"])
            style_fields = {
                "style_name": p["style_name"],
                "category": (p["category"] or "").strip(),
                "buyer": (p["buyer"] or "DA").strip(),
                "season": (p["season"] or "").strip(),
                "description": (p["description"] or "").strip(),
                "fabric_type": fabric_type,
                "rnd_type": "internal_product",
                "updated_at": now_utc(),
            }
            existing = await db.dewi_rnd_styles.find_one({"style_code": p["style_code"]})
            if existing:
                style_id = existing["id"]
                await db.dewi_rnd_styles.update_one({"id": style_id}, {"$set": style_fields})
                summary["styles_updated"] += 1
            else:
                style_id = sid()
                await db.dewi_rnd_styles.insert_one({
                    "id": style_id,
                    "style_code": p["style_code"],
                    "status": "draft",
                    "design_images": [],
                    "created_by": user["id"],
                    "created_by_name": user.get("name", ""),
                    "created_at": now_utc(),
                    **style_fields,
                })
                summary["styles_created"] += 1

            # ── Variants (one per color) — replace prior excel-imported ones (idempotent) ──
            await db.dewi_rnd_variants.delete_many({"style_id": style_id, "source": "excel_import"})
            color_list = p["colors"] or ["Default"]
            for cname in color_list:
                color = await ensure_color(db, name=cname)
                summary["colors_resolved"] += 1
                await db.dewi_rnd_variants.insert_one({
                    "id": sid(),
                    "style_id": style_id,
                    "style_code": p["style_code"],
                    "style_name": p["style_name"],
                    "color": (color or {}).get("name") or cname,
                    "color_code": (color or {}).get("code", ""),
                    "color_hex": (color or {}).get("hex", ""),
                    "sizes": p["sizes"],
                    "status": "draft",
                    "source": "excel_import",
                    "created_at": now_utc(),
                    "updated_at": now_utc(),
                })
                summary["variants"] += 1

            # ── Tech Pack (mark old latest as superseded, insert new latest) ──
            await db.dewi_rnd_tech_packs.update_many(
                {"style_id": style_id, "is_latest": True}, {"$set": {"is_latest": False}}
            )
            construction_notes = "\n".join(cp["description"] for cp in p["construction_points"])
            bom_items = [
                {"material": f["name"], "spec": f["role"], "qty": 0, "unit": "meter", "supplier": ""}
                for f in p["fabrics"]
            ]
            # F3/C3: Excel memberi kolom sebagai daftar STRING (STANDAR/JUMBO) dan nilai
            # measurement berkunci NAMA kolom. Dinormalkan di sini supaya hasil impor
            # langsung memakai `col_id` stabil — kalau tidak, nilai ukuran bisa yatim
            # begitu kolomnya diganti nama di layar.
            size_columns = normalize_size_columns(p["measurement_categories"])
            measurements, meas_stats = normalize_measurements(p["measurements"], size_columns)
            tp = {
                "id": sid(),
                "style_id": style_id,
                "style_code": p["style_code"],
                "style_name": p["style_name"],
                "version": "v1",
                "doc_type": "excel_import",
                "title": f"Techpack {p['style_name']} (Import Excel)",
                "description": (p["description"] or "").strip(),
                "bom_items": bom_items,
                "fabrics": p["fabrics"],                      # (c) main + combination
                "fabric_consumption": p["fabric_consumption"],  # (c) per-size + kombinasi
                "construction_points": p["construction_points"],  # (b) per-poin terstruktur
                "construction_notes": construction_notes,     # backward-compat (join)
                "stitch_type": "",
                "seam_allowance_mm": 10,
                "size_grading_notes": "",
                "base_size": (p["sizes"][0] if p["sizes"] else "M"),
                "size_range": p["size_raw"],
                # F3/C3: kolom ukuran memakai col_id STABIL, nilai measurement dikunci col_id
                # (bukan nama kolom) — sama seperti jalur POST/PUT /tech-packs.
                "size_columns": size_columns,
                "fit_categories": p.get("fit_categories", []),  # #2b: info fit (tanpa ubah SKU)
                "measurements": measurements,
                "measurements_stats": meas_stats,
                "status": "draft",
                "is_latest": True,
                "source": "excel_import",
                "approved_by": None,
                "approved_at": None,
                "created_by": user["id"],
                "created_by_name": user.get("name", ""),
                "created_at": now_utc(),
                "updated_at": now_utc(),
            }
            await db.dewi_rnd_tech_packs.insert_one(tp)
            summary["techpacks"] += 1
            summary["items"].append({
                "style_code": p["style_code"],
                "style_name": p["style_name"],
                "colors": len(color_list),
                "sizes": p["sizes"],
                "construction_points": len(p["construction_points"]),
                "fabrics": len(p["fabrics"]),
                "measurement_categories": p["measurement_categories"],
            })
        except Exception as e:  # noqa: BLE001
            summary["errors"].append({"row": p.get("row_start"), "name": p.get("style_name"), "error": str(e)})

    return serialize(summary)
