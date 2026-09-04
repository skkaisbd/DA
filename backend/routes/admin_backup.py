"""
Admin Backup & Restore Management
Provides API endpoints for database backup/restore operations
Access: Superadmin only
"""
import logging
import os
import json
import re
import secrets
import shutil
import subprocess
import asyncio
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from auth import require_auth
from utils.waktu import now_wib

router = APIRouter(prefix="/api/admin/backup", tags=["admin", "backup"])

BACKUP_DIR = Path("/app/backups")
BACKUP_SCRIPT = "/app/scripts/backup.sh"
RESTORE_SCRIPT = "/app/scripts/restore.sh"
CLEANUP_SCRIPT = "/app/scripts/cleanup_old_backups.sh"
RETENTION_DAYS = 30

# ── UNDUH & UNGGAH BERKAS BACKUP ──────────────────────────────────────────────
# 2026-08-01 (laporan owner: "tidak bisa download, upload bermasalah"). Temuan:
#   1. UNDUH: frontend memakai fetch→Blob→<a download>. Preview dibuka di dalam
#      IFRAME, dan Chrome MEMBLOKIR unduhan dari iframe tanpa `allow-downloads`
#      (tanpa pesan error). Solusinya: sediakan TIKET unduhan sekali-pakai agar
#      URL bisa dibuka sebagai navigasi tab baru (tanpa header Authorization).
#   2. UNGGAH: `await file.read()` memuat SELURUH berkas ke RAM (cap kontainer
#      2 GB) → backup besar bikin backend mati. Sekarang ditulis streaming per
#      1 MB + tersedia unggah BERPOTONG (chunked) supaya lolos batas proxy.
#   3. ZIP tidak pernah divalidasi: berkas bukan-backup ("asal zip") baru gagal
#      saat restore, dan entri path jahat (../) bisa keluar dari folder tujuan.
# Berkas restore yang diunggah hanya SINGGAH sebentar (langsung diekstrak) — dipakai
# direktori sementara sistem, bukan folder aplikasi di pod.
UPLOAD_TMP_DIR = Path(tempfile.gettempdir()) / "da_backup_uploads_tmp"
DOWNLOAD_TMP_DIR = Path("/app/backups/.download_tmp")
STREAM_CHUNK = 1024 * 1024          # 1 MB — aman untuk RAM 2 GB
TICKET_TTL_SECONDS = 900            # tiket unduhan berlaku 15 menit
_DOWNLOAD_TICKETS: dict = {}        # ticket -> {"backup_id":..., "exp": epoch}

logger = logging.getLogger(__name__)

# ── PENJAGA LIMIT FILE DESCRIPTOR MONGOD ──────────────────────────────────────
# 2026-07-31: restore lewat portal SELALU gagal (HTTP 500, pesan KOSONG) karena
# supervisord menjalankan mongod dengan soft limit nofile 1024 → WiredTiger kena
# "Too many open files" → WT_PANIC → mongod abort di tengah restore.
# Penjaga dipanggil TEPAT SEBELUM backup/restore agar operasi berat tak pernah
# gagal karena sebab ini lagi. Akar masalah lengkap: utils/mongod_fdlimit.py
try:
    from utils.mongod_fdlimit import ensure_and_log as _ensure_mongod_fd
except Exception:  # pragma: no cover — modul opsional, tidak boleh memblok import
    def _ensure_mongod_fd(context: str = "") -> dict:  # type: ignore[misc]
        return {"ok": False, "error": "utils.mongod_fdlimit tidak tersedia", "processes": []}


# ── DIAGNOSTIK KEGAGALAN BACKUP/RESTORE ───────────────────────────────────────
# `scripts/restore.sh` menggabungkan stderr mongorestore ke stdout (`2>&1`),
# sehingga `result.stderr` SELALU kosong. Dulu endpoint hanya memakai stderr →
# user melihat "Restore failed: " tanpa sebab apa pun. Sekarang SELURUH keluaran
# (stdout+stderr) dianalisa dan diterjemahkan jadi sebab + saran perbaikan.
_DIAGNOSTICS: List[tuple] = [
    (
        ("too many open files", "wt_panic", "wiredtiger library panic"),
        "MongoDB kehabisan kuota file terbuka (Too many open files), sehingga mesin "
        "penyimpanan WiredTiger berhenti paksa di tengah proses.",
        "Naikkan limit file mongod lalu ulangi: bash /app/scripts/ensure_mongod_fdlimit.sh "
        "(backend juga menaikkannya otomatis saat start dan tiap 5 menit).",
    ),
    (
        ("connection closed unexpectedly", "connection refused", "no reachable servers",
         "connection() error", "server selection error"),
        "Koneksi ke MongoDB terputus di tengah proses — mongod restart atau berhenti.",
        "Cek: sudo supervisorctl status mongodb dan tail -50 /var/log/mongodb.out.log, "
        "pastikan mongod hidup, lalu ulangi restore.",
    ),
    (
        ("e11000", "duplicate key"),
        "Ada dokumen dengan kunci unik yang bentrok saat menulis data (duplicate key).",
        "Gunakan mode 'overwrite' pada Restore Terpilih (koleksi di-drop dulu), atau "
        "kosongkan koleksi terkait sebelum restore.",
    ),
    (
        ("invalid bsonsize", "reading bson input", "not a gzip", "gzip: invalid",
         "unexpected eof", "corrupt", "archive parser", "no such file or directory",
         "not found in backup", "no database found", "invalid metadata",
         "error restoring from"),
        "Berkas di dalam arsip backup rusak / tidak lengkap sehingga tidak bisa dibaca "
        "(bukan format BSON yang sah).",
        "Unggah ulang file backup (.zip) yang utuh — pastikan isinya folder database "
        "berisi file .bson.gz beserta metadata-nya, dan unduhannya tidak terputus.",
    ),
    (
        ("not authorized", "authentication failed", "requires authentication"),
        "MongoDB menolak proses restore karena masalah autentikasi.",
        "Periksa MONGO_URL di backend/.env (user/password/authSource), lalu restart backend.",
    ),
    (
        ("command not found", "executable file not found", "no such command"),
        "Perkakas mongorestore (MongoDB Database Tools) tidak tersedia di server.",
        "Pasang paket mongodb-database-tools di container, lalu ulangi restore.",
    ),
    (
        ("no space left on device", "quota exceeded"),
        "Ruang disk server habis saat menulis data.",
        "Bebaskan ruang (hapus backup lama lewat tombol Cleanup) lalu ulangi restore.",
    ),
    (
        ("permission denied",),
        "Server tidak punya izin membaca/menulis berkas yang dibutuhkan.",
        "Periksa kepemilikan folder /app/backups dan izin eksekusi scripts/restore.sh.",
    ),
]


