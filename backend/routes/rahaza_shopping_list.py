"""routes/rahaza_shopping_list.py — DAFTAR BELANJA MINGGUAN (sesi #33).

Semua hitungan ada di SSOT `core/shopping_list` (yang sendiri memakai SSOT
`core/stock_thresholds` untuk definisi "perlu beli" dan `core/stock_service`
untuk stok kanonik). Router ini hanya pintu + izin + jejak aktivitas.

Endpoint:
  GET  /api/rahaza/shopping-list/weekly     — daftar minggu ini + ringkasan jujur
  POST /api/rahaza/shopping-list/create-pr  — jadikan Permintaan Pengadaan (draft)
  GET  /api/rahaza/shopping-list/history    — PR yang lahir dari layar ini
"""
from fastapi import APIRouter, HTTPException, Query, Request

from auth import log_activity, require_auth, serialize_doc
from core import material_cost_history as mch
from core import shopping_list as sl
from database import get_db

router = APIRouter(prefix="/api/rahaza/shopping-list", tags=["rahaza-shopping-list"])


def _types(type_param: str) -> list | None:
    t = (type_param or "").strip().lower()
    if not t:
        return None
    return mch.TYPE_GROUPS.get(t) or [t]


@router.get("/weekly")
async def weekly_shopping_list(request: Request,
                              type: str = Query(""),
                              search: str = Query(""),
                              include_requested: bool = Query(True)):
    """Barang yang perlu dibeli minggu ini (basis ambang minimum / titik pesan ulang)."""
    await require_auth(request)
    data = await sl.weekly(get_db(), types=_types(type), search=search,
                           include_requested=include_requested)
    return serialize_doc({
        **data,
        "catatan": ("Kebutuhan dihitung HANYA dari ambang minimum / titik pesan ulang "
                    "(pilihan pemilik). Qty beli dibulatkan ke atas ke satuan beli dan "
                    "dinaikkan ke MOQ supplier bila ada. Barang tanpa harga tidak dihitung "
                    "ke perkiraan total."),
    })


@router.post("/create-pr")
async def create_pr_from_list(request: Request):
    """Jadikan baris terpilih sebagai **Permintaan Pengadaan** berstatus draft.

    Body: `{"material_ids": [...], "title"?, "notes"?, "needed_by"?, "priority"?}`

    PR dibuat lewat SSOT Portal Pengadaan (`routes.dewi_procurement.build_pr_doc`)
    supaya satuan, harga per satuan dasar, dan penomorannya SAMA dengan PR yang
    diketik manual — tidak ada jalur kedua yang bisa berbeda hasilnya.
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    ids = body.get("material_ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "Pilih minimal satu barang dari daftar belanja.")
    if len(ids) > 200:
        raise HTTPException(400, "Maksimal 200 barang per Permintaan Pengadaan.")

    prep = await sl.build_pr_items(db, ids)
    if not prep["items"]:
        reasons = "; ".join(f"{s.get('code') or s.get('material_id')}: {s['reason']}"
                            for s in prep["skipped"][:5]) or "tidak ada baris yang layak"
        raise HTTPException(400, f"Tidak ada barang yang bisa dimasukkan ke PR — {reasons}")

    wk = prep["week"]
    from routes.dewi_procurement import build_pr_doc
    doc = await build_pr_doc(db, user, {
        "title": (body.get("title") or "").strip()
                 or f"Belanja Mingguan {wk['iso']} ({wk['label']})",
        "description": (body.get("notes") or "").strip()
                       or (f"Dibuat otomatis dari Daftar Belanja Mingguan {wk['iso']} "
                           f"berdasarkan ambang minimum stok."),
        "justification": "Stok menyentuh ambang minimum / titik pesan ulang.",
        "request_type": "consumable",
        "priority": body.get("priority") or "medium",
        "needed_by": body.get("needed_by") or None,
        "items": prep["items"],
    }, origin=sl.ORIGIN, origin_week=wk["iso"])
    await db[sl.PR_COLL].insert_one(dict(doc))
    await log_activity(user["id"], user.get("name", ""), "create",
                       "rahaza.shopping_list_pr",
                       f"{doc['request_number']} · {len(prep['items'])} barang")
    return serialize_doc({
        "request": {k: v for k, v in doc.items() if k != "_id"},
        "skipped": prep["skipped"],
        "week": wk["iso"],
        "pesan": (f"Permintaan Pengadaan {doc['request_number']} dibuat sebagai DRAFT "
                  f"({len(prep['items'])} barang). Buka Portal Pengadaan → Permintaan "
                  f"Pengadaan untuk mengirimnya ke persetujuan."),
    })


@router.get("/history")
async def shopping_list_history(request: Request, limit: int = Query(100, ge=1, le=500)):
    """Riwayat PR yang lahir dari Daftar Belanja Mingguan."""
    await require_auth(request)
    return serialize_doc(await sl.created_history(get_db(), limit=limit))
