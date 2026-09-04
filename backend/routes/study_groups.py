"""
CV. Dewi Aditya ERP — Study Groups (Phase 3.8)
Portal Kolaborasi: Learning Module

Fitur social learning - study groups untuk kolaborasi peer-to-peer per course.

Collections:
  study_groups    — study group definitions with course linkage

Endpoints:
  GET    /api/collab/study-groups             — list my study groups
  POST   /api/collab/study-groups             — create study group (auto-creates channel + folder)
  GET    /api/collab/study-groups/{id}        — get study group detail
  POST   /api/collab/study-groups/{id}/members — add members (only enrolled students)
  DELETE /api/collab/study-groups/{id}/members/{uid} — remove member
  DELETE /api/collab/study-groups/{id}        — delete study group (creator only)
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/collab/study-groups", tags=["study-groups"])


def _uid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


def _ser(doc):
    """Serialize MongoDB doc (remove _id, convert datetime)"""
    if not doc:
        return doc
    doc = {k: v for k, v in doc.items() if k != '_id'}
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


# ─── Helper: Auto-create channel for study group ──────────────────────────────

async def _create_study_group_channel(db, group_id: str, group_name: str, course_id: str, members: list, creator_id: str):
    """Create a private channel for the study group."""
    try:
        channel_id = _uid()
        now = _now()
        
        channel_doc = {
            'id': channel_id,
            'name': f'sg-{group_name.lower().replace(" ", "-")[:30]}',
            'description': f'Study Group: {group_name}',
            'type': 'private',  # private channel for study group
            'members': list(set(members + [creator_id])),  # ensure creator included
            'created_by': creator_id,
            'created_by_name': 'Study Group System',
            'archived': False,
            'created_at': now,
            'updated_at': now,
            'last_message': None,
            'last_message_at': None,
            'metadata': {
                'study_group_id': group_id,
                'course_id': course_id,
            }
        }
        
        await db.comm_channels.insert_one(channel_doc)
        
        # Post welcome message
        welcome_msg = {
            'id': _uid(),
            'channel_id': channel_id,
            'conversation_id': None,
            'sender_id': 'system',
            'sender_name': 'Study Group System',
            'sender_email': '',
            'content': f'🎓 Selamat datang di *{group_name}*!\n\nIni adalah ruang kolaborasi untuk belajar bersama. Gunakan channel ini untuk diskusi dan workspace untuk berbagi dokumen.',
            'message_type': 'system',
            'file_url': None,
            'file_name': None,
            'file_size': None,
            'reply_to_id': None,
            'reply_to_preview': None,
            'reactions': {},
            'edited': False,
            'deleted': False,
            'created_at': now,
            'updated_at': now,
        }
        await db.comm_messages.insert_one(welcome_msg)
        
        logger.info(f"[StudyGroups] Created channel {channel_id} for group {group_id}")
        return channel_id
    except Exception as e:
        logger.error(f"[StudyGroups] Failed to create channel: {e}")
        return None


# ─── Helper: Auto-create shared folder in workspace ────────────────────────────

async def _create_study_group_folder(db, group_id: str, group_name: str, members: list, creator_id: str):
    """Create a shared folder in workspace for the study group."""
    try:
        folder_id = _uid()
        now = _now()
        
        # Create a "folder" document (or use workspace_documents with type='folder')
        folder_doc = {
            'id': folder_id,
            'title': f'{group_name} - Shared Documents',
            'type': 'folder',  # virtual folder type
            'owner_id': creator_id,
            'shared_with': members,
            'metadata': {
                'study_group_id': group_id,
            },
            'created_at': now,
            'updated_at': now,
        }
        
        await db.workspace_documents.insert_one(folder_doc)
        
        logger.info(f"[StudyGroups] Created folder {folder_id} for group {group_id}")
        return folder_id
    except Exception as e:
        logger.error(f"[StudyGroups] Failed to create folder: {e}")
        return None


# ─── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("")
async def list_my_study_groups(request: Request):
    """List all study groups where current user is a member."""
    user = await require_auth(request)
    db = get_db()
    uid = user["id"]
    
    # Find groups where user is member or creator
    groups = await db.study_groups.find(
        {"$or": [{"members": uid}, {"created_by": uid}]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    # Enrich with course info + member count + last activity
    result = []
    for grp in groups:
        grp_out = _ser(grp)
        
        # Get course info
        course = await db.dewi_lms_courses.find_one(
            {"course_id": grp["course_id"]},
            {"_id": 0, "title": 1, "thumbnail": 1}
        )
        grp_out["course"] = _ser(course) if course else None
        
        # Member count
        grp_out["member_count"] = len(grp.get("members", []))
        
        # Last activity from channel messages
        if grp.get("channel_id"):
            last_msg = await db.comm_messages.find_one(
                {"channel_id": grp["channel_id"]},
                {"_id": 0, "created_at": 1},
                sort=[("created_at", -1)]
            )
            grp_out["last_activity_at"] = _ser(last_msg)["created_at"] if last_msg else None
        else:
            grp_out["last_activity_at"] = None
        
        result.append(grp_out)
    
    return {"ok": True, "study_groups": result}


@router.post("")
async def create_study_group(request: Request):
    """
    Create a new study group.
    Body: {
        name: str,
        course_id: str,
        description: str (optional),
        member_ids: List[str] (optional - initial members to invite)
    }
    """
    user = await require_auth(request)
    db = get_db()
    uid = user["id"]
    
    body = await request.json()
    name = (body.get("name") or "").strip()
    course_id = body.get("course_id")
    description = (body.get("description") or "").strip()
    member_ids = body.get("member_ids", [])
    
    if not name:
        raise HTTPException(400, "Nama study group wajib diisi.")
    if not course_id:
        raise HTTPException(400, "Course ID wajib diisi.")
    
    # Check if course exists
    course = await db.dewi_lms_courses.find_one({"course_id": course_id})
    if not course:
        raise HTTPException(404, "Course tidak ditemukan.")
    
    # Check if creator is enrolled
    creator_enrollment = await db.dewi_lms_enrollments.find_one({
        "user_id": uid,
        "course_id": course_id,
    })
    if not creator_enrollment:
        raise HTTPException(403, "Anda harus terdaftar di course ini untuk membuat study group.")
    
    # Validate all invited members are enrolled in the same course
    if member_ids:
        enrolled_count = await db.dewi_lms_enrollments.count_documents({
            "user_id": {"$in": member_ids},
            "course_id": course_id,
        })
        if enrolled_count != len(member_ids):
            raise HTTPException(400, "Semua anggota harus terdaftar di course yang sama.")
    
    # Create study group document
    group_id = _uid()
    now = _now()
    
    # Include creator as member
    all_members = list(set([uid] + member_ids))
    
    group_doc = {
        "id": group_id,
        "name": name,
        "description": description,
        "course_id": course_id,
        "created_by": uid,
        "created_by_name": user.get("name", ""),
        "members": all_members,
        "channel_id": None,  # will be set after channel creation
        "folder_id": None,   # will be set after folder creation
        "created_at": now,
        "updated_at": now,
    }
    
    # Create channel
    channel_id = await _create_study_group_channel(db, group_id, name, course_id, all_members, uid)
    if channel_id:
        group_doc["channel_id"] = channel_id
    
    # Create shared folder
    folder_id = await _create_study_group_folder(db, group_id, name, all_members, uid)
    if folder_id:
        group_doc["folder_id"] = folder_id
    
    # Insert study group
    await db.study_groups.insert_one(group_doc)
    
    # Notify all members (except creator)
    try:
        from routes.notifications import create_notification
        for member_id in all_members:
            if member_id != uid:
                await create_notification(
                    db,
                    user_id=member_id,
                    notif_type="study_group",
                    title=f"Anda ditambahkan ke study group: {name}",
                    content=f'{user.get("name", "Seseorang")} menambahkan Anda ke study group "{name}" untuk course: {course.get("title", "")}.',
                    source_type="study_group",
                    source_id=group_id,
                    source_url=f"#/collab/learning/study-groups/{group_id}",
                    metadata={"course_id": course_id, "group_name": name}
                )
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    
    return {"ok": True, "study_group": _ser(group_doc)}


@router.get("/{group_id}")
async def get_study_group_detail(group_id: str, request: Request):
    """Get study group detail with enriched info."""
    user = await require_auth(request)
    db = get_db()
    uid = user["id"]
    
    group = await db.study_groups.find_one({"id": group_id}, {"_id": 0})
    if not group:
        raise HTTPException(404, "Study group tidak ditemukan.")
    
    # Check if user is member
    if uid not in group.get("members", []) and group["created_by"] != uid:
        raise HTTPException(403, "Anda bukan anggota study group ini.")
    
    group_out = _ser(group)
    
    # Get course info
    course = await db.dewi_lms_courses.find_one(
        {"course_id": group["course_id"]},
        {"_id": 0}
    )
    group_out["course"] = _ser(course) if course else None
    
    # Get member details
    member_ids = group.get("members", [])
    members = await db.users.find(
        {"id": {"$in": member_ids}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "foto_url": 1, "department": 1}
    ).to_list(len(member_ids))
    group_out["members_detail"] = [_ser(m) for m in members]
    
    # Get channel info (if exists)
    if group.get("channel_id"):
        channel = await db.comm_channels.find_one(
            {"id": group["channel_id"]},
            {"_id": 0}
        )
        group_out["channel"] = _ser(channel) if channel else None
    
    # Get folder info (if exists)
    if group.get("folder_id"):
        folder = await db.workspace_documents.find_one(
            {"id": group["folder_id"]},
            {"_id": 0}
        )
        group_out["folder"] = _ser(folder) if folder else None
    
    return {"ok": True, "study_group": group_out}


@router.post("/{group_id}/members")
async def add_study_group_members(group_id: str, request: Request):
    """
    Add members to study group (only enrolled students).
    Body: { member_ids: List[str] }
    """
    user = await require_auth(request)
    db = get_db()
    uid = user["id"]
    
    group = await db.study_groups.find_one({"id": group_id})
    if not group:
        raise HTTPException(404, "Study group tidak ditemukan.")
    
    # Only creator or existing members can add
    if group["created_by"] != uid and uid not in group.get("members", []):
        raise HTTPException(403, "Hanya pembuat atau anggota yang dapat menambahkan member baru.")
    
    body = await request.json()
    new_member_ids = body.get("member_ids", [])
    
    if not new_member_ids:
        raise HTTPException(400, "member_ids wajib diisi.")
    
    # Validate all new members are enrolled in the course
    course_id = group["course_id"]
    enrolled_count = await db.dewi_lms_enrollments.count_documents({
        "user_id": {"$in": new_member_ids},
        "course_id": course_id,
    })
    
    if enrolled_count != len(new_member_ids):
        raise HTTPException(400, "Semua anggota harus terdaftar di course yang sama.")
    
    # Add to study group
    await db.study_groups.update_one(
        {"id": group_id},
        {
            "$addToSet": {"members": {"$each": new_member_ids}},
            "$set": {"updated_at": _now()}
        }
    )
    
    # Add to channel
    if group.get("channel_id"):
        await db.comm_channels.update_one(
            {"id": group["channel_id"]},
            {"$addToSet": {"members": {"$each": new_member_ids}}}
        )
    
    # Add to shared folder
    if group.get("folder_id"):
        await db.workspace_documents.update_one(
            {"id": group["folder_id"]},
            {"$addToSet": {"shared_with": {"$each": new_member_ids}}}
        )
    
    # Notify new members
    try:
        from routes.notifications import create_notification
        for member_id in new_member_ids:
            await create_notification(
                db,
                user_id=member_id,
                notif_type="study_group",
                title=f"Anda ditambahkan ke study group: {group['name']}",
                content=f'{user.get("name", "Seseorang")} menambahkan Anda ke study group "{group["name"]}".',
                source_type="study_group",
                source_id=group_id,
                source_url=f"#/collab/learning/study-groups/{group_id}",
                metadata={"course_id": course_id, "group_name": group["name"]}
            )
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    
    return {"ok": True, "added": new_member_ids}


@router.delete("/{group_id}/members/{member_id}")
async def remove_study_group_member(group_id: str, member_id: str, request: Request):
    """Remove a member from study group. Creator can remove anyone, member can remove self."""
    user = await require_auth(request)
    db = get_db()
    uid = user["id"]
    
    group = await db.study_groups.find_one({"id": group_id})
    if not group:
        raise HTTPException(404, "Study group tidak ditemukan.")
    
    # Creator can remove anyone, member can only remove self
    is_creator = group["created_by"] == uid
    is_self_remove = member_id == uid
    
    if not (is_creator or is_self_remove):
        raise HTTPException(403, "Anda tidak diizinkan menghapus anggota ini.")
    
    # Remove from study group
    await db.study_groups.update_one(
        {"id": group_id},
        {
            "$pull": {"members": member_id},
            "$set": {"updated_at": _now()}
        }
    )
    
    # Remove from channel
    if group.get("channel_id"):
        await db.comm_channels.update_one(
            {"id": group["channel_id"]},
            {"$pull": {"members": member_id}}
        )
    
    # Remove from shared folder
    if group.get("folder_id"):
        await db.workspace_documents.update_one(
            {"id": group["folder_id"]},
            {"$pull": {"shared_with": member_id}}
        )
    
    return {"ok": True, "removed": member_id}


@router.delete("/{group_id}")
async def delete_study_group(group_id: str, request: Request):
    """Delete study group (creator only). Also deletes associated channel and folder."""
    user = await require_auth(request)
    db = get_db()
    uid = user["id"]
    
    group = await db.study_groups.find_one({"id": group_id})
    if not group:
        raise HTTPException(404, "Study group tidak ditemukan.")
    
    # Only creator can delete
    if group["created_by"] != uid:
        raise HTTPException(403, "Hanya pembuat study group yang dapat menghapus.")
    
    # Archive channel instead of deleting (to preserve message history)
    if group.get("channel_id"):
        await db.comm_channels.update_one(
            {"id": group["channel_id"]},
            {"$set": {"archived": True, "updated_at": _now()}}
        )
    
    # Delete shared folder (or mark as deleted)
    if group.get("folder_id"):
        await db.workspace_documents.delete_one({"id": group["folder_id"]})
    
    # Delete study group
    await db.study_groups.delete_one({"id": group_id})
    
    return {"ok": True, "deleted": group_id}


# ─── Init indexes ──────────────────────────────────────────────────────────────

async def create_study_group_indexes(db):
    """Create indexes for study_groups collection."""
    await db.study_groups.create_index([("members", 1), ("created_at", -1)])
    await db.study_groups.create_index([("course_id", 1)])
    await db.study_groups.create_index([("created_by", 1)])
    logger.info("[StudyGroups] Indexes created")
