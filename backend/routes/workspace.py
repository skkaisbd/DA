"""
Workspace Portal — Backend Routes
CV. Dewi Aditya ERP

Endpoints:
  POST   /api/workspace/documents                       — Create document
  GET    /api/workspace/documents                       — List owned + shared
  GET    /api/workspace/documents/{id}                  — Get single doc
  PUT    /api/workspace/documents/{id}                  — Update content/name
  DELETE /api/workspace/documents/{id}                  — Soft delete (owner only)
  POST   /api/workspace/documents/{id}/share            — Share / update access
  DELETE /api/workspace/documents/{id}/share/{user_id} — Revoke share
  POST   /api/workspace/documents/import-excel          — Upload & parse Excel
  GET    /api/workspace/documents/{id}/export-excel     — Download as Excel
  POST   /api/workspace/documents/import-from-module    — Import from Assets/Procurement
"""

from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from database import get_db
from utils.counters import next_counter
from auth import require_auth
import uuid
import datetime
import re
import io
import pandas as pd

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

# ─── Helpers ─────────────────────────────────────────────────────────────

def _uid(): return str(uuid.uuid4())
def _now(): return datetime.datetime.now(datetime.timezone.utc)


async def _next_version_num(db, doc_id: str) -> int:
    """RC-5 fix: atomic per-document version counter (was count_documents()+1 -> race).

    Lazy-init seeds the counter to the current number of versions so it does not
    collide with historical count-based version numbers already stored."""
    key = f"autonum:workspace_versions:version_num:{doc_id}"
    if await db.counters.find_one({"_id": key}, {"_id": 1}) is None:
        existing = await db.workspace_versions.count_documents({"document_id": doc_id})
        await db.counters.update_one(
            {"_id": key},
            {"$setOnInsert": {"seq": existing, "namespace": "autonum"}},
            upsert=True,
        )
    return await next_counter(db, key, namespace="autonum")