def _decode(value) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


# Kode warna ANSI dari restore.sh/backup.sh (mis. "\033[0;31m") membuat log di UI
# jadi berisi sampah "[0;31m" — dibuang sebelum ditampilkan ke user.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def _combined_output(stdout, stderr) -> str:
    """Gabungkan stdout+stderr — restore.sh mengarahkan stderr ke stdout."""
    return f"{_decode(stdout)}\n{_decode(stderr)}".strip()


def _error_lines(output: str, limit: int = 10) -> List[str]:
    """Ambil baris paling relevan sebagai bukti kegagalan (untuk ditampilkan di UI)."""
    clean = _strip_ansi(output)
    keys = ("failed", "error", "panic", "cannot", "unable", "refused",
            "exception", "e11000", "denied", "❌")
    hits = [ln.strip() for ln in clean.splitlines()
            if ln.strip() and any(k in ln.lower() for k in keys)]
    if not hits:
        hits = [ln.strip() for ln in clean.splitlines() if ln.strip()]
    return hits[-limit:]


def _diagnose(output: str) -> tuple:
    low = (output or "").lower()
    for needles, reason, hint in _DIAGNOSTICS:
        if any(n in low for n in needles):
            return reason, hint
    return (
        "Proses gagal tanpa pola sebab yang dikenali.",
        "Baca log lengkap di bawah, atau jalankan manual untuk melihat keluaran penuh: "
        "echo yes | bash /app/scripts/restore.sh <backup_id>",
    )


def _write_op_log(backup_id: str, kind: str, output: str) -> Optional[str]:
    """Simpan log lengkap operasi di folder backup agar bisa ditelusuri belakangan."""
    try:
        target = BACKUP_DIR / backup_id
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{kind}_{now_wib().strftime('%Y%m%d_%H%M%S')}.log"
        path.write_text(output or "(keluaran kosong)", encoding="utf-8")
        return str(path)
    except Exception as e:  # noqa: BLE001
        logger.warning("gagal menulis log %s untuk %s: %s", kind, backup_id, e)
        return None


def _failure_payload(kind: str, backup_id: str, returncode: Optional[int], output: str) -> dict:
    """Susun detail kegagalan yang INFORMATIF (dipakai sebagai HTTPException detail)."""
    reason, hint = _diagnose(output)
    return {
        "message": f"{kind} dari '{backup_id}' GAGAL",
        "reason": reason,
        "hint": hint,
        "returncode": returncode,
        "log_lines": _error_lines(output),
        "log_path": _write_op_log(backup_id, kind.lower().replace(" ", "_"), output),
    }


class BackupMetadata(BaseModel):
    backup_id: str
    backup_name: str
    created_at: str
    size: str
    status: str
    database: Optional[str] = None


class BackupCreateRequest(BaseModel):
    backup_name: Optional[str] = None
    notify: bool = True


class RestoreRequest(BaseModel):
    backup_id: str
    confirm: bool = False


class UploadRestoreRequest(BaseModel):
    collections: Optional[List[str]] = None  # None = all collections
    mode: str = "overwrite"  # "merge" or "overwrite"
    confirm: bool = False


class SelectiveRestoreRequest(BaseModel):
    backup_id: str
    collections: List[str]  # Selected collections to restore
    mode: str = "overwrite"  # "merge" or "overwrite"
    confirm: bool = False


class ClearCollectionsRequest(BaseModel):
    """Kosongkan isi koleksi tertentu (dokumen dihapus, koleksi tetap ada)."""
    collections: List[str]
    confirm_text: str = ""          # wajib persis "KOSONGKAN"
    create_backup: bool = True      # cadangan pengaman sebelum menghapus
    allow_protected: bool = False   # buka kunci koleksi fondasi (sangat berisiko)


CLEAR_CONFIRM_TEXT = "KOSONGKAN"


def _require_superadmin(user: dict) -> dict:
    """Check if user is superadmin"""
    if user.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return user


SYSTEM_DBS = {"admin", "config", "local", "__pycache__"}


def _current_db_name() -> str:
    """Resolve the current application database name (aligned with backend env)."""
    return os.environ.get("DB_NAME") or os.environ.get("MONGO_DB") or "test_database"


def _has_dump_files(d: Path) -> bool:
    """Apakah folder ini benar-benar berisi hasil mongodump (*.bson[.gz])?"""
    try:
        return any(d.glob("*.bson.gz")) or any(d.glob("*.bson"))
    except Exception:  # noqa: BLE001
        return False


def _select_db_dir(backup_path: Path) -> Optional[Path]:
    """Pick the application's database directory inside a backup.

    Prefers a directory that ACTUALLY contains mongodump files, then the current
    DB_NAME; skips Mongo system databases (admin/config/local). Also handles the
    nested case (`upload_x/manual_y/test_database/*.bson.gz`) that happens when a
    user zips the backup FOLDER instead of its contents — previously this made
    collection listing return the wrapper folder and restore silently found
    nothing.
    """
    if not backup_path.exists():
        return None
    dirs = [d for d in backup_path.iterdir() if d.is_dir() and d.name not in SYSTEM_DBS]
    pool = [d for d in dirs if _has_dump_files(d)]
    if not pool:
        # cari lebih dalam (arsip bersarang)
        deep = sorted({p.parent for p in list(backup_path.rglob("*.bson.gz"))
                       + list(backup_path.rglob("*.bson"))})
        pool = [d for d in deep if d.name not in SYSTEM_DBS] or dirs
    if not pool:
        return None
    current = _current_db_name()
    for d in pool:
        if d.name == current:
            return d
    return pool[0]


