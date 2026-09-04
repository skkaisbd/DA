"""
Announcement Board Routes
Endpoint untuk mengelola pengumuman yang tampil di Portal Selector
CMS management ada di Portal HR
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from database import get_db
from auth import require_auth
import uuid

router = APIRouter(prefix="/api/announcements", tags=["announcements"])

# ─── MODELS ──────────────────────────────────────────────────────────────────

class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    type: str = Field(default="info")  # info, warning, success, urgent
    priority: int = Field(default=0, ge=0, le=10)  # 0=normal, 10=highest
    target_portals: List[str] = Field(default_factory=lambda: ["all"])  # ["all"] atau ["production", "hr", ...]
    is_active: bool = Field(default=True)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    created_by: Optional[str] = None

class AnnouncementUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[int] = None
    target_portals: Optional[List[str]] = None
    is_active: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class AnnouncementResponse(BaseModel):
    id: str
    title: str
    content: str
    type: str
    priority: int
    target_portals: List[str]
    is_active: bool
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

# ─── ROUTES ──────────────────────────────────────────────────────────────────

@router.get("/active", response_model=List[AnnouncementResponse])
async def get_active_announcements(
    request: Request,
    portal: Optional[str] = Query(None, description="Filter by portal (optional)"),
    db=Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    """
    Get active announcements for display in Portal Selector or specific portal.
    Filters by:
    - is_active = true
    - current date within start_date and end_date (if set)
    - target_portals matches (if portal param provided)
    """
    now = datetime.now(timezone.utc)
    
    query = {
        "is_active": True,
    }
    
    # Date range filter
    date_filter = {
        "$or": [
            {"start_date": None, "end_date": None},  # No date restriction
            {"start_date": {"$lte": now}, "end_date": None},  # Started, no end
            {"start_date": None, "end_date": {"$gte": now}},  # Not started, ends in future
            {"start_date": {"$lte": now}, "end_date": {"$gte": now}},  # Active period
        ]
    }
    
    announcements = await db.announcements.find({
        **query,
        **date_filter
    }).sort("priority", -1).to_list(length=100)
    
    # Filter by portal if specified
    if portal:
        announcements = [
            a for a in announcements 
            if "all" in a.get("target_portals", ["all"]) or portal in a.get("target_portals", [])
        ]
    
    # Enrich with creator name
    for announcement in announcements:
        if announcement.get("created_by"):
            creator = await db.rahaza_employees.find_one({"id": announcement["created_by"]})
            announcement["created_by_name"] = creator.get("name") if creator else None
    
    return announcements


@router.get("/all", response_model=List[AnnouncementResponse])
async def get_all_announcements(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    db=Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    """
    Get all announcements (for HR CMS management)
    Requires HR role
    """
    # Check HR permission
    if current_user.get("role") not in ["superadmin", "admin", "owner", "hr", "hr_manager", "staff_hr"]:
        raise HTTPException(status_code=403, detail="Only HR staff can access announcement management")
    
    query = {}
    if is_active is not None:
        query["is_active"] = is_active
    
    announcements = await db.announcements.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
    
    # Enrich with creator name
    for announcement in announcements:
        if announcement.get("created_by"):
            creator = await db.rahaza_employees.find_one({"id": announcement["created_by"]})
            announcement["created_by_name"] = creator.get("name") if creator else None
    
    return announcements


@router.get("/{announcement_id}", response_model=AnnouncementResponse)
async def get_announcement(
    request: Request,
    announcement_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    """Get single announcement by ID"""
    announcement = await db.announcements.find_one({"id": announcement_id}, {"_id": 0})
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    # Enrich with creator name
    if announcement.get("created_by"):
        creator = await db.rahaza_employees.find_one({"id": announcement["created_by"]})
        announcement["created_by_name"] = creator.get("name") if creator else None
    
    return announcement


@router.post("/", response_model=AnnouncementResponse, status_code=201)
async def create_announcement(
    request: Request,
    data: AnnouncementCreate,
    db=Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    """
    Create new announcement
    Requires HR role
    """
    # Check HR permission
    if current_user.get("role") not in ["superadmin", "admin", "owner", "hr", "hr_manager", "staff_hr"]:
        raise HTTPException(status_code=403, detail="Only HR staff can create announcements")
    
    announcement_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    announcement_doc = {
        "id": announcement_id,
        "title": data.title,
        "content": data.content,
        "type": data.type,
        "priority": data.priority,
        "target_portals": data.target_portals,
        "is_active": data.is_active,
        "start_date": data.start_date,
        "end_date": data.end_date,
        "created_by": (current_user.get("employee_id") or current_user.get("id")
                       or current_user.get("email") or "system"),
        "created_at": now,
        "updated_at": None,
    }
    
    await db.announcements.insert_one(dict(announcement_doc))
    
    # Enrich response with creator name
    creator = await db.rahaza_employees.find_one({"id": current_user.get("employee_id")})
    announcement_doc["created_by_name"] = creator.get("name") if creator else None
    
    return announcement_doc


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(
    request: Request,
    announcement_id: str,
    data: AnnouncementUpdate,
    db=Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    """
    Update announcement
    Requires HR role
    """
    # Check HR permission
    if current_user.get("role") not in ["superadmin", "admin", "owner", "hr", "hr_manager", "staff_hr"]:
        raise HTTPException(status_code=403, detail="Only HR staff can update announcements")
    
    existing = await db.announcements.find_one({"id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    update_data = {k: v for k, v in data.dict(exclude_unset=True).items() if v is not None}
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc)
        await db.announcements.update_one(
            {"id": announcement_id},
            {"$set": update_data}
        )
    
    updated = await db.announcements.find_one({"id": announcement_id}, {"_id": 0})
    
    # Enrich with creator name
    if updated.get("created_by"):
        creator = await db.rahaza_employees.find_one({"id": updated["created_by"]})
        updated["created_by_name"] = creator.get("name") if creator else None
    
    return updated


@router.delete("/{announcement_id}", status_code=204)
async def delete_announcement(
    request: Request,
    announcement_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    """
    Delete announcement (soft delete by setting is_active=false)
    Requires HR role
    """
    # Check HR permission
    if current_user.get("role") not in ["superadmin", "admin", "owner", "hr", "hr_manager", "staff_hr"]:
        raise HTTPException(status_code=403, detail="Only HR staff can delete announcements")
    
    result = await db.announcements.update_one(
        {"id": announcement_id},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    return None


@router.post("/{announcement_id}/toggle", response_model=AnnouncementResponse)
async def toggle_announcement_status(
    request: Request,
    announcement_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    """
    Toggle announcement active status
    Requires HR role
    """
    # Check HR permission
    if current_user.get("role") not in ["superadmin", "admin", "owner", "hr", "hr_manager", "staff_hr"]:
        raise HTTPException(status_code=403, detail="Only HR staff can toggle announcements")
    
    existing = await db.announcements.find_one({"id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    new_status = not existing.get("is_active", True)
    await db.announcements.update_one(
        {"id": announcement_id},
        {"$set": {"is_active": new_status, "updated_at": datetime.now(timezone.utc)}}
    )
    
    updated = await db.announcements.find_one({"id": announcement_id}, {"_id": 0})
    
    # Enrich with creator name
    if updated.get("created_by"):
        creator = await db.rahaza_employees.find_one({"id": updated["created_by"]})
        updated["created_by_name"] = creator.get("name") if creator else None
    
    return updated