def _ser(doc: dict) -> dict:
    """Serialize MongoDB doc (ObjectId + datetime → str)."""
    if doc is None:
        return None
    out = {}
    for k, v in doc.items():
        if k == '_id':
            continue
        if isinstance(v, datetime.datetime):
            out[k] = v.isoformat()
        elif isinstance(v, dict):
            out[k] = _ser(v)
        elif isinstance(v, list):
            out[k] = [_ser(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out

def _get_access_level(doc: dict, user_id: str) -> str:
    """Returns 'owner', 'admin', 'edit', or 'view'."""
    if doc.get('owner_id') == user_id:
        return 'owner'
    shared = doc.get('permissions', {}).get('shared_with', [])
    perm = next((s for s in shared if s.get('user_id') == user_id), None)
    return perm['access'] if perm else 'view'


# ─── CRUD ────────────────────────────────────────────────────────────────

@router.post("/documents")
async def create_document(request: Request):
    """Create a new spreadsheet document."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    name = (body.get('name') or '').strip()
    if not name:
        raise HTTPException(400, "name diperlukan")

    doc_type = body.get('type', 'spreadsheet')
    columns = body.get('columns') or [
        {"key": "col_1", "name": "Kolom 1", "type": "text", "editable": True, "width": 180},
        {"key": "col_2", "name": "Kolom 2", "type": "text", "editable": True, "width": 180},
    ]
    rows = body.get('rows') or []

    doc = {
        "id": _uid(),
        "type": doc_type,
        "name": name,
        "description": body.get('description', ''),
        "owner_id": user["id"],
        "owner_name": user.get("name", ""),
        "content": {"columns": columns, "rows": rows},
        "permissions": {"public": False, "shared_with": []},
        "metadata": {
            "source_module": body.get('source_module'),
            "row_count": len(rows),
            "column_count": len(columns),
        },
        "created_at": _now(),
        "updated_at": _now(),
        "last_accessed_at": _now(),
        "is_deleted": False,
    }
    await db.workspace_documents.insert_one(doc)
    result = _ser({k: v for k, v in doc.items() if k != '_id'})
    result['access_level'] = 'owner'
    result['is_owner'] = True
    return result


@router.get("/documents")
async def list_documents(request: Request, include_shared: bool = True):
    """List user's documents (owned + shared), each annotated with access_level."""
    user = await require_auth(request)
    db = get_db()

    owned = await db.workspace_documents.find(
        {"owner_id": user["id"], "is_deleted": False},
        {"_id": 0}
    ).sort("updated_at", -1).limit(100).to_list(100)

    shared = []
    if include_shared:
        shared = await db.workspace_documents.find(
            {
                "permissions.shared_with": {"$elemMatch": {"user_id": user["id"]}},
                "is_deleted": False,
            },
            {"_id": 0}
        ).sort("updated_at", -1).limit(50).to_list(50)

    def _annotate(docs, is_owner: bool):
        result = []
        for d in docs:
            s = _ser(d)
            if is_owner:
                s['access_level'] = 'owner'
                s['is_owner'] = True
            else:
                level = _get_access_level(d, user['id'])
                s['access_level'] = level
                s['is_owner'] = False
            result.append(s)
        return result

    return {
        "owned": _annotate(owned, True),
        "shared": _annotate(shared, False),
    }


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str, request: Request):
    """Get single document with permission check."""
    user = await require_auth(request)
    db = get_db()

    doc = await db.workspace_documents.find_one({"id": doc_id, "is_deleted": False}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Dokumen tidak ditemukan")

    is_owner = doc["owner_id"] == user["id"]
    shared = doc.get("permissions", {}).get("shared_with", [])
    is_shared = any(s["user_id"] == user["id"] for s in shared)

    if not (is_owner or is_shared):
        raise HTTPException(403, "Akses ditolak")

    await db.workspace_documents.update_one(
        {"id": doc_id},
        {"$set": {"last_accessed_at": _now()}}
    )

    result = _ser(doc)
    level = _get_access_level(doc, user['id'])
    result['access_level'] = level
    result['is_owner'] = is_owner
    return result


@router.put("/documents/{doc_id}")
async def update_document(doc_id: str, request: Request):
    """Update document content or metadata (requires edit/owner)."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    doc = await db.workspace_documents.find_one({"id": doc_id, "is_deleted": False})
    if not doc:
        raise HTTPException(404, "Dokumen tidak ditemukan")

    level = _get_access_level(doc, user['id'])
    if level == 'view':
        raise HTTPException(403, "Tidak ada izin edit")

    update = {"updated_at": _now()}
    if "name" in body and body["name"].strip():
        update["name"] = body["name"].strip()
    if "description" in body:
        update["description"] = body["description"]
    if "content" in body:
        update["content"] = body["content"]
        if "rows" in body["content"]:
            update["metadata.row_count"] = len(body["content"]["rows"])
        if "columns" in body["content"]:
            update["metadata.column_count"] = len(body["content"]["columns"])

    await db.workspace_documents.update_one({"id": doc_id}, {"$set": update})
    return {"ok": True}


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, request: Request):
    """Soft delete document (owner only)."""
    user = await require_auth(request)
    db = get_db()

    doc = await db.workspace_documents.find_one({"id": doc_id})
    if not doc:
        raise HTTPException(404, "Dokumen tidak ditemukan")
    if doc["owner_id"] != user["id"]:
        raise HTTPException(403, "Hanya pemilik yang dapat menghapus")

    await db.workspace_documents.update_one(
        {"id": doc_id},
        {"$set": {"is_deleted": True, "updated_at": _now()}}
    )
    return {"ok": True}


# ─── Sharing & Permissions ────────────────────────────────────────────────

@router.post("/documents/{doc_id}/share")
async def share_document(doc_id: str, request: Request):
    """Share document or update existing share."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    target_user_id = body.get("user_id")
    access_level = body.get("access", "view")

    if not target_user_id:
        raise HTTPException(400, "user_id diperlukan")
    if access_level not in ["view", "edit", "admin"]:
        raise HTTPException(400, "access level tidak valid")

    doc = await db.workspace_documents.find_one({"id": doc_id, "is_deleted": False})
    if not doc:
        raise HTTPException(404, "Dokumen tidak ditemukan")

    level = _get_access_level(doc, user['id'])
    if level not in ('owner', 'admin'):
        raise HTTPException(403, "Tidak ada izin share")

    target = await db.users.find_one({"id": target_user_id})
    if not target:
        raise HTTPException(404, "User tidak ditemukan")

    shared = doc.get("permissions", {}).get("shared_with", [])
    existing = next((s for s in shared if s["user_id"] == target_user_id), None)

    if existing:
        await db.workspace_documents.update_one(
            {"id": doc_id, "permissions.shared_with.user_id": target_user_id},
            {"$set": {"permissions.shared_with.$.access": access_level, "updated_at": _now()}}
        )
    else:
        await db.workspace_documents.update_one(
            {"id": doc_id},
            {
                "$push": {
                    "permissions.shared_with": {
                        "user_id": target_user_id,
                        "user_name": target.get("name", ""),
                        "access": access_level,
                        "shared_at": _now(),
                    }
                },
                "$set": {"updated_at": _now()},
            }
        )
        # Record in workspace_shares collection
        await db.workspace_shares.insert_one({
            "id": _uid(),
            "document_id": doc_id,
            "shared_by": user["id"],
            "shared_with": target_user_id,
            "access_level": access_level,
            "shared_at": _now(),
        })

    return {"ok": True, "user_id": target_user_id, "access": access_level, "user_name": target.get("name", "")}


@router.delete("/documents/{doc_id}/share/{user_id}")
async def revoke_share(doc_id: str, user_id: str, request: Request):
    """Revoke share access (owner or admin)."""
    user = await require_auth(request)
    db = get_db()

    doc = await db.workspace_documents.find_one({"id": doc_id})
    if not doc:
        raise HTTPException(404, "Dokumen tidak ditemukan")

    level = _get_access_level(doc, user['id'])
    if level not in ('owner', 'admin'):
        raise HTTPException(403, "Tidak ada izin revoke")

    await db.workspace_documents.update_one(
        {"id": doc_id},
        {"$pull": {"permissions.shared_with": {"user_id": user_id}}, "$set": {"updated_at": _now()}}
    )
    return {"ok": True}


# ─── Import / Export Excel ────────────────────────────────────────────────

@router.post("/documents/import-excel")
async def import_excel(request: Request, file: UploadFile = File(...)):
    """Upload .xlsx / .xls and create a new spreadsheet document."""
    user = await require_auth(request)
    db = get_db()

    contents = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(contents), sheet_name=0)
    except Exception as e:
        raise HTTPException(400, f"Gagal membaca file Excel: {e}")

    df = df.fillna('')

    # Build columns
    columns = []
    for i, col in enumerate(df.columns):
        col_key = re.sub(r'[^a-z0-9_]', '_', str(col).lower().strip())[:30] or f'col_{i}'
        col_key = col_key.strip('_') or f'col_{i}'
        columns.append({
            "key": col_key,
            "name": str(col),
            "type": "number" if pd.api.types.is_numeric_dtype(df[col]) else "text",
            "editable": True,
            "width": 160,
        })

    # Build rows
    rows = []
    for idx, row in df.iterrows():
        r = {"id": f"row_{idx}"}
        for col_def, col_name in zip(columns, df.columns):
            val = row[col_name]
            if pd.isna(val) if not isinstance(val, str) else False:
                val = ''
            r[col_def["key"]] = val
        rows.append(r)

    doc_name = file.filename.rsplit('.', 1)[0] if file.filename else 'Import Excel'

    doc = {
        "id": _uid(),
        "type": "spreadsheet",
        "name": doc_name,
        "description": f"Diimport dari {file.filename}",
        "owner_id": user["id"],
        "owner_name": user.get("name", ""),
        "content": {"columns": columns, "rows": rows},
        "permissions": {"public": False, "shared_with": []},
        "metadata": {
            "source_module": "excel_import",
            "row_count": len(rows),
            "column_count": len(columns),
        },
        "created_at": _now(),
        "updated_at": _now(),
        "last_accessed_at": _now(),
        "is_deleted": False,
    }
    await db.workspace_documents.insert_one(doc)
    result = _ser({k: v for k, v in doc.items() if k != '_id'})
    result['access_level'] = 'owner'
    result['is_owner'] = True
    return result


@router.get("/documents/{doc_id}/export-excel")
async def export_excel(doc_id: str, request: Request):
    """Export spreadsheet as .xlsx download."""
    user = await require_auth(request)
    db = get_db()

    doc = await db.workspace_documents.find_one({"id": doc_id, "is_deleted": False}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Dokumen tidak ditemukan")

    level = _get_access_level(doc, user['id'])
    if level not in ('owner', 'admin', 'edit', 'view'):
        raise HTTPException(403, "Akses ditolak")

    content = doc.get("content", {})
    columns = content.get("columns", [])
    rows = content.get("rows", [])

    col_names = [c["name"] for c in columns]
    col_keys = [c["key"] for c in columns]

    data = []
    for row in rows:
        data.append([row.get(k, '') for k in col_keys])

    df = pd.DataFrame(data, columns=col_names)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    output.seek(0)

    safe_name = re.sub(r'[^\w\s-]', '', doc['name']).strip().replace(' ', '_')
    filename = f"{safe_name}.xlsx"

    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ─── Import from System Module ────────────────────────────────────────────

@router.post("/documents/import-from-module")
async def import_from_module(request: Request):
    """
    Import data dari modul sistem ke Workspace spreadsheet baru.
    Supported modules: assets, procurement
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    module = body.get('module', 'assets')  # 'assets' | 'procurement'
    filters = body.get('filters', {})
    selected_fields = body.get('fields', [])  # list of field keys
    doc_name = (body.get('name') or '').strip()

    if module == 'assets':
        query = {"is_deleted": {"$ne": True}}
        if filters.get('category_name'):
            query['category_name'] = filters['category_name']
        if filters.get('status'):
            query['status'] = filters['status']
        if filters.get('department'):
            query['department'] = filters['department']

        assets = await db.dewi_assets.find(query, {"_id": 0}).sort("asset_number", 1).limit(500).to_list(500)

        FIELD_MAP = {
            'asset_number':   ('Nomor Aset',      'text'),
            'name':           ('Nama',            'text'),
            'category_name':  ('Kategori',        'text'),
            'department':     ('Departemen',      'text'),
            'location':       ('Lokasi',          'text'),
            'brand':          ('Merek',           'text'),
            'model':          ('Model',           'text'),
            'serial_number':  ('Serial Number',   'text'),
            'purchase_date':  ('Tgl Perolehan',   'text'),
            'purchase_cost':  ('Harga Beli',      'number'),
            'residual_value': ('Nilai Sisa',      'number'),
            'status':         ('Status',          'text'),
            'assigned_to_name': ('Ditugaskan Ke', 'text'),
        }
        DEFAULT_FIELDS = ['asset_number', 'name', 'category_name', 'department', 'location', 'purchase_cost', 'status']

        if not selected_fields:
            selected_fields = DEFAULT_FIELDS

        columns = [
            {'key': f, 'name': FIELD_MAP[f][0], 'type': FIELD_MAP[f][1], 'editable': True, 'width': 160}
            for f in selected_fields if f in FIELD_MAP
        ]
        rows = []
        for a in assets:
            row = {'id': f'row_{a.get("id", _uid())}'}
            for f in selected_fields:
                if f in FIELD_MAP:
                    v = a.get(f, '')
                    row[f] = v if v is not None else ''
            rows.append(row)

        if not doc_name:
            doc_name = f'Import Aset - {datetime.date.today().strftime("%d %b %Y")}'
        source_module = 'assets'

    elif module == 'procurement':
        query = {}
        if filters.get('status'):
            query['status'] = filters['status']
        if filters.get('department'):
            query['department'] = filters['department']

        # RC-28: SSOT = dewi_procurement_requests (procurement_requests = phantom tanpa writer)
        prs = await db.dewi_procurement_requests.find(query, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)

        FIELD_MAP = {
            'request_number':     ('Nomor PR',       'text'),
            'title':              ('Judul',          'text'),
            'department':         ('Departemen',     'text'),
            'requested_by_name':  ('Peminta',        'text'),
            'priority':           ('Prioritas',      'text'),
            'total_estimated':    ('Total Est.',     'number'),
            'status':             ('Status',         'text'),
        }
        DEFAULT_FIELDS = ['request_number', 'title', 'department', 'requested_by_name', 'total_estimated', 'status']

        if not selected_fields:
            selected_fields = DEFAULT_FIELDS

        columns = [
            {'key': f, 'name': FIELD_MAP[f][0], 'type': FIELD_MAP[f][1], 'editable': True, 'width': 160}
            for f in selected_fields if f in FIELD_MAP
        ]
        rows = []
        for pr in prs:
            row = {'id': f'row_{pr.get("id", _uid())}'}
            for f in selected_fields:
                if f in FIELD_MAP:
                    v = pr.get(f, '')
                    row[f] = v if v is not None else ''
            rows.append(row)

        if not doc_name:
            doc_name = f'Import Pengadaan - {datetime.date.today().strftime("%d %b %Y")}'
        source_module = 'procurement'
    else:
        raise HTTPException(400, f"Module '{module}' tidak didukung")

    doc = {
        "id": _uid(),
        "type": "spreadsheet",
        "name": doc_name,
        "description": f"Diimport dari modul {source_module}",
        "owner_id": user["id"],
        "owner_name": user.get("name", ""),
        "content": {"columns": columns, "rows": rows},
        "permissions": {"public": False, "shared_with": []},
        "metadata": {
            "source_module": source_module,
            "row_count": len(rows),
            "column_count": len(columns),
        },
        "created_at": _now(),
        "updated_at": _now(),
        "last_accessed_at": _now(),
        "is_deleted": False,
    }
    await db.workspace_documents.insert_one(doc)
    result = _ser({k: v for k, v in doc.items() if k != '_id'})
    result['access_level'] = 'owner'
    result['is_owner'] = True
    result['imported_count'] = len(rows)
    return result



# ─── Excel Preview (Step 1 of 2-step import) ──────────────────────────────

@router.post("/documents/preview-excel")
async def preview_excel(request: Request, file: UploadFile = File(...)):
    """
    Parse Excel file and return column info + first 10 rows preview.
    Used before actual import so user can do column mapping.
    """
    await require_auth(request)

    contents = await file.read()
    try:
        xl = pd.ExcelFile(io.BytesIO(contents))
        sheet_names = xl.sheet_names
        df = xl.parse(sheet_names[0])
    except Exception as e:
        raise HTTPException(400, f"Gagal membaca file Excel: {e}")

    df = df.fillna('')
    df = df.replace({float('nan'): ''})

    # Build column suggestions
    columns = []
    for i, col in enumerate(df.columns):
        col_key = re.sub(r'[^a-z0-9_]', '_', str(col).lower().strip())[:30]
        col_key = col_key.strip('_') or f'col_{i}'
        col_type = "number" if pd.api.types.is_numeric_dtype(df[col]) else "text"
        columns.append({
            "original_name": str(col),
            "suggested_key": col_key,
            "suggested_name": str(col),
            "type": col_type,
            "include": True,
        })

    # Preview rows (first 10)
    preview_rows = []
    for idx, row in df.head(10).iterrows():
        r = {}
        for col in df.columns:
            v = row[col]
            if hasattr(v, 'item'):
                v = v.item()
            r[str(col)] = str(v) if v != '' else ''
        preview_rows.append(r)

    return {
        "file_name": file.filename,
        "sheet_names": sheet_names,
        "total_rows": len(df),
        "columns": columns,
        "preview_rows": preview_rows,
    }


@router.post("/documents/import-excel-mapped")
async def import_excel_mapped(request: Request):
    """
    Step 2: Import Excel with user-defined column mapping.
    Body: { file_data: base64, column_mapping: [...], doc_name: str }
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    import base64
    raw = body.get("file_data", "")
    if not raw:
        raise HTTPException(400, "file_data diperlukan")

    try:
        file_bytes = base64.b64decode(raw)
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0)
    except Exception as e:
        raise HTTPException(400, f"Gagal parse Excel: {e}")

    df = df.fillna('')
    mapping = body.get("column_mapping", [])  # list of { original_name, key, name, type, include }
    doc_name = (body.get("doc_name") or "Import Excel").strip()

    # Build columns from mapping
    columns = []
    col_map = {}  # original_name → { key, name, type }
    for m in mapping:
        if not m.get("include", True):
            continue
        key = (m.get("key") or re.sub(r'[^a-z0-9_]', '_', m["original_name"].lower())[:30]).strip('_') or f"col_{len(columns)}"
        col = {"key": key, "name": m.get("name") or m["original_name"], "type": m.get("type","text"), "editable": True, "width": 160}
        columns.append(col)
        col_map[m["original_name"]] = col

    if not columns:
        raise HTTPException(400, "Pilih minimal satu kolom")

    # Build rows
    rows = []
    for idx, row in df.iterrows():
        r = {"id": f"row_{idx}"}
        for orig, col in col_map.items():
            v = row.get(orig, '')
            if hasattr(v, 'item'):
                v = v.item()
            r[col["key"]] = str(v) if str(v) != 'nan' else ''
        rows.append(r)

    doc = {
        "id": _uid(),
        "type": "spreadsheet",
        "name": doc_name,
        "description": "Diimport dari Excel dengan column mapping",
        "owner_id": user["id"],
        "owner_name": user.get("name", ""),
        "content": {"columns": columns, "rows": rows},
        "permissions": {"public": False, "shared_with": []},
        "metadata": {
            "source_module": "excel_import_mapped",
            "row_count": len(rows),
            "column_count": len(columns),
        },
        "created_at": _now(),
        "updated_at": _now(),
        "last_accessed_at": _now(),
        "is_deleted": False,
    }
    await db.workspace_documents.insert_one(doc)
    result = _ser({k: v for k, v in doc.items() if k != '_id'})
    result['access_level'] = 'owner'
    result['is_owner'] = True
    return result


# ─── Version History ────────────────────────────────────────────────────────

@router.post("/documents/{doc_id}/versions")
async def save_version(doc_id: str, request: Request):
    """Save a manual version snapshot (called on manual save)."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    doc = await db.workspace_documents.find_one({"id": doc_id, "is_deleted": False}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Dokumen tidak ditemukan")

    level = _get_access_level(doc, user['id'])
    if level == 'view':
        raise HTTPException(403, "Tidak ada izin edit")

    # RC-5 fix: atomic race-safe version numbering (was count_documents()+1)
    vnum = await _next_version_num(db, doc_id)

    label = (body.get("label") or "").strip()
    if not label:
        label = f"Versi {vnum} — {_now().strftime('%d %b %Y %H:%M')}"

    version = {
        "id": _uid(),
        "document_id": doc_id,
        "version_num": vnum,
        "label": label,
        "content": body.get("content") or doc.get("content", {}),
        "saved_by_id": user["id"],
        "saved_by_name": user.get("name", ""),
        "saved_at": _now(),
    }
    await db.workspace_versions.insert_one(version)

    # Keep only last 20 versions
    all_versions = await db.workspace_versions.find(
        {"document_id": doc_id}, {"_id": 0, "id": 1, "saved_at": 1}
    ).sort("saved_at", 1).to_list(1000)

    if len(all_versions) > 20:
        old_ids = [v["id"] for v in all_versions[:-20]]
        await db.workspace_versions.delete_many({"id": {"$in": old_ids}})

    return _ser({k: v for k, v in version.items() if k != '_id'})


@router.get("/documents/{doc_id}/versions")
async def list_versions(doc_id: str, request: Request):
    """List version history for a document."""
    user = await require_auth(request)
    db = get_db()

    doc = await db.workspace_documents.find_one({"id": doc_id, "is_deleted": False})
    if not doc:
        raise HTTPException(404, "Dokumen tidak ditemukan")

    level = _get_access_level(doc, user['id'])
    if not level:
        raise HTTPException(403, "Akses ditolak")

    versions = await db.workspace_versions.find(
        {"document_id": doc_id}, {"_id": 0}
    ).sort("saved_at", -1).limit(20).to_list(20)

    return [_ser(v) for v in versions]


@router.post("/documents/{doc_id}/versions/{version_id}/restore")
async def restore_version(doc_id: str, version_id: str, request: Request):
    """Restore document content to a specific version snapshot."""
    user = await require_auth(request)
    db = get_db()

    doc = await db.workspace_documents.find_one({"id": doc_id, "is_deleted": False})
    if not doc:
        raise HTTPException(404, "Dokumen tidak ditemukan")

    level = _get_access_level(doc, user['id'])
    if level == 'view':
        raise HTTPException(403, "Tidak ada izin restore")

    version = await db.workspace_versions.find_one({"id": version_id, "document_id": doc_id})
    if not version:
        raise HTTPException(404, "Versi tidak ditemukan")

    content = version.get("content", {})
    await db.workspace_documents.update_one(
        {"id": doc_id},
        {"$set": {
            "content": content,
            "updated_at": _now(),
            "metadata.row_count": len(content.get("rows", [])),
            "metadata.column_count": len(content.get("columns", [])),
        }}
    )

    # Save a new version snapshot marking the restore
    await db.workspace_versions.insert_one({
        "id": _uid(),
        "document_id": doc_id,
        "version_num": await _next_version_num(db, doc_id),
        "label": f"Restore ke: {version.get('label', version_id)}",
        "content": content,
        "saved_by_id": user["id"],
        "saved_by_name": user.get("name", ""),
        "saved_at": _now(),
    })

    return {"ok": True, "restored_label": version.get("label")}



# ─── Index Setup ──────────────────────────────────────────────────────────

async def create_workspace_indexes(db):
    await db.workspace_documents.create_index("id", unique=True)
    await db.workspace_documents.create_index("owner_id")
    await db.workspace_documents.create_index("is_deleted")
    await db.workspace_documents.create_index("updated_at")
    await db.workspace_shares.create_index("document_id")
    await db.workspace_shares.create_index("shared_with")