# ── TIKET UNDUHAN SEKALI-PAKAI ────────────────────────────────────────────────
def _purge_tickets() -> None:
    now = time.time()
    for t in [k for k, v in _DOWNLOAD_TICKETS.items() if v["exp"] < now]:
        _DOWNLOAD_TICKETS.pop(t, None)


def _issue_ticket(backup_id: str) -> str:
    _purge_tickets()
    ticket = secrets.token_urlsafe(32)
    _DOWNLOAD_TICKETS[ticket] = {"backup_id": backup_id, "exp": time.time() + TICKET_TTL_SECONDS}
    return ticket


def _resolve_ticket(ticket: str) -> Optional[str]:
    """Tiket boleh dipakai berulang SELAMA masa berlaku (browser kadang
    mengulang permintaan / memakai Range request saat mengunduh)."""
    _purge_tickets()
    rec = _DOWNLOAD_TICKETS.get(ticket or "")
    return rec["backup_id"] if rec else None


def _safe_backup_id(backup_id: str) -> str:
    """Cegah path traversal pada backup_id yang datang dari URL."""
    clean = (backup_id or "").strip().strip("/")
    if not clean or "/" in clean or "\\" in clean or ".." in clean:
        raise HTTPException(status_code=400, detail="backup_id tidak valid")
    return clean


def _purge_old_temp(dirpath: Path, max_age_seconds: int = 3600) -> None:
    """Buang berkas sementara lama (dulu ZIP unduhan menumpuk di /tmp)."""
    try:
        if not dirpath.exists():
            return
        now = time.time()
        for p in dirpath.iterdir():
            try:
                if now - p.stat().st_mtime > max_age_seconds:
                    shutil.rmtree(p) if p.is_dir() else p.unlink()
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        logger.debug("purge temp gagal", exc_info=True)


# ── VALIDASI + EKSTRAKSI ZIP BACKUP ───────────────────────────────────────────
def _bad_zip(reason: str, hint: str) -> HTTPException:
    return HTTPException(status_code=400, detail={
        "message": "Berkas backup tidak bisa diproses",
        "reason": reason,
        "hint": hint,
    })


def _extract_backup_zip(zip_path: Path, dest: Path) -> dict:
    """Validasi lalu ekstrak arsip backup dengan aman.

    Pemeriksaan: (a) benar berkas ZIP, (b) tidak ada entri jahat (absolut/`..`),
    (c) berisi berkas mongodump `*.bson[.gz]`. Setelah ekstraksi, struktur
    bersarang DIRATAKAN sehingga `dest/<db>/<koleksi>.bson.gz` — bentuk yang
    dibutuhkan `scripts/restore.sh` dan mongorestore.
    """
    if not zipfile.is_zipfile(zip_path):
        raise _bad_zip(
            "Berkas yang diunggah bukan arsip ZIP yang sah (mungkin terputus saat unggah "
            "atau formatnya .tar/.gz/.bson).",
            "Unggah berkas .zip hasil tombol Download di halaman ini, atau ZIP dari folder "
            "backup yang berisi <nama_database>/<koleksi>.bson.gz.",
        )
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        unsafe = [n for n in names if n.startswith(("/", "\\")) or ".." in Path(n).parts]
        if unsafe:
            raise _bad_zip(
                f"Arsip memuat jalur berkas yang tidak aman ({unsafe[0]}).",
                "Buat ulang ZIP tanpa jalur absolut atau '..' di dalamnya.",
            )
        dumps = [n for n in names if n.endswith((".bson.gz", ".bson"))]
        if not dumps:
            raise _bad_zip(
                "Arsip tidak memuat berkas mongodump (*.bson atau *.bson.gz) sama sekali.",
                "Pastikan yang diunggah adalah hasil backup database (isi folder "
                "/app/backups/<nama_backup>), bukan ZIP dokumen/gambar.",
            )
        dest.mkdir(parents=True, exist_ok=True)
        zf.extractall(dest)

    # Ratakan struktur bila hasil ekstraksi bersarang (mis. dest/manual_x/db/…)
    dump_files = list(dest.rglob("*.bson.gz")) or list(dest.rglob("*.bson"))
    db_dir = dump_files[0].parent
    root = db_dir.parent
    if root != dest:
        for item in list(root.iterdir()):
            target = dest / item.name
            if target.exists():
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            shutil.move(str(item), str(target))
        # bersihkan folder pembungkus yang sudah kosong
        try:
            wrapper = root
            while wrapper != dest and wrapper.exists() and not any(wrapper.iterdir()):
                wrapper.rmdir()
                wrapper = wrapper.parent
        except Exception:  # noqa: BLE001
            logger.debug("gagal membersihkan folder pembungkus", exc_info=True)
        dump_files = list(dest.rglob("*.bson.gz")) or list(dest.rglob("*.bson"))
        db_dir = dump_files[0].parent

    return {
        "database_in_backup": db_dir.name,
        "collections_found": len({p.name.split(".bson")[0] for p in dump_files}),
    }


