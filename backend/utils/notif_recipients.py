"""SSOT PENERIMA NOTIFIKASI + ANTI-SPAM PER-PENERIMA (FASE 14).
==============================================================

## Kenapa modul ini ada (3 bug NYATA yang ditutup di akarnya)

Sebelum FASE 14, pertanyaan *"siapa yang harus menerima notifikasi ini?"* dijawab
**terpisah di 4 tempat** dengan query yang berbeda-beda:

| Lokasi | Filter |
|---|---|
| `core/accessory_valuation.py` `notify_unvalued`        | `{active: {$ne: false}}` |
| `core/accessory_valuation.py` `send_unvalued_digest`   | `{active: {$ne: false}, status: {$ne: 'inactive'}}` |
| `services/accessory_valuation_mailer.py` `resolve_recipients` | `{active: {$ne: false}, status: {$ne: 'inactive'}}` |
| `services/accessory_valuation_mailer.py` `_notify_in_app`     | `{active: {$ne: false}, status: {$ne: 'inactive'}}` |

**BUG-N1 — guard yang tidak menjaga apa pun.** Koleksi `users` di DB ini
**tidak punya field `active` sama sekali** (dibuktikan: 0 dari 10 dokumen), status
karyawan disimpan di field `status`. Jadi `{"active": {"$ne": False}}` cocok dengan
SEMUA dokumen — termasuk user yang sudah **resign** (`status='inactive'`). Akibatnya
`notify_unvalued` mengirim alarm ke orang yang sudah tidak bekerja lagi, sementara
digest hariannya (yang filternya lengkap) tidak. Dua fitur, dua daftar penerima,
satu-satunya pembeda adalah kelalaian menyalin satu baris query.
`{"active": {"$ne": False}}` DIPERTAHANKAN di sini sebagai belt-and-braces untuk
DB lama yang mungkin memakai field itu — tapi TIDAK lagi berdiri sendiri.

**BUG-N2 / BUG-N3 — anti-spam yang menghukum orang yang salah.** Dedup notifikasi
dicek **GLOBAL** (`find_one` tanpa `user_id`): "sudah pernah ada notifikasi untuk
material X dalam 24 jam? kalau ya, JANGAN kirim ke siapa pun". Konsekuensinya:
begitu satu ronde terkirim, **penerima yang baru muncul** (karyawan baru, atau user
yang baru diaktifkan/naik role) **dilewati diam-diam** — hingga 24 jam untuk alarm
per-item, dan **sehari kalender penuh** untuk digest. Yang paling mungkin jadi
korban justru Admin Gudang / Admin Aksesoris baru: orang yang PERSIS ditugaskan
mengisi HPP yang hilang itu.

Niat anti-spam yang benar adalah **"maksimal 1 notifikasi per penerima per
material per window"** — bukan "maksimal 1 notifikasi di seluruh sistem".
`partition_recipients_by_dedup()` menegakkan itu: penerima yang SUDAH punya
notifikasi cocok dilewati, penerima yang BELUM tetap dikirimi.

## Prinsip
- SATU definisi "penerima aktif" (`ACTIVE_USER_FILTER`) untuk seluruh repo.
- Dedup selalu **per-penerima**, memakai filter yang sama dengan yang DITULIS
  (pelajaran FASE 13: nama field wajib diverifikasi terhadap PENULISNYA).
- Tidak pernah melempar exception: notifikasi bukan alasan menggagalkan mutasi stok.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence

# ─────────────────────────────────────────────────────────────────────────────
# SATU-SATUNYA definisi "user yang boleh menerima notifikasi"
# ─────────────────────────────────────────────────────────────────────────────
# `status` = field yang BENAR-BENAR dipakai koleksi `users` (lihat auth.py:134
# yang menulis `'status': 'active'` saat membuat user).
# `active` = belt-and-braces untuk dokumen lama/impor yang memakai boolean.
ACTIVE_USER_FILTER: dict = {
    "status": {"$ne": "inactive"},
    "active": {"$ne": False},
}

# Proyeksi standar penerima — cukup untuk in-app maupun email.
RECIPIENT_PROJECTION: dict = {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def active_user_filter(extra: Optional[dict] = None) -> dict:
    """Filter user aktif, opsional digabung dengan kriteria tambahan.

    Selalu pakai ini alih-alih menulis ulang `{"status": ...}` di tiap modul.
    """
    flt = dict(ACTIVE_USER_FILTER)
    if extra:
        flt.update(extra)
    return flt


async def resolve_role_recipients(
    db,
    roles: Iterable[str],
    *,
    limit: int = 200,
    require_email: bool = False,
) -> list[dict]:
    """Daftar user AKTIF yang punya salah satu `roles`.

    Args:
        roles:         daftar role penanggung jawab.
        limit:         batas dokumen (jaga-jaga DB besar).
        require_email: True → hanya user yang punya email (untuk kanal email).

    Return: list dict {id, name, email, role} — bisa kosong (bukan error).
    """
    role_list = [r for r in dict.fromkeys(roles) if r]
    if not role_list:
        return []
    flt = active_user_filter({"role": {"$in": role_list}})
    users = await db.users.find(flt, RECIPIENT_PROJECTION).to_list(limit)
    if require_email:
        users = [u for u in users if str(u.get("email") or "").strip()]
    return users


async def already_notified_user_ids(
    db,
    *,
    dedup_filter: dict,
    window_hours: Optional[float] = None,
    since: Optional[datetime] = None,
) -> set[str]:
    """user_id yang SUDAH punya notifikasi cocok `dedup_filter` dalam window.

    `dedup_filter` HARUS memakai nama field seperti yang benar-benar TERSIMPAN
    oleh `utils/notif_unified.notif_insert` (`subtype`, `meta.*`, `created_at`
    sebagai datetime — bukan string ISO). Pelajaran FASE 13: query yang tidak
    cocok 0 dokumen gagal DIAM-DIAM.
    """
    flt = dict(dedup_filter)
    if since is None and window_hours is not None:
        since = _now() - timedelta(hours=window_hours)
    if since is not None:
        flt["created_at"] = {"$gte": since}
    ids = await db.notifications.distinct("user_id", flt)
    return {i for i in ids if i}


async def partition_recipients_by_dedup(
    db,
    recipients: Sequence[dict],
    *,
    dedup_filter: dict,
    window_hours: Optional[float] = None,
    since: Optional[datetime] = None,
    force: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Pisahkan penerima menjadi (PERLU_DIKIRIM, SUDAH_PERNAH).

    Inilah inti perbaikan BUG-N2/N3: anti-spam ditegakkan **per-penerima**, jadi
    penerima baru tidak pernah dilewati hanya karena orang lain sudah diberi tahu.

    `force=True` melewati dedup sepenuhnya (dipakai tombol "kirim sekarang").
    """
    if not recipients:
        return [], []
    if force:
        return list(recipients), []
    done = await already_notified_user_ids(
        db, dedup_filter=dedup_filter, window_hours=window_hours, since=since,
    )
    todo = [u for u in recipients if u.get("id") not in done]
    skipped = [u for u in recipients if u.get("id") in done]
    return todo, skipped
