"""Emergent Object Storage — penyimpanan berkas unggahan yang tahan deploy.

URL publik TETAP `/api/uploads/<path>` (dilayani `server.py`), jadi frontend tidak berubah.
"""
import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_PREFIX = "da-erp"
LEGACY_ROOT = Path("/app/uploads")  # berkas lama yang sudah ada di pod (baca-saja)

_storage_key = None


def _key():
    return os.environ.get("EMERGENT_LLM_KEY")


def init_storage(force: bool = False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    if not _key():
        raise RuntimeError("EMERGENT_LLM_KEY belum diset — object storage tidak aktif")
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": _key()}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _full(path: str) -> str:
    return f"{APP_PREFIX}/{path.lstrip('/')}"


def put_object(path: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
    """Simpan berkas. `path` relatif tanpa prefix app (mis. `products/<id>/<uuid>.jpg`)."""
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{_full(path)}",
                        headers={"X-Storage-Key": key, "Content-Type": content_type},
                        data=data, timeout=120)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.put(f"{STORAGE_URL}/objects/{_full(path)}",
                            headers={"X-Storage-Key": key, "Content-Type": content_type},
                            data=data, timeout=120)
    resp.raise_for_status()
    out = resp.json()
    out["url"] = f"/api/uploads/{path.lstrip('/')}"
    return out


def get_object(path: str):
    """Ambil berkas → (bytes, content_type). Jatuh ke berkas lama di pod bila ada. None bila tidak ada."""
    try:
        key = init_storage()
        resp = requests.get(f"{STORAGE_URL}/objects/{_full(path)}",
                            headers={"X-Storage-Key": key}, timeout=60)
        if resp.status_code == 200:
            return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
    except Exception as e:  # noqa: BLE001
        logger.warning("object storage get gagal (%s): %s", path, e)
    legacy = (LEGACY_ROOT / path.lstrip("/")).resolve()
    if str(legacy).startswith(str(LEGACY_ROOT)) and legacy.is_file():
        import mimetypes
        return legacy.read_bytes(), mimetypes.guess_type(str(legacy))[0] or "application/octet-stream"
    return None