def _write_upload_metadata(backup_path: Path, backup_name: str, timestamp: str,
                           user: dict, original_filename: str, shape: dict) -> dict:
    metadata = {
        "backup_name": backup_name,
        "timestamp": timestamp,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "size": _calculate_dir_size(backup_path),
        "status": "uploaded",
        "uploaded_by": user.get("name") or user.get("email") or "unknown",
        "original_filename": original_filename,
        "database": shape.get("database_in_backup"),
        "collections_found": shape.get("collections_found"),
    }
    with open(backup_path / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    return metadata


def _get_backup_metadata(backup_path: Path) -> Optional[dict]:
    """Read metadata.json from backup directory"""
    metadata_file = backup_path / "metadata.json"
    if metadata_file.exists():
        try:
            with open(metadata_file, 'r') as f:
                return json.load(f)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    return None


def _calculate_dir_size(path: Path) -> str:
    """Calculate directory size in human-readable format"""
    try:
        result = subprocess.run(
            ['du', '-sh', str(path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.split()[0]
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    return "unknown"


async def _send_notification(user_id: str, title: str, message: str, type: str = "info"):
    """Send in-app notification"""
    try:
        from routes.rahaza_notifications import send_notification
        await send_notification(
            user_id=user_id,
            title=title,
            message=message,
            type=type,
            category="system"
        )
    except Exception as e:
        print(f"Failed to send notification: {e}")


@router.get("/list")
async def list_backups(request: Request):
    """List all available backups"""
    user = await require_auth(request)
    _require_superadmin(user)
    
    if not BACKUP_DIR.exists():
        return {"backups": []}
    
    backups = []
    for backup_path in BACKUP_DIR.iterdir():
        # Folder kerja internal (.uploads_tmp / .download_tmp) BUKAN backup —
        # tanpa filter ini keduanya muncul sebagai entri palsu di daftar.
        if backup_path.name.startswith('.'):
            continue
        if backup_path.is_dir():
            metadata = _get_backup_metadata(backup_path)
            
            if metadata:
                backup_info = {
                    "backup_id": backup_path.name,
                    "backup_name": metadata.get("backup_name", backup_path.name),
                    "created_at": metadata.get("created_at"),
                    "size": metadata.get("size", "unknown"),
                    "status": metadata.get("status", "unknown"),
                    "database": metadata.get("database")
                }
            else:
                # Fallback if no metadata
                stat = backup_path.stat()
                backup_info = {
                    "backup_id": backup_path.name,
                    "backup_name": backup_path.name,
                    "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "size": _calculate_dir_size(backup_path),
                    "status": "success",
                    "database": None
                }
            
            backups.append(backup_info)
    
    # Sort by created_at descending (newest first)
    backups.sort(key=lambda x: x["created_at"], reverse=True)
    
    return {"backups": backups, "total": len(backups)}


@router.post("/create")
async def create_backup(
    request: Request,
    body: BackupCreateRequest,
    background_tasks: BackgroundTasks
):
    """Create a new database backup"""
    user = await require_auth(request)
    _require_superadmin(user)
    
    # Generate backup name
    timestamp = now_wib().strftime("%Y%m%d_%H%M%S")
    backup_name = body.backup_name or f"manual_{timestamp}"
    
    # Run backup script in background
    async def run_backup():
        # Jaring pengaman limit file mongod (mongodump juga membuka banyak file).
        _ensure_mongod_fd("pre-backup")
        try:
            process = await asyncio.create_subprocess_exec(
                BACKUP_SCRIPT,
                backup_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                if body.notify:
                    await _send_notification(
                        user["id"],
                        "✅ Backup Berhasil",
                        f"Database backup '{backup_name}' telah dibuat dengan sukses",
                        "success"
                    )
            else:
                # SEBAB + SARAN (bukan stderr mentah yang sering kosong karena 2>&1).
                _out = _combined_output(stdout, stderr)
                _reason, _hint = _diagnose(_out)
                _log = _write_op_log(backup_name, "backup", _out)
                logger.error("[backup] GAGAL rc=%s | sebab=%s | log=%s",
                             process.returncode, _reason, _log)
                if body.notify:
                    await _send_notification(
                        user["id"],
                        "❌ Backup Gagal",
                        f"Backup '{backup_name}' gagal — {_reason} Saran: {_hint}",
                        "error"
                    )
        except Exception as e:
            if body.notify:
                await _send_notification(
                    user["id"],
                    "❌ Backup Error",
                    f"Error saat backup: {str(e)}",
                    "error"
                )
    
    background_tasks.add_task(run_backup)
    
    return {
        "ok": True,
        "message": f"Backup '{backup_name}' sedang diproses di background",
        "backup_name": backup_name
    }


@router.post("/restore")
async def restore_backup(request: Request, body: RestoreRequest):
    """Restore database from backup"""
    user = await require_auth(request)
    _require_superadmin(user)
    
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required. Set 'confirm: true' to proceed with restore."
        )
    
    backup_path = BACKUP_DIR / body.backup_id
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail=f"Backup '{body.backup_id}' not found")
    
    # Jaring pengaman: pastikan limit file mongod cukup SEBELUM restore.
    # Ini sebab kegagalan #1 di environment ini (lihat utils/mongod_fdlimit.py).
    fd_guard = _ensure_mongod_fd("pre-restore")

    # Run restore script (blocking operation - this will restart services)
    try:
        result = subprocess.run(
            [RESTORE_SCRIPT, body.backup_id],
            input=b"yes\n",  # Auto-confirm
            capture_output=True,
            timeout=300  # 5 minutes timeout
        )
        output = _combined_output(result.stdout, result.stderr)

        if result.returncode == 0:
            await _send_notification(
                user["id"],
                "✅ Restore Berhasil",
                f"Database berhasil di-restore dari backup '{body.backup_id}'",
                "success"
            )
            return {
                "ok": True,
                "message": f"Database berhasil di-restore dari '{body.backup_id}'",
                "output": output,
                "mongod_fd_limit": fd_guard,
            }

        # GAGAL — sampaikan SEBAB + SARAN, bukan pesan kosong.
        payload = _failure_payload("Restore", body.backup_id, result.returncode, output)
        payload["mongod_fd_limit"] = fd_guard
        logger.error("[restore] GAGAL rc=%s | sebab=%s | log=%s",
                     result.returncode, payload["reason"], payload["log_path"])
        await _send_notification(
            user["id"],
            "❌ Restore Gagal",
            f"{payload['message']} — {payload['reason']}",
            "error"
        )
        raise HTTPException(status_code=500, detail=payload)

    except subprocess.TimeoutExpired as e:
        output = _combined_output(getattr(e, "stdout", None), getattr(e, "stderr", None))
        raise HTTPException(status_code=500, detail={
            "message": f"Restore dari '{body.backup_id}' DIHENTIKAN",
            "reason": "Proses restore melewati batas waktu 5 menit dan dihentikan otomatis.",
            "hint": "Untuk database besar, gunakan Restore Terpilih (per koleksi) atau jalankan "
                    "manual di terminal: echo yes | bash /app/scripts/restore.sh " + body.backup_id,
            "returncode": None,
            "log_lines": _error_lines(output) if output else [],
            "log_path": _write_op_log(body.backup_id, "restore_timeout", output) if output else None,
        })
    except HTTPException:
        # PENTING: dulu blok `except Exception` di bawah menelan HTTPException ini
        # sehingga user menerima "Restore error: 500: Restore failed: " (dobel bungkus,
        # sebab hilang). Sekarang detail asli diteruskan utuh.
        raise
    except Exception as e:
        logger.exception("[restore] error tak terduga")
        raise HTTPException(status_code=500, detail={
            "message": f"Restore dari '{body.backup_id}' GAGAL",
            "reason": f"Kesalahan tak terduga saat menjalankan restore: {type(e).__name__}: {e}",
            "hint": "Cek log backend: tail -50 /var/log/supervisor/backend.err.log",
            "returncode": None,
            "log_lines": [],
            "log_path": None,
        })


@router.delete("/{backup_id}")
async def delete_backup(request: Request, backup_id: str):
    """Delete a backup"""
    user = await require_auth(request)
    _require_superadmin(user)
    
    backup_path = BACKUP_DIR / backup_id
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail=f"Backup '{backup_id}' not found")
    
    try:
        import shutil
        shutil.rmtree(backup_path)
        
        await _send_notification(
            user["id"],
            "🗑️ Backup Dihapus",
            f"Backup '{backup_id}' telah dihapus",
            "info"
        )
        
        return {"ok": True, "message": f"Backup '{backup_id}' deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.post("/cleanup")
async def cleanup_old_backups(request: Request):
    """Cleanup backups older than retention period"""
    user = await require_auth(request)
    _require_superadmin(user)
    
    try:
        result = subprocess.run(
            [CLEANUP_SCRIPT, str(RETENTION_DAYS)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        return {
            "ok": True,
            "message": f"Cleanup completed (retention: {RETENTION_DAYS} days)",
            "output": result.stdout
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@router.get("/config")
async def get_backup_config(request: Request):
    """Get backup configuration"""
    user = await require_auth(request)
    _require_superadmin(user)
    
    return {
        "backup_dir": str(BACKUP_DIR),
        "retention_days": RETENTION_DAYS,
        "auto_backup_enabled": True,
        "auto_backup_schedule": "Daily at 02:00 Asia/Jakarta",
        "storage_type": "local_filesystem"
    }


def _build_backup_zip(backup_path: Path) -> Path:
    """Bungkus folder backup menjadi ZIP di folder sementara khusus."""
    DOWNLOAD_TMP_DIR.mkdir(parents=True, exist_ok=True)
    _purge_old_temp(DOWNLOAD_TMP_DIR)
    tmp = Path(tempfile.mkdtemp(prefix="dl_", dir=str(DOWNLOAD_TMP_DIR)))
    zip_path = tmp / f"{backup_path.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in sorted(backup_path.rglob("*")):
            if file_path.is_file() and file_path.suffix != ".log":
                zipf.write(file_path, file_path.relative_to(backup_path))
    return zip_path


@router.post("/download-ticket/{backup_id}")
async def create_download_ticket(request: Request, backup_id: str):
    """Terbitkan tiket unduhan sekali-pakai (berlaku 15 menit).

    KENAPA ADA: preview aplikasi dibuka di dalam IFRAME, dan Chrome memblokir
    unduhan `Blob`/`<a download>` dari iframe tanpa izin `allow-downloads` —
    user melihat "sukses" tapi tidak ada berkas. Dengan tiket, frontend cukup
    membuka URL biasa di tab baru (tanpa header Authorization) sehingga unduhan
    ditangani sebagai navigasi normal oleh browser.
    """
    user = await require_auth(request)
    _require_superadmin(user)

    backup_id = _safe_backup_id(backup_id)
    backup_path = BACKUP_DIR / backup_id
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail=f"Backup '{backup_id}' not found")

    ticket = _issue_ticket(backup_id)
    return {
        "ok": True,
        "ticket": ticket,
        "expires_in": TICKET_TTL_SECONDS,
        "url": f"/api/admin/backup/download/{backup_id}?ticket={ticket}",
        "filename": f"{backup_id}.zip",
    }


@router.get("/download/{backup_id}")
async def download_backup(request: Request, backup_id: str, ticket: Optional[str] = None):
    """Download backup as ZIP file.

    Dua cara autentikasi:
      • header `Authorization: Bearer <jwt>` (pemakaian lewat fetch/axios), atau
      • query `?ticket=<tiket>` dari `POST /download-ticket/{id}` — dipakai saat
        membuka URL langsung di tab baru (lolos blokir unduhan di iframe).
    """
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    backup_id = _safe_backup_id(backup_id)

    if ticket:
        if _resolve_ticket(ticket) != backup_id:
            raise HTTPException(status_code=403, detail="Tiket unduhan tidak valid atau kedaluwarsa")
    else:
        user = await require_auth(request)
        _require_superadmin(user)

    backup_path = BACKUP_DIR / backup_id
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail=f"Backup '{backup_id}' not found")

    try:
        zip_path = _build_backup_zip(backup_path)
    except Exception as e:  # noqa: BLE001
        logger.exception("[download] gagal membuat ZIP")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

    # Hapus folder sementara SETELAH respons terkirim (dulu ZIP menumpuk di /tmp).
    cleanup = BackgroundTask(shutil.rmtree, str(zip_path.parent), ignore_errors=True)
    return FileResponse(
        path=str(zip_path),
        filename=f"{backup_id}.zip",
        media_type="application/zip",
        background=cleanup,
        headers={"Content-Disposition": f'attachment; filename="{backup_id}.zip"'},
    )


@router.post("/upload")
async def upload_backup(request: Request):
    """Info endpoint — unggah sebenarnya lewat /upload-file (kecil) atau
    /upload-init + /upload-chunk + /upload-complete (besar/berpotong)."""

    user = await require_auth(request)
    _require_superadmin(user)

    return {
        "message": "Gunakan POST /api/admin/backup/upload-file (multipart, berkas kecil) "
                   "atau alur berpotong: /upload-init → /upload-chunk → /upload-complete",
        "chunk_flow": ["/api/admin/backup/upload-init",
                       "/api/admin/backup/upload-chunk",
                       "/api/admin/backup/upload-complete"],
    }


def _new_backup_name(original_filename: str) -> tuple:
    base = Path(original_filename or "backup.zip").name
    if base.lower().endswith(".zip"):
        base = base[:-4]
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:60] or "backup"
    timestamp = now_wib().strftime("%Y%m%d_%H%M%S")
    return f"upload_{timestamp}_{base}", timestamp


@router.post("/upload-file")
async def upload_backup_file(request: Request):
    """Unggah + ekstrak berkas ZIP backup (satu permintaan).

    Berkas ditulis ke disk STREAMING per 1 MB — dulu `await file.read()` memuat
    seluruh berkas ke memori, dan pada kontainer dengan batas 2 GB backup besar
    membuat backend mati (upload "menggantung" lalu gagal tanpa pesan).
    """
    user = await require_auth(request)
    _require_superadmin(user)

    form = await request.form()
    file = form.get('file')

    if file is None or not hasattr(file, "read"):
        raise HTTPException(status_code=400, detail="Tidak ada berkas yang diunggah (field 'file' wajib ada)")

    backup_name, timestamp = _new_backup_name(getattr(file, "filename", "backup.zip"))
    backup_path = BACKUP_DIR / backup_name
    UPLOAD_TMP_DIR.mkdir(parents=True, exist_ok=True)
    _purge_old_temp(UPLOAD_TMP_DIR, max_age_seconds=6 * 3600)
    temp_file_path = UPLOAD_TMP_DIR / f"{backup_name}.part"

    try:
        total = 0
        with tempfile.NamedTemporaryFile(dir=UPLOAD_TMP_DIR, prefix=f"{backup_name}.",
                                         suffix=".part", delete=False) as out:
            temp_file_path = Path(out.name)
            while True:
                chunk = await file.read(STREAM_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                total += len(chunk)
        if total == 0:
            raise _bad_zip("Berkas yang diunggah kosong (0 byte).",
                           "Pilih ulang berkas .zip backup lalu unggah lagi.")

        shape = _extract_backup_zip(temp_file_path, backup_path)
        temp_file_path.unlink(missing_ok=True)

        metadata = _write_upload_metadata(
            backup_path, backup_name, timestamp, user,
            getattr(file, "filename", "backup.zip"), shape,
        )

        await _send_notification(
            user["id"],
            "✅ Backup Diunggah",
            f"Backup '{backup_name}' berhasil diunggah "
            f"({shape['collections_found']} koleksi, database '{shape['database_in_backup']}')",
            "success"
        )

        return {
            "ok": True,
            "message": "Backup berhasil diunggah",
            "backup_id": backup_name,
            "backup_name": backup_name,
            "size_bytes": total,
            "database_in_backup": shape["database_in_backup"],
            "collections_found": shape["collections_found"],
            "metadata": metadata,
        }

    except HTTPException:
        temp_file_path.unlink(missing_ok=True)
        if backup_path.exists():
            shutil.rmtree(backup_path, ignore_errors=True)
        raise
    except Exception as e:
        temp_file_path.unlink(missing_ok=True)
        if backup_path.exists():
            shutil.rmtree(backup_path, ignore_errors=True)
        logger.exception("[upload] gagal")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# ── UNGGAH BERPOTONG (CHUNKED) untuk berkas besar ─────────────────────────────
# Proxy/ingress bisa menolak badan permintaan besar, dan menulis 1 berkas raksasa
# sekaligus berisiko di kontainer 2 GB. Alur: init → kirim potongan → complete.
class UploadInitRequest(BaseModel):
    filename: str
    total_size: int = 0
    total_chunks: int = 0


class UploadCompleteRequest(BaseModel):
    upload_id: str


def _session_dir(upload_id: str) -> Path:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "", upload_id or "")
    if not clean:
        raise HTTPException(status_code=400, detail="upload_id tidak valid")
    return UPLOAD_TMP_DIR / clean


@router.post("/upload-init")
async def upload_init(request: Request, body: UploadInitRequest):
    """Mulai sesi unggah berpotong; balikan `upload_id`."""
    user = await require_auth(request)
    _require_superadmin(user)

    UPLOAD_TMP_DIR.mkdir(parents=True, exist_ok=True)
    _purge_old_temp(UPLOAD_TMP_DIR, max_age_seconds=6 * 3600)

    upload_id = f"up_{now_wib().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"
    sdir = _session_dir(upload_id)
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "session.json").write_text(json.dumps({
        "upload_id": upload_id,
        "filename": body.filename,
        "total_size": body.total_size,
        "total_chunks": body.total_chunks,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user.get("id"),
    }), encoding="utf-8")
    return {"ok": True, "upload_id": upload_id, "chunk_size": 5 * 1024 * 1024}


@router.post("/upload-chunk")
async def upload_chunk(request: Request):
    """Terima satu potongan berkas (multipart: upload_id, index, file)."""
    user = await require_auth(request)
    _require_superadmin(user)

    form = await request.form()
    upload_id = str(form.get("upload_id") or "")
    index_raw = str(form.get("index") or "")
    chunk = form.get("file")

    sdir = _session_dir(upload_id)
    if not (sdir / "session.json").exists():
        raise HTTPException(status_code=404, detail="Sesi unggah tidak ditemukan / sudah kedaluwarsa")
    if not index_raw.isdigit():
        raise HTTPException(status_code=400, detail="index potongan wajib angka")
    if chunk is None or not hasattr(chunk, "read"):
        raise HTTPException(status_code=400, detail="Potongan berkas tidak ada")

    part_path = sdir / f"part_{int(index_raw):06d}"
    written = 0
    # potongan disinggahkan di direktori sementara sistem sampai `upload-complete` menggabungkannya
    with tempfile.NamedTemporaryFile(dir=sdir, prefix="recv_", delete=False) as out:
        staged = Path(out.name)
        while True:
            buf = await chunk.read(STREAM_CHUNK)
            if not buf:
                break
            out.write(buf)
            written += len(buf)
    staged.replace(part_path)

    parts = sorted(sdir.glob("part_*"))
    return {
        "ok": True,
        "index": int(index_raw),
        "bytes": written,
        "received_chunks": len(parts),
        "received_bytes": sum(p.stat().st_size for p in parts),
    }


@router.post("/upload-complete")
async def upload_complete(request: Request, body: UploadCompleteRequest):
    """Gabungkan semua potongan, validasi ZIP, lalu ekstrak jadi backup siap-restore."""
    user = await require_auth(request)
    _require_superadmin(user)

    sdir = _session_dir(body.upload_id)
    session_file = sdir / "session.json"
    if not session_file.exists():
        raise HTTPException(status_code=404, detail="Sesi unggah tidak ditemukan / sudah kedaluwarsa")

    session = json.loads(session_file.read_text(encoding="utf-8"))
    parts = sorted(sdir.glob("part_*"))
    if not parts:
        shutil.rmtree(sdir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Belum ada potongan berkas yang diterima")

    expected = int(session.get("total_chunks") or 0)
    if expected and len(parts) != expected:
        raise HTTPException(status_code=400, detail={
            "message": "Unggahan belum lengkap",
            "reason": f"Potongan diterima {len(parts)} dari {expected}.",
            "hint": "Ulangi unggah — koneksi terputus di tengah proses.",
        })

    backup_name, timestamp = _new_backup_name(session.get("filename") or "backup.zip")
    backup_path = BACKUP_DIR / backup_name
    merged = sdir / "merged.zip"

    try:
        with open(merged, "wb") as out:
            for p in parts:
                with open(p, "rb") as src:
                    shutil.copyfileobj(src, out, STREAM_CHUNK)
        total = merged.stat().st_size
        declared = int(session.get("total_size") or 0)
        if declared and total != declared:
            raise HTTPException(status_code=400, detail={
                "message": "Ukuran berkas hasil gabungan tidak cocok",
                "reason": f"Diterima {total} byte, seharusnya {declared} byte.",
                "hint": "Ulangi unggah dari awal.",
            })

        shape = _extract_backup_zip(merged, backup_path)
        metadata = _write_upload_metadata(
            backup_path, backup_name, timestamp, user,
            session.get("filename") or "backup.zip", shape,
        )

        await _send_notification(
            user["id"],
            "✅ Backup Diunggah",
            f"Backup '{backup_name}' berhasil diunggah "
            f"({shape['collections_found']} koleksi, database '{shape['database_in_backup']}')",
            "success"
        )

        return {
            "ok": True,
            "message": "Backup berhasil diunggah",
            "backup_id": backup_name,
            "backup_name": backup_name,
            "size_bytes": total,
            "chunks": len(parts),
            "database_in_backup": shape["database_in_backup"],
            "collections_found": shape["collections_found"],
            "metadata": metadata,
        }
    except HTTPException:
        if backup_path.exists():
            shutil.rmtree(backup_path, ignore_errors=True)
        raise
    except Exception as e:
        if backup_path.exists():
            shutil.rmtree(backup_path, ignore_errors=True)
        logger.exception("[upload-complete] gagal")
        raise HTTPException(status_code=500, detail=f"Upload gagal saat penggabungan: {str(e)}")
    finally:
        shutil.rmtree(sdir, ignore_errors=True)


@router.get("/{backup_id}/collections")
async def list_collections_in_backup(request: Request, backup_id: str):
    """List all collections available in a backup"""
    user = await require_auth(request)
    _require_superadmin(user)
    
    backup_path = BACKUP_DIR / backup_id
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail=f"Backup '{backup_id}' not found")
    
    try:
        collections = []
        
        # Select the application's database directory (skip system DBs) so we
        # always list the CURRENT database's collections, not admin/config.
        db_dir = _select_db_dir(backup_path)
        
        if db_dir is None:
            return {"collections": [], "database": None}
        
        db_name = db_dir.name
        
        # List all .bson.gz files (collections)
        for bson_file in db_dir.glob('*.bson.gz'):
            collection_name = bson_file.stem.replace('.bson', '')
            
            # Get document count from metadata if available
            metadata_file = bson_file.with_suffix('').with_suffix('.metadata.json')
            doc_count = 0
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        meta = json.load(f)
                        doc_count = meta.get('count', 0)
                except Exception:
                    logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
            
            # Get file size
            size_bytes = bson_file.stat().st_size
            size_mb = round(size_bytes / (1024 * 1024), 2)
            
            collections.append({
                "name": collection_name,
                "size_mb": size_mb,
                "document_count": doc_count,
                "filename": bson_file.name
            })
        
        # Sort by name
        collections.sort(key=lambda x: x['name'])
        
        return {
            "collections": collections,
            "database": db_name,
            "total_collections": len(collections)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list collections: {str(e)}")


@router.post("/restore-selective")
async def restore_selective(request: Request, body: SelectiveRestoreRequest):
    """Restore selected collections only with merge/overwrite mode"""
    user = await require_auth(request)
    _require_superadmin(user)
    
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required. Set 'confirm: true' to proceed."
        )
    
    if not body.collections or len(body.collections) == 0:
        raise HTTPException(status_code=400, detail="No collections selected")
    
    if body.mode not in ['merge', 'overwrite']:
        raise HTTPException(status_code=400, detail="Mode must be 'merge' or 'overwrite'")
    
    backup_path = BACKUP_DIR / body.backup_id
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail=f"Backup '{body.backup_id}' not found")
    
    # Jaring pengaman limit file mongod (lihat utils/mongod_fdlimit.py)
    fd_guard = _ensure_mongod_fd("pre-selective-restore")
    
    try:
        # Select the application's database directory (skip system DBs)
        db_dir = _select_db_dir(backup_path)
        if db_dir is None:
            raise HTTPException(status_code=400, detail="No database found in backup")
        
        # Build mongorestore command
        mongo_uri = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        
        restored_collections = []
        failed_collections = []
        
        for collection_name in body.collections:
            collection_file = db_dir / f"{collection_name}.bson.gz"
            
            if not collection_file.exists():
                failed_collections.append({
                    "name": collection_name,
                    "error": "Collection file not found in backup"
                })
                continue
            
            try:
                # mongorestore options — always target the CURRENT database.
                current_db = _current_db_name()
                src_ns = f"{db_dir.name}.{collection_name}"
                cmd = [
                    'mongorestore',
                    f'--uri={mongo_uri}',
                    '--gzip',
                    f'--nsInclude={src_ns}',
                ]
                # Remap if the backup's DB name differs from the current DB name.
                if db_dir.name != current_db:
                    cmd.append(f'--nsFrom={src_ns}')
                    cmd.append(f'--nsTo={current_db}.{collection_name}')
                
                # Add mode-specific options
                if body.mode == 'overwrite':
                    cmd.append('--drop')  # Drop collection before restore
                # merge mode = no --drop (just insert/upsert documents)
                
                cmd.append(str(backup_path))
                
                # Execute restore
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if result.returncode == 0:
                    restored_collections.append(collection_name)
                else:
                    # Sertakan SEBAB + SARAN, bukan hanya stderr mentah (sering kosong).
                    _out = _combined_output(result.stdout, result.stderr)
                    _reason, _hint = _diagnose(_out)
                    failed_collections.append({
                        "name": collection_name,
                        "error": _reason,
                        "hint": _hint,
                        "returncode": result.returncode,
                        "log_lines": _error_lines(_out, limit=5),
                    })
                    
            except Exception as e:
                failed_collections.append({
                    "name": collection_name,
                    "error": str(e)
                })
        
        # Send notification
        mode_text = "overwrite (drop & restore)" if body.mode == 'overwrite' else "merge (insert only)"
        await _send_notification(
            user["id"],
            "✅ Selective Restore Selesai" if not failed_collections else "⚠️ Selective Restore Sebagian Berhasil",
            f"Restored {len(restored_collections)}/{len(body.collections)} collections (mode: {mode_text})",
            "success" if not failed_collections else "warning"
        )
        
        return {
            "ok": True,
            "mode": body.mode,
            "restored_collections": restored_collections,
            "failed_collections": failed_collections,
            "total_requested": len(body.collections),
            "total_restored": len(restored_collections),
            "total_failed": len(failed_collections),
            "mongod_fd_limit": fd_guard,
        }
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Restore timeout (>5 minutes)")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Selective restore error: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# BACKUP LANJUTAN — jelajah koleksi database aktif & pengosongan terpilih
# Layar: Portal Administrasi Sistem → Backup Data → tab "Koleksi Database".
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/live-collections")
async def live_collections(request: Request):
    """Daftar koleksi database AKTIF beserta jumlah dokumen & pengelompokannya."""
    user = await require_auth(request)
    _require_superadmin(user)

    from database import get_db
    from data.collection_registry import GROUP_ORDER, group_of, is_protected

    db = get_db()
    names = sorted(await db.list_collection_names())
    items = []
    for name in names:
        try:
            count = await db[name].estimated_document_count()
        except Exception:
            count = 0
        items.append({
            "name": name,
            "count": int(count),
            "group": group_of(name),
            "protected": is_protected(name),
        })
    items.sort(key=lambda x: (GROUP_ORDER.index(x["group"]), x["name"]))
    return {
        "database": _current_db_name(),
        "total_collections": len(items),
        "total_documents": sum(i["count"] for i in items),
        "groups": GROUP_ORDER,
        "collections": items,
    }


@router.post("/clear-collections")
async def clear_collections(request: Request, body: ClearCollectionsRequest):
    """Kosongkan koleksi terpilih (hapus SEMUA dokumen di dalamnya).

    Pengaman berlapis:
      1. Hanya super admin.
      2. Harus mengetik persis "KOSONGKAN".
      3. Koleksi fondasi (pengguna, hak akses, counter, bagan akun) ditolak
         kecuali `allow_protected` dinyalakan sadar-risiko.
      4. Cadangan pengaman dibuat lebih dulu (default menyala).
    """
    user = await require_auth(request)
    _require_superadmin(user)

    from database import get_db
    from data.collection_registry import is_protected

    if body.confirm_text.strip().upper() != CLEAR_CONFIRM_TEXT:
        raise HTTPException(400, f"Ketik persis '{CLEAR_CONFIRM_TEXT}' untuk mengonfirmasi.")
    if not body.collections:
        raise HTTPException(400, "Belum ada koleksi yang dipilih.")

    db = get_db()
    existing = set(await db.list_collection_names())
    unknown = [c for c in body.collections if c not in existing]
    if unknown:
        raise HTTPException(404, "Koleksi tidak ditemukan: " + ", ".join(unknown[:5]))

    blocked = [c for c in body.collections if is_protected(c)]
    if blocked and not body.allow_protected:
        raise HTTPException(400,
            "Koleksi fondasi ditolak: " + ", ".join(blocked[:8]) +
            ". Nyalakan opsi 'izinkan koleksi terlindungi' bila benar-benar disengaja.")

    safety_backup = None
    if body.create_backup:
        name = f"sebelum_kosongkan_{now_wib().strftime('%Y%m%d_%H%M%S')}"
        try:
            proc = await asyncio.create_subprocess_exec(
                BACKUP_SCRIPT, name,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
            if proc.returncode != 0:
                raise HTTPException(500,
                    "Cadangan pengaman gagal, pengosongan dibatalkan: " + stderr.decode()[:300])
            safety_backup = name
        except asyncio.TimeoutError:
            raise HTTPException(500, "Cadangan pengaman melebihi batas waktu, pengosongan dibatalkan.")

    cleared, failed = [], []
    for name in body.collections:
        try:
            res = await db[name].delete_many({})
            cleared.append({"name": name, "deleted": res.deleted_count})
        except Exception as e:
            failed.append({"name": name, "error": str(e)})

    total = sum(c["deleted"] for c in cleared)
    await _send_notification(
        user["id"],
        "Koleksi dikosongkan" if not failed else "Pengosongan sebagian gagal",
        f"{len(cleared)} koleksi dikosongkan ({total} dokumen dihapus)."
        + (f" Cadangan pengaman: {safety_backup}." if safety_backup else ""),
        "warning" if failed else "info",
    )
    return {
        "ok": True,
        "safety_backup": safety_backup,
        "cleared": cleared,
        "failed": failed,
        "total_deleted": total,
    }
