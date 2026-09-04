#!/usr/bin/env python3
"""verify_backup_restore_fix.py — bukti 2 perbaikan (2026-07-31):

  FIX-1  Penjaga limit file descriptor mongod (RLIMIT_NOFILE) supaya restore
         lewat Portal Administrasi Sistem tidak lagi kena WT_PANIC
         "Too many open files" → mongod abort → restore putus.
  FIX-2  Pesan kegagalan restore INFORMATIF (sebab + saran + log), bukan
         "Restore failed: " kosong seperti sebelumnya.

Uji ini AMAN: arsip rusak yang dipakai hanya berisi koleksi dummy
`zz_uji_gagal_restore`, jadi data asli tidak pernah di-drop.

Pakai: python3 /app/tests/verify_backup_restore_fix.py
"""
from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import sys
from pathlib import Path

import requests

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
BACKUPS = Path("/app/backups")
BAD_ID = "zz_uji_gagal_restore"
G, R, Y, C, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[0m"

checks: list[tuple[str, bool, str]] = []


def rec(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(f"  [{G}PASS{X}]" if ok else f"  [{R}FAIL{X}]", name, f"— {detail}" if detail else "")


def mongod_soft_limit() -> int | None:
    sys.path.insert(0, "/app/backend")
    from utils.mongod_fdlimit import find_mongod_pids, read_nofile
    pids = find_mongod_pids()
    if not pids:
        return None
    return read_nofile(pids[0])[0]


def set_soft_limit(value: int) -> None:
    sys.path.insert(0, "/app/backend")
    from utils.mongod_fdlimit import find_mongod_pids, read_nofile
    pid = find_mongod_pids()[0]
    hard = read_nofile(pid)[1] or value
    subprocess.run(["prlimit", f"--pid={pid}", f"--nofile={value}:{hard}"],
                   check=True, capture_output=True)


def make_corrupt_backup() -> None:
    """Arsip 'rusak': file .bson.gz berisi data sampah (bukan BSON valid)."""
    d = BACKUPS / BAD_ID / "test_database"
    if (BACKUPS / BAD_ID).exists():
        shutil.rmtree(BACKUPS / BAD_ID)
    d.mkdir(parents=True, exist_ok=True)
    (d / "zz_uji_gagal_restore.bson.gz").write_bytes(gzip.compress(b"BUKAN BSON SAMA SEKALI" * 50))
    (d / "zz_uji_gagal_restore.metadata.json.gz").write_bytes(
        gzip.compress(json.dumps({"options": {}, "indexes": []}).encode()))
    (BACKUPS / BAD_ID / "metadata.json").write_text(json.dumps({
        "backup_name": BAD_ID, "database": "test_database",
        "created_at": "2026-07-31T00:00:00+00:00", "size": "1K", "status": "uji",
    }), encoding="utf-8")


def main() -> int:
    print(f"{C}{'=' * 70}\nVERIFIKASI FIX BACKUP/RESTORE\n{'=' * 70}{X}")

    tok = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=30).json().get("token")
    rec("login admin", bool(tok))
    if not tok:
        return 1
    h = {"Authorization": f"Bearer {tok}"}

    # ── FIX-1: penjaga limit ────────────────────────────────────────────────
    print(f"\n{C}FIX-1 — Penjaga limit file descriptor mongod{X}")
    before_manual = mongod_soft_limit()
    rec("baca limit awal mongod", before_manual is not None, f"soft={before_manual}")
    set_soft_limit(1024)
    rec("turunkan paksa limit ke 1024 (simulasi kondisi rusak)", mongod_soft_limit() == 1024,
        f"soft={mongod_soft_limit()}")

    make_corrupt_backup()
    r = requests.post(f"{BASE}/api/admin/backup/restore", headers=h,
                      json={"backup_id": BAD_ID, "confirm": True}, timeout=300)
    after = mongod_soft_limit()
    rec("endpoint restore menaikkan limit otomatis (pre-restore guard)",
        after is not None and after > 1024, f"soft 1024 → {after}")

    # ── FIX-2: pesan kegagalan informatif ───────────────────────────────────
    print(f"\n{C}FIX-2 — Pesan kegagalan restore informatif{X}")
    rec("restore arsip rusak ditolak dengan HTTP 500", r.status_code == 500, f"HTTP {r.status_code}")
    detail = (r.json() or {}).get("detail")
    rec("detail berbentuk objek terstruktur (bukan string kosong)", isinstance(detail, dict),
        f"tipe={type(detail).__name__}")
    if isinstance(detail, dict):
        rec("ada field 'message'", bool(detail.get("message")), str(detail.get("message")))
        rec("ada field 'reason' (SEBAB)", bool(detail.get("reason")), str(detail.get("reason"))[:120])
        rec("ada field 'hint' (SARAN)", bool(detail.get("hint")), str(detail.get("hint"))[:120])
        rec("ada 'returncode' proses", detail.get("returncode") is not None,
            str(detail.get("returncode")))
        rec("ada 'log_lines' sebagai bukti teknis", bool(detail.get("log_lines")),
            f"{len(detail.get('log_lines') or [])} baris")
        lp = detail.get("log_path")
        rec("log lengkap tersimpan di disk", bool(lp) and Path(lp).exists(), str(lp))
        rec("TIDAK lagi memakai pesan lama 'Restore failed: '",
            "Restore failed: " not in json.dumps(detail), "pesan lama hilang")
        print(f"\n  {Y}Contoh yang kini dilihat user:{X}")
        print(f"    {detail.get('message')}")
        print(f"    Sebab : {detail.get('reason')}")
        print(f"    Saran : {detail.get('hint')}")
        for ln in (detail.get("log_lines") or [])[:3]:
            print(f"    log   | {ln[:150]}")

    # ── bersihkan & pulihkan ────────────────────────────────────────────────
    shutil.rmtree(BACKUPS / BAD_ID, ignore_errors=True)
    # mongorestore membuat koleksi kosong sebelum gagal → buang supaya DB bersih.
    subprocess.run(["mongosh", "--quiet", "test_database", "--eval",
                    f'db.getCollection("{BAD_ID}").drop()'], capture_output=True, text=True)
    hh = requests.get(f"{BASE}/api/health", timeout=20).json()
    rec("backend tetap sehat setelah uji", hh.get("db") == "connected", f"db={hh.get('db')}")
    names = subprocess.run(
        ["mongosh", "--quiet", "test_database", "--eval", "db.getCollectionNames().join(',')"],
        capture_output=True, text=True).stdout
    rec("koleksi dummy tidak meninggalkan sisa di DB", BAD_ID not in names, "bersih")

    ok = sum(1 for _, k, _ in checks if k)
    print(f"\n{C}{'=' * 70}{X}\n  HASIL: {G}{ok} PASS{X} / {R}{len(checks) - ok} FAIL{X}")
    for n, k, d in checks:
        if not k:
            print(f"    {R}✗{X} {n} — {d}")
    print(f"{C}{'=' * 70}{X}")
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
