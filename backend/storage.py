"""
Local filesystem storage module — PT. TRIYASA ERP DEMO
Provides put_object, get_object, delete_object, generate_storage_path, init_storage
using local /app/uploads directory as persistent storage.
"""
import uuid
import logging
from pathlib import Path
from datetime import datetime
from utils.waktu import now_wib

logger = logging.getLogger(__name__)

STORAGE_ROOT = Path("/app/uploads")


def init_storage():
    """Initialize storage directory."""
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    logger.info(f"Storage initialized at {STORAGE_ROOT}")


def generate_storage_path(entity_id: str, filename: str) -> str:
    """Generate a unique storage path for a file."""
    # Sanitize filename
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
    if not safe_filename:
        safe_filename = f"file_{uuid.uuid4().hex[:8]}"
    
    # Create path: entity_id/timestamp_filename
    timestamp = now_wib().strftime("%Y%m%d%H%M%S")
    return f"{entity_id}/{timestamp}_{safe_filename}"


def put_object(path: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
    """
    Store file data at the given path.
    Returns dict with 'url' key for the stored file.
    """
    full_path = STORAGE_ROOT / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(full_path, "wb") as f:
        f.write(data)
    
    logger.info(f"Stored file at {full_path} ({len(data)} bytes)")
    return {
        "url": f"/api/uploads/{path}",
        "path": path,
        "size": len(data),
        "content_type": content_type,
    }


def get_object(path: str) -> tuple:
    """
    Retrieve file data from storage.
    Returns (data: bytes, content_type: str) tuple.
    """
    full_path = STORAGE_ROOT / path
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    with open(full_path, "rb") as f:
        data = f.read()
    
    # Guess content type from extension
    ext = full_path.suffix.lower()
    content_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv": "text/csv",
        ".json": "application/json",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")
    
    return data, content_type


def delete_object(path: str) -> bool:
    """Delete a file from storage. Returns True if deleted, False if not found."""
    full_path = STORAGE_ROOT / path
    if full_path.exists():
        full_path.unlink()
        logger.info(f"Deleted file at {full_path}")
        return True
    return False
