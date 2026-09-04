"""utils/mongod_fdlimit.py — PENJAGA limit file descriptor mongod (RLIMIT_NOFILE).

AKAR MASALAH (ditemukan 2026-07-31; gejalanya: restore lewat Portal Administrasi
Sistem SELALU balas HTTP 500 dengan pesan kosong):

    supervisord menjalankan `mongod` dengan **soft limit 1024** file.
    Saat backup/restore database besar (186 koleksi x file data+index), WiredTiger
    memanggil directory-sync lalu kena errno 24 "Too many open files" →
    `WT_PANIC: the process must exit and restart` → fassert → **mongod ABORT**.
    Supervisor menghidupkan mongod kembali, tetapi `mongorestore` sudah terputus
    ("connection closed unexpectedly by the other side: EOF") sehingga restore
    berhenti separuh jalan dan database tertinggal setengah terisi.

KENAPA RUNTIME (prlimit), BUKAN UBAH CONFIG:
    `/etc/supervisor/conf.d/*.conf` di environment ini **READ-ONLY** ("DO NOT EDIT"),
    jadi `minfds` supervisord tidak bisa dinaikkan. Hard limit mongod sendiri sudah
    1.048.576, sehingga menaikkan **soft** limit TIDAK butuh privilege tambahan —
    cukup panggil syscall `prlimit64` ke PID mongod.

SIFAT: **IDEMPOTEN & AMAN**. Kalau limit sudah >= target, tidak melakukan apa pun.
Kalau mongod tidak ditemukan, hanya melaporkan (tidak pernah melempar exception ke
pemanggil) supaya tidak pernah menggagalkan startup backend.

DIPAKAI DI:
  * `server.py` startup                         → sekali tiap backend start
  * APScheduler job `mongod_fd_guard` (tiap 5m)  → jaring kalau mongod restart
  * `routes/admin_backup.py`                     → tepat sebelum backup/restore
  * `scripts/ensure_mongod_fdlimit.sh`           → manual / dipanggil bootstrap.sh

Pakai manual:
    python3 /app/backend/utils/mongod_fdlimit.py            # naikkan ke target
    python3 /app/backend/utils/mongod_fdlimit.py --print     # hanya lihat status
    MONGOD_NOFILE_TARGET=300000 python3 .../mongod_fdlimit.py
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

RLIMIT_NOFILE = 7  # <bits/resource.h> di Linux


def target_soft_limit() -> int:
    """Target soft limit. Bisa dioverride via env `MONGOD_NOFILE_TARGET`."""
    try:
        return max(4096, int(os.environ.get("MONGOD_NOFILE_TARGET", "200000")))
    except ValueError:
        return 200000


# ── deteksi proses mongod ────────────────────────────────────────────────────
def find_mongod_pids() -> list[int]:
    """Cari PID semua proses bernama `mongod` lewat /proc (tanpa dependensi luar)."""
    pids: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if (entry / "comm").read_text(encoding="utf-8").strip() == "mongod":
                pids.append(int(entry.name))
        except (OSError, ValueError):
            continue
    return sorted(pids)


def read_nofile(pid: int) -> tuple[int | None, int | None]:
    """Baca (soft, hard) RLIMIT_NOFILE dari /proc/<pid>/limits. None kalau gagal."""
    try:
        for line in Path(f"/proc/{pid}/limits").read_text(encoding="utf-8").splitlines():
            if line.startswith("Max open files"):
                parts = line.split()
                # "Max open files  <soft>  <hard>  files"
                soft_raw, hard_raw = parts[3], parts[4]
                soft = None if soft_raw == "unlimited" else int(soft_raw)
                hard = None if hard_raw == "unlimited" else int(hard_raw)
                return soft, hard
    except (OSError, ValueError, IndexError):
        pass
    return None, None


# ── penulisan limit ─────────────────────────────────────────────────────────
class _RLimit64(ctypes.Structure):
    _fields_ = [("rlim_cur", ctypes.c_uint64), ("rlim_max", ctypes.c_uint64)]


def _set_nofile_ctypes(pid: int, soft: int, hard: int) -> None:
    """Panggil syscall prlimit64 via libc. Melempar OSError kalau gagal."""
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.prlimit.argtypes = [ctypes.c_int, ctypes.c_int,
                             ctypes.POINTER(_RLimit64), ctypes.POINTER(_RLimit64)]
    libc.prlimit.restype = ctypes.c_int
    new = _RLimit64(rlim_cur=soft, rlim_max=hard)
    if libc.prlimit(pid, RLIMIT_NOFILE, ctypes.byref(new), None) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))


def _set_nofile_binary(pid: int, soft: int, hard: int) -> None:
    """Fallback: pakai util-linux `prlimit`."""
    subprocess.run(["prlimit", f"--pid={pid}", f"--nofile={soft}:{hard}"],
                   check=True, capture_output=True, timeout=20)


def ensure_mongod_fd_limit(target: int | None = None) -> dict:
    """Pastikan soft limit nofile mongod >= target. Idempoten, tidak pernah raise.

    Return ringkasan: {ok, target, processes:[{pid, before, after, changed}], error}
    """
    goal = target or target_soft_limit()
    out: dict = {"ok": True, "target": goal, "processes": [], "error": None}

    pids = find_mongod_pids()
    if not pids:
        out["ok"] = False
        out["error"] = "proses mongod tidak ditemukan"
        return out

    for pid in pids:
        soft, hard = read_nofile(pid)
        info = {"pid": pid, "before": soft, "after": soft, "changed": False, "error": None}
        if soft is not None and soft >= goal:
            out["processes"].append(info)
            continue
        # jangan pernah melampaui hard limit (kecuali hard = unlimited)
        want = goal if hard is None else min(goal, hard)
        want_hard = want if hard is None else hard
        try:
            try:
                _set_nofile_ctypes(pid, want, want_hard)
            except (OSError, AttributeError) as e_ctypes:
                logger.debug("prlimit64 via ctypes gagal (%s) — coba binary prlimit", e_ctypes)
                _set_nofile_binary(pid, want, want_hard)
            new_soft, _ = read_nofile(pid)
            info["after"] = new_soft
            info["changed"] = new_soft != soft
        except Exception as e:  # noqa: BLE001 — tidak boleh menggagalkan startup
            info["error"] = str(e)
            out["ok"] = False
            out["error"] = f"gagal menaikkan limit pid {pid}: {e}"
        out["processes"].append(info)

    return out


def ensure_and_log(context: str = "") -> dict:
    """Versi yang langsung menulis log (dipakai startup / scheduler / endpoint)."""
    res = ensure_mongod_fd_limit()
    tag = f"[mongod-fd-guard{(' ' + context) if context else ''}]"
    if not res["ok"] and not res["processes"]:
        logger.warning("%s %s", tag, res["error"])
        return res
    for p in res["processes"]:
        if p["error"]:
            logger.warning("%s pid=%s GAGAL naik: %s", tag, p["pid"], p["error"])
        elif p["changed"]:
            logger.info("%s pid=%s nofile %s → %s (target %s)",
                        tag, p["pid"], p["before"], p["after"], res["target"])
        else:
            logger.debug("%s pid=%s nofile %s sudah >= target %s",
                         tag, p["pid"], p["before"], res["target"])
    return res


def _cli() -> int:
    only_print = "--print" in sys.argv
    goal = target_soft_limit()
    pids = find_mongod_pids()
    if not pids:
        print("  ! proses mongod TIDAK ditemukan (mongodb mati?)")
        return 1
    if only_print:
        for pid in pids:
            soft, hard = read_nofile(pid)
            state = "OK" if (soft or 0) >= goal else "RENDAH"
            print(f"  mongod pid={pid}  nofile soft={soft} hard={hard}  target={goal}  [{state}]")
        return 0
    res = ensure_mongod_fd_limit(goal)
    for p in res["processes"]:
        if p["error"]:
            print(f"  x pid={p['pid']} GAGAL: {p['error']}")
        elif p["changed"]:
            print(f"  v pid={p['pid']} nofile {p['before']} -> {p['after']} (target {goal})")
        else:
            print(f"  . pid={p['pid']} nofile {p['before']} sudah >= target {goal} — tidak diubah")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(_cli())
