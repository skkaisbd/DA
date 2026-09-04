#!/usr/bin/env bash
# =============================================================================
# ensure_mongod_fdlimit.sh — naikkan soft limit file descriptor (RLIMIT_NOFILE)
# proses `mongod` supaya backup/restore database besar tidak menabrak
# "Too many open files" (errno 24) → WT_PANIC → mongod abort → restore putus.
#
# Konteks lengkap + akar masalah: backend/utils/mongod_fdlimit.py
#
# Pakai:
#   bash /app/scripts/ensure_mongod_fdlimit.sh            # naikkan ke target (200k)
#   bash /app/scripts/ensure_mongod_fdlimit.sh --print     # hanya tampilkan status
#   MONGOD_NOFILE_TARGET=300000 bash /app/scripts/ensure_mongod_fdlimit.sh
#
# CATATAN: limit ini kembali ke default (1024) setiap mongod restart, karena
# config supervisor READ-ONLY. Karena itu backend memasang penjaga otomatis:
#   * saat startup backend, dan
#   * job APScheduler `mongod_fd_guard` tiap 5 menit, dan
#   * tepat sebelum setiap backup/restore dari Portal Administrasi Sistem.
# =============================================================================
set -uo pipefail
exec python3 /app/backend/utils/mongod_fdlimit.py "$@"
